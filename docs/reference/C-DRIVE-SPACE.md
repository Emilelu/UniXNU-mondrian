# C 盘空间治理报告

- 日期：2026-11-02
- 机器：Windows 11（10.0.26200），用户 `Emilelu`
- 方法：全盘只读枚举（45.6 万个文件，排除 reparse point 文件），再定向复核
- 口径说明：目录体积为**逻辑大小**（Explorer 口径）。WinSxS 与 System32 之间存在大量硬链接，逻辑加总会大于磁盘实际占用（逻辑合计 73.4 GB > 实际已用 62.5 GB 即因此）。

## 0. 总览

| 指标 | 值 |
|---|---|
| C: 总容量 | 100.17 GB |
| 已用 | 62.52 GB |
| **可用（清理前）** | **37.65 GB** |
| >1GB 单文件 | **无** |
| hiberfil.sys | 不存在（休眠未启用） |
| pagefile.sys | **在 D:**（系统管理，约 13.9 GB），不占 C: |
| swapfile.sys | 0.25 GB（系统管理，勿动） |
| 卷影副本/还原点 | 无 |

## 1. 顶层目录体积排行（逻辑大小）

| GB | 路径 | 说明 |
|---|---|---|
| 30.43 | `C:\Users` | 见下 |
| 24.07 | `C:\Windows` | 系统，勿动 |
| 11.22 | `C:\Program Files` | 已装软件，勿动 |
| 3.95 | `C:\Program Files (x86)` | 已装软件，勿动 |
| 2.87 | `C:\ProgramData` | LGHUB 1.39 / Windhawk 0.89 / NVIDIA 0.22 |
| 0.60 | `C:\Recovery` | WinRE，勿动 |

### C:\Windows 子项（只统计）

| GB | 路径 | 说明 |
|---|---|---|
| 9.80（实际 10.31） | `WinSxS` | DISM 分析：可回收包 = 0，**官方不建议清理**（今天 03:35 刚自动清过） |
| 8.20 | `System32` | 与 WinSxS 硬链接重叠 |
| 1.18 | `SysWOW64` | — |
| 1.16 | `SystemApps` | — |
| 1.09 | `Installer` | **切勿删除**（MSI 卸载/修复缓存，删了软件无法卸载/更新） |
| 0.59 | `Fonts` | — |
| 0.11 | `Temp` | 均 ≤7 天 |

### C:\Users\Emilelu 子项

| GB | 路径 | 归类 |
|---|---|---|
| 20.73 | `AppData` | 见下 |
| 4.84 | `.workbuddy` | WorkBuddy 应用数据（workspace 1.53 / binaries 0.65 / plugins 0.47 / projects 0.40 / traces 0.40 / changes-detail 0.30 / app 0.29 / logs 0.29 / blobs 0.24）→ **需用户决定** |
| 2.14 | `Documents` | 个人文件，只登记不动 |
| 0.85 | `.dsh` | 需用户决定 |
| 0.71 | `.rustup` | Rust 工具链（`rustup toolchain list` 看哪些可卸）→ 需用户决定 |
| 0.15 | `.cargo` | 其中 `registry` 140 MB 是缓存 → 可安全删除 |
| 0.11 | `.trae-cn` | 只统计，不删 |

### AppData 热点

| GB | 路径 | 归类 |
|---|---|---|
| 5.61 | `Local\Python\pythoncore-3.14-64` | Python 3.14 运行时 + site-packages（**torch 4.03 GB**、unidic_lite 248 MB、cv2 112 MB、scipy 110 MB、playwright 107 MB…）→ 需用户决定 |
| 5.50 | `Local\Temp` | 大头全部 ≤7 天（见下表），>7 天仅 0.05 GB |
| 2.97 | `Local\Programs` | 已装软件，勿动 |
| 0.70 | `Local\ms-playwright` | Playwright 浏览器，`npx playwright install` 可重下 → 需用户决定 |
| 0.61 | `Local\AnkiProgramFiles` | 软件，勿动 |
| 0.44 | `Local\@zcodedesktop-updater` | ZCode 更新器暂存 → 需用户决定 |
| 0.39 | `Roaming\Trae CN` | Trae 应用数据 → 需用户决定 |
| 0.76 | `Roaming\Tencent` | 腾讯系数据 → 需用户决定 |
| 0.65 | `Roaming\.minecraft` | 游戏数据 → 需用户决定 |

Temp 内大项（**全部 ≤7 天，按规则保留**，列出供用户决定）：

