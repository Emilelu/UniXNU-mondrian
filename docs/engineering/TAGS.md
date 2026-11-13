# Tag 策略：只留有用的锚点

来源：2026-11-13 用户要求 ——「打了一堆 tag 到底哪些有用的？没用的就删掉，后面也不要乱加，只加有用的」。
执行结果见本文末尾的保留清单。

## 允许的三种 tag

| 形态 | 含义 | 打的条件 |
| --- | --- | --- |
| `boot-proven-YYYYMMDD` | 这个提交编出来的镜像**在真机上进到了 SpringBoard** | tag message 必须带镜像路径、大小、sha256 和对应的 `console.log` 证据目录 |
| `snap-rN` | 登记为 `main` 基线的提交（铁则 9） | 出现在 `docs/engineering/MAIN-BASELINE.toml` 的 `tag` 字段 |
| `vX.Y.Z-...` | 版本里程碑（README 里引用） | 发布/里程碑时由人指定 |

**禁止**：每轮、每次提交、每次实验都打 `snap-YYYYMMDD-HHMMSS` 这类时间戳 tag。
日常回退锚点是被推送的提交（铁则 2），不是 tag。

## 为什么

2026-11-13 清点时本仓库有 **134 个 tag**，其中 126 个是每轮自动打的时间戳/轮次快照：
找不到「上一次能启动的是哪个提交」，也没法判断哪个 tag 可以安全引用。
清理后保留 9 个：6 个版本里程碑、`main` 基线 `snap-r180`、文档引用的 `snap-r177`、
以及唯一真正上机验证过的 `boot-proven-20261111`。

## 门禁

`scripts/check-snapshot-tag.py`（铁则 7）：

1. 出现三种允许形态之外的 tag → 失败，并给出删除命令；
2. 没有 `boot-proven-*`，或最近一个没推送到远端 → 失败；
3. `MAIN-BASELINE.toml` 里登记的 tag 在本地不存在 → 失败。

`--tag` 不再无条件打 tag：只有工作区干净、且 `MAIN-BASELINE.toml` 里登记了 HEAD
并写着 `state = "booted"` 时才会创建 `boot-proven-YYYYMMDD`，tag message 直接取那条
登记里的证据字段（`image`、`image_sha256`、`console`、`note`）。

## 2026-11-13 保留清单

| tag | 指向 | 说明 |
| --- | --- | --- |
| `boot-proven-20261111` | `29827f5` | 2026-11-11 编出的 `keep-a6165f2404568c1d.img`，2026-11-12/13 两次上机都进 SpringBoard（SB=129 / SB=133） |
| `snap-r180` | `main` 基线 | `MAIN-BASELINE.toml` 登记 |
| `snap-r177` | 文档引用 | `docs/` 里还有引用 |
| `v0.0.9-premain-8598c97` | 里程碑 | README 引用 |
| `v0.1.0-progressbar` | 里程碑 | README 引用 |
| `v0.1.0-progressbar-device` | 里程碑 | README 引用 |
| `v0.1.1-ios16-main-merged` | 里程碑 | README 引用 |
| `v0.1.2-first-frame` | 里程碑 | README 引用 |
| `v0.2.0-darwin24-archive` | 里程碑 | README 引用 |

被删除的 126 个 tag 已同时从 `origin` 删除；它们指向的提交都还在历史里，
需要时用 `git log`/`git reflog` 找回，不需要靠 tag。