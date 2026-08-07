#!/usr/bin/env python3
"""
Test B extraction for the capture drive: gas-override maneuvers, restricted to
the routes recorded on the deliberate capture drive (per
research/es_capture_drive_protocol.md), applying the exact pre-registered
decision rule from research/es_stage0_prereg_round2.md Test B.

Reuses the identical T5 event definition from
research/es_longitudinal_command_correlation.py: throttle_pedal 0->nonzero
while cc_cruise_activated, sustained >=500ms, measured -100ms -> +1500ms.

FIXED after a first run: the first version computed the +1500ms delta and the
+500ms "sustained" check immediately at detection time, before that much
future data had actually streamed into the buffer (single forward pass, no
settle/defer) -- every d_throttle_body came back None (195/195) as a result.
This version uses the same settle-then-drain pending-queue pattern as every
other script in this campaign: a trigger is queued, then only scored once
enough real future data exists.

Nothing here transmits. Read-only, same archive, same container.
"""
import bisect
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import capnp
import zstandard as zstd

NEW_ROUTES = {"000000c9--0afa14f389", "000000ca--a82378f79a",
              "000000cb--9c36ab21eb", "000000cc--628fef79f1"}

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path("/work/capdrive_testB_results.json")

MS = 1_000_000
S = 1_000_000_000
MAX_STALE_NS = 200 * MS
HORIZON_NS = 10 * S
SETTLE_NS = 2000 * MS  # >= the 1500ms furthest lookahead needed, plus margin

ADDR_ES_DISTANCE = 0x161
ADDR_THROTTLE = 0x140
ADDR_CRUISECONTROL = 0x144
ADDR_BRAKE_PEDAL = 0xD1
MAIN_BUS = 0
CAM_BUS = 2

MIDRANGE_LO, MIDRANGE_HI = 2600, 3100
FLOOR_LO, FLOOR_HI = 0, 900


def u(dat, start, length):
  if len(dat) < 8:
    dat = bytes(dat) + b"\x00" * (8 - len(dat))
  raw = int.from_bytes(dat[:8], "little")
  return (raw >> start) & ((1 << length) - 1)


def dec_es_distance(d):
  return {"es_cruise_throttle": u(d, 0, 12)}


def dec_throttle(d):
  return {"throttle_pedal": u(d, 0, 8), "throttle_body": u(d, 48, 8)}


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
    if not route_id or route_id not in NEW_ROUTES:
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
      self.head[name] = h

  def at(self, name, t, max_stale=MAX_STALE_NS):
    ts = self.ts.get(name)
    if not ts:
      return None
    h = self.head[name]
    i = bisect.bisect_right(ts, t, h) - 1
    if i < h:
      return None
    stale = t - ts[i]
    if max_stale is not None and stale > max_stale:
      return None
    return self.vs[name][i]

  def window(self, name, t0, t1):
    ts = self.ts.get(name)
    if not ts:
      return []
    h = self.head[name]
    lo = bisect.bisect_left(ts, t0, h)
    hi = bisect.bisect_right(ts, t1, lo)
    vs = self.vs[name]
    return list(zip(ts[lo:hi], vs[lo:hi]))


def score_trigger(bufs, t, route_id, events_out):
  """Called only once >=SETTLE_NS of future data exists past t."""
  sustained = bufs.window("throttle_pedal", t, t + 500 * MS)
  if not sustained or not all(v > 0 for _, v in sustained):
    return

  def delta(name, a, b):
    va = bufs.at(name, t + a)
    vb = bufs.at(name, t + b)
    if va is None or vb is None:
      return None
    return vb - va

  ct_before = bufs.at("es_cruise_throttle", t - 100 * MS)
  events_out.append({
    "route_id": route_id, "t": t, "ct_before": ct_before,
    "d_es_cruise_throttle": delta("es_cruise_throttle", -100 * MS, 1500 * MS),
    "d_throttle_body": delta("throttle_body", -100 * MS, 1500 * MS),
  })


