# USB 设备模式 / Type-C 八步调研

> 目标子系统：USB device mode（DWC3 @ 0xa600000）+ Type-C 角色切换
> 日期：2026-11-14
> 状态：① 同型 / ② 官方 / ③ 逆向 / ④ 广域 已完成；⑤ 方案见 §8；⑥⑦⑧ 见 §9、§10
> 当前能力：**CDC-ACM 串口控制台**（VID 0x1209 / PID 0x0001），已上机枚举并承载全部日志采集

---

## 0. 结论摘要

1. **控制器已被 XNU 直接接管**：DWC3 @ 0xa600000 由 `bsd/dev/k60_usblog.c` 在设备模式下跑起来，
   上机日志证明事件环、SETUP、GET_DESCRIPTOR 全通（§2）。所以"设备模式不存在"是错的，
   准确说法是"设备模式只实现了控制台这一种形态"。
2. **Type-C 的 CC 逻辑不在 AP 侧寄存器里**。DTB 里没有 `typec` / `usb-role-switch` / `ucsi` 的
   AP 节点，只有一个 `qcom,ucsi-glink` 挂在 `qcom,pmic_glink` 下（§5）。CC 检测与角色裁决在 ADSP
   （`msm/adsp/charger_pd` 保护域）。任何"直接读 CC 寄存器"的写法都是猜测，违反铁则 3。
3. **从"控制台"到"复合设备"的路线有同 SoC 证据**：pong-usb（SM8475）用一个 3 接口复合描述符
   同时提供 Apple usbmux 与 CDC IAD（§6）。K60 可以先做"CDC-ACM + 第二接口"的复合枚举，
   再决定是否上 mux。
4. **Apple 原生 USB 栈（AppleUSBXDCI / IOUSBHost）是终态，不是下一步**：sheng（SM8550，同厂商）
   已给出可抄的加载序列与 ABI 事实（§7），但依赖 kext 加载与 280 槽 vtable，风险远高于本轮目标。

---

## 1. 现状：本仓已经有什么

| 项 | 位置 | 说明 |
|---|---|---|
| 控制器驱动 | `patches/xnu/series:124` → `0300-k60-usblog-ep0.patch` | 新增 `bsd/dev/k60_usblog.c`（1339 行），含 DWC3 设备模式 + CDC-ACM |
| DMA 一致性修正 | `patches/xnu/series:132` → `0307-k60-usblog-dma-coherency.patch` | TRB 各自独占 64 B 行；设备描述符 class/subclass 置 02/02 |
| 采集重启 | `patches/xnu/series:138` → `0308-k60-usblog-pong-capture-restart.patch` | 采集侧重启路径 |
| boot-arg | `docs/engineering/BOOT-ARGS.md:34` | `k60_usblog` 0=不启用 / 1=只读探针 / 2=完整 CDC 控制台 |
| 能力上限记录 | `porting.toml:187` | "XNU CDC-ACM VID1209/PID0001, not Apple usbmux … no remote debugserver or LLDB" |
| 可行性研究 | `docs/reference/USB-LOG-CHANNEL.md` | DWC3 / eUSB2 / ssphy / QSCRATCH / SMMU 的早期调研 |

驱动内关键锚点（以构建产物 `.cache/xnu-work/bsd/dev/k60_usblog.c` 为准）：

- `k60_usblog.c:935-957`：`static struct { … } ud;`（`dwc`/`dma`/`dma_pa`/`events`/`configured`/`dtr`/`failed`/`started`）
- `k60_usblog.c:959-970`：`dwc_wr()` / `dwc_rd()`，全部控制器访问都走这两个（`dsb sy` 后写）
- `k60_usblog.c:1673`：`ud_hb()` 心跳线程（2 s 一次，现有唯一周期打印点）
- `k60_usblog.c:1722`：`ud.dwc = ml_io_map(DWC3_PA, DWC3_SIZE);`
- `k60_usblog.c:1810`：`vm_offset_t qs = ml_io_map(QSCRATCH_PA, 0x100);`（**局部变量，未保留**）
- `k60_usblog.c:1902`：`k60_usblog_start()`（解析 boot-arg → 起 worker）

---

