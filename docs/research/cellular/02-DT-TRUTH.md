# 02 — DT 真相：modem / IPA / QRTR 在设备树里到底写了什么

> 取证对象：设备实机 `/sys/firmware/devicetree/base`（活 FDT）
> 全量 FDT dump：`su -c 'cat /sys/firmware/fdt'` = **919,210 字节**，
> sha256 `da19d6bb1423e571c2fff93ef341e2d6b7b8b6668512da7a981551de32c4b941`
> 交叉校验：`E:\hackios\uefi-mondrian\Platforms\Xiaomi\mondrianPkg\FdtBlob\sm8475-xiaomi-mondrian.dtb`
> = 480,692 字节，md5 `a977423fca405512f6d333a955c9f970`（同源不同构建，见 §8）
>
> **方法说明**：本机没有 `dtc`，也没有 `fdtdump`，python 无 `libfdt`。
> 所以本文件**不做反编译**，全部用 `od -An -tx1` 读原始字节后**按大端 cell 手工解析**。
> 每条都给出节点路径 + 属性名 + 字节原文。

---

## 0. 一句话结论

设备树把 modem 描述成**一个 SoC 内部的 PAS 远程处理器**（`/soc/remoteproc-mss@04080000`），
它的固件被 PAS 搬进 `/reserved-memory/mpss_region@8bc00000`（306 MiB），
启动/停止握手走 **IPCC 中断 + smp2p**，与 AP 的通信通道是 **GLINK over SMEM 的 `IPCRTR` 逻辑通道**；
数据面是 **IPA**（`/soc/qcom,ipa@3e00000`）把 modem 的 WAN 流量转成 `rmnet` 接口。
**DT 里没有任何"外挂 modem"的总线节点**（无 PCIe、无 USB、无 SPI 上的 modem）。

---

## 1. modem 主节点：`/soc/remoteproc-mss@04080000`

### 1.1 属性字节原文

```
$ adb -s 6033dbec shell 'su -c "od -An -tx1 -c /sys/firmware/devicetree/base/soc/remoteproc-mss@04080000/compatible"'
 71 63 6f 6d 2c 63 61 70 65 2d 6d 6f 64 65 6d 2d 70 61 73 00
   q   c   o   m   ,   c   a   p   e   -   m   o   d   e   m   -   p   a   s  \0
```

→ `compatible = "qcom,cape-modem-pas"`。**`cape` 是 SM8475 平台的 modem 子系统代号**，
`pas` 说明它由 PAS（Peripheral Authentication Service，即 TZ 侧固件加载服务）驱动。

```
$ ... /remoteproc-mss@04080000/reg
 00 00 00 00 04 08 00 00  00 00 00 00 00 01 00 00
$ ... /remoteproc-mss@04080000/reg-names
 63 78 00 6d 78 00        → "cx\0mx\0"
$ ... /remoteproc-mss@04080000/status
 6f 6b 00                 → "ok\0"
```

| 属性 | 值 | 解析 |
|---|---|---|
| `reg` | `0x0000000004080000` + `0x0000000000010000` | 基址 **0x04080000**，窗口 **64 KiB** |
| `reg-names` | `"cx"`, `"mx"` | 两路电源域的寄存器窗口名 |
| `status` | `"ok"` | 已启用 |

**0x04080000 在 SoC 外设地址空间里**（远低于 4 GiB DDR 起点 0x90000000，也低于所有 DDR 低地址区）。
这是"modem 是 SoC 内部子系统"最直接的地址学证据。

### 1.2 供电轨

```
$ ... /remoteproc-mss@04080000/cx-supply   → <0x1e>
$ ... /remoteproc-mss@04080000/mx-supply   → <0x9c>
```

phandle 解析（全树扫描后）：

| phandle | 指向 | 含义 |
|---|---|---|
| `0x1e` | `/soc/rsc@17a00000/rpmh-regulator-cxlvl/regulator-pm8350c-s6-level` | **CX 轨 = PM8350C S6**（level regulator） |
| `0x9c` | `/soc/rsc@17a00000/rpmh-regulator-msslvl/regulator-pm8350c-s4-level` | **MX 轨 = PM8350C S4**（`msslvl` = MSS level） |

→ modem 的供电由 **PM8350C 两颗 SMPS（S6/S4）** 提供，经 RPMh 电压电平接口调压。
XNU 侧要拉起 modem，这两轨必须先按 DT 里的 `cx-uV-uA`/`mx-uV-uA` 表设好电压，
否则 PAS 会失败（TZ 拒绝给未上电的子系统做 auth-and-reset）。

### 1.3 内存区绑定

