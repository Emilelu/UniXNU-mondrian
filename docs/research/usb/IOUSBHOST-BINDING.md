# IOUSBHost 绑定路径（只读调研）

> 调研对象：K60（Redmi K60 / mondrian / SM8475）UniXNU+iOS 移植仓库 `E:\hackios\k60-usb`（WSL `/mnt/e/hackios/k60-usb`）。
> 本文只读产出，未构建、未刷机、未修改任何既有文件。
> 路径约定：**仓库内**文件用相对路径（相对仓库根）；**仓库外**用绝对路径。构建产物在 WSL 内，路径前缀 `/opt/k60/trees/k60build`。
> 关键产物：
> * 本仓内核（prelink 后）：`/opt/k60/trees/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho`（53952512 B）
> * 同目录 `kernel/kernel.json`（15792745 B，components 30 个）
> * Apple 原版：`/opt/k60/trees/k60build/out/ipsw/20G81/kernelcache.decompressed`（48644096 B）
> * XNU 源码副本：`/opt/k60/trees/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`
> * 交给 ADT 生成器的硬件 DT：`/opt/k60/trees/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb`（1866 B）

---

## 0. 一句话结论

**本仓内核（kernel.macho）里一个 USB kext 都没有**；Apple 的 USB 栈在 20G81 原版 kernelcache 里齐全，但绑定分两条互不相通的路：**设备模式**走 `AppleUSBXDCI`（该 kext **没有 IOKitPersonalities**，必须由厂商 subclass 自己 load 并发布 `IOUSBDeviceController`，这正是 sheng 的 UsbProbe.cpp 第 22 行做的事），**主机模式**走 `AppleEmbeddedUSBNub`（`IONameMatch = "usb-xhci,t8011"`），而这个 nub 在本仓**没有任何生产者**（hardware.dtb 里只有 cpus / psci / gic / memory / ufs，无 usb 节点）。所以「让 Apple 栈驱动 K60 的 DWC3」= 设备模式可行但要做三件事（USB kext 进 prelink roots、为 20G81 重做 ABI、写 AppleUSBXDCI subclass）；主机模式还额外缺一个不能靠加配置补上的东西：`AppleEmbeddedUSBNub`。

---

## 1. 本仓内核里实际存在的 USB kext

### 1.1 结论表

| identifier（题目点名） | 20G81 原版 kernelcache | 本仓 kernel.macho | 证据（`strings -a <file> \| grep -c -x <id>`，kc / macho） |
|---|---|---|---|
| `com.apple.driver.AppleUSBXDCI` | 有 | **无** | `AppleUSBXDCI` 1 / 0 |
| `com.apple.iokit.IOUSBDeviceFamily` | 有 | **无** | `IOUSBDeviceFamily` kc 命中于 `com.apple.iokit.IOUSBDeviceFamily` 字符串；macho 版整串 0 |
| `com.apple.driver.AppleUSBDeviceMux` | 有 | **无** | 该 id 在 kc 的 34 个 USB kext 列表内；macho `strings\|grep -c -x AppleUSBDeviceMux` = 0 |
| `com.apple.driver.AppleUSBDeviceNCM` | 有 | **无** | 同上，macho = 0 |
| `com.apple.driver.AppleUSBEthernetDevice` | 有 | **无** | 同上，macho = 0 |
| `com.apple.iokit.IOUSBHostFamily` | 有 | **无** | macho `IOUSBHostFamily` = 0 |
| `com.apple.driver.usb.AppleUSBXHCI` | 有 | **无** | macho `AppleUSBXHCI` = 0 |
| `com.apple.driver.usb.AppleUSBHostT8011` | 有 | **无** | kc 34 列表内；macho 0 |
| `com.apple.driver.AppleT8011USBXDCI` | 有 | **无** | kc 34 列表内；macho 0 |
| `com.apple.driver.AppleEmbeddedUSB` | 有 | **无** | kc 34 列表内；macho 0 |
| `com.apple.driver.AppleUSBHostFamily` | **不存在** | **不存在** | `AppleUSBHostFamily` 0 / 0 —— 见 §6-1 |
| `com.apple.driver.AppleUSBMux` | **不存在** | **不存在** | `AppleUSBMux` 0 / 0 —— 见 §6-2 |
| `AppleUSBDevice`（作为 kext id） | **不是 kext id** | **不是 kext id** | `AppleUSBDevice` 1 / 1，但只出现在 `IOSkywalk` 字符串区；真 id 是 `…AppleUSBDeviceMux/NCM/AudioController` |
| `IOUSBHostDevice`（类名，非 kext id） | 有（类名字符串 2 处） | **有字符串 1 处**（0x1168fb9，IOSkywalk 区，非实体） | `IOUSBHostDevice` 2 / 1 |
| `IOUSBDeviceController`（类名，非 kext id） | 有（类名字符串 1 处） | 无 | `IOUSBDeviceController` 1 / 0 |
| `IOUSBHostController`（类名） | **不存在** | **不存在** | 0 / 0 —— 见 §6-4 |
| `AppleUSBHostController`（类名） | 有（3 处字符串，在 AppleUSBXHCI 二进制里） | 无 | 3 / 0 |

