# Pre-registration, round 2: the perception-impulse retest and the deliberate capture drive

**Written 2026-08-07, BEFORE either test has been run or the data for them collected.**
That is the entire point of this document. Round 1's stratification finding
(`es_stage0_followup_results.md` §3) was chosen *after* seeing the data it was applied to,
which is why it was recorded as hypothesis-generating only. These two tests exist to convert
that into something that can actually count as evidence — which requires fixing the
criteria now, in writing, before looking.

**Rules for both tests, binding:**
1. **Do not tune the thresholds below to make a result come out.** If one is genuinely
   wrong, say so explicitly in the writeup and re-register it — do not silently edit.
2. A test that fails its power floor reports **INCONCLUSIVE, not KILL**. An absent result is
   not evidence of absence.
3. Neither test authorizes any CAN transmission, code change, arming, or device deploy.
   Test A is archive analysis. Test B is ordinary driving with **stock, unmodified** ACC.
4. Even a full CONFIRM on both does **not** establish that the ECU obeys `Cruise_Throttle`.
   G1 (the identifiability ceiling) is unaffected by either. See §3.

---

## Test A — the perception-impulse retest (archive, zero risk)

### Why round 1 failed, restated in one line

`Car_Follow` is a *thresholded flag on a continuous internal estimate*: `Cruise_Throttle` was
already responding ~300ms before the bit flipped, so the flip was not an exogenous impulse,
and the onset detector's baseline window was contaminated by the response itself.

### The fix

Select only events where `Cruise_Throttle` is **provably flat through the entire baseline
window** — i.e. genuine surprises (an abrupt cut-in) rather than gradual overtakes where
EyeSight has been reacting for seconds already. This simultaneously restores the impulse and
decontaminates the baseline.

### Event definition — FIXED NOW

An event qualifies iff **all** of:

1. `Car_Follow` transitions `0 → 1` (lead acquired). **Lead-lost events are excluded from
   the primary endpoint** — round 1 showed them to be slower and messier (median CT onset
   422ms vs 100ms), and mixing two response types was a design weakness. They are analysed
   separately as a secondary endpoint only.
2. **Flat-baseline requirement (the new one):** over `[-1000ms, -50ms]`, `Cruise_Throttle`'s
   peak-to-peak range is **≤ 30 counts**. *Rationale, so this is not mistaken for an
   arbitrary pick:* the onset threshold for `Cruise_Throttle` is 40 counts, so a ≤30-count
   baseline is by construction one that contains nothing the detector would itself call an
   onset. The number is derived from the existing detector, not chosen to yield a result.
3. **Real response required:** `|Δ Cruise_Throttle|` ≥ 40 counts somewhere in
   `(0, +1200ms]`. Without a response there is no onset to order.
4. All round-1 cleanliness gates unchanged: ACC engaged throughout; **no driver gas or brake
   anywhere in `[-1000ms, +1200ms]`**; no `Cruise_Fault`; the transition isolated by ±2s from
   any other `Car_Follow` transition; the new state sustained ≥1s; `Cruise_Throttle` not
   pinned at the floor.
5. Onset thresholds **identical to every prior run** — `es_cruise_throttle` 40,
   `throttle_body` 2.0, `wheel_torque` 20.0, `engine_rpm_140` 30.0, `aego` 0.15,
   `throttle_cruise` 2.0. Detector unchanged (first sample departing baseline by more than
   `max(3σ, min_abs_change)`).

### Primary endpoint — ONE number, fixed now

**`frac_ct_first_50` = fraction of qualifying events where `onset(Cruise_Throttle)` precedes
`onset(throttle_body)` by ≥ 50ms.**

`throttle_body` is the comparator because it is the fastest, most direct physical actuation
signal. **`engine_rpm_140` is excluded from the primary endpoint by pre-registration**, for
the reason documented in round 1: it is slow and CVT-decoupled, `throttle_body` beats it by
~280ms too, so a large margin against it carries no command-vs-report information. It is
reported as a descriptive secondary only, and **may not be quoted as the headline**.

| outcome | criterion |
|---|---|
| **CONFIRM** | `frac_ct_first_50` ≥ **70%** AND median margin ≥ **75ms** |
| **NULL / KILL-side** | `frac_ct_first_50` ≤ **50%** (no better than chance) OR median margin ≤ **25ms** |
| **INCONCLUSIVE** | anything between, or N below the power floor |

### Power floor — fixed now

**N ≥ 100 qualifying events.** Below that: INCONCLUSIVE regardless of the numbers. Round 1
yielded 814 lead-acquired events before the flat-baseline filter; the filter's yield is
genuinely unknown and could plausibly cut it by 10x, which is exactly why this floor is
written down first.

### Pre-specified analysis decisions (so they can't be made post-hoc)

- The **~25ms quantization bias** (ES is 20Hz, so CT's detected onset is on average ~25ms
  late relative to truth, biasing *against* finding a CT lead) is acknowledged but
  **NOT corrected for**. Adjusting an inconclusive result in the hoped-for direction is
  precisely how this goes wrong.
