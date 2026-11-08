# ROUTE-USERSPACE — K60 iOS 16.6.1 用户态路线裁决（2026-11-02 v2）

> **状态（2026-11-04 标注）**：路线分析已定案并已被后续演进吸收——「先诊断不换 PID1」之后，pong init 前置层于 11-03 落地（DECISIONS D-2026-11-03-03/04，v6 屏摄证实 init 跑通至 exec launchd 前）。本文档保留为路线史与证据基础，当前卡点见 INDEX §1。

> v2：纳入 STR/kcdata 上机证据（IMG_0180）、hakios 组织盘点、5 个上游仓库增量审计。
> 只读调研；本文件是唯一写入产物。

## 0. 结论先行

1. **STR 已定性：两批崩溃全是「自杀」，没有外部杀手。**
   - `from=本名 + SIGABRT`（accountsd/dad/aggregated/ScreenTimeAgent）= 进程自己 `abort()`。
   - `from='exc handler' + SIGTRAP`（financiald/cloudd/chronod/mmaintenanced/mobileactivation/liveactivitiesd）= 进程自己 `__builtin_trap()`（`_os_crash`/dyld/libdispatch 断言），Mach 异常 `EXC_BREAKPOINT` 经内核转换成 SIGTRAP。
   - 依据：`kern_sig.c:1808`（`threadsignal()` 里硬编码 `"exc handler"`，照片里的下划线是转写误读）+ `kern_sig.c:1962`（`sender_proc = current_proc()`，sender=濒死进程自己）+ `bsd/uxkern/ux_exception.c:101-104`（EXC_BREAKPOINT→SIGTRAP）。
2. **`exc_handler` 不是进程、没人启动它、与 `disable_exc_resource` 无关**（那是 EXC_RESOURCE，另一种异常类型，且该转换路径根本没走它）。详见 §2。
3. **`desc='-'` 的含义**：没有任何进程走 `abort_with_reason()/terminate_with_reason()`（那会附 `EXIT_REASON_USER_DESC`，`kern_exit.c:217`）。NSException/普通 assert 的原因文本**不在 exit reason 里，在 stderr 上**——所以下一步不是改 STR，而是把 stderr 接出来。
4. **下一步只改一处：payload 的 boot-args 加 `applog=1`**。内核不用动：`applog` TUNABLE 已在核内（kernel.macho 实测含该字符串 ×2；实现 = `zzzz…-pong-hackios-launchd-exec.patch`，kern_exec.c:2621-2710，把 service 的 fd1/fd2 打开 `/dev/null` 重定向到 `/dev/console`）。预期证据见 §4。
5. **上游 5 仓库增量审计：没有一条能解释当前卡点**。提示里「sm8550-common 含 GPU/startup 修复」经核实是误报（实际内容见 §5）。不需要摘任何 commit。
6. **路线裁决不变**：A（续修原生 launchd）为主线；B 的准备序列以内核钩子形态并入（已在跑）；C（可写 root）不做。hakios 主仓的自研 init/rc 层**不借**（§6）。

---

## 1. 症状 → 根因假设表（v2）

| # | 症状 | 根因假设 | 强度 | 来源 |
|---|---|---|---|---|
| S1 | accountsd/dad/aggregated/ScreenTimeAgent：from=self，SIGABRT，desc='-' | 自杀：NSException 或 assert 触发的 `abort()`。原因文本在 stderr，目前进了 `/dev/null`。**最可能诱因仍是容器/MCM 查询失败**（OPEN 墙），文本待 applog 验证 | 强推断（自杀已验证；诱因待 applog 文本） | kern_sig.c:2449/2515（psignal 路径 build_signal_reason(signum,NULL)）；stderr→console 通道 = kern_exec.c:2621-2710 |
| S2 | financiald/cloudd/chronod/mmaintenanced/mobileactivation/liveactivitiesd：from='exc handler'，SIGTRAP | 自杀：`__builtin_trap()`（EXC_BREAKPOINT）→ 内核 `handle_ux_exception`→`threadsignal`→SIGTRAP。常见于 `_os_crash`、dyld 致命错误、libdispatch/CF 断言 | 已验证（机制）；诱因待证 | ux_exception.c:101-104；kern_sig.c:1808；kern_sig.c:1962 |
| S3 | suggestd exit=163 sig=0 ns=0，不打 STR | **正常 exit()，非崩溃**（STR 只在致命信号 + 有 exit reason 时打印，kern_exit.c:185-193）。163 是自愿退出码；是 launchd 让其退出还是自身缺数据，待 applog 输出 | 待证 | 机制见 kern_exit.c 注释（「runs only when the exit carried a fatal signal」） |
| S4 | 崩溃循环不收敛（ex=1388 abn=446） | 这批 daemon 互相是对方的依赖（container→accounts→cloud 链），一个缺根基集体循环。**不是** launchd 在杀（无 from=launchd 记录） | 强推断 | 本次 STR 全量记录无外部 sender |
| S5 | free 稳定 99k–108k 页 | 内存不是瓶颈（再次确认） | 已验证 | 与 HANDOFF §3.1 一致 |
| S6 | `K60DATA mkdir ok=1/28` 的 `[path=errno]` 明细 | 照片未含此行，**仍待证**：全 17(EEXIST)=正常；出现 30(EROFS)=Data 只读，优先级升到 P0 之前 | 待证 | 0239-k60-runtime-directories.patch 的统计逻辑 |
| S7 | launchd 两次 `vm_shared_region_start_address() failed` | 正常启动序列（check_np 先失败后自装），参考项目同消息已证伪为根因 | 强推断（无害） | ios-sweet-k60 HANDOFF-FULL-2026-10-25「推翻共享缓存坏了」节 |

