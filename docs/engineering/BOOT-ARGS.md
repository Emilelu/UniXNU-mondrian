# Boot 参数参考

> 2026-11-12 生成。目的：把「每个 boot-arg 接受什么值、默认是什么、错了会怎样」
> 集中到一处。P-144（`pong_metal=2` 不发布）与 P-145（`pong_adreno_start`
> 从未配过）都是参数语义不清造成的。

**硬限制：command line 607 字节**（含空格分隔）。判据在
`uefi-mondrian/Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h:8`
（`DARWIN_BOOT_LINE_LENGTH 608`）与 `DarwinBoot.c:678-684`：
`if ((Index >= sizeof (CommandLine) - 1) || (Request->BootArgs[Index] > 0x7f)) return EFI_BAD_BUFFER_SIZE;`
—— 即长度 ≥607 或含非 ASCII 时 DarwinBoot 在 ReadFile/ParseKernel 之前直接返回，
屏幕停在 REQUEST 阶段，**串口一个字节都不会出现**，设备自己回 fastboot。
2026-11-14 的 bt 线 `usblog-20261114-bts1b-run1`（610 字节）就是这样 0 字节的。
实测 board.toml 当前 29 项 575 字节（`unixnu build payload` 会按名覆盖后重新拼接）。
`payload.py:30-38 check_args()` 只拦 >1000，注释里的「1024-byte buffer」是过时的。

## 一览

