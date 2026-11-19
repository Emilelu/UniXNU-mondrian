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
22. **十一格矩阵补齐：h2 单格补飞，P-218 门禁落地（2026-11-16 04:56）**
    - Lead 补飞了 h2 单独那张（`bt-bisect-h2`，boot.img `e28626377fedde4b42f538187eaed31a09f3285fa8500d7aba812e6589eab81b`）：
      证据 `E:\k60-work\evidence\usblog-20261116-044817`，console 3,379 行 / 235,151 B、
      SpringBoard 13、`getBytes:range` 35、panic 0；`:192` blob 链入、`:193` probe armed、
      `:702-:704` awake / core created / transport ready，停在 transport ready，无 `power=` 行。
    - 判读：h2 单独能起但不含 h1 的门闩，走不到上电，与 h4 单格同形。至此**构建过的十一张全部飞过**，
      十一格矩阵写进 `S4-SPEC.md` §7.8。
    - 没构建的只剩 h14 / h24 / h134 / h234 四格，Lead 判断都不改变结论（{h1,h2,h3} 的必要性已由
      三次「各去掉一个」定案），除非 d3 把机理指向 h4。
23. **d3 实飞：仍 silent，三张 d 图把 §7.3 的 a/b/c 全部否证（2026-11-16 05:33）**
    - Lead 实飞 `bt-d3-noboot`（全量 0511 + `pong_bt_noboot=1`，boot.img
      `07c139238cf4f3dff8d56e9145d05254ba7efb2cd5b0ebf4e7c697a3df0a817e`、31 参数 / 600 B、
      series 232 / `dcc7bb45d311dc5f`、blob `febdc20d…`）：证据
      `E:\k60-work\evidence\usblog-20261116-053306`，`port-not-observed`、`bytes=0`、
      `portSeen=false`、`stopReason=fastboot-return`、console.log 0 B ⇒ **silent**。
    - 三张 d 图全部 silent：d1 关 SMMU bypass、d2 关 SE 时钟、d3 关固件下载，都一样死 ⇒
      S4-SPEC §7.3 的假设 a / b / c 全部否证；死亡点在 `k60_bt_power_on()` 之前，
      或在它内部三开关之外的那几步（`k60_map` / `kmem_alloc_contig` / `pmap_find_phys` / TLMM pins）。
      落档见 `S4-SPEC.md` §7.9。
    - 下一格：`h123 + pong_bt_noboot=1` 交叉格（series 换 0511g 变体、参数加 `pong_bt_noboot=1`），
      构建提交 `8faa102`。

    - 门禁 **P-218**（`scripts/check-bisect-coverage.py`，main `216902a` / snap-r211）已随 main 合入本分支：
      拿 `build-manifest.json` 的 `boot_img` 与 `evidence/*/boot.json` 的 `imageSha256` 做差集，
      `--prefix bt-bisect-` 直接列出「构建完没飞」的镜像。
24. **d4 实飞：第一行内核 panic，死因是 io_submap 只有 8 MiB（2026-11-16 05:52）**
    - Lead 实飞 `bt-d4-late`（全量 0511 + `pong_bt_late=1`，boot.img
      `87b819f90ddfdd48ac78beebe93b7ddc690b7d48d84a49465ff9ef189a9472d3`、31 参数 / 601 B、
      series 232 / `dcc7bb45d311dc5f`、blob `febdc20d…`）：证据
      `E:\k60-work\evidence\usblog-20261116-055237`，capture `bytes=27727`、`portSeen=true`、
      `panicMarker="K60PANIC: ring kept"`，console 492 行 —— 第一次不是 0 字节。
    - console 死点（连续行）：`:480` K60UILIB deploy → `:481` late released by the deploy point →
      `:483` `full: power_on enter` → `:484` `power: cold boot, rails not voted` →
      **`:486` `K60PANICARGS kmem_alloc(0xfffffff3447b1240, 1048576, 0x100021): failed with 3 @vm_kern.c:178`**
      → `:487` K60PANIC → `:491` K60DATA mounted。
    - 解码：1 MiB、`3` = `KERN_NO_SPACE`、`0x100021` = `KMEM_NOFAIL|KMEM_PAGEABLE|KMEM_PERMANENT`
      —— 正是 `io_map()` 非 unmappable 分支的旗标组合（`osfmk/arm/io_map.c:120-129`），而
      `io_submap` 全内核只有 **8 MiB**（`:65` `IO_MAP_SIZE (8ul << 20)`）。BT 全量阶梯往它里面塞
      GCC 2 MiB（`0500:107`）+ TLMM 1 MiB（`0500:96-97`）+ APPS SMMU 1 MiB（`0508:63`），
      加上同进程其它 60 处 `ml_io_map` 调用点，2 MiB 连续空间申请失败。
    - 这解释了 §7.8 的致命集：h1 开门闩 + h2 去早退 + h3 stage=0，三者齐备才真的执行到
      `k60_map(&k60.tlmm, …1 MiB…)` 与 `k60_smmu_bypass()`；`0507` 探针只 map gcc/uart/qup
      （无 TLMM/SMMU），所以探针全过而全量阶梯 panic。先例：ADSP 线
      `patches/xnu/0613-k60-adsp-pas.patch:362-370` 已用 `ml_io_map_unmappable()` 绕开同一限制。
    - 修法 `patches/xnu/0513-k60-bt-io-windows.patch`（孪生 `patches/bt/0007`，4,660 B，
      sha256 `0517653d13a18c966c5a57df4537da004d630ef04875e17a76e0263d2c812cad`，单文件
      `bsd/dev/qbt_k60.c`，+36/−4 行；2026-11-16 补三行注释说明 0621 走另一条路、两者不叠加时各自动作）：新增 `k60_map_big()` 走 `ml_io_map_unmappable()`
      （`K60_WIMG_IO 0x7u` = VM_WIMG_IO），GCC（阶梯 + 探针）/ TLMM / APPS SMMU 四处改用它，
      UART/QUP/GIC 保持 `k60_map()`；映射完 GIC 后打
      `full: windows mapped, gcc/tlmm/smmu charged to kernel_map`。位置：`patches/xnu/series`
      末尾（233 条），紧随 0512。提交 `4d7c013`。
    - 校验：整条 series `git apply` 重放 **APPLIED=233 BAD=0**；host 测试
      `scripts/tests/test-k60-bt-0513-io-windows.py` **TESTS OK 28 case(s)**；series 指纹
      `e2f0178190e95ef9 233`。
    - 下一张：`bt-0513-iowin-late`（全量 0513 + `pong_bt_late=1`，与 d4 的唯一差别是窗口分配器）。
      判据：panic 消失且日志过 S9 ⇒ io_submap 就是死因；仍 panic 在同一行 ⇒ 那 1 MiB 不是
      GCC/TLMM/SMMU 而是别的调用点，按 `K60PANICARGS` 的地址回查。落档见 `S4-SPEC.md` §7.10。
25. **io_submap 是全内核共享预算（P-219）；d5 / d6 两条配方的分工（2026-11-16 06:40）**
    - P-219（main `caad898`，`scripts/check-io-map-budget.py`）：已应用树上 37 个可解析
      `ml_io_map` 调用点合计 `0x73a900` = **7.23 MiB / 8 MiB**，另有 7 处尺寸是运行时变量；
      `k60_usblog` 单文件 ≈5.2 MiB、`qbt_k60` ≈4.2 MiB。**加任何 IO 窗口都要先算全树总和**，
      不是只看本次请求的大小。落档见 `S4-SPEC.md` §7.11。
    - 两条修法不可同时飞：**0621**（Lead / main）把 `IO_MAP_SIZE` 从 8 MiB 抬到 32 MiB；
      **0513**（本线）把 BT 的 GCC/TLMM/APPS SMMU 改走 `ml_io_map_unmappable()`。
      0513 的注释已写明「0621 走另一条路，两者不叠加时各自动作」。
    - **d5** = main 227 + 0507..0512（不含 0513，含 0621）+ `k60bt=1 pong_bt_late=1`：
      只验「抬高预算是否足以越过那次 1 MiB 分配」，排除 0513 的代码路径。
    - **d6** = main 227 + 0507..0513（全含）+ 同一组参数：验「0513 单独是否够」；与 d5 的差别
      只有窗口分配器。两条共用判据：`:483` 之后不再有 `kmem_alloc(… 0x100021)` panic，
      且出现 `power=1 result=…` 或 `full:` 后续行。两条都死 ⇒ 查 unmappable 分支的
      `KMA_DATA` 与 `VM_WIMG_IO`。落档见 `S4-SPEC.md` §7.12。
    - 并发提醒：d5 构建期间 Lead 占着本 worktree，`patches/xnu` 不能动（`freeze()` 会在构建
      结束前重算 `board.toml dts patches/xnu scripts` 并比对），docs 不在冻结集内。
26. **d5 图 `bt-d5-iomap` 已出（2026-11-16 06:40，Lead 配方）**
    - 构建：Lead 在同一 worktree 跑 `build-strict.sh bt-d5-iomap … --kernel-arg k60bt=1 --kernel-arg
      pong_bt_late=1`，exit 0；series 233 条、尾部 `… 0511 / 0621 / 0512`（**不含 0513**）。
    - manifest：boot_img `491c62de4c217ce63659defd0272584d205c828f3f432f377d5902c2679dfb3e`
      （201,887,744 B）、kernel_built `2c8d92c6862b72cbba68371fed0b97a1c83f01b58572849199881c482dc09092`、
      payload_kernel `bd399e983fe6a011370a2fe6022b17e8f058343ffc898cc9a71bfecf26e2a3dc`、
      payload `9db86eb3bc198e27b11be5d91f97f41ac89350edcd8711a1a1cf967425ca9247`、
      adt `f1377190e2998e23a3822cba8c5cff7f840fccdf714a35404615bc103a681103`、dtb `2d044eaa…`、
      fd `cf4485712c29…`、bt_blob `febdc20d…`、frozen `4f47dad8…`、
      series {233, `c2182894e0f8dea8`, namespace names+sizes, file `c3e6599d45142a1b`}、
      args [k60bt=1, pong_bt_late=1]、head `44e2a50`、dirty 0。
    - 校验（INSIDE WSL）：`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 598 bytes)`。
    - 0513 注释按 Lead 要求补三行（0621 走另一条路、两者不叠加时各自动作）：新 sha256
      `0517653d13a18c966c5a57df4537da004d630ef04875e17a76e0263d2c812cad`（4,660 B，+36/−4），
      孪生 `0007` 同步为字节相同；整条 series 重放仍 **APPLIED=233 BAD=0**（此时 series 里没有 0513，
      重放脚本用的是含 0513 的临时序列）。host 测试 28 例通过，其中新增一条不变式：
      **0513 与 0621 永不同时出现在一条 series 里**（d5/d6 各自一种合法状态）。
