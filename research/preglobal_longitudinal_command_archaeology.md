# Preglobal Subaru longitudinal command archaeology — `Cruise_Throttle` / `Cruise_RPM` / `Brake_Pressure`

**Date:** 2026-08-06
**Scope:** everything real that anyone has ever found or said about *writing* the Subaru longitudinal
command trio — `ES_Brake` (0x160) `Brake_Pressure`, `ES_Distance` (0x161) `Cruise_Throttle`,
`ES_Status` (0x162) `Cruise_RPM` — on a **PREGLOBAL** car. Not the ACC buttons, not Global.

This builds on `research/preglobal_long_fork_precedent.md` (2026-07-25) and does not repeat it.
Everything quoted below is verbatim from a source I actually opened; every URL is marked with
whether it resolved.

**Environment limitation, stated up front:** from this session, `web.archive.org` / `archive.org`
are blocked at the network gateway (`gateway answered 403 to CONNECT`), and the GitHub REST API,
GitHub code search, grep.app, sourcegraph, and the GH-Archive event dataset were all unreachable.
So **the Wayback Machine was NOT checked** — that avenue is still open for a session with different
egress. What *did* work: `git ls-remote` / `git fetch` against github.com, and plain HTML fetches of
github.com pages.

---

## 0. The structural facts (verified from source, not claims)

Message IDs and layouts, from `opendbc/dbc/generator/subaru/` at upstream opendbc commit `a3ed7d18`:

| | Preglobal (`_subaru_preglobal_2015.dbc`) | Global (`subaru_global_2017.dbc`) |
|---|---|---|
| `ES_Brake` | **352 = 0x160**, `Brake_Pressure : 0\|16@1+` | 544 = 0x220, `Brake_Pressure : 16\|16@1+` |
| `ES_Distance` | **353 = 0x161**, `Cruise_Throttle : 0\|12@1+ [0\|4095]`, `Cruise_Button : 48\|3@1+` | 545 = 0x221, `Cruise_Throttle : 16\|13@1+` |
| `ES_Status` | **354 = 0x162**, `Cruise_RPM : 16\|16@1+ [0\|65535]` | 546 = 0x222, `Cruise_RPM : 16\|13@1+` |
| `ES_DashStatus` | 358 = 0x166 (defined in `subaru_outback_2015.dbc`) | 0x321 |

So: **same signal names, different bit layouts.** The names match because Justin Newberry
deliberately renamed them — see §2.

Two more verified source facts that matter more than anything else in this document:

1. **`opendbc/safety/modes/subaru_preglobal.h` (upstream, current) already TX-allows 0x161 on the
   main bus, with `.check_relay = true`, and its `tx_hook` performs *no content check whatsoever*
   on 0x161** — the only value check in the whole preglobal tx_hook is the steering-torque check on
   0x164. Verbatim:

   ```c
   static const CanMsg SUBARU_PG_TX_MSGS[] = {
     {MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true},
     {MSG_SUBARU_PG_ES_LKAS,     SUBARU_PG_MAIN_BUS, 8, .check_relay = true}
   };
   ```

   `ES_Brake` (0x160) and `ES_Status` (0x162) are **not** in that list, and are not defined as
   constants in that file at all.

2. **`check_relay = true` causes the panda to statically block the camera's copy of that address
   from ever reaching the car bus**, unconditionally, whenever the relay is engaged. From
   `opendbc/safety/safety.h`:

   ```c
   int safety_fwd_hook(int bus_num, int addr) {
     bool blocked = relay_malfunction || current_safety_config.disable_forwarding;
     const int destination_bus = get_fwd_bus(bus_num);
     if (!blocked) {
       for (int i = 0; i < current_safety_config.tx_msgs_len; i++) {
         const CanMsg *m = &current_safety_config.tx_msgs[i];
         if (m->check_relay && !m->disable_static_blocking && (m->addr == addr) && (m->bus == (unsigned int)destination_bus)) {
           blocked = true;
   ```

   **Consequence:** on a preglobal car running openpilot today, EyeSight's real 0x161 never reaches
   the engine/cruise ECU. openpilot is the *sole* source of 0x161 on the car bus. Upstream
   `carcontroller.py` re-emits it at 20 Hz (`if self.frame % 5 == 0`) via
   `subarucan.create_preglobal_es_distance()`, which copies **every** field out of the camera's
   message — including `Cruise_Throttle` — and overrides only `Cruise_Button`:

   ```python
   def create_preglobal_es_distance(packer, cruise_button, es_distance_msg):
     values = {s: es_distance_msg[s] for s in [
       "Cruise_Throttle", "Signal1", "Car_Follow", ... "Cruise_Button", "Signal7",
     ]}
     values["Cruise_Button"] = cruise_button
     values["Checksum"] = subaru_preglobal_checksum(packer, values, "ES_Distance")
     return packer.make_can_msg("ES_Distance", CanBus.main, values)
   ```

   This project's existing button work is already writing this exact frame. Changing
   `values["Cruise_Throttle"]` in it is a **one-line change requiring no panda safety modification
   at all**, because 0x161 is already TX-allowed and unbounded. That is a materially different
   situation from `0x144` (Q5 in `progress.md`), and from `ES_Brake`/`ES_Status`.

