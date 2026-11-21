# 文档总索引（INDEX）

> 唯一文档入口。目标：新接手的人 5 分钟内知道**先读什么、文档在哪、哪些已过时**。
>
> 最后更新：2026-11-12。本索引由 `scripts/check-doc-links.py` 校验：文中每个相对链接
> 必须指向真实存在的文件。

---

## 0. 先读这五份

| 顺序 | 文档 | 为什么先读 |
|---|---|---|
| 1 | [`../README.md`](../README.md) / [`../README_EN.md`](../README_EN.md) | 设备身份、八步进度、仓库结构、构建入口 |
| `engineering/REPO-MAP.md` | **仓库与目录登记表**：三个组件仓库路径、构建副本、yibiya 镜像、打镜像该用哪个 DTB |
| 2 | [`engineering/STATUS.md`](engineering/STATUS.md) | 当前硬件状态明细与变更记录 |
| 3 | [`engineering/EIGHT-STEP-SPEC.md`](engineering/EIGHT-STEP-SPEC.md) | 八步流程的完整定义（目的/必做/证据/通过条件/反模式） |
| 4 | [`engineering/HARD-RULES.md`](engineering/HARD-RULES.md) | 铁则 ★1–★35，从踩过的坑提炼的可执行规则 |
| 5 | [`engineering/PITFALLS.md`](engineering/PITFALLS.md) | 坑记录 P-01–P-130，每条含症状/根因/判据/教训 |

**要做触摸/GPU 之前，额外读：**
- [`research/EIGHT-STEPS.toml`](research/EIGHT-STEPS.toml) — 该硬件的八步证据，⑦ 未通过不得刷机
- [`research/SOURCES.toml`](research/SOURCES.toml) — 必须考察的参考源清单

---

## 1. 目录结构

```
docs/
├─ INDEX.md              本文件
├─ engineering/          ★ 核心工程文档（铁则、坑、硬件真值、八步规范、现状）
├─ research/             ★ 八步证据与研究清单（EIGHT-STEPS.toml / SOURCES.toml）
├─ state/                工作状态快照（会话指令、下一步、可信度台账）
├─ plans/                实施方案
├─ audits/               对比审计与诊断记录
├─ reference/            长期参考（决策、问题、USB、历史台账）
├─ ops/                  运行手册
└─ archive/              已过时/被取代的交接与旧索引
```

---

## 2. engineering/ —— 核心工程文档

