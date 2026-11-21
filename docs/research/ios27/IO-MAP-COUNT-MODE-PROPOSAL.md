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

`docs/research/ios27/io-map-budget-27.toml`，15 行 `[[window]]`，每行给 `id / owner / component / file / root / macro_line / call_line / expression / bytes / in_27_build / verify`（可选 `note`、`unresolved`、`unresolved_reason`），字段契约见 §3.2：

- 27 构建内在（`in_27_build = true`）：BT 五窗 `bt-gcc` 2,048,512 + `bt-uart` 16,384 + `bt-qup-wrapper` 8,192 + `bt-tlmm` 1,048,576 + `bt-gic-dist` 65,536 = **3,187,200 B（0x30A200）**；XNU 自身三行（`machine_routines.c:1371`、`cpu.c:1310`、`cpu.c:289`）本板 ADT 无属性 → 0（`verify = 'file'`，只核文件在不在，不核宏）。
- 27 构建外（`in_27_build = false`）：`PongThermal` 四张 0x1000（16,384 B）、`PongPower/K60PmicRail` 四条（`rail_pass()` `:361`/`:368` + `k60_rail_probe()` `:444`/`:510`）、`PongPower/K60AdspBoard` 调用方给尺寸（`unresolved = true`、`verify = 'none'`）。
- `[limits] in_27_build_total_bytes = 3187200`、`page_rounded_4k_bytes = 3190784`、`page_rounded_16k_bytes = 3211264`、`shared_submap = false`。

**两处已更正（2026-11-21，原稿的数字写错了，这里就地留痕）**：

| 项 | 原稿 | 更正 | 依据 |
|---|---|---|---|
| `K60PmicRail` 调用点数与静态最坏 | 两条 / 196,608 B | **四条 / 393,216 B** | `rail_pass()` 在 `:356-357`，映射在 `:361`（`K60_CMD_DB_BYTES 0x20000`）与 `:368`（`K60_RSC_BYTES 0x10000`）；`k60_rail_probe()` 在 `:436-437`，又在 `:444` 与 `:510` 各映射一次（boot-arg 门控）。宏在 `K60PmicRail.h:28`/`:30` |
| 把 PongPower 拉进 27 归档的代价 | ≥ 0.19 MiB | **≥ 0.375 MiB** | 393,216 B（4×）÷ 1 MiB = 0.375，另加 `K60AdspBoard` 调用方给的尺寸 |

同源表在 `docs/research/ios27/PLATFORM-BUDGETS.md` §1.3，该处也已就地标「已更正」。

表在**本线仓库**里，不在 gates 仓库：预算的输入是板级事实（谁映射哪块 MMIO、多大），跟着板走；门禁只按下面这版写死的路径与字段名只读读它。

## 3. 表与门禁的接口契约（写死版，Lead 按这一版接）

Lead 2026-11-21 裁决：「表放本线仓库……gates 侧我只让它只读读你那 15 行表（路径由我写死、表缺失退 2）」。这一节就是那份写死版：路径、字段名、校验顺序、退出码、输出串。改动这份契约要同时改表和门禁，两边版本号一起动。

### 3.1 路径（写死）

```
lane root : /mnt/e/hackios/k60-platform27          # 也可用 --lane-root 覆盖
table     : <lane root>/docs/research/ios27/io-map-budget-27.toml
tree      : <lane root>/… 之外的任意 xnu-work 树，由 --tree 给
```

- 门禁**只读**这个文件，不写、不修、不提交。
- 路径写死为相对 lane root 的 `docs/research/ios27/io-map-budget-27.toml`；`--table` 可覆盖（为的是合成树的自测），默认值必须就是这一条。
- 表缺失 → 退 2，不许回退到 8 MiB、不许打 ✅（这就是 Lead 裁决里「表缺失退 2」）。

### 3.2 每行必须有的字段名（15 行全部已按此改完）

顶层：`schema_version`（int，必须 = 1）、`generated`（str）、`title`（str）、`tree_kind`（str）。

`[limits]`：`shared_submap`（bool，树无 `IO_MAP_SIZE` 时必须 false）、`in_27_build_total_bytes`（int）、`in_27_build_total_hex`（str）、`in_27_build_page_rounded_4k_bytes`（int）、`in_27_build_page_rounded_16k_bytes`（int）、`note`（可选）。

每个 `[[window]]`：

