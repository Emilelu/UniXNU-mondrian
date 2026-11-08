# K60 iOS 移植 — 文档总索引（INDEX）

> 唯一文档入口。目标：新接手的人 5 分钟内知道**先读什么、文档在哪、哪些结论不能信**。
> 建立于 2026-11-07。仓库内文档用 `git mv` 保留历史；仓库外文档是**副本**，原件未删除，索引逐条标注原件位置。
> 范围只含 Markdown/文本；不含二进制、镜像、日志。`patches/`、`series`、`userland/`、`drivers/`、`scripts/`、`board.toml`、`porting.toml`、`.github/` 不在本文档树管理范围内。

## 0. 目录结构（两级）

```
docs/
├─ INDEX.md
├─ state/       当前状态、可信度台账、会话指令、下一步
├─ plans/       实施方案：120Hz / GPU / apply / touch
├─ audits/      对比审计、fork 审查、参考墙审计、实测与诊断记录
├─ reference/   长期参考：PITFALLS、DECISIONS、ISSUES、HISTORY-LEDGER、USB、ROUTE-*
└─ archive/     已过时/被取代的交接、旧索引与历史盘点
```

## 1. 先读这五份

| 顺序 | 文档 | 为什么先读 |
|---|---|---|
| 1 | [state/SESSION-DIRECTIVES-2026-11-07.md](state/SESSION-DIRECTIVES-2026-11-07.md) | 用户指令总账：本会话全部指令、纠正与事实结论，压缩后以此为准 |
| 2 | [state/STATE-2026-11-07.md](state/STATE-2026-11-07.md) | 当前真相：已进用户态；唯一硬阻断是 launchd SIGSEGV 与 stock OS 窗口 |
| 3 | [state/TRUST-LEDGER.md](state/TRUST-LEDGER.md) | 数值可信度：引用任何历史文档数值前先查 T/E/C 编号 |
| 4 | [audits/PONG16-DIFF-AUDIT.md](audits/PONG16-DIFF-AUDIT.md) | 与 pong ios16 的机械差异：补丁顺序、userland、drivers、scripts 的真实账目 |
| 5 | [plans/APPLY-PIPELINE.md](plans/APPLY-PIPELINE.md) | OS 窗口的正确改法：macOS 上 `prepare()` + `apply()`，再 recovery dd 写回 |

## 2. 全量目录表

状态取值：`当前` = 现行依据；`参考` = 长期参考/历史证据；`过时-已归档` = 已被取代；`已证伪` = 有反证，禁止按原文执行。

### state/

| 相对路径 | 一句话摘要 | 状态 | 原件位置（若为副本） |
|---|---|---|---|
| state/SESSION-DIRECTIVES-2026-11-07.md | 用户全部指令、纠正与事实结论总账；含找文件协议、pong16 参照、120Hz/GPU/内存结论 | 当前 | — |
| state/STATE-2026-11-07.md | 当前真相：SpringBoard 进主循环；launchd SIGSEGV 唯一硬阻断；根因是 stock OS 窗口未跑 apply() | 当前 | — |
| state/TRUST-LEDGER.md | 可信度台账：T1–T11、E1–E5、C1–C2，任何实现数值先登记再引用 | 当前 | — |
| state/NEXT-STEPS.md | 当前推进顺序：内核、payload、Data、显示/触摸/GPU 的前置条件 | 当前 | — |

### plans/

| 相对路径 | 一句话摘要 | 状态 | 原件位置（若为副本） |
|---|---|---|---|
| plans/120HZ-PORT-PLAN.md | 120Hz 移植方案（GPU scanout 生效后执行）；页首已加数据源更正，禁用 sharp 面板的 0xC6 切档 | 当前 | — |
| plans/APPLY-PIPELINE.md | 生成并写入 iOS 16 OS 窗口的完整流程：macOS `prepare()` + `apply()`，长度不变，recovery dd 写回 | 当前 | — |
| plans/GPU-ENABLE-PLAN.md | Adreno 730 scanout 启用方案：补丁依赖、代码路径、验证判据与回退 | 当前 | — |
| plans/K60-TOUCH-PARAMS.md | K60 Goodix / GENI-SPI 触摸参数表：live merged FDT 解析、9 个 DT 属性、置信度与复核方法 | 当前 | — |
| plans/K60-120HZ-PLAN.md | 旧版 K60 120Hz 方案；面板数据取自通用参考面板 `sharp_qhd_plus_dsc_cmd`，结论已被 T2 证伪 | 已证伪 | 副本，原件在 `D:/Android/k60-ios/deliverables/K60-120HZ-PLAN.md` |

