# Combined capture-drive protocol: Test B + Test C

**Written 2026-08-07, before any capture drive has happened.** Committed to the repo before
driving, same discipline as every round this campaign — the decision criteria exist in
writing before the data that will be judged against them.

**Scope reminder, unconditional: this is 100% stock, unmodified ACC. Nothing is armed,
patched, or transmitted. The car behaves exactly as it does on any ordinary drive — this
document is entirely about *which ordinary, legal, safe maneuvers to prioritize* and roughly
how many, not about changing anything on the vehicle.** Data collection is automatic (the
existing comma-device rlog pipeline, already syncing to the same archive every round tonight
mined) — no new logging, no button presses, no manual event-marking. Drive with intent, let
the device record as it always does, then re-run the existing scripts against the new
routes once they sync.

**Safety overrides everything below.** Every maneuver description here is qualified by "only
if it's already safe and legal in the traffic you actually have" — never create a tight
following distance, an unsafe lane change, or cut off another driver to manufacture a data
point. If a target maneuver isn't available safely, skip it; the analysis scripts only score
maneuvers that pass their own gating (no driver brake, ACC engaged throughout, etc.), so a
skipped rep costs nothing but is never worth forcing.

---

## Part 1 — Test B: the mid-range gas-override drive

Already fully pre-registered in `research/es_stage0_prereg_round2.md` §Test B. Not
re-litigated here — this is the actionable checklist version of that spec.

**What it's testing:** the one falsifiable, *not-pre-registered* prediction from
`research/es_stage0_followup_results.md` §3 — that gas overrides starting from
`Cruise_Throttle` ∈ [2600, 3100] move `Cruise_Throttle` *opposite* the driver-caused engine
increase (a signature a report can't produce) in ≥60% of maneuvers. The archive gave this
n=13. This drive is powered to give it n≥30.

**Checklist:**

1. Stock ACC engaged, steady cruise, level road, no close lead vehicle. Hold a speed where
   `Cruise_Throttle` settles in **2600–3100** (per the T7 transfer curve, this is roughly
   zero-to-mild acceleration — ordinary highway cruise, not aggressive).
2. Brief, moderate gas press — clearly above baseline — hold **≥1s**, release cleanly to
   zero.
3. Wait **≥10s** before the next one.
4. Repeat **≥30 times, target ≥50**, in the 2600–3100 band. Vary speed/grade across reps
   rather than repeating one identical condition.
5. Also collect **≥20 reps from near the floor** (`Cruise_Throttle` ≈ 808 — e.g. right after
   a coast-down or just after ACC re-engages) as the built-in control group. Round-1
   analysis predicts these look *same-sign* (a delayed state-transition, not an echo) —
   both bins moving the same direction would mean the round-1 finding was noise.

**Decision rule (fixed, from the existing pre-registration):** opposite-sign fraction ≥60% =
confirmed, ≤40% = falsified, between = inconclusive. **If falsified or inconclusive, the
round-1 §3 finding gets marked discarded-as-noise in `progress.md` — that commitment was
already made in writing before this drive exists, and it stands.**

**Estimated time:** 30–60 minutes of focused driving, depending on how quickly the
2600–3100 band is reachable and re-reachable between reps.

---

## Part 2 — Test C: the capture-drive perception-impulse test (NEW pre-registration)

### Why this needs its own drive, not just more archive mining

Both archive-based perception tests (`research/es_stage0_round1_testA_results.md`,
`research/es_stage0_round2_rpm_results.md`) were power-limited by the same cause: `Car_Follow`
is a threshold on a *continuous* internal estimate, so most real lead-acquisitions are gradual
— the flat-baseline filter (which selects for genuine abrupt surprises, the only kind that
gives a valid exogenous impulse) rejected **~86%** of otherwise-qualifying candidates. Out of
282 routes' worth of ordinary driving, only 116 (`Cruise_Throttle`) and 107 (`Cruise_RPM`)
qualifying events survived. **A deliberate drive can raise the fraction of genuinely abrupt
lead-acquisitions well above what ordinary incidental driving produces**, by choosing
maneuvers that create a *new, close* lead in one motion rather than gradually closing on a
distant one.

### What's reused verbatim, and why that matters

Same script family (`research/es_perception_flatbase_test.py` for `Cruise_Throttle`,
`research/es_perception_flatbase_rpm_test.py` for `Cruise_RPM`), same flat-baseline filter
(peak-to-peak ≤30 counts over `[-1000ms, -50ms]` for `Cruise_Throttle`; the analogously
derived value for `Cruise_RPM`), same primary comparators (`throttle_body` for
`Cruise_Throttle`, `trans_engine` for `Cruise_RPM`), same decision thresholds:

| outcome | criterion |
|---|---|
| **CONFIRM** | `frac_first_by_50ms_or_more` ≥ **70%** AND median margin ≥ **75ms** |
| **NULL** | `frac_first_by_50ms_or_more` ≤ **50%** OR median margin ≤ **25ms** |
| **INCONCLUSIVE** | anything between, or N below the power floor |

**Reusing the exact same numbers is itself a methodological choice, stated explicitly:**
this is not a fresh test with fresh thresholds chosen to flatter a hoped-for outcome — it is
the *same* test, run on better-curated data. A different verdict on the same criteria is
directly comparable to Rounds 1–2's archive results, not a new goalpost.

**Fields covered: `Cruise_Throttle` (primary) and `Cruise_RPM` (secondary).**
`ES_Brake.Brake_Pressure` is **not** re-tested here — it already got a unanimous clean
CONFIRM from the archive (N=73, 4/4 comparators, `research/es_stage0_round3_brake_results.md`)
and isn't TX-allowed without a firmware change regardless, so re-testing it has low marginal
value. `Cruise_Throttle` is the field this whole project actually wants to write today;
`Cruise_RPM` got a clean NULL that more, cleaner data could either reinforce or overturn.

### Maneuvers to prioritize (safe and legal only — see the overriding safety note above)

Ranked by how *abrupt* the resulting lead-acquisition is, since abruptness is what the
flat-baseline filter selects for:

1. **Changing into a lane with a car already close ahead** (e.g. moving to the lane you're
   about to need, that happens to have traffic in it) — creates a new, close lead in one
   discrete motion. The single best maneuver for this test.
2. **A vehicle merging into your lane ahead of you** from an on-ramp or side street — happens
   naturally and often in ordinary driving; no action needed beyond noticing it happened
   cleanly (no gas/brake input from you during the transition).
3. **Passing and moving back in ahead of the car you passed** — the return-to-lane creates an
   abrupt new lead, though typically a lower-urgency one than #1.
4. **Optional, only if genuinely available and safe — the gold-standard version:** on a
   private road or empty lot, a cooperating second vehicle pulls out into your lane ahead of
   you at a controlled moment, at low speed, with you on stock ACC. This is the cleanest
   possible exogenous impulse (a true "was empty, now isn't" event with no gradual buildup)
   but requires a second driver and a private setting — a bonus, not a requirement.

**What to avoid:** don't tailgate to try to trigger more lead-losses, don't make an unsafe
lane change to chase this data, don't rely on cruise-control-adjacent traffic weaving.
Ordinary attentive driving with a bias toward lane changes and merges over passive following
already does most of the work.

### Power floor, and an honest expectation about timing

**N ≥ 100 per field, same floor as Rounds 1–2, for direct comparability.** Unlike Test B
(which can plausibly hit its floor in one session because each rep is driver-initiated on
command), **Test C's events depend on traffic actually being there** — a single drive is
unlikely to single-handedly clear N≥100. **This is expected to take multiple sessions,
accumulating in the same archive.** After each drive, once it syncs, re-run
`research/es_perception_flatbase_test.py` / `_rpm_test.py` against the growing archive and
check the running N — no need to wait for a single drive to finish the job. Report interim
counts; only apply the decision rule once N clears the floor.

### Pre-registered expected outcome (recorded before driving)

Given `Cruise_Throttle`'s archive result was a genuine near-miss (61.8% vs. 70%, margin
already clearing its own bar) and `wheel_torque` disagreed with `throttle_body` on the same
events, a larger, cleaner sample could plausibly tip either way — **CONFIRM and INCONCLUSIVE
both look live going in, NULL looks less likely than for the archive version** (the whole
point of the redesign is removing baseline contamination that biased *toward* smaller
margins). For `Cruise_RPM`, given the archive result was a *clean* NULL (45.1%, 0ms margin —
not a near-miss), the honest prior is that a cleaner sample **reproduces NULL**, and a
reversal here would be a genuinely surprising result worth extra scrutiny before trusting it.

