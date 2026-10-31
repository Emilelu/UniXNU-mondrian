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

## 路线迁移：darwin22 → darwin24（2026-11-01）

**16.6.1 / 20G81 / darwin22 分支已关闭。** 该分支解决了所有影响启动的内核 panic
（8 核到 launchd、SpringBoard 拉起、`/private/var` 读写、keybag、watchdogd、进度条上屏），
但用户态 **sig=9 风暴**（约 98% 守护进程被 signal 9 杀掉）无法解决——
补丁 `0240`（无条件 Sandbox 策略）与 `0241`（`k60-no-lc=1`）都未能止住，故放弃。

现工作于 **darwin24（iPadOS 18.7.10 / 22H374 / xnu-11417.140.69）**，路线名 `route-a-18`，
依据是同为 SM8475 的 `UniXNU-pong`。当前进度：

| 项 | 状态 | 说明 |
| --- | --- | --- |
| darwin24 内核构建 | ✅ | Linux 全量构建，20,872,376 B，sha256 `2f485593…` |
| 平台层链接 | ✅ | `libArmDTPlatform.a`(27,808 B) + `libArmCpu.a`(34,600 B) 已 `force_load` |
| loader `boot_args` ABI | ✅ | 由 Darwin 22（`0x2e0`/608）修正为 Darwin 24（`0x480`/1024） |
| loader 跳板 | ✅ | 屏幕出现绿条，证明已跳入内核入口 PA `0xC74C04A0` |
| **内核早期启动** | 🔴 | 跳入后**静默复位**；观测盲区：ramoops 在 `arm_vm_init()` 之后才初始化 |
| FDT 契约 | 🟡 | 待查：打包的是原始 `hardware.dtb`（14 节点），缺 `/chosen` `/arm-io` `/defaults` `/options` |

完整交接见 **[`docs/ROUTE-A-18-HANDOFF-2026-11-01.md`](docs/ROUTE-A-18-HANDOFF-2026-11-01.md)**，
当前状态见 [`docs/ROUTE-A-18-STATE.md`](docs/ROUTE-A-18-STATE.md)。

---

## 当前状态（2026-10-31，Data ENOSPC 已证实）

> 以下状态表属 **darwin22（16.6.1）阶段的历史记录**，分支已关闭，仅作背景参考。



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
| `/private/var`（Data） | 🟡 | ENOSPC 已实测归因：256 MiB 容器被日志占满 97.6%（uuidtext/diagnostics 94%）；已安装 2045 MiB 新容器并读回校验（free blocks 为阈值 399 倍），旧卷已备份 PC；重启验证 pending |
| keybag / MKB | ✅ | ADT `/defaults/no-effaceable-storage` + 内核写明文 `systembag.kb` |
| watchdogd | ✅ | launchd disabled-jobs 策略禁用（core 补丁 0222） |
| SpringBoard 显示模式 | ✅ | ADT `display-scale = 3` |
| 控制台刷屏 | 🟡 | 已清空 resource-violation 三条格式串；0237 将 `K60WATCH` 周期探针改为默认不启动，`k60_watch=1` 才开启；`boot-nowatch.img` 已通过打包内容校验并由 fastboot 临时引导（exit=0），待屏幕确认 |
| **用户态启动** | 🟡 | 进度条到 ~1/3 后周期性回落；0235 v2 实测 98% 退出为 sig=9（tccd/timed/securityd/usermanagerd 成批）。根因已定位到源码级：`kern_minimac.c:371` 的 AMFI/Sandbox 替身策略被缺失的 boot-arg `amfi_get_out_of_my_way` 拦住，`__mac_syscall` 全部 ENOPOLICY(159)——与 sweet NOTES:91 记录的同名死亡路径一致（含 SpringBoard 的 work-interval）。详见 [`docs/DIAGNOSIS-SANDBOX-2026-10-31.md`](docs/DIAGNOSIS-SANDBOX-2026-10-31.md)；`boot-amfi.img` 已构建（唯一 delta = 该 boot-arg） |
| **用户态可观测性** | ✅ | 0235 v2：`KE` 按路径去重的 exec 尝试样本（≤128 行）/ `KX!` 只打异常退出 / `K60 ex= kx= abn=` + `K60 last exec:` + `K60 last bad :` 最近事件摘要（共享字段尚未同步） |
| **minimac 策略闸门** | 🟡 | 仓库自带 AMFI/Sandbox 替身（`kern_minimac.c`，含 container-path/priv 表/dyld policy），由 `amfi_get_out_of_my_way=1` 启用；此前所有镜像都没带这个参数，替身从未注册。`boot-amfi.img` 为打开后的第一颗 |
| **退出原因诊断** | 🟡 | 0238 在 `KX!` 记录 `r/ns/code/rf/jf`，另用 `K60XT` 覆盖无前置 BSD exit 的兜底路径；已构建并提取校验，尚未临时引导；`K60WATCH` 仍默认关闭 |
| **ADT `/chosen` 身份** | 🟡 | `mac-address-wifi0` + `unique-chip-id` + `chip-id` 已进 ADT（字节校验通过），效果未上机确认 |
| **loader 内存与面板报数** | 🟡 | 0236 v2 打印 `K60 MEM:`（判定同族 0172 是否适用）与 `K60 FB :`（面板帧缓冲是否落在 VM 可管理区间内，判定同族 0170 是否适用）；`k60_capmanaged=1` 才启用上限收敛，默认关闭 |
| **GPU（Adreno 730）** | 🟡 | `PongAdreno` 驱动已 `force_load` 进内核（51 处符号），**未上机启动** |
| **IOMFB selector 兜底** | 🟡 | 0233 补丁已入 series（`GetGammaTable` 仍保持 unsupported），未上机 |
| 触摸 / 120 Hz / 音频 / 网络 / 相机 | ❌ | 未开始 |

