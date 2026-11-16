# WiFi DMA cache policy: the port encoded an invalid IOKit mode

Date: 2026-11-17
Status: candidate image built, not flown. c8 remains held.

## 0. Summary

The K60 WiFi port asked IOKit for an **invalid mapping mode** on the DMA
arena and on the uncached buffers. `kIOMemoryMapperNone` is `0x800`;
`kIOMapCacheMask` is `0xf00`; OR-ing them produces cache mode 12, which is
not a valid `kIO*Cache` value (the enum ends at 9). Pong's working platform
documents this exact trap and avoids it (E:/hackios/pong-wifi/PongWifiPlatform.cpp:360-371).
The K60 port copied the Pong allocation pattern but kept the MapperNone bit in
the descriptor options, then never applied the write-combining attribute to the
wired arena pages.

This is a *static defect*, independent of how c7 is interpreted: the descriptor
does not request a supported cache mode, and the CPU mapping and DMA agent can
disagree about visibility. The fix is one policy variable. It does not change
the MHI state machine, the event ring, the MSI address, the INTID, the SMMU
mapping, or the firmware.

The candidate has been built but **not flown**. It removes one known defect; it
does not yet prove that this defect is the cause of the c7 stall.

## 1. The exact defect

Base for the experiment: K60 `feat/wifi-bringup` at
`b004fe6c70f79a6b645b92e07072976e7eba1db8` (the c7 baseline; the c8 commit
`5eacc301` is not in this branch).

Before the change, `drivers/PongWifi/PongWifiPlatform.cpp` had:

- `:400` — `buffer()` descriptor:
  `kIODirectionInOut|kIOMemoryPhysicallyContiguous|kIOMemoryMapperNone|(uncached?kIOMapWriteCombineCache:0)`
- `:415-416` — arena descriptor:
  `kIODirectionInOut|kIOMemoryMapperNone|kIOMapWriteCombineCache`

The physical-segment query at `:401` correctly uses
`getPhysicalSegment(..., kIOMemoryMapperNone)`; that is a query flag, not a
mapping mode, and it stays.

Why mode 12 is not a cache policy: `IOMapTypes.h` defines
`kIOMapCacheMask = 0x00000f00`, `kIOMapCacheShift = 8`, and
`kIOWriteCombineCache = 4`, so `kIOMapWriteCombineCache = 0x400`.
`IOMemoryDescriptor.h` defines `kIOMemoryMapperNone = 0x800`.
`0x800 | 0x400 = 0xc00`; `0xc00 >> 8 = 12`. With `uncached=false`, the
`buffer()` options alone are `0x800` (mode 8), not the default either; with
`uncached=true` they are `0xc00` (mode 12). The arena is always mode 12.
Pong's source says the same in plain words:

> `kIOMemoryMapperNone (0x800) overlaps kIOMapCacheMask (0xf00). Passing both
> MapperNone and WC (0x400) asks the buffer mapping for invalid mode 12.`

Pong's working allocation keeps the descriptor neutral and marks the owned
wired pages explicitly:

- `E:/hackios/pong-wifi/PongWifiPlatform.cpp:370-371`:
  `IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
  kIODirectionInOut|kIOMemoryPageable, ArenaBytes, 4096)`
- `:373` `arena->prepare()`
- `:429-436` `clean(arenaVa, ArenaBytes)`, then
  `pmap_set_cache_attributes(ppnum_t((ranges[i].physical+off)>>12),
  VM_WIMG_WCOMB)` for every owned arena page, then
  `pmap_cache_attributes(...) & VM_WIMG_MASK` verification.

The IOKit implementation confirms what the enum says, rather than treating
"invalid" as a harmless spelling: `IOBufferMemoryDescriptor.cpp:285` copies
the cache bits into the descriptor options and `:443` passes
`options & kIOMapCacheMask` to `createMappingInTask`.
`IOMemoryDescriptor.cpp:360-383` has a ten-entry table (modes 0..9);
`vmProtForCacheMode` asserts `cacheMode < 10` and falls back to
`kIODefaultCache` when it is out of range. In c7 the 64 MiB arena allocation
succeeded (console :586), so construction did not fail; what the old code did
*not* get was write-combining. There was also no `pmap_set_cache_attributes`
call anywhere in the K60 path. The arena therefore remained a default,
cacheable mapping while the device read it through the SMMU — exactly the
visibility hole Pong's explicit WCOMB loop closes.

## 2. The candidate change

Worktree: `E:/hackios/k60-wifi-cache`, branch `feat/wifi-dma-cache`.
Commits: `1e8c72ca` (code + host test), `b6aee1bf` (TREE-OWNERS entry), `623674ab` (IOKit fallback evidence in this document), and `c6dae58e` (validate the arena pages with `pmap_valid_page` before setting attributes).

Changes in that worktree's `drivers/PongWifi/PongWifiPlatform.cpp`:

1. `buffer()` descriptor options no longer contain
   `kIOMemoryMapperNone`; the physical query still does.
2. `allocateArena()` allocates with
   `kIODirectionInOut|kIOMemoryPageable`, requires `prepare()`, and zeroes
   the wired arena.
3. `isolation()`, after every arena physical page has been validated with
   `pmap_valid_page(ppnum_t(pa>>12))` and the SMMU ranges have been built,
   calls `clean(arenaVa, ArenaBytes)`, sets
   `VM_WIMG_WCOMB` on every **arena** page (index 1..count-1; the first 4 KiB
   range is the MSI landing page and is excluded), verifies the attribute, and
   fails closed with
   `WiFi owned DMA cache policy not established` if any page does not read
   back as WCOMB.
