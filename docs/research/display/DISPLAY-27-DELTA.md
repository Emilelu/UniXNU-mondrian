# iOS 16.6.1 → 27 显示线差异表

对象：官方《适配驱动》表第 3 行 `porting/display`（帧缓冲、刷新、亮度）。
16.6.1 侧基线：`main` = `4b744c2e`，阅读的树 `E:/hackios/k60-display27`
（分支 `feat/display-27`，本文件所在树）。
27 侧读数：`24A446`（ipados-27.0.1-24A446 / xnu-12377）的引导链按官方
`docs/zh/porting/display.md` 与参考树 `UniXNU-sheng`、`xnekom-ios27` 逐行读；
**27 侧没有本仓的驱动树**，凡写「27 侧不存在」都是指该契约在官方页面与参考实现里
没有对应物，不是指 Apple 的二进制里没有。

读法（Lead 2026-11-21 的四条补约束）：每行给 ①16.6.1 的 `文件:行`，
②27 侧的 `文件:行` 或「27 侧不存在」，③官网页锚点。判定只用三个词：
`已具备` / `缺` / `改名`（改名含"改形"：同一契约、不同编码或不同名字）。
只写「已具备」不算证据，所以每一条都带行号；没有行号的条目落在 §9 的 unknown 表里。

---

## 0. 计数

| 判定 | 条数 | 说明 |
| --- | --- | --- |
| 已具备 | 12 | 16.6.1 已经按 27 的形状发布/实现了同一契约 |
| 缺 | 7 | 27 要、16.6.1 没有；其中 3 条是"故意没有"（有崩溃判据），4 条是"真缺" |
| 改名 | 6 | 同一意图，两个名字或两种编码 |

真缺的 4 条是：`backlight-calibration-parameters` 六键字典（故意缺）、
MDP/DPU 侧探针读数（VIG/CTL）、`sheng-dpu-scanout` 直扫路径、arm64e 元类伪装路径。
改名的 6 条全部集中在 boot-arg 名与帧所有权编码上（§8、§2.4）。

---

## 1. 官方 `#source-map`：四个组件的形态对照

`docs/zh/porting/display.md:9-19`（`{#source-map}`）把这条线拆成四块：
OS 侧显示接口、帧所有权、亮度实现、时序参考。四块在 16.6.1 与 27 的落点完全不同，
**不是版本升级，是两种架构**：16.6.1 是"补丁改 XNU 自带的 Mini 显示栈"，
27 官方是"独立驱动接管 framebuffer"。

### 1.1 OS 侧显示接口

