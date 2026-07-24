# Live test: does the real cruise ECU act on a commanded `Cruise_Button` value?

## RESULT (2026-07-23): YES — confirmed, clean, on real telemetry. Q6 effectively closed.

**v2 ran for real.** Armed on WiFi at 23:08:09 UTC, driven normally, fired autonomously
once at **23:10:42.888 UTC, vEgo≈12.94 m/s (28.9mph), `real_cruise_button=0`** (no real
press — purely software-commanded `cruise_button=2`, SET shallow). One-shot held: flag
consumed, exactly one log line. Route `00000038--f7ad6dd860` synced to the archive after
the drive; pulled and analyzed offline (GPS-anchored `logMonoTime`→wall-clock mapping,
±15s window around the logged fire time).

**Directly confirmed on the wire** (not just trusting the local log file) — the commanded
frame itself, `Cruise_Button=2`, appears in the CAN capture at `src=128` (bus-0 TX-echo)
raw bytes `282380ff0050021c`, timed **-0.92s relative to the logged fire timestamp** (a
real GPS-anchor/wall-clock offset, not a data problem — see caveat below).

**And the real ECU reacted, fast and completely normally, like an actual press:**

| event | value change | time (rel. to logged fire) |
|---|---|---|
| commanded frame on wire (`src=128`) | `Cruise_Button` 0→2 | -0.92s |
| `carState.cruiseState.enabled` (from `CruiseControl`/0x144) | `False`→`True` | -0.82s |
| `ES_DashStatus` (camera bus, `src=2`) | `Cruise_Activated_Dash` `False`→`True`, `Cruise_Set_Speed` `0`→`28` | -0.78s |
| `carState.cruiseState.speed` | `0.00`→`12.52 m/s` (**28.006mph** — matches the car's actual speed at the moment almost exactly) | -0.31s |

Held steady at 12.52 m/s / 28mph for the entire +15s observed afterward, no further
button activity, no fault, no anomaly. `vEgo` kept climbing independently afterward
(13→18 m/s) — expected, not a bug: this car has no real longitudinal actuation
(`openpilotLongitudinalControl=False`), so `cruiseEnabled`/`Set_Speed` reflect the ECU's
own internal ACC state, not something actually holding the car's real speed.

**This is a genuinely different result from the parked test** (below) — that one showed
zero response to *any* button, real or planned-commanded, while stationary. This one
shows a **real ECU-level engage, triggered purely by software, at driving speed** — the
first confirmed actuation success of this entire project, not just a passive-relay
confirmation.

**One honest caveat:** the commanded-frame/reaction chain above is internally consistent
to ~100ms (TX → `CruiseControl` flip → `ES_DashStatus` flip, in that order, tightly
spaced) — the causal read is solid. But the whole chain sits ~0.8-0.9s *before* time 0 on
this scale, where time 0 is the Python `time.time()` timestamp the test hook itself
logged. That's a real offset between the device's own wall clock and the GPS-derived
`logMonoTime` anchor used to place this route on a wall-clock axis — not a sign the wrong
moment was analyzed (the value match, `28` psi matching real `vEgo`, and the tight
internal spacing make that clear), just noted plainly rather than presented as
false-precision-free.

**Test code has been reverted off the device** (commit `2ba5623`, redeployed, rebooted) —
it should not still be running on the car after this session.

---

**v1 below (parked/manual-arm) is superseded by v2, which is what actually ran (result
above).** Left in place as the reasoning trail: v1's design (park, engine idling, SSH in,
touch a flag file, watch the dash) turned out to be untestable for a real reason found via
a quick zero-risk RX-only check (§ "Parked-test result" below), and separately can't work
at all once the car leaves WiFi range with no Tailscale set up. v2 (further below) is the
design that was actually deployed and fired.

## What this tests

Everything confirmed so far (`es_distance_cruise_button_finding.md`) is about the
*passive relay* — `ES_Distance`'s `Cruise_Button` field faithfully reflects real physical
presses, 98–99.5% clean across 592 real events. Nobody has tested the other direction:
does the real cruise ECU actually *act* on a software-chosen value the way it acts on a
real press? That's the one thing this whole lead hinges on and it's untested.

