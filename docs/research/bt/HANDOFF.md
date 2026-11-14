# Handoff — K60 Bluetooth line (state at 2026-11-14)

This file is the single-page handoff from the `feat/bt-research` line to the integrated line.
The branch adds `docs/research/bt/*` and `patches/bt/*`; the one wiring edit outside that scope is
`patches/xnu/series:205` + `patches/xnu/0507-k60-bt-readonly-probe.patch` (see §3).

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
| `patches/bt/README.md`, `patches/bt/series` | explains that the build reads only `patches/xnu/series`; wiring status (option B used, option A kept as an alternative) | done |

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
normally, so the hang belongs to the `k60bt=1` path, not to the build. The attempt is therefore
**indeterminate**: it says "something in the BT start path kills the machine before the console
enumerates", not which register did it. That is exactly what S1c fixes by sleeping 20 s first,
printing a mark before every single access, and splitting the clock path into rungs that can each
be judged dead on their own.

## 3. Lead actions, in order

1. **Done already:** `feat/bt-research` was rebased onto the integrated line `63eb384` (feat/pmic-rail)
   and the probe was wired as `patches/xnu/0507-k60-bt-readonly-probe.patch` + `patches/xnu/series:205`
   (option B), then `sync-device-input.py` was run so the build mirror matches. On the rebased branch
   `eight-step-gate.py --build` reports `硬件项: 5 个`, `通过 30 项检查`, `✅ 八步流程通过`.
2. **PHYSICAL POWER CYCLE FIRST.** The S1a boot (`k60bt=1`) hung the board before the USB gadget
   enumerated: no `adb`, no `fastboot`, no USB device. `scripts/k60-device.sh` documents this as the
   one state no script can leave. Hold power until it is off, then boot it back to Android/fastboot.
3. **Register the BT hardware item** so the gate can see ①–⑥ (see §4 for the exact TOML).
4. **S3 身份与发布已就位**：`patches/xnu/0509-k60-bt-s3-identity-publish.patch` 在 `series:207`（`0508` 之后、`0503` 之前），把弱 `k60_bt_local_address()` 换成读 `/chosen/unique-chip-id` 的强定义，并在 `native_pong_ui_services_start()` 里发布 `/arm-io/bluetooth` 节点、两处 MAC 与 `bluetooth` IOService（全部 `k60bt=1` 门控）。**但它需要平台种子**：`board.toml:218` 只有 `chip_id`，没有 `unique_chip_id`，所以现在只会打印 `K60 BT: no platform identity (-2); bluetooth not published`。补种子任选一条：给 `[payload."adt"]` 加 `"unique_chip_id" = "required"` 并在构建时设 `UNIXNU_UNIQUE_CHIP_ID=<hex>`（`build-strict.sh` 继承调用者环境，`payload.py:160-163` 会读它），或给 `build-strict.sh` 加 `--unique-chip-id` 转发。种子定下后**不要改**（否则 MAC 变化、配对作废）。详见 `S3-SPEC.md` §4。
5. **S2 前置修复已就位**：`patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch` 在 `series:206`（`0507` 之后、`0503` 之前），修 F1/F11/F3/F12，`git apply --check` 与 `clang -fsyntax-only` 均通过；下一个镜像会自动带上它，不需要额外动作。
6. Build (**done — all five rung images are built and verified**, see the table in `S1-PROBE-SPEC.md` §4.1; rebuild only if the probe changes again): `python3 scripts/sync-device-input.py` → `python3 scripts/check-rules.py` →
   `bash scripts/build-strict.sh <tag> --fd <fd> --kernel-arg k60bt=1 --kernel-arg k60bt_stage=1
   --kernel-arg k60bt_warm=1` → `python3 scripts/verify-boot-image.py --manifest <artifact>/build-manifest.json`.
   Expect the payload TOML to end with the three `k60bt` args (check with
   `mtype -i <payload.img> ::/EFI/UniXNU/unixnu.toml`).
7. Device: attach the CDC-ACM capture **before** any `fastboot boot` (AGENTS.md iron rule 8: console
   VID_1209&PID_0001, usbser.sys, port only from `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM\Device\USBSER000`,
   DTR raised), then boot the rungs in order, adding risk each time (S1-PROBE-SPEC.md §4/§4.1). Each rung
   is its own image because `k60bt_*` lives in the payload command line, not in the kernel:
   `bt-s1c-a1-20261114a` (step 1, maps only, cannot hang) → `bt-s1c-a2-20261114a` (step 4, GCC only) →
   `bt-s1c-a3-20261114a` (step 5, first RCG read) → `bt-s1c-a4-20261114a` (step 7, first RCG writes) →
   `bt-s1c-20261114b` (step 9, first GENI read). All five carry `k60bt_delay=40`.
   Stop the ladder wherever the board dies. Record with `python3 scripts/record-boot.py --image … --log <dir>/console.log`.
   Judge only `capture.json` `verdict`/`panicMarker` (never logstat.py panic counts).
   Read the verdict off the **last `probe: …` line** in the console (S1-PROBE-SPEC.md §5); if it stops
   at an `sX` step, re-boot once with `k60bt_step` one lower to prove that access is the fatal one.
8. Feed the result back into `docs/research/GENI-ACCESS-PRECONDITIONS.md` (the touch and audio lines
   share this precondition), `06-DEEP-DIVE.md` F2/F3 and `RESEARCH.md` §5.4.

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