| 项 | 16.6.1 | 27 侧 | 判定 |
| --- | --- | --- | --- |
| 接口实现 | 补丁直接改 XNU 自带栈：`patches/xnu/0210-k60-display-native-canvas.patch`（`MiniIOMobileFramebuffer.cpp` 的 `start()`，画布=面板原生 1440×3200）、`patches/xnu/0211-k60-display-startup.patch`（`MiniIOSurface.cpp:1916` 的 `native_pong_ui_services_start`，服务默认启动） | 独立驱动 `drivers/GopFramebuffer/NativeLegacyDisplay.cpp`（659 行）+ `OriginalMobileFramebufferABI.h`（107 行）+ `NativeMobileDisplay.cpp`（140 行），见 `display.md:11` | **缺**（27 的驱动形态在本仓不存在） |
| 启动开关 | `pong_software_ui`（默认 1，`=0` 才关；`patch 0211` 的 `MiniIOSurface.cpp` hunk） | 官方在 OS profile 里选 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y` 与 `offline-legacy-*`（`display.md:33-35`） | 改名 |
| 画布尺寸 | `k60_panel=1` 时拒绝 `fbwidth/fbheight/fbscale`，强制面板原生（`patch 0210`，`k60PanelNative()`；日志 `K60 DISPLAY: fbwidth/fbheight/fbscale refused, the canvas is the panel`） | 27 侧无此概念：`NGPMode` 直接报固件 framebuffer 的几何（`NativeGOPWire.h:6`，`display.md:47-49`） | 改名（16 线自建的概念在 27 没有对应物） |

结论：这一块**不能平移**。16.6.1 的显示是"打补丁的 Mini 栈"，27 是"新驱动"。
如果 27 沿用它，`IOMobileFramebuffer::start()` 里的画布拒绝逻辑会和 27 的
`NGPMode` 报出的几何打架；如果迁到 27 形态，0210/0211 两个补丁整个失效。
这条是本线最大的一次架构裁决，见 §10 风险 R5。

### 1.2 帧所有权（NGP 线协议）

| 项 | 16.6.1 | 27 侧 | 判定 |
| --- | --- | --- | --- |
| 协议头 | `drivers/PongAdreno/PongScanoutWire.h:2` 注释即 "adapted from NativeMobileDisplay/NativeGOPWire.h" | `drivers/GopFramebuffer/NativeGOPWire.h:1-17` | 改名（同源，编码不同，见下三行） |
| 版本/格式 | `PongScanoutWire.h:5` `PongScanoutVersion=1, PongScanoutBgra=1` | `NativeGOPWire.h:5` `NGP_BGRX8888=1, NGP_VERSION=1` | 已具备（值相同，名字不同） |
| 方法选择子 | `PongScanoutWire.h:6` `Mode=0x7000, Wait=0x7002, Complete=0x7003, Memory=0x5343` | `NativeGOPWire.h:12` `NGP_METHOD_MODE=0, PRESENT=1, WAIT_SWAP=2, COMPLETE_SWAP=3, NGP_MEMORY_SCANOUT_RW=1` | **改名（改形）**：同一四步，选择子编码完全不同 |
| 记录尺寸 | `PongScanoutWire.h:10-15` ModeInfo 40 / WaitInfo 8 / Frame 48 / Done 16 | `NativeGOPWire.h:6-16` Mode 40 / Present 32 / Transfer 16 / Wait 8 / Swap 48 / Complete 16 | 已具备（三张表重叠；27 多 `NGPPresent`/`NGPTransfer` 的固件拷贝路径） |
| 是否拷像素 | 不拷，交 GPU 拷贝（`PongAdrenoScanout.cpp:154-211` `pong_scanout_frame`） | 不拷，交 GPU 拷贝（`NativeGOPWire.h:9-11` 注释 + `NativeGOPPresenter.cpp`） | 已具备 |
| 失败码 | `PongScanoutWire.h:9` `NotSubmitted=0x4e4f444d`（"MODM"） | 27 侧不存在（`NativeGOPPresenter.cpp` 用 `kIOReturn*`） | 改名 |

### 1.3 亮度实现

见 §5 主表。

### 1.4 时序参考

| 项 | 16.6.1 | 27 侧 | 判定 |
| --- | --- | --- | --- |
| 帧率观测 | `drivers/PongAdreno/PongDsiPanel.cpp:69` `panel_measured_hz`；`:84` INTF 寄存器常量；`:136-236` `panel_intf_rate()`（TE 计数器高位当帧计数、行计数按自动刷新间隔、两次采样相隔 200/500 ms） | `DisplayTimingProbe.cpp:30-39` 常量、`:42-111` 线程：隔 1 s 采两次 `frame count`，`native_dpu_stats[18]` 记 µs | 已具备（INTF 侧；两侧寄存器集完全重合，见下条） |
| INTF 寄存器集 | `PongDsiPanel.cpp:84` `IntfConfig=0x04, IntfVsyncPeriod=0x0c, IntfCountEnable=0xa8, IntfFrameCount=0xac, IntfLineCount=0xb0, IntfTearCheckEn=0x284, IntfTearSyncVsync=0x288, IntfTearAutorefresh=0x2b4, IntfTeCount=0x298` | `DisplayTimingProbe.cpp:32-33` `kTimingEnable=0x6c, kConfig=0x04, kCountEnable=0xa8, kFrameCount=0xac, kLineCount=0xb0, kVsyncPeriod=0x0c, kStatus=0x26c` | 已具备（八个偏移逐字相同；27 多 `0x6c`、`0x26c` 两个） |
| INTF 页基址 | `PongDsiPanel.cpp:505` `0x0ae35000 + active*4096`（即 INTF0 0xae35000 / INTF1 0xae36000） | `DisplayTimingProbe.cpp:31` `kIntf{0x35000,0x36000}`（相对 MDSS 0xae00000） | 已具备（**同一对页**，可互相印证） |
| MDP/DPU 侧读数 | 27 侧不存在（`grep -rn "sheng-dpu\|native_dpu" drivers/ patches/` 零命中） | `DisplayTimingProbe.cpp:35-39` `kSrcSize/kSrc0/kStride0/kFormat`、`kCtl` 七寄存器、`kPipeMore[9]`、`kTearCheck`、`kAutorefresh`；`:42-111` level≥2 才读 | **缺** |
| 直接扫描输出 | 27 侧不存在 | `display.md:58-78`（`sheng-dpu=3` 重写地址并测 flush 锁存；`sheng-dpu-scanout=2` 默认关） | **缺** |

---

## 2. `#dpu-pipes`：探针与直扫

| 项 | 16.6.1 | 27 侧 | 判定 |
| --- | --- | --- | --- |
| 探测参数名 | — | `sheng-dpu=1/2/3`（`DisplayTimingProbe.cpp:114-121` `sheng_dpu_probe()`） | **缺** |
| 直扫参数名 | — | `sheng-dpu-scanout=2`（`display.md:58`） | **缺** |
| 帧缓冲格式 | BGRA（`PongScanoutWire.h:5` `PongScanoutBgra=1`） | 8 位 BGRA（`display.md:78`） | 已具备 |
| 探针失败回退 | — | GPU 拷贝（`display.md:61`） | 已具备（16.6.1 只有 GPU 拷贝这一条路，天然是"回退态"） |
| 探针采样占用 | `PongDsiPanel.cpp:100-118` `probe_page()`/`probe_read()`，13 个 slot | `DisplayTimingProbe.cpp:42` `IOSleep(150000)` 后才第一次采样 | 已具备（两侧都延后采样，理由相同：MDP 寄存器在扫描开始前无意义） |