```
$ ... /remoteproc-mss@04080000/memory-region
 00 00 00 9d  00 00 00 9e
```

| phandle | 指向 | 用途 |
|---|---|---|
| `0x9d` | `/reserved-memory/mpss_region@8bc00000` | **固件加载区**（306 MiB） |
| `0x9e` | `/reserved-memory/linux,cma` | 允许 DMA 进 CMA（modem 有 64-bit DMA 需求时用） |

### 1.4 中断与握手

```
$ ... /remoteproc-mss@04080000/interrupt-names
 77 64 6f 67 00 66 61 74 61 6c 00 68 61 6e 64 6f 76 65 72 00
 72 65 61 64 79 00 73 74 6f 70 2d 61 63 6b 00 73 68 75 74 64 6f 77 6e 2d 61 63 6b 00
→ "wdog\0fatal\0handover\0ready\0stop-ack\0shutdown-ack\0"

$ ... /remoteproc-mss@04080000/interrupts-extended（大端 cell 原文，节选）
 <&gic 1 0x108> <&ipcc 0x9f 0 0> <&ipcc 0x9f 0 1> <&ipcc 0x9f 0 2>
 <&ipcc 0x9f 0 3> <&ipcc 0x9f 0 7>
```

| 中断名 | 来源 | 解析 |
|---|---|---|
| `wdog` | GIC SPI **0x108 = 264** | 看门狗 |
| `fatal` | IPCC client 0, signal **0** | 致命错误 |
| `handover` | IPCC client 0, signal **1** | 固件交接 |
| `ready` | IPCC client 0, signal **2** | 就绪 |
| `stop-ack` | IPCC client 0, signal **3** | 停止确认 |
| `shutdown-ack` | IPCC client 0, signal **7** | 关机确认 |

`&ipcc` = phandle `0x9f` = `/soc/qcom,ipcc@ed18000`（基址 **0xed18000**，见 `dts/mondrian.dts` 里已有的
`ipcc: mailbox@ed18000` 节点 —— **这一块 XNU 侧已经描述过了**）。

```
$ ... /remoteproc-mss@04080000/qcom,qmp        → <0x8c>
$ ... /remoteproc-mss@04080000/qcom,smem-states → <0xa0 0x0>
$ ... /remoteproc-mss@04080000/qcom,smem-state-names → "stop\0"
```

| phandle | 指向 | 用途 |
|---|---|---|
| `0x8c` | `/soc/power-controller@c300000` | AOSS qmp（给子系统发 power-up/down 请求） |
| `0xa0` | `/soc/qcom,smp2p-modem/master-kernel` | **停止确认走 smp2p 位**，不走中断 |

→ **启动时序**：smp2p 置位 → IPCC `ready` → 固件跑起来；
**停止时序**：写 `smem-states` → 等 IPCC `stop-ack`。

### 1.5 GLINK 边：与 AP 的实际通信通道

```
$ ... /remoteproc-mss@04080000/glink-edge/transport          → "smem\0"
$ ... /remoteproc-mss@04080000/glink-edge/qcom,remote-pid     → <0x01>
$ ... /remoteproc-mss@04080000/glink-edge/qcom,glink-label    → "mpss\0"
$ ... /remoteproc-mss@04080000/glink-edge/label               → "modem\0"
$ ... /remoteproc-mss@04080000/glink-edge/mbox-names          → "mpss_smem\0"
$ ... /remoteproc-mss@04080000/glink-edge/interrupts          → <0x02 0x00 0x01>
```

| 属性 | 值 | 含义 |
|---|---|---|
| `transport` | `"smem"` | 走共享内存 FIFO（**不是** MHI、不是 SMD） |
| `qcom,remote-pid` | `1` | 远端 host id = 1（AP 是 0） |
| `qcom,glink-label` | `"mpss"` | GLINK 边名 |
| `label` | `"modem"` | 逻辑名 |
| `mbox-names` | `"mpss_smem"` | 邮箱通道名 |
| `interrupts` | `(2, 0, 1)` | GIC SPI 2，触发类型 1（上升沿） |

#### 子节点 `qcom,modem_qrtr` —— 这就是 QRTR 的传输节点

```
$ ... /glink-edge/qcom,modem_qrtr/compatible
 71 63 6f 6d 2c 67 6c 69 6e 6b 2d 63 68 61 6e 6e 65 6c 73 00 ... 
$ ... /glink-edge/qcom,modem_qrtr/qcom,glink-channels
 49 50 43 52 54 52 00        → "IPCRTR\0"
$ ... /glink-edge/qcom,modem_qrtr/qcom,intents
 00 00 08 00 00 00 00 05   00 00 20 00 00 00 00 03   00 00 44 00 00 00 00 02
```

