#!/usr/bin/env python3
"""
Lead-vehicle early-warning feasibility analysis.

Mines the local route archive (/mnt/immich-storage/comma-routes/raw) for
real evidence on whether openpilot's vision-based lead detection
(radarState.leadOne) could have given useful advance warning before this
car's driver had to brake for a decelerating/queued lead vehicle, on a car
with no radar and no real longitudinal control.

Schema: reuses the route-stats pipeline's own proven log.capnp copy
(~/homelab/comma-pipeline/route-stats/log.capnp) since it's already
confirmed working against this exact archive in production.

Output: writes raw findings as JSON to lead_warning_raw_results.json in the
same directory as this script, for the writeup to summarize.
"""
import json
import math
import sys
from pathlib import Path

import capnp
import zstandard as zstd

RAW_DIR = Path("/mnt/immich-storage/comma-routes/raw")
SCHEMA_DIR = Path("/home/khaledkdaone/homelab/comma-pipeline/route-stats")
SCHEMA_FILE = SCHEMA_DIR / "log.capnp"
OUT_FILE = Path(__file__).resolve().parent / "lead_warning_raw_results.json"

MS_TO_MPH = 2.2369362920544
M_TO_FT = 3.28084

HIGHWAY_MPS = 22.35  # 50 mph
CLOSING_VREL_THRESHOLD = -3.0  # m/s, i.e. closing at > ~6.7mph relative
MIN_SUSTAINED_SAMPLES = 5  # at our stride, see below
LOOKBACK_NO_BRAKE_SEC = 3.0
LOOKFORWARD_SEC = 30.0
REACTION_DECEL_MPH = 8.0  # vEgo drop over the lookforward window counts as a "reaction" even without brake
STRIDE = 10  # keep every 10th carState sample (~10Hz from ~100Hz)


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
    entries = list(RAW_DIR.iterdir())
    for entry in entries:
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


def build_route_samples(log_schema, route_id, segments):
    """Returns a list of sample dicts, one per (strided) carState event, in time order."""
    samples = []
    first_mono = None
    carstate_count = 0

    cur_lead_present = False
    cur_lead_dRel = None
    cur_lead_vRel = None
    cur_lead_vLead = None
    cur_lead_yRel = None
    cur_lead_prob = None
    cur_lead_radar = None
    cur_fcw = False

    for seg_idx, seg_dir in segments:
        for ev in iter_events(log_schema, seg_dir):
            try:
                if not ev.valid:
                    continue
                which = ev.which()

                if which == "radarState":
                    lead = ev.radarState.leadOne
                    cur_lead_present = bool(lead.present)
                    if cur_lead_present:
                        cur_lead_dRel = lead.dRel
                        cur_lead_vRel = lead.vRel
                        cur_lead_vLead = lead.vLead
                        cur_lead_yRel = lead.yRel
                        cur_lead_prob = lead.modelProb
                        cur_lead_radar = bool(lead.radar)
                        try:
                            cur_fcw = bool(lead.deprecated.fcw)
                        except AttributeError:
                            try:
                                cur_fcw = bool(lead.fcw)
                            except AttributeError:
                                cur_fcw = False
                    else:
                        cur_lead_dRel = None
                        cur_lead_vRel = None
                        cur_lead_vLead = None
                        cur_lead_yRel = None
                        cur_lead_prob = None
                        cur_lead_radar = None

                elif which == "carState":
                    cs = ev.carState
                    mono = ev.logMonoTime
                    if first_mono is None:
                        first_mono = mono
                    carstate_count += 1
                    if carstate_count % STRIDE != 0:
                        continue

                    try:
                        cruise_enabled = bool(cs.cruiseState.enabled)
                        cruise_speed = float(cs.cruiseState.speed)
                    except Exception:
                        cruise_enabled = None
                        cruise_speed = None

                    samples.append({
                        "t": round((mono - first_mono) / 1e9, 3),
                        "vEgo": cs.vEgo,
                        "brakePressed": bool(cs.brakePressed),
                        "gasPressed": bool(cs.gasPressed),
                        "cruiseEnabled": cruise_enabled,
                        "cruiseSpeed": cruise_speed,
                        "leadPresent": cur_lead_present,
                        "leadDRel": cur_lead_dRel,
                        "leadVRel": cur_lead_vRel,
                        "leadVLead": cur_lead_vLead,
                        "leadYRel": cur_lead_yRel,
                        "leadProb": cur_lead_prob,
                        "leadRadar": cur_lead_radar,
                        "fcw": cur_fcw,
                    })
            except Exception as e:
                print(f"  malformed event in {seg_dir}: {e}", file=sys.stderr)
                continue

    return samples


