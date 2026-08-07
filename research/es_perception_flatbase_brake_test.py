#!/usr/bin/env python3
"""
Round 3, pre-registered in research/es_stage0_round3_brake_prereg.md, run here
EXACTLY as specified there -- do not tune anything in this file to change the
outcome. Adapted from research/es_perception_flatbase_rpm_test.py (Round 2),
swapping the field under test to esb_brake_pressure (ES_Brake, 0x160) and the
primary comparator to brake2_left (Brake_2, 0xD2).

ONSET THRESHOLDS -- reused directly from T6's already-validated calibration
(research/es_longitudinal_command_results.md), NOT re-derived:
  esb_brake_pressure: 20 counts (T6's own activation threshold)
  brake2_right / brake2_left: 2.0 counts (T6's own onset threshold)
  mc_brake_right / mc_brake_left: 2.0 counts (T6's own onset threshold)
  aego: 0.2 (T6's own onset threshold)

RESPONSE WINDOW EXTENDED to 2.5s (vs Rounds 1-2's 1.2s) -- ES_Brake requires
an extra brake-vs-throttle-only decision on top of ordinary response latency.
POWER FLOOR LOWERED to N>=50 (vs Rounds 1-2's N>=100) -- braking-tied cut-ins
are expected to be structurally rarer than throttle-modulation events. Both
fixed in the pre-registration before this script was run.

PRIMARY ENDPOINT: frac_brake_first_50 = fraction of qualifying LEAD-ACQUIRED
events where onset(esb_brake_pressure) precedes onset(brake2_left) by >=50ms.
  CONFIRM: frac_brake_first_50 >= 70% AND median margin >= 75ms
  NULL:    frac_brake_first_50 <= 50% OR median margin <= 25ms
  INCONCLUSIVE: anything between, or N < 50 (the power floor)

brake2_right / mc_brake_right / mc_brake_left / aego are descriptive
secondaries only, same demotion pattern as engine_rpm_140/wheel_torque in
Rounds 1-2. Lead-LOST events excluded from the primary set, reported
unfiltered as a secondary, same as both prior rounds.

The ~25ms quantization bias (ES_Distance is 20Hz) is acknowledged and NOT
corrected for, same as both prior rounds.

Nothing here transmits. Read-only, same archive, same container.
"""
import bisect
import json
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path

import capnp
import zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path("/work/es_perception_flatbase_brake_results.json")

MS = 1_000_000
S = 1_000_000_000

HORIZON_NS = 20 * S
SETTLE_NS = 5 * S
MAX_STALE_NS = 200 * MS

PRE_NS = 1 * S              # baseline window: [-1000ms, -50ms] -- unchanged
POST_NS = 2500 * MS         # response window: (0, +2500ms] -- EXTENDED vs Rounds 1-2
ISOLATION_NS = 2 * S        # unchanged
SUSTAIN_NS = 1 * S          # unchanged

# pre-registered, not tuned
FLATBASE_MAX_PP2P = 15.0    # 75% of the 20-count onset threshold
REAL_RESPONSE_MIN = 20.0    # == onset threshold, same convention as Rounds 1-2
PRIMARY_MARGIN_FLOOR_MS = 50.0

CONFIRM_FRAC = 70.0
CONFIRM_MARGIN_MS = 75.0
NULL_FRAC = 50.0
NULL_MARGIN_MS = 25.0
POWER_FLOOR_N = 50          # LOWERED vs Rounds 1-2's 100, reasoning in the prereg doc

GATE_PRE_NS = PRE_NS
GATE_POST_NS = POST_NS

MAX_EVENTS = 4000
MAX_EVENTS_PER_ROUTE = 150
MAX_TRACES = 40

ONSET_THRESHOLDS = {
  "esb_brake_pressure": 20.0,
  "brake2_left": 2.0,
  "brake2_right": 2.0,
  "mc_brake_right": 2.0,
  "mc_brake_left": 2.0,
  "aego": 0.2,
}

ADDR_ES_DISTANCE = 0x161
ADDR_ES_BRAKE = 0x160
ADDR_CRUISECONTROL = 0x144
ADDR_BRAKE_PRESSURE = 0x150
ADDR_BRAKE_2 = 0xD2
ADDR_BRAKE_PEDAL = 0xD1
ADDR_THROTTLE = 0x140
MAIN_BUS = 0
CAM_BUS = 2


def u(dat, start, length):
  if len(dat) < 8:
    dat = bytes(dat) + b"\x00" * (8 - len(dat))
  raw = int.from_bytes(dat[:8], "little")
  return (raw >> start) & ((1 << length) - 1)


