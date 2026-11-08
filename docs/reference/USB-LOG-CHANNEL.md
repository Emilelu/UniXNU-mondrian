# USB 内核日志通道可行性调研（unixnu 路线 / K60 mondrian）

> **用途**：USB 日志通道的方案调研与设计档。2026-11-04 起该通道被定为**主线并行必需项（调试放大器）**——见 DECISIONS D-2026-11-04-01（唯一可行解法）与 ISSUES I-20261103-04（已知死亡点：apps_smmu stream 0 无 context → TZ 复位）。
> **边界**：ramoops 是否可用的**结论不在这里**，以 D-2026-11-04-01 / I-20261104-01 / PITFALLS-FROM-HISTORY 第 16 条为准（结构性不可用，重启即失）；本档 §0 结论与方案细节仍有效，但「ramoops→回 Android 不可行」一句的旧依据已被 D-2026-11-04-01 取代。

日期：2026-11-02 ・ 性质：只读调研（未改源码、未构建、未碰真机、未做 git 写操作）・ 全部行号基于当日本地快照

## 0. 结论先行

**能做。推荐方案：把 hakios（ios-sweet 时代）的「XNU 内核态 DWC3 设备端 + CDC-ECM + UDP 实时控制台流」整体移植到我们的 xnu-work，作为驱动形态的内核补丁（bsd/dev 级，不依赖 IOKit USB 栈）。**

> **更正（2026-11-04）**：本节的 ECM 推荐已被取代——pong-usb 在**同 SoC SM8475** 真机跑通 CDC-ACM console（12 秒 108,518 字节），而 ECM 仅有 SM7150 实测且 K60 适配 0 次上机；两条路内核硬前置完全相同，CDC-ACM 链路更短、宿主 Windows 原生免驱。裁决全文见 [`references/USBM-LOG-CHANNEL-AUDIT.md`](references/USBM-LOG-CHANNEL-AUDIT.md) §9。本节及以下 ECM 细节保留备查。

- **机制已在同代 xnu-8796 真机上验证过**：hakios 在 Redmi Note 10 Pro（sweet, SM7150）上 2026-10-18 一天内从只读探针做到实时日志流（commit `809bf54`→`fdad0de`），实测 `ping 192.168.7.2` 约 1 ms、0% 丢包，日志以 UDP 5140 持续流出（见 §1.5 的 NOTES.md 原文）。
- **我们的树已具备全部内核侧前提**：完整 BSD 网络 KPI 已编进 kernel.macho（`ifnet_attach`/`sock_socket`/`mbuf_allocpacket`/`ether_demux` 符号均在）；console 字节镜像（pong_ramoops）和它的只读 accessors 已存在，日志源零侵入；boot-arg 通道现成（打包脚本已支持追加 kernel arg）。
- **代价**：一个约 900–1100 行的新内核文件（对照 hakios 0072–0077 共约 1200 行补丁抄写适配）+ `arm_init.c` 一行初始化调用 + 打包时加一个 boot-arg。主机侧零安装（WSL2 内核自带 `CONFIG_USB_NET_CDCETHER=y`，usbipd 桥接）。
- **主要不确定性（按风险排序）**：① K60 的 USB DMA 是否被应用侧 SMMU 拦截（sweet 上不用管 SMMU 直接物理地址成功；K60 上 UFS 需要 SMMU takeover，USB 未实测——hakios 的 K60 分支只走到探针阶段）；② SM8475 的 GCC USB 时钟/GDSC 偏移本地未确认（hakios 的表是 SM7150 的）；③ eUSB2 PHY（0x88e3000）在 ABL 之后的状态未实测。
- **panic 场景**：panic 前的日志已实时流出（100 ms 粒度）；panic 文本本身会进内存 ring 但发送线程随调度停止，拿不到——需配合持久层（hakios 用 userdata 分区尾 raw 写；我们可同法用 K60DATA 所在分区尾 + 下次启动经 USB 回播，见 §4）。
- **不要做**：CDC-ACM 设计稿（`UniXNU-mondrian/docs/USB-LOGGING-PLAN.zh.md`，pong 时代未实现）已被 hakios 的 ECM 实证路线超越，直接抄 ECM 比新写 ACM 少踩坑；ramoops→回 Android 已确认不可行，本报告不再考虑。

---

## 1. hakios 的实现剖析

### 1.1 机制定性

**它不是 CDC-ACM，不是串口，不是复用 fastboot/调试端口，而是一套 XNU 内核态的裸 DWC3（Synopsys USB3 控制器）设备端 gadget，向主机呈现标准 CDC-ECM（USB 以太网）功能；内核把控制台字节用内核 UDP socket 流式发到主机。**

