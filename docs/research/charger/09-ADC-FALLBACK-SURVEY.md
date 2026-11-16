# K60 电池遥测：不依赖 ADSP 的降级路径（PMIC ADC / SPMI 直读）证据调研

- date: 2026-11-17
- author: charger-agent（research subagent adc-fallback）
- 性质：只做证据收集。未改任何仓库，未编译，未 boot，未执行 fastboot。
- 证据基准：设备树真值 `E:/k60-work/scratch/power-work/assets/fdt-tree.json`（下称 FDT，行号为该文件行号）、端口源码与 patch（`E:/hackios/k60-charger`）、真机 console / Android dmesg（`E:/k60-work/evidence`）、Ubuntu 侧 mainline v6.6 源码（外部参考，只引用寄存器事实）。

## §1 问题与范围

今天的电池遥测全部落在 ADSP 上：`drivers/PongPower/K60PmicGlink.cpp:3-5` 写明本驱动打开 GLINK 通道 `PMIC_RTR_ADSP_APPS` 的前提是 "Main's PAS1 owner must provide the exclusive fresh authenticated lease"；拿不到 lease 时 `porting.toml:33` 的记录是 "Battery correctly reports no authenticated PAS1 handoff and does not publish a fabricated source."。也就是说零售机 ADSP bring-up 失败时，IOPMPowerSource 根本不会 registerService（`K60Battery.cpp:206` 只在首个通过校验的样本上注册）。

本次要回答三个问题：

1. K60 硬件上还有哪些电池遥测源**不经过 ADSP**；
2. 每个源的**前置条件**（SPMI 控制器 / arbiter / PMIC 归属 / 固件 / 现有驱动），端口今天是否已经拥有那条总线；
3. 最便宜的诚实降级方案能给出什么、缺什么证据、一次 boot 能证明什么。

范围边界：目标输出是「电压 + 充电状态」为及格线，电流/温度算加分；SOC（容量百分比）不在承诺范围——理由见 §3.3。本文不提出改代码方案，只给成本估算与验证清单。

## §2 候选表

| candidate | what it yields | prerequisite | evidence（file:line / FDT 节点路径） | port status |
| --- | --- | --- | --- | --- |
| A. SPMI VADC 直读 PM8350B 通道（vbat_sns / usb_in_v_div_16 / chg_temp / die_temp / ichg_fb） | 电池电压、VBUS 是否在（充电状态）、充电电流（未校准）、充电器/PMIC 温度 | AP EE0 拥有 arbiter 且 PPID 0x031（VADC）在 EE 映射里；能对 SID3 的 0x3100 区块做配置写 + EOC 轮询 | FDT:16681 vadc@3100、:16684 compatible "qcom,spmi-adc7"、:16804-16810 vbat_sns reg 0x38f；:16926 usb_in_v_div_16；:16894 ichg_fb；:16874 chg_temp；:16784 die_temp | 驱动 missing；**但 arbiter 读写基础设施已存在且真机验证**（见 §3.1） |
| B. PM8350B temp-alarm / BCL 中断 | PMIC die 温度、过温/过流阈值事件 | 同上 arbiter；中断需 PDC/SPMI 中断路由 | FDT:17795 qcom,temp-alarm@a00、:17845 bcl@4700（interrupt-names bcl-lvl0/1/2） | missing（drivers/ 下无 thermal 驱动，k60-thermal 等仓库只命中 docs/） |
| C. PM8350B 内置 fuel gauge 寄存器直读 | SOC/容量/库仑计数 | 需要 FG 的寄存器手册 + 初始化序列；FDT 里**没有** fg 节点 | FDT 全树无 fg/fuel/qg 节点（pm8350b@3 子节点见 §3.3）；Android 的 SOC 来自 "[ADSP] fg_update_status" | missing，且 mainline 无对应驱动 |
| D. UEFI/ABL 交接（QcomChargerDxe / ChargerExDxe / BATTERY.PROVISION） | 开机瞬间的电池电压/SOC | UEFI 源码里要有实现，并把值传给 XNU（DT /chosen 或 boot-arg） | `E:/hackios/uefi-mondrian/Binaries/9707f/...` 有 efi；源码树 grep Charger/Battery 为空；FDT /chosen 只有 hwid.* 与 swinfo.fingerprint | missing，且不可控（无源码） |
| E. USB VBUS（dwc3 / eusb2 repeater） | VBUS 在/不在 | 需要 USB 控制器驱动 + PHY；Android 侧 chg_type=CDP 也是 ADSP 报的 | FDT /soc/ssusb@a600000；dmesg-android-20261114.txt:41 `chg_type= CDP` | missing（端口没有 USB 驱动） |
| F. SMB139x 电荷泵 ADC（smb139x_*_ichg_smb 等） | 电荷泵电流/温度 | 需要电荷泵驱动 + ADSP 侧 supervisor；FDT 无 smb139x 节点，只有 VADC 通道名 | FDT:16946 `smb139x_1_ichg_smb`、:16956 `_iin_smb`、:16936 `_smb_temp` | rejected：比 A 更贵且依赖 ADSP |