### 1.2 为什么"本仓列"全是"无"

1. kernel.macho 的 kext 集合由 prelink **roots** 决定：`/e/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml:33` 的 `"roots"` 共 32 条，**没有一条 USB kext**（列表里最近的是 `com.apple.iokit.IOHIDFamily`、`com.apple.iokit.IOHIDEventDriver`、`com.apple.iokit.IOStorageFamily`）。
2. kernel.macho 的 `__PRELINK_INFO` 解析出 **38 个 kext 条目，USB 相关 0 个**（解析方法见附录 A）。
3. `kernel.json` 的 components 只有 30 个，同样无 USB（同一目录 `kernel/kernel.json`）。
4. 反证：sheng 之所以有 Apple USB 栈，是因为它的 roots 里显式列了 USB kext —— `/e/k60-work/references/UniXNU-sheng/board.toml:211` 的 roots 含 `com.apple.iokit.IOUSBDeviceFamily`、`com.apple.driver.AppleUSBXDCI`、`com.apple.driver.AppleUSBDeviceMux`、`com.apple.iokit.IOUSBHostFamily`、`com.apple.driver.usb.AppleUSBXHCI`、`com.apple.driver.usb.AppleUSBHub`、`com.apple.driver.usb.AppleUSBHostCompositeDevice`、`com.apple.driver.usb.IOUSBHostHIDDevice`、`com.apple.iokit.IOUSBMassStorageDriver` 等，并用 `!com.apple.driver.AppleOnboardSerial`、`!com.apple.driver.AppleSMC` 排除。**同一份 20G81 kernelcache，roots 决定谁进内核。**

### 1.3 20G81 kernelcache 里 identifier 含 "USB" 的 34 个 kext（完整枚举）

`com.apple.driver.AppleEmbeddedUSB`, `…AppleEmbeddedUSBHost`, `…AppleS5L8960XUSB`, `…AppleT8011USB`, `…AppleT8011USBXDCI`, `…AppleUSBAudio`, `…AppleUSBCardReader`, `…AppleUSBDeviceAudioController`, `…AppleUSBDeviceMux`, `…AppleUSBDeviceNCM`, `…AppleUSBEthernetDevice`, `…AppleUSBEthernetHost`, `…AppleUSBHSIC`, `…AppleUSBHostMergeProperties`, `…AppleUSBMike`, `…AppleUSBTopCaseDriver`, `…AppleUSBXDCI`, `…USBStorageDeviceSpecifics`, `com.apple.driver.usb.AppleUSBCommon`, `…usb.AppleUSBEHCI`, `…usb.AppleUSBHostCompositeDevice`, `…usb.AppleUSBHostPacketFilter`, `…usb.AppleUSBHostPlatformProperties`, `…usb.AppleUSBHostT8011`, `…usb.AppleUSBHostiOSDevice`, `…usb.AppleUSBHub`, `…usb.AppleUSBOHCI`, `…usb.AppleUSBXHCI`, `…usb.IOUSBHostHIDDevice`, `…usb.IOUSBHostHIDDeviceSafeBoot`, `com.apple.iokit.IOAccessoryPortUSB`, `…IOUSBDeviceFamily`, `…IOUSBHostFamily`, `…IOUSBMassStorageDriver`（前缀省略号均表示 `com.apple.` / `com.apple.driver.`）。

---

## 2. 设备模式 vs 主机模式：两条绑定路径

### 2.1 设备模式（device mode）：`AppleUSBXDCI` → `IOUSBDeviceController` → `IOUSBDeviceInterface`

```
厂商 subclass（sheng: QcomDwc3，继承 AppleUSBXDCI）
  └─ 手动 load：OSKextLoadKextWithIdentifier("com.apple.driver.AppleUSBXDCI")   [UsbProbe.cpp:22]
       └─ class AppleUSBXDCI  （无 IOKitPersonalities，自己不匹配任何 provider）
            └─ 发布 IOUSBDeviceController 实例
                 └─ IOUSBDeviceConfigurator ×4  (IOUSBDeviceFamily, IOProviderClass=IOUSBDeviceController)
                      └─ 发布 IOUSBDeviceInterface（⚠ 该"发布"动作无 personality 证据，见 §6-9）
                           ├─ AppleUSBDeviceMux      (IOProviderClass=IOUSBDeviceInterface, IOResourceMatch=IOBSD)
                           ├─ AppleUSBDeviceNCM      (Control ×3 / Data ×2, IOProviderClass=IOUSBDeviceInterface)
                           ├─ AppleUSBEthernetDevice (IOProviderClass=IOUSBDeviceInterface)
                           └─ IOUSBDeviceInterfaceReserved (IOUSBDeviceFamily 自己)
```

