# 请求单：27 上产出 pong_goodix.o / pong_buttons.o（给 Lead，供 ⑦ artifact_check）

日期 2026-11-21 · 输入线（input27）· **我不构建**（stage-0 冻结，构建归 Lead）；这是排队请求，解冻后再执行

## 一、我要的两个对象（另一个可选）

| # | 对象 | 来源 | 用途 |
| --- | --- | --- | --- |
| 1 | `bsd/dev/pong_goodix.o` | 27 构建（arm64e，DEVELOPMENT） | 触摸驱动：坐标使能/配置路径是否真进了 27 编译 |
| 2 | `bsd/dev/pong_buttons.o` | 同上 | 按键驱动：PMIC arbiter 采样路径是否真进了 27 编译 |
| 3（可选） | `bsd/dev/pong_input.o` | 同上 | 队列/字符设备；顺带能验 `struct pong_touch` 布局 |

随对象请附两样东西（否则我判 INVALID）：**构建树的 `xnu-inputs.json`**（`patches.py:39-41` 写的 `source`/`commit`/`patches[].sha256`）与**该次构建的 `xnu-patches.list`**（`patches.py:66-67`）。

**位置更正（2026-11-21 查代码与实物）**：这两份清单不在 `tree/.cache/xnu-work/` 里，而是写在**构建工作目录**——`patches.py:39` 是 `stamp = ctx.work / 'xnu-inputs.json'`、`:66` 是 `patch_list = ctx.work / 'xnu-patches.list'`，`ctx.work` 与 `tree/` 同级。27 实测：`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/xnu-inputs.json` 与同目录 `xnu-patches.list`（`tree/.cache/xnu-work/` 下没有这两份）。核对脚本因此先按 `--work` 取，缺省时从 `--xnu-work` 逐级向上找 6 层，两种布局都吃。

**今日这棵树的清单本身就不含输入层**（这条会影响你的取件）：上面那份 `xnu-inputs.json` 记 `source = /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc`、`commit = ac9718fb1af618d5ce8678d0dc6e8a58f252216f`，`xnu-patches.list` 共 **104 行，全部是 `patches/xnu-12377/` 的 soc 层**，`grep goodix` = 0、`grep touch|pong` = 0。也就是说它是 soc 层构建留下的清单，不是设备四层（含 `:197` touch、`:198` keys）的清单。若你从这棵树直接取 `.o` 给我，我的判定会是 **INVALID（I4：清单里没有 touch/keys）**——这不是对象坏，是清单证明不了对象含输入层；届时需要带输入层的构建树清单。

## 二、我核对什么（全部离线，`llvm-nm` / `llvm-dwarfdump` / `strings`）

| 项 | 期望值 | 依据 |
| --- | --- | --- |
| DW_AT_name 源路径 | `<xnu-work>/bsd/dev/pong_goodix.c`（buttons 同理），`<xnu-work>` 由你给的 27 装配树的 `.cache/xnu-work` 实参决定，脚本不写死任何 `/opt` 路径 | 27 装配树 |
| DW_AT_producer | UniXNU 自带 clang（16.6.1 侧实测为 `clang version 24.0.0git`） | 16 侧 `pong_goodix.o` 的 DWARF |
| 行表最大行 | `pong_goodix.c` ≥ 1375、`pong_buttons.c` ≥ 171 | 27 应用后文件实际行数 |
| 定义符号 | `pong_goodix_init`、`pong_buttons_init`、`pong_touch_post`、`pong_touch_device_ready` | `pong_goodix.c:1338`、`pong_buttons.c:161`、`pong_input.c:30`、`:105` |
| 格式串（缺一即坐标/按键路径丢） | `goodix: %s ack=%02x`、`COORD-ON`、`Pong touch: Berlin-D ready, SPI %#llx reset=%u irq=%u raw axes=%ux%u transport=%s`、`Pong keys: arbiter v%u channels=%u PON=%u GPIO6=%u; power=%u up=%u down=%u` | `pong_goodix.c:1001`、`:1029`、`:1311`；`pong_buttons.c:134` |
| `struct pong_touch` 尺寸 | `DW_AT_byte_size = 24 (0x18)` | `pong_input.h:13-16`（uint64 + 4×uint32） |
| 未定义符号 | 逐个在 27 源/导出里能找到；**不得出现任何 `*_unixnu_fileset_unmapped` 桩** | 27 现状：205 个桩仍未落地 |