| 参数 | 所属 | 接受值 | 未设时 | 陷阱 |
|---|---|---|---|---|
| `k60bt_delay` | 蓝牙 | 秒，上限 `K60_PROBE_MAX_DELAY_SECS` | `K60_PROBE_DELAY_SECS` | `0507-k60-bt-readonly-probe.patch:251`；只在 `k60.stage == 1` 时生效，让探针等 CDC 控制台开始收流后再碰 SE/GCC 寄存器，否则第一次访问就崩、日志留不下来 |
| `k60bt_step` | 蓝牙 | 1..`K60_PROBE_MAX_STEP` | `K60_PROBE_MAX_STEP` | `0507:252`；小于 1 或大于上限都被夹回范围，用来把探针停在指定步而不是跑完 |
| `k60bt_warm` | 蓝牙 | 真值 | 关闭 | `0510-k60-bt-firmware-addon.patch:221`；声明 PM8350 S10/S11/S12、PM8350C S1、PMR735A L7 已经上电，驱动不再自己投票 |
| `pong_adreno_start` | GPU 平台 | 必须 == 1 | 未设 = 不启动 | 缺它则整个 GPU 栈不运行，但日志里没有报错（P-145） |
| `pong_metal` | GPU / Metal | 必须 == 1 | 未设 = 不发布 | 设成 2 稳定但不发布，用 2 的日志判断 Metal 等于没测（P-144） |
| `pong_gpu_scanout` | GPU / 显示 | 必须 == 1 | 未设 = 软件路径 | 官方 next_action 要求先确认 accelerator 已发布再开它 |
| `pong_gpu_pool_mib` | GPU | 任意 uint | 代码默认 | — |
| `pong_metal_opens` | GPU / Metal | 任意 uint | 代码默认 | — |
| `pong_ufs_readwrite` | 存储 | 真值 | 只读 | 写盘会改动 Data 卷 |
| `native-ufs` | 存储 | 任意 | 代码默认 | board.toml 已设 native-ufs=1 |
| `native-ufs-probe` | 存储 | 任意 | 代码默认 | — |
| `native-ufs-wait` | 存储 | 0=Paced 1=Spin 2=Sleep | 1（Spin） | >2 会被忽略回落默认 |
| `sheng-data-reset` | 存储 | 1 或 2 | 不重置 | 会清 Data |
| `k60_touch_se` | 触摸 | 0..7 | 6 | 2026-11-12 显式设为 6；<6 不发布设备 |
| `k60_touch_rcg` | 触摸 | 0 或 1 | 0 | — |
| `k60touchhz` | 触摸 | ≤ 15000000 | 4000000 | 超范围整体拒绝 |
| `k60touchdelay` | 触摸 | ≤ 60（秒） | 8 | 超范围整体拒绝 |
| `touch_flip` | 触摸 | 0..3 | 0 | 超 3 整体拒绝 |
| `pong_touch` | 触摸 | 真值 | 1 | 0 则整条触摸线不跑 |
| `pong_init_path` | 启动链 | 路径 | 代码默认 | — |
| `k60_autoreset` | 自检 | 秒 | 不重启 | 无看门狗时用于自动回环，2026-11-11 的可启动镜像带 300；排障期建议给足，否则崩在用户态也会立刻复位，抓不到日志 |
| `applog` | 调试 | 真值 | 关闭 | 让用户态日志走内核 console；不开时 SpringBoard 的崩溃原因只留在内核侧，`cs_invalid_page` 能看见但进程日志没有 |
| `k60_selftest_reboot` | 自检 | 秒 | 不重启 | 手动测试时是浪费的 23 字节，可让位给 GPU 开关 |
| `k60_console_export` | 调试 | 真值 | 关闭 | `0243-k60-console-export.patch` 把内核 console 导出到 USB EP0 | 与 `k60_usblog` 配合 |
| `k60_usblog` | 调试 | 0/1/2 | 代码默认 | `0300-k60-usblog-ep0.patch` USB 日志级别 | 刷机时的主要日志通道 |
| `k60_usbvend` | 调试 / USB | 0/1/2 | 0（= 0409 原样） | `0410-k60-usb-vendor-loopback.patch`：0 = 67 字节两接口 CDC-ACM、无回环；1 = 98 字节复合描述符（IAD + IF2 vendor 0xff/0xfe，EP 0x03 OUT / 0x83 IN）+ EP6→EP7 回环；2 = 控制台描述符不变、回环跑 CDC 数据对 EP2→EP3（普通 COM 口可验） | mode 1 的 IF2 主机侧没有驱动，要用 libusb 直接开；mode 2 必须同时开 `k60_usblog`（控制台让位给回环） |
| `pong_modem` | uint32 | 0 | `patches/xnu/0621-k60-modem-pas.patch:325` | `bsd/dev/pong_modem_pas.c` | 0 = quiet; 1 = modem image stage; 2 = image + QRTR verdict `K60MODEM qrtr: verdict ok` (cellular L3). |
| `k60_wallpaper_reset` | uint32 | 0 | `userland/ui_compat.c:677` | `select_initial_wallpaper()` | 1 = SpringBoard restores the stock 7410 wallpaper through the native setter on the next boot (springboard F1). |
| `k60_backlight` | uint32 | 1 | `drivers/PongAdreno/K60Backlight.cpp:399` | `k60_backlight_start()` | 0 = never start the backlight service (panel keeps the DBV bring-up left, 0xff). |
| `k60_backlight_control` | uint32 | **1** | `drivers/PongAdreno/K60Backlight.cpp:292` | `K60Backlight::publishFirst()` | 1 = impersonate AppleARMBacklight and publish `backlight-control`; 0 = publish the level only, never claim the control property (int-236 escape hatch). |
| `k60_backlight_invert` | uint32 | 0 | `drivers/PongAdreno/K60Backlight.cpp:346` | `K60Backlight::start()` | 1 = invert the level-to-DBV mapping when the panel is wired the other way round. |
| `pong_thermal_bias` | int32 (mC) | 0 | `drivers/PongThermal/pong_thermal.c:277` | `pong_thermal_start()` | Synthetic offset added to every sensor reading so a cold device can be pushed up the zone ladder: 50000 = level 1, 75000 = level 2, 85000 = level 3. |
| `gprobe` | uint32 | 0 | `drivers/PongAdreno/PongDsiPanel.cpp:330` | `pong_panel_bring_up()` / `pong_panel_sample()` | 1 = arm the bounded 120 s panel-cadence observation window (GCC_DISP_AHB gate, DISPCC, MDSS) and let `K60 CADENCE:` lines print; 0 = the sample hook stays silent unless the one-shot post-bring-up check is still pending. |
| `k60_fontscale` | 显示 | 整数 | 代码默认 | `0214-k60-console-font-scale.patch` 控制台字号倍率 | — |
| `k60_textonly` | 显示 | 真值 | 代码默认 | 只跑文本控制台，不初始化图形帧 | 用于隔离显示问题 |
| `fb_threads` | 显示 | 整数 | 代码默认 | `zzzz…-pong-hackios-ui-foundation.patch` framebuffer 线程数 | — |
| `k60_init_blob` | 启动链 | 真值 | 关闭 | `0391-k60-embedded-init.patch` 启用内嵌 init blob | 关掉则无 `/private/var/pong/init` |
| `k60_launchd_cache` | 启动链 | 真值 | 关闭 | `0391-k60-embedded-init.patch` 部署 launchd 缓存（22 job）| 依赖 `k60_init_blob` |
| `launchd_unsecure_cache` | 启动链 | 真值 | 代码默认 | 允许未签名 launchd 缓存 | 与 `k60_launchd_cache` 同用 |
| `k60_tolerate_cache_loader` | 启动链 | 真值 | 关闭 | `0314-k60-kern-exit-tolerate-and-clean.patch` 容忍缓存加载器失败 | — |
| `k60_entitlement_allow` | 安全 | 真值 | 关闭 | `0330-k60-entitlement-allow.patch` 放宽 entitlement 检查 | — |
| `k60_skip_iosurface` | GPU/IOKit | 真值 | 关闭 | `0332-k60-skip-prelinked-load.patch` 跳过预链接的 IOSurface 加载 | P-13x：避免第二个 IOSurfaceRoot |
| `k60_skip_firmware_mount` | 存储 | 真值 | 关闭 | `0320-k60-skip-firmware-mount.patch` 跳过 firmware 分区挂载 | 加快启动 |
| `k60_panic_reset` | 诊断 | 真值 | 关闭 | `0334-k60-panic-reset-fastboot.patch` panic 后自动重启 | 调试循环用 |
| `pong_allow_unauthenticated_root` | 安全 | 真值 | 关闭 | `zzzz…-pong-development-root-policy.patch` | — |
| `pong_software_keybag` | 安全 | 真值 | 关闭 | `0211-k60-display-startup.patch` 软件 keybag | — |
| `pong_data_mount` | 存储 | 真值 | 关闭 | `offline-owner-systemos-mount.patch` 挂 Data 卷 | 与 `pong_data_rw` 同用 |
| `pong_data_rw` | 存储 | 真值 | 只读 | `offline-owner-systemos-mount.patch` Data 卷可写 | 写盘会改动 Data |
| `xpcproxy_idversion` | 启动链 | 真值 | 关闭 | `zzzz…-pong-hackios-launchd-exec.patch` xpcproxy 版本兼容 | — |
| `pong_wifi` | WiFi | 必须 == 1 | 未设 = 不启动 | 缺它则 `pong_wifi_start_optional()` 只做 `pong_rpmh_init()` 就返回，日志里没有报错 |
| `k60_wifi_rsc` | WiFi | 0..2 | 0 = 不动 RSC | 1 = 只读探针 TCS4 后拒绝投票；2 = 允许 RPMh 投票。默认 fail-safe，因为对未上电 RSC 写入会挂死整机（K60-TOUCH-PARAMS.md:120,174） |
| `k60_wifi_stage` | WiFi | 0..10 | 0 = 跑全部 | 只跑到第 N 级就停，用于把早期挂死收敛到一个 MMIO 块；超范围值等于全跑 |
| `pong_wifi_dma_mib` | WiFi | 64..128 | 64 | 只接受 64/128，其它值 `return fail("WiFi DMA budget must be 64 or 128 MiB")` 后整条线停 |
| `pong_wifi_diag` | WiFi | 真值 | 关闭 | 打开 progressDiagnostic，把 stage 进度写进 `pong_wifi_progress[]` |
| `pong_wifi_test` | WiFi | 真值 | 关闭 | 关联测试：拿到 MAC 后主动连接 fixture 里的 AP |
| `pong_wifi_alt` | WiFi | 真值 | 关闭 | 只有 `pong_wifi_test=1` 时才用；选「备用网络」那一组 fixture，不是 SSID 文本 |
| `pong_wifi_band` | WiFi | 0..5 | 0 = 不限 | 只接受 0/2/5；其它值打 `WiFi association test SKIP: band must be 0, 2 or 5` 并关掉整条测试 |
| `pong_wifi_cycle` | WiFi | 真值 | 关闭 | 与 `pong_wifi_test=1` **同时**满足才开 gCycleTest（`PongWifiNet.cpp:892-893` 是 `&&` 串联） |

