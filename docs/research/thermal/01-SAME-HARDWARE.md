# 01 · 同型号硬件事实（Redmi K60 / mondrian / SM8475）

本文件只记录**可复核的硬件事实**，每条给 DTS 行号。所有结论来自本板自己的 DTB 反编译，不来自同族机型推断。

## 0. 证据来源与复现命令

- DTB：`/mnt/e/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb`
  （= 我们 UEFI/mondrian 平台实际加载的那份 FDT）。
- 反编译（WSL 内 `/usr/bin/dtc`，幂等）：

```
dtc -I dtb -O dts /mnt/e/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb \
    -o /tmp/mondrian.dts
```

- 产物：21954 行，sha256 `516ac7d55c94cde466e57d2e0efb9014fd1cc3534210c80ef20dd5510146f16a`；
  持久副本 `/mnt/e/k60-work/scratch/mondrian.dts`（scratch 会被清理时就地重跑上面的命令重建）。
- dtc 只报 3 条 `graph_child_address` warning（tpda / funnel），与 thermal 无关。
- 本文所有 `mondrian.dts:NNN` 均指上述产物。行号可被任何人重跑 dtc 复核。
- 交叉印证：`docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:139` 在更早的 Android vendor_boot
  反编译（fdt1）里记录 `qcom,tsens-v2 ×2（fdt1:16439,16449）` —— 与本文件行号一致，说明这份 DTB
  与 Android 侧 fdt1 是同一份内容，不是我们从别处拼来的。

## 1. 两个 tsens-v2 控制器

`mondrian.dts:16438-16446`（第一个，aliases `tsens0`）：

```
16438: thermal-sensor@c263000 {
16439:     compatible = "qcom,tsens-v2";
16440:     reg = <0xc263000 0x1ff 0xc222000 0x1ff>;
16441:     #qcom,sensors = <0x10>;
16442:     interrupts = <0x00 0x1fa 0x04 0x00 0x1fc 0x04>;
16443:     interrupt-names = "uplow\0critical";
16444:     #thermal-sensor-cells = <0x01>;
16445:     phandle = <0x5d>;
16446: };
```

`mondrian.dts:16448-16456`（第二个，aliases `tsens1`）：内容同构，只有地址/中断/phandle 不同 ——
`reg = <0xc265000 0x1ff 0xc223000 0x1ff>`（:16450）、`#qcom,sensors = <0x10>`（:16451）、
`interrupts = <0x00 0x1fb 0x04 0x00 0x1fd 0x04>`（:16452）、`phandle = <0x6b>`（:16455）。

aliases：`mondrian.dts:21890 tsens0 = "/soc/thermal-sensor@c263000"`、
`mondrian.dts:21891 tsens1 = "/soc/thermal-sensor@c265000"`。

汇总：

| | 控制器 A（tsens0） | 控制器 B（tsens1） |
|---|---|---|
| 节点行 | mondrian.dts:16438 | mondrian.dts:16448 |
| TM 寄存器块 | `0xc263000`，长度 `0x1ff` | `0xc265000`，长度 `0x1ff` |
| SROT 块（reg 第二段） | `0xc222000`，长度 `0x1ff` | `0xc223000`，长度 `0x1ff` |
| 传感器数 | `#qcom,sensors = 16` | `#qcom,sensors = 16` |
| 中断 | `<0 0x1fa 4>` uplow、`<0 0x1fc 4>` critical（GIC SPI 506 / 508） | `<0 0x1fb 4>` uplow、`<0 0x1fd 4>` critical（SPI 507 / 509） |
| 中断名 | `"uplow","critical"` | `"uplow","critical"` |
| phandle | `0x5d` | `0x6b` |
| aliases | `tsens0` | `tsens1` |

寄存器窗口长度 `0x1ff` 而非 `0x200`：这是 Qualcomm DT 的常规写法（`0x1ff` 表示 512 字节窗口减去 1），
上游 binding 的示例同样是 `0x1ff`（见 02 篇）。

