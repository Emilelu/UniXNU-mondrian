# iOS 27（24A446）USB 导出面、驱动 undefined 与三段接入点

状态：离线研究，**没有构建、没有上机、没有 fastboot**。所有数字都在本机对固定产物复现。
日期：2026-11-21。分支 `feat/usb-27`，汇报 `E:/k60-work/scratch/reply-usb27.md`。

官方依据（iron-17）：`E:/hackios/UniXNU/docs/zh/porting/usb.md`
§源码与接口 `{#source-map}`（:9-17）、§2 启动控制器（:41-58）、§3 注册类（:62-81）、
§4 连接线缆角色（:85-98）、§5 配对（:100-109）、§6 构建和验证（:111-141）。

---

## 1. 口径：先纠正一个数字

上一轮报过「`llvm-nm-18 | grep -ci 'cdc\|acm_\|usb_serial\|k60_usb'`：27 = 87，16.6.1 = 170」。
这个口径不成立：`cdc`、`acm_` 全是十六进制字符，`llvm-nm` 输出的**符号地址**必然命中，
计数衡量的是地址里出现过多少 `cdc`，不是 USB 代码有多少。实测：

| 口径 | 27（652237c6） | 16.6.1（c8a7619d） |
| --- | --- | --- |
| 上一轮的四词正则 | 87 | 55（同一族产物，不是 170） |
| `grep -i usb`（不含地址噪声） | **2** | **9** |
| `grep -c AppleUSB` | 0 | 0 |
| `grep -c native_usb`（QcomDwc3 的计数器） | 0 | 0 |
| `grep -c QcomDwc3` | 0 | 0 |
| `grep -c k60_usblog` | 0 | 7 |
| `grep -c k60_`（整族诊断面） | 64 | 258 |

所以正确说法不是「gadget 在、链接的驱动少」，而是：
**27 内核里既没有 USB gadget，也没有 Apple USB 栈；`k60_usblog` 七个入口全部消失，`k60_` 诊断面从 258 掉到 64。**
16.6.1 的 9 条就是 `_k60_usblog_{init,start,mode,reset,reset_to_fastboot,running,console_up}` 加两条 `_sk_netif_compat_usb_eth_*`；
27 只剩那两条 `sk_netif`（它们属于网络兼容层，不是 USB 传输）。

被测量产物（只读副本，`sha256` 已核）：

| 产物 | 路径 | 大小 | sha256 |
| --- | --- | --- | --- |
| 27 kernel collection | `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho` | 93,061,120 | `652237c6bf5476f216298df9ac71044ec51aa2349c3c31871e822810e163a19e` |
| 16.6.1 kernel | `/opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho` | 105,517,056 | `c8a7619dbac1aa8e5bdc0e2bf571533b69a36b46cd9599c9377d5f671e4012f2` |
| 16.6.1 `k60_usblog.o` | `…/DEVELOPMENT_ARM64_PONG/bsd/DEVELOPMENT/k60_usblog.o` | 104,768 | `774a47dfbf5b82cb302edcc646cf754b4696e55a12c1d8613f429f6d35cfaa9d` |

工具：`llvm-nm` Ubuntu LLVM 18.1.3、Python 3.12.3（`tomllib`/`plistlib`）。
27 的 nm 全量输出：`E:/k60-work/scratch/usb27/nm-27-652237c6.txt`（67,577 行）。

---

## 2. 27 导出面 vs 驱动 undefined（交付 ②）

### 2.1 为什么「无 USB」不是 nm 看不见

27 的 `kernel.macho` 是 **MH_FILESET**（filetype `0xc`，46 条载入命令，32 条 `LC_SUB_FILESET_ENTRY`），
`__PRELINK_INFO` 是 XML plist，`_PrelinkInfoDictionary` 有 38 个条目，减去 7 个
`com.apple.kpi.*` 伪条目（`_PrelinkExecutableLoadAddr = 0x7fffffffffffffff`、size 0）
之后**真正被 prelink 的 kext 是 31 个**，与 32 条子文件集命令（31 kext + `com.apple.kernel`）对得上。
31 个里没有任何 USB/SCSI kext。

但 `strings -a | grep -c AppleUSB` = **1295**（16.6.1 内核为 0）。这 1295 条不是可加载代码：

- 它们出现在 `__PRELINK_TEXT`，地址落在 31 个 kext 的 `__TEXT` 区间之外的空洞
  （`IOSurface` 结束于 `0xfffffff007a14e10+0x72b0`，`AppleImage4` 起于 `0xfffffff007b41050`）；
- 没有 `_PrelinkInfoDictionary` 条目、没有子文件集条目、nm 不为它们出符号。

结论：那是**原始 kernelcache 遗留在 `__PRELINK_TEXT` 的孤立字节**（`AppleUSBXDCI.cpp`、
`AppleUSBXHCI[%p]::%s: port %d in test mode %d`、`AppleUSBDeviceMux` 17 条、`IOUSBHostDevice` 11 条……），
不是 USB 栈。`com.apple.driver.AppleUSBXDCI` 与 `IOUSBDeviceFamily` 各只剩 2 条字符串，
落在 `__DATA`，同样不可加载。

### 2.2 驱动 undefined 对照表

驱动侧唯一能离线枚举 undefined 的产物是 16.6.1 编译好的 `k60_usblog.o`（104,768 B，34 个 undefined）：
27 collection 定义 64,931 个符号、undefined 0，两者对减 → **可解析 27 个，缺 7 个**。
缺的 7 个全部是 16.6.1 K60/Pong 诊断面，没有一个是 USB 传输本身：

| 缺失符号 | 定义处（16.6.1 补丁） | 轴 | 在 27 里的处理 |
| --- | --- | --- | --- |
| `_k60_checkin_compat` | `patches/xnu/0337-k60-checkin-compat.patch:10` | 诊断：用户态 check-in 计数 | 需带补丁，或让 gadget 去掉该依赖 |
| `_k60_exec_count` | `patches/xnu/0235-k60-exec-exit-trace.patch:18` | 诊断：exec/exit 计数 | 同上 |
| `_k60_exit_count` | `patches/xnu/0235-k60-exec-exit-trace.patch:19` | 诊断：exec/exit 计数 | 同上 |
| `_k60_prevlog_dump` | `patches/xnu/0331-k60-prevlog-replay.patch:20` | 诊断：上次启动日志回放 | 同上 |
| `_PE_k60_reset_now` | `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-panic-report.patch:85` | 诊断：panic 路径复位 | 同上 |
| `_pong_ramoops_debug_base` | `patches/xnu/0306-k60-console-snapshot.patch:325` | 控制台：ramoops 环基址 | 同上 |
| `_pong_ramoops_snapshot` | `patches/xnu/0306-k60-console-snapshot.patch:18` | 控制台：ramoops 环抓取 | 同上 |

机器可读版本：`docs/research/eight-step/usb-27-providers.tsv`（喂给判据脚本 `--providers`）。

可解析的 27 个（27 里都有，说明内核/BSD 基础设施够用）：
`_PAGE_SHIFT_CONST`、`_PE_parse_boot_argn`、`___stack_chk_fail`、`___stack_chk_guard`、
`___ubsan_handle_sub_overflow_minimal`、`_assert_wait_deadline`、`_bzero`、`_clock_interval_to_deadline`、
`_delay`、`_flush_dcache64`、`_kernel_map`、`_kernel_pmap`、`_kernel_thread_start`、
`_kmem_alloc_contig_guard`、`_memcmp`、`_memcpy`、`_ml_io_map`、`_panic`、`_pmap_find_phys`、
`_printf`、`_reboot_kernel`、`_strcmp`、`_strlen`、`_thread_block`、`_thread_deallocate`、
`_thread_terminate_self`、`_vprintf`。

