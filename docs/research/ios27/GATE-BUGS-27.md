# 两处门禁在 27 上的缺陷：最小复现与期望输出

> 交接对象：Lead（他说这两处由他在 `k60-gates` 改，本线只读）。本文只写「怎么复现」和「改好后应当打印什么」，不写实现建议之外的改动。
> 复现脚本：`E:/k60-work/scratch/platform27/gate-repro.sh`（WSL 里跑：`MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /mnt/e/k60-work/scratch/platform27/gate-repro.sh`）。
> 采集时间：2026-11-21，两处都是实测输出，不是推断。

## 1. `check-lane-fragment.py`：`official:` 行被当成路径扫描

### 复现

最小 fragment：七步齐全、`status` 有、其它六步的 evidence 都是能解析的路径，只有一步是官方锚点行。

```sh
cat > /tmp/min-frag.toml <<'EOF'
[hardware.platform]
name = 'CPU、中断、定时器、RAM、DMA'
status = 'researching'

[hardware.platform.step.official]
done = false
evidence = 'official: porting/platform.md#source-map'
recorded_at = '2026-11-21T00:00:00'
# …其余六步各一条可解析路径…
EOF

python3 k60-gates/scripts/check-lane-fragment.py /tmp/min-frag.toml \
  --lane-root=/mnt/e/hackios/k60-platform27
```

### 现在打印（RC=1）

```
note min-frag.toml: hardware items: platform
FAIL: min-frag.toml: platform.official: evidence does not resolve: porting/platform.md
```

### 为什么

`official:` 前缀和 `#anchor` 被剥掉之后，剩下的 `porting/platform.md` 交给通用路径解析器（`PATHLIKE` + `resolve()`），而解析根是 `--lane-root` 与三个 `ROOTS`，**不包含** `docs`（`/mnt/e/hackios/UniXNU/docs/zh`）。只有放在 `docs/zh` 顶层的页（`index.md`、`building.md` 之类）能侥幸命中，任何子目录页（`porting/platform.md`、`drivers/arm-cpu.md`）必挂。

### 改好后应当打印（RC=0）

```
note min-frag.toml: hardware items: platform
OK min-frag.toml: seven steps, resolvable evidence, official anchors
```

并且：
- `official: porting/platform.md#source-map` 必须通过——页面存在、锚点 `{#source-map}` 在页面里；
- `official: porting/platform.md#no-such-anchor` 必须 FAIL，且消息里点名是锚点而不是路径，例如 `FAIL: …: anchor #no-such-anchor is not in porting/platform.md`；
- `official: porting/no-such-page.md#source-map` 必须 FAIL 且点名页面。

### 现成的对照（同一行改写成镜像路径就通过，RC=0）

```
OK min-frag2.toml: seven steps, resolvable evidence, official anchors
```

这就是本线目前 `docs/research/eight-step/platform-27.toml` 的绕法：官方页按镜像路径 `../UniXNU/docs/zh/porting/platform.md:10` 写，`{#source-map}` 的名字写在正文里。它能让门禁过，但把「官方锚点」这件事降级成了一句散文，所以还是希望门禁本身认 `official:` 行。

## 2. `check-io-map-budget.py`：27 树上的假绿

### 复现

```sh
python3 k60-gates/scripts/check-io-map-budget.py \
  --tree /mnt/e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work
```

### 现在打印（RC=0）

```
submap 8388608 = 0x800000 (8388608 bytes) from default
2 call site(s), 2 unresolved; resolved total 0x0 (0.00 MiB)
✅ io_submap budget: every ml_io_map window fits
```

同一棵树的 `osfmk/arm/io_map.c` 里 `IO_MAP_SIZE` 出现次数是 **0**（`grep -c IO_MAP_SIZE` → `0`）：12377 每次 `io_map()` 各自 `kmem_alloc(kernel_map, …)`（`osfmk/arm/io_map.c:112`，flags `KMA_NOFAIL|KMA_PAGEABLE|KMA_IO`，`!unmappable` 时再加 `KMA_PERMANENT`），根本没有共享子图可算。

### 为什么是假绿

