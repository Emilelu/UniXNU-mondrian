# UPSTREAM-SYNC — 上游跟进机制（拉别人仓 + 按坑反查 + 自己仓 push 检查）

> 本机制 2026-11-04 建立。目的：**别人踩过的坑不再重复踩**（unixnu.com/devices/ 已收录大量移植仓库），
> 自己仓库的进展不积压。三类动作全部由脚本执行、留痕可查；脚本只报告/只读镜像，push/merge 由用户拍板。

## 0. 铁律关联

- 本机制的一切结论遵守**铁律 5（调研驱动、证据等级）**：仓库归属/状态必须有实测证据
  （`.gitmodules` 原文、`git remote -v`、`git ls-remote` 的 sha、官网 devices 页原文），
  标注证据等级（**实测 / 文档 / 推断**），推断级不得写成结论。
- **铁律 6（实时优先、缓存仅作检索副本）**：判断「当前有哪些设备仓库/最新进展」必须以实时源
  （unixnu.com/devices/ 或 GitHub）为准；本地快照/缓存仅作检索副本，使用缓存时必须标注抓取时间。
- **pull 硬规矩**：任何 fetch/pull 前先记当前 HEAD，完成后记新 HEAD 与新增 commit 列表
  （落 `references/upstream-watch/CHANGES-<date>.md`），**不允许无记录地更新本地副本**。

## 1. 三类上游源

| 源 | 枚举方式 | 证据等级 |
|---|---|---|
| ① UniXNU 官方组织全量 | `https://api.github.com/orgs/UniXNU/repos`（含将来新增） | 实测（API 返回） |
| ② unixnu.com/devices/ 列出的全部设备仓（含同 SoC SM8475 与其它机型，动态发现新增） | `devices.py list`（实时页 / `docs/devices-map.json` 官网索引导出） | 文档（官网），`--verify` 后升实测 |
| ③ 已有本地参考克隆 | `E:\k60-work\references\*\` 的 git 仓库 | 实测（本地 .git） |

## 2. 工具与命令

### 2.1 设备枢纽 `tools/device-hub/devices.py`

```powershell
python E:\k60-work\tools\device-hub\devices.py list [--live] [--verify] [--write] [--fetch-pages]
python E:\k60-work\tools\device-hub\devices.py find "<关键词>" [--refresh]
python E:\k60-work\tools\device-hub\devices.py pull-check
```

- `list`：实时解析设备目录（设备名/SoC/维护者/仓库 URL/文档/页 URL），SM8475 与 K60 相关
  （mondrian×4、pong 等）自动高亮；`--verify` 对高亮条目做 ls-remote 实测；`--write` 落
  `docs/DEVICE-REPOS.md`（人读）+ `docs/device-repos.json`（机读），文件头含快照声明。
- 数据源优先级：`docs/devices-map.json`（官网索引会话导出）→ 缺失时回退实时抓取；
  `--live` 强制实时。实时源不可达时**明确报错退出**，不拿旧缓存冒充最新。
- `find "<关键词>"`：按坑反查。范围 = 设备索引页正文（实时）+ 设备页缓存（标年龄）+
  references/* 克隆的文档/源码/commit message（git grep / git log，只读）。
  输出含命中位置与**该仓克隆状态**。
  常用词：`SMMU`、`stream 0`、`trust cache`、`mount root`、`IOKitBSDInit`、`xpcproxy`、
  `78`、`prelink`、`secure boot`。
- `pull-check`：见 §2.2。

### 2.2 定期 pull 与增量核查（`pull-check`）

- 覆盖三类源；本地克隆一律**只读镜像**（只 fetch 远端引用，不动 HEAD/工作区/本地分支）。
- 只报**增量**：新仓库（首次发现）/ 新 ref / ref 删除 / tip 推进（附 commit 范围
  `old..new`、首父新增数——比对方式 `git rev-list --first-parent`、标题+作者+日期+变动文件数）。
- 落盘：`references/upstream-watch/CHANGES-<date>.md`（本轮报告）+ `state.json`（基线，
  防重复播报）+ `watch.log`（一行流水）。每轮记录全部 fetch/ls-remote 事件的 HEAD 前后值。
- **定时任务最小命令**（由主控挂载，本机制不自建系统任务）：

```powershell
python E:\k60-work\tools\device-hub\devices.py pull-check >> E:\k60-work\references\upstream-watch\watch-cron.log 2>&1
```

  建议频次：沿用「参考仓库上游变动检查」的 09:00 / 21:00。

### 2.3 自有仓 push 检查 `tools/repo-hygiene/push-check.py`

```powershell
python E:\k60-work\tools\repo-hygiene\push-check.py [--no-fetch]
```

- 覆盖六仓：UniXNU、UniXNU-mondrian、uefi-mondrian、ios-sweet-k60、PongUfs、UniXNU-sm8475-common。
- 报告：本地领先远端的 commit 数与标题（待 push）/ 远端领先（待 pull）/ 本地独占分支 /
  脏工作区文件数 / 多工作树提示（如 `/tmp/k60build`）。
- 只报告；push/pull/commit 由用户拍板。PongUfs 本地无检出，仅 ls-remote 报远端状态。

## 3. 克隆纪律

- `references/` 下的克隆 = **只读镜像**：允许 `fetch --all --prune`；禁止 merge/checkout/reset/clean
  （唯一例外：`UniXNU-upstream` 这类专用跟踪克隆可按任务要求 ff-only）。
- 「只读镜像 clone」与「工作仓 fetch+merge 评议」严格分离：上游跟进只碰前者；
  自有工作仓（`~/hackios/*`）的合并动作必须另起任务、用户点头。
- 新发现仓库**不自动克隆**：先在 CHANGES 报「新仓库（未克隆）」，由主控决定是否拉取。

## 4. 失败处理

| 失败 | 行为 |
|---|---|
| unixnu.com 不可达 | `list`/`find` 目录部分明确报错或降级声明；不静默用旧数据 |
| GitHub API 限流 | org 源本轮跳过并在 CHANGES 标注，不误报「无变动」 |
| 单仓 ls-remote/fetch 失败 | 该仓记 ⚠ 事件并继续，不进 state.json（下轮重试） |
| 设备页抓取失败 | 该页缓存缺席，find 结果标注缺口 |

## 5. 既有产物

- `docs/DEVICE-REPOS.md` / `docs/device-repos.json`：`devices.py list --write` 快照（含快照声明）。
- `references/upstream-watch/`：CHANGES-\*.md / state.json / watch.log / device-pages-cache/。
- 既有 `tools/refs-pull.py`：被 pull-check 取代（pull-check 是其超集）；保留不动，由主控决定下线。

## 6. 关联索引

- 全局资产地图：[`MASTER-INDEX.md`](MASTER-INDEX.md)（机读版 `master-index.json`）——本机制产物
  （本文件、`DEVICE-REPOS.md`、`devices-map.json`、`references/upstream-watch/`）已在其顶部互链区登记。
- `devices-map.json`：由 unixnu 官网索引会话导出（含 org/repo、URL、是否官方、fork 关系、
  同 SoC 标注）；缺失时 devices.py 回退实时抓取，功能不受阻。
  2026-11-04 已升级 `field_version: v2`（+`soc_source`/`doc_kind`，`soc` 全量回填）。
  更正一条旧结论：fork 变体一条没少——v1 时它们看似「缺失」的真实原因是 `soc` 字段全空，
  按 SoC 过滤（SM8475 高亮）时不可见；v2 已 100% 回填，map 模式高亮数与 live 模式一致（11 条）。
