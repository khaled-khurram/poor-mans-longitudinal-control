# Phase 3 controller design: closed-loop button-spoofing longitudinal control

**Status: DESIGN ONLY. No code, nothing deployed, nothing touching the device.** This is
the "end game" sketch requested after tonight's Q6 live-test success — the first time
software-commanded `cruise_button` values were confirmed to genuinely move the real ACC.
Per `claude.md`, actual implementation/deployment still needs explicit go-ahead, staged,
same as everything else in this project.

## What's actually confirmed vs. what this design depends on

**Confirmed (2026-07-23, real telemetry):** `cruise_button=2` (SET shallow), sent via the
`ES_Distance` TX path, while cruise was available-but-**not-engaged**, made the real ECU
engage cruise at the car's current speed (28.006mph, matched `vEgo` almost exactly) within
~100ms. See `research/es_distance_live_test_protocol.md`.

**NOT confirmed — and this is the load-bearing gap for the whole controller concept, not
just a nice-to-have:** what happens when `cruise_button=2`/`4` is sent while cruise is
**already engaged**. Two very different possible primitives:

- **(a) Nudge-from-target** — matches the DBC comment's literal semantics and how a human
  uses the real buttons: SET decrements the *existing target* by ~1mph (shallow) or ~5mph
  (deep), RESUME increments it. This is what the original vision doc (`progress.md` §1,
  "ride EyeSight's own setpoint... turn its dial") assumed, and it's what a real controller
  needs — the ability to walk an *already-active* target up/down in controlled steps,
  independent of current actual speed (e.g. pre-emptively lower the target before a curve
  while still going the old, higher speed).
- **(b) Re-baseline-to-current** — SET just captures whatever `vEgo` is *right now* as the
  new target, regardless of what the target already was. This is all tonight's test
  actually proved (cruise wasn't engaged, so there was no existing target to nudge from —
  the result is consistent with either theory). If this is what actually happens, the
  "advance-warning, pre-emptive slowdown" use case this whole project is built around
  doesn't work the way imagined — you could only ever lock in the speed you're already
  going, not aim for a target ahead of where you currently are.

**This needs its own dedicated test before any of the policy design below can be trusted
against reality** — a `cruise_button=2` send while cruise IS already engaged, observing
whether `cruiseState.speed` drops by ~1mph from its prior value or snaps to current
`vEgo`. This is a different test than what the parallel RESUME/deep/sustained-press
effort is covering (that one starts from not-engaged, same as tonight) — flagging it here
explicitly so it doesn't fall through the cracks between the two efforts.

The design below is written to be adjustable around either outcome, but is describing the
system assuming (a) turns out to be true, since that's the useful case — if (b) is what's
real instead, the whole approach needs rethinking, not just retuning.

## 1. Control policy

Keep v1 dead simple and closed-loop (verify the actual result of each command via
telemetry readback before deciding the next one — not open-loop dead-reckoning that
assumes a fixed effect per press):

```
every ~1s (see rate limiting below):
  target_v = <curve advisory target speed, or a fixed test target for early validation>
  current_v = CS.out.cruiseState.speed   # what the ACC currently thinks its target is
  error = target_v - current_v

  if abs(error) < DEADBAND (e.g. 1.5mph): do nothing
  elif error < 0: command SET-shallow (cruise_button=2)     # slow the target down
  elif error > 0: command RESUME-shallow (cruise_button=4)  # speed the target up
```

- **Shallow-only for v1, deliberately.** Deep (`3`/`5`) is unconfirmed both in direction
  and magnitude (Q6's passive pass couldn't separate it from shallow — see
  `es_distance_cruise_button_finding.md`). Don't build v1 on an assumed 5mph step; add a
  deep-step branch only once the parallel test confirms real magnitude, as a v1.1 change.
- **Closed-loop by construction**: because `cruiseState.speed` is readable after every
  command, the controller naturally self-corrects if a command didn't do what was
  expected (including catching the nudge-vs-rebaseline ambiguity above in practice — if
  `current_v` doesn't move the way the policy assumed, that's directly observable, not
  silently wrong).
