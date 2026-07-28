# Phase 3 speed-limit-following design (third Phase 3 feature)

**Status: DESIGN ONLY. No code, nothing deployed, nothing touching the device.** Same
posture as `phase3_controller_design.md` when it was written — this is the design pass
requested after the 2026-07-24 live drive that got curve+lead actuation working and
surfaced this as the next real feature. A separate session with device access
integrates and tests whatever this settles on.

Third Phase 3 actuation feature, alongside curve-speed and lead-vehicle-closing. Same
button-spoofing primitive (`cruise_button=2` SET-shallow / `=4` RESUME-shallow, confirmed
nudge-not-rebaseline per Q10), same file-based `plannerd`→`carcontroller.py` architecture,
same `Phase3CommandArbiter`/override-latch/arm-gate skeleton described in
`phase3_controller_design.md`. This doc assumes that doc's §1-§9 as background and only
covers what's new or different for this feature.

## What this reuses vs. what's genuinely new

**Reused, unmodified:** the SET/RESUME nudge primitive, the freshness-gated command-file
handoff to `carcontroller.py`, `MIN_COMMAND_INTERVAL_S=0.4s`, `ABSOLUTE_FLOOR_MPH≈25`, the
per-event budget pattern, the two-gate arm philosophy (reactive override + proactive
per-feature `Phase3*Armed` param), and — for the already-shipped passive advisory —
`speed_limit.py`'s existing OSM-`maxspeed`-via-`mapd` read path.

**Genuinely new:**
1. A speed-limit-following (SLF) trigger/target policy (§1-§2).
2. A real change to how the override latch treats a detected button press — not a change
   to *what* triggers it, but to *what it does* when a button press (as opposed to
   brake/gas/steering) is the trigger, and *when* it escalates to the existing shared
   kill-switch (§3-§4). This is the requested open question — worked through, not assumed.
3. A "pinned target" concept for SLF that the existing curve/lead controllers don't need,
   since curve/lead always fully restore to a pre-intervention baseline, but SLF's
   corrections are meant to persist (§5).
4. A one-line, independently-decided gating fix to the existing passive display (§8) —
   unrelated to the actuation design, included here because the driver asked for both in
   the same request.

---

## §1 Trigger/target logic

**Source**: reuse the already-shipped passive path exactly — `mapd`'s OSM `maxspeed` tag
resolved against the car's live position, the same signal `speed_limit.py` already reads
to render the on-screen number. Same "don't duplicate a computation Phase 1 already
proved out" principle curve-actuation used with MTSC's `output_v_target`/`distance`.