**已证伪不再试**：内存、Sandbox 策略、显示前提、ADT、dyld 缓存装载、SMP、jetsam、沙箱拒绝、外部杀手（本次新增：from 字段证明无外部杀手）。

---

## 2. 三个具体问题的答案

### Q1：`exc_handler` 是什么、谁启动、为什么 SIGTRAP、是不是 disable_exc_resource 的副作用？

- **不是进程，没有「谁启动」**：它是内核在 exit reason 里硬编码的标签字符串 `"exc handler"`（kern_sig.c:1808，`threadsignal()` 内），表示「这个致命信号来自 Mach 异常→BSD 信号的转换路径」，而不是某个名叫 exc_handler 的程序杀了它。
- **sender pid 为什么是进程自己**：`build_signal_reason()` 里 `sender_proc = current_proc()`（kern_sig.c:1962）——异常是在犯错线程自己的上下文里同步转换的，current 就是濒死进程。
- **为什么是 SIGTRAP**：`EXC_BREAKPOINT → SIGTRAP`（ux_exception.c:101-104 的 `ux_exception()` 映射表）。用户态产生 EXC_BREAKPOINT 的典型来源：`__builtin_trap()`，即 `_os_crash()`、dyld fatal、libdispatch `BUG IN CLIENT`、Swift runtime 致命错误这类「带一条消息后自陷」的路径。
- **与 `disable_exc_resource` 无关**：该 boot-arg 只影响 `EXC_RESOURCE` 型异常的投递；EXC_BREAKPOINT 是独立异常类型，且证据上两类名单/sig 都能用自杀模型完整解释，不需要引入它。
- **与异常端口配置的关系**：只有当进程自己或 ReportCrash 注册了 Mach 异常端口并处理了异常，才不会走到 `threadsignal`。启动早期 ReportCrash 链路不完整 → 走默认转换，这是**预期行为**，不是配置错误。真正的信息缺口是异常文本不在 exit reason 里（见 Q2）。

### Q2：accountsd 类「哑崩」（desc 空、SIGABRT）拿什么最小手段要原因？

可选通道对比（**不改 STR**）：

| 手段 | 原理 | 成本 | 覆盖 |
|---|---|---|---|
| **`applog=1`（推荐）** | `pong-hackios-launchd-exec.patch`：service posix_spawn 打开 fd1/fd2=`/dev/null` 时改写为 `/dev/console`（kern_exec.c:2621-2710，`ARM64_BOARD_CONFIG_PONG && (DEVELOPMENT\|\|DEBUG)`，TUNABLE 默认 0）。NSException 默认处理器的 `*** Terminating app due to uncaught exception ... reason: '...'` 走 stderr | **零内核改动**（字符串已在 kernel.macho，实测 2 处命中），只改 payload boot-args | NSException/assert/CF 错误文本全覆盖；`_os_crash` 的消息**不走 stderr**，SIGTRAP 类只能拿到它之前打印的行 |
| 异常端口/corpse | 注册内核异常端口或等 ReportCrash | 大改 | 能拿 `_os_crash` 的 crash_info，但启动期 ReportCrash 链不完整 |
| crash report 落盘 | 需要 Data 上 CrashReporter 目录 + ReportCrash 可用 | 依赖未就绪 | 0239 已建 `/private/var/mobile/Library/Logs/CrashReporter`？**未找到**（0239 表里没有该路径；pong init.c:262 有 `/private/var/mobile/Library/Logs/CrashReporter`——可作为后续钩子补建） |

