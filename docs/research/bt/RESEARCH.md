# K60 蓝牙研究报告（QCA6490，HCI over GENI UART → UART.SK）

- 设备：Redmi K60 / mondrian / SM8475 (taro) / 序列号 6033dbec
- 目标 OS：iOS 16.6.1 (20G81) / darwin22，走 Apple 用户态 bluetoothd 路线
- 状态（2026-11-14）：八步流程 ①同型、②官方、③反编译、④广搜 已完成，⑤计划即本文；⑥深挖、⑦本地验证、⑧上机 **未开始**。分支 feat/bt-research（自 main f119a80）。
- 证据等级：**M** = K60 本机实测（FDT / 本机厂商源码 / 本机日志）；**A** = 可直接抄写的官方源码；**B** = 官方设计文档；**C** = 未核实推断（核实方法见 §8）。

---

## 0. 七连问直答

| 问题 | 结论 | 等级 | 关键证据 |
|---|---|---|---|
| UART 编号 | **QUPV3_2（wrapper 0x008C0000）第 6 个 SE = SE20**，节点 qcom,qup_uart@894000（0x894000/0x4000），别名 hsuart0 / qupv3_se20_4uart，**4 线** | M | live FDT mondrian.dts:11041-11057、:10707-10720、别名 :396/:21484 |
| 中断 | GIC SPI **587**（0x24b level-high）+ TLMM GPIO**79**（0x4f level-high，RX 唤醒）；TLMM 汇总中断 SPI **208** | M | FDT :11049、:1317-1327 |
| 波特率 | 初始化 **115200** → 运行 **3000000**（不是 3200000）。GENI 16x 过采样，源 48 MHz 整除 | M/A | vendor hci_qca.c:1751-1764（.init_speed=115200、.oper_speed=3000000）；QcaBluetooth/tests/geni.c:57-58（3.2 Mbaud 在非 51.2 MHz 源上 -ERANGE）；patches/xnu/0500 已写 k60_geni_source_hz(3000000,16)=48000000 |
| 流控 | **硬件 4 线 RTS/CTS，必须开启**；无流控 qca_open() 直接 -EOPNOTSUPP | M | FDT 引脚组 :4106-4227；vendor hci_qca.c:560 |
| UART 引脚 | CTS=GPIO76、RTS=GPIO77、TX=GPIO78、RX=GPIO79，function qup20 | M | FDT :4106-4227 |
| BT_EN | qcom,bt-reset-gpio = <&tlmm 81 0>；DT 默认 pinctrl bt_en_sleep = gpio 功能 / output-low / pull-down / 2 mA | M | FDT :1270-1295、:2530-2546 |
| SW_CTRL | qcom,bt-sw-ctrl-gpio = <&tlmm 82 0>（射频开关归属，与 WLAN 共用） | M | FDT :1277；CNSS :10042-10080 |
| XO 时钟 | qcom,xo-clk-gpio = <&tlmm 204 0>；**先拉 XO 再拉 BT_EN，掉电前保持 2-5 ms** | M | FDT :1280；vendor btpower.c:423-460 |
| bt_wake | 控制器→主机 = **GPIO79**（sleep 态把 RX 切回 gpio 作唤醒源）；主机→控制器**无独立引脚**（K60 DT 未给 qcom,btwake_gpio）→ 用 **IBS wake byte 0xFD** | M | FDT :11049、:4220-4227、qcom,wakeup-byte=<0xfd>；btpower.c:1026 |
| 固件 | rampatch + NVM 两个文件，QCA TLV 厂商命令下载。**实测（2026-11-14）**：在 `/vendor/bt_firmware/image/`，113 文件 / 1,063,407 B；rampatch `hpbtfw20.tlv` 201,560 B / `hpbtfw21.tlv` 146,068 B；NVM `hpnv20*`（20）+ `hpnv21*`（90）。走的是 `qca/hpbtfw%02x.tlv` + `qca/hpnv…` 回退名（rom_ver 待 HCI 确认） | **M** | 设备 adb 实测，见 `FIRMWARE.md`；btqca.c:822-852、:715-745、:915-921 |
| 下载协议 | **H4**（type 0x01 cmd / 0x02 ACL / 0x04 event / 0x03 SCO）+ QCA 厂商 TLV 命令（0xFC00 家族）+ **IBS 带内睡眠**（0xFD WAKE_IND / 0xFE SLEEP_IND / 0xFC WAKE_ACK）。**不是 H5**（无 3 线 h5 帧，流控是硬件 CTS/RTS） | M | vendor hci_qca.c:1200-1203、:42-48、:1751-1764；FDT qcom,wakeup-byte=0xfd |
| 与 WiFi 同一颗芯片？ | **是**。单颗 QCA6490：WLAN 走 PCIe0 + cnss，BT 走 SE20 UART；GPIO80/81/82/204 与 S10/S11/PM8350C S1/S12/PMR735A L7 全部共享 | M | FDT CNSS :10042-10080 与 BT 节点 :1270-1295 逐项重名 |

> 一句话：K60 蓝牙不是「没资料」，而是「参数齐了、代码已 staged、只差分级上机验证 + 固件 + 用户态」。
> 真正的未知只剩两项：SE20 的 GENI 访问是否仍会把机器打死（§5.1）、20G81 bluetoothd 适配点（§5.6）。固件文件名/大小已实测（§7、`FIRMWARE.md`）。

---

## 1. ① 同型证据：本机 FDT + 本机 Android 厂商栈

### 1.1 本机 live FDT（M 级，唯一可当「地址真值」的来源）

反编译源：E:/k60-work/scratch/bt/mondrian.dts（21,954 行，sha256 516ac7d55c94cde466e57d2e0efb9014fd1cc3534210c80ef20dd5510146f16a），来自设备 live FDT；另一份 E:/k60-work/reports/live-6033dbec-fdt.dtb（sha256 95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8）是同一棵树的旧反编译，行号整体偏移约 30 行。

