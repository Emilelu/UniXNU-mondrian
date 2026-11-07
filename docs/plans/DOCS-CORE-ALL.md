# DOCS-CORE-ALL — UniXNU 核心文档全量研读（26/26）

> 研读对象：`E:/hackios/UniXNU/docs/{concepts,guide,reference,xnu}` 下全部 26 篇 Markdown。
> 研读方式：逐文件全文读取（`read` 全文，无抽样、无截断；含仅作重定向的 `guide/overview.md`）。文中 `docs/...:line` 均指 `E:/hackios/UniXNU` 主仓路径。
> K60 基线：`E:/hackios/UniXNU-mondrian`，分支 `fix/k60-measured-high-window`，HEAD `9b4fec1`；`board.toml` 为 `schema_version = 2`（format 2）。
> 生成日期：2026-11-08。

## 0. 结论速览

1. **26/26 全部读完**：concepts 5、guide 8、reference 9、xnu 4，逐篇摘要见 §1，覆盖清单见 §3。
2. **boot-args 581 字符不超限**：文档硬限是“拼接后的命令行 ≤1000 字节”，DarwinBoot 再复制进 1024 字节缓冲。581 个 ASCII 字符 = 581 字节，距 1000 字节余 **419 字节**；距 1024 字节缓冲余 **443 字节**（按 C 字符串保留 1 字节 NUL 则余 442 字节）。前提是每个 token 都符合 `[A-Za-z0-9_.-]+(=[A-Za-z0-9_.,-]+)?`，且 581 是最终拼接行（含 `confirm_args`）的字节数。
3. **4K 页表是硬要求**：官方 4K 载体是 `MACHINE_CONFIGS=BCM2837`（`ARM_PGSHIFT=12`、`ARM_PGBYTES=4096`、`TCR_EL1_BOOT TG0=0/TG1=2`）。K60 当前本地构建脚本实际用 `MACHINE_CONFIGS=PONG`（`scripts/build-xnu-4k-baseline.sh:7,234,1109`），必须证明 PONG 与 BCM2837 等价满足 4K 常量，并保留全部 4K 补丁（bootstrap capacity、user ABI、signature hash cache、PGZ、64-bit PA 等）。
4. **补丁顺序是声明顺序，不是文件名排序**：K60 `board.toml:20` 是 format 2 的 `patch_series = ["device:patches/xnu/series"]`；`series` 现有 198 条，`./unixnu status --json` 的 `patch_order` 是唯一权威。依赖补丁必须排在被依赖者之后；任何触碰 `zzy`/`zzz` 区域的补丁必须排在它们之前。
5. **最大跨文档风险**：K60 当前 4.75 GiB 窗口（`board.toml:162`）以及未来 12 GiB 目标，会同时放大 4K bootstrap 页表容量、>4 GiB 物理地址和 4K SMMU 三个问题；文档要求“每个映射 GiB 都预算 bootstrap 页表”，物理地址用 `ptoa()`/`phystokv()`，IOMMU 用 4 KiB 表。

---

## 1. 26 篇逐篇摘要

### 1.1 docs/concepts（5/5）

#### 1.1.1 `docs/concepts/boot-chain.md`（121 行）— 五段启动链与失败回退

**机制**

- 定义 UniXNU 的四次 handoff（正文按五段展开）：bootloader → BootShim → UEFI/UniXNU → DarwinBoot → XNU → userland。每一段有固定输入、校验步骤和失败后返回上一段的失败模式（`:3`）。
- **Bootloader → BootShim**：Android bootloader 读 boot image；kernel 字段是 gzip 流，前半 BootShim、后半 UEFI firmware volume，设备树跟在 gzip 流之后（`:5-7`）。BootShim 按 Mu-Silicium 设备配置的固件 base/size 汇编：示例 `-DFD_BASE=0xA7100000 -DFD_SIZE=0x300000 -DREQUIRES_KERNEL_HEADER=1`（`:11-16`）；需要时包含 ARM64 image header，header 描述 shim + firmware volume，使 bootloader 能按请求地址加载这一对（`:18`）。BootShim 重定位 firmware volume 并进入 UEFI（`:20`）。
- **UEFI → UniXNU**：`UniXNUDxe` 以 `Boot####` 选项注册 `UniXNU.efi`，load option data 为 `unixnu:firmware`；BDS 或固件菜单启动它（`:24`）。Boot manager 先扫描自身卷，再扫描其他卷，找 `\EFI\UniXNU\unixnu.toml`（`:26`）。菜单前固定五步：发布所有 `[[block_slice]]` → 加载并启动所有 `[[driver]]` → 安装所有 ACPI 表 → 合并所有 `[match]` 命中的 kit → 构建菜单（`:28-34`）。
- **UniXNU → DarwinBoot**：`xnu` 类型条目通过 `UNIXNU_LOADER_BOOT_REQUEST` 传递 Volume、KernelPath、BootArgs、DeviceTree、Ramdisk、Kexts 等（`:40-52`）。DTB 准备顺序固定：固件 DTB / 文件 DTB / 无 DTB → 复制并留 64 KiB slack → 全局 patches → entry patches → `[entry.chosen]` 最后 → 安装为 `EFI_DTB_TABLE`（`:54-61`）。
- **DarwinBoot → XNU**：14 步校验/加载（`:67-82`）。硬校验：`MH_MAGIC_64`、`CPU_TYPE_ARM64`、`MH_EXECUTE`、恰好一个 `LC_MAIN`、至少一个 `LC_SEGMENT_64`；入口点位于可执行段；每个 segment 页对齐、不重叠、位于 256 MiB 窗口内；ADT 必读，trustcache 可选；trust cache 校验 header count、offsets、entry count、sorted hashes；读 GOP framebuffer；分配连续物理窗口；复制 segments/ADT/trustcache/ramdisk；构建 `DARWIN_BOOT_ARGS`；退出 boot services；关 MMU/cache；以 EL1 跳入口（`:67-82`）。
- `DARWIN_BOOT_ARGS`（Darwin 23 布局）：`0x00` revision/version/padding；`0x08` virtual base；`0x10` physical base；`0x18` memory size；`0x20` top of kernel data；`0x28` video 六个 64-bit；`0x60` device tree address；`0x68` device tree length；`0x6c` command line，**1024 bytes**；`0x478` memory size actual（`:84-97`）。
- **XNU → userland**：`start.s` 安装 bootstrap 页表，进 C boot path，初始化 platform expert，发布 IOKit registry（`:99-105`）。`ArmDTPlatform` 要求 `/cpus`、`/arm-io`、`/defaults`、`/options` 和 `/chosen` 里的 CHRP NVRAM proxy；发布 CPU nub 和每个 `arm-io` 子节点（`:103`）。存储驱动发布 userdata，分区方案发布 `OS`/`SystemOS`，XNU 按 UUID 匹配根卷、挂载、从所选 userland 启动 `launchd`（`:105`）。
- 失败行为表：bootloader header mismatch → 拒绝镜像留在 bootloader；firmware 无 GOP/无输入 → headless/text；UniXNU 无配置 → 内置配置 + 可移动 loader；DarwinBoot 非法 kernel/ADT/trustcache → `EFI_COMPROMISED_DATA` 并保留固件；XNU 缺 platform/storage driver → panic 并打印缺失 provider（`:107-115`）。

**对 K60 的含义**

- K60 的 boot image 必须按 Mu-Silicium mondrian 配置的 `FD_BASE`/`FD_SIZE` 组装 BootShim；kernel 字段必须是 gzip(BootShim + firmware volume)，DTB 追加在 gzip 之后。
- DarwinBoot 默认窗口 256 MiB；K60 通过 ADT `/chosen/darwinboot-memory-size` 请求 4.75 GiB（当前 `owned_memory_size = 0x130000000`），该占位属性必须存在，否则 DarwinBoot 无法解析。
- 命令行走 `0x6c` 的 1024-byte buffer；这是 boot-args 581 判定的最终硬边界。

#### 1.1.2 `docs/concepts/payload.md`（132 行）— FAT 载荷卷、ADT sidecar 与参数校验

**机制**

- payload 是 Android boot image 的 ramdisk，一个 FAT 卷；UniXNU 从它读配置，DarwinBoot 从它读 kernel、ADT 和可选 trust cache（`:3`）。
- Mu-Silicium initrd payload 必须在 firmware 内嵌 `UniXNURamDiskDxe`、`DiskIoDxe` 和 FAT driver，才能在 UniXNU 读配置前暴露 payload 卷（`:5`）。
- 卷布局固定：`/EFI/UniXNU/unixnu.toml`、`Payloads/kernel.macho`、`kernel.macho.adt`、`kernel.macho.trustcache`（可选）、`scratch-data.img`（`:11-17`）。payload 用 `mformat`/`mcopy` 写卷；时间戳固定 1980-01-01，使同一输入可复现；ADT 含随机 seed，所以两次 payload 构建结果不同（`:19`）。
- 生成的 `unixnu.toml` 示例：`[boot] timeout=3/default="xnu"`、`[kits] autoload=false`、`[[entry]] type="xnu" path="Payloads/kernel.macho" initrd="Payloads/scratch-data.img" args="-v serial=3"`（`:25-42`）。`args` 是 `[payload] kernel_args` 与 `--kernel-arg` 拼接后的结果（`:44`）。
- **ADT sidecar**：format 2 用 `[device_tree] source` 编译并合并硬件 DTB、OS/设备属性、payload 输入，写 Apple node encoding（`:48`）；format 1 调 `[payload.adt] tool` 指定的板级脚本，参数表包含 `--output/--dram-size/--owned-memory-size/--root-match-volume-uuid/--chip-id/--cpu-regs/--psci-method/--unique-chip-id/--packed-data-ramdisk/--data-ramdisk/--trust-cache/--owner-trust-cache/--ipad-identity`（`:50-66`）。
- ADT 必须预留的属性：`/chosen/memory-map/RAMDisk`、`/chosen/memory-map/PackedRAMDisk`、`/chosen/memory-map/TrustCache`、`/chosen/darwinboot-memory-size`；DarwinBoot 对收到的每个输入都要求对应占位存在，不匹配即 `EFI_COMPROMISED_DATA`（`:68-77`）。
- **Kernel arguments**：每个参数匹配 `[A-Za-z0-9_.\-]+`，可选 `=value` 的值匹配 `[A-Za-z0-9_.,\-]+`；额外 `--kernel-arg NAME=VALUE` 替换同名板级参数；拼接行最多 **1000 bytes**；DarwinBoot 复制进 1024-byte buffer（`:81-87`）。命令行以 `args` 存进 `unixnu.toml`，DarwinBoot 原样复制进 `boot_args`（`:87`）。
- **Trust cache**：bundle 校验为 32-bit count 1–128、每个 cache 一个 offset 表项、每个 cache version 2、每 entry 24 bytes、hash type 1–4、hash 升序；bundle 复制进 kernel window，地址/大小替换 `TrustCache` 占位（`:91-100`）。`--owner-trust-cache` 跳过 `[payload] trust_cache_sha256` 检查，携带原始 caches 和额外模块（如 GPU plugin）（`:102`）。
- **Data ramdisk**：`CONFIG_XNU_OWNER_DATA_MOUNT` 开启时，payload 需要 `--data-ramdisk FILE` 或 `[build] data_ramdisk`；没有生成的 `.config` 时读取设备 defconfig；缺 seed 会在写 payload 前停止（`:106-111`）。Dense（`RAMDisk`，整盘拷贝）与 Packed（`PackedRAMDisk`，校验 `DBRDISK1` extent table 后按 extent 拷贝）两种形式；packed header 含 magic `DBRDISK1`、version 1、page size、expanded size、`(offset,length)` extent 表，省略区间补零（`:113-121`）。Data 最大 1 TiB；超过 2 GiB 时 typed provider 只保留非零页（`:122`）。
- **确定性**：boot image 对给定 firmware volume/DTB/ramdisk 确定；ADT random seed 使每次 payload 构建不同；payload report 记录 kernel、ADT、trust cache、Data seed、payload 的 hash（`:124-126`）。

**对 K60 的含义**

- K60 `board.toml:75 size_mib = 192`：payload FAT 卷上限 192 MiB，超过会被 CLI 报 “Payload larger than size_mib”；payload 必须装下 kernel.macho + ADT + scratch-data.img。
- 任何传给 payload 的 `--trust-cache` 必须同时满足 `[payload] trust_cache_sha256` 白名单、ADT `TrustCache` 占位存在；K60 当前 `trust_cache_sha256` 为空（`board.toml:141-145` 注释），即默认不走 trust cache 路径。
- K60 若启用 `--data-ramdisk`，ADT 必须有 `RAMDisk` 或 `PackedRAMDisk` 占位；payload 的 `args` 必须符合字符集和 1000 字节上限。

#### 1.1.3 `docs/concepts/prelink.md`（98 行）— 源码内核 + 原厂 kernelcache 的绑定

**机制**

- Prelink 把“从源码构建的内核”和“原厂 Apple kernelcache”合成一个可启动 kernel：源码内核提供 UniXNU 改动的代码，原厂 kernelcache 提供 Apple kexts 和 platform services（`:3`）。
- 输入：native kernel（示例路径 `out/<device>/<os_profile>/<config>/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf`）、原厂 kernelcache（IPSW `KernelCache` 或 `--kernelcache FILE`）、`[kernel.prelink] roots`、`slide`、`early_security_init`（`:7-13`）。kernelcache 是 `KernelCache` IM4P 的 LZFSE payload，选 arm64 slice 并按 `kernelcache_sha256` 校验（`:15`）。
- `kits/XnuPrelink/emit_prelink.py` 的 9 步：解析 native/original Mach-O → 读 `__PRELINK_INFO` → 选择 `roots` 指定的 components 及其 import 的 kernel interfaces → 把选中 component 的 segments 复制到 native kernel 的空 coalesced segments → 重绑定所有指向选中 component 的指针 → 对每个选中地址应用 slide → 重写 module headers 和 kmod entries → 建 sparse prelink index → 写 `kernel.macho`（`:19-29`）。
- Coalesced segment 映射：`__PRELINK_TEXT`→`__TEXT`、`__PLK_TEXT_EXEC`→`__TEXT_EXEC`、`__PLK_DATA_CONST`→`__DATA_CONST`、`__PRELINK_DATA`→`__DATA`；范围保留原虚拟地址，slide 后原代码内部指针仍有效（`:35-44`）。
- Pointer rebinding：native kernel 对 original components 的每个 import 解析到 component export，把 slid address 写到 import site；report 记录 `bindings`（`:46-60`）。
- `early_security_init` 选一个原厂 security extension 及其可执行段地址；prelink 对其 slide 并记录给 kernel early security path。被选 component 的 prelink metadata 必须有 `AppleSecurityExtension = true`（`:62-64`）。
- `[kernel.prelink] kernelcache_sha256` 可 pin kernelcache；不同的 kernelcache 会被拒绝，把 native kernel 绑定到它被认证过的 component ABI（`:66-75`）。
- Sparsity/capacity：prelink 输出 sparse index；`native-4k-bootstrap-capacity` 增加 native 4 KiB 映射的 bootstrap 页表容量；boot progress patch 在 prelink 路径加 checkpoint（`:77-79`）。
- Report 字段：`components`、`kernel_interfaces`、`bindings`、`instruction_inventory`、`module_entrypoints`、`early_security_initializers`（`:81-92`）。

**对 K60 的含义**

- K60 的原厂 kernelcache 必须与其 OS profile（`ipados-16.6.1-20G81`）严格匹配；`kernelcache_sha256` 是防止 kernelcache/ABI 漂移的硬锁。
- `roots` 必须列出 K60 实际依赖的原厂 components（如 `com.apple.driver.AppleARMPlatform`、`com.apple.filesystems.apfs` 等，以 board.toml 为准）；`slide` 必须按 K60 的 `__DATA` 段大小推导（K60 仓库注释提到 `-0xb9c000` 一类），不能用 pong/sheng 的现成值。
- 源码内核必须是 BCM2837/PONG 的 4 KiB 构建；prelink 不改变页大小，只复制/重绑定。

#### 1.1.4 `docs/concepts/security.md`（148 行）— 信任链、4K 代码签名与 AMFI

**机制**

