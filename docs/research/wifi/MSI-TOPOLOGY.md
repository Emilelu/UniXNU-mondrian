# MSI topology: configured routes and the limits of c7 evidence

Written 2026-11-16; corrected after Lead's 15:12/15:18 review. This note
separates what the host programs, what the live DT describes, and what the
console actually observed. c8 is held; this review changes no interrupt code,
MSI address or INTID.

## 0. Conclusion first

| question | evidence-bounded answer |
|---|---|
| What does the current driver configure? | DesignWare MSI reception and PARF group 0, with a direct GIC **SPI 140 = architectural INTID 172** handler. This is the intended route, not a proven end-to-end route. |
| What other route does DT describe? | PCIe0 `msi-map` targets ITS phandle `0x237`; its MSI cells are DeviceIDs `0x5980`/`0x5981`, **not** EventIDs or LPI INTIDs. |
| Is there another SPI block? | `/soc/qcom,pcie0_msi@0x17110040` declares SPIs 768..799 but is disabled. |
| Why choose legacy? | This XNU tree has a direct-SPI dispatcher, but no ITS driver/LPI management. Legacy was the implementable bring-up choice, not a correctness proof. |
| Did c7 prove an interrupt arrived? | No GIC-entry or nonzero-MSI-status message was observed in this capture. The MHI handler invocation is shim-replayed and is not hardware interrupt evidence. |
| Did c7 prove the device never sent MSI? | **No.** An absent log is not a trace of the device's writes, and does not establish an SBL protocol rule. |

## 1. The three routes

### 1.1 Current host configuration: DesignWare/PARF and SPI 140

Source locations refer to [PongWifiPlatform.cpp](../../../drivers/PongWifi/PongWifiPlatform.cpp)
in the c8 source revision `dd3154a`:

| host operation | source |
|---|---|
| Return target `Iova + 0x40 = 0xa0000040`, data 0 | `drivers/PongWifi/PongWifiPlatform.cpp:41,560`, `msiTarget()` |
| Program DesignWare address registers `0x820/0x824`; status/mask/enable `0x830/0x82c/0x828` | `drivers/PongWifi/PongWifiPlatform.cpp:42,679-684` |
| Program PARF `+0x228` and `+0x22c` with the `ParfMsi0 = 1u << 23` sequence | `drivers/PongWifi/PongWifiPlatform.cpp:43,681-684` |
| Register `armcpu_spi_attach(32 + 140, false, irq, ...)` | `drivers/PongWifi/PongWifiPlatform.cpp:683` |

[ArmCpu.cpp](../../../drivers/ArmCpu/ArmCpu.cpp):423-460 assigns an owner and
programs GICD group, priority, trigger, affinity and enable using the
**architectural INTID 172**, not bit 140. Its dispatch at
`drivers/ArmCpu/ArmCpu.cpp:381-421` masks the SPI around the callback and panics
on an unowned SPI. Successful attach and the `receiver armed` print show that
registration returned success; they do not prove an endpoint write arrived.

### 1.2 DT route: RequesterID to ITS DeviceID

Live DT PCIe0 `msi-map`:

`<0x00 0x237 0x5980 0x01 0x100 0x237 0x5981 0x01>`.

The [PCI MSI binding](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/devicetree/bindings/pci/pci-msi.txt)
defines each tuple as `(rid-base, controller, msi-base, length)`. The final
cell counts **consecutive RIDs**, not events. The
[GICv3 ITS binding](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/devicetree/bindings/interrupt-controller/arm,gic-v3.yaml)
defines its single MSI cell as the **DeviceID**. Thus these tuples map RID
`0x00` to DeviceID `0x5980` and RID `0x100` to DeviceID `0x5981` on ITS `0x237`.
They do not identify an EventID, and do not yield `8192 + 0x5980` as an LPI.
The previous `31104+` claim was wrong: ITS maps (DeviceID, EventID) to a
separately allocated LPI through its translation tables.

The live controller node is `arm,gic-v3-its` at control base `0x17140000`,
phandle `0x237`. Android's captured `/proc/interrupts` has ITS-MSI labels
524289..524306 for MHI/CE/DP, as recorded in
[GAP-ANALYSIS.md §2.4](GAP-ANALYSIS.md).
Those displayed numbers are not a reason to infer EventID or LPI allocation
from the DT DeviceID. The allocation log says 32 MSI vectors; the displayed
range alone is not a count of all allocated vectors.

### 1.3 Disabled 32-SPI block

`/soc/qcom,pcie0_msi@0x17110040` declares 32 SPIs starting at 768 and is
`status = "disabled"` in the captured live tree. It is neither the current
direct-SPI configuration nor evidence of the ITS translation actually used.

## 2. Which observations distinguish hardware delivery from shim replay?

- `PongWifiPlatform::irq()` increments `msiEntries` on entry and
  `msiArrivals` only when DBI `MsiStatus` is nonzero
  (`drivers/PongWifi/PongWifiPlatform.cpp:642-657`). A GIC-entry message would
  establish callback delivery; nonzero status would additionally establish
  observed pending MSI bits. Neither alone validates all vectors or MHI DMA.
