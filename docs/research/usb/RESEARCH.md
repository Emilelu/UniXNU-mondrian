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

### 6.4 参考仓可移植性判定（任务书第③步）

| 参考仓 | 里面有什么 | 判定 |
|---|---|---|
| `references/phk110-port/drivers/core/` | 只有 6 个文件：`conf`、`hakios.platform.c`、`hakios.socinfo.c`、`hakios.stubs.c`、`hakios.stubs.cpp`、`hakios.version.c`；`grep -ril "usb\|dwc3\|otg"` **零命中** | **不可移植**——不是"难"，是这个目录里没有任何 USB 控制器 / PHY / 角色切换代码。它是 SM7150 HAKIOS 时代的平台胶水，与本任务无关。 |
| `references/UniXNU-sheng/package/` | USB 相关只有一个 `UsbProbe.cpp`（47 行，见 §7.1）——"已存在驱动"的加载入口胶水（`qcom_dwc3_bring_up` → `OSKextLoadKextWithIdentifier("com.apple.driver.AppleUSBXDCI")`）；真正的控制器驱动 `QcomDwc3.cpp` **不在本仓** | **胶水可抄、驱动本体不可抄**。这恰好解释了为什么 P0/P1 走 DWC3 原生路径（本仓 `0300-k60-usblog-ep0.patch` 已有 1386 行同 SoC 控制器代码），而不是直接接 AppleUSBXDCI。 |
| 本仓 `patches/xnu/0300-k60-usblog-ep0.patch` | 1339 行 `bsd/dev/k60_usblog.c` + `bsd/conf/files` + `arm_init.c` 调用；同 SoC（SM8475）真机验证过 | **唯一真正可复用的控制器代码**，P0 心跳就加在它上面（§9/§11）。 |

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

**插入点**：原计划塞进 `ud_hb()`（`:1673`）的循环体，实测该函数是**整函数压在一行**（全函数体一个逻辑行），
任何插入都会产生上千字符的两行 diff，评审无法阅读。实际实现退一步：新增独立的 `usb_hb()` 线程
（`patches/usb/0405-k60-usb-heartbeat.patch` 第一个 hunk），由 `ud_worker()` 在 `ud.started = true; us = 4;`
之后启动（第二个 hunk）。既有函数体**一个字符都没改**，只多一个只读线程，节拍仍为 2 s。

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

**实际输出**（每 2 s 两行，交替）：

```
K60 USBHB: DSTS 0x00020001 spd 1 halt 0 DCTL 0x80000000 run 1 csft 0 DALEPENA 0x00000003 GEVNTSIZ 0x80001000 GEVNTCOUNT 0x00000004
K60 USBHB: GDSC 0xf822f000 QSCRATCH HS 0x10100000 SS 0x01000000
```

`spd` 是 `DSTS[2:0]`、`halt` 是 `DSTS_DEVCTRLHLT(1<<22)`、`run`/`csft` 是 `DCTL[31]/[30]`，都只是把已有寄存器
的位摊平成可 diff 的字段，不引入任何新常量。GCC 那一路用 `USBHB_GDSCR_PAGE_PA = GCC_PA + 0x49000`
（`0x00149000`，页对齐）单独 map 4 KiB，与触摸线 `docs/research/touch/05-plan.md` 拆 GCC 子窗口的做法一致；
QSCRATCH 因为 worker 里的映射（`:1810`）是局部的，心跳自己再 map 一次 0x100 字节。映射失败只打一行
`K60 USBHB: gcc window map failed; GDSC field omitted` / `… qscratch map failed; VBUS field omitted`，不重试。

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

---

## 11. P0 上机结果（2026-11-14，tag `usb-20261114b`）

**构建**：分支 `feat/usb-console`，head `0b00bc7`（manifest 记录 dirty=0），series 230 条，
sha256 `c21618e49643513a0fe42609de45ba688afb3691338e07657cfc644927426389`，
八步门禁 `通过 30 项检查`，`scripts/verify-boot-image.py` → `verify-boot-image: OK`。

| 组件 | SHA-256 |
|---|---|
| kernel | `f46e6128b7b97391b3c5695f1e5261236e189c68d7bd28f49ca44b6ab73da492`（54181888 B） |
| boot.img | `ef0e905f473a598244df456c7dfc81901038c560d00afb9897bb4f24a6969640` |
| payload | `fe89663f0ac68ab981645d5349cbf2f6ca1eb2746452965596b58621f78e240b` |
| Payloads/kernel.macho | `49ffc428f06dfb2eb690b89b93f79e5ab958099c8af47bf89fa3ca0ee848b6c4` |
| ADT | `18a514e7775a3afbb59ead3af687be1563cf6f036486345116340cdc3b025c1a` |
| DTB | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| FD | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |

manifest：`E:/k60-work/artifacts/usb-20261114b/build-manifest.json`；boot.img：
`E:/k60-work/artifacts/usb-20261114b/boot.img`。

**两次 `fastboot boot` 同一镜像**：

| # | 证据目录 | console.log | capture.json | 心跳行 |
|---|---|---|---|---|
| 1 | `E:/k60-work/evidence/usblog-20261114-usb-hb1/` | 251274 B，sha256 `8BC69E2F…1FEFAD62` | `captured-budget-complete` / complete=true / stopReason=budget / panicMarker=null / resetMarker=`K60 USBLOG: restart reason published` | 300 |
| 2 | `E:/k60-work/evidence/usblog-20261114-usb-hb2/` | 258773 B，sha256 `0BEBFCB9…380FEDB1` | 同上（openErrors=3） | 300 |

两次都进账本：`scripts/record-boot.py` → `✅ recorded series 2e90b3e865611f67 (230 patches)`，
SpringBoard 行数 130 / 134。300 s 后 `K60AUTORESET: 300 s since boot` 自动回 fastboot（boot-arg 既有行为）。

**稳定段数值**（第 1 次，150 个采样里 149 个完全一致）：

```
K60 USBHB: DSTS 0x0083xxxx spd 0 halt 0 DCTL 0x80000000 run 1 csft 0 DALEPENA 0x0000002f GEVNTSIZ 0x80001000 GEVNTCOUNT 0x00000000
K60 USBHB: GDSC 0xf822f000 QSCRATCH HS 0x10100000 SS 0x01000000
```

（`0x0083xxxx` 是 `DSTS` 的高位随时间滚动，低 3 位恒 0；两次上机都是同一个模式。）

**心跳真正证明的动态事实**：

1. 第一条心跳（hb1 `console.log:259`）：`DSTS 0x00020001 spd 1`、`DALEPENA 0x00000003`、
   `GEVNTCOUNT 0x00000004` —— 枚举尚未完成、事件环里还有 4 个未处理事件。**这是过去"开机打印一次"
   的探针看不到的时刻。**
2. `DALEPENA` 依次 `0x00000003` → `0x0000000f` → `0x0000002f` 后稳定（ep0 + 4 个非 0 端点使能）。
3. `GEVNTCOUNT` 只在枚举瞬间非零（0x4 / 0x8 / 0xc），稳定段恒 0：事件环被控制台 gadget 正常排空，
   没有事件堆积，也就没有"控制器卡死"。
4. `halt=0`、`run=1`、`csft=0` 全程成立：300 s 内没有掉进 halt，也没有触发软复位。
5. `GDSC 0xf822f000`（bit31=1）与 `QSCRATCH HS 0x10100000`（VBUS override 仍在）全程不变，
   与 §2 的一次性探针读数完全一致 —— 说明"启动那一刻对、之后被关掉"这种怀疑可以排除。

**行为未变的证据**：同一日志里 `K60 USBLOG: st=4 ev=… cfg=1 dtr=1 fl=0` 两次各 279 行，
与基线 `usblog-20261114-touchd` 同构；采集工具本身走这条 CDC 通路取日志，能采到日志即证明
控制台收发未退化。

**结论**：P0 落地并两次上机验证，控制器在 300 s 运行期稳定，P1（复合描述符）从此有动态观测手段。
**下一步（P1）**：在 0405 之上把配置描述符改成 CDC IAD + 第二接口（`PongUsbDevice.h:60,66-69` 的形态），
判据是主机侧接口数 2→3 且 `K60 USBHB` 行不断流；再往后才是 mux（P2）与 UCSI/Type-C（P3）。

---

## 12. P1 设计：复合描述符（CDC-ACM IAD + 第二功能）

### 12.1 目标与判据

P1 只做**一件事**：让主机看到的配置从「1 个功能 / 2 个接口 / 4 个非 0 端点」变成
「2 个功能 / 3 个接口 / 5 个非 0 端点」，并且控制台不断流。ADSP 侧（UCSI、mux）不在这一步。

判据（**全部满足才算通过**，缺一即按失败处理并回滚）：

| # | 判据 | 观测点 |
|---|---|---|
| 1 | 设备侧收到 98 字节配置描述符请求 | `console.log` 出现 `setup 80 06 0200 00 00 98`（P0 是 `98`→`67` 那条线：`GET_DESCRIPTOR(CONFIG)` 的 wLength 变成 98） |
| 2 | 五个非 0 端点全部使能 | 新增打印 `K60 USBLOG: composite cfg 98 bytes DALEPENA 0x000000ef` |
| 3 | 控制台未退化 | 同一日志里 `K60 USBLOG: st=4 ev=… cfg=1 dtr=1 fl=0` 行数与基线同量级（≥270 行） |
| 4 | 心跳不断流 | `grep -c 'K60 USBHB:'` ≈ 采集时长 / 2 s（±10%） |
| 5 | 主机侧出现 3 个接口 | Windows `Get-PnpDevice` 出现 `USB\VID_1209&PID_0001&MI_00/01/02` 子节点（§12.5） |
| 6 | 采集链路仍工作 | `capture.json` 仍为 `captured-budget-complete`，`panicMarker` 仍为 null |

