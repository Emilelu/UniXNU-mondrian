# 18 · 离线验收前置条件与失败回执矩阵

> 依据：Lead 2026-11-16 16:44 与 19:32 +08:00 回复；逐项对应 [17 号清单](17-OFFLINE-ACCEPTANCE-CHECKLIST.md)。
> 本交仅准备文档，没有运行候选验收、故障注入、构建或上机，也没有访问 UEFI 工作区。
> 2026-11-16 19:32 Lead 交付框架候选（§2.1）；依赖框架实现的项从“未实现”改为“已具备，待整链候选”，
> 但候选实际执行状态仍为 **NOT RUN / null**。
> 基于清单提交 `72b6d29d843f268d7f811a591d2a3736cd941d10` 核对；下列均为**计划判据**。

## 1. 回执状态、退出码与阻断范围

本文的 `SOURCE_MISSING` 等 reason 是回执分类标签，不是现有工具的日志、已实现门禁或约定退出码。本轮只确认文档覆盖，不声称负例已经执行。

| 情况 | 回执 | 原始命令与退出码 | 后续处理 |
| --- | --- | --- | --- |
| 框架已交付但整链候选尚未产生，候选验收未启动 | NOT RUN | command_results 为空；exit_code=null；框架级子集回执单独存放，不填候选行 | 保留待验，不提前记 FAIL/BLOCKED |
| 验收启动后，必需来源、stage 或随机控制证据未交付/无法绑定到同次输入 | BLOCKED + 明确 reason | 未执行的命令仍为 null；已做的取证命令另留真实 rc | 只阻断依赖该证据的结论；独立只读检查可继续 |
| 可靠检查发现已交付内容不符合约定 | FAIL + 精确差异 | 每条命令各记真实 rc、stdout/stderr；检查器语义失败可 rc=1 | 仅判定被可靠证明不符的内容；依赖项 BLOCKED |
| 必需命令因工具缺失、权限、I/O、启动或进程终止而未可靠完成 | BLOCKED + `*_TOOL_FAILED`，保留执行错误 | 每条命令各记真实 rc、stdout/stderr/终止信息；未执行命令为 null | 不把执行环境错误推断成输入或框架内容损坏 |
| 命令 rc=0，但输出显示脏树、额外补丁、集合或哈希不符 | FAIL + 判据差异 | 仍如实保留 rc=0；这是内容判定失败 | 不伪造非零 rc，不把 rc=0 写成 PASS |
| 已交付内容明确声称包含某文件，实际检查发现文件缺失 | 对应内容检查 FAIL | 保存枚举/打开结果及真实 rc | 下游依赖项 BLOCKED；与“证据尚未交付”分开 |

每项沿用 17 号的绝对路径、产生 repo + 40 位 SHA、文件哈希/大小、cwd/env、argv、原始输出字段，并增加：

```text
check_id: 与17号一致，例如 ON-2
status: NOT RUN | BLOCKED | FAIL | PASS
reason: 本矩阵分类，允许同项多个原因
expected: 明确期望的来源、集合、值或字节
actual: 具体缺项/差异；不能只写“没通过”
missing_evidence: 证据绝对路径或尚未提供的字段
missing_paths / extra_paths: 相对 stage 根的精确路径列表
mismatches: 每项期望/实测的类型、大小、哈希或值
command_results: 每条独立列 argv、stdout_path、stderr_path、真实 exit_code
blocked_check_ids: 被阻断的检查ID；其它结果分别保留
acceptance_status: 当前候选 NOT RUN
exit_code: null
```

多条命令的 rc 分别保存，不用“最后一条成功”覆盖前面的失败。没有执行验收程序就不捏造总退出码。实际工具被信号终止时记录终止信息，不换成 0。负例将来要由已提交的隔离 harness 执行，产物不能进入上机队列；本交不增加 harness。

## 2. 输入账本覆盖（17 号 §1）

下表每行都要求输入绝对路径、产生 repo/SHA 或外部来源、文件身份、产生 argv/日志/真实 rc。字段未交付时 `SOURCE_MISSING`，所声明的身份与实测矛盾时 `SOURCE_MISMATCH`；按 §1 区分 BLOCKED 与 FAIL。

