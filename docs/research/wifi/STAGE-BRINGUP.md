# WiFi staged bring-up: why the first boot left no console

Status: active (⑧). Written 2026-11-14 after the first two on-device attempts
returned `port-not-observed` with a zero-byte console.

## 1. What the first attempts did

| image | kernel_args | result |
| --- | --- | --- |
| `wifi-20261114a/boot.img` sha256 `1bf90492…` | `pong_wifi=1 k60_wifi_rsc=1` | `usblog-20261114-wifi-b`: `state=port-not-observed, bytes=0, returnedToFastboot=true` |
| `wifi-20261114b/boot.img` sha256 `cf1d1ed8…` | `pong_wifi=1 k60_wifi_rsc=2` | built, never booted (device went dark) |
| `wifi-20261114c/boot.img` sha256 `622a1fd6…` | `pong_wifi=0` (control) | built, never booted |

The failing capture is `/mnt/e/k60-work/evidence/usblog-20261114-wifi-b`:
`capture.json` has `portSeen=false, portOpened=false, openErrors=0,
stopReason="fastboot-return"`, and `console.log` is 0 bytes. The collector was
armed before `fastboot boot` and the boot itself was accepted
(`bootAccepted=true, bootExitCode=0`), so this is not a capture-side fault: the
kernel returned to fastboot without ever enumerating the CDC-ACM console.

Same supervisor, same FD, same device: `usblog-20261114-raili` captured 220,576
bytes 5 minutes earlier. A peer line hit the same wall at the same time
(`usblog-20261114-bts1b-run1`: `port-not-observed, bytes=0, stopReason=port-timeout`),
so the device itself also became unreliable after 04:50.

## 2. Why the old code could kill the phone silently

`ArmDTPlatform::configure()` calls `pong_wifi_start_optional()`
(`drivers/ArmDTPlatform/ArmDTPlatform.cpp:227-229`) before the USB console
exists. Measured ordering on a good boot
(`usblog-20261114-raili/console.log`, replay included):

- line 85 `MAC Framework successfully initialized` — after `bsd_init.c:655`
  `mac_policy_initbsd()`;
- line 145 `ArmDTPlatform: registered platform cpus=8 …` — the platform
  configure pass;
- line 150 `PONG_UFS: transport ready …` — so `pong_ufs_ready()` is already
  true, and the worker's UFS gate does not delay anything;
- line 190 `K60 USBLOG: worker entry` — `bsd_init.c:1341`
  `k60_usblog_start()`.

The WiFi worker therefore reached `coldLink()` roughly 180 lines of
`bsd_init.c` before the console could print. `coldLink()` touches TLMM, PMIC
rails through RPMh/RSC, the GCC GDSC/refgen, PARF/DBI/PHY/ATU and finally the
82-entry PHY table. Its own comment states the hazard:

```
// REC leaves PCIe0 suspended. Only GCC/TLMM are accessible at this point:
// even an LTSSM read from PARF can cause a NoC fault while GDSC/AHB is off.
```

That is exactly P-49 (`docs/engineering/PITFALLS.md`): a register access into a
block whose clock or power domain is not up hangs the interconnect, the phone
dies before anything is printed, and the next boot shows no trace because the
ramoops ring is per-boot (verified: `Darwin Kernel Version`,
`K60AUTORESET: armed` and `vm_page_bootstrap` each appear once per capture).

## 3. What changed in the driver

Two independent gates, both default-safe.

### 3.1 Console gate (always on)

`worker()` now waits for the kernel's own console state before its first MMIO:

```c
unsigned n=0,c=0;for(;c<240&&!k60_usblog_console_up();c++)IOSleep(500);
if(c==240){fail("console never came up; WiFi skipped before any MMIO");goto done;}
IOLog("PongWifi: console up after %u ms; starting cold link\n",c*500);
```

`k60_usblog_console_up()` (`bsd/dev/k60_usblog.c:1594-1598`) returns
`us >= 4`, i.e. true only after the console has printed
`K60 USBLOG: running (DSTS …)`. It is exported in the kernel image
(`_k60_usblog_console_up`), so the archive links without new shims. Up to 120 s
of patience; if the console never comes up, WiFi is skipped instead of being
allowed to hang the phone before it can say anything.

