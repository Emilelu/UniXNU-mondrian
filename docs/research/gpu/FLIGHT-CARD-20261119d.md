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

- criteria-sha256: c08fd7beb17dca584a8fc72fb9491291599f65eaa1bedc591c541e323b4c139e

  第一次写进 §5 的 `28bc8596…` 是错的：§4 自创建提交 `5bb92956` 起一个字节都没改过
  （`diff` 过整段 §4 为空），门禁算出来一直是 `c08fd7be…`。钉进去的值和门禁算的
  不一致，比不钉更糟——它会让每一次合法重飞都被拒。教训：钉摘要的脚本必须调用门禁
  自己的函数，并在钉完当场跑一次门禁确认通过，而不是只信「我 import 了它」。

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

### 5.5 第二次飞（`usblog-20261119-070345`）：**PASS，S1–S7 全过，而且这次真有动画**

镜像 `gpu-blitprobe2-20261119`（`boot.img 647f277d…`、kernel `a5adfdc7…` 105,693,184 B、
插件 `metal-plugin-20261119o` 的 `PongAdrenoMetal` 111,808 B sha256 `d55f7489…`）。
证据 500,644 字节，`supervisor rc=0`，抓取完整，无 panic、无复位。

有效性：`compositor=112 frames · client_commits=1215 · scanout_lines=106` ⇒ **有效**，
而且这是 GPU 线上第一次有持续动画的飞行（上一飞只有 8 次 commit，静屏）。

| 判据 | 结果 | 实测 |
|---|---|---|
| S1 无 panic | ✅ | `panic(` 0、`K60KEXC` 0、`crashed: backboardd` 0 |
| S2 恰一行 control | ✅ | 1 行 |
| S3 两个数都非零 | ✅ | 1,993 µs 与 1,835 µs |
| S4 形状 + `imports==frames` | ✅ | `texture untile source=5888 scanout=5760 rows=3200`，99/99 行成立 |
| S5 三个数都记下 | ✅ | 见下 |
| S6 面板 ≥110 Hz | ✅ | `after the UI frame te` 122/s |
| S7 仍在出帧 | ✅ | 106 条 `scanout frames=` |

### 5.6 结论：固件帧缓冲**不是**慢的那个 —— 三处数字合起来推翻了上一轮的归因

```
scanout blit control bytes=18432000 src-to-device=1993 us device-to-scanout=1835 us
```

同一个 18,432,000 字节、同一个 `copyFromBuffer` + `commit` + `waitUntilCompleted` 形状：

| 目标 | 耗时 | 吞吐 |
|---|---|---|
| GPU 自行分配的 shared 缓冲 | 1,993 µs | 9.25 GB/s |
| 固件帧缓冲（物理地址导入） | 1,835 µs | 10.04 GB/s |

两者相差 0.92 倍，**固件帧缓冲甚至略快**。所以：

- **F4 被否**：不是「目标端不可缓存」。走 zizhan 的 `PongScanoutFrame.target`
  （把画面拷进面板缓冲）不会因为「换了个更快的目标」而带来收益。
- **F3 被否**：两个数都远低于 5 ms，不是全局带宽/频率/不可缓存的问题。
- **F5 被否**：`src-to-device` 只有 2.0 ms，拷贝实现（`copyFromBuffer` → DMA 路径）本身没问题。

真实路径的稳态中位（99 条 `frames>=20` 的样本）：

| 段 | 中位 |
|---|---|
| `import` | 53 µs |
| `encode` | 424 µs |
| `submit` | 3,015 µs |
| `gpu` | 5,302 µs |
| `sum` | 12,552 µs |
| `copy`（= `present()`） | 12,631 µs |

`copy - sum` 中位 89 µs，99/99 行 `copy ≥ sum` ⇒ 四段确实构成 `present()`，账是平的。

⇒ **同一个 18.4 MB，纯 buffer→buffer 只要 1.9 ms，而真实路径的 `gpu` 是 5.3 ms、
`present()` 是 12.6 ms。差出来的 10.7 ms 不在目标端、不在带宽、不在 DMA**，
而在拷贝的**形状**：真实路径走的是 `copyFromTexture`（linear texture untile，
源 stride 5888 → 目标 stride 5760），对照走的是单次 `copyFromBuffer`。
这条结论与 2026-11-18 那两次飞行（逐行 3,200 条命令 encode 15 ms、纹理 encode 0.4 ms）方向一致，
但现在有了目标端的对照，把「目标」和「形状」彻底分开了。

