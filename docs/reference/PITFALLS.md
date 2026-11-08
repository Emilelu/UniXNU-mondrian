# K60 iOS 移植 — 踩坑台账（PITFALLS）

> **用途**：踩坑台账——**「不要重复踩什么」的权威源之一**，编号 `P-NN`。
> **谁该读**：新 agent 进场必读三份之一；动手做任何操作前先翻 30 秒判定列。
> **边界**：本册收**当前代码树/流程**的坑；commit 史与按轮次汇编的坑在 `PITFALLS-FROM-HISTORY.md`（第 N 条编号），两册互引不重复展开。
> 每条固定字段：**症状 / 触发条件 / 为什么当初走错 / 正确做法 / 证据 / 下次 30 秒判定**。
> 目的：让同一个坑最多只踩一次。新坑追加到末尾，编号连续。
> 历史坑的批量汇编见 `PITFALLS-FROM-HISTORY.md`（另一 agent 产出）。

---

### P-01 arm64 的 4 GiB pagezero：`[4K, 4MiB)` 永远扫不到东西

- **症状**：内核探针读用户进程低地址内存，期望找到异常字符串，结果全空。
- **触发条件**：任何试图 `copyinmap` 读进程地址空间低 4 MiB 的取证代码。
- **为什么当初走错**：照 x86/其他平台直觉，以为「低地址 = 程序头/堆起点，有料」。arm64 的 pagezero 是整整 **4 GiB**，`[0, 4GiB)` 从不映射，低 4 MiB 落在其中，`copyinmap` 处处失败。
- **正确做法**：不碰地址空间盲扫；读 exit_reason 的 kcdata（`KCDATA_TYPE_PID` / `KCDATA_TYPE_PROCNAME` / `EXIT_REASON_USER_DESC`）——异常文本是 abort/terminate 时由用户态主动挂上去的。
- **证据**：`xnu-work/bsd/kern/kern_exit.c` 162–168 行注释（实测后补写）；D-2026-11-02-07。
- **30 秒判定**：看到任何「扫 `[0x1000, 0x400000)`」或「读低 4 MiB」的提议 → 直接否，指给本条。

### P-02 STR 探针（旧地址扫描版）实测全空 ✅ 已解决：pagezero 扫描 → kcdata 方案生效

- **症状**：`STR <pid> '<comm>' <text>` 一行都打不出来。
- **触发条件**：4g-str 候选镜像上机取证。
- **为什么当初走错**：同 P-01，区间选错；不是打印逻辑坏了，是源头永远读不到数据。
- **正确做法**：用 kcdata 版（新 STR 输出带 `sender=` / `from=` / `desc=` 三字段，kernel `64ae6488…` 起）。
- **证据**：ISSUES I-20261102-09；`logs/kernel-exit-summary.log`。
- **30 秒判定**：探针输出为 0 行时，先问「源头地址在这个平台上真的映射吗」，再怀疑代码。
- **解决闭环（2026-11-02 晚）**：kcdata 版 STR **已上机验证生效**（用户照片 `IMG_0180.JPG`，boot 镜像 `6153c2aa…` / kernel `64ae6488…`）：成功区分自杀（`sender==自身 pid`、`from='<本名>'`、`sig=6`）与被杀（`from='exc_handler'`、`sig=5`）。本条存档防重蹈。

### P-03 `mcopy` 交互式覆盖确认卡死打包流程

- **症状**：打包/抽文件脚本跑到一半无任何输出、永不返回。
- **触发条件**：脚本里 `mcopy -i payload.img ::/path dest` 且 dest 已存在。
- **为什么当初走错**：mcopy 默认覆盖前交互确认；无人值守环境 stdin 没输入，永久等待。
- **正确做法**：所有 mcopy 调用**一律带 `-o`**（overwrite）。
- **证据**：`tools/package-textonly.py` 33–34 行现均带 `-o`；ISSUES I-20261102-04。
- **30 秒判定**：脚本静默卡住 → `ps aux | grep mcopy`，有驻留进程即中此坑；杀掉后给命令补 `-o`。