## 2. 上机真值（证据 `E:/k60-work/evidence/usblog-20261114-touchd/console.log`）

同一次启动（`capture.json` verdict=captured，panicMarker=null）里，`K60 USBLOG` 行给出的寄存器快照：

| 观测点 | 值 | 含义 |
|---|---|---|
| `GDSC usb30_prim` | `0xf822f000`（on） | USB30 GDSC 供电域已开，bit31=1 |
| CBCR master / sleep / mock-utmi / cfg-noc / aggre | `0x00000221` / `0x1` / `0x1` / `0x1` / `0x1` | 七路时钟全开，无 `CBCR_CLK_OFF`(bit31) |
| `GSNPSID` | `0x33313130` | 上半字 `0x3331` → DWC_usb31，与 pong-usb 的 `{0x5533,0x5534,0x3331}` 白名单一致 |
| `GCTL` | `0x00102001` | `PRTCAPDIR=2`（device），固件已把角色交给设备侧 |
| `GSTS` | `0x7e800000` | — |
| `GUSB2PHYCFG` | `0x00102400` | SUSPHY/ENBLSLPM 位与 pong-usb 的关断策略不同（K60 未关） |
| `DCFG` / `DCTL` / `DEVTEN` | `0x00480814` / `0x10f00000` / `0x00001277` | 高速、RUN_STOP 已置位、事件使能 |
| `DSTS` | `0x00d365cc` → 运行后 `0x00020001` | 已连接、速度位有效 |
| `DALEPENA` | `0x0000000f` | EP0–EP3 使能 |
| `GEVNTADR` / `GEVNTSIZ` / `GEVNTCOUNT` | `0x00000000fbfdf000` / `0x80001000` / `0` | 64 位事件环地址（K60 DRAM 高窗），大小 4 KiB、已清空 |
| `GHWPARAMS0` | `0x4020400a` | — |
| eUSB2 `0x88e3000` +0x1a0/+0x210/+0x240/+0x254 | `0x0`/`0x0`/`0x0`/`0x0b0b0b0b` | PHY 侧已出时钟/上电态 |
| SMMU `SCR0`/`IDR0`/`IDR1`/`IDR2`/`GFSR` | `0x00200406`/`0x4c017e71`/`0x6000004b`/`0x00005111`/`0` | SMMUv2、无故障 |
| SMMU 安装 | `sid 0 slot 111 bank 73 SMR 0x80000000 S2CR 0x00000049 CBAR 0x00010000 CBA2R 0x00000001 SCTLR 0` | stream 0 的 bypass 上下文已装好 |
| QSCRATCH | `HS_PHY_CTRL 0x10100000 SS_PHY_CTRL 0x01000000` | VBUS override 生效（bit20/bit28、bit24） |
| 事件 | `0x301` / `0x50301` / `0x30301` / `0x101` / `0x201` / `0xc040` / `0x10c2` | 连接 → 总线复位 → SETUP `80 06 0100`（GET_DESCRIPTOR） |
| DMA 基址 | `0x90934f000` | 高于 4 GiB，64 位 GEVNTADR/TRB 必需 |

**结论**：设备侧链路（时钟 → GDSC → SMMU → PHY → 控制器 → 枚举）每一环都有上机读数，
不是纸面推断。

---

## 3. 控制器：DWC3 @ 0xa600000

| 事实 | 值 | 证据类别 | 出处 |
|---|---|---|---|
| 基址 / 长度 | `0xa600000` / `0xd93c` | 同型（DTB） | `sm8475-xiaomi-mondrian.dtb` → `mondrian.dts:16856` |
| 驱动映射长度 | `0xd000` | 本仓实现 | `k60_usblog.c` `DWC3_SIZE` |
| IOMMU | `<&apps_smmu 0x00 0x00>`，SID 0 | 同型 | `mondrian.dts:16856` `iommus` |
| DMA 地址池 | `0x90000000` + `0x60000000` | 同型 | `mondrian.dts:16856` `qcom,iommu-dma-addr-pool` |
| dr_mode | `"otg"`，`maximum-speed = "high-speed"` | 同型 | `mondrian.dts:16856` |
| 角色 | 固件交接为 device（`GCTL.PRTCAPDIR=2`） | 上机 | §2 |

