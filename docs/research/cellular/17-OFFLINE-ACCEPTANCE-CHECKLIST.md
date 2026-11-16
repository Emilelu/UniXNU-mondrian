# 17 · 框架载具离线验收清单（框架已交付，待整链候选）

> 依据：Lead 2026-11-16 15:12 与 19:32 +08:00 回复；接口以 [16 号文档](16-FRAMEWORK-REQUEST.md) 为准。
> 本轮只准备/更新清单，没有构建、重新打包或上机，也没有检查或改动 UEFI 工作区。
> **框架已交付**：`UniXNU` fork `feat/modem-carrier`，`91982136dc4a1b18633845ccb4a40d3778f4bba3`
> （实现）+`ecc15f974770625496965650f487a148333291db`（文档，分支 HEAD）。但**整链候选尚未产生**，
> 下表候选验收项仍为 **NOT RUN**，不以历史表 A/B 或框架级子集代替。框架级子集已有可执行工具，
> 见 §5 的说明与真实回执。

## 1. 输入与来源账本

每项填写：输入绝对路径、产生它的仓库绝对路径与完整 40 位提交 SHA、文件 SHA-256、实际产生命令、输出日志与真实退出码。Git SHA 表示源码身份，SHA-256 表示文件身份，不能互换。外部固件无 Git 来源时填 N/A，另外记录提取来源、原始文件哈希和打包工具 repo/SHA。

| 输入 | 绝对路径 | 产生 repo + 40 位 SHA | 命令 / 输出 / rc | 状态 |
| --- | --- | --- | --- | --- |
| 框架候选及改动前基线 | 候选 `/mnt/e/hackios/UniXNU`；基线 checkout 待 Lead 指定 | 候选 `feat/modem-carrier`：`91982136dc4a1b18633845ccb4a40d3778f4bba3`（实现）+`ecc15f974770625496965650f487a148333291db`（文档，HEAD）；基线 SHA 待提供 | 候选侧 `git rev-parse` 与祖先关系已核（2026-11-16 19:32 报告）；基线产生回执待提供 | 已具备，待整链候选（基线待指定） |
| 设备源码与隔离输入 | 源码 `/mnt/e/hackios/k60-cellular`；构建输入由 Lead 确认 | 本清单准备前源码为 `f05158f0f3d6f101ee6b00349cc1dc673aa572c8`；未来实际设备输入另记 SHA/同步清单 | 同步检查的 env、argv、日志和 rc 待填 | NOT RUN |
| 严格构建入口与输出 | Lead 提供独占的 K60_OUT、K60_DEVICE_INPUT、产物目录绝对路径 | 入口脚本所属 repo + 完整 SHA | strict argv/env、起止时间、原始日志、build-manifest.json 与 rc | NOT RUN |
| UEFI 与补丁集 | Lead 提供归档 FD、UEFI pin、补丁与 gitlink 清单路径 | UEFI、EDK2、相关子模块各自完整 SHA | FD 产生命令、补丁顺序/哈希与真实 rc；本线不改工作区 | NOT RUN |
| modem 原始输入 | `/mnt/e/k60-work/firmware/modem` 仅为待确认位置 | 外部来源；段表生成器 repo + 完整 SHA | 原始段哈希、30 行表与 27 文件 manifest 的产生回执 | NOT RUN |
| LZMA 载具 | Lead 提供候选目录绝对路径 | 已提交打包工具 repo + 完整 SHA，不能只引用 scratch 夹具 | 压缩参数、8 B 长度改写、逐文件输入/输出哈希与 rc | NOT RUN |
| kernel / DTB / 配置 | Lead 提供 kernel、DTB、board.toml、defconfig、ordered series、实际 .config 路径 | 对应 repo + 完整 SHA；DTB 附 DTS/include 来源 | 各产生命令、版本、文件哈希与 rc | NOT RUN |
| 可选依赖 | trustcache、Data、GPU addon、root policies 路径或明确 N/A | 对应 repo/SHA，或外部来源与哈希 | 实际选择值及回执，不能依赖未记录默认值 | NOT RUN |
| OFF 基线与 OFF 候选 | 两份 payload、ADT、完整 stage manifest 路径 | 各自框架 SHA，其它输入完全相同 | 原始构建日志、随机控制方式、工具版本与 rc | NOT RUN |
| ON 候选及重复样本 | 两次独立输出的 payload、ADT、完整 stage manifest、payload.json 路径 | 同一候选与全部输入 pin | 阶段保留方式、产生回执和 rc | NOT RUN |
| 已交付 boot | boot.img、boot.json、build-manifest.json 绝对路径 | 同一严格构建关联的全部 repo/SHA | 打包 argv、FD/DTB/payload 哈希、实际内核/args 回读 | NOT RUN |

