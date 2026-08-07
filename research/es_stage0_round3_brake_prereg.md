# Round 3 pre-registration: perception-impulse test for `ES_Brake.Brake_Pressure`

**Written 2026-08-07, BEFORE this test's script exists or has been run. Committed alone,
before any implementation or analysis code, so the timestamp is a genuine prior commitment
rather than a documentation convention** — same discipline as Round 2.

## Why this field, why now

Rounds 1 and 2 ran the flat-baseline perception-impulse test on `Cruise_Throttle`
(INCONCLUSIVE — a genuine near-miss undercut by a disagreeing secondary comparator) and
`Cruise_RPM` (clean NULL — notably reversing that field's own strong population-level
correlation, i.e. "most tightly correlated" and "leads causally" turned out to be different
claims). `esb_brake_pressure` (`ES_Brake`/`0x160`, the H2 field) has never had a perception
test at all, and never had a wide-lag correlation sweep either (only T6's onset-latency test
against real EyeSight-braking episodes, a different trigger). This round completes the
symmetric treatment of all three ES fields.

`ES_Brake` is **not TX-allowed today** and would need a panda firmware change to ever write
— so unlike Rounds 1-2, a CONFIRM here does not open an immediate practical door. It is
still worth running for completeness (exhausting what the archive can say about all three
members of the "command trio" before concluding the campaign) and because H2 has had less
scrutiny than H1/H3 so far.

## Comparators — fixed now, from an established precedent, not re-derived

**Primary: `brake2_left`** (`Brake_2`/`0xD2`, wheel/caliper pressure). Chosen because T6 (in
the completed main run, `research/es_longitudinal_command_results.md`) already measured, on
378 real EyeSight-braking episodes, that `brake2_left` leads `brake2_right` marginally
(500.38ms vs 550.05ms median onset after `ES_Brake.Brake_Pressure` goes non-zero) and both
lead the master-cylinder pair (`mc_brake_right`/`mc_brake_left`, ~800-890ms) by ~300-400ms —
i.e. `brake2_*` is the faster, more direct physical-actuation pair, analogous to
`throttle_body`/`trans_engine`'s role in Rounds 1-2.

**Secondary/descriptive only, NOT used for the verdict:** `brake2_right`, `mc_brake_right`,
`mc_brake_left`, `aego`. Reported for completeness; `mc_brake_*` in particular is expected to
be a slow secondary signal (T6's own ~300-400ms lag behind `brake2_*`), the same
"everything beats the slow signal" red herring pattern documented in Rounds 1-2 for
`engine_rpm_140`/`wheel_torque`.

## Onset thresholds — reused from T6's established precedent, not re-derived from scratch

Round 2 derived fresh thresholds because `Cruise_RPM`/`Transmission_Engine` had no prior
onset-detector calibration anywhere in this campaign. That is not true here: T6 already
established and successfully used onset thresholds for every comparator in this round, on a
real 378-event run:

| field | T6's established threshold | used here |
|---|---|---|
| `brake2_right` / `brake2_left` | 2.0 counts | **2.0** (unchanged) |
| `mc_brake_right` / `mc_brake_left` | 2.0 counts | **2.0** (unchanged) |
| `aego` | 0.2 | **0.2** (unchanged) |

Reusing validated thresholds is preferred here to re-deriving new ones from a fresh jitter
sample, on the reasoning that T6 already is a successful, real calibration on this exact
field set (not a hypothetical) — re-deriving would risk *appearing* more rigorous while
actually just adding an arbitrary second number where a validated one already exists.

**`esb_brake_pressure`'s own onset threshold has no direct T6 analogue** (T6 used a hard
threshold — `bp_prev==0 and bp_now>20` — to define the START of a braking episode, not a
sigma-based onset-latency detector measuring how long *after* some other trigger it takes to
respond). That hard threshold of **20 counts** is nonetheless a real, already-used activation
level for this exact field on this exact car, so it is adopted directly as the onset
threshold here: **`esb_brake_pressure`: 20 counts.**

## Flat-baseline filter and real-response requirement — fixed now

Same ratio convention as Rounds 1-2 (baseline peak-to-peak ≤ 75% of the onset threshold):

- **Flat-baseline filter:** `esb_brake_pressure` peak-to-peak over `[-1000ms, -50ms]` must be
  **≤ 15 counts** (75% of 20).
- **Real-response requirement:** `|Δ esb_brake_pressure| ≥ 20` counts somewhere in the
  response window (below), matching the onset threshold exactly — same convention as both
  prior rounds (`REAL_RESPONSE_MIN == onset threshold`).

## Response window — EXTENDED beyond Rounds 1-2, with reasoning fixed now

