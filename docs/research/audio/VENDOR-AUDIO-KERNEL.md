# 厂商音频内核里的真值：PRM 时钟、TDM 结构体、slot 判定

状态：**2026-11-17 采信**。素材是 LineageOS 的厂商音频内核
（`/mnt/e/k60-work/vendor-src/kernel-sm8450-modules/qcom/opensource/audio-kernel`，
 分支 `lineage-22.2`，与 K60 同 SoC 家族的 waipio/cape 平台）。只读事实参考：寄存器、
结构体布局与常量是硬件事实，代码本身不复制进本仓库。

本文回答三个问题：**包长什么样**、**时钟怎么投**、**一颗 24 位立体声帧有几个 slot**。
三项都进了 `AUDIO-CLOSURE.toml`，对应的宿主断言在
`drivers/PongAudio/tests/test-pong-audio-geni-i2c.c` 的 `afe_prm_cases()`。

## 1. 包结构：与我们的编码器逐字节一致

| 事实 | 出处 |
| --- | --- |
| `struct afe_port_cmd_set_param_v2 { struct apr_hdr; u16 port_id; u16 payload_size; struct mem_mapping_hdr mem_hdr; u8 param_data[0]; } __packed` | `include/dsp/apr_audio-v2.h:2029` |
| `AFE_PARAM_ID_TDM_CONFIG 0x0001029D` | `include/dsp/apr_audio-v2.h:3646` |
| `struct afe_param_id_tdm_cfg`：`u32 tdm_cfg_minor_version; u32 num_channels; u32 sample_rate; u32 bit_width; u16 data_format; u16 sync_mode; u16 sync_src; u16 nslots_per_frame; u16 ctrl_data_out_enable; u16 ctrl_invert_sync_pulse; u16 ctrl_sync_data_delay; u16 slot_width; u32 slot_mask;` = **36 B** | `include/dsp/apr_audio-v2.h:3670` |
| `AFE_MODULE_TDM 0x0001028A` / `AFE_PARAM_ID_PORT_SLOT_MAPPING_CONFIG 0x00010297` | `include/dsp/apr_audio-v2.h:3777,3782` |
| `struct afe_param_id_slot_mapping_cfg { u32 minor_version; u16 num_channel; u16 bitwidth; u32 data_align_type; u16 offset[8]; } __packed` = **28 B** | `include/dsp/apr_audio-v2.h:3802` |
| `struct afe_port_cmd_device_start` | `include/dsp/apr_audio-v2.h:5252` |

字段偏移与 `pong_afe_tdm()` / `pong_afe_slot_mapping()` 完全一致：0/4/8/12/16/18/20/22/24/26/28/30/32。
厂商头文件是第二份独立证据（此前只对过 mainline 与 phk110），`afe-packet-layout` 因此从
「两源一致」升为「三源一致」。

## 2. 时钟：走 PRM，不走 AFE clock-set

旧编码器发的 `AFE_MODULE_CLOCK_SET` / `AFE_PARAM_ID_CLOCK_SET`（0x1028F / 0x10290）是旧世代机制；
AudioReach 的机器驱动把位时钟当作 **LPASS 硬件资源**，向 PRM（Audio Process Manager 的资源管理器）请求。

### 2.1 常量

| 常量 | 值 | 出处 |
| --- | --- | --- |
| `PRM_MODULE_INSTANCE_ID` | `0x2` | `include/dsp/audio_prm.h:16` |
| `PRM_CMD_REQUEST_HW_RSC` | `0x0100100F` | `include/dsp/audio_prm.h:192` |
| `PRM_CMD_RELEASE_HW_RSC` | `0x01001010` | `include/dsp/audio_prm.h:194` |
| `PRM_CMD_RSP_REQUEST_HW_RSC` / `RSP_RELEASE_HW_RSC` | `0x02001002` / `0x02001003` | `include/dsp/audio_prm.h:196,198` |
| `PARAM_ID_RSC_AUDIO_HW_CLK` | `0x0800102C` | `include/dsp/audio_prm.h:202` |
| `apm_cmd_header_t` | `{u32 payload_address_lsw, payload_address_msw, mem_map_handle, payload_size}` = 16 B | `include/dsp/audio_prm.h:71` |
| `apm_module_param_data_t` | `{u32 module_instance_id, param_id, param_size, error_code}` = 16 B | `include/dsp/audio_prm.h:110` |
| `audio_hw_clk_cfg_req_param_t` | `{u32 num_clock_id}` = 4 B | `include/dsp/audio_prm.h:132` |
| `audio_hw_clk_cfg_t` | `{u32 clock_id, clock_freq, clock_attri, clock_root}` = 16 B | `include/dsp/audio_prm.h:136` |
| `CLOCK_ID_TER_TDM_IBIT` | `0x204` | `include/dsp/audio_prm.h:457` |
| `CLOCK_ATTRIBUTE_INVERT_COUPLE_NO` | `0x4` | `include/dsp/audio_prm.h:570` |
| `GPR_SVC_ASM` | `0x7` | `include/bindings/qcom,gpr.h:20` |

### 2.2 包的构造

`dsp/audio_prm.c:198-248` 的 `audio_prm_set_lpass_clk_cfg_req()`：

