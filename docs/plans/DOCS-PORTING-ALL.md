# DOCS-PORTING-ALL：UniXNU 移植文档全量阅读（30/30）

> 阅读日期：2026-11-08
> 来源仓库：`E:/hackios/UniXNU` @ `75ae626a12764c706fc0b94c52a3eea09447dbaa`
> 目标仓库：`E:/hackios/UniXNU-mondrian`（分支 `fix/k60-measured-high-window`）
> 范围：`docs/porting/` 26 篇、`docs/contributing/` 2 篇、`docs/building.md`、`docs/index.md`，共 30 篇。
> 方法：每篇从第 1 行读到 EOF，按行数、SHA-256 前缀核对；逐篇记录流程要点、K60 可执行项、16.6.1/20G81 适用性。

## 0. 先给结论

1. 这套文档描述的是 **UniXNU format 2 的通用移植规范**，不是 K60 专属手册。官方示例栈以 SM8550 / sheng / iPadOS 17.7.11-21H461 与 iPadOS 27.0.1-24A446 为主；文档中几乎不出现 `16.6.1` / `20G81`。
2. K60 当前 `board.toml` 的 `os_profile = "ipados-16.6.1-20G81"`、`soc = "SM8475"` 在文档中没有对应示例。**通用流程可以直接套用，所有组件级结论必须按 SM8475/A730/QCA6490/AW882xx 重新验证**，不能把 17/27 的通过记录当 16.6.1 的资格。
3. K60 仓库的 format 2 外形基本成立（`board.toml`、`feeds.toml`、`unixnu.lock`、`porting.toml`、`dts/`、`patches/xnu/series` 都在），但**完成度与文档要求有明显差距**：`scripts/package.sh`、`.github/workflows/package.yml`、`[package]`、`package/Kit.toml`、`[firmware] preflight` 均缺失；`porting.toml` 13 个 area（文档要求 14 个，缺 `cellular`）；`[components]` 只有 4 项。
4. 文档中反复强调的三个硬规则对 K60 全部成立：数组覆盖是**整体替换**不是追加；`porting.toml` 的 status 必须由证据支撑；`scripts/package.sh` 必须逐字复制模板，板子只改 `board.toml`。
5. 文档没有覆盖 K60 当前最关键的 pong userland `apply()` / OS 窗口改写流程；这部分仍以 `docs/plans/APPLY-PIPELINE.md` 为准，不能从这 30 篇推出替代方案。

---

## 一、逐篇摘要（30/30）

### 01. `docs/porting/index.md`（31 行）

**流程/规范要点**
- UniXNU 是类似 OpenCore 的通用 UEFI 环境与驱动加载系统，目标是在非 Apple ARM64 硬件上启动 iOS/macOS。
- 六层栈：Android bootloader → BootShim + UEFI 固件 → UniXNU 启动管理器 → DarwinBoot → 打过补丁的 XNU → IPSW userland。
- 每层都有明确来源、输出与交接：`boot.img`、`SILICIUM_UEFI.fd`、`UniXNU.efi`、DarwinBoot、`kernel.macho` + ADT、`OS` / `SystemOS`。
- 共享代码在 UniXNU 与组件仓库；SoC 仓库提供平台支持；设备仓库提供板级配置、驱动与打包。
- 入口下一步固定指向 `Port a device`（`steps.md`）。

**K60 可执行项**
- 无新增命令。用于核对四层仓库映射：`UniXNU`（框架）/ `UniXNU-sm8475-common`（SoC）/ `UniXNU-mondrian`（设备）/ `uefi-mondrian`（固件）。
- 核对输出路径应为 `out/mondrian/ipados-16.6.1-20G81/mondrian/`，不是 README 里残留的 22H374 路径。

**iOS 16.6.1/20G81 适用性**：直接适用。六层架构不随 OS 版本变化；K60 第 4 层使用 `DarwinBoot22`，仍符合该模型。

### 02. `docs/porting/steps.md`（184 行，重点）

**流程/规范要点**
- 八步：1 收集设备输入 → 2 选择共享支持 → 3 创建设备仓库 → 4 解析并检查构建 → 5 准备 DTS 与固件 → 6 按依赖顺序适配驱动 → 7 构建并启动 → 8 完成并发布仓库。
- 每步都有明确的 Result；新移植与迁移最终都走同一套 `device-repository#completion` 要求。
- 第 1 步要求记录 SoC、CPU 布局、RAM 保留、中断控制器、存储、面板、触摸、无线芯片与固件版本；边收集边写 `porting.toml`。
- 第 2 步按 `profiles/arch/arm64` → `UniXNU-<soc>-common` → `profiles/os/<profile>` → `UniXNU-<device>` → 组件仓库 → `uefi-<device>` 分层选择。
- 第 3 步模板默认 SM8550 + iPadOS 17.7.11；复制 `examples/device`，改 `DEVICE`、defconfig、DTS 文件名；填 `board.toml`、`feeds.toml`、`kernel.defconfig`、`device_tree.source`、DTS、`proprietary-files.txt`、`porting.toml`、README、`AGENTS.md`；最后删除 `board.example = true`。
- **数组替换规则**：`[components] include`、`config_fragments`、`patch_series`、`archives` 等普通数组在覆盖时整体替换，必须写全量。
- 第 4 步命令：`./unixnu defconfig "${DEVICE}_defconfig" -D "../UniXNU-$DEVICE"`、`./unixnu fetch`、`./unixnu status --json`、`./unixnu tree`；组装树在 `out/<device>/<os_profile>/<config>/tree/`。
- 第 6 步驱动顺序：platform/memory → storage → display/brightness → input → GPU → Wi-Fi → Bluetooth → USB → DSP/audio/power；每条能力必须有独立配置与验证入口。
- 第 7 步构建顺序：kernel → package → firmware → payload → userdata（如需）→ boot image；改 boot args 后必须重跑 `payload` 与 `bootimg`。
- 第 8 步：完成仓库检查、源固定、record 校验、发布，并加 GitHub topic `unixnu`。

**K60 可执行项**
- `DEVICE=mondrian`、`DEVICE_DIR=../UniXNU-mondrian`、`DEFCONFIG=mondrian_defconfig`。
- 依次执行：
  ```sh
  ./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
  ./unixnu fetch -D ../UniXNU-mondrian
  ./unixnu status --json -D ../UniXNU-mondrian
  ./unixnu tree -D ../UniXNU-mondrian
  ```
- 核对 `board.toml` 的 `name = "mondrian"`、`kit = "mondrian"`、`soc = "SM8475"`、`soc_source = "sm8475"`、`os_profile = "ipados-16.6.1-20G81"`、`device_tree.source = "device:dts/mondrian.dts"`。
- 核对 `configs/mondrian_defconfig` 被 `kernel.defconfig` 选中；`patches/xnu/series` 每行一个补丁且文件存在。
- 每次改 `board.toml` 的 `kernel_args` 后重跑 `./unixnu payload` + `./unixnu bootimg`。

**iOS 16.6.1/20G81 适用性**：流程直接适用。模板默认的 SM8550 / iPadOS 17.7.11 不适用；第 2 步提到的 arm64e 只针对 iOS/iPadOS 27，K60 16.6.1 保持 arm64。

### 03. `docs/porting/bring-up.md`（155 行，重点）

**流程/规范要点**
- Bring-up 分 7 个阶段，每阶段有可见结果与日志行，必须逐段隔离。
- Stage 1 UEFI：固件卷大小匹配 `[uefi_fd] size`、boot image header 匹配 bootloader、`fastboot boot` 不复位、帧缓冲或串口有输出、块设备与 payload 卷可见。
- Stage 2 UniXNU：串口行以 `UNIXNU:` 开头，日志报告 entry/driver/patch/ACPI/slice/kit 计数，菜单列出预期条目；最小测试用空 ramdisk。
- Stage 3 Payload：UniXNU 读到 `unixnu.toml`，`xnu` 条目存在，payload report 哈希匹配，ADT sidecar 与 kernel 同目录。
- Stage 4 DarwinBoot：串口行以 `DARWINBOOT:` 开头，打印 virtual/physical base、arguments 地址、entry 地址、framebuffer base/width/height/depth，异常级别 EL1，bootstrap 页表到达 kernel entry；拒绝时打印 `DARWINBOOT: boot refused: <status>; firmware retained`。
- Stage 5 Kernel entry：kernel 打印版本与 boot args；bootstrap 页表映射 kernel window；platform expert 匹配 ADT root；`/cpus`、`/arm-io`、`/defaults`、`/options`、NVRAM proxy 都在；缺 provider 会 panic 并点名 provider。
- Stage 6 Storage/root：块驱动打印 link speed 与 command queue；分区方案发布 `OS` 和 `SystemOS`；root volume UUID 匹配 `root_match_volume_uuid`；XNU 挂 root 并启动 `launchd`。
- Stage 7 Userland：`launchd` 从 root 卷启动、Data 卷挂载、显示服务器或控制台输出、boot progress 记录最后检查点；用 `boot-progress=2` 与诊断 boot args。
- 失败隔离表：无固件输出→boot image header/firmware base；有固件无菜单→GOP/UniXNU 驱动/`unixnu.toml`；有菜单无 payload→卷标/FAT/entry path；payload 无 DarwinBoot→loader protocol；DarwinBoot 拒绝→Mach-O/ADT/trust cache；kernel 无日志→boot args/serial/framebuffer；panic 点名 provider→ADT 节点/驱动 archive/kernel flag；无 root→userdata image/UUID/分区容量。
- QEMU 先于硬件：`JOBS=8 bash package/Scripts/smoke.sh`，日志/截图在 `package/Build/Smoke/`。

**K60 可执行项**
- `fastboot boot out/mondrian/ipados-16.6.1-20G81/mondrian/boot/boot.img`。
- 屏幕是唯一日志：进 UniXNU 菜单后 `Tools → Advanced Logger` 抓固件日志；内核阶段用 panic 屏/最后一行文本。K60 无 UART，不能按文档假设串口。
- 逐阶段核对：`UNIXNU:` 行 → `xnu` 条目 → `DARWINBOOT:` 行与 EL1 → kernel 版本行 → `/cpus`/`/arm-io` 等 ADT 节点 → `OS`/`SystemOS` → `launchd`。当前硬阻断在 Stage 7 的 `launchd` SIGSEGV，不在前 6 段。
- 改 boot args 后必须 `./unixnu payload` + `./unixnu bootimg`，再 `fastboot boot`。

**iOS 16.6.1/20G81 适用性**：直接适用。注意 K60 的 Darwin 22 boot_args ABI 是 `0x2e0`/608 字节，文档按通用流程描述，不涉及 0x480/1024（那是 Darwin 24）。

### 04. `docs/porting/device-repository.md`（505 行，重点）

**流程/规范要点**
- 设备仓库固定布局：`AGENTS.md`、`README.md`、`.gitignore`、`board.toml`、`porting.toml`、`.github/workflows/porting-record.yml`、`.github/workflows/package.yml`、`feeds.toml`、`configs/<device>_defconfig`、`dts/<device>.dts`、`patches/xnu/series`、`scripts/package.sh`、`proprietary-files.txt`、`package/`、`local.toml.example`、`unixnu.lock`。
- 完成检查分三组：tracked files、resolve/verify、publish/label；每组有明确 required result。
- `board.toml` 关键段：`[board]`（name/soc/soc_source/os_profile/description/kit/example）、`[ipsw]`（url/product/version/build/device_class/chip_id/board_id/fetch/sha256）、`[userdata]`（first_lba/last_lba/lba_bytes/windows）、`[kernel]`（defconfig/archives/prelink/config_fragments/patch_series）、`[firmware]`（config/dsc/fd/preflight/submodules/patches/packages/defines）、`[bootimg.image]`、`[payload]`、`[payload.adt]`。
- 解析顺序：`UniXNU/profiles/arch/arm64/profile.toml` → SoC `soc.toml` → `profiles/os/<os_profile>/profile.toml` → 设备 `board.toml`；表按键合并，普通数组整体替换，组件依赖按构建顺序追加。
- `[kernel] config_fragments` 按列表顺序应用，最后应用设备 defconfig；`patch_series` 每行一个补丁，前缀 `arch:`/`soc:`/`os:`/`device:`/`component:<ID>/path` 选择来源。
- `feeds.toml` 的 source kind：`driver`、`kit`、`patch`、`script`、`package`、`refer`、`soc`；`local` 键或 `local.toml` 提供本地覆盖，优先级从命令行到 git source 依次降低。
- `package/` 在组装树中变成 `kits/<board.kit>`；`Kit.toml` 的 `[match]`（arch/fdt_compatible/firmware_vendor/requires_protocol）与 `[[driver]]`/`[[overlay]]`/`[[kext]]`。
- 发布：`gh repo edit "$REPOSITORY" --add-topic unixnu`，并确认 `porting-record` workflow 通过。
- `proprietary-files.txt` 记录每个固件文件、来源、哈希；设备仓库 `.cache/firmware` 被 build tree 链接复用。

**K60 可执行项**
- 补齐缺失文件：`scripts/package.sh`（从 `templates/package.sh` 原样复制）、`.github/workflows/package.yml`、`package/Kit.toml`；`board.toml` 增加 `[package] unixnu = "../UniXNU"` 与 `[package.defconfig]`。
- 核对 `[components] include` 当前只有 `ArmDTPlatform`、`ArmCpu`、`XnuPrelink`、`PongUfs`；按实际启用的显示/输入/GPU/网络/音频/电源驱动补全（文档要求每个 selected component 及 dependency 都被 area 覆盖）。
- `[firmware]` 当前无 `preflight`；如 `uefi-mondrian` 有板级检查脚本，补 `preflight = ["scripts/check-mondrian.py"]`（路径按实际）。
- 运行：
  ```sh
  ./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
  ./unixnu fetch -D ../UniXNU-mondrian
  ./unixnu status --json -D ../UniXNU-mondrian
  ./unixnu tree -D ../UniXNU-mondrian
  python3 scripts/porting-record.py check --device ../UniXNU-mondrian
  ```

**iOS 16.6.1/20G81 适用性**：直接适用。文档示例 OS 是 iPadOS 17.7.11，但 profile 层机制对 16.6.1 同样成立；K60 的 `ipados-16.6.1-20G81` 是自定义 profile，字段可照填。

### 05. `docs/porting/device-tree.md`（308 行，重点）

