# 官方设备页：四条 K60 记录，一条都没进过 registry

发现日期：2026-11-22（跑 `k60-docsearch.py` 时撞到 `/devices/mondrian-mzyxsl`）

## 规模上的事实

`OFFICIAL-REQUIREMENTS.toml` 登记 **103 页**，全部来自文档树的中段；`E:/hackios/UniXNU/docs/devices/`
下有 **266 个页面**，`mondrian` 开头的有四页：

| 文件 | 行数 | 是什么 |
| --- | --- | --- |
| `mondrian.md` | 529 | 我们这块板的官方页（正文引 `Emilelu/UniXNU-mondrian` 与 `docs/ROUTE-A-18-STATE.md`） |
| `mondrian-mzyxsl.md` | 664 | 另一位贡献者的同板 bring-up（format 2，16.6.1 / XNU 8796.141.3） |
| `mondrian-wohusaixing.md` | 503 | 第三份同板记录 |
| `mondrian-xtom0706.md` | 505 | 第四份同板记录 |

也就是说：**我们自己这一块板，官方站上有四份独立的 bring-up 记录，而 registry 一份都没审过。**
`unmapped 78/103` 这个数字本身没错，但它衡量的是一个排除了全部设备页的子集。

## 从这四页读到、且直接影响当前卡点的三件事

1. **绿条是 trampoline 画的，不是内核画的。** `mondrian-mzyxsl.md` 的
   「Development findings」原文：green bar "paints the top 1/16 of the framebuffer
   0xFF00FF00, clears SCTLR_EL1 M/C/I, and branches to the kernel entry"。
   ⇒ **看到绿条 = 已经跳进内核入口；没有绿条 = 连 trampoline 都没跑到。**
   这条把一个只能用串口回答的问题变成了肉眼可判的问题，而我们现在恰好没有串口。
0. **这几页是下游，不是独立第三方（用户 2026-11-22 指出，我此前判错）。**
   `mondrian-mzyxsl` 是 **fork 我们自己仓库** 后写的记录，`mondrian.md` 正文引的就是
   `Emilelu/UniXNU-mondrian`。⇒ 「他们也停在绿条上」不是独立佐证，而是我们自己的状态
   被回声了一遍。**引用任何「别人也这样」之前，先查它与本仓的派生关系**（fork 关系、
   共同祖先、提交重合），派生源不能当第二证据。
   本页下面第 1 条（绿条由 `Entry.S` 画）仍然成立，因为那是我在自己固件里直接读到的。
2. **同一份记录也停在绿条上（仅作自身状态记录，不作佐证）。** 它的「Current limits」逐字写：
   "Device observation currently stops at the green bar: no serial, ramoops or
   framebuffer line proves that XNU executed after the trampoline."、「Next action」
   是"Boot one image with the serial console enabled and capture the first XNU-side
   line after the green bar"。**这不是我们独有的失败，是这块板公开的卡点。**
3. **绿条之后还有两段可用的颜色探针。** `mondrian.md` 正文：
   "green bar from Entry.S, then the upstream probe's blue and magenta bars at the
   kernel entry and just before the MMU comes on"。这正是我们上周放弃的
   `patch-xnu-entry-probe.py` 那条路——放弃的理由是脚本里的 `ENTRY_VA`/`CAVES`
   是为另一颗内核写死的（`0xfffffff00ad96488 holds 0xf9401409`），
   而不是这条路不成立。**它在本板上是走通过的，只需要按 27 内核重算地址。**

## 下一步（按代价排序）

1. 下一次飞行就带一个判据：**绿条出现 / 不出现**，连同「多久出现、停留多久」。
   零成本，且能把「trampoline 之前死」与「trampoline 之后死」分开。
2. 把入口探针按 27 内核重算（`ENTRY_VA`、两个 cave 站点、`MMU_ENABLE_VA`），
   用 `llvm-nm` 从**本镜像**取地址，不再沿用 16 线的常数；这一条做完，
   「到哪里死的」就有三段颜色可读。
3. 把这四页登记进 registry（`devices/mondrian*.md` 四行），并把
   `docs/devices/**` 是否整体纳入 registry 作为一个决定记下来——
   现在的 `103 页` 口径会让「官方怎么说」这个问题永远缺掉最相关的一半。

## 纪律

- 引用这几页时必须带文件路径与行号；`mzyxsl` 那页的「green bar」说法与 `mondrian.md`
  的「绿条 + 蓝条 + 品红条」不矛盾（前者只说绿条，后者说后两段也在）。
- 不要把「他们也没成功」当作我们不需要做的理由；它的价值是判据，不是安慰。