**两个控制器都是 TM + SROT 双地址**，SROT（rotated register block）不是独立外设，而是同一 IP 的
"非旋转视图"：TM 块是旋转过的传感器数据视图，SROT 块提供使能位/版本号/中断集合。这个拆分对读温度
是决定性的 —— 见 02 篇 `tsens.c:901-916`（两段 resource 时 `tm_offset=0`，SROT 单独 ioremap）。

## 2. 时钟 / 复位 / 电源属性：DT 里没有

`thermal-sensor@c263000`（16438-16446）与 `thermal-sensor@c265000`（16448-16456）整节点**没有**
`clocks`、`clock-names`、`resets`、`power-domains`、`nvmem-cells`、`qcom,tsens-calibration`。

推论（标明是推论）：上游 binding 的 required 列表（`qcom-tsens.yaml:222-227`）不含 clocks，
上游驱动也从不取时钟，只 ioremap reg。因此 K60 上读 tsens **不需要我们打开任何时钟**，
只需要 XBL 已经把 TSENS 使能（`SROT_CTRL[0]`，见 02 篇 `tsens.c:974-981`）。这一点必须上机读寄存器确认（见 §10）。

## 3. 传感器数量与索引映射（DT 直接给出，共 16+16 = 32 个）

zone 的 `thermal-sensors = <&controller index>` 就是官方索引定义，不需要猜：

**tsens0（0xc263000，phandle 0x5d）16 个**：

| idx | zone | 行 |
|---|---|---|
| 0 | aoss-0 | 7108 |
| 1-4 | cpuss-0 / cpuss-1 / cpuss-2 / cpuss-3 | 7129 / 7150 / 7171 / 7192 |
| 5-13 | cpu-1-0 … cpu-1-8（9 个） | 7213 / 7247 / 7281 / 7323 / 7365 / 7407 / 7449 / 7491 / 7533 |
| 14-15 | gpuss-0 / gpuss-1 | 7575 / 7617 |

**tsens1（0xc265000，phandle 0x6b）16 个**：

| idx | zone | 行 |
|---|---|---|
| 0 | aoss-1 | 7659 |
| 1-4 | cpu-0-0 … cpu-0-3 | 7680 / 7722 / 7764 / 7806 |
| 5-7 | nspss-0 / nspss-1 / nspss-2 | 7848 / 7890 / 7932 |
| 8 | video | 7974 |
| 9 | ddr | 7995 |
| 10-13 | mdmss-0 … mdmss-3 | 8041 / 8104 / 8167 / 8230 |
| 14-15 | camera-0 / camera-1 | 8293 / 8314 |

## 4. 标定属性：**DT 里确实不存在**

复核方法（对全文，不只是节点附近）：

```
grep -c -iE 'calib|qfprom|efuse' /tmp/mondrian.dts     -> 0
```

零命中。所以：

- 本板 DTB 既没有 `nvmem-cells`，也没有 vendor 私有的 `qcom,tsens-calibration`，
  更没有 p1/p2 系数或 base1/base2 地址。
- 这**不等于**传感器不可用。上游驱动在"无 nvmem"时走 calibrationless 分支
  （`tsens.c:147-151`：`dev_dbg("calibrationless mode")` + `p1=500,p2=780`），而 v2 IP 的读数
  路径根本不用 p1/p2 —— `tsens.c:346-347` 明确写 deciCelsius 直接乘 100 得 m°C。
  详见 02 篇 §3。**结论：缺标定属性不影响"读温度"，只影响"我们自己去写硬件阈值"**（本阶段不做阈值编程）。
- 任何声称"必须读 QFPROM 取标定才能换算温度"的说法，在 v2 + 本 DT 上都不成立，不要照抄。

## 5. thermal-zones 全表（58 个 zone，6643-8422）

`mondrian.dts:6643 thermal-zones {`，到 `mondrian.dts:8422` 闭合（脚本按 tab 深度解析，58 个直接子节点）。
按数据来源分三类：

| 类别 | 个数 | 数据来源 |
|---|---|---|
| AP tsens 直读 | 32 | `<0x5d n>` / `<0x6b n>`，见 §3 |
| QMI 远端（modem/ADSP 上报） | 25 | `<0x5c n>`（`qmi-ts-sensors`，mondrian.dts:16774-16788） |
| mx-pe | 1 | `<0x85>`（单 cell，mondrian.dts:8335） |