def analyze_route(route_id, samples):
    """Returns (candidates list, highway_sample_count, lead_present_count, radar_count, fcw_events)"""
    candidates = []
    fcw_events = []
    highway_count = 0
    lead_present_count = 0
    radar_count = 0

    n = len(samples)
    i = 0
    in_candidate = False
    candidate_start_idx = None

    while i < n:
        s = samples[i]
        is_highway = s["vEgo"] is not None and s["vEgo"] > HIGHWAY_MPS
        if is_highway:
            highway_count += 1
            if s["leadPresent"]:
                lead_present_count += 1
                if s["leadRadar"]:
                    radar_count += 1

        if s["fcw"]:
            fcw_events.append({"t": s["t"], "vEgo_mph": round(s["vEgo"] * MS_TO_MPH, 1),
                                "dRel": s["leadDRel"], "vRel": s["leadVRel"]})

        closing = (is_highway and s["leadPresent"] and s["cruiseEnabled"]
                   and s["leadVRel"] is not None and s["leadVRel"] < CLOSING_VREL_THRESHOLD)

        if closing and not in_candidate:
            # check no-brake lookback
            lookback_ok = True
            j = i - 1
            lookback_start_t = s["t"] - LOOKBACK_NO_BRAKE_SEC
            while j >= 0 and samples[j]["t"] >= lookback_start_t:
                if samples[j]["brakePressed"] or samples[j]["gasPressed"]:
                    lookback_ok = False
                    break
                j -= 1
            if lookback_ok:
                in_candidate = True
                candidate_start_idx = i

        elif not closing and in_candidate:
            # candidate window ended, evaluate if sustained long enough
            duration_samples = i - candidate_start_idx
            if duration_samples >= MIN_SUSTAINED_SAMPLES:
                start = samples[candidate_start_idx]
                candidates.append(_evaluate_candidate(route_id, samples, candidate_start_idx, i))
            in_candidate = False
            candidate_start_idx = None

        i += 1

    if in_candidate:
        duration_samples = n - candidate_start_idx
        if duration_samples >= MIN_SUSTAINED_SAMPLES:
            candidates.append(_evaluate_candidate(route_id, samples, candidate_start_idx, n))

    return candidates, highway_count, lead_present_count, radar_count, fcw_events


def _evaluate_candidate(route_id, samples, start_idx, end_idx):
    start = samples[start_idx]
    detect_t = start["t"]
    dRel = start["leadDRel"]
    vRel = start["leadVRel"]
    vEgo_mph = start["vEgo"] * MS_TO_MPH
    ttc = (dRel / -vRel) if (dRel is not None and vRel is not None and vRel < 0) else None

    reaction_t = None
    reaction_type = None
    forward_limit_t = detect_t + LOOKFORWARD_SEC
    baseline_vEgo = start["vEgo"]

    k = start_idx
    while k < len(samples) and samples[k]["t"] <= forward_limit_t:
        s = samples[k]
        if s["brakePressed"]:
            reaction_t = s["t"]
            reaction_type = "brake"
            break
        if baseline_vEgo is not None and s["vEgo"] is not None:
            drop_mph = (baseline_vEgo - s["vEgo"]) * MS_TO_MPH
            if drop_mph > REACTION_DECEL_MPH and not s["gasPressed"]:
                reaction_t = s["t"]
                reaction_type = "decel_no_brake"
                break
        k += 1

    result = {
        "route_id": route_id,
        "detect_t": detect_t,
        "dRel_m": dRel,
        "dRel_ft": round(dRel * M_TO_FT, 0) if dRel is not None else None,
        "vRel_mps": vRel,
        "vEgo_mph": round(vEgo_mph, 1),
        "ttc_sec": round(ttc, 1) if ttc is not None else None,
        "leadProb": start["leadProb"],
        "leadRadar": start["leadRadar"],
        "leadYRel": start["leadYRel"],
        "reacted": reaction_t is not None,
        "reaction_type": reaction_type,
        "lead_time_sec": round(reaction_t - detect_t, 1) if reaction_t is not None else None,
    }
    return result


def main():
    log_schema = load_schema()
    groups = find_route_groups()
    print(f"found {len(groups)} routes, {sum(len(v) for v in groups.values())} segments", file=sys.stderr)

    all_candidates = []
    all_fcw = []
    total_highway = 0
    total_lead_present = 0
    total_radar = 0
    routes_processed = 0
    routes_with_error = 0

    for idx, (route_id, segments) in enumerate(sorted(groups.items())):
        try:
            samples = build_route_samples(log_schema, route_id, segments)
            if not samples:
                continue
            candidates, hwy, lead_present, radar, fcw_events = analyze_route(route_id, samples)
            all_candidates.extend(candidates)
            all_fcw.extend(fcw_events)
            total_highway += hwy
            total_lead_present += lead_present
            total_radar += radar
            routes_processed += 1
        except Exception as e:
            routes_with_error += 1
            print(f"ROUTE ERROR {route_id}: {e}", file=sys.stderr)

        if (idx + 1) % 25 == 0:
            print(f"... {idx+1}/{len(groups)} routes, {len(all_candidates)} candidates so far", file=sys.stderr)

    out = {
        "config": {
            "HIGHWAY_MPS": HIGHWAY_MPS,
            "CLOSING_VREL_THRESHOLD": CLOSING_VREL_THRESHOLD,
            "MIN_SUSTAINED_SAMPLES": MIN_SUSTAINED_SAMPLES,
            "LOOKBACK_NO_BRAKE_SEC": LOOKBACK_NO_BRAKE_SEC,
            "LOOKFORWARD_SEC": LOOKFORWARD_SEC,
            "REACTION_DECEL_MPH": REACTION_DECEL_MPH,
            "STRIDE": STRIDE,
        },
        "routes_processed": routes_processed,
        "routes_with_error": routes_with_error,
        "total_highway_samples": total_highway,
        "total_lead_present_samples": total_lead_present,
        "total_radar_matched_samples": total_radar,
        "fcw_event_count": len(all_fcw),
        "fcw_events_sample": all_fcw[:50],
        "candidate_count": len(all_candidates),
        "candidates": all_candidates,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2, default=str))
    print(f"DONE. {routes_processed} routes ok, {routes_with_error} errored, "
          f"{len(all_candidates)} candidates, {len(all_fcw)} fcw events. Written to {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
