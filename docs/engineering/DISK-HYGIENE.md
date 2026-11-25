# 磁盘卫生（空间门禁与回收流程）

这条规矩是因为同一件事被提醒了三次才写下来的：构建跑到一半磁盘满、`/opt/k60/trees`
每棵线各留一份 17–18 GiB 的旧 `out-*`、`E:\iOS Port\Work\scratch` 里躺着
24,141,365,248 B 的 `data-window.img`（一次性副本，构建从未引用）。清理总是等用户开口才开始。

现在的做法：**门禁自己看**。`scripts/check-disk-space.py` 和别的门禁一起跑（`hard-41`），
不通过就 `❌ 阻断`，不需要任何人提醒。

## 1. 门禁判据

| 位置 | 阻断线 | 提醒线 |
| --- | --- | --- |
| `E:`（仓库、`k60-work`） | 可用 < 8 GiB | 可用 < 25 GiB |
| `D:`（WSL 虚拟盘所在） | 可用 < 10 GiB | 可用 < 30 GiB |
| WSL 根分区 `/` | 可用 < 12 GiB | 可用 < 30 GiB |
| WSL 虚拟盘 vs 盘内数据 | — | 虚拟盘比数据大 > 30 GiB（说明删掉的文件没还给 Windows） |

```bash
python3 scripts/check-disk-space.py            # 全部
python3 scripts/check-disk-space.py --vhdx-only
python3 scripts/tests/test-check-disk-space.py # 16 例
```

「虚拟盘 vs 数据」这一行是关键：2026-11-17 那天 WSL 里只剩 60 GiB 数据，虚拟盘却是
161.53 GB —— 空间不是被数据占着，是被删除后没有回收的块占着。

## 2. 回收顺序（从便宜到贵）

1. **`fstrim`**：`wsl -u root -e bash -lc 'fstrim -av'`。把已删除块告诉虚拟盘。
2. **删可再生产物**：`/opt/k60/trees/*-out`、`/opt/k60/trees/k60build/out-*` 里除当前
   `K60_OUT` 以外的目录；`E:\iOS Port\Work\artifacts` 里同一系列只留最新一两张。
   判据是「能不能从仓库 + `build-strict.sh` 重建」，不是「看起来没用」。
3. **删一次性副本**：任何 `*.img` / `*.bin` 只要构建与门禁都不引用就可以删；
   删之前 `grep -rn '<文件名>' --include=*.py --include=*.sh --include=*.toml` 确认零引用，
   并在 `docs/YIBIYA-FORK-REFERENCE.md` 之类登记处标注删除日期。
4. **压虚拟盘**（见下节）。这一步才真正把空间还给 Windows。

## 2.5 谁来删：`scripts/k60-janitor.py`

`hard-41` 只回答「还剩多少」，它会在快满时阻断，但**从不回收**。回收由
`scripts/k60-janitor.py` 负责，默认 dry run：

```bash
python3 scripts/k60-janitor.py                 # 打印计划，不删
python3 scripts/k60-janitor.py --apply         # 执行（镜子属 root 时用 root 跑）
python3 scripts/k60-janitor.py --apply --json  # 定时任务用
```

规则（`scripts/tests/test-disk-guards.py` 五项断言）：

- 每个 `${前缀}-${8位日期+后缀}` 只留**最新 `--keep`（默认 2）个**，且只删比
  `--days`（默认 3）更旧的——闲了一周的分支，它最后一次输出可能还要回答问题；
- `/tmp` 只删超过 `--hours`（默认 24）的条目，**永不删符号链接**，
  并且**保护被链接指向的构建树**（`/tmp/k60build`、`/tmp/fakeroot` 都指向树里）；
- 镜子与输入（`k60build`、`gates-device`、`usb-cdc-mainline`、`gates-out`）写死在保护名单。

2026-11-19 首次运行实测：`/opt` 94 → 24 GB、`/tmp` 30 → 13.7 GB，盘内 183 → 121 GB。

