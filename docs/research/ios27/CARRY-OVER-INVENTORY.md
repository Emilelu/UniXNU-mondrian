# 16 线资产清点：迁移到 iOS 27 时我们丢了什么

日期：2026-11-22
触发：用户两次质问——「自动复位代码在 ios16 的时候都有了，现在你又要重复造轮子？」「迁移到 iOS 27 你是完全把之前各种代码全丢了？」

## 事实（机器可核，不是印象）
> 口径修正（2026-11-22，input27 指出）：`check-series-numbering.py` 只认四位编号，所以它的「34」不含两条无号条目；真正的行数是 **36**。同一原因，16 线的「136」也不等于「全部」，全部是 **240**（含 111 条无号）。三个数字用 `scripts/series-count.py` 一次打出来，引用时必须写明是哪一种。


| 项 | 数值 |
| --- | --- |
| iOS 16 系列补丁行（`scripts/series-count.py`） | **240**（129 带号 + 111 无号） |
| iOS 27 系列补丁行 | **36**（34 带号 + 2 无号：`ptrauth-string-discriminator.patch`、`armcpu-sleep-hook.patch`） |
| 其中从 16 线搬来的 | **3**（`0540`/`0541`/`0546`），本轮新增 `0547`/`0548` |
| 16 系列里名字命中 console/autoreset/heartbeat/usb/touch/buttons/ramoops/panic/watchdog/reset/boot/log 的 | **46** |

结论：**是的，迁移时几乎全丢了**。27 系列 34 条里，只有 `0540`（PSCI CPU start）、`0541`（虚拟定时器）、`0546`（ramoops 控制台）三件是从 16 线拿过来的，其余 31 条是 27 特有的（arm64e/PAC、fileset、ADT、modesetting）。而 `0546` 之所以要「重切」，是因为我把它当成新东西写，而不是先查 16 线有没有——轮子就在这里。

## 16 线里与 stage-0 出口直接相关的资产（46 条中筛出）

按「没有它就看不清/回不来/起不动」排序，只列 stage-0 必须评估的：

| 16 线补丁 | 作用 | 27 现状 | 处置 |
| --- | --- | --- | --- |
| `0300-k60-usblog-ep0.patch` | 内核自己给出一个 USB 串口（同一次启动内可读） | 无 | **移植（第一优先）** |
| `0243-k60-console-export.patch` | 把内核 console 输出导向导出通路 + sysctl 计数 | 无 | **移植（与 0300 同批）** |
| `0306-k60-console-snapshot.patch` | 冻结/快照最后 N 行，供读侧一次取走 | 无 | 移植（0300 之后） |
| `0331-k60-prevlog-replay.patch` | 上次启动留下的日志在本次启动重放 | 无 | 移植（有前一次日志就能看第二次） |
| `0334b-k60-autoreset.patch` | `k60_autoreset=<s>` / `k60_autoreset_idle=<s>`：到达时间或空闲即**主动复位**，用于「无人值守的连续尝试」 | 无 | **移植（自动复位的正解，不是新写 WDT）** |
| `0219-k60-iowatchdog.patch` + `0221-k60-watchdog-status.patch` | IOWatchDog 状态与喂狗可见性 | 无 | 评估（先看 0334b 是否已够） |
| `0303-k60-heartbeat.patch` / `0405-k60-usb-heartbeat.patch` | 心跳行，证明「还活着」 | 无 | 移植（判据用） |
| `0334-k60-panic-reset-fastboot.patch` | panic 后复位回 fastboot | 无 | 移植（自动化的另一半） |
| `0311-k60-panic-restart-reason.patch` | 复位原因进日志 | 无 | 移植 |
| `0230-k60-exc-resource-early-out.patch` | 早期异常资源不足时早退而不是挂死 | 无 | 评估 |
| `0214/0543/0544`（面板控制台） | 在屏上画字 | 27 已有 `0543`/`0544` | 已带 |
| `zzzzz-pong-ramoops-minimal` + `0232` + `0243` + `0300` | 四层链：底座 → 诊断桥 → 导出 → EP0 | 只有 `0546` 的内核侧写桩 | 按序补齐 |