**口径限制（必须写清）**：`QcomDwc3.cpp` 的 undefined **无法离线枚举**——它没有为 27 编译过的 `.o`，
而硬约束禁止构建。现在能证明的只有「27 的 collection 里没有任何符号能解析 `AppleUSBXDCI`/`AppleUSBXHCI`
这两个 C++ 父类」，因为 `--require-prefix AppleUSB` 为 0、`native_usb_stats` 与 `QcomDwc3` 也是 0。
要补上这一格，需要 Lead 给一次允许的构建（`QcomDwc3.cpp` 编到 BCM2837 obj 后跑同一个 `object` 子命令）。

### 2.3 缺的符号属于哪个 config

27 的 USB 不在 Kconfig 面：`.config` 里 `CONFIG_XNU_NATIVE_UFS/ADRENO/LEGACY_DISPLAY` 都是 `n`，
且**没有任何 USB 开关**。USB 由四层决定，27 现状逐层为空：

| 层 | 位置 | 27 现状 | 要让 USB 出现必须改哪 |
| --- | --- | --- | --- |
| prelink 根 | `E:/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml:41` | 31 个 kext，**0 个 USB** | 在 `board.toml` 加 `["kernel"."prelink"]` 的 `roots`（sheng 的 11 条见 `E:/hackios/UniXNU-sheng/board.toml:25`） |
| 组件 | `E:/hackios/k60-gates/board.toml:14` `components.include` | `ArmDTPlatform`/`ArmCpu`/`XnuPrelink`/`PongUfs` | 加 `QcomDwc3`（目录 `E:/hackios/UniXNU/components.toml:513-528`，revision `e4efe95c903a737e0f5955e5b50a8fb4d2a7d718`） |
| 补丁序列 | `xnu-inputs.json` / `xnu-patches.list` | 104 条，**0 条 USB**（无 0300/0307/0308、无 0405-0411） | 16.6.1 的 `patches/xnu/{0300,0307,0308}` + `patches/usb/0405-0411` 从 `E:/hackios/k60-gates` 移植到 12377 |
| 启动参数 | `payload.json` `kernel_args` | `-v serial=3 debug=0x14e …`，无 `sheng-usb` | 走官方路由加 `sheng-usb=1`（usb.md:62）；走自写 gadget 加 `k60_usblog=2`（16.6.1 形状，`E:/hackios/k60-gates/board.toml:173-174`） |

`bNumConfigurations=0` 与 `stage 12` 那类现象在 27 上现在连判据都还谈不上：控制器代码（`QcomDwc3`）根本没进任何 27 产物。

### 2.4 两条路线不能混为一谈

| 路线 | 组成 | 27 现状 | 16.6.1 证据 |
| --- | --- | --- | --- |
| 官方 Apple 栈 | `QcomDwc3` → `AppleUSBXDCI`/`AppleUSBXHCI`（11 个 prelink 根） | 根为 0、组件未选、ABI 头未生成 | sheng 24A446 真的跑起来了（`drivers/qcom-dwc3.md`） |
| 自写 gadget 控制台 | `bsd/dev/k60_usblog.c`（CDC-ACM，VID 0x1209/PID 0x0001） | 源不在 27 `bsd/dev`（只有 `qbt_k60.c`），`bsd/conf/files:110-115` 无该行 | 2026-11-15 `c`=mode2 回环 `sent=64 received=64`、`d`=mode1 复合声明后出字（`k60-usb/docs/research/usb/08-on-device.md`） |

27 的 console 目前是 `0543-k60-ios27-panel-console.patch`（屏幕），**不是 USB**。
所以「USB 控制台」这条线在 27 上等于从零接一条：要么走官方栈 + Apple 的 CDC 驱动根（是否存在于 24A446 kernelcache 未证），
要么把 `k60_usblog.c` 搬到 12377 并带上 2.2 表里的补丁。

---

## 3. UCSI / eUSB2 / QMP 三段在 27 的接入点（交付 ③）

驱动源码：`E:/hackios/k60-usb27/refs-QcomDwc3/`（`git clone UniXNU/QcomDwc3`，catalog 钉
`e4efe95c903a737e0f5955e5b50a8fb4d2a7d718`；本地 HEAD `f5edd26d`，关键字句两版一致，行号按钉住的那版）。
地址常量在 `QcomDwc3.cpp:40-41`：
`kCore=0x0a600000, kAppleWindow=kCore+0xc000, kQscratch=kCore+0xf8800, kGcc=0x100000,
kTcsr=0x1fd5000, kPhy=0x088e3000, kSmmu=0x15000000, kRsc=0x17a20000`。

### 3.1 eUSB2 PHY（USB2 高速，K60 的 `maximum-speed=high-speed` 就落在这段）

| 项 | 内容 |
| --- | --- |
| 驱动入口 | `QcomDwc3.cpp:208 void phyInit()`，`:209` 循环写 `kQcomEusb2Init`；`:216 selectUtmiClock()` 是 QMP 失败后的退路 |
| 表 | `QcomEusb2Phy.h:12 kQcomEusb2Init[]`（`QcomMaskedWrite{offset,mask,value}`），`:17 {0x54,0x70,0x40} /* FSEL 38.4 MHz */` |
| 时钟前提 | `QcomEusb2Phy.h:2-4`「19.2 MHz … TCSR_USB2_CLKREF_EN，parent RPMH_CXO_CLK = xo_board 76.8 MHz ÷2」 |
| K60 硬件 | eUSB2 hsphy `0x088e3000`（与驱动 `kPhy` 同址）；`E:/hackios/k60-gates/patches/xnu/0300-k60-usblog-ep0.patch:121`「mondrian: the USB2 PHY is the eUSB2 hsphy at 0x88e3000 (sweet: QUSB2 0x88e2000)」；`E:/hackios/k60-usb/docs/research/usb/RESEARCH.md:109` 记 `mondrian.dts:16879 qcom,usb-snps-eusb2-phy`，len `0x154` |
| 27 接入点 | bringUp **stage 7**（`QcomDwc3.cpp:591-595`）→ 官方 usb.md:51「启动 eUSB2 PHY，再启动 QMP PHY……」，预期 usb.md:58 到 stage 9、`native_usb_stats[1]` = 核心 ID |
| 现状/未知 | 27 无控制器代码，无日志可判。FSEL 表是 38.4 MHz，而 K60 的 `xo_board` 也是 76.8 MHz（与 sheng 同族），但 K60 主板上 USB2 参考时钟是否走 TCSR 未在本地取证 → 需要 16.6.1 实测的 TCSR 值或 DT `qcom,tcsr-usb2-clkref` |

### 3.2 QMP PHY（SuperSpeed；**不在 `kPhy`**）

