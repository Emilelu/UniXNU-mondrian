# K60 iOS 移植 — 入口（INDEX）

> ## ⛔ 铁律（先于本文件与全部文档的一切条款；冲突时以本节为准）
>
> 1. **遇坑必录**：遇到任何坑必须**当轮**写进文档（PITFALLS / PITFALLS-FROM-HISTORY），不得等用户提醒、不得下轮补；漏记 = 任务未完成。收尾三连问（落文档了吗 / 当轮写了吗 / 编号闭合了吗）不过**不许收工**。
>    - 违反的实例：扩容轮的 hex 块号写偏、清单几何错误，都是靠事后补录才拦住第二次；用户 2026-11-04 原话立此条。
> 2. **动手前先查坑表**：禁止在同一坑上反复试错（ramoops 读取、PS5 数组/重定向、hex 块号、几何误读、PowerShell 引号——全是前车之鉴）。
>    - 违反的实例：ramoops「读日志」设想在已被定案不可行后又被提出并实测失败一次（2026-11-04 06:03）。
> 3. **「灾情/损坏」级结论必须过三关**：(a) 读点按设备在役清单真值 + 算式复核；(b) dump 带 sidecar；(c) 与独立备份逐字节比对。缺一条只能说「观测异常，待复核」，**禁止**使用「毁 / 全毁 / 清零 / 覆写」定性词。
>    - 违反的实例：2026-11-03 21:43 那批 dump 按错误几何读，就这样误判了「三窗全毁」，差点启动从零重建（PITFALLS 第 19 条）。
> 4. **术语固定**：**窗** = SHNGROOT 清单条目（offset/size/sha256）；**卷** = 窗内的 APFS 容器。文档一律按「窗」记。
>    - 违反的实例：「卷坏了」的口语表述曾让「窗内容是否受损」与「清单几何错误」混为一谈，延误定位。
> 5. **调研驱动，禁止「做一点猜一点」**（用户 2026-11-04 原话："后续所有工作以调研文档驱动进行，而不是做一点猜一点。调研结果必须审阅确保万无一失。没得到充分可行结论不要操作。后续都这样"）。
>    - 上机 / 动盘 / 改代码 / 改清单前，必须先有落盘调研文档：问题定义、事实证据（文件/行号/命令/读数/sha/上游 commit）、方案与失败形态、验证方法、回退路径。
>    - 结论必须复审（自审 + 独立来源交叉核对），标「已审阅」才可执行；**无充分可行结论不得操作**。证据分三级：实测 / 文档 / 推断，推断级不得作为动手依据。
>    - 未调研主题进 `references/GAP-TO-SPRINGBOARD.md` 的「未调研主题」清单，禁止「大概应该可以」开工。
>    - **现状页（谁在跑、卡在哪、等谁拍板）= `HANDOFF.md`**，每次状态变化当轮更新；历史结论写台账，不写现状页。
> 6. **实时优先，缓存仅作检索副本**（用户 2026-11-04 立）：判断上游现状（有哪些仓库/最新进展/设备目录）以实时源（unixnu.com/devices/、GitHub）或带导出时间的 `docs/devices-map.json` 为准；本地快照/缓存只作检索副本，用时标抓取时间；实时源不可达必须明示，禁止旧缓存冒充最新。**任何 fetch/pull 前先记当前 HEAD，完成后记新 HEAD 与新增 commit 列表**（落 `E:\k60-work\references\upstream-watch\CHANGES-<date>.md`），不允许无记录地更新本地副本。机制见 [UPSTREAM-SYNC.md](UPSTREAM-SYNC.md)。
> 7. **屏摄读数三选一才可作证据**（2026-11-04 立）：结论依据的行/寄存器值/sha/编号必须满足 ①用户明确确认 ②设备/文件回读真值 ③原始日志文本 之一；三皆无 → 只写「观测不清，待核」。细则与误读五连实例：[RECORDING-RULES.md](RECORDING-RULES.md) §7.9、[PITFALLS-FROM-HISTORY.md](PITFALLS-FROM-HISTORY.md) 第 32 条。
> 8. **遇到问题先查 Pong 仓库**（2026-11-05 立，用户原话："一遇到问题就要去找找Pong仓库的解决方案 需要写到文档 避免反复踩坑"）：内核/驱动/启动链问题先查 `Chengdong-Yu/UniXNU-pong` 的 `main` + `ios16` 分支，以及 `drivers/*` 子模块独立仓库（`pong-usb`、`pong-boot-capture`、`pong-ufs`、`pong-adreno`、`pong-power`…）——同 SoC 已验证跑通的参考实现。已知对照：AMFI 用 `zzzzzzzzzzz-pong-development-no-amfi-interface.patch`（AMFI 故意缺席 + 全量 NULL 守卫 + 硬 bypass 返回成功）；复位进 fastboot 用 `pong-boot-capture/PongBootCapture.h`（PMIC SDAM7100 SPMI 写 + IMEM `0x77665500`/`0x77665502` + `reboot_kernel(0x400)`，只写 IMEM 会进 Android）；日志/命令通道用 `pong-usb`（CDC-ACM 文本命令 `reboot fastboot` / `reboot rec` / `help`）。详见 [USB-SERIAL-AND-AMFI-CHANNEL-20261105.md](references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md) §12。
>
>
> 本铁律同时已写入项目记忆（`project_memory.md`「铁律」节），任何 agent 加载记忆即可见。**任何批次重写/收敛文档时，本节不得删除、不得移出顶部。**

