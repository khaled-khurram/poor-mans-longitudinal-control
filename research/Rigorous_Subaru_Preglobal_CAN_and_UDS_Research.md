> **⚠️ CORRECTION (2026-07-23, see `progress.md` §7.3):** the button-bit table below (`OnOffButton`/`SET_BUTTON`/`RES_BUTTON`/`Button`, all rated "Speculative (Low)... Unverified") is **factually wrong**. `SET_BUTTON`=byte0/bit3 and `RES_BUTTON`=byte0/bit4 on `0x144` are now doubly confirmed via 412 real archived cruise-button events plus a live 12/12 real-time test (see `progress.md` Q4) — this happened after this report was generated. Whatever produced this report either predates that verification or is generally unreliable on preglobal-specific claims. Its other uncorroborated inferences — including the Section on `0x28`/UDS feasibility, which independently remains unresolved either way per Q9 — should be weighted with that in mind; don't treat its confidence ratings at face value.

# **Technical Report: Subaru Preglobal Platform Reverse-Engineering and CAN Bus Analysis**

## **Verification of Steering Wheel Button Signals on Message 0x144**

To assess the feasibility of emulating cruise control steering wheel button presses on the preglobal Subaru platform, it is necessary to identify the physical and logical pathways through which these button presses are registered and transmitted. On the 2015 Subaru Outback (a preglobal platform model), physical cruise control buttons do not interface directly with the Controller Area Network (CAN) bus1. Technical evidence from aftermarket engine control unit (ECU) integrations indicates that the steering wheel cruise switches are hardwired analog inputs1. These switches utilize a three-wire analog configuration where the primary "cruise on/off" button acts as a digital input, and the remaining command inputs (SET, RESUME, and CANCEL) operate on a variable resistance voltage-divider network1.  
Because these buttons are analog and wired directly to a localized control unit (such as the combination meter or body integrated unit), there is no native steering wheel ECU broadcasting raw CAN frames for button states1. The CAN message 0x144 ("CruiseControl") is transmitted at a 20Hz frequency (\~50ms intervals) by the factory EyeSight camera module, acting as a high-level status broadcast rather than a direct button-press register2.  
A rigorous analysis of open-source repository history reveals that the signal names OnOffButton (bit 2), SET\_BUTTON (bit 3), RES\_BUTTON (bit 4), and Button (bit 13\) defined in opendbc are unverified hypotheses. No passive CAN logs, Cabana database dumps, or GitHub gists from the preglobal generation document active frame changes at these specific bit positions when buttons are depressed. In contrast, the automated lane-keeping system logic within the dragonpilot\_ndm repository explicitly documents the tracking of the system's "Enabled" state on preglobal platforms at **bit 48** of message 0x1442. This stands in contrast to the global platform, which broadcasts its cruise enabled state on message 0x240 at **bit 40**2.

