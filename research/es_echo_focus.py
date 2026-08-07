#!/usr/bin/env python3
"""
Focused follow-up to es_longitudinal_command_correlation.py, answering exactly
the priority-1 question the main run's coarse +/-200ms lag grid could not:

  (a) How tightly does 0x140.Throttle_Cruise (the engine's own report) track
      0x161.Cruise_Throttle (EyeSight's field), at what lag, over a WIDE lag
      range (+/-1500ms) restricted to acc_engaged_clean -- the main run's best
      fit hit the +/-200ms boundary in both directions, meaning the true
      optimum (if any) was clipped and never found.
  (b) What does Throttle_Cruise (the echo) do during a driver gas-pedal
      override while ACC is engaged? The main script's T5 detector recorded
      deltas for es_cruise_throttle/throttle_body/engine_rpm/throttle_pedal/
      ess_cruise_rpm/vego but NOT throttle_cruise itself -- a real gap, since
      this is the single most decisive measurement per the task brief.
  (c) Does throttle_cruise correlate with throttle_pedal directly (i.e. is the
      ECU's own reported "cruise throttle" simply driven by the pedal,
      independent of ES) -- a control check on interpretation.

Nothing here transmits. Read-only, same archive, same container.

STATUS: run 2026-08-07 against the full 282-route archive. Results and interpretation
in research/es_longitudinal_command_results.md.
"""
import bisect
import json
import math
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path

import capnp
import zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path("/work/es_echo_focus_results.json")

MS = 1_000_000
S = 1_000_000_000

HORIZON_NS = 20 * S
SETTLE_NS = 3 * S
MAX_STALE_NS = 200 * MS

# wide lag grid for the affine fit, positive = ES leads (compare ES(t) to
# report(t+lag)). Steps of 50ms out to +/-1500ms.
LAGS_MS = list(range(-1500, 1525, 50))

MAX_EVENTS = 2000

ADDR_ES_DISTANCE = 0x161
ADDR_THROTTLE = 0x140
ADDR_CRUISECONTROL = 0x144
ADDR_BRAKE_PEDAL = 0xD1
MAIN_BUS = 0
CAM_BUS = 2


def u(dat, start, length):
  if len(dat) < 8:
    dat = bytes(dat) + b"\x00" * (8 - len(dat))
  raw = int.from_bytes(dat[:8], "little")
  return (raw >> start) & ((1 << length) - 1)


def dec_es_distance(d):
  return {"es_cruise_throttle": u(d, 0, 12)}


def dec_throttle(d):
  return {
    "throttle_pedal": u(d, 0, 8),
    "throttle_cruise": u(d, 32, 8),
    "throttle_body": u(d, 48, 8),
  }


def dec_cruisecontrol(d):
  return {"cc_cruise_on": u(d, 48, 1), "cc_cruise_activated": u(d, 49, 1)}


def dec_brake_pedal(d):
  return {"pedal_brake": u(d, 16, 8)}


DECODERS = {
  (ADDR_ES_DISTANCE, CAM_BUS): dec_es_distance,
  (ADDR_THROTTLE, MAIN_BUS): dec_throttle,
  (ADDR_CRUISECONTROL, MAIN_BUS): dec_cruisecontrol,
  (ADDR_BRAKE_PEDAL, MAIN_BUS): dec_brake_pedal,
}
CENSUS_ADDRS = set(a for a, _ in DECODERS)


def load_schema():
  return capnp.load(str(SCHEMA_FILE), imports=[str(SCHEMA_DIR)])


def read_rlog_bytes(segment_dir):
  zst_path = segment_dir / "rlog.zst"
  plain_path = segment_dir / "rlog"
  if zst_path.is_file():
    try:
      with open(zst_path, "rb") as f:
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(f) as reader:
          return reader.read()
    except Exception:
      return None
  elif plain_path.is_file():
    try:
      return plain_path.read_bytes()
    except Exception:
      return None
  return None


