# 本地仓库总清单（全盘扫描结果，勿再重复询问）

> 扫描时间：2026-11-10 21:45
> 扫描范围：**E:\hackios、E:\k60-work、E:\k60-archive、D:\Android、D:\Android\k60-ios、D:\Android\wsl、F:\k60-archive**
> 铁则：HR-39（调试前先查索引）。**任何仓库位置问题先看本文档，不要问用户。**

## 1. E:\hackios（主工作区，14 个 git 仓库）

| 仓库 | 分支 | HEAD | 脏文件 | origin |
|---|---|---|---|---|
| **UniXNU-mondrian** ← 当前主仓 | fix/k60-measured-high-window | da9d98d | 14 | Emilelu/UniXNU-mondrian |
| **UniXNU-zizhan** | main | 034a0b0 | 0 | qiumochen/UniXNU-zizhan |
| **UniXNU-pong** | main | e0ee6df | 387 | Chengdong-Yu/UniXNU-pong |
| **UniXNU-sheng** | main | a68ee4e | 0 | UniXNU/UniXNU-sheng |
| **UniXNU**（官方主仓）| main | 75ae626 | 0 | UniXNU/UniXNU |
| UniXNU-docs | (无分支) | 066c8d8 | 576 | UniXNU/UniXNU |
| UniXNU-liuqin | main | 907b8e9 | 105 | 1696108518/UniXNU-liuqin |
| UniXNU-sm8475-common | main | c5b50c3 | 1 | Emilelu/UniXNU-sm8475-common |
| QcaBluetooth | main | 22ff97f | 0 | UniXNU/QcaBluetooth |
| QcomGeniSpi | main | eac47ba | 0 | UniXNU/QcomGeniSpi |
| Device-Binaries | main | 9f4dbfd | 0 | Project-Silicium/Device-Binaries |
| pong-power | main | c37179e | 0 | Chengdong-Yu/pong-power |
| pong-wifi | main | d2e33ca | 0 | Chengdong-Yu/pong-wifi |
| uefi-mondrian | main | 1a7afe7 | 0 | Emilelu/uefi-mondrian |
| uefi-pong | main | 997ae23 | 0 | Chengdong-Yu/uefi-pong |

**非 git 目录**：acpi-mondrian-submodule-backup, artifacts, k60, work-display, xnu-src

## 2. E:\k60-work\references（pong 生态 20+ 仓库）

| 仓库 | 分支 | HEAD | 脏 | origin |
|---|---|---|---|---|
| **UniXNU-pong-upstream** | main | e0ee6df | 0 | Chengdong-Yu/UniXNU-pong |
| UniXNU-pong | latest | e0ee6df | 144 | Chengdong-Yu/UniXNU-pong |
| **UniXNU-sheng-upstream** | main | ba66a66 | 0 | UniXNU/UniXNU-sheng |
| UniXNU-sheng | main | 08cde20 | 1 | UniXNU/UniXNU-sheng |
| **UniXNU-upstream** | main | c1ecc5b | 0 | UniXNU/UniXNU |
| UniXNU | feat/ipados27-gpu-parity | c93e965 | 0 | UniXNU/UniXNU |
| UniXNU-sm8550-common | main | 23b2049 | 1 | UniXNU/UniXNU-sm8550-common |
| **ios-sweet** | main | 45263be | 1 | dipa-studio/ios-sweet |
| darwin-xnu-build | main | 6639065 | 1 | blacktop/darwin-xnu-build |
| pong-adreno-metal | main | 418c550 | 106 | Chengdong-Yu/pong-adreno-metal |
| pong-adreno | main | 3e8ffa2 | 116 | Chengdong-Yu/pong-adreno |
| pong-arm-cpu | main | ac65513 | 6 | Chengdong-Yu/pong-arm-cpu |
| pong-arm-dt-platform | main | 09ecfcf | 5 | Chengdong-Yu/pong-arm-dt-platform |
| pong-boot-capture | main | af2c5ca | 4 | Chengdong-Yu/pong-boot-capture |
| pong-darwin-boot24 | main | 86d300d | 20 | Chengdong-Yu/pong-darwin-boot24 |
| pong-metal | main | ccdbc29 | 24 | Chengdong-Yu/pong-metal |
| pong-power | main | c37179e | 36 | Chengdong-Yu/pong-power |
| pong-ram-block | main | eebcdb6 | 8 | Chengdong-Yu/pong-ram-block |
| pong-ufs | main | 3c7e354 | 13 | Chengdong-Yu/pong-ufs |
| pong-unixnu-upstream | main | 1a01c2a | 0 | Chengdong-Yu/UniXNU |
| pong-usb | main | 6070a99 | 8 | Chengdong-Yu/pong-usb |
| pong-wifi | main | d2e33ca | 13 | Chengdong-Yu/pong-wifi |
| uefi-pong | main | 87c10fd | 0 | Chengdong-Yu/uefi-pong |

