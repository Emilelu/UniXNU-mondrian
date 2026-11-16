# WiFi failure snapshot allocation and MMIO lifetime audit

**Disposition: c8 HOLD. Read-only source audit, 2026-11-16.** The original richer
snapshot was unsafe as written: arena containment did not prove a live allocation,
and non-null mappings did not prove powered MMIO. The revised
[unapplied snapshot diff](<../../../scripts/proposals/wifi-failure-snapshot.diff>)
now collects module-static counters and explicitly skips controller/context/ring
and register accesses. This is a bounded diagnostic amendment, not qualification
of c8, permission to apply the diff, or proof that the existing failure path is
safe.

Only this document and evidence under
[c8-lifetime-review](<E:/k60-work/scratch/c8-lifetime-review/identities.json>) were
written by this audit. No driver, generator, patch, session model, gate, index,
manifest or artifact was changed; no commit, build, compile, application, or device
operation was performed. The controlling Lead 17:54 reply is
[reply-wifi-20261115.md:6](<E:/k60-work/scratch/reply-wifi-20261115.md:6>).

## 1. Identities and historical limits

The historical [c8 manifest](<E:/k60-work/artifacts/wifi-20261116c8/build-manifest.json>)
records build time 2026-11-16T13:27:45+08:00, branch feat/wifi-bringup, clean source
head **dd3154a716e89d0fbcc74058a3de705166fe1a29**, requested arguments
pong_wifi=1 and k60_wifi_rsc=2, native archive SHA-256
1236996adc8cd8c030ed0f194ae58448db7b01498a2e704036d1e2e62c65d95c,
and image SHA-256 f83ea7637b25cbfc87fd43189bb33973495f59c3d89edd7c727c8e00c7a0950c.
Manifest SHA-256 is f99f8bf0489767744f7b52116662040887377f2f3a3a840d0d82fb115a41ba20.
Its eight_step_items=all label is not a WiFi-selected gate result.

The audit worktree HEAD is **3cf1a08c8a7c60656c9682fb53d1c1b3bf74a185** on
feat/wifi-bringup. A read-only git diff from the manifest head to this HEAD is
empty for the six repository files below. Their current bytes are the audit input;
this comparison alone is not historical compilation attestation.

| Repository source | Current SHA-256; same bytes at manifest head |
| --- | --- |
| [PongWifiPlatform.cpp](<../../../drivers/PongWifi/PongWifiPlatform.cpp>) | 32114a8b9232c5a64fd820348fae3308470603fb2fef652a6a8e549d4b2d43e5 |
| [PongWifiPci.cpp](<../../../drivers/PongWifi/PongWifiPci.cpp>) | 379394cd9c01c116c119898326f97945712365f3053dc3715917036ec76d7719 |
| [PongAth11k.c](<../../../drivers/PongWifi/ath11k/PongAth11k.c>) | 6a37edda4c2c64463aeaa382f530c6b6e1639dd2bd4a2864eda1ac4fd4af1f68 |
| [ArmCpu.cpp](<../../../drivers/ArmCpu/ArmCpu.cpp>) | c85498057d8adb9332cc600e4c07282cb813674d1a3d78686415d71d62066f4e |
| [build-k60-ath11k.py](<../../../scripts/build-k60-ath11k.py>) | 0bb0e9a1682b79bd0dc69cb12548789652494ea8dd78ac2a8efb991444e9630c |
| [PongCompat.h](<../../../drivers/PongWifi/ath11k/compat/PongCompat.h>) | d4c7d46d39dc078b82287f19d5103db00501cb5397050b71cb273d1de74fcceb |

The current Linux source root reports full git HEAD
**458c6079fc1d41d564c37679c8ace02cd83ee817**. Read-only status was clean for the
MHI init/internal/pm/common and ath11k MHI files inspected. The retained
[build report](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__build-report.json>)
says Linux v7.0.14, guest 20G81, real_pci_mhi=true, wifi_operational=false,
image_verification="skipped by request". Shared UniXNU-sheng sources are a directory
without a local git repository: no full shared revision can be asserted. Their
identity is the exact current file hashes below, not an invented revision.