判据 1–4、6 由设备侧日志给出；判据 5 必须在**同一台主机、同一根线**上采，且在设备枚举后
30 s 内取（自动复位 300 s 后设备回 fastboot）。

### 12.2 改动（`patches/usb/0406-k60-usb-composite.patch`）

只改 `bsd/dev/k60_usblog.c`，26 insertions / 6 deletions：

1. `ud_cfg_template[]` 67 → 98 字节，`bNumInterfaces` 2 → 3；CDC 两接口前插入 **IAD**
   （`8, 11, 0, 2, 2, 2, 1, 0`：firstInterface 0 / interfaceCount 2 / class 2-2-1）；
   末尾追加 **IF2 = vendor specific**（`0xff/0xfe/0x02`）+ `EP 0x03 bulk OUT` + `EP 0x83 bulk IN`。
2. `SET_CONFIGURATION` 追加 `ud_endpoint(6, 2, ud.packet)` 与 `ud_endpoint(7, 2, ud.packet)`，
   `DALEPENA` 掩码 `0x2c` → `0xec`（+bit6/7），并打印一行证据。
3. `CLEAR_FEATURE(ENDPOINT_HALT)` 白名单补 `ep 6/7`（主机可能对任一使能端点发）。
4. 注释指明本节。

字节布局（`E:/k60-work/scratch/usb/check_desc.py` 逐描述符校验：98 字节、14 个描述符、长度自洽）：

| 偏移 | 长度 | 描述符 | 关键字段 |
|---|---|---|---|
| 0 | 9 | config | wTotalLength 98, bNumInterfaces 3, self-powered, 100 mA |
| 9 | 8 | **IAD** | firstIF 0, count 2, class/subclass/proto 2/2/1 |
| 17 | 9 | IF0 | class 2/2/1, 1 endpoint |
| 26 | 5+5+4+5 | CS_INTERFACE | header / call mgmt / ACM / union |
| 45 | 7 | EP 0x82 | interrupt IN, 16 B, interval 16 |
| 52 | 9 | IF1 | class 10/0/0, 2 endpoints |
| 61 | 7 | EP 0x81 | bulk IN 64 B（控制台 TX） |
| 68 | 7 | EP 0x01 | bulk OUT 64 B（主机 RX drain） |
| 75 | 9 | **IF2** | class 255/254/2, 2 endpoints |
| 84 | 7 | **EP 0x03** | bulk OUT 64 B（mux 下行，本阶段不启动传输） |
| 91 | 7 | **EP 0x83** | bulk IN 64 B（mux 上行，本阶段不启动传输） |

端点号 → 物理端点：`0x82`→5（interrupt IN）、`0x81`→3、`0x01`→2、`0x03`→6、`0x83`→7。
`DALEPENA 0xec = bit2|bit3|bit5|bit6|bit7`，与 `PongUsbDevice.h:200-211`（`0x2c | 0xc0`）一致。

### 12.3 为什么设备描述符 class 仍是 `02/02/00`（留给 0407 单步）

0307 已把设备级 class/subclass 设成 `02/02`，让 Windows 用兼容 ID 绑 inbox `usbser.sys`。
复合设备的标准写法是设备级 `0xEF/0x02/0x01` + IAD，但那是**第二个变量**：0406 一旦失败，
就分不清是「多接口布局」错还是「class 变了导致 usbser 不绑」。所以 0406 只动接口与端点，
`0xEF/0x02/0x01` 留到 0407 单独验证一次。

K60 版把 vendor 功能放在 **IF2**（CDC 仍在 IF0/IF1，主机侧 COM 口布局不变）；
同 SoC 的 `PongUsbDevice.h:69-74` 把 mux 放 IF0、CDC 放 IF1/IF2。差异仅此一处，
目的是把「Windows 是否仍绑 usbser」这个已知风险面压到最小。

### 12.4 风险与回滚

| 风险 | 表现 | 处置 |
|---|---|---|
| usbser 拒绝绑定（多接口 + device class 02） | 主机无 COM 口 → 采集为空 | 该次采集按失败处理，`fastboot boot` 回退 `usb-20261114b/boot.img`；主机侧 `Get-PnpDevice` 输出作为唯一证据入证据目录 |
| 主机对 IF2 vendor 功能发控制请求 | `ud_stall()` 兜底，不影响 EP0 状态机 | 无需改动 |
| EP6/EP7 `SETEPCONFIG` 失败 | 日志 `K60 USBLOG: ep%u cmd …` 非零 status，`ud.failed=true` | 回滚 0406 |
| 300 s 自动复位打断采集 | 采集中断 | 既有行为，按 `capture.json` 收口 |

### 12.5 主机侧观测方法（判据 5）

设备枚举后（`fastboot boot` 返回、屏幕亮起 10–30 s 内）在 Windows 侧执行：

```powershell
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like '*VID_1209&PID_0001*' } |
    Select-Object Status, Class, InstanceId | Sort-Object InstanceId
```

- 单接口设备（P0）只有一条 `USB\VID_1209&PID_0001\…`；
- 三接口设备（P1）应额外出现 `&MI_00` / `&MI_01` / `&MI_02` 三条子节点（Windows 对多接口设备
  一律按 `MI_xx` 拆 devnode），CDC 那两条再绑 `usbser.sys` 生成 COM 口；
- COM 口本身：`[System.IO.Ports.SerialPort]::GetPortNames()`（与 `scripts/capture-k60-usblog.ps1`
  同一来源），必须仍能看到采集脚本用的那个口。

判据 5 的原始输出要存进证据目录（`host-pnp.txt`）：「接口数 2→3」在设备侧日志里只能间接看到
（wLength 98 + DALEPENA 0xef），直接证据必须来自主机侧。


## 13. P1 第二次上机：0407 端点/FIFO 诊断（usb-20261114d）

### 13.1 为什么先做诊断而不是继续加功能

`usb-20261114c`（含 0406）上机结果：设备**枚举成功并持续存在**（Windows 侧 `USB\VID_1209&PID_0001\0001`，Class Ports，Service usbser，COM5），但 300 s 采集 **0 字节**（`capture.json` state `opened-no-data`、bytes 0、panicMarker null）。这不是「设备没起来」，而是 gadget 自身不发数据。

唯一的静默返回点是控制台发送门的入口：

```c
if (!ud.configured || !ud.dtr || ud.failed) return;   /* k60_usblog.c:1332 附近 */
```

主机已置 DTR（采集脚本打开端口即拉 DTR），`configured` 也由 SET_CONFIGURATION 置位，所以最可能是 **`ud.failed = true`**。0406 引入的失败源只有一处：把 `ud_endpoint(6, 2, ud.packet)` / `ud_endpoint(7, 2, ud.packet)` 串进同一个 `||` 链，任一非零即 `ud.failed = true; return;`。

机制假设（**尚未证实**）：EP7 是 IN 端点，`DEPCFG` 的 p0 里 FIFO 号 = `ep >> 1` = 3（EP3→1、EP5→2），若该 core 的 TX FIFO 只有 0..2，则 `SETEPCONFIG` 返回非零状态。同 SoC 参考 `PongUsbDevice.h:200-211` 确实也开 6/7 并 `DALEPENA |= 0xc0`，但它的 `muxEnabled` 路径未必在 K60 的 core 配置上跑过 —— 参考实现不能替代本机寄存器证据（铁律 3）。

因此本轮**不引入任何新的硬件假设**，只做两件事：把失败语义从「杀死控制台」改成「打印并降级」，以及把判定 FIFO 预算所需的只读寄存器打进日志。一次上机同时拿到「ep6/ep7 返回值」和「FIFO 配置」，把「描述符错」与「端点错」分开。

### 13.2 改动（`patches/usb/0407-k60-usb-endpoint-diag.patch`）

只改 `bsd/dev/k60_usblog.c`，26 insertions / 9 deletions：

1. **失败语义分离**：EP2/EP3/EP5（控制台必需）仍硬失败并 `ud.failed = true`；EP6/EP7 改成可选，返回码存进局部变量，失败只打印不置 `ud.failed`。
2. **DALEPENA 条件置位**：基线 `| 0x2c`；仅当 `ep6 == 0 && ep7 == 0` 时才 `| 0xc0`，避免使能一个没配好的端点。
3. **证据行**：`K60 USBLOG: composite cfg <n> bytes ep6 <r> ep7 <r> DALEPENA 0x%08x`。
4. **probe 只读快照**：新增一行 `K60 USBLOG: DWC3 GHWPARAMS1 0x… GHWPARAMS3 0x… GTXFIFOSIZ 0x… 0x… 0x… 0x…`（0xC144 / 0xC14C / 0xC300..0xC30C）。

寄存器语义的**证据来源**是同仓参考 UEFI 栈（不是猜测）：`references/uefi-pong/Silicon/Samsung/SamsungPkg/Include/Device/Dwc3.h:141-144`

```c
#define DWC3_GHWPARAMS3_HSPHY_IFC(n)   (((n) & (3 << 2)) >> 2)
#define DWC3_GHWPARAMS3_NUM_EPS(n)     (((n) & (0x3F << 12)) >> 12)
#define DWC3_GHWPARAMS3_NUM_IN_EPS(n)  (((n) & (0x1F << 18)) >> 18)
#define DWC3_GTXFIFOSIZ(n)             (0xC300 + ((n) * 0x04))
```

以及 `Dwc3Core.c:267-269` 用 `GHWPARAMS3_NUM_EPS` 决定物理端点数的既有用法。`GTXFIFOSIZ(n)` 高 16 位是深度（256 B 单位），低 16 位是起始地址 —— 端点 `DEPCFG` 里写的 FIFO 号必须落在这个表里。

