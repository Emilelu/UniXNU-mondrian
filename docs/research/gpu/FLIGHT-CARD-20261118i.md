# 上机卡 · `gpu-split-20261118`：把 16.8 ms 的扫描输出拷贝拆成 encode / submit / GPU 三段

> **状态：HOLD，未上机，且不得再上机。** 本卡挂着 `gpu-split-20261118` 这个镜像，
> 但那张镜像带的是**跨帧导入缓存**（见 `FLIGHT-CARD-20261118h.md` 的 HOLD 说明），
> 而本卡 S4 的「三段之和落在 `copy` 的 ±20% 内」在当时也不可能通过：`_k60Us()` 对
> 跨整秒的 `tv_nsec` 差做了无符号强转，任何跨秒的跨度会被算成 ~1.8e13 µs。另外本卡
> 只把 encode+submit+gpu 与 `copy` 相比，漏掉了 `import` 与清理，所以「行为零改动」
> 这句在当时就不成立。判据已被 `FLIGHT-CARD-20261118j.md` 取代，本卡仅保留为
> 阶段拆分方法的出处。

## 1. 目的

上一飞（`gpu-stages-20261118`，证据 `usblog-20261118-135714`）把整帧成本定位到
`presenter->present()`：锁页 4–12 µs、交付 38–55 µs、而 `copy` 16,813–19,833 µs。
官方 GPU 移植页要求把慢帧归到具体阶段（「提交到 GPU 完成」与「运行时 commit 到提交」
是两个不同的责任方），一个 `copy=` 数字分不开它们。

本飞在 `present()` 内用四个时钟把同一段拆成三段：**encode**（建 command buffer +
blit 编码）、**submit**（`commit` 返回）、**gpu**（`waitUntilCompleted` 返回）。
行为零改动，只增加三个计时量与三个报告字段。

要回答的问题：18.4 MB（1440×3200×4）的整屏拷贝耗时 16.8 ms，是**我们排队的方式贵**
（encode/submit 占大头 ⇒ 每帧一次额外命令提交的固定开销），还是**GPU 真的慢**
（gpu 段占大头 ⇒ 1.1 GB/s 的搬运确实在硬件上跑不快）。

## 2. 前提证据（镜像之前）

| # | 证据 | 值 |
| --- | --- | --- |
| P1 | `drivers/PongMetal/GpuScanoutPresenter.h` 四个时钟位置 | `e0` 在建 `MTLCommandBuffer` 之前、`e1` 在 `[blit endEncoding]` 之后、`e2` 在 `[commands commit]` 之后、`e3` 在 `[commands waitUntilCompleted]` 之后 |
| P2 | 三个跨度都从相邻时钟对推导 | `lastEncodeUs_=_k60Us(e0,e1)`、`lastSubmitUs_=_k60Us(e1,e2)`、`lastWaitUs_=_k60Us(e2,e3)` |
| P3 | 守卫测试 `scripts/tests/test-present-stage-split.py` | 13 例全过 |
| P4 | 既有守卫仍过 | `test-presenter-import-cache.py` 7 例、`test-frame-stage-timing.py` 6 例 |
| P5 | 报告行 | `… imports=%llu reuses=%llu import=%llu us; encode=%llu us submit=%llu us gpu=%llu us`，`char rate[448]` |
| P6 | 拷贝路径未改 | 等 pitch 仍是单次 `copyFromBuffer…size:frame.stride * (frame.height - 1) + row`；不等 pitch 仍走线性纹理 |
| P7 | 上一飞的实测基准 | `copy=19833/16813 µs`、`wait=14171/118 µs`、`done=55/38 µs`；帧率 0.9–7.79 fps |

## 3. 抓取

- 镜像目录：`E:/k60-work/artifacts/gpu-split-20261118`
- 命令行必须含 `pong_metal=1 pong_gpu_scanout=1 sheng-gpu-addon=1`
- 抓取 240 s，证据落 `E:/k60-work/evidence/usblog-<ts>/`

## 4. 判据

**S1** `K60KEXC` = 0，且 `capture.json` 的 `complete` 为真。
**S2** 至少一行报告同时带 `encode=`、`submit=`、`gpu=` 三个字段（证明本镜像的插件用的是新计时）。
**S3** 出现 `presenter GPU`，且 `crashed: backboardd` = 0（画面仍由 GPU 交付、系统仍稳）。
**S4** 结论可判定：三段之和落在 `copy` 的 ±20% 内（给定 `copy` 是同一段的外层计时），据此把 ≥55% 的一段落成根因。

**F1** 出现 `K60KEXC` 或 panic。
**F2** 有报告行但没有 `encode=`/`submit=`/`gpu=`（插件没换新，本飞无效）。
**F3** `presenter GPU` 消失而只剩 `presenter CPU`（说明退化成软件合成）。
**F4** `crashed: backboardd` > 0。
**F5** 三段之和与 `copy` 相差超过 50%（外层与内层不在量同一件事，先修计时再谈结论）。
**F6** 抓取不完整（`complete` 为假）。

## 5. 结果登记

（判决在镜像产出并上机之后填写；本卡在镜像之前写成。）
