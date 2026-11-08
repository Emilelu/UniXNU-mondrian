# MZYSL-DIFF — mzyxsl/UniXNU-mondrian 与 E:/hackios/UniXNU-mondrian 机械对比

> 生成时间：2026-11-08（Asia/Shanghai）
> 上游：`https://github.com/mzyxsl/UniXNU-mondrian` @ `main` `76552b88441757defce4080a241c2f0ea7464538`
> 本地对比快照：`E:/hackios/UniXNU-mondrian` @ `fix/k60-measured-high-window` `fd3ef0ec63738eed9295709b2e907e013cd50a0c`
> 纪律：本报告只做只读对比；未修改本仓代码；上游克隆位于 `/opt/k60/archive/mzyxsl-mondrian`（WSL，`--depth 50`）。

## ① 仓库 pin

### 1.1 上游 mzyxsl

| 项 | 值 |
|---|---|
| remote | `https://github.com/mzyxsl/UniXNU-mondrian.git` |
| branch | `main` |
| HEAD | `76552b88441757defce4080a241c2f0ea7464538` |
| 提交时间 | `2026-10-30 14:24:02 +0800` |
| subject | `k60: align the porting record and docs with the building flow` |
| tracked files | 381 |
| `patches/xnu/*.patch` | 120 |
| `patches/xnu/series` 条目 | 98 |
| `porting.toml` | 549 行 / 57,811 B，13 个 area |

`git -C /opt/k60/archive/mzyxsl-mondrian log --oneline -5`：

```text
76552b8 k60: align the porting record and docs with the building flow
daed6b5 k60: fix the board inputs the payload, lock and prelink steps read
de71f85 k60: suppress the resource monitors while their services are absent
ce509e2 k60: boot with the software keybag selected
f0b4d9e k60: point the Data mount at this board's seed volume
```

### 1.2 本地

| 项 | 值 |
|---|---|
| path | `E:/hackios/UniXNU-mondrian` |
| branch | `fix/k60-measured-high-window` |
| 对比快照 | `fd3ef0ec63738eed9295709b2e907e013cd50a0c` |
| tracked files | 595 |
| `patches/xnu/*.patch` | 221 |
| `patches/xnu/series` 条目 | 198 |
| `porting.toml` | 189 行 / 28,615 B（快照），13 个 area |

### 1.3 关系判断

本仓是 mzyxsl 的下游超集，而不是两个平行实现：

- `porting.toml:17`（local）明确记录：`Fork audit 2026-10-31: mzyxsl daed6b5d44e3c62978cc0fce4e876ded2a57afc9 imported with provenance.`
- `porting.toml:185`（local）记录从 mzyxsl `76552b88…` 导入 source-only offline checker，并说明 mzyxsl 的 runtime records 已过时。
- 机械结果：mzyxsl 的 120 个补丁文件在本仓全部存在（`only-in-mzyxsl = 0`）；mzyxsl 的 98 条 series 是本仓 198 条的**精确前缀**；156 个 driver 文件中 155 个字节相同；49 个脚本全部存在于本仓。
- 因此，本报告的“可直接 cherry-pick”重点不是搬文件，而是确认哪些 mzyxsl 实现已经被本仓吸收、哪些参数不能照抄。

## ② board / series / dts / drivers 差异表

### 2.1 `board.toml` 逐键对比

| 键 | mzyxsl | local | 差异判断 |
|---|---|---|---|
| `schema_version` | `2` | `2` | 相同 |
| `[board] name/soc/soc_source/os_profile/description/kit` | `mondrian` / `SM8475` / `sm8475` / `ipados-16.6.1-20G81` / `Redmi K60 (mondrian/SM8475): UniXNU UEFI bring-up` / `mondrian` | 同左 | 完全相同 |
| `[components].include` | `["ArmDTPlatform","ArmCpu","XnuPrelink","PongUfs"]` | 同左 | 完全相同 |
| `[kernel].defconfig` | `mondrian_defconfig` | 同左 | 相同 |
| `[kernel].config_fragments` | `arch:configs/common.config`、`soc:configs/sm8475.config`、`os:configs/ipados.config` | 同左 | 相同 |
| `[kernel].patch_series` | `["device:patches/xnu/series"]` | 同左 | 相同 |
| `[kernel].archives` | `component:ArmDTPlatform`、`component:ArmCpu`、`component:PongUfs` | 同左 | 相同 |
| `[kernel].driver_records` | `DEVELOPMENT_ARM64_PONG` | 同左 | 相同 |
| `[kernel].pong_native_driver_source` | 无 | `/tmp/k60build/pong-driver`（`board.toml:23-29`） | local 独有；为 PongAdreno/UI provider 脚本提供源码树 |
| `[device_tree].source/include_dirs` | `device:dts/mondrian.dts` / `["soc:dts"]` | 同左 | 完全相同 |
| `[userdata] first_lba/last_lba/lba_bytes/windows` | `53342976` / `61731583` / `4096` / `OS` + `Cryptex1,SystemOS` | 同左 | 完全相同 |
| `[payload].volume/size_mib/loader/title/cpus/tools/timeout` | `UNIXNU` / `192` / `firmware` / `UniXNU` / `8` / `true` / `5` | 同左 | 完全相同 |
| `[payload].dram_size` | `0x300000000`（12 GiB，`board.toml:73`） | `0x140000000`（5 GiB handoff arena，`board.toml:98`） | **冲突**；local 依据实测内存图，mzyxsl 的 12 GiB 单段不可用 |
| `[payload].kernel_args` | `-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x144 cs_enforcement_disable=1 pong_software_keybag=1 disable_exc_resource=1`（7 项，`board.toml:81`） | 同左 + `pong_ufs_readwrite=1` + `k60_fontscale=3`（9 项，`board.toml:125`） | local 多两项：UFS 写使能、控制台字体缩放 |
| `[payload].trust_cache_sha256` | `["344ae644…e6"]`（1 项，`board.toml:104`） | `[]`（`board.toml:146`） | local 走无 trust-cache sidecar 路线；mzyxsl 走 bundle 白名单 |
| `[payload.adt].root_match_volume_uuid` | `C5DAF029-2070-4F68-B3CC-1D1320344CF0` | 同左 | 相同 |
| `[payload.adt].chip_id` | 无 | `"8015"`（`board.toml:149`） | local 独有；platform seed/ADT 需要 |
| `[payload.adt].owned_memory_size` | 无 | `"0x130000000"`（4.75 GiB 窗口，`board.toml:162`） | local 独有；DarwinBoot window 大小 |

