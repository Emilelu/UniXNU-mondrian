# K60 触摸参数表（Goodix / GENI-SPI）

> 调研日期：2026-11-07。只读调研，只写本文件。
> 结论先行：请求的 raw dtbo `D:/Android/k60-ios/dtb/dtbo_a_fdt15.dtb` **不存在**，本文件无法解析该文件本身；改用同板 **live merged FDT** `E:/k60-work/reports/live-6033dbec-fdt.dtb`（FDT v17，sha256 `95c02052…`）解析出已应用的触摸节点。下表所有数值均标来源；没有查到的项写“未核实”，不猜。

## ① 触摸节点在 dtbo 里的位置与原始值

### 1.1 请求文件状态（先说不存在的部分）

| 检查 | 结果 |
|---|---|
| `D:/Android/k60-ios/dtb/dtbo_a_fdt15.dtb` | 目录不存在（`D:/Android/k60-ios` 下没有 `dtb` 目录） |
| `cmd.exe /c "dir /s /b D:\dtbo_a_fdt15.dtb"` | `File Not Found` |
| `find E:/ -iname 'dtbo_a_fdt15.dtb'` | 无结果 |
| 全盘 FDT magic 扫描（D:/Android/k60-ios、E:/k60-work、E:/hackios/k60） | 只找到 live FDT、pong DT 和若干 UEFI/pong 参考 DTB；没有 raw K60 dtbo |

`D:/Android/k60-ios/AGENT-COORDINATION.md:826` 记录过 2026-10-27 存在 `dtb\` 目录（64 个 dtb，含 `dtbo_a_fdt*`），但该目录和 `D:/Android/k60-ios-backup-20261027` 现在都不在盘上。**因此 raw dtbo 的 `fragment@N` / `target` 路径无法给出，不能猜。**

### 1.2 实际解析的替代源

| 项 | 值 |
|---|---|
| 文件 | `E:/k60-work/reports/live-6033dbec-fdt.dtb` |
| 文件大小 | 919,210 bytes（`totalsize 0x000e06aa`） |
| FDT 版本 | `0x11`（17），last_comp `0x10`（16） |
| SHA-256 | `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8` |
| 来源 | 2026-11-02 从 adb 设备 `6033dbec`（K60）侧导出的 live merged FDT；已含 dtbo 应用后的节点 |

> 这是 **base + overlay 合并后的 FDT**，不是 raw overlay。节点路径和值可直接用于 ADT/驱动；raw overlay 的分片编号不可得。

### 1.3 触摸节点：`soc/spi@990000/xiaomi_touch@0`

节点 token 在 FDT 文件偏移 `0x2caac`。解析出的关键原始行（值为解析后）：

```text
soc/spi@990000/xiaomi_touch@0
  status             = "ok"
  compatible         = "xiaomi,m11a-spi"
  reg                = <0x0>                    # SPI CS0
  spi-max-frequency  = <0x00e4e1c0>             # 15,000,000 Hz = 15 MHz
  interrupt-parent   = <&tlmm>                  # phandle 0x3c
  interrupts         = <0x15 0x2008>            # GPIO 21, flags 0x2008
  pinctrl-names      = "pmx_ts_active", "pmx_ts_suspend"
  pinctrl-0          = <0x585>                  # mi_ts_active: gpio21, gpio20
  pinctrl-1          = <0x2f1 0x2f0>            # ts_int_suspend, ts_reset_suspend
  goodix,avdd-gpio   = <&tlmm 0x47 0x0>         # GPIO 71, active high
  goodix,iovdd-name  = "vdd"
  vdd-supply         = <&pm8350c_l2>            # phandle 0x301, ldoc2
  goodix,irq-gpio    = <&tlmm 0x15 0x2008>      # GPIO 21, flags 0x2008
  goodix,reset-gpio  = <&tlmm 0x14 0x0>         # GPIO 20, flags 0
  goodix,irq-flags   = <0x2>                    # falling edge
  goodix,panel-max-x = <0x3840>                 # 14400
  goodix,panel-max-y = <0x7d00>                 # 32000
  goodix,panel-max-w = <0xff>                   # 255
  goodix,panel-max-p = <0x1000>                 # 4096
  goodix,firmware-name = "goodix_firmware_m11a"
  goodix,config-name   = "goodix_cfg_group_m11a"
  goodix,touch-expert-array = <2 3 2 2 4 3 3 2 3 3 4 2>
  panel = <0x6a3 0x697>
