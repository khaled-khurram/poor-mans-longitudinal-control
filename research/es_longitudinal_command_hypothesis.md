# Is `ES_Distance.Cruise_Throttle` a real longitudinal *command* on preglobal? — passive archive validation design (2026-08-06)

> **Status: hypothesis + pre-registered test design + a runnable-but-never-run script.**
> Nothing here has been executed against real data (this environment has no archive
> and no device access, by design — see `claude.md`). Nothing here transmits.
> Script: `research/es_longitudinal_command_correlation.py`.

---

## 1. The hypothesis

`ES_Distance` (`0x161`) on Subaru preglobal carries a 12-bit `Cruise_Throttle` field at
bits `0|12`. openpilot **already rebuilds and re-transmits this entire message on the main
bus at 20Hz on this car, every drive**, copying `Cruise_Throttle` verbatim from the camera.

**H1:** on preglobal, `Cruise_Throttle` is a *command* that the engine ECU obeys while
EyeSight ACC is engaged — with the same or a similar encoding to Subaru **global**, where
openpilot's production longitudinal control writes exactly this field.

**H1a (stronger, and separable):** the global constants transfer numerically —
`THROTTLE_MIN=808`, `THROTTLE_INACTIVE=1818` ("zero acceleration"),
`THROTTLE_MAX=3400`, `THROTTLE_ENGINE_BRAKE=808`.

The same command-vs-report question applies to the other two members of what global treats
as its command trio, and they are judged **separately** — H1 can be true while H2 and H3
are false, and vice versa:

**H2:** `ES_Brake.Brake_Pressure` (`0x160`, bits `0|16`) is a decel *command*, encoded as
in global (`BRAKE_MAX=600` ≈ `-3.5 m/s²`, i.e. `-0.005833 m/s²` per count).

**H3:** `ES_Status.Cruise_RPM` (`0x162`, bits `16|16`) is an RPM *command* to the ECM/TCM,
as global's DBC comment describes it (`"ES RPM output for ECM and TCM"`), rather than a
report. **There is direct documented counter-evidence against H3 specifically** — see §2.5.

If H1 holds, openpilot gains continuous proportional throttle authority on this car by
writing a field it already transmits — no panda firmware change, no bus contention, no
new message. H2 and H3 have no such property: neither message is TX-allowed on preglobal
(§2.6), so even a confirmed H2/H3 would require a firmware change to use.

**Null / kill hypothesis H0:** the field is a *report* — EyeSight echoing back a
powertrain value it read (or publishing an internal number nothing acts on). Writing it
would do nothing, or would fault something.

> **Before believing any number this design produces:** the script has never been run
> (§5 G10). Run T0's census first and confirm it finds the expected messages on the
> expected buses with a plausible amount of ACC-engaged driving. Every downstream test is
> worthless if T0 is empty or surprising, and an empty test is **INCONCLUSIVE, not a KILL**.

---

## 2. What is actually verified in real source (read directly, this session)

Everything in this section was read out of the real files, not recalled. Source of truth:
a clone of `commaai/opendbc` at `a3ed7d1`, plus its full git history.

### 2.1 The DBC (`opendbc/dbc/generator/subaru/_subaru_preglobal_2015.dbc`)

```
BO_ 352 ES_Brake: 8 XXX          # 0x160
 SG_ Brake_Pressure : 0|16@1+ (1,0) [0|255] "" XXX
 SG_ Cruise_Brake_Lights : 20|1@1+ ...
 SG_ Cruise_Brake_Active : 22|1@1+ ...
 SG_ Cruise_Activated : 23|1@1+ ...

BO_ 353 ES_Distance: 8 XXX       # 0x161
 SG_ Cruise_Throttle : 0|12@1+ (1,0) [0|4095] "" XXX
 SG_ Cruise_Brake_Active : 20|1@1+ ...
 SG_ Cruise_Button : 48|3@1+ ...

BO_ 354 ES_Status: 8 XXX         # 0x162
 SG_ Cruise_RPM : 16|16@1+ (1,0) [0|65535] "" XXX
```

