# SA-UPSTREAM-REVIEW-20261112 — K60（mondrian / SM8475 / taro）上游待合入提交审计

审计对象：`yibiya/UniXNU-mondrian`（镜像 `E:\k60-work\references\yibiya-upstream`）、`UniXNU` 框架（`yibiya-unixnu-upstream`）、`uefi-mondrian`（`yibiya-uefi-upstream`）相对我们 pick 水位的新提交。
审计方式：只读。未执行 `git apply` / `checkout` / `commit` / `push`，未改动任何仓库状态（`E:\k60-work\.pick-upstream-seen.json` 的 sha256 在收集前后一致：`07A912B3…449177`）。本文件是本次审计唯一的写入。

## 0. 结论

- picker（`scripts/pick-upstream.py --plan`）报"新提交 104 个，其中需 pick 88 个"。88 条里 4 条是 `fix/boot-v4-repack` 分支与 `main` 的同一对象（`8e691d5d2` `2d6b86e05` `9c9d5f52e` `7b66697dd`），去重后 **84 个 sha**；另有 16 条纯文档提交按规则归 `not-applicable`。
- 判定分布：**10 条风险低 / 28 条需观察 / 46 条不可合**（共 84 条）。
- 真正能整文件安全落地的只有 **10 条"新增或等价"**（新补丁文件、新脚本、`mac-build/*.json` 报告，外加一条单行改动与一条 no-op）。84 条里没有第二条路径能"整文件覆盖"而上游不擦掉我们的东西：审计把"取完全部 84 条之后的终态"和"逐提交快照"分开算了，逐提交看 `series` / `board.toml` 会误判——它们是单文件快照，中间态回退、终态复原；真正留在终态的差集见 §3（153 个目标文件里 53 个仍与本地不同，其中 21 个**本地更大**，即我们的内容会被删）。
- 最危险的三个整文件：`patches/xnu/0340-k60-uilib-deploy.patch`（本地 1,052,856 B vs 上游 626,659 B，本地多 40.5%，里面是我们的 UI 库 blob；`4c796cd` 已经因为同样的操作回滚过一次）、`drivers/NativeUfs/RootCommands.h`（本地多 51.9%）、`patches/wifi/0003-drivers-PongWifi-k60-rsc-gate.patch`（本地多 44.2%）。
- 三个必答问题：A 否（`fix/touch-gpu-bringup` 已整条进 main、无独立增量，触摸链路仍缺 GENI GPI/DMA 与确认过的 pad role，作者自己也不声称端到端）；B 否（Metal 能编译但 `publish` 被写死 `'0'`，`0404` 不在 series，种子无人部署；两个 Adreno 文件本地已与上游终态逐字节相同）；C `fix/k60-input-adt` 已全量在我们的框架副本里，`fix/ufs-data-payload` 只剩 `payload.py` 一段没落地，而那段正好卡住我们的 Data 窗口构建；两者都不触及 3 窗口几何、SHNGROOT v1、`EFI PART@512` 与 0302 的 24 GiB 上限。

## 1. 审计口径

**范围**：每一条候选都做 `git -C <mirror> show --stat <sha>` + `git -C <mirror> show <sha>`，并对"pick 会写到哪个文件"逐个和本地工作树做字节比较（同尺寸不同内容也记为 DIFF）。判定只回答三问：

- **Q1** 是不是我们自己的文件（battery / audio / wifi），整文件 pick 会不会覆盖我们的工作；
- **Q2** 会不会破坏当前能开机的路线：`board.toml` 的 `archives` / `packages` / `kernel_args`、`patches/xnu/series` 的行序与行预算（P-155：早补丁动 `bsd/kern/kern_exec.c` 会让后面每个补丁的 hunk 位移）、3 窗口 NativeUfs 契约（OS / SystemOS / Data，SHNGROOT v1，Data 必须是 `EFI PART` 在 512 偏移的 GPT 盘）、子模块 pin 与 `-force_load` 归档（P-157：没人读的 CONFIG 是惰性的）；
- **Q3** 依赖是否随提交一起到：子模块 pin、Mu 补丁表、`force_load` 归档、没人读的配置符号。

**判定阈值**（写在最前面，避免逐条主观）：

- 只新增 / 与本地逐字节相同 → `风险低`；
- 存在本地文件、且本地体积比上游大 ≥10% → `不可合`（整文件覆盖即删我们的内容）；`porting.toml` 单文件提交同样 `不可合`（台账，按 hunk 合，否则 `cellular` 这类 area 会被整块删掉——P-151 的原样）；`board.toml` 里"本地更大"的提交也归 `不可合`（`kernel_args` 的 608 B 预算、`pong_metal=1`、`[kernel].archives` 都是逐项取舍，与百分比无关）；反过来，上游 `board.toml` **更大**的提交（`2994f1fd8` `2d6b86e05` `8e691d5d2` `83bb1181f` `81dd415e5` `7a91ff587`）是纯增块，归 `需观察`；
- 差异 <10%、只动 `series` / 补丁文件、或"台账 + 文档"一起动 → `需观察`（按 hunk 取；涉及构建的必须构建验证，纯文档的不影响构建但同样不能整取）；
- 删除 `series` 里我们仍需的补丁、引入我们无法解析的子模块、或把 `Data` 卷 UUID 改回会 panic 的值 → `不可合`（与体积无关）。

**一个必须说清的点**：picker 是整文件提取，而 `board.toml` / `patches/xnu/series` / `porting.toml` 是**单文件状态快照**。逐提交判"这一提交会不会弄坏"会得出"中间态坏了、终态好了"的错觉。所以本报告同时给两套结论：§2 是逐提交（回答"能不能这么取"），§3 是终态净差（回答"全部取完还剩什么"）。合入顺序按 §8 走，逐提交的中间态回退才不会变成一次真实构建。

## 2. 逐提交总表（84 条，已去重）

先记一笔"已经取过的"：`b6a0da6`（`feat(upstream): pick 3 commits…`）已经用 picker 取过 `9269d7728` `aec8dc3fb` `5ee976f53` 三条；紧接着 `4c796cd` 把 `9269d7728` 的 `0340` 整文件覆盖回滚了，回滚说明里写着"他的 626,395 B vs 我们的 1,052,856 B，12,438 行差异、9,500 行删除"，并留下判据"**缩水 40% 的补丁不是更新，是丢失**"。因为 pick 水位文件在本次审计里被复原成基线，这三条在 `--plan` 里还会再出现一次——取之前先看本表，`9269d7728` 的意图（壁纸恢复入口）至今仍未落到我们的 `0340` 上。