def dec_es_distance(d):
  return {
    "es_car_follow": u(d, 16, 1),
    "es_close_distance": u(d, 24, 8) * 0.019607,
    "es_cruise_fault": u(d, 42, 1),
  }


def dec_es_brake(d):
  return {"esb_brake_pressure": u(d, 0, 16)}


def dec_cruisecontrol(d):
  return {"cc_cruise_on": u(d, 48, 1), "cc_cruise_activated": u(d, 49, 1)}


def dec_brake_pressure(d):
  return {"mc_brake_right": u(d, 0, 8), "mc_brake_left": u(d, 8, 8)}


def dec_brake_2(d):
  return {"brake2_right": u(d, 48, 8), "brake2_left": u(d, 56, 8)}


def dec_brake_pedal(d):
  return {"pedal_brake": u(d, 16, 8)}


def dec_throttle(d):
  return {"throttle_pedal": u(d, 0, 8)}


DECODERS = {
  (ADDR_ES_DISTANCE, CAM_BUS): dec_es_distance,
  (ADDR_ES_BRAKE, CAM_BUS): dec_es_brake,
  (ADDR_CRUISECONTROL, MAIN_BUS): dec_cruisecontrol,
  (ADDR_BRAKE_PRESSURE, MAIN_BUS): dec_brake_pressure,
  (ADDR_BRAKE_2, MAIN_BUS): dec_brake_2,
  (ADDR_BRAKE_PEDAL, MAIN_BUS): dec_brake_pedal,
  (ADDR_THROTTLE, MAIN_BUS): dec_throttle,
}
CENSUS_ADDRS = set(a for a, _ in DECODERS)

# primary comparator first, then descriptive-only
COMPARATORS = ["brake2_left", "brake2_right", "mc_brake_right", "mc_brake_left", "aego"]


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


def onset_latency(bufs, name, t0, min_abs_change, k_sigma=3.0):
  base = bufs.window(name, t0 - PRE_NS, t0 - 50 * MS)
  post = bufs.window(name, t0 - 100 * MS, t0 + POST_NS)
  if len(base) < 5 or len(post) < 5:
    return None
  vals = [v for _, v in base]
  mu = statistics.fmean(vals)
  sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
  thr = max(k_sigma * sd, min_abs_change)
  for ts, v in post:
    if abs(v - mu) > thr:
      return ts - t0
  return None


class Acc:
  def __init__(self):
    self.routes_ok = 0
    self.routes_err = 0
    self.events = []          # flat-baseline-qualified, lead acquired (PRIMARY)
    self.events_lost = []     # lead lost, unfiltered (secondary)
    self.traces = []
    self.n_ticks = 0
    self.n_cf_transitions_seen = 0
    self.rejected = defaultdict(int)


def classify_and_record(acc, bufs, t, route_id, direction, per_route):
  ev = {
    "route_id": route_id, "t": t, "direction": direction,
    "bp_before": bufs.at("esb_brake_pressure", t - 100 * MS)[0],
    "close_distance": bufs.at("es_close_distance", t)[0],
  }
  spd, _ = bufs.at("speed_ref", t)
  ev["vego_kph"] = spd

  for name, thr in ONSET_THRESHOLDS.items():
    lat = onset_latency(bufs, name, t, thr)
    ev[f"lat_{name}_ms"] = None if lat is None else lat / MS

  bp = ev.get("lat_esb_brake_pressure_ms")
  for cmp_name in COMPARATORS:
    cmpl = ev.get(f"lat_{cmp_name}_ms")
    if bp is None or cmpl is None:
      ev[f"margin_vs_{cmp_name}_ms"] = None
    else:
      ev[f"margin_vs_{cmp_name}_ms"] = cmpl - bp  # positive => brake_pressure moved FIRST

  bucket = acc.events if direction == "acquired" else acc.events_lost
  if len(bucket) < MAX_EVENTS:
    bucket.append(ev)

  if len(acc.traces) < MAX_TRACES and bp is not None:
    trace = []
    for dt_ms in range(-1100, 2600, 100):
      row = [dt_ms]
      for name in ("esb_brake_pressure", "es_car_follow", "brake2_left",
                   "brake2_right", "mc_brake_right", "throttle_pedal"):
        row.append(bufs.at(name, t + dt_ms * MS)[0])
      trace.append(row)
    acc.traces.append({
      "route_id": route_id, "t": t, "direction": direction,
      "columns": ["dt_ms", "esb_brake_pressure", "car_follow", "brake2_left",
                  "brake2_right", "mc_brake_right", "throttle_pedal"],
      "rows": trace,
    })


