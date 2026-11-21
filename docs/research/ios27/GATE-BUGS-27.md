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

### 2026-11-21T19:03 — A 改好、B 改好（口径变严，附一条副作用）

Lead m01279 说两处已落：`881d005d`（B）与 `c1b50a05`（A）。gates 本地 checkout 本来就在
`diag/menu-hold-20261121` 上，`git log` 已经能看到这两条，与 §4 上一条写死的判据对得上：

| 判据 | 命令 | 输出 |
| --- | --- | --- |
| 出现晚于 `5e0509e2` 的提交 | `git log --oneline --all -- scripts/check-lane-fragment.py scripts/check-io-map-budget.py` | 头两条就是 `c1b50a05`、`881d005d` |
| `DEFAULT_SUBMAP` 归零 | `grep -c DEFAULT_SUBMAP scripts/check-io-map-budget.py` | **`2`——没有归零**（见下） |

第二条判据是我自己写的，写粗了：`DEFAULT_SUBMAP` 这个常量还在（`:28` 定义、`:70` 仍返回它），
真正被改掉的是**调用点**——`881d005d` 在 `measure()` 之前加了一道门（`:153-163`）：

```python
    _, source = io_map_size(tree)
    if source == "default":
        print("FAIL: %s/osfmk/arm/io_map.c declares no IO_MAP_SIZE; the 8 MiB fallback "
              "is the 16-series number, so this tree cannot be judged against it. "
              "Count the ml_io_map windows instead of borrowing a limit." % tree)
        return 2
```

即「常量还在，但它不再被用来给一棵没有该宏的树打分」。判据应改成「`io_map_size()` 的返回值在
`main()` 里被检查」，不是 `grep` 归零。这条教训按同一条纪律记下：**判据要盯行为，别盯字符串**。

#### A. `check-lane-fragment.py`（`c1b50a05`）

五条读数，全部用一个七步齐全的 fragment（`E:/k60-work/scratch/platform27/gate-postfix.sh`）：

| # | 输入 | 输出 | RC | 期望 |
| --- | --- | --- | --- | --- |
| 1 | `official: porting/platform.md#source-map` | `OK p1.toml: seven steps, resolvable evidence, official anchors` | 0 | ✅ 与期望一致（改前是 `evidence does not resolve: porting/platform.md`） |
| 2 | `official: porting/platform.md#no-such-anchor` | `FAIL: p2.toml: platform.official: porting/platform.md has no anchor #no-such-anchor` | 1 | ✅ 点名 anchor |
| 3 | `official: porting/no-such-page.md#source-map` | `FAIL: p3.toml: platform.official: official page missing: porting/no-such-page.md` | 1 | ✅ 点名页面 |
| 4 | 绝对路径证据 `/mnt/e/hackios/k60-platform27/drivers/ArmCpu/ArmCpu.cpp:485-594` | `OK p4.toml: …` | 0 | ✅ 前导 `/` 不再被截（改前 token 变成 `hackios/…` 解析失败） |
| 5 | 本线 fragment + `--require-paths` | `OK platform-27.toml: seven steps, resolvable evidence, official anchors` | 0 | ✅ **没有红**——所以本线证据里没有真笔误（与 power 那条相反） |

副作用一条，写给人看：`official:` 行现在**不再**被当作仓库路径扫，所以本线 §3 那条绕法
（把官方页写成 `../UniXNU/docs/zh/porting/platform.md:10`）可以退役了；两种写法现在都过。

#### B. `check-io-map-budget.py`（`881d005d`）

四棵树（`E:/k60-work/scratch/platform27/gate-b-postfix.sh`）：

| # | 树 | 输出 | RC |
| --- | --- | --- | --- |
| 1 | 27 构建树 `.cache/xnu-work`（`grep -c IO_MAP_SIZE` = 0） | `FAIL: … declares no IO_MAP_SIZE; the 8 MiB fallback is the 16-series number, so this tree cannot be judged against it. Count the ml_io_map windows instead of borrowing a limit.` | **2** |
| 2 | 合成 16 系列形状树（`#define IO_MAP_SIZE (8ul << 20)`，两个窗口 1 MiB + 8 KiB） | `submap 8388608 = 0x800000 (8388608 bytes) from osfmk/arm/io_map.c` / `2 call site(s), 0 unresolved; resolved total 0x102000 (1.01 MiB)` / `✅ io_submap budget: …` | 0 |
| 3 | 合成树，窗口和 > 子图（2 MiB vs 1 MiB） | `❌ … ask for 0x200000 (2.00 MiB) but IO_MAP_SIZE is only 0x100000 (1.00 MiB) …（P-219）` | 1 |
| 4 | 不是 xnu-work 树的目录 | `skip: /tmp does not look like an applied xnu-work tree` | 0 |