| 属性 | 值 | 解析 |
|---|---|---|
| `qcom,glink-channels` | `"IPCRTR"` | 通道名 = **IPCRTR**（QRTR 在 GLINK 上的标准通道名） |
| `qcom,intents` | `(0x800,5)`, `(0x2000,3)`, `(0x4400,2)` | 远端通告的接收缓冲：3 种尺寸 × 数量 |
| `qcom,low-latency` | 存在（空属性） | 低延迟通道 |

→ **XNU 侧要发第一条 QMI，必须做的事是**：在 SMEM 上开一个名叫 `IPCRTR` 的 GLINK 通道，
按上表通告 3 组 intent，然后才能往里塞 QRTR 报文。
现有 `drivers/PongPower/QcomGlink.h` 的 `QCOM_GLINK_MAX_CHANNELS = 1` 和
"exclusively leased K60 PMIC endpoint" 的假设**必须打破**（详见 `03-SCOPE.md` §4）。

#### 子节点 `qcom,modem_ds`

```
qcom,glink-channels = "DS\0"
qcom,intents = (0x4000, 2)
```

`DS` = Data Service（老的 SMD 数据通道）。本机数据面已迁到 IPA，这条通道主要留作兼容。

---

## 2. 保留内存：cellular 相关的全部区域

```
$ adb -s 6033dbec shell 'su -c "ls /sys/firmware/devicetree/base/reserved-memory/"'
```

| 区域 | reg（字节原文） | 基址 | 大小 | 用途 |
|---|---|---|---|---|
| `mpss_region@8bc00000` | `00 00 00 00 8b c0 00 00 / 00 00 00 00 13 20 00 00` | **0x8bc00000** | **0x13200000 = 306 MiB** | modem 固件加载区 |
| `ipa_fw_region@8b900000` | `00 00 00 00 8b 90 00 00 / 00 00 00 00 00 01 00 00` | **0x8b900000** | **0x10000 = 64 KiB** | IPA 固件区 |
| `ipa_gsi_region@8b910000` | `00 00 00 00 8b 91 00 00 / 00 00 00 00 00 00 a0 00` | **0x8b910000** | **0xa000 = 40 KiB** | IPA GSI 环/描述符区 |
| `spu_modem_shared_mem@8bbe0000` | — | **0x8bbe0000** | **0x20000 = 128 KiB** | SPU（安全处理单元）与 modem 共享 |
| `spu_tz_shared_mem@8bb80000` | — | 0x8bb80000 | — | SPU 与 TZ 共享 |
| `spss_region_region@8ba00000` | — | 0x8ba00000 | — | SPSS（modem 安全服务处理器） |
| `smem_region@80900000` | `00 00 00 00 80 90 00 00 / 00 00 00 00 00 20 00 00` | **0x80900000** | **0x200000 = 2 MiB** | SMEM（GLINK FIFO 在这里面） |
| `trust_ui_vm_qrtr@e55f3000` | — | 0xe55f3000 | **0x9000** | Gunyah QRTR 共享缓冲（**不是 modem 的**） |
| `global_sync_region@a6f00000` | — | 0xa6f00000 | — | 全局同步 |

**`mpss_region` 的 306 MiB 与 `modem.mdt` 的段表完全吻合**（见 `01-ANDROID-INVENTORY.md` §3.3 与本文 §3）：
所有 PT_LOAD 的 `paddr` 落在 `[0x8bc00000, 0x9ee00000)`，正好等于 `[base, base+0x13200000)`。
这不是巧合 —— 固件就是按这块 carveout 的尺寸链接的。

**注意 `mpss_region` 在 `/proc/iomem` 里看不到**（`no-map` 保留内存），
所以 XNU 侧也必须从 DT 拿这块区域，不能指望 memblock 上报。

---

## 3. 固件段表与 DT carveout 的逐段对照

`modem.mdt` 有 32 个 program header，其中 30 个 `PT_LOAD`：

