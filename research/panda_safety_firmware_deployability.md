# Panda safety-firmware deployability on this device — can `ES_Brake`/`ES_Status` ever be TX-allowed on preglobal?

**Date:** 2026-08-06
**Scope:** answers the four questions raised by `research/eyesight_throttle_channel.md`'s
"Escalation" section and `progress.md` Q5/Q14 — is a modified panda TX allowlist deployable
on a comma 4 running a prebuilt sunnypilot `release-mici`-lineage branch; how sunnypilot
ships safety changes; what a correct patch looks like; and what it costs in safety-review
terms.

**Method:** every claim below is checked against real source in three trees, read directly:

| Tree | What it is |
|---|---|
| `commaai/opendbc` @ `a3ed7d1` | upstream opendbc/safety |
| `commaai/panda` @ `dd8a5b3` | upstream panda firmware |
| `sunnypilot/opendbc` @ `d427557` | sunnypilot's opendbc fork (contains PR #152) |
| `sunnypilot/sunnypilot` @ `af744c8` (`release-mici`, `sunnypilot v2026.002.001`) | **the exact release export this device's branch was forked from** |

That last tree is the important one — it is the same commit `progress.md` records as this
project's fork point, so its contents are the shipped artifacts, not an approximation.
Citations are `path:line` within the relevant tree.

---

## TL;DR verdict

**The panda firmware path is a SOFT blocker, and materially softer than this project has
assumed since Q5.** Four independent facts, each verified against shipped source/binaries:

1. **There is no signing wall.** The panda bootstub accepts firmware signed with a
   **private key that is published in the panda repo itself**, and the shipped bootstub on
   this device's branch is compiled with that acceptance path enabled.
2. **This device is already running debug-signed, non-comma-release panda firmware — by
   necessity.** `SAFETY_SUBARU_PREGLOBAL` is registered *only* inside `#ifdef ALLOW_DEBUG`.
   A comma release-firmware panda cannot run this car at all. Every drive this project has
   ever done was on a debug build.
3. **The panda firmware ships as a git-tracked binary on `release-mici`.** It is not built
   on device and it is not fetched from comma. It is a committed file in the branch.
4. **`pandad` re-flashes the internal panda on every boot whenever the running signature
   differs from that committed binary** — over SPI, with a software-only DFU recovery path
   if the flash fails.

Consequence: shipping modified safety firmware to this device is a **build-and-commit
problem, not a reinstall problem**. It does **not** require a factory reset, recalibration,
or torque relearn. It requires an ARM cross-compiler somewhere (a laptop or container),
committing two binaries to the fork branch, and the same `git pull` + reboot this project
already uses for every Python change.

**Is it already solved by sunnypilot? Partly, and the part that is solved is not the part
that matters here.** sunnypilot *does* ship a modified preglobal TX allowlist to end users
today — decisive, and it kills the "impossible" framing. But what they added is
`Throttle` (0x140) and `Brake_Pedal` (0xD1) **on the camera bus**, i.e. lying to EyeSight
about the driver's pedals. They did **not** add `ES_Brake` (0x160) or `ES_Status` (0x162).
There is no existing friction-brake authority to inherit.

**Cheapest real route, in order:**

- **Free, today, no build:** flip the already-compiled `SubaruStopAndGo` param. It is in
  this branch's compiled params allowlist and it *already* switches the panda to the
  expanded stop-and-go TX allowlist with zero firmware work. Useful as a live proof that
  the runtime-flag mechanism works on this car, and it is a real feature besides.
- **Cheap-ish, no device risk:** the `Cruise_Throttle` fast path from
  `eyesight_throttle_channel.md` — still the right next move, since it needs **no**
  firmware change at all.
- **Only if the above proves insufficient:** build modified panda firmware off-device and
  commit the binaries. Real work, real review burden (§4), but not a factory reset.

---

## 1. Is a modified panda safety allowlist deployable on this setup?

### 1.1 Where the panda is, and how it is reached

comma 4 is board type `cuatro` — `HW_TYPE_CUATRO = b'\x0a'`
(`panda/python/__init__.py:136`), listed in
`INTERNAL_DEVICES = (HW_TYPE_TRES, HW_TYPE_CUATRO)` (`panda/python/__init__.py:147`) and in
`H7_DEVICES`/`SUPPORTED_DEVICES` (`:144-145`). The board declares `.has_spi = true`
(`panda/board/boards/cuatro.h:118`). This confirms `progress.md` §5: the panda MCU is
integrated into the device and is spoken to over SPI, not USB. There is no removable panda
to swap.

Crucially, an internal panda can be put into DFU **purely in software**, by toggling the
STM32 `BOOT0`/`RST` GPIOs from the SoC:

