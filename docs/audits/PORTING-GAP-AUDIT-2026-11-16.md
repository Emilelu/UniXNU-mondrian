# 移植疏漏审计：文档、调研与复用（2026-11-16）

> 本文是一件**审计**，不是新结论层：它记录"现有文档/调研哪里不准、缺什么、能抄谁"，
> 并把可以在文档层直接修的部分列成清单。基线：`origin/main` = `74c0d24e6c2b5be83b48c0fdcf459e708825be7c`（2026-11-16）。
>
> 范围：只读审计 + 本轮在 `docs/` 内落地的修补。未改 `drivers/`、`patches/`、`scripts/`、
> 门禁、水位与基线；未合 main。

## 0. 摘要：十条最要紧的

| # | 疏漏 | 证据 | 影响 |
|---|---|---|---|
| G1 | 三处入口文档仍把固件卷写成"同源同字节、现场两个卷、P-154 现状" | `README.md:134`、`docs/INDEX.md:52` 一带、`docs/engineering/README.md` | 与 main 上已改写的 `docs/engineering/FIRMWARE-REBUILD.md`（"它不是确定性的 / P-216 / P-154 已关闭"）直接矛盾 |
| G2 | `docs/ops/` 是 2026-11-12 从 yibiya 一次 pick 进来的上游快照，却在文件头自称"唯一权威" | `docs/ops/HARD-RULES.md:1-4`、上游 pick `97b84eb7` | 两份 HARD-RULES（★1–★37 vs HR-01–HR-12）、三份 PITFALLS（P-230 vs P-76 vs 148 行副本）编号空间互不相容 |
| G3 | 文档总入口自身过期且结构断裂 | `docs/INDEX.md:5`（日期、校验脚本名）、`:18-19`/`:52-53`（★35/P-130）、`:15`（3 列表只有 2 格）、`:121-122`、`:138` | 新接手的人按索引读，会先读到错数字 |
| G4 | 引用完整性没有任何门禁 | 2207 处仓库内路径引用中 **217 个目标不存在**（436 处）；**14 处行号越界** | 文档里的 `file:line` 是主要证据形式，坏引用等于证据失效 |
| G5 | 92 个研究文件只在各线分支上，main 只有 71 个，且没有"哪条线在哪"的映射 | 20 个并行检出实测（cellular 18、wifi 14、thermal 12、bt 10…） | 研究不可见 = 重复考古；`EIGHT-STEPS.toml` 已因此引用 7 个 main 上不存在的文件 |
| G6 | `EIGHT-STEPS.toml` 的 wifi 条目仍写"从未上机 / parked" | `docs/research/EIGHT-STEPS.toml:390-426` | 与 c1–c8 实飞、P-215 结案矛盾；这是唯一一处**门禁数据源**与事实相反 |
| G7 | 复用缺口不是"没有轮子"，是"抄了早期版本没跟上" | PongMetal 前端 109,178 B vs 参考 225,616 B；ShengUfs 参考 `9d527ae` 的 `VerifiedTableCache.h` 6,878 B、`RootPublication.h` 3,225 B 未进我们树 | 白写的量远大于没抄的量 |
| G8 | `patches/wifi/` 12 个补丁 229,326 B 在 main 上没有任何构建路径引用 | `grep -rn 'patches/wifi' scripts/*.py scripts/*.sh` 只命中测试断言；`patches/wifi/series` 无读者 | main 侧 WiFi 接线缺位；P-215 的补丁字节在 main，应用它的脚本只在 `feat/wifi-bringup` |
| G9 | **已退役的前身**没有退役登记：`patches/xnu/0610-k60-metal-seeds.patch`（4,364 B）不在 series | series `:218` 是 `0610-k60-metal-plugin-deploy.patch`；`scripts/tests/test-series-source.py:8` 称其 retired，`WIFI-REBUILD-CHECKLIST.md:99` 记为 wifi 线的等价实现 | 不是垃圾，但删之前要确认 wifi 线不再需要；只报告未动 |
| G10 | 三处"现在就该抄"的外部实现没进任何清单 | BT：新发现 `daimile2/renoir_xnu_bluethooth`（QCA6490 XNU，BSD-3-Clause，未考察）；音频：AW882xx 本地无副本（GPL-2.0 候选）；Metal：`pong-metal@0b3b34a` | 见 §7、§8 |

