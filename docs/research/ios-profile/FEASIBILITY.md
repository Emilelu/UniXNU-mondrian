# ios-profile/FEASIBILITY.md —— 换 iOS profile 的可行性（电话/短信/基带）

**结论层。** 证据行在 `evidence/telephony-inventory.txt`、`evidence/abi-and-kernel.txt`、`evidence/data-volume.txt` 与下列 file:line 引用。
调研问题（用户原话）：电话/短信/基带需要 iOS 而不是 iPadOS —— 换 OS profile 值不值得、卡在哪。
本报告只做调研，不改 board.toml、不动 profiles/。

## 0. 一页结论

| # | 结论 | 决定性证据 |
| --- | --- | --- |
| C1 | **「iPadOS 缺电话基础设施」不成立**。同一 build（16.6.1/20G81）的 iOS 与 iPadOS 系统卷，电话/短信的框架层、daemon 层、XPC 服务层、非 Phone 的 UI app（MobileSMS/InCallService 等 9 个）**逐项一致**；唯一的整包差异是 `Applications/MobilePhone.app` 本体，外加 9 个与电话无关的 app（CarPlay/健康/睡眠/支付）。 | evidence/telephony-inventory.txt:14-29、:97-130、:132-139 |
| C2 | **换 iOS 拿不到任何「电话能力」增量**：能拿到的只有 Phone.app 一个 bundle（iOS 卷 115 个条目）+ 若干背景图；短信（MobileSMS.app）、通话服务（InCallService.app）、CommCenter 全套 daemon 两侧本来就有。 | evidence/telephony-inventory.txt:21、:31-96、:133-138 |
| C3 | **真正的缺口在基带，且与 OS 无关**：iOS 16.6.1（iPhone11）内核走 `AppleConvergedIPC`+`AppleBasebandI19`（Intel ICE17），iPadOS（iPad7）走 `AppleBasebandPCI`+`AppleBasebandN71`（Qualcomm Mav/vinyl），**两家都没有 QRTR/QMI 通路**（qrtr 计数 = 0），K60 的 SM8475 modem 是 PAS 远程处理器 + QMI/QRTR（k60-cellular 取证）。换任何一个 Apple profile 都不带来 Qualcomm 基带驱动。 | evidence/abi-and-kernel.txt:55-64；k60-cellular/docs/research/cellular/01-ANDROID-INVENTORY.md:15-22、:92-130 |
| C4 | **iOS 16.6.1 用户态整体是 arm64e，iPadOS 16.6.1 用户态是 arm64**；K60 当前内核是 arm64（subtype 0x0）。所以「iPhone12,1 的 16.6.1」直接换上去 ABI 不匹配；**arm64 的 iOS 候选是 A11 机型**（iPhone10,1/10,3/10,6 的 16.6.1）。A11 的 OS 卷与内核**已下载实测**：SpringBoard / launchd / MobilePhone 三个 Mach-O 的 subtype 全部 0x0（arm64），内核 fat 唯一 slice 也是 0x0——A11 变体与 K60 现有 arm64 基座同类。 | evidence/abi-and-kernel.txt:28-36、:50-53、:66-89、:91-104（A11 实测段） |
| C5 | **没有 iOS IPSW 可下载这一担忧不成立**：Apple CDN 全部可直下（iPhone12,1 6.41 GB、iPhone10,3/10,6 6.17 GB，实测 curl/urllib 200，~50 MB/s）。真正的卡点是 **profile 与构建链的身份 pin**（chip_id/board_id/device_class/product/prelink slide/sha256/ADT product-id/display 参数），全部按 j120ap 定死，见 §4 步骤表。 | §1.4、§4 |
| C6 | **Data 卷（/var）格式两侧零差异**：private/var 顶层 28 项、mobile/Library 子项完全一致；SMS/CallHistory 库不在系统卷，首启后由 daemon 创建。Data 种子脚本无需为 iOS 改。 | evidence/data-volume.txt:4-27 |
| C7 | **最终判定：换 iOS 是「花一轮 profile/ABI/ADT 工程量换一个 Phone.app bundle」，而电话功能真正缺的是基带驱动（QcomBaseband 组件链）**。若目标是「点开拨号盘看到 UI」，换 iOS（A11 arm64 变体）可行但收益只有 Phone.app；若目标是「能打电话/发短信」，换 iOS **不能解锁任何一步**，卡点在 QcomBaseband（components.toml:563-581，verified_devices = []）与 modem PAS 基础设施，与 OS profile 无关。 | 本表 + §4 |

