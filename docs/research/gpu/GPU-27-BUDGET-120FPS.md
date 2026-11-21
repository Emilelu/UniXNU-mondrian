# GPU-27 端到端预算：120 fps 的账本

状态：草案 v1 · 2026-11-21 · 第②件产出（上游裁决 Lead m00595「A → B」）
配套：`docs/research/gpu/GPU-27-CONTRACT-DIFF.md`（契约差异 + 判据 G-*）；本表只回答**哪一段值得改**，
判定「改完能不能判」在第三件。

**证据等级**：**A** 源码或日志逐字可复核；**B** 同一份日志的统计中位（样本数写明）；**C** 由 A/B 推出、
尚无常驻探针证实。表中每一行都带等级，C 不得当作结论引用。

---

## 0 一句话结论

`present()` 不是 120 fps 的瓶颈，**「一帧只能有一个写者」才是**：面板此刻由谁写，取决于渲染线程
**恰好在不在 `wait` 里**。按实测 `sum` 8,281 µs 算，120 Hz 周期内我们只有 0.6% 的帧能接住，其余 99.4%
回落到 Apple 的 CPU 合成（13.2–19.6 ms/帧）——这条算式复算出 **76 fps**，与现场实测的 **74 fps** 上限吻合。
所以 27 上的顺序是：**① 队列化交付（现在没有）→ ② 把 CPU 合成从预算里剔除（`pong_gpu_only` 已有）→
③ 再把 `gpu` 段压到 3 ms 以内（`gperf` 已证）**；只做 ③ 不会改变上限。

---

## 1 预算的定义

| 项 | 值 | 等级 | 出处 |
| --- | --- | --- | --- |
| 120 Hz 名义周期 `T` | 8,333 µs | A | 官方 `docs/zh/porting/gpu.md#frame-path`（七段证据表，帧节拍按面板刷新算） |
| `period=` 回退字段（**不是**周期） | 7,385 / 7,555 / 7,590 / 7,679 µs | C | 同一飞行；display 第 3 轮指正：这是「最短单次 wrap」的回退字段，`drivers/PongAdreno/PongDsiPanel.cpp:223-228` 自己写着「one 7.6 ms interval is 131 Hz while the same 500 ms window has 61 wraps (122 Hz)」，不能用它读频率 |
| 面板几何 | 1,440 × 3,200 · scanout 行距 5,760 B · 源行距 5,888 B | A | `Pong Metal: scanout copy texture untile source=5888 scanout=5760 rows=3200`（同卡 j 飞行） |
| 一帧字节数 | scanout 18,432,000 B · 源 18,841,600 B | A | 5,760·3,200 与 5,888·3,200；`GpuScanoutPresenter.h:44-47` 的越界校验用同一算式 |

> **脚注 1（已结案）**：曾经看起来「TE 到达 7,385–7,679 µs ⇒ 130–135 次/s」的那组数是 `period=` 这个
> **回退字段**，不是周期；display 第 3 轮给出依据（`drivers/PongAdreno/PongDsiPanel.cpp:223-228`）。
> 所以全表只有一个口径：**8,333 µs**。健康判据读 `te <N>/s`，阈值 `te ≥ 110/s`（与判读器 `PANEL_MIN=110`
> 同一行口径）。
>
> **脚注 2**：8,333 µs 不是「我们的」预算，是**客户端 swap 到下一次 swap 的全链预算**。我们的 `present()`
> 只是其中一段，客户端自己绘制也在里面。

---

## 2 七段账本（对齐官方 `#frame-path` 的七行）

官方把一帧拆成七段并要求分别计时（CPU 用 uptime、GPU 用硬件时钟校准）。我们的实现对位如下：