## Why this isn't a bench script like the UDS tests

`uds_silence_test.py`/`uds_probe.py` stopped `pandad` first because they were injecting
*new* one-off diagnostic requests onto an otherwise-undisturbed bus. `ES_Distance` is
different: **openpilot's own control loop already transmits it every single frame,
unconditionally, right now, whenever the device is onroad** (`carcontroller.py`,
unconditional PREGLOBAL block, no `openpilotLongitudinalControl` gate). Stopping `pandad`
to run a standalone script would silence that already-flowing relay — including real
fields this project doesn't even care about testing (`Cruise_Throttle`, `Car_Follow`,
`Close_Distance`, `Standstill`, `Cruise_Fault`, the live counter/checksum) — a bigger,
messier disruption than any prior test needed.

The lower-risk design instead: **substitute only the `Cruise_Button` byte, for exactly
one message cycle, inside the existing production code path** — same packer, same
checksum, same counter continuation, same real values for every other field (all pulled
live from `CS.es_distance_msg` same as today). This is structurally the same reasoning
that made this lead promising in the first place (already-owned, already-correct
transmission — not a hand-rolled stale frame like the `CruiseControl` test that produced
the EyeSight-off fault).

## A landmine avoided: no new Params key

The obvious way to arm a one-shot test would be a new `Params` key (e.g.
`EsDistanceButtonTestArm`). **Deliberately not doing that.** This device's branch
(`phase1-curve-advisory`) is a prebuilt-only release export — no `SConstruct`, `scons`
never runs — and `common/params_pyx.so`'s compiled key allowlist is fixed. This exact
failure mode already crashed `plannerd` once this project (`UnknownKeyName` on
`CurveSpeedAdvisory`, §11 in `progress.md`). Doing the same thing inside
`carcontroller.py` would be far worse — that call happens in the live control loop, not
a helper's `__init__`, so an unregistered key would crash-loop `carcontroller`/`controlsd`
itself, on every onroad boot, silently, the moment this code shipped. **Using a plain
file-existence flag (`/data/es_distance_test_arm`) instead** — no `Params`, no compiled
allowlist involved, same class of primitive already used safely elsewhere in this
project (log files, marker files).

## Proposed code change

See `research/es_distance_button_test.patch` (not applied). Summary:

- Isolated addition inside the existing unconditional PREGLOBAL `cruise_button` block in
  `carcontroller.py` — default behavior (flag file absent) is byte-for-byte identical to
  what ships today.
- Fires **only** if `/data/es_distance_test_arm` exists **and** `abs(CS.out.vEgo) < 0.5`
  (parked interlock, checked in code, not just trusted from the human).
- Test value: `cruise_button = 2` (**SET shallow**) — deliberately the smallest, most
  reversible option. Not `1` (`main` — could toggle cruise on/off entirely) and not `4`/`5`
  (`resume` — could unexpectedly resume a stale set speed). A shallow SET's worst case is
  a 1mph nudge to a value that may not even be displayed if cruise isn't engaged.
- **One-shot by construction**: the flag file is deleted the instant it fires, so it
  cannot repeat without a human explicitly re-touching it.
- Logs every firing (timestamp, frame, `vEgo`, real `CS.cruise_button` at that moment) to
  `/data/es_distance_button_test.log` for exact correlation against whatever the dash
  shows on video.

## Preconditions (human-verified before arming, not just code-checked)

- Car in Park, **engine running/idling** — not just ignition-on/engine-off like the UDS
  tests. Cruise/ACC availability plausibly requires the engine actually running; an
  ignition-only precondition might send the command with nothing observable to confirm
  or refute it reached the ECU meaningfully. This is a real step up in "aliveness" vs.
  every test run so far tonight — still stationary, still Park, still not driving, but
  flagging it honestly as more than a pure bench test.
- Foot on brake or parking brake engaged, car fully stationary.
- Cruise/ACC **not** already engaged at test start, so a SET response is unambiguous
  (something appearing where nothing was before, not a value changing on an
  already-active system).
- Dash/cluster in frame and recorded (phone video) for the entire test — the actual
  ground truth is what the dash shows, not code getting cleanly to `can_sends`.

