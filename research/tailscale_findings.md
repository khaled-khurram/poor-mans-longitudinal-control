# Tailscale-on-comma-device: research findings (2026-07-23)

Scope: whether the plan in `progress.md` §9 (static `linux/arm64` Tailscale binary run out of
`/data`, TUN mode, boot-hook persistence) is sound. Sources: full grep of the 13-file Discord
export corpus in `discord-logs/CommaDiscord/`, plus GitHub code search / web search for the
FrogPilot "built-in tailscale" claim that turned up mid-research.

## Top-line verdict

**Real precedent exists and the core approach works — but it's fragile, not a solved problem, and
the current plan's specific premise (skip the normal installer) is wrong.** People have been
running Tailscale on comma hardware since at least 2021, using the *normal* `apt`-based installer
after remounting root read-write — not a hand-managed static binary. But reliability is
inconsistent across AGNOS versions, and there's a real, confirmed, unresolved failure risk: **OS
updates wipe the install.** The `noexec` question specifically is not answered by anything in the
corpus.

## Findings

### 1. Comma devices are general-purpose, no lockdown against third-party software
`adeebshihadeh` (comma staff), dev-openpilot, 3/30/2021: *"it's an android device, install
whatever you want on it"* — direct comma-employee confirmation, no fundamental OS-level lockdown.
**Confidence: high (primary source, comma staff).**

### 2. AGNOS is Ubuntu-based (corroborates community chatter)
comma's own blog (web search, not Discord): "the comma three runs AGNOS, comma.ai's new
Ubuntu-based operating system." Matches an offhand community remark in hw-three-3x
(`incognitojam`, 4/21/2022): *"guess it works on ubuntu"*. **Confidence: high (official comma
source).**

### 3. Root filesystem is normally read-only; `mount -o remount,rw /` is the standard first step
Confirmed by **two independent real transcripts**, three years apart, both starting the exact same
way:
- `taylorswift1243`, dev-openpilot, 2/24/2022 (a **working** posted install script, 6 fire
  reactions from the channel):
  ```
  sudo mount -o remount,rw /
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo sed -i 's/--state=\/var\/lib\/tailscale\/tailscaled\.state --socket=\/run\/tailscale\/tailscaled\.sock /--state=\/data\/tailscaled.state /g' /lib/systemd/system/tailscaled.service
  sudo systemctl restart tailscaled
  sudo tailscale up
  ```
- `fe2_o3_20425`, general, 9/12/2024 (a **failed** attempt, same first two commands verbatim).

**This directly contradicts the current plan's stated premise** ("skip the normal installer,
assumes writable root apt can't touch"). The normal `curl|sh` installer does work on comma
hardware, at least sometimes — the blocker isn't the installer, it's whether the remount actually
succeeds. **Confidence: high (two real, quoted transcripts).**

### 4. But the remount+install approach is NOT reliably reproducible
`fe2_o3_20425`'s 2024 attempt, running the identical first two commands as the working 2022
script, failed with:
```
tee: /usr/share/keyrings/tailscale-archive-keyring.gpg: Read-only file system
```
i.e. the remount either silently didn't take, didn't apply to whatever underlying mount
`/usr/share` actually lives on, or AGNOS's protections changed between 2022 and 2024. **No fix was
found in the visible thread** — the conversation moved on without resolution, despite the user
specifically tagging `Mike854` (referenced elsewhere as the community's go-to person for
Tailscale-on-comma issues) — no standalone Mike854 guide or fix was found anywhere else in the
corpus either. **Confidence: high on the failure being real; the *why* is unresolved — flag as an
open risk, not a solved compatibility question.**

### 5. Confirmed, real, direct answer to the persistence risk: OS updates blow the install away
`crazysim` (a frequent, technically credible poster throughout this corpus), general, 6/17/2025,
responding to someone asking about running Tailscale:
> *"there's been use of tailscale. issue is that OS updates will blow it away"*
> *"i don't know the status either of that"*