The generated candidate root is /opt/k60/trees/k60build/wifi/ath11k-c8. Its
[current-file inventory](<E:/k60-work/scratch/c8-scheduling-review/inventory.json>)
SHA-256 is bcc68bbfa2eeb8b257c34fd57714b0755864ba45c8d64b6bae6f8b26f94140a3.
The new bounded [identities.json](<E:/k60-work/scratch/c8-lifetime-review/identities.json>)
(SHA-256 573f62c0b0ea036efb8d96b43dfc5c5fba1e72ddc8798374583854c951f646f2)
records resolved symlink targets, byte counts and current hashes, using the
[read-only collector](<E:/k60-work/scratch/c8-lifetime-review/collect.py>)
(SHA-256 68a2b90247c47fe064d748967279e841835ab0ad47b7bdc778de7bc426f2ce50).
The following source versions are the basis for all external line references.

| Candidate/current source | Version relationship and SHA-256 |
| --- | --- |
| [generated ath11k MHI](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c>) | Current generated file; 7fd161158101ec20abd761e982fca8335e5a4ef7f5af87c9e5f91516f74612b6 |
| [MHI init export](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c>) | Candidate is symlink to current Linux host init; ef1b83d70ab6f8bf51001e189d8a279dd1c9f4600d64f10edd4aadc3145b27d4 |
| [MHI internal header export](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__internal.h>) | Candidate is symlink to current Linux host header; 420483b10675646d44e1e292740675b142e65e86bfc7ebec6b629d66254231d5 |
| [MHI common header export](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__common.h>) | Candidate is symlink to current Linux common header; bed7992151ca7af159d162c5244fb182a992e64bcb098b8b645dd3d1c7303d8d |
| [generated MHI pm export](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c>) | Generated replacement of Linux pm; 30c730ab6a111ef9cc89fbba3abf5379356610a9a3cf0d9393c3cfb040a49ce5 |
| [Linux pm source](<E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/bus/mhi/host/pm.c>) | Current untransformed source; b23f86c2b0a39c7eaa5ce616260a00df0515625aa55918d5e1733ab8e35358ff |
| [generated dispatcher export](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__lx_rt_pong.c>) | Current candidate bytes equal shared lx_rt.c; edb649e378d1c1121435c4aa2c06cc8a61239d278b7d9a3b86040252f852da12 |
| [shared lx_rt.c](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/lx_rt.c>) | Same current bytes as preceding row; shared revision unavailable |
| [shared lx_os.h](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/include/lx_os.h>) | Current DMA definitions; 641bcb7cea04c3947559aaed506505a8fd40b9ef385701362e793acaed9ba2d1 |
| [shared lx.h](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/include/lx.h>) | Current heap/layout/lock definitions; 810ed28ec2b1c14424cf3f66ae73b4955223a9e50ae30244d88d1e4efb302236 |
| [shared nw_abi.h](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/include/nw_abi.h>) | Current platform callback ABI; 508f5e8f70cb7fc4d6467a216df42b90c2bf7a40abaa3ff00c400abd23b0c402 |
| [shared mhi_hook.c](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/mhi_hook.c>) | Bus registration only; 5e7e84b65b7480647328f841401cd816f71360b5a7b8124ffd0614523c0202bb |

The new collector rehashed the present ath11k archive as
80b47cfde715240833613a48f0e1ccd2d4abefa3fb7686688900e77274ac1298
(733,064 bytes) and native archive as the manifest's
1236996adc8cd8c030ed0f194ae58448db7b01498a2e704036d1e2e62c65d95c
(12,071,440 bytes). The earlier
[provenance report:38](<E:/k60-work/scratch/c8-provenance-review/REPORT.md:38>)
records identical PongAth11k-linked.o members in the two archives: 698,848-byte
archived payload SHA-256 7b5339cdb243ac423bf87911efcecfa848245404173b6d777e625d9a14ce013c,
including four padding newlines after the 698,844-byte object. This relation is
reused as reported evidence; member extraction was not repeated here.

