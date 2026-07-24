# Discord precedent for lead-vehicle actuation + CAN command pacing (2026-07-24)

## 1. TTC/closing-rate intervention precedent

**This project's exact question was asked independently in the community 8 days before
tonight.** `subaru` channel, 7/16/2026:

> `flyingchair235`: "Anyone tried spoofing ACC buttons to auto-adjust speed alongside
> eyesight? Tired of it braking too late on the highway or it not being able to handle
> curves. (Pre-global)"
> `5pacecaptain`: "Yeah the braking too late is a real thing"

Real, independent confirmation this is a shared pain point, not an individual quirk —
strengthens the case for building it, but also means there's no positive prior art to
learn from (see below).

Response pointed to sunnypilot's own ICBM forum thread
(`community.sunnypilot.ai/t/enabling-icbm-on-17-impreza/191/4`), same mechanism this
project already uses ("we 'trick' the car into thinking the driver is pressing these
buttons by sending the same signals via CAN"). Truncates right at a Subaru-specific
caveat — 403 on direct fetch, no MCP tool available for this domain. **Worth fetching
manually if there's browser access; not retrievable from this pass.**

Community sentiment on ICBM-for-Subaru is uniformly pessimistic, matching this
project's own earlier finding ("ICBM unimplemented for all Subaru platforms"):

> `amusedgrape`: "seems like it's never really been explored or can't be done"
> `furiouslyred`: "I don't even think the ICBM even works"
> `mostlyclueless1994`: "the button is shared between the mads toggle and turning on and
> off stock LKAS. Couldn't turn off stock altogether without issues" — direct echo of
> tonight's own MADS-button conflict (already found and reverted independently).

**No TTC-threshold or closed-loop control design discussion found anywhere in the
corpus** — people have asked if this is possible, nobody's documented actually building
the closed-loop part. This project is ahead of what's publicly documented, which cuts
both ways: no prior art to lean on, but also nothing contradicting the approach.

One unresolved tangent from a different platform (Kia Optima, `custom-forks`,
3/27/2026, `elithecoder`): "what happens when you press the +/- buttons while ICBM is
active — does it change cruise set speed, or does sunnypilot intercept it?" — never
answered in-thread. Not directly applicable to Subaru's mechanism, but a reminder this
exact override-interaction question is generally unresolved territory, not just here.

## 2. CAN command-pacing/debounce wisdom

No hits on anything matching tonight's specific `Cruise_On`-instability failure mode
(MADS revert) — that appears to be a genuinely novel finding from this project's own
live testing, not documented elsewhere.

Real, independent precedent that command **cadence** matters mechanically, corroborating
the already-conservative 1s `MIN_COMMAND_INTERVAL_S`:

> subaru channel: a user rigging a "turbo button" to auto-spam resume: "spamming the
> resume button too quickly will increase your set speed" — unwanted overshoot from fast
> repeated presses, independently corroborated by a second mention of "the same
> increase-speed issue... when spamming the button."
> A third user reports manually spamming resume "every 3 seconds in traffic" as an
> apparently-fine cadence — real field data point (manual, not automated) suggesting
> ~3s is comfortably safe, looser than this project's own 1s limit.

**Worth reconciling with this project's own Q10 finding** (a 3x rapid-fire burst at
~50ms spacing produced *less* net change than expected, debounced into one effective
press) — these aren't contradictory, they're two different regimes: very tight spacing
(<100ms) gets swallowed by debounce into fewer effective presses, while moderate
repeated spam (on the order of ~1s, closer to a real human's press rate) can instead
*accumulate* overshoot beyond the intended step. The 1s interval this design already
uses sits comfortably inside the "known-safe" 3s field data point while being well clear
of the sub-100ms debounce-collapse regime — no change needed to the existing default,
this just explains *why* it's the right kind of conservative rather than an arbitrary
number.

One claim found and explicitly flagged as **wrong for this project's own confirmed
setup**: `54733`, subaru channel: "people have already tried the 'spam buttons' approach
and that's not possible (the buttons are directly connected to the camera)" — directly
contradicted by this project's own Q4/Q6/Q10 live-confirmed results. Outdated/wrong
claim, not a real blocker — but it underscores there's very little positive public
precedent for button-spoofing working reliably at all; this project has already gone
further than what's documented anywhere in this archive.
