# D 盘空间盘点（WSL 专题）

- 日期：2026-11-03（只读盘点，未删/未移/未关机/未 compact）
- 结论先行：**D 盘是 WSL 的 `ext4.vhdx`（56.6 GiB 且今天还在写）+ pagefile.sys 自增到 22.5 GiB 撑起来的；凌晨还有一次性的 ~11.6 GB PowerPaint 模型下载缓存。**

## 1. 容量对照

| 盘 | 总量 | 已用 | 可用 |
|---|---|---|---|
| C: | 100.2 GiB | 63.6 | 36.6 |
| **D:** | **376.0 GiB** | **348.3** | **27.7** ⚠ |
| E: | 178.1 GiB | 70.8 | **107.3** |

D 盘构成：`Softwares` 155.6 + `Files` 110.9 + `Android` 56.9（= 56.6 vhdx + k60-ios 0.2 + platform-tools）+ pagefile.sys 22.5 + 杂项 ≈ 348 GiB。

## 2. 最近 24h 写入者（>100 MB，全盘扫描）

| MB | mtime | 路径 | 归属判定 |
|---|---|---|---|
| 58,003 | 11-03 23:02 | `D:\Android\wsl\Ubuntu-24.04\ext4.vhdx` | **WSL 构建/会话写入**（动态盘只增不减） |
| 23,014 | 11-03 22:52 | `D:\pagefile.sys` | 系统页面文件（系统管理，从 13.9 GB 自增到 22.5 GB） |
| ~11,600 | 11-03 01:21–01:30 | `D:\Files\System\caches\powerpaint\...`（7 个模型文件） | PowerPaint/BrushNet 扩图模型，一次性下载缓存（配合 C: 的 torch 用） |
| 252 | 11-03 00:54 | `D:\Files\Projects\nvidia-macos-driver\out\...tar.gz` | 项目打包产物 |
| 108 | 11-03 21:55 | 网易云音乐 Cache | 应用缓存 |

**一句话：这次 D 盘是 `Ubuntu-24.04` 发行版的 ext4.vhdx（内部 `/tmp` 两个 4.8G 的 `os-*.bin` + `k60build/out` + `usb-a-stage/out` 等构建产物）和 pagefile.sys 一起撑起来的；PowerPaint 模型是一次性事件。**

## 3. WSL 发行版与 vhdx

| 发行版 | 状态 | vhdx 路径 | vhdx 文件大小 | 内部用量 (df) | 差值 |
|---|---|---|---|---|---|
| Ubuntu-24.04（WSL2，唯一发行版） | Running | `D:\Android\wsl\Ubuntu-24.04\ext4.vhdx` | **56.64 GiB** | **64 GiB** | **−7.4 GiB** |

- 差值为负：vhdx 物理文件已小于内部逻辑用量（动态盘块复用/延迟分配），**现在 compact 几乎回收不到东西**；要释放 D 盘必须先删/移内部数据，再 fstrim + compact，或直接迁移。
- `.wslconfig`：当前 `sparseVhd=false`（fstrim 不会自动回收到宿主机）、memory=10GB、swap=4GB。后续可改 `sparseVhd=true` 让 vhdx 随 TRIM 自动缩。
- 压缩工具链：Hyper-V PowerShell 模块**未安装**（无 `Optimize-VHD`）；有**管理员权限** → 可用 `diskpart compact vdisk`。
- E 盘上**没有**任何发行版 vhdx。

## 4. WSL 内部 Top 目录（du，64 GiB）

