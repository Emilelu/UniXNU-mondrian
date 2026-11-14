# Handoff — K60 Bluetooth line (state at 2026-11-14)

This file is the single-page handoff from the `feat/bt-research` line to the integrated line.
The branch adds `docs/research/bt/*` and `patches/bt/*`; the only edits outside that scope are the four
`patches/xnu/05xx` twins wired at `patches/xnu/series:205-208` (see §3).

Branch: `feat/bt-research` (worktree `E:/hackios/k60-bt`), base `f119a80` (= `main` at the time
of writing). Commits: `3fb11e5` (research), `abc6964` (probe patch), `f71ef4f` (S1 spec),
`8bc2f7f` (static verification + baseline gate state), `56ff95c` (probe extension),
`86a7550` (deep dive).

## 1. What is delivered

| artefact | content | status |
|---|---|---|
| `docs/research/bt/RESEARCH.md` | ①同型/②官方/③反编译/④广域 evidence tables, the seven answers (UART SE20 0x894000, IRQ 587 + GPIO79 wake IRQ 208, 3.0 Mbaud, H4 + IBS wake byte 0xFD, CTS/RTS/TX/RX = 76/77/78/79, BT_EN 81, SW_CTRL 82, XO 204), firmware expectations, WiFi/BT single-chip boundary, S1–S6 plan | done |
| `docs/research/bt/06-DEEP-DIVE.md` | ⑥ line-by-line review of `patches/xnu/0500`'s `bsd/dev/qbt_k60.c` (1,249 lines, sha256 `8451c870…`): 11 verified items V1–V11, 12 deviations F1–F12 (F11/F12 added 2026-11-14: the SE20 RCG root is never enabled; no CBCR readiness poll) | done |
| `docs/research/bt/S1-PROBE-SPEC.md` | **S1c** read-only probe: 20 s console delay, 36 marks printed *before* each access, nine bisectable steps (`k60bt_step` 1–9), including the three SE20 RCG-root rungs that decide F11; verdict table keyed on "last mark printed", F2/F3 rows, five-rung device ladder | done, statically verified |
| `patches/bt/0001-k60-bt-readonly-probe.patch` = `patches/xnu/0507-k60-bt-readonly-probe.patch` | 2 hunks on `bsd/dev/qbt_k60.c`: `k60_bt_probe(step)` + delayed `k60bt_stage=1` early return. sha256 `05dd342b83d3d035e05495280d9bee9d40624f9732240b7323146964e7b8b2e1` (13,001 B / 280 lines) | **build-wired** (`patches/xnu/series:205`) |
| `docs/research/bt/FIRMWARE.md` | **measured** BT firmware: `/vendor/bt_firmware/image/`, 113 files / 1,063,407 B, `hpbtfw20.tlv` 201,560 B + `hpbtfw21.tlv` 146,068 B + `hpnv20*`/`hpnv21*`, per-file SHA-256, `btqca.c` name selection, staging plan | done (M) |
| `docs/research/bt/S3-SPEC.md` | S3 spec: why bluetoothd cannot see the controller today (device-tree match, MAC, IOService), the sheng `BluetoothProbe.cpp:222-264` port, the `/arm-io` child publish idiom, the seed gap in `board.toml`, and the verdict table keyed on the `K60 BT:` line | done, statically verified |
| `patches/bt/0003-k60-bt-s3-identity-publish.patch` = `patches/xnu/0509-k60-bt-s3-identity-publish.patch` | 5 files (198 ins / 11 del): strong `k60_bt_local_address()` (SecureDT `/chosen/unique-chip-id` + FNV-1a), new `iokit/Kernel/MiniBluetooth.cpp` (164 lines) publishing the `/arm-io/bluetooth` node, both MAC properties and a `bluetooth` IOService, plus `MiniDrivers.h`/`MiniIOSurface.cpp`/`iokit/conf/files` wiring. sha256 `429630d61fcd06554cc8094ca3381ec49d0485f8c8b025d60f7a5fe8c1208edf` (10,265 B / 304 lines) | **build-wired** (`patches/xnu/series:207`) |
| `docs/research/bt/S2-SPEC.md` | S2 spec: how `0508` fixes F1 (SMMU stream 0x483 bypass + contiguous DMA), F11 (SE20 RCG root enable), F3 (0xc40/0xd40 RESET_DONE instead of the undefined 0xe40) and F12 (CBCR halt after the rate write); expected console lines and verdict table | done, statically verified |
| `patches/bt/0002-k60-bt-s2-smmu-rcg-reset.patch` = `patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch` | 6 hunks on `bsd/dev/qbt_k60.c`: `k60_smmu_plan_bank`/`k60_smmu_plan`/`k60_smmu_configure`/`k60_smmu_bypass` + `kmem_alloc_contig`/`pmap_find_phys` DMA path, RCG root enable, reset-done polling. sha256 `c4bf1ded55fe9bd03b7c10943ed41fff47464037c06c893b6dfd0984f02fd4f2` (18,393 B / 391 lines) | **build-wired** (`patches/xnu/series:206`) |
| `docs/research/bt/S4-SPEC.md` | S4 spec: why the firmware must ride the boot image (Data seed absent, no zlib, no `.incbin`, NGPUADD2 has no kernel consumer), the DarwinBoot `GpuAddon` channel with line-level evidence, the container format, the kernel reader, the **Lead-scope build fragments** (`scripts/make-bt-firmware-addon.py` in full, `build-strict.sh` diff, `.gitignore`), the offline verification and the S4a–S4c device ladder | done, offline-verified |
| `patches/bt/0004-k60-bt-firmware-addon.patch` = `patches/xnu/0510-k60-bt-firmware-addon.patch` | 1 file (237 ins / 1 del): NGPUADD2 parser `k60_addon_find()`, kernel snapshot `k60_bt_addon_load()` (SecureDT `chosen/memory-map/GpuAddon` + `phystokv`), `k60_bt_addon_read()`, and `k60_bt_firmware_read()` trying the addon first. sha256 `4d6e3c1a89b60a55cc146294ec4e9abcfac4521aed0d3787da20df5e22218b04` (12,877 B / 291 lines) | **build-wired** (`patches/xnu/series:208`) |
| `patches/bt/README.md`, `patches/bt/series` | explains that the build reads only `patches/xnu/series`; wiring status (option B used, option A kept as an alternative) | done |
| image `bt-s4-20261114b` (`boot.img` `82ff78b4…`, 201,887,744 B) | the first build that contains `0510`: `build-strict.sh` exit 0, `verify-boot-image.py` OK, `kernel_built 9e8ae410…`, `payload 570f61e9…`, `adt 079cf3c7…`; `strings kernel.macho` shows `NGPUADD2` / `loaded bytes records` / `no GpuAddon property`. **No `--gpu-addon`** (Lead scope), so the addon cell is absent and this image is the negative control for S4 | built, not booted |
| image `bt-s4a-20261114c` (`boot.img` `f886223a…`, 201,887,744 B) | the first **positive** S4 image: built with `--gpu-addon out/pong-bt-firmware.bin` (sha256 `febdc20d…`) through a scratch copy of `build-strict.sh` at `/tmp/bt-s4a/scripts/` (= repo file + `bt-lead-0002.patch`), `K60_OUT=/opt/k60/trees/k60build/bt-out-s1c`, `--kernel-arg k60bt=1` → 583 B / 30 args. `build-strict.sh` exit 0, `verify-boot-image.py` OK, `check-image-args.py` OK. `kernel_built ba805e4c…`, `payload 1e62d481…`, `payload_kernel a92d7b1e…`, `adt c304361e…`; payload FAT carries `kernel.macho.gpuaddon` 1,027,584 B (byte-identical to the packer output) and the ADT holds exactly one `GpuAddon` cell. See `S4-SPEC.md` §6.2 | built, not booted |
| images `bt-s1c-a1…a5-20261114c` (`boot.img` `6848bf1d…`, `2d969773…`, `ac55aa27…`, `7171f4dd…`, `87832493…`) | the S1c ladder rebuilt **in an isolated output tree** at **596 B / 31 arguments** each (`k60bt=1 k60bt_step=1/4/5/7/9`), `check-image-args.py` OK on all five, `verify-boot-image.py` OK on all five; the five kernels are byte-identical except Mach-O `LC_UUID` / build timestamp / `_PrelinkKCID` (45–48 bytes), so only the command line varies — see `S1-PROBE-SPEC.md` §4.1 and §4.3. Built, not booted. The earlier `…-20261114b` five are **void**: built in the shared `out-baseline` tree, their kernel differs by 9,070,788 bytes because other lines' patches were compiled in (§4.3). |
| image `bt-s2-20261114b` (`boot.img` `c3ea7b60…`) | control boot on the returned board: 224,240 B console, `panicMarker=null`, normal `k60_autoreset` reset, zero `K60 BT`/`addon:` lines. `record-boot.py` recorded series `f1c22d7d05bb1b17` (227 patches) | booted, healthy |

