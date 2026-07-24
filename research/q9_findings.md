# Q9 Research: Does preglobal's EyeSight module respond to a UDS CommunicationControl-style "stop transmitting" request?

**Verdict: STILL OPEN.** No evidence found — in the uploaded Discord archive or local opendbc source — of anyone testing UDS `CommunicationControl` (service `0x28`) against a **preglobal** EyeSight module specifically, in either direction. That said, this pass surfaced real new context that meaningfully changes how confident we should be either way, and one cheap, low-risk next diagnostic step.

## Findings

### 1. `0x28` CommunicationControl is NOT reliable even within the *global* platform — HIGH confidence
Direct quote, comma.ai Discord `#subaru`, 2026-03-29, user `rattail98` (corroborated same thread by `jacobwaller`, `sunnyhaibin`), from a comma hackathon working on Subaru angle-steering:

> "the Eyesight ECU on these cars rejects the UDS CommunicationControl disable command (0x28) with `conditionsNotCorrect` (0x22). The ECU enters extended diagnostic session fine, but refuses to actually disable communication - unlike the gen1/non-angle gen2 ECUs where this works. I also tested the 10-second diagnostic prohibition delay ... waiting 12+ seconds after boot ... it still got rejected at 23 seconds - so it's not a timing issue, this ECU variant genuinely won't accept the command."

Takeaway: `0x28` support is **ECU-firmware/generation-specific even among global-platform Subarus** — it works on gen1/non-angle-gen2, fails on newer angle-steering gen2 with a hard negative response, not a timing race. This means "global works, so preglobal probably works too" was never a safe inference — the technique isn't even uniform across cars that *do* speak full UDS.

### 2. Preglobal genuinely runs a different, older diagnostic stack (SSM3) — MEDIUM confidence, independent corroboration
comma.ai Discord `#subaru`, 2026-01-19, discussing the open-source `FreeSSM` tool:

> `mlp______`: "freessm does not work with newer ssm4 subarus" / "iirc ssm2 and ssm3 only"

This independently corroborates (from a different source than the existing research doc's SSM3/SSM4 citations) that preglobal's diagnostic protocol (SSM3) is architecturally distinct from global's (SSM4). It does **not** by itself confirm or deny whether SSM3 implements ISO-14229 UDS services like `0x28` — it only supports the premise that preglobal is a genuinely different stack, not just an older firmware build of the same one.

### 3. Zero preglobal-specific precedent anywhere in the archive — the actual gap
Searched all 13 uploaded channel exports (~60MB, `#subaru` alone is 260k+ lines back to 2019) for `CommunicationControl`, `0x28`, `DISABLE_RX_DISABLE_TX`, `SSM3`, `seed`/`key`, `security access`, `silenc*`. Every concrete UDS-disable success/failure report found (`jnewb1`'s May 2023 seed-key unlock work via UnlockECU, the March 2026 hackathon report above) is explicitly about **global gen2** cars. Nobody in this community — despite years of active Subaru discussion — has published a preglobal-specific UDS `0x28` test either way. This matches progress.md's existing assessment; it's now corroborated by an actual archive search rather than assumed.

### 4. Correction to an earlier research pass
An earlier research pass's conclusion on `0x28` feasibility ("low... will likely return NRC 0x11") was explicitly labeled speculative inference in its own text, and remains a reasonable calibrated inference that doesn't resolve Q9 either way — that part's fine. But flag this: **that same pass's claim that the preglobal button signal bits (`SET_BUTTON`/`RES_BUTTON`) are "unverified... speculative," and that cruise buttons are purely analog with no native CAN broadcast, is now factually wrong** — Q4 in this project is doubly confirmed via 412 real archived events and a live 12/12 real-time test that these buttons *do* flip bits on CAN `0x144`. Whatever produced that pass either predates this project's own live verification or is generally unreliable on preglobal-specific claims — treat any of its other uncorroborated inferences (including the `0x28` speculation) with correspondingly more skepticism, though the underlying SSM3-predates-UDS reasoning isn't necessarily wrong, just unconfirmed either way.

### 4b. Lead chased down: `jnewb1`'s "Eyesight is successfully UDS disabled" (2023-05-27) — confirmed NOT preglobal
Worth flagging explicitly since it reads, out of context, like it could be Q9 answered: `jnewb1`, comma.ai Discord `#subaru`, 2023-05-27: *"Eyesight is successfully UDS disabled, and 0x27 seed/key unlocked - I can still read the buttons through the UDS message."* Checked the surrounding thread (same channel, ~lines 202780–204600) to confirm platform generation before citing it:

- Line 204100: the actual code posted in-thread is `def unlock_gen2(seed):`
- Line 204333 (`jnewb1`, next day): "Both **gen1 and gen2** fully disable eyesight, track OP state through UDS button presses, and get the PCB through UDS" — "gen1"/"gen2" are Global-platform generations in this community's terminology (confirmed same thread: another contributor states "My car is a 2021 Forester (**gen1**)" — a Global-era car; preglobal is consistently referred to as "preglobal"/"pre global" elsewhere in the same channel, e.g. line 202897 "17 outback is preglobal", never as "gen1")
- Line 204341 (`sunnyhaibin`, immediately replying to the gen1/gen2 comment above): **"Upstream doesn't have this set for pre global."**

Verdict: this is Global gen1/gen2 evidence, not preglobal — and the community's own contemporaneous statement is that preglobal explicitly *lacked* this capability upstream as of May 2023. Doesn't move Q9 from open; if anything it's one more data point that this trick has consistently stayed inside the Global platform boundary every time it's come up in three years of channel history.

### 5. Adjacent precedent worth knowing: unsecured DID read on global gen2
`jnewb1`, comma.ai Discord `#subaru`, 2023-07-22: "the whole seed key thing wasn't even required for gen2, you can just read the button DID directly, lol." Not Q9 itself (this is a *read*, not the *disable-transmit* service), but it shows at least one Subaru gen2 ECU exposes some UDS services without security access. Suggested cheap next step if this gets picked back up: before attempting the full `CommunicationControl` disable on the real car, send a benign, read-only UDS probe first — `DiagnosticSessionControl` (`0x10 0x03`, already known-safe per line 255780 of this same channel: "Extended Diagnostic Session (`0x10 0x03`) — the first thing `disable_ecu()` sends") followed by a harmless `ReadDataByIdentifier`. That alone would answer "does this preglobal ECU speak ISO-TP/UDS at all" — much lower-risk than a full silence-and-inject attempt, and a prerequisite for `0x28` to even be worth trying.

## Bottom line for Phase 3 planning
Q9 stays open — this pass didn't find a yes/no answer because one doesn't exist yet in any accessible source. What changed: the "maybe it just works like global does" assumption is weaker than it looked (0x28 isn't even reliable within global), the SSM3-vs-SSM4 protocol split is now corroborated from a second independent source, and there's a concrete, low-risk (read-only) diagnostic probe to run before ever attempting the actual disable command on real hardware.
