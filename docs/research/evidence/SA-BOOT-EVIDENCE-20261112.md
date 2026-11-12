# SA: boot evidence — the battery-enabled image reached SpringBoard, and touch stage 19 never ran

Date: 2026-11-12, audit cut at `2ccb3c715693683676e18cdd947069322821f2f6` (19:27:57 +0800).
Scope: read-only inspection of existing captures, build logs, Git history, and the compiled touch source. No boot, sync, build, or device operation was performed. The only file created is this evidence note. The fixes in `8ffa043` were authored by the Lead while this audit ran; they are cited, not claimed as this audit's work.

## Verdict

1. `E:\k60-work\usb-a-stage\out\boot-uuid.img`, built from the defconfig that still had `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`, mounted Data read-write, executed `/sbin/launchd.ios`, and spawned `SpringBoard[26]`. Its capture ended only when the 90 s budget expired. The `=y` build did not die early, and the 0-byte log that suggested it did is a capture artifact.
2. The battery symbol was also inert in that build. `unixnu` exports `CONFIG_XNU_*` as `XNU_*` environment variables, but `build-xnu-4k-baseline.sh` never reads `XNU_K60_PHYSICAL_BATTERY`, never force-loads `libK60PhysicalBattery.a`, and the patch itself says that parent integration must do both. The linked kernel inspected at 18:56 contains no battery object or symbol, and neither boot log contains a `K60Battery:` line.
3. `k60_touch_se=19` is stale and outside the driver contract. The driver accepts 1..7 (0 disables, default 6). At 19 it prints one line and returns before any clock, probe, config, or polling. The absence of Goodix polling in these logs is exactly what stage 19 produces; it is not evidence that the controller hung. `board.toml:179` was corrected to 6 in `8ffa043`; the two 18:4x/18:5x images were built before that correction.

## Images and captures

| Item | `boot-uuid.img` | `boot-nobat.img` |
|---|---|---|
| Image bytes | 201,887,744 | 201,887,744 |
| Image SHA-256 | `25CC2C7C952B7A5AFD6A6AB21FAE61C1948B3A78B7F9800F9B4A35447886DB31` | `CDD1048D0E5E5C5D8234D3DEFFF749A167200CC21F4D936B308F8CBAAE4B1F13` |
| Kernel SHA-256 at build | `51a8895812e959f0c03a72fadb74001a35dc04afb6a86206f5a603e9182340b7` (`/tmp/build-r84.log:18`) | `379e5337fa712999f29c6612397134e7fe8325c0232ad6adeda48e82dd8cba03` (`/tmp/build-r86.log:18`) |
| Build-time battery config | `CONFIG_XNU_K60_PHYSICAL_BATTERY=y` (`aca503f^:configs/mondrian_defconfig:72`) | `# CONFIG_XNU_K60_PHYSICAL_BATTERY is not set` (`aca503f:configs/mondrian_defconfig:72`) |
| Evidence directory | `E:\k60-work\evidence\usblog-20261112-184616` | `E:\k60-work\evidence\usblog-20261112-185824` |
| `console.log` bytes / SHA-256 | 91,673 / `39FA506A44C7184917AFA8FA561062B59D8C3F5114669C26360320398F10F504` | 91,464 / `5F048398321EE95CC4DE119606B401527A105B10FC4BC667BDEF6D19729D6969` |
| `capture.json` image binding | lines 2-3 bind `E:\k60-work\usb-a-stage\out\boot-uuid.img` and `25CC2C...` | lines 2-3 bind `E:\k60-work\usb-a-stage\out\boot-nobat.img` and `CDD1048D...` |
| Capture window | 90 s, `finishedAt 2026-11-12T18:48:02` | 90 s, `finishedAt 2026-11-12T19:00:11` |
| Termination | `panicMarker: null`, `resetMarker: null`, `deviceGone: false`, `reopenCount: 0`, `complete: false`, reason `budget exhausted while data was still arriving` | identical fields |

The first directory from that boot, `E:\k60-work\evidence\usblog-20261112-184609`, contains a 0-byte `console.log` at 18:46:32 and no `capture.json`. It is not an image-bound capture and must not be used as a boot verdict.

## Boot log anchors

Line numbers below are exact for each 1,411-line and 1,405-line file.

| Event | `usblog-20261112-184616\console.log` | `usblog-20261112-185824\console.log` |
|---|---|---|
| Data UUID `1BCD69FF-24A5-48B1-94B6-8FE592B2F597` bound to `/dev/disk5s1` | 306 | 284 |
| `K60DATA mount returned error=0 result=0 rw=1` | 381 | 430 |
| `K60DATA mounted ro=0 fstype=apfs` | 483 | 456 |
| `/sbin/launchd.ios` exec | 671 | 670 |
| `SpringBoard[26]` | 1089 | 1086 |
| Last heartbeat `K60HB t=105 ... lw=spawn` | 1371 | 1367 |
| Tail | 1411, `tx_flush:1241: disk5 xid 29547 ...` | no panic/reset line |

