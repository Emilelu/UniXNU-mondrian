# iOS 27 defconfig 差异审计：15 个只-我们 stubbed bundle 的因果

日期：2026-11-21
范围：sheng iPadOS 27.0.1 24A446 与 mondrian iOS 27.0.1 24A446 的 defconfig 差异，以及 build 20 中 15 个只在 mondrian 出现的 stubbed bundle。

## 0. 结论先行

- **这 15 个 bundle 不是 sheng-only 配置键打开的子系统。** build 20 的 `kernel.json` 里，134 个 unique 未解析/被重定向 target 的 `owner()` 全部是 `com.apple.kernel`；bundle 只是引用者。见 §3。
- **12 个 sheng-only 键没有一条通过 `bsd/conf/` 或 `osfmk/conf/` 增删源文件。** `grep -rn CONFIG_XNU_ bsd/conf osfmk/conf` 在 27 树 `.cache/xnu-work` 零命中；C 宏消费点只在 `bsd/kern/kern_exec.c`、`bsd/kern/bsd_init.c` 与 `iokit/bsddev/IOKitBSDInit.cpp`。见 §2。
- **sheng 的 policy 与我们的 `kernel.json` 不是同一个 kernelcache。** sheng policy 的 kernelcache sha 是 `38e6d9fa...`，地址基 `0xfffffe00...`；我们的是 `fa07057b...`，地址基 `0xfffffff0...`。24 vs 205、10 vs 25 不能直接归因于 defconfig。见 §4。
- **不能靠这 12 个键关闭 `prelink-map-unresolved`。** 它们最多改变 native 镜像的启动策略、链接 archive 或表布局；不定义原 kernel 的 134 个 target。若打开后 stubbed 数量变了，先当作 matcher/镜像形状变化重新测量，不能当作“补齐了符号”。见 §5、§6。
- **值得先试的三个键是 storage parity 三键，不是 prelink 修复。** `SOURCE_STORAGE=y`、`EXTRA_LD_ARCHIVES=...libShengSourceStorage.a`、`SOURCE_STORAGE_TABLES="userdata"` 是 12 键里唯一自洽、可独立观察的一组；预期只增加 NativeUfs/SourceStorage 等驱动符号，不减少 134 个原始 target。见 §7。

## 1. 输入与口径

| 输入 | 路径 | 关键值 |
|---|---|---|
| sheng defconfig | `/mnt/e/hackios/UniXNU-sheng/configs/sheng_ipados27_defconfig` | 22 行，19 个 `CONFIG_` 键 |
| mondrian defconfig | `/mnt/e/hackios/k60-gates/configs/mondrian_ios27_defconfig` | 25 行，8 个 `CONFIG_` 键 |
| sheng prelink policy | `/mnt/e/hackios/UniXNU/scripts/policies/ipados-27.0.1-24A446/prelink-regression.json` | kernelcache `38e6d9fa...`; missing 2; stubbed 24 |
| our build 20 report | `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json` | candidate 93,061,120 B `dee01c54...`; kernelcache `fa07057b...` |
| our roots | `/mnt/e/hackios/UniXNU/profiles/os/ios-27.0.1-24A446/profile.toml:43` | 30 roots |
| sheng roots | `/mnt/e/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml:41` | 31 roots，只多 `com.apple.iokit.IOHIDEventDriver` |

路径约定：本文的 `bsd/...`、`osfmk/...`、`iokit/...`、`security/...`、`config/...` 都是 27 树 `.cache/xnu-work` 的相对路径；`build-xnu-4k-baseline.sh` 与 `build-sheng-source-storage.py` 指 `/mnt/e/hackios/UniXNU/scripts/` 下的脚本。

口径说明：

- `stubbed` 的键是 **target 地址**，不是调用点地址。`fileset_emit.py` 的 `rebind(target, site)` 在 `pairs` 找不到 target 时执行 `self.missing[self.owner(site)][target] += 1`，所以 `kernel.json` 的 owner 是引用者 bundle，target 是原 kernel 里的地址。
- `missing` 是保留原地址、没有被重定向的引用；`stubbed` 是被改写到 `_unixnu_fileset_unmapped` 的引用。两者都说明 target 在 `kernel.map.json` 里没有配对，不是“bundle 没有被编译”。
- 本文件使用 2026-11-21 直接复算的 `kernel.json`：missing 3 items / 3 unique，stubbed 205 items / 131 unique，合计 208 items / 134 unique。`/mnt/e/hackios/k60-gates/docs/engineering/IOS27-FLIGHT-BLOCKERS.toml:31` 写的是 “203 items”，那是同一轮 blocker 文本的另一个计数口径/快照；本文不拿 203 或旧文档的 150 做推导，两个数都不改变“target 全在原 kernel”的结论。