Consequence: from now on a WiFi fault is visible. The stage line printed just
before the fatal access survives in the capture.

### 3.2 Stage gate (`k60_wifi_stage`)

`stageOpen(n, what)` prints `PongWifi: stage %u (%s)` and returns false when
`n > stageLimit`. `stageLimit` comes from the boot arg `k60_wifi_stage`
(absent or 0 = run everything). Each stage adds exactly one class of MMIO:

| stage | boundary |
| --- | --- |
| 1 | TLMM pinmux for PERST/WAKE/WLAN_EN (GPIO 94/95/96/80) |
| 2 | SPMI controller and PMIC page (`pmicOpen()`) |
| 3 | cmd-db window at 0x80860000 and the per-rail lookup |
| 4 | First RPMh/RSC vote (rails, then mx/cx parents, xo, SN7 NoC) |
| 5 | GCC PCIe0 GDSC, refgen and NoC votes |
| 6 | PARF/DBI/PHY/ATU host MMIO windows |
| 7 | 82-entry vendor QMP PHY table |
| 8 | PERST release and LTSSM link training |
| 9 | APPSSMMU SID 1c01 exclusive 4K context (`isolation()`) |
| 10 | PARF MSI0 to GIC SPI140 attach (`armcpu_spi_attach`) |

Stages 2-4 split `supplies()` on purpose: the SPMI controller, the cmd-db
window and the very first RSC write are three different power domains, and the
first failed boot (`k60_wifi_rsc=1`, whose "read-only" probe still issues RSC
MMIO reads) most likely died on the third one. With `k60_wifi_rsc` absent,
`pong_rpmh_vote()` returns before it opens the RSC, so stage 3 alone never
touches it.

A held-back stage logs `PongWifi: stage N (…) held back by k60_wifi_stage=M`
and `coldLink()` returns false, so `worker()` takes its normal
`done` path: MSI/PERST are only cleared when `hostMmioReady` is set, GPIO 94
is returned, and the log ends with
`WiFi initialization stopped; normal iOS boot continues, DMA retained`
(`fail()` never panics).

## 4. Boot ladder (increasing risk, one boot per step)

### 4.0 The command line must stay under 607 bytes

`DarwinBoot.c:678-684` rejects the boot request when the command line is
`>= sizeof (CommandLine) - 1` (i.e. 607 characters) **or contains any byte
above 0x7f**, and it does so before `ReadFile`/`ParseKernel`. A rejected
request prints nothing to the serial console and returns the phone to
fastboot — indistinguishable from an early kernel hang except that the kernel
was never loaded at all. `BootArgs.h:8` sets `DARWIN_BOOT_LINE_LENGTH 608`.

`board.toml`'s 29 arguments already occupy 575 bytes, so
`pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=10` (+45) would be 620 and be
rejected. The ladder therefore also overrides two baseline arguments to buy
the space back:

- `epoch=1` instead of `epoch=1793709100` (saves 15)
- `debug=1` instead of `debug=0x140` (saves 10, same value)

`unixnu build payload --kernel-arg` overrides by name (`payload.py:119-122`),
so this does not disturb the argument sequence. Do **not** try
`k60_fontscale=0`: `osfmk/console/video_console.c:2844` requires
`scale >= 2 && scale <= 4` and silently ignores 0.

Measured with `E:\k60-work\evidence\wifi-trial\argcheck1.py` (limit 607):
574 / 591 / 591 / 606 / 606 / 606 / 606 / 589 — all compliant.

### 4.1 The eight rungs

All eight images share one kernel: `kernel.macho` sha256
`73c33075d44d231360f26b771bae5bd3ae893ae5fd9865cf8ffcb73f342cfc75`,
65,978,368 B, whose PWF2 payload is the **six-file** pack
(`_pong_wifi_firmware` `fffffff007094000` … `_pong_wifi_firmware_end`
`fffffff007b3fed6`, span 11,189,974 B — see `FIRMWARE.md` §9). Archive:
`/opt/k60/trees/k60build/wifi/native-bdf/libPongWifiNative.a` 12,066,184 B.
Each image passed `scripts/verify-boot-image.py` **and** `argcheck1.py`.
Build recipe: `E:\k60-work\evidence\wifi-trial\mkboot-ladder4.sh`.

