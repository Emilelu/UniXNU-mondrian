# iOS 27 迁移清单（audio 线）

Lead 2026-11-20 定：新 main 从 iOS 27 stage-0 起步、先打通 SpringBoard，期间任何线都不往 main 合代码。
audio 线只搬「与 OS 无关」的东西：

> 只搬内核侧纯 C 模块 + host 测试 + 判据文档；AFE/TDM 参数表、ADSP blob、`0504`、`0003` 都不搬。

## 1. 可搬（纯 C，无内核头，今天就有 host 测试）

| 文件 | 行 | 作用 | host 覆盖 |
| --- | --- | --- | --- |
| `PongAudioGeniI2c.c` / `.h` | 176 / 110 | GENI I2C 控制器（FIFO、状态机、总线恢复） | 是 |
| `PongCodecLpi.c` / `.h` | 78 / 62 | LPASS LPI 时钟/电源序列 | 是 |
| `PongCodecMacro.c` / `.h` | 88 / 71 | WSA/VA macro 寄存器计划 | 是 |
| `PongCodecProbe.c` / `.h` | 237 / 122 | codec 探测与身份判定 | 是 |
| `PongCodecSwr.c` / `.h` | 201 / 133 | SoundWire 帧/端口计划 | 是 |
| `PongAudioAcf.h` | 305 | AW88261 ACF 表装载 | 是（PONG_ACF_FILE 存在时逐字节比对） |
| `PongAudioAmpProfile.h` | 172 | 两颗功放的 ACF 表（0x34 / 0x35） | 是 |
| `PongAudioAmpReplay.h` | 150 | ACF 回放序列 | 是 |
| `PongAudioPlan.h` | 149 | 探针计划（寄存器写入顺序） | 是 |
| `PongAudioPlayback.h` | 130 | 播放档寄存器计划 | 是 |
| `PongAudioRing.h` | 200 | PCM 环与槽记账（纯结构 + 内联） | 是 |
| `PongAudioTlmm.h` | 125 | 焊盘 mux/drive/输出使能计算 | 是 |
| `PongCodecPlan.h` | 335 | codec 计划结构 | 是 |

这一组是硬件契约：GENI I2C 的 FIFO 语义、AW88261 的 ACF 寄存器、TLMM 的 mux 值都不随 iOS 版本变。

## 2. 需要胶水但可搬（内核 API，非版本契约）

| 文件 | 行 | 依赖 | 说明 |
| --- | --- | --- | --- |
| `PongAudioAmp.c` | 984 | `ml_io_map`、`PE_parse_boot_argn`、`printf`、`clock` | 功放探针与播放档；这些接口在 iOS 27 仍在，只是调用点要重接 |
| `PongAudioRegs.h` | 162 | 同上 | 寄存器地址与位域常量 |

搬的时候只换接线（谁在什么时候调用 `pong_audio_amp_probe()` / `pong_audio_amp_play()`），不动实现。

## 3. 不搬

| 对象 | 为什么不搬 |
| --- | --- |
| `PongAudioAfe.h`（705 行） | AFE/TDM 参数表：本机固件里没有 AFE 服务（25 个 blob 对齐扫描零命中），v1/v2 封装都被 status=2 拒 |
| `patches/xnu/0504-k60-audio-pong-audio.patch` | AudioReach 图 + GPR 编解码 + 端点选择，绑 iOS 16 树的文件位置与 `bsd/conf` 接线 |
| `patches/audio/0003-k60-audio-afe-selftest.patch` | 自检/探针脚本，依赖 0504 的结构 |
| `firmware/adsp`（adsp.b00..b25） | 固件 blob，按目标版本另配 |
| `PongAudio.driver` HAL bundle | HAL 层冻结，按 sheng 在 27 重接 |

## 4. 迁移步骤与判据

1. 在 27 树新建 `drivers/PongAudio`，只拷第 1、2 节的 21 个文件。
2. 跑 `drivers/PongAudio/tests/run-tests.sh`，期望 `TESTS OK 979 cases`。
3. 跑 `drivers/PongAudio/tests/run-glink-multislot-tests.sh`，期望 `TESTS OK 800 cases`。
4. 在 27 树加一个编译单元与一个初始化调用点（不进 `patches/xnu/0504`）。
5. 判据：两套 host 测试全绿、内核编译 0 错、工作树不碰 main。

## 5. 现状

2026-11-20 02:03 在本仓实测：`run-tests.sh` = `TESTS OK 979 cases`，
`run-glink-multislot-tests.sh` = `TESTS OK 800 cases`（本轮修了 4 处 bz 遗留断言：
PRM 时钟 12.288 MHz → 3.072 MHz 两处、group/port bit width 32 → 16 两处）。

同一时间做了可搬性的独立验证：把 `drivers/PongAudio` 里 21 个头和 5 个纯 C 模块
（`PongAudioGeniI2c` / `PongCodecLpi` / `PongCodecMacro` / `PongCodecProbe` / `PongCodecSwr`）
拷进一个空目录，只给 `-I.`，用 `cc -std=gnu11 -Wall -Wextra -Werror -c` 逐个编译，
五个全部 `OK`、零内核头、零警告 ⇒ 第 1 节的「纯 C」不是分类推断，是实测。