结论先放这里：**A 是唯一同时满足「不依赖 ADSP」「端口已有前例」「能给出电压 + 充电状态」的候选**；C/D 不值得投入，B 只能算补充，E/F 比 A 贵。

## §3 详细证据

### 3.1 候选 A：SPMI VADC（ADC7）直读

（1）硬件存在，且通道定义在真机 FDT 里。

```
/soc/qcom,spmi@c42d000/qcom,pmk8350@0/vadc@3100
  compatible = "qcom,spmi-adc7";  reg = <0x3100>;
  interrupts = <0x00 0x31 0x00 0x01>;  interrupt-names = "eoc-int-en-set";
```
（FDT:16681-16687，phandle 0x55d 在 :16690）

电池相关通道（同一 vadc 节点下，均带 label / reg / qcom,pre-scaling）：

| label | reg | pre-scaling | 说明 |
| --- | --- | --- | --- |
| pm8350b_vbat_sns | 0x38f | <1 3> | 电池电压，1/3 分压（FDT:16804-16810） |
| pm8350b_usb_in_v_div_16 | 0x311 | <1 0x10> | USB 输入电压，1/16（FDT:16926） |
| pm8350b_ichg_fb | 0x3a1 | <0x3e8 0x4a821> | 充电电流反馈（FDT:16894） |
| pm8350b_chg_temp | 0x310 | <1 1> | 充电器温度（FDT:16874） |
| pm8350b_die_temp | 0x303 | — | PMIC die 温度（FDT:16784） |

关键推导：mainline `drivers/iio/adc/qcom-spmi-adc5.c` 的通道解析写的是
`/* virtual channel number = sid << 8 | channel number */`，ADC7 时
`sid = chan >> ADC_CHANNEL_OFFSET; chan = chan & ADC_CHANNEL_MASK;`。
所以 DT 的 `reg 0x38f` = **SID 3（PM8350B）+ channel 0x8f**，与 FDT:17787 `qcom,pm8350b@3 reg <0x03 0x00>` 对得上；实现时 `ADC_APP_SID(0x40)` 写 3、`CH_SEL_CTL(0x44)` 写 0x8f 即可，不需要额外绑定表。

（2）寄存器序列有公开依据（外部参考，GPL-2.0，仅引用寄存器事实）。
mainline 常量：STATUS1 0x8（CONV_FAULT bit7 / REQ_STS bit1 / **EOC bit0**）、DIG_PARAM 0x42（CAL_VAL bit6 / CAL_SEL 0x30 / DEC_RATIO 0xc）、FAST_AVG_CTL 0x43、CH_SEL_CTL 0x44、DELAY_CTL 0x45（HW_SETTLE 0xf）、EN_CTL1 0x46（ADC_EN bit7）、CONV_REQ 0x47（REQ bit7）、DATA0 0x50 / DATA1 0x51、ADC_APP_SID 0x40。
`adc7_configure()` 的顺序是：写 SID → 读 0x42..0x45 → 改 dig_param/avg/chl/settle → 写 CONV_REQ；`ADC7_CONV_TIMEOUT = 10ms`。
注意一条硬限制：同一文件里有注释 "No support for polling mode at present"，即 mainline 的 ADC7 走 EOC 中断、不轮询；ADC5 才有 `poll_eoc`。我们的降级路径没有中断路由，只能轮询 STATUS1 的 EOC——这是 §6 的未证点之一。
换算（`qcom-vadc-common.c`）：`voltage = code * 1875 * 1000 / full_scale_code_volt`，ADC7 PMIC 的 `full_scale_code_volt = 0x70e4`；再乘 `prescale->denominator`、除 `prescale->numerator`。vbat_sns 的 <1 3> 就是 3 倍还原，量程足够覆盖 4.4V。