- 输入供应者：trust cache bundle（`--trust-cache FILE`）、trust cache pins（`[payload] trust_cache_sha256`）、platform seed（`--unique-chip-id HEX`）、设备树身份（format 2 typed `[adt]` / format 1 board script）、PMGR 集成（`XNU_SHENG_PMGR`）、root policy（`XNU_VERIFIED_ROOT_PROBE`、`XNU_OWNER_ROOT_AUDIT`、`XNU_OWNER_ROOT_TRUST`）（`:7-14`）。
- **Trust cache**：DarwinBoot 校验 bundle 结构并复制进 kernel window；ADT `/chosen/memory-map/TrustCache` 占位接收地址/大小；`native-trust-cache-runtime` 初始化 BCM2837 的 runtime trust cache path；原厂 AppleImage4 和 AMFI 对 cache 验证代码；payload 只接受 SHA-256 在 `[payload] trust_cache_sha256` 列表中的 bundle（`:16-22`）。
- **4 KiB code signing**：原厂 CodeDirectory 用 16 KiB hash page，4 KiB 内核验证 4 KiB 页；`native-4k-signature-hash-cache` 五步：用 `vn_rdwr` 读每个原厂 16 KiB block → 用原厂 CodeDirectory hash 校验 block → 从已验证 block 派生每 4 KiB 页的 hash → 存入只读 kernel memory → `cs_validate_page` 从派生表服务（`:24-34`）。只有原厂 16 KiB hash 匹配后才发布 block；失败 block 使 blob 无派生表，页验证返回 `CS_VALIDATE_TAINTED`（`:34`）。
- **AMFI policy**：ADT `/chosen/amfi-only-platform-code` 让 AMFI 保持 platform code policy；`[kernel.prelink] early_security_init` 在选定地址运行原厂 `AppleMobileFileIntegrity` initializer（`:36-38`）。`offline-owner-root-*` 补丁表 6 项：binding audit、crypto probe、boot manifest、cache carrier、SystemOS mount、Z air init（`:40-49`）。
- **User application installation（sheng iPadOS 27.0.1 / 24A446）**：适配 AppSync Unified 的安装和 FrontBoard 启动处理；无 app list、bundle-ID policy 或 build-time executable hash enrollment；新 app/更新无需重建 boot image（`:51-57`）。构建：`./unixnu build kernel payload -D ../UniXNU-sheng`、`./unixnu bootimg -D ../UniXNU-sheng`；设备上用 `/usr/libexec/unixnu-appinst /path/on/device/Example.ipa`（`:59-71`）。安装 hook 先用原 validator；失败则在安装副本中用 bundled ldid 修签名、保留 entitlements、重生成 resource seals、移除过期 provisioning profiles，再验证；原 IPA 保留（`:73-77`）。它选择 native ad-hoc path、禁用 preloaded trust hash/online authorization、跳过 provisioning profile ID 校验；FrontBoard 信任 user bundles（`.app` on Data，`/private/var/` 或 `/var/`，含 staging、embedded frameworks、app extensions）；系统路径保持 native（`:79-83`）。`sheng-appsync-user-trust.patch` 在 XNU 为这些树的 code 加载签名时登记 CodeDirectory hash，位于结构校验之后、原 AMFI signature callback 之前；用 owner boot modules 的 engineering trust-cache interface，runtime lock 下去重，登记 hash 留到重启；下次 boot 再次登记（`:85-91`）。`payload.runtime.appsync = true` 选择 runtime；`--kernel-arg appsync=0` 关闭 mounts 和自动 trust registration；动态分配 modules 每次 boot 上限 65536；签名结构、resource 校验、可执行页 hash 仍检查；**不提供 FairPlay 解密和 App Store 账号授权**；所有 app 仍需兼容 iOS 可执行文件（`:93-98`）。
- **GPU client grant**：Adreno740 在 accelerator service 发布 `NativeSandboxGrantProcess`；`zzw-native-adreno-sandbox-grant` 比较打开进程名；命名进程绕过 `mac_iokit_check_open_service` 和 `mac_iokit_check_open`；render server 即命名进程（`:108-110`）。
- **Verified root**：`kits/VerifiedRoot` 提供签名 policy bundle；verified block driver 对每次读按 policy 检查；可用 `--verified-root-bundle` 按容量选择；工具 `verified_root.c`、`xnu_crypto.c`、`manifest.py`、`verify_image.py`（`:112-123`）。
- **Storage integrity**：`VirtioMmioBlock` 和 `RamBlock` 共用 verified block policy；构建脚本检查两者 import 同一原厂 storage bindings，编译对象匹配记录 hash（`:125-127`）。
- **Reporting**：payload report 记录 `kernel_sha256`、`payload_kernel_sha256`、`adt_sha256`、`trust_cache_sha256`、`data_ramdisk_sha256`、`payload_sha256`；boot manager log 记录 staged kexts、installed ACPI、injected drivers（`:129-142`）。

**对 K60 的含义**

- K60 若走原厂 kernelcache + 4 KiB 内核，`native-4k-signature-hash-cache` / `CONFIG_XNU_NATIVE_CS_HASH_CACHE=y` 是硬要求（K60 defconfig 已为 `y`），否则 CodeDirectory 的 16 KiB hash page 无法服务 4 KiB 页。
- K60 当前 `CONFIG_XNU_NATIVE_TRUST_CACHE=n`、`CONFIG_XNU_TRUST_CACHE_RUNTIME=n`，与 `board.toml` 的空 trust cache 白名单一致；如果以后加 trust cache，必须同时打开 runtime patch、ADT 占位和 payload 白名单。
- AppSync 章节是 sheng/iPadOS 27 的实现参考，不是 K60 iOS 16 的默认路径；K60 不应把 `payload.runtime.appsync` 当作无条件能力。

#### 1.1.5 `docs/concepts/userdata.md`（95 行）— SHNGROOT 清单与 Data 持久卷

**机制**

- userdata 分区承载 Darwin root file system；UniXNU 不改原 disk images，只加 manifest 把每个 image 映射到分区窗口（`:3`）。
- `struct shngroot_header`：magic `"SHNGROOT"`、version 1、count、image_bytes、window[count]（name[32]、offset、size、block_size 512、flags bit0 read-only、sha256[32]、reserved[40]）、reserved[32]、manifest_sha256[32]（`:7-25`）。header 占 4096 bytes，零填充到 1 MiB；第一个 window 从 `0x100000` 开始；每个 window 按 1 MiB 对齐（`:27`）。
- Windows：`OS`（IPSW `OS`，系统卷）、`SystemOS`（`Cryptex1,SystemOS`，cryptex 系统卷）（`:29-34`）。image 从 IPSW 的 disk image 逐字节复制：macOS 用 `hdiutil` 只读 attach 后读 raw device，Linux 用 `scripts/unixnu/udif.py` 解 UDIF chunk；OS image 是 LZFSE chunk 的 UDIF，SystemOS cryptex 是 raw image（`:36`）。
- 分区容量 `(last_lba - first_lba + 1) * lba_bytes`；step 拒绝大于容量的 image；report 记录 capacity 和 image size（`:38-46`）。
- Root matching：XNU 通过 `/chosen/root-matching` 的 `IOProviderClass=IOMedia` + `IOPropertyMatch/UUID` 选择根卷；UUID 是 OS window 的 volume UUID；native block driver 发布 userdata 分区，partition scheme 发布 volumes，XNU 按 UUID 匹配（`:48-62`）。
- Data volume 独立于 userdata image，来自 payload 的 Data ramdisk seed；seed 是 payload 输入，payload report 记录其 hash（`:64-66`）。kernel 接受最高 1 TiB 的 Data disk；超过 2 GiB 时 typed block provider 只保留 seed 的非零页，内存随内容而不是磁盘大小；seed identity 对 size 和非零页及其 index 做 hash（`:68`）。
- 持久 store 从 userdata 分区末尾的 window 提供；写用 forced unit access，命令完成即落盘；store 避开 root image 和 log reserve；`sheng-log-reserve=<MiB>` 设置 reserve，默认 1024 MiB；`sheng-data-persist=1` 只读证明 window，`=2` 打开写（`:70`）。
- `scripts/seed-data-grow.py` 把 packed seed 的 APFS container 扩到指定大小或平板 userdata 分区；输出保留非零页和 volume UUID；不同 size 会重新开始 Data volume；kernel 拒绝 store window 不 fit 真实分区的 seed（`:72`）。`--skip-setup` 写一份 Setup preferences 标记完成的 seed 副本，按 seed hash 缓存（`:74`）。
- Report `userdata-root.json`：`image_bytes`、`image_sha256`、`manifest_sha256`、`windows`、`userdata_bytes`、`flash_command`、`source`、`hardware_tested`（`:76-89`）。

**对 K60 的含义**

- K60 `[userdata]` 为 `first_lba=53342976`、`last_lba=61731583`、`lba_bytes=4096`，容量正好 `8,388,608 × 4096 = 34,359,738,368 bytes = 32 GiB`；`userdata-root.img` 必须 ≤32 GiB。
- SHNGROOT header 必须 4096 bytes + 1 MiB 零填充，OS window 从 `0x100000` 开始且 1 MiB 对齐；任何自写 manifest 工具不能破坏这些偏移。
- K60 的 root UUID 必须来自实际 20G81 OS image 的 APFS root volume；`/chosen/root-matching` 不匹配会导致 “No root device” 类失败。

### 1.2 docs/guide（8/8）

#### 1.2.1 `docs/guide/overview.md`（16 行）— 纯重定向占位页

- 页面只有 frontmatter 和一行 `[Port a device](/porting/steps)`；`http-equiv="refresh"` 到 `/porting/`，canonical 指向 `https://unixnu.com/porting/`（`:1-16`）。
- 无技术内容；本次仍按“全部 26 篇”要求全文读取并计入覆盖。

#### 1.2.2 `docs/guide/requirements.md`（126 行）— 主机、外部输入与设备前提

**流程/前置条件**

- 四步 procedure：选 host toolchain → 收集外部输入（IPSW/kernelcache、trust cache、Data seed、driver ABI）→ 检查设备输入（device repo、firmware repo、target DTB）并写入 `unixnu.local.toml` → 选 defconfig 后运行 `./unixnu status --json`，确认 device/OS profile/source paths 与输入一致（`:3-8`）。
- **Host**：macOS 用 Xcode + `iphoneos` SDK；Linux 用 Linux toolchain；`--skip-setup` 和 Data seed resizing 需要 macOS image tools（`:10-12`）。工具表：macOS+Xcode、Python ≥3.11、git/make、cmake/ninja、unifdef、LLVM with lld、mtools、dtc、fastboot、QEMU/AAVMF（`:14-25`）。Homebrew keg-only LLVM 在 `/opt/homebrew/opt/llvm/bin` 自动找；其他工具需在 PATH（`:27`）。`unixnu fetch` 需要网络，更新 submodules、Apple source refs、Mu_Basecore tree（`:29`）。无 Mac 可用 GitHub macOS runner（`:31`）。
- **Linux**：`scripts/linux/setup-toolchain.py` 一次安装到 `/opt/unixnu-linux`（或参数/`UNIXNU_TOOLCHAIN`）；组件包括带 `__builtin_xnu_type_*` 的 clang、cctools-port `1030.6.3-ld64-956.6`、mig/iig、xcrun/plutil/codesign shims、lzfse（`:33-43`）。支持 apt/dnf/pacman/zypper（`:45-54`）。命令：`--print-packages`、`sudo scripts/linux/setup-toolchain.py`、`--check`（`:56-63`）；`--package-manager`、`--llvm-config FILE`/`LLVM_CONFIG`、`-j N`、位置参数 prefix（`:65-72`）。脚本写 `/usr/bin/xcrun`、`plutil`、`codesign` shims；Mach-O archives/libdispatch/BlocksRuntime 在 toolchain prefix 下（`:74`）。userdata step 可在 Linux；`--skip-setup` 和 `seed-data-grow` 需要 macOS（`:74`）。
- **External inputs**：Mu-Silicium checkout（`--uefi`/`UNIXNU_UEFI`）、target IPSW（`--ipsw`/`UNIXNU_IPSW`）、解压 kernelcache（`--kernelcache`/`UNIXNU_KERNELCACHE`）、编译 DTB（`--dtb`/`UNIXNU_DTB`）、trust cache bundle（`--trust-cache`）、owner trust cache（`--owner-trust-cache`）、Data seed（`--data-ramdisk`）、platform seed（`--unique-chip-id`/`UNIXNU_UNIQUE_CHIP_ID`）、prebuilt static archives（`--kernel FILE`）、edk2/Mu_Basecore（`--edk2`/`UNIXNU_EDK2`）（`:78-91`）。
- **Target IPSW 表**：arm64 iOS 16.7.16 20H392（iPhone10,3/10,6）；arm64 iPadOS 17.7.11 21H461（iPad7,1）；arm64e iOS 27.0.1 24A446（iPhone17,1）；arm64e iPadOS 27.0.1 24A446（iPad17,1–17,4）（`:97-102`）。iOS16/iPadOS17 都 arm64，共用 `profiles/arch/arm64` patch series；链接来自 ipsw.me（`:104`）。`[ipsw] url` 是设备仓默认，`--ipsw`/`UNIXNU_IPSW` 覆盖；IPSW 下载在仓库外（`:106`）。
- **Device**：可解锁且接受 `fastboot boot` 的 bootloader；提供 framebuffer、input、block I/O、file system 的 UEFI port；bring-up 期 UART/USB log；足够 RAM 给 kernel window、payload、userdata image；匹配的 OS restore image 和 device identity（`:110-118`）。

**对 K60 的含义**

- K60 的 20G81（iOS 16.6.1）不在文档四行 IPSW 表内，必须由 K60 自己的 OS profile/`[ipsw]` 提供；文档的 arm64 规则仍适用（iOS16 与 iPadOS17 共用 arm64 patch series）。
- K60 设备无 UART（仓库 AGENTS.md 说明屏幕即日志），所以 bring-up 前置条件中的 “UART/USB transport” 只能由屏幕诊断/panic screen 替代。
- `--skip-setup`、`seed-data-grow.py` 必须 macOS（或 macOS runner）；K60 的 Data seed 处理不能假设 Linux 可做。

#### 1.2.3 `docs/guide/build-kernel.md`（160 行）— 内核构建、defconfig 与 archive 顺序

**流程/命令**

