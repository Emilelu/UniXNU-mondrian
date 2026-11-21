# `ml_io_map` 计数模式：门禁在 27 上应该数窗口，而不是借 16 系列的 8 MiB

> 官方锚点：<https://unixnu.com/zh/porting/platform#block-and-os-services>（`E:/hackios/UniXNU/docs/zh/porting/platform.md:69-80`，「接入块设备和 OS 服务」里要求把 RAM/DMA 的映射输入逐一核对）与 <https://unixnu.com/zh/porting/platform#source-map>（`:10-19`，ArmCpu 负责 timer/GIC 初始化）。
> 本文是 Lead 2026-11-21（m01381 裁决 ①）要的实现形状。门禁脚本在 `E:/hackios/k60-gates`，本线只读，所以这里给代码与验收读数，不落盘到那边。

## 0. 一句话

27 的 `osfmk/arm/io_map.c` 没有 `IO_MAP_SIZE`，共享子图不存在；门禁在拿不到定义时**不退 2 也不再借 8 MiB**，而是走「count」分支：以 `docs/research/ios27/io-map-budget-27.toml` 为预算表，核对表里每一行在树里仍然成立，然后报窗口总和；**表缺行、行找不到宏、树里出现表外窗口，才退 2**。

## 1. 为什么不能靠 `call_sites()` 自己量

现在的 `scripts/check-io-map-budget.py:78-105` `call_sites()` 只 glob `bsd/dev/*.c`，并且只有「字面量」或「同文件 `#define`」两种窗口能解析出字节数（`:101-105`）。27 的 BT 驱动把大小经 wrapper 传进去：

```
patches/xnu-12377/0500-k60-bt-qbt-new-files.patch:331  static int k60_map(struct k60_region *r, uint64_t phys, size_t bytes) {
patches/xnu-12377/0500-k60-bt-qbt-new-files.patch:336      r->va = (volatile uint32_t *)ml_io_map((vm_offset_t)phys, (vm_size_t)bytes);
patches/xnu-12377/0500-k60-bt-qbt-new-files.patch:1017     int e = k60_map(&k60.gcc, K60_GCC_BASE, K60_GCC_SIZE);
```

于是 `call_sites()` 只看到 `k60_map()` 里那一个 `ml_io_map((vm_offset_t)phys, (vm_size_t)bytes)`，`expr = '(vm_size_t)bytes'` 既不是字面量也不在 `defines` 里 → `unresolved`（实测 `2 call site(s), 2 unresolved`，`E:/k60-work/scratch/platform27/gate-repro.sh` 的 B 组）。五个真实窗口一个都看不见。

结论：**在 27 上「按调用点静态求和」这条路本身不成立**，得换成「表 + 树核对」。

## 2. 预算表（已落盘）

`docs/research/ios27/io-map-budget-27.toml`，15 行 `[[window]]`，每行给 `id / owner / component / file / macro_line / call_line / expression / bytes / in_27_build`：

- 27 构建内在（`in_27_build = true`）：BT 五窗 `bt-gcc` 2,048,512 + `bt-uart` 16,384 + `bt-qup-wrapper` 8,192 + `bt-tlmm` 1,048,576 + `bt-gic-dist` 65,536 = **3,187,200 B（0x30A200）**；XNU 自身三行（`machine_routines.c:1371`、`cpu.c:1310`、`cpu.c:289`）本板 ADT 无属性 → 0。
- 27 构建外（`in_27_build = false`）：`PongThermal` 四张 0x1000（16,384 B）、`PongPower/K60PmicRail` 四条（`rail_pass()` `:361`/`:368` + `k60_rail_probe()` `:444`/`:510`，静态最坏 393,216 B）、`PongPower/K60AdspBoard` 调用方给尺寸（`unresolved = true`）。
- `[limits] in_27_build_total_bytes = 3187200`、`page_rounded_4k_bytes = 3190784`、`page_rounded_16k_bytes = 3211264`、`shared_submap = false`。

表在**本线仓库**里，不在 gates 仓库：预算的输入是板级事实（谁映射哪块 MMIO、多大），跟着板走；门禁只负责核。

## 3. count 分支的形状（给 `scripts/check-io-map-budget.py`）

保留现有 submap 分支不动（16 系列仍要它），只在 `io_map_size()` 返回 `default` 时改道：