**离线未知**：`DisplayTimingProbe.cpp:4-7` 的注释写 MDP 子块 `0xae01000+0x8f000`
且 catalog 是 **DPU 9.2**（`qcom,sm8550-dpu`），而本仓 `docs/research/display/RESEARCH.md`
记 K60（SM8475）的 MDP 是 `0xae00000+0x84000`。两者不是同一个偏移，DPU 版本号
也没有离线证据。这条进 §9 unknown U2，**不能**在实现里直接抄 sheng 的常量。

---

## 3. `§2` 步骤 1–2：固件扫描与 XNU 后端

| 项 | 16.6.1 | 27 侧 | 判定 |
| --- | --- | --- | --- |
| 固件扫描确认 | 走 `PE_current_console`（`patch 0210` 的 `vinfo`），日志 `K60 PANEL: INTF%d config=… vsync_period=…`（`PongDsiPanel.cpp:177`） | `display.md:29-31`（确认固件扫描输出） | 已具备 |
| 原生后端 | 补丁栈（§1.1） | `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`（`display.md:33`） | 改名 |
| 首帧 | `patches/xnu/0213-k60-display-first-frame.patch`；日志 `K60 DISPLAY: first frame presented` | `NGPPresent`/`NGPSwap`/`NGPComplete`（`display.md:47-49`） | 改名 |
| 面板模式与刷新策略 | `PongDsiPanel.cpp:463-520` `pong_panel_switch_120()`：11 个厂商包 + 把 INTF1 `TearSyncVsync` 100→50 + 自动刷新 0x8000003c→0x80000001（`:84` `CadenceInherited/CadenceEveryFrame`） | `display.md:44-45` "根据实际面板模式设置刷新策略；参考实现用 `sheng-vsync=120` 请求 120 Hz" | 改名（16 走面板 DCS + INTF 寄存器，27 走 intf vsync 周期请求） |

16.6.1 的 120 Hz 现在是**默认**（`PongDsiPanel.cpp:566-577`：`p120Value=1`，`vsync=120`
才显式请求，`p120=0` 或 `vsync!=120` 才退回 60 Hz），依据是 120hz-7 的实测
（11 包 rc 0、INTF1 行计数 55/s→120/s、SpringBoard 172 行、sig=11 零，见
`:569-576` 的注释）。所以 27 线**不需要**为 120 Hz 花 boot-arg 字节。

---

## 4. 面板与 DSI 命令通路

| 项 | 16.6.1 | 27 侧 | 判定 |
| --- | --- | --- | --- |
| DSI 控制器基址 | `PongDsiPanel.cpp:33` `DsiPa = 0x0ae94000`（DSI0） | sheng 是双 DSI（`DisplayTimingProbe.cpp:4-7` 的 `dsi@ae94000`/`dsi@ae96000`），K60 单 DSI | 已具备（K60 用 master） |
| 上电序列 | `PongDsiPanel.cpp:520-560` `pong_panel_bringup()`：`dsi_init()` → DCS `0x11` → 120 ms → `0x29` → 20 ms → `0x51` 最大亮度（`pong_panel_dbv_bytes(0xfff,…)`） | 27 侧无对应（本轮不涉及面板上电；官方页面把面板命令留在厂商表里，见 `display.md:80-87` 的"复用前记录控制器数量/寄存器编码/亮度范围"） | 已具备（16 线已有自己的上电通路） |
| 1534 B on-command 回放 | **不存在**：本仓只发 `0x11`/`0x29`/`0x51`（`PongDsiPanel.cpp:531-556`），live FDT 里的 1534 B 序列（`docs/research/display/RESEARCH.md`）没有被回放 | 27 侧不存在（同一份 FDT 事实） | 缺（相对"按 FDT 全量回放"这个理想；当前形态已能点亮，见 §11 第 2 条） |
| 亮度编码 | 12 位，`bl-max=0xfff`，`bl-inverted-dbv` 字节交换（`PongDsiPanel.cpp:541-551`） | 27 侧无对应（K60 无外置背光 IC，走 DCS） | 已具备 |
| 命令提交方式 | `dsi_dcs()`（`PongDsiPanel.cpp:320`）+ `dsi_mdp_waits` 计数（`:67`） | `display.md:89-91` 要求 DSI/PWM 设备在 OS 服务下实现传输与编码，不能阻塞 | 已具备（16.6.1 把亮度请求交给工作循环，`K60Backlight.cpp:420-428`） |

---

## 5. 亮度属性主表（官方 `§4` + `drivers/sheng-backlight.md`）

锚点：`porting/display.md:89-100`（§4 整节）、`drivers/sheng-backlight.md:29-37`（属性表）、
`:41-44`（请求）、`:48`（尼特范围）。16.6.1 侧全部在 `drivers/PongAdreno/K60Backlight.cpp`，
常量在 `drivers/PongAdreno/K60BacklightCodec.h`。

