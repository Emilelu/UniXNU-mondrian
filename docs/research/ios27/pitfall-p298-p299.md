# 坑位 P-298 / P-299 成稿（A-patch 形状，待 Lead apply）

两条由 Lead 分配号码并指定拆开：坏的方式不同、抓住它们的判据也不同，合成一条会让后来人以为修好
其中一个就算完（Lead 2026-11-21 19:43）。

- **P-298** 板级 ADT 节点只在 `board.toml` 里「写对了」，没人核对它进没进 ADT 字节。
- **P-299** 上游 pick 会把别人正依赖的 `board.toml` 块先加后删。

补丁文件：[`pitfall-p298-p299.patch`](pitfall-p298-p299.patch)（106 行非空、11,549 B），改四个文件，
基线是已带 P-296 的 `diag/menu-hold-20261121`：

| 文件 | hunk | 内容 |
| --- | --- | --- |
| `README.md` | `@@ -152,7 +152,7 @@` | 区间 `坑记录 P-01–P-296` → `P-01–P-299` |
| `README_EN.md` | `@@ -164,7 +164,7 @@` | 区间 `Pitfall log P-01–P-296` → `P-01–P-299` |
| `docs/engineering/PITFALLS.md` | `@@ -7674,3 +7674,61 @@` | 两节正文 `## P-298 …` / `## P-299 …`，含下面那条「报编不过要带 HEAD + sha256 + 完整输出」的教训 |
| `docs/engineering/RULES.toml` | `@@ -1313,3 +1313,17 @@` | 两条 `[[rule]]`（P-298 / P-299） |

apply 与验证（都在 WSL、`LANG=C.UTF-8` 下跑，MSYS 的 diff/重定向会毁 UTF-8）：

```sh
cd <gates worktree>
git apply --check docs/.../pitfall-p298-p299.patch   # rc=0
git apply        docs/.../pitfall-p298-p299.patch    # rc=0，四文件 M
python3 -c 'import tomllib,pathlib;d=tomllib.loads(pathlib.Path("docs/engineering/RULES.toml").read_text());r=d["rule"];print(len(r),[x["id"] for x in r[-2:]])'
# → 179 ['P-298', 'P-299']，P-299 的 check 字面量是 false
```

## P-298 的 check：能真跑、单行、零依赖、双判

runner 是 `k60-gates/scripts/check-rules.py:75` 的 `subprocess.run(command, shell=True, cwd=REPO, …)`，
按 returncode 判红绿、打印最后一行输出；因此 check 必须：单行、从设备仓根目录可跑、不依赖 dtc
（工作机 MSYS 侧没有 dtc，字节级验证只能留在 WSL 脚本里）。

成稿的 check 是一条 1,262 字符的 `python3 -c "…"`（原文也留了一份在
`E:/iOS Port/Work/scratch/input27/check-input-adt-nodes.oneline.txt`），读
`${K60_XNEKOM_IOS27:-../xnekom-ios27}/board.toml`，要求：

- `[adt.buttons].string`：`compatible` / `device_type` == `buttons`
- `[adt.buttons].strings`：`button-names` == `["hold","voldown","volup"]`，且**不含** `menu`
- `[adt.buttons].u32`：`home-button-type` == 2
- `[adt.arm-io.pong-buttons].u64`：`core-base` / `cnfg-base` / `observer-base` == `0xc400000` / `0xc42d000` / `0xc440000`
- `[adt.arm-io.pong-buttons].u32`：`ee` / `pon-ppid` / `volume-up-ppid` == `0` / `0x13` / `0x18d`（`int(str(v),0)`，所以 `"0x013"` 也认）

**双判实测**（同一外壳：`shell=True, cwd=E:/iOS Port/Sources/Hardware/k60-gates`）：

| 输入 | 输出 | rc |
| --- | --- | --- |
| 真 `board.toml` | `ok input-adt-nodes: /buttons 4 fields + /arm-io/pong-buttons 6 properties present in the 27 board.toml` | 0 |
| `K60_XNEKOM_IOS27=…/adt27/brokendir`（删掉 `home-button-type` 与 `pon-ppid`） | `FAIL: /buttons home-button-type, pong-buttons pon-ppid` | 1 |

字节级那一层（P-298 判据的"看见"方式）不进门禁，留在本线的可复跑脚本
[`../../scripts/gen-27-adt-buttons.py`](../../scripts/gen-27-adt-buttons.py)：dtc 编 `hardware.dtb` 4,307 B
→ 反编译回 4,597 B/225 行（往返自证）→ `devicetree.py:311` 生成 `kernel.macho.adt` 16,648 B / 26 节点
→ 逐属性比字节。实测 PASS，负例 FAIL 并指名属性；记录见
[`adt-27-buttons-check.md`](adt-27-buttons-check.md)。

## P-298 正文里补的一条教训（2026-11-21 亲历）

报「我这棵树编不过」必须同时给 `git rev-parse HEAD`、该文件的 `sha256`、完整工具输出，三条不齐就别写进
报告——它可能只是**本地副本漂移**。亲历：我在 `feat/xnu27-data-gate`（HEAD `7fd04d89`）上读到
`dts/mondrian.dts:100` 缺 `/*`、`dtc` 报 `syntax error`，据此断言「整条 27 线出不了 payload」；Lead 在
`diag/menu-hold-20261121` 上同一文件（`sha256 ea688315…`）零诊断编出 4,307 B，因为修复提交 `e1b6c15f`
「fix(dts): restore the comment opener the merge dropped」早已在 `remotes/emilelu/main` 里。破坏确实存在过
（合并提交 `585fe75a7` 丢的 `/*`），但我把「某分支的坏状态」说成了「仓库今天坏了」——与 P-297 同族：
把「我这里坏了」当成「仓库坏了」，会让上游去改一个并不存在的 bug。

同一条还带出一个可移植性要求：`dtc` 必须带 `-i <soc feed>/dts`（`/include/ "sm8475.dtsi"` 在 feed 里、
不在设备仓），脚本把 include 目录做成参数 `--include-dir`（可重复），不写死相对路径。

## P-299 的 check：故意写 `false`

这条的判据不是字节比对，而是「有驱动按精确名断言某个节点/属性时，删掉它的那次提交必须让某条门禁红」。
现成检查不存在（Lead 会挂 `check-dt-asserts.py`），所以 `check = "false"`——**不现编一个跑不起来的命令**。
正文里把两次提交写清了：`97b84eb7`（2026-11-12 21:33，「pick 88 commits」）加上
`[adt.arm-io.pong-buttons]`，`3b3ff9ce`（21:35，「never let a pick overwrite the board contract」）把它删掉；
`docs/research/EIGHT-STEPS.toml:406` 记下那两个节点当时只活在 `/opt` 装配输入里。反例即这段历史本身。

## 反例（两条各一）

1. **P-298**：删 `home-button-type` 与 `pon-ppid` 的 `board.toml` 副本 → 上面那行 FAIL（已跑过，不是设想）。
2. **P-299**：2026-11-12 两次 pick 先加后删，当时没有任何门禁对"驱动按精确名断言 `/arm-io/pong-buttons`"
   这件事发过声，于是节点消失而门禁全绿；下一次干净重建立刻打
   `Pong keys: DT node /arm-io/pong-buttons not found`（27 仓 `board.toml:285-287` 注释里留了这句）。

## 未做的事

- 不碰 gates 仓、不碰 BT 线仓：`dts/mondrian.dts:100` 的 `/*` 由 Lead 自己改，我只交 diff。
- 不自占号码、不把 `check = false` 换成猜测命令。
