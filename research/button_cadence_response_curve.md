# Button-press cadence response curve (2026-07-24)

Motivation: at shallow-only 1mph/2.0s, the commanded target descends at 0.5 mph/s -
slower than EyeSight's own physical comfort-tuned decel ceiling (~1.94 mph/s, confirmed
from the user's real 60→25mph/18s test). That means button cadence, not EyeSight's own
braking, was the actual bottleneck on how fast the car could respond to a closing
situation - surfaced directly by the 29:01 off-ramp incident (see
`research/29_01_incident_reconstruction.md` if written up separately, or progress.md).

## Method

Mined the existing 592-press archive dataset (`research/es_distance_correlation_results.json`,
136 routes) for real closely-spaced consecutive presses at varying intervals, bucketed by
exact `cruise_button` value (2/3/4/5) to avoid mixing shallow/deep magnitudes (an earlier
grouping-by-direction pass produced a misleading debounce-looking artifact purely from
that mixing).

## Result

**87 clean same-magnitude bursts across gaps from ~200ms to several seconds show no
debounce collapse and no overshoot anywhere in that range.**

- Deep presses (button 3/5, n=52): hold almost exactly 5.00mph/press from 200ms out to
  2000ms+. Single tightest clean isolated point: a real 199.5ms gap between two deep
  presses produced exactly -5.00mph/press, full undiminished effect.
- Shallow (button 2/4, n=35): ~1-5mph/press with more scatter - smaller sample, closer
  to the measurement noise floor for a 1mph signal.

**Debounce boundary narrowed, not fully pinned**: Q10's dedicated live test confirmed
full collapse at ~50ms; this archive pass confirms zero collapse at ~200ms. The actual
transition sits somewhere in that 50-200ms gap - the archive has no real single-gap
examples inside that specific window (real drivers don't press that fast often enough to
leave a clean isolated sample there).

Overshoot (the Discord report of "spamming increases set speed") never appears anywhere
in this dataset at any interval - either it requires a cadence/condition this archive
doesn't capture, or it's rarer/more car-specific than the one anecdote suggested.

## Important caveat, discovered by a follow-up isolated-single-press pass

A separate, tighter analysis (`research/es_distance_cruise_button_finding.md` follow-up,
2026-07-24) specifically isolating single presses with 4s clear on both sides found that
passively-observed magnitude is NOT reliable for distinguishing shallow vs deep - 37 of
38 clean isolated samples showed 5mph deltas regardless of whether the button code was
"shallow" (2/4) or "deep" (3/5) coded, conflicting with this project's own controlled
live spoof test (Q10: commanding btn=2 specifically, sustained, reliably produced ~1mph).
Likely explanation: passive correlation catches whatever button value happens to be
latched at the instant a press registers on the bus, and a real human tap can mechanically
bounce through multiple states before settling - not reliably "the value that caused the
outcome" the way a deliberate sustained spoof of one exact value is.

**This means the "deep ≈5mph" and "shallow ≈1mph" *magnitude* readings from the cadence
analysis above should be treated with the same skepticism** - both are passive/burst-
level reads, not controlled isolated tests. What the cadence analysis's *timing* finding
(no collapse from 200ms-several seconds) does NOT depend on knowing the magnitude
precisely, so that part still stands on its own. Bottom line: deep-step magnitude is not
trustworthy off archive data at all - would need a dedicated live spoofed test (same
method as Q10) before ever wiring cruise_button 3/5 into a live controller. Not done
tonight; shallow-only remains what's shipped.

## Recommendation adopted

**MIN_COMMAND_INTERVAL_S = 0.4s** (from 2.0s), shallow-only (values 2/4), no deep-step.
`1mph / 0.4s = 2.5 mph/s` - comfortably above EyeSight's own ~1.94 mph/s decel ceiling,
resolving the original bottleneck without touching the now-in-question deep-step
magnitude. Chosen from the well-supported 300-500ms range, not the single 200ms data
point (clean but not a margin).
