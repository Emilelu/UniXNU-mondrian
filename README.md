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

## 当前状态（2026-10-31 10:00）

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UEFI 启动链 | ✅ | ABL -> `fastboot boot` -> BootShim -> UEFI -> UniXNU 菜单 |
| 显示（软件） | ✅ | MiniIOMobileFramebuffer 纯 CPU 缩放 + memcpy，1440x3200 上屏 |
| 实体按键 | ✅ | 官方 KeypadDevice 链 + `K60KeypadDeviceLib`（SPMI PON/GPIO） |
| XNU 内核启动 | ✅ | 8 核；AppleARMCPU `_validateConfiguration` 已二进制打补丁 |
| **内核源码构建（WSL）** | ✅ | MIGCC/MIGCOM/HOST_CC 修复后可全量构建，见下节 |
| **平台驱动链接** | ✅ | `ArmDTPlatform`/`ArmCpu`/`NativeUfs` 已 `force_load` 进内核 |
| **控制台字体放大** | ✅ | `k60_fontscale=3` 生效，日志在 1440x3200 上可读（0214 溢出已修） |
| UFS root（SHNGROOT） | ✅ | OS / SystemOS 两个只读窗口，union 挂到 `/` |
| `/private/var`（Data） | ✅ | 真实 UFS Data 窗口读写挂载 |
| keybag / MKB | ✅ | ADT `/defaults/no-effaceable-storage` + 内核写明文 `systembag.kb` |
| watchdogd | ✅ | launchd disabled-jobs 策略禁用（core 补丁 0222） |
| SpringBoard 显示模式 | ✅ | ADT `display-scale = 3` |
| 控制台刷屏 | ✅ | `send_resource_violation` 三条格式串清空 |
| **用户态启动** | 🟡 | 跑到 APFS 事务刷盘（`tx_flush` 无等待），**但 UI 未起、无启动进度条** |
| **GPU（Adreno 730）** | 🟡 | `PongAdreno` 驱动已 `force_load` 进内核（51 处符号），**未上机启动** |
| **IOMFB selector 兜底** | 🟡 | 0233 补丁已入 series（`GetGammaTable` 仍保持 unsupported），未上机 |
| 触摸 / 120 Hz / 音频 / 网络 / 相机 | ❌ | 未开始 |

## 当前卡点（2026-10-31 10:00）

1. **用户态 UI 未启动**（当前唯一硬阻断）。内核已跑过 APFS 事务阶段
   （最后一行 `tx_flush:1241: disk5 xid 1582 tx stats: ... wait 0 0us flush 4267us`，
   说明 APFS 无阻塞），screen 上没有出现启动进度条，console 仍持有输出权
   （`gc_pause` 未触发）——即卡在 launchd 的某个早期 job，**比"进度条停滞"更早**。
   待办：抓到该 job 名。
2. **内核源码构建已修复**（本节从"不可用"转为已解决，保留原因备查）：
   - `'stdio.h' file not found` → `HOST_CC` 指向 `xnu-host-cc`；
   - `mig: line 183: command not found` 真因不是 `MIGCC` 而是 **`MIGCOM`**：
     `xcrun -find migcom` 只搜 `usr/bin`，而 `migcom` 在 `usr/libexec`，
     于是 `export MIGCOM := $(shell ...)` 被设成空串，mig 的
     `M=${MIGCOM-${migcomPath}}` 用 `${VAR-default}` 不兜底 → 管道变空命令。
     修复见 `scripts/unixnu/kernel.py` 的 `linux_env()`。
   - **平台库漏链接**：`kernel.py` 找不到 `startup.o.json`（路径硬编码
     `DEVELOPMENT_ARM64_BCM2837`，PONG 板永不命中），导致**每次构建都跑
     bootstrap pass**；该 pass 带 `XNU_BOOTSTRAP=1`，会跳过
     `build-xnu-4k-baseline.sh` 里负责 `-force_load` 平台库的那一段，却仍执行
     完整 `build` target 把内核链接掉。正式 pass 变量虽对，但 make 不追踪
     命令行变量变化 → 不重链 → 内核里缺 `ArmDTPlatform`/`ArmCpu`/`NativeUfs`，
     运行时由 score=0 的 `IOPanicPlatform` 兜底并 panic
     `Unable to find driver for this platform "J120AP"`。
     修复：`scripts/build-xnu-4k-baseline.sh` 在正式 pass 的 make 之前清掉
     链接产物，强制重链。
3. **换文件系统有前置条件**：20G81 的 kernelcache 里有 `com.apple.filesystems.hfs`
   与 `com.apple.filesystems.tmpfs`，但本仓库的 prelink 根列表里一个都没有，
   所以 `mount("hfs")` / `mount("tmpfs")` 现在必然 `ENODEV`。

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
| `scripts/build-pong-adreno-platform-linux.py` | 在 WSL 上产出 `libPongAdrenoPlatform.a`（macOS 版的 Linux 移植） |
| `scripts/build-xnu-4k-baseline.sh` | 内核构建驱动脚本（设备仓版优先于框架仓版；已含强制重链修复） |
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
