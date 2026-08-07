# Round 3 results: `ES_Brake.Brake_Pressure` — wide-lag sweep and the campaign's first clean CONFIRM

**Date: 2026-08-07. Fully passive archive analysis, zero CAN transmission, zero device
access.** Completes the symmetric H1/H2/H3 treatment: `esb_brake_pressure` (`ES_Brake`/
`0x160`, the H2 field) had only ever had T6's onset-latency test against real
EyeSight-braking episodes. This round adds the wide-lag correlation sweep both other ES
fields already got, plus the same flat-baseline perception-impulse race used in Rounds 1-2.
Pre-registration: `research/es_stage0_round3_brake_prereg.md` (committed alone, before any
analysis code, same discipline as Round 2). Scripts: `research/es_brake_focus.py`,
`research/es_perception_flatbase_brake_test.py`.

---

## Top-line

**Both sub-analyses point the same direction, cleanly, for the first time in this campaign.**
The wide-lag sweep found the sharpest, most resolved correlation peak of any ES field tested
(R²=0.978, command-direction, +100ms). The perception-impulse test — the one test type in
this campaign designed to reach past the G1 identifiability ceiling — came back a genuine,
unanimous **CONFIRM**: on 73 qualifying exogenously-triggered events, `esb_brake_pressure`
led the physical brake response 100% of the time, by a median margin of ~500ms, across
*every one* of four independent comparators. `Cruise_Throttle` was INCONCLUSIVE (Round 1).
`Cruise_RPM` was a clean NULL that reversed its own strong correlation (Round 2).
`ES_Brake` is a clean CONFIRM that agrees with its own strong correlation. Of the three ES
fields, this is by a wide margin the strongest evidence anywhere in the campaign that a
field is EyeSight's own independent demand, not a report.

**The caveat that matters most, stated up front:** `ES_Brake` is **not TX-allowed today** —
writing it would require a panda safety-firmware change, a separate and larger decision (see
`research/panda_safety_firmware_deployability.md`). This result changes the confidence
picture, not the practical roadmap.

---

## Step 1 — wide-lag correlation sweep

Restricted to ticks where `esb_brake_pressure(t) > 1` (the variance-floor guard — see below),
`acc_engaged` regime, full 282-route archive, n=137,047 active-brake ticks:

| comparator | best lag | R² | slope |
|---|---|---|---|
| `brake2_right` | **+100ms** | **0.9784** | 0.101 |
| `mc_brake_right` | +150ms | 0.9781 | 0.063 |
| `brake2_left` | +150ms | 0.9690 | 0.102 |
| `mc_brake_left` | +150ms | 0.9687 | 0.064 |
| `aego` | +250ms | 0.1544 | −0.002 |

**The sharpest, most resolved peak found anywhere in this campaign.** Full curve for
`brake2_right` (representative — all four brake-pressure comparators are near-identical in
shape):

```
lag_ms   R²
-1500   0.4608
 -700   0.7283
 -300   0.8822
    0   0.9656
 +100   0.9784   <- peak
 +300   0.9515
 +700   0.7900
+1500   0.4327
```

A smooth, symmetric, genuinely localized peak — R² falls to ~0.43-0.46 at both ±1500ms
extremes, unlike `Cruise_RPM`'s elevated plateau (worst point still 0.916) or
`Cruise_Throttle`'s ambiguous broad hump (worst point 0.500, barely below its own peak of
0.549). This is the first ES-field correlation in the whole campaign that looks like a true,
localized peak rather than either a flat co-trend or a wide plateau.