## 1. 问题 ①：iOS 与 iPadOS profile 的差异到底有哪些

### 1.1 profiles/os/ 目录现状

- `/mnt/e/hackios/UniXNU/profiles/os/` 只有 4 个目录：ipados-16.6.1-20G81、ipados-17.7.11-21H461、ipados-26.5.2-23F84、ipados-27.0.1-24A446（实测 ls）。git log --all -- profiles/os 从未出现过 ios-* 目录（只有 macos-27.3-26C5035r 系列与 ipados 系列）。
- 官方文档对 os_profile 的全部定义：`board | os_profile | Directory under profiles/os/`（UniXNU-docs/docs/reference/configuration.md:45）；分层合并 `Layers apply as ARM64, SoC, OS, device. Tables merge by key; arrays replace.`（:52）。
- **resolver 没有 ipados 白名单**：`scripts/unixnu/profiles.py:19-27 resolve_os()` 先按完整目录名匹配（:22-23 `if wanted in names: return wanted`），短名才走 `ipados-{wanted}.` 前缀（:24）；`load()` 只校验目录名合法与 `arch ∈ {arm64, arm64e}`（:42-44，arch 键从 os profile 的 `[os] arch` 读，默认 arm64）。**新建 profiles/os/ios-* 目录即可被选中，无需改 resolver**；同时 CLI 有 `--os` 参数（cli.py:23）可在不改 board.toml 的情况下试跑。
- 用户提到的 os-config 文档页不存在：unixnu.com/zh/porting/ 下没有 os-config 页（20 个页面列表实测，无 os-config），os_profile 的说明只在 reference/configuration.md:45 与 porting/device-repository.md:147-178。

### 1.2 profile.toml 逐字段对比（16.6.1 iPadOS 现行 vs 换 iOS 需要改的值）

现值（/mnt/e/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml）：