**非 git**：UniXNU-ruby, ruby-bringup, ios-sweet-0155(空), unixnu-site, upstream-watch, **yibiya-fork**

## 3. E:\k60-work\forks-review

| 仓库 | HEAD | origin |
|---|---|---|
| UniXNU | afad1a2 | Emilelu/UniXNU |
| hakios-xnu-kernel | 96ffbc532 | oosexgang/hakios-xnu-kernel |
| ios-sweet | 45263be | dipa-studio/ios-sweet |

**非 git**：diffs, patches

## 3b. D:\Android\k60-ios 下的 6 个 git 仓库（重要！）

| 仓库 | 分支 | HEAD | origin |
|---|---|---|---|
| **ios-sweet-k60** ← 用户点名，与 ios-sweet 不同 | main | 886101c | **XTOM0706/ios-sweet-k60** |
| UniXNU-fork | k60 | 48331ff | Emilelu/UniXNU |
| UniXNU | main | 33da813 | UniXNU/UniXNU |
| UniXNU-liuqin | main | 907b8e9 | 1696108518/UniXNU-liuqin |
| UniXNU-sheng | main | 08cde20 | UniXNU/UniXNU-sheng |
| uefi-pong | main | 87c10fd | Chengdong-Yu/uefi-pong |

## 4. D:\Android（3 项，非 git）

| 目录 | 项数 | 说明 |
|---|---|---|
| **k60-ios** | 34 | **重要！含 ios-sweet-k60、UniXNU、UniXNU-fork、UniXNU-liuqin、UniXNU-sheng、uefi-pong 等** |
| platform-tools | 14 | adb/fastboot |
| wsl | 1 | Ubuntu-24.04（WSL 发行版数据）|

### D:\Android\k60-ios 完整内容（34 项）
```
AGENT-COORDINATION.md  INDEX.md  README.md
UniXNU/                UniXNU-fork/     UniXNU-liuqin/   UniXNU-sheng/
ios-sweet-k60/         uefi-pong/       work-display/    work-persaudit/
agents/  archive/  build-artifacts/  cache/  config/  deliverables/
docs/  dual_sys/  evidence/  firmware/  gha-logs/  logs/  out/
patches/  payload/  scripts/  seed/  smp/  tools/
boot.json  hardware.dtb  repack.sh  robocopy.log
```

## 5. D:\Android\wsl
- Ubuntu-24.04/（WSL 发行版根，非仓库）

## 6. F:\k60-archive

| 项 | 说明 |
|---|---|
| backups/ | 备份 |
| dtb/ | 设备树 |
| uefi-sheng/ | sheng UEFI |
| k60-work-scripts-2026-10-31.zip | 脚本快照 |

## 7. E:\k60-archive（非 git）

```
README.md
backups/
bootimg-history/
seed256/
```

---

## 统计汇总