- A zero status on entry is an **empty/spurious or already-cleared status
  observation**, not automatically normal or proof of a valid MSI. The existing
  code disables reception after 64 consecutive empty callbacks. This review
  does not endorse its interrupt-context logging or modify it.
- `Pong MHI: irq entered` proves only that the software handler was called.
  [PongAth11k.c](../../../drivers/PongWifi/ath11k/PongAth11k.c):83 calls
  `lx_irq_raise_all(); lx_pump();`. In the generated runtime
  `/opt/k60/trees/k60build/wifi/ath11k-c8/lx_rt_pong.c:597` sets every registered
  line pending; `lx_rt_pong.c:355` repeats that once per millisecond while
  `g_irq_polling` is enabled, initially 1 at `lx_rt_pong.c:32`. This can
  dispatch MHI events without any observed GIC delivery.
- c7's capture contains neither the GIC-entry message nor a nonzero-status
  delivery message. No terminal dump of the numeric counters was emitted on
  the failed bring-up path. Therefore write **entry not observed in this
  capture**, not measured zero counters or proof that SBL cannot send MSI.

## 3. What the flights establish

Console: `E:/k60-work/evidence/usblog-20261116-122546/console.log`.

| observation | supported reading |
|---|---|
| c5/c7 `DesignWare MSI receiver armed on Pong PCIe0 SPI140` | attach returned success; not an interrupt-arrival test |
| c6 `ath11k: MSI vectors: 32` | host MSI allocation reported 32; not device delivery |
| c7: no `MSI entered the GIC handler` / `MSI delivered` message | no corresponding delivery observed in this capture |
| c7:608 `irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00`; :610/:612/:620 `found no new events` | host-visible event ring appears empty on these samples; shim replay explains invocation |
| c7:632 `ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200` | at timeout: cached EE=PBL, software PM=**POR** (BIT(1)); hardware EE=SBL, hardware state=READY, SYSERR clear; host requests M0 |

READY is polled at `drivers/bus/mhi/host/pm.c:186-198`, so it proves no
interrupt. Event-context `rp` is initially written by the host to the ring
base (`drivers/bus/mhi/host/init.c:391-395`); READY changes `wp` to the last
element, not `rp` (`drivers/bus/mhi/host/pm.c:239-246`). An unchanged host
read is not independent proof that the device fetched or updated any context.
See [MHI-STATE-MACHINE.md](MHI-STATE-MACHINE.md) for the remaining hypotheses.

## 4. Why PARF legacy rather than ITS — and what is still unknown

Three sources support the implementation choice, not a root-cause verdict:

1. Live PCIe0 `interrupt-map` begins
   `<0x00 0x00 0x00 0x00 0x01 0x00 0x8c 0x04>`, describing parent GIC
   `0x01`, SPI `0x8c = 140`, level-high; DT also describes the ITS route
   in §1.2. Neither DT tuple demonstrates working legacy MSI aggregation.
2. The c7/c8 XNU source survey found no ITS/LPI implementation (`GITS_`,
   `GITS_TRANSLATER`, `gic_its`, `lpi_`, `LPI`: zero files in the
   surveyed kernel/driver source, excluding documentation). The direct SPI
   API exists; [PongAdrenoCp.cpp](../../../drivers/PongAdreno/PongAdrenoCp.cpp):388
   also uses `armcpu_spi_attach` for INTID 332.
3. An ITS path needs command queues, DeviceID/EventID translation and LPI
   property/pending tables. Legacy reuses existing code. That explains the
   bring-up shortcut, but does not prove the endpoint, DesignWare and PARF
   combination works on K60.

**ITS address/data correction.** The actual pinned Linux header
`include/linux/irqchip/arm-gic-v3.h:380` defines
`GITS_TRANSLATER = 0x10040`. If the ITS control base is `0x17140000`, its
untranslated physical TRANSLATER address is therefore **`0x17150040`**,
not `0x17140040`. The
[Linux ITS driver](https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/irqchip/irq-gic-v3-its.c)
`its_irq_get_msi_base()` adds this offset; `its_irq_compose_msi_msg()` puts
`its_get_event_id(d)` in MSI **data**, then permits IOMMU MSI-address
translation. DeviceID is associated with the requester/DT mapping, not put in
data. A physical calculation is not evidence of the endpoint-visible address
or the actual vendor routing on this phone.

The endpoint is currently programmed with `0xa0000040`, within a retained
SMMU-mapped landing page (`drivers/PongWifi/PongWifiPlatform.cpp:448-527`).
Whether its MSI writes reach the intended receiver, whether the receiver
claims them, and whether PARF/GIC forwards them remain unverified. The old
claim “firmware only recognises ITS at base+0x40 with DeviceID as data” is
withdrawn: both address/data were wrong, and no evidence established that
firmware restriction. Likewise, an unclaimed write is not proven to land in
RAM; the platform routing and SMMU treatment must be established, not assumed.

## 5. Review boundary

c7 remains useful register/console evidence. It does not locate the fault
upstream or downstream of the interrupt route. DMA visibility, doorbells,
device M0 transition and shim scheduling are still candidates. No ITS driver,
MSI target or INTID change is authorised by this review; c8 remains held.
