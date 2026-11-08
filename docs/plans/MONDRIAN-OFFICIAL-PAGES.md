# MONDRIAN 官方设备页逐域实现方案

> 研读对象：UniXNU 官方 `docs/devices/` 下全部 mondrian（Redmi K60 / SM8475）设备页，以及 `docs/devices/index.md` 的 mondrian 索引行（第 124–127 行）。
>
> 本次全文读完的四页：`mondrian.md`（529 行）、`mondrian-mzyxsl.md`（664 行）、`mondrian-wohusaixing.md`（503 行）、`mondrian-xtom0706.md`（505 行）。
>
> 证据标签沿用页面：`source`（源码/仓库事实）、`host`（主机侧构建或测试）、`device`（真机观察）；页面中只有模板句、没有实际经验的条目会明确标注。
>
> 本文件只做汇编与实现路径设计，不改代码、不改配置。写入时的当前仓库基线：`fix/k60-measured-high-window` 分支 HEAD `9b4fec1`。

## 0. 结论速览

四个页面不是四份同等深度的移植记录，而是同一设备四条不同阶段的分支快照：

- **mzyxsl 页是源码覆盖最全的一页**：配置、DarwinBoot22、ArmCpu、NativeRamBlock、NativeUfs、显示补丁、PongAdreno/GPU 都有实现级内容；但作者自己反复标注“source only / 无设备日志”，且其 12 GiB 单一 `/memory` 与真机六段内存测量冲突。
- **Emilelu 页是真机证据最多的一页**：Firmware and boot、CPU、Memory、Diagnostics 是 `device-verified`，给出了 Darwin 24 loader、扁平 MPIDR、8.625 GiB arena/7 GiB window、framebuffer breadcrumbs 的原始观察；但 Storage/Display/Input/GPU 仍是 `planned`，且页面存在“20G81 profile 配置 + Darwin 24 证据”的混用。
- **wohusaixing 与 XTOM0706 页是配置脚手架**：只有 Configuration 与 Image assembly 有实质内容；其余 11 个域只有生成模板的 “Collect the first … observation…” 句子。XTOM0706 的实际贡献是 `display-scale=3`，被 Emilelu 页采用。
- **K60 当前仓库已经在四条快照之外继续前进**：`patches/xnu/series` 现有 198 条启用项、221 个 `.patch` 文件，远超页面的 83/98 条；但页面的关键结论仍直接指出当前未完成项——secondary CPU 未过 entry checkpoint、内存窗口仍停在 4.75 GiB、触摸 ADT 没有 touch 属性、Network/Audio/Power 无驱动。

一句话选择原则：**要真机事实看 Emilelu，要完整源码看 mzyxsl；memory 绝不要照 mzyxsl 的 12 GiB 单段，input/display/GPU/storage 只能照 mzyxsl，Network/Audio/Power 没有任何作者页可照。**

## ① 各页 status 对照表

### 1.1 页面与仓库元数据