> 上表记的是**发现时**的状态。G1、G2、G3 与 G4 的「没有门禁」部分、G5 的「没有指针」部分已在本分支改掉；
> G6 已按 c1–c8 实飞重评（①–⑦ 记 done，`status` 仍保留 parked 并写明是门禁范围而非进度）；
> G4 的多数坏引用（含指向不存在 research 文件的 11 条已修）、G7–G10 只报告、未动。

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

| 位置 | 现在写的 | 实际 | 级别 |
|---|---|---|---|
| `README.md:134` | "固件卷重建手册：谁在构建、**为什么同源同字节**、现场**两个卷**、**P-154 现状**与重建实验协议" | main 的 `FIRMWARE-REBUILD.md` 已是"它不是确定性的（P-216）、现场四个卷、P-154 已关闭" | 【实测】 |
| `docs/engineering/README.md:24-25`、`docs/engineering/STATUS.md:341-342` | ★1–★35 / P-01–P-130 | ★1–★37（29/30/31 不存在）/ P-01–P-230 | 【实测】 |
| `docs/INDEX.md:18-19`、`:52-53` | 同上 | 同上 | 【实测】 |
| `docs/INDEX.md:5` | "最后更新 2026-11-12。本索引由 `check-doc-links.py` 校验" | 该脚本不存在；实际门禁是 `scripts/check-docs.py` | 【实测】 |
| `README.md:57` | 门禁"当前 84 条" | `docs/engineering/RULES.toml` 有 **107** 个 `[[rule]]` | 【实测】 |
| `AGENTS.md:188` | "`patches/xnu/` carries 245 patch files with 211 entries in `series`" | **268** 个 `.patch`、series **227** 条 | 【实测】 |
| `docs/engineering/STATUS.md:47` | "223 个补丁" | series 227 条（若指使能条数则口径未注明） | 【实测】 |
| `docs/engineering/STATUS.md:98` | "pong_metal=1 导致 backboardd 崩溃" | 同文件 `:393` 已声明该说法失效，`:396-406` 给出真因（插件缺 `Info.plist`/`.publish`/`.clients`/`PongMetalBridge.dylib`/`libvulkan_freedreno.dylib`） | 【实测】 |
| `README.md:50` | "本地构建脚本位于工作区（不在仓库内）" | `scripts/build-strict.sh` 等就在仓库里；工作区那份是构建副本 | 【实测】 |
| `README.md:138-140` | 三条项目符号插在文档表格中间 | 表格被截断，Markdown 渲染错位 | 【实测】 |
| `docs/INDEX.md:15` | REPO-MAP 行只有 2 个单元格 | 该表 3 列 | 【实测】 |
| `docs/INDEX.md:121-122` | `engineering/BATTERY-INTEGRATION.md`、`BOOT-ARGS.md` 列在 state/ 表 | 两者都在 `docs/engineering/` | 【实测】 |
| `docs/INDEX.md:138` | "series 224 vs 229" 的旧对照 | 当前 series 227，且 wifi 已按 P-215 结案 | 【实测】 |
| `docs/plans/GPU-TODO.md:81` | 旧崩溃归因 | 与 STATUS `:396-406` 冲突 | 【转述】 |
| `docs/plans/GPU-TODO.md:25` | 硬编码上游 SHA | ★37 禁止把 pin 写进进度文档（应由 catalog/水位持有） | 【转述】 |

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
**映射已建**：`docs/research/LINE-RESEARCH-MAP.md`（2026-11-17 重扫为 **16 个检出 / 97 个文件**，
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
| WiFi 接线 | `patches/wifi/` 0001–0012 = **229,326 B**，main 无读者【实测】 | 同补丁在 `feat/wifi-bringup` 由 `k60-wifi:scripts/build-k60-ath11k.py` 应用 | 分支独有 | **是**：把 applier + `k60_wifi_stage` 门搬进 main | 高（MHI/AMSS） |
| WiFi 源码 | patch 0001 冻结 `vendor-zizhan-087416a`（134,576 B） | `references/pong-wifi`：Platform **40,342**、Net **47,407**、Pci **6,010**、ath11k **7,248**【实测】 | 同源更新 | 是：替换 0001 的 vendor dump | 高 |
| UFS 根发布层 | `drivers/NativeUfs` 7 文件 ~82 KB | `references/ShengUfs@9d527ae`：`NativeUfs.cpp` **149,596**、`VerifiedTableCache.h` **6,878**、`RootPublication.h` **3,225** + tests【实测】 | 官方组件（catalog pin `99d8bcd` 无此层） | 是：VerifiedTableCache + RootPublication/RootWindowRead + 4 个测试 | **高**（根挂载，P-152/153） |
| Metal 测试 | — | `UniXNU/drivers/AdrenoMetal`：`OfflineMetalFrontend.mm` 75,688 等 5 个 | 官方组件 | 是：当回归网 | 低 |
| ADSP provider | `K60AdspOwnerStages` 只有契约 | `pong-power`：`PongPlatformResources.cpp` **4,230**、`PongPower.cpp` **1,970**、`PongAdsp.cpp` 33,318【实测前两个】 | 同源缺失 | 是：补 owner 的 ops | 高（卡音频/WiFi） |
| 音频传输 | `0503/0504/0505` 补丁，compile-only | `pong-power`：`ShengGpr.c` **4,165**、`ShengAudioReach.c` **17,656**、`PongAudioService.cpp` 7,421【实测前两个】 | 同源缺失 | 是：GPR + AudioReach opcode + service | 高 |
| BT 用户态 | `0500-k60-bt-qbt-new-files.patch` 156,632 B（内核侧） | `UniXNU/QcaBluetooth`：`tools/build-bluetool.py` 2,503、`build-type0.py` 2,941 + `userland/`【实测】 | 官方组件 | 是：userland + 构建脚本，24A446→20G81 | 中 |
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

