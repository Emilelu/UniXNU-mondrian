# 飞行卡 d：`gpu-blitprobe-20261119` —— 同一个 18.4 MB，两个不同的目标

状态：**判据先写（本文件先于镜像提交）**。飞行前不得修改下面 §4 的任何阈值。
上游：`FLIGHT-CARD-20261119c.md`（遥测飞行，`usblog-20261119-055934`）的 §5.5 第 2 条。

## 1. 为什么飞

上一飞把墙定到了一个具体操作上，但没能说是哪一环慢：

| 判据 | 实测（`usblog-20261119-055934`） |
|---|---|
| `rp0 dr0 bl1`（零渲染 pass、只有一次 blit）的 `ctc` | 5.3 / 10.6 / 16.8 / 22.8 ms |
| 内核侧 `gpu=` | 12,593 µs |
| 客户端 `G commit-to-complete mean` | 21,928–23,515 µs |
| 合成器 `us each in the driver` | 13,483–23,589 µs |

18.4 MB / 12.6 ms = 1.5 GB/s，而 A730 的带宽是 50 GB/s 量级。同一个拷贝形状在
zizhan 上是 5–6 ms。三处测量都只说了「这一次拷贝慢」，没有一个能区分：

- **目标端**：固件帧缓冲是 `newBufferWithBytesNoCopy` 导入的物理地址映射，可能不可缓存；
- **拷贝实现**：Turnip 可能把这个调用降成着色器渲染而不是 DMA；
- **带宽本身**：GPU 频率或链路速率低。

这一飞用同样的 API 形状、同样的字节数、只换目标端，把三者分开。

## 2. 这一飞改了什么

只有 `drivers/PongMetal/GpuScanoutPresenter.h` 与 `drivers/PongMetal/PongMetalScanout.h`：

- 新增 `Presenter::runBlitProbe(frame)`：在第一帧真实拷贝成功之后，用**同一个**
  `timedCopy()`（一次 `copyFromBuffer` + `commit` + `waitUntilCompleted`）再拷两次同样的字节：
  ① 客户端 surface → GPU 自行分配的同尺寸缓冲（`src-to-device`）；
  ② 该缓冲 → 固件帧缓冲（`device-to-scanout`）。
- 只跑一次（`probeRan_`），跑在 `PongScanoutComplete` 之前（之后内核会释放帧映射，源页已失效），
  跑在 `t2` 之后（所以 `copy` 仍然只量 `present()`，不会把对照的 25 ms 算进上一张卡的数字）。
- 输出一行：`scanout blit control bytes=<n> src-to-device=<a> us device-to-scanout=<b> us`。
- 默认开、可用 `pong_gpu_blit_probe=0` 关：启动行已用 596 / 607 字节，加 21 字节会超上限。

已知副作用：当 `frame.stride != scanout_.stride` 时，`device-to-scanout` 那一次是按源 pitch
单次搬的，写进固件帧缓冲的**那一帧**行错位，呈斜切状。它发生在开机第一帧，
SpringBoard 下一次合成就会覆盖。若这一帧之后屏幕**仍然**是斜的，见 F6。

## 3. 前置条件（缺一不飞）

- P1 `wsl -u root -e bash -lc '… scripts/build-strict.sh gpu-blitprobe-20261119 …'` 退出码 0。
- P2 `image-arg-audit: OK (30 arguments, 596 bytes)`。
- P3 插件 bundle 里必须有下面三条字符串（否则探针没进 bundle —— 这三行由
  `PongAdrenoMetal` 输出，**不是**内核；上一张卡在这里写错过一次）：
  `scanout blit control bytes=%zu src-to-device=%llu us device-to-scanout=%llu us`、
  `scanout blit control could not run`、`pong_gpu_blit_probe=0`。
- P4 `python3 scripts/queue-flight.py` 保持 `K60_AGENT_ID` 署名；设备在 fastboot。
- P5 `✅ flight card: … written before gpu-blitprobe-20261119`。
- P6 本条卡的 `criteria-sha256` 已钉入 §5（重飞只许重复判据，不许改阈值）。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

必须三项同时成立，否则整飞记 **INVALID**，不算任何 F 规则命中：

