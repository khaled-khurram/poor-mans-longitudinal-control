# Live tests v3: RESUME, deep SET/RESUME, and sustained-command capability

**Status: DRAFTED, NOT DEPLOYED, NOT RUN.** Phase 3 territory, same as v2 — needs
explicit go-ahead per `claude.md` before any of this touches the device.

Builds on the confirmed result in `research/es_distance_live_test_protocol.md` (v2's
"RESULT" section): a software-commanded `cruise_button=2` (SET shallow), sent once while
cruise was available-but-not-engaged at 28mph, made the real ECU engage cruise at that
exact speed within ~100ms. That confirms one specific case. It does **not** confirm
RESUME, it does **not** confirm the shallow/deep distinction, and it says nothing about
whether repeated commands are safe — those are the three gaps this round closes.

Patch: `research/es_distance_button_test_v3.patch` (validated against a clean checkout of
`opendbc_repo/opendbc/car/subaru/carcontroller.py` at commit `2ba5623` — `git apply
--check` passes). Not applied to the working tree; not deployed.

## Why three separate flags, and why still one test per drive

Each test is armed independently (`/data/es_distance_test_resume`,
`..._test_deep`, `..._test_burst`) so a single patch/deploy cycle can serve all three
without redeploying between them. But **still run only one per drive** — arming more than
one simultaneously is actively refused in code (all three disable themselves and log a
warning if more than one flag is present), not just discouraged in the doc. Two reasons:

1. **The RESUME test's precondition depends on cruise having been engaged by a *real*
   press**, not a commanded one (see below). If the deep or burst test's own commanded SET
   fired earlier in the same drive, that would satisfy RESUME's "was really engaged" latch
   for the wrong reason, contaminating the result.
2. Cleanly attributing a result to one variable at a time is the same discipline that made
   tonight's result trustworthy (isolated commanded frame, no concurrent real press) —
   compounding three untested behaviors into one drive makes any anomaly hard to attribute.

## Test 1: RESUME (`cruise_button=4`)

**The precondition is the interesting design problem here, not the button value.** Real
Subaru RESUME semantics differ fundamentally from SET: SET captures the *current* speed as
a new target; RESUME recalls a *previously stored* target. Tonight's v2 test engaged from
a **never-engaged** state, which has no bearing on whether a stored-target recall works.
Naively copying v2's gate (`available and not enabled`) would let this fire before cruise
was ever engaged at all — testing nothing meaningful, since there'd be no stored speed to
resume to.

**Design chosen: piggyback on the driver's own real engagement, don't synthesize one.**
The hook latches `es_distance_resume_was_engaged = True` the first time it observes
`CS.out.cruiseState.enabled == True` while armed — and that can only happen from a **real**
button press this drive, since nothing in this test commands anything before firing. Once
latched, the test arms itself to fire only when: cruise is currently available-but-not-
engaged (a real disengage happened — brake tap, cancel, etc.), the car is still moving
(`vEgo > 11mph`, well above a stop, so this reads as a genuine "ACC paused mid-drive" state
rather than parked), sustained 2s, no concurrent real press.

**What this means for the driver:** no special action beyond normal driving — engage
cruise for real at some point during the armed window (tap SET/RES like normal), then let
it get disengaged normally (brake tap). If that sequence never happens before the 30-minute
arm window expires, the test simply never fires — same safe no-op as any other unmet gate.

**Considered and rejected:** using the code's own `pcm_cancel_cmd` path (`cruise_button=1`,
which is the `main` toggle) to synthesize a disengage after a v2-style commanded SET, all
within the same drive with no driver action needed. Rejected because that chains two
untested assumptions — does a *software-commanded* main-toggle preserve a resume buffer
the same way a driver's real brake-tap disengage does? — into one test, instead of testing
one new thing at a time. If RESUME's first real-engagement-based test works, that
synthesized version becomes a reasonable *second* test to consider, not a substitute for
this one.

## Test 2: deep SET while already engaged (`cruise_button=3`)