| # | 官方段 | 我们的实现与计量点 | 实测 | 等级 |
| --- | --- | --- | --- | --- |
| 1 | 创建到 commit | 客户端绘制（SpringBoard 渲染服务器） | **~48 ms，无任何计时** | C |
| 2 | commit 到编码 | 内核造帧：`pong_scanout_frame` 准备页 + 子描述符 + `prepare()` | `wait` 21,958 µs（多数时间是**空等**，见 §4.1） | B |
| 3 | 编码到运行时 commit | `import` + `encode` | 51 + 335 µs | B |
| 4 | 运行时 commit 到提交 | `submit`（= `[commands commit]`） | 967 µs | B |
| 5 | 提交到 GPU 完成 | `gpu`（= `[commands waitUntilCompleted]`） | 5,983 µs | B |
| 6 | 完成到回调 | `done`（presenter 交回 Complete） | 41 µs | B |
| 7 | 显示更新 | Apple `MiniIOMobileFramebuffer` 的 `drawLayer` **或** 我们的 GPU 拷贝 | 13,183 / 17,720 / 19,607 µs | B |

**关于第 7 段**：它不是「我们的代码慢」，而是 Apple 的 CPU 合成（缩放/滤波/多线程 `drawRows`），
由 `patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch:2678` 的 `drawLayer()` 承担，
调用点 `:2993`，我们只在 `:3011-3027` 加了 5 s 一次的统计。**同一帧里第 7 段的 CPU 版本与第 5 段的 GPU
版本互斥**（`…-pong-gpu-only-display.patch:44-49,52` 用 `gpuFrame` 把二者二选一），这是本表所有推导的基础。

---

## 3 逐段预算表

判据列取现场已被接受的门槛（`scripts/judge-gpu-perf.py` 常量：`GPU_TARGET_US=3000`、`COPY_TARGET_US=6000`、
`PANEL_MIN=110`；S4 记 `sum < 6,000`），最后一列是本表推出的更严条件，理由见 §4.4。

| 段 | 卡 j 中位（92 样本） | bench 中位（24 样本） | 判据门槛 | 120 fps 的条件 | 27 缺项 |
| --- | --- | --- | --- | --- | --- |
| import | 51 µs | 27.5 µs | ≤ 200 | ≤ 100 ✅ | 无 |
| encode | 335 µs | 3,059 µs | — | ≤ 500 ⚠️ bench 超标 6× | 无（bench 形状问题，§3 脚注） |
| submit | 967 µs | 362 µs | — | ≤ 400 ⚠️ 卡 j 超标 2.4× | wire v2（§7） |
| gpu | 5,983 µs | 2,470 µs | < 3,000 | ≤ 3,000（`gperf` 实测 2,935） | GMU 调档需在 27 板级路径里被调用 |
| **sum** | **8,281 µs** | **5,907 µs** | < 6,000 | **≤ 5,300 µs**（§4.4） | — |
| CPU 合成（回落帧） | 13,183–19,607 µs | 不适用 | — | **0 次** | `pong_gpu_only` 已存在，缺「默认开」的裁决 |
| 交付（offer 命中率） | 260 帧 / 110.9 s = **2.34/s** | 不适用 | — | **≥ 120/s** | **无队列，是最大缺口** |
| 客户端绘制 | ~48 ms | 不适用 | — | ≤ 8,333 µs | 无计时（P-241） |

> **脚注 3**：卡 j 的五列是**各自的中位**，不来自同一帧，所以 51+335+967+5,983 = 7,336 ≠ `sum` 8,281；
> 同一帧的合计请用 `sum`（`PongMetalScanout.h:90-92` 的算式 `import+encode+submit+wait`）。
> 用五列相加去反推「哪段是余项」会算错 945 µs。
>
> **脚注 4**：bench 的 `encode` 3,059 µs 与飞行的 335 µs 差 9 倍，而同一批 bench 的 `import` 反而更低
> （27.5 vs 51）。bench 循环在**同一个 offer 内**连续做 24 次 `present()`、每次重建纹理
> （`PongMetalScanout.h:80-93`），飞行里每帧只做一次。哪一端更接近「真实每帧成本」尚无定论（C），
> 但判据用飞行值，bench 只用来证明「同一份代码可以跑到 5,907」。

---

## 4 关键推导：为什么封顶在 ~74 fps，以及 120 fps 需要什么

### 4.1 交付模型（结构性事实，非猜测）

内核只在渲染线程**正好阻塞在 wait 里**、且没有未退休的 offer 时，才把一帧交给 GPU：

