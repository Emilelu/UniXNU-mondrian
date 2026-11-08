# 上游 UniXNU 生态与 iOS 16~27 移植可行性（2026-11-01 调研）

> 本文是 route-a-18 的外部现状底账。结论：**继续 18.7.10（22H374），不迁移 26/27**。
> 数据来源：GitHub API（`git ls-remote` / `api.github.com`）、本地 `~/hackios/UniXNU` 的
> `origin/feat/ipados27-gpu-parity`、unixnu.com 官方文档、`ios-sweet-k60` 的 `IOS-26-27-EVALUATION.md`。
> 复现：`bash scripts/k60-sync-refs.sh`。

## 1. iOS 16 ~ 27 的可行性阶梯

| 版本 | profile | arch | donor | kernelcache | prelink | 先例 |
|---|---|---|---|---|---|---|
| 16.6.1 (20G81) | `ipados-16.6.1-20G81` | arm64 | iPad7,11 | 非 fileset | 传统 `emit_prelink` | 本地 worktree 保留；上游 main 已删 |
| 17.7.11 (21H461) | `ipados-17.7.11-21H461` | arm64 | iPad7,11 | 非 fileset | 传统 | 上游 main 有 |
| 18.7.10 (22H374) | `ipados-18.7.10-22H374` | arm64 | iPad7,11 | 非 fileset | 传统（本仓手写 slide `-0x112C000`） | 本仓与 pong 同版 |
| 26.5.2 (23F84) | `ipados-26.5.2-23F84` | **arm64e** | iPad17,3(M4) | **MH_FILESET**、条目 0 符号 | fileset 参考内核 + `--allow-missing` | sheng；**prelink 因输入是 MH_FILESET 中止** |
| 27.0.1 (24A446) | `ipados-27.0.1-24A446` | **arm64e** | iPad17,3 | MH_FILESET | 同上 | sheng 的 os_profile |

### 1.1 难度分级

| 跨度 | 难度 | 依据 |
|---|---|---|
| 16 → 18 | **低** | arm64 + 传统 prelink；上游有 sheng/alioth/ishtar/marble 等大批先例；kernelcache 非 fileset |
| 18 → 26 | **极高** | `xnu-12377.122.8~1/RELEASE_ARM64_T8142`；Darwin 26 未开源，用 `darwin26-syscalls/kpi/shared-region` 三补丁替代；kernelcache 298 条目、585,131 个 pointer-format-8 fixup、条目 0 符号；dyld 缓存 1208 处 SMSTART SM / 1287 处 SMSTART ZA；31 个 prelink 根 → 1864 个内核目标 / 47807 指针位点 / 42027 分支位点；sheng 的 `arm64e-os` 至今 `planned` |
| 26 → 27 | **中** | 同一基础设施，只换 build 号与 profile |

### 1.2 不迁移的两条独立理由

**理由一（本文档，作者：route-a-18）**：26/27 只有 `arch = "arm64e"` 的 profile，
donor 是 M4（iPad17,3）。K60 是 SM8475（arm64 非 e），sheng 能在 SM8550 上跑 arm64e，
SM8475 **零证据**。且 iPad7,1（A10）在 26/27 没有对应 kernelcache。

**理由二（`ios-sweet-k60` 的 `IOS-26-27-EVALUATION.md`，2026-11-01）**：
1. **兼容机型从 A13 起**（iPhone 11 向上），我们伪装的 A10/A11 身份在 26/27 上不成立，
   必须换身份，框架选择、GPU 家族、Metal 能力全跟着变。
2. **27 的 dyld 共享缓存约 5.95 GiB + 512 MiB maxSlide，超了 26.x 内核固定的 6 GiB 共享区**
   （`SHARED_REGION_SIZE_ARM64 = 0x180000000`），`_shared_region_map_and_slide` 返回 ENOMEM，
   `launchd`（pid 1）启动即 panic。绕过要改 `dyld_cache_header.maxSlide`（@0xF0）清零。
3. 26 生态里只有 zeta（Surface Duo 2）把 launchd/dyld 送到 PID 1，界面没起；
   用户态是 arm64e，zeta 靠离线 arm64e→arm64 重写，下一步就 `Execution faults on an unslid pointer`。
4. cryptex / preboot 挂载必须补齐，否则系统 App 起不来。

### 1.3 我们在官方 bring-up 阶梯上的位置

官方 `unixnu.com/porting/bring-up` 七段：UEFI → UniXNU → Payload → DarwinBoot →
Kernel entry → Storage/root → Userland。

| 段 | 我们 |
|---|---|
| UEFI / UniXNU / Payload / DarwinBoot | 已过（绿条 + `DARWINBOOT:` 校验 + payload 逐字节核对） |
| Kernel entry | **未过**：内核进到 `ml_parse_cpu_topology` 之后（0245 修复后越过），尚未到 platform expert |
| Storage/root、Userland | 未开始 |

## 2. 四个仓库与 UniXNU 组织的进展

### 2.1 设备仓库对比

| 仓库 | 设备 / SoC | 版本 | 状态 | evidence 强度 |
|---|---|---|---|---|
| `UniXNU/UniXNU-sheng` | Pad 6S Pro / SM8550 | 26.5.2→27.0.1 | 13 个 area `implemented` + `arm64e-os` `planned` | 真 device：GPU 325 次映射各 0.20 ms、空闲 130 fps；WiFi 5 GHz WPA2 −73 dBm 12/24 Mbit；音频 6 路 PLL 锁定 151/155 周期；电池 9353 mAh / 172 次循环；CPU 499–2803 MHz |
| `Chengdong-Yu/UniXNU-pong` | Nothing Phone 2 / SM8475 | 18.7.10 | 13 area `implemented` | **13 条全是 `kind = "source"`**，0 host / 0 device |
| `1696108518/UniXNU-liuqin` | Pad 6 Pro / SM8475 | 从 sheng 派生 | **不能构建、不能刷**；板级数值已核实 | 无 `porting.toml`（format 1）；`docs/porting-plan.md` 四阶段 |
| `Emilelu/UniXNU-mondrian`（本仓） | Redmi K60 / SM8475 | 18.7.10 | 死点收敛到可读 panic 屏 | 4 条 device/host（2026-11-01 回填） |

