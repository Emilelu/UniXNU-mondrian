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
- P3 内核里必须有下面两条字符串（否则探针没进镜像）：
  `scanout blit control bytes=%zu src-to-device=%llu us device-to-scanout=%llu us`、
  `scanout blit control could not run`。
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

- criteria-sha256: `待钉入`