| 账本输入 | 缺失时的明确回执 | 不匹配时的明确回执 | 阻断的结论 |
| --- | --- | --- | --- |
| 框架基线与候选 | 两个独立 checkout、两个完整 SHA、提交/推送凭据或产生回执缺项 | rev-parse 与所报 SHA 不符，dirty 内容/归属未定，或产物仅用当前 HEAD 冒认来源 | PRE-1/4，OFF 与 ON 的版本归因 |
| 设备源码与隔离输入 | 实际设备输入快照、同步清单、SHA、env/argv 未提供 | 源码与输入全文件集合/哈希不同，ordered series 多/少/换序 | PRE-1/2/3/4；受影响产物来源 |
| strict 入口与独占输出 | K60_OUT、K60_DEVICE_INPUT、入口 SHA、原始日志、各步真实 rc 缺项 | 复用共享 out-baseline、跳 gates、输出绑定到另一轮构建，或失败被管道掩盖 | PRE-2/4；候选资格 |
| UEFI、EDK2、gitlinks、patches 与归档 FD | pin、补丁顺序/哈希、归属或 FD 产生回执缺项 | 归档 FD 与 pin/补丁产生链不符；gitlink 与已声明输入不同 | PRE-1/3/4、PKG-1/2/4；不清理他人工作区 |
| modem 原始输入与段表 | 提取来源、原始哈希、MDT、30 行表、生成器 SHA/回执缺项 | 字节或表统计不符，生成器实际选中的 .bin 与账本不是同一文件 | ON-1；缺原段时 ON-4D 内容比较 BLOCKED |
| LZMA 输入与打包工具 | 已提交打包工具、参数、长度改写、逐流来源回执缺项 | 压缩输入/输出哈希或长度、名字与账本不同；仅有 scratch 夹具 | PRE-3/4、ON-1/3/4/4D |
| kernel、DTB、配置与 series | 真实 .config、DTS/include、编译工具/命令、ordered series 来源缺项 | 字节、顺序、所选配置或 DTB 来源不符 | PRE-3/4、ON-6、PKG-1/2/3 |
| 可选依赖 | 未说明 trustcache/Data/GPU addon/root policies 是哪个输入或 N/A | 实际启用/禁用与所报选择不同，隐含默认路径带入另一份输入 | PRE-3/4；OFF 比较、ON 完整集合、PKG 来源 |
| OFF 两份样本 | 旧/新 payload、ADT、完整 stage 或随机控制绑定缺项 | 除框架版本外其它输入/工具/env 不同，受控前提下字节不同 | OFF-1/2/3/4；ON 不能补证 |
| ON 两次样本 | stage 删除前证据、payload.json、重复样本或随机控制绑定缺项 | 样本不属于相同候选/输入、阶段与卷不一致 | ON-2/5/7 与同次来源结论 |
| 已交付 boot | boot/boot.json/build-manifest、shim/FD/DTB/payload 的产生链缺项 | 关联哈希、真实内核或选中 entry 的 args 不符 | PKG-1/2/3/4；尺寸正确不补来源 |

外部固件的 Git SHA 可明确 N/A，但提取来源、原始哈希和打包工具 SHA 仍须齐全。独立取证目录必须是新建空目录；旧抽取结果、root 所有目标、mcopy 交互覆盖或非零 rc 属 `EXTRACTION_UNRELIABLE`，不能用留下的半份文件判 PASS。此项影响 OFF-4、ON-5/6 和 PKG 的回读。ON-2/5 的全 stage 期望全集须独立由同次所选配置、依赖开关和输入到生成输出的映射构造；若未交付该映射，stage 与 FAT 互比仅证明两者一致，不证明共同完整。

### 2.1 框架交付登记（2026-11-16 19:32，19:58 前移 pin）

Lead 交付的框架候选是 `UniXNU` fork 的 `feat/modem-carrier`，三个提交都已用 `git rev-parse` 在
`/mnt/e/hackios/UniXNU` 核对，祖先链是 `9198213` → `ecc15f9` → `92bb60f`：