`[firmware]` 整段（config、dsc、fd、patches、packages、defines）逐项相同，不在表中重复。

### 2.2 `patches/xnu/series`

| 指标 | mzyxsl | local |
|---|---:|---:|
| 有效条目（去注释） | 98 | 198 |
| 文件大小 | 4,597 B | 7,629 B |
| 与对方的关系 | 本仓前 98 条的精确前缀 | 前 98 条与 mzyxsl 完全一致；末尾追加 100 条 |
| 仅 mzyxsl 有 | — | 0 |
| 顺序差 | — | 0（`lc[:98] == mz` 为 `True`） |

mzyxsl `series:1-10` 的注释写明：目录里另有 22 个 patch 文件因“本板配置关闭或属于另一个 XNU 版本”而未列入 series。完整 22 个见附录 A。

local 追加的 100 条覆盖：`0214-0243` 的 K60 运行期/诊断补丁、`0300-0390` 的 usblog/panic/异常/CF 补丁、`zzy*`/`zzzz*` 的 cryptex、gpu scanout、touch、container-path 等。

### 2.3 `patches/xnu/*.patch`

| 指标 | 数量 |
|---|---:|
| mzyxsl `.patch` 文件 | 120 |
| local `.patch` 文件 | 221 |
| 仅 mzyxsl 有 | **0** |
| 仅 local 有 | 101 |
| 同名且 SHA-256 相同 | 113 |
| 同名但内容不同 | 7 |

同名内容不同的 7 个文件（方向：mzyxsl → local）：

| patch | 字节 | 行变化 | 差异摘要 |
|---|---:|---:|---|
| `0211-k60-display-startup.patch` | 877 → 1,300 | +10 / −2 | local 增加 `static_cast<IOService *>(IOService::getPlatform())` 及注释，修编译错误；显示启动语义不变 |
| `offline-owner-systemos-mount.patch` | 23,422 → 28,316 | +138 / −16 | local 增加 `XNU_OWNER_DATA_UFS` 分支、`native_pong_ufs_data_volume_device` 弱桩、RO/RW mount 标记与 `pong_data_mount` 开关；mzyxsl 仅有 RAM seed 分支 |
| `zzz-boot-progress.patch` | 11,254 → 11,755 | +69 / −52 | local 适配更新后的 XNU 行号，增加 K60DATA mount / watchdog policy 阶段点 |
| `zzzzz-pong-ramoops-minimal.patch` | 5,139 → 6,379 | +116 / −72 | local 把状态拆成独立头文件，新增 `pong_ramoops_debug_base/start/size` 访问器 |
| `pong-touch-console.patch` | 36,603 → 36,622 | +3 / −3 | local 将 DT 断言 `max-x/max-y` 从 `1080/2412` 改为 `14400/32000`；若启用触摸需按 dtbo 复核（input 当前 planned） |
| `pong-gpu-scanout.patch` | 3,466 → 3,431 | +6 / −6 | local 用 `k60PanelNative()` 门控 canvas，`drawLayer` 改为 `if (!gpuFrame)` |
| `pong-gpu-only-display.patch` | 3,716 → 3,054 | +3 / −19 | local 删除 mzyxsl 的 `pong_display` boot-arg 改名，保留 `pong_software_ui` 语义并整理格式 |

`patches/mesa/**`、`patches/metal2vulkan/**`、`patches/unixnu-core/**` 的文件名集合与内容均无差异。

### 2.4 `dts/mondrian.dts`

| 项 | mzyxsl | local |
|---|---|---|
| 行数 | 48 | 64 |
| model/compatible | `Redmi K60` / `xiaomi,mondrian` | 相同 |
| `/memory` 节点 | `memory@80000000`，`reg = <0x0 0x80000000 0x3 0x0>`（2 GiB 起、12 GiB 长，`dts/mondrian.dts:23-26`） | `memory@900000000`，`reg = <0x9 0x00000000 0x1 0x40000000>`（36 GiB 起、5 GiB 长，`dts/mondrian.dts:29-32`） |
| UFS 节点 | `ufs@1d84000`，`dts/mondrian.dts:33-47` | 相同值，`dts/mondrian.dts:39-53` |
| CPU 说明 | 无 | `dts/mondrian.dts:55-63` 解释 SoC dtsi 的 flat MPIDR，禁止板级覆盖 |

唯一实质差异是 `/memory`。mzyxsl 的 12 GiB 单段与 local 的实测内存图（六段、4..32 GiB 为 28 GiB hole、最长连续 8.65 GiB）冲突；见 ②-2.7 的 memory 行和 ⑤ 风险 1。

### 2.5 `drivers/`

| 指标 | mzyxsl | local |
|---|---:|---:|
| 文件数 | 156 | 156 |
| 仅 mzyxsl 有 | 0 | — |
| 同名内容不同 | — | 1 |
| 字节相同 | — | 155 |

唯一不同：`drivers/NativeUfs/PongUfsTransport.cpp`（local 相对 mzyxsl +47 / −2）。local 增加 Data mount 的读追踪、write call/write result 追踪，以及 `native_pong_ufs_data_volume_device` 的 Data 窗口绑定逻辑；mzyxsl 版本只有基本读写路径。

`drivers/NativeMetal` 是两边 `.gitmodules` 都声明的空 submodule（未初始化），不构成本质差异。

### 2.6 `scripts/`

| 指标 | mzyxsl | local |
|---|---:|---:|
| 文件数（`.py/.sh/.js/.rb`） | 49 | 78 |
| 仅 mzyxsl 有 | 0 | — |
| 仅 local 有 | — | 29 |
| 同名不同 | — | 7 |