不能把当前 checkout 的 HEAD 直接当已有产物的产生 SHA。dirty diff、未提交 gitlink、补丁归属与构建输入快照都必须查清；归属未定即待验，不提交或清理别人的改动。

本轮只读观察（2026-11-16 19:32 后）：`/mnt/e/hackios/UniXNU` 在 `feat/modem-carrier`，HEAD
`ecc15f974770625496965650f487a148333291db`；工作区仍有他人未提交改动（`drivers/DarwinBoot`、
`pong-driver/` 下若干文件、`scripts/unixnu/firmware.py`，未跟踪 `scripts/test-devicetree-handoff.py`），
这些都不在载具实现三文件（`scripts/unixnu/{devicetree,payload,cli}.py`）内，但整链候选必须另取干净
checkout。此前观察到的 HEAD `54f641fa…` 已过期。设备源码仍为 f05158f，工作区干净。此观察不证明任何
已有镜像来自这些 HEAD。

## 2. 每项的回执格式与退出码

每项单独记录下列字段；未执行的退出码为 null，不能填 0。

```text
id: PRE-1 / OFF-1 / ON-1 / PKG-1
status: NOT RUN | PASS | FAIL | BLOCKED
input_absolute_paths: 待填，每个输入分别列明
producer_repositories_and_40char_commits: 待填
input_sha256_and_sizes: 待填
cwd_and_environment: 待填，含 K60_OUT / K60_DEVICE_INPUT
command_argv: 待填，保留独立参数边界
stdout_path / stderr_path: 独立持久证据目录内的绝对路径
exit_code: null
expected_output: 使用下表判据
actual_output: 未执行
```

下表命令以 argv 模板表示，每个逗号分隔项是独立参数；执行前把路径别名换成第 1 节确认的绝对路径。不得把模板直接拼成 shell 字符串。先执行命令，立即保存其退出码，再检查输出；依赖步骤只在前置检查成功后执行。

禁止 `cmd | tail; echo $?` 这种回执。若必须管道，启用 pipefail，并在任何后续命令前保存全部 PIPESTATUS；优先将每条命令独立执行、分别记日志和 rc。mcopy 抽取使用新建且唯一的空目录，输入文件只读，避免 root 所有的旧目标与交互覆盖。

## 3. 共用前置检查

| ID | 输入与来源 | 命令 argv / 检查 | 预期输出与 rc | 实际输出 / rc |
| --- | --- | --- | --- | --- |
| PRE-1 | 账本中每个 repo 绝对路径及完整 SHA | `[git, -C, REPO, rev-parse, HEAD]`；`[git, -C, REPO, status, --porcelain]`；子模块另查 status 与 pin/patches | SHA 等于账本、源码干净、gitlink/补丁可追溯；各 rc 0 | NOT RUN / null |
| PRE-2 | 设备 repo、隔离输入、独占输出；入口 repo/SHA | 相同 K60_DEVICE_INPUT/K60_OUT 下运行 `[python3, DEVICE_REPO/scripts/sync-device-input.py, --check]`；核 strict 原始回执 | 无漂移、不复用 out-baseline、不跳过 gates、每条真实 rc 保留 | NOT RUN / null |
| PRE-3 | 所有原始输入、配置、series 与工具；各 repo/SHA | 每个文件独立 `[sha256sum, FILE]` 与 `[stat, -c, %s, FILE]`；记录 Python/dtc/mtools/xz/gzip 版本 | 哈希、大小、顺序与产生回执相符；各 rc 0 | NOT RUN / null |
| PRE-4 | 同次 build-manifest、payload.json、boot.json 及关联产物 | 交叉核来源 SHA、argv/env、输入输出哈希 | 同一完整产生链，无缺项与未确认默认输入；rc 0 | NOT RUN / null |

