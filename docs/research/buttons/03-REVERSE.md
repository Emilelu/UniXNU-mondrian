# 按键 ③ 反编译资料 + 真机数据

> 状态：✅ 已完成（2026-11-14）。证据等级：反编译 + 真机日志。来源：K60 live FDT 反编译、Android vendor 模块清单与厂商 pinctrl 源码、K60 UEFI 侧按键驱动（boot39/40 实测）、内核侧 `Pong keys` 日志。

## 反编译 / 二进制提取

| # | 对象 | 命令 / 方式 | sha256 / 结果 | 用途 |
|---|---|---|---|---|
| 1 | K60 live FDT | 设备导出 `/sys/firmware/fdt` → `dtc -I dtb -O dts` | dtb `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`（919,210 B，FDT v17）；dump `/e/k60-work/scratch/power-work/assets/live-fdt.dts`（21,954 行） | 按键节点的**唯一本机真值** |
| 2 | Android vendor 模块清单 | `modules.list.msm.mondrian.txt` | 106 行；含 `qcom-spmi-pmic.ko`(:78)、`spmi-pmic-arb.ko`(:79)、`regmap-spmi.ko`(:88)、`nvmem_qcom-spmi-sdam.ko`(:58) | 证明 SPMI 仲裁器是模块，而按键驱动（`gpio_keys`/`qpnp-power-on`）**不在清单里** → GKI 内建 |
| 3 | 厂商 PMIC GPIO 寄存器定义 | `vendor/pinctrl-spmi-gpio.c` | `PMIC_GPIO_REG_SUBTYPE 0x5`(:33)、`MODE_CTL 0x40`(:50)、`DIG_PULL_CTL 0x42`(:52)、`DIG_IN_CTL 0x43`(:54)、`EN_CTL 0x46`(:56)；subtype `GPIO_LV 0x10`/`GPIO_MV 0x11`/`GPIO_LV_VIN2 0x12`/`GPIO_MV_VIN3 0x13`(:41-44) | 内核侧校验 GPIO6 时用的 type/subtype/寄存器偏移 |
| 4 | K60 UEFI 按键库 | `git clone https://github.com/yibiya/uefi-mondrian.git` | `Silicon/Qualcomm/QcomPkg/Library/K60KeypadDeviceLib/K60KeypadDeviceLib.c`（409 行）+ `.inf` | 独立实现，boot39/40 实测值（ground truth） |
| 5 | 已退役的 UEFI 按键驱动 | 同仓 | `Silicon/Qualcomm/QcomPkg/Drivers/K60ButtonsDxe/K60ButtonsDxe.c`（470 行），提交 `28d45ed`（v3 自动检测 v5/v7/v2）、`f4cbb97`（v7 布局） | 仲裁器版本自检的历史证据（boot36 dump 证明 K60 不是 v2） |
| 6 | 内核侧补丁（本线只读） | `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` | 13,668 B，171 行 `bsd/dev/pong_buttons.c`（轮询版） | 当前在树实现 |

### ⚠️ 更正任务书的一条前提

任务书写「用 dtc 从 `sm8475-xiaomi-mondrian.dtb` 生成后 grep 有 gpio-keys 命中」——**实测不成立**：
`references/yibiya-uefi-upstream/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb`（480,692 B）反编译后 `model = "Qualcomm Technologies, Inc. Cape SoC"`，**没有** `gpio-keys` / `pwrkey` / `pon_hlos` 节点。它是 Cape 通用 DT，不是 K60 的按键描述。
本机按键真值来自**live FDT**（上表第 1 行）与 UEFI 侧实测，两者独立且一致。

## live FDT 按键节点（`live-fdt.dts`，行号为该 dump 的绝对行号）

| 行 | 节点 | 关键属性 |
|---|---|---|
| :9836 | `qcom,pmk8350@0` | `compatible="qcom,spmi-pmic"`，`reg=<0x00 0x00>` → **SPMI SID 0** |
| :9843 | `pon_hlos@1300` | `compatible="qcom,pm8998-pon"`，`reg=<0x1300 0x800>`，`reg-names="pon_hlos\0pon_pbs"`，`qcom,log-kpd-event` |
| :9850 | `pwrkey` | `compatible="qcom,pmk8350-pwrkey"`，`interrupts=<0x00 0x13 0x07 0x03>`，`linux,code=<0x74>` |
| :9856 | `resin` | `compatible="qcom,pmk8350-resin"`，`interrupts=<0x00 0x13 0x06 0x03>`，`linux,code=<0x72>` |
| :9862 | `pwrkey-bark` | `interrupts=<0x00 0x13 0x00 0x03>` |
| :9868 | `pwrkey-resin-bark` | `interrupts=<0x00 0x13 0x02 0x03>` |
| :32475 | `gpio_keys` | `compatible="gpio-keys"`，`label="gpio-keys"`，`pinctrl-0=<0x57a>` |
| :32481 | `vol_up` | `label="volume_up"`，`gpios=<0x57b 0x06 0x01>`，`linux,input-type=<0x01>`，`linux,code=<0x73>`，`gpio-key,wakeup`，`debounce-interval=<0x20>`（32 ms），`linux,can-disable` |
| :10322 | `qcom,pm8350@1` | `reg=<0x01 0x00>` → **SPMI SID 1** |
| :10338 | `pinctrl@8800` | `compatible="qcom,pm8350-gpio"`，`reg=<0x8800>`，`gpio-controller`，`#gpio-cells=<2>`，`interrupt-controller`，`phandle=<0x57b>` |
| :10356/:10358 | `key_vol_up` / `key_vol_up_default` | `pins="gpio6"`，`function="normal"`，`input-enable`，`bias-pull-up`，`power-source=<0x01>`，`phandle=<0x57a>` |