| 字段（行号） | 现值 | 换 iOS（iPhone12,1 n104ap） | 换 iOS（A11 iPhone10,6 d221ap） | 证据 |
| --- | --- | --- | --- | --- |
| [os] darwin (:3) | 22.6.0 | 同（同一 build 20G81） | 同 | BuildManifest ProductVersion/Build |
| [os] xnu_version (:4) | 8796.141.3 | 同 | 同 | 同 |
| [ipsw] url (:12) | iPad_Pro_HFR 042-44385 | iPhone12,1 042-44699 | iPhone10,3,10,6 042-44442 | BuildManifest/实测 URL |
| [ipsw] product (:13) | iPad7,1 | iPhone12,1 | iPhone10,6 | ipsw.py:121-123 校验 SupportedProductTypes |
| [ipsw] device_class (:16) | j120ap | n104ap | d221ap | ipsw.py:124-128 校验 DeviceClass |
| [ipsw] chip_id (:17) | 32785 (0x8011) | 32816 (0x8030) | 32789 (0x8015) | 同上 |
| [ipsw] board_id (:18) | 12 (0x0C) | 4 (0x04) | 14 (0x0E) | 同上；iPhone identity ApBoardID=0x04 实测（BuildManifest） |
| [ipsw] fetch (:19) | KernelCache/DeviceTree/StaticTrustCache/Cryptex1,SystemTrustCache | 同 | 同 | iPhone IPSW 同样有这四个成员 + BasebandFirmware |
| [kernel.prelink] kernelcache_sha256 (:28) | d260defc…（iPad 内核 pin） | 必须换成 iPhone 内核 sha 或删除 | 换成 A11 内核 sha | kernel.py:204-206 强制校验 |
| [kernel.prelink] slide (:32) | 0（autoslide -0xb9c000） | 须重推 | 须重推 | emit_prelink_autoslide.py 依赖 native 段表 |
| [adt.root.string] model/target-type/compatible (:54-57) | iPad7,1/J120/J120AP | iPhone12,1/N104/N104AP | iPhone10,6/D221/D221AP | devicetree.py:334-386 |
| [adt.product.string] idiom (:96) | pad | phone（影响 SpringBoard 习惯与 artwork） | phone | ADT artwork-device-idiom |
| [adt.product.bytes] product-id (:108) | e9fefef6…（J120 表项） | 必须换成 n104 的 product-id | d221 的 product-id | profile.toml:105-106 注释：MGGetProductType 查表 |
| display-scale (:88) | 3（1440x3200→480x1066.67 pt） | 重算 | 重算 | :84-87 注释 |
| root_match_volume_uuid（board.toml:219，[payload.adt]） | C5DAF029-2070-4F68-B3CC-1D1320344CF0（iPad OS 卷） | dbff1cb9-4016-4cd8-88f5-f6b13f3c1080 | 2e97a025-6bdf-4c98-a08c-6bd8ffcb1a46（实测） | launchd root-matching（make-pong-adt.py:162-165）；三卷 UUID 见 evidence/abi-and-kernel.txt:10、:23、:94 |

**iPhone 侧没有现成 profile 可抄**：devices.toml:890 出现过 `os_profile = "ios-16.7.16-20H392"`（fuxi-star-mailaz, SM8550），但其 profile 目录在上游不存在（devices.toml:494 record_error），社区设备记录（UniXNU-docs/docs/.vitepress/device-records/nx769j.toml:6,17）的做法是 profile 放设备仓库 `os-profiles/<name>/`、构建前装进 UniXNU checkout——即 iOS profile 在社区也是自己写，没有官方模板。macOS profile 模板亦不可用（profiles/os/macos-27.3-26C5035r 在当前 checkout 不存在）。

### 1.3 iOS 26/27 与 16 的架构分叉

ipados-26.5.2-23F84/profile.toml:3 与 ipados-27.0.1-24A446/profile.toml:3 都是 `arch = "arm64e"`；16.6.1/17.7.11 无该键（默认 arm64）。profiles/arch/ 只有 arm64 与 arm64e 两套（arm64 多 SoftwareAES、四层 patch_series；arm64e 无 SoftwareAES、两层 series、archives 空）。**换 arm64e 的 iOS 会同时换掉 arch 层 profile**，等于换一套构建基座。

### 1.4 IPSW 供给（C5）