现有设备入口 `scripts/build-strict.sh:183-194` 使用 mtype 管道求哈希和 args。非空哈希不证明 mtype 成功；未来验收要先带真实退出码抽出文件，再独立计算哈希。这是验收补强项，本轮不改构建脚本、不放宽门禁。

`sync-device-input.py` 的 `--check` 还会读取固定的 `/opt/k60/trees/k60build/scripts/unixnu` 框架副本；只设置 K60_DEVICE_INPUT 不会改变这个目标。执行前确认它与账本的实际构建框架一致，否则分别留存这条检查的真实结果与隔离框架的全文件比对结果，不为了消除共享树差异去同步或清理别人的目录。该版本在发现额外补丁时可打印告警但仍返回 0，PRE-2 还须核输出和完整文件集合，不能仅凭 rc 0 判无漂移。

## 4. OFF 组：modem=False 的旧行为回归

比较改动前框架与候选框架关闭 modem；这组不能由 ON 组结果替代。

| ID | 输入绝对路径与产生 repo/SHA | 命令 argv / 检查 | 预期输出与 rc | 实际输出 / rc |
| --- | --- | --- | --- | --- |
| OFF-1 | 账本两份 OFF stage/ADT/payload；各框架完整 SHA | 比对全部输入、工具、env 与受控随机输入回执 | 除框架实现版本外全部相同；缺前提则 BLOCKED | NOT RUN / null |
| OFF-2 | 两份 ADT；解析器 repo/SHA | `pong_adt_contract.parse_adt` 检查 memory-map | 两份均无 K60ModemImage；其它结构保持基线；rc 0 | NOT RUN / null |
| OFF-3 | 两份完整 stage manifest 与 payload；来源同 OFF-1 | 比对全路径/类型/大小/哈希/时间戳，再 `[cmp, --, OLD_OFF_PAYLOAD, NEW_OFF_PAYLOAD]`，分别算 SHA-256 | 无 MODEM 目录；stage 与 payload 逐字节相同；cmp rc 0 | NOT RUN / null |
| OFF-4 | 候选 OFF payload、payload.json；同次 repo/SHA | 独立 mcopy 回读 ADT、kernel、unixnu.toml，与完整清单比对 | 实际内核/args/其它文件未改变；载具计数按接口为关闭状态；rc 0 | NOT RUN / null |

### 4.1 随机输入不是 identity seed

本轮在框架 `scripts/unixnu/devicetree.py:310` 读到 `os.urandom(256)`；固定 unique-chip-id 不会固定该随机种子。两个正常独立构建的 payload 哈希不同，不足以归因于 modem 改动；仅固定 utime/EPOCH 也不足以证明可复现。

OFF 字节回归应使用隔离离线 harness，在旧/新框架同一调用点注入相同测试随机输入，记录 harness 的已提交 repo/SHA、注入范围、调用次数及其它变化源。不得修改生产随机源，受控测试产物不得进入上机队列。尚无可审计 harness 时，OFF 字节结论为 BLOCKED；另保留正常随机输入产物的结构检查，两类证据分开。

删除 random-seed 后结构相同，不能写成旧产物逐字节不变；不能原地改旧文件随机种子后声称仍匹配原始历史哈希。

## 5. ON 组：完整阶段与载具校验

