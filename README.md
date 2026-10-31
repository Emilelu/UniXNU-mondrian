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

## 当前状态（2026-10-31 12:50）

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
| **用户态启动** | 🟡 | 进度条**会走一小段后停住**；5 秒统计**每窗恰好 2 帧**，窗口 24.9 s→5.6 s、每帧驱动 39.4 ms→2.6 ms、GPU 等待 0 µs ⇒ **卡在用户态，不是显示层**（见 [`docs/BOOT-STALL-2026-10-31.md`](docs/BOOT-STALL-2026-10-31.md)） |
| **用户态可观测性** | ✅ | 0235 v2：`KE` 按路径去重的完整二进制清单（≤128 行）/ `KX!` 只打异常退出 / `K60 ex= kx= abn=` + `K60 last exec:` + `K60 last bad :` 三行常驻末屏 |
| **ADT `/chosen` 身份** | 🟡 | `mac-address-wifi0` + `unique-chip-id` + `chip-id` 已进 ADT（字节校验通过），效果未上机确认 |
| **loader 内存与面板报数** | 🟡 | 0236 v2 打印 `K60 MEM:`（判定同族 0172 是否适用）与 `K60 FB :`（面板帧缓冲是否落在 VM 可管理区间内，判定同族 0170 是否适用）；`k60_capmanaged=1` 才启用上限收敛，默认关闭 |
| **GPU（Adreno 730）** | 🟡 | `PongAdreno` 驱动已 `force_load` 进内核（51 处符号），**未上机启动** |
| **IOMFB selector 兜底** | 🟡 | 0233 补丁已入 series（`GetGammaTable` 仍保持 unsupported），未上机 |
| 触摸 / 120 Hz / 音频 / 网络 / 相机 | ❌ | 未开始 |

## 当前卡点（2026-10-31 12:50）

1. **用户态启动在 UI 起来之后停住**（当前唯一硬阻断）。完整证据链见
   [`docs/BOOT-STALL-2026-10-31.md`](docs/BOOT-STALL-2026-10-31.md)，要点：
   - 进度条**会往前走一小段然后停住**。5 秒统计行是"打完即清零"的窗口量，
     实测连续六窗**每窗恰好 2 帧**，窗口长度单调变短（24895 / 10191 / 11968 / 12053 / 7319 / 5597 ms），
     每帧驱动耗时 39.4 ms → 2.6 ms，且 `waiting for the GPU = 0 us`、
     `0 swaps waited for the frame before / 0 gave up / 0 came a refresh late`
     ⇒ **帧缓冲与 GPU 路径不是瓶颈，是用户态在阻塞**（客户端"不怎么来要帧"）；
   - `report = fSwapsShown < 8`（`iokit/Kernel/MiniIOMobileFramebuffer.cpp:920`）：每 swap 的详细日志
     只在**头 8 帧**打印，"swap 行停在 8"是设计使然，**不能当卡死证据**；判存活要看 5 秒统计行；
   - 屏幕上的裸数字（如 `83`）**不是进度百分比**；进度条上方无 Apple logo 是引导方式的结果
     （走 UEFI + BootShim，无 iBoot 提供该位图）—— `[推断，未验证]`；
   - 控制台与 UI 抢同一块 framebuffer，控制台丢字（`xid`→`xld`、`surfaces`→`urfac s`），属观感问题；
   - 本轮已补三样：**0235 v2 用户态追踪**、**`/chosen` 三条身份**、
     **0236 内存报数**；下一步靠它们定位 frontier，再严格一次一个变量推进。
   - 首次上机（0235 v1）读到 `K60STAT execs=601 exits=400`，两个上限都被打满，
     所以只能当下界：**至少 601 次 exec、400 次退出**，`ex-kx ≈ 200` 个进程活着 ——
     这是相当正常的一支 iOS 守护进程 population，**不是"什么都起不来"，也不是"集体崩溃循环"**；
     卡点是某一个具体的等待没被满足。v2 的 `KE` 清单会直接回答
     `SpringBoard`/`backboardd`/`runningboardd`/`Setup` 有没有出现过。
   - 计数器是只增的 `unsigned int`，**代码上不可能倒退**；"看起来倒退"只有三种可能：
     滚动太快看错 / 控制台与 UI 抢 framebuffer 导致局部重绘 / **内核真的 panic 重启**。
     在拿到 v2 输出前不对这一点下结论。

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

## 同机先例（重要）

`refs/ios-sweet-k60/docs/LOCKSCREEN-2026-10-28.md` 记录**同一台 K60（mondrian，SM8475）
已经进过锁屏**（iOS 16.7.16，HFSX 可写根写在 `unidata` 之外的 `userdata`），判据是
"进度条走完后出现锁屏"。它给出的"CoreAnimation 一帧也不提交"的**四个必要条件**我们已逐条核对，
**四条全部满足**：

| 条件 | 我们 |
| --- | --- |
| 画布按面板原生 1440x3200 报 | ✅ `0210-k60-display-native-canvas`（实测 swap 已是 `1440x3200 BGRA`） |
| 发布 `TimingElements` / `ColorElements` | ✅ `MiniIOMobileFramebuffer.cpp:363-365` |
| `GetID == 1`，实现选择器 77 / 79（`GetBlock(0x40)`） | ✅ `kFBDisplayID 1`（`:320`）、`:1285`、`:1387` |
| 发布空的 `IOAcceleratorES` | ✅ `0212-k60-empty-accelerator`（`XNU_K60_ACCEL_STUB` 默认 1） |

⇒ **"缺渲染器/缺显示模式"可以排除。** 同族先例的完整修复菜单（24 条，带 file:line 引文）
见工作区 `k60-work/sweet-fix-menu.md`。

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
- **同族 0170 / 0172 不能直接打**：`0170-k60-panel-buffer-out-of-vm.patch`（`osfmk/vm/vm_resident.c`、`osfmk/vm/vm_shared_region.c`）
  与 `0172-k60-cap-managed-ram.patch`（`osfmk/arm64/arm_vm_init.c`）来自同族 K60 分支，
  本次实测 **`git apply --check` 与 `--3way` 都失败**；
  更要紧的是 **0172 的全部改动包在 `#if defined(ARM64_BOARD_CONFIG_SWEET)` 里**，
  即使强打上去，对 PONG 板也是**空操作** —— 要生效必须重写成 PONG 版。
  我们树上锚点位置一致（`arm_vm_init.c` 的 `mem_actual = ...` 之后），
  所以先由 0236 量出 `memSize` / `memSizeActual` 再决定是否写 `0236b`。
- `patches/xnu/series` 尾部有 6 个纯编译环境补丁（`k60-cpp-void-ptr-assert`、
  `k60-v-crypto-syntax`、`k60-pgo-runtime-stub`、`k60-rwlock-caller-trace`、
  `k60-panic-report`、`k60-ppl-lock-sleepable`），每次升上游都要重打。
- 另有 22 个补丁未进 `series`，未评估。

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证，
见 `THIRD_PARTY_NOTICES.md`。