| 项 | 内容 |
| --- | --- |
| 驱动入口 | `QcomDwc3.cpp:307 bool qmpInit(bool reverse)`，**自己再映射一次 `0x088e8000`**（`:307` 内 `mapRegion(phy, 0x088e8000, 0x3000)`），与 `kPhy=0x088e3000` 是两个窗口 |
| 时钟/复位 | `:313-314` GCC reset `gGcc.va+0x50000/4`、common `+0x50008/4`；`:315` rcg(0x39070,0)/branch(0x39060)/branch(0x39064)；`:316-317` `sm8550_gcc_update32(+0x3906c,3,0)` 与 `(+0x39068,0,1)`（PIPE 时钟来自 PHY） |
| 序列 | `:319-331` COM_POWER → ResetOvrd → Typec → Mode(USB3_MODE) → Swi → Reset → PowerDown → 写 `kQmpUsb3Init[]`（`:327`）→ Reset/Start(3) → 等 Status bit6 清；`:332` 记 `native_usb_stats[33] = kQmpStatus` |
| 表来源 | `QcomQmpUsb3.h:1-3`「Generated by `scripts/gen-qmp-usb3-table.py` from Linux `drivers/phy/qualcomm/phy-qcom-qmp-combo.c`」；寄存器 enum 在 `:5`（`kQmpReset 0x1c00`/`kQmpStart 0x1c44`/`kQmpStatus 0x1c14`/`kQmpPowerDown 0x1c40`） |
| 调用顺序 | `superSpeedInit()` `:335-343`：先读 TLMM `0xf100000` 的 orientation（`reverse = tlmm.va[(11*0x1000+4)/4] & 1`，TLMM 11，高有效），再 `return retimerInit(reverse) && qmpInit(reverse);` ⇒ **中继器在 QMP 之前**，与 usb.md:50-51 的 stage 6/7 顺序一致 |
| K60 硬件 | QMP combo `0x088e8000`，与 K60 DT 节点 `qcom,usb-ssphy-qmp-dp-combo@88e8000` 同址（`E:/hackios/UniXNU-mondrian/docs/plans/OFFICIAL-DRIVER-MAP.md:455,464`；`docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:81` 记 `fdt1:16900`） |
| 27 接入点 | 同一 stage 7 的后半段；失败回落 `selectUtmiClock()`（`:216`） |
| 现状/未知 | K60 DT 写的是 `maximum-speed=high-speed`（`FEATURES-DRIVERS-RESEARCH-2026-10-31.md:81`，`fdt1:16829-16860`），所以 **QMP 不必然要成功**：USB2 只在 eUSB2 上跑也能出控制台。要不要 10 Gbps 是后面的目标，不是控制台的前提 → 判据：`native_usb_stats[33]` 与 `gSuperSpeed` |

### 3.3 UCSI（线缆角色，决定 device/host）

| 项 | 内容 |
| --- | --- |
| 驱动入口 | `QcomDwc3.cpp:790 qcom_ucsi_start`、`:797 qcom_ucsi_receive`、`:803 qcom_ucsi_tick`、`:808 qcom_ucsi_polling`、`:809 qcom_ucsi_request_data_host`、`:814 qcom_ucsi_data_host`、`:815 qcom_ucsi_connection`（全 `extern "C"`） |
| 角色判定 | `QcomDwc3.cpp:609 QcomUcsi gUcsi;`，`:629-640 cableChanged()`：`gVbusOn>0` → device；`gUcsi.status_valid && connected && usb` → partner DFP 取 device、UFP/CableUfp 取 host；都不回答 → device（与 usb.md:93 原句「两个来源都没有回答时运行设备角色」一致） |
| 协议侧 | `QcomUcsi.h:22 kUcsiPartnerDfp=1/Ufp=2/CableUfp=4`；`:44 ucsi_start`、`:49 ucsi_command`、`:54 ucsi_advance`、`:117 ucsi_receive`、`:129 ucsi_tick`（`kUcsiPollMs` 轮询）；`:36 ucsi_write_request` |
| 消费者（sheng） | `E:/hackios/UniXNU-sheng/package/ShengBattery.cpp:31-34` weak_import 七个符号、`:75 ucsiTimer->setTimeoutMS(20)`（20 ms，对应 usb.md:91）、`:79 qcom_ucsi_tick`、`:214 qcom_ucsi_start`、`:235-236 qcom_ucsi_receive`（长度 4 且 magic `32779 = 0x800B`） |
| K60 硬件 | 27 payload 的 `hardware.dtb`（`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/device-tree/hardware.dtb`，反编译仅 225 行）里**没有 usb 节点**，但**有 `pmic-glink` 的 `battery-charger` 子节点**，`protection-domain = "tms/servreg", "msm/adsp/charger_pd"` —— UCSI 的消息源正好是充电器 PD |
| 27 接入点 | 板级充电器驱动（27 侧即 `ShengBattery` 同构的 Pong 电池驱动）+ 上表七个 `qcom_ucsi_*`；`qcom_ucsi_polling` 返回 true 时要 20 ms 定时器 |
| 现状/未知 | K60 是否真从 `charger_pd` 收到 `0x800B` 消息未取证。没回答时按 usb.md:93 跑 device 角色，对「做控制台」是可接受的默认 → 判据：`native_usb_stats` 与 UCSI 收包计数 |

### 3.4 三段共用的 27 接缝

| 接缝 | 位置 | 27 现状 |
| --- | --- | --- |
| SMMU stage 1 恒等上下文 | `QcomDwc3.cpp:587 smmuIdentity()`，usb.md:55-56「使用 write-back、inner shareable 块」，`:49`「创建该流的 SMMU 上下文」 | K60 实测 stream **0x0**（`OFFICIAL-DRIVER-MAP.md:464`），sheng 是 **0x40** ⇒ stage 5 的参数必须换 |
| 类 ABI | ABI 头由 `E:/hackios/UniXNU-sheng/scripts/build-gop-legacy-display-27.py:550-589` 从 `scripts/usb-xdci-24A446.json` 生成（`AppleUSBXDCI` 280 槽、`instance_size` 静态断言；槽 179 `KEEP_CONFIGURATIONS`、227 `DESIRED_POWER`、267/268 `POWER_ON/OFF`、275 `CONTROLLER_RESET`） | 27 产物无该头；`gen-usb27-abi.py:14-16` 需要 `out/ipsw/24A446/kernelcache.decompressed`（VT `0xfffffe00083f24c0`、COUNT 280、BASE 168），**本机没有这个文件** |
| prelink 根 | usb.md:70「把 USB 栈加入 `board.toml` 中 `[kernel.prelink]` 的 prelink 根」 | `E:/hackios/k60-gates/board.toml` 无 `[kernel.prelink]` 段 ⇒ 用 profile 的 31 个根 ⇒ 无 USB |
| 两处覆盖 | usb.md:78-79「没有 `IOPort` 传输对象时，`AppleUSBXDCI` 的 179 号槽返回 false」「主机模式下，xHCI 子类对 family 的期望电源回答开启，设备栈回答 0」 | `QcomDwc3.cpp:549/573` 已实现，随组件一起进 27 才有意义 |

---

## 4. 离线判据（交付 ④）

脚本：`scripts/usb27/kc-surface.py`（只读，不构建；`sha256 a0551472207515e23a001c3aae6d0ca447a9004cebed73df016103967eba2f71`）。
数据：`docs/research/eight-step/usb-27-providers.tsv`（`sha256 4a27b221bb2e374e97cfa775b782b31f8d099031c3049d403be9aaf725c829c2`）。
五个子命令（`kexts`/`surface`/`object`/`roots`/`adt`）都可独立跑，`RESULT PASS|FAIL (n)`，exit 0/1（解析错误 exit 2）。`adt` 的自证在 `scripts/usb27/test-adt-check.sh`（`sha256 8dbfaa96db03cdabfb4039bc61e56273277b24c1a6bbf8fd909095b6bc3d8f1e`），真 dtb 上的判别力在 `scripts/usb27/test-adt-real.sh`（`sha256 39615d281fe2b6babbc88ebbcc3fe915d26b182fd235b03c0c6ab72b773f5303`），构建请求在 `scripts/usb27/qdw3-build-request.py`（`sha256 1a1c452302ff8dd2a65eaebc9701d66915776e84d319a085a1747aae34d18c47`）。
以下命令都从 `E:/hackios/k60-usb27` 出发、在 WSL 里执行（`llvm-nm-18` 与 `python3` 只在 WSL 侧有）。