## 逐个说明

### `pong_adreno_start`

- **所属**：GPU 平台
- **接受值**：必须 == 1
- **未设时**：未设 = 不启动
- **作用**：PongAdrenoPlatform.cpp:479 启动 Adreno 平台线程；否则直接 return
- **陷阱**：缺它则整个 GPU 栈不运行，但日志里没有报错（P-145）
- **源码**：`drivers/PongAdreno/PongAdrenoPlatform.cpp:479`

### `pong_metal`

- **所属**：GPU / Metal
- **接受值**：必须 == 1
- **未设时**：未设 = 不发布
- **作用**：PongAdrenoNativeGlue.cpp:30 设 PongMetal20G81Enabled；:44 发布 IOAcceleratorES provider
- **陷阱**：设成 2 稳定但不发布，用 2 的日志判断 Metal 等于没测（P-144）
- **源码**：`drivers/PongAdreno/PongAdrenoClient.cpp:202`
- **源码**：`drivers/PongAdreno/PongAdrenoNativeGlue.cpp:30`
- **源码**：`drivers/PongAdreno/PongAdrenoNativeGlue.cpp:62`

### `pong_gpu_scanout`

- **所属**：GPU / 显示
- **接受值**：必须 == 1
- **未设时**：未设 = 软件路径
- **作用**：PongAdrenoScanout.cpp:44 才能走 GPU scanout
- **陷阱**：官方 next_action 要求先确认 accelerator 已发布再开它
- **源码**：`drivers/PongAdreno/PongAdrenoScanout.cpp:44`

