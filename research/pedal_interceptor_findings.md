# Pedal interceptor for this Subaru — findings (2026-07-23)

## Top-line answer

**Not needed, and not worth pursuing for this car.** The one thing a pedal interceptor
would give this Subaru — resuming from a full stop — is already solved in this
project's own codebase, in software, for free (`opendbc/sunnypilot/car/subaru/stop_and_go.py`,
already present, explicitly handles `SubaruFlags.PREGLOBAL`). Real community members said
exactly this, independently, four years apart:

> mlp______, 2020: "it might be useful when starting to develop long control but for
> just stop and go it is not needed... in short, you can use the pedal but imo it would
> be overkill"

> goldskis, 2024, replying to someone asking specifically about Subaru resume-from-stop:
> "Sunnypilot adds the functionality you are talking about. No need for comma pedal"

And a real, working confirmation the software path actually functions on Subaru:

> rattail98, 12/20/2025: "SP gives me SnG on my subaru, but not sure about the status
> for Honda"

## Is this the same as the physical button-splice idea from earlier? No.

Different mechanism, different physical location:
- **Button-splice idea (discussed earlier):** a relay/microcontroller wired into the
  **steering-wheel button switches**, to physically mimic a SET/RES press.
- **Pedal interceptor:** hardware spliced into the **accelerator pedal's own position
  sensor wiring** (sometimes brake too), letting panda report an arbitrary pedal
  position directly to the car's ECU — genuine continuous/proportional acceleration
  control, not a discrete button click.

They solve different classes of problem. Nothing about researching one validates or
invalidates the other.

## Zero precedent for this specific car

Searched both `pedal-interceptor` (1.2MB/35,560 lines) and `subaru` (8.5MB/263,260 lines)
channels. Only 6 Subaru mentions total in the pedal-interceptor channel, all connector
part-number photos or generic questions — **zero confirmed preglobal-specific installs
found anywhere in either channel.** The Subaru-specific discussion that exists is all
people asking "do I need this?" and being told no (see above), not people who actually
built one.

## No existing code path in this project's stack either

Confirmed directly in opendbc: `enableGasInterceptor` (the flag that wires interceptor
hardware into a car's actual control logic) exists only for **Toyota and Honda** —
zero references anywhere in Subaru's interface code, stock or sunnypilot. So even with
the hardware physically installed, there's currently nothing to drive it — that would
mean writing new carcontroller code from scratch, not installing a supported
accessory. This isn't a documented/paved path anywhere in the community either — the one
person who directly asked "is there some special sauce needed to add interceptor support
to a particular vehicle port?" (jmpz11, 2020) never got a real answer in-thread, just
unrelated anecdotes from people using it on already-supported cars (Bolt, Civic).

## Real safety/reliability signal — genuinely riskier than anything discussed so far

Not hypothetical caution — repeated, consistent signal across years:

- A message repeated verbatim at least 4 times in the channel (looks like a standard
  warning people quote/link): "Getting a Comma Pedal is NOT EASY, nor should it be. It's
  not exactly a polished and warranted product and it can be dangerous or even…"
- Comma's own official stance, stated plainly by a user: "The Pedal is not supported by
  Comma AI. They would rather a car have ACC. Less liability." (18867)
- A real, concrete, unresolved incident report — different car (Chevy Bolt EV), but a
  genuine malfunction, not speculation: "got propulsion power reduced warning at around
  12 miles and the LKAS went off... today I turned on car to see if the warning light is
  still there and it is." (35105, Dec 2025)
- Balancing view also present: "it is risky, but i havent seen any serious malfunctions
  reported" (21784) — so not universal doom, but the risk is treated as real, not
  overblown paranoia, by the community itself.

## Cost

Not cleanly pinned down — general sentiment is "not cheap" ("pricey", "cost me an arm
and a leg") rather than a solid number; one incidental data point (a harness-box bundle
add-on at +$10) isn't the actual interceptor kit price. Didn't chase this further since
the top-line answer already makes cost moot for this use case.

## Bottom line

For resume-from-stop specifically — the only thing this Subaru would actually gain — you
already have it, in software, already in this project's tree, already confirmed working
by a real 2025 community report on Subaru specifically. A pedal interceptor would add
real installation complexity, a genuinely elevated (not hypothetical) safety/reliability
risk profile the community itself flags repeatedly, zero preglobal-specific precedent to
learn from, and would additionally require writing entirely new, unprecedented
carcontroller code just to make the hardware do anything at all on this platform. No
upside found that isn't already covered for free.
