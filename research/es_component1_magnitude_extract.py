#!/usr/bin/env python3
"""Targeted re-extraction: for each of Round 1's 116 qualifying perception events
(route_id, t already known), pull |delta Cruise_Throttle| and |delta Throttle_Body|
over the response window directly from the archive. Not a full archive pass --
only the specific segments containing these 116 events are touched."""
import bisect, json, sys
from collections import defaultdict
from pathlib import Path
import capnp, zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
EVENTS_IN = Path("/work/round1_events.json")
OUT = Path("/work/component1_magnitudes.json")

MS = 1_000_000

def u(dat, start, length):
    if len(dat) < 8: dat = bytes(dat) + b"\x00" * (8 - len(dat))
    raw = int.from_bytes(dat[:8], "little")
    return (raw >> start) & ((1 << length) - 1)

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

def main():
    schema = capnp.load(str(SCHEMA_DIR / "log.capnp"), imports=[str(SCHEMA_DIR)])
    events = json.loads(EVENTS_IN.read_text())
    by_route = defaultdict(list)
    for e in events:
        by_route[e["route_id"]].append(e)
    groups = find_route_groups()

    out = []
    for rid, evs in by_route.items():
        if rid not in groups:
            continue
        ts_ct, vs_ct, ts_tb, vs_tb = [], [], [], []
        for _idx, seg in groups[rid]:
            data = read_rlog_bytes(seg)
            if not data: continue
            try:
                for ev in schema.Event.read_multiple_bytes(data):
                    if ev.which() != "can": continue
                    t = ev.logMonoTime
                    for fr in ev.can:
                        addr, src = fr.address, fr.src
                        if addr == 0x161 and src == 2:
                            ts_ct.append(t); vs_ct.append(u(bytes(fr.dat), 0, 12))
                        elif addr == 0x140 and src == 0:
                            ts_tb.append(t); vs_tb.append(u(bytes(fr.dat), 48, 8))
            except Exception:
                continue
        for e in evs:
            t0 = e["t"]
            lo_ct = bisect.bisect_left(ts_ct, t0 - 300 * MS)
            base_i = bisect.bisect_left(ts_ct, t0 - 300 * MS)
            base_j = bisect.bisect_left(ts_ct, t0 - 50 * MS)
            resp_i = bisect.bisect_left(ts_ct, t0)
            resp_j = bisect.bisect_left(ts_ct, t0 + 900 * MS)
            base_vals = vs_ct[base_i:base_j]
            resp_vals = vs_ct[resp_i:resp_j]
            mag_ct = None
            if base_vals and resp_vals:
                base_mean = sum(base_vals) / len(base_vals)
                mag_ct = max(abs(v - base_mean) for v in resp_vals)

            base_i2 = bisect.bisect_left(ts_tb, t0 - 300 * MS)
            base_j2 = bisect.bisect_left(ts_tb, t0 - 50 * MS)
            resp_i2 = bisect.bisect_left(ts_tb, t0)
            resp_j2 = bisect.bisect_left(ts_tb, t0 + 900 * MS)
            base_vals2 = vs_tb[base_i2:base_j2]
            resp_vals2 = vs_tb[resp_i2:resp_j2]
            mag_tb = None
            if base_vals2 and resp_vals2:
                base_mean2 = sum(base_vals2) / len(base_vals2)
                mag_tb = max(abs(v - base_mean2) for v in resp_vals2)

            out.append({
                "route_id": rid, "t": t0,
                "mag_ct": mag_ct, "mag_tb": mag_tb,
                "margin_vs_throttle_body_ms": e.get("margin_vs_throttle_body_ms"),
            })

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {len(out)} rows to {OUT}", file=sys.stderr)

if __name__ == "__main__":
    main()