- iPhone12,1 16.6.1/20G81：6,409,986,291 B，已下载并 7z 解包（/opt/k60/ios/）。
- iPhone10,3/10,6 16.6.1/20G81：6,167,417,432 B，URL 实测 200；成员表（自写 zip64 远端读取器）：OS = 096-57693-083.dmg（4,729,614,611 B，**method=0 stored，无需解压即可直读 APFS**）、SystemOS = 096-57293-083.dmg（2,745,171,968 B）、kernelcache.release.iphone10b（18,198,200 B，解压后为 fat Mach-O：唯一 slice cputype 0x100000c **subtype 0x0 = arm64**，evidence/abi-and-kernel.txt:53）、BasebandFirmware = Firmware/ICE17-6.01.01.Release.bbfw + Mav17-8.50.04.Release.bbfw。
- **A11 = arm64 的 iOS 候选**（iPhone 8/X，t8015 cpid 32789）：16.6.1/20G81 存在于 iPhone10,1/10,3/10,6（api.ipsw.me 实测）；iPhone9,x（t8010）没有 16.6.x。iPhone12,8（SE2, t8030）同样有 16.6.1，但 A12 及以后的机型用户态是 arm64e，不适用于 arm64 内核路线。
- **A11 变体已完整验证（不是纸面推断）**：iPhone10,3/10,6 的 OS dmg（096-57693-083.dmg，4,729,614,611 B，method=0 stored）已下载并 7z 直读 APFS——卷 `SydneyG20G81.D22D221OS.apfs`、vol_uuid 2e97a0256bdf4c98a08c6bd8ffcb1a46、142,350 文件/136,504 目录/2,324 符号链接；清单 7,637,352 行、141 个 app、MobilePhone.app 119 个条目；SpringBoard（112,528 B）/ launchd（541,600 B）/ MobilePhone（1,596,528 B）三者 cputype 0x100000c **subtype 0x0（arm64）**（evidence/abi-and-kernel.txt:91-104）。
- iOS 17.7.11/21H461 在 iPhone 上不存在（iPad 专属补丁版）；与 iPadOS 同号的 iPhone 版本是 17.7/21H16（iPhone11,2/11,8/12,1 实测）。

## 2. 问题 ②：电话/短信的依赖集，iPadOS 缺什么

### 2.1 系统卷逐项对比（决定性表）

见 `evidence/telephony-inventory.txt`（本目录，145 行，生成命令在文件头）。要点：

- `/Applications`：iPad 134 个 app、iOS 141 个。**只在 iOS**：MobilePhone.app、ActivityMessagesApp.app、CarPlaySettings/SplashScreen/Wallpaper、HealthPrivacyService、Jellyfish、RemotePaymentPassActionsService、SleepLockScreen、SleepWidgetContainer（:14-24）。**只在 iPadOS**：Greenfield-iPad、LoginUI、PassbookStub（:26-29）——无一与电话相关。
- MobilePhone.app：iPad 计数 0，iOS 115 个条目（:31-96）；iPadOS 只保留无障碍插件 `AccessibilityBundles/MobilePhone.axbundle`（两侧都 =1，:130）。
- 框架层 23 项（CallKit、CoreTelephony、TelephonyUtilities/UI/Preferences/XPCClient/XPCServer、IPTelephony、CorePhoneNumbers、PhoneNumbers、PhoneNumberResolver、CallHistory、ChatKit、IMCore、IMDPersistence、IMDaemonCore、IMSharedUtilities、IMDMessageServices、AppleBasebandManager、AppleBasebandServices、VisualVoicemail、CommunicationsSetupUI、BluetoothManager）**两侧全部 =1**（:97-120）。
- 服务 app（MobileSMS、InCallService、MessagesViewService、PeopleMessageService、PeopleViewService、DataActivation、FieldTest、CTCarrierSpaceAuth、SIMSetupUIService）**两侧全部 =1**（:121-129）。
- LaunchDaemon 六个电话相关 plist 两侧全部 =1（:133-138）；daemon 总数 iPad 477 / iOS 491（:139）。
- Carrier Bundles：iPad 3,046 条（根 = iPad/）vs iOS 7,140 条（根 = iPhone/）（:141-145）——这是最大的内容差异，但只影响运营商配置文件数量，不影响能力。

### 2.2 Mach-O 级验证：MobilePhone.app 在 iPadOS 卷上不缺链接依赖