| 节点 | 行 | 关键内容 |
|---|---|---|
| bt_qca6490 | :1270-1295 | compatible="qcom,qca6490"；pinctrl-0=<0x3b> = bt_en_sleep；GPIO80/81/82/204；8 条 supply（S10、S11×4、PM8350C S1、S12、PMR735A L7）；**没有 interrupt、没有 HCI/serdev 子节点** → 它只是电源/复位节点 |
| qcom,qup_uart@894000 | :11041-11057 | compatible="qcom,msm-geni-serial-hs"、reg=<0x894000 0x4000>、interrupts-extended=<&intc 0 0x24b 4 &tlmm 0x4f 4>、clocks=<&gcc 0x82 &gcc 0x8a &gcc 0x8b>（se-clk 130 / m-ahb 138 / s-ahb 139，**与 mainline sm8450 的 118/119 不同，别抄**）、pinctrl-names="default","active","sleep","shutdown"、qcom,wakeup-byte=<0xfd>、qcom,wrapper-core=<0x103>、status="ok" |
| qcom,qupv3_2_geni_se@8c0000 | :10707-10720 | wrapper 0x8C0000/0x2000；iommus=<&apps_smmu 0x483 0>（SID **0x483**）；interconnect-names="qup-core","snoc-llcc","qup-ddr"；qcom,iommu-dma="fastmap"；dma-coherent |
| qupv3_se20_4uart_pins | :4106-4227 | cts(76)/rts(77)/tx(78)/rx_active(79)/rx_wake(79→gpio)/default 态；全部 function="qup20"、drive 2 mA |
| bt_en_sleep | :2530-2546 | pins="gpio81"、function gpio、output-low、bias-pull-down、2 mA |
| pinctrl@f000000 (TLMM) | :1317-1327 | compatible="qcom,cape-pinctrl"、reg=<0xf000000 0x1000000>（16 MB）、interrupts=<0 0xd0 4> → SPI 208、#interrupt-cells=2、wakeup-parent=<0x42>、保留 gpio 28/29/30/31/36/37/38/39 |
| interrupt-controller@17100000 (GIC) | :1297-1315 | arm,gic-v3、reg=<0x17100000 0x10000 0x17180000 0x200000>、#interrupt-cells=3；子节点 ITS msi-controller@17140000 |
| qcom,cnss-qca6490@b0000000 | :10042-10080 | WLAN 侧：wlan-en-gpio=GPIO80、qcom,bt-en-gpio=GPIO81、qcom,sw-ctrl-gpio=GPIO82、qcom,xo-clk-gpio=GPIO204、qcom,wlan-rc-num=0、qcom,vreg_ipa="s3e"、mboxes=<0x90 0> |
| 电源轨 | :5167-5210、:5369-5385、:5932-5940 | pm8350_s10 1.65-1.8 V（init 1.8 V）；pm8350_s11 0.38-1.17 V（init 0.952 V）；pm8350_s12 1.22-2.04 V（init 1.31 V）；pm8350c_s1 1.8-2.02 V（init 1.88 V）；pmr735a_l7 固定 2.8 V |
| 别名 | :396、:21484、:20910 | hsuart0、qupv3_se20_4uart、tlmm |

**SM8475 地址表（本文用到的全部 MMIO 窗口）**：GCC 0x00100000 + 0x2E004…0x3328C、QUPV3_2 wrapper 0x008C0000/0x2000、SE20 0x00894000/0x4000、TLMM 0x0F100000（GPIO n 的 CFG 在 base+0x100000+n*0x1000）、GICD 0x17100000/0x10000、GICR 0x17180000/0x200000。
（TLMM 基址偏移不是猜的：pinctrl@f000000 的 16 MB 窗口里 GPIO 寄存器页从 +0x100000 开始，GPIO204 的 CFG 落在 +0xCC000，仍在窗口内，与 drivers/ArmCpu 现有 GPIO 访问口径一致。）

### 1.2 本机 Android 厂商栈（参数 M 级，逻辑 A 级）

证据目录：E:/k60-work/docs/research/bt/evidence/

| 文件 | 提供什么 | 关键行 |
|---|---|---|
| k60-android-btpower.c（1,484 行） | BT 上电/复位时序、GPIO 属性名、XO latch | of_device_id :212-219（含 qcom,qca6490→bt_vreg_info_qca6490）；GPIO 属性 :988-1034；XO 规则 :423-460（"XO CLK must be asserted for some time before BT_EN"、掉电前保持 "~(2-5)ms"）；复位 :645-646（拉低 + msleep(100)）；msleep(50) :531、:605 |
| k60-android-hci_qca.c（2,229 行） | 传输协议真值：H4 + IBS + 强制流控 + 波特率 | 头注释 :5 "HCI_IBS is Qualcomm's in-band sleep"；IBS 常量 :42-48；H4 收包分派 :1200-1203；qca_open 流控强制 :560；qca_proto :1751-1764；波特率切换时 :1335-1350/:1412-1433 用 hci_uart_set_flow_control() |
| k60-android-btqca.c（565 行）+ .h | 固件命名与 rom_ver 读法 | btqca.h:125-133 **只有 QCA_QCA6390** 一个可用 soc type；rampatch 名 btqca.c:483-487；NVM :509-515；qca_read_soc_version :16-89 |
| k60-android-gcc-waipio.c（4,128 行） | SE20 时钟寄存器 | SE20 RCG .cmd_rcgr=0x2e618 :1371、CBCR halt 0x2e610 :3075；wrapper AHB 分支 gcc_qupv3_wrap_2_m_ahb_clk :3170 / s_ahb_clk :3185（clkr id :3838-3839）；**全文无 gdsc 字样** |
| linux-gcc-sm8450-v6.6.c（mainline） | SM8450 GCC 只建模 4 个 GDSC：pcie_0 0x7b004 :2972、pcie_1 0x9d004、ufs_phy 0x87004、usb30_prim 0x49004；**没有 QUPV3 GDSC**，gcc_sm8450_gdscs[] :3235-3239 仅这 4 个 | 决定了 §5.1 的怀疑排序 |

### 1.3 本机已有实现：patches/xnu/0500…0502b（已 staged、已编译、从未上机）

AGENT-bt.txt 说这条线「完全没开始」—— 对**能用的驱动**成立，对**代码**不成立：

| 补丁 | 内容 | 状态 |
|---|---|---|
| 0500-k60-bt-qbt-new-files.patch（156 KB，2026-11-12） | 新建 bsd/dev/qbt_k60.c（1,249 行）+ bsd/dev/qbt/{qbt.h,qbt_core.c,qbt_geni.c,qbt_transport.c,qbt_linux.c,btqca.c,btqca.h,shim/…}：官方 QcaBluetooth 的内核侧移植 | patches/xnu/series:201 |
| 0502b-k60-bt-qbt-kernel-stubs.patch | 弱符号 armcpu_spi_attach/armcpu_spi_mask、native_gpu_addon_stage | series:202 |
| 0501-… / 0502-… | bsd/conf/files + Makefile.arm64 INCFLAGS；bsd_init.c 里 `#if defined(ARM64_BOARD_CONFIG_PONG)` 调 qbt_k60_start() | series:203-204 |

