# Boot 参数参考

> 2026-11-12 生成。目的：把「每个 boot-arg 接受什么值、默认是什么、错了会怎样」
> 集中到一处。P-144（`pong_metal=2` 不发布）与 P-145（`pong_adreno_start`
> 从未配过）都是参数语义不清造成的。

**硬限制：arm64 boot-args 上限 608 字节**（含空格分隔）。当前 30 项 602 字节，余 6。

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
| `k60_selftest_reboot` | 自检 | 秒 | 不重启 | 手动测试时是浪费的 23 字节，可让位给 GPU 开关 |

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
当前 30 项 602，余 6
pong_metal=1        需 13  -> 超限 7
pong_gpu_scanout=1  需 19  -> 超限 14
```

候选让位项：`k60_selftest_reboot=300`（23 字节，手动测试不需要）。