### `pong_gpu_pool_mib`

- **所属**：GPU
- **接受值**：任意 uint
- **未设时**：代码默认
- **作用**：PongAdrenoCp.cpp:312 GPU 池大小（MiB）
- **源码**：`drivers/PongAdreno/PongAdrenoCp.cpp:312`

### `pong_metal_opens`

- **所属**：GPU / Metal
- **接受值**：任意 uint
- **未设时**：代码默认
- **作用**：NativeAdrenoAccelerator.cpp:31 并发 open 上限
- **源码**：`drivers/PongAdreno/submit/NativeAdrenoAccelerator.cpp:31`

### `pong_ufs_readwrite`

- **所属**：存储
- **接受值**：真值
- **未设时**：只读
- **作用**：PongUfsTransport.cpp:389 允许 UFS 写
- **陷阱**：写盘会改动 Data 卷
- **源码**：`drivers/NativeUfs/PongUfsTransport.cpp:389`

### `native-ufs`

- **所属**：存储
- **接受值**：任意
- **未设时**：代码默认
- **作用**：NativeUfs.cpp:147 启用 UFS 驱动
- **陷阱**：board.toml 已设 native-ufs=1
- **源码**：`drivers/NativeUfs/NativeUfs.cpp:147`

### `native-ufs-probe`

- **所属**：存储
- **接受值**：任意
- **未设时**：代码默认
- **作用**：NativeUfs.cpp:144 探测模式
- **源码**：`drivers/NativeUfs/NativeUfs.cpp:144`

### `native-ufs-wait`

- **所属**：存储
- **接受值**：0=Paced 1=Spin 2=Sleep
- **未设时**：1（Spin）
- **作用**：PongUfsTransport.cpp:174 完成等待策略（2026-11-12 从官方 CompletionWait.h 移植）
- **陷阱**：>2 会被忽略回落默认
- **源码**：`drivers/NativeUfs/PongUfsTransport.cpp:174`

