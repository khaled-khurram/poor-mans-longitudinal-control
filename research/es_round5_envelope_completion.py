#!/usr/bin/env python3
"""Round 5: three quantitative tasks in one archive pass.

1. Cruise_RPM (ess_cruise_rpm) transfer curve -> aego, wheel_torque, over
   acc_engaged_clean. Cruise_Throttle and Brake_Pressure already got this
   treatment in the original main run; Cruise_RPM never did.

2. Extend Round 4's Cruise_RPM vs Brake_Pressure wide-lag correlation from
   +/-1500ms to +/-3000ms (restricted to esb_brake_pressure>20 & ACC engaged,
   same gate Round 4 used) to find where the R^2=0.298-and-climbing curve
   actually peaks, or confirm it never does (a slow shared trend, not a
   lag-locked relationship).

3. Grade-correction attempt (G6): per-route baseline aego offset estimated
   from samples where es_cruise_throttle sits in a narrow band around global's
   documented "zero acceleration" anchor (1818 +/- 100), acc_engaged_clean
   only. Subtract each route's own offset from that route's aego samples
   before re-binning the Cruise_Throttle -> aego transfer curve; compare
   corrected vs uncorrected curve tightness.

Nothing here transmits. Read-only, same archive, same container.
"""
import bisect, json, math, statistics, sys
from collections import defaultdict, deque
from pathlib import Path
import capnp, zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
OUT_FILE = Path("/work/es_round5_results.json")

MS = 1_000_000
S = 1_000_000_000
HORIZON_NS = 20 * S
SETTLE_NS = 3 * S
MAX_STALE_NS = 200 * MS

EXT_LAGS_MS = list(range(-3000, 3025, 100))  # extended grid for task 2
NEUTRAL_LO, NEUTRAL_HI = 1718, 1918          # 1818 +/- 100, task 3 anchor
MIN_NEUTRAL_SAMPLES = 20                      # per-route floor for a usable offset


def u(dat, start, length):
  if len(dat) < 8: dat = bytes(dat) + b"\x00" * (8 - len(dat))
  raw = int.from_bytes(dat[:8], "little")
  return (raw >> start) & ((1 << length) - 1)


def dec_es_distance(d): return {"es_cruise_throttle": u(d, 0, 12)}
def dec_es_status(d): return {"ess_cruise_rpm": u(d, 16, 16)}
def dec_es_brake(d): return {"esb_brake_pressure": u(d, 0, 16)}
def dec_cruisecontrol(d): return {"cc_cruise_activated": u(d, 49, 1)}
def dec_throttle(d): return {"throttle_pedal": u(d, 0, 8)}
def dec_brake_pedal(d): return {"pedal_brake": u(d, 16, 8)}
def dec_engine(d): return {"wheel_torque": u(d, 16, 12)}

DECODERS = {
  (0x161, 2): dec_es_distance,
  (0x162, 2): dec_es_status,
  (0x160, 2): dec_es_brake,
  (0x144, 0): dec_cruisecontrol,
  (0x140, 0): dec_throttle,
  (0xD1, 0): dec_brake_pedal,
  (0x141, 0): dec_engine,
}
CENSUS_ADDRS = set(a for a, _ in DECODERS)


def read_rlog_bytes(seg):
  zp = seg / "rlog.zst"
  if zp.is_file():
    with open(zp, "rb") as f:
      return zstd.ZstdDecompressor().stream_reader(f).read()
  pp = seg / "rlog"
  return pp.read_bytes() if pp.is_file() else None


def find_route_groups():
  groups = defaultdict(list)
  for entry in RAW_DIR.iterdir():
    if not entry.is_dir() or "--" not in entry.name: continue
    rid, _, seg_str = entry.name.rpartition("--")
    try: groups[rid].append((int(seg_str), entry))
    except ValueError: continue
  for k in groups: groups[k].sort()
  return groups


class Buffers:
  def __init__(self, horizon_ns):
    self.horizon = horizon_ns
    self.ts = defaultdict(list); self.vs = defaultdict(list); self.head = defaultdict(int)
  def push(self, name, t, v):
    self.ts[name].append(t); self.vs[name].append(v)
  def trim(self, now):
    cutoff = now - self.horizon
    for name, ts in self.ts.items():
      h = self.head[name]; n = len(ts)
      while h < n and ts[h] < cutoff: h += 1
      if h >= 4096:
        del ts[:h]; del self.vs[name][:h]; h = 0
      self.head[name] = h
  def at(self, name, t, max_stale=MAX_STALE_NS):
    ts = self.ts.get(name)
    if not ts: return None, None
    h = self.head[name]
    i = bisect.bisect_right(ts, t, h) - 1
    if i < h: return None, None
    stale = t - ts[i]
    if max_stale is not None and stale > max_stale: return None, stale
    return self.vs[name][i], stale