```python
def recover_internal_panda(self):
    gpio_init(GPIO.STM_RST_N, True)
    gpio_init(GPIO.STM_BOOT0, True)
    ...
```
(`system/hardware/tici/hardware.py:432-441`, release-mici tree)

So a bad flash is recoverable over SSH. It is not a bricking risk in the "open the case"
sense. (Not risk-free — see §1.6.)

### 1.2 Where the firmware comes from, and how it is built

Panda firmware source lives in the `panda/` directory of the openpilot tree (it is vendored
in, not a submodule, on this release export). The safety logic itself is **not** in panda —
it is `#include`d from opendbc: `panda/SConscript:100` puts `opendbc.INCLUDE_PATH` on
`CPPPATH`, and `opendbc/__init__.py:6` resolves that to the opendbc repo root. So
`opendbc/safety/modes/subaru_preglobal.h` is compiled *into the panda binary*. Changing the
TX allowlist means rebuilding the panda firmware. This is confirmed by panda's own README:

> "panda is compiled with vehicle-specific safety logic provided by opendbc"
> (`panda/README.md:18`)

Build is scons + `arm-none-eabi-gcc` (`panda/SConscript:7` `PREFIX = "arm-none-eabi-"`,
`:137` `-mcpu=cortex-m7`), producing two artifacts per project:

- `board/obj/bootstub.panda_h7.bin` — the bootloader (`panda/SConscript:110-119`)
- `board/obj/panda_h7.bin.signed` — the signed application (`panda/SConscript:120-127`)

### 1.3 The signing model — and why it does not block anything here

`panda/SConscript:12-20`:

```python
if os.getenv("RELEASE"):
  BUILD_TYPE = "RELEASE"
  cert_fn = os.getenv("CERT")
  assert cert_fn is not None, 'No certificate file specified. Please set CERT env variable'
  ...
else:
  BUILD_TYPE = "DEBUG"
  cert_fn = File("./board/certs/debug").srcnode().relpath
  common_flags += ["-DALLOW_DEBUG"]
```

The bootstub verifies the app's RSA signature against **two** compiled-in public keys
(`panda/board/bootstub.c:66-75`):

```c
  if (RSA_verify(&release_rsa_key, ... )) {
    goto good;
  }

  // allow debug if built from source
#ifdef ALLOW_DEBUG
  if (RSA_verify(&debug_rsa_key, ... )) {
    goto good;
  }
#endif
```

The debug **private** key is committed in the repo in plaintext:
`panda/board/certs/debug` (`-----BEGIN RSA PRIVATE KEY-----`, 887 bytes). Verified byte-identical
between upstream `commaai/panda` and this device's `release-mici` tree
(sha256 `43edcfcd80ecf0be818d46be9c04320b2584f31b46bbec5d93f7f74d9c34569c` on both), as is
`debug.pub` (`98be6f5f…`). Signing is done by `panda/board/crypto/sign.py`, plain
pycryptodome RSA — and `pycryptodome` is a first-class openpilot dependency, commented
`"used in updated/casync, panda, body, and a test"` (`pyproject.toml:71`).

**So: anyone can produce a signature the bootstub will accept, provided the bootstub was
built with `ALLOW_DEBUG`.** Which brings us to the decisive check.

### 1.4 Decisive: the shipped firmware on this branch is a DEBUG build

Read directly out of the `release-mici` tree at `af744c8`:

```
$ cat panda/board/obj/version
DEV-unknown-DEBUG

$ strings panda/board/obj/bootstub.panda_h7.bin | grep DEV
DEV-unknown-DEBUG
```

The version string is `f"{BUILDER}-{git}-{BUILD_TYPE}"` (`panda/SConscript:28-33`), and
`BUILD_TYPE == "DEBUG"` is set in exactly the same `else` branch that adds `-DALLOW_DEBUG`.
Both the **app** and the **bootstub** carry it. Therefore the bootstub on this device
accepts debug-key-signed application firmware.

This is not an accident or a sloppy release. It is **required**, because:

```c
#ifdef ALLOW_DEBUG
    {SAFETY_CHRYSLER_CUSW, &chrysler_cusw_hooks},
    {SAFETY_PSA, &psa_hooks},
    {SAFETY_SUBARU_PREGLOBAL, &subaru_preglobal_hooks},
    ...
#endif
```
(`opendbc/safety/safety.h:416-423` upstream; identical at
`opendbc_repo/opendbc/safety/safety.h:416-423` in the release-mici tree)

**`SAFETY_SUBARU_PREGLOBAL` is a debug-only safety mode upstream.** A comma release-signed
panda firmware physically cannot select it. This car has never run comma release firmware
and never can. Every mile this project has driven has been on a debug-signed panda build
that comma did not sign and does not vouch for.