数据通路：

```
kernel printf / /dev/console ──► _cnputs() ──► sweet_log_append() ──► 4 MiB 内存 ring
                                                              │
ud_log_thread（每 100 ms 醒）◄── sweet_log_copy() 增量读取 ◄──┘
      │  sock_send(UDP → 192.168.7.1:5140，每次 ≤1400 B)
      ▼
ifnet ue0（内核自创，192.168.7.2/24）──► DWC3 bulk IN（ep 0x81）──► USB 线
主机：cdc_ether 网卡（02:00:5e:77:ee:01）→ 192.168.7.1/24 → nc/socat 收 UDP:5140
```

启动时先补发 ring 里最后 64 KiB，因此 USB 就绪前的早期内核日志也能收到。

### 1.2 出处：仓库与 commit

实现存活在 **ios-sweet 时代**仓库（hakios 现主线已弃用，见 §1.7）：

| 仓库 | 角色 | 本地副本 |
|---|---|---|
| `github.com/dipa-studio/ios-sweet`（用户 dipa-studio，237 commits，最后 push 2026-10-23） | 原始实现与全部 commit | `E:\k60-work\forks-review\ios-sweet`（本次克隆） |
| `github.com/XTOM0706/ios-sweet-k60`（非 fork，2026-10-21 建库，首提交 `2df0f31` 导入全部补丁） | K60 适配版 | `D:\Android\k60-ios\ios-sweet-k60`（原有克隆） |

关键 commit（dipa-studio/ios-sweet，日期均为 2026-10-17/18，`git log` 实测）：

| commit | 信息 | 内容 |
|---|---|---|
| `65a44a2` | xnu 0047: persistent console log on the userdata partition | console ring + 落盘后备（2026-10-17） |
| `809bf54` | xnu 0072: read-only USB state probe (DWC3 / QUSB2 / GCC) | 只读探针 |
| `381274a` | xnu 0073: USB device mode with endpoint 0 (enumeration), sweetusb=2 | EP0 枚举 |
| `e9969b9` | xnu 0074: force the VBUS session valid in the Qualcomm USB wrapper | VBUS 强制 |
| `59e7aec` | xnu 0075: USB Ethernet (CDC-ECM) function and ue0 network interface | ECM + ifnet |
| `992cadb` | xnu 0076: receive USB Ethernet frames into one cluster mbuf | RX 修复 |
| `5029e91` | xnu 0077: live console log over USB Ethernet (UDP to 192.168.7.1:5140) | **实时日志流** |
| `fdad0de` | xnu 0081: ue0 reports an active Ethernet link | link state |
| `fbf3a9c` | tools: sweet-usbnet.sh, host side of the USB Ethernet and live log | 主机脚本 |

### 1.3 逐文件剖析（行号 = 补丁文件在 XTOM0706/ios-sweet-k60 工作树中的行号；内容与上游 commit 一致）

**日志源（0047，`xnu/patches/0047-sweet-persistent-console-log.patch`）**
- 行 142–156：挂钩点在 `osfmk/console/serial_console.c` 的 `_cnputs()`——所有 console 输出（kprintf 与守护进程 /dev/console 写）必经此处；`sweet_log_append(c, size)` 在任何上下文可调用（原子计数 + memcpy，不阻塞，行 50–60）。
- 行 40–45：`SWEET_LOG_SIZE` = 4 MiB 静态 ring（内核 BSS 普通内存）。
- 行 68–116：`sweet_log_thread` 每秒把增量写到 **userdata 分区末尾 4 MiB+4 KiB 的 raw 块**（HFS 镜像之后的空闲区），块 0 是 `SWEETLOG` 头；这就是 panic 后的取证层，由 `tools/sweet-log-pull.sh` 在 recovery（OrangeFox adb root）里 `dd` 读出（脚本头注释：只读 userdata 末 1025 个 4 KiB 块）。

**探针（0072，行 44–138）**
- DWC3 at `0x0a600000`、QUSB2 PHY at `0x088e2000`、GCC at `0x00100000`（SM7150/sdmmagpie 偏移）。
- 安全设计：先读 GDSC/CBCR 确认电源与时钟开着才碰 DWC3/PHY 寄存器（访问 gated 块会挂）。
- boot-arg `sweetusb`：0=关，1=只报状态，2=起设备（0073 行 27–37）。