> 本文件是唯一入口。目标：新 agent 进场 5 分钟回答三个问题——**现在卡在哪、下一步做什么、哪些结论已定案不能翻案**。
> 工作区总闸（铁律 + 路由 + 硬边界）在 [`D:\Android\AGENTS.md`](file:///D:/Android/AGENTS.md)（2026-11-04 新增，双向互链）。
> **现状页（滚动覆盖、只写现在）在 [`HANDOFF.md`](HANDOFF.md)**：谁在跑、卡在哪、等谁拍板、下一步第一动作、不要重复尝试——每次状态变化当轮更新。定案写本文件/DECISIONS，现状写它。
> 维护规则见 [RECORDING-RULES.md](RECORDING-RULES.md)（§8 每坑必录）。覆盖范围 = `E:\k60-work\docs\`；外域（D:\Android 主仓、WSL 设备仓/固件仓、E:\k60-work 产物盘）的旧版全量地图在 [`archive/INDEX-20261103-map.md`](archive/INDEX-20261103-map.md)（仍有效部分照用）。

---

## 0. 术语表（先定死，全项目统一）

- **窗（window）**：SHNGROOT 清单里的条目（offset / size / sha256）。本设备三个窗：**OS 窗、SystemOS 窗、Data 窗**。
- **卷（volume）**：窗**内部**装的 APFS 容器（镜像区）。
- 口语「卷坏了」实际指「窗内容坏了」。文档一律按**窗**记，必要时写「窗内的 APFS 容器」。

## 1. 状态速览（2026-11-05）

- **一句话状态**：iOS 16.6.1（Darwin 22）主线；**console 落盘通道已打通**（0306 修复上机 PASS：`/pong/console.log` 24,715 B，首行 `K60LOG boot epoch=1793709100 ring_total=24006 dropped=0`，APFS OwnerData xid=19）。下一目标 = init drainer 加固（0600/配额/floor/fsync/STOP），受 inode.size 35,160 B 约束。
- **里程碑（2026-11-04，mtime/内容归因，经种子自带排除复核）**：init（`/pong/status.txt` token 全链 `A0…E1`）→ launchd（`/db/com.apple.xpc.launchd/disabled.plist={'com.apple.watchdogd': True}`）→ installd 级骨架（`/codes`、`/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}`、`/installd/Library`，epoch+35s——**非 init 可造**）→ **SpringBoard**（`com.apple.springboard.plist={'BKNoWatchdogs':1,'FBLaunchWatchdogExceptions':{purplebuddy:100}}`）→ **设置助理跑完全部步骤**（`com.apple.purplebuddy.plist={'SetupDone':1,'SetupFinishedAllSteps':1,'SetupVersion':11}`）。**以上各项基线镜像均无 = 运行时新写**；`.GlobalPreferences.plist` 经对照为种子自带（sha 相同），已剔除出证据。层间进度判读清单：[references/BOOT-PROGRESS-MARKERS.md](references/BOOT-PROGRESS-MARKERS.md)。
- **当前卡点（按优先级）**：
  1. **init drainer 加固**：`console.log` 仍 0644（应 0600）；配额/floor/fsync/轮转/STOP 未加固；init 仅剩 248 B 余量（34,912 / 35,160 B），需先做离线尺寸实验判定可行性。
  2. USB CDC 暂停；显示侧后置，不在当前关键路径。
- **下一步（按序）**：① 离线尺寸实验判定 init 加固能否装入；② 能装入则写加固代码 + 一次构建 + 新短单上机；装不下则立项扩大 init inode 或外置 helper；③ USB reader 同源改动待 USB 线恢复后验证。
- **已定案不能翻案（摘）**：只 `fastboot boot` 不 flash；只动 unixnu 分区内部；Darwin22/16.6.1 主线（darwin24 已放弃）；4 GiB 内存高窗基线（阶梯试验另计）；**三窗内容完好**；**屏摄降级为辅助证据（PITFALLS 44），判读只信盘侧痕迹**；**init-v11drain 当前 34,912 B ≤ 35,160 B 硬上限（PITFALLS 46）；不得增加探针或改写设备 init，除非另有研究文档和用户批准**。

## 2. 必读三份（进场顺序）

1. [DECISIONS.md](DECISIONS.md) — **结论权威（SSOT）**：已定案方向与制度。先看 D-2026-11-04-01（屏摄唯一证据源/USB 通道）、D-2026-11-03-18（几何真值+备份+取证三制度）。
2. [ISSUES.md](ISSUES.md) — **待解权威**：未解决区即当前卡点（I-20261103-11/12/13、I-20261104-01）。
3. [PITFALLS.md](PITFALLS.md) + [PITFALLS-FROM-HISTORY.md](PITFALLS-FROM-HISTORY.md) — **坑台账**：动手前翻 30 秒判定（P-09 写盘四闸门、P-10 屏摄唯一证据、第 13 条清单几何、第 16 条 ramoops、第 6 条错误几何读设备）。

## 3. 文档地图（docs/ 内每个文件一行）

| 文件 | 一行说明 | 何时读 |
|---|---|---|
| INDEX.md | 本文件 | 进场第一份 |
| HANDOFF.md | **现状页**（滚动覆盖，只写现在：卡点/在跑/待拍板/下一步/别重试） | 进场第二份 |
| references/GAP-TO-SPRINGBOARD.md | 到 SpringBoard 的分层差距 + 硬件驱动缺口表 + 未调研主题清单（2026-11-04 首版已落盘） | 决定下一步做什么前 |
| MASTER-INDEX.md / master-index.json | **全局资产地图**（D 限 `D:\Android`、E、F、WSL；258 条机读 + WSL sha 附件） | 找证据/镜像/仓库路径时 |
| UNIXNU-SITE-INDEX.md / unixnu-site-index.json | 官网动态内容唯一入口（实时优先，缓存仅基线） | 查官网最新文档/变动时 |
| DECISIONS.md | 决策台账（结论 SSOT） | 引用任何定案前 |
| ISSUES.md | 问题台账（待解 SSOT） | 要知道卡点时 |
| PITFALLS.md | 当前树/流程坑（P-NN） | 动手前 |
| PITFALLS-FROM-HISTORY.md | 历史卷+轮次坑（第 N 条） | 翻历史背景时 |
| RECORDING-RULES.md | 记录制度（§7 识图纪律、§8 每坑必录） | 写任何文档/读屏摄前 |
| UPSTREAM-SYNC.md | 上游跟进机制（devices.py list/find/pull-check、push-check.py、增量格式） | 查别人仓库/按坑反查/push 积压前 |
| DEVICE-REPOS.md | 设备→仓库目录快照（权威以 devices.py list 实时为准） | 按坑找别人方案时 |
| HISTORY-LEDGER.md | commit 流水台账（至 11-03 收敛） | 查某条 commit 背景时 |
| DECISION-MEMORY-12GIB-2026-11-02.md | 内存窗专项权威（4 GiB 来源/12 GiB 不可行/阶梯） | 碰内存参数前 |
| USB-LOG-CHANNEL.md | USB 日志通道方案调研（主线并行必需项设计档） | 做 USB 通道时 |
| ROUTE-USERSPACE.md | 用户态路线裁决（已定案：先诊断不换 PID1→已演进为 pong init 前置层） | 翻路线史时 |
| MY-REPOS.md | 本人仓库清单 | 推/拉/建分支前 |
| REPO-BRANCH-MAP.md | 分支地图（11-03 收敛后：每仓 main+archive+tags） | 任何 git 操作前 |
| COMMIT-CONVENTION.md | commit 规范（feflow） | 写 commit 前 |
| C-DRIVE-SPACE.md / D-DRIVE-WSL.md | 磁盘空间治理 | 空间告警时 |
| READING-LIST.md | 三层必读书目（与本入口互补） | 进场第二份 |
| MAIN-SWITCH-PLAN.md / FORKS-TRIAGE.md / LAUNCHD-SHA256.md | **指针 stub**（已闭环，原文在 archive/） | 查历史方案时 |
| references/（40 份 DIGEST/ADOPTION/PORT-ALL-MATRIX 等） | 上游/参考仓调研摘要库（另一 agent 领地） | 查上游事实时；pong 移植查 PORT-ALL-MATRIX |
| archive/ | 闭环/被取代文档的存档（含旧版全量地图 INDEX-20261103-map） | 翻旧案时 |

## 4. 交接检查单（新 agent 进场）

1. **先读顶部「铁律」5 条**（任何操作之前）；然后本文件 §1 → DECISIONS 顶部 3 条 → ISSUES 未解决区 → PITFALLS 两册的 30 秒判定列。
2. **不要重复踩**（高频坑速记）：清单几何只能用设备真值（I-20261103-11）；写盘走四闸门 + 备份范围≥写入范围（P-09/D-2026-11-03-18）；取证 dump 必带 sidecar、只定点抽读（D-2026-11-03-18）；ramoops 读不了别再试（I-20261104-01）；屏摄读数按 RECORDING-RULES §7；XNU 阶段禁止索要日志文件。
3. **引用 sha 一律从 `candidates/<目录>/build-verification.json` 或本文件 §5 抄**，不凭记忆（P-06）。
4. **两台设备勿混**：UniXNU 路线 = `6033dbec`；hackios 旧记录 = `ffec9d48`。
5. 收尾前过 RECORDING-RULES §8 三连问（坑已落 PITFALLS？当轮写入？互引闭合？）。
6. 三层书目见 READING-LIST.md（现状 → 历史 → 上游）。

## 5. 关键产物 sha 索引（以 build-verification.json 为最终依据）

**Boot 镜像（E:\k60-work\candidates\4g-quiet\）**
| 版本 | boot img sha256 | kernel macho sha256 | 结果 |
|---|---|---|---|
| 进度条基线（11-02 20:03） | `302a001b…`（kernel `65fbe51e…`） | — | 曾出进度条；A1 在新 Data 上 K60SELF panic（I-20261103-07） |
| v2（pong 用户态首轮） | `a9ae831e…` | `66dcc802…` | 信任缓存装载 panic（miniamfi loadModule） |
| v3 | `d9b9d6fd…ce02` | — | EL1 数据中止（静态区） |
| v4（未上机） | `1113d1b0…` | `ed985662…` | — |
| v5 | `310f7bc1…` | `88c49e85…` | 清单几何错 → mount root panic（I-20261103-11） |
| v6 | 见 candidates build-verification.json | — | pong init 跑通至 exec launchd 前（§1 卡点 2） |

**Data 窗与清单（E:\k60-work\candidates\data-20352\ 与 archive\）**
| 对象 | sha256 | 说明 |
|---|---|---|
| data-window-20354-pre-ponginit-backup.img | `adbbf0dd…` | 11-03 05:17 写入设备的原始 20 GiB 窗（写后回读一致） |
| data-window-20354.img（pong-init） | `81a2662f…` | 11-03 17:09 写入设备（含 `/private/var/pong/init`），回读一致 |
| shngroot-final-20261103.bin | `33626441…` | **几何正确**（= `archive/rollback-v2-ponginit/rb-manifest.bin`），修复基底 |
| shngroot-v2.bin | `5dfc7ea7…` | **几何错误**（当前设备在役，待按 I-20261103-11 方案替换） |
| shngroot-draft.bin | `d443e541…` | 草案（digest 占位零，禁止写设备） |
| pong init（init-v2，deliverables\pong-init\） | `68d9bb06…` | exec 目标已改 `/sbin/launchd`；原件 `faa38544…` 留作回退 |
| 全分区回滚（11-03 03:40，9.4 GiB） | `fca1ffaa…` | `archive/unixnu-rollback-20261103-0330/`，可整体写回 |

## 6. 已知编号冲突（只登记不擅改）

1. DECISIONS.md 存在两条 `D-2026-11-03-04`（Data 窗写入 / v2 Pong 落地）。
2. 双坑编号体系并存：`PITFALLS.md` 的 `P-NN` 与 `PITFALLS-FROM-HISTORY.md` 的「第 N 条」。
3. DECISIONS.md 顶部因 D-17/18 插入，编号不再严格时间倒序。
4. （已消除）旧 INDEX 的「待落盘」状态过期 3 处——本重写版已替换；旧版存档于 `archive/INDEX-20261103-map.md`。
5. （已修复 2026-11-04）PITFALLS-FROM-HISTORY 重号三组：旧 29（df/du Used）→ **33**；旧 30（PS 双引号展开）→ **34**；主线同日新增的 32（fakeroot 缺 Availability.h）→ **35**。全部移卷末并附「编号说明」，现 1..35 连续无重号；全库核对无「第 29/30/31 条」外部引用受影响。

## 7. 事件流水（2026-11-03 下午 → 11-04，增量）

- 11-03 17:09 v2 写盘：Data 窗换 pong-init 镜像（`81a2662f…`）+ 清单换 `5dfc7ea7…`（**几何错误**，I-20261103-11 根因）。
- 11-03 18:52 v2 boot：静态信任缓存装载 panic（miniamfi `loadModule` 返回 Unsupported）。
- 11-03 19:0x v3 boot：EL1 数据中止（静态区）；v4 构建未上机。
- 11-03 20:49/21:06 v5 两次 boot：越过早期 panic，mount root 失败（三窗 `prepared=0`）→ 定位清单几何错误。
- 11-03 19:28 pong 用户态全量移植矩阵完成（`references/PORT-ALL-MATRIX.md`）；v5 = port-all 首轮落地。
- 11-03 晚 三制度立规（D-2026-11-03-18：几何真值 / 写前全范围备份 / 取证 sidecar+抽读）。
- 11-04 06:03 ramoops 读取实测失败 → D-2026-11-04-01 定案：屏摄唯一证据源，ramoops 结构性不可用；**USB 日志通道升为主线并行必需项**。
- 11-04 v6 上机：pong init 跑通至 exec launchd 之前（§1 卡点 2，修正「卡在 write-check」旧假设）。
- 11-04 上游跟进机制落地：新增 `UPSTREAM-SYNC.md`、`DEVICE-REPOS.md`（快照）、`tools/device-hub/devices.py`（list/find/pull-check）、`tools/repo-hygiene/push-check.py`；铁律新增第 6 条「实时优先，缓存仅作检索副本」（AGENTS.md / INDEX / RECORDING-RULES §0 / project_memory 四处同步）；`AGENTS.md` 路由表加 UPSTREAM-SYNC 与 DEVICE-REPOS 两行。
- 11-04 USB 日志通道实施包就绪：§9 裁决（CDC-ACM 胜 ECM，pong-usb 同 SoC 实测 vs ECM 仅 SM7150 实测且 K60 零上机）→ §10 实施前审计 → `k60_usblog.c` 单点一档到底（609→1321 行，SMMU SID0 bypass + CDC-ACM + 环排水，halt→SMMU→CSFTRST）；编译 0 error；`boot-usb-cdc-20261104.img`（`155520e2…`）落 `usb-a-stage\out\`，待上机。坑表 +2：#39（bsd/dev 线程原语 undeclared）、#40（boot.img kernel_size 不对齐）；#36 附 2 直接引用。
- 11-04 USB 首轮上机 panic（nested panic ×5，锁符号化=`_vm_page_locks+0x80`）→ 改打法：F1（SMMU dump 移出 arm_init 探针）+ F2（主线新鲜 clone `3c1bea3` + 0300 + 补 0301–0305 **诊断探针**——「=v5 事实补丁面」口径有误，v5 功能面另含 diffs/ 下 v4 基线两件 + step1..4，见第 47 条）+ cmdline 硬闸门（与 v5 逐字一致仅多 `k60_usblog=2`，PASS）→ 重建得 `boot-usb-cdc2-20261104.img`（`5606aabd…`），等上机窗口。坑表 #39/#40/#42 当轮落。
- 11-04 晚 cdc2 上机：panic `failed to load static trust cache module: 0 @kern_trustcache.c:921`（v2 同坑复发；屏摄经用户核对）——根因 = 新鲜 clone 未携带 v4「B 决策」两件（未入 series）；同屏 mutex 行为警告非死因。当轮落：D-2026-11-04-04（B 决策补录入册）、I-20261104-08（含最小验证判据表/离线指纹 `trust_cache_init`）、第 47 条；HANDOFF §4  mutex 归因错误已更正。下一步 = cdc3（cdc2 + v4 两件）离线三闸后上机。
- 11-04 机制收尾：`PUSH-BACKLOG.md`（待推送勾清单）与 `references/TRUSTCACHE-UPSTREAM-PRIOR-ART.md`（owner trust cache 上游先例，服务 v2/v3 死点）落盘；MASTER-INDEX 互链区补上游同步两行，AGENTS.md 去掉「索引会话生成中」括注。
- 11-04 k60build 推送（用户单条授权）：`git push fork k60build` 快进 `066a3da..56e1da1`（7 条 commit），远端核对一致；main/origin 未触碰，无 force；mondrian/uefi 两分支配额内不推（等单独批准），ios-sweet main 判为 non-ff 禁止强推。记录：`references/upstream-watch/CHANGES-2026-11-04.md` 末节 + `docs/PUSH-BACKLOG.md` §1.1。
- 11-04 铁律新增第 7 条「屏摄读数三选一才可作证据」：INDEX 铁律区 / RECORDING-RULES §7.9 / project_memory / `D:\Android\AGENTS.md`（标题 6 条→7 条）四处同步；同轮修复坑表重号（29→33、30→34、32→35，见 §6 第 5 项）；PITFALLS-FROM-HISTORY 第 32 条（识图误读五连）补录，实例 3–5 原屏摄已定位 `evidence/screen-v5-2106-1.png`（sha `65B8DCAF…`）。
- 11-04 坑表编号机制化：`tools\docs\alloc-pitfall-number.py`（锁+计数器取号，并发自测 5×3 PASS）与 `tools\docs\check-docs.py`（五项一致性校验，收工闸门）落盘；RECORDING-RULES 新增 §9（取号必走分配器、收工必跑校验器）；AGENTS.md 维护规则加一行指向；坑表第 37 条登记「并发追加撞号」本身。
- 11-05 **取证工具变更（强制）**：新增 `tools/apfs-device-read.py` —— 通过 adb `exec-out dd bs=4096 count=1` **按需取块**解析 Data 窗 APFS（内存缓存 + `apfs.py` 随机读接口），解析 `/pong` 仅取几十块（实测 81 块≈324 KiB），**不再落 21 GB 全量容器镜像**。配套 `tools/extract-console-0306.py` 导出 `/pong/console.log` 全文。原因与误判（WSL `df` 显示的是 vhdx 虚拟容量、真实占用在 D 盘）见坑 **#61**。历史全量镜像仅保留一份已登记 sha 的 `evidence/console-drain-20261105/data-container-apfs.bin`（sha `257AEC0B…`）。
- 11-05 夜 **USB 串口日志通道打通**（用户质询「酷安有人说打通串口能提高效率，现在怎么还没打通」）：0307 修 `k60_usblog.c` 的 DMA cache 一致性（KMA_ZERO 脏行 + `ud_events()` 读数前无 invalidate → 事件全读成 `0x00000000`、`ev` 在涨但 `cfg=0`）+ 设备描述符 `02/00→02/02` 让 Windows 自动绑 `usbser.sys`；实测 `USB\VID_1209&PID_0001` → COM5，单次抓 47,650 B。同时暴露两个**我自己的打包 bug**（boot 镜像 kernel 段多拷 1 页致 ramdisk 后移 4096 B；换核漏打 `patch-armcpu-validate.py`），二者都伪装成 `AppleARMCPU.cpp:111` panic，已入坑表 #64。串口日志定位到 SpringBoard 下一个阻塞：`launchd_cache_loader` `abort: Unable to find AMFI`（`ns=7 code=0x1`）——真 AMFI 的 `IOKitPersonalities` 被 prelink `--library-only` 剥掉 + `k60_sandbox=1` 提前 return 跳过 `miniamfi` 注册，真因是 IOKit 服务缺失（MAC policy 实测一直在册，#65 已纠正）。修复 0309（`k60_amfi=1` 注册 MAC policy `"AMFI"`，`0x60` 应答 `0x86 NOT_ENFORCING`）+ 0310（`amfi.c` keep-first）+ 0311（panic 路径写 IMEM `0x146AA65C=0x77665500` 回 fastboot）；`debug=0x144` 的 `DB_NMI` 导致 panic 停在调试等待是「panic 后不重启」的独立原因（#66），改 `debug=0x140`。文档：`references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md`。待上机件 `boot-amfi0312-20261105.img`（`32dfaa39…`）。