This is a direct, first-hand confirmation that the boot/update-persistence concern in the current
plan is real and unsolved by the wider community too — not just an abstract worry. It validates
the plan's instinct to need a boot-time launch hook, but also suggests the **systemd-unit-file
edit approach** (the `sed` step in taylorswift1243's script, which patches
`/lib/systemd/system/tailscaled.service` — a file that lives on the OS-managed root partition, not
`/data`) is exactly the kind of thing that gets wiped on update. Pointing `tailscaled`'s *state*
at `/data` (as that script does) is not the same as making the *binary and service definition*
survive an update — those still live outside `/data` in that script. **Confidence: high (direct,
specific, first-hand claim from a credible community source).**

### 6. "Userspace WireGuard" clarifies one non-issue, doesn't remove the root/TUN requirement
`1vivy`, dev-openpilot, 3/30/2021: *"You'll need to patch the kernel for wireguard too" → "Try
using tailscale, they use a userspace wireguard, and no worrying about this"*. This means
Tailscale avoids needing a **kernel WireGuard module** — but it still needs a TUN device and root
to create it, which the plan already correctly accounts for (root already confirmed available via
passwordless `sudo`). Doesn't change the plan; just removes one theoretical extra obstacle.
**Confidence: high (matches Tailscale's actual documented architecture).**

### 7. The FrogPilot "built-in tailscale" claim does NOT hold up under verification
`danielv123`, general, 9/10/2025: *"frogpilot has built in tailscale vpn which I find really
useful."* This looked like the single best lead in the whole corpus — a maintained fork with a
working reference implementation would obsolete most of the open questions here. **Checked
directly against the primary source**: `github.com/FrogAi/FrogPilot` (confirmed the current,
actively maintained repo — 545 stars, pushed today, not archived). GitHub code search for
`tailscale`, `wireguard`, and `VPN` in that repo all returned **zero results**. No corroborating
mention anywhere else in the 60MB Discord corpus either (single data point, uncorroborated).
**Verdict: unverified, likely stale or simply incorrect — do not treat FrogPilot as a working
reference implementation without further evidence.** (Possible explanations: removed since
9/2025, existed in some other fork the user was conflating it with, or the user was describing
their own manual setup running alongside FrogPilot rather than something FrogPilot ships.)

### 8. `noexec` — still completely unanswered
Zero hits for "noexec" anywhere across all 13 files (60MB). No one in this corpus appears to have
hit or discussed it by that name. Soft, weak signal: the one real documented failure (finding #4)
was a `Read-only file system` error on `tee`, not a `Permission denied`/exec-format error — i.e.
when people do hit a wall, it looks like a **read-only mount** problem, not a **noexec** problem.
That's not proof `/data` isn't `noexec`, just an absence-of-evidence data point from real attempted
installs. **This remains genuinely untested and unconfirmed — still needs the device in hand.**

## Suggested plan adjustments

1. **Prefer the standard `apt`-based installer over hand-rolling a static binary**, since it's the
   only approach with real working precedent (finding #3) — try `mount -o remount,rw /` +
   `install.sh` first, and only fall back to the static-binary-in-`/data` approach (the current
   plan) if the remount/apt path fails on this specific device, matching finding #4's failure mode.
2. **Persistence is the real open problem, confirmed independently by the community (finding #5)**
   — don't just persist `tailscaled`'s *state* in `/data` (already planned) — the *binary* and
   *service launch mechanism* also need to live somewhere that survives an OTA update, not just a
   reboot. Static binary in `/data` (already the plan) plus a `launch_chffrplus.sh`/
   `process_config.py` boot hook (already the plan) is actually the more update-resilient design
   compared to the systemd-unit-edit approach the working 2022 script used — that instinct in the
   current plan looks right, this research reinforces it rather than changing it.
3. **Drop the FrogPilot-as-reference-implementation idea** — it doesn't check out. Don't spend time
   trying to port code from it.
4. **`noexec` is still the single biggest untested unknown** and this research doesn't resolve it
   — first real test on the device should be as simple as possible: confirm you can execute *any*
   binary copied to `/data` before building out the rest of the Tailscale plan on top of that
   assumption.

Pure research — no device access, no code changes, no installation attempted.
