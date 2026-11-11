# K60 触摸：设备树与 regulator 权威证据（2026-11-11 从 Android 实机读取）

> 方法：`fastboot reboot` 回 Android → `adb shell` 读 `/proc/device-tree` 与 `/sys/class/regulator`
> 意义：这是**唯一权威来源**。任何关于引脚/供电/面板尺寸的争论以本文档为准。

## 1. 触摸节点完整属性（`/proc/device-tree/soc/spi@990000/xiaomi_touch@0/`）

| 属性 | 原始 hex | 解析 |
|---|---|---|
| `compatible` | `78 69 61 6f 6d 69 2c 6d 31 31 61 2d 73 70 69 00` | **`xiaomi,m11a-spi`** |
| `goodix,avdd-gpio` | `00 00 00 3c 00 00 00 47 00 00 00 00` | phandle=0x3c, **GPIO 71**, flags=0 |
| `goodix,reset-gpio` | `00 00 00 3c 00 00 00 14 00 00 00 00` | phandle=0x3c, **GPIO 20**, flags=0 |
| `goodix,irq-gpio` | `00 00 00 3c 00 00 00 15 00 00 20 08` | phandle=0x3c, **GPIO 21**, flags=0x2008 |
| `goodix,irq-flags` | `00 00 00 02` | 2 = IRQF_TRIGGER_FALLING |
| `goodix,panel-max-x` | `00 00 38 40` | **14400** = 1440 × 10 |
| `goodix,panel-max-y` | `00 00 7d 00` | **32000** = 3200 × 10 |
| `goodix,panel-max-w` | `00 00 00 ff` | 255 |
| `goodix,panel-max-p` | `00 00 10 00` | 4096 |
| `goodix,firmware-name` | `goodix_firmware_m11a` | 对应本地 223,744 B 固件 |
| `goodix,config-name` | `goodix_cfg_group_m11a` | 对应本地 1627 B config |
| `goodix,iovdd-name` | `76 64 64 00` | **`"vdd"`**（节点上无对应 regulator 属性 → 常开） |
| `panel` | `00 00 06 a3 00 00 06 97` | 两个 phandle |

## 2. 结论：我们的引脚与面板参数全部正确

| 项 | DT 权威值 | 我们驱动 | 判定 |
|---|---|---|---|
| AVDD GPIO | 71 | 71 | ✅ 正确 |
| RESET GPIO | 20 | 20 | ✅ 正确 |
| IRQ GPIO | 21 | 21 | ✅ 正确 |
| panel-max-x/y | 14400 / 32000 | IC_INFO `+138/+140` 读出 `14400 / 32000` | ✅ **IC_INFO 走查 100% 正确** |

**第二行是决定性的**：DT 的 panel-max 与我们按 vendor 公式
（`offset = 2+16+10+4`，5 次 `offset += 1 + 2*info[offset]`，再读 `+138/+140`）
算出的值完全一致，证明 **`off=49` 正确、`touch_address = 0x10308` 是有效地址**。

## 3. Android regulator 快照（`/sys/class/regulator/`）

关键项（state / microvolts）：

```
27 pm8350c_l2   enabled  1800000   <- IOVDD 1.8V（我们写的就是它）
28 pm8350c_l3   disabled 2700000   <- 我们曾误当 AVDD 写入，Android 上本就是关的
35 pm8350c_l9   enabled  3200000   <- 3.2V，enabled（实际用途未知）
44 pm8350c_bob  enabled  3296000   <- boost 3.3V
8  pm8350_l3    disabled 904000
7  pm8350_l2    enabled  3075000
```

**`pm8350c_l3` 在 Android 上也是 disabled，所以写它没有意义（但也无害）。**
AVDD 由 GPIO71 控制的负载开关提供，PMIC 上找不到对应 LDO —— 与 DT 只给 gpio 不给 supply 一致。

## 4. Android 侧触摸完全正常（决定性对照）

```
/sys/bus/spi/devices/spi0.0/driver -> .../gtx8_spi
/sys/bus/spi/devices/spi0.0/modalias = spi:m11a-spi

/proc/bus/input/devices:
  N: Name="goodix_ts"
  S: Sysfs=/devices/virtual/input/input7
  H: Handlers=event7 cpufreq kgsl
  B: ABS=26d800000000003
```

**`gtx8_spi` 绑定成功，`goodix_ts` 输入设备存在。**

→ **硬件（电源、SPI、复位、中断、面板）全部没问题。**
→ 之前「AVDD 欠压」的假设**被推翻**：AVDD 若有问题，Android 触摸也不可能工作。
→ 问题确定在我们的驱动初始化序列。

## 5. 下一个假设：固件未加载