```
drivers/PongAdreno/PongAdrenoScanout.cpp:159
    if(!client || !waiting || pending.offered){IOLockUnlock(scanout_gate);return 0;}
```

`return 0` 的语义是「这次不接，调用者自己走 CPU 路径」（`…-pong-gpu-only-display.patch:34-49`：
`gpuFrame==1` 才算 GPU 帧，`0` 允许 CPU 回落，`2` 是 DMA 不确定时的隔离）。渲染线程的循环是
`wait → present → Complete → wait`（`drivers/PongMetal/PongMetalScanout.h:30-52`），没有队列、没有
第二个 pending 槽位。于是：

- 在 `present()` 的这 `p` 微秒里到达的帧，**一律**不被 GPU 接走；
- 一个周期 `T` 内能被接住的比例 `f = (T − p) / T`，其余 `1 − f` 走 CPU 合成。

### 4.2 用这个模型复算 74 fps

卡 j：`p = sum = 8,281 µs`，`T = 8,333 µs` ⇒ `f = 0.0062`，即 **99.4% 的帧回落 CPU**。
CPU 路径每帧 13,183 µs（同一次飞行的 `MiniIOMobileFramebuffer: 104 frames in 5111 ms (20 a second),
13183 us each in the driver`）⇒ 均摊 0.994 × 13,183 = **13,104 µs/帧 ⇒ 76 fps**。
现场实测上限 **74 fps**（13.5 ms/帧，P-241）。差 2.6%，模型成立。

反过来：即使按 bench 的 `sum = 5,907 µs` 算，`f = 0.291`，均摊 0.709 × 13,183 = 9,345 µs ⇒ **107 fps**。
**这就是「bench 已经 5,907 但界面还是到不了 120」的全部原因**——不是 `present()` 不够快，是它没接住帧。

### 4.3 硬截止，不是均摊

均摊会骗人：回落 CPU 的那一帧本身就花 13.2 ms > 8,333 µs，那一次 swap **必然**错过下一个 TE。
所以 120 fps 的硬条件是

> **回落次数 = 0**：每一帧都由 GPU 接走，且 `present()` 稳定 < 8,333 µs。

这条要求把三件事同时钉死：队列化交付、`present` 有余量、CPU 合成不在稳态里跑。

### 4.4 三条策略与各自的数字

| 策略 | 需要的改动 | 每帧成本 | 120 fps 可及性 |
| --- | --- | --- | --- |
| **P1 混合**（今天的默认） | 无 | `f·p + (1−f)·13,183` | 均摊上限 `p ≤ T²/c = 8,333²/13,183 =` **5,267 µs**；但任何一次回落都丢帧 ⇒ 实测封顶 76 fps |
| **P2 GPU-only**（`pong_gpu_only=1` 已实现） | 默认开 | `min(p, T)` | `p ≤ 8,333` 即可上 120，代价是 `1−f = p/T` 比例的帧**不出新画面**（judder，屏幕停在上一帧） |
| **P3 队列化**（**未实现**） | 内核侧两槽（presenting + next，latest-wins） | `max(p, T)` | `p ≤ 8,333` 且**不丢帧**；这是唯一同时满足「不回落 CPU」与「不掉帧」的形状 |

> **结论**：27 上必须做的是 **P3**。P2 能让帧率数字上去但画面会卡；P1 的 5,267 µs 门槛比 S4 的 6,000 更严，
> 而即便是 5,267 µs，未队列化时也只有 36.8% 的帧能被接住（`1 − 5,267/8,333`）。

---

## 5 CPU 合成墙的真身