从 iPhone 卷解出 `Applications/MobilePhone.app/MobilePhone`（1,662,496 B，arm64e PTRAUTH_ABI，evidence/abi-and-kernel.txt:36），其 LC_LOAD_DYLIB 依赖 44 个；用带 .framework 后缀的精确路径在 **iPadOS 卷清单**里逐条查，44 个全部存在（AVFAudio/SwiftUI/Combine/CorePhoneNumbers/SettingsCellular/ConversationKit/BackBoardServices/SpringBoardServices/AVFoundation/Contacts(UI)/CoreFoundation/CoreGraphics/CoreMedia/CoreServices/Foundation/IOKit/MediaPlayer/QuartzCore/UIKit/UserNotifications/SoftLinking + MobileKeyBag/MapsUI/PhoneNumbers/Speech/TipKit/LinkPresentation/IdentityLookup(UI)/BiomeStreams/AppSupport(UI)/CallHistory/Celestial/CommonUtilities/OnBoardingKit/FrontBoardServices/IDS/TelephonyUI/TelephonyUtilities/VisualVoicemail/CoreTelephony）。教训：比对时必须给依赖名补 `System/Library/(Private)?Frameworks/<name>.framework` 路径再查清单，否则得到全缺的假阴性。

MobilePhone.app/Info.plist（解出实测）：CFBundleIdentifier = com.apple.mobilephone、**SBAppTags = ['any-telephony']**、UIDeviceFamily = [1]（iPhone）、UIRequiredDeviceCapabilities = ['arm64']、MinimumOSVersion 16.6 —— 即 SpringBoard 的电话门控由 app tag + device family 决定，与卷里框架无关。

### 2.3 内核基带族（C3）

evidence/abi-and-kernel.txt:55-64（三份解压内核 strings 计数）：

| 符号族 | iPadOS 20G81 | iPhone11 20G81 | iPhone10,6 (A11) 20G81 | 含义 |
| --- | --- | --- | --- | --- |
| qrtr | 0 | 0 | 0 | **没有任何 Apple 内核带 QRTR** |
| QMIBaseband | 0 | 0 | 0 | 无 QMI 栈 |
| AppleConvergedIPC | 3 | 452 | 4 | iPhone11 走 Intel ICE 的 ConvergedIPC |
| AppleBasebandPCI | 387 | 5 | 533 | iPad7 与 A11 走 PCIe 基带（Qualcomm/Intel PCIe 卡） |
| AppleBasebandN71 / I19 | 8 / 0 | 0 / 14 | 5 / 0 | 各自的机型专属族 |

⇒ Apple 的基带驱动是**机型绑定的 PCIe/专有 IPC 驱动**；K60 的 modem 是 SM8475 PAS 远程处理器 + QMI/QRTR（k60-cellular/01-ANDROID-INVENTORY.md:15-22「modem_a=sde7 380 MiB、36 个 QMI 服务」、:92-130「modem 不是外设，是 PAS 远程处理器」）。上游为此准备了 QcomBaseband 组件（components.toml:563-581：QMUX/QRTR + IPA v4.2，os_abi 对 ipados-17.7.11-21H461 AppleBaseband IOUserClient，board_dependencies 含 GLINK/QRTR/rmtfs，**verified_devices = []**），本线 board.toml:14 components.include 不含它。**换 OS profile 不触碰这一层**。

## 3. 问题 ③：Data 卷格式差异

见 `evidence/data-volume.txt`（33 行）。private/var 顶层 28 项、mobile/Library 子项**两侧零差异**（:4-11）；SMS/CallHistory/手机偏好库两侧都不在系统卷（首启由 daemon 创建，:13-17）；wireless/baseband_data、msgs/bounds、protected/trustd 等种子锚点两侧都有（:19-27）。

- Data 种子管线（make-data-seed.py:40 复制 OS 卷 private/var；k60-make-data-seed.py:110-116 --profile 默认 ipados-16.6.1-20G81/profile.toml 且 darwin-only）**对 iOS 卷同样适用**，只需 --profile 指向 iOS profile。
- 唯一要改的是卷身份：board.toml:219 [payload.adt] root_match_volume_uuid（现指向 iPad 卷 C5DAF029…，三卷 UUID 实测见 evidence/abi-and-kernel.txt:10、:23、:94）与 configs/mondrian_defconfig:54 CONFIG_XNU_OWNER_DATA_VOLUME_UUID（PONG APFS window media uuid，首启后由内核侧接管，与 OS 卷 UUID 无关——但仍需按 userdata 重建流程复核）。
- 容量：iPad OS+SystemOS 6.44 GiB、iOS 7.28 GiB，userdata 窗口 454.26 GiB（scripts/build-userdata.py:19-21 FIRST_LBA=0x413248、LAST_LBA=0x75A40EA）——**容量不是卡点**。