## 2. 逐键对比与编译落点

### 2.1 五个两边相同的键（不是差异）

`BUILD_ARCHIVES=y`、`CRYPTO_BOOTSTRAP="source"`、`DT_PANIC_REGION=y`、`ARMVIRT_PLATFORM=n`、`KERNEL_CHAINED_FIXUPS=y` 在两边值相同，不解释 15 个 bundle 的差异；列在这里是为了防止把“共同键”误当成“sheng 开了”。

### 2.2 只 sheng 开的 12 个键

先说机制：`CONFIG_XNU_*` **不是** XNU 的 source-config。`E:/hackios/UniXNU/scripts/unixnu/kernel.py:17-26` 的 `xnu_env()` 只把 `XNU_` 前缀变量转成环境变量，并把 `{tree}` 替换为实际树路径；`E:/hackios/UniXNU/scripts/build-xnu-4k-baseline.sh:145-146` 与 `:826-827` 硬编码 `KERNEL_CONFIGS=DEVELOPMENT`。在 27 树 `.cache/xnu-work` 执行：

```sh
grep -rn CONFIG_XNU_ bsd/conf osfmk/conf
# 无输出
```

因此下表的“编译落点”是宏/构建变量的实际消费点，不是 `bsd/conf` 的文件选择。

| 键 | sheng 值 | 我们的值 | 编译落点（file:line） | 可能提供的符号/产物 | 判类 |
|---|---|---|---|---|---|
| `CONFIG_XNU_EXTRA_LD_ARCHIVES` | `-Wl,-force_load,{tree}/build/sheng-source-storage/libShengSourceStorage.a` | 未设 | `build-xnu-4k-baseline.sh:784` 并入 `KERNEL_EXTRA_ARCHIVES`；archive 源见 `scripts/build-sheng-source-storage.py:191-195` | NativeUfs、SourceStorage、NativeRamBlock、SourceRootPolicies、SourceRootBinding、verified_root 等；**不是**原 kernel 的 134 个 target | 链接/镜像语义 |
| `CONFIG_XNU_SOURCE_STORAGE` | `y` | 未设 | `build-xnu-4k-baseline.sh:219,295,305,724` 只作为条件；本身不链接 archive | 打开“需要 archive”的代码路径/校验条件；不单独产生符号 | 运行期/构建条件 |
| `CONFIG_XNU_SOURCE_STORAGE_TABLES` | `"userdata"` | 未设 | `scripts/build-sheng-source-storage.py:115`；`:143-152` 决定用 544 B header 还是完整 manifest | `root-policies.bin` / `VROOTB01` 表布局；不改 C 源文件 | 镜像布局/策略 |
| `CONFIG_XNU_OWNER_ROOT_AUDIT` | `y` | 未设 | `build-xnu-4k-baseline.sh:289-307` 组合校验；`:368` 给 `bsd_init.o_CFLAGS_ADD`；C 消费 `bsd/kern/bsd_init.c:1081,1098,1107,1245,1246` | `native_owner_root_*`（trust_enabled/accepted/apple_autherr/decision/readonly/mount_device/selected_device/checkpoint/...） | 运行期策略 |
| `CONFIG_XNU_OWNER_ROOT_TRUST` | `y` | 未设 | 同上 `:289-307`、`:368`、`bsd_init.c:1081,1098,1107,1245,1246` | 同上 `native_owner_root_*` | 运行期策略 |
| `CONFIG_XNU_NATIVE_RAM_BLOCK` | `y` | 未设 | `build-xnu-4k-baseline.sh:213-224`、`:724`；`:513` 的 `kern_exec.o_CFLAGS_ADD`；C 消费 `bsd/kern/kern_exec.c:7976...9213` | `NativeRamBlock` 类/其 vtable（archive）；`native_owner_data_*` 分支 | 链接/运行期 |
| `CONFIG_XNU_OWNER_CACHE_MOUNT` | `y` | 未设 | `build-xnu-4k-baseline.sh:390-423` 组合校验；`:513` 的 `kern_exec.o_CFLAGS_ADD`；C 消费 `bsd/kern/kern_exec.c:7976...9213` | `native_owner_cache_*`（stage/status/authorized/selected_device/prepare/checkpoint/...） | 运行期策略 |
| `CONFIG_XNU_OWNER_CACHE_STARTUP` | `y` | 未设 | 同上 `:390-423`、`:513` 的 `kern_exec.o_CFLAGS_ADD` | 同上 `native_owner_cache_*` | 运行期策略 |
| `CONFIG_XNU_OWNER_BOOT_MANIFEST` | `y` | 未设 | `:390-423`；`:417` `iokit/bsddev/IOKitBSDInit.cpp:575`；`:513` kern_exec | `native_owner_boot_manifest_status/hash`、`native_owner_publish_boot_manifest` | 运行期策略 |
| `CONFIG_XNU_OWNER_DATA_MOUNT` | `y` | 未设 | `:424-513`；`:513` 的 `kern_exec.o_CFLAGS_ADD` 加 `-include owner-data-volume.h` | `native_owner_data_*`（status/stage/readonly/device/seed_base/seed_size/prepare） | 运行期策略 |
| `CONFIG_XNU_OWNER_UNION_SYSTEMOS` | `y` | 未设 | `:424-513`；`:513` 的 kern_exec | 同 `native_owner_data_*` 的 union 分支 | 运行期策略 |
| `CONFIG_XNU_OWNER_DATA_VOLUME_UUID` | `"2A5E9027-D9E1-40F9-983C-41BD3F1994F5"` | 未设 | `:424-513`；`:513` 的 `-include owner-data-volume.h` | 常量；不产生函数/符号定义 | 运行期策略 |

