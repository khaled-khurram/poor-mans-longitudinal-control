# Round 4: detection-confound check + cross-ES-field internal structure

**This round is EXPLORATORY/DESCRIPTIVE, not a pre-registered CONFIRM/KILL test.** Same
honesty standard as the T5 stratification in `research/es_stage0_followup_results.md`:
recorded as hypothesis-generating and interpretive context for Round 3's result, not as a
fresh confirmatory finding. Fully passive, zero CAN transmission, zero device access.

**Context.** The three ES fields have each had a perception-impulse race test:
`Cruise_Throttle` INCONCLUSIVE, `Cruise_RPM` NULL, `ES_Brake` clean CONFIRM (100% across 4
comparators, margins ~500-900ms — see Round 1-3 results docs). No simple rule predicts this
pattern. This round asks two follow-up questions about how much weight the `ES_Brake`
CONFIRM should carry.

---

## Component 1 — is the CONFIRM just an easier detection problem?

**The competing explanation for `ES_Brake`'s big margins:** brake pressure going 0→nonzero
is a big, slow, binary physical state change (hydraulic actuator lag), while throttle is
continuous, near-instant (drive-by-wire), and constantly making small adjustments. If large
physical events are simply easier to win a timing race on regardless of the underlying
truth, `ES_Brake`'s CONFIRM could be a detection artifact rather than a genuine
command-vs-report finding.

**Method.** Re-extracted `|Δ Cruise_Throttle|` and `|Δ Throttle_Body|` directly from the
archive for all 116 of Round 1's qualifying events (targeted lookup by known
`route_id`/`t` — not a fresh full-archive pass), joined to each event's already-computed
`margin_vs_throttle_body_ms`. 110/116 events had both a magnitude and a margin.

**Result: the confound is NOT well supported, and one comparison points the opposite way.**