已就绪的门禁面：`k60bt=1` 才启动（0500:1221）、`k60bt_stage`（:1226）、`k60bt_warm`（:1231）、Skywalk provider **com.apple.uart.sk.bluetooth**（:2303、:2479）、GCC QUPV3_2 vote 0x62010 的 5 个 bit（core BIT(0)/s_ahb BIT(1)/m_ahb BIT(2)/core_2x BIT(3)/SE20 BIT(9)）+ halt 轮询（0500:109-124、:471-503，HWCG_EN BIT(1)、CBCR_CLK_OFF BIT(31)）。

**它缺什么**：① 没有 GDSC/NoC 前置动作（§5.1）；② 没有分级只读探针，一上来就完整 qbt_boot；③ 固件读取路径依赖 Data addon（`/private/var/ngpu/firmware/qca/`），K60 侧还没这些文件；④ 未接 20G81 用户态。

---

## 2. ② 官方证据：UniXNU/QcaBluetooth 组件 + 官方 porting 文档

### 2.1 组件身份（②官方，B 级）

- `UniXNU/components.toml:494-508`：id **QcaBluetooth**，仓库 `https://github.com/UniXNU/QcaBluetooth.git`，
  `path = drivers/QcaBluetooth`，runtime_identifiers = `qbt_transport`、`com.apple.uart.sk.bluetooth`、`kern.qbt_boot`、`kern.qbt_power_on`、`kern.qbt_firmware`。
  参考机型 = Xiaomi Pad 6S Pro（sheng / SM8550 / WCN7850 / iPadOS 27.0.1 24A446）。
- 本机 checkout：`E:/hackios/QcaBluetooth`（另有 `UniXNU-sheng/drivers/QcaBluetooth`）。
- 分层（README.md:16-29）：`qbt_core.c` = Linux 初始化 + H4 成帧 + IBS（单 executor）；`qbt_geni.c` = GENI SE DMA，**4×2048 B RX + 1×4096 B TX**；`qbt_transport.c` = UART.SK 内核管道 + 背压 + 生命周期 + worker 电源请求（APSL-2.0）；`userland/BlueTool.c` = com.apple.BlueTool XPC 引导服务；`userland/Type0.c` = 由 HCI 报告构造 capabilities。
- 组件 sysctl（README.md:34-38）：`kern.qbt_boot`（读，控制器状态）、`kern.qbt_power_on`（读，读即上电并返回结果；只读因为 BlueTool 沙箱禁止写 sysctl）、`kern.qbt_firmware`（读，已加载固件名）。

### 2.2 官方 porting 文档给 K60 的参数清单（`UniXNU/docs/porting/bluetooth.md:22-34`，sheng 的值）

| 项 | sheng（SM8550/WCN7850） | K60 对应值 | 来源 |
|---|---|---|---|
| UART | QUP2 **SE6** @0x898000，GIC INTID 493 | QUPV3_2 **SE20** @0x894000，GIC **587** | FDT M |
| DMA SID | Apps SMMU 0x423 | Apps SMMU **0x483** | FDT :10707-10720 |
| 引脚 | CTS/RTS/TX/RX = 76/77/78/79；BT_EN 81；唤醒源 79 | 完全相同（76/77/78/79、BT_EN 81、唤醒 79） | FDT M |
| 串口时钟 | 51.2 MHz、16x、**3.2 Mbaud** | 源 48 MHz、16x、**3.0 Mbaud**（115200 → 3000000） | vendor M + geni.c:57 |
| 固件 | hmtbtfw20.tlv + hmtnv20.bin | `hpbtfw20.tlv` 201,560 B / `hpbtfw21.tlv` 146,068 B + `hpnv20*`/`hpnv21*`（**M，实测**） | §7、`FIRMWARE.md` |

`docs/porting/bluetooth.md:42-43`：UART 需要 boot firmware 的 **PROTOCOL 2 microcode**，powerOn 在引擎报告其它协议时返回 ENXIO。
`:45-62` 的上电顺序（直接照抄为 K60 的 S3 阶段）：① map 资源 + `smmu_plan_bypass`/`smmu_configure_bypass` 建 32 KiB DMA（持 AppsSmmuLock）；② 取蓝牙电源票；③ **BT_EN 拉低保持 100 ms** 后开串口时钟；④ 查 QUP 版本与协议并准备引擎；⑤ 挂 UART 中断 + 唤醒中断；⑥ 拉高 BT_EN 等 **60 ms**，再开 pin pulls；⑦ `qbt_geni_start` 然后 `qbt_boot(rate, address)`。关电相反并释放票，返回首个错误到 `qbt_transport_power_result`。
`:64-71` worker：late platform probe 调 `sheng_bluetooth_probe` → 填 `qbt_platform` → `qbt_create` + `qbt_transport_init` → 等 Data addon → 在 `qbt_transport`/`qbt_transmit` 间搬字节，睡到 `min(qbt_deadline, qbt_geni_deadline)`。
`:73-89` 发布为 DT 节点 `bluetooth { device_type="bluetooth"; compatible="qcom,wcn7850-bt"; unixnu,adt-name="bluetooth"; transport-encoding=<1>; transport-speed=<3200000>; status="okay"; }`，并在 userland 启动前写 `local-mac-address`、`/chosen/mac-address-bluetooth0`，注册同名 IOService。**K60 要改 compatible 与 transport-speed**（`qcom,qca6490` / `<3000000>`，且 speed 是 4 字节小端属性）。
`:91-107` 原生栈接线（`board.toml` `payload.runtime`）：`audio_system_plugins=["BTAudioHALPlugin.driver"]`、`bluetooth_tool="scripts/build-bluetooth-userspace.py"`、`bluetooth_target="ios27"`；`patches/xnu-12377/sheng-bluetooth-runtime.patch` 把签名后的 BlueTool、bluetoothd、QcaBTType0.dylib 覆盖到 /usr/lib、/usr/sbin。**适配器锁死一个 bluetoothd 哈希** → 换 OS build 必须重新定位补丁点（native-ios27.md）。**K60 是 20G81，必须重做这一层（§5.6）。**

### 2.3 QcaBluetooth 的 API 契约（写 K60 backend 时的签名真值，A 级）

