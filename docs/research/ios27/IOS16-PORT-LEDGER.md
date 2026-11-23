# iOS16 → iOS27 移植账本

## 241 个无法直接应用的补丁的分类

基线：`patches/xnu/` 共 276 个补丁。对 27 线组装树 `xnu-work`（xnu-12377.121.6，`patches/xnu-12377/series` 已应用）执行 `git apply --check`，35 个通过，241 个失败。下表对 241 个失败补丁逐个归类；判定只做静态补丁分析，没有构建，也没有上机。

| 类别 | 含义 | 数量 |
|---|---|---:|
| A `anchor-drift` | 目标文件存在，只是行号/上下文漂移，可重切 | 35 |
| B `missing-file` | 目标文件在 27 树不存在 | 61 |
| C `pong-only` | 被 `#if defined(PONG)` / PONG 板级配置包住；27 是 BCM2837，`-DPONG` 恒 0 | 16 |
| D `sixteen-only` | 依赖 16 线专有结构或符号（`io_submap`、`IO_MAP_SIZE`、PongAdreno、`pong_ramoops` API、`/private/var/pong` 等） | 21 |
| E `duplicate` | 与 0561-0575 或 27 现有补丁实质重复，或已经在 27 树中应用 | 68 |
| F `trivial-log` | 只加日志/追踪/诊断探针，无生产功能变更 | 40 |
| **合计** | | **241** |

### A 类主题分布

| 主题 | 数量 |
|---|---:|
| console | 0 |
| display | 0 |
| boot | 18 |
| power | 2 |
| ufs | 0 |
| other | 15 |

A 类中 easy 23 条、medium 12 条；hard 未出现（44 hunk 的 `ios16-clang-uio-driverkit-compat.patch` 是一次机械替换，按 medium 计）。

### 建议优先移植（≤10 条，只列 console/display/boot 相关且 A 类 easy）

| 序号 | 补丁 | 目标文件 | hunks | 理由 |
|---:|---|---|---:|---|
| 1 | `0218-k60-data-keybag-file.patch` | `bsd/kern/kern_exec.c` | 1 | 写入 `/private/var/keybags/systembag.kb`，让用户态 keybag 可用；锚点 `if (actual != device ||` 在 27 的 `native_owner_data_mount` 中（`bsd/kern/kern_exec.c:9044`） |
| 2 | `0222-k60-disable-watchdogd.patch` | `bsd/kern/kern_exec.c` | 1 | 写 `com.apple.watchdogd` 的 disabled.plist，避免 watchdogd 拉起即崩；同一 1-hunk 插入点 |
| 3 | `0234-k60-seed-boot-preferences.patch` | `bsd/kern/kern_exec.c` | 1 | 预置 SpringBoard/PurpleBuddy 偏好，减少首启卡在设置向导；同一 1-hunk 插入点 |
| 4 | `0242-k60-entitlements-include-shim.patch` | `bsd/kern/kern_exec.c` | 3 | 把 CodeSignature 头替换为 CoreEntitlements 兼容 shim，并给 `init_programs` 加 `!defined(PONG)` 守卫 |
| 5 | `0310-k60-amfi-keep-first.patch` | `libkern/amfi/amfi.c` | 1 | AMFI 接口重复注册时保留第一份而不是 panic；锚点 `amfi_interface_register` |
| 6 | `0327-k60-persona-proxy-bootstrap.patch` | `bsd/kern/kern_persona.c`;`bsd/kern/bsd_init.c` | 2 | 创建 k60-sys/k60-mobile persona 代理，解决 launchd 早期 persona 查询 |
| 7 | `0332-k60-skip-prelinked-load.patch` | `libkern/c++/OSKext.cpp` | 3 | 允许跳过指定预链接 kext 的 C++ 初始化，绕过 16 线遗留 prelinked 项 |
| 8 | `architectural-timer-entry.patch` | `osfmk/arm64/start.s` | 1 | 让 BCM2837 的 architectural timer 可被 `XNU_NATIVE_ARCH_TIMER` 关闭 |
| 9 | `native-trust-cache-runtime.patch` | `osfmk/kern/startup.c` | 1 | 给 trust cache runtime 初始化加原生开关，boot 早期路径 |
| 10 | `zzzzzz-pong-init-scratch-allocation.patch` | `bsd/kern/kern_exec.c` | 1 | 按 27 的 `native_owner_data_mount` scratch 页大小分配，避免 16K/4K 启动参数错配 |

### 其他类别摘要

- **B（61）**：涉及 35 个 27 树不存在的路径。主要缺口是 16 线的 Mini* 显示/iOSurface/KeyStore 栈（`MiniIOMobileFramebuffer.cpp` 17 个补丁、`MiniIOSurface.cpp` 11 个、`MiniAppleKeyStore.cpp` 4 个），以及 `pong_goodix.c`（11）、`kern_minimac.c`（5）、`pong_input.c`、`pong_userland.c`、`pong_handoff.*`、`pong_thermal*`、16 线启动 blob 头文件等。缺失文件无法靠重切解决。
- **C（16）**：`0236`、`0306`、`0314` 及 13 个 `pong-*` 补丁。共同点是整段功能代码位于 `#if defined(PONG)`、`defined(ARM64_BOARD_CONFIG_PONG)` 或 PONG 专有配置内；27 的机器配置只有 `MASTER.arm64.bcm2837`，`-DPONG` 恒 0。
- **D（21）**：依赖 16 线结构而非单纯锚点漂移。代表符号：`pong_ramoops_snapshot`（0331/0333/0338）、`PongAdrenoMetal`（0404/0610）、`pong_audio_bootstrap`（0505）、`IO_MAP_SIZE`/`io_submap`（0621）、`native_pong_ufs_data_volume_device`（offline-owner-systemos-mount）、`/private/var/pong`（0398/0618）。
- **E（68）**：29 条 `git apply --reverse --check` 直接通过（完全已应用）；显式从 16 线移植到 27 的补丁包括 `0214→0544`、`0243→0548`、`0300→0547`、`0308→0549`、`0334b→0550`、`zzzzz-pong-ramoops-minimal→0546`、`pong-cpu-start→0532`、`pong-psci-smp→0540`、`zzzz-pong-virtual-timer→0541`、`zzx-pmap-sync→0573`、`native-4k-bootstrap-capacity→0574`、`k60-v-crypto→0533`；`0500`/`0502b` 与 27 文件同字节。其余是 27 已实现等价功能（如 `native-4k-user-abi`、`native-4k-signature-hash-cache`、`zzy-native-gpu-addon-mount`、`zzz-boot-progress`）。
- **F（40）**：日志/追踪/探针类，例如 `0303` heartbeat、`0321`-`0326` 探针、`0346` userexc trace、`0354` panic backtrace、`0386` quiet exec probes、`0629` sleep trace；不改变生产返回值或状态机。

### 复现

逐补丁 TSV 为工作区 `E:/k60-work/scratch/ios16-anchor-report.tsv`（241 行，列 `patch category target_file hunks difficulty note`），每行 `note` 带可复现的 `grep`/`test`/`git apply --reverse --check` 命令。生成器为同目录 `ios16_classify.py`，原始解析记录为 `ios16-facts.json`。所有检查以 27 树 `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work`（commit `ac9718f`）或仓库根目录为工作目录。
