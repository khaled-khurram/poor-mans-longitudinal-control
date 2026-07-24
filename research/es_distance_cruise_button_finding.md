# ES_Distance's Cruise_Button field — a live, already-active button-command channel (2026-07-23)

## Top-line

**This preglobal Subaru already has a working, currently-running, fully safety-allowed
mechanism for sending virtual SET/RESUME cruise button commands — via `ES_Distance`
(`0x161`), not `CruiseControl` (`0x144`), the message this entire project's Q9/Phase-3
CAN work focused on all night.** Verified directly against this car's actual DBC and
control code, not inferred from documentation or community chat. Never tested live.
Written up for someone (human or AI) with a clearer head/more time to pick up.

## How this was found

A Discord-research pass (searching for RoutineControl/IOControl UDS precedent) surfaced a
community exchange suggesting the real message the "cruise ECU" listens to for button
state might be called `ES_CruiseThrottle`, not `CruiseControl` — and noted this project's
own `opendbc/safety/modes/subaru_preglobal.h` has a comment (`// 0x161 is
ES_CruiseThrottle`) that doesn't match the actual `#define` name at that address
(`MSG_SUBARU_PG_ES_Distance`). Flagged explicitly as unverified — a Discord search, not a
code audit. Verified directly afterward; it checked out, and further.

## What's actually verified, directly, in the real code