| 段 | paddr | filesz | memsz | 落点 |
|---|---|---|---|---|
| b01 | 0x8bc00000 | 7,204 | 8,192 | carveout 起点（= `e_entry`） |
| b02 | 0x8bc02000 | 805,556 | 806,912 | |
| b03 | 0x8bcc7000 | 14,756 | 16,384 | |
| b07 | 0x8bd00000 | 114,688 | 114,688 | |
| b18 | 0x8d045000 | 14,095,752 | 45,514,752 | 大 bss |
| b19 | 0x8fbad000 | 16,584,207 | 16,584,207 | |
| b20 | 0x90b7e000 | 6,541,320 | 6,541,320 | |
| **b21** | 0x911c0000 | **0** | 163,696,640 | **纯 bss，无文件** |
| b22 | 0x9addd000 | 120,256 | 120,256 | |
| b23 | 0x9ae00000 | 40,935,488 | 40,935,488 | 最大代码段 |
| b24 | 0x9d510000 | 8,377,984 | 8,377,984 | |
| b25 | 0x9dd40000 | 1,290,846 | 1,290,846 | |
| b26 | 0x9de7c000 | 8,960 | 8,960 | |
| b27 | 0x9de7f000 | 290,304 | 290,304 | |
| b28 | 0x9dec6000 | 102,208 | 102,208 | |
| b29 | 0x9dedf000 | 10,760 | 10,760 | |
| **b30** | 0x9dee2000 | **0** | 15,851,520 | **纯 bss，无文件** |
| **b14** | （filesz=0） | **0** | — | **纯 bss，无文件** |

- `min(paddr) = 0x8bc00000` = `mpss_region` 基址 ✔
- `max(paddr + memsz) = 0x9ee00000` = `0x8bc00000 + 0x13200000` ✔ **严丝合缝**
- `Σ memsz = 320,073,728 B = 305.2 MiB`，carveout 306 MiB ✔

→ **移植结论**：加载 modem 固件**不需要**任何"猜大小"的逻辑，
carveout 尺寸由 DT 给出，段表由 `modem.mdt` 给出，两者一致。
这也解释了为什么 `modem.b14/b21/b30` 文件不存在：它们是 bss 段。

---

## 4. IPA 节点：`/soc/qcom,ipa@3e00000`

```
$ ... /soc/qcom,ipa@3e00000/compatible  → "qcom,ipa\0"
$ ... /soc/qcom,ipa@3e00000/reg
 00 00 00 00 03 e0 00 00  00 00 00 00 00 08 40 00
 00 00 00 00 03 e0 40 00  00 00 00 00 00 0f c0 00
$ ... /soc/qcom,ipa@3e00000/reg-names → "ipa-base\0gsi-base\0"
```

| 区域 | 基址 | 大小 |
|---|---|---|
| `ipa-base` | **0x3e00000** | 0x84000 = 540 KiB |
| `gsi-base` | **0x3e04000** | 0xfc000 = 1008 KiB（与 ipa-base 重叠，是 GSI 的独立视图） |

| 属性 | 字节原文 | 值 | 含义 |
|---|---|---|---|
| `firmware-names` | `"ipa_fws\0"` | — | 固件名 |
| `memory-regions` | `00 00 00 b5` | phandle `0xb5` → `ipa_gsi_region@8b910000` | GSI 环内存 |
| `pas-ids` | `00 00 00 0f` | **15** | PAS 服务 id |
| `qcom,ipa-hw-ver` | `00 00 00 16` | **0x16 = 22** | IPA 硬件版本 4.11 世代 |
| `qcom,ipa-hw-mode` | `00 00 00 00` | 0 | |
| `qcom,ipa-cfg-offset` | `00 14 00 00` | **0x140000** | 配置区偏移 |
| `qcom,entire-ipa-block-size` | `00 20 00 00` | **0x200000** | 整块 2 MiB |
| `qcom,ee` | `00 00 00 00` | **0** | 执行环境 = AP |
| `qcom,platform-type` | `00 00 00 01` | 1 | |

> **踩坑记录**：用 `od -td4` 而不带 `--endian=big` 读这些属性会得到字节反序的值
> （`qcom,ipa-hw-ver` 会读成 369098752 = 0x16000000 而不是 0x16）。
> 本文件所有 cell 一律用 `od -An -tx1` + 手工大端解析。

### 4.1 IPA 子节点

| 子节点 | 关键属性 | 作用 |
|---|---|---|
| `ipa_smmu_ap` | `iommus`, `qcom,iommu-dma`, `qcom,iommu-dma-addr-pool`, `qcom,additional-mapping`, `qcom,ipa-q6-smem-size` | AP 侧 SMMU 上下文 |
| `ipa_smmu_uc` | `iommus`, `qcom,iommu-dma`, `qcom,iommu-dma-addr-pool` | 微控制器侧 SMMU |
| `ipa_smmu_wlan` | `iommus`, `qcom,iommu-dma` | WLAN 侧 SMMU |
| `ipa_smmu_11ad` | `dma-coherent`, `iommus`, `qcom,iommu-group`, `qcom,shared-cb` | 11ad 侧 |
| `qcom,smp2p_map_ipa_1_in` / `_out` | — | IPA 与 modem 的 smp2p 位图映射 |

### 4.2 IPA 的"队列"在 DT 里怎么描述

**诚实的答案：DT 不描述队列数量。** DT 只给：