def regime_clean(bufs, t):
  act, _ = bufs.at("cc_cruise_activated", t)
  gas, _ = bufs.at("throttle_pedal", t)
  brk, _ = bufs.at("pedal_brake", t)
  if not act: return False
  if gas and gas > 0: return False
  if brk and brk > 0: return False
  return True


def fit_at_lag(bufs, a_name, b_name, t, lag_ms, acc_dict):
  x, _ = bufs.at(a_name, t)
  y, _ = bufs.at(b_name, t + lag_ms * MS)
  if x is None or y is None: return
  a = acc_dict[lag_ms]
  a[0] += 1; a[1] += x; a[2] += y; a[3] += x*y; a[4] += x*x; a[5] += y*y


def fit_summary(acc_dict):
  best = None; curve = {}
  for lag_ms, a in acc_dict.items():
    n, sx, sy, sxy, sxx, syy = a
    if n < 200: continue
    varx = sxx - sx*sx/n; vary = syy - sy*sy/n; cov = sxy - sx*sy/n
    r2 = 0.0 if varx <= 0 or vary <= 0 else (cov*cov)/(varx*vary)
    r = 0.0 if varx <= 0 or vary <= 0 else cov/math.sqrt(varx*vary)
    slope = cov/varx if varx > 0 else 0.0
    rec = {"n": n, "r2": round(r2, 6), "r": round(r, 5), "slope": round(slope, 6)}
    curve[str(lag_ms)] = rec
    if best is None or r2 > best[1]["r2"]: best = (lag_ms, rec)
  return {"curve": curve, "best": ({"lag_ms": best[0], **best[1]} if best else None)}


class Acc:
  def __init__(self):
    self.routes_ok = 0; self.routes_err = 0
    self.n_clean_ticks = 0
    self.n_active_brake_ticks = 0
    # task 1: RPM -> aego / wheel_torque, binned (100-count bins)
    self.rpm_aego = defaultdict(lambda: [0, 0.0])
    self.rpm_wt = defaultdict(lambda: [0, 0.0])
    # task 2: extended-lag RPM vs Brake correlation
    self.fit_rpm_brake_ext = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0])
    # task 3: uncorrected vs grade-corrected Cruise_Throttle -> aego (50-count bins)
    self.ct_aego_uncorrected = defaultdict(lambda: [0, 0.0])
    self.ct_aego_corrected = defaultdict(lambda: [0, 0.0])
    self.route_offsets = []  # per-route neutral-band offset, for reporting spread