Rounds 1-2 used a 1.2s post-trigger window. That is very likely too short here: T6 measured
500-900ms just for the *physical* braking response to arrive *after* `ES_Brake.Brake_Pressure`
already started moving — and here we are measuring how long `ES_Brake.Brake_Pressure` itself
takes to first move *after* a perception trigger, which requires EyeSight to additionally
decide that throttle modulation alone is insufficient and a brake command is warranted. That
decision plausibly takes longer than an immediate throttle adjustment.

**Response window: `(0, +2500ms]`** (vs. Rounds 1-2's 1200ms). The baseline window
(`[-1000ms, -50ms]`), isolation window (±2s), and sustain requirement (≥1s) are unchanged.
The driver-input/ACC-engaged/no-fault gates now span the full extended window
`[-1000ms, +2500ms]`, which will further reduce N relative to Rounds 1-2 — expected and
accepted, not a problem to work around.

## Event definition — same structure as Rounds 1-2, adapted per above

An event qualifies iff **all** of:
1. `Car_Follow` transitions `0 → 1` (lead acquired). Lead-lost events collected as an
   unfiltered secondary endpoint only, same demotion as both prior rounds.
2. Flat-baseline requirement above.
3. Real-response requirement above, within `(0, +2500ms]`.
4. ACC engaged throughout `[-1000ms, +2500ms]`; no driver gas or brake anywhere in that
   window; no `Cruise_Fault`; the transition isolated by ±2s from any other `Car_Follow`
   transition; the new `Car_Follow` state sustained ≥1s.
5. `esb_brake_pressure` not pinned at 0 (its known, already-established floor/inactive value
   — unlike Round 2's RPM field, this one has a directly confirmed floor from the original
   main run's histograms) for the whole window.

## Primary endpoint and decision rule — IDENTICAL numeric bars to Rounds 1-2

Kept identical for direct cross-field comparability, not threshold-shopped:

**`frac_brake_first_50` = fraction of qualifying events where `onset(esb_brake_pressure)`
precedes `onset(brake2_left)` by ≥ 50ms.**

| outcome | criterion |
|---|---|
| **CONFIRM** | `frac_brake_first_50` ≥ **70%** AND median margin ≥ **75ms** |
| **NULL** | `frac_brake_first_50` ≤ **50%** OR median margin ≤ **25ms** |
| **INCONCLUSIVE** | anything between, or N below the power floor |

## Power floor — LOWERED from Rounds 1-2's N≥100, with reasoning fixed now

**Power floor: N ≥ 50 qualifying events.** Justification, stated before running: braking
events tied specifically to a `Car_Follow` acquisition are expected to be structurally rarer
than throttle-modulation events, because most cut-ins plausibly first cause throttle
reduction and only escalate to a brake command if the gap keeps closing after that. Combined
with the extended 2.5s gating window (which independently shrinks N by requiring a longer
clean stretch of driving), a lower floor than Rounds 1-2's N≥100 is set here proactively,
not after seeing an insufficient count. If the smoke sample suggests even N≥50 is
unreachable, that will be reported honestly as INCONCLUSIVE-by-construction rather than
lowering the floor further post-hoc.

## Analysis decisions fixed in advance

- The ~25ms `ES_Distance` quantization bias is acknowledged and **not** corrected for, same
  as both prior rounds.
- No post-hoc stratification of the primary endpoint.
- Secondary comparators (`brake2_right`, `mc_brake_right`, `mc_brake_left`, `aego`) reported
  but may not be quoted as a headline verdict, identical treatment to
  `wheel_torque`/`engine_rpm_140` in Rounds 1-2.

## Pre-registered expected outcome — recorded before running

**INCONCLUSIVE is the most likely single outcome, primarily on power grounds rather than a
directional prediction.** Estimate: INCONCLUSIVE ~55% (dominated by the risk that N<50 given
the extended window and expected event rarity), NULL ~25%, CONFIRM ~20%. Two reasons CONFIRM
is not ruled favorite despite the very high wide-lag correlation (Step 1, run first, found
R²≈0.97-0.98 on a 15-route smoke sample — a strong signal, though at a coarser/unresolved
lag): first, Round 2 already showed that a strong population-level correlation does not
reliably survive a genuine causal-ordering test (`Cruise_RPM` went from R²=0.99 to a clean
NULL); second, `ES_Brake` requires an extra decision step (brake vs. throttle-only) that the
other two fields don't, which plausibly adds latency variance that could push the median
margin either direction. This reasoning is recorded now, before the perception test itself
has been run, specifically so the eventual result cannot be read as confirming a prediction
that was actually written after the fact.