1. `gsi-base` 寄存器窗口（0x3e04000，1008 KiB）—— GSI 环的 MMIO 基址
2. `ipa_gsi_region@8b910000`（40 KiB）—— GSI 环在 DDR 里的落点
3. `qcom,ipa-hw-ver = 0x16` —— 决定环的数量/尺寸

**每个通道的 ring 数量、深度、doorbell 布局由 IPA 硬件版本决定**（这里是 v4.11 世代），
在 Qualcomm 的 IPA 驱动里是**代码常量**（`ipa_reg_v4_11.h` 之类），不是 DT 属性。
→ 所以移植 IPA 时，"从 DT 提取 IPA 队列"这个动作**做不到**，
只能从 DT 拿到基址/尺寸/版本，剩下的必须从官方 IPA 驱动的寄存器表拿。
（这条要写进 `03-SCOPE.md` 的"为什么 IPA 是全有或全无"。）

### 4.3 一个容易踩的坑：`qcom,ipa_fws` 是 `disabled`

```
$ ... /soc/qcom,ipa_fws/compatible  → "qcom,pil-tz-generic\0"
$ ... /soc/qcom,ipa_fws/qcom,firmware-name → "ipa_fws\0"
$ ... /soc/qcom,ipa_fws/qcom,pas-id → <0x0f>
$ ... /soc/qcom,ipa_fws/status → "disabled\0"
```

IPA 固件的加载**不是**由这个 `disabled` 节点驱动的，
而是由 `/soc/qcom,ipa@3e00000` 自己的 `firmware-names` + `pas-ids` 驱动。
**照抄 `qcom,ipa_fws` 节点会得到一个永远不加载固件的 IPA。**

---

## 5. QRTR 的三个传输节点（必须分清）

DT 里 `qrtr` 相关节点有三个，**只有一个属于 modem**：

| 节点 | compatible | 关键属性 | 属于谁 |
|---|---|---|---|
| `/soc/remoteproc-mss@04080000/glink-edge/qcom,modem_qrtr` | （无独立 compatible，靠 `qcom,glink-channels`） | `qcom,glink-channels = "IPCRTR"` | **modem** ✔ |
| `/soc/mhi_qrtr_cnss` | `"qcom,qrtr-mhi"` | `qcom,dev-id = 0x1103`, `qcom,net-id = 0` | **WLAN（CNSS）** ✘ |
| `/soc/qrtr-gunyah` | `"qcom,qrtr-gunyah"` | `gunyah-label = 3`, `peer-name = 2`, `shared-buffer = <0x53>` | **Gunyah 虚拟机** ✘ |

`0x1103` 是 **QCA6490 WLAN 的 PCIe device id**（见 `01-ANDROID-INVENTORY.md` §6.4：
`0000:01:00.0` = `17cb:1103`）。
`qrtr-gunyah` 的 `shared-buffer` phandle `0x53` 指向 `trust_ui_vm_qrtr@e55f3000`，
是给 Trust UI 虚拟机的，与 modem 无关。

→ **结论：modem 的 QRTR 走 GLINK/SMEM 的 `IPCRTR` 通道，与 MHI 无关。**
任何"用 `mhi_qrtr` 连 modem"的实现都是把 WLAN 的路径张冠李戴了。
（参考：`patches/wifi/0001-*.patch` 里已有的 `nw_qrtr_mhi_register` 是 WLAN 的，
**不能复用给 modem**，但它的 AF_QIPCRTR 内核接口形状可以参考。）

---

## 6. 其余与 modem 相关的 DT 节点

| 节点 | compatible | 作用 |
|---|---|---|
| `/soc/qcom,smem` | `"qcom,smem"` | SMEM 描述符；`memory-region = <0xac>`（`smem_region@80900000`），`hwlocks = <0xad 0x03>` |
| `/soc/qcom,smp2p-modem` | `"qcom,smp2p"` | modem 的 smp2p 位图；`qcom,smem = <0x1b3 0x1ac>`，`local-pid = 0`，`remote-pid = 1`，`interrupts = (2,2,1)`；子节点 `qcom,smp2p-ipa-1-in/out`、`master-kernel`（phandle `0xa0`） |
| `/soc/qcom,glink` | `"qcom,glink"` | GLINK 核心（驱动 `msm_glink`） |
| `/soc/qcom,glinkpkt` | `"qcom,glinkpkt"` | 字符设备通道：`apr-apps2`、`at-mdm0`、`data1`、`data11`、`data4`、`data40-cntl` |
| `/soc/qcom,rmnet-ipa` | `"qcom,rmnet-ipa3"` | rmnet 虚拟网卡绑定 |
| `/soc/remoteproc-spss@1880000` | `"qcom,cape-spss-pas"` | SPSS（modem 安全服务处理器）；`reg` 五段 TZ 寄存器窗口（0x188101c/4、0x1881024/4、0x1881028/4、0x188103c/4、0x1881100/4、0x1882014/4） |
| `/soc/qcom,spss_utils` | — | SPSS 工具接口 |
| `/soc/qmi-tmd-devices` | — | 热缓解 QMI 设备表（`modem_vdd`=`cpu_restriction_cold`、`sdr0/sdr1`、`pa_lte_sdr0/1`、`pa_nr_sdr0/1`、`mmw0..3`、`modem_nr_dsc_kr` 等） |
| `/soc/microdump_modem`, `/soc/modem_diag`, `/soc/modem_etm0`, `/soc/modem2_etm0` | — | 调试/coresight（非功能路径） |
| `/soc/qcom,pcie@1c00000`, `/soc/qcom,pcie@1c08000` | `"qcom,pcie-*` | 两个 PCIe 控制器；**其下无 modem 节点**，实际只有 WLAN 端点 |

