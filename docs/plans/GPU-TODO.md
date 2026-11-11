# GPU / Metal 待办（2026-11-12）

> 本文件记录 GPU 与 Metal 的移植欠账。每项都必须按八步流程走，
> 完成后在 `docs/research/EIGHT-STEPS.toml` 的 gpu 段更新证据。

## 现状（2026-11-12 实测）

| 组件 | 我们 | pong 最新 | 官方 AdrenoMetal | 差距 |
|---|---|---|---|---|
| `drivers/PongAdreno/PongAdrenoPlatform.cpp` | 26,279 B | 22,733 B | — | 我们多 3.5 KB（K60 RSC 直接映射 + 只映射已消费 GCC 页）|
| `drivers/PongMetal/NativeBridgeMetalFrontend.mm` | **109,178 B** | 166,152 B | **369,834 B** | **少 57 KB（vs pong）/ 260 KB（vs 官方）** |
| `NativeAdrenoMetalPlugin.mm` | 无 | — | 51,271 B | 缺 |
| `HostMetalCommandServer.mm` | 无 | — | 59,947 B | 缺 |
| `GpuScanoutPresenter.h` | 5,013 B | — | 12,636 B | 少 7.6 KB |

**内核侧我们比 pong 新；Metal 用户态严重落后。**

---

## 待办清单

### P0 —— 官方 AdrenoMetal 的性能优化（24 小时内 8 个提交）

官方仓库：`https://github.com/UniXNU/AdrenoMetal`
本地镜像：`references/AdrenoMetal`（main = `83b667824`）

**现查现取**（★37：不写死 SHA）：

```bash
cd /mnt/e/k60-work/references/AdrenoMetal && git fetch --all --prune
git log --oneline --since='3 days ago' origin/main
```

**要取的提交类型**（按提交信息里的前缀识别）：

| 前缀 | 内容 | 优先级 |
|---|---|---|
| `perf(bridge):` | 降低/提交/预热管线、放宽 half 运算 | P0 |
| `perf(turnip):` | Turnip 自选 pass 渲染、并发 binning | P0 |
| `perf(plugin):` | 每个 pass 在 tile memory 内渲染（省带宽）| P0 |
| `feat(diag):` / `fix(diag):` | 帧追踪、Turnip 日志导出 | P1 |

判断标准：改动集中在 `NativeAdrenoMetalPlugin.mm` 与 `bridge/NativeMetalObjects.rs`，
不含平台地址 → 可移植。

**做法**：这些改动集中在 `NativeAdrenoMetalPlugin.mm` 和 `bridge/NativeMetalObjects.rs`，
不含平台地址，**可移植**。但要先确认它们的 API 是 21H461 还是 20G81。

### P1 —— pong-metal 的中间层

pong-metal 的 `NativeBridgeMetalFrontend.mm` 是 166,152 B，比我们多 57 KB，
比官方少 204 KB。它是「官方 → 20G81 适配」的中间产物，**最贴近我们的版本**。

需要 diff 出 pong 比我们多的 57 KB 是什么。

### P2 —— 内核侧对齐 pong-adreno

pong-adreno 有 `port/ios18e-native-302` 分支（`5bc6f4cc2`，2026-11-11），
我们只跟到 `main`（`3e8ffa242`，2026-11-03）。

需要 diff `port/ios18e-native-302` 对 `PongAdrenoPlatform.cpp` 等的改动，
判断哪些是 22G100 专有、哪些是硬件修复。

### P3 —— 补齐官方缺失文件

```
NativeAdrenoMetalPlugin.mm     51,271 B
HostMetalCommandServer.mm      59,947 B
IOGPUMetalDeviceShim.h         13,746 B
GpuScanoutClient.h              7,956 B
CacheExport.h                  17,362 B
NativeMetalBridgePhase.h       10,579 B
```

先判断哪些是 20G81 必需、哪些是 21H461 专有。

---

## 关键约束

1. **`pong_metal=1` 时 backboardd 崩溃**（`-[NSURL fileURLWithPath:]` nil）。
   当前用 `pong_metal=2` 绕开，但那样 `IOAcceleratorES` 发布 0 次、`native Metal entry` 0 次。
   **这是 ⑦ 核验必须解决的前提。**

2. **20G81 vs 21H461 ABI 差异**。官方 `AdrenoMetal` 的 `os_abi` 是
   `ipados-17.7.11-21H461`，我们是 `ipados-16.6.1-20G81`。
   移植前必须核对 `_MTLDevice` ABI、`NativeAdrenoAbiVersion`、`chip_id`、`gmem_bytes`。

3. **`chip_id` 不同**。官方是 A740（SM8550），我们是 A730v3（`0x07030002`）。
   GPU 命令流可能有差异。

---

## 下一步（按八步流程）

① 同型：已完成（pong / 官方）
② 官方：已完成（unixnu.com/zh/porting/gpu）
③ 反编译：已完成（live FDT `0x07030002`）
④ 广域：**需补充** —— 把官方 AdrenoMetal 加入 `SOURCES.toml` 的 gpu 段
⑤ 方案：待写（本次待办就是方案输入）
⑥ 深挖：待做（diff 出具体差异）
⑦ 核验：待做（ABI 静态对照 + 产物检查）
⑧ 上机：待做（`pong_metal=1` 下验证）

