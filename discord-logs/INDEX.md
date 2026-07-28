# Discord Log Index

Catalog of `comma.ai community` Discord channel exports in `CommaDiscord/`, built by sampling
(grep/head/tail/keyword counts), not full reads — files are up to 16MB. Purpose: pick the right
file(s) to grep for a given question instead of re-scanning all 13 from scratch. Regenerate/extend
this file if more channels get added later.

Active project context these summaries are written against: 2015 Subaru Outback, preglobal EyeSight
platform, sunnypilot fork, reverse-engineering the `0x144 CruiseControl` message and researching
whether a UDS `CommunicationControl` (service 0x28) "stop transmitting" trick — known to work on
Subaru **global-gen2** — also works on **preglobal** (SSM3-era diagnostics). See `progress.md` Q4/Q5/Q8/Q9.

---

## `comma.ai community - Vehicle Specific - subaru [525718620517564446].txt`
- **Size:** 8.5MB, 263,260 lines, 57,719 messages
- **Date range:** 12/21/2018 – 7/21/2026
- **Summary:** The single most important file for this project. Years of Subaru-specific openpilot/sunnypilot discussion — installs, fingerprinting, FPv2 (2nd-gen EyeSight ACC), the multi-year `mlp______`/`hulipill`/`bitwaster` thread on getting access to **SSM4** (Subaru Select Monitor 4, the official $3-6k dealer diagnostic tool) to reverse-engineer FW versions and ACC behavior, and later (2023) `jnewb1`'s UDS/seed-key work that became the `UnlockECU` project referenced in progress.md Q8.
- **Search keywords:** `SSM4`, `SSM3`, `mlp______`, `jnewb1`, `hulipill`, `bitwaster`, `seed/key`, `FPv2`, `fw fingerprinting`, `Mode 22`, `preglobal`, `EyeSight`, `UnlockECU`
- **⚑ DIRECTLY RELEVANT — high value:**
  - Line ~204143-204145 (5/27/2023, `jnewb1`): **"Eyesight is successfully UDS disabled, and 0x27 seed/key unlocked - I can still read the buttons through the UDS message"** — this is a real, first-hand community report of exactly the Q9 bus-contention trick (silence EyeSight's real transmitter via UDS, read/inject around it) actually working. Caveat: `jnewb1`'s seed/key work throughout this file (line ~202980 onward, ~5/18/2023–5/28/2023) is in the context of `SSM4`, which progress.md already notes is the **global-platform** diagnostic tool/protocol — need to confirm in-thread whether this specific success was on a preglobal or global-gen car before citing it as a Q9 answer. This is the single best lead in the whole corpus for Q9 — flagged for the Q9 research pass to chase down directly.
  - 432 mentions of "preglobal", 107 of SSM3/SSM4, 88 UDS/CommunicationControl/0x28 hits, 13 seed/security-access hits — this file alone likely contains most of what's discoverable Discord-side for Q8/Q9.

## `comma.ai community - Development - dev-opendbc [1282121586002104402].txt`
- **Size:** 714KB, 18,691 lines, 3,444 messages
- **Date range:** 9/7/2024 – 7/21/2026 (channel only created then; opendbc discussion pre-2024 likely lives in dev-openpilot instead)
- **Summary:** Technical channel for opendbc itself (car ports, safety code, DBC files) run by comma staff (`adeebshihadeh` et al). General car-port/safety-code process discussion, PR reviews, brand-agnostic longitudinal tuning parameter debates (e.g. `stoppingDecelRate`).
- **Search keywords:** `safety`, `TX_MSGS`, `DBC`, car brand names, `opendbc/pull/`, `AEB`
- **⚑ Relevance:** Low-moderate. No `0x144` mentions, only 2 "preglobal" mentions, 1 SSM3/4 mention. 27 UDS/CommunicationControl/0x28 hits and 7 bus-off/MITM hits worth a targeted grep if Q9 research comes up dry elsewhere, but this reads as a general safety-code channel, not Subaru-specific.

## `comma.ai community - Development - dev-openpilot [524594418628558878].txt`
- **Size:** 7.0MB, 198,552 lines, 39,773 messages
- **Date range:** 1/24/2019 – 7/22/2026
- **Summary:** The long-running general openpilot dev channel — predates dev-opendbc's split-off, so likely has older opendbc/safety-code-era discussion. Broad technical range: planner/controls bugs, EON/comma3/4 firmware, process crashes, PR discussion.
- **Search keywords:** `plannerd`, `carcontroller`, `safety`, `panda`, `EON`
- **⚑ Relevance:** Low-moderate for Subaru specifically (only 1 "preglobal" hit) but 64 UDS/CommunicationControl/0x28 hits and 22 bus-off/MITM hits — worth a grep pass if Q9 needs cross-brand precedent for the "silence a competing ECU via UDS" technique in general.

## `comma.ai community - dev_topics - custom-forks [538741329799413760].txt`
- **Size:** 11.6MB, 349,018 lines, 74,912 messages
- **Date range:** 1/26/2019 – 7/22/2026
- **Summary:** Fork discussion (sunnypilot, FrogPilot, etc.) — feature discussion, install help, fork-specific bugs/UI. Includes `sunnyhaibin` (sunnypilot maintainer) directly answering questions, e.g. recent `copyparty` question.
- **Search keywords:** `sunnypilot`, `sunnyhaibin`, `FrogPilot`, fork names, `mici`
- **⚑ Relevance:** Moderate for general sunnypilot/UI questions (this project uses a sunnypilot fork), low for Q9 specifically (8 "preglobal" hits, 0 `0x144`). Worth checking if a sunnypilot-specific UI or build question comes up.

## `comma.ai community - dev_topics - fw-mods [664566220086837273].txt`
- **Size:** 923KB, 28,584 lines, 6,137 messages
- **Date range:** 1/8/2020 – 7/19/2026
- **Summary:** Firmware modification discussion (per channel rules: no walkthroughs, discussion only, "substantially over 2x torque mods" bannable). Torque-limit unlock discussion across many brands, EPS firmware.
- **Search keywords:** `torque mod`, `EPS`, `firmware`, `seed/key`, `UDS`
- **⚑ Relevance:** Low for Subaru longitudinal specifically (0 "preglobal", 0 `0x144`), but has generic seed/key UDS security precedent (line ~27769: "EPS is locked down — UDS over CAN-FD + seed/key security") that's a useful pattern reference for how other brands' UDS security access gets bypassed. 37 UDS/CommunicationControl/0x28 hits.

## `comma.ai community - dev_topics - openpilot-ui [1120514126783979540].txt`
- **Size:** 158KB, 4,116 lines, 721 messages
- **Date range:** 6/19/2023 – 7/22/2026
- **Summary:** UI mockups/design discussion channel, started by `georgehotz`. HUD layout, alert rendering discussion.
- **Search keywords:** `HUD`, `mockup`, `alert`, `z-order`
- **⚑ Relevance:** None for Q9/CAN work. Could be useful later if more UI polish work happens (this project already did a HUD z-order fix for the speed-limit display) — zero hits on all safety/CAN keywords.

## `comma.ai community - dev_topics - pedal-interceptor [524595554898935808].txt`
- **Size:** 1.2MB, 35,560 lines, 7,619 messages
- **Date range:** 12/20/2018 – 6/24/2026
- **Summary:** Comma pedal interceptor hardware discussion — wiring, installation, noodle-cable/Ethernet-connector quality issues, pedal calibration.
- **Search keywords:** `pedal`, `ethernet`, `noodle cable`, `calibration`, `interceptor`
- **⚑ Relevance:** Low for the current Phase 2/3 UDS/button-injection thread (this project isn't using a pedal interceptor — it's pursuing CAN-bus button injection, not pedal replacement) but worth knowing about as an alternative "poor man's longitudinal control" approach if the CAN-injection route stalls. 1 UDS/0x28 hit, 0 "preglobal".

## `comma.ai community - dev_topics - toyota-security [905950538816978974].txt`
- **Size:** 3.9MB, 124,146 lines, 26,380 messages
- **Date range:** 11/4/2021 – 7/22/2026
- **Summary:** Deep, technical Toyota TSS security-bypass channel started by `georgehotz` (Toyota TechInfo firmware access, encryption). Heaviest UDS/security-access content of any file in this corpus by far.
- **Search keywords:** `SecOC`, `TechInfo`, `seed/key`, `blackbox`, `firmware verification`, `bypass`
- **⚑ Relevance:** Different brand (Toyota, not Subaru) but **highest concentration of UDS/CommunicationControl technique discussion in the whole corpus**: 162 UDS/0x28 hits, 38 seed-key/security-access hits, 53 bus-off/MITM hits. Worth mining for the *general technique* (how UDS communication-control/security-access bypasses are approached methodologically) even though it won't have Subaru-specific answers. Good precedent-pattern source for the Q9 researcher.

## `comma.ai community - dev_topics - tuning [574796986822295569].txt`
- **Size:** 4.7MB, 152,579 lines, 33,162 messages
- **Date range:** 5/5/2019 – 4/28/2026
- **Summary:** Cross-brand longitudinal/lateral tuning discussion — live-tuner usage, PID/torque tuning, general car-dynamics debugging.
- **Search keywords:** `live tuner`, `PID`, `lateral accel`, `longitudinal`, brand names
- **⚑ Relevance:** Low for Q9 (1 preglobal hit, 0x144: 0) but this is the right file if/when tuning the curve-advisory Phase 1 behavior itself becomes the question again, separate from the Phase 2/3 CAN work.

## `comma.ai community - General - general [954493346250887168].txt`
- **Size:** 16.7MB, 521,406 lines, 111,100 messages — **largest file in the corpus**
- **Date range:** 3/18/2022 – 3/24/2026
- **Summary:** Catch-all general discussion — highest noise-to-signal ratio of any file here (account bans, unrelated chat, "who bought a comma 4" type threads), but also the highest raw message count means real technical answers do surface here that don't fit a specific topic channel.
- **Search keywords:** treat as last-resort/fallback — grep specific technical terms only, don't browse
- **⚑ Relevance:** Surprisingly non-trivial: 7 "preglobal", 55 UDS/CommunicationControl/0x28, 22 bus-off/MITM, 6 seed/security-access hits — scattered but present. Worth a keyword grep here if the topic-specific channels come up empty, not worth reading directly otherwise.

## `comma.ai community - Hardware - hw-four [1436852432503046294].txt`
- **Size:** 1.5MB, 45,453 lines, 9,085 messages
- **Date range:** 11/8/2025 – 7/22/2026 (comma 4 hardware is new; channel is young)
- **Summary:** comma 4 hardware discussion/announcement channel — this project's actual device generation. Mix of real hardware questions and off-topic banter (sampled mid-file: a tangent about old dial-up internet).
- **Search keywords:** `comma 4`, `STM32H7`, `panda`, `harness`
- **⚑ Relevance:** Directly relevant hardware generation (this project's comma 4 has the panda chip built in per progress.md), but low content overlap with Q9/CAN-injection specifically (0 preglobal, 0 0x144, only 2 UDS hits). Better source for hardware-quirk questions than protocol questions.

## `comma.ai community - Hardware - hw-three-3x [871838269405556736].txt`
- **Size:** 5.7MB, 167,115 lines, 34,900 messages
- **Date range:** 8/2/2021 – 8/24/2025
- **Summary:** comma 3/3X hardware discussion (previous-gen device, this project uses comma 4 instead) — heat/fan issues, warranty, general hardware troubleshooting.
- **Search keywords:** `fan error`, `heat`, `warranty`, `3X`
- **⚑ Relevance:** Low — different hardware generation than this project's comma 4. 1 preglobal hit, 0 0x144, 12 UDS hits. Skip unless a hw-3X-specific comparison ever comes up.

## `comma.ai community - Vehicle Specific - car-port-info [1246926332110045216].txt`
- **Size:** 1.4KB, 24 lines, **1 message**
- **Date range:** 6/2/2024 only (single pinned welcome message)
- **Summary:** Not a real conversation log — just the channel's single pinned "Welcome to car porting!" message from `adeebshihadeh` with links to the opendbc repo, comma.ai/vehicles list, WIP car-port board, and the car-bounty program page.
- **Search keywords:** n/a — this is reference links, not discussion
- **⚑ Relevance:** None for Q9. Only useful as a pointer to where the *live* car-port board/bounty docs are (external links), not as searchable discussion content.

---

## Quick-reference: where to look first by question type
- **Subaru preglobal / SSM3 / UDS / EyeSight-silencing (Q9-shaped questions):** `subaru` file first, always — it dominates every other file combined. `toyota-security` second, for cross-brand UDS technique patterns. `general` as a last-resort grep.
- **Sunnypilot/fork-specific UI or build questions:** `custom-forks`, then `openpilot-ui`.
- **Hardware quirks on this project's actual device (comma 4):** `hw-four`.
- **Curve-advisory / longitudinal tuning behavior (Phase 1 territory, not Phase 2/3):** `tuning`.
- **Safety-firmware / TX-allowlist code precedent from other brands:** `dev-opendbc`, `fw-mods`, `dev-openpilot`.
