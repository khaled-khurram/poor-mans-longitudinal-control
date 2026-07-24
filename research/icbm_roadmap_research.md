# ICBM research: what's out there, what it means for Phase 3 (2026-07-24)

Four parallel research passes: sunnypilot's own ICBM code architecture, cross-brand
Discord community research, stock-openpilot/industry web research, and a Subaru
global-gen2 deep dive. Goal: find a roadmap for improving Phase 3 (this project's own
from-scratch curve/lead button-spoofing controller) against the real, official pattern.

## 1. Does stock openpilot have this at all?

**No — purely a sunnypilot community feature, not borrowed from any recognized industry
pattern.** Every ICBM PR lives on `sunnypilot/opendbc`, never `commaai/opendbc` or
`commaai/openpilot`. No aftermarket-ADAS or published-research precedent found for
button-spoofing-based cruise emulation as a named technique outside this ecosystem —
"ICBM" appears to be sunnypilot's own coined term. This project isn't rediscovering an
established pattern; it's extending a niche one further than most of sunnypilot's own
existing per-brand implementations have gone.

## 2. What does ICBM actually do, and what's the design philosophy?

Straight from the sunnypilot maintainer (`dev-opendbc`, 9/30/2025, `sunnyhaibin`):
*"ICBM is more for cars that would probably never have OP long or for users that do not
want to use OP long. True OP long is still the better option in terms of direct control,
but some cars don't do well with it yet."* A bridge/fallback, not a superior alternative
— matches this project's own "poor man's" framing exactly.

Architecturally it's generic plumbing: closes the gap between a computed target
(`vTarget`, from whatever planner is running — MTSC/VTSC/lead-following) and the car's
actual displayed cruise speed, via button spam. It does NOT contain curve/lead/speed-
limit logic itself; that lives upstream and just feeds it a target — same separation of
concerns Phase 3 already follows.

**Official ICBM already ships curve/map-based speed adjustment via button-spoofing for
supported cars** ("SCC-Map"/"SCC-Vision" variants, per real Discord confirmation,
`custom-forks` 3/13/2026) — feature parity with what Phase 3's curve controller does,
already shipped elsewhere. Real positive user reports exist (Lincoln Navigator,
`adgower`, repeated over months: *"works like a dream"*).

**Real prior art for a feature Phase 3 doesn't have**: Speed Limit Assist (SLA,
`sunnypilot/selfdrive/car/cruise_ext.py:110-138`) auto-follows posted speed limits —
a separate, adjacent mechanism (direct `v_cruise_kph` clamp for `pcmCruiseSpeed` cars,
not button-walking, so doesn't port directly to Subaru preglobal) but a real, concrete
"what we're missing" answer: automatic speed-limit following, not just curves/lead.

## 3. Per-car config and the shallow/deep question

`common/params_keys.h:152-154` (already-registered, not hitting the compiled-allowlist
landmine our new params hit): `CustomAccShortPressIncrement` default `1`,
`CustomAccLongPressIncrement` default `5`. The official, shipped default assumption
really is short=1x/long=5x — independently corroborating the shallow≈1mph/deep≈5mph
hypothesis this project chased all night, from product config rather than archive
mining. Caveat: this is for manual short-tap-vs-long-hold on cars with native button
semantics, not Subaru's `ES_Distance.Cruise_Button` enum field — doesn't directly
confirm our field's magnitude (see `research/es_distance_cruise_button_finding.md`
follow-up: still genuinely unconfirmed for this car, needs a dedicated live test).

## 4. Braking/acceleration profiles are genuinely car-specific — the single most
## important finding for how this project should keep operating

**Honda's real, shipped, production ICBM cadence is 50ms between button sends**
(`opendbc/sunnypilot/car/honda/icbm.py`) — the *exact* interval Q10's own live test
found causes full debounce collapse on Subaru's `Cruise_Button` field. Same general
"button-spoofing ICBM" category, wildly different real per-ECU tolerance. sunnypilot's
own team has an explicit TODO (`controller.py:19`, `HYST_GAP`) flagging that a hysteresis
constant "might need to be brand-specific" — same lesson, independently.