---

## Q1 — First-hand reports of writing `Cruise_Throttle` / `Cruise_RPM` / `Brake_Pressure` on a PREGLOBAL car

**Found. Multiple, first-hand, with outcomes.** All from the Discord archive at
`discord-logs/CommaDiscord/comma.ai community - Vehicle Specific - subaru [525718620517564446].txt`.

### 1a. `bugsyborromeo` ("Bugsy", GitHub `bugsy924`), 2015 Outback — Jan 2020 — real code, still live

Platform confirmed preglobal by his own words, 1/14/2020 2:23 AM, replying to a question about
his long branch:

> **"Don't try it, it's broken and only for preglobal"**

and 1/14/2020 12:56 AM:

> **"Once I have long control working on preglobal, it might be worth trying it on his car"**

**The code survives.** `https://github.com/bugsy924/openpilot` branch `subaru-long`, tip
`7d09fc0449706f4b5ccd9a4d400c9be28ac54d5c`, commits dated 2020-01-10/11 —
**resolved and fetched successfully** (`git fetch --depth=60 https://github.com/bugsy924/openpilot subaru-long`).
Branch listing URL `https://github.com/bugsy924/openpilot` resolves.

It writes all three fields plus the dash message. From `selfdrive/car/subaru/subarucan.py` at
`7d09fc0` (his DBC names them `ES_CruiseThrottle` / `ES_RPM`, pre-rename):

```python
def create_brake(packer, frame, enabled, error, brake):
  idx = (frame / 5) % 8
  values = {
    "Counter": idx, "Brake_Pressure": brake, "Brake_Light": 1 if brake > 0 else 0,
    "ES_Error": error, "Brake_On": 1 if brake > 0 else 0, "Cruise_Activated": enabled,
  }
  values["Checksum"] = subaru_preglobal_checksum(packer, values, "ES_Brake")
  return packer.make_can_msg("ES_Brake", 0, values)

def create_es_throttle_control(packer, frame, enabled, es_throttle, fake_button, throttle, brake):
  idx = (frame / 5) % 8
  values = {
    "Throttle_Cruise": throttle, "Button": fake_button, "Brake_On": 1 if brake > 0 else 0,
    "NEW_SIGNAL_1": 0, "Standstill": 0, "Standstill_2": 0, "SET_1": 0,
    "CloseDistance": 5, "Counter": idx,
  }
  values["Checksum"] = subaru_preglobal_checksum(packer, values, "ES_CruiseThrottle")
  return packer.make_can_msg("ES_CruiseThrottle", 0, values)

def create_es_rpm_control(packer, frame, enabled, brake, rpm):
  idx = (frame / 5) % 8
  values = {
    "Brake": 1 if brake > 0 else 0, "Cruise_Activated": enabled, "RPM": rpm, "Counter": idx,
  }
  values["Checksum"] = subaru_preglobal_checksum(packer, values, "ES_RPM")
  return packer.make_can_msg("ES_RPM", 0, values)
```

Note these are **built from scratch**, not copy-and-modify of the camera's frame.

His panda diff (`panda/board/safety/safety_subaru.h`, same branch) — this is the real
TX-allowlist + forward-block change, verbatim:

```diff
-const AddrBus SUBARU_TX_MSGS[] = {{0x122, 0}, {0x161, 0}, {0x164, 0}, {0x221, 0}, {0x322, 0}};
+const AddrBus SUBARU_TX_MSGS[] = {{0x122, 0}, {0x160, 0}, {0x161, 0}, {0x162, 0}, {0x164, 0}, {0x166, 0}, {0x221, 0}, {0x322, 0}};
...
-      int block_msg = (addr == 290) || (addr == 353) || (addr == 356) || (addr == 545) || (addr == 802);
+      int block_msg = (addr == 290) || (addr == 353) || (addr == 0x160) || (addr == 0x162) || (addr == 0x166) || (addr == 356) || (addr == 545) || (addr == 802);
```

i.e. **add 0x160 / 0x162 / 0x166 to TX, and block EyeSight's own 0x160 / 0x162 / 0x166 from being
forwarded camera→car.** This is the architectural answer to Q3 (see below).

**Outcome:** he never reported it working. His last commit on the branch is 2020-01-11; his own
verdict three days later is "it's broken". His only in-flight observation, 1/9/2020 11:07 PM:

> "weirdest thing happened while on my long branch, the car went berserk with errors like ABS,
> handbrake and other CEL stuff which I assume are from bad CAN
> this happened when I turned off openpilot from the UI
>
> when i tested with long control enabled, it was all fine except for one eyesight error"