| 提交 | 完整 40 位 SHA | 内容 |
| --- | --- | --- |
| 实现 | `91982136dc4a1b18633845ccb4a40d3778f4bba3` | `feat(payload): stage a modem carrier and publish its placeholder`：`scripts/unixnu/{devicetree,payload,cli}.py`、`scripts/tests/test_modem_carrier.py` |
| 文档 | `ecc15f974770625496965650f487a148333291db` | `docs(reference): document the modem carrier option and its payload fields`：`docs/reference/{cli.md,output-layout.md}` |
| 构建期名字检查（分支 HEAD） | `92bb60f74fff4ea9ca8562b8aa4241bdc77bd9cd` | `fix(payload): refuse modem carrier rows the firmware never opens`：`read_modem_carrier` 拒绝非 `modem.bNN` 行 |

接口：单一开关 `--modem-carrier DIR` / `UNIXNU_MODEM_CARRIER` / `[payload] modem_carrier`，schema 2
以外拒绝；同一变量同时产出 ADT 的 16 B 全零 `K60ModemImage` 与 `EFI/UniXNU/MODEM/` 的 27 个流，
拷贝发生在 utime/EPOCH 与 95% 容量检查之前，因此两者同现或同缺；`payload.json` 增加
`modem_carrier_files/_bytes/_compressed_bytes/_sha256/_placeholder` 五个字段，关闭时为 `null/null/null/null/false`
且 ADT 无该键；`bootimg` 不接受该选项。表行名必须是 `modem.bNN`：这是框架构建期强制，
不是建议——固件用 `L"%a.lzma"` 拼路径并先探 `modem.b01` 哨兵；`92bb60f` 起 `read_modem_carrier`
在读表时拒绝其它形状（如 `b01`）。

**覆盖范围**：只覆盖框架侧。设备侧打包脚本、内核/DTB/配置、UEFI pin 与补丁、严格隔离构建、真实上机
都不在该交付内。框架级离线子集已由 `k60-cellular/scripts/verify-modem-carrier.py` 在真实输入上
`ACCEPTANCE PASS 12/12`（rc 0，写 `acceptance.json`，pin `92bb60f74…`）。该次运行针对该 SHA 的
独立 `git clone`（HEAD 一致、dirty 0），因为共享工作区可能随时出现别人的未提交改动；工具会把载具
实现三文件的未提交改动当作不可信来源并以 rc 2 拒绝。同一工具在 `ecc15f974…`（名字检查之前）上得到
`ACCEPTANCE FAIL 11/12`，唯一失败项是「非 `modem.bNN` 行被拒」，证明负例确实在测名字守卫。但整条
`unixnu build payload` 与整链候选仍 **NOT RUN**；该子集不把本矩阵任何候选行改成 PASS。

**验收绑定规则**：整链验收必须绑干净的精确修订；共享 checkout 中途变脏会让回执失效——回执必须同时
记录 HEAD 与 dirty 清单，能证明被测的是那个 SHA，而不是「当时恰好有什么」的工作区。

## 3. 逐项缺失 / 不匹配矩阵

“缺证据”栏在验收开始后对应 BLOCKED；“实测失败”栏对应 FAIL，并保留具体差异。下游阻断遵循 §1。全部实际执行结果仍为 NOT RUN/null。

