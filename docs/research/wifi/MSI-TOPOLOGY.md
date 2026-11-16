# MSI topology: three interrupt routes from PCIe0, and the one the driver takes

Written 2026-11-16. Scope: how a QCA6490 message-signalled interrupt reaches the
CPU on mondrian, which route the Pong driver actually uses, and what the device
tree says about the routes it does not use. This note exists because c6 armed an
MSI receiver and then waited 20 s for an event that never came
(`usblog-20261116-081646`), so "is the interrupt path right" has to be answerable
from the tree and the code rather than guessed from a silent console. c7
(`usblog-20261116-122546`) then instrumented both ends of the route and showed
that it has not carried a single interrupt yet, which is the reading this note
now records in §3.

## 0. Conclusion first

| question | answer |
|---|---|
| Which route does the driver use? | The **DesignWare legacy** route: PARF `MSI0` (`1u << 23`) translates the endpoint MSI write into **GIC SPI 140 = INTID 172**. No ITS, no LPI. |
| Does the device tree describe another route? | Yes: `/soc/qcom,pcie@1c00000` carries `msi-map` pointing at the **ITS** (`msi-controller@17140000`, phandle `0x237`), event bases `0x5980`/`0x5981`. Linux follows that one. |
| Is there a third node? | `/soc/qcom,pcie0_msi@0x17110040` owns 32 SPIs (768..799) and is `status = "disabled"`. Nothing in this tree uses it. |
| Why legacy rather than ITS? | Because the ITS route needs a driver this kernel does not have, and the legacy route needs one GIC SPI that `ArmCpu` already dispatches. Legacy is the only route that **exists** today, not the route that is **known to be right** — §4 states the three sources and the two known risks. |
| What does it cost? | One shared INTID for all 32 vectors: the handler reads `MsiStatus` and clears it, and cannot tell which vector fired. Acceptable for bring-up; a per-vector route needs ITS. |
| Has the route carried an interrupt yet? | **No.** c7 counted zero entries in `PongWifiPlatform::irq()` and zero advances of the MHI event ring. READY was reached by polling `MHISTATUS`, not by an interrupt, so nothing so far proves the route delivers anything. See §3. |

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

**The phone kernel takes this route.** `/proc/interrupts` captured from
Android on this device lists ITS-MSI 524289..524306 (32 vectors) for `mhi`,
`pci0_wlan_ce_*` and `pci0_wlan_grp_dp_*` (`interrupts.txt` and
`msi_irqs.txt` in the reference collection, summarised in
`GAP-ANALYSIS.md` §2.4). So the hardware and the vendor software both work
through the ITS; the legacy PARF route is a *porting shortcut*, chosen because
it needs one SPI and no ITS driver. That distinction matters when reading a
failure: a route that Linux never uses is not automatically wrong, but it is
unproven on this silicon, and c7 shows it has not carried anything yet.

### 1.3 The disabled 32-SPI block (not used, not needed)

`/soc/qcom,pcie0_msi@0x17110040` declares 32 SPIs starting at 768 and is
`status = "disabled"` in the live tree. It is the "one SPI per vector" fallback
for a GIC without ITS. Since we take the PARF route and Linux takes the ITS
route, nothing selects it; it is listed here only so a future reader does not
mistake the 768..799 block for the route in use.

## 2. What the driver can and cannot see on the legacy route

- All 32 vectors share INTID 172. `irq()` (`PongWifiPlatform.cpp:645`) reads
  `MsiStatus`, writes it back to clear, and increments a counter. It cannot say
  which vector fired; ath11k per-vector handlers are driven by the MHI and CE
  rings, not by the interrupt identity.
