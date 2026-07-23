# UI improvement ideas — Discord research (2026-07-23)

Sources: `openpilot-ui` channel (158KB/4,116 lines, searched in full) and `custom-forks`
channel (11.5MB, targeted search) from the Discord archive. This project's onroad UI:
raylib/Python, `MiciMainLayout`, zero Qt, small comma-4 screen — the c4/mici form factor
comes up repeatedly in the source threads as its own distinct design constraint, so
"works on tici/Qt" advice doesn't always transfer.

No code changes made. Ideas below are ranked by how directly they apply to this
project, not chronologically.

---

## 1. Speed-limit widget: real precedent for exactly the bug this project already hit

**This project's own history:** the first speed-limit display attempt was too big and
covered the alert-warning text — a real z-order bug, fixed, then the whole feature was
removed anyway because the user didn't like the sizing/position even after the fix.

**Direct precedent found — FrogPilot's "Speed Limit Controller" redesign** (custom-forks
channel, changelog post): explicitly fixes the *same class of problem*. Quote:

> "The 'Confirm New Speed Limits' widget no longer displays as large red/green boxes
> that cover the entire screen. Instead, it now utilizes a new speed limit to the right
> of the active one with the title 'Pending Limit'..."

The pattern: a small side-by-side number next to the existing speed display, not a
full-screen or large overlay element. This is a concrete, already-shipped-elsewhere
counter-example to what this project tried and reverted. If speed-limit display gets
revisited, "small number next to the existing speed readout" is a validated direction,
not a guess.

**Separate, real user complaint (openpilot-ui, `tpnxl`, cross-posted from the
Sunnypilot server):**

> "My C3X is mounted really high on my windshield... I can't see the OP speed
> limit/setting display from my normal driving position... It would be great if the
> speed limit/setting display position could be swapped with the driver monitor
> indicator which serves basically no purpose as long as the system is functioning
> properly. This function should probably be on a toggle..."

Nobody in the thread pushed back on this — no confirmed resolution either, it's a
raised idea, not a shipped fix. Relevant here mainly as a second data point: positioning
matters as much as size, and "high-value info competing for space with a low-value
persistent icon" is a recurring complaint.

**Assessment:** Low-to-moderate integration complexity for this codebase specifically —
this project already has a working `speed_limit.py` widget and already found/fixed the
z-order issue once. Re-adding it sized/positioned like FrogPilot's "Pending Limit"
approach (small, adjacent to existing elements, not a takeover) is a bounded, mockup-able
change, not a rebuild.

---

## 2. FrogPilot's curve-speed widget — directly relevant to this project's own curve advisory

Same changelog post as above, "Curve Speed Control" redesign:

> "...instead of just changing the color of the box around the 'MAX' speed... there is
> now a dedicated widget! When a curve is detected... you'll see a left/right curve
> indicator... with two speed values below it showing the calculated speeds from both
> methods. If the top box is larger and highlighted green, the 'Map Based' method is
> active, if the bottom box is larger and highlighted red, the 'Vision' based method is
> active."

This solves a UI problem this project doesn't currently have visually surfaced at all:
showing *which source* (map vs. vision) is driving the current advisory, with a clean
size/color convention for "which one's active" rather than just picking one silently.
Given this project now has two independent advisory triggers feeding the same alert
pipeline (curve + the new lead-closing one), a similar "which source fired this" visual
convention could be worth borrowing if these ever get a persistent (not just transient
banner) UI treatment.

**Assessment:** Real, working precedent (this is a live FrogPilot feature per the
changelog, not a proposal) but FrogPilot's UI framework (their own Qt-based fork,
unconfirmed here) may differ enough from this project's raylib/mici stack that this is
a design-pattern reference, not a portable component. Worth citing as "here's how someone
solved multi-source-attribution cleanly," not as code to copy.

---

## 3. Steering-wheel icon: repeated community consensus it's wasted space on the c4/mici screen

Real, multi-person thread (openpilot-ui, March 2026), several independent people agreeing:

> `sirmaster`: "Does anyone actually like the steering wheel icon on the current ui?
> Like it's so small does anyone even look at it and can tell what angle it is?"
>
> `discountchubbs`: "I forget it's there tbh. If it doubled as experimental indicator it
> would be neat, but it's too small to see it's turning and the torque bar shows that
> anyways"
>
> `sirmaster`: "every pixel is valuable realestate on the c4, i think it should be
> replaced"