### `sheng-data-reset`

- **所属**：存储
- **接受值**：1 或 2
- **未设时**：不重置
- **作用**：NativeRamBlock.cpp:79 Data 卷重置
- **陷阱**：会清 Data
- **源码**：`drivers/NativeRamBlock/NativeRamBlock.cpp:79`

### `k60_touch_se`

- **所属**：触摸
- **接受值**：0..7
- **未设时**：6
- **作用**：触摸阶段：1 只映射 2 GPIO/AVDD 5 识别 6 发布 /dev/pong-touch 7 GPIO 识别
- **陷阱**：2026-11-12 显式设为 6；<6 不发布设备

### `k60_touch_rcg`

- **所属**：触摸
- **接受值**：0 或 1
- **未设时**：0
- **作用**：强制 RCG 时钟路径

### `k60touchhz`

- **所属**：触摸
- **接受值**：≤ 15000000
- **未设时**：4000000
- **作用**：SPI 频率
- **陷阱**：超范围整体拒绝

### `k60touchdelay`

- **所属**：触摸
- **接受值**：≤ 60（秒）
- **未设时**：8
- **作用**：启动后延迟多久开始摸触摸
- **陷阱**：超范围整体拒绝

### `touch_flip`

- **所属**：触摸
- **接受值**：0..3
- **未设时**：0
- **作用**：坐标翻转：bit0 翻 X，bit1 翻 Y
- **陷阱**：超 3 整体拒绝

### `pong_touch`

- **所属**：触摸
- **接受值**：真值
- **未设时**：1
- **作用**：触摸总开关
- **陷阱**：0 则整条触摸线不跑

### `pong_init_path`

- **所属**：启动链
- **接受值**：路径
- **未设时**：代码默认
- **作用**：init 所在路径

### `k60_selftest_reboot`

- **所属**：自检
- **接受值**：秒
- **未设时**：不重启
- **作用**：无人值守自检后自动重启
- **陷阱**：手动测试时是浪费的 23 字节，可让位给 GPU 开关

### `pong_wifi`

- **所属**：WiFi
- **接受值**：必须 == 1
- **未设时**：不启动（`pong_wifi_start_optional()` 只做 `pong_rpmh_init()` 就返回）
- **作用**：通过后 `kernel_thread_start(worker)` 起 QCA6490 bring-up 线程
- **陷阱**：worker 比 `k60_usblog_start()`（`bsd_init.c:1341`）早约 180 行运行；在控制台起来之前碰未上时钟的外设会挂死整机、串口 0 字节（P-49）。驱动侧已有 `k60_usblog_console_up()` 门，但仍应配合 `k60_wifi_stage` 逐级放行
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:716`

### `k60_wifi_rsc`

- **所属**：WiFi
- **接受值**：0..2
- **未设时**：0（RSC 完全不动）
- **作用**：1 = 只读探针 `0x17a20000` 的 TCS4 并打印 `RSC probe id/caps/tcs4Idle/tcs4Status`，然后拒绝所有投票；2 = 探针通过后允许 `rawVote()` 走 RPMh
- **陷阱**：探针本身就是 RSC MMIO 读；RSC 电源域未证明时会挂死整机而不是返回错误。默认 0 是有意的 fail-safe
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:744`

### `k60_wifi_stage`

- **所属**：WiFi
- **接受值**：0..10
- **未设时**：0（跑全部十级）
- **作用**：`stageOpen()` 逐级放行：1 TLMM pinmux、2 SPMI/PMIC page、3 cmd-db、4 RPMh/RSC 投票、5 GCC GDSC/refgen、6 PARF/DBI/PHY/ATU、7 82 项 PHY 表、8 PERST/LTSSM、9 SMMU SID 1c01、10 MSI attach
- **陷阱**：每级在碰寄存器之前就打 `PongWifi: stage N (…)`，被挡的级打 `held back by k60_wifi_stage=N`；最后一条 stage 行就是死掉的那一块的入口
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:69`

### `pong_wifi_dma_mib`

- **所属**：WiFi
- **接受值**：64..128
- **未设时**：64
- **作用**：选择 WiFi DMA arena 大小
- **陷阱**：只接受 64/128，其它值直接 `fail("WiFi DMA budget must be 64 or 128 MiB")` 后整条线停
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:408`