`include/qbt.h:13-32` `struct qbt_platform` 14 个回调：`context`；`allocate( )/release( )`；`now_ns( )`；`uart_write( )`；`uart_drained( )`；`uart_speed(uint32_t)`；`uart_flow(bool)`；`clock(bool)`（**`clock(false)` 只有在真的挂好 RX 唤醒源之后才允许成功**，且允许在停 UART 过程中回调 `qbt_receive`/`qbt_rx_wake`）；`pump( )`；`wait_until(uint64_t)`；`receive( )`；`firmware_get( )/firmware_put( )`；`log( )`。
入口：`qbt_create/destroy`、`qbt_receive`、`qbt_transmit`、`qbt_transmit_capacity`、`qbt_step`、`qbt_deadline`、`qbt_set_service`、`qbt_rx_wake`、`qbt_fail`、`qbt_boot(baud,addr[6])`、`qbt_shutdown`、`qbt_get_info/stats`。`struct qbt_info{state 0 off/1 init/2 ready/3 failed; error; baud; product; soc; rom; patch; char firmware[64];}`。
`include/qbt_geni.h:10-12`：`QBT_GENI_RX_COUNT 4u / QBT_GENI_RX_SIZE 2048u / QBT_GENI_TX_SIZE 4096u`；`struct qbt_geni_ops` 含 `irq_mask(bool)`（**可能在串口时钟已关的硬中断里调用**）、`wake_worker`、`receive`、`barrier`、`sync`。
`qbt_geni_set_rate(g,baud,source_hz,oversampling)` **拒绝误差 > 1%**；`qbt_geni_quiesce` 要求 TX 排空后才 cancel RX、只有 STOPPED 且有外部 RX 唤醒源时才允许门控时钟。

### 2.4 关键约束：3.2 Mbaud 是 sheng 的，不是普适值（A 级反证）

`E:/hackios/QcaBluetooth/tests/geni.c:57-58`：
```c
assert(qbt_geni_set_rate(&f->g, 3200000, 100000000, 16) == -ERANGE);
assert(!qbt_geni_set_rate(&f->g, 115200, 7372800, 16));
```
→ 100 MHz 源 + 16x 过采样下 3.2 Mbaud 非法；115200 配 7,372,800 Hz 源合法。这与 0500 已写的常量（`k60_geni_source_hz(115200,16)=7,372,800`、`(3000000,16)=48,000,000`、`(3200000,16)=-ERANGE`）一致，也说明 sheng 的 51.2 MHz 源才是 3.2 Mbaud 可行的原因。**K60 运行速率定 3.0 Mbaud。**

---

## 3. ③ 反编译 / 二进制证据：iOS 16.6.1 没有内核 HCI 栈

对 `20G81/kernelcache.decompressed`（48,644,096 B）与 `21H461` 做字符串/符号统计：

| 符号 | 20G81 | 21H461 |
|---|---|---|
| `iobluetooth`（IOBluetoothFamily 家族） | **0** | 0 |
| `IOBluetoothHCI` / `IOBluetoothHostController` / `AppleBluetooth` 类族 | 0 / 0 / 仅 5 处字符串 | 0 / 0 / 3 |
| `BTReset` | 6 | 6 |
| `BlueTool` | 1 | 1 |
| `com.apple.uart.sk.%s` | 存在（kernel control socket 名模板） | 存在 |
| `IOSerialStreamSync` / `IOSerialFamily` | 3 / 7 | 3 / — |

关键字节上下文（20G81，@0xa666a5 同一字符串池）：
`...uart.builtin-serial.Identified Serial Port %s at %#llx...AppleOnboardSerialBSDClient: could not make sk kernel control socket for %s: %d...com.apple.uart.sk.%s`，
即**内核提供 `com.apple.uart.sk.<name>` 控制 socket 机制**，而 QcaBluetooth 的 `runtime_identifiers` 正是 `com.apple.uart.sk.bluetooth` —— 两者对上。
@0xe570d2（BlueTool 区）：`BlueTool ... /dev/bt ... /dev/btreset ... /private/etc/bluetool`。
@0xd1efc8（BTReset 串池）：DT 属性 `function-bt_reset`、`function-bt_wake`、`function-power_enable`、`function-bootstrap_lock`、`bootstrap-delay`、`btreset-verbose`；devfs 节点 `<name>.btreset` / btwake / btpoweroff，open/close 各自 assert/deassert RESET、WAKE、REG_ON。
`com.apple.driver.AppleBluetooth` 预链接记录：`_PrelinkExecutableSize 0x7f8`（≈2 KB，**只可能是电源/复位 shim**）。
`marconi-bt` 命中 @0x2b72645 属 `com.apple.driver.AppleSPU`（`aop-marconi-bt-control`），与 K60 无关 —— 排除。

**结论（这是本线最重要的判断）**：iOS 16.6.1 **没有** IOBluetooth kext 家族，内核里没有 HCI 传输栈。BT 必须按 Apple 的架构走：
内核只提供 UART 通道（UART.SK）+ 电源/复位（AppleBluetooth/BTReset 语义），**协议栈在用户态 bluetoothd**。这正是官方 QcaBluetooth 的设计，也证明 `docs/plans/BT-AUDIO-PORT-PLAN.md` §1.4/§1.5 的「自写 IOSerialFamily + HCI + btstack」路线应当**废弃**（该文写作时官方组件尚未被发现）。

---

## 4. ④ 广搜：别的机型/仓库能借到什么

| 来源 | 有 BT？ | 能借什么 | 不能借什么 |
|---|---|---|---|
| `UniXNU-sheng`（SM8550/WCN7850） | **有，完整** | 官方 QcaBluetooth 全套 + `patches/xnu-12377/sheng-bluetooth-runtime.patch` + `package/BluetoothFirmware.c` + `scripts/build-bluetooth-userspace.py`/`stage-bluetooth-firmware.py` + 4 个 check 脚本 | MMIO 地址、SID、时钟索引、baud 3.2M、固件名（hmt*） |
| `UniXNU-pong`（SM8475 同型，iOS 18 线） | **没有** | 只有一条反证：`userland/board_services18.py:84-89` 把 com.apple.bluetoothd 用 `_LimitLoadToDeviceTree=['bluetooth','marconi-bt']` 禁掉，理由写着「requires a real Pong Bluetooth transport; none implemented」 | 任何传输实现 |
| `phk110-port`（一加 Ace 2 / SM8475 兄弟） | 仅 `drivers/bluetooth/hakios.bt.c` 143 行只读诊断 | TLMM 读法：`GPIO_CFG(n)=tlmm+0x1000*n`、`GPIO_IO(n)=+4`；头注释记录 GPIO84 wl-reset/85 bt-reset/86 sw-ctrl | 无 HCI/固件/时序 |
| 本机 Android 厂商栈（§1.2） | 有 | 全部时序、GPIO 属性名、H4/IBS、波特率、固件命名 | 直接编译（Linux API） |
| `QcomGeniSpi`（官方 GENI 组件） | 间接 | GENI SE 上电序列：GPLL0 投票 → 5 个 QUP 分支投票 → 等分支 not-off 且带 HWCG → mux 4 根引脚 → map SE+wrapper → FIFO/DMA/SMMU bypass | 地址（sheng = SM8550 wrap1 0x52008/0x184e4，K60 = wrap0 0x62008/0x274dc/0x33000） |

---

## 5. ⑤ 计划：六个阶段，每阶段独立可判死