---

## 7. 计数核对：brief 里的"121 处命中"

brief 说"DT 里 `qrtr|qmi|ipa` 共 121 处命中"。本会话实测（三种口径）：

| 口径 | 命令 | 结果 |
|---|---|---|
| 活 FDT 字符串命中 | `grep -roaiE 'qrtr|qmi|ipa' /sys/firmware/devicetree/base | wc -l` | **87**（ipa 47 / qmi 30 / qrtr 10） |
| 活 FDT 节点名命中 | `find -L /sys/firmware/devicetree/base -iname '*qrtr*' -o -iname '*qmi*' -o -iname '*ipa*' | wc -l` | **83** |
| 厂商 DTB 二进制命中 | `grep -aoiE 'qrtr|qmi|ipa' sm8475-xiaomi-mondrian.dtb | wc -l` | **125**（ipa 79 / qmi 35 / qrtr 11） |
| 厂商 DTB strings 命中 | `strings -a ...dtb | grep -oiE ... | wc -l` | **123**（ipa 77 / qmi 35 / qrtr 11） |

**121 不在上述四个数里。** 差异原因是统计方法不同（活 FDT 的 `grep -r` 会跳过 symlink 目标、
二进制 DTB 会连 `__symbols__`/`__fixups__` 里的重复引用一起数）。
**本文件不采用 121 这个数**，一律引用上表可复现的口径。

> 另一条踩坑：`grep -r` 对 `/proc/device-tree` **返回 0 命中**（该路径下的条目是 symlink，
> `grep -r` 不跟随）。必须用 `/sys/firmware/devicetree/base` + `find -L`。

---

## 8. 厂商 DTB 的来源

`E:\hackios\uefi-mondrian\Platforms\Xiaomi\mondrianPkg\FdtBlob\Source.txt` 原文：

```
DTB was compiled from https://github.com/sm8450-mainline/linux/tree/tyalie
With usb-role-switch; added on line 1003 to fix USB OTG Mode
```

- 厂商 DTB：480,692 B，md5 `a977423fca405512f6d333a955c9f970`
- 活 FDT：919,210 B，sha256 `da19d6bb...c4b941`（**更大**，因为运行时会注入 `__symbols__`、
  `chosen`、`firmware`、`memory` 等节点，并可能被 bootloader 打过补丁）

**取证时以活 FDT 为准**，厂商 DTB 仅作交叉参考 —— 两者不是同一份二进制。

---

## 9. 仓库里的 `dts/mondrian.dts` 缺什么

本仓 `dts/mondrian.dts`（198 行，已全文读过）现有节点：
`memory@900000000`、`ufs@1d84000`、`pong-audio`、`smem-region@80900000`、
`tcsr` syscon@1f40000、`hwlock`、`smem`、`ipcc` mailbox@ed18000、
`adsp-region@9fd00000`、`remoteproc-adsp@3000000`、`smp2p-adsp`、`pmic-glink`、`battery-charger`。

**完全没有**：`mpss_region`、`ipa_fw_region`、`ipa_gsi_region`、`remoteproc-mss`、
`qcom,ipa`、`smp2p-modem`、`glink-edge`（modem 侧）。

这正好印证 `porting.toml` 里 cellular area 的 configuration 断言
"dts/mondrian.dts does not describe the modem memory regions, QRTR transport or IPA queues"。
→ 要动 cellular，**第一步是把 §1/§2/§4 的节点补进 `dts/mondrian.dts`**，
并且必须从活 FDT 抄字节，不能凭记忆写。

---

## 10. **X65 是封装在 SM8475 内还是外置？**

