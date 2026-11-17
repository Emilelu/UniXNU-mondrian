# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

**当前目标：iOS 16.6.1（20G81）/ darwin22 上跑通完整硬件。**

[English](README_EN.md)

> 最后更新：2026-11-16。详细状态与变更记录见
> [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md)。

## 八步流程进度

<!-- EIGHT-STEP-TABLE:BEGIN -->
| 硬件 | ① 同型 | ② 官方 | ③ 反编译 | ④ 广域 | ⑤ 方案 | ⑥ 深挖 | ⑦ 核验 | ⑧ 上机 | 当前状态 |
|---|---|---|---|---|---|---|---|---|---|
| **触摸（Goodix GT9916R / BERLIN）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **GPU（Adreno 730v3 / Metal）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **storage** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **display** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **bootchain** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **八步全通** |
| **buttons** | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **bluetooth** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **wifi** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | 进行中 |
| **audio** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | **卡在 ⑦ 核验** |
| **battery** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **充电 / 电池协议（qti_battery_charger + pmic_glink）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| **thermal** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ◐ | ✅ | device-verified |
| CPU | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 电源 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 诊断 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| USB | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 基带 | — | — | — | — | — | — | — | — | planned |
| DSP | — | — | — | — | — | — | — | — | planned |

> ✅ 完成　◐ 部分　❌ 未完成　— 未建立记录
>
> 表格由 `scripts/render-eight-step-table.py` 从 `docs/research/EIGHT-STEPS.toml` 生成，`--check` 可校验 README 是否与数据一致。
> 八步定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。
<!-- EIGHT-STEP-TABLE:END -->

## 构建

```bash
./unixnu build kernel -D .
```

产物：`build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong`。

本地构建脚本位于工作区（不在仓库内），流程见
[`docs/engineering/ENVIRONMENT.md`](docs/engineering/ENVIRONMENT.md)。

## 门禁

构建/刷机前由两层检查把关，任一失败即中止：注册表 `scripts/check-rules.py`
执行 [`docs/engineering/RULES.toml`](docs/engineering/RULES.toml) 里登记的全部门禁
（铁则、坑门禁、上游研判、输入同步、快照 tag 等，当前 84 条）；严格构建入口
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
| [`docs/engineering/FIRMWARE-REBUILD.md`](docs/engineering/FIRMWARE-REBUILD.md) | 固件卷重建手册：谁在构建、为什么同源同字节、现场两个卷、P-154 现状与重建实验协议 |
| [`docs/engineering/HARD-RULES.md`](docs/engineering/HARD-RULES.md) | 铁则 ★1–★37 |
| [`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md) | 坑记录 P-01–P-230 |
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
