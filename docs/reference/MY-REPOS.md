# 作者本人仓库清单（K60 iOS 移植）

> **分支级现状地图见 [REPO-BRANCH-MAP.md](REPO-BRANCH-MAP.md)**（2026-11-03 起维护：每仓每分支职责、三方状态、与 iOS16 主线关系、「一次上机牵动哪几个仓库」）。

**以下仓库属于本项目作者本人，不是上游参考仓库。**

判定依据：GitHub 账号 `Emilelu`（`gh auth status` 已登录确认），公开仓库经 `gh repo list` 全量拉取；本地仓库经 `git remote -v` 逐一核对。作者署名在 git 历史中出现为 `Emilelu` / `emilelu` / `k60-ios` / `A2 display` / `A5` / `c`（后四者为项目内 agent 署名，仅 commit 证据）。

## 一、K60 移植直接相关（6 个远端仓库 + 2 个纯本地仓库）

| 仓库 | URL | 是否 fork | 用途 | 与 K60 移植的关系 | 本地克隆路径 |
|---|---|---|---|---|---|
| UniXNU-mondrian | https://github.com/Emilelu/UniXNU-mondrian | 否（自建） | K60 设备仓库：board.toml、DTS、补丁系列、脚本、文档 | **主战场**。设备侧全部配置与 02xx 补丁系列、三路线文档都在此 | WSL `~/hackios/UniXNU-mondrian`（分支 `fix/k60-measured-high-window`，**工作区脏**）；WSL `~/hackios/work-display/device`（`main` 分支克隆） |
| uefi-mondrian | https://github.com/Emilelu/uefi-mondrian | 否（自建，基于 Mu-Silicium 框架） | K60 UEFI 固件：内存映射、启动参数、按钮/ RamPartition DXE | 唯一产出可启动 FD 的固件仓库；4 GiB 高窗口在此定稿 | WSL `~/hackios/uefi-mondrian`（分支 `fix/k60-measured-high-window`，**工作区脏**：`MemoryMapLib.c`、`BootArgs.h`、`Mu_Basecore` 指针） |
| UniXNU | https://github.com/Emilelu/UniXNU | **是**，fork 自 `UniXNU/UniXNU` | UniXNU 框架核心的作者分支：k60 构建编排、CI、profile、prelink 补丁 | **构建核心**。`/tmp/k60build` 就是它的 `k60build` 分支检出；19 个 k60*/wf*/core* 分支承载全部编排实验 | WSL `/tmp/k60build`（`k60build` 分支，583 提交含全部分支）；WSL `~/hackios/UniXNU`（`main`）；WSL `~/smp-core`（detached @ `smp-0340`）；`D:\Android\k60-ios\UniXNU-fork`（`k60` 分支，468 提交，**旧快照**） |
| ios-sweet-k60 | https://github.com/Emilelu/ios-sweet-k60 | **是**，fork 自 `XTOM0706/ios-sweet-k60` | hackios（ios-sweet）路线的 K60 移植参考与协作 | 参考仓库**但含作者本人 4 条提交**（`8c47846` touch 接线 + 3 条 CI 探测）；锁屏四条显示前提等关键证据来自此仓库 | `D:\Android\k60-ios\ios-sweet-k60`（origin=XTOM0706 上游，fork=Emilelu） |
| PongUfs | https://github.com/Emilelu/PongUfs | 否（自建） | SM8475 UFS 传输层 + SHNGROOT 根卷驱动（NativeUfs） | 内核链接的存储驱动源码；经 build 系统以 feed 形式消费 | **未克隆工作副本**；仅构建缓存 `/tmp/k60build/out/feeds/PongUfs-245e493f` |
| UniXNU-sm8475-common | https://github.com/Emilelu/UniXNU-sm8475-common | 否（自建） | SM8475（骁龙 8+ Gen1）平台共享支持：CPU 节点命名、Darwin 簇标签 | 被设备仓库引用的公共层 | WSL `~/hackios/UniXNU-sm8475-common`；构建缓存 `/tmp/k60build/out/feeds/UniXNU-sm8475-common-a599f398` |
| （纯本地）work-display/pw | 无远端 | — | 显示补丁工作区（0210-0213：原生画布、启动、空加速器、首帧） | 显示 bring-up 补丁的暂存区，补丁后进入设备仓库 | WSL `~/hackios/work-display/pw` |
| （纯本地）xnu-src/verify | 无远端 | — | libkern 头文件验证树（单提交 `58dd52a base`） | 构建期头文件核对用 | WSL `~/hackios/xnu-src/verify` |