同名不同（方向 mzyxsl → local）：

| 脚本 | 差异摘要 |
|---|---|
| `build-pong-armcpu-macos.py` | local 的 host 检查从 `Darwin + x86_64` 放宽为 `Darwin 或 Linux` |
| `build-pong-platform-macos.py` | 同上 |
| `build-pong-ram-block-macos.py` | 同上 |
| `build-pong-ufs-probe-macos.py` | 同上 |
| `build-xnu-4k-baseline.sh` | local 增加 Linux `c++filt` shim、`XNU_PONG_RAMOOPS_CONSOLE` 早绑定、`PONG_ADRENO_PLATFORM` 默认 1、复制 `drivers/PongAdreno` 到 build root、强制重链平台 archive |
| `k60-make-data-seed.py` | local 增加 `--size` 参数（mzyxsl 固定 `32m`） |
| `k60-prelink-local.py` | 仅 docstring 措辞差异 |

仅 local 有的 29 个脚本完整名单见附录 C，主要包括 Darwin24 构建链（`build-darwin24-*`、`k60-prelink-darwin24.py`、`verify-darwin24-img.sh`）、K60 数据工具（`inspect-k60-data.py`、`install-k60-ufs-data.py`、`make-k60-gpt-data-image.py`）、设备/日志工具（`k60-device.sh`、`k60-ramoops-read.sh`、`k60-sync-refs.sh`、`dump-boot-img-layout.py`）及 fork/同步工具（`audit-forks.py`、`sync-repos.sh`）。

### 2.7 `porting.toml` 各 area status 与 findings 差异

#### status

| area | mzyxsl | local（快照 fd3ef0e） | 判断 |
|---|---|---|---|
| configuration | implemented | implemented | 相同 |
| firmware | implemented | **device-verified** | local 更高 |
| cpu | implemented | implemented | 相同 |
| memory | implemented | implemented | 相同，但事实冲突（见 findings） |
| storage | implemented | implemented | 相同 status，local 有设备日志 |
| display | implemented | implemented | 相同 status，local 有设备日志 |
| input | planned | planned | 相同 |
| gpu | **implemented** | **planned** | mzyxsl 声称实现，local 明确链接失败，停在 planned |
| network | planned | planned | 相同 |
| audio | planned | planned | 相同 |
| power | planned | planned | 相同 |
| packaging | host-verified | host-verified | 相同 |
| diagnostics | planned | **device-verified** | local 更高 |

mzyxsl 的 README 自己定义：`implemented` = 源码已就位但无主机或板端日志（`README.md:42-43`）。因此上表的 implemented 不能理解为“已跑通”。

#### findings（数量与要点）

| area | mzyxsl findings | local findings | 差异要点 |
|---|---:|---:|---|
| configuration | 4 | 2 | mzyxsl 记录 format-2 迁移、lock pin 修正、trust-cache 数组化；local 保留 fork audit + trust-cache schema 说明，二者无事实冲突 |
| firmware | 6 | 1 | mzyxsl 有 6 条 loader 源码级发现（EL1、绿条、window layout、trust cache bundle、QEMU 测试）；local 以 device-verified 的 green-bar 启动记录为主 |
| cpu | 6 | 2 | mzyxsl 是 GICv3/PSCI 源码细节；local 有 flat MPIDR 实测、三色探针、CPU start order 修复等设备证据，8 核仍未见 secondary 通过 checkpoint |
| memory | 5 | 4 | **实质性冲突**：mzyxsl 写“12 GiB 单段 /memory @0x80000000、620 MiB window 来自维护者笔记”（`porting.toml:146,171`）；local 实测“六段、4..32 GiB 28 GiB hole、最长 8.65 GiB、4 GiB 窗口启动成功、7 GiB loader 接受但 XNU 无输出、12 GiB 不可能”（`porting.toml:59,61`） |
| storage | 8 | 3 | mzyxsl：UFS 读路径 + 32 MiB RAM seed，`CONFIG_XNU_OWNER_DATA_UFS=n`，持久化窗口未编译（`:213,221`）；local：`/dev/disk5s1` 0x4f8200000 bytes UFS Data 窗口读写挂载成功（`porting.toml:73`），`K60DATA mounted ro=0 fstype=apfs` |
| display | 5 | 3 | mzyxsl：0210-0213 native canvas / 空 IOAccelerator stub / first-frame 日志，source only（`:265`）；local：同 patch 集 + 0236，且设备日志到达 SpringBoard main loop（`porting.toml:87`） |
| input | 5 | 2 | mzyxsl：Goodix 三个补丁源码完整但未列入 series；local：K60 触摸参数已提取，RSC/TCS 首次读会整机死，仍 planned |
| gpu | 7 | 2 | mzyxsl：Adreno 730 v3、GMU/HFI/CP、Metal ABI 全套源码，但 `CONFIG_XNU_PONG_ADRENO_PLATFORM=n` 且无设备日志（`:332,354`）；local：103 文件、series 191-193 启用 scanout，但链接报 undefined `_pong_scanout_frame / _pong_scanout_initialize / _pong_scanout_quarantined`（`porting.toml:115`） |
| network | 1 | 2 | mzyxsl 仅范围；local 记录官方 `Ath12kWifi` pin 与 K60 PCIe/BAR/SID 参数 |
| audio | 2 | 1 | mzyxsl 有 OS profile audio node 说明；local 仅占位，二者均 planned |
| power | 4 | 2 | mzyxsl 记录 GPU parent vote、Sheng PMGR stub、RPMh 只在 touch patch 中、`disable_exc_resource=1`；local 占位 |
| packaging | 7 | 4 | 都有 macOS CI prelink 记录（run 40631225483 / 40650877574）；mzyxsl 细节更多，local 有 darwin24 路线选择 |
| diagnostics | 4 | 2 | mzyxsl 只有 host audit 工具；local device-verified，有 breadcrumb/panic 屏证据 |

## ③ Storage / Display / GPU 实现细节（mzyxsl 的“implemented”到底用了什么）