| 文件 | 一句话摘要 |
|---|---|
| [`STATUS.md`](engineering/STATUS.md) | 当前硬件状态明细 + 2026-11-11/11-12 变更记录（README 的详细版） |
| [`EIGHT-STEP-SPEC.md`](engineering/EIGHT-STEP-SPEC.md) | 八步流程规范：① 同型 ② 官方 ③ 反编译 ④ 广域 ⑤ 方案 ⑥ 深挖 ⑦ 核验 ⑧ 上机 |
| [`FIRMWARE-REBUILD.md`](engineering/FIRMWARE-REBUILD.md) | **固件卷重建手册**：谁在构建、为什么它不可复现、Mu_Basecore 必须停在记录的 pin 上（P-217）、现场四个卷、P-154 已关闭与下次重建的实验协议 |
| [`BOOT-PROCEDURE.md`](engineering/BOOT-PROCEDURE.md) | **启动流程唯一入口**（铁则 8）：门禁 → 先挂串口抓取 → `fastboot boot` → 判读"控制台没出现"=早启动挂死 |
| [`HARD-RULES.md`](engineering/HARD-RULES.md) | 铁则 ★1–★35，每条含来源、硬规则、判别方法 |
| [`PITFALLS.md`](engineering/PITFALLS.md) | 坑记录 P-01–P-130：症状 → 真因 → 判别 → 教训 |
| [`TAGS.md`](engineering/TAGS.md) | tag 策略：只留 boot-proven、main 基线、版本里程碑三种 |
| [`PITFALL-TO-RULE-INDEX.md`](engineering/PITFALL-TO-RULE-INDEX.md) | 坑 → 铁则反查表 |
| [`TOOLBOX.md`](engineering/TOOLBOX.md) | 可复用工具与脚本清单 |
| [`PLAYBOOKS.md`](engineering/PLAYBOOKS.md) | 操作手册 PB-1–PB-10 |
| [`ANDROID-HW-TRUTH.md`](engineering/ANDROID-HW-TRUTH.md) | Android 实机实测的硬件真值（协议、寄存器、固件路径） |
| [`K60-TOUCH-DT-EVIDENCE.md`](engineering/K60-TOUCH-DT-EVIDENCE.md) | K60 触摸节点的 DT 权威数据 |
| [`K60-TOUCH-CHECKLIST.md`](engineering/K60-TOUCH-CHECKLIST.md) | 触摸八步核对清单 |
| [`TOUCH-STATEMACHINE.md`](engineering/TOUCH-STATEMACHINE.md) | 官方 Goodix 驱动状态机逐段提取（481 行） |
| [`ENVIRONMENT.md`](engineering/ENVIRONMENT.md) | 构建环境、工具链路径、SSH 主机 |
| [`LOCAL-ASSETS.md`](engineering/LOCAL-ASSETS.md) | 本地资源索引（参考仓库、固件、镜像） |
| [`REPO-INVENTORY.md`](engineering/REPO-INVENTORY.md) | 全部 git 仓库清单与用途 |
| [`README.md`](engineering/README.md) | 本目录的简介与阅读顺序 |

---

## 3. research/ —— 八步证据与研究清单