读数：`881d005d` 的期望形态与我 §3 写的不同——我写的是「打一行 `skip:`、RC 0、不打 ✅」，
他实现的是「打 `FAIL:`、RC 2」。**他的更严，我接受**：判不了的树不该给绿。但要记一条副作用：
**27 的树在这条门禁上从此恒红**，所以任何「全门禁一次跑绿」的说法在 27 上不成立，除非
①这条门禁对 27 显式豁免，或 ②给它一个计数模式——它的 FAIL 文案自己就是指路牌
（"Count the ml_io_map windows instead of borrowing a limit"），而那份计数已经在
`docs/research/ios27/PLATFORM-BUDGETS.md` §1（BT 五窗 3,187,200 B；PongThermal / K60PmicRail /
K60AdspBoard 三个调用点在 27 archive 之外）。这条留给 Lead 决定，本线不改 gates。

边界观察（不是缺陷）：窗口和恰好等于子图（1 MiB vs 1 MiB）时打 `⚠ … (>75%); one more window may not fit`
但结论是 `✅ … fits`、RC 0——共享子图下「刚好装满」确实算装得下，所以这条判读是对的，
只是别把 `⚠` 当失败读。

结论：**A 改好、B 改好**。本线 gate 复核到此收尾；下一次重跑只需要在 27 树这条门禁的处置
（豁免 / 计数模式）定下来之后做一次。

## 5. 复审时冒出来的第三条：一条 evidence 里只有**第一个** `official:` 被机检

不是回归，是复核 A 修好时才暴露的：`check-lane-fragment.py` 现在会校验 `official:` 引用的页面与锚点，
但每条 evidence 只校验**第一个**引用。

### 机理

`check-lane-fragment.py:160` 用的是 `re.search`：

```python
page = re.search(r"official:\s*[\"']?([\w./-]+\.md)(?:#([\w.-]+))?", text)
if page is None:
    continue
```

`:154` 那行 `re.sub` 会把**所有** `official:` 引用从路径扫描里剔掉（这部分是对的），但接下来的页面/锚点
校验只拿到第一个匹配。所以第 2..N 条引用既不参与路径扫描、也不参与锚点校验——等于既不检查也不报错。

### 两发实测（同一份本线 fragment，只改一个锚点）

| 改哪一条 | 命令 | 输出 | RC |
| --- | --- | --- | --- |
| 第 **2** 条（`#clusters` → `#no-such-anchor`） | `check-lane-fragment.py frag-bad.toml --lane-root=… --require-paths` | `OK frag-bad.toml: seven steps, resolvable evidence, official anchors` | **0**（漏检） |
| 第 **1** 条（`#source-map` → `#no-such-anchor`） | 同上，`frag-bad2.toml` | `FAIL: frag-bad2.toml: platform.official: porting/platform.md has no anchor #no-such-anchor` | 1（正确） |

### 改好后应当打印

把 `:160` 的 `re.search` 换成 `re.finditer`，逐条校验（每条都要页面存在 + 锚点存在）：

```
FAIL: frag-bad.toml: platform.official: porting/platform.md has no anchor #no-such-anchor
RC=1
```

### 本线现在的处置（不改 gates，只标明）

fragment 的 `official` 步里三条锚点都写在同一条 evidence 里，所以只有 `#source-map` 是被门禁机检的；
`#clusters`（`platform.md:41`）与 `#block-and-os-services`（`:69`）由本线按页面原文核过：

```sh
grep -n '{#' ../UniXNU/docs/zh/porting/platform.md
# 10:## 源码与接口 {#source-map}
# 41:### 能效簇与性能簇 {#clusters}
# 69:## 3. 接入块设备和 OS 服务 {#block-and-os-services}
```