| 边 | 证据 |
|---|---|
| QcomDwc3 继承 AppleUSBXDCI | `docs/plans/OFFICIAL-DRIVER-MAP.md:41`（"QcomDwc3 继承 AppleUSBXDCI/AppleUSBXHCI"）；sheng 依赖清单 `/e/k60-work/references/UniXNU-sheng/porting.toml:448` |
| 手动 load XDCI | `/e/k60-work/references/UniXNU-sheng/package/UsbProbe.cpp:22`，注释在 `:20-21`："AppleUSBXDCI has no personality of its own, so nothing has loaded it" |
| XDCI 无 personality | 本仓文档同结论 `docs/plans/DOCS-DRIVERS-ALL.md:266`；20G81 plist 解析：`AppleUSBXDCI` 的键里**没有 `IOKitPersonalities`**（§附录 A） |
| XDCI 依赖 | `OSBundleLibraries` = `com.apple.iokit.IOUSBDeviceFamily 2.0`、`com.apple.driver.usb.AppleUSBCommon 1.0`、`kpi.bsd/mach/iokit/libkern 20.0`（同解析） |
| 4 个 configurator | 20G81 `IOUSBDeviceFamily` 的 personalities：`Configuration-standardBringup` / `-ncmBringup` / `-ncmAuxBringup` / `-iBridgeBringup`，均 `IOClass=IOUSBDeviceConfigurator, IOProviderClass=IOUSBDeviceController` |
| mux/ncm/ethernet 的 provider | 同上解析：三者 `IOProviderClass` 全是 `IOUSBDeviceInterface`；mux 另加 `IOResourceMatch=IOBSD` |
| `IOUSBDeviceFamily` 自身依赖 | `com.apple.driver.usb.AppleUSBCommon 1.0` + kpi 20.0；**不依赖 AppleARMPlatform、不依赖 ADT 节点** |

**要点：设备模式整条链上没有一处 IOProviderClass 指向平台专家/ADT 节点** —— 起点是厂商 driver 自己发布的 controller，所以设备模式不需要 platform-expert 设备节点。

### 2.2 主机模式（host mode）：`AppleEmbeddedUSBNub` → `AppleUSBXHCI` → `IOUSBHostDevice`

```
平台/ADT 节点（提供 AppleEmbeddedUSBNub）
  └─ AppleNubT8011USBXHCI   (AppleUSBHostT8011, IOProviderClass=AppleEmbeddedUSBNub, IONameMatch="usb-xhci,t8011", IOProbeScore 10000)
       └─ AppleUSBXHCI（IOKitPersonalities 键存在但内容为空；依赖 IOUSBHostFamily 1.2 + AppleARMPlatform + IOAccessoryManager）
            └─ IOUSBHostFamily 发布的服务/设备
                 ├─ AppleUSBHostResources        (IOProviderClass=IOResources, IOResourceMatch=IOKit, IOMatchCategory=AppleUSBHostResources)
                 ├─ AppleUSBHostResourcesTypeC   (IOProviderClass=IOResources)
                 ├─ AppleUSBHostResourcesClient  (IOProviderClass=AppleUSBHostResources)
                 ├─ AppleUSBHostPacketFilter     (IOProviderClass=AppleUSBHostResources)
                 └─ IOUSBHostDevice
                      ├─ AppleUSBHostCompositeDevice / AppleUSBPrinterDevice0/1 / InterfaceAssociationClass
                      ├─ AppleUSBCDCCompositeDevice (bDeviceClass 2 / 239,2,1 / 0)
                      ├─ AppleUSBHostiOSDevice, AppleUSBHostMergeProperties（大量 idVendor 1452 条目）
                      └─ IOUSBHostInterface → IOUSBHostHIDDevice
```

| 边 | 证据（20G81 plist 实测，见附录 A） |
|---|---|
| nub 名字 | `AppleNubT8011USBXHCI`: `IONameMatch = "usb-xhci,t8011"`, `IOProviderClass = AppleEmbeddedUSBNub`, `IOProbeScore = 10000` |
| 同族其它 nub 名 | `"usb-ohci,t7000"`、`"usb-ehci,s5l8960x"`、`"usb-device,t8011"`、`"usb-device,t7000"` |
| XHCI 自身无 personality | `com.apple.driver.usb.AppleUSBXHCI` 的 `IOKitPersonalities` 存在但为空 dict |
| host family 的锚点 | `IOUSBHostFamily` 里 `AppleUSBHostResources` 匹配 `IOResources` + `IOResourceMatch=IOKit`（任何 XNU 都有 IOResources，所以这条**不是**瓶颈） |
| device 侧匹配点 | `IOUSBHostDevice` 作为 `IOProviderClass` 被 CompositeDevice / usb.cdc / MergeProperties / HostiOSDevice 使用；`IOUSBHostInterface` 被 IOUSBHostHIDDevice 使用 |
| 唯一把 ADT 与 USB 连起来的东西 | `AppleEmbeddedUSB` 的 `AppleEmbeddedUSBArbitrator`: `IONameMatch = "usb-complex,s5l8900x"`, `IOProviderClass = AppleARMIODevice`；它需要 `AppleARMIODevice` 节点，而本仓平台专家发布的是 `IOPlatformDevice`（见 §3-8） |

