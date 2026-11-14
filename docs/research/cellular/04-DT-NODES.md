# 04 — 补 DT：四个 modem/IPA 节点的抄录、改写与零影响证明

> 任务来源：Lead 2026-11-14 批准（m00671），附三个硬条件。
> 交付物：`dts/mondrian.dts` 新增的第三块 `/{ }`，**229–390 行，192 行新增 / 0 行删除**
> （文件从 198 行 6157 B 变为 390 行 13024 B，sha256 `b82b4866649ce843110c63a2ef165ca951beca54fd63a236dfdba64b11ae1206`）。
> 本文是那 192 行的完整取证：每个值从哪来、改了哪几处、以及**为什么可以断言启动行为不变**。

---

## 0. 一句话结论

四个节点（`mpss-region`、`remoteproc-mss` + modem `glink-edge`、`qcom,ipa`）已按活 FDT **逐字面量抄录**进
`dts/mondrian.dts`；**没有任何节点带 `status`，没有任何节点带 `unixnu,adt-name`**；dtc 1.7.0 编译零警告；
ADT 在掩码掉 `random-seed` 后与基线**逐字节相同**（受控实验：同一 board 配置下，base dtb 与 new dtb 各生成一次），
DTB 层面**只多 12 个节点、不删一个节点、不改一个已有节点的属性**。
⇒ 这三个条件不是"我认为没影响"，而是"用同一套构建代码跑了对照实验，输出相同"。

---

## 1. 三个硬条件逐条对账

### 1.1 条件一：只加节点、不加 `status = "okay"`、不写 `unixnu,adt-name`

**机制层面**（`/opt/k60/trees/k60build/scripts/unixnu/devicetree.py`）：

- `:372` `hardware = [entry for entry in entries if 'unixnu,adt-name' in entry.properties and entry.enabled()]`
  —— **只有带 `unixnu,adt-name` 的节点才会被序列化进 ADT**。
- `hardware_properties()` 的白名单（`STRINGS` / `U32` / `U64` / `FLAGS` / `REFERENCES`）只对上面这批
  exported 节点生效。要加的四项不在其中，所以它们的属性**既不进 ADT，也不会触发任何 ADT 侧校验**。
- `enabled()` = 自身与所有祖先的 `status` 属于 {缺省, `okay`, `ok`}。

**实测层面**（新 dtb，用 `unixnu.devicetree.read_fdt` 解析）：

| 指标 | 基线 dtb | 新 dtb |
|---|---|---|
| 带 `unixnu,adt-name` 且 enabled 的节点 | `['intc', 'pong-audio', 'ufshc']` | `['intc', 'pong-audio', 'ufshc']`（完全相同） |
| 全树 `status` 属性个数 | 2 | 2（**没有新增任何 status**） |
| 全树 `unixnu,adt-name` 属性个数 | 3 | 3 |
| `arm_io_window(hardware)` | `(0x1000000, 0x17000000)` | `(0x1000000, 0x17000000)`（相同） |

⇒ 新增节点对 ADT 的输入集合**零贡献**：不新增 exported 节点、不新增 status、不移动 arm-io 窗口。

### 1.2 条件二：ADT 逐字节不变 —— 以及一个必须说清的陷阱

**先说要紧的：ADT 本身不是确定性的。**
`devicetree.py:310`：

    chosen = [('random-seed', os.urandom(256)), ('dram-base', struct.pack('<Q', dram_base)), ...]

同一个 DTB 连跑两次，ADT 的 sha256 就不同（实测 `d65beecc…` vs `0272fb3b…`，差异 256 字节全在 `[372, 628)`）。
所以**"两次生成 sha256 相等"既不可能也不该被当作判据**；正确判据是
**把 `random-seed` 的值域掩掉之后做结构比对**。

掩码区间不是猜的，是用 ADT 二进制解析出来的（`/tmp/dtcheck/offsets.py`；ADT 是小端 `<II>` / `<32sI>`，
用大端解析会直接 `struct.error`）：