### `pong_wifi_diag`

- **所属**：WiFi
- **接受值**：真值
- **未设时**：关闭
- **作用**：打开 progressDiagnostic，把 stage 进度写进 `pong_wifi_progress[]`
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:647`、`drivers/PongWifi/PongWifiNet.cpp:890`

### `pong_wifi_test`

- **所属**：WiFi
- **接受值**：真值
- **未设时**：关闭
- **作用**：拿到 station MAC 后主动关联测试 AP
- **陷阱**：没有真实 board data（BDF）时连不上，日志停在 `Pong: actual QMI board firmware` 之后
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:572`、`drivers/PongWifi/PongWifiNet.cpp:892`

### `pong_wifi_alt`

- **所属**：WiFi
- **接受值**：真值
- **未设时**：关闭
- **作用**：关联测试里选用「备用网络」那一组 fixture（`alternate` 标志），不是 SSID 文本
- **陷阱**：SSID/PSK 来自构建期注入的私有 fixture（`PongWifiTestInputs.h`，0600）；缺 fixture 时打 `WiFi association test SKIP: no private network fixture` 并关掉整条测试
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:573`

### `pong_wifi_band`

- **所属**：WiFi
- **接受值**：0 / 2 / 5
- **未设时**：0（不限）
- **作用**：限定关联测试频段
- **陷阱**：其它值打 `WiFi association test SKIP: band must be 0, 2 or 5` 并关掉整条测试
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:574`

### `pong_wifi_cycle`

- **所属**：WiFi
- **接受值**：真值（必须 == 1）
- **未设时**：关闭
- **作用**：在 `pong_wifi_test=1` **同时**成立时才把 `gCycleTest` 置真，跑断连/重连生命周期测试
- **陷阱**：两个参数是 `&&` 关系，只给 `pong_wifi_cycle=1` 不会有任何动作
- **源码**：`drivers/PongWifi/PongWifiNet.cpp:892`

## 三个 GPU 开关的相互关系

```
pong_adreno_start=1    -> 平台线程启动 -> CP backend -> native_adreno_publish
                          -> PongAdrenoConfigureService
pong_metal=1           -> 在上面全部成功之后，才发布 IOAcceleratorES provider
pong_gpu_scanout=1     -> 只有在 accelerator 已发布之后才应该打开
```

三者的依赖是串行的：前一个没成，后一个开了也没有意义。

## 字节预算

```
上限 607（DarwinBoot.c:681）
基线：29 项 575 B（2026-11-16 实测，baseline-20261116a 的 payload args），余 32

pong_wifi=1                                   +12 -> 587   （c4 实测）
pong_wifi=1 k60_wifi_rsc=1                    +15 -> 602   （只读探针；c5 实测）
pong_wifi=1 k60_wifi_rsc=2                    +15 -> 602   （允许投票；与 =1 同长）
pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=10  +18 -> 620 超限
```

`k60_wifi_rsc` 的取值语义与宽度：`1` = 只读探针（读 drv-2 的 TCS 寄存器，
不写任何票），`2` = 允许投票（会写 TCS）。两者名字同宽，所以在 607 B 上限下
`rsc=1` 与 `rsc=2` 都是 31 项 602 B，换值不改预算——c5 用 `1`、c6 用 `2`，
两张图的参数长度逐字节相同。

让位项（实测）：`epoch=1793709100` 改 `epoch=1` 省 9 字节，`debug=0x140` 改 `debug=1` 省 4 字节，
两项合起来正好把 620 压到 607 以下（实测 589）。`k60_fontscale=0` **不是**让位项：
`osfmk/console/video_console.c:2844` 要求 scale 在 2..4，0 会被忽略且长度不变。
`k60_selftest_reboot=300`（23 字节）在未配置时本来就不在 board.toml 里。

## 当前状态（2026-11-12）

已启用：