def iter_events(log_schema, segment_dir):
  data = read_rlog_bytes(segment_dir)
  if not data:
    return
  try:
    for event in log_schema.Event.read_multiple_bytes(data):
      yield event
  except Exception:
    return


def find_route_groups():
  groups = {}
  for entry in RAW_DIR.iterdir():
    if not entry.is_dir():
      continue
    name = entry.name
    if "--" not in name:
      continue
    route_id, _, seg_str = name.rpartition("--")
    if not route_id:
      continue
    try:
      seg_idx = int(seg_str)
    except ValueError:
      continue
    groups.setdefault(route_id, []).append((seg_idx, entry))
  for route_id in groups:
    groups[route_id].sort(key=lambda t: t[0])
  return groups


class Buffers:
  COMPACT_AT = 4096

  def __init__(self, horizon_ns):
    self.horizon = horizon_ns
    self.ts = defaultdict(list)
    self.vs = defaultdict(list)
    self.head = defaultdict(int)

  def push(self, name, t, v):
    self.ts[name].append(t)
    self.vs[name].append(v)

  def trim(self, now):
    cutoff = now - self.horizon
    for name, ts in self.ts.items():
      h = self.head[name]
      n = len(ts)
      while h < n and ts[h] < cutoff:
        h += 1
      if h >= self.COMPACT_AT:
        del ts[:h]
        del self.vs[name][:h]
        h = 0
      self.head[name] = h

  def at(self, name, t, max_stale=MAX_STALE_NS):
    ts = self.ts.get(name)
    if not ts:
      return None, None
    h = self.head[name]
    i = bisect.bisect_right(ts, t, h) - 1
    if i < h:
      return None, None
    stale = t - ts[i]
    if max_stale is not None and stale > max_stale:
      return None, stale
    return self.vs[name][i], stale

  def window(self, name, t0, t1):
    ts = self.ts.get(name)
    if not ts:
      return []
    h = self.head[name]
    lo = bisect.bisect_left(ts, t0, h)
    hi = bisect.bisect_right(ts, t1, lo)
    vs = self.vs[name]
    return list(zip(ts[lo:hi], vs[lo:hi]))


def regime_of(bufs, t):
  act, _ = bufs.at("cc_cruise_activated", t)
  on, _ = bufs.at("cc_cruise_on", t)
  gas, _ = bufs.at("throttle_pedal", t)
  brk, _ = bufs.at("pedal_brake", t)
  if act is None or on is None:
    return "unknown"
  if act:
    if brk:
      return "acc_engaged_brake"
    if gas:
      return "acc_engaged_gas"
    return "acc_engaged_clean"
  if on:
    return "acc_on_not_engaged"
  return "acc_off"


class Acc:
  def __init__(self):
    self.routes_ok = 0
    self.routes_err = 0
    # (lag_ms) -> [n, sx, sy, sxy, sxx, syy] for es_cruise_throttle vs throttle_cruise,
    # acc_engaged_clean only
    self.fit_ct_vs_tc = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0])
    # control: throttle_cruise vs throttle_pedal, same lag grid, acc_engaged_clean
    self.fit_tc_vs_pedal = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0])
    self.override_events = []
    self.n_acc_engaged_clean_ticks = 0


def fit_at_lag(bufs, esf_name, rf_name, t, lag_ms, acc_dict):
  x, _ = bufs.at(esf_name, t)
  y, _ = bufs.at(rf_name, t + lag_ms * MS)
  if x is None or y is None:
    return
  a = acc_dict[lag_ms]
  a[0] += 1
  a[1] += x
  a[2] += y
  a[3] += x * y
  a[4] += x * x
  a[5] += y * y