That single fact reframes the entire question: **this is not "should we cross the line into
custom safety firmware."** The line was crossed the day the car was installed, by
sunnypilot's own release, out of necessity. The remaining question is only *how much*
custom safety code, and who reviews it.

### 1.5 Decisive: the firmware is shipped as a committed binary, and flashed on every boot

On `release-mici`, `git ls-files panda/board/obj` returns:

```
panda/board/obj/bootstub.panda_h7.bin
panda/board/obj/panda_h7.bin.signed
panda/board/obj/panda_h7/main.elf        (+ bootstub.elf, main.bin)
panda/board/obj/cert.h
panda/board/obj/version
... (jungle and body equivalents)
```

These are real binaries (98,528 bytes for `panda_h7.bin.signed`), not Git-LFS pointers —
the tree has no `.gitattributes`. Note this directory is `.gitignore`d in upstream panda
(`obj/`); the release export force-adds it. This is the panda-side twin of the
`prebuilt` marker file that `progress.md` §11 already identified.

At boot, `pandad` compares signatures and flashes if they differ:

```python
def get_expected_signature() -> bytes:
  fn = os.path.join(FW_PATH, McuType.H7.config.app_fn)
  return Panda.get_signature_from_firmware(fn)
...
  if panda.bootstub or panda_signature != fw_signature:
    cloudlog.info("Panda firmware out of date, update required")
    panda.flash()
```
(`selfdrive/pandad/pandad.py:18-41`, release-mici tree)

`FW_PATH = os.path.join(BASEDIR, "board/obj/")` (`panda/python/constants.py:7`),
`app_fn = "panda_h7.bin.signed"` (`:44`), `bootstub_fn = "bootstub.panda_h7.bin"` (`:46`).
`Panda.flash()` reads that exact file and writes it to the MCU
(`panda/python/__init__.py:432-455`); `up_to_date()` is the signature comparison
(`:503-508`). If the newly flashed app does not boot, pandad falls back to reflashing the
**bootstub** via the GPIO DFU path (`pandad.py:42-48` → `hardware.py:432-441`).

**Therefore: a modified `panda_h7.bin.signed` committed to the fork's branch is picked up
by `git pull` + reboot, exactly like a Python change.** There is no install-URL step, no
factory reset, no calibration loss, no torque relearn. The
`install.sunnypilot.ai/fork/...` wipe cost that `progress.md` §11 documents applies to
switching forks/installs, not to pulling a commit on the same branch.

### 1.6 What it would actually take, concretely

**Route A — off-device build, commit binaries (recommended).**

1. On a dev machine or container with `arm-none-eabi-gcc`, `scons`, `pycryptodome`:
   check out this fork's branch, patch `opendbc_repo/opendbc/safety/modes/subaru_preglobal.h`,
   run `scons -C panda` (no `RELEASE` env var → DEBUG build, debug key, `ALLOW_DEBUG`).