> **58 是 DT 描述数，不是运行时 zone 数。** 设备 6033dbec 上实际注册了 **84** 个 thermal zone
> （`/sys/class/thermal/thermal_zone0..83`）：32 AP tsens + 25 QMI + 6 PMIC(spmi-temp-alarm)
> + 8 BCL + 9 小米虚拟(mi_thermal_interface) + `socd` + 3 电池。多出来的 26 个来自 dtbo overlay
> 与厂商 ko，不在主 DTB；而 DT 里的 `mx-pe` 是 `status = "disabled"`（mondrian.dts:8336），
> 运行时不存在。**两个数字都对，但不是同一个量，不能互相校验**；能互相校验的只有 AP 的 32 个
> （见 `docs/research/thermal/04-ANDROID-EVIDENCE.md` §1、§2）。

### 5.1 AP tsens 的 32 个 zone（温度值均为 m°C 十六进制解码）

| zone | 行 | 传感器 | trip 温度（按 DTS 顺序） | cooling-maps |
|---|---|---|---|---|
| aoss-0 | 7108 | tsens0 idx 0 | 125℃ / 115℃ | — |
| cpuss-0 | 7129 | tsens0 idx 1 | 125℃ / 115℃ | — |
| cpuss-1 | 7150 | tsens0 idx 2 | 125℃ / 115℃ | — |
| cpuss-2 | 7171 | tsens0 idx 3 | 125℃ / 115℃ | — |
| cpuss-3 | 7192 | tsens0 idx 4 | 125℃ / 115℃ | — |
| cpu-1-0 | 7213 | tsens0 idx 5 | 125 / 125 / 115 / 110℃ | — |
| cpu-1-1 | 7247 | tsens0 idx 6 | 125 / 125 / 115 / 110℃ | — |
| cpu-1-2 | 7281 | tsens0 idx 7 | 125 / 125 / 115 / 110℃ | 0x5e→0x5f |
| cpu-1-3 | 7323 | tsens0 idx 8 | 125 / 125 / 115 / 110℃ | 0x60→0x5f |
| cpu-1-4 | 7365 | tsens0 idx 9 | 125 / 125 / 115 / 110℃ | 0x61→0x62 |
| cpu-1-5 | 7407 | tsens0 idx 10 | 125 / 125 / 115 / 110℃ | 0x63→0x62 |
| cpu-1-6 | 7449 | tsens0 idx 11 | 125 / 125 / 115 / 110℃ | 0x64→0x65 |
| cpu-1-7 | 7491 | tsens0 idx 12 | 125 / 125 / 115 / 110℃ | 0x66→0x65 |
| cpu-1-8 | 7533 | tsens0 idx 13 | 125 / 125 / 115 / 110℃ | 0x67→0x65 |
| gpuss-0 | 7575 | tsens0 idx 14 | 125 / 125 / 115 / 95℃ | 0x68→0x69 |
| gpuss-1 | 7617 | tsens0 idx 15 | 125 / 125 / 115 / 95℃ | 0x6a→0x69 |
| aoss-1 | 7659 | tsens1 idx 0 | 125℃ / 115℃ | — |
| cpu-0-0 | 7680 | tsens1 idx 1 | 125 / 125 / 115 / 110℃ | 0x6c→0x6d |
| cpu-0-1 | 7722 | tsens1 idx 2 | 125 / 125 / 115 / 110℃ | 0x6e→0x6f |
| cpu-0-2 | 7764 | tsens1 idx 3 | 125 / 125 / 115 / 110℃ | 0x70→0x71 |
| cpu-0-3 | 7806 | tsens1 idx 4 | 125 / 125 / 115 / 110℃ | 0x72→0x73 |
| nspss-0 | 7848 | tsens1 idx 5 | 125 / 125 / 115 / 95℃ | 0x74→0x75 |
| nspss-1 | 7890 | tsens1 idx 6 | 125 / 125 / 115 / 95℃ | 0x76→0x75 |
| nspss-2 | 7932 | tsens1 idx 7 | 125 / 125 / 115 / 95℃ | 0x77→0x75 |
| video | 7974 | tsens1 idx 8 | 125℃ / 115℃ | — |
| ddr | 7995 | tsens1 idx 9 | 125 / 90 / 115℃ | 0x78→0x19、0x78→0x1c、0x78→0x79 |
| mdmss-0 | 8041 | tsens1 idx 10 | 125 / 102 / 105 / 115℃ | 0x7a→0x7b/0x7c/0x7d、0x7e→0x7b/0x7d |
| mdmss-1 | 8104 | tsens1 idx 11 | 125 / 102 / 105 / 115℃ | 0x7f→0x7b/0x7c/0x7d、0x80→0x7b/0x7d |
| mdmss-2 | 8167 | tsens1 idx 12 | 125 / 102 / 105 / 115℃ | 0x81→0x7b/0x7c/0x7d、0x82→0x7b/0x7d |
| mdmss-3 | 8230 | tsens1 idx 13 | 125 / 102 / 105 / 115℃ | 0x83→0x7b/0x7c/0x7d、0x84→0x7b/0x7d |
| camera-0 | 8293 | tsens1 idx 14 | 125℃ / 115℃ | — |
| camera-1 | 8314 | tsens1 idx 15 | 125℃ / 115℃ | — |