| # | sha | 日期 | 标题 | 判定 | 理由 |
|---|---|---|---|---|---|
| 1 | `0d757719b` | 2026-11-08 | docs(drivers): order the driver map per the requested sect… | **不可合** | 公共仓库根提交（无父）：595 文件整树导入，105 个与本地不同；RootTransportLayout.h 本地多 93.2%、series 只有 198 行、porting 退回 schema 1 |
| 2 | `3ace22d6d` | 2026-11-08 | fix(adt): publish the K60 touch panel maxima | **风险低** | scripts/make-pong-adt.py 单行；该文件终态与本地相同，pick 为 no-op |
| 3 | `77bb520b5` | 2026-11-08 | k60: freeze patch series; drop GPU scanout until archive l… | **需观察** | series 删 3 条 GPU 行（scanout/gpu-only/pitch）；我们 series:195-197 仍在用，只可加不可删 |
| 4 | `873ba9316` | 2026-11-08 | feat(kernel): embed the K60 init helper into the kernel im… | **不可合** | series 一次删 8 行（scanout/gpu-only/pitch/touch-console/goodix/keys…）+ porting 台账；删掉的我们都在用 |
| 5 | `955a58d20` | 2026-11-08 | fix(0391): mirror the proven 0340 vnode write block; add p… | **不可合** | LEDGER.md 本地多 54.1%；同提交里 0391 是全新补丁，只能摘补丁、文档跳过 |
| 6 | `be3673773` | 2026-11-08 | k60: touch/keys bring-up, GPU scanout rebase, 8-step resea… | **不可合** | 0340 本地多 40.3% + init.c 本地多 41.0% + series 重排：三处一起回退 |
| 7 | `03c7c3dc1` | 2026-11-09 | feat(reset): automatic return to fastboot verified on devi… | **需观察** | series +0334b-k60-autoreset 1 行；插入后须重核 P-155 的行号位移 |
| 8 | `0fd703c8a` | 2026-11-09 | fix(data): align Data volume UUID with the committed seed… | **不可合** | Data UUID 改回 6DCCF70A；本地注释记着这条会 K60DATA dataerr=2 (ENOENT) at kern_exec.c:8463 |
| 9 | `1285ccf0a` | 2026-11-09 | feat(display): 120Hz effective with BT and audio patches i… | **需观察** | series +8 行（0500/0501/0502/0502b/0503/0504/0505/0506）；行序敏感，加完必须构建 |
| 10 | `1605750dc` | 2026-11-09 | feat(patches): stage memory 8GiB and UFS concurrent patch… | **风险低** | 纯新增 patches/memory/8gib-*.patch 与 patches/ufs/concurrent-32slot.patch（+1,377 行），不进 series 即不参与构建 |
| 11 | `19faa19b7` | 2026-11-09 | fix(bt): add weak kernel stubs for armcpu_spi_* and native… | **风险低** | 纯新增 0502b-k60-bt-qbt-kernel-stubs.patch（27 行弱符号 stub），在 series 外 |
| 12 | `1e93ab89c` | 2026-11-09 | chore(repo): drop dangling NativeMetal submodule declarati… | **不可合** | 触摸补丁 本地多 32.9%（删 .gitmodules 那半对我们无影响）；净效果是回退 |
| 13 | `2c9eac9e8` | 2026-11-09 | fix(repro): make the public repo buildable - 8 patches fro… | **不可合** | board.toml(debug 0x144→0x140) + PongUfsTransport.cpp 本地多 37.4% + 触摸补丁：三处同时回退 |
| 14 | `6c1e1f165` | 2026-11-09 | k60(touch): embed Goodix GT9916 firmware extracted from th… | **需观察** | series +0403-k60-goodix-fw；按行插，注意后续补丁 hunk 位移 |
| 15 | `7da999e63` | 2026-11-09 | fix(input): three-part root-cause fix for keys/touch not r… | **不可合** | 触摸补丁 本地多 39.9% + series 重排：他要修的正是我们已自己实现的部分 |
| 16 | `7e13afd8c` | 2026-11-09 | fix(input): keys driver now runs - gate + PONG define + GP… | **不可合** | 触摸补丁 本地多 40.2% + physical-keys + series：同一批回退 |
| 17 | `807e0d933` | 2026-11-09 | fix(series): drop never-committed 0403 patch reference; ad… | **不可合** | HANDOFF.md 本地多 31.6% + series 摘 0403；文档不应进 pick |
| 18 | `9c325b7f5` | 2026-11-09 | fix(touch): gate the SE path behind k60_touch_se=1; DT ver… | **不可合** | 触摸补丁 本地多 39.1%：我们这版含 boot-option 握手与 NULL transport 防护 |
| 19 | `abd9eaaa0` | 2026-11-09 | feat(patches): stage BT/audio/120Hz patch sets (0500-0506)… | **不可合** | 0504 audio 补丁是我们的区（本地 29,471 vs 28,993），0500/0502 不同；只有 0503/0505/0506 已同 |
| 20 | `bbf83286b` | 2026-11-09 | fix(input): bump pong_buttons.c new-file hunk to 150 added… | **不可合** | physical-keys 补丁本地多 10.9%；hunk 计数修正对我们已生效 |
| 21 | `c3d5c63b5` | 2026-11-09 | feat(wifi): stage PongWifi final patch series (0001-0009)… | **不可合** | wifi 0003-rsc-gate 本地 2,181 B vs 1,216 B（本地多 44.2%）；wifi 是我们的区 |
| 22 | `da9d98d51` | 2026-11-09 | docs(touch): FDT pin truth, PMIC SPMI path, pitfalls P-63.… | **需观察** | RootTransportLayout.h 本地 3,129 vs 3,110 + 触摸补丁 5.2% + 文档；只按 hunk 合结构体 |
| 23 | `13f2f3eac` | 2026-11-10 | fix(os-window): repair resource forks zeroed by the window… | **风险低** | 纯新增 scripts/diagnostics/rf-repair-all.py 与 rf2-apply.sh，只读修复资源叉 |
| 24 | `212a12b42` | 2026-11-10 | fix(board): disable the bring-up watchdogs | **不可合** | board.toml：kernel_args selftest 300→0 并加 k60_autoreset=0；本地已有等价取舍且多 pong_metal=1 |
| 25 | `3aa279fca` | 2026-11-10 | fix(init): keep the job archive reader in step with the re… | **不可合** | init.c 本地多 18.1% + 0401 + 0330：init.c 同样只能取终态 |
| 26 | `47f33678a` | 2026-11-10 | fix(xnu): shared-cache root layout, console perms and boot… | **不可合** | 0398 本地多 22.7%（1,022 vs 819）：运行目录补丁我们条目更多 |
| 27 | `522c6ead7` | 2026-11-10 | fix(prelink): give launchd the helper it needs to reach th… | **不可合** | board.toml(applog_name=SpringBoard / k60_launchd_cache=1) + 0398 本地多 19.9% + init.c 本地多 15.4% |
| 28 | `53ef046a2` | 2026-11-10 | feat(data): 2 GiB Data window installer | **风险低** | 纯新增 scripts/data2g-install.sh 与 reshuangroot.py（2 GiB Data 盘方案，仅脚本，不碰内核） |
| 29 | `6295ab449` | 2026-11-10 | fix(data): bind the kernel to the 2 GiB seed volume UUID | **不可合** | Data UUID 绑到 2 GiB RAM 种子 E313398B；我们的 Data 是 21.3 GB UFS 窗口 |
| 30 | `640e02c44` | 2026-11-10 | fix(init): point dyld at the union-mounted shared cache | **不可合** | init.c 快照比本地小 39.3%；要的是终态那份（上游 27,712 B > 本地 24,689 B），不是这一版 |
| 31 | `69b7cfda5` | 2026-11-10 | feat(diagnostics): read the shared-region start address fo… | **需观察** | series +0400-k60-pid26-slide 及 0400 本体（2.1%）；按行插 |
| 32 | `7041358df` | 2026-11-10 | fix(diagnostics): compare whole resource forks, not only a… | **风险低** | 纯新增 rf3-repair.py / rf3-verify.py，整叉比对工具 |
| 33 | `792157f1f` | 2026-11-10 | build(drivers): restore the NativeMetal submodule at da7ae… | **不可合** | 新增 .gitmodules + drivers/NativeMetal gitlink(pin da7aedd)；我们无该子模块，目录不存在，离线无法解析 pin |
| 34 | `960081419` | 2026-11-10 | fix(data): repair zeroed resource-fork blocks from the pri… | **风险低** | 纯新增 scripts/repair-resource-forks.py（从原始 IPSW 修零块） |
| 35 | `97debfb95` | 2026-11-10 | feat(data): stream the 2 GiB seed into the resized window | **风险低** | 纯新增 scripts/data2g-stream.sh（把 2 GiB 种子流进窗口） |
| 36 | `b80924d93` | 2026-11-10 | feat(boot): ship the helper and the curated job set in the… | **不可合** | board.toml + init.c 本地多 22.3% + 0401 + series：一次取三处回退 |
| 37 | `c3d390ae6` | 2026-11-10 | fix(init): read the archive fields at their real offsets | **不可合** | init.c 本地多 16.8% + 0401 偏移修正；中间态快照，取终态即可 |
| 38 | `06fc98a1e` | 2026-11-11 | fix(boot): retain event publisher job contracts | **需观察** | userland/build.py +34（事件发布 job 契约）；同上，取终态 |
| 39 | `2917907d5` | 2026-11-11 | docs(boot): record Firehose and publisher evidence | **不可合** | 只写 porting.toml：整文件覆盖删本地 14 个 area（含 cellular），台账按 area 手合 |
| 40 | `5198a6799` | 2026-11-11 | fix(boot): restore selected event publishers | **风险低** | 0394-k60-launchd-cache.patch 与本地逐字节相同，pick 是 no-op |
| 41 | `6c4681169` | 2026-11-11 | docs(boot): record the current UI library cutover | **不可合** | 只写 porting.toml（UI 库切换记录）；按 area 摘，不整取 |
| 42 | `8839ef8a5` | 2026-11-11 | chore(build): record cand7 archive inputs | **需观察** | 只动 mac-build/*/build-report.json 生成物（本地多 5.4%）；对构建无影响 |
| 43 | `ac5481d76` | 2026-11-11 | fix(userland): rebuild the deployed UI blob | **需观察** | userland/build.py +58/−8；终态上游 34,590 B > 本地 30,078 B，取前核对本地增量 |
| 44 | `b8d6ab949` | 2026-11-11 | fix(boot): retain candidate userland preparation | **不可合** | 0340 本地多 40.3% + 0394 + init.c + series：一次取丢四处 |
| 45 | `c6e555c18` | 2026-11-11 | fix(userland): embed the rebuilt UI library | **不可合** | 0340 本地多 49.7%：整文件取即换成他那次 uilib 构建 |
| 46 | `f291b523e` | 2026-11-11 | fix(userland): defer SpringBoard preferences | **不可合** | ui_compat.c 本地多 15.5%：本地已含退回 SpringBoard 偏好的处理 |
| 47 | `04a819c4b` | 2026-11-12 | fix(touch,gpu): adopt the upstream handshake, config downl… | **不可合** | porting.toml 本地多 19.3% + init.c；证据条目按 area 摘，文件不整取 |
| 48 | `04bda86f2` | 2026-11-12 | fix(touch,power): land the handshake, config download and… | **需观察** | 电池 12 文件与本地逐字节相同（我们已是他更新后的状态），实质增量是 0602 + series 行 + 触摸补丁 260 行 |
| 49 | `0a5474b6d` | 2026-11-12 | docs(input): distinguish code inclusion from reports | **不可合** | 只写 porting.toml（代码包含 vs 报告的区别）；按 area 摘 |
| 50 | `0eb295a02` | 2026-11-12 | build(gpu): compile the iOS Metal stack on a Linux host | **不可合** | 对 drivers/PongPower/*（电池，我们的区）整文件覆盖 本地多 18.6%；金属构建脚本可单独摘，Power 目录不动（K60PmicGlink.h / LICENSE 连 04bda86f2 都不还原） |
| 51 | `1b097285c` | 2026-11-12 | docs(porting): record the adopted touch and GPU upstream f… | **不可合** | porting.toml 本地多 13.2% + userspace-inputs.json + 构建脚本；台账整取会删我们的 area |
| 52 | `1e0030e1e` | 2026-11-12 | docs(boot): record persistent Data loader conflict | **需观察** | porting.toml + PITFALLS.md（cand13/14 Data loader 冲突证据）；按 area 摘 |
| 53 | `208869cc5` | 2026-11-12 | chore(build): record actual Adreno flag input | **需观察** | 只动 mac-build/armdt-platform/build-report.json 生成物；无影响 |
| 54 | `25d621b2f` | 2026-11-12 | feat(gpu): start Adreno 730 and make the scanout gate read… | **需观察** | board 加 pong_adreno_start=1（board.toml:180 已有）+ porting 台账；只取台账与 series 说明 |
| 55 | `2994f1fd8` | 2026-11-12 | fix(input): supply actual K60 touch metadata | **需观察** | 加 [adt.arm-io.pong-touch.*] 六张表（spi 0x990000 / tlmm 0xf000000 / gcc 0x100000 / avdd-gpio 71 / max 14400×32000） |
| 56 | `2d6b86e05` | 2026-11-12 | fix(input): supply measured GPIO touch pin roles | **需观察** | 加 bitbang-pins（PERM 扫描唯一可用元组，驱动要求 bitbang_pins[3]==19）；按块搬进本地 board.toml |
| 57 | `3ba274688` | 2026-11-12 | docs(ui): record native gesture and wallpaper contracts | **需观察** | porting.toml + PITFALLS（手势与壁纸契约）；台账摘录 |
| 58 | `3fc388181` | 2026-11-12 | docs(debug): qualify selected native UI sink | **不可合** | 只写 porting.toml（原生 UI 控制台 sink 资质）；按 area 摘 |
| 59 | `4eb839519` | 2026-11-12 | fix(gpu): map only consumed GCC pages | **需观察** | PongAdrenoPlatform.cpp +33/−8（只映射消费页）；终态与本地相同，属 no-op |
| 60 | `5abea9af3` | 2026-11-12 | docs(boot): record unchanged-kernel recovery candidate | **不可合** | 只写 porting.toml（cand15 恢复记录）；按 area 摘 |
| 61 | `5d2d07e8e` | 2026-11-12 | docs(bringup): record desktop and real hardware | **不可合** | 只写 porting.toml（桌面与真实硬件 bring-up 记录）；按 area 摘 |
| 62 | `5ee976f53` | 2026-11-12 | docs(ui): record verified wallpaper recovery image | **不可合** | 只写 porting.toml（壁纸恢复镜像证据）；按 area 摘 |
| 63 | `61544e3f6` | 2026-11-12 | fix(gpu): link actual scanout and mailbox | **不可合** | 删 0392-k60-weak-scanout-stubs 并从 series 摘行；9f51b8b 证明我们的构建需要这些弱符号 |
| 64 | `6565837d3` | 2026-11-12 | fix(gpu): use monitor access for K60 RSC | **需观察** | PongAdrenoPlatform.cpp 改走 secure-IO monitor；defconfig 那半本地已是 y(:54)，别取 defconfig（会把 UUID 带回 E313398B） |
| 65 | `7a0f7b22a` | 2026-11-12 | fix(touch): use actual config staging buffer | **需观察** | 触摸补丁两行真修正（misc 偏移 24→18、回读失败取反）；手工搬进我们的补丁 |
| 66 | `7a91ff587` | 2026-11-12 | docs(input): qualify native gesture provenance | **需观察** | 只改 [adt.buttons.*] 注释两行；board 整取仍丢 pong_metal=1，按行改 |
| 67 | `7b66697dd` | 2026-11-12 | fix(input): publish all three PMIC keys | **不可合** | 0340 本地多 40.5%（本地 1,052,856 B vs 626,659 B）：里面是我们按 K60 触摸/HID 重建的 UI 库 blob |
| 68 | `7bb1fd297` | 2026-11-12 | fix(debug): expose bounded native UI console sink | **需观察** | series +0603-k60-ui-diagnostic（新补丁 1,319 B）；纯追加，行数 216→217 |
| 69 | `81dd415e5` | 2026-11-12 | fix(board): run the touch driver at its publishing stage | **需观察** | board kernel_args 删 applog 对、加 k60_touch_se=6（本地已有）；只并入 608 B 预算说明 |
| 70 | `83bb1181f` | 2026-11-12 | fix(input): select native no-home gesture policy | **需观察** | 加 [adt.buttons.*] home-button-type=2 + button-names；按块搬，board 不整取 |
| 71 | `8e691d5d2` | 2026-11-12 | fix(input): publish PMIC key arbiter node | **需观察** | 加 [adt.arm-io.pong-buttons.*]（0xc400000/0xc42d000/0xc440000、ee 0、ppid 19/397）；pong_buttons.c 精确匹配 |
| 72 | `9269d7728` | 2026-11-12 | fix(wallpaper): permit explicit native stock restore | **不可合** | 0340 本地多 40.5%：只改 blob 内壁纸恢复入口，代码 hunk 极小 |
| 73 | `97551c889` | 2026-11-12 | docs(porting): claim the in-progress power sources and the… | **不可合** | 只写 porting.toml（power 区声明 PongPower/*）；这条 area 声明本身我们已有 |
| 74 | `99abc1752` | 2026-11-12 | fix(wallpaper): select genuine stock via native API | **不可合** | 0340 本地多 40.6% + ui_compat.c：壁纸选择逻辑在我们的 blob 里 |
| 75 | `9c9d5f52e` | 2026-11-12 | fix(input): stop reporting volume keys from PON status | **需观察** | physical-keys 补丁在该时点比本地小 6.5%（本地 13,668 B 已含我们的 PON 修正）；只取 PON 不再报音量键那段 |
| 76 | `aec8dc3fb` | 2026-11-12 | docs(ui): record live native wallpaper guard | **不可合** | 只写 porting.toml（原生壁纸守卫实测）；按 area 摘 |
| 77 | `b1d07d37a` | 2026-11-12 | docs(boot): record v4 packaging regression | **需观察** | porting.toml + PITFALLS（v4 封装回归）；台账摘录 |
| 78 | `c80e0e1c9` | 2026-11-12 | fix(input): adapt real Goodix and HID to K60 | **不可合** | 0340 本地多 49.7%，同时换掉触摸补丁（本地多 3,255 B）；UI blob 与触摸两处都回退 |
| 79 | `d997c6b0f` | 2026-11-12 | fix(display): keep retained layers and blend them correctl… | **需观察** | 0600 补丁上游比本地多 512 B（本地 41,868 / 上游 42,380）+ series +1 + init.c；只取 0600 增量 hunk |
| 80 | `e7391cb02` | 2026-11-12 | fix(ui): keep initial native lockscreen locked | **不可合** | 0340 本地多 49.7% + ui_compat.c 本地多 15.5% |
| 81 | `e98c2908f` | 2026-11-12 | docs(touch): record actual config staging evidence | **不可合** | 只写 porting.toml（config staging 实测证据）；按 area 摘 |
| 82 | `ea885aaa0` | 2026-11-12 | docs(debug): record connected CDC capabilities | **不可合** | 只写 porting.toml（CDC 能力实测）；按 area 摘 |
| 83 | `f44574515` | 2026-11-12 | docs(input): record live transport and lockscreen state | **需观察** | porting.toml + PITFALLS（live transport / 锁屏）；台账摘录 |
| 84 | `ffb9fb70a` | 2026-11-12 | fix(bootimg): align v4 payloads after header page | **风险低** | 纯新增 scripts/repack-boot.py 与 test-repack-boot.py（v4 payload 按页对齐） |

## 3. 终态净差：取完 84 条之后仍与本地不同的文件

方法：以 `25d621b2f` 的树为终态，只比较 84 条提交实际碰过的 153 个文件，逐个和本地工作树做字节比较。`差 = 本地 − 上游`，**正数 = 本地更大 = 整文件 pick 会删掉这部分**（表按这一列从大到小排，最危险的在最上面）；负数表示本地还缺，pick 会补上。

| 状态 | 文件 | 上游 B | 本地 B | 差（本地 − 上游） |
|---|---|---|---|---|
| DIFF | `patches/xnu/0340-k60-uilib-deploy.patch` | 626659 | 1052856 | 本地多 426197 B（+40.5%） |
| DIFF | `drivers/NativeUfs/PongUfsTransport.cpp` | 30867 | 47569 | 本地多 16702 B（+35.1%） |
| DIFF | `patches/xnu/0401-k60-embedded-init.patch` | 1652005 | 1668068 | 本地多 16063 B（+1.0%） |
| DIFF | `drivers/NativeUfs/RootCommands.h` | 14500 | 30160 | 本地多 15660 B（+51.9%） |
| DIFF | `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` | 58849 | 62104 | 本地多 3255 B（+5.2%） |
| DIFF | `patches/wifi/README.md` | 4477 | 7040 | 本地多 2563 B（+36.4%） |
| DIFF | `dts/mondrian.dts` | 2364 | 3903 | 本地多 1539 B（+39.4%） |
| DIFF | `drivers/PongAdreno/PongAdrenoNativeGlue.cpp` | 2731 | 4155 | 本地多 1424 B（+34.3%） |
| DIFF | `drivers/PongMetal/PongMetalPlugin.mm` | 11351 | 12336 | 本地多 985 B（+8.0%） |
| DIFF | `patches/wifi/0003-drivers-PongWifi-k60-rsc-gate.patch` | 1216 | 2181 | 本地多 965 B（+44.2%） |
| DIFF | `patches/xnu/0500-k60-bt-qbt-new-files.patch` | 155670 | 156632 | 本地多 962 B（+0.6%） |
| DIFF | `porting.toml` | 40406 | 41269 | 本地多 863 B（+2.1%） |
| DIFF | `drivers/NativeUfs/RootQueue.h` | 2085 | 2581 | 本地多 496 B（+19.2%） |
| DIFF | `scripts/k60-macos-preflight.sh` | 2165 | 2585 | 本地多 420 B（+16.2%） |
| DIFF | `patches/xnu/0398-k60-pong-runtime-directories.patch` | 819 | 1022 | 本地多 203 B（+19.9%） |
| DIFF | `configs/mondrian_defconfig` | 2922 | 3042 | 本地多 120 B（+3.9%） |
| DIFF | `mac-build/armcpu/build-report.json` | 1575 | 1665 | 本地多 90 B（+5.4%） |
| DIFF | `mac-build/armdt-platform/build-report.json` | 1578 | 1655 | 本地多 77 B（+4.7%） |
| DIFF | `drivers/NativeUfs/RootTransportLayout.h` | 3110 | 3129 | 本地多 19 B（+0.6%） |
| DIFF | `mac-build/native-ufs/build-report.json` | 970 | 977 | 本地多 7 B（+0.7%） |
| DIFF | `patches/xnu/series` | 8158 | 8163 | 本地多 5 B（+0.1%） |
| DIFF | `mac-build/native-ufs/bindings.json` | 1251 | 1251 | 同尺寸不同字节 |
| DIFF | `patches/wifi/0001-drivers-PongWifi-vendor-zizhan-087416a.patch` | 134576 | 134576 | 同尺寸不同字节 |
| DIFF | `patches/xnu/0330-k60-entitlement-allow.patch` | 1884 | 1881 | 本地少 3 B（上游比本地多 0.2%） |
| DIFF | `userland/libmini/mini.h` | 6959 | 6933 | 本地少 26 B（上游比本地多 0.4%） |
| DIFF | `scripts/build-pong-metal-plugin.py` | 3172 | 3141 | 本地少 31 B（上游比本地多 1.0%） |
| DIFF | `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` | 13712 | 13668 | 本地少 44 B（上游比本地多 0.3%） |
| NEW | `.gitmodules` | 111 | 0 | 本地缺失（pick 会新增） |
| NEW | `userland/icons_cpu.h` | 156 | 0 | 本地缺失（pick 会新增） |
| DIFF | `scripts/emit_prelink_autoslide.py` | 5086 | 4838 | 本地少 248 B（上游比本地多 4.9%） |
| DIFF | `patches/xnu/0600-k60-display-composition.patch` | 42380 | 41868 | 本地少 512 B（上游比本地多 1.2%） |
| NEW | `drivers/PongMetal/build-patches/0001-mesa-build-tests-gate.patch` | 515 | 0 | 本地缺失（pick 会新增） |
| DIFF | `userland/ui_compat.c` | 49654 | 49128 | 本地少 526 B（上游比本地多 1.1%） |
| DIFF | `drivers/PongMetal/userspace-inputs.json` | 4155 | 3304 | 本地少 851 B（上游比本地多 20.5%） |
| DIFF | `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mem-report.patch` | 3465 | 2426 | 本地少 1039 B（上游比本地多 30.0%） |
| NEW | `patches/xnu/0603-k60-ui-diagnostic.patch` | 1319 | 0 | 本地缺失（pick 会新增） |
| DIFF | `docs/ops/PITFALLS.md` | 102016 | 100560 | 本地少 1456 B（上游比本地多 1.4%） |
| NEW | `pong-unixnu.patch` | 1818 | 0 | 本地缺失（pick 会新增） |
| DIFF | `scripts/build-xnu-4k-baseline.sh` | 70706 | 68365 | 本地少 2341 B（上游比本地多 3.3%） |
| NEW | `scripts/repair-resource-forks.py` | 2625 | 0 | 本地缺失（pick 会新增） |
| DIFF | `board.toml` | 14991 | 12116 | 本地少 2875 B（上游比本地多 19.2%） |
| DIFF | `userland/init.c` | 27712 | 24689 | 本地少 3023 B（上游比本地多 10.9%） |
| DIFF | `scripts/build-pong-userspace-linux.py` | 29596 | 26440 | 本地少 3156 B（上游比本地多 10.7%） |
| NEW | `scripts/test-repack-boot.py` | 3475 | 0 | 本地缺失（pick 会新增） |
| NEW | `scripts/repack-boot.py` | 3762 | 0 | 本地缺失（pick 会新增） |
| DIFF | `docs/plans/GPU-ENABLE-PLAN.md` | 51581 | 47368 | 本地少 4213 B（上游比本地多 8.2%） |
| DIFF | `userland/build.py` | 34590 | 30078 | 本地少 4512 B（上游比本地多 13.0%） |
| NEW | `scripts/gen-var-skel.py` | 6292 | 0 | 本地缺失（pick 会新增） |
| DIFF | `docs/state/LEDGER.md` | 24132 | 17494 | 本地少 6638 B（上游比本地多 27.5%） |
| NEW | `scripts/prepare-linux.py` | 6768 | 0 | 本地缺失（pick 会新增） |
| DIFF | `docs/INDEX.md` | 16940 | 9193 | 本地少 7747 B（上游比本地多 45.7%） |
| NEW | `pong-payload.patch` | 26262 | 0 | 本地缺失（pick 会新增） |
| NEW | `patches/xnu/0391-k60-embedded-init.patch` | 195794 | 0 | 本地缺失（pick 会新增） |

读法：**21 个文件本地更大**，合计约 0.49 MB 属于我们、会在整文件 pick 里消失；最集中的是 `0340`（本地多 426,197 B）、`PongUfsTransport.cpp`（+16,702 B）、`0401`（+16,063 B）、`RootCommands.h`（+15,660 B）、`pong-touch-console`（+3,255 B）、`patches/wifi/README.md`（+2,563 B）、`dts/mondrian.dts`（+1,539 B）、`PongAdrenoNativeGlue.cpp`（+1,424 B）、`0003-wifi-rsc-gate`（+965 B）。另有 `patches/wifi/0001…` 与 `mac-build/native-ufs/bindings.json` 尺寸相同但字节不同（本地改动，取的时候会被静默覆盖，不会体现在体积上）。

## 4. 分类明细（只展开非 `风险低` 的条目）

### 4.1 `0340-k60-uilib-deploy.patch` 的 UI blob（9 条，全部不可合）

`0340` 是本仓库里最大的单文件（1,052,856 B），它的主体是**内嵌的 `libpong-ui` 二进制 blob**（hex 行，行宽 <200 B，所以任何 diff 工具都只报"整段替换"）。上游这 9 条提交各自带一份自己的 blob（626,659 B 上下），差异不在代码，而在"哪一次 UI 库构建"。`4c796cd`（`revert: do not let a file-level pick erase our uilib work`）就是上一次整文件取它造成的事故记录；`9f51b8b` 之后我们又补过补丁头。

本地 blob 里含 `touch HID:`、`MTLDevice`、`volume key`、`IOHID` 一类符号，说明我们这份 UI 库是按 K60 的触摸/HID + Metal 发现链重建过的，不是上游那份。

| sha | 标题 | 目标文件 | 判定与判读 |
|---|---|---|---|
| `0d757719b` | docs(drivers): order the driver map per the requested sections | `.github/workflows/ios16-os-window.yml`；`.github/workflows/porting-record.yml`；`board.toml`；新增 `.gitmodules`、`pong-payload.patch`；等 105 个文件 | **不可合**：公共仓库根提交（无父）：595 文件整树导入，105 个与本地不同；RootTransportLayout.h 本地多 93.2%、series 只有 198 行、porting 退回 schema 1 |
| `be3673773` | k60: touch/keys bring-up, GPU scanout rebase, 8-step research… | `docs/INDEX.md`；`docs/state/LEDGER.md`；`mac-build/armcpu/build-report.json` （本地多 6.0%）；新增 `0391-k60-embedded-init.patch`；等 13 个文件 | **不可合**：0340 本地多 40.3% + init.c 本地多 41.0% + series 重排：三处一起回退 |
| `b8d6ab949` | fix(boot): retain candidate userland preparation | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 40.3%）；`patches/xnu/0394-k60-launchd-cache.patch` （本地多 0.9%）；`patches/xnu/series` （本地多 0.8%）；新增 `gen-var-skel.py`；等 4 个文件 | **不可合**：0340 本地多 40.3% + 0394 + init.c + series：一次取丢四处 |
| `c6e555c18` | fix(userland): embed the rebuilt UI library | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 49.7%） | **不可合**：0340 本地多 49.7%：整文件取即换成他那次 uilib 构建 |
| `7b66697dd` | fix(input): publish all three PMIC keys | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 40.5%）；`patches/xnu/0600-k60-display-composition.patch` （上游多 512 B）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` （上游多 44 B）；等 4 个文件 | **不可合**：0340 本地多 40.5%（本地 1,052,856 B vs 626,659 B）：里面是我们按 K60 触摸/HID 重建的 UI 库 blob |
| `9269d7728` | fix(wallpaper): permit explicit native stock restore | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 40.5%） | **不可合**：0340 本地多 40.5%：只改 blob 内壁纸恢复入口，代码 hunk 极小 |
| `99abc1752` | fix(wallpaper): select genuine stock via native API | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 40.6%）；`userland/ui_compat.c` （本地多 2.0%） | **不可合**：0340 本地多 40.6% + ui_compat.c：壁纸选择逻辑在我们的 blob 里 |
| `c80e0e1c9` | fix(input): adapt real Goodix and HID to K60 | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 49.7%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 24.3%） | **不可合**：0340 本地多 49.7%，同时换掉触摸补丁（本地多 3,255 B）；UI blob 与触摸两处都回退 |
| `e7391cb02` | fix(ui): keep initial native lockscreen locked | `patches/xnu/0340-k60-uilib-deploy.patch` （本地多 49.7%）；`userland/ui_compat.c` （本地多 16.5%） | **不可合**：0340 本地多 49.7% + ui_compat.c 本地多 15.5% |

要做的事：只从上游拿非 blob 的 hunk（`bsd/dev/k60_uilib.c`、`bsd/kern/kern_exec.c`、`bsd/conf/files` 三段），blob 段一律保留本地。上游若要合，必须把 blob 从补丁里拆出来单独发布（例如放 `payload/` 并在构建时组装），否则任何人做文件级同步都会互相擦除。

### 4.2 `board.toml`（11 条，全部不可合）

`board.toml` 也是单文件快照。上游终态 `14991 B` vs 本地 `12488 B`：他比我们多 `[adt.arm-io.pong-buttons.*]`（8e691d5d2）、`bitbang-pins`（2d6b86e05）、`[adt.buttons.*]`（83bb1181f），但他**没有** `pong_metal=1`——本地 `board.toml:180` 有。整文件取任意一条，`pong_metal=1` 与我们在 `kernel_args` 上的取舍都会一起消失，而 `kernel_args` 的 arm64 预算只有 608 B（81dd415e5 自己就是为这个删掉 `applog` 对的）。同时 `[kernel].archives` 含我们必需的 `ArmDTPlatform` / `ArmCpu` / `PongUfs`，覆盖即改开机路径。

| sha | 标题 | 目标文件 | 判定与判读 |
|---|---|---|---|
| `2c9eac9e8` | fix(repro): make the public repo buildable - 8 patches from is… | `board.toml` （本地多 7.6%）；`drivers/NativeUfs/PongUfsTransport.cpp` （本地多 35.1%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 37.4%）；等 4 个文件 | **不可合**：board.toml(debug 0x144→0x140) + PongUfsTransport.cpp 本地多 37.4% + 触摸补丁：三处同时回退 |
| `212a12b42` | fix(board): disable the bring-up watchdogs | `board.toml` （本地多 3.5%） | **不可合**：board.toml：kernel_args selftest 300→0 并加 k60_autoreset=0；本地已有等价取舍且多 pong_metal=1 |
| `522c6ead7` | fix(prelink): give launchd the helper it needs to reach the ma… | `board.toml` （本地多 3.5%）；`patches/xnu/0394-k60-launchd-cache.patch` （本地多 1.3%）；`0398-k60-pong-runtime-directories.patch` （本地多 19.9%）；等 5 个文件 | **不可合**：board.toml(applog_name=SpringBoard / k60_launchd_cache=1) + 0398 本地多 19.9% + init.c 本地多 15.4% |
| `b80924d93` | feat(boot): ship the helper and the curated job set in the ker… | `board.toml` （本地多 3.5%）；`patches/xnu/0401-k60-embedded-init.patch` （本地多 4.9%）；`patches/xnu/series` （本地多 1.3%）；新增 `prepare-linux.py`；等 4 个文件 | **不可合**：board.toml + init.c 本地多 22.3% + 0401 + series：一次取三处回退 |
| `25d621b2f` | feat(gpu): start Adreno 730 and make the scanout gate readable | `board.toml` （上游多 2503 B）；`docs/plans/GPU-ENABLE-PLAN.md` （上游多 4213 B）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-mem-report.patch` （上游多 1039 B）；等 4 个文件 | **需观察**：board 加 pong_adreno_start=1（board.toml:180 已有）+ porting 台账；只取台账与 series 说明 |
| `2994f1fd8` | fix(input): supply actual K60 touch metadata | `board.toml` （上游多 64 B） | **需观察**：加 [adt.arm-io.pong-touch.*] 六张表（spi 0x990000 / tlmm 0xf000000 / gcc 0x100000 / avdd-gpio 71 / max 14400×32000） |
| `2d6b86e05` | fix(input): supply measured GPIO touch pin roles | `board.toml` （上游多 2021 B） | **需观察**：加 bitbang-pins（PERM 扫描唯一可用元组，驱动要求 bitbang_pins[3]==19）；按块搬进本地 board.toml |
| `7a91ff587` | docs(input): qualify native gesture provenance | `board.toml` （上游多 944 B） | **需观察**：只改 [adt.buttons.*] 注释两行；board 整取仍丢 pong_metal=1，按行改 |
| `81dd415e5` | fix(board): run the touch driver at its publishing stage | `board.toml` （上游多 315 B）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 5.2%） | **需观察**：board kernel_args 删 applog 对、加 k60_touch_se=6（本地已有）；只并入 608 B 预算说明 |
| `83bb1181f` | fix(input): select native no-home gesture policy | `board.toml` （上游多 952 B）；`patches/xnu/0401-k60-embedded-init.patch` （本地多 1.0%） | **需观察**：加 [adt.buttons.*] home-button-type=2 + button-names；按块搬，board 不整取 |
| `8e691d5d2` | fix(input): publish PMIC key arbiter node | `board.toml` （上游多 1508 B） | **需观察**：加 [adt.arm-io.pong-buttons.*]（0xc400000/0xc42d000/0xc440000、ee 0、ppid 19/397）；pong_buttons.c 精确匹配 |

要做的事：按 hunk 手合，且只合这三块 ADT 新增 + `pong_adreno_start=1`；`kernel_args` 保持本地 28 项（含 `pong_metal=1`、`k60_touch_se=6`），合完重新数一遍字节数（≤608）。

### 4.3 `patches/xnu/series` 与补丁文件（含 GPU/display/battery 补丁）

`series` 是 216 行的有序清单，我们是 **216 行 / 8163 B**，上游终态 **216 行 / 8158 B**，差集恰好两行：上游多 `0603-k60-ui-diagnostic.patch`（7bb1fd297），我们多 `0392-k60-weak-scanout-stubs.patch`（第 209 行，`61544e3f6` 在上游删掉了它）。也就是说：**所有中间态的 series 提交都不需要照抄，只有这两行需要决策**。

`0603` 是纯新增（1,319 B，末尾追加），风险低。
`0392-k60-weak-scanout-stubs` 不能删：`9f51b8b`（`fix(build): restore the weak scanout stubs…`）证明删掉之后我们的构建缺符号——上游能删是因为它的 `PongAdreno` 归档在这些符号上齐全，我们的构建脚本没有走到那条归档链。`61544e3f6` 因此判 `不可合`。

补丁文件本身（`0340` 除外）多数是"我们版本更大"：`0398`（本地多 19.9%）、`0401`（本地多 1.0%）、`0600`（本地多 1.2%）、`pong-touch-console`（本地多 5.2%）、`pong-physical-keys`（本地多 0.3%）、`0500`（本地多 0.6%）。取上游等于把我们的 hunk 回退到他那版，必须逐补丁比对后只取增量。

| sha | 标题 | 目标文件 | 判定与判读 |
|---|---|---|---|
| `77bb520b5` | k60: freeze patch series; drop GPU scanout until archive link… | `patches/xnu/series` （本地多 9.7%） | **需观察**：series 删 3 条 GPU 行（scanout/gpu-only/pitch）；我们 series:195-197 仍在用，只可加不可删 |
| `873ba9316` | feat(kernel): embed the K60 init helper into the kernel image | `docs/state/BUILD-RECIPE-2026-11-08.md` （本地多 50.2%）；`patches/xnu/series` （本地多 11.8%）；`scripts/build-xnu-4k-baseline.sh` （本地多 11.3%）；新增 `0391-k60-embedded-init.patch` | **不可合**：series 一次删 8 行（scanout/gpu-only/pitch/touch-console/goodix/keys…）+ porting 台账；删掉的我们都在用 |
| `955a58d20` | fix(0391): mirror the proven 0340 vnode write block; add post-… | `docs/state/LEDGER.md` （本地多 54.1%）；新增 `0391-k60-embedded-init.patch` | **不可合**：LEDGER.md 本地多 54.1%；同提交里 0391 是全新补丁，只能摘补丁、文档跳过 |
| `03c7c3dc1` | feat(reset): automatic return to fastboot verified on device -… | `patches/xnu/series` （本地多 6.2%） | **需观察**：series +0334b-k60-autoreset 1 行；插入后须重核 P-155 的行号位移 |
| `1285ccf0a` | feat(display): 120Hz effective with BT and audio patches in th… | `patches/xnu/series` （本地多 3.1%） | **需观察**：series +8 行（0500/0501/0502/0502b/0503/0504/0505/0506）；行序敏感，加完必须构建 |
| `1e93ab89c` | chore(repo): drop dangling NativeMetal submodule declaration;… | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 32.9%） | **不可合**：触摸补丁 本地多 32.9%（删 .gitmodules 那半对我们无影响）；净效果是回退 |
| `6c1e1f165` | k60(touch): embed Goodix GT9916 firmware extracted from the de… | `patches/xnu/series` （本地多 9.4%） | **需观察**：series +0403-k60-goodix-fw；按行插，注意后续补丁 hunk 位移 |
| `7da999e63` | fix(input): three-part root-cause fix for keys/touch not runni… | `patches/xnu/series` （本地多 6.8%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 39.9%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` （本地多 10.9%）；等 4 个文件 | **不可合**：触摸补丁 本地多 39.9% + series 重排：他要修的正是我们已自己实现的部分 |
| `7e13afd8c` | fix(input): keys driver now runs - gate + PONG define + GPU-be… | `patches/xnu/series` （本地多 6.5%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 40.2%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` （本地多 10.1%） | **不可合**：触摸补丁 本地多 40.2% + physical-keys + series：同一批回退 |
| `807e0d933` | fix(series): drop never-committed 0403 patch reference; add op… | `docs/ops/HANDOFF.md` （本地多 31.6%）；`docs/ops/PITFALLS.md` （本地多 15.8%）；`patches/xnu/series` （本地多 3.4%）；等 4 个文件 | **不可合**：HANDOFF.md 本地多 31.6% + series 摘 0403；文档不应进 pick |
| `9c325b7f5` | fix(touch): gate the SE path behind k60_touch_se=1; DT verific… | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 39.1%） | **不可合**：触摸补丁 本地多 39.1%：我们这版含 boot-option 握手与 NULL transport 防护 |
| `abd9eaaa0` | feat(patches): stage BT/audio/120Hz patch sets (0500-0506) ver… | `patches/xnu/0500-k60-bt-qbt-new-files.patch` （本地多 0.6%）；`patches/xnu/0502-k60-bt-qbt-bsd-init.patch` （同尺寸不同字节）；`patches/xnu/0504-k60-audio-pong-audio.patch` （本地多 1.6%） | **不可合**：0504 audio 补丁是我们的区（本地 29,471 vs 28,993），0500/0502 不同；只有 0503/0505/0506 已同 |
| `bbf83286b` | fix(input): bump pong_buttons.c new-file hunk to 150 added lin… | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` （本地多 10.9%） | **不可合**：physical-keys 补丁本地多 10.9%；hunk 计数修正对我们已生效 |
| `c3d5c63b5` | feat(wifi): stage PongWifi final patch series (0001-0009) into… | `0001-drivers-PongWifi-vendor-zizhan-087416a.patch` （同尺寸不同字节）；`0003-drivers-PongWifi-k60-rsc-gate.patch` （本地多 44.2%）；`0007-configs-mondrian-wifi-defconfig.patch` （同尺寸不同字节）；等 4 个文件 | **不可合**：wifi 0003-rsc-gate 本地 2,181 B vs 1,216 B（本地多 44.2%）；wifi 是我们的区 |
| `da9d98d51` | docs(touch): FDT pin truth, PMIC SPMI path, pitfalls P-63..P-7… | `docs/ops/PITFALLS.md` （本地多 6.7%）；`drivers/NativeUfs/RootTransportLayout.h` （本地多 0.6%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 9.9%） | **需观察**：RootTransportLayout.h 本地 3,129 vs 3,110 + 触摸补丁 5.2% + 文档；只按 hunk 合结构体 |
| `3aa279fca` | fix(init): keep the job archive reader in step with the record… | `patches/xnu/0330-k60-entitlement-allow.patch` （上游多 3 B）；`patches/xnu/0401-k60-embedded-init.patch` （本地多 4.9%）；`userland/init.c` （本地多 18.1%）；等 4 个文件 | **不可合**：init.c 本地多 18.1% + 0401 + 0330：init.c 同样只能取终态 |
| `47f33678a` | fix(xnu): shared-cache root layout, console perms and boot-scr… | `configs/mondrian_defconfig` （本地多 8.4%）；`mac-build/armcpu/build-report.json` （本地多 8.2%）；`mac-build/armdt-platform/build-report.json` （本地多 7.1%）；等 9 个文件 | **不可合**：0398 本地多 22.7%（1,022 vs 819）：运行目录补丁我们条目更多 |
| `69b7cfda5` | feat(diagnostics): read the shared-region start address for pi… | `patches/xnu/0400-k60-pid26-slide.patch` （上游多 85 B）；`patches/xnu/series` （本地多 2.1%） | **需观察**：series +0400-k60-pid26-slide 及 0400 本体（2.1%）；按行插 |
| `c3d390ae6` | fix(init): read the archive fields at their real offsets | `patches/xnu/0401-k60-embedded-init.patch` （本地多 4.9%）；`userland/init.c` （本地多 16.8%） | **不可合**：init.c 本地多 16.8% + 0401 偏移修正；中间态快照，取终态即可 |
| `04bda86f2` | fix(touch,power): land the handshake, config download and batt… | `configs/mondrian_defconfig` （本地多 3.9%）；`patches/xnu/series` （本地多 0.4%）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 5.3%）；等 4 个文件 | **需观察**：电池 12 文件与本地逐字节相同（我们已是他更新后的状态），实质增量是 0602 + series 行 + 触摸补丁 260 行 |
| `0eb295a02` | build(gpu): compile the iOS Metal stack on a Linux host | `drivers/PongMetal/userspace-inputs.json`；`drivers/PongPower/K60BatteryConfig.c` （本地多 1.5%）；`drivers/PongPower/K60BatteryConfig.h` （本地多 18.6%）；新增 `0001-mesa-build-tests-gate.patch`；等 13 个文件 | **不可合**：对 drivers/PongPower/*（电池，我们的区）整文件覆盖 本地多 18.6%；金属构建脚本可单独摘，Power 目录不动（K60PmicGlink.h / LICENSE 连 04bda86f2 都不还原） |
| `61544e3f6` | fix(gpu): link actual scanout and mailbox | `patches/xnu/series` （本地多 1.2%） | **不可合**：删 0392-k60-weak-scanout-stubs 并从 series 摘行；9f51b8b 证明我们的构建需要这些弱符号 |
| `7a0f7b22a` | fix(touch): use actual config staging buffer | `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch` （本地多 5.2%） | **需观察**：触摸补丁两行真修正（misc 偏移 24→18、回读失败取反）；手工搬进我们的补丁 |
| `7bb1fd297` | fix(debug): expose bounded native UI console sink | `patches/xnu/series` （本地多 0.1%）；新增 `0603-k60-ui-diagnostic.patch` | **需观察**：series +0603-k60-ui-diagnostic（新补丁 1,319 B）；纯追加，行数 216→217 |
| `9c9d5f52e` | fix(input): stop reporting volume keys from PON status | `docs/ops/PITFALLS.md` （上游多 1456 B）；`zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch` （本地多 6.5%） | **需观察**：physical-keys 补丁在该时点比本地小 6.5%（本地 13,668 B 已含我们的 PON 修正）；只取 PON 不再报音量键那段 |
| `d997c6b0f` | fix(display): keep retained layers and blend them correctly | `patches/xnu/0401-k60-embedded-init.patch` （本地多 1.0%）；`patches/xnu/series` （本地多 0.8%）；`userland/init.c` （上游多 3023 B） | **需观察**：0600 补丁上游比本地多 512 B（本地 41,868 / 上游 42,380）+ series +1 + init.c；只取 0600 增量 hunk |

要做的事：只按单条 hunk 摘增量。`series` 只做两处编辑（加 `0603`、保留 `0392-k60-weak-scanout-stubs`），其余 series 提交都是快照，不要照抄。补丁文件用 `git -C yibiya-upstream show <sha> -- <file>` 看具体 hunk 再手搬。上游若要减少这种摩擦，得把 `series` 变成生成物（按目录扫描排序），而不是手维护的有序清单。

### 4.4 `porting.toml` 台账（11 条，全部不可合）

这些提交实质上只写台账（`porting.toml`），但 picker 按扩展名收（`.toml` 不在 `SKIP_PATHS`），于是会整文件覆盖。本地台账 41,269 B / 14 个 area（`configuration` … `diagnostics`、`cellular`），上游终态 40,406 B；差的不只是体积，而是我们在 `power` / `audio` / `storage` / `cellular` 上记录的状态与证据。P-151 说的"整文件 pick 删掉了我们的 `cellular` 块"就是这一类。

判定：`不可合`（作为文件级 pick）；价值在于证据条目，按 hunk 摘录即可，不影响构建。

| sha | 标题 | 目标文件 | 判定与判读 |
|---|---|---|---|
| `2917907d5` | docs(boot): record Firehose and publisher evidence | `porting.toml` （本地多 25.0%） | **不可合**：只写 porting.toml：整文件覆盖删本地 14 个 area（含 cellular），台账按 area 手合 |
| `6c4681169` | docs(boot): record the current UI library cutover | `porting.toml` （本地多 27.1%） | **不可合**：只写 porting.toml（UI 库切换记录）；按 area 摘，不整取 |
| `0a5474b6d` | docs(input): distinguish code inclusion from reports | `porting.toml` （本地多 6.4%） | **不可合**：只写 porting.toml（代码包含 vs 报告的区别）；按 area 摘 |
| `3fc388181` | docs(debug): qualify selected native UI sink | `porting.toml` （本地多 4.3%） | **不可合**：只写 porting.toml（原生 UI 控制台 sink 资质）；按 area 摘 |
| `5abea9af3` | docs(boot): record unchanged-kernel recovery candidate | `porting.toml` （本地多 6.3%） | **不可合**：只写 porting.toml（cand15 恢复记录）；按 area 摘 |
| `5d2d07e8e` | docs(bringup): record desktop and real hardware | `porting.toml` （本地多 19.8%） | **不可合**：只写 porting.toml（桌面与真实硬件 bring-up 记录）；按 area 摘 |
| `5ee976f53` | docs(ui): record verified wallpaper recovery image | `porting.toml` （本地多 3.3%） | **不可合**：只写 porting.toml（壁纸恢复镜像证据）；按 area 摘 |
| `97551c889` | docs(porting): claim the in-progress power sources and the GPU… | `porting.toml` （本地多 10.3%） | **不可合**：只写 porting.toml（power 区声明 PongPower/*）；这条 area 声明本身我们已有 |
| `aec8dc3fb` | docs(ui): record live native wallpaper guard | `porting.toml` （本地多 4.0%） | **不可合**：只写 porting.toml（原生壁纸守卫实测）；按 area 摘 |
| `e98c2908f` | docs(touch): record actual config staging evidence | `porting.toml` （本地多 5.5%） | **不可合**：只写 porting.toml（config staging 实测证据）；按 area 摘 |
| `ea885aaa0` | docs(debug): record connected CDC capabilities | `porting.toml` （本地多 5.7%） | **不可合**：只写 porting.toml（CDC 能力实测）；按 area 摘 |

要做的事：`porting.toml` 只按 area 摘证据到我们自己的对应 area（`input` / `gpu` / `storage` / `power`），一律不整文件取；`cellular` / `audio` 两个 area 连摘都不要摘（P-151 的原样）。上游若要合，需要把台账拆成按 area 的多文件（如 `porting/input.toml`），否则任何人的台账增量都无法用文件级工具搬运。

### 4.5 其余：会碰到真实代码/脚本/配置的条目

| sha | 标题 | 目标文件 | 判定与判读 |
|---|---|---|---|
| `0fd703c8a` | fix(data): align Data volume UUID with the committed seed and… | `configs/mondrian_defconfig` （本地多 8.4%）；`scripts/build-xnu-4k-baseline.sh` （本地多 0.9%） | **不可合**：Data UUID 改回 6DCCF70A；本地注释记着这条会 K60DATA dataerr=2 (ENOENT) at kern_exec.c:8463 |
| `6295ab449` | fix(data): bind the kernel to the 2 GiB seed volume UUID | `configs/mondrian_defconfig` （本地多 7.5%） | **不可合**：Data UUID 绑到 2 GiB RAM 种子 E313398B；我们的 Data 是 21.3 GB UFS 窗口 |
| `640e02c44` | fix(init): point dyld at the union-mounted shared cache | `userland/init.c` （本地多 39.3%） | **不可合**：init.c 快照比本地小 39.3%；要的是终态那份（上游 27,712 B > 本地 24,689 B），不是这一版 |
| `792157f1f` | build(drivers): restore the NativeMetal submodule at da7aedd | 新增 `.gitmodules` | **不可合**：新增 .gitmodules + drivers/NativeMetal gitlink(pin da7aedd)；我们无该子模块，目录不存在，离线无法解析 pin |
| `06fc98a1e` | fix(boot): retain event publisher job contracts | `userland/build.py` （上游多 4512 B） | **需观察**：userland/build.py +34（事件发布 job 契约）；同上，取终态 |
| `8839ef8a5` | chore(build): record cand7 archive inputs | `mac-build/armcpu/build-report.json` （本地多 5.4%）；`mac-build/armdt-platform/build-report.json` （本地多 4.7%）；`mac-build/native-ufs/build-report.json` （本地多 0.7%） | **需观察**：只动 mac-build/*/build-report.json 生成物（本地多 5.4%）；对构建无影响 |
| `ac5481d76` | fix(userland): rebuild the deployed UI blob | `userland/build.py` （上游多 2513 B） | **需观察**：userland/build.py +58/−8；终态上游 34,590 B > 本地 30,078 B，取前核对本地增量 |
| `f291b523e` | fix(userland): defer SpringBoard preferences | `userland/ui_compat.c` （本地多 15.5%）；新增 `icons_cpu.h` | **不可合**：ui_compat.c 本地多 15.5%：本地已含退回 SpringBoard 偏好的处理 |
| `04a819c4b` | fix(touch,gpu): adopt the upstream handshake, config download… | `porting.toml` （本地多 19.3%）；`userland/init.c` （上游多 2778 B） | **不可合**：porting.toml 本地多 19.3% + init.c；证据条目按 area 摘，文件不整取 |
| `1b097285c` | docs(porting): record the adopted touch and GPU upstream findi… | `drivers/PongMetal/userspace-inputs.json` （上游多 777 B）；`porting.toml` （本地多 13.2%）；`scripts/build-pong-userspace-linux.py` （上游多 1550 B） | **不可合**：porting.toml 本地多 13.2% + userspace-inputs.json + 构建脚本；台账整取会删我们的 area |
| `1e0030e1e` | docs(boot): record persistent Data loader conflict | `docs/ops/PITFALLS.md` （本地多 3.8%）；`porting.toml` （本地多 6.8%） | **需观察**：porting.toml + PITFALLS.md（cand13/14 Data loader 冲突证据）；按 area 摘 |
| `208869cc5` | chore(build): record actual Adreno flag input | `mac-build/armdt-platform/build-report.json` （本地多 4.7%） | **需观察**：只动 mac-build/armdt-platform/build-report.json 生成物；无影响 |
| `3ba274688` | docs(ui): record native gesture and wallpaper contracts | `docs/ops/PITFALLS.md` （本地多 0.4%）；`porting.toml` （本地多 4.6%） | **需观察**：porting.toml + PITFALLS（手势与壁纸契约）；台账摘录 |
| `4eb839519` | fix(gpu): map only consumed GCC pages | `drivers/PongAdreno/PongAdrenoPlatform.cpp` （本地多 3.6%） | **需观察**：PongAdrenoPlatform.cpp +33/−8（只映射消费页）；终态与本地相同，属 no-op |
| `6565837d3` | fix(gpu): use monitor access for K60 RSC | `configs/mondrian_defconfig` （本地多 7.5%）；`drivers/PongAdreno/PongAdrenoPlatform.cpp` （本地多 6.8%） | **需观察**：PongAdrenoPlatform.cpp 改走 secure-IO monitor；defconfig 那半本地已是 y(:54)，别取 defconfig（会把 UUID 带回 E313398B） |
| `b1d07d37a` | docs(boot): record v4 packaging regression | `docs/ops/PITFALLS.md` （本地多 5.1%）；`porting.toml` （本地多 8.0%） | **需观察**：porting.toml + PITFALLS（v4 封装回归）；台账摘录 |
| `f44574515` | docs(input): record live transport and lockscreen state | `docs/ops/PITFALLS.md` （本地多 1.7%）；`porting.toml` （本地多 5.5%） | **需观察**：porting.toml + PITFALLS（live transport / 锁屏）；台账摘录 |