(He then traced the "berserk" part to a panda forwarding bug of his own making, not to the
longitudinal writes.)

`mlp______` (martinl) summarised it later, 3/3/2020 5:49 PM — this is the single most-cited claim
in the whole topic and it is about **Bugsy's preglobal work**:

> **"but afaik bugsy tried that and eyesight faults when you just try to rewrite throttle and brake values"**

immediately followed by:

> "so the options are either figuring out how to send es throttle and brake messages while keeping
> eyesight alive"
> "or design some custom hw to intercept acc buttons and emulate eyesight"

### 1b. `aileron.me`, 2017 Outback Limited 2.5 (preglobal) — Oct 2020 — the cleanest first-hand test

Car stated by him, 10/12/2020 9:43 PM: *"outback 2017 limited 2.5"*, and 9:42 PM: *"My car is pre-global"*.

**Attempt and result**, 10/15/2020 8:08–8:10 PM:

> "Today I tried blocking ES_CruiseThrottle and ES_RPM and replace them with my own messages where
> throttle and rpm are set to 0"
> "Well it had an unintended effect of generating a tramsmission check engine light"
> "I guess ES detected the discrepancy of RPM messages it's sending out and the resulting wheel
> speed not increasing and it thinks transmission must be broken."
> "Any idea how to tackle that?"

He posted a dashboard photo of the fault on 10/16/2020 8:05 PM: *"This is what I'm getting for
changing ES_CruiseThrottle and ES_RPM"* (Discord CDN attachment; image not retrievable now).

`mlp______` diagnosed it, 10/16/2020 11:01–11:18 PM:

> "eyesight usually faults if any of the required can messages are missing or have invalid checksum
> or if any of the required signals are missing in generated can messages"
> "more or less correct frequency is also important when sending messages"
> **"ES_RPM is missing filler signals to cover all the 64 bits in the message, if you are using copy
> and rewrite one signal method like global does"**

That last line is a concrete, actionable defect explanation: the preglobal `ES_Status`/`ES_RPM` DBC
definition does not cover all 64 bits, so a copy-and-rewrite reconstruction silently zeroes the
undefined bits. (Confirmed against the current upstream DBC: `ES_Status` defines only `Brake`,
`Cruise_Activated`, `Cruise_RPM`, `Checksum`, `COUNTER` — bits 0–7, 10–15, 24–31, 40–47, 51–63 are
undefined. Same problem still exists today.)

**Panda allowlist was required and confirmed by test**, 10/17/2020 5:33–6:37 PM:

> aileron.me: "I think the problem is that I need to add ES_RPM to panda safety in the TX MSGS whitelist"
> aileron.me: "` 13 const CanMsg SUBARU_L_TX_MSGS[] = {{0x161, 0, 8}, {0x162, 0, 8}, {0x164, 0, 8}};` this"
> bugsyborromeo: "yes"
> aileron.me: **"Ok it worked"**
> aileron.me: "So in theory that's half of long control"
> bugsyborromeo: "half of accel"
> aileron.me: "although the actuator.gas output is so delayed it's horrible"
> aileron.me: "what's the other half of accel?"
> bugsyborromeo: **"the throttle message"**

So: **writing `Cruise_RPM` on a preglobal car, once TX-allowlisted, does get on the wire and does
something** — but on its own it is only "half of accel"; the ECU's `Throttle` (0x140) side matters too.

He also reported a real side effect of blocking the stock value, 10/17/2020 6:40 PM:

> "And the problem with blocking the original accel when actuator.gas is 0 is that it would upset
> ES's pid controller and when actuator.gas finally becomes non zero, ES is outputing a huge accel
> value and make the car do a jackrabbit start"

### 1c. Bugsy on what the fields actually are and how EyeSight validates them (10/12/2020, preglobal)

> aileron.me: "If I want to stop ES from accelerating, all I have to do is set
> ES_CruiseThrottle.Throttle_Cruise to 0 right?" / "But what does ES_RPM do then?"
> bugsyborromeo: "controls engine rpm"
> bugsyborromeo: **"not that simple, ES will error if you set it to 0 and it doesn't hear back the
> same thing from 0x140"**
> aileron.me: "So what's the relation between ES_CruiseThrottle.Throttle_Cruise and ES_RPM? which
> is used as a source of truth?"
> bugsyborromeo: "both?" / "ES_RPM's request traces with the transmission message on the main bus"
> aileron.me: "So both ES_CruiseThrottle.Throttle_Cruise and ES_RPM are generated by ES and consumed by ECU?"
> bugsyborromeo: "yes"
> aileron.me: "What happends if I set ES_RPM to idle but Throttle_Cruise is still very high?"
> bugsyborromeo: **"i think it tries, very slowly"** / "or throws an error, one of the two"
> bugsyborromeo: "had a good play with it last year" *(i.e. ~2019, on his 2015 Outback)*