| # | 命令 | 期望输出 | 判据 |
| --- | --- | --- | --- |
| 1 | `python3 scripts/usb27/kc-surface.py kexts /mnt/e/k60-work/scratch/usb27/kernel-27-652237c6.macho --require-kext com.apple.driver.AppleUSBXDCI` | `filetype 0xc (MACH_FILESET)`、`kexts    31`、`FAIL kext com.apple.driver.AppleUSBXDCI`、`RESULT FAIL (1)` | 31 = 与 `LC_SUB_FILESET_ENTRY` 数（32 − 1 个 `com.apple.kernel`）一致；拿掉 `--require-kext` 应 `RESULT PASS`。这是「27 里没有 USB kext」的**机器判据** |
| 2 | `python3 scripts/usb27/kc-surface.py surface …/kernel-27-652237c6.macho --require-prefix AppleUSB --require-prefix IOService` | `symbols   64931 defined, 0 undefined`、`FAIL prefix 'AppleUSB': 0 defined`、`PASS prefix 'IOService': 1680 defined` | 前一行证明采集本身有效（`IOService` 能命中），后一行证明 `AppleUSB` 真为 0 —— 避免「脚本抓不到东西」被当成「没有」 |
| 3 | `python3 scripts/usb27/kc-surface.py object …/kernel-27-652237c6.macho /opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/…/k60_usblog.o --providers docs/research/eight-step/usb-27-providers.tsv` | `resolvable 27, missing 7`，逐行 `FAIL <sym>  <- <patch:line>`，`RESULT FAIL (7)` | 7 个行必须与 §2.2 表逐字一致；少一个（例如有人把 0235 带进 27）说明补丁面变了 |
| 4 | `python3 scripts/usb27/kc-surface.py roots /mnt/e/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml --require-kext com.apple.driver.AppleUSBXDCI` | `effective roots 31, usb/scsi roots 0`、`FAIL kext …`、`RESULT FAIL (1)` | 对照跑 sheng：加 `…/UniXNU-sheng/board.toml` 后 `effective roots 40, usb/scsi roots 11`、`RESULT PASS`。两个板子同 profile 同内核，差别只在 board 的 prelink 根 —— 这是「27 没有 USB 的直接原因」的**机器判据** |
| 5 | `python3 scripts/usb27/kc-surface.py adt /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/device-tree/hardware.dtb /mnt/e/hackios/k60-gates/board.toml --expect-base 0xa600000` | `dtb … (4307 bytes, 29 nodes)`、`usb nodes 0`、`adt.arm-io nodes 2: pong-buttons, pong-touch`、`usb arm-io nodes 0`、`info  the hardware device tree has no usb node; only a board [adt.arm-io] block can declare one`（DT 缺席本身**不算**失败，board 块可以单独声明）、`node  expected base 0xa600000 absent in the ADT inputs`、`REASON no usb node carries unixnu,adt-name and no [adt.arm-io] block declares one, so the ADT has no usb child`、`REASON expected base 0xa600000 is not declared by either input`、`RESULT FAIL (2)`、**exit 1** | 这是 Lead 要的那条 0/1 判据：「27 侧 USB 控制器是否在 ADT 里被声明」——**没有**。DT 侧读的是 payload 真正的 `hardware.dtb`（4,307 B），不是从 DT 源推断；board 侧读 `[adt.arm-io.*]` 的四个 kind 子表。exit 0 只在「DT 有 USB 节点且每个 reg 基址都被 `[adt.arm-io]` 声明」时出现 |
| 5b | `bash scripts/usb27/test-adt-check.sh` | 六条 `PASS`（见下）+ `RESULT PASS`、exit 0 | 判据的自证。只会在真实树上 FAIL 的脚本不算判据，所以每条正反例都跑：导出节点+board 块 → 0；**无 `unixnu,adt-name` 的 usb 节点对真 board → 1**；仅 board 块 → 0；同名双边 → 1；未声明基址 → 1；27 产物 → 1 |
| 5c | `bash scripts/usb27/test-adt-real.sh` | 六条 `PASS` + `RESULT PASS`、exit 0；INFO 行打印被检查 dtb 的 `sha256 59faef26…` | Lead 要的「真机 dtb 上跑出结论、对故意改坏的副本退非 0」。**副本全部由生产 dtb 用 `dtc` 派生**（不是另写一棵树）：生产 dtb → 1；board 块单独声明 → 0；导出节点 0xa600000 → 0；同一节点改 0xa700000 → 1；去掉 `unixnu,adt-name` → 1；同名双边 → 1。第 3 条是关键：证明它在**真 dtb 上**也能返回 0，不是只会 FAIL |

`adt` 的判定规则（脚本里写死，改它就要改这张表，也改这一节）：

1. **ADT 不是 DT**。内核拿到的是 `UniXNU/scripts/unixnu/devicetree.py:311-420` 的 `generate()`
   重新拼出来的 `/device-tree`：`cpus`/`psci`/`arm-io`/`chosen` + `defaults|options|product|buttons`。
   一个硬件节点只有在 DTS 里带 **`unixnu,adt-name`** 才会被导出成 `/device-tree/arm-io/<name>`
   （`devicetree.py:388-397`，`hardware = [entry for entry in entries if 'unixnu,adt-name' in entry.properties]`）。
   `[adt.arm-io.*]` 表则是 `platform_node(name, table)` 直接加进同一个 `arm-io`
   （`devicetree.py:393-396`），两边同名会在这里抛
   `Configured arm-io child duplicates an exported hardware node`（`devicetree.py:389`）。
2. 所以 `adt` 子命令只认两条路：DT 里命中 `usb|dwc3|eusb2|ssphy` **且**带 `unixnu,adt-name` 的节点，
   或 board 里命中同一组词的 `[adt.arm-io.<name>]` 块。两条都没有 ⇒ `REASON ... the ADT has no usb child`。
3. `reg` 按 2+2 或 1+1 cell 解基址；board 侧取 `.u64/.u32/.string` 里的 `0x…` 串与整数。
   `--expect-base` 要求该基址出现在任一条路的声明里（导出节点的 `reg` 或 board 数字），
   这样「有个 usb 节点但地址是别的窗口」也会被抓出来。

为什么这条判据仍然值得写：`[adt.arm-io.*]` 是 board 层交给板级驱动的参数表
（`E:/hackios/k60-gates/board.toml:229` 起的 `pong-touch`/`pong-buttons` 就是这种用法），
而 DT 导出是「硬件节点进内核」的唯一通道。27 现在**两条都没有**，且 DT 侧缺口能追到源：
`board.toml:53-55` 的 `[device_tree] source = "device:dts/mondrian.dts"` +
`include_dirs = ["soc:dts"]`，而 `dts/mondrian.dts`（235 行，`unixnu,adt-name` 6 处：
`pong-audio`/`wlan`/`bluetooth`/`ufshc` 等）与 `E:/hackios/UniXNU-sm8475-common/dts/sm8475.dtsi`
（79 行，1 处：`intc`）**都没有 usb 节点**（`grep -ci usb` = 0）⇒ 4,307 B 的 `hardware.dtb`
只有 29 个节点、0 个 USB，是源里就没有，不是产物丢节点。