要做的事：只取两类——`mac-build/*/build-report.json` 生成物（可直接覆盖，构建会重写）与 `userland/build.py` / `userland/init.c` 的终态文件（按 §8 第 4 步把本地改动重放上去）。`configs/mondrian_defconfig` 与 Data 相关脚本先看 §7 再决定：`0fd703c8a` / `6295ab449` 会改 Data UUID，`data2g-*.sh` 只服务 2 GiB RAM 种子路线，与我们的 19.87 GiB UFS 窗口不是一件事。

## 5. 问题 A：`fix/touch-gpu-bringup-20261112` 的触摸提交能不能把触摸打通

**结论：不能。整条链路代码形状齐了，但两处硬件资格没拿到，作者自己也没声称端到端。**

先把分支事实对齐（这会影响"要不要单独 pick 这个分支"）：镜像里没有 `fix/touch-gpu-bringup-20261112` 这个名字，实际分支是 **`fix/touch-gpu-bringup`（tip `81dd415`，2026-11-12）**，而且 `git log origin/main..origin/fix/touch-gpu-bringup` 为空——它已经通过 `ca208ba`（`merge: carry the verified 2026-11-12 bring-up onto main`）整条进了 `main`。所以**分支本身没有独立增量**，picker 在 main 上已经覆盖它。另外 `7a0f7b2`（`fix(touch): use actual config staging buffer`）**不在这个分支上**，它是合并之后落在 main 的：`branch -a --contains 7a0f7b2` 只有 `origin/main`。