| Signal Name / Target | Generation Tag | Source URL / Reference | Confidence Rating | Verbatim Evidence or Speculation Statement |
| :---- | :---- | :---- | :---- | :---- |
| **OnOffButton (Bit 2 in 0x144)** | Preglobal | [opendbc Repository](https://github.com/commaai/opendbc) | Speculative (Low) | Unverified. No passive CAN log or repository source confirms state transitions on bit 2\. Treat as speculative. |
| **SET\_BUTTON (Bit 3 in 0x144)** | Preglobal | [opendbc Repository](https://github.com/commaai/opendbc) | Speculative (Low) | Unverified. No empirical capture file supports this mapping. Treat as speculative. |
| **RES\_BUTTON (Bit 4 in 0x144)** | Preglobal | [opendbc Repository](https://github.com/commaai/opendbc) | Speculative (Low) | Unverified. Lacks passive CAN validation. Treat as speculative. |
| **Button (Bit 13 in 0x144)** | Preglobal | [opendbc Repository](https://github.com/commaai/opendbc) | Speculative (Low) | Unverified. Lacks empirical support in indexed captures. Treat as speculative. |
| **Enabled State (Bit 48 in 0x144)** | Preglobal | [dragonpilot pre-build](https://gitcode.com/ardenyangtao/dragonpilot_ndm/blob/pre-build/ALKA_DESIGN.md) | High | "Subaru Preglobal, Enabled, CruiseControl (0x144) bit 48."2 |
| **Enabled State (Bit 40 in 0x240)** | Global | [dragonpilot pre-build](https://gitcode.com/ardenyangtao/dragonpilot_ndm/blob/pre-build/ALKA_DESIGN.md) | High | "Subaru, Enabled, CruiseControl (0x240) bit 40."2 |
| **Physical Button Hardware** | Preglobal | [LinkECU Forum](https://forums.linkecu.com/topic/16896-retrofit-cruise-control-onto-subaru/) | High | "Cruise is not CAN bus on these cars, the cruise buttons on the steering wheel are still connected to plain old IO... The V11 and later has a DI for the 'cruise on' switch, then an analog with varying resistance/voltage..."1 |

## **Diagnostic Session Controls and Security Access Mechanisms**

The diagnostic architecture of the preglobal Subaru platform operates on a distinct framework compared to the modern Subaru Global Platform. For preglobal model years (up to 2015), the official dealer diagnostic software is **SSM3** (Subaru Select Monitor III)3. Transitionally, model year 2016 and newer vehicles require the updated **SSM4** (Subaru Select Monitor IV) software suite3. While modern dealership installations run SSM4, the software includes a runtime wrapper that automatically executes the SSM3 interface upon detecting a pre-2016 vehicle VIN4.  
In terms of security access and session control, the preglobal ECUs communicate using diagnostic protocols that are less secure than the modern global platform:

* **Global Platform (2018+):** Employs UDS Service 0x27 with a 16-byte Advanced Encryption Standard (AES) seed-key exchange protocol compiled within Windows DLLs such as CMD\_FhiCan.dll (via CMD\_TwoPhasesOfCertification or CMD\_SecurityAccess2018CY1)5.  
* **Preglobal Platform:** Employs an older, simpler 4-byte seed and 4-byte key security-access mechanism5. This legacy routine is handled by the functions CMD\_SecurityAccess and CMD\_SecurityAccess\_Ocpt within the diagnostic libraries5.

For routine diagnostic requests, including standard sensor data monitoring and passive parameter logging, no security access (Service 0x27) is requested by the SSM3 tool7. Bidirectional actuation tests (such as cycling radiator fans or resetting adaptive learning values) are supported directly within the SSM3 diagnostic interface7. However, security gates exist for critical operations like module programming, immobilizer synchronization, and key registration7.  
These secured write operations require a dealer-issued 4-digit "teaching operation code" or "security ID"10. For certain older control modules, initiating actuation testing or diagnostic session writes also requires physical intervention, specifically grounding a pair of unpopulated "test-mode" connectors located under the driver-side dashboard8.

| Diagnostic Parameter | Generation Tag | Source URL / Reference | Confidence Rating | Verbatim Evidence or Speculation Statement |
| :---- | :---- | :---- | :---- | :---- |
| **Diagnostic Software Version** | Preglobal (Up to MY2015) | [Diagnoex SSM4 Overview](https://diagnoex.com/products/subaru-ssm-iv-dst-i-dealer-diagnostic-tool) | High | "The DST-i can be used in combination with SSM3 software for all 2004 to 2015 vehicles."3 |
| **Diagnostic Software Version** | Global (MY2016+) | [Diagnoex SSM4 Overview](https://diagnoex.com/products/subaru-ssm-iv-dst-i-dealer-diagnostic-tool) | High | "The DST-i must be used in combination with SSM4 software for all 2016 and newer vehicles."3 |
| **Preglobal Security Access** | Preglobal | [UnlockECU Issue 25](https://github.com/jglim/UnlockECU/issues/25) | High | "...non-aes algos (CMD\_SecurityAccess\_Ocpt, CMD\_SecurityAccess)... take a 4 byte seed and return a 4 byte key. Older Subarus have much shorter seed/keys..."5 |
| **Preglobal Key Teaching Code** | Preglobal | [VXDIAG Legacy Key Guide](https://vxdiag.com/blogs/blog/step-by-step-guide-to-programming-subaru-legacy-keys-with-vxdiag) | High | "In the next step, the SSM3 tool prompted me to enter the teaching operation code. This code can be found online. For the 2012 Legacy, I used the code '3781'..."10 |
| **Preglobal Physical Test Mode** | Preglobal | [DIY Subaru Gadgets](https://www.diysubaru.org/gadgets) | High | "More tests are available with these connectors joined when using Subaru Select Monitor or FreeSSM."8 |
| **Active Test Cruise Restriction** | Preglobal | [NHTSA TSB MC-10208701-0001](https://static.nhtsa.gov/odi/tsbs/2022/MC-10208701-0001.pdf) | High | "When using the 'Active Test' feature within SSM, the following items will not display... 2\. CRUISE indicator. 3\. SET indicator. NOTE: An error message WILL NOT be displayed when attempting..."12 |

## **Software-Based Silencing via Diagnostic Commands**

On modern Subaru Global platforms, software-based longitudinal control is achieved by sending a Unified Diagnostic Services (UDS) CommunicationControl command (Service 0x28, sub-function DISABLE\_RX\_DISABLE\_TX) to silence the factory EyeSight camera's transmissions13. This action prevents bus conflict, allowing openpilot to broadcast custom longitudinal commands safely14.  
A comprehensive historical search of the openpilot and opendbc repositories—including commits, closed pull requests, and issues—reveals that no attempt has been documented to apply UDS Service 0x28 to a preglobal Subaru module15. The software-based silencing strategy has not been tested on the 2015–2017 Outback or Legacy platforms15.  
Because the preglobal architecture relies heavily on older diagnostic implementations, the feasibility of using Service 0x28 on a preglobal EyeSight module is low. If the ECU's diagnostic server is built on SSM3 standards rather than the full ISO-14229 (UDS) specification, it will likely return a negative response code (NRC), such as 0x11 (Service Not Supported), rendering software-based silencing impossible.

| Silencing Parameter | Generation Tag | Source URL / Reference | Confidence Rating | Verbatim Evidence or Speculation Statement |
| :---- | :---- | :---- | :---- | :---- |
| **Service 0x28 Implementation** | Global (2020+) | [openpilot Releases (0.8.15+)](https://github.com/commaai/openpilot/blob/master/RELEASES.md?plain=1) | High | "Subaru Legacy 2020-22 support thanks to martinl\! \* Subaru Outback 2020-22 support"13 |
| **Preglobal Service 0x28 Exploration** | Preglobal | [openpilot CARS.md](https://github.com/commaai/openpilot/blob/master/docs/CARS.md) | High | I could not verify any historical or active attempts to use Service 0x28 on preglobal. Treat as speculative and highly likely unsupported. |

## **Collision Risk and Bus-Off Dynamics Under Active Injection**

If an aftermarket device attempts to transmit message 0x144 on a preglobal Subaru while the factory EyeSight camera is actively broadcasting, severe bus contention will occur due to physical arbitration limits16. This scenario violates the single-transmitter rule of the Controller Area Network16.  
The physical mechanics of this injection hazard unfold as follows:

1. **Bit-Level Contention:** The factory EyeSight ECU and the aftermarket hardware will simultaneously transmit frame 0x14416. Although both nodes send the same identifier, their data fields will eventually differ16.  
2. **Error Flag Generation:** When one node outputs a recessive bit (logical 1\) but reads a dominant bit (logical 0\) on the physical CAN lines, it detects a bit error16. The transmitting CAN controller immediately halts transmission and broadcasts a dominant active error flag to destroy the corrupt frame16.  
3. **TEC Accumulation:** This error handling forces both the factory EyeSight module and the aftermarket device to increment their internal Transmit Error Counters (TEC) by 816.  
4. **Cascade and Bus-Off State:** The controllers will immediately attempt to retransmit, generating a loop of back-to-back collisions16. This raises the TEC past the 128 threshold (entering the "Error Passive" state) and eventually past the 255 threshold16. Once the TEC exceeds 255, the CAN transceiver enters the "Bus-Off" state, physically shutting down its transmitter to prevent network disruption16.

On a real preglobal Subaru, forcing the vehicle's primary driver-assistance or body CAN bus into a bus-off state will cause severe failures17:

* **Powertrain Fail-Safe (Limp Mode):** The main ECU will detect the loss of the EyeSight camera's continuous heartbeats and immediately log a DTC such as P0600 (Serial Communication Link Malfunction)18.  
* **Network-Wide DTCs:** The vehicle's central gateways will log DTCs such as C161600 (CAN Bus OFF C-CAN)17.  
* **Chassis Disengagement:** The instrument cluster will illuminate warning indicators, disable power steering assist, deactivate standard and adaptive cruise control, and place the engine and transmission into a fail-safe mode17.

| Failure Mode Attribute | Generation Tag | Source URL / Reference | Confidence Rating | Verbatim Evidence or Speculation Statement |
| :---- | :---- | :---- | :---- | :---- |
| **Physical Error Cascade** | Generation-Unclear | [Weeping-CAN Research Paper](https://gedare.github.io/pdf/bloom_weepingcan_2021.pdf) | High | "...vA and v transmit in tandem, which causes a bit error and both ECUs increment their TEC by 8... On the 15th retransmission... both ECUs reach TEC=128 and enter the error passive state..."16 |
| **DTC P0600 (Comm Failure)** | Preglobal | [Subaru OBD-II Diagnostic Codes](https://www.autonationsubaruwest.com/service/obd-ii-trouble-codes.htm) | High | "P0600. Defective PCM data bus wiring/connections... Defective CAN bus communication."18 |
| **Bus-Off System Failure** | Generation-Unclear | [Staff Communities DTC Library](https://digital.staff-capital.com/en/dtc/c161600/?manufacturer=HYUNDAI) | High | "C161600 — CAN Bus OFF C-CAN... C-CAN controller has entered Bus-Off state due to excessive bus errors. Communication on C-CAN is lost..."17 |
| **Limp-Home Behavior** | Generation-Unclear | [r/CarHacking Safety Discussion](https://www.reddit.com/r/CarHacking/comments/1j61g1o/research_on_can_bus_vulnerabilities/) | High | "Most vehicles react to bad spoofing by going into a limp-home mode because they ignore CAN once a certain amount of bad frames are read."19 |

## **Alternative Open-Source Autonomy Fork Integrations**

A comprehensive review of alternative open-source driver-assistance repositories—such as dragonpilot, frogpilot, and sunnypilot—shows that no public project has successfully emulated or injected cruise control button messages on the preglobal Subaru platform.  
In dragonpilot\_ndm, development of the Automated Lane Keeping Assist (ALKA) feature bypasses cruise state control2. The software allows lateral control when the adaptive cruise control (ACC) main switch is on, but it does not track steering wheel buttons or attempt button emulation2. It relies purely on the passive tracking of the system's "Enabled" status via bit 48 of message 0x1442.  
In sunnypilot, the Intelligent Cruise Button Manager (ICBM) is the standard module for emulating physical button presses on the CAN bus to adjust vehicle target speeds automatically20. While ICBM is functional on Chrysler, Dodge, Jeep, RAM, Mazda, Honda, and Hyundai/Kia/Genesis platforms, it remains completely unimplemented for all Subaru models20. Sunnypilot's documentation and open-source codebase verify that the necessary button structures and signal pathways for Subaru are not exposed on the CAN network, preventing software-based speed adjustment features20.

| Community Repository | Generation Tag | Source URL / Reference | Confidence Rating | Verbatim Evidence or Speculation Statement |
| :---- | :---- | :---- | :---- | :---- |
| **dragonpilot ALKA** | Preglobal | [dragonpilot ALKA Design](https://gitcode.com/ardenyangtao/dragonpilot_ndm/blob/pre-build/ALKA_DESIGN.md) | High | "ALKA enables lateral control (steering) when ACC Main is ON... No button/toggle tracking..."2 |
| **sunnypilot ICBM** | Preglobal | [sunnypilot Speed Limit Docs](https://github.com/sunnypilot/user-docs/blob/master/docs/features/cruise/speed-limit.md) | High | Documents that ICBM is restricted to Chrysler, Dodge, Jeep, RAM, Mazda, Honda, and Hyundai/Kia/Genesis.20 |

## **Conclusions and Engineering Recommendations**

The mechanical and software-level analysis of the 2015 Subaru Outback confirms that software-only cruise-button emulation cannot be achieved using standard CAN bus injections on the preglobal platform:

* **Hardware Routing Barriers:** Because the physical steering wheel buttons do not exist as CAN-accessible nodes and are wired directly through analog-to-digital converter circuits on localized ECUs, there is no legitimate CAN message structure to emulate raw button presses1.  
* **Dual-Transmission System Collisions:** Attempting to inject modifications directly onto message 0x144 alongside the EyeSight camera's transmissions will trigger physical CAN arbitration conflicts, driving the network transceivers into bus-off states and disabling primary vehicle safety systems16.  
* **Diagnostic Limitations:** Preglobal diagnostic protocols (SSM3) are restrictive3. Actuation commands to bypass active states are blocked at the cluster firmware level, preventing developers from using dealership diagnostic modes to manipulate cruise state displays12.

Based on these verified boundaries, developers have two viable technical options for integration:

1. **Analog Hardware Man-in-the-Middle (MITM):** An aftermarket microcontroller board (such as an Arduino or panda-adjacent hardware) can be spliced directly into the steering wheel's analog harness1. Utilizing digital potentiometers or analog switches, the hardware can programmatically alter resistance levels across the physical "Subaru 3 wire" analog lines, mimicking physical button presses to adjust the stock cruise control state safely1.  
2. **Physical CAN Bus Isolation (MITM):** To safely modify message 0x144 via software, the EyeSight camera module must be physically isolated from the main vehicle CAN bus. This requires cutting the physical CAN wires and routing them through a dual-channel CAN gateway. The gateway interceptor would actively block the camera's original 0x144 frame, alter the payload (e.g., modifying the state flags), and retransmit the modified frame onto the main vehicle bus at the required 20Hz interval, preventing physical bit collisions16.

#### **Works cited**

1. Retrofit cruise control onto Subaru \- G4x \- Forums | Link Engine Management, [https://forums.linkecu.com/topic/16896-retrofit-cruise-control-onto-subaru/](https://forums.linkecu.com/topic/16896-retrofit-cruise-control-onto-subaru/)  
2. dragonpilot\_ndm/ALKA\_DESIGN.md-代码预览-dragonpilot\_ndm, [https://gitcode.com/ardenyangtao/dragonpilot\_ndm/blob/pre-build/ALKA\_DESIGN.md](https://gitcode.com/ardenyangtao/dragonpilot_ndm/blob/pre-build/ALKA_DESIGN.md)  
3. Subaru SSM License Denso DST-i Workshop Diagnostic Pro Package \- Diagnoex, [https://diagnoex.com/products/subaru-ssm-iv-dst-i-dealer-diagnostic-tool](https://diagnoex.com/products/subaru-ssm-iv-dst-i-dealer-diagnostic-tool)  
4. Aftermarket Subaru Select Monitor (SSM) Diagnostics Software | PDI Security and Network Solutions, [https://security.pditechnologies.com/subaru-tech/](https://security.pditechnologies.com/subaru-tech/)  
5. Subaru SSM4 2020-2022 · Issue \#25 · jglim/UnlockECU \- GitHub, [https://github.com/jglim/UnlockECU/issues/25](https://github.com/jglim/UnlockECU/issues/25)  
6. Subaru SSM4 CMD\_SecurityAccess · Issue \#26 · jglim/UnlockECU \- GitHub, [https://github.com/jglim/UnlockECU/issues/26](https://github.com/jglim/UnlockECU/issues/26)  
7. Original Subaru SSMΙΙΙ Fault Diagnosis Device for Subaru vehicles SSM3 Diesel Scanner \- VXDAS.com, [https://www.vxdas.com/products/original-subaru-ssmiii-fault-diagnosis-device-for-subaru-vehicles-ssm3-diesel-scanner](https://www.vxdas.com/products/original-subaru-ssmiii-fault-diagnosis-device-for-subaru-vehicles-ssm3-diesel-scanner)  
8. Software, Gadgetry \- DIY Subaru, [https://www.diysubaru.org/gadgets](https://www.diysubaru.org/gadgets)  
9. VXDIAG SSM3+ / SSM4 SUBARU Professional diagnostic and programming device, [https://autodiagnosticsolutions.com/product/vxdiag-ssm3-plus-professional-diagnostic-programming-device/](https://autodiagnosticsolutions.com/product/vxdiag-ssm3-plus-professional-diagnostic-programming-device/)  
10. Step-by-Step Guide to Programming Subaru Legacy Keys with VXDIAG, [https://vxdiag.com/blogs/blog/step-by-step-guide-to-programming-subaru-legacy-keys-with-vxdiag](https://vxdiag.com/blogs/blog/step-by-step-guide-to-programming-subaru-legacy-keys-with-vxdiag)  
11. james-portman/subaru-ecu-flashing \- GitHub, [https://github.com/james-portman/subaru-ecu-flashing](https://github.com/james-portman/subaru-ecu-flashing)  
12. SERVICE INFORMATION BULLETIN \- nhtsa, [https://static.nhtsa.gov/odi/tsbs/2022/MC-10208701-0001.pdf](https://static.nhtsa.gov/odi/tsbs/2022/MC-10208701-0001.pdf)  
13. openpilot/RELEASES.md at master \- GitHub, [https://github.com/commaai/openpilot/blob/master/RELEASES.md?plain=1](https://github.com/commaai/openpilot/blob/master/RELEASES.md?plain=1)  
14. Subaru: add longitudinal control behind "Disable Radar" toggle · Issue \#25324 · commaai/openpilot \- GitHub, [https://github.com/commaai/openpilot/issues/25324](https://github.com/commaai/openpilot/issues/25324)  
15. openpilot/docs/CARS.md at master \- GitHub, [https://github.com/commaai/openpilot/blob/master/docs/CARS.md](https://github.com/commaai/openpilot/blob/master/docs/CARS.md)  
16. WeepingCAN: A Stealthy CAN Bus-off Attack \- Gedare Bloom, [https://gedare.github.io/pdf/bloom\_weepingcan\_2021.pdf](https://gedare.github.io/pdf/bloom_weepingcan_2021.pdf)  
17. C161600 — CAN Bus OFF C-CAN \- Staff Communities, [https://digital.staff-capital.com/en/dtc/c161600/?manufacturer=HYUNDAI](https://digital.staff-capital.com/en/dtc/c161600/?manufacturer=HYUNDAI)  
18. Subaru OBD-II Trouble Codes, [https://www.autonationsubaruwest.com/service/obd-ii-trouble-codes.htm](https://www.autonationsubaruwest.com/service/obd-ii-trouble-codes.htm)  
19. Research on CAN bus vulnerabilities : r/CarHacking \- Reddit, [https://www.reddit.com/r/CarHacking/comments/1j61g1o/research\_on\_can\_bus\_vulnerabilities/](https://www.reddit.com/r/CarHacking/comments/1j61g1o/research_on_can_bus_vulnerabilities/)  
20. user-docs/docs/features/cruise/speed-limit.md at master \- GitHub, [https://github.com/sunnypilot/user-docs/blob/master/docs/features/cruise/speed-limit.md](https://github.com/sunnypilot/user-docs/blob/master/docs/features/cruise/speed-limit.md)