补充观察：hackios（ios-sweet）当年就是靠同族手段取证的——上游补丁表 0047–0055 明写「/dev/null tee、heap strings on crash、user stack sampler」（README「Kernel patches」节，本地克隆 D:\Android\k60-ios\ios-sweet-k60，origin=XTOM0706/ios-sweet-k60，HEAD 3fbaa5e）。我们的 STR 是 heap-strings 的 kcdata 升级版，applog 是 /dev/null tee 的同款。

### Q3：唯一的下一步动作 + 预期证据

**动作：重打 payload，boot-args 加 `applog=1`；内核二进制不动；上机拍一屏。**
（`build-payload-sandbox.sh` + `package-textonly.py` 链；不动 build-kernel。）

| 预期证据 | 判读 |
|---|---|
| `*** Terminating app due to uncaught exception '…' reason: '…'`（accountsd/dad/aggregated/ScreenTimeAgent） | reason 文本直接指认缺什么（container/MCM/偏好/数据库路径），按文本修一处 |
| `BUG IN CLIENT OF …` / CF 断言文本（SIGTRAP 类在 trap 前的 stderr） | 同上 |
| suggestd 退出前的 stderr 行 | 解释 exit=163 |
| 什么 stderr 都没有 | 说明这批崩溃全程不写 stderr（纯 `_os_crash`），再考虑 corpse/crash_info 通道——**这是下一步的下一分支，现在不做** |
| 同屏顺便读 `K60DATA mkdir ok=…[path=errno]` | 全 17=正常；有 30(EROFS)=Data 只读，**改修 Data 挂载为第一优先** |

风险：applog 会让所有 service 的 fd1/2 上屏，行数增多——但 NSException 文本每个 daemon 只几行，且当前内核已压滚动源（帧统计 1 行、corpse 静默）。可接受。

---

## 3. 症状表之外：STR 机制留档（防误读）

- STR 触发条件：进程因致命信号退出且内核持有 exit reason（kern_exit.c:163-193 `k60_print_exit_reason`）。
- 字段来源：`sender` = kcdata `KCDATA_TYPE_PID`；`from` = `KCDATA_TYPE_PROCNAME`；`desc` = `EXIT_REASON_USER_DESC`（kern_exit.c:195-231）。
- `desc` 为空只说明没走 `abort_with_reason()`/`terminate_with_reason()`；**不代表没有原因文本**——NSException 的原因在 stderr。
- 旧版「读进程低 4 MiB 堆字符串」为何作废：arm64 的 4 GiB pagezero 使得低地址从未映射，旧扫描器读到的是空（kern_exit.c:163-169 注释）。

---

## 4. hackios / hakios 盘点

### 4.1 XTOM0706/ios-sweet-k60（本地克隆即上游，HEAD 3fbaa5e，2026-10-29）

- **用户态为什么能起**：可写 HFSX 单卷 root（userdata，无独立 Data 卷）+ 构建期 `sweet-root-tweaks.py`（Setup 跳过、containers、activation data_ark、launchd.plist 改 `_PanicOnCrash`/删 CommCenter、关 VirtualAudio/MediaToolbox）+ 宽松 AMFI/Sandbox 内核策略 + `launchd_unsecure_cache=1` 等 boot-args（README「How to do it yourself」节 cmdline）。launchd 是**原版**。
- **哪些服务仍不行**（README「What does not work」+ HANDOFF-FULL）：无 WiFi/BT/基带/音频/相机/传感器/GPS/SEP，对应 daemon 起来就失败或反复重启；无 GPU（CPU 渲染，CA 帧全空）；导航 home 手势坏；driverkitd 每轮必崩（sig=9）。**即：它的「能进用户态」不等于这批 daemon 都活了——它靠删掉/绕过会致命的，容忍其余循环。**
- **rootfs/Data 组织**：单 HFS+ 卷，`mkiosroot.sh` 把 OS+两个 cryptex 合进一卷、补 dyld 缓存硬链接与 plain keybag；`/private/var` 就在可写 root 上；日志环在 userdata 末尾 4 MiB，recovery 里 `sweet-log-pull.sh` 拉取。
- git 历史（只读 `git log`）：0218 显示前提、0240-0248 触摸、0249 壁纸 Plan Z 等；无 container/launchd 崩溃修复类 commit。