### 3.1 Storage

mzyxsl 的 Storage status = `implemented`（`README.md:51`、`porting.toml:184-232`），但该 area 的 limits 明确写着：**没有设备日志；读路径实现但未验证；持久化 UFS Data 窗口根本没有编译**（`porting.toml:221`）。其实现是“UFS LUN0 只读 root + 32 MiB RAM seed”，不是可用的持久化存储。

**驱动**

| 文件:行 | 内容 |
|---|---|
| `drivers/NativeUfs/NativeUfs.cpp:26-29` | `kGccUfsPage = 0x00187000`、`kUfsHost = 0x01d84000`、`kUfsHostBytes = 0x3000`、`kUfsStreamId = 0xe0` |
| `drivers/NativeUfs/NativeUfs.cpp:157-159` | 首个 MMIO 前的 DT 等值检查：`pong,ufs-hc-base/size`、`pong,gcc-ufs-page`、`pong,smmu-base/size` |
| `drivers/NativeUfs/NativeUfs.cpp:170-171` | `pong,smmu-stream-id`、`pong,ufs-spi=265`、`pong,smmu-context-banks=78`、`pong,smmu-match-groups=120` 等值检查 |
| `drivers/NativeUfs/PongUfsTransport.cpp:129-134` | `pong_ufs_readwrite` boot-arg 门控所有写操作 |
| `drivers/NativeUfs/PongUfsTransport.cpp:204` | `READ CAPACITY(10)` 必须是 4096 字节块，否则 `unsupported LUN geometry` |
| `drivers/NativeUfs/PongUfsTransport.cpp:234` | 非 writable 或未对齐窗口设置 `PongReadOnly` |
| `drivers/NativeUfs/RootLayout.h:109` | `K60_ROOT_PARTITION "unixnu"` |
| `drivers/NativeUfs/RootLayout.h:162` | `SHNGROOT` magic `0x474e4853 0x544f4f52` |

**DTS / board / config**

| 文件:行 | 内容 |
|---|---|
| `dts/mondrian.dts:33-47` | UFS 节点：host `0x1d84000/0x3000`、GCC `0x187000`、SMMU `0x15000000/0x100000`、stream `0xe0`、SPI 265、context banks 78、match groups 120 |
| `configs/mondrian_defconfig:23-25` | `CONFIG_XNU_NATIVE_RAM_BLOCK=y`、`CONFIG_XNU_NATIVE_TRUST_CACHE=y`、`CONFIG_XNU_NATIVE_UFS=y` |
| `configs/mondrian_defconfig:31-44` | owner cache/startup/data mount 全开，`CONFIG_XNU_OWNER_DATA_UFS=n` |
| `configs/mondrian_defconfig:40` | `CONFIG_XNU_OWNER_DATA_VOLUME_UUID="6DCCF70A-6FD6-403E-ACED-95313CD7CBB8"`（与仓内 `seed/k60-data-seed.dbr` 实测一致） |
| `board.toml:81` | kernel args **没有** `pong_ufs_readwrite=1`，因此按代码写路径默认关闭 |

**series 中实际生效的 Storage 补丁**

- `patches/xnu/series:20` `ios16-native-ufs-personality.patch`
- `patches/xnu/series:29-31` `native-4k-bootstrap-capacity.patch`、`native-4k-signature-hash-cache.patch`、`native-4k-user-abi.patch`
- `patches/xnu/series:35-37` `native-ram-block-personality.patch`、`native-trust-cache-runtime.patch`、`native-union-getattrlistbulk.patch`
- `patches/xnu/series:44` `null-root-media.patch`
- `patches/xnu/series:48-53` `offline-owner-boot-manifest.patch`、`offline-owner-cache-carrier.patch`、`offline-owner-root-binding-audit.patch`、`offline-owner-root-crypto-probe.patch`、`offline-owner-z-air-init.patch`、`offline-owner-zz-pong-release-launchd.patch`
- `patches/xnu/series:79-80` `offline-owner-systemos-mount.patch`、`pong-systemos-shared-region.patch`
- `patches/xnu/series:106-108` 三个 trust-cache 补丁

**存在但未列入 series（因此不参与构建）**：`zzzzzz-pong-writable-data.patch`、`...-pong-ufs-data.patch`、`...-pong-union-lower-directory.patch`。这正是 mzyxsl 的 `DATA_UFS=n` 与“持久化窗口未编译”的来源。

`scripts/install-pong-ufs-data.py:16-17,60-66` 还硬编码 Pong 几何：`FIRST_4K=0x413248`、`LAST_4K=0x75a40ea`、`/dev/block/sda13`，不能用于 K60 的 `unixnu` 分区。

### 3.2 Display

mzyxsl Display status = `implemented`（`README.md:52`、`porting.toml:236-277`），但 limits 明确：**仓库里没有一张 first frame 的设备日志，area 是 source only**（`porting.toml:265`）。其实现是 0210–0213 四个 XNU 补丁 + userland QuartzCore 兼容层。

**补丁**