- GPR 头：`src_port = GPR_SVC_ASM(7)`、`dst_port = PRM_MODULE_INSTANCE_ID(2)`、
  `dst_domain = ADSP(2)`、`src_domain = APPS(3)`、`opcode = PRM_CMD_REQUEST_HW_RSC`；
- `payload_header.payload_size = sizeof(prm_cmd_request_rsc_t) - sizeof(apm_cmd_header_t)` = **36**；
- `module_payload_0.module_instance_id = 2`、`param_id = PARAM_ID_RSC_AUDIO_HW_CLK`、
  `param_size = 52 - 16 - 16` = **20**；
- `num_clock_id = 1`，然后一条 `{clock_id, clock_freq, clock_attri, clock_root}`。

整包 = 24 + 16 + 16 + 4 + 16 = **76 字节**，编码为
`pong_afe_prm_clock_request()`（`drivers/PongAudio/PongAudioAfe.h`）。

### 2.3 频率

`asoc/msm_common.c`：

- `:46` `TDM_SLOT_WIDTH_BITS 32`；
- `:383` `slot_width = TDM_SLOT_WIDTH_BITS`；
- `:407` `slots = pdata->tdm_max_slots`；
- `:415` `intf_clk_cfg.clk_freq_in_hz = rate * slot_width * slots`；
- `:416-417` `clk_attri = CLOCK_ATTRIBUTE_INVERT_COUPLE_NO`；
- `:685` 解析 `qcom,tdm-max-slots`；`:721-733` 解析 `qcom,tdm-clk-attribute`，但 **TDM 分支不用它**
  （`:460` 只有 MI2S 用 `mi2s_clk_attribute`）。

本板 live FDT `:23650` `qcom,tdm-max-slots = <0x08>` → 48000 × 32 × 8 = **12,288,000 Hz**。
DT 的 `qcom,msm-cpudai-tdm-clk-rate = <0x177000>`（1.536 MHz）**不被 waipio 机型驱动读取**，
是模板默认值；六个 TDM 节点全是这个数。旧文档据此推「1 slot」是错的。

## 3. slot 判定：2 slots × 32 bit，24-bit 样本

| 事实 | 出处 |
| --- | --- |
| `aw882xx_set_fmt()` 只接受 `SND_SOC_DAIFMT_I2S` 且必须 `SND_SOC_DAIFMT_CBS_CFS`（slave），其余 `-EINVAL` | `asoc/codecs/aw882xx/src/aw882xx.c:303-330` |
| 两颗功放：`aw882xx@34 sound-channel=0`、`aw882xx@35 sound-channel=1` | live FDT `:13325,13338` |
| HAL 要 2 通道、48000、24 bit、`PAL_AUDIO_FMT_PCM_S24_LE` | `resourcemanager_waipio_mtp.xml:459-470` |

两颗 PA 各取 I2S 帧的一半 → `nslots_per_frame = 2`、`slot_width = 32`、`bit_width = 24`、
`slot_mask = 0x3`；总线仍按 8 个 slot 的能力投 12.288 MHz。

## 4. 这对我们的代码意味着什么

1. `pong_afe_prm_clock_request()` 取代 AFE clock-set 包作为第一步；旧 `pong_afe_clock_set()` 保留
   只为把旧布局钉在测试里，speaker 路径不再发送它。
2. `pong_afe_step_ids()/pong_afe_step_opcode()` 的 Clock 步返回 (2, 0x0800102C) 与
   `PRM_CMD_REQUEST_HW_RSC`。
3. `afe_prm_cases()` 30 条断言钉住 76 字节的每一个字段：word0 = 0x4C60（version 0、header words 6、
   packet 76）、域名 2/3、端口 7/2、payload_size 36、param_size 20、clock 0x204、12.288 MHz、attribute 4。
   把任一常量改回旧值，`run-tests.sh` 立刻红。
4. `AUDIO-CLOSURE.toml` 的 `tdm-slot-count`、`afe-clock-hz`、`afe-clock-attribute` 三项关闭，
   新增 `prm-clock-packet` 并关闭；表格里不再有 `blocking`。

## 5. ACDB 说明

AudioReach 的 AGM 服务从标定库（ACDB tagged data）取 `nslots_per_frame` / `slot_width` / `sync_mode`
（`agm/service/src/graph_module.c:390-470`）。本机没有任何 `*.acdb`
（`find /mnt/e/k60-work -maxdepth 7 -iname '*.acdb'` 零命中），K60 的 `vendor/etc/acdbdata` 也不在
可读镜像里。所以我们不依赖 ACDB，按第 3 节的固定值自建端口配置；这也是 `acdb-not-required` 的边界。

## 6. 复现方式

```sh
# 结构体与常量
sed -n '2029p;3646p;3670p;3777,3802p' $VENDOR/include/dsp/apr_audio-v2.h
sed -n '16p;71p;110p;132,140p;192,202p;441,470p' $VENDOR/include/dsp/audio_prm.h
# 时钟公式
sed -n '383p;407,417p;685p;721,733p' $VENDOR/asoc/msm_common.c
# 功放格式限制
sed -n '303,330p' $VENDOR/asoc/codecs/aw882xx/src/aw882xx.c
# 本仓库的断言
sh drivers/PongAudio/tests/run-tests.sh    # TESTS OK 742 cases（带真实 ACF 760）
```