```
pong_adreno_start=1   平台线程
pong_metal=1          accelerator 发布
k60_touch_se=6        触摸发布
```

未启用（按依赖顺序应当后开）：

```
pong_gpu_scanout=1    需 19 字节，当前余 17 —— 官方要求先确认 accelerator 已发布
```

为给 `pong_metal=1` 腾空间，已移除 `k60_selftest_reboot=300`（23 字节）。
它是无人值守自检后的自动重启看门狗：手动上机测试时不需要，
而且在观察过程中会把设备重启掉。

---

### `k60_battery`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 1（启用） |
| 来源 | `drivers/PongPower/K60Battery.cpp:420`（`PE_parse_boot_argn("k60_battery", &enabled, sizeof(enabled))`）|
| 作用 | 0 = 完全不启动电池服务；非 0 = 允许启动 |

**注意**：非 0 只表示"允许尝试"。`k60_physical_battery_start()` 随后要求
`/chosen` 里有 `k60-adsp-glink-handoff` 属性，且该记录里四个标志全真
（Authenticated / ResourcesHeld / GlinkExclusive / FreshHostFifos）。
没有这个 PAS1 租约时它会打印
`K60Battery: blocked rc=N: no authenticated exclusive PAS1/SMEM/GLINK platform handoff`
然后返回，**不会发布任何假电量**。

所以 `k60_battery=0` 是彻底关掉，`k60_battery=1`（默认）是"有租约才启动"。
没有第三个状态 —— 不存在"强制启动"的开关。

### `pong_rail_probe`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不探测，任何启动都不映射 RSC） |
| 取值 | 0 / 1 |
| 来源 | `patches/xnu/0614-k60-adsp-call-site.patch`（`PE_parse_boot_argn("pong_rail_probe", &pong_rail_probe, sizeof(pong_rail_probe))`），实现在 `drivers/PongPower/K60PmicRail.c` |
| 作用 | 1 = 在 Data 卷挂载成功后**只读**一次 RPMh `cmd-db` 与 DRV-2 的 `0x17a20000`，打印 `K60RAIL` 三行（cmd-db magic、ldoc2 地址与电平、RSC 布局） |

**为什么默认关闭**：`docs/ops/HARD-RULES.md` 的 HR-01 规定默认不得访问 RSC —— 2026-11-09 有两次
早期启动阶段首读即整机死（零控制台）。2026-11-14 的 `rail-20261114h` 证明**Data 挂载之后只读**不会死
（`E:\k60-work\evidence\usblog-20261114-railh\console.log:477-479`，3,366 行、129 行 SpringBoard、
`panicMarker=null`），但一次存活不足以改成默认。所以：只读、单次、必须显式开启；**写 TCS 与
`CONTROL_TRIGGER` 仍然全面禁止**，供电投票等 ABL 方案。

### `pong_handoff_publish`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不发布） |
| 取值 | 0 / 1 |
| 来源 | `patches/xnu/0619-k60-adsp-glink-handoff.patch`（`iokit/bsddev/IOKitBSDInit.cpp`，`PE_parse_boot_argn("pong_handoff_publish", …) == 1u`）|
| 作用 | 1 = 在 IOKitBSDInit 早期跑 `k60_adsp_handoff_publish()`：claim owner=1 → 解析电池板配置 → 范围重叠检查 → `/chosen` 查找 → `k60_adsp_owner_acquire`（阶段 1–4：PAS1 bring-up / discovery / build / self-parse）→ 发布 104 字节认证 lease。成功打 `K60Handoff: published authenticated PAS1 epoch=%u bytes=104 flags=15`，失败打 `K60Handoff: PAS1 bring-up/retained ownership failed rc=%d`。 |

**当前状态（2026-11-15）**：owner=1 先 claim 后，`kern_exec.c` 的 legacy `k60_adsp_startup_claim(2u)` 会失败并打
`K60PAS legacy startup excluded by earlier ADSP owner/attempt`——该行在此参数下是**预期输出**，证明发布器先跑。
载体是内核内嵌 `k60_adsp_blob`（26 记录容器，P-197 workaround），与 `pong_adsp` 的 md0 死路无关。

