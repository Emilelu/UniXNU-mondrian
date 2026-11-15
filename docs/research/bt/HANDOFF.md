# Handoff — K60 Bluetooth line (state at 2026-11-15)

This file is the single-page handoff from the `feat/bt-research` line to the integrated line.
The branch adds `docs/research/bt/*` and `patches/bt/*`; the only edits outside that scope are the five
`patches/xnu/05xx` twins wired at `patches/xnu/series:205-209` (see §3), plus the two `k60bt*` rows of
`docs/engineering/BOOT-ARGS.md` this line owns.

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
| `patches/bt/0003-k60-bt-s3-identity-publish.patch` = `patches/xnu/0509-k60-bt-s3-identity-publish.patch` | 5 files (234 ins / 11 del): strong `k60_bt_local_address()` (SecureDT `/chosen/unique-chip-id` + FNV-1a), new `iokit/Kernel/MiniBluetooth.cpp` (179 lines) publishing the `/arm-io/bluetooth` node, both MAC properties and a `bluetooth` IOService, plus `MiniDrivers.h`/`MiniIOSurface.cpp`/`iokit/conf/files` wiring. sha256 `6d92dfe3bae1d96e1974a40a46e61ac9bedfb7b3a56276d0e2f085c3f678a584` (10,836 B / 319 lines) — 2026-11-15 OSData fix: 三属性与 radio `device_type` 改 OSData 发布（backboardd `getBytes:range:` 根因），宿主侧断言 `scripts/tests/test-k60-bt-0509-properties.py` | **build-wired** (`patches/xnu/series:207`) |
| `docs/research/bt/S2-SPEC.md` | S2 spec: how `0508` fixes F1 (SMMU stream 0x483 bypass + contiguous DMA), F11 (SE20 RCG root enable), F3 (0xc40/0xd40 RESET_DONE instead of the undefined 0xe40) and F12 (CBCR halt after the rate write); expected console lines and verdict table | done, statically verified |
| `patches/bt/0002-k60-bt-s2-smmu-rcg-reset.patch` = `patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch` | 6 hunks on `bsd/dev/qbt_k60.c`: `k60_smmu_plan_bank`/`k60_smmu_plan`/`k60_smmu_configure`/`k60_smmu_bypass` + `kmem_alloc_contig`/`pmap_find_phys` DMA path, RCG root enable, reset-done polling. sha256 `c4bf1ded55fe9bd03b7c10943ed41fff47464037c06c893b6dfd0984f02fd4f2` (18,393 B / 391 lines) | **build-wired** (`patches/xnu/series:206`) |
| `docs/research/bt/S4-SPEC.md` | S4 spec: why the firmware must ride the boot image (Data seed absent, no zlib, no `.incbin`, NGPUADD2 has no kernel consumer), the DarwinBoot `GpuAddon` channel with line-level evidence, the container format, the kernel reader, the **Lead-scope build fragments** (`scripts/make-bt-firmware-addon.py` in full, `build-strict.sh` diff, `.gitignore`), the offline verification and the S4a–S4c device ladder | done, offline-verified |
| `patches/bt/0004-k60-bt-firmware-addon.patch` = `patches/xnu/0510-k60-bt-firmware-addon.patch` | **rewritten 2026-11-15 for P-197**: 2 files (289 ins / 1 del): NGPUADD2 parser `k60_addon_find()`, `k60_bt_addon_load_blob()` reading the linked `k60_bt_blob` / `k60_bt_blob_len` (the new primary carrier), the old SecureDT `chosen/memory-map/GpuAddon` path kept as fallback, `k60_bt_addon_read()`, and `k60_bt_firmware_read()` trying the addon first; `osfmk/conf/files.arm64` gains `osfmk/arm64/k60_bt_blob.s` **after `lz4_encode_arm64.s`**（2026-11-16 挪位：原插在 `WKdmCompress_4k.s` 之后会顶掉 `0620` 的上下文，见 item 18）. sha256 `3309d123624bf4461a5ce4e6e197e613546af51ebc894967ad8084a21f7eaa87` (15,718 B) | **build-wired** (`patches/xnu/series:208`) |
| `patches/bt/0005-k60-bt-s4-unblock.patch` = `patches/xnu/0511-k60-bt-s4-unblock.patch` | **2026-11-15, S4 起飞前的三条代码阻断 + 一条日志判据（改行为，不加任何启动参数）**: 2 files (34 ins / 3 del): `k60_worker()` 的 addon 门闩改为「已链入 blob 即放行」（`k60_bt_blob_len > 0`，先判地址再解引用）、`k60_bt_power_on()` 冷启动不再直接 `-EOPNOTSUPP` 而改打 `power: cold boot, rails not voted (k60bt_warm=0)` 后继续、`k60.stage` 默认改为 0（完整阶梯；探针显式 `k60bt_stage=1`/任一 `k60bt_step=N` 才进）、`btqca.c:764` 之后补一条 level-1 的 `QCA controller version 0x…`。sha256 `07b862dd7122432bea04bbfd9fe1975d9abb43abf13b83a412079ce4ec03f39a` (3,718 B) | **build-wired** (`patches/xnu/series:209`) |
| `scripts/gen-k60-bt-blob.py`, `scripts/tests/test-k60-bt-blob.py` | the blob generator (`.incbin` + length constant, one-byte stub when no container) and its host test (9 fixtures, including the P-196 "length forgot the padding" case); `scripts/build-xnu-4k-baseline.sh:311-324` runs the generator inside the xnu build, `scripts/build-strict.sh` gained `--bt-blob` | done (`ccd4dfc`) |
| `patches/bt/README.md`, `patches/bt/series` | explains that the build reads only `patches/xnu/series`; wiring status (option B used, option A kept as an alternative) | done |
| image `bt-s4-20261114b` (`boot.img` `82ff78b4…`, 201,887,744 B) | the first build that contains `0510`: `build-strict.sh` exit 0, `verify-boot-image.py` OK, `kernel_built 9e8ae410…`, `payload 570f61e9…`, `adt 079cf3c7…`; `strings kernel.macho` shows `NGPUADD2` / `loaded bytes records` / `no GpuAddon property`. **No `--gpu-addon`** (Lead scope), so the addon cell is absent. It was the negative control until P-201; the controlled one is now `bt-s4c-20261115a` (same HEAD as the positive) | built, not booted |
| image `bt-s4b-20261115b` (`boot.img` `2402def9…`, 201,887,744 B) | **the positive S4 image to fly** (P-197 carrier, controlled pair): built with main's own `build-strict.sh --bt-blob out/pong-bt-firmware.bin` (sha256 `febdc20d…`) and `--kernel-arg k60bt=1` (583 B / 30 args); `kernel_built e8e0f13b…` (106,541,056 B), `payload 36c7e2c8…`, `payload_kernel 2ed1dc9e…`, `adt 50dfee28…`; `llvm-nm` shows `_k60_bt_blob` @ `fffffff0071b8818` and `_k60_bt_blob_len` @ `fffffff0072b3618` (Δ = 1,027,584), and those bytes in `kernel.macho` hash-equal the packer output. `--gpu-addon` deliberately NOT passed. Same HEAD `68a38f3` and the same 453-entry frozen list as the negative control. See `S4-SPEC.md` §6.5 | built, not booted |
| image `bt-s4c-20261115a` (`boot.img` `535c395a…`, 201,887,744 B) | **the controlled negative control to fly**: the same command as `bt-s4b-20261115b` with `--bt-blob` omitted, so `gen-k60-bt-blob.py` emitted the one-byte stub and `_k60_bt_blob_len` is 0; `kernel_built 7f049b7c…` (105,508,864 B, 1,032,192 B smaller), `payload_kernel f95eee94…`, `payload 0634b28d…`, `adt 25fa7b08…`; `frozen-before.txt` is byte-identical to the positive's (453 lines, `931d391d…08e`). The container is absent from this kernel (`find` = −1). See `S4-SPEC.md` §6.5 | built, not booted |
| image `bt-s4b-20261115a` (`boot.img` `7ee92d51…`) — **superseded by `…b`** | the first P-197 positive build, but its frozen list carried two `scripts/__pycache__/*.pyc` entries that cannot be reproduced (`py_compile` is not deterministic), so it is not a controlled pair with the negative control under P-201. See `S4-SPEC.md` §6.4 | void |
| image `bt-s4a-20261114c` (`boot.img` `f886223a…`, 201,887,744 B) — **void since P-197** | the first **positive** S4 image: built with `--gpu-addon out/pong-bt-firmware.bin` (sha256 `febdc20d…`) through a scratch copy of `build-strict.sh` at `/tmp/bt-s4a/scripts/` (= repo file + `bt-lead-0002.patch`), `K60_OUT=/opt/k60/trees/k60build/bt-out-s1c`, `--kernel-arg k60bt=1` → 583 B / 30 args. `build-strict.sh` exit 0, `verify-boot-image.py` OK, `check-image-args.py` OK. `kernel_built ba805e4c…`, `payload 1e62d481…`, `payload_kernel a92d7b1e…`, `adt c304361e…`; payload FAT carries `kernel.macho.gpuaddon` 1,027,584 B (byte-identical to the packer output) and the ADT holds exactly one `GpuAddon` cell. See `S4-SPEC.md` §6.2 | built, not booted |
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
3. ~~**Register the BT hardware item** so the gate can see ①–⑥~~ —— **已完成（Lead 合为 `8a497a4`，
   2026-11-15）**：`docs/research/EIGHT-STEPS.toml:342` 现在有 `[hardware.bluetooth]`（`status = "parked"`），
   `K60_EIGHT_STEP_ITEMS=bluetooth` 可用。见 §4。
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
9. ~~**S4 构建侧要合并三处**~~ —— **已合（Lead：`277e09e` + `dbc2cd5`，2026-11-15）**；本分支重基后这三个文件与 main 逐字节相同。
   原文保留供追溯（当时内核侧已就位：`patches/xnu/0510` 在 `series:208`，对缺失单元静默降级，所以当时合并也不会改变任何现有镜像；三处补丁已用临时副本**端到端验证过**）：
   (a) 新文件 `scripts/make-bt-firmware-addon.py`——全文与实测输出见 `S4-SPEC.md` §5.2；
   (b) `scripts/build-strict.sh` 增加 `--gpu-addon <file>` 并转发给 `unixnu build payload`，同时写进 manifest 的 `components`——精确 diff 见 `S4-SPEC.md` §5.3；
   (c) `.gitignore` 给 `firmware/bluetooth/manifest.json` 开否定规则（只有 bytes+sha256，可以入库）——见 `S4-SPEC.md` §5.4。
   固件源是 `E:/k60-work/firmware/qca6490-bt`（113 文件 / 1,063,407 B），白名单筛出 106 条 / 1,022,742 B，容器 1,027,584 B。