| 大小 | 路径 | 性质 | 处置建议 |
|---|---|---|---|
| 4.8G | `/tmp/os-py.bin` | 构建中间产物（04:33 写完，无进程占用） | 可删（可再生）★需用户确认 |
| 4.8G | `/tmp/os-dd.bin` | 构建中间产物（04:31 写完，无进程占用） | 可删（可再生）★需用户确认 |
| 4.1G | `/tmp/k60build/out` | k60build 构建输出（10-31） | 可删（重跑可再生）★ |
| 3.0G | `/tmp/usb-a-stage/out` | USB-A 阶段输出（11-02） | 可删（可再生）★ |
| 9.2G | `~/k60-data-build/wsl2-kernel` | WSL2 内核构建树 | 移 E 或保留（重建耗时长，用户定） |
| 7.5G | `~/k60-archive/images`（含 cryptex dmg 2.5G） | **取证存档镜像，不可再生** | **移 E，不删** |
| 4.8G | `~/k60-archive/data`（data2g 安装镜像 2.0G 等） | **存档镜像** | **移 E，不删** |
| 3.7G | `~/k60-archive/probes` | 探测存档 | 移 E |
| 6.5G | `~/hackios/UniXNU/out/ipsw/20G81/*.dmg`（4.0+2.5G） | IPSW 提取物 | 源 ipsw 还在则可重提→可删；否则移 E |
| ~6.5G | `~/hackios` 其余（uefi-pong 3.2G、uefi-mondrian 1.9G 等） | git 仓库 + .git 对象 | **不动** |
| 0.5G | `/var/cache/apt` | apt 缓存 | `sudo apt clean`，可删 |
| 61M | `/var/log` | 日志 | journalctl 清理，可删 |
| 24M | `~/.cache`（pip 24M） | 缓存 | 太小，忽略 |

## 5. 挂载现状（"WSL 里能不能写到其他盘"——能，已挂着）

- `/etc/wsl.conf`：只有 `[user] default=emilelu`，无自定义挂载。
- 已自动挂载（drvfs/9p）：`/mnt/c /mnt/d /mnt/e /mnt/f /mnt/g /mnt/h /mnt/i /mnt/s`。**写 `/mnt/e` 即写 E 盘**，Windows 侧立即可见。
- 注意性能：9p/drvfs 小文件与 git/构建 IO 比 ext4 慢一个量级 → **存档/镜像适合放 `/mnt/e`，构建树不适合**。
- vhdx 内（ext4）：`/` 全部（含 /tmp、/home）。

## 6. 执行方案（分步；② 开始会中断 WSL 会话与构建，必须用户点头后才动）

① **内部清理**（不需要 shutdown，但构建相关的要等构建结束）：
- 可删（可再生，~17.2 GiB）：`/tmp/os-py.bin`、`/tmp/os-dd.bin`、`/tmp/k60build/out`、`/tmp/usb-a-stage/out`、`sudo apt clean`
- 移 E（不可再生存档，~16 GiB）：`~/k60-archive` 整树 → `/mnt/e/k60-work/archives/k60-archive`（robocopy/rsync 校验后删源）
- 预计内部从 64 GiB 降到 ~31 GiB

② `wsl --shutdown`（**副作用：中断所有 WSL 会话与正在进行的构建**）

③ `wsl -d Ubuntu-24.04 -u root -- fstrim -av`（或关机后下次启动时做）

④ compact（二选一）：
```powershell
# 无 Hyper-V 模块 → diskpart（有管理员）
diskpart
> select vdisk file="D:\Android\wsl\Ubuntu-24.04\ext4.vhdx"
> attach vdisk readonly
> compact vdisk
> detach vdisk
> exit
```
- 预计：清理+迁移做完后 vhdx 从 56.6 → **~31–35 GiB，D 盘释放 ~21–25 GiB**
- 可选：`.wslconfig` 改 `sparseVhd=true`，以后 fstrim 自动缩，不用再 compact

## 7. 【独立小节】发行版迁移 D→E 评估（不执行）

### 7.1 空间需求

| 方案 | 过程文件 | 新 vhdx | E 盘峰值需求 | 107 GiB 空闲是否够 |
|---|---|---|---|---|
| 不清理直接 export/import | tar ≈64 GiB（不压缩） | ~64+ GiB | ~128+ GiB | **不够** ✗ |
| **先按 §6-① 清理+移 E 再迁** | tar ≈31 GiB | ~35 GiB | ~70–80 GiB | **够** ✓ |
| `wsl --export ... --vhd`（Win11 新版 wsl） | vhdx 副本 56.6 GiB | 直接注册 | ~57 GiB | 够 ✓ |
| `wsl --import-in-place`（WSL ≥2.4.4）：shutdown 后 `robocopy /MOVE` 把 vhdx 搬到 E 再原地注册 | 无 | 复用原文件 | 几乎为 0 | 最优，但需先验证 wsl 版本支持 |