| image | boot-args (after the two overrides) | len | what it must prove |
| --- | --- | --- | --- |
| `wifi-20261115a` `4cd55196…` | `pong_wifi=0` | 574 | control: this kernel still boots and gives a console |
| `wifi-20261115b` `22edfa71…` | `pong_wifi=1 k60_wifi_stage=1` | 591 | console gate + stage plumbing, one TLMM write only |
| `wifi-20261115c` `97d122d5…` | `pong_wifi=1 k60_wifi_stage=3` | 591 | SPMI/PMIC page and cmd-db read, **no RSC access at all** |
| `wifi-20261115p` `c470091a…` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=4` | 606 | the RSC **read** alone: probe succeeds, every vote is refused |
| `wifi-20261115d` `dfb916fc…` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=4` | 606 | first RSC probe **and** the rail votes |
| `wifi-20261115e` `922627bf…` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=5` | 606 | plus GCC GDSC/refgen/NoC |
| `wifi-20261115f` `418d07ec…` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=8` | 606 | plus host MMIO, PHY table, PERST, link training |
| `wifi-20261115g` `f27b9cb8…` | `pong_wifi=1 k60_wifi_rsc=2` (all stages) | 589 | plus SMMU context, MSI attach, `ath11k start`, firmware load |

Every rung already carries `bdwlan.elf`/`bdwlang.elf`, so image `g` can get
past the board-data request when the real board id is `0xff`; if it is not, the
log names the exact `bdwlan*` file ath11k wanted and that name is the board
selection evidence (`FIRMWARE.md` §8).

`wifi-20261115h` (`20908a03…`, 620 bytes) is **superseded and must not be
booted**: it exceeds the 607-byte limit and would be rejected before the kernel
loads, producing a silent `port-not-observed` capture.

Stop the ladder at the first image that loses the console: the rung that was
new in that image is the one that hangs the interconnect. A successful rung
prints its `stage N (…)` line, then the `held back` line for N+1, then
`WiFi initialization stopped; normal iOS boot continues, DMA retained`.

Milestones inside the ladder:

- stage 3 clean ⇒ the cmd-db/SPMI path is safe before any RPMh traffic.
- stage 4 clean ⇒ both the RSC probe and the first rail votes are safe. Rung
  `p` already splits that pair: it runs stage 4 with `k60_wifi_rsc=1`, so the
  probe reads `0x17a20000` and then every vote is refused. `p` clean ⇒ the
  read is safe and the fault (if any) is in the write. `p` dies ⇒ the plain
  read of the RSC window is the killer, and no voting scheme can be attempted
  before the RSC power/NoC domain is proven some other way.
- stage 8 clean ⇒ `QCA6490 PCIe0 link and BAR established, bus master held off`
  and `QCA6490 PCI subsystem=10817cb` appear, i.e. the endpoint is enumerated
  and the 17CB:1103 / BAR0 0x60200000 / IOVA 0xA0000000 facts from ③ are
  confirmed on the device.
- stage 10 is the first rung that can reach firmware load. Image `g` carries the
  six-file PWF2, so it either passes board data (real board id `0xff` ⇒
  `bdwlan.elf`/`bdwlang.elf`) or stops right after logging the exact `bdwlan*`
  name ath11k asked for — that name is the board selection evidence
  (`FIRMWARE.md` §8/§9).

Runner: `E:\k60-work\evidence\wifi-trial\ladder4-run.ps1 -RaceSeconds 7200 -Seconds 150 -Tag ladder5`
(races fastboot every 0.7 s, then walks the table in order, writing
`E:\k60-work\evidence\usblog-<stamp>-ladder4`; it waits up to 240 s after each
rung for the phone to come back to fastboot and stops on the first timeout).

