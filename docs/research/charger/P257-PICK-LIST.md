# P-257 待拣清单

2026-11-21 记。P-257 的两个提交在 `feat/power-ios27-branch` 上，但不在 `main` 的
`4b744c2e` 上；它们与 27 迁移无关，是 16.6.1 工具链的独立修复。F1 之后由 Lead 下令按
下面的顺序拣回 `main`，**不要整分支合并**。

## 1. 拣哪两个

| 顺序 | 提交 | 文件 | 为什么属于 main |
|---|---|---|---|
| 1 | `f535a0a0` fix(scripts): name both hunk-count directions and refuse a post-0619 tree up front | `scripts/check-patch-hunk-counts.py`（`--root` 与 `patches(explicit, root)`，两种 hunk 方向分别报）<br>`scripts/tests/run-k60-handoff-host.sh`（开头拒绝 post-0619 树，usage 要求 pre-0619 树）<br>`scripts/tests/test-patch-hunk-counts.py`（声明少/声明多两条各自判红） | 这是 16.6.1 handoff 线自身的门禁修复：旧脚本把“补丁声明比实际多”和“实际比声明多”混成一句，且 handoff host 套件在 post-0619 树上会给出看似通过的假绿。两个问题都不依赖 27。 |
| 2 | `5f56137f` fix(patches): count the lines the smccc stanza and the wifi defconfig added | `patches/xnu/0613-k60-adsp-pas.patch`（`@@ -0,0 +1,90` → `+1,96`）<br>`patches/wifi/0007-configs-mondrian-wifi-defconfig.patch`（`@@ -0,0 +1,71` → `+1,73`） | 两个补丁的 hunk 头少写了实际新增行数，`check-patch-hunk-counts.py` 会因此报错。修的是 16.6.1 补丁本身，与 27 镜像、27 账本无关。 |

两个提交都满足：在 `feat/power-ios27-branch` 的历史里，不在 `main` 的历史里
（`git merge-base --is-ancestor <sha> main` 退出 1）。拣回时按 1 → 2 顺序
`git cherry-pick -x`，保留原提交说明与来源。

## 2. 为什么不能整分支合并

`feat/power-ios27-branch` 还带着只有 27 线才成立、且尚未上机的东西：

- `docs/research/power/LANE-CONFORMANCE.toml` 的 41 行 27 对齐表（verified 32 / partial 9）；
- `docs/research/eight-step/power-27.toml` 的三块七步 27 账本与 `[hardware.power]` 的 w11 记录；
- 27 专用的 `check-ios27-power-preflight.py`、`check-pac-probe-capture.py`、`check-sleep-report-build.py`；
- `docs/research/charger/W11-FLIGHT-PACK.md` / `W11-IMAGE.toml` 与 27 侧 PMIC 改线工单。

把这些整体并进 `main` 会把未飞过的 27 材料变成 16.6.1 基线的“已合并”状态，违反
“main 只带可构建/可启动基线”的约束。只拣上面两个提交，其余留在 27 分支。

## 3. 前置与验收

- 前置：F1 关闭（Lead 确认 prelink/150 个地址）；本文件不授权任何构建或上机。
- 拣回后：`python3 scripts/check-patch-hunk-counts.py` 与
  `python3 scripts/tests/test-patch-hunk-counts.py` 必须绿；
  `bash scripts/tests/run-k60-handoff-host.sh` 在 pre-0619 树上必须按 usage 接受、在
  post-0619 树上必须拒绝而不是假绿。
- 不做：不把 27 的 41 行表、七步账本、w11 包或任何 27 checker 带入 `main`。
