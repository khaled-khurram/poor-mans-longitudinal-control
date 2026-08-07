#!/usr/bin/env python3
"""
Follow-up to es_longitudinal_command_correlation.py's T2 pair-fit result for
ess_cruise_rpm (0x162 Cruise_RPM) vs trans_engine (0x148 Transmission_Engine):
R^2 = 0.9889 at the +200ms grid boundary -- both suspiciously close to the K1
threshold (0.999) AND at the edge of the tested lag range, same clipping
problem as the Cruise_Throttle/Throttle_Cruise pair. This resolves the true
best lag and settles the K1 sign question (echo vs command direction) with a
wide grid, restricted to acc_engaged_clean.

This is the pre-registered "most confident" prediction in
es_longitudinal_command_hypothesis.md Sec 4.3 -- worth getting right rather
than reporting a boundary-clipped number.

Nothing here transmits. Read-only, same archive, same container.

STATUS: run 2026-08-07 against the full 282-route archive. First run had a real bug --
ADDR_ES_DISTANCE (the 20Hz tick clock) was never added to DECODERS/CENSUS_ADDRS, so every
ES_Distance frame was filtered out before the tick-append check ran and n_acc_engaged_clean_ticks
came back 0. Fixed (added a no-op decoder for the tick address) and re-run. Results and
interpretation in research/es_longitudinal_command_results.md.
"""
import bisect
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import capnp
import zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path("/work/es_rpm_focus_results.json")

MS = 1_000_000
S = 1_000_000_000

HORIZON_NS = 20 * S
SETTLE_NS = 3 * S
MAX_STALE_NS = 200 * MS

LAGS_MS = list(range(-1500, 1525, 50))

ADDR_ES_DISTANCE = 0x161
ADDR_ES_STATUS = 0x162
ADDR_TRANSMISSION = 0x148
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


def dec_es_status(d):
  return {"ess_cruise_rpm": u(d, 16, 16)}


def dec_es_distance_tick(d):
  # only used to drive the 20Hz tick clock (TICK_ADDR) -- no fields needed
  return {}


def dec_transmission(d):
  return {"trans_engine": u(d, 16, 15)}


def dec_throttle(d):
  return {"throttle_pedal": u(d, 0, 8), "engine_rpm_140": u(d, 16, 14)}


def dec_cruisecontrol(d):
  return {"cc_cruise_on": u(d, 48, 1), "cc_cruise_activated": u(d, 49, 1)}


def dec_brake_pedal(d):
  return {"pedal_brake": u(d, 16, 8)}


DECODERS = {
  (ADDR_ES_STATUS, CAM_BUS): dec_es_status,
  (ADDR_ES_DISTANCE, CAM_BUS): dec_es_distance_tick,
  (ADDR_TRANSMISSION, MAIN_BUS): dec_transmission,
  (ADDR_THROTTLE, MAIN_BUS): dec_throttle,
  (ADDR_CRUISECONTROL, MAIN_BUS): dec_cruisecontrol,
  (ADDR_BRAKE_PEDAL, MAIN_BUS): dec_brake_pedal,
}
CENSUS_ADDRS = set(a for a, _ in DECODERS)
# ES_Distance drives the 20Hz tick clock, same as the main script, so ticks
# line up with real ES frames rather than an arbitrary timer
TICK_ADDR = ADDR_ES_DISTANCE


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
    self.fit_rpm_vs_trans = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0])
    self.fit_rpm_vs_erpm = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0])
    self.n_ticks = 0


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

  def drain(now, force=False):
    while pending and (force or now - pending[0] > SETTLE_NS):
      t = pending.popleft()
      regime = regime_of(bufs, t)
      if regime == "acc_engaged_clean":
        acc.n_ticks += 1
        for lag_ms in LAGS_MS:
          fit_at_lag(bufs, "ess_cruise_rpm", "trans_engine", t, lag_ms, acc.fit_rpm_vs_trans)
          fit_at_lag(bufs, "ess_cruise_rpm", "engine_rpm_140", t, lag_ms, acc.fit_rpm_vs_erpm)

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
          if addr == TICK_ADDR and src == CAM_BUS:
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
    slope = cov / varx if varx > 0 else 0.0
    intercept = (sy - slope * sx) / n
    resid_var = max(0.0, (vary - (cov * cov / varx if varx > 0 else 0.0)) / n)
    rec = {"n": n, "r2": round(r2, 6), "slope": round(slope, 6),
           "intercept": round(intercept, 3), "resid_rms": round(math.sqrt(resid_var), 4)}
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
      print(f"... {idx+1}/{len(route_ids)} routes, {acc.n_ticks} acc-clean ticks", file=sys.stderr)

  out = {
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "n_acc_engaged_clean_ticks": acc.n_ticks,
    "lags_ms_tested": LAGS_MS,
    "cruise_rpm_vs_trans_engine": fit_summary(acc.fit_rpm_vs_trans),
    "cruise_rpm_vs_engine_rpm_140": fit_summary(acc.fit_rpm_vs_erpm),
  }
  OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE. {acc.routes_ok} ok, {acc.routes_err} err. Written to {OUT_FILE}", file=sys.stderr)
  print(json.dumps({k: v for k, v in out.items()
                     if k not in ("cruise_rpm_vs_trans_engine", "cruise_rpm_vs_engine_rpm_140")},
                    indent=2, default=str))
  print("cruise_rpm_vs_trans_engine.best:", json.dumps(out["cruise_rpm_vs_trans_engine"]["best"], indent=2))
  print("cruise_rpm_vs_engine_rpm_140.best:", json.dumps(out["cruise_rpm_vs_engine_rpm_140"]["best"], indent=2))


if __name__ == "__main__":
  main()
