# iOS 27 交棒后黑屏 — 八步证据（blackscreen）

- 仓库：`Emilelu/UniXNU-mondrian`，分支 `fix/ios27-black-screen-muse-20261122`（基点 `diag/menu-hold-20261121` @ `6893c8f92e561e2cf600d71b13b95dcf3f801920`）
- 机型：Redmi K60（mondrian，SM8475，arm64e，4 KiB 页），XNU 12377 / iOS-iPadOS 27.0.1 / 24A446
- 机器可读记录：`docs/research/eight-step/blackscreen-27.toml`（`[hardware.blackscreen]`，步骤 ①–⑦；步骤 ⑧ 由 Lead 上机后写）
- 证据分层：每条结论标 **有证据 / 有推断 / 不知道**。没有核实的参数一律标不知道，不猜。

## 症状（真机已确认，不是推测）

1. 固件界面完全正常：菜单、阶段条、日志都显示，10 秒后自动引导 27 内核条目。
2. 一交棒进入内核（ExitBootServices 之后）屏幕立刻全黑，之后一直黑。
3. 固件在 ExitBootServices 之前加了整屏填红 + `dc civac` + `dsb sy` 和一行 PRE EXIT
   文字阶段标记（uefi-mondrian commit `c6f2c64`），真机仍然是全黑 —— 连红色都没出现。
4. 内核侧控制台只有 ramoops（写在 `0xA7000000`，复位即失，读不到），
   USB CDC / EP0 通道刚移植进来但从未验证成功；串口日志 0 字节是常态。
5. 内核里已确认有 `_pong_ramoops_console_init` / `_write`、`k60_usblog_*` 等符号，
   但没有任何证据表明内核真的执行过（没有一次拿到过任何一个字节的内核输出）。

## ① 同型

| 记录 | 最好状态 | 与 K60 iOS 27 的差距 |
|---|---|---|
| Emilelu 主线（iPadOS 16.6.1-20G81 / Darwin 24）— `unixnu.com/devices/mondrian`，porting.toml `5d8a09a5…` | Darwin 24 到桌面（cand7/cand15：SpringBoard、桌面/状态栏/App Store/Settings/Dock 可见；Goodix BERLIN/9916R 单指触摸合格）；1440×3200、60 Hz 软件帧缓冲（`patches/xnu/0210-k60-display-native-canvas.patch:10-31`、0211/0213/0236，`patches/xnu/series:86,87,89,115`） | 主线是 16.6.1 / Darwin 24，不是 iOS 27。27 线是单核 stage-0，存储/显示/GPU 关闭，尚无桌面 |
| ZxbMsl160918（Darwin 24）— `unixnu.com/devices/mondrian-zxbmsl160918`，porting.toml `c39ff292…`；**不知道其 GitHub 仓库 URL**（该用户下无 UniXNU-mondrian 仓库） | 只到入口探针三条带：Entry.S 绿条 → 内核入口蓝条 → MMU 开启前品红条；Display `planned`、Storage `planned`，无桌面 | 只有 Darwin 24 入口级证据。其 panic-screen 失效原因（地址写死参考内核）警告：不要把 Darwin 24 的探针地址用于 27 内核 |
| diting（Redmi K50 Ultra，SM8475，Darwin 24）— `unixnu.com/devices/diting`，porting.toml `22875f51…` | iPadOS 18.7.10 / Darwin 24 到桌面，device-verified；1080×2412、stride 4320、DCS 背光，`DITING SCANOUT status=0`；Goodix GT9916 触摸 | 同 SoC、同 Darwin 世代的“帧缓冲活着 + 桌面”范本。差异：diting 用 `DitingPlatform24` + 1080×2412 面板；K60 是 1440×3200、DSC 命令模式面板，几何/stride/DSI 配置不能照抄 |
| pong（Nothing Phone (2)，SM8475，Darwin 24）— `unixnu.com/devices/pong-xz1c` | Darwin 24，1080×2412、stride 4320、DCS 背光、原有显示服务；与 diting 同源 | K60 显示栈在 Darwin 24 线上本就复用 Pong 系路径；27 线需核对该路径在 24A446 ABI 下是否仍成立 |
| sheng（Xiaomi Pad 6S Pro，SM8550，官方 iPadOS 27 参考板）— `unixnu.com/devices/sheng` | iPadOS 27.0.1（24A446），`GopFramebuffer`，Display `implemented` | **唯一的官方 24A446 显示参考**，但不是同 SoC（SM8550 vs SM8475） |
| rsarigul15-commits — `unixnu.com/devices/mondrian-rsarigul15-commits` | 只有占位页，无任何实现/启动证据 | 无参考价值 |
| XDA / GitHub topic | XDA 搜索 Redmi K60 mondrian iOS UniXNU 无相关帖；`topic:unixnu` 共 164 仓，无其他 mondrian 设备仓；unixnu.com 设备索引称 mondrian 有 6 个来源，本次只辨认出 3 个，其余 3 个**不知道** | — |

## ② 官方