**EP0 设备栈（0073，行 46–425）**
- 注释（行 49–56）：ABL 把 DWC3 留在「上电、上钟、设备模式、 halted」状态，只需软复位设备控制器 + 自带事件缓冲（轮询、中断屏蔽）+ ep0 + RUN。寄存器与状态机照 Linux `drivers/usb/dwc3`（gadget.c、ep0.c）。
- **DMA 方案（行 371–380）**：`kmem_alloc_contig` + `pmap_find_phys` 拿物理地址直接给控制器，**不碰 SMMU**；非 cache 一致，用 `flush_dcache64` 维护（行 127–130）。16 KiB DMA 区布局：事件环/TRB/SETUP/数据（行 93–100）。
- 事件线程 1 ms 轮询（行 344–363），不需要接 GIC。

**VBUS 强制（0074，行 8–18、23–37）**
- Qualcomm wrapper「QSCRATCH」`0x0a6f8800`：`HS_PHY_CTRL |= UTMI_OTG_VBUS_VALID(20) | SW_SESSVLD_SEL(28)`，`SS_PHY_CTRL |= LANE0_PWR_PRESENT(24)`——对应 Linux `dwc3_qcom_vbus_override_enable`。不置位则控制器不见 VBUS、不拉 D+，枚举无从谈起。

**CDC-ECM + ue0（0075，457 行）**
- 描述符（行 109–126）：VID:PID `1209:0001`（pid.codes 测试 ID），CDC-ECM（类 02/06），bulk 0x81/0x01 各 512 B，interrupt 0x82 发 NETWORK_CONNECTION；主机 MAC `02:00:5e:77:ee:01`，手机 `…:02`。
- 行 327–399：内核用 ifnet KPI 直接造 `ue0`（`ifnet_allocate_extended` + `ether_demux` 等），`proto_plumb(PF_INET)` + 内核 socket `SIOCAIFADDR` 静态配 `192.168.7.2/24`。完全 BSD 层，无 IOKit/IONetworkingFamily。
- TX：mbuf 队列（32 深）+ TRB（行 261–303）；512 整倍数帧补 1 字节避免 ZLP（行 276–280）。

**实时日志（0077，107 行）——核心**
- 行 47–52 注释：「每 100 ms 把 console ring 的新字节作为 UDP 发到 192.168.7.1:5140（PC 上 `nc -ukl 5140`）。从最后 64 KiB 开始补发。**此处任何东西都不许 print（会自喂）**。boot-arg `sweetusblog=0` 关闭。」
- 行 56–92：`ud_log_thread`：`sock_socket(PF_INET, SOCK_DGRAM)`，循环 `sweet_log_copy(&pos, chunk, 1400)` + `sock_send`；`ud.configured` 未就绪前空转。
- `sweet_log_copy`（补丁首部，sweet_ufs.c 行 14–35）：落后超过 ring 容量自动快进到 `total - SIZE`（丢旧保新）。

**RX 修复与 link state（0076/0080/0081）**：0076 修 mbuf 0 长首块 panic（`mbuf_gethdr`+`mbuf_mclget` 单簇，行 8–24）；0080 只是路由/地址变更打印；0081 补 `SIOCGIFMEDIA`/`KEV_DL_LINK_ON` 让 configd 认为链路活着。

### 1.4 K60 适配痕迹（XTOM0706/ios-sweet-k60，未走通）

- `0143-k60-usb-probe-opt-in.patch`：探针改为默认关（`sweetusbprobe=1` 才跑），注释明言「sweet_usb_probe() 读的是 SM7150 地址……mondrian 的 eUSB2 PHY 在 0x88e3000，探针数据中止毁掉启动」。**DWC3 0xa600000 被认为与 mondrian 一致，只改 PHY**。
- `0148-k60-usb-rails-via-touch.patch`：`QUSB2_PA` 改 `0x088e3000`；eUSB2 PHY 电源轨 `ldob5`(879 mV)/`ldoc10`(1.2 V) 经 RPMh 使能（复用 touch 路径，因从 USB 探针里调 RPMh 会崩在 `rh_lookup`）。
- **在 K60 上从未跑到 ECM/日志流**：`PORT-STATUS-K60.md`、`NOTES.md` 无任何 `sweetusb=2` 在 mondrian 的实测记录（grep 无命中）；git log 无 USB 相关独立提交。即：hakios 的 USB 日志在 K60 上处于「地址和电源轨刚摸清、机制未验证」状态。

### 1.5 实测证据（upstream NOTES.md，D:\Android\k60-ios\ios-sweet-k60\NOTES.md）

