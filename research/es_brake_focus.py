#!/usr/bin/env python3
"""
Round 3, Step 1: wide-lag affine-correlation sweep for esb_brake_pressure
(ES_Brake/0x160, the H2 field) vs its own report-field candidates, mirroring
es_echo_focus.py (H1) / es_rpm_focus.py (H3) -- completing the symmetric
treatment across all three ES fields.

VARIANCE-FLOOR GUARD (a real bug was found and fixed earlier this campaign):
esb_brake_pressure is pinned at/near 0 for the vast majority of normal
driving. A naive correlation over that dominant near-constant population
produces spurious high "exact match" fits with r2=0 underneath (documented in
research/es_longitudinal_command_results.md's K1 bug section). Guarded here
two ways: (1) only ticks where esb_brake_pressure(t) > 0 are included in the
correlation accumulators at all -- this is a real behavioral restriction, not
just a reporting change, since the whole point is to characterize the field's
dynamics while it is actually doing something; (2) every fit reports the ES
field's own stdev (es_std) alongside R^2, so a near-zero-variance false
positive is visible rather than hidden.

Comparators: brake2_right, brake2_left (wheel/caliper pressure -- T6 found
these are the FASTER pair, leading mc_brake_right/left by ~300-400ms), plus
mc_brake_right, mc_brake_left (master cylinder) and aego, for completeness.

Nothing here transmits. Read-only, same archive, same container.
"""
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
OUT_FILE = Path("/work/es_brake_focus_results.json")

MS = 1_000_000
S = 1_000_000_000

HORIZON_NS = 20 * S
SETTLE_NS = 3 * S
MAX_STALE_NS = 200 * MS

LAGS_MS = list(range(-1500, 1525, 50))
ACTIVE_MIN = 1.0  # esb_brake_pressure(t) must exceed this to be included at all

ADDR_ES_DISTANCE = 0x161
ADDR_ES_BRAKE = 0x160
ADDR_CRUISECONTROL = 0x144
ADDR_BRAKE_PRESSURE = 0x150   # master cylinder, mc_brake_right/left
ADDR_BRAKE_2 = 0xD2           # wheel/caliper, brake2_right/left
ADDR_BRAKE_PEDAL = 0xD1
MAIN_BUS = 0
CAM_BUS = 2


def u(dat, start, length):
  if len(dat) < 8:
    dat = bytes(dat) + b"\x00" * (8 - len(dat))
  raw = int.from_bytes(dat[:8], "little")
  return (raw >> start) & ((1 << length) - 1)


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


DECODERS = {
  (ADDR_ES_BRAKE, CAM_BUS): dec_es_brake,
  (ADDR_CRUISECONTROL, MAIN_BUS): dec_cruisecontrol,
  (ADDR_BRAKE_PRESSURE, MAIN_BUS): dec_brake_pressure,
  (ADDR_BRAKE_2, MAIN_BUS): dec_brake_2,
  (ADDR_BRAKE_PEDAL, MAIN_BUS): dec_brake_pedal,
}
CENSUS_ADDRS = set(a for a, _ in DECODERS) | {ADDR_ES_DISTANCE}

REPORT_FIELDS = ["brake2_right", "brake2_left", "mc_brake_right", "mc_brake_left", "aego"]


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


import bisect


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
  return "acc_engaged" if act else "other"


class Acc:
  def __init__(self):
    self.routes_ok = 0
    self.routes_err = 0
    self.n_active_ticks = 0
    # (report_field, lag_ms) -> [n, sx, sy, sxy, sxx, syy]
    self.fits = {rf: defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0]) for rf in REPORT_FIELDS}


def fit_at_lag(bufs, x, rf_name, t, lag_ms, acc_dict):
  y, _ = bufs.at(rf_name, t + lag_ms * MS)
  if y is None:
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
      if regime != "acc_engaged":
        continue
      x, _ = bufs.at("esb_brake_pressure", t)
      if x is None or x <= ACTIVE_MIN:
        continue
      acc.n_active_ticks += 1
      for rf in REPORT_FIELDS:
        for lag_ms in LAGS_MS:
          fit_at_lag(bufs, x, rf, t, lag_ms, acc.fits[rf])

  for _seg_idx, seg_dir in segments:
    for ev in iter_events(log_schema, seg_dir):
      try:
        which = ev.which()
        t = ev.logMonoTime
      except Exception:
        continue
      if which == "carState":
        try:
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
          if key in DECODERS:
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
    es_std = math.sqrt(max(0.0, varx) / n)
    rec = {"n": n, "r2": round(r2, 6), "slope": round(slope, 6),
           "intercept": round(intercept, 3), "resid_rms": round(math.sqrt(resid_var), 4),
           "es_std": round(es_std, 4)}
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
      print(f"... {idx+1}/{len(route_ids)} routes, {acc.n_active_ticks} active brake ticks",
            file=sys.stderr)

  summaries = {rf: fit_summary(acc.fits[rf]) for rf in REPORT_FIELDS}
  out = {
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "n_active_ticks": acc.n_active_ticks,
    "active_min_threshold": ACTIVE_MIN,
    "lags_ms_tested": LAGS_MS,
    "fits": summaries,
  }
  OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE. {acc.routes_ok} ok, {acc.routes_err} err. -> {OUT_FILE}", file=sys.stderr)
  for rf in REPORT_FIELDS:
    print(f"{rf}.best:", json.dumps(summaries[rf]["best"], indent=2))


if __name__ == "__main__":
  main()