| check_id | 必需前置条件 | 缺证据的 reason 与回执内容 | 实测失败的 reason 与回执内容 | 阻断范围 |
| --- | --- | --- | --- | --- |
| PRE-1 | 账本全部 repo、40 位 SHA、clean/pin/patches/归属证据 | `SOURCE_MISSING`：逐 repo 列缺字段，不拿当前 HEAD 代替产物 SHA | `SOURCE_MISMATCH`：列 repo、所报/实测 SHA、dirty/gitlink/补丁差异；git rc=0 仍可判 FAIL | 对应输入的版本与来源结论 |
| PRE-2 | 独占输入/输出、strict 原始逐步回执、实际框架位置、同步全量集合 | `STRICT_RECEIPT_MISSING`：列 env/argv/log/rc 或隔离副本证据缺项；若固定检查目标不是隔离框架且尚无独立全文件比对，记 `FRAMEWORK_TARGET_UNBOUND` 并 BLOCKED | `INPUT_DRIFT`：仅在 copied drift/extra patch、共享 out、skip gates 或其它实际输入漂移被可靠证明时使用；strict 入口失败另记 `STRICT_EXECUTION_FAILED`。目标路径不同本身不证明漂移，须记录适用范围或比对结果；同步 rc=0 不抵消告警 | 严格候选资格及依赖的验收汇总；适用范围不明时不把独立检查误判为 FAIL |
| PRE-3 | 原始文件/配置/series 与工具版本、逐文件哈希/大小 | `INPUT_IDENTITY_UNBOUND`：列缺路径/来源/工具版本 | `INPUT_IDENTITY_MISMATCH`：逐文件所报/实测哈希、大小、series 顺序或版本 | 受影响的比较与来源结论 |
| PRE-4 | 同次 build-manifest、payload.json、boot.json 和产生链 | `BUILD_LINK_MISSING`：缺 build 身份、argv/env、输出哈希或真实 rc | `BUILD_LINK_MISMATCH`：列交叉引用不符/不同轮次/未记录默认输入；日志显示失败但汇总称成功也列出 | 同次来源结论；内容检查单独保留 |
| OFF-1 | 两份 OFF 输入只差框架实现；可审计随机控制与全部变量绑定 | `OFF_RANDOM_UNBOUND`：harness SHA、注入点/范围/调用次数/字节身份、两次运行绑定任一缺项 | `OFF_PREMISE_MISMATCH`：列控制字节/调用序列、工具/env/其它输入不同；不能归因为 modem 功能回归 | OFF-3 字节回归；OFF-2 结构可独立留证 |
| OFF-2 | 两份同次 OFF ADT、解析器 repo/SHA、可审计解析结果 | `OFF_ADT_EVIDENCE_MISSING`：缺任一 ADT 或解析器身份 | `OFF_ADT_MISMATCH`：解析失败、K60ModemImage 意外存在、其它属性增删/值不符；记录属性路径与原始长度/字节 | OFF 结构结论；OFF 组不合格 |
| OFF-3 | OFF-1 成立、两份删除前完整 stage、两份原始 payload | `OFF_STAGE_MISSING` 或 `OFF_RANDOM_UNBOUND`：列缺哪次阶段证据/随机绑定；前提不成立时逐字节回归结论 BLOCKED，不用 FAT 倒推；若已可靠枚举发现 MODEM 意外出现，仍独立记内容 FAIL | `OFF_BYTES_MISMATCH`：在前提成立时记录 MODEM 意外出现，或全路径/类型/大小/哈希/时间戳/枚举顺序、cmp 不同；若输入/工具/随机序列前提不一致，改记 `OFF_PREMISE_MISMATCH`，逐字节结论 BLOCKED；任何可靠观察到的内容错误仍保留 | OFF 逐字节结论；内容失败不被前提阻断抹掉，也不改旧文件 seed 取得假相等 |
| OFF-4 | 候选 OFF payload、payload.json、全清单及成功独立抽取 | `OFF_READBACK_UNBOUND`：缺选中 entry/内核/args/计数语义证据或只留半份抽取 | `OFF_CONTENT_MISMATCH`：实际内核/entry args/其它文件不同，或载具计数不是已声明的关闭状态 | OFF 回读结论；不能以 ON 代替 |
| ON-1 | byte-exact 原段、MDT、生成器 SHA、段表/manifest/打包来源 | `RAW_SOURCE_MISSING`：列缺原段/MDT/产生回执 | `TABLE_MISMATCH`：生成器可靠完成后发现非 30 段/27 文件段（文件名不是 b01–b13/b15–b20/b22–b29，连号即失败）、copied 非 109060761、bss 非 211012967，或所选原始文件身份不符；生成器未安装、权限/I/O/进程终止等另记 `TABLE_TOOL_FAILED`，保留真实 rc/错误并 BLOCKED，不据此称输入表损坏 | ON-3/4/4D 的表与内容身份结论 |
| ON-2 | 同次构建删除前全量 stage manifest/快照、导出回执与哈希 | `STAGE_EVIDENCE_MISSING`：仅 FAT、另一轮 stage、无删除前/同次绑定，或漏全量枚举信息；所选配置、依赖和开关绑定的**期望全集**未建立时另记 `STAGE_EXPECTED_SET_MISSING` 并 BLOCKED | `STAGE_CONTENT_MISMATCH`：期望全集已建立而全清单缺项/替换/重复、MODEM 非 27 个普通文件，或快照与清单不符；列 stage 实际与期望的 missing/extra/type/hash 差异。stage 与 FAT 共同漏项不能靠互相比较掩盖 | ON-5 阶段到卷的一致性、ON-7；卷内容可独立检查 |
| ON-3 | stage ADT/目录、ON-1 精确名字集合、解析器身份 | `ON_PAIR_EVIDENCE_MISSING`：缺一侧原始证据或 manifest | `ON_PAIR_MISMATCH` / `STREAM_SET_MISMATCH`：目录/ADT 只开一半、占位非唯一/非 16 B/非零/解析畸形、既有属性丢失，或缺项/额外项/名字替换；详见 §4/5 | ON 配对与集合结论；不得进入封装合格结论 |
| ON-4 | 同次流、可信 manifest、头部检查器 SHA/输出 | `HEADER_EVIDENCE_MISSING`：缺流或 manifest 的身份/原始检查日志 | `LZMA_HEADER_INVALID`：检查器可靠完成后发现短于 13 B、props 非 0x5D、UNKNOWN/>UINT32/声明长度不符、无数据，或 files/失败数/总声明长度不符；若工具未安装、权限/I/O/进程终止导致检查器未可靠完成，记 `HEADER_TOOL_FAILED`，内容结论 BLOCKED；列文件与实际字段/执行错误 | 相关流不合格；ON-4D 不能被“头合法”替代 |
| ON-4D | 全 27 流/原段映射、工具版本、逐文件独立解压与 cmp 回执 | `DECODE_EVIDENCE_MISSING`：少任一流的解码/比较回执、映射或所需哈希/长度；若 xz 已可靠拒绝损坏流，依赖的 cmp 和完整输出为 NOT RUN/null，不补造其 rc；原段缺失时仅内容等价结论 BLOCKED | `STREAM_DECODE_MISMATCH`：解码工具可靠读取输入后明确报告压缩数据损坏/截断/格式非法，或成功解码但长度/哈希/cmp 与原段不符，均为内容 FAIL；损坏流被 xz 可靠拒绝时不要求已有完整输出或执行依赖它的 cmp。若 xz 未安装、启动失败、权限/I/O、进程被终止或输出无法可靠保存，记 `DECODE_TOOL_FAILED`，内容结论 BLOCKED；记录实际 rc/stderr | 全 27 流完整性；不能写“26/26 即 27/27” |
| ON-5 | 同次 payload、独立 stage 期望全集、删除前完整 stage manifest 或快照及其回执、成功全量 FAT 抽取、payload.json | `STAGE_EVIDENCE_MISSING` / `STAGE_EXPECTED_SET_MISSING` / `VOLUME_READBACK_MISSING` / `PAYLOAD_REPORT_MISSING`：分别列缺同次删除前 manifest/快照、独立预期全集、可靠抽取或报告绑定 | `VOLUME_CONTENT_MISMATCH`：相对独立期望全集任一路径/类型/大小/哈希不同或额外项、payload 非 201326592 B、回读 ADT/流不合格；`PAYLOAD_REPORT_MISMATCH`：payload.json 缺 `modem_carrier_files`/`modem_carrier_sha256`/`payload_sha256`、计数非 27、必需值为空或报告字段与实测不符。完整原始 payload 文件 `payload_sha256` 可独立按 SHA-256 重算；载具聚合摘要需绑定算法、输入范围、排序/序列化规则与实现来源，缺此定义只阻断聚合摘要一致性，不阻断 payload 文件哈希核验 | 阶段到卷、ON 卷完整性、报告一致性及后续 PKG 对应输入 |
| ON-6 | 抽出真实 kernel/unixnu.toml、选中 entry、payload patch/seal 产生链 | `KERNEL_ARGS_UNBOUND`：缺真实内核/args 或来源回执，仅 header cmdline 不够 | `KERNEL_ARGS_MISMATCH`：内核哈希/entry 路径/args 不符，pong_modem=2 缺失或非恰一次，原有 args 门禁失败 | ON 实际内核/参数与 PKG-3 |
| ON-7 | 两个独立 ON 样本、全部输入 pin、受控随机与全阶段证据 | `REPEAT_PREMISE_MISSING`：缺第二次、随机绑定或任一次完整 stage；前提未成立时重复结论 BLOCKED | `CONTROLLED_REPEAT_MISMATCH`：仅当前提成立而 stage/payload 字节不同；样本输入、工具或随机序列不一致时记 `OFF_PREMISE_MISMATCH`/`REPEAT_PREMISE_MISSING`，重复结论 BLOCKED；已可靠观察到的单次内容错误仍分别保留 | ON 可复现性；其它单次检查分别保留 |
| PKG-1 | boot/manifest/shim/FD/DTB/payload 来源绑定，验证器与独立解包回执 | `PACKAGE_SOURCE_MISSING`：缺输入或同次来源，不拿当前 UEFI HEAD 补填 | `PACKAGE_CONTENT_MISMATCH`：验证器失败，v4/页值不符，gzip 解出 shim+FD、后附 DTB、ramdisk 任一字节不同 | 封装内容与来源结论 |
| PKG-2 | 可信 FD/payload、boot 头实测值及总大小 | `SIZE_EVIDENCE_MISSING`：缺输入身份、有效读取/解析回执或逐文件大小记录；boot 未交付或无法可靠读取时保持 BLOCKED | `PACKAGE_SIZE_MISMATCH`：解析器可靠完成后，FD 非 3145728、payload/ramdisk 非 201326592 或页数公式不符；已读取的 boot 头畸形/截断为 `PACKAGE_HEADER_INVALID`；解析工具执行层失败为 `PACKAGE_HEADER_TOOL_FAILED`，保留真实 rc/错误并 BLOCKED，不与内容错误混同 | 尺寸合格；尺寸符合不能覆盖 PKG-1/3 失败 |
| PKG-3 | boot 内真实内核与选中 entry args、board 输入及工具 SHA | `BOOT_ARGS_EVIDENCE_MISSING`：仅有 header cmdline，缺真实 entry/内核回读或来源 | `BOOT_ARGS_MISMATCH`：args 检查失败，内核哈希/参数与 ON-6 不同；逐项留 rc/差异 | 已封装镜像的实际内核/args 合格结论 |
| PKG-4 | 同次输入上表 A 七项、B 六项的独立原始回执 | `GATE_RECEIPT_MISSING`：逐项列 A/B 缺哪项；未交付/未允许检查 UEFI 时 B 单列 BLOCKED | `GATE_ITEM_FAILED`：明确 A1/A2/A2b/A3/A4/A6/A5、B1–B6 的失败项与实际 rc/输出；含 C 的整份脚本不能作离线全绿证明 | A/B 汇总；表 C 保持 NOT RUN |