10. **命令行门禁的两个参数名 —— 本线已自行补齐（2026-11-14 23:22，commit `7d01f9e`）**：
    Lead 在 `295b44a` 里补了 `k60bt_delay`/`k60bt_step`/`k60bt_warm` 三条 BOOT-ARGS 文档，并明确「剩下的你补」。
    本线补的两处是：(a) `scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS` 增加 `"k60bt_step", "k60bt_delay",`
    （现在在 :48）；(b) `docs/engineering/BOOT-ARGS.md` 补 `k60bt`（总线开关，`0500-k60-bt-qbt-new-files.patch:1221`）
    与 `k60bt_stage`（默认已是 1，阶梯镜像应省略以省 17 B）两行一览 + 两段逐个说明。
    实测：`bt-s1c-a1-20261114c` → `image-arg-audit: OK (31 arguments, 596 bytes)`，
    `bt-s4a-20261114c` → `OK (30 arguments, 583 bytes)`。加名字前它是
    `REFUSED — argument k60bt_step is not in board.toml kernel_args and is not a declared addition`。
    **为什么 k60bt_stage 要从阶梯里删掉**：`qbt_k60.c` 的 `qbt_k60_start()` 先置 `k60.stage = 1` 再解析
    `k60bt_stage`，所以 `k60bt_stage=1` 是纯冗余的 17 B；607 B 上限下它和 `k60bt_step` 不能共存。
11. ~~**把 `origin/main` 合进 `feat/bt-research`（Lead scope）**~~ —— **本线已自行完成（2026-11-14 22:0x，
    merge commit `b29726d`，之后又 rebase 到 `f02acff`/current `main`）**。冲突只有一处
    `scripts/build-strict.sh`（两边都在给 payload 步转发 `--kernel-arg`），按 main 的 `PAYLOAD_ARGS` 形式解决。
    原文保留供追溯：main 比本分支多 4 个提交
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

**已落地（Lead 合为 `8a497a4`，2026-11-15）**：`[hardware.bluetooth]` 现在就在
`docs/research/EIGHT-STEPS.toml:342`，本分支不再携带该补丁。原始补丁（留档）：
`/mnt/e/k60-work/scratch/bt-s4/lead/bt-ledger.patch`
（12,132 B，sha256 `7a31315374545bc458861d67b69dc00b4772b9a55c9bfbd1ea89eaa01a35f48f`）——
`docs/research/EIGHT-STEPS.toml` 新增 `[hardware.bluetooth]`（`status = "parked"`，48 行）、
`scripts/render-eight-step-table.py` 删掉 `UNTRACKED` 里的 `('蓝牙', 'planned')`、
`README.md`/`README_EN.md` 重新生成。已在 scratch 仓库实跑：`--build` 30 项 rc=0、`--flash` 40 项 rc=0、
`K60_EIGHT_STEP_ITEMS=bluetooth --build` 6 项 rc=0、`render-eight-step-table.py --check` 一致。
详见 `S4-SPEC.md` §8。

下面的草案已作废（留档）：它 `status = "research"` 不是合法状态值，evidence 只有章节号、
没有 file:line 锚点，会被 `has_reference()` 判成"缺可核查引用"；`[hardware.bluetooth]` 也不能放在
`[hardware.touch]` 旁边而不处理 `UNTRACKED` 的重复行（P-148）。

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

## 7. S4 hand-over: three Lead-scope patches (all `git apply --check` clean at `b29726d`)

Every patch below lives outside this line's write scope (`scripts/`, `.gitignore`) and is delivered as a
file, not committed here. Paths are on this host; `sha256` is the first 16 hex digits of the patch file.

**Lead ruling 2026-11-14 21:19:** 0001–0003 are accepted and the Lead merges them. **0004 and 0005 are
withdrawn** — the Lead already wrote stronger fixes for the same two gates on `feat/gpu-yibiya` and will
land them on `main`: P-190 becomes *symbol is the criterion* (`if any(needle in name for name in symbols)`,
independent of whether the archive file exists) and P-194 filters manifests by the **branch** a manifest
recorded, which needs no `git show` call. Both are better shapes than mine; do not merge 0004/0005.

