# Candidate lifetime audit: MHI allocations and powered MMIO

**Status: review only; c8 remains HOLD.** This is an offline, read-only source and
evidence audit for Lead 19:57. It neither applies a diff nor authorizes a build,
boot, device action, c8 execution, or any change to the active driver, generator,
gate, board, status, done state, or patch series. No C/C++ compiler was run.

## 0. Scope, inputs and identity boundary

The audit base is `a47b47e1f0e10632df0e887d8054158483657072` on
`feat/wifi-bringup` (clean at start). The candidate c8 manifest is
[build-manifest.json](<E:/k60-work/artifacts/wifi-20261116c8/build-manifest.json>):
repo head `dd3154a716e89d0fbcc74058a3de705166fe1a29`, dirty files 0; boot image
`f83ea7637b25cbfc87fd43189bb33973495f59c3d89edd7c727c8e00c7a0950c`;
native archive `1236996adc8cd8c030ed0f194ae58448db7b01498a2e704036d1e2e62c65d95c`;
manifest hash `f99f8bf0489767744f7b52116662040887377f2f3a3a840d0d82fb115a41ba20`.
The present built MHI archive is `80b47cfde715240833613a48f0e1ccd2d4abefa3fb7686688900e77274ac1298`
(733,064 bytes); it is a current-file observation, not a historical compile
attestation.

The source identities used below are current bytes:

| Input | SHA-256 |
| --- | --- |
| Linux `init.c` (candidate symlink target) | `ef1b83d70ab6f8bf51001e189d8a279dd1c9f4600d64f10edd4aadc3145b27d4` |
| Linux `boot.c` | `632243a9832c969a250a70f11dd1dbfab9bbc4e990e2ab324cfff8e3a7b386eb` |
| Linux `pm.c` | `b23f86c2b0a39c7eaa5ce616260a00df0515625aa55918d5e1733ab8e35358ff` |
| Linux `internal.h` | `420483b10675646d44e1e292740675b142e65e86bfc7ebec6b629d66254231d5` |
| Linux `common.h` | `bed7992151ca7af159d162c5244fb182a992e64bcb098b8b645dd3d1c7303d8d` |
| generated c8 `ath11k/mhi.c` | `7fd161158101ec20abd761e982fca8335e5a4ef7f5af87c9e5f91516f74612b6` |
| generated c8 `mhi/pm.c` | `30c730ab6a111ef9cc89fbba3abf5379356610a9a3cf0d9393c3cfb040a49ce5` |
| `drivers/PongWifi/PongWifiPlatform.cpp` | `32114a8b9232c5a64fd820348fae3308470603fb2fef652a6a8e549d4b2d43e5` |
| `drivers/PongWifi/PongWifiPci.cpp` | `379394cd9c01c116c119898326f97945712365f3053dc3715917036ec76d7719` |
| `drivers/PongWifi/ath11k/PongAth11k.c` | `6a37edda4c2c64463aeaa382f530c6b6e1639dd2bd4a2864eda1ac4fd4af1f68` |
| shim `src/nw_mhi.c` | `dc26c79b4468789ce90dafa3698e1085271e7667f5abffde3136546864b2ced4` |
| shim `src/nw_pci.c` | `db549a0909d25e102e9ccc8025504f61900271cd290e1db2f23a704447669c94` |
| shim `src/lx_rt.c` | `edb649e378d1c1121435c4aa2c06cc8a61239d278b7d9a3b86040252f852da12` |
| shim `include/lx.h` | `810ed28ec2b1c14424cf3f66ae73b4955223a9e50ae30244d88d1e4efb302236` |
| shim `include/lx_os.h` | `641bcb7cea04c3947559aaed506505a8fd40b9ef385701362e793acaed9ba2d1` |

The current Linux source root reports HEAD
`458c6079fc1d41d564c37679c8ace02cd83ee817`; the shared `UniXNU-sheng` tree has
no local git repository, so its identity is the hashes above, not a revision.
The generated candidate root was `/opt/k60/trees/k60build/wifi/ath11k-c8`; its
symlink resolution and hashes are in
[identities.json](<E:/k60-work/scratch/c8-lifetime-review/identities.json>)
(`573f62c0b0ea036efb8d96b43dfc5c5fba1e72ddc8798374583854c951f646f2`).
Consistent current bytes do not reconstruct the historical preprocessor,
compiler binary, or complete compile inputs. The c8 provenance gap remains.

## 1. Allocation source: who allocates, where, how large

### 1.1 Heap objects versus DMA objects

There are two independent allocators, and they must not be conflated.