### 13.3 判据（usb-20261114d）

| # | 判据 | 通过条件 |
|---|---|---|
| 1 | 控制台恢复 | `grep -c 'K60 USBLOG'` ≥ 250，且出现 `K60 USBHB:` 心跳 |
| 2 | 端点真值 | 日志出现 `composite cfg 98 bytes ep6 <r> ep7 <r> DALEPENA 0x…` |
| 3 | FIFO 真值 | 日志出现 `DWC3 GHWPARAMS1 … GHWPARAMS3 … GTXFIFOSIZ …` |
| 4 | 端点预算自洽 | `(GHWPARAMS3 >> 12) & 0x3f` ≥ 8 且 `(GHWPARAMS3 >> 18) & 0x1f` ≥ 4（EP6 是 OUT、EP7 是 IN，各占一个） |
| 5 | 采集链路 | `capture.json` = `captured-budget-complete`，`panicMarker` null |

判据 1 若仍不成立（依旧 0 字节），则 `ud.failed` 的假设被否证，下一轮改为在 `ud_console()` 入口打印三个门变量的实时值，而不是继续猜。

### 13.4 已知的后续缺陷（本轮不修，登记在此）

`ud_trb_for()` 只有 4 个槽：`0 → UD_TRB_OUT`、`1 → UD_TRB_IN`、`2 → UD_TRB_RX`、`default → UD_TRB_TX`。EP6/EP7 一旦真正开始搬数据会与 EP3 共用 `UD_TRB_TX`。真正启用 vendor 功能（P2）之前必须先把 TRB 槽扩成 8 个，并补 `PongUsbDevice.h:123-140` 的 `transferResource` / `ENDTRANSFER` 收尾逻辑。本轮 0407 只配置端点、不发起任何传输，因此该缺陷不触发。

### 13.5 与 §12.3 的关系

§12.3 原计划把「设备描述符 class 改 `0xEF/0x02/0x01`」作为 0407。诊断优先级更高，该单变量改动顺延为 **0408**，等本轮拿到 ep6/ep7 与 FIFO 真值后再做。

## 14. P1 构建记录：usb-20261114e（等待上机授权）

### 14.1 为什么重建（不是代码问题）

`usb-20261114d` 的内核阶段已经成功，但 bootimg 阶段被合规登记表拒绝：
`unixnu: bootimg refused: the compliance registry failed`，失败项 `iron-4 / iron-5 (0510-k60-bt-firmware-addon.patch) / hard-33 / P-165 / P-166`，
明细是「只在仓库有 zzzz…-pong-touch-bitbang-probe.patch 等三个，只在输入有 0507/0508/0509 三个 bt 补丁」。
根因是共享构建输入树 `/opt/k60/trees/usb-cdc-mainline/device` 在本线同步后 8 分钟被别的线（bt/touch）覆写，
与本线的 0406/0407 无关。

解法：本线改用私有构建输入树 `/opt/k60/trees/usb-device`，先镜像再构建：

```
export K60_DEVICE_INPUT=/opt/k60/trees/usb-device
export K60_SERIES_FINAL=/mnt/e/k60-work/scratch/usb/SERIES-FINAL.txt
python3 scripts/sync-device-input.py      # 同步 4 个文件（0406 / 0407 / patches/usb/series / patches/xnu/series）
python3 scripts/porting-gate.py --quick   # ✅ 门禁通过（6 项警告）
```

同步后 series 三处一致：仓库 / SERIES-FINAL / 构建输入均为 232 行、sha256 `ca9dc29d58e24e0d…`。

### 14.2 产物

| 项 | SHA-256 |
| --- | --- |
| kernel（built） | `93463ccedf7f3770e3ea0e424fb3970491dea1eaa2d170877179cc61b3cf5e0c` |
| boot.img | `2e900d32be2078d24bda3f4df3ce4b622685dc618de2ebe9e3b6a063b266ebf4` |
| payload | `9dd7841329ffa119ba990097d27fdadcc0214675e209af4b3bafdcaf325e9db3` |
| payload kernel | `973cb28345583fa1ef7388adade8ed2e59300eb275b6d07bd6fb2329d8586b19` |
| ADT | `5d5bfc5a3dced62cced72930884b3f390865c391faf00271d66812ab82dd8620` |
| DTB | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| FD | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |
| series（232 条） | `ca9dc29d58e24e0df2d3f886cf5b54c470ad4936f6e555b67d20f630c0c38528` |

manifest：`E:/k60-work/artifacts/usb-20261114e/build-manifest.json`（kernel 54181888 B，series 232 条，
frozen `317469bc3c078b97…`）。

### 14.3 构建期门禁

| 门 | 结果 |
| --- | --- |
| `build-strict.sh`（含 eight-step-gate --build） | ✅ 通过 30 项，`BUILD_EXIT=0` |
| `verify-boot-image.py --manifest` | ✅ `verify-boot-image: OK` |
| `check-rules.py` | ✅ 登记 65 条、失败 0、waiver 37 |
| `check-docs.py` | ✅ 187 项通过 |
| `check-image-args.py --image` | ✅ `OK (29 arguments, 575 bytes)` |

### 14.4 上机计划（待用户与 Lead 批准，未执行）

镜像已就绪但**未 boot**。获准后按 RESEARCH.md §13.3 的五条判据执行：
`fastboot boot usb-20261114e/boot.img` → 300 s 采集 → 第 70 s / 130 s 两次主机侧 `Get-PnpDevice` 采样，
重点读 `composite cfg 98 bytes ep6 %d ep7 %d DALEPENA 0x%08x` 这一行与新增的 `GHWPARAMS1/3 GTXFIFOSIZ` 行。
脚本已备好：`E:/k60-work/scratch/usb/boot0407e.sh`（门禁四连 + boot + 双采样），**当前未运行**。

## 15. P2 前置设计：8 槽 TRB、传输资源收尾、FIFO 预算（尚未实现）

本节是**设计记录**，不包含代码改动。上机被暂停，这里先把下一步要改的东西按证据定下来。

### 15.1 已经能从既有证据读出的结论

`usb-20261114b` 上机日志里 `GHWPARAMS0 0x4020400a`，用参考头文件里的宏可以确定解码
（`references/uefi-pong/Silicon/Samsung/SamsungPkg/Include/Device/Dwc3.h:134-138`）：

| 字段 | 宏 | 值 |
| --- | --- | --- |
| MODE | `GHWPARAMS0 & 0x3` | `0x0a & 3` = **2 = DRD** |
| MDWIDTH | `(GHWPARAMS0 >> 8) & 0xFF` | **64 bit** |

DRD 与 DTS 的 `dr_mode = "otg"`（`scratch/usb/mondrian.dts:16874`）一致，说明该 core 的物理能力里
同时含 device 与 host 两种角色；当前之所以只跑 device，是我们把 `GCTL.PRTCAPDIR` 设成了 device
（同 SoC UEFI 栈 `Dwc3Core.c:243-244` 也是这么做的），不是硬件不支持。

### 15.2 物理端点数是硬件属性，必须读寄存器（不能照抄参考实现）

同 SoC 的 UEFI 栈给出这条链的完整证据：

1. `UsbfnDwc3Dxe.h:11` `#define DWC3_MAX_PHYSICAL_EP 16`（数组上界）；
2. `BoardInit.c:198` `PlatformData->NumEndpoints = 0;` —— 平台层**故意留 0**；
3. `Dwc3Core.c:266-273`：`NumEndpoints` 为 0 时读 `GHWPARAMS3` 的 `NUM_EPS`，再夹到 `[1,16]`；
4. `Dwc3Endpoint.c:176` `if (PhysEpNum >= Dev->NumPhysicalEps) return EFI_INVALID_PARAMETER;`
   —— 端点号越界时**命令根本不会下发**。

这条链正是 0407 要读 `GHWPARAMS3` 的理由：K60 上 EP6/EP7 的 `SETEPCONFIG` 失败，最可能的解释就是
`NumPhysicalEps` 不够（本板可能只暴露 4/6 个物理端点），而不是描述符写错。0407 把这一点变成日志里的一个数。

### 15.3 FIFO 划分在 K60 上没有生产者，只能读回来

在 `references/uefi-pong/.../UsbfnDwc3Dxe/` 里 grep `GTXFIFOSIZ|GRXFIFOSIZ|FifoSize` 命中 **0 次**：
同 SoC 的 UEFI 固件**从不写** TX FIFO 尺寸寄存器，它只是按 `FIFO_NUMBER(PhysEpNum >> 1)`
（`Dwc3Endpoint.c:191`）去**假设**编号 0..3 的 FIFO 存在。也就是说：

- FIFO 表是更早的引导阶段（XBL/ABL）留下的静态配置；
- 「EP7 用 FIFO 3 是否越界」在 K60 上没有任何文档或参考实现能回答，只能把 `GTXFIFOSIZ0..3` 读出来看。

这也是 0407 只加只读打印、不改任何写寄存器的原因。DTS 里 `tx-fifo-resize` 属性存在
（`scratch/usb/mondrian.dts:16873`），说明 Linux 侧同样认为这块需要按实际端点集重新计算，而不是固定值。

### 15.4 P2 要改的三件事（等 0407 数据到位后做）

#### (a) TRB 槽从 4 个扩到 8 个

现状 `ud_trb_for()`（`k60_usblog.c:1029-1036`）只有四个槽：

```c
case 0: return UD_TRB_OUT;   /* 0x1000 */
case 1: return UD_TRB_IN;    /* 0x10c0 */
case 2: return UD_TRB_RX;    /* 0x3040 */
default: return UD_TRB_TX;   /* 0x3000, ep 3 与 ep>=4 共用 */
```

