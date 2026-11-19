# 上机卡 2026-11-19cb —— 把扬声器端点换成 I2S_SINK，看位时钟是否出现

## 1. 目的

这一轮把调查推进到 ADSP 固件本身，结论是 legacy AFE 在本固件上没有服务端，
而我们一直在用的扬声器模块只是个注册桩：

- 对 25 个 adsp blob 做 4 字节对齐的 u32 扫描，`AFE_SVC_CMD_SET_PARAM_V2 0x000100fc`、
  `AFE_PORT_CMD_SET_PARAM_V2 0x000100ef`、`AFE_PORT_CMD_SET_PARAM_V3 0x000100fa`、
  `AFE_PORT_CMD_DEVICE_START 0x000100e5`、`AFE_SVC_CMD_SET_PARAM 0x000100f3`、
  `AFE_PARAM_ID_GROUP_DEVICE_TDM_CONFIG 0x0001029e`、`AFE_MODULE_TDM 0x0001028a`、
  `AFE_PARAM_ID_TDM_CONFIG 0x0001029d`、`AFE_PARAM_ID_CLOCK_SET 0x00010290` 全部零命中，
  只有 `APM_GET_SPF_STATE 0x01001021` 出现一次。
- 模块表记录是 `u32 n, u32 module_id, u32 p1, u32 p2`（p1/p2 是 0xb0000000 基址的虚拟地址），
  `0x0700100E` 只有 8 字节（p1=0xb062c7b4 p2=0xb062c7bc），而 `0x0700100A` I2S_SINK 有 472 字节实现。
- 功放自己要求的是 I2S：AW88261 ACF 的 `0x0006 = 0x34e8` 解出 I2SSR=8（48 kHz）、
  I2SBCK=2（64FS）、I2SFS=3（32-bit 帧）、I2SMD=0（Philips I2S）。

所以 cb 把扬声器图从 TDM_SINK 换成 **I2S_SINK 0x0700100A**，配置改发
**PARAM_I2S_INTF 0x08001019**（LPAIF 0 / TERTIARY 2 / SD1 2 / WS internal 1），
PRM 时钟改成 **clock_id 0x104 TER_MI2S_IBIT @3.072 MHz、attribute 1 COUPLE_NO**。

本飞只判一件事：换端点之后，TDM/I2S 端口是否真的出位时钟，
也就是功放的 `SYSST` 是否出现 PLLS|CLKS（`0x0011`）并从 mute 退出。

## 2. 前提证据（上机前必须全部成立）

| 编号 | 证据 | 结果 |
| --- | --- | --- |
| P1 | 0504 的扬声器模块是 `AR_MOD_I2S_SINK 0x0700100A` | 是（0504 = 31,240 B / 1,007 行 / sha256 dd189168…） |
| P2 | 扬声器配置只发 PARAM_I2S_INTF 0x08001019 + HW_EP_MF + FRAME_SIZE_FACTOR | 是 |
| P3 | PRM 时钟用 `PONG_AUDIO_I2S_CLK_ID 0x104` @3.072 MHz、attribute 1 | 是（0003 = 55,174 B / 1,624 行 / sha256 7093ed04…） |
| P4 | 真实前像 apply 链（0503/0504/0505/0001 → 0003）通过，产物 2,559 行 | 是 |
| P5 | `check-patch-apply.py --all` 通过（313 补丁可解析） | 是 |
| P6 | 门禁 docs / eight / patches 全 0 | 是 |
| P7 | `verify-boot-image: OK` | 待填（构建中） |

本卡判定的镜像：`audio-probe-20261119cb`，
`boot.img` sha256 待填（构建完成后写入）。

## 3. 抓取

```
powershell -NoProfile -ExecutionPolicy Bypass -File E:/hackios/k60-audio-adsp/scripts/boot-and-capture.ps1 \
  -Image E:\k60-work\artifacts\audio-probe-20261119cb\boot.img \
  -OutDir E:\k60-work\evidence\audio-probe-cb\run1-<HHMM> -Seconds 300
```

只 `fastboot boot`，不 flash。证据目录需含 `console.log`、`capture.json`、`boot.json`。

## 4. 判据

**成功（S，全部满足才算这一飞可判读）**

- **S1** `capture.json` 的 `state` 为 `captured` 或 `captured-budget-complete`，且 `console.log` ≥ 500 行。
- **S2** 出现 `PongAudio: playback step 2`（speaker open，408 B）且其 rx `status=0`。
- **S3** 出现 `PongAudio: playback step 3`（speaker SET_CFG）且其 rx `status=0`。
- **S4** 出现 `PongAudio: playback step 10`（speaker START）且其 rx `status=0`。
- **S5** 出现 PRM 时钟票（`clock` 步）且 rx `status=0`，并记下请求里的 clock id（应为 `0x104`）。
- **S6** 记下 `amp0/1 play` 行的 `status=` 值：`0x0011`（PLLS|CLKS）或 `unmuted` 出现即扬声器拿到了位时钟；
  `0x0000` 仍无时钟；`0x0020` 表示 NOCLKS 回来了。

**失败（F，任一命中即判 FAIL，并在 §5 记下命中的是哪一条）**

- **F1** 出现 panic、`K60KEXC`、或抓取被复位中断（`panicMarker` 非空 / 设备中途掉线）。
- **F2** `console.log` < 500 行或零字节（启动没到播放图）。
- **F3** speaker open / SET_CFG / START 任一步 rx `status≠0`（I2S_SINK 被拒）。
- **F4** PRM 时钟票 rx `status≠0`（0x104 不被接受）。
- **F5** 出现 `glink adsp_apps down`（ADSP 掉线，本轮证据无效，需重飞同镜像）。

## 5. 结果登记

criteria-sha256: 待填

（上机后填写：镜像名、boot.img sha256、证据目录、S1–S6 与 F1–F5 的实测值、amp 的 SYSST、判决。）