（3）端口已经有能在零售 K60 上跑通的 SPMI arbiter 读写——这是整个降级方案最大的资产。
`patches/xnu/0308-k60-usblog-pong-capture-restart.patch` 里：

```c
#define K60_SPMI_CORE_PA     0x0C400000u   /* core  0x3000 */
#define K60_SPMI_CONFIG_PA   0x0C42D000u   /* cfg   0x4000 */
#define K60_SPMI_OBSERVER_PA 0x0C440000u
#define K60_SPMI_CHANNEL_PA  0x0C500000u
```
`k60_spmi_wait()` 轮询 `*(u32 *)(w + off + 8)` 的 bit0，返回 `(s & 15) == 1`；`k60_prime_restart()` 扫 `core + 0x2000 + 4n` 找 `((slave >> 8) & 0xfff) == 0x71`（PPID 0x071 = SDAM7100）并检查 `((slave >> 8) & 0xfff) == 0x71 && (cfgv & 7) == 0`（`cfgv = *(cfg + 4n)`，owner 字段为 0 即 APPS EE0），随后 map observer/channel 两个窗口，用 "读-改-写-回读校验" 写 PMIC SDAM cell。
`patches/xnu/0334-k60-panic-reset-fastboot.patch` 又把 map 与写拆成 `k60_restart_map_once()`，说明这套代码已经考虑过锁与重入。
真机证据：`E:/k60-work/evidence/audio-probe-j/run1/console.log:188` `K60AUTORESET: restart reason primed for fastboot`、:256 `K60 USBLOG: PMIC restart reason primed for fastboot`，随后设备确实进了 fastboot（capture-events.jsonl:4 的 reset-marker 是 "K60 USBLOG: restart reason published"）。
结论：**这不是纸面方案——零售 K60 上 XNU 已经用 SPMI 写过 PMIC 并生效**，只差把「写 SDAM」换成「读写 VADC」。

（4）arbiter 侧已有只读探针可复用。
`console.log:687-700`：`K60LDO rev=12 n0=768 n1=256 total=1024`、`i=745 p=0x2c1`、`rev=12 sid2=34 apid241=-1`。最后一项很重要：**PPID 0x241 在 AP EE 的映射里根本不存在**（与 `K60PmicRail.c:2-3` 的注释一致）。但 VADC 的 PPID 0x031 已经在三次独立 boot 的 PPID 扫描里出现并可读：`E:/k60-work/evidence/usblog-20261110-182146/console.log:667`、`usblog-20261110-183040/console.log:667`、`usblog-20261110-183911/console.log:667` 都是 `K60S21: ppid=0x031 apid=408 ok  00 00 00 00 08 44 00 00  08 44 00 00 08 44 00 00`；`usblog-20261110-185544/console.log:643` 的 `K60S23: ppid=0x031 apid=408 en=00(ok=0 en=0) range=03 vset=00` 也一致。即 **PPID 0x031 在 AP EE0 的 map 里存在（apid=408）且 12 字节读取返回 ok**。仍需证明的是「PPID 0x031 就是 vadc@3100 这个外设」，这只能靠 §5 第一步只读探针读 STATUS1/APP_SID/EN_CTL1 的合理值来确认。

（5）风险边界已知。`docs/research/touch/13-PMIC-SPMI-PATH.md:20-34` 记录 arbiter 四窗口与 RSC(0x17a00000) 完全独立、不违反 HR-01；同文档的风险结论是「写错通道/地址可能影响其它供电域，有整机死风险，建议先只读」。历史坑还有 `docs/engineering/PITFALLS.md` P-83（一次最多 8 字节）与 P-84（PPID 只有 12 位，0x4000+ 永不匹配）。

### 3.2 候选 B：temp-alarm 与 BCL

FDT 里 PM8350B 有 `qcom,temp-alarm@a00`（FDT:17795，`io-channels = <0x55d 0x303>`，即复用同一个 vadc 的 die_temp）与 `bcl@4700`（FDT:17845，compatible "qcom,bcl-v5"，interrupts 三条，interrupt-names "bcl-lvl0/1/2"），另有 `bcl-soc` status disabled。
它们给的是**阈值事件与 die 温度**，不是电池电压；而且中断要经 PDC/SPMI 中断路由，端口今天没有任何 SPMI 中断基础设施。所以 B 只能作为 A 的附加信号（过温保护），不能替代 A。