这张表的共同点：**没有一行落在原 kernel 的 134 个 target 上**。它们产生的是新的 `native_owner_*` 全局/函数、NativeUfs/SourceStorage 类，或者表布局；`kernel.map.json` 的函数配对不会因为出现这些名字而把原 kernel 的 target 配对成功。

### 2.3 两边都有但值相反/我们缺的键

| 键 | sheng | 我们 | 编译落点 | 说明 |
|---|---|---|---|---|
| `CONFIG_XNU_NATIVE_ADRENO` | `y` | `n` | `build-xnu-4k-baseline.sh:650-658` 链 `libAdreno740.a`；`:651` 注释说明 kits 由 `scripts/build-native-adreno-kits.py` 生成 | 加 native GPU 驱动；不提供 IOGPUFamily/IOSurface 的原 Apple 函数 |
| `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` | `y` | `n` | `:374-379` 给 `IOUserClient.cpo_CFLAGS_ADD`；`:368` 的 bsd_init | 显示/AV 的 native 路径；不是 AppleM2ScalerCSCDriver 的原函数 |
| `CONFIG_XNU_NATIVE_UFS` | 27 无此键 | `n` | `:90-94` boot progress 前置条件、`:226-228` `PERSONALITY_CFLAGS`、`:644-648` 链 `libPongUfs.a` | storage 线；与 sheng 的 SOURCE_STORAGE 不是同一机制 |

这三键值得做对照构建，但它们不在“只 sheng 开”的 12 键里。把 15 个 bundle 归因于它们同样是错的：它们加的是 native 驱动，不是原 kernel 函数。

### 2.4 roots 不是差异来源

- 我们的 roots：`/mnt/e/hackios/UniXNU/profiles/os/ios-27.0.1-24A446/profile.toml:43`，30 个。
- sheng roots：`/mnt/e/hackios/UniXNU/profiles/os/ipados-27.0.1-24A446/profile.toml:41`，31 个。
- 两者只差 `com.apple.iokit.IOHIDEventDriver`；`ios-27.../profile.toml:41-42` 的注释说明 iPad roots 去掉这一项，因为 iPhone17,2 fileset 没有它。
- build 20 的 closure 是 38 项，25 个 stubbed bundle 都在 closure 里；15 个“只我们有”的 bundle 并不是因为我们多选了 roots。

## 3. 15 个只-我们 stubbed bundle 的真实身份