寄存器偏移（`k60_usblog.c` 与 pong-usb `Dwc3Registers.h` 一致）：

`GSNPSID 0xc120`、`GCTL 0xc110`、`GUSB2PHYCFG 0xc200`、`GEVNTADRLO/HI 0xc400/0xc404`、
`GEVNTSIZ 0xc408`、`GEVNTCOUNT 0xc40c`、`DCFG 0xc700`、`DCTL 0xc704`、`DEVTEN 0xc708`、
`DSTS 0xc70c`、`DALEPENA 0xc720`、`DEPCMD(n) 0xc80c+0x10n`。

**风险注记**：DTB 声明的寄存器长度 `0xd93c` 大于驱动映射的 `0xd000`。当前用到的最大偏移是
`DEPCMD(3)=0xc83c`，仍在 `0xd000` 内，故不影响；若将来要用 `0xd000` 之后的块，必须扩映射。

DMA / TRB 布局（`0307` 之后的最终版）：

`UD_EVT 0x0000`（4 KiB 事件环）、`UD_TRB_OUT 0x1000`、`UD_TRB_IN 0x10c0`、`UD_SETUP 0x1040`、
`UD_DATA 0x1100`、`UD_TRB_TX 0x3000`、`UD_TRB_RX 0x3040`、`UD_TXDATA 0x4000`、`UD_RXDATA 0x5000`、
`UD_SIZE 0x8000`。

---

## 4. PHY

| 块 | 地址 | 证据 | 说明 |
|---|---|---|---|
| eUSB2（HS）PHY | `0x88e3000`，len `0x154` | `mondrian.dts:16879` `qcom,usb-snps-eusb2-phy` | **不是**旧的 FEMTO PHY `0x88e2000`；pong-usb 明确写死这一差异（`PongUsbPhy.h:142`） |
| EUD 使能/检测 | `0x88e2000`/`0xc276000` | `mondrian.dts:16879` `reg-names` | 仅 EUD（调试）用 |
| SS PHY（QMP/DP combo） | `0x88e8000`，len `0x3000`，**status=disabled** | `mondrian.dts:16899` | 本 DT 关掉了 USB3 SS PHY → 只能 HS |
| usb_nop_phy | `usb-nop-xceiv` | `mondrian.dts:16893` | dwc3 的第二个 `usb-phy` 是空 xceiver |
| QSCRATCH | `0xa6f8800` | 本仓 `QSCRATCH_PA`；pong-usb `qscratch.open(0xa6f8800,0x400)` | VBUS 覆盖 |
| GCC GDSC | `0x49004` bit31 | 上机 §2 | usb30_prim 供电域 |
| GCC CBCR | master `0x49018`、sleep `0x49020`、mock-utmi `0x49024`、cfg-noc `0x49084`、aggre `0x49088`、clkref-eusb3 `0x9c00c`、clkref-usb3 `0x9c010` | 上机 §2 | 七路时钟 |

**VBUS 覆盖是什么、不是什么**：`HS_PHY_CTRL |= UTMI_OTG_VBUS_VALID(bit20) | SW_SESSVLD_SEL(bit28)`、
`SS_PHY_CTRL |= LANE0_PWR_PRESENT(bit24)` 让控制器"相信"总线上有 VBUS，从而进入枚举。
它**不提供** CC 方向、也不提供真实供电状态——那部分见 §5。

PHY 供电轨（`docs/reference/USB-LOG-CHANNEL.md`）：RPMh `ldob5` 879 mV、`ldoc10` 1.2 V；
在 USB 上下文直接调 RPMh 会崩（需要 touch 线的时序）。这也是为什么当前只用 QSCRATCH 覆盖，
而不是去改 PHY 供电。

---

## 5. Type-C 角色切换：证据指向 ADSP，不指向 AP

### 5.1 DT 里有什么、没有什么