def process_route(log_schema, acc, route_id, segments):
  bufs = Buffers(HORIZON_NS)
  pending = deque()
  per_route_ovr = 0

  def drain(now, force=False):
    nonlocal per_route_ovr
    while pending and (force or now - pending[0] > SETTLE_NS):
      t = pending.popleft()
      regime = regime_of(bufs, t)
      if regime == "acc_engaged_clean":
        acc.n_acc_engaged_clean_ticks += 1
        for lag_ms in LAGS_MS:
          fit_at_lag(bufs, "es_cruise_throttle", "throttle_cruise", t, lag_ms, acc.fit_ct_vs_tc)
          fit_at_lag(bufs, "throttle_cruise", "throttle_pedal", t, lag_ms, acc.fit_tc_vs_pedal)

      # override event detection, same definition as the main script's T5
      gas_now, _ = bufs.at("throttle_pedal", t)
      gas_prev, _ = bufs.at("throttle_pedal", t - 200 * MS)
      act, _ = bufs.at("cc_cruise_activated", t)
      if (gas_now and not gas_prev and act and per_route_ovr < 200
          and len(acc.override_events) < MAX_EVENTS):
        sustained = bufs.window("throttle_pedal", t, t + 500 * MS)
        if sustained and all(v > 0 for _, v in sustained):
          def delta(name, a, b):
            va, _ = bufs.at(name, t + a)
            vb, _ = bufs.at(name, t + b)
            if va is None or vb is None:
              return None
            return vb - va

          per_route_ovr += 1
          # sampled trace of both fields from -300ms to +2500ms @ ~100ms
          trace = []
          for dt_ms in range(-300, 2600, 100):
            ct, _ = bufs.at("es_cruise_throttle", t + dt_ms * MS)
            tc, _ = bufs.at("throttle_cruise", t + dt_ms * MS)
            tb, _ = bufs.at("throttle_body", t + dt_ms * MS)
            pd, _ = bufs.at("throttle_pedal", t + dt_ms * MS)
            trace.append([dt_ms, ct, tc, tb, pd])
          acc.override_events.append({
            "route_id": route_id, "t": t,
            "ct_before": bufs.at("es_cruise_throttle", t - 100 * MS)[0],
            "tc_before": bufs.at("throttle_cruise", t - 100 * MS)[0],
            "d_es_cruise_throttle": delta("es_cruise_throttle", -100 * MS, 1500 * MS),
            "d_throttle_cruise": delta("throttle_cruise", -100 * MS, 1500 * MS),
            "d_throttle_body": delta("throttle_body", -100 * MS, 1500 * MS),
            "d_throttle_pedal": delta("throttle_pedal", -100 * MS, 1500 * MS),
            "trace": trace,
          })

  for _seg_idx, seg_dir in segments:
    for ev in iter_events(log_schema, seg_dir):
      try:
        which = ev.which()
        t = ev.logMonoTime
      except Exception:
        continue
      if which != "can":
        continue
      try:
        frames = ev.can
      except Exception:
        continue
      for frame in frames:
        try:
          addr = frame.address
          if addr not in CENSUS_ADDRS:
            continue
          src = frame.src
          key = (addr, src)
          if key not in DECODERS:
            continue
          dat = bytes(frame.dat)
          vals = DECODERS[key](dat)
          for name, v in vals.items():
            bufs.push(name, t, float(v))
          if addr == ADDR_ES_DISTANCE and src == CAM_BUS:
            pending.append(t)
        except Exception:
          continue
      bufs.trim(t)
      drain(t)
  drain(0, force=True)


def fit_summary(acc_dict):
  out = {}
  best = None
  for lag_ms, a in acc_dict.items():
    n, sx, sy, sxy, sxx, syy = a
    if n < 300:
      continue
    varx = sxx - sx * sx / n
    vary = syy - sy * sy / n
    cov = sxy - sx * sy / n
    r2 = 0.0 if varx <= 0 or vary <= 0 else (cov * cov) / (varx * vary)
    r = 0.0 if varx <= 0 or vary <= 0 else cov / math.sqrt(varx * vary)
    slope = cov / varx if varx > 0 else 0.0
    rec = {"n": n, "r2": round(r2, 6), "r": round(r, 5), "slope": round(slope, 6)}
    out[str(lag_ms)] = rec
    if best is None or r2 > best[1]["r2"]:
      best = (lag_ms, rec)
  return {"curve": out, "best": {"lag_ms": best[0], **best[1]} if best else None}


