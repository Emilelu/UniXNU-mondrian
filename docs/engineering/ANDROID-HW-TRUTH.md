# Android 硬件真值表（2026-11-10 02:55 实测，root adb）

> 设备 auto-reset 回 Android（XNU k60_autoreset=300），root adb 实测。
> 这份数据用于补齐每个硬件的 ③（反编译/取证）与 ⑦（核验）依据。

## 触摸（重大修正）
| 项 | 真值 | 证据 |
|---|---|---|
| 设备树 compatible | **`xiaomi,m11a-spi`** | `/proc/device-tree/soc/spi@990000/touchscreen@0/compatible` |
| 驱动 | **`goodix_ts`（GTP 协议）** | `/sys/class/input/event7 -> goodix_ts` |
| xiaomi 虚拟设备 | `uinput-goodix` | `/sys/class/input/event1` |
| IOVDD | `pm8350c_l2` enabled 1.8V | `/sys/class/regulator/` |
| AVDD | **不是 pm8350c_l3（2.7V disabled）** | 同上 |
| 结论 | **我们 stage 8-15 用 Berlin-D(BRL) 协议，芯片是 GTP —— 语言不对，芯片当然不响应** | — |

**GTP 协议关键寄存器**：版本 `0x8140`（8B）、config 校验 `0x8047`、状态 `0x804E`。

## 显示
| 项 | 真值 |
|---|---|
| 分辨率/刷新 | **`1440x3200x60cmd` + `1440x3200x120cmd`（面板原生 120Hz！）** |
| 状态 | `connected` |
| 结论 | **之前"软件 120Hz only"的结论要更正：面板硬件支持 120Hz** |

## WiFi（qca6490 / WCN6855）
| 项 | 真值 |
|---|---|
| 驱动 | `qca6490` + `cnss2` + `wlan_firmware_service` |
| 工作状态 | ✅ **已连 5G**（`Connecting to Emilelu_5G rssi:-53 freq:5180`）|
| 固件目录 | `/vendor/firmware_mnt/image/qca6490/` |
| 主固件 | **`amss.bin` 5,470,128 B + `amss20.bin` 5,296,128 B** |
| 板数据 | **`Data.msc` 889,524 B + `Data20.msc` 916,071 B** |
| BT BDF | `bd_l*.elf` 系列（~60 KB each），设备用 **`bd_m11agf.elf` 60,000 B** |

## 蓝牙
| 项 | 真值 |
|---|---|
| 内核 | `qbt_handler` + `btpower` |
| 固件 | **`/vendor/firmware_mnt/image/qca6490/bd_m11agf.elf`（60,000 B）** ← B-4 取证答案 |

## 音频
| 项 | 真值 |
|---|---|
| codec | **`wcd938x_dlkm` + `wcd937x_dlkm`**（WCD938x 主，937x 兼容）|
| 功放 | `aw882xx_dlkm`（AW882xx）+ `cs35l41_dlkm`（CS35L41）|
| 数字麦 | `swr_dmic_dlkm` |
| ADSP | `adsp_loader_dlkm` + `lpass_cdc_*` |

## 电源/电池（重大修正）
| 项 | 真值 | 之前错误 |
|---|---|---|
| capacity | 100 | — |
| **temp** | **358（35.8°C）可读！** | ❌ "电池温度无通道"是错的 |
| status | Charging | — |
| current_now | 836 mA | — |
| voltage_now | 4,333 mV | — |
| 充电 IC | `qti_battery_charger_main_m81`（m81）| — |
| USB | USB_CDP online | — |

## 相机
| 项 | 真值 |
|---|---|
| 后主 | sensorInfo `[01, E0, 5B]`，fuseID `_aac00321...` |
| 后微距 | fuseID `sunn00321...` |
| 前主 | sensorInfo `[10, BA, 46]`，fuseID `_aac00321...` |
| 驱动 | `camera(O)` + `camcc_waipio` + `msm_eva`/`msm_cvp` |

## 传感器
| 项 | 真值 |
|---|---|
| 架构 | **`sensors_ssc`（SSC 传感器协处理器）** |
| HAL | `vendor.sensors.qti` + `vendor.sensors-hal-2-1-multihal` + `citsensor-hal-2-0` |

## 基带
| 项 | 真值 |
|---|---|
| 通道 | `mhi_dev_netdev` + `ipa` + `rmnet_*` + `qcom_esoc` |
| 状态 | ✅ 工作（模块全部加载）|

## NFC
| 项 | 真值 |
|---|---|
| 驱动 | `nfc_i2c`（I2C NFC）|

## 关键固件清单（取证完成）
| 固件 | 路径 | 大小 |
|---|---|---|
| WiFi amss.bin | /vendor/firmware_mnt/image/qca6490/amss.bin | 5,470,128 |
| WiFi amss20.bin | 同上 amss20.bin | 5,296,128 |
| WiFi Data.msc | 同上 Data.msc | 889,524 |
| WiFi Data20.msc | 同上 Data20.msc | 916,071 |
| BT BDF | 同上 bd_m11agf.elf | 60,000 |