| 事实 | 值 | 等级 | 出处 |
| --- | --- | --- | --- |
| `drawLayer()` 是整屏 CPU 合成（缩放、滤波、多线程 `drawRows`） | 无 GPU 参与 | A | `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch:2678` |
| 每个 surface layer 都会调它 | 无条件 | A | 同文件 `:2993` |
| 统计口径 | `fStatDrawing += now − began`；`began` 在 pacing 释放后重置（`:2923`），故窗口 =「唤醒 → 最后一层画完」，含 `pong_scanout_frame()` 交接调用（未等待时几乎为零）与 `drawLayer()` | A | 同文件 `:3011-3027`、`:2901,2923` |
| GPU 等待占比 | `fStatWaiting` = 1 µs | B | 同文件日志行 `after %llu us waiting for the GPU` |
| 三窗口实测 | 13,183 / 17,720 / 19,607 µs（20 / 6 / 14 fps） | B | 卡 j 飞行 `usblog-20261119-151837` |
| 关掉它的开关 | `pong_gpu_only=1` → `fGpuOnly`，无 GPU 帧时直接 `return` | A | `…-pong-gpu-only-display.patch:44-49`，在 `patches/xnu/series:195` |

**这一段的含义**：`13.5 ms ⇒ 74 fps` 这堵墙不是「我们的 GPU 拷贝只有 3 GB/s」，而是**每帧多了一次 18.4 MB
的 CPU 写入**。把它压到 2.5 ms 不会让墙消失——墙是「一帧两个写者」这件事本身。

### 5.1 一句可复跑的读数（不需要设备，只读日志）

```sh
grep -o '[0-9]* us each in the driver, after [0-9]* us waiting for the GPU' \
  E:/k60-work/evidence/usblog-20261119-151837/console.log | sort -u -k1,1n
```

期望输出恰好五行，升序：

```
13183 us each in the driver, after 1 us waiting for the GPU
17720 us each in the driver, after 1 us waiting for the GPU
19607 us each in the driver, after 1 us waiting for the GPU
22165 us each in the driver, after 1 us waiting for the GPU
370719 us each in the driver, after 0 us waiting for the GPU
```

判读：**每一行的第一个数都 > 8,333 µs**（120 Hz 的一帧预算），第二个数恒为 0–1 µs（不是在等 GPU）。
稳态那一行是 `console.log:3341`：

```
MiniIOMobileFramebuffer: 104 frames in 5111 ms (20 a second), 13183 us each in the driver, after 1 us waiting for the GPU …
```

⇒ 一帧里 CPU 合成单独就花 13,183 µs，是 120 Hz 预算的 1.58 倍。**任何只把 GPU 段压到 2,500 µs 的结果，
都改不动这一行**；只有让 `drawLayer()` 不再跑（`pong_gpu_only=1` 且 GPU 帧成立），这一行才会消失。

这条读数的边界（写清楚，避免被当成比它更强的证据）：它证明的是「驱动内每帧耗时」，
不直接等于帧周期；帧周期 30,654 µs 里还有 22 ms 是 `wait`（等客户端交帧，见 §3）。


带宽口径（写进判据，避免再吵）：以「扫描出侧字节 18,432,000 B」计，卡 j `gpu` 5,983 µs ⇒ 3.08 GB/s；
以「读源 + 写扫描出」37.3 MB 计 ⇒ 6.24 GB/s；bench `gpu` 2,470 µs ⇒ 7.46 / 15.1 GB/s；CPU 合成
13,183 µs 搬 36.9 MB ⇒ 2.80 GB/s。**引用时必须写清用的是哪一个口径**，否则 3.08 与 15.1 会被当成矛盾。

---

## 6 零拷贝扫出：现在有的三条半成品，各自省下哪一段

「零拷贝」在本文里有严格定义：**面板直接扫描合成器的 surface，一帧里没有任何整屏写**。
按这个定义，现存的三个方向都还不算：

| 路径 | 实际做了什么 | 省下的段 | 仍要付 | 等级 |
| --- | --- | --- | --- | --- |
| `pong_surface_pitch`（行距归零） | 让客户端 surface 的行距等于 scanout 行距 ⇒ `singleRun` 一条连续拷贝 | `encode` 从纹理路径降到单次 blit | `gpu` 18.4 MB 带宽 | A（`GpuScanoutPresenter.h:75-77`） |
| zizhan 的 `target`（面板双缓冲） | 内核拥有第二个 panel buffer，`dbFlip` 翻页；presenter 把 `destinationOffset` 加上 `frame.target` | 撕裂与「翻转必须等拷贝完」 | **仍是 GPU 整屏拷贝**，`gpu` 段不变 | A（`UniXNU-zizhan/drivers/PongAdreno/PongAdrenoScanout.cpp:1274,1368`；`GpuScanoutPresenter.h:88-89` 原文写明） |
| 停止拷贝（零拷贝扫出） | 按 surface 的 pitch 编程 DPU，让扫描出直接指向 surface | 整个 `gpu` 段（5,983 → 0） | DPU 行距寄存器编程 + 缓冲所有权移交 | C（未实现；`GpuScanoutPresenter.h:87-89` 记「the only ways to get it are … or to stop copying at all」） |

