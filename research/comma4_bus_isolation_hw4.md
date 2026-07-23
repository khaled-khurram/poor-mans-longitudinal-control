# EyeSight/CAN isolation hardware on comma 4/3X (integrated-panda) — Discord research (2026-07-23)

## Top-line

**No one has documented building a modern equivalent of the old standalone-panda Giraffe
board for comma 4 or 3X.** But real, useful architecture context was found: an external
Red Panda CAN genuinely be added to a comma 4 via its second USB-C port — a real,
comma-supported accessory pattern, not a hack — which means the physical path a modern
"Giraffe" would need (a standalone Panda to interpose hardware into) does exist on this
hardware. Nobody's documented actually building the isolation board itself for this era
of hardware.

## Method

Searched `comma.ai community - Hardware - hw-four [1436852432503046294].txt` (1.5MB,
45,453 lines) for isolation/interposer/Giraffe/splice-tap terms, integrated-panda
architecture discussion, and external/red Panda discussion.

## What's confirmed

**Panda is fully integrated into both comma 4 and 3X** — direct, unambiguous community
confirmation:
> `calvinspark`, 11/29/2025: "No, panda is built into 4 (and also 3x)"

**An external Red Panda can genuinely be added to a C4** via a second USB-C port — this
is a real comma-supported use case, not theoretical:
> "C4 Magmount will come soon after, with 2 full-featured USB-C ports for the external
> GPU, or as Rivian users requested for the external Red Panda." (11/15/2025)

Confirms real people do this for specific needs — a related exchange mentions "ESCC"
(a Rivian-specific longitudinal feature) explicitly requiring or benefiting from a
second Panda in some configurations (`41418`, not fully explained in-thread but real).

One user asked directly whether an external Panda offers any advantage over the
built-in one and got a blunt answer:
> `winwho.`: "What would be the advantage over the built-in capability?"
> `erichmoraga`: "Not advantageous."

This reflects normal-use sentiment (most people don't need it), not a statement that
it's impossible or pointless for an isolation-hardware use case specifically — that
specific application never came up in this channel at all.

## What's NOT found

Zero discussion anywhere in this channel of: physically tapping/modifying the comma 4's
own OBD-C harness path, anyone building custom interposer/isolation hardware for 3X or
4, or any modern successor to the old Giraffe concept. The OBD-C schematic is publicly
referenced (`github.com/commaai/hardware/blob/master/harness/OBD-C.sch.pdf`) but nobody
in this channel discusses using it to design custom hardware.

## What this means for the EyeSight-isolation idea

The theoretical path exists and uses confirmed-real hardware capability: get an
external Red Panda, connect it via the C4's second USB-C port (already a real,
supported pattern), then design a modern interposer board to sit between that Panda
and EyeSight — the same conceptual role the old Giraffe played for standalone-panda-era
hardware. But this is a genuinely unexplored combination — nobody has documented doing
the EyeSight-isolation part on this generation of hardware. Not contradicted by
anything found, not validated either — real open territory, same as the bus-2
injection question researched earlier tonight.