- 本地有 `goodix_firmware_m11a.bin`（**223,744 B**），与 DT 的 `firmware-name` 对应
- **我们从未加载过固件**
- 官方流程 `goodix_do_fw_update`（`goodix_brl_fwupdate.c:1285`）在版本无效时
  `UPDATE_MODE_FORCE`，走 `goodix_update_prepare`（reset + hold CPU + enable misctl clock）
  → `goodix_flash_firmware` → `goodix_update_finish`（reset）
- 我们读到的 `BERLIN 9916R 05.80.02.63` 可能来自芯片 ROM 而非运行中的固件
- **若固件在 RAM 中、掉电即失，每次冷启动都必须重新加载** —— Android 这么做了，我们没做

### 验证方法

1. 读芯片的 `fw_state_addr`（misc+16 = 0x20118），看固件状态字段
2. 若固件未运行，实现 `goodix_update_prepare` + `goodix_flash_firmware` 的等价流程
3. 注意 `goodix_update_prepare` 的 `HOLD_CPU_REG_W` 写入与 `misctl clock` 使能，
   以及 `goodix_update_finish` 必须复位

## 6. 对既有结论的修正（HR-30 登记）

| 原假设 | 本证据的反驳 |
|---|---|
| K60 面板是 1220×2712 | ❌ DT 明确 `panel-max-x=14400 / y=32000` → 面板 **1440×3200** |
| `0x10308` 不是报告地址（PHK110 subagent 的判断） | ❌ DT 面板尺寸与我们 IC_INFO 读数完全一致，证明走查正确，`0x10308` 有效 |
| AVDD 欠压导致 AFE 不工作 | ❌ Android 触摸正常工作，证明 AVDD 无问题 |
| `pm8350c_l3` 是 AVDD | ❌ Android 上它本就是 disabled；AVDD 走 GPIO71 负载开关 |

---

## 7. 芯片实际运行状态（Android sysfs，2026-11-11）

从 `/sys/devices/platform/goodix_ts.0/` 读取的驱动内部状态：

```
chip_info:
  rom_pid:BERLIN          ROM 是 BERLIN
  rom_vid:020004
  patch_pid:GEST          ★ 运行时固件是 GEST
  patch_vid:00010104
  sensorid:255
  config_id:640fdf7d      ★ 实际使用的 config ID
  config_version:46       ★ 实际 config 版本

driver_info:  DriverVersion:v1.2.2
esd_info:     state:disabled
irq_info:     irq:324  state:enabled  disable-depth:0  trigger-count:0
result:       result:success  spend_time:150ms
modalias:     platform:goodix_ts
```

### 与我们本地文件的核对（全部匹配）

| 项 | 芯片报告 | 本地文件 | 判定 |
|---|---|---|---|
| ROM pid | `BERLIN` | 固件 offset 8 = `BERLIN` | ✅ |
| ROM 版本 | — | 固件 offset 24 = `05 80 02 63` | ✅ 与我们读芯片得到的版本一致 |
| **config_id** | **`640fdf7d`** | config 载荷 offset 28（u32 LE）= **`0x640fdf7d`** | ✅ **完全匹配** |
| config 日期 | — | `F20230314`（cfg offset 32） | — |
| 固件长度 | — | 223,744 B | — |

**结论：我们手上的 config 与固件都是正确的那一份。config 下载也确认成功（ack=0x80）。**

### 新的未解点

1. **`patch_pid:GEST`** vs 我们读到的 `9916R`
   - 我们读的版本区（`GOODIX_FW_VERSION`）给出 ROM 身份 `BERLIN 9916R 05.80.02.63`
   - 芯片报告的实际运行固件 patch 名是 **`GEST`**（`patch_vid:00010104`）
   - 本地固件文件 offset 18164 处也含 `GEST` 字符串，说明该文件确实是 GEST 补丁
   - **即：版本区读到的是 ROM 信息，不是运行固件信息。我们从未读过 patch 区。**

2. **`irq_info: trigger-count:0`（Android 上也是 0）**
   - 说明 Android 的触摸**不依赖中断计数**或该计数不复位
   - 不能用「INT 恒为 1」作为独立故障判据

3. **所有数据区静态**（我们实测）
   - `0x10308` touch_data changed=0/12
   - `0x30084` frame_data changed=0/12
   - 只有 `0x10400` 变化（诊断计数器）

### 下一步候选（按优先级）

1. **读 patch 区而非 ROM 区**：官方 `goodix_brl_hw.c` 的 `brl_read_version`
   读的结构里同时含 ROM 与 patch 字段，我们只解了前半。按官方结构重新解析
   28 字节版本区，确认 patch_pid/patch_vid 是否与我们本地固件一致。
2. **对比 Android 的 `read_cfg` / `send_cfg` 行为**：
   `/sys/devices/platform/goodix_ts.0/read_cfg` 与 `send_cfg` 是驱动暴露的
   config 读写接口。可在 Android 上读一次真实运行的 config，与本地文件逐字节对比。