Current source hashes, live symlink targets and retained compile commands tie
present files together. The manifest did not freeze the complete generated source,
headers, compiler binary or intermediate archive. The earlier report also records
a transient T2 native-builder change, restored before the later clean snapshot.
Consequently the address/lifetime findings below are **exact current candidate
source findings**, with a historical c8 compilation proof gap. They do not
retroactively attest the full historical preprocessing/compile inputs. See
[provenance report:64](<E:/k60-work/scratch/c8-provenance-review/REPORT.md:64>).

## 2. Actual allocation chain and CPU/bus/length derivation

The retained [compile command:1116](<E:/k60-work/scratch/c8-provenance-review/ath11k-c8-compile-commands.json:1116>)
targets arm64-apple-ios16.0, includes the repository compatibility overlay and then
the shared shim before Linux headers. The
[DMA macros:306](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/include/lx_os.h:306>)
map dma_alloc_coherent/dma_free_coherent to lx_dma_alloc/lx_dma_free. The
[dispatcher:531](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/lx_rt.c:531>)
forwards them to lx_plat->dma_alloc/dma_free. The
[platform table:686](<../../../drivers/PongWifi/PongWifiPlatform.cpp:686>)
supplies dmaAlloc/dmaFree/dmaMap/dmaSync. No alternate CH/ER/CMD coherent allocator
was found in this chain.

For a successful board allocation, let o=b.at+pad and n be the requested bytes.
The allocator rounds n to 64 bytes and, once at least 4096, to 4096 bytes; for page
sized blocks it chooses a power-of-two alignment at least the rounded size. It
splits a free Block and sets used=true. At
[platform:531](<../../../drivers/PongWifi/PongWifiPlatform.cpp:531>) and
[platform:537](<../../../drivers/PongWifi/PongWifiPlatform.cpp:537>):

- CPU = arenaVa + o.
- bus = Iova + 4096 + o, with Iova = 0xa0000000.
- arena CPU interval is [arenaVa, arenaVa+ArenaBytes); bus interval is
  [0xa0001000, 0xa0001000+ArenaBytes).
- The MSI landing page [0xa0000000,0xa0001000) is separate and is not a context
  allocation. ArenaBytes is the **actual successful** 64 or 128 MiB budget,
  established by [allocateArena:405](<../../../drivers/PongWifi/PongWifiPlatform.cpp:405>).
  No actual CPU address or chosen runtime budget was sampled by this audit.

The [aligned-ring allocator:163](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:163>)
uses allocation length a=L+(L-1), then
B=(dma_handle+(L-1)) & ~(L-1), CPU base=pre_aligned+(B-dma_handle).
The original span (pre_aligned,dma_handle,a) and active span (base,B,L) are distinct.
Power-of-two L and nonoverflowing length arithmetic are prerequisites; no later
range check can repair corrupted metadata before it is safely captured.