def process_route(log_schema, events_out, route_id, segments):
  bufs = Buffers(HORIZON_NS)
  pending = deque()  # candidate trigger timestamps awaiting enough future data

  def drain(now, force=False):
    while pending and (force or now - pending[0] > SETTLE_NS):
      t = pending.popleft()
      score_trigger(bufs, t, route_id, events_out)

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
          key = (addr, frame.src)
          if key not in DECODERS:
            continue
          vals = DECODERS[key](bytes(frame.dat))
          for name, v in vals.items():
            bufs.push(name, t, float(v))
        except Exception:
          continue

      # T5 trigger definition, identical to the main correlation script --
      # detection uses only PAST/current data (safe at detection time); the
      # sustained/delta scoring is deferred via the pending queue above.
      gas_now = bufs.at("throttle_pedal", t)
      gas_prev = bufs.at("throttle_pedal", t - 200 * MS)
      act = bufs.at("cc_cruise_activated", t)
      if gas_now and not gas_prev and act:
        pending.append(t)

      bufs.trim(t)
      drain(t)
  drain(0, force=True)


def dedup(events, window_ns=5 * S):
  byroute = defaultdict(list)
  for e in events:
    byroute[e["route_id"]].append(e)
  out = []
  for rid, evs in byroute.items():
    evs.sort(key=lambda x: x["t"])
    last_t = None
    for e in evs:
      if last_t is None or (e["t"] - last_t) > window_ns:
        out.append(e)
        last_t = e["t"]
  return out


def band_stats(events, lo, hi, label):
  sel = [e for e in events if e.get("ct_before") is not None and lo <= e["ct_before"] < hi]
  usable = [e for e in sel if e.get("d_es_cruise_throttle") is not None
            and e.get("d_throttle_body") not in (None, 0)]
  same = sum(1 for e in usable if e["d_es_cruise_throttle"] * e["d_throttle_body"] > 0)
  opp = sum(1 for e in usable if e["d_es_cruise_throttle"] * e["d_throttle_body"] < 0)
  return {
    "label": label, "n_in_band": len(sel), "n_usable": len(usable),
    "same_sign": same, "opposite_sign": opp,
    "frac_opposite_sign": None if not usable else round(100 * opp / len(usable), 2),
    "events": sel,
  }


def main():
  log_schema = load_schema()
  groups = find_route_groups()
  print(f"found {len(groups)} matching new routes: {sorted(groups)}", file=sys.stderr)
  raw_events = []
  for route_id in sorted(groups):
    try:
      before = len(raw_events)
      process_route(log_schema, raw_events, route_id, groups[route_id])
      print(f"  {route_id}: {len(groups[route_id])} segments, "
            f"{len(raw_events) - before} raw events", file=sys.stderr)
    except Exception as e:
      print(f"ROUTE ERROR {route_id}: {e}", file=sys.stderr)

  deduped = dedup(raw_events)
  midrange = band_stats(deduped, MIDRANGE_LO, MIDRANGE_HI, "mid-range 2600-3100 (the prediction)")
  floor = band_stats(deduped, FLOOR_LO, FLOOR_HI, "floor ~808-900 (control group)")

  n = midrange["n_usable"]
  frac_opp = midrange["frac_opposite_sign"]
  if n < 30:
    verdict = f"INCONCLUSIVE (n={n} < power floor of 30)"
  elif frac_opp is not None and frac_opp >= 60:
    verdict = f"PREDICTION CONFIRMED (opposite-sign={frac_opp}% >= 60%)"
  elif frac_opp is not None and frac_opp <= 40:
    verdict = f"PREDICTION FALSIFIED (opposite-sign={frac_opp}% <= 40%)"
  else:
    verdict = f"INCONCLUSIVE (opposite-sign={frac_opp}%, between 40-60%)"

  out = {
    "raw_events_all_bands": len(raw_events),
    "deduped_events_all_bands": len(deduped),
    "midrange_band": midrange,
    "floor_band": floor,
    "prereg_verdict_midrange": verdict,
    "power_floor_note": "N>=30 required, target>=50, per es_stage0_prereg_round2.md",
  }
  OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE -> {OUT_FILE}", file=sys.stderr)
  print(json.dumps({
    "raw_events_all_bands": out["raw_events_all_bands"],
    "deduped_events_all_bands": out["deduped_events_all_bands"],
    "prereg_verdict_midrange": out["prereg_verdict_midrange"],
    "midrange_summary": {k: v for k, v in midrange.items() if k != "events"},
    "floor_summary": {k: v for k, v in floor.items() if k != "events"},
  }, indent=2, default=str))


if __name__ == "__main__":
  main()