**流程/规范要点**
- Format 2 先用 `dtc` 编译硬件树（SoC DTSI + board DTS）成 `device-tree/hardware.dtb`，再由公共 ADT generator 加上 OS profile 与 payload 输入生成 `kernel.macho.adt`。
- 硬件绑定表：字符串类属性（`compatible`、`device_type`、`reg-names`、`interrupt-names`、`clock-names`、`method`）按 NUL 结尾字符串编码；单 cell 属性（`phandle`、`#interrupt-cells`、`clock-frequency`、`timebase-frequency` 等）转 little-endian u32；`reg` 按父节点 cell 宽度翻译成物理 u64 地址/大小对；`unixnu,adt-name` 导出为 `/arm-io` 下子节点名；`unixnu,cluster-type` 为 `"E"` 或 `"P"`，ADT 中为小端 u32 字符。
- 每个有翻译的 bus 必须声明 `ranges`；空 `ranges` 表示 identity mapping；每个 register range 必须有匹配翻译；引用 provider 必须有唯一非零 phandle 且 argument-cell 数匹配。
- 必需顶层节点：`/chosen`（`random-seed`、CHRP NVRAM proxy、DRAM 描述、`osenvironment`）、`/cpus`（每核一个 `cpuN`）、`/arm-io`（`#address-cells`、`#size-cells`、`ranges`）、`/defaults`、`/options`。缺一个 platform expert `configure()` 就失败。
- `/chosen` 关键属性：`random-seed`（64 字节）、`unique-chip-id`（64-bit，与 `chip-id` 一起 seed `IOPlatformUUID`）、`chip-id`（32-bit）、`osenvironment`（`main`/`recoveryos`/`ramdisk`）、`dram-base`/`dram-size`（64-bit）、`crypto-hash-method`、`root-matching`、`ephemeral-storage`、`darwinboot-memory-size`（256 MiB 到 8 GiB，2 MiB 步进）、`amfi-only-platform-code`、`boot-manifest-hash`。
- `/chosen/memory-map` 占位符：`RAMDisk`、`PackedRAMDisk`、`TrustCache` 各 16 字节；缺占位符 DarwinBoot 返回 `EFI_COMPROMISED_DATA`。
- CPU：第一个启用 CPU 是 boot CPU，`reg` 为其 MPIDR affinity；多 CPU 必须有 `/psci`，`method = "smc"` 或 `"hvc"`。
- `arm-io`：公共 generator 把所有导出 register 从最低（向下取整到 16 MiB）到最高合成一个 window；XNU 把 window base 当 SoC base，且必须非零，导出寄存器低于 16 MiB 是错误。
- `/product` 供 product-name/model，`/buttons` 供 button-names/home-button-type；`/defaults` 如 `sleep-disabled = 1`。
- 启动镜像 DTB 与固件 DTB 是两份输入；`[[bootimg.dtb_node]]` 由 `fdtput` 应用并校验整数属性回读；`dt_patch` 支持 `set`/`delete-prop`/`add-node`/`delete-node`/`overlay`。

**K60 可执行项**
- 编译检查：
  ```sh
  dtc -I dts -O dtb -i ../UniXNU-sm8475-common/dts -o /tmp/mondrian.dtb dts/mondrian.dts
  dtc -I dtb -O dts /tmp/mondrian.dtb
  ```
- 确认 `dts/mondrian.dts` 只有一个 `/memory` 节点、一个连续 `reg`（当前 `memory@900000000` 为 5 GiB arena，不是整机 12 GiB 声明）。
- 确认 SoC DTSI 的 CPU 节点带 `unixnu,cluster-type`；当前 `sm8475.dtsi` 8 个 CPU 全部是 `"P"`，与文档的 E/P 两簇调度模型不符，需按实际 A510/A710/X2 分组复核后修改。
- 确认 `/chosen` 的 `chip-id`（`board.toml` 当前 `"8015"`）、`unique-chip-id`（构建时 `--unique-chip-id`）、`root_match_volume_uuid`（`C5DAF029-2070-4F68-B3CC-1D1320344CF0`）与 payload ADT 输入一致。
- `darwinboot-memory-size` 当前 `owned_memory_size = "0x130000000"`（4.75 GiB），在文档允许的 256 MiB–8 GiB 范围内。
- 跑 `./unixnu payload` 后用 `mtype`/`mcopy` 抽取 `payload.img` 里的 `kernel.macho.adt` 与 `device-tree/hardware.dtb` 对照必需节点。

**iOS 16.6.1/20G81 适用性**：直接适用。ADT 格式与 Darwin 22 无关；K60 的 `DarwinBoot22` 读取同一 sidecar。注意文档的 8 GiB 窗口上限，12 GiB 单窗口在物理上不成立。

### 06. `docs/porting/migration.md`（517 行，重点）

**流程/规范要点**
- 迁移目标：把 format 1 设备仓库转成 format 2，得到固定 SoC source、board DTS、完整组件选择、可重复的 kernel/firmware/payload 命令。
- 9 步：记录当前配置 → 选 SoC/OS profile → 组件名映射 → 编辑 `board.toml` 与 kernel 输入 → DTS 转换 → 解析迁移配置 → 准备 firmware/local inputs → 按依赖构建 → 更新 record/CI/文档。
- 组件 canonical 名映射：`NativeAdreno`→`Adreno740`、`NativeMetal`→`AdrenoMetal`、`NativeUfs`→`ShengUfs`、`NativeHidInput`→`ShengHidInput`、`NativeNovatekTouch`→`ShengNovatekTouch`、`NativeGeniSpi`→`QcomGeniSpi`、`NativeMobileDisplay`→`GopFramebuffer`、`NativeAES`→`SoftwareAES`、`NativeKeyStoreEvents`→`AppleKeyStoreState`、`NativeRamBlock`→`RamBlock`、`NativeVirtioBlock`→`VirtioMmioBlock`、`NativeVirtioConsole`→`VirtioMmioConsole`、`NativePrelink`→`XnuPrelink`、`NativeWifi`→`Ath12kWifi`。
- `board.toml` 迁移示例：`schema_version = 2`、`[board]`、`[components] include`、`[kernel] config_fragments/patch_series`、`[device_tree] source/include_dirs`。
- 数组替换：components、fragments、patch series、archives 都是整体替换；每个 kernel-stage recipe 必须被显式 archive plan 覆盖。
- 构建顺序：`./unixnu ipsw fetch` → `kernel` → `build package` → `firmware` → `payload` → `bootimg`。
- 输出检查：`.config`、`tree/.cache/xnu-work/`、`kernel/kernel.macho`、`device-tree/hardware.dtb`、`payload/payload.img`、`payload/payload.json`、`boot/boot.img`、`logs/`。
- build inputs 包括 Xcode/iPhoneOS SDK、`storage-abi/interface-audit.json`、`build/xnu-prelink/*candidate.macho`、GPU firmware、Turnip/metal2vulkan、IPSW members、platform seed、trust-cache bundle、Data seed、firmware DTB。
- 最后一节 `source-drivers` 只针对 `ipados-27.0.1-24A446`，使用 `build-sheng-source-drivers.py` 与 macOS 26.5 public sources；与 16.6.1 无关。

**K60 可执行项**
- 迁移已经完成，按本文件做反向审计：`./unixnu status --json -D ../UniXNU-mondrian` 检查 `profiles`/`components`/`patch_order`/`output` 是否与 `board.toml` 一致。
- K60 的 UFS 组件是 `PongUfs`（catalog 中确实存在，kind=`driver`，board scope），不是文档映射表的 `ShengUfs`；不要为了对齐文档强行改名。
- `patches/xnu/series` 当前 224 个 `.patch` 文件、series 启用大量条目（含 16.6.1 与 pong 系列）；文档要求“每个 patch 只出现一次、prerequisites 在前”，需用 `./unixnu status --json` 的 `patch_order` 核对。
- 构建输入至少核对：20G81 kernelcache（`d260defc...` sha256）、`prebuilt/20G81-trustcache.bundle`（如仍使用）、Data seed、`--unique-chip-id`。

**iOS 16.6.1/20G81 适用性**：流程直接适用；示例是 iPadOS 17.7.11，K60 的 16.6.1 profile 需要按同一 schema 填。`source-drivers`（27/24A446）不适用。

### 07. `docs/porting/packaging.md`（171 行，重点）

**流程/规范要点**
- **每个设备仓库必须携带 `scripts/package.sh`**，从 `templates/package.sh` 原样复制，板子只改 `board.toml`，不改脚本。
- 一条命令完成：`scripts/package.sh` 按固定步骤运行并写输出与 manifest，第一步失败即停止并点名。
- 配置全部来自 TOML；脚本本身不含设备名、路径、大小、kernel 参数、版本。唯一自读的板级值是 `[package] unixnu`。
- `--os 17|27|PROFILE` 选择 profile；不同 profile 的差异放 `board.toml [os_overrides."<profile>"]`；没有按 target 的第二份 driver/patch/optimization。
- 步骤：`deps`（fetch 子模块/git sources、写 `unixnu.lock`、解 IPSW）→ `preflight`（选 defconfig、写配置）→ `patches`（解析 patch series）→ `build`（kernel/package/payload/firmware）→ `pack`（boot image）→ `verify`（manifest 与输出比对）。
- 接口：`scripts/package.sh [--os 17|27|PROFILE] [--no-deps] [--check] [unixnu options]`；`--check` 只跑 deps/preflight/patches 并打印 patch list。
- GitHub：设备仓库 `.github/workflows/package.yml` 在 macOS runner 上跑 `scripts/package.sh`，产出 `boot.img`、`payload.img`、`kernel.macho`、`package.manifest.json`；fork 里设置 `UNIXNU_UNIQUE_CHIP_ID`。
- `[package]` 键：`unixnu`、`[package.defconfig]`（每个 profile 的 defconfig）、`boot_partition_bytes`（可选，verify 拒绝更大的 boot.img）；`[os_overrides."<profile>"]` 可覆盖表并支持 `remove`。
- `verify` 失败条件：输出缺失或与 manifest 不符、kernel command line 达到 1000 字节、`boot.img` 超过 `boot_partition_bytes`。
- iOS 27 runtime 段：`runtime` 表在 kernel 编译前准备；Apple 静态/System/App trust modules 来自 IPSW；Turnip/AdrenoMetal/board audio HAL 从源码构建并追加 owner trust module；`--init-data` 生成首次安装 Data seed；`--gpu-addon`/`--owner-trust-cache` 复现已有镜像。

**K60 可执行项**
- 当前缺失，按 Adoption 四步补齐：
  1. `cp templates/package.sh scripts/package.sh`（从 `E:/hackios/UniXNU/templates/package.sh`）。
  2. `board.toml` 增加：
     ```toml
     [package]
     unixnu = "../UniXNU"

     [package.defconfig]
     "ipados-16.6.1-20G81" = "mondrian_defconfig"
     ```
  3. `scripts/package.sh --check --os ipados-16.6.1-20G81` 逐一修报告项。
  4. 在 `porting.toml` 的 `packaging` area 记录运行结果。
- 若用 `--os 17|27` 简写，16.6.1 不在其中，必须写完整 profile 名 `--os ipados-16.6.1-20G81`。
- `package/` 当前只有 `README.md`，需补 `Kit.toml` 或明确该板不使用 kit 包。

**iOS 16.6.1/20G81 适用性**：流程适用；`runtime`/`--init-data`/GPU addon 的 iOS 27 细节不适用。K60 的 Data seed 仍按现有 `k60-make-data-seed.py`/`install-k60-ufs-data.py` 流程管理。

### 08. `docs/porting/records.md`（164 行，重点）

**流程/规范要点**
- `porting.toml` 是设备仓库的权威记录；每个 area 记录 inputs、configuration、procedure、development findings、completion criteria、current limits、next action、evidence。
- 必需 areas（14 个）：Configuration、Firmware and boot、CPU and interrupts、Memory and DMA、Storage and root、Display、Input、GPU、Network、Cellular、Audio、Power、Image assembly、Diagnostics；其它外设可加 area。
- 每个 area 的字段：`id`、`status`、`components`、`paths`、`inputs`、`configuration`、`procedure`、`findings`、`completion`、`limits`、`next_action`、`evidence`。
- **status 取值定义（重点）**：
  - `planned`：只要求记录所需输入与 next action。
  - `implemented`：有源码引用与实现范围。
  - `host-verified`：有 host 命令、完整 source commit、结果与可访问日志。
  - `device-verified`：有 device 命令、完整 source commit、结果与可识别 device/firmware/image 的日志。
  - `not-applicable`：在 `limits` 里说明范围，`components` 为空。
- evidence 每项有 `kind`、`reference`、`result`；host/device 还要 `command` 与完整 40 字符 `revision`；reference 用 HTTPS 或设备仓库内已提交文件；大日志放 release/CI artifact。
- 检查命令：
  ```sh
  python3 scripts/porting-record.py check --device /path/to/device
  python3 scripts/porting-record.py check --device /path/to/device --base origin/main
  ```
  第二条比较 committed changes，每个改动代码路径必须有 owning area，且对应 area 的 findings/evidence 有更新。
- 变更流程：先读 record 与 guide → 定位 affected areas → 改实现并同步 findings/evidence → 改配置/procedure/completion → 跑 checker → 代码与文档分 commit 同一 PR → 发布后 catalog workflow 刷新页面。
- 发布：catalog workflow 每天 00:00/12:00 UTC 扫描 `unixnu` topic；`devices.toml` 存仓库身份与 revision；`docs/.vitepress/device-records/` 存记录快照；两种语言共用同一记录文本，用简洁英文。

**K60 可执行项**
- `porting.toml` 当前 13 个 area，缺 `cellular`；K60 是手机（有 modem），不能写 `not-applicable` 除非明确移出范围，应先加 `cellular` 并写 `planned`/`not-applicable` 理由。
- 重新评定 status：`storage`、`display`、`input`、`gpu`、`network`、`audio`、`power` 目前都是 `planned`，但 `docs/STATE-2026-11-07.md` 已记录 UFS/Data/显示/触摸/GPU 的部分证据；按 `records.md` 的定义只能在不满足证据时保留 `planned`，不能写成 `device-verified`。
- `packaging` 目前 `host-verified`，但没有 `scripts/package.sh`；补齐并跑 `--check` 后才成立。
- 运行 K60 自带预检：
  ```sh
  python3 scripts/check-porting-paths.py --quiet
  ```
  再在 core 仓运行官方：
  ```sh
  python3 scripts/porting-record.py check --device ../UniXNU-mondrian
  ```

**iOS 16.6.1/20G81 适用性**：直接适用且具约束力。status 定义与 OS 版本无关。

### 09. `docs/porting/log-capture.md`（225 行，重点）

**流程/规范要点**
- 四阶段日志策略：UEFI 菜单（GOP + 菜单输入 + Advanced Logger + QR 插件）→ XNU entry（UART 或 framebuffer 诊断）→ Storage（保留日志区 + kernel writer + Linux/recovery reader）→ 重复测试（每 boot 一个 evidence 目录）。
- 固件日志导出器：`package/UniXNUPkg/Driver/AdvancedLogDxe/AdvancedLogDxe.inf`；DSC `[Components]` 加 INF，FDF 的 DXE FV 加 `INF`；依赖 `AdvLoggerPkg`、`MsGraphicsPkg`、`AdvancedLoggerAccessLib`、`QrEncoderLib`；DSC 映射这些库，`board.toml [firmware] packages` 加 package roots。
- `gUniXNUPkgTokenSpaceGuid.PcdUniXNUDeviceModel` 设为板名 ASCII；`[payload] tools = true` 增加菜单 **Tools**；手写 `unixnu.toml` 用 `action = "tools"`。
- QR 抓取：OneSend（扫传）扫描 `Tools → Advanced Logger` 的循环帧；Down/j 减速、Up/k 加速，初始 1 秒，5 档 5 秒到 250 ms；保存 `<model>-<date>-<time>.log` 并记录 image revision 与最后 checkpoint。
- kernel handoff：保存固件日志 → 启动 kernel entry → 按 debugging 指南抓 UART/framebuffer → 拍完整 panic/checkpoint（寄存器与最后文本）→ 记录 kernel args；改 args 后重跑 payload+bootimg。
- 持久日志：在存储布局中保留 log region（partition/offset/size/block units），kernel writer 存 message buffer/diagnostic snapshots/boot ID/write status；reader 可选 Linux（target kernel/DTB/storage/USB CDC ACM）或 recovery（TWRP + ADB），`dd`/`adb pull` 读取；host decoder 按 writer header 解码；实现返回 bootloader/recovery 的路径。
- 手动 cycle：测试 payload → 等 checkpoint → 回 reader（`fastboot boot reader.img` 或 `adb reboot recovery`）→ 保存 raw region 与 decoded text 到 boot ID 目录 → 确认 header/snapshots/write status → 回 bootloader。
- 自动 cycle：设定时返回、host runner、boot test image、观察返回、启动 reader、retrieve/decode、确认最终 bootloader 状态；timeout 记录失败阶段与镜像。
- 参考实现：`package/BootLog.c`、`BootReset.c`、`BootResetCore.h`、`package/linux-log/`、`scripts/read-sheng-log.py`；PMIC 地址/watchdog/storage reservation 属于板级记录。