对照组要说清两点，否则这条判据会被读偏：

- **sheng 也不是靠 `[adt.arm-io]` 起 USB 的**：`E:/hackios/UniXNU-sheng/board.toml` 里 `adt.arm-io`
  节点数是 **0**（同一条 `adt` 命令的 INFO 行可见），它的 USB 靠 `board.toml:25` 的 11 个
  prelink 根 + `QcomDwc3.cpp:40-41` 的硬编码窗口。所以 board 半边 FAIL **不能**单独证明
  「K60 有 sheng 没有的缺口」。
- **sheng 的 DT 半边拿不到**：`board.toml:107` 指 `build/sheng/sheng.dtb`，本机没有这个产物，
  它的 DT 源 `dts/sheng.dts` 只有 56 行且 `grep -ci usb` = 0，USB 节点来自被 include 的
  `soc:dts`（本机无对应 dtsi）。这一格记 **unmeasured**，不许写成「sheng 的 ADT 有 USB 节点」。

还有一处必须写明的限制：`payload.json` 的 `adt_sha256`（`899ea73a…`）**不等于**
`sha256(hardware.dtb)`（`59faef26e286b376e1ded968ac69eebaca44dac4c9e3c183ba99a3cdafa906a2`），
因为 ADT 是 `generate()` 的产物（`UniXNU/scripts/unixnu/payload.py:231-236`）。`adt` 子命令读的是
**输入**（DT 与 board 表），不是最终 ADT 二进制；结论只对「输入里有没有声明」成立，这一点写在
§7 第 7 条里。

对照组（16.6.1 内核）用来证明脚本不是只会说 FAIL：`kexts` 会报 `filetype 0x2 (MACH_EXECUTE)` +
`note no machine-readable __PRELINK_INFO`，`surface --require-symbol _k60_usblog_init --require-symbol _k60_usblog_start` 给 `RESULT PASS`（4.8 万符号里真有这两个）。

---

## 5. 方案（⑤）：改动清单与顺序

不是「USB 先做」，而是「先判 USB 能不能救当前 0 字节日志」：
27 的 console 在 `bsd_init` 之后才起，`code_signing_init()` 之后的 13 项静默失败发生在它前面，
所以 **USB 通道救不了当前的 0 字节故障**，它的价值是 `bsd_init` 之后的所有飞行取证。
下面的顺序按「先拿到通道、再谈配对」排。

| # | 改动文件 | 依据 | 预期 | 谁能做 |
| --- | --- | --- | --- | --- |
| 1 | `board.toml` 加 `["kernel"."prelink"]` 的 `roots`（sheng 的 11 条 USB 根，按需加 `!AppleOnboardSerial`/`!AppleSMC` 排除） | usb.md:70；`UniXNU-sheng/board.toml:25`；§2.3 第 1 行 | prelink 报告里出现 11 个 USB kext；`kc-surface.py kexts --require-kext com.apple.driver.AppleUSBXDCI` 转 PASS | Lead（board 是他的树，我只出草案） |
| 2 | `board.toml` 的 `components.include` 加 `QcomDwc3` | `components.toml:513-528`（revision `e4efe95c`，`os_abi=["ipados-27.0.1-24A446"]`）；§2.3 第 2 行 | 组件目录落到 `drivers/QcomDwc3`，`QcomDwc3Xdci/Xhci` 进链接 | Lead |
| 3 | `QcomDwc3.cpp:42` `kSid = 0x40` → K60 的 `0x0`；`kIrq = 133+32=165` 按 K60 核实 | `OFFICIAL-DRIVER-MAP.md:464`（K60 stream 0x0，sheng 0x40）；usb.md:21-37（GIC 165） | `smmuIdentity()` 的 SMR/S2CR 命中本板 stream，stage 5 不再失败 | 我出补丁草案，Lead 构建 |
| 4 | `gen-usb27-abi.py` 重跑 → `usb-xdci-24A446.json` / 按 `build-gop-legacy-display-27.py:550-589` 生成 `OriginalUsbXdciABI.h` | usb.md:72-74 | `static_assert(sizeof(AppleUSBXDCI)==instance_size)` 过 | **阻塞：需要 24A446 kernelcache**（本机只有 20G81/21H461） |
| 5 | 启动参数加 `sheng-usb=1`（官方路由）或 `k60_usblog=2`（自写 gadget 路由） | usb.md:62；`E:/hackios/k60-gates/board.toml:173-174` | 控制器线程真的跑起来；`native_usb_stats[0]` 由 0 变正 | Lead |
| 6 | 自写 gadget 路由：`bsd/dev/k60_usblog.c` + `bsd/conf/files` 一行 + `patches/xnu/{0300,0307,0308}` + `patches/usb/0405-0411` + 诊断五补丁（`0235/0238/0331/0337/0334b/0306`） | §2.2 表；§2.4 第 2 行 | `kc-surface.py object` 的 `missing` 从 7 变 0 | 我出移植草案，Lead 构建 |
| 7 | **不修 ADT 也能推进**：`QcomDwc3` 路线不需要 ADT 节点（全文 0 处 `IODT*`），所以这一项只在「要让读 DT 的消费者看见控制器」时才做。要做则二选一（不要同时做，`devicetree.py:389` 会抛重名）：(a) 在 `E:/hackios/UniXNU-sm8475-common/dts/sm8475.dtsi` 或 board 的 `dts/mondrian.dts` 里加 `usb@a600000` 节点并写 `unixnu,adt-name = "usb0"`（只加节点不加该属性不会进 ADT，`devicetree.py:388`）；(b) 或只在 board.toml 加 `[adt.arm-io.pong-usb.u64] dwc-base="0xa600000"` | `RESEARCH.md:81`（DWC3 0xa600000/size 0xd93c）、`OFFICIAL-DRIVER-MAP.md:464`；判据 5/5b 给出「改完怎么算过」 | `kc-surface.py adt` 从 `RESULT FAIL (3)` 变 `RESULT PASS` | **需要 owner 同意**（`UniXNU-sm8475-common` 是共享组件树、`dts/mondrian.dts` 在 k60-gates，两者都不在我的写权限内）；对 QcomDwc3 路线**非必需**（`QcomDwc3.cpp` 全文 0 处 `IODT*` 调用），只对「读 DT 的消费者」有意义 |

顺序建议：**先 1+2（不改代码、只开花名册）**拿到「USB kext 是否真进 27 产物」的判据；
再 3+5 试官方栈能不能起来；4 一旦拿到 kernelcache 就必须做，否则 XDCI 子类无法实例化；
6 只在「官方栈确实没有 CDC 数据类驱动」时启动（未定项 3）。

---