2. Run the opendbc safety unit tests against the change (see §4 — this is not optional if
   the fork wants to stay within comma's stated fork policy).
3. Commit `panda/board/obj/panda_h7.bin.signed` (+ `bootstub.panda_h7.bin` and the `.elf`s,
   to keep the tree self-consistent) **and** the modified `subaru_preglobal.h`.
4. On device: `git pull`, reboot. `pandad` sees the signature mismatch and flashes.
5. Verify: `pandad` logs the old/new signature at `pandad.py:36`; confirm no
   `AssertionError` on "Version mismatch after flashing" (`:56-58`) before driving.

Two build gotchas found in the real source, both real:

- sunnypilot's `panda/SConscript` is an **older** revision than upstream's and still
  imports `from Crypto.PublicKey import RSA` in `get_key_header()` (`sp release-mici
  panda/SConscript:35-51`). Upstream removed that dependency (`commaai/panda` @ `d9ed70b`,
  "rm pycryptodome"). Building this tree therefore **requires pycryptodome installed**, and
  you must build sunnypilot's panda, not upstream's.
- Only `opendbc/safety/can.h` and `board/health.h` feed the SPI protocol version hashes
  (`panda/SConscript:161-167`). Editing `subaru_preglobal.h` does **not** change
  `CAN_PACKET_VERSION_HASH` or `HEALTH_PACKET_VERSION`, so no host/panda protocol mismatch
  is introduced. Good — this is a genuinely narrow change surface.

**Route B — on-device panda-only rebuild (plausible, unverified).**
`panda/SConstruct` *does* exist in this tree even though the top-level `SConstruct` does
not — so `scons -C panda` is at least structurally possible on device. And
`gcc-arm-none-eabi` is listed in openpilot's **core** dependency list, not a dev extra
(`pyproject.toml:44`), so the toolchain may well be present in the on-device venv.
**Unverified — needs a one-line on-device check** (`which arm-none-eabi-gcc`, or
`python -c "import scons"` in the openpilot env). If it is present, this route removes the
"commit binaries to a public repo" awkwardness entirely. Note `system/manager/build.py`
runs bare `scons` at `BASEDIR` and is skipped by the `prebuilt` marker
(`launch_chffrplus.sh:83-85`), so this would be a manual invocation, not something the boot
path does.

**Residual risk, stated plainly.** A firmware that flashes but misbehaves is worse than one
that does not boot: a non-booting app is caught and auto-recovered
(`pandad.py:42-48`), whereas subtly wrong safety code just… runs. Recovery from a bad
commit is `git revert` + reboot (pandad reflashes back), but only if the device still boots
far enough to run pandad. This is the one place in this project where a mistake is not
purely a software revert.

---

## 2. How sunnypilot handles this — and the decisive check on their `subaru_preglobal.h`

### 2.1 They ship a modified panda firmware. Proven, not inferred.

`selfdrive/pandad/panda.cc:43-45` (release-mici tree):

```cpp
void Panda::set_alternative_experience(uint16_t alternative_experience, uint16_t safety_param_sp) {
  handle->control_write(0xdf, alternative_experience, safety_param_sp);
}
```

Upstream panda's `0xdf` handler ignores `param2` entirely:

```c
    case 0xdf:
      if (!is_car_safety_mode(current_safety_mode)) {
        alternative_experience = req->param1;
      }
      break;
```
(`commaai/panda board/main_comms.h:246-252`)

sunnypilot's does not:

```c
    case 0xdf:
      if (!is_car_safety_mode(current_safety_mode)) {
        alternative_experience = req->param1;
        current_safety_param_sp = req->param2;
        mads_set_alternative_experience(&alternative_experience);
      }
      break;
```
(`release-mici panda/board/main_comms.h:247-255`)

sunnypilot added a **second safety parameter word** to the panda's control protocol. Since
MADS demonstrably works on this device (`progress.md` Q11), the shipped binary is
demonstrably built from this modified source. The distribution mechanism is exactly §1.5:
a committed binary on the release branch.

### 2.2 Decisive: sunnypilot's preglobal TX allowlist already exceeds 0x161/0x164

`sunnypilot/opendbc opendbc/safety/modes/subaru_preglobal.h:21-27` (identical in the
release-mici tree at `opendbc_repo/opendbc/safety/modes/subaru_preglobal.h:21-27`):

```c
#define SUBARU_PG_COMMON_TX_MSGS \
  {MSG_SUBARU_PG_ES_Distance, SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
  {MSG_SUBARU_PG_ES_LKAS,     SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \

#define SUBARU_PG_STOP_AND_GO_TX_MSGS \
  {MSG_SUBARU_PG_Throttle,    SUBARU_PG_CAM_BUS,  8, .check_relay = false}, \
  {MSG_SUBARU_PG_Brake_Pedal, SUBARU_PG_CAM_BUS,  4, .check_relay = false}, \
```

selected at init:

```c
  safety_config ret = subaru_stop_and_go ? BUILD_SAFETY_CFG(subaru_preglobal_rx_checks, subaru_pg_stop_and_go_tx_msgs) : \
                                           BUILD_SAFETY_CFG(subaru_preglobal_rx_checks, SUBARU_PG_TX_MSGS);
```
(`:115-116`)

`subaru_stop_and_go` comes from the new SP param word:

```c
void subaru_common_init(void) {
  const uint16_t SUBARU_PARAM_SP_STOP_AND_GO = 1;
  subaru_stop_and_go = GET_FLAG(current_safety_param_sp, SUBARU_PARAM_SP_STOP_AND_GO);
}
```
(`opendbc/safety/modes/subaru_common.h`)

This is the real diff from **sunnypilot/opendbc PR #152** ("Subaru: Stop and Go support
(beta)", merged as commit `b8a00bd`, 2025-10-13) — read from the merged commit itself, not
from the PR page.

**What this settles:**

- ✅ "sunnypilot ships modified preglobal TX allowlists to end users" — **true, decisive.**
  The `.h` file on this device right now allows four TX addresses, not two.
- ✅ The mechanism is a **runtime flag**, not a separate build. The expanded allowlist is
  compiled into the firmware this device is already running; a Params toggle flips it.
- ❌ "sunnypilot's preglobal Stop-and-Go required adding ES_Brake/ES_Status" — **false.**
  It added `Throttle` (0x140) and `Brake_Pedal` (0xD1), **on the camera bus** (bus 2),
  `.check_relay = false`. Those are the *engine's* messages being forged toward EyeSight —
  the same class of trick as this project's Q9 camera-bus experiment, not longitudinal
  authority. Their payloads confirm it: `values["Throttle_Pedal"] = 5` to fake a gas tap
  (`opendbc/sunnypilot/car/subaru/subarucan_ext.py`, per
  `research/eyesight_throttle_channel.md` §7).

So there is **no existing precedent to inherit for friction braking**. `ES_Brake` and
`ES_Status` remain untouched by everyone, upstream and fork alike.

### 2.3 A free experiment that exists today

`SubaruStopAndGo` is already in this branch's **compiled** params allowlist:

```
common/params_keys.h:221:    {"SubaruStopAndGo", {PERSISTENT | BACKUP, BOOL, "0"}},
common/params_keys.h:222:    {"SubaruStopAndGoManualParkingBrake", {PERSISTENT | BACKUP, BOOL, "0"}},
```

— i.e. it does **not** hit the `UnknownKeyName` landmine from `progress.md` §11, because
sunnypilot compiled `common/params_pyx.so` (also a committed binary in this tree) with it.
The plumbing is pure Python and already present:

```python
    if stop_and_go or stop_and_go_manual_parking_brake:
      CP_SP.safetyParam |= SubaruSafetyFlagsSP.STOP_AND_GO
```
(`opendbc_repo/opendbc/sunnypilot/car/interfaces.py:133`; gate at `:124` excludes
GLOBAL_GEN2/HYBRID, so preglobal qualifies)

and there is even a UI toggle (`selfdrive/ui/sunnypilot/layouts/settings/vehicle/brands/subaru.py:19`)
— though per `progress.md`'s UI caveat, mici hardware may not route to it, in which case
it is a `Params().put_bool()` away.

**This is a zero-build, zero-risk-to-firmware way to prove on this specific car that the
runtime-flag → expanded-TX-allowlist mechanism works end to end**, before anyone spends
effort on a custom build. It is also a real feature (EPB auto-resume from standstill).

Caveat worth knowing before enabling it: sunnypilot's own value checks for these two
messages are **commented out** in `subaru_common.h` (the `subaru_common_stop_and_go_*_check`
functions sit inside a `/* */` block and are never called), so those two TX addresses pass
the panda with **no value restriction at all**. And per `progress.md` Q9, this car reacted
badly to a single foreign frame on bus 2 ("EyeSight Off" dash fault) — so this is worth
treating as a real test with a real failure mode, not a free lunch.

---

## 3. What a correct upstream-style patch would look like

### 3.1 First: verifying the `check_relay` claim

**The claim holds.** Verified at `opendbc/safety/safety.h` (upstream, and byte-identical in
the release-mici tree):

Relay-malfunction detection — fires when a `check_relay` TX address is seen **on its own
declared bus**:

```c
  for (int i = 0; i < current_safety_config.tx_msgs_len; i++) {
    const CanMsg *m = &current_safety_config.tx_msgs[i];
    if (m->check_relay) {
      stock_ecu_check((m->addr == addr) && (m->bus == msg->bus));
    }
  }
```
(`safety.h:208-213`; `stock_ecu_check` → `relay_malfunction_set()` at `:373-380`;
`relay_malfunction` then blocks *all* TX at `:248` and *all* forwarding at `:264`)

Forwarding block — a `check_relay` TX address is not forwarded **to** its declared bus:

```c
  const int destination_bus = get_fwd_bus(bus_num);
  if (!blocked) {
    for (int i = 0; i < current_safety_config.tx_msgs_len; i++) {
      const CanMsg *m = &current_safety_config.tx_msgs[i];
      if (m->check_relay && !m->disable_static_blocking && (m->addr == addr) && (m->bus == (unsigned int)destination_bus)) {
        blocked = true;
```
(`safety.h:263-277`; `get_fwd_bus` maps 0↔2 at `:251-261`)

And the struct comment says exactly this:

```c
  bool check_relay;              // if true, trigger relay malfunction if existence on destination bus and block forwarding to destination bus
  bool disable_static_blocking;  // if true, static blocking is disabled so safety mode can dynamically handle it (e.g. selective AEB pass-through)
```
(`opendbc/safety/declarations.h:90-91`)

So for a preglobal entry `{0x160, bus 0, .check_relay = true}`: the camera's own 0x160
arriving on bus 2 is **not** forwarded to bus 0, and does not trip relay malfunction
(it is on bus 2, not bus 0). openpilot becomes the sole transmitter of 0x160 on the main
bus. **Contention is handled by construction — confirmed.** This is exactly the mechanism
already keeping 0x161/0x164 collision-free today, and the preglobal safety mode declares no
`.fwd` hook (`subaru_preglobal_hooks`, `subaru_preglobal.h:101-105`), so the generic
0↔2 forwarding above is all that applies.

**Three corollaries that are easy to miss and are load-bearing:**

- Blocking forwarding means the car **stops receiving the camera's 0x160/0x162 entirely**.
  openpilot must then transmit a valid replacement at the correct rate, with correct
  checksum and counter, from the first frame — or the ABS/engine ECUs see a dead EyeSight.
  This is a much heavier commitment than the `Cruise_Throttle` fast path, where openpilot
  is *already* the sole 0x161 transmitter and the frame is already being rebuilt at 20 Hz.
- **`ES_Brake` carries `AEB_Status` on global**, and upstream reads stock AEB out of it
  (`opendbc/car/subaru/carstate.py:127-128`). Taking ownership of 0x160 means openpilot
  becomes responsible for whatever AEB signalling preglobal's 0x160 carries. `Tesla`'s
  `.disable_static_blocking = true` entries (`opendbc/safety/modes/tesla.h:336-344`) exist
  precisely to allow selective AEB pass-through — that pattern is the one to study if
  0x160 turns out to matter for AEB on preglobal. **Preglobal's 0x160 has no `AEB_Status`
  signal in the DBC** (`opendbc/dbc/generator/subaru/_subaru_preglobal_2015.dbc:124-132`),
  which is suggestive but not proof that preglobal AEB doesn't ride on it.
- Nothing in openpilot currently **reads** preglobal 0x160/0x162.
  `carstate.py:122` / `:130` populate `es_brake_msg`/`es_status_msg` only in the
  `else` (non-preglobal) branch. A read-modify-write builder — which is the only responsible
  way to author these, exactly as `create_preglobal_es_distance` does — needs new preglobal
  carstate parsing first. That part is **pure Python**, so it is free on this prebuilt
  branch.

### 3.2 What `subaru.h` really does for global longitudinal

The model to copy (`opendbc/safety/modes/subaru.h`):

```c
#define SUBARU_COMMON_LONG_TX_MSGS(alt_bus) \
  {MSG_SUBARU_ES_Distance,       alt_bus,         8, .check_relay = true}, \
  {MSG_SUBARU_ES_Brake,          alt_bus,         8, .check_relay = true}, \
  {MSG_SUBARU_ES_Status,         alt_bus,         8, .check_relay = true}, \
```
(`:55-58`)

```c
  const LongitudinalLimits SUBARU_LONG_LIMITS = {
    .min_gas = 808,       // appears to be engine braking
    .max_gas = 3400,      // approx  2 m/s^2 when maxing cruise_rpm and cruise_throttle
    .inactive_gas = 1818, // this is zero acceleration
    .max_brake = 600,     // approx -3.5 m/s^2
    .min_transmission_rpm = 0,
    .max_transmission_rpm = 3600,
  };
  ...
  // check es_brake brake_pressure limits
  if (msg->addr == MSG_SUBARU_ES_Brake) {
    int es_brake_pressure = GET_BYTES(msg, 2, 2);
    violation |= longitudinal_brake_checks(es_brake_pressure, SUBARU_LONG_LIMITS);
  }

  // check es_distance cruise_throttle limits
  if (msg->addr == MSG_SUBARU_ES_Distance) {
    int cruise_throttle = (GET_BYTES(msg, 2, 2) & 0x1FFFU);
    bool cruise_cancel = (msg->data[7] >> 0) & 1U;

    if (subaru_longitudinal) {
      violation |= longitudinal_gas_checks(cruise_throttle, SUBARU_LONG_LIMITS);
    } else {
      // If openpilot is not controlling long, only allow ES_Distance for cruise cancel requests,
      violation |= (cruise_throttle != SUBARU_LONG_LIMITS.inactive_gas);
      violation |= (!cruise_cancel);
    }
  }

  // check es_status transmission_rpm limits
  if (msg->addr == MSG_SUBARU_ES_Status) {
    int transmission_rpm = (GET_BYTES(msg, 2, 2) & 0x1FFFU);
    violation |= longitudinal_transmission_rpm_checks(transmission_rpm, SUBARU_LONG_LIMITS);
  }
```
(`:134-142`, `:158-183`)

The check helpers (`opendbc/safety/longitudinal.h`) all share a shape — *either* controls
are allowed and the value is in range, *or* the value is exactly the inactive sentinel:

```c
bool longitudinal_brake_checks(int desired_brake, const LongitudinalLimits limits) {
  bool violation = false;
  violation |= !get_longitudinal_allowed() && (desired_brake != 0);
  violation |= desired_brake > limits.max_brake;
  return violation;
}
```
and `get_longitudinal_allowed() { return controls_allowed && !gas_pressed_prev; }`.

Note also `subaru_longitudinal` is itself set only under `#ifdef ALLOW_DEBUG`
(`subaru.h:235-238`) — comma's own Subaru longitudinal is debug-gated too.

### 3.3 The bit offsets do NOT port. This is the trap.

Preglobal and global lay these signals out **differently**. Verified against the DBC
generators:

| Signal | Global (`_subaru_global.dbc` / `subaru_global_2017.dbc`) | Preglobal (`_subaru_preglobal_2015.dbc`) |
|---|---|---|
| `ES_Brake.Brake_Pressure` | `16\|16` → `GET_BYTES(msg,2,2)` ✔ matches `subaru.h:160` | **`0\|16`** → would need `GET_BYTES(msg,0,2)` |
| `ES_Status.Cruise_RPM` | `16\|13` → `GET_BYTES(msg,2,2)&0x1FFF` ✔ | **`16\|16`** → `GET_BYTES(msg,2,2)`, **no 13-bit mask** |
| `ES_Distance.Cruise_Throttle` | `16\|13` | **`0\|12`** |
| `ES_Distance` cancel bit | `Cruise_Cancel` @ bit 56 | **no cancel bit**; `Cruise_Button` `48\|3` instead |
| checksum / counter | `CHECKSUM` byte 0, `COUNTER` `8\|4` | `Checksum` **byte 7**, `COUNTER` 3-bit, per-message offsets |

(preglobal: `_subaru_preglobal_2015.dbc:124-160`; global: `_subaru_global.dbc:147-158`,
`subaru_global_2017.dbc:14-46`)

A copy-paste of `subaru.h`'s tx_hook onto preglobal would read the **wrong bits** and
enforce nothing. Worse, the *limits* are equally non-portable: `.max_brake = 600` is
calibrated to global's 16-bit `Brake_Pressure` ("approx -3.5 m/s²"); preglobal's field is
also 16-bit but its DBC range comment says `[0|255]` and its physical scaling is **entirely
undetermined**. Same for `Cruise_RPM` (`[0|65535]` on preglobal vs `[0|4095]` global) —
`.max_transmission_rpm = 3600` is meaningless until preglobal's scale is measured.

**Do not write numeric limits from the global file.** They must come from observed
EyeSight-authored values on this actual car — which the existing route archive can supply
passively, the same "only ever replay values EyeSight itself has commanded" principle
already adopted in `eyesight_throttle_channel.md`.

### 3.4 Patch shape (sketch — deliberately not a drop-in patch)

Following sunnypilot's own structure, as an SP-param-gated variant so it is off by default
and cannot affect anyone else's car:

```c
#define MSG_SUBARU_PG_ES_Brake              0x160U
#define MSG_SUBARU_PG_ES_Status             0x162U

#define SUBARU_PG_LONG_TX_MSGS \
  {MSG_SUBARU_PG_ES_Brake,    SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
  {MSG_SUBARU_PG_ES_Status,   SUBARU_PG_MAIN_BUS, 8, .check_relay = true}, \
```

and, in `subaru_preglobal_tx_hook()`, mirroring `subaru.h:158-183` but with **preglobal
offsets** and **preglobal-measured limits**:

```c
  if (msg->addr == MSG_SUBARU_PG_ES_Brake) {
    int es_brake_pressure = GET_BYTES(msg, 0, 2);          // preglobal: bits 0..15, NOT 16..31
    violation |= longitudinal_brake_checks(es_brake_pressure, SUBARU_PG_LONG_LIMITS);
  }

  if (msg->addr == MSG_SUBARU_PG_ES_Status) {
    int transmission_rpm = GET_BYTES(msg, 2, 2);           // preglobal: 16-bit, no 0x1FFF mask
    violation |= longitudinal_transmission_rpm_checks(transmission_rpm, SUBARU_PG_LONG_LIMITS);
  }
```

with `SUBARU_PG_LONG_LIMITS` values marked TODO until measured. And — following the
existing tx_hook's structure, which currently does `if (...) { tx = false; } return tx;`
rather than accumulating a `violation` flag (`subaru_preglobal.h:64-78`) — the hook should
be refactored to `subaru.h`'s `bool violation` accumulator style so multiple addresses
compose correctly.

**Also required and currently absent**: `ES_Distance`'s own value check. Today
`subaru_preglobal_tx_hook` checks *only* `ES_LKAS`, so a preglobal build with longitudinal
TX would still let `Cruise_Throttle` through unbounded. Upstream's non-long branch
(`subaru.h:171-176`) is the model: when not doing long, force `cruise_throttle` to the
inactive sentinel. That would need a preglobal `inactive_gas` value — again, measured, not
assumed.

---

## 4. Safety review / certification implications

Stated factually, from comma's own documents.

**comma's fork policy**, `docs/SAFETY.md` (identical text in this device's release-mici
tree and in `commaai/openpilot` master):

