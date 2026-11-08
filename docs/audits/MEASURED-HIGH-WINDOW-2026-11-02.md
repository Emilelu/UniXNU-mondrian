# K60 measured high-memory window — 2026-11-02

## Scope and state

Goal: replace the 296 MiB managed window with a 4 GiB contiguous XNU window.
Current candidate is host-verified, NOT yet proven to reach XNU or SpringBoard.
No Android partition is flashed; the experiment uses `fastboot boot` only.

## Corrected diagnosis

The earlier `boot-ios16-hi4g.img` had SHA-256
`350227d1a62f3abe7afb651ee2f24270420598e827939ff1ad036b1f4df42dd9`.
Its inflated kernel stream was checked to end in the exact pre-repair UEFI FD
(SHA-256 `bada90e777db7db7b16bc8c1108f802b16ac49fea29b5bae6a43605d3d1b1426`).
The photo reports PE SizeOfImage `0xb000`, entry RVA `0x1110`, PC RVA `0x48fc`.
That metadata matches DarwinBoot, NOT ArmCpuDxe (size `0x10000`, entry `0x1ff4`).
DarwinBoot's RVA `0x48fc` is `str xzr, [x20], #8` in ZeroMem, consistent with
zeroing the falsely advertised window. `[ArmCpuDxe]` identifies the exception
handler's debug module, not necessarily the faulting image. X0 is not FAR.

Earlier guesses about ArmCpuDxe, fixed page-table capacity, a universal 4 GiB
physical-address ceiling, and all high DDR being inaccessible are unsupported.
`none` in adb/fastboot also does NOT establish that XNU has taken over.

## Serial-bound raw evidence collected in Android

Current unit: serial `6033dbec`, product `mondrian`, root adb shell, Linux
`5.10.237-Fuutao-Qn_miao-source-gc28e50058`, MemTotal `11432144 kB`.
Read-only adb collection saved on E:\k60-work\reports:

- live-6033dbec-memory-reg.bin: 96 bytes, binary adb pull,
  SHA-256 `729587c3f0c5c469768dce73a833b3ba35fd9abb091ff22e28141ed34fc0cec6`.
- live-6033dbec-fdt.dtb: 919210 bytes, binary adb pull, FDT totalsize checked,
  SHA-256 `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`.
- live-6033dbec-iomem.txt: rooted live `/proc/iomem` text (UTF-16 host capture).
- live-6033dbec-memory.txt: serial, product, kernel version, meminfo, cmdline,
  raw memory-reg byte output.

BE64 base/size pairs from the exact runtime /memory/reg:

| Base | Size | Exclusive end |
|---|---|---|
| 0x80000000 | 0x6a000000 | 0xea000000 |
| 0xf4600000 | 0xba00000 | 0x100000000 |
| 0x800000000 | 0x37500000 | 0x837500000 |
| 0x900000000 | 0x180000000 | 0xa80000000 |
| 0x840000000 | 0xc0000000 | 0x900000000 |
| 0x837b00000 | 0x1e00000 | 0x839900000 |

There is NO RAM bank in `[0x100000000,0x800000000)` (4..32 GiB).
The old Conv `[0x100000000,0x380000000)` was entirely in that hole.
A hand-authored DTS containing `base=0x80000000,size=12 GiB` is NOT hardware
measurement. Neither is `swinfo.fingerprint=mondrian:12` a reliable SKU proof.

## Minimal candidate

- Restore the accidentally truncated MemoryMapLib.c from git HEAD e06211de,
  preserving all original low-memory descriptors; add ONE arena only:
  `[0x900000000,0xa40000000)`, 5 GiB, AddMem/SYS_MEM/Conv/WB.
- The arena is contained in an actual runtime FDT bank and in top-level
  Android System RAM, has no intersecting fixed reserved-memory reg or iomem
  sub-reservation, and ends below first observed high reserved area
  `0xa69b78000`. This justifies an experiment, not proof of accessibility or
  ownership in the fastboot-loaded firmware context.
- Do not expose all high banks, do not import pong's HYP reservation blindly,
  and do not change the request to 8 GiB.
- Keep AddMem: Silicium MemoryPeim must create both HOB and identity mapping.
  HobOnlyNoCacheSetting skips mapping and is NOT a fix for RamPartitionDxe.
- RamPartitionDxe's separate UINT32 size narrowing exists but is not the
  proven cause of this fault; its fallback does not enumerate Conv pages.
- Match the active firmware-local loader to Darwin22: command line608,
  BootFlags0x2d0, memSizeActual0x2d8, boot_args size0x2e0. The pre-repair dirty
  firmware-local header had Darwin24 offsets despite the iOS16 kernel.