| 文件:行 | 内容 |
|---|---|
| `patches/xnu/0210-k60-display-native-canvas.patch:22-24` | `K60_PANEL_WIDTH 1440`、`K60_PANEL_HEIGHT 3200`、`TUNABLE(gK60Panel, "k60_panel", 1)` |
| `patches/xnu/0210-k60-display-native-canvas.patch:44-56` | native panel 时拒绝 `fbwidth/fbheight/fbscale`，canvas 固定为 1440×3200 |
| `patches/xnu/0210-k60-display-native-canvas.patch:65-71` | 打印 `K60 DISPLAY: panel … canvas … stride … Hz` |
| `patches/xnu/0210-k60-display-native-canvas.patch:76-91` | 发布 `K60Display` 字典：PanelWidth/PanelHeight/CanvasWidth/CanvasHeight/Stride/RefreshHz/Native |
| `patches/xnu/0211-k60-display-startup.patch:10-17` | `pong_software_ui=0` 才关闭显示服务，未设置则默认启动 |
| `patches/xnu/0212-k60-empty-accelerator.patch:65-79` | 空 `IOAcceleratorES`：最多 16 个 scalar output 清零、structure output 清零、前 24 个 selector 打日志 |
| `patches/xnu/0212-k60-empty-accelerator.patch:98-101` | `IOAcceleratorStub=true`，不发布 `MetalPluginName` |
| `patches/xnu/0213-k60-display-first-frame.patch:10` | `kFBDisplayID 1`（0 表示无显示） |
| `patches/xnu/0213-k60-display-first-frame.patch:27-30` | `K60 DISPLAY: first frame presented (swap …)` |
| `patches/xnu/0213-k60-display-first-frame.patch:39` | display id 返回 `kFBDisplayID` |
| `userland/ui_compat.c:709-718` | 强制 framebuffer 格式 `0x42475241`（`BGRA`） |
| `userland/ui_compat.c:800-811` | 四个 QuartzCore 虚地址 hook：`0x1d586e000/0x18826a418`、`0x1d586c7c0/0x1884aa47c`、`0x1d586c7c8/0x1882787f4`、`0x1d586dfd8/0x1882df668` |

**参数**

- `k60_panel=1`（默认；仅当 boot framebuffer 恰好 1440×3200 时启用 native canvas，否则回落 generic）。
- `pong_software_ui=0` 可关闭显示服务；未设置默认开启。
- `accel_stub=0` 可关闭空 accelerator（`0212:114-117`）。
- `kFBDisplayID=1`、`kFBTimingID=1`、`kFBColorID=1`。

**实际可用的部分**：`0210`、`0212`、`0213` 与本仓字节相同；`0211` 本仓是 mzyxsl 版 + 编译修复。因此显示补丁本身可直接使用，不需要从 mzyxsl 重新取。mzyxsl 不提供设备证据；本仓 `porting.toml:87` 有 SpringBoard main loop 的设备日志（`[SpringBoard] _checkIn returned` → `UIApplication _run entered`）。

### 3.3 GPU

mzyxsl GPU status = `implemented`（`README.md:54`、`porting.toml:321-366`），但同一记录自己写着：`CONFIG_XNU_PONG_ADRENO_PLATFORM=n and CONFIG_XNU_NATIVE_ADRENO=n`（`porting.toml:332`），limits 又写“switched off in the committed defconfig, and no device log records which bring-up phase was reached last”（`porting.toml:354`）。此外，真正把 GPU 画面上屏的 `pong-gpu-scanout` / `pong-gpu-only-display` / `pong-source-row-pitch` 三个 patch **不在 mzyxsl 的 series 中**（见 2.2 的成员检查，均为 `False`）。所以 mzyxsl 的 GPU “implemented” = 驱动源码完整、默认不编译、没有画面。

**驱动**

| 文件:行 | 内容 |
|---|---|
| `drivers/PongAdreno/PongAdrenoGmu.c:10-13` | 8 个寄存器窗口：GPU core `0x03d00000/0x40000`、GMU `0x03d68000/0x37000`、RSCC `0x03d50000/0x10000`、PDC `0x0b290000/0x10000`、CxMisc `0x03d9e000/0x1000`、GPUCC `0x03d90000/0xa000`、GPU SMMU `0x03da0000/0x40000`、AO `0x03d40000/0x10000` |
| `drivers/PongAdreno/PongAdrenoGmu.h:19-31` | `PongAdrenoChipId=0x07030002`、GMEM `0x200000`；GPU/LPAC/secure/GMU SID = 0/1/2/5，GMU mask `0x400`；IRQ 332/336/337；context banks 21、stream slots 24；HighestBankBit 16；tile 64×32；timer `0x16220/0x16224` |
| `drivers/PongAdreno/PongAdrenoGmu.c:96` | 要求 `GEN7_GMU_CM3_SYSRESET == 1`（CM3 处于复位）才继续 |
| `drivers/PongAdreno/PongAdrenoGmu.c:148` | `GEN7_GMU_CM3_CFG = 0x4052` |
| `drivers/PongAdreno/PongAdrenoGmu.c:164-166` | 释放 CM3 reset 后轮询 `GEN7_GMU_CM3_FW_INIT_RESULT`：`0x1ff == 0x100` 才算 firmware ready |
| `drivers/PongAdreno/PongAdrenoGmu.c:175` | 失败后重新置 CM3 复位并 poison |
| `drivers/PongAdreno/PongAdrenoPlatform.cpp:287-288` | `config.asid=1`、`shared_asid=1`、`ignore_top_byte=1`、`polled_faults=1`、`continue_after_fault=1` |
| `drivers/PongAdreno/PongAdrenoPlatform.cpp:291-294` | 在 `0x03da0000` 启 GPU SMMU，绑定 GMU bank/slots |
| `drivers/PongAdreno/PongAdrenoPlatform.cpp:389-396` | `pong_adreno_start=1` 才启动一次性的 GPU bring-up 线程 |
| `drivers/PongMetal/PongMetalAbi.h:8-14` | 20G81 `_MTLDevice` instance size **528**，不是 Sheng 的 536 |
| `drivers/PongMetal/PongMetalPlugin.mm:92` | Metal 连接类型 `0x4147`；`PongMetalScanout.h:68` 为 `0x4148` |
| `configs/pong-iogpu-20G81.json:3-5,16` | `instance_bytes=136`、`virtual_entries=168`、`metaclass=0xfffffff007a575c8`、`original_prelink_base=0xfffffff004fbc000` |
| `scripts/build-pong-adreno-platform.py:41-83` | 编译 `AdrenoFirmware`、`PongAdrenoHfi`、`PongAdrenoGmu`、`PongAdrenoSmmu`、`PongAdrenoCp`、`PongAdrenoNativeGlue`、`PongAdrenoScanout`、`PongAdrenoAccelerator` 及 `ArmSmmu4K` 子目录；固件由 `--firmware-dir` 外部提供 |

**参数**