> ### Forks of openpilot
>
> * Do not disable or nerf [driver monitoring]
> * Do not disable or nerf [excessive actuation checks]
> * If your fork modifies any of the code in `opendbc/safety/`:
>    * your fork cannot use the openpilot trademark
>    * your fork must preserve the full [safety test suite] and all tests must pass,
>      including any new coverage required by the fork's changes
>
> Failure to comply with these standards will get you and your users banned from comma.ai
> servers.
>
> **comma.ai strongly discourages the use of openpilot forks with safety code either missing
> or not fully meeting the above requirements.**

**opendbc's code-rigor bar** (`opendbc/README.md:139-152`) for anything under
`opendbc/safety/`:

- cppcheck static analysis, plus a cppcheck **MISRA C:2012** addon
- `-Wall -Wextra -Wstrict-prototypes -Werror`
- per-car-variant safety unit tests
- a mutation test on MISRA coverage
- **100% line coverage enforced on the safety unit tests**

**And comma's stance on non-release safety modes** (`opendbc/README.md:135`):

> "Some of safety modes (for example `SAFETY_ALLOUTPUT`) are disabled in release firmwares.
> In order to use them, compile and flash your own build."

That sentence is, in effect, comma's documented answer to this whole question. It is also
already what this device does — see §1.4.

