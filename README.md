# UniXNU-mondrian

Redmi K60（**mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。格式 2 设备仓：
`board.toml` 的 `schema_version = 2`，配置按 ARM64 → SoC → OS → 设备四层合并，
输出到 `out/mondrian/ipados-16.6.1-20G81/mondrian/`。

## 当前状态（2026-11-07）

**iOS 16.6.1（20G81）已启动到用户态首帧。**

- 启动链完整：XNU → `launchd` → SpringBoard / backboardd / containermanagerd / mediaserverd。
- 显示：`K60 DISPLAY: first frame presented (swap 1, 1440x3200 canvas on 1440x3200 panel)`，
  之后 `MiniIOMobileFramebuffer` 稳定 60 fps。屏幕上可见 iOS 启动进度条。
- 内省：`K60PANICFMT`（panic 格式串+caller）、`K60KEXC`（pid/pc/lr/esr/far）、
  `K60KFRAME`（帧指针回溯）、`K60NULLENTRY`（无 ExpansionData 的 IORegistryEntry）。
- **唯一阻塞**：`launchd`（pid 1）收到 SIGSEGV（`KX! 50 1 launchd ... sig=11 code=0xb`），
  XNU 依设计因 `pid 1 exited` panic 并复位，进度条从头再来。崩溃地址尚未抓到。

### 可用镜像

| 镜像 | 说明 |
| --- | --- |
| `boot-0408-20261107.img` | 首帧 + SpringBoard 存活 |
| `boot-0409-20261107.img` | 同上，`k60_textonly=0` |
| `boot-0410-20261107.img` | 首帧后停止 framebuffer 文字，屏幕只留 iOS UI |

### 两条硬约束

1. payload 的 boot-arg **不得超过 600 字符**：boot.img 内预编译的 UniXNU 加载器超限直接返回
   `Bad Buffer Size`，内核零启动（见 `docs/PITFALLS-FROM-HISTORY.md` #124）。
2. payload FAT 用已验证基座组装；内核体积随补丁增长时，组装器需扩展簇链并做读回校验。

## 结构

| 路径 | 内容 |
| --- | --- |
| `porting.toml` | 各子系统的输入、发现、证据与完成判据（权威设备记录） |
| `board.toml` / `configs/` / `dts/` | 设备配置、内核 defconfig、内存与 CPU 选择 |
| `patches/xnu/series` | 16.6.1 补丁序列（182 项） |
| `userland/` | `init`、UI 兼容库（`libpong-ui.dylib`）源码 |
| `scripts/` | 构建、prelink、镜像校验与安装工具 |
| `docs/` | 坑表、路线与取证记录 |

`AGENTS.md` 是作业说明：必读文档、先调研再写代码、分支与提交规范、设备红线。

## 四层仓库

| 层 | 仓库 | 内容 |
| --- | --- | --- |
| 框架 | [Emilelu/UniXNU](https://github.com/Emilelu/UniXNU)（分支 `k60`） | `unixnu` 命令、共享脚本、ARM64 与 OS profile、组件目录 |
| SoC | [Emilelu/UniXNU-sm8475-common](https://github.com/Emilelu/UniXNU-sm8475-common) | `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi` |
| 设备 | 本仓库 | `board.toml`、`dts/mondrian.dts`、`patches/xnu/series`、`userland/`、`porting.toml` |
| 固件 | [Emilelu/uefi-mondrian](https://github.com/Emilelu/uefi-mondrian) | EDK2 / Mu-Silicium 构建树，产出 `SILICIUM_UEFI.fd` |

迁移与证据记录见 `porting.toml`；它同时是 [unixnu.com/zh/devices/mondrian](https://unixnu.com/zh/devices/mondrian) 的数据源。

## 构建

```sh
git clone --recurse-submodules -b k60 https://github.com/Emilelu/UniXNU
git clone https://github.com/Emilelu/UniXNU-sm8475-common
git clone https://github.com/Emilelu/UniXNU-mondrian

cd UniXNU
../UniXNU-mondrian/scripts/k60-macos-preflight.sh
./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
./unixnu fetch -D ../UniXNU-mondrian
./unixnu build kernel -D ../UniXNU-mondrian
```

Linux（WSL）本地构建不需要 macOS：工具链由 `scripts/linux/setup-toolchain.py` 提供，
`unixnu fetch` 会自动取回 IPSW 的 `kernelcache.decompressed`。只有 Data 种子
（`k60-make-data-seed.py`）仍依赖 macOS 的 `hdiutil`/`diskutil`。

只跑 prelink：

```sh
python3 scripts/k60-prelink-local.py \
  --kernel mach.development.pong.unstripped \
  --prelinked out/ipsw/20G81/kernelcache.decompressed \
  --profile profiles/os/ipados-16.6.1-20G81/profile.toml \
  --output kernel.macho
```

固件：`./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian`，
输出 `uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`。

## 数据安全

bring-up 全程只用 `fastboot boot`（RAM 临时引导），不 flash 任何分区，不写 `persist`，
不跑 `flash all`。Data 走独立的 `unixnu` 分区（双系统）。

## 许可

设备级代码 BSD-2-Clause-Patent；导入组件保留各自 SPDX 标记，见 `THIRD_PARTY_NOTICES.md`。
