# The throttle channel: a continuous longitudinal command surface this project already owns

**Status: source-verified architecture finding, zero live testing, zero archive validation
yet. Written 2026-08-06.**

## Top-line

Every actuation this project has ever done — Q6, Q10, all of Phase 3 — writes **one field**
of `ES_Distance` (`0x161`): `Cruise_Button`. The same message carries `Cruise_Throttle`
(bits `0|12`), and openpilot **already rebuilds and re-checksums the entire message at 20Hz
on the main bus**, copying `Cruise_Throttle` verbatim from the camera every single frame of
every drive.

Preglobal's DBC also defines the other two members of Subaru's longitudinal command trio —
`ES_Brake` (`0x160`, `Brake_Pressure` 16-bit) and `ES_Status` (`0x162`, `Cruise_RPM`
16-bit) — the exact three messages upstream Subaru **global** longitudinal control writes
today.

So the question this project has been asking ("can we get real longitudinal control?") has
a different shape than assumed. It was never "find a way to inject a message the car will
accept." **A continuous, proportional longitudinal command channel is already in the TX
allowlist, already transmitted, already relay-isolated from contention, already
checksum-correct, and already passing the panda's safety hook with no value check at all.**
This project has been turning a dial next to an open throttle cable for two weeks.

## What is verified, directly in upstream source

All line references are to `commaai/opendbc` at the tip cloned 2026-08-06. Nothing here is
inferred from documentation or community chat.

### 1. The message carries a throttle command field

`opendbc/dbc/generator/subaru/_subaru_preglobal_2015.dbc:134-152`:

```
BO_ 353 ES_Distance: 8 XXX
 SG_ Cruise_Throttle : 0|12@1+ (1,0) [0|4095] "" XXX
 ...
 SG_ Cruise_Brake_Active : 20|1@1+ (1,0) [0|1] "" XXX
 SG_ Standstill : 22|1@1+ (1,0) [0|1] "" XXX
 SG_ Close_Distance : 24|8@1+ (0.019607,0) [0|5] "m" XXX
 SG_ Cruise_Fault : 42|1@1+ (1,0) [0|1] "" XXX
 SG_ COUNTER : 44|3@1+ ...
 SG_ Cruise_Button : 48|3@1+ ...
 SG_ Checksum : 56|8@1+ ...
```

And the other two, in the same preglobal DBC — this is the part that reframes everything:

```
BO_ 352 ES_Brake: 8 XXX          # 0x160
 SG_ Brake_Pressure : 0|16@1+ ...
 SG_ Cruise_Brake_Active : 22|1@1+ ...
 SG_ Cruise_Activated : 23|1@1+ ...

BO_ 354 ES_Status: 8 XXX         # 0x162
 SG_ Brake : 8|1@1+ ...
 SG_ Cruise_Activated : 9|1@1+ ...
 SG_ Cruise_RPM : 16|16@1+ ...
```

The preglobal safety header's own comment (`safety/modes/subaru_preglobal.h:5`) reads
`// 0x161 is ES_CruiseThrottle`. `research/es_distance_cruise_button_finding.md` flagged
that comment as a mismatch against the `#define` name and treated it as an unverified
Discord lead. **Git history settles it, and it is stronger than that doc assumed.**

### 1b. The provenance of these names — primary source, from git history

`opendbc` commit `2bab99fd`, **martinl, 2021-12-15**, "Subaru signals update (#474)",
diffing `generator/subaru/_subaru_preglobal_2015.dbc`:

```diff
-BO_ 353 ES_CruiseThrottle: 8 XXX
- SG_ Throttle_Cruise : 0|12@1+ (1,0) [0|4095] "" XXX
+BO_ 353 ES_Distance: 8 XXX
+ SG_ Cruise_Throttle : 0|12@1+ (1,0) [0|4095] "" XXX
```

`0x161` on **preglobal** was originally named `ES_CruiseThrottle` — by martinl, the person
who reverse-engineered this platform's bus in the first place — and was renamed in 2021
only to unify naming with global. The safety-header comment is not a hint borrowed from
global; it is the **original preglobal name**, and the name exists because that is what the
message was found to do. Note also that the field's original name, `Throttle_Cruise`, is
the *same name* as the field the engine reports back in its own `Throttle` message
(`0x140`, `SG_ Throttle_Cruise`) — a command and its echo.

