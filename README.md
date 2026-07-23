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
- An opt-in validation tool for testing automated speed-adjustment guidance against real
  driving, before any hardware investment.

## Phase 2/3 (recon, not yet actuation)

Investigating whether real longitudinal control (not just advisory) is feasible on a
platform with no native long-control support. This has stayed strictly recon/bench-only
throughout — every finding below came from either passive CAN analysis of already-logged
drives, or narrowly-scoped live tests with explicit before/after safety verification.

See [`research/`](research) for the individual write-ups — CAN bus reverse-engineering,
UDS diagnostic probing, bus-topology analysis, and community research pulled from the
comma.ai Discord, with every claim checked against a primary source (real telemetry,
actual code, or a directly-quoted first-hand report) before being relied on.

## A note on paths

A couple of the research scripts/docs reference a local route-archive location and
schema path from this project's own setup — those have been scrubbed before publishing.
Swap in your own paths if you want to actually run them.