| 事实 | 位置 |
|---|---|
| `ssusb@a600000` 有 `extcon = <0x22f>` | `mondrian.dts:16853` |
| `qcom,pmic_glink` 节点，`channel = "PMIC_RTR_ADSP_APPS"`，`qcom,subsys-name = "lpass"`，`qcom,protection-domain = "tms/servreg", "msm/adsp/charger_pd"` | `mondrian.dts:8555` 起 |
| `qcom,ucsi { compatible = "qcom,ucsi-glink"; }` | `mondrian.dts:8567-8568` |
| alias `ucsi = "/soc/qcom,pmic_glink/qcom,ucsi"` | `mondrian.dts:21364` |
| alias `usb0 = "/soc/ssusb@a600000"`、`eusb2_phy0`、`usb_qmp_dp_phy` | `mondrian.dts:21937-21940` |
| **没有** AP 侧 `typec` / `usb-role-switch` / `qcom,pmic-typec` 节点 | 全文检索无命中 |

### 5.2 结论（可作为方案依据）

- Type-C 的 CC 检测、角色（DFP/UFP）、alt-mode 协商由 **ADSP 上的 charger_pd 保护域**经
  pmic-glink/UCSI 上报。AP 侧没有可直接读的 CC 寄存器。
- `extcon` 是 DWC3 的角色输入，由上层（pmic-glink → ucsi → extcon 映射）驱动；
  当前 XNU 里没有任何东西喂这个 extcon。
- 因此"上电后自己判断插的是主机还是从机"这件事，在 K60 上必须先有 **GLINK 通道**，
  再谈 UCSI 命令。本仓已有可复用的传输层：`drivers/PongPower/K60PmicGlink.h`
  （SMEM/GLINK 客户端，`open/close/poll/send`，`QcomGlink.h` 提供 intent 协议）。
- **不做的判断**：不假设 `0x88e2000` 附近有 CC 状态位，也不假设 PMIC 侧有可直读的 CC ADC——
  没有同型可执行证据，按铁则 3 只能记为 blocker 而不是代码。

---

## 6. 从"控制台"到"可枚举复合设备"

### 6.1 现状描述符

`0300` + `0307` 之后：单配置、2 接口 CDC-ACM，config 67 B，自供电，100 mA；
设备描述符 class/subclass 置 `02/02` 以便 Windows 用 inbox `usbser.sys` 绑定
（Microsoft Learn「USB serial driver (Usbser.sys)」；subclass=00 时 Windows 不绑定）。

### 6.2 同型证据：pong-usb 的复合形态

`references/pong-usb/PongUsbDevice.h:69`：

```c
static uint8_t composite[]={9,2,98,0,3,1,0,0xc0,50, …};
```

98 字节、3 接口；`PongUsbDevice.h:66-68` 的注释给出设计意图：

> Mux first for native mobile-host discovery, plus a separate CDC IAD.
> Apple protocol VID/PID is used only by this opt-in compatibility function.
> Product/manufacturer continue to identify the actual Pong port.

同一文件 `:60` 给出 mux 端点布局（`MuxTxTrb 0x3040`、`MuxRxTrb 0x3060`、`MuxTxData 0x6000`、`MuxRxData 0x7000`），
`:214-216` 说明 AppleUSBHostiOSDevice 会请求 host/device/default configuration 与 extended function，
三者都指向同一个复合配置。

### 6.3 K60 的可落地路径（按风险排序）

| 阶段 | 内容 | 需要的新证据 | 风险 |
|---|---|---|---|
| P1 | 在现有 CDC-ACM 旁边加一个**第二接口**（厂商自定义，IN/OUT bulk），配置改成 3 接口 IAD | 描述符字节本地校验 + 上机 `lsusb`/Windows 设备管理器 | 低（不改控制器逻辑） |
| P2 | 第二接口上跑 Apple usbmux 协议层 | `PongUsbMux.h` 的 socket/lockdownd 契约（§7.3） | 中（要内核 socket + lockdownd 行为） |
| P3 | Type-C 角色（GLINK/UCSI） | ADSP charger_pd 通道可用性 | 高（跨子系统） |

**不采用**：直接照搬 pong-usb 的 Apple VID/PID（`0x05ac`）作为 K60 默认身份。
那会把调试设备伪装成 Apple 设备，且与"同型证据"无关——pong-usb 自己也把它限制在 opt-in 函数里。

---

## 7. IOUSBHost 侧要加的 hook（终态，非本轮）