## 4. 目录与 ADT 必须按声明配对

这里“目录在”指 stage 或 FAT 中确实存在 `EFI/UniXNU/MODEM/`；普通文件冒充目录也失败。“占位合格”指 ADT 可正确解析，目标属性唯一、恰好 16 B 全零，并保留其它既有映射。目录和 ADT 要分别检查，不能只看开关或 payload.json 计数。

| 声明 | 目录 | 占位 | 离线回执（ON-3 / OFF-2/3） | 固件语义边界（来自 16 号，不在本轮执行） |
| --- | --- | --- | --- | --- |
| OFF | 无 | 无 | 配对通过，仍须完成 OFF 其它项 | 目录不存在是合法跳过 |
| OFF | 无 | 有或畸形 | FAIL：OFF_ADT_MISMATCH；保留实际长度/值 | 目录先开，固件可跳过；不等于 OFF 字节回归通过 |
| OFF | 有 | 任意 | FAIL：OFF_BYTES_MISMATCH；意外目录/文件单列 | 固件发现目录后才会检查占位，离线不靠启动证明 |
| ON | 有且集合合格 | 合格 | 配对通过，仍须做头/解压/stage/卷/封装检查 | 配对本身不能证明成功装载 |
| ON | 有 | 无 | FAIL：ON_PAIR_MISMATCH，列缺属性路径 | 文档契约为 EFI_COMPROMISED_DATA，不自行上机重现 |
| ON | 无 | 合格 | FAIL：ON_PAIR_MISMATCH，列缺目录 | 固件可跳过，但声明 ON 没有载具，验收失败 |
| ON | 无 | 无 | FAIL：ON_PAIR_MISMATCH，注入与占位都没生效 | 合法跳过不能冒充 ON 已实现 |
| ON | 有或无 | 非 16 B/非零/重复/解析错误 | FAIL：ON_PAIR_MISMATCH，保留原始 ADT 与精确差异 | 鲜生成载具要求全零；历史 A5 允许范围值不替代此项 |
| 任意 | 任一侧（目录或 ADT）未能可靠读取 | 任一侧证据缺失/不可可靠读取：`ON_PAIR_EVIDENCE_MISSING` 或 `OFF_ADT_EVIDENCE_MISSING`，配对结论 BLOCKED；未交付目录证据与已可靠枚举确认目录不存在分别记录；已可靠观察到的另一侧仍单独记录，若已证明违反要求则保留对应 FAIL | 同左；可靠发现的缺失/额外/畸形内容仍按 ON_PAIR_MISMATCH、OFF_ADT_MISMATCH 等单独判 FAIL | 未取证不猜成“目录不存在”；不能因一侧 BLOCKED 抹掉另一侧的已知失败 |

