# 显示栈缺口：我们缺的是整个 `GopFramebuffer` 组件（不是一行 console 补丁）

日期：2026-11-23 · 状态：证据已闭合，待实施（冻结期只做离线改动） · 关联：`LOG-CHANNEL-PRECEDENTS.md`、`IOS27-FLIGHT-BLOCKERS.toml`

## 1. 结论

27 线上「内核文本控制台写不进面板 / 只有洋红条带」不是某一处映射写错，而是**我们根本没有显示驱动组件**。

- 我们的 27 profile：`board.toml:364` 的 `include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink"]` —— 没有 `GopFramebuffer`，仓库里也没有 `drivers/GopFramebuffer`、`scripts/build-gop-legacy-display*.py`。
- 能进系统的 sheng（同 `ipados-27.0.1-24A446`、同 arm64e）：`UniXNU-sheng/board.toml:117/174/194` 的 include 都含 `GopFramebuffer`，`:20` 的 archives 含 `build-gop-legacy-display-27.py`，`:66` 的 kernel_args 带 `offline-legacy-gop=1`、`sheng-fb-gpu=1`、`sheng-dpu-scanout=2`、`sheng-fb-bgra=1`。
- 组件目录明确把它标成 27 可用且已在 sheng 验证：`E:/hackios/UniXNU/components.toml:206-225`，`os_abi = ["ipados-17.7.11-21H461", "ipados-27.0.1-24A446"]`、`verified_devices = ["sheng"]`、`source_files = ["NativeMobileDisplay.cpp", "NativeLegacyDisplay.cpp"]`、`outputs = ["build/gop-framebuffer/libGopFramebuffer.a", "build/gop-framebuffer/libGopFramebuffer.late.a"]`。

没有这个组件，内核里就没有任何 `IOFramebuffer` / `IOMobileFramebuffer` 实现，PE 文本控制台直接写物理帧缓冲是唯一输出路径；而 iOS 27 的 WindowServer 要求存在 framebuffer provider 才会出画面 —— 所以即使 stage-0 走通，也仍然是黑屏。

## 2. 组件能做什么（读 `E:/k60-work/references/GopFramebuffer` 源码）

克隆：`https://github.com/UniXNU/GopFramebuffer.git`（catalog 固定 `revision = e47c1b8de169cd2bd0b885c7d85e433010e3cdf2`）。

- `README.md`：CPU 与 GPU scanout 都支持；`vsync=<Hz>` 时工作循环定时器向 compositor 发 vsync 消息；swap 携带整屏 surface（BGRA / 单平面压缩拼写 / half-float RGBA）；`dpu-scanout=2` 时由显示 pipe 自己取 8-bit surface；half-float 不能直取时 `fb-gpu=1` 由 GPU 客户端转换，否则 CPU 转换。
- `NativeGOPPresenter.cpp:2`：「Transfer completed GPU pixels to actual firmware scanout. No CPU rendering」——即真正把合成结果写进 **firmware 的 scanout**（GOP 帧缓冲），正是我们缺的那一层。
- `NativeLegacyDisplay.cpp:108` 注释：「that subclass is not part of this port: without it the render server never saw a vsync」⇒ 组件本身只有 Modern 路径，**Legacy 子类要设备仓自己构建**，这就是 sheng 的 `build-gop-legacy-display-27.py` 存在的原因。
- `NativeLegacyDisplay.cpp:282`：「DPU 9.2 inside the MDP block (0xae01000): VIG 0 and 1 at 0x4000 and 0x6000」——这是 **SM8550** 的 DPU 基址；K60 是 SM8475，`dpu-scanout` 不能照抄，第一期必须走 CPU 拷贝路径（`dpu-scanout=0`、`fb-gpu=0`）。

## 3. sheng 的 Legacy 构建器（必须移植的部分）

`UniXNU-sheng/scripts/build-gop-legacy-display-27.py` 头注释逐字要点：

- 「Bind the owned GOP backend to the original IOMobileFramebufferLegacy of the iPadOS 27 (24A446) fileset.」
- ABI（vtable 目标与 diversity、实例大小、字段偏移、原始绑定）来自复核过的 fixture `legacy-display-24A446.json`。
- 内核是 arm64e：owned 子类的每个 vtable 项必须带原始调用者认证的 diversity，所以每个原槽按「以该槽 diversity 为 discriminator 的名字」声明；原代码按 fileset 地址 + collection slide 绑定，不改任何原始指令或 vtable。
- 脚本开头硬校验 `ARCH == 'arm64e' and IOS_VERSION.split('.')[0] == '27'`，否则 `SystemExit`。

⇒ 这份 builder + fixture 是**OS 版本相关、SoC 无关**的，可原样移植到我们的 27 线（前提是我们的 kernel_target 也报 arm64e/27，已是事实）。

## 4. 移植清单（按依赖顺序）