### P-04 探针 needle 里 `\\n` 转义笔误 → 计数恒 0 的假象

- **症状**：`handoff-probes.py` 报「KX! dedup 不存在（count=0）」，但改动明明在内核里。
- **触发条件**：探针字节串里写了字面 `\\n`（反斜杠+n 两个字符），二进制里真实存在的是换行符 `0x0A`。
- **为什么当初走错**：从 shell/文档里复制格式串时多转义了一层。
- **正确做法**：needle 用真实字节（`b'...\n'`）；判 0 时**先怀疑探针，再怀疑内核**。
- **证据**：ISSUES I-20261102-11；修复于 2026-11-02 20:41，修复后同内核 count=1。
- **30 秒判定**：探针 count=0 但改动者确信已编译 → 打印 needle 的 `repr()` 检查是否含字面反斜杠。

### P-05 「字符串应出现 N 次」经验断言过期（count==2 事件）

- **症状**：打包校验/探针用旧经验值断言字符串出现次数，误报 FAIL。
- **触发条件**：内核改动改变了 printf 站点数量（KX! dedup 把两处合并成一处）。
- **为什么当初走错**：把「出现 2 次」当成恒真指纹写死；它属于上一代内核。
- **正确做法**：计数断言必须随内核改动同步更新，并在注释里写明**为什么是这个数**（`package-textonly.py` 38–42 行已示范）。
- **证据**：ISSUES I-20261102-10。
- **30 秒判定**：校验 FAIL 且 fail 项是 count 类 → 对当前 kernel.macho 手工 `count()` 一次，以实测值为准更新脚本，不要去改内核凑数。

### P-06 取证单/交接引用旧 sha，张冠李戴

- **症状**：文档说「当前内核 sha X」，实际打出来/上机的是 Y。
- **触发条件**：一天内多次重编；HANDOFF §4 成文（19:30）后又重编两轮（19:54 的 `65fbe51e…`、20:42 的 `64ae6488…`）。
- **为什么当初走错**：凭记忆引用 sha；交接成文后没回刷。
- **正确做法**：**sha 一律从 `candidates/<目录>/build-verification.json` 现场抄**；文档之间用 DECISIONS 的「镜像身份链」表对时；交接前刷新 INDEX（RECORDING-RULES 硬性要求）。
- **证据**：ISSUES I-20261102-05；`logs/boot-attempt-20261102-200610.log` 中三处 sha 一致（snapshot/source/expected）。
- **30 秒判定**：要引用任何 sha 前 → 打开对应候选目录的 `build-verification.json`，不凭记忆。

### P-07 STR 的 `desc='-'` 不代表「没有崩溃原因」

- **症状**：kcdata 版 STR 输出里 `desc` 恒为 `-`，容易误判为「日志缺失 / 探针没读到 / 还要再补探针」。
- **触发条件**：崩溃进程自杀时**没走** `abort_with_reason()` / `terminate_with_reason()` 挂描述（例如直接 `abort()`、NSException 的原因没落到 exit_reason）。
- **为什么当初走错**：（预防性登记，尚无实踩）看到 `-` 的第一反应是怀疑探针链路。
- **正确做法**：`desc='-'` 只说明 userspace 没附原因（**哑崩**），不等于没有原因；先看 `from=` / `sender=` 分「自杀还是被杀」，再决定下一步取证方向。
- **证据**：2026-11-02 晚用户照片 `IMG_0180.JPG`（boot 镜像 `6153c2aa…` / kernel `64ae6488…`）：子问题 A（`accountsd`/`dad`/`aggregated`/`ScreenTimeAgent`）desc 恒 `-`，但 `from='<本名>'` 已足够完成自杀/被杀分类（ISSUES I-20261102-01）。
- **30 秒判定**：`desc='-'` 且 `from='<本名>'` → 哑崩，不是探针问题；`from='exc_handler'` → 被杀，去查中介（I-20261102-13）。

