# 移植疏漏审计：文档、调研与复用（2026-11-16）

> 本文是一件**审计**，不是新结论层：它记录"现有文档/调研哪里不准、缺什么、能抄谁"，
> 并把可以在文档层直接修的部分列成清单。基线：`origin/main` = `74c0d24e6c2b5be83b48c0fdcf459e708825be7c`（2026-11-16）。
>
> 范围：只读审计 + 本轮在 `docs/` 内落地的修补；后续轮次按用户授权新增/修改了 `scripts/` 下的文档门禁（见 §10）。
> 未改 `drivers/`、`patches/`、水位与基线；未合 main。

## 0. 摘要：十条最要紧的

| # | 疏漏 | 证据 | 影响 |
|---|---|---|---|
| G1 | 三处入口文档仍把固件卷写成"同源同字节、现场两个卷、P-154 现状" | `README.md:134`、`docs/INDEX.md:51`、`docs/engineering/README.md` | 与 main 上已改写的 `docs/engineering/FIRMWARE-REBUILD.md`（"它不是确定性的 / P-216 / P-154 已关闭"）直接矛盾 |
| G2 | `docs/ops/` 是 2026-11-12 从 yibiya 一次 pick 进来的上游快照，却在文件头自称"唯一权威" | `docs/ops/HARD-RULES.md:1-4`、上游 pick `97b84eb7` | 两份 HARD-RULES（★1–★37 vs HR-01–HR-12）、三份 PITFALLS（P-230 vs P-76 vs 148 行副本）编号空间互不相容 |
| G3 | 文档总入口自身过期且结构断裂 | `docs/INDEX.md:5`（日期、校验脚本名）、`:18-19`/`:52-53`（★35/P-130）、`:15`（3 列表只有 2 格）、`:68-69`、`:153` | 新接手的人按索引读，会先读到错数字 |
| G4 | 引用完整性没有任何门禁 | 2207 处仓库内路径引用中 **217 个目标不存在**（436 处）；**14 处行号越界** | 文档里的 `file:line` 是主要证据形式，坏引用等于证据失效 |
| G5 | 92 个研究文件只在各线分支上，main 只有 71 个，且没有"哪条线在哪"的映射 | 20 个并行检出实测（cellular 18、wifi 14、thermal 12、bt 10…） | 研究不可见 = 重复考古；`EIGHT-STEPS.toml` 已因此引用 7 个 main 上不存在的文件 |
| G6 | `EIGHT-STEPS.toml` 的 wifi 条目仍写"从未上机 / parked" | `docs/research/EIGHT-STEPS.toml:390-426` | 与 c1–c8 实飞、P-215 结案矛盾；这是唯一一处**门禁数据源**与事实相反 |
| G7 | 复用缺口不是"没有轮子"，是"抄了早期版本没跟上" | PongMetal 前端 109,178 B vs 参考 225,616 B；ShengUfs 参考 `9d527ae` 的 `VerifiedTableCache.h` 6,878 B、`RootPublication.h` 3,225 B 已在 `k60-ufs-verified:feat/ufs-verified-table` 移植（含 `RootWindowRead.h`/`RootPolicyTable.h`/`RootWindowVerifier.h`、3b 异步根发布与 host 测试，未合 main） | PongMetal 仍是主要缺口；UFS 复用已推进到分支 |
| G8 | `patches/wifi/` 主仓 12 个补丁 **221,744 B**（`k60-wifi` 检出同 series **228,302 B**，5 个文件不同）在 main 上没有任何构建路径引用 | `grep -rn 'patches/wifi' scripts/*.py scripts/*.sh` 只命中测试断言；`patches/wifi/series` 无读者；main 的 `0007` 仍写旧 Data UUID `6DCCF70A-...`，`0010` 只加 `KERNEL_EXTRA_ARCHIVES` 分支，k60-wifi 已改 `1BCD69FF-...` 并补 `PLATFORM_ARCHIVES` | main 侧 WiFi 接线缺位；P-215 的补丁字节在 main 但**不是最新**，直接接线会静默漏掉 PongWifi；字节差已在 `feat/wifi-patch-sync` `5d70dd08` 同步（从 `origin/main` 拉出的仅 4 文件分支），等合入与接线；2026-11-17 07:28 用与 `5d70dd08` 字节相同的同步补丁（当时取自 `e1a46146`）在 `k60-wifi` 的 `b9a8e981^` 干净树上按 series 顺序 apply 12/12 通过（548 个文件），应用后 Data UUID 为 `1BCD69FF-...`、脚本同时含 `KERNEL_EXTRA_ARCHIVES`/`PLATFORM_ARCHIVES` |
| G9 | **已退役的前身**缺少可见的退役登记（2026-11-16 状态）：`patches/xnu/0610-k60-metal-seeds.patch`（4,364 B）不在 series | series `:218` 是 `0610-k60-metal-plugin-deploy.patch`；`scripts/tests/test-series-source.py:8` 称其 retired，`WIFI-REBUILD-CHECKLIST.md:99` 记为 wifi 线的等价实现 | 不是垃圾；2026-11-17 已由 `3dae8347` 在 `PATCH-CATALOG.toml:98-102` 登记为 `retired`（evidence `3a8d61d8`），文件保留，删除前仍需 wifi 线确认 |
| G10 | 三处"现在就该抄"的外部实现没进任何清单 | BT：新发现 `daimile2/renoir_xnu_bluethooth`（QCA6490 XNU，BSD-3-Clause，未考察）；音频：AW882xx 本地无副本（GPL-2.0 候选）；Metal：`pong-metal@0b3b34a` | 见 §7、§8 |

> 上表记的是**发现时**的状态。截至 2026-11-17：G1–G3 已修；G4 已有门禁（2,215 处引用 / **101** 个目标缺失 / 0 处行号越界，
> 基线冻结，124 个跨仓目标已加前缀）；G5 已有 `LINE-RESEARCH-MAP.md`（108 个分支文件，05:45 复核）与 `LINE-MAP.md`（18 条线）；
> G6 的 wifi 段已按 c1–c8 重评（①–⑦ 记 done，`status` 仍保留 parked 并写明是门禁范围而非进度）；
> G9 已登记进 `PATCH-CATALOG.toml`（retired）；G10 已把 QcaBluetooth / UniXNU-liuqin / Device-Binaries 三处写进 `SOURCES.toml` 的 required（研究源从 53 增至 **58**，2026-11-17，第三前缀 `/mnt/e/hackios` 已可用）；G7 的 UFS 部分已在 `k60-ufs-verified:feat/ufs-verified-table` 移植（verified-root policy/cache/read path + 3b 异步根发布 `46545497`，`NATIVE_VERIFIED_BLOCK` 默认关闭，未合 main）；PongMetal、G8 与 AW882xx/pong-metal 两项仍只报告、未动（G8 的补丁字节差已在干净分支 `feat/wifi-patch-sync` `5d70dd08` 同步，等合入与接线；旧的 `feat/wifi-series-sync` `e1a46146` 基于 docs 分支、不可直接合 main，保留为历史）。另：QcaBluetooth 本地参考仓已到 `effe4ec`，k60-bt vendored `986d631`，4 个诊断提交未移植（见 §8.3）。

## 1. 方法与可复现性

- 脚本在 `E:/k60-work/scratch/refmine/`：`doc-cite-scan*.py`（引用完整性）、`line-research-map2.py`（跨检出研究分布）、
  `num-audit.py` 类小脚本（规则/坑/补丁计数）。全部在 WSL 里对 `/mnt/e/...` 运行。
- 计数一律用脚本读文件，不靠记忆；本文每个数字都可用 §附录 A 的命令复算。
- 未做：全仓库全文语义审阅（只对入口文档、规则文件、`docs/research` 与 `docs/ops` 做逐条核对）；
  联网检索只到 2026-11-16 23:35（`web_search` 报 HTTP 402 余额不足，GitHub API 触发限速，
  `raw.githubusercontent.com` 直取失败），见 §8。
