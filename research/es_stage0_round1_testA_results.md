# Test A results: the flat-baseline perception-impulse retest

**Date: 2026-08-07. Fully passive archive analysis, zero CAN transmission, zero device
access.** Executes Test A exactly as fixed in `research/es_stage0_prereg_round2.md` — every
threshold below was written down before this script ran. Script:
`research/es_perception_flatbase_test.py`. Raw results:
`research/es_perception_flatbase_results.json`.

## Why this test exists

The round-1 perception-trigger test (`research/es_perception_focus.py`,
`es_stage0_followup_results.md` §5) came back INCONCLUSIVE for a diagnosed reason: its
traces showed `Cruise_Throttle` was already declining ~300ms *before* the `Car_Follow` flag
flipped, because the flag is a threshold on a continuous internal estimate, not an exogenous
impulse — and that same pre-flip drift contaminated the onset detector's own baseline
window. Test A's fix: only score events where `Cruise_Throttle` is provably flat
(peak-to-peak ≤ 30 counts) through the entire `[-1000ms, -50ms]` baseline window, which
selects for genuine surprises and simultaneously decontaminates the baseline.

## PRIMARY RESULT — mechanically applied, exactly as pre-registered

```
PRIMARY_VERDICT: INCONCLUSIVE
  frac_ct_first_50 = 61.82%   (need >= 70% for CONFIRM, <= 50% for NULL)
  median_margin_ms = 80.06ms  (need >= 75ms for CONFIRM, <= 25ms for NULL)
  n_qualifying = 116          (power floor: 100 — CLEARED, comfortably)
```

**Neither AND-condition for CONFIRM is jointly satisfied.** The median margin (80.06ms)
*does* clear the CONFIRM bar (≥75ms) on its own — but the win-rate does not (61.82% vs the
70% required), and CONFIRM requires both simultaneously. This is a genuine near-miss, not an
ambiguous middle: one of the two pre-registered conditions passed, the other fell short by
8 points. Per the fixed decision rule, that is INCONCLUSIVE, not a partial confirm, and it is
reported as such without editorializing the threshold.

## What actually happened, in full

| comparator | n_usable | median onset | median margin | CT-first (any) | **CT-first ≥50ms (primary stat)** |
|---|---|---|---|---|---|
| **`throttle_body` (primary)** | 110 | 429.9ms | **80.06ms** | 73.64% | **61.82%** |
| `wheel_torque` (descriptive) | 110 | 269.6ms | **19.97ms** | 50.91% | 45.45% |
| `engine_rpm_140` (descriptive, excluded from primary by pre-reg) | 23 | 869.9ms | 639.27ms | 82.61% | 78.26% |

`Cruise_Throttle`'s own median onset: **449.6ms** (n=116/116, always detected — expected,
since a detected onset is part of the qualifying criteria).

**A real inconsistency between the two direct physical comparators, worth stating plainly
rather than picking the flattering one.** `throttle_body` shows a real, near-CONFIRM lead
(median margin 80ms, clearing the CONFIRM bar on its own). `wheel_torque` — also a fast,
direct actuation signal, and used as a secondary specifically to cross-check `throttle_body`
— shows essentially **chance-level timing** (50.91% win rate, median margin 19.97ms, which
would itself satisfy the **NULL** condition in isolation). Two signals that both measure
"the powertrain moving" disagree with each other by a wide margin on the same 116 events.
That disagreement is itself evidence against a clean, confident CONFIRM — a genuine command
signal that beats `throttle_body` by 80ms should not simultaneously be a coin-flip against
`wheel_torque`, which is mechanically close to (in an CVT, downstream but tightly coupled
with) `throttle_body`.

`engine_rpm_140` (n=23 only, most events lack a detected RPM onset within the response
window) again shows the largest-looking margin — and is again excluded from the primary
result and *not* treated as supporting evidence, per pre-registration, for the same reason
as round 1: RPM is slow and CVT-decoupled and a large margin against it is uninformative.

**A methodological note on the timescale shift, disclosed rather than smoothed over.**
Round 1's (non-flat-baseline) version of this test found `Cruise_Throttle`'s median onset at
~100ms. Here, after requiring a flat baseline, the median onset is **449.6ms** — over 4x
later. This is an expected and unavoidable consequence of the filter: selecting for events
with *no* prior drift necessarily selects for a different, slower-building subpopulation of
real-world lead-acquisition events (a car gradually closing rather than an abrupt cut-in),
not a methodology bug. It does mean this test's "impulse" is less sharp than the design
aimed for, which plausibly contributes to the muddier result.

## Secondary: lead-lost events (unfiltered, n=858, not subject to the flat-baseline filter)

Reported for continuity with round 1, per pre-registration — this was never the primary
endpoint and carries no CONFIRM/NULL verdict of its own.

| comparator | n_usable | median margin | CT-first (any) | CT-first ≥50ms |
|---|---|---|---|---|
| `throttle_body` | 463 | 49.59ms | 60.04% | 49.24% |
| `wheel_torque` | 459 | 29.9ms | 51.63% | 47.49% |
| `engine_rpm_140` | 255 | 199.66ms | 69.02% | 65.49% |

Same qualitative shape as the primary result: `throttle_body` weakly favors a CT lead,
`wheel_torque` is close to chance. Consistent with round 1's own lead-lost numbers
(59.5% / 46.7%), i.e. the flat-baseline filter did not materially change this unfiltered
population's behavior, which is expected since the filter was never applied to it.

## Rejection funnel (282 routes, 0 errors, 5,583 raw `Car_Follow` transitions)

```
driver_gas            691
not_isolated         2583
acc_dropped            370
driver_brake           201
baseline_not_flat      683   <- the new pre-registered filter
no_real_response         62
ct_pinned_at_floor       17
not_sustained             2
                     -----
qualifying (acquired)   116
```

The flat-baseline filter (`baseline_not_flat`) rejected 683 of the ~800 acquired-direction
candidates that survived the earlier gates — roughly an 86% rejection rate, close to what a
40-route smoke sample predicted (a ~92% rejection rate on n=38). **The power floor was
cleared, but not by a wide margin** (116 vs. the 100 floor) — a materially smaller effective
sample than round 1's unfiltered 814, exactly the tradeoff the pre-registration anticipated
("could plausibly cut it by 10x").

## What this does and does not establish

**Does not confirm H1. Does not kill it. Genuinely INCONCLUSIVE**, per a mechanical
threshold applied exactly as written down beforehand — no post-hoc adjustment was made,
including the acknowledged-but-uncorrected ~25ms quantization bias (which, if corrected,
would only move this result *toward* CONFIRM, which is exactly why it was pre-committed not
to be corrected).

**G1 stands.** Even a full CONFIRM here would only have shown that `Cruise_Throttle`'s
onset reliably precedes the powertrain's on a perception-triggered event — consistent with
either "the ECU obeys this field" or "EyeSight commands the ECU some other way and
independently publishes this field slightly ahead of the visible result." This test, like
every archive test before it, cannot resolve that distinction. It also could not resolve it
this time regardless, since the result itself is inconclusive.

**One real, disclosed weakness of this specific test design**, useful if anyone revisits it:
the `wheel_torque` vs `throttle_body` disagreement suggests 116 events may simply not be
enough to average out route-to-route and event-to-event noise for a signal whose true effect
size (if any) is on the order of the ES message's own 50ms quantization. A future version
would need either a much larger qualifying N (a bigger archive, or a looser flat-baseline
threshold traded against re-introducing some of round 1's contamination) or a fundamentally
different, higher-time-resolution trigger than a 20Hz binary flag.