## 5. 27 流精确集合与逐流内容

MODEM 期望集合 E 必须由已绑定原始输入的 manifest 生成：27 个唯一名字加 `.lzma`；名字集合是 `b01–b13, b15–b20, b22–b29`（第 14/21/30 行是纯 bss，无文件），任何 `b01..b27` 或 `b01..b30` 连号假设本身即失败。行名还必须是 `modem.bNN`：这是框架构建期强制
（固件拼 `L"%a.lzma"` 并先探 `modem.b01` 哨兵，`92bb60f` 起 `read_modem_carrier` 拒绝
其它形状），不是建议。全 stage 期望集合 S 则由同次所选配置、依赖开关及每个输入/生成输出映射独立生成，不能从实际 stage 或 FAT 反推；若实现没有可审计的预期清单，记 `STAGE_EXPECTED_SET_MISSING` 并 BLOCKED。实际 stage A 与 FAT B 分别对 S 校验，并做 A↔B 比对。MODEM 实际集合取目录**全部**子项，不能先过滤后数 27。回执同时列 `missing=expected-actual`、`extra=actual-expected` 和类型差异；manifest 自身重复名、非 27、条目长度不合法先在 ON-1 拒绝，不允许 set 去重掩盖。

| 情况 | 必须留下的失败回执 | 现有工具覆盖与边界 |
| --- | --- | --- |
| 缺一个/多个期望流 | STREAM_SET_MISMATCH，列每个缺失名字与声明长度；缺失内容为 FAIL | 头检查器会打印 missing，但仍须保存全目录集合 |
| 多一个流，或少一个又用别的名字补成 27 | STREAM_SET_MISMATCH，分别列 missing/extra；总数相等也失败 | 头检查器拒绝非 manifest 的普通 .lzma；不能只读 files=27 |
| 多 README、隐藏文件、子目录、符号链接或大小写碰撞 | STREAM_SET_MISMATCH，列路径/类型与冲突名；不得作为普通流接受 | 头检查器只额外枚举普通 .lzma；它的 rc=0 不证明目录无其它项，is_file 也可能跟随链接 |
| 头部非法/声明与表不同 | LZMA_HEADER_INVALID，列 13 B 头、props、声明/期望值、文件身份 | 头检查器已覆盖短头/props/UNKNOWN/UINT32/长度/无 payload；不证明能解压 |
| 头合法但流截断/损坏，或解出不同原段 | STREAM_DECODE_MISMATCH，逐流留 xz rc、stderr、解码长度/哈希、cmp rc、对应原段身份 | ON-4D 独立验证；头检查 rc=0 不补证 |
| 27 个都在但少一项解压/比较回执 | DECODE_EVIDENCE_MISSING，列缺哪个流、哪个命令/字段 | 内容等价结论 BLOCKED；历史 27/27、当前 26/26 均不能补齐 |
| 只留 27 流，漏 kernel/ADT/config/其它依赖，或 stage/FAT 中藏额外项 | 期望全集未由所选配置和输入映射独立建立时 BLOCKED / STAGE_EXPECTED_SET_MISSING；已建立后用 STAGE_CONTENT_MISMATCH / VOLUME_CONTENT_MISMATCH 列相对期望全集的 missing/extra/type/hash；另列 stage↔FAT 差异 | ON-2/5 分别核对每侧对独立期望全集，并互相比对；两边共同遗漏也会相对期望全集失败，MODEM 子目录通过不替代全量比较 |