| # | 属性 / 请求 | 16.6.1 | 27 侧 | 锚点 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 1 | `backlight-control` | `K60Backlight.cpp:339-341`（默认发，显式 `k60_backlight_control=0` 关）、`:350-351` 发布 | `AppleARMBacklight.cpp:355-356`（默认 1）、`:360` 发布 | `sheng-backlight.md:29-31`；`display.md:93` | 已具备（默认值语义相反，见 §6） |
| 2 | `IODisplayParameters.brightness`{min,max,value} | `:185-187`、`:193` | `:267-272`、`:274` | `sheng-backlight.md:31`；`display.md:93` | 已具备 |
| 3 | `IODisplayParameters.BrightnessMilliNits` | `:188-192`（`milliNitsFromLevel`） | `:273`（`milliNits` 字典） | `sheng-backlight.md:32`；`display.md:95` "iPadOS 27 还需要毫尼特" | 已具备 |
| 4 | `backlight-marketing-table` | `:211-217`（三值 `kMin/kMid/kMaxNits<<16`，OSData） | `:285-288`（同形） | `sheng-backlight.md:33`（"缺少时无法创建显示对象"） | 已具备 |
| 5 | `LmaxProduct` | `:218-221`（OSData 4 B） | `:290-293`（OSData 4 B） | `sheng-backlight.md:34`（"4 字节 16.16；为 0 时滑块表缩放为无穷大"） | 已具备（形状一致到字节数） |
| 6 | `LminProduct` / `LmidProduct` | `:222-229`（OSNumber） | `:294-300`（OSNumber） | `sheng-backlight.md:35-36` | 已具备 |
| 7 | `backlight-calibration-parameters`（六键 `lMin/lMid/lMax` × `Product/Panel`） | **缺**：`:230-246` 明确"Never publish a partial dictionary"，因为 20G81 的 CoreBrightness 读十个键不查 NULL（`0x1af030a28` 读、`0x1af030a5c..0x1af030a70` 循环），缺键即 `CFNumberGetValue(NULL)` → backboardd SIGSEGV（判据 int-236 brightness-4，lr `CoreBrightness+0xfbaa4`） | `:301-312` 发全六键，`:311` `setProperty` | `sheng-backlight.md:37`；`display.md:95` "校准参数" | **缺**（唯一实质缺口；27 是否仍需这个回避，见 §9 U1） |
| 8 | 请求 `brightness-nits`（有符号 16.16） | `:392-396`（`levelFromNits`） | `setProperties` `:400-428` → `levelForNits()` `:394-399` | `sheng-backlight.md:41-42`；`display.md:95` | 已具备 |
| 9 | 请求 `brightness` + `FadePeriod` | `:397-401`；上限 `kMaxFadeMs=5000`（`K60BacklightCodec.h:51`） | 同段；`kStepMs=16`（`:53`） | `sheng-backlight.md:43-44`（最长 5 s、每 16 ms 一步） | 已具备 |
| 10 | 未知属性（如 `brightness-nits-cap`）"返回成功、无效果" | **缺**：`setProperties()` `:384-433` 是 `brightness-nits` / `brightness` 的二分支，落空走 `:415-418` 的 `else`，仍用**未初始化**的 `goal` 继续 `publish(goal)`（`:428`） | `:400-428`（同一分支结构）；契约在 `sheng-backlight.md:46` | `sheng-backlight.md:46` | **缺**（27 的契约要求"成功且无效果"；16.6.1 会把未知字典当一次亮度写，等级未定义） |
| 11 | 尼特范围 | `K60BacklightCodec.h:45-47` `kMinNits=5 / kMidNits=140 / kMaxNits=400` | `:52` `kMinNits=2 / kMidNits=140 / kMaxNits=500` | `sheng-backlight.md:48`（2/140/500） | 已具备（值不同属于板级参数，不是契约差异） |
| 12 | 元类伪装（`getMetaClass` 返回 `AppleARMBacklight`） | `:134-158`，**只在 arm64 生效**（ptrauth 构建直接拒绝） | `:324-343`（arm64e 走 `gImpersonating` 标志 `:330-335` + 手写 `getMetaClass()` `:437-440`） | `display.md:102-107`（集成点 rg） | 改名（手法）/ 缺（arm64e 路径） |
| 13 | conformance 查询 | `:167-170` `conformsToAppleBacklight()` = `gAppleClass && metaCast("AppleARMBacklight")`；统计位 `native_backlight_request[4]`（`:361`） | 27 侧无独立"conformance"概念，伪装成功即 `stats[0]=4`（`:365`） | `display.md:102-107` | 已具备（16 线自建的可观测位，27 不需要但不冲突） |
| 14 | 虚拟平台丢弃请求 | 不涉及（K60 是物理机；`vmm-present` 只影响 27 的 MobileGestalt） | `sheng-backlight.md:50-54`：板级 ADT `vmm-present` → `IsVirtualDevice` → CoreBrightness 选 `VMBLControl` → **丢弃所有亮度请求** | `sheng-backlight.md:50-54`；`display.md:95-100` | 缺（见 §10 风险 R2：这是一条会静默吃掉整条亮度线的坑） |

---

## 6. 默认值语义：形态 A 在 27 上仍然成立，但方向相反