**Conclusion: there is no universal cadence/profile to borrow from other brands.**
Tonight's empirical, Subaru-specific archive-mining approach (`research/button_cadence_response_curve.md`)
was the correct methodology, not a workaround — every car's real limits have to be
found empirically, and this project already did that correctly.

## 5. Does Subaru (any generation) actually have this working anywhere?

**No — corrected from the working assumption going into this research.** Checked
exhaustively at the code level: the per-brand ICBM injection interface
(`opendbc/sunnypilot/car/*/icbm.py`) exists for exactly four brands — Honda, Hyundai,
Chrysler, Mazda. Zero Subaru files, either generation.

**Global-gen2 is not a better-integrated analog to preglobal.** `opendbc/car/subaru/interface.py:90-91`
excludes `GLOBAL_GEN2` from `alphaLongitudinalAvailable` in the exact same clause as
`PREGLOBAL` — structurally the same category, not real long control either. The one
alternate path that exists for gen2 (`DISABLE_EYESIGHT` when alpha-long is used) takes
the *opposite* architecture from this project's choice — fully disabling EyeSight and
taking over, rather than riding its own setpoint. A real global-Subaru user reported
exactly the fragility that predicts (`subaru` channel, `subaru-giraffe` fork discussion):
EyeSight faulting (orange light, requires a car restart) tied to OP disengage/re-engage
cycles — *"there's really no way to have stock EyeSight working without OP engaged with
the current setup."* Arguably a worse failure mode than anything this project hit
tonight. **This validates, not just excuses, the "ride EyeSight's own setpoint"
architecture this whole project is built on** — it's not a workaround forced by missing
integration, it's a real robustness advantage over the alternative other Subaru owners
have actually hit problems with.

Two Discord reports independently confirm no working Subaru ICBM exists, global-gen or
otherwise (`furiouslyred`, 4/11/2026: *"I don't even think the ICBM even works"*;
`amusedgrape`, 7/17/2026, linking the sunnypilot forum's own unresolved "Enabling ICBM
on '17 Impreza" thread).

## 6. Shared risk class, genuinely reassuring context

Even official ICBM implementations have been reverted and reshipped for the same
*category* of bug this project hit tonight: Honda Bosch and Mazda ICBM were both
reverted ("button events needed to be parsed first" — a sequencing bug) and later
reapplied fixed; a separate PR fixed `pcmCruiseSpeed` being incorrectly `true` during
initialization. Engagement/initialization-moment edge cases, not steady-state logic
errors — the same shape as tonight's own plannerd crash (schema mismatch surfaced only
at real onroad init) and the override-latch grace-period fix (engagement-timing
residue). **This is a structural risk of the whole technique, not something specific to
this project's approach or competence** — even sunnypilot's own reference
implementations across other brands have hit it.

## Roadmap this points to

1. **Speed-limit-following as a third Phase 3 feature** — reuse the existing button-
   spoofing mechanism (SLA's direct-clamp approach doesn't apply to Subaru preglobal,
   no `pcmCruiseSpeed`), walk the target toward posted limits the same way curve/lead
   already do. The clearest concrete "what are we missing" answer from this research.
2. **Consider ICBM's unified state-machine pattern** (inactive→preActive→holding/
   increasing/decreasing) over the current two separate ad-hoc controller classes —
   cleaner, and a natural fit for adding a third feature.
3. **Deep-step magnitude still needs a dedicated live test** — official per-car config
   elsewhere reinforces the 1x/5x short/long philosophy is real and valuable once
   confirmed, but Subaru's own field magnitude remains genuinely unconfirmed
   (see `research/es_distance_cruise_button_finding.md`).
4. **Any further cadence tightening needs Subaru-specific live testing, not borrowed
   numbers** — the 50-200ms gap is still open, and this research just proved other
   brands' numbers (Honda's 50ms) are not transferable.
5. **ICBM's `update_readiness` gate is transient ("don't act this frame"), not sticky
   like Phase 3's override latch** — noting this as a deliberate, considered design
   difference (matches the user's own explicit "tap once, everything goes dark"
   request), not a gap to close.
