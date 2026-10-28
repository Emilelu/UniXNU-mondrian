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

## 当前状态（2026-10-28）

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UEFI 启动链 | ✅ | ABL -> `fastboot boot` -> BootShim -> UEFI -> UniXNU 菜单 |
| 显示 | ✅ | ABL splash framebuffer + SimpleFbDxe GOP；无 GPU 加速 |
| 实体按键 | ✅ | 官方 KeypadDevice 链 + `K60KeypadDeviceLib`（SPMI PON/GPIO） |
| Tools -> Advanced Logger | ✅ | 4 MB Advanced Logger + QR 序列帧，OneSend 可抓 DXE 全量日志 |
| XNU 内核 | ✅ | macOS CI 编译 + prelink 通过：`kernel.macho` 54,349,824 B，prelink slide `-0xb9c000` |
| 板级 ADT / payload / bootimg | ❌ | DTS 已就位并通过 `dtc`，payload 与启动镜像尚未打包 |
| 触摸 / GPU / 音频 / 网络 / 相机 | ❌ | 未开始 |
| UFS / Data / root | ❌ | 规划使用独立 `unixnu` 分区（双系统），不动安卓 `userdata` |

已实测的硬件事实：DRAM **12 GiB** @ `0x80000000`（`swinfo.fingerprint=mondrian:12`）、
GIC `0x17100000` / `0x17180000`、8 核 `reg = 0x000..0x700`、面板 `m11a_42_02_0a`。
换一台不同容量的机器时，需要同步改 `dts/mondrian.dts` 的 `/memory` 与
`board.toml [payload] dram_size`。

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

没有 macOS 时，可以只把预链接单独跑：**`kernel.macho` 的生成需要 macOS 上的 XNU 编译**，
但拿到 `mach.development.pong.unstripped` 之后，prelink 是纯 Python：

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

- 当前 bring-up 只用 `fastboot boot`（RAM 临时引导），不写任何分区；安卓
  `/data`、system、persist 均不动。
- 后续 XNU root/Data 使用**独立 `unixnu` 分区**（双系统方案：缩 F2FS +
  尾部新建分区），不写安卓 `userdata`；见 `docs/DUAL-SYSTEM.md`。
- **绝对禁止** `fastboot flash persist` / `flash all`（TEE 密钥永久损坏）。
- 写任何分区前先备份并确认目标；默认构建命令可能仍指向安卓 `userdata`。

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证，
见 `THIRD_PARTY_NOTICES.md`。