这四条（`c80e0e1` 适配 Goodix/HID、`04bda86` 落地握手+配置下载+电池联动、`81dd415` 触摸在第 6 阶段发布、`7a0f7b2` 改用真正的 config staging 缓冲）确实把"协议层"补齐了：`7a0f7b2` 把 misc 偏移 18（`fw_buffer_addr`）与 24（`frame_data_addr`）分开，把 `0x1205c`/4200 B 的 staging 缓冲对上，并把回读失败从"假通过"改成"失败"——这是对的行为。但它自己的提交信息写着：

> `GPIO pad roles remain unqualified; no real contact or gesture is claimed.`

上游台账里的状态也是同一个结论：
- `04a819c4b`：`IF_DISABLE=1`（`GENI_IF_DISABLE_RO`，`se+0x064` bit0）意味 FIFO 接口不存在，必须走 GENI GPI/DMA；`next_action` 明确写"Implement the actual K60 GPI path (base 0x900000, EE offset 0x10000, TX0/RX1, SE4, SID 0x5b6)"。
- `1e0030e1e` / `f44574515`：cand15 的 live log 只走到 `SE4 protocol1/interfaces1`，FIFO 是 disabled，GPIO SPI 因为"没有 bitbang roles"起不来。
- `2d6b86e05` 的 `bitbang-pins="11000000120000001000000013000000"` 来自 24 组排列的硬件扫描，只有 PERM7/PERM8 读数为 `ff ff ff ff`，驱动要求 `bitbang_pins[3]==19` 才接受——这是**假设级**证据，不是"pad role 已确认"。