### 4.2 hakios 组织（github.com/oosexgang，7 仓，2026-11-02 盘点）

| 仓库 | 内容 | 与本任务相关性 |
|---|---|---|
| hakios-xnu-kernel（2.3k★） | 主仓：内核 patch + loader + **userland/** + 文档 | 见下 |
| hackios-xnu-userland（403★） | 只剩指针：已并入主仓 `userland/`（commit 2573c4a，2026-10-25） | — |
| hakios-metal | Adreno 上的 Metal 命令模型（C++） | GPU 后期，无关当前卡点 |
| hakios-sm7325 | POCO X5 Pro（redwood）设备仓 | 参考 |
| hakios-uefi | Mu-Silicium 固件 + U-Boot | 引导层，无关 |
| hackios-web | 项目网站 | 无 |
| hakios-mt6768 | Infinix hot 20 设备仓 | 无关 |

**主仓 userland/ 内容**（api.github.com 目录清单）：`rc.darwin`、`rc.jobs`、`rc.jobs.air{,2,kernels,tex,apfs,apps}`、`mkjobs.py`、`jobinfo.py`、`mkeagl.py`、`mkhighrate.py`、`build.sh`、`libmini/`、`com.hakios.{demo,varstore,wifi}.plist`。
`rc.darwin` 头注：「Commands init runs after its own checks」——**hakios 用自研 init + rc 脚本编排用户态**（Darwin userland 16.5），不依赖 launchd 的 job 语义；README 自称研究台（RAM 会话、logdump 分区写日志、`ufs_write=1` 才写自建 `darwin` 分区）。

### 4.3 本质差异判断：差在哪一层、能否只借一层

| 层 | ios-sweet（hackios 旧线） | hakios 主仓新线 | pong | 我们 |
|---|---|---|---|---|
| 异常端口 | 不装 userspace handler；内核 console crash report + heap strings | 同思路（研究台） | 无 | KX!/STR（等价物已在） |
| init/PID1 | **原版 launchd** | **自研 init + rc.jobs** | 自研静态 init → exec 原版 launchd | 原版 launchd |
| root 可写性 | 可写 HFSX（构建期改） | RAM 会话 / 自写 darwin 分区 | 可写 APFS 副本（构建期改） | 只读 union + 内核挂载期钩子写 Data |
| 服务白名单 | 构建期改 launchd.plist | rc 脚本全量自管 | 运行时 bindfs/prefs | disabled.plist + 偏好种子（kern_exec.c 钩子） |

**结论**：
- 我们与 ios-sweet **不本质不同**：同是原版 launchd + 内核替身策略，差的只是 tweak 的**投递机制**（它构建期改可写 root，我们内核钩子写可写 Data）。它的 tweak 清单已大部移植（0239/disabled.plist/双偏好）。
- hakios 主仓的 init/rc 层**是另一层替换，且比 pong 更激进**（连 launchd job 语义都不要）。它能进锁屏/主屏是在 redwood 上用 16.5 userland + 自己的服务编排，**证明的是「换 init 层可行」，不是「我们的 daemon 崩溃因此可解」**。借它等于放弃 launchd 语义重做服务编排——工作量大于 pong 方案，且失去 Apple 自己的依赖/恢复语义。当前 STR 证据（全自杀、无外部杀手）完全不指向 PID1 层，**不借**。
- 可只借且值得借的一层：**诊断投递**（stderr→console，已在我们树里=applog）与 tweak 内容清单（已移植大半）。

---

## 5. 上游 5 仓增量审计（E:\k60-work\references\，HEAD..FETCH_HEAD，只读）

| 仓库 | 落后 | 关键词命中 | 逐条结论 |
|---|---|---|---|
| UniXNU-sheng | 227 | 无 container/launchd/sandbox/shared_region/dyld 命中 | **没有能解释当前卡点的提交**。最近的「startup」族（6dafef9 PR#57、030fcd2、50bd2f9）是 iPadOS27/xnu-12377 的打包与构建修复；`5ef4821`（每次启动丢 LaunchServices 库，治「只剩 Settings」）与 `0c52609`（`kern.hv_vmm_present` 对用户态改答，治 MobileGestalt IsVirtualDevice=1→QuartzCore 选错帧缓冲格式）是有价值的**记录**，但对应症状我们都没有；`3075216`（追踪发给 backboardd 的消息）是纯诊断 |
| UniXNU | 55 | 全部 GPU/Adreno/Turnip/诊断 | 面向其 Darwin24+ GPU 栈，与用户态崩溃无关 |
| UniXNU-pong | 7 | 无 | docs + CI userdata 镜像 + `6da0ec3` **删除 iOS16/20G81 构建树**（上游已弃 Darwin22，别再等它修我们这条线） |
| uefi-pong | 2 | 无 | Mu_Basecore 子模块 bump |
| UniXNU-sm8550-common | 1 | — | `a9f45dc` 实测内容 = xnu-12377 的两个小 patch（native-smp-secondary 15 行 + sheng-platform-power 16 行）。**「GPU/startup 修复」提示不成立**；SM8550 + 新内核代际，与 K60 backboardd 首帧后的停滞无关 |

**可摘性总判**：无一需要摘。若未来要参考异常取证增强，sheng 的 `50bd2f9`（exception record 在 RELEASE 下的声明修复）说明他们在 xnu-12377 树里做了一个「exception record」诊断件，可作思路参考，不可直接摘（跨内核代际）。

---

## 6. 路线对比与混合分层（维持 v1 结论，按新证据收紧）

- **A（续修原生 launchd）= 主线。** STR 证明问题在 daemon 自身缺资源/数据，不在 PID1、不在内核杀手。改动形态：内核挂载期钩子（已有 0239/keybag/disabled.plist/双偏好四个先例，kern_exec.c:7509-7800）+ 主机侧 Data 镜像修复。
- **B（pong init）**：仍只在「STR/applog 证明必须在 PID1 之前跑用户态准备」时才上；换入机制 = `init_programs[]` 加候选路径（kern_exec.c:7886-7894），init 放 Data，exec 原版 `/sbin/launchd`，无需 pong 的 rename（其 rename 依赖可写 root，build-ipados18.py:1062-1064）。
- **C（hackios 可写 root）**：不做。它能起用户态靠的是 tweak 内容而非 HFSX 本身；内容已能经内核钩子投递。
- **分层现状**：内核层=现树全保留；root 准备层=内核钩子（借 pong 序列的形，不走它的 init）；init 层=原版 launchd；服务层=原版 daemon + 逐个点修。

## 7. 待证清单（不猜）

1. `K60DATA mkdir ok=1/28` 的逐项 errno（待补拍照片）。
2. applog 打开后各 daemon 的 stderr 原文。
3. suggestd exit=163 的退出原因。
4. SIGTRAP 类是否全程不写 stderr（决定要不要 corpse/crash_info 通道）。
5. accountsd 类是否与 container/MCM 相关——等 applog 文本证实或证伪（当前仅强推断）。

## 8. 查证记录（新增部分）

| 结论 | 来源 |
|---|---|
| "exc handler" 标签语义 | 构建树 `bsd/kern/kern_sig.c:1808`（threadsignal）、`:1959-2016`（build_signal_reason，sender=current_proc）、`bsd/uxkern/ux_exception.c:101-104`（EXC_BREAKPOINT→SIGTRAP） |
| STR v2 字段来源 | 构建树 `bsd/kern/kern_exit.c:163-236`（k60_print_exit_reason） |
| applog 机制与门禁 | `patches/xnu/zzzz…-pong-hackios-launchd-exec.patch`（kern_exec.c:2621-2710）；kernel.macho 二进制含 `applog` 字符串 ×2（/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho） |
| ios-sweet 用户态方法与缺口 | 本地克隆 README（D:\Android\k60-ios\ios-sweet-k60，origin=https://github.com/XTOM0706/ios-sweet-k60，HEAD 3fbaa5e）、HANDOFF-FULL-2026-10-25.md、tools/sweet-root-tweaks.py |
| hakios 组织 7 仓与 userland 内容 | github.com/oosexgang 组织页 + api.github.com 目录清单 + userland/rc.darwin 原文（2026-11-02 拉取） |
| 上游增量 | E:\k60-work\references\{UniXNU-sheng,UniXNU,UniXNU-pong,uefi-pong,UniXNU-sm8550-common}，`git log HEAD..FETCH_HEAD` / `git show`（只读） |
| 未找到 | 各上游对 accountsd/financiald 等 daemon 崩溃的直接修复；hakios 的 exception-handler 专门件（未找到——它的取证也是内核 console 线） |