| 页面 | 仓库 | 页面源记录 commit | 组件 / 启用补丁 | 页面行数 |
|---|---|---|---|---:|
| `mondrian.md`（Emilelu） | [Emilelu/UniXNU-mondrian](https://github.com/Emilelu/UniXNU-mondrian) | `c39ff292eee2726c0135f3ba3a98462c9c21d8de`（2026-11-03，`docs: merge kernel baseline into device readme`） | 3 个组件（ArmDTPlatform、ArmCpu、XnuPrelink）/ 83 条有序补丁 | 529 |
| `mondrian-mzyxsl.md`（mzyxsl） | [mzyxsl/UniXNU-mondrian](https://github.com/mzyxsl/UniXNU-mondrian) | `76552b88441757defce4080a241c2f0ea7464538`（2026-10-30，`k60: align the porting record and docs with the building flow`） | 4 个组件（ArmDTPlatform、ArmCpu、XnuPrelink、PongUfs）/ 98 条有序补丁 | 664 |
| `mondrian-wohusaixing.md`（wohusaixing） | [wohusaixing/UniXNU-mondrian](https://github.com/wohusaixing/UniXNU-mondrian) | `092a61d8c20364eab86b35737c6b831c4cecc1ff` | 3 个组件 / 83 条有序补丁 | 503 |
| `mondrian-xtom0706.md`（XTOM0706） | [XTOM0706/UniXNU-mondrian](https://github.com/XTOM0706/UniXNU-mondrian) | `9d1a14f83d1050a042313f30dc9d5b7e80d31f7a` | 3 个组件 / 83 条有序补丁（Storage 另标 `PongUfs` 但状态 `planned`） | 505 |

状态词含义（按页面用法）：

- `planned`：只有模板或范围描述，没有可执行实现。
- `implemented`：有源码级实现，但不等于真机跑通；mzyxsl 页大量使用这一口径并在 Current limits 中承认无设备日志。
- `device-verified`：有真机观察/命令/revision。
- `host-verified`：只在主机侧编译或测试通过，未上机。

### 1.2 十三域状态矩阵

| 硬件域 | Emilelu `mondrian.md` | mzyxsl `mondrian-mzyxsl.md` | wohusaixing | XTOM0706 |
|---|---|---|---|---|
| Configuration | `implemented` | `implemented` | `implemented` | `implemented` |
| Firmware and boot | `device-verified` | `implemented` | `planned` | `planned` |
| CPU and interrupts | `implemented` | `implemented` | `planned` | `planned` |
| Memory and DMA | `implemented` | `implemented` | `planned` | `planned` |
| Storage and root | `planned` | `implemented` | `planned` | `planned` |
| Display | `planned` | `implemented` | `planned` | `planned` |
| Input | `planned` | `planned` | `planned` | `planned` |
| GPU | `planned` | `implemented` | `planned` | `planned` |
| Network | `planned` | `planned` | `planned` | `planned` |
| Audio | `planned` | `planned` | `planned` | `planned` |
| Power | `planned` | `planned` | `planned` | `planned` |
| Image assembly | `host-verified` | `host-verified` | `host-verified` | `host-verified` |
| Diagnostics | `device-verified` | `planned` | `planned` | `planned` |

按页面自报统计：Emilelu 为 2 个 `device-verified`（Firmware、Diagnostics）+ 3 个 `implemented`（Configuration、CPU、Memory）+ 1 个 `host-verified`（Image assembly）+ 7 个 `planned`；mzyxsl 为 7 个 `implemented`（Configuration、Firmware、CPU、Memory、Storage、Display、GPU）+ 1 个 `host-verified`（Image assembly）+ 5 个 `planned`（Input、Network、Audio、Power、Diagnostics）；wohusaixing/XTOM0706 均为 1 个 `implemented`（Configuration）+ 1 个 `host-verified`（Image assembly）+ 11 个 `planned`。

### 1.3 组件与实现规模差异

| 项目 | Emilelu | mzyxsl | wohusaixing | XTOM0706 |
|---|---|---|---|---|
| 配置组件 | ArmDTPlatform、ArmCpu、XnuPrelink | ArmDTPlatform、ArmCpu、XnuPrelink、PongUfs | ArmDTPlatform、ArmCpu、XnuPrelink | ArmDTPlatform、ArmCpu、XnuPrelink；Storage 另标 PongUfs |
| 补丁数量 | 83 | 98 | 83 | 83 |
| 驱动/组件覆盖 | ArmCpu、DarwinBoot22（页面证据）、PongUfs（planned） | ArmCpu、DarwinBoot22、NativeRamBlock、NativeUfs、PongAdreno、PongMetal | 仅配置 | 仅配置；Display 的 `display-scale=3` 来源 |
| 真机证据 | Firmware、CPU、Memory、Diagnostics | 无（页面全部为 source/host） | 无 | 无 |
| 最大优点 | 真机启动、CPU、内存、诊断证据链最完整 | 源码最全，storage/display/GPU/input 可直接抄结构和常量 | 配置模板干净 | display-scale=3 被其他页采用 |
| 最大风险 | 20G81 配置与 Darwin 24 证据混用；memory 只到 4 GiB 证明 | 12 GiB 单段 DTS 与真机六段内存冲突；多数 “implemented” 未上机 | 几乎无实现 | 几乎无实现 |

### 1.4 关键方法差异与冲突（先看这几条再读逐域）

| 主题 | Emilelu 页 | mzyxsl 页 | 应采用 |
|---|---|---|---|
| `boot_args` ABI | Evidence 明确 0x480（Darwin 24 loader：`boot-darwin24-bc8.img`） | DarwinBoot22 contract：0x2e0 字节、608 字节命令行在 0x6c、Video[6] 在 0x28 | 按目标 loader 选择：当前仓库 README 声称已修正为 Darwin 24 `0x480/1024`；若走 mzyxsl 的 20G81/Darwin 22 链，必须用 `0x2e0/608`，两套不能混 |
| Memory | 真机六段 RAM；最长连续可用 8.65 GiB `[0x840000000,0xa69b78000)`；4 GiB 已启动 XNU；8.625 GiB arena + 7 GiB window 被 loader 接受但 XNU 未启动；12 GiB 单 window 物理不可能 | DTS 写成 `memory@80000000` 单段 12 GiB（`reg = <0x0 0x80000000 0x3 0x0>`），ADT 生成器只接受单 memory 节点单 range | **只采用 Emilelu 的实测内存图**；mzyxsl 的 12 GiB 单段不得直接用于 12 GiB 六段机 |
| CPU 启动 | 真机验证扁平 MPIDR 0x000..0x700；Darwin 22 `ArmCpu::start()` 自触发 IPI 触发 `cpu_common.c:586` 断言；切 Darwin 24 first-boot path 后三根 probe bar 通过；后续 `0247` 做 flat target 翻译 | ArmCpu 源码完整（GICv3/MPIDR/PSCI/INTID/SPI），但明确写“eight-CPU start is unproven”；`pong_adt_contract` 只接受单 CPU ADT | 驱动实现抄 mzyxsl，target 处理抄 Emilelu `patches/xnu-ipados18/0247` + `0250`；八核日志必须真机补 |
| Storage | `planned`，但有 2026-10-31 真机 ENOSPC 事实：256 MiB APFS / 258 MiB Data GPT / unixnu offset 7420 MiB / 约 24.5 GiB 未分配 | `implemented`：完整 NativeUfs/RootLayout，32 MiB raw APFS seed，`CONFIG_XNU_OWNER_DATA_UFS=n`（实际 Data 持久化关闭） | 驱动结构抄 mzyxsl；Data 几何用当前仓库已实测的 2 GiB GPT 路径；dual-system 另做 |
| Display | 只有 `display-scale=3`（取自 XTOM0706 `9d1a14f8`） | 完整 0210–0213：1440×3200 native canvas、K60Display dictionary、空 accelerator stub、QuartzCore hooks | mzyxsl 是唯一显示实现；XTOM 只贡献 `display-scale=3` |
| GPU | `planned` | 唯一实现：Adreno 730 v3、GMU/HFI/CP/SMMU/Metal，但 committed defconfig 关闭且无 GPU frame | 只能照 mzyxsl；先按 GPU-ENABLE-PLAN 分阶段开 |
| Input | `planned` | 唯一源码：Goodix Berlin-D + SPMI 按键，但三补丁不在 series，状态仍 `planned` | 照 mzyxsl 的补丁和参数；补 ADT touch 节点后才能上机 |
| 诊断 | 真机 breadcrumbs + entry probe 证据最完整 | 主机侧 audit 工具完整，但无任何真机 transcript | 设备证据照 Emilelu，脚本照 mzyxsl |
| 完成度评价 | 硬件验证最深、源码覆盖中等 | 源码覆盖最广、硬件验证最浅 | 两者互补，不可只信一个页的 status |

## ② 逐域 findings 汇编

说明：每域先列 Emilelu，再列 mzyxsl；wohusaixing 与 XTOM0706 没有独立实现经验，只在 Configuration 与 Image assembly 两处有与 Emilelu 相同的生成内容，其余域为模板句，统一在 2.1 / 2.12 交代。所有 technical value 保留页面原文精度；页面用 `\(...\)` 转义的部分按原义还原。

### 2.1 Configuration（配置）

**Emilelu `mondrian.md` — `implemented`**

- Migrated from format 1 on 2026-10-28：`board.toml` 是 `schema_version = 2`，`soc_source = sm8475`，`os_profile = ipados-16.6.1-20G81`；SM8475 资源在 `UniXNU-sm8475-common`，板级 wiring 在 `dts/mondrian.dts`。
- Fork audit 2026-10-31：mzyxsl `daed6b5d44e3c62978cc0fce4e876ded2a57afc9` 带 provenance 导入。`board.toml` 使用精确 trust-cache 列表；`unixnu.lock` 与显式 SM8475 feed pin 一致。当前 payload reader 也接受完全相等的 scalar hash，所以列表属于 schema hardening，并不是已被证明的 former build blocker。
- Evidence：`source` — `board.toml`；`schema_version = 2` 经 arch、SM8475、20G81、device 四层解析，status 报告 3 个组件与 83 条有序补丁。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- 四层按顺序合并：`UniXNU profiles/arch/arm64` → `UniXNU-sm8475-common` 的 SM8475 `soc.toml` → `ipados-16.6.1-20G81` OS profile → 本板 `board.toml`。
- 源 pin 是 `feeds.toml` 内的显式 40 字符 commit：xnu `8796.141.3`（`1b191cb5`）、libplatform `1b2b22f2`、libdispatch `ca80d303`、AvailabilityVersions `f3b52ca7`、sm8475 `d0c90f1e`。
- OS profile 带 `[ipsw]`：iPad7,1、16.6.1、20G81、device class `j120ap`、chip `32785 = 0x8011`、board `12`，fetch `KernelCache/DeviceTree/StaticTrustCache/Cryptex1,SystemTrustCache`；带 `[kernel.prelink]`：32 roots、`slide 0` 供 auto-slide wrapper 使用，所以 `board.toml` 不重复这两张表。
- 其它配置：`board.toml schema_version = 2`，`[board] name mondrian, soc SM8475, soc_source sm8475, os_profile ipados-16.6.1-20G81, kit mondrian`，无 `example` flag；`[components] include` 为 `ArmDTPlatform, ArmCpu, XnuPrelink, PongUfs`；`[kernel]` 使用 `mondrian_defconfig` + arch/soc/os fragments，`patch_series = device:patches/xnu/series`，archives 为 `component:ArmDTPlatform/ArmCpu/PongUfs`，`driver_records = DEVELOPMENT_ARM64_PONG`；`[device_tree] source device:dts/mondrian.dts`，`include_dirs soc:dts`；`[userdata] first_lba 53342976, last_lba 61731583, lba_bytes 4096`，windows 为 `OS + Cryptex1,SystemOS`。
- `patches/xnu/series` 共 98 条按应用顺序：4 条是 `021x` display 补丁，13 条是 K60 专属（trust cache、panic reporting、compiler fixes），其余 81 条是共享的 Darwin 22 / Pong bring-up 补丁；目录中另外 22 个文件有意不列入，并记录为 switched off 或 version-bound。
- Procedure：clone UniXNU `k60` 分支及 submodules，把 `UniXNU-sm8475-common`、`UniXNU-mondrian`、`uefi-mondrian` 放在旁边；运行 `../UniXNU-mondrian/scripts/k60-macos-preflight.sh`、`./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian`、`./unixnu fetch -D ../UniXNU-mondrian`、`./unixnu status --json -D ../UniXNU-mondrian`、`./unixnu tree -D ../UniXNU-mondrian`；再在 core checkout 运行 `python3 scripts/porting-record.py check --device ../UniXNU-mondrian`，以及 `python3 ../UniXNU-mondrian/scripts/check-porting-paths.py`。
- Development findings：① 2026-10-28 从 format 1 迁到 format 2，输出目录变为 `out/mondrian/ipados-16.6.1-20G81/mondrian/`，所有 pin 移入 `feeds.toml`。② lock file 仍记录旧 sm8475 commit `70f20268`，而 `feeds.toml` pin 的是较新的 `d0c90f1e`（2026-10-28 15:19Z，“tag every CPU node with a Darwin cluster type”）；显式 format-2 commit 优先于 lock，所以把 lock 条目改成 feed 值，避免两个答案。③ `board.toml [payload] trust_cache_sha256` 曾是 bare string；payload 步骤按 list membership 测试，字符串会让每个 `--trust-cache` 都过不了 board allow-list；现改为 shipped bundle hash 的 one-element array。④ `docs/NEXT-STEPS.md` 曾把单 CPU first-boot 一行与 `cpus = 8` 的板子并列；现在注明 `cpus=1` 是 bring-up baseline、八核声明仍未测量。
- Current limits：本 workspace 无 core checkout、无网络，pins 通过 GitHub API 确认；`[ipsw]`/`[kernel.prelink]` 的解析来自 profile，不是 live status。Arch profile 的 `SoftwareAES` 未被本板选中；K60 通过 pong build scripts 链接 platform archives，而不是 format-2 archive recipes。
- Evidence：`source` — `board.toml`（schema_version 2 选择 4 个组件、mondrian defconfig、device-only patch series、12 GiB DRAM、`cpus = 8` payload window）；`feeds.toml`（五个源 pin）；`patches/xnu/series`（98 条，引用文件全部存在）。

**wohusaixing / XTOM0706 — `implemented`**

- 两页都只有同一条 finding：2026-10-28 从 format 1 迁移到 format 2，`board.toml` 为 `schema_version = 2`、`soc_source sm8475`、`os_profile ipados-16.6.1-20G81`；SM8475 资源在 `UniXNU-sm8475-common`，板级 wiring 在 `dts/mondrian.dts`。
- Evidence：各自仓库的 `board.toml`，文字与 Emilelu 相同：“status reports three components and 83 ordered patches”。

**差异与判断**

- mzyxsl 的配置信息最细（四层来源、五个 pin、98 条 series、userdata 几何）；Emilelu/wohusaixing/XTOM 只有 83 条 series 的生成摘要。
- `trust_cache_sha256` 是 schema list 而非 scalar，这是 mzyxsl 与 Emilelu 都提到的实际踩坑；但当前仓库后续按 B 决策把整个 trust-cache 路径去掉（`trust_cache_sha256 = []`），属于有意分歧，不是遗漏。

### 2.2 Firmware and boot（固件与启动）

**Emilelu `mondrian.md` — `device-verified`**

- 该页的 `### Development findings` 只有模板句“Collect the first firmware and boot observation…”，没有独立文字；真正的实现经验在 `### Evidence` 的 `device` 条目：
- `device`：Darwin 24 loader 每次都能启动本板：green bar 来自 `Entry.S`，之后 upstream probe 在 kernel entry 画 blue bar、在 MMU 打开前画 magenta bar。确认 `0x480` `boot_args` ABI、ADT handoff 和 framebuffer 在硬件上是 live 的。`k60_fontscale=4` 时曾出现可读 kernel panic，直到 CPU start order 修好；该 panic 已消失。
- Command：`scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc8.img`；Revision：`d2af811a6dc9c6225de586e1615ca3824e2edce4`。
- 关联文件：`docs/ROUTE-A-18-STATE.md`。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- Hardware and dependencies：Mu-Silicium platform tree `uefi-mondrian`，关键文件 `Resources/Configs/mondrian.toml`、`Platforms/Xiaomi/mondrianPkg/mondrian.dsc`、FD `Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd`。
- 固件必须内嵌 `UniXNU`、`UniXNUDxe`、`DarwinBoot`、`UniXNURamDiskDxe`，再加 `DiskIoDxe` 和 `FAT`，使 payload FAT volume 在读取 config 前就可被发现。
- Boot inputs 来自 OS profile：kernelcache hash `d260defc`、20G81 trust cache bundle（SHA-256 `344ae644`）、Data seed；`platform seed` 只在 board 通过 `--unique-chip-id` 时需要。Display、keypad、logger 的 vendor binaries 来自 `uefi-mondrian`，本仓库只在 `proprietary-files.txt` 列出。
- Configuration：`[firmware] config mondrian, dsc Platforms/Xiaomi/mondrianPkg/mondrian.dsc, fd Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd`，patches `AsmMacroLib.patch`、`Boot-Manager.patch`，packages 包括 `{uefi}`、`{tree}/package`、`{tree}/drivers/DarwinBoot22`、`{edk2}`、`Platforms/Xiaomi`、`Common/Mu`、`Silicon/Qualcomm`、`Silicon/Silicium`、`Silicium-ACPI`、`Binaries/pong`。
- Defines：`DEVICE_MODEL 0`、`ENABLE_SECUREBOOT 0`、`MEMORY_PROTECTION TRUE`、`SHIP_MODE FALSE`、`BUILDID_STRING UniXNU-Mondrian`。
- DarwinBoot22 contract：`boot_args` `0x2e0` 字节，608 字节 command line 在 `0x6c`，`Video[6]` 在 `0x28`；一个 256 MiB `EfiConventionalMemory` window（2 MiB 对齐）加 kernel base；ADT 上限 16 MiB；trust cache sidecar 1..128 个模块，SHA-1 entries 严格升序。
- Procedure：`./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian`，或 Pong-layout checkout 的 `scripts/build-firmware.sh`；`python3 scripts/verify-firmware.py --output-dir <build>` 检查 FV header、checksum、UniXNU `9b665204`、UniXNUDxe `29b950cf`、DarwinBoot `1b64af87`、PongBootMemoryDxe `7b27b767` 四个 FFS 文件与 ARM64 PE machine `0xaa64`；`scripts/build-darwinboot22-macos.py` 用 Darwin 22 headers 编译 loader，不改已保存 FD。
- Development findings：① loader 只在 RAM 安装 `UniXNULoader` protocol，unload 时恢复原 interface；不写 firmware variable/partition，所以 `fastboot boot` bring-up 是只读的。② DarwinBoot 必须在 EL1：`DarwinCurrentEl() != 4` 返回 `EFI_UNSUPPORTED` 并保持 firmware alive；从 EL2 启动的 payload 永远到不了 XNU。③ green bar 是 trampoline，不是 kernel：它把 framebuffer 顶部 1/16 画成 `0xFF00FF00`，清 `SCTLR_EL1 M/C/I`，再跳 kernel entry；`README.md:19-20` 因此记录 payload entry as unconfirmed，这也是该域不是 `device-verified` 的原因。④ one-window layout：args 在 kernel image 后 16 KiB 对齐，ADT 再后一页，page-aligned ramdisk，trust cache，然后 copied trampoline page；`Used` 必须小于 `WindowSize - 2 MiB`，否则 boot 被拒。⑤ `prebuilt/20G81-trustcache.bundle` 是 61,764 字节、两个模块（2510 和 61 entries，version word 2），满足 loader validator，SHA-256 等于 board allow-list。⑥ host tests 真实但窄：`Test/Validation.c` 驱动 24 个 rejected loader requests（6 kernel paths、6 memory windows、4 ramdisk layouts、8 trust-cache layouts）加 GOP format check；`Test/window-size.c` 断言 5 accepted/6 rejected；`scripts/test-window-qemu.py` 断言 post-ExitBootServices pixel `12d4a6`，`df2020`/`aa33dd` 为 failure controls；这些在最后 Mac round 都没跑。
- Current limits：设备观察止于 green bar；无 serial、ramoops 或 framebuffer line 证明 XNU 在 trampoline 后执行；board 的 boot image 还没打包；USB log export 只是 `docs/USB-LOGGING-PLAN.zh.md` 设计，树里没有 USB logger 或 host reader。
- Evidence：`source` — `DarwinBoot.c`（Mach-O 校验、ADT/trust-cache/ramdisk sidecar 经 zero-filled `/chosen` placeholders、ExitBootServices 重试三次后经 trampoline 分支）；`scripts/test-window-qemu.py`（`12d4a6` pass，`df2020`/`aa33dd` controls）；`prebuilt/20G81-trustcache.bundle`（61,764 B、2510+61 entries、SHA-256 `344ae6445dfcb791ac838dbfec5c4d39a871cf58f91d8bee84ba57204f6727e6`）。

**wohusaixing / XTOM0706 — `planned`**

- 两页均只有模板句；无 finding、无组件、无 Evidence。

**差异与判断**

- Emilelu 是唯一有真机 Firmware evidence 的页，且明确是 Darwin 24 `0x480` ABI；mzyxsl 是唯一把 DarwinBoot22 的 `0x2e0`/608 字节合约、FFS GUID、trust cache bundle 写全的页。
- 两者不是同一 ABI：`0x480` vs `0x2e0`。当前仓库 README 写“由 Darwin 22（0x2e0/608）修正为 Darwin 24（0x480/1024）”，而 `board.toml` 仍写 `os_profile ipados-16.6.1-20G81`；构建前必须确认 loader/profile 配对，不能直接把 mzyxsl 的 Darwin 22 合约塞进 Darwin 24 链。

### 2.3 CPU and interrupts（CPU 与中断）

**Emilelu `mondrian.md` — `implemented`**

- SM8475 的硬件 MPIDR 是扁平的 `0x000..0x700`，`Aff1 = core index`。Vendor device tree 和 Android tree 都是这个值；本 firmware 拒绝任何不在该表内的 `CPU_ON` target。Android sysfs 看到的 `4/3/1 A510/A710/X2` 分组是 L2/L3 cache topology，不是 MPIDR affinity；kernel 的 cluster-type property（全 `P`）才把八核压成一个 topology cluster。
- 启动 core 通过 `MPIDR & 0xFFFF` 与 ADT 的 per-CPU reg 匹配到自己的 `cpu_data`；同一个值也是 PSCI target，所以 ADT 必须携带真实 MPIDR。board dts 不得覆盖 SoC dtsi 的 cpu nodes：ADT generator 需要它们的 `compatible` 和 `unixnu,cluster-type`。
- Evidence `device`：Android device tree 八个硬件 MPIDR 扁平 `0x000..0x700`，八核都通过 PSCI 启动；Android sysfs 的 `4/3/1` 是 cache grouping 而非 MPIDR。我们的 board dts 曾把 cpu nodes 覆盖成 packed `0x0-0x3/0x100-0x102/0x200`，同时破坏 firmware target table 和 reset vector 的 match；该 override 已移除，恢复继承 SoC dtsi。Command：`adb shell 'cat /sys/devices/system/cpu/cpu*/topology/physical_package_id; cat /proc/device-tree/cpus/cpu@*/reg'`；Revision `e636e445b621bed4fac0069f3604b87061350a8d`。
- Evidence `device`：Darwin 22 的 `ArmCpu::start()` 自己调用 `initCPU()`，其尾部 `signalCPU(this)` 在 `cpu_machine_init()` 设置 `StartedState` 前给 boot CPU 发 self IPI，于是第一个 IPI 触发 `cpu_common.c:586` 断言，`cpu_flags 0x2000` 对 expected `0x3000`。切到 Darwin 24 first-boot path（`pong_cpu_first_boot`、`pong_cpu_first_boot_wait`、`ml_cpu_init_completed`）后，kernel 在 `processor_boot()` 期间调用 `initCPU()`。现在板子画出三根 probe bar，不再触发断言，并通过 probe 的 timed PSCI reset 自行回到 Android。Command：`scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc8.img`；Revision `d2af811a6dc9c6225de586e1615ca3824e2edce4`。
- Evidence `device`：flat targets 下每个 `CPU_ON` 都被 granted、`AFFINITY_INFO` 回答 `on`，但没有 core join；arrival flag 在 reset vector 显示 MPIDR `0x81000200`，core 随后卡在 `start.s` 的 `Lskip_cpu_reset_handler`，因为它按真实 MPIDR 匹配到的 cpu data 还没有 reset handler。flat targets 是 firmware 的表，配对才是 defect。Command：`scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc11.img`；Revision `e636e445b621bed4fac0069f3604b87061350a8d`；对应 patch `patches/xnu-ipados18/0247-k60-psci-flat-targets.patch`。
- Current limits：八核都能 register，boot CPU 收到第一个 IPI，但 hardware 上还没有任何 secondary 被看到越过自己的 entry checkpoint。Next action：确认每个 secondary 都运行自己的 entry checkpoint 并在 unit 上服务 timer。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- Hardware：八个 SM8475 CPU，MPIDR affinity `0x000..0x700`，声明在 SoC `dts/sm8475.dtsi`，加上 PSCI conduit 和 GICv3 distributor/redistributor windows。
- 真机测量：GIC distributor `0x17100000`、redistributor `0x17180000`；driver 从 `/arm-io ranges` 和 `/arm-io/intc reg` 读真实 base，而不是硬编码。Redistributor stride 只接受 `0x20000`、`0x30000`、`0x40000`（fallback `TYPER.VLPIS`），与本 SoC 的 `0x17180000` window 匹配。
- Config：`CONFIG_XNU_ARMCPU=y`、`CONFIG_XNU_ARM_DT_PLATFORM=y`、`CONFIG_XNU_NATIVE_ARCH_TIMER=y`、`CONFIG_XNU_ARMVIRT_PLATFORM=n`；`[payload] cpus = 8` 限制 ADT CPU list；AppleARMCPU multi-CPU validation 由 kext patch 在 `_validateConfiguration` 绕过。Kernel side：`MAX_CPUS 8`、`MAX_CPU_CLUSTERS 2`、`GENERIC_PSCI_SMP`、`ARM_ARCH_TIMER` 来自 psci-smp patch 的 `board_config`。
- Procedure：`python3 scripts/build-pong-armcpu-macos.py` 用 Darwin 22 headers 编译 GICv3/PSCI provider；archive 通过 `[kernel] archives component:ArmCpu` 链接；prelink、boot，读 XNU serial 的 per-CPU registration 和 PSCI start 结果。
- Findings：① ArmCpu 先注册每个 `device_type = cpu` nub，若 `armcpu_registered != ml_get_cpu_count()` 就 panic，所以 DTS 隐藏一个 CPU 会大声失败而不是少核启动。② MPIDR matching 用 aff0-aff2 加 aff3 对 `GICR_TYPER[63:32]`；boot affinity 是 `mpidr & 0xff00ffffff`，SGI 通过 `ICC_SGI1R_EL1` 用四个 affinity field 构造。③ 只 enable `INTID 0`（SGI0 IPI）和 `INTID 27`（CNTV PPI）；`32..1019` 按 priority `0xa0` 分发给 SPI owners，树内唯一 SPI client 是 Adreno `332`。④ PSCI 用 `0xC4000003 CPU_ON`、`0x84000002 CPU_OFF`，start/stop timeout 5 s/3 s；调用前把 `__TEXT`、`__TEXT_EXEC`、`__DATA`、`__DATA_CONST`、`__BOOTDATA` 和每个 `cpu_data_t` clean 到 point of coherency。⑤ UFS controller 在 DTS 声明 SPI 265 但从不 attach，所以 storage 是 polled 而非 interrupt-driven；这是有意的 bring-up 选择，不是缺 GIC 功能。⑥ `docs/NEXT-STEPS.md` 记录 first bring-up 用 `cpus=1` 并警告不要 `cpus=8`，而 `board.toml` 自 2026-10-29 测量后设为 `cpus = 8`；该 note 现在把 single-CPU 行标为 bring-up baseline，并指向本域缺失的 eight-CPU log，board 值保持不变。
- Current limits：只从 source 实现；八核启动未有硬件证明，因为没有保存 run log。`pong_adt_contract` audit 只接受一个 running CPU，所以 eight-CPU ADT 只能在该 audit 之外生成；不兼容仍未解决。
- Evidence：`source` — `drivers/ArmCpu/ArmCpu.cpp`（GICv3 D/R 从 DT ranges、MPIDR→GICR matching、INTID 0/27、SPI 四 owners、八核注册与 mismatch panic）；`patches/xnu/zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch`（SMC/HVC PSCI、secondary entry `SCTLR_EL1 0x30D00800`、自己的 VBAR、每个 `cpu_data_t` cache maintenance、64-byte fault record）。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**差异与判断**

- Emilelu 的真机 CPU 结论是“扁平 MPIDR 正确，但 secondary 尚未过 entry checkpoint”；mzyxsl 的源码补全了 GIC/PSCI 细节，但同样承认 eight-CPU start 未证明，且 `pong_adt_contract` 只允许一个 CPU。
- 当前仓库 active `patches/xnu/series` 只用 `pong-psci-smp.patch`，没有把 `patches/xnu-ipados18/0247`、`0248`、`0250` 系列带进来；如果要在同一 firmware 上启动 secondary，必须移植 `0247` 的 flat-target 翻译、`0248` 的 arrival probes 或 `0250` 的 target scan（后续 commit `3f0e785` 是这条线的最终修正）。

### 2.4 Memory and DMA（内存与 DMA）

**Emilelu `mondrian.md` — `implemented`**

- Live serial `6033dbec` 的 `/memory/reg` 和 rooted `/proc/iomem` 给出六段 RAM banks，并在 `4..32 GiB` 之间有 28 GiB hole。安装的 12 GiB 不能作为一个 XNU window：最长的连续未保留 run 是 `8.65 GiB`（`0x840000000..0xa69b78000`）。
- 4 GiB window 启动 XNU，报告 `mem=actual=managed=4096 MiB`。8 GiB window（arena 等于整个 8 GiB）被拒：DXE 占用 arena 的一部分，DarwinBoot 返回 UniXNU menu。
- 8.625 GiB arena `[0x840000000,0xa68000000)` 配 7 GiB window 被接受：loader 打印 `window 0x1c0000000 bytes at pa 0x8400200000` 和 `HANDOFF EXIT RETURN 0`。`DarwinWindowSizeValid` 把 window 限制在 8 GiB，所以 12 GiB 根本不可达。
- 4 GiB boot 的 screen trace：`suggestd` 以 status `163`、signal `0`、`ns=0`、`code=0x0` 退出，是正常 exit status，不是 jetsam 或 sandbox denial；`disk5s` APFS transactions 持续完成（`xid 2512, 140/140 finished`），Data volume 没有卡住。
- Current limits：4 GiB window 是已证明配置；7 GiB 被 loader 接受但 XNU 没有启动；12 GiB 单 window 物理不可能。reference project 的 display/CA prerequisites 已在本 kernel 中；开放的墙是 userland contract/container handling，表现为 `ns=2 SIGABRT/SIGTRAP`。
- Evidence `host`：8.625 GiB arena + 7 GiB window；strict v4 round trip PASS；image SHA-256 `8ea52daf4b3e926d4840e13a73fa00c9cadf9b3f1e97e1ececfdaa446e1afc34`。Command：`python3 repair-high-window.py; build-uefi-8g.sh; build-kernel-summary.sh; package-textonly.py`；Revision `48abe35d0a0a57f5fea9f9ba1e570800021ae6b1`。
- Evidence `device`：loader 接受 `window 0x1c0000000 bytes at pa 0x8400200000` 与 `HANDOFF EXIT RETURN 0`；XNU console 输出尚未观察到。Command：`fastboot boot /mnt/e/k60-work/candidates/7g/boot-ios16-7g-textonly.img`；Revision `e06211de59325bbd086c312324bdbf40e21d1045`。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- Hardware：单段连续 DRAM：`dts/mondrian.dts` 的 `memory@80000000 reg = <0x0 0x80000000 0x3 0x0>`，12 GiB，匹配 `[payload] dram_size 0x300000000`。
- ADT generator 要求恰好一个 enabled memory node、恰好一个 range；issue #1 报告的五段 16 GiB 布局无法描述，需要 README.md 的 narrowed bank0 form。
- DMA width/contiguity：UFS engine 在 `CAP bit 24` clear 时需要 one physically contiguous `139 KiB` buffer below 4 GiB；window parser 接受 `0x10000000..0x200000000`，2 MiB steps。
- Config：`[payload] dram_size 0x300000000, cpus 8, timeout 5`；DTS `/memory` 是 ADT generator 检查 `dram_size` 的唯一来源。`CONFIG_XNU_NATIVE_RAM_BLOCK=y`、`CONFIG_XNU_NATIVE_PAN=y`、`CONFIG_XNU_DT_PANIC_REGION=y`、`CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y`、`CONFIG_XNU_PONG_VOLATILE_PANIC_LOG=y`。Panic/ramoops：`darwinboot-memory-size` 经 `[payload.adt] owned_memory_size` 请求；loaded window 上限 `0x200000000` 且必须 2 MiB aligned。
- Procedure：`dtc -I dts -O dtb -i ../UniXNU-sm8475-common/dts dts/mondrian.dts`；`scripts/build-window-probe.py` / `build-window-probe-local.py` 编译 own MMU-off probe kernel；`scripts/build-pong-ram-block-macos.py` 编译 volatile RAM block provider；`scripts/test-window-qemu.py` 在 ExitBootServices 后读 framebuffer 并对比 pass/failure colours。
- Findings：① handoff window 是第一 boot constraint，不是 driver detail：`docs/NEXT-STEPS.md` 记录 working p0prime `dram-base 0xB9200000`、`dram-size 0x26C0000`、恰好 `145502` free 4 KiB pages（`36905` at 16 KiB），更大 window 在 XPU wall `0xE9F00000` 静默死亡。② `docs/NEXT-STEPS.md` 曾把该 window 记成 `0x26C0000 (620 MiB)`；page count 证明 hex 值错误：145502 free 4 KiB pages 约 568 MiB after kernel image，所以文档值改为 `0x26C00000` 并在原处注明更正。③ `NativeRamBlock` 读 `/chosen/memory-map` 的 `RAMDisk` 或 `PackedRAMDisk`（互斥、4 KiB 对齐、最多 `0x80000000` bytes），并在 2 GiB 以上从 sparse pages 切到 `SeedDisk`，这才让 32 GiB Data window 可容忍。④ persistence overlay（`'SHNGDATA' v1`、64-byte header 带 generation 和 CRC32）只调用 weak-imported `native_ufs_store_*` 符号，而仓库没有文件定义这些符号，所以 persistence 按 committed 状态无法链接。⑤ `probes/window-probe.c` 是独立 diagnostic kernel，不是 XNU：断言 boot-args magic `0x00020002`、`CurrentEL 4`、SCTLR bits，要求 window 恰好 `0x10000000`，在 unused window 的每个 4 KiB page 写两个 pattern，异常路径打印 ESR/FAR/ELR。
- Current limits：realised window、SMMU geometry、DMA addresses 未在 unit 上测量；12 GiB / 620 MiB 对来自 maintainer notes，不是 captured boot log。16 GiB variant 需要不同 `/memory` form 和匹配 `dram_size`；ADT generator 拒绝 multi-range，所以该 unit 在选定 narrowed form 前无法 boot。
- Evidence：`source` — `dts/mondrian.dts`（单 12 GiB range + UFS/GCC/SMMU 属性）；`probes/window-probe.c`；`drivers/NativeRamBlock/NativeRamBlock.cpp`（memory-map discovery、4 KiB alignment、sparse vs SeedDisk、weak persistence overlay）。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**差异与判断**

- 这是四个页面里最危险的冲突：mzyxsl 的 `12 GiB` 单段 `/memory` 是格式假设，Emilelu 的真机测量明确说 installed 12 GiB 由六段构成、最长连续只有 8.65 GiB、12 GiB 不能作为一个 XNU window。任何 K60 12 GiB 机器都必须按 Emilelu 的实测表选 arena，不能照 mzyxsl 的 `memory@80000000` 12 GiB 段。
- mzyxsl 的 ADT “exactly one memory node / one range” 限制是真实的工程约束；实现时把“一个 arena”选为 `/memory` 的单一 range，而不是把整机六段塞进去。

### 2.5 Storage and root（存储与 root）

**Emilelu `mondrian.md` — `planned`**

- `### Development findings` 首行是模板；实际 finding：2026-10-31 用户 console 报 APFS Data ENOSPC：`free_blocks` 约 `1208`，低于 `threshold_blocks 1310`，影响 `launchd`、`usermanagerd`、`logd_helper`。最新保存安装是 256 MiB APFS container 位于 258 MiB Data GPT window、unixnu offset `7420 MiB`，留下约 `24.502 GiB` 在 windows 之外。历史 images 有 checksum/CRC 校验但不能证明当前 live occupancy；root recovery 的 capture 仍 pending。Read-only inspector 校验保存的 256/512 MiB images，并能在 second-read hash comparison、可选 local directory-allocation summary 下备份当前 Data。未做任何 device storage writes 或 resize。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- Hardware：UFS host `0x01d84000`（`0x3000`）、GCC UFS page `0x00187000`、SMMU `0x15000000`（`0x100000`），stream ID `0xe0`，DTS 声明 78 context banks、120 stream-match groups。
- SMMUv2 register facts：reference device `IDR1.NUMCB 75` 会 cap 声明的 78；`IDR2` 必须 advertise A64；banks 和 pages 必须 fit `0x100000` window；masked stream IDs 被拒。
- Root volumes 来自 OS profile disks：OS `096-57366-083.disk.cdr`、SystemOS `096-56782-083.dmg`，包在 SHNGROOT v1 manifest 中，window records 128 字节。
- Data volume 是 committed seed `seed/k60-data-seed.dbr`：`33,554,432` bytes raw APFS，volume 名 `OwnerData`，SHA-256 `5fd2f3566e989d11cde74289151888392615a4771e5b616ff5e98ca3b24ffc03`，由 `scripts/k60-make-data-seed.py` 在 macOS 重生成。
- Dual-system 计划需要 unlocked TWRP、root ADB、decryptable `/data`、F2FS online shrink support，见 `docs/DUAL-SYSTEM.md`。
- Config：`[userdata] first_lba 53342976, last_lba 61731583, lba_bytes 4096`，windows `OS + Cryptex1,SystemOS`：`8,388,608` blocks、32 GiB starting at byte `218,492,829,696`。`CONFIG_XNU_NATIVE_UFS=y`、`CONFIG_XNU_OWNER_CACHE_MOUNT=y`、`CONFIG_XNU_OWNER_CACHE_STARTUP=y`、`CONFIG_XNU_OWNER_DATA_MOUNT=y`、`CONFIG_XNU_OWNER_UNION_SYSTEMOS=y`、`CONFIG_XNU_OWNER_DATA_UFS=n`。
- `CONFIG_XNU_OWNER_DATA_VOLUME_UUID 6DCCF70A-6FD6-403E-ACED-95313CD7CBB8` 是 seed 里的 `OwnerData` volume（Pong 常量 `576A2203-F35D-45DA-80B0-11EF01DDA8C9` 永远匹配不上）；`CONFIG_XNU_OWNER_CACHE_VOLUME_UUID 15B507FA-21B7-4EE5-B55D-0F3445DE0752`；`[payload.adt] root_match_volume_uuid C5DAF029-2070-4F68-B3CC-1D1320344CF0`。
- Writes 只有 boot arg `pong_ufs_readwrite=1` 才允许；SCSI allow-list：`TUR`、`START STOP UNIT` on LUN `0xd0`、`READ CAPACITY(10)`、`READ(10)`、`WRITE(10)` with FUA、`SYNCHRONIZE CACHE(10)`。
- Procedure：`./unixnu build userdata --dry-run` 再 `./unixnu build userdata` 生成 SHNGROOT image；或 `scripts/build-userdata.py --component-dir out/ipsw/20G81 --os-disk <cdr> --systemos-disk <dmg>`；`scripts/derive-ios16-storage-bindings.py --tree <tree>` 从 genuine kernelcache 推导 190 个 `IOBlockStorageDevice` slots；`scripts/audit-ios16-storage-abi.py` 检查 176 bindings 和 `0x90` class size；`scripts/k60-make-data-seed.py --profile <profile> --output k60-data-seed.dbr` 在 macOS 构建 32 MiB APFS Data seed；`scripts/install-pong-ufs-data.py` 通过 ADB 在 recovery 安装 Data window；独立 partition 见 `docs/DUAL-SYSTEM.md` 的 `partition.py inspect` → f2fs-shrink helper → apply → verify。
- Findings：① transport 接管已初始化 controller：要求 `HCE bit 0`、`HCS low nibble 0xf`、zero doorbells、clear fatal interrupt mask，然后 polled command ring，无 resubmission，timeout 时 poisoned buffer。② LUN 0 必须通过 `READ CAPACITY(10)` 报恰好 4096-byte blocks；其它 geometry 被拒为 `unsupported LUN geometry`，这是换 UFS part 时第一件要检查的事。③ 每个 DT property 在第一次 MMIO read 前与 compiled constants 做 equality check；`dts/mondrian.dts` 与 `drivers/NativeUfs` 不符会在 probe 以 specific message 失败，而不是 corrupt controller。④ Data mount 必须命名 board 自己的 seed volume；继承 Pong 常量时 lookup 永远不 match，`/private/var` 不挂载，`mkbinit` 写不了 `/private/var/keybags/systembag.kb`。Committed seed 的 volume superblock 在 `0xa2020`：UUID 在 `+0xd0`、名字 `OwnerData` 在 `+0x2a0`，checkpoint copies `0x15c020`、`0x15f020` 都保留。⑤ 32 MiB seed 远低于 `NativeRamBlock` 的 2 GiB switch，provider 保持 sparse pages 而不是 `SeedDisk`，所以 committed image 可以很小且仍有 writable `/private/var`。⑥ Data persistence 有意关闭：`CONFIG_XNU_OWNER_DATA_UFS=n` 把 Data window 编译掉，`patches/xnu/...-pong-ufs-data.patch` 不在 `patches/xnu/series`，in-tree Data branch 从不 build。⑦ `install-pong-ufs-data.py` 仍硬编码 Pong geometry（`sda13`、`0x413248..0x75a40ea`、454 GiB），拒绝其它值，不能按原样安装 K60 自己的 unixnu partition。⑧ `docs/DUAL-SYSTEM.md` 没有固定 size：仓库唯一 concrete number 是 32 GiB `[userdata]` window，partition plan 必须 match。
- Current limits：本板没有 device log；read path 实现但未证明；boot RAM seed 是唯一 writable Data；persistent UFS Data window 根本没编译。32 GiB window 未对 real GPT 验证；scripts 与 record 对 partition 描述不一致。Dual-system partition 未创建，第三方 TWRP 的 F2FS online shrink/decryption 未检查。
- Evidence：`source` — `NativeUfs.cpp`（DT equality checks、controller power/bus verification、SMMU ownership limits）；`RootLayout.h`（GPT CRC32、UTF-16LE unixnu name、SHNGROOT records、0..7 status codes）；`seed/k60-data-seed.dbr`（NXSB at `0x20`、volume superblock at `0xa2020`、UUID at `+0xd0`、volname `OwnerData` at `+0x2a0`、SHA-256 `5fd2f356...`）；`docs/DUAL-SYSTEM.md`（F2FS online shrink、unixnu at tail of userdata、TWRP prerequisites、inspect/plan/apply/verify）。

**wohusaixing / XTOM0706 — `planned`**

- wohusaixing 无组件、无 finding；XTOM0706 仅标 `Components: PongUfs`，状态仍 `planned`，无 finding、无 Evidence。

**差异与判断**

- mzyxsl 是唯一把 UFS/root 做完整的页，但它明确把 Data persistence 关掉、只保留 32 MiB RAM seed，且 `install-pong-ufs-data.py` 不能装 K60 自己的分区。
- Emilelu 页状态是 `planned`，但它的真机 ENOSPC 数据给出了真实 Data 几何：`256 MiB APFS / 258 MiB GPT / offset 7420 MiB`。当前仓库后来把这个窗口扩到 2 GiB 并改 UUID `1BCD69FF-...`，是比两页都新的实际路线。

### 2.6 Display（显示）

**Emilelu `mondrian.md` — `planned`**

- `### Development findings` 首行模板；实际 finding：Board-level chosen `display-scale=3`，adapted from XTOM0706 `9d1a14f83d1050a042313f30dc9d5b7e80d31f7a`。解析 generated ADTs before/after，除 `random-seed` 外属性完全一致（当前 20G81 profile）。其 additional sweet display node 未复制，因为 `MiniIOMobileFramebuffer` 运行时已经发布 `disp0` display-subsystem child。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- Hardware：panel `m11a_42_02_0a`，1440×3200 native canvas，DSC video mode，stride 取 `vinfo.v_rowbytes`，refresh 通过 panel driver 报告。Firmware 必须发布 `EFI_GRAPHICS_OUTPUT_PROTOCOL` surface（本 port 是 ABL splash framebuffer + `SimpleFbDxe`）；DarwinBoot 只接受 `PixelBlueGreenRedReserved8BitPerColor`。Userland presentation 需要 20G81 QuartzCore cache layout，`ui_compat.c` 按地址 pin，slide 为 `base - 0x180000000`。
- Config：`K60_PANEL_WIDTH 1440`、`K60_PANEL_HEIGHT 3200`，`k60_panel` tunable 默认 1（0210）；只有 `vinfo` 恰好 1440×3200 时 canvas 强制 panel，`fbwidth/fbheight/fbscale` 被拒。`kFBDisplayID 1`（0 表示无 display）和 Timing/Color ids 1（0213）；display services 在 `pong_software_ui=0` 时仍启动（0211）。`XNU_K60_ACCEL_STUB=1`（在 `PONG && (DEVELOPMENT || DEBUG) && !SECURE_KERNEL` 下默认）发布空 `IOAcceleratorES` stub，`IOAcceleratorStub=true` 且无 `MetalPluginName`，`accel_stub=0` 运行时关闭（0212）。
- Procedure：0210..0213 是 series entries 0209..0213，按该顺序应用；改动后 rebuild kernel 和 payload；boot 后读 XNU console 的 `K60 DISPLAY: first frame presented (swap n, WxH canvas ...)`，并检查发布的 `K60Display` dictionary 的 `Stride` 和 `RefreshHz`。
- Findings：① display stack 从 firmware surface 起步：0210 发布 `K60Display` dictionary（`PanelWidth, PanelHeight, CanvasWidth, CanvasHeight, Stride, RefreshHz, Native`），拒绝缩放非 native canvas，所以第一帧永远不是拉伸图。② empty accelerator 让 clients 在没有 GPU 时存活：0212 最多回答 16 个 scalar outputs 加 structure output，记录前 24 个 selectors，advertise `IOAcceleratorStub`，让 SpringBoard 在 GPU port 前先呈现 software frame。③ console 有两个 first UI frame 修复：touch-console patch 在 `kPEGraphicsMode` 后释放 graphics console，让 `vcputc` 不再覆盖 frame；console-sink-dedup patch 去掉 duplicate sinks。④ userland 强制 framebuffer format `'BGRA'`（`0x42475241`），缓存 null renderer，保持 display readiness；四个 QuartzCore hooks 在 `0x1d586e000/0x18826a418`、`0x1d586c7c0/0x1884aa47c`、`0x1d586c7c8/0x1882787f4`、`0x1d586dfd8/0x1882df668`。⑤ 1080×2412 main screen 选择 `PongStatusBarVisualProvider1080`（`Split1080` subclass），所以 status bar geometry 跟随硬件 screen，而不是 1440×3200 panel canvas。
- Current limits：repository 没有 presented first frame 的 device log；该域 source only。Backlight control 未实现；panel driver 只提供 initial brightness。GPU-backed presentation 依赖 GPU 域和 accelerator stub replacement。
- Evidence：`source` — `0210-k60-display-native-canvas.patch`（native 1440×3200 canvas、拒绝 scaling fields、K60Display dictionary）；`0213-k60-display-first-frame.patch`（display id 1、timing/colour ids 1、first-frame-presented log line）；`0212-k60-empty-accelerator.patch`（16 scalar + structure outputs、24 selectors、`IOAcceleratorStub=true`）。

**wohusaixing / XTOM0706 — `planned`**

- 两页均无 display finding；XTOM0706 的贡献只在 Emilelu 页被引用：`display-scale=3` 来自其 commit `9d1a14f8...`。

**差异与判断**

- mzyxsl 是唯一显示实现页；Emilelu 只采用了 XTOM 的 `display-scale=3`，本身没有显示栈。XTOM 页自身 status 是 `planned`，不要误以为 XTOM 实现了 display。
- mzyxsl 的显示实现有一个值得注意的细节：panel 是 1440×3200，但 status bar 逻辑按 1080×2412 main screen 选择 `PongStatusBarVisualProvider1080`；这是从 Pong 继承的 userland 行为，不是 panel 几何。

### 2.7 Input（输入）

**Emilelu `mondrian.md` — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。该页没有触摸或按键实现记录。

**mzyxsl `mondrian-mzyxsl.md` — `planned`**

- Hardware：Goodix `Berlin-D` touch controller 位于 GENI/QUP0 SE4 `0x990000`，TLMM `0xf000000`、GCC `0x100000`、RSC `0x17a20000`、cmd-db `0x80860000`；pins `16/17/18/19` 为 MISO/MOSI/CLK/CS，`21` 为 INT，`20` 为 RESET。
- Panel 在 touch 坐标中是 1080×2412，所以 driver 把 x/y 按 `max-x 1080`、`max-y 2412` 缩放到 `0..65535`。
- 物理按键来自 SPMI PMIC arbiter：`0xc400000` cnfg `0xc42d000`、observer `0xc440000`、EE 0，PON ppid `0x013`、GPIO6 ppid `0x18d`。
- XNU-side code 只有 boot arg `pong_touch=1` 存在且 DT node 精确匹配 compiled resources 时才运行。
- Config：`pong_touch=1` 启用 driver；`touch_flip 1` 左右镜像、`2` 上下镜像，用于 panel orientation。Driver 发布 `/dev/pong-touch`（char、`0444`、`root:wheel`、512-entry ring），结构 `struct pong_touch { u64 time; u32 type, finger, x, y }`；`/dev/pong-buttons` 在 minor 1。`userland/touch.c` 发布 virtual HID services：digitizer page `0x0d` usage `0x04`，consumer page `0x0c` usage `0x01`，key usages `0x30` power、`0xe9` volume up、`0xea` volume down。
- Procedure：把三个 patch 加进 `patches/xnu/series` 的 intended positions，重建 kernel、重打 payload、带 `pong_touch=1` boot；读 XNU console 的 Berlin-D probe line 和 first finger report；从 userspace bridge 检查 `/dev/pong-touch`。
- Findings：① driver 作为 source 完整但未 build：`pong-touch-console.patch`、`pong-physical-keys.patch`、`pong-goodix-resume.patch` 不在 `patches/xnu/series`，所以文档描述的 kernel 不包含它；因此该域保持 `planned`，而 firmware keypad path 可用。② resume patch 存在是因为 Android 或 recovery 可能把 controller 留在 sleep 或 gesture mode：它 reset、re-probe、publish input 前清掉一个 report byte。③ GENI engine 4 MHz、mode 0、cs0、8-bit MSB first、200 ms deadline、polled FIFO；每个 clock 和 power vote 都是 direct register write（GCC vote `0x62008` bits `6,7,8,9,14`；RPMh `ldoc12 1800 mV` 然后 `ldoc3 2700 mV`）。④ 同一个 touch patch 带有树内唯一真正的 RPMh regulator writer；enable touch 同时会给 panel 和 controller rails 第一批 working regulator votes。⑤ firmware keypad（`K60KeypadDeviceLib` over SPMI PON/GPIO）已经能在 UniXNU menu 使用，所以 menu navigation 已验证而 XNU input 未验证。
- Current limits：当前 series 没有编译本域任何东西，所以没有 build/device result；没有 captured report 证明 Goodix controller 在本 unit 上应答。
- Evidence：`source` — `zzzz...-pong-touch-console.patch`（Goodix Berlin-D driver、GENI SPI、TLMM pin muxing、RPMh rail votes、report parser、/dev/pong-touch ring）；`zzzz...-pong-physical-keys.patch`（SPMI PMIC arbiter PON/GPIO6 16 ms poll、/dev/pong-buttons）。

**wohusaixing / XTOM0706 — `planned`**

- 两页均只有模板句；无 finding、无组件、无 Evidence。

**差异与判断**

- mzyxsl 是唯一有 input 源码的作者，但自己的 status 是 `planned`，因为它没有把三个 patch 放进 series。
- 当前仓库后来把 `pong-touch-console.patch`、`pong-goodix-resume.patch`、`pong-physical-keys.patch` 加到 `patches/xnu/series:194-196`，但 `board.toml`/`dts/mondrian.dts` 仍没有 touch 节点，也没有 `pong_touch=1`；结果仍是“驱动已编译、ADT 无属性、无法 probe”。K60 的实测参数与 ADT skeleton 见 `docs/plans/K60-TOUCH-PARAMS.md`：`spi-base 0x00990000`、`tlmm-base 0x0f000000`、`gcc-base 0x00100000`、`rsc-base 0x17a20000`、`cmd-db-base 0x80860000`、`gpio-offset 0x00100000`、`pins <16 17 18 19 21 20>`、`max-x 14400`、`max-y 32000`（单位语义未核实）。

### 2.8 GPU

**Emilelu `mondrian.md` — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**mzyxsl `mondrian-mzyxsl.md` — `implemented`**

- Hardware：Adreno 730 v3（chip id `0x07030002`，Mesa FD725 / A7XX Gen1），GMEM 2 MiB，`HighestBankBit 16`，64×32 tile。
- Windows：GPU core `0x03d00000`、GMU `0x03d68000`、RSCC `0x03d50000`、cx_misc `0x0b290000`、PDC `0x03d9e000`、GPUCC `0x03d90000`、GPU SMMU `0x03da0000`、AO `0x03d40000`；GCC `0x100000`、RSC `0x17a20000`。
- Firmware blobs 不存本仓：`gmu_gen70000.bin`、`a730_sqe.fw`、`a730_zap.mdt/.b01/.b02` 在 build 时提供；ZAP 使用 PAS id `13` at `0x8b91a000`。SPI `332`（GPU）、`336`（HFI）、`337`（GMU）是 CP 目前唯一 attach 的中断。
- Config：committed defconfig 中 `CONFIG_XNU_PONG_ADRENO_PLATFORM=n`、`CONFIG_XNU_NATIVE_ADRENO=n`：GPU path 实现但关闭，直到 display stack 在没有 GPU 时验证通过。`pong_adreno_start=1` 打开 bring-up entry；ASID `1` 给 GMU、`2` 给 GPU，`shared_asid 1`、`ignore_top_byte 1`、`polled_faults 1`。Metal frontend：20G81-only gate on `sysctl kern.osversion`、`_MTLDevice` instance size `528`、connection types `0x4147`/`0x4148`、`abi_version 1`、16 native methods。
- Procedure：`scripts/build-pong-adreno-platform.py --output-dir <dir> --firmware-dir <dir>` 重新生成 GEN7 register header、编译 objects、把五个 firmware blobs 嵌进 `libPongAdrenoPlatform.a`，report 设 `hardware_qualified=false`；`scripts/build-pong-turnip.py` 与 `scripts/build-pong-metal-bridge.py/--plugin.py` 生成 `libvulkan_freedreno.dylib` 和 `PongAdrenoMetal` bundle；带 `pong_adreno_start=1` boot，读 `PONG ADRENO` records 的最远 passing phase。
- Findings：① GPU port 复用 Nothing Phone (2) SM8475 工作：register windows、GMU boot config、HFI table、CP firmware names 都是 Pong 值，唯一 K60 改动是 SoC timer offsets `0x16220/0x16224`。② GMU bring-up 要求 CM3 held in reset（`GEN7_GMU_CM3_SYSRESET == 1`）、`CM3_CFG 0x4052`、`AHB_FENCE_RANGE_0 0x80c808a0`，以及 firmware-ready poll `0x1ff == 0x100`，之后 HFI power commands `4,3,14,30` 和 `START10` handshake。③ GPU SMMU 是 SMMUv2 LPAE，4 KiB leaves、`ACTLR 0x32b`；它在一个 context 租用 `SID0|0x400` 和 `SID1|0x401`，排除 secure `SID2|0x402`，把 GMU 路由到 `SID5|0x405`。④ Metal shim gated on IOS16.6.1：要求 528-byte `_MTLDevice`，advertise `abi_version 1` 和准确 chip/GMEM 值，拒绝其它 OS build；`configs/pong-iogpu-20G81.json` pin `20G81` `IOAcceleratorES` metaclass 和 prelink base `0xfffffff004fbc000`。⑤ 两个 metal2vulkan patch 加 `IOS16_6_1` level，带 7×64-bit `MTLPixelFormatGetInfo` ABI 和 optional surface row padding（`PONG_IOSURFACE_PADDING=1`）；两个 Mesa patch 把 heap cap 到 `va_size`，并在 250 ms fence wait 后重试 allocation。⑥ link hazard：`PongAdrenoPlatform.cpp` 调用 `pong_ramoops_diagnostic_write`，该函数只在未列入 series 的 settings-pmsg patch 中定义；所以 enable `CONFIG_XNU_PONG_ADRENO_PLATFORM` 而不加该 patch 会 link 失败。⑦ 树内没有任何东西产生过 GPU frame：README 只记录 v98 phone 到过 iOS main UI，Adreno 和 Metal 均未确认。
- Current limits：committed defconfig 关闭；无 device log 记录最后到哪个 bring-up phase；firmware blobs 由外部提供且 `image_verification` 被跳过，不知道是否匹配本 unit；scanout path 需要先验证 display 域。
- Evidence：`source` — `PongAdrenoGmu.c`（CM3 reset gate、GMU boot config、firmware-ready mask、HFI power sequence、`START10` after `OOB_GPU`）；`PongAdrenoPlatform.cpp`（register windows、GMU/SMMU/ASID setup、APSS DRV2 TCS3 parent ARC votes、`pong_adreno_start`）；`configs/pong-iogpu-20G81.json`（instance `136` bytes、`168` virtual entries、metaclass `0xfffffff007a575c8`、prelink base `0xfffffff004fbc000`）。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**差异与判断**

- mzyxsl 是唯一 GPU 实现页，但明确“switched off in committed defconfig、无 device log、无 GPU frame”。任何“GPU 已实现”的说法只能理解为 source-level。
- 当前仓库的 `drivers/PongAdreno` 文件集与 mzyxsl 一致，且 `configs/mondrian_defconfig` 已把 `CONFIG_XNU_PONG_ADRENO_PLATFORM=y`；但 `STATE-2026-11-07 §7` 仍把 GPU 当主动关闭、使用 software framebuffer，GPU-ENABLE-PLAN 要求按 `pong_adreno_start=1` → `pong_gpu_scanout=1` → `pong_gpu_only=1` 分阶段验证，不能一次全开。

### 2.9 Network

**Emilelu `mondrian.md` — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**mzyxsl `mondrian-mzyxsl.md` — `planned`**

- Hardware：K60 是 WCN685x combo on PCIe，带 MHI firmware loading；本 port 尚未枚举 attachment 或 firmware partition。Driver 需要 PCIe 或 MHI window、firmware partition name、自己的 SMMU stream，以及匹配的 OS-facing service（例如 IO80211 family）。
- Config：没有配置项；`board.toml [components]` 和 `configs/mondrian_defconfig` 都没有 network component。
- Procedure：读 vendor DT 和 board files 的 WCN685x node，然后选已有 component 或计划新 driver，再写代码。
- Findings：树内什么都没有：除了 userspace About screen 说本 port 没有 baseband/WLAN/BT transport 之外，没有 driver、patch、script 或 DTS node 提到 Wi-Fi、WCN 或 MHI。
- Current limits：仅 scope；transport 未触及，无法测量。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句。

**差异与判断**

- 官方四页没有 network 实现可照；mzyxsl 只给 WCN685x PCIe/MHI 的范围描述。当前仓库有 `docs/plans/WIFI-PORT-PLAN.md`，其结论是 K60 应移植 Pong 的 QCA6490 + ath11k 路线（PCIe0、BAR0 `0x60200000`/2 MiB、SID `0x1c01`、IOVA `0xA0000000`/256 MiB、MSI SPI140、GPIO 80/81/82/94/95/96/204），且需先补 `PongPower`/`QcomRpmh` 和 `pong_ufs_ready()` 两个依赖。

### 2.10 Audio

**Emilelu `mondrian.md` — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**mzyxsl `mondrian-mzyxsl.md` — `planned`**

- Hardware：audio 需要 ADSP remoteproc reserved-memory range 和 PAS id、GPR/GLink SMEM queues、codec 及其 XO-derived clocks，以及 OS 对 J120 identity 期望的 routing table。OS profile 已提供 J120 AP identity（audio server 用它 key routing database），identity 侧已准备。
- Config：没有配置项；没有 component、defconfig option 或 DTS node 覆盖 ADSP、GPR 或 codec。
- Procedure：从 vendor DT 读 ADSP 和 codec nodes，按 DSP/audio guide 选择或编写 driver。
- Findings：树内什么都没有：DTS 没有 ADSP node，driver/patch/script 也没有提到 ADSP、GPR 或 codec；OS profile 的 product audio node（`wireless-splitter 1`）是 repository 里唯一 audio-related artefact，且它是 OS 侧 ADT property，不是 driver。
- Current limits：仅 scope；没有记录 ADSP window、PAS id 或 codec。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句。

**差异与判断**

- 官方页没有 audio 实现。当前仓库 `docs/plans/BT-AUDIO-PORT-PLAN.md` 纠正了两个关键硬件事实：K60 音频功放是 2×AW882xx（I2C `0x34/0x35`），不是 Pong 的 TFA9873；蓝牙是 UART（`qcom,msm-geni-serial-hs@894000`，QUPV3_2 SE20，IRQ 587，GPIO76/77/78/79，`wakeup-byte 0xfd`），不是 PCIe。音频可复用 PongPower 的 `PongAudio.cpp`/`PongAudioService.cpp`/`PongAudioPlugIn.c`/`PongAudioRoute.h` 与 Sheng 的 `ShengAudioReach.c`/`ShengGpr.c`，但 K60 要新写 AW882xx 适配、TDM 1.536 MHz 双数据线配置和 20G81 HAL/路由 ABI。

### 2.11 Power

**Emilelu `mondrian.md` — `planned`**

- 仅模板句；无 finding、无组件、无 Evidence。

**mzyxsl `mondrian-mzyxsl.md` — `planned`**

- Hardware：PMIC 和 RPMh resources：APSS RSC `0x17a20000`，TCS blocks 在 `+0xd00`，command-db `0x80860000`，SPMI arbiter `0xc400000`（firmware keypad 已经驱动它）。Battery/charger readings 需要 PMIC ADC channels 和 fuel gauge service；两者未枚举。
- Config：committed defconfig 中 `CONFIG_XNU_SHENG_PMGR=n`，唯一的 PMGR boot hook 被编译掉；`board.toml [components]` 没有 battery、charger 或 regulator component。
- Procedure：按 DSP/power guide 枚举 PMIC/RPMh resources，再 enable boot hook 和 parent votes，之后才允许声称任何 state transition。
- Findings：① 树内唯一 power code 在 GPU 侧：`PongAdrenoPlatform.cpp` 通过 APSS DRV2 TCS3 给 GPU parent corner 投票，并从 command-db 序列化 58-word PERF 和 159-word BW payload；它明确注明没有 generic RPMh driver 链接。② `patches/xnu/...-sheng-platform-power.patch` 是一个 15-line hook，在 `bsd_bufferinit()` 后调用 `sheng_pmgr_run()`；该函数在 repository 中没有定义，`CONFIG_XNU_SHENG_PMGR=n` 让调用不进 build。③ 唯一真正的 RPMh regulator writer 在 touch patch 里（`pm8350c ldoc12 1800 mV` 然后 `ldoc3 2700 mV`），但该 patch 不在 series；因此给 panel 和 touch rails 供电依赖 input 域先落地。④ Resource accounting 被抑制而不是实现：boot arg `disable_exc_resource=1` 阻止 wakeups 和 disk-write monitors 到达 `exception_triage()`，因为本板会应答这些异常的服务仍缺失，watchdogd 因无法应答的 FATAL wakeups violation 被杀。移除该 arg 是 power 侧第一个里程碑。
- Current limits：没有 PMIC、charger、battery 或 RPMh aggregator；GPU parent votes 是唯一实现部分且未在硬件证明；resource accounting 是关闭而非提供。
- Evidence：`source` — `PongAdrenoPlatform.cpp`（APSS DRV2 TCS3 parent-corner vote 的 issue/completion message IDs，以及未链接 generic RPMh driver 的声明）。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句。

**差异与判断**

- 官方页没有 power 实现；mzyxsl 的 scope 给出了 APSS RSC/TCS/cmd-db/SPMI 地址和 `CONFIG_XNU_SHENG_PMGR=n` 的现状。当前仓库没有 `PongPower`/`QcomRpmh`，只有 PongAdreno 的 parent vote；`disable_exc_resource=1` 仍在 `board.toml` kernel args 中，移除它需要先有服务应答 wakeups/disk-write monitors。

### 2.12 Image assembly（镜像组装）

**Emilelu `mondrian.md` — `host-verified`**

- The three local trees use different userland models：ours 保留 OS+SystemOS read-only APFS union from unixnu partition；`ios-sweet-k60` 在 build 时重写 writable HFSX image；`UniXNU-pong` 在自己的 static init（成为 PID 1 后 exec launchd）中 run time prepare。Selected approach：先诊断，不替换 PID 1，因为 launchd chain 已验证且 pong adapter 目标是 Darwin 24 ABI。Our kernel 已带 `exec_inject` 和 `bindfs`，所以如果 blocker 需要 run-time preparation，pong model 仍可用。见 `docs/USERLAND-ROUTES-2026-11-02.md`。
- Kernel links and prelinks on macOS CI。Format 1 run `40631225483` produced `54,349,824` bytes；format 2 run `40650877574` produced `54,419,456` bytes at same slide `-0xb9c000` and same lowest component extent `0xfffffff004426600`。
- `69,632`-byte difference 是真实 fix，不是 noise：format-1 glob 以 fuzz 应用 `zzzzzz-pong-init-scratch-allocation.patch`，其 panic string 不在那个 kernel；strict format-2 series 在 intended place 应用，string 存在。Checked scratch allocation 从未在 qualified kernel 中出现过。
- mzyxsl `daed6b5` 修复 local prelink helper，使其 merge OS-profile prelink table 和 board overrides。0238 native kernel 的真实 prelink 成功：32 roots、auto slide `-0xb9c000`、`53,788,672` bytes、SHA-256 `bb33682837f1807ef28d385cf09acf94f2749f49b3f7337d22348dcbf6c4b9df`。非 sibling checkout 用 `--profile/--kit`。
- Evidence `host`：Build kernel succeeded on macOS；prelink slide `-0xb9c000`、`54,419,456` bytes、lowest component extent `0xfffffff004426600`。Command `./unixnu build kernel -D ../UniXNU-mondrian`；Revision `6a10bf5e42ecfad7eed2789cc091287d31009623`。
- Evidence `host`：Route a-18 chain 端到端复现：kernel `20,872,544 B`（`15966fcd`）→ prelink `54,808,576 B` → payload `201,326,592 B` → `boot-darwin24-bc6.img`。Verifier 确认 kernel slot 是 112-byte shim + rebuilt FD，ramdisk slot 与 `payload.img` byte-identical，in-volume `kernel.macho` 与 built kernel match。Command `python3 scripts/k60-prelink-darwin24.py && python3 scripts/verify-boot-img-payload.py --img /mnt/d/Android/k60-ios/boot-darwin24-bc6.img --payload /tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img --kernel /tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/kernel/kernel.macho`；Revision `e636e445b621bed4fac0069f3604b87061350a8d`。

**mzyxsl `mondrian-mzyxsl.md` — `host-verified`**

- Hardware：XNU `8796.141.3` / Darwin `22.6.0`，4 KiB page configuration，target `DEVELOPMENT_ARM64_PONG`，20G81 kernelcache（SHA-256 `d260defc`）作为 prelink input。
- Prelink 需要 `XnuPrelink` kit、32 个 OS-profile roots、slide 和 early-security-init address；device preflight 在 kit entry point 上安装 auto-slide wrapper。
- Payload 需要 20G81 trust cache bundle、`seed/k60-data-seed.dbr`，以及 board 需要 platform seed 时的 `--unique-chip-id`。Boot image 需要 firmware FD、`uefi-mondrian` 的 firmware DTB、payload FAT volume。
- Config：`[kernel.prelink]` 使用 `kits/XnuPrelink/emit_prelink.py`、kernel `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped`、`slide 0`（wrapper 推导 `-0xb9c000`）、32 roots、`kernelcache_sha256 d260defc`。`[payload] volume UNIXNU, size_mib 192, loader firmware, dram_size 0x300000000, timeout 5, tools true, kernel_args -v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x144 cs_enforcement_disable=1 pong_software_keybag=1 disable_exc_resource=1`。`[payload.adt] root_match_volume_uuid C5DAF029-2070-4F68-B3CC-1D1320344CF0` 是唯一 board override；其余 ADT identity 来自 OS profile；`packed_data_ramdisk` unset，所以 raw APFS seed 走 `--data-ramdisk`。
- Procedure：`./unixnu build kernel -D ../UniXNU-mondrian`，然后 `./unixnu build payload --trust-cache prebuilt/20G81-trustcache.bundle --data-ramdisk seed/k60-data-seed.dbr` 和 `./unixnu bootimg`；没有 macOS 时 `python3 scripts/k60-prelink-local.py --kernel mach.development.pong.unstripped --prelinked out/ipsw/20G81/kernelcache.decompressed --output kernel.macho`；`python3 scripts/build-bootimg.py --ramdisk <payload.ramdisk> --output-dir <dir> --fd <SILICIUM_UEFI.fd>` 打包并 self-check v4 boot image；`python3 userland/build.py prepare|apply|finish` 组装 userspace data image，用 `xcrun` 编译 `arm64-apple-ios16.6.1` 并 pack `DBRDISK1`。
- Findings：① kernel links/prelinks macOS CI run `40650877574`：`54,419,456` bytes at slide `-0xb9c000`、lowest extent `0xfffffff004426600`；README 仍显示 earlier round `54,349,824` bytes，少 `69,632`，本记录保留 newer size。② format-2 prelink 在 OS profile，不在 `board.toml`：`k60-prelink-local.py` 过去只读 `board.toml`，在本 device 上失败；现在 merge profile table 并允许 board `[kernel.prelink]` override individual keys。③ profile 故意保留 `slide = "0"`：K60 `__DATA` 是 `0x150000`，20G81 是 `0xb0000`，components 在 slide 0 放不下，wrapper 从 native segment table 推导 `-0xb9c000`。④ ADT generator 拒绝没有 `[payload.adt] chip_id` 的 platform seed，也拒绝超过一个 memory range；所以 seed path 和 16 GiB multi-bank unit 都需要 board decision 才能 packing。⑤ 两个 boot args 是 bring-up decisions 不是 tuning：`pong_software_keybag=1` 选 software-keybag patch 的 volatile no-passcode keybag，因为本板没有 SEP，`mkbinit` 否则强制 recovery-mode reboot；`disable_exc_resource=1` 在服务缺失时阻止 wakeups/disk-write monitors 到 `exception_triage()`。⑥ `build-bootimg.py` 和 `build-native-bootimg-local.py` 都记录 `hardware_tested false`：验证 structure/corruption controls，但从不声称 boot。⑦ Userland build pin 20G81 QuartzCore cache addresses，因此绑定该 OS profile，换 build 必须重新推导。
- Current limits：只有 kernel step host-verified；payload 和 boot image 没有 recorded run；prelink helper 需要 core checkout 和 local XnuPrelink kit，两者不在 repository；ADT platform-seed path 需要 `[payload.adt] chip_id`，故意未设直到 seed policy 决定。
- Evidence：`host` — macOS CI run `40650877574`，prelink slide `-0xb9c000`、`54,419,456` bytes、lowest extent `0xfffffff004426600`，Command `./unixnu build kernel -D ../UniXNU-mondrian`，Revision `6a10bf5e42ecfad7eed2789cc091287d31009623`；`source` — `kits/NativePrelink/emit_prelink.py`（写 `__PRELINK_INFO` after largest extent、记录 `_PrelinkKCID` from kernel + original、拒绝 overwrite）；`scripts/k60-prelink-local.py`（merge `[kernel.prelink]` from OS profile + board override、auto-slide wrapper）。

**wohusaixing / XTOM0706 — `host-verified`**

- 两页的 Image assembly findings 与 Emilelu 第 2、3 条相同：format 1 run `40631225483` 产生 `54,349,824` bytes；format 2 run `40650877574` 产生 `54,419,456` bytes，same slide `-0xb9c000`、same lowest extent `0xfffffff004426600`；`69,632`-byte difference 是 `zzzzzz-pong-init-scratch-allocation.patch` 从 fuzz 到 intended place 的真实 fix。
- Evidence：`host` — macOS run `40650877574`，`54,419,456` bytes、slide `-0xb9c000`、lowest extent `0xfffffff004426600`，Command `./unixnu build kernel -D ../UniXNU-mondrian`，Revision `6a10bf5e42ecfad7eed2789cc091287d31009623`。

**差异与判断**

- Emilelu 额外记录 userland 三模型选择和 Route a-18 的 `k60-prelink-darwin24.py`/`verify-boot-img-payload.py` 链；mzyxsl 额外记录 OS-profile prelink 的 slide 推导和 `build-bootimg.py` 的 `hardware_tested false`。两者共享 CI run `40650877574` 与 kernel size。
- 两者的 payload 路径都依赖 `payload.img`、trust cache（Emilelu 后来按 B 决策去掉）和 Data seed；实际打包前必须先选定 `boot_args` ABI 与 OS profile，否则 `0x480`/`0x2e0` 和 `20G81`/`22H374` 会互相打架。

### 2.13 Diagnostics（诊断）

**Emilelu `mondrian.md` — `device-verified`**

- `### Development findings` 首行模板；实际 finding：从 mzyxsl `76552b88441757defce4080a241c2f0ea7464538` 导入 source-only offline path/evidence checker，保留当前 milestone statuses 而不复制其过时 runtime records。`scripts/audit-forks.py` 枚举 public forks 和所有 branches，pin comparison SHAs，报告 candidates 而不执行或 merge fork code。KX SIGKILL records 单独不能证明 sender 或 pressure；`0238` 增加 committed reason scalars 和 bounded fallback logging。见 `docs/FORK-REVIEW.md` 与 `docs/BOOT-STALL-2026-10-31.md`。
- Evidence `device`：breadcrumbs 把 silent reset 变成 located fault：column 1 显示六个 squares、column 2 零、column 3 一，把死亡位置定在 `ml_parse_cpu_topology()`。第一个 carrier（u64 slots at `0xA73FF000`）无用，因为 hung board 永不返回 DRAM；markers 移到 framebuffer；`0245` 随后在 hardware 产生 readable panic。Command `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc4.img; count the breadcrumb squares`；Revision `e636e445b621bed4fac0069f3604b87061350a8d`；patch `patches/xnu-ipados18/0244-k60-breadcrumbs.patch`。
- Evidence `device`：upstream entry probe 在本 kernel 可安装：stage 1 blue bar、stage 2 magenta bar、stage 3 在 MMU 打开后六秒通过 PSCI reset 板子。板子自行回到 fastboot 再回 Android，所以 hung kernel 不再需要 manual power cycle。Probe 的 panic screen 关闭，因为它把代码装在 `panic()` 之后的 padding，地址是按 reference kernel 固定的。Command `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc7.img`；Revision `350d1c57c86d2fc562c7fa7529271fdae3af95bc`；见 `docs/ROUTE-A-18-UPSTREAM.md`。

**mzyxsl `mondrian-mzyxsl.md` — `planned`**

- Hardware：Firmware log channels：UniXNU menu 把 4 MiB Advanced Logger output 当 QR frames 扫描；serial port 在有 UART 时输出 `UNIXNU:` 和 `DARWINBOOT:` 行。Kernel log channels：IOLog 加 Pong ramoops console mirror at physical `0xA7000000`（2 MiB，12-byte `'DBGC'` header 记录 signature、start、size），由 in-series patch 提供；第二个 2 MiB 是 pmsg zone，helper `pong_ramoops_diagnostic_write` 只在未列出的 settings-pmsg patch 中存在。
- Checkpoint sources：green-bar trampoline、HANDOFF stage lines、PongProbeRecord slot/state pairs。
- Config：`CONFIG_XNU_PONG_RAMOOPS_CONSOLE=y`、`CONFIG_XNU_PONG_VOLATILE_PANIC_LOG=y`、`CONFIG_XNU_PONG_APFS_DEBUG=y`、`CONFIG_XNU_PONG_EARLY_TRACE=n`。Kernel args 当前 `debug=0x144`、`native-ufs=1`；文档 first-boot set 是 `-v keepsyms=1 debug=0x14e cpus=1`。USB logging 设计了但未接线：40-byte frame header magic `PNGLG001 v1`、1 MiB queue、16 KiB batches、20 ms wait，没有 `usblog=` 参数。
- Procedure：`python3 scripts/audit-pong-adt.py <adt> --report <json> --boot-manifest <json>` replay 14 negative ADT cases + byte-exact round trip；`python3 scripts/verify-firmware.py --output-dir <build>` 检查 FV header、module GUIDs、PE images；`scripts/build-probe-stage.sh` 跑完整 host-side chain（无 adb/fastboot）；`python3 scripts/check-porting-paths.py --device .` 离线检查 identity、required areas、evidence shape、component coverage、path ownership、series references。
- Findings：① host-side audit tooling 真实可复用：`audit-pong-adt.py` 拒绝 known-bad loader contracts；`verify-firmware.py` 检查四个 FFS GUID 和 PE machine type；window probe 用 PASS/FAIL 断言 handoff contract。② 多个 harness 指向 repository 之外：`check-pong-probe-policy.py` 读 `/Volumes/PongDev`、`build-window-probe-local.py` 默认该 driver directory、`test-window-qemu.py` 期望 `UniXNU-pong` 和 core checkout 的 `qemu-run.py`；clean clone 跑不了。③ 记录曾引用不存在文件的 glob（`scripts/read-*`、`scripts/probe-*`）和不存在的 `package/Kit.toml`；现在 patterns 匹配实际 scripts。④ 没有 captured log 存在 repository，所以上面每个 hardware checkpoint 是从会打印它的 code 描述的，不是 transcript。
- Current limits：没有任何 on-device transcript；USB log path 仍是 design document；依赖 `/Volumes/PongDev` 或 Pong-layout checkout 的 harness 无法从 clean clone 复现。
- Evidence：`source` — `scripts/audit-pong-adt.py`（byte-exact ADT round trip + 14 rejected contracts + manifest mismatches，打印 `ADT PASS; N invalid-input cases rejected`）；`scripts/verify-firmware.py`（FV header/checksum、UniXNU/UniXNUDxe/DarwinBoot/PongBootMemoryDxe GUIDs、ARM64 PE machine，写 `firmware-verification.json`）。

**wohusaixing / XTOM0706 — `planned`**

- 仅模板句。

**差异与判断**

- Emilelu 有真正 device-verified 的 diagnostics（framebuffer breadcrumbs、entry probe、PSCI reset），但工具链细节少；mzyxsl 有完整 host audit 脚本和 ramoops 设计，但承认没有任何 transcript。
- 两者共同的硬限制：长按电源重启不是 warm reset，DRAM 掉电，ramoops/pstore 永远空；**屏幕是唯一可靠日志**。当前仓库 `STATE-2026-11-07 §13.3` 与这一结论一致，并补充 `PE_k60_reset_now()` 未生效。

## ③ 可直接执行的实现路径

### 3.0 K60 尚未实现域的判定

**按官方四页的 status 口径，严格未实现（全部作者页都是 `planned`）的域只有四个：Input、Network、Audio、Power。** 其中 Input 有 mzyxsl 的完整源码但未进 series，属于“有代码无构建”；Network/Audio/Power 连源码都没有，只有 mzyxsl 的范围描述。

| 域 | 官方页结论 | 能照的作者页 | 组件/文件 | 关键参数 |
|---|---|---|---|---|
| Input | 四页全 `planned`；mzyxsl 有完整 source 但三 patch 不在 series | mzyxsl（唯一源码） | `pong-touch-console.patch`、`pong-goodix-resume.patch`、`pong-physical-keys.patch`；`userland/touch.c` | `spi-base 0x00990000`、`tlmm-base 0x0f000000`、`gcc-base 0x00100000`、`rsc-base 0x17a20000`、`cmd-db-base 0x80860000`、`gpio-offset 0x00100000`、`pins <16 17 18 19 21 20>`、`max-x 14400`、`max-y 32000`、`pong_touch=1` |
| Network | 四页全 `planned`；mzyxsl 仅 WCN685x PCIe/MHI 范围 | 无官方实现；mzyxsl 只给约束 | 无；按本仓 `docs/plans/WIFI-PORT-PLAN.md` 的 PongWifi/QCA6490/ath11k 路线 | PCIe0、BAR0 `0x60200000`/2 MiB、SID `0x1c01`、IOVA `0xA0000000`/256 MiB、MSI SPI140、GPIO `80/81/82/94/95/96/204` |
| Audio | 四页全 `planned`；mzyxsl 仅 ADSP/GPR/GLink 范围 | 无官方实现；mzyxsl 只给约束 | 无；按本仓 `docs/plans/BT-AUDIO-PORT-PLAN.md` 的 PongPower/AudioReach + AW882xx 路线 | ADSP reserved-memory + PAS id、GPR/GLink SMEM、AW882xx I2C `0x34/0x35`、TDM 1.536 MHz 双数据线 |
| Power | 四页全 `planned`；mzyxsl 只有 GPU parent vote | 无官方实现；mzyxsl 只给 APSS RSC 地址 | 无；需新增 `PongPower`/`QcomRpmh` | APSS RSC `0x17a20000`、TCS `+0xd00`、cmd-db `0x80860000`、SPMI `0xc400000`、GPU PERF 58 words / BW 159 words |

**当前仓库口径下另有 5 个“有源码但未完成/未验证”的域**，不要与上面的“全页未实现”混淆：CPU secondary 未过 entry checkpoint；Memory 仍为 4.75 GiB window；Storage 的持久 Data 只有 2 GiB 且 dual-system 未做；Display 的 backlight/120Hz 未做；GPU 的 Metal/scanout 未出设备帧。下面逐域给出可执行路径。

若以 **Emilelu 页** 为基线，则 Storage、Display、Input、GPU 也属于 `planned`，它们的实现路径分别是 3.5、3.6、3.7、3.8，统一照 **mzyxsl 页**；若以 **mzyxsl 页** 为基线，则只剩 Input、Network、Audio、Power 四处没有实现。

### 3.1 Configuration

参照：**mzyxsl 页**（配置四层、五个 pin、98 条 series 写得最全）；Emilelu/wohusaixing/XTOM 只在 83 条 series 摘要层面一致。

组件/文件：`board.toml`、`feeds.toml`、`configs/mondrian_defconfig`、`dts/mondrian.dts`、`patches/xnu/series`、`UniXNU-sm8475-common`。

关键参数：`schema_version = 2`；`soc = SM8475`；`soc_source = sm8475`；`os_profile = ipados-16.6.1-20G81`；components `ArmDTPlatform, ArmCpu, XnuPrelink, PongUfs`；xnu `8796.141.3`（`1b191cb5`）、libplatform `1b2b22f2`、libdispatch `ca80d303`、AvailabilityVersions `f3b52ca7`、sm8475 `d0c90f1e`。

执行：

```bash
# 在 core checkout 旁放置三个仓库后
../UniXNU-mondrian/scripts/k60-macos-preflight.sh
./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
./unixnu fetch -D ../UniXNU-mondrian
./unixnu status --json -D ../UniXNU-mondrian
./unixnu tree -D ../UniXNU-mondrian
python3 scripts/porting-record.py check --device ../UniXNU-mondrian
python3 ../UniXNU-mondrian/scripts/check-porting-paths.py
```

验证判据：所有 pin 解析到存在的 commit；`status --json` 报告 4 个组件；`tree` 的 patch order 与 `patches/xnu/series` 一致；两个 record check 都通过。

### 3.2 Firmware and boot

参照：**mzyxsl 页**（DarwinBoot22 合约、FFS GUID、trust cache bundle、EL1 要求）；真机启动证据用 **Emilelu 页**（Darwin 24 `0x480` ABI）。先确定目标 ABI，再选对应表格。

组件/文件：`uefi-mondrian` 的 `Resources/Configs/mondrian.toml`、`Platforms/Xiaomi/mondrianPkg/mondrian.dsc`、`Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd`、`drivers/DarwinBoot22`。

关键参数：
- Darwin 22 / DarwinBoot22：`boot_args 0x2e0` 字节；command line 608 字节 at `0x6c`；`Video[6]` at `0x28`；一个 256 MiB `EfiConventionalMemory` window，2 MiB 对齐，加 kernel base；ADT ≤ 16 MiB；trust cache 1..128 模块，SHA-1 严格升序。
- Darwin 24 / Emilelu evidence：`0x480` boot_args ABI（1024 字节），loader `boot-darwin24-bc8.img`；`DarwinCurrentEl() != 4` 必须返回 `EFI_UNSUPPORTED`，payload 不能从 EL2 进入。
- 固件 modules：`UniXNU`、`UniXNUDxe`、`DarwinBoot`、`UniXNURamDiskDxe`、`DiskIoDxe`、`FAT`。

执行：

```bash
./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian
# 或 Pong-layout checkout
scripts/build-firmware.sh
python3 scripts/verify-firmware.py --output-dir <build>
# Darwin 22 loader 单独编译
scripts/build-darwinboot22-macos.py
# 真机
scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc8.img
```

验证判据：FV header/checksum 通过；`UniXNU 9b665204`、`UniXNUDxe 29b950cf`、`DarwinBoot 1b64af87`、`PongBootMemoryDxe 7b27b767` 四个 FFS 存在；ARM64 PE machine `0xaa64`；green bar（trampoline）之后能看到 blue/magenta probe bar；`0x480` 与 `0x2e0` 不得混用。

### 3.3 CPU and interrupts

参照：**mzyxsl 页** 的 ArmCpu 源码；**Emilelu 页** 的 flat MPIDR 与 Darwin 24 start-order 证据；flat target 修复用 `patches/xnu-ipados18/0247-k60-psci-flat-targets.patch`，target scan 用 `0250`。

组件/文件：`drivers/ArmCpu/ArmCpu.cpp`、`patches/xnu/zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch`、`patches/xnu-ipados18/0247`、`0248`、`0250`、`dts/sm8475.dtsi`（不得覆盖 CPU nodes）。

关键参数：MPIDR 扁平 `0x000..0x700`；GIC distributor `0x17100000`、redistributor `0x17180000`、stride `0x20000/0x30000/0x40000`；INTID `0` SGI0、`27` CNTV；SPI `32..1019` priority `0xa0`，Adreno SPI `332`；PSCI `0xC4000003 CPU_ON`、`0x84000002 CPU_OFF`，timeout 5 s/3 s；secondary `SCTLR_EL1 0x30D00800`；`MAX_CPUS 8`、`MAX_CPU_CLUSTERS 2`。

执行：

1. 保持 `dts/sm8475.dtsi` 的八个 CPU node 原样；`dts/mondrian.dts` 不写 `cpu@*` override。
2. 用 `python3 scripts/build-pong-armcpu-macos.py` 编译 ArmCpu；archive 通过 `component:ArmCpu` 链接。
3. 把 `0247` 的 `psci_smp_target()`（rank << 8，refusal 重试 plain position）和 `0250` 的 target scan（`0x100..0x700` 逐个尝试，直到 arrival flag 的 low 16 bits 等于 `phys_id`）移植到 active `psci_smp.c`；只靠 `pong-psci-smp.patch` 直接发真实 MPIDR 不足以覆盖本 firmware。
4. 如用当前仓库历史 commit，`3f0e785`（“let the firmware pick, and let a woken core wait for its turn”）是这条修复线的最终版本。
5. 读串口：`ArmCpu: CPU n MPIDR=0x... registered`、`psci: cpu n ...`、`armcpu_timer_interrupts` delta。

验证判据：八个 CPU 都打印 entry checkpoint；没有 `psci: cpu n ... was not started`；每个 CPU timer interrupt count 增长；IPI 能到达每个 secondary。

### 3.4 Memory and DMA

参照：**Emilelu 页的实测内存图**（唯一可用的真机数据）；mzyxsl 页只用于 `NativeRamBlock`/window-probe 实现细节，**不要用它的 12 GiB 单段 DTS**。

组件/文件：`dts/mondrian.dts`、`board.toml [payload] dram_size`、`[payload.adt] owned_memory_size`、`MemoryMapLib.c`（firmware）、`drivers/NativeRamBlock/NativeRamBlock.cpp`、`probes/window-probe.c`。

关键参数：真机六段 RAM，`4..32 GiB` 是 28 GiB hole；最长连续可用 `0x840000000..0xa69b78000` = 8.65 GiB；`DarwinWindowSizeValid` 限 window ≤ `0x200000000`（8 GiB）；4 GiB window 已证明可启动 XNU（`mem=actual=managed=4096 MiB`）；8.625 GiB arena `[0x840000000,0xa68000000)` + 7 GiB window 被 loader 接受（`window 0x1c0000000 at pa 0x8400200000`、`HANDOFF EXIT RETURN 0`），但 XNU 未启动；8 GiB arena 等于整段被 DXE 占用时拒绝；UFS 需要 one physically contiguous 139 KiB buffer below 4 GiB（CAP bit24 clear）；window parser 接受 `0x10000000..0x200000000`、2 MiB steps。

执行：

```bash
# 从真机只读采集内存图
adb shell 'cat /proc/device-tree/memory/reg' > memory-reg.bin
adb shell 'cat /proc/iomem' > iomem.txt
# 选一个 arena 后同步三处
#   1) dts/mondrian.dts: memory@<base> { reg = <...>; }
#   2) board.toml [payload] dram_size = <arena size>
#   3) board.toml [payload.adt] owned_memory_size = <window size, 2 MiB aligned, <= 0x200000000>
# 4) MemoryMapLib.c 加唯一 EfiConventionalMemory arena

python3 repair-high-window.py
build-uefi-8g.sh
build-kernel-summary.sh
package-textonly.py
fastboot boot /mnt/e/k60-work/candidates/7g/boot-ios16-7g-textonly.img
```

验证判据：loader 打印窗口大小与 PA，`HANDOFF EXIT RETURN 0`；XNU console 出现 `mem=actual=managed`；`window-probe` 打印 `PONG WINDOW PASS` 与 `PAGES CHECKED`。当前仓库先按 `docs/plans/MEMORY-12G-PLAN.md` 的阶梯（4.75 → 5 → 8 GiB）执行，不要直接跳 12 GiB。

### 3.5 Storage and root

参照：**mzyxsl 页** 的 NativeUfs/RootLayout 源码；当前仓库的 2 GiB Data GPT 路线（`STATE-2026-11-07 §12`）作为板级几何。

组件/文件：`drivers/NativeUfs/NativeUfs.cpp`、`PongUfsTransport.cpp`、`RootLayout.h`、`RootCommands.h`、`seed/k60-data-seed.dbr`、`scripts/build-userdata.py`、`scripts/derive-ios16-storage-bindings.py`、`scripts/audit-ios16-storage-abi.py`、`scripts/k60-make-data-seed.py`、`scripts/install-pong-ufs-data.py`、`docs/DUAL-SYSTEM.md`。

关键参数：UFS host `0x1d84000`（`0x3000`）、GCC UFS page `0x187000`、SMMU `0x15000000`（`0x100000`）、stream ID `0xe0`、78 context banks、120 stream-match groups；`IDR1.NUMCB 75` cap；LUN 0 必须 4096-byte blocks；`[userdata] first_lba 53342976, last_lba 61731583, lba_bytes 4096`，32 GiB at byte `218,492,829,696`；Data seed 33,554,432 bytes raw APFS `OwnerData` UUID `6DCCF70A-...`（当前仓库实际 Data UUID `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`）；`pong_ufs_readwrite=1`；SCSI allow-list `TUR / START STOP UNIT / READ CAPACITY(10) / READ(10) / WRITE(10) with FUA / SYNCHRONIZE CACHE(10)`。

执行：

```bash
./unixnu build userdata --dry-run
./unixnu build userdata
# 或
scripts/build-userdata.py --component-dir out/ipsw/20G81 --os-disk <OS.cdr> --systemos-disk <SystemOS.dmg>
scripts/derive-ios16-storage-bindings.py --tree <tree>
scripts/audit-ios16-storage-abi.py
scripts/k60-make-data-seed.py --profile <20G81 profile> --output k60-data-seed.dbr
scripts/install-pong-ufs-data.py   # 先确认其 geometry，不要按 Pong 的 sda13/454 GiB 原样跑
# 独立分区：
python3 partition.py inspect   # 详见 docs/DUAL-SYSTEM.md
# 然后 f2fs-shrink helper -> plan -> apply -> verify
```

验证判据：`READ CAPACITY(10)` 返回 4096；GPT header/entries CRC 正确；SHNGROOT manifest window 数正确；`/private/var` 能挂载且 `systembag.kb` 可写；重启后写入仍在。当前仓库先保证 2 GiB Data 的 RW 挂载，再谈 22 GiB 流式/稀疏写入和 dual-system。

### 3.6 Display

参照：**mzyxsl 页**（唯一完整实现）；`display-scale=3` 取自 XTOM0706 `9d1a14f8...`。Emilelu 页只有该 property。

组件/文件：`patches/xnu/0210-k60-display-native-canvas.patch`、`0211-k60-display-startup.patch`、`0212-k60-empty-accelerator.patch`、`0213-k60-display-first-frame.patch`、`drivers/DarwinBoot22` 的 GOP、`userland/ui_compat.c`。

关键参数：panel `m11a_42_02_0a` 1440×3200、DSC video mode、stride from `vinfo.v_rowbytes`；`K60_PANEL_WIDTH 1440`、`K60_PANEL_HEIGHT 3200`、`k60_panel=1`；`kFBDisplayID 1`、Timing/Color ids `1`；`pong_software_ui=0` 仍启动 display services；`XNU_K60_ACCEL_STUB=1` 空 accelerator；framebuffer `BGRA 0x42475241`；QuartzCore hooks `0x1d586e000/0x18826a418`、`0x1d586c7c0/0x1884aa47c`、`0x1d586c7c8/0x1882787f4`、`0x1d586dfd8/0x1882df668`；ADT `display-scale=3`。

执行：

1. 按顺序应用 0210 → 0211 → 0212 → 0213（当前仓库 series 第 86–89 行已是此顺序）。
2. 确保 UEFI GOP 发布 `PixelBlueGreenRedReserved8BitPerColor`，panel native 1440×3200。
3. rebuild kernel + payload，boot 后读 `K60 DISPLAY: first frame presented (swap n, WxH canvas ...)` 和 `K60Display` dictionary 的 `Stride`/`RefreshHz`。
4. Backlight 单独补：mzyxsl 页明确“未实现，只给 initial brightness”。
5. 120Hz 不在本页范围；按 `docs/plans/120HZ-PORT-PLAN.md` 的 DSI timing/0xC6 寄存器路线另做。

验证判据：known frame 几何/颜色正确；`K60Display` 的 Stride/RefreshHz 与 panel 一致；窗口变化后 presentation 存活；backlight 可调。

### 3.7 Input

参照：**mzyxsl 页**（唯一 Goodix/SPMI 源码）+ `docs/plans/K60-TOUCH-PARAMS.md`（K60 实测 ADT 值）。当前仓库已把三 patch 放进 series，但缺 ADT node 与 boot arg。

组件/文件：`patches/xnu/zzzz...-pong-touch-console.patch`、`zzzz...-pong-goodix-resume.patch`、`zzzz...-pong-physical-keys.patch`、`userland/touch.c`、`dts/mondrian.dts`/ADT generator。

关键参数：`spi-base=0x00990000`、`tlmm-base=0x0f000000`、`gcc-base=0x00100000`、`rsc-base=0x17a20000`（drv-2，不是 `0x17a00000` drv-0）、`cmd-db-base=0x80860000`、`gpio-offset=0x00100000`、`pins=<16 17 18 19 21 20>`、`max-x=14400`、`max-y=32000`（或 driver 先把 raw/10 变面板 px 时用 `1440/3200`，单位未核实）、`pong_touch=1`、`touch_flip`（1 左右、2 上下）。

执行：

1. 在 K60 的 ADT 生成路径（`board.toml` → core `devicetree.py`，或 `dts/mondrian.dts` 的 `/arm-io/pong-touch` 节点）加入 K60-TOUCH-PARAMS 的 9 属性 skeleton：

```text
/arm-io/pong-touch {
    compatible = "pong,goodix-berlin-d";
    spi-base = <0x00990000>;
    tlmm-base = <0x0f000000>;
    gcc-base = <0x00100000>;
    rsc-base = <0x17a20000>;
    cmd-db-base = <0x80860000>;
    gpio-offset = <0x00100000>;
    pins = <16 17 18 19 21 20>;
    max-x = <14400>;
    max-y = <32000>;
};
```

2. `board.toml kernel_args` 加 `pong_touch=1`（当前没有）。
3. 启动读 `Berlin-D` probe line 与 first finger report；检查 `/dev/pong-touch`、`/dev/pong-buttons`。
4. RSC 是硬墙：`0x17a00000` 访问死、`0x17a20000` 的 TCS 首次读可能整机死；先用 `k60rpmhoff=1` 做只读诊断，但这不是修复，必须解决 RSC/PMIC 上电再声称 touch 通过。

验证判据：触点映射到 display；多指 ID 稳定；release events 到达；power/volume 键产生 HID report。

### 3.8 GPU

参照：**mzyxsl 页**（唯一实现）；当前仓库 `docs/plans/GPU-ENABLE-PLAN.md` 给出分阶段启用顺序。

组件/文件：`drivers/PongAdreno/*`、`configs/pong-iogpu-20G81.json`、`scripts/build-pong-adreno-platform.py`、`build-pong-turnip.py`、`build-pong-metal-bridge.py`、`patches/xnu/0231-k60-accel-stub-adreno-gate.patch`、`0232-k60-pong-adreno-ramoops-bridge.patch`、`zzzz...pong-gpu-scanout.patch`、`zzzz...pong-gpu-only-display.patch`、`zzzz...pong-source-row-pitch.patch`。

关键参数：Adreno 730 v3 `0x07030002`、GMEM 2 MiB、HighestBankBit 16、64×32 tile；GPU core `0x03d00000`、GMU `0x03d68000`、RSCC `0x03d50000`、cx_misc `0x0b290000`、PDC `0x03d9e000`、GPUCC `0x03d90000`、GPU SMMU `0x03da0000`、AO `0x03d40000`；GMU `CM3_CFG 0x4052`、`AHB_FENCE_RANGE_0 0x80c808a0`、ready poll `0x1ff==0x100`；SMMU `ACTLR 0x32b`、SID `0x400/0x401/0x405`；Metal `_MTLDevice` 528 bytes、`abi_version 1`、connection types `0x4147/0x4148`、16 native methods；prelink base `0xfffffff004fbc000`。

执行：

```bash
# 保持 CONFIG_XNU_PONG_ADRENO_PLATFORM=y
scripts/build-pong-adreno-platform.py --output-dir <dir> --firmware-dir <dir>
scripts/build-pong-turnip.py
scripts/build-pong-metal-bridge.py
scripts/build-pong-metal-plugin.py
# 阶段 A：只开 Adreno bring-up
# kernel args: pong_adreno_start=1
# 阶段 B：加 scanout
# pong_adreno_start=1 pong_gpu_scanout=1
# 阶段 C：Metal
# pong_adreno_start=1 pong_gpu_scanout=1 pong_metal=1
# 决定性实验：pong_gpu_only=1
```

验证判据：阶段 A 出现 `PONG ADRENO: <phase> result=<n>` 且到 `CP ready; authenticated nonsecure fence`；阶段 B 出现 `PONG SCANOUT: GPU frame completed`；阶段 C Metal client 呈现 known image。出现黑屏立即退回上一阶段，不要一次全开。

### 3.9 Network

参照：**没有官方实现页**。mzyxsl 页只给出 WCN685x PCIe/MHI 范围；实际实现参照当前仓库 `docs/plans/WIFI-PORT-PLAN.md` 的 Pong QCA6490/ath11k 路线。

组件/文件：待新增 `drivers/PongWifi`（PongWifiPlatform/PongWifiNet/PongWifiPcie 等）、`PongPower`、`QcomRpmh`；DTS 的 `pcie@1c00000`、`wifi`/`wlan` firmware partition；`IO80211` service。

关键参数：PCIe0 六个 reg 窗口、BAR0 `0x60200000`/2 MiB、GPIO `80/81/82/94/95/96/204`、82 项 PHY 序列、`gdsc@17b004` + collapse vote `0x162128` bit0、SID `0x1c01`、IOVA `0xA0000000`/256 MiB、MSI SPI140；必须先补 `PongPlatformResources`/`QcomRpmh` 与 `pong_ufs_ready()` 导出。

执行：

1. 读 vendor DT 的 WCN685x/QCA6490 node 和 firmware partition，记录 window、interrupt、SMMU stream。
2. 先移植 `PongPower`/`QcomRpmh`；给 NativeUfs 增加 `pong_ufs_ready()` 导出。
3. 移植 `PongWifiPlatform.cpp` 电源/PCIe/PHY/BAR/SID/页表/MSI/worker，再移植 `PongWifiNet.cpp` 的 ifnet/Apple80211/IO80211。
4. 加入 boot-arg gate（按 Pong 的 `pong_wifi_start` 约定），先只读扫描/关联，再跑吞吐。
5. 验证 `en0` 在 Darwin 侧出现、scan/assoc/DHCP/持续 RX/TX 通过。

### 3.10 Audio

参照：**没有官方实现页**。mzyxsl 只给 ADSP/GPR/GLink/codec 范围；实际参照当前仓库 `docs/plans/BT-AUDIO-PORT-PLAN.md`。

组件/文件：待新增 `PongAudio`/`PongAudioService`/`PongAudioPlugIn`/`PongAudioRoute`（可从 PongPower 副本移植）、`ShengAudioReach.c`/`ShengGpr.c`/`AdspFirmware.c`；K60 DTS 的 ADSP reserved-memory、GENI serial HS。

关键参数：ADSP remoteproc reserved-memory + PAS id；GPR/GLink SMEM queues；K60 功放 2×AW882xx I2C `0x34/0x35`（不是 TFA9873）；TDM 1.536 MHz 双数据线；BT UART `qcom,msm-geni-serial-hs@894000`（QUPV3_2 SE20、IRQ 587、GPIO76/77/78/79、`wakeup-byte 0xfd`）；UEFI 64 KiB audio DMA lease。

执行：

1. 从 live FDT 记录 ADSP reserved-memory range、PAS id、GPR/GLink SMEM 地址。
2. 移植 PongAudio 的 ADSP AudioReach、SID1801 DMA、MI2S/TDM 初始化；把 codec 部分替换为 AW882xx。
3. 在 `userland` 加 AudioServerPlugIn 与路由表；按 20G81 HAL/路由 ABI 重新对位（不能照 Pong 的 18/22H374）。
4. 先做 playback known tone，再做 capture/route switch。

### 3.11 Power

参照：**没有官方实现页**。mzyxsl 只给 APSS RSC/TCS/cmd-db/SPMI 地址与 GPU parent vote；需新增 PongPower/QcomRpmh。

组件/文件：待新增 `drivers/PongPower`（PongPlatformResources、QcomRpmh、PongAudio power）、PMIC ADC/fuel gauge driver；`board.toml [components]` 添加 power component。

关键参数：APSS RSC `0x17a20000`、TCS blocks `+0xd00`、cmd-db `0x80860000`、SPMI arbiter `0xc400000`；GPU parent corner 通过 APSS DRV2 TCS3，PERF payload 58 words、BW payload 159 words；touch patch 的 `pm8350c ldoc12 1800 mV → ldoc3 2700 mV` 是目前唯一真实 RPMh regulator writer（但不在 series）。

执行：

1. 先枚举 PMIC（PM8350/PM8350C/PMR735A 等）和 RPMh RSC/TCS，读 command-db。
2. 移植 PongPower 的 `PongPlatformResources`/`QcomRpmh`；给 GPU 的 parent vote 做硬件确认（`parent ARC votes acknowledged`）。
3. 加 battery/charger ADC + fuel gauge service；enable `CONFIG_XNU_SHENG_PMGR` 的真实实现（当前 `=n` 且 `sheng_pmgr_run()` 未定义）。
4. 最后移除 `disable_exc_resource=1`，让 watchdogd 在 wakeups/disk-write monitors 下存活。

### 3.12 Image assembly

参照：**mzyxsl 页**（prelink/payload/bootimg 全流程）+ **Emilelu 页**（Darwin 24 `k60-prelink-darwin24.py`/`verify-boot-img-payload.py` 链）。

组件/文件：`kits/XnuPrelink/emit_prelink.py`、`scripts/k60-prelink-local.py`、`scripts/k60-prelink-darwin24.py`、`scripts/build-bootimg.py`、`scripts/verify-boot-img-payload.py`、`userland/build.py`。

关键参数：XNU `8796.141.3` / Darwin `22.6.0`、4 KiB pages、`DEVELOPMENT_ARM64_PONG`、kernelcache SHA-256 `d260defc`；prelink 32 roots、slide 0 → auto `-0xb9c000`；`[payload] volume UNIXNU, size_mib 192, loader firmware, dram_size <arena>, timeout 5, tools true`；boot image v4，`hardware_tested false`。

执行（下面是 mzyxsl 页的完整路径；当前仓库按 B 决策不带 `--trust-cache`，见第二组命令）：

```bash
# mzyxsl 页路径
./unixnu build kernel -D ../UniXNU-mondrian
./unixnu build payload --trust-cache prebuilt/20G81-trustcache.bundle --data-ramdisk seed/k60-data-seed.dbr
./unixnu bootimg

# 当前仓库 B 决策路径（不要 trust-cache）
./unixnu build kernel -D ../UniXNU-mondrian
./unixnu build payload --data-ramdisk seed/k60-data-seed.dbr
./unixnu bootimg
# 没有 macOS 的本地 prelink
python3 scripts/k60-prelink-local.py --kernel mach.development.pong.unstripped \
  --prelinked out/ipsw/20G81/kernelcache.decompressed --output kernel.macho
python3 scripts/build-bootimg.py --ramdisk <payload.ramdisk> --output-dir <dir> --fd <SILICIUM_UEFI.fd>
python3 scripts/verify-boot-img-payload.py --img <boot.img> --payload <payload.img> --kernel <kernel.macho>
```

验证判据：kernel prelink 成功且 slide/extent 与页面记录一致；payload 含全部声明输入、4 KiB 对齐、`ramdisk_bytes != 0`；boot image v4 header/page alignment 正确；不要相信 `unixnu bootimg` 对 v4 的 `page_size` 误报，用独立 verifier。

### 3.13 Diagnostics

参照：**Emilelu 页**（device breadcrumbs/entry probe 证据）+ **mzyxsl 页**（host audit 脚本）。

组件/文件：`patches/xnu-ipados18/0244-k60-breadcrumbs.patch`、`0245-k60-cpu-clusters.patch`、`0246-k60-console-font-scale.patch`、`scripts/audit-pong-adt.py`、`scripts/verify-firmware.py`、`scripts/build-probe-stage.sh`、`scripts/check-porting-paths.py`、`docs/FORK-REVIEW.md`、`docs/BOOT-STALL-2026-10-31.md`。

关键参数：breadcrumb carrier `0xA73FF000` 无效（hung board 不返回 DRAM）；markers 移入 framebuffer，column 1 six squares、column 2 zero、column 3 one 指向 `ml_parse_cpu_topology()`；entry probe stage1 blue、stage2 magenta、stage3 PSCI reset 6 s after MMU；ramoops `0xA7000000` 2 MiB `'DBGC'` + pmsg 2 MiB；QR frames 4 MiB Advanced Logger。

执行：

```bash
# 真机 breadcrumbs
scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc4.img
# 数 framebuffer squares; 0245 后读 panic
# entry probe
scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc7.img
# host audit
python3 scripts/audit-pong-adt.py <adt> --report <json> --boot-manifest <json>
python3 scripts/verify-firmware.py --output-dir <build>
scripts/build-probe-stage.sh
python3 scripts/check-porting-paths.py --device .
```

验证判据：每个 milestone 都有可复现 command + 匹配 source/image revision + 可见结果；长按重启后 ramoops 为空，必须保存屏幕照片或串口 transcript 作为证据。

## ④ 与当前仓库的差距

### 4.1 当前基线事实（写入时）

- 仓库：`E:/hackios/UniXNU-mondrian`；分支 `fix/k60-measured-high-window`；HEAD `9b4fec1`（`docs(bt-audio): plan the QCA6490 BT and TFA9873 audio ports`）。
- `board.toml`：`schema_version = 2`；components `ArmDTPlatform, ArmCpu, XnuPrelink, PongUfs`；`dram_size = 0x140000000`（5 GiB arena）；`[payload.adt] owned_memory_size = 0x130000000`（4.75 GiB window）；`cpus = 8`；`trust_cache_sha256 = []`（B 决策，已去掉 trust-cache 路径）；`chip_id = 8015`；kernel args 含 `pong_ufs_readwrite=1`、`disable_exc_resource=1`、`k60_fontscale=3`。
- `configs/mondrian_defconfig`：`CONFIG_XNU_PONG_ADRENO_PLATFORM=y`、`CONFIG_XNU_OWNER_DATA_UFS=y`、`CONFIG_XNU_NATIVE_RAM_BLOCK=n`、`CONFIG_XNU_SHENG_PMGR=n`、`CONFIG_XNU_NATIVE_ADRENO=n`。
- `patches/xnu/series`：198 条 active entries；`patches/xnu` 下 221 个 `.patch`；另有 `patches/xnu-ipados18` 7 个 Route A-18/Darwin 24 补丁（`0243`–`0250`）不在 active series。
- 当前状态文档：`docs/state/STATE-2026-11-07.md` 记录 SpringBoard `_checkIn returned`/`_run entered`，唯一硬阻断是 launchd PID 1 在后期 SIGSEGV；§7 说 GPU 主动关闭/软件 framebuffer；§8 说 K60 ADT 一个触摸属性都没发；§12 说 Data 是 2 GiB GPT 窗口、UUID `1BCD69FF-...`。
- 相关方案：`docs/plans/MEMORY-12G-PLAN.md`（12 GiB 是装机容量，最长连续 8.652 GiB，单 window 上限 8 GiB）、`docs/plans/GPU-ENABLE-PLAN.md`、`docs/plans/K60-TOUCH-PARAMS.md`、`docs/plans/WIFI-PORT-PLAN.md`、`docs/plans/BT-AUDIO-PORT-PLAN.md`。

### 4.2 逐域差距表

| 域 | 官方页最好状态 | 当前仓库事实 | 差距/风险 | 下一步 |
|---|---|---|---|---|
| Configuration | mzyxsl `implemented`（98 条 series） | `board.toml` schema 2、4 组件、198 条 active series | 页面已过时（83/98 vs 198），但关键 semantics 已超过页面；trust-cache B 决策与 mzyxsl/Emilelu 的 list 逻辑不同，属有意分歧 | 保留 mzyxsl 四层/pin 语义；不要再把 83/98 条当目标；在文档中标注 B 决策 |
| Firmware and boot | Emilelu `device-verified`（Darwin 24 `0x480`） | DarwinBoot22 源码在树；`README.md` 写 boot_args ABI 已由 `0x2e0/608` 修正为 `0x480/1024`；`board.toml` 仍写 `os_profile ipados-16.6.1-20G81` | **ABI/profile 可能打架**：mzyxsl 页是 Darwin 22 `0x2e0`，Emilelu 证据是 Darwin 24 `0x480`；同一 build 不能混用 | 先锁定目标：20G81 + Darwin 22 或 22H374 + Darwin 24；按 3.2 的对应合同打包；用 `scripts/k60-device.sh boot` 复现 green/blue/magenta bar |
| CPU and interrupts | Emilelu `implemented`（真机 flat MPIDR 证据，但 secondary 未过 entry） | `drivers/ArmCpu` 与 mzyxsl 一致；active series 有 `pong-psci-smp.patch`；`patches/xnu-ipados18/0247/0248/0250` 未进 active series；`board.toml cpus=8` | **八核 secondary 启动仍未证明**；当前 PSCI 直接发真实 MPIDR，可能重复 Emilelu bc9/bc11 的失败；没有八核 log | 把 `0247`/`0250` 的 flat-target/target-scan 逻辑移植进 active `psci_smp.c`；按 3.3 采集 `ArmCpu: CPU n MPIDR` 与 timer delta |
| Memory and DMA | Emilelu `implemented`（8.625 GiB arena/7 GiB window 被 loader 接受；4 GiB 已启动 XNU） | 5 GiB arena `[0x900000000,0xa4000000)`，4.75 GiB window；`MEMORY-12G-PLAN` 认为单 window 上限 8 GiB、最长连续 8.652 GiB | 当前离 8 GiB 窗口还有阶梯；页面 mzyxsl 的 12 GiB 单段不可用；8 GiB arena 与 DXE 冲突的历史已存在 | 按 `MEMORY-12G-PLAN` 先 4.75→5→8 GiB 逐级试；用 Emilelu 的 8.625 GiB arena `[0x840000000,0xa68000000)` 作为 7 GiB 候选；每次记录 `HANDOFF EXIT RETURN` 与 XNU `mem=actual=managed` |
| Storage and root | mzyxsl `implemented`（源码完整，但 `DATA_UFS=n`、32 MiB seed、无设备 log） | `CONFIG_XNU_OWNER_DATA_UFS=y`；2 GiB Data GPT（offset 7420 MiB、UUID `1BCD69FF-...`）；`PongUfsTransport` 已加 K60RD/K60UFS trace | 持久 Data 只有 2 GiB；`install-pong-ufs-data.py` 仍是 Pong geometry；dual-system 未创建；>2 GiB 的 `kern_exec` 限制未解 | 先保证 2 GiB Data RW 挂载与重启持久；再按 `docs/DUAL-SYSTEM.md` 做 partition.py inspect/plan/apply/verify；扩容前改流式/稀疏写入与 `kern_exec` 限制 |
| Display | mzyxsl `implemented`（0210–0213，source only） | active series 第 86–89 行有 0210/0211/0212/0213；`STATE-2026-11-07` 已到 SpringBoard main loop，软件 framebuffer 在跑 | Backlight 未实现；120Hz 未实现；GPU scanout 未启用；没有 `K60 DISPLAY: first frame presented` 的仓库内 transcript | 按 3.6 验证 1440×3200 native canvas；补 backlight；120Hz 另按 `120HZ-PORT-PLAN`；GPU 之前保持 software framebuffer |
| Input | mzyxsl `planned`（唯一源码） | 三个 touch patch 已在 series 第 194–196 行；`board.toml`/`dts` 无 touch node、无 `pong_touch=1`；`STATE §8` 明确 ADT 无触摸属性 | **驱动已编译但无法 probe**；RSC `0x17a20000` 可访问性仍是硬墙；`max-x/max-y` 单位未核实 | 按 3.7 加 `/arm-io/pong-touch` 9 属性与 `pong_touch=1`；先只读 RSC 诊断；用 `K60-TOUCH-PARAMS` 的 `14400/32000` 原值，除非驱动先除 10 |
| GPU | mzyxsl `implemented`（source only，committed 关闭） | `drivers/PongAdreno` 与 mzyxsl 一致；`CONFIG_XNU_PONG_ADRENO_PLATFORM=y`；scanout patches 第 191–193 行 active；`STATE §7` 仍把 GPU 当主动关闭 | 没有 `PONG ADRENO`/`PONG SCANOUT` 设备日志；firmware blobs 外部且未验证；`pong_ramoops_diagnostic_write` 依赖 `0232` | 按 `GPU-ENABLE-PLAN` 分 A/B/C 阶段：`pong_adreno_start=1` → `pong_gpu_scanout=1` → `pong_metal=1`/`pong_gpu_only=1`；不得一次全开 |
| Network | 四页全 `planned`（仅 mzyxsl 范围） | 无 `drivers/PongWifi`、无 DTS node、无 IO80211；只有 `docs/plans/WIFI-PORT-PLAN.md` | 整个 transport 未实现；PongPower/QcomRpmh 与 `pong_ufs_ready()` 两个前置缺口 | 按 3.9 先补 PongPower/QcomRpmh + `pong_ufs_ready()`，再移植 PongWifi 的 PCIe0/MHI/ath11k |
| Audio | 四页全 `planned`（仅 mzyxsl 范围） | 无 ADSP/GPR/codec driver；只有 `docs/plans/BT-AUDIO-PORT-PLAN.md` | 整个音频链路未实现；K60 是 2×AW882xx 不是 TFA9873；BT 是 UART 不是 PCIe | 按 3.10 先 ADSP reserved-memory/PAS id，再移植 PongAudio + 写 AW882xx/TDM |
| Power | 四页全 `planned`（仅 mzyxsl 范围 + GPU vote） | 无 PongPower/QcomRpmh；`CONFIG_XNU_SHENG_PMGR=n`；`disable_exc_resource=1` 仍在 kernel args | 无 PMIC/charger/battery/RPMh；resource accounting 被抑制而非实现；GPU parent vote 未上机 | 按 3.11 移植 PongPower/QcomRpmh；先确认 GPU parent vote，再加 PMIC ADC/fuel gauge；最后移除 `disable_exc_resource` |
| Image assembly | mzyxsl/Emilelu `host-verified` | 完整 `kits/XnuPrelink`、`scripts/k60-prelink-local.py`、`build-bootimg.py`、`verify-boot-img-payload.py`；198 条 series 可构建基础 | 页面 54,419,456 B / slide -0xb9c000 是历史 CI 结果；当前 build 必须重新对 `board.toml` 的 memory/payload 参数；`hardware_tested false` 不等于 boot | 用 3.12 命令重建并记录新 hash/size；打包前锁定 Darwin 22/24 ABI；payload 不许把 trust cache 与 B 决策混用 |
| Diagnostics | Emilelu `device-verified`（breadcrumbs/entry probe） | 当前有 `patches/xnu/0308-k60-usblog-pong-capture-restart.patch`、0238 exit reason、`docs/state`、`docs/audits`；屏幕是唯一可靠日志（ramoops 长按重启无效） | 没有每域的统一 transcript 台账；历史 page 的 QR/ramoops 工具部分依赖 `/Volumes/PongDev` | 按 3.13 把每次 boot 的 command/revision/屏幕照片归档；新增域必须留下 transcript |

### 4.3 与页面快照的时间差

- `mzyxsl` 页停在 2026-10-30：98 条 series、`DATA_UFS=n`、`dram_size 0x300000000`、`trust_cache_sha256` 单元素。当前仓库 2026-11-08 已到 198 条 series、`DATA_UFS=y`、`dram_size 0x140000000`、trust-cache 空数组。**不要把 mzyxsl 页的数值当作当前值**。
- `Emilelu` 页停 2026-11-03：83 条 series，但它的 Firmware/CPU/Memory/Diagnostics evidence 是更晚的 Darwin 24 route（`patches/xnu-ipados18`）。当前仓库保留 `patches/xnu-ipados18` 目录但 active series 不引用它，说明这条 route 仍是 side line，不是当前 20G81 主构建。
- `wohusaixing` / `XTOM0706` 页只是配置模板，不能用于判断当前实现状态；XTOM 唯一可执行贡献是 `display-scale=3`。

## ⑤ 参考 commit/仓库清单

### 5.1 仓库地址

| 名称 | 地址 | 用途 |
|---|---|---|
| Emilelu/UniXNU-mondrian | https://github.com/Emilelu/UniXNU-mondrian | `mondrian.md` 源记录，83 patches，device evidence |
| mzyxsl/UniXNU-mondrian | https://github.com/mzyxsl/UniXNU-mondrian | `mondrian-mzyxsl.md` 源记录，98 patches，最全源码 |
| wohusaixing/UniXNU-mondrian | https://github.com/wohusaixing/UniXNU-mondrian | `mondrian-wohusaixing.md` 源记录，83 patches，配置模板 |
| XTOM0706/UniXNU-mondrian | https://github.com/XTOM0706/UniXNU-mondrian | `mondrian-xtom0706.md` 源记录，`display-scale=3` 来源 |
| Emilelu/UniXNU | https://github.com/Emilelu/UniXNU | CI run `40650877574` 所在主仓 |
| Emilelu/uefi-mondrian | https://github.com/Emilelu/uefi-mondrian | `uefi-mondrian` firmware tree（README 命令使用） |

### 5.2 页面源记录与分支 commit

| Commit | 日期/说明 | 归属 | 关键内容 |
|---|---|---|---|
| `c39ff292eee2726c0135f3ba3a98462c9c21d8de` | 2026-11-03，`docs: merge kernel baseline into device readme` | Emilelu `mondrian.md` | 83 patches；board.toml、ROUTE-A-18、MEASURED-HIGH-WINDOW 等 |
| `76552b88441757defce4080a241c2f0ea7464538` | 2026-10-30，`k60: align the porting record and docs with the building flow` | mzyxsl `mondrian-mzyxsl.md` | 98 patches；DarwinBoot22、ArmCpu、NativeUfs、NativeRamBlock、PongAdreno、0210–0213 等 |
| `092a61d8c20364eab86b35737c6b831c4cecc1ff` | 页面源记录 | wohusaixing `mondrian-wohusaixing.md` | 83 patches；仅配置模板 |
| `9d1a14f83d1050a042313f30dc9d5b7e80d31f7a` | 页面源记录 | XTOM0706 `mondrian-xtom0706.md` | `display-scale=3`；配置模板 |
| `daed6b5d44e3c62978cc0fce4e876ded2a57afc9` | mzyxsl 导入 provenance / prelink helper fix | mzyxsl | Emilelu 页 Fork audit 与 Image assembly 均引用 |
| `3f0e785bc5d3014eb095a45882a9199be8ab6f43` | 2026-11-01，`fix(smp): let the firmware pick, and let a woken core wait for its turn` | 当前仓库 | `0250` PSCI target scan/arrival 修复线的最终版本（当前 active series 未引用） |
| `9b4fec1` | 2026-11-08，当前 HEAD（短号） | 当前仓库 | 198 active series；本文件写入基线 |

### 5.3 Evidence 中的 revision / command 对照

| 页面 | 域 | Evidence 类型 | Command | Revision |
|---|---|---|---|---|
| Emilelu | Firmware and boot | `device` | `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc8.img` | `d2af811a6dc9c6225de586e1615ca3824e2edce4` |
| Emilelu | CPU | `device` | `adb shell 'cat /sys/devices/system/cpu/cpu*/topology/physical_package_id; cat /proc/device-tree/cpus/cpu@*/reg'` | `e636e445b621bed4fac0069f3604b87061350a8d` |
| Emilelu | CPU | `device` | `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc8.img` | `d2af811a6dc9c6225de586e1615ca3824e2edce4` |
| Emilelu | CPU | `device` | `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc11.img` | `e636e445b621bed4fac0069f3604b87061350a8d` |
| Emilelu | Memory and DMA | `host` | `python3 repair-high-window.py; build-uefi-8g.sh; build-kernel-summary.sh; package-textonly.py` | `48abe35d0a0a57f5fea9f9ba1e570800021ae6b1` |
| Emilelu | Memory and DMA | `device` | `fastboot boot /mnt/e/k60-work/candidates/7g/boot-ios16-7g-textonly.img` | `e06211de59325bbd086c312324bdbf40e21d1045` |
| Emilelu | Image assembly | `host` | `./unixnu build kernel -D ../UniXNU-mondrian` | `6a10bf5e42ecfad7eed2789cc091287d31009623` |
| Emilelu | Image assembly | `host` | `python3 scripts/k60-prelink-darwin24.py && python3 scripts/verify-boot-img-payload.py --img /mnt/d/Android/k60-ios/boot-darwin24-bc6.img --payload /tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/payload/payload.img --kernel /tmp/k60build/out/mondrian/ipados-18.7.10-22H374/mondrian/kernel/kernel.macho` | `e636e445b621bed4fac0069f3604b87061350a8d` |
| Emilelu | Diagnostics | `device` | `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc4.img; count the breadcrumb squares` | `e636e445b621bed4fac0069f3604b87061350a8d` |
| Emilelu | Diagnostics | `device` | `scripts/k60-device.sh boot /mnt/d/Android/k60-ios/boot-darwin24-bc7.img` | `350d1c57c86d2fc562c7fa7529271fdae3af95bc` |
| mzyxsl | Image assembly | `host` | `./unixnu build kernel -D ../UniXNU-mondrian` | `6a10bf5e42ecfad7eed2789cc091287d31009623` |

### 5.4 关键 SHA / 摘要值

| 值 | 含义 | 来源 |
|---|---|---|
| `8ea52daf4b3e926d4840e13a73fa00c9cadf9b3f1e97e1ececfdaa446e1afc34` | 8.625 GiB arena/7 GiB window candidate image SHA-256 | Emilelu Memory `host` evidence |
| `bb33682837f1807ef28d385cf09acf94f2749f49b3f7337d22348dcbf6c4b9df` | 0238 native kernel prelink SHA-256 | Emilelu Image assembly finding |
| `344ae6445dfcb791ac838dbfec5c4d39a871cf58f91d8bee84ba57204f6727e6` | `prebuilt/20G81-trustcache.bundle` SHA-256 | mzyxsl Firmware evidence |
| `5fd2f3566e989d11cde74289151888392615a4771e5b616ff5e98ca3b24ffc03` | `seed/k60-data-seed.dbr` SHA-256 | mzyxsl Storage evidence |
| `d260defc` | 20G81 kernelcache SHA-256（页面只给前缀） | mzyxsl Firmware/Image assembly |
| `15966fcd` | Route a-18 kernel short hash（20,872,544 B） | Emilelu Image assembly evidence |
| `12d4a6` / `df2020` / `aa33dd` | window probe pass / wrong-window failure / exception control colours | mzyxsl Firmware evidence |
| `1b191cb5` / `1b2b22f2` / `ca80d303` / `f3b52ca7` / `d0c90f1e` | xnu / libplatform / libdispatch / AvailabilityVersions / sm8475 pins（页面短号） | mzyxsl Configuration evidence |
| `70f20268` | 旧 lock 中的 sm8475 commit（已被 `d0c90f1e` 取代） | mzyxsl Configuration finding |
| `40631225483` / `40650877574` | GitHub Actions format-1 / format-2 kernel build run ID | Emilelu/wohusaixing/XTOM Image assembly |

### 5.5 页面 section 行号索引（便于复核全文）

| 页面 | Configuration | Firmware | CPU | Memory | Storage | Display | Input | GPU | Network | Audio | Power | Image | Diagnostics |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `mondrian.md` | 29 | 68 | 105 | 147 | 189 | 230 | 267 | 303 | 339 | 375 | 411 | 447 | 489 |
| `mondrian-mzyxsl.md` | 29 | 80 | 134 | 184 | 233 | 293 | 342 | 390 | 443 | 480 | 518 | 560 | 617 |
| `mondrian-wohusaixing.md` | 29 | 67 | 103 | 139 | 175 | 213 | 249 | 285 | 321 | 357 | 393 | 429 | 467 |
| `mondrian-xtom0706.md` | 29 | 67 | 103 | 139 | 175 | 215 | 251 | 287 | 323 | 359 | 395 | 431 | 469 |

### 5.6 一句话交付结论

对 K60 的实现排序应是：**先按 Emilelu 修 memory/CPU 的真机约束，再按 mzyxsl 补 storage/display/GPU 源码，最后按当前仓库的 `MEMORY-12G-PLAN`/`GPU-ENABLE-PLAN`/`K60-TOUCH-PARAMS`/`WIFI-PORT-PLAN`/`BT-AUDIO-PORT-PLAN` 做剩余域；Network/Audio/Power 没有作者页可照，只能按当前仓库方案稿从零实现。**
