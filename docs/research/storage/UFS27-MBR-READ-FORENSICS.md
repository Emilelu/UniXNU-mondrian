# UFS 27 — MBR/read forensics for `k60_ufs_read(0, 512)`

Status: read-only analysis, 2026-11-24. Base `feat/ufs-27` @ `f60da7e0`
(tree `E:/k60-work/ufs27`). No build, no device, no tree outside this checkout
was modified.

Scope: the Lead reported that the 27 kernel passes VM bootstrap, the log stops
at `K60UFS`, and a read of partition 0's MBR has no `0x55AA` tail. This page
traces that read through `drivers/NativeUfs`, compares it with the 16.6.1 line,
states a conclusion, and carries a minimal fix draft.

## 0. The requested symbol does not exist; here is what does

`K60UfsTransport` and `k60_ufs_read` appear in **no** tree on this host:
`E:/k60-work/ufs27` (all 85 remote branches), `E:/hackios/k60-gates`,
`E:/hackios/UniXNU`, `E:/hackios/UniXNU-mondrian` and
`E:/hackios/xnekom-ios27` were searched with `git grep`/`rg`; there are zero
hits. The identifiers in the boot log map as follows:

| Log / request | Real code |
| --- | --- |
| `K60UFS` | the **write**-trace tag: `drivers/NativeUfs/PongUfsTransport.cpp:656` (`wcall#`), `:724` (`write#`), `:772` (`-> result`) |
| `K60RD` | the **read**-trace tag: `drivers/NativeUfs/PongUfsTransport.cpp:678`; only armed when the Data volume is looked up (`:495-505`, `K60RD trace armed for Data mount` at `:504`), so a stage-0 boot that never reaches Data logs **no reads at all** |
| `k60_ufs_read(0, 512)` | `PongUfsBlock::doAsyncReadWrite(IOMemoryDescriptor *, UInt64 block, UInt64 count, IOStorageAttributes *, IOStorageCompletion *)` at `drivers/NativeUfs/PongUfsTransport.cpp:646`, with `block = 0`, `count = 1` (the device advertises 512-byte blocks, `kRootLogicalBlock = 512` at `:69`) |

Consequence: a log that "stops at `K60UFS`" ends on a **write** trace. The read
path prints nothing unless the Data volume was reached first. The missing
`0x55AA` therefore cannot be read out of the `K60UFS` line; it has to be
explained from the read path and from what block 0 of the published disk is.

## 1. Parameter trace of `(block = 0, count = 1)`

All line numbers are in `drivers/NativeUfs/PongUfsTransport.cpp` unless stated.

| Item | Value at `block=0, count=1` | Where |
| --- | --- | --- |
| Logical block size | `kRootLogicalBlock = 512` | `:69`; `reportBlockSize` `:325`; `reportMaxValidBlock` `:326` |
| Transfer bytes | `count * 512 = 512` | `:729` |
| Root block count | `window.size / 512` | `:648` |
| Entry guard | rejects `count == 0`, `block >= rootBlocks`, `buffer->getLength() < count * 512`, and any direction other than `kIODirectionIn` for a read — with `kIOReturnBadArgument` and **no completion callback** | `:663-667` |
| Online guard | `!online || !gHost.ready` → `kIOReturnNotReady` | `:676` |
| Absolute byte offset | `window.baseByte + 0 * 512 + 0` | `:733` |
| Offset inside the 4 KiB physical block | `window.baseByte & 4095` (windows are 4 KiB aligned, `init()` at `:510-515` rejects `baseByte & 4095`) | `:734` |
| Physical block count | `(inside + 512 + 4095) / 4096 = 1` | `:737` |
| Copy length | `min(512, 1 * 4096 - inside) = 512` | `:738-739` |
| Physical LBA for READ(10) | `window.baseByte / 4096` | `:757`, `RootCommands.h:274-286` |
| DMA source | `gHost.virt + kDataOffset + inside` | `:760` |
| Copy to caller | `buffer->writeBytes(0, data, 512)` | `:761` |
| Completion | `completion->action(..., result, 512)` | `:779` |

So for the MBR read the loop runs exactly once, copies 512 bytes from DMA
offset 0, and the last two bytes of the caller's buffer are bytes 510 and 511 of
the 4 KiB physical block. There is no truncation in this path.

## 2. DMA mapping

- Allocation: `IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
  kIODirectionInOut | kIOMemoryPhysicallyContiguous | kIOMemoryMapperNone,
  kDmaBytes, 4096)` — `PongUfsTransport.cpp:197-200`. `kDataOffset = 8192`,
  `kDataMax = 131072`, `kDmaBytes = kDmaBytesOneSlot = 139,264`
  (`RootTransportLayout.h:16-35`).