| 属性 | 长度 | 值偏移 | 结束 |
|---|---|---|---|
| `random-seed` | 256 | **372** | **628** |
| `dram-base` | 8 | 664 | 672 |
| `dram-size` | 8 | 708 | 716 |
| `nvram-bank-size` / `-count` / `-current-bank` | 4 / 4 / 4 | 752 / 792 / 832 | — |
| `nvram-proxy-data` | 8192 | 872 | 9064 |
| `darwinboot-memory-size` | 8 | 9100 | 9108 |
| `root-matching` | 171 | 9144 | 9315 |

基线（从真实产物里取出的那份）与补 DT 后生成的 ADT：**总长都是 15736 B，都是 158 个属性，布局完全相同**。
⇒ 只有 `[372, 628)` 这 256 字节可能不同；实测差异 255 字节，正好落在该区间内。

**受控实验**（关键：把"DT 改动"与"board 配置差异"分开）
方法：同一个 device 目录、同一个 `Context`、同一个 `dt.generate()`，只换喂进去的 dtb。

| 项 | 基线 dtb | 改后 dtb |
|---|---|---|
| 文件 | `/tmp/dtw/base.dtb` | `/tmp/dtv5/new.dtb` |
| 大小 | 4024 B | 7810 B |
| sha256 | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` | `bdf3db0b179a780bff421c4eba0f9a56171263a9380f4918acd701be9ad9e9ea` |

> 基线 dtb 的 sha256 **等于** `E:\k60-work\artifacts\gpu-20261114d\build-manifest.json` 的 `components.dtb`，
> 说明本机 dtc + `include_dirs = ["soc:dts"]` 能逐字节复现真实构建的 DTB。

结果（基线 board 配置 = `/tmp/dtcheck/dev-baseline`，其 board.toml 取自 `git show 1381863f:board.toml`）：

| 比较 | 结果 |
|---|---|
| ADT(base) vs ADT(new) 长度 | 都是 15736 B |
| raw sha256 | 不同（`1df7f6fa…` vs `321fc61a…`） |
| raw 差异字节数 | 255，区间恰为 `(372, 627)` |
| **掩码 `[372,628)` 后 sha256** | 两者都是 `b0dc4beed52129983cfdb00f933347be6b22aa9909502741eb63ba27a7a3dd5f` → **IDENTICAL** |
| 掩码后 vs 真实产物基线 | 相等（`masked(real) == masked(base) == True`） |

真实产物基线：`E:\k60-work\artifacts\gpu-20261114d\boot.img` 的 ramdisk 段
（该段 sha256 `3513f992…` 与 manifest `components.payload` 一致）里的
`::EFI/UniXNU/Payloads/kernel.macho.adt` = 15736 B，sha256
`dd1b9da18f789292716c3ca8d804eb27e0a4acef69184195614a6a9bb728ab30`（与 manifest `components.adt` 一致）。

**分支自己的 board 配置**（`-D /mnt/e/hackios/k60-cellular`）同样跑一遍：掩码后 base 与 new 也相同
（`5ccb5d0a7e3e18032caaaa4eb0b4a8fff80681aaceae44ff36d16f8a74ad4610`）。与真实产物相比 258 字节不同：
**255 字节在 `random-seed`，剩下 3 字节在 `14612..14620`**。

那 3 字节是什么？把两份 ADT 结构化成文本后 `diff -u`，**只有一个 hunk**：

    ` -132,7 +132,7 `
           pins = <100000001100000012000000130000001500000014000000>
    -      bitbang-pins = <10000000110000001200000013000000>
    +      bitbang-pins = <11000000120000001000000013000000>

即 `[adt.arm-io.pong-touch.bytes] bitbang-pins`。**这是 cellular 分支 board.toml 相对 gpu-yibiya 基线的既有差异
（触摸 MISO 引脚排列），与本次 DT 改动无关** —— `git diff main...HEAD -- board.toml` 为空，说明分支的
board.toml 与 main 一致，差异在 gpu 那次构建所用的 board 上。

> **诚实点**：`dd1b9da1…` 是**某一次**含随机 seed 的构建的 sha256，掩码后的 ADT 永远不可能等于它。
> 所以"ADT 不变"的严格表述是：**在相同 board 配置下，补 DT 前后生成的 ADT 在掩码 `random-seed` 后完全相同**。
> 这一条已用受控实验证明，而不是"我看了一遍代码觉得不会变"。

### 1.3 条件三：只加这四个

新增节点共 **12 个**（4 个父节点 + 8 个子节点；子节点是父节点的属性结构的一部分，不是额外设备）：

1. `/mpss-region@8bc00000`（活树 `/reserved-memory/mpss_region@8bc00000`）
2. `/remoteproc-mss@4080000`（活树 `/soc/remoteproc-mss@04080000`）
   - `/remoteproc-mss@4080000/glink-edge`（modem 的 GLINK 边，`qcom,remote-pid = <1>`）
     - `.../glink-edge/qcom,modem_qrtr`（`IPCRTR`，QRTR 传输）
     - `.../glink-edge/qcom,modem_ds`（`DS`）
3. `/qcom,ipa@3e00000`（活树 `/soc/qcom,ipa@3e00000`）
   - `.../qcom,smp2p_map_ipa_1_out`、`.../qcom,smp2p_map_ipa_1_in`
   - `.../ipa_smmu_ap`、`.../ipa_smmu_wlan`、`.../ipa_smmu_uc`、`.../ipa_smmu_11ad`

**没有**加：`smp2p-modem`、`ipa_fw_region`、`ipa_gsi_region`、`linux,cma`、apps-smmu、rpmh 时钟控制器、
PM8350C regulator 节点。它们只作为"被省略的引用目标"出现在第 4 节的表里。

---

## 2. 抄录来源：可复现的二进制与文本

| 层 | 对象 | 大小 | 校验 |
|---|---|---|---|
| 设备 | `/sys/firmware/fdt` dump（serial 6033dbec） | 919210 B | sha256 `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`，md5 `d2c760e0dc6112c3a607e160a10e5386`，sha1 `499f307e7b190cdd693a1baeccbb9867927f6b18` |
| 主机副本 | `E:\k60-work\reports\live-6033dbec-fdt.dtb` | 919210 B | 同上（同一份二进制） |
| 反编译文本 | `dtc -I dtb -O dts` | 18920 行 | sha256 `26b99d68a2e08f3ead46263e96fcebe9487c0456ddd2331445166ba4fa2d7027` |

该反编译文本有三个互为独立的副本，sha256 完全一致：`/tmp/dtw4/frombin.dts`（本次从二进制重新反编译）、
`/tmp/k60-live-fdt.dts`（早先的反编译）、`E:\k60-work\scratch\audio-work\live-fdt.dts`。

> **更正 `02-DT-TRUTH.md` 的一处记录**：`02` 里写的活 FDT sha256
> `da19d6bb1423e571c2fff93ef341e2d6b7b8b6668512da7a981551de32c4b941` **不可复现**。
> 全盘搜 919210 字节的文件只有上面这一份，`/e/k60-work` 全盘 grep `da19d6bb` 零命中。
> 尺寸 919210 是对的，sha256 是错的（很可能当时对 `adb shell` 的输出做过换行/编码转换后才算的）。
> 本文及后续一律以 `95c02052…` 为准。

活 FDT 的形态（引用节点位置时用这些行号，行号基于 `/tmp/k60-live-fdt.dts`）：
4206 个节点；root 子节点依次为 `chosen, memory, ddr-regions, reserved-memory, aliases,
sram@17D09400, firmware, cpus, idle-states, cluster-device, soc, __symbols__, hypervisor`；`/soc` 下 574 个子节点。

| 节点 | 活 FDT 行号 |
|---|---|
| `/reserved-memory/mpss_region@8bc00000` | 173–177 |
| `/soc/remoteproc-mss@04080000`（含 glink-edge / modem_qrtr / modem_ds） | 11309–11351 |
| `/soc/qcom,ipa@3e00000`（含 4 个 ipa_smmu_* 子节点） | 12129–12236 |

---

## 3. 四条机械改写（逐条给原文）

### 改写 1：`/soc` 是 1-cell 地址空间，本仓没有 `/soc` 容器

活树：`/` 是 `#address-cells = 2` / `#size-cells = 2`，而 **`/soc` 是 `#address-cells = 1` / `#size-cells = 1`**，
`ranges = <0x00000000 0x00000000 0xffffffff>`（1:1 恒等映射）。所以活树里
`reg = <0x4080000 0x10000>` 是 1+1 cell。

