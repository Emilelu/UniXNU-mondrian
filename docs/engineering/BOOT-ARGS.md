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
实测 board.toml 当前 30 项 596 字节（2026-11-19 起含 `pong_metal=1` 与 `sheng-gpu-addon=1`，此前为 29 项 575 字节；`unixnu build payload` 会按名覆盖后重新拼接）。
`payload.py:30-38 check_args()` 只拦 >1000，注释里的「1024-byte buffer」是过时的。

预算实例（2026-11-19，合并 `feat/120hz-panel` 时核算）：`board.toml` 当前 29 项 575 字节，`p120=1` 追加 7 字节为 582，`vsync=120` 追加 10 字节为 585；`p120=1` 叠加 `k60_backlight_control=1` 为 606，仍在 607 上限内；`vsync=120` 与 `k60_backlight_control=1` 同用会到 609，装不进同一张镜像——所以面板切档与背光控制改为**默认开启**，只保留 `p120=0` / `vsync=120` / `k60_backlight_control=0` 作为退出开关。

探针镜像另有实测：2026-11-19 的 mode-1 探针 w11 为 30 项 601 字节（596 − 9 去掉 `applog=1` + 14 加入 `k60_cpufreq=1`），余 6 字节；2026-11-18 的旧探针记的是 603 字节，属当时那份参数表。发布镜像仍以 `board.toml` 的完整参数为准。

## 一览