- 五步：`./unixnu defconfig <name> -D /path/to/device` → `./unixnu fetch` + `status --json`（检查 OS revision、archives、patch order，提供 kernelcache/firmware/ABI）→ `./unixnu build kernel`（失败看 `logs/`，最终 `kernel/kernel.macho`）→ 仅 prelink 输入变化用 `./unixnu build prelink` → 继续 package/firmware/payload（`:6-17`）。
- 源树表：`tree/refer/xnu` pinned source、`.cache/xnu-work` patched working clone、`build/xnu/ios-obj` objects/compile records、`ios-sym` symbols、`ios-dst` install headers、`.cache/fakeroot` kernel SDK root、`.cache/firmware` device proprietary inputs、`kernel/kernel.macho` prelinked kernel（`:20-31`）。
- `[[source]]` 示例：`name="xnu" kind="refer" git=... ref="xnu-10063.141.1" commit="d8b802..." darwin="23.6.0" version="10063.141.1" driverkit_tag="xnu-10063.121.3" trustcache_tag="xnu-8796.101.5"`（`:35-46`）。`build kernel` 把这些作为 `UNIXNU_XNU_TAG/COMMIT/DARWIN/VERSION/DRIVERKIT_TAG/TRUSTCACHE_TAG` 传给 `scripts/build-xnu-4k-baseline.sh`（`:48`）。另外 pin `libpthread-519.120.4`、`corecrypto-2023` commit `11fba65`（`:50`）。
- 构建目标：`SDKROOT=iphoneos`、`ARCH_CONFIGS=ARM64`、`MACHINE_CONFIGS=BCM2837`、`KERNEL_CONFIGS=DEVELOPMENT`、`ARM64_LINK_ADDR=0xfffffff007004000`、`ARM64_PLKSEG_ADDR=0xfffffff004004000`、`DEPLOYMENT_TARGET_FLAGS="-miphoneos-version-min=17.0 -DXNU_TARGET_OS_IOS"`（`:52-62`）。`BCM2837` 承载 4 KiB page layout；arm64 kernel 目标 iOS 17 以匹配 iOS16/iPadOS17 kernelcache ABI；两个 arm64 目标共用 arm64 patch series（`:64`）。
- Defconfig 映射：`CONFIG_XNU_<NAME>` → `XNU_<NAME>`；`y`→1、`n`→0、quoted string 原样、`{tree}` 替换为 build tree path（`:66-68`）。标志表（22 项）：`XNU_SOURCE_CORECRYPTO14`、`XNU_SOURCE_PTHREAD`、`XNU_ARM_DT_PLATFORM`、`XNU_ARMVIRT_PLATFORM`、`XNU_ARMCPU`、`XNU_NATIVE_UFS`、`XNU_NATIVE_AES`、`XNU_NATIVE_VIRTIO_BLOCK`、`XNU_NATIVE_RAM_BLOCK`、`XNU_NATIVE_VIRTIO_CONSOLE`、`XNU_NATIVE_MOBILE_DISPLAY`、`XNU_NATIVE_LEGACY_DISPLAY`、`XNU_NATIVE_ADRENO`、`XNU_NATIVE_OFFLINE_GPU`、`XNU_VERIFIED_ROOT_PROBE`、`XNU_NATIVE_CS_HASH_CACHE`、`XNU_NATIVE_ARCH_TIMER`、`XNU_NATIVE_PAN`、`XNU_DT_PANIC_REGION`、`XNU_TRUST_CACHE_RUNTIME`、`XNU_BOOT_PROGRESS`、`XNU_SOURCE_MOCKFS`（`:70-93`）。
- `[kernel] archives` 是 build tree 的脚本列表，按顺序跑；一个 builder 消费另一个输出时必须排在后面；没有 builder 产出的 archive 必须在 build tree 提供；`CONFIG_XNU_BUILD_ARCHIVES=y` 才启用，bootstrap pass 和 first-console 配置不设（`:95-108`）。builders 通过 `scripts/xnu_symbols.py` 读符号名（checkpoint kernel 或 `link.filelist` + `all-alias.exp`）；fresh tree 需要一次 kernel pass 产生记录（`:110`）。`build-software-aes-bindings.py`、`build-adreno740-accelerator.py` 在无硬件证据时用 `scripts/data/` 的记录审计结果，地址属于 `board.toml` pin 的 kernelcache（`:114`）。
- 构建顺序：fetch → build kernel（apply patches + restore omitted headers）→ 无 compile records 时跑一次 XNU pass（可停在 link）→ 按顺序跑 `[kernel] archives` builders → build/link + prelink → `build prelink` 只重复 prelink（`:116-125`）。
- `[kernel.prelink]` 示例：`tool="kits/XnuPrelink/emit_prelink.py"`、`kernel="build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf"`、`kernelcache_sha256`、`slide="-0x1000000"`、`early_security_init="com.apple.driver.AppleMobileFileIntegrity=0xfffffff005ab4ae0"`、`roots=[...]`（`:127-142`）。
- 新增 kernel flag 五步：defconfig `CONFIG_XNU_<NAME>=y` → `build-xnu-4k-baseline.sh` 读 `XNU_<NAME>` → `EXTRA_MAKE_ARGS+=("<file>.o_CFLAGS_ADD=-DXNU_<NAME>=$VALUE")` → builder 加 `[kernel] archives`，archive 加 `KERNEL_EXTRA_ARCHIVES`/`KERNEL_ARCHIVE_DEPENDENCIES` → 通过 patch 加 personality 到 `iokit/KernelConfigTables.cpp`（`:144-150`）。
- Prebuilt kernel：`./unixnu build payload --kernel FILE` 可打包已有 prelinked kernel，不重建 XNU（`:152-154`）。

**对 K60 的含义**

- 文档示例的 `MACHINE_CONFIGS=BCM2837` 是官方 4K 路径；K60 本地脚本用 `MACHINE_CONFIGS=PONG`，因此 K60 的 PONG machine config 必须被证明与 BCM2837 同样定义 12-bit granule（见 §2.2）。
- K60 的 `CONFIG_XNU_NATIVE_CS_HASH_CACHE=y` 与 `CONFIG_XNU_NATIVE_PAN=y` 已落在 defconfig；`CONFIG_XNU_NATIVE_TRUST_CACHE=n`/`CONFIG_XNU_TRUST_CACHE_RUNTIME=n` 对应空 trust cache 策略。
- `[kernel] archives` 的顺序同样是硬约束：K60 的 `component:ArmDTPlatform`、`component:ArmCpu`、`component:PongUfs` 必须先于消费它们的 archive/link。

#### 1.2.4 `docs/guide/boot.md`（174 行）— 从 fastboot 到 XNU 的启动与诊断

**流程/命令**

- 先按 Building 组装 boot image；`./unixnu build firmware --uefi ../uefi-<device>`，Mu-Silicium initrd payload 必须含 `UniXNURamDiskDxe` + `DiskIoDxe` + FAT support；payload 先于 `./unixnu bootimg` 构建（`:5`）。
- 前置：解锁 bootloader + fastboot；匹配板配置的 UEFI port；有 payload 的 boot image（或空 ramdisk 做 boot manager smoke test）；有 UART 时串口（`:9-14`）。
- **首次根启动**：使用 userdata root layout 的 port 必须先安装 userdata image；`fastboot flash userdata out/<...>/userdata/userdata-root.img` 后 `fastboot reboot bootloader`；flash userdata 会覆盖分区，先确认设备、分区几何和 report 路径（`:16-28`）。
- **启动镜像**：`fastboot boot out/<...>/boot/boot.img`；`fastboot boot` 只传输并启动一次；运行中的 payload 按其 storage/installation policy 执行（`:34-41`）。boot image 组成：Kernel = gzip(BootShim + UEFI firmware volume)、Ramdisk = UniXNU payload FAT volume、Appended data = device tree（`:43-51`）。
- **启动菜单**：串口打印版本/配置摘要并画菜单；Up/Down 移动、Enter 启动、任意键停止倒计时、Enter 确认、无 choices 时任意键取消、Up/Down+Enter 选确认项；`confirm` 条目不会被倒计时启动；`confirm_titles` 时 Cancel 默认选中，选中的 `confirm_args` 追加到 entry args（`:53-66`）。菜单项来自 `\EFI\UniXNU\unixnu.toml`；无配置时扫描所有卷的 `\EFI\BOOT\BOOTAA64.EFI`，放在内置 action 前面（`:68-70`）。
- **Loader handoff**：xnu 条目目录文件：`kernel.macho`（必需）、`kernel.macho.adt`（必需）、`kernel.macho.trustcache`（可选）、entry `initrd`（可选）（`:74-82`）。DarwinBoot 复制 kernel segments 到连续物理窗口，构建 `boot_args`，把 ADT/trustcache 地址写进 `/chosen/memory-map` 占位，退出 boot services（`:83`）。默认窗口 256 MiB；ADT `/chosen/darwinboot-memory-size` 可请求更大窗口（`:85`）。
- **日志**：UEFI 日志到 `EFI_SERIAL_IO_PROTOCOL`，UniXNU 行前缀 `UNIXNU:`；kernel 日志到串口（如 `serial=3`）；boot progress 写 framebuffer + serial（`:87-91`）。日志位置：build `out/.../logs/*.log`、boot manager serial `UNIXNU:`、DarwinBoot `DARWINBOOT:`、XNU serial（`:93-100`）。
- **vendor_boot payload**：超过几 MB 的 payload 放不进 `boot`；GKI 设备 `boot` 无 ramdisk（`ramdisk_size=0`），vendor ABL 拒绝，所以 payload 放 `vendor_ramdisk`，`./unixnu bootimg --ramdisk none`（`:102-107`）。三个限制：Window（stock `vendor_boot` 把 ramdisk 放 `0x01000000`、DTB 放 `0x01f00000`，只剩 15 MiB；用 `--ramdisk-addr` 重定位）、Partition（重建 image 必须在分区内；最后 64 bytes AVB footer 重定向到 vbmeta，不必删除 footer）、Filesystem（firmware 按 FAT 挂载；`mformat -F` 可能产生读不了的卷，`mformat -T 8192 -h 64 -s 32` 产生可挂载 FAT16）（`:109-121`）。菜单行 `payload: initrd <start>-<end> [<id>] fs <n>`；`fs 0` = 块设备存在但无文件系统，缺 payload 行 = ramdisk 没到 loader（`:122-124`）。
- **面板诊断**：无串口板卡用 framebuffer；DarwinBoot 在跳 kernel 前把顶部 1/16 画绿；entry probe 在绿条下画蓝（kernel entry, MMU off）、品红（MMU 开启前）；`entry_probe_reset_delay` 在 MMU 开后数秒 PSCI reset；`payload.panic_screen=true` 把 panic 画到 kernel framebuffer；它与 stage-four probe 共用 `_start` 后零填充，不能同时开；`entry_probe_reset_after` 按 `_arm_init` 中的调用 bisect（`:126-146`）。
- **恢复**：硬件 reset 回 bootloader，`fastboot reboot bootloader`；firmware 在菜单前卡住则抓最后输出、回 bootloader、确认 `fastboot devices`，按 bring-up 检查固件输入（`:148-156`）。
- **macOS port**：需要匹配 XNU 版本的 OS profile、kernelcache、prelink roots、private driver ABIs、trust caches、root layout；用 kernel preparation/prelink 认证这些输入（`:158-167`）。

**对 K60 的含义**

- K60 无 UART，`boot-progress` / panic screen / 绿蓝品红条是唯一可视证据；`payload.panic_screen` 与 stage-four probe 互斥，必须二选一。
- K60 payload `size_mib=192` 可能超过 `boot` 分区能力，需按 vendor_boot 路径检查 15 MiB window 并 `--ramdisk-addr` 重定位；FAT16 格式化参数 `-T 8192 -h 64 -s 32` 是硬配方。
- K60 的 4.75 GiB window 依赖 ADT `/chosen/darwinboot-memory-size`；默认 256 MiB 不足。

#### 1.2.5 `docs/guide/debugging.md`（393 行）— 日志、诊断页、绿条与证据包

**流程/工具**

- 五步 procedure：记录失败命令/最后 boot checkpoint + 设备/固件/image revision → 选日志源（USB terminal 仅用于实现该协议的板卡）→ 绿条走 entry-probe，panic 抓 panic screen，用户态 fault 收集 user fault evidence → 一次只改一个诊断项，重建受影响 artifact（boot-args 改动要 `./unixnu payload` + `./unixnu bootimg`）→ 保存 evidence bundle 并更新 porting record（`:5-11`）。
- **USB debug terminal**：`scripts/debug_terminal.py` 和 `scripts/debug-terminal.cmd`；需 Python ≥3.10；命令 `--list`、`--port COM21 --command collect --seconds 20`（Windows）、Linux `--port /dev/ttyACM0 --command status --seconds 5`；Windows interactive `scripts\debug-terminal.cmd --port COM21`，`:help`；giulia 设备 `--vid 0x1209 --pid 0x0001 --usb-serial ACE5DBG001`；115200 baud，assert DTR（`:19-31`）。命令表：`all/collect`、`logs wifi/gpu/panic`、`save`、`watch status 2`/`unwatch`、`screen.start/stop`、`screen.snapshot`、`shell`（Ctrl+] 返回）、`reboot.fastboot`（`:33-42`）。会话存 `out/terminal/<timestamp>/`，topic export 保留最近 20,000 完整行；screen packet 与文本日志分离（`:44`）。
- **Device compatibility**：host tools 不是 kernel upgrade；初始 backend 实现 giulia protocol 2（`GIULIA` shell/input/reset markers、GSC1 screen framing up to 1264×2780 RGB565）；其他板必须实现该协议或加 backend；只改 USB IDs 不提供兼容；基本 kernel 可能只支持 `help/ping/status/replay`（`:53-57`）。
- **Log sources** 表：Firmware log export（OneSend QR frames）、Persistent logs（reserved storage / Linux reader / recovery reader）、UEFI serial（UART）、Kernel serial（`serial=`）、Diagnostic page（framebuffer）、Pulse strip（framebuffer 底行）、Panic screen（framebuffer）、QEMU log、Build reports（JSON）（`:67-79`）。
- **Serial console**：`[payload] kernel_args = ["-v","serial=3","debug=0x14e"]`；UniXNU 写第一个 `EFI_SERIAL_IO_PROTOCOL`，行前缀 `UNIXNU:`；DarwinBoot 行 `DARWINBOOT:`；采集 `tio -b 115200 -d 8 -p none -s 1 /dev/tty.usbserial-0001 -L out/serial.log`，或 picocom/screen/minicom（`:81-104`）。早期输出样例：UniXNU starting/config/driver/menu，DARWINBOOT loader installed/ARM64 va-pa-args/inputs validated（`:108-118`）。
- **Diagnostic page**：`boot-progress=1` 冻结（30 秒无 stage/storage 活动或 120 秒观察上限），`boot-progress=2` 连续；48 行 × 120 列，2160×1400 以上 scale 3；行组：Title、1（time/idle/IRQ/monitor/root/procs/free）、2（storage/verified/failures/integrity）、3–30（stage history/process states/storage detail/last PC/registers）、31–47（cached storage/UFS timing/memory/process sampling/UI trace/touch）、47 pulse strip（`:120-145`）。`sheng-build-tag=ks-001` 让标题栏带 `[ks-001]`；`boot-diag-resume=10` 在 userland 停止 scanout 10 秒后夺回面板（`:147-161`）。字段：time/idle/IRQ/monitor/lost/root/procs/free/requests/verified4K/failures/integrity/last PC/TCR/TTBR/SCTLR（`:163-180`）。
- **Pulse strip**：32-pixel 底条，2x 绿色，独立高优先级 monitor 线程每秒；格式 `P<turn> I<irq> M<monitor>/<seconds> B<bind>:<result> d<depth> @<base> lock<busy>/<render> PC<pc>`（`:182-198`）。
- **Panic screen**：`[payload] panic_screen = true`；payload 跑 `python3 scripts/patch-xnu-entry-probe.py <kernel> --panic-screen --no-reset`；使用 Mu-Silicium `FrameBufferSerialPortLib/Font.h`；`uefi` 设 `[build]` 或 `./unixnu payload --uefi ...`；`--no-reset` 保留屏幕拍照（`:202-219`）。
- **Green bar**：DarwinBoot `DarwinEnter` 在 `ExitBootServices` 后、cache maintenance/MMU shutdown/branch 前画绿；绿条卡住只说明 loader handoff 前成功；需要 entry probe 或串口定位下一段（`:221-230`）。Color bars：Green = DarwinBoot handoff、Blue = entry probe stage 1（MMU off）、Magenta = stage 2（MMU enable 前）；stage 3 无 bar，等待 `--reset-delay` 后 reset（`:232-242`）。Entry probe reset 配置：`entry_probe_reset_delay`、`entry_probe_reset_after`（如 `_arm_vm_init`）、`entry_probe_reset_in`（默认 `_arm_init`）、`entry_probe_reset_occurrence`（默认 1）、`entry_probe_reset_before`（默认 false）；映射到 `--reset-delay`、`--reset-after`、`--in`、`--occurrence`、`--reset-before`，可与 `panic_screen` 组合；无 `entry_probe_reset_delay` 时保持 `--no-reset`（`:244-257`）。
- **User fault evidence**：fault probe 在 exception delivery 前记录 EL0 breakpoint/abort 状态：pid/name、PC/LR/SP/FP、ESR/FAR、slide、x0–x28、最多 12 个返回地址；trap path 无分配；匹配的 process exit 打印 record 与 signal；未捕获 exception reason 在退出进程的可写 malloc region 搜索并随 crash row 打印（`:269-282`）。
- **UI stack trace**：`boot-ui-focus=launchd`、`boot-ui-focus2=SpringBoard`、`boot-ui-focus3=backboardd`、`boot-ui-focus4=Setup`、`boot-ui-chrono=1`；地址 token 用 radix-64；`python3 scripts/decode-boot-ui-trace.py trace.txt` 输出每线程组 JSON（`pc`、`lr`、frames、error codes）；每 8 秒轮换一页，拍 3–4 张（`:284-304`）。
- **拍照规范**：sheng-build-tag → boot-progress=1/2 → boot-diag-resume → 设备支架、镜头平行、关闪光、侧光、锁焦/曝光、四角入画、标题栏+整页、UI trace 每 8 秒 3–4 张、底部 pulse strip、记录 boot image SHA-256 与拍摄时间（`:306-330`）。
- **QEMU capture**：`python3 package/Scripts/qemu-run.py out/esp --log out/qemu.log --screenshot out/qemu.png --expect 'UNIXNU: menu: shown'`；clean log 在 `out/qemu.clean.log`；`--keys` 发键；`scripts/qemu-entry/gdb-stop.py --help` 在 symbol 停并记录 registers/memory（`:332-346`）。
- **Debug arguments 表**：`-v`、`serial=3`、`debug=0x14e`、`kextlog=0xfff`、`boot-progress=1/2`、`sheng-build-tag=<tag>`、`boot-diag-resume=<seconds>`、`sheng-platform-stage=<n>`、`sheng-touch=<n>`、`offline-legacy-phase=<n>`、`-no_slto_panic`、`cs_debug=<mask>`（`:348-364`）。
- **Evidence bundle**：serial log、diagnostic photos（title/full/trace/pulse）、panic photo、boot report、payload report、build logs；`shasum -a 256 boot.img`、`jq . boot.json`（`:366-384`）。
- 末尾说明 panic renderer 的 first-panic claim 在当前 kernel 的 zeroed BSS，warm reboot 可能保留 framebuffer 像素但不决定新 boot 是否显示/导出 panic；2048-byte panic text buffer 最后 1 字节保留给 claim（`:386-393`）。

