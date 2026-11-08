# K60 iOS 移植 — 问题与踩坑记录（ISSUES）

> **用途**：问题台账——**「现在卡在哪 / 什么还没解」的唯一权威源（SSOT）**。
> **谁该读**：新 agent 进场必读三份之一；要知道当前阻塞点先看「未解决」区。
> **边界**：已拍板的方向归 DECISIONS.md；防复发判定归 PITFALLS*.md。引用结论写 I-编号。
> 字段固定：现象 / 证据 / 根因 / 修复 / 验证 / 影响面 / 遗留风险。
> **未解决在前，已解决在后（各自时间倒序）。** 问题一解决就追加，不等收尾。
> 条目编号：I-YYYYMMDD-NN。无实物证据的一律标「待验证」。

---

## 未解决

### I-20261104-09 cdc3 上机零 `K60 USBLOG:` 行：worker 执行到哪一站不可见（arg/hook 已实证在位，待 E-worker-state 周期状态行实验分流）

- **日期**：2026-11-04 晚
- **现象**：`boot-usb-cdc3-20261104.img` 上机越过 `:921`（B 决策生效）、推进到 init 四条 SKIP；尾帧零 `K60 USBLOG:` 行；宿主 120 s 无新 COM 口（`VID_1209` 未枚举）。
- **已实证排除**：挂接点（`arm_init.c:675-676`、`bsd_init.c:1322-1323`）在且位置正确；符号实体（`_k60_usblog_init/_start/_mode`）在 unstripped；`conf/files` 编入；arg 在镜像 cmdline；`PE_parse_boot_argn` 机制在调用点可用；编译门宏共用且已证生效。详见 `references/USBM-LOG-CHANNEL-AUDIT.md` §18。
- **未决**：worker 到底跑到哪一站——**「尾帧无行」按坑表 #48（滚屏）与 I-20261104-07（console 静默死亡）都不能证明「没跑」**；DarwinBoot `CommandLine[1024]` 不触顶使 arg 截断可能性较低，但「arg 实际送达」离线不可证。
- **下一步**：E-worker-state 实验（worker 入口行 + poll 循环 ~2 s 周期 `st=` 状态行，净增 ≤6 行，一次 boot 一个变量）——帧内高密度留痕直接读出停在 waiting-ufs / plan / configure / soft-reset / endpoints / qscratch / running 哪一站（审计 §18.3，**待用户拍板**）。

### I-20261104-08 cdc2 复发静态 trust cache 装载 panic（`:921`）——根因已定位：v4「B 决策」未入 series，新鲜 clone 不携带

- **现象**（2026-11-04 晚，用户核对屏摄读数）：`boot-usb-cdc2-20261104.img`（sha `5606aabd…`）boot 屏两行：
  1. `Attempt to take mutex 0xfffffff007ad3ac0 with preemption disabled (1) @lock_mtx.c:194`（**警告，非死因**）；
  2. `panic(cpu 0 caller 0xfffffff007772940): failed to load static trust cache module: 0 @kern_trustcache.c:921`（**真 panic**）。
- **根因**（文档+实测级）：cdc2 = 新鲜 clone 主线 `3c1bea3` + 0300 + 0301–0305 探针；`3c1bea3` 的 repo 真值 = `CONFIG_XNU_NATIVE_TRUST_CACHE=y`、`CONFIG_XNU_TRUST_CACHE_RUNTIME=y`、`board.toml trust_cache_sha256=["344ae644…"]`（`git show` 实测），miniamfi = pong 原文 `kTCReturnUnsupported`；而 v5 不 panic 靠的是 **v4「B 决策」**（摘掉整条 tc 路径，D-2026-11-04-04），该决策只存于 `E:\k60-work\diffs\v4-baseline-*.patch` + 构建树，**未入 series/未入库**，新鲜 clone 天然丢失。「0301–0305 = v5 事实补丁面」口径错误（INDEX §7 11-04 cdc2 条，已更正）。
- **离线实证**（不需上机）：`grep -a -c trust_cache_init`：cdc2 boot img=1、v5 boot img=0（该串在 `startup.c:742` 的 `#if … XNU_NATIVE_TRUST_CACHE` 块内，是有无该路径的编译期指纹）。
- **修复**：cdc3 = cdc2 构建面 + `diffs/v4-baseline-config.patch` + `v4-baseline-miniamfi-revert.patch`（其余不动）；根治 = 两件入 series（待拍板，D-2026-11-04-04 ③）。
- **最小验证判据表**：

| # | 判据 | 通过形态 | 证据等级 |
|---|---|---|---|
| 1 | 构建配置（离线） | 构建树 defconfig `TRUST_CACHE=n/n`；board.toml `trust_cache_sha256=[]` | 实测（读文件） |
| 2 | payload（离线） | `payload.json` 无 `trust_cache_sha256` 非空值；Payloads/ 内**无** `kernel.macho.trustcache` | 实测（mcopy/mdir） |
| 3 | boot img 指纹（离线） | `grep -a -c trust_cache_init <img>` == **0** | 实测（本轮已建基准：v5=0/cdc2=1） |
| 4 | 上机 | 无 `failed to load static trust cache module` panic；进度 ≥ v5 阶段 | 屏摄 |
| 5 | 若 1–3 全过仍 panic `:921` | 补丁没作用到实际构建树 → 回查构建树 `startup.c` 块与 defconfig 真值 | — |

- **mutex 行归属**：与 panic 同屏但非死因（真 panic 在其后）；`0xfffffff007ad3ac0` 经 USB 线符号化 = `_vm_page_locks+0x80` 既有打印路径级联（伴生噪声，审计 §15），不阻塞本修复。
- **影响面**：USB 通道第二轮上机（HANDOFF §2）；其余线无涉。
- **遗留风险**：v4 两件一日不入库，任何新鲜 clone 构建都会复发（第 47 条）。

### I-20261104-07 屏幕 console 静默死亡（显示侧丢字；写路径无阻塞，内核日志在 ramoops 门前进环）

- **症状**：boot 中段屏幕停更（v9alias 停在 `write-check done`、v6/v7probe 停在 4 条 SKIP，**停止点逐版漂移**），设备随后重启回 Android；无 panic 屏。
- **已证事实**：
  - `/pong/status.txt` 39 B token 全链（`A0…D2…E1`）⇒ init 跑完并 exec launchd（I-20261104-06）⇒ **所有 printf 都返回了**，写路径**无阻塞**（vcputc_lock 死锁、ramoops 写阻塞均据此排除）。
  - launchd 痕迹：`/codes`、`/containers/{Bundle,Data,Shared,Temp}`、`/installd`、`/keybags`、`/db/com.apple.xpc.launchd` 的 mtime 均为 **epoch+35/36s**（时钟未校准段，早于 init trace 建 status.txt 的 44s）⇒ **launchd 起到 installd 层**（T1/T2 任务判定）。
  - T1/T2 快照（间隔约 50 min，Android 中）：头区（sha `a1ce6709…`）与尾区（sha `73324ee1…`）逐字节一致 ⇒ 窗口内卷**静态**（Android 不写 sda38；但此结果**不能**否定 13:56 boot 内 launchd 动过——彼时 iOS 已退出）。
- **链路（源码走读，progress-bar-20261102 树）**：`cnwrite`（bsd/dev/arm/cons.c:76）→ tty → `kmstart`（bsd/dev/arm/km.c:299）→ `kmoutput`（:347）→ `kmputc`（:272，**G1 门** `!disableConsoleOutput && initialized` :275）→ `console_write_char`（serial_console.c:612）→ `console_write`（:517，**先写 ramoops :520**，再走 :528 直写/环形缓冲；**G2 门** `console_io_allowed` :542 → arm64 interrupt-disabled 直接 **panic** :161-175）→ `_cnputs`（:269，**G3 门** `disableConsoleOutput` :274）→ `_cnputc`（:240）→ cons_ops → `vcputc_options`（video_console.c:1239，**G4 门** `gc_initialized && gc_enabled` :1241）→ `gc_putchar` → 帧缓冲。
- **静默门与开关者**：`disableConsoleOutput` 置位 = video_console.c:362（`gc_enable(FALSE)`）、:2800（`gc_pause(TRUE)`），清零 = :453/:2912/arm_init.c:723；`gc_enabled` 置/清 = :364/:452/:2801。驱动 op：`kPEAcquireScreen`(:2997-3025)/`kPEDisableScreen`(:3027-3031)/`kPEReleaseScreen`(:3059-3062)。**注意**：ARM 侧**未发现** `kPEDisableScreen`/`kPEReleaseScreen` 的实际调用者（IOPlatformExpert.cpp:385-389 已注释）；`-v` 文本路径（pexpert/arm/pe_init.c:542-558）下 acquire 后 console 是 ENABLED——**「被显示接管关闭」目前缺触发源，待查**。
- **三处断点候选（按可能性）**：
  1. **渲染到面板不再扫描的内存**（映射/滚动区状态错乱）：video_console.c:2956-2967（`pmap_remove` 旧帧缓冲映射、`lastVideoVirt` 重映射；`kPEBaseAddressChange` 在 ARM 无调用者）、`gc_scroll_up`（:1114，触发点 :644/:899/:928）、`vc_paint_char`——内核照常画、画进不可见区域；进程安全、停止点随打印量漂移，**与现场吻合最好**。
  2. **disableConsoleOutput/gc_enabled 被关**（门族如上）——机制存在但**触发源未明**（待查：谁发 disable/release op；IOPM/IODisplayWrangler 电源回调 IOPMrootDomain.cpp:5924/:7190 仅电源管理）。
  3. **console_io_allowed 的 arm64 panic 分支**（serial_console.c:161-175）——interrupt-disabled 打印 → panic（可能解释**设备为何重启回 Android**；控制台已死时 panic 屏同样不可见）；与「静默」是并列事件，非同一事件。
  - **排除**：`vcputc_lock` 死锁（:161；持锁挂会阻塞写者 → 与 E1 矛盾）、`pong_ramoops_console_write` 阻塞（arm_init.c:117-173 无阻塞原语，busy 仅丢字节 :121）、`gc_scroll_up` data abort（会 panic）。
- **关键推论（环形区）**：内核 printf 路径（osfmk/kern/printf.c:849/863/915 → `console_write_char` → `console_write:517` → **ramoops :520**）在任何显示门**之前**写环形区 ⇒ **屏幕死后内核日志极可能仍进环**；init 用户态打印过 G1（kmputc:275），`disableConsoleOutput` 后**不进环**。区分二者即定「显示死」vs「写路径死」。
- **区分实验（设计，不上机）**：
  - 读环通道（按工作量）：① 内核 sysctl 导出（~30 行；复用现成 accessor arm_init.c:175-191 `pong_ramoops_debug_base/start/size`，读头+尾 N 字节，**不碰写路径**）；② CONSOLE-FULL-CAPTURE 的 drainer（`drainer-for-v8.patch` 草稿）：内核线程周期把环增量追加 `/private/var/pong/dbc.log`（限容轮转），之后任意盘侧块读（sidecar 流程）即可；③ TWRP `/dev/mem`——**不可用**（PITFALLS 16）。
  - **init 内读环（用户点名评估）**：**不可行**——init 是用户态进程，无 phys 通道（无 /dev/mem、无 sysctl 暴露环形区）；只能内核侧导出（①或②）。最小改动选 ②（不依赖任何用户态存活）。
  - 判定规则：屏幕死亡点之后环尾若有**内核**新行（与 init trace token 停止点对表）⇒ 显示侧死坐实，排水器升唯一通道；若环同停 ⇒ 查 G1/`console_suspend`（serial_console.c:151/:482；调用者 IOCPU.cpp:280、AppleARMSMP.cpp:468）。