> ⚠ `AppleEmbeddedUSBArbitrator` 是否就是 `AppleEmbeddedUSBNub` 的生产者，**没有证据**（§6-5）。因此主机模式在 K60 上不是"加配置"能补的。

---

## 3. 匹配条件清单：要接 Apple 栈还缺什么

| # | 条件 | 依据（绝对/仓库内路径:行） | K60 现状 |
|---|---|---|---|
| 1 | USB kext 必须先进 prelink roots，否则根本不在 kernel.macho 里 | `/e/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml:33`；sheng 对照 `/e/k60-work/references/UniXNU-sheng/board.toml:211` | **缺失**（32 条 roots 无 USB） |
| 2 | `AppleARMPlatform` 必须已在（`AppleUSBDeviceNCM`、`AppleUSBXHCI` 都依赖它） | 依赖表见附录 A；roots `profile.toml:33` 含 `com.apple.driver.AppleARMPlatform` | **已有** |
| 3 | `AppleUSBXDCI` 不需要 personality、但需要有人 load 它 | `AppleUSBXDCI` 无 `IOKitPersonalities`；`UsbProbe.cpp:22`；`docs/plans/DOCS-DRIVERS-ALL.md:266` | **缺失**（本仓无任何 load 点，`rg com.apple.driver.AppleUSBXDCI` 只命中文档，见 §6-3） |
| 4 | 设备模式的 provider 由厂商 driver 自己发布 `IOUSBDeviceController` | `IOUSBDeviceFamily` 的 4 个 configurator `IOProviderClass=IOUSBDeviceController` | **缺失**（本仓无 USB 的 IOService subclass） |
| 5 | `AppleUSBXDCI` 的 vtable/ABI 表必须按**目标 kernelcache**生成 | sheng 脚本只跑 24A446：`/e/k60-work/references/UniXNU-sheng/scripts/gen-usb27-abi.py:17`；本仓结论 `docs/plans/OFFICIAL-DRIVER-MAP.md:41`（"ABI 脚本只针对 24A446"） | **缺失**（20G81 无对应 json） |
| 6 | 主机模式需要一个 `AppleEmbeddedUSBNub` provider（`IONameMatch="usb-xhci,t8011"`） | 20G81 plist（§2.2 表） | **缺失**（无任何 kext/DT 生产它，§6-5/§6-7） |
| 7 | 平台/ADT 里要有对应 USB 节点 | `hardware.dtb`（1866 B）`strings` 只有 `xiaomi,mondrian`/`cpus`/`psci`/`arm,gic-v3`/`memory@900000000`/`ufs@1d84000`/`qcom,sm8475-ufshc`；仓库 `dts/mondrian.dts`（198 行）无 usb/dwc3 | **缺失** |
| 8 | 平台专家当前发布的是 `IOPlatformDevice`，不是 Apple 的 `AppleARMIODevice` | `/opt/.../tree/.cache/xnu-work/iokit/KernelConfigTables.cpp:48-53`（`IOClass=ArmDTPlatform, IOProviderClass=IOPlatformExpertDevice, IONameMatch='device-tree'`）；`drivers/ArmDTPlatform/ArmDTPlatform.cpp:124`（`createNub`）、`:211`（"as real IOPlatformDevice nubs"） | **类型不符**（有 nub，但类不对） |
| 9 | built-in personality 的注册方式：写进 `KernelConfigTables.cpp` | 同上 `:35-75`（现有 6 个：ArmCpu / ArmVirtPlatform / ArmDTPlatform / IOPanicPlatform / NativeUfs `:61-64` / NativeRamBlock `:69-73`） | **机制已有**（可直接照 NativeUfs 的写法加） |
| 10 | 不能靠运行时加载 kext 包补 | `docs/plans/OFFICIAL-DRIVER-MAP.md:45`（"kext 需要 loader protocol revision 2，shipped DarwinBoot 不接受 staged kexts"） | **缺失**（只能 built-in + prelink） |
| 11 | DMA/SMMU：USB 需要流映射或 bypass | `patches/xnu/0300-k60-usblog-ep0.patch` 生成的文件里 `smmu_usb_bypass()`（文件行 479）、`smmu_plan/configure`（411/434）；另有 `0307-k60-usblog-dma-coherency.patch`（`patches/xnu/series:132`） | **已有**（但作用于现有裸驱动，Apple 栈要自己再谈一次） |
| 12 | 时钟/PHY 门控：GCC + QSCRATCH + eUSB2 | 同文件 `ml_io_map(GCC_PA…)`（文件行 211）、`QSCRATCH_PA 0x0a6f8800`（568）、`EUSB2` 注释 0x88e3000（108） | **已有** |
| 13 | 角色切换（device ↔ host）需要 Type-C/UCSI 决策 | `docs/research/usb/RESEARCH.md` §5（UCSI 在 `pmic_glink` 下，AP 侧无 usb-role-switch 节点） | **缺失**（AP 侧无 role switch） |
| 14 | 主机侧 `AppleUSBHostResources`（`IOResources`+IOKit） | 20G81 plist：`AppleUSBHostResources` personality | **随 kext 一起到位**（不是瓶颈） |