**还缺三样，且都不在这个分支里**：
1. GENI GPI/DMA 传输路径（分支里只有 FIFO/PIO 探测 + `GENI_DMA_MODE_EN` 的定义，没有真正的 GPI 角色协商）；
2. 确认过的 GPIO pad role 元组（现在只有 bitbang 候选）；
3. 框架侧必须把 `[adt.arm-io.pong-touch.*]` 真正写进 ADT——那是 `fix/k60-input-adt`（框架仓）的 `devicetree.py` 改动，见 §7；我们这边已经有（`E:\hackios\UniXNU\scripts\unixnu\devicetree.py:378-384`），所以他那边缺这条时 ADT 里根本没有 `/arm-io/pong-touch`。

另外，我们自己的触摸补丁（`…-pong-touch-console.patch`，62,104 B）比他的（58,849 B）大 5.2%，`f1b5280` 之后我们自己实现了握手、config 下载、NULL transport 防护。取他的分支会删掉这 3,255 B——所以 A 的答案对我们是"不取，只对照"。

## 6. 问题 B：GPU 提交是否真的把 Adreno 730 / Metal 打开

**结论：没有。GPU 侧只是"能起来、能编译、能读寄存器"，Metal 侧的发布被写死为 0，缺的是部署链而不是驱动。**

