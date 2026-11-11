# UniXNU-mondrian

UniXNU device support repository for the Redmi K60 (codename **mondrian**, Qualcomm **SM8475**).

**Current target: full hardware bring-up on iOS 16.6.1 (20G81) / darwin22.**

> Last updated: 2026-11-12. Detailed status and change log:
> [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md).

[中文版](README.md)

## Eight-step progress

<!-- EIGHT-STEP-TABLE:BEGIN -->
| Hardware | ① Same model | ② Official | ③ Reverse | ④ Wide search | ⑤ Plan | ⑥ Deep dive | ⑦ Local verify | ⑧ On device | Status |
|---|---|---|---|---|---|---|---|---|---|
| **触摸（Goodix GT9916R / BERLIN）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | **Blocked at ⑦** |
| **GPU（Adreno 730v3 / Metal）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | Ready to flash (⑦ verified) |
| CPU | — | — | — | — | — | — | — | ✅ | device-verified (no record) |
| UFS / 存储 | — | — | — | — | — | — | — | ✅ | device-verified (no record) |
| 显示 | — | — | — | — | — | — | — | ✅ | device-verified (no record) |
| 固件 / 启动 | — | — | — | — | — | — | — | ✅ | device-verified (no record) |
| 电源 | — | — | — | — | — | — | — | ✅ | device-verified (no record) |
| 诊断 | — | — | — | — | — | — | — | ✅ | device-verified (no record) |
| WiFi / 蓝牙 / USB | — | — | — | — | — | — | — | — | planned |
| 音频 | — | — | — | — | — | — | — | — | planned |
| 基带 | — | — | — | — | — | — | — | — | planned |
| DSP | — | — | — | — | — | — | — | — | planned |

> ✅ done　◐ partial　❌ not done　— no record
>
> 表格由 `scripts/render-eight-step-table.py` 从 `docs/research/EIGHT-STEPS.toml` 生成，`--check` 可校验 README 是否与数据一致。
> 八步定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。
<!-- EIGHT-STEP-TABLE:END -->

## Branches

| Branch | Purpose |
|---|---|
| **`main`** | Mainline (default). All working milestones land here |
| `feat/first-frame-20261107` | Historical milestone: first iOS 16.6.1 userland frame (separate history line) |
| `chore/archive-darwin24-main-20261103` | Retired darwin24 (iPadOS 18) route (kept as archive) |

## Layout

| Path | Contents |
|---|---|
| `board.toml` | `schema_version = 2` board configuration and component selection |
| `porting.toml` | Records for 14 subsystems (data source for the device page on unixnu.com) |
| `feeds.toml` | Pinned SoC sources |
| `configs/mondrian_defconfig` | Kernel configuration |
| `dts/mondrian.dts` | Memory, CPU, peripherals |
| `patches/xnu/` | Device patches; order in `patches/xnu/series` |
| `scripts/` | Build and check tooling (including four gates) |
| `drivers/` | PongAdreno / NativeUfs / NativeRamBlock / ArmCpu / ArmDTPlatform / PongMetal |
| `docs/engineering/` | Hard rules, pitfalls, hardware truth, eight-step spec |
| `docs/research/` | Eight-step evidence (`EIGHT-STEPS.toml`) and research checklist (`SOURCES.toml`) |

## Four-layer repository model

| Layer | Repository | Contents |
|---|---|---|
| Framework | [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU) | `unixnu` command, shared scripts, component catalog |
| SoC | [UniXNU-sm8475-common](https://github.com/UniXNU/UniXNU-sm8475-common) | `soc.toml`, `configs/sm8475.config`, `dts/sm8475.dtsi` |
| Device | This repository | `board.toml`, `dts/mondrian.dts`, `patches/xnu/` |
| Firmware | [uefi-mondrian](https://github.com/Emilelu/uefi-mondrian) | EDK2 / Mu-Silicium build tree |

## Building

```bash
./unixnu build kernel -D .
```

Output: `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong`.

Local build scripts live in the workspace (not in this repository); see
[`docs/engineering/ENVIRONMENT.md`](docs/engineering/ENVIRONMENT.md) for the flow.

## Gates

Four checks run automatically before build or flash; any failure aborts:

| Gate | What it checks |
|---|---|
| `scripts/research-gate.py` | Every source in `docs/research/SOURCES.toml` has been examined and has a written finding |
| `scripts/eight-step-gate.py` | Eight-step evidence is complete; `build` needs ①–⑥, `flash` needs ①–⑦ plus the ⑧ prediction |
| `scripts/porting-gate.py` | `porting.toml` matches the official schema; the README table matches the data |
| `scripts/render-eight-step-table.py --check` | README table matches `EIGHT-STEPS.toml` |

## Working discipline

1. **Eight-step pipeline**: same model → official → reverse engineering → wide search →
   plan → deep dive → local verification → on device. No flashing until a step is complete.
   See [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md).
2. **Check the official component catalog first**: before writing a driver, search
   `UniXNU/components.toml` and the
   [driver repository list](https://unixnu.com/zh/drivers/repositories) to avoid
   reimplementing an existing wheel.
3. **Record every pitfall**: [`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md).
4. **Commit changes promptly and push milestones.**

## Data safety

- Bring-up uses `fastboot boot` only (temporary RAM boot); **no partition is ever flashed**.
- XNU root/Data lives on a separate `unixnu` partition and never touches Android `userdata`.
- **Never run** `fastboot flash persist` or `flash all` (permanent TEE key damage).

## License

Device-level code is BSD-2-Clause-Patent. Imported components keep their own SPDX
identifiers and original licenses. Third-party sources are listed in
[`CREDITS.md`](CREDITS.md).