| # | 要求 | 来源 |
|---|---|---|
| R-1 | 启动分 Stage 1–7；Stage 4 DarwinBoot 打印 `DARWINBOOT:` 行与 framebuffer base/width/height/depth；Kernel entry 无日志时先查启动参数、串口选择、帧缓冲地址。红在 EBS 前不出现 ⇒ 故障在 Stage 4 完成之前 | `unixnu.com/porting/bring-up` §Stage 1–7；Failure isolation 表 L166–187 |
| R-2 | xnu 条目必需 `kernel.macho` + `kernel.macho.adt`；DarwinBoot 把内核段复制到连续物理窗口（默认 256 MiB）、构造 `boot_args`、退出 boot services | `unixnu.com/guide/boot` §5、§6；中文 `unixnu.com/zh/guide/boot` |
| R-3 | 绿条：`DarwinEnter` 在 ExitBootServices **之后**、MMU 关闭、跳转 XNU **之前**画在帧缓冲顶部 1/16；绿 → 蓝（MMU 关时内核入口已跑）→ 品红（MMU 开启前一点）；stage 3 无条，MMU 开启后等 `--reset-delay` 秒再复位；`panic_screen=true` 运行 `scripts/patch-xnu-entry-probe.py --panic-screen --no-reset`，panic 屏与 stage-4 探针共用 `_start` 之后零填充，二者不能同时启用；无探针输出时检查记录的 framebuffer base 与 stride | `unixnu.com/guide/debugging` §Green bar L340–344、§Color bars L370–385、§Entry probe reset L387–412、§Panic screen L313–338；`unixnu.com/guide/boot` L165–181 |
| R-4 | 先立固件扫描输出（菜单显示正确、GOP 几何与帧缓冲范围对照固件内存映射与板级 DTS、在内核交接期间保留当前扫描缓冲区），再启用 XNU 显示后端（`GopFramebuffer` + `NativeLegacyDisplay.cpp`，`CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`）；帧缓冲必须是 8 位 BGRA；`dpu-scanout=2` 是实验功能、默认关闭 | `unixnu.com/porting/display` §2 L34–59、§Read the display pipes L64–86 |
| R-5 | payload 写法 `[-v, serial=3, debug=0x14e]`；板级 UART 引脚与波特率记录在设备页上；支持 USB device 模式的板子可以暴露 CDC ACM 串口代替；官方 USB 调试终端 `scripts/debug_terminal.py` 实现 giulia 协议 2，只改 USB ID 不能提供协议兼容性 | `unixnu.com/guide/debugging` §Serial console L133–167、§Log sources L109–131；`unixnu.com/xnu/boot-arguments` |
| R-6 | `boot-progress=1` 启用监视（30 秒无活动或 120 秒上限时冻结页面以便拍照）；`boot-progress=2` 持续运行；脉冲条为面板底部 32 像素绿色条，格式含 `@<base>`（帧缓冲基址）与 `B<bind>`（绑定计数/结果/深度） | `unixnu.com/guide/debugging` §On-screen diagnostic page L189–210、§Pulse strip L282–311 |
| R-7 | iPadOS 27 显示（sheng 参考）：选 `GopFramebuffer`；`CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`；`vsync=120`；`dpu-scanout=2` 默认关闭；`backlight=1`；`ca-fb-8bit=1` 使 WindowServer 呈 8-bit BGRA；`backlight-marketing-table` 缺失则无法创建显示对象；`fb-half=2`（macOS 27.3） | `unixnu.com/devices/sheng` Display 节；`unixnu.com/porting/display` §5 L126–172；`unixnu.com/guide/build-kernel` §Defconfig flags L133–184 |
| R-8 | 构建目标 `SDKROOT=iphoneos`、`ARCH_CONFIGS=ARM64`、`MACHINE_CONFIGS=BCM2837`（选 4 KiB 页布局）、`KERNEL_CONFIGS=DEVELOPMENT`；顺序 defconfig → fetch/status → build kernel → prelink → package/firmware/payload | `unixnu.com/guide/build-kernel`（288 行）；`unixnu.com/building` §3 |
| R-9 | 日志抓取三段式：UEFI 菜单（GOP 显示、Advanced Logger、QR 插件）→ XNU 入口（UART 或帧缓冲诊断）→ 存储（预留日志区、内核写入器、Linux 或 recovery 读取器）；ExitBootServices 之后的 XNU 执行用步骤 3 的抓取方式，固件 QR 日志覆盖不到 EBS 之后 | `unixnu.com/porting/log-capture` §1–6 |

**有证据的关键分叉：** 绿条是否出现（R-3）是下一步必须先确认的一个二元事实 —— 任务上下文未说明，**不知道**。若绿条出现而红不出现，则填充点与 DarwinEnter 写的是不同缓冲/不同时刻；若绿条也不出现，则故障更早（EBS 本身或 EBS 前的 GOP 状态）。

## ③ 反编译（本机参数，repo-local）