- `pong_adreno_start=1` 启用 bring-up；mzyxsl 的 defconfig 里 `CONFIG_XNU_PONG_ADRENO_PLATFORM=n`、`CONFIG_XNU_NATIVE_ADRENO=n`（`configs/mondrian_defconfig:14,46`），所以默认不链接、不启动。
- 外部固件：`gmu_gen70000.bin`、`a730_sqe.fw`、`a730_zap.mdt/.b01/.b02`（构建时提供，仓库不含）。
- ASID：GMU 1、GPU 2、shared ASID 1；`ignore_top_byte=1`、`polled_faults=1`。

**本仓现状**：GPU 驱动文件与 mzyxsl 相同（103 个 `PongAdreno` + 12 个 `PongMetal`），但本仓 `porting.toml:115` 记录内核链接失败：`_pong_scanout_frame / _pong_scanout_initialize / _pong_scanout_quarantined` undefined；本仓 GPU 状态为 planned，且 `patches/xnu/series:191-193` 已启用三个 scanout 补丁。也就是说：**mzyxsl 的 GPU 实现可作为源码参考，但不能作为“已可用”的证据；本仓的问题在链接/构建，不在驱动源码缺失。**

## ④ 三类清单

### A. 可直接 cherry-pick / 直接采用

> 机械结论：`only-in-mzyxsl` 的补丁文件和 driver 文件均为 **0**。下列内容已经在本仓中，属于“无需搬运、可直接采用”的实现；如果将来从 mzyxsl 重新同步，字节相同的文件可以按同名直接覆盖；`0211-k60-display-startup.patch` 与 `PongUfsTransport.cpp` 必须保留本仓版本，否则会丢掉编译修复和 Data 窗口追踪。

| 对象 | 证据 | 用法 |
|---|---|---|
| Display `0210` / `0212` / `0213` | 与本仓同路径文件 SHA-256 相同；`0211` 本仓多一个编译修复 | 直接使用本仓版本 |
| `drivers/PongAdreno/**`（103 文件）+ `drivers/PongMetal/**`（12 文件）+ `configs/pong-iogpu-20G81.json` | 全部字节相同 | GPU 源码与常量可直接作为实现基础 |
| `drivers/NativeUfs/**`（除 `PongUfsTransport.cpp`） | 全部字节相同 | UFS 读路径可直接用 |
| `patches/mesa/**`、`patches/metal2vulkan/**`、`patches/unixnu-core/**` | 文件集与内容相同 | 直接复用 |
| `porting.toml` 的 Storage/Display/GPU `inputs`/`configuration` 段 | mzyxsl 记录更细（UFS SMMU 事实、1440×3200 面板、Adreno 730 v3 窗口） | 可摘录进本仓 porting record 的 findings；不要连同 status/12 GiB 一起搬 |
| `docs/DUAL-SYSTEM.md`、`docs/NEXT-STEPS.md`、`docs/USB-LOGGING-PLAN.zh.md` | 本仓已有更完整版本（`docs/reference/DUAL-SYSTEM.md` 多 Data 空间补充、`docs/reference/USB-LOGGING-PLAN.zh.md`、`docs/state/NEXT-STEPS.md`） | 不需要复制；mzyxsl 版只作历史参考 |

### B. 需改参数

| 对象 | mzyxsl 值 | 本仓应取 | 原因 |
|---|---|---|---|
| `[payload].dram_size` | `0x300000000`（12 GiB） | `0x140000000`（5 GiB arena）或按新实测 | mzyxsl 记录自认来自维护者笔记而非 boot log（`porting.toml:171`）；本仓实测 12 GiB 单段不可达，DarwinWindowSizeValid ≤8 GiB |
| `/memory` DTS | `memory@80000000 / <0x0 0x80000000 0x3 0x0>` | `memory@900000000 / <0x9 0x0 0x1 0x40000000>` | 必须与实际 handoff arena 一致，否则 ADT/DarwinBoot 窗口失败 |
| `[payload].kernel_args` | 不含 `pong_ufs_readwrite=1`、`k60_fontscale=3` | 加上这两个 | 不加 `pong_ufs_readwrite=1` 则 UFS 所有写被 `PongUfsTransport.cpp:131-134` 拒绝；不加 `k60_fontscale=3` 则 1440×3200 上控制台不可读 |
| `CONFIG_XNU_OWNER_DATA_VOLUME_UUID` | `6DCCF70A-6FD6-403E-ACED-95313CD7CBB8` | 走 seed 时用该值；走 UFS Data 安装时按实际卷（本仓当前是 `1BCD69FF-…`） | mzyxsl 值只对应 32 MiB `seed/k60-data-seed.dbr`（实测 UUID `6DCCF70A-…`）；本仓当前 `CONFIG_XNU_OWNER_DATA_UFS=y` 对应已安装 UFS Data，两者不能混用 |
| `CONFIG_XNU_OWNER_DATA_UFS` | `n` | `y`（本仓当前） | 只有 `y` 才能把持久化 Data 窗口编译进去；mzyxsl 的 `n` 是“只读 root + RAM seed” |
| `CONFIG_XNU_NATIVE_RAM_BLOCK` / `CONFIG_XNU_NATIVE_TRUST_CACHE` | `y` / `y` | `n` / `n`（本仓当前） | `DATA_UFS=y` 与 NativeRamBlock 不能同时有效；本仓走 UFS trust-cache runtime 路线 |
| `CONFIG_XNU_PONG_ADRENO_PLATFORM` | `n` | `y`（本仓当前） | 要用 GPU 必须链接 Adreno platform；但仅设置此项还不够，需先修 `_pong_scanout_*` 链接 |
| `pong_adreno_start` | 无（默认 0） | `1`（bring-up 时） | `PongAdrenoPlatform.cpp:389-396` 只有该 boot-arg=1 才启动 GPU 线程 |
| `k60_panel` | 默认 1 | 保持 1 仅当 framebuffer 真的是 1440×3200；换面板/模拟器设 0 | `0210:22-32` 的 `k60PanelNative()` 硬门控 |
| `pong_software_ui` | 默认启动（只有 `=0` 关闭） | 默认不传；需要纯控制台时传 0 | `0211:10-17` |
| `trust_cache_sha256` | `["344ae644…e6"]` | `[]`（本仓当前）或按实际 payload sidecar 恢复 | 本仓 payload 不带 trust-cache sidecar；mzyxsl 的 bundle 路线与 local 不同 |

