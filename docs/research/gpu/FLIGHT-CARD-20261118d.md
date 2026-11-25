# 上机卡：gpu-cbtrace-20261118

镜像目录：`E:/iOS Port/Work/artifacts/gpu-cbtrace-20261118`

## 1. 目的

判定 backboardd 在 Metal 路径上走到哪一步就停：是否请求 command buffer、是否 present、是否进入 draw、是否 commit。
只加三条「首次发生」日志（`K60CB`、`K60DRAW`），不改行为。

## 2. 前提证据

- `scripts/tests/test-metal-cb-trace.py` PASS：`K60CB first command buffer requested` 与 `K60CB first presentDrawable` 各一条，分别在工厂方法与 `presentDrawable` 内，`gCommits.fetch_add` 仍只有一处。
- `scripts/tests/test-metal-draw-trace.py` PASS：`K60DRAW enter/leave` 包住 `nmb_render_draw`。
- 前两飞对照：`usblog-20261118-101832` 是 B 变体（`D2 F1 M4500`、`c0/0`、卡死）；`usblog-20261118-105506` 是 C 变体（`D0 F0 M18`、软件出帧）。

## 3. 抓取

`scripts/flash.sh <boot.img> 240`，证据落 `E:/iOS Port/Work/evidence/usblog-<ts>/`。

## 4. 判据

**S1** `K60KEXC` 计数为 0。
**S2** 出现 `K60CB first command buffer requested`。
**S3** 出现 `K60CB first presentDrawable`。
**S4** `Pong Metal: S …` 的 `c` 第一段大于 0。
**S5** `crashed: backboardd` 计数为 0。

**F1** 内核异常中断抓取。
**F2** 无 `K60CB first command buffer requested` —— backboardd 从未向 Metal 申请 command buffer。
**F3** 有 CB、无 `K60CB first presentDrawable` —— 建了缓冲但未进入 present 路径。
**F4** 有 CB 与 `K60DRAW enter`、无 `K60DRAW leave` —— 卡在 `nmb_render_draw` 内部。
**F5** 有 CB 与 present、但 `c` 仍为 0 —— 卡在 commit 之前。
**F6** `Pong Metal: S …` 缺失 —— 插件未装载。

## 5. 结果登记

（上机后填写）