SPMI 中断说明符是 `<USID periph irq type>`：`<0x00 0x13 0x07 0x03>` = SID0 / 外设 0x13 / IRQ 7；`<0x00 0x13 0x06 0x03>` = 同一外设的 IRQ 6。
`gpios=<0x57b 0x06 0x01>` = 控制器 0x57b（pm8350 pinctrl@8800）/ 第 6 脚 / **GPIO_ACTIVE_LOW**。
`pinctrl@8800` 是 **GPIO1 的页**，每脚 0x100 → GPIO6 = `0x8800 + 0x100*5 = 0x8d00`，页内 `INT_RT_STS` = 0x10。

## 键位映射（本机真值，三条独立证据一致）

| 键 | 来源 | 外设 / PPID | 状态寄存器 | 判据 | linux,code |
|---|---|---|---|---|---|
| 电源 | PMK8350 PON KPDPWR_N | SID0 / `0x013`（type 0x01, subtype 0x09 HLOS） | `0x10` INT_RT_STS | **bit7 = 1**（按下） | `0x74` = 116 KEY_POWER |
| 音量减 | 同一 PON 的 RESIN_N | SID0 / `0x013` | `0x10` INT_RT_STS | **bit6 = 1**（按下） | `0x72` = 114 KEY_VOLUMEDOWN |
| 音量加 | PM8350 GPIO6 | SID1 / `0x18D`（type 0x10, subtype 0x10..0x13） | `0x10` INT_RT_STS | **bit0 = 0**（低有效，按下） | `0x73` = 115 KEY_VOLUMEUP |

- **RT_STS 的位号 == 该外设的 IRQ 号**（`spmi-pmic-arb` 的 qpnpint 规则）：pwrkey 是 IRQ7 → bit7，resin 是 IRQ6 → bit6。这条规则同时解释了为什么早期的 `bit0/bit1` 假设（K60ButtonsDxe v3 头注释）是错的。
- **与 PHK110 的映射相反**：PHK110 是 RESIN=音量加、GPIO6=音量减；K60 是 RESIN=音量减、GPIO6=音量加。外设 id 两机相同，**不能照抄映射**。

## Android 侧实机取证

| 项 | 结论 | 证据 |
|---|---|---|
| SPMI 从设备 | `pmk8350@0`(SID0) :9836、`pm8350@1`(SID1) :10322、`pm8350c@2` :10370、`pmr735a@4` :10817 | live FDT |
| 按键驱动形态 | vendor 模块清单里**没有** `gpio_keys.ko`/`qpnp-power-on.ko` → 走 GKI 内建 `gpio-keys` + `pm8941-pwrkey`（PON） | `modules.list.msm.mondrian.txt` 全 106 行 grep |
| GPIO6 的配置 | `normal` 功能 + `input-enable` + `bias-pull-up` + `power-source=1`；内核侧回读校验 `MODE&3==0`（输入）、`PULL&7<4`（上拉）、`EN&0x80`（使能） | live FDT :10358-10364；`patches/…-pong-physical-keys.patch:257-259` |
| 去抖 | DT 给 32 ms（`debounce-interval=<0x20>`）；内核驱动自己再用 16 ms 周期 + 三态（last/live/down）判定 | live FDT :32487；`patches/…:235` `look()` |

## UEFI 侧独立取证（K60 自己的实现，boot39/40 实测）

`K60KeypadDeviceLib.c` 头注释 :19-33 逐条（"Hardware facts carried over from K60ButtonsDxe v7 (boot39/40 verified)"）：