**对预算的影响**：只有第三条改变 `sum` 的量级。前两条只改 `encode` 与所有权，`gpu` 段一个字都不省。
27 上的取舍因此是：先做 P3 队列（§4.4）拿 120 fps 的**准入**，零拷贝扫出再把 `sum` 从 6 ms 压到 3 ms 以下
拿到**余量**；顺序反了会得到「每帧很快但仍掉帧」。

---

## 7 wire ABI v1→v2（单列）

两代头文件逐字只差两行（`diff -u` 只有两个 hunk），其余 struct 的 `static_assert` 完全相同：

| 项 | v1（本树与 27 线现有） | v2（官方 27 kit） | 出处 |
| --- | --- | --- | --- |
| `NativeAdrenoAbiVersion` | 1 | 2 | `drivers/PongAdreno/submit/NativeAdrenoABI.h:14` vs `drivers/Adreno740/NativeAdrenoABI.h:14` |
| `NativeAdrenoAbiMaxBuffers` | 16 | 128 | 同 `:15` |
| `sizeof(NativeAdrenoAbiSubmit)` | **416 B** | **3,104 B** | `:154` `assert(==416)` vs `assert(==32+24*MaxBuffers)` |
| 其余 12 条 assert | 相同 | 相同 | 两侧 `:145-153` |

### 7.1 每帧字节账

一帧扫出在 wire 上走的记录（`PongScanoutWire.h:10-13` + `NativeAdrenoABI.h:96-102`）：

| 记录 | v1 | v2 | 说明 |
| --- | --- | --- | --- |
| `Submit` 输入（每帧 1 次） | 416 B | 3,104 B | +2,688 B，`inputSize()` 精确校验 |
| `Submit` 回复（fence） | 8 B | 8 B | 不变 |
| `WaitFence`（若用） | 16 B | 16 B | 不变 |
| 扫出 `Wait` 输入 / `Frame` 输出 | 8 / 48 B | 8 / **56 B** | 见 §7.4（这是另一条 wire，不是这一条） |
| **合计** | **≈ 496 B** | **≈ 3,192 B** | **+2,696 B/帧** |

120 fps 下增量 = 323,520 B/s ≈ 316 KiB/s，按 2 GB/s 的拷贝成本折 **1.3 µs/帧（0.016% 预算）**。
**结论：v2 的字节账是噪声，它不是一个预算项。** 真正的预算影响在**提交次数**：

| 场景 | v1 | v2 |
| --- | --- | --- |
| 我们自己的 presenter（一次 blit，引用 2 个 BO） | 1 次 submit | 1 次 submit（无收益） |
| 27 官方 Turnip 客户端，一帧绑定 > 16 个 BO | 必须拆成 ⌈n/16⌉ 次 submit，每次一个 fence + 一次内核往返 | 1 次 |

每多一次 submit，就多一次「`submit` 段量级」的成本（实测 362–967 µs，取决于哪一批样本）。
所以 v2 对 120 fps 的意义只在**27 客户端**上：它把「一帧 N 次内核往返」压成 1 次。

### 7.2 不做会看到什么失败形态

四条都是 A 级（源码逐字），且两侧行为对称：