**What this means concretely here:**

1. **The trademark clause is already engaged.** sunnypilot modifies `opendbc/safety/`
   (`subaru_common.h` is new, `subaru_preglobal.h` and `subaru.h` are patched, and panda's
   `main_comms.h` gained a safety-param word). This is upstream of anything this project
   would do.
2. **The "all tests must pass, including any new coverage" clause is currently unmet by
   the precedent.** sunnypilot's `opendbc/safety/tests/test_subaru_preglobal.py` still
   declares `TX_MSGS = [[0x161, 0], [0x164, 0]]` and
   `FWD_BLACKLISTED_ADDRS = {2: [0x161, 0x164]}` (`:14-16`) — the stop-and-go additions
   have **no** safety-test coverage, and their value-check functions are commented out.
   That is a factual observation about the precedent, not an endorsement of copying it. A
   patch adding `ES_Brake`/`ES_Status` that wants to meet comma's bar needs a
   `TestSubaruPreglobalLongSafety` subclass exercising the new TX addresses and the new
   limits, in the style of `test_subaru.py`'s longitudinal tests.
3. **There is no "cert" to lose in a regulatory sense.** `docs/SAFETY.md` describes
   *observing* ISO 26262 guidance, ISO 11270/15622 actuator limits, and NHTSA ALC material,
   and "developed in good faith to be compliant with FMVSS" — not certification by an
   external body. The enforceable consequences comma states are: no trademark, and account
   bans from comma servers.
