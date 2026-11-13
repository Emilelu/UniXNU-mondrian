# 贡献者与来源说明

> GitHub 的 contributors 图只统计 commit 的 `author` 字段与 `Co-authored-by` trailer。
> 当代码经由 fork 搬运、rebase、或提交时使用了共享的 git 身份，图就无法反映实际归属。
> **本文件是人工维护的权威记录。**

---

## 一、人员贡献

| 贡献者 | 身份 | 贡献内容 |
|---|---|---|
| **Emilelu** | 仓库所有者 | 主线开发、移植框架、构建与刷机流程 |
| **yibiya**（sduuub） | `github.com/yibiya` | 见下方「yibiya 的贡献」专节 |
| **mzyxsl** | — | 早期 mondrian 设备记录与 DT 数据 |
| **XTOM0706** | `github.com/XTOM0706` | `ios-sweet-k60` 独立移植线的作者（见下方来源表） |
| **A5** / **A2 display** | — | 单点提交（显示相关） |

### 构建机身份（非个人，列出以免误解）

| 身份 | 提交数 | 说明 |
|---|---|---|
| `k60-ios <k60-ios@localhost>` | 53 | 2026-10-30 ~ 10-31 的自动化/构建机提交 |
| `K60 Bring-up <k60@local>` | 28 | 2026-11-10 ~ 11-11 的构建机提交 |

---

## 二、yibiya 的贡献（重点）

`https://github.com/yibiya/UniXNU-mondrian`

**为什么 contributors 图里看不到他**：这些分支上的提交，git author 字段写的是
`Emilelu <...>`（提交时用了共享的 git 身份），所以 GitHub 把它们算给了 Emilelu。

### 已取用的分支与内容

| 分支 | 提交 | 我们取用的部分 | 落在 main 的哪个提交 |
|---|---|---|---|
| `fix/ui-startup-blob` | `f291b52` | `userland/ui_compat.c`：`CFPreferencesSetAppValue` 从 `__attribute__((constructor))` 移到 `present_home()`（主队列运行时）。这是 backboardd 崩溃的直接修复 | `50f4644` |
| `fix/ui-startup-blob` | `5198a67` | `patches/xnu/0394-k60-launchd-cache.patch`：22 个核心 job 的精选 launchd 缓存，修 `webookmarksd` 缺失导致的 `initproc exited` | `50f4644`（并入 `0391`）|
| `fix/ui-startup-blob` | `c6e555c` | `0340` 的 95,856 B UI 库（含上述修复的编译产物） | `50f4644` |
| `fix/ui-startup-blob` | 早期 | `userland/ui_compat.c` 初版（41511 B，CFPreferences 仍在 constructor） | `6dcb7da` |
| `fix/ui-startup-blob` / `upstream-fix` | `163b748` / `0576573` | `patches/xnu/0391-k60-embedded-init.patch`（sha `accaab23221b`，与我们完全一致）| `163b748`、`0576573` |
| `upstream-fix` | `522c6ea` | prelink：给 launchd 提供到达主队列的 helper | 参考 |

### 尚未取用（2026-11-12 新发现）

| 分支 | 内容 |
|---|---|
| **`fix/touch-gpu-bringup`**（2026-11-11 17:04） | **触摸驱动重写**：47,040 B / 1,039 行（我们的版本是 239,781 B / 5,452 行），`max_x==14400 && max_y==32000` 真实触摸坐标、`bitbang-pins` 显式 MISO/MOSI/CLK/CS 角色元组、`k60_touch_se=5 k60_touch_rcg=1`；**GPU**：`link actual scanout and mailbox`、`map only consumed GCC pages`、`use monitor access for K60 RSC` |

### 他自己署名的 6 个提交（author = sduuub）

全部在 `fix/k60-measured-high-window` 分支：