def process_route(log_schema, acc, route_id, segments):
  bufs = Buffers(HORIZON_NS)
  pending = deque()
  per_route = {"n": 0}

  def drain(now, force=False):
    while pending and (force or now - pending[0] > SETTLE_NS):
      t = pending.popleft()
      acc.n_ticks += 1

      act, _ = bufs.at("cc_cruise_activated", t)
      if not act:
        continue

      cf_now, _ = bufs.at("es_car_follow", t)
      cf_prev, _ = bufs.at("es_car_follow", t - 100 * MS)
      if cf_now is None or cf_prev is None or cf_now == cf_prev:
        continue
      acc.n_cf_transitions_seen += 1
      direction = "acquired" if cf_now > cf_prev else "lost"

      if per_route["n"] >= MAX_EVENTS_PER_ROUTE:
        acc.rejected["per_route_cap"] += 1
        continue

      gas_win = bufs.window("throttle_pedal", t - GATE_PRE_NS, t + GATE_POST_NS)
      brk_win = bufs.window("pedal_brake", t - GATE_PRE_NS, t + GATE_POST_NS)
      if not gas_win or any(v > 0 for _, v in gas_win):
        acc.rejected["driver_gas"] += 1
        continue
      if any(v > 0 for _, v in brk_win):
        acc.rejected["driver_brake"] += 1
        continue

      act_win = bufs.window("cc_cruise_activated", t - GATE_PRE_NS, t + GATE_POST_NS)
      if not act_win or any(v < 1 for _, v in act_win):
        acc.rejected["acc_dropped"] += 1
        continue

      flt = bufs.window("es_cruise_fault", t - GATE_PRE_NS, t + GATE_POST_NS)
      if any(v > 0 for _, v in flt):
        acc.rejected["cruise_fault"] += 1
        continue

      cf_win = bufs.window("es_car_follow", t - ISOLATION_NS, t + ISOLATION_NS)
      transitions = 0
      for i in range(1, len(cf_win)):
        if cf_win[i][1] != cf_win[i - 1][1]:
          if abs(cf_win[i][0] - t) > 60 * MS:
            transitions += 1
      if transitions > 0:
        acc.rejected["not_isolated"] += 1
        continue

      sustain = bufs.window("es_car_follow", t, t + SUSTAIN_NS)
      if not sustain or any(v != cf_now for _, v in sustain):
        acc.rejected["not_sustained"] += 1
        continue

      if direction == "acquired":
        base_win = bufs.window("esb_brake_pressure", t - PRE_NS, t - 50 * MS)
        if len(base_win) < 5:
          acc.rejected["insufficient_baseline"] += 1
          continue
        base_vals = [v for _, v in base_win]
        pp2p = max(base_vals) - min(base_vals)
        if pp2p > FLATBASE_MAX_PP2P:
          acc.rejected["baseline_not_flat"] += 1
          continue

        post_win = bufs.window("esb_brake_pressure", t, t + POST_NS)
        base_mu = statistics.fmean(base_vals)
        max_dev = max((abs(v - base_mu) for _, v in post_win), default=0.0)
        if max_dev < REAL_RESPONSE_MIN:
          acc.rejected["no_real_response"] += 1
          continue

      per_route["n"] += 1
      classify_and_record(acc, bufs, t, route_id, direction, per_route)

  for _seg_idx, seg_dir in segments:
    for ev in iter_events(log_schema, seg_dir):
      try:
        which = ev.which()
        t = ev.logMonoTime
      except Exception:
        continue

      if which == "carState":
        try:
          bufs.push("speed_ref", t, float(ev.carState.vEgo))
        except Exception:
          pass
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
          key = (addr, frame.src)
          if key not in DECODERS:
            continue
          vals = DECODERS[key](bytes(frame.dat))
          for name, v in vals.items():
            bufs.push(name, t, float(v))
          if addr == ADDR_ES_DISTANCE and frame.src == CAM_BUS:
            pending.append(t)
        except Exception:
          continue
      bufs.trim(t)
      drain(t)
  drain(0, force=True)


def med(xs):
  xs = [x for x in xs if x is not None]
  return round(statistics.median(xs), 2) if xs else None


def pct(a, b):
  return None if not b else round(100.0 * a / b, 2)


