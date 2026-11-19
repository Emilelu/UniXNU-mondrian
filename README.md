# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

> **Branch `feat/ios27`:** iOS **27.0.1 (24A446)** as an **iPhone 16 Pro Max (iPhone17,2)**, arm64e, on xnu-12377 with the Darwin 26 calls. `main` remains the iOS 16.6.1 (20G81) port. Read
> [`docs/engineering/IOS27.md`](docs/engineering/IOS27.md) for the profile, the inputs and the phase gates.

[English](README_EN.md)

> **蓝牙基线的边界（feat/bt-ios27-port）：** 这一支只有内核与设备树。
> `[payload.runtime]` 未启用、0521 只是 blob stub，所以「iOS 27 基线」
> ≠「iOS 27 蓝牙可跑」。见 [`docs/plans/BT-IOS27-PORT.md`](docs/plans/BT-IOS27-PORT.md) §5.3。

> 最后更新：2026-11-16。详细状态与变更记录见
> [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md)。
>
> **2026-11-16 重新审视**：见[审计报告](docs/audits/REASSESSMENT-2026-11-16.md)。WiFi c7 停在硬件 SBL/READY，BT d7 在 NVM 阶段总预算超时，ADSP 早期发布链曾缺少 rail 保护，owner 分支已恢复拒绝并提供宿主轨迹；功能实验暂缓，按报告中的条件继续。
> 下表是本分支八步台账的生成视图，不是镜像放行证。`parked` 项可能被 flash 门禁略过，表中的「可刷机」不能单独授权上机；必须核对镜像所属分支、实际选中的硬件与实验预测。历史通过也不代表当前 HEAD 已重建上机。

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

实验构建统一使用本仓库的 `scripts/build-strict.sh`。先核对所属源树与隔离的输入/输出目录、提交并推送，再提供真实的固件卷：

```bash
K60_REPO="$PWD" K60_DEVICE_INPUT="/path/to/isolated-device-input" \
K60_OUT="/path/to/isolated-out" \
bash scripts/build-strict.sh <experiment-tag> --fd /path/to/verified.fd
```

以上路径为占位符，不可原样执行。构建日志中的成功终态、`kernel.macho` 新哈希和镜像 manifest 必须同时核对；包装脚本退出 0 不单独代表构建成功。环境与产物路径见
[`docs/engineering/ENVIRONMENT.md`](docs/engineering/ENVIRONMENT.md)。
磁盘余量与 WSL 虚拟盘回收由门禁自动检查（`hard-41`），清理流程见
[`docs/engineering/DISK-HYGIENE.md`](docs/engineering/DISK-HYGIENE.md)。

## 门禁

构建/刷机前由两层检查把关，任一失败即中止：注册表 `scripts/check-rules.py`
执行 [`docs/engineering/RULES.toml`](docs/engineering/RULES.toml) 里登记的全部门禁
（铁则、坑门禁、上游研判、输入同步、快照 tag 等，当前 136 条）；严格构建入口
`scripts/build-strict.sh` 内嵌下列检查：

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

`check-readme.py` 把本表与 `build-strict.sh` 的内嵌门禁逐名对账：新增门禁而不
更新本表、或本表点名不存在的脚本，都直接失败。

## 数据安全

- bring-up 全程只用 `fastboot boot`（RAM 临时引导），**不 flash 任何分区**。
- XNU 的 root/Data 使用独立 `unixnu` 分区，不写安卓 `userdata`。
- **绝对禁止** `fastboot flash persist` / `flash all`（TEE 密钥永久损坏）。

## 作业纪律

1. **八步流水线**：同型 → 官方 → 反编译 → 广域 → 方案 → 深挖 → 核验 → 上机。
   缺一步不得上机。定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。
