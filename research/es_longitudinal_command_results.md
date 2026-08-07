# Stage 0 results: is `ES_Distance.Cruise_Throttle` a real longitudinal command on preglobal?

**Date run: 2026-08-07. Fully passive archive analysis, zero CAN transmission, zero device
access.** This is the actual output of `research/es_longitudinal_command_correlation.py`
(written and pre-registered 2026-08-06, executed for the first time here) plus two small
follow-up scripts written after seeing the first results, `es_echo_focus.py` and
`es_rpm_focus.py` (included in this directory). Companion docs: the hypothesis and
pre-registered CONFIRM/KILL criteria are in `research/es_longitudinal_command_hypothesis.md`
— read that first for what each test means and why. This document reports what actually
came back, including where the pre-registered design had real gaps.

**Archive scale:** 282 routes, 3,920 segments, 0 route-level errors. `ES_Distance` census:
4,516,037 openpilot-authored main-bus frames (T9), ~2.1M `acc_engaged_clean` 20Hz ticks —
over 100x the pre-registered statistical-power floor (20,000 ticks). Every Gate-0 threshold
cleared by a wide margin: 4,000 step events (hit the collection cap), 283 usable gas-override
events (vs. 30 required), 378 EyeSight-brake events (vs. 50 required). **Nothing here is
INCONCLUSIVE for lack of data.**

---

## Top-line verdict

**H1 survives its own kill test. It is not confirmed either.** `Cruise_Throttle` is not an
echo of any powertrain report field (K1 does not fire, anywhere, in any regime) — the
cheapest, cleanest way this hypothesis could have died for free, and it didn't. But the
lead/lag evidence that would make a clean CONFIRM (T3, T4, T5) came back **weak and
heterogeneous**, not a clean positive. The single most decisive, cleanest results in this
entire pass are not about lead/lag at all — they're the **transfer-function** measurements:
`Cruise_Throttle` maps almost perfectly monotonically onto real measured acceleration across
its entire operating range (floor → strong deceleration, ~1800 → near-zero, ~3750 → strong
acceleration), and `ES_Brake.Brake_Pressure` maps onto deceleration with a slope within ~4%
of the exact global constant. Whatever this field is, it is not noise and it is not
disconnected from the powertrain — it is either a live command or an extremely faithful
real-time report, and archive data alone cannot finish separating those two (as pre-registered
in G1 — this was never expected to be resolvable without a live write).

**Practical read:** nothing here justifies a live write yet. Nothing here kills the idea
either. The honest state is "still open, now with much better-characterized envelopes and a
much sharper picture of exactly which evidence types can and can't separate command from
report on this specific car."