**K60 可执行项**
- `board.toml [payload] tools = true` 已有；确认 `uefi-mondrian` 的 DSC/FDF 是否包含 `AdvancedLogDxe` 与 `PcdUniXNUDeviceModel = "mondrian"`。
- K60 无 UART，屏幕是唯一日志；ramoops 在本机不可用（长按重启掉 DRAM），不要按文档假设 `/sys/fs/pstore` 或 persistent log 已成立。
- 固件阶段按 QR 流程抓日志；内核阶段用 panic 屏与最后 checkpoint；如需持久日志，先实现 Linux reader 或 recovery reader，并记录 `log region` 几何。
- 构建命令：`./unixnu firmware` → `./unixnu payload` → `./unixnu bootimg`（用 `-D ../UniXNU-mondrian`）。

**iOS 16.6.1/20G81 适用性**：固件 QR/Advanced Logger 直接适用；persistent log 部分只适用于已实现 log region 的板子，K60 目前不具备；文末 `sheng-log=1 boot-ui-trace=1` 与 iOS 27 原生 source path 不适用。

### 10. `docs/porting/uefi-firmware.md`（266 行，重点）

**流程/规范要点**
- UEFI 固件来自 Mu-Silicium，为 UniXNU 与 DarwinBoot 提供 GOP、输入、块设备、文件系统、串口、ACPI、FV2 等服务。
- 五步：准备 Mu-Silicium checkout/vendor inputs/submodules → 完成 required integration（DSC/FDF 模块与库映射）→ 保存 firmware 路径并 build → build payload 并 boot-image integration → 设备上验证 menu/DarwinBoot handoff。
- Required integration 模块：`UniXNUPkg/Application/UniXNU/UniXNU.inf`、`UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf`、`DarwinBootPkg/Driver/DarwinBoot.inf`、`UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf`、`MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf`、`FatPkg/EnhancedFatDxe/Fat.inf`；库映射 `HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf`、`FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf`；用分区表时加 `PartitionDxe`。
- Payload discovery：Android bootloader 把 FAT payload 放 RAM，并在 firmware FDT 写 `/chosen/linux,initrd-start`、`linux,initrd-end`；Mu-Silicium SEC 把 FDT 地址保存在 HOB `DAEE82E6-8090-4E72-BFB9-78C13CD4E359`；`UniXNURamDiskDxe` 发布 Block I/O，DiskIoDxe + FAT 暴露 `EFI_SIMPLE_FILE_SYSTEM_PROTOCOL`。
- 菜单无条目检查 5 项：`boot/boot.json` 的 `ramdisk_bytes` 非零；FD 包含 `UniXNURamDiskDxe`/DiskIoDxe/FAT；FDT 的 initrd start/end 有效；串口有 `UNIXNURAMDISK: initrd block device` 成功状态；payload FAT 有 `EFI/UniXNU/unixnu.toml`。
- 必需服务表：GOP、SimpleTextIn、SimpleFileSystem、BlockIo、SerialIo、ACPI Table、FirmwareVolume2。
- Device configuration `Resources/Configs/<device>.toml`：`[boot_shim] requires_kernel_header`、`[uefi_fd] base/size`、`[boot_image_kernel] kernel_compression/append_dtb`、`[boot_image] header_version/base/kernel_offset/tags_offset/pagesize`。
- `[firmware]` 的 `config`、`dsc`、`fd`、`preflight`、`submodules`、`patches`、`packages`、`defines`；`fd = "Build/<device>Pkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd"`。
- Build 流程：preflight → 初始化 submodules → 缺 GenFw 时 build BaseTools → 应用 board patches → EDK II build（DSC、AARCH64、CLANGPDB、board defines）→ revert patches → 检查 FV size/path。
- Boot image integration：`clang --target=aarch64-none-elf -c -DFD_BASE=<base> -DFD_SIZE=<size> -DREQUIRES_KERNEL_HEADER=<0 or 1> BootShim/BootShim.S`，再 append FV、gzip、append DTB、`mkbootimg.py`。
- 验证：FV size 对 `[uefi_fd] size`、shim header `ARM\x64`、boot image 各部件、串口 `UNIXNU:`、菜单 `xnu` 条目与 DarwinBoot handoff。

**K60 可执行项**
- `./unixnu build firmware --uefi ../uefi-mondrian`；核对输出 FD 路径 `Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd`。
- 检查 `uefi-mondrian` 的 DSC/FDF 是否包含 `UniXNURamDiskDxe`、DiskIoDxe、FAT、`UniXNUDxe`；K60 `board.toml` 的 `[firmware] packages` 已列 `{tree}/drivers/DarwinBoot22` 与 pong vendor DXE，按实际 INF 名称核对 `DarwinBoot22` 的 DSC 组件名。
- `./unixnu bootimg --uefi ../uefi-mondrian --dtb out/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb`；检查 `boot/boot.json` 的 `ramdisk_bytes` 非零、FV base/size 与 `[uefi_fd]` 一致。
- 若换用外部 FD：`./unixnu bootimg --fd <file>`，其 DSC/FDF/package paths/defines/patch 必须与 `[firmware]` 匹配。

**iOS 16.6.1/20G81 适用性**：直接适用；K60 的 DarwinBoot 是 `DarwinBoot22`，文档的 `DarwinBootPkg/Driver/DarwinBoot.inf` 路径是通用示例，需按 `uefi-mondrian` 实际名称替换。K60 无串口，验证以屏幕为准。

### 11. `docs/porting/dual-system-partition.md`（197 行，重点）

**流程/规范要点**
- 实验性工具 `scripts/dual_sys/partition.py`：通过 ADB 检测设备与分区，在线缩小 F2FS，然后从 `userdata` 末尾创建 `unixnu` 分区；保留 userdata 的 start/type/GUID/attributes。
- 支持布局：Python 3.10+、Android platform-tools、TWRP root ADB + `/data` 解密、内核支持 `F2FS_IOC_RESIZE_FS`、F2FS 4096 block/512 block per segment/1 segment per section/checkpoints、直接 userdata 或单层 dm 映射、主备 GPT 一致、userdata 是最后一个占用分区且有空 GPT entry、`unixnu` 不存在。
- 不支持即停止：Ext4、多设备/zoned F2FS、multiple segments per section、encryption footers、stacked mappings、intervening partitions。
- 备份：可选离线备份 `userdata` 与 `metadata` 到另一块物理盘；TWRP 文件备份可能漏 encryption metadata；禁用 MTP、卸载 Data/bind mounts/Metadata；`adb exec-out dd` + `blockdev --getsize64` + `wc -c` + `shasum -a 256` 校验。
- 构建 helper：`aarch64-linux-gnu-gcc -static -O2 -Wall -Wextra -Werror scripts/dual_sys/f2fs-shrink.c -o out/dual_sys/f2fs-shrink`；`file` 确认静态 AArch64 ELF。
- `plan`：`python3 scripts/dual_sys/partition.py plan --size-gib 32 --helper out/dual_sys/f2fs-shrink --output out/dual_sys/preview`；写 `plan.json`、GPT before/after、`plan.env`、`twrp.sh`、`SHA256SUMS`。
- `apply`：重新生成 plan，确认设备与布局，输入确认短语；顺序：重检 bundle/设备/内核/GPT → shrink F2FS → 验证两个 superblock → 卸载 `/data` → 写 backup GPT 并读回 → 写 primary GPT 并读回。
- `verify`：`python3 scripts/dual_sys/partition.py verify --plan out/dual_sys/applied/plan.json`；重启 recovery 刷新分区表与加密映射。
- F2FS 大小公式：`floor((L - B % S) / S) * S`（B 原 block 数，L 新 partition 4096-byte blocks，S=512）；只按 L round 会超过新分区。
- 中断处理：无自动重试/回滚；不要删 recovery-session lock；按最后完成操作表处理；不要格式化不可读 Data，GPT 恢复不能撤销 F2FS relocation。

**K60 可执行项**
- K60 已经有 32 GiB `unixnu` 分区：`board.toml [userdata] first_lba = 53342976`、`last_lba = 61731583`、`lba_bytes = 4096`。**不要再次运行 `apply` 创建分区**，否则会对现有 Android `userdata` 做第二次 shrink。
- 只做 `inspect`/`verify` 类检查；如需确认分区，用 `python3 scripts/dual_sys/partition.py inspect`（脚本来自 UniXNU core；K60 仓库当前无 `scripts/dual_sys/`）。
- AGENTS 铁律：只 `fastboot boot`，绝不 `fastboot flash` Android 分区；本文件描述的 `unixnu` 写入路径与 K60 当前“只 boot 不 flash”的约束冲突。

**iOS 16.6.1/20G81 适用性**：不适用（当前 K60 分区已存在）；仅保留 F2FS 大小公式、GPT 备份顺序、TWRP 恢复流程作为参考。

### 12. `docs/porting/soc-support.md`（151 行，重点）

**流程/规范要点**
- 步骤：识别 SoC 型号/revision、CPU 拓扑、中断控制器、timer、IOMMU、外设；读候选 `UniXNU-<soc>-common` 的 `README.md`、`AGENTS.md`、`soc.toml`、DTSI、configs、patches、platform code。
- 所有权表：ARM64 profile 管通用架构配置与 XNU patch；SoC 仓库管 CPU 拓扑、控制器资源、共享平台操作与 SoC patch；设备仓库管启用的 CPU/外设、RAM/保留、wiring、firmware selection、power policy、display、partitions；OS profile 管 XNU/IPSW、Apple identity、prelink roots、ABI、版本 patch；组件仓库管驱动与库。
- 新建 SoC 仓库布局：`AGENTS.md`、`README.md`、`soc.toml`、`configs/<soc>.config`、`dts/<soc>.dtsi`、`patches/xnu/series`、`kits/`。
- `soc.toml`：`schema_version = 2`、`[soc] name`、description、source repository/revision、`[components] include` 用 canonical ID。
- 设备接入：`feeds.toml` 加 `[[source]] name/kind="soc"/git/commit`；`board.toml` 设 `soc`、`soc_source`、`os_profile`；`[device_tree] include_dirs = ["soc:dts"]`；DTS include `<soc>.dtsi`；`config_fragments` 加 `soc:configs/<soc>.config`；`patch_series` 加 `soc:patches/xnu/series`。
- 解析验证：`./unixnu defconfig <device>_defconfig -D ../UniXNU-<device>`、`fetch`、`status --json`、`tree`；检查 SoC revision、profiles、components、overrides、patch order。
- SM8550 示例：`UniXNU-sm8550-common` 提供 `soc.toml`、`configs/sm8550.config`、`dts/sm8550.dtsi`、platform ops、XNU patch series；Adreno740/AdrenoMetal 覆盖 A740/SM8550。

**K60 可执行项**
- SoC 源固定：`feeds.toml` 的 `sm8475` → `https://github.com/Emilelu/UniXNU-sm8475-common` commit `d0c90f1e2f8d570b48030ec5062aef59d0040121`。
- 核对 `UniXNU-sm8475-common` 的 `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi`、`patches/xnu/series` 是否都存在且 revision 一致。
- `board.toml` 已设置 `soc = "SM8475"`、`soc_source = "sm8475"`；`config_fragments` 已含 `soc:configs/sm8475.config`（当前列表：`arch:configs/common.config`、`soc:configs/sm8475.config`、`os:configs/ipados.config`）。
- `patch_series` 当前只有 `device:patches/xnu/series`，未列 `arch:`/`soc:`/`os:` 的 series；按 `soc-support.md` 应把 `soc:patches/xnu/series` 加进完整列表，或在 record 中说明所有共享 patch 已并入设备 series。
- 跑 `./unixnu status --json -D ../UniXNU-mondrian` 确认 SoC profile 解析；`dts/mondrian.dts` 的 `/include/ "sm8475.dtsi"` 是唯一 SoC include。

**iOS 16.6.1/20G81 适用性**：直接适用。SM8550 示例不是 K60；K60 用 SM8475 共享仓库，不能照搬 SM8550 的地址/配置。

### 13. `docs/porting/sm8550.md`（16 行，重点提及）

**流程/规范要点**
- 这是一个纯跳转页：frontmatter 设 `sidebar: false`、`aside: false`、`prev/next: false`，`meta refresh` 0 秒到 `/porting/soc-support#sm8550`，canonical 指向同一锚点。
- 正文只有一行链接 `[Select and add SoC support](/porting/soc-support#sm8550)`。
- 没有独立技术内容，真正的 SoC 支持流程在 `soc-support.md` 的 `#sm8550` 节。

**K60 可执行项**
- 无命令可执行；不要把 SM8550 的 `soc.toml`/DTSI/地址当 K60 数据。
- 如站点要保留该页，应改成 `/porting/soc-support#sm8475` 或新增 SM8475 锚点，否则 K60 无对应页面。

**iOS 16.6.1/20G81 适用性**：不适用（SM8550 专用跳转）；仅说明文档结构。

### 14. `docs/porting/arm64e.md`（89 行，重点提及）

**流程/规范要点**
- 仅适用于满足全部条件且出现在 supported devices 表的设备；其他设备用 arm64 profile（iOS 16 或 iPadOS 17，例如 `ipados-17.7.11-21H461`）。
- 要求：每个启用 CPU 实现 FEAT_PAuth（`ID_AA64ISAR1_EL1` 的 APA/API 或 GPA/GPI 非零，或 `ID_AA64ISAR2_EL1` 的 APA3/GPA3 非零）；XNU 在 EL1 可写五个 key 寄存器（APIA/APIB/APDA/APDB/APGA）；PAC 指令在 EL1/EL0 不 trap；SoC support 存在；native 4 KiB stage 1 translation。
- Supported devices：仅 `sheng / SM8550 / ipados-27.0.1-24A446 / In development`。
- Profile 布局：`profiles/arch/arm64e`（arm64e build config、PAC key management、XNU patch series）与 `profiles/os/ipados-27.0.1-24A446`（XNU 12377.121.6、Darwin 26 calls、iPadOS 27 IPSW pins、prelink roots、OS patches）。
- `[os] arch = "arm64e"` 选择 arm64e；没有该键用 `profiles/arch/arm64`；两者共用组件，arm64e 编译为 arm64e。
- PAC 细节：arm64e 镜像用 chained fixups 指定 key/diversifier；dyld 在用户态签名，XNU early boot 签 kernel collection；不在设备外计算签名，所以 CPU PAC 算法不必匹配 Apple。
- 公开 XNU 只为 paravirtualized `VMAPPLE` 编程 key（`osfmk/arm64/pac_asm.h`），arm64e profile 提供 ARMv8.3 key register 编程；EL0/EL1 共用 key，PAC 不隔离进程。
- 事实：`xnu-12377.121.6` 的 non-SPTM pmap 在 `osfmk/arm/pmap`；arm64e kernel 用 `BCM2837` machine config、non-SPTM pmap、Apple CPU counters disabled；iPadOS 27 kernelcache 是 `MH_FILESET` 且 stripped symbols，kext 直接 branch 到 kernel，arm64 prelink 不适用。

**K60 可执行项**
- K60 当前是 `ipados-16.6.1-20G81`，按本文规定必须保持 **arm64**，不得使用 arm64e/27 profile。
- 如果未来考虑 iOS 27：先在每核读 `ID_AA64ISAR1_EL1`/`ID_AA64ISAR2_EL1` 并做 PAC 指令测试，记录到 `porting.toml`；K60 不在 supported devices 表，不能直接宣称支持。
- 当前无命令；不要设置 `board.os_profile = "ipados-27.0.1-24A446"`。