## 4. 问题 ④：换 iOS 需要哪几步、证据来源、预计风险、哪一步卡死

### 4.1 步骤表

| 步 | 内容 | 证据来源（file:line / URL） | 预计风险 |
| --- | --- | --- | --- |
| S1 | 选机型：arm64 → A11（iPhone10,1/10,3/10,6, d2xxap）；arm64e → iPhone12,1 或任意 A12+ | api.ipsw.me 设备表（本报告 §1.4）；evidence/abi-and-kernel.txt:28-33、:50-53 | 低。arm64e 要连 profiles/arch/arm64e 一起换（§1.3），构建基座变化大 |
| S2 | 写 profiles/os/ios-16.6.1-20G81/（profile.toml + configs/ios.config + patches/xnu/series），字段值按 §1.2 表 | 模板 = ipados-16.6.1-20G81/profile.toml 全文；BuildManifest identity（/tmp/ev/BuildManifest.plist 已解出）；profiles.py:19-27 证明目录名可直接选中 | 中。prelink roots 33 项按 iPad 20G81 kernelcache 调出（profile.toml:33），iPhone 内核的组件集合不同，roots/slide/early_security_init 要重调 |
| S3 | board.toml os_profile 切换 + [payload.adt] 身份（model/target-type/compatible/product-id/idiom/display-scale/root_match_volume_uuid） | board.toml:7（os_profile）、:218-219（chip_id / root_match_volume_uuid）；profile.toml:54-57、:88、:96、:108；make-pong-adt.py:150-174 | 中。product-id 必须查 libMobileGestalt 产品表（profile.toml:105-106 注释），填错=音频路由等全部退化 |
| S4 | [ipsw] 五元组换 iPhone 值 + [ipsw.sha256] pin | ipsw.py:100-102（无 [ipsw] 直接报错）、:121-128（版本/product/DeviceClass/ApChipID/ApBoardID 四重校验）、:141-168（sidecar + sha256 pin） | 低。纯数据，BuildManifest 已解出（iPhone12,1 ApChipID 0x8030/ApBoardID 0x04；A11 ApChipID 0x8015/ApBoardID 0x0E） |
| S5 | 构建链路径去硬编码：build-strict.sh:68 `M=$OUT/mondrian/ipados-16.6.1-20G81/mondrian`；check-build-env.py:27、check-config-consistency.py:28 的 K60_SDK_RELATIVE；k60-make-data-seed.py:110 --profile 默认值 | build-strict.sh:66-70 实读；scripts/check-*.py 实读 | 低-中。7 处字符串替换，漏一处=gate 报 stale/missing |
| S6 | prelink 重调：kernelcache_sha256 换 iPhone/A11 内核；slide 重推（autoslide 依赖 native 段表）；early_security_init 若 iPhone 内核要求则补 | kernel.py:192-224（pin 校验 :204-206）；emit_prelink_autoslide.py（K60 __DATA 0x150000 vs 20G81 0xb0000 的教训） | **高**。iPhone 内核是 arm64e（subtype 0x2，abi-and-kernel.txt:52）——K60 内核 arm64 与 arm64e kernelcache **不能混装**（prelink 组件 ABI 必须一致）；A11 内核是 arm64（:53）才与 K60 内核同类 |
| S7 | Data 种子重建（macOS 步骤）+ userdata 重建（Linux 可做，udif.py 支持 LZFSE/zlib/bzip2） | k60-make-data-seed.py:116（darwin-only）；scripts/unixnu/userdata.py:47-103（非 Darwin 走 udif）；docs/plans/DOCS-CORE-ALL.md:135/:144 | 低。流程不变，仅输入换 iOS 的 OS/SystemOS dmg |
| S8 | 电话功能验证（上机） | —— | **卡死点：与本报告范围无关的 QcomBaseband/modem 链**（C3/C7）。换 iOS 不推进它 |