## 6. 核验（⑦）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 静态对照 | 官方 usb.md 的六节 ↔ §3 的 27 接入点表 ↔ §2 的导出面表 | 逐节有引；`AppleUSB` 0、`native_usb_stats` 0、`QcomDwc3` 0 三处一致 |
| 离线单测（官方） | `bash scripts/usb27/ucsi-host-test.sh`（内部：`git archive e4efe95c \| tar -x` 到临时目录；`clang++ -std=c++17 -I.. ucsi_host.cpp && ./ucsi_host`） | **`PASS` / `RESULT PASS`，exit 0**（宿主侧，不构建内核）。测试用一个端口管理器模型跑 `ucsi_start`/`ucsi_receive`：断言 `u.partner == kUcsiPartnerDfp`、版本 `0x0110`/`0x0200` 两档 buffer、变更通知的 ack 顺序 |
| 产物检查 | §4 的五条命令 | 依次 `RESULT FAIL (1)` / `FAIL prefix 'AppleUSB': 0` + `PASS IOService 1680` / `resolvable 27, missing 7` / K60 `usb/scsi roots 0` vs sheng `11` / `adt` 三条 `REASON` 且 **exit 1** |
| 判据自证（Lead 要求 ⑦ 可跑） | `bash scripts/usb27/test-adt-check.sh` | 六条全 `PASS`：导出节点+board 块 → 0、无 `unixnu,adt-name` 的 usb 节点×真 board → 1、仅 board 块 → 0、同名双边 → 1、未声明基址（QMP 0x88e8000）→ 1、真 27 产物 → 1；`RESULT PASS` |
| 判据自证（真 dtb 判别力） | `bash scripts/usb27/test-adt-real.sh` | 六条全 `PASS`，全部副本由**生产 dtb** 用 `dtc` 派生：生产 dtb → 1（两条 `REASON`）、board 块 → 0、导出节点 0xa600000 → 0、同一节点改到 0xa700000 → 1、去掉 `unixnu,adt-name` → 1、同名双边 → 1；`RESULT PASS` |
| 请求文书自证（不构建） | `python3 scripts/usb27/qdw3-build-request.py check --object <16.6.1 k60_usblog.o>` | `missing from the kernel 7` / `known 16.6.1 diagnostics 7`（逐个带补丁行号）/ `other 0` / `RESULT PASS`，exit 0 —— 分类器本身可跑，缺的只是 27 侧的 `QcomDwc3.o` |
| `local_verified` | 以上三项都只证明「27 产物里没有 USB 面」「驱动源自身自洽」「ADT 里没有声明」 | **仍为 false**：没有任何一项证明 K60 上 USB 能出字，那需要上机（⑧，见 §9） |

---

## 7. 未定项（unknown + 什么证据能定它）


1. **`QcomDwc3.cpp` 在 27 上还缺哪些符号** —— 未定，但「怎么问」已经是文书：`scripts/usb27/qdw3-build-request.py plan` 从 27 自己的编译 recipe 拼出精确命令（§10），`check` 按「内核缺的符号逐名列 + 三分桶」判。它为 0 的证明（对 16.6.1 的 `k60_usblog.o` 跑 `check` → `missing 7 / known 7 / other 0 / RESULT PASS`）已在 §6。证据：Lead 排一次构建后跑 `plan --abi <已生成头目录>` 再 `run`，`other` 桶必须为空。
2. **24A446 的 ABI 槽位（280/168）是否与 sheng 的 JSON 一致** —— 本机无 `24A446/kernelcache.decompressed`（只有 20G81/21H461）。证据：Lead 提供 24A446 ipsw 的 kernelcache 后跑 `gen-usb27-abi.py`，比对生成的 `usb-xdci-24A446.json` 与 sheng 的差异。**需要 Lead 给这个文件。**
3. **27 的 Apple 栈里有没有 CDC-ACM 数据类驱动**（`AppleUSBCDCACMData` 之类）—— 24A446 kernelcache 不可得 ⇒ 未定。这决定「官方栈能不能当控制台」，还是必须搬 `k60_usblog.c`。证据：拿到 kernelcache 后对 11 个根做 `kexts` 闭包，看是否含 CDC 类。
4. **K60 的 eUSB2 参考时钟是否走 TCSR**（FSEL 38.4 MHz）—— 本地只有 sheng 的 DT 与 K60 的 phy 节点，没取到 `tcsr` 属性。证据：完整 K60 Android DT（22k 行版本，`mondrian.dts:16856-16905` 区间）或 16.6.1 实测 TCSR 读取值。
5. **UCSI 在 K60 上是否从 `charger_pd` 回答** —— 未取证。证据：上机日志里 `qcom_ucsi_receive` 计数；无回答时按 usb.md:93 走 device，对控制台可接受。
6. **prelink 根的闭包会不会拖进 `AppleOnboardSerial`/`AppleSMC` 冲突** —— sheng 用两条 `!` 排除（`UniXNU-sheng/board.toml:25`），K60 是否需要同样的排除要等真机。证据：加根后 prelink 报告里两边是否同时存在。
7. **27 里到底有没有消费者读 USB 的 ADT 节点** —— 已知 `QcomDwc3.cpp` 全文 0 处 `IODT*`（它自建 nub + 硬编码窗口，`QcomDwc3.cpp:846-881`），所以 ADT 缺口对这条路线不是阻塞项；Apple 的 `AppleUSBXDCI`/`AppleUSBXHCI` 是否在 `start()` 里找 `/arm-io` 子节点 **未定**（它们在我们产物里不是 kext）。证据：拿到 24A446 kernelcache 后对这两个 kext 做 `strings | grep -c IODTFindMatchingEntries` 与 `nm` 反查，或上机后看 `ioreg -p IODeviceTree` 里 USB 节点缺失时 XDCI 的 `probe` 返回什么。
7b. **`adt` 子命令读的是输入，不是最终 ADT 二进制** —— 它检查 `hardware.dtb` 的 `unixnu,adt-name` 与 board `[adt.arm-io]`，而内核实际拿到的是 `generate()` 的产物（`payload.json` 的 `adt_sha256 899ea73a…` ≠ `sha256(hardware.dtb) 59faef26…`）。「输入里没有 ⇒ ADT 里没有」这一推理成立，因为 `generate()` 只会加节点不会凭空造 usb 子节点（`devicetree.py:388-397`）；反过来「输入里有 ⇒ ADT 里一定有」**没有验证**（取决于 `hardware_properties`/`platform_node` 的过滤）。证据：在一次允许的构建后对 `payload/kernel.macho.adt` 直接跑同一套 FDT 遍历（脚本已有 `fdt_nodes()`，只差一个 `--adt` 入口），或导出 payload.img 里的 ADT 段比对。
8. **ADT 判据的 board 半边是不是本板特有** —— sheng 的 `[adt.arm-io]` 节点数是 0，`build/sheng/sheng.dtb` 本机不存在，所以「sheng 的 DT 有 USB 节点」这半句**未测**。证据：在 sheng 树上构建一次 payload 后对 `build/sheng/sheng.dtb` 跑同一条 `adt` 命令（我没有构建权限），或拿 sheng 的 `kernel.macho.adt` 直接遍历 `arm-io` 子节点名。

## 8. 参考源判定（iron-16）

| 源 | 读数 | 判定 |
| --- | --- | --- |
| `E:/hackios/UniXNU/docs/zh/porting/usb.md` | :41-58 九阶段与 stage 预期、:70 prelink 根、:78-79 两处覆盖、:87-93 角色表 | **adapted**：作为 27 接入点的官方依据原文引用，未改一字 |
| `UniXNU/QcomDwc3` `e4efe95c` | `QcomDwc3.cpp:40-41,208,216,307-343,576-604,609-640,790-815`、`QcomEusb2Phy.h:12-17`、`QcomQmpUsb3.h:1-6`、`QcomUcsi.h:22-129` | **copied**（只读引用行号，GPL-2.0-only，未复制代码进本仓） |
| `E:/hackios/UniXNU-sheng` | `board.toml:25` 11 个 USB 根 + 2 条排除；`package/ShengBattery.cpp:31-34,75,79,214,235-236`；`scripts/build-gop-legacy-display-27.py:550-589` | **adapted**：作为 24A446 同版本的可用先例，参数要按 K60 换（stream 0x0、board-id/security-domain、chip-id） |
| `E:/hackios/k60-usb` 16.6.1 树 | `docs/research/usb/RESEARCH.md:56,67,81,83,109,113,273`、`08-on-device.md` | **rejected for 27 as-is**：自写 gadget 路线在 27 缺 7 个符号与全部源文件，且 27 的 console 已是屏幕面板 |
| `patches/xnu/*`（16.6.1 序列） | 2.2 表里 7 个符号的定义行 | **rejected**（27 的 104 条补丁里没有它们）；要复用需逐条重做，见 §2.3 |
| `drivers/community-native-dwc3.md`（Lux12138/NativeDwc3，SM8150 nabu） | 无真机结果、不接管维护 | **rejected**：无 24A446 证据 |
| `virtio-mmio-console.md` | split queue 控制台 | **rejected**：与 USB 无关，只在「没有 USB 时怎么取证」的备选里提过 |