### 10.1 结论

**基带子系统在 SM8475 封装内，不是外置 modem。** 但必须把话说准：

- ✅ **能证明的**：modem 是一个 **SoC 内部 PAS 远程处理器**（MMIO 在 0x04080000，
  固件搬进 SoC DDR 的 carveout，供电由板上 PMIC 的 SMPS 经 RPMh 提供，
  通信走 SoC 内部 SMEM/GLINK，数据面走 SoC 内部 IPA）。
  **没有任何外部总线（PCIe/USB/SPI）上的 modem 设备。**
- ❌ **DT 不能证明的**：这颗 modem 的**市场名称叫 "X65"**。
  DT 里只有代号 `cape`（`qcom,cape-modem-pas`），固件里也没有 `X65`/`SDX` 字样
  （对 b18/b19/b23 前 2 MB 做 `strings` 只匹配到 `cape`）。
  "X65" 这个型号来自 Qualcomm 对 SM8475 平台的官方命名（SD 8+ Gen 1 配 X65 5G modem-RF），
  **不是 DT 里的字符串**。所以本文的措辞是"X65 级 modem 内置于 SM8475"，
  而不是"DT 证明它是 X65"。
- ⚠️ **必须区分**：**基带（baseband/MSS + 固件 + IPA）在封装内**，
  **射频前端（transceiver、PA、滤波器、天线）在封装外**。这是所有手机的常态。
  说"X65 在封装内"指的是基带 SoC 部分，不含 RF FEM。

### 10.2 证据链（逐条可复现）

| # | 证据 | 命令 / 出处 | 说明 |
|---|---|---|---|
| 1 | modem 的 MMIO 在 SoC 外设地址空间 | DT `/soc/remoteproc-mss@04080000/reg` = `0x04080000`/64 KiB | 0x04080000 远低于 DDR 起点，属 SoC 内部寄存器区；外置器件不会出现在这里 |
| 2 | 固件由 PAS 加载进 SoC DDR carveout | DT `memory-region = <0x9d>` → `mpss_region@8bc00000`（306 MiB）；`modem.mdt` 段表 `min(paddr)=0x8bc00000`、`max=0x9ee00000` 严丝合缝 | 外置 modem 有自己的 flash/DRAM，不需要 AP 的 DDR carveout |
| 3 | 固件是 Hexagon 代码 | `modem.mdt` `e_machine = 0xA4`（QDSP6）、`e_type=2`、`e_entry=0x8bc00000` | 跑在 SoC 内 Hexagon 核上，不是 AP 的 AArch64 |
| 4 | 供电来自板上 PMIC | DT `cx-supply = <0x1e>`→PM8350C S6，`mx-supply = <0x9c>`→PM8350C S4 | 由 SoC 的 RPMh 直接管；外置 modem 有自己的 PMIC 或独立供电轨 |
| 5 | 启动握手走 SoC 内部 IPCC | DT `interrupts-extended` 含 `<&ipcc 0x9f 0 0..7>`，`&ipcc`=`/soc/qcom,ipcc@ed18000` | IPCC 是 SoC 内部核间中断控制器 |
| 6 | 通信走 SoC 内部 SMEM/GLINK | DT `glink-edge/transport = "smem"`，`qcom,remote-pid = 1`，`mbox-names = "mpss_smem"` | SMEM 是 SoC 内共享内存；外置 modem 走 PCIe/USB |
| 7 | 数据面走 SoC 内部 IPA | DT `/soc/qcom,ipa@3e00000`（MMIO 0x3e00000） | IPA 是 SoC 内硬件加速器 |
| 8 | **PCIe 上没有 modem** | `ls /sys/bus/pci/devices/` → 只有 `0000:00:00.0`(17cb:0110 root port) 和 `0000:01:00.0`(17cb:1103 QCA6490 WLAN) | 整机只有两个 PCIe 设备，第二个是 WLAN |
| 9 | **DT 里没有外置 modem 总线节点** | 全树搜索 modem 相关节点，无 PCIe/USB/SPI 下的 modem 子节点 | 反证 |
| 10 | 基带标识是"板载 SoC" | `getprop ro.baseband = msm`，`ro.boot.baseband = msm` | 外挂模块（如工程机 MDM9x55）此值不同 |
| 11 | 分区布局是"固件容器"而非"独立系统" | `modem_a`=`sde7` 380 MiB，只读挂 `/vendor/firmware_mnt`，里面只有 `modem.*` 104 MiB 固件 + `modem_pr` 配置 | 外置 modem 通常有自己的完整固件分区 + 自己的文件系统 |
| 12 | 没有 `mba.mbn` | `ls /vendor/firmware_mnt/image | grep -i mba` → 无 | 新一代单镜像 PAS 加载，与 SDM845 世代不同 |

