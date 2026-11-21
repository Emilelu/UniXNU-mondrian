# 27 线 GPU 的证据链（⑥deep）

这张表回答一个问题：**预算表 §8 那八项缺项，每一项的 27 侧证据长什么样、谁交、交到哪、交来之后
用什么判。** 它不是「27 上应该改成什么」的设计稿（那是 ⑤plan 的事），也不是「已经验证过」的结论
（那是 ⑦verify 的事，现在全部为 false）。

读法：每条写四行——**现状**（16.6.1 与 27 线各自现在是什么）、**27 侧落点**（证据必须出现的
文件:行，若 27 侧不存在就写不存在）、**谁交**、**交付物与判据**。凡是需要 display 线或 Lead 决策的，
在「谁交」里点名；凡是等扫出 wire 版本号定案的，判据行写「待版本号定案」，不写结论。

## 0 三条边界

1. **本节不含推断**：每行给的是「去哪看」「看什么」「看到什么算过」，不是「我认为会是多少」。
2. **27 侧读数尚未存在**的项，一律标 `待`，`gpu-27.toml` 的 ⑦verify 保持 `false`。
3. **扫描出相关的三行**（#1、#6、U3 的一半）在 display 会签前不写判定，只写待办形态。

## 1 八项缺项的证据链

### #1 交付队列（两槽 latest-wins）

- **现状**：16.6.1 与 27 线**同一份代码**——`E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoScanout.cpp:159`
  `if(!client || !waiting || pending.offered){…return 0;}`，单 pending 槽；交付循环
  `:135 while(client==owner && !poisoned && (!pending.offered || pending.delivered))`。presenter 侧
  `drivers/PongMetal/PongMetalScanout.h:30-52` 无队列，`wait{500}` 超时即 `continue`。
- **27 侧落点**：同两个文件。改的是内核 `pong_scanout_frame()` 的接帧条件与 presenter 的 wait 循环，
  **不新增 ABI**。
- **谁交**：GPU 线自己（属 `feat/gpu-27` 的代码改动，需 Lead 单独批准后动）。
- **交付物与判据**：离线草案已写——`patches/proposed/pong-scanout-offer-count.patch`（接帧闸门前后各加一个
  计数，并在既有周期行上打 `scanout version=<n> offers=<n> dropped=<n>`）。判据 = 稳态飞行
  `dropped=0` 且 `offers` ≥ 120/s；配合 #2 一起判。草案只过 `git apply --check`，未编译未上机。

### #2 CPU 合成默认关

- **现状**：16.6.1 有开关 `pong_gpu_only`（`patches/xnu/…-pong-gpu-only-display.patch:34-52`，
  在 `patches/xnu/series:195`），默认**关**。27 线**同一个补丁也在同一行**：
  `E:/hackios/xnekom-ios27/patches/xnu/series:195`（series 共 240 行）挂着同名文件；
  `patches/xnu/0600-k60-display-composition.patch:152` `PE_parse_boot_argn("pong_gpu_only", &gpuOnly, sizeof(gpuOnly))`、
  `:153 fGpuOnly = gpuOnly != 0`、`:110` 字段注释「explicit bring-up policy, never the default」、
  `:863 if (fGpuOnly && !gpuFrame)`。⇒ **开关已在 27 上，缺的是「默认打开」这个决定**，不是代码。
- **27 侧落点**：`patches/xnu/0600-k60-display-composition.patch:152`（默认值）+ `:863`（分支），
  以及 `…-pong-gpu-only-display.patch` 的 `if(pong_scanout_quarantined())return;`。
- **谁交**：display 线（`MiniIOMobileFramebuffer.cpp` 侧补丁归它）+ Lead 裁决是否把默认翻成 1。
- **交付物与判据**：飞行日志里出现 `gpuonly=1`，且 `… us each in the driver` 那格**不再出现**
  （`usblog-20261119-151837/console.log:3341` 那条统计 5 秒一次，出现即证明 `drawLayer()` 还在跑）。

### #3 `gperf` 调档在 27 板级路径里被调用

- **现状**：27 线**已在**——`E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoGmu.c:260`
  `PongAdrenoHfiSend(&d->hfi,30,vote,3,&r->header)`；`PongAdrenoPlatform.cpp:557`
  `PE_parse_boot_argn("gperf",…)`、`:560` `record("GPU level vote from gperf",…)`。
- **27 侧落点**：**已就位**，无需补。
- **谁交**：无人；这条是「确认已存在」，证据就是上面两处 `文件:行`。
- **交付物与判据**：飞行日志出现 `GPU level vote from gperf` 且 `gpu` 中位 < 3,000 µs
  （卡 k 实测 2,935）。**注意**：这条只证明调档被投了，不证明 GPU 段达标。

### #4 wire ABI v2