## 为什么这条清单必须在写任何新代码之前存在

今天已经重造了两个轮子：
1. `0546` ramoops 控制台——16 线 `0243`+`0300` 早就有完整实现；
2. 「看门狗自动复位」——16 线 `0334b-k60-autoreset.patch` 就是它，`board.toml` 的启动行里 `k60_autoreset=300` 至今还在，而我今晚在设计新的 WDT 方案。

同时还有一条已证伪的仪器：`RamoopsDumpDxe`（固件侧读 `0xA7000000`）在**复位后读**，而 ramoops 掉电即失 ⇒ 它天然读不到东西。这条也在 `BOOT-FREEZE.md` 里作废了。

## 纪律（写进 `check-carry-over.py` 的判据）

1. 新增任何内核侧能力之前，必须先在 16 系列 240 条里搜同义关键词；命中就必须在本文档登记一行（`ported` / `to-port` / `not-needed` + 理由）。
2. 「27 上没有」不等于「需要新写」；先答「16 线是怎么做的、为什么现在不能直接用」。
3. 任何 `to-port` 条目，移植前要给出「16 线验证过的证据」（哪次启动、哪行日志、哪个 jar）。

## 实测：这三条能不能直接打到 27 树上（2026-11-22 03:3x）

判据：在**已应用四层补丁的 27 装配树** `…/mondrian_ios27/tree/.cache/xnu-work` 上逐条 `git apply --check`（只读，不改树）。

| 16 线补丁 | 结果 | 含义 |
| --- | --- | --- |
| `0300-k60-usblog-ep0.patch` | `patch failed: osfmk/arm/arm_init.c:669` | 锚点被 arch 层的 `zzz-boot-progress.patch` 包住，与 `0546` 同一个位置 ⇒ 必须按 `recut_console_layers2.py` 那套「重放四层 → 显式打 arm_init 的 hunk → commit 分层 → 再插」重切 |
| `0243-k60-console-export.patch` | `patch failed: bsd/conf/files:105` | conf/files 行号漂移。我们的 `conf/files` 由 `scripts/append-conffiles.py` 追加（19 条），**这一 hunk 应丢弃**，其余 hunk 再逐个对锚点 |
| `0334b-k60-autoreset.patch` | `bsd/dev/k60_usblog.c: No such file or directory` | 它依赖 `0300` 新建的文件 ⇒ **顺序是硬约束**：先 `0300`（建文件），再 `0243`（导出），最后 `0334b`（复位）。反过来打只会报「文件不存在」，不是「不适用」 |

结论：三条都不能「直接搬」，但只有 `0300` 需要真正的重切；`0243` 是丢一个 hunk + 改锚点；`0334b` 在 `0300` 落地后大概率干净应用。移植顺序由此定死：**0300 → 0243 → 0334b**，每条落地后单独 `check-kernel-console.py` / 符号量测，不合并成一次构建。

## `0300` 重切设计（2026-11-22 03:3x 实测三条）

读 16 线 `0300` 的两处插入 + 在 27 装配树上量三条事实：

1. **守卫是死的**：`0300` 两个 hunk 都包在 `#if defined(ARM64_BOARD_CONFIG_PONG)` 里，而 27 树的 `osfmk/arm/arm_init.c` 里 `ARM64_BOARD_CONFIG_PONG` 出现 **0** 次（机器配置是 `DEVELOPMENT_ARM64_BCM2837`）⇒ **原样打进去等于没打**，与 `0532`/`0546` 同一族（P-301）。重切时守卫必须去掉，改由运行期自我守卫（`0300` 的 `k60_usblog_init()` 本身就是只读探测，`k60_usblog_start()` 才有副作用）。
2. **`arm_init.c` 的锚点还活着**：16 线插在 `(void)pong_ramoops_console_init();` 之后；27 树该行在 **`arm_init.c:702`**（我们 `0546` 装的）⇒ 这个锚点可以直接用，且顺序天然正确（ramoops 先、usblog 后）。
3. **`bsd_init.c` 的锚点不存在**：16 线插在 `native_pong_ui_services_start();` 之后，该串在 27 树 `bsd/kern/bsd_init.c` 里出现 **0** 次 ⇒ 必须重新选点，判据是「线程已经能跑、且在此之前不会有人去枚举 USB」。候选点下一轮量（`bsd_init` 里 `vfs_mountroot` 成功之后、`init` 拉起之前）。

