# Boot-death suspects: why the wifi images died before any console output

Status: working hypothesis ledger (⑧). Written 2026-11-15 after
`wifi-20261116mhi3` and `wifi-20261116mhi4` both returned
`state=port-not-observed, bytes=0, returnedToFastboot=true` with a zero-byte
console. The rule for this file: **every row carries evidence and a way to
disprove it; nothing here is a code change.**

## 0. What is actually known

- The silence happens **before any kernel output**. `k60_usblog_start()` is
  called from `bsd_init.c` after `mac_policy_initbsd()` (patch
  `0300-k60-usblog-ep0.patch`, inserted after
  `if (result == KERN_SUCCESS)`), so a zero-byte console means the machine
  never reached that point: the kernel died or was never entered.
- Both flights were supervised (`usblog-20261115-002243` for mhi4,
  `usblog-20261115-002804` for mhi3): `bootAccepted=true`,
  `bootExitCode=0`, `returnedToFastboot=true`, capture side clean
  (`portSeen=false` is the device never enumerating CDC-ACM, not a collector
  fault).
- mhi3 and mhi4 differ **only** in the ADT window (`0x130000000` vs
  `0x120000000`). Kernel identity must be read from
  `build-manifest.json:components.payload_kernel`, **not** from
  `boot.json:kernel_sha256` — that field hashes the boot image's kernel slot
  (gzip of the 112 B shim plus the 3,145,728 B firmware volume, then the DTB),
  so it is `83b52b56…` on every image that shares the firmware volume (P-200).
  Measured the right way: mhi3 = `0addbb48…`, mhi4 = `e24a58f1…`, both
  65,978,368 B, differing in 47 bytes (26 in `__TEXT`, 21 in
  `__PRELINK_INFO`); `payload.img` is byte-identical and the boot images
  differ in 324 bytes. The peer that boots, `bt-s4a-20261114f`, has the same
  4.5 GiB window and differs from mhi4 in exactly one boot argument
  (`k60bt=1` instead of `pong_wifi=1`) — but a different kernel, so it is
  suggestive, not controlled.

## 1. The stale-kernel confound (established, not a suspect)

mhi3/mhi4 were built from `kernel.macho` (65,978,368 B, Nov 14 23:12) that
predates the rebase and the new `.config`. Kernel build picks it up whenever
the file is newer than the marker; `.config` changes do not invalidate it.
Consequences, all measured on the stale image:

| fact | stale (mhi3/mhi4) | mhi5 |
|---|---|---|
| kernel bytes | 65,978,368 | 117,305,344 |
| battery symbol | absent | `_k60_physical_battery_start` present |
| `__DATA` vmsize | 0x1c8000 (1.8 MiB) | 0x32b0000 (50.6 MiB) |
| `K60LDO` strings (retired touch probe) | 5 | 0 |
| series baked into image | 229 (pre-rebase) | 224 |

So mhi3/mhi4 tested **neither** the current series **nor** the current
config. Any "wifi images die" conclusion drawn from them is unsound; mhi5 is
the first image that tests the current tree.

## 2. Suspects

### S1. PWF2 firmware blob in `__TEXT,__const` (11.2 MB) — **primary suspect**

- Source: `scripts/build-k60-wifi-native.py:102` emits
  `.section __TEXT,__const` + `.p2align 12` + `.incbin`; the whole PWF2
  container (PongWifiFirmware.bin, 11,189,974 B) lands in the kernel's
  read-only first segment.
- Measured on six payload kernels, section table of the `kernel.macho`
  extracted from each `boot.img` (`E:/k60-work/scratch/constsz.py`):

  | image | kernel bytes | `__TEXT` vmsize | `__const` | PWF2 magic | on device |
  |---|---|---|---|---|---|
  | springboard-20261114c | 105,480,192 | 0x1a1321 | 0x85e18 (0.52 MiB) | 0 | SpringBoard |
  | gpu-20261114t | 105,476,096 | 0x1a100e | 0x86028 (0.52 MiB) | 0 | SpringBoard |
  | brightness-9 | 105,500,672 | 0x1a1520 | 0x86038 (0.52 MiB) | 0 | SpringBoard |
  | wifi-20261116mhi5 | 117,305,344 | 0xc61645 | 0xb38ed6 (11.22 MiB) | 2 | untested |
  | wifi-20261116a2 | 65,978,368 | 0xc60ad5 | 0xb38ed6 (11.22 MiB) | 2 | silent |
  | wifi-20261116mhi3 | 65,978,368 | 0xc60c11 | 0xb38ed6 (11.22 MiB) | 2 | silent |

  The 11.19 MB delta between the two groups is exactly the firmware blob, and
  it is the only clean structural difference between kernels that reach
  SpringBoard and kernels that never print a byte. Inside `__TEXT` the blob is
  the first thing mapped: `__const` sits at file offset 0x2000
  (`addr 0xfffffff007006000` for mhi5), with `__cstring` only after it at
  file offset 0xb3aed6. Every booting kernel starts `__cstring` at 0x89008.