def main():
  log_schema = load_schema()
  groups = find_route_groups()
  route_ids = sorted(groups)
  print(f"found {len(groups)} routes", file=sys.stderr)
  acc = Acc()
  for idx, route_id in enumerate(route_ids):
    try:
      process_route(log_schema, acc, route_id, groups[route_id])
      acc.routes_ok += 1
    except Exception as e:
      acc.routes_err += 1
      print(f"ROUTE ERROR {route_id}: {e}", file=sys.stderr)
    if (idx + 1) % 20 == 0:
      print(f"... {idx+1}/{len(route_ids)} routes, "
            f"{acc.n_acc_engaged_clean_ticks} acc-clean ticks, "
            f"{len(acc.override_events)} override events", file=sys.stderr)

  echo_fit = fit_summary(acc.fit_ct_vs_tc)
  pedal_fit = fit_summary(acc.fit_tc_vs_pedal)

  # override summary: does throttle_cruise (echo) move with the pedal/engine,
  # same-direction-fraction and gain relative to es_cruise_throttle's own move
  ovr = acc.override_events
  usable_tc = [e for e in ovr if e.get("d_throttle_cruise") is not None
               and e.get("d_throttle_pedal") not in (None, 0)]
  same_tc_pedal = sum(1 for e in usable_tc if e["d_throttle_cruise"] * e["d_throttle_pedal"] > 0)
  usable_ct = [e for e in ovr if e.get("d_es_cruise_throttle") is not None
               and e.get("d_throttle_pedal") not in (None, 0)]
  same_ct_pedal = sum(1 for e in usable_ct if e["d_es_cruise_throttle"] * e["d_throttle_pedal"] > 0)
  usable_tc_ct = [e for e in ovr if e.get("d_throttle_cruise") is not None
                  and e.get("d_es_cruise_throttle") not in (None, 0)]
  same_tc_ct = sum(1 for e in usable_tc_ct if e["d_throttle_cruise"] * e["d_es_cruise_throttle"] > 0)

  def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None

  out = {
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "n_acc_engaged_clean_ticks": acc.n_acc_engaged_clean_ticks,
    "lags_ms_tested": LAGS_MS,
    "echo_relationship_es_cruise_throttle_vs_throttle_cruise": echo_fit,
    "control_throttle_cruise_vs_throttle_pedal": pedal_fit,
    "override_events": {
      "n": len(ovr),
      "n_usable_tc_vs_pedal": len(usable_tc),
      "frac_throttle_cruise_same_sign_as_pedal": None if not usable_tc else round(100 * same_tc_pedal / len(usable_tc), 2),
      "median_d_throttle_cruise": med([e.get("d_throttle_cruise") for e in ovr]),
      "n_usable_ct_vs_pedal": len(usable_ct),
      "frac_es_cruise_throttle_same_sign_as_pedal": None if not usable_ct else round(100 * same_ct_pedal / len(usable_ct), 2),
      "median_d_es_cruise_throttle": med([e.get("d_es_cruise_throttle") for e in ovr]),
      "n_usable_tc_vs_ct": len(usable_tc_ct),
      "frac_throttle_cruise_same_sign_as_es_cruise_throttle": None if not usable_tc_ct else round(100 * same_tc_ct / len(usable_tc_ct), 2),
    },
    "sample_traces": ovr[:60],
  }
  OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE. {acc.routes_ok} ok, {acc.routes_err} err. Written to {OUT_FILE}", file=sys.stderr)
  print(json.dumps({k: v for k, v in out.items() if k != "sample_traces"}, indent=2, default=str)[:6000])


if __name__ == "__main__":
  main()
