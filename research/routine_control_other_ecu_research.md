# RoutineControl / IOControl / other-ECU UDS precedent — Discord research (2026-07-23)

## Top-line

**No RoutineControl (0x31) precedent found — that angle's a dead end in this corpus.** But
**IOControlByIdentifier (0x2F) has real, first-hand, working precedent from a credible
source (sunnypilot maintainer `sunnyhaibin`)** — gated behind SecurityAccess, likely on a
global-platform car, so doesn't directly resolve preglobal. **The most valuable find is a
different, third thing**: real community discussion reveals the actual message chain for
button-press recognition may not be `CruiseControl` (0x144) at all — it's `ES_CruiseThrottle`,
and this project's own code has a naming inconsistency suggesting that message might already
be `0x161` (`ES_Distance`) — a message **already TX-allowed and already transmitted every
drive**, no new firmware patch needed to test with.

## 1. RoutineControl (0x31) — no real precedent

Grep hits for "0x31" in `subaru` are false positives (NRC `requestOutOfRange` responses, not
the RoutineControl service ID). Zero real discussion found of RoutineControl for
actuator/button simulation on any brand in the searched channels.

## 2. IOControlByIdentifier (0x2F) — real, working, but security-gated and likely global-only

Same May 2023 `subaru` thread already documented in this project's Q9 research (the
`jnewb1`/`sunnyhaibin` exchange, already confirmed global gen1/gen2 context —
"Upstream doesn't have this set for pre global" appears earlier in the same conversation).
Direct quotes:

> `jnewb1`: "There is a write data by identifier, I'd be curious if it does anything if we
> try and write to it"
> `sunnyhaibin`: "That's how some HKG enables radar tracks" [confirms WDBI is a real,
> separately-precedented technique on Hyundai]
> `sunnyhaibin`: "Forgot to say, I'm sending via `0x2F` already."
> `sunnyhaibin`: "Positive response after gaining access via SecurityAccess" ... "Negative
> response when I didn't gain access via SecurityAccess"

This is real: a credible maintainer got `0x2F` to return a **positive response**, gated on
successfully completing `SecurityAccess` first — a genuinely different outcome than this
project's own SecurityAccess test tonight (total silence, no response at all, not even a
negative one). That contrast is itself informative: this ECU/platform implements
SecurityAccess with real responses; this project's preglobal ECU didn't respond at all,
consistent with preglobal lacking the service entirely rather than just needing better
parameters. Not proof either way for preglobal, but real precedent that `0x2F` is a genuine,
usable mechanism *when* SecurityAccess is available — worth retrying if SecurityAccess is
ever cracked for preglobal specifically.

## 3. Which ECU actually owns cruise button state — real answer, and it complicates the picture

Multiple independent, consistent first-hand statements:

> `47247`: "Buttons from the wheel and go to eyesight, then eyesight broadcasts a message to
> the cruise control ecu"
> `82763`: "the buttons are wired directly to eyesight, then eyesight broadcasts this to the
> CAN bus, then the cruise ecu repeats this back to eyesight"

So there's a real, separate "cruise ECU" beyond EyeSight — buttons go to EyeSight, EyeSight
broadcasts, a distinct cruise ECU echoes it back. The next exchange is the important one:

> `82971`: "eyesight would set ES_CruiseThrottle.Button to 1 and this is heard by cruise ecu"
> `82983`: "So even if we fake a CruiseControl.RES_BUTTON signal it only affects Eyesight and
> doesn't properly set the cruise ECU to 'resume' state?"

**This suggests the message that actually matters for the cruise ECU to register a real
button state is `ES_CruiseThrottle`, not `CruiseControl` (0x144)** — this whole project's
button-injection work tonight targeted `0x144` exclusively. Worth checking directly against
this project's own opendbc source: `opendbc/safety/modes/subaru_preglobal.h` has a comment
`// 0x161 is ES_CruiseThrottle` immediately above where `0x161` is actually `#define`'d as
`MSG_SUBARU_PG_ES_Distance` — a naming inconsistency in the codebase itself. If that comment
is accurate rather than stale, `0x161` may carry both distance data and the actual
cruise-throttle/button state the real cruise ECU listens to — and **`0x161` is already in
`SUBARU_PG_COMMON_TX_MSGS`, already TX-allowed, already actively transmitted every single
drive for lateral control.** That would make it a testable avenue requiring zero new
firmware/allowlist changes, categorically different from the `0x144` work done tonight. Not
independently verified in this pass (out of scope — this was a Discord search, not a code
audit) — flagging clearly as a lead to verify, not a confirmed fact.

Also real: `138470`: "stop start button press message and receiving ecu are both on can0 so
spamming the button press may work but it will not be reliable" — corroborates main-bus
placement and matches this project's own bus-contention findings.

## 4. Other-ECU UDS attempts (ABS/EPS/engine/transmission) — nothing found

No discussion found of UDS actuation attempts against `0x7b0`/`0x746`/`0x7e0`/`0x7e1` for
anything button/cruise-related — only FW-fingerprint reads (passive, already known/uneventful).
No evidence for or against these being useful targets.

## 5. WriteDataByIdentifier general precedent (any brand)

Toyota-security channel has repeated raw `WriteDataByIdentifier 0x201`/`0x202` log dumps
(all-zero payloads, no narrative context) — not useful as technique discussion, just log
noise from an unrelated tool run. The Subaru-channel exchange in §2/§3 above is the only real
WDBI/IOControl narrative found anywhere in this corpus.