本仓 `dts/mondrian.dts` **没有 `/soc` 容器**（既有的 `adsp-region@9fd00000`、`remoteproc-adsp@3000000`
都直接挂根），`sm8475.dtsi` 里也没有。因此：

    活树： reg = <0x4080000 0x10000>;                      // /soc 内，1+1
    本仓： reg = <0x00 0x4080000 0x00 0x10000>;            // 根下，2+2

> 这是**唯一**会造成"字节不同"的地方；凡含 `reg` 的节点都做了同样加宽，写法与既有
> `adsp-region@9fd00000 { reg = <0x00 0x9fd00000 0x00 0x3100000>; }` 一致。
> `qcom,ipa` 的两个 reg 区间（`ipa-base` 0x84000、`gsi-base` 0xfc000）同样加宽成 4 组 cell。

### 改写 2：丢弃悬空 phandle 引用

活树里这些属性指向的节点，本仓一个都没有：

| phandle | 活树里的目标 | 本仓有吗 |
|---|---|---|
| `0x20` | `/soc/rsc@17a00000/qcom,rpmhclk` | 无 |
| `0x1e` | `/soc/rsc@17a00000/rpmh-regulator-cxlvl/regulator-pm8350c-s6-level` | 无 |
| `0x9c` | `.../rpmh-regulator-msslvl/regulator-pm8350c-s4-level` | 无 |
| `0x8c` | `/soc/power-controller@c300000` | 无 |
| `0x46` / `0x5a` / `0x49` | `interconnect@1` / `interconnect@1700000` / 另一条 NoC | 无 |
| `0x5b` | `/soc/apps-smmu@15000000` | 无 |
| `0x9e` | `/reserved-memory/linux,cma` | 无 |
| `0xb5` | `/reserved-memory/ipa_gsi_region@8b910000` | 无 |
| `0xb6` / `0xb7` | `/soc/qcom,smp2p-modem/qcom,smp2p-ipa-1-{out,in}` | 无 |
| `0x9f` | `/soc/qcom,smp2p-modem/slave-kernel` | 无 |
| `0x01` | `/soc/interrupt-controller@17100000` | **有**（`sm8475.dtsi` 的 `&intc`） |
| `0x8f` | `/soc/qcom,ipcc@ed18000` | **有**（`mondrian.dts` 的 `&ipcc`） |
| `0x9d` | `/reserved-memory/mpss_region@8bc00000` | **本次新建** |