def summarize(events, label):
  out = {"label": label, "n": len(events)}
  for name in ONSET_THRESHOLDS:
    lats = [e.get(f"lat_{name}_ms") for e in events]
    out[f"median_lat_{name}_ms"] = med(lats)
    out[f"n_detected_{name}"] = sum(1 for v in lats if v is not None)
  for cmp_name in COMPARATORS:
    margins = [e.get(f"margin_vs_{cmp_name}_ms") for e in events]
    usable = [m for m in margins if m is not None]
    wins = sum(1 for m in usable if m > 0)
    solid = sum(1 for m in usable if m >= PRIMARY_MARGIN_FLOOR_MS)
    out[f"vs_{cmp_name}"] = {
      "n_usable": len(usable),
      "median_margin_ms": med(usable),
      "frac_brake_first": pct(wins, len(usable)),
      "frac_brake_first_by_50ms_or_more": pct(solid, len(usable)),
    }
  return out


def apply_prereg_verdict(acquired_summary, n_qualifying):
  """Mechanical application of the fixed decision rule. Do not edit thresholds here."""
  primary = acquired_summary["vs_brake2_left"]
  frac50 = primary["frac_brake_first_by_50ms_or_more"]
  median_margin = primary["median_margin_ms"]

  if n_qualifying < POWER_FLOOR_N:
    return {
      "verdict": "INCONCLUSIVE",
      "reason": f"n_qualifying={n_qualifying} < power floor {POWER_FLOOR_N}",
      "frac_brake_first_50": frac50, "median_margin_ms": median_margin,
    }
  if frac50 is None or median_margin is None:
    return {"verdict": "INCONCLUSIVE", "reason": "insufficient usable pairs",
            "frac_brake_first_50": frac50, "median_margin_ms": median_margin}

  if frac50 >= CONFIRM_FRAC and median_margin >= CONFIRM_MARGIN_MS:
    verdict = "CONFIRM"
  elif frac50 <= NULL_FRAC or median_margin <= NULL_MARGIN_MS:
    verdict = "NULL"
  else:
    verdict = "INCONCLUSIVE"
  return {
    "verdict": verdict,
    "reason": f"frac_brake_first_50={frac50}%, median_margin={median_margin}ms, n={n_qualifying}",
    "frac_brake_first_50": frac50, "median_margin_ms": median_margin,
  }


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
            f"{len(acc.events)} flat-baseline-qualified acquired / "
            f"{len(acc.events_lost)} lost (unfiltered), "
            f"{acc.n_cf_transitions_seen} raw transitions seen", file=sys.stderr)

  acquired_summary = summarize(acc.events, "Car_Follow 0->1, flat-baseline-qualified (PRIMARY)")
  lost_summary = summarize(acc.events_lost, "Car_Follow 1->0, unfiltered (secondary)")
  verdict = apply_prereg_verdict(acquired_summary, len(acc.events))

  out = {
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "n_es_ticks": acc.n_ticks,
    "n_raw_car_follow_transitions": acc.n_cf_transitions_seen,
    "rejected_reasons": dict(acc.rejected),
    "prereg_constants": {
      "FLATBASE_MAX_PP2P": FLATBASE_MAX_PP2P, "REAL_RESPONSE_MIN": REAL_RESPONSE_MIN,
      "PRIMARY_MARGIN_FLOOR_MS": PRIMARY_MARGIN_FLOOR_MS,
      "CONFIRM_FRAC": CONFIRM_FRAC, "CONFIRM_MARGIN_MS": CONFIRM_MARGIN_MS,
      "NULL_FRAC": NULL_FRAC, "NULL_MARGIN_MS": NULL_MARGIN_MS,
      "POWER_FLOOR_N": POWER_FLOOR_N, "POST_NS_ms": POST_NS / MS,
    },
    "onset_thresholds": ONSET_THRESHOLDS,
    "PRIMARY_VERDICT": verdict,
    "lead_acquired_flatbase_qualified": acquired_summary,
    "lead_lost_unfiltered_secondary": lost_summary,
    "traces": acc.traces,
    "raw_events_acquired": acc.events[:800],
    "raw_events_lost": acc.events_lost[:800],
  }
  OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE. {acc.routes_ok} ok, {acc.routes_err} err. -> {OUT_FILE}", file=sys.stderr)
  print(json.dumps({k: v for k, v in out.items()
                    if k not in ("traces", "raw_events_acquired", "raw_events_lost")},
                   indent=2, default=str))


if __name__ == "__main__":
  main()