- 断言分级：**【实测】**= 本轮脚本/命令读到；**【转述】**= 子 agent 报告或上游文档说法，未逐字节复核；
  **【未知】**= 没有证据，不猜。

## 2. 文档事实错误（按危害排序）

> 状态：本表分级保留发现时的证据等级（【实测】/【转述】/【未知】）。2026-11-17 09:15 复核：除 G7 PongMetal、G10 AW882xx/pong-metal 等明确待办项外，表中列出的文档修正均已完成。

| 位置 | 现在写的 | 实际 | 级别 |
|---|---|---|---|
| `README.md:134` | "固件卷重建手册：谁在构建、**为什么同源同字节**、现场**两个卷**、**P-154 现状**与重建实验协议" | main 的 `FIRMWARE-REBUILD.md` 已是"它不是确定性的（P-216）、现场四个卷、P-154 已关闭" | 【实测】 |
| `docs/engineering/README.md:24-25`、`docs/engineering/STATUS.md:341-342` | ★1–★35 / P-01–P-130 | ★1–★37（29/30/31 不存在）/ P-01–P-230 | 【实测】 |
| `docs/INDEX.md:18-19`、`:52-53` | 同上 | 同上 | 【实测】 |
| `docs/INDEX.md:5` | "最后更新 2026-11-12。本索引由 `check-doc-links.py` 校验" | 该脚本不存在；实际门禁是 `scripts/check-docs.py` | 【实测】 |
| `README.md:57` | 门禁"当前 84 条" | `docs/engineering/RULES.toml` 有 **108** 个 `[[rule]]`（审计时 107；现已由 check-readme 门禁校验） | 【已修】 |
| `AGENTS.md:188` | "`patches/xnu/` carries 245 patch files with 211 entries in `series`" | **268** 个 `.patch`、series **227** 条 | 【实测】 |
| `docs/engineering/STATUS.md:47` | "223 个补丁" | series 227 条；2026-11-17 已注明为“构建时启用 223 个补丁（当时 series 223；现 227）” | 【已修】 |
| `docs/engineering/STATUS.md:98` | "pong_metal=1 导致 backboardd 崩溃" | 同文件 `:393` 已声明该说法失效，`:396-406` 给出真因（插件缺 `Info.plist`/`.publish`/`.clients`/`PongMetalBridge.dylib`/`libvulkan_freedreno.dylib`） | 【实测】 |
| `README.md:50` | "本地构建脚本位于工作区（不在仓库内）" | `scripts/build-strict.sh` 等就在仓库里；工作区那份是构建副本 | 【实测】 |
| `README.md:138-140` | 三条项目符号插在文档表格中间 | 表格被截断，Markdown 渲染错位 | 【实测】 |
| `docs/INDEX.md:15` | REPO-MAP 行只有 2 个单元格 | 该表 3 列 | 【实测】 |
| `docs/INDEX.md:68-69` | `engineering/BATTERY-INTEGRATION.md`、`BOOT-ARGS.md` 列在 state/ 表 | 两者都在 `docs/engineering/` | 【实测】 |
| `docs/INDEX.md:153` | "series 224 vs 229" 的旧对照 | 当前 series 227，且 wifi 已按 P-215 结案 | 【实测】 |
| `docs/INDEX.md:153-154` | WIFI-REBUILD-CHECKLIST 行被截断，五条硬差异串到 SHENGUFS 行 | 两行已修复，WIFI 的五条差异归回本行 | 【实测】 |
| `docs/engineering/BOOT-ARGS.md:36-61` | 26 行有 6 个单元格，表头只有 5 列，Markdown 渲染错位 | 已把末两列合并为一列（内容不变），全表统一 5 列 | 【实测】 |
| 13 个文档的 16 行表格，另有 `UNIXNU-SITE-INDEX.md` 的 4 行 | 未转义的 `\|`、未闭合反引号或缺列，渲染时列错位 | 2026-11-17 全量表格扫描后逐行修复：`docs/ops/HANDOFF.md:1496`、`docs/engineering/TOOLBOX.md:115-122`、`docs/plans/120HZ-PORT-PLAN.md:207`、`docs/plans/DOCS-CORE-ALL.md:568`、`docs/plans/DOCS-PORTING-ALL.md:762`、`docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:237`、`docs/reference/ZCODE-RESEARCH-REPORT.md:350`、`docs/research/REFERENCE-INDEX.md:581/931/936`、`docs/research/charger/02-GLINK-CONTRACT.md:189-190`、`docs/research/charger/06-SUBSCRIPTION-CONSTANT.md:158`；另修 `docs/reference/UNIXNU-SITE-INDEX.md:68/85/96/369` 的未闭合反引号；内容不变 | 【实测】 |
| `docs/state/STATE-2026-11-07.md:1-3` | "唯一‘当前状态’入口" | 本文件是 2026-11-07 快照；当前入口是 `docs/engineering/STATUS.md`，INDEX:132 已标过时但文件本身没标 | 【实测】 |
| `docs/state/NEXT-STEPS.md:1-3` | 没有历史标记的 2026-11-07 推进顺序 | 旧窗口/旧 boot-args；当前计划见 STATUS 与 `docs/plans/` | 【实测】 |
| `docs/audits/FORK-REVIEW.md:1-7` | 只写到 2026-10-31 基线 | 2026-11-17 重查 `scripts/audit-forks.py` 返回 PARTIAL（GitHub compare API 全部 404），无新 ahead/behind，不能解释成无更新 | 【实测】 |
| `docs/plans/GPU-TODO.md:81` | 旧崩溃归因 | 与 STATUS `:396-406` 冲突；2026-11-17 已加更正注并保留历史 | 【已修】 |
| `docs/plans/GPU-TODO.md:25` | 硬编码上游 SHA | ★37 禁止把 pin 写进进度文档（应由 catalog/水位持有）；2026-11-17 已改为现查命令 | 【已修】 |
| `patches/wifi/README.md:4-30,67-68` | `0001–0010`、`optional/0011`、`0010-scripts-build-xnu-4k-baseline-wifi.patch` | 实际为 `0001–0012` 共 12 个补丁、`series` 12 行，没有 `optional/` 子目录；2026-11-17 已更新表格与接线状态 | 【已修】 |
| `docs/plans/WIFI-REBUILD-CHECKLIST.md:236` | “按 `patches/wifi/series` 顺序 `git apply` 十条落地” | 当前 `series` 12 条（0001–0012），已改为“当前 12 条，以 `series` 为准” | 【已修】 |
| `README_EN.md:17-39` | 八步表的硬件名、未跟踪标签与表尾说明仍是中文（`触摸（Goodix GT9916R / BERLIN）`、`电源`、`诊断`、`基带`、中文 footer） | `render('en')` 一直取 TOML 的 `name`；2026-11-17 已加 `name_en` 与英文 UNTRACKED/footer，`check-readme` 现在扫描整个 README_EN（只放行两处语言链接标签）并校验标题层级与代码块数量 | 【已修】 |
| `docs/research/touch/07-verification.md:7,15`、`docs/research/07-verification.md:7,15` | 称 `GOODIX-TOUCH-PORT.md §3.1` 的断言值错误（应为 1080/2412） | 2026-11-17 复核：当前 `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch:85` 已是 `max_x==14400 && max_y==32000`，计划文档正确；旧记录来自旧补丁快照，两处 07 已改为复核结论 | 【已修】 |
| `docs/plans/GPU-ENABLE-PLAN.md:225,268` | 称 `pong-touch-console.patch:61-65` 要求 1080/2412 | 本仓补丁已改为 14400/32000（`MZYSL-DIFF.md:115`）；已注明 1080/2412 是 Pong 原值 | 【已修】 |
| `docs/plans/GOODIX-TOUCH-PORT.md:109-121` | §3.1 称触摸仍是 `planned`，并列三个缺口（ADT 1080/2412、缺 `pong_touch=1`、Pong 的 ldoc3/ldoc12 与 RSC） | 2026-11-17 复核：ADT 已由 `d0956cd9`/`708f4d25` 改为 14400/32000；驱动默认 `enabled=1`、`stage=6`；`io_supply_on()` 已改为 AVDD GPIO71 + IOVDD RPMh；2026-11-14 已单指上机，§3.1 已改为复核记录 | 【已修】 |