```
e6c4c60  ci: touch the OS window workflow so forks register it
2d29a2f  fix(board): use the boot-args the device actually booted with
9dfc92b  fix(preflight): treat the core patch as optional
46986f3  fix(preflight): run apply-core-patches.sh through sh and restore the exec bits
527a6b6  config: disable the Pong Adreno platform for the software-framebuffer build
15348fc  fix(series): retarget pong-touch-console to the unmodified drawLayer line
```

**注意**：这 6 个提交在 origin 上已被删除的 `fix/k60-measured-high-window` 分支里，
不在 `main` 历史中。若把它们合并回 `main`，GitHub 会立刻把 yibiya 计入 contributors，
**不需要 force-push**。

---

## 三、外部参考来源（全部）

### 3.1 设备移植 fork

| 仓库 | 说明 | 我们参考的部分 |
|---|---|---|
| **`XTOM0706/ios-sweet-k60`** | HackiOS / ios-sweet 的 Redmi K60（mondrian / SM8475）独立移植线，2026-10-21 建，含 patched shim、硬件映射、cape 板级准备 | HackiOS userland 结构、shim 思路、板级映射 |
| **`Seanding1998/hakios-xnu-kernel`**（`phk110-port`） | 一加 Ace 2 / PHK110 / **SM8475** 的 HakiOS 移植 | `docs/phk110/waves/wave12c-electrical.md`：同 SoC 触摸 PASS 全流程（20 ms 节拍 + 分帧收割）；`wave12b`/`wave12a`：软件链闭环与断点定位；`wave12-touch-buttons.md`：cape/sm8475 的 GCC 与 mainline sm8450 差异（m/s_ahb FID 134/135 vs 118/119）；`wave20-launchd.md`：`hw.target` / `PEGetTargetName` 根因与双层修复 |
| **`yibiya/UniXNU-mondrian`** | 本仓库的 fork，见上方专节 | UI 库、launchd 缓存、触摸/GPU 新线 |

### 3.2 Pong 参考实现（Chengdong-Yu）

| 仓库 | 我们参考的部分 |
|---|---|
| `Chengdong-Yu/UniXNU-pong` | Pong 原机移植总参考 |
| `Chengdong-Yu/pong-adreno` | Adreno GPU 驱动结构 |
| `Chengdong-Yu/pong-adreno-metal` | Metal 插件与 bridge 架构（我们的 `drivers/PongMetal` 同源） |
| `Chengdong-Yu/pong-arm-cpu` | ArmCpu 驱动 |
| `Chengdong-Yu/pong-arm-dt-platform` | ArmDTPlatform |
| `Chengdong-Yu/pong-boot-capture` | 启动日志抓取 |
| `Chengdong-Yu/pong-darwin-boot24` | darwin24 启动链 |
| `Chengdong-Yu/pong-metal` | Metal 前端 |
| `Chengdong-Yu/pong-power` | 电源/RPMh |
| `Chengdong-Yu/pong-ram-block` | RamBlock |
| `Chengdong-Yu/pong-ufs` | UFS 存储 |
| `Chengdong-Yu/pong-usb` | USB |
| `Chengdong-Yu/pong-wifi` | WiFi |
| `Chengdong-Yu/uefi-pong` | UEFI 固件 |

### 3.3 其它参考

| 仓库 | 说明 |
|---|---|
| `dipa-studio/ios-sweet` | HackiOS / ios-sweet 上游（userland 注入、UIKit 兼容层思路） |
| `oosexgang/hakios-xnu-kernel` | HakiOS XNU 内核的另一个分支参考 |
| `blacktop/darwin-xnu-build` | XNU 构建工具链参考 |

### 3.4 UniXNU 官方

