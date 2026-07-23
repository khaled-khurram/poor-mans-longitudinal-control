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
comma.ai Discord (with every claim checked against a primary source before being relied
on — this project has caught and corrected fabricated "research" before, see
`progress.md` §7.1/§7.2).

## A note on rigor

Two early AI-generated research passes are referenced in `progress.md` but deliberately
**not included here** — they mixed real findings with fabricated specifics (invented
function names, a misattributed citation, a fabricated "verbatim quote"), and every
claim from them was independently re-verified before anything was built on it. The
research docs in this repo are the ones that survived that bar.