**已正确、不要"修"的**：`README.md:135-136` 的 ★1–★37 / P-01–P-230 是对的；`check-readme.py` 正是为
这两行写的（P-205 的教训：README 曾写 ★35/P-130 而实际 ★37/P-204）。**它只校验 README 与 README_EN**，
所以 INDEX、`docs/engineering/README.md`、STATUS 的同款数字才一路错到今天。

## 3. 重复权威与上游快照（G2）

三份互不相容的规则/坑文件：

| 文件 | 规模 | 编号体系 | 来源 | 危害 |
|---|---|---|---|---|
| `docs/engineering/HARD-RULES.md` | 2,502 行 | ★1–★28、★32–★37（缺 29–31） | 我们自己的权威 | — |
| `docs/ops/HARD-RULES.md` | 467 行 | HR-01–HR-12，自称"唯一权威" | 上游 pick `97b84eb7`（2026-11-12，yibiya 88 commits） | HR-01"默认禁止访问 RSC"已被 `engineering/HARD-RULES.md:1130` 推翻，照它执行会与 P-215 修复方向相反 |
| `docs/engineering/PITFALLS.md` | 223 个标题，最大 **P-230** | P 编号 | 我们的权威 | — |
| `docs/ops/PITFALLS.md` | 1,169 行，最大 **P-76** | 同一个 P 编号空间 | 同上 pick | 同一个 "P-76" 在两份文件里是两条不同的坑 |
| `docs/reference/PITFALLS.md` | 148 行 | 第三份副本 | 更早的搬运 | 三份都可能被搜索命中 |

`docs/INDEX.md:38` 只写"ops/ 运行手册"，没有一句话说明它是**上游快照**。修法（本轮已做）：
在 `docs/ops/` 加一份 `README.md` 说明它是 2026-11-12 的上游快照、不具权威、编号与本地 P/★ 不可混用；
并在两份文件头部加同样两行。删文件不是本轮能决定的事（可能要保留上游对照）。

## 4. 索引与覆盖（G3）

- `docs/INDEX.md` 198 行；`docs/research` 下 67 个 md 中 **19 个**在 INDEX 正文里没有任何一行；
  `check-docs.py` 只遍历 `docs/research` **顶层**（`os.listdir` 非递归，`:79/:84`）且用裸 basename 匹配，
  子目录里的孤儿永远不报。
- `docs/research/README.md` 只列 11 项（结论层精选），没有说明"这不是全量"。
- `docs/engineering/REPO-MAP.md` 是好的（最后核对 2026-11-12）：三仓库、构建输入、构建树、DTB 选择、固件卷都在；
  但它不覆盖"20 个并行检出分别在哪条分支"（见 §6）。

## 5. 引用完整性（G4）

**【实测】** docs 内仓库相对路径引用 2,207 处；去重后 **217 个目标不存在**（共 436 处出现）。
行号越界 14 处，典型：

| 引用处 | 引用的目标 | 实际 |
|---|---|---|
| `docs/engineering/BOOT-ARGS.md:83` | `drivers/PongAdreno/PongAdrenoNativeGlue.cpp` 的 `:62` | 该文件 52 行；发布调用实际在 `:39-45`（2026-11-17 已修） |
| `docs/engineering/PITFALLS.md:3508`、`:3595` | `porting.toml` 的 `:248`、`:240` | `porting.toml` 223 行；两处引文在现记录里已不存在，已改为指 `[[area]] id = "gpu"`（`:107`） |
| `docs/plans/120HZ-PORT-PLAN.md:203` | `PongAdrenoScanout.cpp:682` | 176 行 |

**2026-11-17 复测（门禁口径）**：`scripts/check-doc-citations.py` 已落地（基线 `docs/engineering/DOC-CITATIONS-BASELINE.toml`，`check-docs.py` 调用）。门禁口径比上表的手工扫描更宽（含无行号纯路径、多了根文档），测得 **2,528 处**引用、**308 个**目标不存在、行号越界 **0**。上表 14 处越界里，2 处加上 `pong:`/`zizhan:` 仓库限定后不再算本仓（`PongAdrenoScanout.cpp:682`、`ArmDTPlatform.cpp:254`），其余 13 个键（17 处站点）已逐条修正：`docs/ops/HARD-RULES.md` 两条改到真实行/去行号、`docs/engineering/BOOT-ARGS.md` 的 `:62`→`:39-45`、审计表自身两条拆成「文件 + 行号」写法、`FEATURES-DRIVERS-RESEARCH-2026-10-31.md` 两处标 `sheng:`、`docs/plans/MZYSL-DIFF.md` 六个键标 `mzyxsl:`、`PITFALLS.md` 与 `GPU-TODO.md` 对 `porting.toml` 的 `:248`/`:240` 两处引用改指 `[[area]] id = "gpu"`（`:107`）。

**2026-11-17 二次收敛（同一门禁，基线 102）**：把 124 个实际属于其它本地检出的目标加仓库限定后，
口径变为 **2,148 处引用、102 个目标缺失、0 处行号越界**。做法分三类：①按 `docs/research/LINE-RESEARCH-MAP.md`
的节头给 97 条 bullet 加检出前缀（如 `k60-adsp-handoff:docs/research/...`）；②对 49 个文件里 260 行裸引用按
「该路径在哪个检出存在」批量加 `unixnu:`/`sheng:`/`pong:`/`zizhan:`/`liuqin:`/`k60-wifi:`/`k60-bt:`/`linux:`
（label 由脚本逐个 `os.path.exists` 判定，不按目录猜）；③零散修正 13 处：6 个 `patches/xnu/...` 占位改真名、
`0401/0602` 旧补丁名改真名、`0621/0622` 标 `k60-cellular:`、Pong{Power,Audio,Cellular,Thermal}/K60Backlight
五个文件标线检出、`track-upstream-branches.py` 改 `<workspace>/scripts/`（它从来不在仓库里）。
剩余 102 个按目录：scripts 56、drivers 19、package 11、patches 5、docs 4、configs 3、dts 2、kits 2 —— 全部是
「历史上真的删掉了」「只存在于上游 pong/sheng 早期树」或「命令行片段里的相对路径（按执行目录解释，不是引用）」三类，
基线冻结、新增即 FAIL。

**指向 docs/research 但 main 上不存在的引用（8 处，逐条核实过实体在哪）**：

| 引用处 | 目标 | 实体现状 |
|---|---|---|
| `docs/research/REFERENCE-INDEX.md:322` | `research/audio/AMPS.md` | 只在 `k60-audio` 检出 |
| `docs/ops/HARD-RULES.md:82` | `research/bt/EVIDENCE.md` | **任何检出都没有** |
| `docs/engineering/STATUS.md:301` | `research/display/BACKBOARD-CRASH-FAMILIES.md` | 只在 `k60-display` |
| `docs/ops/HARD-RULES.md:83-85` | `research/power/01-same-hardware.md` 等三份 | **路径写错**：实体是 `docs/research/01-same-hardware.md` 等（无 power/ 目录） |
| `docs/engineering/PITFALLS.md:4379`、`:4503` | `research/touch/13-STAGE-ONE-ROOT-CAUSE-MATRIX.md` | **任何检出都没有** |
| `docs/research/wifi/BLOB-RESIDENCY.md:191` | `research/wifi/BOOT-DEATH-SUSPECT.md` | 只在 `k60-wifi` |
| `docs/research/wifi/BOOT-DEATH-BISECT.md:6`、`:364`；`docs/plans/WIFI-REBUILD-CHECKLIST.md:23`、`:293` | `research/wifi/LOCAL-VERIFICATION.md` | 只在 `k60-wifi` / `k60-wifi-lead` |
| `docs/plans/WIFI-REBUILD-CHECKLIST.md:294` | `research/wifi/STAGE-BRINGUP.md` | 只在 `k60-wifi` |