- **`a2` does not exonerate the blob.** `wifi-20261116a2` carries the same
  0xb38ed6 `__const`, so whatever it does on device says nothing about S1; it
  only tests the driver (`pong_wifi=0`, no MHI). The earlier plan "if a2 is
  silent, move on to residency" was wrong for exactly this reason.
- Why it could kill: `DarwinBoot.c:195-196` rejects a kernel whose
  Base..End span exceeds `WINDOW_SIZE - 2 MB` — not the binding constraint
  here (mhi5 span 123.6 MB, stale 74.7 MB, both < 254 MB). The sharper risk:
  `AllocateWindow` (`:452-509`) must find `WindowSize` (4.5 GiB)
  **contiguous** in `EfiConventionalMemory` while the loader still holds the
  whole kernel image in one `AllocateZeroPool`; a bigger image shrinks the
  biggest run (`MemoryMapLib.c:82-88` records a failure at a 320 MiB heap with
  "biggest run 0xF0A0000").
- How to disprove: fly T0 `wifi-20261115z0` (`pong_wifi=0`, kernel
  117,305,344 B, same 0xb38ed6 blob). SpringBoard reached → the driver is
  exonerated and the blob is still alive as a suspect for mhi5; silent →
  blob or its residency is the killer, and T2 (blob into `__DATA`, or read
  from the Data volume at runtime) becomes the next image.

### S2. Window arithmetic with the new kernel size — **downgraded to bookkeeping**

- `need ≈ window + kernel_image + fixed` (`LOCAL-VERIFICATION.md`
  §5.16 model, fixed ≈ 177 MB measured on the stale pair). For mhi5 at 4.5 GiB:
  4608 + 112 + 177 = 4897 MB against a 5120 MB arena → slack ≈ +223 MB.
- **Why downgraded:** mhi4 already flew at 4.5 GiB with a 66 MB kernel and
  ≈ +272 MB of slack, and it was still silent. A model that predicts "safe"
  for a flight that died cannot be the explanation; keep it only to size the
  next image.
- It is not discarded because the loader really does need one contiguous
  4.5 GiB run, and a bigger kernel image does shrink the heap. But it is now a
  contributing-factor candidate behind S1, not a peer of it.

### S3. Retired touch `spmi-probe` patch (Lead's HR-01 hypothesis) — weakened

- The patch (`zzzzzz…-pong-touch-spmi-probe.patch`, 93 lines) maps SPMI
  core/observer and polls before `geni_spi_init()` in
  `pong_goodix.c` `bring_up()`. It was in the 229-line series that
  mhi3/mhi4 shipped, so they were exposed.
- Counterevidence: `K60LDO` probe output appears in many healthy captures
  (`usblog-20261113-045951` lines 624-643, `basef2`/`basef4` with
  SB=129) — the probe ran to completion on boots that reached userland.
- Also: it is **not** in the current 224-line series and mhi5 does not carry
  it, so the mhi5 flight is the cleanest test of this hypothesis available
  without another build.

### S4. `pong_wifi=1` kills the boot before the worker's first log — weak

- `ArmDTPlatform.cpp:228` calls `pong_wifi_start_optional()` after
  `registerService()`; the worker first waits up to 120 s for the console
  (`PongWifiPlatform.cpp:655`), so wifi code cannot explain a console that
  never starts.
- The peer flight `bt-s4a-20261114f` differs from mhi4 in exactly one arg
  (`k60bt=1` vs `pong_wifi=1`) and boots. But its kernel is the
  bt line's build (105.5 MB, no wifi objects), so this is suggestive, not
  controlled.
- How to disprove: the mhi5 flight; and if needed, a `pong_wifi=0` build
  of the **same** wifi kernel as an on-device control.