| patch | bytes | what it does | sha256 |
| --- | --- | --- | --- |
| `/mnt/e/k60-work/scratch/bt-s4/lead/bt-lead-0001.patch` | 4,858 | new `scripts/make-bt-firmware-addon.py`: packs the whitelisted QCA set into the `NGPUADD2` container DarwinBoot already carries (`qca/` prefix, uncompressed records, manifest-checked bytes+sha256) | `9118fe9e79f85abf` |
| `…/bt-lead-0002.patch` | 2,842 | `scripts/build-strict.sh`: `--gpu-addon <file>` forwarding into the payload step, its existence check, a `gpu addon` log line, and `gpu_addon`/`gpu_addon_path` in the manifest | `765a5271139125e8` |
| `…/bt-lead-0003.patch` | 424 | `.gitignore`: keep `/firmware/` ignored but track `firmware/bluetooth/manifest.json` | `0c4d3b8c555f3836` |
| ~~`…/bt-lead-0004.patch`~~ | 1,687 | **withdrawn** — P-190 in-progress exemption; superseded by the Lead's symbol-as-criterion fix | `f2c37e69f958e6bb` |
| ~~`…/bt-lead-0005.patch`~~ | 5,941 | **withdrawn** — P-194 manifest scoping by recorded head; superseded by the Lead's branch-filter fix | `01b744f4ac6bd96f` |

### The two gates that block every line (diagnosis only; the Lead owns the fix)

The merge of `origin/main` (`b29726d`) brought two gates that no single line can satisfy, so every
line is red before it builds. The analysis below is why they are red; the fix is not mine to ship:

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

### Evidence that the diagnosis is right (and that this line's records are honest)

With the withdrawn patches installed the two gates went green (`P-190 ✅ kernel archives: 4 enabled
archive(s) all present`, `P-194 ✅ TESTS OK 11 cases (0 failure(s))`), which proves the reds were the
sampling scope and not this line's build records. Independently, **all 24 manifests this line has ever
produced** satisfy `recorded sha256 == sha256(git show <head>:patches/xnu/series)` — the series a build
recorded always equals the series that commit actually applied.

Measured on the unpatched tree at `e909d32` (so the numbers a reader will reproduce until the Lead's
fixes reach `main`):

```
P-190  FAIL: CONFIG_XNU_K60_PHYSICAL_BATTERY=y but no k60_physical_battery_start symbol is in
       kernel.macho; build/k60-battery/libK60PhysicalBattery.a was force-loaded into a branch that
       does not run (P-190)
P-194  FAIL gpu-20261114n: manifest patch count equals the series — manifest 224 vs series 227
       FAIL gpu-20261114n: manifest series sha256 equals the file
       TESTS OK 0 cases (2 failure(s))
```

### Hand-over state (who does what next)

**State 2026-11-15 03:30 — everything the Lead owed this line has landed.** Merged on `main`:
`277e09e`+`dbc2cd5` (the three build fragments), the symbol-as-criterion P-190 fix, the branch-filter
P-194 fix, `8a497a4` (`[hardware.bluetooth]` ledger), `344e47d` (P-197). This line added
`k60bt_step`/`k60bt_delay` to `ALLOWED_ADDITIONS` (`7d01f9e`) and the `k60bt`/`k60bt_stage` rows to
`BOOT-ARGS.md`, and switched the S4 carrier to a kernel-embedded blob (`ccd4dfc`).

Lead, remaining: open a device window and fly **two** images — the controlled negative control
`bt-s4c-20261115a` (`535c395a…`, 583 B, `--bt-blob` omitted so the stub is linked) and the positive
`bt-s4b-20261115b` (`2402def9…`, 583 B, embedded blob). Both are built from the same HEAD `68a38f3` with a
byte-identical 453-entry frozen list, so the pair is controlled by construction (P-201). Do **not** queue
the `a1/a4/a5/a7/a9` ladder before the S4 result: the ladder verifies the same firmware-load path, and the
carrier change invalidates its criteria.

This line, next in order:

1. ~~Wait for `main` to carry the Lead's gate fixes, then rebase.~~ Done: `df82dfe` → `ccd4dfc`.
2. ~~Rebuild the positive S4 sample with `--gpu-addon`.~~ Superseded by P-197: the positive sample is
   now `bt-s4b-20261115b`, built with `--bt-blob out/pong-bt-firmware.bin`; success is
   `[bluetooth] addon: linked blob bytes=1027584 records=106` (S4a) and `addon: serving 201560 0` (S4b).
   The old `--gpu-addon` images are void, and their measured `addon: unusable range 0 0` is the P-197
   device evidence. Done: `…b` (positive) and `bt-s4c-20261115a` (negative control) form a controlled pair
   — same HEAD, same 453-entry frozen list, only `--bt-blob` differs (S4-SPEC.md §6.5).
3. Keep the device ladder parked until the Lead opens a window: negative control `bt-s4c-20261115a`,
   positive `bt-s4b-20261115b` (both 583 B, both pass `check-image-args.py`), then — only after the S4
   verdict — the c-series ladder `a1/a4/a5/a7/a9` (596 B), `s3a`/`s3b`.
4. ~~`docs/research/EIGHT-STEPS.toml` needs the `[hardware.bluetooth]` block.~~ Landed on `main` as
   `8a497a4`. The criteria still name the old carrier's line, so this line exported the update as a
   patch instead of editing the shared contract: `/mnt/e/k60-work/scratch/bt-s4/lead/bt-ledger-blob.patch`
   (10,117 B, sha256 `539473c2e2ab2578cbdcb1212047e2ed88a08f3616bd3e569841d79e0258cdc3`) — it rewrites
   `step.plan` / `step.verify` / `step.device.prediction` / `paths` / `parked_why` in
   `docs/research/EIGHT-STEPS.toml` and the P-197 `Check` line in `docs/engineering/PITFALLS.md`.
   `git apply --check` passes on `ccd4dfc`; `render-eight-step-table.py --check` stays consistent
   because only `done`/evidence text changed, not the table cells. The Lead landed it as `626cc9b`
   (split: PITFALLS hand-replaced, EIGHT-STEPS applied), so the branch now carries main's version verbatim.
5. ~~Ledger follow-up for the pair.~~ Landed on `main` as `133473e` "bluetooth: point the S4 criteria
   at the controlled pair". Kept for the record: `626cc9b` still names `bt-s4b-20261115a`
   (superseded) and `bt-s4-20261114b` (old baseline) as the S4 samples. This line exported the correction
   rather than editing the shared contract: `/mnt/e/k60-work/scratch/bt-s4/lead/bt-ledger-pair.patch`
   (7,728 B, sha256 `93791005ac92b8f01b4c8bc2a0160792090b12c05349627cdcfa8da3a223920d`, 1 file, +3/−3)
   — it rewrites `parked_why`, `step.plan`'s S4 sentence and `step.verify`'s evidence to the controlled
   pair `bt-s4b-20261115b` / `bt-s4c-20261115a`. Validated in a scratch repo seeded from `origin/main`:
   `render-eight-step-table.py --check` consistent, `eight-step-gate.py --build` 30 checks rc=0,
   `--flash` rc=0, `K60_EIGHT_STEP_ITEMS=bluetooth --build` 6 checks rc=0. `git apply --check` passes on
   this branch (whose `EIGHT-STEPS.toml` is byte-identical to `origin/main`).