16.6.1 的代码默认是"发 `backlight-control`"，只有显式 `k60_backlight_control=0` 才关
（`K60Backlight.cpp:339-341`：`uint32_t controlArg = 1;` → `if (controlGiven ? controlArg != 0 : true)`）。
sheng 的 27 实现默认是"`control` 默认 1 且必须 `==1`"才发（`AppleARMBacklight.cpp:355-360`）。
两者在"显式传 0 就不发"这一点上一致，差别只在省略参数时的默认值。

交付形态 A 要求镜像带 `k60_backlight_control=0`（24 B）。27 上这 24 B 很贵（见
`DISPLAY-27-INTEGRATION.md` 的预算表），**建议**在 27 的代码里把默认值翻成 0
（与 sheng 相反、与形态 A 一致），让参数只在做实验时出现。这属于实现决策，
不是契约差异；列在这里是因为它直接改变 §8 的参数表。

`K60Backlight.cpp:316-338` 的注释与 `:339-341` 的代码自相矛盾（注释说「自 brightness-19/120hz-7
起默认发布」，代码是「默认 1 = 发布」——其实一致，矛盾只在于注释同时说「默认 0」）。
27 线以代码为准，并把注释改掉；这条已在 16 线记录过，不重复裁。

**Lead 裁决（2026-11-21）**：允许在 27 分支把 `K60Backlight.cpp:339` 的默认翻成 0，
三条约束：参数名不变（仍可 `k60_backlight_control=1` 覆盖）、提交信息写明
「27 默认由后端裁决」、本文记一行。

> **这是行为改变，不是优化。** 同一份 `K60Backlight.cpp` 在 16.6.1 上默认发布
> `backlight-control`、在 27 上默认不发布；判据 `conformance=… control=…` 的默认值
> 因此随 OS 版本变化，读日志时不能跨版本比较 `control=` 这一位。字节上省 23 B，
> 但省字节是结果，不是目的。

代码改法（27 分支，一行）：`uint32_t controlArg = 1;` → `uint32_t controlArg = 0;`，
上下文与判据见 `DISPLAY-27-INTEGRATION.md` §2.2。

交付形态（Lead 2026-11-21T16:58 裁）：**不直接改源码、不进 series**，以草案
`patches/proposed/0002-k60-backlight-let-the-backend-decide.patch` 提交（`git apply --check` 已过，
diff 只动 `:330-339` 的注释块与 `:339` 一行）。草案头写明「只适用 27 分支，16.6.1 封闭系列不得取」。

---

## 7. boot-arg 名称对照

| 意图 | 16.6.1（名字 / 字节 / 位置） | 27 侧（名字 / 字节 / 位置） | 判定 |
| --- | --- | --- | --- |
| 亮度服务总开关 | `k60_backlight=1`（15 B，`K60Backlight.cpp` 的 `bootArg`） | `sheng-backlight=1`（17 B，`sheng-backlight.md:58`） | 改名 |
| 发布 `backlight-control` | `k60_backlight_control=0/1`（23 B，`K60Backlight.cpp:340`） | `sheng-backlight-control=0/1`（25 B，`AppleARMBacklight.cpp:356`） | 改名 |
| 刷新策略 | `p120=1` / `vsync=120`（`PongDsiPanel.cpp:566-577`；默认已是 120 Hz，参数只用于退回 60） | `sheng-vsync=120`（`display.md:45`） | 改名 |
| 时序探针 | — | `sheng-dpu=1/2/3`（`DisplayTimingProbe.cpp:114-121`） | **缺** |
| 直扫 | — | `sheng-dpu-scanout=2`（`display.md:58`） | **缺** |
| 帧交 GPU | `pong_gpu_scanout=1`（17 B，board.toml） | `sheng-fb-gpu=1`（`NativeGOPWire.h:9`） | 改名 |
| 显示侧日志 | `k60_usblog=2`、`applog=1`、`k60_console_export=1`（13/9/20 B） | `log-display=1`（13 B，`sheng-backlight.md:62`） | 改名 |
| 亮度校准字典 | `k60_backlight_calibration`（29 B，**仅建议，尚未存在**） | 无（sheng 无条件发布） | 建议新增（见 §9 U1 回退） |
| 面板画布 | `k60_panel=0/1`（12 B，`patch 0210`） | 无 | 改名（27 无此概念） |
| 探针（帧/锁存）细节 | `gprobe=1`（9 B，`PongDsiPanel.cpp:568`） | 无（27 用 `sheng-dpu` 的级别） | 改名 |

27 上这些名字的取舍见 `DISPLAY-27-INTEGRATION.md` §3：沿用 `k60_*` 前缀
（先例 `k60bt`，见 `docs/engineering/BOOT-ARGS.md`），而不是照抄 `sheng-*`——
理由是本板的驱动是 `K60Backlight`/`PongDsiPanel`，用 `sheng-*` 名会让人以为代码来自 sheng 树。