### 7.1 同厂商可抄的加载序列（sheng / SM8550）

`references/UniXNU-sheng/package/UsbProbe.cpp:16-38`：

1. `IOSleep(3000)` → `qcom_dwc3_bring_up()`（硬件自检通过才继续）
2. `OSKextLoadKextWithIdentifier("com.apple.driver.AppleUSBXDCI")`，结果写 `native_usb_stats[21]`；
   失败（非 `kOSReturnSuccess` 且非 `kOSKextReturnStartStopError`）→ `stats[0] = -9` 并终止线程
3. `qcom_dwc3_host_load((int)OSKextLoadKextWithIdentifier("com.apple.driver.usb.AppleUSBXHCI"))`
4. `OSMetaClass::preModLoad(g_kernel_kmod_info.name)`（失败 → `stats[0] = -10`）
5. `qcom_dwc3_static_init()`（即 `__GLOBAL__sub_I_QcomDwc3.cpp`）
6. `OSMetaClass::postModLoad(handle)`（失败 → `stats[0] = -11`）
7. `qcom_dwc3_publish()`；boot-arg `usb` 为 2/3 时 `qcom_dwc3_diag(mode==3)`

入口 `sheng_usb_probe()`（`UsbProbe.cpp:42-47`）只在 boot-arg `usb` 非零时起 worker。

### 7.2 ABI 事实（sheng 已生成）

`references/UniXNU-sheng/scripts/gen-usb27-abi.py` 产出 `usb-xdci-24A446.json` / `usb-xdci-26C5035r.json`：
`AppleUSBXDCI` 的 vtable 共 **280 槽**（`VT=0xfffffe00083f24c0`、`BASE=168`），
槽位 ≥168 属 `IOUSBDeviceController`/`AppleUSBXDCI`，其头文件不公开；指针认证判别式用 SipHash
（key `b5 d4 c9 eb 79 10 4a 79 6f ec 8b 1b 42 87 81 d4`，每 8 字节 2 轮、末轮 4 轮、结果 `% 0xffff + 1`）。
数据源是 `kits/XnuPrelink/kc_image.py` 解 `kernelcache.decompressed`。

### 7.3 mux 侧契约

`references/pong-usb/PongUsbMux.h`：

- `:58-59`：用 `kpi_socket` 建**真内核 socket**（peer PID 0），满足 Darwin24 lockdownd 的
  `TCP_PEERPID` 检查；不 patch 凭据、不做原生服务校验，全部走 loopback。
- `:144-146`：接口属性供 lockdownd 的连接检测消费，描述实际实现的 mux 端点。
- `:156-157`：`mux_notification_handler` 的 configured/unconfigured 事件；调用 IOKit 客户端时
  不得持有字节队列锁。

**K60 现状**：XNU 里 BSD 网络 KPI 已编译（`docs/reference/USB-LOG-CHANNEL.md` 已确认
`ifnet_attach`/`sock_socket`/`mbuf_allocpacket`/`ether_demux` 可用），但 KDP 需要 IOKit NIC，
当前没有。故 P2 之前必须先解决"内核 socket 可用性"这一前置。

---

## 8. 方案（⑤）：本轮只做 P0

| 阶段 | 目标 | 判据 |
|---|---|---|
| **P0（本轮）** | 只读心跳：控制器 + PHY + 时钟寄存器快照，周期打印 | 上机日志出现 `K60 USBHB:` 行，数值与 §2 一致，`capture.json` verdict 正常，**无行为变化** |
| P1 | 复合描述符（CDC IAD + 第二接口） | 主机侧看到 3 接口；控制台仍可用 |
| P2 | mux 协议层 | lockdownd 侧可连接 |
| P3 | Type-C 角色 | GLINK/UCSI 通道有数据 |

**为什么 P0 先做心跳**：现在所有 USB 结论都来自"启动那一刻打印一次"的探针。插拔、挂起、复位、
总线速度变化这些**动态事实**没有任何观测手段。没有心跳，P1 改描述符后一旦枚举失败，无法区分
"描述符错了"还是"控制器掉线了"。

---

## 9. P0 设计（只读、可验证）