| 参数 | 所属 | 接受值 | 未设时 | 陷阱 |
|---|---|---|---|---|
| `k60bt_delay` | 蓝牙 | 秒，上限 `K60_PROBE_MAX_DELAY_SECS` | `K60_PROBE_DELAY_SECS` | `0507-k60-bt-readonly-probe.patch:251`；只在 `k60.stage == 1` 时生效，让探针等 CDC 控制台开始收流后再碰 SE/GCC 寄存器，否则第一次访问就崩、日志留不下来 |
| `k60bt_step` | 蓝牙 | 1..`K60_PROBE_MAX_STEP` | `K60_PROBE_MAX_STEP` | `0507:252`；小于 1 或大于上限都被夹回范围，用来把探针停在指定步而不是跑完 |
| `k60bt_warm` | 蓝牙 | 真值 | 关闭 | `0510-k60-bt-firmware-addon.patch:221`；声明 PM8350 S10/S11/S12、PM8350C S1、PMR735A L7 已经上电，驱动不再自己投票 |
| `pong_adreno_start` | GPU 平台 | 必须 == 1 | 未设 = 不启动 | 缺它则整个 GPU 栈不运行，但日志里没有报错（P-145） |
| `pong_metal` | GPU / Metal | 必须 == 1 | 未设 = 不发布 | 设成 2 稳定但不发布，用 2 的日志判断 Metal 等于没测（P-144） |
| `pong_gpu_scanout` | GPU / 显示 | 必须 == 1 | 未设 = 软件路径 | 官方 next_action 要求先确认 accelerator 已发布再开它 |
| `pong_gpu_coherent` | GPU / 提交 | 0 / 1 / 2（默认 2） | 2 = 跑探针 | 唯一有对方量化证据的一项：zizhan g40/g41 强制开后扫出 24–35 ms → 5–6 ms。用 1 绕过证明等于拿帧的正确性换速度 |
| `pong_surface_pitch` | GPU / 扫出 | `1` 开（默认 `0` 关） | 关 = 照客户端请求的 `IOSurfaceBytesPerRow` 分配（当前行为） | 开时一律按 `alignUp(width*bpe, 64)` 回报，客户端经 `IOSurfaceGetBytesPerRow` 得到同一个数。行距差（5888 vs 5760）是扫描 blit 只能走线性纹理的唯一原因，实测那一段 `encode` 46 ms 而同样 18.4 MB 的普通拷贝 1.9 ms；若调用方不尊重回报值，画面会斜切，这是它保留开关的原因 |
| `pong_gpu_blit_probe` | GPU / 扫出 | `1` 开（默认关） | 开 = 首帧后跑一次对照 | 已答完并默认**关**：对照实测两个目标都是 9–10 GB/s，固件帧缓冲不是慢的那个；带它的那次飞行以 CP/SMMU fault 收场（P-244），且它按源行距写目标会让那一帧斜切 |
| `gbench` | GPU / 提交 | `0`..`120`（默认不跑） | 未设：`gperf` 出现时按 24 次 | 把同一次拷贝在同一个 offer 里重复 N 次并逐次打印 `scanout bench n=…`，让 blit 的测量不依赖「屏幕上恰好有没有动画」。三次飞行都因为静止屏只有 4 帧、拿不到稳态样本，这个开关就是为此存在 |
| `gperf` | GPU / 提交 | `1`..`13`（默认不投） | 未设 = 只投一次启动票、此后永不复访 | GX 起来之后按 `gperf=N` 重投同一条 `GX_BW_PERF_VOTE`（HFI id 30）。功率与发热随档位变化，所以默认不动；`0` 与 `>13` 被当成调用方 bug 拒发，`14` 是表长不是档位 |
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
| `pong_gpu_dcvs` | 电源 / GPU | 0 / 1 / 2 | 0（关闭） | `drivers/PongAdreno/PongAdrenoDcvs.cpp`；1=16 ms 读 GMU XO 忙碌计数器并经 HFI id 30 投票，连续 8 次被拒停线程；2=再在启动时做一次升档投票并立即还原；image o 02:14 已上机（空闲、24 窗口、无投票）；image q 02:36 用 2 验证 HFI id 30 投票被接受（升档+还原各一次、错误码 0） |
| `pong_gpu_max_level` | 电源 / GPU | 1..13 | 13 | `drivers/PongAdreno/PongAdrenoDcvs.cpp`；DCVS 可投的最高档，越界回落 13，仅在 `pong_gpu_dcvs=1` 时读取 |
| `pong_gpu_dcvs_min` | 电源 / GPU | 1..13 | 1 | 同上；空闲时允许降到的最低档，小于 1 夹到 1、大于最高档夹到最高档 |
| `pong_gpu_dcvs_boost_ms` | 电源 / GPU | ≥ 0（毫秒） | 50 | 同上；GMU 忙碌计数从零转非零后唤醒档（两倍频率、至少 578 MHz）的保持时间，0 = 不保持 |
| `k60_cpufreq` | 电源 / EPSS | 1/2/3/5/6/7/8 | 0（关闭） | `drivers/PongPower/K60CpuFreqProbe.cpp`；1=只读三域+L3，2=d0 最高非 turbo，3=三域+L3，5=16 ms `processor_info` 只读采样，6=d0 降到最低档（已上机），7=首个降档窗口起 10 s 按 governor 只降档写回并恢复（100 s 上限，已上机），8=同一窗口内双向写回并恢复（已上机）；2/3 为瞬态验证写（写前守卫、写后回读、立即恢复），4 被拒绝，9 已禁用（两次 0 字节卡死）；2/3 未上机，5 已于 2026-11-18 23:19 以 image l 只读上机（274 条样本），6 已于 2026-11-19 02:47 以 image n 上机，7 已于 03:26 以 image r 上机、8 已于 03:58 以 image s 上机（d0 双向生效，d1 写回不被 EPSS 接受）；探针镜像需去掉 `applog=1` 才不超 607 字节 |
| `platform-sleep` | 电源 / 睡眠 | 0 / 1 | 0（关闭） | `drivers/ArmCpu/ArmCpu.cpp`；仅当值为 1、XNU 侧 `arm64_platform_sleep_hook` 存在且 GIC 映射成功时安装 hook，`quiesceCPU` 才进入 `ml_arm_sleep`；默认 0 时整条路径不安装，image z 用它做默认启动回归 |
| `platform-sleep-wake-after` | 电源 / 睡眠 | 秒，0 = 不设期限 | 0 | 同上；启动核等待的绝对 CNTV 期限，与 10 s tick 取较小值。没有唤醒源也没有该期限时 hook 直接返回（`unarmed`），所以计时唤醒测试必须同时给 `platform-sleep=1` 和本参数 |
| `k60_slp` | 电源 / 睡眠 | 秒，0 = 不触发 | 0 | `drivers/PongPower/K60PlatformSleep.cpp`；仅 bring-up 诊断用，非 0 时在板级 hook 注册后启动内核线程，等待指定秒数后调用 `IOPMrootDomain::sleepSystem()`，用于无人按电源键时验证 `platform-sleep=1`；w9/w10 已用它进入 `IOCPUSleepKernel`，但完整恢复挂死，发布镜像不应带它 |
| `applog` | 调试 | 真值 | 关闭 | 让用户态日志走内核 console；不开时 SpringBoard 的崩溃原因只留在内核侧，`cs_invalid_page` 能看见但进程日志没有 |
| `k60_selftest_reboot` | 自检 | 秒 | 不重启 | 手动测试时是浪费的 23 字节，可让位给 GPU 开关 |
| `k60_console_export` | 调试 | 真值 | 关闭 | `0243-k60-console-export.patch` 把内核 console 导出到 USB EP0 | 与 `k60_usblog` 配合 |
| `k60_usblog` | 调试 | 0/1/2 | 代码默认 | `0300-k60-usblog-ep0.patch` USB 日志级别 | 刷机时的主要日志通道 |
| `k60_usbvend` | 调试 / USB | 0/1/2 | 0（= 0409 原样） | `0410-k60-usb-vendor-loopback.patch`：0 = 67 字节两接口 CDC-ACM、无回环；1 = 98 字节复合描述符（IAD + IF2 vendor 0xff/0xfe，EP 0x03 OUT / 0x83 IN）+ EP6→EP7 回环；2 = 控制台描述符不变、回环跑 CDC 数据对 EP2→EP3（普通 COM 口可验） | mode 1 的 IF2 主机侧没有驱动，要用 libusb 直接开；mode 2 必须同时开 `k60_usblog`（控制台让位给回环） |
| `pong_modem` | uint32 | 0 | `patches/xnu/0621-k60-modem-pas.patch:325` | `bsd/dev/pong_modem_pas.c` | 0 = quiet; 1 = modem image stage; 2 = image + QRTR verdict `K60MODEM qrtr: verdict ok` (cellular L3). |
| `k60_wallpaper_reset` | uint32 | 0 | `userland/ui_compat.c:677` | `select_initial_wallpaper()` | 1 = SpringBoard restores the stock 7410 wallpaper through the native setter on the next boot (springboard F1). |
| `k60_backlight` | uint32 | 1 | `drivers/PongAdreno/K60Backlight.cpp:443` | `k60_backlight_start()` | 0 = never start the backlight service (panel keeps the DBV bring-up left, 0xff). |
| `k60_backlight_control` | uint32 | **0** | `drivers/PongAdreno/K60Backlight.cpp:322` | `K60Backlight::publishFirst()` | 1 = impersonate AppleARMBacklight and publish `backlight-control`, but only if `metaCast("AppleARMBacklight")` then answers true (the kernel side of `IOObjectConformsTo`, `K60Backlight.cpp:161`); 0 (default) = publish `IODisplayParameters` only and never claim the control property. brightness-4 ran with 1 and backboardd crashed with four SIGSEGVs before the first frame (int-236), so the default is off. Judge a log with `python3 scripts/check-backlight-log.py <console.log> [--control=1]`. Index semantics: `docs/research/display/STATS-INDEX.md`. |
| `k60_backlight_invert` | uint32 | 0 | `drivers/PongAdreno/K60Backlight.cpp:390` | `K60Backlight::startService()` | 1 = invert the level-to-DBV mapping when the panel is wired the other way round. |
| `pong_thermal_bias` | int32 (mC) | 0 | `drivers/PongThermal/pong_thermal.c:277` | `pong_thermal_start()` | Synthetic offset added to every sensor reading so a cold device can be pushed up the zone ladder: 50000 = level 1, 75000 = level 2, 85000 = level 3. |
| `gprobe` | uint32 | 0 | `drivers/PongAdreno/PongDsiPanel.cpp:330` | `pong_panel_bring_up()` / `pong_panel_sample()` | 1 = arm the bounded 120 s panel-cadence observation window (GCC_DISP_AHB gate, DISPCC, MDSS) and let `K60 CADENCE:` lines print; 0 = the sample hook stays silent unless the one-shot post-bring-up check is still pending. |
| `p120` | 显示 | uint32 | 0 | `patches/xnu/0506-k60-120hz-refresh.patch` + `drivers/PongAdreno/PongDsiPanel.cpp` | `refreshHz()` / `pong_panel_switch_120()` | `p120=1` = send the m11a timing@2 eleven-packet switch once at the first completed GPU frame; report the requested 120 Hz to TimingElements and log the separately measured INTF1 rate; 0 (default) = keep the native 60 Hz mode. The `K60 PANEL: INTF1 ... te .../s` line is the measured evidence; a failed switch is visible there even though the one-time TimingElements publication already says 120. |
| `vsync` | 显示 | 仅 120（其他值忽略） | 0 | `patches/xnu/0506-k60-120hz-refresh.patch` + `drivers/PongAdreno/PongDsiPanel.cpp` | `refreshHz()` / `pong_panel_switch_120()` | Official display-document alias: `vsync=120` is accepted as equivalent to `p120=1`; it is a request, not a report. The same eleven-packet timing@2 switch runs at the first completed GPU frame; refreshHz() publishes the requested 120 Hz and the INTF1 line records the measured rate. Do not combine `vsync=120` with `k60_backlight_control=1` — the boot-args budget reaches 609 B, over the 608-byte limit. |
| `k60_fontscale` | 显示 | 整数 | 代码默认 | `0214-k60-console-font-scale.patch` 控制台字号倍率 | — |
| `k60_textonly` | 显示 | 真值 | 代码默认 | 只跑文本控制台，不初始化图形帧 | 用于隔离显示问题 |
| `fb_threads` | 显示 | 整数 | 代码默认 | `zzzz…-pong-hackios-ui-foundation.patch` framebuffer 线程数 | — |
| `k60_init_blob` | 启动链 | 真值 | 关闭 | `0391-k60-embedded-init.patch` 启用内嵌 init blob | 关掉则无 `/private/var/pong/init` |
| `k60_launchd_cache` | 启动链 | 真值 | 关闭 | `0391-k60-embedded-init.patch` 部署 launchd 缓存（22 job）| 依赖 `k60_init_blob` |
| `launchd_unsecure_cache` | 启动链 | 真值 | 代码默认 | 允许未签名 launchd 缓存 | 与 `k60_launchd_cache` 同用 |
| `k60_tolerate_cache_loader` | 启动链 | 真值 | 关闭 | `0314-k60-kern-exit-tolerate-and-clean.patch` 容忍缓存加载器失败 | — |
| `k60_entitlement_allow` | 安全 | 真值 | 关闭 | `0330-k60-entitlement-allow.patch` 放宽 entitlement 检查 | — |
| `k60-thermal` | 热管理 | 真值 | 1（开） | 发布 mTPL 的 IOKit 服务开关；`k60-thermal=0` 让 `k60_thermal_start()` 直接返回，不起两个 tsens 控制器 |
| `pong_thermal` | 热管理 | 真值 | 1（开） | 内核内建 tsens 驱动（`bsd/dev/pong_thermal.c`）开关；0 则只留启动日志，不读传感器、不起轮询线程 |
| `pong_thermal_bias` | 热管理 | 任意 int32（mC） | 0（不加） | 只给验证等级阶梯用：给所有有效读数加固定偏移；改变上报值、不改变硬件读数，也不是标定 |
| `k60_skip_iosurface` | GPU/IOKit | 真值 | 关闭 | `0332-k60-skip-prelinked-load.patch` 跳过预链接的 IOSurface 加载 | P-13x：避免第二个 IOSurfaceRoot |
| `k60_skip_firmware_mount` | 存储 | 真值 | 关闭 | `0320-k60-skip-firmware-mount.patch` 跳过 firmware 分区挂载 | 加快启动 |
| `k60_panic_reset` | 诊断 | 真值 | 关闭 | `0334-k60-panic-reset-fastboot.patch` panic 后自动重启 | 调试循环用 |
| `pong_allow_unauthenticated_root` | 安全 | 真值 | 关闭 | `zzzz…-pong-development-root-policy.patch` | — |
| `pong_software_keybag` | 安全 | 真值 | 关闭 | `0211-k60-display-startup.patch` 软件 keybag | — |
| `pong_data_mount` | 存储 | 真值 | 关闭 | `offline-owner-systemos-mount.patch` 挂 Data 卷 | 与 `pong_data_rw` 同用 |
| `pong_data_rw` | 存储 | 真值 | 只读 | `offline-owner-systemos-mount.patch` Data 卷可写 | 写盘会改动 Data |
| `xpcproxy_idversion` | 启动链 | 真值 | 关闭 | `zzzz…-pong-hackios-launchd-exec.patch` xpcproxy 版本兼容 | — |
| `pong_wifi` | WiFi | 1 或 2 | 未设 = 不启动 | 1 = 启动板级 worker；2 = 启动 worker，并在私有 fixture 存在时同时开启关联测试。缺它则 `pong_wifi_start_optional()` 只做 `pong_rpmh_init()` 就返回，日志里没有报错 |
| `k60_wifi_rsc` | WiFi | 0..2 | 0 = 不动 RSC | 1 = 只读探针 TCS4 后拒绝投票；2 = 允许 RPMh 投票。默认 fail-safe，因为对未上电 RSC 写入会挂死整机（K60-TOUCH-PARAMS.md:120,174） |
| `k60_wifi_stage` | WiFi | 0..10 | 0 = 跑全部 | 只跑到第 N 级就停，用于把早期挂死收敛到一个 MMIO 块；超范围值等于全跑 |
| `pong_wifi_dma_mib` | WiFi | 64..128 | 64 | 只接受 64/128，其它值 `return fail("WiFi DMA budget must be 64 or 128 MiB")` 后整条线停 |
| `pong_wifi_diag` | WiFi | 真值 | 关闭 | 打开 progressDiagnostic，把 stage 进度写进 `pong_wifi_progress[]` |
| `pong_wifi_test` | WiFi | 真值 | 关闭 | 关联测试：拿到 MAC 后主动连接 fixture 里的 AP；`pong_wifi=2` 是等价且不增加命令行字节的入口 |
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

