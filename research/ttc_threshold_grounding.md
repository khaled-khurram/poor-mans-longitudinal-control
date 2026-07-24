# TTC/following-distance threshold grounding (2026-07-24, overnight research pass)

Goal: pin a real threshold for Phase 3's lead-vehicle actuation trigger
(`research/phase3_controller_design.md` §9), which was left as an explicit unknown
("not yet pinned to a number") since the archived data showed raw TTC-at-detection
alone doesn't cleanly separate real brake-needed episodes from benign ones.

## Web research (NHTSA / literature)

- NHTSA's heavy-vehicle FCW test-track protocol uses a **5.0s TTC** threshold for alert
  timing. [Test Track Procedures for Heavy-Vehicle FCW](https://rosap.ntl.bts.gov/view/dot/42186/dot_42186_DS1.pdf)
- Time-headway literature: **1.2-2.0s is the established safe/efficient following
  range**; headways under 0.5s are flagged as critical/dangerous. A field-deployed
  bundled ACC+FCW system increased average headway 16% and cut sub-0.5s critical
  headways by 73%, reducing harsh-braking events 67%.
  [ITS Deployment Evaluation](https://www.itskrs.its.dot.gov/2014-b00947),
  [ScienceDirect — headway monitoring FCW](https://www.sciencedirect.com/science/article/abs/pii/S0968090X18318679)
- No literature found combining "TTC below X" with "host vehicle not yet braking" as a
  named standard technique — that compound signal is a reasonable project-specific
  adaptation (this platform can't observe EyeSight's brake state directly), not itself
  an established pattern.

## Local code check — openpilot already has a usable, tuned FCW mechanism (not a raw TTC number)

`selfdrive/controls/lib/longitudinal_mpc_lib/long_mpc.py`:
- `CRASH_DISTANCE = .25` (meters, line 42)
- `FCW_IDXS = T_IDXS < 5.0` (line 54 — a 5-second horizon, matching the NHTSA
  heavy-vehicle figure above)
- Triggers `crash_cnt += 1` when the **MPC-solved ego trajectory** would close to within
  `CRASH_DISTANCE` of the lead within that horizon (lines 354-356).

`selfdrive/controls/lib/longitudinal_planner.py`:
- `self.fcw = self.mpc.crash_cnt > 2` (line 148 — sustained 3 frames, not single-frame)
- published as `longitudinalPlan.fcw` (line 193)

This is a **trajectory-prediction check, not a threshold on raw TTC** — it asks "does my
planned deceleration still end in a crash," a fundamentally more sophisticated
computation than `dRel/-vRel < X`. Phase 3's shallow-nudge controller has no MPC of its
own, so this can't be reused directly, but it's a strong independent confirmation the
5-second horizon is the right order of magnitude.

## Recommendation

- **Primary gate: TTC < 5.0s** — two independent real-world anchors (NHTSA + openpilot's
  own existing FCW horizon).
- **Secondary/backup check: time-headway < ~2.0s.**
- **Confidence**: the two individual numbers are well-grounded (published standard +
  this project's own existing FCW code). The specific *combination* with the "ego not
  yet braking" compound signal is a project-specific design choice, not literature-
  validated — that's exactly what the planned archive backtest against the 63 real
  historical episodes (`research/lead_warning_raw_results.json`) is for: confirming or
  correcting the compound signal, not just the threshold number.