27. **d5 实飞：panic 消失，停点移到 `qbt_boot()` 内部（2026-11-16 06:41–06:46）**
    - 证据 `E:/k60-work/evidence/usblog-20261116-064150`：`491C62DE…DFB3E`（= `bt-d5-iomap`）、
      bootAccepted true / exit 0 / returnedToFastboot false；capture `captured-budget-complete`、
      bytes 224,863、portSeen/portOpened true、openErrors 0、stopReason `budget`、panicMarker null；
      console.log 3,241 行、sha256 `917B5AA9…A20B`、SpringBoard **132**、`getBytes:range` **0**、
      panic 标记 0、心跳 16 条（t=15…240）。
    - **0621 有效**：d4 在 `:484` 之后必现的 `K60PANICFMT` / `K60PANICARGS kmem_alloc(…, 1048576,
      0x100021): failed with 3` 全部消失；`:486`/`:487` SMMU 旁路、`:488` dma+smmu ready、
      `:489` uart pins parked、`:493` clocks vote、`:494` `full: qbt_boot enter` 依次出现。
    - **新停点**：`:707` `QCA controller version 0x12110201`、`:708` `addon: serving 146068`（rampatch）、
      `:724` `addon: serving 6442`（NVM），此后到采集结束（约 240 s）`[bluetooth]` 再无输出，
      且 `k60_power_result()` 的 `power=%u result=%d …` 一次没打印 ⇒ `qbt_boot()` 在窗口内没返回。
      （`k60_log` 只放行 level ≤ 3，`bt_dev_info` 是 level 6，被静音；判据力在缺 `power=` 行。）
    - 系统其余部分正常：132 行 SpringBoard、`bluetoothd`/`bluetoothuserd` 已起、`:1459` Server attached。
    - 下一张图：`qbt_boot()` 内每个阶段一条 level-1 行 + 一条硬超时保证 `power=` 一定打印。
28. **按 Lead 要求补齐的三段文档（2026-11-16 07:0x，无新镜像）**
    - §7.8 十一格矩阵重写：一行一格，四列 `SB / getBytes / armed / power` 全部在证据目录里
      重新数出（不抄旧结论），并列出每一格的证据目录名；末尾写清两条结论——**致命集 =
      {h1,h2,h3} 三者齐备**（去掉任一都能起），以及**0621 才是真凶，h1/h2/h3 只是让阶梯
      走到那一步**（三个 hunk 不写任何硬件地址，作用是把 `k60_bt_power_on()` 推到第四次
      `k60_map()`，撞穿全内核共享的 8 MiB `io_submap`）。
    - §7.11 增「两条修法的代价对照」表（0621 抬预算 vs 0513 搬窗口）：花什么、作用面、代价、
      归属四行，并写清**为什么先飞 0621**——它修缺陷本身、落在 main 上所有线受益、只有一行
      `#define`；0513 只是收窄蓝牙自身地址空间占用的整洁化项。
    - §7.12 的 d6 行改成确切配方：**全量 0511 + 0512 + 0621 + 0513**（= d5 的 233 条再追加
      0513，共 234 条），参数与 d5 一致（31 项 / 598 B），一次只加 0513；补 d6 纪律（series
      尾部追加 + `touch` + 放开「0513 与 0621 不同列」的测试不变式）与判读树（d6 起 ⇒ 两条
      修法等价、只用 0621；d6 死 ⇒ 0513 的 `KMA_DATA`/`VM_WIMG_IO` 有问题、删掉）。
    - 顺手修掉两处陈旧表述：§7.8 末尾「下一格是 h123+noboot 交叉格」改成 d 系列已收敛的实况，
      h3/h23/h34 三行的「结果」列写清它们是 stage 0 导致探针整段不跑（`[bluetooth]` 只有
      `:192` blob 一行），不是「卡在闸门」。
29. **d6 就绪 + baseline-20261116a 被旧构建输入镜像挡住（2026-11-16 07:0x–07:17）**
    - 0513 的 host 测试第 6 节从「两态」改成「三态」（提交 `17d0b7c`）：d5 = 有 0621、无 0513；
      d6 = 0621 与 0513 同在且 0513 在最后；两者都不在则 0513 只留在盘上。仍然非法的是
      「0513 不在最后」与「0513 前面不是 0512」。`TESTS OK 28 case(s)`。
    - d6 出图工具链已备好：`E:/k60-work/scratch/bt-s4/late2/prep-d6.sh`（有 build-strict 在跑时拒绝
      动手 → 校验 series 尾是 0512、0513 在盘且不在 series → 追加 0513 → `touch patches/xnu/series`
      → 提交），`wsl-build-d.sh` 已加 `d5`/`d6` 两个 case（d6 = TAG `bt-d6-iowin`，参数
      `k60bt=1 pong_bt_late=1`，31 项 / 598 B，series 234 条）。本线门禁 98 条 / 失败 0 / waiver 37。
    - **baseline-20261116a 构建失败与代码无关**：`logs/kernel.log` 只有六行，被 registry 拒
      （`❌ iron-4` / `❌ hard-33` / `❌ P-220 FAILED (failures=1)`）。按该次构建自己的 env
      （`K60_DEVICE_INPUT=/tmp/usb-cdc-mainline/device`、`K60_OUT=/tmp/k60build/out-baseline`）
      复跑完整 registry，红的是 iron-4 / iron-5 / hard-33 / P-165 / P-166，P-166 原文
      「只在仓库有 `0619`/`0620`/`0621`，只在输入有 `0507`/`0508`/`0509`」；
      `porting-gate.py --quick` 同 env 下 5 项阻断，前两条是 `0610-k60-metal-plugin- 未同步
      7235 vs 8324` 与 `series 仓库与构建输入一致 不一致`。
    - 三份镜像实测：`/opt/k60/trees/usb-cdc-mainline/device` 228 条 / mtime 2026-11-15 14:28:11、
      `/tmp/usb-cdc-mainline/device` 228 条 / 同一 mtime、`/opt/k60/trees/k60build/bt-device`
      233 条 / mtime 2026-11-16 06:28:46。⇒ 构建输入停在 series 还是 228 条的那天，
      所以门禁判的是「输入镜像落后」，不是「main 起不来」。修法是构建前用该次构建的
      `K60_DEVICE_INPUT` 跑一次 `sync-device-input.py` 再重建同 tag。
    - 教训（与本线 P-166 同族）：**同一台机器上多棵树/多条线各有一份 device 镜像时，
      「未同步」一定是相对某一份镜像说的；报红时先 `date -r <mirror>/patches/xnu/series`
      看它停在什么时候，再判断是镜像旧还是补丁集坏。**
30. **d6 图 bt-d6-iowin 出图（2026-11-16 08:13，Lead 批准走 B，只报事实不下结论）**
    - 配方：全量 0511 + 0512 + 0621（main 自带，P-219）+ 0513 在最后一条（前面是 0512），
      series **234 条**；参数 `k60bt=1 pong_bt_late=1`（31 项 / 598 B）；
      `K60_OUT=/opt/k60/trees/k60build/bt-out-s1c`、`K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device`。
    - manifest `/mnt/e/k60-work/artifacts/bt-d6-iowin/build-manifest.json`：boot_img
      `9f4e2a90c5b5bf6a656eab738d7038e4a6b8a3da2c5dcc5cce5c5896f2e7a3b3`（201,887,744 B）、
      kernel_built `020c7f04060790346ad6d1fa787b7bac1841768cc6acbbaa2b0f2c674f590eaf`
      （106,598,400 B）、payload_kernel `13a68ed4…`、payload `b2fe7b9b…`、adt `8bfc8066…`、
      series {234, `4305c6cc2821bcb7`, namespace `names+sizes`, file `b4c40d4e421e0dec`}、
      blob `febdc20d…`、dirty_files 0；`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments,
      598 bytes)`。
    - 构建后 series 保留 234 条（commit `4c5f8e0`）而不是抽回 233 条：P-165/P-166 的输入戳
      要与飞出去的图一致；镜像同步到 234 条后门禁 **98 条 / 失败 0 / waiver 37 / ✅ RC=0**。
      若把 0513 抽回 series，P-165/P-166 立刻转红（实测：只还原 series 不重建时红 2 条，
      再连同镜像一起抽回则红 5 条 iron-4/iron-5/hard-33/P-165/P-166）。
    - 判据由 Lead 给：d6 起且出现 `QCA controller version` 行 ⇒ 0513 可标 superseded；
      d6 silent 或 panic ⇒ 把 0513 拆成 gcc / tlmm / smmu 三个独立开关，一次只搬一个。
33. **Lead 回复（2026-11-16 11:16）：批准飞 d7，并派两件文档活（本轮完成）**
    - 飞行队列：wifi c7 → **bt-d7-obs** → adsp → modem，本线排第二。
    - 0514 的设计被认可，特别是「服务阶段恒 0、只绑启动路径」的边界；90 s 被肯定为
      当时选择了 90 s；这是历史选值理由。15:12 已撤回“600 段各等 10 s”的机制解释，
      以及用 command timeout=0 证明每段正常的推论；当前结论见 item 35。
    - 三处采纳并已成为规则（写进 S4-SPEC §7.16）：
      ① 「只加观测的补丁，测试必须断言它没有碰状态」——一个只加观测的镜像若死在设备上，
      唯一价值是「死因不是观测引入的」，这个前提必须由测试证明；
      ② 「分片下载 + 每片独立超时 = 没有总期限」——ADSP / modem 会遇到同一形状；
      ③ 跨文件 static 审计（`now()` 那类问题的系统性排查）。
    - 判据表加第四档（Lead 亲自加的）：「出现 `full: qbt_boot returned e=0` 但之后什么都没有
      ⇒ 不是蓝牙失败，是服务循环没被调起来」，要去看 `nw_wifi_step` 那类泵循环在蓝牙侧
      是否也存在。d5/d6 停在 `:726 addon: serving 6442 0` 之后没有下文，Lead 一直怀疑
      「下载完了但没人继续驱动它」。
    - MARCONI-AOP-GAP.md 结案，口径采用本线的：**内核侧 HCI 已通，用户态栈在 Pong 上被主动
      禁用，属上游设计缺口，不在本线范围**。
    - 下一步（Lead 明确「不用等他」）：(a) 把「只加观测必须断言没碰状态」落进通用节；
      (b) 把十一格二分的最终解释单独成节，作为「单变量二分」的可照抄方法。
    - 本轮据此新增 **S4-SPEC §7.16**（两条通用规矩 + 跨文件 static 审计结果）与
      **§7.17**（单变量二分五步法 + 「二分给范围、panic 给机制」）；§7.15 判据表补第四档。