- **现状**：27 线仍是 `drivers/PongAdreno/submit/NativeAdrenoABI.h:14 NativeAdrenoAbiVersion = 1`、
  `:15 MaxBuffers = 16`、`:154 static_assert(sizeof(NativeAdrenoAbiSubmit) == 416)`。
- **27 侧落点**：同文件三行改成 v2 / 128 / `== 32 + 24 * MaxBuffers`（3,104），与官方
  `E:/hackios/UniXNU/drivers/Adreno740/NativeAdrenoABI.h:14-15,154` 逐字对齐。
- **谁交**：GPU 线自己（改动极小，但要两侧同时，否则 `NativeAdrenoUserClient.cpp:67` 直接
  `kIOReturnUnsupported`）。
- **交付物与判据**：G-ABI——飞行日志 `abi=kernel=<v>/<sizeof> client=<v>` 双侧一致（字段本身要先加）。

### #5 客户端绘制计时（第 1 段）

- **现状**：**P-241 已过期**——`native_bridge_metal_telemetry()` 有调用点了：
  `drivers/PongMetal/PongMetalPlugin.mm:62 streamTelemetry()`，`:247 if(seconds>=60u)streamTelemetry();`。
  真日志证实生效：usblog-20261119-151837 的 console.log 第 2727 行
  `Pong Metal: S c11/0 d11 p40 x4 R49 D550 F13 M4500k C0 B7 status=0x0`、第 2731 行
  `Pong Metal: G commit-to-complete n=11 total=263ms max=82ms mean=23964us`。
  真正缺的是**客户端的帧间隔**：桥只累加 pipeline/library/function 与两次 wait，
  `wait` 是渲染服务端阻塞多久，不是客户端多久交一帧。另外该行标签
  `commit-to-complete` 与累加器名 `gTimeEncodeToCommit`（`NativeBridgeMetalFrontend.mm:49`，
  累加在 `:1015-1016`）不一致，读日志的人会把它当成交付延迟。
- **27 侧落点**：`drivers/PongMetal/PongMetalScanout.h` 的 presenter 循环（27 线副本同路径）
  记录相邻两帧到达的时间差，挂在既有 stage 行上。
- **谁交**：GPU 线自己（用户态插件侧）。
- **交付物与判据**：离线草案 `patches/proposed/pong-metal-client-gap.patch`，字段
  `client=<us> us`（判读器 `SCANOUT_VERSION`/`OFFERS`/`CLIENT` 三个正则里最后一个就是它）。
  判据：120 Hz 下 `client` ≤ 8,333 µs；`client` 大于预算而 `gpu` 在预算内 ⇒ 客户端是瓶颈。
  **这条不补，判读器永远只能判「present 快不快」，判不了「界面为什么不够 120」。**

### #6 零拷贝扫出（DPU 行距）

- **现状**：未实现。三条半成品见预算表 §6；真正零拷贝要求显示按合成器 surface 的 pitch 扫描，
  `drivers/PongMetal/GpuScanoutPresenter.h:87-89` 自己写明了这一点。
- **27 侧落点**：**不存在**（没有 27 侧的 DPU 行距编程代码）。落点会是 display 线的 DPU 路径，
  而不是 GPU 线。
- **谁交**：display 线（DPU 编程）+ GPU 线（扫出 wire 字段）。
- **交付物与判据**：**待版本号定案**。定案前这里只留形态：扫出 wire 需要能表达「面板缓冲偏移」，
  且判据必须是「`gpu` 段整段消失于飞行」（无 blit pass），不是「`gpu` 段更小」。

### #7 hw_init 执行者归属

- **现状**：官方 kit 只有表——`E:/hackios/UniXNU/drivers/Adreno740/NativeAdrenoA740HwInit.h:61`
  `NativeAdrenoA740Hwcg[][2]`，`drivers/Adreno740/` 内**无任何 .cpp 引用 `RBBM_CLOCK_*`**；
  真正执行 A740 hw_init 的是板级配方 `E:/hackios/UniXNU-sheng/package/GpuPowerProbe.cpp:1568 gpuHwInit()`。
  A730 表则**不存在**（`derive-a730-hwinit.py` 的 REFERENCE 指向尚未生成的 `NativeAdrenoA730HwInit.h`）。
- **27 侧落点**：`E:/hackios/xnekom-ios27/` 的板级配方（要与 sheng 的 `GpuPowerProbe.cpp` 对齐），
  或沿用 `drivers/PongAdreno/PongAdrenoCp.cpp:252` 的自有路径。
- **谁交**：**Lead 裁决**（沿用 PongAdreno 的 A730 自有路径 vs 走官方 kit + 板级配方）。
- **交付物与判据**：G-HWCG——启动后 `RBBM_CLOCK_CNTL` 回读 `0x8aa8aa82`，且 HWCg 12 行差异的
  行为列由 A/B 上机填（现在只有 A(值)/C(行为)）。