trip 命名与含义（同一家族一致）：

- `thermal-engine-config` / `thermal-engine-config0`：125℃（`0x1e848`），`passive`，无 phandle
  → 高通 thermal-engine 用户态用，内核侧无映射。
- `thermal-engine-config`（第二个）/ `thermal-hal-config`：125℃（`0x1e848`），`passive`。
- `reset-mon-cfg`：115℃（`0x1c138`），`passive`，hysteresis 5000m°C（`0x1388`）
  → 触发复位监控（真正会重启机器的线）。
- `cpuX-emergN-cfg` / `tj_cfg` / `junction-config` / `ddr0-config`：110℃ / 95℃ / 90℃，
  `passive`，**带 phandle** → 这些是被 cooling-map 引用的 trip。
- `mdmss*-config0/config1`：102℃ / 105℃，`active` → 全表里唯一的 active trip，且属于 modem 侧。

**关键结论：AP tsens 侧没有 active trip；除 mdmss 的 102/105℃ 外全是 passive。**
在 XNU 侧我们不跑 thermal-engine，所以这些 trip 对我们只有"参考阈值"意义，不会被内核自动触发。

### 5.2 QMI 远端 25 个 zone（不是我方 tsens，但共用同一个 thermal-zones 表）

`mondrian.dts:16774-16788 qmi-ts-sensors`（`compatible = "qcom,qmi-sensors"`，`#thermal-sensor-cells = <1>`，
phandle `0x5c`），两个子节点：`cdsp`（16779-16782，instance-id `0x43`，sensor 名 `isense_trim`）、
`modem`（16784-16787，instance-id `0x00`，sensor 名 26 个：pa … sdr1_pa）。

| zone | 行 | qmi idx | | zone | 行 | qmi idx |
|---|---|---|---|---|---|---|
| pa | 6646 | 0x00 | | mmw-ific0 | 6961 | 0x32 |
| pa1 | 6667 | 0x01 | | sub1-modem-cfg | 6976 | 0x33 |
| bcl-warn | 6688 | 0x1f | | sub1-lte-cc | 6991 | 0x34 |
| sdr0-pa0 | 6709 | 0x20 | | sub1_mcg_fr1_cc | 7006 | 0x35 |
| sdr0 | 6730 | 0x26 | | sub1_mcg_fr2_cc | 7021 | 0x36 |
| sdr1-pa0 | 6751 | 0x27 | | sub1_scg_fr1_cc | 7036 | 0x37 |
| sdr1 | 6772 | 0x2d | | sub1_scg_fr2_cc | 7051 | 0x38 |
| sdr-mmw-therm | 6793 | 0x1d | | sdr0-pa | 7066 | 0x40 |
| mmw0 | 6814 | 0x2e | | sdr1-pa | 7087 | 0x41 |
| mmw1 | 6835 | 0x2f | | isense_trim | 8389 | 0x82 |
| mmw2 | 6856 | 0x30 | | | | |
| mmw3 | 6877 | 0x31 | | | | |
| mmw_pa1 | 6898 | 0x1a | | | | |
| mmw_pa2 | 6919 | 0x1b | | | | |
| mmw_pa3 | 6940 | 0x1c | | | | |