- Physical address: `gHost.phys = gHost.dma->getPhysicalSegment(0, &contiguous,
  kIOMemoryMapperNone)` — `:203`; the code refuses unless the segment is
  contiguous and non-zero (`:205-207`).
- PRD: one entry, `prd[0] = low32(gHost.phys + kDataOffset)`,
  `prd[1] = high32(...)`, `prd[2] = 0`, `prd[3] = dataBytes - 1` —
  `RootCommands.h:69-76`; UTRD dword 7 sets one PRDT entry
  (`RootCommands.h:68`).
- `dataBytes` for READ(10) is `blocks * 4096` (`RootCommands.h:285`), i.e.
  4096 for the MBR read, not 512.

## 3. SMMU

- The Apps SMMU is mapped at `0x15000000` (`PongUfsTransport.cpp:233`) and
  planned with `planUfsSmmu(0xe0, gHost.phys, kDmaBytes, read, 78, 120)` at
  `:236` (stream `0xe0`; bank/group limits 78/120).
- `configureUfsSmmu` in `drivers/NativeUfs/SmmuTakeover.h:122-145` puts the
  chosen context bank into **bypass**: `write(cb, 0)`, CBAR `0x10000`,
  CBA2R `1`, SCTLR 0. DMA therefore uses the physical addresses in the PRD
  unchanged; there is no IOVA translation to get wrong for this read.
- `pong_smmu_lease_lock`/`_unlock` are weak stubs here (`PongUfsTransport.cpp:
  39-40`, return false / no-op) and a strong provider exists only in
  `drivers/PongWifi/PongWifiPlatform.cpp:917-918`. On a storage-only link the
  log says `no Apps SMMU lease; storage-only build, bank selection is
  unshared` (`:230`), which means the bank selection is not serialised against
  another SMMU user. That is a risk on a build that also links WiFi/display,
  but it cannot by itself remove two bytes from an otherwise copied sector.

## 4. Cache coherency

- Before ringing: `cacheCivac(gHost.virt, 64)` (UTRD),
  `cacheCivac(gHost.virt + kUcdOffset, kPrdtOffset + 16)` (UCD/PRDT) and
  `cacheCivac(gHost.virt + kDataOffset, dataBytes)` (payload) —
  `RootCommands.h:79-81`.
- After completion: `cacheInvalidate(gHost.virt + kUcdOffset + kRspOffset, 512)`
  and, for a device-to-host transfer, `cacheInvalidate(gHost.virt +
  kDataOffset, dataBytes)` — `RootCommands.h:99-100`. The invalidate covers all
  `dataBytes` (4096), so bytes 510-511 are inside the invalidated range.
- `cacheCivac` (`PongUfsTransport.cpp:113-118`) aligns the start down to 64
  bytes; `cacheInvalidate` (`:119-125`) starts at the exact pointer. Both
  `gHost.virt + kDataOffset` (page-aligned + 8192) and
  `gHost.virt + kUcdOffset + kRspOffset` (page-aligned + 4608) are 64-byte
  aligned, so both helpers cover their ranges exactly.

## 5. 16.6.1 same-path comparison

Checked out at `origin/archive/ios16-final-20261119`,
`drivers/NativeUfs/PongUfsTransport.cpp` (621 lines):

- `doAsyncReadWrite` at `:461-555` is byte-identical to the 27 loop at
  `:646-780`, except (a) the 27-only `#if defined(NATIVE_VERIFIED_BLOCK)`
  branch at `PongUfsTransport.cpp:682-720`, which is compiled out unless
  `CONFIG_XNU_VERIFIED_ROOT_PROBE` is set (the 27 defconfig does not set it),
  and (b) an explicit `return kIOReturnSuccess` at the end.
- The 16.6.1 publication order is `wanted[]` order — OS, SystemOS, Data —
  `:604-612`. It has no `RootPublication.h` plan at all.

The one 27-specific difference that changes **what block 0 of the first
published disk contains** is the publication order:

| | 16.6.1 | 27 (`dd45964b`) |
| --- | --- | --- |
| First registered block device | `OS` — a GPT disk image: protective MBR at +0 with `0x55AA` at +510, `EFI PART` at +512 | `SystemOS` — a raw APFS volume: `NXSB` at +32, **no MBR at all** |
| Second | `SystemOS` (raw APFS) | `OS` (the GPT disk) |
| Third | `Data` (GPT disk, when `XNU_PONG_UFS_DATA`) | `Data`, if present |

`ufsBuildRootPlan()` sets `plan.order[0] = system` at
`drivers/NativeUfs/RootPublication.h:17` and puts `os` last (`:20`);
`PongUfsTransport.cpp:1010-1024` registers the blocks in that order. The
commit message `dd45964b "feat(ufs): publish root windows in the reference
order"` records the change and says "the old loop started OS before SystemOS";
no document in this tree states why the reference order is required for the
K60 boot.