### 内核工作树（作者改动载体，**均未提交**，不是独立仓库）

| 路径 | 基线 | 状态 |
|---|---|---|
| `/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work` | apple-oss xnu-8796.141.3（16.6.1，单提交 `1b191cb`） | **detached HEAD + 全部诊断改动未提交**（kern_exit.c STR/corpse、MiniIOMobileFramebuffer 等）。严禁 checkout/reset/clean |
| `/tmp/k60build/out/route-a18/Pong-iPadOS18-native/.cache/xnu-work` | apple-oss xnu-11417.140.69（iPadOS18 路线，单提交 `43a9088`） | iOS 18 弯路的工作树，已搁置 |
| `…/ipados-16.6.1-20G81/…/libdispatch-work`、`…/ipados-17.7.11-21H461/…/libdispatch-work` | apple-oss libdispatch-1325.120.2（`ca80d30`） | 构建缓存检出 |

## 二、作者本人但与 K60 无直接关系（简要登记）

| 仓库 | fork | 说明 | 本地 |
|---|---|---|---|
| Hackintosh-EFI-Lenovo-Legion-R7000-2020-… | 否 | 联想 R7000 2020 Hackintosh EFI（x86 黑苹果，非本项目） | 未克隆 |
| NootedRed | 是（ChefKissInc/NootedRed） | macOS AMD GPU kext，黑苹果相关 | 未克隆 |
| nvidia-macos-driver | 是（nullmoth/nvidia-macos-driver） | macOS NVIDIA Metal 驱动 | 未克隆 |
| BunpoNotes | 是（Bokjan/BunpoNotes） | 日语语法笔记 | 未克隆 |
| ocat-plus-plus / lenovo-dmi-rescue / Project-Banager / emilelu.github.io / SanBPushChest / KichikuAdventure / iLight | 否 | 个人工具/博客/早期项目，与 K60 无关 | 未克隆 |
| 私有 10 个（OLD-TECHNOLOGIES、My-Obsidian-Vault、fishtalk-backend、Thesis、starlight-blog、FuckBOC、FuckICBC、AnyApiToolBox、BandoriLotteryEmulator、StrangeAdventure） | 否 | 个人私有项目，与 K60 无关 | 未克隆 |

## 三、明确**不是**作者本人的仓库（防混淆速查）

| 仓库 | 归属 | 本地位置 |
|---|---|---|
| UniXNU/UniXNU（及 org 下 19 个 kits/drivers 模块、UniXNU-sheng、uefi-sheng） | UniXNU 组织（上游框架） | `D:\Android\k60-ios\UniXNU`、`D:\Android\k60-ios\UniXNU-sheng`、`F:\k60-archive\uefi-sheng`、WSL `~/hackios/UniXNU-sheng`、`~/hackios/UniXNU-docs`、`/tmp/k60build/kits/*`、`/tmp/k60build/drivers/*` |
| XTOM0706/ios-sweet-k60 | XTOM0706（hackios 路线上游，锁屏证据来源） | 本地 fork 克隆的 origin 远端 |
| Chengdong-Yu/UniXNU-pong、Chengdong-Yu/uefi-pong | Chengdong-Yu（pong/iPadOS18 路线上游） | WSL `~/hackios/UniXNU-pong`、`~/hackios/uefi-pong`、`D:\Android\k60-ios\uefi-pong` |
| 1696108518/UniXNU-liuqin | 1696108518（liuqin 设备参考） | `D:\Android\k60-ios\UniXNU-liuqin`、WSL `~/hackios/UniXNU-liuqin` |
| Project-Silicium/Device-Binaries | Project-Silicium | WSL `~/hackios/Device-Binaries` |
| apple-oss-distributions/*（xnu×3 版本、libdispatch、libplatform、libpthread、IOStorageFamily、AvailabilityVersions）、microsoft/mu_basecore、ONLYA/corecrypto-2023 | Apple / Microsoft / ONLYA | `/tmp/k60build/out/feeds/*`、`~/hackios/work-display/xnu`、`~/hackios/work-display/verify-xnu` |

> 备注：UniXNU-mondrian 历史中混有 `XTOM0706`（`b8df9fc`）与 `mzyxsl`（`acb5c2d`）两条署名提交，均为协作方补丁被引入设备仓库，仓库归属不变（仅 commit 证据）。