| MB | 日期 | 项 | 用途判断 |
|---|---|---|---|
| 2409 | 11-02 | `azuma_4k_work` | 4K 视频 AI 放大工作产物（ai_x4/final4k/shots 等） |
| 884 | 10-27 | `DiagOutputDir` | 诊断输出（含 TRAESetup exe） |
| 478 | 11-02 | `trae-cn-user-x64` | Trae 运行暂存（今日） |
| 384 | 11-01 | `k60probe` | K60 项目探测产物 |
| 306 | 10-29 | `ocrvenv` | OCR venv |
| 197 | 10-28 | `kernel.development.sweet.*` | K60 内核构建产物 |

## 2. 隐形大户排查结果

| 项 | 结果 |
|---|---|
| WSL `ext4.vhdx` | **在 `D:\Android\wsl\Ubuntu-24.04`**（注册表 BasePath 确认），不占 C:。发行版 Ubuntu-24.04 Running 中 |
| Docker vhdx | 不存在 |
| `SoftwareDistribution\Download` | ≈0 MB（已空） |
| `C:\Windows\Minidump` / `MEMORY.DMP` | 不存在 |
| 回收站（全部 4 个 SID） | 0 |
| npm 缓存 | ≈0 |
| pip 缓存 | 不存在 |
| uv | `Roaming\uv\python` 179 MB 是 **uv 管理的 Python 解释器**（非缓存，删了引用它的 venv 会坏）→ 需用户决定 |
| cargo 缓存 | `.cargo\registry` 139.6 MB → 可安全删除 |
| go / gradle / maven / conda / nuget | 不存在或 ≈0 |
| 浏览器缓存（Edge/Chrome/Firefox cache2） | 不存在或 ≈0（Firefox Roaming 185 MB 是配置档案非缓存） |
| `.trae-cn`（plugins 82 MB + attachments 14 MB） | 113 MB，只统计不删 |

## 3. 三档处置方案

### A. 可安全删除（本次执行）

| 项 | 预计回收 | 命令 | 风险 |
|---|---|---|---|
| 用户 Temp >7 天文件 | ~0.05 GB | `Get-ChildItem $env:TEMP -Recurse -File -Force \| ? LastWriteTime -lt (Get-Date).AddDays(-7) \| Remove-Item -Recurse -Force -EA SilentlyContinue` | 被占用文件自动跳过（报错即跳过），无风险 |
| `C:\Users\defaultuser0\AppData\Local\Temp` >7 天 | ~0.11 GB | 同上换路径 | 残留配置档临时文件，无风险 |
| cargo registry 缓存 | ~0.14 GB | 删除 `~\.cargo\registry\{cache,src,index}` 内容 | 下次 build 重新下载，无数据损失 |
| 回收站 | 0 | `Clear-RecycleBin -Force -EA SilentlyContinue` | 已空 |
| SoftwareDistribution\Download | 0 | 复核为 0，**跳过**（无需停 wuauserv） | — |
| 崩溃转储 | 0 | 不存在 | — |
| 浏览器缓存 | 0 | 不存在 | — |
| **A 类合计** | **~0.3 GB** | | |

> 说明：Temp 大头（azuma_4k_work、DiagOutputDir 等 4.6 GB）均 ≤7 天，按「保留 7 天内」规则**不在 A 类**，列入需用户决定。

### B. 系统组件清理（本次执行）

```cmd
DISM /Online /Cleanup-Image /StartComponentCleanup
```

- 预计回收：**≈0**。`/AnalyzeComponentStore` 显示 Reclaimable Packages = 0、Cleanup Recommended = No（今天 03:35 已自动清理）。执行一次以验证并报告实际值。
- **不执行 `/ResetBase`**（会使已装更新不可卸载）。
- 风险：无；耗时几分钟。

### C. 需压缩类（本次只出方案，不执行）

**WSL vhdx 不在 C: 而在 `D:\Android\wsl\Ubuntu-24.04`，对 C 盘无贡献。** 若日后要压缩 D: 上的 vhdx（**必须先确认 WSL 里无构建任务**）：

```powershell
wsl --shutdown
# Hyper-V 模块可用时：
Optimize-VHD -Path "D:\Android\wsl\Ubuntu-24.04\ext4.vhdx" -Mode Full
# 无 Hyper-V 模块时：
diskpart
> select vdisk file="D:\Android\wsl\Ubuntu-24.04\ext4.vhdx"
> attach vdisk readonly
> compact vdisk
> detach vdisk
> exit
wsl -d Ubuntu-24.04   # 重启验证
```