### audits/

| 相对路径 | 一句话摘要 | 状态 | 原件位置（若为副本） |
|---|---|---|---|
| audits/PONG16-DIFF-AUDIT.md | 与 pong `ios16` 分支的机械差异审计：103/155 补丁集合、111 clean/14 fuzz/30 FAIL、userland/drivers/scripts 对账 | 当前 | — |
| audits/FORK-REVIEW.md | Fork 巡查与吸收记录：公开 fork 枚举、逐提交判断、上游 SHA 证据 | 参考 | — |
| audits/REFERENCE-WALL-AUDIT-2026-11-02.md | 对照 ios-sweet-k60 已验证墙的审计；`ns=2` 自 abort 判读仍是当前关键结论 | 参考 | — |
| audits/USERLAND-ROUTES-2026-11-02.md | UniXNU / hackios / pong 三种 userland 路线模型对比，防止跨树照抄 | 参考 | — |
| audits/PONG-FEASIBILITY.md | pong（iOS 18.7.10）路线本地代码深度核验：硬件可行、构建可控、用户态需换轨 | 参考 | — |
| audits/MEASURED-HIGH-WINDOW-2026-11-02.md | K60 高内存窗口实测：4 GiB 窗口、`/memory/reg` 六段原始证据与误判纠正 | 参考 | — |
| audits/BOOT-STALL-2026-10-31.md | 2026-10-31 启动进度条卡死诊断史料；§5 的 ADT 三条身份属性仍必做 | 参考 | — |
| audits/DIAGNOSIS-SANDBOX-2026-10-31.md | AMFI/Sandbox 替身与 SIGKILL 风暴诊断；行动建议已废弃，仅作历史诊断 | 参考 | — |

### reference/