`opendbc` commit `783a8927`, **Justin Newberry (comma.ai), 2023-08-29**, "Subaru: preglobal
normalize signals to global (#929)":

```diff
 BO_ 352 ES_Brake: 8 XXX
- SG_ Brake_On : 22|1@1+ ...
+ SG_ Cruise_Brake_Active : 22|1@1+ ...

-BO_ 354 ES_RPM: 8 XXX
- SG_ RPM : 16|16@1+ ...
+BO_ 354 ES_Status: 8 XXX
+ SG_ Cruise_RPM : 16|16@1+ ...
```

This is the same jnewb1 whose preglobal longitudinal work `research/preglobal_long_fork_precedent.md`
traces — April 2023 first engagement, Aug 2023 bounty, Nov 2023 `subaru-preglobal-long`
installer. **In the middle of building preglobal longitudinal control, a comma engineer
went and renamed preglobal's `0x160`/`0x162` signals to exactly match global's
longitudinal-command signal names.** People do that when they are writing one piece of
control code against both platforms.

This does not prove the engine obeys these fields. It does mean the two people with the
most hands-on preglobal CAN experience in this community independently named these three
messages as the ACC longitudinal command trio, based on their own reverse-engineering of
this platform — not by analogy to global.

### 2. openpilot already transmits it, and already owns every bit of it

`opendbc/car/subaru/subarucan.py:302`, `create_preglobal_es_distance()` — copies
`Cruise_Throttle`, `Car_Follow`, `Cruise_Brake_Active`, `Standstill`, `Close_Distance`,
`Cruise_Fault`, `COUNTER` and the rest verbatim from the camera's live message,
overrides **only** `Cruise_Button`, then recomputes `Checksum` over the whole frame.

Two consequences, both load-bearing:

- Writing a different `Cruise_Throttle` is a **one-line change to an already-shipping code
  path**. The checksum is recomputed after the field assignment, so any value written is
  automatically frame-valid. There is no new message, no new address, no new rate, no new
  counter to fake.
- `CS.es_distance_msg` is read from the **camera bus** for preglobal
  (`car/subaru/carstate.py:32`, `cp_es_distance = cp_cam` for non-GEN2/non-hybrid;
  `carstate.py:112` reads `Cruise_Button` from `cp_cam`). So on every frame openpilot
  already knows *exactly what EyeSight is asking the engine to do* — and then relays it.

`carcontroller.py` sends it unconditionally for preglobal, every 5 frames (20Hz), with no
`openpilotLongitudinalControl` gate:

```python
if self.CP.flags & SubaruFlags.PREGLOBAL:
  if self.frame % 5 == 0:
    ...
    can_sends.append(subarucan.create_preglobal_es_distance(self.packer, cruise_button, CS.es_distance_msg))
```

20Hz is the same rate upstream global longitudinal control runs its throttle/brake/RPM
commands at (`frame % 5` on all three). This is not a degraded channel — it is the
production one.

### 3. There is no contention, and it is proven by this car's own working lateral control

`safety/modes/subaru_preglobal.h`:

```c
static const CanMsg SUBARU_PG_TX_MSGS[] = {
  {MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true},
  {MSG_SUBARU_PG_ES_LKAS,     SUBARU_PG_MAIN_BUS, 8, .check_relay = true}
};
```

`check_relay` does two things (`safety/declarations.h:90`, and confirmed in
`safety/safety.h:263-285`): it **blocks camera→main forwarding** of that address, and it
**trips `relay_malfunction`** if that address is ever seen arriving on the destination bus.

So:
- The camera's own `0x161` is structurally prevented from reaching the car. openpilot is
  the **sole transmitter** of `ES_Distance` on bus 0. This is the entire reason button
  spoofing on `0x161` worked cleanly while `0x144` injection caused an EyeSight-off fault
  (Q9): `0x144` has a live competing transmitter, `0x161` has none *by construction*.
- **This is already proven true on this specific car**, not assumed. `relay_malfunction`
  blocks *all* TX (`safety/safety.h:248`). Lateral control works on this car every drive,
  which means `ES_LKAS` is transmitting, which means `relay_malfunction` is false, which
  means the relay is genuinely isolating the camera. The same relay, the same allowlist
  entry, the same bus.

### 4. The panda applies no value check to this message

`subaru_preglobal_tx_hook()` checks steering torque limits for `MSG_SUBARU_PG_ES_LKAS` and
then `return tx;` — **`ES_Distance` passes unconditionally, any value in any field.**

`safety_tx_hook()` (`safety/safety.h:236`) is `!relay_malfunction && whitelisted &&
safety_allowed`. `0x161`/bus 0/8 bytes is whitelisted; the mode hook returns true. There is
no `controls_allowed` gate on it either — which is exactly why the existing preglobal code
can send it whether or not openpilot is engaged.

### 5. This car has already been proven to obey an openpilot-authored `0x161`

This is the strongest argument here and it comes from this project's own telemetry, not
from source reading. Q6 (2026-07-23, 23:10:42.888 UTC) commanded `Cruise_Button = 2` in
this exact message, purely in software, with `real_cruise_button = 0` — and the real ECU
engaged cruise within ~100ms, populating `Cruise_Set_Speed` to 28.006mph against a real
`vEgo` of 28.9mph. Q10 then confirmed deep-SET, RESUME and burst behavior the same way.

So the question is **not** "will the car accept and act on a frame openpilot authored at
`0x161`?" That is settled, live, on this car, four separate ways. The only open question
is whether a *different field* of that same already-accepted, already-obeyed frame is
honored the same way. That is a much smaller claim than anything this project has
previously had to prove.

**No panda firmware change is required to command throttle.** This is the single most
important practical fact in this document, because it means this path does not hit the
prebuilt-branch landmine that has blocked or complicated nearly every other idea in this
project (no `scons`, no new Params key, no new capnp field, no reinstall, no factory reset,
no recalibration — it is pure Python in an already-shipping function, deployable by
`git pull` + reboot, revertable the same way).

### 6. Confirmed in sunnypilot's own fork, not just upstream

`sunnypilot/opendbc`, `opendbc/safety/modes/subaru_preglobal.h` — the safety mode actually
running on this car:

```c
#define SUBARU_PG_COMMON_TX_MSGS \
  {MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
  {MSG_SUBARU_PG_ES_LKAS,     SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \

#define SUBARU_PG_STOP_AND_GO_TX_MSGS \
  {MSG_SUBARU_PG_Throttle,    SUBARU_PG_CAM_BUS,  8, .check_relay = false}, \
  {MSG_SUBARU_PG_Brake_Pedal, SUBARU_PG_CAM_BUS,  4, .check_relay = false}, \
```

Its `tx_hook` is byte-identical to upstream's: steering-torque checks on `ES_LKAS`,
`return tx` — **no value check on `ES_Distance`**. Everything above holds in the deployed
stack.

Two extra findings fall out of this, both material:

- **sunnypilot already ships a *modified* preglobal TX allowlist to end users** (the
  stop-and-go entries, runtime-selected via a safety-param word sunnypilot added to the
  panda protocol itself). So "we would need a panda safety change" is not the hard wall
  this project has treated it as since Q5. Note this is **already reachable on this device
  with zero build work**: `SubaruStopAndGo` is in the *compiled* params allowlist
  (`common/params_keys.h:221`), so setting it flips the panda to the expanded TX allowlist
  live — a way to exercise the mechanism on this car before ever building firmware. Caveat:
  it transmits on bus 2, which is where Q9's "EyeSight Off" fault came from. Two further
  cautions worth knowing: sunnypilot's own `tx_hook` value checks for those two messages
  are **commented out**, and `test_subaru_preglobal.py:14` still declares
  `TX_MSGS = [[0x161,0],[0x164,0]]` — their additions have zero test coverage.
- **There is a second, independent lever, already shipping**: see below.

### 7. Second lever — sunnypilot already lies to EyeSight on this platform

`opendbc/sunnypilot/car/subaru/subarucan_ext.py` — `create_throttle()` and
`create_brake_pedal()` rebuild the engine's `Throttle` (`0x140`) and `Brake_Pedal`
(`0xD1`) messages and transmit them **to the camera bus**, with fabricated values, on
preglobal:

```python
if send_resume:
  values["Throttle_Pedal"] = 5          # tell EyeSight the driver tapped the gas
...
if send_resume:
  values["Speed"] = 1 if CP.flags & SubaruFlags.PREGLOBAL else 3
```

That is sunnypilot's Stop-and-Go: it makes EyeSight release standstill by **feeding it a
fabricated view of the car's own state**. It is in production, on preglobal, from the
maintainer of the fork this project runs.

This is the honest, signal-domain version of "can we trick the cameras" — and it is
already proven to work on this platform. Its implication for the braking complaint is
direct: `Brake_Pedal` (`0xD1`) carries `Speed`, and EyeSight's own closed loop runs on
what it believes the car's speed is. Biasing that belief upward by a few mph makes EyeSight
decelerate using **its own full authority, friction brakes included** — no button
quantization, no 1mph steps, no debounce.

Ranked against the throttle channel, though, this is the **worse** lever, and the ranking
matters:

- These entries are `check_relay = false`, so forwarding is **not** blocked — openpilot's
  fabricated frames interleave with the real ones the panda is still forwarding. That is
  contention by design (brief bursts, not a clean MITM), which is why stop-and-go uses it
  for a ~15-frame nudge and not for continuous control.
- It corrupts EyeSight's world model, which is also **AEB's** world model. The throttle
  channel leaves EyeSight's perception completely intact and never touches `ES_Brake`.
- It requires the stop-and-go TX entries to be enabled; the throttle channel requires
  nothing.

Keep it in the file as a real, precedent-backed fallback for friction-brake authority if
the throttle channel proves insufficient and the `ES_Brake` allowlist path proves
unavailable. Do not lead with it.

## Why this is materially different from every avenue already closed

| Avenue | Blocked by | Does this apply here? |
|---|---|---|
| `0x144` `CruiseControl` TX (Q5) | Not in allowlist → needs panda firmware change | No — `0x161` already allowlisted |
| `0x144` main-bus injection (Q9) | Live competing transmitter, bus contention | No — camera's `0x161` is relay-blocked; openpilot is sole source |
| `0x144` camera-bus injection (Q9 follow-up) | Stale counter/checksum → real "EyeSight Off" fault | No — counter copied live, checksum recomputed every frame, already in production use |
| UDS `CommunicationControl` silence (Q9) | ECU doesn't implement the service | Not needed — nothing has to be silenced |
| Physical EyeSight isolation / Giraffe relay | No controllable relay on preglobal harness | Not needed |
| Pedal interceptor | Hardware, no Subaru code path, real reliability risk | Not needed — this is the ACC's own throttle channel |
| New Params key / new capnp field / new UI state | Prebuilt branch, no `SConstruct` | Not applicable — no new state needed |

Every closed door was a door into the same room. This is a door that is already open,
that this project has been walking through 20 times a second since the day lateral control
was installed.

## What this actually buys, against the three real complaints

**"EyeSight brakes too late."** Today's mechanism: decide → wait for the 0.4s button
cadence → EyeSight notices its setpoint moved → EyeSight decides to decelerate → EyeSight
commands throttle down and brakes. Measured end-to-end authority: ~1.94 mph/s
(`phase3_controller_design.md` §7), and the *decision-to-first-motion* latency is
EyeSight's, not ours.

With throttle authority: decide → next 50ms frame, throttle goes to EyeSight's own
engine-braking value. The car starts responding within one control frame. That is the
gap the 29:01 off-ramp incident died in — that analysis concluded even zero-latency
*button* intervention couldn't have helped, because the button channel's floor is
EyeSight's own decel ceiling. The throttle channel has a different floor.

**"It doesn't do a good job accelerating."** The button channel literally cannot express
"accelerate harder" — it can only ask for a higher setpoint and let EyeSight choose the
ramp. `Cruise_Throttle` is a direct request. Upstream's global constants
(`car/subaru/values.py`) put `THROTTLE_INACTIVE = 1818` at zero acceleration and
`THROTTLE_MAX = 3400`, mapped from a requested accel of 0→2 m/s². That is a real
acceleration authority, expressed in the same units the planner already produces.

**"It's not end-to-end / it's not longitudinal."** Correct, and structurally so. A
setpoint dial can never be end-to-end: the model's output gets quantized into 1mph clicks
and handed to a black box that decides what to do with them. A continuous throttle
command consumes `actuators.accel` — the longitudinal planner's real output — the same way
every properly-supported car does. **That is the difference between advising EyeSight and
driving the car.**

**What it does not buy, honestly:** friction braking. `Cruise_Throttle` at its floor gives
throttle-closed plus whatever engine/CVT braking the powertrain does on its own. Real
brake pressure lives in `ES_Brake` (`0x160`) and CVT-ratio engine braking in `ES_Status`
(`0x162`) — **neither is in the preglobal TX allowlist**, so both need a panda safety
change, which is the expensive path on this device. See "escalation" below.

## Proposed architecture: fast path + deep path

Do not replace the existing Phase 3 controller. Layer on top of it.

- **Deep path (existing, unchanged):** the button controller walks EyeSight's setpoint.
  This is what brings EyeSight's *friction braking* to the party and what handles large,
  sustained speed changes. Keep every safety rail, budget, and latch exactly as is.
- **Fast path (new):** `Cruise_Throttle` override. Sub-100ms response, continuous,
  proportional. Covers the dead time between "the model decided" and "EyeSight reacted."

They compose naturally: on a curve or a closing lead, cut throttle *now* (fast path) while
walking the setpoint down (deep path). The car lifts off immediately and EyeSight's brakes
arrive behind it. On restore, hand authority back to the deep path and release the fast
path to passthrough.

### The v1 safety rule that makes this tractable: **veto, never override**

```
commanded_throttle = min(eyesight_throttle, our_requested_throttle)
```

v1 may only ever command **less** throttle than EyeSight is already asking for. Never more.

This is not a tuning choice, it is a structural safety property:

- A bug, a stuck value, a runaway policy, a desync — the worst case is *the car coasts*.
  Unintended acceleration is not merely unlikely, it is **not expressible**.
- Stock AEB is untouched (`ES_Brake` is forwarded straight through, never written) and
  cannot be fought — during an AEB event EyeSight commands minimum throttle, and `min()`
  of that is still minimum throttle.
- It fails safe on loss of the fast path: stop writing, and you are back to byte-for-byte
  passthrough, which is exactly today's behavior.

Acceleration authority (`max()` above EyeSight, for the "doesn't accelerate well"
complaint) is a **v2** decision, deliberately deferred — it is a genuinely different risk
category, the same way SLF's decrease-only scoping was deferred in
`phase3_speed_limit_following_design.md`.

### The self-calibrating principle: only ever say what EyeSight has already said

The encoding of preglobal `Cruise_Throttle` is **unverified**. Upstream's 808/1818/3400
constants are global-platform numbers; whether preglobal shares them is unknown.

This does not need to be resolved before building, because of a property this channel has
that no previous avenue had: **openpilot reads EyeSight's own live command every frame.**
So the control law can be defined entirely in terms of values EyeSight has itself
demonstrably commanded on this exact car — never a number invented from a spec sheet:

- The floor is not "808." The floor is *the lowest value EyeSight has been observed
  commanding on this car during real deceleration*, mined from the archive.
- The ceiling is *the value EyeSight is commanding right now* (the veto rule).
- Everything in between is interpolation inside a measured, real envelope.

Framed that way, the fast path never says anything to the engine that this specific car's
EyeSight has not already said to it thousands of times. **It says the same words, just
sooner.** That is a very different risk conversation than "inject a novel command."

## Staged validation — nothing here is a "try it and see"

Same discipline that closed Q4, Q6, Q9 and Q10. Each stage has its own go/no-go.

**Stage 0 — passive archive proof (zero risk, no device, run first).** ~105GB of archived
raw CAN already contains `ES_Distance.Cruise_Throttle` (bus 2) on every drive ever
recorded, alongside the engine's own `Throttle` message (`0x140`) which carries
`Throttle_Cruise`, `Throttle_Body` and `Engine_RPM`, plus `Brake_Pressure` (`0x150`),
`CVT_Ratio` and `carState.aEgo`. The decisive question — **does `Cruise_Throttle` lead the
engine's response (command) or lag it (report)?** — is answerable from data already on
disk, with zero transmission. This also directly measures the real value envelope and the
throttle→accel transfer function on this car. **If `Cruise_Throttle` turns out to lag, the
entire thesis dies here, for free.** Methodology and script: see the companion analysis
doc in this directory.

**Stage 1 — parked/idling passthrough-identity check.** Write `Cruise_Throttle` with the
value already being read (a no-op rewrite). Confirms the write path is byte-identical and
provokes nothing. Cheap, and it isolates "did our code break the frame" from "did the car
dislike the value."

**Stage 2 — single-shot, bounded, driving.** One brief, small, downward-only deviation
(e.g. −5% of EyeSight's commanded value for 200ms), one-shot armed, at safe speed, on an
empty road, with the dash watched for `Cruise_Fault`/EyeSight-off — the exact
one-shot-armed-and-analyze-afterward pattern that closed Q6. **The named risk to watch is
EyeSight's plausibility check**: it commands throttle, the car does something else, and it
may fault itself off protectively — the same *category* of behavior that produced the
"EyeSight Off" dash fault in the bus-2 injection test, and the reason this stage is
deliberately 200ms and not 2 seconds.

**Stage 3 — bounded closed loop, veto-only**, wired to the existing Phase 3 override latch
and arm gates, with a hard watchdog: if the fast path's own command file/state is stale by
more than N frames, revert to passthrough immediately.

**Escalation (separate decision, not part of this):** adding `ES_Brake` (`0x160`) and
`ES_Status` (`0x162`) to `SUBARU_PG_TX_MSGS` would give real friction-brake and CVT
engine-brake authority — full openpilot longitudinal, the thing jnewb1's lost
`subaru-preglobal-long` branch appears to have had. **This was investigated separately and
the firmware wall turned out to be far lower than Q5 assumed — see
`research/panda_safety_firmware_deployability.md`.** Headline: this device already runs
debug-signed, non-comma panda firmware *by necessity* (`SAFETY_SUBARU_PREGLOBAL` is
registered only inside `#ifdef ALLOW_DEBUG`, so comma's release firmware cannot run this
car at all), the firmware ships as a git-tracked binary on the release branch, and
`pandad` reflashes on every boot when the signature differs — so modified safety firmware
reaches this device by `git pull` + reboot, with **no reinstall, no factory reset, no
recalibration, no torque relearn**. Still deliberately scoped out of v1, but it is now a
real option rather than a wall.

Two warnings from that same pass, both of which would have bitten a naive patch:
**the bit offsets do not port from global.** Preglobal `ES_Brake.Brake_Pressure` is `0|16`
(global's is `16|16`) and `ES_Status.Cruise_RPM` is `16|16` (global's is `16|13`), so
copy-pasting `subaru.h`'s `GET_BYTES(msg, 2, 2)` value checks would read the wrong bits and
enforce nothing — and global's `.max_brake = 600` is calibrated to global's scaling, which
is unmeasured on preglobal. Second: `check_relay = true` makes openpilot the **sole**
transmitter, so it would have to produce valid `0x160`/`0x162` frames from the first frame
onward, and preglobal `carstate.py` does not parse those messages at all today.

## Honest gaps and what would kill this

- **Unverified: that the engine obeys `Cruise_Throttle` on preglobal at all.** Everything
  above establishes that openpilot *can* write it, unblocked and un-checked. It does not
  establish that the ECU *acts* on it. Stage 0 is designed to answer exactly this.
- **Unverified: the encoding/scaling on preglobal.** Mitigated by the self-calibrating
  principle above, but still a real unknown.
- **Unverified: whether the engine gates on ACC state.** It probably only honors the field
  while ACC is engaged — which is fine (that is already the arming precondition), but it
  means this cannot be an ACC-independent control channel.
- **Unresolved: EyeSight's reaction to being vetoed.** It sees the car's speed diverge from
  its own intent (it cannot see our modified frame — the relay blocks it) and will wind up
  its own controller in response. Two sub-risks: a protective fault, and a release
  transient when we hand authority back. Mitigations: short deviations first, ramped
  release, veto-only.
- **Unresolved: interaction with the existing button controller.** Both would be moving the
  car at once. Needs explicit arbitration, not two independent loops.
- **Not yet checked at time of writing:** whether sunnypilot's fork modifies preglobal
  safety or `create_preglobal_es_distance` in a way that changes any of the above (this
  document is verified against upstream `commaai/opendbc`), and whether anyone in the
  community has ever written this field on a preglobal car.

## The one-line version

The project's founding assumption — "EyeSight can't be commanded on gas/brake over CAN on
the pre-global platform — that's settled" (`progress.md` §1) — is **the thing to retest**.
It was true of `0x144`. It appears not to be true of the message openpilot has been
transmitting, unchecked and uncontested, on this car all along.