前置：先在 WSL 内 `sudo fstrim -av`（ext4 支持 TRIM 时 compact 才有效）。预计回收量 = vhdx 物理大小 − 发行版实际数据量，需届时实测。

### D. 页面文件/休眠文件（只报告，不改）

| 项 | 现状 | 可选项 |
|---|---|---|
| pagefile | 在 **D:**（系统管理 13.9 GB），C: 无 | 无需处理 |
| hiberfil.sys | 不存在（休眠未启用） | `powercfg /h off` 只能省 0；无需处理 |
| swapfile.sys | 0.25 GB，系统管理 | 不建议动 |

### E. 需用户决定（真正的大头，合计 ~20 GB）

| GB | 项 | 建议 |
|---|---|---|
| 5.61 | `Local\Python\pythoncore-3.14-64`（torch 占 4 GB） | 若 torch 不再用：`pip uninstall torch`；或整体重装到 D: |
| 4.84 | `.workbuddy`（logs/traces/changes-detail 约 1.0 GB 可清） | 需批准后方可清 logs/traces |
| ~4.6 | Temp 内 ≤7 天的大项（azuma_4k_work、DiagOutputDir、k60probe 等） | 确认是废弃产物后手动删 |
| 2.97 | `Local\Programs` | 卸载不用的软件才有效果 |
| 2.14 | `Documents` | 个人文件，只登记 |
| 1.43 | `ProgramData\LGHUB\cache+depots` | G HUB 更新缓存，删后会自动重下；需批准 |
| 0.89 | `ProgramData\Windhawk` | Windhawk mods，删=卸 mods |
| 0.71 | `.rustup` | `rustup toolchain list` 后卸不用的 toolchain |
| 0.70 | `Local\ms-playwright` | 可重下，需批准 |
| 0.76 / 0.65 / 0.61 | Tencent / .minecraft / AnkiProgramFiles | 应用数据，自行判断 |

## 4. 执行记录（2026-11-02 已执行）

| 步骤 | 动作 | 实际释放 |
|---|---|---|
| A1 | 用户 Temp 861 个 >7 天文件 | ~50 MB |
| A2 | defaultuser0 Temp 564 个 >7 天文件 | ~109 MB |
| A3 | cargo registry 缓存（cache/src/index 内容） | ~140 MB |
| A4 | Clear-RecycleBin | 0（本已为空） |
| A5 | SoftwareDistribution\Download | 0（复核为 0，跳过停 wuauserv） |
| **A 合计** | | **320 MB** |
| B | `DISM /StartComponentCleanup`（成功，未用 /ResetBase） | **≈0**（−4 MB，属噪声；与 Analyze 结论一致：今天 03:35 已自动清理，Reclaimable=0） |
| C | WSL vhdx | 未执行（vhdx 在 D:，且 WSL 中有构建任务；方案见 §3-C） |
| D | pagefile/hiberfil | 未改动（pagefile 在 D:；休眠未启用） |

## 5. 前后对比

| 指标 | 第一轮前 | 第一轮后 | 第二轮后 | 第三轮后 | 可删档后 | 累计变化 |
|---|---|---|---|---|---|---|
| C: 可用 | 37.68 GB | 37.99 GB | 40.09 GB | 42.81 GB | **43.59 GB** | **+5.91 GB** |
| C: 已用 | 62.52 GB | 62.21 GB | 60.08 GB | 57.36 GB | 56.51 GB | −6.01 GB |

## 6. 结论与待批准项

C 盘结构健康：无 >1GB 散落大文件、无转储、无更新残留、无还原点；**可自动安全清理的部分总共只有 ~0.3 GB，已全部清完**。真正占空间的 ~20 GB 全部属于软件本体、运行环境和个人/项目数据，需要逐项批准：

1. `Local\Python\pythoncore-3.14-64`（5.6 GB，torch 4 GB）— `pip uninstall torch` 可立省 ~4 GB，或把 Python 迁到 D:
2. Temp 近期大项（~4.6 GB：`azuma_4k_work` 2.4 / `DiagOutputDir` 0.9 / `trae-cn-user-x64` 0.5 / `k60probe` 0.4 / `ocrvenv` 0.3）— 确认废弃后即可删
3. `.workbuddy` 4.8 GB — logs/traces/changes-detail 约 1 GB 可清，需批准
4. `ProgramData\LGHUB\cache+depots` 1.4 GB — G HUB 更新缓存，需批准
5. `.rustup` 0.7 GB / `ms-playwright` 0.7 GB / `Windhawk` 0.9 GB — 按 §3-E 处理
6. 若仍紧张：卸载不用的软件（Program Files 11.2 GB + Local\Programs 3.0 GB）是唯一的大额来源

