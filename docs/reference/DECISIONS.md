# K60 iOS 移植 — 决策记录（DECISIONS）

## D-2026-11-04-04 trust cache 路径定案补录：v4「B 决策」入册 + cdc2 复发判定

- **日期**：2026-11-04（补录 11-03 定案 + 11-04 晚复发判定）
- **背景**：v2 boot panic `failed to load static trust cache module: 0 @kern_trustcache.c:921`（miniamfi `loadModule` 返回 `kTCReturnUnsupported`）；v3 把返回码改 `kTCReturnSuccess` 但不供模块 → EL1 数据中止（实测，INDEX §5/§7）。11-03 定「B 决策」：**对齐 pong，摘掉整条 trust cache 路径**——但当时只落在 `E:\k60-work\diffs\v4-baseline-config.patch` / `v4-baseline-miniamfi-revert.patch` 与构建树，**未入册、未入 series**。
- **B 决策内容（以 v4-baseline-config.patch 原文为准）**：`configs/mondrian_defconfig` 置 `CONFIG_XNU_NATIVE_TRUST_CACHE=n` + `CONFIG_XNU_TRUST_CACHE_RUNTIME=n`；`board.toml` `trust_cache_sha256=[]`；打包链不再传 `--trust-cache`（payload 无 sidecar）；miniamfi 两个装载桩**回退 pong 原文**（`kTCReturnUnsupported`）。效果：`startup.c:741-749` 的 `trust_cache_runtime_init()`+`load_static_trust_cache()` 块被 `#if … XNU_NATIVE_TRUST_CACHE` 编译期排除，`loadModule` 永不被调，与 pong 结构级一致（pong 两 defconfig 同双 n）。
- **复发判定（2026-11-04 晚，cdc2）**：`boot-usb-cdc2-20261104.img`（sha `5606aabd…`，新鲜 clone `3c1bea3` + 0300 + 0301–0305 探针）上机 panic 于同一 `:921`（用户核对的屏摄读数）。根因：`3c1bea3` 的 repo 真值仍是 `TRUST_CACHE=y/y` + 白名单 `["344ae644…"]`（`git show 3c1bea3:` 实测），**B 决策不在 series 里**，新鲜 clone 不携带；「0301–0305=v5 事实补丁面」口径错误（0301–0305 仅诊断探针，v5 功能面 = v4 基线两件 + v5-step1..4）。
- **离线实证**：`grep -a -c trust_cache_init` —— cdc2 boot img = **1**（路径编入），v5 boot img = **0**（路径摘除）；v5 payload 无 `kernel.macho.trustcache` sidecar。
- **决定**：① B 决策为现行定案，禁止回退到 v3 式「空 success」（TRUSTCACHE-UPSTREAM-PRIOR-ART §0/§3 已证雪崩）；② 后续一切基于新鲜 clone 的构建必须把 `diffs/v4-baseline-config.patch` + `v4-baseline-miniamfi-revert.patch` 当**基线组成部分**同步叠加（cdc3 = cdc2 + 这两件，其余不动）；③ 根治方向 = 把 v4 两件做成 series patch 提交入库（待用户拍板后执行，消除「clone 即丢」形态）。
- **验证方式**：离线三道闸（见 ISSUES I-20261104-08 判据表）全过后才上机；上机判据 = 无 `:921` panic，进度至少追平 v5 阶段。
- **回滚方式**：纯打包/config 层改动，不涉及设备写；回退 = 撤两件补丁重打。
- **相关文件**：`E:\k60-work\diffs\v4-baseline-{config,miniamfi-revert}.patch`、`references/TRUSTCACHE-UPSTREAM-PRIOR-ART.md`、PITFALLS-FROM-HISTORY 第 47 条、I-20261104-08。

## D-2026-11-04-03 USB 日志通道形态定案：pong-usb CDC-ACM（弃 ECM 虚拟网卡），一档到底