**iOS 16.6.1/20G81 适用性**：不适用（本文明确把 iOS 16 归到 arm64 profile）；是“不要升级到 arm64e”的反向依据。

### 15. `docs/porting/gpu-diagnostics.md`（76 行，重点提及）

**流程/规范要点**
- 参考 latency capture 记录七个帧延迟问题的证据：foreground allocation、background reservation、submission delay、release/completion、concurrent services/faults、GPU pass cost、upstream display gaps。
- 启用参数：`sheng-log=1 sheng-gpu-trace=1 sheng-gpu-perf=1 sheng-diag-export=240`；export 在选定 boot-log 时间运行一次，不安排重启；正常构建默认关闭。
- 保留证据表：foreground allocation（pool/requested/available KiB/backing handle/reuse/page prep/device-lock/caller stack）；background reservation（同 memory-operation IDs/pool/foreground/room-worker）；submission delay（command creation/commit、encoding batch、slow ops、runtime lowering、scheduler handoff、Vulkan submission、4 ms render encode thread）；release/completion（deferred physical release、resource/owner destruction、GPU wait、completion state、handlers、retained objects、final prep、4 ms completion thread）；concurrent services/faults（process CPU time/occupancy/busiest threads/exceptions/registers/image UUIDs/fatal exit/crash reports/shared-region unnests）；GPU execution（per-pass hardware duration/dimensions/render mode/attachments/shader figures/submission-retirement/GPU frequency votes/A7XX counters）；upstream display gaps（validation/GPU wait/flip/latch/retirement/blanking、4 ms render/SpringBoard threads、blocked-thread waits）。
- 采集策略：kernel GPU ring 只放 submission/retirement/display arrival/display fence/latch/build identities/render server thread identities；其他进程不写入；render server 其余写自己的 `frames.trace`，无 per-record syscall。
- 不采集：Mach message streams、user-client call rings、contiguous allocation rings、per-contact touch records、dispatch introspection、queue-priority/ring-switch/restart/stall rows、其他进程 pass/pipeline notes、status/telemetry、screenshots/pixel samples。Fast resource release <250 µs 省略；completion/owner callbacks 保留配对。
- LAT1 容量：32,768 slots for faults/unnests/exit reasons/process identities；491,519 slots ordinary latency events + 1 summary；普通事件不能覆盖 fault lane。
- 导出：`gpu.trace.bin`、`kernel.latency.bin`、`kernel.rings.txt`、`kernel.boalloc.bin`、`kernel.cpus.bin`、`kernel.ptime.bin`、`kernel.touch.bin`、`kernel.client.bin`、backboardd `frames.trace`、最多两个 crash report per named service/widget（≤8 MiB）；`diag-skipped.txt` 记录未放入文件与 dasd model resource lookup。
- 读取：`fastboot boot /path/to/linux-log.img`、`python3 scripts/read-sheng-log.py --wait 60 --out /path/to/logs`；解码 `scripts/decode-gpu-trace.py RUN/diag/files`、`scripts/decode-sheng-latency.py ...`；LAT1 16-byte header + 72-byte records；event 35/36 是 unnest range，用户栈跟随 fault event 8/9/12；client sampler state bits 12-13（1 render/2 encode/3 completion）。
- 检查：`python3 scripts/check-gpu-trace.py`、`python3 scripts/check-native-adreno-scheduling.py`。

**K60 可执行项**
- 无直接可执行项：K60 使用 `PongAdreno`/`PongMetal`，不是 sheng 的 Adreno740/GPU trace 栈；`sheng-log`、`sheng-gpu-trace`、`read-sheng-log.py`、`decode-gpu-trace.py` 在 K60 仓库不存在。
- 可借用其“七个问题 + 每段证据字段”的框架，为 `PongAdreno` 设计 K60 自己的 trace；不能把 `sheng-gpu-perf=1` 当 K60 的开关。

**iOS 16.6.1/20G81 适用性**：不适用（仅参考）；K60 的 GPU 诊断以 `docs/plans/GPU-ENABLE-PLAN.md` 的 `pong_gpu_*` 日志为准。

### 16. `docs/porting/drivers.md`（123 行）

**流程/规范要点**
- 先定义 driver boundary：Hardware（寄存器范围/访问宽度/中断/clock/reset/power owner）、Transport（请求格式/响应匹配/timeout/retry/disconnect）、Memory（CPU/DMA 地址/buffer size/alignment/cache policy/release point）、OS（provider class/properties/ABI/entry points/completion）、Build（source files/dependencies/archive output/link input/initialization caller）。
- 硬件顺序：1 CPU/interrupts/timer/RAM/DMA → 2 storage/root/Data → 3 framebuffer/refresh/brightness → 4 touch/buttons → 5 GPU/Metal → 6 Wi-Fi/Bluetooth/USB（baseband 6a）→ 7 DSP/audio/battery/CPU freq/power → 8 OS services/packaging。
- Build integration 8 步：选择 startup path（provider-matched personality 或 board-started explicit caller）；完成 resource cleanup（mapping/interrupt/work-loop/timer/DMA/service reference 的 owner 与 release）；按选定 OS 编译（kernel headers/compile records/private interface 的 class layout/vtable slot/selector/arg structs/symbol bindings）；添加 recipe（`scripts/` build scripts、`package/` hardware sources、compile-record lookup/source list/include paths/class initializer/archive destination）；连接 selection/linking（`[components] include`、`[kernel] archives` 的 `component:<ID>` 或 device script、`CONFIG_XNU_BUILD_ARCHIVES=y`、driver flags/archive paths）；检查 resolved inputs（`./unixnu status --json`、`./unixnu kernel`、archive log/prelink output）；检查 linked implementation（`llvm-ar t <archive.a>`、`llvm-nm --defined-only <archive.a>`、prelink report）；exercise one complete operation。
- 记录：每个 capability 记录 source revision/firmware/boot args/command/artifact path/last successful stage/captured result 到 `porting.toml`。

**K60 可执行项**
- 按顺序维护 `[components] include` 与 `[kernel] archives`；K60 `board.toml` 当前 `archives = ["component:ArmDTPlatform", "component:ArmCpu", "component:PongUfs"]`，新增驱动时按依赖顺序追加。
- 每次修改后：
  ```sh
  ./unixnu status --json -D ../UniXNU-mondrian
  ./unixnu kernel -D ../UniXNU-mondrian
  llvm-ar t <archive.a>
  llvm-nm --defined-only <archive.a>
  ```
- 注意 K60 的 `CONFIG_XNU_BUILD_ARCHIVES=y` 已启用，但 `board.toml` 注释明确说平台 archives 走 pong build scripts，不走 format-2 recipe；新增组件时要在两者之间二选一并记录。

**iOS 16.6.1/20G81 适用性**：方法直接适用；文档的 sheng 组件示例不适用。16.6.1 的私有 ABI 必须以 20G81 kernelcache 为准。

### 17. `docs/porting/display.md`（150 行）

**流程/规范要点**
- 先建立 firmware scanout：构建 UEFI 固件、确认菜单/颜色/尺寸正确、比较 GOP geometry 与 firmware memory map/board DTS、保留 active scanout allocation 到 kernel handoff。
- 再适配 XNU display backend：`GopFramebuffer` 的 `NativeLegacyDisplay.cpp`、`NativeGOPPresenter.cpp`、`NativeGOPWire.h`；消费 `PE_current_console`，适配 MobileFramebuffer/IOSurface ABI。
- 参考 recipe：`scripts/build-gop-legacy-display.py` 用 prelinked candidate 与 ABI audit 生成 late display archive；`CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y` + `offline-legacy-*`；`sheng-dpu=1` 采 SM8550 DPU/dual-DSI counters；`sheng-vsync=120` 请求 120Hz。
- `NativeGOPWire.h` 路径：先查 mode/geometry、校验 present buffer 的 size/stride；GPU handoff 用 `NGPSwap.sequence` 跟踪 pending frame，copy 后以该 sequence 返回 `NGPComplete`；保留 source frame/IOSurface 到 swap 完成。
- 24A446 adapter：默认 surface 经原 IOSurfaceRoot factory，校验 backing memory/geometry 后转交 display family；`create_default_fb_surface()` slot 返回 void，残留返回寄存器不是 object pointer；300 秒 boot 三次 swap 无 panic，显示 Apple logo；Home screen 未验证。
- DPU pipes：`sheng-dpu=2` 读 VIG0/1 source/size/format/fetch、CTL0、tear check、apps SMMU display streams；`sheng-dpu=3` 还改 pipe current address 并计时 CTL flush latch；直接 scanout `sheng-dpu-scanout=2` 实验默认关闭。
- 亮度：识别 I2C/DSI-command/PWM；`AppleARMBacklight.cpp` 是 KTZ8866 示例，`GeniI2c.h` 是 GENI 状态机；记录 controller 数量/寄存器编码/亮度范围/I2C engine/slave address/pins/clocks/interrupts/power sequence；iPadOS 17 用 `IODisplayParameters`/`backlight-control`/`brightness`/`FadePeriod`，iPadOS 27 还加 millinits/slider table/calibration/`brightness-nits` 并在 virtual platform 丢弃请求。
- 验证：min/mid/max 设置对应 readback 与可见亮度；fade 完成；timeout counter 稳定；`native_backlight_stats` 记录 publication/requests/readback/interrupts/failures；UI 亮度变化与 raw controller write 分开验证。

**K60 可执行项**
- K60 当前走 `MiniIOMobileFramebuffer` + CPU 软件呈现（补丁 0210/0211/0213），不是 `GopFramebuffer`；继续沿用现有路径，除非决定移植 GopFramebuffer。
- 面板 1440×3200，`display-scale = 3` 已在 20G81 profile 的 `[adt.chosen.u32]`；不要丢。
- 亮度是面板 DSI DCS `0x51` 调光，无独立背光 IC；不要套 KTZ8866/GeniI2c 的 I2C 常量。
- GPU scanout 前软件 framebuffer 单核整帧 9–10 ms，120Hz 每帧 8.3 ms 不可行；先完成 `GPU-ENABLE-PLAN.md`。

**iOS 16.6.1/20G81 适用性**：部分适用。firmware scanout/亮度属性/验证方法可参考；`GopFramebuffer`、`sheng-dpu`、iPadOS 27 亮度属性均不适用于 K60 16.6.1 当前路径。

### 18. `docs/porting/input.md`（104 行）

**流程/规范要点**
- 先完成 display geometry 与 interrupt/DMA 设置；记录 touch controller 型号/固件/matrix geometry/physical orientation/bus wiring/reset/IRQ pins/OS HID ABI。
- 传输与传感器：`QcomGeniSpi`、`ShengNovatekTouch`（`NvtProtocol.h`/`NvtTouchCore.c`）；`nvt_bus.xfer` 必须是一个 full-duplex transfer 且 chip select 全程保持；caller-owned buffers + delay callback；按 `nvt_identify` → `nvt_fw_parse` → `nvt_download_firmware` → `nvt_read_frame` 顺序检查返回码；下载失败保留 stage/CRC/SRAM-readback 诊断。
- Board path：controller windows/bus mode/rate/GPIOs/interrupt/SMMU stream；power/reset ownership；DMA addressing/cache；chip ID → firmware → geometry；坐标映射到 display orientation；稳定 contact ID/多点/边缘/release。Novatek core 是 40×60 matrix；固件由 `scripts/gen-touch-firmware.py` 与 proprietary inventory 管理。
- HID：按选定 kernelcache 资质 IOHIDFamily 方法/对象布局；adapt report descriptor/logical ranges/contact limits；`sheng-touch=1..4` 分阶段，`sheng-touch-hid=1` 开启发布。
- 实体按键：`ButtonProbe.cpp` 参考；GPIO/PMIC 输入极性/ownership/interrupt routing/ack；只访问当前执行环境拥有的 PMIC 外设；`BootResetCore.h` 适配 SPMI；report 2 bits 为 Power/Volume Increment/Volume Decrement；`sheng-buttons=1`。

**K60 可执行项**
- K60 触摸是 Goodix `xiaomi,m11a-spi`，接 GENI SPI `spi@990000` CS0、15 MHz；不是 Novatek NT36532。`QcomGeniSpi` 传输层概念可复用，`NvtProtocol`/`NvtTouchCore` 不可用。
- K60 ADT 需要 9 个触摸属性（见 `K60-TOUCH-PARAMS.md`）：`spi-base`、`tlmm-base`、`gcc-base`、`rsc-base`、`cmd-db-base`、`gpio-offset`、`pins`、`max-x`、`max-y`；`pins[0..5]` 必须为 `16,17,18,19,21,20`。
- 实体键：PMIC PON peripheral `0x13`，音量加在 `pm8350@1/pinctrl@8800` GPIO6=`0x8d00`，ACTIVE_LOW。
- HID 走 `ShengHidInput` 概念，但 16.6.1 的 IOHIDFamily ABI 必须用 20G81 kernelcache 重新资质；不要直接套 17/27 的 candidate/JSON。

**iOS 16.6.1/20G81 适用性**：部分适用。通用 checklist/坐标/HID 方法适用；Novatek 40×60 与 sheng 参数不适用；Goodix 协议层需另用 pong 的 `pong_goodix.c`/`0242` 补丁。

### 19. `docs/porting/gpu.md`（188 行）

**流程/规范要点**
- 先完成 platform DMA 与 basic display presentation；读 `Adreno740` runtime 与 `AdrenoMetal` interface。
- Adreno740 只实现 A740 kernel interface；AdrenoMetal 使用该接口 + Turnip/metal2vulkan + 选定 OS GPU/IOSurface ABI；换 GPU generation 必须先实现匹配 kernel backend 与 compiler support。
- 对另一个 A740 board：收集 GPU/GMU registers/interrupts/SMMU context/stream IDs/firmware/power domains/clock-voltage levels/interconnect votes/RAM reservations/scanout layout。
- 固件输入：`qcom/gmu_gen70200.bin`、`qcom/a740_sqe.fw`、`qcom/sm8550/sheng/a740_zap.mbn`；`scripts/data/adreno-inputs.json` pins；`.cache/firmware/sheng-gpu/`；`proprietary-files.txt` 记 provenance。
- 命令提交：ArmSmmu4K context ownership/stream/address width/cache；reserved memory/GPU VA windows；CP init/ring progress/fence completion；known image render；client teardown/mapping lifetime/fence failure。
- Memory path 规则：对象 handle index；BO 用 pageable `IOBufferMemoryDescriptor` 无 task + write-combined + `prepare()`；owned map 用 `ArmSmmu4KLiveMapContextBatchExclusive`；imported map 按 cache class/page bitmap 选择；unmap ≤512 pages 每页 TLBIVAL，>512 invalidate ASID；submission 不做 TLB invalidate；stalled fence 仍 invalidate。
- Scheduling：`sheng-gpu-preempt=2`，高/正常高/实时用 ring 0，普通/低/背景/未指定用 ring 1；FIFO across priority changes；preemption 保存 GMEM/恢复每 ring executed page table；interactive QoS。
- Render mode：`sheng-fb-bgra=1` 默认 `TU_DEBUG=sysmem,nocb`；transient attachment 可用 GMEM；`turnip-transient-attachments-in-gmem.patch`、`turnip-gmem-mutable-swap.patch`；`sheng-metal-flow=1` 实验；Metal 默认单 sample，`NATIVE_METAL_SINGLE_SAMPLE=0` 保留请求。
- Build：iOS 17 `build-turnip-darwin.py --target ios`、`build-adreno-metal-plugin.py --target ios`、`make-gpu-addon.py --publish build/gpuaddon.bin`；iOS 27 用 `--target ios27` + `ADRENO_PLUGIN_DIR=build/adreno-metal-plugin27`；`--gpu-addon`/`--owner-trust-cache` 传入 payload，`sheng-gpu-addon=1`。
- Shader warmup：prime list 绝对路径写 `build/prime-list.txt`，plugin 嵌入 `__DATA,__primelist`，`make-gpu-addon.py --prime-list` 生成 `addons/NativeAdrenoMetal.primelist`；pipeline pack 用 `--cache-export` 产出后 `make-m2vpack.py` 合并、`--pipeline-pack` 发布；priming 90 秒后启动，8 MiB stack，8 command buffers/250 ms 为 busy，idle 120Hz 约 6。

