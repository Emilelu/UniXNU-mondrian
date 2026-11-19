# iOS 27 用户态重接（音频）

内核侧的可搬清单在 [IOS27-MIGRATION.md](IOS27-MIGRATION.md)，接线在 [IOS27-WIRING.md](IOS27-WIRING.md)。
这一份只写另一半：**用户态**。它不在本仓，也不该被复制到本仓——按 Lead 的口径，27 上照 sheng 最新代码重接，
HAL 注入冻结。本文只记录接口、注入点和可复核的基线。

## 1. 谁拥有哪一半

| 层 | 住在哪 | 27 上怎么处理 |
| --- | --- | --- |
| 功放 bring-up、PCM 提交、日志 | 本仓 `drivers/PongAudio` + 0001/0003 补丁 | 只搬纯 C 与 host 测试（见迁移清单），接线见 WIRING |
| IOKit 音频服务（`ShengAudio` 类） | **UniXNU-sheng** `package/AudioProbe.cpp`、`package/ShengAudioService.cpp` | 直接用 sheng 的最新代码，不复制 |
| AudioServerPlugIn bundle（`ShengAudio.driver`） | **UniXNU-sheng** `hal/ShengAudioPlugIn.c` | HAL 冻结：不重建，只把它的 CDHash 放进 trust cache |
| 服务与 plug-in 的 ABI | **UniXNU-sheng** `package/ShengAudioAbi.h` | 接口不动；它是内核侧唯一需要对齐的用户态契约 |

2026-11-20 03:0x 观察到的 sheng `main` 是 `a68ee4e`（"docs: record the keyboard cover device state"）。

## 2. ABI（`package/ShengAudioAbi.h`，88 行）

- 类名 `"ShengAudio"`，magic `0x53484155`（`'SHAU'`），`SHENG_AUDIO_VERSION 1`。
- 48 kHz；输出 2 声道、输入 1 声道；`SHENG_AUDIO_PERIOD_FRAMES 480`（10 ms）；
  `SHENG_AUDIO_RING_FRAMES 65536`（1.37 s，为 300 ms 的 lead 与音频服务器的迟到 IO 留空间）。
- 三块内存：`ShengAudioMemoryControl = 0` 控制页、`ShengAudioMemoryOutput = 1` 播放环、`ShengAudioMemoryInput = 2` 采集环；
  环里是 16 bit 小端交错样本。
- 选择器：`ShengAudioStartOutput = 0`、`StopOutput = 1`、`StartInput = 2`、`StopInput = 3`、
  `ShengAudioSetHostClock = 4`（把 CoreAudio 的 host clock 频率常量改成这块板的定时器频率）。
- 时间线（`ShengAudioControl`）：`ticks_per_frame_q32` 是 32.32 定点，`out_anchor_host` / `in_anchor_host` 在服务启动时
  写一次，样本时间 `t` 落在 `t % ring_frames` 帧；服务对播放超前 `lead_frames` 消费、对采集滞后 `lead_frames` 填充。
- 控制页第二半是诊断：`SHENG_AUDIO_DIAG_OFFSET 2048`（32 个 selector/where 槽、音量、`mix_peak`、`ahead_*`/`behind_*`、
  IO 优先级、host clock 结果）与 `SHENG_AUDIO_TRACE_OFFSET 2560`（128 条属性访问轨迹）。**27 上排查"没声音"时，这两半比统一日志好用**。

## 3. 注入路径（27 树已有）

`patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch`（`bsd/kern/kern_exec.c`）在原有三个 addon 槽之后加第四个：

    static const char audio_source[] = "/private/var/ngpu/audio",
                      audio_point[] = "/System/Library/Audio/Plug-Ins/HAL";
    native_gpu_addon_mount(p, scratch, 0xa00, audio_source, sizeof(audio_source), audio_point, sizeof(audio_point),
        "/System/Library/Audio/Plug-Ins/HAL/BuiltinAudioPlugin.driver",
        "/System/Library/Audio/Plug-Ins/HAL/ShengAudio.driver/Info.plist",
        &native_gpu_addon4_stage, &native_gpu_addon4_status);

- 基准是系统自带的 `BuiltinAudioPlugin.driver`；可见点是我们的 `ShengAudio.driver/Info.plist`；挂载点是音频服务器会扫描的 HAL 目录。
- 16 系列的同一补丁在 `patches/xnu/zzyd-sheng-audio-addon-mount.patch`，两代只是 addon 槽编号不同（27 上多了 `addon4_stage/status`）。
- `hal/ShengAudioPlugIn.c`（703 行）实现 `AudioServerPlugIn`；`build-sheng-audio-hal.py` 用 macOS 的 CoreAudio 头 + iphoneos SDK
  编成 bundle 并写 `trust.json`（可执行文件 CDHash，给 owner trust cache）。脚本文档字符串已点名：**iPadOS 27 的音频服务器是
  `arm64e-apple-ios27.0`**，默认 target 仍是 `arm64-apple-ios17.0`。HAL 冻结的意思是：不重编这个 bundle，只确认 `trust.json`
  里那份 CDHash 在 27 的 trust cache 里。

## 4. 可复核的基线（都不需要设备）

| 命令 | 期望 | 说明 |
| --- | --- | --- |
| `cd UniXNU-sheng && python3 scripts/check-audioreach-host.py` | `PASS audioreach: 182 checks` | ASan/UBSan 编 `package/tests/audioreach_host.c`（162 行），核对图管理命令的包长、参数块布局与 DSP 参考客户端一致 |
| `cd k60-audio-ios27-carry && sh scripts/tests/portability/run.sh` | `STUBS OK PongAudioAmp.c` | 内核侧胶水对六个符号的内核面 |
| `python3 scripts/check-audio-migration.py --compile` | `OK: the migration list matches the driver directory` | 可搬清单与磁盘一致 |

2026-11-20 03:0x 三条都实测通过（182 checks / STUBS OK / OK）。

## 5. 接缝：内核侧给用户态什么

内核只出三样东西，用户态不读内核里的任何结构：

1. **功放与端点状态**：`PongAudio: amp probe done found=%u/2`、`amp%u play status=0x%04x`、`amp play done playing=%u/2`
   ——没有这些行，用户态拿到的是一块不会出声的图。
2. **PCM 提交**：`ShengAudio`/sheng 的服务按 `ShengAudioAbi.h` 的三块内存搬样本，内核侧只负责把提交路径接通
   （判据 `WRITE_DONE replies>0`）；这条仍是 27 前未解的一项（`/chosen pong-audio-dma` 与 SMMU stream `0x1801` 的归属）。
3. **日志**：内核 `printf` 与用户态的 `native_audio_service[8]`（`[0]` = 1 表示服务已发布）分开看，
   27 上先看内核有没有 `amp probe start`，再看用户态 `[0]` 是否为 1。

## 6. 27 上需要复核的三点

1. `kern_exec.c` 的 addon 槽在 27 的 `xnu-12377` 里还在（本轮已读到补丁），但 27 的基线是否已并入由 Lead 定——音频不碰 main。
2. `arm64e` 目标：HAL 冻结时 bundle 是 16 时代编的；若 27 的音频服务器拒绝加载，先看 CDHash/架构，再考虑重编。
3. `lead_frames` 与 300 ms 的余量是按 16.x 的 IO 周期定的；27 的音频服务器首轮跑起来后，用控制页的
   `ahead_min/max`、`behind_min/max`、`io_frames` 校正，不要先改内核。
