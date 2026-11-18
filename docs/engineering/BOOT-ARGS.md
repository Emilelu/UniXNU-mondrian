# Boot 参数参考

> 2026-11-12 生成。目的：把「每个 boot-arg 接受什么值、默认是什么、错了会怎样」
> 集中到一处。P-144（`pong_metal=2` 不发布）与 P-145（`pong_adreno_start`
> 从未配过）都是参数语义不清造成的。

**硬限制：arm64 boot-args 上限 608 字节**（含空格分隔）。2026-11-18 探针镜像为 30 项
603 字节（临时去掉 `applog=1`），余 4；发布镜像仍以 board.toml 的完整参数为准。

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
| `pong_gpu_dcvs` | 电源 / GPU | 0 / 1 / 2 | 0（关闭） | `drivers/PongAdreno/PongAdrenoDcvs.cpp`；1=16 ms 读 GMU XO 忙碌计数器并经 HFI id 30 投票，连续 8 次被拒停线程；2=再在启动时做一次升档投票并立即还原；image o 02:14 已上机（空闲、24 窗口、无投票）；image q 02:36 用 2 验证 HFI id 30 投票被接受（升档+还原各一次、错误码 0） |
| `pong_gpu_max_level` | 电源 / GPU | 1..13 | 13 | `drivers/PongAdreno/PongAdrenoDcvs.cpp`；DCVS 可投的最高档，越界回落 13，仅在 `pong_gpu_dcvs=1` 时读取 |
| `pong_gpu_dcvs_min` | 电源 / GPU | 1..13 | 1 | 同上；空闲时允许降到的最低档，小于 1 夹到 1、大于最高档夹到最高档 |
| `pong_gpu_dcvs_boost_ms` | 电源 / GPU | ≥ 0（毫秒） | 50 | 同上；GMU 忙碌计数从零转非零后唤醒档（两倍频率、至少 578 MHz）的保持时间，0 = 不保持 |
| `k60_cpufreq` | 电源 / EPSS | 1/2/3/5/6/7/8 | 0（关闭） | `drivers/PongPower/K60CpuFreqProbe.cpp`；1=只读三域+L3，2=d0 最高非 turbo，3=三域+L3，5=16 ms `processor_info` 只读采样，6=d0 降到最低档（已上机），7=首个降档窗口起 10 s 按 governor 只降档写回并恢复（100 s 上限，已上机），8=同一窗口内双向写回并恢复（已上机）；2/3 为瞬态验证写（写前守卫、写后回读、立即恢复），4 被拒绝；2/3 未上机，5 已于 2026-11-18 23:19 以 image l 只读上机（274 条样本），6 已于 2026-11-19 02:47 以 image n 上机，7 已于 03:26 以 image r 上机、8 已于 03:58 以 image s 上机（d0 双向生效，d1 写回不被 EPSS 接受）；探针镜像需去掉 `applog=1` 才不超 607 字节 |
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
上限 608
当前 30 项 591，余 17
pong_metal=1        需 13  -> 超限 7
pong_gpu_scanout=1  需 19  -> 超限 14
```

候选让位项：`k60_selftest_reboot=300`（23 字节，手动测试不需要）。

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
| 取值 | 1 / 2 / 3 / 5 / 6 / 7 / 8 / 9（4 被拒绝） |
| 来源 | `drivers/PongPower/K60CpuFreqProbe.cpp`（`PE_parse_boot_argn("k60_cpufreq", &mode, sizeof(mode))`）；`K60Battery.cpp:517` 在电池租约判断之前做第一次读取，`K60Battery.cpp:546-550` 在 `begin` 成功后 5 s 调用 `k60_cpufreq_probe_late()` |
| 作用 | 1 = 只读 EPSS 三域与 L3（enable/state/vote/LUT 行）；2 = 只给 domain 0 投最高非 turbo 档；3 = 三域 + L3；5 = 内核线程每 16 ms 读 `processor_info(PROCESSOR_CPU_LOAD_INFO)`，把每 CPU 的 user/system/idle/nice tick 差分后按域取最忙 CPU，喂 governor 并打印 busy/governor/hw，只读、不投票；6 = 只给 domain 0 投**最低**非 turbo 档（降档不需要抬压，是首次写入的最安全方向）。2/3/6 是**瞬态验证写**：写前检查 enable 与档位，保存每个目标寄存器原值，写后逐条回读，再立即写回原值；不会留下持续投票。6 在写后与恢复后各等 20 ms，日志追加 `state=<写前>-><写后>-><恢复后>`；7 = 复用 5 的采样线程，从第 10 秒起观察 governor，在首次出现 governor 档位低于已投档位的窗口（启动突发约 78–85 s 后才首次降档）起 10 秒内把后续**降档**决策写进 EPSS（升档请求只打印 `raise refused` 并退回已投档位，最多 16 票），每次写后回读并打印 `mode7 apply … state=<写前>-><写后>`，到 10 秒窗口结束、100 秒上限或线程停止时恢复所有写过的域并打印 `mode7 restore …`。7 只降不升，因此同样不涉及抬压；8 = 与 7 同一受限期窗口，但**双向**写回（升档也写），投票上限 32 次，DCVS 控制位每次投票重新读取，并每 64 窗口重试 d1/d2 的 `DOMAIN_STATE` 匹配（辅核启动前读到 0，无法查表）。依据是参考 `CpuFreqProbe.cpp:198-203, 293-296` 对升档也只写工作点、由 EPSS 固件完成电压过渡。8 只在 d0 成立：d1 的写回回读成功但 `state` 不变、硬件仍由固件自主变频；9 = 对三域分别做 DCVS 控制位/单行/全行写入探针（image t 已构建，未上机），用来判断大核簇为什么不接受持续投票。 |

**为什么默认关闭**：EPSS 是 CPU 频率/电压的现场控制点。官方 §5 要求 OS 明确外设电源投票的所有权与引用计数；在 governor、供电和温控路径接入之前，任何持续写都可能与固件或其它 owner 冲突。探针镜像必须确认设备独占空窗，首次只做 d0 单域。

**陷阱**：`k60_cpufreq` 不在 `board.toml` 的默认参数里。探针镜像若保留 `applog=1`，命令行会超过 DarwinBoot 的 607 字节上限（实测 612 字节）；构建时必须临时去掉 `applog=1`，上机结束后恢复，并把该镜像视为探针镜像而非发布镜像。该参数已列入 `scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS`，但参数 gate 仍会检查 board 契约的其余部分；image i/j/k 构建时 gate 尚未接受该名字。`k60_cpufreq=2/3` 的升档写入仍未上机；`k60_cpufreq=6` 已于 2026-11-19 02:47 以 image n 上机（d0 `state=81->15->81`、`readback=ok restored=1`），`k60_cpufreq=5` 已于 2026-11-18 23:19 以 image l 只读上机（159,147 B console，274 条 `sample win=`，d0 可降到 300 MHz，无 `sample stop`，因为 300 s autoreset 先到），23:53 又以 image m 复测 88 条。`k60_cpufreq=7` 已于 2026-11-19 03:26 以 image r 上机：`mode7 armed win=854 d0 level=9`、`apply d0 level=9 (1324800kHz) readback=ok state=81->69`，10 s 后 `restore domains=1 votes=1`，硬件回到 1.5552 GHz；它在首次降档窗口后 10 s 内改变运行频率，探针镜像应保留 300 s 的抓取预算，并确认设备独占空窗。首次写入建议用 6 而不是 2：降档不抬压，日志里的 `state` 三元组能直接说明写入与恢复是否生效。`k60_cpufreq=8` 已于 2026-11-19 03:58 以 image s 上机（console 165,881 B，sha256 `d98bdc30…`，277 条 `sample win=`）：d0 双向写回共 11 票后 `mode8 restore domains=2 votes=11`，升档 `state=81->94`、降档 `state=94->59`，恢复后硬件回到 1.5552 GHz；d1 `state=130->130` 且采样 hw 仍 2.496 GHz，因此 8 的升档能力只在 d0 成立。帧下限（§5 :116）自 image w 起接入：采样线程读 CP 环提交窗口喂 boost 规划，mode 8 的升档窗口把 60 % 下限写成投票；image w（sha256 `005b3095…`）05:07 上机 276 条样本全部 `fr=0`，启动全程没有 GPU 提交，下限未激活，`sample` 行末尾带 `fr=<0|1>`。触摸计数（补丁 `0622-k60-touch-activity.patch`）自 image x 起导出：计数变化喂 `k60_boost_touch()`，1 s 窗口内 governor 的 `boost` 把 P 域抬到 top；`sample` 行末尾再带 `tb=<0|1>`，触摸时日志打印 `touch boost active`/`released`。该路径尚未上机触摸。

### `pong_gpu_dcvs`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不启动 DCVS） |
| 取值 | 0 = 关闭；1 = 启动 DCVS；2 = 启动并做一次 HFI 投票探针（升一档再立刻还原） |
| 来源 | `drivers/PongAdreno/PongAdrenoDcvs.cpp`（`PE_parse_boot_argn("pong_gpu_dcvs", &on, sizeof(on))`）；`PongAdrenoPlatform.cpp` 在 Adreno 启动记录完成后调用 `pong_adreno_dcvs_start()`，CP 启动失败则不启动 |
| 作用 | ≥1 = 起 16 ms 线程：读 GMU XO 忙碌计数器 → `k60_gpu_governor_window()` → HFI id 30 投 `{1, level, bandwidth}`；计数器从零转非零时给 50 ms 唤醒档（两倍频率、至少 578 MHz）；连续 8 次投票被拒就停线程并毒化 HFI。=2 时另在进入循环前投一档（`DCVS probe up`）并立即还原（`DCVS probe restore`），用于无 GPU 负载时验证 HFI id 30 是否被接受。日志前缀 `PONG ADRENO: `，每 10 s 一条档位汇总；触摸计数变化后 1 s 内目标档强制为 top，并打印 `DCVS touch top`/`DCVS touch release`（计数与时间在参数里）。 |

伴随参数（都未列入 board 契约，只有 `pong_gpu_dcvs`≥1 时才读取）：

| 参数 | 默认 | 含义 |
|---|---|---|
| `pong_gpu_max_level` | 13 | DCVS 可投的最高档；越界（<1 或 >13）回落 13，`table.count = top` 所以它同时是档位表的顶 |
| `pong_gpu_dcvs_min` | 1 | 空闲允许降到的最低档；<1 夹到 1，>最高档夹到最高档 |
| `pong_gpu_dcvs_boost_ms` | 50 | 忙碌计数由零转非零后的唤醒档保持毫秒数；0 = 立即回落，不再保持 |

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
