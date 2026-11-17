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
| `wifi/BOOT-DEATH-SUSPECT.md` | **WiFi ⑧ 死因账本**：mhi3/mhi4 静默前无任何内核输出的证据、过期内核混淆项、四个嫌疑（__TEXT 11.2 MB 固件 blob / 窗口算术 / 退役 touch 探针 / `pong_wifi=1`）与逐个反证方法 |
| `wifi/T2-PATCH.md` | **WiFi T2 备胎补丁**：把 11.19 MB PWF2 容器从 `__TEXT,__const` 挪到 `__DATA,__const` 的一行 diff（已验证可正反向 apply）、t2 构建配方、飞行前三项离线校验 |
| `wifi/MSI-TOPOLOGY.md` | **WiFi 中断拓扑**：PCIe0 的三条 MSI 路径（PARF `MSI0`→SPI140/INTID172 实走、DT `msi-map` 指向 ITS 的 `0x5980`/`0x5981`、`pcie0_msi` 32 条 SPI 768..799 已 disabled）、为什么选 legacy、单 INTID 能看见与看不见什么、c5/c6 飞行证据 |
| `wifi/SBL-QUEUE.md` | **WiFi SBL 队列候选**：c7 的 `ee=0 exec_env=1` 与官方 `MhiBoot.c` 的 `BHI_EXECENV` 轮询/BHIe 路径、`pong_sbl_pushed` 一次锁、`wifi-20261117sbl-queue` 镜像身份与预写成功/失败判据 |
| `wifi/DARWINBOOT-POOL.md` | **WiFi 死因收窄②**：DarwinBoot 三处内存节点（ReadFile 的 AllocatePool / AllocateWindow 4.5 GiB 连续窗口 / FreePool(Image)）逐行失败形态与打印、board.toml:235 与 5120 MiB arena 的窗口算术对账、一次上机分开 pool 通道的判据 + 固件打印提案 |
| `audio/RESEARCH.md` | **音频八步 ①②③**：Pong 的 ADSP PAS1 + AudioReach/PRM + WCD938x（约 107 KB）、官方无组件、K60 待测项 |
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