| 字段 | 类型 | 必填 | 语义（门禁怎么用） |
|---|---|---|---|
| `id` | str，全表唯一 | 是 | 报错点名用；重复即退 2 |
| `owner` | str | 是 | 归属线（bt / thermal / power / xnu），只用于输出分组 |
| `component` | str | 是 | 提供窗口的组件或补丁，人读 |
| `file` | str | 是 | 路径，按下一行的 `root` 解析 |
| `root` | `'lane' \| 'xnu'` | 是 | `lane`：`<lane root>/<file>`（板级文件与补丁）；`xnu`：`<--tree>/<file>`（XNU 源码）。两个根分开是必要的——`osfmk/arm64/cpu.c` 不在本线仓库里 |
| `macro_line` | int（0 = 无宏行） | 是 | 人读定位；门禁不据此判 |
| `call_line` | int | 是 | 人读定位；门禁不据此判 |
| `expression` | str | 是 | `verify = 'macro'` 时，**第一个空白前的前缀**必须是该文件里的 `#define` 名 |
| `bytes` | int ≥ 0 | 是 | 窗口字节数；`verify = 'none'` 时必须 0 |
| `in_27_build` | bool | 是 | 只有 true 的行进合计 |
| `verify` | `'macro' \| 'file' \| 'none'` | 是 | `macro`：查 `#define <expression 首个 token>` 在 `file` 里；`file`：只查文件存在（用于「本板属性不存在，映射为 0 字节」的 XNU 行）；`none`：不查文件也不查宏（调用方给尺寸，无法静态定） |
| `note` | str | 否 | 人读 |
| `unresolved` | bool | 否 | true 表示这一行**没有**可信字节数；必须同时 `bytes = 0` 且 `in_27_build = false`，否则退 2 |
| `unresolved_reason` | str | `unresolved = true` 时必填 | 缺什么输入才能定它 |

门禁必须容忍**未知字段**（表将来加字段不该让门禁红）。

### 3.3 校验顺序与退出码（顺序写死，先命中的那个报）

1. 表存在 → 否则 `FAIL: budget table missing: <path>`，**退 2**。
2. TOML 可解析、`schema_version == 1` → 否则 `FAIL: table schema_version is <x>, this gate reads 1`，退 2。
3. `[limits].shared_submap is False` → 否则 `FAIL: table claims shared_submap = true, but <tree>/osfmk/arm/io_map.c declares no IO_MAP_SIZE`，退 2。
4. 每行必填字段齐全 → 否则 `FAIL: window <id>: missing field <name>`，退 2。
5. `id` 唯一 → 否则 `FAIL: window id <id> appears twice`，退 2。
6. 每行类型/取值合法（`verify` 在枚举内、`bytes` 是非负 int、`unresolved` 自洽）→ 否则 `FAIL: window <id>: <what>`，退 2。
7. 对每个 `in_27_build = true` 的行：
   - 解析根：`base = <lane root>` 当 `root = 'lane'`，`base = <tree>` 当 `root = 'xnu'`；`root` 不在枚举内即 `FAIL: window <id>: root is <x>`，退 2；
   - `verify ∈ {macro, file}`：`<base>/<file>` 存在 → 否则 `FAIL: window <id> points at <file>, which this tree does not have`，退 2；
   - `verify = macro`：`#define <token>` 在该文件里 → 否则 `FAIL: window <id> expects #define <token> in <file>; the table no longer describes this tree`，退 2。
8. 合计 = `[limits].in_27_build_total_bytes` → 否则 `❌ io_map budget table is inconsistent: rows sum to <n>, [limits] declares <m>`，**退 1**。
9. 通过：`count: <k> window(s) in the 27 build, <n> B (<x.xx> MiB); no shared submap to overflow (12377 io_map() allocates each window from kernel_map)` + `✅ io_map windows: the table matches the tree`，退 0。

退 2 = 判不了（缺表 / 表与契约不符 / 表与树不符）；退 1 = 表自己矛盾；退 0 = 判过。**不许**在退 2 的分支上打印 ✅。

### 3.4 代码形状

保留现有 submap 分支不动（16 系列仍要它），只在 `io_map_size()` 返回 `default` 时改道：