### C. 不可用

| 对象 | 证据 | 结论 |
|---|---|---|
| mzyxsl `board.toml` 的 12 GiB `dram_size` + `dts/mondrian.dts` 的 `memory@80000000` 单段 | `board.toml:73`、`dts/mondrian.dts:23-26`；与 local `porting.toml:59,61` 实测六段 / 28 GiB hole / 4 GiB 窗口相反；`porting.toml:171` 自认来自 maintainer notes，不是 boot log | **不可用**：按此配置无法在本仓实测单元启动 |
| mzyxsl Storage “implemented” 作为持久化存储 | `porting.toml:213` `CONFIG_XNU_OWNER_DATA_UFS=n`；`pong-ufs-data.patch` 不在 series；`porting.toml:221` 无设备日志 | **不可用**：只是 UFS 只读 root + 32 MiB RAM seed，掉电即失；不能当持久化 Data |
| mzyxsl GPU “implemented” 作为可用 GPU | `porting.toml:332` `CONFIG_XNU_PONG_ADRENO_PLATFORM=n`；gpu-scanout/only-display/source-row-pitch 不在 series；`porting.toml:354` 无设备日志 | **不可用**：源码完整但默认不编译、无 GPU 画面 |
| `scripts/install-pong-ufs-data.py` | `:16-17` `FIRST_4K=0x413248`、`LAST_4K=0x75a40ea`；`:60-66` `/dev/block/sda13` + Pong geometry 检查 | **不可用**：硬编码 Pong userdata 几何，不能装 K60 `unixnu` 分区 |
| `scripts/build-pong-*-macos.py`（4 个） | mzyxsl 版本要求 `platform.system() == 'Darwin' and platform.machine() == 'x86_64'` | **不可用**：在 WSL/Linux 直接拒绝；本仓已放宽为 Darwin/Linux，不要回退 |
| mzyxsl `pong-touch-console.patch` 的触摸坐标断言 | mzyxsl `max-x=1080 / max-y=2412`，local 改成 `14400 / 32000`；且该 patch 不在 mzyxsl series（input 仍 planned） | **不可直接采用**：坐标量纲与面板不一致，启用前必须按 `docs/plans/K60-TOUCH-PARAMS.md` 的 dtbo 实测值复核 |
| mzyxsl `docs/NEXT-STEPS.md` 的 620 MiB / 0x26C0000 记录 | `porting.toml:162` 自认 `0x26C0000` 写错、应为 `0x26C00000`；仍是历史笔记 | **不可作为当前参数**：只可当历史线索，不要写入 board.toml/dts |

## ⑤ 风险

1. **状态语义风险（最高）**：mzyxsl 的 `implemented` 明确定义为“源码已就位但无主机或板端日志”（`README.md:42-43`）。把它的 Storage/Display/GPU 三个 implemented 当作“可直接上机”会误判；其 Storage 持久化未编译、GPU 默认关闭、Display 无 first-frame 日志。
2. **内存配置冲突（最高）**：mzyxsl 的 `board.toml:73` + `dts/mondrian.dts:23-26` 是 12 GiB 单段，本仓 `porting.toml:59,61` 有实测六段内存图、28 GiB hole、4 GiB 窗口成功、12 GiB 不可能。若把 mzyxsl 的 `board.toml`/`dts` 机械覆盖到本仓，会直接破坏当前可启动配置。以本仓实测为准；换 12/16 GiB 机型需重新测量后再改。
3. **Storage UUID 分叉风险**：mzyxsl 的 `CONFIG_XNU_OWNER_DATA_VOLUME_UUID=6DCCF70A…` 对应 32 MiB seed；本仓 `configs/mondrian_defconfig:46` 当前是 `1BCD69FF…`（UFS Data 安装路径）。混用会导致 `native_owner_data_prepare()` 找不到 Data 卷，`/private/var` 不挂载，mkbinit 报错。修改前先确认走 seed 还是 UFS 安装。
4. **GPU 链接风险**：本仓 `porting.toml:115` 已记录 `_pong_scanout_frame/_pong_scanout_initialize/_pong_scanout_quarantined` undefined；mzyxsl 的 `build-pong-adreno-platform.py` 虽把 `PongAdrenoScanout` 列入编译源，但 mzyxsl 自己未把它编入 series/defconfig，无法证明链接通过。先修 build 脚本/归档，再谈 `pong_adreno_start=1`。
5. **record 自身不一致**：本仓 `porting.toml` 的 storage/display 已提升为 `implemented`，但 `limits` 仍是模板占位“Hardware inputs and implementation are pending”（`porting.toml:75,89`）；GPU 仍 `planned` 但已有 `103 files + series 191-193`。报告发布前应把 limits/findings 与状态对齐，避免下游把 status 当作证据。
6. **上游分叉不可 patch-merge**：mzyxsl 的 98 条 series 是本仓 198 条的前缀，但本仓对 7 个同名 patch 做了内容修改（尤其 `offline-owner-systemos-mount.patch`、`pong-gpu-scanout.patch`）。若未来用 mzyxsl 的 patch 文件覆盖，会丢掉本仓的 UFS Data 分支和 GPU 修正；只能按文件级 review 后选择性同步。
7. **并发/工作区风险**：对比期间本仓 `porting.toml` 多次更新（storage/display 状态提升），本报告以快照 `fd3ef0e` 为准；若继续有并发提交，重新生成表格时应以新 HEAD 重跑同样的机械脚本。

## 附录

### A. mzyxsl 目录中存在但未列入其 series 的 22 个 patch

