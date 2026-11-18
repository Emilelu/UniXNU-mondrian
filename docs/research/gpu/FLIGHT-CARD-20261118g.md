# 上机卡 20261118 / gpu-stages：把每帧耗时拆成三段

## 1. 目的

`usblog-20261118-131041` 实测每帧「in the driver」20,397–88,584 µs，而
`waiting for the GPU`（`MiniIOSurfaceDrawn` 等待）恒 1 µs、`presenter` 全为 GPU。
也就是说 20–40 ms 里到底有多少是页准备、多少是渲染线程取帧、多少是 GPU 拷贝，
现在**无法归因**。

官方 GPU 文档「定位慢帧的耗时」一节要求把帧路径按阶段拆开记录。这张镜像只做这件事：
在 `pong_scanout_frame()` 里记录 `prepare`（`IOSubMemoryDescriptor::withSubRange` +
`prepare()` 锁页）与 `offer_and_copy`（发出 offer 到 `PongScanoutComplete` 返回），
在渲染线程 `serve()` 里记录 `wait`（`PongScanoutWait` 调用）、`copy`
（`presenter->present()` 含 `waitUntilCompleted`）、`done`（`PongScanoutComplete` 调用）。

不改行为、不改判据门限、不改 Metal 侧。

## 2. 前提证据（都在镜像之前产生）

| 编号 | 事实 | 出处 |
| --- | --- | --- |
| P1 | 上一飞每帧驱动耗时 20,397–88,584 µs，GPU 等待恒 1 µs | `evidence/usblog-20261118-131041/console.log` 的 `frames in … ms (…)` 行 |
| P2 | 该飞 `presenter GPU` 8 次 / `presenter CPU` 0 次 | 同上 `presenter %s` 行 |
| P3 | 该飞 `scanout frames=` 13 行，首 60 帧 @101.281 s → 末 780 帧 @193.669 s | 同上；算得 7.79 fps |
| P4 | 内核侧三处时间戳在真实工作两侧 | `scripts/tests/test-frame-stage-timing.py` 6 例 |
| P5 | 内核报 `prepare=%llu us offer_and_copy=%llu us`，渲染线程报 `wait/copy/done` | 同上测试第 1、3 例 |
| P6 | 两处报告都按 60 帧采样，不是每帧 | 同上测试第 5 例；内核 `(completed<=4 \|\| !(completed%60))` |
| P7 | 桥接层（含 0013）与上一飞同一二进制 | `metal-bridge-20261118d` 未重建，只重打插件 bundle |

## 3. 抓取

- 镜像：`gpu-stages-20261118`
- 命令：`scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`
- 只看 `console.log`；`capture.json` 的 `complete` 必须为真

## 4. 判据

**S1** `K60KEXC` 命中 0（内核没异常）。
**S2** `PONG SCANOUT: frame=` 至少 5 行（内核三段计时真的在跑）。
**S3** `last frame: wait=` 至少 1 行（渲染线程三段计时真的在跑）。
**S4** 同一行内 `prepare + offer_and_copy` 之和与 `total` 相差不超过 10%（数字自洽，
不是把别处的耗时算进来）。
**S5** 存在 `scanout frames=` 行（画面确实还在出帧，不是靠软件合成兜底假装通过）。

**F1** `K60KEXC` 命中 > 0 ⇒ 计时改动引入异常。
**F2** 没有 `PONG SCANOUT: frame=` 行 ⇒ 内核侧计时没编进镜像（看 `strings kernel.macho`）。
**F3** 没有 `last frame: wait=` 行 ⇒ 插件 bundle 没换成带计时的版本（查 bundle sha 与
`stage-metal-plugin.sh` 的日志）。
**F4** `prepare` 单段占 `total` 一半以上 ⇒ 瓶颈在锁页，下一步查
`IOSubMemoryDescriptor::prepare()` 与 surface 页的来源，而不是 GPU。
**F5** `offer_and_copy` 减去渲染线程 `copy` 后仍占 `total` 一半以上 ⇒ 瓶颈在 offer
交接（`IOLockSleepDeadline` 与唤醒），不是 GPU 也不是锁页。
**F6** 渲染线程 `copy` 占 `total` 一半以上 ⇒ 瓶颈在 `presenter->present()`
（含 `waitUntilCompleted`），下一步查 GPU 拷贝本身与 `TU_DEBUG=sysmem` 的分块策略。
**F7** `capture.json` 的 `complete` 为假或 `crashed: backboardd` > 0 ⇒ 抓取无效/回归，本轮结论作废。

## 5. 结果登记

（判决在出帧后填写，不在镜像之前填。）
