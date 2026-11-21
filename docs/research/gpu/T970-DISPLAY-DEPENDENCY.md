# t970 显示栈对 iPadOS 18 / PongPlatform24 契约的依赖判定

研究对象：`E:/hackios/UniXNU-t970`（Pong / Nothing Phone (2)，SM8475，main 面向
iPadOS 18.7.10 / 22H374）里的八个显示补丁。问题只有一个：**这些补丁能不能在
iOS 27 的 K60 上原样用，还是它们依赖某个 iPadOS 18 独有的契约。**

结论先行：**没有任何一行依赖 `PongPlatform24`。** `PongPlatform24` 是构建 kit，
不是内核类（`kits/PongPlatform24/README.md:2-9`），八个补丁对
`IOFramebuffer` / `fbinfo` / `setAttribute` / `getAttribute` /
`IOInterruptEventSource` / `IOFBCursorInformation` / `IOPlatformExpert` /
`PongPlatform24` / `gPongPlatform` 的引用数为 **0**（八个文件 grep 零命中），也
不含任何 `#if` 版本分支。真正的依赖是另外两样：**写死的 SM8475 寄存器/缓冲常量**
和**t970 出树符号**。八项裁决全部 `NEEDS_WORK`，没有一项 `IPADOS18_ONLY`，也没有
一项可以直接用。

## 0 一个必须先纠正的前提

本文件早期草稿把 P3 的常量记成「T970/SM8250」。**错**：t970 就是 SM8475
（`E:/hackios/UniXNU-t970/README.md:16`「CPU / 内存 | SM8475，Cortex-X2 + 3×A710 +
4×A510，PSCI/GICv3，19.2 MHz timer，原生 4 KiB 页」）。所以 P3 的 MMIO 常量不是
「别的 SoC 的值」，而是**同一 SoC、另一棵树的假设**——这让冲突更值得查，而不是更
不值得：两个 SM8475 树对 CTL 页位置的说法不一致（§3.1）。

## 1 研究对象与它的落点

八个补丁全在 `E:/hackios/UniXNU-t970/patches/xnu-ipados18/`，文件名 = 180 字符
`z` 前缀 + 下表后缀：

| 标签 | 后缀 | 改的文件 |
| --- | --- | --- |
| P1 | `-pong-fb-pacing.patch` | `iokit/Kernel/MiniIOMobileFramebuffer.cpp`、`bsd/dev/pong_usb_ctl.c` |
| P2 | `-pong-fb-flip-guard.patch` | 同上 |
| P3 | `-pong-dpu-flip.patch` | 同上 + `bsd/dev/pong_usb_ctl.c` |
| P4a | `-pong-fb-120hz.patch` | 同上 + `bsd/dev/pong_backlight_t970.c` |
| P4b | `-pong-fb-vrr.patch` | 同上 |
| P4c | `-pong-fb-vrr-active.patch` | 同上 |
| P4d | `-pong-fb-vrr-still.patch` | 同上 |
| P5 | `-pong-fb-ar-idle.patch` | 同上 |

关键事实：**`MiniIOMobileFramebuffer.cpp` 不是 Apple 的文件**，是本项目的替身
（`work-display/xnu/iokit/Kernel/MiniIOMobileFramebuffer.cpp`，1472 行），由 t970
`0001-pong-darwin24.patch:10675` / 我们
`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch:2098` 创建，守卫
为 `#if defined(PONG) && (DEVELOPMENT || DEBUG) && !SECURE_KERNEL`
（`MiniIOMobileFramebuffer.cpp:14`）。八个补丁没有一个碰 Apple 的
`IOGraphicsFamily` 文件，也没有一个覆盖 `IOFramebuffer` 虚方法——`show` /
`armVSync` 是替身自己选择的入口。

## 2 五项裁决