| stratified by | low tercile | mid tercile | high tercile |
|---|---|---|---|
| **`\|Δ Cruise_Throttle\|`** (ES field's own excursion) | 45ms margin, 53% CT-first | 100ms, 75% | 80ms, **92%** |
| **`\|Δ Throttle_Body\|`** (physical response size — the direct analog to Brake's actuator size) | 125ms margin, 81% CT-first | 90ms, 81% | **15ms, 61%** |

If the confound story were right, both rows should trend the same way (bigger physical
event → bigger margin, mimicking Brake). Instead they diverge: bigger *internal* ES
excursions modestly predict a cleaner win (53%→92%), but bigger *physical* throttle
responses predict the **opposite** — the largest real throttle-body movements show the
weakest, most chance-like margin (61%, 15ms — worse than the low tercile's 81%, 125ms).
Both Pearson correlations are weak (r=0.13 for ES-magnitude, r=−0.18 for physical-magnitude,
n=110), so neither trend is strong. But the direction of the physical-magnitude result is
the one that matters for the confound hypothesis, and it runs against it.

**Reading:** Round 3's `ES_Brake` CONFIRM should not be substantially discounted on the
"it's just a bigger, easier-to-win physical event" theory — the data available here don't
support that mechanism. This is modest evidence, not a strong rebuttal; report accordingly.

---

## Component 2 — do the three ES fields move together internally?

**The question:** if `Cruise_Throttle`, `Cruise_RPM`, and `Brake_Pressure` are all emitted
by one internal EyeSight decision simultaneously, `ES_Brake`'s large margin *against the
powertrain* could be entirely a physical-actuator-lag story — the internal decision might be
just as immediate as throttle's, only the hydraulics are slower to show it externally. If the
fields don't move together internally, that explanation doesn't hold and `ES_Brake`'s
CONFIRM looks more like a property specific to that channel.

**Method.** Wide-lag pairwise correlation (±1.5s, 50ms steps) between the three ES fields
directly (not vs. powertrain), restricted to ticks where `esb_brake_pressure` is active
(>20 — the variance-guarded threshold from Round 3, the most informative window). N=102,362
active ticks across all 282 routes.

**Result, with an important variance caveat found and checked, not glossed over:**

| pair | best lag | best R² | shape |
|---|---|---|---|
| `Cruise_Throttle` vs `Cruise_RPM` | boundary (−1500ms) | **0.0017** | essentially flat/negligible everywhere |
| `Cruise_Throttle` vs `Brake_Pressure` | boundary (−1500ms) | **0.032** | weak, nearly flat from −1500 to 0, gently declining toward +1500 |
| `Cruise_RPM` vs `Brake_Pressure` | boundary (−1500ms), still rising | **0.298** (r=−0.546) | real structure, genuinely still climbing toward the tested edge |

**Checked before drawing any conclusion (this matters): is `Cruise_Throttle`'s near-zero
correlation real independence, or just no variance to correlate?** Directly measured on a
60-route subsample of the same active-brake population (n=13,111 ticks): **`Cruise_Throttle`
is pinned at exactly 808 in 88.96% of these ticks** (mean 919.6, stdev 316.6, but the mass is
overwhelmingly at the floor — consistent with the original run's T6 finding that
`Cruise_Throttle` collapses to 808 during EyeSight braking). **`Cruise_RPM` in the same
window has real, non-degenerate variance** (mean 1084.8, stdev 539.5).

**This caveat changes the conclusion materially.** The near-zero `Cruise_Throttle` vs
`{Cruise_RPM, Brake_Pressure}` correlations are likely driven substantially by
`Cruise_Throttle` simply not varying much in this window (89% at one value), not by clean
evidence that the fields are computed independently. **This component is therefore
INCONCLUSIVE regarding `Cruise_Throttle`'s relationship to the other two fields** — the test
had little power to detect a link even if one exists, because one of the two variables barely
moves. The `Cruise_RPM` vs `Brake_Pressure` relationship is on firmer ground (real variance
in both), but its best fit lands at the ±1.5s grid boundary and is still climbing, so even
that result is unresolved — and its likely explanation (per the earlier `Cruise_Throttle` vs
`Throttle_Cruise` finding in the original run, where a similar slow, broad relationship
turned out to reflect a shared slow trend rather than a fast causal link) is at least as
consistent with **both fields reflecting the same slow, multi-second vehicle-deceleration
physics** (engine RPM naturally decays as the car slows under braking, a gearing/speed
relationship, not necessarily an internal EyeSight-decision link) as with a genuine internal
architectural connection. Not re-run with a wider grid here, given the ambiguity of
interpretation either way — flagged as an open item rather than chased further in this round.

---

## Synthesis: what this means for Round 3's CONFIRM

**Weakened less than initially feared, but the evidence for "it's just physics" is thinner
than hoped in both directions.** Component 1 modestly argues against the detection-confound
explanation (the physical-magnitude trend runs the wrong way for that story). Component 2
was supposed to test the competing "shared internal timing" explanation directly and mostly
came back uninformative — not because the fields agree or disagree, but because the test
lacked power on the `Cruise_Throttle` side (too little variance during active braking to
say anything), and the one pair with real signal (`Cruise_RPM`/`Brake_Pressure`) is itself
ambiguous between a real internal link and shared slow vehicle dynamics.

**Net effect: Round 3's CONFIRM stands, unweakened by either component here, but neither
component provides strong independent corroboration either.** The honest state is
"no evidence found against it, modest evidence against the most obvious alternative
explanation, but the direct test of the main competing hypothesis (shared internal timing)
was underpowered by an unrelated fact about `Cruise_Throttle`'s own behavior in that
regime." This is exactly the kind of nuance pre-registration and honest reporting exist to
preserve rather than round off into a cleaner-sounding story.

**A genuinely new, real finding, worth keeping regardless of the confound question:**
`Cruise_Throttle` and `Cruise_RPM` show no meaningful correlation with each other anywhere
in a wide lag window, even restricted to active-braking ticks where both are engaged parts
of the same driving episode. Whatever governs `Cruise_Throttle`'s moment-to-moment value, it
does not appear to be simply tracking `Cruise_RPM` (or vice versa) — the two fields'
dynamics are decoupled to first order, independent of the command-vs-report question
entirely.

Scripts: `research/es_crossfield_focus.py` (Component 2, full-archive pass) + raw results
`research/es_crossfield_results.json`; `research/es_component1_magnitude_extract.py`
(Component 1, targeted re-extraction of Round 1's 116 known events) + raw results
`research/es_component1_magnitudes.json`.