---

### P-08 K60 屏幕挖孔截断长行：屏摄里的「残缺字符串」不是数据证据

- **症状**：屏摄中某行长字符串中间「缺 3–5 个字符」，看似数据畸形（曾把 `KE` 行的 exec 路径误读为 `/usr/bin/[0]=?FDR_Loader`，据此启动过「路径畸形」方向的排查）。
- **触发条件**：任何经过屏幕前置摄像头挖孔位置的长行文本。
- **为什么当初走错**：把屏幕物理遮挡造成的视觉截断当成了内核/用户态的真实字符串内容，没有先核对同一代码路径下其它行是否完好。
- **正确做法**：① 关键长字段（路径、地址串、寄存器值）**必须经用户逐字核对**才能当硬事实；② 新打印设计**优先短行**（字段拆行、行宽 ≤ 挖孔前可见宽度），避免把判决性证据放在长行里；③ 遇到「中间缺字」先怀疑挖孔，再怀疑数据。
- **证据**：2026-11-03 argfix2 屏摄复核（用户口头确认两条「畸形」路径均为挖孔截断）；同屏其它长行完好可对照。
- **30 秒判定**：屏摄字符串中间缺 3–5 字符且缺失位置与挖孔重合 → 一律按视觉截断处理，不作为数据完整性证据；换短行重打或让用户核对后再立项。

### P-09 十六进制块号当十进制用 + 大二进制走 adb stdin：一次写偏 1.19 MiB 进 OS 窗口的事故

- **症状**：写 Data 窗口时 dd 落点错误（写入 1,327,499 字节到 OS 窗口 0x26510000），且内容为失真流；OS 窗 digest 失配。
- **触发条件**：手写把 `0x26110` 当成十进制块号 156944（正确：`0x261100000/4096 = 0x261100 = 2494720`）；传输走 `adb shell` stdin（大流断管）与 `adb exec-in`（Windows adb 37.0.1 对 stdin 做文本模式处理：文件头被加 UTF-8 BOM `EF BB BF`、LF→CRLF）。
- **为什么当初走错**：块号换算跨进制手算且写前未读回落点核对；假设 adb 的 stdin 是二进制通道（实测三种里两种失真，唯一可信的是 adb push 文件协议）。
- **正确做法**：① 块号一律脚本内 `byte_offset/4096` 直接除算并打印（禁手算、禁中间量）；② 写前必读落点 4 KiB 与预期比对（含「不等于源镜像头」反向 sanity）；③ 大二进制传输只用 **adb push + 设备侧 dd**（restore/20 GiB 均验证完整）；④ 先 64 MiB 探针（写+回读 sha）再放全量；⑤ 写完必做全窗 sha256 回读（设备侧，UFS 速度免费）。
- **证据**：`archive/unixnu-rollback-20261103-0330/`（restore-seg.bin sha `5db74a2d…` 写回、OS digest 复验 `bc4c5670…` 一致、ROLLBACK.json 事故条）；corruption 分析（BOM+CRLF，138 差异字节）。
- **30 秒判定**：命令里出现任何手工换算的 seek/count → 停下改用脚本公式打印；任何经 `adb shell/exec-in` stdin 的二进制流 >1 MiB → 直接否，换 adb push。
- **恢复闭环（2026-11-03）**：rollback 段写回 → 段 sha 一致 → OS 窗 digest 复验匹配清单 → Data 窗重写到正确偏移（readback `adbbf0dd…`）→ 清单重写（`33626441…`）。

### P-10 XNU 阶段没有任何日志通道，屏摄是唯一证据源