- `io_map_size()` 在找不到 `IO_MAP_SIZE` 时**不报错也不跳过**，回落 `DEFAULT_SUBMAP = 8 << 20`（`check-io-map-budget.py:28`、`:62-70`），打印一句 `from default` 就继续；
- `call_sites()` 只扫 `bsd/dev/*.c`（`:73`），BT 的五个窗口全在 `patches/xnu-12377/0500-k60-bt-qbt-new-files.patch` 里，一个都扫不到，于是「2 call site(s), 2 unresolved」也被当成通过；
- 结论行仍然打 ✅。**「没有东西可比」被渲染成「全部装得下」。**

这正是 P-219 那类错误的镜像：门禁量错了对象，却给出了一个可以贴进汇报的绿色。

### 改好后应当打印（RC=0，但没有 ✅）

```
skip: <tree>/osfmk/arm/io_map.c has no IO_MAP_SIZE; 12377 allocates every window from kernel_map, so there is no shared submap to budget (P-219 is a 16-series shape)
```

要求：
- 退出码 0（不是失败），但**不得**出现 ✅ 行——skip 与 pass 必须在输出上可区分；
- 有 `IO_MAP_SIZE` 但调用点解析不出来时，仍应 ❌（保留现在 `problems` 的语义），例如 `❌ io_submap budget: 2 call site(s) unresolved; the windows cannot be summed`；
- 27 侧若还想量窗口，唯一可靠的来源是 `patches/xnu-12377/0500-k60-bt-qbt-new-files.patch` 里的 `K60_GCC_SIZE`/`K60_BT_UART_SIZE`/`K60_BT_QUP_WRAPPER_SIZE`/`K60_TLMM_SIZE`/`K60_GIC_DIST_SIZE`，合计 `3,187,200 B ≈ 3.04 MiB`；但那已经不是 submap 预算，不该复用这个名字。

## 3. 本线已做的绕法与不变式

- 平台线 fragment 用镜像路径 + 正文锚点绕过第 1 条，`check-lane-fragment.py --require-paths` 通过（2026-11-21）。
- 平台线不依赖 `check-io-map-budget.py` 的结论：`docs/research/ios27/PLATFORM-BUDGETS.md` §1 是按调用点手工加的字节（BT 五窗口 3,187,200 B，XNU 自身三处因 ADT 无属性为 0 B）。
- 两处修好之前，任何汇报里出现「io_submap 预算 ✅」都应视为无效证据。

## 4. 复核记录（结论写回，改好/仍需改）

### 2026-11-21T18:05 — 仍需改（两条都没到得了可复核的状态）

Lead m00967 ② 说两处已在 main 修、让我拉下来重跑。实测：**修好的版本不在这台机器的任何 ref 上**，所以两条都还停在原状。

| 检查 | 命令 | 输出 |
| --- | --- | --- |
| `origin/main` 有没有这个文件 | `git -C /e/hackios/k60-gates cat-file -p origin/main:scripts/check-lane-fragment.py` | `fatal: path 'scripts/check-lane-fragment.py' exists on disk, but not in 'origin/main'` |
| `origin/main` 停在哪 | `git log -1 --format='%h %ad %s' --date=iso origin/main` | `4b744c2e 2026-11-20 23:14:52 +0800 ios27: the loader accepts the collection now…` |
| 哪个分支带着这个文件 | `git branch -a --contains 5e0509e2` | `diag/menu-hold-20261121`、`remotes/origin/diag/menu-hold-20261121` |
| 该文件最后一次改动 | `git log --all --oneline -- scripts/check-lane-fragment.py` | `5e0509e2 fix(lanes): resolve evidence from this checkout…`（其后无提交） |
| 文件本身动过吗 | `ls -l --time-style=+'%m-%d %H:%M'` | `11-21 14:22`（与本线 m00962 首次复现时一致） |
| `check-io-map-budget.py` | 同上 | `11-16 06:07`，最后改动 `caad898c`，其后无提交 |

复现输出（gates HEAD `40dd9cf8`，脚本 `E:/k60-work/scratch/platform27/gate-repro.sh`，原样重跑）：

```
=== A. check-lane-fragment.py: an official: row is also scanned as a path
FAIL: min-frag.toml: platform.official: evidence does not resolve: porting/platform.md
RC_A=1
=== A control: the same row written as a mirror path instead
OK min-frag2.toml: seven steps, resolvable evidence, official anchors
RC_A2=0
=== B. check-io-map-budget.py on the 27 build tree (no IO_MAP_SIZE in 12377)
submap 8388608 = 0x800000 (8388608 bytes) from default
2 call site(s), 2 unresolved; resolved total 0x0 (0.00 MiB)
✅ io_submap budget: every ml_io_map window fits
RC_B=0
```

