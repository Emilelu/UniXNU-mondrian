# 仓库分支地图（K60 iOS 移植，2026-11-03 收敛后）

> 收敛动作见 `DECISIONS.md` D-2026-11-03-17：每仓只留 `main`（+ `archive/*`），里程碑锚点全部转 annotated tag。
> remote 归属：mondrian/uefi 的 `origin` = 自有仓；fork 的 `origin` = org 只读，`fork` = Emilelu/UniXNU 自有可写。

## 1. UniXNU-mondrian（设备仓 + 内核主线）

**远端形态**（ls-remote 实证 2026-11-03）：

| 引用 | 尖端 | 职责 |
|---|---|---|
| `main`（默认分支） | `c39ff29` | **iOS16 主线** = 内核树（`v0.1.0-progressbar`/`66a603f`）+ merge 设备配置（`v0.1.1-ios16-main-merged`/`3c1bea3`） |
| `archive/darwin24-main-20261103` | `10d1be3` | darwin24 45 提交存档 = iOS18 起点（路线决策 D-2026-11-03-14） |

**tags**：`v0.0.9-premain-8598c97`（切换前 main 锚 `8598c97`）、`v0.1.0-progressbar`（内核基线 `66a603f`）、`v0.1.0-progressbar-device`（设备基线 `48abe35`）、`v0.1.1-ios16-main-merged`（设备线合入点 `3c1bea3`）、`v0.2.0-darwin24-archive`（darwin24 线 `10d1be3`）。

**本地**：检出 `fix/k60-measured-high-window`（`d881352`，2026-11-04 晚 0301–0305 诊断补丁 `1c0f468` + B 决策 `d881352`；**均已推送 fork `origin/fix/k60-measured-high-window`**，远端尖端复核一致；工作区另有他路会话脏改动在跑）；另保留 `archive/darwin24-main-20261103`。已删：本地 `main`（旧 darwin24 线）、`baseline/*`、`ios16-main-20261103`（经前置核对与 origin/main 同 sha 后 `-D`）。a5-timeout 孤儿提交已判吸收删除（diff 存档 `docs/archive/a5-timeout-fef75ea.diff`）。

## 2. UniXNU fork（核心编排）

**远端形态**（fork remote）：

| 引用 | 尖端 | 职责 |
|---|---|---|
| `main` | `0fc0fc1` | fork 主干（跟随 org 的方向） |
| `k60` | `db7177c` | 编排基线（= `v0.1.0-progressbar-core`）。**保留原因：fork 固有分支，非我方工作线** |
| `k60build` | `066a3da` | **现役构建编排分支**（db7177c + 4 整理提交），检出在 `/tmp/k60build` |

**tags**：`v0.1.0-progressbar-core`（`db7177c`）。

**本地**：`k60build`（在用）；`main`/`smp-0340`（其他 worktree 检出中，未动）。子模块 `kits/XnuPrelink` 本地提交 `d2e15c8`（**远端不可获取，换机需带工作副本**）。

## 3. uefi-mondrian（固件）

**远端形态**：

| 引用 | 尖端 | 职责 |
|---|---|---|
| `main` | `e06211d` | 固件主线（= `v0.1.0-high-window-fd`） |

**tags**：`v0.1.0-high-window-fd`（`e06211d`）、`v0.1.1-fd-darwin22`（`6244582` = Darwin22 boot_args + XNU High Arena）。

**本地**：检出 `fix/k60-measured-high-window`（`6244582`，出货 FD 依赖；远端同名分支已删，tag `v0.1.1-fd-darwin22` 锚定）。子模块 `Mu_Basecore` 本地提交 `3d2a9fa`（**远端不可获取**）。已删本地 `main`/`baseline/*`。

## 4. ios-sweet-k60（参考/协作，本轮未动）

`main`（`3fbaa5e`，工作区 30+ 触摸/显示探针未提交改动在用）；`ci/macos15`、`probe/runner` 过期。tag `v0.1-lockscreen`（`d11a3c0`）。

## 5. PongUfs（驱动 feed）

无本地克隆；构建经 feed 缓存钉 `c959284`（unixnu.lock 已钉）。远端 `main` 领先 3 未跟进。

## 6. UniXNU-sm8475-common（平台公共层）

`main` @ `d0c90f1`，本地=远端，干净。

---

## 当前实际在用的一组（一次 `fastboot boot` 牵动什么）

| 环节 | 来自哪 | 状态 |
|---|---|---|
| **远端主线** | `UniXNU-mondrian` `main` @ `c39ff29` | 已切换（11-03） |
| **内核源树** | xnu-work 现役树（detached @`1b191cb` + 125 脏路径）= tag `v0.1.0-progressbar`（`66a603f`） | 已归档推送 |
| **123+4 补丁清单** | `patches/xnu/series`（123 项，含于 main） | 已推送 |
| **设备配置** | mondrian 检出 `fix/k60-measured-high-window` @ `3c1bea3`（= tag `v0.1.1-ios16-main-merged`） | 已推送（已合入 main） |
| **构建编排** | `/tmp/k60build`（`k60build` @ `066a3da`，remote=`fork`） | 已推送 |
| **固件 FD** | uefi 检出 `fix/k60-measured-high-window` @ `6244582`（= tag `v0.1.1-fd-darwin22`） | 已推送 |
| **驱动 feed** | PongUfs @ `c959284`（unixnu.lock 钉） | 远端 main 领先 3 未跟进 |
| **平台 feed** | UniXNU-sm8475-common @ `d0c90f1` | 同步 |
| **子模块（本地提交）** | XnuPrelink `d2e15c8`、Mu_Basecore `3d2a9fa`（**仅本地，远端不可获取；换机需带工作副本**） | 父仓指针未 bump（刻意） |
| **打包** | `E:\k60-work\tools\package-textonly.py` + uefi 仓 `Resources/Scripts/mkbootimg.py` | 脚本在 E 盘 |
| **Data 卷** | 设备 unixnu 分区窗口（`data-window-20354.img` 已写入校验） | 非 git |
