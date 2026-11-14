# 背光计数索引（native_backlight_stats / native_backlight_request）

> 2026-11-15。上机判据要读这两个数组，但它们没有符号名可查、索引语义只写在
> 源码注释里。本文把 22 个槽位逐个写清，并给出三种启动配置下应该看到的值。
>
> 定义位置：`drivers/PongAdreno/K60Backlight.cpp:60`（`native_backlight_stats[16]`）
> 与 `drivers/PongAdreno/K60Backlight.cpp:64`（`native_backlight_request[6]`）。
> 两者都是 `extern "C"` 的 `volatile int32_t`，构建后用
> `llvm-nm kernel.macho | grep native_backlight` 能在内核里找到。
> 参考实现的同名数组见 sheng `package/AppleARMBacklight.cpp`，K60 版删掉了
> GENI/SPI 相关槽位（没有背光 IC），保留编号以免与日志对照时错位。

## native_backlight_stats[16]

| 索引 | 含义 | 默认镜像（control 关） | `k60_backlight_control=1` 且 conformance 成立 | 说明 |
|---|---|---|---|---|
| 0 | 服务阶段 | **3** | **4** | 1 = 已启动、2 = 事件源就绪、3 = 已发布（未声称 AppleARMBacklight）、4 = 已发布为 AppleARMBacklight；负值 = 失败的步骤号。判据里的「[0]=4」只在 `k60_backlight_control=1` 且 conformance 查询通过时成立 |
| 1 | 收到的亮度请求数 | 随 backboardd 递增 | 同左 | `setProperties()` 每接受一次 `brightness` 或 `brightness-nits` 加一（`K60Backlight.cpp:364` 的 `__atomic_fetch_add`） |
| 2 | 最后**写入**的 level（0..2047） | 2047（bring-up 后的 0xff） | 同左 | 由 `writeLevel()` 在 DCS 0x51 成功后写入，`K60Backlight.cpp:251` |
| 3 | 最后写入值反算的 level | 2047 | 同左 | `levelFromDbv(stats[4])`，用于确认 level↔DBV 的往返一致 |
| 4 | 最后**回读**的 DBV | 255 | 同左 | **不是硬件读回**：DCS 0x51 没有读命令，这里取 `pong_panel_brightness()` 记录的「上次成功写入的 DBV」（`PongDsiPanel.cpp:255`），见下文诚实说明 |
| 5 | 写入失败次数 | 0 | 0 | 每次 `pong_panel_set_brightness()` 非零即加一；上机判据要求它为 0 |
| 6 | GENI 协议字 | -1 | -1 | K60 无背光 IC，槽位保留恒为 -1 |
| 7 | GENI 时钟配置低半 | -1 | -1 | 同上 |
| 8 | GENI 时钟配置高半 | -1 | -1 | 同上 |
| 9 | 最后错误 engine<<8\|error | -1 | -1 | 同上 |
| 10 | 中断计数 | -1 | -1 | 同上 |
| 11 | 中断模式 | -1 | -1 | 同上 |
| 12 | 未识别中断数 | -1 | -1 | 同上 |
| 13 | 传输超时数 | -1 | -1 | 保留；K60 的超时由 `PongDsiPanel.cpp:107-190` 的 `dsi_failures` 统计，失败会走 stats[5] |
| 14 | 挂接尝试次数 | 1 | 1 | `startService()` 里置 1，表示服务已尝试 attach 到平台 |
| 15 | 完成的写入次数 | 随请求递增 | 同左 | 每次成功的 DCS 0x51 加一；上机时它应随 stats[1] 一起增长 |

## native_backlight_request[6]

| 索引 | 含义 | 默认镜像 | `control=1` | 说明 |
|---|---|---|---|---|
| 0 | 最后一次请求的 level | 2047 | 同左 | `setProperties()` 里夹紧后的目标值 |
| 1 | 最后一次请求的渐变毫秒 | 0 | 同左 | 来自 `FadePeriod`（16.16 秒），上限 5000 |
| 2 | 请求定时器触发次数 | 递增 | 同左 | `requestAction()` 每次进入加一（`K60Backlight.cpp:290`）；与 [3] 的差值是「定时器跑了但没有请求」的轮次 |
| 3 | 真正发起的渐变数 | 递增 | 同左 | `requestAction()` 取到有效请求后加一（:293） |
| 4 | conformance 结果 | **0** | **1** | `metaCast("AppleARMBacklight")` 是否为真，即用户态 `IOObjectConformsTo` 会不会答 true（`K60Backlight.cpp:161`） |
| 5 | 是否发布了 `backlight-control` | **0** | **1** | 只有 [4]=1 且 `k60_backlight_control=1` 时才会是 1 |

## 三种启动配置的预期

| 配置 | stats[0] | request[4] | request[5] | 日志 |
|---|---|---|---|---|
| 默认（不传参） | 3 | 0 | 0 | `K60 BACKLIGHT: conformance AppleARMBacklight=0 control=0` + `published level 2047 dbv 0xff control 0 (no AppleARMBacklight conformance)` |
| `k60_backlight_control=1` | 4 | 1 | 1 | 同上，但 `conformance …=1 control=1`；**brightness-4 就是这一行之后 backboardd 连崩 4 次**，所以默认关 |
| `k60_backlight=0` | 未初始化（0） | -1 | -1 | 服务完全不启动，屏幕停在 bring-up 的 0xff |

## 诚实说明：「回读」是什么

DCS 0x51（`set_display_brightness`）是单向命令，面板没有对应的读回命令；
K60 也没有独立背光 IC 可以读寄存器。所以：

- `stats[4]` 是**软件记录值**，等于「本服务最后一次成功写入的 DBV」；
- `stats[3]` 由它反算，不是独立测量；
- 真正的物理亮度只能由**屏幕肉眼可见的变化**证明（上机拍照/观察）。
  这条限制写在 `docs/research/display/BRIGHTNESS-PLAN.md` §5 与
  `docs/research/display/HANDOFF-20261114.md` 的判据里，避免把软件记录当成硬件回读。

```text
读法示例（USB 日志或 debugger）：
  K60 BACKLIGHT: conformance AppleARMBacklight=0 control=0
  K60 BACKLIGHT: published level 2047 dbv 0xff control 0 (no AppleARMBacklight conformance)
  -> stats[0]=3 stats[1]>0 stats[5]=0 stats[15]>0
```