**This is the closed-loop that matters:** EyeSight cross-checks its own `Cruise_Throttle` command
against the ECU's echo in `Throttle` (0x140) `Throttle_Cruise` (verified present in the preglobal
DBC: `SG_ Throttle_Cruise : 32|8@1+`), and faults on mismatch. That is a *different* fault mechanism
from checksum/frequency and is not fixed by getting the frame construction right.

### Q1 verdict
**Real, first-hand, preglobal, with real outcomes.** Two independent people wrote these fields on
preglobal Outbacks (2015 and 2017). Neither got working longitudinal control. The observed failures
were: an EyeSight fault, and a **transmission check-engine light**. The one clearly positive result
is that `Cruise_RPM` writes *do* reach the wire once TX-allowlisted. Nobody in this archive ever
reported the engine cleanly obeying a commanded `Cruise_Throttle` on preglobal.

---

## Q2 — Recovering jnewb1 / martinl's preglobal longitudinal code

### What resolved and what didn't (exact URLs)

| URL | Result |
|---|---|
| `https://github.com/jnewb1/openpilot/tree/subaru-preglobal-long` | **404** |
| `https://github.com/jnewb1/openpilot/pulls?q=is%3Apr` | **404** (whole repo gone) |
| `https://github.com/jnewb1/openpilot/branches/all?query=subaru` | **404** |
| `git ls-remote https://github.com/jnewb1/openpilot` | **fails — repo does not exist** |
| `https://github.com/commaai/openpilot/compare/master...jnewb1:openpilot:subaru-preglobal-long` | **404** |
| `https://github.com/commaai/openpilot/compare/master...jnewb1:openpilot:subaru-global-long` | not separately fetched; same fork is deleted, so expected 404 (**unverified**) |
| `https://installer.comma.ai/jnewb1/subaru-preglobal-long` | **403 Forbidden** |
| `https://github.com/jnewb1?tab=repositories` | **resolved.** No `openpilot` repo. Present: `openpilot2`, `openpilot-cleanup`, `openpilot-data`, plus ~27 unrelated repos |
| `git ls-remote https://github.com/jnewb1/openpilot2` | **resolved** — only `bridge-toggle`, `master`. No Subaru branch |
| `git ls-remote https://github.com/jnewb1/openpilot-cleanup` | **resolved** — empty (no refs) |
| `git ls-remote https://github.com/jnewb1/openpilot-data` | **resolved** — only `master` |
| `git ls-remote https://github.com/jnewb1/panda`, `.../opendbc` | **fail — do not exist** |
| `git ls-remote https://github.com/martinl/openpilot` | **resolved** — 164 branches. Greps for `preglobal` return only `preglobal-non-epb-sng` and `subaru-preglobal`. **No jnewb1-derived preglobal-long branch** |
| `git ls-remote https://github.com/commaai/openpilot` / `.../opendbc`, grep subaru | **resolved** — nothing preglobal-long |
| web.archive.org (CDX + direct) | **BLOCKED by network policy — NOT CHECKED** |
| GitHub code search / REST API / grep.app / sourcegraph / GH-Archive | **all unreachable from this environment** |

### One recovery technique that *does* work, and should be reused

Orphaned commits from a **deleted** fork of `commaai/openpilot` are still reachable through the
upstream network repo. Verified empirically with a jnewb1 SHA salvaged from Discord:

- `https://github.com/commaai/openpilot/commit/821ba1e8431bc7fdf5730f3bc91c700046a1412f` —
  **resolved**, renders as a real commit ("wip", author jnewb1, 2 files changed).
- `git fetch --depth=1 https://github.com/commaai/openpilot 821ba1e8431bc7fdf5730f3bc91c700046a1412f`
  — **succeeded**, `FETCH_HEAD` = `821ba1e wip`.

**So: if a single SHA from `subaru-preglobal-long` is ever found, the entire branch can be recovered
from `commaai/openpilot` by SHA.** I could not find such a SHA. The only jnewb1 commit SHAs in the
Discord archive (`477be1a…`, `821ba1e…`, `cf1b378…`, `a1d5f68…`) are all from April–May 2023
`subaru-legacy-long` / gen2-UDS work, not from the Nov 2023 preglobal branch. The two places a SHA
would most likely still exist — the Wayback Machine, and the GH-Archive PushEvent dataset — are both
unreachable from here. **This is the single highest-value unfinished thread.**

### What *did* survive of jnewb1's preglobal-long work

His stated plan, Discord 8/17/2023 11:40–11:45 AM, replying to `rikinmshah` offering the $1,750 bounty:

> jnewb1: "I can take a look when I get a chance, maybe get something close and then someone can
> take it over. I took a quick look at the DBC and it seems like we already have the core
> longitudinal signals, so it's just a matter of putting together a branch"
> jnewb1: **"ES_Distance -> Cruise_Throttle, ES_RPM -> Cruise_RPM (should be renamed ES_Status to match global)"**
> jnewb1: **"ES_Brake -> Brake_Pressure"**
> jnewb1: **"If you rename ES_RPM to ES_Status, most of the logic will be exactly the same and it
> will just be a matter of changing what DBC file is loaded"**

`mlp______` the same day, 8/17/2023 2:55–2:56 PM:

> **"prelgobal long is probably only missing the feedback signals from car and maybe some messages
> have different frequency than global gen1"**
> "only a few messages have counters and checksums but that should not be an issue for poc"

**And he then actually did the rename, upstream, twelve days later.** This is the durable artifact:

- `https://github.com/commaai/opendbc/pull/929` — **resolved.** Title *"Subaru: preglobal normalize
  signals to global"*, author jnewb1, merged 2023-08-29. Body per the PR page: *"ES_RPM -> ES_Status
  to match global name signals within ES_Distance and ES_Brake to match global"*.
- Commit `783a892751ce1ad731836a2ef91c37fba4f7f71e`, `Justin Newberry <justin@comma.ai>`,
  Tue Aug 29 2023 — present in the local opendbc clone. The diff renames, on **preglobal only**:
  `ES_Brake.Brake_Light`→`Cruise_Brake_Lights`, `ES_Brake.Brake_On`→`Cruise_Brake_Active`,
  `ES_Distance.Brake_On`→`Cruise_Brake_Active`, `BO_ 354 ES_RPM`→`ES_Status`, `RPM`→`Cruise_RPM`,
  and adds `ES_Brake.SET_1`. **Bit positions and scaling are untouched.**

That is why preglobal and global share signal *names* today — it was a deliberate step toward
preglobal long. It also means "just change what DBC file is loaded" only works at the name level;
the packer handles the differing bit layouts.

### Independent corroboration that the branch existed and what it was

- `emalton`, 11/23/2023, replying to a list of Subaru fork installers that included
  `installer.comma.ai/jnewb1/subaru-preglobal-long`:
  > **"subaru-preglobal-long has long support (no eyesight)"**
- `zookie1234`, 11/8/2023 8:19 AM — a real user actually running it:
  > **"I am running subaru-preglobal-long in 2017 forester and the auto high beams does not work."**
- `samehimohamed`, 11/5/2023 1:44 PM (reposting for visibility):
  > "thanks to @justin for getting long control working under subaru global and preglobal with
  > stock OP and Justin's subaru-global-long branch."
  and, 11/5/2023 6:40 PM, pointing at the changeset:
  > "the changeset can be seen here
  > https://github.com/commaai/openpilot/compare/master...jnewb1:openpilot:subaru-global-long ...
  > this also works for pre-global check https://discord.com/channels/469524606043160576/1137397673989775392"

  **Caveat, and it is important:** samehimohamed's own car is a **Forester 2020 (global)**. His
  "this also works for pre-global" is second-hand and points at a Discord thread
  (`1137397673989775392`) that is **not present in this archive's 13 exported channels** — so it is
  **unverified**. The same message also documents the drive's failure modes, which are worth keeping:
  > "once driving, EyeSight activates fine, activating OP works fine but immediately after it comes
  > to stop then tries to start driving. So if I am at 15 MPH and I enable OP, it comes to a full
  > stop then starts again. - It also starts up pretty jerky"
  > "at the intersection when navigation says to turn left or right, OP attempts to turn then
  > quickly thrown up the disengagement yellow alert asking the driver to take over, and EyeSight
  > throws up the 'place hands on the steering wheel' error"
  > "once OP throws up the yellow error, it's not possible to reactivate OP without a full car turn
  > off, then back on, then adding a new destination"

  and, 11/5/2023 6:39 PM: *"AEB does become inactive though on this branch, so it's something to keep in mind"*.

### Q2 verdict
**The code itself is not recoverable from this environment.** The repo is deleted; every direct URL
404s; the two archives that could plausibly still hold a SHA are unreachable here. What I *did*
recover is (a) jnewb1's own explicit description of the mechanism, (b) his surviving upstream DBC
commit that was step one of it, (c) three independent contemporaneous confirmations that the branch
existed and replaced EyeSight, and (d) **a working technique to fully recover the branch if any one
SHA is ever found.**

---

## Q3 — Did preglobal long silence EyeSight, or ride alongside a live one?

**This is the best-evidenced answer in the document, and it is: it replaced EyeSight's longitudinal
messages at the relay. It did not ride alongside a live EyeSight, and it did not need UDS silencing
either.** Three independent lines of evidence, all preglobal-specific:

**(1) Bugsy's actual panda diff (2020, preglobal, code I read).** He added 0x160 / 0x162 / 0x166 to
the block list in `subaru_fwd_hook` — EyeSight's own `ES_Brake`, `ES_Status`/`ES_RPM` and
`ES_DashStatus` are dropped at the comma relay and never reach the car; openpilot generates
replacements. EyeSight itself stays powered and transmitting on the camera bus. He also wrote a
`create_es_dash_control()` that fabricates the whole dash message, which only makes sense if
EyeSight's own dash message is being suppressed.

**(2) aileron.me's 2020 preglobal attempt used the same architecture** — *"Today I tried **blocking**
ES_CruiseThrottle and ES_RPM and **replace them with my own messages**"* — and separately confirmed
the relay direction was already correct in stock panda code, quoting
`subaru_legacy_fwd_hook`'s `int block_msg = ((addr == 0x161) || (addr == 0x164));`.

**(3) The user-visible symptom on jnewb1's actual preglobal-long branch matches.** `zookie1234`
(2017 Forester, preglobal, 11/8/2023): *"I am running subaru-preglobal-long in 2017 forester and
the auto high beams does not work."* — and jnewb1 had explained that exact symptom for his global
long branch the day before, 11/7/2023 6:36 PM: *"The message isn't blocked, but I'd bet when
eyesight faults it stops sending that message"*, plus 11/7/2023 7:23 PM: *"ES_HighBeamAssist is the
message if you want to take a look, though I think the only way to preserve is would be to keep
eyesight from faulting by faking some more feedback stuff"*. And `emalton`'s one-line description
of the branch: **"has long support (no eyesight)"**.

**Contrast with GLOBAL — do not conflate these.** martinl's wiki
`https://raw.githubusercontent.com/wiki/martinl/openpilot/Subaru-longitudinal-control.md`
(**resolved, read in full**) opens: *"Openpilot longitudinal control for Subaru **global platform**
works by controlling engine power request (rpm), cruise throttle and cruise brake signals"* and
claims *"With openpilot longitudinal control activated, Eyesight remains in ready state, so PCB/AEB
and FCW safety features signals are passed through."* **That "EyeSight stays ready" claim is
explicitly about the global platform, and it is contradicted for gen2 by jnewb1 himself**
(11/23/2023 8:08 PM): *"totally kills eyesight though, so you lose AEB, High beam assist, etc"*,
followed by *"for gen1 its possible"* when asked whether passthrough could be preserved. There is
**no** source anywhere in this corpus claiming EyeSight stayed healthy alongside preglobal long.

**Why this matters for this project specifically:** it means the failure mode this project already
hit in Q9 (a single unmodified frame injected onto the camera bus faulted EyeSight off) is *not*
what preglobal long did. Preglobal long worked in the opposite direction — main-bus transmission
with camera-side suppression at the relay — which is the architecture openpilot already uses on this
car for 0x161 and 0x164 today. `ES_Brake` (0x160) and `ES_Status` (0x162), however, are **not**
currently relay-blocked, so writing them today without a safety change would put openpilot's frames
on the car bus *interleaved with EyeSight's forwarded originals* — which is precisely the "duplicate
messages" situation aileron.me hit. `mlp______` on that, 10/15/2020 9:14–9:18 AM:

> "filtering messages using panda + copy/rewrite in openpilot is usually more reliable than just
> spamming messages and hoping for the best"
> "I think if there are multiple messages with same counter then first one to arrive at receiveing
> ecu is accepted and rest are dropped"
> "most preglobal can messages do not have counters so spamming may still work in some cases"

---

## Q4 — Scaling / encoding of preglobal `Cruise_Throttle`

**Partial. One real code data point, no explicit measured statement.**

- **Field width (verified from DBC):** preglobal `ES_Distance.Cruise_Throttle` is
  `0|12@1+ (1,0) [0|4095]`. Global is `16|13@1+`. Global was *corrected* from 12→13 bits by jnewb1
  in `https://github.com/commaai/opendbc/commit/40d9c723d48496229fecc436046538a53af19c11`
  ("Subaru: cruise_rpm and cruise_throttle are 13 bits (#995)", 2023-12-29) — and that commit
  touches **global DBC files only**; preglobal was left at 12 bits.