- Secondary endpoints, reported but not decisive: same statistic vs `wheel_torque`; the
  lead-lost subset; the distribution of `ct_before`.
- No further stratification of the primary endpoint. If a subgroup pattern appears, it is
  a round-3 hypothesis, not a round-2 result.

### Pre-registered expected outcome (recorded before running)

**INCONCLUSIVE is the most likely single outcome (~50%), CONFIRM ~25%, NULL ~25%.** The
binding constraint remains the 20Hz ES rate; the flat-baseline filter improves the impulse
quality but does not improve timing resolution, and round 1's margins were 20–49ms against a
50ms floor. Recording this pessimism now so a CONFIRM, if it happens, is not retrofitted
into "as expected."

---

## Test B — the deliberate capture drive (zero risk, stock ACC only)

### What this tests

The one falsifiable prediction round 1 produced: `es_stage0_followup_results.md` §3 found
that gas overrides starting from **mid-range** `Cruise_Throttle` (2600–3100) moved
`Cruise_Throttle` *opposite* to the driver-caused engine increase in 69% of maneuvers
(n=13) — a signature a report of powertrain state physically cannot produce. That was
post-hoc and underpowered. This drive tests it prospectively.

### Prediction — FIXED NOW

**Among override maneuvers initiated while `Cruise_Throttle` is in [2600, 3100], the
fraction where `Δ Cruise_Throttle` and `Δ Throttle_Body` have opposite signs (measured
−100ms → +1500ms, the identical window and definition used by the original T5) will be
≥ 60%.**

| outcome | criterion |
|---|---|
| **PREDICTION CONFIRMED** | opposite-sign fraction ≥ **60%** |
| **PREDICTION FALSIFIED** | opposite-sign fraction ≤ **40%** |
| **INCONCLUSIVE** | between 40% and 60%, or N below the power floor |

**If the prediction is falsified or inconclusive, §3 of the round-1 writeup is to be
discarded as noise** and marked as such in `progress.md`. That commitment is made here, in
advance, so the finding cannot survive on the strength of having been interesting.

### Power floor — fixed now

**N ≥ 30 independent maneuvers in the 2600–3100 band**, where "independent" means separated
by ≥ 5s (the same deduplication rule that reduced round 1's 283 raw events to 66 real ones).
Target ≥ 50 to leave margin. Below 30: INCONCLUSIVE.

### Drive protocol

**Nothing is modified, armed, or transmitted. This is stock ACC plus ordinary use of the
gas pedal, logged passively — the car behaves exactly as it does on any normal drive.**

1. Stock ACC engaged, steady cruise, level road, no lead vehicle (or a distant, stable one),
   speed steady enough that `Cruise_Throttle` settles in the 2600–3100 band. Per the T7
   transfer curve this corresponds to roughly zero to slightly positive acceleration, which
   is ordinary highway cruising.
2. Apply a **brief, moderate** gas press — enough to raise `Throttle_Body` clearly above
   baseline — hold ≥1s, then release cleanly to zero.
3. Wait ≥10s for the system to resettle before the next one (comfortably beyond the 5s
   independence rule).
4. Repeat ≥30, ideally ≥50 times. Vary speed and grade across the set rather than doing all
   of them in one identical condition.
5. Also collect ≥20 maneuvers starting from **near the floor (`Cruise_Throttle` ≈ 808)** as
   the built-in control group: round 1 predicts these will look *same-sign* (the delayed
   state-transition behavior). Both bins moving the same direction would indicate the
   round-1 stratification was an artifact.

Note conditions informally (road, rough speed, grade) — no GPS traces needed or wanted, per
the repo's scrubbing rules.

### Why this drive is worth doing regardless of Test A

The archive is opportunistic; it contains whatever driving happened to occur, which is why
the decisive bin ended up at n=13. A single deliberate hour produces more usable
mid-range override events than the entire 282-route archive did, at zero risk. It is the
highest-value data-collection action available and it does not depend on Test A's outcome.

---

## 3. What neither test can establish — restating G1, because it still binds

Both tests measure whether `Cruise_Throttle` behaves like EyeSight's *own independent
demand* rather than a powertrain echo. **Neither can show that the engine ECU obeys it.**

"EyeSight commands the engine via `0x161`" and "EyeSight commands the engine some other way
and *also* publishes its internal demand on `0x161`" produce identical archive signatures and
identical capture-drive signatures. Round 1 already narrowed the space usefully — C5's result
(inert during ACC-off across 122,037 samples) kills the "echo of an engine signal" class
outright — but the surviving ambiguity is precisely the one that determines whether writing
the field would do anything, and it is not reachable by observation.

**A full CONFIRM on both tests therefore raises the prior and does not close the question,
and specifically does not constitute authorization for a live write.** The next step after
these, if both confirm, remains a design review — including the two prerequisites round 1
surfaced: there is currently **no panda `tx_hook` value check of any kind** on `ES_Distance`
(so the veto-only rule lives entirely in Python with nothing beneath it), and T8 showed
`Cruise_Throttle`/`Cruise_RPM` are tightly co-varying, so a throttle-only write would create
combinations the ECM may never have seen.