结论：**A 仍需改、B 仍需改**。本线 fragment 依旧按 §3 的绕法通过
（`OK platform-27.toml: seven steps, resolvable evidence, official anchors`），
所以本线不阻塞；要复核 Lead 的修复，需要他把包含这两处改动的提交推到
`origin/main`（或任一条我能 fetch 到的分支），并告诉我分支名/提交号——本条复核到此为止。

### 2026-11-21T18:41 — 仍需改（按 Lead 指的分支 fetch 了，两个脚本与 14:22 那次逐字节相同）

Lead m01022 ① 给了分支名：修好的两个脚本在 `diag/menu-hold-20261121`（不是 `origin/main`），
该分支已推到 origin。照做：`git fetch origin diag/menu-hold-20261121`，`FETCH_HEAD` =
`origin/diag/menu-hold-20261121` = `f200bd47`（`2026-11-21 17:59:59 +0800`），gates 本地 checkout
本来就在这条分支上，工作树干净、`scripts/` 无未提交改动。

| 检查 | 命令 | 输出 |
| --- | --- | --- |
| 取到的分支尖端 | `git rev-parse FETCH_HEAD origin/diag/menu-hold-20261121` | 两个都是 `f200bd470afe…` |
| 全仓有没有新提交碰过 A 脚本 | `git log --all --oneline -6 -- scripts/check-lane-fragment.py` | 只有 `5e0509e2`（`14:22:41`）与 `235ffa97`，**没有更新的** |
| 全仓有没有新提交碰过 B 脚本 | `git log --all --oneline -6 -- scripts/check-io-map-budget.py` | 只有 `caad898c`（`11-16 06:22`），**没有更新的** |
| 拉下来的 blob 与本地 HEAD 是否一致 | `git diff --stat HEAD FETCH_HEAD -- scripts/check-lane-fragment.py scripts/check-io-map-budget.py` | 空（逐字节相同） |
| A 脚本里有没有 `official:` 豁免 | `grep -n official scripts/check-lane-fragment.py` | `:150` 只做「页面存在 + 有 anchor」二次校验，PATHLIKE 之前没有任何豁免分支 |
| B 脚本里有没有「无 IO_MAP_SIZE 就 skip」 | `grep -n "DEFAULT_SUBMAP\|from default\|IO_MAP_SIZE" scripts/check-io-map-budget.py` | `:28 DEFAULT_SUBMAP = 8 << 20`、`:70 return DEFAULT_SUBMAP, "default"` 仍在；`:146`/`:150` 的 skip 只管「没有 --tree」，不管「树里没有 IO_MAP_SIZE」 |

原样重跑同一脚本（同一 gates checkout `f200bd47`）：

```
=== A. check-lane-fragment.py: an official: row is also scanned as a path
note min-frag.toml: hardware items: platform
FAIL: min-frag.toml: platform.official: evidence does not resolve: porting/platform.md
RC_A=1
=== A control: the same row written as a mirror path instead
note min-frag2.toml: seven steps, resolvable evidence, official anchors
OK min-frag2.toml: seven steps, resolvable evidence, official anchors
RC_A2=0
=== B. check-io-map-budget.py on the 27 build tree (no IO_MAP_SIZE in 12377)
submap 8388608 = 0x800000 (8388608 bytes) from default
2 call site(s), 2 unresolved; resolved total 0x0 (0.00 MiB)
✅ io_submap budget: every ml_io_map window fits
RC_B=0
=== B control: IO_MAP_SIZE occurrences in that tree
0
```

结论：**A 仍需改、B 仍需改**，且这次不是「找不到 ref」而是「ref 找到了、内容没变」——
`f200bd47` 上这两个文件的 blob 与 14:22 那次逐字节相同，`git log --all` 里也没有任何更新的提交。
可能的原因只有三种，按证据强弱排：①改动还在 Lead 的工作树里没提交/没推到这条分支；
②改在了另一条分支或另一个 gates 检出上（本机 `/e/hackios/k60-gates` 是唯一一个）；
③改在了别的文件名下。判据：`git log --all --oneline -- scripts/check-lane-fragment.py` 出现一条
晚于 `5e0509e2` 的提交，且 `grep -c DEFAULT_SUBMAP scripts/check-io-map-budget.py` 归零。