- 行 13（0077s 启动）：**「LIVE LOG over USB：no more recovery round-trips」**——`sweetusb=2` 启动 + PC 跑 `tools/sweet-usbnet.sh`，每 100 ms 收到内核 console（含启动早期 64 KiB 补发）。
- 行 15（0076s 启动）：**ping 192.168.7.2 约 1 ms、200 包 0% 丢**（1500/512/1024 字节帧）。主机侧是 Linux `cdc_ether`。
- 行 17（0074s 启动）：主机高速枚举出 `1209:0001 ios-sweet "Sweet iOS (USB bring-up)"`；并记录 ABL 留下的控制器状态（GDSC/时钟全 on、DWC3 v3.20a、设备模式、halted）。
- panic/挂死时的后备仍是 recovery 里 `sweet-log-pull.sh`（行 13 末句）。

### 1.6 带宽、稳定性、限制、panic 行为

| 项 | 事实 | 出处 |
|---|---|---|
| 物理带宽 | USB 2.0 high-speed bulk（理论 480 Mbps）；日志节奏为 100 ms × ≤1400 B/包，文本量级远未触顶 | 0073 行 400（DCFG high speed）、0077 行 58–60 |
| 实测链路 | ping ~1 ms，0% 丢（200 包突发） | NOTES.md 行 15 |
| 稳定性设计 | 轮询线程（不依赖新 IRQ）；ring 满自动丢旧；`sweetusblog=0` 可关；USB 未配置时发送线程空转不阻塞启动 | 0073 行 344–363、0077 |
| 限制 1 | **UDP 无重传**——丢包即丢行，无序号/缺口标记 | 0077（协议就是裸 UDP） |
| 限制 2 | 事件 1 ms 轮询 + 日志 100 ms 节奏 → panic 前最多丢约 100 ms 的未发字节 | 0077 行 71 |
| 限制 3 | 无流量控制；主机不收时 mbuf 队列 32 深后丢弃 | 0075 行 288–296 |
| panic 行为 | panic/poll 路径的字节仍进 ring（`_cnputs` 全覆盖），但 `ud_log_thread` 是普通线程，调度一停就发不出去；**panic 尾部靠 userdata 分区尾的持久层事后拉取** | 0047 行 142–156、NOTES.md 行 13 |
| 主机依赖 | Linux `cdc_ether`（免驱）；macOS 支持 ECM；**Windows 无 inbox CDC-ECM 驱动**（社区共识，未找到微软官方出处；Windows 原生需改做 RNDIS） | NOTES.md 行 15；Windows 侧见 §5.3 |

### 1.7 hakios 现主线的状态（防止找错地方）

`oosexgang` 组织 7 个仓库（GitHub API，2026-11-02）：`hakios-xnu-kernel`（2026-11-01 仍在更新）、`hakios-metal`、`hakios-sm7325`（redwood 设备）、`hakios-uefi`、`hackios-web`、`hakios-mt6768`、`hackios-xnu-userland`。已克隆 `hakios-xnu-kernel`（`96ffbc5`）到 `E:\k60-work\forks-review\hakios-xnu-kernel`：**全树 grep 无 DWC3/USB gadget**；网络改为 `drivers/net/hakios.net.c` 的 en0 抽象（链接层是 Wi-Fi / QEMU virtio / modem IPA，`xnu/README.md` 驱动表）。**即「hakios 的 USB 读日志」只在 ios-sweet 时代的补丁系列里，不在当前主线。** 该仓库另有一个相关机制 `xnu/files/osfmk/arm64/loader_return.c`（见 §4.5）。

---

## 2. unixnu 路线可行性

### 2.1 我们树里的现状（xnu-work，xnu-8796.141.3）