### 3.3 候选 C：fuel gauge——为什么 SOC 不在承诺范围

FDT 全树没有 fg / fuel / qg 节点：`qcom,pm8350b@3`（FDT:17787，reg <0x03 0x00>）的子节点只有 temp-alarm、pbs、pinctrl、bcl、bcl-soc(disabled)、hv-haptics、amoled、amoled-ecm（FDT:17793 起）。Android 的 SOC 明确来自 ADSP 侧：
`E:/k60-work/evidence/wifi-trial/dmesg-android-20261114.txt:2` 的 `[ADSP] fg_update_status:: ssoc:100, rsoc:99, raw_soc:9815, vbat:4392, ibat:0, temp:296 ...`。
同文件 :2140-2142 的模块表里，与电池相关的只有 `qti_battery_charger_main_m81`、`qcom_spmi_adc5`、`qcom_vadc_common`、`qti_adc_tm`、`qcom_spmi_temp_alarm` 等；没有任何 AP 侧 FG 驱动。
所以：**FG 的库仑计数与 SOC 属于 ADSP 固件（qcom_q6v5_pas 加载的 cape-adsp-pas，FDT:18514）**，ADSP 死了就没有 SOC。想要 SOC 只能自己在 AP 侧做库仑积分（需要持续采样电流 + 初始 SOC），这超出了「半天的降级方案」。诚实结论：降级方案给电压与充电状态，SOC 标 not available。

### 3.4 候选 D：UEFI/ABL 已经把电池值带进来了吗？

- 二进制在：`uefi-mondrian/Binaries/9707f/QcomPkg/Application/QcomChargerApp/QcomChargerApp.efi`、`Drivers/ChargerExDxe/ChargerExDxe.efi`、`Drivers/QcomChargerDxe/QcomChargerDxeLA.efi`、`RawFiles/QcomChargerCfg.cfg`。
- 源码不在：`E:/hackios/uefi-mondrian` 的 Platforms/Silicon/Conf/Common 里 grep Charger|Battery 为空——端口 UEFI 没有自建读取或传递逻辑。
- `RawFiles/BATTERY.PROVISION` 开头是 `[BATTERY_PROFILE]`、`Float_Voltage,4350`、`Nom_Batt_capacity,3600`、`Batt_id,107000`、`Therm_B,4250`、`Thermistor_Value,100000`，后面是 `Address, Address2, Offset, Data` 的寄存器初始化行——这是 **ABL 充电用的配置**，不是给 OS 的遥测接口。
- FDT `/chosen` 的 bootargs 里只有 hwid.* 与 `swinfo.fingerprint=mondrian:12/OS2.0.220.0.VMNCNXM`，没有 battery 属性。
结论：D 今天拿不到值；要做就得改 UEFI 并定义传参（DT 属性或 Apple boot-arg），成本高、验证链长，而且只能给开机瞬间的一次性快照。

### 3.5 候选 E：USB VBUS

端口没有 USB 驱动（FDT 有 `/soc/ssusb@a600000` "qcom,dwc-usb3-msm"、hsphy/ssphy、eusb2 repeater，但驱动目录里只有 PongPower 的电池与 PMIC 相关代码）。而且 Android 侧 `chg_type= CDP`（dmesg-android-20261114.txt:41）也是 ADSP 报的，说明「USB 在不在」在 K60 上默认也不是 AP 自己判的。即便写了 dwc3 驱动，也只得到 VBUS，仍得不到电压与电流——比 A 贵且信息更少。

### 3.6 候选 F：SMB139x

VADC 里有 `smb139x_1_ichg_smb / _iin_smb / _smb_temp`（FDT:16936-16970，另有 smb139x_2_*）通道名，但 FDT 没有对应的 smb139x 设备节点（全树 grep smb139x 只命中 vadc 通道 label），也没有对应驱动；电荷泵的使能与保护由 ADSP 侧 supervisor 管。排除。

### 3.7 端口今天有没有任何不依赖 ADSP 的电池相关值？