## Run sequence

1. Deploy patch, confirm `git pull` + reboot, confirm process health (all onroad
   processes clean, no crash logs) — same verification discipline as every prior deploy.
2. With engine idling in Park, dash visible/recorded: SSH in, `touch
   /data/es_distance_test_arm`.
3. Watch the dash for any change (cruise indicator appearing, a set-speed number, any
   fault light) for a few seconds.
4. `cat /data/es_distance_button_test.log` to confirm it actually fired and see the exact
   moment, cross-reference against the video.
5. **Reboot regardless of outcome** — same rollback discipline as every other live test
   this project has run. Confirm HEAD, confirm no crash logs, confirm normal onroad
   process set comes back.
6. If any fault/warning light appears at any point: stop immediately, note it, do not
   repeat, ignition-cycle to clear, treat as a real negative result (same as the
   `CruiseControl` camera-bus incident) — not something to retry differently first.

## Honest gaps this test does NOT close even if it "works"

- One shallow-SET result doesn't validate `3`/`4`/`5` (deep set, resume shallow/deep) —
  each would need its own deliberate, separately-confirmed test, not assumed by analogy.
- Even a clean single success doesn't establish whether *sustained/rapid* commanded
  presses (what real Phase-3 actuation would eventually need) behave the same way — a
  single one-shot tap and a held/repeated command are different regimes, especially given
  how much this project's already learned about counter/checksum staleness mattering.
- Still says nothing about closing the loop end-to-end (deciding *when* to send a
  command) — this only tests whether the ECU listens at all.

---

## Parked-test result (2026-07-23) — why v1 can't work as written

Before deploying v1, ran a quick zero-risk RX-only check instead
(`tools/phase2/live_es_distance_monitor.py`, deployed and run live over SSH, engine
idling in Park, MADS keeping `Cruise_On`/main always-on) to see what real physical
SET/RES presses actually do at the CAN level while stationary, before spending the one
TX test on an assumption. Result, real telemetry:

- `ES_Distance.Cruise_Button` responds exactly as expected to real presses (`2`/`3` for
  SET, `4`/`5` for RES) — reconfirms Q6 live, not just from the archive.
- `ES_DashStatus.Cruise_Activated_Dash` stayed `False` and `Cruise_Set_Speed` stayed `0`
  across every single press, real button, zero exceptions, despite `Cruise_On` (main)
  being `True` throughout.

**Conclusion: this car's cruise ECU doesn't "activate" from a button press while
parked/idling, real button or not.** Standard EyeSight behavior — ACC generally won't
engage at 0mph. This means v1's whole premise (fire the commanded value while parked,
watch for a dash change) can't produce a readable result: a commanded `2` firing and
`Activated_Dash` staying `False` would look identical whether the ECU ignored the
software command *or* just doesn't engage below driving speed — which was just proven
true regardless of button source. Spending the live TX test in this state would answer
nothing.

## v2: driving test, no SSH/WiFi required during the drive

Second constraint on top of the above: the device only has WiFi at home, no Tailscale
installed yet (deliberately not pursued — see `progress.md` §9), so there is **no way to
arm, observe, or abort this test live once the car leaves the driveway.** The whole
design has to be autonomous and self-contained, with all analysis done after the fact.

**This fits how this project already works, not a new pattern:** the comma pipeline
(`<local-rlog-pipeline>`) continuously syncs full `rlog.zst` off the device to the NUC
archive independent of any SSH session — that's the exact mechanism tonight's Q6
correlation pass (and Q4 before it) already used. So the test doesn't need a live channel
at all: arm it before leaving WiFi, let it fire autonomously under tight gating during
the drive, pull the synced route afterward, analyze offline exactly like every other
passive pass this project has done.

### Trigger redesign (autonomous, not human-touched mid-drive)

Old v1 trigger: human touches a flag file right before the test, checked against
`vEgo < 0.5` (parked interlock).

New v2 trigger — fires **at most once, per arm, automatically**, only when ALL of these
hold simultaneously (checked every 5-frame cycle, same cadence as the existing block):

