#!/usr/bin/env python3
"""Component 2: do the three ES fields (Cruise_Throttle, Cruise_RPM, Brake_Pressure)
move together (single internal decision -> 3 outputs) or in sequence (staged)?
Wide-lag pairwise correlation between the fields THEMSELVES, not vs powertrain.
Restricted to ticks where esb_brake_pressure is active (>20, matching Round 3's
variance guard) -- the rarer, most-informative window where all three fields are
plausibly moving together for a real reason."""
import bisect, json, math, sys
from collections import defaultdict, deque
from pathlib import Path
import capnp, zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
OUT_FILE = Path("/work/es_crossfield_results.json")

MS = 1_000_000
S = 1_000_000_000
HORIZON_NS = 20 * S
SETTLE_NS = 3 * S
MAX_STALE_NS = 200 * MS
LAGS_MS = list(range(-1500, 1525, 50))

def u(dat, start, length):
    if len(dat) < 8: dat = bytes(dat) + b"\x00" * (8 - len(dat))
    raw = int.from_bytes(dat[:8], "little")
    return (raw >> start) & ((1 << length) - 1)

def dec_es_distance(d): return {"es_cruise_throttle": u(d, 0, 12)}
def dec_es_status(d): return {"ess_cruise_rpm": u(d, 16, 16)}
def dec_es_brake(d): return {"esb_brake_pressure": u(d, 0, 16)}
def dec_cruisecontrol(d): return {"cc_cruise_activated": u(d, 49, 1)}

DECODERS = {
    (0x161, 2): dec_es_distance,
    (0x162, 2): dec_es_status,
    (0x160, 2): dec_es_brake,
    (0x144, 0): dec_cruisecontrol,
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
        self.n_active_ticks = 0
        self.fit_ct_rpm = defaultdict(lambda: [0,0.0,0.0,0.0,0.0,0.0])
        self.fit_ct_brake = defaultdict(lambda: [0,0.0,0.0,0.0,0.0,0.0])
        self.fit_rpm_brake = defaultdict(lambda: [0,0.0,0.0,0.0,0.0,0.0])

def process_route(schema, acc, route_id, segments):
    bufs = Buffers(HORIZON_NS)
    pending = deque()
    def drain(now, force=False):
        while pending and (force or now - pending[0] > SETTLE_NS):
            t = pending.popleft()
            act, _ = bufs.at("cc_cruise_activated", t)
            bp, _ = bufs.at("esb_brake_pressure", t)
            if not act or bp is None or bp <= 20:
                continue
            acc.n_active_ticks += 1
            for lag_ms in LAGS_MS:
                fit_at_lag(bufs, "es_cruise_throttle", "ess_cruise_rpm", t, lag_ms, acc.fit_ct_rpm)
                fit_at_lag(bufs, "es_cruise_throttle", "esb_brake_pressure", t, lag_ms, acc.fit_ct_brake)
                fit_at_lag(bufs, "ess_cruise_rpm", "esb_brake_pressure", t, lag_ms, acc.fit_rpm_brake)
    for _idx, seg in segments:
        data = read_rlog_bytes(seg)
        if not data: continue
        try:
            for ev in schema.Event.read_multiple_bytes(data):
                if ev.which() != "can": continue
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
        if (idx+1) % 20 == 0:
            print(f"... {idx+1}/{len(route_ids)} routes, {acc.n_active_ticks} active ticks", file=sys.stderr)
    out = {
        "routes_ok": acc.routes_ok, "routes_err": acc.routes_err,
        "n_active_ticks": acc.n_active_ticks,
        "lags_ms_tested": LAGS_MS,
        "cruise_throttle_vs_cruise_rpm": fit_summary(acc.fit_ct_rpm),
        "cruise_throttle_vs_brake_pressure": fit_summary(acc.fit_ct_brake),
        "cruise_rpm_vs_brake_pressure": fit_summary(acc.fit_rpm_brake),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
    print(f"DONE. {acc.routes_ok} ok, {acc.routes_err} err.", file=sys.stderr)
    for k in ("cruise_throttle_vs_cruise_rpm","cruise_throttle_vs_brake_pressure","cruise_rpm_vs_brake_pressure"):
        print(k, "best:", json.dumps(out[k]["best"]))

if __name__ == "__main__":
    main()