Never `fastboot flash`; always `fastboot boot`, always with the collector
armed first (`docs/engineering/BOOT-PROCEDURE.md`).


### 4.2 Fallback: the size bisect rungs

Rung `a` already answers "does this 65.9 MB kernel boot at all?", because it is
the same kernel with the WiFi worker switched off. Only if `a` also returns a
zero-byte console do the two size-bisect rungs matter. Both are built from a
second kernel whose PWF2 pack is four 23-byte synthetic files, so the kernel is
54,804,480 B (only 622,592 B above the proven 54,181,888 B baseline) instead of
65,978,368 B:

| image | boot-args | len | what it must prove |
| --- | --- | --- | --- |
| `wifi-20261115t0` `6b21772f…` | `pong_wifi=0` | 574 | the WiFi code linked into the kernel is harmless when its worker never runs |
| `wifi-20261115t1` `3de009f2…` | `pong_wifi=1 k60_wifi_stage=1` | 591 | stage 1 alone (TLMM pinmux for PERST/WAKE/WLAN_EN) is safe |

Kernel sha256 `92fad10599f5ded612426e555093d20e9ac9f4a9ae641da73aa60a56185059cd`,
archive `/opt/k60/trees/k60build/wifi/native-tiny/libPongWifiNative.a` 892,616 B,
firmware `/mnt/e/k60-work/impl/wifi/work/fake-fw/` (synthetic — these two images
can prove a point about the boot path but **cannot** reach a real firmware load).
Recipes: `build-tiny-archive.sh`, `build-tiny-kernel.sh`, `mkboot-tiny.sh`.

Reading the pair:

- `t0` boots, `a` did not ⇒ the 11.2 MB of embedded firmware is what breaks the
  boot, not the driver code. Two mechanisms fit and §7 says why both are live:
  the Mach-O layout moves every segment by 11.2 MB, **and** the kernel image
  stays allocated in the DXE heap while `AllocateWindow` asks for its
  contiguous 256 MB, so a bigger image leaves less room for that request. The
  next move is a firmware pack loaded from the FAT payload instead of being
  linked into `__TEXT,__const`.
- `t0` also fails ⇒ the WiFi archive itself (or its `ArmDTPlatform` hook) breaks
  a 54.8 MB kernel; compare against a stock 54,181,888 B baseline image booted
  with the same arguments.
- `t1` dies while `t0` lives ⇒ stage 1's four TLMM pin writes are the killer, and
  nothing past stage 1 can be attempted until the TLMM window is proven.


## 7. Loader facts checked while the phone was dark

These were read out of `/mnt/e/hackios/uefi-mondrian` and they constrain what a
"no console at all" capture can mean.

- **Command line ≤ 607 bytes** (`DarwinBoot.c:678-684`, `BootArgs.h:8`). Over
  the limit the request is refused before `ReadFile`, so the kernel is never
  loaded and nothing reaches the console.
- **Kernel read cap is 128 MB** (`DarwinBoot.c:699`, `SIZE_128MB`), ADT and
  trust cache are capped at 16 MB. Our 65.9 MB kernel is not near the cap.
- **Segment sanity** (`ParseKernel`, `DarwinBoot.c:140-205`): each
  `LC_SEGMENT_64` must satisfy `filesize <= vmsize`, `vmsize <= 256 MB`,
  `fileoff + filesize <= file size`; `LC_MAIN` must point into a file-backed
  executable segment; segments may not overlap; and
  `Kernel.End - Kernel.Base` must stay under 254 MB. A local reimplementation of
  those rules (`E:\k60-work\evidence\wifi-trial\parsecheck.py`) passes both the
  65.9 MB WiFi kernel (span 78,213,120 B) and the 54.2 MB baseline
  (66,301,952 B), with zero overlaps, so the WiFi kernel is **not** malformed.