- **日期**：2026-11-04
- **背景**：用户质询「用 hackios 虚拟网卡还是 pong-usb，确定可行吗」。两条候选：A=ios-sweet 时代 CDC-ECM+UDP（`USB-LOG-CHANNEL.md` 11-02 推荐）；B=pong-usb CDC-ACM（研审 v3 方案）。
- **证据**：①B 有**同 SoC SM8475 真机实测**（pong-usb `6070a991`，12 s 收 108,518 B，`UniXNU-pong-upstream` services135 L45）+ SM8850 独立旁证（pandora `PLAN.md`「USB 串口实时日志」列真机已验收，2026-11-04 实时抓取）；②A 仅 SM7150 实测（无 apps_smmu 前提，不适用 K60），K60 适配（ios-sweet-k60 0143/0148）**0 次上机**（commit `b2ae97e` 缺口表原文）；③UniXNU 主线全分支仅 1 条 USB commit（`b9ecfdb`，纯宿主侧工具，内核侧零实现）；④两条路内核硬前置（SMMU SID0/GCC/DMA 高字/cache）完全相同，ECM 额外多 ifnet/mbuf/UDP 三层失败面且 Windows 无 inbox 驱动。
- **决定**：USB 日志通道 = pong-usb CDC-ACM 形态，单点 `bsd/dev/k60_usblog.c`，`k60_usblog=2` 一档到底（无 v1/v2/v3 分档）；宿主侧 Windows usbser 免驱 COM 口。`USB-LOG-CHANNEL.md` 的 ECM 推荐作废（该文 §0 已加更正指针，原文保留备查）。若未来需要网络形态（KDP/gdb），通道稳定后单独立项。
- **实施要点（随案定）**：静息顺序 halt→SMMU→CSFTRST；SMMU bypass 移植 `SmmuTakeover.h` 并补 R-B1（NUMS2CB 拒绝）；C3 的 UFS 等待由「kext 导出」改为「worker 硬件轮询 SMR 0xe0」（内核本体链接期引用不了 kext 符号，语义等价且更真）；环消费遵守 D-2026-11-04-02（只读、独立游标、seqlock 双重读）。
- **验证方式**：上机判据与失败形态矩阵见 `E:\k60-work\usb-a-stage\REPORT-CDC.md` §4/§5（宿主收到真实 console 字节流 = 打通）。
- **回滚方式**：去掉 `k60_usblog` boot-arg 即现状；镜像只 boot 不 flash，零持久副作用。
- **相关文件**：`references/USBM-LOG-CHANNEL-AUDIT.md` §9/§10/§11、`E:\k60-work\usb-smmu\`（DESIGN/RISKS/draft）、`E:\k60-work\usb-a-stage\REPORT-CDC.md`、坑表第 39/40 条。

> **用途**：所有「这么干而不是那么干」的定案——**结论类信息的唯一权威源（SSOT）**。
> **谁该读**：新 agent 进场必读三份之一；要引用任何已定案结论时来这里找编号。
> **边界**：问题/现象归 ISSUES.md；教训/30 秒判定归 PITFALLS*.md；commit 流水归 HISTORY-LEDGER.md。其余文件提到同一结论只留一句 + 指向 D-编号。
> 时间倒序。每条：日期、背景、证据、决定、验证方式、回滚方式、相关文件。
> 只写有证据的；没有实物证据的标「待验证」。新增条目追加到**最上方**（§1 之下）。
> **已知编号异常（只登记不擅改）**：存在两条 `D-2026-11-03-04`；D-17/18 插入后顶部编号非严格时间倒序。

## D-2026-11-04-02 console 环形区定为「单写者 / 多读者、各自独立游标」结构

- **日期**：2026-11-04
- **背景**：console 全量落盘调研（`references/CONSOLE-FULL-CAPTURE.md`）定稿进入实施。内核 ramoops 环形区（物理 `0xA7000000`、2 MiB、`DBGC` 头 sig/start/size、无读指针）将有多个消费者：文件排水器（`kern.pong_ramoops` sysctl → Data 卷，补丁 `0243-k60-console-export.patch`）、未来 USB/ECM 日志流（k60_usblog 线程）、以及任何后续读者。
- **证据**：写者实现 `osfmk/arm/arm_init.c:117-173`（busy 自旋，争用即丢）；`pong_ramoops_console.h:16-20`（头仅 sig/start/size）；hakios `sweet_log_copy` 的调用者自带游标先例（`USB-LOG-CHANNEL.md:92`）；现 `k60_usblog.c` 只到 ep0 探针、尚未读环形区（usb-a-stage 实测）。
- **决定**：
  1. 环形区 = **单写者多读者**：写者唯一（console 钩子 + Adreno 诊断桥接），每个消费者自维护独立 64 位流游标，**谁先到谁读、互不仲裁**；
  2. **任何读者禁止写 12 字节头、禁止取 busy 锁**（读者取锁会让写者丢字节）；一致性靠 seqlock 双重读 + 有界重试；
  3. 回绕「丢旧保新」对所有读者一视同仁，各方各自记 GAP，不互相吃掉数据；
  4. 环形区物理布局（12B 头 + 数据区）不变；容量调整只改 `PONG_RAMOOPS_CONSOLE_BYTES`（DT 保留区实为 4 MiB，`mem-audit-dump2.txt:41`）。
- **验证方式**：USB 通道落地后双消费者同跑一轮，对比双方 GAP 计数与文件落盘内容一致性。
- **回滚方式**：读者侧（sysctl / USB 流）移除即可，写者语义不变。
- **相关文件**：`references/CONSOLE-FULL-CAPTURE.md`、补丁 `0243-k60-console-export.patch`、`osfmk/arm/arm_init.c`、`USB-LOG-CHANNEL.md`。

## D-2026-11-04-01 XNU 阶段证据采集固定为屏摄；ramoops 不作可依赖取证手段

- **日期**：2026-11-04
- **背景**：内核 `console_write` 确有 ramoops 旁路（`osfmk/console/serial_console.c:517-575`，物理 `0xA7000000` 起 2 MiB 环形区），曾设想「冻结后进 TWRP 读 ramoops 拿日志」；2026-11-04 06:03 实测 TWRP（Fuutao 5.10.237）无 `/dev/mem`、`/dev/kmem`，adb 随即掉线（I-20261104-01）。
- **证据**：`serial_console.c:517-575` 源码；2026-11-04 06:03 现场记录（两个设备节点 No such file or directory）；**用户 2026-11-04 现场确认：XNU 重启/复位后 ramoops 内容在任何后续系统里都读不到——TWRP 读不到，进 Android 也读不到**。
- **决定**：
  1. **XNU 阶段证据采集固定为屏摄**（RECORDING-RULES §7 流程）。ramoops 通道**结构性不可用，非时效问题**：读取日志的前置动作本身是重启（进 TWRP/安卓），重启必清 DRAM，流程里不存在可用窗口——任何计划/报告不得再列「读 ramoops / devmem / kcore」或「抓紧在重启前抓」类步骤；
  2. **唯一可行解法（用户原话确认）：「除非打通 XNU 里的 USB 日志通道。」** 即复位前内核自己把 console 流从 USB 吐出，不依赖任何重启后的读取——这正绕开 ramoops「重启即失」的死结。已知死亡点：`k60_usblog.c` 的 SMMU 路径——apps_smmu stream 0 无 context → TZ 强制整机复位（I-20261103-04）；破法已有草案（SMMU stream 0 context 设计）。**本条标为主线并行必需项（调试放大器）**：它直接决定每轮试错的信息量——目前一轮只有一张屏摄，通道打通后每轮有完整 console 流。（flash 持久化路线一并否决：需写盘能力与已发布驱动，现状不具备。）
- **验证方式**：本决定生效的判定 = 后续所有取证计划中文本检索无「ramoops 读取」类步骤；屏摄流程按 §7 执行；USB 日志通道以「主机侧收到 XNU console 流」为打通判据。
- **回滚方式**：若 USB 通道确认不可行，追加新 DECISIONS 重议；本条不阻塞主线取证（屏摄保底）。
- **相关文件**：`osfmk/console/serial_console.c`、`docs/PITFALLS-FROM-HISTORY.md` 第 16 条、`docs/ISSUES.md` I-20261104-01、PITFALLS P-10、ISSUES I-20261103-02/I-20261103-04。

## D-2026-11-03-18 几何真值来源 + 写前全范围备份 + 取证 sidecar/抽读上限（三制度，用户批准方向）

- **日期**：2026-11-03（本轮 unixnu 扩容/取证复盘后立规）
- **背景**：本轮集中暴露三类流程缺口——①清单生成脚本 `tools/make-shngroot-manifest.py` L22-26 把规划尺寸写真值，产出错误几何清单并落盘（I-20261103-11，v2–v5 mount root 失败的根因）；②取证按错误几何读设备 + dump 无 sidecar，一度误判「三窗全毁」（I-20261103-12）；③17:09 写盘前备份范围 < 写入范围（I-20261103-13）。
- **证据**：四份清单解析对照（draft `d443e541…` / final `33626441…` / v2 `5dfc7ea7…` / `rb-manifest.bin`）；`evidence/blocks/` 复核（OS 头与 03:40 回滚逐字节一致 sha `6fed98dd…`）；`archive/rollback-v2-ponginit/ROLLBACK-METADATA.json`。
- **决定**：
  1. **几何唯一真值来源** = 设备在役 SHNGROOT 清单或其回滚件；任何脚本禁止写死窗口偏移/尺寸；清单落盘前断言 `OS off==0x100000 && SystemOS off==0x12FE00000`（设备真值变动时先改断言再走流程）。
  2. **写前备份完整范围**：任何写盘动作的备份范围必须 ≥ 实际写入范围（整窗，非头部抽样），备份 sha256 双读一致才放行，回滚件登记 ROLLBACK 元数据。
  3. **取证两件套**：每个 dump 必须落同名 sidecar json（源设备、skip、bs、count、字节偏移算式、时间、sha256），无 sidecar 不作证据；取证只做定点抽读（单次 ≤ 64 KiB、串行、总量设上限），禁止整盘/整窗全量读入。
- **验证方式**：下次写盘/取证按此检查单执行并回写本条「验证」栏；`make-shngroot-manifest.py` 修正后首次生成的清单逐字段与设备在役清单比对。
- **回滚方式**：流程层制度，无技术回滚；条目修订走正常 DECISIONS 追加。
- **相关文件**：`tools/make-shngroot-manifest.py`、`/tmp/build-manifest.py`（正面先例）、`docs/PITFALLS-FROM-HISTORY.md` 2026-11-03 轮新增第 6–14 条、`docs/RECORDING-RULES.md` §8。

## D-2026-11-03-17 分支收敛：每仓只留 main（+archive），里程碑全部转 annotated tag

- **日期**：2026-11-03（用户批准"收"）
- **a5-timeout 判定（先判定后处置）**：`fef75ea`（payload 菜单 countdown `timeout = -1 → 5`）**已被主线完全吸收**——当前 main `board.toml:103-110` 含 `timeout = 5` 及逐字相同的注释（含 2026-10-29 18:47 实测记录）→ 判定无用，**不建 tag，直接删**；diff 存档 `docs/archive/a5-timeout-fef75ea.diff`。
- **tag 补齐（annotated，全部推送并 ls-remote 核对 deref sha）**：
  - mondrian 新建 `v0.1.0-progressbar-device`（→48abe35）、`v0.1.1-ios16-main-merged`（→3c1bea3）；已有 `v0.0.9-premain-8598c97`、`v0.1.0-progressbar`（→66a603f）、`v0.2.0-darwin24-archive`（→10d1be3）。
  - fork `v0.1.0-progressbar-core`（→db7177c，已在远端）。
  - uefi 新建 `v0.1.1-fd-darwin22`（→6244582）；已有 `v0.1.0-high-window-fd`（→e06211d）。
- **远端分支删除（tag 核对全过后执行）**：mondrian 删 5（`progress-bar-20261102`、`baseline/progressbar-device-20261102`、`ios16-main-20261103`、`fix/k60-measured-high-window`、`a5-timeout`）；fork 删 1（`baseline/progressbar-core-20261102`，`k60build` 保留=构建在用）；uefi 删 2（`baseline/high-window-fd-20261102`、`fix/k60-measured-high-window`）。全部成功。
- **本地分支删除（`git branch -d`，不用 -D）**：mondrian 删 `baseline/*`、`main`（旧 darwin24 线）；fork 删 `baseline/*`；uefi 删 `baseline/*`、`main`。**跳过**：mondrian `ios16-main-20261103`（`-d` 报 not fully merged——本地 main 已删导致祖先链不可达，按纪律保留）、三个被检出分支（mondrian/uefi `fix/...`、fork `k60build`）、fork `main`/`smp-0340`（其他 worktree 检出中）。检出分支的 gone upstream 已 `--unset-upstream` 清理。
- **收尾清理（同日用户批准）**：mondrian 本地 `ios16-main-20261103`（`c39ff29`）经前置核对（`rev-parse` 与 `origin/main` 同 sha、`log -1 %H` 一致）后 `git branch -D` 删除——尖端内容已达远端 main 且 tag `v0.1.1-ios16-main-merged` 锚定同内容。fork 远端 `k60`（`db7177c`）保留不动（fork 固有分支，非我方工作线，已在 REPO-BRANCH-MAP 标注）。
- **最终形态（ls-remote 实证）**：mondrian = `main`(c39ff29) + `archive/darwin24-main-20261103`(10d1be3) + 5 tags；fork = `main` + `k60` + `k60build` + 1 tag；uefi = `main` + 2 tags。
- **回退方式**：所有被删分支的 sha 均有 tag 锚定（或 diff 存档），`git push origin <sha>:refs/heads/<name>` 可恢复。
- **相关文件**：`E:\k60-work\git\conv-*.txt`、`docs/archive/a5-timeout-fef75ea.diff`。

## D-2026-11-03-16 推送 11 条提交 + 远端 main 一次性切换为 iOS16 主线（已执行）

- **日期**：2026-11-03（用户确认执行）
- **第一阶段（普通推送，全成功）**：
  - mondrian `fix/k60-measured-high-window` → origin 同名分支（新建），远端 = `3c1bea3` = 本地。
  - fork `k60build` → **`fork` remote**（Emilelu/UniXNU；`origin` 是 org 仓无权限，首次误推 403 后改 fork），远端 = `066a3da` = 本地。
  - uefi `fix/k60-measured-high-window` → origin 同名分支（新建），远端 = `6244582` = 本地。
- **第二阶段（切 main，唯一 force 步骤）**：
  1. 保底 tag `v0.0.9-premain-8598c97`（annotated，tag obj `4a795e57` → `8598c97`）先推送并核实存在。
  2. 临时 worktree 从 `progress-bar-20261102`（`66a603f`）建 `ios16-main-20261103`，`--allow-unrelated-histories` 合入 `fix/k60-measured-high-window`；唯一冲突 = `README.md` add/add，按用户裁定：设备线为主体 + 追加「内核基线（progress-bar-20261102）」章节（基线 sha/能力/已知缺陷照录，未改写事实）。merge commit = `c39ff29`。
  3. 三条自检全过：①13 个关键路径（board/dts/series/scripts/docs/configs/feeds/lock）合并树与设备分支 sha 逐一相等；②series 项数两侧均 123；③`git diff` 5013 个差异路径全部是设备分支没有的内核源树文件 + README（预期内）。
  4. 强推：`git push --force-with-lease=refs/heads/main:8598c9797d455dfe275d889c3a873ca0b0d38796 origin ios16-main-20261103:main` → `8598c97..c39ff29`。
  5. 远端核验：main = `c39ff29`；`archive/darwin24-main-20261103`（10d1be3）、`progress-bar-20261102`（66a603f）、`baseline/progressbar-device-20261102`（48abe35）、`fix/k60-measured-high-window`（3c1bea3）、`a5-timeout`、tag `v0.0.9-premain-8598c97`/`v0.1.0-progressbar`/`v0.2.0-darwin24-archive` 全部在场。
  6. 默认分支未改（仍 main）。
- **远端分支最终形态**：`main` = iOS16 主线（开发主线，持续前进）；`progress-bar-20261102` = 里程碑永久保留；`baseline/*`、`archive/*` = 锚定保留；`fix/k60-measured-high-window` = 设备配置工作线（已合入 main，可继续用或退役待用户定）。
- **回退方式**：`git push --force-with-lease origin 8598c97:main`（tag/存档分支均在）。
- **纪律遵守**：xnu-work 脏树未碰、构建树未碰、参考仓库未碰；fork 仓 remote 归属已登记（origin=org 只读，fork=自有可写）；子模块指针未 bump。
- **相关文件**：`E:\k60-work\git\push-p*.txt`、`p2-*.txt`、`docs/MAIN-SWITCH-PLAN.md`。

## D-2026-11-03-15 三组脏改动整理为合规提交（mondrian 6 + fork 4 + uefi 1）+ 子模块本地提交

- **日期**：2026-11-03
- **背景**：mondrian 55 项、fork 9 项、uefi 3 项未提交改动，经用户确认的分组方案整理为 feflow 规范提交；一组一提交、不 push、不改文件内容（唯一例外：`unixnu.lock` 的 xnu pin `d8b80295` 恢复为 `1b191cb`，见 ISSUES I-20261103-09）。
- **提交清单**：
  - mondrian（`fix/k60-measured-high-window`，48abe35 → 3c1bea3）：`738c6e2` chore(scripts) 37 脚本可执行位 / `5e97e9d` fix(board) 4.75 GiB 高窗口（board.toml+dts）/ `c28f5e8` chore(lock) PongUfs pin / `28d358c` feat(series) 4 诊断探针入系列（删 0240）/ `f06cd07` feat(scripts) patch-armcpu-validate.py / `3c1bea3` docs(porting) 3 文档+AGENTS+porting.toml。
  - fork（`k60build`，db7177c → 066a3da）：`832b5cd` chore(gitignore) / `a21789e` feat(vendor) c++filt shim 恢复 / `711abc1` fix(build) HOST_CC/MIG 环境变量 / `066a3da` feat(payload) armcpu 补丁自动化（沙盒钩子引用不存在脚本，已记 ISSUES I-20261103-08）。
  - uefi（`fix/k60-measured-high-window`，e06211d → 6244582）：`6244582` fix(fd) Darwin22 boot_args + XNU High Arena 描述符。
- **子模块本地提交（仅本地，不推远端、不 bump 父仓指针）**：XnuPrelink `d2e15c85d413661dca474be15d433cbb9d3cd8eb`（emit_prelink.py 调整）；Mu_Basecore `3d2a9fab4eea41634a0cb4a2feb2580afc59d090`（11 文件 K60 固件修复）。**换机/重编需带工作副本**。
- **pong-driver 处置**：原 V1 vendor 提交 `315cf99` 已放弃（磁盘内容消失 + 经审计 12 项中 11 项在 mondrian 仓有同源副本可放弃，仅 `shim-bin/c++filt` 为独有——因 `build-xnu-4k-baseline.sh:240-247` 依赖其 shim-bin 在 PATH 而恢复，提交 `a21789e`）。`315cf99` 保留于 reflog，不 gc。
- **不提交项**：mondrian `mac-build/`（94 MB 构建产物）、3 个孤儿补丁草稿（zzyb-cryptex / zzyc-skip-launch / quiet-watch，未入 series，保持 untracked，见 HISTORY-LEDGER §7.2）；fork `pong-driver/`（symlink 农场，已整体 gitignore）、`pong-adreno-*/`、profiles 18.7.10 实验目录。
- **验证**：三仓 `git status --porcelain` 复核——mondrian 剩 4 项 untracked（mac-build + 3 孤儿补丁，全部刻意保留）；fork 仅子模块指针（不 bump 是刻意的）；uefi 仅子模块指针（同理）。敏感扫描零命中。
- **回滚方式**：全部为新提交未推送，`git reset --hard <旧HEAD>` 即可（mondrian `48abe35`、fork `db7177c`、uefi `e06211d`）。
- **相关文件**：`E:\k60-work\git\`（msg-*.txt、commit-log-*.txt、pong-driver-audit-*.txt）

## D-2026-11-03-14 路线决策：iOS 18（Darwin 24）推进排到 iOS 16 修得差不多之后

- **日期**：2026-11-03（用户口头决定）
- **性质**：路线决策，不是待办。
- **决策**：iOS 18（Darwin 24）路线不并行推进，待 iOS 16（20G81）基本可用后再启动。
- **依据**：darwin24 归档线已完整冻结——`archive/darwin24-main-20261103`（45 提交，尖端 `10d1be3`）+ tag `v0.2.0-darwin24-archive` 均已推送，随时可接续，无需重新考古。
- **技术差异提醒（供将来直接复用）**：Darwin 24 强要 system-proxy persona，pong 靠 `pong_persona_bootstrap` 预建两个 persona（`pong-sys` uid=-1、`pong-mobile` uid=501）解决；**Darwin 22（我们的 20G81）不需要 persona，也能进 launchd**——不要把 16 的经验直接套到 18。

## D-2026-11-03-13 darwin24 归档分支推送（覆盖 D-12 的「直推 main」建议）

- **日期**：2026-11-03
- **背景**：用户否决 D-2026-11-03-12 的「直接推 main」建议，理由：45 条提交对当前 iOS16/20G81 修复基本无助（17 条构建链属 iPadOS18 线、3 条 route-a-17 旧 series、其余文档/调研/台账；仅 2 条 payload 探针有借鉴价值），不应推上 main。
- **执行**：mondrian 新建 `archive/darwin24-main-20261103`（= 本地 main 尖端 `10d1be3`）并 `push -u origin`；打 annotated tag `v0.2.0-darwin24-archive`（tag 对象 `26b45cd` → `10d1be3`）并推送。**远端 `main` 未推未动**（仍 `8598c97`），本地 main 原样。
- **核验**：`ls-remote` 确认远端五分支（`main`、`a5-timeout`、`progress-bar-20261102`、`baseline/progressbar-device-20261102`、`archive/darwin24-main-20261103`）+ 两 tag（`v0.1.0-progressbar`、`v0.2.0-darwin24-archive`）。
- **关系登记**：darwin24 归档线与 iOS16 主线（`progress-bar-20261102`）互不混入；可用性判断「仅 `9807d4b`/`58746fc` 两条 payload 探针可借鉴」已同步登记 HISTORY-LEDGER §7.1。
- **纪律**：零 force push、零 reset、未改远端 main。
- **回滚方式**：删除远端该分支与 tag 即可（纯新增引用）。

## D-2026-11-03-12 分支清理批次（保守口径）与 main 45 提交定性

- **日期**：2026-11-03
- **背景**：用户对 D-2026-11-03-11 的删除清单回复「全按你建议」，按保守口径执行（有独有提交的一律保留）。
- **已删（删前存在/删后消失均已核对，远端经 ls-remote 复核）**：
  - 本地：mondrian `fix/darwin24-cpu-first-boot`（与现役分支同提交 `48abe35`）；fork 16 个（`k60c2/c3/c4/cpu/dt/edit/push/roots/roots2/oscfg/wf154` + `corek60/coretc/k60rev/wf15/wf26`，全部 0 独有提交、已并入 `fork/k60`；后 5 个先 `git worktree prune` 清理失效注册）。
  - 远端：mondrian `k60`、`route-a-18`（已并入 main）；fork 17 个 org 快照 topic 分支；ios-sweet-k60 fork 的 `cache-ci`、`fb-probe`。
  - 目录：`~/hackios/work-display/device`、`~/hackios/work-display/pw`（删前 tar 备份至 `~/k60-archive/2026-11-03/work-display-device-pw-backup.tar.gz`，1.7 MB；无进程占用；`make-pong-adt.py` 的 `work-display` 匹配为 `artwork-display-gamut` 误报）。
- **保留项**：远端 `a5-timeout`（独有提交 fef75ea）；本地 `smp-0340`（独有提交 `4d6d0e4`，`~/smp-core` 检出中）；全部基线分支与 tag。失败 0 项。
- **main 45 提交定性**（`git rev-list --count origin/main..main` = 45，挂在本地 `main`，upstream=`origin/main`；同时被 `fix/k60-measured-high-window` 与 `baseline/progressbar-device-20261102` 包含）：
  - 主题六类：darwin24 构建链 17、darwin24 文档/交接 12、route-a-17 终点 3、上游调研/规范 6、payload 探针 2、合并节点 2、分支台账 3。
  - 凭据扫描：`ghp_/gho_/password/secret/api key/PRIVATE KEY/token` 全零命中。
  - 敏感点：设备序列号 `6033dbec` 新增 5 处（**已存在于 origin/main 五个文档**，非新暴露）；`deepseek-harness` 绝对路径为新暴露（`/mnt/c/Users/Emilelu/Documents/deepseek-harness/…`，无凭据性质）；其余为本机 WSL/Windows 工作路径。
  - 与 123 补丁系列关系：无内容重复；仅 `e5f23c4`/`6e94f41` 曾把 `patches/xnu/series` 改成 17.7.11 的 62 项旧集（main 现承载 64 项），现役 123 项系列从未提交，不存在冲突。
- **推送建议（本轮未执行，待用户确认）**：建议**直接推 main**（fast-forward，`git push origin main:main`）。理由：main 的身份本就是 darwin24 归档线，45 个提交是其应有内容；`progress-bar-20261102` 是无关历史的内核源树分支，两者不会混淆；A/B 锚定已由 `baseline/progressbar-device-20261102` 承担，无需再建 `archive/darwin24-main-20261103`。双保险备选：`git push origin main:refs/heads/archive/darwin24-main-20261103`（建存档分支）+ `git push origin main:main`。
- **相关文件**：`E:\k60-work\git\main45-report.txt`（逐提交清单与扫描原文）、`E:\k60-work\git\analyze-main45.sh`。

## D-2026-11-03-11 仓库分支整理与进度条基线归档（git 状态盘点 + 基线推 GitHub）

- **日期**：2026-11-03
- **背景**：用户要求盘点 6 个自有仓库（mondrian/uefi-mondrian/UniXNU fork/ios-sweet-k60/PongUfs/sm8475-common）分支状态，并把「能进进度条」基线（2026-11-02 20:03，boot `302a001b48fc…`）以可复现提交序列推上 GitHub；中途追加两条硬要求：commit 规范统一遵循 feflow/git-commit-style-guide（原文已取回存档 `references/feflow-git-commit-style-guide.md`）、重大进展点打 annotated tag + 建基线分支并登记台账。
- **关键事实（盘点）**：
  - mondrian 本地 `main` 领先 GitHub 45 提交未推；现役 123 项 series 是**未提交的工作区改动**（比 fix 分支提交版 −0240 +4 zzzz 探针；main 上只有 64 项旧集）。
  - 4 个主线诊断文件（`kern_exec.c`/`kern_exit.c`/`kern_minimac.c`/`MiniIOMobileFramebuffer.cpp`）此前不在任何分支，只在 xnu-work 工作区。
  - fork 本地 18 分支中 16 个已完全并入 `fork/k60`（0 独有提交）；`smp-0340` 有 1 个独有提交；远端 17 个 topic 分支均为 fork 时 org 快照。
  - mondrian 远端 `k60`、`route-a-18` 已并入 main；`a5-timeout` 有 1 个未并入提交（仅改 board.toml 菜单倒计时）。
- **决定/动作**：
  1. 基线归档：从 xnu-work 仓 `git worktree add` 出 `E:\k60-work\git\progress-bar-20261102`，以自包含根 `cad1c22`（树与 apple-oss `1b191cb` 逐字节一致；浅克隆悬空父指针导致 GitHub 拒收，`commit-tree` 重建无父根后 rebase 重放）+ 123 补丁逐补丁提交（应用器 `git apply`，与构建链 `patches.py` 完全一致）+ 诊断残差单提交（`e4778db`，重放后与 xnu-work 全部 125 脏路径逐字节一致）+ README 文档提交（`66a603f`）。
  2. 推送：mondrian 仓新增 `progress-bar-20261102`（分 3 批快进推送，最终 `66a603fbf1bd75ff2ec6a0fe3db1b5c159c9a6a4`）与 `baseline/progressbar-device-20261102`（`48abe35`）；fork 仓新增 `baseline/progressbar-core-20261102`（`db7177c`）；uefi 仓新增 `baseline/high-window-fd-20261102`（`e06211d`）。
  3. Tag（annotated，均已推送）：`v0.1.0-progressbar`（mondrian，`66a603f`）、`v0.1.0-progressbar-core`（fork，`db7177c`）、`v0.1.0-high-window-fd`（uefi，`e06211d`）。tag 消息含达成能力 + 镜像 sha + 已知缺陷。
  4. 登记：里程碑表入 `HISTORY-LEDGER.md` §7；commit 规范落地映射入 `COMMIT-CONVENTION.md`。
- **中断与恢复**：首次重定根 rebase 进行中遭遇机器重启（WSL vhdx 保留了 rebase-merge 中间态 59/125），经 ORIG_HEAD 核对后 `rebase --abort` 回至 `9e24ab9` 并重新执行成功；xnu-work 全程未受影响（detached @1b191cb、125 脏路径不变）。
- **验证**：推送后 `git ls-remote` 三仓逐一核对 sha 一致；重放树与 xnu-work 逐字节比对（121 路径由 series 覆盖 + 4 诊断文件补齐）。
- **回滚方式**：删除远端新分支/tag 即可（全部为新增引用，未触碰任何既有分支；不删除本地归档）。
- **纪律遵守**：未删任何分支（删除清单仅提交建议待用户确认）；未 force push；未在 xnu-work 提交/改写；未碰参考仓库。
- **相关文件**：`E:\k60-work\git\`（replay-baseline.sh、msg-*.txt、k60-readme-section.md）、`docs/COMMIT-CONVENTION.md`、`docs/HISTORY-LEDGER.md` §7。

## D-2026-11-03-10 进度条基线（11-02 20:03）之后改动台账与「UI 消失」归因（含 USB 专项）

- **日期**：2026-11-03
- **背景**：用户追问「能进进度条的版本之后改了什么、为什么跑不到进度条」，并要求把 USB 通道改动（`k60_usblog`）单独定性。基线 = 2026-11-02 20:03:36 boot（boot `302a001b…` / payload `0854bb38…` / 内核 macho `65fbe51e…`；组成 = xnu 基线 commit `1b191cb`（xnu-8796.141.3，08-14 上游 tag，**非 11-02 提交**）+ 补丁系列 + 4 个主线诊断/替身文件）。
- **commit 层事实（git log 实证，2026-11-03 回读）**：2026-11-02 当天三仓库**零 commit**——UniXNU-fork `/tmp/k60build`（HEAD `db7177c` 10-31）、`UniXNU-mondrian`（HEAD `48abe35` 11-01）、`uefi-mondrian`（HEAD `e06211d` 10-31）；当天全部改动均为未提交工作区（`git status`：xnu-work 约 100 改 + 17 新文件）。
- **基线后改动台账**（按时间；性质＝诊断/功能/构建链/配置/数据）：

  | # | 时间 | 批次 | 文件/行号 | 性质 | 产物与上机 |
  |---|---|---|---|---|---|
  | 1 | 11-02 20:42 | kcdata 版 STR | `kern_exit.c` 150-240/2340-2370 | 诊断 | 镜像 `6153c2aa…`（内核 `64ae6488…`）已上机；STR 分类 sig=6 自杀/sig=5 被杀生效（IMG_0180.JPG + crops 22:12-22:20） |
  | 2 | 11-02 晚 | 心跳轮→直方图轮 | `kern_exit.c`（KX! 限流/直方图） | 诊断 | `db9f3c8b…`/`a73e80c8…`（mkerr=17）、`ed328cfc…`/`cc8cf34e…`（mkE=17/28）均上机（I-20261102-12）；build-verification 缺失（覆盖） |
  | 3 | 11-03 00:5x | A 档建树 + 0300 | `bsd/dev/k60_usblog.c`（新，608 行）、`bsd/conf/files`、`arm_init.c:672-677`、`bsd_init.c:1318-1325` | **功能（USB DWC3，boot-arg 门控）** | `boot-a-usblog2`（arg=2，~35 s SMMU 复位，I-20261103-04）/`boot-a-control`（无 arg，vnode panic，I-20261103-03） |
  | 4 | 11-03 凌晨 | 4.75 GiB 阶梯重打包 | ADT darwinboot-memory-size `0x100000000→0x130000000` | 配置/构建链 | `e5171421…`（payload `59faf30e…`、内核 `c6ed3cae…`），**未上机**（hardware_tested:false） |
  | 5 | 11-03 | P1 argfix | 仅 payload unixnu.toml 补 7 args（内核逐字节不变 `ac896498…`） | 配置 | `310c25a8…` 上机：vnode panic 消除，KX! 78 风暴 |
  | 6 | 11-03 | P2-lite argfix2 | `kern_minimac.c` 同步 + KX! 打印改维 | 功能替身同步+诊断 | `b99064f1…` 上机：78 不变，Sandbox 假设证伪 |
  | 7 | 11-03 | 0302 | `kern_exec.c` 三处 `0x80000000→0x600000000`（L7437/7447/7451 区域）+ exec 错误码 + pid→path | **功能（Data 上限放宽）+诊断** | `9478a25f…` 上机 |
  | 8 | 11-03 | 0303 心跳 | `kern_exec.c`/`kern_exit.c`（K60HB） | 诊断 | `73a0ad0c…` 上机（`dw=20354 dm=1`） |
  | 9 | 11-03 | 0304 | ler/lw + KX? 改维（约 12 行） | 诊断 | `41d81932…` 上机（`ler=13 lw=spawn`） |
  | 10 | 11-03 | 0305 | site= 六处（`kern_exec.c` L3838/3877/3931/4310/4322/4475，约 8 行） | 诊断 | `bb0498dd…` 上机（10:47:22，`site=1`） |
  | 11 | 11-03 03:30+ | **环境：Data 卷替换** | sda38 @0x261100000 写入 19.87 GiB 新种子（`adbbf0dd…`）+ 清单 `33626441…` | **数据** | 非镜像；其后全部 boot 的环境（D-2026-11-03-04） |
  | 12 | 11-03 11:51 | A1 | 基线快照 `302a001b…` + 新 Data | — | K60SELF panic（`datastage=0 dataerr=-22`），D-2026-11-03-09 |

- **逐项「能否导致跑不到进度条」判定**（①进 XNU ②framebuffer/backboardd ③spawn）：
  - #1/#2/#8/#9/#10（诊断）：三个主线诊断文件全量 diff（`kern_exec.c` 286 行、`kern_exit.c` 257 行、`MiniIOMobileFramebuffer` 98 行）**均为诊断，spawn/显示路径零功能改动**（用户已复核结论，本条引用不重复推翻）→ ①②③无影响。**已证实**。
  - #3 USB：见下方专项 → 除 usblog2 一轮外全部惰性，**不解释 UI 消失**。**已证实**。
  - #4：未上机，与当前症状无关。
  - #5：argfix 后 boot-args 已与 4g-quiet 全集一致（I-20261103-03）→ 与基线等价，非退化源。
  - #6：替身注册与否不改变 78 形态（P2-lite 上机复核）→ 对②③无已见影响。
  - #7：放宽是单向的，且是 A 档能挂新 Data 的必要条件；对基线/旧 Data 行为无收窄 → 不产生新失败。
  - #11 新 Data：**未排除，首要嫌疑**。机制：主线内核 Data 校验期望旧布局（7420 MiB 偏移 / ≤2 GiB 量级 / 旧卷 UUID），新 9745 MiB 偏移 19.87 GiB 种子被 `-EINVAL` 拒——A1 已实证主线镜像在新 Data 上必死（D-09）。注意：A 档在同一新 Data 上**能挂**（`dw=20354 dm=1`）却仍无 UI → A 档的无 UI 可能另有独立根因。
  - ①A 档打包链（`./unixnu payload` vs `package-textonly.py`，ramdisk/ADT/trustcache 字节级差异）：**未排除，次要嫌疑**；未经字节级审计。A1 在 Data 自检即 panic，未能区分此项。
- **USB 专项（五问）**：
  1. **是否编进镜像**：是，条件仅在板级配置——`0300-k60-usblog-ep0.patch` 挂 `bsd/conf/files`；文件体 `#if defined(ARM64_BOARD_CONFIG_PONG)`（`k60_usblog.c:35`，本构建恒真）。二进制证据：全部 A 档产物含 28 处 `K60 USBLOG` 字符串 + `k60_usblog_init` 符号（boot-a-usblog2/control、payload-argfix/argfix2/20261103/0303/0304/0305 逐一 grep）；**基线快照 `302a001b…` 为 0 处**（主线树从未有该文件）。
  2. **是否执行**：调用点无条件（`arm_init.c:672-677`、`bsd_init.c:1318-1325`），但函数自门控——`k60_usblog_arg()`（`k60_usblog.c:102-110`）无 boot-arg 返回 0 → init 于 `:167-170`、start 于 `:514-517` 立即返回，**零寄存器访问**。boot-arg 二进制证据：`k60_usblog=2` 仅出现在 `payload-a-usblog2.img`（1 处）；control/argfix/argfix2/0305 均为 0 处。
  3. **时机**：arm_init（线程子系统之前）与 bsd_init 尾部——都在显示服务/backboardd 之前；若激活（≥1）确实能挡住 UI，但仅在 `=2` 的 usblog2 一轮发生（DMA→SMMU stream 0 fault→SoC 复位，~35 s，I-20261103-04）。
  4. **各 boot 镜像含它与否**：基线（302a001b/6153c2aa）= 无此代码；A 档全部 = 含代码、仅 usblog2 带 arg。
  5. **判定**：**usblog 不是「跑不到进度条」的元凶**。佐证：argfix→0305 各轮分钟级存活（KX! 至 300、心跳 t=135+）无 35 s 复位；唯一 usblog 归因失败是 usblog2（I-20261103-04）。
