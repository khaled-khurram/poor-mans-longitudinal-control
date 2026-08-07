#!/usr/bin/env python3
"""
Passive archive validation: is ES_Distance.Cruise_Throttle (0x161, bits 0|12) on
Subaru PREGLOBAL a *command* that EyeSight sends to the powertrain, or a *report*
that EyeSight echoes back from it?

Companion doc (hypothesis, pre-registered CONFIRM/KILL criteria, honest gaps):
  research/es_longitudinal_command_hypothesis.md

Nothing here transmits. This is read-only analysis of already-logged rlogs.
Run it before anything is ever written to Cruise_Throttle on a real car.

--------------------------------------------------------------------------------
WHAT IT TESTS  (each test's pass/fail thresholds are pinned in PREREG_* below,
                deliberately fixed before any output was ever looked at)

  T0  census        - do the messages/buses even exist in the archive, and is
                      there enough ACC-engaged data to test anything?
  T1  acc_off       - during manual driving with ACC OFF, EyeSight has no
                      longitudinal authority, so anything it emits then cannot
                      be a command being obeyed. Does Cruise_Throttle track the
                      engine in that regime (=> report), or sit pinned (=> idle
                      command channel)?
  T2  exact_copy    - is any ES_* field an exact / affine copy of a powertrain
                      report field at some lag? (the KILL test)
  T3  xcorr         - first-difference cross-correlation, ES(t) vs response(t+tau).
                      peak at tau > 0 => ES leads => command-like.
  T4  step_events   - isolated step changes in Cruise_Throttle -> time to first
                      response in Throttle_Body / Engine_RPM / aEgo, and the
                      converse (engine steps -> time to Cruise_Throttle response).
  T5  override      - driver presses the gas while ACC is engaged: an exogenous
                      input EyeSight did NOT ask for. Does Cruise_Throttle follow
                      the engine up (report) or not (command)? THE discriminator.
  T6  brake         - ES_Brake.Brake_Pressure onset vs master-cylinder pressure
                      (0x150), wheel brakes (0xD2), brake lights and aEgo; plus
                      what Cruise_Throttle does while EyeSight brakes (the global
                      THROTTLE_ENGINE_BRAKE = 808 prediction).
  T7  transfer      - measured accel / wheel torque as a function of
                      Cruise_Throttle, and decel as a function of Brake_Pressure.
  T8  joint         - joint distribution of (Cruise_Throttle, Cruise_RPM,
                      Brake_Pressure). If they are tightly coupled, writing
                      throttle ALONE produces a triple the ECM has never seen.
  T9  relay         - openpilot already rebuilds and re-sends 0x161 on the main
                      bus at 20Hz. How faithful is that copy, and how often does
                      its (verbatim-copied, not regenerated) COUNTER duplicate or
                      skip? Evidence for how much the receiving ECU tolerates.

--------------------------------------------------------------------------------
NOTE ON PATHS: RAW_DIR / SCHEMA_DIR below are placeholders - this project's real
local paths are scrubbed before publishing. Point them at your own route archive
and a matching cereal/log.capnp schema copy to actually run this.

Same runner as research/es_distance_correlation.py (a container that already has
pycapnp + zstandard and the archive mounted):
  docker exec <route-stats-container> python3 /work/es_longitudinal_command_correlation.py
(copy this file in first, e.g. docker cp)

STATUS: written but NEVER RUN - the environment it was authored in has no archive
and no device access. Treat every number it emits as unvalidated until someone
runs it and sanity-checks T0's census first.
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

# ------------------------------------------------------------------ config ---

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path("/work/es_longitudinal_command_results.json")

ROUTE_LIMIT = None      # set to e.g. 5 for a smoke run before the full pass
PROGRESS_EVERY = 25     # routes

MS = 1_000_000          # ns per ms
S = 1_000_000_000       # ns per s

HORIZON_NS = 14 * S     # how much history each signal buffer keeps
SETTLE_NS = 6 * S       # a tick is only scored once this much future exists
PRE_NS = 1 * S          # baseline window before an event
POST_NS = 2 * S         # response window after an event

MAX_STALE_NS = 200 * MS  # a held value older than this is treated as missing
MAX_EVENTS_PER_KIND = 4000
MAX_EVENTS_PER_ROUTE = 200

# lag grids, in ms. positive tau = ES leads the response by tau, i.e. we compare
# ES(t) against response(t + tau). Coarse grid for the many-pair copy test,
# fine grid for the few-pair cross-correlation.
COPY_LAGS_MS = [-200, -100, -50, -25, 0, 25, 50, 100, 200]
XCORR_LAGS_MS = list(range(-300, 325, 25))

# --------------------------------- PRE-REGISTERED FALSIFICATION CRITERIA -----
# Fixed here, in code, before any archive output existed. Do not tune these to
# make a result come out. If a threshold turns out to be wrong, say so in the
# writeup and re-register it explicitly - do not silently edit.

PREREG = {
  # T0
  "min_acc_engaged_ticks": 20_000,        # ~17 min of 20Hz ACC-engaged data
  "min_isolated_step_events": 100,
  "min_override_events": 30,
  "min_brake_events": 50,

  # T2 - "it's a report" kill test
  "report_exact_match_frac": 0.99,        # >=99% bit-exact at some lag => report
  "report_affine_r2": 0.999,              # or affine fit this good with
  "report_affine_resid_lsb": 1.0,         # residual under 1 LSB

  # T3/T4 - lead/lag
  "confirm_min_lead_ms": 40,              # ES must lead by more than one 20Hz
                                          # frame + bus latency to count
  "confirm_max_lead_ms": 600,             # beyond this it isn't actuator lag
  "confirm_lead_event_frac": 0.80,        # in >=80% of isolated step events
  "kill_lead_ms": 0,                      # ES lagging the engine => report

  # T5 - driver gas override while ACC engaged. The override gain is measured
  # RELATIVE to the ordinary ACC-engaged regression slope of Cruise_Throttle on
  # Throttle_Body, so "does it still move with the engine the way it normally
  # does" is the actual question being asked.
  "confirm_override_gain_ratio_max": 0.25,
  "confirm_override_same_sign_max_frac": 0.50,
  "kill_override_gain_ratio_min": 0.75,
  "kill_override_same_sign_min_frac": 0.80,

  # T1/T7 - does the global encoding transfer?
  "encoding_mode_tol_frac": 0.05,         # +/-5% around 1818 / 808 / 600
  "encoding_min_mode_frac": 0.10,         # the landmark must be a real mode
  "brake_slope_tol_frac": 0.50,           # measured m/s2-per-count within 2x of
                                          # global's -3.5/600 = -0.005833
}

GLOBAL_CONSTS = {  # verbatim from opendbc/car/subaru/values.py CarControllerParams
  "THROTTLE_MIN": 808,
  "THROTTLE_MAX": 3400,
  "THROTTLE_INACTIVE": 1818,
  "THROTTLE_ENGINE_BRAKE": 808,
  "BRAKE_MIN": 0,
  "BRAKE_MAX": 600,
  "RPM_MIN": 0,
  "RPM_MAX": 3600,
  "RPM_INACTIVE": 600,
  "BRAKE_MAX_DECEL_MS2": -3.5,
}

# ------------------------------------------------------------- CAN decoding --
# All bit positions below are read straight off
# opendbc/dbc/generator/subaru/_subaru_preglobal_2015.dbc (verified, not recalled).
# Every signal used here is Intel/little-endian (@1+), so one extractor covers all.

ADDR_ES_DISTANCE = 0x161   # 353, EyeSight -> car
ADDR_ES_BRAKE = 0x160      # 352, EyeSight -> car
ADDR_ES_STATUS = 0x162     # 354, EyeSight -> car
ADDR_ES_DASHSTATUS = 0x166  # 358, EyeSight -> car
ADDR_THROTTLE = 0x140      # 320, engine
ADDR_ENGINE = 0x141        # 321, engine
ADDR_CRUISECONTROL = 0x144  # 324, car
ADDR_TRANSMISSION = 0x148  # 328
ADDR_BRAKE_PRESSURE = 0x150  # 336, master cylinder
ADDR_BRAKE_PEDAL = 0xD1    # 209
ADDR_BRAKE_2 = 0xD2        # 210
ADDR_G_SENSOR = 0xD0       # 208

MAIN_BUS = 0
CAM_BUS = 2


def u(dat: bytes, start: int, length: int) -> int:
  """Unsigned little-endian (Intel, @1+) signal extraction, DBC start-bit convention."""
  if len(dat) < 8:
    dat = bytes(dat) + b"\x00" * (8 - len(dat))
  raw = int.from_bytes(dat[:8], "little")
  return (raw >> start) & ((1 << length) - 1)


def to_signed(v: int, bits: int) -> int:
  return v - (1 << bits) if v & (1 << (bits - 1)) else v


def dec_es_distance(d):
  return {
    "es_cruise_throttle": u(d, 0, 12),
    "es_car_follow": u(d, 16, 1),
    "es_brake_active": u(d, 20, 1),
    "es_distance_swap": u(d, 21, 1),
    "es_standstill": u(d, 22, 1),
    "es_close_distance": u(d, 24, 8) * 0.019607,
    "es_standstill_2": u(d, 41, 1),
    "es_cruise_fault": u(d, 42, 1),
    "es_counter": u(d, 44, 3),
    "es_cruise_button": u(d, 48, 3),
    "es_checksum": u(d, 56, 8),
  }


def dec_es_brake(d):
  return {
    "esb_brake_pressure": u(d, 0, 16),
    "esb_brake_lights": u(d, 20, 1),
    "esb_cruise_fault": u(d, 21, 1),
    "esb_brake_active": u(d, 22, 1),
    "esb_cruise_activated": u(d, 23, 1),
    "esb_counter": u(d, 48, 3),
  }


def dec_es_status(d):
  return {
    "ess_brake": u(d, 8, 1),
    "ess_cruise_activated": u(d, 9, 1),
    "ess_cruise_rpm": u(d, 16, 16),
    "ess_counter": u(d, 48, 3),
  }


def dec_es_dashstatus(d):
  return {
    "dash_cruise_on": u(d, 16, 1),
    "dash_cruise_activated": u(d, 17, 1),
    "dash_cruise_distance": u(d, 21, 3),
    "dash_set_speed": u(d, 24, 8),
    "dash_cruise_fault": u(d, 32, 1),
    "dash_car_follow": u(d, 46, 1),
  }


def dec_throttle(d):
  return {
    "throttle_pedal": u(d, 0, 8),            # raw counts; DBC scale 0.392157
    "not_full_throttle": u(d, 14, 1),
    "engine_rpm_140": u(d, 16, 14),
    "off_throttle": u(d, 30, 1),
    "throttle_cruise": u(d, 32, 8),
    "throttle_combo": u(d, 40, 8),
    "throttle_body": u(d, 48, 8),
    "off_throttle_2": u(d, 56, 1),
  }


def dec_engine(d):
  return {
    "engine_torque": u(d, 0, 15),
    "wheel_torque": u(d, 16, 12),
    "engine_rpm_141": u(d, 32, 12),
  }


def dec_cruisecontrol(d):
  return {
    "cc_onoff_btn": u(d, 2, 1),
    "cc_set_btn": u(d, 3, 1),
    "cc_res_btn": u(d, 4, 1),
    "cc_cruise_on": u(d, 48, 1),
    "cc_cruise_activated": u(d, 49, 1),
    "cc_brake_pedal_on": u(d, 51, 1),
  }


def dec_transmission(d):
  return {
    "trans_engine": u(d, 16, 15),
    "trans_gear": u(d, 48, 4),
  }


def dec_brake_pressure(d):
  return {
    "mc_brake_right": u(d, 0, 8),
    "mc_brake_left": u(d, 8, 8),
  }


def dec_brake_pedal(d):
  return {
    "pedal_brake": u(d, 16, 8),
    "speed_d1": u(d, 0, 16) * 0.05625,       # KPH
  }


def dec_brake_2(d):
  return {
    "brake2_light": u(d, 35, 1),
    "brake2_right": u(d, 48, 8),
    "brake2_left": u(d, 56, 8),
  }


def dec_g_sensor(d):
  # 48|16@1- (-0.00035, 0). Sign convention and physical units are NOT verified
  # against anything - recorded raw + scaled, used only as a cross-check on aEgo.
  return {"g_long": to_signed(u(d, 48, 16), 16) * -0.00035}


# (addr, expected src) -> (label, decoder)
DECODERS = {
  (ADDR_ES_DISTANCE, CAM_BUS): ("ES_Distance@cam", dec_es_distance),
  (ADDR_ES_BRAKE, CAM_BUS): ("ES_Brake@cam", dec_es_brake),
  (ADDR_ES_STATUS, CAM_BUS): ("ES_Status@cam", dec_es_status),
  (ADDR_ES_DASHSTATUS, CAM_BUS): ("ES_DashStatus@cam", dec_es_dashstatus),
  (ADDR_THROTTLE, MAIN_BUS): ("Throttle@main", dec_throttle),
  (ADDR_ENGINE, MAIN_BUS): ("Engine@main", dec_engine),
  (ADDR_CRUISECONTROL, MAIN_BUS): ("CruiseControl@main", dec_cruisecontrol),
  (ADDR_TRANSMISSION, MAIN_BUS): ("Transmission@main", dec_transmission),
  (ADDR_BRAKE_PRESSURE, MAIN_BUS): ("Brake_Pressure@main", dec_brake_pressure),
  (ADDR_BRAKE_PEDAL, MAIN_BUS): ("Brake_Pedal@main", dec_brake_pedal),
  (ADDR_BRAKE_2, MAIN_BUS): ("Brake_2@main", dec_brake_2),
  (ADDR_G_SENSOR, MAIN_BUS): ("G_Sensor@main", dec_g_sensor),
}

CENSUS_ADDRS = {
  ADDR_ES_DISTANCE, ADDR_ES_BRAKE, ADDR_ES_STATUS, ADDR_ES_DASHSTATUS,
  ADDR_THROTTLE, ADDR_ENGINE, ADDR_CRUISECONTROL, ADDR_TRANSMISSION,
  ADDR_BRAKE_PRESSURE, ADDR_BRAKE_PEDAL, ADDR_BRAKE_2, ADDR_G_SENSOR,
}

# --------------------------------------------------------- pairs under test --

ES_FIELDS = ["es_cruise_throttle", "ess_cruise_rpm", "esb_brake_pressure"]

REPORT_FIELDS = [
  "throttle_pedal", "throttle_cruise", "throttle_combo", "throttle_body",
  "engine_rpm_140", "engine_rpm_141", "engine_torque", "wheel_torque",
  "trans_engine", "mc_brake_right", "mc_brake_left", "brake2_right",
  "brake2_left", "pedal_brake", "vego", "aego",
]

RESPONSE_FIELDS = ["throttle_body", "engine_rpm_140", "wheel_torque", "aego", "vego"]

# regimes, evaluated per tick
REGIMES = ["acc_engaged_clean", "acc_engaged_gas", "acc_engaged_brake",
           "acc_on_not_engaged", "acc_off", "unknown"]

HIST_FIELDS = ["es_cruise_throttle", "ess_cruise_rpm", "esb_brake_pressure",
               "throttle_body", "throttle_cruise", "engine_rpm_140"]


# ------------------------------------------------------------- archive I/O ---

def load_schema():
  return capnp.load(str(SCHEMA_FILE), imports=[str(SCHEMA_DIR)])


def read_rlog_bytes(segment_dir: Path):
  zst_path = segment_dir / "rlog.zst"
  plain_path = segment_dir / "rlog"
  if zst_path.is_file():
    try:
      with open(zst_path, "rb") as f:
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(f) as reader:
          return reader.read()
    except Exception as e:
      print(f"  decompress fail {zst_path}: {e}", file=sys.stderr)
      return None
  elif plain_path.is_file():
    try:
      return plain_path.read_bytes()
    except Exception as e:
      print(f"  read fail {plain_path}: {e}", file=sys.stderr)
      return None
  return None


def iter_events(log_schema, segment_dir: Path):
  data = read_rlog_bytes(segment_dir)
  if not data:
    return
  try:
    for event in log_schema.Event.read_multiple_bytes(data):
      yield event
  except capnp.KjException as e:
    print(f"  truncated {segment_dir}: {e}", file=sys.stderr)
    return
  except Exception as e:
    print(f"  unexpected {segment_dir}: {e}", file=sys.stderr)
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


# ---------------------------------------------------------------- plumbing ---

class Buffers:
  """Time-ordered rolling buffers, one (times, values) list pair per signal.

  Lookups are bisect-based, not linear scans: every tick is scored SETTLE_NS in
  the past, so a scan-from-the-tail would walk ~6s of 100Hz samples per query and
  the full-archive pass would never finish.
  """

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
    """Zero-order hold: freshest sample at or before t. (value, staleness) or (None, None)."""
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


class Acc:
  """Streaming accumulators; nothing per-sample is retained."""

  def __init__(self):
    self.census = defaultdict(int)                     # "0x161/src2" -> n
    self.decoded = defaultdict(int)
    self.regime_ticks = defaultdict(int)
    self.hist = defaultdict(lambda: defaultdict(int))  # (regime, field) -> {val: n}
    self.pairs = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0])
    # key (regime, es_field, report_field, lag_ms) ->
    #   [n, sx, sy, sxy, sxx, syy, n_exact, n_within1]
    self.xcorr = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    # key (es_field, response_field, lag_ms) -> [n, sxy, sxx, syy] on first diffs
    self.transfer = defaultdict(lambda: [0, 0.0, 0.0])  # (field, bin) -> [n, sum_a, ...]
    self.transfer_tq = defaultdict(lambda: [0, 0.0])
    self.brake_transfer = defaultdict(lambda: [0, 0.0])
    self.joint = defaultdict(int)                      # coarse (ct_bin, rpm_bin, bp_bin)
    self.step_events = []
    self.rev_step_events = []
    self.override_events = []
    self.brake_events = []
    self.relay = defaultdict(int)
    self.relay_delays = []
    self.routes_ok = 0
    self.routes_err = 0
    self.segments = 0

  def add_event(self, bucket, ev):
    if len(bucket) < MAX_EVENTS_PER_KIND:
      bucket.append(ev)


# ------------------------------------------------------------- per-route ----

def regime_of(bufs, t):
  """Classify the driving regime at time t from raw CAN only (no carState),
  so the result does not depend on openpilot's own engagement state."""
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