---

## 4. 现有 `k60_usblog.c` 提供了什么

来源：`patches/xnu/0300-k60-usblog-ep0.patch`（`patches/xnu/series:124` 引用），新增文件 1339 行。
**行号规则**：下表"文件行"= 该 patch 内文件正文行号（patch 第 14 行 = 文件第 1 行；构建树里 `.cache/xnu-work/bsd/dev/k60_usblog.c` 已被后续补丁改成 1792 行，行号不同）。
性质：`bsd/conf/files` 里一行 `bsd/dev/k60_usblog.c standard`（patch:6），由 `osfmk/arm/arm_init.c`（patch:1358-1364）与 `bsd/kern/bsd_init.c`（patch:1372-1380）直接调用 —— **它是 BSD 层裸 C 代码，不是 kext，也不是 IOService**：全文 `IOService|IOKit|OSMetaClass|OSKext|IOProviderClass|IOClass` 只有 1 处命中，且是注释（文件行 1320 "Called from bsd_init once IOKit is up"）。

| 能力 | 入口（文件行） | 说明 | Apple 栈替代后是否还要自己写 |
|---|---|---|---|
| boot-arg 开关 | `k60_usblog_arg()` 162 | `k60_usblog=0/1/2`（0 惰性、1 只读探测、2 全 CDC 控制台） | 否（换成驱动自己的开关） |
| 只读探测 | `k60_usblog_probe()` 206 | 映射 DWC3/GCC/eUSB2/SMMU 打寄存器，失败即退出 | 部分（PHY/时钟仍需自备） |
| apps_smmu | `smmu_dump_state()` 177、`smmu_plan()` 411、`smmu_configure()` 434、`smmu_usb_bypass()` 479 | stream-0 bypass 上下文 + 4K 全局页约束 | **是**（Apple 栈走 IODART/自己的 DMA 契约） |
| DWC3 设备控制器 | `dwc_wr/rd` 632/639、`ud_epcmd()` 668、`ud_start()` 708、`ud_endpoint()` 745、`ud_reset_endpoints()` 760 | 端点命令/TRB/事件环 | **是**（Apple 侧由 subclass 做，等价工作量） |
| 描述符与标准请求 | `ud_configuration()` 803、`ud_string()` 821、`ud_setup()` 848 | VID 0x1209 / PID 0x0001、CDC-ACM 两接口（776-795） | 否（Apple 栈自己造描述符，但要给 mux/NCM 让路） |
| CDC-ACM 控制台 | `ud_console()` 978 | 把内核 console 镜像灌进 USB bulk IN | 否（可改走 `AppleUSBDeviceMux`+`AppleUSBDeviceNCM` 或 serial） |
| 事件泵 | `ud_event()` 1038、`ud_events()` 1108、`ud_worker()` 1147、`ud_hb()` 1144 | worker + 2 s 心跳 | 否（IOKit 有 workloop） |
| 启动顺序 | `k60_usblog_init()` 262（arm_init 期）、`k60_usblog_start()` 1325（bsd_init 期、线程可用后） | 两段式启动 | 否（但 load 时机要重排，见 §5） |

---

## 5. 参考实现：sheng 的 `UsbProbe.cpp` 加载序列

文件：`/e/k60-work/references/UniXNU-sheng/package/UsbProbe.cpp`（47 行）。