---

## 9. ⑧ 上机判据（只写判据，不上机）

上机由 Lead 调度；本节只回答「跑完之后用什么判、判不出来时怎么把它标成 INVALID」。
每条都带 `unmeasured`：写明这条即使过了，也**仍然没有测到**什么。没有串口的板子上，
「没看到」和「坏了」是两件事，所以每条都单独给 INVALID 条件。

### 9.1 prediction（改动前先写死，改完只用它判）

对 §5 的 (1)(2)(3)(5)（prelink 根 + QcomDwc3 组件 + stream 0x0/IRQ 165 + `sheng-usb=1`），
预期按顺序出现：`native_usb_stats[0] = 9` → `native_usb_stats[1] = 0x33313130`
（GSNPSID，`RESEARCH.md:56`；白名单 0x5533/0x5534/0x3331 见 `QcomDwc3.cpp:602`）→
`native_usb_stats[19] = 1`（XDCI `start` 返回）→ stage 12 → 主机侧枚举出设备。
**任一环缺席都算预测失败**，不得把后面的通过当成前面的证据。

### 9.2 判据表

| # | 要观察到什么 | 怎么观察（无串口） | 期望 | 判 INVALID（证据不足，不是 FAIL） | unmeasured |
| --- | --- | --- | --- | --- | --- |
| D1 | 产物里真的有 USB 面 | 离线：§4 的 1–4 条（不用上机） | `kexts --require-kext com.apple.driver.AppleUSBXDCI` 转 PASS、`roots` 里 usb/scsi 从 0 变 11 | **不适用**（离线可判） | 产物里有 kext ≠ 运行时被实例化；这一步过了也说明不了控制器起来了 |
| D2 | 控制器 bring-up 到 stage 9 | 面板 console（`0543-k60-ios27-panel-console.patch`）里打 `usb stage=`；**当前 0543 没有这一行**，要用就得先加打印 | `stage=9`、core id `0x33313130` | 面板上既没有 `usb stage=` 也没有任何新行，且主机 30 s 内无枚举 ⇒ 连「内核跑到哪」都不知道，判 INVALID | 面板 console 是否覆盖到 USB 线程启动的那个时刻（bsd_init 之后）——没有实测过 |
| D3 | 失败时能定位到哪一阶段 | 同上，读负值：`-1` 映射/`-2` 电源轨/`-3` GDSC/`-4` 时钟复位/`-5` SMMU/`-6` 中继器/`-7` PHY/`-8` core id/`-9` 之后（`QcomDwc3.cpp:576-604`） | 负值能对上表里某一行 | 读到负值但面板行被截断、只剩前 40 字符 ⇒ 判 INVALID，重跑一次并加长缓冲 | 每个阶段在 K60 上的具体寄存器读数（无串口时只能看到阶段号，看不到值） |
| D4 | USB2 高速链路（eUSB2 FSEL 38.4 MHz） | Mac：`ioreg -p IOUSB -l -w0 \| grep -E 'idVendor\|idProduct\|Device Speed'`（usb.md:113-118） | 出现 `0x1209/0x0001`（自写 gadget）或 Apple 的默认 ID，`Device Speed = 3`（high） | 主机侧 `ioreg` 里 30 s 无任何新节点，且 D2 也没读到 stage ⇒ INVALID（先修取证通道） | K60 的 eUSB2 `tcsr` 属性（§7 第 4 条），所以 FSEL 是否真被写成 38.4 未测 |
| D5 | SuperSpeed（QMP + retimer） | 同上，看 `Device Speed = 4` | 4（10 Gbps 线） | 只有 3 没有 4 ⇒ 不是 INVALID，是「QMP/retimer 没通」，可按 usb.md:60 回退 UTMI | K60 的 USB3 通道（fsa4480/Type-C 方向）从未取证；`maximum-speed=high-speed`（`FEATURES-DRIVERS-RESEARCH-2026-10-31.md:81`）说明这条本来就不是控制台的前提 |
| D6 | 线缆角色切换（UCSI） | 换一条线/一个优盘重跑，`sheng-usb-host=1` 强制宿主 | host 模式下 `ioreg -p IOUSB` 出现优盘；device 模式出现 D4 的节点 | UCSI 无回答时按 usb.md:93 跑 device —— 这是**预期分支**，不算 INVALID | K60 是否从 `charger_pd` 拿到线缆对端（§7 第 5 条）；`qcom_ucsi_receive` 的计数没有可读出口 |
| D7 | 配对/lockdown | Mac 上的信任弹窗与 `UserDeniedPairing` 文案（usb.md:104-107 的失败表） | 弹窗出现、信任后能读设备 | 枚举成功但没有任何弹窗、也没有 `UserDeniedPairing` ⇒ 判 INVALID（配对路径没走到） | `/System` 的 fsid 与锁状态在 27 stage-0 上是否可写（当前进不了 SpringBoard） |
| D8 | **CDC 控制台能不能出字**（这条线真正的目的） | 主机侧出现 tty 后写 64 字节回环，读回 64 字节（16.6.1 的 c 格判据，`k60-usb/docs/research/usb/08-on-device.md`） | `sent=64 received=64` | 枚举成功、tty 存在，但 60 s 内零字节 ⇒ 这是**判 FAIL**（官方栈缺 CDC 数据类驱动），不是 INVALID；据此才启动 §5 第 6 项 | 27 的 Apple 栈里到底有没有 CDC-ACM 数据类驱动（§7 第 3 条，要 24A446 kernelcache） |

### 9.3 无串口时的通用 INVALID 规则

一次上机只有在下面四条同时成立时才可以下结论，缺一条就记 INVALID 并重跑，不许写成 FAIL：

1. boot claim 有记录（谁、什么时间、哪个 payload sha256）；
2. `payload.json` 的 `kernel_sha256` 与预期镜像一致（当前 `652237c6…`），不一致 ⇒ 判的是别的镜像；
3. 主机侧观察窗口 ≥ 30 s（DWC3 枚举在 `bsd_init` 之后，冷启动可能更慢）；
4. 面板 console 至少有一行新输出（证明内核走到了 console worker）。第 4 条不成立时，
   一切「主机没看到设备」都不算 USB 的证据 —— 这正是 2026-11 那几次 0 字节日志的教训。



---

## 10. 构建请求（⑦ 的第二件离线活）

Lead 2026-11-21 裁决：stage-0 冻结期不批准任何对象级构建（会改共享装配树，他要拿同一棵树
复现诊断镜像），所以「`QcomDwc3.cpp` 编进 BCM2837 obj 后还缺哪些符号」这一问**只能以请求形式交付**。
文书由 `scripts/usb27/qdw3-build-request.py` 生成，三个模式分工明确：`plan` 只算不编（写 `REQUEST.md`
与 `QcomDwc3.command.json`）、`run` 要一次显式构建后才用（`subprocess` 调 `clang-24`）、`check` 只读对象与内核。

