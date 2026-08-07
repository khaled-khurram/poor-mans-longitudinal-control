# Round 2 results: perception-impulse retest for `Cruise_RPM` — NULL

**Date: 2026-08-07. Fully passive archive analysis, zero CAN transmission, zero device
access.** Executed exactly per `research/es_stage0_round2_rpm_prereg.md`, committed before
this test's script or data existed. Script: `research/es_perception_flatbase_rpm_test.py`.
Results: `research/es_perception_flatbase_rpm_results.json`.

## Verdict: **NULL**

Applied mechanically, no tuning:

```
frac_rpm_first_50 = 45.1%   (NULL fires if <= 50%)
median_margin      = 0.0ms  (NULL fires if <= 25ms)
n = 107                     (clears the N>=100 power floor)
```

**Both of the independent NULL conditions fired — this is not a borderline call.** `Cruise_RPM`
does not lead `Transmission_Engine` on a perception-triggered event. The two signals move
essentially simultaneously: median onset latency for `Cruise_RPM` was 400.73ms after the
`Car_Follow` flip, for `Transmission_Engine` 375.09ms — 25ms apart, i.e. within a single
20Hz ES tick of each other. The win/lose split (49.0% `Cruise_RPM` first, before the ≥50ms
solidity filter) is close to a coin flip and, after requiring a real ≥50ms margin, tips
slightly the other way (45.1%).

## Power floor — cleared, but only just, and the pre-registration's own honesty check earned its keep

The smoke-sample check specified in the pre-registration was run before committing to the
full pass, exactly as planned: 40 routes → 9 qualifying events, 100 routes → 28 — both
extrapolating to well under 100 over the full archive (63 and 79 respectively). The
pre-registration required running to completion for the real number rather than stopping on
an extrapolation, which was the right call: the actual full-archive yield (107) landed
*above* the floor despite both smoke extrapolations sitting below it, meaning event density
was not uniform across the route ordering. Recorded as a methods note: extrapolating from
early-route smoke samples in this archive is not reliable, and the honest thing (already
built into the pre-registration) was to run to completion rather than trust the projection.

`Cruise_RPM`'s own flat-baseline filter rejected candidates at a similar rate to
`Cruise_Throttle`'s in Round 1 (`baseline_not_flat`: 174 of ~2,700 gate-eligible candidates,
plus 587 `no_real_response`) — comparable selectivity to Round 1's ~86% rejection, not a
looser filter producing an artificially large N.

## What this means, set against the prior wide-lag correlation result — the important part

This is the most consequential single finding of Round 2, and it complicates rather than
simply extends the earlier work. The prior wide-lag correlation
(`research/es_rpm_focus.py`, reported in `progress.md`'s Q14 addendum) found a **sharp,
well-resolved interior peak at lag=+400ms** (R²=0.9905) between `Cruise_RPM` and
`Transmission_Engine`, on the command side of zero lag — and that result was explicitly
read as *"the transmission appears to track `Cruise_RPM`'s demand with a ~250–400ms lag"*,
reversing the pre-registered "duplicate/report" prediction.

**The perception-impulse test does not reproduce that lead on genuine, isolated,
exogenously-triggered events.** On the 107 clean perception-triggered responses collected
here, the two signals move together with essentially zero margin, not the ~400ms separation
the aggregate correlation implied.

**These two results are not necessarily contradictory, and the honest reading requires
holding both at once rather than picking a winner:**

- The wide-lag correlation is a **population-level, aggregate statistic** over ~2.1 million
  ticks of ordinary driving — it finds the lag that best aligns two *slowly co-varying*
  signals across the whole dataset. A ~400ms aggregate-optimal lag is compatible with the
  two signals being tightly, near-instantaneously linked at the event level if there is also
  a slower, systematic phase relationship in how each is filtered or computed internally
  (analogous to the broad-hump, slow-common-trend finding already documented for
  `Cruise_Throttle` vs `Throttle_Cruise` — a real correlation whose optimal lag reflects
  smoothing dynamics, not a fixed causal delay applicable to any single event).
- The perception test is **event-level and exogenously triggered** — it measures what
  happens right after a specific, isolated moment neither signal chose, which is the more
  direct test of causal ordering. It says: whatever produces the aggregate +400ms
  correlation, it is not "`Cruise_RPM` moves first and the transmission needs ~400ms to
  catch up" on an actual surprise.

**Net effect on the Q14 record: the "command-direction" framing from the wide-lag result
should be treated as weaker than the prior writeup stated, and this document is the
correction.** `Cruise_RPM` remains the most tightly powertrain-*correlated* of the three ES
fields by every aggregate measure — that finding stands, R²=0.99 is real. But "most tightly
correlated" and "leads causally" have now been shown to be different claims for this field,
and only the first one survives contact with an exogenous-trigger test. This is the same
epistemic lesson Round 1 delivered for `Cruise_Throttle` (weak lead/lag despite surviving
the echo kill test) arriving from a different direction: a field can be real, powertrain-
coupled, and *not* demonstrably command-first, simultaneously.

## Secondary comparator (`engine_rpm_140`) — descriptive only, per pre-registration

`frac_cruise_rpm_first_by_50ms_or_more` = 48.45%, median margin 40.46ms — also near chance,
consistent with the primary result. Not used for the verdict, reported for completeness.

## Illustrative trace (one of 9 acquired, flat-baseline-qualified events)

```
  dt_ms   Cruise_RPM   Car_Follow   Trans_Engine
   -300      2413           0           2407
   -100      2410           0           2405
    -50      2404           0           2405
      0      2399           1           2406    <- flag flips
    100      2388           1           2407
    200      2381           1           2400
    400      2355           1           2385
    900      2335           1           2367
```

Both decline smoothly after the flip, `Cruise_RPM` moving somewhat faster in raw counts
early on — but this is one of only 9 acquired traces retained and is not representative of
the aggregate margin (which nets to ~0ms across all 107). Included for concreteness, not as
evidence beyond the mechanical verdict above.

## What this does and does not establish (G1 restated)

A NULL here does not mean `Cruise_RPM` is a report and does not mean it isn't a command —
G1 (the identifiability ceiling) still applies. It means: on this specific, well-powered,
exogenously-triggered test, `Cruise_RPM` does not demonstrate the kind of causal precedence
that would make "command" the clearly favored reading. Combined with Round 1's INCONCLUSIVE
on `Cruise_Throttle`, the perception-impulse approach has now been tried on the two most
promising ES fields and has not produced a clean CONFIRM on either. That is itself useful
information about the limits of what this archive can settle, not merely a null result to
discard.