### `pong_gpu_coherent`

- **所属**：GPU / 提交（每次 `[MTLCommandBuffer commit]` 的缓存维护）
- **接受值**：`0` 关 / `1` 强制开（**不证明**）/ `2` 跑探针（默认）
- **未设时**：2 —— 探针，两个方向都过才置位
- **作用**：PongAdrenoNativeGlue.cpp:151 用 `coherenceProbe()` 的结论给 `native_adreno_io_coherent` 赋值；该变量非零时 `NativeAdrenoVm::publishMapped()`（`submit/NativeAdrenoVm.cpp:359`）、`acquireImported()`（`:389`）与 `NativeAdrenoUserClient.cpp:268` 才真正跳过导入帧的 clean+invalidate
- **陷阱**：这三处跳过判据一直存在，但此前**全仓无人给该变量赋值**，所以全是死代码；实测每次提交维护 93.2 MiB 导入帧（`usblog-20261118-233946`，`publish` 中位 6,635 µs、`ibytes/cachebytes=1.00`）。探针不读 DTS、不参考 A740，而是写/读真实页并核对 DRAM，脏行不足时最多重试 8 次（sheng int-150 见过一次被写回后的假阳性）。判据写在 `docs/research/gpu/FLIGHT-CARD-20261119b.md`
- **源码**：`drivers/PongAdreno/PongAdrenoNativeGlue.cpp:149`
- **源码**：`drivers/PongAdreno/PongAdrenoNativeGlue.cpp:151`
- **源码**：`drivers/PongAdreno/submit/NativeAdrenoVm.cpp:359`