**K60 可执行项**
- K60 是 Adreno 730 v3（chip `0x07030002`、4 MiB GMEM、HighestBankBit 16、64×32 tile），不是 A740/SM8550；`Adreno740`/`AdrenoMetal`/`Sm8550Platform` 不可直接替换。
- 当前使用 `PongAdreno`/`PongMetal`（与 pong ios16 同码）；GPU 工作按 `docs/plans/GPU-ENABLE-PLAN.md` 的 `pong_adreno_start=1` → `pong_gpu_scanout=1` → `pong_gpu_only=1` 分阶段；不要套 `a740_*` 固件。
- `build-turnip-darwin.py --target ios` 可为 16.6.1 提供方法参考，但必须重新验证 A730 ABI 与 20G81 Metal/IOSurface。

**iOS 16.6.1/20G81 适用性**：不适用（组件/固件/参数均为 A740/SM8550 或 iOS 17/27）；只保留 memory path、scheduling、warmup 方法参考。

### 20. `docs/porting/ufs.md`（145 行）

**流程/规范要点**
- 官方实现 `ShengUfs`（runtime class `NativeUfs`），组合 SM8550 controller access、firmware adoption、SMMU handling、GPT/window parsing、board persistence policy。
- Hardware inventory：Controller compatible/revision/MMIO base/length/capabilities/interrupt；PHY register/lanes/ref clock/tuning/init owner；Clocks provider/ID/rate/parent/branch/interconnect；Reset/power；SMMU instance/stream IDs/stream masks/context banks/address width/existing mappings；DMA buffer/physical-IOVA/alignment/coherency/cache；Handoff HCE/HCS/link state/power mode/request-list base/outstanding commands；Storage layout LUNs/block size/capacity/GPT/root windows/Data/log reservations；OS interface storage ABI/prelink/publication/matching/completion。
- SM8550 reference DTSI：host `0x01d84000/0x3000`、PHY `0x01d80000/0x2000`；GCC `0x00100000`；apps-SMMU stream `0x60`；当前驱动用 C++ constants，转 DTS property 要改 consumer 并验证 ADT。
- Initialization/ownership：读 controller/clock/PHY/link/SMMU state → 确认 firmware 已配置的 clocks/resets/power → 选择 firmware-state adoption 或 cold init → 分配 request descriptors/data buffers → 取得 request list/SMMU context 独占 → bounded command → capacity/known blocks → 发布 root。
- Findings：idle hardware-gated AHB branch 可能报 `CLK_OFF`，要同时看 branch enable/gating；SMMU bypass 受地址宽度限制；capacity/GPT/root window 分开检查；root reads/Data writes/reset 分开记录；ShengUfs 同时拥有 apps SMMU stage 1 window（display `sheng-dpu-scanout`、WiFi `sheng-wifi=2`），audio 保持 pass-through。
- Config：`[components] include` 加 `ShengUfs`，`[kernel] archives` 加 `component:ShengUfs`；`[userdata] first_lba/last_lba/lba_bytes` 从目标 GPT；`[payload.adt] root_match_volume_uuid` 从选定 APFS；`CONFIG_XNU_NATIVE_UFS=y` + `native-ufs-root=1`。
- Completion criteria：hardware inventory → host access → DMA/commands → block reads → root → persistence；每步更新 storage record。
- 命令：`./unixnu defconfig ...`、`status --json`、`build kernel`、`python3 scripts/porting-record.py check`。

**K60 可执行项**
- K60 用 `PongUfs`，不是 `ShengUfs`；`PongUfs` 是 catalog 的 board-scope driver（`NativeUfs.cpp`，输出 `build/sheng-ufs/libShengUfs.a`）。
- K60 DTS 已有完整常量：host `0x1d84000/0x3000`、GCC `0x187000`、SMMU `0x15000000/0x100000`、stream `0xe0`、SPI 265、context banks 78、match groups 120。
- defconfig 已有 `CONFIG_XNU_NATIVE_UFS=y`；boot args 是 `native-ufs=1`（文档写 `native-ufs-root=1`，需确认驱动实际接受的拼写），`pong_ufs_readwrite=1` 打开可写。
- `[userdata] first_lba=53342976`、`last_lba=61731583`、`lba_bytes=4096`；root UUID `C5DAF029-2070-4F68-B3CC-1D1320344CF0`。

**iOS 16.6.1/20G81 适用性**：checklist 直接适用；ShengUfs 的 SM8550 常量与组件不适用；K60 用 PongUfs 的 SM8475 常量。

### 21. `docs/porting/usb.md`（157 行）

**流程/规范要点**
- `QcomDwc3` 派生自 Apple `AppleUSBXDCI`/`AppleUSBXHCI`；port 提供 register window/interrupt/power/PHYs；Apple USB stacks/configd/lockdownd 不改。
- sheng 参考值：DWC3 base `0x0a600000`，Apple register window at base+`0xc000`，GIC INTID 165，SMMU stream `0x40`，eUSB2 ref clock 38.4 MHz，PHYs/rails = eUSB2 PHY、PMIC repeater、QMP combo PHY、retimer、GDSCs、RPMh rails。
- `bringUp` 9 阶段：map clock/TCSR/PHY/QSCRATCH → vote rails → enable GDSCs → clocks/resets → SMMU context → repeater → eUSB2 then QMP PHY（fallback UTMI）→ read core ID → hardware ready；`native_usb_stats[0]` 存最后 stage，负数表示失败 stage。
- `AppleUSBXDCI` 不做 cache maintenance；给 controller stream 一个 stage 1 identity context，write-back inner shareable blocks。
- Class registration：`qcom_dwc3_bring_up` → `OSKextLoadKextWithIdentifier` for `com.apple.driver.AppleUSBXDCI`/`com.apple.driver.usb.AppleUSBXHCI` → `OSMetaClass::preModLoad`/static init/`postModLoad` → `qcom_dwc3_publish`；USB stacks 加 prelink roots。
- Class layout 来自 kernelcache：`scripts/gen-usb27-abi.py`、`gen-usb27-host-abi.py` 生成 `scripts/usb-xdci-24A446.json`/`usb-xhci-24A446.json`；两个 override：`AppleUSBXDCI` slot 179 无 `IOPort` 返回 false；host mode xHCI subclass 对 power 回答 on，device stack 回答 0。
- Cable role：`qcom_dwc3_vbus(int)`、`qcom_ucsi_start/receive/tick`、`qcom_ucsi_polling`；host on cable selects device role，peripheral selects host role；无回答时 device role。
- Mac pairing：`chip-id` in `[payload.adt]`；`board-id`/`security-domain` in `adt.chosen.u32` OS profile；`native-union-statfs-fsid`；lock state 3；`MobileDevice.framework` device map row。
- 构建/验证：`sheng-usb=1 log-sys=1`，`./unixnu build kernel payload`、`bootimg`、`fastboot boot`；Mac `ioreg -p IOUSB -l -w0 | grep -E 'idVendor|idProduct|Device Speed'`；Device Speed 4 on USB3；解锁/Trust 后 lockdown session。
- 症状表：Chirp passes/high-speed fails→eUSB2 ref clock table；`ep0OutEventOccurred: event 0`→stage 1 SMMU；PAC panic creating TRB pool→kext load before class registration；`bNumConfigurations=0`→slot 179；Mac asks software update→chip-id/board-id/security-domain；`UserDeniedPairing` no dialog→file system number of `/System`；passcode after Trust→lock state。

**K60 可执行项**
- K60 DWC3 core `0xa600000`、QSCRATCH `0xa6f8800`、eUSB2 PHY `0x88e3000`；SMMU stream 实测 `0x0`（docs/reference/USB-LOG-CHANNEL.md / ISSUES.md），不是文档的 `0x40`。
- 官方 `QcomDwc3` 只标 iPadOS 27.0.1/24A446，ABI JSON 全是 24A446；不能直接用于 16.6.1。K60 当前是自定义 DWC3/usblog 探针。
- 若移植：按 9 阶段记录 `native_usb_stats`，先修 stage 1 SMMU context 再谈数据；pairing 的 `chip-id` 已在 board.toml `"8015"`，`board-id`/`security-domain` 需按 20G81 的 `MobileDevice.framework` 行填写。

**iOS 16.6.1/20G81 适用性**：结构/症状表可参考；具体值/ABI 不适用（文档面向 27/24A446）。

### 22. `docs/porting/baseband.md`（80 行）

**流程/规范要点**
- Wi-Fi-only 平板可跳过；设置 `porting.toml` 的 cellular area 为 `not-applicable` 并在 `limits` 写硬件理由。
- 示例 `QcomBaseband`（作者 HoshinoYumeka/@chiba233）连接 iOS 的 ABM/BBUpdater/CommCenter 到 Qualcomm modem；Coachz 示例是 SC7180/IPA v4.2/iOS 17 (21H461)。
- 分层：SoC/board（power/clocks/reserved memory/modem firmware boot/interrupts/DMA/EFS/NV）→ control bridge（QMUX framing/QMI client/service discovery/reply routing）→ iOS interface（baseband services/channels/async read-write/boot exchange）→ data path（IPA/GSI/QMAP muxes/OS net interface）。
- Modem startup：记录 modem rails/resets/clocks/interconnect/interrupts/firmware memory/SMMU streams；加载 MBA/MPSS firmware + factory FSG/EFS/NV；启动 GLINK/QRTR 跟踪 service announcements；IPA v4.2 先 configure IPA，`ipa-setup-ready` 后 GSI/endpoint，完成 INIT_DRIVER/INIT_COMPLETE over QMI。
- iOS bridge：publish `AppleBaseband`/`AppleBasebandPCIControl`/`AppleBasebandPCIInterface` per channel；`ABPInterfaceProtocol` names `pbl`/`sahara`/`qmux1`/`qmux2`；`coachz_baseband_configure(send, del_client)`；`coachz_baseband_new_server/del_server/qrtr`；`coachz_baseband_poll`；CTL QMI clients/local QRTR ports；BSP 0xb001 chip ID/serial；BSP 0xa000/SetConfig 0xe00d carrier bundle segments acknowledged/discarded/FileTransferStatus 0xa001；cellular ADT nodes/product properties；package Apple firmware where ABM/BBUpdater look；publish PDP manager services。
- Data path：`kOnline` 只表示 radio online；检查 NAS registration/serving network/packet-service attachment；`coachz_bb_data.h` opens IPA hardware port with DPM + WDA raw IP/QMAPv4 before first WDS client；translate WDS/QOS endpoint fields Apple PCIe `{3,4}` → embedded `{4,1}`；bind WDS session to QMAP mux；connect address/routes/DNS/MTU to `pdp_ip`; route each mux; pair DMA completion with buffer ownership; test TX/RX/disconnect/flight mode/modem reset; eSIM needs UIM/APDU + VINYL.
- 构建：`QcomBaseband` to components，normal archive `component:QcomBaseband`；Coachz IPA adapter `build-qcom-baseband.py --coachz`；output `build/qcom-baseband/libQcomBaseband.a`；link archive + IOKit class init/startup；记录 modem boot/QMI/SIM/registration/data/reset/eSIM 分开的 checkpoint。

**K60 可执行项**
- K60 `porting.toml` 当前没有 `cellular` area，必须先补；K60 是手机有 modem，不能默认 `not-applicable`，如果当前阶段不做就写 `planned` 并列出 modem firmware/EFS/NV/SMMU 输入。
- `QcomBaseband` 是 Coachz/SC7180 IPA v4.2 示例，K60 SM8475 的 modem/IPA 版本不同；不要直接复制 `coachz_*` 常量。
- 若后续实现：把 modem firmware/EFS/NV 记入 `proprietary-files.txt`，按 `[components] include` + `[kernel] archives` 接入。

**iOS 16.6.1/20G81 适用性**：仅参考。示例是 iOS 17/SC7180；K60 的 16.6.1 需要重新确认 CommCenter/ABM ABI 与 modem 型号。

### 23. `docs/porting/bluetooth.md`（147 行）

**流程/规范要点**
- `QcaBluetooth` 在 GENI UART 上跑 Linux `btqca.c` 初始化，通过 UART.SK 把 H4 bytes 送给 Apple `bluetoothd`；Apple stack owns scanning/pairing/keys/BLE/audio profiles。
- sheng 硬件：UART QUP2 SE6 `0x898000`、GIC INTID 493；DMA stream `0x423`；CTS/RTS/TX/RX GPIO 76/77/78/79；`BT_EN` GPIO81；wake GPIO79；serial clock 51.2 MHz、16x oversampling、3.2 Mbaud；firmware `hmtbtfw20.tlv`/`hmtnv20.bin`。
- 固件 staging：`python3 scripts/stage-bluetooth-firmware.py OUTPUT --source FIRMWARE_QCA_DIRECTORY`；UART 需要 boot firmware 的 protocol 2 microcode，`powerOn` 在 engine 报其他 protocol 时返回 `ENXIO`。
- Power path：`sheng_wcn_power_get/put` 与 Wi-Fi 共享 WCN supplies，每个 radio 一票，最后一个 owner 释放；`powerOn` 顺序：map resources + 32 KiB DMA buffers via `smmu_plan_bypass`/`smmu_configure_bypass` holding `AppsSmmuLock` → take BT power vote → `BT_EN` low 100 ms → enable serial clock → check QUP version/protocol → prepare engine → attach UART/wake interrupts → raise `BT_EN` wait 60 ms → enable pin pulls → `qbt_geni_start` → `qbt_boot(rate, address)`；`powerOff` 逆序。
- Worker：`sheng_bluetooth_probe` from late platform probe；`qbt_platform` → `qbt_create` → `qbt_transport_init`；wait for Data addon；move bytes between `qbt_transport`/`qbt_transmit`；sleep until `qbt_deadline`/`qbt_geni_deadline`.
- DTS：`bluetooth { device_type = "bluetooth"; compatible = "qcom,wcn7850-bt"; unixnu,adt-name = "bluetooth"; transport-encoding = <1>; transport-speed = <3200000>; status = "okay"; };`；userland 前设 `local-mac-address` + `/chosen/mac-address-bluetooth0`，注册 `IOService` `bluetooth`。
- Native stack: `payload.runtime` 的 `audio_system_plugins = ["BTAudioHALPlugin.driver"]`、`bluetooth_tool = "scripts/build-bluetooth-userspace.py"`、`bluetooth_target = "ios27"`；stages signed BlueTool/bluetoothd/QcaBTType0.dylib；`patches/xnu-12377/sheng-bluetooth-runtime.patch` mounts over `/usr/lib`/`/usr/sbin`；adapter locked to one bluetoothd hash；pairing keys need keychain/AppleKeyStoreState.
- 验证：`check-bluetooth-platform.py`、`check-bluetooth-shared.py`、`check-wcn-power.py`；`sheng-bluetooth=1 log-bluetooth=2`；`[bluetooth] state=2 error=0`、`[bluetooth proc]` one bluetoothd start；Settings turn on/pair/play/restart reconnect。

