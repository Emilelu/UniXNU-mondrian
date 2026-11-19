# iOS 27 接线清单（音频）

这份文件回答「文件搬过去之后，27 树还要补什么才能编译、能跑」。
可搬清单本身在 [IOS27-MIGRATION.md](IOS27-MIGRATION.md)，判据行在它 §6；这里只写接线。

## 1. 编译单元与依赖

`drivers/PongAudio` 里只有五个纯 C 单元加 `PongAudioAmp.c` 会进内核编译，它们对外的全部依赖是：

| 符号 | 用途 | 27 树上谁提供 |
| --- | --- | --- |
| `ml_io_map` / `ml_io_map_wcomb` | 把寄存器窗口映射进内核 | XNU 本体，无版本契约 |
| `PE_parse_boot_argn` | `pong_audio=1` 之类的开关 | XNU 本体 |
| `wait_us` / `printf` | 功放 SYSST 轮询与日志 | XNU 本体 |
| `k60_pmic_glink_send_audio` | 走 PMIC GLINK 的 adsp_apps 通道 | `drivers/PongPower`（`QcomGlink.c` + `K60AudioGlink.c`），power 线 |

⇒ 功放这一半（GENI I2C、ACF 回放、开关、SYSST）**不依赖 GLINK**；`PongAudioAmp.c` 可以单独编译、
单独在 27 上跑出 `amp0 id=0x2113`。只有 AudioReach 图那半边需要 GLINK，而它不在本清单里。

## 2. 调用点（16 树在哪里调，27 树照这个位置重接）

| 函数 | 16 树的调用点 | 时机 |
| --- | --- | --- |
| `pong_audio_amp_probe()` | `patches/audio/0001-k60-audio-amp-probe.patch:3515`（`bsd_init.c`） | 内核初始化一次，不需 DSP |
| `pong_audio_amp_play()` | `patches/audio/0003-k60-audio-afe-selftest.patch:717` | 播放图 START 之后、第一个 PCM 周期之前 |
| `pong_audio_amp_stop()` | 同文件停机路径 | 停图之后 |
| `pong_audio_tdm_pads()` | `patches/audio/0003`:1497（`pong_audio_start()`） | 27 树若没有 pinctrl 框架，仍在初始化里手动 mux |

`pong_audio_amp_play()` 内部已经驱动扬声器开关（gpio52，回读 `0x2` 才算拉高），所以 27 树不需要
单独的开关调用点。

## 3. 仍然悬着的一件事：PCM 缓冲归属

16.x 上八轮实验的结论（`AMPS.md` 的 bk…cc 段）：SCM `MEM_PROT_ASSIGN` 会把 HLOS 移出、逐周期过户
会让整机复位、无属主 carveout 能活满 300 s 但 DSP 一条 WRITE_DONE 都不回。也就是「DSP 能不能读到
那 64 KiB」在 16.x 上没解决。

27 上这一项的判据仍然只有一行：`WRITE_DONE replies=` 是否大于 0。进 27 之前先确认两件事：

1. UEFI 是否还往 `/chosen` 发布 `pong-audio-dma`（64 KiB）；没有这块区就先补 loader 侧。
2. 27 树是否保留了 SMMU 旁路能力（`stealUfsSmmu`/stream 0x1801 路由）；没有就先只做功放半边。

## 4. 进入顺序

1. 功放探针：`amp0 id=0x2113` —— 证明 GENI I2C 通。
2. ACF 回放：`amp replay done … mismatched=0` —— 证明两颗芯片的寄存器表对得上。
3. 开关与 SYSST：`read=0x00000002`、`ampN play status=0x0011` —— 证明位时钟真的到了功放。
4. 端点与 PCM：`--playback` 判据 S2/S3/S4 + `WRITE_DONE replies>0`。

前两步不依赖 DSP，也不依赖 HAL，是 27 stage-0 一旦到 `bsd_init` 就能争取的成果。

## 5. 不做的事

- 不搬 `PongAudioAfe.h` 进内核接线（本机固件无 AFE 服务，v1/v2 都被 `status=2` 拒）；它只随 host 测试走。
- 不搬 `patches/xnu/0504`、`patches/audio/0003`：绑 16 树的文件位置与 `bsd/conf`。
- HAL bundle 冻结，用户态按 sheng 在 27 重接。
