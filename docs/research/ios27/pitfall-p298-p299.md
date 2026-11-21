# 坑位 P-298 / P-299 成稿（A-patch 形状；**已由 Lead 落地**，见文末「落地后的两次更正」）

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
`E:/k60-work/scratch/input27/check-input-adt-nodes.oneline.txt`），读
`${K60_XNEKOM_IOS27:-../xnekom-ios27}/board.toml`，要求：

- `[adt.buttons].string`：`compatible` / `device_type` == `buttons`
- `[adt.buttons].strings`：`button-names` == `["hold","voldown","volup"]`，且**不含** `menu`
- `[adt.buttons].u32`：`home-button-type` == 2
- `[adt.arm-io.pong-buttons].u64`：`core-base` / `cnfg-base` / `observer-base` == `0xc400000` / `0xc42d000` / `0xc440000`
- `[adt.arm-io.pong-buttons].u32`：`ee` / `pon-ppid` / `volume-up-ppid` == `0` / `0x13` / `0x18d`（`int(str(v),0)`，所以 `"0x013"` 也认）

**双判实测**（同一外壳：`shell=True, cwd=E:/hackios/k60-gates`）：

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
  **该 diff 已撤回**，见下节第一条。
- 不自占号码、不把 `check = false` 换成猜测命令。

## 落地后的两次更正（2026-11-21 20:0x）

### 一、dts 的 `/*` 早已修好，我的 diff 作废且不可 apply

Lead 在 `diag/menu-hold-20261121` 上实测：`1e2e6814`（feat(bt)）确实丢了注释开头的 `/*`，合并提交
`585fe75a` 把它带进来，而修复提交 `e1b6c15f`「fix(dts): restore the comment opener the merge dropped」
（`dts/mondrian.dts | 2 ++`）已经在树里。所以：

- 我的 diff 在那棵树上 `git apply --check` → `patch failed: dts/mondrian.dts:95` / `patch does not apply`：
  `/*` 已存在，再插一行就成了嵌套注释。**不可 apply，也不要再写成「可直接 apply」。**
- 我这边之所以编不过，是读了一棵 stale 检出：`E:/hackios/xnekom-ios27`（`feat/xnu27-data-gate` @
  `7fd04d89`，dts `sha256 e9871e43…`）与构建输入 `E:/hackios/k60-gates`
  （dts `sha256 ea688315…`）是两棵树两个阶段。
- 顺带更正 Lead 的一条前提：`feat/input-27` **已经含** `e1b6c15f`——HEAD `61513c11`，
  `git merge-base --is-ancestor e1b6c15f HEAD` rc=0，`git hash-object dts/mondrian.dts` = `91a26c32…`
  = `git rev-parse HEAD:dts/mondrian.dts`。所以不需要 rebase / cherry-pick。
- 用**未修改**的本仓 dts 重跑 ADT 检查：`verdict: PASS (exit 0)`，`kernel.macho.adt` 16,648 B，
  结论不变（记录见 [`adt-27-buttons-check.md`](adt-27-buttons-check.md)）。

### 二、P-298 / P-299 已落地；补丁 `apply --check` 失败 = 已落地，不是漂移

Lead 已 apply 到 `E:/hackios/k60-gates`（HEAD `78db41e0`）：`README.md:155` 与 `README_EN.md:167` 的区间
已到 `P-01–P-299`，`docs/engineering/RULES.toml` 179 条规则末两条是 `P-298` / `P-299`，
`docs/engineering/PITFALLS.md` 102 个 `^## P-` 节，`## P-298` 在 `:7679`、`## P-299` 在 `:7720`，
且落地的 P-298 里已带「报编不过要给 HEAD + sha256 + 完整输出」那一小节。

于是 `pitfall-p298-p299.patch` 现在 apply 会在四处失败（`README.md:152`、`README_EN.md:164`、
`PITFALLS.md:7674`、`RULES.toml:1313`）。**这四处 `patch does not apply` 的含义是「已经 apply 过」**，
不是上下文漂移、更不是补丁坏了。

落地版仍缺的一半教训（补丁：[`pitfall-p298-apply-check.patch`](pitfall-p298-apply-check.patch)，22 行非空、
1,637 B，单 hunk `@@ -7716,6 +7716,19 @@`，只改 `PITFALLS.md`）：**交付补丁前必须在目标分支上跑
`git apply --check` 并把输出贴进报告**；在「我以为的基线」上验过不算。校验记录：

| 步骤 | 结果 |
| --- | --- |
| 目标分支上 `git apply --check --verbose`（`k60-gates` @ `78db41e0`，只读） | rc=0，`Checking patch docs/engineering/PITFALLS.md...` |
| `git archive HEAD` 副本里真 apply | rc=0，文件里出现该小节，`^## P-` 节数仍 102（只加子节，不占新号） |
