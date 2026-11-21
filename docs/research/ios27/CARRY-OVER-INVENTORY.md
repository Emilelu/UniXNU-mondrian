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