| Object | Actual source operation | Requested length and output fields |
| --- | --- | --- |
| Controller/context/event/command/channel metadata | kzalloc/vzalloc through lx_alloc, then board alloc/IOMallocData; **ordinary heap, outside retained DMA arena** | c is mhi_alloc_controller; mhi_ctxt is kzalloc at [init:316](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:316>); mhi_event allocation at [init:702](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:702>). Heap forwarding is [lx_rt:190](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/lx_rt.c:190>) and [platform:544](<../../../drivers/PongWifi/PongWifiPlatform.cpp:544>). |
| CH context array | dma_alloc_coherent at [init:321](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:321>) | sizeof(*chan_ctxt) * max_chan; CPU chan_ctxt, bus chan_ctxt_addr |
| ER context array | dma_alloc_coherent at [init:353](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:353>) | sizeof(*er_ctxt) * total_ev_rings; CPU er_ctxt, bus er_ctxt_addr |
| CMD context array | dma_alloc_coherent at [init:400](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:400>) | sizeof(*cmd_ctxt) * NR_OF_CMD_RINGS; CPU cmd_ctxt, bus cmd_ctxt_addr |
| Each non-offload ER ring | mhi_alloc_aligned_ring at [init:381](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:381>) | L=sizeof(struct mhi_ring_element)*elements; original and active spans as above; context rbase/rlen set to active bus/L, ctxt_wp points into ER context |
| CMD ring | Same allocator at [init:413](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:413>) | L=16*128=2048 with NR_OF_CMD_RINGS=1 and CMD_EL_PER_RING=128 from [internal:176](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__internal.h:176>); a=4095, board block rounds to 4096 |
| Each prepared CH transfer ring | Same allocator at [init:644](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:644>) | L=16*tre_ring.elements; the separate buf_ring is vzalloc heap metadata, not a DMA allocation |

The source layouts in [common:258](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__common.h:258>)
contain three 32-bit fields and four packed/aligned(4) 64-bit fields per context:
44 source-derived bytes each; the ring element is 16 bytes. These are layout
arithmetic from inspected definitions, not a compiled sizeof test. In the generated
QCA6390/WCN6855 profile
[ath11k MHI:55](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:55>)
and [profile selection:396](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:396>),
max_chan=128 and total_ev_rings=2, so CH request=5632 (board block=8192), ER
request=88 (block=128), CMD request=44 (block=64). ER elements are 32 and 256:
active L=512/4096, allocation a=1023/8191, board blocks=1024/8192. Configured CH20/21
have 64 elements each, so if prepared L=1024, a=2047, board block=2048. Those
are conditional source values, not evidence that every CH ring was prepared in the
failed attempt or a dump of runtime addresses.

The controller envelope is independent: generated
[ath11k MHI:382](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:382>)
uses [0,dma_mask] unless the fixed-memory DT branch is selected. It is an allowed
bus envelope, not the allocator's active extent or an ownership registry. Inclusive
checks require n>0, bus>=low, bus<=high and n-1<=high-bus. Arena containment and
CPU/bus offset equality can be checked with subtraction after bounds checks, but
only over scalars already captured with a separately proven lifetime.

## 3. Lifetime, cleanup, cancellation and failure returns

| Boundary | Source evidence | Consequence for a snapshot |
| --- | --- | --- |
| Successful preparation | [init:427](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:427>) publishes c->mhi_ctxt only after all contexts/rings succeed | Creation is grounded; later liveness is a different question. |
| Allocation failure | [init:431](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:431>) through error labels frees completed CMD/ER rings, context arrays and descriptor | A failed partial descriptor is not published as a complete snapshot source. |
| Prepare register-offset/RDDM failure | [init:1180](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:1180>) calls mhi_deinit_dev_ctxt before returning; caller returns at generated [ath11k MHI:454](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:454>) | The proposed sync timeout hook does not cover this return. |
| Context deinit | [init:256](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:256>) frees CMD/ER original ring spans and CH/ER/CMD context arrays, clears ring base/iommu_base, kfree(mhi_ctxt), then sets c->mhi_ctxt=NULL | Non-null checks are not synchronized ownership. Other stale ring fields may survive; nulling after free is not a lease. |
| CH stop/deinit | [init:609](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:609>) frees DMA TRE and heap buf_ring, nulls bases/ctxt_wp and zeros channel context ring fields | CH ring lifetime is shorter than CH context-array lifetime. Channel allocation failure also frees its TRE if heap buf allocation fails. |
| Power-down/unprepare | [pm:1215](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c:1215>) marks fatal/linkdown or shutdown, queues disable/destroy, flushes st_worker, disables IRQ; [init:1190](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:1190>) frees firmware/RDDM tables, nulls bhi/bhie and deinitializes contexts | Before this particular call does not exclude an earlier fatal transition, another teardown path, or loss of endpoint/interconnect power. |
| Disable transition | [pm:475](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c:475>) conditionally resets/polls hardware, disables IRQs, kills event tasklets, may destroy child devices and resets host/shared rp/wp | Cancellation is CPU work control. This audit does not promote it to proven reset completion or a late-DMA fence. Fatal state can skip reset. |
| Controller unregister/free | [init:1060](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c:1060>) deinitializes IRQ/workqueue state, frees mhi_cmd/mhi_event/mhi_chan, releases mhi_dev; generated [ath11k MHI:435](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:435>) then frees IRQ array and controller | c, mhi_dev and event/command/channel arrays are independently reclaimable heap objects. |
| Board free/reuse | [platform:540](<../../../drivers/PongWifi/PongWifiPlatform.cpp:540>) matches CPU offset to a used Block, sets used=false and coalesces; size/bus arguments are not ownership checks | The arena remains wired but the suballocation can immediately be reused. Arena range + exact mapping is insufficient. |
| Board halt/done | [platform:546](<../../../drivers/PongWifi/PongWifiPlatform.cpp:546>) halts on firmware/deadline/fault; [platform:714](<../../../drivers/PongWifi/PongWifiPlatform.cpp:714>) cleans up at done and retains DMA | Halt may never reach the new hook. Retention is not successful power-down, per-block ownership or proof that late DMA stopped. |