## 当前卡点（2026-10-31，先解决 Data 写入空间）

已确认一个必须先解决的存储阻断：`disk5s1 launchd/usermanagerd/logd_helper: ENOSPC`，
`free_blocks` 约 1208 低于 `threshold_blocks=1310`，APFS 拒绝 INSERT 写事务。
`xid` 增加不能当作写入成功或 UI 推进的证据。最近历史安装记录是 256 MiB APFS Data
（不是此前误认的 512 MiB），外层 32 GiB 仍有约 24.5 GiB 未分配给窗口；
“主要由日志写满”尚未统计证实。详见 [Data 容量与保留数据方案](docs/DATA-SPACE-2026-10-31.md)。

预案是在 unixnu 偏移 8 GiB 处放入扩大后的 22 GiB Data，保留旧卷，末尾留约 2 GiB。
须先 recovery 只读备份、在副本上用支持的 APFS 工具扩容并核验，不能靠改窗口长度或
替换空种子处理。当前 UFS Data 挂载分支另有 2 GiB 上限，部署前需单独验证解除。
**本次只新增只读采集/统计工具与文档，没有改写手机分区、窗口表或 APFS 容量。**

1. **用户态启动在 UI 起来之后停住**。完整证据链见
   [`docs/BOOT-STALL-2026-10-31.md`](docs/BOOT-STALL-2026-10-31.md)，要点：
   - 进度条**会往前走一小段然后停住**。5 秒统计行是"打完即清零"的窗口量，
     实测连续六窗**每窗恰好 2 帧**，窗口长度有波动、末窗短于首窗（24895 / 10191 / 11968 / 12053 / 7319 / 5597 ms），
     每帧驱动耗时 39.4 ms → 2.6 ms，且 `waiting for the GPU = 0 us`、
     `0 swaps waited for the frame before / 0 gave up / 0 came a refresh late`
     ⇒ 已计量的帧拷贝和 GPU 等待不足以解释帧间长停顿，优先检查用户态启动/退出原因；
   - `report = fSwapsShown < 8`（`iokit/Kernel/MiniIOMobileFramebuffer.cpp:920`）：每 swap 的详细日志
     只在**头 8 帧**打印，"swap 行停在 8"是设计使然，**不能当卡死证据**；判存活要看 5 秒统计行；
   - 屏幕上的裸数字（如 `83`）**不是进度百分比**；进度条上方无 Apple logo 是引导方式的结果
     （走 UEFI + BootShim，无 iBoot 提供该位图）—— `[推断，未验证]`；
   - 控制台与 UI 抢同一块 framebuffer，控制台丢字（`xid`→`xld`、`surfaces`→`urfac s`），属观感问题；
   - 本轮已补三样：**0235 v2 用户态追踪**、**`/chosen` 三条身份**、
     **0236 内存报数**；下一步靠它们定位 frontier，再严格一次一个变量推进。
   - 0235 v1 的 `execs=601 exits=400` 是两个封顶值，**不能相减推算存活进程数**。
      0235 v2 实测多支 daemon 为 `exit=0 sig=9`，`ex` 从 680 增至 707；能确认启动活动和
      SIGKILL 退出持续发生，尚不能确定是内存回收、用户态主动终止或其他终止路径。
   - 当前追踪使用无锁、非原子的全局计数和字符串，日志可能交错，`last bad` 各字段可能
      属于不同事件；`KE` 位于加载完成之前，`ex` 统计 exec 尝试，既不是成功启动数也不是
      进程数。因此不能用这些值认定计数倒退、重启、内存压力或卡死位置。
   - 0238 诊断镜像已记录内核提交的 `exit_reason`（namespace/code/flags）和 `jetsam_flags`，
     尚待上机；字段用于区分已记录原因，不等同于信号原始发送者。0238 与 0237 基线镜像的
     启动配置完全一致，保留默认关闭 K60WATCH 的行为。

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

