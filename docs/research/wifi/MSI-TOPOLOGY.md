# MSI topology: three interrupt routes from PCIe0, and the one the driver takes

Written 2026-11-16. Scope: how a QCA6490 message-signalled interrupt reaches the
CPU on mondrian, which route the Pong driver actually uses, and what the device
tree says about the routes it does not use. This note exists because c6 armed an
MSI receiver and then waited 20 s for an event that never came
(`usblog-20261116-081646`), so "is the interrupt path right" has to be answerable
from the tree and the code rather than guessed from a silent console.

## 0. Conclusion first

| question | answer |
|---|---|
| Which route does the driver use? | The **DesignWare legacy** route: PARF `MSI0` (`1u << 23`) translates the endpoint's MSI write into **GIC SPI 140 = INTID 172**. No ITS, no LPI. |
| Does the device tree describe another route? | Yes: `/soc/qcom,pcie@1c00000` carries `msi-map` pointing at the **ITS** (`msi-controller@17140000`, phandle `0x237`), event bases `0x5980`/`0x5981`. Linux follows that one. |
| Is there a third node? | `/soc/qcom,pcie0_msi@0x17110040` owns 32 SPIs (768..799) and is `status = "disabled"`. Nothing in this tree uses it. |
| Why did the port choose legacy? | It needs one GIC SPI and no ITS driver, no LPI allocation, no `msi-map` parsing. c5 and c6 show the receiver arming and the DMA landing, so the route is live up to "the device has something to say". The phone's own Android kernel uses the ITS instead (§1.2), so legacy is a shortcut, not the vendor path. |
| What does it cost? | One shared INTID for all 32 vectors: the handler reads `MsiStatus` and clears it, and cannot tell which vector fired. Acceptable for bring-up; a per-vector route needs ITS. |

## 1. The three routes

### 1.1 Legacy: PARF MSI0 to SPI 140 (used)

| step | evidence |
|---|---|
| Endpoint writes to the MSI target address the host programmed | `PongWifiPlatform.cpp:560` `msiTarget()` returns `Iova + 0x40`; `:680` programs `MsiAddressLo/Hi` with the same value |
| The DesignWare core raises its internal MSI line | `PongWifiPlatform.cpp:42` `MsiEnable=0x828, MsiMask=0x82c, MsiStatus=0x830`; `:684` unmasks and enables after the GIC handler is attached |
| PARF maps that line onto MSI group 0 | `PongWifiPlatform.cpp:43` `ParfMsi0 = 1u << 23`; `:681` and `:684` set it in `PARF + 0x228` and clear the mask in `PARF + 0x22c` |
| The GIC sees SPI 140, INTID 172 | `PongWifiPlatform.cpp:43` `PcieGlobalIntid = 32 + 140`; live FDT `interrupt-map` first entry decodes to `0x8c = 140`, type `0x04` (level-high) |
| The kernel owns that SPI | `PongWifiPlatform.cpp:683` `armcpu_spi_attach(PcieGlobalIntid, ...)`; `ArmCpu.cpp:423` is the entry, `ArmCpu.cpp:403` panics on `unowned SPI` |

### 1.2 ITS: `msi-map` to `msi-controller@17140000` (not used)

Live FDT: `/soc/qcom,pcie@1c00000` `msi-map = <0x00 0x237 0x5980 0x01 0x100 0x237 0x5981 0x01>`.

Reading it the way `Documentation/devicetree/bindings/pci/pci-msi.txt` says:
four-cell tuples of (PCI RID, MSI controller phandle, ITS DeviceID, number of
events). So RID `0x00` and RID `0x100` are both mapped to ITS `0x237`, with
event-ID bases `0x5980` and `0x5981`. `0x5980 = 22912`, and because a GIC-v3
LPI number is `8192 + eventid`, the Linux route would land at INTIDs
`31104+` — nothing like 172. That difference is the tell: the two routes cannot
be confused, and `0x5980` is not a SPI.

The controller node: `/soc/interrupt-controller@17100000` is `arm,gic-v3`, and
its child `msi-controller@17140000` (phandle `0x237`, alias `gic_its`) is the
ITS. Using this route would require ITS support, LPI configuration tables in
memory, and `msi-map` parsing in the kernel — none of which this port has.

**The phone's own kernel takes this route.** `/proc/interrupts` captured from
Android on this device lists ITS-MSI 524289..524306 (32 vectors) for `mhi`,
`pci0_wlan_ce_*` and `pci0_wlan_grp_dp_*` (`interrupts.txt` and
`msi_irqs.txt` in the reference collection, summarised in
`GAP-ANALYSIS.md` §2.4). So the hardware and the vendor software both work
through the ITS; the legacy PARF route is a *porting shortcut*, chosen because
it needs one SPI and no ITS driver. That distinction matters when reading a
failure: a route that Linux never uses is not automatically wrong, but it is
unproven on this silicon beyond the SBL phase, which is exactly what c6 shows
(READY reached, MISSION event missing).

### 1.3 The disabled 32-SPI block (not used, not needed)

`/soc/qcom,pcie0_msi@0x17110040` declares 32 SPIs starting at 768 and is
`status = "disabled"` in the live tree. It is the "one SPI per vector" fallback
for a GIC without ITS. Since we take the PARF route and Linux takes the ITS
route, nothing selects it; it is listed here only so a future reader does not
mistake the 768..799 block for the route in use.

## 2. What the driver can and cannot see on the legacy route

- All 32 vectors share INTID 172. `irq()` (`PongWifiPlatform.cpp:645`) reads
  `MsiStatus`, writes it back to clear, and increments a counter. It cannot say
  which vector fired; ath11k's per-vector handlers are driven by the MHI and CE
  rings, not by the interrupt identity.
- `MsiStatus == 0` on entry is therefore normal: it means "this GIC interrupt
  was for us, but by the time we looked the aggregator had nothing pending".
  c7 adds a separate entry counter exactly because c6 could not tell that case
  apart from "the MSI never reached the GIC at all".
- After 64 consecutive empty entries the driver disables the MSI and clears the
  PARF bit (`PongWifiPlatform.cpp:655`), so a wedged route fails loudly rather
  than spinning.

## 3. Evidence from the flights

| cell | line | reading |
|---|---|---|
| c5 (`usblog-20261116-075300`) | `:589` `DesignWare MSI receiver armed on Pong PCIe0 SPI140` | attach succeeded; the SPI has an owner, so the `ArmCpu.cpp:403` panic path was not taken |
| c6 (`usblog-20261116-081646`) | `:592` `ath11k: MSI vectors: 32` | the endpoint accepted the vector count the host programmed |
| c6 | `:586` `64MiB wired DMA mapped from 16384 spans` | the target address written into `MsiAddressLo/Hi` is inside a live DMA mapping |
| c6 | `:620` `Pong MHI: device in READY state` then `:624` `failed to power up mhi: -110` | the route carried the READY handshake; what did not arrive is the later EE event |

The last row is the reason this note is careful about "the interrupt path is
fine": the route demonstrably delivered events during the SBL phase, so a
missing MISSION-mode event is a device-side or ring-side question, not a
topology question.

## 4. If the route ever has to change

Moving to ITS would mean: parse `msi-map`, allocate and program LPI
properties, keep a per-vector handler table, and give up the single-INTID
simplicity that makes `armcpu_spi_attach` enough today. Nothing in the current
failure points there. The legacy route stays until something proves it cannot
carry the traffic.
