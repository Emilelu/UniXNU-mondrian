# 16 线资产清点：迁移到 iOS 27 时我们丢了什么

日期：2026-11-22
触发：用户两次质问——「自动复位代码在 ios16 的时候都有了，现在你又要重复造轮子？」「迁移到 iOS 27 你是完全把之前各种代码全丢了？」

## 事实（机器可核，不是印象）

| 项 | 数值 |
| --- | --- |
| iOS 16 系列条目（`patches/xnu/series`） | **240** |
| iOS 27 系列条目（`patches/xnu-12377/series`） | **34** |
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