逐条看：
- `6565837 fix(gpu): use monitor access for K60 RSC`：把 RSC 读写改走 Qualcomm secure-IO monitor 服务（`PongAdrenoPlatform.cpp` +91/−30），并把 `configs/mondrian_defconfig` 的 `CONFIG_XNU_PONG_ADRENO_PLATFORM` 从 `n` 改成 `y`——本地 `configs/mondrian_defconfig:54` 已经是 `y`，所以配置那半是空操作。这是为了修 `04a819c4b` 记录的 `monitor secure-IO denies APSS RSC 0x17a2000c (return -2)`。
- `4eb8395 fix(gpu): map only consumed GCC pages`：把 GCC 映射从整页区间收窄到实际消费的页（+33/−8），是稳健性修复。
- `61544e3 fix(gpu): link actual scanout and mailbox`：补 `GEN7_GMU_GMU2HOST_INTR_CLR`/`_INFO`（`PongAdrenoRegisters.h`），并**删掉** `0392-k60-weak-scanout-stubs`——见 §4.3，这半条对我们不可合。
- `0eb295a build(gpu): compile the iOS Metal stack on a Linux host`：在 Linux 主机上编 Turnip 687/687、metal2vulkan 桥、`PongAdrenoMetal.bundle`，全部 arm64 Mach-O、NOUNDEFS。但同一提交把 `scripts/build-pong-metal-plugin.py` 里的种子从 `'1'` 改成 `'0'`，`build-report.json` 记 `publication_enabled=False`、`hardware_acceleration_confirmed=False`；提交信息原文：

