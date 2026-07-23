# FreeSSM source research — SSM3 protocol capabilities beyond generic UDS

**Top-line: real, concrete new lead found — a genuine write-to-ECU-memory capability
exists in the SSM2/3/4 protocol layer that nothing tonight has tested. Not proven to
work for cruise-switch simulation on this car, but architecturally distinct from
everything tried so far (not CAN injection, not generic ISO-14229 UDS) and worth a
real test.**

## Source

`github.com/Comer352L/FreeSSM` — real, active, 280 stars, C++, last pushed April 2024.
This is the canonical FreeSSM project (confirmed via `gh search repos`, cross-checked
against the "freessm... ssm2 and ssm3 only" comment already found in this project's own
Discord research). Cloned and inspected directly, not going on documentation alone.

## 1. Real per-ECU cruise-control definitions exist — but only for the OLDEST generation

`definitions/SSM1defs_CruiseControl.xml` is a genuine, real XML definitions file for a
1996 Impreza's cruise control unit. It defines a `SWBLOCK` — a set of individual
switch-state bits read from a fixed memory address (`0x00A7` for the '96 example):

- `SW_SE` — SET/COAST switch
- `SW_RE` — RESUME/ACCEL switch
- `SW_ST` — Stop light switch
- `SW_BR` — brake/clutch switch
- `SW_N` / `SW_IH` — inhibitor switches

This is on **SSM1** (this car's protocol is SSM3, a newer generation) and is READ-only
in this file — it shows how to *monitor* switch state via SSM, not how to *set* it. No
SSM2/SSM3-specific `.xml` definitions exist anywhere in this repo (`ls definitions/`
shows only 4 SSM1 files: AirConditioning, ABS, CruiseControl, Engine) — the human-
documented, per-model definitions don't cover this car's generation or model.

**But it's still useful corroboration**: independent, non-CAN confirmation (via an
entirely different diagnostic protocol, on a different car generation) that Subaru
cruise switches are natively exposed as discrete, individually-addressable on/off
signals to the diagnostic system — consistent with, not contradicting, the CAN-side
`SET_BUTTON`/`RES_BUTTON` bit-level findings already confirmed on this project's actual
car.

## 2. The real new lead: SSM2/3/4 protocol layer has a genuine WRITE capability

Checked the actual communication implementation, not just definitions. `SSMP2communication.h`
(FreeSSM's internal name for the protocol generation that covers what this community
calls SSM2/SSM3/SSM4 — confirmed via `enum protocol_dt {SSM1, SSM2}` in
`SSMprotocol.h`, i.e. everything past SSM1 is "SSM2" internally) implements real,
working write methods:

```
bool writeAddress(unsigned int addr, char databyte, char *databytewritten = NULL);
bool writeAddresses(std::vector<unsigned int> addr, std::vector<char> data, ...);
bool writeAddress_permanent(unsigned int addr, char databyte, int delay = 0);
Result WriteDataBlock(const unsigned int ecuaddr, const unsigned int dataaddr, ...);
Result WriteDatabyte(const unsigned int ecuaddr, const unsigned int dataaddr, ...);
bool writeDataBlock(const unsigned int dataaddr, const std::vector<char> data, ...);
bool writeDatabyte(const unsigned int dataaddr, const char databyte, ...);
```

(`SSMP2communication.h` lines 47-95, `SSMP2communication_core.h` lines 56-57.)

Checked the actual implementation of `writeDatabyte()` (`SSMP2communication.cpp` line
201+) — it's a real, functioning code path (prepares a buffer, sends it, verifies the
echoed data matches what was sent), **with no security-access/authentication call in
that path**. Doesn't rule out the ECU itself gating writes internally, but nothing in
FreeSSM's own client-side logic requires unlocking anything first.

**Why this matters:** this is a fundamentally different mechanism from everything
tested tonight. It's not a CAN bus message (no bus-contention problem — this operates
over the diagnostic K-line/ISO14230-style link, not the vehicle CAN network the
CruiseControl broadcast lives on). It's not a generic ISO-14229 UDS service either (not
`WriteDataByIdentifier`/DID-based — this is raw memory-address writes, SSM's own native
addressing scheme, architecturally older/simpler than UDS DIDs). Neither
`CommunicationControl` nor `SecurityAccess` (both tested tonight, both got silence) are
in this code path at all — this is a genuinely untested class of request.

## 3. What's NOT established — real gaps, not overclaimed

- **No SSM2/3-specific address for this car's cruise switches was found.** The only
  concrete switch address (`0x00A7`) is from the SSM1/1996-Impreza example — a
  different protocol generation with likely different addressing. Finding the right
  address for this car's actual ECU would need either community data (not found in
  this pass) or direct trial against the real hardware.
- **No evidence anyone has actually used `writeAddress`/`writeDataBlock` to simulate a
  cruise switch specifically** — found in any Subaru model, any generation. The
  capability exists in the code; a demonstrated success story for this exact use case
  does not.
- **Not in the tool's own end-user documentation** — grepped `doc/help_en.html`
  directly for "write", zero hits. Suggests this write capability is a lower-level
  piece of the library, not a heavily-exercised, user-facing feature — real risk that
  it's less battle-tested than the read paths most FreeSSM users actually rely on daily.
- **Whether the *specific ECU* on this car (EyeSight/camera module, or whichever ECU
  actually owns cruise-switch state) accepts writes to any address at all is untested.**
  This capability existing in the client library doesn't guarantee the target ECU's
  firmware honors write requests to any given address without rejection.

## Bottom line

Real, concrete, previously-untested capability found: SSM's own native write-to-memory
command, available in FreeSSM's real source for the protocol generation this car uses,
architecturally distinct from CAN injection and from the UDS services already
exhausted. Not proven to solve anything — the actual target address for this car's
cruise switches is unknown, and no successful precedent for this specific use case was
found anywhere in the source or its documentation. Worth a real bench test to determine
if it's even reachable/responsive on this car's actual ECUs, using the same
low-risk-first discipline as tonight's UDS probing (start with a read/query, not a
write, to establish whether the target address concept is even valid on this hardware
before ever attempting an actual write).