| 文件 | 说明 |
|---|---|
| [`EIGHT-STEPS.toml`](research/EIGHT-STEPS.toml) | **门禁数据源**：逐硬件的 ①~⑧ 证据、⑦ 三类核验、⑧ success/failure 预测 |
| [`SOURCES.toml`](research/SOURCES.toml) | **门禁数据源**：每个子系统必须考察的参考源，逐条填 `examined` + `finding` |
| `01-same-hardware.md` | 触摸调研 ① 同型 |
| `02-official-docs.md` | 触摸调研 ② 官方 |
| `03-reverse-and-device-data.md` | 触摸调研 ③ 反编译/取证 |
| `04-device-data.md` | 触摸调研 ④ 设备数据 |
| `05-plan.md` | 触摸调研 ⑤ 方案 |
| `06-deep-dive.md` | 触摸调研 ⑥ 深挖 |
| `07-verification.md` | 触摸调研 ⑦ 核验 |
| `08-on-device.md` | 触摸调研 ⑧ 上机 |
| `09-CLOCK-FIX-PLAN.md` | GENI 时钟修复方案 |
| `10-SE-HANG-ROUND3.md` | SE 挂死第三轮诊断 |
| `wifi/RESEARCH.md` | **WiFi 八步 ①②③**：Pong 同 SoC 同芯片的 PCIe0 冷启动、PWF2 固件包、K60 本机真值 |
| `wifi/BOOT-DEATH-BISECT.md` | **WiFi series 死因考古（静态）**：0618 MHI 注入不存在、0011 stage 门与 229 series 均被对照排除，剩余差异与缺失的对照格子 |
| `wifi/BLOB-RESIDENCY.md` | **11.19 MB 固件 blob 与装载边界**：最窄余量 1.14×（117 MB 镜像 vs `ReadFile` 128 MB），可证伪判断、五格判别矩阵、全家族实测段表与 `z0` 上机判决（silent） |
| `audio/RESEARCH.md` | **音频八步 ①②③**：Pong 的 ADSP PAS1 + AudioReach/PRM + WCD938x（约 107 KB）、官方无组件、K60 待测项 |
| `audio/CODEC.md` | **音频 codec 侧**：WCD938x 同型判定、live FDT 逐条、供电 rail 表、DT 映射表 |
| `audio/SOUNDWIRE.md` | **音频 SoundWire 侧**：宏与 SWR master 地址、寄存器表、PRM 前置、io_submap 预算 |
| `audio/TDMS.md` | **音频 TDM 布线（端口结论已过时，见 VENDOR-AUDIO-CONFIG.md）**：AFE 参数结构体与启动顺序（编码器 `PongAudioAfe.h`）、dai-tdm DT 逐字、与 phk110 的差异、留给 PAS1 线的接口清单 |
| `audio/VENDOR-AUDIO-CONFIG.md` | **音频后端真值**：扬声器走 TERT TDM RX（AFE 0x9020 / 组 0x9120）、引脚 gpio121/123/122/124、24-bit S24_LE、旧 PRI 结论为什么错、slot 与位时钟的闭合 |
| `audio/VENDOR-AUDIO-KERNEL.md` | **厂商音频内核真值**：TDM 参数包结构（36 B / 28 B）、时钟走 PRM 请求（76 B、12.288 MHz、0x204、attribute 4）、2 slots × 32 bit 判定、ACDB 为什么不需要 |
| `audio/PAS1-AUDIO-REQUIREMENTS.md` | **音频对 PAS1 的依赖**：GPR/APM 服务注册与 GLINK 独占的仲裁（adsp_apps 560x20、复用同一 QcomGlink 实例第二槽）、PAS1 未就绪时的五级降级与具名错误、AFE 参数在 publish 之后下发、provider 必须为 audio 保证的四条（§5：单实例多槽 / 建槽时机 / 独占语义改写 / 发包时机）、0504 三处 GPR 常量的修正与宿主断言（§1.3）、载具 ABI 与音频的零耦合（§0.1）、GLINK 独占两案仲裁与代价（§1.2）、-1000 的具体表现与 codec-only 路径（§2.1）、AFE 三道门与重试边界（§3.1/§3.2）、§9 provider 交接可勾选清单、TDMS §8 五条的机器可读版 |
| `audio/AMPS.md` | **音频功放侧**：AW882xx 判定、GENI I2C 路径、探针方案 A1–A7、上机 run 1、A5 选型与 ACF 配置档（§8）、寄存器回放层（§9）、run 2 判据 `judge-audio-capture.py --replay`（§9.6） |
| `audio/IOS27-MIGRATION.md` | **音频 27 迁移清单**：可搬 18 纯 C + 2 胶水 + 1 只随测试走的 `PongAudioAfe.h`、搬不动的补丁/blob/HAL、`check-audio-migration.py --copy/--compile` 门禁与 979 例回归 |
| `audio/IOS27-WIRING.md` | **音频 27 接线清单**：谁调用 probe/play、每步的证明日志、GLINK 只留调用方契约、AFE 在 27 不存在的证据指针、`PONG` 机配置是第零道闸 |
| `audio/IOS27-USERLAND.md` | **音频 27 用户态重接**：sheng 的 `ShengAudioAbi.h` 接口（三块内存、48 kHz/480 帧/65,536 帧环、诊断页）、HAL 注入的 addon4 槽、182 例 audioreach host 基线、与内核侧的接缝 |
| `audio/LANE-BOUNDARIES.md` | **音频线的边界与越界记录**：四条不变边界（上机只在 Lead、不合 main、不动设备、提交形状）、一次越界推 `k60-gates` main 的事实与后果、本线判据速查表 |
| `audio/IOS27-SHENG-REFS.md` | **sheng 内核与驱动参考清单**：同一基准的 25 项补丁逐条判 audio/partial/no（1 条新增音频、1 条含既有音频上下文、23 条无直接新增音频），K60 设备系列对照、页表与弱链接证据边界、GENI FIFO 与功放型号差异、同树引用门禁 |
| `audio/IOS27-PAC.md` | **音频接缝与 PAC**：arm64e 的原生密钥补丁怎么给内核装上 PAC、音频代码的 EL1 特权面逐行判定、io 表与弱符号调用在插桩前后各是什么形态、以及 sheng 的 addon-mount 补丁为什么不依赖 PAC |
| `audio/IOS27-STAGE0-STATE.md` | **iOS 27 stage-0 的音频位置**：board profile 与缺失的 conf-files 钩子怎么让音频不在构建里、三分钟自证的命令与各 checker 的 rc 语义，以及为什么「0 符号」是设计读数而不是回归 |
| `audio/PRELINK-AUDIO-RESIDUE.md` | **预链接残留里的音频**：IOAudio2Family、AppleM2ScalerCSCDriver、IOAVFamily 的 21 个槽逐个落到目标/锚点、stage-0 可达性的静态边界，以及为什么 Pong 的驱动不能补 Apple kext 的导入槽 |
| `audio/GLINK-MULTISLOT.md` | **音频对 GLINK 的多槽需求**：QcomGlink 的环几何 / doorbell / 打点位置、每槽独立 rx 分发的逐函数核对（唯一单槽假设是数组长度）、`QCOM_GLINK_MAX_CHANNELS` 2 与 `MAX_LOCAL_INTENTS` 20 已落地、`K60AudioGlink` 音频桥（含 `k60_audio_glink_send()` 发送路径与 GPR `GET_SPF_STATE` 首发）与 376 条宿主断言、哪些要等 provider 真 lease 才能上机、provider 落地后音频侧要改的三处 |
| `battery/RESEARCH.md` | **电池 ①②④**：ADSP GLINK 交接租约的四标志、解锁链、单位转换 |