- **Order matters for the heap question**: `AllocateWindow` runs at
  `DarwinBoot.c:751`, the kernel image buffer is released only at
  `DarwinBoot.c:818`. So at the moment the firmware asks for one contiguous
  `WINDOW_SIZE` (256 MB) run, the 65.9 MB image is **still** allocated. With
  the baseline 54.2 MB image the same request leaves ~11.7 MB more headroom.
  `MemoryMapLib.c:83` gives the DXE heap 384 MB (`0xC7000000` + `0x18000000`)
  and `:76-82` records that a 320 MB heap already failed once with
  `biggest run 0xF0A0000`, so headroom is not obviously ample. This is the
  second reason the size-bisect rungs exist.
- **A window failure is visible on the panel, not on serial**:
  `AllocateWindow` prints `DARWINBOOT: no window 0x%lx, biggest run 0x%lx at
  0x%lx` to the advanced logger and draws `NO WINDOW …` / `FREE …` lines
  (`DarwinBoot.c:488-512`). A zero-byte serial capture is consistent with that
  path, which is why the phone's screen (not the console) is the tie-breaker.
- **A good DarwinBoot run does talk on serial**: `DARWINBOOT: ARM64 va=… pa=…
  args=… entry=… owned=…`, `DARWINBOOT: command line: …`,
  `inputs validated; exiting boot services` (`DarwinBoot.c:845-851`). Seeing
  those lines but no kernel output would move the fault into XNU's own early
  boot instead of the firmware.

## 6. How to read each rung's capture

Run `python3 E:\k60-work\evidence\wifi-trial\analyze-ladder.py <evidence dir>`
(it prints the capture verdict plus an ordered timeline of the PongWifi markers).
The verdict decides the next move:

| capture verdict | what it means | next move |
| --- | --- | --- |
| `port-not-observed`, `bytes=0`, `stop=fastboot-return` | nothing reached the console. Check `argcheck1.py` **first** — a >607-byte command line produces exactly this. If the length is fine, the kernel died before `k60_usblog_start` | boot the control rung `a`; if `a` also gives 0 bytes, the fault is in the image, not in WiFi |
| `captured-…`, console has `console up after N ms` then `stage 1 (…)` … | the worker is alive and the gates work | read the timeline: the **last** `stage N` line names the last block that survived; the rung that died is N+1 |
| console has `stage N (…) held back by k60_wifi_stage=M` | this rung ran exactly what it was asked to and stopped cleanly | the rung passed: move up one rung |
| `WiFi initialization stopped; normal iOS boot continues, DMA retained` | the worker took its `done` path — iOS kept booting | expected ending for every rung below 10 |
| `QCA6490 PCI subsystem=10817cb` + `link and BAR established` | ③'s endpoint facts are confirmed on real hardware | stage 8 passed; the next rung exercises SMMU/MSI |
| `Pong: actual QMI board firmware <name>` then `ath11k start failed` | firmware asked for a `bdwlan*` file that is not in PWF2 | that name **is** the board-data selection evidence (`FIRMWARE.md` §8); pull exactly that file from `/vendor/firmware_mnt/image/qca6490/` |
| `PongWifi: firmware <name> bytes=<n>` | the PWF2 lookup worked and the blob was handed to ath11k | keep reading towards `ath11k start` |
| `QCA6490 station ready` + `runtime state=…` | station up, scan issued | ⑧ target reached; record the boot and update the eight-step table |
| `panic(` / `K60CACHE FAIL` in the console | a real panic, not an interconnect hang | the panic text is in the console; fix that, do not widen the ladder |

Two rules that have already cost a boot each:

1. **Never trust a 0-byte console as "the kernel hung" until `argcheck1.py`
   passes.** The 607-byte limit is enforced before the kernel is read.
2. **Never boot an image whose `build-manifest.json` payload sha256 does not
   match the payload that was current when it was built** — `unixnu build
   payload` overwrites one shared `payload.img`, so a manifest built after the
   next rung's payload will describe the wrong bytes.

## 5. Blocking issue right now

Since 04:50 the phone enumerates neither ADB nor fastboot, and
`Get-PnpDevice` has no live `VID_2717`/`VID_18D1`/`VID_1209` entry, so no boot
can be attempted until the phone is power-cycled by hand (hold power ~10 s).
The staged kernel is ready and waiting for that.