EP6/EP7 一旦真正发传输，会与 EP3 写同一个 TRB（互相踩），必须给每个物理端点独立 64 B 行。
`UD_SIZE = 0x8000`（32 KiB），现有占用到 `0x5000 + 0x1000 = 0x6000`，`0x1300..0x1400` 与
`0x6000..0x8000` 都是空闲的，因此**不需要移动任何既有偏移**（0307 特意给 TRB_IN / TRB_RX 分了独立
cache line，挪动会重新引入伪共享）：

| 物理端点 | 新 TRB 偏移 | 说明 |
| --- | --- | --- |
| 0 | `0x1000` | 不变 |
| 1 | `0x10c0` | 不变 |
| 2 | `0x3040` | 不变 |
| 3 | `0x3000` | 不变 |
| 4 | `0x1300` | 新增（当前未用） |
| 5 | `0x1340` | 新增（interrupt IN，当前只配置不传输） |
| 6 | `0x1380` | 新增（vendor bulk OUT） |
| 7 | `0x13c0` | 新增（vendor bulk IN） |

vendor 端点的数据缓冲同样落在空闲区：`UD_VEND_RX 0x6000`、`UD_VEND_TX 0x7000`（各 4 KiB）。

#### (b) 传输资源收尾（`ENDTRANSFER`）

现在 `ud_epcmd(STARTTRANSFER)` 之后从不记录返回的传输资源号，`ud_reset_endpoints()` 直接
`DWC3_DALEPENA = 0` 就重来。同 SoC 参考实现是显式收尾的（`PongUsbDevice.h:123-140`）：

```c
transferResource[ep] = uint8_t((core.r(DWC3_DEPCMD(ep)) >> 16) & 0x7f);   /* :130 */
if (!cmd(ep, DWC3_DEPCMD_ENDTRANSFER | (1u << 11) | DWC3_DEPCMD_PARAM(transferResource[ep]))) return false;  /* :136 */
```

注释写明「DWC3 requires DEPENDXFER for real active resources before RunStop0；HIPRI_FORCERM11 +
actual STARTTRANSFER resource index; no guessed id」。K60 版要补的是同一个东西：
`uint8_t transferResource[8]`、`ud_start()` 里记下资源号、`ud_reset_endpoints()` 在清 `DALEPENA` 前
逐端点 `ENDTRANSFER`。这不改变控制台行为（EP0/2/3 的传输都会正常完成），但让「重新配置端点」在
vendor 端点有活动传输时也不会残留半截资源。

#### (c) vendor 功能的数据通路

P2 的第一版只做**回环**（EP6 OUT 收到的字节从 EP7 IN 回给主机），目的是证明端点真的能搬数据，
不引入任何协议假设。mux 协议（`pong_usb_mux`，`references/pong-usb/PongUsbMux.h`）留给 P3，
它需要用户态 daemon 与 launchd job，属于另一个量级。

### 15.5 顺序与判据

| 步 | 内容 | 判据 |
| --- | --- | --- |
| P2-a | 8 槽 TRB + `transferResource`/`ENDTRANSFER` | 控制台与心跳完全不变（回归判据同 §13.3 的 1、5） |
| P2-b | EP6/EP7 回环 | 主机用 `UsbTreeView`/`lsusb` 打开 IF2 后写入字节，能在 EP7 读回同一串 |
| P3 | mux 协议 | 需要用户态组件，另立文档 |

P2-a 是**纯结构性**改动，不含新的硬件假设，因此可以在拿到 0407 数据后立刻做；
P2-b 依赖 0407 证明 EP6/EP7 确实可配置。

## 16. P2-a 落地：8 槽 TRB、传输资源收尾（`patches/usb/0408-k60-usb-p2-structure.patch`）

§15 把 P2 拆成三件：(a) TRB 槽 4→8，(b) `transferResource` + `ENDTRANSFER` 收尾，(c) vendor 端点回环。
本节只做 (a) 和 (b) —— 两者都是**纯结构性**改动，不引入任何新的硬件假设，因此不需要 0407 的上机数据就能先落地；
(c) 仍然要等 `usb-20261114e` 证明 EP6/EP7 能配置成功（§13.3 判据 2）。

### 16.1 改动（10 处锚点，全部在 `bsd/dev/k60_usblog.c`）

| # | 位置 | 改动 |
| --- | --- | --- |
| R1 | DMA 布局常量 | 新增 `UD_TRB_EP4 0x1300` / `UD_TRB_EP5 0x1340` / `UD_TRB_EP6 0x1380` / `UD_TRB_EP7 0x13c0` / `UD_VEND_RX 0x6000` / `UD_VEND_TX 0x7000` |
| R2 | `ud_trb_for()` | `case 3..7` 各回自己的槽；`default` 不再是"ep 3 兜底"（8 个物理端点以外不会出现） |
| R3 | 命令常量 | 新增 `DEPCMD_ENDTRANSFER 8`、`DEPCMD_FORCERM (1u<<11)`、`DEPCMD_PARAM(x) ((uint32_t)(x)<<16)` |
| R4 | `struct ud` | 新增 `uint8_t transferResource[8]` |
| R5 | `ud_epcmd()` | 拆成 `ud_epcmd_full(ep, command, p0,p1,p2)` + 一层薄包装 `ud_epcmd()`（ENDTRANSFER 需要把 PARAM 与 FORCERM 一起 OR 进命令字，原签名只接受纯命令号） |
| R6 | `ud_start()` | STARTTRANSFER 成功后读 `(DEPCMD(ep) >> 16) & 0x7f` 存进 `transferResource[ep]` |
| R7 | 新增 `ud_end_transfers()` | 对每个非零资源发 `ENDTRANSFER | FORCERM | PARAM(res)`，成功后清 0 |
| R8 | `ud_reset_endpoints()` | 在 `DALEPENA = 0` 之前调用 R7 |
| R9 | SET_CONFIGURATION 的 deconfigure 分支 | 调用 R7（端点仍然使能，资源需要显式收尾） |
| R10 | 设备事件 type 0（disconnect） | 调用 R7 |

`git diff --stat`: 1 file changed, 55 insertions(+), 6 deletions(-)。

### 16.2 为什么这样改（证据，不是猜测）

- **TRB 槽必须按物理端点分**：原实现 `default: return UD_TRB_TX` 让 ep3 与 ep>=4 写同一个 16 字节 TRB，
  一旦 vendor 端点真的发起传输就会互相踩。新偏移全部落在既有空洞里（现有占用到 `0x5000+0x1000 = 0x6000`，
  `UD_SIZE = 0x8000`），**没有移动任何既有偏移** —— 0307 特意给 `UD_TRB_IN` / `UD_TRB_RX`
  分了独立 cache line（`0x10c0` / `0x3040`），挪动会重新引入伪共享。
- **资源号必须从寄存器读回**：`references/pong-usb/PongUsbDevice.h:130`
  `transferResource[ep] = uint8_t((core.r(DWC3_DEPCMD(ep)) >> 16) & 0x7f);` —— 同 SoC 参考实现就是这么做的。
- **ENDTRANSFER 的命令字**：`PongUsbDevice.h:136`
  `DWC3_DEPCMD_ENDTRANSFER | (1u << 11) | DWC3_DEPCMD_PARAM(transferResource[ep])`，
  注释原文「DWC3 requires DEPENDXFER for real active resources before RunStop0；HIPRI_FORCERM11 +
  actual STARTTRANSFER resource index; no guessed id」。宏值来自 `references/pong-usb/Dwc3Registers.h:98-108`
  （`CMDACT 1<<10` / `PARAM(x) (x)<<16` / `SETTRANSFRESOURCE 0x02` / `STARTTRANSFER 0x06` / `ENDTRANSFER 0x08`）。
- **失败要容忍**：已经完成的传输资源在控制器侧可能已经回收，此时 ENDTRANSFER 会返回非零状态。
  `ud_epcmd_full` 会把状态码打印成 `K60 USBLOG: ep%u cmd 0x%x status %u`（`cmd & 0xf` = 8 即可识别），
  但 `ud_end_transfers()` 本身不置 `ud.failed` —— 收尾失败不应该杀掉控制台。

### 16.3 上机判据（下一次带 0408 的镜像）

| # | 判据 | 判读方式 |
| --- | --- | --- |
| 1 | 控制台**完全不变** | `console.log` 里 `K60 USBLOG` 行数不少于 usb-20261114c 同级水平（≥250），`setup 80 06 0200 len 98` 仍出现 |
| 2 | 心跳不断流 | 每 2 s 一行 `K60 USBHB`，总数 ≈ 时长÷2s ±10% |
| 3 | 收尾不报错 | 出现 `bus reset` / `disconnect` 时**不应**伴随 `ep%u cmd 0x8 status` 之外的异常；允许出现该行（说明资源确实存在过） |
| 4 | 采集仍完整 | `capture.json` `state = captured-budget-complete`、`complete = true`、`panicMarker = null` |

判据 1、2、4 是回归判据（与 §13.3 的 1、5 同构）；判据 3 是本补丁新增的观测点。
**注意**：0408 不改变任何描述符、端点使能位或 PHY 配置，因此主机侧设备树（`MI_00..02` 子节点）不会因为 0408 而变化 ——
那仍然是 §12.3 留给 0409（device class `0xEF/0x02/0x01`）的变量。

### 16.4 与 0407 的关系（为什么 0408 不能替代上机）

0407 提供的是**运行时真值**：EP6/EP7 的 `SETEPCONFIG` 返回值、`GHWPARAMS1/GHWPARAMS3` 的物理端点/FIFO 预算、
`GTXFIFOSIZ0..3` 的实际划分。0408 只在代码层面保证"如果 EP6/EP7 能配起来，它们的 TRB 不会互相踩、
重新配置时资源会被正确收尾"。两者正交：0408 可以独立构建和上机（它不依赖 0407 的日志内容），
但 **P2-b（vendor 回环）必须同时有 0407 的成功结论**，否则回环会挂在不可配置的端点上。