## 6. Conclusion

1. `K60UFS` is a write trace. It proves the write path ran; it says nothing
   about reads, because reads are only logged after the Data volume lookup arms
   `gHost.readTrace` (`PongUfsTransport.cpp:495-505`).
2. The read path itself cannot drop the MBR tail. For `(0, 512)` it copies
   exactly 512 bytes from DMA offset 0 of the correct 4 KiB physical block, and
   the DMA/SMMU/cache handling above is identical to the 16.6.1 line where the
   same read works.
3. The 27-specific change is which disk is **disk0**: `ufsBuildRootPlan()`
   publishes `SystemOS` first. `SystemOS` is a raw APFS volume (`NXSB` at +32),
   so a reader that opens "partition 0"/`disk0` and checks the MBR tail finds
   the APFS superblock at +32 and no `0x55AA` at +510. 16.6.1 published `OS`
   first; the `OS` window is a GPT disk whose first sector is a protective MBR
   with `0x55AA`. That is the only code-level difference that explains the
   symptom without contradicting the driver trace.
4. The driver also never checks the MBR before publishing: `prepareForPublish`
   only compares the GPT signature at `window.signatureOffset` (+512 for
   OS/Data) at `PongUfsTransport.cpp:600`. A window whose first sector is zero
   is published as a healthy 512-byte disk.

## 7. Minimal fix draft

File: `docs/research/storage/UFS27-MBR-READ-FIX.patch` (3 files, +16/−7;
`git apply --check` passes against `f60da7e0`). It is a draft: not applied, not
built.

1. `drivers/NativeUfs/RootPublication.h:17` — publish `OS` first, `SystemOS`
   second (`plan.order[0] = os; plan.order[1] = system; position = 2;`). This
   restores the 16.6.1 disk order for the stage-0 boot. If the reference order
   is later required for the verified-root path, gate this block on
   `NATIVE_VERIFIED_BLOCK` rather than reverting it.
2. `drivers/NativeUfs/PongUfsTransport.cpp:600` — after the GPT signature
   check, for a GPT window (`signatureOffset == 512`) also require
   `bounce[510] == 0x55 && bounce[511] == 0xAA`, and fail with
   `SHNGROOT window MBR signature missing`. This turns a silent wrong-disk
   publish into a named boot failure.
3. `drivers/NativeUfs/tests/RootPublication.cpp:46/49/52` — the unit test
   currently asserts `SystemOS` first; update the three order assertions to
   `OS` first and the `puts` summary text.

Apply check (offline, re-runnable):

```sh
cd E:/k60-work/ufs27
git apply --check docs/research/storage/UFS27-MBR-READ-FIX.patch
# expected: exit 0, no output
git apply --stat docs/research/storage/UFS27-MBR-READ-FIX.patch
# expected: 3 files changed, 16 insertions(+), 7 deletions(-)
```

## 8. Optional diagnostic (not in the patch)

If the fix is not applied first, the cheapest way to confirm the conclusion on
the next boot is a one-line unconditional trace at the top of
`doAsyncReadWrite` when `block == 0 && count == 1`:

```cpp
IOLog("K60RD first name=%s base=%llx len=%llu dir=%d\\n", window.name,
      (unsigned long long)window.baseByte, (unsigned long long)buffer->getLength(),
      buffer ? (int)buffer->getDirection() : -1);
```

with a matching dump of `((const uint8_t *)gHost.virt + kDataOffset)[508..511]`
after the copy. Expected on a correct OS-first boot: the line names `OS`, and
bytes 508-511 are `00 00 55 AA`; if it names `SystemOS`, the conclusion is
confirmed without a rebuild of the fix.

## 9. Next-step criteria

| Step | Re-runnable check | Expected | Criterion |
| --- | --- | --- | --- |
| Patch shape | `git apply --check docs/research/storage/UFS27-MBR-READ-FIX.patch` | exit 0 | applies cleanly to `f60da7e0` |
| Unit test (host) | build `drivers/NativeUfs/tests/RootPublication.cpp` and run | `PASS: … OS first/SystemOS second …` | the three order assertions pass |
| Next boot | `K60RD first …` (diagnostic) or the kernel's own MBR probe | `name=OS`, `… 00 00 55 AA`; no `SHNGROOT window MBR signature missing` | disk0 is the OS GPT disk and the MBR tail is present |
| Regression | same boot, SystemOS/Data mount lines | SystemOS and Data still appear and mount as before | order change does not disturb the mounts |

No command in this page builds the kernel or touches the device; the unit test
row is a host compile that the no-build rule leaves to the Lead.