**先做 ④**：把 `references/AdrenoMetal` 与 `references/pong-metal` 加进 SOURCES.toml。

---

## P-132：GPU 固件 `.cache/firmware/k60-gpu/` 丢失 —— **2026-11-12 已恢复**

**症状**：构建在 `build-pong-adreno-platform.py:64` 失败：
```
FileNotFoundError: /mnt/e/hackios/UniXNU-mondrian/.cache/firmware/k60-gpu/gmu_gen70000.bin
```

**需要五个文件**（`build-pong-adreno-platform.py:61-63`）：
```
gmu_gen70000.bin    → PongAdrenoGmuFirmware
a730_sqe.fw         → PongAdrenoSqeFirmware
a730_zap.mdt        → PongAdrenoZapMdt
a730_zap.b01        → PongAdrenoZapCode
a730_zap.b02        → PongAdrenoZapSignature
```

**原因**：cherry-pick yibiya 的 `fix(gpu): link actual scanout and mailbox`
时带入 `.gitignore` 的 `/.cache/`（他的本意是"本地捕获的固件不进 git"），
随后修 CRLF 时 `git checkout -- .` 不会恢复被忽略的文件，固件从磁盘消失。
git 历史里从未跟踪过它们。

**恢复方法**：从设备重新提取。这五个文件在 Android 的
`/vendor/firmware_mnt/image/` 与 `/vendor/firmware_mnt/image/a730/` 下。

**已恢复（2026-11-12）**：五个文件一直在 `/mnt/d/Android/k60-ios/firmware/k60-gpu/`，`porting.toml:248` 早就写着这个路径。已复制回 `.cache/firmware/k60-gpu/` 并设回 `CONFIG_XNU_PONG_ADRENO_PLATFORM=y`。构建产物 54,243,328 B，`libPongAdrenoPlatform.a` 406,464 B，GPU 符号全部在内核里。

**教训**：`/.cache/` 这类 gitignore 目录里放的是**构建必需品**时，
必须有独立备份，不能只依赖工作区文件。

---

## Mesa / Turnip 补丁的现状（2026-11-12 核查）

**结论：四个 mesa 补丁目前没有任何构建路径消费它们。**

| 补丁 | 谁应用 |
|---|---|
| `0001-pong-scoped-gpu-heap.patch` | `scripts/build-pong-turnip.py:29` |
| `0002-pong-allocation-pressure-reclaim.patch` | `scripts/build-pong-turnip.py:32` |
| `0003-pong-atomic-batches-and-fence-wait.patch` | **无** |
| `0004-pong-buffer-copy-allocation-errors.patch` | **无** |

而 `scripts/build-pong-turnip.py` **本身没有任何构建脚本调用**，且要求：
- `--mesa`（需已打上 UniXNU Darwin backend 补丁的 Mesa 源码）
- `--abi-directory`、`--tools-directory`、`--venv`、`--output-dir`
- `--developer-dir`，默认 `/Volumes/PongDev/.../Xcode.app`（仅 macOS）

内核产物里 `tu_knl` / `tu_device` 各 0 次出现，确认 Turnip 未进内核。

**因此上游新提交「turnip: keep the Vulkan device after a GPU restart」
虽然技术上可应用（它改 `tu_knl_darwin.cc` 第 1664-1690 行，我们的补丁改 77-1090
与 `tu_clear_blit.cc`，无行重叠），但它此刻不会进入任何产物 —— 先不引入。**

**解锁条件**：真正在 Linux 侧交叉构建 Turnip，或把 `build-pong-turnip.py`
接进 `build-xnu-4k-baseline.sh`。届时再一并评估该提交。

查询命令：`git -C references/UniXNU-upstream log --oneline --grep="keep the Vulkan device after a GPU restart"`

---

## GPU 的三个启动开关与字节预算（2026-11-12）

代码里有三个开关，**全部要求恰好等于 1**，缺一个对应环节就不执行：

| 开关 | 位置 | 作用 |
|---|---|---|
| `pong_adreno_start` | `PongAdrenoPlatform.cpp:479` | 启动 Adreno 平台（缺则什么都不做）|
| `pong_metal` | `PongAdrenoNativeGlue.cpp:30,44` | 发布 Metal accelerator（缺则按设计不发布）|
| `pong_gpu_scanout` | `PongAdrenoScanout.cpp:44` | GPU scanout（缺则用软件路径）|

**现状**：只有 `pong_adreno_start=1` 已加入（2026-11-12），另两个未设。

**字节预算**（arm64 boot-args 上限 608）：

```
当前 30 项，602 字节，余量 6
pong_metal=1        需 13 字节  -> 超限 7
pong_gpu_scanout=1  需 19 字节  -> 超限 14
```

要开 `pong_metal` 必须先腾空间。候选删除项：

- `k60_selftest_reboot=300`（23 B）—— 无人值守自检重启，手动测试时不需要
- `fb_threads=3`（12 B）—— 已 device-verified，但去掉可能影响显示性能

查询命令：`grep -n 'pong_adreno_start\|pong_metal\|pong_gpu_scanout' drivers/PongAdreno/*.cpp`