def onset_latency(bufs, name, t0, min_abs_change, k_sigma=3.0):
  """Time (ns) from t0 to the first sample that departs from its own pre-t0
  baseline by more than max(k*sigma, min_abs_change). None if it never does."""
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


def process_tick(acc, bufs, t, prev_tick):
  """Score one 20Hz ES_Distance tick, once enough future data exists."""
  regime = regime_of(bufs, t)
  acc.regime_ticks[regime] += 1

  cur = {}
  for f in set(ES_FIELDS + REPORT_FIELDS + HIST_FIELDS + RESPONSE_FIELDS):
    v, _ = bufs.at(f, t)
    cur[f] = v

  # --- T1/T0: per-regime histograms of the three candidate command fields ---
  for f in HIST_FIELDS:
    v = cur.get(f)
    if v is not None:
      acc.hist[(regime, f)][int(v)] += 1

  # --- T2: exact-copy / affine-fit accumulators over the coarse lag grid ---
  # cache each (report field, lag) lookup once instead of once per ES field
  lagged = {}
  for rf in REPORT_FIELDS:
    for lag_ms in COPY_LAGS_MS:
      lagged[(rf, lag_ms)] = bufs.at(rf, t + lag_ms * MS)[0]

  for esf in ES_FIELDS:
    x = cur.get(esf)
    if x is None:
      continue
    for rf in REPORT_FIELDS:
      for lag_ms in COPY_LAGS_MS:
        # positive lag = ES leads: compare ES(t) to report(t + lag)
        y = lagged[(rf, lag_ms)]
        if y is None:
          continue
        a = acc.pairs[(regime, esf, rf, lag_ms)]
        a[0] += 1
        a[1] += x
        a[2] += y
        a[3] += x * y
        a[4] += x * x
        a[5] += y * y
        if abs(x - y) < 1e-9:
          a[6] += 1
        if abs(x - y) <= 1.0:
          a[7] += 1

  # --- T3: first-difference cross-correlation (ACC-engaged regimes only) ---
  if prev_tick is not None and regime.startswith("acc_engaged"):
    tp = prev_tick
    dresp = {}
    for rf in RESPONSE_FIELDS:
      for lag_ms in XCORR_LAGS_MS:
        y1, _ = bufs.at(rf, t + lag_ms * MS)
        y0, _ = bufs.at(rf, tp + lag_ms * MS)
        dresp[(rf, lag_ms)] = None if (y0 is None or y1 is None) else (y1 - y0)
    for esf in ES_FIELDS:
      x0, _ = bufs.at(esf, tp)
      x1 = cur.get(esf)
      if x0 is None or x1 is None:
        continue
      dx = x1 - x0
      for rf in RESPONSE_FIELDS:
        for lag_ms in XCORR_LAGS_MS:
          dy = dresp[(rf, lag_ms)]
          if dy is None:
            continue
          a = acc.xcorr[(esf, rf, lag_ms)]
          a[0] += 1
          a[1] += dx * dy
          a[2] += dx * dx
          a[3] += dy * dy

  # --- T7: transfer curves, steady-state-ish samples only ---
  if regime == "acc_engaged_clean":
    ct = cur.get("es_cruise_throttle")
    ae = cur.get("aego")
    wt = cur.get("wheel_torque")
    bp = cur.get("esb_brake_pressure")
    ve = cur.get("vego")
    if ct is not None and ve is not None and ve > 5.0:
      b = int(ct // 50) * 50
      if ae is not None:
        a = acc.transfer[b]
        a[0] += 1
        a[1] += ae
      if wt is not None:
        a = acc.transfer_tq[b]
        a[0] += 1
        a[1] += wt
    if bp is not None and ae is not None and ve is not None and ve > 5.0:
      b = int(bp // 25) * 25
      a = acc.brake_transfer[b]
      a[0] += 1
      a[1] += ae

    # --- T8: joint distribution of the three would-be command fields ---
    rpm = cur.get("ess_cruise_rpm")
    if ct is not None and rpm is not None and bp is not None:
      acc.joint[(int(ct // 100) * 100, int(rpm // 100) * 100, int(bp // 50) * 50)] += 1


def detect_events(acc, bufs, t, route_id, per_route):
  """Event detectors that need both a pre- and post-window around t."""
  regime = regime_of(bufs, t)

  # ---- T4a: isolated Cruise_Throttle steps -> engine/vehicle response ----
  ct_now, _ = bufs.at("es_cruise_throttle", t)
  ct_prev, _ = bufs.at("es_cruise_throttle", t - 150 * MS)
  if ct_now is not None and ct_prev is not None and regime == "acc_engaged_clean":
    step = ct_now - ct_prev
    if abs(step) >= 100:
      # isolation: no other comparable step within +/-1.5s
      w = bufs.window("es_cruise_throttle", t - 1500 * MS, t + 1500 * MS)
      others = 0
      for i in range(3, len(w)):
        if abs(w[i][1] - w[i - 3][1]) >= 100 and abs(w[i][0] - t) > 200 * MS:
          others += 1
      if others == 0 and per_route["step"] < MAX_EVENTS_PER_ROUTE:
        per_route["step"] += 1
        ev = {
          "route_id": route_id, "t": t, "step": step,
          "ct_before": ct_prev, "ct_after": ct_now,
          "vego": bufs.at("vego", t)[0],
        }
        for rf, minchg in (("throttle_body", 2.0), ("engine_rpm_140", 30.0),
                           ("wheel_torque", 20.0), ("aego", 0.15)):
          lat = onset_latency(bufs, rf, t, minchg)
          ev[f"lat_{rf}_ms"] = None if lat is None else lat / MS
        acc.add_event(acc.step_events, ev)

  # ---- T4b: the converse - isolated engine steps -> Cruise_Throttle response --
  tb_now, _ = bufs.at("throttle_body", t)
  tb_prev, _ = bufs.at("throttle_body", t - 150 * MS)
  if tb_now is not None and tb_prev is not None and regime == "acc_engaged_clean":
    step = tb_now - tb_prev
    if abs(step) >= 8:
      w = bufs.window("throttle_body", t - 1500 * MS, t + 1500 * MS)
      others = 0
      for i in range(15, len(w)):
        if abs(w[i][1] - w[i - 15][1]) >= 8 and abs(w[i][0] - t) > 200 * MS:
          others += 1
      if others == 0 and per_route["rev"] < MAX_EVENTS_PER_ROUTE:
        per_route["rev"] += 1
        lat = onset_latency(bufs, "es_cruise_throttle", t, 40.0)
        acc.add_event(acc.rev_step_events, {
          "route_id": route_id, "t": t, "step": step,
          "lat_es_cruise_throttle_ms": None if lat is None else lat / MS,
          "vego": bufs.at("vego", t)[0],
        })

  # ---- T5: driver gas override while ACC engaged (the discriminator) ----
  gas_now, _ = bufs.at("throttle_pedal", t)
  gas_prev, _ = bufs.at("throttle_pedal", t - 200 * MS)
  act, _ = bufs.at("cc_cruise_activated", t)
  if (gas_now and not gas_prev and act and per_route["ovr"] < MAX_EVENTS_PER_ROUTE):
    sustained = bufs.window("throttle_pedal", t, t + 500 * MS)
    if sustained and all(v > 0 for _, v in sustained):
      def delta(name, a, b):
        va, _ = bufs.at(name, t + a)
        vb, _ = bufs.at(name, t + b)
        if va is None or vb is None:
          return None
        return vb - va
      still_on, _ = bufs.at("cc_cruise_activated", t + 1500 * MS)
      per_route["ovr"] += 1
      acc.add_event(acc.override_events, {
        "route_id": route_id, "t": t,
        "d_es_cruise_throttle": delta("es_cruise_throttle", -100 * MS, 1500 * MS),
        "d_throttle_body": delta("throttle_body", -100 * MS, 1500 * MS),
        "d_engine_rpm": delta("engine_rpm_140", -100 * MS, 1500 * MS),
        "d_throttle_pedal": delta("throttle_pedal", -100 * MS, 1500 * MS),
        "d_ess_cruise_rpm": delta("ess_cruise_rpm", -100 * MS, 1500 * MS),
        "d_vego": delta("vego", -100 * MS, 1500 * MS),
        "acc_still_engaged_after": still_on,
        "ct_before": bufs.at("es_cruise_throttle", t - 100 * MS)[0],
      })

  # ---- T6: EyeSight-commanded braking onsets (no driver brake) ----
  bp_now, _ = bufs.at("esb_brake_pressure", t)
  bp_prev, _ = bufs.at("esb_brake_pressure", t - 150 * MS)
  pb_win = bufs.window("pedal_brake", t - 500 * MS, t + 1500 * MS)
  driver_braked = any(v > 0 for _, v in pb_win)
  if (bp_now is not None and bp_prev is not None and act
      and bp_prev == 0 and bp_now > 20 and not driver_braked
      and per_route["brk"] < MAX_EVENTS_PER_ROUTE):
    per_route["brk"] += 1
    ev = {"route_id": route_id, "t": t, "bp_at_onset": bp_now,
          "vego": bufs.at("vego", t)[0]}
    for rf, minchg in (("mc_brake_right", 2.0), ("mc_brake_left", 2.0),
                       ("brake2_right", 2.0), ("brake2_left", 2.0),
                       ("aego", 0.2), ("brake2_light", 0.5),
                       ("es_cruise_throttle", 40.0)):
      lat = onset_latency(bufs, rf, t, minchg)
      ev[f"lat_{rf}_ms"] = None if lat is None else lat / MS
    ct_during = [v for _, v in bufs.window("es_cruise_throttle", t + 200 * MS, t + 1500 * MS)]
    ev["ct_during_brake_min"] = min(ct_during) if ct_during else None
    ev["ct_during_brake_median"] = statistics.median(ct_during) if ct_during else None
    bp_peak = [v for _, v in bufs.window("esb_brake_pressure", t, t + 2 * S)]
    ev["bp_peak"] = max(bp_peak) if bp_peak else None
    ae = [v for _, v in bufs.window("aego", t, t + 2 * S)]
    ev["aego_min"] = min(ae) if ae else None
    acc.add_event(acc.brake_events, ev)


def process_route(log_schema, acc, route_id, segments):
  bufs = Buffers(HORIZON_NS)
  pending = deque()          # ES_Distance ticks awaiting scoring: (t, prev_tick_t)
  last_es_tick_t = None      # previous ES tick *in time order*, not scoring order
  per_route = {"step": 0, "rev": 0, "ovr": 0, "brk": 0}

  # T9 relay-fidelity state
  last_cam_es = None         # (t, dict)
  last_op_counter = None

  def drain(now, force=False):
    while pending and (force or now - pending[0][0] > SETTLE_NS):
      t, ptick = pending.popleft()
      try:
        process_tick(acc, bufs, t, ptick)
        detect_events(acc, bufs, t, route_id, per_route)
      except Exception as e:
        print(f"  tick error {route_id}@{t}: {e}", file=sys.stderr)

  for _seg_idx, seg_dir in segments:
    acc.segments += 1
    for ev in iter_events(log_schema, seg_dir):
      try:
        which = ev.which()
        t = ev.logMonoTime
      except Exception:
        continue

      if which == "carState":
        try:
          bufs.push("vego", t, float(ev.carState.vEgo))
          bufs.push("aego", t, float(ev.carState.aEgo))
        except Exception:
          pass
        continue

      if which not in ("can", "sendcan"):
        continue

      try:
        frames = ev.can if which == "can" else ev.sendcan
      except Exception:
        continue

      for frame in frames:
        try:
          addr = frame.address
          if addr not in CENSUS_ADDRS:
            continue
          src = frame.src
          dat = bytes(frame.dat)
          acc.census[f"{which}/0x{addr:03x}/src{src}"] += 1

          # T9: openpilot's own rebuilt 0x161 on the main bus
          if addr == ADDR_ES_DISTANCE and src == MAIN_BUS:
            d = dec_es_distance(dat)
            acc.relay["op_es_distance_frames"] += 1
            acc.relay[f"op_stream_{which}"] += 1
            if last_op_counter is not None:
              step = (d["es_counter"] - last_op_counter) % 8
              acc.relay[f"op_counter_step_{step}"] += 1
            last_op_counter = d["es_counter"]
            if last_cam_es is not None:
              ct_cam = last_cam_es[1]["es_cruise_throttle"]
              if d["es_cruise_throttle"] == ct_cam:
                acc.relay["op_cruise_throttle_matches_cam"] += 1
              else:
                acc.relay["op_cruise_throttle_differs_from_cam"] += 1
              if d["es_cruise_button"] != last_cam_es[1]["es_cruise_button"]:
                acc.relay["op_cruise_button_differs_from_cam"] += 1
              if len(acc.relay_delays) < MAX_EVENTS_PER_KIND:
                acc.relay_delays.append((t - last_cam_es[0]) / MS)
            continue

          key = (addr, src)
          if key not in DECODERS:
            continue
          label, decoder = DECODERS[key]
          acc.decoded[label] += 1
          vals = decoder(dat)
          for name, v in vals.items():
            bufs.push(name, t, float(v))

          if addr == ADDR_ES_DISTANCE and src == CAM_BUS:
            last_cam_es = (t, vals)
            pending.append((t, last_es_tick_t))
            last_es_tick_t = t

        except Exception as e:
          print(f"  frame error {seg_dir}: {e}", file=sys.stderr)
          continue

      bufs.trim(t)
      drain(t)

  drain(0, force=True)


# ---------------------------------------------------------------- summary ----

def pct(x, n):
  return None if not n else round(100.0 * x / n, 3)


def summarize_pairs(acc):
  """For each (regime, es_field, report_field), the best affine fit - split by the
  SIGN of the lag, which is the whole ballgame.

  A tight match on its own does NOT mean the ES field is a report. If the ECU
  obeys or echoes an ES command, the ECU's own report becomes a near-copy of that
  command a few tens of ms LATER. Preglobal first-hand accounts describe exactly
  that: EyeSight cross-checks its commanded Cruise_Throttle against the ECU's
  echo in Throttle(0x140).Throttle_Cruise (see the archaeology writeup). So:

    best fit at lag <= 0  (ES(t) matches what the report already was)  => ECHO
    best fit at lag  > 0  (ES(t) matches what the report becomes later) => COMMAND

  K1 only fires when the match is best in the ECHO direction. Ignoring the sign
  here would turn the strongest possible confirmation into a false KILL.
  """
  def fit(a):
    n, sx, sy, sxy, sxx, syy, nex, nw1 = a
    if n < 500:
      return None
    varx = sxx - sx * sx / n
    vary = syy - sy * sy / n
    cov = sxy - sx * sy / n
    r2 = 0.0 if varx <= 0 or vary <= 0 else (cov * cov) / (varx * vary)
    slope = cov / varx if varx > 0 else 0.0
    intercept = (sy - slope * sx) / n
    resid_ms = max(0.0, (vary - (cov * cov / varx if varx > 0 else 0.0)) / n)
    return {
      "n": n, "r2": round(r2, 6), "slope": round(slope, 6),
      "intercept": round(intercept, 3), "resid_rms": round(math.sqrt(resid_ms), 4),
      "exact_frac": pct(nex, n), "within1_frac": pct(nw1, n),
      "es_std": round(math.sqrt(max(0.0, varx) / n), 4),
    }

  # best fit per direction
  best = defaultdict(dict)   # (regime, esf, rf) -> {"echo": rec, "cmd": rec}
  for (regime, esf, rf, lag), a in acc.pairs.items():
    rec = fit(a)
    if rec is None:
      continue
    rec = dict(rec, lag_ms=lag)
    side = "echo" if lag <= 0 else "cmd"
    prev = best[(regime, esf, rf)].get(side)
    if prev is None or rec["r2"] > prev["r2"]:
      best[(regime, esf, rf)][side] = rec

  def meets(rec):
    # BUG FOUND POST-HOC (2026-08-07, real archive run): the exact_frac branch
    # is a false-positive magnet when the ES field itself is ~constant (e.g.
    # esb_brake_pressure pinned at 0 during acc_off). A pinned signal trivially
    # "exact-matches" any report field that also happens to sit near that same
    # constant, with r2 = 0 (no real relationship) and exact_frac = 100%. Seen
    # live: acc_off|esb_brake_pressure|throttle_cruise hit exact_frac=100%,
    # r2=0.0 -- a spurious K1 trigger, not evidence of an echo. Guard it by
    # requiring the ES field to actually vary. Does NOT affect es_cruise_throttle
    # anywhere in the real run (it has 300+ distinct values in every regime),
    # so this does not change the H1 verdict -- it only removes false H2/H3
    # "report" hits on near-constant fields. Not a PREREG threshold retune:
    # the 99%/0.999/1-LSB numbers are untouched, this only adds a variance
    # floor before they're allowed to apply.
    if rec is None:
      return False
    min_es_std = 5.0  # counts; well below any real command field's dynamic range
    if rec.get("es_std", 1e9) < min_es_std:
      return False
    return bool((rec["exact_frac"] or 0) / 100.0 >= PREREG["report_exact_match_frac"]
                or (rec["r2"] >= PREREG["report_affine_r2"]
                    and rec["resid_rms"] <= PREREG["report_affine_resid_lsb"]))

  out = {}
  for (regime, esf, rf), sides in best.items():
    echo, cmd = sides.get("echo"), sides.get("cmd")
    overall = max([r for r in (echo, cmd) if r], key=lambda r: r["r2"], default=None)
    if overall is None:
      continue
    rec = dict(overall)
    rec["best_echo_side"] = echo
    rec["best_cmd_side"] = cmd
    # K1: tight match AND that match is best in the echo (lag <= 0) direction
    rec["is_report_by_prereg"] = bool(
      meets(echo) and (cmd is None or echo["r2"] >= cmd["r2"]))
    # the mirror case: tight match that is best in the command direction, i.e.
    # the ECU reproducing an ES command. Strong CONFIRM evidence, not a kill.
    rec["is_ecu_echo_of_es_by_prereg"] = bool(
      meets(cmd) and (echo is None or cmd["r2"] > echo["r2"]))
    out[f"{regime}|{esf}|{rf}"] = rec
  return out


def summarize_xcorr(acc):
  out = {}
  peaks = {}
  for (esf, rf, lag), a in acc.xcorr.items():
    n, sxy, sxx, syy = a
    if n < 500 or sxx <= 0 or syy <= 0:
      continue
    r = sxy / math.sqrt(sxx * syy)
    out.setdefault(f"{esf}|{rf}", {})[str(lag)] = round(r, 5)
    k = f"{esf}|{rf}"
    if k not in peaks or abs(r) > abs(peaks[k][1]):
      peaks[k] = (lag, r, n)
  return {"curves": out,
          "peaks": {k: {"peak_lag_ms": v[0], "peak_r": round(v[1], 5), "n": v[2]}
                    for k, v in peaks.items()}}


def med(xs):
  xs = [x for x in xs if x is not None]
  return round(statistics.median(xs), 2) if xs else None


def summarize_events(acc):
  s = {}

  lat_keys = ["lat_throttle_body_ms", "lat_engine_rpm_140_ms",
              "lat_wheel_torque_ms", "lat_aego_ms"]
  s["t4a_cruise_throttle_steps"] = {
    "n": len(acc.step_events),
    "median_latency_ms": {k: med([e.get(k) for e in acc.step_events]) for k in lat_keys},
    "frac_response_after_step": {
      k: pct(sum(1 for e in acc.step_events
                 if e.get(k) is not None and e[k] >= PREREG["confirm_min_lead_ms"]),
             sum(1 for e in acc.step_events if e.get(k) is not None))
      for k in lat_keys},
  }
  rev = [e.get("lat_es_cruise_throttle_ms") for e in acc.rev_step_events]
  s["t4b_engine_steps"] = {
    "n": len(acc.rev_step_events),
    "median_es_latency_ms": med(rev),
    "frac_es_responded_after": pct(sum(1 for v in rev if v is not None and v > 0),
                                   sum(1 for v in rev if v is not None)),
  }

  ovr = acc.override_events
  usable = [e for e in ovr if e.get("d_es_cruise_throttle") is not None
            and e.get("d_throttle_body") not in (None, 0)]
  ratios = [abs(e["d_es_cruise_throttle"]) / abs(e["d_throttle_body"])
            for e in usable if abs(e["d_throttle_body"]) > 0]
  same_sign = sum(1 for e in usable
                  if e["d_es_cruise_throttle"] * e["d_throttle_body"] > 0)
  s["t5_gas_override"] = {
    "n": len(ovr),
    "n_usable": len(usable),
    "n_acc_still_engaged": sum(1 for e in ovr if e.get("acc_still_engaged_after")),
    "median_d_es_cruise_throttle": med([e.get("d_es_cruise_throttle") for e in ovr]),
    "median_d_throttle_body": med([e.get("d_throttle_body") for e in ovr]),
    "median_abs_gain_ratio": med(ratios),
    "frac_same_sign_as_engine": pct(same_sign, len(usable)),
  }

  brk = acc.brake_events
  bkeys = ["lat_mc_brake_right_ms", "lat_mc_brake_left_ms", "lat_brake2_right_ms",
           "lat_brake2_left_ms", "lat_aego_ms", "lat_brake2_light_ms",
           "lat_es_cruise_throttle_ms"]
  s["t6_eyesight_braking"] = {
    "n": len(brk),
    "median_latency_ms": {k: med([e.get(k) for e in brk]) for k in bkeys},
    "median_ct_during_brake": med([e.get("ct_during_brake_median") for e in brk]),
    "min_ct_during_brake": min([e["ct_during_brake_min"] for e in brk
                                if e.get("ct_during_brake_min") is not None], default=None),
    "median_bp_peak": med([e.get("bp_peak") for e in brk]),
    "median_aego_min": med([e.get("aego_min") for e in brk]),
  }
  return s


def summarize_hist(acc):
  out = {}
  for (regime, field), h in acc.hist.items():
    n = sum(h.values())
    if not n:
      continue
    top = sorted(h.items(), key=lambda kv: -kv[1])[:20]
    ks = sorted(h)
    out[f"{regime}|{field}"] = {
      "n": n, "min": ks[0], "max": ks[-1],
      "distinct_values": len(ks),
      "top20": [[k, v, pct(v, n)] for k, v in top],
      "frac_eq_808": pct(h.get(808, 0), n),
      "frac_eq_1818": pct(h.get(1818, 0), n),
      "frac_eq_600": pct(h.get(600, 0), n),
      "frac_eq_0": pct(h.get(0, 0), n),
      "frac_below_808": pct(sum(v for k, v in h.items() if k < 808), n),
      "frac_above_3400": pct(sum(v for k, v in h.items() if k > 3400), n),
    }
  return out


def verdicts(acc, pair_sum, xcorr_sum, ev_sum, hist_sum):
  """Apply the pre-registered criteria. Written so the answer is mechanical."""
  v = {}

  # T0 - is there enough data to test anything at all?
  n_acc = acc.regime_ticks.get("acc_engaged_clean", 0)
  v["T0_power"] = {
    "acc_engaged_clean_ticks": n_acc,
    "sufficient": n_acc >= PREREG["min_acc_engaged_ticks"],
    "step_events": len(acc.step_events),
    "override_events": len(acc.override_events),
    "brake_events": len(acc.brake_events),
    "note": "if any of these are near zero the corresponding test is INCONCLUSIVE, "
            "not a KILL. Report it as such.",
  }

  # T2 - the kill test (echo direction only, see summarize_pairs)
  reports = {k: r for k, r in pair_sum.items() if r["is_report_by_prereg"]}
  echoes = {k: r for k, r in pair_sum.items() if r["is_ecu_echo_of_es_by_prereg"]}
  v["T2_exact_copy"] = {
    "pairs_meeting_report_criteria_ECHO_direction": sorted(reports),
    "pairs_where_ECU_reproduces_the_ES_field_COMMAND_direction": sorted(echoes),
    "verdict": "KILL (field is a powertrain report)" if any(
      k.split("|")[1] == "es_cruise_throttle" for k in reports) else
      "no echo-direction copy source found for es_cruise_throttle",
  }

  # T2b - the documented ECU cross-check. First-hand preglobal accounts say
  # EyeSight faults if it does not "hear back the same thing from 0x140" after
  # commanding Cruise_Throttle. If that loop is real it should be visible here as
  # Throttle(0x140).Throttle_Cruise reproducing ES_Distance.Cruise_Throttle at a
  # POSITIVE lag. Finding it is simultaneously the strongest CONFIRM available
  # from archive data AND the identification of the exact mechanism that makes a
  # naive write fault EyeSight.
  tc = pair_sum.get("acc_engaged_clean|es_cruise_throttle|throttle_cruise")
  if tc is None:
    v["T2b_ecu_crosscheck"] = {"verdict": "INCONCLUSIVE (no usable samples)"}
  else:
    cmd_side = tc.get("best_cmd_side")
    echo_side = tc.get("best_echo_side")
    v["T2b_ecu_crosscheck"] = {
      "cmd_direction_fit": cmd_side,
      "echo_direction_fit": echo_side,
      "verdict": ("ECU reproduces Cruise_Throttle at positive lag => command "
                  "confirmed AND EyeSight cross-check loop is real"
                  if tc["is_ecu_echo_of_es_by_prereg"] else
                  "no clean ECU reproduction of Cruise_Throttle found"),
      "implication_if_present": (
        "any write to Cruise_Throttle changes what the ECU echoes on 0x140, "
        "which EyeSight is reported to validate against its own command. A naive "
        "write would therefore be expected to fault EyeSight, matching the 2020 "
        "first-hand preglobal reports. Plan the live test around this, not past it."),
    }

  # T3 - lead/lag
  peaks = xcorr_sum.get("peaks", {})
  leads = {k: p for k, p in peaks.items()
           if k.startswith("es_cruise_throttle|") and p["peak_lag_ms"] >= PREREG["confirm_min_lead_ms"]}
  lags = {k: p for k, p in peaks.items()
          if k.startswith("es_cruise_throttle|") and p["peak_lag_ms"] <= PREREG["kill_lead_ms"]}
  v["T3_xcorr"] = {"leading": leads, "lagging": lags}

  # T4 - event-level lead
  t4 = ev_sum["t4a_cruise_throttle_steps"]
  fr = t4["frac_response_after_step"].get("lat_throttle_body_ms")
  v["T4_step_events"] = {
    "median_throttle_body_latency_ms": t4["median_latency_ms"].get("lat_throttle_body_ms"),
    "frac_after": fr,
    "verdict": ("CONFIRM-side" if fr is not None and fr / 100.0 >= PREREG["confirm_lead_event_frac"]
                else "not confirming"),
  }

  # T5 - the discriminator
  t5 = ev_sum["t5_gas_override"]
  base = pair_sum.get("acc_engaged_clean|es_cruise_throttle|throttle_body")
  # summarize_pairs regresses report-on-ES, so its slope is d(throttle_body)/
  # d(cruise_throttle). The override measurement is the other way round
  # (|dCT|/|dTB|), so invert before comparing - orientation matters here.
  base_slope = (1.0 / abs(base["slope"])
                if base and abs(base["slope"]) > 1e-9 else None)
  obs = t5["median_abs_gain_ratio"]
  rel = (obs / base_slope) if (obs is not None and base_slope) else None
  same = t5["frac_same_sign_as_engine"]
  if t5["n_usable"] < PREREG["min_override_events"]:
    t5_verdict = "INCONCLUSIVE (too few usable override events)"
  elif (rel is not None and rel <= PREREG["confirm_override_gain_ratio_max"]
        and same is not None and same / 100.0 <= PREREG["confirm_override_same_sign_max_frac"]):
    t5_verdict = "CONFIRM-side: Cruise_Throttle decouples from the engine under driver gas"
  elif (rel is not None and rel >= PREREG["kill_override_gain_ratio_min"]
        and same is not None and same / 100.0 >= PREREG["kill_override_same_sign_min_frac"]):
    t5_verdict = "KILL-side: Cruise_Throttle tracks driver-caused engine rise => echo"
  else:
    t5_verdict = "AMBIGUOUS (between the two pre-registered bands)"
  v["T5_gas_override"] = {
    "n_usable": t5["n_usable"],
    "n_acc_still_engaged": t5["n_acc_still_engaged"],
    "baseline_slope_ct_per_tb": base_slope,
    "override_slope_ct_per_tb": obs,
    "relative_gain": None if rel is None else round(rel, 4),
    "frac_same_sign_as_engine": same,
    "verdict": t5_verdict,
  }

  # T1 / encoding transfer
  h_on = hist_sum.get("acc_engaged_clean|es_cruise_throttle")
  h_off = hist_sum.get("acc_off|es_cruise_throttle")
  v["T1_encoding_and_gating"] = {
    "acc_engaged": h_on, "acc_off": h_off,
    "global_landmarks": {k: GLOBAL_CONSTS[k] for k in
                         ("THROTTLE_MIN", "THROTTLE_INACTIVE", "THROTTLE_MAX")},
    "note": "encoding transfers if the ACC-engaged distribution has a real mode "
            "near 1818, a floor near 808 and a ceiling <= ~3400. A different but "
            "still structured encoding does NOT kill the command hypothesis - it "
            "only kills 'same constants as global'.",
  }

  # T6 brake scaling
  bt = {b: (a[0], round(a[1] / a[0], 4)) for b, a in sorted(acc.brake_transfer.items()) if a[0] >= 30}
  v["T6_brake_scaling"] = {
    "binned_aego_by_brake_pressure": bt,
    "global_prediction_ms2_per_count": round(GLOBAL_CONSTS["BRAKE_MAX_DECEL_MS2"]
                                             / GLOBAL_CONSTS["BRAKE_MAX"], 6),
  }

  v["WHAT_THIS_CANNOT_SHOW"] = (
    "None of these tests can show that the ECM would obey a value openpilot "
    "writes. Every sample here is EyeSight's own value, perfectly consistent with "
    "everything else EyeSight emits at the same instant. A field that leads the "
    "engine and is not copied from it is necessary-but-not-sufficient evidence of "
    "a command: EyeSight publishing its internal demand while commanding the "
    "powertrain over some other path produces the identical signature. Only a "
    "live write separates the two."
  )
  return v


# -------------------------------------------------------------------- main ---

def main():
  log_schema = load_schema()
  groups = find_route_groups()
  route_ids = sorted(groups)
  if ROUTE_LIMIT:
    route_ids = route_ids[:ROUTE_LIMIT]
  print(f"found {len(groups)} routes ({len(route_ids)} selected), "
        f"{sum(len(groups[r]) for r in route_ids)} segments", file=sys.stderr)

  acc = Acc()
  for idx, route_id in enumerate(route_ids):
    try:
      process_route(log_schema, acc, route_id, groups[route_id])
      acc.routes_ok += 1
    except Exception as e:
      acc.routes_err += 1
      print(f"ROUTE ERROR {route_id}: {e}", file=sys.stderr)
    if (idx + 1) % PROGRESS_EVERY == 0:
      print(f"... {idx+1}/{len(route_ids)} routes, "
            f"{acc.regime_ticks.get('acc_engaged_clean', 0)} acc-engaged ticks, "
            f"{len(acc.step_events)} step / {len(acc.override_events)} override / "
            f"{len(acc.brake_events)} brake events", file=sys.stderr)

  pair_sum = summarize_pairs(acc)
  xcorr_sum = summarize_xcorr(acc)
  ev_sum = summarize_events(acc)
  hist_sum = summarize_hist(acc)

  out = {
    "config": {
      "copy_lags_ms": COPY_LAGS_MS, "xcorr_lags_ms": XCORR_LAGS_MS,
      "horizon_ns": HORIZON_NS, "settle_ns": SETTLE_NS,
      "max_stale_ns": MAX_STALE_NS, "route_limit": ROUTE_LIMIT,
    },
    "prereg": PREREG,
    "global_constants_for_reference": GLOBAL_CONSTS,
    "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
    "segments": acc.segments,
    "t0_census": dict(sorted(acc.census.items())),
    "t0_decoded": dict(sorted(acc.decoded.items())),
    "t0_regime_ticks": dict(acc.regime_ticks),
    "t1_t7_histograms": hist_sum,
    "t2_pair_fits": pair_sum,
    "t3_xcorr": xcorr_sum,
    "t4_t5_t6_events": ev_sum,
    "t7_transfer_cruise_throttle_to_aego": {
      str(b): {"n": a[0], "mean_aego": round(a[1] / a[0], 4)}
      for b, a in sorted(acc.transfer.items()) if a[0] >= 30},
    "t7_transfer_cruise_throttle_to_wheel_torque": {
      str(b): {"n": a[0], "mean_wheel_torque": round(a[1] / a[0], 2)}
      for b, a in sorted(acc.transfer_tq.items()) if a[0] >= 30},
    "t8_joint_top": [
      {"cruise_throttle_bin": k[0], "cruise_rpm_bin": k[1], "brake_pressure_bin": k[2], "n": n}
      for k, n in sorted(acc.joint.items(), key=lambda kv: -kv[1])[:200]],
    "t8_joint_distinct_combos": len(acc.joint),
    "t9_relay": dict(acc.relay),
    "t9_relay_delay_ms": {
      "n": len(acc.relay_delays),
      "median": med(acc.relay_delays),
      "p95": (round(sorted(acc.relay_delays)[int(0.95 * (len(acc.relay_delays) - 1))], 2)
              if acc.relay_delays else None),
    },
    "verdicts": verdicts(acc, pair_sum, xcorr_sum, ev_sum, hist_sum),
    "raw_events": {
      "step_events": acc.step_events[:1000],
      "rev_step_events": acc.rev_step_events[:1000],
      "override_events": acc.override_events[:1000],
      "brake_events": acc.brake_events[:1000],
    },
  }
  OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
  OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
  print(f"DONE. {acc.routes_ok} routes ok, {acc.routes_err} errored. "
        f"Written to {OUT_FILE}", file=sys.stderr)
  print(json.dumps(out["verdicts"], indent=2, default=str)[:4000])


if __name__ == "__main__":
  main()