## 3. 压 WSL 虚拟盘（需要管理员）

虚拟盘在 `D:\Android\wsl\Ubuntu-24.04\ext4.vhdx`。`diskpart` 必须提权，非管理员运行会
**静默失败并留下 attach 状态**，之后 `wsl --manage --set-sparse` 一直报
`ERROR_SHARING_VIOLATION`，连 WSL 都起不来（2026-11-17 实际踩过）。

脚本 `compact-vhdx.txt`（每行一条）：

```
select vdisk file="D:\Android\wsl\Ubuntu-24.04\ext4.vhdx"
detach vdisk
select vdisk file="D:\Android\wsl\Ubuntu-24.04\ext4.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
```

执行（UAC 会弹窗）：

```powershell
Start-Process -FilePath diskpart -ArgumentList '/s','<path>\compact-vhdx.txt' -Verb RunAs -Wait
```

跑完再开 sparse 并 trim：

```powershell
wsl --shutdown
wsl --manage Ubuntu-24.04 --set-sparse true
```

```bash
wsl -u root -e bash -lc 'fstrim -av'
fsutil sparse queryflag "D:\Android\wsl\Ubuntu-24.04\ext4.vhdx"
```

实测：161.53 GB → 62.05 GB，`D:` 可用 83.6 → 183 GiB。
（`--set-sparse` 会提示 "Sparse VHDs are currently experimental"，属正常。）

## 4. 常见坑

- `ls -la` 给的是逻辑大小，判断真实占用要看 `fsutil sparse queryflag` 与 `Get-PSDrive`。
- MSYS 下 `powershell -NoProfile -Command` 会把 `$_` 吃掉（`Missing argument in parameter list`），
  复杂脚本一律写 `.ps1` 再用 `-ExecutionPolicy Bypass -File` 跑。
- `wsl --manage --set-sparse` 必须在 `wsl --shutdown` 之后、且虚拟盘没有被 attach 时执行。
- 删除前先确认不是 `build-strict.sh --fd` 的 FD、不是当前 `K60_OUT` / `K60_DEVICE_INPUT`、
  不是刚上机那张图的证据目录。

## 3.5 一条命令压缩（2026-11-20 起）

上面那套顺序（`wsl --shutdown` → `--set-sparse false` → diskpart compact → `--set-sparse true`）
已经包进脚本，不要再手敲：

```powershell
# 在仓库根目录：会弹一次 UAC（只有 diskpart 那半需要提权），跑完自动恢复 sparse
.\scripts\compact-wsl.ps1

# 双击版（等价，末尾 pause 好看结果）
.\scripts\compact-wsl.cmd

# 只看它会做什么，不动任何东西
.\scripts\compact-wsl.ps1 -WhatIf
```

脚本自己做的事，正是手敲容易漏的四个点：

1. `wsl --shutdown` 之后等 5 秒再动文件（否则 diskpart 报 `being used by another process`）；
2. **只把自己提权重启**，`--set-sparse` 的开关留在非提权窗口，跑完在 `finally` 里恢复 `--set-sparse true`；
3. 用 `cmd /c diskpart /s ... > log` 提权（`Start-Process -Verb RunAs` 不能同时 `-RedirectStandardOutput`，
   直接写会报 `Parameter set cannot be resolved`），所以 diskpart 的 100% 进度条也能落进日志；
4. 打完报告 `vhdx before -> after`、`D: 可用`、**以及 guest 里真占多少**——最后这个数是 vhdx 的物理下限，
   没有它就会以为「压完还是很大」是脚本没生效。

实测（2026-11-20）：`123.1 GiB -> 90.1 GiB`，`D:` 可用 `101.9 -> 134.9 GiB`，guest 80.3 GiB。

判定口径：**压缩只能去掉空洞，不能去掉数据**。压完 `vhdx ≈ guest used + 一点` 就是到底了；
要继续变小必须先删 guest 里的东西（见 §2 与 `scripts/k60-janitor.py`）。
