#!/usr/bin/env python3
"""
Checks which physical CAN bus (src) CruiseControl (0x144), ES_LKAS (0x164),
and ES_Distance (0x161) actually appear on, across a sample of the local
route archive. Run with sudo (files are root:khaledkdaone).
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import capnp
import zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"

TARGET_ADDRS = {0x144: "CruiseControl", 0x164: "ES_LKAS", 0x161: "ES_Distance"}
SAMPLE_SEGMENTS = 50


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


def main():
    log_schema = load_schema()
    groups = find_route_groups()
    route_ids = sorted(groups.keys())

    # pick every Nth route to spread across the whole archive, one segment each
    step = max(1, len(route_ids) // SAMPLE_SEGMENTS)
    chosen = route_ids[::step][:SAMPLE_SEGMENTS]

    bus_counts = {addr: Counter() for addr in TARGET_ADDRS}
    routes_with_addr = {addr: set() for addr in TARGET_ADDRS}
    segments_ok = 0
    segments_failed = 0
    total_can_frames = 0

    for route_id in chosen:
        seg_idx, seg_dir = groups[route_id][0]  # first segment of each chosen route
        found_any = False
        try:
            for ev in iter_events(log_schema, seg_dir):
                if ev.which() != "can":
                    continue
                for frame in ev.can:
                    total_can_frames += 1
                    addr = frame.address
                    if addr in TARGET_ADDRS:
                        bus_counts[addr][frame.src] += 1
                        routes_with_addr[addr].add(route_id)
                        found_any = True
            segments_ok += 1
        except Exception as e:
            print(f"FAILED {seg_dir}: {e}", file=sys.stderr)
            segments_failed += 1
            continue
        print(f"  {route_id}: {'ok, found target msgs' if found_any else 'ok, none of the target addrs seen'}")

    result = {
        "segments_sampled": len(chosen),
        "segments_ok": segments_ok,
        "segments_failed": segments_failed,
        "total_can_frames_scanned": total_can_frames,
        "bus_counts": {TARGET_ADDRS[addr]: dict(counts) for addr, counts in bus_counts.items()},
        "routes_seen_in": {TARGET_ADDRS[addr]: len(routes) for addr, routes in routes_with_addr.items()},
    }
    print(json.dumps(result, indent=2))

    out_path = Path(__file__).resolve().parent / "cruise_control_camera_bus_raw.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