| 步 | 行 | 动作 | 失败处理 |
|---|---|---|---|
| 0 | `:10` | `extern kmod_info_t g_kernel_kmod_info;` | — |
| 0 | `:11-16` | 5 个 `extern "C"`：`qcom_dwc3_bring_up()`、`qcom_dwc3_publish()`、`qcom_dwc3_diag(bool)`、`qcom_dwc3_static_init`（绑定 `__GLOBAL__sub_I_QcomDwc3.cpp`）、`qcom_dwc3_host_load(int)`、`native_usb_stats[54]` | — |
| 1 | `:18` | `IOSleep(3000)` 等 IOKit 起来 | — |
| 2 | `:19` | `qcom_dwc3_bring_up()`（PHY/时钟/复位/SMMU 全在这步） | 失败直接返回 |
| 3 | `:22` | `OSKextLoadKextWithIdentifier("com.apple.driver.AppleUSBXDCI")` | `:24` 非 `kOSKextReturnStartStopError` → `stats[0]=-9`，`thread_terminate` |
| 4 | `:23` | 结果存 `native_usb_stats[21]` | — |
| 5 | `:26` | `qcom_dwc3_host_load((int)OSKextLoadKextWithIdentifier("com.apple.driver.usb.AppleUSBXHCI"))` | — |
| 6 | `:27` | `handle = OSMetaClass::preModLoad(g_kernel_kmod_info.name)` | 失败 `stats[0]=-10` |
| 7 | `:30` | `qcom_dwc3_static_init()`（静态构造：注册 subclass） | — |
| 8 | `:31` | `postModLoad` | 失败 `stats[0]=-11` |
| 9 | `:33` | `qcom_dwc3_publish()`（发布 `IOUSBDeviceController`） | — |
| 10 | `:34-36` | `PE_parse_boot_argn("usb", &mode, …)`，mode 2/3 → `qcom_dwc3_diag(true)` | — |
| 11 | `:42-47` | `sheng_usb_probe()` 只在 boot-arg `usb` 非零时 `kernel_thread_start` | — |

**同一 identifier 是否出现在本仓**：`rg -c 'com\.apple\.driver\.AppleUSBXDCI' .` → 仅 4 个文档文件（`docs/research/usb/RESEARCH.md`、`docs/plans/OFFICIAL-DRIVER-MAP.md`、`docs/plans/DOCS-PORTING-ALL.md`、`docs/plans/DOCS-DRIVERS-ALL.md`），**代码/脚本/配置 0 处**（`rg --no-heading -g '!docs/**'` 输出为空）。

`gen-usb27-abi.py`（76 行）产出的 ABI 事实：`:14` SERIES=`parents[2]`；`:16` `from kc_image import Image`（`kits/XnuPrelink`）；`:17` 读 `out/ipsw/24A446/kernelcache.decompressed`；`:18` `Image(raw).fixups()`；`:19-21` `VT=0xfffffe00083f24c0`、`COUNT=280`、`BASE=168`；`:24-46` SipHash 判别式（key `b5 d4 c9 eb 79 10 4a 79 6f ec 8b 1b 42 87 81 d4`，末轮 rounds(4)，`%0xffff+1`）；`:49-57` 逐槽取 target + `kind==1` + diversity，并给 179/227/267/268-270/275-278 号槽显式签名；`:59-68` 对每个 ≥168 的槽暴力生成 `opaque{i}_{n}` 去匹配 mangled `_ZN12AppleUSBXDCI…`；`:69-73` 输出 json（`collection_slide=0x1f000000000`、`instance_size=0x2650`、`bindings` 里 C2 `0xfffffe000a68d85c`、D2 `0xfffffe000a68d894`、gMetaClass `0xfffffe000bb68bd0`、`__ZTV12AppleUSBXDCI = VT-16`）；`:74-76` 写 `scripts/usb-xdci-24A446.json`。**它只对 24A446 跑，没有 20G81 版本。**

---

## 6. NO EVIDENCE FOUND 清单