用原 kit 复算：在 `/opt/k60/trees/ios27-fw/kits/XnuPrelink` 里导入 `kc_image.Image` 与 `fileset_emit.Emit, rebase_collection`，按 `rebase_collection(cache, native.base, set(J["closure"]), {}, set(J["closure"]))` 后构造 `Emit`，对 134 个 target 逐个调用 `emit.owner(a)` 与 `emit.mapped(a)`：

- `slide = 0x0`；
- 134/134 的 owner 都是 `com.apple.kernel`；
- 134/134 都在 `old_ranges` 里（`emit.mapped(a)` 为真）；
- 因此 target 是 rebase 后的原 kernel 地址，`kernel.json` 里的 bundle 名是**引用者**。

按 rebase 后的段分布：

| 段 | unique target 数 | 说明 |
|---|---:|---|
| `__TEXT_EXEC` | 129 | 原 kernel 代码 |
| `__TEXT_BOOT_EXEC` | 2 | 原 kernel 启动代码 |
| `__DATA` | 2 | 原 kernel 数据地址：`0xfffffff00b72fce8`、`0xfffffff00b739538` |
| `__PRELINK_TEXT` | 1 | `0xfffffff007044478`，读出 16 个 0，不是函数起点 |
| 合计 | 134 | 131 个是原 kernel 的 function start，3 个不是 |

> 段名注：`0xfffffff007044478` 在 `/mnt/e/hackios/k60-gates/docs/engineering/IOS27-FLIGHT-BLOCKERS.toml:29` 里写作 `__TEXT,__const` 的 leaf；上表按 rebase 后 `Emit` 视图归到 `__PRELINK_TEXT`。地址、16 个 0、非 function start 三者一致，段名差异不影响“target 全在原 kernel”的结论。

原 kernel `old.function_starts()` 有 21,692 个；134 个 target 中 131 个落在这 21,692 个起点上。原 kernel 的 `old.symbols()` 为 0，所以不能从原 kernel 直接取名；`__LINKINFO,__symbolsets` 只有 9 个 KPI 集合的名字，不含地址。不要用首指令指纹猜名字：此前试过 131/134，约 52 个弱命中且大量假阳性（例如把 `_filt_fsprocess`、`_mptcp_disconnect` 配到无关函数），该路径已放弃。

### 3.1 25 个 stubbed owner 与 15 个只-我们

| bundle | stubbed items | 备注 |
|---|---:|---|
| AppleFSCompression | 1 | 只我们 |
| AppleEffaceableStorage | 2 | 只我们 |
| AppleIISController | 2 | 只我们 |
| AppleM2ScalerCSCDriver | 4 | 只我们 |
| AppleMobileFileIntegrity | 41 | 只我们 |
| IODARTFamily | 1 | 只我们 |
| apfs | 20 | 只我们 |
| CoreAnalyticsFamily | 3 | 只我们 |
| IOAVFamily | 16 | 只我们 |
| IOAudio2Family | 1 | 只我们 |
| IOHDCPFamily | 2 | 只我们 |
| IOMobileGraphicsFamily | 1 | 只我们 |
| IOReportFamily | 1 | 只我们 |
| kec.corecrypto | 3 | 只我们 |
| security.sandbox | 23 | 只我们；另 1 个 missing 也在它名下 |
| AppleARMPlatform | 17 | 两边都有 |
| AppleARMWatchdogTimer | 6 | 两边都有；另 1 个 missing |
| ApplePMGR | 7 | 两边都有 |
| IOCryptoAcceleratorFamily | 2 | 两边都有 |
| IOGPUFamily | 10 | 两边都有 |
| IOHIDFamily | 14 | 两边都有；另 1 个 missing |
| IOStorageFamily | 5 | 两边都有 |
| IOSurface | 9 | 两边都有 |
| AppleImage4 | 7 | 两边都有 |
| Image4 | 7 | 两边都有 |
| **合计** | **205** | 15 个只-我们 = 121 items；10 个两边都有 = 84 items |

缺失的 3 个 target：AppleARMWatchdogTimer 1、IOHIDFamily 1、security.sandbox 1。加上 missing 后总 items 208；security.sandbox 是唯一同时有 missing 和 stubbed 的只-我们 bundle。