| 位置 | git 仓库数 |
|---|---|
| E:\hackios | 15 |
| E:\k60-work\references | 23 |
| E:\k60-work\forks-review | 3 |
| D:\Android\k60-ios | 6 |
| **合计** | **47 个 git 仓库** |

**定时同步任务应覆盖全部 47 个。**

---

## 定时同步任务的范围（用户要求）

**每日两次**，同步以下仓库到上游最新：
1. **E:\hackios 全部 15 个 git 仓库**（有 origin 的）
2. **E:\k60-work\references 全部 23 个 git 仓库**
3. **E:\k60-work\forks-review 3 个**
4. **D:\Android\k60-ios 下的仓库**（需确认哪些是 git）

**额外**：yibiya fork（https://github.com/yibiya/UniXNU-mondrian/commits/upstream-fix/）
的有用 commit 需 cherry-pick 到主仓。

**注意**：有脏文件的仓库（如 UniXNU-pong dirty=387、pong-adreno dirty=116）
同步前必须先 stash 或跳过，禁止强拉丢改动。


---

## 8. WSL 内部文件系统（D:\Android\wsl 的 vhdx 内部）

> **重要**：WSL 里散落着大量工作文件，扫描范围必须包括 `/root`、`/home`、`/opt`、`/tmp`。

### 8.1 WSL 内 git 仓库

| 仓库 | 分支 | HEAD | 脏 | origin |
|---|---|---|---|---|
| /root/linux-apfs-rw | master | 949677e | 0 | linux-apfs/linux-apfs-rw |

### 8.2 WSL 内工作目录（非 git）

| 路径 | 项数 | 说明 |
|---|---|---|
| /home/emilelu/k60-work | 35 | **WSL 侧 k60 工作目录** |
| /home/emilelu/smp-core | 20 | SMP 相关 |
| /home/emilelu/k60tmp | 5 | 临时 |
| /home/emilelu/dsh-sync-logs | 10 | 同步日志 |
| /home/emilelu/acpica-local | 1 | ACPICA |
| /home/emilelu/bin | 1 | 工具 |
| /opt/k60/trees | 3 | **构建树（k60build 在此）** |
| /opt/k60/archive | 1 | 归档 |
| /opt/unixnu-linux | 6 | **Xcode/LLVM 工具链**（CommandLineTools, llvm, include, lib, bin）|

### 8.3 /tmp 内的临时产物（220 个 .patch + 大量目录）

**注意：/tmp 是易失的，但包含大量手工 patch 和中间产物。**

`/tmp` 下 220 个 `.patch` 文件（如 `0301-part1.patch`、`6c-patches-0210-k60-display-native-canvas.patch` 等）。

`/tmp` 下关键目录：
```
/tmp/gpu-rebase/       (183 项)  ← GPU 补丁重基工作
/tmp/bt-test/          (46 项)   ← 蓝牙测试
/tmp/ar-full/ (20)  /tmp/ar-regen/ (20)  ← APFS 参考
/tmp/bt-regen/         (20 项)
/tmp/init-v3/ (15)  /tmp/init-v10guard/ (12)  ← init 相关
/tmp/apfs/             (8 项)
```

---

## 9. 定时同步任务覆盖范围（最终版）

**每日两次（建议 09:00 / 21:00）同步以下全部仓库：**

| 位置 | git 仓库数 |
|---|---|
| E:\hackios | 15 |
| E:\k60-work\references | 23 |
| E:\k60-work\forks-review | 3 |
| D:\Android\k60-ios | 6 |
| **WSL /root/linux-apfs-rw** | **1** |
| **合计** | **48 个** |

**同步脚本**：`E:\k60-work\scripts\sync-all-repos.sh`

**额外任务**：检查 `yibiya/UniXNU-mondrian` 的 `upstream-fix` 分支新 commit，
有用的 cherry-pick 到主仓 `E:\hackios\UniXNU-mondrian`。

**安全约束**：有未提交改动的仓库一律跳过（不 stash、不强拉），
在日志中列出，等人工处理。
