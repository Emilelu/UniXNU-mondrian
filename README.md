# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

**当前目标：iOS 27.0.1（24A446，iPhone17,2 身份、arm64e）在 xnu-12377（Darwin 25.5.0）上走到 SpringBoard，再按线回修硬件。**

[English](README_EN.md)

> 最后更新：2026-11-25。状态明细见 [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md)，总方案见 [`docs/engineering/PORTING-PLAN.md`](docs/engineering/PORTING-PLAN.md)，工作流见 [`docs/engineering/WORKFLOW.md`](docs/engineering/WORKFLOW.md)。

## 现状

- `main` 是 27 线唯一基线；iOS 16.6.1（20G81）线已归档为 `archive/ios16-20261120`，仍可用 `--os ipados-16.6.1-20G81` 构建。
- 27 内核已能打印完整文本（r290n，`boot.img 311f4f54…`）；r313h 首次把 source-storage 链接进内核（`boot.img 932d50ad…`），但上机全绿屏、console 0 字节，正在按单变量二分定位（首嫌疑 `0580` GIC 补丁）。
- `unixnu` 分区已写入 27 三窗口镜像（34,359,738,368 B；OS / SystemOS / Data 四段 `cmp -n` 全部 MATCH）。
- 飞行前置条件与未决 blocker 见 [`docs/engineering/IOS27-FLIGHT-BLOCKERS.toml`](docs/engineering/IOS27-FLIGHT-BLOCKERS.toml)；未满足前不构建、不上机。

## 八步流程进度

<!-- EIGHT-STEP-TABLE:BEGIN -->
| 硬件 | ① 同型 | ② 官方 | ③ 反编译 | ④ 广域 | ⑤ 方案 | ⑥ 深挖 | ⑦ 核验 | ⑧ 上机 | 当前状态 |
|---|---|---|---|---|---|---|---|---|---|
| **触摸（Goodix GT9916R / BERLIN）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **GPU（Adreno 730v3 / Metal）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **存储（UFS 3.1 / unixnu 三窗分区）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **显示（m11a 面板 / DSI / 背光 / 120Hz）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **亮度（12-bit DBV / 背光一致性）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **固件与启动链（UEFI / DarwinBoot / payload）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **按键（power / volume）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **蓝牙（QCA6490 / HCI over UART）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 已暂停（flash 门禁不选择） |
| **无线（QCA6490 / PCIe + MHI）** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | 已暂停（flash 门禁不选择） |
| **音频（WCD938x + AW88261 / ADSP PAS1）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | 已暂停（flash 门禁不选择） |
| **电池（IOPMPowerSource / PMIC GLINK）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **充电 / 电池协议（qti_battery_charger + pmic_glink）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **USB（DWC3 复合设备 / 控制台 / 回环）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **thermal** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ◐ | ✅ | device-verified |
| **蜂窝（X70 modem / DXE 载具 / QRTR）** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | 进行中 |
| **壁纸 / 换壁纸后进不去系统 / 桌面小组件（SpringBoard·PosterBoard·WallpaperKit）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| CPU | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 电源 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 诊断 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| USB | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 基带 | — | — | — | — | — | — | — | — | planned |
| DSP | — | — | — | — | — | — | — | — | planned |

> ✅ 完成　◐ 部分　❌ 未完成　— 未建立记录
>
> 表格由 `scripts/render-eight-step-table.py` 从 `docs/research/EIGHT-STEPS.toml` 生成，`--check` 可校验两份 README 是否与数据一致。
> 八步定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。
<!-- EIGHT-STEP-TABLE:END -->

## 构建

27 线：

```bash
K60_DEVICE_INPUT=/path/to/isolated-device-input \
K60_OUT=/path/to/isolated-out \
UNIXNU=/opt/k60/trees/ios27-fw UNIXNU_OUT=/opt/k60/trees/ios27-out \
UNIXNU_UEFI=/path/to/uefi-mondrian \
bash scripts/build-ios27-linux.sh
```

构建成功必须同时核对 `kernel.macho` 新哈希、`payload.img` 的 declared transform 与 `boot.img` manifest；包装脚本退出 0 不单独代表成功。
16.6.1 归档线仍用 `scripts/build-strict.sh <tag> --fd <verified.fd>`（实验构建唯一入口）。

## 门禁

`scripts/check-rules.py` 执行 [`docs/engineering/RULES.toml`](docs/engineering/RULES.toml) 里登记的全部门禁（铁则、坑门禁、上游研判、输入同步、快照 tag 等，当前 207 条）；`build-strict.sh` 还内嵌下列检查：

<!-- GATE-TABLE:BEGIN -->
| 门禁 | 检查内容 |
|---|---|
| `scripts/check-build-env.py` | 构建环境完整（Darwin 工具链 shim、fakeroot，P-185） |
| `scripts/eight-step-gate.py` | 八步证据完整；`build` 需 ①–⑥，`flash` 需 ①–⑦ + ⑧ 预测 |
| `scripts/check-kernel-archives.py` | 强制链接的归档确实进了内核（P-190） |
| `scripts/check-metal-blob.py` | Metal 插件容器自洽（magic/条目数/对齐/不重叠） |
| `scripts/check-image-args.py` | 镜像命令行 ≤607 B、无 `debug=1`/`epoch=1`、无未声明参数 |
| `scripts/verify-boot-image.py` | boot 镜像可解包、kernel/payload 槽位与 manifest 一致 |
| `scripts/render-eight-step-table.py --check` | README 八步表与 `EIGHT-STEPS.toml` 一致 |
| `scripts/check-docs.py` | 文档索引与链接完整（★36） |
| `scripts/check-readme.py` | README 双语互链、日期不早于 STATUS、门禁表不过时 |
<!-- GATE-TABLE:END -->