> **2026-11-17 部分已修**：上表 11 条「指向不存在的 research 文件」全部处理——能定位到线检出的
> 改成显式「（在 k60-XXX 检出，main 未收录）」；路径写错的三条改成 `docs/research/0X-*.md`；
> 两份任何检出都没有的（`bt/EVIDENCE.md`、`touch/13-STAGE-ONE…`）写明不存在与抢救副本位置。
> 217 个里已处理 139 个（97 条地图 bullet + 42 条跨仓/改名），其余冻结在基线（含命令行片段）。

**机制修复（2026-11-17 已做）**：新增 `scripts/check-doc-citations.py`，由 `scripts/check-docs.py`
的 `check_citations()` 调起，所以文档门禁现在会真的检查引用。口径比上表宽（多扫 README /
README_EN / AGENTS / CREDITS，行号支持 `:12-34` 范围），首版实测 **2,647 处引用、311 个目标不在本仓库、
15 处行号越界**，冻结基线 326 条；2026-11-17 收敛后为 **2,148 / 102 / 0**（基线 102 条），
基线之外新增一处就 FAIL，修好一条后跑 `--update-baseline` 收紧。单测见
`scripts/tests/test-check-doc-citations.py`（5 例：正常引用 / 缺失目标 / 越界行号 / 无行号纯路径 / 基线往返）。

## 6. 调研的物理分布（G5）

【实测】20 个 `k60-*` 检出共用同一个仓库；main 上 `docs/research` 有 71 个 md/toml，其余检出相对 main 的**独有**研究文件：

| 检出 | 分支 | 研究文件 | 不在 main 的 |
|---|---|---|---|
| k60-cellular | feat/cellular | 72 | **18** |
| k60-wifi | feat/wifi-bringup | 85 | **14** |
| k60-thermal | feat/thermal-tsens | 66 | **12** |
| k60-bt | feat/bt-research | 81 | **10** |
| k60-usb | feat/usb-console | 61 | 7 |
| k60-audio-merge | feat/audio-merge | 60 | 6 |
| k60-display | feat/display | 75 | 6 |
| k60-adsp-handoff | feat/adsp-handoff-owner | 75 | 4 |
| k60-audio / k60-buttons / k60-springboard / k60-wifi-lead | 各自 | 52–57 | 3 各 |
| k60-gpu-user / k60-ios-profile | 各自 | 55–56 | 2 / 1 |

合计约 **92 个研究文件**只活在分支上。后果已经在 `EIGHT-STEPS.toml` 上出现：
它引用 `docs/research/bt/{06-DEEP-DIVE,FIRMWARE,RESEARCH,S1-PROBE-SPEC,S3-SPEC,S4-SPEC}.md` 与
`docs/research/touch/14-RETAINED-KO-INIT-AUDIT.md` 共 **7 个 main 上不存在的文件**。

修法：每个硬件"结案"时把该线研究**整目录**合进 main（而不是留分支）。
**映射已建**：`docs/research/LINE-RESEARCH-MAP.md`（2026-11-17 05:45 复核为 **16 个检出 / 108 个文件**，00:20 首扫为 97，
本段此前按 92 计，漏了 `UniXNU-zizhan` 的 4 个与个别新增；以那份为准），
由 `E:/k60-work/scratch/refmine/linemap{,2}.py` 生成，可直接改成仓库脚本。
本轮仍不搬文件：这些内容可能已被各自的新结论取代，搬运要各线 owner 点头。

### 6.1 `EIGHT-STEPS.toml` 的 wifi 段已过期（G6）

`:390-426`：`status = "parked"`、`parked_why = "缺设备/缺前置依赖…无 evidence"`、`step.decompile.done = false`、
`step.verify.done = false`（"未做"）、`step.device.done = false`（"从未上机"）。
而 2026-11-14 起 c1–c8 已全部实飞，P-215 已结案（`docs/engineering/MAIN-BASELINE.toml:198`、`RULES.toml:707` 都写着
c3 进 SpringBoard 132），c4/c5/c6 进桌面、c7 已判读到 SBL/READY。
**本轮不擅自改 done/status**（那是门禁数据，改它等于改放行条件）；只在文件里加一条显式"本行已过期"的注释，
把重评交给 Lead。同类需要复核的还有 audio（verify/device=NO）与 charger（planned）——它们可能同样落后于实际飞行。

## 7. 复用矩阵：缺的不是轮子，是"跟上"（G7）

子 agent（reuse-gaps）对 14 个移植区逐一比较了"我们写的 / 现成最好的 / 关系 / 能不能抄"。结论：
**我们大多是 Pong 的早期 fork，损失主要在后续上游提交**。以下数字我复核过标【实测】，其余标【转述】。

| 区 | 我们实现 | 现成最好的 | 关系 | 现在能抄？ | 风险 |
|---|---|---|---|---|---|
| GPU/Metal | `drivers/PongMetal/` 267,785 B；前端 `NativeBridgeMetalFrontend.mm` **109,178**【实测】 | `references/pong-metal@0b3b34a` 952,507 B；同文件 **225,616**【实测】 | 同源更晚 | **是**：前端 + `bridge/NativeMetalObjects.rs` 135,840 + 10 个头 + `shaders/scanout_convert.ll` | 高（backboardd 崩溃面） |
| WiFi 接线 | `patches/wifi/` 主仓 0001–0012 = **221,744 B**；`k60-wifi` 同 series **228,302 B**，5 个文件不同（0003/0007/0009/0010/README）【实测】 | `k60-wifi:feat/wifi-bringup` 的 `patches/wifi` 更完整；`board.toml:20` 两边都仍只挂 `patches/xnu/series`，没有自动 applier，`MERGE-REQUEST.md` 记录的是 `/opt/k60/trees/wifi-device` 手工 `git apply` | 分支独有 | **补丁字节差已在 `feat/wifi-patch-sync` `5d70dd08` 同步**（从 `origin/main` 拉出，仅 4 个补丁文件）：12 个补丁与 k60-wifi 逐字节一致；再把 applier + `k60_wifi_stage` 门搬进 main | 高（MHI/AMSS） |
| WiFi 源码 | patch 0001 冻结 `vendor-zizhan-087416a`（134,576 B） | `references/pong-wifi`：Platform **40,342**、Net **47,407**、Pci **6,010**、ath11k **7,248**【实测】 | 同源更新 | 是：替换 0001 的 vendor dump | 高 |
| UFS 根发布层 | `drivers/NativeUfs` 7 文件 ~82 KB（main）；`k60-ufs-verified:feat/ufs-verified-table` 已移植 `VerifiedTableCache`/`RootPublication`/`RootWindowRead` + `RootPolicyTable`/`RootWindowVerifier` 与 host 测试，3b 把 `PongUfsBlock` 拆成 prepare/publish 并接异步发布（`46545497`） | `references/ShengUfs@9d527ae`：`NativeUfs.cpp` **149,596**、`VerifiedTableCache.h` **6,878**、`RootPublication.h` **3,225** + tests【实测】 | 官方组件（catalog pin `99d8bcd` 无此层） | 分支已做：VerifiedTableCache + RootPublication/RootWindowRead + 3 个新增测试 + 3b 异步发布；未合 main | **高**（根挂载，P-152/153） |
| Metal 测试 | — | `UniXNU/drivers/AdrenoMetal`：`OfflineMetalFrontend.mm` 75,688 等 5 个 | 官方组件 | 是：当回归网 | 低 |
| ADSP provider | `K60AdspOwnerStages` 只有契约 | `pong-power`：`PongPlatformResources.cpp` **4,230**、`PongPower.cpp` **1,970**、`PongAdsp.cpp` 33,318【实测前两个】 | 同源缺失 | 是：补 owner 的 ops | 高（卡音频/WiFi） |
| 音频传输 | `0503/0504/0505` 补丁，compile-only | `pong-power`：`ShengGpr.c` **4,165**、`ShengAudioReach.c` **17,656**、`PongAudioService.cpp` 7,421【实测前两个】 | 同源缺失 | 是：GPR + AudioReach opcode + service | 高 |
| BT 用户态 | `0500-k60-bt-qbt-new-files.patch` 156,632 B（内核侧） | `UniXNU/QcaBluetooth`：`tools/build-bluetool.py` 2,503、`build-type0.py` 2,941 + `userland/`【实测】 | 官方组件 | **只能抄骨架**：BlueTool/Type0 是 iOS 27 24A446；Type0 构造器锁 LC_UUID `8E49197B-E6BC-3F3B-A8D3-DF4BEDD37F01`、bluetoothd SHA-256 `cfd94854…`，不能直接用于 20G81。可抄 build/sign 流程、XPC 服务骨架、`kern.qbt_*` 只读 sysctl 契约、版本校验写法 | 中 |
| BT ADT 节点 | 无 | `docs/porting/bluetooth.md` 的 `arm-io/bluetooth` 模板 | 官方文档 | 是：自己写节点 | 中 |
| CPU | `ArmCpu.cpp` 21,792 | 官方 `ArmCpu` 38,129（@93a5030） | 官方 | 择段：GIC/timer 16 KB | 低 |
| RAM 块 | `NativeRamBlock` 25,309 + 4 变体 17,911 | 官方 `RamBlock` 23,637 + 测试 21 KB | 官方 | 是：5 个测试当回归 | 低 |
| 显示 | `PongDsiPanel.cpp` 14,936（自写） | 官方 `GopFramebuffer` 无 16.6.1 builder；Pong scanout 三件套 | 官方不可用 | 否：先 re-diff scanout | 高 |
| 触摸 | `zzzz…pong-touch-console.patch` 63,484 | 官方 `QcomGeniSpi` 15,536 + `ShengHidInput` | 官方 | 择段：多点/晚 .o 语义 | 中 |
| 打包/诊断 | `build-bootimg.py` v4 4096；ramoops | Pong 同布局；`pong_ramoops_console.h` | 同源 | 否 / 择段 pmsg | 低 |

