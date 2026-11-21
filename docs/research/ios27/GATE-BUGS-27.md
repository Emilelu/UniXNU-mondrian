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