**对 K60 的含义**

- K60 没有串口，`boot-progress=1` + 屏幕拍照是主证据链；`payload.panic_screen` 与 `entry_probe_reset_delay` 的组合要注意“与 stage-four probe 共用零填充不能同时开”的限制。
- `boot-diag-resume` 是 userland 接管显示后继续抓 K60 面板的唯一开关。
- 任何 boot-args 改动都必须 `payload` + `bootimg` 重新打包，不能只改 TOML。

#### 1.2.6 `docs/guide/mobilegestalt.md`（101 行）— ADT 身份与 UI 手势

**机制/步骤**

- MobileGestalt 从 Apple device tree（ADT）回答设备查询；payload 在 build 时写 ADT，身份变化不影响 signed kernel 和 userland image（`:3`）。
- 四步：按 iPadOS/iOS 选 model/target/product → 用 Apply 编辑 typed ADT 属性 → `./unixnu payload` + `./unixnu bootimg` 启动 → 检查身份/UI，若仍旧值按 cached answers 清缓存（`:5-10`）。
- 属性表：root `model`（如 `iPad7,1` → hw.product/hw.machine，按 prefix 选 device class）、root `target-type`（`J120` → hw.target）、`/product` 的 `product-name`、`product-description`、`artwork-device-idiom`（`pad`/`phone`）、`artwork-device-subtype`（`2732`）、`artwork-scale-factor`（`2`）、`artwork-display-gamut`（`P3`）、`compatible-device-fallback`（`iPad6,7`）、`thin-bezel`（`1`）、`/buttons` 的 `button-names`（`hold,voldown,volup`，无 Home 时省略 `menu`）、`home-button-type`（`2` = 无机械 Home，swipe 手势）、`/chosen` 的 `certificate-production-status`（`0`）、`effective-production-status-ap`（`0`）、`certificate-security-mode`（`1`）、`effective-security-mode-sep`（`1`）、`display-scale`（`2`）（`:12-33`）。`DeviceClass` 按 `hw.product` prefix 比较 `iPhone/iPod/iPad/AppleTV/Watch` 等，不匹配回退 `iPod`；root `model` 提供 `hw.product`，必须与 `/product` 一起设（`:34`）。
- 全屏手势：无 Home 设备要求 root model/target-type 来自无 Home 设备、`/buttons` 无 `menu`、`home-button-type=2`；SpringBoard 通过 `BSPlatform homeButtonType` 读取，值 2 时锁屏用 swipe-up（`:36-44`）。
- iPadOS/iOS 表：iPadOS `iPad7,1` / `J120` / `iPad Pro (12.9-inch) (2nd generation)` / `pad`；iOS `iPhone10,3` / `D22` / `iPhone X` / `phone`（`:46-55`）。`[payload.adt] ipad_identity = true` 传 `--ipad-identity` 给 board ADT tool，写 iPad 身份；iPhone 目标要写 phone 值或加 board option（`:57`）。身份描述硬件给 userland，系统仍来自 IPSW；iPadOS root 仍 iPadOS，iOS root 仍 iOS（`:59`）。root `compatible` 保留板卡自身；Apple board name 可能匹配原厂 platform kext 并选到未实现路径（`:61`）。
- Apply：format 2 在 board/OS profile 的 typed `[adt.product]`/`[adt.buttons]` 设置（device-tree types）；format 1 用 board ADT tool 的 `ipad_identity`；`./unixnu payload` → `./unixnu bootimg`；清 Data 卷缓存；启动检查 device name/lock hint/swipe/keyboard（`:63-70`）。format 1 Python ADT tool 直接写 `buttons`/`product` 节点的示例（`:72-91`）。
- Cached answers：`/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist`；按 build/platform UUID 缓存，身份变化可能保留旧 class/Home 答案；删文件或重建 Data volume；`/var/mobile/Library/Preferences/com.apple.MobileGestalt.plist` 和 `com.apple.mobilegestalt.plist` 同 domain（`:93-95`）。

**对 K60 的含义**

- K60 是 phone（Redmi K60），若使用 iOS root 必须写 `iPhone` 族身份（`model`/`target-type` 不能沿用 iPad）；若使用 iPadOS root 则 `ipad_identity=true` 并写 iPad 值。ADT 身份与 root image 必须同族。
- 改身份后必须清 MobileGestalt cache，否则 `hw.product`/Home button 答案不更新。

#### 1.2.7 `docs/guide/skip-setup.md`（127 行）— 跳过首启 Setup

**前置/流程**

- 需要 macOS image tools、匹配的 packed Data seed、板卡 `skip_setup_tool`；payload 后 `./unixnu bootimg` 并启动新 image（`:3`）。
- 四步：准备 seed/macOS/tool，检查 build version 和 ADT identity → 需要时先 `seed-data-grow` → `./unixnu build payload --data-ramdisk ... --skip-setup --trust-cache ... --unique-chip-id ...`，`payload.json` 必须有 `"skip_setup": true` → `bootimg`、启动、验证（`:7-12`）。
- `--skip-setup` 需要 `--data-ramdisk`；payload 读 `[payload] skip_setup_tool` 并在 seed 副本上运行；`skip_setup_args` 可选，追加在两个路径后；原 seed 不变；编辑副本作为 `Payloads/scratch-data.img`（`:22-34`）。
- `scripts/seed-data-skip-setup.py`：展开 packed APFS Data seed、读写 attach、合并 preferences 到 `/private/var/mobile/Library/Preferences`、重新打包（`:36-38`）。Preference 表：`com.apple.purplebuddy`（SetupDone=true、SetupFinishedAllSteps=true、SetupVersion=11、daemonizeNeedsToRun=false）；`com.apple.purplebuddy.notbackedup`（所有 mini-buddy flag=false：diagnostics、HSA2、keychain sync、Mesa、payment、standard、silent ICDP）；`com.apple.managedconfiguration.notbackedup`（LockdownActivationIndicatesCloudConfigurationAvailable=false）；`com.apple.springboard`（BKNoWatchdogs=true、FBLaunchWatchdogExceptions={com.apple.purplebuddy:100}、MCForceShowCloudConfigurationUI=false）；`com.apple.migration`（LastSystemVersion=21H461、DMUserDataDisposition={SyntheticDidUpgrade=false, buildVersion=21H461}）（`:40-46`）。`--no-auto-dim` 还设 `SBDisableAutoDim`、`SBDontDimOrLockOnAC`、`SBDisableIdleSleep`（`:48`）。
- 创建 `/private/var/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}`；volume UUID 不变；编辑后再次检查 APFS container magic（`:50-59`）。
- Build version：`BUILD, VERSION = '21H461', '17.7.11'`；目标 iOS build 不同时两者都改；`LastSystemVersion` 和 `DMUserDataDisposition.buildVersion` 必须匹配 IPSW（`:61-69`）。
- Device tree：format 2 OS profile 设置 `/chosen` 的 `certificate-production-status=0`、`effective-production-status-ap=0`、`certificate-security-mode=1`、`effective-security-mode-sep=1`；描述 development-fused/undemoted board，`mobileactivationd` 通过 MobileGestalt 读取并走 native activation path（`:71-82`）。
- Jobs：sheng iPadOS 27.0.1 的 `sheng-lite=1` 保留按需 `iconservicesagent`，IconRendering 用 Metal，`FORCE_SOFTWARE_RENDERER=0`、`CI_ENABLE_METAL_GPU=0`；`sheng-lite=2` 禁用 icon service（Home/Dock 无 app artwork，Settings 可开）；`sheng-disable-jobs=com.apple.identityservicesd,com.apple.locationd`（`:84-92`）。
- 输出：`payload/data-skip-setup-<hash>.dbr`、`payload.img`、`payload.json`；`payload.json` 记录 `data_ramdisk_sha256`、`skip_setup=true`、`payload_sha256`；编辑 seed 按原 seed hash + `skip_setup_args` 缓存（`:94-112`）。验证：payload.json 有 skip_setup，bootimg 启动到 SpringBoard 而不是 Setup（`:114-121`）。

**对 K60 的含义**

- K60 若使用 `--skip-setup`，必须 macOS 环境 + matching packed Data seed + `skip_setup_tool`；当前 K60 的 Data seed 若是 raw NXSB（仓库状态文档提到），不能直接套 DBRDISK1 工具，必须先转换/适配。
- Build version `21H461/17.7.11` 是 iPadOS 17.7.11 默认值；K60 的 20G81（iOS16.6.1）必须改这两个值，否则 `LastSystemVersion`/`DMUserDataDisposition` 不匹配。

#### 1.2.8 `docs/guide/userdata.md`（130 行）— userdata 镜像构建与 flash

**流程/命令**

- 准备 IPSW + device GPT；Linux 需 Linux toolchain（lzfse）；扩 Data seed 需要 macOS `hdiutil`/`diskutil`；AEA 加密 image（iOS/iPadOS 27）需要 macOS `aea` + `ipsw` 工具；先选设备并保存 local inputs（`:5`）。
- **分区几何**：`board.toml [userdata] first_lba/last_lba/lba_bytes` 来自设备 GPT 的 `userdata` 条目（`:9-18`）。OS profile `[userdata] windows = [{name="OS",component="OS"},{name="SystemOS",component="Cryptex1,SystemOS",optional=true}]`（`:20-30`）。image size = 各 window 1 MiB 对齐 + 1 MiB header；大于分区则拒绝（`:32`）。
- **预览/构建**：`./unixnu build userdata --ipsw ... --dry-run`，再 `./unixnu build userdata --ipsw ...`；提取 `[userdata] windows` 组件，macOS 解密 AEA，macOS `hdiutil`/Linux `scripts/unixnu/udif.py` 读 disk image，写 raw image 到 `out/<...>/userdata/userdata-root.img`；report 记录 offsets/sizes/hashes/capacity/flash command（`:34-45`）。
- **Root UUID**：`[payload.adt] root_match_volume_uuid = "REQUIRED_ROOT_VOLUME_UUID"`；用所选 OS image 的 APFS root volume UUID；macOS `diskutil apfs list` 匹配 container 后复制 Volume UUID；改后重建 payload/boot image（`:47-58`）。ADT generator 写 `/chosen/root-matching`（IOProviderClass=IOMedia、UUID）；native block driver 发布 userdata，partition scheme 发布 volumes，XNU 按 UUID 选 IOMedia（`:58`）。
- **Data volume**：`./unixnu build payload --data-ramdisk data.img`；macOS `python3 scripts/seed-data-grow.py --gib 8 /path/data.dbr /path/data-grow.dbr`；size 要在 root windows/store metadata/log reserve 之后 fit；工具 attach raw image + `diskutil apfs resize`，输出新 packed seed；接受 3–1024 GiB（`:60-77`）。`--auto` 读 `build/userdata-root/userdata-root.json`（或 `.img`）并查 fastboot userdata capacity；`--userdata-bytes BYTES` 替代查询；`--reserve-mib` 选 log reserve，默认 1024 MiB（`:79-83`）。volume UUID 保留但 size 改变会改变 persistence identity 并初始化新 Data store；记录 size/root report（`:85-88`）。`--skip-setup` 标记 Setup 完成，payload report 记录 seed hash 和 image hash（`:90`）。
- **Flash/boot**：确认设备/几何/report 路径，保存分区数据；`fastboot devices`、`fastboot flash userdata out/.../userdata-root.img`；成功后启动匹配 image，记录 root-mount 结果（`:92-103`）。
- **Layout**：`0x000000` SHNGROOT manifest 4096 bytes zero-padded 1 MiB；`0x100000` OS window 整个 disk image；后续 SystemOS window（`:105-111`）。Manifest little endian：offset 0 `SHNGROOT`、8 version 32-bit=1、12 window count 32-bit、16 image size 64-bit、24 window entries 128 bytes each、4064 SHA-256 of bytes 0..4063（`:113-124`）。window entry：32-byte name、64-bit offset、64-bit size、32-bit block size、32-bit flags、32-byte SHA-256、40 reserved（`:124`）。

**对 K60 的含义**

- K60 的 `first_lba=53342976`、`last_lba=61731583`、`lba_bytes=4096` → 32 GiB 容量；`--dry-run` 必须显示 image ≤32 GiB。
- K60 的 root UUID 必须从 20G81 OS image 提取；SystemOS window 若 IPSW 无该组件会在 `optional=true` 时跳过。
- flash userdata 会覆盖 K60 的 `unixnu` 分区，必须确认目标并保留原数据；K60 仓库规则还要求只 `fastboot boot`，不 flash Android 分区（但 userdata 安装是文档明确步骤，按设备策略执行）。

### 1.3 docs/reference（9/9）

#### 1.3.1 `docs/reference/index.md`（59 行）— 技术参考导航/能力矩阵

- 三步工作流：① 找 setting/implementation（表：local input paths → `unixnu.local.toml`；device/SoC/component → `board.toml`/`feeds.toml`/`configs/`；hardware resources → DTSI/DTS；driver behavior → component/board package；kernel behavior → profile/component patch series；XNU command line → `[payload] kernel_args` 或 `[build] kernel_args`；boot menu/kit → payload `unixnu.toml`/`Kit.toml`；device record → `porting.toml`；docs → `docs/`）（`:8-22`）。
- ② 读对应 reference：build driver（cli/configuration/output-layout）、components（components/drivers/repositories）、driver interfaces（UEFI/XNU drivers/kexts/device-tree matching）、XNU（source-and-patches/patch-reference/four-k-page-tables）、boot/image formats（boot-chain/prelink/payload/userdata/boot-configuration）、integrity（security）、project structure（repository/glossary）（`:24-37`）。
- ③ 验证 affected output：`./unixnu status --json` 检查 device/OS profile/configuration/module origins/output dir；验证表：kernel/driver/patches → kernel build + bring-up；firmware/payload → build/boot；boot args → inspect payload config；common UEFI → QEMU；record/docs → record check/site build（`:39-59`）。
- **能力矩阵含义**：本页不是能力清单，而是“变更类型 → 拥有文件 → 验证方法”的路由矩阵；真正能力字段在 `components.md`。

#### 1.3.2 `docs/reference/components.md`（85 行）— 组件目录与选择

- `components.toml` 记录 maintained components；profiles 用 `[components] include` 选 canonical IDs；resolver 加依赖并按 consumer 前排序 build commands（`:3-5`）。
- 选择流程：driver adaptation checklist 找 capability → 在 `components.toml` 搜 ID、读 implementation/board dependencies → 比较 hardware/OS ABI inputs → 在 device profile 选、加 archive/integration、`./unixnu status --json`（`:8-19`）。
- 字段表（能力矩阵的核心）：`id`、`kind/path`、`repository/revision`、`legacy_name`、`function`、`scope`、`hardware`、`os_abi`、`board_dependencies`、`verified_devices`、`dependencies`、`build_stage`、`build`、`outputs`、`runtime_identifiers`（`:22-40`）。实现 scope 与 hardware verification 是分离字段：Adreno740 实现 A740 GPU interface（SM8550 用），AdrenoMetal 通过 metal2vulkan/Turnip 提供 Metal frontend，依赖 kernel interface 和 OS ABI（`:42-44`）。
- 选择示例：`[components] include = ["ArmDTPlatform","ArmCpu","Adreno740","AdrenoMetal","GopFramebuffer"]`；kernel-stage recipes 按依赖顺序；`[kernel] archives` 可放 `component:<ID>` 标记；payload/firmware/prelink/embedded 各阶段（`:46-53`）。device 的 `include` 替换继承数组，必须列全，依赖由 resolver 加；`./unixnu status --json -D /path/to/device` 检查 resolved selection/revisions/local overrides/build order（`:55-61`）。
- 新 component 可用 `./unixnu tree -D ... --local-module driver:MyDriver=/path/to/MyDriver` 先本地挂载；catalog component 仍需 profile selection（`:67-74`）。
- Source identity：official compatibility name 按 catalog 的 repository identity 解析（`UniXNU/NativeAdreno` → `Adreno740`）；`another-owner/NativeAdreno` 保留自己的 identity/selection；编辑 feed 前检查 remote/revision；migration table 列 accepted names；source filenames/runtime identifiers 保持 ABI 值（`:76-85`）。