**总原则**：先用只读探针证明「SE20 在这台机器上能不能碰」，再谈协议；每阶段一条 boot-arg、一个 capture.json 判决、一次提交。
依据 `docs/research/GENI-ACCESS-PRECONDITIONS.md` 的两次本机事故（触摸 SE4 0x990000、音频 I2C 0x880000 都在首次 GENI 寄存器访问时**零日志死机**）——蓝牙 SE20 在同一个 QUPV3_2 wrapper 里，**默认假设它也会死**，直到 S1 证明相反。

| 阶段 | 内容 | 产物 | 判定（读 capture.json 的 verdict/panicMarker，不看 logstat） | 预估 |
|---|---|---|---|---|
| **S1** 只读探针（S1b） | `k60bt=1 k60bt_stage=1`：先 `IOSleep(k60bt_delay)`（默认 20 s，上限 120 s）等 CDC 控制台活着，再**每次访问之前打一行点**（共 25 个打点），分 6 个可分子步（`k60bt_step`）：s1 map → s2 GPLL0 投票+锁轮询 → s3 QUPV3_2 5 位投票 → s4 逐个读 5 个 halt 寄存器 → s5 读 SE 身份 4 个 + wrapper 版本 → s6 读 0x2ac/0xc40/0xd40/0xe40 与复读状态。不建 DMA、不碰 UART 中断、不拉 BT_EN | 内核补丁 `patches/bt/0001-k60-bt-readonly-probe.patch` = `patches/xnu/0507`（**已接入 series:205**） | 出现 `probe: done` → SE20 可达，进 S2；停在某行 `probe: sX` → **那一行就是死因**（S1a 那种 0 字节日志不再重演），据此判定 NoC/时钟/单条 load | 0.5 d 离线 + 2 次上机 |
| **S2** 时钟+引脚+引擎 | `k60bt=1 k60bt_stage=2`：S1 全部 + 引脚 mux（76/77/78/79 → qup20，2 mA；sleep 态 79 → gpio）+ SE20 RCG 设 48 MHz/16x/3.0 Mbaud + wrapper 协议检查（期望 PROTOCOL 2）。**不拉 BT_EN** | 同上扩展 | 无死机且 `uart_speed(3000000)` 返回 0 → 进 S3 | 1 d + 1 次 |
| **S3** 上电时序 | `k60bt=1 k60bt_stage=3`：加 XO(GPIO204) → 100-200 µs → BT_EN(81) 高 → 4-6 ms → **保持高**；然后 115200 下读 HCI Reset 的 event。断电路径先 XO 保持 2-5 ms 再降 | 同上 + 电源回调 | 收到 `0e 04 01 03 0c 00` 之类 Command Complete → 芯片活了；无响应 → 分「XO 无效 / BT_EN 极性 / 电源轨未开」三支（§8 I-1） | 1-2 d + 2 次 |
| **S4** 固件下载 | `k60bt=1 k60bt_stage=4`：`qbt_boot(3000000, addr)` 走 QCA TLV（0xFC00 家族）+ NVM，固件从 `/private/var/ngpu/firmware/qca/` 读；失败回落 115200 并打印 rom_ver/soc_id | 同上 + staging 实测固件（`hpbtfw20.tlv`/`hpbtfw21.tlv` + `hpnv20*`/`hpnv21*`，见 `FIRMWARE.md` §5） | `kern.qbt_firmware` 有非空名字、`kern.qbt_boot` state=2 → 进 S5 | 2-3 d + 2 次 |
| **S5** UART.SK 通道 | `k60bt=1`（去掉 stage，全速）：`kern_nexus_controller_register_provider` 注册 `com.apple.uart.sk.bluetooth`，用 BlueTool 读 `kern.qbt_power_on` 触发上电 | 0500 已有骨架，补 provider 语义 | 用户态能 open 通道、能收发 H4 | 2-3 d + 1-2 次 |
| **S6** 用户态 bluetoothd | 20G81 的 BlueTool/bluetoothd 适配：定位 20G81 bluetoothd 的补丁点（sheng 是 24A446，哈希锁死）、签名、`/usr/lib/QcaBTType0.dylib`、`/private/etc/bluetool` | `patches/bt/` + runtime 补丁 | `[bluetooth]` 日志出现 state=2 error=0、bluetoothd 起一次、`bluetoothctl`/设置里能看到适配器 | 3-10 d（最大不确定） |

### 5.1 为什么把 S1 做成「一读就退」（对 GENI 事故线的回应）

`docs/research/GENI-ACCESS-PRECONDITIONS.md` 的怀疑排序，结合本轮新增的**反面证据**重排：

1. ~~QUPV3 GDSC 未开~~ → **不支持**：mainline `linux-gcc-sm8450-v6.6.c` 只建模 4 个 GDSC（:3235-3239），vendor `k60-android-gcc-waipio.c` 全文无 gdsc；SM8475 的 QUPV3 没有独立 GDSC 描述。sheng 的 `gcc_qupv3_wrap0_gdscr` 是 SM8550 的东西，**不能移植**。仍保留为「若 S1 死机且投票正常」时的备选检查项。
2. **NoC / interconnect 路径**（升为首要）：wrapper 节点声明 `interconnect-names="qup-core","snoc-llcc","qup-ddr"`，本 port 没有任何 ICC 框架，若 boot firmware 未留默认带宽，首次访问 SE/wrapper 会 NoC hang —— 与「零日志死机」现象吻合。
3. TLMM mux 未切（S2 才做，所以 S1 不受影响）；4. 时钟真关（S1 会先投票并轮询 halt）。

### 5.2 与 S1 配套的判据（不许用 logstat.py 的 panic 计数）

- 死机：capture.json 的 `verdict` 非正常结束 / `panicMarker` 存在 / 控制台字节数为 0。
- 成功：控制台出现 S1 专属字符串（建议 `[bluetooth probe] se20 fwrev=%08x status=%08x`），且 capture 正常收尾。
- 每次 `fastboot boot` **必须先挂 CDC-ACM 捕获**（AGENTS.md 铁律 8），否则证据无效。

---

### 5.3 S1 的落地物（本线已产出）