- `MsiStatus == 0` on entry is therefore normal: it means "this GIC interrupt
  was for us, but by the time we looked the aggregator had nothing pending".
  c7 added a separate entry counter (`msiEntries`, `PongWifiPlatform.cpp:566`,
  exactly because c6 could not tell that case apart from "the MSI never reached
  the GIC at all". In c7 **both** counters read zero, so the ambiguity is gone:
  the handler never ran.
- After 64 consecutive empty entries the driver disables the MSI and clears the
  PARF bit (`PongWifiPlatform.cpp:655`), so a wedged route fails loudly rather
  than spinning.
- The MHI-level `Pong MHI: irq entered` line is **not** MSI evidence. The
  compatibility shim raises all 64 shim IRQs on every pump
  (`PongAth11k.c:83` `lx_irq_raise_all(); lx_pump();`), so the MHI handler runs
  whether or not a real interrupt arrived. Only the `QCA6490 MSI entered the GIC
  handler` line proves the GIC delivered something.

## 3. Evidence from the flights

| cell | line | reading |
|---|---|---|
| c5 (`usblog-20261116-075300`) | `:589` `DesignWare MSI receiver armed on Pong PCIe0 SPI140` | `armcpu_spi_attach` returned success; the SPI has an owner, so the `ArmCpu.cpp:403` panic path was not taken, and `GICD_ISENABLER` bit 140 is set |
| c6 (`usblog-20261116-081646`) | `:592` `ath11k: MSI vectors: 32` | the endpoint accepted the vector count the host programmed |
| c6 | `:586` `64MiB wired DMA mapped from 16384 spans` | the target address written into `MsiAddressLo/Hi` is inside a live DMA mapping |
| c6 | `:620` `Pong MHI: device in READY state` then `:624` `failed to power up mhi: -110` | the host reached READY; what did not arrive is the EE event that follows |
| c7 (`usblog-20261116-122546`) | `MSI entered the GIC handler` 0 times, `MsiStatus 0` 0 times | the handler was never entered, so the GIC raised nothing on INTID 172 |
| c7 | `:608` `Pong MHI: irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00`, then `:610`/`:612`/`:620` `found no new events` | the event ring read pointer never moved: the device wrote nothing into it for the whole 20 s |
| c7 | `:632` `timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200` | decoded with `common.h:111-115`: `MHISTATUS` says MHISTATE=1 READY, READY bit set, SYSERR clear; `MHICTRL` says the host already asked for M0. The device sits in READY, never raises the EE event, and reports `BHI_EXECENV = 1` (SBL) |

The last three rows correct what an earlier revision of this note claimed. c6
was read as "the route delivered the READY handshake"; it did not. READY is
read by polling `MHISTATUS_READY_MASK` (`pm.c:186-198`
`mhi_poll_reg_field`, 25 ms interval), so it needs no interrupt at all, and the
event ring read pointer in c7 never moved off the wrap value the host itself
wrote (`pm.c` sets `*ring->ctxt_wp` to `base + len - el_size` and rings the ER
doorbell). Nothing in c5, c6 or c7 shows a single interrupt reaching the CPU.

## 4. Why PARF legacy rather than ITS

Three sources, in the order that decides the question.

**① The device tree offers both routes, and they are distinguishable.** The
legacy route is the `interrupt-map` first entry of `/soc/qcom,pcie@1c00000`:
`<0x00 0x00 0x00 0x00 0x01 0x00 0x8c 0x04>` → parent `0x01` (the GIC), IRQ
`0x8c = 140`, type `0x04` (level-high), i.e. INTID 172. The ITS route is the
`msi-map` on the same node, `<0x00 0x237 0x5980 0x01 0x100 0x237 0x5981 0x01>`
→ phandle `0x237` = `msi-controller@17140000` (`gic_its`), event bases `0x5980`
and `0x5981`, which as LPIs are INTIDs `31104+`. Two different address spaces;
picking one is a decision, not an accident.

**② This kernel has no ITS or LPI support at all.** Measured on the tree this
build compiles (repository excluding `docs/` and `.git`, and the XNU work tree):
`GITS_`, `GITS_TRANSLATER`, `gic_its`, `lpi_` and `LPI` each match **zero
files**. The only `ITS` hits are licence boilerplate (`LICENSE` files, `DiagFont.h`) and three
comments (`PongWifiPci.cpp:10`, `PongWifiPlatform.cpp:450-452`,
`PongWifi/README.md:22`). What the tree does have is
a direct SPI path: `ArmCpu.cpp:423` `armcpu_spi_attach(intid, edge, handler,
context, readback, router)` writes `GICD_IGROUPR`, `GICD_IPRIORITYR`,
`GICD_ICFGR`, `GICD_IROUTER` and `GICD_ISENABLER` for one INTID and registers a
handler in the four-slot `gSpi[]` table; `ArmCpu.cpp:381-421` dispatches by
INTID and panics on an unowned SPI. `PongAdrenoCp.cpp:388` uses the same call
for SPI 332. The comment at `PongWifiPlatform.cpp:452` states the choice
plainly: "Pong root interrupt map routes int_global_int to SPI140. Use the
DesignWare MSI receiver already implemented in this core; GIC MBIS and an
unimplemented ITS command queue are not prerequisites for this path."

**③ So legacy is the only route that exists, not the route proven right.** The
honest statement is: the ITS route would need an ITS driver, LPI property and
pending tables, and `msi-map` parsing, none of which exist here; the legacy
route needs one SPI and one PARF bit, both of which exist. Choosing it is a
sequencing decision — bring the endpoint up on the path that compiles today —
and it carries two known risks, both of which look exactly like silence:

- **Risk A — the endpoint may not write where we point it.** We program the
  endpoint MSI capability (`nw_pci.c:31-46`, `cfg_write(msi_cap + 4, lo)` with
  `lo = 0xa0000040`) and map `0xa0000040` through the SMMU to a retained landing
  page (`PongWifiPlatform.cpp:41` Iova, `:448-527` isolation, `:454` msiPage,
  `:464` `ranges[0]`). If the QCA6490 firmware raises interrupts only through
  the ITS doorbell (`GITS_TRANSLATER`,
  `0x17140000 + 0x40 = 0x17140040`, device ID as data), nothing ever writes to
  `0xa0000040`, `MsiStatus` reads 0 forever, and the console is identical to
  "the MSI never reached the GIC".
- **Risk B — the write may not be claimed or routed.** Even if the endpoint
  writes, the DesignWare core has to claim it (a match against `MSI_ADDR_L/H`,
  `0x820`/`0x824`) and PARF has to map it onto MSI group 0 (`PARF + 0x228` bit
  `1u << 23` set, `PARF + 0x22c` mask clear). We program all of those, but no
  flight proves any of them took effect: an unclaimed write simply lands in the
  SMMU-mapped landing page and raises no interrupt, which is again silence.

These two risks are why c7 counts entries at the GIC handler instead of
trusting `MsiStatus`, and why the next step on a silent route is to read back
the three enable points (`PARF + 0x228`, DBI `MsiEnable`, the GIC line
`armcpu_spi_attach` returned) before touching the INTID.

## 5. If the route ever has to change

Moving to ITS would mean: parse `msi-map`, allocate and program LPI
properties, keep a per-vector handler table, and give up the single-INTID
simplicity that makes `armcpu_spi_attach` enough today. Nothing in the current
failure points there yet — the failure is upstream of the route, in whether the
endpoint writes at all. The legacy route stays until something proves it cannot
carry the traffic.