### `pong_surface_pitch`

**默认是 `0`（2026-11-19 改回）**：把行距差关掉是**替客户端改几何**，而量到收益的那一飞
（`usblog-20261119-125434`）没有确认画面没有斜切——那张卡的 S8 至今未由人目视确认。
CPU 数字更好看不构成让它做默认值的理由；要开就自己写 `pong_surface_pitch=1`，启动行还余 11 字节。


- **所属**：`drivers/PongAdreno/`（宏）与 `MiniIOSurface`（`surfaceCreate()`，经 xnu 补丁）
- **接受值**：`0` 或 `1`；未设时按 **1**（关闭一个行距）
- **作用**：`1` 时忽略客户端给的 `IOSurfaceBytesPerRow`，把 `bpr` 算成
  `alignUp(width * bytesPerElement, MINISURF_ROW_ALIGN)`，并在请求值不同时打印
  `MiniIOSurface: row bytes asked=%llu reported=%llu (one pitch only)`。
  `0` 时回到「客户端要多少给多少」。
- **为什么**：2026-11-19 的 `gpu-surface-20261119` 飞行枚举了 19 块 surface，
  其中扫描画布是 `sid=15 1440x3200 bpr=5888 planes=0 alloc=18841600`，而我们自己创建的两块
  是 `bpr=5760`。5888 只能来自 `dictNumber(props, "IOSurfaceBytesPerRow", 0)` 这一行。
- **陷阱**：客户端是否尊重回报的行距**尚未在真机验证**；不尊重则画面斜切。
  判据必须包含「画面正确」这一条，而且不得用「帧还在出」代替它。

### `pong_gpu_blit_probe`

- **所属**：GPU / 扫出（`[MTLCommandBuffer commit]` 里那次全屏 blit 的成本归因）
- **接受值**：`1` 开；**未设时关**
- **未设时**：关
- **作用**：`PongMetalScanout.h` 在第一帧真实拷贝成功之后，用同样的 API 形状再拷两次同样的字节：
  ① 客户端 surface → GPU 自有缓冲（`src-to-device`），② 该缓冲 → 固件帧缓冲（`device-to-scanout`）。
  三处独立测量（内核 `gpu=`、客户端 `G commit-to-complete`、合成器 `us each in the driver`）都指向
  12.6 ms / 18.4 MB = 1.5 GB/s，但没有任何一个能区分「目标端慢」「Turnip 的拷贝实现慢」「带宽本身慢」。
  这一对照正是用来分开这三者的
