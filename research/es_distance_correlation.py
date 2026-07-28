#!/usr/bin/env python3
"""
Passive correlation: does ES_Distance's Cruise_Button field (0x161, bus 2)
actually read 2/3/4/5 (set-shallow/set-deep/resume-shallow/resume-deep) at
the moments real SET/RESUME button presses are known to have happened?

Ground truth for "a real press happened, and which direction": the
already-doubly-confirmed CruiseControl (0x144, bus 0) bits from Q4 —
SET_BUTTON = byte0 bit3, RES_BUTTON = byte0 bit4 (rising edge = press).

For each such edge, records the freshest Cruise_Button value seen on the
camera-bus (src=2) copy of ES_Distance up to that moment (matches
carstate.py's own cp_cam.vl["ES_Distance"]["Cruise_Button"] source), plus
how stale that value was. Also tracks carState.vCruiseCluster around the
same moment to get a real-world shallow(~1mph)/deep(~5mph) delta, to
cross-check against the DBC comment's shallow/deep claim independently.

Run inside the comma-pipeline-route-stats container (already has
capnp/zstandard + the archive mounted):
  docker exec comma-pipeline-route-stats-1 python3 /work/es_distance_correlation.py
(copy this file in first, e.g. docker cp)
"""
import json
import sys
from pathlib import Path

import capnp
import zstandard as zstd

RAW_DIR = Path("/data/routes/raw")
SCHEMA_DIR = Path("/app")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path("/work/es_distance_correlation_results.json")

CRUISE_CONTROL_ADDR = 0x144
ES_DISTANCE_ADDR = 0x161
CRUISE_CONTROL_SRC = 0   # main bus — matches carstate.py's cp_cruise (Bus.pt/CanBus.main)
ES_DISTANCE_SRC = 2      # camera bus — matches carstate.py's cp_cam (CanBus.camera)
SET_BIT = 3
RES_BIT = 4

STALE_WARN_NS = 100_000_000  # 100ms — flag if the freshest ES_Distance frame is older than this
VCRUISE_LOOKAHEAD_NS = 2_500_000_000  # 2.5s window to catch the resulting cluster-speed change


def bit(byte0: int, n: int) -> int:
    return (byte0 >> n) & 1


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


def process_route(log_schema, route_id, segments):
    """Returns list of press-event dicts for this route (time-ordered across segments)."""
    events_out = []

    prev_cc_byte0 = None
    latest_button = None       # last decoded Cruise_Button value (0-7)
    latest_button_t = None     # logMonoTime of that frame
    latest_counter = None      # ES_Distance COUNTER at that frame (sanity: is it live/incrementing)

    # rolling vCruiseCluster history as (t, value) for shallow/deep delta lookups
    vcluster_history = []  # kept short, pruned as we go

    for seg_idx, seg_dir in segments:
        for ev in iter_events(log_schema, seg_dir):
            try:
                which = ev.which()
                t = ev.logMonoTime

                if which == "carState":
                    try:
                        vc = float(ev.carState.vCruiseCluster)
                        vcluster_history.append((t, vc))
                        # prune anything older than 3s behind current time
                        cutoff = t - 3_000_000_000
                        while vcluster_history and vcluster_history[0][0] < cutoff:
                            vcluster_history.pop(0)
                    except Exception:
                        pass
                    continue

                if which != "can":
                    continue

                for frame in ev.can:
                    addr = frame.address
                    src = frame.src

                    if addr == ES_DISTANCE_ADDR and src == ES_DISTANCE_SRC:
                        dat = bytes(frame.dat)
                        if len(dat) >= 7:
                            latest_button = dat[6] & 0x07
                            latest_counter = (dat[5] >> 4) & 0x07
                            latest_button_t = t

                    elif addr == CRUISE_CONTROL_ADDR and src == CRUISE_CONTROL_SRC:
                        dat = bytes(frame.dat)
                        if not dat:
                            continue
                        byte0 = dat[0]
                        if prev_cc_byte0 is not None:
                            set_edge = bit(prev_cc_byte0, SET_BIT) == 0 and bit(byte0, SET_BIT) == 1
                            res_edge = bit(prev_cc_byte0, RES_BIT) == 0 and bit(byte0, RES_BIT) == 1
                            if set_edge or res_edge:
                                direction = "SET" if set_edge else "RES"
                                staleness_ns = (t - latest_button_t) if latest_button_t is not None else None

                                vcluster_before = vcluster_history[-1][1] if vcluster_history else None
                                events_out.append({
                                    "route_id": route_id,
                                    "t": t,
                                    "direction": direction,
                                    "es_distance_cruise_button": latest_button,
                                    "es_distance_staleness_ns": staleness_ns,
                                    "es_distance_counter_at_press": latest_counter,
                                    "vcluster_before": vcluster_before,
                                    "vcluster_before_t": vcluster_history[-1][0] if vcluster_history else None,
                                })
                        prev_cc_byte0 = byte0
            except Exception as e:
                print(f"  malformed event in {seg_dir}: {e}", file=sys.stderr)
                continue

    return events_out