这些已实现的服务和模式降低了该类缺项的优先级，但不能单靠代码存在排除渲染或 ABI 问题。同族先例的完整修复菜单（24 条，带 file:line 引文）
见工作区 `k60-work/sweet-fix-menu.md`。

## Fork 巡查与吸收（2026-10-31）

按用户要求，开发期间及推送前检查公开 fork；本会话另设每 6 小时一次的巡查提醒。
`python3 scripts/audit-forks.py --output /tmp/mondrian-forks.json` 枚举所有 fork/分支并固定
比较 SHA，只读报告候选，不自动合并。首次检查为 3 个 fork / 4 个分支 / 11 个历史独有提交，
完整取舍和来源见 [docs/FORK-REVIEW.md](docs/FORK-REVIEW.md)。

已吸收并验证：

- `mzyxsl/daed6b5` 完整 cherry-pick 为 `acb5c2d`，修复本地 prelink 从 OS profile 读取参数；
  trust-cache 数组与 lock pin 是规范化/一致性改动，不宣称它们此前阻止所有 payload 构建。
  实际运行 prelink 通过，32 roots、slide `-0xb9c000`，输出与本轮原 prelink 内核逐字节一致。
  非并列目录可用 `--profile` 和 `--kit` 显式指定。
- 从 `mzyxsl/76552b8` 选择性导入离线适配记录检查器；整理现有路径归属，保留当前硬件验证等级。
  `python3 scripts/check-porting-paths.py` 已通过。它只做离线预检，不替代框架官方检查器或设备验证。
- 从 `XTOM0706/9d1a14f` 只移植设备级 `display-scale=3`；与当前 profile 一致，
  ADT 生成/解析比较仅随机种子不同。未带入额外显示节点或未经目标验证的 ramoops magic。

菜单倒计时已有等效补丁，不重复；另一台 16 GiB 手机的内存窗口和旧 Data UUID 不用于当前
12 GiB 设备。没有因 fork 改变当前已构建诊断镜像的启动参数、内存或根文件系统。

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
| `scripts/inspect-k60-data.py` | 只读采集 recovery 的 unixnu/Data 备份、核验 SHNGROOT/GPT/APFS 容量，`--usage` 在本地统计目录元数据 |
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
  --profile profiles/os/ipados-16.6.1-20G81/profile.toml \
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