### 16.5 构建与门禁（tag `usb-20261114f`，待构建）

`patches/xnu/series` 现 233 行（末三行 = `../usb/0406`、`../usb/0407`、`../usb/0408`），
三处 series 指纹一致：`sha256 18d72571e489bccf1e1d5e9b6134dba0ab24add21be0e554b064cf051f6ecefe`。
`porting-gate.py --quick` ✅ 通过（7 项警告，均为"第一次跑/内核新鲜度"类），`check-docs.py` ✅ 187 项通过。

**构建输入必须用本线私有树** `/opt/k60/trees/usb-device`：共享的 `/opt/k60/trees/usb-cdc-mainline/device`
已被其他线覆写过两次（§14.1），每次都会让 bootimg 阶段因为 series 不一致被拒。

## 17. 构建记录：`usb-20261114f`（0408 结构改动）

### 17.1 构建输入

| 项 | 值 |
| --- | --- |
| tag | `usb-20261114f` |
| 分支 / HEAD | `feat/usb-console` / `72393b2`（工作区干净，dirty = 0） |
| series | 233 条，`sha256 18d72571e489bccf1e1d5e9b6134dba0ab24add21be0e554b064cf051f6ecefe` |
| frozen | `list_sha256 cfb61522b01990a9049e7c278ea7bbf324f58e548b5bb95d03ea61b756210850` |
| 构建输入树 | **私有** `/opt/k60/trees/usb-device`（`K60_DEVICE_INPUT`） |
| SERIES-FINAL | `/mnt/e/k60-work/scratch/usb/SERIES-FINAL.txt`（`K60_SERIES_FINAL`） |
| FD | `/mnt/e/k60-work/artifacts/fd/usb-20261114b-cf4485712c29.fd` |

为什么必须指定这两个环境变量：共享输入树 `/opt/k60/trees/usb-cdc-mainline/device` 已被其他线覆写两次
（§14.1），`SERIES-FINAL.txt` 的默认路径 `/mnt/e/k60-work/scratch/SERIES-FINAL.txt` 同样是跨线单例。
两者任一被别的线改写，`porting-gate.py` 的 iron-4 / hard-33 就会因为"三处 series 不一致"直接拒绝构建。

### 17.2 产物（`build-manifest.json`）