这一条不影响本线交付（三条锚点都是真的），但它意味着「门禁绿」在现阶段**不能**被读成「所有官方锚点都验过」。
在 `finditer` 落地前，任何人加第 2 条引用都要自己看一眼。

## 6. 新坑草案：`call_sites()` 把「算不出」折叠成「0 字节」（坑号请 Lead 分配）

> 本节按 Lead 2026-11-21 的指示单独立坑：**坑号找 Lead 要，本线不自占**。这是本线写下的
> 正文草稿，Lead 给号后我把 `P-xxx` 补进标题与下方结论。

**现象。** `E:/hackios/k60-gates/scripts/check-io-map-budget.py` 在拿不到窗口尺寸时不会说「算不出」，
而是把这一项从合计里静默丢掉，最后报一个 0：

```
$ python3 scripts/check-io-map-budget.py --tree <27 树>/osfmk/arm/io_map.c 所在树
submap 8388608 = 0x800000 (8388608 bytes) from default
2 call site(s), 2 unresolved; resolved total 0x0 (0.00 MiB)
✅ io_submap budget: every ml_io_map window fits
```

`unresolved 2` 已经写在输出里，但**结论行仍然是 ✅**，退出码 0。读结论的人（和后续自动化）看到的
是「预算通过」，不是「两项没算出来」。

**为什么它是坑。** 「读不到」被折叠成「没有」，与 P-279（文档镜像读不到 → 报"没有镜像"，退 2 前
先误报）同形。区别只在折叠点：P-279 折在文档镜像，这里折在窗口尺寸。

**什么时候会静默通过**（任意一条成立就够了）：

1. 尺寸经 wrapper 传入。27 的 BT 驱动就是这么写的：`patches/xnu-12377/0500-k60-bt-qbt-new-files.patch:331`
   `static int k60_map(struct k60_region *r, uint64_t phys, size_t bytes)`，`:336`
   `r->va = (volatile uint32_t *)ml_io_map((vm_offset_t)phys, (vm_size_t)bytes);`，
   真正的五个窗口在 `:1017-1021` 以 `k60_map(..., K60_GCC_SIZE)` 形式给出。`call_sites()` 只看到
   `(vm_size_t)bytes`，既非字面量也不在同文件 `#define` 里 → unresolved。
2. `#define` 在另一个文件。`K60PmicRail.c` 的四个映射用的是 `K60PmicRail.h:28/:30` 里的宏，
   同文件里没有定义 → unresolved。
3. 调用点不在扫描范围内。`call_sites()` 只 glob `bsd/dev/*.c`；`drivers/**`（PongThermal、
   PongPower）与补丁文件（`patches/xnu-12377/0500-*.patch`）都不在扫描范围，等于看不见。
4. 树里没有 `IO_MAP_SIZE` 时它借 16 系列的 `DEFAULT_SUBMAP = 8 << 20`（`:28`、`:70`）。这一条
   已经由 Lead 修掉（`c1b50a05`/`881d005d`，27 树现在明确红并要求计数模式），但 1–3 三条仍在，
   所以**计数模式落地后**这个坑依然会咬人：计数模式必须显式处理 unresolved 行，否则换个形状
   继续折叠。

**建议判据。**

- `unresolved > 0` 时不允许打印 ✅、不允许退出 0：要么退 2 并点名「无法计算：缺 <wrapper 的实参宏 /
  缺`#define` 所在文件>」，要么在计数模式下把 unresolved 行当作「表外项」打印出来（不计入合计、
  但在结论行里计数并列出 `id`）。
- 结论行必须能区分三种状态：`0 unresolved`（判过）/ `N unresolved`（N 项没算出来）/ 无表无树（判不了）。
  现在只有第一种状态看起来像通过，其余两种都长得像通过。

**复现。** `E:/k60-work/scratch/platform27/gate-repro.sh` 的 B 组（读数见 §4 与本轮重跑）；
计数模式下的同形复现见 `E:/k60-work/scratch/platform27/contract-check.py` 的 `verify = none` /
`unresolved = true` 行——契约要求这些行 `bytes = 0` 且**不进合计**，并在输出里单独计数，正是为了避免
同一种折叠。