| [`battery/HANDOFF-PUBLISH.md`](research/battery/HANDOFF-PUBLISH.md) | **ADSP 交接发布者**：早期钩子、持续所有权、只读live发现/104字节发布、通知资格与离线测试；平台adapter已接线，板级资源与停机证明仍缺 |
| [`battery/INTEGRATION-ORDER.md`](research/battery/INTEGRATION-ORDER.md) | **ADSP 交接集成时间轴**：六步与 IOKitBSDInit/电池/root 挂载的前后界限、默认关闭门控、零交接访问宿主断言和未来检查清单 |
| [`battery/PAS1-PROVIDER-CONTRACT.md`](research/battery/PAS1-PROVIDER-CONTRACT.md) | **PAS1 provider 契约**：acquire/revalidate/abort 参数、返回码、持续所有权及未就绪行为；真实 provider 仍为 battery/audio/charger 共享阻塞 |
| [`battery/CARRIER-BLOB-PLAN.md`](research/battery/CARRIER-BLOB-PLAN.md) | **ADSP 生产 blob 契约**：冻结顺序 K60A ABI、26文件/23,506,184字节、生成器/校验器与host断言要求；Lead负责build-strict/归档接线，完整platform adapter另见下文，板级ownership服务未安装 |
| [`battery/PAS1-PROVIDER-INSTALL.md`](research/battery/PAS1-PROVIDER-INSTALL.md) | **PAS1 平台安装**：完整回调/source/log矩阵、runtime安装点、native SCM/映射安全、31/34宿主场景；板级ownership/资源/stopped服务仍缺，硬件未验证 |
| `charger/01-SYMBOL-MAP.md` | **充电器 ③ 反编译**：`qti_battery_charger_main_m81.ko` 的 675 个符号、232 个函数、对外依赖只有 pmic_glink/power_supply/typec/debugfs/panel |
| `charger/02-GLINK-CONTRACT.md` | **充电器 GLINK 契约**：client `battery_charger`/id `0x800a`、16 B 头、opcode 表、四张 prop map；104 B handoff 只覆盖 L0；§10 钉死 ADSP 侧名字三元组寻址（无端口/GUID） |
| `charger/03-REVERSE.md` | **充电器关键路径**：probe/write/callback 跳转表/subsys-up/ship mode，逐条附 objdump 原始片段 |
| `charger/04-PROP-MAP.md` | **充电器属性映射**：四张 prop map 的 .rodata 偏移与 25/13/7/187 条目、wire prop_id 实为该域 map 的**下标**、与 `K60Battmgr.c` 字段表 18 项逐项交叉验证 |
| `charger/05-OPEN-QUESTIONS.md` | **充电器未决结案**：+0xc 不对称、`0x37` shutdown、`0x48` 未识别、type 1/2、`check_status_work` 四条请求、无线升级 0x40–0x44/0x51，附 bcdev 字段表 30 项 |
| `charger/06-SUBSCRIPTION-CONSTANT.md` | **订阅应答常量定值**：`K60_BATTERY_NOTIFY_REPLY_TYPE = 1` / `_BYTES = 16`，依据 ADSP opcode-0x04 handler `0x60155910` 逐指令 + 四字节锚点 + 全固件 30 处 `0x800a` 组包点穷举；含生成器/测试落点与交给 touch agent 的交接段 |
| `charger/07-DEVICE-CRITERIA.md` | **充电器 ⑧ 判据**：订阅成立（`subscription-ack=1/16` → `subscribed=1`）、四属性区间（3.3–5.0 V / 0.1–6 A / 1–100 % / 0–60 °C）、与 Android 同窗口（±60 mV、±150 mA 仅 \|I\|≥100 mA、±3 pp、±3 °C，ΔT≤10 s），每条附失败行原文 |
| `display/RESEARCH.md` | **显示结论层（本板真值）**：面板 m11a 1440x3200 DSC cmd 单 DSI 三档 60·90·120、5 条供电轨、DSI `0xae94000` / PHY `0xae94400` / MDP `0xae00000`、XML 缺口与已转派的 owner |
| `storage/RESEARCH.md` | **存储结论层（本板真值）**：UFS PHY `0x1d80000` + `qcom,ufs-phy-qmp-v4-cape`、控制器 `0x1d84000` / ICE / HWKM、IRQ SPI 265、与 liuqin 的双源交叉验证 |
| `memory/RESEARCH.md` | **内存布局结论层（本板真值）**：DDR 保留区与寄存器窗口，以及跨板边界——DXE Heap `0xC7000000` 与 Kernel `0xBB000000` 绝不可跨板抄 |
| `11-KEY-EVIDENCE-RING.md` | 关键证据闭环清单 |
| `GENI-ACCESS-PRECONDITIONS.md` | GENI 引擎可访问性前置条件 |
| [`REFERENCE-INDEX.md`](research/REFERENCE-INDEX.md) | **参考仓库事实索引（人读）**：42 个参考仓库逐条 文件:行 + 可信度，按供电/音频/WiFi/触摸/显示/GPU/存储/USB/电池分区；机器可读部分同源进 `SOURCES.toml` |