**Top 8（按解锁阻塞排序；完整 15 条在子 agent 报告）**

1. Metal 前端（`pong-metal@0b3b34a`）→ `drivers/PongMetal/`，再补 20G81 ABI 差量。**直接对着 backboardd 崩溃。**
2. WiFi 补丁接线（`patches/wifi/series` 的 applier + 门）→ main。**解锁 MHI/AMSS。**
3. WiFi 源码升级（`pong-wifi` 新于 087416a vendor dump）。
4. ADSP provider（`PongPlatformResources` + `PongPower` + `PongAdsp` 的 client/GPR/GLINK 段）。
5. UFS `VerifiedTableCache` + `RootPublication/RootWindowRead` + 测试。**根挂载**。
6. 音频 GPR/AudioReach 传输 + `PongAudioService`。
7. BT userland（BlueTool/Type0）+ `arm-io/bluetooth` 节点。
8. GPU 诊断/UserClient（`NativeGpuTrace`、`GpuTraceStore`、`NativeAdrenoHandleIndex`、`NativeAdrenoService.cpp`）。

**顺带发现的两条"文档真相"**：`docs/plans/OFFICIAL-DRIVER-MAP.md` 应补记——
ShengUfs 的 main 与 catalog pin 不同步；`PongUfs` 本身也是 catalog 组件；`pong-metal@0b3b34a` 晚于我们那次 import；
`patches/wifi` 在 main 上无读者。另：`patches/xnu/0610-k60-metal-seeds.patch` 不在 series（G9），但
`scripts/tests/test-series-source.py:8` 已把它记作 retired——它是 `0610-k60-metal-plugin-deploy.patch` 的
**退役前身**，不是没人要的垃圾。正确处置是给它一条退役登记（或与 wifi 线确认后删除），
而不是按「没人用的补丁」直接删：`PITFALLS.md:3978` 记的正是它被误接进序列后出事的现场。

2026-11-17 已由 `3dae8347` 在 `PATCH-CATALOG.toml:98-102` 登记为 `retired`（evidence `3a8d61d8`）；文件保留，删除与否等 wifi 线确认。

### 7.1 Top 8 落地顺序（2026-11-17 修订版）

原 Top 8 按「解锁阻塞」排序；这一版按「先只读、后可跑、最后动构建序列」重排，路径都写成可直接核对的本地位置。
每一项只到「源码/脚本可抄」，不声称已集成。

| 顺序 | 项 | 从哪抄（本地路径） | 我们现状 | 为什么这个顺序 | 验收 |
|---|---|---|---|---|---|
| 1 | UFS 验证表/根发布层 | `references/ShengUfs@9d527ae`：`VerifiedTableCache.h` 166 行、`RootPublication.h` 84、`RootWindowRead.h` 54 + tests | `drivers/NativeUfs` 7 文件约 82 KB（main）；`k60-ufs-verified:feat/ufs-verified-table` 已有这一层、3 个新增 host 测试与 3b 异步根发布（`46545497`） | 纯头文件/只读，先立回归网；直接对着根挂载（P-152/P-153） | 编译 + 6 个 host 测试（3 个原有 + 3 个新增）；草案见 [`plans/SHENGUFS-VERIFIED-TABLE-PORT.md`](../plans/SHENGUFS-VERIFIED-TABLE-PORT.md) |
| 2 | BT userland | `QcaBluetooth`：`userland/BlueTool.c`、`Type0.c`、`tools/build-bluetool.py` 2,503 B、`build-type0.py` 2,941 B | `0500-k60-bt-qbt-new-files.patch` 只有内核侧 | **只能抄骨架**：BlueTool/Type0 是 iOS 27 24A446，Type0 锁自身 LC_UUID 与 bluetoothd SHA-256，20G81 不能直接运行；先抄 build/sign 流程、XPC 服务骨架、`kern.qbt_*` sysctl 契约 | 脚本产出与 QcaBluetooth 同结构；XPC 服务骨架可在 20G81 编译（不加载 Type0） |
| 3 | 音频传输 | `references/pong-power`：`ShengGpr.c` 4,165 B、`ShengAudioReach.c` 17,656、`PongAudioService.cpp`、`PongAudio.cpp` | `0503/0504/0505` compile-only | audio planned，纯代码，先补传输层 | 编译 + opcode/route 表单测 |
| 4 | ADSP provider | `references/pong-power`：`PongPlatformResources.cpp` 240 行、`PongPower.cpp` 66、`PongAdsp.cpp` 714 | `K60AdspOwnerStages` 只有契约 | 承接 battery/PAS1 缺口；依赖 3 的 GPR/GLINK | host suite（owner 77 场景）不回归 |
| 5 | Metal 前端 | `references/pong-metal@0b3b34a`：`NativeBridgeMetalFrontend.mm` **225,616** vs 我们 **109,178**；`PongMetalPlugin.mm` 14,777 vs 11,899；`bridge/NativeMetalObjects.rs` | `drivers/PongMetal` 267,785 B | 对着 backboardd 崩溃面：先要 GPU 直连 RSC 验证通过再换前端 | 20G81 ABI 差量清零 + backboardd crashed=0（上机） |
| 6 | GPU 诊断/UserClient | `pong-adreno`、`pong-adreno-metal`（patch 0001–0024） | 无 `NativeGpuTrace`/`GpuTraceStore`/`NativeAdrenoHandleIndex` | 与 5 同线，先有前端再补诊断 | 客户端连接 + trace 输出 |
| 7 | WiFi 补丁接线 | `patches/wifi/series` 12 条（主仓 221,744 B；`k60-wifi` 228,302 B，5 个文件不同）+ `k60-wifi:feat/wifi-bringup` | main 无读者（仅 `scripts/tests/test-pong-smmu-lease.py:76` 断言 0012 在 series） | 会动构建序列，等 Lead 对 `patches/wifi` 的裁决；字节差已在 `feat/wifi-patch-sync` `5d70dd08` 同步 | series 可被 main 的 applier 应用、`k60_wifi_stage` 门存在 |
| 8 | WiFi 源码升级 | `pong-wifi`：`PongWifiPlatform.cpp` 40,342 B、`PongWifiNet.cpp` 47,407、`PongWifiPci.cpp` 6,010、`ath11k/PongAth11k.c` 7,248 | patch 0001 冻结 `vendor-zizhan-087416a` 134,576 B | 会重刷 patch 0001 基线，最后做 | 0001 重新生成后 7 项一致 + MHI 行为不变 |