6. **Worktree repair tool — landed on `main` as `ff19c51`.** P-203 restored nineteen trees by hand
   with `E:/k60-work/scratch/refmine/repair-wts.py`, a one-off that hard-codes the main checkout and has
   no test. The Lead asked this line for a generalised version; it was exported as
   `/mnt/e/k60-work/scratch/bt-s4/lead/bt-repair-worktrees.patch` (23,312 B, sha256
   `9a08aade286924780f5f16628a7b03a0b21cc160e60818ad7e5a35309332ed44`, two new files:
   `scripts/repair-worktrees.py` and `scripts/tests/test-repair-worktrees.py`) and the Lead merged it
   as `ff19c51 scripts: add the generalised worktree repair tool` (tag `snap-r190`, registry 83 rules,
   0 failures). **`--check` is deliberately not a gate**: it scans the parent directory and reads
   nineteen pointer files, too expensive for every registry run, and the prune accident is already
   blocked at the source by `git-guard` (rc=128 inside a linked worktree). It stays an incident-recovery
   tool plus an on-demand check; the Lead will wire it into a daily task only if a third accident happens.
   `repair-worktrees.py` recovers the branch by scoring every branch's blobs against the files still in
   the tree, rebuilds `{HEAD,gitdir,commondir}`, then `git read-tree` (never `checkout`, so uncommitted
   work survives byte for byte), and offers `--check` (read-only, exit 1 when a tree is broken) and
   `--dry-run`. It refuses to adopt a sibling directory whose `.git` file points into another repository.
   Measured on this host: `--check` over all nineteen trees → "19 checked, 0 broken, 0 repaired"; the
   test suite → "TESTS OK 29 case(s) (0 failure(s))"; `check-repo-paths.py` (hard-39) → 0 errors; the
   patch applies to a clean `main` clone at `133473e` and the suite passes there too. Two Windows
   details it encodes: a worktree `.git` file is marked hidden and the C runtime refuses to open it for
   writing (EACCES), so the pointer is removed and rewritten; and git's own `worktree list` drops a tree
   whose admin directory is gone, so broken siblings are found by scanning the parent directory and
   checking that the pointer text still names `<main>/.git/worktrees/<name>`.

7. **S4 上机前复核（2026-11-15 14:00）：两枚镜像按现状不能飞。** 四条独立阻断，全部实测：

   | # | 阻断 | 证据 | 后果 |
   |---|---|---|---|
   | 1 | `k60.stage` 默认 1 | `bsd/dev/qbt_k60.c:2073` 先置 1 再解析 `k60bt_stage` | 583 B 的 `k60bt=1` 让 worker 走 S1c 探针分支并在 `:2008` `return`，到不了 `qbt_boot()` |
   | 2 | `k60.warm_boot` 默认 false | `:1814` `if (!k60.warm_boot) return -EOPNOTSUPP;` | 即使 `k60bt_stage=2`，上电仍返回 102 |
   | 3 | `native_gpu_addon_stage` 门闩 | `:1998` 自旋等待；链进内核的定义只有 `bsd/kern/kern_exec.c:7700`（`__DATA,__common`，加载值 0），`qbt_k60.c:341` 的弱定义 `= 1` 被它盖掉 | 命令行没有 `sheng-gpu-addon=1` 时，worker 在 `probe: transport ready` 之后永久阻塞——这就是 2026-11-15 012913 那轮"打完 `transport ready` 就再没有 `addon gate passed`"的原因 |
   | 4 | `/chosen/unique-chip-id` 不存在 | 从 `payload.img` 取出的 `kernel.macho.adt`（15,972 B）`grep -c unique-chip-id` = 0；`make-pong-adt.py:159` 只在传 `--unique-chip-id` 时写这条属性，`build-native-bootimg-local.py` 从不传 | `k60_bt_local_address()` 返回 -ENOENT(2)，`qbt_boot()` 仍不会被调用，`serving` 不会出现 |

   参数预算：base 583 B / 上限 607 B。`k60bt_stage=2` → 597、`k60bt_warm=1` → 596、
   `sheng-gpu-addon=1` → 601；任两条相加即超（stage+warm 610、stage+addon 615），三条 628。
   **没有"只加参数"的解法**：要么从 30 个现有参数里腾出 21 B，要么改代码。Lead 裁决（2026-11-15
   15:36，见 item 9）：阻断 4 由 `main` 的 `3ea8d71` + `dafa502` 在构建期解掉（`--unique-chip-id` 默认
   `4B36305400000001`），阻断 1/2/3 由本分支新增的 `patches/xnu/0511-k60-bt-s4-unblock.patch` 一次解掉，
   **不新增任何启动参数**，所以 607 B 上限不再构成约束。

   仍然成立的一件事：正向镜像的 `addon: linked blob bytes=1027584 records=106` 在 `qbt_k60_start()`
   里、线程起来之前就打，不受上述四条影响——`0511` 之前的旧对照对因此**只能**验 S4a。

8. **日志等级闸门（2026-11-15）**：`k60_log()` 只放行 `level <= 3`（`qbt_k60.c:1545` = `0500:971`），
   `bt_dev_info` 是 level 6 ⇒ 十个调用点永不上控制台，第一个就是 S4c 的原判据
   `QCA controller version 0x…`。逐条审计与替代判据在 `S4-SPEC.md` §7.1；S4c 的通过条件因此改成
   裸 printf 的 `[bluetooth] power=1 result=0 baud=… firmware=<label>`。Lead 裁决：**不放宽闸门**，
   只给 `btqca.c:764` 补一条专用 level-1 行，已落在 `0511`（item 9 第 5 行）。

9. **`0511`：一个补丁解掉三条阻断（2026-11-15，Lead 批准"改代码、不砍启动参数"）**。落点对照表：

   | 阻断 | 落点（`0511` 之后，`bsd/dev/qbt_k60.c`） | 做法 |
   |---|---|---|
   | 1 `k60.stage` 默认 1 | `:2096-2105`（`qbt_k60_start()`） | 默认 0 = 完整阶梯；`k60bt_stage=1` 或任一 `k60bt_step=N` 才进 S1c 探针，`k60bt=0` 仍整条关闭；删掉 `if (!k60.stage) return;` |
   | 2 `k60.warm_boot` 默认 false | `:1818-1827`（`k60_bt_power_on()`） | `return -EOPNOTSUPP` 改为打 `power: cold boot, rails not voted (k60bt_warm=0)` 后继续；该函数只记录上电请求、从不投票 |
   | 3 `native_gpu_addon_stage` 门闩 | `:2006-2015`（`k60_worker()`） | 门条件变 `native_gpu_addon_stage < 1 && (!&k60_bt_blob_len || k60_bt_blob_len == 0)`——P-197 之后固件已在核内，不必等 GPU addon 挂载；先判地址再解引用，没接 `0510` 的构建仍走旧等待 |
   | 4 `/chosen/unique-chip-id` 缺失 | `main` `3ea8d71` + `dafa502`（不在本补丁） | `build-strict.sh` 默认 `UNIXNU_UNIQUE_CHIP_ID=4B36305400000001` 并转发 `--unique-chip-id` |
   | S4c 死判据 | `bsd/dev/qbt/btqca.c:764-771` | `bt_dev_info`（level 6）之后补 `qbt_linux_log(hdev->q, 1, "QCA controller version 0x%08x", soc_ver);`，闸门不放宽 |

   补丁本体：`patches/xnu/0511-k60-bt-s4-unblock.patch` = `patches/bt/0005-k60-bt-s4-unblock.patch`
   （3,718 B，sha256 `07b862dd…f39a`，+34/−3，2 文件 4 个 hunk），`patches/xnu/series:209`；在 post-`0510`
   树上 `git apply --check` / apply 均 rc=0，落地字节与编辑副本逐字节相同。参数不变：30 项 / 583 B。
   Lead 要求重出受控对照对 `bt-s4b-20261115c`（正向）/ `bt-s4c-20261115c`（负向，ADT 也随 `3ea8d71`
   变了所以要重建）。判据：负向 `addon: no GpuAddon property`；正向 `linked blob bytes=1027584 records=106`
   → `serving 201560 0` → `power=1 result=0 baud=… firmware=…` + `QCA controller version 0x…` →
   不再出现 `no platform identity`。