## 2. Why S1 first

Two independent reproductions (`docs/research/GENI-ACCESS-PRECONDITIONS.md`) show that the **first
GENI register access** on this device produced a 0-byte console: touch on QUP0 SE4 (0x990000) and
audio I2C on 0x880000. BT sits in the same QUPV3_2 wrapper. So the only question S1 answers is
"can SE20 be touched at all". S1 maps GCC/SE20/wrapper, takes the five QUPV3_2 votes, and performs
nine **loads**. No pin mux, no BT_EN pulse, no DMA, no interrupt.

Secondary purpose: decide the deviation that would otherwise be debugged as a mysterious power
failure — `k60_stop_engine()` polling the undefined offset 0xe40 (F3, returns `-ETIMEDOUT`
deterministically if it reads non-zero). (F2, the `G_MANUAL_RFR` value, was resolved offline on
2026-11-14: `0x80000001` is the official sheng backend's own write, `BluetoothProbe.cpp:202`.)

**Measured result of the first attempt (S1a, 2026-11-14 04:51):** image `bt-s1-20261114b`
(`boot_img 2fef132a…`) booted with `k60bt=1 k60bt_stage=1 k60bt_warm=1`, fastboot accepted it, and
then **zero console bytes** appeared: `capture.json` state `port-not-observed`, `bytes=0`,
`panicMarker=null`. Afterwards the board answers neither `adb` nor `fastboot` and exposes no USB
device at all — the "USB-down hang, physical power cycle only" state of `scripts/k60-device.sh`.
The same kernel without `k60bt` (`bt-s1-20261114a`, `boot_img 7b6b02fc…`) reached userland
normally.

**Root cause, found 2026-11-14 11:00 (Lead) and re-verified locally:** that image's kernel command
line is **610 bytes**, over DarwinBoot's **607-byte** ceiling
(`uefi-mondrian/Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h:8` `DARWIN_BOOT_LINE_LENGTH 608`,
`DarwinBoot.c:678-684` returns `EFI_BAD_BUFFER_SIZE`). The firmware refused the line and the kernel
was never entered, so the zero-byte console is a **boot-image argument defect, not a register
access fault**: "the first GENI access kills the machine" is neither confirmed nor refuted.
The three args were `k60bt=1 k60bt_stage=1 k60bt_warm=1` = 35 B stacked on the 29-arg / 575 B board
contract. `k60bt_stage=1` is redundant anyway (`bsd/dev/qbt_k60.c:1844-1846` defaults `k60.stage` to
1) and `k60bt_warm` only selects a warm-boot branch, so the ladder uses `k60bt=1 k60bt_step=N`
= **596 B**. Byte budget and the per-image audit live in `docs/research/bt/S1-PROBE-SPEC.md` §4.2.

## 3. Lead actions, in order

1. **Done already:** `feat/bt-research` was rebased onto the integrated line `63eb384` (feat/pmic-rail)
   and the probe was wired as `patches/xnu/0507-k60-bt-readonly-probe.patch` + `patches/xnu/series:205`
   (option B), then `sync-device-input.py` was run so the build mirror matches. On the rebased branch
   `eight-step-gate.py --build` reports `硬件项: 5 个`, `通过 30 项检查`, `✅ 八步流程通过`.
2. **PHYSICAL POWER CYCLE FIRST.** The S1a boot (`k60bt=1`) hung the board before the USB gadget
   enumerated: no `adb`, no `fastboot`, no USB device. `scripts/k60-device.sh` documents this as the
   one state no script can leave. Hold power until it is off, then boot it back to Android/fastboot.
3. **Register the BT hardware item** so the gate can see ①–⑥ (see §4 for the exact TOML).
4. **S3 身份与发布已就位**：`patches/xnu/0509-k60-bt-s3-identity-publish.patch` 在 `series:207`（`0508` 之后、`0503` 之前），把弱 `k60_bt_local_address()` 换成读 `/chosen/unique-chip-id` 的强定义，并在 `native_pong_ui_services_start()` 里发布 `/arm-io/bluetooth` 节点、两处 MAC 与 `bluetooth` IOService（全部 `k60bt=1` 门控）。**镜像已构建两个**：`bt-s3-20261114a`（`k60bt_stage=1`，只跑探针 s1 + 发布钩子，boot.img sha256 `4b865f94deeb9427004f8ca84c7b55516462cbdfc1ef9330c50dacda25985c14`，kernel `e3965c37…2ed5`，adt `7ad7f4a6…12f7`）与 `bt-s3-20261114b`（`k60bt_stage=2`，真实路径：上电 → 取 MAC → `qbt_boot()`，boot.img `fb2b9bb3ea622f432253ba82a2e2c18eb2f6e5b0e380915b6110cde56218d6d5`，kernel `7aab2f21…cdf1`，adt `b623d7c3…eb8e`）；两者 series 226 / `97da5eb2…665a`，`verify-boot-image: OK`，`MiniBluetooth.cpo` 已编译、kernel.macho 里能 `strings` 到三条 `K60 BT:` 串。
构建时用 `UNIXNU_UNIQUE_CHIP_ID=4B36305400000001` 绕过了种子缺失：ADT 实测 `/chosen/unique-chip-id=0x4B36305400000001`、`chip-id=0x8015`，所以这版会打印 `K60 BT: published local address 02:…` 而不是 `no platform identity`。**把种子固化下来仍是 Lead 待办**：给 `[payload."adt"]` 加 `"unique_chip_id" = "required"` 并在每次构建设 `UNIXNU_UNIQUE_CHIP_ID=<hex>`（`build-strict.sh` 继承调用者环境，`payload.py:160-163` 会读它），或给 `build-strict.sh` 加 `--unique-chip-id` 转发。种子定下后**不要改**（否则 MAC 变化、配对作废）。
**ADT 里仍没有 `/arm-io/bluetooth` 节点**（`/arm-io` 子节点只有 intc/pong-audio/pong-buttons/pong-touch/ufshc），节点目前由补丁在 IORegistry 里建；要让 DT 二进制里也有，加 `[adt.arm-io.bluetooth.string]` + `[adt.arm-io.bluetooth.u32]`（TOML 见 `S3-SPEC.md` §4 第 3 条）。详见 `S3-SPEC.md` §4/§4.1。
5. **S2 前置修复已就位**：`patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch` 在 `series:206`（`0507` 之后、`0503` 之前），修 F1/F11/F3/F12，`git apply --check` 与 `clang -fsyntax-only` 均通过；下一个镜像会自动带上它，不需要额外动作。
6. Build (**done — all five rung images `bt-s1c-a1…a5-20261114c` are built and verified at 596 B each**, see the table in `S1-PROBE-SPEC.md` §4.1; rebuild only if the probe changes again). **Always build with a line-private output tree**: `K60_OUT=/opt/k60/trees/k60build/bt-out-s1c K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device` — the default `out-baseline` is shared and other lines' patches end up in the kernel (§4.3): `python3 scripts/sync-device-input.py` → `python3 scripts/check-rules.py` →
   `bash scripts/build-strict.sh <tag> --fd <fd> --kernel-arg k60bt=1 --kernel-arg k60bt_step=<N>`
   → `python3 scripts/verify-boot-image.py --manifest <artifact>/build-manifest.json`
   → `python3 scripts/check-image-args.py --image <artifact>/boot.img --board board.toml` (must print OK;
   596 B of the 607 B ceiling, see `S1-PROBE-SPEC.md` §4.2). **Never** add `k60bt_stage`/`k60bt_warm`
   to the ladder: together they push the line to 610 B and the firmware refuses to boot the kernel at all.
   Expect the payload TOML to end with `k60bt=1 k60bt_step=N` (check with
   `mtype -i <payload.img> ::/EFI/UniXNU/unixnu.toml`).
7. Device: attach the CDC-ACM capture **before** any `fastboot boot` (AGENTS.md iron rule 8: console
   VID_1209&PID_0001, usbser.sys, port only from `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM\Device\USBSER000`,
   DTR raised), then boot the rungs in order, adding risk each time (S1-PROBE-SPEC.md §4/§4.1). Each rung
   is its own image because `k60bt_*` lives in the payload command line, not in the kernel:
   `bt-s1c-a1-20261114c` (step 1, maps only, cannot hang) → `bt-s1c-a2-20261114c` (step 4, GCC only) →
   `bt-s1c-a3-20261114c` (step 5, first RCG read) → `bt-s1c-a4-20261114c` (step 7, first RCG writes) →
   `bt-s1c-a5-20261114c` (step 9, first GENI read). All five carry `k60bt=1 k60bt_step=N` only (596 B).
   **Do not use the `…-20261114b` five** — they were built in the shared `out-baseline` tree and their kernels
   contain other lines' patches (9,070,788-byte difference, `S1-PROBE-SPEC.md` §4.3).
   Stop the ladder wherever the board dies. Record with `python3 scripts/record-boot.py --image … --log <dir>/console.log`.
   Judge only `capture.json` `verdict`/`panicMarker` (never logstat.py panic counts).
   Read the verdict off the **last `probe: …` line** in the console (S1-PROBE-SPEC.md §5); if it stops
   at an `sX` step, re-boot once with `k60bt_step` one lower to prove that access is the fatal one.
8. Feed the result back into `docs/research/GENI-ACCESS-PRECONDITIONS.md` (the touch and audio lines
   share this precondition), `06-DEEP-DIVE.md` F2/F3 and `RESEARCH.md` §5.4.
9. **S4 构建侧要合并三处**（内核侧已就位：`patches/xnu/0510` 在 `series:208`，对缺失单元静默降级，所以现在合并也不会改变任何现有镜像）。三处补丁已用临时副本**端到端验证过**：`bt-s4a-20261114c` 就是经 `/tmp/bt-s4a/scripts/build-strict.sh` 构建出来的，可以直接合：
   (a) 新文件 `scripts/make-bt-firmware-addon.py`——全文与实测输出见 `S4-SPEC.md` §5.2；
   (b) `scripts/build-strict.sh` 增加 `--gpu-addon <file>` 并转发给 `unixnu build payload`，同时写进 manifest 的 `components`——精确 diff 见 `S4-SPEC.md` §5.3；
   (c) `.gitignore` 给 `firmware/bluetooth/manifest.json` 开否定规则（只有 bytes+sha256，可以入库）——见 `S4-SPEC.md` §5.4。
   固件源是 `E:/k60-work/firmware/qca6490-bt`（113 文件 / 1,063,407 B），白名单筛出 106 条 / 1,022,742 B，容器 1,027,584 B。
10. **命令行门禁要补两个参数名（Lead scope）**：`scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS`
    （该文件 :44-48）目前是 `… "k60bt", "k60bt_stage", "k60bt_warm", …`，没有本阶梯用的 `k60bt_step`
    与 `k60bt_delay`。所以 `bt-s1c-a1…a5-20261114c` 这五份**长度合规（596 B）但会被该门禁拒**
    （实测：`image-arg-audit: REFUSED — argument k60bt_step is not in board.toml kernel_args and is not a
    declared addition`）。把两个名字加进 `ALLOWED_ADDITIONS` 后，五份全部 `OK (31 arguments, 596 bytes)`。
    已用一份只加这两个名字的 gate 副本（`/tmp/gateiso/g.py`）实测：`bt-s1c-a1…a5-20261114c` 五份全部
    `image-arg-audit: OK (31 arguments, 596 bytes)`。
    同一处注释要求「每个名字都要写进 `docs/engineering/BOOT-ARGS.md`」，而该文件目前**没有任何 `k60bt` 条目**
    （`grep -n k60bt docs/engineering/BOOT-ARGS.md` → 空），五个 `k60bt*` 名字需要一起补上文档。
11. **把 `origin/main` 合进 `feat/bt-research`（Lead scope）**：main 比本分支多 4 个提交
    （`90d8271` merge feat/gate-fixes、`3f55e32`、`2050064`、`7fa8110`，含 `scripts/check-image-args.py`）。
    本地 `git merge origin/main` 在 `docs/engineering/PITFALLS.md`、`docs/engineering/RULES.toml`、
    `docs/engineering/TREE-OWNERS.toml`（add/add）与 `scripts/sync-device-input.py` 上冲突——这四处都是
    Lead/共享范围，本线不自行解冲突（已 `git merge --abort`，HEAD 保持 `9beffa5`）。
12. **构建输出树必须按线隔离（Lead scope，脚本改动）**：`scripts/build-strict.sh:40` 的 `OUT` 默认是
    `$BUILD/out-baseline`，而该目录被所有线共用。2026-11-14 12:24 的 `xnu-inputs.json` 记录 232 个补丁
    （本线 227 个 + 别线的 `0405/0406/0407` 与六个 `zzzz…-pong-touch-*`），本线 `0507–0510` 一个都没进树，
    于是同一次阶梯的五个内核在两份输出树之间差了 9,070,788 字节（`S1-PROBE-SPEC.md` §4.3）。
    建议：(a) `build-strict.sh` 要求显式 `K60_OUT`（或按 tag 派生），并把它写进 manifest；
    (b) `scripts/check-build-applied.py:52-59` 在没有 stamp 时不要回退去读全项目最新的 `kernel.log`——
    那会把别线的构建当成本线的记录（本次 P-165/P-166 就是这样红的）。本线现用
    `K60_OUT=/opt/k60/trees/k60build/bt-out-s1c`、`K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device`。

## 4. Gate snippets (outside this line's write scope)

`docs/research/EIGHT-STEPS.toml` — add next to `[hardware.touch]`:

```toml
[hardware.bluetooth]
status = "research"
name = "QCA6490 HCI over QUPV3_2 SE20"

[hardware.bluetooth.step.same_model]
done = true
evidence = "docs/research/bt/RESEARCH.md §1: live FDT mondrian.dts:1270-1295 bt_qca6490, :11041 qup_uart@894000, :10707-10720 wrapper, :4124-4227 SE20 pins; vendor btpower.c:193-219 / hci_qca.c:1751-1764"

[hardware.bluetooth.step.official]
done = true
evidence = "docs/research/bt/RESEARCH.md §2: UniXNU components.toml:494-508 QcaBluetooth; UniXNU/docs/porting/bluetooth.md:22-142"

[hardware.bluetooth.step.decompile]
done = true
evidence = "docs/research/bt/RESEARCH.md §3: 20G81 kernelcache has no IOBluetooth kext family, only com.apple.uart.sk.%s + BlueTool + BTReset; transport must reach userland bluetoothd"

[hardware.bluetooth.step.wide]
done = true
evidence = "docs/research/bt/RESEARCH.md §4: UniXNU-sheng has QcaBluetooth; pong has none (board_services18.py:84-89 blocks bluetoothd); phk110-port has a 143-line diagnostic only"

[hardware.bluetooth.step.plan]
done = true
evidence = "docs/research/bt/RESEARCH.md §5 S1-S6 + §6 acceptance criteria"

[hardware.bluetooth.step.deep]
done = true
evidence = "docs/research/bt/06-DEEP-DIVE.md: V1-V11 verified, F1-F3 block S2 until S1 returns the register reads"

[hardware.bluetooth.step.verify]
done = false
evidence = "S1 not yet run on device"
local_verified = false
```

`docs/research/SOURCES.toml` — add:

```toml
[subsystem.bluetooth]
required = [
  "docs/research/bt/RESEARCH.md",
  "docs/research/bt/06-DEEP-DIVE.md",
  "docs/research/bt/S1-PROBE-SPEC.md",
  "docs/research/bt/FIRMWARE.md",
  "docs/research/bt/evidence/k60-android-btpower.c",
  "docs/research/bt/evidence/k60-android-hci_qca.c",
  "docs/research/bt/evidence/linux-geni-se-v6.6.h",
  "docs/research/bt/evidence/linux-qcom-geni-se-v6.6.c",
  "docs/research/bt/evidence/linux-qcom_geni_serial-v6.6.c",
]
```

(Each entry needs `examined = "..."` and `finding = "..."` fields with a checkable reference —
copy the style of the neighbouring subsystems. The evidence files live under `E:/k60-work/docs/research/bt/evidence/`
and are resolvable by `research-gate.py` through its `/mnt/e/k60-work` root.)

## 5. Still blocked from this line

- **Firmware — RESOLVED 2026-11-14** (no longer blocked): a read-only Android session located the
  BT files in `/vendor/bt_firmware/image/` (**not** `firmware_mnt/image/qca6490`, which only holds the
  WiFi `amss*.bin`/`Data*.msc` and 42 `bd_*.elf` board-data files). **113 files / 1,063,407 B** were
  pulled to `E:/k60-work/firmware/qca6490-bt/` and hashed. Rampatch is `hpbtfw20.tlv` (201,560 B) and
  `hpbtfw21.tlv` (146,068 B); NVM is `hpnv20*` (20 files) + `hpnv21*` (90 files). The old
  `htbtfw21.tlv`/`htnv21.bin` guess is **void** — the device set uses the `hp*` fallback names, which is
  exactly what `k60_firmware_get()`'s alias path (0500:924-960) covers. Full table + hashes + staging
  plan: `docs/research/bt/FIRMWARE.md`. Remaining is Lead write scope: `firmware/bluetooth/manifest.json`,
  `scripts/stage-bluetooth-firmware.py` (K60 regex `(wcn)?hp(btfw|nv)…`, allow `g` and `.bXXXX`), and
  `board.toml [payload.runtime] bluetooth_tool/bluetooth_target="ios20"`. Do **not** commit the vendor
  firmware into the repo (sheng pins an external firmware repo by hash instead).
- **Userland**: `BlueTool`/`QcaBTType0.dylib`/`bluetoothd` patching for 20G81 needs the iOS SDK
  on the LAN Mac (per AGENT-bt.txt), and the adapter is locked to the 24A446 hash in sheng's
  `native-ios27.md` — 20G81 patch sites must be re-located.
- **SMMU**: F1 — the wrapper declares `iommus = <&apps_smmu 0x483 0>` and the backend uses the
  virtual pointer as a DMA address. S2 must add a bypass mapping or a physically contiguous block
  before any DMA is armed.

## 6. One-command state check

```bash
cd /mnt/e/hackios/k60-bt
git log --oneline -6
git diff --stat f119a80 HEAD -- docs/research/bt patches/bt
sha256sum patches/bt/0001-k60-bt-readonly-probe.patch
```

## 7. S4 hand-over: five Lead-scope patches (all `git apply --check` clean at `b29726d`)

Every patch below lives outside this line's write scope (`scripts/`, `.gitignore`) and is delivered as a
file, not committed here. Paths are on this host; `sha256` is the first 16 hex digits of the patch file.

| patch | bytes | what it does | sha256 |
| --- | --- | --- | --- |
| `/mnt/e/k60-work/scratch/bt-s4/lead/bt-lead-0001.patch` | 4,858 | new `scripts/make-bt-firmware-addon.py`: packs the whitelisted QCA set into the `NGPUADD2` container DarwinBoot already carries (`qca/` prefix, uncompressed records, manifest-checked bytes+sha256) | `9118fe9e79f85abf` |
| `…/bt-lead-0002.patch` | 2,842 | `scripts/build-strict.sh`: `--gpu-addon <file>` forwarding into the payload step, its existence check, a `gpu addon` log line, and `gpu_addon`/`gpu_addon_path` in the manifest | `765a5271139125e8` |
| `…/bt-lead-0003.patch` | 424 | `.gitignore`: keep `/firmware/` ignored but track `firmware/bluetooth/manifest.json` | `0c4d3b8c555f3836` |
| `…/bt-lead-0004.patch` | 1,687 | `scripts/check-kernel-archives.py`: while `K60_BUILD_IN_PROGRESS=1`, a force-loaded archive whose symbol is not in the kernel **yet** is a warning, not a failure (P-190 is only decidable after the link) | `f2c37e69f958e6bb` |
| `…/bt-lead-0005.patch` | 5,941 | `scripts/tests/test-series-source.py`: scope the manifest comparison to this checkout and compare each manifest to the series blob at **its own** recorded head (P-194) | `01b744f4ac6bd96f` |

### Why 0004 and 0005 are needed at all

The merge of `origin/main` (`b29726d`) brought two gates that no single line can satisfy, so every
line is red before it builds:

- **P-190** — `check-kernel-archives.py` demands that a configured force-load archive's symbol is already
  in `kernel.macho`. Before a build the kernel is by definition older than the archive that build is
  about to link, so the gate refuses the very build that would satisfy it. `build-strict.sh:121-131`
  builds `build/k60-battery/libK60PhysicalBattery.a` and `:250` re-runs the gate after the link, which
  is exactly where the question is decidable. The patch reuses the `K60_BUILD_IN_PROGRESS` idiom
  `check-build-applied.py:42-44` already established for P-165.
- **P-194** — `test-series-source.py` compared the **newest** `build-manifest.json` on disk to this
  checkout's `patches/xnu/series`. Every line builds in its own worktree, so the newest manifest belongs
  to another line. Measured 2026-11-14 20:0x: newest was `touch-20261114a` (223 patches) while five
  lines were building 227. Worse, after a merge the working-tree series legitimately differs from what
  an older manifest recorded. The patch keeps the substantive assertion — *the fingerprint a manifest
  recorded must equal the series that build actually applied* — and reads that series with
  `git show <head>:patches/xnu/series`.

### Validation (both patches installed, then reverted; tree left clean, `porcelain=0`)

```
P-190  ✅ kernel archives: 4 enabled archive(s) all present in kernel.macho
P-194  ✅ TESTS OK 11 cases (0 failure(s))
```

With `K60_BUILD_IN_PROGRESS=1` the archive gate prints
`warn: CONFIG_XNU_K60_PHYSICAL_BATTERY=y but build/k60-battery/libK60PhysicalBattery.a is not in kernel.macho yet; this build links it (P-190)`
and returns 0; **without** the variable it still returns 1, so the exemption exists only inside a build.
P-194 goes from 3 FAILs to 11 PASSes, and every one of this line's 24 manifests was independently checked
to satisfy `recorded sha256 == sha256(git show <head>:patches/xnu/series)` (all 24 matched).

The only reds left after installing both patches are the "tracked files modified but not committed"
family (`hard-5`, `hard-10`, `hard-11`, `iron-5`) — they describe the two uncommitted patch files
themselves and disappear once the Lead commits them.

### Still needed from the Lead before a positive S4 image

1. Merge 0001–0003 and rebuild `bt-s4a-20261114c` with `--gpu-addon out/pong-bt-firmware.bin`; that image
   prints `addon: loaded bytes records 1027584 106` (S4a) and `addon: serving 201560 0` (S4b).
2. Merge 0004–0005 so the registry stops refusing every line's build.
3. `scripts/check-image-args.py`: add `k60bt_step` and `k60bt_delay` to `ALLOWED_ADDITIONS`, and document
   all five `k60bt_*` names in `docs/engineering/BOOT-ARGS.md` (it currently has none). Until then the
   ladder images cannot pass the gate even though they fit the 607-byte ceiling at 596 bytes.
4. `docs/research/EIGHT-STEPS.toml`: add the `[hardware.bluetooth]` block from §4 above — the BT line has
   no ledger entry at all, so `K60_EIGHT_STEP_ITEMS=bluetooth` is rejected by `eight-step-gate.py`.