#### 1.3.3 `docs/reference/glossary.md`（43 行）— 术语表

- 33 个术语：ADT（Apple device tree，compact node encoding，XNU 从 `.adt` sidecar 读）、AMFI、ABL、BootShim、UniXNU（UEFI boot manager）、DarwinBoot（UniXNU XNU loader）、Defconfig、Device repository、ADT sidecar（`kernel.macho.adt`）、Feed、Firmware volume（EDK II `SILICIUM_UEFI.fd`）、IOMedia、IPSW、Kernelcache、Kext、Kit、Module、Personality、PGZ（zone allocator secondary page）、Prelink、SMMU、Trust cache、Userdata、SHNGROOT、SystemOS、DSC、FDF、INF、DXE、BDS、GOP、CHRP、PGZ probe（`:3-37`）。
- 本表是全文术语的唯一权威；对 K60 文档写作应统一用 `ADT`（不是 DTB）、`payload`、`prelink`、`SHNGROOT`。

#### 1.3.4 `docs/reference/boot-configuration.md`（303 行）— `unixnu.toml` 与 `Kit.toml` 全字段

- `unixnu.toml` 从 boot manager 自身卷开始，再每其他卷找；kit 目录 `Kit.toml` 有相同 match/injection sections（`:3`）。boot args 在 payload 的 `EFI/UniXNU/unixnu.toml`；改后 `./unixnu payload` + `./unixnu bootimg`（`:5`）。
- 五步 procedure：定位 `EFI/UniXNU/unixnu.toml`（生成 payload 改 board.toml/local inputs）→ 按字段定义 entry/paths、确认 kernel/sidecar/driver/initrd 存在 → kit 填 Kit.toml、验证 match → 重建 payload/boot image，`mtype -i <payload.img> ::/EFI/UniXNU/unixnu.toml` 检查，启动看菜单（`:7-12`）。
- `[boot]`：`timeout`（默认 5，负值等输入）、`rotate`（0 禁用）、`fallback_timeout`（10，无输入设备）、`connect_all`（true，对每个 handle `ConnectController`）、`default`（first entry/index）（`:35-43`）。
- `[ui]`：`title`（UniXNU）、`scale`（0 自动）、`logo`（true）、`layout`（auto/landscape/portrait）、`portrait_below`（800；auto 下 width/height×1000 低于该值用 portrait）、`console`（auto/graphics/text/none）（`:45-56`）。Portrait 布局说明（`:56`）。
- `[[driver]]`：`path`（文件或 `fv:<GUID>`）、`args`、`connect`（true）、`enabled`（true）；kit driver 用 `file` 代替 `path`（`:58-75`）。
- `[[dt_patch]]`：`op`（set/delete-prop/add-node/delete-node/overlay）、`node`（绝对路径）、`prop`、`value`、`type`（string/stringlist/u32/u64/bytes/empty）、`file`（overlay）；patches 只 apply EFI/Linux entries；Darwin 用 `.adt` sidecar（`:77-97`）。
- `[[block_slice]]`：`partition`（GPT name）、`name`（slice label）、`offset`、`length`（0=到结尾）、`writable`、`enabled`；slice 显示为 whole disk，child partition scheme/file system driver 可绑定（`:99-120`）。
- ACPI：`[acpi] add=["Tables/DSDT.aml","Tables/SSDT.aml"]`，每表经 `EFI_ACPI_TABLE_PROTOCOL` 安装，header length 必须等于文件大小（`:122-129`）。
- Kits：`[[kit]] path/enabled`；`[kits] autoload=true/directory="Kits"`；显式 kit 先加载，autoload 按名称顺序加载 `*.kit`（`:131-143`）。
- `[[entry]]`：`id/title/type`（efi/linux/action/xnu）、`path`、`args`、`dtb`（firmware/文件/缺省）、`initrd`、`confirm`、`confirm_titles`、`confirm_args`、`action`（reset/shutdown/exit/tools）、`enabled`（`:145-174`）。有 `confirm` 的 entry 只有 Enter 启动；无 choices 任意键取消，无输入设备也取消；`confirm_titles` 时 Up/Down 选，Cancel 默认第一，选中 `confirm_args` append 到 args 副本；默认 entry 需确认时倒计时退到第一个不需确认的 entry（`:176-178`）。内置配置有 exit/reset/shutdown/tools；tools 打开二级菜单列出 menu plugins；无文件时 removable loaders 放前面（`:180`）。
- `[entry.chosen]`：每个 key 成为 `/chosen` 属性，apply 在 entry patches 之后（`:182-189`）。
- `[[entry.kext]]`：bundle/plist/executable/enabled，只对声明它的 entry 生效（`:191-201`）。
- `[[entry.variable]]`：guid/name/value/type（ascii/ucs2/u8/u16/u32/u64/bytes）/volatile（false 加 `EFI_VARIABLE_NON_VOLATILE`）；entry 启动前设置（`:203-222`）。
- `[[entry.dt_patch]]`：entry 自己的 dt_patch，apply 在 global patches 之后（`:224-226`）。
- `Kit.toml`：`schema=1`、`[kit] name/version/description`、`[match] arch/fdt_compatible/firmware_vendor/requires_protocol`、`[[driver]] file/args`、`[[overlay]] file`、`[[dt_patch]]`、`[[acpi]] file`、`[[kext]] bundle/entry`（`:228-264`）。Match 键：`arch=AARCH64`、`fdt_compatible`（firmware root compatible 列表）、`firmware_vendor`（`gST->FirmwareVendor` substring）、`requires_protocol`（GUID 必须 installed）；同一 key 内任一值匹配，跨 key 全部匹配（`:266-285`）。
- Menu behavior：有输入设备 → 倒计时到 timeout；无输入 → fallback_timeout；负 timeout + 有输入 → 等键；负 timeout + 无输入 → fallback_timeout；failed boot → 回菜单无倒计时；菜单显示配置源、entry 列表、injection summary、first error（`:287-297`）。

#### 1.3.5 `docs/reference/cli.md`（171 行）— 命令、选项、环境变量、退出行为

- 命令：`defconfig [NAME]`（列表/合并 profile fragments + selected file 到 `.config` 并解析）、`fetch [NAME...] [--update]`（更新 module submodules/device repo、fetches git sources、写 `unixnu.lock`）、`tree`（解析 modules/fetch refs/assemble tree）、`ipsw info/fetch`、`build [kernel|package|firmware|payload|prelink|userdata]`（userdata first, then kernel incl. prelink, package, payload, firmware；默认/all = kernel/package/payload/firmware）、`bootimg [--fd --dtb --ramdisk|none -o]`、`vendor_boot --stock ...`、`status [--json]`、`clean`、`release`（`:11-99`）。
- `build prelink` 只重复 prelink；`build kernel` 准备有序 patches、compile-record pass、component recipes + archives、link；`component:<ID>` 标记 component recipe 位置；`build userdata --dry-run` 检查 IPSW/partition size（`:52-58`）。
- `bootimg`：firmware volume 默认 `--uefi` 输出；ramdisk 默认 payload 输出（若存在）（`:60-67`）。`vendor_boot`：重写 stock `vendor_boot` v4 的 vendor ramdisk；DT/ramdisk table/bootconfig/vbmeta 原样复制，AVB footer 重定向，仅 ramdisk 和依赖 size 变化；`--ramdisk-addr` 重定位；`--verify-against` 先重打包 stock ramdisk 并要求 byte-identical，否则拒绝；输出默认 `vendor_boot.img`（`:68-74`）。
- `status --json` 字段：`schema_version`、`device`、`name`、`output`、`configuration`、`config_path`、`configured`、`profiles`、`configuration_sources`、`board`、`components`、`modules`、`patch_order`；读 cached/local SoC sources，缺 source 先 fetch（`:76-82`）。`clean` 删除 tree/logs/kernel/package/boot/edk2-conf，保留 fetched sources（`:84-90`）。`release` 固定步骤 deps/preflight/patches/build/pack/verify，写 `package.manifest.json`（`:92-98`）。
- Options 表：`-D/--device`、`--os VERSION`（17/27/profile dir）、`--out`、`-j/--jobs`、`--local` / `--local-drivers` / `--local-kits` / `--local-patches` / `--local-scripts` / `--local-package` / `--local-module [KIND:]NAME=PATH`、`--uefi`、`--edk2`、`--kernelcache`、`--skip-preflight`、`--kernel FILE`、`--kernel-arg NAME[=VALUE]`、`--trust-cache`、`--owner-trust-cache`、`--skip-setup`、`--data-ramdisk`、`--unique-chip-id`、`--ipsw`、`--dry-run`、`--target DEBUG|RELEASE`、`--fd`、`--dtb`、`--ramdisk`、`-o/--output`、`--stock`、`--ramdisk-addr`、`--verify-against`（`:100-136`）。
- Environment：`UNIXNU_DEVICE`、`UNIXNU_OUT`、`UNIXNU_UEFI`、`UNIXNU_EDK2`、`UNIXNU_KERNELCACHE`、`UNIXNU_DTB`、`UNIXNU_IPSW`、`UNIXNU_UNIQUE_CHIP_ID`、`JOBS`（`:137-149`）。
- Exit behavior 表：缺 device repo → `-D` hint；缺 kernel config → defconfig hint；缺 Mu-Silicium → error before fetching；IPSW identity mismatch → expected/actual；sha256 pin mismatch → member；firmware volume size mismatch → size；payload > size_mib → 提升 size；invalid kernel arg → 参数名；kernel command line >1000 bytes → 长度和 limit；缺 platform seed → `--unique-chip-id` hint；example device repo → error（`:151-165`）。

#### 1.3.6 `docs/reference/configuration.md`（264 行）— `board.toml` / local inputs / feeds

- Format 2 用 `schema_version = 2`；无该字段是 format 1（`:3-5`）。
- **Local build inputs**：复制 `unixnu.example.toml` 到 `unixnu.local.toml`（Git 忽略）；示例 `[build] device/uefi/dtb/kernelcache/trust_cache/data_ramdisk/unique_chip_id/jobs/target/kernel_args`；相对路径相对配置文件目录；优先级 CLI > env > 文件 > device defaults；`kernel_args` 按 name 覆盖 board args，`--kernel-arg` 再覆盖 local（`:7-27`）。支持路径键：`device`、`out`、`uefi`、`edk2`、`kernelcache`、`kernel`、`trust_cache`、`owner_trust_cache`、`data_ramdisk`、`gpu_addon`、`dtb`、`fd`、`ramdisk`、`output`；其他键 `ipsw`、`unique_chip_id`、`jobs`、`target`、`kernel_args`；`ramdisk="none"` 空 ramdisk（`:27`）。命令示例 defconfig/kernel/firmware/payload/bootimg/status（`:29-36`）。`status` 报 `build_config`；module source overrides 用 device 仓 `local.toml`（`:38`）。
- Profile fields：`board.soc_source`/`os_profile`；`components.include`；`kernel.config_fragments`/`patch_series`；`device_tree.source`/`include_dirs`（`:44-54`）。Layers 顺序 ARM64→SoC→OS→device；tables merge by key，arrays replace；defconfig 在 fragments 之后；file prefixes `arch:`/`soc:`/`os:`/`device:`；series entries 也接受 `component:<ID>/path`；`status --json` 报 effective config（`:56-59`）。
- `board.toml` 各表：`[board]` name/soc/description/kit/example；`[ipsw]` url/product/version/build/device_class/chip_id/board_id/fetch；`[ipsw.sha256]` member→SHA；`[userdata]` first_lba/last_lba/lba_bytes/windows；`[kernel]` defconfig/archives；`[kernel.prelink]` tool/kernel/slide/roots/early_security_init/kernelcache/kernelcache_sha256/extra_args；`[firmware]` config/dsc/fd/packages/preflight/patches/submodules；`[firmware.defines]` any→`-D NAME=VALUE`；`[bootimg.image]` base/kernel_offset/tags_offset/pagesize/header_version/kernel_compression（gzip/none）；`[[bootimg.dtb_node]]` path/props（s/x/i/u/empty）；`[payload]` volume（≤11 chars）/size_mib/loader/title/dram_size/panic_screen/trust_cache_sha256/kernel_args/tools/timeout/skip_setup_tool；`[payload.adt]` tool/chip_id/owned_memory_size/root_match_volume_uuid/cpu_regs/psci_method/packed_data_ramdisk/ipad_identity/unique_chip_id（`:61-188`）。
- Defconfig 语法：`CONFIG_NAME=y/n/"text"/123`、`# CONFIG_NAME is not set`；`CONFIG_XNU_<NAME>`→`XNU_<NAME>`；`{tree}` 替换（`:189-199`）。`feeds.toml` source 字段 name/kind（driver/kit/patch/script/package/refer/soc）/git/ref/path/commit/local/submodules（`:201-224`）。`local.toml` 的 `[local] drivers/kits/patches/scripts/package`（`:226-237`）。`unixnu.lock` `[source."Name"] commit=...`；format 2 explicit source commit 优先 lock（含 selected OS XNU revision）；format 1 lock-first；official aliases 可复用 lock entries（`:239-246`）。
- Module resolution 优先级：`--local-module` → `--local-<kind>` → `--local` → `feeds.toml`/`local.toml` local key → device repo → base repo → git source；first match wins（`:248-258`）。

#### 1.3.7 `docs/reference/output-layout.md`（154 行）— 输出目录与 report schema

- Format 2 输出按 device/OS profile/config 隔离到 `out/<device>/<os_profile>/<config>/`；format 1 用 `out/<board>/`；fetched sources 和 IPSW members 共享 caches；`unixnu.lock` 记录 source revisions（`:3`）。
- Tree：`out/state.json`、`feeds/`、`ipsw/<build>/`、`<device>/<os_profile>/<config>/{.config,tree,logs,device-tree/hardware.dtb,kernel/kernel.macho,package/Build/Out,payload/payload.img,payload.json,boot/boot.img,boot.json,userdata/userdata-root.img,userdata-root.json}`（`:5-31`）。
- `state.json` 只有 `device` 路径；driver 在 `-D`/`UNIXNU_DEVICE` 缺失时读它（`:33-41`）。`feeds/<repo>-<hash>/` hash 覆盖 URL+ref，浅/无 blob/sparse clone（`:43-51`）。`ipsw/<build>/` 每 member + `.json` sidecar（component/member path/size/SHA/source），size+hash match pin 时复用（`:53-61`）。
- `tree/` 子目录 `drivers/kits/patches/refer/scripts/package/build/.cache`；`.cache/xnu-work` patched sources，`build/` generated headers/archives，module dirs 是 symlink，scripts 是 copy，device package 是 `kits/<board.kit>`，`.cache/firmware` 是 device repo 的 symlink（`:63-79`）。
- Logs 表：`kernel.log`、`kernel-bootstrap.log`、`archive-NN-<name>.log`、`prelink.log`、`package.log`、`firmware-preflight.log`、`firmware.log`、`basetools.log`、`payload.log`、`payload-adt.log`、`payload-patch.log`、`payload-skip-setup.log`、`userdata.log`（`:81-99`）。
- `boot.json` 字段：kernel_sha256、ramdisk_bytes、header_version、kernel_address、tags_address、image_sha256、image_bytes、fd_sha256、dtb_sha256、shim_bytes、hardware_tested（`:101-115`）。`payload.json`：kernel_sha256、payload_kernel_sha256、adt_sha256、kernel_args、trust_cache_sha256、data_ramdisk_sha256、skip_setup、panic_screen、payload_sha256、payload_bytes、hardware_tested（`:117-131`）。`userdata-root.json`：image_bytes、image_sha256、manifest_sha256、windows、userdata_bytes、flash_command、source、hardware_tested（`:133-144`）。
- `clean` 删除 tree/logs/kernel/package/boot/edk2-conf，保留 fetched sources/IPSW members（`:146-148`）。

#### 1.3.8 `docs/reference/qemu.md`（131 行）— QEMU 测试矩阵