## 3. What each next flight decides

Order set by the Lead on 2026-11-15. Both T0 and T1 must come out of
`scripts/build-strict.sh` — a hand-packed control image carries no series
fingerprint and proves nothing (P-201).

| order | flight | decides | if it boots | if it dies |
|---|---|---|---|---|
| **T0** | `wifi-20261115z0` (ready: `pong_wifi=0`, kernel 117,305,344 B, blob present, 4.5 GiB) | the driver vs the blob: same kernel as mhi5, wifi arg off | driver code is implicated → fly T1 to test the full stack | driver exonerated → the blob or its residency is the killer → go straight to T2 |
| **T1** | `wifi-20261116mhi5` (ready, 117,305,344 B, `pong_wifi=1`) — only after T0 boots | S1+S2 on the full wifi stack, and retires the stale confound | the MHI handshake logs become the next evidence | blob/loader interaction confirmed without the driver |
| **T2** | rebuild with the firmware in `__DATA` (or read from the Data volume at runtime) | isolates blob placement | placement was the killer | S1 falsified; investigate loader/pool with the `NO WINDOW` diag line |

## 3a. The T0 control image (built 2026-11-15 03:49)

`wifi-20261115z0` — first image of this line that is both a control and a
`build-strict.sh` artifact, so its manifest carries the series fingerprint
that `wifi-20261116a2` lacked (P-201):

| field | value |
|---|---|
| series | 224 patches, `34cf51e4d10e46eb3514d798a3e3208c3ac7f124dd8a982585e9eea1e8b9c8c0` |
| `components.payload_kernel` | `ec094bc952930d30f5b18ee43a1e19e0d06898309ec46e80e43121595498ce22` |
| kernel bytes | 117,305,344 (same size as mhi5, different bytes: the arg is baked into the payload) |
| `__TEXT` / `__const` | 0xc64000 / `0xb38ed6` (11.22 MiB, PWF2 magic present twice) |
| `boot.img` | `c2e069f0088a0728e24dbc89338edee2ba9d5f453265d63d42ccb64bc3303728`, 201,887,744 B |
| ADT window | `0x120000000` (4.5 GiB) |
| boot args | 30, 587 B, last one `pong_wifi=0` |
| gates | eight-step passed, kernel archives 4/4, image-arg-audit OK, verify-boot-image OK |

Because the kernel size, the firmware blob and the window all match mhi5 and
only the boot argument differs, z0 is the controlled test of "driver versus
blob" that the plan needs.

## 4. T2 contingency: move the firmware blob out of `__TEXT` (planned, not started)

Written on 2026-11-15 at the Lead's request so the fix is ready the moment
T0 comes back silent. **Nothing here has been built or flown.**

### 4.1 The change is one line

`scripts/build-k60-wifi-native.py:102` emits the assembly that carries the
11,189,974-byte PWF2 container into the kernel:

```python
asm.write_text('.section __TEXT,__const\n.p2align 12\n.globl _pong_wifi_firmware\n'
               '_pong_wifi_firmware:\n.incbin "'+str(pack)+'"\n'
               '.globl _pong_wifi_firmware_end\n_pong_wifi_firmware_end:\n')
```

Change the section name only — `.section __DATA,__const` (or
`__DATA,__data`) — and keep `.p2align 12` so the container stays 4 KiB
aligned. There is no kernel linker script to touch: Mach-O assigns a section
to a segment by the name the input object declares, and the wifi archive is
pulled in with `-Wl,-force_load` (`scripts/build-xnu-4k-baseline.sh:1153`
and `:1186`) which does not constrain layout.

The ready-to-apply diff, its validation, the t2 build recipe and the
pre-flight checks are in `docs/research/wifi/T2-PATCH.md`; this section keeps
the reasoning, that file keeps the executable form.

The C side needs no change at all. `PongWifiPlatform.cpp:35` declares
`extern const uint8_t pong_wifi_firmware[], pong_wifi_firmware_end[]` and
`fwGet()` (`:554-556`) only does pointer arithmetic inside that range
(`*data = pong_wifi_firmware + off`); it never writes. Moving the bytes to a
writable segment is harmless because nothing writes them.

### 4.2 The precedent is already in this tree and it boots

