# 上机卡 20261118 / gpu-import：源缓冲导入缓存与导入计时

## 1. 目的

`usblog-20261118-135714`（`gpu-stages-20261118`）把每帧拆开后给出决定性数字：

| 段 | 实测 | 结论 |
| --- | --- | --- |
| 内核 `prepare` | 4–12 µs | 锁页不是瓶颈 |
| 渲染线程 `done` | 38–55 µs | 交付不是瓶颈 |
| 渲染线程 `copy`（`presenter->present()`） | **16,813–19,833 µs** | 全部成本在这里 |
| 内核 `offer_and_copy` | 13,296–37,320 µs | 与 `copy` 同阶，说明内核在等这一次拷贝 |

18.4 MB（1440×3200×4）在 16.8 ms 里搬完 ≈ **1.1 GB/s**，远低于 A730 blit 的
预期带宽。`present()` 每帧都调 `newBufferWithBytesNoCopy` 重新导入同一批 surface 页，
而 2026-11-18 早先的日志里曾出现单飞 25,149 次逐页 `IOMemoryDescriptor` 映射记录
—— 这与「导入贵、blit 便宜」的假设一致。

这张镜像做两件事，**不改帧路径的语义**：

1. 按 `(base, bytes)` 缓存上一次的源导入；页面不变时直接复用，不再重新映射。
2. 记录导入耗时（`import=%llu us`）与导入/复用次数（`imports=`/`reuses=`），
   让下一次飞行能直接判定「贵在导入还是贵在 blit」。

## 2. 前提证据（都在镜像之前产生）

| 编号 | 事实 | 出处 |
| --- | --- | --- |
| P1 | 每帧 `copy` 16,813–19,833 µs，`prepare` 4–12 µs，`done` 38–55 µs | `evidence/usblog-20261118-135714/console.log` 的 `PONG SCANOUT: frame=` 与 `last frame: wait=` 行 |
| P2 | `presenter GPU` 出现、`presenter CPU` 0 次 | 同上 |
| P3 | 该飞 `scanout frames=180 at 201.523 s`，`crashed: backboardd` 0 | 同上 |
| P4 | 缓存键是页面指针与长度两者，且导入被计时、计数 | `scripts/tests/test-presenter-import-cache.py` 7 例 |
| P5 | 二进制为 ARC（`-fobjc-arc`），旧导入由强引用赋值释放，不发 `release` | 同上第 2 例；`scripts/build-pong-metal-plugin.py` 的命令行 |
| P6 | 插件由当前源码重编，不是旧 bundle | 构建日志的 `BUILD_EXIT=0` 与 bundle 内 `strings \| grep -c "reuses="` = 1 |
| P7 | 内核侧不变（本卡只改插件 bundle） | `git diff` 只含 `GpuScanoutPresenter.h`、`PongMetalScanout.h`、测试 |

## 3. 抓取

- 镜像：`gpu-import-20261118`
- 命令：`scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`
- 只看 `console.log`；`capture.json` 的 `complete` 必须为真

## 4. 判据

**S1** `K60KEXC` 命中 0（内核没异常）。
**S2** `last frame: wait=` 至少 1 行，且该行含 `imports=` / `reuses=` / `import=` 三个字段
（带导入计时的插件真的上了机）。
**S3** `reuses` 随帧数增长（同一批页面被复用），即末条 `reuses=` 明显大于 `imports=`。
**S4** 末条 `last frame: copy=` 小于 16,813 µs（上一飞的最小值），即拷贝这一段真的变快了。
**S5** `scanout frames=` 仍在增长，且 `crashed: backboardd` 为 0（没有为了变快而丢帧或崩）。
**S6** 从首条与末条 `scanout frames=N at T s` 算出的帧率高于上一飞的 7.79 fps。

**F1** `K60KEXC` > 0 ⇒ 缓存改动引入内核异常。
**F2** 没有 `imports=` 字段 ⇒ 带计时的插件没上机（查 bundle sha 与 `stage-metal-plugin.sh` 日志）。
**F3** `imports=` 等于帧数（每次都是新导入）⇒ 页面每帧都在变，缓存假设不成立，
下一步改为按页面集合的多槽缓存或让合成器固定 surface。
**F4** `import=` 单帧超过 `copy` 的一半，而 `copy` 没有下降 ⇒ 导入计时把开销记在了
错误的位置（或缓存未命中），需要重新核对 `present()` 的时间戳边界。
**F5** `copy` 没有下降但 `reuses` 在增长 ⇒ 贵在 blit 本身而非导入，
下一步转向 `TU_DEBUG=sysmem` 与 blit 的路径（官方默认是 `gmem,nocb`）。
**F6** `crashed: backboardd` > 0 或 `capture.json` 的 `complete` 为假 ⇒ 抓取无效，本轮结论作废。

## 5. 结果登记

（判决在出帧后填写，不在镜像之前填。）
