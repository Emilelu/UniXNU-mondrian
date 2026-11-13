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

All seven images were built from the same ten-stage kernel
(`kernel.macho` sha256 `f430c2177cf1636e6265ef6a7c729802d3847dd518bfdb62efb78f30841197ef`,
archive `/opt/k60/trees/k60build/wifi/native-stage/libPongWifiNative.a`
11,943,304 B) and each passed `scripts/verify-boot-image.py`. Build recipe:
`E:\k60-work\evidence\wifi-trial\mkboot-ladder.sh`.

| image | boot-args | what it must prove |
| --- | --- | --- |
| `wifi-20261115a` `a261340b…` | `pong_wifi=0` | control: this kernel still boots and gives a console |
| `wifi-20261115b` `493fab93…` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=1` | console gate + stage plumbing, one TLMM write only |
| `wifi-20261115c` `1126de64…` | `pong_wifi=1 k60_wifi_stage=3` | SPMI/PMIC page and cmd-db read, **no RSC access at all** |
| `wifi-20261115d` `410e02e8…` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=4` | first RSC read (probe-only mode) |
| `wifi-20261115e` `e45e50d9…` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=5` | real rail votes plus GCC GDSC/refgen |
| `wifi-20261115f` `c7c39525…` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=8` | host MMIO, PHY table, PERST, link training |
| `wifi-20261115g` `4173014a…` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=10` | SMMU context, MSI attach, `ath11k start` |
| `wifi-20261115h` `20908a03…` | same as g | same as g, but with `bdwlan.elf`/`bdwlang.elf` inside PWF2 (six files, 11,189,974 B; kernel `73c33075…` 65,978,368 B) |

Stop the ladder at the first image that loses the console: the rung that was
new in that image is the one that hangs the interconnect. A successful rung
prints its `stage N (…)` line, then the `held back` line for N+1, then
`WiFi initialization stopped; normal iOS boot continues, DMA retained`.

Milestones inside the ladder:

- stage 3 clean ⇒ the cmd-db/SPMI path is safe before any RPMh traffic.
- stage 4 clean ⇒ the RSC probe in `k60_wifi_rsc=1` mode is safe; if stage 4
  dies while stage 3 lives, the RSC is the killer and the rail votes must be
  restructured before any further attempt.
- stage 8 clean ⇒ `QCA6490 PCIe0 link and BAR established, bus master held off`
  and `QCA6490 PCI subsystem=10817cb` appear, i.e. the endpoint is enumerated
  and the 17CB:1103 / BAR0 0x60200000 / IOVA 0xA0000000 facts from ③ are
  confirmed on the device.
- stage 10 is the first rung that can reach firmware load. Image `g` carries the
  four-file PWF2 and will stop at the missing board data file (see `FIRMWARE.md`
  §8) after logging the exact `bdwlan*` name ath11k asked for; image `h`
  already carries `bdwlan.elf`/`bdwlang.elf` (`FIRMWARE.md` §9), so it can get
  past board data when the real board id is 0xff.

Runner: `E:\k60-work\evidence\wifi-trial\ladder-run.ps1` (races fastboot,
then walks the table in order, writing `E:\k60-work\evidence\usblog-wifi-ladder-<tag>`).

Never `fastboot flash`; always `fastboot boot`, always with the collector
armed first (`docs/engineering/BOOT-PROCEDURE.md`).

## 5. Blocking issue right now

Since 04:50 the phone enumerates neither ADB nor fastboot, and
`Get-PnpDevice` has no live `VID_2717`/`VID_18D1`/`VID_1209` entry, so no boot
can be attempted until the phone is power-cycled by hand (hold power ~10 s).
The staged kernel is ready and waiting for that.