`check-readme.py` 会把上表与 `build-strict.sh` 的内嵌门禁逐名对账：新门禁不写进表、或表里点名不存在的脚本，都直接失败。

## 数据安全

- 只用 `fastboot boot`（RAM 临时引导），**不 flash 任何分区**。
- XNU 的 root/Data 使用独立 `unixnu` 分区，不写安卓 `userdata`。
- **绝对禁止** `fastboot flash persist` / `flash all`（TEE 密钥永久损坏）。

## 作业纪律

1. **八步流水线**：同型 → 官方 → 反编译 → 广域 → 方案 → 深挖 → 核验 → 上机；缺一步不得上机（[`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)）。
2. **先查已有实现**：动手写驱动前查 `UniXNU/components.toml`、[驱动仓库列表](https://unixnu.com/zh/drivers/repositories)，并过 `scripts/check-capability-reuse.py`（铁则 20）。
3. **坑必记录**：[`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md)，坑号先由 Lead 在 [`docs/engineering/PITFALL-IDS.md`](docs/engineering/PITFALL-IDS.md) 分配。
4. **改动及时 commit、阶段性成果及时 push**；禁止强推与 `worktree prune`/`gc`/`repack`（铁则 18、P-203）。
5. **上机由 Lead 统一调度**；每次飞行先挂串口/屏幕取证，再 `fastboot boot`。

## 结构

| 路径 | 内容 |
|---|---|
| `board.toml` | `schema_version = 2` 设备配置、组件选择与 `os_overrides` |
| `porting.toml` | 子系统记录（官网设备页数据源） |
| `configs/` | `mondrian_defconfig`（16.6.1）与 `mondrian_ios27_defconfig`（27） |
| `dts/mondrian.dts` | 板级设备树（SoC 节点来自 feed） |
| `patches/xnu-12377/` | 27 补丁与 `series`（四层之一） |
| `patches/xnu/` | 16.6.1 归档补丁与 `series` |
| `drivers/` | PongAdreno / NativeUfs / NativeRamBlock / ArmCpu / ArmDTPlatform |
| `kits/` | 本仓携带的 kit（`VerifiedRoot`、`mondrian` 探针） |
| `scripts/` | 构建、门禁与一次性工具 |
| `docs/engineering/` | 铁则、坑记录、状态、方案与工作流 |
| `docs/research/` | 八步证据、参考源账本与研究文档 |

## 四层仓库

| 层 | 仓库 | 内容 |
|---|---|---|
| 框架 | [Emilelu/UniXNU](https://github.com/Emilelu/UniXNU)（上游 [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU)） | `unixnu` 命令、共享脚本、组件目录 |
| SoC | [Emilelu/UniXNU-sm8475-common](https://github.com/Emilelu/UniXNU-sm8475-common) | `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi` |
| 设备 | [Emilelu/UniXNU-mondrian](https://github.com/Emilelu/UniXNU-mondrian)（本仓库） | `board.toml`、`dts/mondrian.dts`、`patches/` |
| 固件 | [Emilelu/uefi-mondrian](https://github.com/Emilelu/uefi-mondrian) | EDK2 / Mu-Silicium 构建树 |

> 四仓均已 GitHub archive；需要推送前先 unarchive。

## 分支

`main` 是唯一基线；历史线以 `archive/` 开头（如 `archive/ios16-20261120`）。所有未合入分支登记在 [`docs/engineering/BRANCH-REGISTRY.toml`](docs/engineering/BRANCH-REGISTRY.toml)，含 purpose / merge_plan / flight 状态；未登记的新分支会被 `check-branch-registry.py` 拒绝。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/INDEX.md`](docs/INDEX.md) | 文档总入口：阅读顺序、全量目录、门禁命令 |
| [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md) | 硬件状态与变更记录 |
| [`docs/engineering/PORTING-PLAN.md`](docs/engineering/PORTING-PLAN.md) | 移植总方案：四层、启动链、缺口、产物与回退 |
| [`docs/engineering/WORKFLOW.md`](docs/engineering/WORKFLOW.md) | 工作流：铁则、八步、构建/上机、DSH 多线协作 |
| [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md) | 八步流程规范 |
| [`docs/engineering/BOOT-PROCEDURE.md`](docs/engineering/BOOT-PROCEDURE.md) | 启动流程唯一入口（铁则 8） |
| [`docs/engineering/IOS-SCOPE.md`](docs/engineering/IOS-SCOPE.md) | iOS 迁移边界：只保留可转移的活 |
| [`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md) | 坑记录 P-01–P-325 |
| [`docs/engineering/HARD-RULES.md`](docs/engineering/HARD-RULES.md) | 铁则 ★1–★37 |
| [`CREDITS.md`](CREDITS.md) | 贡献者与全部外部来源 |
| [`README_EN.md`](README_EN.md) | English |

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证。
第三方来源见 [`CREDITS.md`](CREDITS.md)。