**不抄的**：`pong-adreno` 的 GPL 混合部分只读思路；官方 `ShengUfs/NativeUfs.cpp` 149,596 B 与我们版本差异过大，先只抄三个头文件与测试。

## 8. 联网调研：已有结论与仍未知（G10）

### 8.1 已找到、可直接对照的

| 来源 | 许可证 | 价值 |
|---|---|---|
| `Chengdong-Yu/pong-wifi`（本地 `/e/hackios/pong-wifi`） | BSD-2-Clause-Patent | 同 SoC 同芯片板级层：GPIO 80/94/95/96/204、MSI SPI140→INTID172、PARF MSI0 bit23、TCS4 DRV2、GDSC `0x162128`、PCIe0 GDSCR `0x17b004`、SID `0x1c01`；其日志停在 102 MHI 通道后 RDDM |
| `Chengdong-Yu/pong-power`（本地 `/e/hackios/pong-power`） | BSD-2-Clause-Patent | PAS1 40 MiB carveout、SMEM `0x80900000+0x200000`、TCSR mutex3 `0x1f43000`、IPCC `0xed18000`/INTID261、AOSS `0xc300000`、Glink/Battmgr/AudioReach/GPR |
| `UniXNU/QcaBluetooth`（本地 `/e/hackios/QcaBluetooth`） | APSL/BSD | GENI UART + type-0 适配器的官方实现（userland + tools）；userland 是 iOS 27 24A446，Type0 锁自身 LC_UUID 与 bluetoothd SHA-256，20G81 只能抄骨架不能直接用 |
| `daimile2/renoir_xnu_bluethooth`（**新发现，未考察**） | BSD-3-Clause | 题名即"Renoir QCA6490 Bluetooth for XNU：kernel patches + native iOS type-0 adapter"——与我们的 BT 缺口同芯片、同 OS 侧 |
| `qiumochen/UniXNU-zizhan` | NOASSERTION | SM8475 + darwin24，自称 WiFi 端到端（WPA2/DHCP/HTTPS/漫游）、A730 95.3 fps、PMIC GLINK 电池；只能当**行为对照**，不能抄代码 |
| `oosexgang/hakios-xnu-kernel` | MIT+APSL | `hakios.goodix.c` 52.9 KB GT9916 Berlin-D SPI；WCN6750 WiFi 193 KB（不同芯片） |
| `pong-adreno` / `pong-adreno-metal` | 混合 BSD+GPL / MIT | A730 GMU/CP/HFI/ZAP/SMMU/scanout；Metal render-server plugin（`NativeBridgeMetalFrontend.mm` 等 24 个 patch） |
| lore（MHI ELF 讨论） | 邮件列表 | FBC image = ELF 头 + SBL/RDDM/AMSS 段；BHIe 阶段要先 `fw_data += sbl_size` 跳过前 512 KiB —— 与 c7「BHI 已送 512 KiB、BHIe 未发起」一致 |
| `PNSoniX/Np2-WiFi-Fix`、`MemerGamer/np2-wifi-keeper`（**新发现，未考察**） | MIT | Nothing Phone 2 的 QCA6490 **PCIe link failure** 修复/保活说明——可作为我们 PCIe0/冷启动失败面的对照 |
| `dianjixz/aw882xx`、`atomx-sm8350/android_driver_awinic_aw882xx` 等（**新发现，未考察**） | GPL-2.0 / 无许可 | AW882xx 智能功放驱动；本地**没有**任何副本，是音频线缺的那块。无许可的那两个只能读思路 |
| `Fcaing/hakios-venus`（**新发现，未考察**） | NOASSERTION | 小米 11（SM8350）iOS 16.5 HakiOS bring-up 的"已验证功能"清单，可对照同代 SoC 的可行边界 |

### 8.2 仍然未知（不要假装有答案）

- 公开的 MHI/BHI 寄存器序列与通道表**没有**（只有 GPL 的 ath11k，vendor spec 是 NDA）。
- QCA6490/WCN6855 的分区布局没有权威文档；只能从设备 dump 反推。
- 没有独立的用户态 AMSS loader；AMSS 只能由内核侧 MHI 状态机推。
- ADSP/PMIC-GLINK/AudioReach 的第三方 XNU 实现只有 pong-power 与 zizhan 两家。
- AudioReach 的 topology 仍无上游文档。
- FreeBSD 侧没有 MHI host（2.6 KB stub，ath11k 的 QMI 也是 TODO）——**不要**指望从 FreeBSD 移植。

### 8.3 本地参考仓的上游漂移（2026-11-17 补）

| 参考仓 | 我们 vendored | 上游 HEAD | 未移植 |
|---|---|---|---|
| `UniXNU/QcaBluetooth` | `986d631`（k60-bt 的 `0500` 补丁与 D9 的 `0516` 都基于它） | `effe4ec`（2026-11-17） | 4 个非 merge 提交 / 6 文件 +198/−4：`68e2e60` extended discovery counters（`trace_hci` 回调、`qbt_discovery_stats`）、`32dab19`/`e853395` Classic Inquiry trace（`trace_command`/`trace_event`/`trace_tx`）、`5d5ae94` LE event mask trace。均为诊断/计数增强，不是控制器修复；HCI 扫描验证时再抄，不影响当前固件下载阻塞。 |

结论：这不是"缺轮子"，是 vendored 版本落后；`REFERENCE-INDEX.md` 的 pin 已同步到 `effe4ec`，第 15 节补了覆盖缺口行。2026-11-17 同时复核了 REFERENCE-INDEX §2.2 的稳定参考快照：AdrenoMetal `9a9da56`（121 文件）、ShengUfs `9d527ae`（35 文件，`NativeUfs.cpp` 149,596 B）、UniXNU-sheng/-upstream `bc05635`（各 584）、UniXNU-upstream `9931232`（2,265）；共享检出的分支/HEAD 会随各线漂移，未写死在该表。

### 8.4 本轮网络限制（写下来免得下轮重复踩）

`web_search` → HTTP 402（DeepSeek 余额不足）；`api.github.com` 前两次成功、之后 403 限速；
`raw.githubusercontent.com` 直取 `fetch failed`。所以 §8.1 里标"未考察"的四条只拿到仓库元数据
（名称/许可/描述），**没有读代码**。网络恢复后第一件事：读 `renoir_xnu_bluethooth` 的 BT 补丁与 type-0 适配器。

## 9. 机制修复建议（比逐条修更重要）

1. **引用门禁**：**已做（2026-11-17）** `scripts/check-doc-citations.py`（路径存在性 + 行号上限），由 `check-docs.py` 调起，
   欠账从 326 条降到 102 条、行号越界 0；剩余目标的分类见 §5，新增即 FAIL。
