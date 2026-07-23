# Does CruiseControl (0x144) appear on the camera bus? — real measurement (2026-07-23)

**Top-line: yes, confirmed — but this does NOT mean bus-2 injection would avoid the
collision problem. It's genuinely uncertain, and untested, not a solved workaround.**

## Method

Sampled 50 segments spread evenly across the entire local route archive (one segment
per route, every ~28th route out of ~1,377 total), via `docker exec` into the
`comma-pipeline-route-stats` container (already has `capnp`/`zstandard` installed and
the raw archive mounted at `/data/routes/raw` — much cleaner than fighting host-side
permissions/dependencies). Script: `research/bus_check_script.py`. 50/50 segments parsed
cleanly, 0 failures, ~8.0M raw CAN frames scanned. Raw counts: `research/cruise_control_camera_bus_raw.json`.

## Raw bus-distribution results

| Message | bus 0 | bus 2 | other (128/130/192/194) |
|---|---|---|---|
| CruiseControl (0x144) | 141,472 | **19,884** | 121,547 (code 130) |
| Throttle (0x140) | 282,924 | **39,746** | 480,806 (130) + 319 (194) |
| Brake_Pedal (0xD1) | 141,481 | **19,898** | 240,412 (130) + 171 (194) |
| ES_LKAS (0x164) | 19,617 | **141,141** | 121,562 (128) + 174 (192) |
| ES_Distance (0x161) | 7,830 | **56,443** | 48,625 (128) + 84 (192) |

All five appeared in all 50/50 sampled routes — none of this is rare/edge-case traffic.

## What's solid

**CruiseControl unambiguously appears on bus 2** — 19,884 real frames in this sample,
not zero, not noise. The safety file's RX check (main-bus only) does NOT mean the
message is main-bus-exclusive on the wire; it just means that's the only copy panda's
safety code currently looks at.

**CruiseControl, Throttle, and Brake_Pedal all share the same bus-0-dominant pattern**
(~87% bus 0 / ~13% bus 2, ~7:1 ratio, matching within a percent across all three).
**ES_LKAS and ES_Distance show the opposite, bus-2-dominant pattern** (~1:7 ratio) — and
those two are exactly the messages this project actively transmits on bus 0 today. This
is a real, consistent grouping, not noise.

## What's genuinely unclear — flagged honestly, not resolved here

The "other" bus codes (128, 130, 192, 194) are clearly not junk — they're large,
consistent, and cleanly paired (128↔0, 130↔2, 192↔0, 194↔2 by the pattern). The obvious
guess is "128 = TX-echo flag" (bus number OR'd with 0x80), which would cleanly explain
ES_LKAS/ES_Distance's large "128" bucket (this project genuinely transmits those on bus
0 every drive). **But that guess breaks for CruiseControl**: it shows a large "130"
(bus-2-echo-flag) bucket despite this project never transmitting CruiseControl on
*any* bus in normal driving (confirmed elsewhere — not in any TX allowlist). So either
the "echo" guess is wrong, or something other than this project's own code is producing
that traffic (relay/harness-level behavior is plausible but not confirmed here). Did not
chase this further — flagging as a real open question rather than guessing further.

## Direct answer to the actual question asked

**Does this mean spoofing a button-press on bus 2 would dodge the collision problem
that closed Q9? Unknown — genuinely untested, not ruled out and not confirmed.**

Important distinction: Q9's tests (this session, both `uds_silence_test.py` and
`uds_variations_test.py`'s bus-2 variant) only ever tested the UDS "please stop
transmitting" diagnostic request — asking the ECU nicely to go quiet. Both buses,
both failed (no response, real traffic never stopped). **Nothing tonight actually
tested transmitting a spoofed CruiseControl frame itself** on any bus — that's
categorically blocked right now by panda's safety firmware (0x144 isn't in the TX
allowlist at all, confirmed Q5/closed) and was deliberately not attempted, since doing
so would require either flashing the already-drafted-but-unapplied TX-allowlist patch,
or running panda in a fully unsafe mode — a bigger step than anything taken this session.

So: the bus-2 presence is real and the Throttle/Brake_Pedal precedent shows *some*
version of "spoof on bus 2" can coexist with real bus-0-dominant traffic without
apparent ill effect (that trick is confirmed working in production by real community
reports) — but CruiseControl's own bus-2 traffic being real and substantial (not
absent) means it is NOT obviously a quiet, contention-free channel the way the
Throttle/Brake trick might have implied. Whether injecting there specifically would
collide, be ignored, or actually reach whatever reads it cleanly is a real open
question that would need an actual test to answer — not something this data alone
resolves either way.