- `/data/es_distance_test_arm` exists (armed before leaving WiFi) **and** its mtime is
  less than 30 minutes old — auto-expiring, so a forgotten arm can't sit live for some
  future, unrelated drive.
- `CS.out.vEgo > 11.2 m/s` (~25mph) **sustained for 2 full seconds** (not a single-frame
  blip) — avoids firing during a brief speed spike (e.g. mid-merge), and 25mph matches
  this project's own already-documented EyeSight floor elsewhere in the codebase.
- `CS.out.cruiseState.available` is `True` **and** `CS.out.cruiseState.enabled` is
  `False` (sourced from `CruiseControl`/0x144's own `Cruise_On`/`Cruise_Activated` —
  same fields this exact code block already reads two lines above, not a new source) —
  only ever attempts to engage from a genuinely-not-already-engaged state, so it can't
  interfere with or mask an already-real cruise session.
- `CS.cruise_button == 0` that frame — driver isn't mid-press on the real wheel switch,
  avoids colliding with real input.
- Not already fired this process lifetime (in-memory flag, belt-and-suspenders on top of
  the file check, so it truly cannot double-fire within one drive even if the file check
  raced somehow).

On fire: `cruise_button = 2` (SET shallow, same reasoning as v1 — smallest, most
reversible option) for that one message, then **immediately and permanently delete the
flag file** (real disarm, not reversible without a human re-arming next time on WiFi),
and log a full state snapshot (timestamp, frame, `vEgo`, real `CS.cruise_button`) to
`/data/es_distance_button_test.log`.

### Why this is still bounded, even without live oversight

- Test value stays `2` only — worst case is functionally a driver's own accidental bump
  of the real SET button: cruise engages at current speed, or a ~1mph nudge if already
  engaged (which the gate above prevents anyway, since it only fires from
  not-yet-engaged). Ordinary, reversible, something the driver can immediately override
  with a real button press or the brake, same as any errant real cruise state — no
  different in kind from a mis-press that already happens on real drives.
- Same already-flowing production packer/checksum/counter path as v1 — not a new,
  potentially-stale frame like the `CruiseControl` test that caused the EyeSight-off
  fault.
- Fires at most once, ever, per arm — not a standing behavior change. Default (unarmed)
  state is byte-for-byte identical to shipped code, same as v1.
- All the actual observation happens offline, after the fact, from the synced rlog —
  removing "must watch a screen while driving" from the loop entirely, which is a safety
  improvement over v1's design, not just a workaround for the WiFi gap.

### Run sequence (v2)

1. On WiFi at home: deploy the v2 patch, `git pull` + reboot, confirm process health
   (same discipline as every prior deploy) — done well before any drive, not same-day
   rushed.
2. Still on WiFi, before leaving: SSH in, confirm cruise is currently *not* engaged, `touch
   /data/es_distance_test_arm`.
3. Drive normally. No phone/SSH interaction needed or expected during the drive — the
   whole point of this redesign. If it fires, it fires once, quietly, logged only.
4. After the drive, once the route has synced to the NUC archive (or once home on WiFi
   and reachable again): pull `/data/es_distance_button_test.log` and cross-reference its
   timestamp against the synced route's `ES_DashStatus`/`ES_Distance` telemetry —
   specifically whether `Cruise_Activated_Dash`/`Cruise_Set_Speed` changed in the ~1-3s
   following the logged firing moment. This is the actual verdict; nothing needs to be
   observed live.
5. Immediately re-verify `/data/es_distance_test_arm` is gone (confirms one-shot held) and
   deploy the **rollback**: revert the patch, redeploy, reboot, confirm HEAD and process
   health — do not leave this code live on the car beyond the single drive it was meant
   to test, armed or not.
6. If the driver notices any fault light or unexpected behavior during the drive: that's
   the signal to stop pursuing this line entirely and treat it as a real negative result
   (same standard as the `CruiseControl` incident), not something to retry differently.

### Added gap vs. v1

- No live human confirmation that the fire moment was actually a reasonable, safe moment
  to test at (v1 could rely on a human choosing to arm at a good moment; v2's trigger has
  to encode "good moment" entirely in code — the gating above is the whole safety case,
  there's no human failsafe in the loop once the drive starts).