- Describe the 5 GiB handoff arena in the authored DTS and board dram_size;
  keep darwinboot-memory-size 0x100000000 (4 GiB). Other payload bytes,
  kernel.macho, trust caches, boot args and userland remain unchanged.

## Host build result

Firmware build (EDK2 existing toolchain): PASS at 2026-11-02 14:38:16 +08:00.
Firmware SHA-256:
`1c870bb2add6fffe82fb605d5215fde1695523ed8d7d9d7fad8c74a515b3b755`.

Candidate:
`E:\k60-work\candidates\measured-high4g\boot-ios16-measured-high4g.img`
201883648 bytes; SHA-256
`aa6806595e68078c9e769dd854243ea3534e6cc6e03d9e540ef43e1ab0f4ab3d`.
Actual v4 parser verified header1584, 4096 page alignment, gzip member, 112-byte
qualified shim, exact new FD, exact appended DTS, exact 192MiB FAT ramdisk,
4096-byte zero signature area and total length. ADT decoded structurally;
only dram-base/dram-size/darwinboot-memory-size locations were patched.
The old core bootimg verifier reads v4 as v0; its misleading legacy error was
NOT accepted as a successful validation. This candidate has independent strict
round-trip verification in build-verification.json.

## Acceptance and next observation

Before declaring memory device-verified, the photo must show DarwinBoot handing
off at PA in the measured arena and XNU's actual managed-memory print (expected
4096 MiB), with no synchronous external abort. Userland's abn/jetsam trend and
SpringBoard status are separate subsequent acceptance criteria.


## Hardware boot attempt (screen result pending)

2026-11-02T14:50:03+08:00 — ADB reboot bootloader succeeded; fastboot sent 197152 KB and Booting returned OKAY (4.809s total). Afterwards neither adb nor fastboot visible. This establishes transport acceptance ONLY; loader/kernel/userspace state awaits screen photo.

Command: `bash scripts/k60-device.sh boot /mnt/e/k60-work/candidates/measured-high4g/boot-ios16-measured-high4g.img`. No flash was performed.


## Screen result: memory verified, SpringBoard pending

The latest screen reports `mem=4096 actual=4096 managed=4096`. `free_pages` samples are 30,931 and 31,622 (about 484/494 MiB at 16 KiB pages), not monotonically exhausted. MiniIOMobileFramebuffer reports 304–305 frames per 5,000–5,016 ms (~60 fps), indicating active frame presentations.

Alternating text/progress display is consistent with the documented XNU text console and framebuffer sharing the panel; it does not prove reboot. The screen also shows `abn=718..742`, `suggestd`/`xpcproxy` status 163 signal 0, and corpse-creation failures. The corpse message reports a failed crash-report capture, not the original process termination cause. SpringBoard stability remains unconfirmed.

Screenshots: log SHA-256 `40b2b77bd22f87473250395a4b60103e2a65dc5e777014644e137ca00615e3d2`; progress SHA-256 `60832584f9747b2ccfa9bccf24f1aa6af953631ca19fb77592ea7e099707822d`. Preserved under `E:\k60-work\reports`.


## Window size ceiling and the 7 GiB handoff (2026-11-02T17:51:53+08:00)

The installed DRAM is 12 GiB, but XNU/arm64 manages ONE contiguous range, so the
ceiling is the largest contiguous run of real RAM:

| Run | Free span | Note |
|---|---|---|
| 0x840000000..0xa80000000 | 8.65 GiB | first Android reservation at 0xa69b78000 |
| 0x80000000..0xea000000 | 0.61 GiB | low bank, heavily carved out |
| 4..32 GiB | 0 GiB | hole: no DRAM at all |

A 12 GiB window is therefore impossible on this board: no single run is that
long, and the 4..32 GiB hole holds no DRAM. DarwinWindowSizeValid also caps a
window at 8 GiB.

An 8 GiB window (arena == whole 8 GiB) FAILED: the loader returned to the UniXNU
menu because DXE holds part of the arena, leaving no contiguous 8 GiB run. The
working configuration is an 8.625 GiB arena with a 7 GiB window, which keeps
1.6 GiB of head-room.

Loader evidence for the 7 GiB boot (screen photograph, 2026-11-02):

    kernel va 0xfffffff004420000  pa 0x8400200000
    entry  pa 0x8430364A00
    args   pa 0x8433E8000  window 0x1c0000000 bytes      <- 7 GiB accepted
    HANDOFF EXIT RETURN 0000000000000000                  <- ExitBootServices OK
    green bar at the top                                  <- DarwinEnter ran

So the handoff is good and the window is inside the measured arena. What the
kernel then prints is the next observation; this is not yet SpringBoard.