> `Nothing was run on the device: the kernel still publishes no accelerator, the sealed cache is not extracted and publication stays 0.`

- `25d621b2f feat(gpu): start Adreno 730 and make the scanout gate readable`：只加 `pong_adreno_start=1`（阶段 A：把 GPU 起起来、报告每一阶段、**不做 framebuffer 交接**），`pong_gpu_scanout` / `pong_gpu_only` 明确留空，等 K60FB 行证明 framebuffer 在 VM 管理区之外。他的台账还记着"stage A never run on board since 2026-11-12"。

**为什么 Metal 仍然出不来**（三条硬依赖，缺一不可）：
1. `patches/xnu/0404-k60-metal-deploy.patch` 存在（7,978 B）但**不在** `patches/xnu/series`（216 行里没有 0404）。没有它，51 MB 的 `PongAdrenoMetal.bundle` 不会随 boot payload 的 FAT 卷（`/dev/md0`）落到 Data 上，`launchd` 之前那次拷贝不会发生。
2. `drivers/PongMetal/PongMetalPlugin.mm:193-200` 对每个客户端做两道闸：`PongAdrenoMetal.publish` 必须存在、regular file、`st_uid==0`、`(st_mode&022)==0`、首字节 `'1'`；`PongAdrenoMetal.clients` 同权限、逐行列进程名。种子不部署，插件对所有客户端都 `continue`——`0eb295a` 还把 publish 写成 `'0'`，等于自己关门。
3. `PongAdrenoAccelerator.cpp:44` 发布的 `MetalPluginName=PongAdrenoMetal` 只有在 bundle 已经在系统里时才解析得到；而 bundle 的落地又依赖 §8 那条 boot payload 路线——也就是 P-154 里"重建的 FD 找不到 boot entry"的重灾区。

