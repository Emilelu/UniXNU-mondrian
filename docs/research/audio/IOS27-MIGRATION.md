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
| `PongAudioAmp.c` | 1011 | `ml_io_map`、`PE_parse_boot_argn`、`printf`、`clock` | 功放探针、播放档与扬声器开关（`spk_switch_drive()`）；这些接口在 iOS 27 仍在，只是调用点要重接 |
| `PongAudioRegs.h` | 162 | 同上 | 寄存器地址与位域常量 |

搬的时候只换接线（谁在什么时候调用 `pong_audio_amp_probe()` / `pong_audio_amp_play()`），不动实现。

## 1b. 只为 host 测试随行

| 文件 | 行 | 说明 |
| --- | --- | --- |
| `PongAudioAfe.h` | 705 | AFE/TDM 参数表。本机固件里没有 AFE 服务（25 个 blob 对齐扫描零命中，v1/v2 封装都被 status=2 拒），所以**内核接线不许调用它**；但 `tests/test-pong-audio-geni-i2c.c:30` include 了它、979 个用例覆盖它的编码器，测试搬过去就必须带上它 |

## 3. 不搬

| 对象 | 为什么不搬 |
| --- | --- |
| `patches/xnu/0504-k60-audio-pong-audio.patch` | AudioReach 图 + GPR 编解码 + 端点选择，绑 iOS 16 树的文件位置与 `bsd/conf` 接线 |
| `patches/audio/0003-k60-audio-afe-selftest.patch` | 自检/探针脚本，依赖 0504 的结构 |
| `firmware/adsp`（adsp.b00..b25） | 固件 blob，按目标版本另配 |
| `PongAudio.driver` HAL bundle | HAL 层冻结，按 sheng 在 27 重接 |

AFE/TDM 参数表不进内核接线：它只按 §1b 随 host 测试走。

## 4. 迁移步骤与判据

1. 先在本仓跑 `python3 scripts/check-audio-sources.py`：它用真实补丁链重建 `bsd/dev`，再和
   `drivers/PongAudio` 逐字节比对（2026-11-20 的漂移就是这样发现的：`PongAudioAmp.c` 的副本比
   0001 的产物少 27 行，正好缺 `spk_switch_drive()`，而其余门禁全绿）。期望
   `OK: drivers/PongAudio matches the patch chain`。
   再跑 `python3 scripts/check-audio-migration.py --compile`：它把第 1、2 节的清单
   和 `drivers/PongAudio` 的实际文件逐一对照（目录里出现未分类文件、清单里的文件缺失、
   冻结项混进可搬表都会报错），再用 `-I.` 把五个纯 C 单元逐个 `-Wall -Wextra -Werror`
   编一遍；同时核对表里每个文件的行数（表与磁盘对不上就报错，防止文档变陈旧）。
   期望 `OK: the migration list matches the driver directory`。
   再跑 `sh scripts/tests/portability/run.sh`：它用桩头文件把胶水文件 `PongAudioAmp.c` 编过，
   期望 `STUBS OK PongAudioAmp.c`（六个内核符号 + 三个类型的内核面）。
   这两条加上判据测试、功放 host 测试与（有 sheng 检出时的）audioreach 测试，可以用一条命令全跑：
   `sh scripts/check-audio27-preflight.sh` → 六行 `ok` 与 `PREFLIGHT OK`（2026-11-20 03:1x 实测
   979 cases / 182 checks 全过）。
2. 在 27 树里跑 `python3 scripts/check-audio-migration.py --copy <27树>/drivers/PongAudio`：
   它按同一份清单复制 §1/§1b/§2 的 21 个文件与 `tests/` 的两个文件（共 23 个），分类检查不通过时
   直接拒绝复制。本仓实测 `--copy` 到空树后，`tests/run-tests.sh` 在副本里仍是 `TESTS OK 979 cases`。
3. 跑 `drivers/PongAudio/tests/run-tests.sh`，期望 `TESTS OK 979 cases`。
4. 可选：等 power 线把 `drivers/PongPower/QcomGlink.c` 与 `K60AudioGlink.c` 迁到 27 树之后，
   再跑 `drivers/PongAudio/tests/run-glink-multislot-tests.sh`（期望 `TESTS OK 800 cases`）。
   这套件编的是 PongPower 的传输源，不随本清单走。