```python
 凡例：以下为提案代码，尚未落进 gates 仓库。
import tomllib

DEFAULT_TABLE = "docs/research/ios27/io-map-budget-27.toml"

def load_table(path):
    """Return (rows, limits) from the lane's budget table, or (None, None)."""
    try:
        with open(path, "rb") as handle:          # tomllib needs bytes
            data = tomllib.load(handle)
    except FileNotFoundError:
        return None, None
    return data.get("window", []), data.get("limits", {})

def count_mode(tree, table_path):
    """Judge a tree that has no shared submap: validate the table, not a limit."""
    rows, limits = load_table(table_path)
    if rows is None:
        print("FAIL: no budget table at %s; a tree without IO_MAP_SIZE needs one "
              "(the windows go through wrappers, so they cannot be summed from "
              "call sites)" % table_path)
        return 2
    if limits.get("shared_submap", False):
        print("FAIL: %s claims shared_submap = true, but %s/osfmk/arm/io_map.c "
              "declares no IO_MAP_SIZE" % (table_path, tree))
        return 2

    total = 0
    for row in rows:
        if not row.get("in_27_build", False):
            continue
        define = os.path.join(tree, row["file"])
        if not os.path.exists(define):
            print("FAIL: row %s points at %s, which this tree does not have"
                  % (row["id"], row["file"]))
            return 2
        macro = row["expression"].split()[0]
        if not re.search(r"#define\s+%s\b" % re.escape(macro), _read(define)):
            print("FAIL: row %s expects #define %s in %s; it is not there, so the "
                  "table no longer describes this tree" % (row["id"], macro, row["file"]))
            return 2
        total += row["bytes"]

    declared = limits.get("in_27_build_total_bytes")
    if declared != total:
        print("❌ io_map budget table is inconsistent: rows sum to %d, [limits] "
              "declares %d" % (total, declared))
        return 1

    print("count: %d window(s) in the 27 build, %d B (%.2f MiB); no shared submap "
          "to overflow (12377 io_map() allocates each window from kernel_map)"
          % (len([r for r in rows if r.get("in_27_build")]),
             total, total / 1048576.0))
    print("✅ io_map windows: the table matches the tree")
    return 0
```

`main()` 里把现在的恒红改成：

```python
    _, source = io_map_size(tree)
    if source == "default":
        return count_mode(tree, args.table or os.path.join(args.lane_root or ".", DEFAULT_TABLE))
```

新增两个参数：`--table`（默认 `<lane-root>/docs/research/ios27/io-map-budget-27.toml`）、`--lane-root`。

## 4. 验收读数（Lead 落地后我按这六条复核）

| 场景 | 期望 | 退出码 |
|---|---|---|
| 27 构建树 + 本表 | `count: 8 window(s) in the 27 build, 3187200 B (3.04 MiB)` 且 `✅ io_map windows: the table matches the tree` | 0 |
| 27 构建树，缺表 | `FAIL: no budget table at …` | 2 |
| 表里 `shared_submap = true` 但树无定义 | `FAIL: … claims shared_submap = true` | 2 |
| 树里新增一个表外窗口（我们加一行不删） | 走「宏找不到」/「行不一致」分支，`FAIL` 点名 `id` | 2 |
| 表内 `in_27_build_total_bytes` 与行和不一致 | `❌ io_map budget table is inconsistent` | 1 |
| 16 系列树（有 `IO_MAP_SIZE`） | 旧 submap 分支不变（`submap … from osfmk/arm/io_map.c`） | 0/1 |

第 4 条的边界：当前实现只看表里有的行，所以「树里多出一个窗口、表没更新」只能靠**行核对**（宏还在不在）+ 人工 review 抓住，不能靠集合差。要真做成集合差，`call_sites()` 必须认 wrapper 的第三个实参，那等于把 wrapper 的名字写死进 gates——不划算，写出这个边界即可。

## 5. 为什么不给 27 豁免

Lead m01381 的原话：「豁免会让门禁对 27 永久闭嘴，而计数模式说的是事实」。豁免的形状是 `if no IO_MAP_SIZE: return 0`，风险是把「表漂移」和「新窗口没备案」一起沉默掉；计数模式至少每轮都重新核一遍「表里五行仍然在树里、总和仍然是 3,187,200 B」，漂移会被点名。

## 6. 复核记录

- 现状读数（恒红）：`E:/k60-work/scratch/platform27/gate-repro.sh` B 组，2026-11-21T18:41，见 `docs/research/ios27/GATE-BUGS-27.md` §4。
- 表与树的数字一致性：`docs/research/ios27/PLATFORM-BUDGETS.md` §1.3 的窗口字节数与本文 §2 同源（`0500-*.patch:75/78/97/101/107` 与 `:1017-1021`）。
- 未做：本提案未改 `E:/hackios/k60-gates` 任何文件，也未跑过 count 分支的真实实现（gates 仓库对本线只读，改动由 Lead 落地）。