10. **受控对照对已重出（2026-11-15 16:25）**：`bt-s4b-20261115c`（正向）/ `bt-s4c-20261115c`（负向），
    HEAD `5190337`，series 229 / `67baff88…bca`，frozen 两者逐字节相同（`0254f9d5…585e`，同一基线），
    30 项 / 583 B（`k60bt=1`），`verify-boot-image: OK`、`image-arg-audit: OK`。
    | 镜像 | boot.img | kernel_built | payload_kernel | adt | bt_blob |
    |---|---|---|---|---|---|
    | `bt-s4b-20261115c` | `2dc1054e…968` | `8fc5ab58…45e`（106,541,056 B） | `96401d1f…c906` | `dbcab086…1afbf` | `febdc20d…2037`（1,027,584 B） |
    | `bt-s4c-20261115c` | `dbf089c0…8d03` | `5046e338…029e`（105,508,864 B） | `a352bf57…5a20` | `3042f2ca…2c8a` | （空，单字节 stub） |
    待飞窗口；上机前先把 item 9 的落点对照表给 Lead 抽查。

11. **0511 逐 hunk 二分（2026-11-15 晚，Lead 裁决）**：c 对已飞——负向 `bt-s4c-20261115c`
    （`dbf089c0…8d03`）到桌面、判据全中（`console.log:192` `[bluetooth] addon: no GpuAddon property`
    逐字命中；`:186` `K60 BT: published local address ee:98:c5:8a:6b:4e`，identity 种子在 BT 上确认，
    第 4 项阻断关闭；证据 `usblog-20261115-162553/console.log`，245,222 B / 3,535 行）。正向
    `bt-s4b-20261115c`（`2dc1054e…968`）0 字节、port-not-observed、returnedToFastboot=True
    （证据 `usblog-20261115-163144`）。Lead 排除两个假设：不是内核体积（两枚正向都是
    106,541,056 B 逐字节相同；负向 −1,032,192 B，106.5 MB 能起）；不是 blob 本身（旧正向 b
    携带同一个 `febdc20d` blob 到过桌面）。唯一剩余变量 = `0005`+blob 组合 ⇒ **按 hunk 二分**：
    四张图各只带 `0005` 的一个 hunk + blob，判据是**到桌面（SB>100）**，不是 BT 自己的行。
    h1=addon 闸门（`qbt_k60.c:2006-2015`）；h2=warm 去掉 `-EOPNOTSUPP`（`:1818-1827`）；
    h3=stage 默认 0（`:2096-2105`）；h4=btqca 等级行（`btqca.c:764-771`）。每张图构建前先把
    series 换成对应 hunk 并**提交**（构建内合规门禁硬拒 dirty series，第一轮就死在这里）：
    `e296d9e`(h1) / `00aa205`(h2) / `40cdafd`(h3) / `3bcaac3`(h4) / `9bf2de8`(恢复全量)。
    | 镜像 | hunk | boot.img | kernel_built | payload_kernel | frozen | series |
    |---|---|---|---|---|---|---|
    | `bt-bisect-h1` | 闸门 | `3936416f…abe6` | `f4ba4245…57e7` | `252afd1a…dcf0` | `0d3ee7ae…1130` | 229 / `d8c1cee2…07de` |
    | `bt-bisect-h2` | warm | `e2862637…ab81b` | `40ded59a…2419` | `cae9330b…57fab` | `cbc44962…b3cf` | 229 / `30319819…a24a` |
    | `bt-bisect-h3` | stage | `182e73de…1102` | `ee96b73d…5c7c` | `a8e2a142…0a9` | `912bb990…5d3` | 229 / `9d21a68b…05b` |
    | `bt-bisect-h4` | btqca 行 | `d9977a2e…197b` | `1573f6bf…e44` | `d4f91491…db9` | `33c52fcf…76c` | 229 / `62c2c818…fdb` |
    四张 boot.img 均 201,887,744 B、`bt_blob=febdc20d…2037`、30 参数 / 583 B（`k60bt=1`）。
    frozen/series 每张不同是**预期**（series 指向单 hunk 变体，frozen 列表含该变体文件）。
    预测：h1 单独时 stage 仍是 1 → 20 s 睡眠后走**默认第 9 步的首次真机探针**（此时 USB 控制台
    已起，故障会留日志）；h2/h3/h4 单独时要么在闸门前空转要么纯装饰 → 预期到桌面。四张全到桌面
    ⇒ 凶手是 h1+h2+h3 组合（无延迟的早启动固件路径），下一步组合二分先试 h1+h3。
    收尾构建 `bt-restamp-20261115`（全量 0511，series `67baff88…bca`、frozen `0254f9d5…585e`
    ——与 c 对逐字节一致）只为重建 P-165 戳记让注册表回绿，**不是飞行镜像**。5 个提交均未 push
    （5 个提交已由 Lead 在 Windows 侧推上，`5190337..8ec4883`）。

12. **h13 组合图与 0509 OSData 修复（2026-11-15 晚，Lead reply 二/三）**
    - 飞行顺序定稿 h1 → h3 → h13（h2/h4 单独不烧窗口）；h1 silent 就停飞，改
      `k60_bt_addon_load_blob()` 挪到 bring_up 之后 + level-1 具名日志，重建再飞。
    - `bt-bisect-h13`（0511e = h1+h3 两 hunk 合并，commit `670e138`，boot.img
      `0f3a455d…27db`，kernel `141bd513…b3bf`，payload_kernel `4233a2b7…2e4`，
      frozen `94792777…3e91`，series 229 / `ec4eee05…c109a`，blob `febdc20d…`，
      30 参数 / 583 B）。预测：h2 不在 ⇒ warm 拒绝仍在 ⇒ 早启动只到
      addon+transport+闸门+一次冷启拒绝；h13 silent ⇒ 早启动无延迟路径本身是凶手；
      h13 到桌面 ⇒ 真凶是 h2 去掉后的上电续路。
    - 0509 OSData 修复已落（commit `ad49ff2`，选法 ①）：三属性与 radio `device_type`
      改经 `k60_bt_string_property`（`OSData::withBytes`，NUL 在内）发布，补丁
      10,836 B / 319 行 / sha256 `6d92dfe3…a584`（234 增 / 11 删），双子 0003 逐字节
      相同；宿主侧断言 `scripts/tests/test-k60-bt-0509-properties.py` 25 cases 全过。
      法 ②（砍 registerService）被否：会让 bluetoothd 退回 "No bluetooth on this
      device"。不构建；下一张全量 0511 恢复镜像必须带此修复（届时 P-165 重建戳记）。
    - h13 实飞（21:26，Lead 飞）：证据 `usblog-20261115-212643`（237,533 B，无 panic），
      `:192` blob 链入、`:193` power=1 result=-102（−EOPNOTSUPP，h2 缺席）、内核进桌面、
      用户态同 h3（`:1309` marconi 匹配不到、`:1310` MAC 全 00、`:1311` 拿到 ee:98:c5:8a:6b:4e）。
      三张一致 ⇒ 单 hunk 与 h1+h3 均不致死，全量 0005 的 silent 死因收敛到 h2（和/或 h4）。
    - 下一张 `bt-bisect-h12`（0511f = h1+h2，不含 h3/h4；H12_EQUALS_FULL_MINUS_H3_H4 +
      H12_CHECK_OK）：boot.img `0eb30032…9af2`、kernel `67252a00…`、payload_kernel
      `0e74cf5e…`、payload `ee3abfc9…`、adt `313bb5ba…`、series 229 / `cd4acbf6…`、blob
      `febdc20d…`、30 参数 / 583 B。silent ⇒ h2 单独致死（拆子 hunk 再二分）；到桌面 ⇒
      凶手是 h4 或 h2+h4，再出 h124。