**1. `ES_Distance` (`0x161`) carries a discrete button-command field, not just distance
data.** From `opendbc/dbc/generator/subaru/_subaru_preglobal_2015.dbc` (the actual DBC
used to build this exact car's interface):

```
BO_ 353 ES_Distance: 8 XXX
 SG_ Cruise_Throttle : 0|12@1+ (1,0) [0|4095] "" XXX
 ...
 SG_ Cruise_Button : 48|3@1+ (1,0) [0|7] "" XXX
...
CM_ SG_ 353 Cruise_Button "1 = main, 2 = set shallow, 3 = set deep, 4 = resume shallow, 5 resume deep";
```

A 3-bit field, 5 documented states, distinguishing shallow (1mph-step) from deep (5mph-step)
presses for both SET and RESUME — a materially richer, already-decoded command surface
than the plain SET/RES bits on `CruiseControl` that Q4 spent two rounds of real telemetry
confirming.

**2. This project's own control code already builds and sends this field, every single
frame, unconditionally for this platform.** From `opendbc/car/subaru/carcontroller.py`:

```python
if self.CP.flags & SubaruFlags.PREGLOBAL:
  if self.frame % 5 == 0:
    # 1 = main, 2 = set shallow, 3 = set deep, 4 = resume shallow, 5 = resume deep
    if pcm_cancel_cmd:
      cruise_button = 1
    elif not CS.out.cruiseState.available and CS.ready:
      cruise_button = 1
    else:
      cruise_button = CS.cruise_button
    ...
    can_sends.append(subarucan.create_preglobal_es_distance(self.packer, cruise_button, CS.es_distance_msg))
```

No `openpilotLongitudinalControl` gate on this block at all — it runs on every preglobal
car regardless of long-control support, including this one, right now, every drive.
Currently `cruise_button` just relays `CS.cruise_button` (the real, physical button state,
read in `carstate.py` from `cp_cam.vl["ES_Distance"]["Cruise_Button"]` — i.e. EyeSight's
own camera-bus broadcast) except in the two special-cased conditions above. The pathway to
command `2`/`3`/`4`/`5` instead of relaying is already built, already wired to a real CAN
send, already running — nothing new needs to be added to make this fire, only to make it
fire with a software-chosen value instead of a passively-relayed one.

**3. This message is already in the TX allowlist, already transmitted on the main bus,
already working in production — the same category as steering, not `CruiseControl`.**
`opendbc/safety/modes/subaru_preglobal.h`:

```c
#define SUBARU_PG_COMMON_TX_MSGS \
  {MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
  {MSG_SUBARU_PG_ES_LKAS,     SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
```

`ES_Distance` sits in the exact same allowlist entry pattern as `ES_LKAS` — the message
that already carries this project's real, working lateral control every single drive,
with zero collision issues, because openpilot is the authoritative relayed source of it on
the main bus (the same reason `ES_LKAS` doesn't collide with anything). This is a
structurally different situation from `CruiseControl`, which was never in the allowlist at
all (Q5) and, even in the drafted-but-unapplied patch, would still face a live competing
main-bus transmitter (Q9's entire bus-contention problem). `ES_Distance` does not appear
to have that problem, because openpilot already owns its main-bus transmission today.

## Empirical passive correlation (2026-07-23, later still)

Ran the suggested first step: correlated `ES_Distance`'s `Cruise_Button` (bus 2, camera —
matches `carstate.py`'s own `cp_cam.vl["ES_Distance"]["Cruise_Button"]` source) against
Q4's already-confirmed real `CruiseControl` SET/RES bit edges (bus 0, main — matches
`cp_cruise`), across the full local archive (136 routes, 1,476 segments, 0 fatal route
errors). Script: `research/es_distance_correlation.py`, run inside the
`comma-pipeline-route-stats` container. Raw output: `research/es_distance_correlation_results.json`.

**SET/RES → `Cruise_Button` message-level mapping: confirmed, cleanly, at real scale.**
592 real button-press edges found:

| direction | n | `Cruise_Button` value at press |
|---|---|---|
| SET | 216 | `2`: 116 (53.7%), `3`: 96 (44.4%), `0`: 4 (1.9%) |
| RES | 376 | `5`: 209 (55.6%), `4`: 165 (43.9%), `0`: 2 (0.5%) |

98–99.5% of real presses landed on exactly the DBC-documented set (`2`/`3` for SET,
`4`/`5` for RES) — never a RES press reading `2`/`3` or a SET press reading `4`/`5`.
The 6 stray `0`s (1% combined) are the only anomaly, most plausibly a first-frame/no-data
artifact at route start rather than a real semantic collision (not chased further).
Freshness of the `Cruise_Button` value used at each press: median 29.5ms, p95 49.9ms, max
60.0ms staleness — comfortably inside a single button-press duration, so this isn't an
artifact of using a stale reading. **This closes the main open question**: `Cruise_Button`
on `ES_Distance` really does track real SET/RESUME presses in the field, at production
scale, not just in the DBC comment.

**`shallow` vs `deep` (the `2`-vs-`3` / `4`-vs-`5` split): still genuinely open, not
resolved by this pass.** Cross-referenced against real `carState.vCruiseCluster` deltas
following each press (400 usable samples after excluding a `255.0` sentinel/invalid
readings). Result: **both `2` and `3` (and both `4` and `5`) are dominated by ~5mph
deltas**, with a smaller population of ~1mph deltas mixed into *both* buckets, plus noisy
outliers (some deltas of 20–100+ mph, physically impossible for a single press). This
doesn't refute the shallow/deep hypothesis, but doesn't confirm it either — the likely
culprit is methodology: a 2.5s lookahead window for "the next distinct cluster value" is
long enough to catch multiple presses in a burst/spam sequence (this car's rocker is
known to be spam-vs-hold sensitive, see Q1–3), so a single press's isolated effect isn't
cleanly separated here. Resolving this needs a tighter method — e.g. isolate single,
solitary presses only (no other press within some window before/after) — or a live test
like the one that double-confirmed Q4's bits.

## What this does NOT yet establish — real, honest gaps

- **Never tested live, in any form.** Everything above is static code/DBC verification
  plus passive correlation, not a live probe. No confirmation the real cruise ECU actually
  *acts* on a **commanded** `2`/`3`/`4`/`5` value the way it acts on a real physical press
  — the correlation above confirms the field's real-world *meaning*, not that writing it
  in software would be obeyed the same way.
- **`shallow` vs `deep` semantics remain unconfirmed** by real telemetry (see above) —
  the SET/RES-vs-message-value mapping is now solid, but which of `2`/`3` is the 1mph
  step and which is the 5mph step is still just the DBC comment's word for it.
- **Whether `Cruise_Fault`/`Standstill`/`Car_Follow`/`Cruise_Brake_Active` (the other
  real-state fields in the same message, currently passed through verbatim from
  `es_distance_msg`) need to stay consistent with reality while `Cruise_Button` is
  software-commanded** is an open design question, not yet worked through — same category
  of open question the drafted (unapplied) `CruiseControl` TX patch flagged and
  deliberately left open rather than guessing.
- **Not clear this avoids every failure mode from tonight** — `CruiseControl` injection
  triggered an EyeSight-off fault via a stale-counter mismatch, a failure mode one layer
  above plain CAN bus errors. `ES_Distance` already gets re-transmitted with a live,
  correctly-incrementing counter every frame (it's actively used for steering-adjacent
  purposes already), which is a meaningfully different situation — but that reasoning has
  not been tested, only inferred.

## Suggested first real step, if/when this gets picked back up

The same discipline this project has used all along: **verify against real, already-logged
telemetry before ever transmitting anything.** The local route archive already has
`ES_Distance`/`Cruise_Button` on every single recorded drive. A passive correlation pass —
does `Cruise_Button` actually read `2`/`3`/`4`/`5` at the moments real SET/RESUME presses
are known to have happened (cross-referenced against `CruiseControl`'s already-confirmed
bits from Q4) — would confirm the shallow/deep semantics and the field's real-world
reliability with zero device access and zero risk, exactly like Q4 was closed. That's the
next step before any live test, not a live test itself.