- **因果结论**：
  - **已证实**：基线后没有任何一条改动触碰显示/spawn 功能路径；基线镜像在新 Data 上必死于 Data 自检（A1）。
  - **推断（待 A2）**：UI 消失元凶 = 今晨新 20 GiB Data（环境）；A 档在旧 Data 复测前，打包链嫌疑保留。
- **验证路径**：A2＝写回 `archive/unixnu-rollback-20261103-0330/rollback-0-0x24FB00000.bin`（sha `fca1ffaa…`）恢复旧 Data → 同一 `302a001b…` 重 boot：**预期 K60SELF 通过 + 进度条/backboardd 回归**→坐实环境；随后以 A 档最新镜像（0305 `bb0498dd…`）在旧 Data 复测：仍无 UI → 打包链升首要嫌疑；有 UI → 两线同因（Data）。
- **回滚方式**：本条无代码改动；A2 本身即 Data 回滚。
- **相关文件**：`candidates/4g-quiet*/build-verification.json`、`logs/boot-attempt-20261102-200610.log`、`usb-a-stage/stage-src/bsd/dev/k60_usblog.c`、D-2026-11-03-09、ISSUES I-20261103-04/07。
- **附：读数自查（违反 §7 一致性约束，只列不改，标「需重核」）**：
  1. `abn=302`（0304 轮 t=135 行初读）——违反易混对 `3↔8`；用户已核真值 **382**。凡归档引用 302 处 → 需重核。
  2. `KE 38`「FDR_Loader 畸形路径」——挖孔截断误读，已作废（P-08）。
  3. A1 panic 屏摄：mutex 地址折行后 17 位 hex（超 64 位宽）、`panic_caller` 跨行折行 → **位数不确定**；`ro_size=16666`（末位 6，落 `5↔6` 对）、`Bytes Traced 6448 / Uncompressed 19312`（单点）→ 屏摄读数、低置信；D-09 引用处需带此标注。`sig=43474244` 待与源码常量交叉（可升级）。
  4. 0303 三张（`7A0F17BE…`/`75073806…`/`8864CC0C…`）与 0304（`5940A4EC…`）心跳行各字段初读未做相邻行差分 → 末位落易混对的单点值 → 需重核（用户已核 `t=135 abn=382`、`KXP 24` 按 §7-7 优先，不重核）。
  5. 11-02 20:03 轮 `backboardd 首帧 1440x3200` 无照片存档（D-2026-11-02-06 明记）→ 维持「文字转述」证据级，不升格。