| # | 组合 | 现场看到什么 | 机制 |
| --- | --- | --- | --- |
| F1 | 客户端 v2 常量 + 内核 v1 | 挂载即失败：`[gpu client text]` 第一行就报错，插件无设备，界面全程 CPU 合成 | `NativeAdrenoUserClient.cpp:67 if(abi_version!=NativeAdrenoAbiVersion)return kIOReturnUnsupported`（官方 kit 同逻辑 `:78`） |
| F2 | 客户端 v2 结构 + 内核 v1（常量未改） | 首个 submit 起 `kIOReturnBadArgument`，`scanout frames=` 不再增长 | `:398 case NativeAdrenoMethodSubmit:return sizeof(NativeAdrenoAbiSubmit)`（官方 `:416`）——输入尺寸精确等于 416，3,104 会被 IOKit 层拒 |
| F3 | 内核 v2 + 客户端 v1 | 客户端自己退出 | `NativeAdrenoClient.cpp:14 reply.abi_version!=NativeAdrenoAbiVersion` ⇒ open 失败 |
| F4 | 两侧头文件版本号相同但布局不同步（最险） | **编译期无告警**，只有运行期 F2/F3 | `static_assert` 只校验本编译单元的布局；两侧头文件同名同路径，插件构建树里的旧副本不会被发现（同类事故已发生过一次：YB-01 校验 `NativeAdrenoMetal.bundle` 而产物是 `PongAdrenoMetal.bundle`，见 `UPSTREAM-PARITY.md`） |

**F4 的防线**：把 `abi_version` 从常量升级为**运行时打印**（内核在 `[gpu client text]` / `[vm kinds]` 里
写出自己编译时的 `NativeAdrenoAbiVersion` 与 `sizeof`），使「两侧不同步」在第一条日志里就能看见，
而不是表现为「界面莫名退回 CPU 合成」。这一条建议进 27 的启动自检（判据 G-ABI 已留位）。

### 7.3 27 上的迁移顺序

1. 内核侧升到 v2（`NativeAdrenoABI.h` 两行 + `inputSize()` 自动跟随，其余 struct 不动）；
2. 插件侧用**同一份**头文件重建（不许复制粘贴），并在 mount 后立即 `GetDeviceInfo` 取回 `abi_version` 复核；
3. 判据加一条 **G-ABI**：日志里同时出现「内核编译期 v2」与「客户端上报 v2」，缺一即 fail-closed。

### 7.4 附：扫出 wire 的版本号冲突（另一条 wire，需与 display 线会签）

`PongScanoutFrame` 我们 **48 B**、zizhan **56 B**（多 `token`/`evict`/`target`），而两侧 `PongScanoutVersion`
**都还是 1**（我们 `PongScanoutWire.h:5`，zizhan 同文件 `:5`）。内核侧按 `outBytes==sizeof(PongScanoutFrame)`
精确校验（`PongAdrenoScanout.cpp:129`），所以版本号相同的两种布局**不会碰巧兼容**，只会互相报
`kIOReturnBadArgument`、presenter 打 `scanout frame wait stopped` 并结束线程、退回 CPU 合成。
完整规格提案另发（见 `E:/k60-work/scratch/reply-gpu-display-sync.md`），本表只记：**它是一条独立的 wire，
不要和 §7.1 的 v1→v2 混为一谈**。

---

## 8 27 上还要补哪几项

按「不做就上不了 120 fps」排序。前四项是准入，后四项是余量与可判性。

| # | 缺项 | 现状（16.6.1 / 27 线） | 27 上的判据 | 等级 |
| --- | --- | --- | --- | --- |
| 1 | **交付队列**（两槽 latest-wins） | 无（`PongAdrenoScanout.cpp:159` 单 pending 槽） | offer 命中率 ≥ 120/s，`dropped=` 计数为 0 | A |
| 2 | **CPU 合成默认关** | 有开关（`pong_gpu_only`），默认关 | 稳态飞行里 `… us each in the driver` 不出现（第 7 段计数为 0） | A |
| 3 | **`gperf` 调档在 27 板级路径里被调用** | 我方 `PongAdrenoPlatform.cpp:557` + `PongAdrenoGmu.c:260`（HFI id 30） | `GPU level vote from gperf` 出现且 `gpu` 中位 < 3,000 | A |
| 4 | **wire v2**（§7） | 27 线仍是 v1/16/416 | G-ABI 双侧 v2 | A |
| 5 | 客户端绘制计时（第 1 段） | 无（P-241：`native_bridge_metal_telemetry()` 无调用点） | 每帧一条 `ctc`，120 Hz 下 ≥ 110/s | A |
| 6 | 零拷贝扫出（DPU 行距） | 未实现（§6 第三行） | `gpu` 段消失于飞行（无 blit pass） | C |
| 7 | hw_init 执行者归属 | 官方 kit 只有表（`NativeAdrenoA740HwInit.h:61`），无 .cpp 引用；执行者在 sheng 的 `package/GpuPowerProbe.cpp:1568` | 27 上必须有一个**板级**调用点，否则 HWCg 不写 | A |
| 8 | ~~面板节拍与 8,333 的差~~ **已消解，不是缺项** | 那组数是 `period=` 回退字段，display 第 3 轮指正 | 不需要再补；判据只读 `te N/s` ≥110 | A |

