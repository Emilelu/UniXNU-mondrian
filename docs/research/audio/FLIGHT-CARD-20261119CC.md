# 上机卡 2026-11-19cc —— I2S 端点 + 扬声器开关，看位时钟与通路是否同时到位

## 1. 目的

cb 把扬声器端点从 TDM_SINK 换成 I2S_SINK，但还有一处会在出声前挡住声音：
扬声器开关 gpio52 从来没被拉高。探针按 vendor 语义把它压在低电平
（`aw882xx.c:1711-1717` 用 `GPIOF_OUT_INIT_LOW` 申请，只有扬声器通路才拉高），
播放路径里却没有任何一处再把它拉起来——即使功放拿到位时钟并 unmute，
扬声器那端仍然是断的。

cc 在 `drivers/PongAudio/PongAudioAmp.c`（0001）里补上
`spk_switch_drive(bool on)`：读原 CFG、写 `pong_audio_spksw_cfg()` /
`pong_audio_spksw_io()`、回读 IO 校验，并打印
`PongAudio: amp spk switch gpio=52 on=… cfg=… io=… read=…`。
`pong_audio_amp_play()` 在至少一颗功放 unmute 后拉高，
`pong_audio_amp_stop()` 在停完两颗后拉低；探针的 `spk_switch_mute()` 不变。

本飞判两件事：位时钟是否出现（`amp play pll=1` / SYSST `0x0011`），
以及开关是否真的被拉高（`amp spk switch … on=1 … read=0x2`）。

## 2. 前提证据（上机前必须全部成立）

| 编号 | 证据 | 结果 |
| --- | --- | --- |
| P1 | 0504 的扬声器模块是 `AR_MOD_I2S_SINK 0x0700100A` | 是（0504 = 31,240 B / 1,007 行 / sha256 dd189168…） |
| P2 | 扬声器配置只发 PARAM_I2S_INTF 0x08001019 + HW_EP_MF + FRAME_SIZE_FACTOR | 是 |
| P3 | PRM 时钟用 `PONG_AUDIO_I2S_CLK_ID 0x104` @3.072 MHz、attribute 1 | 是（0003 = 55,174 B / 1,624 行 / sha256 7093ed04…） |
| P4 | 0001 新增 `spk_switch_drive()`，play 后拉高、stop 后拉低 | 是（0001 = 133,116 B / 3,521 行 / sha256 76154f07…） |
| P5 | 真实前像 apply 链（0503/0504/0505 → 0001 → 0003）通过，产物 2,559 行 | 是 |
| P6 | `check-patch-apply.py --all` 通过（313 补丁可解析），docs 门禁 0 | 是 |
| P7 | `verify-boot-image: OK` | 是 |

本卡判定的镜像：`audio-probe-20261119cc`，
`boot.img` sha256 `90051b6e68714e098792e4ec3527671df2aacc8c5b584d03a50ddfdb8ab9796c`。

## 3. 抓取

```
powershell -NoProfile -ExecutionPolicy Bypass -File E:/hackios/k60-audio-adsp/scripts/boot-and-capture.ps1 \
  -Image E:\k60-work\artifacts\audio-probe-20261119cc\boot.img \
  -OutDir E:\k60-work\evidence\audio-probe-cc\run1-<HHMM> -Seconds 300
```

只 `fastboot boot`，不 flash。证据目录需含 `console.log`、`capture.json`、`boot.json`。

## 4. 判据

判读只用工具，不看人眼：

```
python3 scripts/judge-audio-capture.py --playback <证据目录>
```

退出码 0 = 成功，1 = 跑到播放图但失败，2 = 播放图没跑。脚本只读 `console.log` 与
`capture.json`，下面每一条都对应报告里的一行，不需要任何人工目视。

**成功（S，全部满足才算这一飞可判读）**

- **S1** `capture.json` 的 `state` 为 `captured` 或 `captured-budget-complete`（脚本行 `S1 capture state=`）。
- **S2** 出现 `PongAudio: playback step 2 send bytes=408 opcode=0x01001000 token=…`，且该 token 收到
  `glink adsp_apps rx … opcode=0x02001005 status=0`（speaker open 被接受）。
- **S3** 出现 `PongAudio: playback step 10 send bytes=64 opcode=0x01001002 token=…`，且该 token 的
  rx `status=0`（speaker START 被接受）。
- **S4** 出现 `PongAudio: playback step 6 send bytes=76 opcode=0x0100100f token=…`，且该 token 收到
  `opcode=0x02001002 status=0`（PRM 时钟票被接受）。**clock id 0x104 不在日志里**，它由镜像钉住（P3），
  本卡不把它当运行时判据。
- **S5** 出现 `PongAudio: amp spk switch gpio=52 on=1 cfg=… io=… read=0x00000002`（开关真的拉高）。
- **S6** 记录型、不 gate：`PongAudio: amp0/1 play pll=… status=0x… faults=… tries=…`。
  `0x0011`（PLLS|CLKS）= 位时钟到了功放；`0x0020` = NOCLKS；`0x0000` = 时钟位全无。
  同一份报告还给出 `WRITE_DONE replies=`（`opcode=0x05001004` 的条数，0 表示 DSP 没消费过一个周期）。

**失败（F，任一命中即判 FAIL）**

- **F1** 日志出现 `K60KEXC` / `K60PANICFMT` / `K60PANICARGS` / `panic(cpu`，或 `capture.json` 的
  `panicMarker` 非空（`K60PANIC: ring kept` 只是保留环标记，不算 panic）。
- **F2** `console.log` < 500 行或零字节（启动没到播放图）。
- **F3** step 2 或 step 10 的 rx `status≠0`（I2S_SINK 被拒）。
- **F4** step 6 的 PRM `status≠0`（0x104 不被接受）。
- **F5** 出现 `glink adsp_apps down`（ADSP 掉线，本轮证据无效，需重飞同镜像）。

## 5. 结果登记

criteria-sha256: 88c086494db35348d8d0179c78c798ac52993ac2cee74799b847822600ee71f1

（上机后填写：镜像名、boot.img sha256、证据目录、S1–S6 与 F1–F5 的实测值、amp 的 SYSST、判决。）