- **症状**：分析时反复假设「设备上有 log 可读」「先读文本源」；屏摄读数被当高置信直接使用，酿成 `0↔8`/`3↔8`（`abn=382` 误读 302）、位数（7 个 `f` 读成 6 个）等误读被当证据引用。
- **触发条件**：任何 XNU 接管后的取证与读数环节。
- **为什么当初走错**：把 Android/Linux 侧习惯（dmesg/logcat/串口）带进 XNU 阶段——XNU 接管后 USB 全断；ramoops 通道即断、重启 DRAM 掉电不保留、且只属加载器/DXE 侧（I-20261103-02）；USB 日志通道（apps_smmu stream 0）尚未打通（I-20261103-04）；串口 COM3/COM4 是蓝牙虚拟口读不到内核输出。
- **正确做法**：屏摄是唯一证据源 → 读数一律标「屏摄读数、低置信」，并执行 [RECORDING-RULES.md](RECORDING-RULES.md) §7（三重一致性校验、易混对末位待核对、hex 位宽校验、裁切放大、只问用户是/否判断题）；禁止在流程里写「优先读文本/日志」，禁止向用户索要 XNU 阶段日志。
- **证据**：ISSUES I-20261103-02（ramoops 定案）、I-20261103-04（USB 通道未通）；HANDOFF-2026-11-02 §6.6（「屏幕不滚动 + 拍照」为唯一取证通道，D-2026-11-02-01）；用户 2026-11-03 当场纠正「XNU 里面抓不了日志」。**2026-11-04 升级定案：ramoops 结构性不可用（重启即失，TWRP/Android 都读不到）——权威条目 D-2026-11-04-01 / I-20261104-01 / PITFALLS-FROM-HISTORY 第 16 条，本条不再展开。**
- **30 秒判定**：任何计划/报告里出现「读 log」「若有日志」「先看文本源」「读 ramoops」→ 删，改「屏摄读数、低置信」并按 RECORDING-RULES §7 校验。

---


## mcopy（mtools）覆盖已存在文件时打开 /dev/tty 等确认，表现为零 I/O 假死

- **现象**：`package-datafix.py` 的 `mcopy -o -i payload.img ::/EFI/UniXNU/Payloads/kernel.macho extracted/kernel.macho` 在目标已存在时不走 stdin，直接 `open("/dev/tty")` 等待人工确认；进程 S 态、`/proc/<pid>/io` 无读写增长，脚本无限挂起（13:05 那轮「拷完 payload 后被中断」即此；2026-11-03 v1 打包复现两次）。
- **为什么当初走错**：把 `-o`（overwrite）当成「永不询问」；实际上 mtools 对「已存在的落盘目标」仍可能经 `/dev/tty` 确认，stdin 重定向无效（它根本不读 stdin）。
- **正确做法**：重跑前 `rm -f extracted/kernel.macho extracted/kernel.macho.adt extracted/unixnu.toml extracted/verify.adt`；并用 `setsid python3 E:\k60-work\tools\package-datafix.py < /dev/null`（新会话无控制终端，`/dev/tty` 打不开即不会等待）。判定卡死：`ls -l /proc/<mcopy_pid>/fd`，fd 4 指向 `/dev/tty` 即中。
- **证据**：`/proc/388/fd` 实录 fd 4 → `/dev/tty`、wchan=`wait_woken`（2026-11-03 14:27）；`E:\k60-work\usb-a-stage\DIFF-AMFI-PRELINK.md` §5.1。
- **30 秒判定**：打包脚本含 `mcopy` 且 `extracted/` 非空 → 先删目标再跑；发现打包 5 分钟无产物 → 查 fd 是否挂 `/dev/tty`，挂则 kill 后按正确做法重跑。

---

### P-11 整目录 gitignore 误伤构建依赖：整理「参考目录」前必须核对 scripts/ 是否为构建输入