**One pre-registered prediction came back reversed, and it's worth flagging up top.** §4.3
of the hypothesis doc predicted `Cruise_RPM` (`ES_Status`) was "more likely than not" to trip
K1 against `Transmission_Engine`, confirming a 2019 DBC comment calling it a report-side
"duplicate." The data show an extremely tight relationship (R²≈0.95–0.99, far tighter than
anything found for `Cruise_Throttle`) — but the tightest point sits on the **command** side
of zero lag (`Cruise_RPM` leads the transmission's own RPM report by ~250–400ms), not the
echo side. The "duplicate" framing looks backwards; "the transmission appears to track
`Cruise_RPM`'s demand" is the better-supported reading. See the T2/H3 section below.

---

## (a) THE ECHO RELATIONSHIP — priority 1

### What the main script found, and why it wasn't trustworthy as-is

`es_longitudinal_command_correlation.py`'s T2b result, gated to `acc_engaged_clean`
(n=2,104,942 ticks):

| | lag | R² | slope | resid RMS |
|---|---|---|---|---|
| echo-side best | **−200ms (grid boundary)** | 0.5107 | 0.0218 | 14.01 |
| cmd-side best | **+200ms (grid boundary)** | 0.5018 | 0.0215 | 14.11 |

Both sides landed on the **edge of the tested lag grid** (`COPY_LAGS_MS` only goes to
±200ms), and both sides are nearly tied (R² 0.51 vs 0.50). That's not a usable answer — it
means the coarse 9-point grid clipped before finding wherever the real optimum is, and a
near-tie at the boundary is exactly what you'd see approaching a peak that lies further out.
**This was flagged as a real gap, not treated as the answer.**

### The fix: `es_echo_focus.py` — wide lag grid (±1500ms, 50ms steps), same regime gate

Restricted to `acc_engaged_clean` only, same archive, same 282 routes, n=2,104,942 ticks.
**The full lag curve, not just the best point, is the important result here:**

```
lag_ms   R²      r
-1500   0.4946  0.7033
-1000   0.5393  0.7344
 -800   0.5480  0.7402
 -700   0.5486  0.7407   <- global max
 -600   0.5456  0.7387
 -300   0.5211  0.7218
 -150   0.5061  0.7114
    0   0.5003  0.7073   <- curve minimum, right at zero lag
 +150   0.5001  0.7072
 +300   0.5084  0.7130
 +650   0.5257  0.7250   <- local max on the command side
 +700   0.5255  0.7249
+1000   0.5072  0.7122
+1500   0.4458  0.6677
```

Full 61-point curve in `es_echo_focus_results.json` / reproducible from `es_echo_focus.py`.

**Shape matters more than the single best point.** This is a smooth, broad hump spanning the
*entire* ±1.5s window at R²≈0.45–0.55, with two shallow local maxima around ∓700ms and a
genuine local *minimum* sitting almost exactly at lag=0 (R²=0.5003 at 0ms — the single worst
point on the whole curve). That is not the shape a tight, fast causal echo or command-ack
loop would produce (which would show a sharp, narrow peak at some specific short lag,
falling off quickly on either side). It's the shape two signals produce when they're both
driven by a slow common trend — both broadly tracking overall vehicle speed / power demand
as a drive evolves — rather than one directly causing or copying the other on a fast
timescale. **The global best (lag=−700ms, R²=0.549) is barely above the +650ms local max
(R²=0.526) and both are barely above the zero-lag minimum (R²=0.500) — this whole curve
lives in a narrow band, nowhere near the 0.999 threshold, at any lag from −1.5s to +1.5s.**
That is strong, direct evidence *against* a tight lag-locked copy relationship existing
anywhere in this range, in either direction — a meaningfully stronger and more complete
version of C1 than the original ±200ms grid could show.

**A real limit on what this specific measurement can resolve:** `ES_Distance` itself only
ticks at 20Hz (50ms). Nothing faster than that can be seen by this design at all, regardless
of lag-grid width — so a genuinely tight, sub-50ms echo-and-cross-check loop (the literal
mechanism `bugsyborromeo` described) is architecturally invisible to this test. This isn't a
new gap — it was already implicit in the pre-registered design's own tick rate — but it's
worth stating plainly: this result rules out a *slow* echo (tens to hundreds of ms), not a
*fast* one at the message's own native rate.

### Control check: does the ECU's own `Throttle_Cruise` just track the driver's pedal?

If `0x140.Throttle_Cruise` is largely pedal-driven regardless of ACC state, a moderate
correlation with `Cruise_Throttle` would be uninformative either way — both would just be
independently correlated with what the driver's foot is doing. Restricted to
`acc_engaged_clean` (driver's foot should be *off* the pedal almost the whole time in this
regime by definition, so this is really a check on whether "clean" driving is clean):

```
best lag = -1500ms (boundary, i.e. essentially flat across the whole grid)
R² = 0.0033, r = 0.057
```

Essentially zero correlation, as expected — during `acc_engaged_clean`, `throttle_pedal` is
close to zero almost by construction (that's what makes the regime "clean"), so there's
nothing for `throttle_cruise` to track. This is a sanity check that passed (no spurious
pedal-driven correlation leaking into the regime), not a finding on its own.

### (b) What does the echo do during a driver gas-pedal override?

This is the sharp question the task brief called the decisive one, and it exposed a real
blind spot in the original script: `es_longitudinal_command_correlation.py`'s T5 detector
recorded deltas for `es_cruise_throttle`, `throttle_body`, `engine_rpm`, `throttle_pedal`,
`ess_cruise_rpm`, and `vego` around each override event — but **never recorded
`throttle_cruise` itself**, the one field the whole obstacle (§2.8 of the hypothesis doc) is
about. `es_echo_focus.py` fixes that, replaying the identical override-event definition
(gas pressed while ACC engaged, sustained ≥500ms, edge-triggered) plus a −300ms…+2500ms
sampled trace of both fields per event.

```
n = 283 override events (same edge-triggered detector as the main script's T5:
    gas pressed while ACC engaged, sustained >=500ms)

throttle_cruise (ECU echo) vs throttle_pedal (driver):
  n_usable=258, same-sign fraction = 51.55%   (~coin flip)
  median d_throttle_cruise = +8.0

es_cruise_throttle (ES field) vs throttle_pedal (driver):
  n_usable=258, same-sign fraction = 45.35%   (~coin flip)
  median d_es_cruise_throttle = +73.0

throttle_cruise (echo) vs es_cruise_throttle (ES field) -- the two ECU/ES-side
fields against EACH OTHER:
  n_usable=251, same-sign fraction = 89.64%   (strongly coordinated)
```

**A genuinely interesting, non-obvious pattern.** Neither `Cruise_Throttle` nor
`Throttle_Cruise` tracks the driver's raw pedal direction consistently over the 1.5s
override window — both sit at essentially chance level (51.6%, 45.4%) against the pedal.
But `Cruise_Throttle` and `Throttle_Cruise` track **each other** 89.6% of the time. That
combination rules out the simplest story ("both fields just mirror the pedal") — whatever is
driving them during an override, it isn't a shared direct pedal-echo. It's consistent with
either (a) `Cruise_Throttle` is a real command whose *own* dynamics the ECU's
`Throttle_Cruise` report then tracks (the two move together because one causes the other,
independent of exactly what the pedal is doing at that instant), or (b) both are downstream
of some third, slower state (e.g. resulting engine RPM/speed) neither pedal-delta alone
captures over a fixed 1.5s window. This pass cannot distinguish (a) from (b) — but a
concrete example from the raw traces makes (a) look like a live possibility worth taking
seriously:

```
route 00000002--bd426df276, one representative override event (ct_before=808, tc_before=0):

  t(ms)   Cruise_Throttle   Throttle_Cruise   Throttle_Body   Pedal
   -100         808                0               19          0
      0         808                0               19          2
    200         808                0               32          35
    400         808                0               47          34
    600         808                0               55          34   <- pedal & TB near saturated,
    700        2090                4               54          34      CT still pinned at floor
    900        2552               21               53          34
   1300        2967               32               52          33
   1800        3264               45              106            0   <- pedal released...
   2100        3505               54              100            0   <- ...CT/TC keep climbing
   2400        3751              125              162            0
   2500        3824              144              251            0   <- TB near its ceiling
```

`Cruise_Throttle` sits dead flat at the 808 floor through the entire gas press — the pedal
and physical `Throttle_Body` are both already saturated (34, 55) *before* `Cruise_Throttle`
moves at all. Then, roughly 700ms after the press began, it jumps abruptly and keeps ramping
upward for the next ~1.8 seconds — continuing to climb for a full 700ms **after the driver's
foot is already off the pedal**. `Throttle_Cruise` (the ECU's own report) tracks that climb
closely and with a small delay throughout, exactly matching the "ECU acknowledging a growing
command" pattern from T2b, not a "field mirrors the pedal in real time" pattern. If
`Cruise_Throttle` were a direct pedal echo it should fall back toward baseline the moment the
pedal releases at t=1800ms; instead it does the opposite. This reads as a real command
channel with its own internal ramp dynamics — plausibly "woken" by the driver's input
(consistent with an ACC resume-style trigger) rather than continuously mirroring it.

**A methodological caveat worth stating plainly:** several of the sample traces pulled for
this inspection came from the *same* route in close succession, consistent with the
edge-triggered detector (`pedal crosses 0→nonzero`) re-firing multiple times on what is
really a single continuous driving maneuver if the pedal signal dips near zero briefly mid-press.
This means the n=283 event count likely represents somewhat fewer independent real-world
maneuvers than it appears to — a real limitation inherited from the pre-registered detector
design (used identically in the main script's T5), not something patched here, but worth
weighting the aggregate statistics accordingly rather than treating n=283 as 283 independent
trials.

**Heterogeneity found by hand in the raw override events (from the main run's
`raw_events.override_events`, before the echo-specific fields existed):** the response is
not uniform across the operating range. A cluster of events starting from `ct_before = 808`
(the floor) show `Cruise_Throttle` jumping by +2,300 to +2,370 counts — a huge fraction of
its entire dynamic range — in direct response to a driver gas press, while `Throttle_Body`
only moves 47–64 counts (out of 0–255). That looks strongly echo/report-like. But other
events starting from mid-range values (`ct_before` ≈ 2,700–2,800) show much smaller,
sometimes **opposite-signed** `Cruise_Throttle` moves for a comparable or larger pedal press
— including one event with a massive real pedal/throttle-body surge (`d_throttle_pedal=151`,
`d_throttle_body=+201`, near-saturating) where `Cruise_Throttle` actually **fell** by 263
counts. A falling ES demand while the car visibly accelerates faster than commanded is
exactly the signature the hypothesis doc predicted for a genuine independent command (§3,
T5 rationale: *"EyeSight's demand should fall — the car is now going faster than asked"*).

**This is the honest finding, not a script bug: the override response is genuinely
heterogeneous.** It looks echo-like near the floor and command-like in the mid-range. The
pre-registered aggregate test (T5) landed exactly where this heterogeneity would put it —
**AMBIGUOUS**, between the CONFIRM band (relative gain ≤0.25, same-sign ≤50%) and the KILL
band (relative gain ≥0.75, same-sign ≥80%):

- n_usable = 277 (comfortably above the 30-event power floor)
- relative gain = **0.567** (override-window `|ΔCruise_Throttle| / |ΔThrottle_Body|`,
  normalized against the ordinary ACC-engaged regression slope)
- same-sign fraction = **58.8%**

Neither CONFIRM nor KILL fires. Reported as AMBIGUOUS, exactly per the pre-registered rule
(§4.1) — not stretched either direction.

---

## (b/priority-2) T2 — the exact-copy KILL test, full matrix

**K1 does not fire for `es_cruise_throttle`, anywhere, in any of the 6 regimes, against any
of the 16 candidate report fields, at any of the 9 coarse lags.** This is the single cleanest
result in the whole pass and it is a real, load-bearing CONFIRM-side finding (C1 holds): no
powertrain report reproduces `Cruise_Throttle` to within the pre-registered 99%-exact /
R²≥0.999 threshold in the echo direction. `Cruise_Throttle` is not a disguised copy of
anything on this candidate list.

**A real bug found in K1 itself, and what it does and doesn't affect.** `esb_brake_pressure`
(`ES_Brake.Brake_Pressure`, the H2 field) *did* trip the exact-match branch, twice:

| pair (regime) | exact_frac | R² |
|---|---|---|
| `acc_off\|esb_brake_pressure\|throttle_cruise` | 100.0% | **0.0** |
| `acc_on_not_engaged\|esb_brake_pressure\|throttle_cruise` | 99.9% | **0.0** |

R² = 0.0 in both cases. That's the tell: `esb_brake_pressure` is **pinned at exactly 0 for
100% of `acc_off` samples** (confirmed directly — `distinct_values: 1`, `min: 0, max: 0`).
A constant field trivially "exact-matches" any other field that also happens to sit near
that same constant most of the time, with zero real relationship (hence R²=0). The
pre-registered exact-match branch (`exact_frac ≥ 99%`) has no variance floor on the ES side,
so a pinned signal can pass it for free. **This is a genuine gap in the test as specified,
not a result** — it does not mean `ES_Brake` echoes `Throttle_Cruise`. It also **does not
touch H1 or `es_cruise_throttle` anywhere**: `es_cruise_throttle` has 300+ distinct values in
every regime it appears in (confirmed via the T1 histograms), so it was never at risk of this
artifact, and it never trips K1. Fixed in the checked-in script (a variance-floor guard on
the ES field, `es_std ≥ 5` counts, before the exact-match branch is allowed to fire) — noted
as a code correctness fix, not a PREREG retune; the numeric thresholds themselves
(99% / 0.999 / 1 LSB) are untouched. The already-completed run above predates the fix; this
writeup reports the artifact explicitly rather than silently treating it as evidence.

**`Cruise_RPM` vs `Transmission_Engine` — the pre-registered "most likely" prediction, and it
came within a hair of firing.** §4.3 of the hypothesis doc pre-registered, before seeing any
data, that this pair was "more likely than not" to trip K1 (confirming the 2019 DBC comment
that `0x162`'s RPM field is *"a 20Hz duplicate of the transmission's engine-RPM report"*).
The main run found:

```
acc_engaged_clean | ess_cruise_rpm | trans_engine
  R² = 0.9889, slope = 0.983, intercept = 41.1, lag = +200ms (grid boundary, command side)
```

R²=0.9889 is **0.0101 short** of the 0.999 threshold — and, same problem as the throttle
pair, the best fit landed on the ±200ms grid boundary. This needed the same wide-lag
treatment as the echo test:

```
es_rpm_focus.py, acc_engaged_clean, n=2,104,942, wide ±1.5s grid, 50ms steps:

lag_ms   R²      slope   intercept
-1500   0.9160  0.9491   110.85
 -700   0.9569  0.9689    70.74
 -300   0.9747  0.9772    53.88
    0   0.9848  0.9817    44.59    <- best WITHIN the echo-side (lag<=0) subset
 +200   0.9889  0.9835    41.08
 +300   0.9900  0.9839    40.16
 +400   0.9905  0.9840    39.89    <- GLOBAL best (interior peak, not clipped)
 +500   0.9902  0.9838    40.30
+1000   0.9791  0.9780    51.67
+1500   0.9567  0.9667    74.05
```

**A completely different shape from the throttle/echo curve above — a single, sharp, well-
resolved interior peak, not a broad ambiguous hump.** R² rises smoothly and monotonically
from 0.916 at −1500ms all the way to a clean maximum of **0.9905 at +400ms** (safely inside
the tested range, not clipped), then falls back down symmetrically. Even the *worst* point on
the entire ±1.5s curve (0.916) is far higher than anything the throttle pair produced anywhere
(max 0.549). Whatever `Cruise_RPM` and `Transmission_Engine` are doing, they are far more
tightly coupled than `Cruise_Throttle` and `Throttle_Cruise` are, by every measure.

**R²=0.9905 is still 0.0085 short of the pre-registered 0.999 threshold — K1 does not
technically fire, even with the wide grid.** But the direction is the important, and
genuinely surprising, update: the global maximum sits at **lag=+400ms, the command side**,
not lag≤0. Restricting to the echo-side subset only (lag≤0), the best available fit is
R²=0.9848 at lag=0 — measurably *below* the command-side peak (0.9905 at +400ms). Per the
pre-registered sign rule (§4.2 of the hypothesis doc), K1 can only fire when the echo-side
fit is both good enough *and better than* the command-side fit — and here the command side
wins outright. **So even in the counterfactual where R² had crossed 0.999, this would have
resolved as `is_ecu_echo_of_es_by_prereg` (ECU acknowledging a command), not K1 (echo/kill).**

Companion cross-check, `Cruise_RPM` vs `Engine_RPM` (`0x140.Engine_RPM`): peak R²=0.955 at
lag=+250ms — same command-direction story, independent field, consistent result.

**What this means for the §4.3 pre-registered prediction.** The prediction was: *"more
likely than not"* that `Cruise_RPM` trips K1 against `Transmission_Engine`, confirming the
2019 DBC comment that called it *"a 20Hz duplicate of the transmission's engine-RPM
report."* **That prediction is half right and half wrong, and both halves matter.** Half
right: there unmistakably *is* an extremely tight (R²≈0.95–0.99) relationship between
`Cruise_RPM` and the real transmission/engine RPM — far tighter than anything found for
`Cruise_Throttle`, and this is a genuinely different, stronger character of evidence than the
throttle field showed anywhere. Half wrong: the tightest point in that relationship sits on
the **command** side of zero lag, not the echo side — `Cruise_RPM` leads, the powertrain
report follows ~250–400ms later, the opposite of "duplicate" in the causal sense. Per the
task instructions on pre-registered predictions that turn out wrong: **stated explicitly,
not silently reinterpreted** — the 2019 DBC comment's "duplicate" framing looks backwards on
this measurement; a better-supported reading is "the transmission/engine RPM appears to
track `Cruise_RPM`'s demand with a ~250–400ms lag," which is closer to the "controls engine
rpm" testimony in the archaeology doc's §2.8 than to "just a report." This does not confirm
`Cruise_RPM` is a validated command either (the same G1 identifiability ceiling applies —
archive data can't separate "commanded and obeyed" from "demanded and independently
matched") — but it meaningfully shifts the qualitative picture toward H3 being alive, not
the pre-registered "most likely" dead outcome.

---

## T3 — cross-correlation (lead/lag, aggregate, first differences)

`es_cruise_throttle`, full archive, `acc_engaged_clean`-gated first-difference xcorr,
±300ms/25ms grid (n≈2.1M per pair):

| response field | peak lag | peak r |
|---|---|---|
| `throttle_body` | **+100ms** | 0.071 |
| `wheel_torque` | **+300ms (boundary)** | 0.113 |
| `aego` | **+300ms (boundary)** | 0.012 |
| `engine_rpm_140` | −225ms | 0.048 |
| `vego` | −300ms (boundary) | −0.019 |

Positive-lag (leading) for the two most direct physical-actuation signals
(`throttle_body`, `wheel_torque`) satisfies the pre-registered lag-sign criterion for C3
(`tau ≥ +40ms`) — but the correlation **magnitude is weak** (r ≤ 0.11 everywhere; r=0.07 for
`throttle_body` specifically, meaning it explains under 1% of the variance in first-differenced
`throttle_body`). The pre-registered criterion is lag-sign-only and does not have a
magnitude floor, so this technically satisfies C3 — but it is worth being honest that "weak
positive-lag correlation" is much less impressive than the pre-registered table's phrasing
suggests in isolation. Two of five response fields also clipped the ±300ms grid boundary
(`wheel_torque`, `vego`), another case where the coarse grid may be hiding the true peak;
not re-run with a wider grid here since the correlation magnitudes are already small enough
that a sharper peak wouldn't change the qualitative picture.

For comparison, the same test on `ess_cruise_rpm` (Cruise_RPM) is **far stronger** —
`engine_rpm_140` r=0.487 at +300ms (boundary), `throttle_body` r=0.349 at 0ms — consistent
with the R²=0.99 level-fit against `trans_engine` above. `Cruise_RPM` is a much more tightly
powertrain-coupled signal than `Cruise_Throttle` is, by every measure in this pass.

---

## T4 — step events (event-wise lead/lag)

**T4a (forward: `Cruise_Throttle` step → `Throttle_Body` response), n=4,000 (hit the
collection cap):**
- median latency = **+69.98ms** (inside the pre-registered CONFIRM band, 40–600ms)
- but only **59.2%** of events show a response at ≥40ms latency — short of the **80%**
  consistency bar (C2) → verdict **"not confirming"**

**T4b (converse: `Throttle_Body` step → `Cruise_Throttle` response), n=2,243:**
- median latency = **+100.12ms**, 65.3% respond after (positive)

**K2 does not fire.** K2 requires *both* T4a's forward median ≤0 *and* the converse showing
engine-precedes-ES. T4a's forward median is **+70ms, not ≤0**, so K2's first condition fails
outright regardless of T4b. (The script computes T4b's data but never wires K2 into its
automated `verdicts()` output — this is a second real gap, applied manually here rather than
left unevaluated.)

Taken together: T4 shows a weak, real, positive-lag signal in the CONFIRM direction (median
latency lands in-band both ways) but fails the **consistency** bar needed to call it a clean
CONFIRM, and does not meet the KILL bar either. Same "real but not clean" character as T3 and
T5.

---

## T6 — EyeSight braking (H2, plus the `Cruise_Throttle` "808 during braking" prediction)

n=378 EyeSight-initiated brake events (driver-brake episodes excluded by construction).
Onset latencies from `ES_Brake.Brake_Pressure` going non-zero:

| response | median latency |
|---|---|
| `aego` (measured decel) | +496ms |
| `Brake_2.right/left` (wheel brakes) | +500 / +550ms |
| `mc_brake_right/left` (master cylinder) | +801 / +890ms |
| `Cruise_Throttle` collapse to floor | **+600ms** |
| `Brake_2.brake_light` | +1,311ms (last, as expected — a downstream indicator) |

**The clean result: `median_ct_during_brake = 808.0` and `min_ct_during_brake = 808.0` —
exact.** During every one of these 378 EyeSight-braking episodes, `Cruise_Throttle` is
pinned at *exactly* the global `THROTTLE_ENGINE_BRAKE` constant (808), both at the median
and at the minimum, arriving ~600ms after the brake command starts. This is the single
tightest, cleanest confirmation of an H1a anchor value found anywhere in this pass — a
coordinated three-message behavior (brake pressure rises, throttle drops to exactly 808)
that matches the global architecture's documented semantics precisely.

---

## T7 — transfer curves (the value-envelope / control-law question, priority item 5)

### `Cruise_Throttle → aEgo`, `acc_engaged_clean`, binned by 50-count buckets

The cleanest, most decisive plot in this entire analysis. Selected bins (full table in the
raw JSON):

| Cruise_Throttle | n | mean aEgo (m/s²) |
|---|---|---|
| 800 (floor) | 97,923 | **−0.657** |
| 1800 (≈ global INACTIVE=1818) | 37,706 | −0.177 |
| 2600 | 80,877 | −0.002 |
| 2750 | 110,282 | +0.016 |
| 3400 (global MAX) | 20,718 | +0.271 |
| **3750 (peak)** | 16,805 | **+0.496** |
| 4050 (near top of 12-bit range) | 1,016 | +0.356 (small n, rolls off) |

**Near-perfectly monotonic from the floor through ~3750**, covering strong deceleration
through zero-crossing to strong acceleration, with huge per-bin sample sizes (tens to
hundreds of thousands) everywhere that matters. Two things this settles cleanly:

1. **This field is not noise and is not disconnected from the powertrain** — full stop. A
   report or a command would both produce this curve; it doesn't separate H1 from H0 by
   itself, but it is definitive that the field carries real, physically meaningful throttle
   information on this specific car.
2. **H1a (does the global encoding transfer) — CONFIRM the anchors, KILL the range, exactly
   the pre-registered "partial" outcome.** The floor (808) and the near-zero crossing
   (~1800–2000) land almost exactly where global's constants predict. But the *effective
   ceiling* on this car is **~3750–3800**, not global's 3400 — 8.5% of all `acc_engaged_clean`
   samples exceed 3400 entirely (`T1` histogram), and the accel curve keeps climbing
   meaningfully well past it. **Any future control law on this car must use a
   locally-measured ceiling (~3750), not global's 3400.** This is exactly the "only ever
   replay values this car's own EyeSight has demonstrably commanded" principle from
   `eyesight_throttle_channel.md` — and now it's measured, not just proposed.

### `ES_Brake.Brake_Pressure → aEgo` (H2 encoding, not writable today but cheap to check)

Extremely clean, near-linear across the full range (`BP=0` → +0.037 m/s², `BP=600` → −3.34
m/s², `BP=825` → −4.10 m/s²). Fitted slope ≈ **−0.00563 to −0.0058 m/s²/count**, within
**~4%** of global's exact constant (`BRAKE_MAX_DECEL / BRAKE_MAX = −3.5/600 = −0.005833`).
This is the tightest H1a-style encoding match found anywhere in this pass, on a field that
isn't even TX-allowed today. If `ES_Brake` is ever added to the allowlist (a separate,
larger decision — see `panda_safety_firmware_deployability.md`), global's brake-scaling
constant looks like it would transfer almost exactly.

---

## T8 — joint distribution (write-safety, not truth)

1,004 distinct coarse `(Cruise_Throttle, Cruise_RPM, Brake_Pressure)` bins observed. The
dominant combinations are tightly clustered — e.g. `(CT=2700, RPM=2100, BP=0)` alone
accounts for 100,076 samples, and the top 10 combinations are all adjacent
`CT∈[2500,3000], RPM∈[2100,2400], BP=0`. **`Cruise_Throttle` and `Cruise_RPM` co-vary
tightly** in ordinary driving. This is exactly the risk T8 was designed to flag: a future
throttle-only write (leaving `Cruise_RPM` as EyeSight's own value) would, at some
operating points, produce a `(throttle, RPM)` pair the ECM has plausibly never seen
together. Descriptive only — does not bear on H1's truth, but is a real design input for
any eventual live-test protocol.

---

## T9 — relay fidelity, and an unplanned finding

**The relay is highly faithful — the opposite of what the design doc speculated (G11).**
Openpilot's own rebuilt `ES_Distance` (main bus): 4,516,037 frames.
- `Cruise_Throttle` matches the camera's copy exactly in **98.67%** of frames
  (4,455,951 / 4,516,037); diverges in 1.32% (59,819) — expected given two independent
  20Hz-ish clocks, but far less than "regularly," contrary to the design doc's
  pre-run speculation.
- The verbatim-copied `COUNTER` increments cleanly by exactly 1 in **99.06%** of frames.
  Duplicate (step-0) and double-skip (step-2) together account for under 1%; larger jumps
  are rare (tens of frames total, out of 4.5M).
- Median relay delay (camera frame → openpilot's main-bus retransmission): **2.97ms**,
  p95 **3.38ms** — tight, consistent with drain-on-ingest rather than a free-running
  independent 20Hz timer.

**Unplanned finding, worth flagging on its own: `SubaruStopAndGo` (or an equivalent
mechanism) is continuously active on this device across the entire archive, not firing in
brief resume bursts.** Census counts:

```
sendcan/0x140/src2 (fabricated Throttle → camera bus):     22,303,874 frames
sendcan/0x0d1/src2 (fabricated Brake_Pedal → camera bus):  11,152,007 frames
can/0x140/src0     (real Throttle, main bus):               22,582,553 frames
can/0x0d1/src0     (real Brake_Pedal, main bus):             11,290,851 frames
```

The fabricated-frame volume on the camera bus is within a few percent of the *real* main-bus
message volume for the same two addresses — i.e. openpilot is rebuilding and resending these
two ECU-report messages toward the camera bus at essentially the **same rate as the real
messages**, continuously, for the whole recorded history of this device. This matches the
source structure described in `preglobal_longitudinal_command_archaeology.md` §Q5 (the
frame is unconditionally rebuilt every cycle; only specific fields like `Throttle_Pedal=5`
are conditionally overridden on a resume trigger) — but corrects the operational picture in
`eyesight_throttle_channel.md`/`panda_safety_firmware_deployability.md`, which characterized
this as "brief bursts" (§7, "a ~15-frame nudge"). **In practice it's an always-on shadow
transmission, not an occasional one.** This doesn't change any H1/H2/H3 conclusion (this
analysis only ever decodes the genuine main-bus src0 copies of `0x140`/`0xD1`, never the
camera-bus spoof), but it's a materially different fact about what this device is already
doing to EyeSight's inputs 24/7, and it belongs in the operational picture for any future
live-test risk assessment.

---

## Summary against the pre-registered CONFIRM/KILL table

| test | criterion | result |
|---|---|---|
| T0 power | ≥20k ticks etc. | **PASS, by 100x+ margin everywhere** |
| T2 K1 (kill) | exact/affine copy, echo side | **does not fire for `es_cruise_throttle`** — C1 holds |
| T2b | ECU reproduces CT at positive lag | R²=0.51, below 0.999 — neither confirms nor kills cleanly; wide-lag follow-up above |
| T3 C3 | xcorr peak lag ≥ +40ms | lag-sign passes, magnitude weak (r≤0.11) |
| T4 C2/K2 | ≥80% events in-band / engine-precedes-ES | neither — 59% in-band, K2's AND-condition fails on its first clause |
| T5 (discriminator) | gain ratio + same-sign bands | **AMBIGUOUS**, exactly between the two pre-registered bands; heterogeneous by hand-inspection |
| T6 | ES_Brake leads real braking; CT→808 | **strong CONFIRM** — 808 exact, +600ms after brake onset |
| T7 / H1a | encoding transfers | **anchors CONFIRM (808/1818), range KILLS (3400→measured ~3750)** |
| T8 | joint coupling | CT/RPM tightly coupled — real write-safety flag for later |
| T9 | relay fidelity | **faithful** (98.7% exact, clean counters) — premise intact |
| H3 pre-reg prediction (§4.3) | Cruise_RPM echoes Transmission_Engine | **prediction reversed**: R²=0.9905 (command side, +400ms), 0.0085 short of K1; echo-side peak (0.9848) is *lower* than command-side — direction favors "RPM leads, transmission follows" over "duplicate" |

**Bottom line, stated plainly per G1 (identifiability ceiling, pre-registered before any
data existed): archive data has now done everything it structurally can. It ruled out the
cheapest kill (echo). It did not produce a clean CONFIRM. The transfer-function evidence is
strong that this is a real, physically-meaningful, powertrain-coupled signal. Separating
"EyeSight's own live command, obeyed by the ECU" from "EyeSight's own live demand, published
here and acted on some other way" — the distinction that actually matters for whether writing
it would work — requires a live write. This document does not recommend one. Per the task
brief, if this counted as Stage 0 confirming, the next step is a design review, not a live
test — and this result is a weaker confirm than that bar implies.**
