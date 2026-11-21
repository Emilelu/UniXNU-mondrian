# platform27 线内规则

> 这些规则是**长期**的，不是本轮指令。上下文被压缩后仍按这里执行。
> 由 Lead 裁决过、并带「记住」性质的条目在标题后面标 `〔Lead 裁决〕`。

## 1. 判据要盯行为，别盯字符串 〔Lead 裁决 m01381 ②〕

**教训实例（我自己写错的判据）**：复审 `check-io-map-budget.py` 时我用 `grep -c DEFAULT_SUBMAP` 判断「Lead 有没有修假绿」，得出「仍是 2 → 没修」。实测 `:28` 是定义、`:70` 仍然 `return DEFAULT_SUBMAP, "default"`，所以计数永远是 2；真正改的是 `:153-163` 那段「拿不到 `IO_MAP_SIZE` 就恒红」的门。字符串计数不是行为判据。

**规则**：

1. 判「某缺陷修没修」时，判据必须是一次**行为观测**：跑一遍、看退出码与输出行，而不是数源码里某个符号出现几次。源码里 `DEFAULT_SUBMAP` 即使被彻底绕过也可能留着定义与旧返回值。
2. 判据要能区分「改好了」与「改了别处」：至少一条正例 + 一条反例（例如 `#no-such-anchor` 必须 FAIL，正常锚点必须 OK），只跑正例等于没跑。
3. 判据写进文档时必须带上**命令 + 原始输出 + 日期**，让下一个人能重放；没有原始输出的结论按未验证处理。
4. 同类教训：`grep` 到一次就等于「存在」，不等于「被调用」——`psci_smp_start_fault.valid` 只有清零、`PSCI_SMP_CPU_IN_KERNEL` 只有定义没有写者，都是靠「谁写/谁读」两问才发现的（`docs/research/ios27/SMP-STEP-DECODE.md` §3）。

## 2. 门禁绿 ≠ 所有引用都验过 〔Lead 裁决 m01381〕

`check-lane-fragment.py:160` 用 `re.search` 只取**第一个** `official:` 引用，而 `:154` 的 `re.sub` 又把所有 `official:` 从路径扫描里剔掉，于是第 2..N 条既不机检也不报错——门禁对多引用是**静默的**（与 P-290 同族，Lead 判定为本轮最有价值的发现）。Lead 落 `re.finditer` 之前：

1. 我写的 fragment 里三条 `official:` 锚点只有第一条被机检，第 2、3 条在文档里注明「人工核过，等 `finditer` 落地」。
2. 任何「门禁通过」只能读成「已机检的那部分通过」，不能写成「全部通过」。汇报里区分「机检」与「手核」。
3. 看到门禁只报一个引用/一个文件的错时，先确认它是不是只看了第一个，再决定要不要继续查。

4. **表外新增窗口只靠行核对，不做集合差** 〔Lead 裁决 2026-11-21 ②，写进规则〕。预算表
   `docs/research/ios27/io-map-budget-27.toml` 只描述「表里有的行」；树里新冒出来的窗口不会
   自动进表，也不会自动让门禁红。这条边界是**故意**的，理由有两半：
   - 人可查：新增窗口只有两条出路——改这张表，或者在 review 时被看见。两条都在 git 里留下
     痕迹（diff 或对话），出问题时能追到人。
   - 换成集合差就要把 wrapper 名字写死进门禁（BT 的窗口尺寸经 `k60_map()` 的第三个实参传，
     `0500-k60-bt-qbt-new-files.patch:331`/`:336`），那是把实现细节焊进门禁——下次改 wrapper
     名，门禁不会再红，而是**静静地不再检查**，这就是给自己埋 P-280。
   代价写清楚：表漂移（旧行还在、数字变了）门禁能抓；「树里多了一个窗口、表没跟」只能靠行
   核对 + 人工。所以在 review 清单里固定一条：改 `ml_io_map` 调用点 → 同 PR 改表。

## 3. Report 通道：写文件 + 发消息，两个都要

