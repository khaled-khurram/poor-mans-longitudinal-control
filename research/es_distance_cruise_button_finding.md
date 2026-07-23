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

## What this does NOT yet establish — real, honest gaps

- **Never tested live, in any form.** Everything above is static code/DBC verification,
  not a live probe. No confirmation the real cruise ECU actually *acts* on a commanded
  `2`/`3`/`4`/`5` value the way it acts on a real physical press — only that the field
  exists, is documented, and is already being transmitted.
- **`shallow` vs `deep` semantics are inferred from the comment, not independently
  confirmed** against this project's own real telemetry the way `CruiseControl`'s
  SET/RES bits were (Q4's 412-event/12-live-press double-confirmation). Worth a passive
  correlation pass against the existing local route archive before ever sending anything
  live — the same low-risk, no-device-needed method already used successfully for Q4.
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
