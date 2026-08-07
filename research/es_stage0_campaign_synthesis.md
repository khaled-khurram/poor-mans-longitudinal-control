# Q14 archive-exhaustion campaign: final synthesis

**Date: 2026-08-07 (overnight session). Fully passive, zero CAN transmission, zero device
access, throughout every round below.** This document rolls up the entire Stage 0 archive
investigation into `ES_Distance.Cruise_Throttle` / `ES_Status.Cruise_RPM` /
`ES_Brake.Brake_Pressure` as a real longitudinal command channel: the original pre-registered
run, its follow-up, and five subsequent rounds of an autonomous, self-directed campaign that
each built on the previous round's findings. Source documents, in chronological order:

1. `research/es_longitudinal_command_results.md` — original Stage 0 run (T0–T9)
2. `research/es_stage0_followup_results.md` — C5, dedup, T5 stratification, first perception-trigger attempt
3. `research/es_stage0_prereg_round2.md` — pre-registration for the fixed perception-impulse design + the capture-drive design (Test B)
4. `research/es_stage0_round1_testA_results.md` — Round 1: `Cruise_Throttle` perception-impulse retest
5. `research/es_stage0_round2_rpm_prereg.md` + `research/es_stage0_round2_rpm_results.md` — Round 2: `Cruise_RPM` perception-impulse test
6. `research/es_stage0_round3_brake_prereg.md` + `research/es_stage0_round3_brake_results.md` — Round 3: `ES_Brake` wide-lag + perception test
7. `research/es_stage0_round4_crossfield_results.md` — Round 4: detection-confound check, cross-field structure
8. `research/es_stage0_round5_envelope_completion_results.md` — Round 5: `Cruise_RPM` transfer curve, boundary-clip resolution, grade correction

---

## The bottom line, stated first because it inverts the original framing

**The one field that produced a clean CONFIRM is the one field that isn't TX-allowed today.**
`ES_Brake.Brake_Pressure` — which requires a panda safety-firmware change before it could
ever be written on this car — is the *only* one of the three ES fields where the
perception-impulse test (the one method in this entire campaign capable of reaching past the
G1 identifiability ceiling) came back a clean, unanimous CONFIRM. The two fields that are
**already TX-allowed and writable today with zero firmware change** —
`Cruise_Throttle` (the field the whole investigation was originally built around, per
`research/eyesight_throttle_channel.md`'s "day one, no firmware change needed" framing) and
`Cruise_RPM` — came back **INCONCLUSIVE** and a **clean NULL**, respectively.

This is not a minor footnote. It cuts directly against the practical premise that motivated
this entire line of investigation: the field that's cheapest to write is the field the
evidence is weakest for, and the field the evidence is strongest for is the one that's
expensive to write. Anyone deciding what to do next needs to sit with that tension, not route
around it.

---

## Full pattern across all three fields, every test type

| | `Cruise_Throttle` (H1) | `Cruise_RPM` (H3) | `Brake_Pressure` (H2) |
|---|---|---|---|
| **TX-allowed today?** | Yes (already the channel Q6/Q10 proved obeyed for `Cruise_Button`) | No — needs firmware | No — needs firmware |
| **K1 exact-copy kill test** | Does not fire, any regime/field/lag | Came within 0.0085 of firing, wrong direction to count (command side) | Never approached (checked via T2's original matrix) |
| **Wide-lag correlation shape** | Broad, ambiguous hump, R²≈0.45–0.55 everywhere, *minimum* at zero lag | Sharp interior peak, R²=0.9905 at +400ms, worst point still 0.916 | **Sharpest peak of the three**, R²=0.978 at +100ms, worst point 0.43–0.46 |
| **Perception-impulse verdict** | **INCONCLUSIVE** (61.8% vs 70% needed; margin cleared its own bar; undercut by a disagreeing secondary comparator) | **NULL** (45.1%, 0ms margin — clean, both conditions fired; reverses its own strong correlation) | **CONFIRM** (100% across 4 independent comparators, ~500–900ms margins, unanimous) |
| **Transfer curve vs aEgo** | Clean, monotonic, floor→−0.66, peak→+0.50 m/s² | Clean, monotonic, similar shape, plateau not sharp peak | Cleanest of the three, near-linear, slope within ~4% of global's exact constant |
| **Does global's encoding transfer?** | Anchors yes (808/1818, sharpened by grade correction to ~1850≈1818), range no (measured ceiling ~3750 vs global 3400) | **No anchor transfers** — 600 vs measured ~1900–2000 (3x off), 3600 vs measured ~2600–3300 (lower, not higher) | Anchors and slope both transfer closely (~4% of global's brake constant) |

**No simple rule predicts this pattern.** "Strongest correlation wins" fails (`Cruise_RPM`
had the strongest population-level signal of the three and produced a NULL). "Weakest
correlation loses" fails too (`Cruise_Throttle`'s weak, ambiguous correlation still survived
every kill test and produced an inconclusive near-miss rather than a clean NULL). The
perception-impulse verdict and the aggregate wide-lag correlation strength are measuring
genuinely different things, and this campaign is the direct demonstration of that — most
sharply in Round 2, where `Cruise_RPM`'s R²=0.99 population correlation and its 45.1%
event-level race outcome are both real, simultaneously, and describe different properties of
the same field.