规则：**整个属性都是悬空引用的，属性整体删掉，绝不留占位值**；能兑现的两个引用保留为
`<&ipcc …>` 与 `<&mpss_region>`。

被整体省略的属性（逐条）：

- `remoteproc-mss`：`clocks = <&rpmhclk 0>`、`cx-supply = <&pm8350c_s6>`、`mx-supply = <&pm8350c_s4>`、
  `qcom,qmp = <&power_controller>`、`interconnects = <…>`、`qcom,smem-states = <&smp2p_modem_stop 0>`
- `remoteproc-mss`：`interrupts-extended`（19 个 cell，见下）
- `qcom,ipa`：`memory-regions = <&ipa_gsi_region>`、`clocks = <&rpmhclk 0x16>`、`interconnects = <…>`
- `qcom,smp2p_map_ipa_1_out`：`qcom,smem-states = <&smp2p_ipa_1_out 0>`
- `qcom,smp2p_map_ipa_1_in`：`interrupts-extended = <&smp2p_ipa_1_in 0 0>`
- 四个 `ipa_smmu_*`：`iommus = <&apps_smmu …>`
- 所有节点：`phandle`

**`interrupts-extended` 单独说明**（唯一一处"部分可兑现却整体省略"的属性）：19 个 cell 解码为

    <0x01 0x00 0x108>                              → GIC SPI 0x108（这一个本仓能兑现）
    <0x9f 0x00 0x00> <0x9f 0x02 0x00>              → smp2p-modem / slave-kernel（本仓无此节点）
    <0x9f 0x01 0x00> <0x9f 0x03 0x00> <0x9f 0x07 0x00>