> 另注：`C:\Windows\Installer`（1.1 GB）网上有教程建议清空，**不要照做**——那会导致对应 MSI 软件无法卸载/修复/更新。

---

## 7. 第二轮（2026-11-02 晚）：用户拍板执行 + 调研方案

### 7.1 已执行（合计释放 2.10 GB）

| 动作 | 实际释放 | 说明 |
|---|---|---|
| 删 `C:\ProgramData\LGHUB\cache` + `depots` 内容 | **1,427.9 MB** | 只清了更新下载暂存（depots 为哈希名更新包，无 exe/dll）；配置 json 与 `C:\Program Files\LGHUB` 程序本体未动。删除时 lghub_agent/tray/updater 在运行，无文件被占用，全部清净。G HUB 下次更新会自动重下 |
| 删 `C:\Users\Emilelu\.rustup` | **725.8 MB** | 删前检查 cargo/rustc/rustup/rust-analyzer 无进程运行。`.cargo` 保留（bin 里还有用户装的 cargo 工具 12 MB） |
| PyTorch（torch 4 GB） | **保留未动** | 本地扩图 AI 模型要用 |
| Windhawk（0.89 GB） | **保留未动** | 用户拍板 |

### 7.2 调研：`.workbuddy`（4.84 GB，WorkBuddy 工作目录）

**结构判定**（newest 为最新文件 mtime）：

| MB | 目录 | newest | 用途判定 | 类别 |
|---|---|---|---|---|
| 1,529 | `workspace\sessions` | 今天 | 各会话工作区（≤7天 576 / **>30天 953**）。最大的 265b71a5=680MB(今天活跃)、38ba16bf=575MB(10-28) | 部分历史可归档 |
| 650 | `binaries\node` | 今天 | agent 的 Node 运行时（下载产物，可再生，但每次运行必需） | **保留** |
| 468 | `plugins` | 今天 | cache 262（含在用的 playwright-cli，可重下）+ marketplaces 199（可重下）+ data | 可再生，但含在用件 |
| 400 | `projects` | 今天 | 各项目/会话的元数据与索引（单项 ≤91MB），删了无法恢复旧会话上下文 | **保留** |
| 395 | `traces` | 今天 | 诊断追踪（≤7天 202 / 8-30天 188） | **可删** |
| 302 | `changes-detail` | 今天 | 检查点差异快照（**>30天 261**），用于会话回滚 | 老的可归档 |
| 294 | `app` | 今天 | 应用本体数据：session 215（保留）、Crashpad 37（崩溃转储，可删）、playbook-covers 28（可删）、CodeCache 13（可再生，可删） | 混合 |
| 291 | `logs` | 今天 | 运行日志（289MB 是近 7 天的） | **可删** |
| 244 | `blobs` | 11-01 | 内容寻址附件库（会话引用的图片/文件），无法安全甄别孤儿 | **保留** |
| 123 | `clipboard-images` | 11-01 | 用户贴图（107MB 是近 7 天的）——**用户成果** | **保留** |
| ~150 | 其余 30+ 小目录 | — | file-history 49 / connectors-marketplace 48（09-23 快照，可重下）/ file-tree-manifests 47 / cache 23 / shell-snapshots 12 等 | 混合 |

**处置方案（待确认）**：

| 档位 | 内容 | 预计释放 |
|---|---|---|
| **建议删除**（纯诊断/可再生缓存） | logs 291 + traces 395 + app\Crashpad 37 + app\CodeCache 13 + app\playbook-covers 28 + plugins\cache 262 + connectors-marketplace 48 + cache 23 | **~1.10 GB** |
| **建议归档到 E:**（历史会话，归档后旧会话无法在 WorkBuddy 内恢复/回看，但文件还在） | workspace\sessions 中 >30 天部分 953 + changes-detail >30 天 261 + file-history >30 天 37 | **~1.25 GB** |
| **建议保留** | binaries 650（运行时）、projects 400、app\session 215、blobs 244、clipboard-images 123、sessions ≤30 天 ~576、plugins\marketplaces+data 206、credentials/security/memory/plans/tasks 等 | ~2.4 GB |