The presence of `SpringBoard[26]` plus a t=105 heartbeat with `lw=spawn`, and the absence of a panic marker, is normal forward progress, not an early death. The capture was cut at 90 s while bytes were still arriving, so the logs do not prove full UI readiness; they do prove Data mount and userland launch.

## Why the first log was empty: two readers on one CDC-ACM port

At the time of these boots, `E:\k60-work\scripts\flash.sh` started two collectors:

- `flash.sh:102-109` launched `capture-k60-usblog.ps1` in the background with its own `usblog-$(date +%Y%m%d-%H%M%S)` directory (`:104-108`).
- `flash.sh:113-118` then ran `boot-and-capture.ps1`, whose old revision created a second timestamped `$outDir` (`boot-and-capture.ps1:98-100`) and opened the same `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` USBSER port (`:55-62`, `:124-132`).
- `flash.sh:124-131` judged only the first directory's log. A 0-byte file there printed the "kernel died before USB gadget init" verdict at `:130`, while the real 91 KB log was written by the second reader in the sibling directory.

This is the complete explanation of the false "early death": one boot, two evidence directories, and a verdict that read the loser's file. The battery configuration was never implicated by any byte of the real log.

The Lead's `8ffa043` replaces this with a single-writer contract: `scripts/capture-k60-usblog.ps1` is the only `SerialPort` owner and takes a named mutex (`:23-29`, `:43`); `scripts/boot-and-capture.ps1` never opens a port and waits for `capture.ready` before `fastboot boot` (`:3`, `:23-26`, `:49-58`); `scripts/flash.sh:7-11` documents the single collector. That is the correct structural fix; the 18:4x evidence above predates it.

`capture-k60-usblog.ps1` now writes both `capture.json` and `capture-events.jsonl` (`scripts/capture-k60-usblog.ps1:20-21`, `:28`, `:128`), so a future 0-byte directory can be distinguished from "no port ever appeared".

## Why `CONFIG_XNU_K60_PHYSICAL_BATTERY=y` was inert

`E:\hackios\UniXNU\scripts\unixnu\kernel.py:17-26` converts every `CONFIG_XNU_*` value from the selected defconfig into an `XNU_*` environment variable for the legacy kernel script. Thus `=y` exported `XNU_K60_PHYSICAL_BATTERY=1` into the build environment at 18:43.

That variable has no consumer:

- `.../tree/scripts/build-xnu-4k-baseline.sh` has zero matches for `Battery`, `BATTERY`, `PHYSICAL`, or `PongPower`. The only custom defines near the IOKit area are `XNU_OWNER_BOOT_MANIFEST` (`:615`) and `XNU_K60_ACCEL_STUB` (`:1200`).
- `patches/xnu/0602-k60-physical-battery.patch:10-12` states the required parent integration explicitly: "must force-load libK60PhysicalBattery.a and define XNU_K60_PHYSICAL_BATTERY=1 for IOKitBSDInit.cpo". The patch only adds the guarded declaration and call at `:17-27`; neither the archive nor the define is wired into the build.
- No `libK60PhysicalBattery.a` exists under `/opt/k60`; `scripts/build-k60-physical-battery.py` exists but is not invoked by the build script.
- `llvm-nm -a` on the linked `kernel.macho` lists every object via `OSO` entries. `IOKitBSDInit.cpo` is present, but there is no `K60Battery.o`, no `PongPower` object, and no `K60Battery`/`k60_physical_battery` symbol. The battery-related hits are Apple's `IOPMPowerSource` symbols only.
- `drivers/PongPower/K60Battery.cpp:416-432` logs on every start path (`:424` invalid board config, `:432` blocked with no PAS1 handoff, `:441` source setup rejected). Neither 91 KB log contains `K60Battery`, `k60_battery`, or `physical_battery` (0 matches in both).

The `=y` build therefore differed from the `=n` build by an unused environment variable, not by linked battery code. Even if the code had been linked, the image booted to SpringBoard, so the proposed "battery driver caused the early death" explanation is contradicted by the capture itself.

## Touch: `k60_touch_se=19` is stale and invalid

Both logs contain exactly one touch line and no Goodix polling:

- `usblog-20261112-184616\console.log:217`: `Pong touch: unsupported k60_touch_se=19; normal UI boot continues`
- `usblog-20261112-185824\console.log:229`: same text
- The effective boot-args in the first log show the value (`:678-679`; the line is interleaved with a kernel `KE 3 2 launchd /sbin/fsck` fragment, but `k60_touch_se=19` is unambiguous).

Supported values and behavior:

- `docs/engineering/BOOT-ARGS.md:23` documents `k60_touch_se` as `0..7`, default 6; `:141` is the detail section; `:232` shows the expected `k60_touch_se=6`.
- The compiled source used by the booted kernel is `.../tree/.cache/xnu-work/bsd/dev/pong_goodix.c` (1,337 lines, SHA-256 `80ac461a76dd3b60e5fbb4329791abec4a5d788c62f9f7d144781fb15cbce880`): `:1303` declares `enabled=1, stage=6`; `:1305-1306` parses `pong_touch` and `k60_touch_se`; `:1307` returns when disabled or zero; `:1308-1311` rejects `stage > 7` with the exact log line; `:1312-1315` requires `configuration()`; `:1316-1323` validates delay/SPI/flip/RCG.
- Stage behavior in the same file: `:1216-1219` stage 1 maps pins only; `:1228-1231` stage 2 stops after GPIO/AVDD; `:1232-1237` stages 3/4 stop after clocks; `:1245-1248` stages 5 and 7 identify the chip but publish no input device and do not poll; `:1249-1295` only the remaining path (stage 6) resets, probes, applies config, publishes the device, and enters the polling loop.
- `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch:1325-1329` carries the same parse/reject logic; the patch text still documents stage 5 = ID, 6 = input, 7 = GPIO ID.

Consequence: with 19, `pong_goodix_init()` returns at the `stage > 7` guard before the touch thread is created. No `goodix:` line, no POLL heartbeat, and no 0x10308 read can appear. That is precisely the observed log, so this capture says nothing about the chip's condition and cannot support "Goodix is dead/hung."

Provenance of the bad value:

- At `aca503f`, `board.toml:179` read `"k60_touch_se=19"`. `git blame` attributes the 6→19 change to `51fbd9a305623c4b28cc4ebeeff8fec06299d11a` (2026-11-12 10:06:25), a commit about gate rules whose message does not mention touch.
- The build logs record the assembled argument list at `\\wsl.localhost\Ubuntu-24.04\tmp\pl.log:16` and `tmp\pl2.log:16`, both ending `... k60_touch_se=19 ...`. The value came from `board.toml`, not from a driver default.
- `docs/research/UPSTREAM-TRIAGE.toml:147` is internally inconsistent with that history: it claims line 179 already held 6 and that the value was "changed back to 19" after a hang test. The repository and build logs show the opposite (19 was present, and 19 is the value that disables touch). This line should not be used as evidence.
- `8ffa043` corrected `board.toml:179` to 6 and added `docs/engineering/PITFALLS.md:3872-3886` (P-156) plus range enforcement in `scripts/check-boot-args.py:78-114`, which parses the documented range column. At the audit cut, `board.toml:179` is 6 and `git diff` is clean.

Residual driver deviations from `docs/engineering/TOUCH-STATEMACHINE.md`, reported only, not fixed and not part of this audit's conclusion:

- `pong_goodix.c:940-951` writes `GOODIX_SPI_MODE_REG` (0xC900) on every `touch_reset()` (`:953-961`). `TOUCH-STATEMACHINE.md:474` says not to write 0xC900 on Berlin-D, citing `brl_hw.c:59-61`.
- `pong_goodix.c` has no `config_id` equality skip; `TOUCH-STATEMACHINE.md:475` recommends adding one (`core.c:2081-2085`).
- The old CFG-RESET is already absent from `goodix_apply_config()`; `TOUCH-STATEMACHINE.md:469` still lists its removal as a requirement. The current apply path ends with the 100 ms settle, matching the documented `brl_send_config()` behavior (`TOUCH-STATEMACHINE.md:432`, `:12`).
- The sole touch success criterion remains `0x10308` first byte non-`0x00` (`TOUCH-STATEMACHINE.md:480`), mirrored by `docs/research/EIGHT-STEPS.toml:73-75` (`reports`/`touches` grow and the first byte is non-zero; failure is first byte `0x00` or three zero-report heartbeats). These captures do not test that criterion at all because stage 19 never reached the probe.

## What would change these conclusions

- A `boot-uuid.img` capture that is image-bound, longer than the 90 s budget, with `panicMarker`/`resetMarker` set before Data mount would reopen the battery question. The existing 91,673-byte capture contradicts that outcome.
- Evidence that `build-xnu-4k-baseline.sh` consumed `XNU_K60_PHYSICAL_BATTERY` or force-loaded `libK60PhysicalBattery.a` in the 18:43 build would invalidate the "inert" finding; the current script and symbol table show neither.
- A boot with `k60_touch_se` in 1..7 that still shows no `Pong touch: ...` probe line or no polling would move the diagnosis from "boot arg disabled it" to the driver/chip path. That experiment has not been run in this audit.
- A source revision that accepts stage 19 would invalidate the range finding; `pong_goodix.c:1308`, the patch, and `BOOT-ARGS.md:23` all agree on 7 as the maximum.

## Limits

The 51a889 kernel binary was overwritten by the 18:56 build; its absence from the linked kernel is established from the unchanged build script and the sibling 379e kernel's object list, not by re-extracting the 18:43 Mach-O from the boot image. The two console logs are 90 s windows and contain some interleaved launchd/kernel lines (for example `184616:675` and `:678-679`), so only the unambiguous anchors above were used. No device was touched, so "normal boot" here means Data mount rw, launchd exec, SpringBoard spawn, and a live heartbeat, not a fully usable UI.