31. **d6 实飞：0513 与 0621 等价，0513 标 superseded（2026-11-16 08:54–08:59）**
    - 证据 `E:/k60-work/evidence/usblog-20261116-085439`（boot_img `9F4E2A90…7A3B3` =
      `bt-d6-iowin`）：`bootAccepted` true / exit 0 / returnedToFastboot false；
      capture `captured-budget-complete`、bytes 240,620、stopReason `budget`、panicMarker null；
      console.log 3,440 行、sha256 `1BCF8490…D1577`、SpringBoard **132**、`getBytes:range` **0**、
      panic 标记 0、心跳 17 条。
    - 阶梯 16 行 `[bluetooth]`：`:487` 新增 `full: windows mapped, gcc/tlmm/smmu charged to
      kernel_map`（0513 生效的直接证据），`:488`–`:496` SMMU 旁路 / dma / uart pins / qbt_boot
      enter 与 d5 一致，`:709` `QCA controller version 0x12110201`、`:710`/`:726` 两个固件分片
      （146068 / 6442）都被取走；d4 在同一位置必现的 `kmem_alloc(…, 1048576, 0x100021): failed
      with 3` 一次没有。
    - **结论**：0621（抬 IO_MAP_SIZE）与 0513（把 BT 三窗口搬出 io_submap）等价，0513 属整洁化项
      —— **文件保留、移出 series**，随 0621 一起收口。
    - 仍缺：`power=1 result=…` 行依旧未打印（`qbt_boot()` 停在 NVM 之后、`qca_set_bdaddr`
      之前）；userspace `:1487` marconi-bt 匹配不到 device tree 服务、`:1499` 只有
      `ee:98:c5:8a:6b:4e`。前者是本线下一张图的阶段日志，后者是 Lead 的 ADT 工作。

32. **0514 观测补丁与 d7 图（2026-11-16 09:48）**
    - 触发：d5 / d6 都停在 `qbt_boot()` 内部（rampatch 与 NVM 都被取走），但
      `[bluetooth] power=…` 行始终不打印。Lead 批 A：只加观测，不改状态机 / 时钟 /
      SMMU / 窗口 / `board.toml`。
    - 当时的动机是 `qbt_boot()` 没有整体期限，而每条命令有 10 s `QBT_COMMAND_TIMEOUT`。
      **15:12 更正**：段错误会 `goto out`，并非超时后继续下一段；撤回“600 多段各超时可耗上小时”。
      90 s 是当前观测预算，检查依赖返回 `run()`，不能抢占阻塞回调；不能由 timeout=0 证明预算足够。
    - 0514 内容：`QBT_BOOT_BUDGET 90000000000ULL` + `struct qbt.boot_deadline` +
      `run()` 里的预算检查（超预算打印 `boot: budget exhausted at op=0x…` 并返回
      `-ETIMEDOUT`）+ 单条超时打印 `boot: command timeout op=0x…` + 12 条 level-1
      阶段行（enter / soc version / set speed / uart setup / rampatch / nvm / hci reset /
      bdaddr check / set bdaddr / return / full: qbt_boot returned）。
    - 边界由 host 测试守住：`scripts/tests/test-k60-bt-0514-boot-observability.py`
      33 例，断言只删了 `run()` 那一行、新增行不含 `k60_map` / `ml_io_map` /
      `k60_gcc_set_se_rate` / `k60_smmu_bypass` / 任何既有开关字段；孪生
      `patches/bt/0008` 字节相同。
    - 首建失败一次：`qbt_linux.c:97: error: call to undeclared function 'now'` ——
      `now()` 是 `qbt_core.c` 里的 static，改成 `q->ops.now_ns(q->ops.context)` 后通过。
    - d7 图 `bt-d7-obs`：series 234（尾部 … 0512 / 0514），参数
      `k60bt=1 pong_bt_late=1`（31 项 / 598 B）。判据见 S4-SPEC §7.15。
    - 新增文档 `docs/research/bt/MARCONI-AOP-GAP.md`：marconi 是 AOP/SPU 控制通道
      （`AppleA7IOPV2Marconi` / `AppleR5IOPT8006` / `AppleSPUMarconiControl`），
      Pong 的 `board_services18.py:84-89` 故意用 `_LimitLoadToDeviceTree` 挡掉
      `bluetoothd` ⇒ 用户态栈属上游设计缺口，不在本线范围，别再补 ADT 节点。

### 34. 跨线通用文档 BISECT-METHOD.md（2026-11-16 12:40）

Lead 回复 #12 第五项：把 S4-SPEC §7.17 的「单变量二分五步法」提炼成跨线文档
`docs/engineering/BISECT-METHOD.md`，给 adsp / modem / wifi 直接引用。边界：只写方法，
不写任何一条线的硬件结论；三个反例只引用已有提交号与 evidence 路径，不新增观测。

- 新文档 **`docs/engineering/BISECT-METHOD.md`**（6,229 B / 114 行）：五步
  （① 变量定义清楚 + 单块补丁 + 字节级等式 ② 判据先写死再飞 ③ 每格都飞、飞过的要能查（P-218）
  ④ 中途结论必须能被下一格推翻 ⑤ 矩阵收敛后别停在「谁是真凶」）+ 第 0 步前置
  （拆编译单元先查跨文件 static）+ 三个反例（各按「原结论 / 依赖哪几格 / 哪一格推翻了它」写：
  「h2 是必要条件」被 h2 单格 `usblog-20261116-044817` 推翻；「致命集是 h3×h4」被 h34
  `usblog-20261116-014536` 与 h123 `usblog-20261116-043650` 推翻；「致命集必须含 h4」
  被 h123 silent + h34 能起两个方向同时推翻）。
- 登记：`docs/INDEX.md` 的 engineering 表 + `docs/engineering/README.md` 的「现状与流程」表各加一行。
- S4-SPEC 同步两处：§7.16 第 0 条把「修一个 static 引用必须顺带做同名审计」**升格为通用规矩**
  （Lead 2026-11-16 定，P-204 的另一种形状）；§7.17 开头加引用块指向通用文档，本节保留本线的
  具体数字与 evidence 路径。
- check-docs 202 项 ✅（新文档被 INDEX 与 engineering/README 双登记）。

### 35. d7 实飞：NVM 路径遇全局预算，根因未定（2026-11-16 15:12 更正）

Lead 飞了 `bt-d7-obs`（boot.img `76a4260bc762a22a3dc683e4042a0a13a8dea41f04defccede8f9a96719c7512`），
证据 `E:/k60-work/evidence/usblog-20261116-130444`（console 3,180 行 / 221,001 B、SpringBoard 132、
panic 0、stopReason budget）。稳定事实：rampatch 返回、NVM 路径开始，90 s 全局预算先被观察到，
最终 `power=1 result=-60`；蓝牙启动失败，原因未定。完整阶梯见 S4-SPEC.md §7.18。

- `:2044 boot: budget exhausted at op=0xfc00 waiting=1` 中 `0xfc00` 是 `EDL_PATCH_CMD_OPCODE`，
  `waiting=1` 是布尔状态，不是等待次数；这不能区分控制器未应答、事件不匹配或 TX 排空。
- **撤回**“NVM 第一段卡住”和“command timeout=0 证明每段正常、只是慢”两种结论。
  `run()` 先判断 boot_deadline，再判断命令 deadline；pump/wait 阻塞跨过两个期限时只打印 budget。
  因此 timeout=0 不能排除卡住。d7 没有逐段计数，6,442 B / 243 B 得到的约 27 段只是理论数，
  65 s ÷ 27 = 2.4 s/段不是测量。两次 `serving 6442` 包含 fallback，预算耗尽后重试可立即失败。
- 慢、阻塞、事件不匹配、TX 排空仍未判定；不据此预做 d9。d8 的判读口径见 §7.18：
  sent/acks 是 boot 累计，按 PATCH/NVM/fallback attempt 的基线与 done 行取差；失败尝试不算完成，
  缺失基线需标不确定，且日志自身会扰动耗时。

### 36. d8 配方与保留产物：0515 逐段观测（2026-11-16）

0515 仅在原 `qca_tlv_send_segment()` 调用返回后打印 i/size/dt_ms/e/sent/acks，
每次下载结束打印 type/segs/计数/final/ret，power 行附全局计数；不改调用参数、预算、段长、
下载模式、状态机、时钟/SMMU/窗口或 `board.toml`。

- 补丁 `patches/xnu/0515-k60-bt-tlv-counters.patch`（2,727 B，+38/−4），sha256
  `120c4d57d1bf72bdee18770a520367bd68d46c1c96ffb185c5bbf51ec46c4cd6`；孪生
  `patches/bt/0009-k60-bt-tlv-counters.patch` 字节相同。原 234 条重放 BAD=0 后单独 apply 成功。