**Also a precondition correction, not just "the deep variant of tonight's test."** On a
real Subaru, when cruise is *not* engaged, SET (shallow or deep) just captures current
speed — tonight's result doesn't distinguish shallow from deep because there'd have been
nothing to decrement from. Shallow vs. deep only becomes observable once cruise is already
engaged with a real, known set-speed, and a SET press *adjusts* that speed (shallow ≈
-1mph, deep ≈ -5mph, matching this project's own earlier documented rocker behavior).

**Gate:** `cruiseState.enabled == True` (real engagement, same requirement as RESUME —
this test also can't fire from our own commanded SET, since deep and resume flags are
mutually exclusive with each other per-drive) **and** steady-state (`|vEgo -
cruiseState.speed| < 1 m/s` for 3s, not mid-transition) **and** no concurrent real press.
Fires `cruise_button=3` once. Measures: `cruiseState.speed` immediately before vs. a couple
seconds after — the delta is the answer, no ambiguity needed from archive correlation.

**Direction chosen deliberately: decrease (SET), not increase (RESUME-deep/`5`).** Same
reasoning as v2 — smallest, most reversible effect, especially for the first-ever "adjust
an existing engaged set-speed" test. A symmetric deep-RESUME (`5`) test is a reasonable
follow-up once this one's confirmed, not bundled into this round.

## Test 3: sustained/rapid burst (3× `cruise_button=2`, ~250ms apart)

**What it answers:** can the ECU accept several commanded presses close together —
matching real "spam" cadence (this project's own Q1-3 finding: spam beats hold for real
ramp speed; a firm real press sometimes double-pulses ~0.4s apart) — without faulting or
breaking the counter/checksum continuity? This is the one that actually determines whether
a real closed-loop controller is feasible with this message at all, since a controller
needs to send many commands over a drive, not a single isolated one.

**Gate:** same as the deep test (engaged, steady-state, 2s) before the *first* press.
**Between presses:** each subsequent press requires ~250ms elapsed (5 cycles at this
block's 20Hz cadence) **and** steady-state/no-real-press re-checked at send time — this
isn't "commit to 3 sends no matter what," it's "send up to 3, abort immediately if
conditions change mid-sequence." An abort mid-burst is logged distinctly from a completed
burst, so a partial result (e.g. 1 or 2 presses sent, then aborted) is visible and
interpretable, not silently indistinguishable from a clean 3-press run.

**Direction: decrease only** (`2`, shallow SET), same reversibility reasoning, bounded to
~3mph total even in the best case.

## Run sequence (applies to whichever one test is armed)

1. Deploy the relevant flag's code path (same patch serves all three), `git pull` +
   reboot, confirm process health — identical discipline to v2.
2. On WiFi, before leaving: confirm current cruise state matches the test's precondition
   as best as can be checked from the driveway (e.g. for the deep/burst tests, no real
   check possible until actually engaged and driving — that's fine, the gate handles it
   live). `touch` the one flag file for the test being run.
3. Drive normally — for RESUME, this means: engage cruise for real at some point, then let
   it disengage normally (brake tap) while still moving. For deep/burst: get cruise engaged
   and hold a steady speed for a few seconds at some point.
4. No SSH/live interaction needed or possible mid-drive, same constraint as v2 (no
   Tailscale yet).
5. After the drive, pull `/data/es_distance_button_test_v3.log` and cross-reference against
   the synced route the same way v2's result was verified — timestamp-match the FIRED (or
   ABORTED) line(s) against real `cruiseState`/`ES_DashStatus` telemetry in that window.
6. Revert immediately after, same as v2 (`git revert`, redeploy, reboot, confirm HEAD +
   process health) — don't leave any of this running past the single drive it's meant for.

## Honest gaps this round still won't close

- Deep-RESUME (`5`) isn't tested — only deep-SET (`3`), for the reversibility reason above.
- The burst test caps at 3 presses, ~250ms apart — doesn't establish behavior at higher
  rates, longer bursts, or truly continuous/indefinite command streams, which is what an
  actual closed-loop controller would eventually need. It's a first data point on
  feasibility, not a full characterization.
- None of these tests say anything about *deciding* when to send a command (the actual
  control-policy question) — they're all still testing whether the ECU listens, under
  various conditions, not testing any decision logic.