4. **The safety argument that actually matters is not comma's, it's physics.** Adding
   `ES_Brake` moves this project from "veto — worst case the car coasts"
   (`eyesight_throttle_channel.md`'s `min(eyesight, ours)` rule, where unintended
   acceleration is structurally inexpressible) into **commanding friction braking with
   unmeasured scaling on a message the car has never received from a non-EyeSight source**.
   `longitudinal_brake_checks` bounds it, but only as well as `.max_brake` is calibrated —
   and §3.3 shows that number cannot be borrowed from the global file. Unintended *braking*
   authority is a genuinely different risk class from unintended throttle-cut, and it is
   the one class where a wrong constant is immediately dangerous rather than merely
   ineffective.

---

## Unverified / open

Flagged explicitly rather than smoothed over:

- **That preglobal's 0x160/0x162 are camera-authored on bus 2.** Strongly indicated
  (they are `ES_*` messages in the same block as 0x161/0x164; on global gen1 the equivalents
  are read from the camera parser — `carstate.py:20`, `:32`, `:122`, `:130`), but **not directly
  verified**. Settled for free from the existing route archive by checking which bus carries
  them. If they were main-bus-authored by another ECU, `.check_relay = true` would instantly
  trip relay malfunction and kill all TX.
- **Whether preglobal's engine/ABS ECUs act on 0x160/0x162 at all.** Entirely unknown — the
  same open question as Q14's `Cruise_Throttle`, one step further out. Nothing here
  establishes authority, only permission.
- **Preglobal scaling for `Brake_Pressure` and `Cruise_RPM`.** Unknown. Global's constants
  are not transferable (§3.3).
- **Whether `arm-none-eabi-gcc` is present on this device's AGNOS/venv.** One command to
  check; would decide Route A vs Route B in §1.6.
- **Whether the committed `panda_h7.bin.signed` on `release-mici` was built from that same
  commit's `opendbc_repo`.** Inferred (the SP-param protocol change at
  `panda/board/main_comms.h:252` must be in the running binary for MADS to work, and MADS
  works on this car), not proven by disassembly.
- **Whether preglobal AEB rides on 0x160.** Preglobal's DBC has no `AEB_Status` signal
  (unlike global's), which is suggestive but not conclusive.