⇒ `0300` 重切 = 去掉两层守卫 + `arm_init.c:702` 原锚点 + `bsd_init.c` 换点。这一步不需要再「创新」，只是把 16 线的两处调用搬到 27 的两个新位置。

### `0300` 的 `bsd_init.c` 锚点已定（2026-11-22 03:3x）

27 树 `bsd/kern/bsd_init.c` 的 `bsd_autoconf()` 末尾本来就有和 16 线同形的块：

```c
	if (result == KERN_SUCCESS) {
		extern void qbt_k60_start(void);
		qbt_k60_start();
	}
	return result;
```

⇒ `k60_usblog_start()` 直接加在 `qbt_k60_start();` 之后、同一个 `if (result == KERN_SUCCESS)` 里。三个好处：①复用现成的成功守卫，不用新造条件；②它就在 `return result;`（`:1339`）之前，与 16 线的插入位置语义相同（线程已能跑、`init` 还没拉起）；③USB 枚举发生在这之后，不会有人提前抢 DWC3。

至此 `0300` 的两个锚点都定了：`osfmk/arm/arm_init.c:702`（复用）与 `bsd/kern/bsd_init.c` 的 `qbt_k60_start()` 之后（新选），守卫去掉。

## `0334b`（autoreset）的依赖链：不是「0300 之后就能打」（2026-11-22 实测）

`0334b-k60-autoreset.patch` 只改一个文件 `bsd/dev/k60_usblog.c`（184 行、4 个 hunk），
而 `0547`（0300）造出来的该文件只有 **1,349** 行，16 线那个版本有 **1,900+** 行。逐 hunk 用「尾随上下文是否在 0547 后的文件里」判：

| hunk | 尾随上下文 | 在 0547 的文件里 |
| --- | --- | --- |
| `@@ -186,6 +186,44 @@` | `* ->` | **在** |
| `@@ -337,7 +375,25 @@` | `register uint64_t x0 __asm__("x0") = 0x8400000…` | **不在** |
| `@@ -1540,6 +1596,80 @@` | `static void` | 在（但这种上下文太弱，不足以下结论） |
| `@@ -1779,6 +1909,28 @@` | `}` | 同上 |

`0x84000009` 是 PSCI `SYSTEM_RESET`，这段「按 conduit 发 SYSTEM_RESET」的 helper 在 16 线由
**`0308-k60-usblog-pong-capture-restart.patch`** 与 **`0311-k60-panic-restart-reason.patch`** 提供
（`grep -ln 0x8400000 patches/xnu/*.patch` 的命中），而 `0300` 本身不含它。

⇒ 正确顺序是 **`0300` → `0308`/`0311`（谁提供复位 helper 谁先）→ `0334b`**，不是「`0300` 之后就能打 `0334b`」。
这条不改也能通过 `git apply`（hunk 1/3/4 会硬塞进去），但塞进去后 `k60_autoreset_do_reset()` 会引用一个不存在的 helper ⇒ **链接期才炸**，正是 `0532` 那一族的形状。所以先补 helper、再打 autoreset，两步分开验。

## 复位原语的依赖图（2026-11-22 读 0308 原文）

`0334b` 要的「复位」不是一条指令，而是一条四段链：