- **症状**：`unixnu build kernel` 在 `build-pong-platform-macos.py: [Errno 2] No such file or directory` 止步；随后连环缺 `build-pong-adreno-platform.py` / `bind-ios16-storage.py` / `bindings.json` / GMU 固件，同一 build 连炸四次。
- **触发条件**：任何「整理仓库目录、加 .gitignore、删参考副本」的动作。
- **为什么当初走错**：把 `pong-driver/` 整体当「参考副本」加进 `.gitignore`（一行 `/pong-driver/`），但其中 `scripts/build-pong-*.py`、`bind-ios16-storage.py`、`shim-bin/` 是 `build-xnu-4k-baseline.sh` 经 `PONG_NATIVE_DRIVER_SOURCE` 实际执行的**构建脚本**（board.toml `pong_native_driver_source` 指向它）；整理后构建链断。又：adreno 脚本需要的 GMU 固件 `--firmware-dir` 默认指向 `/mnt/d/Android/k60-ios/firmware/k60-gpu`（恢复后脚本自述），不在仓库内，随清理一同失联。
- **正确做法**：
  1. **整理任何目录前先查它的 `scripts/` 是否被构建链引用**（grep 构建脚本、board.toml、CI 工作流）；是构建输入的一律不删、不忽略。
  2. **`.gitignore` 只能忽略产物**（`*.a` / `*.o` / `*.log` / `build/` / `build-report.json`），**禁止整目录忽略含脚本的目录**；改完必须 `git check-ignore -v` 证明脚本不再被忽略。
  3. 恢复依赖优先走对象库确定性来源（`git ls-tree -r <commit> --name-only` 判定 → `git checkout <commit> -- <path>`），不要靠搜索现凑。
- **证据**：v2 构建 4 连失败日志（`logs/kernel-v2.log`）；恢复提交 `cafab71 fix(vendor): restore pong platform build scripts`（315cf99 → scripts 7 件 + bindings.json）；`.gitignore` 修正前后（`/pong-driver/` → 5 条产物规则）+ `check-ignore -v` 输出；固件实址 `D:\Android\k60-ios\firmware\k60-gpu`（5 件与 13:55 构建产物 `PongAdrenoFirmware.generated.c` 反嵌字节完全一致）。
- **30 秒判定**：要给任何目录加 ignore/删除前 → 先 `grep -rn '目录名' build-*.sh board.toml .github/workflows`，有命中即停；凡看到 `.gitignore` 里出现整目录（非 `*.a` 等产物模式）→ 直接否，按本条改。

---

### P-12 派 Explore 子代理做「全文提取」只回片段：核心调研文档必须主 agent 亲自读

- **症状**：2026-11-04 GAP 调研轮，派 3 个 Explore 子代理分别精读 4 份/25 份/9 份 references 文档并要求结构化报告，返回结果只有「Relevant Code Snippets」片段指针（每份文档 1-2 个行号摘录），无提取报告，证据颗粒度不满足调研驱动要求，被迫主 agent 重新逐份精读。
- **触发条件**：用 Explore 子代理做「读 N 份指定文档并给详细事实提取报告」类任务。
- **为什么走错**：Explore 的定位是「代码库概念搜索/定位」（返回文件+行号片段），不是「多文档全文消化+写报告」；把报告型任务派给它，产出天然只有片段。
- **正确做法**：① 已锁定具体文件清单的精读任务，主 agent 直接 Read（小文件批量并行）；② 子代理只用于开放域搜索（不知道答案在哪个文件时）；③ 派报告型任务必须用 general-purpose 而非 Explore，且报告长度上限写进 prompt。
- **证据**：GAP-TO-SPRINGBOARD.md 调研轮次记录（2026-11-04）；3 个子代理返回均为 snippets 格式。
- **30 秒判定**：要给子代理的任务里出现「通读这几份文件并报告」→ 改为自己读；只有「找到 X 在哪里」才派 Explore。

---

## 台账维护规则

1. 新坑确认后**当场追加**（与 ISSUES 同步，不等收尾）。
2. 「30 秒判定」必须写成一个可立即执行的动作或一条否决规则，不写空泛口号。
3. 证据栏必须有实物：文件+行号、日志路径、sha、commit。没有的标「待验证」。