### 10.1 命令行从哪来（不是手抄）

Sheng 在 iOS 27 上编译这个组件时并不手写旗标，它读 XNU 自己写下的编译 recipe
（`E:/hackios/UniXNU/scripts/build-sheng-source-drivers.py:97-99` 的做法）。同一条 recipe 在 27 装配树里是：

```
/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/
  DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json
```

`sha256 a3913117988814834af4705b79b4e5813c29a2084dfe86625aa9f3541d3b37dd`，540 个参数：
`arguments[0]` 是 `/opt/unixnu-linux/llvm/bin/clang-24`，开头固定
`-xc++ <src> -o <out> --target=arm64e-apple-ios27.0 -c`，然后 `-std=gnu++2b`、`-arch arm64e`、
`-mkernel`、`-fapple-kext`、`-fno-builtin`、`-fno-common`、`-D KERNEL_PRIVATE`、`-D XNU_KERNEL_PRIVATE`、
`-D IOKIT_KERNEL_PRIVATE`（`-D` 与宏名是两个 token，抄错会变成 `-DKERNEL_PRIVATE` 之外的形态）、
`-D VM_KERNEL_LINK_ADDRESS=0xfffffff007004000`、`-D ARM64_BOARD_CONFIG_BCM2837`、
`-D CURRENT_MACHINE_CONFIG_LC=bcm2837`、16 个 `-I` 根（`EXPORT_HDRS/{iokit,osfmk,bsd,libkern,pexpert,libsa,security,san}`、
`.cache/xnu-work/EXTERNAL_HEADERS`、`.cache/fakeroot/usr/local/include{/kernel,/iBoot}`）、86 个 `-W`，
没有 `-MD/-MF`（不产生依赖文件，所以对象就是唯一产物）。

`plan` 做的事只有两件：把 recipe 里的源文件与 `-o` 换成 `QcomDwc3.cpp` / `QcomDwc3.o`，
再追加三个 include 根 `-I <abi> -I <component> -I <package>`（与 sheng 的
`usb_flags = ('-I', USB_OUT, '-I', USB, '-I', KITS)`，`build-gop-legacy-display-27.py:636-638` 同形）。

### 10.2 三个 include 根各是什么

| 根 | 内容 | 本机状态 |
| --- | --- | --- |
| component | `QcomDwc3.cpp`、`QcomEusb2Phy.h`、`QcomQmpUsb3.h`、`QcomUcsi.h`（catalog 钉 `e4efe95c`） | 有：`/mnt/e/k60-work/scratch/usb27/refs-QcomDwc3`（HEAD `f5edd26d`，`git archive e4efe95c` 可取到钉住版本） |
| package | `GeniI2c.h`、`QcomRpmh.h`、`AppsSmmuLock.h` | 有：`E:/hackios/UniXNU-sheng/package/` |
| abi | `OriginalUsbXdciABI.h`、`OriginalUsbXhciABI.h` | **缺**：由 `build-gop-legacy-display-27.py:551-589`（XDCI）与 :600-625（XHCI）从 `usb-xdci-24A446.json`(23,224 B)/`usb-xhci-24A446.json`(28,994 B) 现生成，本机全盘没有这两个头 |

所以 `plan` 现在**如实报缺**：`MISSING … OriginalUsbXdciABI.h`、`MISSING … OriginalUsbXhciABI.h`、
`RESULT FAIL (preconditions)`、exit 1。这不是失败，是请求的前置条件被写成可检查的一行 ——
ABI 头的生成不需要内核构建，只要那两个 JSON（`gen-usb27-abi.py` 只需 ipsw 的 kernelcache，
本机缺 24A446 那份，见 §7 第 2 条）。

### 10.3 请求正文（给 Lead 的四行）

1. **要编什么**：`<component>/QcomDwc3.cpp` → `build/usb27/qcom-dwc3/QcomDwc3.o`（`/build/` 已 gitignore）。
2. **怎么编**：`python3 scripts/usb27/qdw3-build-request.py plan` 生成的 `QcomDwc3.command.json`
   就是完整的 argv（可直接 `json` 喂给 `subprocess`），`run` 模式只是 `plan` + 执行 + `check`。
   前置：把两个 ABI 头放进 `--abi`（默认 `build/usb27/abi`）。
3. **看什么**：`check` 打印 `missing from the kernel <n>`，逐行列出**每个**缺失符号名，
   再分三桶：`family ABI`（`AppleUSBXDCI`/`AppleUSBXHCI` 的 vtable/typeinfo，说明 ABI 面不匹配）、
   `known …`（`usb-27-providers.tsv` 里查到的 16.6.1 专有符号，带补丁行号）、`other`（**必须为空**）。
4. **判据**：`RESULT PASS` = `other 0`。`other` 非空就是「27 上没有提供者的符号」，
   每一行都是一个必须回答的移植问题；`family ABI` 非空说明 §7 第 2 条（ABI 槽位）没解决。

### 10.4 判据本身已被自证（不用等构建）

对 16.6.1 的 `k60_usblog.o` 跑同一条 `check` 就是完整的分桶演示：34 个 undefined 里
`missing from the kernel 7`、`known 16.6.1 diagnostics 7`（`_k60_checkin_compat`、`_k60_exec_count`、
`_k60_exit_count`、`_k60_prevlog_dump`、`_PE_k60_reset_now`、`_pong_ramoops_debug_base`、
`_pong_ramoops_snapshot`，每个带补丁名与行号）、`other 0`、`RESULT PASS`。
第一次跑时这 7 个全落进 `other`（把前导 `_` 剥掉后查表失败），修法是先按原名查再按去掉下划线的名字查 ——
这条修正本身就是「分类器会骗人」的例子，所以 `other 0` 这个判据是跑出来的，不是声明出来的。

---

## 复现全部数字的最短路径（不构建、不动设备）

```sh
# WSL 内，工作目录 E:/hackios/k60-usb27
K27=/mnt/e/k60-work/scratch/usb27/kernel-27-652237c6.macho
python3 scripts/usb27/kc-surface.py kexts  $K27 | tail -3
python3 scripts/usb27/kc-surface.py surface $K27 --require-prefix AppleUSB --require-prefix IOService
python3 scripts/usb27/kc-surface.py roots /mnt/e/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml \
  --require-kext com.apple.driver.AppleUSBXDCI
# 判据 5（ADT 0/1）与它的自证
python3 scripts/usb27/kc-surface.py adt \
  /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/device-tree/hardware.dtb \
  /mnt/e/hackios/k60-gates/board.toml --expect-base 0xa600000
bash scripts/usb27/test-adt-check.sh
bash scripts/usb27/test-adt-real.sh            # 真 dtb 判别力（六条）
# ⑦ 第二件：构建请求（只算不编；现在因缺两个 ABI 头而 FAIL(preconditions)，这是设计）
python3 scripts/usb27/qdw3-build-request.py plan
# 判据自证：拿 16.6.1 的对象证明分桶器可跑（missing 7 / known 7 / other 0 / RESULT PASS）
python3 scripts/usb27/qdw3-build-request.py check --object \
  /opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/bsd/DEVELOPMENT/k60_usblog.o
```

`plan` 与 `check --object` 都不写共享树：前者只写 `build/`（gitignored），后者只读。