1. `E:/k60-work/scratch/reply-platform27.md` 是双向通道：**先读**，保留 Lead 的段落（他的 `## Lead reply` 原文不改），只覆盖我自己那部分。
2. 首行必须是 `delivery: steer`（steer 成功）或 `delivery: followup, steer-rejected: <原文原因>`（steer 被拒改 followup）。缺这行 gates 的 `check-reply-freshness.py` 报红。
3. 结尾必须有 `## 请 Lead 给下一步`。
4. **只写 md 不算汇报**：每轮都要真的发 `send_agent_message`，先 `mode=steer`，被拒（`steer 仅用于 running 会话`）才 `followup`。

## 4. 只在自己分支上动

1. 工作树 `E:/hackios/k60-platform27`，分支 `feat/platform-27`；不并 main，不碰其他线的树。
2. `E:/hackios/k60-gates` 对本线**只读**：不改 `board.toml`、`patches/`、`scripts/`、`docs/engineering/{RULES,PITFALLS}.md`。发现门禁缺陷 → 写进 `docs/research/ios27/GATE-BUGS-27.md` 交回 Lead，不自己改。
3. 禁：任何构建（`unixnu build *`、`scripts/build-strict.sh`、`build-ios27-linux.sh`、FD/payload/boot.img）、任何 `fastboot` 与 adb 改动。
4. 提交：`git -c user.name=Emilelu -c user.email=kimiuso@vip.qq.com commit -q -F -`；一次提交只做一件事，代码与文档分开；英文祈使句 subject ≤50 字符。`git commit` 不带路径会提交整个索引（曾把 `git mv` 的重命名泄漏进别的提交）。

## 5. 证据规矩

1. 每条结论带 `file:line`；引用官方页带 `{#anchor}`（`porting/platform.md` 的 `#source-map` `:10`、`#clusters` `:41`、`#block-and-os-services` `:69`）。
2. 写「不知道」比写「大概」好：写 `unknown` + 什么证据能定它，不写「应该是/按经验」。
3. 数字要可重算：给出算式（例如 BT 五窗 `0x1F4200 + 0x4000 + 0x2000 + 0x100000 + 0x10000 = 3,187,200`），不写孤立的合计。
4. 一个窗口被多处映射时，按**调用点**计数（`K60PmicRail.c` 四条 → 静态最坏 393,216 B），不按物理区间去重，除非明确说明。

## 6. 本机环境陷阱（每次都会踩）

1. `ops_bash` 是 MSYS bash；`python3` 是 **Windows** CPython：程序里的 `/tmp/x` 会变成 `E:\tmp\x`，`/e/...` 无法解析。Python 里用 `E:/...`，`/e/...` 只作 bash 参数。
2. `tomllib.load` 需要**二进制**文件对象：`open(path, 'rb')`。
3. 走 `python3 - <<'PY'` 时非 ASCII 会被按 cp936 解码并抛 `SyntaxError: invalid character '：'`：脚本先写成 `.py` 文件再跑。
4. 写 `.patch` 必须 `open(..., 'wb')`，否则 Windows 把 `\n` 变 `\r\n`，`git apply` 明确拒绝上下文。
5. MSYS 的 `/tmp` 与 WSL 的 `/tmp` 不是一个目录；合成树必须在 WSL 里建。WSL 调用固定写：`MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /mnt/e/k60-work/scratch/platform27/<script>.sh`（脚本要落盘，`bash -lc` 里带 `\$` 的循环会被 MSYS 吃掉）。
6. 门禁必须在 WSL 里跑，MSYS 下 `/mnt/e/...` 会变成 `\mnt\e\...` 直接退 2（P-279）。
7. 需要 UTF-8 输出的 gate 加 `PYTHONIOENCODING=utf-8`，否则 `UnicodeEncodeError: 'gbk' codec`。

## 6.5 坑号（P-xx）只能由 Lead 分配

`E:/hackios/k60-gates/docs/engineering/PITFALL-IDS.md` 是唯一的坑号表，本线**不自占号**。发现新坑
的流程：把「现象 / 为什么它是坑 / 什么时候会静默通过 / 建议判据」写成一段，放进
`docs/research/ios27/GATE-BUGS-27.md`，在回复里请 Lead 给号；他给号之后才写 `P-xxx`。理由：坑号
是跨线共享的命名空间，两条线各自占号就会撞号，撞号比没号更难查。

## 7. 本线的事实基座（别再重新推导）