| 仓库 | 我们参考的部分 |
|---|---|
| `UniXNU/UniXNU` | 框架、`components.toml` 组件目录（25 个组件）、`porting-record.py` 校验器、文档站 |
| `UniXNU/UniXNU-pong` | 官方 Pong 设备仓库 |
| `UniXNU/UniXNU-sheng` | 官方 sheng 设备（SM8550，Novatek 触摸 + GPU 调度） |
| `UniXNU/UniXNU-zizhan` | 同 SoC SM8475 设备（ST FTS 触摸 + Adreno 730） |
| `Emilelu/UniXNU-sm8475-common` | SM8475 SoC 公共层（本项目的 SoC 仓库） |
| `UniXNU/UniXNU-sm8550-common` | SM8550 SoC 公共层（`Sm8550Platform` 组件） |
| `UniXNU/Adreno740` | A740 内核 GPU 驱动（`NativeAdrenoService.cpp` 分层参考） |
| `UniXNU/AdrenoMetal` | Metal 前端（`NativeAdrenoMetalPlugin.mm` / `NativeBridgeMetalFrontend.mm` / `NativeMetalBridge.rs`），与我们 `PongMetal` 同架构 |
| `UniXNU/AdrenoPM4` | PM4 命令编码 |
| `UniXNU/AdrenoFirmware` | Adreno 固件与 HFI |
| `UniXNU/QcomGeniSpi` | **GENI SPI 控制器**（`GeniSpi.c:80` 有 `use_dma` 分支、`:113-118` DMA 模式切换）——触摸 SPI 层的官方解 |
| `UniXNU/ShengNovatekTouch` | Novatek NT36532 触摸协议（不同芯片，架构参考） |
| `UniXNU/ShengHidInput` | `NativeHidInput.cpp`：touch → IOHIDDevice 上报架构 |
| `UniXNU/ArmSmmu4K` | SMMU 4 KiB 页表 kit |
| `UniXNU/ArmCpu` | ARM GIC 与定时器 |
| `UniXNU/ArmDTPlatform` | 设备树平台专家 |
| `UniXNU/DarwinBoot` | UEFI XNU loader |
| `UniXNU/GopFramebuffer` | GOP framebuffer |
| `UniXNU/RamBlock` | RAM block 设备 |
| `UniXNU/SoftwareAES` | 软件 AES-CBC |
| `UniXNU/AppleKeyStoreState` | AppleKeyStore 状态 |
| `UniXNU/VerifiedRoot` | 认证块读取 |
| `UniXNU/ShengPreflight` | sheng 固件预检 |
| `UniXNU/QcomBaseband` | 基带参考 |
| `UniXNU/QcaBluetooth` | 蓝牙参考 |
| `UniXNU/QcomDwc3` | USB DWC3 参考 |
| `UniXNU/Ath12kWifi` | WiFi 参考 |
| `UniXNU/Ath12kWifi` | 音频 codec 参考 |

### 3.5 文档站

| 地址 | 用途 |
|---|---|
| `https://unixnu.com/zh/porting/records` | 设备适配记录规范（`porting.toml` schema） |
| `https://unixnu.com/zh/porting/input` | 触摸移植指南 |
| `https://unixnu.com/zh/porting/gpu` | GPU 移植指南 |
| `https://unixnu.com/zh/reference/components` | 组件目录 |
| `https://unixnu.com/zh/drivers/repositories` | 驱动仓库列表 |

---

## 四、引用规范（以后必须遵守）

1. **优先 `git cherry-pick -x <sha>`** —— 保留原 author，自动加
   `(cherry picked from commit <sha>)` trailer。
2. **手工复制代码时必须加 trailer**：
   ```
   Co-authored-by: 姓名 <邮箱>
   ```
3. **新来源出现时同步更新本文件**。
4. **不要把 fork 当成"上游"而不核实**：
   ```bash
   gh api "/repos/<owner>/<repo>/commits/<sha>" \
     --jq '{git: .commit.author, gh: .author.login}'
   ```
   git author 与 GitHub 账号可能不一致。

参见 `docs/engineering/PITFALLS.md` P-130 与 `docs/engineering/HARD-RULES.md` ★35。