- **Target source for v1 validation**: a fixed, operator-set test target (e.g. "hold
  45mph"), not Phase 1's live curve advisory — isolates controller-loop bugs from
  curve-advisory-timing bugs during initial validation. Wire to the real
  `curveSpeedAdvisory`/MTSC target only after the loop itself is proven stable in
  dry-run + closed-course stages (see rollout below).

## 2. Rate limiting

Sustained/repeated-press feasibility is being tested in parallel and hasn't reported back
— **don't hard-code an assumed-safe cadence.** Default to something well inside any
plausible safe range until that data lands:

- `MIN_COMMAND_INTERVAL_S = 1.0` (default, conservative) — one command per second max,
  adjustable once the sustained-press test confirms a real safe minimum spacing (this
  project's own earlier finding: real button spam beats holding for ramp speed, and a
  firm real press sometimes double-pulses ~0.4s apart — so *something* faster than 1s is
  probably fine, but "probably" isn't good enough to ship on before it's tested).
- `MAX_COMMANDS_PER_SESSION = 10` — a hard cap independent of the interval check, so a
  policy bug that decides to command continuously can't do so indefinitely even if the
  per-command spacing looks individually fine.

## 3. Hard safety bounds

- **Absolute floor: never command below EyeSight's own ~25mph ACC floor** (already the
  project's stated ceiling on the whole feature — `progress.md` §1: "it slows the car, it
  does not stop the car"). Refuse to issue a SET-direction command if the resulting target
  would go below this.
- **Absolute ceiling**: a fixed configurable max (e.g. current speed limit + margin, or a
  flat cap) — must exist, not left open-ended.
- **Max total delta per session**: bound the cumulative change the controller can apply
  across one drive, independent of the per-command cap above.
- **Driver override — airtight, not best-effort.** Checked *first*, before any policy
  decision, using fields already read today: `CS.out.brakePressed`, `CS.out.steeringPressed`
  (real torque override), `CS.out.gasPressed` (confirmed present, `carstate.py:31`,
  `Throttle_Pedal > 1e-5` — added 2026-07-24: without this, the controller could keep
  re-sending SET commands trying to walk the target back down while the driver is
  actively flooring it to overrule a too-slow auto-set speed, which would feel exactly
  like the controller "fighting" the driver even though EyeSight's own pedal-override is
  stock behavior with zero Phase 3 involvement), and `CS.cruise_button != 0` (a real
  physical press happening — same `no_real_press` gate tonight's test hook already used).
  Any of these firing must **latch the controller off for the rest of the onroad session** — not just skip one
  frame and silently resume the next, which would let a driver's deliberate brake-tap
  rejection get immediately re-applied by the controller a moment later. Re-enabling
  after a latch requires a fresh explicit arm (same discipline as tonight's flag-file
  arming), not automatic resumption on the next ignition cycle.
- **Where this sits in the code**: the override check must be the single first gate
  wrapping the *entire* "maybe send a command" block, structured as a simple early-return
  — not buried inside a longer boolean expression where a future edit could accidentally
  weaken it. Testable in isolation from the policy logic itself.

## 4. Watchdog / fail-safe design, and 5. integration point (tied together)

This project has been burned twice by process-crash-adjacent surprises: the `plannerd`
`UnknownKeyName` crash (`progress.md` §11) and the comma-manager restart quirk (killing a
process directly does not get it auto-relaunched — only a full reboot reliably does).
Given no `scons`/rebuild capability and no new `Params` keys (fixed compiled allowlist,
same landmine already documented in `es_distance_live_test_protocol.md`), the fail-safe
has to be simple, file-based, and not depend on any watchdog process actively detecting a
crash.

**Recommended architecture: split decision-making from execution, into two already-
existing processes, connected by a freshness-gated file — not a new Params key, not a new
IPC mechanism, not a new standalone daemon.**

- **Decision-making lives in `plannerd`** (specifically alongside `curve_advisory_helper.py`
  / `longitudinal_planner.py`, which already compute the exact target speed Phase 1 uses
  every frame). It reads `CS`/`CC` state, runs the policy in §1, and — instead of (or
  alongside) firing the advisory alert — writes its decision to a plain file, e.g.
  `/data/phase3_button_command` containing `<int value> <timestamp>`, once per decision
  cycle. Reuses Phase 1's existing target-speed computation directly; no new target logic
  duplicated.
- **Execution stays minimal, inside `carcontroller.py`'s existing PREGLOBAL button block**
  (the same block tonight's test hook lived in) — reads that file, and only overrides
  `cruise_button` if: the file exists, its timestamp is fresher than a small staleness
  bound (e.g. 500ms — comfortably tighter than the 1s command interval above), and the
  override-guarantee checks from §3 all pass. Otherwise, falls back to today's exact
  shipped behavior: pure relay of `CS.cruise_button`.

**Why this gives a fail-safe for free, without an explicit watchdog:** if the policy
process (`plannerd`) crashes, hangs, or gets stuck in a bad state, it simply stops
updating the command file. The file goes stale within one staleness window, and
`carcontroller.py` automatically reverts to plain relay — the exact behavior shipping
today, not a stuck or repeated stale command. `carcontroller.py`/`controlsd` itself never
has to know or care that the policy died; its own crash-blast-radius stays exactly what it
is today (a `carcontroller.py` crash is already catastrophic — total cruise loss, same as
§11 — but this design doesn't make that *worse*, and doesn't add new logic to the
highest-blast-radius file beyond a small, easily-audited file-read-and-gate block).

**Honest tradeoff**: `plannerd` crashing already means losing curve-advisory functionality
today (§11 precedent) — adding policy logic there doesn't change plannerd's own blast
radius, it just means Phase 3's automation goes down at the same time Phase 1's advisory
already would. That's an acceptable coupling given the alternative (a brand-new
standalone process) adds a whole new failure mode and onroad-launch entry to reason about
for comparatively little benefit — the file-staleness fail-safe works identically either
way.

## 3.5 Persistent master arm/disarm — a real gap, not yet designed (added 2026-07-24)

User's explicit ask this session: a way to control *when this whole feature is even
capable of firing*, not just the per-event driver-override latch in §3 above. Motivating
worry, verbatim: "dont want eyesight setting to 25 when im going 80 type shit." Checked
directly against the code as it exists today (2026-07-24): this specific scenario is not
currently possible — Phase 1's advisory only ever raises an alert event
(`EventNameSP.curveSpeedAdvisory`), it never writes to `vCruise`/CAN, and Phase 3 has zero
implementation (this doc only). But the underlying design gap is real: **neither Phase 1
nor this design has a persistent, deliberately-toggled "off until I turn it on" switch** —
§3's driver-override is a *reactive* per-session latch (something firing turns it off),
not a *proactive* gate (nothing turns it on unless the user says so first).

**Community precedent for this exact worry, found via Discord archive + web research
(2026-07-24):** a user in this project's own comma Discord export disabled both
sunnypilot's stock VTSC and MTSC toggles because the car was "aggressively slowing
down... trying to drop like 10mph" on a highway bend it could easily take —
same complaint shape as this project's stated worry. FrogPilot (a sunnypilot sibling
fork) separately added a "Map Turn Speed Controller Limiter" specifically because bad
OSM data caused unwanted brake slams on straight roads. Real prior art for wanting a
hard guard against unwanted automatic speed reduction, not a hypothetical concern.

**Correction (2026-07-24, later same day): layer 1 below is dead — do not build on it.**
The MAIN-button-to-MADS wiring this recommendation depended on was fully implemented,
live-tested, found unsafe (`Cruise_On` goes unstable for multi-second stretches under
real rapid button mashing, silently dropping presses — see
[[feedback-verify-signal-stability-under-realistic-conditions]]), fully reverted
(commit `c619a7b`), and the user explicitly shelved the whole idea afterward. That
mechanism does not exist on the device. **It turns out not to matter**: §3's existing
driver-override latch (`brakePressed`/`steeringPressed`/real button press → immediate
session-long lockout) already delivers the exact "fast in-drive kill switch" behavior
this section was trying to add — and it's built on signals already relied on elsewhere
in this project, not the path that just proved unstable under real mashing. Phase 3
needs only layer 2 below as a second, independent gate.

**Recommendation for when Phase 3 implementation actually starts — two layers, not one:**

1. ~~Fast in-drive kill switch: reuse the MAIN-button-driven MADS `enabled` state~~ —
   dead, see correction above. §3's override latch already covers this.
2. **Deliberate per-session arm, defaulting OFF, separate from MADS**: a dedicated param
   (e.g. `Phase3Armed`), checked as a second, independent gate before `plannerd` ever
   writes the command file, alongside MADS being enabled — not instead of it. Defaults to
   `False` on every boot; today that means it can only be set via an explicit SSH
   `Params().put_bool()` call before a session (mici's on-device Toggles screen doesn't
   route to custom settings pages at all — see `progress.md` line 15 — so a real
   dash-reachable toggle isn't available yet without separate UI work, out of scope for
   now). This is deliberately more friction than the button: the button is a fast
   *disable*, this is a slow, deliberate *enable* — asymmetric on purpose, so the feature
   can never be "accidentally on."

Both gates sit in the same "maybe send a command" early-return block described in §3 —
MADS-disabled and `Phase3Armed=False` are both immediate, unconditional refusals, checked
before the override logic, not folded into it.

## 6. Staged rollout — each stage needs its own explicit go/no-go, none auto-graduate

1. **Dry-run / shadow mode.** `plannerd` computes and logs intended commands (what it
   *would* send) without ever writing the command file `carcontroller.py` reads — the
   "send" step fully stubbed out. Zero CAN risk, zero effect on cruise state. Correlate
   logged decisions against a real drive's actual curve/speed context — do the decisions
   look sane (slows for curves at sensible lead distance, ramps back up smoothly after)?
   Matches this project's own founding principle (`progress.md` §1: "validate the decision
   before automating the actuation") — same discipline, one level deeper now that
   actuation itself is possible.
2. **First live enable — closed course, not a public road.** Empty parking lot or private
   road, low speed, single supervised session, conservative rate limit and session-command
   cap turned down further than defaults. Explicitly, deliberately test the override
   guarantee here — have the driver intentionally brake or press a real button mid-sequence
   and confirm the controller actually stops, not just assume the code is right because it
   compiled. This is the first time the override logic gets exercised against reality at
   all.
3. **Repeat stage 2 a few times** before ever touching a public road — build a track record,
   not a single lucky run.
4. **Supervised backroad use** — low-traffic, familiar route, driver fully attentive and
   ready to override throughout, same posture as tonight's live test.
5. **Broader use** — only after multiple clean stage-3/4 sessions.

Each transition needs the user's explicit sign-off, same pattern as every risk escalation
this project has already gone through (UDS test rounds, the parked recheck before
tonight's live TX test). No stage is assumed safe because the previous one went well.

## Open dependencies this design does not resolve

- ~~The nudge-vs-rebaseline question~~ — **CLOSED 2026-07-24 (Q10)**. Live 3-test drive
  (deep-SET, burst, RESUME) confirmed commanded presses nudge the existing target, they
  don't snap to current speed — the useful case this whole design assumed. See
  `progress.md` Q10 and `research/es_distance_live_test_protocol_v3.md`.
- RESUME (`4`) semantics, deep (`3`/`5`) magnitude, and sustained-press feasibility —
  being tested in parallel; §1/§2 above are written to be adjustable, not blocked, but
  are not yet grounded in confirmed data for those specific values.
- No consideration yet of *what* target-speed source is trustworthy enough to drive real
  actuation (Phase 1's curve advisory has real telemetry validation from actual drives,
  but was built as an advisory, not audited for actuation-grade reliability — worth a
  fresh look before Stage 1 above, not assumed carried over automatically).

## 7. Finalized v1 settings (locked 2026-07-24, brainstorm session)

| Setting | Value | Rationale |
|---|---|---|
| Decel-rate constant | **1.94 mph/s** (~0.87 m/s²) | User's own test: 60→25mph in 18s, flat backroad, spam-SET. Reverse-checked against the user's own 80mph projections — all three reproduce cleanly from this one constant, internally consistent. |
| Decel model shape | Single global constant, not speed/grade-bucketed | Matches v1 simplicity philosophy; only one real data point exists so far anyway. |
| Decel self-learn | Online EMA, live, post-launch only — **no archive-mining pass planned for v1** | User's explicit call: rough number is fine to start, "it'll only get better as we keep driving." Archive-mining shelved as a maybe-later idea, not scheduled. |
| Decel self-learn isolation filter | No lead tracked (`radarState.leadOne` absent) + `brakePressed` false, for the whole post-command decel window, before a real observed decel updates the EMA | Prevents lead-following or human-brake decel from contaminating the learned EyeSight-only rate. |
| Trigger distance | `distance_needed(v_current, v_target) × 1.25`, computed live per curve event, not fixed half/quarter-mile buckets | `distance_needed = avg_speed × (Δv / decel_rate)`. Fixed-bucket approach was checked against real numbers and found to actually fail (80→50mph needs 1,471ft, quarter-mile is only 1,320ft — a deficit, not just "tight"). |
| Insufficient lookahead | Auto-downgrade to the largest step-down that fits within available distance × margin | Never asks EyeSight to do something the geometry can't support; always physically achievable. |
| Ceiling (how high RESUME can walk the target back up) | Never exceeds the driver's own pre-existing cruise set-speed | Falls directly out of the use-case (lower for a curve, restore after) — no new dependency on speed-limit/map data. |
| Per-event command budget | Resets **per curve event** (on the same rising-edge "new curve" trigger Phase 1 already uses for its once-per-curve advisory debounce), not a flat whole-session cap | A flat 10-command whole-session cap was checked against real telemetry (5 curve detections in one real city drive, `progress.md` 2026-07-22) and found likely to exhaust itself by the second curve, going silently passive for the rest of the drive. |
| Master arm/disarm | Two gates, both required, both independent early-returns before any policy logic: (1) reactive — §3's existing brake/steer/button-press override latch, session-long, no silent re-arm; (2) proactive — `Phase3Armed` param, defaults `False` every boot, deliberate SSH-set only for now (no dash toggle yet) | §3.5's originally-proposed MADS-reuse layer is dead (reverted, shelved, see correction above) — these two gates don't depend on it and are both already sound. |
| Arming precondition | Cruise must be actively engaged (`CS.out.cruiseState.enabled`) or the controller is completely inert, not just quiet | User's explicit framing: "if I set cruise, and only if I do, then it should take over." |
| City-chatter suppression | Inherited for free from Phase 1's existing 35mph MTSC minimum-speed gate | Same gate that already kills roundabout/intersection chatter for the advisory alert — Phase 3 acting on the same trigger can't fire more often than the advisory already does today (~4-5x/drive empirically). |
| Alert during auto-actuation | Alert still fires, wording shifts from advisory to informational (e.g. "consider slowing" → "auto-adjusting for curve") | Driver keeps situational awareness even though no action is required — silently changing speed with zero indicator would erode trust. |
| Chained/back-to-back curve restore target | Always the one original pre-Phase-3-intervention set-speed, snapshotted once per arm-cycle — never an intermediate per-curve value | Simple single baseline, matches the ceiling rule exactly, no stacked-snapshot state needed even if curves chain before a full restore completes. |
| Override latch triggers | `brakePressed`, `steeringPressed`, `gasPressed` (added 2026-07-24), `cruise_button != 0` | Gas pedal was a real gap — EyeSight's own pedal override is stock/independent of Phase 3, but without this the controller could keep re-asserting a lower target underneath a driver flooring it, which would feel like fighting. |

## 7.5 Implementation verification catches (2026-07-24, overnight)

Curve-actuation implementation (`sunnypilot/selfdrive/controls/lib/phase3_curve_controller.py`,
commit `4e2adbf`) was independently re-read rather than trusted from the implementer's own
report — two real gaps against this doc's own locked requirements found and fixed
(commit `0d9708c`):
- **Shared budget bug**: fire-down and restore-up were drawing from the same
  `CURVE_EVENT_BUDGET` pool. A big curve could exhaust the budget walking the target
  down, leaving too little to walk back up — stranding the car below the driver's own
  set speed until the next curve happened to reset the counter. Fixed: restore-up now
  gets its own budget reset on the falling edge (curve clears), not shared with fire-down.
- **Missing absolute floor**: §3's "never command below EyeSight's own ~25mph ACC floor"
  hard bound wasn't implemented anywhere in the first pass. Added as `ABSOLUTE_FLOOR_MPH`,
  clamped in both the normal-target and downgrade-target paths.

**Second verification round (after lead-vehicle actuation was added, commit `a9401e8`),
also independently confirmed** — not just the implementing fork's own report:
- `MIN_COMMAND_INTERVAL_S = 1.0` (§2's own requirement) was **completely absent** from
  the first curve-controller pass — steps fired every ~50ms planner frame, not once a
  second. Harmless in shadow mode (nothing real ever sends), but would have been a real
  problem live. Now enforced via a shared constant in `phase3_shared.py`, used by both
  controllers.
- `CURVE_EVENT_BUDGET`/`LEAD_EPISODE_BUDGET` were both `10` — left over from an earlier
  *whole-session* cap discussion, never reconsidered for what a *single event's own
  delta* needs. Couldn't even cover this doc's own worked 60→40/80→50mph examples
  (20-30 steps). Raised to `60` for both.
- Independently re-verified via numeric regression (not just trusting the report): the
  `distance_needed_ft`/`largest_reachable_target_mph` closed-form pair reproduces the
  user's own 60→25/80→60/80→50 test figures exactly, and a round-trip check (feed the
  inverse function the forward function's own output) recovers the original target to
  the mph — including the downgrade case, where the recovered (smaller-drop) target's
  own distance requirement fits the available distance exactly, neither over nor under.

Known, not fixed tonight (real but non-blocking for shadow-mode validation):
`Phase3Armed` hits the same compiled-Params-allowlist landmine `CurveSpeedAdvisory`
already has on this prebuilt branch — reads always default to `False` until a real
reinstall registers the key natively. This only matters for an actual on-device
deployment (out of scope tonight anyway); the archive-replay validation pass instantiates
the controller directly and sets `.armed = True` in the harness, sidestepping the live
Params read entirely — this is not a blocker for tonight's validation, just a
pre-existing pattern to remember before any real Stage 2 attempt.

**Second verification pass, after lead-vehicle actuation was built on top (commit
`a9401e8`): two more real gaps found via an actual runtime test harness, not just
reading the code.** Stubbed only the native/capnp dependencies unavailable in this
sandbox (`Params`, `cereal`, `openpilot.common.realtime`) and let the real business logic
run unmocked — found:
- **No `MIN_COMMAND_INTERVAL_S` gate existed anywhere.** §2 of this doc locks it at
  1.0s, but the first implementation pass never actually enforced it — a 30-frame test
  loop produced 10 fires in the first 10 frames (500ms), not spread across ~10 real
  seconds. Harmless in shadow mode (nothing is ever actually sent), but would have been a
  real problem the moment this logic was ever pointed at a live send path. Fixed: added
  as a shared constant in `phase3_shared.py`, enforced in both controllers'
  `_step_toward`.
- **`CURVE_EVENT_BUDGET`/`LEAD_EPISODE_BUDGET` were both 10, and neither could actually
  reach this doc's own worked examples.** A 60→40mph curve target needs 20 one-mph
  steps; 80→50mph needs 30. Both exceed a budget of 10 — the "10" was carried over from
  an earlier *whole-session* cap discussion (§7's own city-driving conversation) without
  being reconsidered for what a *single event's own delta* needs, a different question
  entirely. Confirmed via the test harness: a synthetic 60→40mph curve test converged
  correctly once raised to 60, and failed (stalled at 50mph, 10 steps short) at the
  original value. Fixed: both raised to 60 — still a finite defensive backstop, just
  sized to cover realistic worst-case single-event deltas (e.g. 80mph down to the 25mph
  floor) instead of silently truncating exactly the largest, most safety-relevant
  adjustments.

Test harness confirmed correct (not just "doesn't crash"): shared-latch propagation
(brake tap on one controller immediately latches the other, same frame, either call
order), curve fire-down + restore-to-baseline with the separated budgets, and lead
trigger/target/restore all converge to within each feature's own designed tolerance.

## 9. Lead-vehicle actuation (reopened 2026-07-24) — extends the original "Phase 1.5" advisory

**Correction (2026-07-24, overnight research pass): everything below the trigger/target
design was reinvented from scratch and shouldn't have been — a code-precedent research
pass found this work already exists, already shipped, already further along than assumed
when this section was first written earlier tonight.** Two files, both already committed
to this branch:

- `sunnypilot/selfdrive/controls/lib/lead_closing_advisory_helper.py` (commit `c4db590`,
  shipped, on by default) — real tuned trigger: `CLOSING_VREL_THRESHOLD = -3.0 m/s`,
  `SUSTAIN_TIME = 0.5s`, `NO_RECENT_PEDAL_TIME = 3.0s`, `DEBOUNCE_TIME = 20s`,
  `MIN_ADVISORY_SPEED = 50mph`.
- `sunnypilot/selfdrive/controls/lib/lead_closing_test_guidance_helper.py` (commit
  `7d20543`, opt-in, off by default) — built explicitly "before spending money/effort on
  a physical button-press microcontroller... so the driver can execute it manually and
  judge... before ever building an actuator to do it for real." Already has a target
  formula: `v_target = lead.vLeadK + TARGET_MARGIN(4mph)`, `CONVERGED_TOLERANCE = 2mph`,
  `REPEAT_INTERVAL = 5s`.

**This supersedes the TTC/aEgo-based trigger and unpinned target originally drafted
below — don't implement that design, adapt these existing, already-integrated ones
instead.** Same reasoning that's already governed every other piece of this project:
reuse Phase 1's existing computation rather than duplicating logic (curve actuation
already does this with MTSC's `output_v_target`/`distance`; this is the same move for
the lead-vehicle side). The TTC grounding research (`research/ttc_threshold_grounding.md`)
isn't wasted — it's a useful independent cross-check that `vRel < -3.0 m/s` sustained
0.5s is roughly the same sensitivity class as a 5s-TTC/2s-headway gate at typical
closing speeds, just a second, still-worthwhile validation, not the primary design.

**What's still genuinely open, and still needs tonight's backtest**:
`research/lead_vehicle_warning_analysis.md` line 96 explicitly flags that the
`-3.0 m/s` / `50mph` thresholds were the *candidate definition* used to find the 63
episodes in the first place, not independently validated against a false-positive rate
— "good enough to validate the core premise... not enough to claim the exact thresholds
are optimal... real-world tuning after building should be expected." **Nobody has
actually computed the confusion matrix** (does `sustained`+`no_recent_pedal`+`debounce`
correctly separate the 14 real brake-needed episodes from the 49 benign ones, or does it
false-fire on a meaningful chunk of the 49?) — that's the real remaining gap, not the
threshold values themselves. Also still open: the guidance tool (`LeadClosingTestGuidance`)
has only been confirmed process-healthy on-device, never actually driven with a human
following its prompts — so its target formula is grounded in the same research as the
advisory trigger, but not yet field-validated the way curves got three live confirmation
rounds.

**Revised plan for tonight**: backtest the *existing* trigger+target logic above against
the 63 archived episodes (not a fresh TTC design), then wrap it in Phase 3's
button-spoofing mechanism (shared override latch, shared arm-gate pattern, shared
shadow-mode logging — same infrastructure as curve actuation, `Phase3LeadArmed` as the
separate gate already decided) instead of firing an alert/guidance event.

**Backtest result (2026-07-24, overnight): build on the existing trigger+target as-is,
no threshold changes.** Full writeup: `research/lead_closing_trigger_backtest.md`.
Headline findings:
- **Precision, not a full confusion matrix**: the shipped trigger's constants are
  identical to the candidate definition used to build the 63-episode dataset in the
  first place, so "trigger fires" and "episode exists" are the same 63 by construction.
  That makes this a precision question: **14/63 = 22%** of episodes where the trigger
  fires actually needed real braking. **Recall (false-negative rate — real brake-needed
  situations the trigger would miss entirely) is genuinely unresolved** — would require
  re-mining the full archive for the broader non-triggering population, correctly
  flagged as out of scope for tonight rather than glossed over. Worth remembering this
  characterizes "of the times it fires, how often was it warranted," not "how often does
  it catch every real case."
- No single feature (vRel, dRel, vEgo, or TTC at first detection) separates the 14
  brake-needed episodes from the 49 benign ones — generalizes the earlier "TTC alone
  doesn't discriminate" finding to every feature checked. No simple threshold tweak would
  raise precision; this isn't a tuning problem, it's inherent to what's observable at
  detection time.
- Target formula sanity check (no per-episode time-series available, so this is a
  point-estimate, not a full stability check): across all 14 brake episodes, computed
  target vs. current speed gap ranged 2.8-13.1mph, always positive/actionable, never
  degenerate. Three episodes with the steepest closing rates show notably larger gaps —
  flagged as natural v1.1 deep-step candidates, not a v1 blocker.
- **Why 22% precision is acceptable here despite being a low number for a hard alarm**:
  this is a shallow, reversible nudge riding the same override-latch/restore machinery
  as curve actuation, not a one-shot alarm a driver has to react to. The bar for "good
  enough to softly actuate" is lower than "good enough to alarm on," and this clears it.

---

*(Original TTC/aEgo-based draft below, superseded by the above — kept for the record,
not the implementation target.)*

**This was the project's original acceptance criterion, not a new idea.** `progress.md`
§1's founding "accept when" line: "the lead car braking, EyeSight has no lock' highway
case is handled without manual intervention, repeatably and predictably." The
2026-07-23 decision to make this advisory-only (`research/lead_vehicle_warning_analysis.md`)
was scoped that way specifically because no actuation mechanism existed yet — Q10 closing
removes that constraint. Same underlying primitive as curve actuation (SET/RESUME nudges
the existing target), different trigger source and — importantly — a **continuous, not
discrete**, condition: a lead car can persist for an entire highway drive, where a curve
is a one-shot bounded event. That's a materially different risk shape even though shadow
mode keeps tonight's actual CAN risk at zero either way — hence the separate arm switch
locked below.

**Concrete daily scenario this is built for (user's own words, 2026-07-24):** "going 80,
no cars in front so EyeSight has no lock, then car in front starts slowing down, EyeSight
doesn't pick the car up till it gets a little too close, and before then I always have to
intervene and brake — lead distance always picked that car up way before EyeSight catches
a lock (if I even let it)." Important sharpening: the failure mode this trigger targets
isn't "EyeSight reacts slowly to a lock it already has" — it's that **EyeSight frequently
has no lock at all** for the entire window where openpilot's own vision (`radarState.leadOne`)
already sees the car, which is exactly why the trigger below is built on openpilot's own
independent vision tracking rather than anything from EyeSight's internal lock/lead state
(not observable to openpilot on this platform anyway) — it doesn't need EyeSight to see
the car, only that openpilot does and `aEgo` isn't dropping yet.

**Trigger — threshold, not continuous** (locked 2026-07-24). The archive data already
shows EyeSight's own ACC handles most lead-following fine unassisted (27 of 41 historical
episodes needed zero driver input, `lead_vehicle_warning_analysis.md`). A continuous
target-matching controller would mean constantly overriding EyeSight's own following
logic, not backstopping it. Instead, only intervene when a signal suggests **EyeSight
hasn't started reacting yet** despite a closing lead — the actual "brakes too late"
complaint, not "is a lead present."

- `radarState.leadOne` present, `vRel < 0` (closing)
- `TTC = dRel / -vRel` drops below **5.0s** (pinned 2026-07-24, overnight research pass —
  see `research/ttc_threshold_grounding.md`) — two independent real-world anchors agree
  on this number: NHTSA's own heavy-vehicle FCW test-track protocol uses a 5.0s TTC
  threshold, and openpilot's own existing FCW logic
  (`selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`, `FCW_IDXS = T_IDXS < 5.0`)
  independently uses the same 5-second horizon. Secondary/backup check: time-headway
  (`dRel / v_ego`) < ~2.0s, from the same pass's literature review (1.2-2.0s is the
  established safe/efficient following range, <0.5s is flagged critical). Honesty check
  carried over from the research: no literature combines a raw TTC/headway threshold
  with an "ego not yet decelerating" compound check the way this design does — that
  compound signal is a project-specific adaptation (this platform can't observe
  EyeSight's own braking state directly), not itself a validated pattern. The archive
  backtest below is what actually validates or corrects it — the literature grounding
  just replaces a guessed number with two independently-sourced ones for the TTC/headway
  piece specifically. Original finding this all still respects: raw TTC-at-detection
  alone doesn't cleanly separate the 14 real brake-needed episodes from the 49 that
  resolved on their own (overlapping medians, 27.2s/21.9s/23.7s across groups) — so TTC
  alone is not the whole signal, which is exactly why the compound check below matters.
- **Combined with**: `CS.out.aEgo` not yet meaningfully negative (EyeSight isn't
  decelerating despite the closing lead) sustained over ~1-2s, not a single noisy frame.
  This compound signal (closing + EyeSight-not-yet-reacting) is the actual hypothesis to
  validate — not assumed correct. **This is exactly what tonight's archive backtest is
  for**: replay this trigger logic against the same 63 historical closing-lead episodes
  already characterized in `lead_vehicle_warning_analysis.md` / `lead_warning_raw_results.json`
  and check whether it fires on the 14 that needed real braking without lighting up on
  the 49 that resolved on their own. Report the confusion-matrix-style result, don't just
  assert the trigger is right.

**Target**: shallow SET steps (same primitive/step size as curves) while the trigger
condition holds, same `MIN_COMMAND_INTERVAL_S`/deadband as §1/§2. Stop decrementing once
the closing condition clears (TTC/gap reopens past a hysteresis threshold — must differ
from the trigger threshold, or the controller will chatter on/off right at the boundary).

**Restore**: RESUME back toward the one pre-Phase-3 session baseline (same semantics as
the chained-curve decision above) once the lead either clears (`radarState.leadOne`
no longer present) or the gap/TTC reopens past the hysteresis threshold — this is the
"episode end" signal, playing the same role a curve's `turning`-state-clears edge does.

**Budget — per-episode, plus a rolling backstop** (episode = a fresh rising edge of the
trigger condition, same per-event pattern as curves' budget). Unlike curves, lead-following
episodes can plausibly recur many times in one drive (dense traffic), so add a rolling
window cap (e.g. max N commands per 5-minute window) as a backstop independent of the
per-episode reset, specifically because this feature's continuous-recurrence risk is real
in a way curves' isn't — a policy bug here has a much larger blast radius across one drive
than the curve case does.

**Arm gate**: separate `Phase3LeadArmed` param (locked 2026-07-24), independent of curve
actuation's arm switch — same defaults-off, deliberate-SSH-set-only pattern as §3.5.
Lets curve actuation get trusted and used on its own before lead-actuation is ever turned
on, given the latter is newer and less validated (three confirmed live test rounds for
curve-button semantics vs. zero live validation yet for this trigger).

## 8. Overnight autonomous execution scope (planned 2026-07-24, not yet started)

**Hard boundary, non-negotiable for any unattended run:** stays entirely within **Stage 1
(dry-run/shadow mode)** from §6. The "send" step — ever writing
`/data/phase3_button_command` — is fully stubbed out for the whole run, regardless of
whether the device happens to be reachable/parked overnight. Per `claude.md` ("never TX
on CAN without explicit confirmation") and the fresh MAIN-button-MADS incident (clean
recon looked fine, real-world mashing broke it, forced a live revert with the user in the
car) — shadow-mode-first isn't extra caution for its own sake here, it's the exact lesson
that incident just reinforced. Stage 2+ (any live-enable, even closed-course) always
needs the user physically present and an explicit go-ahead — never something this run
does on its own, no matter how clean shadow-mode results look.

**Further tightened (2026-07-24, mid-run): `carcontroller.py` gets zero changes tonight,
not even the read-and-gate hook.** Even with the command file never written, having the
hook's code exist in the most safety-critical file in the stack differs from what's live
today for no real benefit during a shadow-only run — it's only worth adding once it's
about to be reviewed immediately before an actual Stage 2 attempt. Tonight's changes are
scoped entirely to `plannerd` (decision computation + logging to a distinct shadow-log
path, never the real command file path) — a stronger, simpler guarantee than "wrote the
hook but the file happens to be absent."

**Also added (2026-07-24, same night):** the run now covers §9 (lead-vehicle actuation)
alongside curve actuation — same shadow-mode boundary applies equally to both, since
shadow mode carries zero CAN risk regardless of feature complexity. **`git push` and any device deployment wait for explicit morning sign-off** — tonight's
run implements and validates entirely against the local repo and the already-archived
rlog data (`<local-rlog-pipeline>`, no device reachability needed), committing locally
as it goes (normal repo convention, one commit per logical change) so there's something
concrete ready to review and push in the morning — but the `git push` itself, and any
device deploy, do not happen tonight. User's own words: "I wake up, check the results,
and give you permission to go for the push."

Task list for the run itself:

1. Implement curve-actuation decision logic (trigger-distance formula, deadband,
   per-curve-event budget, decel EMA, ceiling, alert-wording change, chained-restore
   semantics, all four override-latch signals including the new `gasPressed`, both
   arm gates) in `plannerd`/`curve_advisory_helper.py`, reusing Phase 1's existing
   target-speed computation rather than duplicating it.
2. Implement the decel-rate EMA state file, seeded at 1.94 mph/s, update gated by the
   isolation filter (no lead, no brake-press) described in §7.
3. Design and implement lead-vehicle actuation per §9: the compound trigger
   (closing + EyeSight-not-yet-reacting), shallow-SET target logic, hysteresis-gated
   restore, per-episode + rolling-window budget, separate `Phase3LeadArmed` gate.
4. **Backtest the §9 trigger against the archive first, before trusting it in the
   logging pass**: replay it over the same 63 historical closing-lead episodes from
   `lead_warning_raw_results.json` / `lead_vehicle_warning_analysis.md`, report how many
   of the 14 real brake-needed episodes it catches and how many of the 49 benign ones it
   false-triggers on. If the false-trigger rate looks bad, say so plainly rather than
   shipping the logging pass on an unvalidated trigger.
5. Implement shadow-mode logging for both features: structured log line per decision
   cycle (timestamp, trigger type, `v_current`, `v_target`, computed distance/TTC,
   decision taken, budget remaining) — the actual command file is never written, for
   either feature, this entire run.
6. Validate both features by replaying against archived segments (no live drive or
   device reachability needed) — do the logged decisions look sane (curves: sensible
   lead distance, respects budget; lead-vehicle: fires on real brake-needed episodes,
   stays quiet on benign ones)?
7. Write up results (§9's backtest numbers especially) for morning review. Do not
   commit, push, or auto-graduate to Stage 2 under any circumstance — that's explicitly
   gated on the user's morning go-ahead.
8. Update `progress.md` (§5 phase status, Open Questions, changelog) per this project's
   standing discipline, but leave it uncommitted alongside the code changes — one
   review pass, one push decision, in the morning.