5. 在 27 树加一个编译单元与一个初始化调用点（不进 `patches/xnu/0504`）；接哪个点、还缺什么
   依赖，见 [IOS27-WIRING.md](IOS27-WIRING.md)。
6. 判据：`run-tests.sh` 与 `scripts/tests/test-judge-audio-capture.py` 全绿、内核编译 0 错、工作树不碰 main。

## 5. 现状

2026-11-20 02:03 在本仓实测：`run-tests.sh` = `TESTS OK 979 cases`，
`run-glink-multislot-tests.sh` = `TESTS OK 800 cases`（本轮修了 4 处 bz 遗留断言：
PRM 时钟 12.288 MHz → 3.072 MHz 两处、group/port bit width 32 → 16 两处）。

`run-glink-multislot-tests.sh` 不属于本清单：它编译 `drivers/PongPower/QcomGlink.c` 与
`K60AudioGlink.c`，那是 power 线的传输源，音频分支带上它就会跨线复制。所以 27 树里它要等
power 搬完之后才可跑；音频侧自己的门禁是 `run-tests.sh` 与 `scripts/tests/test-judge-audio-capture.py`。

同一时间做了可搬性的独立验证：把第 1 节的 18 个文件（5 个 .c 模块
—— `PongAudioGeniI2c` / `PongCodecLpi` / `PongCodecMacro` / `PongCodecProbe` / `PongCodecSwr`
——加 13 个头）拷进一个空目录，只给 `-I.`，用 `cc -std=gnu11 -Wall -Wextra -Werror -c`
逐个编译，五个单元全部 `OK`、零内核头、零警告 ⇒ 第 1 节的「纯 C」不是分类推断，是实测。
这条验证现在由 `scripts/check-audio-migration.py --compile` 复现。
搬之前还要有 `PONG` 机配置：胶水整体在 `#if defined(PONG)` 里，缺它会把音频静默编空
（细节与判读顺序见 [IOS27-WIRING.md](IOS27-WIRING.md) §1「第零道闸」）。
胶水文件另有 `scripts/tests/portability/run.sh`：桩头文件只声明 `ml_io_map`、`ml_io_map_wcomb`、
`printf`、`delay_for_interval`、`NSEC_PER_USEC`、`PE_parse_boot_argn` 与三个类型，
`PongAudioAmp.c` 在里面 `-Wall -Wextra -Werror` 编过（`STUBS OK`）。

## 6. 每一项在 27 上靠什么日志行证明

27 stage-0 只走到 `bsd_init`，音频结论不可能在那之前出现——**下表每一项的前置条件都是 F4
（内核走到 `bsd_init` 并开始跑 PongAudio 代码）**，没有 F4 就没有任何一条可判。有了 F4 之后，
每项用一行日志证伪或证实，仍然可以喂给 `scripts/judge-audio-capture.py`：

| 项 | 27 上的证明行 | 判读 |
| --- | --- | --- |
| GENI I2C 通路 | `PongAudio: amp0 id=0x2113 chip=AW88261` | id 在已知表即通，超时计数非零即断 |
| ACF 两半回放 | `PongAudio: amp replay done amp0=60 amp1=60 written=120 mismatched=0` | `mismatched=0` 且 dev_index 与地址配对（0x34→1、0x35→0） |
| 扬声器开关 | `PongAudio: amp spk switch gpio=52 on=1 … read=0x00000002` | 回读 0x2 才算拉高 |
| I2S 端点 / 位时钟 | `--playback` 判据 S2/S3/S4 + `ampN play status=0x0011` | S 全过、status 含 PLLS\|CLKS 才算拿到时钟 |
| PCM 周期 | `WRITE_DONE replies=` > 0 | 0 表示 DSP 没消费，与 16.x 上的八轮结论同形 |

这些行在 27 上第一次出现的位置由 ROUTE-A 的 stage 定义决定，本表只钉「用哪一行判」，
不假设它出现的时机。