- **它已经回答完了，所以默认关**（2026-11-19，P-244）：`gpu-blitprobe2-20261119` 上实测
  `bytes=18432000 src-to-device=1993 us device-to-scanout=1835 us`，两块目标分别是 9.25 GB/s 与
  10.04 GB/s ⇒ **固件帧缓冲不是慢的那个**，对照没有剩余问题要问。同一次飞行最后以
  `CP/SMMU fault` 收场（受管对象从 331 长到 951、字节从 276 MB 长到 557 MB），探针多写的那一帧
  无法证明无辜；而且它按源行距写目标，会让**那一帧**斜切
- **陷阱**：它只在第一帧跑一次，所以日志里要么有一行、要么一行都没有；没有时先去查
  `scanout copy …` 那一行在不在，不要直接读成「对照很便宜」。启动行已用 596 / 607 B，
  所以想打开它必须自己腾出 20 字节（见 `## 参数预算`）——这是有意的成本，不是遗漏
- **源码**：`drivers/PongMetal/PongMetalScanout.h:114`
- **源码**：`drivers/PongMetal/GpuScanoutPresenter.h:116`

### `gbench`

- **所属**：`drivers/PongMetal/`（扫出 worker 的有界基准循环）
- **接受值**：`0`..`120`；超过 120 被夹到 120
- **未设时**：**`gperf` 出现在启动行时按 24 次**，否则不跑
- **作用**：在第一帧真实拷贝成功之后、内核 retire 映射之前，用同一个 `present()` 再拷 N 次同一帧，
  每次打印一行 `scanout bench n=<i>/<N> import=… encode=… submit=… gpu=… sum=… status=0x…`
- **为什么**：`gpu-pitchoff-20261119`（卡 j）的 `gpu` 中位 5,983 µs、`gpu-perf-20261119`（卡 k）飞行
  时屏幕静止只有 4 帧，稳态样本数为 0。判据一旦依赖「设备上恰好有东西在动」就不是判据
  （P-236 同族）。这个循环把同一次工作重复到够多，测的还是同一次工作
- **陷阱**：它在同一个 offer 内跑，所以源页仍然有效——不要在 `PongScanoutComplete` 之后调用
  （那之后内核已 `release()` 映射，`usblog-20261119` 的 P-244 就是从那类误用开始的）；
  循环次数有上限，且 `status` 非 0 立即中止，不会把一次启动变成无限基准
- **源码**：`drivers/PongMetal/PongMetalScanout.h:60`
- **源码**：`drivers/PongMetal/PongMetalScanout.h:198`

### `gperf`

- **所属**：`drivers/PongAdreno/`（GMU 运行期调档）
- **接受值**：`1`..`13`；`0` 与大于 `13` 的值被 `PongAdrenoGmuVotePerf()` 以 `PongGpuArgument` 拒绝
- **未设时**：不投票 —— 启动时那一次 `default_gpu_index` 是全程唯一的票
- **作用**：`PongAdrenoPlatform.cpp` 在 `PongAdrenoCpStart()` 成功之后（即 GMU 已持有 GX 域、
  GX 时钟已开）读这个参数，非零就调 `PongAdrenoGmuVotePerf(&gmu,perf,…)`，向 GMU 发
  `{ack type 1, GX 档位, DDR 档位}` 到 HFI id 30（`GX_BW_PERF_VOTE`），成功后打印
  `GPU level vote from gperf` 一行（含 settle 后的 `perf_gpu_index` 与 `perf_bus_index`）
- **为什么需要**：`PongAdrenoPower.c:186-187` 只投一次启动票（`table.default_gpu_index=2`，
  注释 `DT initial-pwrlevel11 -> ascending wire index2`），**此后永不改档**；perf 表 14 档
  （`performance[0]=14` 是项数、`[1]=3` 是每档 word 数，`PongAdrenoPowerLevels[13-i]` 映射到
  索引 0=关 / **13=最高**）。t970 的 z164 在 GX 起来后重投同一条消息，本参数是它在 K60 上的入口
- **陷阱**：升档改变功耗与发热，**不该由默认值决定**；投票只在 CP 起来之后合法（那之前 GMU 还没
  接管 GX，发出去要么被拒要么挂死启动）；同一时刻只允许一个未完成的 HFI 头
  （`hfi.pending_header` 时返回 `PongGpuBusy` 而不是排队）；1 秒等不到回复即 `PongGpuTimeout`，
  不会无限轮询。DDR 档位始终沿用启动票的值，这个参数只动 GX 档