32 个 target 被多个 bundle 引用，最多 11 个：

- `0xfffffff00abe3554` 被 AppleFSCompression、AppleARMPlatform、AppleARMWatchdogTimer、AppleIISController、AppleMobileFileIntegrity、apfs、IOCryptoAcceleratorFamily、IOGPUFamily、IOHDCPFamily、IOSurface、security.sandbox 引用；
- `0xfffffff00b36e788` 与 `0xfffffff00ab86b04` 各被 7 个 bundle 引用。

这解释了一个现象：一个原 kernel 函数没有配对，会在多个 bundle 里同时出现；bundle 数量不能当作“多个子系统被关掉”的证据。

## 4. sheng policy 不是同一输入的对照组

`/mnt/e/hackios/UniXNU/scripts/policies/ipados-27.0.1-24A446/prelink-regression.json`：

- `kernelcache_sha256 = 38e6d9fa5f789b8228f4617ef4c6d2a3fd8ab564abdc9b62920f1db53fc1780a`；
- 地址形态 `0xfffffe00...`（iPad 的 kernelcache）；
- missing 2：AppleARMWatchdogTimer `0xfffffe00070446a8`、IOHIDFamily `0xfffffe000b8b3ce8`；
- stubbed 24：AppleARMPlatform 7、AppleARMWatchdogTimer 2、ApplePMGR 2、IOCryptoAcceleratorFamily 1、IOGPUFamily 1、IOHIDFamily 3、IOStorageFamily 2、IOSurface 1、AppleImage4 1、Image4 4；
- `required_original_branches`：`__ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass`、`__ZN11IOHIDDevice10handleOpenEP9IOServicejPv`。

我们的 build 20：

- `kernelcache_sha256 = fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`；
- 地址形态 `0xfffffff0...`（iPhone17,2 / D94AP 的 kernelcache）；
- missing 3 / stubbed 205 / 134 unique。

这不是同一个 kernelcache，也不是同一个 native build。**24 vs 205、10 vs 25 不能直接归因于 defconfig**；要做真正的同输入比较，需要 sheng 那一侧的 native kernel 与 `kernel.json`（相同的 kernelcache sha、相同的 native build、相同的 matcher 版本），目前没有这个产物。`prelink-regression.json` 只能作为“sheng 的已知残差”参考，不能当对照实验。

## 5. 每键判类：为什么没有一条能减少 134 个 target

把 12 键按结果分成三类：

### 5.1 只改运行期策略（8 键）

`OWNER_ROOT_AUDIT`、`OWNER_ROOT_TRUST`、`OWNER_CACHE_MOUNT`、`OWNER_CACHE_STARTUP`、`OWNER_BOOT_MANIFEST`、`OWNER_DATA_MOUNT`、`OWNER_UNION_SYSTEMOS`、`OWNER_DATA_VOLUME_UUID`。

- 消费点只在 `bsd/kern/bsd_init.c:1081,1098,1107,1245,1246`、`bsd/kern/kern_exec.c:7976...9213`、`iokit/bsddev/IOKitBSDInit.cpp:575`；
- 提供的是 `native_owner_root_*`、`native_owner_cache_*`、`native_owner_data_*`、`native_owner_boot_manifest_*` 这些新符号；
- 这些符号不是原 kernel 的 134 个 target 的同名定义，不会让 `kernel.map.json` 多出配对。

### 5.2 改链接/镜像布局（3 键 + 1 个常量）

`EXTRA_LD_ARCHIVES`、`SOURCE_STORAGE`、`SOURCE_STORAGE_TABLES`、`NATIVE_RAM_BLOCK`。

- `EXTRA_LD_ARCHIVES` 是唯一真的把 `libShengSourceStorage.a` 链进内核的键；`NATIVE_RAM_BLOCK=1` 且 `SOURCE_STORAGE=1` 时 `build-xnu-4k-baseline.sh:724` 不会单独链 `libRamBlock.a`（archive 里已包含）；
- archive 的源是 `scripts/build-sheng-source-storage.py:191-195`：NativeUfs.cpp、NativeRamBlock.cpp、SourceStorage.cpp、SourceRootPolicies.cpp、SourceRootBinding.cpp、BootLog.c、BootLogDefaults.c、BootReset.c、verified_root.c、xnu_crypto.c、anchor（27 另加 BootProcess 等）；
- 这些是 I/O Kit 存储驱动与启动策略，不是 AMFI/sandbox/apfs/IOGPU 的原 kernel 函数；
- 可能改变 native 符号集合与镜像布局，但不能“定义”原 kernel 的 target。若 stubbed 数变化，优先解释为 matcher 对新 native 形状的重新配对，而不是补齐。