## 三、`.o` 到手后我怎么做

1. 先跑 `llvm-dwarfdump --debug-info <o>` 取 `DW_AT_producer` / `DW_AT_name` / `pong_touch` 的 `DW_AT_byte_size`；
2. `llvm-dwarfdump --debug-line <o>` 取每个文件的行号区间，与上表行数比；
3. `llvm-nm --defined-only` / `--undefined-only` 取符号表，与 16.6.1 同对象的表做差集，新增项逐个在 27 源里定位；
4. `strings -a <o>` 或 `llvm-objdump -s -j __TEXT,__cstring` 抓上表格式串；
5. 输出一张「项 / 期望 / 实测 / 判定」表，写进 `input-27.toml` 的 ⑦ `artifact_check` 与 evidence；
   若三项（静态 + 离线单测 + 产物）全过，⑦ 转 `done=true`；`local_verified` 仍为 false（没有上机）。

## 四、判定口径：什么算 FAIL，什么算 INVALID

**INVALID（我判不了，先重取/补料，不动台账结论）**

| 代号 | 条件 |
| --- | --- |
| I1 | 对象缺失、0 字节、`llvm-nm` 解析失败 |
| I2 | `DW_AT_name` 指向 27 之外（例如 `gates-out/…/ipados-16.6.1…`），即对象不是 27 产物 |
| I3 | 对象无 DWARF（未开 `-g`），行表/结构体检查不可做（此时我只出「字符串+符号」半张表，整体仍 INVALID） |
| I4 | 未附 `xnu-inputs.json` / `xnu-patches.list`，无法确认对象对应的输入 |
| I5 | 实测与期望只差一处且**可能是我方台账错**（如行数少 1–2 行）：先判 INVALID，复核台账后再重判，不直接判 FAIL |

**FAIL（输入层要改）**

| 代号 | 条件 |
| --- | --- |
| F1 | 缺 `goodix: %s ack=%02x` 或 `COORD-ON` 串 → 坐标使能路径没进 27（这正是 16.6.1 的真因） |
| F2 | 缺 `Pong touch: Berlin-D ready` 串 |
| F3 | 缺 `Pong keys: arbiter v%u …` 串 |
| F4 | 缺 `pong_goodix_init` / `pong_buttons_init` 定义符号 |
| F5 | 行表最大行 < 1375（goodix）或 < 171（buttons） → 编的不是当前文件 |
| F6 | `struct pong_touch` 的 `DW_AT_byte_size ≠ 24` |
| F7 | 未定义符号里出现 `*_unixnu_fileset_unmapped` 桩，或出现 27 源里查不到的符号 |

**PASS**：上表「我核对什么」每一行都在范围内，且无 I*/F*。

## 五、核对脚本已就绪（本轮交付，全部离线）

`scripts/verify-input27-objects.py`（本仓 `feat/input-27`）。参数化，**不含任何写死路径**：

```sh
python3 scripts/verify-input27-objects.py \
  --xnu-work <27 装配树>/tree/.cache/xnu-work \
  --obj-dir  <构建产物目录，含 pong_goodix.o / pong_buttons.o> \
  [--work <含 xnu-inputs.json 的目录，缺省向上搜 6 层>] \
  [--dwarfdump <llvm-dwarfdump>] [--nm <llvm-nm>] [--json]
```

它实现上表的 I1–I5 与 F1–F7，输出 `PASS / FAIL / INVALID` 三态；`PASS` 只填 ⑦ 的 `artifact_check`，`local_verified` 仍为 false。`--self-test` 会在临时目录用宿主 clang 编三个 fixture 并自证三件事（2026-11-21 实跑，`llvm-dwarfdump` / `llvm-nm` / `clang` 均为 WSL 18.1.3）：

| 用例 | 期望 | 实测 |
| --- | --- | --- |
| A 形状正确、源路径正确的对象（行表门槛放宽到 1） | PASS | PASS |
| B 同源但去掉 `COORD-ON` 串 | FAIL（F1） | FAIL |
| C 形状正确的对象撞真实行表门槛（≥1375） | FAIL 或 INVALID | FAIL（F5） |

另在真实 27 树上试跑一次（空产物目录）：脚本自动把 `--work` 定到 `…/mondrian_ios27`，判 **INVALID**，理由正是 `I4: input patches absent from the manifest: pong-touch-console, pong-physical-keys` 加两个 `I1` 对象缺失——与上面「今日清单不含输入层」的事实一致。
