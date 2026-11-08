# PUSH-BACKLOG — 自有仓待推送清单（给用户逐个画勾用）

> 数据：`push-check.py` 2026-11-04 08:44 实跑（fetch 后口径）。刷新：`python E:\k60-work\tools\repo-hygiene\push-check.py`。
> **本文件只供决策，任何人执行 push 前必须经用户点头；push 后请把对应行划线标注。**

## 1. UniXNU（fork，`~/hackios/UniXNU`；工作树另有 `/tmp/k60build`、`~/smp-core`）

### 1.1 `k60build` → `fork/k60build`：~~领先 7 条 / 落后 0~~ **已推送（2026-11-04 10:33）**
```
56e1da1 fix(ci): validate the porting record after force pushes
81d6ab3 fix(bootimg): verify Android v0 kernels after the header page
18bfe9d fix(scripts): verify v3 and v4 boot headers
4262056 fix(scripts): pass os_version and os_patch_level to mkbootimg
86b1a84 fix(package): connect controllers on every boot path
cbfbc88 fix(package): round a bootloader initrd up to a whole sector
cafab71 fix(vendor): restore pong platform build scripts
```
- [x] ~~push 命令：`git push fork k60build`~~ **已执行**：`066a3da..56e1da1` fast-forward；推后本地=远端=`56e1da1`，核对 0/0。证据：`references/upstream-watch/CHANGES-2026-11-04.md` 末节。
- 注意：`/tmp/k60build` 工作树还有 5 项未提交改动（kits/XnuPrelink 子模块、profile.toml、pong-driver/ 三目录）——**保持原样未动**。

### 1.2 `main` → `origin/main`（上游 org）：领先 1 / 落后 652
```
e3b3133 ci: opt-in upload of the native kernel
```
- [ ] **不要直接 push 到 origin（上游 org，非本人仓）**。若要保留：推去 fork——`git push fork main`（fork/main 与本地分叉：本地领先 1、落后 2，需先 merge/rebase，非快进）。
- 风险：高（上游历史已重构，见 UPSTREAM-SYNC；误推 origin 即事故）。

### 1.3 `smp-0340`：本地独占（远端无此分支）
- [ ] 首次推送：`git push fork smp-0340`（或在 fork 建仓分支）
- 风险：低；内容 = `4d6d0e4 k60: skip AppleARMCPU device-tree validation at prelink (0340)`。

## 2. UniXNU-mondrian（`~/hackios/UniXNU-mondrian`）

### `fix/k60-measured-high-window`：本地独占（origin 只有 main + archive/…）
- [ ] 首次推送：`git push -u origin fix/k60-measured-high-window`
- **状态：本轮（2026-11-04）暂不推，等用户单独批准。**
- 风险：低；但注意 8 项脏文件未提交（board.toml、defconfig、init.c、3 个新 patch 文件等），push 的只是已有 commit。

## 3. uefi-mondrian（`~/hackios/uefi-mondrian`）

### `fix/k60-measured-high-window`：本地独占（origin 只有 main）
- [ ] 首次推送：`git push -u origin fix/k60-measured-high-window`
- **状态：本轮（2026-11-04）暂不推，等用户单独批准。**
- 风险：低；`Mu_Basecore` 子模块脏 1 项不在范围。

## 4. ios-sweet-k60（`D:\Android\k60-ios\ios-sweet-k60`）

### 4.1 `main` → `origin/main`：领先 2 / **落后 55**
```
3fbaa5e ci: try macos-15 (macOS 14 is deprecated)
8c47846 k60: touch wiring from /k60-touch, ID readback, rpmh map-order fix
```
- [ ] **直接 `git push origin main` 会被拒（non-fast-forward，远端多 55 条）**。先 `git pull --rebase origin main` 或 merge，解完再推。**禁止强推（--force 一律不许）。**
- 风险：高——落后 55 条说明远端被别的线推进过，rebase 前先看 `git log main..origin/main` 里有什么。
- **结论（2026-11-04 确认）：push 必被 non-fast-forward 拒绝，需用户先裁定 rebase/merge 方案，在此之前一律不推。**

### 4.2 `ci/macos15`、`probe/runner`：本地独占
- [ ] `git push origin ci/macos15` / `git push origin probe/runner`
- 风险：低（新分支）。
- 另：脏工作区 31 项（xnu/patches 批量改动）未提交，不在范围。

## 5. PongUfs

- 本地无检出，远端 `main = 65f157c7`（ls-remote 实测）。无本地积压可推。
- [ ] 如需纳入管理：`git clone https://github.com/Emilelu/PongUfs.git` 后再评。

## 6. UniXNU-sm8475-common

- 干净、与远端同步。无动作。