没有。`K60Battery.cpp` 的所有属性都来自 `K60PmicGlink` 的样本；`K60PmicGlink.cpp::discover()` 在拿不到 PAS1 lease 时直接失败，`registerService()` 不会被调用（`K60Battery.cpp:206`）。
唯一的旁证是 SPMI 本身可用（§3.1(3) 的 restart reason 写入成功），但那不是电池值。兄弟端口（Nothing Phone 2）同样如此：`pong-power/ShengBattmgr.c:235-245` 的 `external` 来自 pmic_glink 报的 `V(BmUsbVoltage) >= 4000000`，没有任何 PMIC 直读路径。

## §4 成本 / 风险

| 选项 | 新增/改动 | 规模（估） | 需要 boot 验证 | 主要风险 |
| --- | --- | --- | --- | --- |
| A. VADC 直读 | `drivers/PongPower/K60PmicAdc.c/.h`（arbiter 打开 + 通道表 + ADC7 配置/轮询/换算）+ `K60Battery.cpp` 接线（无 ADSP 时取 ADC 样本） | 新增约 400-550 行，改动约 120-180 行 | 是，1-2 次（先只读探针，再转换） | ① PPID 0x031 已实测存在（apid=408，三次 boot）；待证「它就是 vadc@3100」② ADC7 EOC 轮询未证 ③ ichg_fb 换算无公开公式 ④ 写 VADC 配置可能影响正在用 ADC 的其它 EE ⑤ 无校准 |
| B. temp-alarm/BCL | 独立小驱动 + 中断路由 | 150-250 行 | 是 | 端口无 SPMI 中断基础设施；收益只有 die 温度 |
| C. FG 直读 | 需要寄存器手册与初始化序列，FDT 无节点 | 未知，>800 行 | 是 | 无文档、无前例，SOC 仍需库仑积分 |
| D. UEFI 交接 | 改 uefi-mondrian + 定义传参 + XNU 侧解析 | 300-600 行（跨仓库） | 是，且要重刷 UEFI | 无源码（只有 efi），只能抄/逆；只给一次性快照 |
| E. USB VBUS | 新 USB 控制器 + PHY 驱动 | >1500 行 | 是 | 远超本次范围；信息量最少 |

补充风险（对所有 SPMI 选项通用）：
- **arbiter 归属**：FDT:16613-16615 写 `qcom,channel = <0x00>`、`qcom,ee = <0x00>`、`qcom,bus-id = <0x00>`，说明 AP 是 EE0；但 PMIC 上每个 PPID 的 owner 是按 PPID 单独配置的，0x241 已证明会缺（`console.log:700` `apid241=-1`）。
- **与 ADSP 抢 VADC**：如果 ADSP 其实活着（只是 PAS lease 没谈成），AP 直接配置 VADC 会与 ADSP 的 qti_adc_tm / battmgr 抢同一个 ADC。降级路径必须只在「ADSP 明确不可用」时启用，否则应保持只读。
- **写错地址的后果**：13-PMIC-SPMI-PATH.md 的风险结论是整机死；缓解办法是把写限定在 SID3 的 0x3100-0x3105 区块、每条写前先回读。
- **P-83/P-84**：单次读不超过 8 字节；PPID 是 12 位，别用 0x4000+ 的编码去匹配。

## §5 推荐 + 一次 boot 要证明什么

推荐：**A（SPMI VADC 直读），分两步走**。

- 第一步（只读探针，约 100-150 行，风险≈0）：复用 0308/0334 的 map 逻辑，扫 `core + 0x2000 + 4n` 找 **PPID 0x031** 的 apid，打印 apid / cfg owner / 该 PPID 的 map 项；然后只用 observer 读 `vadc + 0x08`(STATUS1)、`+0x40`(APP_SID)、`+0x46`(EN_CTL1) 三个字节。这一步不写任何 PMIC 寄存器。
- 第二步（转换，约 300-400 行）：写 SID/CH_SEL/DELAY，写 CONV_REQ，轮询 STATUS1.EOC（超时 10ms），读 DATA0/DATA1 并按 `code*1875*1000/0x70e4*3` 换算；先只做 vbat_sns 与 usb_in_v_div_16 两个通道，ichg_fb 与 chg_temp 作为 experimental 另开开关。
- 接线：`K60Battery.cpp` 增加一个「无 PAS1 lease 时走 PMIC ADC」的采样源，仍然走现有的字段/单位/极性校验后才 registerService；SOC 字段标记为 unknown 而不是编造（保持 `K60Battery.cpp:3-6` 的既有原则）。