- **源码**：`drivers/PongAdreno/PongAdrenoPlatform.cpp:558`
- **源码**：`drivers/PongAdreno/PongAdrenoGmu.c:242`
- **源码**：`drivers/PongAdreno/PongAdrenoPower.c:186`

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
- **接受值**：1 或 2
- **未设时**：不启动（`pong_wifi_start_optional()` 只做 `pong_rpmh_init()` 就返回）
- **作用**：1 = 通过后 `kernel_thread_start(worker)` 起 QCA6490 bring-up 线程；2 = 同一 worker，并在私有 fixture 存在时同时开启关联测试（与 `pong_wifi_test=1` 等价，但复用已有参数、命令行不多占字节）
- **陷阱**：worker 比 `k60_usblog_start()`（`bsd_init.c:1341`）早约 180 行运行；在控制台起来之前碰未上时钟的外设会挂死整机、串口 0 字节（P-49）。驱动侧已有 `k60_usblog_console_up()` 门，但仍应配合 `k60_wifi_stage` 逐级放行
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:730-733`；关联测试分支 `PongWifiPlatform.cpp:579-580`

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
- **作用**：拿到 station MAC 后主动关联测试 AP；也可以用 `pong_wifi=2` 达到同样效果而不增加命令行字节
- **陷阱**：没有真实 board data（BDF）时连不上，日志停在 `Pong: actual QMI board firmware` 之后；注意 `pong_wifi=2` 仅在源码/构建包含私有 fixture 时才会进入关联测试
- **源码**：`drivers/PongWifi/PongWifiPlatform.cpp:571`、`:579-580`、`drivers/PongWifi/PongWifiNet.cpp:892`

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
pong_wifi=2 k60_wifi_rsc=2                    +15 -> 602   （mission5 关联测试；与 =1 同长）
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

2026-11-19 起基线改为 30 项 596 字节（`pong_metal=1`、`sheng-gpu-addon=1` 加入，`k60_fontscale=3` 移除），余 11：上面那张以 575 为基线的表整体右移 21 字节，`pong_wifi=1`（+12）现在是 608、`k60_wifi_rsc` 系列因此全部超限，充电认证的 `k60_charge_auth=1`（+18）是 614。这几项只跑进探针镜像（去掉 `applog=1` 后 587：wifi 599、charge-auth 605 都装得下），或先按上面的让位项腾字节。

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
| 作用 | 1 = 显式开启 Data 卷挂载后、受 HR-01 四条件约束的 cmd-db / DRV-2 `0x17a20000` 只读取证。历史 railh 只有 cmd-db magic、ldoc2、RSC 布局三行；后加 LCX/LMX 采样器的槽/command 覆盖、状态语义与失败也只尝试一次尚待离线审计。`complete`/`valid` 或非零 `cmd_data` 不证明轨有效；缺记录不证明轨关闭。当前 `resources()` 返回 -63，不置 ResourcesHeld；legacy `k60_rail_inherit()` 不能保护生产 owner 发布路径（P-223） |

**为什么默认关闭**：`docs/ops/HARD-RULES.md` 的 HR-01 规定默认不得访问 RSC —— 2026-11-09 有两次
早期启动阶段首读即整机死（零控制台）。2026-11-14 的 `rail-20261114h` 记录了一次 **Data 挂载之后只读**存活
（`E:\k60-work\evidence\usblog-20261114-railh\console.log:477-479`，3,366 行、129 行 SpringBoard、
`panicMarker=null`），但一次存活不足以改成默认。所以：只读、单次、必须显式开启；**写 TCS 与
`CONTROL_TRIGGER` 仍然全面禁止**。2026-11-16 15:03 裁决撤回 C 与功能图批准；
`adsp-20261116a` 被门禁拒绝，无 boot.img、未上机。下一次 rail-only 须先完成离线审计再由 Lead 决定，
不增参数、不扩大到其它 DRV；参数字节数须从真实镜像量，不能沿用旧 592/593 B 估算。

### `k60_cpufreq`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不探测） |
| 取值 | 1 / 2 / 3 / 5 / 6 / 7 / 8（4 被拒绝，9 已禁用） |
| 来源 | `drivers/PongPower/K60CpuFreqProbe.cpp`（`PE_parse_boot_argn("k60_cpufreq", &mode, sizeof(mode))`）；`K60Battery.cpp:517` 在电池租约判断之前做第一次读取，`K60Battery.cpp:546-550` 在 `begin` 成功后 5 s 调用 `k60_cpufreq_probe_late()` |
| 作用 | 1 = 只读 EPSS 三域与 L3（enable/state/vote/LUT 行）；2 = 只给 domain 0 投最高非 turbo 档；3 = 三域 + L3；5 = 内核线程每 16 ms 读 `processor_info(PROCESSOR_CPU_LOAD_INFO)`，把每 CPU 的 user/system/idle/nice tick 差分后按域取最忙 CPU，喂 governor 并打印 busy/governor/hw，只读、不投票；6 = 只给 domain 0 投**最低**非 turbo 档（降档不需要抬压，是首次写入的最安全方向）。2/3/6 是**瞬态验证写**：写前检查 enable 与档位，保存每个目标寄存器原值，写后逐条回读，再立即写回原值；不会留下持续投票。6 在写后与恢复后各等 20 ms，日志追加 `state=<写前>-><写后>-><恢复后>`；7 = 复用 5 的采样线程，从第 10 秒起观察 governor，在首次出现 governor 档位低于已投档位的窗口（启动突发约 78–85 s 后才首次降档）起 10 秒内把后续**降档**决策写进 EPSS（升档请求只打印 `raise refused` 并退回已投档位，最多 16 票），每次写后回读并打印 `mode7 apply … state=<写前>-><写后>`，到 10 秒窗口结束、100 秒上限或线程停止时恢复所有写过的域并打印 `mode7 restore …`。7 只降不升，因此同样不涉及抬压；8 = 与 7 同一受限期窗口，但**双向**写回（升档也写），投票上限 32 次，DCVS 控制位每次投票重新读取，并每 64 窗口重试 d1/d2 的 `DOMAIN_STATE` 匹配（辅核启动前读到 0，无法查表）。依据是参考 `CpuFreqProbe.cpp:198-203, 293-296` 对升档也只写工作点、由 EPSS 固件完成电压过渡。8 只在 d0 成立：d1 的写回回读成功但 `state` 不变、硬件仍由固件自主变频；9 = DCVS 控制位/单行/全行写入探针，**已禁用**：image u 与 image t 两次带 9 启动都在串口出现前卡死（0 字节、`port-not-observed`），`3a0a5511` 在入口直接拒绝 9。 |

**为什么默认关闭**：EPSS 是 CPU 频率/电压的现场控制点。官方 §5 要求 OS 明确外设电源投票的所有权与引用计数；在 governor、供电和温控路径接入之前，任何持续写都可能与固件或其它 owner 冲突。探针镜像必须确认设备独占空窗，首次只做 d0 单域。

**陷阱**：`k60_cpufreq` 不在 `board.toml` 的默认参数里。探针镜像若保留 `applog=1`，命令行会超过 DarwinBoot 的 607 字节上限（实测 612 字节）；构建时必须临时去掉 `applog=1`，上机结束后恢复，并把该镜像视为探针镜像而非发布镜像。该参数已列入 `scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS`，但参数 gate 仍会检查 board 契约的其余部分；image i/j/k 构建时 gate 尚未接受该名字。`k60_cpufreq=2/3` 的升档写入仍未上机；`k60_cpufreq=6` 已于 2026-11-19 02:47 以 image n 上机（d0 `state=81->15->81`、`readback=ok restored=1`），`k60_cpufreq=5` 已于 2026-11-18 23:19 以 image l 只读上机（159,147 B console，274 条 `sample win=`，d0 可降到 300 MHz，无 `sample stop`，因为 300 s autoreset 先到），23:53 又以 image m 复测 88 条。`k60_cpufreq=7` 已于 2026-11-19 03:26 以 image r 上机：`mode7 armed win=854 d0 level=9`、`apply d0 level=9 (1324800kHz) readback=ok state=81->69`，10 s 后 `restore domains=1 votes=1`，硬件回到 1.5552 GHz；它在首次降档窗口后 10 s 内改变运行频率，探针镜像应保留 300 s 的抓取预算，并确认设备独占空窗。首次写入建议用 6 而不是 2：降档不抬压，日志里的 `state` 三元组能直接说明写入与恢复是否生效。`k60_cpufreq=8` 已于 2026-11-19 03:58 以 image s 上机（console 165,881 B，sha256 `d98bdc30…`，277 条 `sample win=`）：d0 双向写回共 11 票后 `mode8 restore domains=2 votes=11`，升档 `state=81->94`、降档 `state=94->59`，恢复后硬件回到 1.5552 GHz；d1 `state=130->130` 且采样 hw 仍 2.496 GHz，因此 8 的升档能力只在 d0 成立。帧下限（§5 :116）自 image w 起接入：采样线程读 CP 环提交窗口喂 boost 规划，mode 8 的升档窗口把 60 % 下限写成投票；image w（sha256 `005b3095…`）05:07 上机 276 条样本全部 `fr=0`，启动全程没有 GPU 提交，下限未激活，`sample` 行末尾带 `fr=<0|1>`。触摸计数（补丁 `0626-k60-touch-activity.patch`）自 image x 起导出：计数变化喂 `k60_boost_touch()`，1 s 窗口内 governor 的 `boost` 把 P 域抬到 top；`sample` 行末尾再带 `tb=<0|1>`，触摸时日志打印 `touch boost active`/`released`。image x 于 05:47 上机触摸：12 条 `touch boost` 日志、7 条 `tb=1`、计数 1→7，d0 governor 被抬到 1,804,800 kHz；但 mode 8 的写窗口在 ~20 s 已 `restore domains=1 votes=5`，触摸（~121 s）没写进寄存器。commit `9b8a36b6` 给触摸/帧重开短窗口（触摸 1 s/63 窗口、帧 300 ms/19 窗口，总票数 32），日志打印 `touch window`/`frame window`，该重开路径进了 image y（sha256 `71141ac7…`），但所有投票仍受 `kApplyLatestEndWindow=6250`（100 s）限制；`a0e8a060` 让信号窗口不再受该上限（仍受 32 票预算），archive 137,384 B sha256 `b65a10f1…`，image z（sha256 `59921097…`，30 项 603 B）用这份代码构建，06:47 尝试上机时设备不在 fastboot，未上机。image ab（sha256 `a0563a08…`，kernel `e5a26b91…`，30 项 603 B）07:18 上机触摸成功：win=6937 `touch window span=63`，d0 `level=0 state=36->15` 后 `level=13 state=15->94`，win=6976 样本 `d0=1000/1804800kHz/hw1804800kHz … tb=1`，窗口末 `restore domains=3 votes=27`；第二触 win=7207 仅 5 票即 `votes=32`，暴露票数整轮累计；`boost` 当时只作用于共享簇，轻触摸抬不动 d0。commit `43af2a5c` 把票数改为每窗口重置、`boost` 对每个域取 top，host 154 项，archive 137,520 B（`5d6d1203…`），image ac（sha256 `0d5a5411…`，kernel `001003aa…`）07:34 与 07:43 两次上机，启动与 mode 8 写回正常（`restore domains=2 votes=9`/`votes=7`），但两次采集都没有触摸（276/273 条样本全 `tb=0`），轻触摸与第二触预算仍未验证。`k60_cpufreq=9` 于 2026-11-19 07:56 以 image t（只含 mode 9、无温控补丁，boot.img sha256 `567d9b62…`）上机：fastboot 报 `Booting OKAY`，但 console 0 字节、`capture.json state=port-not-observed`、`returnedToFastboot=false`，需强制复位；它与 04:36 的 image u（mode 9 + thermal）同一签名，共同因素是 mode 9 而非温控补丁，`3a0a5511` 已让入口拒绝 9。

### `pong_gpu_dcvs`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不启动 DCVS） |
| 取值 | 0 = 关闭；1 = 启动 DCVS；2 = 启动并做一次 HFI 投票探针（升一档再立刻还原） |
| 来源 | `drivers/PongAdreno/PongAdrenoDcvs.cpp`（`PE_parse_boot_argn("pong_gpu_dcvs", &on, sizeof(on))`）；`PongAdrenoPlatform.cpp` 在 Adreno 启动记录完成后调用 `pong_adreno_dcvs_start()`，CP 启动失败则不启动 |
| 作用 | ≥1 = 起 16 ms 线程：读 GMU XO 忙碌计数器 → `k60_gpu_governor_window()` → HFI id 30 投 `{1, level, bus index}`（第三字为带宽档索引）；计数器从零转非零、或 2/4 提交窗口活跃且 GPU 空闲时先布防 50 ms 唤醒档（两倍频率、至少 578 MHz，日志 `DCVS prewake`）；连续 8 次投票被拒就停线程并毒化 HFI。=2 时另在进入循环前投一档（`DCVS probe up`）并立即还原（`DCVS probe restore`），用于无 GPU 负载时验证 HFI id 30 是否被接受。日志前缀 `PONG ADRENO: `，每 10 s 一条档位汇总；触摸计数变化后 1 s 内目标档强制为 top，并打印 `DCVS touch top`/`DCVS touch release`（计数与时间在参数里）。 |

伴随参数（都未列入 board 契约，只有 `pong_gpu_dcvs`≥1 时才读取）：

| 参数 | 默认 | 含义 |
|---|---|---|
| `pong_gpu_max_level` | 13 | DCVS 可投的最高档；越界（<1 或 >13）回落 13，`table.count = top` 所以它同时是档位表的顶 |
| `pong_gpu_dcvs_min` | 1 | 空闲允许降到的最低档；<1 夹到 1，>最高档夹到最高档 |
| `pong_gpu_dcvs_boost_ms` | 50 | 忙碌计数由零转非零、或提交窗口提前布防后的唤醒档保持毫秒数；0 = 立即回落，不再保持 |

触摸保持不另设参数：窗口固定 1 s，与官网 §5 :115 的 `gpu-dcvs-boost-ms` 一致。`pong_gpu_dcvs=1` 时触摸会强制目标档为 top，窗口结束立刻回到 governor 的档位；`=2` 的启动探针不受触摸影响。

**为什么默认关闭**：官方 §5 要求先处理稳压器/互连/温控顺序。DCVS 只发 HFI 投票，没有温度与电压顺序，
帧信号已从 CP 环接入但没有 GPU 负载验证，触摸计数已接入但没有真机触摸；首次上机只验证计数器在动、投票是否被接受。

**陷阱**：image o（2026-11-19）用探针 board（去掉 `applog=1`）+ `pong_handoff_publish=1` +
`pong_gpu_dcvs=1`，共 30 项 606 字节，在 607 字节上限内；再加 `applog=1` 会超限。
该参数已列入 `scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS`。image o 已于 02:14 上机：
线程启动、24 条空闲汇总、无投票、无 panic；因为整轮没有 GPU 提交，投票路径只有 `=2` 的探针能验证。
image q（`pong_gpu_dcvs=2`，2026-11-19 02:36）返回
`DCVS probe up result=0 a=0x200000000 b=0x1` 与 `DCVS probe restore result=0 a=0x100000000 b=0x0`：
HFI id 30 的升档与还原投票都被固件接受（错误码 0），整轮仍空闲、29 条汇总窗口、无 panic。

### `pong_handoff_publish`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不发布） |
| 取值 | 0 / 1 |
| 来源 | `patches/xnu/0619-k60-adsp-glink-handoff.patch`（`iokit/bsddev/IOKitBSDInit.cpp`，`PE_parse_boot_argn("pong_handoff_publish", …) == 1u`）|
| 作用 | 1 = 在 IOKitBSDInit 早期跑 `k60_adsp_handoff_publish()`：claim owner=1 → 配置/范围/载体预检 → 安装 board/platform → `k60_adsp_owner_acquire`。当前真实 board 的 `resources()` 在 lease/排他/stopped 通过后仍返回 `K60BoardUnsupported`(-63)，打印 `K60ADSP: rails not verified for handoff; no PAS/SMEM mutation`；owner 拒绝在下游 map_smem、SMEM 分配、INIT_IMAGE、MEM_SETUP、COPY/BSS、AUTH、104 字节 lease 发布之前。`published authenticated ... flags=15` 是未来完整证明后的验收日志，非当前可达成功。 |

**当前状态（2026-11-16 15:03）**：本轮不开 `pong_handoff_publish` 或 `pong_adsp`、不出功能图。历史 owner=1 先 claim 后，`kern_exec.c` 的 legacy `k60_adsp_startup_claim(2u)` 会失败并打
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
这是 2026-11-13 的 legacy 诊断记录。2026-11-16 15:03 裁决要求本轮不启用 `pong_adsp`；
legacy 后加的 rail 检查保留，但它不经过生产 owner stages，也不能以 TCS 请求证明供电或授权 SCM。
不能作为可用的音频/电池前提。

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

### `pong_thermal_bias`

| 项 | 值 |
|---|---|
| 类型 | int32（毫摄氏度） |
| 默认 | 0（不加偏移） |
| 来源 | `drivers/PongThermal/pong_thermal.c`（`PE_parse_boot_argn("pong_thermal_bias", &pong_thermal_bias_mc, sizeof(pong_thermal_bias_mc))`）|
| 作用 | 非 0 时给每一路有效读数加这个偏移，再算五域温度与 zone 等级 |

**为什么存在**：本板冷机读数 40–56℃（`docs/research/thermal/08-KERNEL-DRIVER.md` §5 的首次上机日志），
离最低被动档 90℃ 还差 34℃，跑任何负载都到不了 level 1，等级阶梯就永远只能验 0 档。
`pong_thermal_bias=50000` 把 45℃ 的板子抬到 95℃、`=75000` 抬到 120℃、`=85000` 抬到 130℃，
于是 1/2/3 三档都能在冷机上看到（逐档算式见 `docs/research/thermal/LEVEL-MAP.md` §5.2）。
**它不改硬件**：读窗口仍是只读，偏移只作用于内存里的读数；日志会打
`PongThermal: bias N mC added to every reading (validation only)`，看到这行就说明数据是人为抬过的。
**不要把它当标定**：本板没有 `qcom,tsens-calibration`，真正的标定系数不在 DT 里
（`docs/research/thermal/01-SAME-HARDWARE.md` §4）。