---

## D-2026-11-03-09 A1 结果：归档主线镜像（302a001b）在新 Data 环境上 K60SELF panic（`dataerr=-22 stage=0`）

- **日期**：2026-11-03
- **背景**：线 A 二分第一步——boot 归档主线「进度条版」到当前设备（新 20 GiB Data）以分辨「构建链 vs 环境」。
- **证据**：
  - 镜像核对：`candidates/4g-quiet/boot-ios16-4g-quiet.img` 实读 sha=`e5171421…`（已被 4.75 GiB 内存阶梯重打包，非 `6153c2aa…`）；改用快照 `bootimg/boot-4g-quiet-snapshot.img`（sha 回读 `302A001B48FC…` = 原始 20:03 版）；
  - boot：11:51:37 fastboot OKAY，EXIT=0；随后整机停于 panic stall；
  - panic 原文（`evidence/screen-4g-quiet-a1-panic-20261103.png` sha `54B80ECC…`）：`panic(cpu 3): K60SELF novar ro_base=… sig=43474244 ro_start=0 ro_size=16666 var_err=0 datastage=0 dataerr=-22 @kern_exec.c:8019`，嵌套 `lock_mtx.c:194` ×5 → stall；
  - 代码定位：主线 [kern_exec.c:8099-8131](file://wsl.localhost/Ubuntu-24.04/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/bsd/kern/kern_exec.c)——`XNU_PONG_RAMOOPS_CONSOLE` 自检：`k60_data_attempt && native_owner_data_status != 0` 即 panic（故意设计，报告 Data 挂载失败 + ramoops sig）。
- **决定（定性，待用户确认）**：判 A1 的 **(b) 环境分支**——镜像本身健康（昨日同设备到 backboardd），主线内核拒绝今晨替换的新 Data 窗口（`-EINVAL` stage 0）；A 档内核在同一新 Data 上却能挂（`dw=20354 dm=1`）——两路 Data 校验存在行为差异，待查。A2 方案：写回 `archive/unixnu-rollback-20261103-0330/rollback-0-0x24FB00000.bin`（sha `fca1ffaa…`）恢复旧 Data 后同镜像重 boot，预期进度条回归。
- **回滚方式**：无写入、无 flash；设备停在 panic stall，需物理电源键恢复。
- **相关文件**：`bootimg/boot-4g-quiet-snapshot.img`、`evidence/screen-4g-quiet-a1-panic-20261103.png`、ISSUES I-20261103-05

---

## D-2026-11-03-08 78 = xpcproxy posix_spawn 激活后属性段 EACCES（`ler=13 lw=spawn site=1`，用户屏上直读）

- **日期**：2026-11-03
- **背景**：0304（`ler/lw`）+ 0305（`site=`）两轮纯观测。0305 于 10:47:22 boot（sha `bb0498dd…`、payload `f7bb2e43…`、内嵌内核 `17992331…`），EXIT=0。
- **证据**：0304 屏摄（`evidence/screen-0304-heartbeat-20261103.jpg` sha `5940A4EC…`）：`KX? #200/#400 … execerr=13 where=spawn path=/usr/libexec/xpcproxy`、心跳全行 `ler=13 lw=spawn`、`kxq==abn`（t=135 行 abn=382 已经用户 2026-11-03 核对；KE 38 行作废）；0305 屏上用户直读 **`site=1`**（一致、非散点）。
- **决定（定性）**：78 = launchd 对 xpcproxy 的 posix_spawn 在**激活成功之后、属性段（px_sa block, kern_exec.c L4366-4482）之内**返回 EACCES(13) → 汇聚 `bad_px_sa:`（L4475, site=1）→ spawn 失败。锁定链：`KX? comm=xpcproxy` ⇒ p 已被 `proc_exec_switch_task`（L4350）换成子进程 ⇒ 失败必在激活后；`kxq≈abn`（非 2×）⇒ exec_activate_image 本体没失败。段内 EACCES 候选经签名排除（setpgid 自 pid 不查 / setsid 只 EPERM / setsigvec 只 EINVAL）后剩 `proc_set_task_ruse_cpu`（L4459）与段内 MAC 钩子两个候选；方法学记录：site=1 标签在标签级有 fall-through 残留歧义，下一轮细化到 goto 级（site=10..14 + psa_flags 打印）。
- **验证方式**：等 0306（goto 级 site + 属性面打印）一屏定点。
- **回滚方式**：纯观测补丁，series 移除即可；无行为改动。
- **相关文件**：`kern_exec.c`（0304/0305）、`kern_prot.c:596`（setpgid EACCES 语义，已排除本流程命中）

---

## D-2026-11-03-07 0303 心跳读数：Data 20 GiB 认领成功（已验证）；「78 未到 exec」结论被 `kxq==abn` 推翻

- **日期**：2026-11-03
- **背景**：0303 上机（09:50:59），心跳首现。两张关键照片（`evidence/0303-screen-3-IMG_0187.JPG` sha `7A0F17BE…`、`0303-screen-1-IMG_0188.JPG` sha `75073806…`）。
- **证据与结论**：
  1. **Data 20 GiB 认领+挂载成功（已验证，关闭）**：`K60HB t=30 … dw=20354 dm=1`（自首行起每行如此）、`handle_mount:765: disk5s1 … block count: 5210112`（×4096 ≈ 20354 MiB）、`K60DATA mounted ro=0 fstype=apfs`、`mount returned error=0 result=0 rw=1`；
  2. **「78 = 用户态 EX_CONFIG、未到 exec」（D-2026-11-03-06 的定性）已推翻**：`kxq` 在 12 个采样点与 `abn` **逐点相等**（93/153/237/298/382/442/525/586/670/730/797/873，t=135 行 abn=382 已由用户核实）⇒ 每次 78 恰好伴随一次 exec/spawn 失败调用。0302 轮「整屏零 KX?」的真实原因是**首见去重 + 屏不可滚动**，首见行被冲掉而非没有发生；
  3. **失败点定位在「KE 存路径之前」**：`KXP 76 /usr/libexec/xpcproxy`——78 进程的 pid→path 未被 job 路径覆盖 ⇒ 失败在 `execargs_alloc`/`exec_save_path`/spawn-attr 阶段，不是 namei/mach-o；
  4. 心跳机制验证通过：15 s 固定出现、`dw/dm` 语义分离正确、风暴速率 ~4.1 次/s 稳定；`remoted`/`usermanagerd` 等部分 job 存活（spawn 非全灭）。
- **决定**：放行 0304（纯观测 ~12 行）：`KX?` 改「首见 + 每 200 次补打（带累计 #n、path 恒打、空则 `path=-`）」；`K60HB` 加 `ler=`（最近 execerr，未失败显 `-`）与 `lw=`（exec|spawn|-）；下一论据 `execerr` 值直接定层（EFAULT→坏指针/配置未得、ENOENT→路径层、spawn→属性层）。
- **验证方式**：0304 构建 0 error、标记串 `KX? #%u`/`ler=%s lw=%s` 各 1 命中；10:15:25 下发 EXIT=0。
- **回滚方式**：series 移除 0304；无 flash。
- **相关文件**：`kern_exec.c`（0304 全部改动）

---

## D-2026-11-03-06 定性「78 = 用户态 EX_CONFIG，未到 exec」+ 0303 周期心跳

- **日期**：2026-11-03
- **背景**：0302 上机后整屏零 `KX?`（用户确认），而风暴持续。需要区分「插桩失效」与「78 根本不过 kern_exec」。
- **证据**：`KX?`/`KXP`/`KX#` 标记串在 kernel.macho 与 payload 内嵌 kernel 各 1 命中；`bad_notrans` 是 `exec_activate_image()` 所有失败出口的唯一汇聚点（execargs_alloc/exec_save_path/namei/权限/vn_rdwr/imgact 全部 `goto bad*`，无遗漏）；同系列 `KX#` 在屏持续滚动 → printf 链路正常。**零 `KX?` ⇒ kernel exec 层无失败 ⇒ 78 由 xpcproxy 在 execve 之前的用户态配置阶段决定（EX_CONFIG 语义吻合）**。
- **决定**：
  1. 定性：78 = 用户态 EX_CONFIG（待屏上 `kxp=0` 最终坐实——pid→path 表只在 exec 入口写入，78 的 pid 若无 KXP 即未达 exec）；
  2. 0303 补丁（纯观测，~60 行）：`K60HB` 每 15 s 固定打 `K60HB t=.. abn=.. xp=.. lag=.. mse=.. kxq=.. kxp=.. dw=.. dm=..`；`dw` 在 L7512 等三处 size 校验**之前**记录原始窗口字节（未认领也可见），`dm` 在 mount 成功处置 1（两量语义分离）；心跳双保险启动（Data 挂载路径 L7509 + kern_exit 首次异常退出 lazy，atomic cmpxchg 一次性）；
  3. 屏不可滚动 ⇒ 一次性打印均不可靠，此后诊断一律走周期自报。
- **产物**：内核 `d943cbb4…`（前 `fe85c4e4…`）；payload 内嵌 `158d1b99…`；boot `boot-ios16-4g-quiet-0303.img`（sha `73a0ad0c…`，payload `4a425d3d…`）；args 与 argfix 逐字一致。
- **验证方式**：构建 0 error；`K60HB` 串 2 命中、`KX?` 1 命中；09:50:59 下发 EXIT=0，等屏摄。
- **回滚方式**：series 移除 0303；无 flash、无行为路径改动。
- **相关文件**：`kern_exec.c`（globals/heartbeat/datawin/datamnt）、`kern_exit.c`（storm 表文件级 + k60_storm_count + kxp 计数 + lazy 启动）

---

## D-2026-11-03-05 一次构建三变量：Data 2 GiB 上限抬高 + execerr 打印 + KX! pid→路径（0302 补丁）

- **日期**：2026-11-03
- **背景**：Data 窗已写 19.87 GiB（D-2026-11-03-04），需内核放宽上限认领；`exit=78` 根因未定位，需 exec 错误码与「哪些服务在失败」两个观测手段。三者为同轮判决性实验（上限是功能、后两者是纯打印、互不交互），合并一次重编节省上机轮次；边界：打印改动不改任何行为路径。
- **证据**：`kern_exec.c` L7437/L7447/L7451 三处 `0x80000000` 上限（Data 挂载验证）；exec 失败汇聚点 `bad:`/`bad_notrans:`（L2351-2354）与 posix_spawn `bad:`（L4327）；KE 哈希块（L2185）只存路径不存 pid 映射。
- **决定**（补丁 `0302-data-cap-execerr-kxp.patch`，三个独立 hunk）：
  1. 三处上限 `0x80000000`→`0x600000000`（24 GiB），保留 `!size` 与 4K 对齐检查；
  2. exec 失败在 `bad_notrans`（where=exec，覆盖 namei/权限/mach-o 激活）与 posix_spawn `bad:`（where=spawn，spawn-attr 层）打 `KX? <pid> <comm> execerr=<err> where=<..> path=<..>`，(comm,where,err) 8 槽首见去重、只失败路径打印；
  3. 滚动 128 槽 pid→path 表（每次 exec 记录），`KX!` 首见行后补打 `KXP <pid> <path>`。
- **产物**：源内核 `fe85c4e4…`（前 `a4a37775…`）；payload 内嵌内核 `545c157e…`；boot `candidates/4g-quiet/boot-ios16-4g-quiet-20261103.img`（sha `9478a25f…`，payload `5e6d26f0…`）；args 与 argfix 全集逐字一致。
- **验证方式**：构建 0 error；`KX?`/`KXP` 标记串各 1 命中；上机 09:14:50 EXIT=0，等屏摄判读（Data 是否认领 20354 MiB、execerr 值、KXP 路径、KX# 形态）。
- **回滚方式**：series 移除 0302 即回滚；无 flash。
- **相关文件**：`kern_exec.c`（3 hunk）、`kern_exit.c`（1 hunk）、ISSUES I-20261103-05

---

## D-2026-11-03-04 Data 窗口写入 20 GiB（偏移 9745/`0x261100000`）+ 清单重写（含事故与恢复）

- **日期**：2026-11-03
- **背景**：P1（D-2026-11-03-02）后需要把 19.87 GiB Data 镜像（sha `adbbf0dd…`）写入 unixnu 分区并更新 SHNGROOT 清单；设备 TWRP（boot 分区集成，root adbd）成为首个可靠的块级写入通道。
- **证据**：
  - TWRP 核实：`uid=0`、`unixnu -> /dev/block/sda38`（32 GiB = 34,359,738,368 B）、读速 814 MB/s、挂载表不含 sda38；
  - 回滚：`archive/unixnu-rollback-20261103-0330/`（9,928,040,448 B，sha `fca1ffaa…`，**双读一致**；OS/SystemOS 窗口 digest 重算与清单一致；ROLLBACK.json 全程登记）；
  - 事故与恢复（PITFALLS P-09）：首次写入因 seek 进制错误落到 OS 窗 0x26510000（1.19 MiB 失真字节）→ restore-seg.bin 写回 → 段 sha `5db74a2d…` 一致 → **OS digest 复验 `bc4c5670…` 与清单一致**；
  - 正式写入：seek=2494720（公式 `0x261100000/4096`，打印留证；**用户口报 2494030 为笔误，已按公式纠正并标注**）；64 MiB 探针（sha `cc6a9020…` 回读一致）→ 5 段（4×4 GiB + 4,162,846,720 B）经 adb push + 设备 dd 写入，段级传输 sha 逐段一致；
  - 终验：全窗回读 sha256 = **`adbbf0ddc4bbba0d0335ccc07eb497a826b57fc103888187f0ad0f991829da24`**（与源镜像逐字节一致）。
- **决定**：
  1. Data 落最终偏移 `0x261100000`（留 ~2.28 GiB 空档给 OS/SystemOS 扩容；驱动解析只查 bounds+重叠，空档合法）；
  2. 清单重写 = 当前 OS/SystemOS 两项原样（digest 已实）+ 新 Data 项 + `imageBytes=0x759300000` + 自校验重算 → `candidates/data-20352/shngroot-final-20261103.bin`（sha `33626441…`），**先数据后清单**，写后回读一致；
  3. 通道纪律：大二进制只走 adb push + 设备侧 dd（adb shell/exec-in stdin 实测失真，见 P-09）；
  4. 本轮不验证 XNU；**内核侧待办**：`kern_exec.c` L7437/L7447/L7451 三处 `size > UINT64_C(0x80000000)`（2 GiB）上限需放宽到 ≥20 GiB（建议 `0x600000000`=24 GiB 或直接去掉上限改查 4K 对齐），并入下一次重编（与 execerr 实验同轮）。
- **验证方式**：全部 sha256 闭环（段/窗/清单三级）；设备当前停在 TWRP，未触发 XNU。
- **回滚方式**：`archive/unixnu-rollback-20261103-0330/rollback-0-0x24FB00000.bin`（9.93 GB，sha `fca1ffaa…` 双读一致）可整体写回恢复 2026-11-03 03:28 前布局。
- **相关文件**：`candidates/data-20352/`（data-window-20354.img、shngroot-final-20261103.bin）、`archive/unixnu-rollback-20261103-0330/`、`scripts/write-data-window2.sh`（WSL `/tmp`）

---

## D-2026-11-03-03 AMFI prelink 降级（用户批准）与 v1/v2 拆分构建

- **日期**：2026-11-03（用户当日上午拍板「直接做」，随后拍板「分两版出，先出第一版」）
- **背景**：xpcproxy posix_spawn EACCES(13) 风暴；0305 boot 的 prelink 中真 AMFI（`com.apple.driver.AppleMobileFileIntegrity`）与真 sandbox（`com.apple.security.sandbox`）均为完整组件在载，exec/签名决策方是真 AMFI；pong ios16 路线以 miniamfi/minisandbox stand-in 替代（`E:\k60-work\docs\references\ADOPTION-PONG-USERLAND.md`）。
- **证据（结构性约束，干跑 `tools/dryrun-amfi-prelink.py`）**：roots 级移除对 **sandbox 有效**（无人依赖，plan 30 组件 OK）；对 **AMFI 无效**——`IOGPUFamily`/`IOHIDFamily`/`IOMobileGraphicsFamily`（均在 roots）以 OSBundleLibraries 强制拉回（共 12 家声明依赖）。故 AMFI 只能「留在 prelink + 防撞名 panic」：`libkern/amfi/amfi.c` 改 keep-first 注册（miniamfi `EARLY_BOOT/STARTUP_RANK_FIRST` 先注册，真 AMFI 后到只留日志不再 panic `interface already set`）。
- **决定**：
  1. **v1（已构建）**：只含 UFS/Data 尺寸上限三处 → `UINT64_C(0x600000000)`（kern_exec.c :7557/:7561；:7547 此前已抬）+ 树内已有的 Data 自检 panic 降级与心跳 `sf=/svm=`；**不含** AMFI 任何改动、不含 boot-args 调整（保持 `k60_sandbox=1` 原串）。`pong_init_path` hunk 为本树既有未提交改动，未被激活，予以保留登记。
  2. **v2（待 v1 验证后执行）**：profile roots 去 `com.apple.security.sandbox`（消除「Sandbox」MAC 撞名 + 移除其 `mpo_cred_label_update_execve` 拒源）+ `amfi.c` keep-first + boot-args 去 `k60_sandbox=1`、加 `amfi_get_out_of_my_way=1 pong_init_path=/private/var/pong/init epoch=<打包时刻>` + pong init（已编译签名，`E:\k60-work\deliverables\pong-init\init` sha256 `faa38544…`）写入 Data。
- **验证方式**：v1 上机判据见 `E:\k60-work\usb-a-stage\DIFF-AMFI-PRELINK.md` §6（`dm=1`/`dw=20354`/`block count 5210112`/`K60DATA mounted ro=0 rw=1`/mkdir/心跳 `sf=0 svm=0`/进度条）。
- **代价**：v1 无新增风险（纯上限值 + 注释）；v2 的 keep-first 使真 AMFI 的 `amfi` 接口被 miniamfi 抢先接管（entitlement/信任缓存回答变宽容），真 AMFI 的 MAC 策略仍在载（行为与现状一致）；`amfi_get_out_of_my_way` 与 `k60_sandbox` 在 `kern_minimac.c:386-398` 互斥，不可同给。
- **回滚方式**：boot-args 还原（恢复 `k60_sandbox=1`、去三个新 arg）即回 13:05 行为；roots 恢复 `cp E:\k60-work\archive\prelink-before-amfi-20261103\profile.toml.bak` → `profiles/os/ipados-16.6.1-20G81/profile.toml` 后重跑 `unixnu prelink payload bootimg`（纯打包，内核不必重编）；`amfi.c`/上限两处用补丁反向 apply；备份与说明见 `E:\k60-work\archive\prelink-before-amfi-20261103\README-ROLLBACK.md`。
- **相关文件**：`tools/dryrun-amfi-prelink.py`、`tools/apply-amfi-round-edits.py`、`tools/revert-amfi-for-v1.py`、`tools/edit-profile-roots.py`、`E:\k60-work\usb-a-stage\DIFF-AMFI-PRELINK.md`、`E:\k60-work\deliverables\pong-init\`

## D-2026-11-03-04 v2 Pong 用户态前置层落地（kernel/payload/Data 全链路完成，待放行上机）+ init exec 目标 mondrian 修正

- **日期**：2026-11-03（v1 上机通过后，用户放行 v2）
- **背景**：D-2026-11-03-03 的 v2 部分按原方案执行。v1 上机结论：K60SELF panic 消除、20 GiB Data 认领通过（mnt=0 ro=0 mkE=17/28 sf=0）、出帧持续、xpcproxy 78 风暴仍在（v2 要解决的问题）。
- **执行与证据**：
  1. **内核**：mfi.c keep-first（libkern/amfi/amfi.c:7-19）；心跳删 svm= 保留 sf=（kern_exec.c:7499-7504，namei 跟随挂载点导致 svm 恒 0 的语义缺陷，按用户指示删除）；miniamfi/minisandbox/pong_init_path 为树内既有件直接激活。prelink roots 去 com.apple.security.sandbox（31 roots），AMFI 保留 + keep-first。内核 macho（prelink 出）sha 73a30ea7…；payload 抽取 sha 66dcc802…。
  2. **boot-args**：去 k60_sandbox=1（kern_minimac.c:386-398 结构性互斥），加 mfi_get_out_of_my_way=1（pong ios18 build-ipados18-prelinked-boot.py:50 原文；本树 kern_minimac.c:395 + miniamfi.c:266 消费）、pong_init_path=/private/var/pong/init（kern_exec.c:8209-8210 强校验唯一路径）、epoch=1793695092（打包时刻；pong userland init.c prepare_calendar 消费，来源行 UniXNU-pong/userland/init.c:292-309）。
  3. **init 修正（deviation）**：pong 原版 execve( /sbin/launchd.ios) 依赖其可写 root 上的改名文件；我方 root 为密封只读 union 无此文件，照原样 boot 必以 ENOENT 于 PID 1 exec 失败。按 pong 模型语义（自研 init → 官方 launchd）改为 exec /sbin/launchd（stock，未动），源级两行修正 + 注释；重编译（Apple ld64 工具链，未改动源码复现原版仅 LC_UUID 16 字节差）+ 自写 ad-hoc 签名器（与原签名字节级一致验证：除 UUID 与覆盖页哈希外零差异）。新 init sha256 68d9bb06fa6411b12f2bb1cd4dd7e12b9a8a46fc4ae1573aea8511633738e53e；原件 aa38544… 保留于 deliverables 作回退。
  4. **Data 侧**：/private/var/pong/init（0755 root:wheel）经 linux-apfs-rw 写入 20 GiB 窗镜像（窗 sha 81a2662f…，写入前备份 dbbf0dd… 校验一致），readback 校验 sha/mode/owner 全对；清单重生 shngroot-v2.bin（5dfc7ea7…，OS/SystemOS digest 沿用现机清单值）。设备侧四闸门写入：gate1 窗头+清单备份（E:\k60-work\archive\rollback-v2-ponginit\）、gate2 设备端 sha 一致、gate3 落点 EFI PART 签名核对、gate4a 全窗 readback sha 81a2662f… 一致、gate4b 清单 readback 5dfc7ea7… 一致。只写 unixnu 的 Data 窗与清单块，未 flash、未动任何安卓分区。
- **产物**：E:\k60-work\candidates\4g-quiet\boot-ios16-4g-quiet-v2.img sha 9ae831e…（payload cf8e920…）；**未上机，等用户放行**。
- **预期（上机判据）**：Pong init: loading helper … + helper exec result=0；init 本体行（static 20G81 helper entered/HackiOS userland adapter/preparing writable Data seed/ar.skel unavailable（root 无 /pong/etc，预期内）/calendar epoch=1793695092 result=0/boot view SKIP/UI compatibility library absent; SKIP/exec original /sbin/launchd）；miniamfi/minisandbox 承接后 xpcproxy **78 风暴应消失**（KX?/bad 行终止或改码）；AppleMobileFileIntegrity interface already set; keeping first registration 一行（真 AMFI 后到不 panic）。
- **回滚**：boot-args 还原（恢复 k60_sandbox=1、去三新 arg）→ 重打 payload 即回 v1 行为；roots 用 rchive/prelink-before-amfi-20261103/profile.toml.bak 还原；Data 用 data-window-20354-pre-ponginit-backup.img（sha dbbf0dd…）按同一四闸门写回 + 旧清单（rchive/unixnu-rollback-20261103-0330 或 rollback 目录 rb-manifest.bin）；init 回退直接使用原件 aa38544…。
- **相关文件**：	ools/build-v2-round.sh、	ools/package-v2.py、E:\k60-work\deliverables\pong-init\（init-v2 + init.c.v2-mondrian-src）、E:\k60-work\candidates\data-20352\（镜像/备份/清单）、E:\k60-work\logs\{kernel,payload,package}-v2.log、提交 cafab71（依赖恢复）。

## D-2026-11-04-03 init 改由 apfs.ko 正常分配，后续更新走已分配 extent 内同长原地覆盖

- **背景**：`/pong/init` 自 11-03 起用「手工 dd 写 9 块到 extent `(0,36864,6135)`」放入 inode 216，该 extent 未经正常 APFS 分配路径、spaceman 位图中块 6135-6143 为 free。pong 种子注入轮实证：apfs.ko `cp -a` 复用 inode 216 把 extent 改写指向 var.skel，init 被覆盖丢失（PITFALLS 第 24 条、I-20261104-02）。
- **决定（用户拍板方向 A）**：init 与 pong 种子**同走 apfs.ko 正常分配一条路**——放弃「手工 extent」通道，rm 手工 extent 文件后用 `cp` 正常写入，让 init 的 extent 进入 spaceman 记账。20354 工作副本上 init-v6 新 extent = `(0,36864,6144)`，分配探测（probe 块 6159）证实不与 init 重叠、不回落 6135-6143。
- **后续 init 更新规则**：init 物理块已由 apfs.ko 分配（6144 起）后，**后续版本更新走「已分配 extent 内同长原地覆盖」**——不再 rm/cp（避免 extent 重新分配），也不再引入任何新的手工 extent。同长覆盖才保证 extent 不变、块号稳定。
- **配套约束**：① 任何文件写入前必须确认它与同卷其它写入走**同一条分配路径**（绝不混用手工 extent 与 apfs.ko）；② init 块号从 6135 变 6144，依赖固定物理块号的外部假设（pong_init_path 内核钩子若按物理地址定位 init）需在部署前重新核对；③ 设备侧在迁移完成前，旧的常驻覆盖风险（I-20261104-02）一直存在。
- **相关**：PITFALLS 第 24/25 条、I-20261104-02、HANDOFF「不要重复尝试」新增两条。