- **The one real preglobal value data point** is Bugsy's Jan 2020 `carcontroller.py` on his 2015
  Outback, verbatim:
  ```python
  if enabled:
    throttle = actuators.gas * 2048 + 1818
  else:
    throttle = 808
  ...
  if enabled:
    brake = actuators.brake * 1024
  else:
    brake = 0
  ```
  Those anchor constants — **1818 for "no acceleration" and 808 for the disengaged/engine-brake
  value** — are *identical* to the global constants that live in upstream
  `opendbc/car/subaru/values.py` today:
  ```python
  THROTTLE_MIN = 808
  THROTTLE_MAX = 3400
  THROTTLE_INACTIVE     = 1818   # corresponds to zero acceleration
  THROTTLE_ENGINE_BRAKE = 808    # while braking, eyesight sets throttle to this, probably for engine braking
  ```
  Bugsy's preglobal range works out to 1818–3866 (vs global's 1818–3400 cap), and his brake range to
  0–1024 (vs global `BRAKE_MAX = 600`).

  **Confidence caveat:** this is an *inference from code someone wrote in 2020 on a preglobal car*,
  not a statement anyone made and not a measurement I can independently confirm. The 808/1818 match
  is strong evidence the encoding anchors are shared, but the upper end (2048 vs 3400 span, 1024 vs
  600 brake) clearly differs and looks hand-picked rather than measured. **Treat "preglobal uses the
  same 808/1818 anchors" as likely; treat "same 808/1818/3400 *range*" as unverified.**

- **Contradicting low-confidence datapoint, recorded for honesty:** Bugsy himself, 10/12/2020
  10:08 PM, asked what unit `Throttle_Cruise` is in: *"umm %"* / *"or 0-255"* / *"i can't remember,
  that was at least 3 years go"*. Do not weight this — he was guessing about a message he'd last
  looked at years earlier, and it conflicts with his own code.

- **Global-only reference for comparison** (martinl wiki, explicitly global): *"[ES_Distance]
  [Cruise_Throttle] - (0..4000) output, related to [Throttle][Throttle_Cruise]"*, *"[ES_Brake]
  [Brake_Pressure] (0..400) - Cruise brake pressure"*, *"[ES_Status][Cruise_RPM] - (0...4000) Cruise
  RPM output for ECM/TCM"*. **These are global numbers. Do not apply them to preglobal.**

- **`Cruise_RPM` semantics on preglobal (first-hand, Bugsy 10/12/2020):** *"controls engine rpm"*,
  *"ES_RPM's request traces with the transmission message on the main bus"*. Preglobal
  `ES_Status.Cruise_RPM` is 16 bits `[0|65535]` in the DBC; martinl (4/9/2023): *"cruise_rpm signal
  is input for transmission which sets the cvt gear ratio"*.

---

## Q5 — sunnypilot's Stop-and-Go for preglobal: what does it actually write?

**Fully answered from source.** Cloned `https://github.com/sunnypilot/opendbc` (**resolved**),
HEAD `d427557285fc468b377963f3f71c2aa2e73e8eb4`.

**It does not touch `Cruise_Throttle`, `Cruise_RPM`, or `Brake_Pressure` at all — on preglobal or
global.** It spoofs the *car's own* sensor messages back at EyeSight, on the **camera bus**.

`opendbc/sunnypilot/car/subaru/subarucan_ext.py`, verbatim tails:

```python
  values["COUNTER"] = create_counter(throttle_msg)
  if send_resume:
    values["Throttle_Pedal"] = 5
  return packer.make_can_msg("Throttle", CanBus.camera, values)
```
```python
  if send_resume:
    values["Speed"] = 1 if CP.flags & SubaruFlags.PREGLOBAL else 3
  return packer.make_can_msg("Brake_Pedal", CanBus.camera, values)
```

- **Messages:** `Throttle` (**0x140**) and `Brake_Pedal` (**0xD1**).
- **Bus:** `CanBus.camera` = **bus 2** in both cases.
- **Preglobal-specific handling:** the preglobal branch copies a different signal set (no `CHECKSUM`,
  and `Brake_Pedal` on preglobal gets **no COUNTER** — the counter line sits only in the `else`
  branch). Preglobal `Brake_Pedal.Speed` is spoofed to **1**, global to **3**.
- **Preglobal-specific timing**, from `stop_and_go.py`:
  `mpb_standstill_timers = (0.75, 0.8) if self.CP.flags & SubaruFlags.PREGLOBAL else (0.5, 0.55)`.
- On preglobal (manual parking brake path) the trigger is simply *"Direct resume when the standstill
  hold threshold is reached to prevent ACC fault"*; the distance-based EPB resume sequence
  (`_SNG_ACC_MIN_DIST = 3`, `_SNG_ACC_MAX_DIST = 4.5`, using `ES_Distance.Close_Distance`) is the
  global/EPB path.

**Panda safety TX-allowlist change: YES, required, and it is real.** sunnypilot's
`opendbc/safety/modes/subaru_preglobal.h` splits the allowlist into two macros and picks between
them at init:

```c
#define SUBARU_PG_COMMON_TX_MSGS \
  {MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
  {MSG_SUBARU_PG_ES_LKAS,     SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \

#define SUBARU_PG_STOP_AND_GO_TX_MSGS \
  {MSG_SUBARU_PG_Throttle,    SUBARU_PG_CAM_BUS,  8, .check_relay = false}, \
  {MSG_SUBARU_PG_Brake_Pedal, SUBARU_PG_CAM_BUS,  4, .check_relay = false}, \
...
  safety_config ret = subaru_stop_and_go ? BUILD_SAFETY_CFG(subaru_preglobal_rx_checks, subaru_pg_stop_and_go_tx_msgs) : \
                                           BUILD_SAFETY_CFG(subaru_preglobal_rx_checks, SUBARU_PG_TX_MSGS);
```