- 规格：`docs/research/bt/S1-PROBE-SPEC.md`（寄存器出处、boot args、判据表、上机步骤、接线选项）。
- ⑥ 深挖：`docs/research/bt/06-DEEP-DIVE.md`——对 0500 的 `bsd/dev/qbt_k60.c`（1,249 行，抽取值 sha256 `8451c870…`）逐行对照 Linux GENI/clk 源与官方 QcaBluetooth，给出**已验证 11 项（V1–V11）**与**偏差 10 项（F1–F10）**。其中三项必须在 S2 前定性：**F1** GENI DMA 拿虚拟地址当物理地址、SMMU 流 0x483 未 bypass；**F2** 0x2ac（`G_MANUAL_RFR`）被写成组件从不使用的 `0x80000001`（组件只写 0 或 `0x80000002`）；**F3** `k60_stop_engine()` 轮询的 0xe40 在两个 GENI 头文件里都不存在，若读出非零会恒定 `-ETIMEDOUT`。
- 补丁（S1b）：`patches/bt/0001-k60-bt-readonly-probe.patch` = `patches/xnu/0507-k60-bt-readonly-probe.patch`（8,331 B / 192 行，sha256 `6136fc67…`）——先延迟 20 s 让控制台活着，再在每个寄存器访问**之前**打点，6 个可分子步；0x2ac / 0xe40 / 0xc40 / 0xd40 的读专为 F2/F3 设计。
- **已接入构建**：`patches/xnu/0507-k60-bt-readonly-probe.patch` + `patches/xnu/series:205`（0502 之后、0503 之前），`patches/bt/` 仍只作本线存档；接线选项 A/B 的讨论保留在 `patches/bt/README.md` 与 SPEC §6。

### 5.4 S1a 上机实测（2026-11-14 04:51）：不可判定，但换来一条硬事实

镜像 `bt-s1-20261114b`（boot_img `2fef132a…`，内核 `78bf1986…`）带 `k60bt=1 k60bt_stage=1 k60bt_warm=1` 上机：fastboot 接受，`capture.json` = `port-not-observed`、`bytes=0`、`portOpened=false`、`panicMarker=null`，随后板子既不在 `adb` 也不在 `fastboot`，Windows PnP 里没有任何 Qualcomm/CDC 设备——`scripts/k60-device.sh` 记录的「USB 掉线挂死，只能物理断电」。

- **可判定的一条**：同一颗内核在**不带** `k60bt` 的镜像（`bt-s1-20261114a`，boot_img `7b6b02fc…`）里正常跑到用户态（`captured-budget-complete`，3,192 行）。所以挂死属于 `k60bt=1` 这条路径，不是构建问题。
- **不可判定的**：控制台 0 字节，没有任何 `[bluetooth]` 行，无法知道死在哪次访问——因为 `qbt_k60_start()` 紧跟在 `k60_usblog_start()` 之后执行，USB gadget 还没枚举完。这正是 S1b 先延迟 20 s、再逐访问打点的原因。
- **顺带拿到的 iOS 侧事实**：那次成功的启动里 `bluetoothd` 已经起来，反复打印 `Unable to match bluetooth service in device tree.` / `Not a valid MAC address (all 00s).` / `bluetoothd: No bluetooth on this device.` —— 20G81 只有用户态栈，且要求设备树里存在 `bluetooth` 节点与非零 MAC（与 §2/§3 结论一致，现在有设备侧证据）。

---

## 6. ⑧ 上机验收标准（写死在 S6 之前）

1. 控制台出现 `[bluetooth sk] ctl_register com.apple.uart.sk.bluetooth error=0 firmware=<非空> speed=3000000`（0500:2479 已有该 printf）。
2. `sysctl kern.qbt_boot` → `state=2 error=0 baud=3000000 rom=<非0> patch=<非0> firmware=<名>`。
3. 一次 bluetoothd 启动（不是反复重启），且 `[bluetooth]` 无 ENXIO（ENXIO = 引擎协议不对，说明 boot firmware 没给 PROTOCOL 2）。
4. `bluetoothd` 起来后 `defaults read /Library/Preferences/com.apple.Bluetooth` 能看到控制器地址；`/chosen/mac-address-bluetooth0` 与 `local-mac-address` 一致。
5. 失败预测（提前写，便于判死）：① S1 零日志死机（概率按触摸/音频经验不低）；② PROTOCOL 2 不可用 → ENXIO；③ 20G81 bluetoothd 无对应补丁点 → 用户态起不来；④ 固件文件名猜错 → TLV 下载失败。

---

## 7. 固件：已知、未知、取法

**已实测（M，2026-11-14 Android 启动只读 adb）**：BT 固件在 **`/vendor/bt_firmware/image/`**（不在 `firmware_mnt/image/qca6490`），共 **113 个文件 / 1,063,407 B**，已全部拉到 `E:/k60-work/firmware/qca6490-bt/` 并逐个哈希。rampatch 实测为 `hpbtfw20.tlv`（201,560 B）与 `hpbtfw21.tlv`（146,068 B），NVM 为 `hpnv20*`（20 个）+ `hpnv21*`（90 个，含 `g` 与 sony 变体）。**旧推断的 `htbtfw21.tlv`/`htnv21.bin` 作废。** 完整表见 `docs/research/bt/FIRMWARE.md`。
**命名逻辑（A，0500 内 `bsd/dev/qbt/btqca.c`）**：WCN6855 分支先请求 `qca/wcnhpbtfw%02x.tlv`（:822-824），失败回退 `qca/hpbtfw%02x.tlv`（:847-852）；NVM 先 `wcnhpnv`（:884-888），失败回退 `hpnv`（:915-921），板级名 `qca/<stem><rom_ver:02x><g?>.b<bid:02x>`（:715-745）。本机固件只有 `hp*` 拼写 ⇒ 走**回退名**，正好是 0500 `k60_firmware_get()` alias（:924-960）覆盖的路径。
**已在本机（M）**：`/mnt/e/k60-work/firmware/qca6490/` 只有 WiFi 侧 amss.bin/amss20.bin/Data.msc/Data20.msc；`docs/research/wifi/FIRMWARE.md:353-` 记录 `bd_m11agf.elf` 60,000 B 是本机 BT BDF（板级数据文件），**不是** TLV rampatch/NVM。
**已核实（M）**：① 文件名/大小见上表；② reader 会剥掉 `qca/` 前缀再拼根（`qbt_k60.c:867-874`），故 iOS 落盘为 `/private/var/ngpu/firmware/qca/hpbtfw20.tlv`，不需要多一层 `qca`；③ `bd_*.elf` 是 WiFi 板级数据，**不要**混进 BT 固件目录。
**仍未知（C）**：本机真实 `rom_ver`（0x20 还是 0x21）与 board id —— 需 HCI 起来后由 `btqca` 打印 `QCA controller version`/`Downloading qca/…`。保底：staging 同时放两套 rampatch 与 `hpnv20*`+`hpnv21*` 全量（约 1.06 MB），运行时按名取。
**取法**：已完成（2026-11-14 一次 Android 启动 + 只读 `adb pull`）。复现命令、设备侧证据（dumpsys OFF→ON 但无 `hci0`、VINTF 缺 IBluetoothHci）、staging 方案（`firmware/bluetooth/manifest.json` + `scripts/stage-bluetooth-firmware.py` + `board.toml [payload.runtime]`）全部写在 `docs/research/bt/FIRMWARE.md` §2/§5/§7。
**注意**：不要把厂商固件提交进仓库（sheng 也是外部固件仓 + hash pin）；本机来源目录 `/mnt/e/k60-work/firmware/qca6490-bt`。