| 相对路径 | 一句话摘要 | 状态 | 原件位置（若为副本） |
|---|---|---|---|
| reference/PITFALLS-FROM-HISTORY.md | 历史卷踩坑台账（第 N 条，1969 行）：从 commit 史提炼，含 Top 5 与逐条判定 | 参考 | 副本，原件在 `E:/k60-work/docs/PITFALLS-FROM-HISTORY.md` |
| reference/PITFALLS.md | 当前树/流程踩坑台账（P-NN）：症状、触发条件、正确做法、30 秒判定 | 参考 | 副本，原件在 `E:/k60-work/docs/PITFALLS.md` |
| reference/DECISIONS.md | 决策记录 SSOT：D-YYYYMMDD-NN，已定案方向与制度 | 参考 | 副本，原件在 `E:/k60-work/docs/DECISIONS.md` |
| reference/ISSUES.md | 问题台账 SSOT：I-YYYYMMDD-NN，未解决在前，字段固定 | 参考 | 副本，原件在 `E:/k60-work/docs/ISSUES.md` |
| reference/HISTORY-LEDGER.md | commit 级历史台账（至 2026-11-03 收敛）：查某个 sha 是干什么的 | 参考 | 副本，原件在 `E:/k60-work/docs/HISTORY-LEDGER.md` |
| reference/USB-LOG-CHANNEL.md | USB 内核日志通道可行性调研：CDC-ACM 裁决、SMMU/复位链、实施审计 | 参考 | 副本，原件在 `E:/k60-work/docs/USB-LOG-CHANNEL.md` |
| reference/ROUTE-USERSPACE.md | K60 iOS 16.6.1 用户态路线裁决（2026-11-02 v2）：先诊断不换 PID1 的演进史 | 参考 | 副本，原件在 `E:/k60-work/docs/ROUTE-USERSPACE.md` |
| reference/MASTER-INDEX.md | 全局资产总索引：D/E/F/WSL 路径地图与机读索引说明 | 参考 | 副本，原件在 `E:/k60-work/docs/MASTER-INDEX.md` |
| reference/AGENT-COORDINATION.md | D:/Android 主协作日志（append-only，368 KB）：CPU 拓扑、触摸、porting 回填等原始记录 | 参考 | 副本，原件在 `D:/Android/k60-ios/AGENT-COORDINATION.md` |
| reference/AGENT-COORDINATION-route-a-18.md | 本仓 route-a-18 协作日志（短）：早期 5 条上机与上游调研记录 | 参考 | — |
| reference/BRANCHES.md | 2026-11-01 分支清理台账：48 个旧分支的合并/作废判断 | 参考 | — |
| reference/DUAL-SYSTEM.md | 安卓 + UniXNU 双系统分区方案：在线缩 F2FS、GPT 约束、操作流程 | 参考 | — |
| reference/ROUTE-A-18-DELTAS.md | pong → K60 板级差异清单：显示、触摸、存储、GPU 的逐项差异 | 参考 | — |
| reference/ROUTE-A-18-HANDOFF-2026-11-01.md | Route A-18 交接全文：darwin24 迁移背景、已排除阻断、后续路线 | 参考 | — |
| reference/ROUTE-A-18-STATE.md | route-a-18 round 27 状态：darwin24 构建通过、上机绿条后静默复位 | 参考 | — |
| reference/ROUTE-A-18-UPSTREAM.md | 上游 UniXNU 生态与 iOS 16~27 移植可行性调研：不迁移 26/27 的依据 | 参考 | — |
| reference/USB-LOGGING-PLAN.zh.md | Pong USB 日志读取方案设计稿：DWC3 + CDC-ACM + Mac 接收器 | 参考 | — |
| reference/DECISION-MEMORY-12GIB-2026-11-02.md | 内存窗口专题 SSOT：4 GiB 来源、12 GiB 可行性、阶梯试验与约束 | 参考 | 副本，原件在 `E:/k60-work/docs/DECISION-MEMORY-12GIB-2026-11-02.md` |
| reference/DEVICE-REPOS.md | UniXNU 设备仓库目录快照（2026-11-04，235 条，★=SM8475） | 参考 | 副本，原件在 `E:/k60-work/docs/DEVICE-REPOS.md` |
| reference/REPO-BRANCH-MAP.md | 自有仓库分支地图（2026-11-03 收敛后）：每仓每分支职责与三方状态 | 参考 | 副本，原件在 `E:/k60-work/docs/REPO-BRANCH-MAP.md` |
| reference/MY-REPOS.md | 作者本人仓库清单：6 个远端 + 2 个纯本地仓库 | 参考 | 副本，原件在 `E:/k60-work/docs/MY-REPOS.md` |
| reference/COMMIT-CONVENTION.md | 自有仓库 commit 规范（feflow 指南，2026-11-03 起向后适用） | 参考 | 副本，原件在 `E:/k60-work/docs/COMMIT-CONVENTION.md` |
| reference/RECORDING-RULES.md | 记录规范：铁律、§7 识图纪律、§8 每坑必录、§9 编号分配器 | 参考 | 副本，原件在 `E:/k60-work/docs/RECORDING-RULES.md` |
| reference/READING-LIST.md | 三层必读书目：项目内、历史、上游，作为入场索引补充 | 参考 | 副本，原件在 `E:/k60-work/docs/READING-LIST.md` |
| reference/UPSTREAM-SYNC.md | 上游跟进机制：devices.py list/find/pull-check、push-check、增量落盘 | 参考 | 副本，原件在 `E:/k60-work/docs/UPSTREAM-SYNC.md` |
| reference/UNIXNU-SITE-INDEX.md | unixnu.com 官网动态内容索引（程序生成，禁止手改；实时优先） | 参考 | 副本，原件在 `E:/k60-work/docs/UNIXNU-SITE-INDEX.md` |
| reference/PUSH-BACKLOG.md | 自有仓待推送清单（2026-11-04 快照）：push 前必须用户点头 | 参考 | 副本，原件在 `E:/k60-work/docs/PUSH-BACKLOG.md` |
| reference/C-DRIVE-SPACE.md | C 盘空间治理报告（2026-11-02）：逻辑/实际占用口径与清理项 | 参考 | 副本，原件在 `E:/k60-work/docs/C-DRIVE-SPACE.md` |
| reference/D-DRIVE-WSL.md | D 盘/WSL 空间盘点（2026-11-03）：ext4.vhdx、pagefile、缓存 | 参考 | 副本，原件在 `E:/k60-work/docs/D-DRIVE-WSL.md` |
| reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md | K60→iPadOS 16.6.1 外设与功能分层调研：T1–T4 与证据等级 | 参考 | 副本，原件在 `D:/Android/k60-ios/deliverables/FEATURES-DRIVERS-RESEARCH-2026-10-31.md` |
| reference/ZCODE-RESEARCH-REPORT.md | ZCode 深度调研报告：启动链、面板 m11a、显示/挂载修复细节 | 参考 | 副本，原件在 `D:/Android/k60-ios/deliverables/ZCODE-RESEARCH-REPORT.md` |
| reference/INTEGRATION.md | 两件成品集成说明：UEFI 日志进 ramoops、ResetSystem 自动回 fastboot | 参考 | 副本，原件在 `D:/Android/k60-ios/deliverables/INTEGRATION.md` |
| reference/README-k60-ios.md | D:/Android/k60-ios 参考与协作区目录说明（已整理 2026-11-02） | 参考 | 副本，原件在 `D:/Android/k60-ios/README.md` |