| Object | Allocation path | Map / lifetime class |
| --- | --- | --- |
| `struct mhi_controller` | `nw_mhi_register()` calls `mhi_alloc_controller()`; `mhi_alloc_controller` is `kzalloc_obj(*mhi_cntrl)` at `init.c:1092-1098` | Ordinary kernel heap through `lx_alloc` → `PongWifiPlatform.cpp:544` `IOMallocData(n+16)`. Not the DMA arena. |
| `struct mhi_ctxt` descriptor | `kzalloc_obj(*mhi_ctxt)` at `init.c:316` | Ordinary heap; owned by `mhi_cntrl`, freed by `kfree` at `init.c:297`. |
| `mhi_cmd`, `mhi_event`, `mhi_chan` arrays | `kzalloc_objs`/`vzalloc` at `init.c:940`, `:702`, and parse-config paths | Ordinary heap; freed by `mhi_unregister_controller` at `init.c:1073-1083`. |
| CH context array | `dma_alloc_coherent` at `init.c:321-325` | Board DMA arena (SID `1c01`); CPU `arenaVa+offset`, bus `0xa0001000+offset`. |
| ER context array | `dma_alloc_coherent` at `init.c:353-357` | Board DMA arena. |
| CMD context array | `dma_alloc_coherent` at `init.c:400-404` | Board DMA arena. |
| ER rings and CMD ring | `mhi_alloc_aligned_ring` at `init.c:162-177`; called at `:383` and `:416` | Board DMA arena; allocation is `len + (len-1)`, active span is aligned subrange `[iommu_base, iommu_base+len)`. |
| `fbc_image` data buffers and vector table | `mhi_alloc_bhie_table` at `boot.c:368-420`; each entry is a separate `dma_alloc_coherent` at `:397-399` | Board DMA arena. Descriptor and `mhi_buf` array are heap. |

The board allocator is `PongWifiPlatform.cpp:530-538`:
`dmaAlloc` rounds to 64 bytes and then to 4096 bytes for page-sized requests,
chooses a power-of-two alignment for page-sized blocks, first-fits a free
`Block`, and returns `*bus = Iova + 4096 + b.at + pad` with
`CPU = arenaVa + b.at + pad`; `Iova=0xa0000000` at `:41`. The CPU interval is
`[arenaVa, arenaVa+ArenaBytes)`; the bus interval is
`[0xa0001000, 0xa0001000+ArenaBytes)`. The 4 KiB MSI landing page
`[0xa0000000,0xa0001000)` is separate and is not a context allocation.
`isolation()` maps this arena under SID `1c01` and `planUfsSmmu(0x1c01, Iova,
ArenaBytes+4096, ...)` at `:448-458`; `dmaOwned` is published at `:527`.

**Which map.** The MHI metadata objects are on the ordinary kernel heap through
`IOMallocData`; the context arrays and rings are in the board's dedicated
wired DMA arena and SMMU IOVA window, not in `kernel_map` or `io_submap`.
The audit did not trace `IOMallocData` into a specific XNU submap
(`kernel_map` versus `io_submap`); no inspected source line selects one, so
that submap classification is **unknown**, not assumed. The important separation
is source-visible: metadata is not protected by arena arithmetic, and arena
containment does not prove a live metadata object.

### 1.2 Exact source-derived sizes and alignment

These are `sizeof`/`struct` arithmetic from the inspected definitions, not a
compiled ABI observation. The context layout in `common.h` is 44 source-derived
bytes for the generated QCA6390/WCN6855 profile (three 32-bit fields and four
packed/aligned(4) 64-bit fields); a ring element is 16 bytes. Runtime
`sizeof` was not sampled.

| Object | Request from source | Board block/alignment |
| --- | --- | --- |
| CH context array | `44 * max_chan`; profile `max_chan=128` → 5,632 | 8,192 bytes, 4 KiB alignment |
| ER context array | `44 * total_ev_rings`; `total_ev_rings=2` → 88 | 128 bytes, 64-byte alignment |
| CMD context array | `44 * 1` → 44 | 64 bytes |
| ER ring 0 | `16 * 32 = 512`; allocation `512+511=1,023` | 1,024-byte block, 1 KiB alignment |
| ER ring 1 | `16 * 256 = 4,096`; allocation `4,096+4,095=8,191` | 8,192-byte block, 4 KiB alignment |
| CMD ring | `16 * 128 = 2,048`; allocation `2,048+2,047=4,095` | 4,096-byte block, 4 KiB alignment |
| CH transfer ring (if prepared) | `16 * 64 = 1,024` each; allocation `1,024+1,023=2,047` | 2,048-byte block, 2 KiB alignment |
| `fbc_image` | 11 data buffers of 524,288 requested, plus vector-table buffer of `16*11=176`; descriptor `entries=12` | 11 × 524,288-byte blocks plus 176-byte block; the final data copy is 53,248 bytes, not a separate allocation |