| 行 | 事实 |
|---|---|
| :21 | 仲裁器 map 表 @ `core+0x2000`，`apid_count 758`，obs stride `0x20`（ee=0） |
| :23 | **opcode 15（`PMIC_ARB_OP_READ`）在真机可用**，失败回退 `EXT_READL(1)` |
| :26/:27 | PON = `pmk8350@0 pon@1300` → PPID `0x013`（sid 0）；GPIO = `pm8350@1 pinctrl@8800(+5)` → PPID `0x18D`（sid 1） |
| :28-:30 | Power = PON `INT_RT_STS(0x10)` **bit7**（pwrkey IRQ7）；VolDn = **bit6**（resin IRQ6）；VolUp = pm8350 gpio6 `RT_STS` **bit0，ACTIVE LOW** |
| :32 | **RT_STS 位号 == 外设 IRQ 号**（spmi-pmic-arb 的 qpnpint 规则） |
| :33 | **boot40 VERIFY ground truth：pon rtsts=0x10、gpio rtsts=0x01**（PON 空闲读到 0x10，GPIO6 空闲读回 0x01 = 低有效未按下） |
| :65/:66 | `SPMI_MAP_BASE 0x2000`、`SPMI_APID_COUNT 758` |
| :72/:74/:75 | `ARB_OP_READ 15`、`PON_REG_STATUS 0x10`、`GPIO_REG_STATUS 0x10` |
| :78/:79 | `PPID_PON 0x013`、`PPID_GPIO 0x18D` |
| :364 | 代码里再次注释 "Live DT: PON pwrkey=IRQ7 -> bit7, resin=IRQ6 -> bit6" |

退役的 `K60ButtonsDxe.c` 给出的仲裁器自检：boot36 dump 显示 v2 布局（`core+0x900`）全 0、`core+0x1000` 只有 4 个垃圾项、所有 OBS 事务超时 → K60 不是 v2；现行判断是 `version >= 0x70000000` → v7。

## 内核侧真机数据（K60 自己的日志）

| 日志目录 | 行 | 内容 |
|---|---|---|
| `usblog-20261108-180257/console.log` | :204 | `Pong keys: missing/incompatible DT; SKIP`（早期一版，DT 节点尚未生成） |
| 同上 | :229 | `Pong keys: arbiter v7 channels=768 PON=407 GPIO6=434; power=1 up=1 down=1` |
| 同上 | :3742-3838 | **134 条** `Pong keys: <0|1|2> down/up`（0=power、1=vol-up、2=vol-down） |
| `usblog-20261108-213652/console.log` | :1266 | `Pong keys HID: physical side/volume consumer opened` |
| 同上 | :2424 起 | **170 条** `Pong keys HID: key=<0|1|2> down=<0|1> sent=1`，含长按与同时按 |
| `usblog-20261108-210018/console.log` | :1904 | `Pong keys HID: verified PMIC input unavailable; SKIP`（设备节点未就绪的对照） |
| `usblog-20261114-usb-hb1/console.log` | :215 | `Pong keys: PMIC windows mapped, pon-ppid=0x13 volume-up-ppid=0x18d` |
| 同上 | :240 | `Pong keys: arbiter v7 channels=768 PON=407 GPIO6=434; power=1 up=1 down=1` |
| 同上 | :1358 | `Pong keys HID: physical side/volume consumer opened`（本轮无按键按下记录） |

**APID 实测值**：PON = 407（0x197）、GPIO6 = 434（0x1B2）。这两个数是仲裁器 map 表的运行时索引，**无法从 DT 推导**，只能实测 —— 它们与 PHK110 的 407/434 完全相同，因为同一代 PMIC 的 APID 分配一致。

## 缺口

- ❌ **DTBO 未取得**：K60 的 `dtbo.img` / `/proc/device-tree` 原始输出没有留档，live FDT 是 AP 侧视角的合并结果；UEFI 注释写「live DT dtbo0」说明按键节点来自 dtbo0，但该分区镜像本身没保存。影响：无法核对 overlays 里是否还有第二份 gpio-keys 或 status 覆盖。
- ◐ **Android 侧 `/sys/class/input` 与 `dmesg` 未留档**：`gpio-keys` 的实际注册名、`/proc/bus/input/devices` 的键位表没抓。当前映射靠 DT + UEFI 实测两源，足够，但少了第三源。
- ❌ `/buttons` 节点缺失（见 ② 缺口）—— 属于 ADT 生成器问题，不是反编译问题。发射器是 `board.toml` 的 `[adt.buttons.*]`（`devicetree.py:388-390`），不是 `scripts/make-pong-adt.py`；修法见 `patches/buttons/README.md` 的 diff 建议。
- ◐ **`/arm-io/pong-buttons` 的来源已查清（2026-11-14）**：11-14 镜像的 ADT 里有该节点（六属性、无 `compatible`），但 `board.toml` 与 `dts/` 都没有 —— 它来自框架 OS profile `profiles/os/ipados-16.6.1-20G81/profile.toml:149-158` 的一处**本地未提交**改动（合并顺序 arch → soc → os profile → board，后者覆盖前者）。取证过程与三个反证见 `02-OFFICIAL.md` 的「ADT 里 `/arm-io/pong-buttons` 的实际来源」一节。
- ◐ PON 的 PBS 页（`pon_pbs@800`，`0x0810`）在 K60 上不可由 AP 读取：`0x0810` 落在 `pon_pbs` 页而非 `pon_hlos`，这是 sweet 板驱动（`0060-sweet-keys-touch-drivers.patch:58` `KEYS_PON_RT 0x0810`）在 K60 上失效的根因；K60 读的是 `pon_hlos` 页内的 `0x10`（整地址 `0x1310`）。
