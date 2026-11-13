# Handoff — K60 Bluetooth line (state at 2026-11-14)

This file is the single-page handoff from the `feat/bt-research` line to the integrated line.
Nothing here is build-wired: the branch adds only `docs/research/bt/*` and `patches/bt/*`.

Branch: `feat/bt-research` (worktree `E:/hackios/k60-bt`), base `f119a80` (= `main` at the time
of writing). Commits: `3fb11e5` (research), `abc6964` (probe patch), `f71ef4f` (S1 spec),
`8bc2f7f` (static verification + baseline gate state), `56ff95c` (probe extension),
`86a7550` (deep dive).

## 1. What is delivered

| artefact | content | status |
|---|---|---|
| `docs/research/bt/RESEARCH.md` | ①同型/②官方/③反编译/④广域 evidence tables, the seven answers (UART SE20 0x894000, IRQ 587 + GPIO79 wake IRQ 208, 3.0 Mbaud, H4 + IBS wake byte 0xFD, CTS/RTS/TX/RX = 76/77/78/79, BT_EN 81, SW_CTRL 82, XO 204), firmware expectations, WiFi/BT single-chip boundary, S1–S6 plan | done |
| `docs/research/bt/06-DEEP-DIVE.md` | ⑥ line-by-line review of `patches/xnu/0500`'s `bsd/dev/qbt_k60.c` (1,249 lines, sha256 `8451c870…`): 11 verified items V1–V11, 10 deviations F1–F10 | done |
| `docs/research/bt/S1-PROBE-SPEC.md` | S1 read-only probe: 9 reads, boot args, verdict table (incl. F2/F3 rows), device procedure, wiring options | done, statically verified |
| `patches/bt/0001-k60-bt-readonly-probe.patch` | 2 hunks on `bsd/dev/qbt_k60.c`: `k60_bt_probe()` + `k60bt_stage=1` early return. sha256 `95e4b098e552619db135b455af5dbec96eae4450a2a8cdae1c6c61ce658ed8a3` | **not build-wired** |
| `patches/bt/README.md`, `patches/bt/series` | explains that the build reads only `patches/xnu/series`; wiring options A/B | done |

## 2. Why S1 first

Two independent reproductions (`docs/research/GENI-ACCESS-PRECONDITIONS.md`) show that the **first
GENI register access** on this device produced a 0-byte console: touch on QUP0 SE4 (0x990000) and
audio I2C on 0x880000. BT sits in the same QUPV3_2 wrapper. So the only question S1 answers is
"can SE20 be touched at all". S1 maps GCC/SE20/wrapper, takes the five QUPV3_2 votes, and performs
nine **loads**. No pin mux, no BT_EN pulse, no DMA, no interrupt.

Secondary purpose: decide the two deviations that would otherwise be debugged as mysterious
power failures — `G_MANUAL_RFR` (0x2ac) written as `0x80000001` (F2), and `k60_stop_engine()`
polling the undefined offset 0xe40 (F3, would return `-ETIMEDOUT` deterministically if it reads
non-zero).

## 3. Lead actions, in order

1. **Rebase/merge `feat/bt-research` onto the integrated line ≥ `4f90f12`** (feat/pmic-rail).
   On `f119a80` the build gate is red for touch, not for BT:
   `eight-step-gate.py --build` → `硬件项: 5 个`, `通过 27 项检查`,
   `问题 3 处: touch :: ④ 广域 / ⑤ 方案 / ⑥ 深挖 未标记 done=true`.
2. **Wire the probe**, option A (preferred): fold the two hunks of
   `patches/bt/0001-k60-bt-readonly-probe.patch` into
   `patches/xnu/0500-k60-bt-qbt-new-files.patch` — 0500 creates a new file, so `patches/xnu/series`
   and `check-build-applied.py` are untouched. Option B: new `patches/xnu/0503-…` + one series
   line + `sync-device-input.py`.
3. **Register the BT hardware item** so the gate can see ①–⑥ (see §4 for the exact TOML).
4. Build: `python3 scripts/sync-device-input.py` → `python3 scripts/check-rules.py` →
   `python3 scripts/eight-step-gate.py --build` → `bash scripts/build-strict.sh` →
   `python3 scripts/verify-boot-image.py <boot.img>`.
5. Device: attach the CDC-ACM capture **before** any `fastboot boot` (AGENTS.md iron rule 8: console
   VID_1209&PID_0001, usbser.sys, port only from `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM\Device\USBSER000`,
   DTR raised), boot the **same image twice** with boot args
   `k60bt=1 k60bt_stage=1 k60bt_warm=1`, then `python3 scripts/record-boot.py --evidence <dir>`.
   Judge only `capture.json` `verdict`/`panicMarker` (never logstat.py panic counts).
6. Feed the S1 result back into `docs/research/GENI-ACCESS-PRECONDITIONS.md` (the touch and audio
   lines share this precondition) and into `06-DEEP-DIVE.md` F2/F3.

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

- **Firmware**: `/vendor/firmware_mnt/image/qca6490/` holds 42 `bd_*.elf` (~60 KB each; this unit
  uses `bd_m11agf.elf`, 60,000 B) plus the WiFi `amss*.bin`/`Data*.msc` already copied to
  `E:/k60-work/firmware/qca6490/`. The BT TLV names (`htbtfw21.tlv` + `htnv21.bin` expected) are
  **not** verifiable offline; listing requires one Android boot with read-only adb.
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