## 8. 联网调研：已有结论与仍未知（G10）

### 8.1 已找到、可直接对照的

| 来源 | 许可证 | 价值 |
|---|---|---|
| `Chengdong-Yu/pong-wifi`（本地 `/e/hackios/pong-wifi`） | BSD-2-Clause-Patent | 同 SoC 同芯片板级层：GPIO 80/94/95/96/204、MSI SPI140→INTID172、PARF MSI0 bit23、TCS4 DRV2、GDSC `0x162128`、PCIe0 GDSCR `0x17b004`、SID `0x1c01`；其日志停在 102 MHI 通道后 RDDM |
| `Chengdong-Yu/pong-power`（本地 `/e/hackios/pong-power`） | BSD-2-Clause-Patent | PAS1 40 MiB carveout、SMEM `0x80900000+0x200000`、TCSR mutex3 `0x1f43000`、IPCC `0xed18000`/INTID261、AOSS `0xc300000`、Glink/Battmgr/AudioReach/GPR |
| `UniXNU/QcaBluetooth`（本地 `/e/hackios/QcaBluetooth`） | APSL/BSD | GENI UART + type-0 适配器的官方实现（userland + tools） |
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

### 8.3 本轮网络限制（写下来免得下轮重复踩）

`web_search` → HTTP 402（DeepSeek 余额不足）；`api.github.com` 前两次成功、之后 403 限速；
`raw.githubusercontent.com` 直取 `fetch failed`。所以 §8.1 里标"未考察"的四条只拿到仓库元数据
（名称/许可/描述），**没有读代码**。网络恢复后第一件事：读 `renoir_xnu_bluethooth` 的 BT 补丁与 type-0 适配器。