> 风险备注：① 删 `plugins\cache` 会把正在使用的 playwright-cli 一并删掉（下次使用自动重下，~数 MB，可接受）；② 任何删除都应在 **WorkBuddy 完全退出** 后进行，否则锁文件会跳过且可能写坏索引；③ 「归档到 E」= `robocopy /MOVE` 到 `E:\k60-work\archive\workbuddy-<日期>\`。

### 7.3 调研：Temp 近期产物（4.6 GB，逐项占用测试）

方法：逐文件尝试独占打开（ReadWrite+None，失败再试 Read+None 区分只读属性），结合 mtime 判断活跃性。**本轮未删任何文件。**

| MB | 项 | mtime | 占用 | 判定 | 建议 |
|---|---|---|---|---|---|
| 2,409 | `azuma_4k_work` | **今天 21:46** | 0 锁 | 4K 扩图流水线工作目录（10630 文件），几分钟前还在写——**活跃** | **保留** |
| 884 | `DiagOutputDir` | **今天 21:47** | **1 文件被锁** | 有进程正持有句柄——**活跃** | **保留** |
| 478 | `trae-cn-user-x64` | 今天 12:52 | 0 锁 | 单文件，Trae 安装/更新暂存；本体已在 `Local\Programs` 正常运行 9 小时未再访问 | **可删** |
| 384 | `k60probe` | 11-01 15:25 | 0 锁 | K60 项目探测产物，13 个文件 | **移 E:\k60-work** |
| 306 | `ocrvenv` | 10-29 | 0 锁 | Python venv，`python -m venv` + pip 可重建 | **可删**（近期还要跑 OCR 则保留） |
| 130 | `kernel.development.sweet.a` | 10-28 | 0 锁 | K60 内核构建产物 | **移 E:\k60-work** |
| 90 | `xnu-kernel.zip` | 10-30 | 0 锁 | K60 内核包 | **移 E:\k60-work** |
| 83 | `gh-artifact.3269073225.zip` | 10-31 | 0 锁 | GitHub artifact，`gh run download` 可再下 | **移 E:\k60-work** |
| 67 | `kernel.development.sweet.ctf` | 10-28 | 0 锁 | K60 内核 CTF 数据 | **移 E:\k60-work** |
| 57 | `sess-203b.jsonl` | 10-30 | 0 锁 | agent 会话日志 | **可删**（或随归档移 E） |

汇总：**可删 ~841 MB**（trae-cn-user-x64、ocrvenv、sess-203b）／**应移 E ~754 MB**（k60probe、sweet.a、sweet.ctf、xnu-kernel.zip、gh-artifact zip）／**保留 ~3.29 GB**（azuma_4k_work、DiagOutputDir，均活跃）。

### 7.4 调研：`ms-playwright`（699 MB）

- **使用方**：WorkBuddy/CodeBuddy 的 `playwright-cli` 插件（`C:\Users\Emilelu\.workbuddy\plugins\cache\codebuddy-plugins-official\playwright-cli\0.1.0`，`.in_use\` 里 10-27/10-28 有 8 个进程使用标记；`.workbuddy\.playwright-driver-node-reuse.done` 10-26）。
- **最后实际使用**：**2026-11-02（今天）**——目录内有文件今天 13:32、15:58 被写入；chromium-1248 / headless_shell / ffmpeg 浏览器二进制 mtime 10-31。`PLAYWRIGHT_BROWSERS_PATH` 未设置（用默认位置），C 盘无其他项目的 playwright 配置引用。
- **结论**：远未到 3 个月未用的门槛，agent 浏览器自动化正在用，**建议保留**。
- 若日后要删：`Remove-Item "$env:LOCALAPPDATA\ms-playwright" -Recurse -Force`；重装 = 在使用方项目里 `npx playwright install chromium`，或插件下次调用时自动拉取。

### 7.5 待用户确认清单

1. `.workbuddy` 三档方案（删 ~1.10 GB 诊断缓存 / 归档 ~1.25 GB 历史会话到 E / 保留其余）——确认哪几档、执行前需退出 WorkBuddy
2. Temp：可删 841 MB（trae-cn-user-x64、ocrvenv、sess-203b）+ 移 E 754 MB（K60 产物 5 项）
3. `ms-playwright` 维持保留，无需动作

---

## 8. 第三轮（2026-11-02 深夜）：按批准执行三档方案

### 8.1 已执行（本轮释放 2.72 GB，C: 可用 40.09 → 42.81 GB）

| 动作 | 实际释放 | 校验 |
|---|---|---|
| Temp 删除：trae-cn-user-x64 477.7 + ocrvenv 306.2 + sess-203b.jsonl 57.4 | **841.3 MB** | 删除后路径均不存在 |
| Temp 移 E：k60probe 384.0 + sweet.a 130 + sweet.ctf 67 + xnu-kernel.zip 90 + gh-artifact 83 | **754.0 MB** | 17 个文件移动前后逐文件 SHA256 比对，**0 失败**；manifest 见下 |
| `.workbuddy` 归档移 E：sessions 旧文件 952.9 + changes-detail 261.4 + file-history 37.3（共 4385 文件，>30 天，robocopy /MINAGE:30 /MOV） | **1,251.6 MB** | 逐项目文件数+字节数核对一致，源残留旧文件 0 |
| `azuma_4k_work`、`DiagOutputDir` | 跳过未动 | 仍活跃（另 agent 使用中） |

**Manifest**：`E:\k60-work\incoming\temp-k60-artifacts\MANIFEST.md`（17 文件哈希全 OK）
**归档位置**：`E:\k60-work\incoming\workbuddy-sessions-archive\{sessions,changes-detail,file-history}`（952.9 / 261.4 / 37.3 MB）

**过程记录（已纠正的操作失误）**：首次归档时误用 `robocopy /MAXAGE:30`（语义为"排除超过 30 天的文件"），把 521+1153 个**近期**文件移到了归档目录；立即用反向 `robocopy /MOVE` 全量回滚（changes-detail 恢复 1185 文件、file-history 恢复 3157 文件，与盘点值一致），再用 `/MINAGE:30` 正确移动旧文件。最终校验全部一致，无数据损失。

### 8.2 可删档执行结果（2026-11-02 深夜，释放 869.3 MB）

**PID 39304 身份核实**：`browser-extension-native-host.exe`（位于 `.workbuddy\browser-runtime\native-host\`），启动 21:50:47，父链 = `cmd.exe` ← **正在运行的便携版 Chrome**（`D:\Softwares\Daily\Chrome`，14 个进程，chrome.nativeMessaging 管道）。结论：不是 WorkBuddy 残留，而是**浏览器正在使用的 WorkBuddy 扩展原生宿主**。按规则：不杀、不连坐，跳过涉插件项。

**已删 7 项（全部清净，0 残留被占用）**：logs 291.1 / traces 395.0 / app\Crashpad 37.4 / app\CodeCache 12.6 / app\playbook-covers 28.3 / connectors-marketplace 48.2 / cache 22.8 = **835.5 MB，实际释放 869.3 MB**。

**因占用跳过 1 项（等用户处理）**：`plugins\cache`（**~262 MB**，内含正在配合浏览器扩展工作的 playwright-cli）。待 Chrome 关闭或用户确认该扩展可中断后，删除此目录即可（下次使用自动重下）；playwright-cli 本次未动，完好可用；PID 39304 全程未受影响、未杀任何进程。

### 8.3 .workbuddy 当前剩余（~3.6 GB）与下一步可选项

| MB | 剩余项 | 下一步选项 |
|---|---|---|
| ~650 | `binaries\node` 运行时 | 保留（每次运行必需）；若 WorkBuddy 支持多版本，可让它自清旧版本 |
| ~576 | `workspace\sessions` ≤30 天活跃部分 | 随时间自然变老，可每月跑一次 `/MINAGE:30` 归档 |
| ~468 | `plugins`（marketplaces 199 + data + 重下的 cache） | 保留 |
| ~400 | `projects` 项目元数据 | 保留（删=丢会话上下文） |
| ~395 | `traces` | 可删档一部分，随 8.2 执行 |
| ~294 | `app`（session 215 保留，Crashpad/CodeCache/covers 随 8.2 清） | — |
| ~291 | `logs` | 随 8.2 执行 |
| ~244 | `blobs` 附件库 | 保留（内容寻址无法甄别孤儿；若官方出自清理工具再清） |
| ~123 | `clipboard-images` 用户贴图 | 保留（用户成果） |
| ~150 | 其余小目录 | 保留 |

> 下一轮可再做：① 8.2 的可删档（等 WorkBuddy 退出）；② 每月定期归档 sessions 旧文件；③ Temp 的 azuma_4k_work/DiagOutputDir 待对应任务结束后再评估（当前 ~3.3 GB）。
