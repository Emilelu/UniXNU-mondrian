# pong（iOS 18.7.10）路线可行性 —— 本地代码深度核验结论
# 2026-10-31 初稿；2026-11-07 按设备实测与 pong16 ios16 分支复核更新证据等级

## 你的问题：本地 pong 仓库，pull 后仔细看代码，是否可行？

### 结论：**硬件层完全可行且价值极高；构建层有明确的 Linux 适配工作量（可控）；用户态层是"换轨"而非"修复"。**

## 已核实的事实链（全部 file:line）

### 1. 成就属实：pong 上游记录仍是 source 级，本项目已有 device 级证据

- `porting.toml` 中 **13 处 `kind="source"`、0 处 `kind="host"`、0 处 `kind="device"`**。这是 **pong 上游仓库**的记录状态；`migration/format2/migration-state.json` 的 `"local_unpublished_edits": false`、`"image_hashes_used": false` 说明它对镜像不做哈希或回读，公开仓库里没有可复验的 device 证据链。
- 但 **本项目**已把 pong 代码搬到 K60 并拿到 device 级证据：
  - `drivers/` 与 pong16 `FETCH_HEAD`（`ios16` 分支）文件清单一致：pong16 分支中的 **8 个驱动目录共 155 个文件**，加上顶层 `PongProbe.h`；`PongAdreno` **103/103 文件同码**。仅 4 个文件内容分叉：`DarwinBoot22/DarwinBoot.c`、`NativeUfs/NativeUfs.cpp`、`NativeUfs/PongUfsTransport.cpp`、`NativeUfs/RootLayout.h`（逐文件账见工作区 `docs/PONG16-DIFF-AUDIT.md` §3.2）。
  - `userland/` 14 个文件在 HEAD 上与 pong16 的 blob 全部相同；`userland/build.py` 双方 blob 都是 `14760bae1bbd6270c68717cf384d5565366a9731`（`git rev-parse` 复核）。
  - 设备上系统已进用户态、SpringBoard 已进主循环（2026-11-07 设备日志，见 `docs/STATE-2026-11-07.md` §1）；当前硬阻断是 stock OS 窗口未跑 `apply()` 导致的 launchd SIGSEGV，不是 pong 代码不可用。
- 口径更正：旧说“drivers/ 9 目录完全一致”不准确——实测是 **8 个目录**、且 4 个文件有本地分叉。准确说法是“文件清单一致、`PongAdreno` 同码”，不是全部字节一致。

### 2. darwin24 内核补丁 = 单个 467 KB 聚合补丁
- `patches/xnu-ipados18/0001-pong-darwin24.patch`：**12,396 行**，全部 darwin24 适配在一个文件里。
- OS profile 的 series 只有一行注释："Darwin24 fixes are currently reviewed as part of the device aggregate; apply them only once."
- README 明说：**"Darwin23 的 architecture patch series 没有直接叠加到 XNU11417；其适配版本已经包含于现有 Darwin24 聚合补丁"** —— 意味着我们的 16.6.1 系列（128 个补丁）里的等价修改**大部分应在这个聚合里已存在**，这是巨大利好。

### 3. 构建系统：macOS-only 是设计现状，非本质依赖
- `scripts/build-ipados18-pong-macos.py` → `build-xnu-ipados18.sh`（1116 行）。
- **无 `uname`/Linux 分支**（0 处）；CI 是 `macos-15-intel`；`pong_paths.py` 默认 `/Volumes/PongDev`、`DEVELOPER_DIR`。
- **对照**：我们 16.6.1 跑通的 `build-xnu-4k-baseline.sh` 同样**没有 uname 分支** —— 它的 Linux 支持全部来自 `scripts/linux/prepare-xnu.py`（源码改写）+ `kernel.py:linux_env()`（HOST_CC/MIGCOM/CLT_PREFIX 注入）+ `/opt/unixnu-linux` 工具链（`setup-toolchain.py` 生成 `xnu-host-cc`、`migcom` 等）。
- **因此 Linux 适配路径是清晰的**：把 `prepare-xnu.py source` + `linux_env()` 的同等注入接进 `build-xnu-ipados18.sh`。xnu-11417 与 8796 的差异会被 prepare-xnu.py 的改写规则覆盖一部分，不够的按 16.6.1 的经验补。

### 4. 硬件驱动：与 K60 同 SoC，直接可用
- `PongPlatform24` 组件（`migration/format2/components.toml`）：**A730、QCA6490、TFA9873、Goodix Berlin-D** —— K60 全部同款或同族。
- `drivers/PongAdreno/`：完整 A730 栈（GMU/HFI/CP/Clocks/SMMU4K/Firmware/Metal bridge）。
- `drivers/PongWifi/`（QCA6490/ath11k）、`PongPower/`（ADSP/AudioReach）、`ArmCpu/`、`NativeUfs/`、`DarwinBoot24/`。
- **与 sheng 的本质区别**：sheng 是 SM8550，硬件层我们搬不了；pong 与 K60 同 SoC，硬件层**已按文件清单核验可直接复用**（`PongAdreno` 103/103 同码；仅 `NativeUfs` 等 4 个文件有本地分叉，见 §1），只有面板参数（1080×2412 vs 1440×3200 DSC）和按键布局要改回 K60 的。

### 5. 22H374 输入依赖（要注意的一个点）
- profile 指向 Apple 的 `iPad_10.2_18.7.10_22H374_Restore.ipsw`（第七代 iPad）。
- 需要：kernelcache（prelink 用）、trust cache、**dyld shared cache**（用户态运行必需）、App cryptex。
- 本地目前只有 20G81 和 21H461 的缓存；22H374 需要按需 fetch（unixnu fetch / range 下载，磁盘无忧）。

## 工作量分解（相比 sheng 17.7.11 路线）

| 工作项 | pong 18.7.10 | sheng 17.7.11（原 Route A） |
|---|---|---|
| 内核源 fetch | xnu-11417（新 fetch） | xnu-10063（已 fetch ✓） |
| 内核补丁 | 1 个聚合补丁（已含全部适配） | 62 个干净 + 58 个要重写 |
| Linux 构建适配 | 把 linux_env/prepare-xnu 接入 ipados18 脚本（1-2 天） | 已完成 ✓ |
| 硬件驱动 | **同 SoC 原样用**（改面板参数） | SM8550→SM8475 全部自己搬 |
| GPU | A730 现成（PongAdreno+Metal bridge） | 无 |
| 用户态 | HackiOS init（pong 现成，mzyxsl 已证明此路） | stock launchd（风暴未解） |
| 输入依赖 | 22H374 IPSW（需 fetch） | 21H461 已缓存 |
| 预链接 | pong 自己的入口（build-ipados18-prelinked-boot.py） | unixnu 原生 ✓ |

## 最终建议

**pong 18.7.10 路线可行，且明显优于 sheng 17.7.11**——因为同 SoC 让硬件层从"移植"变"复用"，用户态从"未解"变"已验证"，GPU 从"无"变"现成"。代价是：
1. Linux 构建适配（把 16.6.1 已验证的 linux_env 注入法移植到 ipados18 脚本）；
2. K60 面板参数回填（我们已有工作的 1440×3200 栈）；
3. 22H374 输入 fetch。

16.6.1 主线与 route-a-17 分支原样保留。**确认后我立即开 `route-a-18`：先 pong→K60 的板级差异清单（面板/按键/Data UUID），再接 Linux 构建链。**
