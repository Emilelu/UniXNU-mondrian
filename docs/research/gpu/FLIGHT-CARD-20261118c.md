# 上机卡：gpu-drawtrace-20261118

镜像目录：`E:/k60-work/artifacts/gpu-drawtrace-20261118`

## 1. 目的

判定 Metal 客户端是否卡死在 `nmb_render_draw`（Rust runtime 入口）内部。只加了 2 行 `K60DRAW` 日志，不改行为。

## 2. 前提证据

- `scripts/tests/test-metal-draw-trace.py` PASS（进/出各一条、包住 `nmb_render_draw`、只前 4 个 draw）。
- 上一飞 `usblog-20261118-101832`：`c0/0`、`D2`、`F1`、`M4500`、5,517 次 `IOMemoryDescriptor` 映射，抓取预算 240 s 结束时仍在刷屏。
- 内核、payload、ADT、命令行哈希记录在 `build-manifest.json`。

## 3. 抓取

`scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`。

## 4. 判据

**S1** `K60KEXC` 计数为 0。
**S2** 出现 `K60DRAW enter` 至少 1 次。
**S3** 出现 `K60DRAW leave` 至少 1 次。
**S4** `Pong Metal: S …` 中 `c` 的第一段大于 0。
**S5** `crashed: backboardd` 计数为 0。

**F1** 出现内核异常导致抓取中断。
**F2** 有 `K60DRAW enter` 但全程没有 `K60DRAW leave` —— 确认卡在 `nmb_render_draw` 内部。
**F3** 有 `K60DRAW leave` 但 `c` 仍为 0 —— 卡点在 encode 之后、commit 之前。
**F4** `Pong Metal: S …` 行完全缺失 —— 插件未装载。
**F5** `crashed: backboardd` 大于 0。

## 5. 结果登记

（上机后填写）