The cooperative dispatcher explicitly allows nested waits to run other queued
callbacks. Its [cancel/flush:213](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/lx_rt.c:213>)
removes queued work, rejects synchronously cancelling a running ancestor, and
flushes by pumping. [lx_pump:368](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/lx_rt.c:368>)
warns that a callback can cancel and free another timer; queue destruction leaves
delayed-work lifetime to its caller. Device references are real host reference
counts at [lx_rt:471](<E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/shim/src/lx_rt.c:471>),
but the original proposed timeout helper acquired none. A device reference alone
would not pin independent context arrays or the board allocator's blocks.

There is an active synchronous caller which expects c to survive its call; these
free endpoints do **not** demonstrate that an actual free races this timeout. The
audit has not closed all reentrancy/cancellation/stop paths with an explicit
spanning reference and teardown exclusion. Therefore timeout c/mhi_dev/mhi_ctxt/
mhi_event/ring liveness is **UNKNOWN**, not a demonstrated use-after-free and not
qualified for additional diagnostic dereferences. The narrowed no-argument helper
avoids relying on that unresolved contract.

## 4. Every proposed access: evidence, unknown, required action

This table classifies the original richer proposal (diff SHA-256
699abb0d6030cca4989d2162ddf36f0f0e2e1e03da5ff7ae12b5997d178ff242)
and the narrowed review diff (SHA-256
4c4b4037e08a8a8f057497c40243dd5897adab7b005f3594400b285e1b0d5c10).
The original review document hash was
dd3004467873dcf6813cc629453b6832feb905c7cf9727bac4c317d28e1d78bf.
The original read paths are superseded by explicit SKIP output in the narrowed
[proposal](<FAILURE-SNAPSHOT-PROPOSAL.md>).