现有头检查器的限制来自本分支 [check-modem-lzma.py](../../../scripts/check-modem-lzma.py)：它按 manifest 行数打印 files，成功行才累加 declared-total，并只将额外的普通 `.lzma` 计为失败；不额外强制 manifest 恰 27 行/唯一名，也不解压。故 ON-1/2/3/4D 与 ON-4 的判据分别保留。生成器/检查器/解压器未安装、权限/I/O 错误或进程终止时记录 `*_TOOL_FAILED`、原始 stderr/真实 rc/终止信息，依赖内容结论 BLOCKED；只有工具可靠完成并证明数据不同才归因于表或流损坏。上述 reason 是验收分类，不是脚本新增日志。

## 6. 重点缺证据的回执模板（未执行示例）

| 条件（假设未来验收已启动） | 失败/阻断回执应写什么 | 不能写什么 |
| --- | --- | --- |
| 只给 FAT，没有同次删除前 stage | ON-2 BLOCKED / STAGE_EVIDENCE_MISSING；缺 stage 绝对路径、导出 SHA/哈希/时点/同次绑定；ON-5 阶段比较与 ON-7 BLOCKED；独立卷检查另留结果 | “从 FAT 抽出 27 文件，所以 stage 通过” |
| OFF 给了 unique-chip-id/EPOCH，没给 harness 绑定 | OFF-1 BLOCKED / OFF_RANDOM_UNBOUND；逐项列缺 harness SHA、随机字节身份、注入范围/调用序列、两次运行绑定；OFF-3 BLOCKED | “两个正常随机构建哈希不同，所以 modem 回归”或“删 seed 后字节不变” |
| ON 有目录而 ADT 无占位 | ON-3 FAIL / ON_PAIR_MISMATCH；目录原始清单与 ADT 属性列表/原始字节、解析器真实 rc；验收分类不伪造 EFI 返回码 | 将计划的 EFI_COMPROMISED_DATA 写成已观察运行日志 |
| ON 有占位而目录无文件/目录缺失 | ON-3 FAIL / ON_PAIR_MISMATCH 或 STREAM_SET_MISMATCH；列空目录/缺目录与 missing 27 项，保留占位原始字节 | “固件允许跳过，所以 ON 合格” |
| 27 集合缺/多流 | ON-3 FAIL / STREAM_SET_MISMATCH；实际绝对目录、manifest 身份、missing/extra/type 列表、枚举/检查各真实 rc | “files=27，够数了” |

当前没有上述负例的执行回执；这里的样例没有填入任何假 argv 输出或非零退出码。候选交付后，执行到哪一步就填哪一步，不以文档矩阵覆盖未执行事实。

## 7. 覆盖与交付边界

覆盖账本 11 类输入，以及 17 号全部 20 个检查 ID：PRE-1–4、OFF-1–4、ON-1–7、ON-4D、PKG-1–4；另覆盖随机控制、stage 删除前证据、目录/ADT 的 OFF/ON 组合、精确文件集合、抽取可靠性与真实 rc。各项都列缺失与不匹配回执，依赖阻断不会消除已知失败。

完成项仅为矩阵准备与文档检查。等待 Lead 提供已提交框架基线/候选、匹配 UEFI pin/patches、隔离 strict 回执和完整 stage 证据后再启动五级验收。表 C 等同次真实 console.log；本交不排上机、不改框架/UEFI/他人 hunk，也不把历史夹具升级为候选。