| 组件 | SHA-256 |
| --- | --- |
| kernel（built） | `784dec66458c40af18ed651b2c2f11f726197edd83f037a00a7a94136a2825e0`（54181888 B） |
| boot.img | `9bfa7cc39c1e5301e7c1074c164ba0831b9c70aa1813efbf7249779dcff5cbaa` |
| payload | `20c126e944128ada8c9e59ccd83b606ffdc4d83b52693929d064589e8e3c77d2` |
| payload kernel | `9a04e745a83474ad2e343499722cc80b837a929d894b2b48994b6540c1dd4b9f` |
| ADT | `a931d084a15732a69ca25049a61a7dc7220a5acb7a76207990a1fbd309c6481a` |
| DTB | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`（与 usb-20261114b/c/e 完全相同） |
| FD | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |

manifest：`/mnt/e/k60-work/artifacts/usb-20261114f/build-manifest.json`

### 17.3 门禁（全绿）

| 门禁 | 结果 |
| --- | --- |
| `eight-step-gate.py --build` | ✅ 通过 30 项（`eight_step_sha256 9ea6bd823c148afec8c3e8f9a7f8ce0f1a10693b0e70780aec80ca082a8fbb1e`） |
| `verify-boot-image.py --manifest` | `verify-boot-image: OK`（rc=0） |
| `check-image-args.py --image` | `image-arg-audit: OK (29 arguments, 575 bytes)`（rc=0，上限 607 B） |
| `check-rules.py` | ✅ 登记 65 条 / 失败 0 / waiver 37 |
| `check-docs.py` | ✅ 187 项通过 |

### 17.4 补丁确实进了镜像

`logs/kernel.log:250` = `== kernel: patch 0408-k60-usb-p2-structure.patch`
（:247 = 0405、:248 = 0406、:249 = 0407、:250 = 0408，四条按序全部应用）。
构建缓存源码 `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/bsd/dev/k60_usblog.c`
共 **2099 行**（post-0407 基线 2050 行 + 0408 的 55 增 6 删），`transferResource` 命中 4 处、
`ud_end_transfers` 命中 4 处、`DEPCMD_ENDTRANSFER 8` 在 :920、`UD_TRB_EP7 0x13c0` 在 :948、
`case 7: return UD_TRB_EP7;` 在 :1055、`ud_end_transfers` 的 ENDTRANSFER 发送在 :1136。

### 17.5 上机计划（**未执行**，等用户批准）

脚本 `E:/k60-work/scratch/usb/boot0408f.sh` 已写好但**没有运行**（用户 m01929「禁止擅自 boot」）。
批准后的动作序列：门禁四连（`porting-gate --quick` / `eight-step-gate --flash` / `check-boot-procedure` / `research-gate`）
→ `adb reboot bootloader` 等 fastboot（150 s 上限）→ `boot-and-capture.ps1`
`-Image E:\k60-work\artifacts\usb-20261114f\boot.img -Seconds 300`
`-OutDir E:\k60-work\evidence\usblog-20261114-usb-f1 -Serial 6033dbec`
→ 第 70 s / 130 s 各采一次 `host-pnp.ps1` → 收 supervisor rc。
判据见 §16.3（回归性质：控制台不变、心跳不断流、收尾不报错、采集完整）。

## 18. 静态复核：`usb-20261114f` 一张镜像同时回答 0407 与 0408

### 18.1 关键发现：不需要两次上机

`usb-20261114f` 的 series 是 233 条，**0405 / 0406 / 0407 / 0408 四条全部在镜像里**
（`logs/kernel.log:247-250`）。对构建产物 `kernel.macho`
（`/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho`，
54181888 B，`sha256 784dec66458c40af…` 与 manifest 的 `kernel_built` 一致）做 `strings -a` 复核：

| 检查项 | 结果 |
| --- | --- |
| `K60 USBLOG` 格式串总数 | 66 |
| 0407 的 `DWC3 GHWPARAMS1 0x%08x GHWPARAMS3 …` | ✅ 命中 1 |
| 0407 的 `composite cfg %u bytes ep6 %d ep7 %d DALEPENA 0x%08x` | ✅ 命中 |
| 0408 的 `K60 USBLOG: ep%u cmd 0x%x status %u` / `… timeout` | ✅ 命中（`ud_epcmd_full` 改名后仍在） |

⇒ **一次上机（f）就能同时拿到**：
1. 0407 的运行时真值 —— `GHWPARAMS1/GHWPARAMS3`、`GTXFIFOSIZ0..3`、`ep6/ep7` 的 `SETEPCONFIG` 返回值；
2. 0408 的结构回归 —— 8 槽 TRB + 资源收尾是否破坏控制台/心跳。

原本准备的两张镜像（e = 0407、f = 0408）**可以只上 f**，e 留作 0407 单独隔离用的备份
（若 f 出现异常需要把 0408 这个变量排除时再上）。

### 18.2 补丁静态复核（153 行 diff，逐处确认无越界）

| 检查点 | 结论 |
| --- | --- |
| DMA 偏移是否重叠 | `UD_TRB_EP4..EP7 = 0x1300/0x1340/0x1380/0x13c0` 位于 `UD_DATA 0x1100`（512 B，到 `0x1300` 为止）与 `UD_TRB_TX 0x3000` 之间，**无重叠**；`UD_VEND_RX 0x6000` / `UD_VEND_TX 0x7000` 各 4 KiB，上界 `0x8000 = UD_SIZE`，**不越界** |
| 既有偏移是否被移动 | 未移动任何一个（`UD_TRB_IN 0x10c0` / `UD_TRB_RX 0x3040` 保持 0307 的独立 cache line） |
| `ud_epcmd` 语义是否改变 | 否：新 `ud_epcmd_full` 与原实现逐行等价（只把形参 `cmd` 改名 `command`），`ud_epcmd` 变成一行转发；所有既有调用点行为不变 |
| `ud_start` 是否新增失败路径 | 否：`rc == 0 && ep < 8` 才读资源号，读的是只读的 `DEPCMD` 状态位，不写寄存器 |
| `ud_end_transfers` 失败是否杀控制台 | 否：`(void)ud_epcmd_full(...)` 丢弃返回值，不置 `ud.failed`；最坏情况是打印一行 `ep%u cmd 0x8 status %u` |
| 三处调用点的时序 | `ud_reset_endpoints()` 在 `DALEPENA = 0` **之前**；deconfigure 分支在清 `dtr/tx/rx/log_ready` 之前；disconnect 分支同理 —— 都是“端点仍使能时收尾”，符合 `PongUsbDevice.h:136` 的注释（before RunStop0） |
| 是否有新的 MMIO 假设 | 无。所有寄存器偏移都来自已上机验证过的既有代码或 `Dwc3Registers.h` |

### 18.3 合并后的上机判据（一次上机，六条）

| # | 判据 | 来源 | 判读 |
| --- | --- | --- | --- |
| 1 | 控制台不断流 | 回归 | `console.log` 里 `K60 USBLOG` ≥250 行，`setup 80 06 0100 len 64` 与 `setup 80 06 0200 len 98` 都出现 |
| 2 | 心跳不断流 | 回归 | 每 2 s 一行 `K60 USBHB`，总数 ≈ 时长 ÷ 2 s ±10% |
| 3 | **物理端点预算** | 0407 | `K60 USBLOG: DWC3 GHWPARAMS1 0x… GHWPARAMS3 0x… GTXFIFOSIZ …` 出现；`(GHWPARAMS3>>12)&0x3f ≥ 8`（否则 EP6/EP7 物理上不存在）、`(GHWPARAMS3>>18)&0x1f ≥ 4` |
| 4 | **EP6/EP7 配置结果** | 0407 | `K60 USBLOG: composite cfg 98 bytes ep6 0 ep7 0 DALEPENA 0x000000ef` —— `ep6/ep7` 都是 0 才能进 P2-b 回环；非 0 则说明 FIFO 或端点号越界，P2-b 需要改端点分配 |
| 5 | 收尾不报错 | 0408 | 允许出现 `ep%u cmd 0x8 status %u`（说明资源确实存在过），但不应出现 `ud.failed` 之后的控制台中断 |
| 6 | 采集完整 | 回归 | `capture.json` `state = captured-budget-complete`、`complete = true`、`panicMarker = null` |

判据 3 和 4 是**新信息**，只有 0407 的打印能给出；判据 1、2、5、6 是 0408 的回归面。这也是为什么 f 一张镜像足够。

### 18.4 仍未执行的唯一原因

用户 m01929：“禁止擅自 boot”。两张镜像、脚本（`boot0407e.sh` / `boot0408f.sh`）与证据目录都已就绪，
设备 `6033dbec` 停在 fastboot，本轮**没有**任何 `fastboot boot` / `boot-and-capture.ps1` 进程。
批准后**只需跑 f**（`E:/k60-work/scratch/usb/boot0408f.sh`），预计 300 s 采集 + 约 2 min 起机。

## 19. 判据执行器：`docs/research/usb/analyze-capture.py`

§13.3 / §16.3 / §18.3 的判据此前只写在文档里，每次上机都要手工 `grep`。本节把它变成一个只读脚本，
上机后一条命令出结论：

```
python3 docs/research/usb/analyze-capture.py /mnt/e/k60-work/evidence/usblog-<stamp>
```

退出码 0 = 无 FAIL，1 = 有 FAIL，2 = 用法/证据目录错误。脚本**只读**，不修改证据。

### 19.1 三个必须编码进脚本的坑（都是本轮实际踩到的）

| 坑 | 现象 | 处理 |
| --- | --- | --- |
| PowerShell 写 JSON 带 UTF-8 BOM | `json.load` 抛 `Unexpected UTF-8 BOM (decode using utf-8-sig)` | 所有 JSON 读取统一 `encoding="utf-8-sig"` |
| 一次心跳打印**两行** | `K60 USBHB` 行数 = 2 × tick 数（`DSTS` 行 + `GDSC/QSCRATCH` 行）；hb1 里 300 行 = 148 tick | 只数 `^K60 USBHB: DSTS` |
| 0 字节采集没有描述符信息 | 判据 3/4 会误报 FAIL | 采集 0 字节或缺 98 字节配置请求时，判据 3/4 报 **SKIP**（附原因），不计入失败 |

### 19.2 校准（用已有证据反向验证）

| 证据 | 结果 | 说明 |
| --- | --- | --- |
| `usblog-20261114-usb-hb1`（P0，0405） | **ALL PASS**（4 pass / 0 fail / 2 skip） | 279 行 `K60 USBLOG`、148 tick（320 s 采集，期望 160，±10% 内）、`panicMarker=null` |
| `usblog-20261114-usb-hb2`（P0，0405） | **ALL PASS**（4 / 0 / 2） | 与 hb1 同镜像，可重复性确认 |
| `usblog-20261114-usb-c1`（P1，0406） | **FAIL**（0 / 4 / 2） | 0 字节、无心跳、`state=opened-no-data` —— 正是 §13 要诊断的现象，脚本判 FAIL 正确 |

判据 3/4 在 hb1/hb2 上是 SKIP（镜像早于 0406，主机从未请求 98 字节配置），在 c1 上也是 SKIP（0 字节，
镜像根本没说话）—— 这两种 SKIP 的原因文本不同，便于区分"镜像没这段代码"和"镜像没出声"。

### 19.3 上机后的用法

`usb-20261114f` 上机后：

```
python3 docs/research/usb/analyze-capture.py /mnt/e/k60-work/evidence/usblog-20261114-usb-f1
```

期望：6 条全 PASS（判据 3 要求 `NUM_EPS ≥ 8` 且 `NUM_IN_EPS ≥ 4`；判据 4 要求 `ep6=0 ep7=0 DALEPENA=0x000000ef`）。
任一条 FAIL 时脚本会把寄存器原值和期望值并排打印，可直接对照 §18.3 判读。

## 20. 上机结果决策树（`usb-20261114f` → 下一步补丁）

§18.3 的六条判据给出一组读数，本节把这组读数映射到**具体的下一个补丁**。
所有分支都只依赖 0407 打印的两个真值：`GHWPARAMS3` 的端点预算、`composite cfg` 行的 `ep6/ep7` 返回值。

### 20.1 期望值是怎么算出来的（不是猜的）

| 量 | 期望 | 推导 |
| --- | --- | --- |
| `DALEPENA` | `0x000000ef` | 复位后 `0x3`（bit0 EP0 + bit1 EP1）→ `ud_endpoint(2/3/5)` 成功后 `|= 0x2c`（bit2/3/5）→ EP6/EP7 都成功再 `|= 0xc0`（bit6/7）= `0b1110_1111` |
| `ep6` | `0` | `ud_endpoint(6, 2, packet)` 的返回值；`-1` 表示 `DEPCMD_SETEPCONFIG` 或 `SETTRANSFRESOURCE` 报错（`k60_usblog.c` 的 `ud_epcmd_full` 打印 `ep6 cmd 0x1 status N`） |
| `ep7` | `0` | 同上，但 EP7 是 IN 端点，`p0 |= (7>>1)<<17` = FIFO 3 |
| `NUM_EPS` | `≥ 8` | `(GHWPARAMS3>>12)&0x3f`，同 SoC UEFI `Dwc3Core.c:266-273` 用的就是这两位 |
| `NUM_IN_EPS` | `≥ 4` | `(GHWPARAMS3>>18)&0x1f`（`Dwc3.h:144`） |

### 20.2 分支表

| 分支 | 读数 | 结论 | 下一个补丁 |
| --- | --- | --- | --- |
| **A** | `NUM_EPS≥8`、`NUM_IN_EPS≥4`、`ep6=0`、`ep7=0`、`DALEPENA=0xef`、控制台活着 | 复合设备在**端点层面**成立，`usb-20261114c` 的 0 字节不是端点配置失败造成的 | **0409** = vendor 端点回环（P2-b）：EP6 OUT 收到的字节从 EP7 IN 回送，主机侧用 `IF2` 的 bulk 对验证 |
| **B** | `ep6=0` 但 `ep7≠0`，且 `GTXFIFOSIZ3 = 0` | EP7 的 FIFO 3 在这颗 core 上**没实现**；IN 端点的 FIFO 号是软件选的（`ud_endpoint` 里的 `(ep>>1)<<17`），可以改 | **0409** = 给 EP7 指定一个 `GTXFIFOSIZ(n)≠0` 的 FIFO 号（候选由打印值决定），**一次只改这一个变量** |
| **C** | `ep6≠0` | EP6 是 OUT 端点、不需要 FIFO，它失败只能是端点号越界（`Dwc3Endpoint.c:176` 的 `PhysEpNum >= NumPhysicalEps` 分支） | **0409** = 把 vendor 功能从 EP6/EP7 下移到 `NUM_EPS` 允许的号段；同时把 `ud_cfg_template` 里的端点号一起改（描述符与 `ud_endpoint` 必须同时改，否则主机会等一个不存在的端点） |
| **D** | `NUM_EPS < 8` | 这颗 core 的物理端点少于 8 个，EP6/EP7 根本不存在 | **0409** = 去掉 IF2 的两个端点，退回 IAD + CDC（2 接口）复合；P2-b 在这颗 core 上不可行，写进 RESEARCH 作为定论，并转 0410（device class） |
| **E** | 又回到 0 字节（`state=opened-no-data`） | 0407 的「可选端点」没有救回控制台 → 失败点不在 EP6/EP7，而在 0406 的描述符本身 | 先上 **`usb-20261114e`**（0407 无 0408）隔离 0408；仍 0 字节则回退到 `usb-20261114b`（无 0406）并重新设计 IF2 |

分支 A 是唯一能直接推进到 P2-b 的；B/C/D 都要求**先读打印值再决定参数**，这正是不允许猜寄存器的原因。

### 20.3 0410（device class）的定位

§12.3 把 device descriptor 的 class 从 `02/02/00` 改成 `EF/02/01` 留成单独一步。它**不依赖**上面任何一个分支，因此编号取 **0410**（0409 留给分支 A/B/C/D 选出的那一步，避免两个补丁抢同一个号）：

- 现状：class `02/02` 让 Windows 把**整个设备**当串口（`usb-20261114c` 主机侧只有一个 devnode、`CompatibleIds` 是 `USB\Class_02&SubClass_02`，没有 `MI_00..02`）。
- 改成 `EF/02/01` 后，Windows 走 `usbccgp`，把 IF0+IF1（IAD 已声明）交给 `usbser.sys`，IF2 交给 vendor 驱动 —— 这是 IAD 生效的**必要条件**。
- 风险：一旦 `usbccgp` 不绑，控制台会**整条消失**（不是降级）。所以它必须在分支 A 之后单独上机，且要准备好回退镜像。

草稿已生成并本地验证（**未入库、未进 series**）：`E:/k60-work/scratch/usb/0410-k60-usb-device-class-composite.patch`（22 行，只改 `ud_dev_desc[18]` 的 3 个字节 `2, 2, 0` → `0xef, 0x02, 0x01`）；对 post-0408 源 `patch -p1 --dry-run` → `APPLY_OK`。是否入库由 §20.2 的分支结论决定（分支 D 会先走它，其余分支先走 0409）。

### 20.4 当前状态

- 镜像 `usb-20261114f` 已构建、门禁全绿、**未上机**（用户 m01929 禁止擅自 boot）。
- 脚本 `E:/k60-work/scratch/usb/boot0408f.sh` 就绪；执行后先跑 `docs/research/usb/analyze-capture.py` 再按本节分支表决策。


## 21. 0409 控制台恢复镜像 usb-20261114g（诊断优先）

### 21.1 为什么先恢复控制台

两张复合描述符镜像（`usb-20261114c` = 0406；`usb-20261114f` = 0406+0407+0408）在主机侧都正常枚举：
Windows 建出 `USB\VID_1209&PID_0001\0001`，`Service=usbser`，`FriendlyName=USB Serial Device (COM5)`，
采集器能看到 COM5、能打开、DTR 置位，但 300 s 采集窗口内 **0 字节**（`capture.json` state =
`opened-no-data`、`bytes=0`、`logSha256=E3B0C442…` 即空文件）。而 67 字节两接口时代的两张镜像
（`usb-20261114b`、两次上机 251274 B / 258773 B，K60 USBLOG 279 行、心跳 148 tick）都正常。

⇒ 设备能起来（用户 m02429/m02433 确认镜像进了系统、300 s 后回 fastboot 是 `k60_autoreset=300`
的设计行为），失败点在 gadget 自身：**控制台没有数据**。而没有控制台就永远读不到 0407 想拿的
`GHWPARAMS1/GHWPARAMS3/GTXFIFOSIZ0..3` 与 `ep6/ep7` 返回值，P2 的端点预算判据无法成立。
所以下一步必须先恢复一个能出字节的控制台，把"诊断"和"复合描述符"两个变量分开。

### 21.2 0409 改了什么

`patches/usb/0409-k60-usb-console-restore.patch`（35 行，只改 `bsd/dev/k60_usblog.c` 的
`ud_cfg_template[]`）：

| 项 | 0406（复合） | 0409（恢复） |
| --- | --- | --- |
| 配置描述符长度 | 98 字节 | **67 字节** |
| bNumInterfaces | 3 | **2** |
| IAD (8, 11, …) | 有 | 无 |
| IF0/IF1 | CDC comm / CDC data | CDC comm / CDC data（不变） |
| IF2 | vendor 0xff/0xfe，EP 0x03 OUT / 0x83 IN | 无 |

保留不动（关键）：

- 0407 的 `ud_endpoint(6, 2, ud.packet)` / `ud_endpoint(7, 2, ud.packet)` 仍会在 SET_CONFIGURATION 里执行，
  失败只打印、不置 `ud.failed`；
- 打印 `K60 USBLOG: composite cfg %u bytes ep6 %d ep7 %d DALEPENA 0x%08x` 仍在，
  于是这张镜像**同时**给出「控制台是否恢复」与「EP6/EP7 是否可配置」两件事；
- 0407 的 `GHWPARAMS1/GHWPARAMS3/GTXFIFOSIZ` probe 打印仍在。

字节自检（`E:/k60-work/scratch/usb/check0409.py`）：67 B、10 个描述符全部长度自洽
（config 9 / IF0 9 class 2/2/1 / CS_INTERFACE 5+5+4+5 / EP 0x82 int 16 / IF1 9 class 10/0/0 /
EP 0x81 bulk 64 / EP 0x01 bulk 64），`bNumInterfaces=2`。

### 21.3 构建 usb-20261114g

- 提交 `9ce7d2c` "feat(usb): restore the two-interface console descriptor for diagnosis (0409)"，
  分支 `feat/usb-console`，工作区干净。
- series：`patches/xnu/series` 234 行，末行 `../usb/0409-k60-usb-console-restore.patch`；
  三处指纹一致 `88846d3552c8b0042bfef9ae092c5d32cf92bb6c3edd8c181e841b10cf2bac0e`
  （仓库 / `/opt/k60/trees/usb-device` / `SERIES-FINAL.txt`）。
- 构建环境：`K60_DEVICE_INPUT=/opt/k60/trees/usb-device`（私有树）、
  `K60_SERIES_FINAL=/mnt/e/k60-work/scratch/usb/SERIES-FINAL.txt`。
- 产物（`/mnt/e/k60-work/artifacts/usb-20261114g/build-manifest.json`）：

| 产物 | SHA-256 |
| --- | --- |
| kernel（built） | `438de64f08af16c5c227817a86eef87b1c0a9c042e18d946036904c33d5ed8ae`（54181888 B） |
| boot.img | `3cba15c8a119606fd16125e2455b820c087e7ca3c4044711e0d4081e98faf695` |
| payload | `5841d4893962c63a86e4e6e5d77feba786466c1e06673f09c7b7a1e31d997c9a` |
| payload kernel | `ac001a5c19e3423d189b6cf64fa963673d81c3b1c468059224d3fc7aed6e4f06` |
| ADT | `2d37bd30c67e3d9c4031e6655f48557a55e6ca845bff631eb6beced05b87ef42` |
| DTB | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`（未变） |
| FD | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |
| frozen list | `2e1ddcdf35e2925db781b6764b3381117a421fb23c37c0579a6106f069a3e9f9` |