### 5.3 不产生任何 C 符号（`OWNER_DATA_VOLUME_UUID`）

只生成 `owner-data-volume.h` 里的常量，供 `kern_exec.o` 的 `-include` 使用；不可能减少 unresolved。

## 6. 不可能靠这 12 个键解决的 bundle

下面按 build 20 的 205 个 stubbed items 分类。数字是 items，不是 unique target；一个 target 可被多个 bundle 引用，所以分类和总数不能相加成“函数个数”。

### 6.1 GPU/显示：24 items

`IOGPUFamily` 10、`IOSurface` 9、`AppleM2ScalerCSCDriver` 4、`IOMobileGraphicsFamily` 1。

- 这些属于 GPU/显示线；board 的 27 defconfig 明确 `NATIVE_ADRENO=n`、`NATIVE_LEGACY_DISPLAY=n`（`/mnt/e/hackios/k60-gates/configs/mondrian_ios27_defconfig:21-22`）。
- 打开这两个 native 键只会加入 Adreno/legacy display 的 native 代码，不会提供 IOGPUFamily/IOSurface 原 Apple 函数的定义；不能把“开 native GPU”当成“补 prelink”。
- 这条线应按 GPU/显示的分工单独审计，不应为了 stubbed 数去打开。

### 6.2 安全/存储核心：112 items

`AppleMobileFileIntegrity` 41、`security.sandbox` 23（另 1 missing）、`apfs` 20、`AppleImage4` 7、`Image4` 7、`kec.corecrypto` 3、`IOCryptoAcceleratorFamily` 2、`AppleEffaceableStorage` 2、`AppleFSCompression` 1、`IODARTFamily` 1、`IOStorageFamily` 5。

- 这些 bundle 的未解析 target 全在原 kernel；12 键的消费点没有一条落在它们的原始函数定义上。
- MACF 的源码选择来自 XNU 的 `config/MASTER:569`（`options CONFIG_MACF`）与 `security/conf/files:10-29`（`optional config_macf`），不是 `CONFIG_XNU_OWNER_*`；把 `OWNER_ROOT_TRUST` 打开不会让 AMFI/sandbox 的原函数出现。
- 要推进，必须做符号级审计：查这些 target 在原 kernel 的调用者、native 侧是否有等价实现、补丁是否改了函数边界；不能靠打开 sheng 的 OWNER/SOURCE 键。

### 6.3 平台/AV/输入：69 items

`AppleARMPlatform` 17、`ApplePMGR` 7、`AppleARMWatchdogTimer` 6、`IOHIDFamily` 14、`IOAVFamily` 16、`IOAudio2Family` 1、`IOHDCPFamily` 2、`CoreAnalyticsFamily` 3、`IOReportFamily` 1、`AppleIISController` 2。

- 这些是平台、电源、输入、AV、分析类；与 12 键没有直接的“键 → 缺失符号”链路。
- 其中 `IOHIDFamily`、`AppleARMPlatform`、`ApplePMGR` 是两边都有的 bundle；它们在我们的输入里引用数更高，可能是 kernelcache 差异、matcher 差异或补丁差异，不能归因于 sheng-only 键。
- 需要逐 target 的调用点/可达性审计；在此之前，不为它们打开任何全局 OWNER 键。

**结论：** 25 个 bundle 里没有一个是因为“sheng 开了某个 CONFIG，我们关了”而整体缺失；15 个只-我们 bundle 是同一批原 kernel target 的不同引用者。配置差异可以解释启动策略/存储路径的差异，不能解释 prelink 的 134 个 target。

## 7. 值得先试的三个键（以及为什么不是 prelink 修复）

如果只能从这 12 个键里挑三个做一次对照构建，选：