| ID | 输入绝对路径与产生 repo/SHA | 命令 argv / 检查 | 预期输出与 rc | 实际输出 / rc |
| --- | --- | --- | --- | --- |
| ON-1 | 原始 modem 目录、设备 repo/SHA、载具目录和打包回执 | `[python3, DEVICE_REPO/scripts/gen-modem-table.py, RAW_MODEM, --manifest, EVIDENCE/want.txt]`；核原始/压缩逐文件清单 | 30 段、27 个文件段（名字 b01–b13/b15–b20/b22–b29，非连号）、copied 109060761、bss 211012967；rc 0 | NOT RUN / null |
| ON-2 | 同次生成、删除前保留的完整 stage；框架 repo/SHA | 导出全部相对路径、类型、大小、哈希、时间戳和目录枚举顺序 | MODEM 恰 27 个普通文件；整个 stage 无缺项/替换；rc 0 | NOT RUN / null |
| ON-3 | 同次 stage 的 ADT/流；解析器与表生成器 repo/SHA | parse_adt 检查 memory-map；精确比对 want.txt 名字加 .lzma 与实际文件集合 | K60ModemImage 恰 16 B 全零；与既有项共存；27 文件集合相等；rc 0 | NOT RUN / null |
| ON-4 | stage MODEM、ON-1 manifest；检查器 repo/SHA | `[python3, DEVICE_REPO/scripts/check-modem-lzma.py, --dir, ON_STAGE/EFI/UniXNU/MODEM, --manifest, EVIDENCE/want.txt, --sum]` | files=27 failures=0、declared-total=109060761；rc 0 | NOT RUN / null |
| ON-5 | ON payload、完整 stage 清单、原始流、payload.json；同次 repo/SHA | 新建空目录后 `[mcopy, -s, -n, -i, ON_PAYLOAD, ::/*, EVIDENCE/on-extracted]`（通配符原样传给 mtools）；另记根目录清单，递归核全部路径/类型/大小/哈希，重做 ON-3/4 | 所有阶段文件进入同一卷，无额外文件；payload=201326592 B；mcopy 与检查各 rc 0 | NOT RUN / null |
| ON-6 | 抽出 kernel、unixnu.toml、payload.json/build-manifest；同次设备 SHA | 独立 sha256sum；TOML 解析实际选中 entry 的 path/args，核 payload patch/seal 回执 | 实际内核可追溯，参数与目标一致，pong_modem=2 恰一次；原有 args 门禁另查；rc 0 | NOT RUN / null |
| ON-7 | 两次独立 ON 输出；同一框架 SHA/全部输入/随机控制回执 | 完整 stage 清单比对，再 `[cmp, --, ON_PAYLOAD_1, ON_PAYLOAD_2]` 与各自 SHA-256 | 受控测试下完全相同；缺前提则 BLOCKED；不宣称正常随机构建必同哈希 | NOT RUN / null |

框架级子集已可执行：`scripts/verify-modem-carrier.py --unixnu ... --board ... --dtb ... --carrier ...
--manifest ... --work ...` 覆盖 5.1、5.2 的卷与 5.3，写 `acceptance.json`（输入 SHA、27 流哈希、
框架 HEAD 与 dirty 清单、工具版本、逐项结果与真实 rc）。2026-11-16 在真实 `board.toml`、
`candidates/4g-quiet/hardware.dtb`、dxe-dryrun-d 的 27 个流与 `want.txt` 上 `ACCEPTANCE PASS 11/11`、
rc 0，回执 `/mnt/e/k60-work/artifacts/modem-carrier-verify/port-run/acceptance.json`。该次运行使用
`ecc15f974…` 的独立 `git clone`（`git clone /mnt/e/hackios/UniXNU` + `checkout` 该 SHA，HEAD 一致、
dirty 0），因为共享工作区这时已出现未提交的 `scripts/unixnu/payload.py` 改动（非本线所为）；工具遇到
载具实现三文件有未提交改动即以 rc 2 拒绝，不会把工作区内容当成交付修订。它不运行 `unixnu build payload`、
不构建内核，所以 ON-2/5/6/7 与整链候选仍为 **NOT RUN**；该回执只证明框架契约的离线子集，不把本表
任何候选行改成 PASS。

框架 `scripts/unixnu/payload.py:297` 在结束时 `shutil.rmtree(stage)`。需 Lead 提供同次构建在删除前导出的完整 manifest 或阶段快照及回执。事后 FAT 抽取只能证明卷里内容，不能倒推此前 stage；缺阶段证据须单独待验。本线不为此修改框架。

