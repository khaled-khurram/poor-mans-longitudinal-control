# NHTSA TSB verification: does SSM's "Active Test" mode offer a real path to cruise actuation?

## Top-line

**Document is real and the quote is accurate this time (not fabricated) — but it doesn't open a new avenue for this project.** It's the wrong platform (2020-22 global, not this car's 2015 preglobal) and the wrong kind of "activation" (a dashboard-icon display test, not actual cruise-function actuation).

## The document itself

Fetched directly: `https://static.nhtsa.gov/odi/tsbs/2022/MC-10208701-0001.pdf`. It's a genuine Subaru of America Service Information Bulletin, **Bulletin Number 07-204-22, dated 02/18/2022**.

- **Applicability: "2020-22MY Legacy & Outback"** — this is the **global platform**, not the 2004-2015 preglobal generation this project's car is on. Confirmed platform mismatch, same category of error this project has caught in prior research (citing real documents that don't actually apply to the target car).
- **Subject: "Tentative Select Monitor Procedures When Replacing and/or Diagnosing Combination Meters"** — the entire bulletin is about the **instrument cluster (combination meter)**, not cruise control functionality itself.

## The quote, in actual context

The earlier report's quote is accurate — this text really is on page 4, under "Scenario 3: Tentative Functionality of Activated Tests Using Select Monitor":

> "When using the 'Active Test' feature within SSM, the following items will not display the desired activation of the combination meter. If these items are selected and activated, there will be no change displayed within the combination meter.
> 1. SRH OFF
> 2. CRUISE indicator
> 3. SET indicator
> NOTE: An error message WILL NOT be displayed when attempting to use these functions."

**What this actually describes:** on 2020-22 Legacy/Outback specifically, SSM's Active Test can *command the dashboard to light up the CRUISE and SET indicator icons* as a bench/display test (like a bulb-check) — and the bulletin is reporting a **bug**: on these model years, that specific display test silently fails (the icon doesn't light up, with no error shown). The bulletin promises a future combination-meter logic fix.

This is **not** about triggering the ECU to behave as if a button was actually pressed, or changing real cruise state/target speed. It's a cosmetic/display-only actuator test aimed at verifying the instrument cluster's own indicator lights work — the kind of thing a tech does after replacing a combination meter to confirm the new part is wired correctly.

## What this does confirm, honestly

- **SSM's "Active Test" mode is real and does include something named "CRUISE indicator" and "SET indicator" as commandable items** — general web search confirms Active Test broadly covers many actuator/indicator tests across Subaru's lineup (windows, mirrors, sunroof, wipers, etc. — [iWire Subaru Test Mode overview](https://iwireusa.com/blogs/iwire-university/subaru-test-mode), [SSM usage tips](https://subaru.oemdtc.com/6977/subaru-select-monitor-iii-ssmiii-usage-tips)). So the *names* "CRUISE indicator"/"SET indicator" existing as SSM-addressable items is real, not fabricated.
- **Not confirmed for preglobal/SSM3 at all.** This bulletin is SSM4-era, global-platform only. No preglobal-specific Active Test documentation was found in this search.
- **Even if it did apply, it wouldn't be the right mechanism** — this only proves the dashboard *icon* can be commanded on, not that the underlying cruise system treats it as a real button press. Icon lighting up and the car's ACC actually reacting are two different things.

## Bottom line for this project

Interesting to know Active Test as a general SSM capability is real, and that Subaru does have named diagnostic hooks for cruise-related indicators somewhere in the SSM ecosystem — but this specific document doesn't transfer to preglobal, doesn't describe real actuation (only cosmetic display testing), and doesn't reveal a new mechanism worth pursuing based on what's actually in it. Treat the earlier report's citation of this document as technically accurate-but-misleading — real quote, wrong takeaway.