```text
external-archive-dependencies.patch
native-aes-personality.patch
offline-pgz-alignment-probe.patch
pgz-aligned-validation.patch
public-entitlements-header.patch
published-freezer-condition.patch
zzy-native-gpu-addon-mount.patch
zzz-boot-progress.patch
zzzzzz-pong-writable-data.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-init-envp-plumbing.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-upstream-oct22.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-container-path.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-goodix-resume.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-settings-pmsg.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-zap-reservation.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-scanout.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-gpu-only-display.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-source-row-pitch.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-union-lower-directory.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-ufs-data.patch
```

### B. local 独有的 101 个 `patches/xnu/*.patch`

```text
0214-k60-console-font-scale.patch
0215-k60-data-keybags-probe.patch
0216-k60-aks-bag-selectors.patch
0217-k60-aks-status.patch
0218-k60-data-keybag-file.patch
0219-k60-iowatchdog.patch
0220-k60-coredump-off.patch
0221-k60-watchdog-status.patch
0222-k60-disable-watchdogd.patch
0230-k60-exc-resource-early-out.patch
0231-k60-accel-stub-adreno-gate.patch
0232-k60-pong-adreno-ramoops-bridge.patch
0233-k60-mfb-selector-success.patch
0234-k60-seed-boot-preferences.patch
0235-k60-exec-exit-trace.patch
0236-k60-managed-memory-and-panel.patch
0237-k60-keybag-watch-opt-in.patch
0238-k60-exit-reason-observer.patch
0239-k60-runtime-directories.patch
0240-k60-sandbox-policy-always.patch
0241-k60-skip-launch-constraints.patch
0242-k60-entitlements-include-shim.patch
0243-k60-console-export.patch
0300-k60-usblog-ep0.patch
0301-k60-sandbox-kx-histogram.patch
0302-data-cap-execerr-kxp.patch
0303-k60-heartbeat.patch
0304-kxq-rate-ler-lw.patch
0305-kxq-site-tags.patch
0306-k60-console-snapshot.patch
0307-k60-usblog-dma-coherency.patch
0308-k60-usblog-pong-capture-restart.patch
0309-k60-minimac-amfi-standin.patch
0310-k60-amfi-keep-first.patch
0311-k60-panic-restart-reason.patch
0314-k60-kern-exit-tolerate-and-clean.patch
0318-k60-miniamfi-optional.patch
0320-k60-skip-firmware-mount.patch
0321-k60-probe-vm-mem-entry.patch
0322-k60-probe-procinfo.patch
0323-k60-probe-audit-token.patch
0324-k60-probe-trailer-audit.patch
0325-k60-probe-trailer-elem.patch
0326-k60-probe-posix-spawn.patch
0327-k60-persona-proxy-bootstrap.patch
0328-k60-exit-reason-payload.patch
0329-k60-miniamfi-entitlement-trace.patch
0330-k60-entitlement-allow.patch
0330-k60-entitlement-any.patch
0331-k60-prevlog-replay.patch
0332-k60-skip-prelinked-load.patch
0333-k60-prevlog-panic-focus.patch
0334-k60-panic-reset-fastboot.patch
0335-k60-setprop-guard.patch
0336-k60-setprop-report.patch
0337-k60-checkin-compat.patch
0338-k60-panic-flush.patch
0339-k60-xpc-report.patch
0340-k60-uilib-deploy.patch
0341-k60-setprop-probe.patch
0342-k60-reserve-probe.patch
0343-k60-reserve-fail.sh.patch
0344-k60-client-uaf-probe.patch
0345-k60-setprop-null-guard.patch
0346-k60-userexc-trace.patch
0347-k60-panic-text.patch
0348-k60-kernexc-trace.patch
0349-k60-client-pin.patch
0350-k60-getprop-null-guard.patch
0351-k60-property-guards.patch
0352-k60-client-pin-hold.patch
0353-k60-client-call-guards.patch
0354-k60-panic-backtrace.patch
0355-k60-connect-guards.patch
0356-k60-analytics-notifport.patch
0357-k60-close-gen-guard.patch
0358-k60-deny-analytics-open.patch
0359-k60-proptable-guards.patch
0360-k60-null-lock-safety.patch
0361-k60-childset-guard.patch
0362-k60-nullentry-name.patch
0363-k60-attach-expansion.patch
0364-k60-deny-without-release.patch
0365-k60-ui-owns-screen.patch
0366-k60-userexc-pid.patch
0367-k60-userexc-sp-fp.patch
0373-k60-dyld-payload.patch
0384-k60-pid-hibernate.patch
0385-k60-aks-datamigrator.patch
0386-k60-quiet-exec-probes.patch
0387-k60-panic-args.patch
0388-k60-n4k-cache-io.patch
0389-k60-kx-pc-lr.patch
0390-k60-cryptex-app-access.patch
zzyb-native-cryptex-os-view.patch
zzyc-owner-skip-launch-constraints.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-cache-report.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mactable-summary.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mem-report.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-quiet-wakes.patch
zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-quiet-watch.patch
```

### C. local 独有的 29 个 `scripts/` 文件

```text
scripts/adt-generate.py
scripts/audit-forks.py
scripts/build-darwin24-console.py
scripts/build-darwin24-linux.sh
scripts/build-darwin24-platform.py
scripts/build-k60-platform-archives.py
scripts/build-pong-adreno-platform-linux.py
scripts/check-kernel-entry.py
scripts/check-kernel-thread-entry.py
scripts/dump-boot-img-layout.py
scripts/extract-kernelcache-kexts.py
scripts/inspect-k60-data.py
scripts/install-k60-ufs-data.py
scripts/k60-bootstrap-pt-model.py
scripts/k60-compare-components.py
scripts/k60-device.sh
scripts/k60-prelink-darwin24.py
scripts/k60-ramoops-read.sh
scripts/k60-sync-refs.sh
scripts/make-k60-gpt-data-image.py
scripts/parse-kernelcache-im4p.py
scripts/patch-armcpu-validate.py
scripts/sync-repos.sh
scripts/verify-boot-img-payload.py
scripts/verify-boot-img-shim.py
scripts/verify-darwin24-img.sh
scripts/verify-k60-boot-img.sh
scripts/verify-kernel-platform-symbols.sh
scripts/verify-loader-abi.py
```