ON-4 只检查头与长度，不证明流实际可解压。补充项 **ON-4D**：对同一 27 文件分别执行 `[xz, --format=lzma, --decompress, --stdout, STREAM]`，将 stdout 直接保存到新的解码文件，不接管道；立即保存 xz 的 rc，再独立执行 `[cmp, --, DECODED, ORIGINAL_SEGMENT]`、sha256sum 与大小检查。期望每流 xz/cmp 均为 0、长度等于 manifest、内容等于对应原始段；实际 **NOT RUN / null**。原始文件路径、流路径、解码路径及工具/生成器 repo/SHA 逐项填入回执。若用 UEFI 同源 LzmaDec 的宿主 harness，再附其 repo/SHA、编译 argv、二进制哈希、精确输出长度和输入消费量。历史 27/27 不代替新输入验证。

## 6. 已交付 boot 的封装核验（不产生新镜像）

| ID | 输入绝对路径与产生 repo/SHA | 命令 argv / 检查 | 预期输出与 rc | 实际输出 / rc |
| --- | --- | --- | --- | --- |
| PKG-1 | Lead 提供 boot、FD、DTB、shim、payload、manifest 与来源 | `[python3, DEVICE_REPO/scripts/verify-boot-image.py, --manifest, BUILD_MANIFEST, --image, BOOT]`；独立解包补充比对 | Android v4/4096 页；gzip 解出 shim+FD 完全匹配；后附 DTB 与输入一致；ramdisk 与验收 payload 完全一致；rc 0 | NOT RUN / null |
| PKG-2 | 同上；FD 来源为确认过的 UEFI pin/patches | `[stat, -c, %s, FD]`，解析头 kernel_size/ramdisk_size 与最终长度 | FD=3145728；payload=201326592；boot=4096+ceil(kernel_size/4096)*4096+201326592+4096；rc 0 | NOT RUN / null |
| PKG-3 | 该 boot 中实际 kernel/config；同一构建链 | `[python3, DEVICE_REPO/scripts/check-image-args.py, --image, BOOT, --board, DEVICE_INPUT/board.toml]`；同 ON-6 比对 | 实际内核哈希与所选 entry args 一致；不能只看 boot header cmdline；rc 0 | NOT RUN / null |
| PKG-4 | 同次 boot/payload 与 UEFI 来源回执 | 13 号表 A 七项、B 六项分别保留绝对输入路径、argv、输出与 rc | 分项判定；未检查 UEFI 则 B 待验；不运行含 C 的整份脚本冒充离线全绿 | NOT RUN / null |

kernel_size 包含压缩 shim+FD **及后附 DTB**，不是只有 gzip 长度。尺寸自洽不证明 FD、内核正确或可以上机。表 C 待 Lead 交付真实 console.log 后执行，判据不改；本轮没有表 C 结论。

## 7. 历史夹具与当前结论

`/mnt/e/k60-work/artifacts/bootimg-test/boot-modem-4024.img` 仅保留为历史离线夹具，不是最新可飞图。相邻 boot.json 本轮读取到下列声明值，未重新计算大文件哈希：

- image_bytes：201891840。
- image_sha256：`8c9c7d2d9d11c11094d25e60fdc9aea6d575d6286f531ae74cc1ebf9dbb9dc02`。
- fd_sha256：`93e0affda5f8598546094b12a89fd97abcd7c7bc2d3a3adcf5afe18571f3ddd6`。
- dtb_sha256：`2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`。
- hardware_tested：false。

完成项仅为清单准备。待 Lead 提供框架完整 SHA、匹配 UEFI pin/patches、隔离构建输入与完整阶段证据，才开始 PRE、OFF、ON、PKG 对应的五级接口验收；所有未执行项保持 NOT RUN，不把旧 A/B 绿灯当新产物合格。

缺失/不匹配时的回执与阻断范围见 [18 号失败矩阵](18-FAILURE-RECEIPT-MATRIX.md)；该矩阵是计划判据，未执行项继续保持 NOT RUN/null。

规范：[13 号门禁](13-FIRMWARE-ACCEPTANCE.md)、[15 号载具](15-FIRMWARE-CARRIER-LOADER.md)、[16 号接口](16-FRAMEWORK-REQUEST.md)。