> 01–08 是早期按八步逐份写的调研，`EIGHT-STEPS.toml` 是它们的结构化汇总与门禁数据源。
> 两者冲突时以 `EIGHT-STEPS.toml` 为准。

---

## 4. state/ —— 工作状态快照

| 文件 | 说明 | 状态 |
|---|---|---|
| `state/SESSION-DIRECTIVES-2026-11-07.md` | 2026-11-07 会话的用户指令总账 | 参考 |
| `state/STATE-2026-11-07.md` | 2026-11-07 的当前真相快照 | **过时**，现以 `engineering/STATUS.md` 为准 |
| `engineering/BATTERY-INTEGRATION.md` | **电池栈编译集成**：构建脚本 4 处改动、defconfig 开关、宏链路、归档构建时机、无 PAS1 时的运行时行为 |
| `BOOT-ARGS.md` | **Boot 参数参考**：每个参数的接受值/默认/陷阱，608 字节预算，三个 GPU 开关的串行依赖 |
| `state/TRUST-LEDGER.md` | 数值可信度台账（T/E/C 分级） | 参考 |
| `state/NEXT-STEPS.md` | 当时的推进顺序 | **过时** |

---

## 5. plans/ —— 实施方案

| 文件 | 说明 |
|---|---|
| `plans/GPU-ENABLE-PLAN.md` | Adreno 730 scanout 启用方案（47 KB，6 章节） |
| [`plans/BACKLOG.md`](plans/BACKLOG.md) | **白天待办**：上游追平（全动态查询）+ P0~P3 实现优先级 |
| [`plans/GPU-TODO.md`](plans/GPU-TODO.md) | **GPU/Metal 待办**：官方 AdrenoMetal 8 个性能提交、pong-metal 中间层 diff、内核侧对齐、缺失文件清单 |
| `plans/APPLY-PIPELINE.md` | 生成并写入 iOS 16 OS 窗口的完整流程 |
| `plans/K60-TOUCH-PARAMS.md` | K60 Goodix / GENI-SPI 触摸参数表 |
| `plans/120HZ-PORT-PLAN.md` | 120Hz 移植方案 |
| [`plans/WIFI-REBUILD-CHECKLIST.md`](plans/WIFI-REBUILD-CHECKLIST.md) | **WiFi 对照镜像重出核对清单**：从 origin/main 按 4.5 GiB 窗口重出，对照 mhi3/mhi4 逐字段；五条硬差异（0010 装配路径、series 224 vs 229、`.config` 开关、buttons 节点、freeze 盲区） |
| 其余 | 见目录 |