3. **确认是否需要真正的固件加载**：
   `result:success spend_time:150ms` 表明 Android 在启动时做过一次 150ms 的更新操作。
   若该操作是 config 而非固件，则固件由 ROM 自带，不需要加载。

---

## 8. 2026-11-11 01:31 实测：config 修正 + 坐标模式切换后的状态

**内核 f3c10bed / 镜像 970bc966 / usblog-20261111-013108**

### 已实现并验证通过的步骤

```
goodix: CFG-DL start, 1488 bytes in 64-byte chunks
goodix: CFG-DL wrote=1488/1488 bad=0 -> DATA-OK      config 1488B（修正偏移后）
goodix: CFG-WRITE ack=80 OK
goodix: CFG-EXIT ack=80 OK-config-applied
goodix: CFG-RESET assert reset (gpio20)
goodix: CFG-RESET re-handshake OK (rb=01)
goodix: COORD-MODE frame 00 00 05 90 00 95 00 00     cmd=0x90 data[0]=0x00
goodix: COORD-MODE ack=80 OK-coordinate-mode          切回坐标模式
POLL hb int=1 polls=3750 reports=0                    仍然无报告
```

### 本轮修正的两个真实 bug

1. **config 提取偏移错 2 字节**（1486→1488）
   `goodix_cfg_pkg_const_info` 实际 56 字节（我算成 58），
   提取起点应为 `bin[139]` 而非 `bin[141]`。
   证据：Android `read_cfg` 前 40 字节与 `bin[139:179]` 完全一致。
2. **缺少坐标模式切换命令**
   Berlin-D 用同一 `cmd=0x90` 靠 `data[0]` 区分模式：
   `0x81`=rawdata、`0x82`=diffdata、**`0x00`=坐标模式**。
   依据 `goodix_brl_hw.c brld_get_cap_data:1296-1360` 的 exit 段。
   **我们发过 0x81 读 rawdata，却从未发 0x00 切回来。**

### 当前明确的失败模式

**芯片对每一条命令都回 `ack=0x80`，但从不产生任何数据：**

| 步骤 | 结果 |
|---|---|
| 读版本（28 B） | ✅ `BERLIN 9916R 05.80.02.63 sensor 255` |
| 读 IC_INFO（193 B） | ✅ len=193 off=49，panel-max 14400/32000 与 DT 一致 |
| dev_confirm 写 8×0xAA | ✅ 读回一致（裸路径下已跳过，不影响） |
| config 三阶段 | ✅ 全部 ack=0x80，1488 B 读回校验通过 |
| 复位 + 重握手 | ✅ rb=01 |
| 坐标模式切换 | ✅ ack=0x80 |
| **读触摸报告 0x10308** | ❌ 恒定 `00 94 b7 56 4b b4 ce ba`，`event=0x00`、`touch_num=7`、校验 `sum=0x02a0 ≠ stored=0xbace` |
| **读帧数据 0x30084** | ❌ 静态 |
| **INT 脉冲** | 仅 3 次（心跳采样），触及面板时也几乎不脉冲 |

### 剩余最大假设：固件未加载

官方 `goodix_do_fw_update`（`goodix_brl_fwupdate.c:1285`）的完整流程：

```
goodix_update_prepare  (:934)
    goodix_fw_update_reset(5)              reset
    HOLD_CPU_REG_W = 1                     ← 我们从未做过
    读回 3 次校验 hold 成功
    使能 misctl clock                      ← 我们从未做过
goodix_flash_firmware                       ← 我们从未做过（223,744 B）
goodix_update_finish   (:920)
    goodix_fw_update_reset(100)            reset
    goodix_fw_version_compare
```

**我们读到的版本来自 ROM；运行固件（`patch_pid:GEST`）可能根本没被加载进芯片 RAM。**
Android 每次冷启动都会走这条流程（`result:success spend_time:150ms`）。

### 其他已排除

- **不是 AVDD**：Android 触摸正常工作（`goodix_ts` @ event7）
- **不是引脚**：DT 确认 AVDD=GPIO71 / RESET=20 / IRQ=21，与我们一致
- **不是地址**：DT panel-max 14400/32000 与我们 IC_INFO 读数一致
- **不是 config 内容**：`config_id:640fdf7d` 与我们完全匹配
- **不是轮询速度**：已从 8ms/10 次提高到 2ms/1 次（轮询数 1636→9375，5.7 倍）
- **不是 INT 竞态**：已改为在决定读取时捕获 INT 电平

### 下一步（唯一未验证的方向）

实现固件加载流程（`update_prepare` + `flash_firmware` + `update_finish`），
把本地 `goodix_firmware_m11a.bin`（223,744 B）写进芯片。
这是 Android 每次冷启动都做、而我们从未做的事。
