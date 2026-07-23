# Camera-bus injection precedent — Discord research (2026-07-23)

## Top-line: mixed. No clean precedent for "inject 0x144 on bus 2 specifically to
## dodge collision" — but real, substantive, relevant material on all the adjacent
## questions, including a genuine 2019 first-hand report of spoofed Subaru button
## presses being recognized by EyeSight, and confirmation this exact idea is still
## unsolved community-wide as of THIS WEEK (7/17/2026).

## 1. The general "inject on the bus where the real transmitter isn't" technique — real, but Toyota not Subaru

`dev-openpilot`, Aug 2025, `alesatobrazilsp` + `cydia2020` (a real, technically detailed
exchange about enabling Toyota TSS-P longitudinal control on unsupported cars):

> alesatobrazilsp: "DSU is a ECU with take decisions about cruise control (powertrain)
> in Toyota Safety Sense TSS-P and not is at camera bus" ... "2-interface detect 0x343
> at camera bus / 3-send 'fake custom heartbeat' to enable openpilot tx longitudinal
> control at panda firmware side"

> cydia2020: "openpilot can send 0x343 if it is not being detected on bus0 and it is
> on bus2 (meaning camera/dsu bypass is sending it) otherwise block"

This is real, substantive precedent for the *general concept* — using bus placement to
determine where it's safe/meaningful to transmit — but it's about *detecting which bus
the real ECU is on* to conditionally allow TX, not specifically about "the real
transmitter is on bus 0, so inject an identical/modified copy on bus 2 to avoid
colliding with it." Different car (Toyota TSS-P/DSU), different message (0x343, a
control message), different specific mechanism (heartbeat-gated TX permission, not
bus-routing around an already-active broadcaster). Relevant as a "this general class of
bus-topology exploitation is a real, known technique in this community" data point —
not a direct precedent for the Subaru 0x144 case.

## 2. Real Subaru bus-topology explanation — corroborates why EyeSight's bus position matters

`subaru` channel, Oct 2019, `mlp______` and `bugsyborromeo` (real, detailed first-hand
technical discussion, predates this project by years):

> mlp______: "acc buttons are directly wired to eyesight" ... "but they go through the
> giraffe so there are possible solutions"

> bugsyborromeo: "Eyesight listens to the button press response from an ECU on CAN0
> that listens to the initial output from eyesight / Driver/wheel -> eyesight -> car ->
> eyesight"

This describes a real request/response loop where EyeSight is the first hop for button
input and also the thing waiting for an acknowledgment from a CAN0 (main bus) ECU. It
doesn't explicitly confirm a camera-bus copy of 0x144 or explain the specific
bus-0-dominant-with-a-130-echo-bucket pattern this project's own telemetry found — but
it does confirm EyeSight's physical position in this loop is bus-topology-relevant, not
a black box, consistent with the idea that where you inject could plausibly matter.

## 3. Real first-hand report: spoofed button injection WAS recognized by EyeSight (platform generation unconfirmed)

Same 2019 thread, `bugsyborromeo` (real-time, "tonight i test stop and go" style
first-hand build log, not secondhand):

> "i was able to successfully spoof a resume button press where the car-side ACC ecu
> recognised the press but i forgot to undo the standstill bit from eyesight"

> chaoticau: "So it's not just a CAN message [that differs between real press and
> spoof]?" / bugsyborromeo: "eyesight listens to all spoofed button presses / it just
> refuses to release standstill unless the physical button is pushed or ACC is
> cancelled"

**This is a genuine, real, first-hand report that CAN-injected button presses got
recognized by EyeSight** — with one specific, narrow caveat (standstill-release
specifically requires a physical press or cancel/resume, not a general rejection of
spoofed input). Two things this does NOT resolve, checked and not found in surrounding
context:
- **Platform generation (preglobal vs global) is not stated anywhere nearby** — this
  project's whole Q9 investigation is specifically about whether preglobal behaves like
  global here, and this 2019 report doesn't settle that either way.
- **Which bus the spoof was sent on is not stated** — no confirmation this used bus 2,
  bus 0, or whether it caused any bus errors/contention at all. Could be consistent with
  either "it just worked on bus 0 with no contention issue in 2019" or "they used
  camera bus and didn't say so" — genuinely unknown from this text alone.

Treat as real but incomplete evidence — a Subaru first-hand success report exists, but
it doesn't pin down the two specific variables (platform, bus) this project needs.

## 4. Corroborates the "echo flag" bus-code pattern from the earlier telemetry check

`dev-openpilot`, June 2024, `alesatobrazilsp` (real, technical, unrelated conversation
about a different Subaru carstate.py port):

> "here if the message come from camera bus: [carstate.py link]" / "if BUS is from 129
> or 2"

"129" here = 1 | 0x80 in the same encoding pattern this project's own bus-2-check
research flagged as a guess (128/130/etc = bus number OR'd with an echo/TX-confirmation
flag). This is independent, real corroboration that this encoding scheme is a genuine,
known pattern in this community's Subaru work — not a full resolution of that earlier
research's specific unexplained anomaly (why CruiseControl shows a "130" bucket despite
never being transmitted by this project), but supporting context that the general
pattern-guess was reasonable.

## 5. This exact idea is confirmed still unsolved, as of THIS WEEK

`subaru` channel, **7/16/2026, `flyingchair235`** (11 days before this conversation):

> "Hey guys! Anyone tried spoofing ACC buttons to auto-adjust speed alongside eyesight?
> Tired of it braking too late on the highway or it not being able to handle curves.
> (Pre-global)"

Reply, 7/17/2026, `amusedgrape`:

> "seems like it's never really been explored or can't be done :(" [links the same
> "Enabling ICBM on '17 Impreza" community thread this project already cited in
> progress.md]

And `5pacecaptain`, same thread: "Yeah the braking too late is a real thing" — real,
current confirmation the underlying complaint is shared community-wide, not unique to
this project.

**This is directly relevant, current context**: as of 11 days ago, someone else with the
exact same platform (preglobal) asked the exact same question this project has spent
tonight investigating, and got the same answer this project independently arrived at —
nobody's cracked it. Not a new technical finding, but real confirmation this project
isn't chasing something the community already quietly solved elsewhere.

## Bottom line

No direct precedent for "inject 0x144 specifically on bus 2 to avoid collision" exists
anywhere in the searched channels. What does exist: a real transferable technique
(Toyota, different mechanism), real Subaru bus-topology detail explaining EyeSight's
relay-like position, a genuine but incomplete 2019 first-hand Subaru button-spoofing
success report (platform/bus unconfirmed), corroboration of the bus-code encoding
pattern, and current (this week) confirmation the community still treats this whole
idea as unsolved. The actual bus-2 injection test this project is building remains
genuinely untested territory — not contradicted by anything found here, but not
validated either.
