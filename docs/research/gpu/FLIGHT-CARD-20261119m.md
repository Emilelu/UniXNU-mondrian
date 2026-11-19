# 飞行卡 m — `gpu-bench2-20261119`：bench 循环是否真的跑起来

## 1. 为什么飞

卡 l 的飞行（`usblog-20261119-170653`）给出了 `gpu 2,935 µs`（卡 j 是 5,983），但
`bench samples: 0`：我把 bench 循环插进了 `if(context->blitProbe && runBlitProbe(...))` 的
**内部**，而 `blitProbe` 默认关，于是循环一次都没进。那张卡因此只能靠「屏幕上恰好有动画」的
stage 行取样 —— 这正是 P-247 要消灭的依赖。

本卡只问一件事：把循环移到 `blitProbe` 分支之外以后，静止屏能不能自己产出样本。

## 2. 改了什么

- `drivers/PongMetal/PongMetalScanout.h`：bench 块整体移到 `if(...blitProbe...) / else if(...)`
  链**之后**、外层 `if(!copies && result==kOk)` 之内；仍然在 `PongScanoutComplete` 之前，
  所以页还是客户端刚给的那一批。
- `scripts/tests/test-gpu-perf-vote.py` 新增 `bench_not_inside_the_control_branch`
  （断言 `if(context->bench)` 出现在 `scanout blit control could not run` 之后，
  且在 `lastCopy=span(t1,t2)` 之前）。

## 3. 前置条件

- P1 镜像 `gpu-bench2-20261119`，args 含 `gperf=13`（31 条 / 605 B）。
- P2 插件 bundle 里 `strings` 能查到 `scanout bench n=` 与 `gperf=`。
- P3 内核串能查到 `GPU level vote from gperf`。
- P4 `K60_AGENT_ID` 已设，设备在 fastboot 或 adb。

## 4. 判据

**S1** 六类 fault（`panic(` / `K60KEXC` / `crashed: backboardd` / `DeviceLost` /
`CP/SMMU fault` / `GPU copy not retired`）各 0 行。
**S2** `scanout bench n=` 至少 8 行，且每条 `status=0x0`。
**S3** bench 的 `gpu` 中位 < 3,000 µs。
**S4** bench 的 `sum` 中位 < 6,000 µs。
**S5** bench 的 `import` 中位 < 200 µs。
**S6** 面板 `te` ≥ 110/s。
**S7** `GPU level vote from gperf` 至少 1 行且 `a` = 13。

**F1** bench 0 行 ⇒ 循环仍未执行，先看 `blitProbe` 路径再看构建产物，不许改判据。
**F2** bench 全 `status!=0x0` ⇒ 拷贝本身坏了，回滚 bench 再看真实路径。
**F3** bench `gpu` ≥ 5,000 µs ⇒ 档位不是限制项，转向 `submit`。
**F4** 出现 `DeviceLost` ⇒ 按 P-244 判 INVALID，不得用本次数字谈帧率。
**F5** 零帧且无 bench 行 ⇒ INVALID。

## 5. 结果登记

- criteria-sha256: deee9c1d074252859125e9a6e98674737648f2a94c49ffe734373daa4f42086e
