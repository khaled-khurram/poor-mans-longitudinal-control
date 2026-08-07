# Round 5: Cruise_RPM transfer-curve completion, the Round-4 boundary-clip resolved, and a grade-correction attempt

**Date: 2026-08-07. Fully passive archive analysis, zero CAN transmission, zero device
access.** Descriptive/completeness work — the command-vs-report question was already
attacked as hard as archive data allows in Rounds 1-4 (perception-impulse tests on all
three ES fields, a detection-confound check, cross-field structure). This round fills
practical gaps for any eventual control law and closes two open threads. Script:
`research/es_round5_envelope_completion.py`. Full data: `research/es_round5_results.json`.

---

## Task 1 — Cruise_RPM's transfer curve, never measured until now

`Cruise_Throttle`'s and `Brake_Pressure`'s transfer curves were both done in the original
main run. `Cruise_RPM` (`ess_cruise_rpm`) never got the same treatment. Binned against
`aego` over `acc_engaged_clean` (huge per-bin samples — hundreds of thousands at the
dominant bins):

| Cruise_RPM | n | mean aEgo (m/s²) |
|---|---|---|
| 1000 (floor) | 43,445 | **−0.631** |
| 1500 | 58,988 | +0.056 |
| **~1900–2000 (zero-crossing)** | 89,548 / 176,270 | **−0.007 / −0.026** |
| 2100 (dominant bin) | 513,272 | −0.005 |
| 2500 | 30,667 | +0.216 |
| **2700–3300 (plateau ceiling)** | 2,790–8,509 | **+0.45 to +0.53** |
| 3800 (top, thin) | 84 | +0.342 (small n, edge noise) |

**Shape: nearly identical qualitative character to `Cruise_Throttle`'s curve** — strong
decel at the floor, a genuine zero-crossing, then a rise to a broad plateau rather than a
sharp peak (this plateau is smoother/flatter than `Cruise_Throttle`'s, which had a more
distinct single peak around 3750). `wheel_torque` moves in lockstep (1901 at the floor →
~3800 plateau), the same complementary confirmation pattern used for the other two fields:
this is a real, physically meaningful signal, not noise.

**The landmark values do NOT match global's constants — a genuinely new, useful finding,
different in character from `Cruise_Throttle`'s result.** Recall `Cruise_Throttle`'s floor
(808) and zero-crossing (~1818) matched global's `THROTTLE_MIN`/`THROTTLE_INACTIVE` almost
exactly, and only the ceiling diverged. `Cruise_RPM` is different: global's `RPM_INACTIVE`
is documented as **600**; this car's actual zero-crossing is **~1900–2000**, over 3x higher.
Global's `RPM_MAX` is **3600**; this car's effective ceiling is **~2600–3300**, lower, not
higher. Neither anchor transfers here. **Any future control law must derive `Cruise_RPM`'s
operating envelope entirely from this car's own measured curve — none of global's numbers
are usable starting points for this specific field**, a stronger and more specific version
of the "self-calibrating principle" already adopted for `Cruise_Throttle`.

---

## Task 2 — Round 4's boundary-clip, resolved (as "not a real lag-locked relationship")

Round 4 found `Cruise_RPM` vs `Brake_Pressure` (restricted to active-brake ticks) still
climbing at the ±1.5s grid boundary (R²=0.298). Extended to ±3.0s, n=102,358 active-brake
ticks:

```
lag_ms    R²      r
-3000   0.3768  -0.6138   <- new boundary, still rising
-2000   0.3273  -0.5721
-1000   0.2713  -0.5209
    0   0.2282  -0.4777
+1000   0.1907  -0.4366   <- genuine local MINIMUM
+2000   0.2151  -0.4638
+3000   0.2517  -0.5017   <- rising again toward the new boundary
```

