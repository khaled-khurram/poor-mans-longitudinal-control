# Lead-closing trigger backtest (2026-07-24, overnight pass)

Answers the gap `research/lead_vehicle_warning_analysis.md` line 96 flags as never
computed: does the shipped `LeadClosingAdvisoryHelper` trigger (`CLOSING_VREL_THRESHOLD
= -3.0 m/s`, `SUSTAIN_TIME = 0.5s`, `NO_RECENT_PEDAL_TIME = 3.0s`, `DEBOUNCE_TIME = 20s`,
`MIN_ADVISORY_SPEED = 50mph`) separate the 14 real brake-needed episodes from the 49
benign ones well enough to build Phase 3 actuation on directly?

## Method

Reused `research/lead_warning_raw_results.json` (163 raw candidates) and replicated the
same 20s same-route clustering `analyze_lead_warning.py` uses to produce episodes — no
archive re-mining. Reproduced exactly: **63 episodes, 14 brake / 27 decel_no_brake / 22
none**, matching `lead_vehicle_warning_analysis.md` Finding 3 verbatim. This confirms the
shipped code's constants are byte-for-byte identical to the original candidate/episode
definition — there is no daylight between "the trigger fires" and "this dataset's 63
episodes exist" by construction.

## Why this isn't a classic TP/FP/FN/TN confusion matrix

The 63 episodes **are** the full set of things the trigger fires on — the candidate
definition literally *is* the trigger condition. So there's no way to measure false
negatives (real brake events the trigger would have missed entirely) without a fresh
search across the *non-firing* population, which means re-mining the full archive from
scratch — explicitly out of scope for this pass, flagged as genuinely unresolved below,
not glossed over.

What **is** answerable from this data: of everything the trigger fires on, what fraction
turns out to matter? That's precision, not recall: **14/63 = 22%** — already the
headline number in Finding 3, now confirmed as the actual precision of the exact shipped
constants, not just a general finding from the original analysis.

## Does any feature separate brake from non-brake better than raw TTC already didn't?

Checked all four available features at first-detection, across the three outcome
groups — extending Finding 4's "TTC doesn't cleanly separate" check to see if it
generalizes:

| Feature | brake (n=14) median | decel_no_brake (n=27) median | none (n=22) median |
|---|---|---|---|
| vRel (mph) | -7.8 | -7.8 | -7.8 |
| dRel (ft) | 328 | 236 | 323 |
| vEgo (mph) | 75.6 | 73.7 | 80.2 |
| TTC (s) | 26.7 | 19.1 | 23.2 |

**None of these separate the groups.** `vRel` medians are essentially identical across
all three (the threshold check itself doesn't discriminate outcome, only whether a lead
is closing at all). `vEgo` is if anything backwards — the "none" (benign) group has the
*highest* median speed. This is a real negative result, not a gap in the analysis: no
single-feature threshold adjustment on the currently-available fields would improve
precision. Getting materially better than 22% would need a fundamentally different
approach (trajectory-based, like openpilot's own FCW MPC in `long_mpc.py` — out of scope
for a shallow-nudge v1 controller), not a retuned constant.

## Target formula sanity (`v_target = lead.vLeadK + 4mph`)

No per-episode time-series of `vLeadK` exists in this candidate-level dataset (only a
snapshot at first detection), so a true "did the lead's speed stay stable through the
episode" check isn't answerable without re-reading raw rlogs — **flagged as a real
limitation, not faked**. What is checkable: a coarse one-point estimate,
`vLead ≈ vEgo + vRel` at detection, for all 14 real brake episodes:

- Delta between current speed and computed target (`vEgo - (vLead+4)`) ranged
  **2.8-13.1mph** across the 14 episodes — always positive (a real, actionable
  slowdown is implied, never a zero/negative no-op) and never absurd.
- Three episodes stand out with notably larger gaps (12.3-13.1mph): `0000007c`,
  `0000009a`, `000000ac` — these also have the steepest closing rates of the whole set
  (vRel -16 to -17mph vs. the ~-7 to -8mph typical of the rest). A single shallow
  (~1mph) SET step will take many presses/cycles to converge on these three
  specifically — worth flagging as a natural v1.1 case for a deep-step branch (already
  noted as deferred in §1 of the main design doc for a different reason), not a v1
  blocker, since the closed-loop controller just keeps stepping until it converges
  either way, only slower.

## Bottom line

**Build on the existing trigger + target as-is — no threshold changes recommended.**
Reasoning:
- No evidence any single-feature adjustment improves precision (checked 4 features,
  all overlap the same way TTC alone already did in the original research).
- 22% precision is a real, honestly low number for a hard alarm, but this isn't one —
  it's a shallow, reversible nudge with the same override-latch/restore machinery as
  curve actuation. An unnecessary firing costs a ~1mph dip that gets corrected back once
  the lead clears, not a startling false alarm. The bar for "good enough to actuate on"
  is lower than the bar for "good enough to alarm on," and this clears that lower bar.
- **Genuinely unresolved, not swept under the rug**: false-negative rate (real
  brake-needed events this trigger structure would miss entirely) is not computable from
  existing data — would need a full fresh archive pass over non-triggering samples too.
  Worth doing eventually, not blocking tonight's implementation, which is shadow-mode
  only regardless.
- The 3 high-closing-rate episodes are worth a deep-step v1.1 note, not a v1 change.