**K60 可执行项**
- K60 QCA6490 BT：`bt_qca6490` power node + `qcom,msm-geni-serial-hs@894000`（QUPV3_2 SE20、IRQ 587、GPIO76/77/78/79、wakeup-byte `0xfd`）；firmware 未核实（可能 `htbtfw21.tlv`/`htnv21.bin`）。
- pong main/ios16 都没有 `drivers/PongBt`；`QcaBluetooth` catalog hardware 是 WCN7850 UART，不等于 QCA6490；K60 BT 是零先例，需新写 GENI UART/HCI 驱动。
- iOS 16.6.1 的 20G81 kernelcache 无 `IOBluetoothFamily`（BT plan 已扫描 0 命中），只有 `com.apple.driver.AppleBluetooth`（BTReset）；不要按本文 iOS 27 native stack 路线执行。

**iOS 16.6.1/20G81 适用性**：不适用（文档面向 iOS 27 + WCN7850）；K60 16.6.1 的 BT 基础实现暂不在当前范围。

### 24. `docs/porting/network.md`（121 行）

**流程/规范要点**
- `Ath12kWifi`：先识别 radio/PCI ID/firmware/board-data variant；读 `include/nw_abi.h`。
- 分层：`lx_platform`（time/sleep/poll/log/alloc/DMA alloc-map-sync/`fw_get`）、`nw_board`（mapped BAR/PCI identity/config-space/MSI target）、`nw_wifi_events`、`nw_wifi_start/step/stop`。
- PCIe endpoint：记录 controller/PHY windows/lane count/reset sequence/WLAN enable/PERST/ref clock/regulators/interconnect votes/SMMU streams/MSI routing；步骤：inspect powered/clocked registers → rails/clocks/PHY/reset → train link/read vendor-device ID → assign/map BAR/PCI caps/bus-master → DMA range/cache → attach MSI/delivery。
- 回调所有权：`dma_alloc` 返回 zeroed CPU memory + endpoint-reachable bus address；`dma_map` 对窗口外 buffer 返回 0；`dma_sync` 按方向；`fw_get` 按 filename 返回 data/length 且消费期间有效；install events before start；continue while `nw_wifi_step` returns nonzero；copy RX data before async return；shutdown 顺序 stop submissions → stop worker/component → release BAR/MSI/DMA。
- OS net：adapt `WifiNet.cpp` to selected XNU/wireless ABI；`nw_wifi_scan/connect/tx`/receive/link events；MAC identity/channel/regulatory/request layouts。
- WCN7850 reference: `sheng-wifi=5` starts Wi-Fi, `sheng-wifi-aj=0` leaves join to Settings; six PMU rails need RPMh mode/voltage/enable; PCIe0 Gen2 x1; endpoint `17cb:1107`; MSIs through PCIe0 MSI receiver to SPI 141; firmware c7-00108 works, c2-00259 hangs in demand pager; zero MAC → board makes one from chip ID; 6 GHz omitted (59 passive channels); association uses AP HT/VHT capability; beacon miss ignored if frames arrive within 5s; VHT MCS10/11 dropped; system cannot store network password.

**K60 可执行项**
- K60 是 QCA6490/WCN6855（PCI `17cb:1103`、ath11k），不是 WCN7850/ath12k；`Ath12kWifi` 不可用。
- 正确先例是 pong main 的 `PongWifi`（QCA6490 + Linux v7.0.14 ath11k），`nw_abi.h` 的 `nw_wifi_start/step/stop` 接口形状可复用；按 `docs/plans/WIFI-PORT-PLAN.md` 六阶段实施。
- 不要沿用 `porting.toml` 里旧的 `Ath12kWifi` 规划（WIFI plan 已明确）；PCIe0 的 K60 常量在 WIFI plan §2，MSI SPI140（不是文档的 SPI141）。
- 前置：`PongPower` 的 `PongPlatformResources`/`QcomRpmh` 不在 K60 树里；`PongUfs` 没有 `pong_ufs_ready()` 导出；先补这两项。

**iOS 16.6.1/20G81 适用性**：部分适用。`nw_abi` 接口/PCIe 检查清单可参考；Ath12kWifi 组件、WCN7850 参数、iOS 17/27 记录不适用。

### 25. `docs/porting/power.md`（233 行）

**流程/规范要点**
- 先完成 platform memory/interrupts/DMA；DSP、audio、battery、power 分层实现。
- 输入表：DSP（firmware/PAS IDs、memory reservations、mailbox interrupts、shared-memory layout、clock/power ownership）；Audio（codec/amplifier IDs、buses、clocks、routes、DSP topology、formats、OS audio ABI）；Battery（gauge/firmware protocol、property IDs、units、current sign、notifications）；Power（clock domains、OPP tables、regulators、firmware votes、thermal limits）。
- DSP transport：`AdspProbe.cpp`（firmware load/SMEM/SMP2P/GLINK/mailbox/resource setup）、`ShengAdsp.h`（`ShengAdspClient`/channel registration/queued sends）、`LegacyDisplayProbe.cpp`（init order）。步骤：adapt firmware auth/reserved memory/power votes → mailbox/ready/crash paths → channel state/receive callbacks on DSP thread copy bytes to bounded queue/wake consumer → `sheng_adsp_channel(name, intent_size, intent_count, initiator, callbacks, context)` → `sheng_adsp_send` returns 0 queued, -1 full/oversized, -2 invalid args; max `SHENG_ADSP_MAX_MESSAGE` 512 bytes → disconnect cancel/invalidate; reconnect negotiate/restore.
- Audio：AudioReach/GPR references `ShengGpr.h`/`ShengAudioReach.h`/`AudioProbe.cpp`/`ShengCs35l43.c`/`ShengAudioService.cpp`/`ShengAudioPlugIn.c`; Linux `q6apm.h/.c`/`audioreach.c`/`topology.c`/`q6apm-dai.c`;步骤：open/identify GPR service → describe one complete route → graph open/configure/prepare/start/stop/close → period buffer path (`q6apm_write_async`/`q6apm_read`) → OS service ABI → exercise route.
- SM8550 audio facts: DSP takes buffer as 32-bit address with stream index (`0x1001 & 0xf`) in upper word; period buffer below 4 GiB; small GLINK intents first/larger on request; PRM own port/clock IDs, TX core clock `0x30c` not DT index; VA macro gates TX SoundWire master clock too; CoreAudio assumes 24 MHz host clock, on 19.2 MHz timebase audio service corrects at start else 25% IO cycle error.
- Microphone route: power codec → SoundWire link enumeration/manufacturer-part IDs → analog path (AMIC3/micbias 3/ADC2, gain, port/channel) → digital path (master port → TX decimator → codec DMA TX3) → read buffers (byte count/offset; short period normal) → publish input only after known sound capture; reference WCD938x/reset gpio108/ldob15/SoundWire device1 0x6d30000, mono 48 kHz, iOS HAL input port with Thunderbolt transport type; check `sheng-audio=4` `[mic]`/`[mic capture]`.
- Battery: `ShengBattmgr.h/.c`, `ShengBattery.cpp`, `BatteryProbe.cpp`, XNU `IOPMPowerSource.h`; protocol owner/message type/opcode/property ID/response length; one outstanding request + timeout; snapshot presence/external power/charge state/capacity/voltage/current/temp/time remaining; units micro→milli, capacity hundredths %, seconds→minutes; subclass `IOPMPowerSource`, work loop, response queue, request/refresh timers; `registerService()` then `updateStatus()`; subscribe changes/periodic refresh; transport loss cancel/mark stale; compare raw vs OS.
- Power: `CpuFreqProbe.cpp` EPSS LUT/CPU/L3 OPP; `QcomRpmh.h` resource votes; `ShengPlatformPower.cpp` OS-facing; `GpuPowerProbe.cpp` GPU clock governor; SM8550 governor inputs: CPU idle every 16ms, domain follows busiest CPU with 1.25 margin/steps down after 4 quieter windows; GPU GMU XO busy counter votes level + bandwidth over HFI; touch holds P CPU domains + GPU top for 1s after last report (`sheng-cpufreq-boost-ms`, `sheng-gpu-dcvs-boost-ms`); frames GPU submissions 2 of last 4 windows keep every CPU domain ≥60% top for 300ms, GPU work after idle starts at 2× current clock ≥578 MHz for 50ms; fence waits sleep until interrupt max 1ms (`sheng-gpu-pause-us`).

**K60 可执行项**
- K60 ADSP carveout `0x9fd00000/0x3100000`（49 MiB）；PMIC `pmk8350/pm8350/pm8350c/pm8350b/pmr735a/pmr735b/pm8450`。
- K60 音频是 2×AW882xx（`awinic,aw882xx_smartpa@34/@35`，I2C `0x34/0x35`，reset GPIO1/3，IRQ 88/63，spksw 52），不是 CS35L43/WCD938x/TFA9873；AudioReach/GPR 框架可从 PongPower/Sheng 复用，AW882xx 功放驱动与 20G81 HAL/route ABI 必须新写。
- K60 计划先移植 `PongPower`（`PongPlatformResources`/`QcomRpmh`），再做 WiFi/BT/音频；`PongPower` 的 `PongAudio.cpp`/`PongAudioService.cpp`/`PongAudioPlugIn.c`/`PongAudioRoute.h` 是可读参考。

**iOS 16.6.1/20G81 适用性**：部分/参考。DSP/audio 框架与“period buffer <4 GiB/24 MHz vs 19.2 MHz”类硬件事实可参考；具体 sheng 值（WCD938x/CS35L43）不适用。

### 26. `docs/porting/platform.md`（113 行）

**流程/规范要点**
- 先读 device-tree bindings/matching、ArmDTPlatform、ArmCpu；用 driver build integration 连接初始化/archive/OS ABI，然后做硬件检查。
- Source map：`ArmDTPlatform.cpp`（ADT root/child nubs/NVRAM publication）；`ArmCpu.cpp`（CPU registration/timer/GIC setup/secondary entry/IPI delivery）；`ArmSmmu4K.h`/`ArmSmmu4KContext.h`（table allocation/mappings/context programming，匹配 SMMU generation）。
- CPU/interrupt：记录 MPIDR affinity/boot CPU/enabled cores/PSCI method/GIC revision/distributor-redistributor ranges/stride/timer frequency/interrupt specifiers；共享拓扑放 SoC DTSI，板级 enablement 放 board DTS；`dtc -I dts -O dtb -i "$SOC_DTS" -o /tmp/board-hardware.dtb "$BOARD_DTS"`，再 `dtc -I dtb -O dts` 检查 `reg`/`ranges`/phandles/interrupt providers/disabled nodes。
- Performance clusters：两核类型 SoC 每个 CPU 节点必须 `unixnu,cluster-type = "E"` 或 `"P"`；ADT 携带 cluster-type，scheduler patch 运行 Edge scheduler with one E/one P cluster；SM8550 reference E cpu0-2 (A510), P cpu3-7 (A715/A710/X3)；检查 CPU governor per-domain busy share，UI work 应加载 P domains。
- Memory/DMA：比较 firmware RAM/secure carveouts/framebuffer/DSP/GPU firmware/payload/kernel allocations；硬件 DTS 用连续 handoff RAM range，loader owned-memory request 有自己的 size/alignment，二者与实际 UEFI memory map 一致；每个 DMA device 记录 address width/physical→IOVA/SMMU instance/stream/context ownership/cache policy；GPU/UFS/SPI/PCIe 可能不同 streams/policies。
- Block/OS services：`RamBlock`（dense/packed Data + ADT placeholders + `native_ufs_store` callbacks）、`VirtioMmioBlock`、`VerifiedRoot`、`SoftwareAES`、`AppleKeyStoreState`、`XnuPrelink`、`DarwinBoot`、`ShengPreflight`。
- 检查：`./unixnu status --json`、`./unixnu build kernel`；先检查 dependency order/config fragments/patch series；每个 selected archive 需要 OS inputs 与 initialization caller。

**K60 可执行项**
- 核对 `ArmDTPlatform`/`ArmCpu` 已在 `[components] include`，`ArmSmmu4K` 可作为独立 kit 复用；K60 当前 `archives` 含 `component:ArmDTPlatform`、`component:ArmCpu`。
- `dtc -I dts -O dtb -i ../UniXNU-sm8475-common/dts -o /tmp/mondrian-hardware.dtb dts/mondrian.dts`；检查 `reg`/`ranges`/phandles/中断 provider。
- 修复 CPU cluster：`sm8475.dtsi` 当前 8 核全 `"P"`，按 E/P 分组（A510 vs A710/X2）修改后再验证 governor per-domain。
- Memory/DMA：K60 DTS 的 `memory@900000000` 是 handoff arena，不是整机 DRAM；`dram_size` 与 DTS 一致（5 GiB），`owned_memory_size` 4.75 GiB；每个 DMA 设备（UFS stream 0xe0、WiFi/PCIe、USB、GPU）分别记录 SMMU context。

**iOS 16.6.1/20G81 适用性**：直接适用（通用平台层）；SM8550 的 E/P 具体核号不适用，K60 需按 SM8475 拓扑。

### 27. `docs/contributing/documentation.md`（118 行）

**流程/规范要点**
- 文档是 `docs/` 下的 VitePress 站点，发布到 `https://unixnu.com`。
- 流程：定位 owning page 与英文/中文对应页；编辑当前 procedure/reference；每次操作要有 prerequisites/working directory/ordered commands/expected results/next step；从相关 workflow 链接；`npm --prefix docs run build`；预览并检查命令块/next-step 链接。
- 要求 Node.js 22+、npm 10+；`cd docs && npm install && npm run dev`；`npm run build` 输出 `docs/.vitepress/dist`；`npm run preview`。
- 结构：`.vitepress/config.mts`、`theme/`、`public/`、`guide/`、`concepts/`、`porting/`、`drivers/`、`xnu/`、`devices/`、`reference/`、`contributing/`、`zh/`。
- 新增页面：Markdown 文件 → sidebar `config.mts` → `docs/zh/` 中文页与中文 sidebar → 从相关 guide/topic index 链接 → 从 Port a device 两种语言走通 → `npm run build` → 新 section 加 language switcher。
- 双语：根 `/` 英文，`/zh/` 简体中文；两边同页，同一 PR 更新。
- 写作规则：标准术语、直接陈述当前行为、避免 em/en dash、避免比喻、中性标题、单页单主题、表格用于 reference、列表用于 steps、设备特定值放设备页、每个 procedure 有具体命令、按执行顺序编号并写输入/工作目录/命令/期望结果/下一步。
- Link check：`cd docs && npm run build`，VitePress 断链失败。
- Device records：site build 需要 Python 3.11+；`npm run build` 渲染已提交 catalog/record snapshots；catalog workflow 每天两次；编辑设备仓库 `porting.toml`；两种语言共用同一记录文本。
- Driver guides：按 hardware inputs → interface implementation → OS integration → build → verification 组织；链接真实 source file 的 reviewed revision；写 symbols/call order/data ownership/error handling；设备状态留 record。

**K60 可执行项**
- 本文件是仓库内 `docs/plans/` 研究文档，不是站点页面；若以后发布到 uniixnu.com，需要英文/中文两版并更新 sidebar。
- 提交文档前跑 `npm --prefix docs run build`（在 `E:/hackios/UniXNU`），修复断链。
- 设备特定值（K60 的地址/UUID/窗口）放设备仓库记录，不写进公共 guide。

**iOS 16.6.1/20G81 适用性**：直接适用（流程规范）。

### 28. `docs/contributing/repository.md`（91 行）