一次 boot 必须证明（缺一条就不能算降级方案成立）：

1. **PPID 0x031 的映射复核**：历史 boot 已证明它在 AP EE0 的 map 里（apid=408，见 §3.1(4)）；本次 boot 打印 apid 与 map 原值，并确认 cfg owner 字节显示 EE0 拥有，同时用 STATUS1/APP_SID/EN_CTL1 的合理值证明「PPID 0x031 就是 vadc@3100」。
2. VADC 在 observer 侧可读且不是 0xEE 错误码：STATUS1 的 CONV_FAULT=0、ADC_EN 状态合理。
3. 写 CONV_REQ 后 **EOC 在 10ms 内到达**（这直接否证/证实 mainline 的 "no polling" 限制）。
4. vbat_sns 换算值与同机 Android 基准一致：`ANDROID-HW-TRUTH.md:72-75` 记录 35.8°C / 836 mA / 4,333 mV，允许 ±150 mV。
5. usb_in_v_div_16 在插 USB 时明显非零（约 5V/16 量级）、拔掉后接近 0——这是「充电状态」的唯一硬件依据。
6. 采样后系统存活 ≥60 秒，console 继续输出，无 PMIC fault、无 arbiter hang（对照 fastboot 前那次的 `K60LDO ... total=1024` dump 是否仍能打印）。
7. （加分）ichg_fb 的符号与量级：Android 报 +836 mA 时读出正值且随负载变化。

## §6 未解问题（明确 not proven）

- **PPID 0x031 是否在 AP EE0 映射**：**proven（2026-11-17 复核）**。三次独立 boot 的 `K60S21` 扫描都返回 `ppid=0x031 apid=408 ok ...`（路径见 §3.1(4)），另一份 `K60S23` 也一致。它证明 PPID 0x031 在 AP EE0 的 map 里且可读；不证明该 PPID 就是 vadc@3100（见下一条）。
- **ADC7 能否轮询 EOC**：not proven。mainline 注释明确写 "No support for polling mode at present"，本方案没有中断，只能轮询；若轮询拿不到 EOC，第一步仍能出 STATUS1，但取不到转换值。
- **ichg_fb 的换算公式**：not proven。mainline 的 `adc7_data_pmic` 没有 `full_scale_code_cur`（只有 adc5 有 0x2710/0x1800），`qcom-spmi-adc5.c` 全文没有 ichg 相关通道；DT 的 pre-scaling <0x3e8 0x4a821> 语义在 mainline 里找不到对应代码。电流只能给相对值或标 experimental。
- **校准**：not proven。mainline 的 SCALE_HW_CALIB_DEFAULT 用标称 1.875V 参考、不读 PMIC NVM 的校准字；没有校准的 vbat 误差估计 ±1-2%，是否足够让 IOPMPowerSource 的校验通过需实测。
- **chg_temp 的换算**：FDT 给 pre-scaling <1 1>，但 mainline 的 PM7 thermistor 用 SCALE_HW_CALIB_THERM_100K_PU_PM7 + qcom,pre-scaling，是否缺 rpull-up 参数 not proven。BATTERY.PROVISION 里的 Therm_B 4250 / Thermistor_Value 100000 只是 ABL 的 thermistor 参数。
- **ADSP 是否真的死了**：not proven。若 ADSP 还活着且只是 lease 没谈成，则 §4 的「抢 VADC」风险成立，降级路径应该先只读。
- **VADC 的 PPID/地址**：vadc@3100 的 reg 0x3100 是 SPMI 偏移，但实际访问要经 arbiter 的 apid 映射；vadc 的 PPID 值（0x031）来自 mainline/同 SoC 惯例，**在本机 FDT 里没有直接写出**。2026-11-17 已证明 PPID 0x031 在 AP EE0 映射里且可读（apid=408，§3.1(4)），但「PPID 0x031 = vadc@3100」仍是推断，需靠 §5 第一步的 STATUS1/APP_SID/EN_CTL1 读数确认。
- 未找到（not found）：`E:/hackios` 下没有 Linux 内核源码树（`qcom_spmi_adc5.c`、`qcom_battmgr.c` 均 not found），本文的寄存器与公式全部来自外部 mainline v6.6 引用；端口仓库内也没有任何 VADC/ADC 相关驱动（`grep -i vadc` 在 drivers/ 下 not found）。
