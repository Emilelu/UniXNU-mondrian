# 飞行卡 l：把 blit 的测量从「屏幕上有没有动画」里解耦出来

- **镜像**：`gpu-bench-20261119`
- **日期**：2026-11-19
- **依赖**：卡 k 已证明 GX 档能投到 13（`result=0 a=0xd b=0x2`），本卡只测「投了之后到底快不快」

## 1. 为什么还要飞

卡 k 的飞行 `usblog-20261119-163734` 屏幕静止，只有 4 帧、0 条稳态 stage 行，按 P-236 判
INVALID —— 升档有没有用**没测到**。同样的事已经发生三次（`095547` 4 帧、`163734` 4 帧）。
判据依赖「设备上恰好有东西在动」不是判据，所以这一飞让驱动自己把同一次拷贝重复 24 次：

```
scanout bench n=<i>/24 import=… encode=… submit=… gpu=… sum=… status=0x…
```

重复发生在**第一帧真实拷贝成功之后、内核 retire 映射之前**，用的是客户端真交给我们的那批页，
所以测的仍然是同一次工作，只是不再需要屏幕帮忙。

## 2. 改了什么

| 文件 | 改动 |
|---|---|
| `drivers/PongMetal/PongMetalScanout.h` | `Context` 加 `bench`；见到 `gperf=` 时 `bench=24`（`gbench=N` 可覆盖，上限 120）；首帧成功后循环 `present()` 并逐次打印 bench 行；`status` 非 0 立即中止 |
| `scripts/judge-gpu-perf.py` | 优先用 bench 行取中位；有 ≥8 条 bench 样本时允许屏幕静止（否则仍要求 ≥5 帧） |

## 3. 前置条件

- P1 插件里必须有 `scanout bench n=`（`strings PongAdrenoMetal`）
- P2 图像命令行 31 条 605 B，含 `gperf=13`
- P3 `image-arg-audit: OK`、`verify-boot-image: OK`
- P4 设备在 fastboot

## 4. 判据

### 4.1 有效性

- **V1** ≥8 条 bench 行且其中 ≥8 条 `status=0x0`；或 ≥20 条稳态 stage 行
- **V2** 至少 1 条 `MiniIOMobileFramebuffer: N frames`（必须有帧被真正提供过）
- 不成立 ⇒ INVALID（P-236），`DeviceLost` 出现也判 INVALID（P-244）

### 4.2 成功判据

- **S1** 无 fault 行（同卡 k 的六条）
- **S2** bench 行 ≥8 条且全部 `status=0x0`
- **S3** bench 中位 `gpu` **< 3,000 µs**（卡 j 真实路径 5,983 µs）
- **S4** bench 中位 `sum` **< 6,000 µs**（卡 j 8,281 µs）
- **S5** bench 中位 `import` **< 200 µs**（每帧导入；卡 j 51 µs 量级）
- **S6** 面板 `te` ≥110/s
- **S7** 投票行 `a` = 13

### 4.3 失败规则

- **F1** bench 行 0 条 ⇒ 插件没这个代码或 `gperf` 没进命令行；先查 P1/P2，不得读成「基准没用」
- **F2** bench 全部 `status` 非 0 ⇒ 重复的拷贝本身失败，先看第一条的 status 与 `GPU scanout copy failed` 行
- **F3** bench `gpu` 中位 ≥5,000 µs ⇒ 档位不是限制项；下一步是 fence 串行化 / vblank 排队 / 读回真实频点
- **F4** `DeviceLost` 或 `CP/SMMU fault` ⇒ INVALID（P-244），不得以帧率为结论
- **F5** 零帧 ⇒ INVALID（P-236）

## 5. 结果登记

（飞行后写）