- 门禁：eight-step `--build` 通过 30 项；`verify-boot-image.py --manifest` → `OK`；
  `check-image-args.py` → `image-arg-audit: OK (29 arguments, 575 bytes)`；
  `check-rules.py` 登记 65 条 / 失败 0 / waiver 37；`check-docs.py` 187 项通过；
  `porting-gate.py --quick` ✅ 通过（7 警告）。
- 补丁进镜像证明：`logs/kernel.log` 中 234 条 `== kernel: patch`，USB 线依次
  0405 / 0406 / 0407 / 0408 / **0409**；构建缓存源码
  `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/bsd/dev/k60_usblog.c`
  73313 B，`:1182` 是 `9, 2, 67, 0, 2, 1, 0, 0xc0, 50`，`9, 2, 98` 命中 0，
  `:1320` 仍是 `composite cfg %u bytes ep6 %d ep7 %d DALEPENA 0x%08x`。

### 21.4 上机判据（由 Lead 执行）

| # | 判据 | 期望 |
| --- | --- | --- |
| 1 | 控制台恢复 | `K60 USBLOG` ≥ 250 行，`setup 80 06 0100 len 64` 出现，**不再**出现 `setup 80 06 0200 len 98` |
| 2 | 心跳 | 每 2 s 一行 `K60 USBHB`，tick ≈ 采集秒数 ÷ 2（±10%） |
| 3 | 物理端点预算 | `(GHWPARAMS3 >> 12) & 0x3f` = NUM_EPS，`(>> 18) & 0x1f` = NUM_IN_EPS |
| 4 | FIFO 表 | `GTXFIFOSIZ0..3` 四个值（决定 EP6/EP7 的 FIFO 号是否合法） |
| 5 | EP6/EP7 | `composite cfg 67 bytes ep6 0 ep7 0 DALEPENA 0x000000ef`（EP6/EP7 成功）或非零返回值（失败，按 §20.2 分支 B/C） |
| 6 | 采集完整 | `capture.json` = `captured-budget-complete`、`complete=true`、`panicMarker=null` |

判读命令：`python3 docs/research/usb/analyze-capture.py <evidence-dir>`（判据 3/4/5 需要人工看寄存器原值，
执行器只覆盖 1/2/6 与"是否出现 98 字节请求"）。

### 21.5 权限边界

上机权限只保留给 Lead（用户 2026-11-14 明确要求）：本线只产出镜像、脚本与判据，
`fastboot boot` 与 `boot-and-capture.ps1` 由 Lead 执行。设备 `6033dbec` 本轮停在 fastboot 未动。

## 22. QMP PHY 与 UCSI：主机侧可验证部分（2026-11-14）

Lead 指派（m02635）"把 QMP PHY 与 UCSI 的 host 可验证部分做完"。本节只记录**不依赖 ADSP 固件字节、
不依赖上机**就能定论的内容，细节分别落在两份独立文档里：

- `docs/research/usb/QMP-PHY.md`（325 行）：SS PHY `ssphy@88e8000` 的 13 项 reg-offset 解码、
  164 条 init-seq 分区与逐条比对、Pong override-seq、主线上电时序。
- `docs/research/usb/UCSI.md`（336 行）：UCSI over pmic_glink 的线格式、角色裁决表、
  K60 侧已有 GLINK 通道与 owner 分流点。
- `docs/research/usb/qmp-phy-table.py`：可重跑的表提取/校验器（`--check` / `--emit-c`）。
- `docs/research/usb/ucsi-host-selftest.c` + `UCSI-SELFTEST-OUTPUT.txt`：主机自测，`RESULT: PASS`。

### 22.1 QMP PHY：三条结论

1. **13 项 `qcom,qmp-phy-reg-offset` 与下游枚举 1:1 对应，无歧义。**
   权威枚举是 `phy-msm-ssusb-qmp-sm8450.c:82-101`（`enum qmp_phy_rev_reg`，13 实项 + MAX），
   解析代码在 `:1066-1086`。逐项：`0x1c14`=PCS_STATUS、`0x1f08`=AUTONOMOUS_MODE_CTRL、
   `0x1f14`=LFPS_RXTERM_IRQ_CLEAR、`0x1c40`=POWER_DOWN_CONTROL、`0x1c00`=SW_RESET、
   `0x1c44`=START、`0xffff`=PCS_MISC_TYPEC_CTRL（哨兵）、`0x08`=DP_COM_POWER_DOWN_CTRL、
   `0x04`=DP_COM_SW_RESET、`0x1c`=DP_COM_RESET_OVRD_CTRL、`0x00`=DP_COM_PHY_MODE_CTRL、
   `0x10`=DP_COM_TYPEC_CTRL、`0x1e00`=PCS_MISC_CLAMP_ENABLE。
   前六项与主线 v6 布局交叉验证全部吻合（`phy-qcom-qmp-combo.c:1476-1490` +
   `phy-qcom-qmp-pcs-v5.h:10-13` + `phy-qcom-qmp-pcs-usb-v5.h:12/15`）；
   **唯一偏离主线的是 clamp = `0x1e00`（主线 `0x1a0c`）——以 DT 为 K60 真值。**