所以 B 的答案是：这五条**没有一条能单独把 Metal 打开**，两条还是纯 staging。

一个硬证据：`git -C yibiya-upstream rev-parse 25d621b2f:drivers/PongAdreno/PongAdrenoPlatform.cpp` 与本地 `git hash-object` 同为 `73e82f2d75ec5076583f8f8e2fe4763f5043c842`；`PongAdrenoRegisters.h` 同为 `7412ceb8364d4f86fcb2b5ac3bcd659ef397f39a`。也就是说 `6565837` / `4eb8395` 的**文件内容我们已经有了**（逐字节比对为证，与哪次 pick 无关），再取只是把它们回退到提交当时那一版——所以两条判 `需观察`，实际操作是"不取，构建前确认本地仍是这份"。

取法建议：`6565837`/`4eb8395` 跳过（本地已是终态）；`25d621b2f` 只取台账与 series 注释（`pong_adreno_start=1` 本地 `board.toml:180` 已有）；`61544e3` 的寄存器两行可摘、series 删除不可合；`0eb295a` 只取 `drivers/PongMetal/build-patches/0001-mesa-build-tests-gate.patch` 与 `userspace-inputs.json` 增量，**不要**取它对 `PongPower/*` 的整文件覆盖。Metal 要真正开，需要上游补的是：`0404` 进 series + 种子由构建产物部署 + `publish` 写 `'1'`，三者一起。

## 7. 问题 C：`fix/k60-input-adt` 与 `fix/ufs-data-payload` 改了什么，与我们的 Data 窗口什么关系

**`fix/k60-input-adt`（2 个提交：`569b80e` 文档、`1e1a70e` 代码）**：`scripts/unixnu/devicetree.py` 增加"metadata-only 外设"通道——`platform.get('arm-io', {})` 里声明但没有 `reg` 映射的子节点，会被 `platform_node(name, table)` 塞进 `arm-io`，遇到与已导出硬件重名则 `raise Error('Configured arm-io child duplicates an exported hardware node')`。这就是让 `board.toml` 的 `[adt.arm-io.pong-touch.*]` / `[adt.arm-io.pong-buttons.*]` 能出现在 ADT 里的那一层。

**`fix/ufs-data-payload`（6 个提交）**：在上面两条之外再加 `182c0a2`（`U32`/`U64` 类型表补 `pong,smmu-*`、`pong,ufs-*`；CPU 节点补 `cpu-id`；`cpus` 补 `max_cpus`）、`5fba86d`（`payload.py` 的 Data 输入规则）、以及三条文档。

**与我们框架副本的实测对比**（`E:\hackios\UniXNU`，这是 picker 的第二个 target）：
- `scripts/unixnu/devicetree.py` 与分支 tip **逐字节相同**（0 行差异）——`fix/k60-input-adt` 与 `fix/ufs-data-payload` 的 ADT 部分**已经在我们树里**。
- `scripts/unixnu/payload.py` 是唯一落差：`check_data_input()` 仍是旧版（`"An owner-Data kernel needs a seed even when it resumes a persistent overlay."`）。分支版把规则反过来：

```python
if config.get('XNU_OWNER_DATA_UFS'):
    if data:
        raise Error('CONFIG_XNU_OWNER_DATA_UFS uses the installed Data volume; '
                    'omit --data-ramdisk to avoid attaching a conflicting RAM disk')
    return
```

这正好压在我们的痛点上：`configs/mondrian_defconfig:37,41` 同时是 `CONFIG_XNU_OWNER_DATA_MOUNT=y` 和 `CONFIG_XNU_OWNER_DATA_UFS=y`，而本地 `payload.py` 只看 `MOUNT`，于是任何"UFS-only"的 payload 构建要么被迫带一个 RAM Data 种子（cand13 的"Data loader conflict"），要么直接报 `requires --data-ramdisk`（cand14 卡在这里）。分支这条改动**不碰**窗口几何、SHNGROOT v1、`EFI PART@512`、也不改 0302 的 24 GiB 上限（`patches/xnu/0302-data-cap-execerr-kxp.patch:113,122,127` 的 `UINT64_C(0x600000000)`；我们的 Data 窗口 21,342,715,904 B = 19.87 GiB，离上限还有余量）——它只解决"要不要塞 RAM 种子"这一个决定。

**结论**：两个分支都与我们的 Data 窗口工作直接相关，但不是同一个问题域。`fix/k60-input-adt` 已经落地（无需再取）；`fix/ufs-data-payload` 只剩 `payload.py` 一段值得手工落下，而且**它不在 pick 计划里**——这两个分支在框架镜像的水位上，picker 不会报它们（"新提交 0 个"）。这是一个流程缺口：框架侧的修复永远不会被 picker 带进来。

## 8. 建议合入顺序

1. **先落手工项，不落 pick**：`E:\hackios\UniXNU\scripts\unixnu\payload.py` 按 `5fba86d` 的 `check_data_input()` 改写（UFS 分支 + 去掉 `MOUNT` 的强制种子）。这一步只影响 payload 组装，不碰内核；落完后把 cand13/14 的"Data loader conflict"从构建里摘掉，再谈 P-154。
2. **纯新增先取（10 条，风险低）**：`3ace22d6d`(make-pong-adt 面板最大值)、`19faa19b7`(0502b)、`1605750dc`(memory/ufs 补丁集)、`960081419`/`53ef046a2`/`13f2f3eac`/`7041358df`/`97debfb95`(Data/资源叉脚本)、`5198a6799`(0394 已同)、`ffb9fb70a`(v4 repack 脚本)。新补丁文件不进行 `series` 就不参与构建，属于惰性资产（P-157 的正向用法）。
3. **补丁增量按 hunk 取**：`d997c6b0f`(0600，本地多 1.2%)、`04bda86f2`(0602 + 触摸补丁 +5.3%)、`7bb1fd297`(0603 新文件)、`47f33678a`/`b8d6ab949`/`69b7cfda5`/`03c7c3dc1`/`1285ccf0a` 的 `series` 行——但要先决定 `0392-k60-weak-scanout-stubs` 留不留；留，就跳过 `61544e3`。
4. **`userland/init.c` 一次取终态，不要取中间快照**：`640e02c44` `3aa279fca` `c3d390ae6` `b80924d93` `522c6ead7` 在提交当时都比本地小 16%~39%（判 `不可合` 指"别取那一版"），但它们叠到最后，`25d621b2f` 的 `init.c` 是 **27,712 B，比本地 24,689 B 还大**——说明我们落后在他那条 init 线上。做法：以终态那份为底，把本地 `f1b5280` 之后的 dyld/union 改动重放上去，构建过 `0401-k60-embedded-init.patch` 的 hunk 计数（P-155）。
5. **GPU 阶段 A**：`6565837` / `4eb8395` 跳过（`PongAdrenoPlatform.cpp` 与 `PongAdrenoRegisters.h` 与上游 tip 逐字节相同），`25d621b2f` 只取台账与 series 说明。`0eb295a` 只取 `drivers/PongMetal/build-patches/0001-mesa-build-tests-gate.patch` 与 `userspace-inputs.json` 增量，跳过 `PongPower/*`。
6. **触摸只做对照**：`fix/touch-gpu-bringup` 已经整条进了 main（`ca208ba`），没有可单独 pick 的分支增量；拿 `c80e0e1` / `04bda86` / `7a0f7b2` 的 diff 当参考，只把 `7a0f7b2` 那两行（偏移 24→18、回读失败取反）搬进我们的补丁；我们自己的 `pong-touch-console` 已经多 3,255 B。
7. **永远不要**：整文件取 `0340`、`board.toml`、`porting.toml`、`series`；也不要取 `0fd703c8a` / `6295ab449`（Data UUID 回退到 `6DCCF70A` / `E313398B`，而本地注释记着这条会 `K60DATA dataerr=2 (ENOENT) at kern_exec.c:8463`）与 `792157f1f`（`drivers/NativeMetal` 子模块我们根本没有）。

## 附：not-applicable（16 条纯文档）与重复（4 条）

纯文档/CI（无 `.md/.txt/.rst/.github` 之外的文件）：`a2bb27aaa` `31eefaeff` `db94d5283` `a91fdf50c` `f09f36004` `dd2555818` `230046d7d` `2901026b5` `2b1120040` `9639e5d9d` `d29bce7e2` `c40738505` `74be7da32` `810eecb9e` `ca208ba5d`（merge，仅 1 个 md）`d855ce2d4`。

重复：`8e691d5d2` `2d6b86e05` `9c9d5f52e` `7b66697dd` 同时在 `fix/boot-v4-repack` 与 `main`，只取一次。
