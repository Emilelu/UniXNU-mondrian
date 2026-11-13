# Boot 参数参考

> 2026-11-12 生成。目的：把「每个 boot-arg 接受什么值、默认是什么、错了会怎样」
> 集中到一处。P-144（`pong_metal=2` 不发布）与 P-145（`pong_adreno_start`
> 从未配过）都是参数语义不清造成的。

**硬限制：arm64 boot-args 上限 608 字节**（含空格分隔）。当前 30 项 591 字节，余 17。

## 一览

| 参数 | 所属 | 接受值 | 未设时 | 陷阱 |
|---|---|---|---|---|
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

## WiFi（`drivers/PongWifi/`）
只有构建时 `CONFIG_XNU_PONG_WIFI=y` 才存在这些参数；默认构建里 `pong_wifi_start_optional()` 不参与链接。
### `pong_wifi`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不起 WiFi） |
| 取值 | 0 / 1 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:679 `pong_wifi_start_optional()` |
| 作用 | 1 = 启动 WiFi worker（先 `pong_rpmh_init()`，再起内核线程）。必须同时构建时打开 `CONFIG_XNU_PONG_WIFI=y`，否则归档根本没链进内核，这个参数无效。 |
### `k60_wifi_rsc`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不碰 RSC） |
| 取值 | 0 / 1 / 2 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:707 |
| 作用 | WiFi 侧 RPMh 投票闸门。1 = 只做只读探针（读 RSC id/caps/idle/status 并打印）；2 = 探针通过后允许投票。默认 0，因为 RSC 电源域在本板从未被证明，写错会硬挂。 |
### `pong_wifi_dma_mib`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 64 |
| 取值 | 64 / 128 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:382 |
| 作用 | WiFi DMA arena 预算（MiB）。只接受 64 或 128，其它值直接 `fail("WiFi DMA budget must be 64 or 128 MiB")`。128 会先试 128，失败后回退 64。 |
### `pong_wifi_diag`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0 |
| 取值 | 0 / 1 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:621、PongWifiNet.cpp:890 |
| 作用 | 1 = 逐步打印 WiFi 进度（每个阶段一行），用于定位卡在哪一步。不影响功能路径。 |
### `pong_wifi_test`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0 |
| 取值 | 0 / 1 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:546、PongWifiNet.cpp:892 |
| 作用 | 1 = 打开关联测试（需要仓库内有私有 SSID/口令 fixture，缺失时打印 `WiFi association test SKIP: no private network fixture` 并跳过）。 |
### `pong_wifi_alt`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0 |
| 取值 | 0 / 1 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:547 |
| 作用 | 仅在 `pong_wifi_test=1` 时有效：1 = 用备用关联路径（第二条扫描/认证序列）。 |
### `pong_wifi_band`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0（不限） |
| 取值 | 0 / 2 / 5 |
| 来源 | drivers/PongWifi/PongWifiPlatform.cpp:548 |
| 作用 | 仅在 `pong_wifi_test=1` 时有效：限定首次关联的频段。其它值打印 `WiFi association test SKIP: band must be 0, 2 or 5` 并关闭测试。 |
### `pong_wifi_cycle`

| 项 | 值 |
|---|---|
| 类型 | uint32 |
| 默认 | 0 |
| 取值 | 0 / 1 |
| 来源 | drivers/PongWifi/PongWifiNet.cpp:893 |
| 作用 | 仅在 `pong_wifi_test=1` 时有效：1 = 断链后自动重连循环（`pong_wifi_test_reconnect()`）。 |