## 9. 机制修复建议（比逐条修更重要）

1. **引用门禁**：**已做（2026-11-17）** `scripts/check-doc-citations.py`（路径存在性 + 行号上限），由 `check-docs.py` 调起，
   欠账从 326 条降到 102 条、行号越界 0；剩余目标的分类见 §5，新增即 FAIL。
2. **数字不要手写**：★/P/RULES/series/patch 计数在 `check-readme.py` 已有实现，扩展到 INDEX、`docs/engineering/README.md`、`docs/engineering/STATUS.md`、`AGENTS.md`（同一段逻辑，多传几个文件）。**2026-11-17 已做**：range 校验覆盖上述四份文档（写了才校验、写错即红），并校验 AGENTS.md 的 `N patch files with M entries` 与 `patches/xnu` 实际 .patch 数、series 条数。
3. **研究可见性**：`docs/research/README.md` 改成"结论层索引 + 指向 INDEX 全量"；INDEX 的 research 段由脚本从目录生成，
   或至少加"未列出文件"小节（本轮先加了指针）。
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

## 10. 本轮已修 / 待 Lead 决定

**已修（本分支，两个提交）**：`docs(audit): add the porting gap audit` 只加本文；
`docs(hygiene): refresh stale numbers and mark the upstream ops snapshot` 含下面这串——
`docs/INDEX.md`（日期、脚本名、★/P、REPO-MAP 行、state 段、research 指针、本文链接）、
`README.md` / `README_EN.md`（84→107、固件描述、表格外项目符号、构建脚本位置）、
`docs/engineering/README.md` 与 `docs/engineering/STATUS.md`（★/P、223→227、pong_metal 矛盾标注）、
`AGENTS.md`（268/227）、`docs/ops/README.md`（新）+ 两份 ops 文件头横幅、
`docs/research/EIGHT-STEPS.toml` wifi 段的"已过期"注释、`docs/research/README.md` 指针；
后续轮次另加 `docs/engineering/PATCH-CATALOG.toml` + `check_catalog()`、以及 P-155 的 `expected_kern_exec_delta = 1713`（此前门禁空转）。

**待 Lead 决定（本文只报告，不动）**：

1. `EIGHT-STEPS.toml` 的 wifi/audio/charger 条目要不要按实飞重评（改 `done`/`status` 等于改放行条件）。
2. 92 个分支研究文件怎么回 main：整目录搬、还是结案时逐份搬（建议后者 + LINE-MAP）。
3. `docs/ops/` 三份上游文件：加横幅（已做）之外，要不要删除或移到 `docs/archive/upstream-ops/`。
4. `0610-k60-metal-seeds.patch`：**已做（2026-11-17）**。不删——它是退役前身（`test-series-source.py:8`），
   已登记进 `docs/engineering/PATCH-CATALOG.toml` 的 `status = "retired"`（evidence 3a8d61d8，replaced_by 0610-k60-metal-plugin-deploy）。
   同一目录还把另外 40 个 series 外补丁一并归类（9 retired / 3 renumbered / 29 library），并加了门禁。
5. `patches/wifi` 的 main 侧接线：把 `feat/wifi-bringup` 的 applier + 门搬过来，还是继续只在 wifi 分支构建。
6. §7 的 Top 8 抄写顺序（尤其 Metal 前端与 UFS 验证表——两者都对着已崩溃面）。

## 附录 A：复算命令

```bash
# 计数
grep -c '^### ★' docs/engineering/HARD-RULES.md        # ★ 条数（注意 29-31 缺号）
grep -c '^## P-'  docs/engineering/PITFALLS.md          # 坑条数
grep -c '^\[\[rule\]\]' docs/engineering/RULES.toml # 107
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