### #8 面板节拍与 8,333 的差

- **现状**：TE 实测 7,385–7,679 µs（卡 j 飞行 `K60 PANEL: … te 120/s … period`），名义 8,333 µs。
- **27 侧落点**：`pong_panel_refresh_hz()`（`drivers/PongAdreno/PongDsiPanel.cpp:596`）与
  `nanoseconds_to_absolutetime(NSEC_PER_SEC / refreshHz(), &period)`（
  `…-pong-fb-pacing.patch:117`）——即「判据用哪个周期」这件事由 display 线的 pacing 决定。
- **谁交**：display 线给口径，GPU 线照着算预算。
- **交付物与判据**：飞行日志里同时出现 `panel_period=<us>` 与 bench 行；判读器按实测周期立账，
  并把它写进结论（否则 5% 的差会让「够 120」和「不够 120」两种结论都出现）。

## 2 三项 unknown 的转化条件

| unknown | 现在为什么判不了 | 什么证据能定 | 谁交 | 定案后填到 |
| --- | --- | --- | --- | --- |
| U1 Metal 用户态 selector 面 | 没有 24A446 `dyld_shared_cache_arm64e`，`audit-metal-api-surface.py` 跑不了 | 抽取方交 `metal-api-surface.json`（字段契约见 CONTRACT-DIFF §10.2） | Lead 已派抽取方 | CONTRACT-DIFF §4 的 C 行 |
| U2 27 WindowServer 是否仍驱动 `show`/`armVSync`/`externalMethod` | 27 stage-0 进不了 SpringBoard，没有运行期读数 | 一次进 SpringBoard 的飞行里 `MiniIOMobileFramebuffer: selector N not implemented` 的集合 | 上机（Lead 调度） | T970-DISPLAY-DEPENDENCY §4 |
| U3 HWCg 12 行的行为方向 | 位语义无公开文档，只有 A730 目录值 | 上机 A/B：换表前后各跑一次 bench，看 `gpu` 中位与 `DeviceLost` | 上机（Lead 调度） | CONTRACT-DIFF §7.2 的 C 列 |

## 3 27 侧已经就位的（不需要补，列入此表以免重复劳动）

| 项 | 27 侧证据 | 说明 |
| --- | --- | --- |
| `IOAcceleratorES` 基类布局 | `ioaccelerator-base-abi-24A446.json`（136 B / 168 槽 / `[0,1,7]`） | 与 16.6.1 完全一致，只差 slide |
| 发布路径 | `drivers/Adreno740/NativeAdrenoPublish.cpp:736-758` | 与我们的 `PongAdrenoNativeGlue.cpp:9-11,146-158` 同构 |
| `gperf` 调档 | `PongAdrenoGmu.c:260`、`PongAdrenoPlatform.cpp:557,560` | 见 #3 |
| A740 HWCg 表 | `NativeAdrenoA740HwInit.h:61` | 表在、执行者不在（#7） |
| A740 protect 表 | `GpuPowerProbe.cpp:1594-1596` | 与 `NativeAdrenoA740HwInit.h` 同源生成 |

## 4 与 fragment ⑥deep 的对应

`docs/research/eight-step/gpu-27.toml` 的 ⑥deep 证据行就指向本文件，按缺项编号写，
不写「已确认」字样；⑦verify 的四个键（`static_check`/`unit_test`/`artifact_check`/`local_verified`）
保持空/false，直到上机有读数。

## 5 引用

- 预算表：`docs/research/gpu/GPU-27-BUDGET-120FPS.md:272`（§8 八项）、`:293`（§9 字段）
- 契约差异：`docs/research/gpu/GPU-27-CONTRACT-DIFF.md`（§4 C 行、§7.2 HWCg 表、§10 unknown）
- 27 线源码（只读）：`E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoScanout.cpp:135,159,166`、
  `…/PongScanoutWire.h:5,15`、`…/submit/NativeAdrenoABI.h:14-15,154`、`…/PongMetal/PongMetalScanout.h:30-52`、
  `…/PongMetal/GpuScanoutPresenter.h:87-89`
- 官方 kit（只读）：`E:/hackios/UniXNU/drivers/Adreno740/{NativeAdrenoABI.h,NativeAdrenoA740HwInit.h,NativeAdrenoPublish.cpp}`
- 板级配方（只读）：`E:/hackios/UniXNU-sheng/package/GpuPowerProbe.cpp:1568`
- 补丁：`patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-only-display.patch:34-52`、
  `patches/xnu/series:195`；t970 `…-pong-fb-pacing.patch:117`
- 官方页：`E:/hackios/UniXNU/docs/zh/porting/gpu.md#frame-path`、`#memory-path`、`#scheduling`