Multiple people independently suggested repurposing that space for an
**experimental/chill-mode-active indicator** instead — genuinely converged opinion, not
one person's take. A comma team member (`subzeroalphaq`) confirmed an
"experimental mode indicator onroad is coming soon" from comma itself, separately.

**Assessment:** Not directly actionable for this project (this project doesn't currently
touch the steering-wheel icon or experimental-mode UI), but useful as a general
principle specific to this exact hardware: **on the c4/mici screen, small persistent
icons that don't convey real-time information are considered wasted space by this
community.** Worth keeping in mind before adding any new small persistent icon rather
than a transient alert (which is the pattern this project's two new advisories already
correctly use).

---

## 4. Lead-vehicle path/distance visualization — one suggestion, unconfirmed/unbuilt

`darshan12433` (openpilot-ui, replying to someone else's UI showcase):

> "For lead car indicator can you just highlight two or three same arrow in different
> color that shows drive path. I believe that will makes your UI super clean"

**Assessment:** A single person's suggestion in reply to someone else's redesign, not a
built or validated feature anywhere in the search. Flagging as speculative only — don't
treat as precedent. Relevant context though: this project's own new lead-closing
advisory doesn't currently have any visual (non-alert-banner) representation of the
tracked lead at all — if that ever becomes wanted, this is at least one aesthetic
direction someone independently proposed, nothing more.

---

## 5. Turn-by-turn arrow overlay — real attempt, flagged as too small on-device

`sshane_` posted a video of "some onroad ui experimentation" (turn arrows), then
immediately self-flagged:

> "arrows probably too small to look good on device though"

**Assessment:** A genuine integration pitfall data point, self-reported by the person
who built it, not secondhand — small graphical elements that read fine in a mockup/video
can be illegible on the actual small device screen. Directly relevant if this project
ever adds any new small-scale visual (icon, arrow, indicator) rather than a
banner-style alert — the two advisories built this session both deliberately reuse the
existing large alert-banner text size specifically to avoid this exact trap.

---

## 6. Larger "info-dense redesign" concept threads — interesting but explicitly unbuilt/philosophical

`larsa0` posted a full PDF redesign concept (openpilot-ui, March 2026) explicitly built
"with Sunnypilot in mind" (mentions SLM/speed-limit-maps and SCC-M/smart-cruise-map by
name — same features this project uses). Got substantial community discussion, but:

- A comma-adjacent community member (`subzeroalphaq`) called it "generally quite solid"
  but explicitly said current stock UI isn't heading this direction yet ("the underlying
  technology as well as the culture/community is not ready yet") and suggested it's
  realistic as a **custom branch**, not something to expect upstream.
- No indication anyone actually built/shipped this — it stayed a concept/PDF + community
  discussion thread.
- One concrete piece of reusable value: comma's actual icon assets are public —
  `github.com/commaai/openpilot/tree/master/selfdrive/assets/icons_mici` — confirmed
  by the same community member, useful if any new icon-based element gets built later.

**Assessment:** Interesting direction-setting reading, not an actionable feature to
adopt. Flagging mainly because it's the most sunnypilot-specific concept found and
because the underlying philosophy ("expert users don't need the camera feed/lanelines
once they trust the model") could matter later, but nothing here is ready to build.

---

## Not found

No z-order/layering bug reports specific to *other* people's mici/c4 UI work were found
— the z-order class of bug this project hit (HUD drawing over alert banners) doesn't
appear to have a documented precedent elsewhere in these two channels; it may be
somewhat specific to how this project's `MiciMainLayout` composes its render order
rather than a widely-known community gotcha. No mici-specific integration pitfalls
beyond what's captured above (sizing on the small screen, generally) — searched
explicitly for "mici" (3 hits total, none substantive beyond icon-asset links and one
unrelated tizi-porting post).

## Suggested next step, if picking one

Of everything above, **#1 (speed-limit widget, FrogPilot's small-side-by-side "Pending
Limit" pattern)** is the most directly actionable: this project already has the
underlying data/toggle wired up, already tried and reverted a version of this exact
feature, and now has a concrete, real, working alternative layout to mock up against
instead of guessing at sizing again from scratch.