**Lead 裁决（2026-11-21）**：时序探针用 **`k60_dpu=1`（9 B）**，`sheng-dpu` 只作为
官方页面里的别名出现（实现只解析 `k60_dpu`）。理由：板级参数统一 `k60_` 前缀、
跨线引用不与 sheng 命名混淆、省 2 B。

另外三项在 27 上**没有任何读者**，Lead 2026-11-21 已裁**整体删除**，不进命令行
（逐项检索范围与结果见 `DISPLAY-27-INTEGRATION.md` §4.4 C 组）：
`-v`（2 B，XNU 与 DarwinBoot22 均无）、`epoch=1793709100`（16 B，三处 grep 只有同名
sysctl 与 FDT `boot-epoch` 属性）、`launchd_unsecure_cache=1`（24 B，三处零命中）。

**落地口径（Lead 2026-11-21）**：A+B 合计 32 项 **626 B**，仍超上限 19 B；收口三选项
（删 `disable_exc_resource` → 603、删 `k60_console_export` → 605、删
`applog`+`k60_panic_reset` → 599，均已按「删项同时少一个空格」逐字节算过）在
`DISPLAY-27-INTEGRATION.md` §4.7，本线建议 O1 但不替平台线裁。

---

## 8. 与 16 线的帧率契约（补充读数，不算差异）

- 16.6.1 把 60 Hz→120 Hz 的切换推迟到首帧（`PongDsiPanel.cpp:576-578` `panel_120_switch_pending`），
  因为厂商 timing 包必须在面板已亮之后才接受。
- 27 的 `display.md:51-56` 记录 24A446 实测"300 秒内三次交换完成，无 panic，只到苹果标志"，
  **桌面未验证**。所以 27 侧"帧所有权协议能用"这件事，官方自己只证明了 3 次交换。
- 这两条合起来的含义：27 上第一帧到桌面之间还有一段未验证的路，本线不宣称覆盖它。

---

## 9. unknown 清单（每条：要什么证据 / 在哪取 / 取不到时怎么实现）

### U1 CoreBrightness 在 24A446 是否仍读那十个键

- **问题**：16.6.1 因为 20G81 的 CoreBrightness 读十键不查 NULL（`K60Backlight.cpp:230-246`）
  而**故意不发**六键字典。如果 24A446 已经把读取器改成"缺键走默认"，那 §5 第 7 行的
  `缺` 就可以消掉（发全六键是对的）；如果没改，发它 = backboardd SIGSEGV。
- **要什么证据**：`CoreBrightness` 二进制的字符串表里还存在
  `current-for-max-backlight`、`current-for-mid-backlight`、`hardware-max-current-limit`、
  `lMaxPanel`、`lMinPanel`、`lMidPanel`、`milliAmps2NitsScaleFactor`；以及读这些键的那个
  函数在 `CFNumberGetValue` 之前**有没有** NULL 分支。
- **在哪取**：24A446 的 IPSW → `System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e`
  → `ipsw`（或 `dyld_shared_cache_util -extract`）导出 `CoreBrightness` → `strings` 先判存在性
  → 命中后用 `otool -tV`（或 `llvm-objdump -d`）看调用点。能跑这套工具的机器是 macOS 构建机；
  **凭据只在本机，不写进仓库**。
- **本机现状（离线一手读数）**：`/opt/k60/sdk/iPhoneOS16.5.sdk/System/Library/PrivateFrameworks/CoreBrightness.framework/`
  只有 `CoreBrightness.tbd`（链接桩，`strings` 零行）；`/opt/k60/osroot/os.raw` 是 4.8 GB
  APFS 镜像（iOS 根，版本未确认，框架二进制在 dyld 共享缓存里，需要提取工具）；
  `E:/hackios/Device-Binaries/` 是 Android 机型目录，没有 CoreBrightness。所以**今天取不到**。
- **取不到时的实现与回退**：按 16.6.1 的保守形态实现——只发 BrightnessMilliNits +
  marketing table + Lmax/Lmin/LmidProduct，**不发**六键字典；字典放在
  `k60_backlight_calibration=1`（默认 0，29 B，只在实验镜像里出现）后面。
  回退判据与 16.6.1 形态 A 相同：`K60 BACKLIGHT: … conformance=0 control=0 stats=3,0,2047,2047`
  + backboardd 崩溃计数 0 + SpringBoard 行数。若开了 `k60_backlight_calibration=1` 之后
  backboardd 立刻 SIGSEGV，即判定 24A446 仍读十键，字典永久关闭。

### U2 K60 的 DPU 版本与 catalog 偏移

- **问题**：sheng 的探针按 `qcom,sm8550-dpu`、DPU 9.2 catalog、MDP 子块 `0xae01000+0x8f000`
  写常量（`DisplayTimingProbe.cpp:4-7`、`:30-39`）；本仓 `RESEARCH.md` 记 K60 的 MDP 是
  `0xae00000+0x84000`。K60 是 SM8475（sm8450 家族），与 sm8550 不是同一代 catalog。