### 2.2 UniXNU 组织的 28 个仓库

| 仓库 | 作用 | 关键分支（2026-11-01） |
|---|---|---|
| `UniXNU` | 核心构建驱动 | `main` `8f63c39`；`feat/ipados27-gpu-parity` `d266658`；另有 26 个功能分支 |
| `UniXNU-sheng` | Pad 6S Pro 设备仓 | `main` `6b43339`；`feat/ipados27-gpu-parity` `d0eecd4`；26 个功能分支 |
| `UniXNU-sm8550-common` | SM8550 共享层 | `main` `a9f45dc`；`feat/ipados-26` `9118a9e` |
| `uefi-sheng` | sheng 的 UEFI 固件 | `main` `0a55f26`；`sheng` `20ac23d` |
| `Adreno740` | 原生 Adreno 740 驱动 | `main` `a9a2cbb`；`feat/ipados27-gpu-parity` `10ac0ea`；`perf/gpu-smoothness` `5629fbc` |
| `AdrenoMetal` | Metal 前端 + metal2vulkan | `main` `831a9dc`；`feat/ipados27-gpu-parity` `a0a34fa` |
| `XnuPrelink` | prelink 发射器 | `main` `b74ed7c`；`feat/ipados27-gpu-parity` `76452c6` |
| `DarwinBoot` | UEFI 引导器 | `main` `3c75734`；`feat/ipados27-gpu-parity` `3e3a8a9` |
| `ArmCpu` | ARM64 CPU/GIC/定时器 | `main` `93a5030`；`feat/ipados27-gpu-parity` `4bd3230` |
| `ArmDTPlatform` | ARM 设备树 platform expert | `main` `417ff95` |
| `ShengUfs` | 原生 UFS | `main` `99d8bcd`；`feat/ipados27-gpu-parity` `78c93b0` |
| `ShengHidInput` | HID 输入 | `main` `71a40e7`；`feat/ipados27-gpu-parity` `24f1f3f` |
| `ShengNovatekTouch` | NT36532E 触摸 | `main` `a1a6f2b`；`fix/touch-hold` `30e1542` |
| `GopFramebuffer` | 显示 / 扫描输出交接 | `main` `19ef3a7`；`feat/ipados27-gpu-parity` `74ff4c4` |
| `ArmSmmu4K` | SMMUv2 原生 4 KiB 表 | `main` `83969cd`；`feat/ipados27-gpu-parity` `1811b6d` |
| `VerifiedRoot` | root 信任工具 | `main` `974f043`；`feat/ipados27-gpu-parity` `ed368a8` |
| `RamBlock` | RAM 块存储 / 持久覆盖 | `main` = `feat/ipados27-gpu-parity` = `4be2d7e` |
| `VirtioMmioBlock` / `VirtioMmioConsole` | virtio | `main` `4e1013e` / `7025321` |
| `AdrenoFirmware` / `AdrenoPM4` / `AirNir` | GPU 固件与着色器 kit | 各自 `main` |
| `QcomGeniSpi` / `Ath12kWifi` / `SoftwareAES` / `ArmVirtPlatform` / `ShengPreflight` / `AppleKeyStoreState` | 板级驱动与工具 | 各自 `main` |
| `.github` | 组织级配置 | — |

**`feat/ipados27-gpu-parity` 是跨 14 个仓库的联合作业线**，本地 `~/hackios/UniXNU` 的
`origin/feat/ipados27-gpu-parity` 也在（`d266658`）。它是后续主线，不是可选项。

## 3. 可摘取的件（不迁移也能用）

| 件 | 来源 | 用途 | 何时用 |
|---|---|---|---|
| fileset prelink 实现与 `--fileset-reference` 用法 | `XnuPrelink` 27 分支、`docs/drivers/xnu-prelink.md` | 唯一可参考的 fileset 实现 | 若转 fileset 内核 |
| `darwin26-syscalls/kpi/shared-region` 三补丁 | `UniXNU` 27 分支 `patches/xnu/series` | 26+ 的 syscall/KPI 缺口 | 迁移时 |
| `abi/original-classes.json` + `ioaccelerator-base-abi-24A446.json` | 同上 | GPU / IOAccelerator ABI 对照 | GPU 阶段 |
| sheng(SM8550) 的 GPU/SMMU/display 模块 | `Adreno740` `AdrenoMetal` `ArmSmmu4K` `GopFramebuffer` | 同族 SoC，K60 可对照 | GPU/UFS 阶段 |
| 官方 entry probe + panic screen + 诊断页 | `UniXNU/scripts/{patch-xnu-entry-probe.py,xnu-panic-screen.c}`、`unixnu.com/guide/debugging` | **本轮就用** | 立刻 |

## 4. 未决问题

- SM8475 能否跑 arm64e 用户态：零证据。若 26/27 要做，这是第一个要验的。
- K60 的 GPU 家族对外伪装成哪一档（Adreno 740 同代，但 Apple 身份档位要跟 iOS 版本匹配）。
- `feat/ipados27-gpu-parity` 与 `main` 无共同祖先，不能 cherry-pick，只能整体取用或重做。
