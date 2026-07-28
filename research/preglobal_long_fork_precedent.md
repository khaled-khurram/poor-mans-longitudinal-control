# Preglobal Subaru longitudinal-control fork precedent (2026-07-25)

Research trigger: a Discord message quoted to the user claimed martinl and jnewb1 "did get
[preglobal long] working" and it was shared privately with "Jason from sunnypilot." Ran 4
parallel research passes (2x local Discord archive grep, 2x live web/GitHub) to find the
real history behind this.

## Timeline

- **2019-2022 (martinl / `mlp______`):** original unofficial Subaru preglobal community fork
  (`martinl/openpilot`, branches `subaru-community`, `subaru-giraffe-devel`). Steering/harness
  support only — no longitudinal. Upstream PR
  [#1489](https://github.com/commaai/openpilot/pull/1489) "WIP: Subaru preglobal models
  support" (2020, credited `@bugsy924`), closed unmerged, vehicle support not longitudinal.

- **Jan 2022 — `martinl/openpilot:preglobal-non-epb-sng`** (commit `af7cb56`, still live on
  GitHub, not deleted): real button-spoof code. In `selfdrive/car/subaru/carcontroller.py`,
  sends `cruise_button = 4` (RES) once/sec via `subarucan.create_preglobal_es_distance()`
  while in standstill with a lead car — auto-resumes stock ACC stop-and-go. Same CAN
  button-injection mechanism this project independently reverse-engineered (Q4/Q10). Also
  `martinl/openpilot:subaru-preglobal` (2022-02-21) — FPv2/firmware-ID work, not actuation.

- **April 2023 — jnewb1 (Justin Newberry) starts real longitudinal work.** Builds a second
  panda + Subaru "B harness" specifically for CAN intercept. Discord, `mlp______`
  (martinl), 4/11/2023: *"Subaru Long control has a proof of concept from martinl. It is
  possible and it works, but not very good yet and not upstreamed."*

- **April 27, 2023 — first real engagement.** Forces `cruise_active=true` via second panda,
  works ~15s before LKAS fault. comma engineer `sshane_` (Shane) coaching directly in-thread.
  Branches: `jnewb1/openpilot:subaru-legacy-long`, `jnewb1/panda:subaru-legacy-long`.

- **April 30, 2023 — pivot to UDS approach** (single panda, gen2): jnewb1 shares
  `github.com/commaai/openpilot/compare/master...jnewb1:openpilot:feature-subaru-long-gen2-uds`
  — silence EyeSight via UDS instead of a second physical panda. Installer:
  `installer.comma.ai/jnewb1/subaru-gen2-uds-test`.

- **May 2023 — comma's stated upstream bar:** jnewb1: *"Shane told me when we get gen2
  working is when he would try and get Subaru long upstreamed."* Never happened for
  preglobal.

- **Aug 2023 — real cash bounty, tied to Justin by name.**
  [GoFundMe: "Pre-Global Subaru: Openpilot Longitudinal Support"](https://www.gofundme.com/f/preglobal-subaru-openpilot-longitudinal-support),
  organized by Rikin Shah (`rikinmshah` in Discord) on behalf of Justin Newberry. Goal
  $1,700, raised $2,550 (150%). Bounty terms: merged PR to both `commaai/openpilot` and
  `martinl/subaru-community` fork, verified by 2+ preglobal owners, 6-month completion
  window with refund clause (likely expired/refunded by now — not verified live).
  Covers Forester 2017-18, Legacy 2015-19, Levorg 2016-20, Outback 2015-19, WRX 2016-18.
  Earlier/general precedent: [GitHub issue #1177](https://github.com/commaai/openpilot/issues/1177)
  "Bypass Subaru ACC and enable stop and go - $500 Bounty" (2020).

- **Aug 2023 — upstream global-only longitudinal lands.**
  [#25345](https://github.com/commaai/openpilot/pull/25345) "Subaru: POC for longitudinal
  control" (martinl, global gen1/gen2 Crosstrek) closed, superseded by
  [#28872](https://github.com/commaai/openpilot/pull/28872) "Subaru: Global gen1
  experimental longitudinal" (jnewb1) — **merged**, but explicitly excludes preglobal.

- **Nov 5, 2023 — the actual "we did get it working" event.** Discord, `samehimohamed`:
  *"thanks to @justin for getting long control working under subaru global **and
  preglobal** with stock OP and Justin's subaru-global-long branch."* Same post: EyeSight
  activation conflicts with OP's own stop/start at low speed; intersections reliably throw
  disengagement + unrecoverable "hands on wheel" EyeSight faults (needs full ignition
  cycle); AEB inactive on this branch. This is the real basis for "long isn't where it
  needs to be to use instead of stock."

- **Nov 8-23, 2023 — the specific preglobal installer appears:**
  `installer.comma.ai/jnewb1/subaru-preglobal-long`, described in-thread: *"has long
  support (no eyesight)"* — i.e. full OP longitudinal **replacing EyeSight entirely**, not
  button-spoofing. This is the exact repo path referenced (now 404) in the message quoted
  to the user.

- **June 2025 — martinl gives the still-current verdict, unprompted:** *"iirc preglobal
  does not have longitudinal but in current state you are not missing much vs stock
  long."* Matches the 2026-07-25 Discord answer almost verbatim — stable community
  consensus for a year+.

- **2025 — sunnypilot's own Stop-and-Go ships, covering preglobal.**
  [sunnypilot/opendbc PR #152](https://github.com/sunnypilot/opendbc/pull/152), authored by
  **sunnyhaibin** (sunnypilot's lead maintainer), merged 2025: "Subaru: Stop and Go support
  (beta)" — sunnypilot changelog confirms it covers "Global (excluding Gen 2/Hybrid) and
  Pre-Global." Button/throttle-style auto-resume, not full EyeSight replacement. Plausibly
  connected to what was shared privately ("Jason from sunnypilot"), though that specific
  name was never found in the archive.

## Current state / dead ends confirmed

- `jnewb1/openpilot/tree/subaru-preglobal-long` — confirmed 404, doesn't exist.
- jnewb1's current GitHub only has `openpilot2` (branches `bridge-toggle`, `master`) and an
  empty `openpilot-cleanup` — no public preglobal-long branch survives anywhere on his
  account.
- No GitHub repo/branch anywhere (code search across all of GitHub) combines
  `subaru-preglobal` + full longitudinal actuation publicly.
- "Jason from sunnypilot" not resolved to a real identity — not `sunnyhaibin` (found
  separately, unrelated context), not the one "Jason Young" hit in the archive (a
  COMMA_CON community speaker, unconnected to sunnypilot). Likely someone newer than this
  archive's coverage.
- `community.sunnypilot.ai/t/enabling-icbm-on-17-impreza/191/4` still 403s on direct fetch;
  no indexed site-search hits for preglobal longitudinal on that forum either.
- Reddit: no relevant discussion found — this topic lives in GitHub PR threads and
  Discord/sunnypilot-forum, not Reddit.

## Relevance to this project

`martinl/openpilot:preglobal-non-epb-sng` is the one piece of real, still-live code
directly on point — same CAN button-injection mechanism (`create_preglobal_es_distance`,
RES-button spam) this project already independently reverse-engineered and live-tested
(see `progress.md` Q4/Q10). Worth a direct diff against this project's own implementation:
either confirms the approach further, or surfaces an edge case from 3+ years of it existing
that this project's own testing hasn't hit yet. The full-longitudinal "no eyesight"
replacement path (jnewb1/Justin's Nov 2023 work) is a fundamentally different, harder
approach than this project's "ride EyeSight, just move its dial" design — its documented
failure modes (unrecoverable EyeSight faults, AEB disabled, low-speed stop/start conflicts)
are a reason to actively favor this project's more conservative approach, not a blocker to
work around.
