# Failure-reachable WiFi snapshot proposal

**Status: review only; NOT applied. c8 remains HOLD.** No build, rebuild, device
boot, current image/manifest change, MSI address/INTID/segment/window change is
part of this proposal. The accompanying [unapplied diff](<../../../scripts/proposals/wifi-failure-snapshot.diff>) is a review artifact, not a ready-to-build generator patch.

## Scope and reachability

The full MHI snapshot covers **only the non-mission return from
mhi_sync_power_up()**. It runs after the wait has returned but **before
mhi_power_down(c,false)** destroys the pre-failure state. It does not cover an
immediate mhi_async_power_up error, every firmware-load error, later crash, or
all failure paths. The small board-only pre/post-cleanup snapshots also run at
the existing worker done label. This is deliberately not advertised as complete
failure coverage.

Existing evidence: [platform:690](<../../../drivers/PongWifi/PongWifiPlatform.cpp#L690>) branches to done when nw_wifi_start fails; the success loop and
net-conditional periodic print at [platform:692–711](<../../../drivers/PongWifi/PongWifiPlatform.cpp#L692-L711>) are never reached in c7. Their absence says nothing about msiArrivals.
The prospective insertion point is generated c8 pm.c:1307–1308, immediately
before mhi_power_down; its source-tree equivalent is Linux 7.0.14
 drivers/bus/mhi/host/pm.c:1294–1295. The latter is outside this repository.

## What is collected (worker context only)

| Layer | Values | Interpretation boundary |
| --- | --- | --- |
| Hardware dispatch | existing ArmCpu SPI dispatcher callback count for INTID 172 (incremented before callback at ArmCpu.cpp:407); GICD ISENABLER, ISPENDR, ISACTIVER and IROUTER via existing gDist | count measures GIC dispatch, not logical Linux IRQ calls; no second GIC mapping |
| Receiver callback | existing msiEntries, msiArrivals (callback with nonzero MsiStatus), msiEmptyStatus | entries are not number of individual vector bits; beginning/end entry count exposes some races |
| Final receiver | DBI MSI enable/mask/status, PARF group mask before power-down, and pre/post worker cleanup | read only; existing cleanup writes remain visibly separate |
| Software shim | pump calls, polling raises, all raise_all calls, logical IRQ dispatches, polling enabled | never label these MSI arrivals; lx_irq_raise_all marks registered IRQs pending even without endpoint interrupts |
| MHI registers | cached EE/POR plus MHICTRL/MHISTATUS/BHI_EXECENV, CCABAP/ECABAP/CRCBAP low/high, control/data base/limit, ERDBOFF/CHDBOFF; each read return code | low/high parts are not an atomic 64-bit read; errors do not become successful zero values |
| Context ranges | CH/ER/CMD actual CPU pointers, bus addresses and allocation lengths | compare with inclusive controller envelope and retained arena; no physical-zero inference |
| ER state | CPU base/host rp/wp; bus base/len/alloc/element size; db_addr, ctxt_wp; host-visible context rbase/rlen/rp/wp/msivec | CPU-visible values only, not proof device consumed a context or performed DMA |

The existing ISR has logging. The proposal removes those prints and keeps only
existing counter/ACK/wakeup behavior; **no new logging, allocation or snapshot
calls enter interrupt context**. See [ArmCpu:386–420](<../../../drivers/ArmCpu/ArmCpu.cpp#L386-L420>) and [platform:642–657](<../../../drivers/PongWifi/PongWifiPlatform.cpp#L642-L657>).

PARF +0x228 is an existing ACK write site, not an established safe status-read
register in the audited evidence. This proposal **does not read it**, invent a
clear operation, or infer that a mask bit proves signal routing. Additional
PARF status reads need a documented read-semantics source first. DBI +0x830
already has read/W1C usage in the callback; the snapshot performs no W1C write.

## Mapping checks and limits

The current source maps Linux dma_alloc_coherent to lx_dma_alloc, then to the
board dmaAlloc. The board assigns both CPU and bus addresses inside the retained
arena ([platform:537](<../../../drivers/PongWifi/PongWifiPlatform.cpp#L537>));
dmaMap uses the same arithmetic at [platform:541](<../../../drivers/PongWifi/PongWifiPlatform.cpp#L541>).
This is a current-source check, not historical c8 compile attestation:

- DMA arena bus interval is [Iova+4096, Iova+4096+ArenaBytes); the separate
  retained MSI landing page [Iova,Iova+4096) is **not** a context allocation.
- For nonzero length n, inclusive envelope containment is checked without
  addition overflow: bus >= low, bus <= high, n-1 <= high-bus.
- Arena containment similarly uses n <= end-bus after bus bounds, and CPU
  pointer subtraction only after pointer bounds. CPU-to-bus exact match is
  checked separately from containment. A failed ER context check prevents its
  CPU dereference. Zero length is not a valid allocated range.
- Check aligned ring allocation span (pre_aligned/dma_handle/alloc_size) and
  active span (base/iommu_base/len) separately. The emitted checks compare
  context rbase/rlen with ring bus/len, validate host and shared rp/wp bounds
  and element alignment, and compare ctxt_wp with the context wp address.
- The reviewer must compare CCABAP, ECABAP and CRCBAP register pairs with the
  emitted CH, ER and CMD context bus addresses. These are sequential reads;
  neither that comparison nor range validation changes device state.

**Blocker to promotion:** verify generated dma_alloc_coherent routes these
allocations through the retained arena in the exact candidate. If some context
uses a different allocator, classify it explicitly and do not weaken the guard
until that allocator's valid CPU/bus mapping is documented. Range validation is
host bookkeeping, **not** a page-table walk, cache coherency test, proof of
current SMMU translation, or proof of device DMA visibility. No invalidation,
cache cleaning, doorbell readback or payload bytes are added.

## Stability and integration blockers

1. Snapshot reads are sequential, not a globally atomic event. ISR count can
   change between lines; entries start/end helps identify but cannot eliminate
   racing reads. Shared packed context fields can change or tear. Logging also
   changes timing. Unchanged rp never proves absence of device work.
2. Snapshot is inside the existing cooperative worker, before power-down; it
   does not call lx_pump, schedule work, lock the MHI transition queue, or write
   cached EE/PM state. Existing powered-MMIO guard protects board reads. A
   logical access failure cannot guarantee the interconnect will not hang if
   hardware power disappeared; promotion needs exact power-lifetime review.
3. The diff targets repository-owned files only. Linux MHI pm.c is transformed
   in-memory by a new strict generator helper after the existing patch pairs;
   the shared shim source is instrumented after the timer adapter and before
   writing generated lx_rt_pong.c. Both transformations require every anchor
   exactly once. No generated or external source is edited by this task. The
   proposed allowlist adds only the two nw_wifi-prefixed board diagnostics;
   their prefix survives the existing namespace rule. Generator execution,
   compile/link and hardware behavior remain untested.
4. No undocumented BHIE status-clear, transfer retry, protocol-sequence change,
   MSI data/address rewrite or extra GIC ownership slot is proposed.

## Host/static validation (not driver validation)

Run from the repository:

    python3 scripts/tests/test-wifi-failure-snapshot-proposal.py

The test reconstructs the proposed files only in memory, parses the resulting
generator AST, and executes selected pure source transformers. It checks the
timeout hook before power-down, unchanged GIC dispatcher, absence of snapshot
MMIO writes and ISR logging, software counter labels, and range/ring boundaries.
It neither writes reconstructed files nor compiles C/C++ or validates hardware.

With --pm-source and --shim-source, it also checks exact retained source anchors
and the existing timer adapter followed by the new shim instrumentation.
Eight tests passed against retained c8 MHI pm.c and shared lx_rt.c on 2026-11-16.
A separate git apply --check passed; no patch was applied. These results verify
host transformations, not generator build/link output or device behavior.
Parent must independently inspect the final diff and rerun this test before
committing the proposal. **c8 remains HOLD after these host tests pass.**