1. 27 的 `osfmk/arm/io_map.c` 没有 `IO_MAP_SIZE`/`io_submap`，每次 `ml_io_map` 走 `kmem_alloc(kernel_map, …)`（`io_map.c:112`）；16 系列 `0621` 的 8→32 MiB 在 27 上无对应物。门禁该走计数模式，见 `docs/research/ios27/IO-MAP-COUNT-MODE-PROPOSAL.md`。
2. 保留 `drivers/ArmCpu/ArmCpu.cpp` fork（三条硬缺口：catalog 的 `psciConduit` 读 `/psci` 而我们 ADT 无该节点、catalog 次核是 boot-arg 选择加入、catalog 无 sleep 而 PongPower 不在 27 archive），见 `docs/research/ios27/FORK-DECISION.md`。
3. `ml_arm_sleep` 是 XNU 原生（`osfmk/arm64/cpu.c:1024`），不是 fork 的发明；只有 `arm64_platform_sleep_hook` 需要补丁（`patches/xnu-12377/armcpu-sleep-hook.patch:13`）。
4. F1 = 1 核是口径（`scripts/make-pong-adt.py:74 --cpus 1`），`board.toml:210 cpus = 8` 是 16 线残留；0543 不写，等 8 核重评；镜像一落地立刻跑 `SMP-STEP-DECODE.md` §6.2 对账并回一行结论 + 产物路径。
5. ADT 单核锁在三处（`scripts/pong_adt_contract.py:158-163`、`:189`、`make-pong-adt.py:290-292`），多核提案在 `patches/proposed/9002-adt-multicore-topology.patch`，审过再进 series。

## 8. 共享 RAG 库与三档断言纪律 〔Lead 广播 2026-11-22〕

1. **先查库**：库根 `E:\k60-work\kb\kb.sqlite`（WSL `/mnt/e/k60-work/kb`，6,194 文档 / 142,260 块）。
   用法：`echo '{"kb_root":"/mnt/e/k60-work/kb","query":"…","top_k":4}' | python kb_engine.py search`。
2. **三档写法，不许混用**：
   - 官方文档 / 别人实现类断言 → **先查库**，命中就写 `文件:节`；
   - 库里没有 → 才联网，并附 URL；
   - 都没有 → 写「**未证**」，不许用「应该是/按经验」冒充。
   本线已有的例子：catalog `psciConduit` 读 `/psci` 这条是从源码读出来的（`ArmCpu-93a5030c.cpp:501-514`），
   不是从库或网上抄的；反过来，`FORK-DECISION.md` §1.1 的六棵参照树结论全部带 `file:line`，可直接入库比对。
3. **环境坑（查库时会踩）**：`NO_PROXY=localhost,127.0.0.1,::1` —— `::1` **不能带方括号**；
   `HF_ENDPOINT=https://hf-mirror.com`（嵌入模型走镜像，不然卡在下载）。
4. **P-300**：27 内核没有可靠的串口/日志通路，**0 字节日志不能解读成「内核没跑」**。
   这条已写进 `SMP-STEP-DECODE.md` §0 与 `F1-PLATFORM-HANDOFF.md` §3.5，判读表在「没读到日志」时只出
   「本次没有证据」，不出「全灭」。
5. **上机冻结令（2026-11-22 03:02，用户本人下达）**：`docs/engineering/BOOT-FREEZE.md` 的 `state = "frozen"`，
   `scripts/flash.sh` 在任何 `fastboot boot` 之前读它，只有用户本人改成 `lifted` 并写明理由与时间才放行；
   任何人不得用环境变量绕过（等同铁则 9）。解冻条件：同一次启动内的日志通路 + 自动引导 + 看门狗自动复位。
   本线本来就不上机，所以冻结期间**照常做离线件**，但不要设计「先飞一次看日志」的方案。
6. **P-307 / 通道四问**：ramoops 在 DRAM，掉电/复位即归零。任何「通道类」文档必须写清
   `lifetime` / `read_moment` / `writer` / `loss_condition` 四问，门禁 `scripts/check-channel-lifetime.py`
   会按一级标题切块、对同时出现通道词与判据词的块判缺项。本线的两份通道相关文档已补：
   `SMP-STEP-DECODE.md` §0、`F1-PLATFORM-HANDOFF.md` §3.5。