---

## Part 3 — running both in one session

Both tests are stock-ACC-only and compose without interference: the analysis-side gating
already excludes any event contaminated by driver pedal input in the wrong window, so
incidental overlap (a lead-change happening during a gas-override rep, or vice versa) costs
that one event, not the whole dataset.

**Suggested structure for a combined ~1–1.5 hour drive:**

1. **Arterial/highway segment with real traffic** — drive normally, biased toward the Test C
   maneuvers above when a safe opportunity arises. This is also naturally the best place to
   find the 2600–3100 `Cruise_Throttle` band for Test B (ordinary highway cruise).
2. **Interspersed Test B reps** whenever cruising steadily in that band — no need to
   dedicate a separate stretch of road, just do a rep whenever the conditions line up.
3. **A calmer stretch (rural/low-traffic) for the Test B floor-band control reps** — easiest
   right after a stop or a coast-down, when `Cruise_Throttle` is naturally near 808.
4. No special notes required. Optionally jot rough road-type/conditions per the existing
   Test B convention — not needed for the analysis, just useful context if a result looks
   surprising later.

**After the drive:** once routes sync, re-run the four existing analysis scripts
(`es_perception_flatbase_test.py`, `es_perception_flatbase_rpm_test.py`, and a
T5-style gas-override extraction reusing `es_longitudinal_command_correlation.py`'s
override-event detector, filtered to the new routes) against the newly synced data. No new
code is needed for either test — this drive produces data, not a new analysis design.

---

## Part 4 — what this drive can and cannot decide, restated one more time

Same G1 ceiling that has applied to every round tonight: neither test can prove the ECU
*obeys* a field, only that the field behaves like an independent demand rather than a
powertrain echo. **A full double-CONFIRM here still does not authorize a live write.** The
honest next step after a confirm remains a design review — including the two concrete
prerequisites already surfaced: there is currently **no panda `tx_hook` value check at all**
on `ES_Distance` (the veto-only safety rule lives entirely in Python with nothing under it),
and `Cruise_Throttle`/`Cruise_RPM` are tightly co-varying (T8), so a throttle-only write would
put the ECM in a state it may never have seen paired with its own live `Cruise_RPM`.
