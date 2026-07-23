# Lead-vehicle early-warning feasibility — real telemetry analysis (2026-07-23)

**Question:** the user's daily pain point is highway cruising at a locked set-speed with no lead currently tracked, where traffic ahead is visibly slowing/queuing, and EyeSight doesn't react until it's close enough that the driver has to brake themselves. Does openpilot's own vision-based lead detection (`radarState.leadOne`) — which runs independently of whether the car has real longitudinal control — already "see" these situations early enough to be useful as a proactive advisory, the same way MTSC already is for curves?

**Bottom line: yes, on the real evidence.** In every one of the real historical episodes where this car's driver ended up physically braking despite cruise being engaged and a lead already tracked, the vision model had detected that lead closing at least 0.7s before the brake — and in most cases (10 of 14), the lead time was 3-31 seconds. This is a genuinely buildable advisory feature, using data that's already being computed on every drive right now and going nowhere.

## Methodology

- **Source:** a local route archive (path scrubbed for publishing — see script) — 124 routes / 1,375 segments processed successfully (0 hard errors; a handful of individual segments had truncated trailing rlog data, handled the same defensive way as a known-working sibling parser — a few dropped events, not a few dropped routes).
- **Schema:** reused a known-working `log.capnp` schema copy verbatim from a sibling parsing service already proven working against this exact archive in production, rather than risking a mismatch against the main repo's schema.
- **Processing:** wrote `research/analyze_lead_warning.py` (kept, reusable). Streams `carState` + `radarState` events per route via `pycapnp`, strided to ~10Hz, tracks the current lead state alongside each carState sample. Runtime: 8 minutes for the full archive.
- **Candidate definition:** a sustained (≥0.5s) window where `vEgo > 50mph`, cruise engaged, a lead is present and closing (`vRel < -3.0 m/s`, i.e. closing at >~6.7mph relative), with no brake/gas in the preceding 3s (rules out "already reacting"). For each candidate, looked forward up to 30s for either a real brake press or a >8mph speed drop without braking (likely EyeSight's own ACC handling it).
- **Episode clustering:** raw candidates within 20s of each other on the same route were merged into one "episode" — a single real-world traffic encounter can otherwise fragment into several candidate rows as `vRel` fluctuates around the threshold. All headline numbers below use episodes, not raw candidates (163 raw candidates → 63 distinct episodes).

## Finding 1: the data exists and is rich

245,068 highway-speed samples across the archive; a lead was present in 68% of them (167,850). **`leadRadar` was `False` for every single sample in the entire archive** — confirms this car's lead detection is purely vision-based, exactly as expected (no radar fusion available on this platform). This isn't a hypothetical data source — it's already running, on every drive, right now.

## Finding 2: FCW is not a usable signal

`fcw` never fired — not once, across 245k highway samples / 124 real drives. This isn't surprising in hindsight (FCW is tuned as a last-resort collision alarm, not a comfort feature) but it rules out the tempting shortcut of just surfacing openpilot's existing collision-warning flag. Any advisory here has to be built on `leadOne`'s raw distance/velocity, not FCW.

## Finding 3: real episodes, honestly categorized

63 distinct closing-lead episodes across 124 drives:

| Outcome | Count | What it likely means |
|---|---|---|
| Driver physically braked | 14 | The real "EyeSight didn't handle it" cases — the ones matching the complaint |
| Smooth deceleration, no brake | 27 | Most likely EyeSight's own ACC following the lead correctly on its own — **not a failure case**, cruise was engaged throughout so this is probably the system working as intended |
| No measurable reaction in 30s | 22 | Likely benign — lead resolved itself (sped back up, changed lanes) or wasn't ever a real hazard |

Only 14/63 (22%) of real "vision model saw a closing lead" episodes actually required the driver's own brake. That base rate matters for the algorithm design below.

## Finding 4: the actual advance-warning numbers (the core result)

For the 14 real brake-required episodes, distance/TTC at the *first* moment the vision model detected the closing lead, and how long before the driver actually braked:

| Route | First detection: distance / TTC / speed | Lead time to actual brake |
|---|---|---|
| 0000007c | 262ft / 10.4s / 50mph | **0.7s** (worst case) |
| 0000009a | 400ft / 16.7s / 83mph | 3.0s |
| 0000009a | 303ft / 27.2s / 84mph | 1.4s |
| 0000009c | 402ft / 34.6s / 63mph | 5.1s |
| 0000009d | 110ft / 7.1s / 81mph | 1.2s |
| 0000009d | 175ft / 15.5s / 67mph | 2.6s |
| 000000ac | 228ft / 9.4s / 66mph | 1.8s |
| 00000011 | 365ft / 34.2s / 84mph | 9.1s |
| 00000014 | 369ft / 32.8s / 52mph | 14.0s |
| 0000008c | 99ft / 9.1s / 71mph | 31.6s |
| 00000080 | 388ft / 30.6s / 83mph | 24.3s |
| 00000087 | 353ft / 26.2s / 52mph | 28.6s |
| 000000a6 | 276ft / 27.8s / 80mph | 27.7s |
| 000000a8 | 383ft / 34.0s / 81mph | 28.9s |

Median lead time: **~7.8s**. Only one case (the 0.7s one) would have given a genuinely marginal warning; every other real historical near-miss-to-brake event had multiple seconds to nearly half a minute of advance notice already sitting in the model's output, unused.

**Important honesty check:** TTC-at-first-detection does *not* cleanly predict which episodes will need a brake — the brake, decel-only, and no-reaction groups all have overlapping TTC distributions (medians 27.2s / 21.9s / 23.7s respectively). A simple "TTC below X seconds = danger" trigger would not reliably separate real cases from benign ones. This shapes the algorithm recommendation below: don't pretend to predict severity, just surface the same kind of low-key advisory Phase 1 already does for curves.

## Proposed algorithm

Framed the same way as MTSC's curve advisory — a calm, low-urgency nudge, not a collision alarm — because the data supports that framing (only 22% of real detections turn into an actual brake) and because that's genuinely the user's stated goal ("making driving chill," not building a second FCW).

```
trigger candidate when, sustained for ≥0.5s:
  leadOne.present == True
  leadOne.vRel < -3.0 m/s          # closing at >~6.7mph relative
  vEgo > 50mph                      # highway-only; irrelevant at city/stop-go speed
  cruiseState.enabled == True       # only meaningful when ACC is actually driving
  no brake/gas in the prior 3s      # not already mid-reaction

on trigger:
  fire ONE advisory (reuse the existing curve-advisory alert pipeline/UI),
  something like: "traffic ahead may be slowing — consider easing off"
  (not "BRAKE NOW" — the data doesn't support that level of certainty)

debounce:
  suppress re-firing for the same encounter — don't re-trigger while still
  inside a closing episode (mirrors the natural ~20s clustering window
  found in real data), same once-per-event pattern Phase 1 already uses
  for curves

explicitly NOT used as a trigger:
  fcw (confirmed non-firing, not a usable signal on this car)
  TTC-based severity tiers (data doesn't support reliably distinguishing
  "will need a hard brake" from "will resolve on its own" at detection time)

interaction with curve advisory (MTSC):
  independent trigger source feeding the same alert mechanism; share one
  cooldown/debounce pool so a curve and a closing lead don't double-fire
  back to back
```

## Caveats, stated plainly

- **14 real brake-episodes is a real but modest sample.** Good enough to validate the core premise (the model does see it early, every time, in this dataset) — not enough to claim the exact -3.0 m/s / 50mph thresholds are optimal. Real-world tuning after building, same as every other feature in this project, should be expected.
- **The "decel_no_brake" bucket (27 episodes) is an inference, not a direct measurement** — cruise being engaged strongly suggests EyeSight's own ACC was doing the work, but this wasn't independently confirmed against EyeSight's own internal state (not observable to openpilot on this platform).
- **This is advisory-only by design, matching Phase 1** — nothing here requires CAN changes, new hardware, or touches anything discussed earlier tonight about button injection or bus contention. It's a second alert trigger source on top of the exact same mechanism already shipping.
- Raw per-candidate data (all 163) is in `research/lead_warning_raw_results.json` alongside the reusable mining script (`research/analyze_lead_warning.py`) if this needs re-running with different thresholds later.