| 前提 | 现状 | 证据 |
|---|---|---|
| USB 栈 | **完全没有**。无 AppleUSB/IOUSBHost/DWC3 任何痕迹；`drivers/`（/tmp/k60build/drivers）只有 Adreno740、AdrenoMetal、AppleKeyStoreState、ArmCpu、ArmDTPlatform、ArmVirtPlatform、DarwinBoot、GopFramebuffer、QcomGeniSpi、RamBlock、SoftwareAES、VirtioMmioBlock、VirtioMmioConsole | `grep -rln 'DWC3\|dwc3'` 全树空；drivers 目录列表 |
| BSD 网络 KPI | **已编进内核**：kernel.macho 含 `ifnet_attach`(30)、`sock_socket`(8)、`mbuf_allocpacket`(8)、`ether_demux`(3) 符号；树内 `bsd/sys/kpi_socket.h`、`kpi_mbuf.h`、`net/kpi_interface.h` 齐 | `/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho` strings |
| console 字节镜像 | **已有**：`osfmk/console/serial_console.c:517-520,601` 在 `console_write`/`console_write_unbuffered` 里调 `pong_ramoops_console_write`；实现于 `osfmk/arm/arm_init.c:113-118`；`pong_ramoops_console_init()` 于 `arm_init.c:669` 调用；保留区 `0xA7000000`、console 2 MiB、12 字节头；**并有只读 accessors `pong_ramoops_debug_base/start/size()` 供 bring-up 自检** | `osfmk/arm64/pong_ramoops_console.h:9-33` |
| 板级宏 | `ARM64_BOARD_CONFIG_PONG`（makedefs/MakeInc.def:63），hakios 补丁的 `#if ARM64_BOARD_CONFIG_SWEET` 可直接类比换名 | 同上 |
| 原语 | `ml_io_map`（osfmk/arm/machine_routines.h:703）、`kernel_thread_start`（osfmk/kern/thread.h:1793）、`PE_parse_boot_argn`（pexpert.h:337）、`kmem_alloc_contig`/`pmap_find_phys` 均在（hakios 用到的全部） | 各头文件 |
| SMMU 能力 | **有 kit 可用**：`/tmp/k60build/kits/ArmSmmu4K`；PongUfs 已有 `SmmuTakeover.h`（ARM SMMUv2 context 规划） | /tmp/k60build/kits、feeds/PongUfs-245e493f/SmmuTakeover.h:2 |
| KDP | `osfmk/kdp/`（kdp.c、kdp_udp.c、kdp_serial.c）在树中，但 KDP 需要 IOKit NIC 轮询驱动挂 `kdp_register_send_receive`，我们没有 | 树内文件列表 |
| boot-args | 打包期组装：`UniXNU-mondrian/scripts/build-native-bootimg-local.py:108-146` 写 `unixnu.toml args="..."`；`build-pong-prelinked-boot.py:110-113` 支持 `--kernel-arg` 追加（**加 arg 不改脚本**）。当前命令行约 263 字节（`E:\k60-work\candidates\4g-quiet\extracted\unixnu.toml:12`）；命令行预算两处口径不一：`drivers/DarwinBoot/.../BootArgs.h:21` 为 `CommandLine[1024]`，`scripts/build-darwinboot22-macos.py:61` 为 608，以实际构建链为准——加 `k60_usblog=1`（13 字节）均无压力 | 各文件行号 |
| 驱动形态 | 我们的带外驱动是 prelinked KEXT feed（PongUfs：`NativeUfs : IOService` + Info.plist），但 hakios 的 sweet_usb.c 是纯 BSD 文件 + 一个初始化调用，**不必套 IOKit**：新文件经 `UniXNU-mondrian/patches/xnu/` 补丁系列（现有 123 个，`xnu-patches.list`）进树，在 `arm_init.c:669` 附近加一行 `k60_usblog_init()` | feeds/PongUfs-245e493f/NativeUfs.cpp:123-127 |

### 2.2 K60 硬件事实（USB）

| 资源 | 值 | 出处 |
|---|---|---|
| DWC3 core | `0xa600000`（mondrian 沿用 SM7150 同址；pong 设计稿 DT 亦 `dwc3@a600000`） | 0143/0148 补丁；USB-LOGGING-PLAN.zh.md 行 45–46 |
| USB2 PHY | **eUSB2 hsphy `0x88e3000`**（注意与 sweet 的 QUSB2 `0x88e2000` 不同，直接照抄会数据中止） | 0143/0148 补丁注释 |
| USB3 PHY | `ssphy@88e8000`（首版不用） | USB-LOGGING-PLAN.zh.md 行 49 |
| QSCRATCH（VBUS override） | `0xa6f8800`（0074 的地址，Qualcomm wrapper 惯例地址，K60 未实测） | 0074 补丁行 13 |
| PHY 电源轨 | RPMh `ldob5` 879 mV（vdd）、`ldoc10` 1.2 V（vdda12）；从 USB 上下文直接调 RPMh 会崩，需复用 touch 路径的时机 | 0148 补丁注释 |
| GCC 时钟/GDSC 偏移 | **未在本地确认**（hakios 表是 SM7150/sdmmagpie；SM8475 属 waipio 家族，需从 Linux `gcc-sm8450.c` 取数；本地 pong-adreno-linux 无此文件） | 0072 行 52–73；本地 grep 无 |
| SMMU | DT 标 USB 走应用侧 SMMU（pong 设计稿 `iommus=<0x5b 0 0>`，K60 未核对）；**USB DMA 是否必须建 context 未知，是最大技术不确定性**（见 §2.3 风险①） | USB-LOGGING-PLAN.zh.md 行 50 |
| UEFI 侧 | uefi-mondrian `DXE.inc:5` 注释：K60 UEFI 只含开源 provider，**不含 vendor USB 栈**——UEFI 不会与 XNU 抢 USB，XNU 必须全自理 | DXE.inc 行 1–20 |

