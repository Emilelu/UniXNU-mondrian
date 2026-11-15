# Handoff — K60 Bluetooth line (state at 2026-11-15)

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
| `patches/bt/0004-k60-bt-firmware-addon.patch` = `patches/xnu/0510-k60-bt-firmware-addon.patch` | **rewritten 2026-11-15 for P-197**: 2 files (289 ins / 1 del): NGPUADD2 parser `k60_addon_find()`, `k60_bt_addon_load_blob()` reading the linked `k60_bt_blob` / `k60_bt_blob_len` (the new primary carrier), the old SecureDT `chosen/memory-map/GpuAddon` path kept as fallback, `k60_bt_addon_read()`, and `k60_bt_firmware_read()` trying the addon first; `osfmk/conf/files.arm64` gains `osfmk/arm64/k60_bt_blob.s`. sha256 `316148931ab11fa9fbd79fbe7b878960e702b39d5e89babd0daa806655fccc96` (15,672 B) | **build-wired** (`patches/xnu/series:208`) |
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
6. **Worktree repair tool (Lead, one patch).** P-203 restored nineteen trees by hand with
   `E:/k60-work/scratch/refmine/repair-wts.py`, a one-off that hard-codes the main checkout and has no
   test. The Lead asked this line for a generalised version, so it is exported as
   `/mnt/e/k60-work/scratch/bt-s4/lead/bt-repair-worktrees.patch` (23,312 B, sha256
   `9a08aade286924780f5f16628a7b03a0b21cc160e60818ad7e5a35309332ed44`, two new files:
   `scripts/repair-worktrees.py` and `scripts/tests/test-repair-worktrees.py`).
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