- QEMU 测 UniXNU、injection paths、DarwinBoot、kernel entry，无需设备（`:3`）。
- 四步：装 requirements（AArch64 firmware）→ common UEFI 场景跑 smoke test；custom EFI 先 stage ESP 再 run + expect markers → kernel-entry 用 XNU entry fixture 和 runner options → 检查 logs/screenshot，记录 exact marker/timeout，继续 device bring-up（`:5-10`）。
- Requirements：`qemu-system-aarch64`、AAVMF 或 EDK2 AArch64 firmware、`dtc`、`mtools`/`pyfatfs`；runner 找 common Homebrew/distro 路径或 `--firmware`（`:12-21`）。
- Stage ESP：`python3 package/Scripts/stage-esp.py -o out/esp package/UniXNUPkg/Test/Qemu/esp --put ...=EFI/BOOT/BOOTAA64.EFI ...`；把 dts→dtb、dtso→dtbo，按 `--put` 放置（`:23-33`）。
- Run：`python3 package/Scripts/qemu-run.py out/esp --log out/qemu.log --screenshot out/menu.png --expect 'UNIXNU: menu: shown' --expect 'UNIXNU-HELLO: RESULT PASS'`；options：`--firmware`、`--log`、`--screenshot`、`--keys`、`--expect`、`--reject`、`--no-gop`、`--display-size WxH`（如 1080x2400 portrait，宽度至少 640）、`--disk`、`--timeout`、`--cpus`、`--finish-on-expect`、`--menu-marker`；ESP 通过 QEMU `vvfat` 只读暴露，QMP 控制 screenshot/keys（`:35-60`）。
- Smoke test `JOBS=8 bash package/Scripts/smoke.sh` 六场景：Default entry（DT patches/overlay/kit driver/initrd media/entry variable）、Keyboard（Down+Enter 第二项）、Degraded（无 GOP/无配置、内置 entries、text console）、Block slice（FAT partition head，tail 为 block device）、Kext staging（revision 2 handoff、revision 1 refusal、invalid bundles、duplicates）、Layout（1080x2400 portrait、800x1000 landscape）；logs/screenshots 到 `package/Build/Smoke/`（`:62-79`）。
- XNU entry fixture：`python3 scripts/qemu-entry/make-dt.py --armvirt --armcpu --smp 2 --owned-memory-size 0x20000000 --output build/qemu-test.adt`；选项 `--armvirt`、`--armcpu`（GICv3 distributor/redistributor）、`--smp N`、`--owned-memory-size`、`--data-ramdisk`、`--trust-cache`、`--nvram-proxy`、`--root-match-volume-uuid`、`--osenvironment`（main/recoveryos/ramdisk）、`--qemu-vmm-present`、`--crypto-hash-method`；只描述 QEMU 值（`:81-106`）。
- HVF：Apple Silicon macOS 可用 `--qemu-accel hvf`，generator 读 host counter frequency 作 CPU timebase；bound fixture 观察 kernel stop 点实际 `TCR_EL1`、`SCTLR_EL1`、`TTBR`（`:108-117`）。Stop point `python3 scripts/qemu-entry/gdb-stop.py --help` 记录 registers/memory/last checkpoint 为 JSON（`:119-125`）。

#### 1.3.9 `docs/reference/troubleshooting.md`（100 行）— 症状表与证据

- 五步：保存 failing command/first error + 最后 bring-up stage → `status --json` 确认 device/source/OS/output → 查 build/IPSW/boot 表 → 修正输入后重复失败步骤并重打包 → 未确定则 evidence bundle（`:5-9`）。
- Early boot checks：顶部绿条 = DarwinBoot handoff 前；boot-args 改动要重建 payload/boot image；保存 firmware/image 路径到 `unixnu.local.toml`（`:11-15`）。
- **Build 表**关键错误：`no device repository`、`has no board.toml`、`is an EXAMPLE device repository`、`no configuration`、`no Mu-Silicium checkout`、`is not a Mu-Silicium checkout`、`no edk2 tree`、Missing archive、`no builder makes it`、`kernelcache not found`、`does not match the kernelcache`、Firmware volume size mismatch、`Payload larger than size_mib`、`not one of the trust caches this board accepts`、`unsupported kernel argument`、`command line is ... bytes`（`:18-36`）。
- **IPSW 表**：`this IPSW is ...`、`no Erase build identity`、`does not support range requests`、`differs from the pinned sha256`、`expected exactly one arm64 slice`（`:38-46`）。
- **Boot 表**：fastboot 看不到设备、Image 启动后 reset、Firmware stalls、No display、No menu、No boot entry（检查 boot.json ramdisk_bytes、FD 的 UniXNURamDiskDxe/DiskIoDxe/FAT、FDT initrd range、`EFI/UniXNU/unixnu.toml`）、Driver failed、`no loader protocol installed`、`loader revision 1 cannot accept kexts`、`boot refused: ...; firmware retained`、Kernel panics at entry（page tables/kernel window/boot args）、Panic names a provider、No root device（userdata image/UUID/capacity）、Data store window refused（seed size/`sheng-log-reserve`/root image）、Display assertion in userland（`:48-66`）。
- Logs 位置（build/serial/QEMU）、report 检查 `jq`、module origin `./unixnu status`（`:68-97`）。

### 1.4 docs/xnu（4/4）— 硬性要求逐条

#### 1.4.1 `docs/xnu/boot-arguments.md`（124 行）— boot-args 格式、优先级与平台参数

**定位**：boot-args 的生效链、语法、常用/平台参数、新增参数方法（`:3-5`）。

**硬性要求（逐条）**

1. **生效链**：有效命令行 = `[payload] kernel_args`（board profile）+ `[build] kernel_args`（`unixnu.local.toml`）+ `--kernel-arg` overrides；后者按同名替换前者；payload builder 把它写进 `EFI/UniXNU/unixnu.toml` 的 XNU entry `args`；UniXNU 把选中 entry 传给 DarwinBoot，DarwinBoot 原样复制进 XNU `boot_args.CommandLine`（`:5`）。
2. **单参数语法**：`[A-Za-z0-9_.-]+(=[A-Za-z0-9_.,-]+)?`；不允许空格作为参数内部字符、不允许 `/`、`:`、`+`、`@` 等（`:22-26`）。
3. **总长度**：拼接后的行最多 **1000 bytes**；DarwinBoot 复制进 **1024-byte** buffer（`:28`）。
4. **修改后的重建链**：`./unixnu payload --kernel-arg ...` 后必须 `./unixnu bootimg`；`bootimg` 把当前 payload 复制进 `boot.img`；打包后再编辑 payload 必须重跑 `bootimg`（`:7-16`）。
5. **验证命令**：`jq -r .kernel_args out/<...>/payload/payload.json`；`mtype -i out/<...>/payload/payload.img ::/EFI/UniXNU/unixnu.toml`（`:12-13`）。
6. **多卷配置**：多个卷都有 `unixnu.toml` 时，先检查 boot manager 自身卷的配置（`:16`）。
7. **自定义 ramdisk**：`--ramdisk FILE` 选择该文件的配置；检查所选 XNU entry 及追加的 `confirm_args`（`:16`）。
8. **观测点**：payload 命令打印 `kernel args:`；DarwinBoot 打印 `DARWINBOOT: command line:`；两者不一致则查所选卷/entry；一致但行为不变则查 kernel/driver 是否实现该参数（`:18`）。
9. **新增参数**：默认值放 `[payload] kernel_args` → 一次性值用 `--kernel-arg` → kernel 用 `PE_parse_boot_argn("my-driver-stage", &stage, sizeof(stage))` 读取 → 在 device page 文档化（`:91-104`）。
10. **内核配置开关**：由 `./unixnu kernel` 编译，不是 boot-arg（`:5`）。
11. **安全例外**：`amfi_get_out_of_my_way=1` 只用于诊断启动，会改变安全策略（`:51`）。
12. **参数分类**：Common args 表（`-v`、`serial=3`、`debug=0x14e`、`kextlog=0xfff`、`-apfs_shared_datavolume`、`-no_slto_panic`、`kt_fixed_zones=<n>`、`boot-progress=<n>`、`cs_debug=<mask>`、`amfi_get_out_of_my_way=1`、`pmap_debug=<mask>`、`zlog=<name>`）（`:34-49`）；Platform args 表（`sheng-platform-stage=<n>`、`sheng-pmgr=<n>`、`native-ufs-root=1`、`native-ufs-stats-delay=<n>`、`armcpu-diagnostics=1`、`armcpu-spi-ipi=1`、`sheng-smp=1`、`sheng-cpufreq=<n>`、`sheng-touch=<n>`、`sheng-touch-hz=<n>`、`sheng-touch-mode=<n>`、`sheng-touch-hid=1`、`sheng-aks=1`、`sheng-aks-sls=<n>`、`sheng-usb=<n>`、`sheng-usb-host=<s>`、`sheng-usb-back=<s>`、`sheng-gpu-power=<n>`、`sheng-gpu-metal=1`、`sheng-gpu-addon=1`、`sheng-data-persist=<n>`、`sheng-data-reset=<n>`、`sheng-log-reserve=<mib>`、`sheng-disable-watchdogd=1`、`sheng-disable-jobs=<list>`、`offline-legacy-*=1`、`offline-owner-root-check=1`、`offline-owner-root-audit=1`、`offline-apfs-load=1`、`offline-mobile-graphics-*=1`、`boot-ui-focus=<name>`）（`:53-89`）。
13. **调试组合**：早 kernel 输出 `-v serial=3 debug=0x14e`；kext `kextlog=0xfff`；boot progress `boot-progress=2`；platform stop `sheng-platform-stage=<n>`；storage `native-ufs-root=1 native-ufs-stats-delay=30`；display `offline-legacy-gop=1 offline-legacy-phase=<n>`；code signing `cs_debug=<mask>`（`:106-116`）。

**K60 判定**：见 §2.1（581 字符 = 581 字节 < 1000；注意 `confirm_args` 追加与参数正则）。

#### 1.4.2 `docs/xnu/four-k-page-tables.md`（196 行）— 4 KiB 页表全栈要求

**定位**：Apple ARM64 多数 SoC 用 16 KiB page；非 Apple ARM64 常用 4 KiB granule；UniXNU 用 BCM2837 machine config（4 KiB layout）并 patch XNU 假设 16 KiB 的地方（`:3`）。

**硬性要求（逐条）**

1. **Granule 常量**：`BCM2837`：`ARM_PGSHIFT=12`、`ARM_PGBYTES=4096`、`TCR_EL1_BOOT TG0=0 (4 KiB)`、`TG1=2 (4 KiB)`；`VMAPPLE`：14/16384、TG0=2、TG1=1（`:5-10`）。`scripts/check-xnu-granules.py` 对两个 profile 编译 `TCR_EL1_BOOT` 并检查 TG0/TG1（`:12`）。
2. **构建隔离**：kernel 按 4 KiB 编译；page size 是 machine configuration 和 build flags 的一部分；16 KiB kernel 与 4 KiB kernel 是两次独立构建，不能混用（`:14`）。
3. **Boot page tables**：`osfmk/arm64/start.s` 在开 MMU 前构建 bootstrap page tables；pool 大小由 `BOOTSTRAP_TABLE_SIZE` 决定（`:16-18`）。`native-4k-bootstrap-capacity` 增加非 Apple 4 KiB budget：
   ```c
   #elif !defined(APPLE_ARM64_ARCH_FAMILY) && !__ARM_16K_PG__
   /* Two roots plus up to seven L2 pages per 6 GiB mapping. */
   #define BOOTSTRAP_TABLE_SIZE (ARM_PGBYTES * 16)
   ```
   （`:20-26`）。
4. **容量检查**：同一 patch 在分配新 L2 表前检查 `add $6, x25, #(BOOTSTRAP_TABLE_BYTES >> 12), lsl #12; cmp $4, $6; b.hs Lbootstrap_tables_exhausted`；耗尽时在循环中停住，cursor 和 end 地址保留在寄存器中，MMU 仍关闭，调试器可直接看寄存器（`:28-36`）。
5. **清池**：patch 清整个 reserved pool，而不是四个 16 KiB pages：`mov x2, #(BOOTSTRAP_TABLE_BYTES / ARM_PGBYTES); lsl x2, x2, #(ARM_PGSHIFT - TTE_SHIFT)`（`:38-43`）。
6. **Runtime page size**：`osfmk/arm/arm_init.c` 在 Apple 板上按 RAM size 选 page size；`native-4k-user-abi` 让 native 4 KiB build 在任何 RAM size 都用 hardware page size：`PAGE_SHIFT_CONST = ARM_PGSHIFT; page_shift_user32 = ARM_PGSHIFT;`（`:45-56`）。策略表：native 4K 任意 RAM → kernel/user32 shift 12/12；Apple 4K ≤1 GiB → 12/14；Apple 4K >1 GiB → 14/14；Apple 16K → 14/14（`:58-67`）。**Native build 必须始终 4 KiB，不能按 Apple 的 >1 GiB 切 16 KiB。**
7. **User address space**：`bsd/kern/mach_loader.c` 64-bit 进程用 `FOURK_PAGE_SHIFT`；`osfmk/arm/commpage/commpage.c` 64-bit commpage shift=12；`osfmk/vm/vm_shared_region.c` shared region submap 用 4 KiB entries；`osfmk/arm/arm_init.c` `PAGE_SHIFT_CONST`/`page_shift_user32` 跟随 `ARM_PGSHIFT`（`:69-80`）。4 KiB userspace 期望 4 KiB `mmap` alignment、4 KiB commpage shifts、4 KiB dyld shared cache layout；读 commpage 的进程 legacy/current 64-bit shift 都得到 12（`:80`）。
8. **Code signing**：`native-4k-signature-hash-cache` 六步：接受 `pageSize=14` 的 CodeDirectory on 12-bit kernel → `vn_rdwr` 读每个原厂 16 KiB block → 与 CodeDirectory hash 比较 → 从已验证 block 派生每 4 KiB page 的 digest → 存只读 kernel memory → `cs_validate_page` 从派生表服务（`:82-92`）。派生表挂在 `cs_blob`：`csb_native4k_hashes`、`csb_native4k_hashes_size`、`csb_native4k_hash_count`（`:93-100`）。页验证检查 index、offset alignment、table bounds；miss 返回 `CS_VALIDATE_TAINTED`；原厂 16 KiB block hash 失败则 blob 无表（`:101`）。Build flag `XNU_NATIVE_CS_HASH_CACHE`；`scripts/check-code-signing-granules.py` 编译实际 `cs_validate_codedirectory` gate 并检查 8 种 kernel shift/signature shift/cache mode 组合（`:103`）。
9. **Allocator alignment**：zone allocator metadata 在 secondary page；`pgz-aligned-validation` 在 page mask 前 decode PGZ：`elem = pgz_decode((vm_offset_t)addr, 1); offs = (elem & PAGE_MASK) - zone_elem_inner_offs(zone); if (from_zone_map(elem, 1)) ...`（`:105-115`）。
10. **物理地址 >4 GiB**：`pmap_sync_page_attributes_phys` 原用 32-bit shift `pp << PAGE_SHIFT`；`zzx-pmap-sync-64bit-pa` 改用 `ptoa(pp)`，在 shift 前 widen page number；DRAM 起始高于 4 GiB 的设备不能丢高位（`:117-131`）。
11. **Non-Apple platform guards**：`apple-only-cpu-tunables`（仅 `APPLE_ARM64_ARCH_FAMILY` 应用 Apple CPU tunables）、`non-apple-cache-monitor`（只在 `XNU_MONITOR` 下调 `ml_enable_monitor`、导出 cache clean symbol）、`non-apple-iommu-bootstrap`（guard UAT/SART bootstrap 和 PPL code）、`non-apple-pmap-field`（按 non-PAC layout 重命名 reserved field）、`source-machine-layer`（加 `CONFIG_APPLE_AMCC`、删 Apple-only config entries）、`native-arm-pan`（`XNU_NATIVE_PAN` 下启用 ARMv8.1 PAN）（`:133-144`）。
12. **SMMU 4 KiB tables**：`ArmSmmu4K` kit 用 4 KiB granule 构建 stage 1/stage 2 表；文件 `ArmSmmu4KProgram.c`、`ArmSmmu4KContext.c`、`ArmSmmu4KStreams.c`、`ArmSmmu4KLive.c`、`ArmSmmu4KTableMemory.c`；设备驱动通过 SMMU 映射 DMA buffers 用 4 KiB 表；touch driver 示例用 apps SMMU bypass path（`:146-158`）。
13. **Verification**：`check-xnu-granules.py`、`check-native-4k-policy.py`、`check-code-signing-granules.py`、`check-pgz-alignment-checkpoints.py`、`check-ufs-va64-evidence.py`、`qemu-entry/gdb-stop.py` + native 4K fixture（`:160-169`）。QEMU 观测期望：`TCR_EL1 TG0=0`、`TG1=2`、`SCTLR_EL1 M=1`、`TTBR0_EL1/TTBR1_EL1` 非零、`_PAGE_SHIFT_CONST/_page_shift/_page_shift_user32/_page_size = 12/12/12/4096`（`:171-179`）。
14. **New code 规则（8 条）**：用 `PAGE_SIZE`/`PAGE_SHIFT`，汇编用 `ARM_PGBYTES`/`ARM_PGSHIFT`；code signing hash shift 与 kernel page shift 分开；每个 new user map 设置 user map page shift；DMA buffers/descriptors 按 `PAGE_SIZE` 对齐；new IOMMU contexts 用 4 KiB SMMU tables；PGZ 地址先 decode 再 page mask；>4 GiB 物理地址用 `ptoa()`/`phystokv()`；每个 mapped GiB 都预算 bootstrap page tables（`:181-190`）。

