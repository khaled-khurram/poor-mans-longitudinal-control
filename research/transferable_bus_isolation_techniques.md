# Transferable CAN-bus isolation techniques — Discord research (2026-07-23)

**Directive:** search for community discussion of physically isolating a stock ADAS/camera/radar
module's CAN connection on ANY car brand, on modern comma hardware, as a transferable technique
for Subaru EyeSight isolation — since the only Subaru-specific hardware found so far (the 2021
"Giraffe" PCB) requires an old standalone Panda this project's comma 4 doesn't have.

## Top-line: real, substantial, directly transferable precedent found — and it does NOT require
## new custom hardware. The mechanism may already be present in the harness this project already has.

## The core finding

The isolation mechanism isn't a special board — it's the **stock comma harness relay**, combined
with **panda's software forwarding hook (`fwd_hook`)**. Real, technically precise explanation from
`jyoung8607` (dev-openpilot, 2/15/2022 and 10/25/2023 — same person, consistent across a year+):

> "you make a harness to break the relevant CAN bus and stick the comma harness relay in the
> middle" ... "when the relay is closed (default, not running, etc) the buses are electrically
> bridged and everything works just like from the factory" ... "when openpilot wants to drive, it
> opens the relay and it can address both sides independently"

> "With the relay closed, buses 0 and 2 are electrically bridged... Soon as you open the relay,
> buses 0 and 2 are split, and the OBD-C wiring has to be good for both"

Corroborated separately by `zorrobyte` (6/5/2021): "whenever the harness is set in relay mode,
panda is a gateway between the camera, AEB, LKAS, whatever, and the CAN bus. It repeats messages."

**In plain terms:** the harness already installed in this car has a physical relay. While driving,
openpilot opens it, genuinely electrically splitting the camera-side bus from the main bus.
Panda's own software then decides, message by message, what crosses that split — by default it
just repeats/forwards everything, but it doesn't have to.

## Real, concrete precedent that this is used to block ACC messages specifically (not just steering)

`alfhern` (dev-openpilot, 10/7/2020), describing real Toyota safety code:

> "the list of messages that OP transmit is on the safety header files in `panda/board/safety`,
> more specifically for toyota (`safety_toyota.h`) there is a `TOYOTA_TX_MSGS` used for validation
> in the `toyota_tx_hook()` method. The `toyota_fwd_hook()` method **also filters out those LKAS
> and ACC messages from being forwarded**."

This is a real, named, existing function (`toyota_fwd_hook()`) on a real supported car that
selectively blocks **ACC messages** — not just steering — from crossing the relay split. Directly
relevant as precedent that "block the cruise-control message from reaching the other side" is a
real, implemented pattern elsewhere in opendbc, not a hypothetical.

## The general mechanism, further confirmed

Multiple independent, consistent confirmations across different dates/people that this is a
well-understood, standard pattern (not obscure or fringe):

> `mlp______` (5/24/2021): "you can filter messages in panda safety forwarding hook" ... "panda
> woud have to be in the middle of source and destination ecu" ... "eg source on can2 and
> destination on can0"

> unattributed technical exchange (7/2021 era, same file): "the signal is in the forward hook
> though, it forwards the message from bus 0 to bus 2" / "then forward hook will drop the message"

> `[unnamed]` (2022, replying in a car-port support thread): "panda doesn't really perform
> actions, it just decides whether or not to forward CAN traffic. The TX hook... evaluates CAN
> packets sent by openpilot and decides whether they pass safety checks. If they don't pass, the
> packet is dropped instead of forwarded"

## Connects directly to a flag already present in this project's own code (not independently
## verified in this Discord-only research pass, flagging as a pointer, not a finding)

One user (`179365`, unattributed further) described `check_relay`: "check_relay is for making sure
messages aren't appearing on a bus, if they do, it triggers a malfunction I believe." This name
matches a flag this project's own earlier work already found in `subaru_preglobal.h`
(`.check_relay = true` on the `ES_Distance`/`ES_LKAS` TX entries — the two messages this project
already transmits successfully every drive). **Not independently re-verified as part of this
Discord-only research task** (out of scope for this fork), but worth flagging as a strong hint:
those two messages likely already rely on exactly this relay-split-plus-fwd_hook mechanism to
avoid collision — meaning the same category of fix (a `fwd_hook` rule blocking `CruiseControl`
from being forwarded across the relay split) may be achievable in software, without new hardware,
if Subaru's preglobal safety code has (or could be given) a `fwd_hook` function. Whether that
function currently exists for Subaru preglobal specifically is a code-level question, not
something this Discord search resolves — flagging it as the natural next check for whoever picks
this up.

## What this does NOT confirm

- No message found is Subaru-specific for this exact technique — all the concrete "block ACC
  messages via fwd_hook" precedent is Toyota's `toyota_fwd_hook()`, not Subaru's.
- Nothing found confirms whether Subaru preglobal's safety code currently has any `fwd_hook`
  implementation at all, or whether adding `CruiseControl` blocking there would work the same way
  it does for Toyota's ACC messages — different cars, different bus topologies, not guaranteed to
  transfer cleanly.
- This is a software change to safety firmware (still requires flashing panda, the same "could
  brick / lose safety cert" category of step already flagged elsewhere in this project), not a
  risk-free action — real but different risk profile than a new PCB, not risk-free.

## Bottom line

Real, well-corroborated, multi-source, cross-year precedent exists for "block a specific message
(including ACC-category messages) from crossing the panda relay split via a `fwd_hook`" — a
software mechanism using the harness hardware this car already has, not a new custom board like
the obsolete 2021 Giraffe. This is the most promising lead found in tonight's research for
achieving genuine EyeSight-message isolation on modern comma 4 hardware. The concrete next step
isn't hardware shopping — it's checking whether Subaru preglobal's safety code has (or can be
given) a `fwd_hook`, and whether blocking `CruiseControl` there is architecturally sound for this
car's specific bus layout.