```
0300  bsd/dev/k60_usblog.c 这个文件（0547 已造）
0308  k60_usblog_reset_to_fastboot()  —— 先发 restart reason，再 smc #0 SYSTEM_RESET，
                                       返回则再试 hvc #0，两次都返回才打印放弃
0311  k60_prime_restart(int)          —— 0308 的第一句就是它，负责把重启原因写进持久位置
0334b k60_autoreset_*                 —— 定时器/空闲判据，最后调 0308 那个函数
```

0308 的注释逐字写了一个关键事实：「**pong uses reboot_kernel(RB_QUICK) rather than a bare PSCI call:
the latter can simply return, which is what left this board sitting at the panic screen**」
⇒ 裸 `smc #0` 在**本板**可能直接返回（我已两次遇到「PSCI 调用返回而不复位」的记录），
所以 0308 才写成「smc 失败就 hvc，两次都失败才算失败」。

**decision（stage-0）**：解冻条件 ④「自动复位」按 **0300 → 0311 → 0308 → 0334b** 四步走，
每步单独 `apply --check` + 单独一次构建验证符号；不合并成一次。理由不是保守，而是这四个
文件互相引用（0308 调 0311 的函数、0334b 调 0308 的函数），任何一步漏了都只在**链接期**暴露。

## `0308` 不只是复位：它先写 SPMI/IMEM（HR-01 相关）

把 `0308-k60-usblog-pong-capture-restart.patch` 的 195 行新增段读完后，链的形状变了：

```
0311 提供 k60_prime_restart(int)  —— 实际定义就在 0308 这个补丁里（合并了）
0308 k60_usblog_reset_to_fastboot()
      ├─ k60_prime_restart(2)   → 先经 SPMI observer 写 IMEM 的 restart-reason 槽
      └─ smc #0 SYSTEM_RESET → 返回则 hvc #0 → 都返回才打印放弃
```

新增的静态量有 `k60_spmi_apid`、`k60_spmi_observer`、`k60_spmi_channel`、`k60_imem`
——即这段代码会在**复位之前对 SPMI observer 做写操作**。

这与 HR-01 的现行口径直接冲突（HR-01：默认关闭 SPMI/RSC 写入；只在 Data 挂载后允许
`pong_rail_probe=1` 的只读探测）。所以 stage-0 的自动复位不能原样搬，必须在两者之间选：

- **A（推荐）**：只搬复位那一半——把 `k60_usblog_reset_to_fastboot()` 的 SPMI/IMEM
  前置整段去掉，直接 `smc #0 SYSTEM_RESET`，返回则 `hvc #0`。代价：重启原因不落盘，
  下次启动看不到「为什么重启」；换来的是不碰 SPMI、不违 HR-01。
- **B**：整段搬，并向用户申请一次 HR-01 豁免（写 IMEM 的 restart-reason 槽）。
  收益是下次启动能读到原因码；代价是引入一处 SPMI 写路径，且它在 `bsd_init` 之后、
  Data 挂载之前就会跑。

**未决定**，留给用户裁；在此之前不动 0308。

### 裁决（2026-11-22，不再等外部确认）：走 A，只搬复位，不搬 SPMI 记录

证据（`patches/xnu/0308-k60-usblog-pong-capture-restart.patch` 逐行读）：

- `:103` `k60_prime_restart(int target)` 单独成函数，职责是**记重启原因**：`:129-133` 映射
  `K60_SPMI_OBSERVER_PA` / `K60_SPMI_CHANNEL_PA + apid*4096` / `K60_IMEM_PA`，
  `:144` 写 `k60_spmi_channel + 0x10`，`:92-98` 再经 observer 读回校验。
- 复位本身在 `k60_usblog_reset_to_fastboot()` 里，与上面的写无关：`smc #0`（SYSTEM_RESET），
  返回则 `hvc #0`，两次都返回才放弃（`:26` 注释说明为什么不用裸 PSCI：裸调用可能直接返回，
  该板曾因此停在 panic 屏幕）。