**K60 判定**：见 §2.2。关键：K60 当前用本地 `PONG` machine config，不是字符串 `BCM2837`；必须证明 PONG 的 `ARM_PGSHIFT=12`（`PONG.h` 未定义 `__ARM_16K_PG__`，`osfmk/arm64/proc_reg.h` 默认走 12）并让上述补丁/检查全部适用。

#### 1.4.3 `docs/xnu/patch-reference.md`（122 行）— 补丁目录与顺序规则

**定位**：format 2 `[kernel] patch_series` 按声明顺序应用；series 可引用 profile/component patches；`unixnu status --json` 报 resolved sequence；format 1 按 `patches/xnu/*.patch` + `kits/XnuPrelink/patches/*.patch` 文件名顺序（`:3`）。

**硬性要求（逐条）**

1. **Format 2 顺序**：`[kernel] patch_series` 按声明顺序应用；component patches 参与同一 resolved order；`status --json` 打印该顺序（`:3`、`source-and-patches:21-27`）。
2. **Format 1 顺序**：`patches/xnu/*.patch` 和 `kits/XnuPrelink/patches/*.patch` 按 filename order；shell preparation 处理 late `zzw`/`zzy`/`zzz` patches 并检查已应用 patches（`:3`、`source-and-patches:32-34`）。
3. **依赖顺序**：依赖另一个 patch 的 patch 必须在它之后应用；触碰 `zzy` 或 `zzz` 修改区域的 patch 必须在它们之前应用（`:109-116`）。
4. **Patch 目录结构**（按类别）：Build/toolchain 9 项（`apple-only-cpu-tunables`、`cxx-flag-dependencies`、`external-archive-dependencies`、`kernel-sdk-root`、`local-availability`、`public-entitlements-header`、`source-machine-layer`、`disabled-deferred-reclaim`、`published-freezer-condition`）（`:5-17`）；Platform/CPU 5 项（`architectural-timer-entry`、`armvirt-platform-personality`、`native-smp-secondary`、`native-arm-pan`、`native-dt-panic-region`）（`:19-27`）；4 KiB pages 8 项（`native-4k-bootstrap-capacity`、`native-4k-user-abi`、`native-4k-signature-hash-cache`、`pgz-aligned-validation`、`zzx-pmap-sync-64bit-pa`、`non-apple-pmap-field`、`non-apple-iommu-bootstrap`、`non-apple-cache-monitor`）（`:29-40`）；Security/owner root 14 项（`native-trust-cache-runtime`、`source-corecrypto14-bootstrap`、`source-pthread-bootstrap`、`native-aes-personality`、`offline-owner-root-crypto-probe`、`offline-owner-root-binding-audit`、`offline-owner-boot-manifest`、`offline-owner-cache-carrier`、`offline-owner-systemos-mount`、`offline-owner-z-air-init`、`offline-legacy-start`、`offline-component-load-probes`、`offline-native-gpu-broker`、`sheng-platform-power`）（`:42-59`）；Graphics/display 4 行（`offline-native-gpu-broker`、`zzy-native-gpu-addon-mount`、`zzw-native-adreno-sandbox-grant`、`native-aes-personality`，其中两个重复）（`:61-68`）；Diagnostics 4 项（`offline-pgz-alignment-probe`、`native-work-interval-trace`、`native-quiet-managed-page-report`、`zzz-boot-progress`）（`:70-77`）；Behavior fixes 6 项（`native-priv-work-interval`、`native-work-interval-soft-fail`、`native-union-getattrlistbulk`、`native-union-statfs-fsid`、`null-root-media`、`published-freezer-condition`）（`:79-88`）；Mockfs 5 项（`mockfs-intermediate-lookup`、`mockfs-memory-device-width`、`mockfs-statfs`、`mockfs-typed-allocation`、`mockfs-test-file`）（`:90-98`）；Prelink 2 项（`xnu-10063.141.1-security-init.patch`、`xnu-10063.141.1-sparse-index.patch`）（`:100-107`）。
5. **新增 patch 流程**：编辑 `.cache/xnu-work` → `git diff` 生成 diff → 放 `patches/xnu/`，文件名决定正确顺序 → 重建 kernel（`:109-115`）。
6. **顺序冲突规则**：依赖 patch 之后；触碰 `zzy`/`zzz` 区域之前（`:116`）。

**K60 判定**：见 §2.3。K60 `board.toml:20` 是单一 `device:patches/xnu/series`（198 条），format 2 按文件行序，不按文件名排序；末尾 `zzz...` 系列必须保持在最后。

#### 1.4.4 `docs/xnu/source-and-patches.md`（149 行）— 源码 pin、补丁所有权与构建规范

**定位**：OS profile pin XNU 与其 ABI 输入；arm64 iPadOS 17.7.11 用 `xnu-10063.141.1`、Darwin 23.6.0、DriverKit `xnu-10063.121.3`、TrustCache `xnu-8796.101.5`；iOS16/iPadOS17 共用 `profiles/arch/arm64`；iOS/iPadOS27 用 `profiles/arch/arm64e`（`:3-7`）。

**硬性要求（逐条）**

1. **源 pin**：`feeds.toml` 提供 libplatform、libdispatch、AvailabilityVersions、libpthread、corecrypto、IOStorageFamily、edk2；format 2 OS profile 的 explicit XNU revision 优先于 source lock（`:9-11`）。
2. **Patch application**：format 2 解析 `[kernel] patch_series` 声明顺序；series 每行一个 patch path，相对 series 文件或前缀 `arch:`/`soc:`/`os:`/`device:`/`component:<ID>/`；component patches 参与同一 resolved order；`status --json` 打印顺序（`:21-27`）。
3. **Kernel preparation**：创建 `tree/.cache/xnu-work`，逐个检查/应用 patch，准备缺失的 source headers；target 拥有 generated headers 和 `tree/build` outputs（`:28-30`）。
4. **Format 1**：`patches/xnu/*.patch` 和 `kits/XnuPrelink/patches/*.patch` 按 filename order；shell preparation 处理 late `zzw`/`zzy`/`zzz`，并检查 already-applied patches（`:32-34`）。
5. **Ownership**：ARM64 profile（common architecture config + patch series）、SoC repo（hardware ops + SoC patch series）、OS profile（version-specific fixes + prelink patch selection）、Device repo（board-specific patch series）、Component repo（component-required patches）、`patches/libpthread/`、`patches/mesa/`（`:36-45`）。
6. **Add patch 流程**：先 build kernel 一次准备 `tree/.cache/xnu-work`；设 `XNU_WORK`、`DEVICE_DIR`；把要改的文件复制到临时 Git 目录，保留 XNU-relative path，先 stage baseline（示例 `PATCH_WORK=$(mktemp -d); git -C "$PATCH_WORK" init; mkdir -p "$PATCH_WORK/osfmk/arm64"; cp "$XNU_WORK/osfmk/arm64/start.s" ...; git -C "$PATCH_WORK" add osfmk/arm64/start.s`）；编辑临时副本；`git -C "$PATCH_WORK" diff -- osfmk/arm64/start.s > "$DEVICE_DIR/patches/xnu/my-change.patch"`；review 后加入 device series 并 `./unixnu build kernel`；共享改动放 owning SoC/arch/OS/component series 的 baseline 位置（`:47-72`）。
7. **Patch 内容模式**：新增 build option 的 patch 用 personality pattern `#if defined(XNU_MY_OPTION) && XNU_MY_OPTION ... #endif`；对应 `-DXNU_MY_OPTION=1` 来自 kernel script 的 `EXTRA_MAKE_ARGS`（`:74-85`）。
8. **Build flags**：`SDKROOT=iphoneos`、`ARCH_CONFIGS=ARM64`、`MACHINE_CONFIGS=BCM2837`、`KERNEL_CONFIGS=DEVELOPMENT`、`ARM64_LINK_ADDR=0xfffffff007004000`、`ARM64_PLKSEG_ADDR=0xfffffff004004000`、`DEPLOYMENT_TARGET_FLAGS="-miphoneos-version-min=17.0 -DXNU_TARGET_OS_IOS"`、`BUILD_LTO=0`、`BOUND_CHECKS=0`（`:87-103`）。`BCM2837` 承载 4 KiB layout；`BUILD_LTO=0` 保持 object files/compile records 可读且与 external archives link-compatible（`:103`）。
9. **Defconfig mapping**：`CONFIG_XNU_<NAME>`→`XNU_<NAME>`；`y`→1、`n`→0、`"text"`→text、`123`→123、`{tree}`→build tree path（`:105-117`）。
10. **Source tree 布局**：`refer/xnu/` pinned source、`.cache/xnu-work/` working clone、`.cache/fakeroot/` kernel SDK root、`.cache/sources/` restored header manifests、`build/xnu/ios-obj/` objects/compile records、`ios-sym/` symbols、`ios-dst/` install headers、`patches/xnu/` linked patches、`kits/XnuPrelink/` prelink tool and patches（`:119-132`）。
11. **Updating source 五步**：改 OS `profile.toml` 的 `[os] xnu_version` + full `xnu_revision`（format 1 改 XNU feed 的 `ref`/`commit`）→ review `darwin`/`driverkit_tag`/`trustcache_tag`/IPSW identity/prelink kernelcache pin → rebase ordered patches，更新 component/auxiliary archive builders 的 compile records → `./unixnu fetch` + `status --json` 确认 resolved XNU revision → `./unixnu kernel` 检查 link/prelink/component ABI，重建 payload/boot image 并记录验证（`:134-140`）。
12. **Prelink ABI 约束**：prelink 依赖原厂 kernelcache ABI；换 source version 时必须认证 matching kernelcache、root components、ABI inputs（`:142-143`）。

---

## 2. 对 K60 的硬性约束清单

> 本节把 26 篇文档中的“必须/不超过/只有…才”提取为可执行判定。K60 当前值来自 `E:/hackios/UniXNU-mondrian` 的 `board.toml`（format 2）与构建脚本；与文档示例不同处明确标注。

### 2.1 boot-args：581 字符是否超限

#### 2.1.1 硬限表

| 项目 | 文档硬限 | 依据 |
|---|---:|---|
| 单参数语法 | `[A-Za-z0-9_.-]+(=[A-Za-z0-9_.,-]+)?` | `docs/xnu/boot-arguments.md:22-26`；`docs/concepts/payload.md:83` |
| 拼接后命令行 | **≤1000 bytes** | `docs/xnu/boot-arguments.md:28`；`docs/concepts/payload.md:85`；CLI 错误 “Kernel command line over 1000 bytes” `docs/reference/cli.md:163` |
| DarwinBoot 复制缓冲 | **1024 bytes**（`DARWIN_BOOT_ARGS` command line @ `0x6c`） | `docs/xnu/boot-arguments.md:28`；`docs/concepts/boot-chain.md:96` |
| 参数值字符集 | `[A-Za-z0-9_.,-]+`（值内允许逗号、点、下划线、连字符） | 同上 |
| 生效优先级 | `[payload] kernel_args` < `[build] kernel_args` < `--kernel-arg`（同名后者替换） | `docs/xnu/boot-arguments.md:5`；`docs/reference/configuration.md:25` |
| `confirm_args` | 选中项追加到 entry `args` 副本，计入最终行 | `docs/reference/boot-configuration.md:176`；`docs/xnu/boot-arguments.md:16` |

#### 2.1.2 581 字符判定

**结论：不超限。**

- 581 个 ASCII 字符（含参数间单个分隔空格；boot-args 只允许 ASCII 字符集）= **581 bytes**。
- 对 1000 字节 builder 限制：`1000 - 581 = 419 bytes` 余量。
- 对 1024 字节 DarwinBoot 缓冲：`1024 - 581 = 443 bytes` 余量；若按 C 字符串保留 1 字节 NUL，则 442 bytes 余量。
- 只有当 581 是“最终拼接行”的字节数，且每个 token 都符合正则时成立。若 581 是某个参数列表的字符数但 `confirm_args` 还会追加、或某个 token 含 `+`/`:`/`/`/`@`/非 ASCII，则长度判定不能单独救它——格式会先被 payload builder 拒绝。

**K60 当前实测基线（2026-11-08）**：`board.toml:125` 的 9 个 `kernel_args`（`-v`、`native-ufs=1`、`pong_allow_unauthenticated_root=1`、`debug=0x144`、`cs_enforcement_disable=1`、`pong_software_keybag=1`、`disable_exc_resource=1`、`pong_ufs_readwrite=1`、`k60_fontscale=3`）拼接为 **169 字符**；581 字符的候选行仍比该基线多 412 字符，但离 1000 上限还有 419 字节。**结论：581 字符的 K60 boot-args 不超限，可安全打包；但必须用最终 entry args（含 confirm_args）重新计数，不能只看 board.toml 的原始列表。**

#### 2.1.3 测量与验收命令

```sh
# 在 K60 构建输出上执行：读取最终 payload 的 kernel_args 并检查长度/字符集
python3 - <<'PY'
import json, re, sys
p = "out/mondrian/ipados-16.6.1-20G81/mondrian/payload/payload.json"
args = json.load(open(p))["kernel_args"]
line = " ".join(args)
print("tokens:", len(args), "chars:", len(line), "bytes:", len(line.encode("utf-8")))
print(line)
assert len(line.encode("utf-8")) <= 1000, "over 1000-byte builder limit"
for a in args:
    assert re.fullmatch(r"[A-Za-z0-9_.-]+(=[A-Za-z0-9_.,-]+)?", a), f"bad token: {a!r}"
print("OK: <=1000 bytes and every token matches the grammar")
PY

# 检查打包进 payload 的 TOML 实际 args
mtype -i out/mondrian/ipados-16.6.1-20G81/mondrian/payload/payload.img \
  ::/EFI/UniXNU/unixnu.toml

# 改完参数必须重建两级
./unixnu payload --device ../UniXNU-mondrian --kernel-arg <name>=<value> ...
./unixnu bootimg  --device ../UniXNU-mondrian --uefi ../uefi-mondrian ...
```

#### 2.1.4 K60 的额外注意

- K60 使用 `confirm`/`confirm_titles` 时，`confirm_args` 会在启动时追加到 `args`；581 必须按“entry args + chosen confirm_args”计。
- `--kernel-arg NAME=VALUE` 只替换同名参数，不删除重复的匿名 token；K60 脚本生成的参数名必须唯一。
- `amfi_get_out_of_my_way=1` 仅诊断；K60 的 `cs_enforcement_disable=1` 同样是安全策略改变，不能作为常规 boot-args 默认值。
- 任何 boot-args 改动只改 payload/TOML 不会影响已打包的 `boot.img`；必须 `payload` + `bootimg`。

### 2.2 4K 页表：K60 必须满足的硬条件

#### 2.2.1 构建目标与 granule

