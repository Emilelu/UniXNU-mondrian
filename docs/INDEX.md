# 文档总索引（docs/INDEX.md）

> 唯一入口。所有历史调研文档**不能默认正确**：数值先查 `state/TRUST-LEDGER.md`。
> 生成时间：2026-11-07。规则：新文档按目录归类；过期文档移 `archive/` 不删除；外部文档副本保留原件。

## 先读这五份

1. [state/SESSION-DIRECTIVES-2026-11-07.md](state/SESSION-DIRECTIVES-2026-11-07.md) — 用户指令总账（铁则、找文件协议、全部纠正）
2. [state/STATE-2026-11-07.md](state/STATE-2026-11-07.md) — 当前真相（SpringBoard 已进主循环、launchd SIGSEGV 根因）
3. [state/TRUST-LEDGER.md](state/TRUST-LEDGER.md) — 数值可信度台账（已实测/可复算/未核实/已证伪）
4. [audits/PONG16-DIFF-AUDIT.md](audits/PONG16-DIFF-AUDIT.md) — 与 pong16 的逐项差异与冲突
5. [plans/APPLY-PIPELINE.md](plans/APPLY-PIPELINE.md) — OS 窗口的正确改法（macOS apply + recovery dd）

## 已证伪 / 冲突（引用前必看）

- T1 内存「12 GiB @0x80000000」：`AGENT-COORDINATION:1778/1792` 与 `MEASURED-HIGH-WINDOW:39-57` **互相矛盾**
- T2 `K60-120HZ-PLAN` 面板数据来自通用参考面板（真机是 `m11a_42_02_0a`）
- T3 sweet 的触摸常量 `0x5d/0xa84000` 是 Note 10 Pro，不是 K60
- T4 按 pong 字母序全量应用补丁：30 FAIL，第 1 个补丁就失败
- T5 sweet 的 cryptex hard-link 架构不适用于我们的三窗口模型
- C1/C2/C3 dtbo、IPSW、真面板：均已在 `F:/k60-archive/dtb` 与 `E:/hackios/UniXNU/out/ipsw/20G81` 找到

## 全量目录

