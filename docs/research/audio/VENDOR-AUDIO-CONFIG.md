# 厂商音频配置里的真值：扬声器走 TERT TDM

状态：**2026-11-17 采信**。取代 `TDMS.md` 里「扬声器走 PRI_TDM_RX_0」的旧结论（那是从 phk110
移植来的，phk110 不是 K60）。

## 1. 结论

K60 的扬声器后端是 **TERTIARY TDM RX**：

| 项 | 值 | 出处 |
| --- | --- | --- |
| HAL 后端名 | `TDM-LPAIF-RX-TERTIARY-VIRT-0` | `resourcemanager_waipio_mtp.xml:459-460` |
| AFE 端口 | **0x9020** | `q6afe.c:135,215`（0x9000 + 0x20）；live FDT `:20592` |
| AFE 组 | **0x9120** | live FDT `qcom,msm-cpudai-tdm-group-id`（tert-rx） |
| 通道 / 采样率 / 位宽 | 2 / 48000 / **24** | `resourcemanager_waipio_mtp.xml:461-465` |
| 采样格式 | `PAL_AUDIO_FMT_PCM_S24_LE` | 同上 `:470` |
| 保护 | `speaker_protection_enabled=0`、`ras_enabled=0` | 同上 `:466,486` |
| 引脚组 | `tert_tdm_pinctrl`（gpio121/123/122/124） | live FDT `:23666-23674`，由 sound 引用 |

## 2. 证据链

### 2.1 厂商 HAL 配置

`/mnt/e/k60-work/scratch/sensors-work/los-device-mondrian/audio/resourcemanager_waipio_mtp.xml`
（LOS 设备树里的厂商 HAL 配置；LOS 用原厂 vendor 分区，所以这份文件就是 K60 出厂配置）：

```xml
<out-device>
    <id>PAL_DEVICE_OUT_SPEAKER</id>
    <back_end_name>TDM-LPAIF-RX-TERTIARY-VIRT-0</back_end_name>
    <max_channels>2</max_channels>
    <channels>2</channels>
    <samplerate>48000</samplerate>
    <bit_width>24</bit_width>
    <snd_device_name>speaker</snd_device_name>
    <speaker_protection_enabled>0</speaker_protection_enabled>
    <supported_bit_format>PAL_AUDIO_FMT_PCM_S24_LE</supported_bit_format>
    <ras_enabled>0</ras_enabled>
```

同一份文件里 `PAL_DEVICE_OUT_HANDSET` 也用这个后端（1 通道、24 位）；`PAL_DEVICE_IN_EXT_EC_REF`
用 `TDM-LPAIF-TX-TERTIARY`，但 `ext_ec_ref_enabled=0`，本阶段不涉及发送方向。

### 2.2 混音路径不碰后端

`mixer_paths_waipio_mtp.xml:1987-1990` 的 `speaker` 路径只有两条写：

```xml
<path name="speaker">
    <ctl name="aw_dev_0_switch" value="Enable" />
    <ctl name="aw_dev_1_switch" value="Enable" />
</path>
```

整份文件里没有 `TDM-LPAIF-RX-...` 的 ctl —— 因为 AudioReach 的后端由 HAL 经 GPR 配置，不走
ALSA mixer。所以「mixer 里看不到 TDM」不代表没有 TDM，只代表它是 AudioReach 通路。

### 2.3 设备树：两套 TDM 都在，只有 tert 被引用

live FDT（`/mnt/e/k60-work/scratch/audio-work/live-fdt.dts`）：

- `:20500-20507` `qcom,msm-dai-q6-tdm-pri-rx-0`：dev-id `0x9000`；
- `:20588-20596` `qcom,msm-dai-q6-tdm-tert-rx-0`：dev-id `0x9020`，父节点 group-port-id `0x9020`、
  group-id `0x9120`；
- `:23630` sound 节点 `qcom,tert-mi2s-gpios = <0x5ec>`，而 `0x5ec` 就是 `:23666-23674` 的
  `tert_tdm_pinctrl`（引脚组 0x5cd/0x5ce/0x5cb/0x5cc = gpio121/123/122/124，`status = "ok"`）；
- PRI 的 pinctrl 组（`pri_aux_pcm` 0x279-0x288、`pri_tdm` 0x289-0x290 等）**refs 全 0**。

也就是说：DT 里定义了六个 TDM，但只有 tert 这一组被 sound 节点引用。

### 2.4 端口号表

`/home/emilelu/wifi-inputs/linux/sound/soc/qcom/qdsp6/q6afe.c:135-300`：

```
AFE_PORT_ID_TDM_PORT_RANGE_START = 0x9000
PRIMARY_TDM_RX    = 0x9000 + 0x00
SECONDARY_TDM_RX  = 0x9000 + 0x10
TERTIARY_TDM_RX   = 0x9000 + 0x20   -> 0x9020
QUATERNARY_TDM_RX = 0x9000 + 0x30
QUINARY_TDM_RX    = 0x9000 + 0x40
```

时钟 ID（`q6afe.h:104-107`）：`Q6AFE_LPASS_CLK_ID_TER_TDM_IBIT = 0x204`（PRI 是 0x200）。

## 3. 旧结论为什么错

`TDMS.md` 的 PRI 结论来源是 phk110 的 `hakios.sound.c:10-11,338-343`：那台机器的扬声器确实在
PRI_TDM_RX_0 / 组 0x9100。我们当时把「同系列功放（AW88261）」当成了「同一根 TDM」，没有回到
K60 自己的 HAL 配置去核对。K60 的 PA 是 AW88261，但挂在 **tert TDM** 上。

## 4. 已闭合：slot 数与位时钟（2026-11-17）

厂商音频内核给出了直接证据，两点都已关闭（详见 `VENDOR-AUDIO-KERNEL.md`）：

1. **每帧 2 个 slot**：两颗功放各取 I2S 帧的一半（live FDT `sound-channel=0/1`），aw882xx 只接受 `SND_SOC_DAIFMT_I2S` + slave（`aw882xx.c:303-330`），HAL 要 2 通道 S24_LE。
2. **位时钟 12.288 MHz**：waipio 机型驱动按 `rate × slot_width × qcom,tdm-max-slots` 计算（`msm_common.c:407-417`），本板 max-slots=8 → 48000×32×8；DT 的 `clk-rate=0x177000` 不被读取。时钟经 PRM 请求发出（clock id 0x204、attribute 4），不是 AFE clock-set 包。