| 参数 | 值 | 来源 | 状态 |
|---|---|---|---|
| 面板 | 1440×3200，cmd mode，60 Hz + 120 Hz（面板原生 120 Hz） | `docs/engineering/ANDROID-HW-TRUTH.md` display 表（live Android/root adb，2026-11-10） | 有证据 |
| GOP PCDs | width 1440、height 3200、depth 32 | uefi-mondrian `Platforms/Xiaomi/mondrianPkg/mondrian.dsc:61-63` | 有证据 |
| GOP 像素格式 | `PixelBlueGreenRedReserved8BitPerColor`（BGRX32），否则 `EFI_UNSUPPORTED` | uefi-mondrian `Platforms/Xiaomi/DarwinBootPkg/Driver/BootVideo.h` | 有证据 |
| 帧缓冲基址 | **静态无值**，运行时 `Video[0] = Gop->Mode->FrameBufferBase` | `BootVideo.h`；`DarwinBoot.c:960`、`:1027-1028`、`:1043` | 不知道（静态） |
| stride | `Video[2] = PixelsPerScanLine × 4`；若 scanline = 1440 → 5760 B/行 | `BootVideo.h` | 不知道（静态）；只校验 ≥1440 |
| 满帧大小 | `Video[2] × Video[4]`；1440×3200×32 = 18,432,000 B（0x1194000）——推导值，不是仓库常量 | `DarwinBoot.c:573`、`:724-725`、`:1073` | 有推断 |
| `Video[6]` 布局 | [0]=base、[1]=1、[2]=rowBytes、[3]=width、[4]=height、[5]=32 | `BootVideo.h`；`DarwinBoot.c:1027-1028` | 有证据 |
| 红填充 | `FillScreen(Video, 0x00FF0000)`，`dc civac` 每 64 B + `dsb sy`；随后 `PRE EXIT`、`EXIT CALL`、`ExitBootServices` | uefi-mondrian `DarwinBoot.c:561-588`、`:592-598`、`:1063-1067`（提交 `c6f2c64`，本次已核实） | 有证据 |
| `FlushRange` | `dsb sy` + `ctr_el0`  derived cache line 的 `dc civac` + `dsb sy` | `DarwinBoot.c:50-60` | 有证据 |
| 诊断文字 | 白 `0xFFFFFFFF`、黑框 `0xFF000000`、5×12 字形 4 倍缩放、`FlushRange` 整帧 | `DarwinBoot.c:504-541` | 有证据 |
| SimpleFbDxe | **缺席**：`mondrian.dsc:130-143` 与 `mondrian.fdf` 均无其 INF | `mondrian.dsc`、`mondrian.fdf`（全文已读） | 有证据 |
| GOP 提供方 | `USE_CUSTOM_DISPLAY_DRIVER = 1`；实现在 `QcomPkg/Extra.fdf.inc` 之外，未读到 | `mondrian.dsc:26`；`mondrian.fdf` | 不知道 |
| `video_region` | 0x85700000、0x00700000（7 MiB） | uefi-mondrian `MemoryMapLib.c:22` | 有推断：7 MiB < 17.6 MiB 满帧，不可能是帧缓冲；文件也未称它是 |
| Display Reserved | 0xB8000000、0x02B00000（43 MiB） | `MemoryMapLib.c:52` | **不知道**：与 sheng/fuxi/cupid 的值完全相同，出处未核实，禁止代入 mondrian |
| DSI / DSC | 仅 "DSC 后 720×3120"、`panel-framerate=0x78`、`mdp-transfer-time-us=0x1efd` | `docs/state/STATE-2026-11-07.md` §9 | 有推断（薄）：无 DSC slice/line 参数，无 DSI lane 数/时钟，无面板型号 |
| 交棒 arena | [0x900000000, 0xa40000000)，0x140000000 = **5 GiB**（注释称 4 GiB 是旧文案） | `dts/mondrian.dts:29-32`；`board.toml:127-129`；`MemoryMapLib.c:94` | 有证据 |
| Owned window | 0x120000000 = 4.5 GiB（止于 0xa20000000，在 arena 内） | `board.toml:257` | 有证据 |
| ramoops | 0xA7000000，控制台 2 MiB（总保留 4 MiB），头 12 B `{sig,start,size}`，sig `0x43474244` | `patches/xnu-12377/0546-k60-ramoops-console-27.patch:152-162`；`MemoryMapLib.c:38`；live FDT `ramoops@0xa7000000 reg = <0x00 0xa7000000 0x00 0x400000>`，`pmsg-size 0x200000` | 有证据（三处独立 repo-local 来源一致） |
| ramoops 初始化点 | `arm_init`，`arm_vm_init` 返回后立即调用 `pong_ramoops_console_init()`；`ml_io_map_wcomb`，头清零后写 sig（`CleanPoC` + `dsb sy`） | 0546 hunk `@@ -585,6 +699,8 @@`、`:94-123` | 有证据 |
| ramoops 写入器 | 钩在 `serial_console.c` 的 `console_write()` / `console_write_unbuffered()` 头部；`console_init()`（`startup.c:582`）之前无人调用 | 0546 `:187-200`；`docs/research/ios27/CONSOLE-GAP.md:246-261` | 有证据 |
| ramoops 读数器 | `RamoopsDumpDxe`，`mondrian.dsc:141`，只读；AT 探针可读性，打印头 1200 B + 尾 2400 B；hold 循环代码 20 s，注释称 12 s（内部不一致） | `RamoopsDumpDxe.c:36-37,75-86,168,178-179` | 有证据 |
| ramoops 寿命 | DRAM only —— 任何复位 / 长按电源 / 掉电都清掉；只在 warm / 同启动内可读 | `CONSOLE-GAP.md:1-5`；`STATE-2026-11-07.md` §13.3 | 有证据 |
| 27 `kernel_args`（8 项） | `-v`、`serial=3`、`debug=0x14e`、`kt_fixed_zones=120`、`-no_slto_panic`、`use_contiguous_hint=0`、`amfi_get_out_of_my_way=1`、`k60_fontscale=3`；无 `k60_usblog`、无 `log=1`、无 `ramoops=`、无 SMP 参数 | `board.toml:396-406` | 有证据 |
| 27 overrides | `chip_id` 8140（T8140/iPhone17,2）vs 顶层 8015；`driver_records` `DEVELOPMENT_ARM64_BCM2837` vs 顶层 `DEVELOPMENT_ARM64_PONG`；components 只有 `ArmDTPlatform, ArmCpu, XnuPrelink`（无 PongUfs）；`cpus = 8`、`timeout = 10` | `board.toml:350-419`、`:233`、`:210`、`:223` | 有证据 |
| 入口探针 / panic 屏 | **无激活键**，只有注释：蓝（MMU 关时内核入口）、品红（MMU 开启前一点）、MMU 开启后 6 秒 PSCI 复位；`entry_probe_reset_delay = 6` 被注释掉；"panic screen stays off … refuses to patch ours" | `board.toml:109-125` | 有证据 |
| 0542 色带（MMU 关） | `_start` row 256 红 `0xFFFF0000`、row 272 黄 `0xFFFFFF00`、row 288 青 `0xFF00FFFF`，各 64 px × 16 行，`dsb sy`、无 `dc civac`；读 `boot_args.Video` base `[args+0x28]`、rowBytes `[args+0x38]` | `patches/xnu-12377/0542-k60-f2-start-breadcrumbs.patch:14-35,45,53,61` | 有证据 |
| 0543 面板控制台 | 需 `-v` + `v_depth==32` + base/width/height 非零；置 `v_baseAddr \|= 1`、`v_display = 0`，`PE_initialize_console(text)` + `kPEAcquireScreen` | `patches/xnu-12377/0543-k60-ios27-panel-console.patch:16-24` | 有证据 |
| 0544 字号 | `k60_fontscale=3` → 24×48 px 单元，1440×3200 上 60×66 单元 | `patches/xnu-12377/0544-k60-console-font-scale.patch`；`board.toml:405` | 有证据 |
| 0551 bootbar | arm_init 后绿 `0x0000ff00`、bsd_autoconf 后蓝 `0x000000ff`，64×64 块在 (8,8)，`ml_io_map(stride×height)`，depth < 32 时拒绝 | `patches/xnu-12377/0551-k60-bootbar-27.patch:18-45,55-57,69-71` | 有证据 |
| 0547 USB log | DWC3 0x0a600000、GCC 0x00100000、eUSB2 PHY 0x088e3000、SMMU 0x15000000、QSCRATCH 0x0a6f8800；CDC-ACM VID 0x1209/PID 0x0001；`k60_usblog=0` 惰性 / `1` 探针 / `2` 全 CDC；init 在 `arm_init`，start 在 `bsd_autoconf` | `patches/xnu-12377/0547-k60-usblog-ep0-27.patch:81-128,165-172,779-796,1328-1368` | 有证据（补丁自述，未在真机独立测量） |
| 27 `dts/mondrian.dts` | 235 行，**无** display、framebuffer、reserved-memory、ramoops 节点；只有 `memory@900000000`、smem 0x80900000（2 MiB）、adsp-region 0x9fd00000（0x3100000） | `dts/mondrian.dts`（全文已读） | 有证据 |