---

## What's now well-established (stands regardless of what happens next)

- **`Cruise_Throttle` is inert during ACC-off** (C5): 4 distinct values across 122,037
  samples, 99.98% at 808, while the engine's real throttle is certainly moving freely. Kills
  the entire "echo of an engine signal" hypothesis class outright, for all three fields by
  extension (none showed anything resembling this during the campaign). Does not touch
  "report of EyeSight's own internal demand" — that ambiguity (G1) is untouched by this
  finding and remains the live question.
- **The main-bus relay of `ES_Distance` is highly faithful** (T9): 98.67% exact match,
  99.06% clean counter increments, ~3ms median relay delay — contrary to the design doc's
  pre-run speculation that it would degrade "regularly."
- **`ES_Brake.Brake_Pressure`'s encoding transfers almost exactly from global** — slope within
  ~4% of the documented constant, on a field nobody has ever written on this car. If `ES_Brake`
  is ever added to the TX allowlist, the scaling is very unlikely to need local re-derivation.
- **`Cruise_Throttle`'s anchors transfer, its range doesn't — and grade correction sharpens
  this rather than complicating it.** The floor (808) and zero-crossing (originally reported
  as "~1800–2000, near but not exact") were shown in Round 5 to land almost exactly on
  global's 1818 once a real, quantified per-route grade/rolling-resistance bias
  (median −0.198 m/s², real route-to-route variation) is removed. The ceiling still does not
  transfer (measured ~3750–3800 vs global's 3400) — any future control law needs a
  locally-measured ceiling regardless of this correction.
- **`Cruise_RPM`'s operating envelope, measured for the first time, transfers *nothing* from
  global** — not the inactive anchor (600 vs measured ~1900–2000), not the ceiling (3600 vs
  measured ~2600–3300, which is *lower* than global's spec, not higher like `Cruise_Throttle`'s
  case). A stronger self-calibration warning than any other field produced.
- **`SubaruStopAndGo` (or an equivalent mechanism) is continuously active on this device**
  across the entire archive — fabricated `Throttle`/`Brake_Pedal` frames toward the camera bus
  at within a few percent of the real main-bus rate for the same addresses, not brief resume
  bursts as prior research assumed. An operational fact for any future risk assessment,
  independent of the command-vs-report question.
- **`Cruise_Throttle` and `Cruise_RPM` are decoupled from each other**, at every lag tested,
  even restricted to active-braking windows — a real, if secondary, architectural finding
  about how these fields relate to each other internally.

---

## What's still genuinely unresolved

**G1 — the identifiability ceiling — stands for all three fields, including the one CONFIRM.**
A CONFIRM on the perception-impulse test shows that a field's onset reliably precedes the
*physical sensors it's compared against* on a genuine exogenous trigger. It does not and
cannot show that the vehicle's actuation ECU *obeys* that CAN field, as opposed to EyeSight
computing and publishing the field while commanding the actuator through some other,
unobserved channel that happens to correlate with it. This is true even for `ES_Brake`'s
clean CONFIRM — Round 3's own writeup states this caveat explicitly, while also noting it is
*weaker* there than for `Cruise_Throttle`/`Cruise_RPM`: no alternative CAN-based
braking-command channel has been identified anywhere in this project's research, whereas for
throttle a concrete alternative (the ECU's own independent speed-following loop, with
`Cruise_Throttle` as EyeSight's internal telemetry only) remains live and unfalsified.

**Two loose threads, closed with negative characterizations, not left open:**
- `Cruise_RPM` vs `Brake_Pressure`, extended to ±3s in Round 5, is U-shaped with a genuine
  interior minimum and never converges — the same "slow shared trend, not a fast causal link"
  signature already established for `Cruise_Throttle`/`Throttle_Cruise`. Read as evidence
  the two fields co-vary with braking-episode severity/duration, not evidence of a fast
  internal link. Not chased with a wider grid; the shape is already diagnostic.
- Round 4's cross-field test of `Cruise_Throttle` against the other two fields during active
  braking came back underpowered by an unrelated fact (`Cruise_Throttle` is pinned at 808 in
  89% of that specific window, per the already-established T6 finding) rather than by a
  clean null — correctly reported as INCONCLUSIVE rather than false independence.

**Two structural data gaps that no further archive mining can fix:**
- **G7:** `CVT_Ratio` (`0x149`) has zero decoded signals anywhere in the DBC, so the
  "does engine RPM jump for transmission-ratio reasons independent of `Cruise_RPM`'s demand"
  confound can never be tested with this archive's data.
- **G9:** the brake (and now RPM) transfer curves are sampled only at whatever pressures/RPMs
  EyeSight happened to command during real archived drives — coverage near the physical
  ceilings is thin by construction. Only a deliberate capture drive with some harder
  braking/acceleration fixes this.

---

## Methods retrospective — the campaign's own bugs, found and fixed in the open

Worth recording as a set, since several recur as a pattern (repeatedly finding and disclosing
real bugs rather than quietly patching them is the reason any of the verdicts above are
trustworthy):

- **K1's exact-match branch had no variance floor**, letting a near-constant field
  (`esb_brake_pressure` pinned at 0 during `acc_off`) trivially "exact-match" any other
  near-constant field with R²=0 — a false positive, caught, and fixed with an `es_std ≥ 5`
  guard, confirmed to never have affected `Cruise_Throttle`.
- **The first perception-trigger test (`research/es_perception_focus.py`) had a design flaw,
  not a bug**: `Car_Follow` is a thresholded flag on a continuous internal estimate, so the
  flag flip is not an exogenous impulse, and the onset detector's own baseline window was
  contaminated by the pre-flip response. Diagnosed from the traces, fixed with a flat-baseline
  filter in Round 1 onward.
- **Round 2's first RPM perception script had a real bug**: the 20Hz tick-clock address
  (`ES_Distance`) was never added to its own decoder table, so every tick got silently
  filtered before the drain loop ever ran — `n_acc_engaged_clean_ticks=0`. Caught immediately
  by checking the output rather than trusting a clean exit code, fixed, re-run.
- **Smoke-sample linear extrapolation undershot the true full-archive N in at least three
  separate instances** (Round 2's RPM test: 40→9, 100→28, both projecting well under the true
  107; Round 3's brake test: 40-route sample projected ~28, true count was 73 — 2.6x higher).
  This is now a confirmed, general property of this specific archive/pipeline, not a one-off:
  **a smoke sample projecting below a power floor is not sufficient grounds to skip the full
  run**, and every round from Round 2 onward ran to completion rather than trusting a
  projection.
- **A confound check that came back negative was reported as negative** (Round 4, Component
  1: does `ES_Brake`'s CONFIRM reduce to an easier-detection artifact? The data available
  argue weakly against that explanation, not for it — the physical-magnitude trend runs
  backwards from what the confound predicts) rather than being quietly dropped or spun.

---

## What archive analysis can and cannot do from here

**The honest case for stopping here:** the perception-impulse method — the only test type in
this campaign that can reach past G1 — has now been run on all three ES fields, following the
same rigor (pre-registered before running, mechanical decision rules, honest reporting of
near-misses and disagreements). It produced one INCONCLUSIVE, one clean NULL, and one clean
CONFIRM, and two follow-up rounds specifically interrogated whether the CONFIRM should be
trusted (it should, modestly). The two remaining loose threads (`Cruise_RPM`/`Brake_Pressure`'s
slow shared trend, and the underpowered `Cruise_Throttle` cross-field check) both resolved to
clean negative characterizations, not to "needs more archive mining." The two permanent gaps
(G7, G9) are structural — no amount of additional passive analysis of this archive can touch
them, because the data simply isn't there (CVT_Ratio was never decoded; the archive never
happened to contain enough hard-braking/high-RPM samples).

**This is diminishing returns, not exhaustion in a stronger philosophical sense** — there is
always some new correlation or stratification one could try — but every remaining thread
identified during this campaign either terminated in a clean negative or in a structural
data gap. That is a meaningfully different, more complete state than where the investigation
stood after the original Stage 0 run alone.

**Two genuinely useful next steps, and both are physical:**

1. **Test B, already pre-registered** (`research/es_stage0_prereg_round2.md`): the deliberate
   capture drive testing whether gas overrides from mid-range `Cruise_Throttle` (2600–3100)
   produce ≥60% opposite-sign responses, with a committed-in-advance rule that a falsified or
   inconclusive result discards the round-1 stratification finding as noise. Stock,
   unmodified ACC — nothing armed, modified, or transmitted.
2. **A version of the perception-impulse test adapted for a deliberate drive rather than
   archive mining.** The method's power throughout this campaign was consistently limited by
   how rarely a sufficiently clean, isolated, flat-baseline lead-acquisition event occurs
   naturally in ordinary recorded driving (Round 1's flat-baseline filter alone rejected ~86%
   of otherwise-qualifying candidates). A driver who can deliberately produce clean, isolated
   cut-in events from a stable cruise baseline — on any of the three ES fields, but especially
   `Cruise_Throttle` and `Cruise_RPM` given their weaker archive verdicts — could plausibly
   generate a much higher-quality dataset in an hour than 282 routes of incidental driving
   did. This was not pre-registered anywhere in this campaign and would need its own fixed
   criteria, written before driving, following the same discipline as everything above.

**Neither of these authorizes a live write.** Both are still purely observational — stock ACC
behavior, logged passively. G1 will still stand after either one, for the same reason it
stands now: no observational test, archive or drive, can distinguish "the ECU obeys this
field" from "EyeSight computes and publishes this field while commanding the actuator some
other way that happens to correlate with it." That distinction requires an actual write, and
nothing in this document is a recommendation to make one.
