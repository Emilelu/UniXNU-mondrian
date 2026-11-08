# 分支台账（route-a-18）

> 状态（2026-11-07）：本页是 2026-11-01 的分支清理台账，不跟踪之后的分支；当前工作分支为 `fix/k60-measured-high-window`，以 `git branch` 为准。

> 2026-11-01 整理：把 48 个旧分支按"已合并 / 已作废"处理，只留下按规范命名的活动分支。
> 分支规范见 `AGENTS.md`：`feat|fix|refactor|docs|chore|perf|wip/<topic>`，一条分支一件事，
> 确认没问题才并入 `main`，任务完成后删分支。

## 活动分支

| 分支 | 用途 | 状态 |
| --- | --- | --- |
| `main` | 唯一长期分支，当前是 darwin24 路线 | 活动 |
| `feat/official-diagnostics` | 上游 entry probe（色条 + 定时复位） | 已并入 `main` |
| `chore/agent-guidelines` | `AGENTS.md`、README、CI | 已并入 `main` |
| `docs/upstream-survey` | iOS 16~27 调研、组织分支快照 | 已并入 `main` |
| `chore/sync-refs` | 同步脚本 | 已并入 `main` |

## 已删除分支（2026-11-01）

### `dev*` 系列（46 个：adtgen、dev8r、devcc14、devcpu、devcs、devdata…devwtD）

`git rev-list --count main..<branch>` 全为 0，`--is-ancestor` 对 `main` 与 `route-a-18`
都成立：**内容全部已在主线**，属于开发过程中的临时分支，直接删除。

| 分支 | 内容 |
| --- | --- |
| `adtgen` | ADT 生成器早期版本 |
| `devcpu` / `devcs` / `devdata*` | CPU、chip-select、Data 卷早期尝试 |
| `devdbg` / `devfix` / `devmin` | 调试开关、最小配置 |
| `devio2` / `deviolib` / `devisa` | I/O 探测与 ISA 总线 |
| `devpgo` / `devport` / `devppl` / `devpr` | PGO、移植、PPL、PR 流程 |
| `devram*` / `devroot*` / `devrw` | 内存、根卷、读写路径 |
| `devsys` / `devtc*` / `devtcb` | 系统调用、触摸、TCON |
| `devufs` / `devvp` | UFS、虚拟分页 |
| `devwt` / `devwt2`…`devwtD` | 工作树系列（wt = 工作树），最后一次提交 `devwt9` 的 IM4P 解析已在 `main` |

### `smp-0340` / `smp-8cpu` / `smp8`

| 分支 | 内容 | 处理理由 |
| --- | --- | --- |
| `smp-0340` | `board.toml [kernel.prelink] kext_patch`：给 20G81 的 `AppleARMPlatform::_validateConfiguration` 打补丁 | 属 **16.6.1 路线**。darwin24 用 `library_only` 丢掉它的 personality，不需要；且它会把 `archives` 里的 `ArmDTPlatform`/`ArmCpu` 删掉，**合入会破坏当前路线**。补丁本体在核心仓 `Emilelu/UniXNU` 的 `k60` 分支（`scripts/unixnu/kernel.py::patch_prelinked_kext`） |
| `smp-8cpu` | `board.toml` 的 8 核 ADT | 其 `cpus = 8` 已在 `main`；该分支的 `kernel_args` 比 `main` 旧，属过期快照 |
| `smp8` | `board.toml` 的 `cpus` 1 → 8 | 同上，内容已在 `main` |

### `route-a-17`

16.6.1 / 20G81 / darwin22 路线的终点状态（0242 shim、BCM2837 machine、17.7.11 profile）。
其 4 个提交都已包含在 `route-a-18` 中，而 `route-a-18` 又已并入 `main`，故删除。

## 保留的路线分支

`route-a-18` 在并入 `main` 后删除。**后续新工作一律从 `main` 开规范分支**，
不再新建 `route-a-*` 长期分支——路线切换用合并记录表达。

## 核对方法

```bash
bash scripts/k60-sync-refs.sh              # 同步外部仓库
git for-each-ref --format='%(refname:short)' refs/heads/
git log --oneline --graph --all -20
```