| Proposed access | Classification / evidence | Required disposition |
| --- | --- | --- |
| c->mhi_dev and &c->mhi_dev->dev for dev_info/dev_err; c->mhi_ctxt; c->regs/bhi, c->iova_start/stop, counts, cached EE/PM | UNKNOWN timeout object lifetime/teardown exclusion. Referenced objects are heap, not protected by arena arithmetic. Existing caller expectation is not a newly proven snapshot lease. | SKIP before reading any c field; use a literal host log with no controller argument. |
| x->chan_ctxt/addr, x->cmd_ctxt/addr and sizeof/count-derived runtime lengths | UNKNOWN x lifetime; even fetching the metadata to validate it dereferences unqualified objects. sizeof is compile-time, but the original value path also reads counts/pointers. | SKIP runtime metadata extraction; offline scalar arithmetic may remain a test only. |
| x->er_ctxt[i].rbase/rlen/rp/wp/msivec and ctxt_wp comparison | UNKNOWN DMA suballocation ownership, no registry generation/lease; stale/reused arena block passes original guard. Device may also update fields. | SKIP all shared context reads; no range guard may authorize them. |
| c->mhi_event[i], event irq/index, v->ring fields (base, pre_aligned, rp/wp, dma_handle, iommu_base, len, alloc_size, el_size, db_addr, ctxt_wp) | UNKNOWN independent heap/event lifetime and ring ownership. Printing pointer values still requires dereferencing their containing object. | SKIP whole walk. No ring payload or doorbell pointer target read is authorized. |
| MHISTATUS 0x48, MHICTRL 0x38, BHI_EXECENV BHI+0x28 | UNKNOWN current mapping/power lease. Generated [ath11k read callback:303](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:303>) performs raw readl then returns 0; it cannot turn a stalled interconnect access into a bounded error. runtime_get returns 0 and runtime_put is empty at [ath11k MHI:231](<E:/k60-work/scratch/c8-lifetime-review/opt__k60__trees__k60build__wifi__ath11k-c8__ath11k__mhi.c:231>). | SKIP; neither a callback return code nor !base check proves powered access. |
| CCABAP 0x58/0x5c; ECABAP 0x60/0x64; CRCBAP 0x68/0x6c | Register offsets grounded by common header; current power/mapping lifetime UNKNOWN. Sequential halves are not atomic 64-bit observations. | SKIP every half; no inferred address from failed/omitted reads. |
| MHICTRLBASE 0x80/0x84; MHICTRLLIMIT 0x88/0x8c; MHIDATABASE 0x98/0x9c; MHIDATALIMIT 0xa0/0xa4; ERDBOFF 0x20; CHDBOFF 0x18 | Offsets grounded; power/mapping and complete read bounds UNKNOWN at failure. Original helper checked only non-null base. | SKIP all reads. |
| Board DBI MSI Enable/Mask/Status +0x828/+0x82c/+0x830; PARF group mask +0x22c | UNKNOWN current clock/GDSC/NoC/host power lifetime. [platform:275](<../../../drivers/PongWifi/PongWifiPlatform.cpp:275>) sets hostMmioReady after PARF mapping; DBI mapping follows. This is initialization history, not a power lease. | SKIP before and after cleanup; existing callback read/W1C usage supplies semantics only, not current access safety. |
| PARF +0x228 | Existing ACK write site; safe status-read semantics not established. | Never add a read/clear experiment. Original and narrowed proposals both omit such a read. |
| GICD_TYPER +4, ISENABLER +0x100, ISPENDR +0x200, ISACTIVER +0x300, IROUTER +0x6000+8*id | UNKNOWN diagnostic GIC power/MMIO lifetime; gDist/ready/owner do not establish it. Original helper read TYPER before owner validation. | SKIP all distributor reads. Moving owner validation first alone would not close the power proof. |
| Existing static gSpiUsed/gSpi[i].id/gSpi[i].count; accessor output stack pointer | GROUNDED for the narrowed counter-only path in inspected source: static array; id is initialized before release-store gSpiUsed at [ArmCpu:449](<../../../drivers/ArmCpu/ArmCpu.cpp:449>), accessor acquire-loads and bounds-checks used, atomic count load; caller supplies live stack output. No slot removal/reuse path was found in inspected ArmCpu source. | Permit counter-only observation, with return/available flag. No gDist access; no route/pending/active claim. |
| Existing static msiEntries/msiArrivals/msiEmptyStatus | GROUNDED static storage and atomic access. They describe prior callback entries/nonzero-status entries/empty entries. | Permit atomic counter reads only; no new DBI/PARF read and no conversion to vector count. |
| New module-static shim pump/poll-raise/raise_all/logical-dispatch counters | GROUNDED static storage, atomic increments/loads in the proposed transformation. | Permit worker-context counter read; software dispatch never becomes hardware MSI evidence. |
| Pure arena/envelope/ring checks on artificial or already-authorized captured scalar values | GROUNDED arithmetic only, conditional on overflow/bounds checks and input provenance. | Offline tests may retain it; no runtime object access or dereference entitlement follows. |