### `pong_adsp`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不探测） |
| 取值 | 0 / 1 |
| 来源 | `drivers/PongPower/K60AdspBoot.c`（`PE_parse_boot_argn("pong_adsp", &enabled, sizeof(enabled))`）|
| 作用 | 1 = 启动 ADSP PAS1 探针：读取 24 段镜像、算 SMC 参数、打印每一段的 `rc` |

**当前状态（2026-11-13）**：探针能从 `memdev` 拿到 md0 的几何，但 `vmd0` 记的是固件
虚拟地址，XNU 读不到（`esr 0x96000010`，见 `docs/research/audio/ADSP-MD0.md`）。
所以 `pong_adsp=1` 目前只用于诊断，不能作为可用的音频/电池前提。

### `sheng-gpu-addon`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不做任何 union 挂载） |
| 取值 | 0 / 1 |
| 来源 | `patches/xnu/zzy-native-gpu-addon-mount.patch`（`PE_parse_boot_argn("sheng-gpu-addon", &enabled, sizeof(enabled))`，`native_gpu_addon_prepare()`），实现在 `bsd/kern/kern_exec.c` |
| 作用 | 1 = 在 Data 卷挂载成功、launchd 启动**之前**，把 `/private/var/ngpu/addons` 只读 union 到 `/System/Library/Extensions`、把 `/private/var/ngpu/daemons` union 到 `/System/Library/LaunchDaemons` |

**为什么需要它**：`0610-k60-metal-plugin-deploy.patch` 把 51,278,451 字节的 Metal 插件
（`PongAdrenoMetal.bundle` 含 `PongMetalBridge.dylib` 33,146,048 B 与
`libvulkan_freedreno.dylib` 18,036,688 B）从内核写到 `/private/var/ngpu/addons`，但 Metal 的
原始发现路径只查 `/System/Library/Extensions/<name>.bundle`。没有这个 union，插件落在 Data 卷上
也永远不被加载，用户态继续打印 `software-only platform`（`userland/ui_compat.c:510`）。

**默认关闭的理由**：它改写的是 sealed 系统目录的可见性，任何异常都会影响 launchd 与所有进程；
先按 opt-in 上机验证（判据：`native_gpu_addon_prepare` 打印挂载成功 + 不再出现
`software-only platform` + 出现 `[direct scanout]`），确认无副作用后再评估是否改成默认。
缺目录或挂载被拒只打印失败，不会 panic。

### `gprobe`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0 |
| 取值 | 0 / 1 |
| 来源 | `drivers/PongAdreno/PongDsiPanel.cpp:330`（`PE_parse_boot_argn("gprobe", &probe, sizeof(probe)) && probe == 1`），由 `pong_panel_bring_up()` 末尾设置；消费点是 `pong_panel_sample()`（`PongAdrenoScanout.cpp:171` 每帧调用） |
| 作用 | 1 = 开启有界（120 秒）面板节拍观测：读 `GCC_DISP_AHB` 时钟门、`DISPCC` 与 `MDSS` 的计数器，按 5 秒间隔打印 `K60 CADENCE:` 行；0 = 只有 bring-up 之后那一次自动校验仍会跑，其余采样静默 |

**为什么要它**：显示线要回答「面板真的按 120 Hz 在刷新吗、有没有帧被丢掉」，
只能读 `DISPCC`/`MDSS` 的节拍计数器；这些寄存器在 `IO_MAP_SIZE` 8 MiB 的窗口之外
（P-63），必须用 `ml_io_map` 单独映射，所以只能按需开启，不能常驻。

**陷阱**：窗口是**有界**的（`elapsed >= 120 * NSEC_PER_SEC` 后自动关闭），不要指望整场
启动都有 `K60 CADENCE:` 行；`GCC_DISP_AHB off` 一行表示时钟门还没开，此时不会去读
`DISPCC`/`MDSS`（避免对未上电模块做 MMIO，P-161/HR-01 同一个形状）。缺映射时打印
`no GCC mapping` / `no DISPCC mapping` 后直接返回，不会 panic。