### 7.1 与 WiFi 的边界（写给 WiFi 线）

同一颗 QCA6490，但**互不代管**：

| 资源 | WiFi 线 | BT 线 | 冲突规则 |
|---|---|---|---|
| GPIO80 | `wlan-en`（CNSS 与 BT 节点都叫它 `wl-reset-gpio`） | 只读、不驱动 | WiFi 独占 |
| GPIO81 | CNSS 也声明 `qcom,bt-en-gpio` | **本线驱动** BT_EN | BT 独占；cnss 侧不得拉 |
| GPIO82 | `qcom,sw-ctrl-gpio` | 本线驱动 SW_CTRL | 共享，按「最后释放者关」 |
| GPIO204 | `qcom,xo-clk-gpio` | 本线脉冲 XO | 共享；WiFi 已开则不发脉冲 |
| PCIe0 / cnss | 独占 | 不碰 | — |
| SE20 UART | 不碰 | 独占 | — |
| 电源轨 S10/S11/PM8350C S1/S12/PMR735A L7 | 共用 | 共用 | **一次投票一个 radio，最后释放者断电**（照抄 sheng_wcn_power_get/put 语义） |

---

## 8. 未核实项清单（每条带核实方法）

| ID | 未核实 | 方法 | 影响 |
|---|---|---|---|
| I-1 | BT 电源轨是否已由 boot firmware/PMIC 默认开（S1/S2/S3 是否需要显式 RPMH 投票） | S3 阶段失败时读 PMIC 或看 shen 的 wcn_power 票语义；先假设「默认开」，不写 PMIC 代码（避免猜电压） | S3 可能全灭 |
| I-2 | ~~固件真实文件名/大小~~ **已核实 2026-11-14**（113 文件 / 1,063,407 B，见 `FIRMWARE.md`） | 已用只读 adb 完成 | — |
| I-3 | 本机 rom_ver（0x20/0x21）与 board id（文件集已两套齐备） | S3 收到 HCI event 后读 `qca_read_soc_version` 并打印 | 选错固件 → TLV 校验失败（已用双份 staging 兜底） |
| I-4 | boot firmware 是否给 SE20 分了 PROTOCOL 2 microcode | S2 打印 `GENI_PROTOCOL`；ENXIO 即无 | S2/S3 卡住 |
| I-5 | SE20 首次访问是否死机（NoC/ICC） | S1 | 决定整条线是否可行 |
| I-6 | 20G81 bluetoothd/BlueTool 的补丁点与哈希 | 对 20G81 的 bluetoothd 做与 native-ios27.md 相同的定位；需要 LAN Mac 与 iOS SDK 签名 | S6 不可完成 |
| I-7 | K60 是否需要在 `dts/mondrian.dts` 增 ADT `bluetooth` 节点 | 若用户态按 `unixnu,adt-name="bluetooth"` 找设备，则必须加；S6 前确认 | S5/S6 之间 |

---

## 9. 交接给 Lead 的事项（都在本线写权限之外）

1. **DT 节点**：`dts/mondrian.dts` 增 ADT 节点（照官方 bluetooth.md:73-89，改 compatible/speed）：
```dts
bluetooth {
    device_type = "bluetooth";
    compatible = "qcom,qca6490";
    unixnu,adt-name = "bluetooth";
    transport-encoding = <1>;
    transport-speed = <3000000>;
    status = "okay";
};
```
（`dts/mondrian.dts` 是 198 行的 ADT 导出 overlay，现有节点：memory、pong-audio、ufs、smem/tcsr/hwlock/ipcc/adsp。）
2. **SOURCES.toml 增 `[subsystem.bluetooth]`**（research-gate.py:34-84 只认 REPO 或 /mnt/e/k60-work 下的路径；现有块：touch/storage/gpu/wifi/audio/battery/launchd）：
```toml
[subsystem.bluetooth]
name = "Bluetooth (QCA6490 over GENI UART SE20)"
required = [
  { path = "docs/research/bt/RESEARCH.md", examined = "FDT 全节点/厂商 btpower+hci_qca+btqca/官方 QcaBluetooth/20G81 kernelcache/0500 补丁", finding = "UART=QUPV3_2 SE20 @0x894000 IRQ587、115200→3000000、4 线 RTS/CTS、BT_EN=GPIO81、XO=GPIO204、H4+IBS 0xFD、固件 hpbtfw20/21.tlv+hpnv20*/hpnv21*(M)" },
  { path = "docs/research/bt/FIRMWARE.md", examined = "设备只读 adb：/vendor/bt_firmware/image 清单、113 文件逐个 sha256、btqca.c 选名逻辑、qbt_k60.c 白名单与 alias", finding = "BT 固件在 /vendor/bt_firmware/image，113 文件 / 1,063,407 B；rampatch hpbtfw20.tlv 201,560 B + hpbtfw21.tlv 146,068 B；NVM hpnv20*/hpnv21*；走 hp* 回退名，与 0500 alias 一致" },
]
```
3. **EIGHT-STEPS.toml 增 `[hardware.bluetooth]`**（现有只有 touch/gpu/storage）：`same_model/official/decompile/wide/plan = true`（证据指向本文与 §1/§2/§3/§4），`deep/verify = false`，`verify.local_verified = false`。
4. **`docs/plans/BT-AUDIO-PORT-PLAN.md` §1.4/§1.5 需修订**：其「自写 IOSerialFamily + HCI + btstack」结论与 §3 的二进制证据、与官方 QcaBluetooth 组件冲突，应改为「UART.SK + 官方组件 + 用户态 bluetoothd」。该文件不在本线写权限内。
5. **代码归属决定**：BT 代码已在 `patches/xnu/0500-0502b`（series:201-204）里编译进内核，本线**不**新建 `drivers/PongBt/`（避免 P-170「新源文件没人引用」类假进展）。S1 探针放在 `patches/bt/`，`patches/bt/README.md` 明确写「未接构建」，补丁实际改的是 0500 内的 `bsd/dev/qbt_k60.c`；接线由 Lead 选 §6 的 A/B 之一。
6. **固件获取已完成**（2026-11-14 Android 启动只读 adb，113 文件已落到 `E:/k60-work/firmware/qca6490-bt/`，清单与哈希见 `docs/research/bt/FIRMWARE.md`）。剩余属 Lead 写权限：`firmware/bluetooth/manifest.json` + `scripts/stage-bluetooth-firmware.py` + `board.toml [payload.runtime] bluetooth_tool/bluetooth_target="ios20"`，**不要**把厂商固件提交进仓库。
7. **20G81 用户态适配**需要 LAN Mac 的 iOS SDK（`libpong-ui.dylib` 之外还有签名工具链），按 AGENT-bt.txt 的约定由 Lead 在 Mac 侧执行。