All added helpers remain worker-context observations with no allocation, new
snapshot work scheduling, lx_pump, reset, context write, cache operation, payload
read or doorbell readback. Static counter loads are individually atomic, not one
global snapshot; counters can advance/wrap, are cumulative without session
baselines, and logging changes timing. An unavailable value must be SKIP/REJECT
with reason, never a successful zero.

## 5. Existing candidate remains unqualified

**Preexisting generated c8 timeout accesses are still unqualified.**
[pm:1299](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c:1299>)
through 1305 reads MHISTATUS and MHICTRL, dereferences cached EE/PM, and calls
mhi_get_exec_env/mhi_get_mhi_state before the proposed hook. The wait can return
because of MHI_PM_FATAL_ERROR. The narrowed helper does not remove, fence or
qualify any of these existing operations. It may never be reached if an earlier
read stalls. The existing board cleanup/MMIO in halt/done and interrupt callback
also remains unchanged and is not certified by this audit.

A mapping, ordinary non-null pointer, hostMmioReady, retained arena, power-state
enum, raw register callback returning zero, or successful host guard test does
**not** prove a powered endpoint/interconnect or absence of a bus hang. No
interconnect access was attempted here. Allocation retention also does not prove
SMMU mappings remain valid, cache visibility, device consumption, reset completion
or absence of late DMA. No protocol/session/direct-path eligibility is promoted.

## 6. Limited amendment requirements for root

The narrowed proposal satisfies the required default at its new diagnostic
access sites: no controller argument, literal reason for skipped MHI
objects/registers, software counters, counter-only ArmCpu owner lookup, and no
board/GIC MMIO reads. Review this bounded scope before any later application.

A richer successor would need all of the following source-backed contracts;
otherwise the corresponding segment must remain SKIP/REJECT:

1. Acquire a controller/device ownership token from an already-live owner before
   fetching metadata, prove release ordering and no teardown/reentrant cancellation
   through the final capture. Audit every caller/free path; do not obtain a
   reference through an already-unqualified pointer.
2. Pin the context descriptor and independent event/command/channel arrays;
   serialize context deinit/channel stop/reset, and pin each coherent suballocation
   against dmaFree/reuse with exact base/size/owner/generation evidence. A boolean
   that once recorded successful allocation is insufficient. Define packed/shared
   field sampling and tearing limits separately.
3. Hold independently documented power/clock/GDSC/NoC/reset and mapping lifetimes
   for the entire register sequence; validate full offset+width bounds before
   access, including BHI subwindow bounds. Establish GIC lifetime separately.
   Do not fabricate runtime_get, power-provider success, an MMIO lease or a
   post-read error path as proof against a hang.
4. Check original/aligned ring spans and controller/arena bounds only after safe
   scalar capture. Keep numerical mapping proof distinct from active allocation,
   SMMU/coherency, device DMA and reset/late-DMA fencing proof.
5. Preserve narrow reachability: the hook covers sync-power-up non-mission return
   before its own power-down call only. Immediate async/prepare errors, firmware
   halt, later crashes and all other paths need separate analysis. Address existing
   timeout/cleanup MMIO separately before claiming candidate failure-path safety.

This audit reviewed the narrowed diff but did not run a compiler, the generator,
or snapshot host tests. The proposal owner reports static tests and apply-check;
root must independently review final diff and validation. The only executed helper
here read existing files and wrote authorized evidence copies/hashes (exit 0;
WSL reported an unrelated S: mount warning). No host result supplies hardware
safety evidence. **c8 remains HOLD.**
