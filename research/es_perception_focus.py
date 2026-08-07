#!/usr/bin/env python3
"""
The perception-trigger discriminator: can Cruise_Throttle move for a reason the
powertrain does not yet know about?

WHY THIS TEST EXISTS
--------------------
research/es_longitudinal_command_results.md reached the identifiability ceiling
described in the hypothesis doc's G1: every archive sample is EyeSight's own
self-consistent output, so "EyeSight commands the engine via 0x161" and
"EyeSight publishes its internal demand on 0x161 while commanding some other
way" produce identical signatures. T2/T3/T4/T5 all measure ES-vs-powertrain
relationships, and a sufficiently faithful *report* can mimic a command in all
of them.

This test attacks that directly, using an input that is exogenous to the
powertrain: a PERCEPTION event. ES_Distance (0x161) carries Car_Follow (bit 16)
and Close_Distance (24|8) in the SAME FRAME as Cruise_Throttle (0|12). When a
lead vehicle is acquired or lost, EyeSight's controller learns about it
instantly -- but the engine has no reason to have changed anything yet.

  COMMAND  => Cruise_Throttle moves at/near the perception event, and the
              powertrain (Throttle_Body, Engine_RPM, Wheel_Torque) follows.
  REPORT   => Cruise_Throttle cannot move until the powertrain moves first,
              because it would have nothing to report. So powertrain leads.

The decisive statistic is therefore an ORDERING, per event, internally
controlled: does Cruise_Throttle's onset precede Throttle_Body's onset?
A report cannot systematically win that race on a perception-triggered event.

TIMING RESOLUTION CAVEAT, stated up front: ES_Distance ticks at 20Hz (50ms),
Throttle (0x140) at ~100Hz (10ms). So Cruise_Throttle's onset is quantized to
+/-25ms while the powertrain's is not. A lead of less than ~50ms is NOT
meaningful. Only a consistent lead well beyond one ES frame counts, and the
summary reports the margin distribution, not just a win rate.

THRESHOLDS: deliberately identical to the ones already used in the completed
es_longitudinal_command_correlation.py run (T4/T6 onset detection), NOT retuned
for this test:
  es_cruise_throttle 40 counts | throttle_body 2.0 | engine_rpm_140 30.0
  wheel_torque 20.0 | aego 0.15 | throttle_cruise 2.0
Onset = first sample departing its own pre-event baseline by more than
max(3*sigma, min_abs_change), same detector as the main script.

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
OUT_FILE = Path("/work/es_perception_focus_results.json")

MS = 1_000_000
S = 1_000_000_000

HORIZON_NS = 20 * S
SETTLE_NS = 4 * S
MAX_STALE_NS = 200 * MS

PRE_NS = 1 * S            # baseline window before the event
POST_NS = 1200 * MS       # response window after the event
ISOLATION_NS = 2 * S      # no other Car_Follow transition within +/- this
SUSTAIN_NS = 1 * S        # new Car_Follow state must hold this long

# Cleanliness gates (driver pedals, ACC state) are applied over exactly the
# measurement window [-PRE_NS, +POST_NS], NOT a wider one. Rationale, recorded
# so it is not mistaken for tuning-to-taste: the decisive statistic is which
# signal moves FIRST in the few hundred ms after the perception event, and a
# driver input well after the response window cannot retroactively change that
# ordering. A first pass gating over +/-3s rejected 100% of transitions (71/71
# on a 12-route sample) and would have produced no test at all. Residual risk:
# a driver input landing just inside the window can still create a spurious
# late "onset" for a signal that had no real response -- which is why the
# headline statistic is the >=50ms margin fraction, not raw onset presence.
GATE_PRE_NS = PRE_NS
GATE_POST_NS = POST_NS

MAX_EVENTS = 4000
MAX_EVENTS_PER_ROUTE = 150
MAX_TRACES = 40

# same as the completed main run -- not retuned for this test
ONSET_THRESHOLDS = {
  "es_cruise_throttle": 40.0,
  "throttle_body": 2.0,
  "throttle_cruise": 2.0,
  "engine_rpm_140": 30.0,
  "wheel_torque": 20.0,
  "aego": 0.15,
}

ADDR_ES_DISTANCE = 0x161
ADDR_THROTTLE = 0x140
ADDR_ENGINE = 0x141
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
  return {
    "es_cruise_throttle": u(d, 0, 12),
    "es_car_follow": u(d, 16, 1),
    "es_brake_active": u(d, 20, 1),
    "es_close_distance": u(d, 24, 8) * 0.019607,
    "es_cruise_fault": u(d, 42, 1),
  }


def dec_throttle(d):
  return {
    "throttle_pedal": u(d, 0, 8),
    "engine_rpm_140": u(d, 16, 14),
    "throttle_cruise": u(d, 32, 8),
    "throttle_body": u(d, 48, 8),
  }


def dec_engine(d):
  return {"wheel_torque": u(d, 16, 12)}


def dec_cruisecontrol(d):
  return {"cc_cruise_on": u(d, 48, 1), "cc_cruise_activated": u(d, 49, 1)}


def dec_brake_pedal(d):
  return {"pedal_brake": u(d, 16, 8)}


DECODERS = {
  (ADDR_ES_DISTANCE, CAM_BUS): dec_es_distance,
  (ADDR_THROTTLE, MAIN_BUS): dec_throttle,
  (ADDR_ENGINE, MAIN_BUS): dec_engine,
  (ADDR_CRUISECONTROL, MAIN_BUS): dec_cruisecontrol,
  (ADDR_BRAKE_PEDAL, MAIN_BUS): dec_brake_pedal,
}
CENSUS_ADDRS = set(a for a, _ in DECODERS)

# powertrain signals the ES field is raced against
POWERTRAIN = ["throttle_body", "engine_rpm_140", "wheel_torque"]


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
  """Same detector as the main script: first post-t0 sample departing its own
  pre-t0 baseline by more than max(k*sigma, min_abs_change)."""
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
    self.events = []          # lead acquired (Car_Follow 0->1)
    self.events_lost = []     # lead lost      (Car_Follow 1->0)
    self.traces = []
    self.n_ticks = 0
    self.n_cf_transitions_seen = 0
    self.rejected = defaultdict(int)


def classify_and_record(acc, bufs, t, route_id, direction, per_route):
  """Score one isolated, clean Car_Follow transition at time t."""
  ev = {
    "route_id": route_id, "t": t, "direction": direction,
    "vego_kph": None,
    "ct_before": bufs.at("es_cruise_throttle", t - 100 * MS)[0],
    "close_distance": bufs.at("es_close_distance", t)[0],
  }
  spd, _ = bufs.at("speed_ref", t)
  ev["vego_kph"] = spd

  for name, thr in ONSET_THRESHOLDS.items():
    lat = onset_latency(bufs, name, t, thr)
    ev[f"lat_{name}_ms"] = None if lat is None else lat / MS

  # the decisive comparison: did the ES field's onset precede the powertrain's?
  ct = ev.get("lat_es_cruise_throttle_ms")
  for pw in POWERTRAIN:
    pwl = ev.get(f"lat_{pw}_ms")
    if ct is None or pwl is None:
      ev[f"margin_vs_{pw}_ms"] = None
    else:
      # positive => Cruise_Throttle moved FIRST by this many ms
      ev[f"margin_vs_{pw}_ms"] = pwl - ct

  bucket = acc.events if direction == "acquired" else acc.events_lost
  if len(bucket) < MAX_EVENTS:
    bucket.append(ev)

  if len(acc.traces) < MAX_TRACES and ct is not None:
    trace = []
    for dt_ms in range(-600, 1600, 50):
      row = [dt_ms]
      for name in ("es_cruise_throttle", "es_car_follow", "throttle_body",
                   "throttle_cruise", "engine_rpm_140", "throttle_pedal"):
        row.append(bufs.at(name, t + dt_ms * MS)[0])
      trace.append(row)
    acc.traces.append({
      "route_id": route_id, "t": t, "direction": direction,
      "columns": ["dt_ms", "cruise_throttle", "car_follow", "throttle_body",
                  "throttle_cruise", "engine_rpm", "throttle_pedal"],
      "rows": trace,
    })


def process_route(log_schema, acc, route_id, segments):
  bufs = Buffers(HORIZON_NS)
  pending = deque()
  per_route = {"n": 0}
  cf_history = []  # (t, value) of Car_Follow at each ES tick

  def drain(now, force=False):
    while pending and (force or now - pending[0] > SETTLE_NS):
      t = pending.popleft()
      acc.n_ticks += 1

      # --- regime gate: ACC engaged, no driver pedal anywhere in the window ---
      act, _ = bufs.at("cc_cruise_activated", t)
      if not act:
        continue

      # find the Car_Follow transition at this tick, if any
      cf_now, _ = bufs.at("es_car_follow", t)
      cf_prev, _ = bufs.at("es_car_follow", t - 100 * MS)
      if cf_now is None or cf_prev is None or cf_now == cf_prev:
        continue
      acc.n_cf_transitions_seen += 1

      direction = "acquired" if cf_now > cf_prev else "lost"

      if per_route["n"] >= MAX_EVENTS_PER_ROUTE:
        acc.rejected["per_route_cap"] += 1
        continue

      # driver must not touch pedals across the measurement window
      gas_win = bufs.window("throttle_pedal", t - GATE_PRE_NS, t + GATE_POST_NS)
      brk_win = bufs.window("pedal_brake", t - GATE_PRE_NS, t + GATE_POST_NS)
      if not gas_win or any(v > 0 for _, v in gas_win):
        acc.rejected["driver_gas"] += 1
        continue
      if any(v > 0 for _, v in brk_win):
        acc.rejected["driver_brake"] += 1
        continue

      # ACC must stay engaged across the window
      act_win = bufs.window("cc_cruise_activated", t - GATE_PRE_NS, t + GATE_POST_NS)
      if not act_win or any(v < 1 for _, v in act_win):
        acc.rejected["acc_dropped"] += 1
        continue

      # no EyeSight fault in the window
      flt = bufs.window("es_cruise_fault", t - GATE_PRE_NS, t + GATE_POST_NS)
      if any(v > 0 for _, v in flt):
        acc.rejected["cruise_fault"] += 1
        continue

      # isolation: no other Car_Follow transition within +/- ISOLATION_NS
      cf_win = bufs.window("es_car_follow", t - ISOLATION_NS, t + ISOLATION_NS)
      transitions = 0
      for i in range(1, len(cf_win)):
        if cf_win[i][1] != cf_win[i - 1][1]:
          if abs(cf_win[i][0] - t) > 60 * MS:
            transitions += 1
      if transitions > 0:
        acc.rejected["not_isolated"] += 1
        continue

      # the new state must be sustained
      sustain = bufs.window("es_car_follow", t, t + SUSTAIN_NS)
      if not sustain or any(v != cf_now for _, v in sustain):
        acc.rejected["not_sustained"] += 1
        continue

      # Cruise_Throttle pinned at the floor for the whole window carries no
      # information about ordering -- exclude rather than score as "no onset"
      ct_win = bufs.window("es_cruise_throttle", t - GATE_PRE_NS, t + GATE_POST_NS)
      if ct_win and max(v for _, v in ct_win) <= 810:
        acc.rejected["ct_pinned_at_floor"] += 1
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
          bufs.push("aego", t, float(ev.carState.aEgo))
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

  # the decisive ordering statistic
  for pw in POWERTRAIN:
    margins = [e.get(f"margin_vs_{pw}_ms") for e in events]
    usable = [m for m in margins if m is not None]
    wins = sum(1 for m in usable if m > 0)
    # only count as a real lead if it exceeds one ES frame (50ms)
    solid = sum(1 for m in usable if m >= 50)
    out[f"vs_{pw}"] = {
      "n_usable": len(usable),
      "median_margin_ms": med(usable),
      "frac_cruise_throttle_first": pct(wins, len(usable)),
      "frac_cruise_throttle_first_by_50ms_or_more": pct(solid, len(usable)),
    }
  return out


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
            f"{len(acc.events)} acquired / {len(acc.events_lost)} lost events, "
            f"{acc.n_cf_transitions_seen} raw transitions seen", file=sys.stderr)

  out = {
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "n_es_ticks": acc.n_ticks,
    "n_raw_car_follow_transitions": acc.n_cf_transitions_seen,
    "rejected_reasons": dict(acc.rejected),
    "onset_thresholds": ONSET_THRESHOLDS,
    "timing_note": ("ES_Distance is 20Hz so Cruise_Throttle onset is quantized "
                    "to +/-25ms; Throttle(0x140) is ~100Hz. A margin under "
                    "~50ms is not meaningful. frac_*_by_50ms_or_more is the "
                    "conservative statistic."),
    "lead_acquired": summarize(acc.events, "Car_Follow 0->1 (lead acquired)"),
    "lead_lost": summarize(acc.events_lost, "Car_Follow 1->0 (lead lost)"),
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