The `fbc_image` size follows `fw_sz=5,296,128` and `seg_len=524,288`:
`DIV_ROUND_UP(5,296,128, 524,288) + 1 = 11 + 1 = 12` entries at
`boot.c:372-373`. `mhi_alloc_bhie_table` allocates each entry at `:389-402`;
the last entry is the vector table at `:392-394`; `mhi_firmware_copy_bhie`
copies 11 data segments (10 full + 53,248 bytes) and fills 11 vector entries of
16 bytes at `:422-440`. This is **not** an ELF program-header count and does
not depend on the failed second-ELF probe at `:591`.

### 1.3 Failure returns: what is checked, what is not

- `mhi_alloc_aligned_ring` checks `dma_alloc_coherent` and returns `-ENOMEM`
  at `init.c:168-171`; its callers clean up at `init.c:383-385` and
  `:416-418`, then the error labels free completed objects at `:431-466`.
- `mhi_alloc_bhie_table` checks each DMA allocation and frees the completed
  prefix on failure at `boot.c:400-401` and `:410-419`; the FBC caller checks
  its return at `boot.c:596-600`.
- `mhi_ready_state_transition` **checks** `mhi_init_mmio` at `pm.c:224-228`;
  this is not an ignored return. This corrects a possible earlier reading.
- `mhi_prepare_for_power_up` ignores the return of the **RDDM**
  `mhi_alloc_bhie_table` at `init.c:1163`. In this candidate `rddm_size` is
  zero (the `nw_config` at `nw_mhi.c:17-21` has no RDDM size), so that branch
  is not executed. It is a real ignored-return pattern, but it is not the c8
  FBC allocation.
- `nw_mhi_pre_load` logs `mhi_init_mmio`'s result without aborting
  (`nw_mhi.c:78-82`); this is a diagnostic path, not a checked context setup
  guarantee. c8's later READY transition writes MMIO again and checks the
  result.
- `mhi_register_controller` converts a `parse_config` failure into
  `-EINVAL` at `init.c:936-938`; the caller still fails, but the original
  error is lost. No allocation is published on that path.
- No `ml_io_map` or `KMA_NOFAIL` call was found in the inspected WiFi/MHI
  allocation chain. That does not prove `IOMallocData` has no internal
  no-fail behavior; the P-219 hazard is outside this chain's visible source.

## 2. Powered MMIO lifetime

### 2.1 Windows and mappings

The board uses `struct Window` at `PongWifiPlatform.cpp:46-55`:
`IODeviceMemory::withRange(pa, bytes)` then
`map(kIOMapAnywhere|kIOMapInhibitCache)`, storing the `IOMemoryMap*` and
virtual address. **No `close()` method exists on this `Window`**; the map is
held by the global `Window` object. The global mapping sites are:

| Window | Physical range | Length | Purpose |
| --- | --- | --- | --- |
| `gcc` | `0x100000` | `0xa0000` | PCIe GDSC/clocks (open at `:217`) |
| `tlmm` | `0xf100000` | `0xd0000` | PERST/pinmux (open at `:217`) |
| `db` | `0x80860000` | `0x20000` | debug/monitor window (open at `:192`) |
| `parf` | `0x1c00000` | `0x3000` | PARF PCIe controller (open at `:274`) |
| `dbi` | `0x60000000` | `0x1000` | DesignWare DBI (open at `:277`) |
| `phy` | `0x1c06000` | `0x2000` | QMP PHY (open at `:277`) |
| `atu` | `0x60001000` | `0x1000` | iATU (open at `:277`) |
| `cfg` | `0x60100000` | `0x1000` | endpoint config (open at `:383`) |
| `bar` | `0x60200000` | `0x200000` | endpoint BAR (open at `:396`) |
| `smmu` | `0x15000000` | `0x100000` | Apps SMMU (open at `:449`) |
| `rsc` | `0x17a20000` | `0x10000` | RSC (open at `:764`) |

`coldLink` powers the PCIe0 GDSC and clocks, performs resets, opens
`parf` at `:274`, sets `hostMmioReady=true` at `:275`, then opens
`dbi/phy/atu` at `:277`. `hostMmioReady` therefore means "PARF is mapped",
not "DBI/PHY/ATU/BAR are mapped or powered". The `done` label at
`:714-719` writes DBI/PARF only when `hostMmioReady` is true and guards DBI
with `dbi.v`; it does not close any window, does not call `pci_iounmap`, does
not `IOFreeData`, does not disable GDSC/clocks, and does not call
`nw_mhi_unregister` or `nw_wifi_stop`. `halt` at `:546` likewise masks
MSI/PARF and terminates the worker, with the explicit comment "DMA retained
until reset".