### 4.2 哪一步会卡死

1. **S6（prelink/ABI）是第一道真正的硬卡点**：iPhone12,1 的 16.6.1 用户态与内核全是 arm64e（evidence/abi-and-kernel.txt:29-36、:52），K60 主线内核是 arm64（kernel.macho subtype 0x0）。arm64e 用户态要配 arm64e 内核，等于把 profiles/arch 从 arm64 换成 arm64e（无 SoftwareAES、series 只两层）+ K60 全部设备 patch 在 arm64e 基座重验。**绕法：选 A11 的 iOS 16.6.1**——已实测 A11 的 OS 卷与内核都是 arm64（SpringBoard/launchd/MobilePhone subtype 0x0、内核 thin slice 0x0，evidence/abi-and-kernel.txt:91-104），S6 的 ABI 部分因此解除，剩下的是 prelink roots/slide 重调。
2. **S2/S6 的 prelink 工程量是持续性成本**：33 个 roots 是对着 iPad kernelcache 调出来的（profile.toml:33），iPhone kernelcache 的 kext 集不同（AppleBasebandI19 vs N71 等），emit_prelink 的组件地址、Libm 浮点表豁免、autoslide 都要重新核对——不是一次性的数据改写。
3. **「能打电话」在这条线的任何 OS profile 上都卡在同一处**：modem PAS + GLINK/QRTR + QcomBaseband（verified_devices=[]，components.toml:575）。这不是换 profile 能解锁的，也不是本报告能给出工作量的（k60-cellular 线在做）。
4. **不存在「没有 iOS IPSW」的卡点**（C5）；也不存在 Data 卷差异卡点（C6）。

### 4.3 建议路线（若仍要换）

- **推荐变体：iOS 16.6.1 (20G81) @ iPhone10,6 (D221AP/A11)**——唯一同时满足「iPhone 电话身份 + arm64 ABI + 官方 IPSW 可下」的组合。先在 `unixnu status --os ios-16.6.1-20G81`（cli.py:23 --os）下试解析，再决定是否落盘 profile。
- 换完后**预期获得**：MobilePhone.app 可启动（依赖全在，:2.2）；**预期不获得**：拨号能力（无基带驱动）、运营商配置生效（无 CommCenter 后端数据源）。
- 不推荐 iPhone12,1/12,x 变体（arm64e）作为第一步：它同时引入 arch 层切换与 prelink 全量重调，失败面大。

## 5. 方法与可复现性

- 卷清单：`7z l -ba -slt <OS.dmg 或 os.raw>`（7-Zip 23.01，WSL）；iPhone12,1 卷 /tmp/ios_list.txt（7,555,320 行）、iPad 卷 /tmp/os_list.txt（6,776,328 行）、A11 卷 /tmp/a11_os_list.txt。
- 二进制头：`python3 -c struct.unpack_from('<III', …, 4)`（evidence/abi-and-kernel.txt 全部数字可由文件头命令复现）。
- IPSW 成员：自写 zip64 远端读取器（tmp/ipsw_man3.py 模式：尾 4 MiB 找 PK 06 07 → 中央目录 → Range 读成员；**教训：只看 400 KB 尾块或前 8 MiB 都会 entry not found**）。
- kernelcache 解包：IM4P 容器（hdr_len 大端在 IM4P+4）内 bvx2 载荷用 py-lzfse 解；fat 头 0xcafebabe 解析 slice。
- 本目录 evidence/*.txt 全部由脚本生成（生成命令在文件头注释），日期 2026-11-14。