| # | 找不到的东西 | 搜索词 / 命令 |
|---|---|---|
| 1 | `com.apple.driver.AppleUSBHostFamily` 这个 identifier 存在于任何产物 | `strings -a kernelcache.decompressed \| grep -c -x AppleUSBHostFamily` = 0；同命令对 kernel.macho = 0；`rg 'AppleUSBHostFamily' /e/hackios/k60-usb` = 0 |
| 2 | `com.apple.driver.AppleUSBMux` | `strings\|grep -c -x AppleUSBMux` = 0（kc 与 macho 皆 0） |
| 3 | 本仓代码路径里对 `AppleUSBXDCI` 的任何引用 | `rg -n --no-heading 'com\.apple\.driver\.AppleUSBXDCI' -g '!docs/**' .` → 空 |
| 4 | `IOUSBHostController` 类名 | `strings\|grep -c -x IOUSBHostController` = 0（kc 与 macho 皆 0）；`rg 'IOUSBHostController'` = 0 |
| 5 | 谁创建 `AppleEmbeddedUSBNub`（哪个 kext 的哪个 personality/函数） | 20G81 plist 里 `AppleEmbeddedUSBNub` 只作为 `IOProviderClass` 值出现（5 处：usb-xhci,t8011 / usb-ohci,t7000 / usb-ehci,s5l8960x / usb-device,t8011 / usb-device,t7000），**没有任何 `IOClass=AppleEmbeddedUSBNub` 的条目**；`rg 'AppleEmbeddedUSBNub'` 于本仓 = 0（只有 §3 无）；sheng 参考树内亦无源码 |
| 6 | sheng 的 `QcomDwc3` 实现源码（本机 references 里） | `rg -c 'QcomDwc3\|qcom_dwc3' /e/k60-work/references/UniXNU-sheng` → 只有 `porting.toml`(9)、`package/UsbProbe.cpp`(11)、`package/BootLog.c`(1)、`package/ShengBattery.cpp`(3)、`scripts/build-gop-legacy-display-27.py`(13)、`scripts/gen-qmp-usb3-table.py`(1)；**无 QcomDwc3.cpp/.h** |
| 7 | K60 的任何 USB 平台/ADT 节点 | `strings -a .../device-tree/hardware.dtb \| grep -i 'usb\|dwc3\|xhci'` → 空（该 dtb 1866 B，只有 `xiaomi,mondrian`/`cpus`/`psci`/`arm,gic-v3`/`memory@900000000`/`ufs@1d84000`+`qcom,sm8475-ufshc`）；`rg -i 'usb\|dwc3\|xhci' drivers/ArmDTPlatform* drivers/PongProbe.h` → 空；`rg -n -i 'usb\|dwc3\|xhci' scripts/adt-generate.py scripts/make-pong-adt.py scripts/pong_adt_contract.py` → 空；仓库 `dts/mondrian.dts`（198 行）`grep -i usb` → 空 |
| 8 | `AppleUSBHostPlatformProperties` 的 personality | 20G81 plist：该 kext **无 `IOKitPersonalities`**（只有 `OSBundleLibraries`=`kpi.iokit 16.0.0`+`AppleUSBHostMergeProperties 1.2`） |
| 9 | `IOUSBDeviceConfigurator` 发布 `IOUSBDeviceInterface` 的直接证据（谁 new 的） | 只能看到 `IOUSBDeviceInterface` 作为 5 个 personality 的 `IOProviderClass`（ReservedInterface + mux/ncm×2/ethernet/mike/audio），**没有"生产者"条目** |
| 10 | 20G81 的 `AppleUSBXDCI` ABI 表 / 任何 K60 侧 XDCI 绑定 json | `ls /e/k60-work/references/UniXNU-sheng/scripts/usb-xdci-*.json` 只有 `24A446` 与 `26C5035r`；本仓 `rg 'usb-xdci'` = 0 |
| 11 | `AppleUSBXHCI` 在 iOS 16.6.1 上的 IOKitPersonalities 内容 | plist 里该键存在但为**空 dict**；因此无法从 personality 判断它原本匹配什么 provider（只能从 `AppleUSBHostT8011` 的 `AppleNubT8011USBXHCI` 反推） |

**合计：11 条 NO EVIDENCE FOUND。**

---

## 7. 对 K60 的下一步建议

1. 先按 sheng 的形态把设备模式跑通：在 `profile.toml:33` 的 roots 里追加 `com.apple.driver.AppleUSBXDCI`、`com.apple.iokit.IOUSBDeviceFamily`、`com.apple.driver.AppleUSBDeviceMux`、`com.apple.driver.usb.AppleUSBCommon`（mux 需要 `IOResourceMatch=IOBSD`，XNU 侧天然满足）。
2. 用 `gen-usb27-abi.py` 的同一套 SipHash/vtable 方法对 **20G81** kernelcache 生成 XDCI 绑定表（现成 json 只有 24A446，直接搬会踩 §3-5 的坑）。
3. subclass `AppleUSBXDCI` 时把 `k60_usblog.c` 的 SMMU bypass、GCC/QSCRATCH/eUSB2 序列整段搬进 `start()`，先只发布 `IOUSBDeviceController` 不动 CDC，确认 `IOUSBDeviceConfigurator` 能匹配上。
4. 主机模式先别碰 `AppleEmbeddedUSBNub`（本仓无生产者）；若必须做，就要给自己的 kext 加一条 `IOClass=…, IOProviderClass=IOPlatformDevice` 的 personality（照 `KernelConfigTables.cpp:61-64` 的 NativeUfs 写法），绕开 Apple 的 nub 名。
5. 角色切换缺口（§3-13）单独排期：没有 AP 侧 role switch，设备模式与主机模式只能二选一写死。

---

## 附录 A：可复现的取证命令

在 WSL 内执行（`wsl.exe -u root -e bash -lc '...'`）。

### A.1 两个产物里"某个 identifier 是否存在"（§1.1 表的数据来源）

