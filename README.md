# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

本仓库是**格式 2 设备仓**：`board.toml` 的 `schema_version = 2`，配置由 UniXNU 的共享解析器
按 ARM64 → SoC → OS → 设备四层合并，输出目录为
`out/mondrian/ipados-16.6.1-20G81/mondrian/`。

## 四层仓库

| 层 | 仓库 | 内容 |
| --- | --- | --- |
| 框架 | [Emilelu/UniXNU](https://github.com/Emilelu/UniXNU)（分支 `k60`） | `unixnu` 命令、共享脚本、`profiles/arch/arm64`、`profiles/os/ipados-16.6.1-20G81`、组件目录 |
| SoC | [Emilelu/UniXNU-sm8475-common](https://github.com/Emilelu/UniXNU-sm8475-common) | `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi`（CPU / PSCI / GIC） |
| 设备 | 本仓库 | `board.toml`、`dts/mondrian.dts`、`configs/mondrian_defconfig`、`patches/xnu/series`、`package/`、`porting.toml` |
| 固件 | [Emilelu/uefi-mondrian](https://github.com/Emilelu/uefi-mondrian) | EDK2 / Mu-Silicium 构建树，产出 `SILICIUM_UEFI.fd` |

迁移记录见 `porting.toml`；它同时是 [unixnu.com/zh/devices/mondrian](https://unixnu.com/zh/devices/mondrian)
页面渲染的数据源。

## 当前状态（2026-10-30）

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UEFI 启动链 | ✅ | ABL -> `fastboot boot` -> BootShim -> UEFI -> UniXNU 菜单 |
| 显示 | ✅ | ABL splash framebuffer + SimpleFbDxe GOP，1440×3200 / stride 5760 B；无 GPU 加速 |
| 实体按键 | ✅ | 官方 KeypadDevice 链 + `K60KeypadDeviceLib`（SPMI PON/GPIO） |
| Tools -> Advanced Logger | ✅ | 4 MB Advanced Logger + QR 序列帧，OneSend 可抓 DXE 全量日志 |
| XNU 内核 | ✅ | 本地 Linux（WSL）与 macOS CI 均可编：`kernel.macho` 53.5 MB，含 prelink |
| 板级 ADT / payload / bootimg | ✅ | payload 192 MiB + Android boot v4 镜像；校验用 `scripts/verify-k60-boot-img.sh` |
| UFS root（SHNGROOT） | ✅ | OS / SystemOS 两个只读窗口，union 挂到 `/` |
| `/private/var`（Data） | 🟡 只读 | 真实 UFS Data 窗口 @ offset `7,780,433,920`，32 MiB，只读可挂 |
| keybag / MKB | ❌ | Data 不可写 → `systembag.kb` 写不进 → `MKB FATAL` |
| 触摸 / GPU / 音频 / 网络 / 相机 | ❌ | 未开始。GPU 驱动源码已在 `drivers/PongAdreno/`（含 `submit/`），尚未进链接 |

已实测：XNU 已 exec 到 `launchd`，服务链推进到 `watchdogd`（pid 95）；
`/private/var` 来自真实 UFS Data 窗口，首次挂载成功（只读）。

## 当前卡点（2026-10-30）

1. **APFS 读写挂载在空间管理器扫描后卡死**。已加 `K60UFS write#N` 有限次跟踪（`drivers/NativeUfs/`），
   尚未判定是 UFS 写命令卡住还是 APFS 内部卡住。
2. **32 MiB Data 过小**。同 SoC 的 sirius 先例：32 MiB Data 空间耗尽 → watchdogd `brk #1` → panic。
   扩容需要重造 APFS 种子（`hdiutil`/`newfs_apfs`，只能在 macOS 上做）。
3. **换文件系统有前置条件**：20G81 的 kernelcache 里有 `com.apple.filesystems.hfs` 与
   `com.apple.filesystems.tmpfs`，但本仓库的 prelink 根列表里一个都没有，
   所以 `mount("hfs")` / `mount("tmpfs")` 现在必然 `ENODEV`。要用得先改 core 的 prelink 配置。

## 工具

| 脚本 | 用途 |
| --- | --- |
| `scripts/build-xnu-4k-baseline.sh` | 内核构建（含 defconfig 重生成） |
| `scripts/k60-macos-preflight.sh` | 打核心补丁 + 装 auto-slide prelink wrapper |
| `scripts/emit_prelink_autoslide.py` | 装到 `kits/XnuPrelink/emit_prelink.py` 的包装器 |
| `scripts/k60-prelink-local.py` | 只跑 prelink，不需要 macOS |
| `scripts/k60-make-data-seed.py` | 造 Data 种子（**需要 macOS**） |
| `scripts/make-k60-gpt-data-image.py` | 裸 APFS → GPT 磁盘镜像 |
| `scripts/install-k60-ufs-data.py` | 把 Data 窗口写进 `unixnu`（支持 `--dry-run`） |
| `scripts/verify-k60-boot-img.sh` | boot v4 镜像独立校验（不依赖 `unixnu bootimg` 自带校验） |
| `scripts/sync-repos.sh` | 全部本地仓 fetch + 落后/领先报告，干净的仓可 ff-only |

## 构建

四个目录并列，核心仓用本仓的 `k60` 分支（已含 20G81 OS profile）：

```sh
git clone --recurse-submodules -b k60 https://github.com/Emilelu/UniXNU
git clone https://github.com/Emilelu/UniXNU-sm8475-common
git clone https://github.com/Emilelu/UniXNU-mondrian
git clone --recurse-submodules https://github.com/Emilelu/uefi-mondrian

cd UniXNU
../UniXNU-mondrian/scripts/k60-macos-preflight.sh      # 打核心补丁 + 装 auto-slide prelink wrapper
./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
./unixnu fetch -D ../UniXNU-mondrian
./unixnu status --json -D ../UniXNU-mondrian          # 三层 profile、组件、补丁顺序
./unixnu build kernel -D ../UniXNU-mondrian
```

`k60-macos-preflight.sh` 会写 `$GITHUB_ENV`（CI 用），本地跑时如果不在 GitHub Actions
里它会跳过那一行，其余步骤照常。它就把 `scripts/emit_prelink_autoslide.py` 装到
`kits/XnuPrelink/emit_prelink.py` 的位置。

**Linux（WSL）本地构建**：内核与 prelink 都不需要 macOS，工具链由
`scripts/linux/setup-toolchain.py` 提供；`unixnu fetch` 会自动取回 IPSW 里的
`kernelcache.decompressed`。只有 Data 种子（`k60-make-data-seed.py`）仍然依赖 macOS 的
`hdiutil`/`diskutil`。

没有 macOS 时，可以只把预链接单独跑：

```sh
python3 scripts/k60-prelink-local.py \
  --kernel mach.development.pong.unstripped \
  --prelinked out/ipsw/20G81/kernelcache.decompressed \
  --output kernel.macho
```

固件构建：

```sh
./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian
```

输出 `uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`。

## 数据安全

- bring-up 全程只用 `fastboot boot`（RAM 临时引导），**不 flash 任何分区**。
- XNU 的 root/Data 使用独立 `unixnu` 分区：SHNGROOT 里的 OS/SystemOS 窗口 + 尾部 Data 窗口，
  不写安卓 `userdata`；见 `docs/DUAL-SYSTEM.md`。
- **绝对禁止** `fastboot flash persist` / `flash all`（TEE 密钥永久损坏）。
- 写任何分区前先 `--dry-run` 确认几何，并备份 manifest。

## 已知技术债

- `boot-manifest-hash` 是板级事实，目前写在核心仓共享的
  `profiles/os/ipados-16.6.1-20G81/profile.toml` 里，正确位置应是本仓的 ADT 段。
- `patches/xnu/series` 尾部有 6 个纯编译环境补丁（`k60-cpp-void-ptr-assert`、
  `k60-v-crypto-syntax`、`k60-pgo-runtime-stub`、`k60-rwlock-caller-trace`、
  `k60-panic-report`、`k60-ppl-lock-sleepable`），每次升上游都要重打。
- 另有 22 个补丁未进 `series`，未评估。

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证，
见 `THIRD_PARTY_NOTICES.md`。