2. **serdes 表不能套用主线 sm8550 的表。** 164 条 init-seq 里 32 条与主线不同，
   其中 24 条集中在 serdes 的 PLL/SSC/LOCK_CMP/BIN_VCOCAL/DEC_START 段
   （`0x1000/0x1004/0x1020-0x1038/0x1050-0x1064/0x1080-0x1098/0x10bc/0x10cc/0x10d0/0x1174`），
   是另一套 24 MHz XO 的 PLL 参数；tx/pcs 表逐条相同，rx 只差 `RX_MODE_00_*` 四条与
   `UCDR_SB2_GAIN2`。**写入时必须按 rxa/rxb 两块分别写**（DT 已按 lane 展开成两份）。
   唯一"主线有、DT 无"的寄存器是 `0x1f00` `QPHY_USB_V6_PCS_USB3_POWER_STATE_CONFIG1 = 0x68`，
   列入未决，不擅自补写（铁则 3）。
3. **上机证据表明 SS PHY 从未上电。** `usblog-20261114-usb-hb2/console.log:269` 是
   `connected, speed 0`（`DSTS[2:0]=0` = HIGHSPEED），全程只有 eUSB2 路径；
   QMP 段零初始化。因此 P2 若要走 SS，第一步是 `qmp_combo_usb_init` 等价流程
   （serdes → tx/rx lane → pcs → pcs_usb → 清 SW_RESET → START=0x03 → 轮询 PHYSTATUS）。

### 22.2 UCSI：三条结论

1. **角色裁决规则有官方原句**（`UniXNU-upstream/docs/porting/usb.md:100-101`）：
   线上是主机 → 设备角色；线上是外设 → 主机角色；无回答 → 设备角色。
   落到 `UCSI_CONSTAT_PARTNER_TYPE`（`ucsi.h:260-263`）：DFP→device、UFP/CABLE_AND_UFP→host、
   DEBUG/AUDIO→device、CABLE/未连接→device。该表已被自测第 4/6 组固化。
2. **K60 已经有这条通道，只是只服务电池。**
   `K60PmicGlink.cpp:84` 在 `PMIC_RTR_ADSP_APPS` 上开通道，
   `K60Battmgr.c:149` 用 `le32(data) != 32778` 过滤 owner —— **32779 的 UCSI 消息现在被静默丢弃**。
   接入点是在 `K60Battery::receive()`（`K60Battery.cpp:284-289`）里按 owner 分流，
   与主线 `pmic_glink.c:84/90` 的 client-list 语义同构；通道只有一条
   （`QcomGlink.h:17` `QCOM_GLINK_MAX_CHANNELS 1u`），不该为 UCSI 再开一条。
3. **DT 不需要改。** 随镜像的 `hardware.dtb`（sha256 `2d044eaa…f33cd`，210 行）
   只有 `pmic-glink` + `battery-charger`，没有 `qcom,ucsi`/`qcom,altmode`；
   而主线 `pmic_glink.c:131/272/277` 把 UCSI/altmode/power-supply 建成 auxiliary device，
   **不读 DT 子节点**。走 owner 注册模型就不需要 DT 改动（片段仍写在 `UCSI.md` §10 备用）。

### 22.3 仍被阻塞的两点（诚实记录）

- **ADSP 不在线**：`usblog-20261114-usb-hb2/console.log` 里 `adsp|glink` 命中 0 次；
  0612/0613/0614 三个补丁只到 PAS 的 SMC 封装与调用点，未见任何 `K60PAS` 输出。
- **GLINK lease 无生产者**：`docs/research/battery/GLINK-HANDOFF.md:14` 记录
  `k60-adsp-glink-handoff` 只有消费点。电池、音频、UCSI 三条线共用这个前置。

### 22.4 复现

```sh
python3 docs/research/usb/qmp-phy-table.py --dts /mnt/e/k60-work/scratch/usb/mondrian.dts --check
python3 docs/research/usb/qmp-phy-table.py --dts /mnt/e/k60-work/scratch/usb/mondrian.dts \
    --emit-c --out /tmp/kQmpPhyK60.h
cc -std=c11 -Wall -Wextra -o /tmp/ucsi-host-selftest docs/research/usb/ucsi-host-selftest.c \
    && /tmp/ucsi-host-selftest
```

## 23. 0410：vendor 端点回环（P2-b）

### 23.1 0410 是什么（P2-b：vendor 端点回环）

§15.4(c) 定义的 P2-b 现在有了实现：`patches/usb/0410-k60-usb-vendor-loopback.patch`
（14 hunks，全部在 `bsd/dev/k60_usblog.c`）。P2-a（8 槽 TRB + `transferResource`/
`ENDTRANSFER` 收尾）已由 0408 完成，0410 只加回环数据通路，两者判据分开验证。

**单变量原则用 boot arg 控制**（`k60_usbvend`，`k60_usbvend_arg()` 解析，
`k60_usblog_init()` 里赋值）：

| 值 | 描述符 | 回环位置 | 主机侧验证方法 |
| --- | --- | --- | --- |
| 0（默认） | 67 字节两接口 CDC-ACM（0409 原样） | 无 | 与 0409 逐字节同：控制台必须不变 |
| 1 | 98 字节复合（IAD + IF2 `0xff/0xfe`，EP `0x03` OUT / `0x83` IN） | EP6→EP7 | 需要裸 USB 工具（Windows 无 libusb；用 LAN 上的 Mac + IOKit，或 WSL usbip） |
| 2 | 67 字节控制台描述符不变 | CDC 数据对 EP2→EP3（`ud_console()` 让位） | 普通 COM 口即可：打开串口发字节，同一口读回应为原样回显 |

mode 2 的价值：**不用 libusb 就能验证回环机制**——主机打开 COM 口，
写入的字节从 EP2 进、EP3 出，主机读到回显即判据通过；控制台输出在该模式下
有意让位（`ud_console()` 首行 `|| k60_usbvend_mode == 2` 直接返回）。

### 23.2 实现要点（file:line 见补丁）

- `ud_cfg_vendor[]`：98 字节，逐字节取自 0406 被删的描述符段
  （`9,2,98,0,3,1,0,0xc0,50` + IAD `8,11,0,2,2,2,1,0` + IF0/IF1 原样 +
  `9,4,2,0,2,0xff,0xfe,2,0` + EP `0x03`/`0x83` bulk 64）。
- `ud_configuration()`：`cfg = k60_usbvend_mode == 1 ? ud_cfg_vendor : ud_cfg_template;`。
- `struct ud` 新增 `vend_ok`/`vend_out_ep`/`vend_in_ep`/`vend_rx_active`/
  `vend_tx_active`/`vend_zlp`/`vend_pending`/`vend_sent`/`vend_bytes`/`vend_packets`。
- SET_CONFIGURATION：`vend_ok = (mode==1 && ep6==0 && ep7==0) || mode==2`；
  三处清零点（deconfigure / `ud_reset_endpoints` / disconnect）同步清 `vend_*`。
- `ud_vendor()`（主循环 `ud_events(); ud_console(); ud_vendor();` 的第三步）：
  空闲 arm OUT（`UD_VEND_RX 0x6000`，4096 字节）→ 收到后拷到 `UD_VEND_TX 0x7000`
  从 IN 端点回发；满包后补 ZLP（Pong `PongUsbDevice.h:256-259` 语义）。
- 完成事件：OUT 侧 `residual = trb[2] & 0xffffff`，`got = 4096 - residual`；
  IN 侧完成按满包→ZLP / 短包→计数。
- 缓冲复用 0408 已布线的 `UD_TRB_EP6 0x1380`/`UD_TRB_EP7 0x13c0`；
  **0307 特意分开的 cache line 未动**。

### 23.3 判据（沿 §15.5）

- mode 0：控制台与心跳与 0409 完全一致（回归零）。
- mode 2：主机写 N 字节到 COM 口 → 读回 N 字节回显；
  日志出现 `K60 USBLOG: echo %u bytes on ep%u (total %u)`。
- mode 1：主机打开 IF2（vendor 接口）写 → EP7 读回。

### 23.4 主机侧工具现实（不隐瞒）

Windows 工作机无 libusb/pyusb/gcc；mode 1 的裸端点验证只能走
(a) LAN 上的 Mac（`ssh emilelu@192.168.31.204`，IOKit user client）或
(b) WSL usbip 附接。mode 2 不需要任何特殊工具。

### 23.5 构建与验证状态

- series 三处一致：仓库 / `/opt/k60/trees/usb-device` / `SERIES-FINAL.txt`
  均 `2b66c5f4…c7e84`（235 行）；`patches/usb/series` 10 行（0405..0410）。
- `sync-device-input.py` 同步 3 个文件（0410 patch + 两个 series）。
- porting-gate --quick ✅（series 三处一致 PASS，7 项警告均为已知类别）；
  check-docs ✅ 187 项；eight-step-gate --build ✅ 30 项。
- 构建：usb-20261114h，私有树 `K60_OUT=/opt/k60/trees/usb-out`
  （`cp -a` 自 out-baseline，17 GB；0408 教训：共享 OUT 树被 bt/display 线覆写）。