1. 至少一条 `MiniIOMobileFramebuffer: … N frames in …` 且 N ≥ 1；
2. 至少一条 `Pong Metal: c<n>/0 d<n>` 且 n ≥ 1；
3. 至少一条 `scanout frames=` 行。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`。
- **S2** 恰好一行 `scanout blit control bytes=`。
- **S3** `src-to-device` 与 `device-to-scanout` 两个数都 **非零**（零 = 那次拷贝失败，不是很快）。
- **S4** 形状行仍是 `scanout copy texture untile`，且 `imports==frames` 每一行都成立。
- **S5** 记录下三个数：本飞的 `copy` 中位、`src-to-device`、`device-to-scanout`。
- **S6** 面板仍在 120 Hz 档（`after the UI frame te` ≥ 110/s）。
- **S7** 仍在出帧（`scanout frames=` 至少两次采样）。

### 4.3 失败规则（命中即按分支走，不许「再看看」）

- **F1** 出现 panic / `K60KEXC` / `crashed: backboardd` ⇒ 立即回滚整个探针，
  下一飞加 `pong_gpu_blit_probe=0` 确认能恢复到上一飞的行为。
- **F2** 没有 `scanout blit control` 行，但**有** `scanout copy` 行 ⇒ 探针没跑到
  （`context->blitProbe` 为假、或 `runBlitProbe` 提前返回）。先查 P3 的两条字符串，
  不要把它读成「对照很便宜」。
- **F3** 两个数都 ≥ 5 ms 且相差不到 2 倍 ⇒ 目标端与实现都不是主因，
  慢在**全局**（带宽 / GPU 频率 / 不可缓存）。下一步是读 GPU 实际频率，不是换目标。
- **F4** `src-to-device` ≤ 2 ms 而 `device-to-scanout` ≥ 8 ms ⇒ **固件帧缓冲是慢的那个**。
  下一步转 zizhan 的 `target`（把画面拷进面板缓冲而不是固件帧缓冲），
  零拷贝扫出则升为唯一根治方向。
- **F5** `src-to-device` ≥ 8 ms ⇒ **拷贝实现是慢的那个**（Turnip 把它降成了着色器或其他非 DMA 路径）。
  下一步是在同一飞里用 `memcpy` 量一次 CPU 侧的 18.4 MB 作为下限，并考虑绕开
  纹理路径、直接用能落到 `CP_MEMCPY` 的调用形状。
- **F6** 屏幕在第一帧之后仍呈斜切/错位 ⇒ 这一飞的画面判据作废，
  下一飞加 `pong_gpu_blit_probe=0`，并改法：把 `device-to-scanout` 换成按
  `scanout_.stride` 逐行搬（形状改变要重新写判据，不许偷偷换）。

## 5. 结果登记

（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入。）

- criteria-sha256: `28bc85968a223c8eae70745f2261e073002641e5c588ee20201fb45ef87f6897`

### 5.1 第一次飞（`usblog-20261119-064122`）：**F2 命中，对照没跑**

镜像 `gpu-blitprobe-20261119`（`boot.img db77a632…`、kernel `dcbed46f…` 105,693,184 B、
插件 `metal-plugin-20261119n` 的 `PongAdrenoMetal` 111,808 B sha256 `dfbcf147…`）。
证据 246,704 B，`supervisor rc=0`，抓取完整、无 panic、无复位。

| 判据 | 结果 | 实测 |
|---|---|---|
| S1 无 panic | ✅ | `panic(` 0、`K60KEXC` 0、`crashed: backboardd` 0 |
| S2 恰一行 control | ❌ | 0 行 |
| S3 两个数都非零 | ❌ | 没有数 |
| S4 形状 + `imports==frames` | ✅ | `texture untile source=5888 scanout=5760 rows=3200`，4/4 |
| S5 三个数都记下 | ❌ | 只有 `copy` 中位 23,802 µs |
| S6 面板 ≥110 Hz | ✅ | 122/s |
| S7 仍在出帧 | ✅ | 4 条 `scanout frames=` |

按 §4.3，**F2 命中**：没有 control 行但有 `scanout copy` 行 ⇒ 探针没跑到。

### 5.2 真因：被它要测量的那个差异挡住了

`runBlitProbe()` 第一版用源的行跨度算字节数：

```
bytes = frame.stride * (frame.height - 1) + row = 5888 * 3199 + 5760 = 18,841,472
```

而固件帧缓冲只有 `scanout_.stride * height = 5760 * 3200 = 18,432,000` 字节。
于是那句 `if (bytes > scanout_.bytes) return false;` 直接把它挡掉了 ——
**保护条件用的是「源比目标宽 128 字节/行」这个事实，而这个事实正是这一飞要解释的东西。**

修法：两条对照各拷**同一个**字节数，取两者中较小的那个
（`bytes = frame.bytes < scanout_.bytes ? frame.bytes : scanout_.bytes`），
并删掉那句返回。这样既不会溢出帧缓冲，也不再用尺寸去做准入判断。

这一条本身就是个值得记的形状：**一个为诊断而写的保护条件，把被诊断的现象当成了不合法输入。**
测试里加了两条（`the control clamps its byte count to the smaller extent`、
`and never guards the control away by size`），断言的不只是「夹住了」，还有「不再按尺寸拒绝」。

### 5.3 这一飞给出的数（仍然有用）

即便没有 control 行，这一飞也复现了上一飞的结论：`copy` 中位 **23,802 µs**，
`gpu` 中位 4,577 µs，`imports==frames` 4/4，面板 122 Hz，4 帧、8 次 commit —— 仍然是静屏。

### 5.4 重飞

判据未改，因此 `criteria-sha256` 不变，按 §3 P6 允许在同一张镜像之后重飞——
但这一飞需要**新镜像**（改动在插件里）。下一张镜像 `gpu-blitprobe2-20261119`。