13. **h12 实飞与 h123 决定性图（2026-11-15 深夜）**
    - h12 实飞（Lead 飞，证据 `usblog-20261115-230047`，console.log 220,889 B / 3,196 行，
      SpringBoard 132 行、panic 0、supervisor rc=0）：`:192` blob 链入、`:193` `probe: armed
      delay=20s step=9`；`:702-:705` awake / core created / transport ready / addon gate
      passed；`:707` s1 mapped（gcc=fffffff8be6b6000 uart=fffffff8be8ab000
      qup=fffffff8be8af000）；`:709`+`:712` s2 gpll0_cmd=00000001 locked=1；`:717` s3
      qup_vote_after=0000020f；`:719-:727` s4 halt 回读（core=00004220 core2x=00004220
      m_ahb=00000000 s_ahb=80000002 se20=00004220）；`:729-:733` s5；`:735` s6 root_on=1；
      `:737-:741` s7 rcg_cfg 00100000→00100001；`:743-:751` s8 fw_rev=00000204
      qup_hw_ver=30080000；`:753-:760` s9 dma_tx/rx=0；`:761` probe: done；`:762`
      `power=1 result=0 baud=115200 firmware=` ——**电源/时钟/QUP 整段首次真机成功**
      （h3 是 −102、全量 silent，只有 h12 是 0）。
    - 判读：**h2 不是凶手**。只剩两种可能：h4 单独致死，或 h2+h3 组合致死（h1+h3 只是 −102
      且到桌面）。`getBytes:range:` 在 h12 里 0 次（h1 36 次、全量 36–37 次）——C 族与身份
      发布链的新旁证（h12 无 h3 故无崩溃），只记录，三态判定表归 display 线。`firmware=` 为空
      是预期：固件下载在下一段（btslim/QCA 协议），不在 S1–S9。
    - `bt-bisect-h123`（0511g = h1+h2+h3，不含 h4；H123_EQUALS_FULL_MINUS_H4 +
      H123_CHECK_OK；构建 commit `540f51b`、series 恢复 `36d97a9`）：boot.img
      `580b2795…e9a6`（201,887,744 B）、kernel_built `bf3aee6b…445b`（106,541,056 B）、
      payload_kernel `0140faa5…fe33`、payload `15b7b9ba…583d`、adt `b082c73d…41c2`、
      dtb `2d044eaa…`、fd `cf4485712c29…`、blob `febdc20d…`、frozen `0fa2c372…28e7`、
      series 229 / `d80464df…8115`、30 参数 / 583 B `k60bt=1`、head `540f51b`、dirty 0；
      verify-boot-image OK + image-arg-audit OK。
    - 判读树：h4 单独 silent ⇒ 凶手是 h4，h123 用于确认 h2+h3 无害；h4 单独到桌面 ⇒ 凶手是
      h2+h3 组合，h123 是决定性那张。
14. **h23 与 h4 单独实飞、h124 决定性图（2026-11-16 凌晨）**
    - `bt-bisect-h23`（0511h = h2+h3，不含 h1/h4）**到桌面**：证据 `usblog-20261115-235417`
      （console 3,233 行 / 225,486 B、SpringBoard 128、panic 0、rc=0、`:453` disk5s1
      vol-uuid 1BCD69FF Data 正常、`:192` blob 链入）。两个可观测性副作用要记住：`:193`
      `probe: armed` 消失（h3 的 stage 默认 0 让早启动探针不再挂载，不是失败），
      `getBytes:range` 0 次。
    - `bt-bisect-h4` 单独飞（`usblog-20261115-230627`，253,946 B、SB 13、panic 0、
      `[bluetooth]` 只有 5 行、停在 transport ready、getBytes 36）也到桌面。
    - 六张矩阵（全 Lead 飞）：h1 SB13/getBytes36/power 未成功；h13 SB13/36/-102；h4 SB13/36/无
      power 行；h12 SB132/**0**/result=0；h23 SB128/**0**/无 power 行；h123 与全量 **silent**。
    - 两条硬结论：① **h2 是 `getBytes:range` 消失的必要条件**（含 h2 的两张都是 0 次，不含的
      四张都是 36 次），与 0509 的 ad49ff2 无关，C 族真凶是「冷启动早退导致身份发布走错分支」，
      不必等 ad49ff2；② **致命集必须含 h4**——h23 能起、h4 单独能起、全量 silent ⇒ 凶手是
      h4 × {h1,h2,h3} 的交互，此前「必须含 h3 且含 h2 或 h4」的推断被 h23 推翻。
    - 下一张只出 **h124（h1+h2+h4）**：能起 ⇒ 致命组合是 h3+h4，再出 h34 收口；silent ⇒ 用
      0512 的三个开关（`pong_bt_smmu=0` / `pong_bt_rcg=0` / `pong_bt_noboot=1`）逐条关断。
      变体 `0511i-k60-bt-bisect-h124.patch`（2,686 B，sha256 `83e80a10…bbe3`，
      H124_EQUALS_FULL_MINUS_H3 + H124_CHECK_OK），series 换 hunk 的提交 `9b4bc59`。
    - `bt-bisect-h124`（0511i = h1+h2+h4，不含 h3；commit `9b4bc59`，构建 00:20）：boot.img
      `b6d293e5cfe56903bf787fd48f56332bd763a9dac233e0753e66a5f099eec641`（201,887,744 B）、
      kernel_built `a6980b9c4e79912e26834e4df1f17f544e80521c6f3e3e724c0d1d6fa2630f06`、
      payload_kernel `0f73563d7b8c7008889d65ac19458dce27363c08e2e2671f025ebc35fc2b87a5`、
      payload `86d8bb5716f7c0e623c587945a18593697e3567812b307326618ca3ebdd82080`、
      adt `4db35f3c932f9bfe3b36e301c1295e6f0e6bebd8299cdf4c3833d38d60f9d12a`、
      frozen `b0c08d35a4970b6df82c788732d85823c045c6d94c31b19458dd6f540cd34792`、
      series 230 / `21eda89a147c96533ae42cbfcaf67f8393806c8ab9e9ebd49cf4c1dc891a2240`、
      blob `febdc20d…2037`、30 参数 / 583 B `k60bt=1`、head `f742288`、dirty 0；
      verify-boot-image OK + image-arg-audit OK。series 是 230 而不是 229，因为 0512 已在尾部。

15. **0512 完整阶梯延期启动（`pong_bt_late=1`）与 §7.3 机制假设（2026-11-16 凌晨）**
    - 问题不在哪一行而在时机：`qbt_k60_start()` 由 `bsd/kern/bsd_init.c:1352` 早启动调用，
      worker 一起线程就 `k60_bt_power_on()` + `qbt_boot()`，总线写死时 CDC console 还没枚举完，
      于是整机静默、连死在哪一行都看不到。
    - `patches/xnu/0512-k60-bt-late-start.patch`（twin `patches/bt/0006`，commit `a4c257a`）
      把阶梯挪到 `bsd/kern/kern_exec.c` 的 K60DATA 部署点（`k60_uilib_deploy()` 之后）：早启动只建
      core、快照 addon、把 worker 挂在 `k60.late_go` 上；Data 挂载后 `qbt_k60_late_start()` 放行，
      日志依次 `late: armed…` → `late: released by the K60DATA deploy point` →
      `late: released, starting the full ladder` → `full: power_on enter` →
      `full: dma buffer and smmu bypass ready` → `full: uart pins parked` → … →
      `full: qbt_boot enter`，**最后一行就是死亡点**。
    - 三个机理开关：`pong_bt_smmu=0`（跳过 S2CR/SMR 写入）、`pong_bt_rcg=0`（跳过两处
      `k60_gcc_set_se_rate()`）、`pong_bt_noboot=1`（停在固件下载前）。
    - **序列位置是尾部**（`patches/xnu/series` 最后一行，不是 0511 之后）：0610/0614/0616 都锚在
      `(void)k60_uilib_deploy(); }` 这个交界上，任何插入都会让它们 apply 失败（第一轮构建死在
      `patch does not apply: bsd/kern/kern_exec.c:7900`）。移到尾部后整条 series 230 个补丁
      从头重放 APPLIED=230 BAD=0。
    - 不加任何 `pong_bt_*` 时行为与 0511 逐字节等价，宿主侧断言
      `scripts/tests/test-k60-bt-0512-late-start.py` 39 cases（四个默认值 + 三条裸调用只剩受保护
      形态 + 序列位置）全过；§7.3 记录 a SMMU / b RCG / c DMA 三个假设的"若是它日志长什么样"与
      各自开关，§7.4 记录断网出图的 `UNIXNU_KERNELCACHE`。
    - `bt-late-20261115a`（全量 0511+0512 的 late 图）按 Lead 裁决**暂缓**：致命集未收敛前飞它，
      silent 也分不清是"late 没救回来"还是"h4 交互仍在"。

    - 旁记（Lead 账本问题，非本线）：`record-boot.py` 这次把 h12 记成 series 226 /
      `9688ad85…`（读的是 main 当前 series，不是镜像 manifest），Lead 本周改成优先取
      `build-manifest.json` 的 series；本线 manifest 字段一直完整。