2. **数字不要手写**：★/P/RULES/series/patch 计数在 `check-readme.py` 已有实现，扩展到 INDEX、`docs/engineering/README.md`、`docs/engineering/STATUS.md`、`AGENTS.md`（同一段逻辑，多传几个文件）。**2026-11-17 已做**：range 校验覆盖上述四份文档（写了才校验、写错即红），并校验 AGENTS.md 的 `N patch files with M entries` 与 `patches/xnu` 实际 .patch 数、series 条数；同时校验 README/README_EN 正文里的 `当前 N 条` 规则数与 `RULES.toml` 的 `[[rule]]` 条数（2026-11-17 追加）。
3. **研究可见性**：`docs/research/README.md` 改成"结论层索引 + 指向 INDEX 全量"；INDEX 的 research 段由脚本从目录生成，
   或至少加"未列出文件"小节（本轮先加了指针）。**2026-11-17 已做**：`docs/research/README.md` 由目录生成，
   69 个 md 全量按目录分组；`check-docs.py` 的 `check_subdir_indexes()` 改成对 research 递归校验；INDEX §3 改为结论层摘选 + 指针。
4. **线→检出映射**：新增 `docs/engineering/LINE-MAP.md`，每行 = 线 / 检出 / 分支 / 研究目录 / 当前结论；
   由 `line-research-map2.py` 生成初稿，人工补结论。**2026-11-17 已做**：`docs/engineering/LINE-MAP.md`（18 行，含 owner 与两个未登记检出），
   逐文件清单仍以 `docs/research/LINE-RESEARCH-MAP.md` 为准；不设门禁（HEAD 会漂移）。
5. **catalog 与 pin 的差**：`check-component-pin.py` 对每个 catalog 组件的 `revision` 与本地参考树 HEAD 比较，
   不一致就要求写一行"为什么不用 pin"。这次 ShengUfs 的差就是这么漏掉的。**2026-11-17 已做**：
   `scripts/check-component-pin.py` + `docs/engineering/COMPONENT-PINS.toml`（board 组件硬校验，3 条 deviation：
   ArmCpu 9066b53b vs 93a5030c、XnuPrelink f876e3ee vs c645d76b、PongUfs 138a9fb0 vs c959284f；非 board 组件只告警），
   登记为 P-231，5 例单测。
6. **退役补丁要有登记**：**已做（2026-11-17）** 新增 `docs/engineering/PATCH-CATALOG.toml`（series 之外的 41 个文件：
   retired 9 / renumbered 3 / library 29），并在 `scripts/check-patch-series.py` 加 `check_catalog()`——
   series 外的每个 `.patch` 必须有登记、status 只能是三种之一、retired/renumbered 必须写 evidence；
   只要求「必须在 series」会误伤退役前身（G9）与共享补丁库，所以用目录而不是删除。
7. **上游快照要带横幅**：任何 `docs/ops/` 这类 pick 进来的目录，文件头必须写明来源 commit 与"非权威"。
8. **门禁自测要能脱离环境变量跑**：`K60_DEVICE_INPUT` 不导出时，main 上 `check-rules.py` 实际红 **7** 条，不是 P-230 注释里记的 5 条——
   iron-4/iron-5/hard-33/P-165/P-166 是被 `scripts/check-build-applied.py:30` 直接拒绝；而 **P-214 与 P-220 是自测 import 了 `scripts/porting-gate.py`**，
   后者在模块级 `:48-52` 就 `sys.exit`，测试捕到 SystemExit 之后拿到的是半个模块
   （`AttributeError: module 'porting_gate' has no attribute 'series_fingerprint'`，`test-check-build-applied.py:38` 则连 setUp 都过不去）。
   修法：把"取环境"从模块顶层挪进 `main()`，或让测试在 import 前注入指向临时镜像的 `K60_DEVICE_INPUT`。
   否则任何没设变量的 CI 都会把"环境没给"读成"代码坏了"——正是 P-220 自己讲的那类错。
   **已做（2026-11-17）**：`porting-gate.py` 与 `check-build-applied.py` 改为『导入不退出、命令行才拒绝』——
   前者把 `K60_DEVICE_INPUT` 的拒绝挪到 `[X]` 段与 `__main__` 入口，后者挪进 `main()`；新增
   `scripts/tests/test-gates-import-without-device-input.py`（2 例）。现在不导出变量跑 check-rules 与导出时同为 5 条既有红，
   P-214/P-220 不再假红。
9. **登记的检查可能在空转**：P-155 的 `check-patch-series.py` 一直从 `RULES.toml` 读 `expected_kern_exec_delta`，
   但这个键从未写进去——脚本每次都打印「未记录基线…跳过」并返回 0，门禁登记了却什么都没检查。
   **已做（2026-11-17）**：补上 `expected_kern_exec_delta = 1713`（41 个 series 补丁改 `bsd/kern/kern_exec.c`，+1764/−51），
   并验证改 1712 会红。教训：门禁的"跳过"分支必须显式登记为 waiver，不能静默返回成功。

## 10. 本分支已修 / 待 Lead 决定

**已修（本分支，截至 2026-11-17；提交与文件数以 `git log --oneline origin/main..HEAD` 与 `git diff --stat origin/main...HEAD` 为准）**：

- **文档卫生**：`INDEX`/`README`/`README_EN`/`engineering/README`/`STATUS`/`AGENTS` 的日期、★/P 范围、补丁与系列计数、断表、固件描述；
  `docs/ops/` 两份文件头加「上游快照、非权威」横幅并新建 `ops/README.md`；`EIGHT-STEPS.toml` wifi 段按 c1–c8 重评；
  `research/README.md` 全量索引（69 个 md）。
- **引用**：11 条指向不存在 research 文件的引用标出所在线检出；2,148 处引用中 124 个跨仓目标加 `unixnu:`/`sheng:`/`pong:` 等前缀；
  行号越界 0；基线 102。
- **门禁**：新增 `check-doc-citations.py`（基线 102）、`check-component-pin.py`（P-231，3 条 deviation）、
  `PATCH-CATALOG.toml`（41 条 series 外补丁）+ `check_catalog()`、P-155 的 `expected_kern_exec_delta = 1713`、
  `check-readme` 数字校验扩到四份文档（含 `RULES.toml` 的 108 条规则数）、`check-docs` 递归 research
  与 189 个 Markdown 的表格列数校验（6 例单测）、`docs/INDEX.md` 的阅读顺序表校验（5 例单测）、docs/ops 的 4 个历史快照横幅（3 例单测）、两个门禁脚本可 import。
- **研究可见性**：`LINE-RESEARCH-MAP.md`（108 个分支文件）、`LINE-MAP.md`（18 条线）；`SOURCES.toml` 三种路径前缀与 5 条新 required（QcaBluetooth×3、liuqin×1、Device-Binaries×1），研究源 53→58。

**待 Lead 决定（本文只报告，不动）**：

1. `EIGHT-STEPS.toml` 的 audio/charger/battery/buttons 条目要不要同样按实飞重评（wifi 段已做；改 `status` 等于改放行条件）。
2. 108 个分支研究文件怎么回 main：结案时逐份搬（建议）+ `LINE-MAP.md` 指向；地图不复制内容。
3. `docs/ops/` 的四份历史文件（HARD-RULES、PITFALLS、HANDOFF、TWRP-FACT-CLARIFICATION）：横幅已加、README 已登记，要不要移到 `docs/archive/upstream-ops/`。
4. `patches/wifi` 的 main 侧接线：把 `feat/wifi-bringup` 的 applier + 门搬过来，还是继续只在 wifi 分支构建。
5. §7 的 Top 8 抄写顺序（尤其 Metal 前端与 UFS 验证表——两者都对着已崩溃面）。

## 11. 取用清单（给合并到 main 的人）

全部在本分支，按目录分组：

- **门禁脚本**（`scripts/`）：`check-doc-citations.py`、`check-component-pin.py`、
  `tests/test-check-doc-citations.py`、`tests/test-check-component-pin.py`、`tests/test-check-docs-tables.py`、`tests/test-check-docs-ops.py`、
  `tests/test-check-docs-state.py`、`tests/test-check-docs-index-order.py`、`tests/test-check-patch-series-wifi.py`、`tests/test-gates-import-without-device-input.py`、`tests/test-render-eight-step-table.py`；修改 `check-docs.py`、`check-readme.py`、
  `check-patch-series.py`、`porting-gate.py`、`check-build-applied.py`。
