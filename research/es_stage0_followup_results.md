# Stage 0 follow-up: closing gaps, stratifying the ambiguity, and the perception-trigger test

**Date: 2026-08-07. Fully passive archive analysis, zero CAN transmission, zero device
access.** Follow-up to `research/es_longitudinal_command_results.md`, which left three things
undone: an unevaluated pre-registered criterion (C5), an aggregate T5 result that was
"AMBIGUOUS" in a way that looked like structure rather than noise, and the identifiability
ceiling (G1) that all of T2–T5 runs into by construction.

**Read the epistemic status note in §3 before quoting anything from the stratification.**

---

## 1. C5 — the pre-registered criterion the first pass never evaluated

C5 ("`Cruise_Throttle` is materially different in distribution between ACC-engaged and
ACC-off — i.e. gated on control authority") is one of the five CONFIRM criteria. The first
writeup reported the `acc_off` and `acc_engaged_clean` histograms but **never actually
stated the C5 verdict**. Correcting that, from the completed run's own data:

| regime | n | distinct values | % at 808 | % at 1818 |
|---|---|---|---|---|
| `acc_off` | 122,037 | **4** | **99.984%** | 0.014% |
| `acc_on_not_engaged` | 2,275,660 | 2,076 | 66.841% | 15.847% |
| `acc_engaged_clean` | 2,104,942 | 2,694 | 6.662% | 1.644% |
| `acc_engaged_gas` | 12,203 | 2,301 | 12.931% | 7.654% |
| `acc_engaged_brake` | 204 | 91 | 48.039% | 4.902% |

**C5 passes decisively, and it is a stronger result than the first pass gave it credit
for.** Across 122,037 samples of real ACC-off driving — during which the engine's actual
throttle is certainly moving through its full range — `Cruise_Throttle` takes **exactly four
distinct values and sits at 808 for 99.98% of them.** It is inert.

**Why this matters more than "C5 passed":** it kills an entire class of hypothesis outright.
A *report of powertrain state* cannot be constant while the powertrain it reports on is
varying freely. K4 (the pre-registered kill — "during ACC-off manual driving,
`Cruise_Throttle` tracks engine throttle/RPM with the same relationship it has when
engaged") is not merely unfired, it is falsified in the strongest possible direction: the
field doesn't track the engine *at all* when ACC is off.

**The honest limit on that claim.** This rules out "echo of an engine signal." It does not
rule out "report of EyeSight's *own internal* ACC demand," which would naturally also be
inert when ACC is disengaged. That is precisely the G1 ambiguity, and C5 cannot touch it.
What C5 does is collapse the remaining space to a single question: not "is this a powertrain
echo" (settled: no), but "is EyeSight's published internal demand the thing the ECU acts on,
or a parallel readout of a demand delivered some other way."

The three-tier structure is itself informative and was not predicted: the field is *already
partially live* when ACC is on but not engaged (2,076 distinct values, though still 67% at
the floor), then fully dynamic when engaged. Consistent with a controller that is powered
and computing but not yet authoritative.

---

## 2. Deduplicating the override events — the first pass overstated its N by ~4.3x

The first writeup flagged as a caveat that the edge-triggered override detector
(`throttle_pedal` crossing 0→nonzero) probably re-fires several times on a single real
driving maneuver. Quantified now: collapsing events closer than 5s on the same route,

**283 raw override events → 66 independent maneuvers (23%).**

So T5's headline `n_usable = 277` was really **n ≈ 64 independent trials.** Every confidence
interval in the original T5 section should be widened accordingly.

Reassuringly, the aggregate numbers barely move, which argues the inflation was
distributionally benign rather than biasing:

| | n_usable | same-sign | median \|ΔCT\|/\|ΔTB\| | relative gain |
|---|---|---|---|---|
| raw (as originally reported) | 277 | 58.8% | 15.78 | 0.567 |
| **deduplicated** | **64** | **60.9%** | **16.94** | **0.609** |

Still AMBIGUOUS, still between the pre-registered CONFIRM (≤0.25 gain, ≤50% same-sign) and
KILL (≥0.75 gain, ≥80% same-sign) bands. The verdict does not change; only the confidence
in it does, downward.

---

## 3. Stratifying T5 by operating point — the ambiguity is structure, not noise

**⚠ EPISTEMIC STATUS — READ THIS BEFORE USING ANY NUMBER BELOW. This stratification was
NOT pre-registered.** It was motivated by hand-inspection of raw events from the completed
run, i.e. it was chosen *after* seeing the data it is applied to. That makes everything in
this section **hypothesis-generating, not confirmatory** — exactly the category of analysis
that can manufacture a clean-looking result from noise if you go looking. It is recorded
here as a **falsifiable prediction for a future deliberate capture drive**, not as a Stage 0
result, and it must not be quoted as evidence for H1. Per-bin sample sizes are small (24,
23, 13, 3 independent maneuvers). Given this project's history with over-claimed research,
this distinction is load-bearing.

With that stated — binning the 64 deduplicated maneuvers by `Cruise_Throttle`'s value
*before* the driver's gas press:

| `ct_before` | n | same-sign | opposite-sign | median gain | relative gain | pre-registered band |
|---|---|---|---|---|---|---|
| **≤900 (at/near floor)** | 24 | **79.2%** | **0.0%** | 61.64 | **2.214** | **KILL side** |
| 900–1900 | 1 | 100% | 0% | 32.90 | 1.182 | (n=1, ignore) |
| 1900–2600 | 23 | 56.5% | 43.5% | 16.35 | 0.587 | ambiguous middle |
| **2600–3100** | 13 | **30.8%** | **69.2%** | 5.76 | **0.207** | **CONFIRM side** |
| >3100 | 3 | 66.7% | 33.3% | 6.38 | 0.229 | (n=3, ignore) |

**The two ends of the operating range land in opposite pre-registered bands, monotonically.**
The aggregate "AMBIGUOUS" verdict is the average of two opposite behaviors, not a weak
signal.

**Why the two ends are not symmetric evidence — this is the important part.** The
KILL-side bin and the CONFIRM-side bin are *not* equally damaging/supporting, because the
T5 metric (direction + gain over a fixed 1.5s window) can be fooled in one direction but not
the other:

- **The floor cluster (KILL-looking) has an innocent command-side explanation the metric
  cannot see.** The traced example in the first writeup came from exactly this bin: at
  `CT=808`, driver presses gas, and `Cruise_Throttle` stays pinned at the floor through the
  *entire* press — then jumps ~700ms *after* the press began and keeps climbing for another
  1.8s, continuing well after the pedal is released. That is a **delayed state transition**
  (an inactive/coasting ACC controller waking up), not an echo. It scores as "same-sign,
  high gain" because both ended up higher, which is all the metric measures. A genuine echo
  would have tracked the pedal *during* the press and fallen when it released. It did the
  opposite.
- **The mid-range cluster (CONFIRM-looking) has no innocent report-side explanation.** 69%
  of those maneuvers move `Cruise_Throttle` **opposite** to a real, driver-caused engine
  increase — EyeSight reducing its demand while the car accelerates past what it asked for.
  A report of powertrain state physically cannot go down when the powertrain goes up. This
  is the one signature in the entire analysis that an echo hypothesis cannot produce.

So the asymmetry favors the command reading — but on n=13 unpre-registered maneuvers, which
is nowhere near enough to conclude anything. **Stated as a prediction:** a deliberate capture
drive doing repeated gas overrides from mid-range `Cruise_Throttle` values (~2600–3100) at
steady cruise should reproduce ≥60% opposite-sign responses. If it does not, this section
was noise and should be discarded.

---

## 4. T4 stratification — a hypothesis that failed, recorded as such

The first writeup speculated that T4's weak 59.2% consistency (short of the 80% C2 bar) was
probably dominated by small steps near the detection floor, and that stratifying by step
magnitude would show large steps behaving cleanly. **That hypothesis is not supported.**
Over the 1,000 stored step events (of 4,000 collected — the raw-event store is capped, so
this is a subsample):

| step size (counts) | n | median latency | % in the 40–600ms CONFIRM band |
|---|---|---|---|
| 100–200 | 787 | +70.2ms | 52.0% |
| 200–400 | 31 | **−29.7ms** | 19.4% |
| 400–800 | 3 | −60.5ms | 33.3% |
| 800–1600 | 179 | +90.3ms | 63.3% |

No monotonic trend; the 200–400 bin actually has a *negative* median latency. Large steps
are somewhat better (63.3%) but nowhere near the 80% bar. **C2 stays unrescued and T4
remains a weak, inconsistent positive.** Recording the failed hypothesis rather than
quietly dropping it.

---

## 5. The perception-trigger test — attacking G1 directly

Results in the next section once the full run completes. Design and rationale:

`ES_Distance` (`0x161`) carries `Car_Follow` (bit 16) and `Close_Distance` (`24|8`) in the
**same frame** as `Cruise_Throttle` (`0|12`) — zero relative timing uncertainty between the
perception signal and the field under test. `Throttle` (`0x140`) is a separate message at
~100Hz.

When EyeSight acquires or loses a lead vehicle, its controller learns of it instantly, but
**the powertrain has no reason to have changed anything yet.** So:

- **COMMAND** ⇒ `Cruise_Throttle` moves at/near the perception event, powertrain follows.
- **REPORT** ⇒ `Cruise_Throttle` cannot move until the powertrain moves first — it would
  have nothing to report.

The decisive statistic is a per-event **ordering**, internally controlled: does
`Cruise_Throttle`'s onset precede `Throttle_Body`'s? A report cannot systematically win that
race on a perception-triggered event. This is the one test in the whole program whose
trigger is exogenous to the powertrain, which is why it can reach past G1 where T2–T5
cannot.

**Method notes, stated for auditability:**
- Onset thresholds are **identical to the already-completed main run** (T4/T6 detector):
  `es_cruise_throttle` 40 counts, `throttle_body` 2.0, `engine_rpm_140` 30.0,
  `wheel_torque` 20.0, `aego` 0.15, `throttle_cruise` 2.0. Not retuned for this test.
- Events require: ACC engaged throughout, **no driver gas or brake anywhere in the
  measurement window**, no `Cruise_Fault`, the `Car_Follow` transition isolated by ±2s from
  any other transition, the new state sustained ≥1s, and `Cruise_Throttle` not pinned at the
  floor for the whole window (no ordering information available in that case).
- **A gating change was made after a failed first attempt and is disclosed here rather than
  buried:** the cleanliness gates were initially applied over ±3s, which rejected 100% of
  transitions (71/71 on a 12-route sample) and produced no test at all. They were narrowed
  to exactly the measurement window (−1s to +1.2s) on the rationale that a driver input
  *after* the response window cannot retroactively change which signal moved first within
  it. Re-checking on a 60-route sample then yielded 546 raw transitions → 92 clean events,
  confirming the original zero was a small-sample artifact of the first 12 routes rather
  than a structural problem. Residual risk: an input landing just inside the window could
  still create a spurious late onset, which is why the headline statistic is the **≥50ms
  margin fraction**, not raw onset presence.
- **Timing resolution is a hard floor:** `ES_Distance` is 20Hz, so `Cruise_Throttle`'s onset
  is quantized to ±25ms while the powertrain's (100Hz) is not. **A margin under ~50ms is not
  meaningful**, and the conservative reported statistic requires ≥50ms.

Script: `research/es_perception_focus.py`. Results: `research/es_perception_focus_results.json`.

### 5.1 Results — INCONCLUSIVE, and the design flaw that explains why

**Yield was excellent:** 5,583 raw `Car_Follow` transitions across 282 routes → **814 clean
"lead acquired" + 814 clean "lead lost" events** after all gating. (Rejections: 2,450 not
isolated, 688 driver gas, 361 ACC dropped, 236 per-route cap, 201 driver brake, 17
floor-pinned, 2 not sustained.) No shortage of data — this is not a power problem.

**First, a validity check that passed convincingly.** From the retained traces, the
responses are real and physically coherent, not noise:

| event | median Δ`Cruise_Throttle` (−200→+600ms) | direction |
|---|---|---|
| lead **acquired** | **−302.5 counts** | DOWN in 18/22 |
| lead **lost** | **+276.0 counts** | UP in 14/18 |

`Cruise_Throttle` drops when a lead appears and rises when it clears — exactly correct ACC
behavior. These are genuine responses to perception events.

**But the decisive ordering statistic does not deliver.** Positive margin = `Cruise_Throttle`
moved first:

| comparison | n | median margin | CT first | **CT first by ≥50ms** |
|---|---|---|---|---|
| **acquired vs `throttle_body`** | 559 | +30.2ms | 60.1% | **42.6%** |
| **acquired vs `wheel_torque`** | 577 | +20.4ms | 55.1% | **41.6%** |
| acquired vs `engine_rpm_140` | 281 | +390.1ms | 88.3% | 85.4% |
| **lost vs `throttle_body`** | 444 | +49.4ms | 59.5% | **48.4%** |
| **lost vs `wheel_torque`** | 439 | +19.7ms | 50.8% | **46.7%** |
| lost vs `engine_rpm_140` | 244 | +245.0ms | 70.1% | 66.4% |

**Against the fast, direct powertrain signals the result is essentially a coin flip with a
sub-resolution margin.** `Cruise_Throttle` wins the race ~55–60% of the time, but the median
margin (20–49ms) sits **below the ≥50ms meaningfulness floor declared before the run**, and
the conservative ≥50ms statistic is 42–48% — *under half*. Median onsets tell the same
story: on lead-acquire, `Cruise_Throttle` 100ms vs `throttle_body` 110ms vs `wheel_torque`
85ms. Those are simultaneous within one or two 20Hz ES frames, not a lead.

**The `engine_rpm_140` numbers look dramatic and should be discarded as a red herring.**
Beating engine RPM by 390ms is unimpressive because RPM is a slow, filtered, CVT-decoupled
downstream consequence — `throttle_body` *also* beats it by ~280ms. Anything that moves
early beats engine RPM. That comparison carries no command-vs-report information, and
quoting the 88.3% would be misleading.

**Why the test underperformed — a real design flaw, found in the traces.** A representative
lead-acquire trace:

```
  dt_ms   Cruise_Throttle   Car_Follow   Throttle_Body
   -300        3131             0             70
   -200        3128             0             70
   -100        3118             0             70
      0        3110             1             69     <- flag flips here
   +200        3106             1             68
   +600        3058             1             64
```

**`Cruise_Throttle` was already declining ~300ms before `Car_Follow` flipped.** That breaks
the test's core assumption. `Car_Follow` is a *thresholded binary flag on a continuous
internal estimate* — EyeSight has been tracking the closing lead and adjusting its demand
for some time before the flag crosses its threshold. So the flag flip is **not an exogenous
impulse**, and "CT moves at the same time as the flag" doesn't isolate a causal ordering.

It gets worse in a specific, correctable way: the onset detector's baseline window
(−1s to −50ms) is **contaminated by the pre-flip response itself**. That inflates the
baseline sigma for `Cruise_Throttle` specifically — the signal that starts moving earliest —
which *delays* its detected onset and therefore biases the measurement **against** finding a
CT lead. So the weak ~55–60% could understate a real effect. Noted as a consideration, **not
applied as a correction** — adjusting an inconclusive result in the direction one hoped for
is exactly how this analysis would go wrong.

**Verdict: INCONCLUSIVE. The perception-trigger test does not break G1.** My proposal for it
was over-optimistic about achievable timing resolution: the binding constraint is the 20Hz
ES message rate — the same limit flagged in the first writeup's echo section — and on a lead
event EyeSight's response and the powertrain's response fall within one to two ES frames of
each other. The data cannot resolve an ordering at that scale. This is a genuine negative
result about the *method*, not evidence either way about H1.

**The salvageable version, if this is worth another pass.** Restrict to events where
`Cruise_Throttle` is provably *flat* through the entire baseline window (no pre-flip drift),
which selects for genuine surprises — an abrupt cut-in rather than a gradual overtake — and
simultaneously fixes the baseline-contamination bias. That is a real impulse and a clean
baseline. Cost: much smaller N, and it is a **new test design**, not a rerun. It should be
pre-registered before running, given §3's lesson about post-hoc slicing.