The `0x140 Throttle` message (engine's own report, main bus) carries `Throttle_Pedal 0|8`,
`Engine_RPM 16|14`, `Throttle_Cruise 32|8`, `Throttle_Combo 40|8`, `Throttle_Body 48|8`.

**Note the field-name collision that makes this whole area confusing:** `0x140` has
`Throttle_Cruise` (engine's report) and `0x161` has `Cruise_Throttle` (EyeSight's field).
Different messages, different directions, near-identical names.

### 2.2 openpilot already owns `0x161` on the main bus, today, on this car

`opendbc/car/subaru/carcontroller.py`, preglobal branch — runs unconditionally, with no
`openpilotLongitudinalControl` gate:

```python
if self.CP.flags & SubaruFlags.PREGLOBAL:
  if self.frame % 5 == 0:
    ...
    can_sends.append(subarucan.create_preglobal_es_distance(self.packer, cruise_button, CS.es_distance_msg))
```

`subarucan.create_preglobal_es_distance()` copies `Cruise_Throttle` (and `Car_Follow`,
`Cruise_Brake_Active`, `Standstill`, `Close_Distance`, `Cruise_Fault`, **and `COUNTER`**)
verbatim from `es_distance_msg`, overwrites only `Cruise_Button`, then recomputes
`Checksum` via `subaru_preglobal_checksum()` (sum of all bytes except byte 7, mod 256).

`opendbc/safety/safety.h` `safety_fwd_hook()` blocks forwarding of any `check_relay`
TX message toward its destination bus. `subaru_preglobal.h` marks `ES_Distance` on the
main bus `.check_relay = true`. **So while openpilot is running, the camera's own `0x161`
never reaches the main bus — the engine ECU sees only openpilot's rebuilt copy.** That is
the single most important enabling fact for H1, and it is already true today.

### 2.3 The panda has no value check on this message

`subaru_preglobal_tx_hook()` checks **only** `ES_LKAS` (steer torque limits). `ES_Distance`
passes the allowlist (`{MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true}`)
with **no bounds check on any field**. If H1 is true, openpilot's preglobal safety mode
currently transmits an unbounded longitudinal-authority field at 20Hz with zero limits.
That is a finding in its own right, independent of whether we ever use it.

### 2.4 Global's constants (verbatim, `opendbc/car/subaru/values.py`)

```
THROTTLE_MIN = 808;  THROTTLE_MAX = 3400
THROTTLE_INACTIVE     = 1818   # corresponds to zero acceleration
THROTTLE_ENGINE_BRAKE = 808    # while braking, eyesight sets throttle to this, probably for engine braking
BRAKE_MIN = 0;  BRAKE_MAX = 600   # about -3.5m/s2 from testing
RPM_MIN = 0;  RPM_MAX = 3600;  RPM_INACTIVE = 600
```

**These are global numbers on a global bit layout.** Global's `Cruise_Throttle` is
`16|13` (13 bits, starting at bit 16); preglobal's is `0|12` (12 bits, starting at bit 0).
Different width, different position. The constants transferring is an *assumption* (H1a),
tested separately below, and H1 can be true while H1a is false.

### 2.5 DBC provenance — real, checkable, and it cuts **both ways**

This matters because the obvious objection is "the preglobal names were just copied from
global by analogy." They were not — the direction of copying is the opposite, and the
history is verifiable:

| commit | date | author | what it shows |
|---|---|---|---|
| `608caba6` "Create subaru_outback_2015_eyesight.dbc (#137)" | 2019-01-27 | Bugsy | The **original** preglobal reverse-engineering names `BO_ 353 ES_CruiseThrottle` with `SG_ Throttle_Cruise : 0|12`, `BO_ 354 ES_RPM` with `SG_ RPM : 16|16`, `BO_ 352 ES_Brake` with `SG_ Brake_Pressure : 0|16`. Predates all Subaru longitudinal work. |
| `608caba6` (same file) | 2019-01-27 | Bugsy | Also contains `CM_ SG_ 354 RPM "20hz version of Transmission_Engine under Transmission";` |
| `2ade6eeb` "Subaru DBC update (#242)" | 2020-05-28 | martinl | On **global**, replaces `CM_ SG_ 545 ES_Cruise_Throttle "signal might be smaller, values do not correlate with Throttle:CruiseThrottle"` with `CM_ SG_ 545 Cruise_Throttle "RPM-like output signal"`, and adds `CM_ SG_ 546 Cruise_RPM "ES RPM output for ECM and TCM"`. |
| `2bab99fd` "Subaru signals update (#474)" | 2021-12-15 | martinl | Renames **preglobal** `ES_CruiseThrottle`→`ES_Distance` and `Throttle_Cruise`→`Cruise_Throttle`, to match global naming. (This is why `subaru_preglobal.h` still carries the stale comment `// 0x161 is ES_CruiseThrottle`.) |

**Supporting reading:** the person who first reverse-engineered *this* car's bus, in 2019,
looked at `0x161` and called the whole message "ES CruiseThrottle" — i.e. believed the
EyeSight camera was emitting a cruise throttle. Independently, the global work found that
the ES throttle field does **not** correlate with the engine's own `Throttle:Throttle_Cruise`
(a report-vs-command distinction, recorded in a comment that was later replaced by
"RPM-like output signal" / "ES RPM output for ECM and TCM" — "output" being the operative
word).

**Counter-reading, from the same 2019 file:** `CM_ SG_ 354 RPM "20hz version of
Transmission_Engine under Transmission"` is a direct statement that `0x162`'s RPM field on
preglobal is a **duplicate of another message's engine-RPM report**. That comment survives
to this day (orphaned — the signal was renamed `Cruise_RPM`, the comment still says `RPM`).
If it is accurate, then at least one of the three "global command trio" fields is a report
on preglobal, and the "same trio" framing is already partly wrong. **This is directly
testable and is test T2 below.** It is the single most concrete piece of counter-evidence
available before touching any data, and it deserves to be tested first rather than
explained away.

### 2.6 What is NOT available on preglobal (kills the "same trio" framing)

- `subaru_preglobal.h` `SUBARU_PG_TX_MSGS` contains **only** `ES_Distance` and `ES_LKAS`.
  `ES_Brake` (`0x160`) and `ES_Status` (`0x162`) are **not TX-allowed**. Writing brake or
  RPM would require a panda firmware change — exactly the boundary the project has so far
  refused to cross (Q5).
- `opendbc/car/subaru/carstate.py` only populates `es_brake_msg` / `es_status_msg` /
  `cruise_control_msg` inside the **non-preglobal** branch. On preglobal, openpilot does
  not even keep a copy of `ES_Brake`/`ES_Status` to rebuild from.

So the honest version of the premise is: **one of the three global command fields is
already transmitted by openpilot on preglobal — the throttle one. The other two are not,
and cannot be without a firmware change.** Throttle-only means acceleration authority plus
whatever engine braking `THROTTLE_MIN` buys, and **no service-brake authority at all** —
which is the half this project actually needs for curves and lead vehicles.

### 2.7 The strongest supporting fact already in this project's own history

Q6 (progress.md) established, on real telemetry, that a **software-commanded**
`Cruise_Button = 2` inside openpilot's rebuilt `0x161` frame produced a real ECU-level ACC
engagement with a correct captured set speed. That means some ECU on the main bus already
**acts on openpilot-authored content of this exact message**. The channel is proven
writable-and-obeyed for one field of `0x161`. That materially raises the prior on H1 — it
is a different and much better starting point than `CruiseControl` (`0x144`) ever had.

### 2.8 Prior art: two people already wrote these fields on preglobal cars, and it faulted

A parallel research pass — `research/preglobal_longitudinal_command_archaeology.md`
(2026-08-06) — recovered first-hand accounts and live code from two preglobal owners who
wrote this exact trio in 2020. **That document is the primary source for this subsection;
the claims below are its findings, not independent verification by this pass.** It changes
the prior substantially, in both directions, and it is why T2's sign rule and T2b exist at
all.

**What it supports:**
- Both fields are described first-hand as *"generated by ES and consumed by ECU"*, and
  `Cruise_RPM` as *"controls engine rpm"* — i.e. commands, on preglobal specifically.
- One owner's 2015 Outback code used **`throttle = actuators.gas * 2048 + 1818`** and
  **`throttle = 808`** when disengaged. The 1818 / 808 anchors match global's
  `THROTTLE_INACTIVE` / `THROTTLE_ENGINE_BRAKE` exactly. That is real supporting evidence
  for H1a's *anchors* (though his span, 2048, and brake range, 1024, differ from global's
  3400 / 600 — so H1a's *range* stays unverified).
- Writing `Cruise_RPM`, once TX-allowlisted, demonstrably reached the wire and did
  something ("Ok it worked" / "half of accel").

**What it undercuts — and this is the important half:**
- The summary verdict from the community at the time: *"bugsy tried that and eyesight
  faults when you just try to rewrite throttle and brake values."*
- A second owner blocking and replacing `ES_CruiseThrottle` + `ES_RPM` got a **transmission
  check-engine light**, diagnosed as EyeSight seeing its commanded RPM not matched by
  resulting wheel speed.
- The mechanism that matters most here: EyeSight *"will error if you set it to 0 and it
  doesn't hear back the same thing from `0x140`"* — i.e. **EyeSight validates its own
  commanded `Cruise_Throttle` against the ECU's echo in `Throttle` (`0x140`)
  `Throttle_Cruise`**, and faults on mismatch. This is a distinct fault path from
  checksum/counter/frequency, and getting frame construction right does not avoid it.
- Neither owner ever achieved working longitudinal control.

**Why this does not simply end the investigation.** Both 2020 attempts *replaced* EyeSight's
messages wholesale — new frames built from scratch, camera copies relay-blocked, all three
fields overwritten at once, on panda forks. None of them did the narrow thing this
hypothesis proposes: change **one field** inside the frame openpilot **already** rebuilds
and transmits, leaving every other field, the counter and the checksum as EyeSight
produced them. That is a materially smaller perturbation, and it is the one configuration
nobody in the recovered record tried. It may still fault for exactly the reason above —
but "it faulted when done a different, larger way" is weaker evidence than it first looks.

**What it changes about this design:** T2's sign rule (§4.2) and T2b exist *because* of the
`0x140` cross-check finding. Without it, a perfect ECU-echo correlation would have been
scored as a KILL. Archive data can now test that specific documented loop directly, before
anyone writes anything — which is a strictly better position than either 2020 attempt was in.

---

## 3. The test design

All tests run on the already-synced local rlog archive. Regime gating is done from **raw
CAN only** (`CruiseControl` `0x144` bits 48/49, `Throttle` `0x140` byte 0, `Brake_Pedal`
`0xD1`), never from openpilot's `carState.cruiseState`, so results do not depend on
openpilot's own engagement state. `carState.aEgo` / `vEgo` are used only as vehicle-motion
references.

**Lag convention throughout: `tau > 0` means the ES field LEADS the response** — we compare
`ES(t)` against `response(t + tau)`.

| # | Test | Question | Mechanism |
|---|---|---|---|
| T0 | census / power | Is there enough ACC-engaged data to test anything? | per-(addr,bus) frame counts, per-regime tick counts |
| T1 | ACC-off behaviour | While ACC is **off**, EyeSight has no longitudinal authority, so anything it emits then cannot be a command being obeyed. Does `Cruise_Throttle` track the engine, or sit pinned? | per-regime value histograms |
| T2 | **exact-copy (the kill test)** | Is any ES field an exact/affine copy of a powertrain report **at a lag ≤ 0**? | 3 ES fields × 16 report fields × 9 lags; streaming affine fit (R², residual RMS) + bit-exact match fraction, **fitted separately either side of zero lag** |
| T2b | **ECU cross-check** | Does `0x140 Throttle_Cruise` reproduce `Cruise_Throttle` at a **positive** lag — the ECU acknowledging a command? | the same fits, read in the command direction |
| T3 | cross-correlation | Does `Cruise_Throttle` lead or lag engine response? | first-difference normalised xcorr, ±300ms in 25ms steps |
| T4 | step events | Same question, event-wise and robust to closed-loop smoothing: isolated `Cruise_Throttle` steps → time-to-first-response in `Throttle_Body`/`Engine_RPM`/`Wheel_Torque`/`aEgo`; **and the converse** (isolated `Throttle_Body` steps → time-to-first `Cruise_Throttle` response) | 3σ-over-baseline onset detection |
| T5 | **driver gas override (the discriminator)** | Driver presses the gas while ACC is engaged — an exogenous input EyeSight did not ask for. Does `Cruise_Throttle` follow the engine up? | compare the override-window `ΔCT/ΔTB` gain against the ordinary ACC-engaged regression slope |
| T6 | EyeSight braking | Does `ES_Brake.Brake_Pressure` lead master-cylinder pressure (`0x150`), wheel brakes (`0xD2`), brake lights and `aEgo`? What does `Cruise_Throttle` do during EyeSight braking (the 808 prediction)? | onset latencies + value distributions, driver-brake episodes excluded |
| T7 | transfer curves | `accel = f(Cruise_Throttle)` and `decel = f(Brake_Pressure)` — the maps a controller would actually need | binned means over steady ACC-engaged samples |
| T8 | joint distribution | Are `(Cruise_Throttle, Cruise_RPM, Brake_Pressure)` tightly coupled? If so, writing throttle **alone** produces a triple the ECM has never seen. | coarse 3-D histogram |
| T9 | relay fidelity | How faithful is openpilot's existing rebuild of `0x161`, and how often does its verbatim-copied `COUNTER` duplicate or skip? | bus-0 vs bus-2 comparison, counter-step histogram, delay distribution |

### 3.1 The exact signals correlated, and why each one

**The three fields under test (all EyeSight-originated, read on the camera bus, src 2):**

| signal | msg / bits | why |
|---|---|---|
| `Cruise_Throttle` | `0x161` `0\|12` | H1. The whole point: openpilot already re-transmits it verbatim. |
| `Brake_Pressure` | `0x160` `0\|16` | H2. The decel half. Read passively even though it can't be written today. |
| `Cruise_RPM` | `0x162` `16\|16` | H3, and the best available *negative control*: if the 2019 DBC comment is right this one **is** a report, so it should trip K1 while `Cruise_Throttle` does not. A test design that can't produce a KILL on anything is not a test. |

**Powertrain reports they are correlated against (main bus, src 0) — the K1 "is it just an
echo of something" candidate set.** The logic: EyeSight can only echo a value that exists
somewhere on the bus it can see, so the candidate set must be *exhaustive over the
plausible sources*, not cherry-picked.

| signal | msg / bits | why this one |
|---|---|---|
| `Throttle_Cruise` | `0x140` `32\|8` | The single most likely echo source — the engine's *own* cruise-throttle report. Global's DBC once carried an explicit note that its ES throttle field does **not** correlate with this (§2.5); the mirror test on preglobal is the direct analogue. |
| `Throttle_Body` | `0x140` `48\|8` | Actual throttle-plate position: the physical thing a throttle command would move. Primary **response** signal for T3/T4/T5. 100Hz, the fastest response signal available. |
| `Throttle_Pedal` | `0x140` `0\|8` | Driver input. Used to *define* the T5 override regime, and as an echo candidate (if `Cruise_Throttle` tracks the pedal it is not EyeSight's demand). |
| `Throttle_Combo` | `0x140` `40\|8` | Undocumented (`"Throttle related"` is the entire DBC comment) — included precisely because an unknown field is a plausible echo source and cheap to rule out. |
| `Engine_RPM` | `0x140` `16\|14` **and** `0x141` `32\|12` | Both copies included deliberately: global calls its throttle field `"RPM-like output signal"`, so an RPM-shaped echo is the specific failure mode to check. Two different messages carry RPM at different rates/widths. |
| `Transmission_Engine` | `0x148` `16\|15` | **Named directly by the 2019 DBC comment** as what `0x162`'s RPM field duplicates. The specific pre-registered prediction in §4. |
| `Engine_Torque`, `Wheel_Torque` | `0x141` `0\|15`, `16\|12` | Torque-domain response signals — less confounded by CVT ratio changes than RPM is. |
| `Brake_Pressure_Right/Left` | `0x150` `0\|8`, `8\|8` | Master-cylinder pressure: what a *commanded* brake would cause. The H2 lead/lag reference. |
| `Right_Brake`, `Left_Brake`, `Brake_Light` | `0xD2` `48\|8`, `56\|8`, bit 35 | Second, independent brake measurement + the physical brake-light state. If EyeSight's `Cruise_Brake_Lights` **leads** the car's own brake light, EyeSight is originating the braking event. |
| `Brake_Pedal` | `0xD1` `16\|8` | Driver brake — used to *exclude* driver-braking episodes from T6, so only EyeSight-initiated braking is measured. |
| `Cruise_On`, `Cruise_Activated`, `SET/RES/OnOff` bits | `0x144` bits 48, 49, 2/3/4 | Regime gating, entirely from raw CAN. Bits 3/4 are Q4's doubly-confirmed button bits; bit 49 is what the panda itself uses for `pcm_cruise_check`. Deliberately **not** taken from `carState.cruiseState`, so the analysis is independent of openpilot's own engagement state. |
| `aEgo`, `vEgo` | `carState` | Ground-truth vehicle response for the T7 transfer curves and the slowest/most-integrated response signal for T3/T4. |
| `Longitudinal` | `0xD0` `48\|16` | Accelerometer cross-check on `aEgo`. **Scale and sign unverified** (§5 G7) — used only qualitatively. |

**Deliberately excluded:** `CVT_Ratio` (`0x149`) has **zero decoded signals** in the DBC, so
the "engine RPM jumped for transmission reasons" confound cannot be measured directly and is
not implemented. See §5 G7.

### Why T5 is the load-bearing test

T3/T4 are confounded: in a closed loop, a *report* generated slightly ahead of the
measured response (e.g. echoed from a faster internal signal) can look leading, and a
*command* smoothed by actuator dynamics can look nearly simultaneous. T5 breaks the loop
with an input EyeSight did not generate. If `Cruise_Throttle` rises with a driver-caused
engine rise at its ordinary gain, it is an echo. If it stays flat or moves the other way
(EyeSight's demand should *fall* — the car is now going faster than asked), it is EyeSight's
own independent demand.

### Why T9 is worth the cheap effort

`create_preglobal_es_distance()` copies the camera's `COUNTER` **verbatim** while
re-transmitting on openpilot's own 20Hz clock. Two independent 20Hz clocks means the
main-bus counter must already duplicate and skip regularly. T9 quantifies how much of that
the receiving ECU has silently tolerated for years of driving — directly relevant to the
Q9 finding that *EyeSight* fault-checks message consistency, since here the receiver is the
ECM, not EyeSight.

---

## 4. Pre-registered CONFIRM / KILL criteria

These are fixed in code in the `PREREG` dict at the top of
`es_longitudinal_command_correlation.py`, and the script's `verdicts()` applies them
mechanically. **Do not tune them to make a result come out.** If one turns out to be
wrong, say so explicitly in the writeup and re-register it — do not silently edit.

They were written down **before any archive output existed** — the only data any of these
thresholds has ever been checked against is synthetic signals with known ground truth
(§5 G10). That is the whole point of pre-registering: the numbers below cannot have been
reverse-engineered from the answer, because at the time of writing there was no answer.

### 4.1 Per-test criteria, T0–T9

Every threshold below is the literal value of the named `PREREG` key.

| test | decides | CONFIRM-side | KILL-side | `PREREG` keys |
|---|---|---|---|---|
| **T0** census / power | whether any other test is admissible | ≥ 20,000 `acc_engaged_clean` ticks, ≥ 100 step events, ≥ 30 override events, ≥ 50 brake events | *(none — T0 cannot kill anything)* below threshold ⇒ that test is **INCONCLUSIVE** | `min_acc_engaged_ticks`, `min_isolated_step_events`, `min_override_events`, `min_brake_events` |
| **T1** ACC-off behaviour | is the field gated on control authority | distribution ACC-engaged materially differs from ACC-off (C5) | field behaves identically in both regimes and tracks the engine in both (**K4**) | judged against T2's fits per regime |
| **T2** exact-copy | **the kill test** — is it an echo | no report field reproduces `es_cruise_throttle` in the **echo (lag ≤ 0)** direction (C1) | ≥ **99%** bit-exact **or** affine R² ≥ **0.999** with residual ≤ **1 LSB**, **best at lag ≤ 0** (**K1**) | `report_exact_match_frac`, `report_affine_r2`, `report_affine_resid_lsb` |
| **T2b** ECU cross-check | is the ECU acknowledging a command | `throttle_cruise` reproduces `es_cruise_throttle` best at **lag > 0** ⇒ command confirmed **and** the documented EyeSight fault loop is real | *(cannot kill H1 — a failure here is merely uninformative)* | same three keys, read on the command side |
| **T3** cross-correlation | lead vs lag, aggregate | xcorr peak vs `throttle_body` at **tau ≥ +40ms** (C3) | peak at **tau ≤ 0** | `confirm_min_lead_ms`, `kill_lead_ms` |
| **T4** step events | lead vs lag, event-wise | median `Cruise_Throttle`-step → `Throttle_Body` latency **≥ 40ms and ≤ 600ms**, in **≥ 80%** of isolated events (C2) | forward median ≤ 0 **and** converse test shows engine steps precede ES responses (**K2**) | `confirm_min_lead_ms`, `confirm_max_lead_ms`, `confirm_lead_event_frac`, `kill_lead_ms` |
| **T5** gas override | **the discriminator** | relative gain ≤ **0.25** **and** ≤ **50%** of events same-sign as engine (C4) | relative gain ≥ **0.75** **and** ≥ **80%** same-sign (**K3**) | `confirm_override_gain_ratio_max`, `confirm_override_same_sign_max_frac`, `kill_override_gain_ratio_min`, `kill_override_same_sign_min_frac` |
| **T6** EyeSight braking | H2, plus the 808 prediction | `ES_Brake.Brake_Pressure` onset **leads** `0x150` master-cylinder pressure and the physical brake light; `Cruise_Throttle` collapses during braking | `ES_Brake` **lags** `0x150` ⇒ H2 dead by the same logic as K1/K2 | `confirm_min_lead_ms`, `kill_lead_ms` |
| **T7** transfer curves | H1a / H2 encoding | ACC-engaged mode within **±5%** of 1818 holding **≥ 10%** of samples; floor ≈ 808 with < 1% below; ceiling ≤ ~3400; braking median within ±5% of 808; brake slope within **2×** of `-0.005833 m/s²/count` | *(cannot kill H1)* — failure kills **H1a only**, and must be reported that way | `encoding_mode_tol_frac`, `encoding_min_mode_frac`, `brake_slope_tol_frac` |
| **T8** joint distribution | write-safety risk, not truth | the three fields vary independently ⇒ throttle-only writes stay in-distribution | tight coupling ⇒ a throttle-only write is a combination the ECM has **never seen**; raises live-test risk, does not decide H1 | *(descriptive; no threshold)* |
| **T9** relay fidelity | how much the ECM tolerates | `Cruise_Throttle` on bus 0 matches bus 2 ~100%; counter duplicates/skips already common with no known fault | bus-0 copy diverges unexpectedly ⇒ the premise "openpilot already transmits this verbatim" is wrong and §2.2 must be re-derived | *(descriptive; no threshold)* |

**Precedence rule, fixed in advance:** T2 (K1) outranks everything. If `Cruise_Throttle`
is demonstrably an affine copy of a powertrain report, no amount of favourable lead/lag
from T3/T4 rescues H1 — a copy generated slightly early still isn't a command. Conversely
T0 outranks T2: a test with no data returns INCONCLUSIVE and may not be reported as a KILL.

### Gate 0 — statistical power (checked first, blocks everything else)

- ≥ 20,000 `acc_engaged_clean` 20Hz ticks (~17 min of clean ACC driving)
- ≥ 100 isolated step events, ≥ 30 usable gas-override events, ≥ 50 EyeSight brake events

Below these, the corresponding test reports **INCONCLUSIVE — not KILL.** A test that
didn't run is not evidence of absence. (This gate is a real risk: the archive is dominated
by openpilot-lateral driving, and there is no prior measurement of how much *stock ACC*
driving it contains.)

### 4.2 KILL — H1 is dead if **any** of these hold

| K# | Criterion |
|---|---|
| K1 | `es_cruise_throttle` matches some powertrain report field ≥ **99% bit-exact**, **or** with affine R² ≥ **0.999** and residual RMS ≤ **1 LSB** — **and that match is best at a lag ≤ 0**, i.e. the ES field reproduces what the report *already was*. See the sign rule below; without it this criterion is wrong. |
| K2 | T4 converse: engine steps are followed by `Cruise_Throttle` responses at a **negative or zero** median latency, and T4a's forward median latency is **≤ 0** — i.e. the engine consistently moves first. |
| K3 | T5: override relative gain ≥ **0.75** of the baseline slope **and** ≥ **80%** of override events move `Cruise_Throttle` in the same direction as the driver-caused engine rise. |
| K4 | T1: during **ACC-off manual driving**, `Cruise_Throttle` tracks engine throttle/RPM with the same relationship it has when ACC is engaged. (EyeSight has no authority then; a field that behaves identically in both regimes is not gated on control authority.) |

**The K1 sign rule — the correction that keeps K1 from being wrong.** A tight match on its
own means nothing, because *a command that the ECU obeys or acknowledges also produces a
near-perfect copy* — just displaced the other way in time. The lag sign is the entire
discriminator:

| best-fit lag | reading |
|---|---|
| **≤ 0** — `ES(t)` reproduces what the report **already was** | **ECHO ⇒ K1 fires, H1 dies** |
| **> 0** — `ES(t)` reproduces what the report **becomes later** | **COMMAND, and the ECU is reproducing it ⇒ strong CONFIRM, not a kill** |

This is not a hypothetical distinction. First-hand preglobal accounts describe EyeSight
cross-checking its commanded `Cruise_Throttle` against the ECU's echo on `0x140`
(§2.8), and describe `Cruise_RPM`'s "request tracing with the transmission message" —
both of which are *tight copies in the command direction*. A sign-blind K1 would have
converted the single strongest available confirmation into a false KILL. The script
therefore fits each pair **separately on each side of zero lag** and only fires K1 when
the echo-side fit is both good enough and better than the command-side fit. Verified on a
synthetic ECU-echo case (perfect R² = 1.0 at +100ms): correctly classified as
command-with-echo, `is_report_by_prereg = False`.

**With that rule applied, the single cleanest outright kill is still K1**, and it is the
cheapest to reach: if a powertrain report reproduces `Cruise_Throttle` to within 1 LSB
*in the echo direction*, EyeSight is repeating a number the engine already published, and
the hypothesis dies in one line of output. Everything else in this design exists because
K1 is expected to *fail*, at which point the question becomes harder and needs T5.

**H2 / H3 kill conditions** (same logic, judged independently of H1):
- **H2 dead** if `ES_Brake.Brake_Pressure` trips K1 against `0x150`/`0xD2` brake pressure,
  or if T6 shows it consistently *lagging* master-cylinder pressure.
- **H3 dead** if `ES_Status.Cruise_RPM` trips K1 against `Transmission_Engine` (`0x148`) or
  either `Engine_RPM` copy. **This is the pre-registered expected outcome** (§4.3) — it
  would confirm the 2019 DBC comment and is the result this design is most confident about.

### CONFIRM — H1 is supported (never "proven", see §5) if **all** of these hold

| C# | Criterion |
|---|---|
| C1 | K1 fails for `es_cruise_throttle` — no powertrain report reproduces it. |
| C2 | T4a: median latency from `Cruise_Throttle` step to `Throttle_Body` response is **≥ 40ms and ≤ 600ms**, in **≥ 80%** of isolated events. (40ms floor = one 20Hz frame + bus latency; the ES stream is 20Hz so timing is quantised to ±25ms.) |
| C3 | T3: xcorr peak for `es_cruise_throttle` vs `throttle_body` at **tau ≥ +40ms**. |
| C4 | T5: override relative gain ≤ **0.25** **and** ≤ **50%** of events same-sign as the engine. |
| C5 | T1: `Cruise_Throttle` is materially different in distribution between ACC-engaged and ACC-off (gated on control authority). |

### H1a (global encoding transfers) — judged separately

- CONFIRM H1a if, ACC-engaged: a real mode (≥10% of samples) within ±5% of **1818**; observed
  floor at/near **808** with < 1% of samples below it; ceiling ≤ ~**3400**; and during
  EyeSight braking episodes the median `Cruise_Throttle` collapses to within ±5% of **808**.
- If the distribution is structured but centred on *different* numbers, that **kills H1a
  and leaves H1 intact** — it means the encoding must be measured on preglobal, not
  inherited. This distinction must be reported explicitly; conflating them is the most
  likely way this analysis gets misread.
- Brake scaling (H1a for `ES_Brake`): measured `aEgo` per `Brake_Pressure` count within 2× of
  global's `-3.5/600 = -0.005833 m/s²/count`.

### 4.3 The pre-registered expected outcome (recorded before seeing any data)

`ess_cruise_rpm` (`0x162`) tripping **K1 against `trans_engine`** (`0x148` `Transmission_Engine`),
i.e. confirming the 2019 DBC comment. Pre-registered prediction: **this is more likely than
not.** If it happens it does *not* kill H1 for the throttle field, but it does kill the
"preglobal has the same command trio as global" framing, and it should sharply lower
confidence that global's architecture maps onto preglobal at all. Recording this
prediction *before* seeing the data is the point.

---

## 5. Honest gaps — what this can never show, and where it can mislead

**G1 — the identifiability ceiling (the fundamental one).** Archive data can show that
`Cruise_Throttle` is EyeSight-originated, independent of powertrain reports, and leading
the engine's response. It **cannot** show that the ECM obeys it. Every sample in the
archive is EyeSight's own value, perfectly consistent with everything else EyeSight emits
at that instant. "EyeSight commands the engine via `0x161`" and "EyeSight commands the
engine some other way and *also* publishes its internal demand on `0x161`" produce
**identical** archive signatures. Only a live write separates them. A full CONFIRM here
raises the prior; it does not close the question.

**G2 — the strongest counter-argument** (see §6): a clean CONFIRM on every test here is
still compatible with the live write faulting EyeSight, because the tests measure whether
the field *is* a command, not whether EyeSight tolerates someone else issuing it. No
archive analysis can close that gap.

**G2b — this pass did not independently verify §2.8.** The first-hand accounts, the 2020
branch code and the community quotes in §2.8 come from
`research/preglobal_longitudinal_command_archaeology.md`, produced by a separate research
pass. I read that document, not its underlying Discord exports or the recovered branches.
Its own caveats (including that the Wayback Machine was unreachable and that one scaling
data point is inferred from someone's 2020 code rather than measured) carry over. Given
this project's history with fabricated research, treat §2.8 as second-hand until spot-checked
against `discord-logs/` directly — the quotes are attributed with dates and are checkable.

**G3 — statistical power is unmeasured.** How much *stock ACC-engaged* driving the archive
contains has never been quantified. Q4 found 412 button events and Q6/Q10 confirm real ACC
use, so it is not zero — but T5 needs gas-override-while-ACC-engaged events specifically,
which may be rare, and it is the load-bearing test. Run T0 first and report the counts
before interpreting anything.

**G4 — throttle-only is half a controller.** Even a full CONFIRM gives acceleration
authority and engine-brake authority, not service-brake authority. `ES_Brake` is not
TX-allowed on preglobal and preglobal `carstate.py` doesn't even retain the message.
The project's actual use cases (slow for a curve, slow for a lead) are the *decel* half.

**G5 — cross-message consistency risk is only partly testable.** T8 measures what
`(throttle, RPM, brake)` combinations the ECM has historically seen. If they're tightly
coupled, writing throttle alone creates a novel combination. T8 can flag that risk; it
cannot tell us whether the ECM validates it.

**G6 — grade contaminates the transfer curve.** `aEgo` is wheel-speed-derived and includes
road grade; no grade estimate exists in this data. T7's *shape and monotonicity* are
robust; its absolute m/s²-per-count is biased by whatever grade distribution the archive
happens to contain. Do not tune a controller off T7 numbers alone.

**G7 — unverified decodes, flagged explicitly.**
- `G_Sensor` (`0xD0`) `Longitudinal` scale `-0.00035` and its sign convention are not
  verified against anything; used only as a loose cross-check on `aEgo`.
- `ES_Brake.Brake_Pressure` is declared `0|16@1+` with a value range of `[0|255]` — the DBC
  is internally inconsistent. 16 bits assumed.
- `CVT_Ratio` (`0x149`) has **zero decoded signals** in the DBC, so the "does engine RPM
  jump for transmission reasons while the ES field doesn't" test is **not implemented**.
  A future pass could use `Engine_RPM / vEgo` as a ratio proxy.
- `Throttle_Combo` / `Throttle_Body` semantics are guesses inherited from the DBC
  (`CM_ SG_ 320 Throttle_Body "Throttle related"` — that is the entire documentation).

**G8 — the 20Hz ES rate quantises every timing result to ±25ms.** The 40ms CONFIRM floor
exists for this reason. Single events prove nothing; only the distribution over ≥100 events
does.

**G9 — selection effect in T6.** Only EyeSight-braking episodes with *no* driver brake are
usable. If EyeSight rarely brakes hard, the brake transfer curve is sampled only at low
pressures and cannot be extrapolated to `BRAKE_MAX`.

**G10 — the script has never been run.** It was written without archive access. Its
decoders were unit-checked against hand-computed bit extractions, and its four
discriminators (T2/T3/T4/T5) were validated end-to-end on **synthetic** command-mode and
report-mode signals where the ground truth was known: the command case produced
xcorr peak `+200ms`, T4a median `+100ms` with 100% of responses after the step, and no
report-classification; the report case produced xcorr peak `-50ms`, T4a median `-80ms`
with 0.7% after, T4b ES-response at `-50ms`, and a correct K1 report-classification. That
validates the *machinery*, not the *conclusion*. Sanity-check T0's census before trusting
any downstream number.

**G11 — T9's null result is weak evidence.** If openpilot's copied `COUNTER` already
duplicates/skips constantly with no observed fault, that suggests the ECM doesn't hard-check
it. But absence of a fault for years is not proof of absence of checking — the ECM may
tolerate counter anomalies while still validating value plausibility or cross-message
consistency.

---

## 6. The strongest counter-argument, stated as strongly as I can make it

**The likeliest failure is not that `Cruise_Throttle` is inert — it is that it is a real
command inside a loop EyeSight is watching, so writing it faults EyeSight rather than
moving the car.**

This is the counter-argument to beat, and it is *empirical*, not speculative. Per §2.8:
EyeSight is reported to validate its own commanded `Cruise_Throttle` against the ECU's
echo on `0x140 Throttle_Cruise` and *"will error if you set it to 0 and it doesn't hear
back the same thing from `0x140`"*. If openpilot writes a different value, the ECU's echo
necessarily stops matching what EyeSight commanded — and EyeSight, still fully alive on the
camera bus and still running its own loop, sees a discrepancy it is designed to fault on.
Two preglobal owners writing these fields in 2020 hit exactly that class of failure (an
EyeSight fault; a transmission CEL), and neither ever got working longitudinal control.

Note how this interacts with the rest of the design: **this failure mode is fully
compatible with a clean CONFIRM on every test here.** C1–C5 can all pass, T2b can light up
positively, and the live write can still fault the car — because the tests measure whether
the field *is* a command, and the fault is about whether EyeSight *tolerates someone else
issuing it*. Q9 already taught this project the same lesson at the vehicle-system level:
EyeSight actively validates consistency and protects itself, and a clean software-level
measurement is not a prediction of the physical outcome.

There is also a real precedent asymmetry worth sitting with: this is a two-line change,
and multiple competent people — martinl, jnewb1, two preglobal owners, a funded $2,550
bounty — worked this exact problem across 2020–2023 without landing it. The strong prior
is that the simple version doesn't work. The honest counter to *that* is narrow but real:
nobody in the recovered record tried the minimal perturbation (one field changed inside
the frame openpilot already rebuilds, everything else EyeSight's own). Everyone replaced
the messages wholesale.

**A weaker, secondary counter-argument** (kept because the archive can test it and it was
not fully ruled out): the ECM may run the speed loop itself, with EyeSight supplying only a
limit/request it arbitrates. `0x144 CruiseControl` carries `Cruise_On`/`Cruise_Activated`
and the physical button bits; `0x140` carries its own `Throttle_Cruise`; `0x360` carries
`Saved_Speed` and yet another `Cruise_Activated`. Under that architecture `Cruise_Throttle`
would still be EyeSight-originated, independent, and leading — passing C1–C3 — while being
non-authoritative. §2.8's first-hand *"generated by ES and consumed by ECU"* argues against
it, but that is one person's recollection, not a measurement.

Three things sharpen the overall picture:

1. **The 2019 DBC comment — but read it carefully now.** The person who reverse-engineered
   this bus documented `0x162`'s RPM field as a *20Hz duplicate of the transmission's
   engine-RPM report*, and the same person later said `Cruise_RPM` *"controls engine rpm"*
   and that *"ES_RPM's request traces with the transmission message on the main bus"*
   (§2.8). **Both statements can be true at once** — a command the TCM obeys traces with
   the transmission's report by construction. So this is no longer clean evidence for
   "report"; it is evidence that the copy relationship exists, with the *direction*
   unresolved. That is precisely the ambiguity T2's lag-sign rule is built to settle, and
   it is the best argument for running T2 before believing anything else.
2. **Global ≠ preglobal, and the differences are not cosmetic.** Different addresses,
   different bit layouts (13-bit @16 vs 12-bit @0), different checksum algorithms, a
   different set of signals, and — decisively — upstream openpilot supports longitudinal on
   global and **explicitly excludes preglobal**, after multiple people (martinl, jnewb1,
   a funded $2,550 bounty) spent 2022-2023 trying. See
   `research/preglobal_long_fork_precedent.md`. The one approach that reportedly did work
   on preglobal was jnewb1's *"long support (no eyesight)"* — i.e. **replacing** EyeSight,
   not writing a field alongside it. If simply overwriting `Cruise_Throttle` on a live
   preglobal EyeSight worked, that is a two-line change, and it is implausible that
   everyone who worked this problem for two years missed it. **The most likely explanation
   for the absence of this trick in the wild is that it doesn't work** — and §2.8 now
   supplies a concrete mechanism for *why* it wouldn't, rather than leaving it as an
   argument from silence.
3. **Q9's lesson applies directly.** Camera-bus injection looked completely clean by CAN
   error counters and still produced a real "EyeSight Off" dash fault. A narrow
   software-level health check is not a substitute for the physical outcome. Whatever this
   analysis concludes, the live test needs a physical-symptom observer, not just telemetry.

**Counter-counter-argument, for balance:** Q6 already showed that an openpilot-authored
*field* of this exact message is acted on by a real ECU at driving speed. So the message is
not inert, openpilot is already the authoritative source of it on the main bus, and the
question is narrowly "is *this* field of *this* message also live", not "can we write this
message at all." That is a much smaller leap than `0x144` ever was.

---

## 7. What each outcome should trigger

| Outcome | Next step |
|---|---|
| **KILL** on K1 (it's an echo) | Close it. Write the result into `progress.md` as a closed question, with the matching report field named. Cheapest possible death, and worth having. |
| **KILL** on K3/K4 | Same — close it, and record that EyeSight's throttle field is not gated on control authority. |
| **INCONCLUSIVE** (gate 0 fails) | Do **not** proceed to a live test. Either mine more archive, or run a deliberate *passive* capture drive using stock ACC (gas overrides, hills, lead-car decels) — a zero-risk data-collection drive, not an actuation test. |
| **CONFIRM H1, kill H1a** | H1 alive, encoding must be measured on preglobal. T7's curves become the starting map. Still no live write yet. |
| **Full CONFIRM (H1 + H1a)** | Still not authorisation to transmit. It earns a *separate* live-test protocol, in the style of `research/es_distance_live_test_protocol_v3.md`: single-shot, gated, live-monitored over Tailscale, with a physical-symptom observer, starting from writing `THROTTLE_INACTIVE` (i.e. the value already on the wire — a no-op write that tests only whether the ECM accepts an openpilot-authored value at all), then ±small deltas, on a private road. And a panda `tx_hook` bounds check should be written **before** any non-identity value is ever sent, since §2.3 shows there is currently none. |
| **T2b lights up** (ECU reproduces `Cruise_Throttle` at positive lag) | Treat as CONFIRM *and* as a red flag simultaneously. It means the `0x140` cross-check loop of §2.8 is real on this car, so the live protocol must assume EyeSight will notice a divergent write. Design the first live step to be **identity** (write back exactly the value received) held for a sustained period — that isolates "does EyeSight fault merely because openpilot is the author" from "does EyeSight fault because the value changed", which is the single most useful bit of information available and costs nothing but a drive. |

---

## 8. Running it

```
# copy into the container that already has pycapnp + zstandard + the archive mounted
docker cp es_longitudinal_command_correlation.py <route-stats-container>:/work/
docker exec <route-stats-container> python3 /work/es_longitudinal_command_correlation.py
```

Set `RAW_DIR` / `SCHEMA_DIR` (placeholders in the file — real paths scrubbed per
`claude.md`) and start with `ROUTE_LIMIT = 5` for a smoke run to confirm the T0 census
finds `0x161/src2`, `0x160/src2`, `0x162/src2` and `0x140/src0` before committing to a
full-archive pass. Output: `es_longitudinal_command_results.json`, with a `verdicts`
block that applies §4 mechanically.