```python
# 凡例：以下为提案代码，尚未落进 gates 仓库。
import tomllib

DEFAULT_TABLE = "docs/research/ios27/io-map-budget-27.toml"
REQUIRED_FIELDS = ("id", "owner", "component", "file", "root", "macro_line",
                   "call_line", "expression", "bytes", "in_27_build", "verify")

def load_table(path):
    try:
        with open(path, "rb") as handle:        # tomllib needs bytes
            return tomllib.load(handle)
    except FileNotFoundError:
        return None

def count_mode(tree, table_path):
    data = load_table(table_path)
    if data is None:
        print("FAIL: budget table missing: %s" % table_path)          # 契约 3.3-1
        return 2
    if data.get("schema_version") != 1:
        print("FAIL: table schema_version is %r, this gate reads 1"
              % data.get("schema_version"))
        return 2
    limits = data.get("limits", {})
    if limits.get("shared_submap", True):
        print("FAIL: table claims shared_submap = true, but %s/osfmk/arm/io_map.c "
              "declares no IO_MAP_SIZE" % tree)
        return 2
    rows = data.get("window", [])
    seen = set()
    for row in rows:
        wid = row.get("id", "<no id>")
        for field in REQUIRED_FIELDS:
            if field not in row:
                print("FAIL: window %s: missing field %s" % (wid, field))
                return 2
        if wid in seen:
            print("FAIL: window id %s appears twice" % wid)
            return 2
        seen.add(wid)
        if row["root"] not in ("lane", "xnu"):
            print("FAIL: window %s: root is %r" % (wid, row["root"]))
            return 2
        if row["verify"] not in ("macro", "file", "none"):
            print("FAIL: window %s: verify is %r" % (wid, row["verify"]))
            return 2
        if not isinstance(row["bytes"], int) or row["bytes"] < 0:
            print("FAIL: window %s: bytes is %r" % (wid, row["bytes"]))
            return 2
        if row.get("unresolved") and (row["bytes"] or row["in_27_build"]):
            print("FAIL: window %s: unresolved rows carry no bytes and stay out of "
                  "the 27 build" % wid)
            return 2

    total = 0
    counted = 0
    for row in rows:
        if not row["in_27_build"]:
            continue
        counted += 1
        base = args.lane if row["root"] == "lane" else tree
        path = os.path.join(base, row["file"])
        if row["verify"] in ("macro", "file") and not os.path.exists(path):
            print("FAIL: window %s points at %s, which this tree does not have"
                  % (row["id"], row["file"]))
            return 2
        if row["verify"] == "macro":
            token = row["expression"].split()[0]
            if not re.search(r"#define\s+%s\b" % re.escape(token), _read(path)):
                print("FAIL: window %s expects #define %s in %s; the table no "
                      "longer describes this tree" % (row["id"], token, row["file"]))
                return 2
        total += row["bytes"]

    declared = limits.get("in_27_build_total_bytes")
    if declared != total:
        print("❌ io_map budget table is inconsistent: rows sum to %d, [limits] "
              "declares %d" % (total, declared))
        return 1
    print("count: %d window(s) in the 27 build, %d B (%.2f MiB); no shared submap "
          "to overflow (12377 io_map() allocates each window from kernel_map)"
          % (counted, total, total / 1048576.0))
    print("✅ io_map windows: the table matches the tree")
    return 0
```

`main()` 里把现在的恒红改成：

```python
    _, source = io_map_size(tree)
    if source == "default":
        return count_mode(tree, args.table or
                          os.path.join(args.lane_root or ".", DEFAULT_TABLE))
```

新增两个参数：`--table`（默认 `<lane-root>/docs/research/ios27/io-map-budget-27.toml`，仅为自测可覆盖）、`--lane-root`。

### 3.5 契约自检

`E:/k60-work/scratch/platform27/contract-check.py` 是这份契约的参考实现（只读、不改表、不进仓库）：按 §3.2 逐字段校验 15 行、按 §3.3 的顺序报第一条错误、对 `verify = macro` 的 5 个在-build 行（全在 BT 补丁里）真去文件里找 `#define`，对 `root = xnu` 的三行在 XNU 树里核文件存在（`--xnu` 默认 `E:/hackios/xnu-12377`）。2026-11-21 实跑：`count: 8 window(s) in the 27 build, 3187200 B (3.04 MiB)`、`rows: 15 total, 8 in the 27 build (5 macro-verified, 3 file-verified)`、`✅ io_map windows: the table matches the tree`，RC=0。

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