16. **h124 实飞到桌面、致命集收敛为 h3 × h4（2026-11-16 凌晨）**
    - `bt-bisect-h124`（0511i = h1+h2+h4，不含 h3）**到桌面**：证据 `usblog-20261116-004519`，
      console.log 223,630 B / 3,229 行、SpringBoard **132**、panic 标记 0、supervisor rc=0、
      `getBytes:range` **0 次**。关键行：`:192` blob 链入、`:193` `probe: armed delay=20s step=9`、
      `:703-:706` awake / core created / transport ready / addon gate passed、`:708` s1 mapped
      （gcc=fffffff757695000 uart=fffffff75788a000 qup=fffffff75788e000）、`:710/:713` s2
      gpll0_cmd=00000001 locked=1、`:718` s3 qup_vote_after=0000020f、`:720` 起 s4 halt 回读、
      `:762` probe: done、`:763` **power=1 result=0 baud=115200 firmware=**、`:455` disk5s1
      vol-uuid 1BCD69FF、`:485` K60DATA mounted ro=0、`:1037` Early boot complete。
    - 七张矩阵（全 Lead 飞）：h1 SB13/36/armed 有/power 1；h13 SB13/36/有/1(−102)；h4 SB13/36/有/0
      （停 transport ready）；h12 SB132/**0**/有/1(result=0)；h23 SB128/**0**/**无**/0；h124
      SB132/**0**/有/**1(result=0)**；全量 silent。
    - 收敛：① 能起的三张（h12/h23/h124）都含 h2 ⇒ **h2 是「不再 silent」的必要条件**；
      ② 全量 = h124 + h3，h124 能起、h23（h2+h3）能起、h4 单独能起 ⇒ **致命集是 h3 × h4 两两
      交互**，不需要 h1、也不需要 h2 同时在场；③ h23（探针不跑）与 h124（探针全程跑通）对照
      ⇒ **h3 是「让探针看不见」的 hunk，h4 是「让内核起不来」的 hunk**，两者叠加才 silent。
    - C 族归因按 h2 口径改写：不是 0509 的 ad49ff2 直接生效，而是 h2 让冷启动早退消失后身份发布
      第一次真正执行（display 线已按此口径改）。
    - 下一张 `bt-bisect-h34`（0511j = h3+h4，不含 h1/h2）：变体
      `0511j-k60-bt-bisect-h34.patch`（1,711 B，sha256 `5a81ac8a4dff49848313aa9c7c1917f5384ef7da352c4869dc058f038f1c8612`，
      H34_EQUALS_FULL_MINUS_H1_H2 + H34_CHECK_OK），series 换 hunk 的提交 `2cdb459`。
      h34 silent ⇒ 致命集锁定为 {h3,h4}，再在 h34 上逐条关断 `pong_bt_smmu=0` / `pong_bt_rcg=0` /
      `pong_bt_noboot=1` 定位；h34 能起 ⇒ 还需 h1 或 h2 之一在场，出 h134 与 h234 各一张。
    - `bt-bisect-h34`（0511j = h3+h4，不含 h1/h2；commit `2cdb459`，构建 01:06）：boot.img
      `3b7d79b73e435b5058f692152150e7fc7ea27c335ceb9c7877e8c61f2c9b1873`（201,887,744 B）、
      kernel_built `556ad11d0e86845fdf0a401b0b3665037efb233dd055840e7a35712f27c45947`、
      payload_kernel `6544ca3e8b69c882828a586ad9cdfb4d26a7a651b0a6f3cfcb83a5e1997f95fd`、
      payload `75900b955fc00e85adbdba3f562578530e5594615aed6f1b6754456683ce9814`、
      adt `9bbad874197fa6b88f5e4771cbef2a363f98a233836d6086e011252fd496dd9d`、
      blob `febdc20d…2037`、30 参数 / 583 B `k60bt=1`、head `f604d5f`、dirty 0、
      series 230 / `dfa2f138ae7c7d0a4aed07f6f558500729618f1fa48967e5a44e442598319a34`；
      verify-boot-image OK + image-arg-audit OK（30 arguments, 583 bytes）。
      构建后 series 已还原为 0511（提交 `205c72f`），镜像输入同步移除 0511j。

17. **h34 实飞到桌面、致命集改为「h4 × h3 × (h1|h2)」三元组（2026-11-16 凌晨）**
    - `bt-bisect-h34`（0511j = h3+h4，不含 h1/h2）**到桌面**：证据 `usblog-20261116-014536`，
      console.log 134,032 B / 2,264 行、SpringBoard **128**、panic 标记 0（`panic(` / `panic: ` /
      `Debugger called` / `stackshot` 各 0）、`getBytes:range` **0 次**。关键行：`:186`
      `K60 BT: published local address ee:98:c5:8a:6b:4e`、`:192` `[bluetooth] addon: linked blob
      bytes=1027584 records=106`（`[bluetooth]` 全篇仅此 1 行）、`:300` K60DATA attempt enter、
      `:304` APFS UUID 1BCD69FF 绑到 Data UFS 窗口 /dev/disk5s1、`:481` K60DATA mounted ro=0、
      `:973` Early boot complete、`:2196` Pong UI 开发版 SpringBoard 激活门。
      `probe: armed` / `probe: done` / `power=` 三行全无 —— h3 把早启动探针整段拿掉，与 h23 同形的
      可观测性副作用，不是失败。
    - 结论更新：h34 = h3+h4 能起 ⇒ **致命集不是纯 {h3,h4}，还必须带 h1 或 h2 之一**；
      「h3 × h4 两两交互」被推翻，改为 **h4 × h3 × (h1|h2) 三元组**（h1 与 h2 至少一个在场）。
    - 下一轮：`bt-bisect-h134`（0511k = h1+h3+h4）与 `bt-bisect-h234`（0511l = h2+h3+h4）各一张，
      两张即可定位是 h1 还是 h2 在放大。变体
      `0511k-k60-bt-bisect-h134.patch`（2,735 B，sha256 `b1a81f2c851371ccd666210a945613975b88fa431166f35864909b955167a3f8`，
      H134_EQUALS_FULL_MINUS_H2 + H134_CHECK_OK）与
      `0511l-k60-bt-bisect-h234.patch`（2,694 B，sha256 `e2ff0dc3821bef2af126bba97ad78556df8f4aeec5222538cb7a73550e9ea42f`，
      H234_EQUALS_FULL_MINUS_H1 + H234_CHECK_OK）；series 换 h134 的提交 `7e8a247`。
    - 变体校验脚本 `E:/k60-work/scratch/bt-s4/bisect/make-h134-h234.sh`：scratch 仓库必须先
      `git reset --hard post0510` + `git clean -fd`，否则上一轮的脏文件让 `git apply` 报
      `patch does not apply`（第一次跑就是这样失败的）；h134 的反向参考是「full − h2」、h234 是
      「full − h1」，多减 h4 会得到 MISMATCH。
18. **d 系列第一张图 `bt-d1-smmu` 与它暴露的 0510/0620 上下文撞车（2026-11-16 凌晨）**
    - 图：全量 0511（series 232）+ 一个开关 `pong_bt_smmu=0`，31 个启动参数 / 598 B。
      manifest `E:/k60-work/artifacts/bt-d1-smmu/build-manifest.json`（built_at 2026-11-16T02:23:44+08:00）：
      boot_img `bd1f5bc6f4cb96f9ec8995ca86a0f0d0769879c75a933dc7a2d130b3718d45b5`（201,887,744 B）、
      kernel_built `d40ae0b9c4c50795481909cd451434071bffeb297f35b970e453f9014f35e682`、
      payload_kernel `487a1518c0e1824e8951064df7d4994ebdacb4a5e1734f1c33a26efdeefd270a`、
      payload `ed2c08d1503e5efeceeb4f57fdcf1ba8e850d5459fee383b52982eb44ce244ec`、
      adt `b0423763799659620dd79f79acb3ad5be9024af765d87c4e9612c3a46bb011c6`、dtb `2d044eaa…`、
      fd `cf4485712c29…`、bt_blob `febdc20d…`、series {232, `dcc7bb45d311dc5f`, namespace names+sizes,
      file `dff40135325fd673`}、dirty_files 0；`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 598 bytes)`。
      这是第一张带 `namespace` 字段的图（P-214 生效）。
    - 首次构建失败：`unixnu: XNU patch …/patches/xnu/0620-k60-adsp-blob.patch: git failed (1):
      error: patch failed: osfmk/conf/files.arm64:22` / `patch does not apply`。
      原因：`0510` 把 `osfmk/arm64/k60_bt_blob.s` 插在 `WKdmCompress_4k.s` 之后（hunk `@@ -22,6 +22,7 @@`），
      而 `0620` 的 hunk 上下文正是 `k60_metal_blob.s` / `WKdmCompress_4k.s` 之间；0510 先插一行，0620 整体错位。
      合并 main 之前 0620 不存在，所以这是这次 merge 才引入的撞车，不是 0510 本身写错。
    - 修法：0510 的插点挪到 **`lz4_encode_arm64.s` 之后**（`@@ -25,6 +25,7 @@`），后续没有补丁引用那一段；
      两个孪生文件同步改、字节仍相同，新 sha256
      `3309d123624bf4461a5ce4e6e197e613546af51ebc894967ad8084a21f7eaa87`（15,718 B，仍 289 增 / 1 删）。
      提交 `eb3cd83`。全量重放校验：pristine `/opt/k60/trees/out-old/feeds/xnu-c465a9f8` 上 232 个补丁
      `git apply` 顺序打完 → `APPLIED=232 BAD=0`，`conf/files.arm64` 里 24 行 `k60_metal_blob.s`、
      25 行 `k60_adsp_blob.s`、30 行 `k60_bt_blob.s`。
    - 教训：**给同一文件追加行时，先看后面还有没有补丁锚在同一段上下文**；插在「列表末尾附近没人引用的一行之后」
      永远比插在中间安全。
19. **d1 实飞：仍 silent，SMMU 路径被排除（2026-11-16 04:19）**
    - Lead 实飞 `bt-d1-smmu`（boot.img `bd1f5bc6…45b5`、kernel `d40ae0b9…`、series 232 /
      `dcc7bb45d311dc5f`、blob `febdc20d…`、args `['k60bt=1','pong_bt_smmu=0']`、head `eb3cd83`）：
      证据 `E:\k60-work\evidence\usblog-20261116-041744`，`port-not-observed`、`bytes=0`、
      `complete=False`、`returnedToFastboot=True`，supervisor rc=2，端口 84 s 内从未出现；
      `record-boot.py` 正确拒记（0 SpringBoard 行）。
    - 判读：关掉 `k60_smmu_bypass()` 一样静默 ⇒ **SMMU / stream-mapping（S4-SPEC §7.3 假设 a）排除**。
      与 wifi 线的「lease 抢在分配之前」不是同一段代码，两个结论不冲突。
    - 下一步（Lead 指定，一次一张）：d2 = 全量 0005 + `pong_bt_rcg=0`（假设 b：共享 RCG 复位停掉
      UFS 参考时钟）、d3 = 全量 0005 + `pong_bt_noboot=1`（假设 c：固件下载整段不跑）。
      每张与 d1 同形：同 series（232）、同 blob、manifest 带 `namespace`、args 只多一个开关；
      出图后只报 tag + boot.img sha，由 Lead 飞。
    - Lead 另外两条规矩：① 以后往 `osfmk/conf/files.arm64` 加行一律加在**文件末尾独立 hunk**，
      不要贴着别人的行（0510×0620 撞车的通用教训）；② `dc57e6c` 与
      `scripts/tests/test-series-fingerprint.py` 要两边都断言 `namespace` 字段，d 系列跑完后对齐，
      由 Lead 合进 main。
20. **d2 实飞：仍 silent，RCG 路径排除（2026-11-16 04:34）**
    - Lead 实飞 `bt-d2-rcg`（boot.img `7f83bc0c…4101`、kernel `c68c54ed…`、series 232 /
      `dcc7bb45d311dc5f`、blob `febdc20d…`、args `['k60bt=1','pong_bt_rcg=0']`、head `ffc1de1`）：
      证据 `E:\k60-work\evidence\usblog-20261116-043417`，`port-not-observed`、`bytes=0`、
      `portSeen=false`、`returnedToFastboot=true`，console.log 0 B（空文件哈希 `e3b0c442…`）。
    - 判读：跳过 `k60_gcc_set_se_rate()` 两个调用点一样静默 ⇒ **S4-SPEC §7.3 假设 b（共享 RCG 复位
      停掉 UFS 参考时钟）排除**。a、b 均被实飞否证，只剩 c（固件下载 DMA 缓冲未进 IOMMU）。
    - 下一张：d3 = 全量 0005 + `pong_bt_noboot=1`（上电/时钟/QUP 照跑、`qbt_boot()` 固件下载整段不跑），
      即假设 c 的判据；d3 起来 ⇒ 凶手在固件下载段，d3 仍 silent ⇒ 三段假设全灭，转 d4（`pong_bt_late=1`）
      区分「早启动时序」与「BT 代码本身有毒」。
21. **九格矩阵收敛：致命集恰好 {h1, h2, h3}，h4 无关（2026-11-16 04:38）**
    - Lead 补飞了 23:18 就构建好、一直没飞的 `bt-bisect-h123`（`580b2795…`、kernel `bf3aee6b…`、
      series 229 / `d80464df…`）：证据 `E:\k60-work\evidence\usblog-20261116-043650`，
      `port-not-observed`、`bytes=0`、`returnedToFastboot=True`、supervisor rc=2 ⇒ **silent**。
    - 九格矩阵（全部 Lead 实飞，SpringBoard / getBytes:range）：h1 13/36 起、h13 13/36 起、h4 13/36 起、
      h12 132/0 起、h23 128/0 起、h124 132/0 起、h34 128/0 起、**h123 0/— silent**、全量 0005 0/— silent。
    - 结论：**致命集恰好是 {h1, h2, h3} 三者齐备，h4 无关**；h123 去掉任意一个都能起
      （h23、h13、h12 全起），三者都是必要条件。此前「h2 是必要条件」「致命集是 h3×h4」两条推断作废。
    - 方法教训（Lead 亲述，已写进 S4-SPEC §7.8）：四个 hunk 有 15 个非空子集，本轮只飞 9 个，
      缺的那一格正好是决定性的；二分要么飞满全部子集，要么在矩阵里把「已构建未飞」显式标出来。
      PITFALLS 草稿见 `scratch/bt-s4/PITFALLS-draft-already-built.md`（正式编号由 Lead 发）。