**流程/规范要点**
- 仓库分工：`UniXNU`（build tools/component catalog/ARM64 support/OS profiles/template/UEFI package/docs）、`UniXNU-<soc>-common`（SoC config/DTSI/platform ops/patch series）、`UniXNU-<device>`（board DTS/peripherals/components/partitions/packaging）、component repos、`uefi-<device>`。
- Source kind → assembled path：`driver`→`drivers/<ID>`、`kit`→`kits/<ID>`、`patch`→`patches/<name>`、`script`→`scripts/`、`package`→`package/`、`refer`→`refer/<name>`、`soc`→selected profile root。
- Format 2 应用 ARM64/SoC/OS/device 四层 profile；assembled target `out/<device>/<os_profile>/<config>/tree`；modules linked、scripts copied、device `package/` → `kits/<board.kit>`。
- Component work 6 步：读 AGENTS.md/search `components.toml`/inspect interfaces → shared controller/protocol code in component repo → SoC ops/resources in SoC repo and board policy in device repo → record source identity/revision/dependencies/build command/outputs/runtime identifiers → update consumers/README/AGENTS/site pages → run build and record host/device results separately。
- Canonical names use hardware scope/protocol/function；renames preserve history/pinned revisions；compatibility aliases use official source identity；community sources keep own identity。
- Commit prefixes：`feat(<area>)`、`fix(<area>)`、`docs`、`build(<area>)`、`chore`；commit messages describe changes；docs describe current behavior。
- Device records：main repo submodules provide shared components；device repos own board driver submodules；catalog supports discovery/selection；official devices maintain `porting.toml`；site renders revision in `devices.toml`；code changes update findings/evidence。

**K60 可执行项**
- 本任务使用 `docs` 前缀：`docs(research): read every porting document`。
- 修改代码与文档分 commit 同一 PR；设备记录与代码变更同步。
- 组件变更要更新 `components.toml` 的 revision/`outputs`/dependencies，并同时更新英文/中文站点页。

**iOS 16.6.1/20G81 适用性**：直接适用（仓库治理）。

### 29. `docs/building.md`（360 行）

**流程/规范要点**
- `unixnu` 解析 ARM64/SoC/OS/device profiles，选组件依赖，组装 target tree，逐步构建；format 2 输出 `out/<device>/<os_profile>/<config>/`。
- 固件必须先 build，DSC/FDF 必须含 UniXNU/UniXNUDxe/DarwinBoot/payload volume driver；Mu-Silicium FDT initrd path 用 `UniXNURamDiskDxe` + DiskIoDxe + FAT。
- 准备：clone UniXNU + device + UEFI repos with submodules；`./unixnu defconfig "$DEFCONFIG" -D ../UniXNU-device`、`fetch`、`status --json`；`-D` 记录到 `out/state.json`。
- 本地输入：`cp unixnu.example.toml unixnu.local.toml`；填 device/UEFI paths/firmware DTB/platform identity/kernelcache/trust-cache/Data seed；`./unixnu ipsw info`、`ipsw fetch`、`tree`。
- 构建：`./unixnu build kernel` → `build package` → `build firmware`；kernel 输出 `<output>/kernel/kernel.macho`，package 输出 `<output>/package/Build/Out/AARCH64-DEBUG/UniXNU.efi`，firmware 输出 `[firmware] fd`。
- userdata：`./unixnu build userdata --dry-run` → `build userdata`；检查 `userdata-root.json`；payload：`./unixnu build payload`；检查 `payload.json`/printed command line；FAT 内容 `unixnu.toml`/kernel/ADT/sidecars。
- boot：`./unixnu bootimg`；检查 `boot/boot.json` 的 firmware/DTB/payload/`ramdisk_bytes` nonzero；改 boot args 后 payload+bootimg；改 kernel code 先 rebuild kernel。
- macOS runner：`macos-26`、`xcode` 默认 26.6；inputs `device_repository`/`device_ref`/`defconfig`/`xcode`/`steps`（kernel、kernel payload、kernel userdata、kernel userdata payload）/`ipsw_url`/`pre_build`/`trust_cache_url`/`owner_trust_cache`/`data_seed_url`/`grow_gib`/`skip_setup`；secret `UNIXNU_UNIQUE_CHIP_ID`、`UNIXNU_DEVICE_TOKEN`；只发布 redacted `*.log`。
- Linux host：installer supports apt/dnf/pacman/zypper on glibc；`--package-manager none` + `--llvm-config FILE`；`scripts/linux/setup-toolchain.py --print-packages`/`sudo ...`；`./unixnu defconfig`/`fetch`/`build kernel`；`prepare-xnu.py` source/libs；`build-firehose.sh`、`build-corecrypto-14.py`、`lzfse`。
- Commands 表：`defconfig`、`fetch [NAME...] [--update]`、`tree`、`ipsw info`、`ipsw fetch`、`build [kernel] [package] [firmware] [payload] [prelink]`、`build userdata [--dry-run]`、`bootimg`、`status [--json]`、`clean`。
- Options：`-D DIR`、`--out DIR`、`-j N`、`--target DEBUG|RELEASE`、`--uefi DIR`、`--edk2 DIR`、`--kernelcache FILE`、`--kernel FILE`、`--kernel-arg NAME[=VALUE]`、`--trust-cache FILE`、`--owner-trust-cache FILE`、`--data-ramdisk FILE`、`--skip-setup`、`--unique-chip-id HEX`、`--ipsw PATH_OR_URL`、`--skip-preflight`、`--dry-run`；env vars `UNIXNU_DEVICE`/`UNIXNU_OUT`/`UNIXNU_UEFI`/`UNIXNU_EDK2`/`UNIXNU_KERNELCACHE`/`UNIXNU_DTB`/`UNIXNU_IPSW`/`UNIXNU_UNIQUE_CHIP_ID`/`JOBS`。
- Steps 细节：defconfig merges ordered fragments + device defconfig last；fetch shallow blobless cone sparse, writes `unixnu.lock`；tree layout `drivers/kits/patches/refer/scripts/package/build/.cache`；ipsw HTTP range + sha256 pins；kernel pass/compile records/archives/BCM2837/DEVELOPMENT/iOS 17/prelink；package EDK II outputs; firmware preflight/patches/EDK II; payload FAT; userdata OS/SystemOS `SHNGROOT`; bootimg BootShim/FV/gzip/DTB/mkbootimg/unpack verify。
- Output layout and reproducibility：`out/state.json`、`out/feeds/`、`out/ipsw/<build>/`、target `.config`/`tree`/`logs`/`kernel`/`package`/`payload`/`boot`/`userdata`；`unixnu.lock` pins every source；firmware `SOURCE_DATE_EPOCH` = Mu-Silicium commit；boot image deterministic for given FV/DTB/ramdisk；payload random seed makes two builds differ。

**K60 可执行项**
- 用 `-D ../UniXNU-mondrian` 跑：
  ```sh
  ./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
  ./unixnu fetch -D ../UniXNU-mondrian
  ./unixnu status --json -D ../UniXNU-mondrian
  ./unixnu ipsw info -D ../UniXNU-mondrian
  ./unixnu ipsw fetch -D ../UniXNU-mondrian
  ./unixnu build kernel -D ../UniXNU-mondrian
  ./unixnu build payload -D ../UniXNU-mondrian
  ./unixnu bootimg -D ../UniXNU-mondrian --uefi ../uefi-mondrian --dtb out/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb
  ```
- 输出根：`out/mondrian/ipados-16.6.1-20G81/mondrian/`；K60 当前 `package/` 只有 README，`./unixnu build package` 不会产出可用设备包；实际打包走 `uefi-mondrian`/`k60-macos-preflight.sh` 等脚本。若按文档启用 package，需要先补 `package/Kit.toml`。
- K60 在 Linux/WSL 上构建：使用 `scripts/linux/setup-toolchain.py`，`JOBS` 控制并行；`--target DEBUG` 默认。
- 修改 `kernel_args` 后重跑 `build payload` + `bootimg`，不要只重打 bootimg。

**iOS 16.6.1/20G81 适用性**：大部分直接适用；但文档 kernel 步骤写“iOS 17”，K60 实际是 16.6.1/XNU 8796，需走 profile 的自定义 prelink/build 脚本；`build package` 与 `bootimg` 的默认路径对 K60 不完整。

### 30. `docs/index.md`（37 行）

**流程/规范要点**
- Home layout frontmatter：`migration`（title/text/label/link 到 `/porting/migration`）、`hero`（text “Run iOS and macOS on non-Apple ARM64 hardware”、tagline、logo、actions：Port a device、Supported devices、GitHub、X、Telegram、QQ Group）。
- 正文只有一个 info block：文档随源码修订，具体细节以 linked build report 或 repository 为准。
- 这是站点首页，不是技术流程页。

**K60 可执行项**
- 无命令；只影响站点入口。K60 若发布设备页，应确保 `Port a device` 与 `Supported devices` 链接可达。

**iOS 16.6.1/20G81 适用性**：通用（站点入口），无版本含义。

---

## 二、对 K60 的可执行项汇总

> 按优先级排列。P0 = 不补就无法按 format 2 验收；P1 = 影响 bring-up/驱动；P2 = 发布与文档。

### A. 仓库格式与记录（P0）

1. **补 `scripts/package.sh`**：从 `E:/hackios/UniXNU/templates/package.sh` 原样复制到 `E:/hackios/UniXNU-mondrian/scripts/package.sh`，不改脚本内容。
2. **补 `.github/workflows/package.yml`**：按 `packaging.md` 的 GitHub 流程，macOS runner + `scripts/package.sh`，artifacts 为 `boot.img`/`payload.img`/`kernel.macho`/`package.manifest.json`。
3. **补 `board.toml [package]`**：
   ```toml
   [package]
   unixnu = "../UniXNU"

   [package.defconfig]
   "ipados-16.6.1-20G81" = "mondrian_defconfig"
   ```
4. **补 `package/Kit.toml`**（如果 K60 的 `kit = "mondrian"` 要产出 kit）；当前 `package/` 只有 `README.md`，格式 2 下空 kit 会让 `kits/mondrian` 为空。
5. **补 `[firmware] preflight`**（若 `uefi-mondrian` 有板级校验脚本）；文档要求 preflight 在 EDK II build 前运行。
6. **`porting.toml` 补第 14 个 area `cellular`**；K60 是手机，不能直接 `not-applicable`，按当前范围写 `planned` 或说明 modem 不在本期路线。
7. **重评 `porting.toml` status**：`storage`/`display`/`input`/`gpu`/`network`/`audio`/`power` 目前都是 `planned`；只有具备对应证据时才升级为 `implemented`/`host-verified`/`device-verified`。`packaging` 的 `host-verified` 在 `package.sh` 补齐前不成立。
8. **跑两个 checker**：
   ```sh
   python3 scripts/check-porting-paths.py --quiet
   python3 scripts/porting-record.py check --device ../UniXNU-mondrian
   ```
9. **修掉 README/AGENTS 的 stale 路径**：`out/mondrian/ipados-18.7.10-22H374/mondrian/`、`build-darwin24-platform.py`、`k60-prelink-darwin24.py` 与 HEAD 的 `ipados-16.6.1-20G81` 不一致；README line 7、AGENTS line 143-153 需要统一。

### B. 构建链（P0）

10. **统一构建入口**：`./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian` → `fetch` → `status --json` → `tree`；所有后续命令带 `-D ../UniXNU-mondrian`。
11. **固定输出目录**：`out/mondrian/ipados-16.6.1-20G81/mondrian/`；kernel `kernel/kernel.macho`，payload `payload/payload.img`，boot `boot/boot.img`，DTB `device-tree/hardware.dtb`。
12. **修复 `/tmp` 依赖**：`board.toml` 的 `pong_native_driver_source = "/tmp/k60build/pong-driver"` 与 AGENTS 铁律 1 冲突；改为仓库内路径或 `E:\k60-work` 并写进 `local.toml`/记录。
13. **build inputs**：20G81 kernelcache sha256 `d260defc...`、`prebuilt/20G81-trustcache.bundle`（如仍用）、Data seed、`--unique-chip-id`、`uefi-mondrian` checkout、firmware DTB；按 `migration.md#build-inputs` 逐项记录来源。
14. **每次改 boot args**：`./unixnu build payload` + `./unixnu bootimg`，不要只重打 boot。
15. **每次改 kernel code**：先 `./unixnu build kernel`，再 payload/bootimg。

### C. DTS/ADT（P1）

16. **保持 `/memory` 单节点单 reg**：`dts/mondrian.dts` 的 `memory@900000000` 为 handoff arena（5 GiB），不要写成整机 12 GiB；`board.toml dram_size = "0x140000000"` 与 DTS 一致。
17. **`owned_memory_size` 在 256 MiB–8 GiB 范围**：当前 `0x130000000`（4.75 GiB）合法；`MEMORY-12G-PLAN.md` 已确认 12 GiB 单窗口物理上不存在，不要按 12 GiB 改 `darwinboot-memory-size`。
18. **CPU cluster-type 修正**：`sm8475.dtsi` 当前 8 核全 `"P"`；按实际 A510/A710/X2 分组设置 `"E"`/`"P"`，否则 Edge scheduler 只有单簇，UI 线程不会被钉到 P 簇。
19. **必需 ADT 节点**：`/cpus`、`/arm-io`、`/defaults`、`/options`、`/chosen`（random-seed/CHRP NVRAM/`dram-base`/`dram-size`）必须齐全；`/chosen` 不能缺 NVRAM proxy。
20. **Apple identity**：`chip-id = "8015"`、`unique-chip-id` 构建时传入、`root_match_volume_uuid = "C5DAF029-2070-4F68-B3CC-1D1320344CF0"`（与 Data UUID `1BCD69FF-24A5-48B1-94B6-8FE592B2F597` 区分）。
21. **memory-map placeholders**：`RAMDisk`/`PackedRAMDisk`/`TrustCache` 各 16 字节，按 payload 实际输入生成；缺一个 DarwinBoot 返回 `EFI_COMPROMISED_DATA`。
22. **boot image DTB 与 firmware DTB 分开**：`[[bootimg.dtb_node]]` 只给 stock bootloader 补 splash/reserved-memory；`board.toml [device_tree]` 只给 XNU 的 ADT。

### D. UEFI/固件/日志（P1）

23. **固件 DSC/FDF 必需模块**：`UniXNU.inf`、`UniXNUDxe.inf`、`DarwinBoot22`（按实际 INF 名）、`UniXNURamDiskDxe.inf`、`DiskIoDxe.inf`、`Fat.inf`；缺任一，菜单看不到 payload。
24. **AdvancedLogDxe**：DSC `[Components]` + FDF `INF`，`PcdUniXNUDeviceModel = "mondrian"`，`[payload] tools = true`；否则无法 QR 抓固件日志。
25. **固件 build**：`./unixnu build firmware --uefi ../uefi-mondrian`；核对 `Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd` 与 `[uefi_fd] size`。
26. **bootimg 校验**：`boot/boot.json` 的 `ramdisk_bytes` 非零、shim header `ARM\x64`、FV/DTB/payload 与输入一致；K60 `unixnu bootimg` 对 v4 的 `page_size` 误报用 `scripts/verify-k60-boot-img.sh` 复核。
27. **日志路线**：K60 无 UART、ramoops 不可用；以屏幕/panic 屏为主，固件阶段用 QR；持久日志需先实现 Linux/recovery reader，不能假设 pstore。

### E. 驱动适配顺序与 K60 对应实现（P1/P2）