def process_route(schema, acc, route_id, segments):
  bufs = Buffers(HORIZON_NS)
  pending = deque()
  # per-route buffers for the grade-correction pass (task 3)
  route_ct_aego = []       # (ct, aego) during acc_engaged_clean
  route_neutral_aego = []  # aego where CT in [NEUTRAL_LO, NEUTRAL_HI]

  def drain(now, force=False):
    while pending and (force or now - pending[0] > SETTLE_NS):
      t = pending.popleft()
      clean = regime_clean(bufs, t)
      act, _ = bufs.at("cc_cruise_activated", t)

      if clean:
        acc.n_clean_ticks += 1
        ct, _ = bufs.at("es_cruise_throttle", t)
        rpm, _ = bufs.at("ess_cruise_rpm", t)
        ae, _ = bufs.at("aego", t)
        wt, _ = bufs.at("wheel_torque", t)
        ve, _ = bufs.at("vego", t)

        if rpm is not None and ve is not None and ve > 5.0:
          b = int(rpm // 100) * 100
          if ae is not None:
            a = acc.rpm_aego[b]; a[0] += 1; a[1] += ae
          if wt is not None:
            a = acc.rpm_wt[b]; a[0] += 1; a[1] += wt

        if ct is not None and ae is not None and ve is not None and ve > 5.0:
          route_ct_aego.append((ct, ae))
          if NEUTRAL_LO <= ct <= NEUTRAL_HI:
            route_neutral_aego.append(ae)

      # task 2: active-brake extended lag (independent of the clean-regime gate,
      # matching Round 4's own gating exactly: ACC engaged + brake active)
      bp, _ = bufs.at("esb_brake_pressure", t)
      if act and bp is not None and bp > 20:
        acc.n_active_brake_ticks += 1
        for lag_ms in EXT_LAGS_MS:
          fit_at_lag(bufs, "ess_cruise_rpm", "esb_brake_pressure", t, lag_ms, acc.fit_rpm_brake_ext)

  for _idx, seg in segments:
    data = read_rlog_bytes(seg)
    if not data: continue
    try:
      for ev in schema.Event.read_multiple_bytes(data):
        which = ev.which()
        if which == "carState":
          try:
            bufs.push("vego", ev.logMonoTime, float(ev.carState.vEgo))
            bufs.push("aego", ev.logMonoTime, float(ev.carState.aEgo))
          except Exception:
            pass
          continue
        if which != "can": continue
        t = ev.logMonoTime
        for fr in ev.can:
          addr = fr.address
          if addr not in CENSUS_ADDRS: continue
          key = (addr, fr.src)
          if key not in DECODERS: continue
          vals = DECODERS[key](bytes(fr.dat))
          for name, v in vals.items():
            bufs.push(name, t, float(v))
          if addr == 0x161 and fr.src == 2:
            pending.append(t)
        bufs.trim(t); drain(t)
    except Exception:
      continue
  drain(0, force=True)

  # end-of-route: fold this route's (ct, aego) samples into the global bins,
  # both uncorrected and grade-corrected by this route's own neutral offset
  for ct, ae in route_ct_aego:
    b = int(ct // 50) * 50
    a = acc.ct_aego_uncorrected[b]; a[0] += 1; a[1] += ae

  if len(route_neutral_aego) >= MIN_NEUTRAL_SAMPLES:
    offset = statistics.fmean(route_neutral_aego)
    acc.route_offsets.append({"route_id": route_id, "n": len(route_neutral_aego), "offset": round(offset, 4)})
    for ct, ae in route_ct_aego:
      b = int(ct // 50) * 50
      a = acc.ct_aego_corrected[b]; a[0] += 1; a[1] += (ae - offset)
  else:
    # not enough neutral-band samples to estimate this route's offset --
    # fold in uncorrected (offset=0), consistent with "can't correct what
    # we can't estimate" rather than dropping the route's data entirely
    for ct, ae in route_ct_aego:
      b = int(ct // 50) * 50
      a = acc.ct_aego_corrected[b]; a[0] += 1; a[1] += ae


def main():
  schema = capnp.load(str(SCHEMA_DIR / "log.capnp"), imports=[str(SCHEMA_DIR)])
  groups = find_route_groups()
  route_ids = sorted(groups)
  print(f"found {len(groups)} routes", file=sys.stderr)
  acc = Acc()
  for idx, rid in enumerate(route_ids):
    try:
      process_route(schema, acc, rid, groups[rid])
      acc.routes_ok += 1
    except Exception as e:
      acc.routes_err += 1
      print(f"ROUTE ERROR {rid}: {e}", file=sys.stderr)
    if (idx + 1) % 20 == 0:
      print(f"... {idx+1}/{len(route_ids)} routes, {acc.n_clean_ticks} clean ticks, "
            f"{acc.n_active_brake_ticks} active-brake ticks, {len(acc.route_offsets)} routes with usable offset",
            file=sys.stderr)

  def bins_to_json(d, min_n=30):
    return {str(b): {"n": v[0], "mean": round(v[1] / v[0], 4)} for b, v in sorted(d.items()) if v[0] >= min_n}

  offs = [r["offset"] for r in acc.route_offsets]
  out = {
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "n_clean_ticks": acc.n_clean_ticks,
    "n_active_brake_ticks": acc.n_active_brake_ticks,
    "task1_cruise_rpm_transfer": {
      "rpm_to_aego": bins_to_json(acc.rpm_aego),
      "rpm_to_wheel_torque": bins_to_json(acc.rpm_wt),
    },
    "task2_rpm_vs_brake_extended_lag": fit_summary(acc.fit_rpm_brake_ext),
    "task3_grade_correction": {
      "n_routes_with_usable_offset": len(acc.route_offsets),
      "offset_stats": {
        "median": round(statistics.median(offs), 4) if offs else None,
        "stdev": round(statistics.pstdev(offs), 4) if len(offs) > 1 else None,
        "min": round(min(offs), 4) if offs else None,
        "max": round(max(offs), 4) if offs else None,
      },
      "route_offsets_sample": acc.route_offsets[:50],
      "ct_aego_uncorrected": bins_to_json(acc.ct_aego_uncorrected),
      "ct_aego_corrected": bins_to_json(acc.ct_aego_corrected),
    },
  }
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE. {acc.routes_ok} ok, {acc.routes_err} err.", file=sys.stderr)
  print("task2 best:", json.dumps(out["task2_rpm_vs_brake_extended_lag"]["best"]))
  print("task3 n_routes_with_usable_offset:", len(acc.route_offsets))
  print("task3 offset_stats:", json.dumps(out["task3_grade_correction"]["offset_stats"]))


if __name__ == "__main__":
  main()