- **要什么证据**：`/chosen` 或 `soc` 节点里 K60 的 `qcom,mdss-mdp` 兼容串与 `reg` 长度；
  以及 DPU catalog 版本（Android 侧 `dpuCatalog` 的 `major.minor`）。live FDT 已在
  `docs/research/display/RESEARCH.md`（MDP/MDSS 基址、双 DSI 名字），但 **catalog 版本未读**。
- **在哪取**：`/mnt/e/k60-work/artifacts/` 里的 live FDT dump（`fdtget -t s <dtb> /soc qcom,mdss-mdp`
  一类命令），或 Android `vendor_boot` 的 dtbo；两者都在本机。
- **取不到时的实现**：探针只读 INTF 侧（§1.4 已证明八个偏移完全重合，风险为零），
  VIG/CTL 侧先写成"按 catalog 表驱动"的形状（偏移进表、表可缺），表里 K60 那一行留空，
  探针读到缺表就打印 `K60 DPU: catalog unknown, INTF only` 并不写任何 pipe 寄存器。
  **不猜偏移**：写错 VIG 源地址会把扫描输出指到别处，比不探针更糟。

### U3 K60 的 `v_baseAddr` 与 stride

- **问题**：§10 风险 R1（256 MB 窗口压帧缓冲）取决于固件 framebuffer 的实际物理地址
  是否落在 `Boot` 的候选窗口里；而 `docs/plans/GPU-ENABLE-PLAN.md:546` 记
  "stride 是否 5760、`v_baseAddr` 是否页对齐，未核实"。
- **要什么证据**：`PE_current_console` 的 `v_baseAddr`/`v_rowbytes`/`v_width`/`v_height`
  四个值的一次打印（`patch 0210` 的 `vinfo` 就在手上，加一行日志即可），以及固件
  `Video[]` 三项是否都非零。
- **在哪取**：下一次上机（Lead 的 `step.device`）；或 Advanced Logger 里已有的
  `K60 PANEL: INTF…` 附近行（`PongDsiPanel.cpp:177` 打的是 INTF 寄存器，不含基址）。
- **取不到时的实现**：本线**不改** `Boot` 的窗口逻辑（那是平台线的文件），只在
  `DISPLAY-27-INTEGRATION.md` 的预算/风险表里留下"帧缓冲地址必须由 Lead 核对"的钩子。

### U4 27 的内核是否 arm64e（决定元类伪装路径）

- **问题**：`K60Backlight.cpp:134-158` 的 vtable slot 替换在 ptrauth 构建里被拒绝；
  sheng 为此写了 `gImpersonating` 标志 + 手写 `getMetaClass()`（`:324-343`、`:437-440`）。
- **要什么证据**：27 内核的构建目标架构（`XNU arm64e` 还是 `arm64`），以及 `kmod_info`
  里的 `ptrauth` 标志位。
- **在哪取**：`docs/ROUTE-A-18-UPSTREAM.md` 的 profile 表；或构建产物
  `otool -hv` 的 `cpusubtype`（离线可读，不需上机）。
- **取不到时的实现**：直接把 sheng 的 arm64e 路径搬过来（`gImpersonating` + 手写
  `getMetaClass()`），它在 arm64 上也安全（退化成一个普通返回）。

---

## 10. 风险清单

按"会不会让屏幕黑掉"排序。

### R1 装载窗口压到帧缓冲（**显示相关，不排除**）

- `k60-gates/docs/research/ios27/F2-PARSER-NOT-THE-CAUSE.md:72` 记录：`Boot` 分配 256 MB
  `EfiLoaderCode` 窗口、地址与 `Kernel.Base & 0x3fff` 同余，然后拷 93 MB。
- 代码侧边界（我读到的）：`DarwinBoot.c:596` 用 `AllocatePages(AllocateAddress, …)`；
  `:684-690` 逐段跳过与 `Video[0]`/`Video[2]*Video[4]` 重叠的候选（`if (Video[0] && Video[2] && Video[4])`
  且 `Start < FbEnd && Fb < Stop` 才 `continue`）；候选下界是 `0x100000000`（`:660-670`）。
  ⇒ **守卫只在 `Video[]` 三项都非零时生效**，且只在 ≥4 GiB 里找窗口。
- 所以真实条件是：`Video[]` 有零（守卫整段跳过）**且** 帧缓冲落在 ≥4 GiB。
  K60 的帧缓冲按同 SoC 异板 zizhan 是 32 位地址（`0xb8000000`，`RESEARCH.md:65`），
  但**本板未核实**（U3）。若本板帧缓冲也在 32 位，R1 的概率低但**不是零**：
  `Video[0]` 若被固件填 0，守卫跳过，而 256 MB 窗口仍在 ≥4 GiB 找——那不会压到 32 位地址。
  真正会压到的是"`Video[0]` 非零但 `Video[2]/Video[4]` 为 0"，此时守卫跳过、窗口仍可能落在
  帧缓冲上（如果帧缓冲恰好在 ≥4 GiB）。
- **取证**：5 s 倒计时内按键取消自动计时、手选 entry 0，读 Advanced Logger 里 `Video[0]`
  与窗口地址；一次就够。
- **本线的处置**：不改 `Boot`（不是本线的文件），把它作为"黑屏候选之一"留在表里，
  证据路径写在上面。