**颜色字节说明（已解决，不是冲突）：** 固件红 `0x00FF0000`、0542 红 `0xFFFF0000`、0551 绿 `0x0000ff00` / 蓝 `0x000000ff` 在 BGRX（`BootVideo.h` 要求 `PixelBlueGreenRedReserved8BitPerColor`）下一致：字节序是 B,G,R,X，差异的最高字节是 reserved 字节，不是 alpha。

**已核实的配置冲突：** 0547 的全 CDC 由启动参数 `k60_usblog=2` 开关（0547 `:10-11,165-172`，缺省 → 0 → 惰性），而 27 `kernel_args` 里根本没有 `k60_usblog`（`board.toml:403-406`）。`serial=3` 被记为替代品（`board.toml:402`），但 0543 自己写着 "serial=3 but no serial hardware"。USB 在 27 飞行上不枚举是**配置关闭**，不是内核生死判据。

## ④ 广域

`UniXNU/UniXNU components.toml`（1121 行，**28 个组件，不是任务简报说的 25 个**，SHA `69a8cff8…`）逐个核对：

- **GopFramebuffer（L405–443）：可用作显示提供方** —— `os_abi` 含 `ipados-27.0.1-24A446`；源 `NativeMobileDisplay.cpp`、`NativeLegacyDisplay.cpp`；`verified_devices` 只有 sheng（SM8550）。但它只是显示提供方、**不是文本控制台**（`video_console`/`console` 检索 0 命中）；mondrian 27 defconfig 关掉了 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` 与 `CONFIG_XNU_NATIVE_MOBILE_DISPLAY`；它依赖正确的 GOP 交棒（base/stride/format），而这正是可疑点。
- **DarwinBoot（L116–148）：部分可用，仅加载器侧信号** —— `DarwinEnter` 在 ExitBootServices 之后画顶部 1/16 绿条，是交棒判别器，不是内核控制台，不能打印 panic。
- **VirtioMmioConsole（L620–658）：不可用** —— 目录里唯一的 console 组件，但传输是 VirtIO 1.2 MMIO，QEMU 专属；目录里没有 UART/串口控制台组件。
- **Adreno740 / AdrenoMetal / Sm8550Platform：不可用** —— A740/SM8550 专属，mondrian 是 Adreno 730/SM8475；目录里**没有 `Sm8475Platform` 组件**。
- 其余 24 个（ArmCpu、ArmDTPlatform、ArmVirtPlatform、ShengUfs、ShengHidInput、ShengNovatekTouch、QcomGeniSpi、SoftwareAES、AppleKeyStoreState、RamBlock、VirtioMmioBlock、XnuPrelink、AdrenoPM4、AdrenoFirmware、ArmSmmu4K、AirNir、VerifiedRoot、Ath12kWifi、QcaBluetooth、QcomDwc3、ShengPreflight、QcomBaseband）：**不可用**，与早期帧缓冲/控制台无关。
- **不在目录里：** BootProgress（sheng 自有，`UniXNU/UniXNU-sheng kits/sheng/BootProgress.c`，82 KB + 探针，需移植）；NativeLegacyDisplay（不是独立组件，是 GopFramebuffer 内的 `NativeLegacyDisplay.cpp` + `scripts/build-gop-legacy-display.py`）；入口探针 + panic 屏（框架脚本 `scripts/patch-xnu-entry-probe.py` + `scripts/xnu-panic-screen.c`，不是组件；mondrian 27 上 panic 屏被 `board.toml:234-238` 拒绝，因 `panic()` 地址对参考内核写死）。
- `unixnu.com/zh/drivers/repositories`：28 官方 + 12 社区 + 9 设备分支，结论同上；唯一社区显示 fork 是 `RigoLigoRLC/unixnu-nativemobiledisplay`（SM8250 平板，非 SM8475）。
- 同 SoC SM8475（pong/diting/zizhan）全用 pong 原生栈（PongPlatform/DitingPlatform、DCS 背光、GPU scanout、vendor DXE/GOP 二进制），不用 GopFramebuffer。
- **唯一可复用的先例：** vermeer（SM8550，iOS 27/24A446）选 GopFramebuffer + 自定义 `vermeer-framebuffer-console.patch`（`startup.c` 插 `switch_to_video_console()` 与 `initialize_screen(NULL, kPETextScreen)`，SHA `28a2d0ac…`）。其注释写明：`PE_create_console()` 选 `kPEGraphicsMode`，`gc_pause()` 置 `disableConsoleOutput`，丢掉每个 `kprintf`/`IOLog`；无串口的板子上这会让 `IOFindBSDRoot` 的 30 秒等待与 `ROOTDEVICETIMEOUT` 全无输出；`kPETextScreen` 调 `gc_enable(TRUE)`，`vcputc` 才能画滚动日志；"Nothing on ARM calls it, which is why the ARM ports show nothing."
- rothko（Redmi K70 Ultra，MT6989，不同 SoC）是唯一的 CMD 模式 DSI 面板先例：每帧需主动推送，NativeMobileDisplay 在合成后显式推送；1220×2712×32 GOP FB。

**④ 结论：没有可直接用的官方组件能给 mondrian 一个早期视频控制台；vermeer 的补丁是模板，GopFramebuffer 是可并行启用的显示提供方。**

## ⑤ 方案

| # | 改动 / 实验 | 位置（file:line） | 依据（①–④） |
|---|---|---|---|
| P1 | 一次上电全程拍屏 + 抓固件 DEBUG 日志：核对 `video base=` / `PRE EXIT` / `EXIT CALL` 任一行是否出现过；核对烧录 FD 是否含 uefi-mondrian `c6f2c64`；核对 `DARWINBOOT: video base=0x…` 行是否存在 | uefi-mondrian `DarwinBoot.c:1043,1063-1067` | ① Zxb 三条带；② R-1/R-3；③ FillScreen/HandoffStage 已核实 |
| P5+P2 | 一次固件构建、一次上电：`FillScreen` 与 `ExitBootServices` 之间插 `gBS->Stall(5*1000*1000)`，相机对面板 + 暗室检查；同时读出 `DARWINBOOT: video base=0x… display=… row=… width=… height=… depth=…` 一行，与 ABL splash 地址及菜单 GOP 模式逐项比对 | uefi-mondrian `DarwinBoot.c:1063-1066` | ③ 面板 1440×3200 cmd mode + DSC；④ rothko CMD 面板先例 |
| P3 | 一次固件构建、一行改动：把 `FillScreen` 内联 `dc` 循环换成已有的 `FlushRange(Video[0], Video[2]*Video[4])` | uefi-mondrian `DarwinBoot.c:583-586` → `:50-60` | ③ `FlushRange` 读 `CTR_EL0`、对齐、前后 `dsb sy`，`FillScreen` 硬编码 64 B 步长 |
| P4 | 一次固件构建、一行改动：填充常量 `0x00FF0000` 改为 `0xFFFF0000` | uefi-mondrian `DarwinBoot.c:1063` | ③ `DiagDrawVideo` 只用最高字节 `0xFF` 的常量 |
| P7 | 一次上电：填充前把覆盖 `Video[0]` 的内存图描述符（类型 + 属性）打印进 `video base=` 行 | uefi-mondrian `MemoryMapLib.c`；`DarwinBoot.c:GetMap` / `AllocateWindow` | ③ `dts/mondrian.dts` 无显示保留区；`MemoryMapLib.c` 未读到 FB 描述符类型 |
| 绿条 | 一次上电，记录绿条是否出现（见 §8 H1） | 框架 `DarwinBoot`（R-3） | ② R-3 |
| — | **本分支本次无代码改动**（见下） | — | — |

**为什么本分支本次没有代码改动（有证据）：**

- P1/P3/P4/P5/P7 的改动点全在 **uefi-mondrian** 仓库（`Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c`），不是本仓库。按任务要求，不在本分支静默编辑另一个仓库；上述提案是给 uefi-mondrian 分支的改动清单，含 file:line。
- 本仓库的 0542/0543/0546/0551 仪器已在 27 系列内（`patches/xnu-12377/series`），缺的不是写入器，是内核到达它们的证明（§8 H5/H6）。
- GopFramebuffer 启用（defconfig + `board.toml` components）不是一变量判别实验，且在 SM8475/27 上未验证，推迟到首输出判别之后。
- vermeer 式 framebuffer-console 补丁移植需 xnu-12377 `startup.c` 上下文核对，源码不在本仓库内，本次不盲目加补丁。
- 入口探针（`entry_probe_reset_delay`）在 27 内核上能否打补丁**不知道**（全部色带证据是 Darwin 24；iOS 27 上 `patch-xnu-entry-probe.py` 是否拒绝 27 内核未验证），盲目启用是猜测。

## ⑥ 深挖（未解项，每项可证伪）

| 未解项 | 若 A 则… / 若 B 则… | 验证方法 |
|---|---|---|
| U1 绿条是否出现 | 出现 ⇒ 故障在填充路径；不出现 ⇒ 故障在 EBS 或更早 | §8 H1 |
| U2 烧录 FD 是否含 c6f2c64 / 填充是否到达 L1063 | `video base=` / `PRE EXIT` 全无 ⇒ 填充点未到达或固件过期（P1）；有 ⇒ 排除 P1 | H1 + 宿主机核对 FD |
| U3 GOP 缓冲/stride 是否为面板正在扫描的缓冲 | `video base=` 行与 ABL splash 地址/GOP 模式任一字段不符 ⇒ P2 定案；相符 ⇒ 排除 P2 | H1 日志比对 |
| U4 DSI 命令模式 + DSC 是否缺 DPU 提交 | 5 秒保持期内红出现 ⇒ 像素已在 DRAM、只缺传输（P5）；5 秒始终不出现 ⇒ 排除 P5 为唯一原因 | §8 H2 |
| U5 `FillScreen` 缓存维护是否写错 | 换 `FlushRange` 后红出现 ⇒ P3 是阻塞点；仍黑 ⇒ 排除 P3 | §8 H3 |
| U6 颜色/alpha | 常量改为 `0xFFFF0000` 后红出现 ⇒ P4 定案；仍黑 ⇒ 排除 P4 | §8 H4 |
| U7 帧缓冲内存是否在 EBS 时被回收/覆盖 | 描述符类型为 `EfiConventionalMemory` ⇒ P7 对 EBS 后黑成立；保留/`EfiMemoryMappedIO` ⇒ 排除 P7 | H1 的描述符打印 |
| U8 面板/DSI/时钟/电源是否在 EBS 时被关 | 5 秒保持期内斜看有微弱红像或背光亮而图像黑 ⇒ 面板活着，排除 P6；全暗无背光辉 ⇒ 关断在 EBS 之前 | H2 暗室检查 |
| U9 内核是否到过 `arm_init` | 绿 bootbar（0551）出现 ⇒ 活过 `arm_vm_init` + ramoops 初始化，排除桩 panic 在 `arm_init` 之前；红/黄/青三带（0542）定位死亡点 | §8 H5 |
| U10 桩 panic 是否静默发生 | warm-reset 后 `RamoopsDumpDxe` 读到 `fileset: original component called an unmapped kernel function from 0x…` ⇒ 桩 panic 实锤；`no signature` ⇒ 死在 `arm_init` 末之前 | §8 H6 |

**已结案（不列入未解）：** PONG 不是 27 线偏离（BCM2837 是 27 标准目标，R-8）；0546 ramoops 钩在 `console_write()` 而非 `_cnputc`，比 tb710fu 弱，但写入器已在 27 系列内；27 stage-0 无 `k60_usblog=2`，USB 不枚举是配置关闭，不是内核生死判据；`debug=0x14e` 含 `DB_NMI`，panic 会等调试器而不复位；桩 panic 不可能在 `arm_init` 之前（桩是 kext `__auth_got` / `__const` 指针槽里的值，kext 代码在 `PE_init_iokit()` 之前不执行），最早可达点是 `arm_init` 之后的 `code_signing_init()`，那时 console 子系统已起、而 USB 没开、ramoops 无同启动内读者且跨复位保留性存疑、panic 屏 mondrian 没有装。

## ⑦ 核验（本地，离线，不含构建与上机）

| 种类 | 命令 | 输出 | 结论 |
|---|---|---|---|
| 静态比对 | `grep` 抽查 fragment 引用的 file:line（本地克隆 `fix/ios27-black-screen-muse-20261122` @ `6893c8f`）：`board.toml:109-125/196-205/396-406`、`dts/mondrian.dts:29-32`、`patches/xnu-12377/0542/0543/0546/0551` 补丁头、`docs/engineering/ANDROID-HW-TRUTH.md` display 表；uefi-mondrian 引用用 browser.open 核对 `c6f2c64` diff（`DarwinBoot.c:583-586`、`:1063-1067`）与 `RamoopsDumpDxe.c:28-32` | 全部命中；uefi `c6f2c64` diff 与任务简报一致 | 通过 |
| 离线单元测试 | `python3 -c "import tomllib; tomllib.load(open('docs/research/eight-step/blackscreen-27.toml','rb'))"`；`python3 scripts/assemble-27-eight-step.py --check`；`python3 scripts/render-eight-step-table.py --check` | TOML 解析通过，1 个 hardware 项，7 步齐全；assemble `--check`：`ok eight-step-27: 8 item(s) from 6 fragment(s), all seven steps present`；render `--check` 通过（README 的 16 线表不受 27 fragment 影响） | 通过 |
| 制品检查 | `file` + `grep -c $'\r'` + `git status --porcelain` | 两个新增文件均为 LF、UTF-8、无 CRLF；`git status` 只含这两个新增文件 | 通过 |
| 完整构建 | **未运行** | 本 VM 没有仓库要求的构建环境（Darwin 工具链 shim、隔离输入/输出目录、已验证 FD）；`scripts/build-strict.sh` 需要宿主机环境 | **不知道**（未宣称通过） |

**`local_verified = false` 的原因：** 本分支本次无代码改动可核验；上述三项检查的是证据制品本身，不是代码。`EIGHT-STEPS-27.toml` **未手改** —— 它是 assembled 文件；注意：直接运行 `scripts/assemble-27-eight-step.py`（写模式）会从账本里**删掉 `[hardware.console]`**（它的 fragment 不存在，且它带有 Lead 专属的 `step.device`，assemble 的 `read()` 会拒绝含 `step.device` 的 fragment），所以账本合并必须由 Lead 用保留 device 步的方式做，本分支只交 fragment + 本文件，不代劳。

## ⑧ 上机（预测，Lead 执行；本分支不启动真机）

**前置铁则：** 只用 `fastboot boot`（RAM 临时引导），**不 flash 任何分区**；每次只改一个变量；保留回滚镜像；上机前挂好 USB CDC-ACM 抓取（VID 1209/PID 0001，DTR 必须置位），但 27 stage-0 无 `k60_usblog=2`，USB 不枚举是预期，不作为生死判据。

### H1 — 一次启动，拍照 + 计时（定位死亡点）

用当前镜像启动一次；在 5 秒 / 15 秒 / 60 秒 / 300 秒拍屏并记录：F2 三色带是否出现、绿 bootbar 是否出现、蓝 bootbar 是否出现、绿条是否出现、`video base=` / `PRE EXIT` / `EXIT CALL` 是否出现过、设备是否自行回 fastboot/菜单。

- `prediction.success`：`DARWINBOOT: video base=0x…` 行出现，且红/黄/青三带中至少红带出现 —— 证明填充点与内核入口都活着，故障在 `arm_init` 之后。
- `prediction.failure`：`video base=` / `PRE EXIT` / `EXIT CALL` 全无，且三色带全无 —— 故障在填充点之前（P1/P2/P5），与内核无关。
- 判定表：无红带 ⇒ 死在 DarwinBoot 交棒或入口之前；红/黄/青有、绿 bootbar 无 ⇒ 死在 `arm_vm_init` 或 `arm_init` 早段（桩已排除）；绿 bootbar 有、蓝 bootbar 无 ⇒ 活过 `arm_init`，死在 `kernel_bootstrap_thread`（`console_init` / `code_signing_init` / `PE_init_iokit` 区间，桩 panic 的候选区）；蓝 bootbar 有 ⇒ 活进 `bsd_init`，桩 panic 不在早期。

### H2 — P5 判别（一次固件构建、一次上电）

在 `FillScreen` 与 `ExitBootServices` 之间插 `gBS->Stall(5*1000*1000)`（uefi-mondrian `DarwinBoot.c:1063-1066` 之间），一次上电、相机对面板 + 暗室检查。

- `prediction.success`：保持期内红出现（至多约 60 个 TE 周期）—— 像素已在 DRAM、只缺传输（P5 定案）。
- `prediction.failure`：5 秒始终不出现 —— 排除 P5 为唯一原因；保持期内斜看有微弱红像或背光亮而图像黑 ⇒ 面板活着，排除 P6；全暗无背光辉 ⇒ 关断发生在 EBS 之前。

### H3 — P3 判别（一次固件构建）

把 `FillScreen` 内联 `dc` 循环换成已有的 `FlushRange(Video[0], Video[2]*Video[4])`，其它不动，一次上电。

- `prediction.success`：红出现 —— P3 是阻塞点。
- `prediction.failure`：仍黑 —— 排除 P3。

### H4 — P4 判别（一次固件构建）

只把填充常量改为 `0xFFFF0000`（同红，最高字节 `0xFF`），一次上电。

- `prediction.success`：红出现 —— P4 定案。
- `prediction.failure`：仍黑 —— 排除 P4。

### H5 — 色带定位（与 H1 同一次启动的不同读数维度，不要拆成另一次“加参数重飞”）

同一次 H1 启动，连续观察 300 秒（不碰电源）：自行回 fastboot/菜单 ⇒ 有复位源，记录回落时刻；300 秒仍挂住、屏面冻结 ⇒ 与“panic 等调试器”（`debug=0x14e` 含 `DB_NMI`）一致。

### H6 — warm-reset 读 ramoops（第二次启动，不长按电源）

H1 挂住后，**不长按电源**，用固件菜单 warm reset 进第二次启动，看 `RamoopsDumpDxe` 的输出。

- `prediction.success`：出现 `sig ok` + `pong-ramoops: console attached`，且出现 `fileset: original component called an unmapped kernel function from 0x…` —— **桩 panic 实锤**，返回地址即调用点，可对照 `kernel.json` 的 `stubbed` 表定位 bundle。
- `prediction.failure`：`RAMOOPS: no signature` —— 内核没走到 `pong_ramoops_console_init()`（死在 `arm_init` 末之前，与 H1 的色带对照）；出现 `sig ok` 但无 panic 文本 —— 活过 `arm_init`，死在 console 起来之后、无 panic 文本的挂死。
- 本实验同时判定 ramoops 跨复位保留性：warm reset 后仍读到文本，则“复位即失”只适用于断电/长按；读不到，则两种读法都失效，ramoops 不能作为事后取证。

### 离线前置（宿主机，不上机）

- O1：对本次构建产物跑 `python3 scripts/check-ios27-artifacts.py --flight-ready <board dir>`，打印 `kernel.json` 的 `missing` / `stubbed` 字段（注明读的是 `kernel.json` 还是 `kernel.map.json`，两者口径不同：94/203 vs 3/205）；再跑 `llvm-nm-18 --defined-only kernel/kernel.macho | grep _unixnu_fileset_unmapped` —— 这是验证桩函数是否真的编进本次内核的唯一直接证据。
- O2：在装配树里 `grep -n "console_init\|code_signing_init\|PE_init_iokit\|kernel_bootstrap_thread" <tree>/osfmk/kern/startup.c`，解决行号冲突（478/526/689 vs 582）。

## 未能验证的事（汇总，不要把它们当成已解决）

- 本次 27 构建产物（`kernel.macho` / `kernel.json` / `kernel.map.json`）未读到；`_unixnu_fileset_unmapped` 是否编进本次内核须跑 O1 的 `llvm-nm`。**不知道**
- `fileset-unmapped-call.patch` 是否在 27 实际应用的 series 里：克隆中找不到 `UniXNU/patches/xnu*/series` 文件；间接证据（artifacts 脚本的断言、sheng 的实测 panic）强，直接证据缺失。**不知道**
- `startup.c` 行号冲突（478/526/689 vs 582）、13 项桩身份（3 目标 / 13 项的 bundle 与槽）、看门狗超时、`serial=3` 在 mondrian 27 上的绑定目标。**不知道**
- 绿条在本次 iOS 27 黑屏中是否出现。**不知道**
- GOP 帧缓冲基址/stride/像素格式的静态值、`video_region` 0x85700000 的用途、`Display Reserved` 0xB8000000 是否属 mondrian、SimpleFbDxe/GOP 驱动实现位置、面板型号/DSI lane 数/时钟/DSC slice 参数、27 ADT 是否带 `display-scale=3`。**不知道**
- uke 的确切 27 `kernel_args` 与桌面证据（uke 页损坏）；vermeer 记录内部矛盾（`board.toml` 选 `ShengUfs` + `CONFIG_XNU_NATIVE_UFS=y`，而 unixnu 摘要称“未选定存储驱动”）；`IOS27-PRELINK-POLICY.json` 与 `PRELINK-RESIDUE.md` 的基线口径矛盾。**不知道**
- `patch-xnu-entry-probe.py` 能否给 XNU 12377（27）内核打补丁；`EIGHT-STEPS-27.toml` 的 `[hardware.console]` 缺 fragment（见 §7），账本合并须由 Lead 保留 device 步来做。**不知道**