> **第 7 项是 27 的板级决定，不在本线权限内**：官方 `drivers/Adreno740/` 里没有任何 .cpp 引用
> `RBBM_CLOCK_*`，A730 表也不存在（`derive-a730-hwinit.py` 的 REFERENCE 指向一个尚未生成的头）。
> 沿用 PongAdreno（A730 专用）还是走官方 kit + 板级配方，需要 Lead 裁决；本表只记它对 HWCg 的依赖。

---

## 9 给第三件的判据字段（本表的直接产物）

第三件（离线判读器）需要的、现在日志里**还没有**的字段，全部来自上表的缺口：

| 字段 | 从哪来 | 判什么 |
| --- | --- | --- |
| `offers=` / `dropped=` | 内核 `pong_scanout_frame` 的两个 return 0 分支（`:159` 与 `:166` 之后） | 交付是否够 120/s（缺项 1） |
| `gpuonly=<0/1>` | `pong_gpu_only` 生效值 | 第 2 项是否真的关掉了 CPU 合成 |
| `client=<us>` | 第 1 段计时（`native_bridge_metal_telemetry` 接上） | 客户端是否已经 ≤ 8,333 µs（缺项 5） |
| `abi=kernel=<v>/<sizeof> client=<v>` | §7.2 F4 的防线 | G-ABI 是否双侧一致 |
| `panel_period=<us>` | 回退字段（最短单次 wrap），**不作周期依据**；周期判据读 `te N/s` ≥110 | 只用一个口径：8,333 µs |

---

## 10 引用

- 官方：`E:/hackios/UniXNU/docs/zh/porting/gpu.md#frame-path`（七段证据表）、`#render-mode`（渲染模式）、
  `E:/hackios/UniXNU/docs/zh/porting/gpu-diagnostics.md`（§保留的证据、§检查）
- 飞行（全部只读）：`E:/k60-work/evidence/usblog-20261119-151837`（卡 j，92 样本）、
  `E:/k60-work/evidence/usblog-20261119-173454`（bench 24 样本）、`usblog-20261119-044558`（P-241，8.4 fps）
- 卡：`docs/research/gpu/FLIGHT-CARD-20261119j.md:96-108`、`…k.md:11,17`、`…l.md`（S3/S4 判据）、`…m.md:5`
- 源码（本树）：`drivers/PongMetal/GpuScanoutPresenter.h:40,56,67,75-77,103,116-122`、
  `drivers/PongMetal/PongMetalScanout.h:30-52,80-93,147-151`、
  `drivers/PongAdreno/PongAdrenoScanout.cpp:129,159,175`、
  `drivers/PongAdreno/submit/NativeAdrenoABI.h:14-15,154`、`…/NativeAdrenoUserClient.cpp:67,398`、
  `…/NativeAdrenoClient.cpp:14`
- 补丁：`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch:2678,2993,3011-3027`、
  `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-only-display.patch:34-52`、
  `patches/xnu/series:195-196`、`patches/xnu/0600-k60-display-composition.patch:857`
- 参考树：`E:/hackios/UniXNU-zizhan/drivers/PongAdreno/PongAdrenoScanout.cpp:1274,1368`、
  `E:/hackios/UniXNU/drivers/Adreno740/{NativeAdrenoABI.h,NativeAdrenoUserClient.cpp:78,416}`