6 个中断里 5 个指向 `smp2p-modem`，只留 GIC 那一条会让 `interrupt-names`（6 项）与中断表（1 项）
长度不匹配，比省略更危险。**所以 `interrupt-names` 保留（它固定了厂商的六路顺序，纯字符串、无引用），
`interrupts-extended` 整体省略**，并在 dts 注释里写明"第 6 个是 GIC SPI 0x108"。

### 改写 3：`qcom,ipa` 补 `interrupt-parent = <&intc>`

活树里 `qcom,ipa` 的 `interrupts = <0x00 0x28e 0x04 0x00 0x1b0 0x04>` 是相对 `/soc` 的
`interrupt-parent`（`/soc` 上继承 GIC）。本仓节点挂在根下，没有可继承的 `interrupt-parent`，
所以显式写 `interrupt-parent = <&intc>`。**这是新增属性，不是抄录属性**，因此单列一条。

### 改写 4：节点名去掉前导零、下划线改连字符（为了 dtc 零警告）

活树名 `remoteproc-mss@04080000` / `mpss_region@8bc00000`。照抄会得到：

    /tmp/dtw3/variant.dts:250.42-283.4: Warning (unit_address_format):
      /remoteproc-mss@04080000: unit name should not have leading 0s

本仓改用 `remoteproc-mss@4080000`、`mpss-region@8bc00000`（下划线在 DT 节点名里也是非法的）。
**只是节点名变了，`reg` 与所有属性值不变**；节点名不参与任何匹配（驱动匹配用 `compatible`）。
---

## 4. 逐属性对照与省略表

统计口径：属性个数（不含 dtc 自动生成的 name 属性）。

| 节点 | 活 FDT | 本仓 | 省略 | 新增 |
|---|---|---|---|---|
| `/reserved-memory/mpss_region@8bc00000` | 3 | 3 | 0（只有 `phandle` 换成新编号） | 0 |
| `/soc/remoteproc-mss@04080000` | 19 | 10 | 9 | 0 |
| `…/glink-edge` | 8 | 8 | 0（`mboxes` / `interrupt-parent` 的 phandle 重编号） | 0 |
| `…/glink-edge/qcom,modem_qrtr` | 3 | 3 | 0（**逐字节相同**） | 0 |
| `…/glink-edge/qcom,modem_ds` | 2 | 2 | 0（**逐字节相同**） | 0 |
| `/soc/qcom,ipa@3e00000` | 59 | 56 | 4 | 1（`interrupt-parent`） |
| `…/qcom,smp2p_map_ipa_1_out` | 3 | 2 | 1 | 0 |
| `…/qcom,smp2p_map_ipa_1_in` | 3 | 2 | 1 | 0 |
| `…/ipa_smmu_ap` | 8 | 6 | 2 | 0 |
| `…/ipa_smmu_wlan` | 4 | 2 | 2 | 0 |
| `…/ipa_smmu_uc` | 5 | 3 | 2 | 0 |
| `…/ipa_smmu_11ad` | 6 | 4 | 2 | 0 |

**逐字面量完全保留的"硬件事实"属性**（本次取证最值钱的部分，一个值都没改）：

- modem 身份与固件入口：`compatible = "qcom,cape-modem-pas"`、`reg = 0x04080000 / 0x10000`、
  `reg-names = "cx", "mx"`、`clock-names = "xo"`、`qcom,smem-state-names = "stop"`