| 条件 | 文档要求 | K60 判定 |
|---|---|---|
| Machine config | `MACHINE_CONFIGS=BCM2837` 是官方 4K 载体；`ARM_PGSHIFT=12`、`ARM_PGBYTES=4096`、`TCR_EL1_BOOT TG0=0/TG1=2` | K60 脚本实际 `MACHINE_CONFIGS=PONG`（`scripts/build-xnu-4k-baseline.sh:7,234,1109`），`DEVELOPMENT_ARM64_PONG`。必须验证 PONG 等价满足 4K 常量；`PONG.h` 未定义 `__ARM_16K_PG__`，`osfmk/arm64/proc_reg.h` 因此走 `ARM_PGSHIFT 12` |
| 16K vs 4K | 两次独立构建，不能混用 | K60 必须始终使用 4K build；不得复用 VMAPPLE/16K 产物 |
| Bootstrap pool | `BOOTSTRAP_TABLE_SIZE = ARM_PGBYTES * 16` = 64 KiB；分配新 L2 前检查容量；耗尽在 `Lbootstrap_tables_exhausted` 停住 | K60 4.75 GiB 当前窗口必须通过；若提升到 12 GiB，按注释“2 roots + 每 6 GiB 最多 7 张 L2”的 16 页预算正好是边界，必须实测不触发 exhaustion（还要计 MMIO mappings） |
| Runtime page shift | `native-4k-user-abi`：`PAGE_SHIFT_CONST=ARM_PGSHIFT`、`page_shift_user32=ARM_PGSHIFT`，任意 RAM size 都是 12 | K60 必须启用该 patch；不能沿用 Apple 4K 的“>1 GiB 切 16K”策略 |
| User map | 64-bit `FOURK_PAGE_SHIFT`；commpage 12；shared region 4K；mmap 4K align；dyld cache 4K | K60 的 4K userland 必须全部满足；否则 dyld/commpage 崩溃 |
| Code signing | `native-4k-signature-hash-cache` / `XNU_NATIVE_CS_HASH_CACHE`；16K CodeDirectory block → 4K derived hashes | K60 defconfig 已 `CONFIG_XNU_NATIVE_CS_HASH_CACHE=y`；必须在 series 中保留该 patch |
| PGZ | `pgz-aligned-validation`：先 `pgz_decode` 再 page mask | K60 必须启用；否则 zone metadata 误判 |
| PA >4 GiB | `zzx-pmap-sync-64bit-pa` 用 `ptoa()` | K60 的 `/memory/reg` 有 `0x800000000`/`0x900000000`/`0x840000000` 等高段，必须启用；不能用 `pp << PAGE_SHIFT` |
| SMMU | `ArmSmmu4K` 4 KiB stage1/stage2 tables | K60 的 GPU/UFS DMA 必须用 4K SMMU 表；`CONFIG_XNU_SMMU4K_PROBE=n` 只是 probe 关闭，不代表表可 16K |
| Non-Apple guards | 6 个 patch（cpu tunables/cache monitor/iommu bootstrap/pmap field/source machine layer/native PAN） | K60 是 non-Apple ARM64；必须全部在 series |
| 代码新规 | 用 `PAGE_SIZE`/`PAGE_SHIFT`、汇编 `ARM_PGBYTES`/`ARM_PGSHIFT`、DMA 按 `PAGE_SIZE` 对齐、每个映射 GiB 预算 bootstrap | K60 新增驱动/补丁必须逐条遵守 |

#### 2.2.2 验证命令

```sh
# 在 UniXNU 主仓脚本目录执行；对实际 profile 检查 granule/TCR 常量
python3 scripts/check-xnu-granules.py
python3 scripts/check-native-4k-policy.py
python3 scripts/check-code-signing-granules.py
python3 scripts/check-pgz-alignment-checkpoints.py

# QEMU 原生 4K fixture 检查寄存器
python3 scripts/qemu-entry/gdb-stop.py --help
```

期望（文档 `four-k-page-tables.md:171-179`）：

| 寄存器/符号 | 期望值 |
|---|---|
| `TCR_EL1` TG0 | 0（4 KiB） |
| `TCR_EL1` TG1 | 2（4 KiB） |
| `SCTLR_EL1` M | 1（MMU enabled） |
| `TTBR0_EL1`、`TTBR1_EL1` | 非零 |
| `_PAGE_SHIFT_CONST`、`_page_shift`、`_page_shift_user32`、`_page_size` | 12、12、12、4096 |

#### 2.2.3 K60 特有的三条硬判断

1. **`PONG` 不是 `BCM2837`**：文档只把 `BCM2837` 列为 4K 载体，但 K60 本地脚本使用 `PONG` machine config。必须把 `PONG` 当作“必须证明等价的 4K profile”，在 `status --json`/构建日志中确认实际 `MACHINE_CONFIGS`，并在 `check-xnu-granules.py` 中覆盖它；不能因为名字不是 BCM2837 就跳过检查。
2. **12 GiB 接近 bootstrap 容量的边界**：`BOOTSTRAP_TABLE_SIZE (ARM_PGBYTES * 16)` 按注释预算为 2 roots + 每 6 GiB 7 张 L2；K60 若把 `owned_memory_size` 从 `0x130000000`（4.75 GiB）提高到 12 GiB，必须先用 boot progress/`Lbootstrap_tables_exhausted` 确认不耗尽；MMIO 映射也会占表。
3. **高 DRAM 必须用 `ptoa()`**：K60 的内存不是单一低 4 GiB 段；任何 `pmap_sync_page_attributes_phys` 类路径、DMA descriptor、SMMU 映射都必须保留高位物理地址。

### 2.3 补丁顺序：K60 的 format 2 规则

#### 2.3.1 顺序判定

| 项目 | 文档规则 | K60 现状/判定 |
|---|---|---|
| 格式 | `schema_version=2` → `[kernel] patch_series` 按声明顺序，不是文件名排序 | K60 `board.toml:1 schema_version=2`、`:20 patch_series=["device:patches/xnu/series"]`；按 `series` 文件行序 |
| 层合并 | ARM64 → SoC → OS → device；tables merge，arrays replace；series 支持 `arch:`/`soc:`/`os:`/`device:`/`component:<ID>/` | K60 目前只有 `device:` 一个 series；未来加 arch/soc/os series 时按该顺序拼接，数组替换不是追加 |
| 依赖 | 依赖 patch 必须在被依赖者之后 | K60 新 patch 必须插到其依赖的 patch 之后；不能依赖文件名巧合 |
| `zzy`/`zzz` | 触碰其修改区域的 patch 必须在它们之前 | K60 `series` 末尾是 `zzzz...pong-gpu-scanout` 等 zzz 系列；任何改同一区域的 patch 要插在它们前面 |
| 验证 | `unixnu status --json` 的 `patch_order` 是唯一权威 | K60 每次 build 前必须 `status --json | jq '.patch_order'`，并与 `patches/xnu/series` 对照 |
| Format 1 | 若设备是 format 1：`patches/xnu/*.patch` + `kits/XnuPrelink/patches/*.patch` 按文件名排序；late zzw/zzy/zzz 由 shell 处理 | K60 不是 format 1；此条仅作为迁移/兼容参考 |

#### 2.3.2 K60 当前 series 事实

- `patches/xnu/series` 现有 **198 条**启用项（不含空行/注释）；首项 `apple-only-cpu-tunables.patch`，末项 `zzz-boot-progress.patch`；末尾连续多个 `zzzz...pong-*`（GPU scanout、gpu-only-display、source-row-pitch、touch-console、goodix-resume、physical-keys、container-path）。
- K60 的 `board.toml:20` 只有一个 `device:patches/xnu/series`，因此 `series` 文件的行序就是最终顺序；不要用 `Get-ChildItem | Sort-Object` 之类的目录排序替代。
- 当前 K60 系列里有 `native-4k-bootstrap-capacity.patch`、`native-4k-user-abi.patch`、`native-4k-signature-hash-cache.patch`、`pgz-aligned-validation.patch`、`zzx-pmap-sync-64bit-pa.patch` 等 4K 补丁（见 `patches/xnu/`），必须保持它们的应用位置；任何 rebase/插入都要 `git apply --check` 通过且 `status --json` 顺序不变或按预期变化。

#### 2.3.3 补丁操作的硬步骤

```sh
# 1) 构建一次，准备 tree/.cache/xnu-work
./unixnu kernel --device ../UniXNU-mondrian

# 2) 查看当前 resolved patch order（唯一权威）
./unixnu status --json --device ../UniXNU-mondrian | jq '.patch_order'

# 3) 修改后检查 patch 能否应用（不要 fuzz）
git -C out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work apply --check /path/to/my-change.patch

# 4) 重建 kernel 并检查 patch application/link/prelink
./unixnu kernel --device ../UniXNU-mondrian
```

### 2.4 其他跨文档硬约束（K60 必须同时满足）

| 领域 | 硬约束 | 依据 | K60 动作 |
|---|---|---|---|
| BootShim / boot image | BootShim 按 Mu-Silicium 的 `FD_BASE`/`FD_SIZE` 汇编；kernel 字段 gzip(BootShim + firmware volume)；DTB 追加 | `concepts/boot-chain.md:5-20` | 用 mondrian 的 firmware base/size；构建后核对 `boot.json` 的 `fd_sha256`/`dtb_sha256`/`shim_bytes` |
| DarwinBoot kernel 校验 | `MH_MAGIC_64`、`CPU_TYPE_ARM64`、`MH_EXECUTE`、1 个 `LC_MAIN`、≥1 `LC_SEGMENT_64`；入口在可执行段；segments 页对齐、不重叠、≤256 MiB 窗口；ADT 必读；trust cache 可选 | `concepts/boot-chain.md:67-82` | K60 prelinked `kernel.macho` 必须由 `prelink` 生成并满足这些 Mach-O 条件；不要手工拼 kernel |
| DarwinBoot 窗口 | 默认 256 MiB；ADT `/chosen/darwinboot-memory-size` 可请求更大 | `concepts/boot-chain.md:72`；`guide/boot.md:85` | K60 `owned_memory_size=0x130000000`（4.75 GiB）必须在 ADT 中有该属性；12 GiB 目标同样 |
| Payload FAT | payload 是 FAT 卷；必须含 `EFI/UniXNU/unixnu.toml`、kernel、ADT、可选 trustcache、Data seed | `concepts/payload.md:11-17` | K60 `size_mib=192`；`bootimg --ramdisk` 指向 payload.img |
| Payload 占位 | `RAMDisk`/`PackedRAMDisk`/`TrustCache`/`darwinboot-memory-size` 按输入必须存在，否则 `EFI_COMPROMISED_DATA` | `concepts/payload.md:68-77` | K60 ADT generator 必须为每个实际输入生成占位；不要只生成 default |
| Trust cache 结构 | count 1–128；每 cache offset；version 2；entry 24 bytes；hash type 1–4；hash 升序 | `concepts/payload.md:91-100` | 若 K60 加 trust cache，bundle 必须满足；`[payload] trust_cache_sha256` 必须 pin |
| Data seed | `CONFIG_XNU_OWNER_DATA_MOUNT` 时必须有 seed；packed `DBRDISK1` extent table；Data ≤1 TiB；>2 GiB 只保留非零页 | `concepts/payload.md:106-122` | K60 Data seed 必须匹配其 payload 配置；raw NXSB 需先适配工具（见仓库状态文档） |
| Prelink kernelcache pin | `[kernel.prelink] kernelcache_sha256` 拒绝不同 kernelcache | `concepts/prelink.md:66-75` | K60 `board.toml` 必须 pin 20G81 kernelcache；换 IPSW 同步更新 |
| Prelink early security | `early_security_init` 选中的 component 必须有 `AppleSecurityExtension=true` | `concepts/prelink.md:62-64` | K60 选 AMFI 时必须验证 metadata |
| 4K code signing | 16K CodeDirectory → 4K derived table；失败 block → `CS_VALIDATE_TAINTED` | `concepts/security.md:24-34`；`xnu/four-k-page-tables.md:82-103` | K60 defconfig `XNU_NATIVE_CS_HASH_CACHE=y`；不要关 |
| AMFI / owner root | `/chosen/amfi-only-platform-code`；`offline-owner-root-*` 六补丁 | `concepts/security.md:36-49` | K60 的 owner root 路径按需启用；不在 iOS16 主线默认全开 |
| Userdata manifest | header 4096 bytes 零填充 1 MiB；首 window 0x100000；每 window 1 MiB 对齐；capacity 公式 | `concepts/userdata.md:7-46` | K60 32 GiB 容量；任何生成器必须写对 header/offset |
| Root UUID | `/chosen/root-matching` 的 `IOPropertyMatch/UUID` 必须等于 OS window UUID | `concepts/userdata.md:48-62`；`guide/userdata.md:47-58` | K60 从 20G81 OS image 取 UUID；改后重建 payload/bootimg |
| 构建前置 | Python ≥3.11；macOS Xcode 或 Linux toolchain；mtools/dtc/fastboot；`--skip-setup`/seed-grow 仅 macOS | `guide/requirements.md:14-74` | K60 构建环境按此选；无 Mac 用 macOS runner |
| 输出验证 | `status --json` 检查 device/OS/profile/source/patch_order；报告 hash 与输入比对 | `reference/index.md:39-58`；`reference/output-layout.md:101-144` | K60 每次 build 保存 `boot.json`/`payload.json`/`userdata-root.json` |

---

## 3. 覆盖清单（26/26）

### 3.1 清单生成命令

```sh
find docs/concepts docs/guide docs/reference docs/xnu -name '*.md' | sort
```

### 3.2 逐篇核对

- [x] `docs/concepts/boot-chain.md` — 121 行 / 5,076 B — 已全文读
- [x] `docs/concepts/payload.md` — 132 行 / 5,945 B — 已全文读
- [x] `docs/concepts/prelink.md` — 98 行 / 4,070 B — 已全文读
- [x] `docs/concepts/security.md` — 148 行 / 7,352 B — 已全文读
- [x] `docs/concepts/userdata.md` — 95 行 / 4,025 B — 已全文读
- [x] `docs/guide/boot.md` — 174 行 / 8,872 B — 已全文读
- [x] `docs/guide/build-kernel.md` — 160 行 / 9,219 B — 已全文读
- [x] `docs/guide/debugging.md` — 393 行 / 19,238 B — 已全文读
- [x] `docs/guide/mobilegestalt.md` — 101 行 / 5,717 B — 已全文读
- [x] `docs/guide/overview.md` — 16 行 / 263 B — 已全文读（重定向占位页）
- [x] `docs/guide/requirements.md` — 126 行 / 8,394 B — 已全文读
- [x] `docs/guide/skip-setup.md` — 127 行 / 5,735 B — 已全文读
- [x] `docs/guide/userdata.md` — 130 行 / 5,583 B — 已全文读
- [x] `docs/reference/boot-configuration.md` — 303 行 / 9,087 B — 已全文读
- [x] `docs/reference/cli.md` — 171 行 / 7,378 B — 已全文读
- [x] `docs/reference/components.md` — 85 行 / 3,668 B — 已全文读
- [x] `docs/reference/configuration.md` — 264 行 / 9,319 B — 已全文读
- [x] `docs/reference/glossary.md` — 43 行 / 2,200 B — 已全文读
- [x] `docs/reference/index.md` — 59 行 / 4,099 B — 已全文读
- [x] `docs/reference/output-layout.md` — 154 行 / 3,918 B — 已全文读
- [x] `docs/reference/qemu.md` — 131 行 / 5,279 B — 已全文读
- [x] `docs/reference/troubleshooting.md` — 100 行 / 6,231 B — 已全文读
- [x] `docs/xnu/boot-arguments.md` — 124 行 / 5,856 B — 已全文读
- [x] `docs/xnu/four-k-page-tables.md` — 196 行 / 7,626 B — 已全文读
- [x] `docs/xnu/patch-reference.md` — 122 行 / 6,582 B — 已全文读
- [x] `docs/xnu/source-and-patches.md` — 149 行 / 6,521 B — 已全文读

### 3.3 统计

| 目录 | 文件数 | 已读 | 覆盖率 |
|---|---:|---:|---:|
| `docs/concepts` | 5 | 5 | 5/5 |
| `docs/guide` | 8 | 8 | 8/8 |
| `docs/reference` | 9 | 9 | 9/9 |
| `docs/xnu` | 4 | 4 | 4/4 |
| **合计** | **26** | **26** | **26/26（100%）** |

### 3.4 复核记录

- 读取方式：对每个路径调用 `read` 全文（无 `limit` 截断）；所有文件均返回 `(End of file - total N lines)`。
- 行数/字节数由 `[System.IO.File]::ReadAllLines(...).Count` 与文件长度复核，和 `read` 返回的行数一致（26 个文件共 3,722 行、167,253 bytes）。
- 本文只新增 `docs/plans/DOCS-CORE-ALL.md`；未修改 `E:/hackios/UniXNU` 或 `E:/hackios/UniXNU-mondrian` 的其他文件。