28. **顺序**：platform/memory → storage/root → display/brightness → input → GPU → Wi-Fi → Bluetooth → USB → DSP/audio/power → OS services/packaging。
29. **保留 K60 实际组件**：`PongUfs`（SM8475 UFS）、`PongAdreno`/`PongMetal`（A730）、`PongWifi`（QCA6490/ath11k）、`PongPower`（ADSP/AudioReach/电源）、Goodix 触摸协议、AW882xx 功放、QCA6490 BT；不要用官方 `ShengUfs`/`Adreno740`/`Ath12kWifi`/`QcaBluetooth`/`QcomDwc3` 直接替换。
30. **每个驱动按 `drivers.md` 5 个 boundary 记录**：Hardware/Transport/Memory/OS/Build；每个 capability 在 `porting.toml` 有独立 area/finding/evidence。
31. **ABI 以 20G81 kernelcache 为准**：`profiles/os/ipados-16.6.1-20G81/profile.toml` 的 `abi = ["IOGPUFamily", "IOHIDFamily", "IOMobileGraphicsFamily"]`；任何 iOS 17/27 的 candidate/JSON/记录都不能直接当 16.6.1 证据。

### F. 发布与文档（P2）

32. **README/AGENTS 重写为 16.6.1 口径**：命令、输出目录、prelink/board 路径全部统一；删除 darwin24 残留（或明确标注历史）。
33. **站点发布**：如发布 `DOCS-PORTING-ALL.md` 到 unixnu.com，按 `contributing/documentation.md` 做英文/中文两版、sidebar、断链检查。
34. **提交规范**：`docs(research): read every porting document`（本任务），代码与文档分 commit，同一 PR。

---

## 三、与当前仓库/方案的冲突点

### 3.1 硬冲突（不处理就无法按 format 2 验收）

| ID | 冲突 | 依据 | 处置 |
| --- | --- | --- | --- |
| C01 | 设备仓库缺 `scripts/package.sh`，但 `packaging.md` 标注 **Mandatory for every device repository** | `packaging.md:3-6`；K60 `Test-Path scripts/package.sh = False` | 从 `templates/package.sh` 原样复制；补 `[package]`/`[package.defconfig]` |
| C02 | 缺 `.github/workflows/package.yml` | `device-repository.md:17-18,57`；`packaging.md:55-66` | 补 workflow，macOS runner，artifacts 四件套 |
| C03 | `package/` 只有 `README.md`，无 `Kit.toml`/kit 内容；`board.kit = "mondrian"` 会让 `kits/mondrian` 为空 | `device-repository.md:455-487`；`package/README.md` | 补 `Kit.toml` 与 kit 目录，或明确该板不使用 kit 并记录 |
| C04 | `porting.toml` 13 个 area，`records.md` 要求 14 个（含 `cellular`） | `records.md:15-39`；K60 `porting.toml` area id 列表 | 增加 `cellular`；K60 有 modem，写 `planned` 或说明范围 |
| C05 | `porting.toml` 多个 area 状态与证据不匹配（storage/display/input/gpu/network/audio/power 全 `planned`；packaging `host-verified` 无 package.sh） | `records.md:66-80`；`docs/state/STATE-2026-11-07.md` | 按 status 定义重评，用 evidence 升级或降级 |
| C06 | `board.toml [components]` 只有 4 项，未覆盖已存在的 display/input/GPU/network/audio/power 驱动 | `device-repository.md:49-59`；`steps.md:65-86`；K60 `board.toml:13-14` | 按实际启用组件补全 `[components] include`，含 catalog 依赖 |
| C07 | `board.toml [kernel] archives` 只有 3 个 component，`patch_series` 只有 `device:patches/xnu/series`；文档要求完整四层序列与 archive plan | `device-repository.md:262-276`；`steps.md:84-85`；K60 `board.toml:16-22` | 补 `arch:`/`soc:`/`os:`/`device:` 的 `patch_series`（如果实际使用），并补 archives；数组覆盖必须写全量 |
| C08 | `board.toml` 的 `pong_native_driver_source = "/tmp/k60build/pong-driver"` | K60 `board.toml:23-29`；AGENTS 铁律 1（`/tmp` 不可持久）；`building.md:352-354` 可复现性 | 移到仓库内或 `E:\k60-work`，通过 `local.toml`/`--local-module` 传入 |
| C09 | `[firmware]` 无 `preflight` | `device-repository.md:280-308`；`uefi-firmware.md:170-183`；K60 `board.toml:41-71` | 若 `uefi-mondrian` 有板级检查，补 `preflight = [...]`；否则在 record 中说明 |
| C10 | K60 的 `DarwinBoot22`/`{tree}/drivers/DarwinBoot22` 与文档的 `DarwinBootPkg/Driver/DarwinBoot.inf` 不一致 | `uefi-firmware.md:24-44`；K60 `board.toml:49-64`；`profiles/os/ipados-16.6.1-20G81/profile.toml` | 保留 Darwin22，按实际 INF/路径写进 DSC/FDF；记录 ABI 0x2e0 |
| C11 | `board.toml [payload] trust_cache_sha256 = []`、B 决策放弃 trust-cache，与文档默认 `--trust-cache`/`trust_cache_sha256` 路径不一致 | K60 `board.toml:141-146`；`device-repository.md:330-374`；`building.md:215-217` | 保持 B 决策；构建不传 `--trust-cache`，record 写明原因；不要照文档的 trust-cache 验证路径 |
| C12 | `README.md`/`AGENTS.md` 仍写 `ipados-18.7.10-22H374` 和 `build-darwin24-platform.py`，但 HEAD `board.toml` 是 `ipados-16.6.1-20G81` | `README.md:7,38-54`；`AGENTS.md:143-153`；`board.toml:7` | 统一到 16.6.1；把 darwin24 文字移入 archive/历史说明 |

### 3.2 语义/范围冲突（不要照抄文档到 K60）

| ID | 冲突 | 依据 | 处置 |
| --- | --- | --- | --- |
| C13 | `packaging.md` 的 `--os 17|27` 没有 16；`building.md` kernel 步骤写 iOS 17；K60 是 16.6.1/XNU 8796 | `packaging.md:41-53`；`building.md:256-269`；`profiles/os/ipados-16.6.1-20G81/profile.toml` | 所有命令用完整 profile `--os ipados-16.6.1-20G81`；kernel 走 K60 自定义 prelink；不要把 17 的 build 结果当 16 资格 |
| C14 | `arm64e.md` 仅支持 sheng/SM8550/iPadOS 27；K60 不在列表 | `arm64e.md:37-48`；K60 `board.toml:7` | K60 保持 arm64；不得切 arm64e/27 |
| C15 | 官方驱动映射与 K60 硬件不匹配：Adreno740/A740 vs A730；ShengUfs vs PongUfs；Ath12kWifi vs QCA6490/PongWifi；QcaBluetooth vs QCA6490；QcomDwc3 27/24A446 vs 16.6.1；GopFramebuffer vs MiniIOMobileFramebuffer；CS35L43/WCD938x vs AW882xx | `gpu.md:22-32`；`ufs.md:5-10`；`network.md:3-5`；`bluetooth.md:3-8`；`usb.md:23-33`；`display.md:33-45`；`power.md:53-68`；`OFFICIAL-DRIVER-MAP.md` 结论 | 保留 pong 设备栈；官方组件只作接口/方法参考，不替换；在 `porting.toml` 记录不适用理由 |
| C16 | `dual-system-partition.md` 要求创建 `unixnu` 分区；K60 已有 32 GiB `unixnu` GPT，且 AGENTS 禁止 `fastboot flash` Android 分区 | `dual-system-partition.md:1-20`；K60 `board.toml:31-35`；`AGENTS.md` device rules | 不运行 `apply`；只 `inspect`/`verify`；任何写 `unixnu` 的操作需单独方案并脱离当前只 boot 约束 |
| C17 | `log-capture.md` 的 persistent log/reader 假设 reserved region + Linux/recovery；K60 ramoops 实际不可用、无 UART | `log-capture.md:116-176`；`docs/state/STATE-2026-11-07.md:161-165` | 以屏幕/panic + QR 为主；持久日志作为独立任务，先建 log region + reader |
| C18 | `gpu-diagnostics.md` 的 `sheng-*` 开关/K60 不可用；`gpu.md` 的 A740 固件/K60 不可用 | `gpu-diagnostics.md:5-9`；`gpu.md:44-52`；K60 `docs/plans/GPU-ENABLE-PLAN.md` | 用 `pong_gpu_*`/PongAdreno 路径；只借用 trace 问题框架 |
| C19 | `display.md` 的 GopFramebuffer/DPU/亮度示例是 SM8550/sheng；K60 当前 `MiniIOMobileFramebuffer` + CPU 软件呈现 | `display.md:16-45,73-100`；K60 补丁 0210/0211/0213 | 保留 K60 当前路径；GopFramebuffer 作为后续候选，不直接替换 |
| C20 | `input.md` 的 Novatek 40×60 matrix 不适用于 K60 的 Goodix m11a-spi | `input.md:23-54`；`K60-TOUCH-PARAMS.md`；`OFFICIAL-DRIVER-MAP.md` | 复用 `QcomGeniSpi` 传输概念 + `ShengHidInput` HID 概念；Goodix 协议另写 |
| C21 | `power.md`/`bluetooth.md` 的音频/蓝牙示例是 sheng WCN7850/CS35L43/WCD938x/TFA9873；K60 是 QCA6490 + AW882xx | `power.md:53-68`；`bluetooth.md:24-35`；`BT-AUDIO-PORT-PLAN.md` | 保留 PongPower/AudioReach 框架；AW882xx/QCA6490 驱动新写 |
| C22 | `packaging.md` 要求单一 build target/`[os_overrides]`，K60 同时保留 `patches/xnu`（16.6.1）与 `patches/xnu-ipados18`（darwin24）两套系列 | `packaging.md:19-25`；K60 `README.md:18-19`；`patches/xnu-ipados18/` | 采用 package.sh 时把 16.6.1 设为唯一 build target，darwin24 系列归档；或明确双路线例外并记录 |
| C23 | `records.md` 要求官方 `scripts/porting-record.py`，K60 只有自定义 `scripts/check-porting-paths.py` | `records.md:92-104`；K60 `scripts/check-porting-paths.py:1-10` | 自定义预检保留，官方 checker 作为验收；在 CI 里跑两者 |
| C24 | `device-tree.md` 的 `darwinboot-memory-size` 上限 8 GiB，`MEMORY-12G-PLAN.md` 讨论 12 GiB | `device-tree.md:168-185`；`MEMORY-12G-PLAN.md` 结论（12 GiB 单窗口不可行，最长连续 8.652 GiB） | 不把 12 GiB 写成单窗口；当前 4.75 GiB 保持；如做多区 pmap 另立方案 |

### 3.3 文档空白（当前方案必须自担）

1. **userland `apply()`/OS 窗口改写**：30 篇没有 pong `userland/build.py prepare()/apply()`、`/pong/stock-config`、`launchd.ios` 的说明；K60 的 `APPLY-PIPELINE.md` 仍是唯一可执行路径，不能因为文档没提就跳过。
2. **16.6.1 专属 ABI**：文档不提供 20G81 的 IOKit/IOHID/IOGPU/MobileFramebuffer ABI 数据；K60 必须以 `profiles/os/ipados-16.6.1-20G81/profile.toml` + `kernelcache` 自行审计。
3. **K60 板级常量**：文档的 SM8550 示例不覆盖 SM8475 的 UFS/GCC/SMMU/PCIe/PMIC/触摸/音频地址；以 `dts/mondrian.dts`、`docs/plans/K60-TOUCH-PARAMS.md`、`WIFI-PORT-PLAN.md`、`BT-AUDIO-PORT-PLAN.md` 为准。
4. **持久日志硬件**：K60 无 UART、ramoops 掉电失效；文档的 Linux/recovery reader 需要新写，不能直接复用 sheng 的 `read-sheng-log.py`。
5. **双系统**：K60 已有 `unixnu` 分区，文档的创建流程不适用；`docs/reference/DUAL-SYSTEM.md` 是 K60 自己的双系统记录。

---

## 四、覆盖清单（30/30）

> 清单生成命令（在 `E:/hackios/UniXNU` 下执行）：
> ```sh
> find docs/porting docs/contributing -name '*.md' | sort
> # 再追加：
> docs/building.md docs/index.md
> ```
> 结果：`docs/porting/` 26 篇 + `docs/contributing/` 2 篇 + 根目录 2 篇 = 30 篇。
> 每篇均已从第 1 行读到 EOF；行数、SHA-256 前缀来自 `E:/hackios/UniXNU` @ `75ae626a12764c706fc0b94c52a3eea09447dbaa`。

- [x] 01 `docs/porting/arm64e.md`（89 行，`1DDF36CD68DD4A10`）
- [x] 02 `docs/porting/baseband.md`（80 行，`975E693EFE4B359A`）
- [x] 03 `docs/porting/bluetooth.md`（147 行，`9578C40D3EA62A94`）
- [x] 04 `docs/porting/bring-up.md`（155 行，`E90F511C3B9746DF`）
- [x] 05 `docs/porting/device-repository.md`（505 行，`76ECF41F6E20B7ED`）
- [x] 06 `docs/porting/device-tree.md`（308 行，`B20F66420A969A79`）
- [x] 07 `docs/porting/display.md`（150 行，`5CE0DA4E430F6291`）
- [x] 08 `docs/porting/drivers.md`（123 行，`1A358E731FE9BC28`）
- [x] 09 `docs/porting/dual-system-partition.md`（197 行，`573F2E2257A6CAAA`）
- [x] 10 `docs/porting/gpu.md`（188 行，`238F08CA362B363C`）
- [x] 11 `docs/porting/gpu-diagnostics.md`（76 行，`59D8659E1A1BF27B`）
- [x] 12 `docs/porting/index.md`（31 行，`236C7247713A5274`）
- [x] 13 `docs/porting/input.md`（104 行，`0EE1FEA5C04FAA1D`）
- [x] 14 `docs/porting/log-capture.md`（225 行，`2B1684CD0E1D7698`）
- [x] 15 `docs/porting/migration.md`（517 行，`E9D5EECFDBCEB59E`）
- [x] 16 `docs/porting/network.md`（121 行，`8EC4908C73DCD11E`）
- [x] 17 `docs/porting/packaging.md`（171 行，`53DE19EB0138B8A3`）
- [x] 18 `docs/porting/platform.md`（113 行，`60428DDA5E2B1188`）
- [x] 19 `docs/porting/power.md`（233 行，`A2EFBAF127F616B3`）
- [x] 20 `docs/porting/records.md`（164 行，`2EFD9BE75D0DF246`）
- [x] 21 `docs/porting/sm8550.md`（16 行，`8AB63018AE0140D8`）
- [x] 22 `docs/porting/soc-support.md`（151 行，`D70F04FFE6C14590`）
- [x] 23 `docs/porting/steps.md`（184 行，`013075F3803C6402`）
- [x] 24 `docs/porting/uefi-firmware.md`（266 行，`A2F22133D3622813`）
- [x] 25 `docs/porting/ufs.md`（145 行，`9347EA8F66CDA355`）
- [x] 26 `docs/porting/usb.md`（157 行，`DF513C5B4510A676`）
- [x] 27 `docs/contributing/documentation.md`（118 行，`19582A33E2FEDF0B`）
- [x] 28 `docs/contributing/repository.md`（91 行，`441FB36C43F40B1C`）
- [x] 29 `docs/building.md`（360 行，`A39583335DDB3BB9`）
- [x] 30 `docs/index.md`（37 行，`6341071A0F6F20C7`）

**合计：30/30 已全文阅读。**

<!-- 文档结束：2026-11-08，来源 UniXNU @ 75ae626a12764c706fc0b94c52a3eea09447dbaa -->