def backfill_vcluster_after(log_schema, route_id, segments, press_events):
    """Second pass: for each press event, find the next distinct vCruiseCluster
    value within VCRUISE_LOOKAHEAD_NS after the press, to compute a real delta."""
    if not press_events:
        return
    pending = {id(e): e for e in press_events}
    idx_sorted = sorted(pending.values(), key=lambda e: e["t"])
    cursor = 0

    for seg_idx, seg_dir in segments:
        for ev in iter_events(log_schema, seg_dir):
            try:
                if ev.which() != "carState":
                    continue
                t = ev.logMonoTime
                vc = float(ev.carState.vCruiseCluster)

                while cursor < len(idx_sorted) and idx_sorted[cursor]["t"] + VCRUISE_LOOKAHEAD_NS < t:
                    cursor += 1

                for e in idx_sorted[cursor:]:
                    if e["t"] > t:
                        continue
                    if t - e["t"] > VCRUISE_LOOKAHEAD_NS:
                        continue
                    before = e.get("vcluster_before")
                    if before is None:
                        continue
                    if abs(vc - before) < 1e-6:
                        continue
                    if "vcluster_after" not in e:
                        e["vcluster_after"] = vc
                        e["vcluster_after_t"] = t
                        e["vcluster_delta"] = vc - before
            except Exception:
                continue


def main():
    log_schema = load_schema()
    groups = find_route_groups()
    print(f"found {len(groups)} routes, {sum(len(v) for v in groups.values())} segments", file=sys.stderr)

    all_events = []
    routes_processed = 0
    routes_with_error = 0

    for idx, (route_id, segments) in enumerate(sorted(groups.items())):
        try:
            press_events = process_route(log_schema, route_id, segments)
            if press_events:
                backfill_vcluster_after(log_schema, route_id, segments, press_events)
                all_events.extend(press_events)
            routes_processed += 1
        except Exception as e:
            routes_with_error += 1
            print(f"ROUTE ERROR {route_id}: {e}", file=sys.stderr)

        if (idx + 1) % 50 == 0:
            print(f"... {idx+1}/{len(groups)} routes, {len(all_events)} press events so far", file=sys.stderr)

    out = {
        "config": {
            "CRUISE_CONTROL_SRC": CRUISE_CONTROL_SRC,
            "ES_DISTANCE_SRC": ES_DISTANCE_SRC,
            "SET_BIT": SET_BIT,
            "RES_BIT": RES_BIT,
            "STALE_WARN_NS": STALE_WARN_NS,
            "VCRUISE_LOOKAHEAD_NS": VCRUISE_LOOKAHEAD_NS,
        },
        "routes_processed": routes_processed,
        "routes_with_error": routes_with_error,
        "press_event_count": len(all_events),
        "press_events": all_events,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
    print(f"DONE. {routes_processed} routes ok, {routes_with_error} errored, "
          f"{len(all_events)} press events. Written to {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