```

属性 token 的 FDT 文件偏移（用于复核）：

| 属性 | prop token 偏移 | value 偏移 | 原始值（hex） |
|---|---:|---:|---|
| `compatible` | `0x2cad0` | `0x2cae0` | `78 69 61 6f 6d 69 2c 6d 31 31 61 2d 73 70 69 00`（`xiaomi,m11a-spi`） |
| `reg` | `0x2caec` | `0x2cafc` | `00 00 00 00`（0） |
| `spi-max-frequency` | `0x2cafc` | `0x2cb0c` | `00 e4 e1 c0`（0x00e4e1c0 = 15 MHz） |
| `interrupts` | `0x2cb1c` | `0x2cb2c` | `00 00 00 15 00 00 20 08`（21, 0x2008） |
| `goodix,avdd-gpio` | `0x2cb80` | `0x2cb90` | `00 00 00 3c 00 00 00 47 00 00 00 00`（phandle 0x3c, 71, 0） |
| `vdd-supply` | `0x2cba8` | `0x2cbb8` | `00 00 03 01`（phandle 0x301） |
| `goodix,irq-gpio` | `0x2cbb8` | `0x2cbc8` | `00 00 00 3c 00 00 00 15 00 00 20 08`（0x3c, 21, 0x2008） |
| `goodix,reset-gpio` | `0x2cbd0` | `0x2cbe0` | `00 00 00 3c 00 00 00 14 00 00 00 00`（0x3c, 20, 0） |
| `goodix,panel-max-x` | `0x2cbf8` | `0x2cc08` | `00 00 38 40`（14400） |
| `goodix,panel-max-y` | `0x2cc08` | `0x2cc18` | `00 00 7d 00`（32000） |
| `goodix,firmware-name` | `0x2cc38` | `0x2cc48` | `goodix_firmware_m11a\0` |
| `goodix,config-name` | `0x2cc5c` | `0x2cc6c` | `goodix_cfg_group_m11a\0` |
| `goodix,touch-expert-array` | `0x2cc80` | `0x2cc90` | `00 00 00 02 00 00 00 03 …`（12 个 u32） |

### 1.4 SoC 级节点（同一 live FDT）

| 节点路径 | compatible | `reg` | 关键属性 | node token 偏移 |
|---|---|---|---:|---:|
| `soc/spi@990000` | `qcom,spi-geni` | `<0x990000 0x4000>` | `interrupts = <0 0x25d 4>`（GIC SPI 605，level high）；`spi-max-frequency = 0x02faf080`（50 MHz 控制器上限）；`pinctrl-0 = <0x581 0x582>` | `0x2c8fc` |
| `soc/clock-controller@100000` | `qcom,cape-gcc` | `<0x100000 0x1f4200>` | `clock-names = "bi_tcxo", "sleep_clk"`；`clocks = <0x20 0x0 0x21>` | `0x36a4` |
| `soc/pinctrl@f000000` | `qcom,cape-pinctrl` | `<0xf000000 0x1000000>` | `phandle = 0x3c`（触摸节点 `interrupt-parent`/GPIO phandle） | `0x5b74` |
| `soc/rsc@17a00000` | `qcom,rpmh-rsc` | `<0x17a00000 0x10000 0x17a10000 0x10000 0x17a20000 0x10000 0x17a30000 0x10000>` | `qcom,drv-id = <0x2>`；`reg-names = "drv-0", "drv-1", "drv-2", "drv-3"` | `0x120ac` |
| `reserved-memory/aop_cmd_db_region@80860000` | `qcom,cmd-db` | `<0x0 0x80860000 0x0 0x20000>` | — | `0xb44` |

**关键结论：** K60 的触摸节点不是 `goodix,*` compatible，而是 Xiaomi 包装节点 `xiaomi,m11a-spi`；Goodix 型号只能从 `goodix_firmware_m11a` / `panel-max` 推断，未在硬件上确认。GENI SE 是 `spi@990000`（SE4），片选 `reg = <0>`（CS0）。

### 1.5 引脚 pinctrl 原始值

| pinctrl 节点 | phandle | pins | function | 配置 |
|---|---:|---|---|---|
| `mi_ts_spi_active` | `0x581` | `gpio16`, `gpio17`, `gpio18` | `qup4` | drive-strength 6, bias-disable |
| `mi_ts_cs_active` | `0x582` | `gpio19` | `qup4` | drive-strength 6, bias-pull-up |
| `mi_ts_spi_sleep` | `0x583` | `gpio16`, `gpio17`, `gpio18` | `gpio` | drive-strength 6, bias-disable |
| `mi_ts_cs_suspend` | `0x584` | `gpio19` | `gpio` | drive-strength 6, bias-pull-up |
| `mi_ts_active` | `0x585` | `gpio21`, `gpio20` | `gpio` | drive-strength 8, bias-pull-up |
| `ts_int_suspend` | `0x2f1` | `gpio21` | `gpio` | drive-strength 2, bias-pull-down |
| `ts_reset_suspend` | `0x2f0` | `gpio20` | `gpio` | drive-strength 2, bias-pull-down |

这组值给出 `pins = <16 17 18 19 21 20>` 的集合与顺序；16–18 是 SPI 三根线、19 是 CS、21 是 IRQ、20 是 RESET。**16/17/18 各自是 CLK/MOSI/MISO 的哪一种，pinctrl 组本身没有逐线命名**，见 ⑤。

## ② 9 个属性的 K60 取值表

pong 驱动的 `configuration()` 读取 `/arm-io/pong-touch` 的 9 个属性并硬断言（`zzzz…-pong-touch-console.patch:57-65`）：

```text
spi-base / tlmm-base / gcc-base / rsc-base / cmd-db-base / gpio-offset /
pins[6] / max-x / max-y
```

| # | 属性 | K60 取值 | 来源（dtbo 节点 + offset / 补丁:行号） | 置信度 |
|---:|---|---|---|---|
| 1 | `spi-base` | `0x00990000` | live FDT `soc/spi@990000` `reg[0]`，node `0x2c8fc`；pong 断言 `:63`；0240 `:120` | **高**（FDT + 同 SoC），未上机 |
| 2 | `tlmm-base` | `0x0f000000` | live FDT `soc/pinctrl@f000000` `reg[0]`，node `0x5b74`；pong 断言 `:63` | **高**（FDT）；必须与 `gpio-offset` 相加 |
| 3 | `gcc-base` | `0x00100000` | live FDT `soc/clock-controller@100000` `reg[0]`，node `0x36a4`；pong `:63`；0240 `:115` | **高**（FDT） |
| 4 | `rsc-base` | `0x17a20000` | live FDT `soc/rsc@17a00000` `reg[2]` + `qcom,drv-id=2`，node `0x120ac`；pong `:63`；0240 `:126`（`0x17a00000 + 2*0x10000`） | **地址高；可访问性零**（0246 / `ROUTE-A-18-DELTAS.md:13-15`） |
| 5 | `cmd-db-base` | `0x80860000` | live FDT `reserved-memory/aop_cmd_db_region@80860000` `reg[1]`，node `0xb44`；pong `:63`；0240 `:133` | **高**（FDT），从未运行时读取 |
| 6 | `gpio-offset` | `0x00100000` | pong 断言 `:64`；0240 `:110` 以 `TLMM_BASE=0x0f100000` 的扁平值反推。K60 DT 本身没有这个属性 | **中**（pong schema 推导；等价写法见下） |
| 7 | `pins[6]` | `<16 17 18 19 21 20>` | pong 断言 `:64-65`；live FDT pinctrl `mi_ts_spi_active`（16–18）、`mi_ts_cs_active`（19）、`goodix,irq-gpio`（21）、`goodix,reset-gpio`（20） | **高**（集合与顺序）；16–18 角色有歧义 |
| 8 | `max-x` | `14400`（raw，约 10×面板 px）/ `1440`（面板 px） | live FDT `goodix,panel-max-x=0x3840` @`0x2cbf8`；0240 `:172`（`ABS_MAX_X=14400`）；pong `:65` 是 `1080`（面板 px） | **中**（单位语义待定） |
| 9 | `max-y` | `32000`（raw，约 10×面板 px）/ `3200`（面板 px） | live FDT `goodix,panel-max-y=0x7d00` @`0x2cc08`；0240 `:173`（`ABS_MAX_Y=32000`）；pong `:65` 是 `2412`（面板 px） | **中**（单位语义待定） |

### 2.1 可直接填的 ADT 节点骨架（按 pong 的 schema）

如果 K60 继续复用 pong 的 `pong_goodix.c`（它按 `/arm-io/pong-touch` 查找），节点应发成：

```text
/arm-io/pong-touch {
    compatible = "pong,goodix-berlin-d";
    spi-base = <0x00990000>;
    tlmm-base = <0x0f000000>;
    gcc-base = <0x00100000>;
    rsc-base = <0x17a20000>;
    cmd-db-base = <0x80860000>;
    gpio-offset = <0x00100000>;
    pins = <16 17 18 19 21 20>;
    max-x = <14400>;
    max-y = <32000>;
};
```

**三个必须避免的坑：**

- `tlmm-base` 与 `gpio-offset` 是相加关系：`0x0f000000 + 0x100000 = 0x0f100000`。若写成 `tlmm-base=0x0f100000`，`gpio-offset` 必须为 `0`；二者不能同时给 `0x100000`。
- `rsc-base` 填 **`0x17a20000`**（drv-2），不是 `0x17a00000`（drv-0）。pong 的 `TCS(reg)=rsc+0xd00+reg` 直接以 drv-2 为基址。
- `max-x/max-y` 的 `14400/32000` 是 Goodix 报告的原始上限（量级上是面板 px 的 10 倍；0242 注释称“0.1 mm”，但该单位与 1440×3200 面板不一致，单位待核）；pong 原值 `1080/2412` 是面板像素。**不要混用**：用 pong 的 `pong_goodix.c` 原样时它按原始坐标缩放，填 `14400/32000`；若驱动先把 raw/10 变成面板 px，则填 `1440/3200`。见 ⑤。

### 2.2 附加参数（不在 9 项内，但上机/ADT 需要）

| 参数 | K60 值 | 来源 |
|---|---|---|
| SPI 片选 | `reg = <0>`（CS0） | live FDT `xiaomi_touch@0` @`0x2caec` |
| `spi-max-frequency` | `0x00e4e1c0` = 15 MHz；控制器上限 `0x02faf080` = 50 MHz | live FDT @`0x2cafc`；0241 头部“DT 的 spi-max-frequency 是 15 MHz” |
| 首次 bring-up SPI | 4 MHz（`K60_TOUCH_SPI_HZ`） | 0240 `:195`；0241 头部 |
| 触摸 IRQ | GPIO 21，flags `0x2008`（下降沿）；`goodix,irq-flags=2` | live FDT @`0x2cb1c`；0240 `:145` |
| SE 中断 | GIC SPI 605（`0x25d`），type 4；驱动全程轮询，不接这根中断 | live FDT `soc/spi@990000`；0240 `:116-118` |
| RESET | GPIO 20，DT flags 0；0240 低有效（0=复位，1=释放） | live FDT @`0x2cbd0`；0240 `:144` |
| AVDD | GPIO 71，高有效 | live FDT @`0x2cb80`；0240 `:146` |
| IOVDD | `pm8350c_l2` / `rpmh-regulator-ldoc2`，1.8 V，init-mode 4（LPM）；0240 投票 1.8 V / mode 7（HPM） | live FDT `regulator-pm8350c-l2`；0240 `:182-184` |
| 面板/坐标 | 面板 1440×3200；Goodix raw `panel-max` 14400×32000 | 0240 `:166-173`；0242 `:104-105` |
| 固件/配置名 | `goodix_firmware_m11a` / `goodix_cfg_group_m11a` | live FDT @`0x2cc38`/`0x2cc5c`；0242 头部 |
| 额外 Goodix 属性 | `panel-max-w=0xff`、`panel-max-p=0x1000`、`touch-expert-array=<2 3 2 2 4 3 3 2 3 3 4 2>`、`panel=<0x6a3 0x697>` | live FDT @`0x2cc18`…`0x2ccbc`；用途未核实 |

## ③ sweet 的 8 个 K60 触摸补丁：各做了什么、失败点在哪

> 这 8 个补丁是“试过什么/踩过什么”的证据，不是解法。作者结论：触摸仍未修好。

| 补丁 | 做了什么 | 关键值/改动 | 失败点/证据 |
|---|---|---|---|
| `0240-k60-touch-pins-rpmh.patch` | 拆出 `bsd/sys/k60_touch.h`、`k60_touch_pins.c`、`k60_touch_rpmh.c`；TLMM 引脚 + AVDD + pm8350c ldoc2 的 RPMh 投票；默认 stage 2 | TLMM `0x0f100000`（`:110`）；GCC `0x100000`（`:115`）；SE `0x990000`（`:120`）；RSC `0x17a00000` + drv2（`:126`）；cmd-db `0x80860000`（`:133`）；GPIO 16/17/18/19/20/21/71（`:140-146`）；IOVDD `ldoc2` 1800 mV / mode 7（`:182-184`） | 依赖 RSC 投票。0240 头部自称 2026-10-31 “drv-2 可读，DRV_ID=0x20700”，但 0246 明确说“RSC 一个寄存器都读不得：首次读 TCS 就整机死”。两者矛盾，未定因；RSC 是整条链的硬墙 |
| `0241-k60-touch-geni-spi.patch` | GCC 时钟投票 + RCG + QUPv3 SE4 的 GENI SPI 初始化/收发 | `0x62008` 位 6/7/8/9/14（`:102-111`）；halt `0x27004/0x27008/0x33000/0x3300c/0x274dc`；RCG `0x274e4/0x274e8`（`:118`）；SPI 4 MHz，packing `0x0007f8fe`/`0x000ffefe`（`:194-195`） | 三道闸门（vote 回读、halt bit31 全清、root clock 非 ROOT_OFF）不过就停在 SE 之前；**stage 3/4/5 从未在真机执行**（A1 HANDOFF:17）；时钟没真开时一次 SE 访问可挂住互连 |
| `0242-k60-touch-goodix.patch` | 实现 Berlin 与 GT9xx 两套 Goodix ABI；按“谁回得出校验和正确的数据”选 ABI；解析触点并交 `SweetHIDTouch` | Berlin：读 `0xf1`+4 字节地址+`0xff`，写 `0xf0`+地址；FW `0x10014`（28 B），IC info `0x10070`；GT9xx：`0x8140/0x814e/0x8150`；坐标 raw `14400×32000` → 面板 `1440×3200`（`:392`、`:423-424`） | 型号未在硬件确认（DT 只有 `xiaomi,m11a-spi` / `goodix_firmware_m11a`）；全仓库没有任何一条真机 `K60 TOUCH: ID:` / `goodix id ok` / 触点日志；两套都不答时打印 `abi none: the chip answers neither framing` |
| `0243-k60-touch-hid-thread.patch` | 线程、boot-arg 分级、把 0240-0242 串起来；默认 stage 2 | 分级 1/2/3/4/5；默认 stage 2（`:11-21`）；stage 4 读 ID 后 `k60_touch_done`（`:160-168`）；stage 5 才轮询 | 默认只到 stage 2，**不会读 ID**；stage 4/5 从未在真机执行（A1 HANDOFF:17）；任何失败只打印后 `thread exits`，不影响启动 |
| `0244-k60-rpmh-slot-probe.patch` | 在 `k60_touch_iovdd_on()` 里先做只读体检：打印 TCS 的 ctrl/enable/status/irqen；`k60rpmhprobe=1` 时到此为止，一个寄存器都不写 | 插入点在 `k60_rsc_map()` 之后（`:12-23`） | 仍是 RSC 读；如果整块 RSC 不可达，这个“只读体检”本身就可能整机死。后来 `0252` 修了另一处 `k60_rpmh_write()` 在 `ml_io_map()` 前读 TCS 的 map-order bug（A1 HANDOFF:32/100；`0252` 不在本次 8 个内） |
| `0245-k60-touch-irq-pullup-pins.patch` | 把 IRQ 引脚的 pull-down 改成 pull-up；在放开复位前再读一次 IRQ 电平并打印 | `K60_TOUCH_PIN_PULL_DOWN` → `PULL_UP`（`:11`）；新增 `irq before reset release %u`（`:21`） | IRQ 是开漏输出，没上拉读出来必然 0（`LOCKSCREEN-2026-10-28.md` “顺手修掉的三个坑”）；0240 原来的 pull-down 让 IRQ 判据失真。此补丁本身无成功记录 |
| `0246-k60-touch-skip-rpmh.patch` | 加 `k60rpmhoff=1`，整段跳过 RSC 投票，继续验证 GCC/SPI/Goodix | 注释原文：“这台机器上 RSC 一个寄存器都读不得：首次读 TCS 就整机死”（`:13`）；日志 `iovdd vote skipped (k60rpmhoff=1)`（`:22`） | 这是**绕过**不是修复：跳过 IOVDD 投票后芯片可能没上电，ID 读不到；A1 明确“IOVDD 是假设不是事实”（A1 HANDOFF:102） |
| `0248-k60-rsc-address-probe.patch` | `k60rscprobe=1` 只读探针：从 drv-2 的 `0x17a20000` 起读 `0x20000/0x20d00/0x20d14/0x20d1c/0x20d20/0x21000`，每次读前先刷盘 | `offsets[]`（`:34-35`），`ml_io_map(0x17a00000, 0x22000)`（`:38`） | 目的是分清“整个 RSC 块不可达”还是“只有 TCS 槽不可达”。若第一笔读就死，日志只留地址，无法继续；`LOCKSCREEN-2026-10-28.md` 说“读 RSC 第一个地址 0x17a00000 整机死，没有 panic”，所以是整块 RSC 不可达的强证据，但根因（XPU/电源域/互连）未定 |

**③ 的结论：** 0240–0243 的代码路径里，真机唯一通过的是 0240 的“只上电”引脚层（`LOCKSCREEN-2026-10-28.md`：“只上电那步通过”）；stage 3/4/5 从未执行，0242 从未读到 ID。0244/0246/0248 是侦察与绕过；0246 的 `k60rpmhoff=1` 是后续上机的唯一安全入口，但它同时把 IOVDD 供电变成假设。

## ④ 首次上机：先只跑到 stage 4（读 Goodix ID + report 地址，不碰 TCS/RPMh）

### 4.1 启动参数

```text
k60touchstage=4 k60rpmhoff=1 k60touchdelay=8 k60touchhz=4000000
```

如果树里有 `0251`（`k60touchid=1` 的 ID 摘要补丁），再加 `k60touchid=1`；没有 0251 时，stage 4 本身就会在 `k60_touch_goodix_probe(1)` 后 `k60_touch_done`，效果相同。

**不要**加 `k60rscprobe=1`；**不要**在 `k60rpmhoff=0` 的情况下把 `k60touchstage` 设到 2 或以上。`0246` 的 `k60rpmhoff=1` 会在 `k60_touch_iovdd_on()` 之前直接跳过整个 RSC 路径，`0248` 的探针也不会跑。

### 4.2 这条路径实际做什么

1. stage 1：配置 AVDD GPIO71、RESET GPIO20、IRQ GPIO21（0240 pins）。
2. stage 2：打印 `iovdd vote skipped (k60rpmhoff=1)`；**不映射 RSC、不读 TCS、不写 TCS**。
3. stage 3：GCC 投票 `0x62008` 五位 + RCG + 三条 halt 判据；不过就停在 SE 之前。
4. stage 4：把 SE4 `0x990000` 配成 SPI（4 MHz，FIFO，mode 0/8-bit），读 Goodix `0x10014` 固件版本 + `0x10070` IC info，找 `touch_address`；然后 `k60_touch_done(4)` 退出，**不轮询、不写 TCS、不投 RPMh**。

这正是“只读芯片 firmware 版本 + 找 report 地址，不碰 TCS/RPMh”的最小闭环。

### 4.3 判据日志行（全部以 `K60 TOUCH:` 开头）

| 日志行（grep） | 期望 | 判读 |
|---|---|---|
| `init: stage 4 (1 pins, 2 +iovdd, 3 +clocks, 4 +spi/id, 5 +poll), delay 8 s, spi 4000000 Hz, flush 1` | 参数解码正确 | 启动参数生效 |
| `stage 1: avdd gpio71, reset gpio20, irq gpio21` | 三个 GPIO 号正确 | 引脚层 |
| `powered: avdd=1 reset=1 irq level 0` | 上电完成；IRQ 电平只记录不判成败（0240 下拉配置常见 0；0245 上拉后可能 1） | 引脚层通过 |
| `iovdd vote skipped (k60rpmhoff=1)` | 出现 | **预期**，不是失败；RSC 零访问 |
| `stage 3: gcc 0x100000 window 0x70000, no SE access yet` | 出现 | 进入时钟层 |
| `gcc vote 0x… -> 0x…, bits 0x43c0` | `bits` 至少包含 `0x43c0`（位 6/7/8/9/14） | 五个投票位被接受 |
| `gcc halt m/s/se 0x…/0x…/0x…` | 三个值 bit31 全为 0 | 时钟真的在跑 |
| `clocks ready: …` | 出现 | stage 3 通过 |
| `se4 fw 0x102 version 2 protocol 1 (SPI=1)` | `+0x068 = 0x00000102`，protocol 1 | SE4 装的是 SPI 固件 |
| `se4 spi cfg word 0x4 mclk 0x51 (source 19200000 Hz / 5)` | `+0x048 = 0x51` | 4 MHz = XO/5 |
| `se4 pins gpio16-19 -> qup` | 出现 | 四根 SPI 线交给 QUP |
| `se4 status 0x0 fifo 64 words` | status 0，FIFO 64 字 | 引擎空闲 |
| `id: berlin fw chip "911" firmware "…" … sensor N` | Berlin 有应答 | 芯片 ID 读到了 |
| `id: berlin touch report at 0x…, command at 0x…, axes 14400 x 32000` | report 地址非 0 | 找到触点报告地址 |
| `abi berlin selected, axes 14400 x 32000, panel 1440 x 3200` | 出现 | **验收行**：Berlin ABI 选中 |
| `stage 4: goodix id ok, abi 1` | 出现 | stage 4 成功 |
| `stage 4 done (…), thread exits` | 出现 | 按 stage 4 正常收尾 |

失败/分支判据：

| 日志行 | 含义 | 下一步 |
|---|---|---|
| `pins failed` / `pins unavailable, stopping` | TLMM 引脚页映射/配置失败 | 查 `tlmm-base` + `gpio-offset` 是否等于 `0x0f100000`；不要动 RSC |
| `clocks not ready … stopping before SE` / `gcc refused N vote bit(s)` | GCC 投票或 halt 未过 | 查 `gcc-base=0x100000`、`0x62008` 五位、SE4 RCG；不要动 RSC |
| `geni: <problem>` | SE4 固件/SPI 配置失败 | 查 `se4 fw 0x102`、gpio16-19 是否 `qup4`；不要动 RSC |
| `abi none: the chip answers neither framing` | SE 正常但芯片不答 | 先怀疑 IOVDD：从 Android 热重启进 fastboot 再 boot（Android 已开 ldo2）；仍不答走平台供电/RSC，不再在驱动里硬试 |
| `goodix id failed, thread exits` | `k60_touch_goodix_probe` 失败 | 同上；不要为了“试一下”读 `0x17a00000` |

### 4.4 停止条件

出现 `stage 4 done` 或 `thread exits` 就停；不要在同一轮里加 `k60touchstage=5` 或 `k60rscprobe=1`。如果日志在 `gcc halt` / `se4 fw` 之前中断，最后一行就是嫌疑点（0241 的每一步都先刷盘）；不要用“再读一次 RSC”来排查。

## ⑤ 未知 / 需实机验证的项

| # | 项 | 现状 | 闭合方式 |
|---:|---|---|---|
| 1 | raw `dtbo_a_fdt15.dtb` 的实际内容 | 文件不存在；本表来自 live merged FDT，无法证明与 `dtbo_a_fdt15` 逐字节一致 | 从设备只读 dump `dtbo_a` 分区，解析 `dtbo_a_fdt15` 并对比本表 |
| 2 | RSC 0x17a00000 / 0x17a20000 可达性 | 0x17a00000 首读整机死（`LOCKSCREEN`）；0240 称 drv-2 可读、DRV_ID=0x20700，0246 称首读 TCS 死；根因未定 | 只用 0248 的只读探针；先确认 XPU/电源域/互连，不要写 TCS |
| 3 | `cmd-db-base` 与 `ldoc2` 条目 | live FDT 地址 `0x80860000` 已核；运行时从未读；cmd-db magic/entry 布局未验 | RSC 修好后先 `k60rpmhprobe=1` 只读，再 dump cmd-db |
| 4 | GCC/SE4 stage 3/4 | 从未在真机执行（A1 HANDOFF:17）；`se4 fw 0x102`/`mclk 0x51` 都是期望值 | 一次 `k60touchstage=4 k60rpmhoff=1` 启动，按 4.3 表判读 |
| 5 | Goodix 型号 / ABI | DT 只有 `xiaomi,m11a-spi` / `goodix_firmware_m11a`；Berlin vs GT9xx 未确认；无真机 ID 日志 | stage 4 读 `0x10014` / `0x8140`；看 `abi berlin` 或 `abi gt9xx` |
| 6 | IC info `+52/+54` 的语义 | 0242 按“坐标上限”用（14400×32000）；mainline 称 reserved；两者必有一误 | stage 4 打印原始 IC info，和 mainline `goodix_berlin` 对照 |
| 7 | `pins` 16/17/18 的角色 | pong 映射为 MISO/MOSI/CLK；0240 映射为 CLK/MOSI/MISO；pinctrl 组只写 `qup4`，不逐线命名 | QUP 模式下不影响；若走 bit-bang，按原理图/实测确认 |
| 8 | RESET 极性 | DT flags `0`；0240 低有效（0=复位，1=释放）；未用示波器确认 | 上机量 GPIO20 与芯片复位脚；或看 `irq before reset release` 与 ID 结果 |
| 9 | `max-x/max-y` 单位 | 14400/32000 是 Goodix raw（0242 注释称 0.1 mm，但量级更像 10×面板 px，未核）；1440/3200 是面板 px；pong 原值 1080/2412 是 px | 决定复用哪套驱动：pong `pong_goodix.c` 用 raw；K60 0242 先 raw/10 再 px |
| 10 | `k60rpmhoff=1` 时的 IOVDD 状态 | 假设 bootloader/Android 已开 pm8350c ldo2；冷启动是否成立未知 | Android 热重启进 fastboot 再 boot；对比冷启动 ID 结果 |
| 11 | SPI 15 MHz 的信号完整性 | DT 上限 15 MHz；0240 首次用 4 MHz；15 MHz 未上机 | ID 通过后再逐级升 `k60touchhz`，看误码/ID 失败 |
| 12 | ADT 节点路径与 schema | pong 驱动要 `/arm-io/pong-touch` 的 9 属性；K60 0240-0252 的 A1 方案用 `/k60-touch` 另一套 schema；当前仓库没有触摸节点 | 先决定复用 pong 驱动还是 K60 驱动；按对应 schema 发节点并让 `SecureDTLookupEntry` 路径一致 |
| 13 | `tlmm-base` + `gpio-offset` 的组合 | 0x0f000000 + 0x100000 = 0x0f100000（pong schema）；K60 0240 用扁平 0x0f100000 | 二者只能选一种；写 ADT 后 dump 校验和必须为 0x0f100000 |
| 14 | `rsc-base` 的语义 | pong 驱动要 drv-2 的 `0x17a20000`；0240 用 `0x17a00000 + 2*0x10000` | 填 pong ADT 时写 `0x17a20000`，不要写 `0x17a00000` |
| 15 | `goodix,panel-max-w/p`、`touch-expert-array`、`panel` phandles | live FDT 有值，但用途/是否必需未核实 | 先不填；等 ID/坐标通了再按厂商驱动逐项加 |

## 附录：复现与解析说明

- 环境里 `dtc`、`fdtdump`、Python `libfdt` 都不可用；本表用 Python 直接按 FDT 结构解析（`magic 0xd00dfeed`，`off_dt_struct 0x38`，`size_dt_struct 0xd1d40`，`off_dt_strings 0xd1d78`，`size_dt_strings 0xe932`）。
- live FDT 的 `totalsize=0x000e06aa`，文件大小 919,210 bytes；SHA-256 见 1.2。
- 请求的 raw dtbo 搜索命令与结果见 1.1；没有用 pong 的 DTB 值替代 K60 的 SoC 节点值，K60 的 `soc/spi@990000`、`soc/clock-controller@100000`、`soc/pinctrl@f000000`、`soc/rsc@17a00000`、`reserved-memory/aop_cmd_db_region@80860000` 均直接来自 live FDT。
- `D:/Android/k60-ios/firmware/history/mondrian-fdt.img` 也带 FDT magic，但其结构与 live FDT 不同（解析到 `0x1a44` 即出现非 FDT token），本表未采用它的任何数值。