### 2.3 移植方案与风险

**机制完全可移植**：hakios 全部代码是自包含 BSD 级 C（无 IOKit 依赖、无网络栈外部服务），我们内核的 KPI 符号、原语、console 镜像、打包 arg 通道逐项对上（§2.1）。适配点只有：

1. **地址表**换 K60 的（§2.2），GCC 偏移待查（风险②，只影响探针的「先读后碰」安全检查的解读，不影响主逻辑）。
2. **电源轨**：RPMh `ldob5`/`ldoc10` 使能时机避开 `rh_lookup` 崩溃（0148 已给出模式：挂在已验证的 touch 初始化路径里；我们树里 RPMh 驱动形态不同，需找等价物或先依赖 ABL 已供的电——fastboot 刚用完这个口，大概率轨还开着）。
3. **日志源不用动 serial_console.c**：USB 发送线程直接经 `pong_ramoops_debug_base()/start()/size()` 快照读取 ramoops 镜像增量——比 hakios 还多一层隔离（hakios 是自己另起 ring；我们复用已验证的镜像，零侵入 console 热路径）。
4. **SMMU（风险①）**：hakios 物理地址直 DMA 在 sweet 上成立；K60 的 UFS 已证明该平台 SMMU 是要管的（SmmuTakeover.h）。若 ep0 阶段枚举失败且寄存器侧一切正常，则用 `ArmSmmu4K` kit 给 USB stream 建 4 KiB 页表 context（kit 现成，但属新增工作，量级参考 PongUfs 的 SmmuTakeover）。**这在最小验证第 A 档就会暴露**（ep0 控制传输本身就走 DMA）。
5. **中断**：首版照抄 1 ms 轮询，不接 GIC（pong 设计稿行 61 也是这个结论）。
6. **启动方式**：`fastboot boot` 无额外限制——ABL 用完 USB 后 XNU 接管重枚举，主机看到一次设备切换（fastboot 的 `2717:ff48` 消失、`1209:0001` 出现），线缆不动。`fastboot boot` 的 768 MiB 镜像上限与本方案无关（内核增量 ~50 KB）。

**不需要 iBoot/不需要改 UEFI**（hakios 路线裸控 DWC3；UEFI 本来就不碰 USB）。**不需要动 boot-args ABI**，`--kernel-arg k60_usblog=1` 即可。

### 2.4 主机侧（Windows + WSL2）

- **推荐路径**：手机 ECM 枚举到 Windows → `usbipd attach --wsl --busid <id>` 桥进 WSL2 → Ubuntu 侧 `cdc_ether` 自动绑定（**已验证 WSL2 官方内核 `linux-msft-wsl-5.15.y` 的 config-wsl 含 `CONFIG_USB_NET_CDCETHER=y`**，raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel 当日拉取）→ `sudo ip addr replace 192.168.7.1/24 dev <if>` → `socat -u udp-recv:5140 -` 或 `nc -ukl 5140`。usbipd 安装与 attach 流程见微软官方文档 learn.microsoft.com/windows/wsl/connect-usb（需要 usbipd-win ≥5.0、WSL 内核 ≥5.10.60.1）。
- 每次重启动设备会重新枚举，需要重新 attach（可脚本化轮询；细节未实测）。
- 备选：任何原生 Linux 机器 / 树莓派（cdc_ether 免驱）+ 同一脚本；macOS 原生支持 ECM（未实测）。
- Windows 原生直接收：无 inbox ECM 驱动（未找到微软官方出处，社区共识；若必须 Windows 原生，设备侧要换成 RNDIS 功能——额外工作量，不建议为首版做）。

---

## 3. 备选方案逐项评估

