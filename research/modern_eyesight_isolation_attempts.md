# Modern EyeSight isolation attempts — Discord research (2026-07-23)

## Top-line

**No modern (post-2021) EyeSight-isolation hardware project found for any Subaru, and
more importantly: the "relay box" isolation architecture that DOES exist and DOES work
today is explicitly GLOBAL-platform-only. Preglobal cars — this car — don't have it and
don't use it, confirmed directly by the original Giraffe-era developer himself.**

## The real, current isolation mechanism — but it's global-only

A 2024 conversation (`goldskis`, sunnypilot-affiliated, Aug 2024) describes the modern
official harness architecture plainly:

> "The car and the eyesight computer are isolated from each other at the relay box. The
> relay box mirrors the respective signals from the CAN0 side to the CAN1 side and vice
> versa. The comma then selectively overwrites or blocks the signals we don't want
> crossing over."

This is real and current, and confirms full bidirectional signal blocking is
architecturally possible with the official harness — goldskis states Subarus can be
driven "down to 0" (overriding EyeSight's normal 35mph floor) using this mechanism. But
the same thread is about a **2020 Subaru** (confirmed by `hmhale` later in-thread) and
the actual blocking mechanism referenced elsewhere in that conversation is UDS
`CommunicationControl` (`0x787`, `make_tester_present_msg`) — the same global-only
silencing trick this project's own Q9 investigation already tested and confirmed does
NOT work on preglobal. So this doesn't reveal a new mechanism — it's the same one Q9
already ruled out for this car, just working as expected on a global-platform car.

## Direct, explicit confirmation: preglobal doesn't have/need this

From the original 2019 Giraffe-era thread, `bugsyborromeo` (the same person behind the
Giraffe hardware) and `mlp______`:

> bugsyborromeo: "It's on all cars with eyesight, i just don't have a relay to worry
> about and run direct"

> mlp______: "relay is a solution to technical problem on global, preglobal does not
> need it"

This is about as direct as it gets: the person who actually built the isolation
hardware says his own preglobal setup runs "direct," no relay involved, and a second
contributor independently confirms the relay/isolation architecture is a global-specific
solution. Preglobal's harness is architecturally simpler and does not have this
selective-block capability.

## No continuation of the Giraffe project found

Zero hits for "isolate eyesight" combined with any post-2021 date, no discussion of
Coltonton or the Giraffe hardware continuing past its original 2019-2021 era in the
searched channels. No comma-3X-era or comma-4-era EyeSight isolation hardware project
found for any Subaru generation.

## No experimental/alpha longitudinal support for preglobal, confirmed explicitly

> "experimental longitudinal is currently supported for some global models, there is no
> working implementation for preglobal" (subaru channel)

Rules out the other angle this fork was asked to check (whether an alpha-long mode
might already provide fuller isolation) — it doesn't exist for this platform at all.

## Bottom line

The modern, working, official isolation mechanism is real but is global-platform-only,
and uses the same UDS silencing trick this project's Q9 already tested and found
non-functional on preglobal — not a new avenue. The original DIY Giraffe hardware that
did achieve true physical isolation was preglobal-relevant but is 2019-2021-era,
built for a standalone Panda box incompatible with this project's comma 4, and has no
found successor project. Direct confirmation from the person who built it: preglobal
doesn't have or need the relay/isolation architecture that makes any of this work on
global cars. This closes the "maybe the harness already supports fuller isolation"
question — it doesn't, for this platform.
