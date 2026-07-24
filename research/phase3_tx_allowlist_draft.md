# Phase 3 TX allowlist draft — Subaru preglobal CruiseControl (0x144)

**Status: DRAFT ONLY.** Not applied to the working tree, not committed, not built, not
flashed. This does not authorize transmitting on the real CAN bus — per `claude.md`,
that needs separate explicit confirmation, and Phase 2/3 stays recon/bench-only until
stated otherwise. This file exists purely so the code change isn't a blocker once Q9
(bus-contention research) resolves.

## What this closes

Q5 (progress.md) found that `0x144` (`MSG_SUBARU_PG_CruiseControl`) is not present in
any of `SUBARU_PG_TX_MSGS` / `SUBARU_PG_COMMON_TX_MSGS` / `SUBARU_PG_STOP_AND_GO_TX_MSGS`
in `opendbc/safety/modes/subaru_preglobal.h` — so panda's safety firmware would reject
any attempt to transmit it, full stop, regardless of what the higher-level code tries to
send. The patch adds it to `SUBARU_PG_COMMON_TX_MSGS`, which is unconditionally included
in the TX allowlist (both the plain and stop-and-go variants build from
`SUBARU_PG_COMMON_TX_MSGS`, see `subaru_preglobal_init()`), since button-press injection
isn't gated behind the stop-and-go/interceptor feature — it's a separate mechanism.

## Reasoning for each field

- **Bus = `SUBARU_PG_MAIN_BUS`**: matches where the RX check already reads `0x144` from
  (`subaru_preglobal_rx_checks`, line ~104 in the current file) — TX has to target the
  same bus the real ECU listens/transmits on for a spoofed frame to actually collide with
  (or replace) the real one, which is the entire point of Q9.
- **Length = 8**: matches the existing RX check entry for the same message.
- **`.check_relay = false`**: This is the one modeled directly on precedent rather than
  invented. In `opendbc/safety/modes/honda.h`, the SCM_BUTTONS message (`0x296`) — Honda's
  equivalent "spam a button state over CAN" message — is allowlisted with
  `.check_relay = false` in every TX_MSGS variant (`HONDA_BOSCH_TX_MSGS`,
  `HONDA_RADARLESS_TX_MSGS`, `HONDA_CANFD_TX_MSGS`), while genuinely continuous
  camera/radar control messages (`0xE4`, `0xE5`, `0x33D`) use `.check_relay = true`.
  `check_relay = true` is for messages the safety firmware expects to see steadily
  relayed/forwarded; a button message that's only sent while a button is actively being
  "pressed" fits the `false` pattern, same as this file's own `ES_Distance`/`ES_LKAS`
  (`true`, continuous) vs. what `0x144` would be (event-driven) — so `0x144` follows
  Honda's `0x296` pattern rather than this file's own `ES_Distance`/`ES_LKAS` pattern.

## What was deliberately left out — open questions

**No `tx_hook` value-restriction check was added.** Honda's `0x296` has one:

```c
// FORCE CANCEL: safety check only relevant when spamming the cancel button in Bosch HW
// ensuring that only the cancel button press is sent (VAL 2) when controls are off.
if ((msg->addr == 0x296U) && !controls_allowed && (msg->bus == bus_buttons)) {
  if (((msg->data[0] >> 5) & 0x7U) != 2U) {
    tx = false;
  }
}
```

I did not draft a Subaru equivalent, because — unlike Honda's `0x296`, which is a
dedicated, pure button-state message — Subaru's `0x144` (`CruiseControl`) is a shared
message that also carries live state this project already relies on elsewhere:

- `cruise_engaged` at byte6 bit1 (read in `subaru_preglobal_rx_hook`)
- `acc_main_on` at bit 48 (also read there)
- at least one more bit (byte1 bit0) noted in progress.md Q4 as "almost certainly a
  rolling counter/heartbeat" — unconfirmed, not yet decoded

Honda's model works because `0x296` carries *only* button state, so "restrict which byte0
top-3-bits value is allowed" is a complete, correct check on its own. For `0x144`, a
naive port of that idea only validates the button bits and says nothing about what the
other live fields should be set to in an injected frame. Two real open design questions
follow from that, and I didn't want to guess at either and present it as settled:

1. **Does an injected frame need to mirror the real ECU's current state for the
   non-button fields** (cruise_engaged, acc_main_on, the unknown heartbeat bit), i.e.
   read-modify-send off the last real RX'd `0x144`, rather than constructing a frame from
   scratch? Sending a frame with those fields zeroed/wrong could desync whatever else on
   the bus reads them.
2. **What value-bounds check is even correct here?** Honda's is "exactly VAL 2 (cancel)
   when disengaged." Subaru's SET/RES are two independent bits (byte0 bit3/bit4), not an
   enum, and this project's use case (per the project's own framing, "poor-man's
   longitudinal control" via button spam) plausibly wants either bit assertable — so the
   check isn't "only one specific value," it's closer to "only bits 3/4 of byte0 may
   differ from a real captured frame, everything else must match a real observed value."
   That's a materially different (and more involved) check than Honda's, not a drop-in
   port.

Both are real engineering questions, not just formalities — recommend resolving them
(and writing the actual `tx_hook` restriction) as a distinct follow-up task once Q9 is
answered and this is actually about to be tested on a bench, not before. Shipping a
guessed-at value check here would be the same mistake progress.md §7.1 already flagged
in the earlier deep-research pass (specific-sounding but unverified claims) — better to
leave it explicitly open than invent something that looks more finished than it is.

## Not addressed here at all

- The actual bus-contention problem (Q9) — does injecting `0x144` even work without the
  real transmitter also being on the bus and colliding? That's the other parallel task.
- Rate limiting / anti-spam protection on the injected message.
- Whether `SUBARU_PG_TX_MSGS` (used for the non-stop-and-go build) vs.
  `subaru_pg_stop_and_go_tx_msgs` needs different treatment — this draft puts the entry
  in `SUBARU_PG_COMMON_TX_MSGS`, which both already include, so no further change needed
  there, but worth double-checking against whichever variant is actually running before
  this is ever applied.

## How to apply (when actually ready, not now)

```
cd ~/long_control/openpilot/opendbc_repo
git apply ~/long_control/research/phase3_tx_allowlist_draft.patch
```

Not run as part of this task.