| # | 方案 | 可行性 | 工作量 | 说明与出处 |
|---|---|---|---|---|
| A | **KDP over USB** | 中（二阶段可行） | 高 | 树内 `osfmk/kdp/kdp_udp.c` 等俱在，但 KDP 走 IOKit NIC 轮询驱动（`kdp_register_send_receive`），我们无 IOKit 网络栈。路径：先落 ECM（§2.3），再写一个 KDP 传输 shim 在 DWC3 bulk 端点上收发 raw Ethernet 帧（绕开 ifnet，模拟 NIC 的 send/receive 回调）。收益是全套 gdb；但作为「拿日志」手段属于杀鸡用牛刀。xnu-work 文件列表 + 0075 的 ifnet-only 事实 |
| B | **物理 UART 引出** | 低 | 高 | ISSUES.md I-20261102-03：「串口 COM3/COM4 是蓝牙虚拟口读不到内核输出」「平台限制（无引出 UART）」。K60 无已记录的 UART 测试点；即便拆机飞线（GENI UART 模式），还需新写 GENI UART 内核驱动（QcomGeniSpi 是 SPI 不是 UART）。 |
| C | **落盘可写 Data 卷，下次读取** | 中-高 | 中 | 我们已有 `pong_data_mount=1 pong_data_rw=1`（K60DATA 可写，DECISIONS.md 行 35 实测 mkdir ok）。照 hakios 0047 的 **raw 分区尾写**（不经过 APFS，避免文件系统状态污染）：内核线程每秒把 ring 增量写 K60DATA 所在分区尾部空闲 raw 块（PongUfs/NativeUfs 已具备写能力）。回读两路：① Android 侧 `dd` 需 root，**是否有 root 未确认**；② 下次 iOS 启动由 ECM 回播（ECM 落地后零额外通道）。这是 ECM 的天然互补（覆盖 panic 尾部），建议作为 ECM 之后的第二步。hakios 0047 + sweet-log-pull.sh 为证 |
| D | **iBoot 调试通道** | 不适用 | — | 启动链是 ABL→UEFI(unixnu)→XNU，全程无 iBoot。 |
| E | **hakios loader_return（生态内已有，上面未列）** | 低-中 | 高 | `hakios-xnu-kernel@96ffbc5` 的 `xnu/files/osfmk/arm64/loader_return.c:1-15`：loader 不 ExitBootServices，panic/halt/定时时内核收集 message buffer+panic buffer+kprintf 跳回 UEFI 存日志。原文约束：「Only valid while the kernel does not drive hardware that UEFI also uses」——K60 的 XNU 驱动 UFS/显示/USB，与 UEFI 环境冲突面大，且需 uefi-mondrian 配合改造。列为远期备选。 |
| F | **Qualcomm EUD** | 未知 | 未知 | pong 设计稿 DT 表提到「另有 EUD 依赖」（USB-LOGGING-PLAN.zh.md 行 48）。EUD 可在主 USB 栈外提供调试口，但主机侧要 QPST/鉴权，可行性未调研，标记「未找到足够证据」。 |
| G | **unixnu VirtioMmioConsole** | 真机不适用 | — | `/tmp/k60build/drivers/VirtioMmioConsole` 是 QEMU 通道，真机无 virtio。 |
| H | **sheng 式 Linux 恢复盘 CDC-ACM shell** | 可行但非实时 | 中 | USB-LOGGING-PLAN.zh.md 行 34：sheng 用独立 Linux 以 CDC-ACM 提供 shell 读 userdata 尾日志。属「重启后读取」类，不能解决「实时看 XNU」；且 SM8550 镜像布局不能直接用。 |

---

## 4. 推荐方案总装与 panic 策略

**主通路（实时）**：hakios ECM 移植版（§2.3）——kernel console 经 ramoops 镜像 → UDP/5140 → WSL2。
**后备（panic 尾部）**：方案 C 的 raw 分区尾持久层 + 下次启动 ECM 回播（或 Android root dd，待确认）。
**远期可选**：KDP shim（§3-A）拿 gdb；loader_return（§3-E）不动。

预期日常体验（对齐 hakios 实测）：`fastboot boot` 后约 10–30 s（内核到 `arm_init` 晚期）Windows 弹出新网卡 → attach 进 WSL2 → UDP 流出从启动早期补发的完整内核日志；守护进程崩溃循环（当前 4g-quiet 的痛点）的每条 trace 实时可见，不再拍照。

---

## 5. 最小验证步骤（拿「第一行内核日志」）

### 5.1 改动清单（全部为新增，不动既有行为；boot-arg 默认关）

1. 新补丁 `UniXNU-mondrian/patches/xnu/02xx-k60-usblog.patch`：
   - 新文件 `bsd/dev/k60_usblog.c`（`#if defined(ARM64_BOARD_CONFIG_PONG)`）：照抄 ios-sweet 0072（探针）+0073（ep0）+0074（VBUS），地址换 §2.2 的 K60 表；`sweetusb`→`k60_usblog`，语义不变（0/1/2）。
   - `bsd/conf/files` 加一行 `bsd/dev/k60_usblog.c standard`（对照 0072 行 1–7 的加法）。
   - `osfmk/arm/arm_init.c`：在 669 行 `(void)pong_ramoops_console_init();` 之后加 `(void)k60_usblog_init();`（无 arg 时立即返回）。