`nw_pci.c:26` maps the endpoint BAR by returning `nw_board->bar`; the board
supplies `bar.v` at `PongWifiPlatform.cpp:688`. `nw_pci.c:27`
`pci_iounmap` is a no-op, and `ath11k_pci_free_region` at
`ath11k/pci.c:593-603` only calls that no-op, `pci_release_region` (no-op at
`nw_pci.c:24`), and `pci_disable_device` (no-op at `nw_pci.c:20`), then
sets `ab->mem=NULL`. **No current path unmaps the BAR or the board windows.**

### 2.2 Current failure path: retention, not a proved UAF

The candidate c8 wrapper is `drivers/PongWifi/ath11k/PongAth11k.c` (compiled at
`scripts/build-k60-ath11k.py:510`), not the shared `src/nw_wifi.c` mainline
variant. `PongAth11k.c:51-77` calls `pong_ath11k_pci_init()` and, on failure,
returns after `nw_qrtr_mhi_unregister()` without calling
`pong_ath11k_pci_exit()`. `nw_wifi_stop` is guarded by
`if (!running) return;` at `:97-101`, and `running` is set to 1 only after a
successful start at `:75`. Therefore a c8 start failure leaves:
`nw_mhi_unregister` uncalled, the MHI controller and its contexts retained, and
the board `done` path with no MHI teardown.

The generated c8 timeout path is:
`mhi_sync_power_up` (`pm.c:1277-1297`) waits; on non-mission it calls
`mhi_power_down(false)` at `:1295`. `__mhi_power_down` at `pm.c:1212-1262`
queues the disable transition, flushes `st_worker`, and disables IRQ0 at
`:1261`; the disable transition disables each event IRQ and kills its tasklet
at `pm.c:522-528`. It does **not** free CH/ER/CMD context arrays or
`fbc_image`; that requires `mhi_unprepare_after_power_down` at
`init.c:1190-1206`. `ath11k_mhi_start` returns the error at
`ath11k/mhi.c:444-448` without calling `ath11k_mhi_stop`. The probe error
path `err_mhi_unregister` at `ath11k/pci.c:1155-1156` calls
`ath11k_mhi_unregister`, which at `ath11k/mhi.c:425-429` calls
`mhi_unregister_controller`, frees the IRQ array, and frees the controller.
It does **not** call `mhi_unprepare_after_power_down`.

Consequences for the audit:

- In the current c8 failure path there is **no `dmaFree` of the CH/ER/CMD
  contexts or `fbc_image`**. The objects leak until reboot. No post-free read
  is demonstrated on this path, because no free occurs.
- The normal successful-stop path `ath11k_mhi_stop` at `ath11k/mhi.c:453-465`
  does call `mhi_power_down` and `mhi_unprepare_after_power_down`; but
  `PongAth11k.c` `nw_wifi_stop` cannot reach it after a failed c8 start because
  `running` is false.
- The board's `done`/halt retention is not a power-down and does not prove
  that late DMA stopped. It is also why "mapping still non-null" cannot be used
  as a powered-MMIO lease.

### 2.3 dmaFree reuse and stale ring/context fields

`mhi_deinit_dev_ctxt` at `init.c:256-299` frees the CMD ring, CMD context,
ER rings, ER context, and CH context arrays, then `kfree(mhi_ctxt)` and sets
`mhi_cntrl->mhi_ctxt=NULL`. It clears only `ring->base` and
`ring->iommu_base` at `:269-270` and `:285-286`; it does **not** clear
`ring->ctxt_wp`, `ring->rp/wp`, `ring->pre_aligned`, `ring->dma_handle`, or
`ring->alloc_size`. `mhi_deinit_chan_ctxt` at `:609-642` clears the channel
TRE ring and the channel context fields, but the ER/CMD ring fields above are
left stale.

`PongWifiPlatform::dmaFree` at `:540` ignores both the size and bus arguments,
computes `off` from the CPU pointer, matches only `blocks[i].at==off`, sets
`used=false`, and coalesces adjacent free blocks. `dmaAlloc` at `:530-538`
first-fits free blocks; there is no generation, owner, or size tag. A freed
block can therefore be reused by the next coherent allocation, and
`ctxt_wp`/`rp`/`wp` retained in the event/command structures would then point
into a different allocation. That is a latent stale-pointer hazard, not a
demonstrated use-after-free: the current c8 failure path never frees, and the
normal unprepare path frees only after the disable transition has disabled the
event IRQs and killed the tasklets.