**Buffer**: `Phase3SlfBufferMph`, default **+5mph** over the posted limit (per the
driver's explicit ask), a simple tunable constant — no reason to hardcode it if a param
read is free.

**Target formula (v1, decrease-only — see §2 for why)**:

```
on a detected, debounced posted-limit change to a NEW value L (see debounce below):
  candidate_target = L + Phase3SlfBufferMph
  if candidate_target < current_held_target (i.e. this segment requires slowing down):
      slf_target_mph = max(candidate_target, ABSOLUTE_FLOOR_MPH)
      begin walking cruiseState.speed down toward slf_target_mph via shallow SET,
      same MIN_COMMAND_INTERVAL_S/deadband/per-event-budget pattern as curve
  else:
      do nothing — v1 does not auto-raise (§2)
```

**Segment-change debounce**: a raw `maxspeed` read is a single tile/way lookup, subject
to the same GPS-jitter/tile-boundary flicker that made Phase 1's curve advisory need a
rising-edge debounce. Propose requiring the new value to read consistently for some
short persistence window (**2-3s, guessed, not measured** — flagged explicitly, same
epistemic status as `MIN_COMMAND_INTERVAL_S` before the cadence archive-mining pass
grounded it) before treating it as a real segment change worth acting on. This needs its
own real-telemetry pass before Stage 1 shadow-mode validation is trusted, the same way
curve's distance-formula needed the archive-mined cadence data before it was trusted.

**Explicitly NOT inheriting the existing ~35mph curve-advisory minimum-speed gate.** That
gate exists because OSM curvature alone can't tell a highway sweeper from a city
roundabout — it's a false-positive suppressor specific to curvature data. SLF's entire
premise is the highway→small-town transition, which by construction crosses through and
below 35mph. Reusing that gate would silently disable the feature for its primary use
case. The debounce window above is SLF's equivalent false-positive suppressor, tuned to
a different failure mode (tile/GPS noise, not curvature ambiguity).

**Floor**: same shared `ABSOLUTE_FLOOR_MPH`. If `L + buffer` computes below the floor
(e.g., a 15mph zone: 15+5=20, below EyeSight's ~25mph ACC floor), clamp to the floor —
same "auto-downgrade to the largest reachable/legal target" philosophy curve already
uses for insufficient lookahead distance, applied here to an unreachable low target
instead of an unreachable-in-time one.

**Arming precondition**: cruise must be actively engaged (`carState.cruiseState.enabled`)
— identical precondition to curve/lead's existing "if I set cruise, and only if I do,
then it should take over" framing. Notably, this is *the same boolean* §8's passive-
display fix gates on — not a coincidence worth over-reading, just the same natural
condition applying to both an actuation feature and a display feature that both only
make sense while cruise is actually doing something.

## §2 Scope decision: decrease-only for v1 (flagged, not silently assumed)

The driver's own examples — "hold 70 on a highway posted 65," "wants 85 instead of
70" — are both instances of *resisting a slowdown SLF wants to make*, not instances of
wanting SLF to autonomously accelerate the car toward a newly-raised limit. Both are
satisfiable by a decrease-only v1 where a manual correction simply caps or cancels an
in-progress descent (§5).

**A fully symmetric version (auto-raise toward a higher limit on, say, re-entering a
highway after a town) is a materially different risk category from anything this project
has shipped so far, and I'm deliberately not including it in v1.** Curve and lead
actuation only ever *decelerate* the target and *restore* it back up to a value the
driver themselves already chose earlier in the drive — the ceiling for "how high" has
always been "wherever the driver already was." An auto-raise-on-new-limit SLF would be
the first Phase 3 behavior that pushes the target to a number the driver never
themselves selected this drive, in the accelerating direction. EyeSight already handles
unexpected braking as its core stock function (that's what ACC does); an unprompted
*acceleration* from a script is a genuinely new kind of surprise, untested here even
once. Recommend treating symmetric raise as an explicit v1.1 decision needing its own
discussion and its own staged rollout, not something to fold in by default because it
seemed like the natural generalization of "follow the limit."

If the driver wants v1 to also raise, that's a one-line reversal of the `if` in §1's
formula — flagging it as a decision to make explicitly, not implementing it silently.

## §3 The override-interaction-model question

**The actual question**: today, `Phase3OverrideLatch` trips on any of
`brakePressed`, `steeringPressed`, `gasPressed`, or `cruise_button != 0`, and a trip is
session-long with no auto re-arm — deliberately blunt, "tap once, everything goes dark."
For SLF, a driver overriding via the *same* SET/RESUME buttons should instead have that
correction become the new held value and let everything else keep running. The hard part
named in the task: **neither controller can see which button was pressed, or that a
button was pressed at all, directly** — `CS.buttonEvents` is never populated on this
preglobal car (confirmed, `progress.md` §7 Q11 and the `dba5d57` crash writeup: raw
`cruise_button` only exists on `carcontroller.py`'s own opendbc `CarState` object, not on
the capnp-published `sm['carState']` that `plannerd`'s controllers actually read). So
"was a button pressed" and "which feature was it about" both have to be inferred, not
observed.

### Options considered

**Option A — try to infer intent from the correction's direction relative to the
controller's own action.** E.g., a correction opposite the direction Phase 3 was
pushing reads as "resisting," same direction reads as "agreeing/impatient." Rejected:
direction doesn't actually separate *why* — a driver could press in either direction for
either a preference reason or a safety reason, and this adds a classifier with no real
discriminating signal behind it.

**Option B — use press count/burst shape as an urgency proxy** (rapid multi-press =
distress, single tap = calm correction). Rejected on this project's own prior data: Q4
found a firm single real press can mechanically double-pulse ~0.4s apart, and normal
*deliberate* preference-setting (e.g., walking from 70 to 85) legitimately needs many
shallow taps in a row. Burst count is confounded by ordinary usage, not a clean signal.

**Option C — require a new, distinct gesture** (double-tap, hold-and-release) to mean
"this is a deliberate correction, not a kill." Rejected: it adds a UX vocabulary the
driver has to remember and execute correctly *in the moment they're already reacting to
something* — exactly the wrong place to add cognitive load, and exactly the category of
fragility Q11's MADS-button investigation already hit and reverted (signal behavior
under real, rushed, imperfect presses is measurably worse than under careful, spaced
test presses). Also directly opposite this project's "ride the stock buttons, don't
invent new interaction" philosophy.

**Option D (chosen) — don't try to read intent off the button signal at all. Split by
*channel* (button vs. pedal/wheel) and by *context* (was a transient Phase 3 event
actually in progress when the press happened).**

Reasoning:

- **Channel split is well-grounded, not arbitrary.** Brake, gas, and steering are never
  routine cruise-housekeeping actions on this car — nobody taps the brake to adjust a
  preference. Every real occurrence of one of those three is a meaningful signal,
  unconditionally, regardless of what Phase 3 happens to be doing. SET/RESUME are the
  *opposite*: they're the ordinary, everyday mechanism for completely mundane cruise
  adjustments unrelated to Phase 3 at all (resuming after a stop, nudging speed on an
  open highway, etc.) — the "meaning" of a button press is genuinely context-dependent
  in a way a pedal press isn't. So: **pedals/wheel keep the exact current unconditional
  blanket-kill behavior, unchanged, for all three features (curve, lead, SLF).** This is
  the actual "something's wrong" channel and shouldn't get more lenient for anyone.

- **Button presses need a context check, and the only context available is "was curve
  or lead actively mid-intervention right now."** Here's the part that isn't optional:
  a bare, ambiguous button press has no way to declare which feature it's "about." If
  curve/lead's existing per-frame override check stays exactly as unconditional as it is
  today (any button press, active or not, trips the shared latch), then *any* SLF-only
  correction on a calm straight highway — the driver's own headline example — would
  still nuke curve and lead for the rest of the drive, which directly contradicts the
  ask. There's no way to protect SLF's routine corrections from the shared kill switch
  without *some* logic distinguishing "this button press coincided with something
  curve/lead actually cared about" from "this button press is unrelated ambient
  adjustment." The least invasive way to draw that line, without inventing a new
  gesture or trying to read minds: **was curve or lead's own event state actually active
  (curve: rising edge of `turning` through the end of its restore-to-baseline window;
  lead: rising edge of the compound closing trigger through the hysteresis-cleared
  falling edge) at the moment of the press.**

  - If yes → the press is treated exactly as it is today: full, unconditional,
    session-long trip of the shared latch, killing curve, lead, *and* SLF. This is
    precisely the scenario that's already been validated on real drives (e.g. the
    documented steering-override latch during the third, larger curve on the first live
    actuation drive) — nothing about that path changes.
  - If no (both dormant) → the press cannot be "about" an active curve/lead event,
    because neither has one running. It's routed to SLF as a pinned-target correction
    (§5) instead, and the shared latch is **not** tripped — curve and lead stay live for
    whatever the rest of the drive brings.

**This is a real, if narrow, behavior change to curve/lead's own trigger condition** —
worth being explicit about rather than hiding it inside "SLF gets new behavior, nothing
else changes." What actually changes: a button press that happens while curve and lead
are *both* dormant no longer pre-emptively silences *future* curve/lead events later in
the same drive. What doesn't change: a press during an actual active intervention still
produces the exact same full blackout as today. The only drives affected are ones where
a stray, unrelated button press occurred with nothing running for it to interrupt — by
definition nothing was actually protected by the old behavior in that case, only future
events were collaterally silenced by a press that had nothing to do with them.

**Honest remaining false-positive/false-negative, named rather than hidden**: a button
press that happens to *coincide* with an active lead-closing episode (which can run
continuously in the background for many seconds without necessarily feeling "active" to
the driver) but was actually meant as an SLF correction unrelated to that episode will
still get the full blanket kill under this design. That's an accepted, deliberate
asymmetry: when the context signal is ambiguous, default to the more conservative
(kill-everything) interpretation, not the more permissive one — same posture this
project has taken everywhere else a genuine ambiguity showed up (e.g. the gas-pressed
addition after realizing the override set was incomplete).

### Answer, restated in one line

Pedals/wheel: unconditional blanket kill, unchanged, no context needed, applies to all
three features. Buttons: escalate to the same blanket kill only when a transient
curve/lead event is actually in flight; otherwise route to SLF as a pinned correction,
touching nothing else.

## §4 Detecting that a button was pressed at all

The mechanism above depends on being able to say "a button press just happened" from
`plannerd`, which — again — has no `buttonEvents` and no raw `cruise_button` field. The
only observable is `carState.cruiseState.speed` changing. This project already leans on
exactly this fact once: the `64d42da` settle-resync fix explicitly notes it's "the only
way either [controller] will ever notice the driver adjusted their real set speed
mid-drive." This design generalizes that same mechanism rather than inventing a second
one.

**Self- vs. external-attribution, once per planner cycle:**

```
observed_delta = cruiseState.speed_this_frame - cruiseState.speed_last_frame
if observed_delta == 0: nothing happened, done

# was this delta explained by a command WE (any Phase 3 controller) just wrote?
if a Phase 3 command was written within the last ~[carcontroller cadence + margin]
   and observed_delta's direction/magnitude matches what that command should produce:
       attribute SELF — not a manual press, no further action

else:
       attribute EXTERNAL — a real button press happened
       is_active = phase3_transient_event_active()   # curve or lead mid-event, §3
       if is_active: latch.trip(reason="button")      # existing behavior, unchanged
       else: route to SLF pinned-target capture (§5), do not trip the latch
```

**A useful structural simplification specific to decrease-only v1**: SLF (and curve's
fire-down phase) only ever issue SET, never RESUME. That means **any observed upward
(RESUME-shaped) delta is unambiguously external** — no self-attribution question even
arises, since nothing on the Phase 3 side ever produces that direction. Only downward
deltas need the timing/magnitude check against the command file, since those are the
ones Phase 3 itself might have just caused.

**This detector should be one shared utility in `phase3_shared.py`**, not reimplemented
per controller — same "hoist the shared constant/helper instead of duplicating it"
discipline that already applied to `MIN_COMMAND_INTERVAL_S` after the first
implementation pass duplicated it ad hoc across curve and lead.

**Flagged, not yet confirmed**: this whole detector is logically sound given what's
already independently confirmed (Q6's ~100ms end-to-end command-to-effect timing, Q10's
nudge semantics, the existing settle-resync fix) but has never itself been exercised
against a *real* driver button press landing in the same window as an in-flight Phase 3
command — a genuine race condition this design assumes is rare and resolvable, not
something actually observed happening yet. Recommend this be the first thing validated
in SLF's own Stage 1 shadow-mode pass, logging every classification decision (self vs.
external, active vs. dormant) against the real drive, before it's ever wired to a live
pin-or-kill decision — same discipline as everything else that's shipped here.

## §5 Pinned-target semantics

**Scope: per posted-limit segment, not session-long.** A manual correction becomes the
held value for the remainder of the *current* segment, but a genuinely new segment (a
real, debounced change in the posted limit — a new town, a new highway stretch) gets a
fresh, unconstrained `L + buffer` computation from scratch, independent of any earlier
correction.

This is a deliberate choice worth flagging rather than the only reading of "stay there."
The alternative — a correction persists for the rest of the drive/session regardless of
later segments — was rejected: it would mean a driver correcting a 65-limit highway back
up to 85 could, in the worst case, also suppress a *later, unrelated, genuinely lower*
limit (a school zone, a sharper town drop) from ever being followed, which is exactly the
kind of stale-override-blocks-a-real-safety-relevant-adjustment failure mode this project
has been careful to avoid elsewhere (e.g. why `SESSION_COMMAND_CAP` is a generous backstop
and not a tight one). Per-segment scope means the correction only ever suppresses
re-adjustment *within the segment the driver was actually looking at when they made it*.

If the driver actually wants "leave SLF alone for the rest of this drive entirely,"
that's a different, coarser action — disarming the feature via its own arm gate
(`Phase3SlfArmed`, §6), not something a single button tap should do silently as a side
effect. Worth surfacing to the driver as an explicit option once this is live, rather
than trying to guess from one button tap whether they meant "just this segment" or
"the whole rest of the drive."

**Mechanically:**

```
on a NEW segment (debounced posted-limit change), whether or not the previous segment
ended with a pin in place:
    reset pin state; compute a fresh slf_target_mph = L + buffer (§1)

on an external delta detected while dormant (§3/§4), during the CURRENT segment:
    slf_pin_mph = current cruiseState.speed (post-delta)
    slf_target_mph = slf_pin_mph   # stop trying to move it further, in either direction
    suppress further auto-SET commands for the rest of this segment
```

**Engagement-moment race condition, same category as the already-fixed
`baseline_v_cruise_mph=90.1mph` bug**: the very first frame SLF becomes gated-on (cruise
freshly engaged, or `Phase3SlfArmed` freshly set), `cruiseState.speed` populating for the
first time is not a manual correction — it's initialization. Reuse the same
`SETTLE_TIME_S`-style settle window already shipped for curve/lead's baseline resync
before SLF treats any delta as a correction rather than a startup transient.

## §6 Architecture integration

- **`Phase3OverrideLatch`**: pedal triggers (`brakePressed`, `steeringPressed`,
  `gasPressed`) unchanged — unconditional, immediate, session-long, feeds all three
  features equally. The button trigger becomes conditional on
  `phase3_transient_event_active()` (§3) before it calls `.trip()`; when it doesn't
  trip, the detected press routes to SLF's pin logic instead (§4-§5). This reuses the
  existing `trip_reason` field the `b2acc3e` grace-period fix already added — extend it
  to record `"button-while-active"` vs. the new `"button-while-dormant→SLF"` outcome, so
  the shadow log can show which path was taken, the same verification discipline used
  for every other piece of this project.
- **New shared helper in `phase3_shared.py`**: `phase3_transient_event_active()` —
  `curve.state in {turning, restoring}` OR `lead.state == episode_active`. Both curve
  and lead already track equivalent state for their own budget-reset logic; this just
  exposes a boolean view of it for the latch-gating decision, not new state.
- **New shared helper**: the self/external attribution classifier from §4, consumed by
  SLF and (optionally, for shadow-log completeness) by curve/lead too, even though their
  own behavior when a press is external-and-active doesn't change.
- **`Phase3CommandArbiter` priority**: curve > lead > SLF. If curve or lead have a
  pending write this cycle, SLF's write is deferred (retried next cycle), never
  collides. Ordering rationale: curve is the most torque/geometry-bound urgent case,
  lead is closing-distance/collision-adjacent, SLF is the least time-critical of the
  three — "eventually converge on the right cruising speed" tolerates a delayed cycle
  far better than a curve mid-turn does.
- **New arm gate**: `Phase3SlfArmed`, same defaults-off/deliberate-SSH-set pattern as
  `Phase3Armed`/`Phase3LeadArmed` — keeps SLF's rollout risk isolated from curve/lead,
  same reasoning already used to gate lead separately from curve ("lets curve actuation
  get trusted... before lead is turned on"). Same known landmine applies: this will hit
  the compiled-Params-allowlist issue `CurveSpeedAdvisory`/`Phase3Armed` already hit on
  this prebuilt branch until an actual reinstall registers the key — a pre-existing,
  already-documented constraint, not new to this feature.
- **Command file**: reuse the existing single shared file/arbiter path, not a new one —
  SLF is just a third source feeding the same one-write-per-cycle mechanism.

## §7 Settings table (v1 proposal)

| Setting | Value | Rationale / status |
|---|---|---|
| Buffer | `Phase3SlfBufferMph = 5` | Driver's explicit default ask. |
| Direction | Decrease-only for v1 | §2 — auto-raise is a new surprise-acceleration risk category, deferred to an explicit v1.1 decision. |
| Segment debounce | ~2-3s stable read before acting | **Guessed, not measured** — needs a real telemetry pass, same status `MIN_COMMAND_INTERVAL_S` had before the cadence archive-mining grounded it. |
| Min-speed gate | None (explicitly not inheriting curve's 35mph gate) | Would disable the feature for its own primary use case (highway→town crossing through &lt;35mph). |
| Floor | Shared `ABSOLUTE_FLOOR_MPH` (~25mph) | Same clamp as curve/lead. |
| Ceiling | N/A in v1 (decrease-only; no auto-raise to bound) | — |
| Command budget | Per-segment, shared per-event pattern | Segment = SLF's version of curve's "event." |
| Arm gate | `Phase3SlfArmed`, default off | Isolated rollout risk from curve/lead, same two-gate pattern. |
| Arming precondition | `cruiseState.enabled` | Same as curve/lead; same boolean §8 uses for the display gate. |
| Pin scope | Per-segment, not session | §5 — avoids a stale correction suppressing a later, genuinely lower limit. |
| Override — pedals | brake/gas/steering, unconditional, unchanged | Same latch, same behavior, all three features. |
| Override — buttons | Conditional on `phase3_transient_event_active()` | §3 — the actual design answer to the open question. |
| Arbiter priority | curve &gt; lead &gt; SLF | Least-time-critical of the three defers cleanly. |

## §8 Passive display gate (separate, already-decided, simple)

The existing passive speed-limit advisory (`speed_limit.py`, OSM-`maxspeed`-driven,
shipped, not part of Phase 3 actuation) should render only while
`carState.cruiseState.enabled` is true. This is unrelated to the actuation design above
— included here only because it was asked for in the same request. Implementation is a
single added condition on the widget's existing render/visibility check, gated on the
same boolean SLF's own arming precondition uses (§1) — no new signal, no design
question, no interaction with the latch/arbiter at all. Worth double-checking there
isn't a second enforcement point the way `SmartCruiseControlMap` had two independent
param-wipe gates (`ui_state.py` and `interfaces.py::_cleanup_unsupported_params`) before
calling this done — that pattern has bitten this project twice already.

## §9 Staged rollout

Same five-stage process as `phase3_controller_design.md` §6, run as SLF's own
independent instance of it — not fast-tracked because curve/lead are already further
along:

1. Dry-run/shadow mode: log intended pins, segment detections, and
   active-vs-dormant/self-vs-external classifications against real drives — this is
   also where §4's attribution mechanism gets its first real validation.
2. First live enable, closed course: deliberately test a manual correction mid-descent
   and confirm it pins and stops, not just that the code compiles.
3. Repeat stage 2 before any public road.
4. Supervised backroad use, attentive driver throughout.
5. Broader use only after multiple clean stage 3/4 sessions.

Each transition needs explicit sign-off, same discipline as every other risk escalation
in this project.

## §10 Open questions / flagged assumptions this design does not resolve

- **§4's attribution mechanism is logically derived, not empirically tested.** Needs a
  dedicated shadow-mode validation pass before Stage 1 sign-off, specifically checking
  the self-vs-external classification against real button presses landing near a
  command-file write.
- **Segment debounce window (2-3s) is a guess.** Needs the same kind of archive-mining
  pass that grounded curve's cadence numbers, ideally before Stage 1, not after.
- **Whether `mapd`'s live-position `maxspeed` read is reliable enough for
  actuation-grade use, not just display-grade use, is unaudited.** Curve-actuation got
  an explicit "is this trustworthy enough to drive real actuation" pass before trusting
  MTSC's output for anything beyond an alert; SLF's source signal (current-position
  lookup, not MTSC's forward-curvature pipeline) hasn't had the equivalent pass. A bad
  tile-boundary read causing a spurious real deceleration is a different failure shape
  than a bad curve read (which at least degrades toward "did nothing," per the earlier
  MTSC-empty-region incident) — worth its own look before Stage 2.
- **Auto-raise (v1.1) is explicitly deferred, not designed here.** If pursued later, it
  needs its own risk discussion (new surprise-acceleration category) and its own staged
  rollout, not a silent reversal of §1's `if`.
- **The "coincidence with a dormant-but-recent lead episode" false-positive/negative
  edge case (§3) is named, not resolved** — accepted as a conservative-default trade-off,
  not something this design claims to have engineered away.
- **Whether the driver wants a coarser "ignore SLF for the rest of this drive" gesture
  beyond disarming the feature entirely is unaddressed** — §5 punts this to the existing
  arm-gate mechanism rather than inventing a new one, but it's worth confirming that's
  actually sufficient once this is live.