1. `CONFIG_XNU_SOURCE_STORAGE=y` — 打开 storage 条件；
2. `CONFIG_XNU_EXTRA_LD_ARCHIVES="-Wl,-force_load,{tree}/build/sheng-source-storage/libShengSourceStorage.a"` — 真正把 archive 链进来；没有它，第 1 项单独不会产生 archive 符号（archive 只在 `build-xnu-4k-baseline.sh:784` 进入链接）；
3. `CONFIG_XNU_SOURCE_STORAGE_TABLES="userdata"` — 选择 544 B header 还是完整 manifest（`build-sheng-source-storage.py:115,143-152`）。

注意：`build-xnu-4k-baseline.sh` 没有调用 `build-sheng-source-storage.py`；它只在 `:784` 接收一个已存在的 archive 路径。三键实验前必须先由 sheng 的构建流水线生成 `libShengSourceStorage.a`（`build-sheng-source-storage.py:238-240`），否则 `-force_load` 会指向缺失文件。

预期：

- 增加 NativeUfs/SourceStorage/SourceRootPolicies/VerifiedRoot 等符号；
- 可能改变 boot image 的表布局与大小；
- **不预期减少 134 个原 kernel target**；如果 stubbed 数变化，先按 §5.2 解释为 matcher 重新配对，并记录 before/after 的 `kernel.json` 与 `kernel.map.json`。

不先试 `OWNER_DATA_MOUNT` 的原因：它需要 `OWNER_BOOT_MANIFEST`、`OWNER_CACHE_STARTUP`、`OWNER_ROOT_TRUST` 等组合校验（`build-xnu-4k-baseline.sh:390-423`、`:424-513`），一开就是 6 键链；在只想知道“archive 是否改变 native 符号集合”时，它把变量搅在一起。

如果目标真的是减少 stubbed，12 键里没有合格候选；应先做的是 §3 的 target 归属与 §6 的符号级审计，以及 `NATIVE_ADRENO`/`NATIVE_LEGACY_DISPLAY`/`NATIVE_UFS` 的独立对照（它们不在“只 sheng 开”的表里）。

## 8. 复现命令

```sh
# 1) 两份 defconfig 的键
grep -n '^CONFIG_' /mnt/e/hackios/UniXNU-sheng/configs/sheng_ipados27_defconfig
grep -n '^CONFIG_' /mnt/e/hackios/k60-gates/configs/mondrian_ios27_defconfig

# 2) 证明 CONFIG_XNU_ 不选源文件（在 27 树 .cache/xnu-work 内）
grep -rn CONFIG_XNU_ bsd/conf osfmk/conf

# 3) 读 build 20 的 kernel.json（root-only）
sudo python3 - <<'PY'
import json
p='/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json'
j=json.load(open(p))
print(j['inputs']['kernelcache_sha256'])
print('missing', sum(len(v) for v in j['missing'].values()), 'owners', len(j['missing']))
print('stubbed', sum(len(v) for v in j['stubbed'].values()), 'owners', len(j['stubbed']))
print('unique', len({a for v in j['stubbed'].values() for a in v} | {a for v in j['missing'].values() for a in v}))
PY

# 4) 原 kit 的 owner()/mapped() 复算（在 /opt/k60/trees/ios27-fw/kits/XnuPrelink）
#    见本文件 §3；脚本不要在共享树里留文件。
```

## 9. 对 m44296 的交付

- 分支：`feat/cellular-k55`；本文提交后 tip 以 `git rev-parse HEAD` 为准。
- 三行摘要：
  1. 12 个 sheng-only 键没有一条通过 `bsd/conf`/`osfmk/conf` 增删源文件；它们只改 `kern_exec.c`/`bsd_init.c`/`IOKitBSDInit.cpp` 的宏分支或链 storage archive。
  2. 15 个只-我们 bundle 是 134 个原 kernel target 的引用者，target 的 owner 全是 `com.apple.kernel`；sheng policy 与我们的 kernelcache sha/地址基不同，24 vs 205 不可直接归因 defconfig。
  3. 不能靠这 12 键关闭 `prelink-map-unresolved`；先试的三键是 storage parity 三键，预期不减少 stub；GPU/显示 bundle 另线解决。
- 仍缺：同输入的 sheng native kernel/`kernel.json`（用于真正的 24 vs 205 对照）；27 树的 data-mount 锚点（0629 仍不能 apply）；0626–0630 进 27 设备仓的 `series`；`prelink-map-unresolved` 仍 open。