1. `board.toml` 27 profile：include 增加 `GopFramebuffer`；archives 增加 `build-gop-legacy-display-27.py`（与 sheng `board.toml:20` 同形），保留我们已有的 `build-k60-platform-archives.py`、`k60-fileset-stamp.py`。
2. 从 sheng 复制 `scripts/build-gop-legacy-display-27.py` 与 `scripts/legacy-display-24A446.json` 到本仓 `scripts/`，只改路径/模块名前缀，不改 ABI 常量；在 `PRECEDENT-MANIFEST.toml` 记 `copied`（源仓 `UniXNU-sheng`、源文件、sha256）。
3. kernel args（第一批保守值）：`offline-legacy-gop=1`、`vsync=60`、`fb-gpu=0`、`dpu-scanout=0`、`fb-half=1`；**不**带 `sheng-dpu-scanout=2`（SM8550 专有地址）。
4. 保留 `0543`（PE 文本控制台）与 `0577`（`video_console.c` 的 PONG 门）作为 stage-0 的早期诊断通道；等 GopFramebuffer 起来后由它接管画面。
5. 门禁：`check-series-order.py` 必须仍 129/0；`check-driver-arch.py` 新增一条 `display-27: GopFramebuffer included`；`check-ios27-artifacts.py --flight-ready` 的 `prelink-map-unresolved` 不因这次改动变化（组件是 archive，不引入 prelink root）。

## 5. 为什么这不是「猜」

三条独立证据指向同一结论：

1. 组件目录把 `ipados-27.0.1-24A446` 列为 `os_abi`，`verified_devices = ["sheng"]`（同一 OS 版本、同一 arm64e 内核）。
2. sheng 的 27 段实际 include 了它、并且额外构建 Legacy 子类；它的 `offline-legacy-gop=1` 就在 `kernel_args` 里，是它进系统的既有配置。
3. 组件源码自己说明「没有 Legacy 子类，render server 永远看不到 vsync」——这与我们「内核跑起来也没有任何 framebuffer provider」的现象一致。

## 6. 未决与风险

- `dpu-scanout=2` 的 DPU 基址是 SM8550 的 `0xae01000`，K60 必须先用 CPU 路径；DPU 直取留到显示线单独立项（需要先读 SM8475 的 MDP/DPU 基址与 VIG 偏移）。
- Legacy fixture `legacy-display-24A446.json` 的 vtable slot/diversity 必须与**我们构建的 24A446 fileset** 同源；若 sheng 的 fixture 基于不同的 collection slide，需要按我们的 kernelcache 重新核（脚本只用相对 slide，风险可控，但必须跑 `check-prelink-hazards.py`）。
- 移植后第一次上机仍需用户批准；本文件不授权构建或上机。

## 7. 逐行读 sheng 构建器后的修正（2026-11-23 晚）

`sheng/scripts/build-gop-legacy-display-27.py` 不是「显示构建器」，是 sheng 的**整板驱动合并归档器**：末尾 `archive = OUT / 'libNativeLegacyDisplay.late.a'`，`xcrun ar rcs` 把 `NativeLegacyDisplay` + `NativeGOPPresenter` + `KeyStoreProbe` + 键鼠（`kits/Wn8030.c`、`GeniI2c.c`、KeyboardCover/KeyboardProbe）+ USB（`drivers/QcomDwc3`、`usb-xdci-24A446.json`）+ 蓝牙探针全部塞进一个 `.late.a`；还依赖 `kits/Sm8550Platform`（SM8550 专用头）与 `drivers/AppleKeyStoreState`。⇒ **不能整支拷**，只能抽 `NativeLegacyDisplay` + `NativeGOPPresenter` + `original-bindings/original-addresses` 生成逻辑 + ABI fixture 这四块。

两个未知已查清（机制在 `scripts/build-xnu-generic.sh`，不是 `board.toml`）：

1. **归档怎么进内核链接**：`scripts/build-xnu-generic.sh:371/376` 读 `XNU_NATIVE_MOBILE_DISPLAY` / `XNU_NATIVE_LEGACY_DISPLAY`（由 defconfig 的 `CONFIG_XNU_NATIVE_*` 转成环境变量）。`:661-671` 在 `NATIVE_MOBILE_DISPLAY=1` 时 `-force_load $ROOT/build/gop-framebuffer/libGopFramebuffer.late.a`，并先核 `build-report.json` 的 `archive_sha256`；`:675-687` 在 `NATIVE_LEGACY_DISPLAY=1` 时 `-force_load $ROOT/build/native-legacy-display/libNativeLegacyDisplay.late.a`，除 `archive_sha256` 外还逐条核 `source_sha256`（改任何一个源都必须重建）。⇒ sheng 的 `build-gop-legacy-display-27.py` 输出路径正好对上，这就是它的挂接方式。
2. **开关现状**：`configs/mondrian_ios27_defconfig:22 CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n`，`UniXNU-sheng/configs/sheng_ipados27_defconfig:21 = y`。`build-xnu-generic.sh:370` 还把它作为 `-DXNU_NATIVE_LEGACY_DISPLAY=${...}` 传给 `bsd_init.o`，`:381` 传给 `IOUserClient.cpo` — 说明内核源码里已有该宏的调用点（我们只是关着）。
3. **`kernel_target` 从哪来**：sheng `scripts/` 下没有，框架 `UniXNU/scripts/kernel_target.py` 有，装配时拷进树 `scripts/`（`/opt/k60/trees/ios27-out/.../tree/scripts/kernel_target.py` 实测存在）⇒ 我们的构建器同样可用，无需自造。

因此最小可行移植 = ①`configs/mondrian_ios27_defconfig` 打开 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y`（`CONFIG_XNU_NATIVE_MOBILE_DISPLAY` 视组件是否提供 Modern 归档再定）；②造出 `build/native-legacy-display/libNativeLegacyDisplay.late.a` + `build-report.json`（从 sheng 的 builder 抽出显示四块）；③kernel args 打开 `offline-legacy-gop=1`。在此之前**不动 `board.toml` 的 include**，也不改 defconfig：归档不存在时链接直接 `test -f` 失败，属于可预见的红。