8. **构建前必须先换基线（本线实测，2026-11-14）**：`feat/bt-research` 从 `f119a80` 切出，在该基线上 `python3 scripts/eight-step-gate.py --build` **是红的**：`硬件项: 5 个（touch, gpu, storage, display, bootchain）`、`通过 27 项检查`、`问题 3 处: touch :: ④ 广域 / ⑤ 方案 / ⑥ 深挖 未标记 done=true`。同一条命令在 `feat/pmic-rail`（`4f90f12`，比本线多 4 条 RULES、EIGHT-STEPS 改 32 行）上通过。**结论：BT 构建前先把本分支 rebase/merge 到当前集成线（≥`4f90f12`），否则 iron-3 会拦构建，且原因不在 BT。**
   - 同一基线状态下在 `k60-bt` 跑 `python3 scripts/check-rules.py` 另有 2 项红：`P-165/P-166 构建输入序列与仓库不一致：只在仓库有 [3 条 zzzz…pong-touch-*-probe.patch]`。这 7 条 `zzzz…pong-touch-*` 探针在 `f119a80` 的 series 里已存在，而 `/opt/k60/trees/k60build` 的构建输入未同步；与本线 5 个新文件无关（`git diff --stat f119a80 HEAD` 只增 `docs/research/bt/*` 与 `patches/bt/*`，未改 series / EIGHT-STEPS / SOURCES）。
   - 按铁则 8 报备：这两条是**基线门禁问题**，不要为了让门禁变绿去改判定；`research-gate.py`（32 项）与 `check-docs.py`（187 项）在 `f119a80` 上均已通过。
9. **S1 探针已过 ⑦ 本地静态检查**：补丁 `patches/bt/0001-k60-bt-readonly-probe.patch` sha256 `95e4b098e552619db135b455af5dbec96eae4450a2a8cdae1c6c61ce658ed8a3`（4,174 B / 80 行 / 2 hunk，9 次只读）；对 0500 抽出的完整树执行 `git apply --check` 通过，再用 out3 构建记录的 `.CFLAGS` 跑 `clang -target arm64-apple-ios16.0 -fsyntax-only` **0 error**。细节与日志路径见 `S1-PROBE-SPEC.md` §8。
10. **⑥ 深挖已完成，结论是「S1 必须先跑，且 S1 扩大了」**：逐行评审见 `docs/research/bt/06-DEEP-DIVE.md`。S2 之前必须由 S1 的寄存器读数定性 F1/F2/F3（DMA 物理地址、RFR 值、0xe40 轮询）；其中 F1 的正确修法（SMMU bypass + 连续物理页）属于 S2 代码工作，F2/F3 可能只需改两行，但**都不允许在无设备读数的情况下猜**。

---

## 10. 复现本文全部证据的命令

```bash
# 1) live FDT 反编译（WSL 里有 dtc 1.7.0，Windows 侧没有）
wsl -e bash -lc 'dtc -I dtb -O dts /mnt/e/k60-work/reports/live-6033dbec-fdt.dtb > /tmp/x.dts && grep -n -E "bt_qca6490|qup_uart@894000|qupv3_2_geni_se|cnss-qca6490|qupv3_se20" /tmp/x.dts'
# 2) 厂商栈关键行
grep -n -E "init_speed|oper_speed|HCI_IBS|hci_uart_set_flow_control" /mnt/e/k60-work/docs/research/bt/evidence/k60-android-hci_qca.c | head -20
grep -n -E "htbtfw|htnv|QCA_QCA6390" /mnt/e/k60-work/docs/research/bt/evidence/k60-android-btqca.c /mnt/e/k60-work/docs/research/bt/evidence/k60-android-btqca.h
# 3) 内核有没有 HCI 栈（答案应为 0）
strings -a /mnt/e/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed | grep -c IOBluetoothFamily
# 4) 官方组件与测试约束
grep -n "set_rate" /mnt/e/hackios/QcaBluetooth/tests/geni.c | head
ls /mnt/e/hackios/QcaBluetooth/{include,src,userland,tools}
# 5) 本机固件现状
ls -l /mnt/e/k60-work/firmware/qca6490/
```

---

## 11. 结论

- 硬参数（UART/IRQ/引脚/GPIO/流控/协议/速率）**全部有 M 级证据**，不需要再猜任何地址或引脚。
- 软件栈有**官方组件 + 已 staged 的内核补丁**，本线的工作不是从零写驱动，而是「分级验证 + 固件 + 用户态」。
- 最大风险不在蓝牙本身，而在 **QUPV3_2 的首次 GENI 访问**（与触摸/音频同一类死机）。因此 S1 必须先做、必须能一读就退。
- 下一步（本线）：**S1b 只读探针已接入构建**，等一次物理断电复位后的上机；判据看「最后一行 `probe: sX`」（§5.4 记录 S1a 的 0 字节日志）。

## 12. 证据来源清单（SOURCES 口径）

| 类别 | 路径 | 用途 |
|---|---|---|
| 本机 FDT | E:/k60-work/scratch/bt/mondrian.dts（sha256 516ac7d5…46f16a） | 地址/引脚/中断真值 |
| 本机 FDT(旧) | E:/k60-work/reports/live-6033dbec-fdt.dtb（sha256 95c02052…9fdac8） | 交叉核对 |
| 厂商源码 | E:/k60-work/docs/research/bt/evidence/k60-android-{btpower,hci_qca,btqca,gcc-waipio}.c | 时序/协议/固件名 |
| 官方组件 | E:/hackios/QcaBluetooth（README.md、include/qbt*.h、tests/geni.c、native-ios27.md） | API/约束/用户态 |
| 官方文档 | E:/hackios/UniXNU/docs/porting/bluetooth.md、UniXNU/components.toml:494-508 | 流程/接线 |
| 本机内核 | E:/hackios/UniXNU/out/ipsw/20G81/kernelcache.decompressed | 反证无内核 HCI 栈 |
| 本仓库 | patches/xnu/0500-0502b、patches/xnu/series:201-204、docs/research/GENI-ACCESS-PRECONDITIONS.md、docs/plans/BT-AUDIO-PORT-PLAN.md | 已 staged 代码/已知事故/旧计划 |
| 同型对照 | UniXNU-pong、phk110-port、UniXNU-sheng | 边界与反证 |