- **影响**：修好前**屏摄仅作辅助**（PITFALLS 44）；一切 boot 判读走盘侧通道。

**分工（2026-11-04 用户拍板）**：
- **当前关键路径 = 观测通道**（USB 日志通道上机验证 → console 排水器 drainer）——这是唯一阻塞项；本条所列「读环/区分实验」沿该路径推进。
- **不在当前关键路径（另开平行线）**：显示侧根因修复（断点候选 1 的帧缓冲映射重建/滚屏区错乱、候选 2 的 disable 触发源追查）——修好前屏摄只作辅助，**不修显示不阻塞主线**；主线判读一律盘侧（`references/BOOT-PROGRESS-MARKERS.md`）。
- **init 禁改**：尺寸硬上限 35,160 B（PITFALLS 46），v10guard 已 34,880 B（余量 280 B）；停止在 init 上加任何探针（链路已证全通，I-20261104-06）。

**显示交接（2026-11-04 增补，新现场事实吸收）**：
- **新现场事实（用户确认）**：屏**停在最后一帧控制台文字**（非黑屏非白屏），**无苹果标、无进度条**——内核控制台仍持有帧缓冲，画面不再刷新；与盘侧「launchd/installd/SpringBoard/Setup 均运行时新写」**一致且不矛盾：系统在跑，显示没交出去**。
- **交接链路（源码走读）**：iOS 用户态画面（backboardd/SpringBoard → IOSurface → `IOMobileFramebufferUserClient` → swap）到达显示驱动时，在 [MiniIOMobileFramebuffer.cpp:1008-1012](file:///E:/k60-work/git/progress-bar-20261102/iokit/Kernel/MiniIOMobileFramebuffer.cpp#L1008-L1012) 触发**唯一交接点**：`fGraphics=true` + `PE_initialize_console(NULL, kPEGraphicsMode)` + `drawLayer(...)`——首帧后内核文字让位、UI 上屏。
- **`k60_textonly` 作用点（实测）**：定义于 [MiniIOMobileFramebuffer.cpp:138](file:///E:/k60-work/git/progress-bar-20261102/iokit/Kernel/MiniIOMobileFramebuffer.cpp#L138)（`TUNABLE(uint32_t, gK60TextOnly, "k60_textonly", 0)`，默认 0）；拦截于 [:999-1007](file:///E:/k60-work/git/progress-bar-20261102/iokit/Kernel/MiniIOMobileFramebuffer.cpp#L999-L1007)——`if (gK60TextOnly != 0) { continue; }`：每个 UI 帧被跳过（只计数不绘制），`fGraphics` 永不置位 ⇒ **交接永不发生，内核文本独占面板**。在役 cmdline 实证含 `-v … k60_textonly=1 …`（[4g-quiet/extracted/unixnu.toml:12](file:///E:/k60-work/candidates/4g-quiet/extracted/unixnu.toml#L12)）。
- **「无苹果标/进度条」归因**：① 内核进度条/苹果标——`-v` 文本路径（pexpert/arm/pe_init.c:542-558）下 vc_progress 不激活，**本来就不画**；② 用户态画面——被 `k60_textonly=1` 拦下。两者都是**有意设置的诊断位**，与「停在最后一帧文字」完全互洽。
- **A/B 判定**：
  - **A（`k60_textonly=1` 是用户态画面的唯一拦路点）——成立（实测级）**：机制见上；显示驱动**存在**（B 不成立——MiniIOMobileFramebuffer start() :390-483 起线程/发布 UserClient/报模式，MiniIOSurface.cpp:2050 启动；软件合成 CPU 绘制，不依赖 GPU/Adreno DPU）。**修正判据措辞**：去掉后看到的**不是苹果标**（苹果标属 iBoot/内核进度 UI 阶段，-v 模式本无），而是 **SpringBoard/purplebuddy 的 UI**（Hello 屏或 Setup 完成后的画面）。
  - **B（iOS 侧显示驱动缺失）——不成立（实测级）**：驱动在内核内完整存在并运行。
  - **唯一剩余不确定项（推断级）**：SpringBoard/backboardd 是否真在提交 swap 帧——盘侧只证明其写了 prefs，未证明「提交过画面帧」。零成本旁证：屏摄里 5s 摘要区（`K60 DISPLAY: first frame presented` / swap 帧统计行，MiniIOMobileFramebuffer.cpp:1019/:1027/:1040 附近）若已有帧计数 ⇒ swap 一直在提交、只是被拦。
- **实验设计（只设计，不上机）**：变量 = 仅 `k60_textonly=1 → 0`（或删该 arg，默认即 0），其余 boot-arg 逐字不变；走现有打包流程出新 boot.img，**只 `fastboot boot` 不 flash**。判据：① 屏从文字切到图形 UI（Hello/Setup 完成画面）⇒ A 成立；② 切到 graphics 但全黑 ⇒ 交接发生但无帧提交（查 backboardd/WindowServer 存活，非驱动问题）；③ 仍停文字帧 ⇒ 交接未触发（查 UserClient/swap 路径，`fbtrace=N` 打开）。回退：只 boot，无持久影响。
- **实验已执行（2026-11-04 15:41:02）**：cmdline 补丁版 `boot-ios16-4g-quiet-v5-gfx.img`（201,883,648 B / sha `65D8F295…`；全镜像唯一字节差 = `k60_textonly=1→0`，等长单字符替换 @0x349B586，不重编、header/kernel 段/trailer 全部相同）已 `fastboot boot` 下发（OKAY 4.538s/0.152s）。**等屏摄判读**（三判据见上；原始返回与校验细节见 HISTORY-LEDGER 2026-11-04 gfx 条）。
- **gfx 判读结果（用户回报）= 判据 3：交接未触发**——屏依旧停在 Pong init 文字帧，`fGraphics` 从未置位 ⇒ **没有任何进程提交过第一帧**。转「GUI 进程在跑/崩过」盘侧取证（T3 快照，xid 15→16，sidecar 更新于 `evidence/data-live-20261104/SIDECAR.json`）。
- **盘侧 GUI 进程取证（T3，实测）**：
  - **崩溃证据全空**：`/cores` 0 项；`/mobile/Library/Logs/CrashReporter/DiagnosticLogs` 0 项（无 `.ips`/`.crash`/`.panic`）；`/log/asl`、`/log/com.apple.xpc.launchd` 0 项；`/db/diagnostics` 0 项；`/db/uuidtext` 不存在。
  - **GUI 痕迹**：`/mobile/Library/Caches` 0 项（无 SpringBoard/backboardd 缓存）；`/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}` 骨架在（epoch+35s）但**内容全空**（无 app 容器入驻）；`/tmp`、`/run` 0 项。
  - **launchd 状态**：`/db/com.apple.xpc.launchd/` 仍仅 {config（空）, disabled.plist}；**`disabled.plist`、`purplebuddy.plist`、`springboard.plist` 的 mtime 从 epoch+39s 推进到 epoch+45s**——gfx boot 内三件被**同内容重写**（新 checkpoint，数据块 4096025→4096029-31；内容逐键相同）。
- **判定（三选一定案）= ② 有启动痕迹但无崩溃记录**：SpringBoard/purplebuddy/launchd 在 gfx boot 内**重新持久化了各自状态**（证明这些进程在跑），但零崩溃报告、零帧提交 ⇒ **进程活着但没提交帧**。下一步方向：查 swap 调用方（backboardd/WindowServer 的 IOMobileFramebuffer 打开与提交路径）——盘侧对此无直接证据，候选通道 = `fbtrace=N`（MiniIOMobileFramebuffer.cpp:162 调试位）或内核日志出口（drainer/USB，见本条目「区分实验」）。**不是显示驱动问题**（驱动存在且被调通，见前 A/B 判定）。

### I-20261104-06 写盘能力验证（实读卷目录）：写盘可用已证实；「hang」叙事翻转——console 静默死亡是真故障，新前线在 launchd/console

- **任务**：重估「这个卷到底能不能写」前提——设备现读 OwnerData 卷目录项，判定 `.pong-write-check`/`status.txt`/`pong/init` 存在性（只读，未写盘未 boot）。
- **证据（全部实测；sidecar `E:\k60-work\evidence\data-live-20261104\SIDECAR.json`）**：容器头 128 MiB（skip=2494976 count=32768，sha `a1ce6709…`）+ 尾区 334 MiB（skip=7623424 count=81664，含现行 omap 根块 5128782——容器经扩容，omap 在高块，sha `73324ee1…`）dd 拉取，设备/主机双 sha 一致；稀疏装配 + **读护栏**解析（任何越出证据区的块读即报错；枚举共 83 次块读全部在界内）。
- **目录项关键事实**（live xid=15 vs 基线 xid=7；files 42 vs 37、dirs 178 vs 163、symlinks 2 vs 1）：
  - `/pong` = { `init`, **`status.txt`** }；`/pong/init` 实读 36864 B sha `ed6c3bf1…`（== Gate3 段值）、前 34880 B sha `db7e4eee…`（== init-v10guard）——「init 从 `/private/var/pong/init` 加载」在 FS 层证实。**注意**：inode.size 字段残留 35160（raw 覆写不更新 inode，PITFALLS 46）。
  - `/pong/status.txt` 39 B（uid 0 mode 644），内容 = **`A0 A1 A2 B0 B1 B4a B4e B4s C1 D1 D2 E1`**（12 token 全链，sha `b823e52c…`）——**E1 是 execve 前最后一 token：v9alias 完整跑完整个 init 并 exec 了 launchd**（A2 后无 A3/A4 = var.skel 缺席按设计早退；B4e+B4s = 第 5 条走 stock-skip；D2 = libpong-ui 缺席 SKIP）。
  - init 运行时写入全部跨重启持久：`/cores`（mode 1775 uid 0）、`/mobile/Library/CoreDuet/Knowledge`、`/mobile/Library/IdentityServices/PDS`（uid 501 mode 700）、`/db/timezone/{zoneinfo→/usr/share/zoneinfo.default, localtime→/var/db/timezone/zoneinfo/UTC}` 双链接——对照基线（均缺）证实为 init 所建。
  - `/codes`、`/containers`（uid 0，基线无，非 init 产物）——疑似 launchd 早期启动痕迹，**待查**。
  - `/.pong-write-check` 缺席——**按 `unlink` 设计本应缺席，不构成写失败证据**。
- **裁决（用户 A/B/C 框架）**：**A（修正判据版）——用户态写盘可用**：建文件（status.txt）+ 建目录（cores/CoreDuet/IdentityServices）+ 建链接（timezone）三重证据跨重启持久；`.pong-write-check` 缺席系设计使然。
- **对既有结论的冲击（三条旧条目据此关闭并移已解决区）**：
  - I-20261104-05「trace 写盘挂住」**前提错误**：status.txt 实际生成且写满 12 token；早前「零痕迹」是 strings 扫描未覆盖高块区（现行 omap/jtree 在 ~5.1M 块区）的**覆盖假象**（PITFALLS 45）。
  - I-20261104-04「第 5 条 mount 死锁」**证伪**：B4e+B4s+C1 = 第 5 条走 stock-skip、循环完整结束，mount 从未到达。
  - I-20261104-03「死点在第 5 条迭代内」**证伪**：真实进度到 D2/E1。
  - **真正故障 = 屏幕 console 静默死亡**（v9alias 屏停在 write-check done、v7probe/v6 屏停在 4 条 SKIP，而进程都跑到了 configure_ui_library 乃至 execve）——CONSOLE 调查 S2 假设（静默吞写盲跑）实锤；**「屏上最后可见行 ≠ 进程死点」**（PITFALLS 44）。
- **新前线**：(i) console 静默死亡根因与修复（gc_pause/滚动路径，CONSOLE-FULL-CAPTURE.md 排水器路线升为主线）；(ii) launchd exec 之后走到哪层（`/codes`、`/containers` 谁建的、SpringBoard 差距按 GAP-TO-SPRINGBOARD 重新对表）——**屏摄证据降级为辅助，盘痕迹升为唯一可信通道**。
- **v11markers 立项结论**：**可行**——写盘能力已证；但标记读回必须走盘侧实读而非程序自报（PITFALLS 43），且不得在嫌疑域内新增未验证写路径而不先单测（PITFALLS 41）。

### I-20261104-02 设备上 `/pong/init` 常驻覆盖风险（手工 extent 未登记分配）

- **现象**：设备 Data 卷的 `/pong/init` 随时可能被运行时 RW 分配覆盖，而覆盖前无任何征兆。
- **证据**：
  - 设备窗 `data-window-20354.img`：`/pong/init` ino=216 extent `[(0,36864,6135)]`，但该 extent 是 11-03「手工 dd 写 9 块」塞入，**未经过正常 APFS 分配路径**，spaceman 位图中块 6135-6143 为 free。
  - 对照组：11-02 cp -a 写的 36 个文件 extent 物理块 5970-6134 连续止于 6134，证实 6135 起 free（apfs.py 只读核实，无 spaceman 解析器，用「分配器连续止于 6134」+「apfs.ko 实际复用 6135」双观测互证）。
  - 复现：pong 种子注入轮在副本上 apfs.ko `cp -a` 把 var.skel 分配到块 6135，inode 216 extent 被改写为 `(0,16384,6135)`，`/pong/init` lookup 变 None——init 被吃（详见 PITFALLS 第 24 条）。
- **根因**：手工 extent 写与正常 APFS 分配是两套互不知情的记账；spaceman 不知道 6135-6143 已被 init 占用。**（2026-11-04 补：6135-6143 的 free 判定降级为「推断」**——无 spaceman 位图解析器，两条竞争假设并列：(i) 设备真把该区标为 free（则 init 随时可能被运行时 RW 覆盖）；(ii) apfs.ko 在副本上误读 spaceman 位图才复用 6135（设备实际未必如此标）。**证据倾向 (ii)**：锚点实测（PITFALLS 26）init-v6 在 LBA 2501111 完好、iOS 多次 RW 写入（6400 keybag 等）从未碰该区——若设备真标 free，运行时应早已覆盖它，故「设备标 free」存疑。本条目风险等级相应下调，但仍需在迁移到 apfs.ko 正常分配前保持关注。**）**
- **修复（已按 D-2026-11-04 方向 A 落地）**：init 改由 apfs.ko 正常分配（rm 手工 extent 文件 + cp 正常写入），20354 工作副本上 init 新 extent = `(0,36864,6144)`，分配探测（probe 块 6159）证实不重叠、不回落 6135-6143；后续 init 更新走**已分配 extent 内同长原地覆盖**，不再引入新的手工 extent。
- **验证**：副本四道门全过（apfsck rc=0；ro 抽读 init sha=init-v6 `25d23885…`、var.skel sha `2fa76a69…`；`/pong`+`/pong/etc` 全枚举无缺漏；5 个骨架文件完好）；**设备侧尚未写入（第 2 步前不碰设备）**。
- **影响面**：若设备某次开机屏上**完全无 Pong init 输出**，第一件事先核对 init 现址内容是否仍为 init（回读 sha 对 init-v6 `25d23885…`），**而不是另开排查线**——这是「开机无输出」被误判成新死点的最大来源。**核对锚点**：init 现址（手工 extent，迁移前）= 容器块 6135-6143 → 窗内块 6391-6399 → **设备 LBA 2501111-2501119**（`dd bs=4096 skip=2501111 count=9`，bare-34872 sha 应 == `25d23885…`；2026-11-04 锚点实测 MATCH，覆盖风险**尚未触发**）；迁移到 apfs.ko 正常分配后新址 = 容器块 6144-6152 → 窗内块 6400-6408 → **设备 LBA 2501120-2501128**。坐标算式见 PITFALLS 第 26 条（base=2494720，勿再加容器偏移两次）。
- **遗留风险**：设备侧在迁移到「apfs.ko 正常分配的 init」之前，该常驻风险一直存在；迁移后 init 物理块从 6135 变 6144，依赖固定块号的任何外部假设（如 pong_init_path 内核钩子按物理地址找 init）需重新核对。

### I-20261104-01 内核日志旁路（ramoops）存在但设备侧无法读取

- **现象**：XNU 冻结后想抢救内核日志，ramoops 通道在内核侧真实存在、设备侧却无任何读取手段。
- **证据**：
  - 写入侧：`osfmk/console/serial_console.c:517-575` `console_write` 逐字节先调 `pong_ramoops_console_write`（物理地址 `0xA7000000` 起 2 MiB 环形区，`DBGC` 头），再走屏幕——本项目唯一内核日志旁路。
  - 读取侧：TWRP（Fuutao 5.10.237）无 `/dev/mem`、无 `/dev/kmem`；`/proc/kcore`、`devmem`、busybox devmem 均未验证成功。
  - 失败实录（2026-11-04 06:03）：`fastboot reboot recovery` 进 TWRP 后 1 秒内查两个设备节点均 No such file or directory，随后 TWRP adb 掉线。
- **根因（结论：通道结构性不可用，非时效问题）**：ramoops 区是 DRAM 普通内存；**XNU 重启/复位后其内容在任何后续系统里都读不到——TWRP 读不到，进 Android 也读不到（用户 2026-11-04 现场确认）**。读取日志的前置动作本身就是重启，重启必清 DRAM，故本通道在我们的流程里**不存在可用窗口**；叠加 TWRP 用户态无 devmem 类接口的硬约束。
- **已失败路径清单（禁止重试）**：`/dev/mem`、`/dev/kmem`（TWRP 不存在）；`/proc/kcore`、`devmem`、busybox devmem（未验证成功）；**XNU 复位后进 Android 读取（用户现场确认读不到）**。
- **修复方向（唯一可行解法，用户原话确认：「除非打通 XNU 里的 USB 日志通道。」）**：复位前内核自己把 console 流从 USB 吐出，不依赖任何重启后的读取。已知死亡点：`k60_usblog.c` SMMU 路径——apps_smmu stream 0 无 context → TZ 强制复位（I-20261103-04）；破法已有草案（SMMU stream 0 context 设计）。**标为主线并行必需项（调试放大器）**：直接决定每轮试错信息量（现状一轮 = 一张屏摄）。（flash 持久化路线否决：需写盘能力与已发布驱动，现状不具备。）在此之前证据采集固定为屏摄（PITFALLS P-10、RECORDING-RULES §7）。
- **验证**：不适用（结论性封案，见 D-2026-11-04-01）；USB 通道打通判据 = 主机侧收到 XNU console 流。
- **影响面**：所有 XNU 冻结类问题的取证方式；排查计划里不得再出现「读 ramoops」步骤。
- **遗留风险**：USB 日志通道若确认不可行，需追加 DECISIONS 重议取证路线（屏摄保底不变）。

### I-20261103-11 `make-shngroot-manifest.py` LAYOUT 把规划尺寸当真值 → v2–v5 全系列 mount root 失败

- **现象**：v2–v5 全部 boot 三窗 `found=3 prepared=0 published=0`，v5 panic `Failed to mount root device @IOKitBSDInit.cpp:971`；v1（用 05:17 正确清单 `33626441…`）正常进 launchd。
- **证据**：`tools/make-shngroot-manifest.py` L22-26 写死 OS `4096`/6144 MiB、SystemOS `6145 MiB`/3584 MiB；设备真值 OS `0x100000`、SystemOS `0x12FE00000`（03:40 回滚清单 + `archive/rollback-v2-ponginit/rb-manifest.bin`）；17:05 生成的 `shngroot-v2.bin`（sha `5dfc7ea7…`）含错误几何，17:09 写入设备；PongUfsTransport 签名校验（OS/Data +512 `EFI PART`、SystemOS +32 `NXSB`）在错误偏移上必然失败。
- **根因**：清单生成脚本把规划布局当设备真值；正确做法的正面先例 = 凌晨 `build-manifest.py` 从设备在役清单继承 OS/SystemOS 条目（产出 `33626441…` 几何全对）。
- **修复（已定方案，待用户放行）**：以 `rb-manifest.bin`（`33626441…`）为底，仅替换 Data 条目 sha256（pong-init 镜像 `81a2662f…`，前提是该窗内容复核仍在位）并重算前 4064 字节自哈希，只重写清单块 4 KiB；脚本侧把 LAYOUT 改为从设备现清单/回滚解析并加落盘前断言（见 D-2026-11-03-18）。
- **验证**：修复后 v5 同镜像 boot 应过签名校验、发布 root 媒体、越过 `IOKitBSDInit.cpp:971`。
- **影响面**：v2 起全部主线候选镜像无法进 root；Data 窗 20 GiB 内容本身不受此 bug 影响。
- **遗留风险**：`make-shngroot-manifest.py` 的 docstring 仍自称「the K60 unixnu layout」，不改掉还会再误导。

### I-20261103-13 写盘前备份范围 < 写入范围（17:09 只备了 Data 头 + 清单）

- **现象**：17:09 v2 写盘前的回滚件只有 Data 窗头 16 MiB（`rb-head.bin`）+ 清单 4 KiB（`rb-manifest.bin`）；OS / SystemOS 窗无当轮独立备份，只能依赖 03:40 的 9.4 GiB 前段回滚。
- **证据**：`archive/rollback-v2-ponginit/ROLLBACK-METADATA.json`；对照 `archive/unixnu-rollback-20261103-0330/ROLLBACK.json`。
- **根因**：闸门设计只覆盖了「被写窗的头」而非「被写的完整范围 + 邻窗」。
- **修复**：已立硬规矩（D-2026-11-03-18）——写入前备份将被覆盖的完整范围，sha256 双读一致后放行。
- **验证**：下次写盘的 ROLLBACK 元数据中备份范围 ≥ 写入范围。
- **影响面**：回滚精度；本轮若 OS/SystemOS 真受损，恢复基准是 03:40 回滚而非当轮备份。
- **遗留风险**：无（制度已立，待执行验证）。

### I-20261103-08 `patch-sandbox-label-update.py` 缺失：payload 沙盒二进制补丁静默跳过

- **现象**：fork `scripts/unixnu/payload.py:148-153` 引用 `scripts/patch-sandbox-label-update.py`，但该脚本不存在于任何检出；`is_file()` 守护使构建不报错，**沙盒补丁（强制 `mpo_cred_label_update_execve` 返回 0）实际从未生效**。
- **证据**：`ls scripts/unixnu/patch-sandbox-label-update.py` → No such file；payload.py 提交 `066a3da` 内联注释说明意图（消除 launchd execve → SIGKILL / `OS_REASON_EXEC/EXEC_EXIT_REASON_SECURITY_POLICY`）。
- **根因**：脚本从未编写；意图由 P2-lite 调查（sandbox MAC 钩子拒 execve 假设）提出，该假设后被 sig=6/5 归因部分证伪，优先级下降。
- **修复（何时需要补）**：当 spawn EACCES（I-20261103-05，site=1）排查落到 MAC 钩子段内时，编写该工具——在 kernel.macho 中定位沙盒策略的 `mpo_cred_label_update_execve` 入口并改为 `return 0`；补写后无需改 payload.py（自动生效）。
- **影响面**：当前零影响（守护下静默跳过）；但"沙盒钩子是否拒源"这一变量在 v2 轮（D-2026-11-03-03）仍未被实验排除。

### I-20261103-09 `unixnu.lock` xnu pin `d8b80295` 身份未明，未采用

- **现象**：mondrian 工作区的 `unixnu.lock` 曾把 `[source."xnu"]` 从 `1b191cb58250d0705d8a51287127505aa4bc0789`（xnu-8796.141.3，现役构建基线）改为 `d8b80295118ef25ac3a784134bcf95cd8e88109f`。
- **证据**：`d8b80295` 在 feeds 缓存中无法定位（xnu-c465a9f8 无此对象；xnu-b7545ced 有同名前缀 commit 但身份未核实）；现役 xnu-work 与归档分支 `progress-bar-20261102` 均基于 `1b191cb`。
- **处置（2026-11-03，用户决定）**：**不提交该 pin**；提交前已把该行恢复原值 `1b191cb`（唯一允许改内容的例外），`unixnu.lock` 实际提交（`c28f5e8`）仅新增 PongUfs pin `c959284`。
- **遗留**：`d8b80295` 的来源（何时何因写入 lock）未查清；若将来 darwin24/17.7.11 线重启，需先核实其身份再决定是否采用。

### I-20261103-07 主线镜像（302a001b）在新 Data 环境 K60SELF panic：Data 挂载 -EINVAL stage 0

- **现象**：2026-11-03 11:51 boot 归档主线「进度条版」快照（sha `302A001B…`）到当前设备（新 20 GiB Data 窗 + 新清单），未跑码即 panic stall：`K60SELF novar … sig=43474244 datastage=0 dataerr=-22 @kern_exec.c:8019`，嵌套 lock_mtx 级联 → stall。
- **证据**：屏摄 `evidence/screen-4g-quiet-a1-panic-20261103.png`（sha `54B80ECC…`）；自检代码主线 kern_exec.c:8099-8131（`k60_data_attempt && native_owner_data_status != 0` 即 panic）；同设备今晨 A 档内核（argfix→0305）在**同一新 Data** 上挂载成功（`dw=20354 dm=1`、block count 5210112）。
- **根因**：未定。已知：镜像昨日同设备健康（backboardd 首帧）；新 Data 窗/清单今晨写入（D-2026-11-03-04）。差异点在主线与 A 档的 Data 校验路径（候选：窗口几何/offset（旧 7420 vs 新 9745）、APFS 卷 UUID、或主线私有校验阶段）。**推断：主线内核期望旧 Data 布局/种子**。
- **复核进展（2026-11-03，DECISIONS D-2026-11-03-10）**：基线后全部改动逐项复核——无任何一条触碰显示/spawn 功能路径（三主线诊断文件 diff 零功能；args 已对齐；`k60_usblog` 除 usblog2 外全惰性，已排除）；未排除项仅剩 ①本条（新 Data）②A 档打包链字节级差异（未审计，A2 后复测定夺）。
- **修复**：A2——回滚件 `archive/unixnu-rollback-20261103-0330/rollback-0-0x24FB00000.bin`（sha `fca1ffaa…`）写回旧 Data 后同镜像重 boot 验证；若回归则实锤环境差异，再决定主线 Data 校验是否放宽到新布局。
- **验证**：A2 后 K60SELF 通过 + 进度条出现。
- **影响面**：主线观测平台（backboardd 可达）当前不可用；线 A 二分推进。
- **遗留风险**：旧 Data 回写后，今晨新 20 GiB 布局暂时失效（可再次按 D-2026-11-03-04 重写，镜像在库）。

### I-20261103-05 A 档 argfix 内核：全部 launchd job 的 xpcproxy 以 exit=78 循环退出（屏停 KX! 300 限流）

- **现象**：P1（args 补齐）镜像 `310c25a8…` 上机：越过 vnode panic、Data/UFS/keybag 全过、`load_init_program` 拉起 launchd 后，`xpcproxy` 以 `exit=78 sig=0 ns=0 code=0x0 rf=0x0 jf=0x0` 全量循环退出（KX! 序号 269→300、pid 386→399 递增），打满 300 条限流后屏幕安静、不复位。
- **证据**：2026-11-03 用户屏摄（已核对：mkdir 全 `[17]` EEXIST、`mem=actual=managed=4096` 三数一致）；限流代码 `kern_exit.c` L1640-1643（`_Atomic k60_reason_sequence`，`k60_record <= 300` 才打印，计数不停）→「停在 300」是限流，**不是卡死**。
- **根因（最新定性，D-2026-11-03-08）**：**78 = posix_spawn 激活后属性段（px_sa block）内 EACCES(13)**。证据：`ler=13 lw=spawn`（0304 屏摄全行）、`KX? #200/#400 execerr=13 where=spawn`、0305 用户屏上直读 `site=1`（= `bad_px_sa:` 标签 kern_exec.c:4475）；`kxq==abn` 逐点相等（推翻"未到 exec"旧论）；`KX? comm=xpcproxy` 锁定失败在激活后子进程侧。候选：`proc_set_task_ruse_cpu`（L4459）或段内 MAC 钩子（setpgid/setsid/setsigvec 已按错误签名排除）；待 0306（goto 级 site=10..14 + psa_flags 打印）定点。
- **根因（Sandbox stand-in 假设已于 2026-11-03 证伪）**：P2-lite 后 `K60 SANDBOX: stand-in policy registered` 已生效（用户确认；二进制证据 `kern_minimac.o` 含 `k60_sandbox`/注册串，kernel.macho 含 `k60_sandbox`），**但 78 风暴不变**（`KX#` 直方图 xpcproxy 96→1996 持续、占比 ~99.7%，零成功启动）→ ENOPOLICY 不是根因。修正方向：均匀失败位于 spawn/exec 边界（KE 行显示 exec 尝试路径完好；无任何目标进程名进入直方图 → 目标从未替换映像存活），下一步在 `kern_exec.c` 打 exec 失败错误码（namei 后/ `bad*` 出口）定位阶段（ENOENT/EACCES/mach-o/spawn-attr）。另注：路径「畸形」线索已撤销（PITFALLS P-08 挖孔截断）。
- **修复**：P2-lite 已执行（2026-11-03，D-2026-11-03-03）：`0301-k60-sandbox-kx-histogram.patch`——`kern_minimac.c` 与主线逐字节同步（`k60_sandbox=1` 注册 stand-in）+ `kern_exit.c` 限流改首见表/KX# 直方图。镜像 `boot-ios16-4g-quiet-argfix2.img`（sha `b99064f1…`）。**0302（D-2026-11-03-05）追加观测**：exec 错误码打印（`KX? … execerr= where=exec|spawn`）+ KX! 补 `KXP <pid> <path>`（pid→path 128 槽滚动表），镜像 `boot-ios16-4g-quiet-20261103.img`（sha `9478a25f…`）；同补丁把 Data 2 GiB 上限抬到 24 GiB（认领 19.87 GiB 新窗口）。
- **验证**：P2-lite 后 78 风暴应转变形态（daemons 起跑，进入主线已知 A/B/C 形态或前进到 backboardd）；不变则证伪 Sandbox 假设，转查 plist/域配置/amfi。
- **影响面**：用户态零进展；阻塞 USB-B 档（ECM/UDP 日志流）前的环境对齐。
- **遗留风险**：`exit=78` 也可能混有少量他因 job；限流放宽（KX! 改首见+直方图）未做前无法逐服务统计。

### I-20261103-04 usblog 镜像无声复位：USB DMA 未过 apps_smmu stream 0（无 panic，SoC 级复位）

- **现象**：`boot-a-usblog2.img`（sha `47c7bcee…`，`k60_usblog=2`）三次上机同一形态：跑码 → `K60 USB: soft reset done after 1 ms; GCTL 0x00102001 DCFG 0x00480814` 为**最后一行** → 立即无声复位（无 panic 文本），~35-45 s 后进 Android。
- **证据**：2026-11-03 三次跑机 usbipd 时间线（`logs/usb-watch-20261103-012138.log`：fastboot 消失 → ~30 s 后 Android 早期 ADB 复现，全程无 `1209:0001`）；用户核对屏摄（无 QSCRATCH/VBUS 行 → 未执行到）；`k60_usblog.c` L558 之后 = L564-586（GEVNT 编程 → ep0 → `ud_start_setup()` 首次 DMA）。
- **根因（已定性强推断）**：SM8450/8475 的 USB3 DMA 走**应用侧 SMMU stream 0x0**（`sm8450.dtsi` L5483 `iommus = <&apps_smmu 0x0 0x0>`）；代码按 sweet 策略直给物理地址 `0x9xxxxxxxx`（K60 高窗），不在 ABL 遗留上下文里 → **SMMU context fault → TZ 强制整机复位**（QC 平台对未处理 SMMU 故障的标准行为，故无 panic）。对照组（control，无 USB 代码）存活 ≥4 min 证明其余路径无害。GCTL=`0x00102001`（设备模式）、DCFG=`0x00480814`（SS+地址 2，ABL fastboot 正常残留）。
- **修复**：二选一——(a) 给 USB stream 0 建 SMMU context（`ArmSmmu4K` kit 现成，PongUfs `SmmuTakeover.h` 为模板）；(b) 先跑「只到 soft reset」最小镜像（L562 后 return）坐实 L564-586。随后才是 ECM/UDP（B 档）。
- **验证**：(b) 屏上过 `soft reset done` 继续启动、~35 s 不复位即坐实；(a) 后主机 `lsusb` 见 `1209:0001`。
- **影响面**：USB 实时日志通道（I-20261102-03 的解）进度；不影响主线启动。**已排除为「进度条消失」元凶**（2026-11-03，D-2026-11-03-10）：除 usblog2（`k60_usblog=2`）外全部 boot 无此 arg、`k60_usblog.c` L167-170/L514-517 惰性返回，基线镜像（`302a001b…`）根本不含此代码（`K60 USBLOG` 字符串 0 处）。
- **遗留风险**：若 stream 0 实际被 ABL/QHEE 配置为 bypass 以外的特殊态，建 context 前还需先读 SMMU 现状（ArmSmmu4K 有 audit 能力）。

### I-20261103-02 ramoops 语义定案：可作加载器/DXE 侧取证，**不能**作 XNU 内核日志通道

- **现象**：5 GiB 轮加载器日志首段有 `RAMOOPS: sig=0x43455343 size=0x8A (no xnu log)`——ramoops 区签名非空，但无 XNU 日志内容。
- **证据**：`evidence/loader-5g-nowindow-20261103.log` L3（sha `3e85885f…`）。
- **根因（用户一手解释，2026-11-03 定案）**：该日志是 unixnu 里用 **advancedlogger** 抓的；`sig=0x43455343`（ASCII `CESC`）是 advancedlogger 的签名区，**非 XNU 写入**。ramoops 能被读到只是因为**没有重启、RAM 未掉电**；一旦 XNU 接管此通道即断，**重启后内容不保留**。
- **结论（定案）**：ramoops **不能**作为 XNU 内核日志通道，只能作加载器/DXE 侧取证；后续任何「读 ramoops 取 XNU 日志」的设想一律标注**不成立**。
- **修复**：无（语义更正）。
- **验证**：—
- **影响面**：取证通道规划（I-20261102-03 的约束不变；XNU 侧实时取证走 USB ECM 线，见 USB-LOG-CHANNEL.md）。
- **遗留风险**：无。

### I-20261103-01 5 GiB 内存窗口被加载器拒绝（NO WINDOW，单变量失败）

- **现象**：`owned_memory_size=0x140000000`（5 GiB）镜像 `fastboot boot` OKAY 但停在 unixnu 菜单，按电源键选 XNU 也不交接（用户亲述，2026-11-03 凌晨）；与 8 GiB 同形态（窗口分配失败），非内核崩溃。对照：4.5 GiB（`0x120000000`）正常起，三数 4608 一致。
- **证据**：窗口分配代码 `UniXNU-mondrian/drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c` L422-468（`AllocateWindow`：扫描 EfiConventionalMemory 的连续空闲 run，失败时菜单屏打 `NO WINDOW %lx BIG RUN %lx @ %lx` + FREE 列表）；arena 定义 `uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c` L94（`XNU High Arena` [0x900000000, +0x140000000) = 5 GiB，Conv）。
- **根因（已实测定性，2026-11-03 凌晨）**：日志实证 **arena 100% 空闲连续**——`DARWINBOOT: no window 0x140000000, biggest run 0x140000000 at 0x900000000` 与 `free 0x900000000 + 0x140000000`（`evidence/loader-5g-nowindow-20261103.log` sha `3e85885f…`），**否定"DXE 占用 arena 顶部"假设**。真正卡点是**窗口基址对齐偏移**：`DarwinBoot.c` L453 要求候选地址 = `ALIGN_VALUE(run_start, 2 MiB) + (Kernel->Base & (2 MiB−1))`；已验证可用的 4/4.5 GiB 窗口基址都是 `0x900020000`（HANDOFF §3.1）⇒ 内核映像块内偏移 = **0x20000**。arena 末端 0xA40000000 − 0x900020000 = **0x13FFFE000 < 0x140000000，恰好差 128 KiB** → 无合法候选 → NO WINDOW。即"窗口==arena 时必败，差值恒为内核基址偏移"。
- **修复**：路径 A（判据满足：BIG RUN `0x140000000` ≥ `0x130000000`）：试 `0x130000000`（4.75 GiB），窗口 [0x900020000, 0xA20020000) 完整落入 arena。路径 B（挪基址）暂不需要。
- **验证**：BIG RUN 实测值已取（原文见证据文件 L33-35/42-44 等，六次尝试全同值）。**A 轮结果（2026-11-03）：4.75 GiB 通过，判据 = 窗口被接受并成功交接 XNU**（boot 后 100 s adb/fastboot 均消失、内核接管）；mem 三数行滚出屏顶未读到（记录限制：本档不记三数验证）。本条目随 A 轮通过转为已解决——见下方已解决区副本要点。
- **影响面**：内存阶梯上限；7 GiB 复评（回 7 GiB 前须先回 stage-bar 探针）。
- **遗留风险**：无；4.5 GiB 是当前已验证上限。

### I-20261102-01 一批用户态守护进程异常退出，SpringBoard 未稳定存活（已拆 A/B/C 三子问题）

- **现象**：启动后 `abn` 持续上涨，且是**持续重启循环**，不是单次崩。
- **证据（总）**：2026-11-02 晚用户屏幕照片 `IMG_0180.JPG`（boot 镜像 `6153c2aa…` / kernel `64ae6488…`）：`K60 ex=` 已到 **1388**、`abn=` 到 **446**、free 稳定 **99k–108k 页**（约 400 MB）→ 不是内存压力；ns=2 = OS_REASON_SIGNAL；kcdata 版 STR（见 I-20261102-09）已读出每条死亡的 `sender=`/`from=`/`desc=`。
- **根因**：**未定**。按 STR 的 from/desc 字段拆成三个子问题，证据均出自 `IMG_0180.JPG`：
  - **子问题 A（哑崩组）**：`accountsd`、`dad`、`aggregated`、`ScreenTimeAgent` —— `sender == 自身 pid`、`from='<本名>'`、`sig=6` SIGABRT，**desc 恒为 `-`**（userspace 未走 abort_with_reason 附原因，属哑崩；勿误判为日志缺失，见 PITFALLS P-07）。
  - **子问题 B（exc_handler 组）**：`financiald`、`cloudd`、`chronod`、`mmaintenanced`、`mobileactivation`、`liveactivitiesd` —— `from='exc_handler'`、`sig=5` SIGTRAP，被名为 **exc_handler** 的进程发信号打死。**新线索**，单列 I-20261102-13。
  - **子问题 C（suggestd）**：持续 `exit=163 sig=0 ns=0 code=0x0`，不打 STR，与 A/B 无关，单独跟踪 I-20261102-14。
- **已排除**：内存不足（free 稳定 99k–108k 页）、Sandbox 策略缺失（D-2026-11-02-03）、显示前提（REFERENCE-WALL-AUDIT 全具备）、ADT 缺键（逐键比对无缺失）、`/private/var/containers` 树（0239 已建）。
- **修复**：无（待根因）。
- **验证**：A/B/C 拆分证据为 `IMG_0180.JPG` 逐字复核；后续验证见 I-20261102-13 / I-20261102-14。
- **影响面**：SpringBoard 及全用户态稳定性。
- **遗留风险**：参考项目（ios-sweet-k60/NOTES.md）里 `container_system_path_for_identifier` 返回 NULL → backboardd NSException 的墙体我们标 **OPEN**，是嫌疑方向之一，但无实证。

### I-20261102-13 待查：exc_handler 发 SIGTRAP 打死一批守护进程（子问题 B）

- **现象**：`financiald`、`cloudd`、`chronod`、`mmaintenanced`、`mobileactivation`、`liveactivitiesd` 的 STR 行显示 `from='exc_handler'`、`sig=5` SIGTRAP——信号发送者**不是自身**，而是一个名为 exc_handler 的进程。
- **证据**：2026-11-02 晚用户屏幕照片 `IMG_0180.JPG`（boot 镜像 `6153c2aa…` / kernel `64ae6488…`），kcdata 版 STR 的 `sender=`/`from=` 字段。
- **根因**：未定。疑似方向：**异常端口 / 异常中介链路**把本可恢复（或本应生成 crash 报告）的异常转成 SIGTRAP 直接处死；exc_handler 究竟是 launchd 域内的异常处理中介还是某替身进程，待源码对照。
- **修复**：无。下一步：在 xnu-work 与 iOS 用户态里查 exc_handler 的身份（谁注册、谁 spawn、处死条件）；同时注意它可能吃掉第一手 crash 现场。
- **验证**：待源码对照 + 下轮上机复核。
- **影响面**：6 个后台守护；可能掩盖真实异常原因（第一手证据被中介截走）。
- **遗留风险**：该组 desc 同样为 `-`，中介路径大概率也不附原因文本，别指望 desc 补位。

### I-20261102-14 suggestd 持续 exit=163（子问题 C，单独跟踪）

- **现象**：`suggestd` 反复 `exit=163 sig=0 ns=0 code=0x0`，不产生 STR 行。
- **证据**：`IMG_0180.JPG`（镜像 `6153c2aa…` / kernel `64ae6488…`）；HANDOFF §3.2 早前同款记录。
- **根因**：未定。`exit=163` 是 `_exit()` 状态码而非信号；`ns=0` 表示无 exit_reason——kcdata STR 对它无输出**属预期**，不是探针失灵。
- **修复**：无。需独立取证路径（`K60XT` 回退行、launchd 侧对该 job 的处理记录）。
- **验证**：—
- **影响面**：suggestd 单体；与 A/B 的 SIGABRT/SIGTRAP 循环无关。
- **遗留风险**：163 可能是 launchd throttle/禁用类状态码，需查 launchd 对退出码的处理表。

### I-20261102-02 launchd `vm_shared_region_start_address()` 两次失败

- **现象**：用户观察到 launchd 阶段 `vm_shared_region_start_address()` 失败两次。
- **证据**：**待验证**（用户转述，仓库内未见屏幕照片/日志存档；全文检索 docs/tools/reports 无此行；2026-11-02 晚已请用户补拍这两行原文）。
- **根因**：未定。可能方向：dyld 共享缓存挂载/路径、共享区域映射窗口与 4 GiB 高窗的交互。
- **修复**：无。先补证据（下轮上机拍照/抄全行）。
- **验证**：—
- **影响面**：若共享缓存没挂上，所有动态链接进程都会受影响——可能与 I-20261102-01 同源，也可能独立。
- **遗留风险**：`kern_exit.c` 中已有 `k60_probe_dyld_cache` 探针框架（路径 vnode_lookup），可用来确认缓存可达性。

### I-20261102-03 取证手段只剩「屏幕 + 拍照」

- **现象**：XNU 接管后 USB 全断；串口 COM3/COM4 是蓝牙虚拟口读不到内核输出；ramoops 重启后 DRAM 掉电不可用。
- **证据**：HANDOFF-2026-11-02.md §6.5/§6.6；`logs/boot-attempt-20261102-200610.log`。
- **根因**：平台限制（无引出 UART；XNU 阶段 USB 栈未起）。
- **修复**：无（约束，非缺陷）。工作方式已适配：所有诊断输出一屏放下。
- **验证**：—
- **影响面**：迭代速度；要求每条 printf 都谨慎设计。
- **遗留风险**：屏幕像素级丢字（控制台与 UI 抢帧缓冲），抄录需 4x 放大逐字复核。

---

## 已解决（时间倒序）

### I-20261105-02 宿主机 WSL2 无法启动（HypervisorPresent=False）——已解决（用户授权启用 Hyper-V 并重启）

- **日期**：2026-11-05（同日 11:26 关闭）
- **现象**：所有 `wsl.exe -d Ubuntu-24.04 ...` 立即失败，报 `WSL2 is unable to start since virtualization is not enabled`、`HCS_E_HYPERV_NOT_INSTALLED`；发行版列表仍显示 Ubuntu-24.04 为 Stopped。
- **证据（只读实测）**：`HypervisorPresent=False`；`VirtualMachinePlatform=1`、WSL=1，`Microsoft-Hyper-V-Hypervisor=2`（未安装）；`hypervisorlaunchtype` 已是 Auto。
- **修复**：经用户批准，管理员 DISM 启用 `Microsoft-Hyper-V-Hypervisor` 与 `HypervisorPlatform`（两者均返回成功），用户重启 Windows。
- **验证（实测）**：`HypervisorPresent=True`；`wsl -d Ubuntu-24.04 -- uname -m` 返回 `x86_64`；clang-24、`/tmp/usb-cdc-mainline`、`/tmp/k60build` 均可访问；随后 0306 内核构建成功。
- **遗留**：WSL 启动仍打印 `Failed to mount S:\`（E 盘已挂 `/mnt/e`，不影响构建），未处理。


### I-20261105-01 console-export 首轮空日志 —— 已解决（0306 修复上机 PASS，2026-11-05 12:2x）

- **日期**：2026-11-05（2026-11-05 下午解决）
- **最终判定**：`fastboot boot` `boot-console-0306-20261105.img`（sha `56953b8c…`）后，盘侧（APFS OwnerData **xid=19**，按需只读解析）`/pong/console.log` inode 249 为 **24,715 B**，首行 `===== K60LOG boot epoch=1793709100 ring_total=24006 dropped=0 =====`，其后为真实内核日志（`K60 USBLOG…`、`Darwin Kernel Version 22.6.0: Thu Nov 5 11:41:56 CST 2026` = 本轮构建）。→ **PASS，sysctl 导出通道打通**。
- **根因（首轮，源码推导）**：0243 OID 为 `CTLTYPE_OPAQUE|CTLFLAG_RD|CTLFLAG_LOCKED`；drainer 以 8 B cursor 作 `newp`，被 `bsd/kern/kern_newsysctl.c:1709-1714` 在 handler 前以 EPERM 拒绝（运行时 errno 未回读）。同时 writer/reader 无 generation，0243/USB/`kern_exec` 各自双读，一致性不可证。
- **修复（0306-k60-console-snapshot.patch，16,001 B，sha `03db2b5a…`）**：OID 加 `CTLFLAG_WR`（无 `ANYBODY`）；handler 每次请求（含无 newp 读）用 `kauth_cred_proc_ref`+uid==0 兜底 root；严格 8 B cursor；新增 `pong_ramoops_seq` odd/even writer 包裹与统一 `pong_ramoops_snapshot()`（0243 与 USB reader 共用，`kern_exec` getter 原子化）；56 B header `_Static_assert`；不稳定快照返回 `EBUSY` 而非 EAGAIN。
- **验证（离线）**：内核 `7a944a0a…`（53,813,248 B）、payload `b6c08c58…`、boot `56953b8c…`（201,883,648 B）；`trust_cache_init`=0；cmdline 18 token 与 11-04 baseline 同集合；编译 error=0。
- **验证（上机）**：仅 `fastboot boot`，Sending OKAY 4.525s / Booting OKAY 0.150s；未 flash/erase/写分区。设备回到 **TWRP recovery**，只读块设备取证。报告 `evidence/console-drain-0306-20261105/REPORT.md`，日志原件 `console.log.txt`（24,715 B），解析记录 `DEVICE-READ.json`。
- **取证方式变更**：改用 `tools/apfs-device-read.py` 按需只读取块（本次 81 块 ≈324 KiB），**不再落 21 GB 全量镜像**；并清理 E 盘一份重复全量件（19.9 GB），E 可用 62.95→82.82 GB。
- **遗留（下一步）**：① `console.log` 权限仍 0644，应 0600；marker/配额（16/64 MiB）、500 MiB floor、fsync、轮转与 STOP 持久语义未加固，受 init 35,160 B inode.size 上限约束（当前 v11drain 34,912 B）；② `dropped=0` 仅为本轮观测；③ USB reader 同源改动未在 USB 线验证（该线仍暂停）。



### I-20261104-05 trace 写盘本身疑似挂住（v9alias 比 v7probe 停得更早）

> **已关闭（2026-11-04，I-20261104-06 裁决）**：前提错误——status.txt 实际生成（39 B 全 token 链至 E1）；「零痕迹」为扫描覆盖假象（PITFALLS 45）；「早停」= console 静默死亡（PITFALLS 44）。

- **现象**：init-v9alias 上机，屏摄最后可见行是 `Pong init: var: write-check done`，其后只有一条 `K60UFS write#5`——**连 v7probe 曾打出的 4 条 `optional boot view SKIP` 都没出现**，停得比 v7probe 更早。
- **证据**：TWRP 只读核对——`/private/var/pong`、`/private/var/pong/etc`、`status.txt` 在 APFS 卷上**均不存在**（直接 ls 不存在；sda38 容器头区 + init 6144 数据区 + 5177600 新分配区 strings 扫描均无 `A0/A1/…/status.txt` 痕迹）；盘上裸前缀 sha `78dcee4c…` 确认跑的是 v9alias。
- **根因（转向，推断级）**：v9alias 的第一个 trace 写 `tr("A0")` 在 `:142`（`write-check done` :141 之后、var.skel read :143 之前），其 `trace_open`（:22-27）惰性执行 `mkdir("/private/var/pong")` → `open(status.txt,O_CREAT|O_APPEND)` → `write`+`fsync`。屏摄停在 write-check done、status.txt 又从未生成 ⇒ **init 极可能死在 `tr("A0")` 的首次 trace 写盘（mkdir/open/fsync）在 boot 早期 APFS 卷上创建新 inode 的路径上**——而非此前推断的「第 5 条 mount」。**trace 写盘本身成了新的死点。**
- **静态复核（trace 调用顺序，v9alias 源）**：`tr("A0")` :142 是**首个** trace 调用（在 `write-check done` :141 之后）；`trace_open` :22-27 惰性 `mkdir → open(O_CREAT|O_APPEND) → fsync`；此前 `:115-117` 的 write-check（open+close+unlink `.pong-write-check`）**已成功**——证明同卷 open/unlink 能工作，但 **mkdir 新目录 / open O_CREAT 新文件 / fsync 这条「创建+同步」路径未验证**。
- **竞争假设**：(i) `mkdir("/private/var/pong")` 在 APFS 上挂（建目录项触发 B-tree 分裂/vnode 锁，与 keybag/policy/prefs 写入冲突）；(ii) `open(O_CREAT)` 建 inode 挂；(iii) `fsync` 等新数据 flush 挂；(iv) 与 I-20261104-04 的 mount 死锁是同一 vnode 锁根源，只是 trace 把它提前暴露了。**注意**：v8trace（从未上机）与 v9alias 都含 trace，v7probe（无 trace）能走到第 4 条 SKIP——**有无 trace 与「停得早晚」强相关**，支持「trace 写盘挂住」。
- **修复方向（待定）**：① trace 写盘**降级为可选**（boot-arg `pong_trace=1` 才启用，默认关）先把 mount 死锁验证完；② 或 trace 目标从「创建新文件」改为「写入一个**预先存在**的空文件」（复用 write-check 已验证的 open 路径，避开 mkdir/O_CREAT）；③ 或 trace 延迟到 mount 成功后再启用（但那样 A0 之前的步骤仍无 trace）。**需先确认 mkdir/O_CREAT/fsync 三者哪个是死点**（可分版探针，但又会回到「一次 boot 一个探针」的老路——见 PITFALLS 30，需另想一次性区分法）。
- **验证**：下一步先出「trace 复用已存在文件（不 mkdir、不 O_CREAT）」版本，或「默认关 trace」版本，看能否回到 v7probe 的第 4 条 SKIP 进度再细分。
- **影响面**：trace 方案本身的可行性；若 boot 早期 APFS 创建+fsync 路径有锁冲突，**所有「init 写 Data 文件」的旁路日志方案都受影响**（包括 GAP-AUDIT 曾建议的 status.txt 旁路）。
- **遗留风险**：若连「复用已存在文件的 open+write」也挂，则 init 在 boot 早期对 Data 卷只能读不能写（write-check 的 open O_CREAT|O_EXCL 其实创建过 `.pong-write-check` 并 unlink 了——**它成功过**，所以创建是可行的，矛盾点待解：为何 `.pong-write-check` 的 O_CREAT 成功而 status.txt 的 O_CREAT 挂？差异在 `O_APPEND`/`fsync`/路径深度）。
- **结论（2026-11-04 用户拍板）**：**trace 自身是观察者效应**——v7probe（无 trace）能走到 4 条 SKIP，v8trace/v9alias（含 trace）都停得更早且 status.txt 零痕迹 ⇒ v9alias 的「早停」是 trace 引入的新变量，**不可作为「第 5 条 mount 无问题」的反证，也不证明 I-20261104-04 的 mount 死锁假设错**。定案 = 原候选①：**撤掉观测变量**，出 init-v10guard（删除全部 trace helper 与 16 处 `tr()` 调用、守卫保留并扩到 target-first），单独验第 5 条 mount。原候选②（复用已存在文件）/③（延迟启用）存档不采用。产物：`init-v10guard` 34,880 B sha `db7e4eee…`（构建与证据见 HISTORY-LEDGER 2026-11-04 构建条）；写盘脚本 `write-pong-init-v10guard.ps1`（Gate1 锚定 v9alias 现值，双断言）。
- **判读规则（裁决后方向）**：若 v10guard 在 4 条 SKIP 之后**仍定住** ⇒ 死点在第 5 条或其内核侧（`bindfs` mount 在本版 XNU 可能无可用路径），**方向立刻切到内核**，不再在用户态加探针消耗上机次数（规则全文落 GAP-AUDIT「判读规则」节）。


### I-20261104-04 第 5 条 wallpaper 别名 `mount` 疑似死锁（hang，非 panic）

> **已关闭（2026-11-04，I-20261104-06 裁决）**：假设证伪——token B4e+B4s+C1 证明第 5 条走 stock-skip、循环完整结束，mount 从未到达。

- **现象**：init-v7probe 上机，4 条 `optional boot view SKIP` 打出后**屏幕定住不动、设备不重启**——hang（死锁/阻塞）。第 5 条 `wallpaper aliases SKIP`、探针 `enter configure_ui_library`、`UI compatibility SKIP` 均未出现。
- **证据**：用户现场确认「定住不重启」（GAP-AUDIT「hang vs panic」节）；前 4 条 view 迭代（纯 stat+puts+continue）已走通 4 次，第 5 条是**唯一带 `mount` 的条目**（:254 `mount("bindfs","/Library/Wallpaper",MNT_RDONLY,"/private/var/pong/Wallpaper")`）。
- **根因（推断级，待 v9alias 证实）**：第 5 条在 stock-wallpaper 缺失时**仍走到 :254 mount**，其 bindfs 绑目录在等一个不会释放的 vnode 锁——很可能与 init 先前写入 keybag/launchd policy/boot preferences（屏摄 `keybag write err=0` 等）留下的 vnode 锁冲突。竞争假设：(i) mount 等 vnode 锁（现场支持）；(ii) stock 特判 :243/:244 本身挂（前 4 条同路径成功，降级）；(iii) 屏摄漏行（与 `enter configure_ui_library` 缺席矛盾，降级）。
- **修复（init-v9alias，正当语义守卫非绕过）**：第 5 条加守卫——source(`/private/var/pong/Wallpaper`)或 target(`/Library/Wallpaper`)父目录不存在时**整条别名步骤 skip、不进 mount**，打 `wallpaper alias SKIP (no source)`；保留 v8trace 全部 14 token，守卫前后补 `B4x`（进守卫）/`B4y`（判 skip）。
- **验证方法**：v9alias 写入 → boot → ① 若过第 5 条（打出 `wallpaper alias SKIP (no source)` 或继续到 `C1`/`D1`/`E1`）→ 死锁假设成立、原 mount 是死点；② 若仍定住 → TWRP 拉 `/private/var/pong/status.txt`，最后 token 定位（止 `B4x`=守卫内 stat 挂；止 `B4b`=进 mount 前）。**仍挂时按 vnode 锁排查（keybag/policy/prefs 写入的锁释放），不按崩溃排查**（PITFALLS 38）。
- **影响面**：直接决定 launchd 能否起；第 5 条是可选美化，SKIP 不应阻塞 exec——它 hang 住说明 mount 用户态目录在 boot 早期内核态有锁冲突。
- **遗留风险**：即使守卫绕过 mount，`configure_ui_library` 的 `sysctlbyname("kern.exec_inject")` 与 `execve` 仍是未验证下游风险点。


### I-20261104-03 init 卡点在 prepare_boot_services 第 5 条 view 迭代内（两竞争假设）

> **已关闭（2026-11-04，I-20261104-06 裁决）**：两竞争假设均证伪——进程实际跑到 D2/E1（execve 前），死点不在第 5 条迭代内。

- **现象**：init-v7probe 上机，4 条 `optional boot view SKIP` 出现后，第 5 条 `wallpaper aliases SKIP`、探针 `enter configure_ui_library`、`UI compatibility library absent; SKIP` **三者均未出现**——进程死在 prepare_boot_services 循环的第 5 条 view 迭代内部（第 4 条 SKIP 之后、`wallpaper aliases` 打印之前）。
- **证据**：v7probe 屏摄（USERLAND-PONG-GAP-AUDIT 第三轮更正，2026-11-04 11:3x 逐行转写）；`enter configure_ui_library` 探针缺席 ⇒ 没过 `:314`；`wallpaper aliases SKIP` 缺席 ⇒ 没过第 5 条的 `:245` 特判打印。
- **根因（两个竞争假设，未分）**：
  - **(a) 第 5 条别名逻辑自身崩**：`stat("/private/var/pong/stock-wallpaper/Collections/Collections~ipad.plist")`（:239）或后续 `symlink` 建别名时**空指针/越界**，进程 crash（但 PID1 crash 通常有内核打印，屏上未见 panic——待查）。
  - **(b) `/private/var/pong` 目录缺失导致 ENOENT 被当致命**：stock-wallpaper 源目录在 Data 卷上不存在（GAP-AUDIT 缺件清单已确认 Wallpaper/stock-wallpaper 均缺），某个 `stat`/`symlink` 返回 ENOENT 后被逻辑当致命错误卡死（而非优雅 SKIP）。
- **修复（下一步）**：出 init-v8probe——探针落进循环内部（每轮迭代开始打 `view[i]`），第 5 条内部三分点（进入 → 别名解析完成 → 建链接前），每个可能失败调用带 `errno`。
- **验证**：v8probe 上机后，最后停在哪个 `view[i]`/errno 行即死点。
- **影响面**：直接决定 launchd 能否起；view 5 是「可选美化」，理论上 SKIP 不应阻塞 exec——所以它**卡死**本身说明 init 的容错路径有 bug（应 SKIP 而崩）。
- **遗留风险**：即使绕过第 5 条，`configure_ui_library` 的 `sysctlbyname("kern.exec_inject")` 与 `execve` 仍是未验证的下游风险点。


### I-20261103-12 【已闭环：灾情误判】错误几何读设备 →「三窗全毁」假象；窗内容从未受损

- **闭环结论（2026-11-04，用户点名确认 + 逐字节比对）**：**「毁」= 取证读偏（按 v2 错误几何读）+ 镜像固有全零段。三窗内容从未受损；唯一真实差异 = 设备首 4 KiB 清单被 v2 错几何版本覆盖（`5dfc7ea7…`）。** v5 失败 = 清单几何错误（I-20261103-11），不是窗内容损坏。教训与防复发流程见 PITFALLS-FROM-HISTORY 第 19 条（灾情级结论三条成立条件）。本条保留原始记录如下。
- **现象**：21:43–22:09 取证判读一度认为「OS 窗全零无 NXSB、SystemOS 头变 iOS 文件内容、Data 头高熵 = 大面积毁盘」。
- **证据与复核**：
  - **OS 窗头完好（硬证据）**：`evidence/blocks/oshead-32k.bin` 与 03:40 回滚 `[0x100000,+32K)` 逐字节一致（sha `6fed98dd…`），`EFI PART`@+0x200、`NXSB`@+0x4420 在；`scan-osbody.bin` 内实测 NXSB×8。「OS 全零」读数来自按 v2 错误几何 `0x1000` 读的 `blk-a-os-v2geom.bin`。
  - **SystemOS 头 / Data 头「异常」实为读偏**：`blk-d-sysos-rbgeom.bin`、`probe-data64-device.bin` 的内容与 03:40 回滚的 `0x13020000` / `0x25F10000` 区域逐段命中（旧 OS 窗内部，iOS 文件区天然高熵）——读到了别处，不是窗被改写；全部 dump 无 sidecar（PITFALLS-FROM-HISTORY 第 7 条）导致当时无法复核读点。
- **根因**：取证读点用了错误几何 + dump 无 sidecar 无法复核。
- **修复**：灾情级结论三条件制度（第 19 条）；取证纪律（sidecar + 定点抽读，D-2026-11-03-18）。
- **验证**：已闭环（逐字节比对 + 用户确认）。
- **影响面**：消除「从零重建三窗」的错误预案；修复面收敛到 4 KiB 清单（I-20261103-11）。

### I-20261103-06 Data 写入事故：seek 进制错误写偏 1.19 MiB 进 OS 窗口（已解决：回滚恢复 + 正确偏移重写 + 全量校验）

- **现象**：首次写 20 GiB Data 镜像时，dd 落到 `0x26510000`（OS 窗内）并写入 1,327,499 失真字节；OS 窗 digest 失配。
- **证据**：三方比对（现场/回滚/镜像三方 sha）；恢复后段 sha `5db74a2d…` 一致、OS digest 复验 `bc4c5670…` 与清单一致（`logs`/ROLLBACK.json 事故条；PITFALLS P-09）。
- **根因**：seek 把十六进制块号当十进制（正确 `0x261100000/4096=2494720`）+ `adb shell` stdin 大流断管失真。
- **修复**：restore-seg 写回 → 全窗 76 块分块比对全 OK → 按四道闸门重写（公式 seek、落点核对、64 MiB 探针、分段写+段级 sha）→ 全窗回读 `adbbf0dd…` 一致 → 清单重写（`33626441…`，先数据后清单）。
- **验证**：三级 sha256 闭环（段/窗/清单）；设备停 TWRP，未触发 XNU。
- **影响面**：Data 窗口已达 20 GiB 最终布局（`0x261100000`）；OS/SystemOS 内容零变化。
- **遗留风险**：内核侧 `kern_exec.c` L7437/L7447/L7451 的 2 GiB 上限未放宽前，XNU 仍按 ≤2 GiB 处理新 Data（待下次重编）。

### I-20261103-03 A 档构建（干净树）对照镜像 `vnode_rele_ext uscount -ve` 嵌套 panic（已解决：boot-args 漂移，P1 补齐后越过）

- **现象**：`boot-a-control.img`（sha `e8290aff…`，干净树 124 补丁内核、无 `k60_usblog`）上机：`mem=actual=managed=4096` 后 `panic(cpu 0): vnode_rele_ext: vp … uscount -ve: -1, v_tag=0(VT_NON), v_type=8(VBAD), v_flags=0x84801(VROOT|VSTANDARD|VNCACHEABLE|VOPENEVT)`（vfs_subr.c L2679），随后 `lock_mtx.c:194` 抢占断言连环嵌套（Nested panic 2/3/4/5 → stall）。usblog 镜像同内核，但更早死于 I-20261103-04（SMMU），两线独立。
- **证据**：用户逐字核对屏摄 panic 原文；`vfs_subr.c` L2671-2694（panic 条件：对 usecount 已为 0 的 vnode 再 rele = 双重释放/use-after-reclaim）、`vn_set_dead` L6122-6131（回收时置 VT_NON+VBAD）；**两树 vfs/vnode 代码逐文件 diff 全同**（差异仅 0300 USB 补丁 + 4 个主线诊断文件）。
- **根因**：**boot-args 漂移**——A payload 缺 `pong_data_mount=1 pong_data_rw=1 fb_threads=3 k60-no-lc=1 k60_textonly=1 k60_sandbox=1 applog=1`（对照 4g-quiet 全集，见 `candidates/4g-quiet/extracted/unixnu.toml` vs A payload），挂载拓扑/守护进程存活形态改变，踩中共享代码里潜伏的双重 rele。
- **修复（P1，已验证）**：只重打 payload 补齐 7 个 args（**内核逐字节不变**，内嵌 kernel sha `ac896498…` 前后一致），产物 `candidates/4g-quiet/boot-ios16-4g-quiet-argfix.img`（sha `310c25a8…`，payload `851f72a1…`）。
- **验证（2026-11-03 上机通过）**：不再 panic；`K60DATA mounted ro=0 fstype=apfs`、mkdir 全 `[17]`、K60UFS write1..4 `result=0`、keybag/launch policy/boot preferences `err=0`、`load_init_program` 拉起 launchd。新阻塞独立记录为 I-20261103-05。
- **影响面**：A 档构建链可用性确认；干净树 + 123 补丁内核本身可启动到 launchd。
- **遗留风险**：潜伏的双重 rele 代码仍在共享补丁里，环境凑齐还可能再咬人；待 P2/P3 环境对齐后复查。

### I-20261102-12 `K60DATA mkdir ok=1/28` 的 errno 分布（已解决：全 EEXIST，骨架已建成且持久）

- **现象**：首轮抄录 `ok=1/28`；心跳轮报 `mkerr=17`（镜像 `db9f3c8b…` / kernel `a73e80c8…`）；直方图轮报 **`mkE=17/28`**（镜像 `ed328cfc…` / kernel `cc8cf34e…`）。
- **证据**：用户屏摄逐项核对（2026-11-02 深夜）；`kern_exec.c` L7612-7632（`mk` 只统计 mkdir() 返回 0 = **新建成功**，EEXIST=17 计入失败）。
- **根因**：28 项全部 EEXIST = 目录已存在。与「空卷」的调和：空卷是 **10-31 安装时**状态（mkapfs，xid=1）；目录由我们自己的内核在历次 boot 的 mkdir 循环创建，并经 APFS checkpoint（屏幕上的 tx_flush 行）跨断电持久。EEXIST 主项成立，且反证 **Data 读写路径完全可用**。
- **修复**：无需修。mkdir 层关闭；I-20261102-01 的「Data 只读」方向正式否证。
- **验证**：`mkE=17/28`、无 30/13；心跳每 15 秒带 `mkerr/at/dir/mkE`。
- **影响面**：冻结根因与建目录无关；exc_handler/EX_CONFIG 线继续。
- **遗留风险**：无。

### I-20261102-11 handoff-probes.py 的 `\\n` 转义 bug 导致 per-program KX! dedup 恒 0 的假象

- **现象**：探针脚本报「KX! dedup 不存在」，但内核明明已含该改动。
- **证据**：探针 needle 写成字面 `\\n`（反斜杠+n 两字符），永远匹配不到二进制里的真实换行；`tools/handoff-probes.py`（修复于 20:41）。
- **根因**：Python 字节串转义笔误。
- **修复**：修正 needle；当前输出 `per-program KX! dedup 1`。
- **验证**：对 kernel `64ae6488…` 重跑探针，9 项全绿。
- **影响面**：差点误判「构建没吃进改动」而触发不必要的重编。
- **遗留风险**：同类 needle 笔误可能存在于其他一次性脚本；判 0 时先怀疑探针再怀疑内核（见 PITFALLS P-04）。

### I-20261102-10 「reason fmt 应出现 2 次」断言过期

- **现象**：打包校验若沿用旧经验值 `count==2` 会误报。
- **证据**：`tools/package-textonly.py` 38–42 行注释：KX! dedup 把两处旧 printf 合并后，`ns=%u code=0x%llx rf=0x%llx jf=0x%x` 恰好出现 **1** 次；`count==2` 属于上一代内核。
- **根因**：内核改动改变了字符串出现次数，校验脚本的经验值没同步。
- **修复**：校验改为 expect 1，并写明原因。
- **验证**：`package-textonly.log` 显示 identity OK。
- **影响面**：打包校验可信度。
- **遗留风险**：**字符串计数是脆弱的版本指纹**；内核再改输出格式时，必须同步更新 handoff-probes.py 与 package-textonly.py 两边（见 PITFALLS P-05）。

### I-20261102-09 STR 探针实测全空（4 GiB pagezero）→ kcdata 方案【已上机验证】

- **现象**：旧 STR 探针（扫进程地址空间 `[4K, 4MiB)` 找异常文本）上机一条都打印不出来。
- **证据**：`xnu-work/bsd/kern/kern_exit.c` 162–168 行注释实证：该区间落在 arm64 的 4 GiB pagezero 内，从不映射，`copyinmap` 处处失败。
- **根因**：地址区间选错——低 4 MiB 在 arm64 永远不可读。
- **修复**：改为读 exit_reason 的 kcdata payload（`KCDATA_TYPE_PID` / `KCDATA_TYPE_PROCNAME` / `EXIT_REASON_USER_DESC`），见 D-2026-11-02-07。
- **验证**：构建通过 + 探针全绿；**上机验证完成**（2026-11-02 晚，照片 `IMG_0180.JPG`，boot 镜像 `6153c2aa…` / kernel `64ae6488…`）：STR 成功区分「自杀」（`sender==自身 pid`、`from='<本名>'`、`sig=6`）与「被杀」（`from='exc_handler'`、`sig=5`），探针有效，从「待验证」转为「已验证」。
- **影响面**：取证主通道。
- **遗留风险**：若进程死时没带 exit_reason（OS_REASON_NULL），新版也打不出 desc——`K60XT` 回退路径行可部分补位。

### I-20261102-08 内存窗口定案：4 GiB 可用，12/8/7 GiB 已实测不可行

- **现象**：早期 296 MiB 窗口疑似不够；想上更大窗口。
- **证据**：live FDT 六 bank（`reports/live-6033dbec-*`）；8 GiB 镜像被拒（DXE 占区间）、7 GiB 加载器接受但 XNU 未起（AGENT-COORDINATION 17:51 条目，镜像 sha `8ea52daf`）；4 GiB 屏幕实测 `mem=4096 actual=4096 managed=4096`、`free_pages≈105012`（≈1.6 GiB）。
- **根因**：物理布局——12 GiB 在 6 个不连续 bank，4–32 GiB 无 DRAM，XNU arm64 只管理一段连续区间；加载器限 ≤8 GiB。
- **修复**：定案 4 GiB 高窗 `0x900020000..0xA00020000`（D-2026-11-02-04）。
- **验证**：设备实测三值 + free_pages。
- **影响面**：所有后续候选镜像的 ADT `/chosen`。
- **遗留风险**：无；1.6 GiB 空闲说明内存不是当前瓶颈。

### I-20261102-07 Data 卷 ENOSPC

- **现象**：10-31 记录 `launchd/usermanagerd/logd_helper: ENOSPC`（free_blocks 1208 < threshold 1310）。
- **证据**：`UniXNU-mondrian/docs/DATA-SPACE-2026-10-31.md`（用户抄录的 ENOSPC 行）。
- **根因**：内部 Data APFS 只有 256 MiB；外层 32 GiB unixnu 有 24.5 GiB 未分配但 APFS 分配器不会自动借用。
- **修复**：Data 已扩到 2 GiB（GPT 窗口 + 内部 APFS 一起扩）。
- **验证**：20:03 上机屏幕抄录 `K60DATA mounted ro=0 fstype=apfs`、`K60DATA mkdir ok=1/28`（用户转述，**无照片存档，待验证**）；HANDOFF §2 记录「已扩到 2 GiB」。
- **影响面**：launchd/容器/日志写入。
- **遗留风险**：`mkdir ok=1/28` 的 1/28 语义（28 项里成功 1？还是计数口径）待下轮照片逐字复核。

### I-20261102-06 固件虚报高段 + boot_args ABI 代际错误

- **现象**：高窗候选镜像早期 fault；PE 元数据一度被误判为 ArmCpuDxe 故障。
- **证据**：`reports/fault-pe-inventory.json`；DarwinBoot RVA 0x48fc = ZeroMem 的 `str xzr, [x20], #8`；固件本地头是 Darwin24 偏移而内核是 iOS16（Darwin22）。
- **根因**：旧 Conv 段 `[0x100000000,0x380000000)` 整个落在 4–32 GiB 无 DRAM 空洞；BootArgs 偏移代际错配。
- **修复**：恢复低段描述符 + 只加 `[0x900000000,0xA40000000)` arena；BootArgs 改 Darwin22（D-2026-11-02-02）。
- **验证**：固件 sha `1c870bb2…`、候选 `aa680659…`、屏幕 mem=4096。
- **影响面**：启动链最底层。
- **遗留风险**：无。

### I-20261102-05 「内核未重编」叙述过时（文档误导风险）

- **现象**：HANDOFF-2026-11-02.md §4 写「源码已改，但内核未重编」，且表中 STR 一行指旧地址扫描版。
- **证据**：该叙述在 19:30 成文时为真；20:42 已重编（`64ae6488…`，含 kcdata 修复）；且 19:54 的 4g-quiet（`302a001b…`）已含上一代重编内核 `65fbe51e…` 并上机。
- **根因**：交接文档成文后工作继续推进，文档未回刷。
- **修复**：本 docs 体系（INDEX 已标注；DECISIONS 镜像身份链以 sha 为准）；RECORDING-RULES 规定交接前必须刷新 INDEX。
- **验证**：`logs/kernel-exit-summary.log`、`logs/package-textonly.log`。
- **影响面**：下一个人若照 §4 重编旧 STR，会浪费一轮。
- **遗留风险**：HANDOFF 正文未改（只读盘点原则）；误导防护靠 INDEX 的显著标注。

### I-20261102-04 mcopy 交互式覆盖确认卡死打包

- **现象**：从 payload.img（FAT）抽文件时流程卡死无输出。
- **证据**：`tools/package-textonly.py` 33–34 行固定带 `mcopy -o`（用户转述曾在此卡过）。
- **根因**：`mcopy` 默认覆盖前交互确认，无人值守脚本里 stdin 无输入 → 永久等待。
- **修复**：所有 mcopy 调用一律带 `-o`。
- **验证**：19:54 打包全程无人工干预通过。
- **影响面**：所有从 FAT ramdisk 抽文件的脚本。
- **遗留风险**：新写脚本时容易漏（见 PITFALLS P-03）。

---

### I-20261103-10 pong-driver 整目录 gitignore 误删构建依赖（已解决：315cf99 恢复 + gitignore 产物化 + P-11 立规）

- **现象**：v2 `unixnu build kernel` 连续失败：① `pong-driver/scripts/build-pong-platform-macos.py` 不存在；②（补后）adreno 脚本 `ROOT` 定位穿透、`PongAdrenoCpProfile.h` 找不到；③ `bindings.json` 缺失；④ GMU 固件 `/Volumes/...` 默认路径不存在；⑤（构建过）prelink 撞 `Rebased component collides with native __DATA`（autoslide 包装器被 tree 刷新重置，需恢复 `emit_prelink_orig.py` 配套）。
- **根因**：仓库整理把 `pong-driver/` 当参考副本整体 `.gitignore`（`/pong-driver/` 一行），但其中 `scripts/`、`shim-bin/` 是构建链执行件（board.toml `pong_native_driver_source` 指向）；固件在仓外 `D:\Android\k60-ios\firmware\k60-gpu`（恢复后脚本 `--firmware-dir` 默认值自述）。
- **修复**：`git checkout 315cf99 -- pong-driver/scripts pong-driver/shim-bin pong-driver/mac-build/native-ufs/bindings.json` 恢复并提交 `cafab71 fix(vendor): restore pong platform build scripts`；`.gitignore` 改为只忽略产物（`*.a`/`*.o`/`*.log`/`build/`/`build-report.json`），`git check-ignore -v` 证明脚本不被忽略；固件五件与 13:55 构建产物反嵌字节完全一致（`D:\Android\k60-ios\firmware\k60-gpu` 实址在机）；autoslide 包装器按 preflight 步骤重装（`emit_prelink_autoslide.py` → 入口、stock → `emit_prelink_orig.py`）。
- **教训**：已写入 PITFALLS P-11（整理目录前必查 scripts/ 是否构建依赖；gitignore 只忽略产物）。
- **30 秒判定**：要给任何目录加 ignore/删除前 → 先 grep 构建脚本与 board.toml；见整目录忽略规则直接否。

---

## 外部线索登记（只记来源，不写结论）

| 登记时间 | 来源 | 一句话说明 |
|---|---|---|
| 2026-11-02 晚 | `https://github.com/XTOM0706/ios-sweet-k60` | hackios 方案仓库；同硬件已进用户态，未修完 |
| 2026-11-02 晚 | `https://github.com/oosexgang` | hackios 已改名 **hakios**，此为组织页 |