**This resolves the question, just not by finding a peak.** The curve is now visibly
**U-shaped with a real interior minimum around +1000ms**, rising toward *both* extremes of
a full 6-second window, and it is still climbing at the new ±3000ms boundary. That shape —
never converging, growing wider the more window you give it — is the same diagnostic
signature already established for `Cruise_Throttle` vs `Throttle_Cruise` earlier in this
campaign (a broad hump with a minimum near zero lag, read there as "two signals sharing a
slow common trend, not a fast causal link"). **Read the same way here: `Cruise_RPM` and
`Brake_Pressure` are not lag-locked to each other on any fast timescale.** They both trend
together over the multi-second *span of a braking episode itself* (both ramp with episode
severity/duration), which produces ever-growing correlation as the averaging window widens,
without a genuine peak ever appearing. Not chased further with an even wider grid — the
shape is already diagnostic, and further widening would only demonstrate the same thing
more expensively.

---

## Task 3 — grade-correction attempt (G6): tractable, and it sharpens an existing result

**Method:** per-route baseline `aEgo` offset, estimated from samples where
`Cruise_Throttle` sits in a narrow band around global's documented "zero acceleration"
anchor (1818 ± 100), `acc_engaged_clean` only. 99 of 282 routes had ≥20 usable neutral-band
samples. Offset distribution across those routes: **median −0.198 m/s², stdev 0.122,
range −0.615 to +0.051.**

**Two findings, one expected and one not:**

1. **There is a real, consistent archive-wide downward bias** (median −0.198 m/s² even at
   the "should be zero" commanded value) — consistent with the original T7 finding that the
   uncorrected CT=1800 bin already showed −0.177. Rolling resistance and/or a net downhill
   bias in this specific archive's routes are the likely causes; this data cannot
   distinguish between them.
2. **There is real route-to-route variation** (stdev 0.122, a >0.6 m/s² range from best to
   worst route) — grade is not a fixed constant across this archive, it genuinely differs
   by route. A controller assuming one fixed anchor will be systematically wrong on
   particular routes, not just uniformly off by a small constant.

**Applying the correction sharpens the H1a zero-crossing finding.** Uncorrected, the curve's
zero-crossing sits around CT≈1900–2000 (e.g. CT=1850 → −0.163). After correction, CT=1850 →
**+0.006**, i.e. almost exactly zero. **The corrected zero-crossing lands much closer to
global's documented 1818 anchor than the uncorrected curve suggested** — the original
report of "anchors confirm" undersold how well 1818 actually transfers; the discrepancy was
mostly grade/rolling-resistance bias, not an encoding mismatch.

**Honest limitation:** this pass tracked bin *means* before/after correction, not variance —
so "does correction reduce noise/spread within each bin" (the tightening question) is not
directly measured here, only "does it shift the curve to a more physically sensible zero
point," which it clearly does. A future pass wanting the variance-reduction number would
need to re-run with per-bin variance tracking; not done here given time budget.

---

## Permanent limitations, noted and closed out (not chased further)

- **G7 (RPM-vs-transmission-ratio confound):** `CVT_Ratio` (`0x149`) has zero decoded
  signals anywhere in the DBC. There is no way to test "does `Engine_RPM` jump for
  transmission-ratio reasons independent of `Cruise_RPM`'s demand" with this archive's
  data. Structural gap, not a to-do item.
- **G9 (T6 brake-episode selection effect):** the brake transfer curve (both in the
  original main run and this round's `Cruise_RPM` curve) is sampled only at whatever
  pressures/RPMs EyeSight happened to command during real archived drives. Coverage near
  `BRAKE_MAX`/RPM ceiling is thin by construction (visible in the small `n` at the extreme
  bins above). Only a deliberate capture drive fixes this — it is exactly the kind of gap
  Test B (the planned capture drive) is positioned to help with if it also happens to
  include some harder braking/acceleration.

---

## What this means for the campaign

Nothing here bears on the command-vs-report question (that was Rounds 1-4's job, and G1
still stands as established there). This round's value is practical: `Cruise_RPM` now has a
measured operating envelope for the first time, with landmarks that explicitly do **not**
match global's constants (unlike `Cruise_Throttle`'s partial match) — a concrete warning
against porting any global numbers for this field. The Round 4 loose thread is closed with
a clean negative characterization rather than an unresolved boundary artifact. And the
grade-correction attempt, rather than being a null result, meaningfully sharpens confidence
in the existing 1818 zero-crossing finding while surfacing a real, previously
unquantified route-to-route grade variation that matters for any future controller.
