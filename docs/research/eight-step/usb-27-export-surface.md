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

脚本：`scripts/usb27/kc-surface.py`（只读，不构建；`sha256 5592fdc50c26dd1ed3c49a9d291b02d8a800410845d2c2c9a626489efb69b00a`）。
数据：`docs/research/eight-step/usb-27-providers.tsv`（`sha256 4a27b221bb2e374e97cfa775b782b31f8d099031c3049d403be9aaf725c829c2`）。
四个子命令都可独立跑，`RESULT PASS|FAIL (n)`，exit 0/1（解析错误 exit 2）。
以下命令都从 `E:/hackios/k60-usb27` 出发、在 WSL 里执行（`llvm-nm-18` 与 `python3` 只在 WSL 侧有）。

| # | 命令 | 期望输出 | 判据 |
| --- | --- | --- | --- |
| 1 | `python3 scripts/usb27/kc-surface.py kexts /mnt/e/k60-work/scratch/usb27/kernel-27-652237c6.macho --require-kext com.apple.driver.AppleUSBXDCI` | `filetype 0xc (MACH_FILESET)`、`kexts    31`、`FAIL kext com.apple.driver.AppleUSBXDCI`、`RESULT FAIL (1)` | 31 = 与 `LC_SUB_FILESET_ENTRY` 数（32 − 1 个 `com.apple.kernel`）一致；拿掉 `--require-kext` 应 `RESULT PASS`。这是「27 里没有 USB kext」的**机器判据** |
| 2 | `python3 scripts/usb27/kc-surface.py surface …/kernel-27-652237c6.macho --require-prefix AppleUSB --require-prefix IOService` | `symbols   64931 defined, 0 undefined`、`FAIL prefix 'AppleUSB': 0 defined`、`PASS prefix 'IOService': 1680 defined` | 前一行证明采集本身有效（`IOService` 能命中），后一行证明 `AppleUSB` 真为 0 —— 避免「脚本抓不到东西」被当成「没有」 |
| 3 | `python3 scripts/usb27/kc-surface.py object …/kernel-27-652237c6.macho /opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/…/k60_usblog.o --providers docs/research/eight-step/usb-27-providers.tsv` | `resolvable 27, missing 7`，逐行 `FAIL <sym>  <- <patch:line>`，`RESULT FAIL (7)` | 7 个行必须与 §2.2 表逐字一致；少一个（例如有人把 0235 带进 27）说明补丁面变了 |
| 4 | `python3 scripts/usb27/kc-surface.py roots /mnt/e/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml --require-kext com.apple.driver.AppleUSBXDCI` | `effective roots 31, usb/scsi roots 0`、`FAIL kext …`、`RESULT FAIL (1)` | 对照跑 sheng：加 `…/UniXNU-sheng/board.toml` 后 `effective roots 40, usb/scsi roots 11`、`RESULT PASS`。两个板子同 profile 同内核，差别只在 board 的 prelink 根 —— 这是「27 没有 USB 的直接原因」的**机器判据** |

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

顺序建议：**先 1+2（不改代码、只开花名册）**拿到「USB kext 是否真进 27 产物」的判据；
再 3+5 试官方栈能不能起来；4 一旦拿到 kernelcache 就必须做，否则 XDCI 子类无法实例化；
6 只在「官方栈确实没有 CDC 数据类驱动」时启动（未定项 3）。

---

## 6. 核验（⑦）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 静态对照 | 官方 usb.md 的六节 ↔ §3 的 27 接入点表 ↔ §2 的导出面表 | 逐节有引；`AppleUSB` 0、`native_usb_stats` 0、`QcomDwc3` 0 三处一致 |
| 离线单测（官方） | `bash scripts/usb27/ucsi-host-test.sh`（内部：`git archive e4efe95c \| tar -x` 到临时目录；`clang++ -std=c++17 -I.. ucsi_host.cpp && ./ucsi_host`） | **`PASS` / `RESULT PASS`，exit 0**（宿主侧，不构建内核）。测试用一个端口管理器模型跑 `ucsi_start`/`ucsi_receive`：断言 `u.partner == kUcsiPartnerDfp`、版本 `0x0110`/`0x0200` 两档 buffer、变更通知的 ack 顺序 |
| 产物检查 | §4 的四条命令 | 依次 `RESULT FAIL (1)` / `FAIL prefix 'AppleUSB': 0` + `PASS IOService 1680` / `resolvable 27, missing 7` / K60 `usb/scsi roots 0` vs sheng `11` |
| `local_verified` | 以上三项都只证明「27 产物里没有 USB 面」「驱动源自身自洽」 | **仍为 false**：没有任何一项证明 K60 上 USB 能出字，那需要上机（⑧） |

---

## 7. 未定项（unknown + 什么证据能定它）


1. **`QcomDwc3.cpp` 在 27 上还缺哪些符号** —— 无 27 编译产物，禁构建 ⇒ 未定。证据：一次允许的构建后跑命令 3（`kc-surface.py object` 换 `QcomDwc3.o`）。
2. **24A446 的 ABI 槽位（280/168）是否与 sheng 的 JSON 一致** —— 本机无 `24A446/kernelcache.decompressed`（只有 20G81/21H461）。证据：Lead 提供 24A446 ipsw 的 kernelcache 后跑 `gen-usb27-abi.py`，比对生成的 `usb-xdci-24A446.json` 与 sheng 的差异。**需要 Lead 给这个文件。**
3. **27 的 Apple 栈里有没有 CDC-ACM 数据类驱动**（`AppleUSBCDCACMData` 之类）—— 24A446 kernelcache 不可得 ⇒ 未定。这决定「官方栈能不能当控制台」，还是必须搬 `k60_usblog.c`。证据：拿到 kernelcache 后对 11 个根做 `kexts` 闭包，看是否含 CDC 类。
4. **K60 的 eUSB2 参考时钟是否走 TCSR**（FSEL 38.4 MHz）—— 本地只有 sheng 的 DT 与 K60 的 phy 节点，没取到 `tcsr` 属性。证据：完整 K60 Android DT（22k 行版本，`mondrian.dts:16856-16905` 区间）或 16.6.1 实测 TCSR 读取值。
5. **UCSI 在 K60 上是否从 `charger_pd` 回答** —— 未取证。证据：上机日志里 `qcom_ucsi_receive` 计数；无回答时按 usb.md:93 走 device，对控制台可接受。
6. **prelink 根的闭包会不会拖进 `AppleOnboardSerial`/`AppleSMC` 冲突** —— sheng 用两条 `!` 排除（`UniXNU-sheng/board.toml:25`），K60 是否需要同样的排除要等真机。证据：加根后 prelink 报告里两边是否同时存在。

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

复现全部数字的最短路径（不构建、不动设备）：

```sh
# WSL 内，工作目录 E:/hackios/k60-usb27
K27=/mnt/e/k60-work/scratch/usb27/kernel-27-652237c6.macho
python3 scripts/usb27/kc-surface.py kexts  $K27 | tail -3
python3 scripts/usb27/kc-surface.py surface $K27 --require-prefix AppleUSB --require-prefix IOService
python3 scripts/usb27/kc-surface.py roots /mnt/e/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml \
  --require-kext com.apple.driver.AppleUSBXDCI
```