| 路径 | 摘要 |
|---|---|
| `archive/DATA-SPACE-2026-10-31.md` | Data ENOSPC 与 32 GiB 内部布局（2026-10-31） |
| `archive/FORKS-TRIAGE.md` | FORKS-TRIAGE（已归档） |
| `archive/HANDOFF-2026-10-30-EVENING.md` | K60 iOS 移植 · 交接文档（HANDOFF-2026-10-30-EVENING） |
| `archive/HANDOFF-2026-10-31.md` | Redmi K60 (mondrian) — iOS 16.6.1 移植交接 |
| `archive/HANDOFF-PROMPT-2026-10-30.md` | 交接 Prompt（可直接复制发给新 agent） |
| `archive/HANDOFF-PROMPT-2026-10-31.md` | 交接 Prompt（2026-10-31） |
| `archive/HANDOFF-PROMPT-2026-11-01.md` | 交接 Prompt — K60 iOS 移植（darwin22 → darwin24） |
| `archive/HANDOFF-k60-work-2026-11-06.md` | HANDOFF — 当前状态（滚动覆盖，只写「现在」） |
| `archive/INDEX-k60-ios.md` | D:\Android\k60-ios INDEX（2026-11-02 归类版） |
| `archive/INDEX-k60-work.md` | ﻿# K60 iOS 移植 — 入口（INDEX） |
| `archive/LAUNCHD-SHA256.md` | LAUNCHD-SHA256（已归档） |
| `archive/MAIN-SWITCH-PLAN.md` | MAIN-SWITCH-PLAN（已归档） |
| `archive/MILESTONE-DARWIN24-KERNEL.md` | route-a-18 里程碑：darwin24 内核在 Linux 上编译成功 |
| `archive/PROGRESS-2026-10-30-PM.md` | K60 移植进展与 pong 对标（2026-10-30 下午） |
| `archive/READING-INDEX.md` | K60 移植 — 开工必读索引 |
| `archive/ZCODE-RESEARCH-TASK.md` | K60 iOS 移植 — ZCode 调研任务书 |
| `audits/BOOT-STALL-2026-10-31.md` | 启动进度条卡死 —— 现状、证据、下一步（2026-10-31） |
| `audits/DIAGNOSIS-SANDBOX-2026-10-31.md` | 诊断结论与修复方案：进度条卡 1/3 + SIGKILL 风暴（2026-10-31） |
| `audits/FORK-REVIEW.md` | Fork 巡查与吸收记录 |
| `audits/MEASURED-HIGH-WINDOW-2026-11-02.md` | K60 measured high-memory window — 2026-11-02 |
| `audits/PONG-FEASIBILITY.md` | pong（iOS 18.7.10）路线可行性 —— 本地代码深度核验结论 |
| `audits/PONG16-DIFF-AUDIT.md` | PONG16-DIFF-AUDIT |
| `audits/REFERENCE-WALL-AUDIT-2026-11-02.md` | Audit against ios-sweet-k60's proven walls (2026-11-02T18:26:27+08:00) |
| `audits/USERLAND-ROUTES-2026-11-02.md` | Userland routes compared: UniXNU vs hackios vs pong (2026-11-02T19:11:15+08:00) |
| `plans/120HZ-PORT-PLAN.md` | K60 120 Hz 移植方案（GPU scanout 生效之后执行） |
| `plans/APPLY-PIPELINE.md` | APPLY-PIPELINE — 生成并写入 iOS 16 的 OS 窗口 |
| `plans/GPU-ENABLE-PLAN.md` | K60 Adreno 730 scanout 启用方案 |
| `plans/K60-120HZ-PLAN.md` | K60 120Hz 显示方案（离线调研，等根挂载后再实施） |
| `plans/K60-TOUCH-PARAMS.md` | K60 触摸参数表（Goodix / GENI-SPI） |
| `reference/AGENT-COORDINATION-route-a-18.md` | 协作日志（route-a-18） |
| `reference/AGENT-COORDINATION.md` | K60 移植 · 双 Agent 协作板 |
| `reference/BRANCHES.md` | 分支台账（route-a-18） |
| `reference/C-DRIVE-SPACE.md` | C 盘空间治理报告 |
| `reference/COMMIT-CONVENTION.md` | Commit 规范（K60 自有仓库） |
| `reference/D-DRIVE-WSL.md` | D 盘空间盘点（WSL 专题） |
| `reference/DECISION-MEMORY-12GIB-2026-11-02.md` | K60 内存窗口定性：4 GiB 的来源、上限与 12 GiB 可行性（2026-11-02，只读审计） |
| `reference/DECISIONS.md` | K60 iOS 移植 — 决策记录（DECISIONS） |
| `reference/DEVICE-REPOS.md` | DEVICE-REPOS — UniXNU 设备仓库目录（快照） |
| `reference/DUAL-SYSTEM.md` | 双系统分区（安卓 + UniXNU） |
| `reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md` | K60（Redmi K60 / mondrian / SM8475）→ iPadOS 16.6.1：外设与功能分层调研交付 |
| `reference/HISTORY-LEDGER.md` | 历史 commit 台账（K60 iOS 移植） |
| `reference/INTEGRATION.md` | K60 调试加速 · 两件成品集成说明（Agent-B 交付，Agent-A 只需集成） |
| `reference/ISSUES.md` | K60 iOS 移植 — 问题与踩坑记录（ISSUES） |
| `reference/K60-120HZ-PLAN-legacy.md` | K60 120Hz 显示方案（离线调研，等根挂载后再实施） |
| `reference/MASTER-INDEX.md` | MASTER-INDEX — K60 iOS 移植全局资产总索引 |
| `reference/MY-REPOS.md` | 作者本人仓库清单（K60 iOS 移植） |
| `reference/PITFALLS-FROM-HISTORY.md` | 踩坑台账（从历史 commit 提炼） |
| `reference/PITFALLS.md` | K60 iOS 移植 — 踩坑台账（PITFALLS） |
| `reference/PUSH-BACKLOG.md` | PUSH-BACKLOG — 自有仓待推送清单（给用户逐个画勾用） |
| `reference/READING-LIST.md` | K60 iOS 移植 — 动手前必读清单（READING-LIST） |
| `reference/README-k60-ios.md` | k60-ios — 参考仓库与协作区（已整理 2026-11-02） |
| `reference/RECORDING-RULES.md` | K60 iOS 移植 — 记录规范（RECORDING-RULES） |
| `reference/REPO-BRANCH-MAP.md` | 仓库分支地图（K60 iOS 移植，2026-11-03 收敛后） |
| `reference/ROUTE-A-18-DELTAS.md` | pong → K60 板级差异清单（route-a-18 第一步） |
| `reference/ROUTE-A-18-HANDOFF-2026-11-01.md` | Route A-18 交接全文（2026-11-01） |
| `reference/ROUTE-A-18-STATE.md` | route-a-18 状态（2026-11-01 round 27） |
| `reference/ROUTE-A-18-UPSTREAM.md` | 上游 UniXNU 生态与 iOS 16~27 移植可行性（2026-11-01 调研） |
| `reference/ROUTE-USERSPACE.md` | ROUTE-USERSPACE — K60 iOS 16.6.1 用户态路线裁决（2026-11-02 v2） |
| `reference/UNIXNU-SITE-INDEX.md` | UNIXNU-SITE-INDEX — unixnu.com 官网动态内容索引（人读入口） |
| `reference/UPSTREAM-SYNC.md` | UPSTREAM-SYNC — 上游跟进机制（拉别人仓 + 按坑反查 + 自己仓 push 检查） |
| `reference/USB-LOG-CHANNEL.md` | USB 内核日志通道可行性调研（unixnu 路线 / K60 mondrian） |
| `reference/USB-LOGGING-PLAN.zh.md` | Pong USB 日志读取方案 |
| `reference/ZCODE-RESEARCH-REPORT.md` | K60 iOS 移植调研报告 |
| `state/NEXT-STEPS.md` | K60 移植下一步 |
| `state/SESSION-DIRECTIVES-2026-11-07.md` | 会话指令与事实总账（2026-11-07） |
| `state/STATE-2026-11-07.md` | STATE-2026-11-07 — K60 iOS 移植当前真相 |
| `state/TRUST-LEDGER.md` | 可信度台账（TRUST LEDGER） |