4. It does not touch the MHI state machine, ER/CH/CMD layout, MSI target,
   INTID, SMMU context, firmware, or `seg_len`.

The host test is
`scripts/tests/test-wifi-dma-cache-policy.py`. It checks the neutral
descriptor, the pageable/wired arena, the clean and WCOMB verification, and
rejects six negative mutants (arena MapperNone+WC, missing pageable, missing
clean, missing WC verification, missing prepare, buffer MapperNone).

## 3. Built artifact

All paths are on the build host / WSL:

| Item | Value |
|---|---|
| tag | `wifi-20261117cache` |
| boot image | `E:/k60-work/artifacts/wifi-20261117cache/boot.img` |
| boot SHA-256 | `ea58a428881150b6367bb83475a661c35de61603b0c072a405cefd3952ff0506` |
| size | 201,887,744 B |
| manifest | `E:/k60-work/artifacts/wifi-20261117cache/build-manifest.json` |
| manifest SHA-256 | `f4e5d2b05890213381d4d64f3224e5cae5a986365d4d6e48d3d228602817dfd4` |
| repo | `feat/wifi-dma-cache` @ `c6dae58e93fefd18b3df5d07e2a2cf8a5cc0d0f9`, dirty 0 |
| kernel | `46524e7e6383c8d210ad2082d363e25bd39f3c017c08c472820d3b6c19380047` |
| payload kernel | `4913fb96dc7314946116b977c69d8d63d1bdea3b5a9d31257c1945accd8a06e0` |
| WiFi archive | `dfe8fa433c1948851d2f8e346bed155a7240f52c297221720f8bff7ae07fa75e` |
| args | 31 items / 602 B, ends `pong_wifi=1 k60_wifi_rsc=2` |
| series | 227 files, `59d8037521a5b07b`, file `bb14a480c6b2ea4b465f409d862394f0ea25cce178d19a63b7253fab3511f9d4` |

Checks already run:

- `python3 scripts/verify-boot-image.py --manifest ...` → `OK`
- `python3 scripts/check-image-args.py --image ...` → `OK (31 arguments, 602 bytes)`
- `python3 scripts/tests/test-wifi-dma-cache-policy.py` → `PASS` (6 negative cases)
- archive strings: `Pong MHI` 18, `pre-push` 0, `amss download begin` 0,
  `WiFi owned DMA cache policy` 1; `_pong_wifi_firmware` in
  `__DATA,__const`, `_pong_smmu_lease_lock` in `__TEXT`.

The archive contains no c8 proactive-AMSS strings; this is the c7 path plus the
cache-policy fix, not c8.

## 4. Flight criteria (prewritten, one variable)

This image may be flown once, with the console capture attached before boot.
Success and failure are judged from the console, not from "the boot looked
normal".

**Setup / one variable**

- Compare against the c7 baseline `b004fe6c`; the only executable change is
  the DMA cache policy in `PongWifiPlatform.cpp`, plus the TREE-OWNERS
  registry entry and host test.
- Do not combine with c8. Do not change boot args, `seg_len`, `iova_start`,
  MSI target, INTID, or firmware on this flight.

**Success — L1 (this experiment passes)**

All of:

1. Boot reaches SpringBoard with a console log; no panic and no boot-death
   before the WiFi driver runs.
2. The c7 timeout line is absent:
   `Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 ...`
3. The event-ring path advances. At least one of:
   - `Pong MHI: event type=` appears in the console, or
   - `Pong MHI: EE event execenv=` appears, or
   - the device advances `exec_env` past SBL (values 2/4/5 etc. as printed by
     the existing instrumentation).
4. `ath11k: failed to power up mhi` is absent, and the MHI/QMI continuation
   lines (if the driver reaches them) appear.

`QCA6490 MSI entered the GIC handler` is **not** required for L1. The shim
replays registered IRQs, so an event can be processed without proving that the
GIC received a hardware MSI. If that line does appear, record it as additional
evidence; its absence is not an L1 failure.

**Success — L2/L3 (follow-on, not this experiment)**

- L2: QMI service/channel bring-up, MHI mission mode, 102 channels.
- L3: `en0`/IO80211 interface published and a scan returns BSS entries.

L2/L3 are not promised by this candidate; they are the next levels to observe
if L1 passes.

**Failure — stop and report**

- Exactly the c7 timeout line returns, with no `event type`/EE line and no
  `exec_env` advance → the cache policy is not the sole blocker; do not fly
  c8 on this result. Preserve the console and report the full MHI line.
- `WiFi owned DMA cache policy not established` appears → the fix refused
  before DMA; record the line; do not retry with a looser check.
- `WiFi DMA allocation`/`wiring` failure → same: stop, report, do not fall
  back silently to the old descriptor.
- Panic, boot death, or no console → stop; capture the image hash and the last
  console line.

## 5. What remains unclosed

- This is not Pong parity: no Pong raw pstore log or Pong `modem_b` firmware
  image is available in this workspace. The static defect stands on its own,
  but the c7 stall may have additional causes.
- The fix marks only the arena pages. The SMMU table buffer and the MSI landing
  page retain their existing policies; that is unchanged from c7 and is not
  part of this variable.
- c8 (proactive AMSS push) remains HOLD. It is not part of this image.