- 电压/电流上限：`cx-uV-uA = <0x180 0x186a0>`、`mx-uV-uA = <0x180 0x186a0>`（384 mV / 100 mA）
- 互联路径名：`interconnect-names = "rproc_ddr", "crypto_ddr"`
- 六路中断名：`wdog, fatal, handover, ready, stop-ack, shutdown-ack`
- GLINK 边：`qcom,remote-pid = <1>`、`transport = "smem"`、`mbox-names = "mpss_smem"`、
  `interrupts = <2 0 1>`、`label = "modem"`、`qcom,glink-label = "mpss"`
- **QRTR 通道**：`qcom,glink-channels = "IPCRTR"`、`qcom,low-latency`、
  **`qcom,intents = <0x800 5 0x2000 3 0x4400 2>`**（三组意图：2 KiB×5、8 KiB×3、17 KiB×2）
- IPA：`reg = 0x3e00000/0x84000 + 0x3e04000/0xfc000`、`reg-names = "ipa-base", "gsi-base"`、
  `pas-ids = <0x0f>`、`firmware-names = "ipa_fws"`、`qcom,ipa-cfg-offset = <0x140000>`、
  `interrupts = <0 0x28e 4 0 0x1b0 4>`、`interrupt-names = "ipa-irq", "gsi-irq"`、
  `qcom,ipa-hw-ver = <0x16>`（IPAv4.5）、`qcom,ipa-hw-mode = <0>`（GSI 模式）、
  `qcom,platform-type = <1>`、`qcom,ee = <0>`、`qcom,entire-ipa-block-size = <0x200000>`
- IPA 的 21 个布尔开关与 20 余个数值属性（bus vectors `MIN/SVS2/SVS/NOMINAL/TURBO`、
  `throughput-threshold = <2000 4000 8000>`、`tx-wrapper-cache-max-size = 0x190`、
  `max_num_smmu_cb = 4`、ULSO ip-id 区间等）
- 四个 IPA SMMU 上下文库的 `compatible`、`qcom,iommu-dma`、
  `qcom,iommu-dma-addr-pool = <0x20000000 0x20000000>`、
  `qcom,additional-mapping = <0x146a8000 0x146a8000 0x2000>`、`qcom,ipa-q6-smem-size = <0x9000>`、
  `dma-coherent`、`qcom,shared-cb`、`qcom,iommu-group`

---

## 5. DTB 层面的差异（节点集合）

用 `unixnu.devicetree.read_fdt()` 解析两份 dtb（注意它要 **bytes**，不是 `Path`），逐节点比对：

| 指标 | 基线 | 新 |
|---|---|---|
| 节点总数 | 27 | 39 |
| 删除的节点 | — | **`[]`（零删除）** |
| 已有节点上变更的属性数 | — | **0** |
| 新增节点 | — | 12（§1.3 那 12 个） |

新 dtb 的 phandle 分配（dtc 自动）：`0x01 syscon@1f40000`、`0x02 smem-region@80900000`、`0x03 hwlock`、
`0x04 interrupt-controller@17100000`、`0x05 adsp-region@9fd00000`、`0x06 mailbox@ed18000`、
`0x07 mpss-region@8bc00000`。

root 子节点顺序（追加在末尾，既有顺序不变）：
`cpus, psci, interrupt-controller@17100000, memory@900000000, pong-audio, ufs@1d84000,
smem-region@80900000, syscon@1f40000, hwlock, smem, mailbox@ed18000, adsp-region@9fd00000,
remoteproc-adsp@3000000, smp2p-adsp, pmic-glink, mpss-region@8bc00000, remoteproc-mss@4080000, qcom,ipa@3e00000`

---

## 6. dtc 零警告

    $ dtc -I dts -O dtb -o /tmp/dtv5/new.dtb -i <soc:dts> dts/mondrian.dts
    rc = 0
    stdout = (空)
    stderr = (空)

DTC 1.7.0。**零警告、零错误**，所以构建日志里不会出现新的噪音，也不会因为将来加 `-Werror` 而失败
（当前 `devicetree.py:408` 的调用没有 `-Werror`，但保持零警告仍然是对的）。

---