### archive/

| 相对路径 | 一句话摘要 | 状态 | 原件位置（若为副本） |
|---|---|---|---|
| archive/HANDOFF-2026-10-30-EVENING.md | 2026-10-30 傍晚旧交接：trust cache、Data 路线、ramoops、构建陷阱的原始记录 | 过时-已归档 | 仓库历史 `c98c1c4:docs/HANDOFF-2026-10-30-EVENING.md` |
| archive/PROGRESS-2026-10-30-PM.md | 2026-10-30 PM 旧进度记录：trust cache 打通后的推进与 pong 对标 | 过时-已归档 | 仓库历史 `c98c1c4:docs/PROGRESS-2026-10-30-PM.md` |
| archive/HANDOFF-PROMPT-2026-10-30.md | 旧交接 prompt（2026-10-30）：仅复述 EVENING + 工具清单 | 过时-已归档 | 仓库历史 `c98c1c4:docs/HANDOFF-PROMPT-2026-10-30.md` |
| archive/HANDOFF-PROMPT-2026-10-31.md | 旧交接 prompt（2026-10-31）：display-scale / printf / fb_threads 等修复记录 | 过时-已归档 | 仓库历史 `c98c1c4:docs/HANDOFF-PROMPT-2026-10-31.md` |
| archive/HANDOFF-2026-10-31.md | 旧交接（2026-10-31）：启动状态、阻断、显示修复、构建陷阱 | 过时-已归档 | 仓库历史 `c98c1c4:docs/HANDOFF-2026-10-31.md` |
| archive/DATA-SPACE-2026-10-31.md | 旧 Data/存储盘点；独特事实已并入 STATE §12（几何、ENOSPC、2 GiB 安装） | 过时-已归档 | 仓库历史 `c98c1c4:docs/DATA-SPACE-2026-10-31.md` |
| archive/HANDOFF-PROMPT-2026-11-01.md | darwin22→darwin24 交接 prompt；该路线后来被放弃 | 过时-已归档 | — |
| archive/MILESTONE-DARWIN24-KERNEL.md | darwin24 内核首次在 Linux 构建成功的里程碑（历史） | 过时-已归档 | — |
| archive/READING-INDEX.md | 旧开工必读索引（2026-10-30）：指向已删除的旧交接 | 过时-已归档 | — |
| archive/HANDOFF-k60-work-2026-11-06.md | E:/k60-work 滚动状态页（2026-11-06 快照），已被 STATE-2026-11-07 取代 | 过时-已归档 | 副本，原件在 `E:/k60-work/docs/HANDOFF.md` |
| archive/INDEX-k60-work.md | E:/k60-work 旧项目入口与铁律（2026-11-05 版） | 过时-已归档 | 副本，原件在 `E:/k60-work/docs/INDEX.md` |
| archive/INDEX-k60-ios.md | D:/Android/k60-ios 旧目录索引（2026-11-02 归类版） | 过时-已归档 | 副本，原件在 `D:/Android/k60-ios/INDEX.md` |
| archive/FORKS-TRIAGE.md | fork 分拣指针 stub（已归档，原文在 E:/k60-work/docs/archive） | 过时-已归档 | 副本，原件在 `E:/k60-work/docs/FORKS-TRIAGE.md` |
| archive/LAUNCHD-SHA256.md | launchd SHA256 指针 stub（已归档，原文在 E:/k60-work/docs/archive） | 过时-已归档 | 副本，原件在 `E:/k60-work/docs/LAUNCHD-SHA256.md` |
| archive/MAIN-SWITCH-PLAN.md | 主仓切换指针 stub（已归档，原文在 E:/k60-work/docs/archive） | 过时-已归档 | 副本，原件在 `E:/k60-work/docs/MAIN-SWITCH-PLAN.md` |
| archive/ZCODE-RESEARCH-TASK.md | ZCode 调研任务书（已由 ZCODE-RESEARCH-REPORT 取代） | 过时-已归档 | 副本，原件在 `D:/Android/k60-ios/deliverables/ZCODE-RESEARCH-TASK.md` |