2. 打包：`build-pong-prelinked-boot.py --kernel-arg k60_usblog=1`（现有机制，不改脚本）。

### 5.2 验证 A（机制档）：ep0 枚举

- `k60_usblog=1` 只跑探针：屏幕/现有 ramoops 应出现 `K60 USBLOG: GDSC … clk … DWC3 GSNPSID 0x…`——**判定 SM8475 时钟/电源/DWC3 可读性**（GCC 偏移不对时这里先暴露，表现为 GDSC 位解读异常；此时只允许降回「直接试碰 DWC3」的受控尝试，因为 fastboot 刚用完此口）。
- `k60_usblog=2` 起 ep0：Windows 设备管理器/WSL2 `lsusb` 应出现 `1209:0001`「K60 iOS (USB bring-up)」。
- **判定矩阵**：
  - 无探针输出 → init 调用没接上（实现问题）；
  - 探针显示时钟/电源关 → 平台配合问题（先查 RPMh 轨，再查 GCC 偏移）；
  - 探针正常但枚举失败 → 若寄存器流程全对而 SETUP 无事件，高度怀疑 **SMMU 拦 DMA**（风险①实锤）→ 转 ArmSmmu4K 建 USB context 后重试；
  - 枚举成功 → **机制全通**（时钟、PHY、VBUS、SMMU、DMA 全部排除）。

### 5.3 验证 B（日志档）：第一行内核日志到主机

在 A 的基础上往补丁里加 0075+0076+0077 对应部分（ECM 描述符、ue0、UDP 线程），日志源用 `pong_ramoops_debug_base()/start()/size()` 增量读。

主机侧：

```powershell
# Windows 管理员 PowerShell（首次）：winget install dorssel.usbipd-win
usbipd list                      # 找到 1209:0001 的 busid
usbipd bind --busid <id>
usbipd attach --wsl --busid <id>
```

```bash
# WSL2 Ubuntu-24.04（cdc_ether 已验证内置）
ifname=$(ip -o link | grep -i 02:00:5e:77:ee:01 | awk -F': ' '{print $2}' | cut -d@ -f1)
sudo ip addr replace 192.168.7.1/24 dev "$ifname"; sudo ip link set "$ifname" up
ping -c3 192.168.7.2             # 期望 ~1ms（对照 NOTES.md 行 15）
socat -u udp-recv:5140 - | tee logs/k60-usb-first.log
```

- **预期第一屏**：ramoops 镜像自启动以来的增量（含早期启动行），随后每 100 ms 滚动。
- **判定矩阵**：
  - `lsusb` 无 ECM → 回 5.2 矩阵（机制问题）；
  - ECM 在但 ping 不通 → 描述符/alt-setting/endpoint 配置（实现问题，机制已通）；
  - ping 通但 UDP 无数据 → log 线程/ramoops 快照读取（实现问题；查 `k60_usblog=2` 的屏幕打印计数）；
  - UDP 有数据 → **打通**，记录首行时间戳与启动耗时。

### 5.4 失败时的总判据

- A 档过、B 档挂 → 实现问题（网络层），机制无虞；
- A 档挂 → 机制问题，按 5.2 矩阵定位到时钟/电源/PHY/VBUS/SMMU 哪一层；
- 全程不得影响无 arg 的默认启动（arg 缺席 = 完全不执行，等价现状）。

---

## 附：本次调研产物位置

- 克隆：`E:\k60-work\forks-review\ios-sweet`（dipa-studio 上游全史）、`E:\k60-work\forks-review\hakios-xnu-kernel`（oosexgang 主线，blobless）
- 既有相关文档：`UniXNU-mondrian/docs/USB-LOGGING-PLAN.zh.md`（pong 时代 CDC-ACM 设计稿，未实现，被本报告的 ECM 实证路线取代）；`E:\k60-work\docs\ISSUES.md` I-20261102-03（取证手段约束）；`E:\k60-work\docs\DECISIONS.md`（4g-quiet 诊断形态）
- 未找到/未确认清单：SM8475 GCC USB 时钟偏移（需 Linux gcc-sm8450.c）；K60 USB SMMU stream 编号与行为；Android 侧是否有 root（落盘回读用）；Windows 原生 ECM 驱动的官方说法；EUD 可用性。
