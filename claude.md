# Poor-Man's Longitudinal Control

Read @progress.md at the start of every session — it's the living project state
(phase status, open questions, decisions log, key constraints). Update it at the
end of every session: Status checkboxes, Open Questions table, Changelog.

**Phase 3 is live**, not bench-only — real curve-speed and lead-vehicle-closing
actuation, armed and public-road-tested. See `research/phase3_controller_design.md`
§7-§9 for the full settings/design, and progress.md's most recent entries for the
latest live-drive findings and fixes.

**This repo is for planning, design, and reference code only — it is not deployed
from directly.** There is no device/CAN access from here. Draft designs as new or
updated `.md` files, and reference implementations as standalone code if useful, then
push. A separate session with the actual local dev environment and vehicle SSH access
integrates anything real into the working `openpilot` fork and handles deployment —
never attempt to reach a device or transmit on CAN from this environment; there's
nothing here that could do that anyway, but don't assume otherwise.

**This repo is public — scrub before pushing.** No personal name, no local absolute
file paths (use `~/...` or generic placeholders), no network details (IPs, hostnames,
Tailscale/LAN addresses, dongle IDs), no GPS coordinates from real drives. Two early
research reports (`Rigorous_Subaru_Preglobal_CAN_and_UDS_Research.md`,
`Subaru_CAN_Reverse_Engineering.md`) were found to contain fabricated "verbatim
quotes" and were deliberately excised — do not recreate them or cite them if
encountered elsewhere; every claim from them was independently re-verified and only
the corroborated facts were kept, in the Q4/Q5/Q8/Q9 rows and changelog of
progress.md.