- **门禁数据**（`docs/engineering/`）：`DOC-CITATIONS-BASELINE.toml`、`COMPONENT-PINS.toml`、`PATCH-CATALOG.toml`、
  `RULES.toml`（P-231 + `expected_kern_exec_delta`）、`PITFALLS.md`（P-231）。
- **文档**：本文、`LINE-MAP.md`、`LINE-RESEARCH-MAP.md`、`research/README.md`、`INDEX.md`、`README.md`、`README_EN.md`、
  `engineering/README.md`、`STATUS.md`、`AGENTS.md`、`ops/README.md`、`ops/HARD-RULES.md`、`ops/PITFALLS.md`、`ops/HANDOFF.md`、`ops/TWRP-FACT-CLARIFICATION.md`、`EIGHT-STEPS.toml`。
- **合并前在目标树跑**：`check-docs`、`check-readme`、`check-patch-series`、`check-component-pin`、`check-doc-citations`，
  以及 `tests/test-check-doc-citations.py`、`test-check-component-pin.py`、`test-check-docs-ops.py`、`test-check-docs-index-order.py`、`test-check-patch-series-wifi.py`、`test-gates-import-without-device-input.py`、`test-render-eight-step-table.py`；
  已知红只有 iron-4/iron-5/hard-33/P-165/P-166（构建输入镜像落后，见 P-230）。
- **不要从本分支取**：`drivers/`、`patches/`（除登记文件）、水位/基线。本分支没碰它们。

## 12. EIGHT-STEPS 其余四段与 `porting.toml` 的交叉核对（2026-11-17，只报告）

§6.1 只处理了 wifi 段。这一节把 audio / battery / charger / buttons 四段与 `porting.toml`（AGENTS.md 指定的设备状态权威记录）
逐条对照；**只报告，不改 `status`**——改 status 等于改八步门禁的放行条件。

| # | 条目 | EIGHT-STEPS 记录 | porting.toml 记录 | 不一致 | 建议 |
|---|---|---|---|---|---|
| 1 | audio | `status = "parked"`；①–⑥ done（DT 节点已建、四步方案、深挖三条） | `status = "planned"`；`limits` 仍写 "Hardware inputs and implementation are pending for this board." | 后者把硬件输入与实现写成「待做」，与已落库的 DT 节点/方案不符 | 只改 `porting.toml` audio 的 `limits` 措辞，不改 status |
| 2 | battery | `status = "active"`；①–⑦ done（`verify.local_verified = true`，27/27 + 30 断言）；⑧ false（usblog-20261115-223916 在 `K60ADSP owner stage=1 rc=-1000` 卡住） | `status = "planned"`；`limits` 写 "battery verify/local_verified/device remain false" | `verify`/`local_verified` 实际已为 true | 更新 `porting.toml` power 的 `limits` 中 verify 部分 |
| 3 | charger | `status = "planned"`；①–⑦ done（`test-k60-charger-subscription.c` 30 断言）；⑧ false | 无 charger area（由 power 覆盖） | 无直接冲突；但研究已完成仍标 planned | 可考虑把 charger 并入 power 的 findings，或 EIGHT 改 parked 并写明原因 |
| 4 | buttons | `status = "parked"`；official/wide false；verify false（本地命中检查过了，但仍缺上机）；device false | `input` area `status = "device-verified"`，`completion` 明确含 "buttons produce expected HID reports" | porting 把 input 标 device-verified，但按键从未上机验证 | 收敛 input 的 completion 措辞，或把 buttons 单独列为一个 area/状态 |
| 5 | battery ⑧ | `done = false`，prediction 的 success/failure 已写 | — | 一致 | 无需改 |
| 6 | wifi（对照） | `status = "parked"`，①–⑦ done，⑧ false | `network` planned | — | 已在 §6.1 处理 |

结论：3 处措辞/状态需要修（audio 的 limits、power 的 verify 说法、input 的 completion），1 处可选（charger 的位置）。
这些都不改八步 spec 的 status，因此不影响门禁；但 `porting.toml` 是设备状态的权威记录，建议由 Lead 或对应线主确认后改 3 句。

**2026-11-17 已改 3 句中的 2 句**：audio 的 `limits`/`next_action` 改为『硬件已盘点、实现待 audio 线』；power 的 `limits` 首句改为
『battery host verification 与 local_verified 已 true，device 仍 false』。input 的 `completion` 涉及区域状态（device-verified 只对触摸成立），
未改，留给 Lead/线主决定。

```sh
# 复算：四段的步骤矩阵
python3 - <<'PY'
import tomllib
d = tomllib.load(open('docs/research/EIGHT-STEPS.toml','rb'))
for n in ('audio','battery','charger','buttons'):
    e = d['hardware'][n]
    flags = ''.join('Y' if e['step'][k].get('done') else '.' for k in e['step'])
    print(n, e['status'], flags)
PY
```

## 13. EIGHT-STEPS 的 gpu/storage/display/bootchain 与 `porting.toml` 的交叉核对（2026-11-17，只报告）

同 §12 的方法，核对剩下四段；`porting.toml` 的 area 集合是
`configuration/firmware/cpu/memory/storage/display/input/gpu/network/audio/power/packaging/diagnostics/cellular`。

| # | 条目 | EIGHT-STEPS 记录 | porting.toml 记录 | 观察 | 建议 |
|---|---|---|---|---|---|
| 1 | storage | `status = "active"`，①–⑧ 全 done | `status = "implemented"`，但 `limits` 仍写 "Hardware inputs and implementation are pending for this board." | EIGHT ⑧ 已完成（K60DATA 三窗挂载），limits 却写成「待做」 | 只改 storage 的 `limits` 措辞 |
| 2 | gpu | `status = "active"`，①–⑦ done，⑧ false（gpu8-start 被 secure-IO 拒 -2，直连 RSC 版本未跑） | `status = "planned"`，`limits` 详细记录了两次尝试 | 状态词汇不一致：porting「planned」与已上机试过的记录不相称 | 建议确认后把 gpu 改成 `implemented`（仍未 device-verified）或加一句「已在推进」 |
| 3 | display | `status = "active"`，①–⑧ 全 done | `status = "implemented"`，`limits` 有 78,716 B 实测与下一步 | 一致 | 无需改 |
| 4 | bootchain | `status = "active"`，①–⑧ 全 done（launchd exec + pid 增长） | **没有 bootchain area**；相邻的 `firmware` 是 device-verified、`packaging` 是 host-verified | bootchain 的 ⑧ 完成在 porting.toml 里没有归属——设备状态权威记录看不到这条结论 | 建议把 bootchain 映射到 `firmware`，或在 `packaging` 加 findings；不改 EIGHT 的 status |

结论：2 处措辞（storage limits、gpu 状态词）与 1 处覆盖缺口（bootchain 无 area），display 一致。均只报告，未改任何 status。

**2026-11-17 已改 storage 的 `limits`/`next_action`**（改为已实现、剩余 Live Data occupancy）；gpu 的状态词与 bootchain 的归属未动，等 Lead 确认。

## 附录 A：复算命令

```bash
# 计数
grep -c '^### ★' docs/engineering/HARD-RULES.md        # ★ 条数（注意 29-31 缺号）
grep -c '^## P-'  docs/engineering/PITFALLS.md          # 坑条数
grep -c '^\[\[rule\]\]' docs/engineering/RULES.toml # 108（2026-11-17 起；审计时 107）
grep -vc '^#' patches/xnu/series                        # 227
ls patches/xnu/*.patch | wc -l                          # 268
# 引用完整性（WSL）
wsl -u root -e python3 /mnt/e/k60-work/scratch/refmine/doc-cite-scan.py
# 跨检出研究分布
wsl -u root -e python3 /mnt/e/k60-work/scratch/refmine/line-research-map2.py
# 死补丁
grep -n 'metal-seeds' patches/xnu/series || echo NOT-IN-SERIES
# patches/wifi 的读者
grep -rn 'patches/wifi' scripts/*.py scripts/*.sh
```