---

## 6. audits/ —— 对比审计与诊断

| 文件 | 说明 |
|---|---|
| `audits/PONG16-DIFF-AUDIT.md` | 与 pong `ios16` 分支的机械差异审计 |
| `audits/FORK-REVIEW.md` | Fork 巡查与吸收记录 |
| `audits/REFERENCE-WALL-AUDIT-2026-11-02.md` | 对照 ios-sweet-k60 已验证墙的审计 |
| `audits/USERLAND-ROUTES-2026-11-02.md` | 三种 userland 路线对比 |
| 其余 | 见目录 |

---

## 7. reference/ —— 长期参考

| 文件 | 说明 |
|---|---|
| `reference/DECISIONS.md` | 决策记录 SSOT（D-YYYYMMDD-NN） |
| `reference/ISSUES.md` | 问题台账 SSOT（I-YYYYMMDD-NN） |
| `reference/HISTORY-LEDGER.md` | commit 级历史台账 |
| `reference/USB-LOG-CHANNEL.md` | USB 内核日志通道调研 |
| 其余 | 见目录 |

---

## 8. archive/ —— 已归档

已过时或被取代的交接、旧索引与历史盘点，16 个文件。**不要作为当前依据。**

---

## 9. 仓库根部的关键文件

| 文件 | 说明 |
|---|---|
| [`../README.md`](../README.md) / [`../README_EN.md`](../README_EN.md) | 设备简介与八步进度（中英互链） |
| [`../CREDITS.md`](../CREDITS.md) | 贡献者与全部外部来源 |
| [`../porting.toml`](../porting.toml) | 14 个子系统的记录（官网设备页数据源） |
| [`../board.toml`](../board.toml) | 设备配置与组件选择 |
| [`../AGENTS.md`](../AGENTS.md) | 仓库级 agent 约定 |
| `research/SUBAGENT-DELIVERABLES.md` | **Subagent 交付物台账**：落库文件 + 产出断言 + 提交，门禁验证断言成立 |
| `engineering/DIVISION-OF-LABOR.md` | **上下游分工与仓库覆盖**：哪些跟踪、哪些 pick、为什么参考实现不能 pick |

---

## 10. 门禁与检查

```bash
python3 scripts/research-gate.py            # 研究完整性（SOURCES.toml）
python3 scripts/eight-step-gate.py --build  # 八步 ①~⑥
python3 scripts/eight-step-gate.py --flash  # 八步 ①~⑦ + ⑧ 预测
python3 scripts/porting-gate.py --quick     # porting.toml schema + README 表格一致性
python3 scripts/render-eight-step-table.py --check
```

四个门禁在 build / flash 前自动运行，任一失败即中止。