（共 25 个：24 个 modem 侧 + 1 个 cdsp 侧 `isense_trim`。`mondrian.dts:16786` 的
`qcom,qmi-sensor-names` 就是这个顺序的字符串表，不是 AP tsens 的传感器名 —— 两者不要混。）

这些 zone 的 trip 一律 125℃ `thermal-engine-config*`（`isense_trim` 例外，见 §5.3），
没有 cooling-map 价值可挖，且读它们需要 QMI/GLINK 通路（我们还没有），**本阶段整类排除**。

### 5.3 mx-pe（唯一一个非 tsens、非 QMI 的 zone）

`mondrian.dts:8335-8388`：`thermal-sensors = <0x85>`（单 cell 引用别的传感器节点），
三个 trip `mx-pe-config1/2/3` 的 `temperature` 是 `1/2/3` —— **不是温度**，是 config 序号
（102/105℃ 之类的真实值不在这三个 trip 里）。它的 cooling-map 指向 cdsp(0x75)/GPU(0x69)/modem(0x7b,0x7c)。
我们不解析它，登记在案以免后来者误当温度读。

## 6. polling-delay：58 个 zone 里 52 个为 0，6 个为 10ms

```
grep -o 'polling-delay-passive = <[^>]*>' mondrian.dts | sort | uniq -c
   52 polling-delay-passive = <0x00>
    6 polling-delay-passive = <0x0a>
grep -c 'polling-delay = <0x00>' mondrian.dts     -> 58（全部为 0）
```

6 个 10ms 的 zone：`gpuss-0`(7575, `:7577`)、`gpuss-1`(7617)、`nspss-0`(7848)、
`nspss-1`(7890)、`nspss-2`(7932)、`ddr`(7995, `:7996`)。

含义：厂商固件不靠内核轮询热区（polling-delay 全 0 = 只靠中断/用户态），GPU/NPU/DDR 例外给了 10ms
被动轮询。**对我们的启示：XNU 侧必须自己起轮询**，不能指望 trip 中断驱动 —— 这与同族实现的
"每 2s 采一次" 做法一致（见 03 篇）。

## 7. cooling device 与 cooling-map

cooling device 全部是 `/soc` 下的节点，phandle 与名字：

| phandle | 节点 | 行 | 说明 |
|---|---|---|---|
| 0x5f | `qcom,cpu-pause/cpu5-pause` | 16485（phandle :16488） | `compatible = "qcom,thermal-pause"`（:16459），`qcom,cpus=<0x17>`（:16486） |
| 0x62 | `cpu6-pause` | 16491 | `qcom,cpus=<0x18>` |
| 0x65 | `cpu7-pause` | 16497 | `qcom,cpus=<0x1a>`（注意：0x1a 是 CPU7 的 phandle，不是索引 0x1a） |
| 0x6d/0x6f/0x71/0x73 | `cpu0-pause`…`cpu3-pause` | 16461/16467/16473/16479 | 每节点 `#cooling-cells = <2>`（:16463 起） |
| 0x69 | `qcom,kgsl-3d0@3d00000` | 16170（`#cooling-cells` :16193） | Adreno GPU，`compatible = "qcom,adreno-gpu-gen7-4-0","qcom,kgsl-3d0"`（:16171） |
| 0x75 | `cdsp`（remoteproc） | — | NPU/DSP 侧 |
| 0x79 | `qcom,ddr-cdev` | 16612 | DDR 频率 |
| 0x19 / 0x1c | cpufreq cooling（gold / gold+） | — | `qcom,cpufreq-cdev` 节点 :16790-16793，`qcom,cpus = <0x15 0x19 0x1c>`（:16792） |
| 0x7b/0x7c/0x7d | modem cdev（lte / nr_scg / nr） | — | 由 `qcom,qmi-cooling-devices`（16630）提供 |
| 0x43c | `qcom,userspace-cdev/display-fps` | 16800-16807 | `qcom,max-level = 4`（:16804） |

