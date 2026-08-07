# Capture drive #1 — first real data against the Test B / Test C pre-registration

**Date: 2026-08-07, evening. First deliberate capture drive per
`research/es_capture_drive_protocol.md`.** ~43 minutes across 4 routes (`000000c9`,
`000000ca`, `000000cb`, `000000cc` — synced via the normal comma-device rlog pipeline over
Tailscale, no device access from this environment, same as every round tonight). Scripts:
`es_capdrive1_ct_test.py`, `es_capdrive1_rpm_test.py` (perception-impulse, Test C),
`es_capdrive1_testB.py` (gas-override, Test B) — each a route-restricted copy of the
already-validated Round 1/2 scripts and the T5 detector, decision rules unchanged.

**Headline: nowhere near either power floor yet, exactly as predicted in the protocol
before this drive happened. This is expected, not a disappointing result — it's data point
one of several needed.**

---

## A real bug found and fixed before trusting any of this

The first version of the Test B extraction script computed each event's outcome
(`throttle_body` delta at `t+1500ms`) **immediately at detection time**, before that much
future data had actually streamed into the buffer — every single delta came back `None`
(195/195 events). This is the exact class of bug the "settle-then-drain" pattern in every
other script tonight exists to prevent, and this one-off script skipped it. Fixed by adding
the same pending-queue/settle-window pattern used everywhere else. Flagged here rather than
silently patched, per the standing rule for this whole campaign.

---

## Test C — perception-impulse (the main event)

| | `Cruise_Throttle` | `Cruise_RPM` |
|---|---|---|
| Raw `Car_Follow` transitions | 235 | 235 |
| Rejected: driver gas/brake in window | 25 / 4 | 25 / 4 |
| **Rejected: not isolated (±2s)** | **129** | **129** |
| Rejected: baseline not flat | 34 | 14 |
| Rejected: no real response | — | 17 |
| **Qualifying (primary set)** | **4** | **7** |
| verdict | INCONCLUSIVE (n=4 « floor of 100) | INCONCLUSIVE (n=7 « floor of 100) |

**The raw trigger rate is genuinely encouraging.** 235 raw `Car_Follow` transitions in ~43
minutes works out to roughly **4x the archive's average rate** (the full 282-route archive
produced 5,583 transitions across many times more driving time). The "prefer lane changes
and merges" instruction clearly worked — this car saw a lot more lead-vehicle events per
minute than ordinary incidental driving does.

**The dominant rejection reason was "not isolated" (129 of 235, 55%)** — a real, useful
operational finding for the next drive. Doing these maneuvers in genuinely dense traffic
(exactly where lane-change opportunities are easiest to find) means nearby cars keep
shuffling your lead status within the ±2s isolation window, which the test needs to be clean.
**Lesson for drive #2: moderate traffic — enough for one clear target car, not a weaving
pack — will convert more raw transitions into qualifying ones.**

At N=4 and N=7, **the specific percentages (0% and 57.14% CT/RPM-first) mean nothing on
their own and should not be read as a trend** — that's a coin-flip's worth of samples. They
are not reported as directional evidence, only as confirmation the pipeline is working end
to end.

### A real trace from tonight's drive

One of the 4 qualifying `Cruise_Throttle` events, illustrating what a "clean" one looks like
(flat for a full second, then a real move right around the flag flip):

```
 dt_ms  Cruise_Throttle  Car_Follow  Throttle_Body
  -600       3346              0          86
  -200       3362              0          88
   -50       3356              0          88
     0       3346              1          88   <- flag flips
    50       3346              1          87
   100       3318              1          86
   200       3312              1          83
```

`Cruise_Throttle` and `Throttle_Body` both start moving within the same ~50–100ms window —
consistent with everything found tonight: real, physically meaningful movement, timing too
close to call at this sample size.

---

## Test B — gas overrides

Only **1 usable event landed in the mid-range 2600–3100 band**, and 1 in the floor-band
control group (n=30 required). **Far short of the floor — this drive was mostly Test C
maneuvers, matching what you said going in ("lots of test 3's, some test 2's").** No verdict
possible yet; needs a session actually focused on repeated gas-tap reps in the target band.

---

## What this drive actually accomplished

- Validated the whole capture-drive pipeline end to end, for the first time, on real
  deliberately-collected data — sync, decode, gating, scoring all worked (after the one fix
  above).
- Found a real, fixable bug before it could contaminate anything.
- Confirmed the "prefer abrupt lane changes" strategy meaningfully raises the raw event rate
  (4x the archive baseline).
- Surfaced a concrete, actionable lesson for drive #2 (moderate traffic, not dense).
- **Did not, and was never going to, single-handedly reach either power floor.** Per the
  protocol: continue accumulating across future drives, and re-run these same three scripts
  against the growing set of capture-drive routes each time.

**Next drive should weight more toward Test B specifically** (this one leaned almost
entirely Test C), and toward moderate rather than dense traffic for Test C.