- 保留产物 `bt-d8-tlv`（2026-11-16 13:56:24）：series 235，namespace `names+sizes`，
  指纹 `f7aa7d63470b891d`，file `9a2cfd416b5250854f8fda38d03ca095a631be296e0679bf9522ba445e73cbb8`；
  参数 `k60bt=1 pong_bt_late=1`，真实 payload 31 项 / 598 B，原 head `91dcd07`、dirty 0。
  boot.img sha256 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`（201,887,744 B），
  kernel_built `6c96f7ccd641d0f751cd76669312c7279055e3232415d5b2d505b28c38065331`（106,598,400 B）；
  manifest `E:/k60-work/artifacts/bt-d8-tlv/build-manifest.json`，sha256
  `3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0`。不重建、不追改旧 manifest。
- 15:28 本树离线复核：0515 host 28 cases、0514 host 33 cases 均为静态契约检查，
  verify-boot-image 与真实 image 参数审计通过（31 arguments, 598 bytes）；详见
  `E:/k60-work/scratch/bt-s4/d8-evidence-20261116.log`。
- 账本改为当前 d8 纯观测 active；⑦三类离线证据已核实，⑧已记录 Lead 的设备观测结果。
  README 双语表由生成器更新。默认 `python3 scripts/eight-step-gate.py --flash` 实际列出
  7 项（touch, gpu, storage, display, bootchain, bluetooth, battery），56 项通过、RC=0；
  记录 `E:/k60-work/scratch/bt-s4/d8-flash-gate-20261116.log`。未改 gate 或绕过 done=false。
  旧产物原 eight-step.log 只有 6 项 build 检查，不追认其包含 BT；本次是后补的本树核验。
- 判读前提：按 PATCH/NVM/fallback 的 type/attempt 分开；日志发生于段调用返回后；
  ret 非零不算完成，segs 包括失败尝试；累计计数需取差，final 状态必须结合 done 行。
  耗时仅代表 d8 并受日志成本影响。d7 result=-60 保留为功能失败；d8 观测完成但初始化失败，
  本线不操作设备，也不预做 d9。

### 37. d8 实飞结果：NVM 未完成，暂停 d9（2026-11-16 16:58）

证据 `E:/k60-work/evidence/usblog-20261116-164726/console.log`（3,749 行 / 255,020 B，sha256 `1ef1f5abf55f6036f36c729779aab3de53f667e782e9ba3492fb332109be7cd2`），`boot.json` 为 `bootAccepted=true`、`exit=0`、未回 fastboot；`capture.json` 为 complete、无 panic/reset marker。只用 `fastboot boot`，未 flash。

- PATCH type=1：602 次调用全部 `e=0`，`sent +602`、`acks +1`，段大小合计 146,068 B，`done segs=602 final=0 ret=0`。
- NVM 首次 type=2：7 次调用，前 6 次 `e=0`（dt_ms 10000/10000/10000/10001/10001/10001），第 7 次 `e=-60` / 15 ms；`sent +7`、`acks +6`，`done segs=7 final=0 ret=-60`。
- NVM fallback type=2：21 次调用，前 20 次 `e=0` / 0 ms，第 21 次 `e=-60` / 16 ms；`sent +21`、`acks +21`，`done segs=21 final=1 ret=-60`。
- 最终 `qca/hpnv21g.bin (-60)`、`qbt_boot returned e=-60`、`power=1 result=-60`；无 `nvm done`。系统继续到 SpringBoard，蓝牙初始化失败。`e=0` 仅表示该软件调用返回，不能等同控制器接受；`serving 6442` 没有文件名/哈希，不能证明 fallback 内容相同。

`run()` 先 pump/step、错误与完成谓词，再判 boot deadline、命令 deadline；完成谓词可先于过期检查返回，budget 又可遮住 command timeout。`acks` 包括非零 status 的 report，`final=1` 是最后 status，不是确认数；`dt_ms=0` 为整毫秒截断，不能写零耗时。详见 S4-SPEC.md §7.20 的源码与日志锚点。未知项仍包括设备确认、晚到/缓存响应、重试语义与具体等待路径；现有日志不能区分。保留独立 reassessment 的历史 HOLD，不把 observation-only 当功能成功。下一步仅提请批准宿主时序模型/测试（complete、两期限、ACK/status、fallback 重置）；当前不实现模型或新观测，不抬预算、不改下载模式/分片/状态机/地址，不预做 d9、不再上机。

### 38. d8 宿主时序模型：已证明的软件事实与 adapter/fallback 方案（2026-11-16 18:58）

Lead 的 `test/bt-d8-timing-model` 已交付：代码 `0ccdfbba5ab626bf99be65d973e45b87e389f59c`、文档 `a1858958ccb4a5b84d44c2eaac643b4b614ca32f`、台账 `bce47bf99415e7d4418f9f48f8d2a48eb4b0d22a`，分支 HEAD = origin，未合 main、未打 tag。宿主模型抽取真实 `qbt_core.c`，以假时钟/pump/ops 执行 `event` / `qbt_step` / `run` / `qbt_command`；34 场景 / 84 断言 / 8 个输入拒绝守卫，`rc=0`，17 个回归夹具全过，输入身份 `RECORDED_INPUTS_MATCH`。

**宿主模型已证明的软件事实**（详见 `docs/research/bt/S4-SPEC.md` §7.21）：

- `run()` 顺序：pump/step → 错误 → 完成谓词 → 全局 boot deadline → 单命令 deadline；两处比较都是 `>=`。阻塞跨过两者时 budget 先返回，command-timeout 行可被隐藏。
- 睡眠/等待被夹到命令期限，但不夹到全局 boot 期限；晚到事件只要在期限检查前满足完成谓词，仍可返回成功。
- 全局 TLV `acks/final` 自增与“是否匹配本次等待”无关；非零 status 的 ack 不置 `complete`；同 opcode 旧事件可完成新的等待；新命令清 `complete` 但保留预算与统计。
- 0515 的 `dt_ms` 为整数截断，失败调用也计入 `segs`。

**d8 计数分组仍是设备观测**（§7.20）：PATCH 602/602 次 `e=0`，NVM 首次 7 次（6 次 `e=0`、末次 `-60`），fallback 21 次（20 次 `e=0`、末次 `-60`），合计 630 次；两次 NVM 均 `ret=-60`。宿主模型没有 replay d8 时间戳，不能把任何机制升级成硬件结论。

**仍是 UNKNOWN**：控制器逐段接受/完整 NVM、UART/DMA/IBS 时间线、真实 RX 时刻、晚到/缓存响应、重试语义、首次 NVM 约 10 s 与 fallback 快速 `e=0` 的具体机制、两次 `serving 6442` 内容是否相同、编译产物到 payload 对应、flash 门禁与硬件行为。

**方案已被 Lead 批准并实现**：见 item 39 与 `docs/research/bt/S4-SPEC.md` §7.22。

### 39. d8 adapter/fallback 宿主证据已交付（2026-11-16 20:53）

Lead 于 19:31 按 §7.22 原范围批准（3 行被测层表 + A/B/C 场景矩阵 + 六条负向控制，不扩），只允许 test-only 与 docs-only 提交。本线已交付：

- test-only 提交 `916aaaa552b8470fa63b992dac2a525226b7288d` "test(bt): host-test the d8 adapter and fallback"，3 文件 +1156：`scripts/tests/test-bt-d8-adapter-host.py`、`scripts/tests/fixtures/bt-d8-adapter-harness.c`、`scripts/tests/fixtures/bt-d8-adapter-support.c`。未改运行代码、series、`board.toml`、预算、下载模式、段长、状态机或地址。
- 运行 `python3 scripts/tests/test-bt-d8-adapter-host.py`（默认读取保留产物 `/mnt/e/k60-work/artifacts/bt-d8-tlv`）：`RAW_RC=0`，`TESTS OK: 90 case(s), 0 failure(s)`；日志 `E:/k60-work/scratch/bt-s4/late3/run17.log`。90 = 19 输入绑定 + 3 源码重建 + 22 场景各 2 项 + 24 变异孪生。
- 场景：A 组 8（status/short/timeout/TLV status/late/early/version mismatch/version overlong）、B 组 8（完整下载/fallback 成功/fallback 失败/NVM 缺失/patch fallback/skip/alt 已是 .bin/alt 改名）、C 组 6（成功/失败清理/fallback 成功/patch 失败/bdaddr 失败/reset 失败）。24 个变异孪生全部真红后才退出 0；例：`firmware_release_count` 红行 `patch and NVM buffers are each released once: requests=2 puts=0`，`version_overlong_exact` 红行 `overlong version payload is -EILSEQ: 0`。
- fail-closed：manifest 追加一个换行后运行即 `REFUSED: manifest bytes differ from the retained d8 manifest`，退出码 2；不 fallback 到 latest，不读当前工作树。源码身份用三条重建后哈希钉住（qbt_core `e3405ca4…`、qbt_linux `a0ec555a…`、btqca `ecc7346f…`），235 条 series 的补丁字节、frozen-before/after、head `91dcd07`、boot.img `0297012d…` 任一不符都拒绝。
- 断言级重叠表已写入 S4-SPEC §7.22：本仓对完整 `qbt_linux` adapter、`qca_download_firmware` fallback/缺失/skip/alt/release、`qca_set_bdaddr` 与 `qbt_boot` 生命周期权威；Lead 的 `test-bt-d8-host-timing.py` 对 `run()`/期限/调度器微时序权威，本线不编辑该文件，也不复制其断言。两边进入 main 或 ⑦ 前由 Lead 决定哪些断言退休，不保留长期分叉。
- 仍未覆盖：控制器/UART/DMA/IBS、真实 d8 时间线、90 s 预算分支、firmware vmalloc 失败、`qca_disable_soc_logging` 失败、NVM 内容相等、payload 对应、flash 门禁、d8 物理机制与蓝牙可用。

状态：test-only 与 docs-only 分开提交；本次未重建、未再上机、未预做 d9，d8 产物未改。21:26 Lead 已给出裁决，见 item 40。

### 40. 21:26 Lead 裁决：一条断言一个 owner，§7.22 可作 ⑦ 补充证据，d9 未批准（2026-11-16 21:26）

Lead 在 `E:/k60-work/scratch/reply-bt-20261115.md` 裁决，并独立复核远端 `2104231a` 干净、重跑本线测试得 `TESTS OK: 90 case(s), 0 failure(s)`、`rc=0`。

- **权威分区**：核心微时序归 Lead 的 `test-bt-d8-host-timing.py`（`run()` 顺序、两期限 `>=`、精确期限注入、调度器夹取、`dt_ms` 截断、0515 wrapper 汇总）；adapter/下载/生命周期归本仓（完整 `qbt_linux` wake/skb、`qca_download_firmware` 的 fallback/缺失/skip/alt/release、`qca_set_bdaddr`、`qbt_boot`、22 场景、24 变异）；三条共享语义（TLV ack/final、`sent/acks` 累计、fail-closed 拒跑）保留在本仓，Lead 只保留两条 core 断言（全局 ack/final 独立于当前等待、stale 同 opcode 可完成新等待）。§7.22 已按此重写为“一条断言一行 + owner + 引用位置”的表，并列出请 Lead 退役的重复 ack/final 计数断言。
- **输入身份**：两边可短期并存，进 main/⑦ 前只留一份；Lead 倾向 `check-bt-d8-inputs.py`（它钉 boot.img、235 条 series 字节与 namespace），本仓保留部分应缩成“调用 Lead 检查器 + 本仓三条重建源码 SHA”，不再维护第二份身份实现。
- **§7.22 的 ⑦ 地位**：可作 ⑦ 的补充证据，但不能满足 ⑦ 本身；进入 ⑦ 需同时具备 artifact_check（飞行 payload 内核里有 `[bluetooth]` 的具体行）与 manifest→payload kernel 映射。两项只读候选证据已写入 §7.22：`logs/kernel.log:218/251/252` 是 0500/0514/0515；从 boot.img 的 payload FAT 抽出的 kernel sha256 `72793ffd…` 等于 manifest `payload_kernel`；payload `strings -a` 的 `[bluetooth]` 在 10907/11010；`verify-boot-image.py --manifest …` 得 `OK`。账本未改，等 Lead 复核后决定是否写入 ⑦。
- **⑧ 固定边界**：不得因为 90 个宿主用例变绿就改 ⑧；d8 仍是失败观测（两次 NVM 均未完成、`result=-60`、蓝牙不可用），⑧ 的 `done=true` 只表示“设备观测已取得”。
- **d9**：未批准。先交 `docs/research/bt/D8-NEXT.md`，列三个候选判据（HCI 层 NVM 完成标志、控制器 exec_env/MHI 状态、真实 RX 字节时间线），逐条写“需要什么观测、能排除什么、不能排除什么”，由 Lead 选单变量；在收到裁决前不重建、不上机、不改预算/下载模式/段长/状态机/地址。

状态：两项交付（权威分区表 + `D8-NEXT.md`）已落盘，待 Lead 复核；test-only 提交 `916aaaa` 与 docs 提交 `56e3c73`/`2104231a` 已在远端。`E:/hackios/k60-work/scratch/bt-s4/d8-evidence-20261116.log` 的 90 用例证据与本次只读 artifact 核对均未启动设备。下一步：Lead 对断言退役、⑦ 写入与 d9 判据的选择。

### 41. 0516 UART clock 候选已构建（2026-11-17 01:47）

用户 2026-11-16 确认 BT 子目录接受 GPL-2.0，要求按最快路径修复；本线把 QcaBluetooth `986d631`（fix: send control bytes queued behind a stopped UART clock）作为唯一移植对象，未改 90 s budget、10 s command deadline、243 B 段长、`dnld_mode`/type、状态机、时钟/SMMU/窗口或 106 文件固件。

- 补丁提交 `13fdf711` "fix(bt): port QcaBluetooth UART clock fix"：`patches/xnu/0516-k60-bt-qbt-uart-clock.patch`（135 行，4 文件 +35/-10，sha256 `0134a31b…`）与 series 追加；`986d631` 上游为 5 文件 +82/-14，本树只取 4 个源码文件。control 字节也拉时钟、`clock(false)` 内收到 wake 重新开钟、拒写按 `QBT_TX_POLL` 退避并计 `tx_refused`、`qbt_deadline` 返回 `write_retry_at`、`qbt_fail`/`qbt_shutdown` 清零。
- test-only 提交 `1a9ede4e` "test(bt): host-test the 0516 UART clock fix"：`scripts/tests/test-bt-0516-uart-clock.py`（81 cases）、`scripts/tests/fixtures/bt-0516-clock-harness.c`（`clock_wake_in_stop`/`clock_refused_write`），并让 d8 adapter runner 只取 235 条前缀；`test-bt-0516-uart-clock.py` 得 `TESTS OK: 81 case(s), 0 failure(s)`，4 个源码变异全真红；d8 adapter 仍 `90 case(s), 0 failure(s)`，0514 33、0515 28。
- docs 提交 `32243230` "docs(bt): scope the 0516 UART clock candidate"：账本蓝牙块切到 `bt-0516-uart-clock` 候选范围；README/README_EN 由 `render-eight-step-table.py --apply` 再生成，默认 ⑦ 显示 Ready to flash 只表示离线通过，⑧ 仍 false。
- 构建：`K60_OUT=/opt/k60/trees/k60build/bt-out-0516`、`K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device`、`K60_EIGHT_STEP_ITEMS=bluetooth`；`scripts/build-strict.sh bt-0516-uart-clock --fd .../bt-d8-tlv-cf4485712c29.fd --bt-blob .../pong-bt-firmware.bin --kernel-arg k60bt=1 --kernel-arg pong_bt_late=1`，`RAW_RC=0`。manifest `built_at=2026-11-17T01:47:01+08:00`、head `32243230`、dirty 0、series 236、namespace `a56a29e329161163`、frozen `dc714e29…`。
- 产物：boot.img `8a211a76…`（201887744 bytes）、kernel `dd9cbbd6…`、payload `ad412eb7…`、payload_kernel `04a9f928…`、ADT `0e7a6fbc…`、dtb `2d044eaa…`、fd `cf448571…`、bt_blob `febdc20d…`；kernel.log:253 有 0516 patch，八步 build 6 项通过，check-image-args 31 arguments/598 bytes、kernel archives 4 个全在、metal/bt blob container self-consistent、`verify-boot-image.py --manifest ...` → OK、boot.json `hardware_tested=false`。
- 边界：这是 HOST-ONLY + 离线构建证据，不证明控制器 UART/DMA/IBS、真实 NVM 完成、蓝牙可用；0516 未上机，仍需 Lead 批准 d9；d8 的 PATCH 成功、两次 NVM 失败、`result=-60` 不变，⑧ 不改。

### 43. d9 实飞：0516 仍失败（2026-11-17 12:03）

用户 11:56 明确授权后，按 D9-PLAN 只执行一次 `fastboot boot E:/k60-work/artifacts/bt-0516-uart-clock/boot.img`，未 flash、未写 persist/sda38。证据目录 `E:/k60-work/evidence/usblog-20261117-115842`：boot.img `8a211a76…`，boot.json `bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`；capture.json `complete=true`、`bytes=282532`、panic/reset null、`stopReason=budget`。console 与 d8 同形：PATCH `segs=602 ret=0`，NVM 第一次 `segs=7 ret=-60`，fallback `segs=21 ret=-60`，`power=1 result=-60`，无 `nvm done`。按预声明判据判 **FAIL**；0516 不能作为修复，下一步需要新的控制器/UART 观测或新的单变量候选，不能直接改预算/段长掩盖。

### 42. d9 单变量飞行计划已准备（2026-11-17 02:00，未批准）

新增 `docs/research/bt/D9-PLAN.md`：候选 `E:/k60-work/artifacts/bt-0516-uart-clock/boot.img`
（sha256 `8a211a7608186990951a94a6c26b04dc0c1d4ea53ab937cbcfb55d8acc447095`，201887744 B）
对回滚基线 d8 `E:/k60-work/artifacts/bt-d8-tlv/boot.img`（`0297012d…`）；唯一变量为 0516
（135 行，4 文件 +35/−10，`0134a31b…`），不改 90 s budget、10 s deadline、243 B 段长、
下载模式、状态机、地址或固件。`eight-step-gate.py --flash` 默认 7 项/56 项通过、RC=0
（日志 `E:/k60-work/scratch/bt-s4/0516-flash-gate-20261117.log`），`verify-boot-image` OK，
check-image-args 31/598 OK。计划预先写死成功判据（镜像哈希、boot 接受、无 budget exhausted、
NVM `ret=0`、`power=1 result=0`）与失败判据（budget exhausted、NVM `-60`、power `-60`、
panic/reset、哈希不符），并明确成功也只证明传输/下载路径，不证明蓝牙可用。d9 未批准；
（历史，d9 轮）bt-agent 不开机、不刷机，只由 Lead 执行或明确授权。2026-11-18 起按先到先得规则，见 item 46。

### 44. 0517 上电顺序候选已构建（2026-11-18 16:47，未上机）

- 0517 只对齐官网顺序与 100/60 ms：BT_EN 低 100 ms → 串口时钟 → QUP/engine → UART/wake IRQ → XO pulse/BT_EN 高 → 60 ms → 引脚；不改 budget、10 s deadline、243 B 段长、下载模式/type、状态机、地址、SMMU 或固件。补丁 `patches/xnu/0517-k60-bt-power-order.patch` 64 行/3 hunk，sha256 `ebd0fe35…`；series 237 条（`3339e34f…`），前 236 行仍 `e7de3927…`。
- 真实源码 base 是 2235 行，不是首版误用的 1267 行：由 0500→…→0515 逐条应用 `bsd/dev/qbt_k60.c` 得到 `35887d2f…`，应用 0517 后 `4a3947d5…`，仍 2235 行；首版在真实 series 上 `git apply` 失败，已重生成并重跑测试。
- 构建：`K60_OUT=/opt/k60/trees/k60build/bt-out-0517`、`K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device`、tag `bt-0517-power-order`，`RAW_RC=0`；manifest `built_at=2026-11-18T16:47:01+08:00`、head `2c7d948d`、dirty 0、series 237、frozen `2aaa4903…`。
- 产物：boot.img `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`（201887744 B）、kernel `c40e4277…`、payload `9acde534…`、payload_kernel `a44053e4…`、ADT `db998204…`、dtb `2d044eaa…`、fd `cf448571…`、bt_blob `febdc20d…`；kernel.log:254 记录 0517，八步 build 6 项通过，image-arg-audit 31/598，kernel archives 4 个全在，metal/bt blob self-consistent，`verify-boot-image.py --manifest` → OK，boot.json `hardware_tested=false`。
- 宿主：0517 测试 52、0516 测试 82、d8 adapter 90，全绿；均 HOST-ONLY，不证明控制器/NVM/蓝牙可用。
- 边界（截至 16:47 的历史记录）：0517 当时未上机。d10 后于 21:32 飞行 FAIL，见 item 46；回滚 d8 `0297012d…`，上一候选 d9 `8a211a76…`。

### 45. 0518 GIC INTID 候选已构建；d8/d10 回滚镜像已恢复（2026-11-18 18:08，未上机）

- 0518 只修一个具体缺陷：`armcpu_spi_attach(uint32_t intid, ...)` 要的是 GIC INTID，旧代码却直接传 DT 的 SPI 587（UART）和 208（TLMM wake）。新增 `K60_BT_UART_GIC_INTID=(32u+587u)`=619、`K60_TLMM_GIC_INTID=(32u+208u)`=240，四个调用点（`k60_gic_mask`、`armcpu_spi_mask`、两处 `armcpu_spi_attach`）全部改用 INTID。附依据：`drivers/ArmCpu/ArmCpu.cpp:784-814` 直接拿 `intid` 写 ISENABLER/IROUTER/ICFGR 并拒绝 `<32`；UFS/PCIe/pong 的既有调用者都是 `SPI+32`。0518 不改 0517 的上电顺序/100-60 ms，也不改 budget、10 s deadline、243 B 段长、下载模式/type、状态机、SMMU、地址或固件。
- 候选身份：补丁 `patches/xnu/0518-k60-bt-gic-intid.patch` 51 行/2,280 B/4 hunk，sha256 `c1e2cb96ac79b26089e4a495741165d800ee8e730b0a460ab2e476853809e13f`；base（post-0517）`4a3947d5926d8a636d29d914530509cdf7208ed46fcb3e2022002798e8792b0e`（2235 行），applied `4a1a4e269fce5f2bf3d964f8610d3c7943f3329aed2dce2da681dd45705ef5fb`（2239 行）。series 238 条，全文件 `4a39a8d2fddf0da93dbcab18a2302c69bab8f34955d56e9172c1a395e8b12e11`，前 237 行 `3339e34f…`，前 236 行 `e7de3927…`。
- 构建：tag `bt-0518-gic-intid`，`built_at=2026-11-18T18:08:47+08:00`，head `3aa6910a`、dirty 0；manifest boot `d6beec4c6bfbb09c1d11076db0239ead0ee357dd2ba58bfb4f92a69c9d7158ec`（201,887,744 B）、kernel `6f44a07f…`、payload `1a6cf06f…`、payload_kernel `46da4e24…`、ADT `4b91e549…`、dtb `2d044eaa…`、fd `cf448571…`、bt_blob `febdc20d…`；kernel.log:271 记录 0518，八步 build 6 项通过，image-arg-audit 31/598，kernel archives 4 个全在，metal/bt blob self-consistent，`verify-boot-image.py --manifest` → OK，boot.json `hardware_tested=false`、`kernel_sha256=83b52b56…`。
- 宿主：0518 套件 35、0517 套件 53、0516 套件 82、d8 adapter 90，全部 0 failure；均 HOST-ONLY，不证明控制器/UART/DMA/IBS、真实 NVM 完成或蓝牙可用。
- 回滚恢复：d8 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b` 与 d10 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69` 已按各自 manifest 用“0518 donor 镜像 + 对应 payload”重组，两枚均 201,887,744 B，`verify-boot-image` 与 image-arg-audit 均 OK。d9 `8a211a76…` 仍不可用，不得声称保留；d8 产物目录保持不动。
- 计划：`docs/research/bt/D11-PLAN.md` 已写明 d11 是 0517+0518 累积候选，**相对 d10 的唯一差别是 0518**；权威顺序是先 d10、后 d11。（历史，截至 18:08；d10 21:32 FAIL、d11 22:19 PASS，见 item 46/47。）

### 46. d10（0517）已飞，FAIL（2026-11-18 21:32–21:36）

- 权限口径：按用户 2026-11-18 更新的“先到先得、统一 supervisor、单设备单写者”规则，在没有其他 supervisor/collector 占用时由 bt-agent 执行；只 `fastboot boot`，未 flash。
- 镜像：`E:/k60-work/artifacts/bt-0517-power-order/boot.img`，sha256 `6c631bc4…`；设备 `6033dbec`；supervisor rc=0。
- 采集：`E:/k60-work/evidence/usblog-20261118-213228`；bootAccepted=true、exit=0、returnedToFastboot=false；capture complete=true、bytes=201732、panic/reset=null、stopReason=budget；console 3290 行，logSha256 `6A9AF54A…`。
- 判决：PATCH `segs=602 ret=0`；NVM 主轮 `segs=7 ret=-60`（i=0..5 每段约 10 s）；fallback 这次 `segs=1 ret=-60`；`budget exhausted at op=0xfc00`；`power=1 result=-60`；无 `nvm done`；`bluetoothd exit=1`。按预声明判据 **FAIL**。
- 形状：主轮仍是 7 段/每段约 10 s，但 fallback 从 d9 的 21 段变成 1 段，**不能说失败形状完全不变**，也不能说 0517 完全无效。
- 下一步：d11（0517+0518）已于 22:19 飞行 PASS，见 item 47；NVM 问题由 0518 的 GIC INTID 修正解释，不再需要先补观测。

### 47. d11（0518）已飞，PASS：蓝牙固件下载路径打通（2026-11-18 22:19–22:23）

- 权限口径同 item 46：先到先得、单设备单写者；只 `fastboot boot`，未 flash。设备 `6033dbec`，镜像 `d6beec4c…`（201,887,744 B），supervisor rc=0。
- 采集：`E:/k60-work/evidence/usblog-20261118-221925`；bootAccepted=true、exit=0、returnedToFastboot=false；capture complete=true、bytes=278123、panic/reset=null、stopReason=budget；console 278123 B，logSha256 `591CD9A6…`。
- 蓝牙：PATCH `segs=602 ret=0`；NVM 单轮 27 段，26 段 `dt_ms=1`、末段 124 B `dt_ms=120`，`segs=27 sent=629 acks=28 final=0 ret=0`；`nvm done`、`hci reset done`、`bdaddr check done`、`uart setup done e=0`、`set bdaddr done e=0`、`return e=0 baud=3000000`；`power=1 result=0 ... firmware=BTFW.HSP.2.1.0-00570-PATCHZ-1`；`[bluetooth sk] ctl_register com.apple.uart.sk.bluetooth error=0`。
- 因果：d11 相对 d10 唯一差别是 0518。此前 UART RX 中断挂在 INTID 587 而不是 619，每段 ack 只能等 10 s 命令期限；0518 修正后 ack 约 1 ms 到达。**0518 是修复，0517 不是。**
- 边界：只证明 patch/NVM 下载、HCI reset、BD_ADDR 设置与 UART SK 注册；用户态 `marconi-bt` 仍报 `Unable to match bluetooth service in device tree` 和全零 MAC，`bluetoothd` 已由 `xpcproxy` 拉起但只进入 msg loop。蓝牙可用性仍未证明。

### 48. d12（0519+0520）观测飞行：BlueTool 在打开传输前被 30 s 看门狗杀死（2026-11-19 00:02–00:06）

- 与 d10/d11 不同，d12 是观测候选：0519 增加 `/dev/btreset`、`/dev/btwake`、`/dev/btpoweroff` 三个探针字符设备（open/ioctl 一律返回成功）并把 `K60_BT_TRANSPORT_SPEED` 改成 3000000；0520 增加 `com.apple.uart.bluetooth` 控制别名（stock BlueTool 的默认名）和 `K60ARG` argv 追踪。不改下载/时序/状态机。
- 权限口径同 item 46/47：先到先得、单设备单写者；只 `fastboot boot`。设备 `6033dbec`，镜像 `9361ec1c…`（201,887,744 B），supervisor rc=0。
- 采集：`E:/k60-work/evidence/usblog-20261119-000246`；bootAccepted=true、exit=0、returnedToFastboot=false；capture complete=true、bytes=264656、panic/reset=null、stopReason=budget；console `2A5E3FA9…`。
- 探针生效：`:1349` UART.SK 注册 error=0（speed=3000000）、`:1350` 别名 `com.apple.uart.bluetooth` 注册 error=0、`:1351` `[bluetooth power] nodes ready major=17`。
- 参数：`:1723` bluetoothd argc=1；`:2083/2873/3286/3527/3729` 五次 `BlueTool argc=2 [/usr/sbin/BlueTool] [-R]`。`-R` 合法（20G81 的 `com.apple.BlueTool.plist` 只传 `-R`），D12-A 排除。
- 关键否定：**没有任何 `[bluetooth sk] connect` 行，也没有任何 `[bluetooth power]` open/ioctl 行**。两个控制名在开机时都已注册，说明 BlueTool 在打开传输之前就退出了。
- 时间：`:2082` 的 wall clock 是 `04:32:51.607`，`:2867` 是 `04:33:24.445`，`:2871` 是 `KX! 15 137 BlueTool exit=1`。exec→exit 约 33 s，等于静态分析的 30 s XPC 看门狗（`dispatch_time(0,0x6FC23AC00)`，`0x1000430f0` → `_exit(1)`），不是坏参数的瞬时退出。
- 判定：D12-C 形态，但 §6 要求的"至少一次 connect"没有出现，按探针门槛未达记录；结论（看门狗在传输打开前触发）靠时间差成立。0519 的电源节点未被打开，0520 的名字别名错配也被排除为直接原因。
- 边界：不证明卡在哪一步（XPC 等待、平台/芯片探测、设备树读取），不证明蓝牙可用；内核栈自 d11 起未变。离线补充：从 20G81 IPSW 解出 `com.apple.BlueTool.plist`（`-R`、MachServices `com.apple.BlueTool`、无 RunAtLoad）与 `com.apple.bluetoothd.plist`（RunAtLoad、KeepAlive SuccessfulExit=false），bluetoothd 字符串同时含 `com.apple.uart.sk.bluetooth` 与 `/dev/btwake`。

### 50. 蓝牙转入待命：接受“iOS 16 测试床 / 用户态预算转 iOS 27”，并记下上游基线（2026-11-19 01:10）

- 用户决定（2026-11-19）：“接受『iOS 16 停在测试床、用户态预算转 iOS 27』，接下来就看外国大佬，如果他有突破性进展，那 iOS 27 的蓝牙就可以继续做。现在蓝牙先待命。” 据此：不启动 iOS 27 构建、不做 20G81 用户态、不新增飞行；只保留监视。
- 上游基线（本轮抓取，供下次比对）：
  - `xNekom/UniXNU-mondrian` `feat/ios27` = `95d9c8a1849e1befed0852ff78f7674089345e6c`。我们的 `feat/bt-ios27-port` 基于 `96e07b1`，已落后 17 个提交。新提交把 F1 内核、payload、F2 prelink、F3 userdata 全部搬到了 Linux 离线路径（`scripts/build-ios27-linux.sh`、`scripts/check-ios27-artifacts.py`、`patches/unixnu-core/fileset-reference-linux.patch`、`linux-aea-decrypt.patch`、`patches/ios-mondrian/pac-probe-arm64e-gate.patch`、`patches/xnu-12377/armcpu-sleep-hook.patch`），也就是我们之前 F1 卡住的 `LD_KERNEL_LIBS` 一类问题已被上游用自己的路径解决。
  - `QcaBluetooth` 本地落后 `origin/main` 4 个提交（尖端 `fa52814`，2026-11-16）：LE event-mask 追踪与 CrossDarwin 的 classic inquiry / extended discovery 合并——都属于 iOS 27 用户态蓝牙的实质推进。
  - 框架 `UniXNU` 本地 `4eaf2b9`（A730 hw_init 生成）。
- 恢复条件（任一命中就重新评估，不必等用户再次点名）：上游 `docs/engineering/IOS27.md` 记录 F1/F2 镜像在真机到达 `bsd_init`；或 `board.toml`/catalog 出现蓝牙相位或 `QcaBluetooth` 组件；或 `QcaBluetooth` 新增 iOS 16 目标/新 native 适配；或 `feat/ios27` 出现蓝牙相关提交。
- 恢复后的第一步（已定，不用重新设计）：把 `feat/bt-ios27-port` 变基到新的 `95d9c8a1`，按 `docs/plans/BT-IOS27-PORT.md` §4/§7 重排 0501/0502/0509/0510/0512（含 0519 的 `MiniBluetooth.cpp`、0520 的 `kern_exec.c` 两个 hunk），再把 13 个补丁从 `patches/xnu/series` 移进 `patches/xnu-12377/series`，用上游的 `scripts/build-ios27-linux.sh` 出 F1。
- 进度更新（2026-11-19 01:50，离线完成，未构建未飞行）：变基与重排都已落地。`feat/bt-ios27-port` 现在基于 `95d9c8a1`，补丁进入 `patches/xnu-12377/series`（18 个：0500、0502b、0501、0502、0507-0512、0514-0520、0521），`patches/xnu/series` 回到 227 行原状。四个平台钩子按 95d9c8a1 重排：0501 在 `bsd/conf/files` 列六个 qbt 源，0502 去掉 `ARM64_BOARD_CONFIG_PONG` 门，0509 变成独立的 `iokit/Kernel/MiniBluetooth.cpp`（用 `IOService::getResourceService()` 当 provider，丢掉 12377 没有的 MiniDrivers/MiniIOSurface hunk），0510 在 `osfmk/conf/files.arm64` 挂 `k60_bt_blob.s`，0512 在 `native_owner_data_prepare()` 里起 late start；0519/0520 原样可用。0510 需要的 `osfmk/arm64/k60_bt_blob.s` 由 0521 提供（生成器不带 `--container` 时的确切 stub，12 行、长度 0），`scripts/gen-k60-bt-blob.py` 已复制进 fork。验证：从 pre-BT 基树按系列顺序应用 18 个补丁全部无 reject，`bsd/dev/qbt_k60.c` 仍是 2239 行 `4a1a4e26…`。远端 tip `9503432`（`emilelu/feat/bt-ios27-port`）。
- 剩余（都不在待命授权内）：P3 构建并确认 `qbt_k60_start` 进内核；`[payload.runtime]` 用户态接线；等上游真机到 `bsd_init`。
- 当前没有待飞行项：设备 `k60-device.sh state` = none；d8 `0297012d…`、d10 `6c631bc4…`、0518 `d6beec4c…`、0520 `9361ec1c…` 四枚镜像均在且哈希已复核。

### 49. 用户态难度对比：iOS 16 停在测试床，用户态预算转向 iOS 27（2026-11-19 00:35）

- 新文件 `docs/plans/BT-USERLAND-COMPARE.md`（114 行）回答用户 2026-11-18 的决定性问题：先修 20G81 的用户态，还是把用户态留给 iOS 27。
- 事实骨架：20G81 的 `bluetoothd`（sha256 `2cf8d9cd…ea4a`）**完全没有 QCA 支持**——`grep -i 'QCA\|Qualcomm\|wcn'` 零命中，芯片表是 `Server/Chipsets/LEHardwareModel.cpp` 的 BCM/CSR 语义；BlueTool 内置 firmwareList 也是 BCM 专用，QCA 无条目（`0x100014f10`）。反过来 iOS 27 的替换用户态（QcaBluetooth `BlueTool.c` 63 行 + `Type0.c` 217 行 + `native_ios27.py` 496 行）已在 sheng/aston 上验证。
- 差距归因：iOS 16 差的是**为一个 build 重做 496 行地址重定位**（`native_ios16.py` + 20G81 布局）与**安装路径**（20G81 profile 没有 `[payload.runtime]`；sealed root 拒绝 bindfs，见 `0404-k60-metal-deploy.patch:210-224` 的 P-27）；iOS 27 那两条都是现成的。
- 估时（带“约”）：iOS 16 顺利 1–2 周（只做 BlueTool 身份伪装，成功率未知）、稳妥 4–6 周（daemon 重定位，且不可迁移）；iOS 27 用户态 1–3 天，风险全在内核 bring-up（F1 的 `LD_KERNEL_LIBS` 一行修复 → F2 prelink 到 bsd_init → F3 存储 → F4 面板）。
- 离线追加（子代理 bluetool-flow 反汇编 `runCommandForCurrentConfig` 0x100015fa4）：打印该句之后依次是 `getManufacturer` 0x1000401a8 → **`MGIsDeviceOneOfType` 0x100040284** → `getVendor` 0x100014dbc → `MGCopyAnswer("ReleaseType")` 0x100016060 → `stat("/etc/bluetool/<HWModel>.<phase>.script")` 0x10001648c → `stat("/etc/bluetool/<platform>.<phase>.script")` 0x100016534 → 内置 firmwareList。全程只有 MobileGestalt 的同步 XPC 没有超时；看门狗取消点在 0x100042cf0，只有工作函数返回才执行，所以 33 s 被杀 ⇒ 0x100042b98 未返回，最可能是卡在 MG。`stat` 与 `fopen` 都是本地 VFS、不会无限等待；`Opening %s @ %d baud.`（0x10001d1f8）没出现也印证没到内置脚本。**该卡点属用户态**，内核侧无法推进（除非伪造 MG 回复，那是用户态/补丁层面的工作）。
- 建议与分界点：iOS 16 内核侧到此为止（d11 PASS + d12 观测已记录），用户态不再投入；若 F1/F2 在约两周内看不到 bsd_init，再回头评估 20G81 的 daemon 重定位。`porting.toml` 的 bluetooth `next_action` 与 `limits` 已同步改口径，并把 `marconi-bt` 的归属更正为 `com.apple.driver.AppleSPU`。

### 51. iOS 27 蓝牙系列首次在 GitHub Actions 上构建通过（2026-11-19 05:04）

- 背景：用户 m21327 要求用 GitHub Actions 试构建。按 item 50 的口径，本轮只跑 Linux CI 构建，不启动真机、不碰 20G81 用户态。
- 分支：fork `Emilelu/UniXNU-mondrian`，`feat/bt-ios27-port` 基于上游 `95d9c8a`；蓝牙系列 19 个补丁（0500、0502b、0501、0502、0507-0522）。触发构建的分支是 `ci/ios27-kernel`，携带 `.github/workflows/ios27-kernel.yml`。
- 工具链：release `toolchain-linux-20261119`（`unixnu-linux-20261119.tar.gz`，68,589,703 B，sha256 `b29926aef9938d2c540bfd01f3341bede457db9efed98f78f79735c7c86f85ee`），runner 解到 `/opt/unixnu-linux`；框架固定在 `563595ab`。
- 首次真错误：`bsd/dev/qbt_k60.c:1851:13: error: call to undeclared function 'kmem_alloc_contig'`，同处的 `KMA_DATA`/`KMA_ZERO`/`KMA_PERMANENT`/`kmem_free` 也都未声明。原因：xnu-12377 把 kmem allocator API 从 `vm_kern.h` 拆到新的 `vm_kern_xnu.h`，8792（iOS 16）仍写在 `vm_kern.h`。新增 `0522-k60-bt-vm-kern-xnu.patch` 只补这一行 include，驱动逻辑不动；之后 19/19 补丁干净应用，`bsd/dev/qbt_k60.c` 2243 行 sha256 `4b973811ed805820d8b59c1e10a624f260b1769bcf24280f546cfedcd5eedc62`。
- 结果：run `44395638974`（head `6f27fbc`，2026-11-18T20:52:54Z→21:04:39Z，11m45s）success。`kernel/kernel.macho` 93,077,504 B sha256 `bf737397a915fd659d9c1a89c0addd7263d6a6190f3071d5c9311c544f1d8122`；`payload/payload.img` 201,326,592 B sha256 `36e0014faade8601d517608ab0d3916c2fccb5cec9cdf1ea911a9292d58eaeb4`。`xnu-patches.list` 96 条，含 0500、0502b、0501、0502 与 0507-0522。
- 内核内容：`strings` 能看到 `[bluetooth sk] ctl_register com.apple.uart.sk.bluetooth`、0520 的别名 `com.apple.uart.bluetooth`、`[bluetooth power]`、`K60 BT: no IOKit resource service; bluetooth not published`，说明 qbt 栈与 MiniBluetooth 发布点都进了链接。
- 日志状态：只剩 bootstrap pass 的已知假阴性（release reference 先 `exit 2` 去掉 67 个 unavailable forced exports，再次链接 `exit 0`）；ArmCpu、ArmDTPlatform 的 `-Werror` arm64e 对象审计通过。
- 边界：这是构建/预链接证明，不是运行证明。iOS 27 在 SM8475 上仍未到 `bsd_init`，P4 不启动；蓝牙本体继续按 item 50 待命。
- 记录位置：fork `docs/plans/BT-IOS27-PORT.md` §5.3、fork `porting.toml` 的 `ios27-arm64e` findings；提交 `786fde0`。


### 52. 0523：客户端改速真正落到 UART（2026-11-19 13:48）

- 背景：用户 m21660 授权继续与系统版本无关的内核工作。0520 之后已知的内核功能缺口只剩一个：TIOCSETA 只保存 termios，从不把新速率写进 GENI，BlueTool/bluetoothd 即使连接成功，改速请求也到不了硬件。
- 设计：transport ops 新增 `int (*set_rate)(void *, uint32_t baud)`。TIOCSETA 仍先校验 cflag 与 8N1；speed 与当前不同才调 hook，成功才更新 `bt_sk_speed` 与 termios，失败返回 EINVAL。改速必须在 worker（GENI 所有者）里做：客户端持 `k60_rate_lock`、写 `rate_request`、`msleep(&k60.rate_done, ..., 2 s)` 等结果；worker 在 `k60.powered` 块内先取锁、调 `k60_uart_speed(NULL, requested)`、`wakeup`；power off 清 `k60.ready`。未上电或未就绪返回 ENODEV。
- 补丁：`patches/xnu/0523-k60-bt-transport-set-rate.patch`，sha256 `8240dcbf0fc9563a4cae6b6405278553ab4689a6760c919421448d65d8ee8575`，7,189 B，11 个 hunk，只碰 `qbt_transport.h`、`qbt_transport.c`、`qbt_k60.c`。series 241 行，sha256 `c1e23a54a5b1a4ba3fed3efef47b5f5650f246e9d14b39dc3a35195dd638c03d`；0519/0520 字节未变。两棵树都 `git apply --check` 通过：iOS 16 结果 `qbt_k60.c` 2,302 行 `276bcf7decc8858e62febc9eb73be1c489fedd43e58164b0a0bd5b02266f7cea`，ios27 2,306 行 `65e29a1afd5c3ee85b98cd1db2bdbe5f727a83422040f21fac0af758ba10a803`，transport 613 行 `5a80bb039d91db1297400ceeb5cc583205ef192565ac78090655b20a98afc634`。
- 测试：新增 `scripts/tests/test-bt-0523-transport-set-rate.py` 36/0；旧套件 0516 82/0、0517 53/0、0518 36/0、0519 29/0、0520 24/0。
- iOS 16 构建：`bt-0523-transport-set-rate`，`built_at` 2026-11-19T13:48:47+08:00，repo head `6b25953ee67ccd31090b9781244bb66240fb8df0`、dirty 0；boot.img `865f3ede1c192cfec046a5bf5f93a0e8fadf819559587dc0c5fe47418a4d0208`（201,887,744 B）、kernel_built `fbf5ffcc3680ea5495a18ce5884a44318fa00c3078c692fed1859a3c92fa251d`、payload `f813342682ae6624efb8528edce6c66eba0b213d98d87aa54b810be6e13f03e3`、payload_kernel `9fd1ceb797021f475f68349f2bd421f5622b192ec554b5fbffe079a3083270bc`、ADT `6fd846b12645a4363b64feccd7f0cbbff74b0e0488e82001f05c7ad13bd44ce6`、dtb `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`、fd `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f`、bt_blob `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037`；kernel.log:274 = 0523；verify-boot-image OK、image-arg-audit 31/598、八步 bluetooth 通过。未飞行：改速只有真实客户端触发，悬空飞行没有判据。
- 边界：只证明客户端改速路径存在，且编译、链接、打包通过；不证明任何客户端真的改速成功，不证明蓝牙可用。
- ios27 侧同步：0523 也进了 fork 的 patches/xnu-12377/ 系列（二十个蓝牙补丁）。GitHub Actions run 44466443708（head b689f94，2026-11-19T05:37:28Z 至 05:52:57Z）构建并 prelink 成功：kernel.macho 93,077,504 B sha256 04765d4eb2a1bb6c953ded6009af9733026477e6d4d2255332c76842eccd870b、payload.img 201,326,592 B sha256 d571b254de20625c63441764ee3a80ca567ed55808add3aff1aabdf09aa2d7f1、xnu-patches.list 97 条且 0523 在末尾，内核里带 [bluetooth sk] TIOCSETA 新日志。仍未上真机。


### 53. 蓝牙节点进设备树：/arm-io/bluetooth 由静态节点发布（2026-11-19 14:22）

- 背景：官方页 step 4 要求在用户态启动前发布 bluetooth 节点（device_type、compatible、unixnu,adt-name、transport-encoding、transport-speed），并设置 local-mac-address 与 /chosen/mac-address-bluetooth0。此前 K60 只有 MiniBluetooth.cpp 在运行时创建 /arm-io/bluetooth，静态 DTS 里没有该节点，构建产物的 ADT 也不含它。
- 改动：dts/mondrian.dts 在 pong-audio 与 ufs@1d84000 之间新增根节点 bluetooth：device_type="bluetooth"、compatible="qcom,wcn6855-bt"、unixnu,adt-name="bluetooth"、transport-encoding=<1>、transport-speed=<3000000>、status="okay"。compatible 取 mainline 同硅绑定（K60 是 QCA6490/WCN6855 系，不是 sheng 的 WCN7850）；速率保持 3000000，因为 QUPV3 源 48 MHz 没有 3.2 Mbaud 的整数分频，qbt_boot 实际停在 3.0 M。
- 机制：scripts/unixnu/devicetree.py:368-380 把所有 enabled 且带 unixnu,adt-name 的根节点导出成 /arm-io/<name>，所以 bluetooth 会出现在 ADT 的 /arm-io 下。MiniBluetooth.cpp 的 k60_bt_node() 先 IORegistryEntry::fromPath("/arm-io/bluetooth")，命中后不再重建节点，只补 local-mac-address 与 K60BluetoothRadio。
- 提交：k60-bt f7d6621f（+19 行，已推）；fork Emilelu/UniXNU-mondrian 1e2e681，CI 分支 5f4c895。
- iOS 16 验证：bt-0524-dt-node，boot.img 57d8f964ab5f45af2df293181590ec3396fd3786b350f257a596672ab70bf257（201,887,744 B），manifest repo head f7d6621f、dirty 0、series 241；hardware.dtb 4,207 B，fdtget 读到六个属性；payload ADT 16,292 B，bluetooth 出现 2 次（偏移 13668/13716）、compatible 1 次（13764）、transport-speed 1 次（13820）。
- iOS 27 验证：GitHub Actions run 44470953368（head 5f4c895，9m12s）success；产物的 ADT 同样含 bluetooth 2 次与 compatible 1 次；kernel.macho 里 com.apple.uart.sk.bluetooth 字符串 2 条。
- 检查脚本：scripts/check-bluetooth-dt.py 检查 dts，可选 --dtb（fdtget 逐属性）与 --payload（mcopy 取 ADT 后查字节），对 bt-0524 全过；scripts/tests/test-bt-0524-dt-node.py 15/0，错速率、重名、缺节点三种输入都会变红。
- 参考仓（用户 m22039 指定）：t970（SM8250，tip 638dbda）与 zizhan（SM8475，tip 034a0b0）都没有蓝牙驱动；t970 userland/board_services18.py:84-89 直接把 bluetoothd 限制到 bluetooth/marconi-bt 节点；zizhan 可借的是 PongWifiPlatform.cpp:170-191 的 RPMh rail 投票（K60 qbt 目前不投 rail）与 make-pong-adt-ipados18.py:349-362 的 udid-version 2 经验（缺 WifiAddress 时 MG UniqueDeviceID 会阻塞数秒；K60 make-pong-adt.py:266 仍写死 version 1，属 OS 版本强相关，暂不动）。
- 边界：构建与 ADT 证明，不是运行证明；没有飞行，没有新的硬件观测；蓝牙可用性仍受 item 52 的用户态结论限制。

### 54. iOS 27 用户态首次离线构建：24A446 的 bluetoothd 与锁定的原件逐字节一致（2026-11-19 15:33）

- 背景：新目标要求这条线为迁移到 iOS 27.0.1 做准备，用户态参考 sheng 最新代码。QcaBluetooth 的 native_ios27 适配器绑定 bluetoothd 的 SHA-256 与 UUID，所以第一步是确认我们的 24A446 IPSW 里的守护进程是否就是它锁定的那一份。
- IPSW：https://updates.cdn-apple.com/2026FallFCS/3741bcd4-e0a6-43a7-bac1-74f363efb9ab/iPhone17,2_27.0.1_24A446_Restore.ipsw，12,314,041,166 B，下载到 /home/emilelu/ipsw/24A446.ipsw。根文件系统是 AEA 加密的 043-69909-664.dmg.aea（8,858,370,048 B）；用 blacktop/ipsw 3.1.749 的 ipsw fw aea 解出 043-69909-664.dmg（10,223,616,000 B），7z 取出 usr/sbin/bluetoothd（13,092,096 B）。
- 结论：bluetoothd SHA-256 = cfd94854d0a2efd3ca4a2de6e55349f43fd0d274a4b8bfa9937f29d9f7208cb1，与 QcaBluetooth tools/native_ios27.py 的 ORIGINAL_SHA256 和 UUID 8E49197B-E6BC-3F3B-A8D3-DF4BEDD37F01 完全一致。适配器不需要重新定位。
- 构建：在一台只有 Command Line Tools 的 Mac（Intel，iPhoneOS.sdk，codesign 为系统工具）上跑 fork 的 scripts/build-bluetooth-userspace.py，产出 bin/BlueTool（87,216 B，CDHash 1c1c94b3c400d2525051be6c0815851c436206b6，sha256 aef741399ef23d3283721a708ff78a2ad6d9ea64357229cf2d11564dafe73d9f）、bin/bluetoothd（重签，CDHash 7d6db4db44e30e52150c6ae63b3337f0f1fa6521，sha256 178444d651c734bdbff49b03503418b4c1264b45b80bc4c54a5d7dda13013d34；157 项 entitlement 保留）、lib/QcaBTType0.dylib（102,096 B，CDHash 4c000ee5244140a98ec23f1b11ec30b5fd12f15e，sha256 e815fe2f32a147b1f574ebccaf9e205503bbba41c723d184096fa3f0879147b7），并暂存 40 个 firmware/qca 文件。report 里 hardware_verified=false。
- 环境适配（已随 fork 提交）：CLT 的 iPhoneOS.sdk 有 libxpc 但没有头文件，scripts/toolchain/xpc-shim/xpc/xpc.h 声明 BlueTool.c 用到的 13 个符号；该 SDK 也没有 libxpc 的链接桩，scripts/toolchain/xpc-shim/lib/libxpc.tbd 补上安装名与导出符号，使 BlueTool 带上真实的 LC_LOAD_DYLIB /usr/lib/libxpc.dylib（而不是留未绑定符号）；组件的 tools/build-bluetool.py 不收额外编译参数，scripts/toolchain/qca-bluetooth-extra-flags.diff 加了 QCA_BT_EXTRA。完整 Xcode 三者都不需要。
- 提交：fork Emilelu/UniXNU-mondrian 91d4123（toolchain 输入）、f16cca5（文档 §6.1）、后续修正提交（libxpc 显式链接与新哈希），已推 emilelu/feat/bt-ios27-port。
- 边界：构建与签名证明，不是运行证明；[payload.runtime] 仍未启用（会让 payload 构建去挂 24A446 系统镜像，属 F3）；没有飞行。