- 因此 **A 不是降级**：把 `k60_prime_restart()` 换成只写一个静态变量（或直接不调用），
  复位路径完全不变，唯一损失是"重启原因"不落盘——而原因这件事本来就要等日志通路可用后才谈。
- 不选 B 的理由不只是 HR-01：SCMI/SPMI 写发生在**复位前**，一旦写错就是"想复位结果写坏一条总线"，
  而这条通路在 stage-0 没有任何观测手段能证明它成功（P-300 的同族问题）。

落地顺序：`0547`（已落）→ **`0549`：`k60_usblog_reset_to_fastboot()` + 静态原因** → `0334b`（触发时机）。

## 2026-11-22 06:33 — `0334b`（自动复位触发）不能搬，要重写，理由与落点

逐 hunk 比对 `patches/xnu/0334b-k60-autoreset.patch` 与我们 27 侧已有的文件，四处 hunk 全部落空：

| 0334b hunk | 需要的上下文 | 我们树里的情况 |
| --- | --- | --- |
| `@@ -186,6 +186,44 @@` | 16 线 `k60_usblog.c` 第 186 行附近（`k60_autoreset_arg()` 插在 `}` 与 `/\* 0319: Pong-style restart reason` 之间） | `0547` 造的文件 1,338 行，没有那段注释，行号与上下文都不在 |
| `@@ -337,7 +375,25 @@` | `delay(1500000);` 与 `register uint64_t x0 __asm__("x0") = 0x84000009u;`（在 `k60_prime_restart` 的 SPMI 前置里） | 我们按裁决 A **故意没搬** SPMI/IMEM 前置，`0549` 里复位是 `k60_usblog_reset_to_fastboot()`，没有这段 |
| `@@ -1540,6 +1596,80 @@` | `printf("K60 USBLOG: restart reason %s\n", primed ? "published" : "FAILED to publish");` | 同一个原因：`published/FAILED` 这对字串只在 SPMI 版本里 |
| `@@ -1779,6 +1909,28 @@` | 16 线文件尾的 `{ return us >= 4; }` 之类弱上下文 | 同样不存在 |

⇒ **不是上下文偏移，而是依赖了我们已经决定不搬的那半**。硬搬等于把 SPMI 写重新引回内核（HR-01 冲突 + stage-0 无法观测），得不偿失。

**重写方案（落点已定，下一轮切补丁并构建）**：

- 新文件 `bsd/dev/k60_autoreset.c`，只做三件事：
  1. `PE_parse_boot_argn("k60_autoreset", …)` 与 `"k60_autoreset_idle"`（两个名字与 16 线保持一致，`board.toml` 启动行里 `k60_autoreset=300` 已经带着它们，不新增字节）；
  2. 用 `kernel_thread_start()` 起一个线程，先 `delay()` 到空闲阈值，再循环轮询空闲秒数；
  3. 到点调 `k60_usblog_reset_to_fastboot()`（`0549` 已定义并已被符号表证实）。
- 唯一要改的现有文件是 `bsd/kern/bsd_init.c`，锚点 `k60_usblog_start();`（`0547` 在 `@@ -1334,7 +1334,11 @@` 里加的，实测存在于补丁第 1368 行，全树唯一），调用 `k60_autoreset_start();`。
- `patches/xnu-12377/conf-files.txt` 加一行 `bsd/dev/k60_autoreset.c		standard`。
- 切补丁方式：**仍用生成脚本**（`E:/k60-work/scratch/cut_autoreset_v27.py`，仿 `cut_ep0_v27.py`），因为要改新增行计数（P-155），手写 hunk 已咬过多次。
- 判据（先写死）：`== kernel: patch 0550`、`llvm-nm` 有 `_k60_autoreset_start`、`strings kernel.macho | grep -c "k60_autoreset"` ≥ 1、`check-image-args.py` 仍 OK、prelink 两数仍 94/203。
- 不使用 `0311`：`0311` 是 restart-reason 名字表，而裁决 A 已决定原因记静态变量；引入它只会把 SPMI 前置再拉回来。