```bash
K=/opt/k60/trees/k60build/out/ipsw/20G81/kernelcache.decompressed
M=/opt/k60/trees/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho
for s in AppleUSBXDCI IOUSBDeviceFamily AppleUSBHostFamily AppleUSBMux AppleUSBDevice \
         AppleUSBDeviceMux AppleUSBDeviceNCM AppleUSBEthernetDevice IOUSBHostFamily \
         AppleUSBXHCI AppleEmbeddedUSBNub IOUSBHostDevice IOUSBHostController AppleARMIODevice; do
  printf "%-24s kc=%-4s macho=%-4s\n" "$s" \
    "$(strings -a "$K" | grep -c -x "$s")" "$(strings -a "$M" | grep -c -x "$s")"
done
```

2026-11-14 实测输出（节选）：

```
AppleUSBXDCI             kc=1    macho=0
AppleUSBHostFamily       kc=0    macho=0
AppleUSBMux              kc=0    macho=0
AppleUSBDevice           kc=1    macho=1
IOUSBHostDevice          kc=2    macho=1
IOUSBHostController      kc=0    macho=0
AppleUSBHostController   kc=3    macho=0
AppleEmbeddedUSBNub      kc=2    macho=0
AppleARMIODevice         kc=2    macho=1
```

注意：**不能用 `grep -a -c`**。该 kernelcache 几乎没有换行，`grep -c` 按行计数恒为 1（例如 `grep -a -c 'CFBundleIdentifier' kernelcache` 只出 10，而真实条目 236 个），必须 `strings | grep -c -x`。

### A.2 kext 清单与 personality（§1.3 / §2.2 / §3 的 plist 事实）

```__PRELINK_INFO``` 是 XML plist，但键值以 `<string ID="…"/>` + `<string IDREF="…"/>` 交叉引用，**plistlib 直接解析会抛 `plistlib.InvalidFileException: Invalid file`**（此格式在本仓已有证据里可见：`docs/research/evidence/bluetooth-kext-symbol-detail.txt:18` 就是 `IONameMatch` 的 `IDREF` 形态）。因此用两遍解析：

1. `d.find(b'<key>_PrelinkInfoDictionary</key>')` 定位（本机偏移 **45449222**），向后取 40 MiB 窗口；
2. 第一遍 `<string ID="(\d+)">(.*?)</string>` 建 ID 表；
3. 第二遍按每个 kext 的 `<key>CFBundleIdentifier</key>` → `IDREF` 回填，得到 **236 个 kext 条目**；`IOKitPersonalities` 内的 `IOClass/IOProviderClass/IONameMatch` 同样回填；
4. 只验存在性时可直接子串计数，例如 `grep -o 'usb-xhci,t8011' <窗口>` → 1（唯一一处属于 `AppleNubT8011USBXHCI`）。

§2.2 / §3 引用的取值即由此得到，例如 `AppleNubT8011USBXHCI` 的三元组 = `IOClass=AppleNubT8011USBXHCI` / `IOProviderClass=AppleEmbeddedUSBNub` / `IONameMatch=usb-xhci,t8011`。

⚠ 不要用"从某 identifier 字符串向前找最近 `<dict>`"的方式取块：`<string>AppleUSBXDCI</string>` 首次出现于 **`AppleT8011USBXDCI` 的 `OSBundleLibraries`**，会把它人的 personality 误算到 XDCI 头上（本次实测踩过）。

### A.3 从 patch 重建 `k60_usblog.c` 并取函数行号（§4 表）

```bash
cd /e/hackios/k60-usb
awk 'NR>=14 && NR<=1352 && /^\+/ {sub(/^\+/,""); print}' patches/xnu/0300-k60-usblog-ep0.patch > /tmp/k60c.c
wc -l /tmp/k60c.c                                              # 1339
grep -n -E '^[a-zA-Z_][a-zA-Z_0-9]*\(' /tmp/k60c.c              # 33 个函数，即 §4 表
grep -n -E 'IOService|IOKit|OSMetaClass|OSKext|IOProviderClass|IOClass' /tmp/k60c.c
```

实测：
* 函数定义 **33 个**（首个 `usb_rd` 在 147 行，末个 `k60_usblog_start` 在 1325 行）；
* IOKit 相关只有 **1 行**：`/tmp/k60c.c:1320` 的注释 "Called from bsd_init once IOKit is up" —— 即该驱动不含任何 IOKit 类；
* 构建树里的同一文件已被后续补丁扩到 **1792 行**（`/opt/k60/trees/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/bsd/dev/k60_usblog.c`，61166 B），因此引用行号必须以 patch 为准并注明版本。

### A.4 产物内 USB 字符串的完整枚举（§1.3）

```bash
strings -a "$K" | grep -o 'com\.apple\.\(driver\.\)\?[A-Za-z0-9.]*USB[A-Za-z0-9.]*' | sort -u | wc -l   # 40
```
plist 层面（identifier 含 "USB" 的 kext）为 **34 个**，两者差集是 libs/字符串引用而非 kext 实体。