2. **先查官方组件目录**：动手写驱动前必须查 `UniXNU/components.toml`
   与 [驱动仓库列表](https://unixnu.com/zh/drivers/repositories)，避免重复造轮子。
3. **坑必记录**：[`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md)。
4. **改动后及时 commit，阶段性成果及时 push。**

## 结构

| 路径 | 内容 |
|---|---|
| `board.toml` | `schema_version = 2` 设备配置与组件选择 |
| `porting.toml` | 14 个子系统的记录（官网设备页数据源） |
| `feeds.toml` | 固定的 SoC 源 |
| `local.toml.example` | 本地路径配置模板（复制为 `local.toml`，已被 gitignore） |
| `configs/mondrian_defconfig` | 设备内核设置 |
| `dts/mondrian.dts` | 内存、CPU、外设 |
| `patches/xnu/` | 设备补丁，顺序见 `patches/xnu/series` |
| `patches/uefi/` | UEFI 固件补丁（记录用，不进内核构建）|
| `scripts/` | 构建与检查工具（全部门禁与检查，见「门禁」） |
| `drivers/` | PongAdreno / NativeUfs / NativeRamBlock / ArmCpu / ArmDTPlatform / PongMetal |
| `docs/engineering/` | 铁则、坑记录、硬件真值、八步规范 |
| `docs/research/` | 八步证据（`EIGHT-STEPS.toml`）与研究清单（`SOURCES.toml`） |

## 四层仓库

| 层 | 仓库 | 内容 |
|---|---|---|
| 框架 | [Emilelu/UniXNU](https://github.com/Emilelu/UniXNU)（官方上游 [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU)） | `unixnu` 命令、共享脚本、组件目录 |
| SoC | [Emilelu/UniXNU-sm8475-common](https://github.com/Emilelu/UniXNU-sm8475-common) | `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi` |
| 设备 | [Emilelu/UniXNU-mondrian](https://github.com/Emilelu/UniXNU-mondrian)（本仓库） | `board.toml`、`dts/mondrian.dts`、`patches/xnu/` |
| 固件 | [uefi-mondrian](https://github.com/Emilelu/uefi-mondrian) | EDK2 / Mu-Silicium 构建树 |

## 分支

| 分支 | 用途 |
|---|---|
| **`main`** | 主线（默认分支），所有可工作的阶段性成果都合到这里 |
| `feat/first-frame-20261107` | 历史里程碑：iOS 16.6.1 用户态首帧（独立历史线） |
| `chore/archive-darwin24-main-20261103` | 已废弃的 darwin24（iPadOS 18）路线（归档保留） |

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/INDEX.md`](docs/INDEX.md) | **文档总入口**：阅读顺序、全量目录、门禁命令 |
| [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md) | 硬件状态明细与变更记录 |
| [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md) | 八步流程规范 |
| [`docs/engineering/BOOT-PROCEDURE.md`](docs/engineering/BOOT-PROCEDURE.md) | 启动流程唯一入口（铁则 8）：先挂串口抓取再 `fastboot boot` |
| [`docs/engineering/IOS-SCOPE.md`](docs/engineering/IOS-SCOPE.md) | iOS 迁移边界：只保留可转移的活（用户 2026-11-19 决定） |
| [`docs/engineering/BRANCH-INVENTORY-20261119.md`](docs/engineering/BRANCH-INVENTORY-20261119.md) | 未合入 main 的分支清单：按线分组编号，逐条确认合入或归档 |
| [`docs/engineering/FIRMWARE-REBUILD.md`](docs/engineering/FIRMWARE-REBUILD.md) | 固件卷重建手册：谁在构建、为什么同源同字节、现场两个卷、P-154 现状与重建实验协议 |
| [`docs/engineering/HARD-RULES.md`](docs/engineering/HARD-RULES.md) | 铁则 ★1–★37 |
| [`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md) | 坑记录 P-01–P-259 |
| [`docs/engineering/GPU-IOSURFACE-ROOT-CAUSE.md`](docs/engineering/GPU-IOSURFACE-ROOT-CAUSE.md) | GPU Metal 根因：`IOSurfaceRoot` 注册名不匹配 |
| [`docs/engineering/TOOLBOX.md`](docs/engineering/TOOLBOX.md) | 可复用工具与脚本 |
- [`docs/engineering/REPO-MAP.md`](docs/engineering/REPO-MAP.md) —— 仓库与目录登记表：三个组件仓库路径、构建副本、yibiya 镜像、打镜像该用哪个 DTB
- [`docs/engineering/BATTERY-INTEGRATION.md`](docs/engineering/BATTERY-INTEGRATION.md) —— 电池栈编译集成：构建脚本改动、defconfig 开关、宏链路、归档构建时机
- [`docs/engineering/DIVISION-OF-LABOR.md`](docs/engineering/DIVISION-OF-LABOR.md) —— 上下游分工与仓库覆盖：23 跟踪 / 48 同步 / 3 pick
| [`docs/research/EIGHT-STEPS.toml`](docs/research/EIGHT-STEPS.toml) | 逐硬件的八步证据（门禁数据源） |
| [`docs/research/SOURCES.toml`](docs/research/SOURCES.toml) | 必须考察的参考源清单（门禁数据源） |
| [`CREDITS.md`](CREDITS.md) | 贡献者与全部外部来源 |
| [`AGENTS.md`](AGENTS.md) | 仓库级 agent 约定 |
| [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) | 第三方许可证声明 |
| [`v98-source.md`](v98-source.md) | v98 构建的源码集快照说明 |
| [`README_EN.md`](README_EN.md) | English |

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证。
第三方来源见 [`CREDITS.md`](CREDITS.md)。