### 5.7 另一个更重要的数字：`present()` 只占一帧的 9 %

`scanout frames=1 at 90.776 s` → `frames=1000 at 230.386 s` = 999 帧 / 139.6 s = **7.16 fps**，
即帧间隔 **139.7 ms**。`present()` 的 12.6 ms 只占 **9.0 %**。

即使把扫出做到 0，上限也只有 ~7.9 fps。**扫描路径不是 120 fps 的主要障碍** ——
这是对前几轮结论的修正，必须写明，否则下一轮还会继续优化错的 9 %。

合成器窗口（18 个）的帧率分布：`0.1 20.4 5.0 11.1 2.1 21.9 17.8 1.5 7.3 15.0 11.4 6.8 17.8 8.1 22.1 4.9 6.0 5.7`，
中位 9.6 fps，最好 22.1 fps（该窗口 `102 frames in 5010 ms, 14036 us each in the driver`）。
即使在最好的窗口，`present()` 的 12.6 ms 也只占 ~28 %，另外 30 ms 在别处。

同一次飞行的客户端侧累计：`G commit-to-complete n=1215 total=27372ms max=752ms mean=22528us`
（1.2 次 commit/帧 × 22.5 ms ≈ 27 ms/帧，比我们的 `present()` 还大）；
`J completed wait n=601 total=8787ms`；`J scheduled wait n=617 total=722ms`（很小）；
`J surface cache n=1838 bytes=24456486912 dup=8 us=694`（24.5 GB 被导入过，但没有重复导入的浪费）；
`T pipeline n=101 total=1516ms max=715ms`、`T library n=5 total=147ms`、`V vkpipe n=0`
⇒ 管线编译仍是一次性成本，不是稳态成本。

### 5.8 这张卡自己的缺陷（必须记下来）

§4.3 的六条失败规则覆盖了「目标慢」「实现慢」「全局慢」「探针没跑」「画面错位」，
**唯独没有覆盖「两个都很快」这一支** —— 而这正是实际发生的事。

后果：这一飞虽然 S1–S7 全过，判据却**没有为「真相是拷贝形状」准备任何出口**，
结论是我事后从三个数里读出来的，不是卡预先指明的。这属于 P-242「判据存在 ≠ 判据覆盖」
的同一族：判据枚举了所有**慢**的分支，却没枚举「对照推翻了假设」这一支。
下一张卡的写法：每条对照实验都必须包含「两个都正常 ⇒ 假设被推翻，下一步是 X」这一支。

### 5.9 下一步

1. **主攻方向换成客户端绘制**：`present()` 只占 9 %，先把「一帧 139.7 ms 花在哪」
   做一次端到端分解。现有 `T/G/J/K` 行只覆盖我们自己的 bridge，
   缺的是 SpringBoard / CoreAnimation 那一段（合成器窗口已给出
   「14036 us each in the driver」与「408888 us each in the driver」两个极端，
   说明有的窗口驱动内只 14 ms、有的 34 秒只出 4 帧）。
2. **把纹理 untile 换成单次 `copyFromBuffer`**：对照证明这条能到 1.9 ms（省 10.7 ms/帧）。
   前提是扫描缓冲的 stride 等于 surface 的 5888 —— 即自己拥有扫描缓冲
   （zizhan 的 `db[]` 路线，见 `ZIZHAN-DBUF.md`），并且要接受「画面不上屏」
   直到 DPU/SSPP 编程完成。这条路能把 `present()` 从 12.6 ms 压到 ~2 ms，
   但按 §5.7 只值 7.6 % 的帧时间。
3. **`submit` 3.0 ms 仍未解释**：coherence 已开、`publishMapped` 已降到 51 µs，
   这 3 ms 在别处（提交路径的固定开销）。
4. **47 条 `native-metal: surface import refused: no-copy buffer: DeviceLost`** 是本飞新症状，
   未查。