## 7. 复现命令

    # 1) 基线 dtb（应当逐字节等于 gpu-20261114d 的 components.dtb）
    cp dts/mondrian.dts /tmp/dtw/base.dts
    dtc -I dts -O dtb -o /tmp/dtw/base.dtb -i /mnt/e/hackios/UniXNU-sm8475-common/dts /tmp/dtw/base.dts
    sha256sum /tmp/dtw/base.dtb     # 2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd

    # 2) 改后 dtb（零警告）
    dtc -I dts -O dtb -o /tmp/dtv5/new.dtb -i /mnt/e/hackios/UniXNU-sm8475-common/dts dts/mondrian.dts
    sha256sum /tmp/dtv5/new.dtb     # bdf3db0b179a780bff421c4eba0f9a56171263a9380f4918acd701be9ad9e9ea

    # 3) 从真实产物里取出基线 ADT（证明比对对象是真产物，不是我造的）
    dd if=boot.img of=/tmp/payload.img bs=4096 skip=136 count=49152   # k_off=4096, r_off=557056
    mtype -i /tmp/payload.img ::EFI/UniXNU/Payloads/kernel.macho.adt > /tmp/adt-baseline.bin
    sha256sum /tmp/adt-baseline.bin # dd1b9da18f789292716c3ca8d804eb27e0a4acef69184195614a6a9bb728ab30

    # 4) 受控实验：同一 board 配置，分别喂 base.dtb 与 new.dtb
    python3 /tmp/dtcheck/controlled.py
    #   ADT(base) 15736 B, ADT(new) 15736 B
    #   raw 差 255 字节，区间 (372, 627)
    #   masked 都是 b0dc4beed52129983cfdb00f933347be6b22aa9909502741eb63ba27a7a3dd5f

    # 5) 节点集合差异
    python3 /tmp/dtcheck/nodediff.py           # added 12, removed [], changed 0

> 设备侧不参与：补 DT 全程离线完成。设备当时在 fastboot（`fastboot devices` = `6033dbec fastboot`）。

---

## 8. 诚实清单

| 项 | 状态 |
|---|---|
| ADT 逐字节不变 | **已证明，但必须带掩码条件**：`random-seed` 是 `os.urandom(256)`，ADT 本身不确定；判据是"掩码后相同"。raw sha256 永远不会两次相等，也永远不会等于 manifest 里的 `dd1b9da1…` |
| 真实产物 vs 分支 board 的 3 字节差异 | **不是本次改动造成的**：是 `bitbang-pins`（触摸引脚）；分支 board.toml 与 main 一致，差异来自 gpu-yibiya 那次构建所用的 board 配置 |
| 活 FDT sha256 | `02-DT-TRUTH.md` 记的 `da19d6bb…` **不可复现**，已更正为 `95c02052…`；尺寸 919210 无误 |
| `mpss_region` 的 306 MiB 是否够 modem 用 | **未验证**。`0x13200000` 是 DT 声明值，`modem.mdt` 的 30 个 PT_LOAD 段恰好覆盖 `0x8bc00000..0x9ee00000`，与声明值吻合；但"够不够"取决于固件运行期分配，DT 不描述 |
| IPA 的 ring 几何 | **仍未取到**。DT 只给 `ipa-hw-ver = 0x16`（IPAv4.5）与 EE / 平台类型，ring 深度是驱动代码里的寄存器表（`03-SCOPE.md` §9 已列此缺项） |
| `qcom,intents` 是否只有三组 | **未验证**。DT 只有 3 组，运行时对端可能通告更多；需要 GLINK 通道建立后核对 |
| 这些节点被驱动 probe 了吗 | **没有**。XNU 侧 cellular 代码 0 行，`drivers/PongCellular/` 只有 README；节点纯文档性质 |
| 启动行为是否变化 | **预期不变**（ADT 不变 = bootloader 看到的设备树不变；DTB 里多出的节点没有任何驱动认领）。**但未上机实测** —— 上机需 Lead 排队 + 用户明确同意 |
| 设备验证 | **未做**。设备当时在 fastboot，补 DT 全程离线 |