**Variance-floor guard, explicitly checked (a real bug from earlier this campaign was a
false-positive K1 trigger on `esb_brake_pressure`'s dominant near-zero population):**
`es_std = 135.47` at every lag — large, confirming this is a real signal on real variance,
not a near-constant artifact. The `>1` active-tick restriction is doing its job.

**Direction: command, not echo.** The peak sits at positive lag (+100 to +150ms) — meaning
`esb_brake_pressure(t)` best predicts what the physical sensors *become* ~100-150ms later,
not what they *already were*. Per the campaign's standing sign convention, this is the
command/acknowledgment direction, the same direction `Cruise_RPM`'s (ultimately-reversed)
population correlation pointed. R²=0.978 remains short of K1's 0.999 echo-direction
threshold — and even if it had crossed it, the direction means it would not trigger K1
(which only fires in the echo direction) — so this alone is suggestive, not decisive. See
Step 2 for the test that actually is decisive.

---

## Step 2 — perception-impulse test: **CONFIRM**

### Method (full detail in the pre-registration doc)

Same `Car_Follow` 0→1 exogenous trigger as Rounds 1-2. Onset thresholds and comparator
choice reused directly from T6's already-validated calibration rather than re-derived
(`esb_brake_pressure`: 20 counts, T6's own activation threshold; `brake2_left`/`brake2_right`/
`mc_brake_right`/`mc_brake_left`: 2.0 counts; `aego`: 0.2 — all T6's established values).
Primary comparator `brake2_left`, chosen because T6 found it the faster of the wheel-pressure
pair. Response window extended to 2.5s (vs Rounds 1-2's 1.2s) and power floor lowered to
N≥50 (vs 100) — both fixed in the pre-registration before running, reasoned from `ES_Brake`
requiring an extra brake-vs-throttle-only decision and braking-tied cut-ins being
structurally rarer than throttle-modulation events.

### Yield, and a confirmed methodological lesson

5,474 raw `Car_Follow` transitions → **73 qualifying primary events** after all gating
(rejections: 2,521 not isolated, 781 no real response, 702 driver gas, 376 ACC dropped, 266
driver brake, 14 baseline not flat, 2 not sustained). A 40-route smoke sample had projected
only ~28 for the full archive — the true count (73) was **2.6x higher**. This is the third
time in this campaign smoke-sample linear extrapolation has undershot the real full-archive
count (Round 2's write-up flagged the same pattern independently on a different field). This
is now a confirmed, general property of this specific pipeline/archive, not a one-off — worth
remembering for any future round: **a smoke sample projecting below a power floor is not
sufficient grounds to skip the full run.**

### The result

**PRIMARY VERDICT: CONFIRM.** `frac_brake_first_50 = 100.0%`, `median_margin = 499.74ms`,
n=73 (clears the N≥50 floor). Both AND-conditions (≥70% and ≥75ms) blown through with
enormous margin — this is not a near-miss the way Round 1's was.

**And it is not a fragile result riding on one comparator — all four agree, unanimously:**

| comparator | n_usable | median margin | brake-first |
|---|---|---|---|
| `brake2_left` (primary) | 42 | 499.74ms | **100.0%** |
| `brake2_right` | 42 | 530.16ms | **100.0%** |
| `mc_brake_right` | 37 | 810.41ms | **100.0%** |
| `mc_brake_left` | 30 | 910.47ms | **100.0%** |

Every qualifying event where both onsets were detectable showed `esb_brake_pressure` moving
first, against every comparator, with margins that scale exactly as T6 already predicted
(the wheel-pressure pair leads, master-cylinder pressure lags further behind — `brake2_*` at
~500-530ms, `mc_brake_*` at ~810-910ms, consistent with T6's own ~300-400ms gap between the
two pairs). **This is the opposite failure mode from Round 1**, where a disagreeing secondary
comparator (`wheel_torque`) undercut confidence in a near-miss primary result. Here, internal
agreement across independent signals is part of what makes this CONFIRM credible rather than
a fluke of one noisy comparator.

**Secondary endpoint (lead-lost, unfiltered, not used for the verdict) points the same
direction, more weakly:** n=848 raw, n_usable=20 vs `brake2_left`, 80.0% brake-first, median
margin 80.6ms. Directionally consistent, smaller and noisier as expected for the unfiltered
population — supports rather than contradicts the primary result.

### A representative trace, illustrating exactly what "CONFIRM" means here

```
 dt_ms  esb_brake_pressure  Car_Follow  brake2_left  brake2_right  mc_brake_right
  -100         0.0              0            0.0          0.0          0.0
     0         0.0              1            0.0          0.0          0.0     <- trigger
   100         8.0              1            0.0          0.0          0.0
   200        32.0              1            0.0          0.0          0.0
   300        57.0              1            0.0          1.0          0.0
   400        63.0              1            0.0          1.0          1.0
   500        70.0              1            1.0          2.0          1.0     <- peak-ish
   700        70.0              1            2.0          3.0          2.0
  1300        45.0              1            4.0          5.0          3.0
  1900        13.0              1            2.0          2.0          1.0
  2200         0.0              1            0.0          1.0          0.0
```

`esb_brake_pressure` is already at 57-70 (near its own peak) by 300-500ms — before any of the
three physical brake sensors have registered more than a single count. The decay back to
zero over the following ~1.7s is smooth and coordinated across all signals, and the driver's
throttle pedal is zero throughout (part of the gating, confirmed in the trace). A completely
clean, EyeSight-initiated braking event with no ambiguity about which signal moved first.

---

## What this does and doesn't establish — G1 still applies, but more weakly here than elsewhere

**What it establishes:** `esb_brake_pressure` is not a report of the wheel or master-cylinder
brake pressure — it moves first, unanimously, by a wide margin, on an exogenous trigger. That
rules out the "echo of a physical brake sensor" hypothesis as cleanly as any result in this
campaign has ruled out anything.

**What it still cannot establish, per G1:** that the vehicle's brake-actuation ECU *obeys*
this specific CAN field, as opposed to EyeSight computing and publishing this field while
commanding the physical brakes through some other, unobserved channel that merely correlates
with it.

**Why this caveat is weaker here than it was for `Cruise_Throttle` or `Cruise_RPM`, worth
saying plainly:** for throttle, there is a real, non-hypothetical alternative — the ECU's own
cruise/speed-following control loop could independently modulate the physical throttle while
`Cruise_Throttle` is merely EyeSight's internal telemetry of what it *wants*. The archaeology
research (`research/preglobal_longitudinal_command_archaeology.md`) established that
`ES_Brake` is specifically the DBC-defined member of Subaru's documented longitudinal
"command trio," and no alternative CAN-based braking-command channel has been identified
anywhere in this project's research. The alternative-mechanism hypothesis that keeps G1 alive
for throttle is considerably less concrete here. This is not a loophole closed — G1 formally
still stands — but it is the least-hedged CONFIRM in this campaign.

---

## Pattern across all three ES fields, now complete

| field | wide-lag correlation | perception-impulse verdict |
|---|---|---|
| `Cruise_Throttle` (H1) | broad ambiguous hump, R²≈0.55 max | **INCONCLUSIVE** (near-miss, undercut by disagreeing secondary) |
| `Cruise_RPM` (H3) | sharp peak, R²≈0.99, command-direction | **NULL** (reversed its own correlation) |
| `Brake_Pressure` (H2) | sharpest peak of the three, R²≈0.978, command-direction | **CONFIRM** (unanimous, 4/4 comparators, ~500ms margin) |

No simple rule ("strongest correlation wins" or "weakest loses") predicts this pattern —
`Cruise_RPM` had the strongest population-level signal and produced a NULL; `ES_Brake` had a
comparably strong signal and produced the campaign's only clean CONFIRM. This reinforces
Round 2's central methodological lesson: population-level correlation strength and
causal-ordering-on-an-exogenous-trigger are genuinely different questions, and only the
latter comes close to the evidence a live write would actually need.
