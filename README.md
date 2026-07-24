# Poor-Man's Longitudinal Control

A DIY curve-speed advisory / longitudinal-control research project for a 2015 Subaru
Outback running [sunnypilot](https://github.com/sunnypilot/sunnypilot) — built and
documented iteratively, with an emphasis on verifying every real claim against actual
telemetry, code, or first-hand community reports rather than assumption.

**Start here:** [`progress.md`](progress.md) — the living project doc. Phase status,
open questions, decisions log, and full incident history.

## What's actually shipped

- **Phase 1 (curve-speed advisory):** map-based curve detection (MTSC) wired to a
  driver-facing alert, live and working.
- **Lead-vehicle closing-speed advisory:** a second advisory trigger, grounded in real
  telemetry analysis of the vision model's own (previously unused) lead-detection data.
- **Phase 3 (real longitudinal actuation — live):** on a platform with no native
  long-control support, the car's own ACC (EyeSight) is commanded via steering-wheel
  button emulation ("ride EyeSight's own setpoint, turn its dial" rather than replace
  it) — a closed-loop controller for both curve-speed and lead-vehicle-closing scenarios,
  gated behind explicit driver-controlled arming and an unconditional, session-long
  override latch (brake/gas/steering torque instantly and permanently disables it).
  Deployed and live-tested on public roads. Real magnitude/cadence limits were
  empirically derived from this car's own archived driving data rather than assumed —
  see `research/button_cadence_response_curve.md` and
  `research/phase3_controller_design.md` for the full derivation and safety design.

## How this got here

Every step — from the original CAN reverse-engineering through the first live actuation
test — followed the same discipline: verify against real telemetry, actual code, or a
directly-quoted first-hand source before relying on anything, and revert immediately if
a live test starts misbehaving rather than debug live. That discipline caught real bugs
along the way (a plannerd crash from a schema mismatch, a safety-latch false-positive
from engagement timing, an under-sized safety budget), each found and fixed *before* it
became a real problem, not after.

See [`research/`](research) for the individual write-ups — CAN bus reverse-engineering,
UDS diagnostic probing, bus-topology analysis, and community research pulled from the
comma.ai Discord and cross-referenced against sunnypilot's own official implementations
for other car brands — with every claim checked against a primary source before being
relied on.

## A note on paths

A couple of the research scripts/docs reference a local route-archive location and
schema path from this project's own setup — those have been scrubbed before publishing.
Swap in your own paths if you want to actually run them.