### 7.2 步骤（export/import 路线）

```powershell
wsl --shutdown                                                    # 停机窗口开始
wsl --export Ubuntu-24.04 E:\k60-work\wsl-export\Ubuntu-24.04.tar
wsl --import Ubuntu-24.04 E:\wsl\Ubuntu-24.04 E:\k60-work\wsl-export\Ubuntu-24.04.tar --version 2
wsl -d Ubuntu-24.04 -u root -- echo OK                            # 校验能启动
# 进系统重建默认用户（import 后默认 root）：在 /etc/wsl.conf 写回 [user] default=emilelu
# 校验 ~/hackios 各仓、/tmp/k60build、构建命令可跑
wsl --unregister Ubuntu-24.04-old                                 # 仅在新实例验证全过后
```

### 7.3 停机窗口

- export（读 56 GiB）+ import（写 ~31–64 GiB）+ 校验 ≈ **30–60 分钟**，期间所有 WSL 会话/构建中断。

### 7.4 风险清单与回滚

| 风险 | 对策 |
|---|---|
| 丢数据 | **tar 与 D 盘旧 vhdx 都保留到新实例验证通过**；回滚 = 不 unregister，或从新 tar 重新 import |
| 默认用户丢失 | import 后 `/etc/wsl.conf` 重写 `[user] default=emilelu` |
| `~/hackios`、`/tmp/k60build` 完整性 | 迁移后 `git -C ~/hackios/UniXNU status`、构建冒烟 |
| `.wslconfig` | 全局文件（在 C:），迁移不受影响，照常生效 |
| 注册表 BasePath | import 自动指向 E 新路径，无需手工改 |

### 7.5 迁移后影响面

- `/mnt/c|d|e|f...` 是全局 drvfs 自动挂载，**与发行版位置无关，完全不变**。
- 发行版内部路径（`/home/emilelu/hackios/...`）原样保留 → **写死 Linux 路径的脚本不受影响**。
- 仅 Windows 侧写死 `D:\Android\wsl\Ubuntu-24.04\...` 的东西（文档、备份脚本、项目记忆）需要改指向 E。

### 7.6 替代方案对比

| 方案 | 性能 | 复杂度 | 适用 |
|---|---|---|---|
| 直接写 `/mnt/e`（已挂） | 9p，慢（小文件/git 尤其差） | 零 | **存档/镜像/产物包**（如 k60-archive 16G） |
| 数据 vhd 挂 `/work`（`wsl --mount --vhd`） | ext4 原生，快 | 中（持久化要启动脚本，wsl.conf 无原生支持） | 大型构建树 |
| **发行版整体迁 E** | 原生 | 一次性 30–60 min | **治本**，D 盘永久释放 56.6 GiB |

**推荐**：短期先按 §6-① 把 `k60-archive` 16 GiB 挪到 `/mnt/e`（今天就能做，零停机）；构建窗口空档再做发行版整体迁 E（优先试 `import-in-place`，退回 export/import）。日常约定维持"大产物只写 E:\k60-work"。

## 8. D 盘三档释放预估

| 档 | 项 | 预计 |
|---|---|---|
| 无风险（需 shutdown 窗口） | §6 内部清理 17.2G + compact → vhdx 瘦身 | **~21–25 GiB** |
| 需确认 | `/tmp/os-*.bin`（构建是否已结束）、`UniXNU/out/ipsw` dmg（源 ipsw 是否在）、`k60-data-build/wsl2-kernel` 9.2G、PowerPaint 11.6G（在用的模型，建议留） | ~15–27 GiB |
| 绝对不能动 | `pagefile.sys`（系统）、`~/hackios` 仓库与 `.git`、`k60-archive`（只移不删）、`D:\Softwares`、`E:\k60-work` 备份 | — |