## 3. 已证伪 / 冲突（与 state/TRUST-LEDGER.md §1 同步）

| 编号 | 断言 | 反证 / 结论 | 状态 |
|---|---|---|---|
| T1 | DRAM 12 GiB @`0x80000000`，`swinfo.fingerprint=mondrian:12` 可作 SKU 证据 | `audits/MEASURED-HIGH-WINDOW-2026-11-02.md:39-57` 明确否定：手写 DTS 不是硬件实测，fingerprint 不是可靠 SKU 证据 | **冲突未解** |
| T2 | K60 面板 = `sharp_qhd_plus_dsc_cmd`，无 120Hz 档，切档用 DCS `0xC6` | 真机面板是 `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`；sharp 是通用参考面板（`ZCODE-RESEARCH-REPORT.md:396`，U6-C5） | **已证伪** |
| T3 | K60 触摸是 sweet 那套 I2C `0x5d` / SE `0xa84000` | K60 = GENI SPI `spi@990000` CS0 15 MHz；不要抄 sweet 的 GT9896 常量（`AGENT-COORDINATION.md:1379`） | **已证伪** |
| T4 | 按 pong 的 glob 字母序全量应用 155 个补丁即可“与 pong 完全一致” | `audits/PONG16-DIFF-AUDIT.md` §5：111 clean / 14 fuzz / 30 FAIL；真实脚本第 1 个补丁就 exit 1（`0210` 目标文件由第 115 位的 `ui-foundation` 创建） | **已证伪** |
| T5 | sweet 的 19 个 cryptex hard-link 是解决 launchd 崩溃的正解 | 架构不同：sweet 单卷可写 HFS+；我们/pong 三窗口 + 只读 OS 卷，正解是 `apply()` 移走 stock jobs（`userland/build.py:449-471`） | **已证伪（架构不适用）** |
| C1 | K60 raw dtbo 已不在盘上，无法解析 `dtbo_a_fdt15/fdt19` | `F:/k60-archive/dtb/` 有 65 个文件，含 `dtbo_a_fdt15.dtb` 752,562 B、`dtbo_a_fdt19.dtb` 509,088 B（`SESSION-DIRECTIVES-2026-11-07.md` §1） | **已证伪（可用性误判）** |
| C2 | IPSW 分量本地已丢，重建前必须重新下载 | `E:/hackios/UniXNU/out/ipsw/20G81/` 有 `096-57366-083.dmg` 4,250,815,697 B、`096-56782-083.dmg` 2,665,480,192 B、`kernelcache.decompressed` 48,644,096 B（约 6.5 GB）（`SESSION-DIRECTIVES-2026-11-07.md` §1） | **已证伪（可用性误判）** |

> 引用规则：任何历史文档里的数值，先在 `state/TRUST-LEDGER.md` 找到对应行；状态不是 `已实测`/`可复算` 的，必须重算或标注“未核实”。出现反证时只追加、不删旧行。

## 4. 命名与归档规则

1. 新文档先按用途入目录：状态/指令/可信度 → `state/`；实施方案 → `plans/`；对比审计/诊断/实测 → `audits/`；长期台账与调研 → `reference/`。
2. 过期文件移入 `archive/`，**不删除**；文件名保留原名，必要时加来源/日期后缀（如 `HANDOFF-k60-work-2026-11-06.md`）。
3. 外部文档用复制（`cp` / `Copy-Item`）入库，原件不删；索引“原件位置”列必须写清 `副本，原件在 …`。
4. 任何准备用于实现的数值，先登 `state/TRUST-LEDGER.md`（出处 / 冲突 / 复算方式 / 状态），否则只能写“未核实”。
5. 归档文件仍可被引用，但引用时必须注明“过时-已归档”，不得当作当前结论。
6. 本索引是唯一入口：新增/移动/归档任何文档，必须同步更新本文件的全量目录表。
