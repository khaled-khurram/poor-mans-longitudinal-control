# Round 2 pre-registration: perception-impulse retest for `Cruise_RPM`

**Written 2026-08-07, BEFORE this test's script exists or has been run. Committed alone,
before any implementation or analysis code, so the timestamp is a genuine prior commitment
rather than a documentation convention.**

## Why this field, why now

Round 1 (`research/es_stage0_round1_testA_results.md`) ran the flat-baseline
perception-impulse test on `Cruise_Throttle` and came back INCONCLUSIVE — a genuine
near-miss (median margin cleared its bar, win-rate fell 8 points short) undercut further by
a secondary comparator (`wheel_torque`) landing at chance on the same events.

`Cruise_RPM` (`ES_Status`/`0x162`) is the strongest remaining candidate for a clean result.
The prior wide-lag correlation work (`research/es_rpm_focus.py` /
`es_rpm_focus_results.json`) found R²=0.9905 at a sharp interior peak, lag=+400ms
(command-direction, not echo-direction), vs `Transmission_Engine` — a single, well-resolved
peak, not the broad ambiguous hump `Cruise_Throttle` showed against `Throttle_Cruise`. If any
of the three ES fields is going to win a perception-triggered race against the powertrain,
the prior evidence says it's this one.

## Comparators — fixed now

- **Primary: `trans_engine`** (`Transmission_Engine`, `0x148`, bits `16|15`). Chosen because
  it produced the tightest, most command-direction-favoring fit in the prior wide-lag work.
- **Secondary/descriptive only, NOT used for the verdict: `engine_rpm_140`** (`0x140`,
  `Engine_RPM`). Same demotion Round 1 applied to `wheel_torque`/`engine_rpm_140` — a slow,
  filtered signal will look like it's "beaten" by almost anything that moves early, which
  carries no command-vs-report information (documented in Round 1 as a red herring). Reported
  for completeness only.

## Onset thresholds — derived, not reused verbatim

Round 1 used pre-existing thresholds inherited from the original T4/T6 detector design.
`Cruise_RPM` and `Transmission_Engine` have no such prior threshold anywhere in this
campaign, so one was derived here from each field's own observed frame-to-frame jitter
(sample-to-sample absolute difference) over a 15-route calm sample of real `acc_engaged`
driving, computed directly from the archive before writing this threshold down:

| field | n samples (15-route sample) | median \|Δ\| | p90 \|Δ\| | p99 \|Δ\| | **chosen onset threshold** |
|---|---|---|---|---|---|
| `ess_cruise_rpm` | 163,667 | 2 | 9 | 33 | **60 counts** (~1.8× p99) |
| `trans_engine` | 819,409 | 1 | 2 | 8 | **20 counts** (~2.5× p99) |
| `engine_rpm_140` | *(pre-existing, campaign-wide)* | — | — | — | **30 counts** (unchanged from Round 1/T4/T6) |

Both new thresholds sit comfortably above their field's own p99 frame-to-frame jitter (so
ordinary noise won't trip the detector) and are small relative to the dynamic range these
fields move through during a real response (thousands of counts, per the T8 joint
distribution and the wide-lag work's own residual scale of ~44–85 counts around the
regression line) — so a real perception-triggered response should clear them easily if one
exists.

## Flat-baseline filter — fixed now

Same logic as Round 1: the pre-event baseline (`[-1000ms, -50ms]`) peak-to-peak range on
`Cruise_RPM` must be **≤ 45 counts** (75% of the 60-count onset threshold, matching Round 1's
own baseline/onset ratio of 30/40), so the baseline by construction contains nothing the
detector would itself call an onset.

## Event definition — identical structure to Round 1

An event qualifies iff **all** of:
1. `Car_Follow` transitions `0 → 1` (lead acquired). Lead-lost events are collected as a
   secondary endpoint only, same demotion as Round 1.
2. Flat-baseline requirement above.
3. Real response required: `|Δ Cruise_RPM| ≥ 60` counts somewhere in `(0, +1200ms]`.
4. ACC engaged throughout `[-1000ms, +1200ms]`; no driver gas or brake anywhere in that
   window; no `Cruise_Fault`; the transition isolated by ±2s from any other `Car_Follow`
   transition; the new `Car_Follow` state sustained ≥1s.
5. `Cruise_RPM` not pinned at its own observed floor for the whole window (mirrors Round 1's
   "not pinned at 808" exclusion for Throttle — the floor value for RPM will be determined
   empirically during the run and is whatever value the histogram shows dominating
   `acc_off`/idle samples; excluded because a pinned field carries no ordering information).

## Primary endpoint and decision rule — IDENTICAL numeric thresholds to Round 1

Kept identical on purpose, for direct cross-field comparability within the campaign rather
than threshold-shopping a friendlier bar for the field expected to do better:

**`frac_rpm_first_50` = fraction of qualifying events where `onset(Cruise_RPM)` precedes
`onset(trans_engine)` by ≥ 50ms.**

| outcome | criterion |
|---|---|
| **CONFIRM** | `frac_rpm_first_50` ≥ **70%** AND median margin ≥ **75ms** |
| **NULL** | `frac_rpm_first_50` ≤ **50%** OR median margin ≤ **25ms** |
| **INCONCLUSIVE** | anything between, or N below the power floor |

**Power floor: N ≥ 100 qualifying events.** Below that: INCONCLUSIVE regardless of the
numbers. Round 1's flat-baseline filter rejected ~86% of otherwise-qualifying candidates on
`Cruise_Throttle`; `Cruise_RPM`'s rejection rate under its own filter is unknown and will be
checked with a smoke sample before committing to the full run. If the smoke sample indicates
the floor is unreachable, that will be reported honestly rather than loosening this
threshold.

## Analysis decisions fixed in advance

- The same ~25ms quantization bias as Round 1 (ES ticks at 20Hz) is acknowledged and **not**
  corrected for.
- No further stratification of the primary endpoint post-hoc. A subgroup pattern, if one
  appears, is a future hypothesis, not a Round 2 result — same discipline as Round 1's
  handling of the (separately, honestly-flagged-as-post-hoc) T5 stratification.
- `engine_rpm_140` results are reported but may not be quoted as a headline, identical to
  Round 1's treatment.

## Pre-registered expected outcome — recorded before running

**CONFIRM is more likely here than it was for `Cruise_Throttle`, but INCONCLUSIVE is still
the single most likely outcome.** Estimate: INCONCLUSIVE ~45%, CONFIRM ~35%, NULL ~20%. The
reasoning for raising CONFIRM's odds relative to Round 1: `Cruise_RPM`'s baseline
(non-perception) correlation with the powertrain was far tighter and directionally cleaner
(sharp interior peak, unambiguous command-side lag) than `Cruise_Throttle`'s broad ambiguous
hump was — if that directional signal is real, it should show up here too. The reasoning for
keeping INCONCLUSIVE as the modal outcome anyway: the binding constraint in Round 1 was
`ES_Distance`'s 20Hz tick rate, which applies identically to `Cruise_RPM` (also carried at
20Hz via the same message cadence), and Round 1's margins (20–49ms) were well within the
range this same resolution ceiling would produce regardless of which field is being raced.
