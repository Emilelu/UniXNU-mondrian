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
| `audio/RESEARCH.md` | **音频八步 ①②③**：Pong 的 ADSP PAS1 + AudioReach/PRM + WCD938x（约 107 KB）、官方无组件、K60 待测项 |
| `battery/RESEARCH.md` | **电池 ①②④**：ADSP GLINK 交接租约的四标志、解锁链、单位转换 |
| [`battery/HANDOFF-PUBLISH.md`](research/battery/HANDOFF-PUBLISH.md) | **ADSP 交接发布者**：早期钩子、持续所有权、只读live发现/104字节发布、通知资格与离线测试；真实PAS1 owner仍缺失 |
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