### 10.3 分区布局怎么证明"内置"

关键在 `modem_a` 分区**装的是什么**：

```
modem_a (sde7, 380 MiB, 只读 vfat @ /vendor/firmware_mnt)
└── image/
    ├── modem.mdt  (ELF32, e_machine=0xA4 QDSP6, e_entry=0x8bc00000)   ← 可加载镜像
    ├── modem.b00..b31 (30 个分片，104.02 MiB)                          ← 段数据
    ├── modemr.jsn (root_pd, qmi_instance_id=180)                       ← 服务注册
    └── modem_pr/mcfg/configs/ (运营商配置 mbn)                          ← 配置
```

- 分区里**只有可加载镜像 + 配置**，**没有**引导程序、没有内核、没有文件系统、没有可执行脚本。
  → 它是"给 PAS 喂料"的容器，不是"一个能自己跑的系统"。
- `modem.mdt` 的 `e_entry` 等于 DT carveout 基址 → 镜像的**链接地址就是 AP 的 DDR 地址**。
  外置 modem 的固件链接地址会是它自己 DRAM 的地址，不会等于 AP 的 carveout。
- `modemst1`/`modemst2`（各 8 MiB，裸分区未挂载）是 EFS/NV 存储，
  由 modem 固件通过 QMI 请求、Android 的 `tftp_server` 代读。
  → 连"自己的持久化存储"都要 AP 代劳，进一步说明它没有独立的主机侧。

### 10.4 一句话给 porting.toml

> "K60 的基带是 SM8475 封装内的 PAS 远程处理器（`qcom,cape-modem-pas` @ 0x04080000，
> 固件 `modem.mdt` 为 QDSP6 ELF32，加载到 `mpss_region` 0x8bc00000/0x13200000），
> 不是板上外置 modem；整机仅有两个 PCIe 设备且均为 WLAN/root port。
> 市场型号 X65 来自 Qualcomm 平台命名，DT 中只有代号 `cape`，固件不自报型号。"

---

## 11. 还缺什么（本文的诚实清单）

| 缺项 | 为什么缺 | 怎么补 |
|---|---|---|
| 反编译后的 `.dts` 文本 | 本机无 `dtc`/`fdtdump`，python 无 `libfdt` | 装 `device-tree-compiler`，或 `pip install libfdt`，再 `dtc -I fs -O dts /sys/firmware/devicetree/base` |
| IPA 每个通道的 ring 数/深度 | DT 不描述，由 `ipa-hw-ver=0x16` 在驱动代码里决定 | 从官方 `ipa_reg_v4_11`（或对应版本）寄存器表取 |
| GLINK FIFO 在 SMEM 里的具体偏移 | DT 只给 SMEM 区基址，FIFO 由 GLINK 协议在 SMEM 内动态协商 | 读 SMEM 头部（`SMEM_FIRST_VALID_ENTRY`）+ `smem_alloc` 结果 |
| `qcom,modem_qrtr` 的 `qcom,intents` 是否还有别的组 | 只读到 3 组 | 需要 GLINK 通道建立后从对端通告里核对 |
| `X65` 型号的直接证据 | DT/固件都不自报 | 只能引用 Qualcomm 平台命名（外部文档），本文不伪造 DT 证据 |

---

## 12. 复现命令

```bash
export K60_AGENT_ID=cellular-agent
adb -s 6033dbec shell 'su -c "cat /sys/firmware/fdt"' > /tmp/k60-live.fdt   # 919210 B
sha256sum /tmp/k60-live.fdt    # da19d6bb...c4b941

B=/sys/firmware/devicetree/base
adb -s 6033dbec shell "su -c 'ls $B/reserved-memory/'"
adb -s 6033dbec shell "su -c 'od -An -tx1 $B/reserved-memory/mpss_region@8bc00000/reg'"
adb -s 6033dbec shell "su -c 'od -An -tx1 $B/soc/remoteproc-mss@04080000/reg'"
adb -s 6033dbec shell "su -c 'cat $B/soc/remoteproc-mss@04080000/glink-edge/qcom,modem_qrtr/qcom,glink-channels'"
adb -s 6033dbec shell "su -c 'od -An -tx1 $B/soc/qcom,ipa@3e00000/reg'"
adb -s 6033dbec shell "su -c 'ls /sys/bus/pci/devices/'"
```

> adb + MSYS 引号坑：嵌套 `su -c "..."` 里的引号会被吃掉，把整个 payload 用**单引号**包住、
> 内部用双引号；或者先把文件 dump 到主机再过滤。