补充节点：`apc1-pause`（16503，`qcom,cpus=<0x1a 0x1b 0x1c>`，phandle 0x420）、
`cpu-6-7-pause`（16509，`qcom,cpus=<0x1b 0x1c>`，phandle 0x421）、`qcom,devfreq-cdev`（16795，
`qcom,devfreq=<0x69>` 即 GPU）。

cooling-map 的形状说明（以 `cpu-1-2` 为例，`mondrian.dts:7306-7313`）：

```
cpu12_cdev {
    trip = <0x5e>;                       /* 指向本 zone 的 trip phandle */
    cooling-device = <0x5f 0x01 0x01>;   /* cpu5-pause，下限 1 上限 1 级 */
};
```

即"某温度点触发，把某个 cooling device 压到某一档"。**我们不复用这套策略**（XNU 没有 cooling-device 框架，
也没有 thermal-engine），只把它当作"板级设计意图"的证据：CPU 集群靠 pause 核 + 降频，GPU/NPU 靠降频，
DDR 靠 gold/gold+ 降频 + ddr-cdev，modem 靠 LTE/NR 降频。

## 8. 这份 DTB 里**没有**的其它热源

- 没有 `qcom,spmi-temp-alarm`（PMIC 温度告警）节点 —— grep 零命中。
  `docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:139` 记录的 6 个
  `qcom,spmi-temp-alarm@a00`、2 个 `qcom,bcl-v5`、`qcom,msm-bcl-soc` 都在 **overlay（dtbo）** 里
  （该文档写的是 fdt19 / vendor_boot overlay），不在我们这份主 DTB 中。
  → 本阶段只做 tsens，PMIC 温度告警属于后续（需要 overlay 合入 + SPMI 通路）。
- 没有 `qcom,tsens-calibration` / `nvmem-cells` / `qfprom`（§4）。
- `qcom,qmi-cooling-devices`（16630）是远端 cooling device 的容器，其子节点由 QMI 服务提供，
  不能本地直读。

## 9. 与任务书「8 个传感器」的偏差（重要）

任务书写"2 个控制器 × 8 传感器"或"8 个传感器"。**DT 事实是 2 个控制器 × 16 = 32 个**：

- `#qcom,sensors = <0x10>`（mondrian.dts:16441 与 :16451）；
- 上游 binding `qcom-tsens.yaml:214` 的 `maximum: 16` 也印证 16 是单控制器上限；
- 32 个 AP zone 一一对应（§5.1），没有空洞，所以我方读数应按 32 个规划。

（另：同族 SM8550 是 3 个控制器 × 16 = 48；POCO X5 Pro 的 SM6375 是 2 个控制器但只暴露
15+12=27 个 —— 见 03 篇。所以"数量"必须逐板从 DT 取，不能跨型号套用。）

## 10. 上机前必须确认的三件事（本阶段禁上机，只登记）

1. **SROT_CTRL[0]（TSENS_EN）必须为 1** —— 位置 `0xc222000+0x4` / `0xc223000+0x4`。若为 0，上游驱动会
   `dev_err("device not enabled")` 并放弃（`tsens.c:974-981`），说明 XBL 没使能，读数不可信。
2. **SROT_HW_VER（`+0x0`）应能读出合理的 major/minor**（v2 期望 major=2），可用来确认映射正确。
3. **TM_Sn_STATUS（`TM + 0xa0 + 4*n`）的 bit21（VALID）在 32 个传感器上应全为 1**，且读数落在
   -40..160℃ 合理区间。逐传感器比对同族实现的顺序（aoss/cpuss/cpu/gpuss 与我们的索引一致，见 03 篇差异表）。

这三条是第 8 步（上机）的 prediction 依据，写进 EIGHT-STEPS 的 `step.device.prediction`（见 04 篇/登记项）。