| 项 | 关键行 | 依赖 PongPlatform24 | 裁决 | 一句话理由 |
| --- | --- | --- | --- | --- |
| ① `fb_vsync_lock` | `P1:41` `static TUNABLE(uint32_t, gVsyncLock, "fb_vsync_lock", 0);`、`P1:74` `mdssRead(MDSS_INTF1 + INTF_FRAME_COUNT)`、`P1:157` / `P1:191`（`::show` / `::armVSync` 里 `vsyncLockSample(); period = vsyncPeriod();`） | 否（0 命中） | NEEDS_WORK | 时基取自 SM8475 的 `INTF_FRAME_COUNT`，且 `fb_vsync_lock` 是 27 契约里没有的新 boot-arg。 |
| ② `fb-flip-guard` | `P2:73` `uint32_t sent = mdssRead(MDSS_INTF1 + INTF_FRAME_COUNT) - gPendingFrame;`、`P2:75` `if (sent >= 3)`、`P2:82` `fBase = gPanelVirt[gShown];` | 否 | NEEDS_WORK | 逻辑是纯记账，但记账对象（`gPendingFrame` / `gPanelBuffers` / `panelLatched`）是 P3 才引入的全局量——**没有 P3 连编译都过不去**。 |
| ③ `fb_flip=2/3` | `P3:66` `gFlip`、`P3:70` `#define PANEL_FRONT_PHYS 0x9c000000ull`、`P3:83-84` `MDSS_BASE 0xae00000` / `MDSS_SIZE 0x85000`、`P3:87` `#define MDSS_CTL(n) (0x02000 + 0x200 * (n))`、`P3:362` `mdssWrite(kPipeBase[p] + SSPP_SRC0_ADDR, (uint32_t) gPanelPhys[which]);` | 否 | NEEDS_WORK | 前缓冲物理地址 `0x9c000000` 是 Pong 的 UEFI carve-out（`P3:70` 注释写「the UEFI's framebuffer: "Display Reserved" (gts7xlwifiPkg MemoryMapLib)」），CTL 页位置与我们的假设冲突（§3.1）。 |
| ④ `fb_120hz` | `P4a:69` `g120Hz`、`P4a:70` `INTF_TEAR_SYNC_CONFIG_VSYNC 0x288`、`P4a:71` `VSYNC_CLOCK_HZ 19200000`、`P4a:72` `PANEL_120_VTOTAL (1752 + 48 + 64 + 48)`、`P4a:103` DCS `{0x60,0x20}` | 否 | NEEDS_WORK | 120 Hz 切换是**一条** DCS 包 + 由 1912 vtotal 算出的 vsync 分频；K60 是 `pong_panel_switch_120()` 的多包序列（`drivers/PongAdreno/PongDsiPanel.cpp:463`）。 |
| ⑤ VRR 阈值 | `P4b:37` `RATE_FAST_US 12500`、`P4b:38` `RATE_SLOW_US 15000`、`P4b:39` `RATE_IDLE_MS 500`、`P4d:62` `moving = gRateShort >= 2;`、`P5:42` `INTF_TEAR_AUTOREFRESH`、`P5:51` `pong_panel_is_off()` | 否 | NEEDS_WORK | 阈值按 Pong 面板的 120 Hz 节奏（12,500 µs ≈ 80 fps）与 19.2 MHz vsync 时钟标定，结构可复用、数值必须重推。 |

## 3 真正要换掉的东西

### 3.1 MMIO 常量：两个 SM8475 树对 CTL 页位置不一致

t970 认为 CTL 在 MDP 块内、`0x2000 + 0x200 * n`（`P3:87`，相对
`MDSS_BASE 0x0ae00000`）；我们读的是六个 0x1000 页，
`0x0ae16000 + i * 0x1000`（`drivers/PongAdreno/PongDsiPanel.cpp:115-123`，注释写
「zizhan's dbFindPipes uses the same six 0x1000 CTL pages at 0x0ae16000」）。

两边都是 SM8475，所以**必有一边记错了**，或者两边在说不同用途的页：

* 我们的用法只读 `CTL_INTF_ACTIVE`（`0xf4`）做接口推断，读不到就回落 INTF1
  （`PongDsiPanel.cpp:115-123` 注释「Read only; if no bit is set fall back to
  INTF1」）——**错了也不致命**。