The IRQ callback `PongWifiPlatform::irq` reads/writes `dbi` and is attached
to GIC SPI140 at `:683`. `done`/`halt` mask the DBI MSI and PARF bit but do
not detach the `ArmCpu` SPI owner; the callback remains registered for kernel
lifetime. No current path unmaps `dbi` or powers the controller down, so an
actual post-unmap IRQ read is not demonstrated. If a future power-down/unmap
path is added, the missing detach and the lack of a powered-MMIO lease become
live blockers.

## 3. Direct answers

1. **Who allocates, when, size/align/flags, which map.** MHI metadata
   (controller, `mhi_ctxt`, command/event/channel arrays) is ordinary kernel
   heap allocated during `nw_mhi_register`/`mhi_register_controller` and
   `mhi_init_dev_ctxt`, through `kzalloc*` → `lx_alloc` → `IOMallocData`;
   exact XNU submap is unknown. CH/ER/CMD context arrays and rings, and the
   `fbc_image` buffers, are allocated by `dma_alloc_coherent` during
   `mhi_init_dev_ctxt` / `mhi_fw_load_handler` and are in the board arena
   (SID `1c01`, bus `0xa0001000+`, CPU `arenaVa+`). Sizes/alignment are in
   §1.2; flags are `GFP_KERNEL` at the MHI layer, ignored by the board shim.
   The checked failures and the one ignored RDDM allocation are in §1.3.
2. **Powered-MMIO lifetime.** The board maps `gcc/tlmm/parf/dbi/phy/atu/cfg/
   bar/smmu` with `kIOMapInhibitCache` and never closes them; `hostMmioReady`
   is only a PARF-mapping flag. `coldLink` powers/clock-gates the controller
   and endpoint; `done`/halt only mask DBI/PARF and assert PERST, retaining
   DMA and mappings. `pci_iounmap` is a no-op, so the BAR is not unmapped on
   the ath11k free-region path either. There is no current sequence that
   removes a mapping then reads it, but there is also no teardown/power-down
   lease; powered access is **unknown**, not qualified.
3. **dmaFree reuse boundary.** Freed arena blocks are immediately reusable by
   first-fit `dmaAlloc`; no owner/generation/tag exists. `mhi_deinit_dev_ctxt`
   leaves `ctxt_wp`/`rp`/`wp` stale after freeing; `mhi_deinit_chan_ctxt`
   clears only channel fields. In the current c8 failure, `mhi_unprepare` is
   never called, so the allocations are not freed at all; on a normal stop,
   unprepare frees after IRQ/tasklet shutdown, and the event array is later
   freed. No post-free read is demonstrated in either path, but the stale-field
   and reuse hazard is real and unqualified.
4. **What this audit cannot prove.** No physical-layout conclusion; no
   cache-visibility/coherency conclusion; no controller-behavior conclusion; no
   reset completion or late-DMA fence; no powered-MMIO or SMMU lease; no
   historical compile attestation; no claim that a host guard or arithmetic
   range proves bus safety. A non-null map, `hostMmioReady`, retained arena,
   or raw register callback returning zero is not proof of power.

## 4. Disposition

**c8 remains HOLD.** This audit does not qualify a new failure-path
`MHISTATUS`/`MHICTRL`/`EE` or ring read. Any future diagnostic must either
hold an independently documented controller/power/DMA lease through the final
access, or keep the read in the already-bounded static-counter category and
explicitly SKIP the unqualified objects. The existing c8 timeout and board
cleanup reads at `pm.c:1299-1305` and the halt/done MSI/PARF writes are
pre-existing and remain unqualified by this audit. No build, compile, apply,
boot, device operation, active-source edit, or c8 execution occurred.

## 5. Machine-checkable offline check

`scripts/tests/test-candidate-lifetime-audit.py` is a source-shape test, not a
lifetime proof. It checks the exact anchors cited above: aligned-ring
allocation arithmetic, checked/ignored returns, `mhi_deinit_dev_ctxt` free
order and stale fields, `mhi_unprepare_after_power_down`, the missing
unprepare in `nw_mhi_unregister`, the ath11k start/stop/remove order,
`nw_wifi_start`/stop gating, `dmaFree` offset-only reuse, `pci_iomap`/unmap
no-op, `Window` map-without-close, and the `done` retention path. It reads
only files and exits nonzero if an anchor disappears; it does not compile,
execute, or touch a device.