Note `.check_relay = false` on both SnG messages — deliberately, since these are *additive* frames
sent toward the camera, not replacements for a forwarded ECU message. Gated by a runtime flag
(`SubaruFlagsSP.STOP_AND_GO` / `STOP_AND_GO_MANUAL_PARKING_BRAKE`, `SubaruSafetyFlagsSP.STOP_AND_GO = 1`).

**Provenance.** `https://github.com/sunnypilot/opendbc/pull/152` — **resolved.** "Subaru: Stop and Go
support (beta)", author sunnyhaibin, merged 2025-10-14; local commit `b8a00bd`. But the *feature*
is older and is martinl's: sunnypilot 0.9.5.1 changelog (posted by `sunnyhaibin` in the
`custom-forks` channel, 11/17/2023) reads **"NEW❗: Subaru - Stop and Go auto-resume support thanks
to martinl! * Global (excluding Gen 2 and Hybrid) and Pre-Global support"**, and `sunnyhaibin`
announced it earlier, 9/23/2023 8:24 PM: *"#custom-forks sunnypilot's `dev-c3` confirmed to work
with Pre-Global Stop and Go auto resume!"*.

I verified the lineage directly: `https://github.com/martinl/openpilot` branch
`subaru-community-long-sng` (**fetched successfully**) contains

```python
def create_preglobal_throttle(packer, throttle_msg, throttle_cmd):
  values = copy.copy(throttle_msg)
  if throttle_cmd:
    values["Throttle_Pedal"] = 5
  return packer.make_can_msg("Throttle", 2, values)
```

— identical mechanism, bus 2, three years earlier.

**Bottom line for Q5: sunnypilot's preglobal SnG is not longitudinal control and is not evidence
about the ES command trio.** It is a camera-bus sensor spoof that convinces EyeSight the driver
touched the throttle. It is, however, a live, shipping, upstream-merged precedent for **openpilot
transmitting fabricated frames on this car's camera bus without faulting EyeSight** — which is worth
reconciling against this project's own Q9 camera-bus result (a single injected `CruiseControl` 0x144
copy produced a dash "EyeSight Off" fault). The difference is *which* address: 0x140/0xD1 are
messages EyeSight *receives* from the car, whereas 0x144 is one EyeSight itself also sees from a
real transmitter on the main bus.

---

## Consolidated: what would actually be required to write each field today, on this car

| Field | Message | Already TX-allowed? | Camera copy already relay-blocked? | Panda change needed? |
|---|---|---|---|---|
| `Cruise_Throttle` | `ES_Distance` **0x161**, bus 0 | **YES** (`SUBARU_PG_COMMON_TX_MSGS`) | **YES** (`check_relay = true`) | **None.** openpilot is already the sole source of this frame and already copies the field through verbatim. No `tx_hook` bound exists on 0x161 |
| `Cruise_RPM` | `ES_Status` **0x162**, bus 0 | **NO** | **NO** | Add to TX list. Historically confirmed necessary and sufficient to get on the wire (aileron.me, 10/17/2020, "Ok it worked"). Also needs relay-blocking or you get duplicates, and the DBC's undefined bits are a known landmine |
| `Brake_Pressure` | `ES_Brake` **0x160**, bus 0 | **NO** | **NO** | Same as above. Never independently confirmed working on preglobal by anyone in this corpus |

---

## Open threads worth a future pass

1. **Wayback Machine on `installer.comma.ai/jnewb1/subaru-preglobal-long` and on
   `github.com/jnewb1/openpilot/tree/subaru-preglobal-long` / its commits page.** Blocked here.
   A single 40-hex SHA from that branch makes the whole branch recoverable via
   `git fetch https://github.com/commaai/openpilot <sha>` — technique verified working in this session.
2. **GH-Archive PushEvent data for actor `jnewb1`, Aug–Dec 2023** (e.g. via the public ClickHouse
   `github_events` dataset). Same goal: one SHA. Unreachable here.
3. **Discord thread `1137397673989775392`** — referenced twice as *the* preglobal-long thread
   ("still a WIP for preglobal", "this also works for pre-global check <thread>"). Not among the 13
   exported channels. If the export can be extended, this is the highest-density remaining source.
4. **`martinl/openpilot` branch `feature-subaru-long` family** (~20 branches, all still live) — I
   confirmed the branch names exist but only read `subaru-community-long-sng`. These are global-focused,
   but `feature-subaru-long` was cited by aileron.me in a preglobal context and may contain the
   RPM-curve modelling that both preglobal attempts lacked.