### R2 `vmm-present` → `VMBLControl` 静默丢弃亮度请求

`sheng-backlight.md:50-54`：27 上若板级 ADT 带 `vmm-present`，MobileGestalt 会答
`IsVirtualDevice`，CoreBrightness 选 `VMBLControl`，**所有亮度请求被丢弃且不报错**；
`scripts/appsync/BacklightMode.m` 只改 backboardd 模式 1 而不是 3。
K60 的 ADT 是我们自己生成的（`tools/mkadt.py`），所以这条**可控**：27 的 ADT 里不能有
`vmm-present`。这是本线要交给平台线的唯一一条硬要求，判据是
MobileGestalt 的 `IsVirtualDevice` 答 false（或 backboardd 日志里不出现 `VMBLControl`）。

### R3 DPU 常量照抄 sheng 会指错扫描输出

见 U2。`sheng-dpu=3` 会**写**寄存器（`DisplayTimingProbe.cpp:100-110` 的 level 3 分支），
在 K60 上若 catalog 偏移不对，等于把扫描输出地址写到未知寄存器。处置：
K60 的探针 level 上限先只到 2（只读），level 3 必须在 catalog 核实后才开。

### R4 亮度未知属性走未初始化分支（**已撤回：误读**）

~~原文：`K60Backlight.cpp:415-428` 落空分支用未初始化 `goal` 发布一次亮度，
滑块跳变或黑屏，必须在 27 实现里改成「未知键直接返回成功」。~~

复核结果（2026-11-21，本树 HEAD，`git status drivers/` 干净）：请求只有三支，
在 `:392-404`——`brightness-nits`（`:392-396`）、`brightness`+`FadePeriod`
（`:397-401`）、`else { return kIOReturnSuccess; }`（`:402-404`）。`goal` 只在前
两支赋值，**没有任何路径把未初始化的 `goal` 交给 `publish(goal)`（`:428`）**。
被误当作落空分支的 `:415-418` 是「非 nits 请求」的**日志**分支（条件在 `:410`
`if (nitsRequest)`），不是请求落空分支。`grep -n setProperties` 全文件只有 `:384`
一处定义，不存在第二份旧实现。

- **判据**：`git show HEAD:drivers/PongAdreno/K60Backlight.cpp | sed -n '384,404p'`。
- **教训**：把日志分支的 `else` 读成了请求分支的 `else`；引用行号必须同时引用
  产生它的 `if` 条件行。
- **处置**：不再当缺陷。这个函数里唯一值得改的是日志字段
  （`:416-417` 把 `goal` 打了两次，无法从日志区分请求值与等级），已单独提成
  `patches/proposed/0001-k60-backlight-log-requested-level.patch`，
  不混进本文的预算/差异结论。

### R5 补丁栈与 27 驱动形态互斥

§1.1。0210/0211 改的是 XNU 自带的 `MiniIOMobileFramebuffer`/`MiniIOSurface`；
27 官方用独立驱动（`NativeLegacyDisplay.cpp`）。两者同时存在会争 `PE_current_console`
的所有权。处置：27 上二选一，且这个选择要在 `xnu` 线的 patch series 里体现，不是显示线能单独定的。

### R6 面板原生命令序列未全量回放

§4 第 3 行：16.6.1 只发 `0x11/0x29/0x51`，FDT 的 1534 B 没有回放。当前能点亮，
但 27 若在更早的时序上要求完整序列（例如 DSC 参数、`0x2f` 一类），缺包会表现为
"有背光无图像"。判据：`K60 PANEL: bring-up complete` 之后有 `first frame presented` 但屏幕黑。
处置：真出现时再按 live FDT 补 `0x11` 之前的包，不回放全部 1534 B（字节与时间都不值）。

---

## 11. 本次不裁决的条目

1. **16.6.1 与 27 的 CoreBrightness 版本差异**（20G81 vs 24A446）只影响 U1；
   在拿到 U1 证据前不改任何发布逻辑。
2. **1534 B on-command**：Lead 给的已知事实是"三档各 1534 B、`@0 vs @1` 差 6 字节、
   `@0 vs @2` 差 4 字节、`@1 vs @2` 差 3 字节；off 18 B 三档相同"。本表只把它记为
   "未回放"（§4），不把它写成 27 的差异——因为它不是版本差异，是 16 线的既有选择。
3. **sheng 的 KTZ8866 通路**：K60 没有外置背光 IC，见 `DISPLAY-27-INTEGRATION.md` §2 的
   GeniI2c 结论；不列进差异表，避免把"不适用"写成"缺"。
4. **`conformance=0` 的那次实测**：`reply-display-20261115.md` 记的判据是
   `conformance=0 control=0`，而形态 A 要求 conformance 查询**真答**。两者不矛盾
   （`conformance=` 打的是 `conformed`，即伪装是否成功；`=0` 表示未伪装，而
   `brightness-nits` 仍然被接受），但 27 线要以"未伪装时亮度仍生效"为验收点，
   不能只验 `stats[0]`。这条留作 27 上机第一个检查项。