The 51 MB Metal blob takes exactly this route:
`scripts/gen-k60-metal-blob.py:109-119` emits `.data` + `.globl
_k60_metal_blob` + `.incbin`, and it lands in `__DATA,__data`. The image
built from it (`gpu-20261114t`) reaches SpringBoard. So a large read-only
blob in `__DATA` is a proven layout on this board, not an experiment.

### 4.3 The segment budget checks out

Measured with `mcopy` on the payload kernel (script
`E:/k60-work/scratch/prec.py`):

| segment / section | gpu-20261114t (boots) | wifi-20261116mhi5 (silent) |
|---|---|---|
| `__TEXT` vmsize | 0x1a4000 | 0xc64000 |
| `__TEXT,__const` | 0x86028 | **0xb38ed6** |
| `__DATA` vmsize / filesize | 0x3278000 / 0x3130000 | 0x32b0000 / 0x3130000 |
| `__DATA,__data` | 0x3110d08 | 0x31111f0 |

- Moving 11.19 MiB into `__DATA` takes its vmsize from 52.9 MiB to about
  64 MiB. DarwinBoot rejects a segment only above `WINDOW_SIZE` = 256 MiB
  (`DarwinBoot.c:168`), and the whole-image span only above 254 MiB
  (`:195-196`; mhi5's span is 123.6 MB), so both limits stay far away.
- The **file** does not grow: the same bytes simply live in a different
  segment, so the 117,305,344-byte total is unchanged. That matters because
  the loader reads the kernel through `ReadFile (Root, Request->KernelPath,
  SIZE_128MB, ...)` (`DarwinBoot.c:699`) — a 128 MiB hard ceiling that
  mhi5 already sits 10.7 MB under. Any T2 variant that *adds* bytes instead
  of relocating them would eat into that margin.
- `__DATA`'s vmsize exceeds its filesize by `__common` 0x95a18 plus
  `__bss` 0xe96220 (zero-fill, no file cost), which is why the segment can
  grow without the file growing.
- XNU maps segments by name in `arm_vm_init.c` (`:1415` RNX for
  `segTEXTB`, `:1432` RWNX for `segDATAB`), with no hard-coded size
  limit; the assertions at `:2306-2308` only check that adjacent segments
  stay contiguous, which a section move inside `__DATA` preserves.

### 4.4 What T2 would and would not prove

- If the T2 image boots, the killer is *residency of the blob in
  `__TEXT`* — the loader copying or mapping a 128 MiB image whose first
  read-only pages are 11 MB of opaque firmware — and not the firmware
  content or the wifi driver.
- If the T2 image is also silent, S1 is falsified and the remaining suspect
  is the loader/heap interaction (S2), which then needs the `NO WINDOW`
  diagnostic line rather than another placement guess.

### 4.5 Option B: read the firmware from the Data volume at runtime

Considered and deferred. `/private/var` lives on the Data volume, and the
metal plugin patch (`patches/xnu/0610-k60-metal-plugin-deploy.patch`) notes
that no host tool available here can write into it, which is why the Metal
blob went into the kernel instead. A Data-volume firmware would need a new
write path in the loader or the ramdisk — the "register a reserved region,
write it from the loader, rebuild the FD" work in `uefi-mondrian` that the
Lead scoped for T2 — and it costs a full FD rebuild per firmware change.
It stays the fallback if `__DATA` placement turns out to be insufficient.

## 5. Evidence index

- Flights: `/mnt/e/k60-work/evidence/usblog-20261115-002243` (mhi4),
  `usblog-20261115-002804` (mhi3); healthy peers
  `usblog-20261115-012913` (bt-s4a), `usblog-20261115-013520`
  (brightness-4), `usblog-20261114-150931` (touch-20261114a).
- Kernel forensics: `out-wifi/mondrian/…/kernel/stale/kernel-20261114-2312.macho`
  vs current `kernel.macho`; segment tables in the section above measured
  with `E:/k60-work/scratch/seg3.py`.
- Loader constraints: `DarwinBoot.c:168` (segment ≤ 256 MB),
  `:195-196` (span ≤ 254 MB), `:452-509` (contiguous
  `AllocateWindow`), `:723` (ADT `darwinboot-memory-size`),
  `:775` (`Used > WindowSize - BLOCK_SIZE`), `:794`
  (`Args->MemorySize = WindowSize`).
- Probe script: `E:/k60-work/scratch/seg3.py` (segment tables).