* t970 的用法是**写** `mdssWrite(MDSS_CTL(gCtl) + CTL_FLUSH, gPipeFlush)` 提交
  翻页（`P3:365`）——**错了就是翻页永不落地，屏上永远停在第一帧**。

⇒ 27 线上如果照抄 P3，必须先证 CTL 基址。判据：一次探针读 `0xae02000` /
`0xae16000` 两处的 `CTL_INTF_ACTIVE`，只有真 CTL 页会在有画面时置位。这条同时是
display 线的活（`reply-gpu-display-sync.md` 已记）。

### 3.2 其余替换项

| 项 | t970 的值 | K60 的落点 |
| --- | --- | --- |
| 前缓冲物理地址 | `PANEL_FRONT_PHYS 0x9c000000`（`P3:70`） | K60 无此 carve-out；须由 UEFI/DT 给出，并替换 `P3:428` 的 `vinfo.v_physaddr` 校验 |
| 面板 DCS 发送器 | `pong_panel_dcs()`（`bsd/dev/pong_backlight_t970.c`，我们树里没有这个文件） | `dsi_dcs()`（`drivers/PongAdreno/PongDsiPanel.cpp:320`） |
| 120 Hz 切换 | 单包 `{0x60,0x20}`（`P4a:103`） | `pong_panel_switch_120()`（`PongDsiPanel.cpp:463`） |
| 面板灭查询 | `pong_panel_is_off()`（`P5:51`） | 无对应；`PongDsiPanel.cpp:596` 只有 `pong_panel_refresh_hz()` |
| 刷新率访问器 | `refreshHz()`（`P1:117`） | `pong_panel_refresh_hz()`（`PongDsiPanel.cpp:596`，接线在 `patches/xnu/0506-k60-120hz-refresh.patch:27`、`:37`） |
| `start()` hunk | `P3:634-649` | 我们的 `start()` 带 `k60PanelNative` 分支（`patches/xnu/0210-k60-display-native-canvas.patch:28`、`:44`、`:57`），**P3 的 hunk 文本上打不进**，须重写 |
| 缓冲池 | `IOBufferMemoryDescriptor::inTaskWithPhysicalMask`（`P3:483`） | 27 仍导出该 API；`fb_flip=3` 要有意义必须自建 2/3 池 |

九个 tunable（`fb_vsync_lock` / `fb_flip` / `fb_120hz` / `fb_vrr_active_us` /
`fb_vrr_idle_ms` / `fb_ar_idle` / `fb_ar_off` / `fb_ar_idle_ms` /
`fb_ar_active_us`）都是 `TUNABLE` 加出来的，27 上照样能加（`startup.h:267`
→ `PE_parse_boot_argn`）；风险不在能不能加，而在**27 契约里没有任何地方给它们
语义**。

## 4 唯一可能把任何一项降级为 IPADOS18_ONLY 的问题

27 的 `IOMobileFramebuffer.framework` 是否仍驱动这些补丁扩展的
`show` / `armVSync` / `externalMethod` 选择器。补丁本身答不了——需要 27 的
`IOMobileFramebuffer.framework` 头或一次 WindowServer trace。这一项归入
`GPU-27-CONTRACT-DIFF.md` §10 的 unknown 家族（同一条 dyld cache 取证链）。

## 5 与本线其它文档的关系

* `docs/research/gpu/GPU-27-BUDGET-120FPS.md` §6（零拷贝的三个半成品）与 §8（27
  缺项）引用本文件的 ③：**`target` 只是面板双缓冲偏移，仍是 GPU 拷贝**，要真正
  零拷贝得按 surface pitch 编程 DPU，而 DPU 编程的前置正是 §3.1 的 CTL 基址。
* 版本号与 wire 布局的冲突不在本文件范围，见
  `docs/research/gpu/GPU-27-SCANOUT-WIRE-PROPOSAL.md`。