**插入点**：`k60_usblog.c` 的 `ud_hb()`（`:1673`）循环体内，每 2 s 一次（与现有节拍一致，不新增线程）。

**读取集合**（全部只读）：

| 寄存器 | 偏移 | 用途 |
|---|---|---|
| `DSTS` | `0xc70c` | 连接状态 + 速度 + 挂起位 |
| `DCTL` | `0xc704` | RUN_STOP / 软复位位 |
| `DALEPENA` | `0xc720` | 端点使能位图 |
| `GEVNTSIZ` | `0xc408` | 事件环大小 |
| `GEVNTCOUNT` | `0xc40c` | 未处理事件数（卡死时会持续非零） |
| `GCC_USB30_PRIM_GDSCR` | `0x49004` | 供电域是否被关 |
| QSCRATCH `HS_PHY_CTRL`/`SS_PHY_CTRL` | `0xa6f8800+0x10`/`+0x30` | VBUS 覆盖是否仍在 |

**安全约束（逐条对应现有代码事实）**：

1. `ud.dwc` 在 worker 映射前为 0（`:1722` 才赋值）→ 心跳必须先判空，打印 `unmapped` 而不是解引用。
2. QSCRATCH 在 `:1810` 是 worker 局部映射，未保留 → 心跳需要自建一次 `ml_io_map(QSCRATCH_PA, 0x100)`，
   失败则打印 `no-qscratch`，不得重试循环。
3. 只调用 `usb_rd()` / `dwc_rd()`，**不调用任何写函数**（`dwc_wr` 一次都不出现）。
4. 不改 `ud` 的任何状态字段（`configured`/`dtr`/`failed` 只读不写）。
5. 打印用 `printf`，与现有 `K60 USBLOG:` 行同格式，前缀单独用 `K60 USBHB:` 便于日志过滤与计数。

**预期输出**（每 2 s 一行）：

```
K60 USBHB: DSTS 0x00020001 DCTL 0x10f00000 DALEPENA 0x0000000f GEVNTSIZ 0x80001000 GEVNTCOUNT 0x00000000
K60 USBHB: GDSC 0xf822f000 QSCRATCH HS 0x10100000 SS 0x01000000
```

**上机验证判据**：

- 两次 `fastboot boot` 同一镜像，日志都出现 `K60 USBHB:`；
- 行数 ≈ 采集时长 / 2 s（允许 ±10%，采集有启动延迟）；
- `DSTS` 在"主机未插"与"主机插上"两种状态下不同（这是心跳真正要证明的东西）；
- `capture.json` `verdict` 与基线一致，`panicMarker` 仍为 null；
- CDC 控制台仍能收发（采集工具本身依赖它，采到日志即证明）。

---

## 10. 证据索引

| 断言 | 出处 |
|---|---|
| DWC3 / eUSB2 / ssphy / nop_phy 地址与长度 | `mondrian.dts:16828,16856,16879,16893,16899` |
| `extcon` 是 dwc3 的角色输入 | `mondrian.dts:16853` |
| pmic-glink / UCSI 在 ADSP 侧 | `mondrian.dts:8555,8567,8568,21364` |
| 现有 CDC-ACM 与 boot-arg | `patches/xnu/series:124,132,138`；`docs/engineering/BOOT-ARGS.md:34` |
| 能力上限（非 usbmux） | `porting.toml:187` |
| 上机寄存器真值 | `E:/k60-work/evidence/usblog-20261114-touchd/console.log` |
| 同 SoC 复合描述符 / 端点布局 | `references/pong-usb/PongUsbDevice.h:60,66-69,214-216` |
| eUSB2 不是 FEMTO | `references/pong-usb/PongUsbPhy.h:142` |
| mux 的 socket 契约 | `references/pong-usb/PongUsbMux.h:58-59,144-146,156-157` |
| AppleUSBXDCI 加载序列 | `references/UniXNU-sheng/package/UsbProbe.cpp:16-47` |
| AppleUSBXDCI vtable ABI | `references/UniXNU-sheng/scripts/gen-usb27-abi.py` |
| GLINK 传输层可复用 | `drivers/PongPower/K60PmicGlink.h`、`QcomGlink.h` |
