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

### P-13 给 patch 写「新增文件」段必须带 `@@ -0,0 +1,N @@ hunk 头`，否则 git apply 静默建 0 字节文件

- **症状**：`patches/xnu/0391-k60-embedded-init.patch` 应用后链上"成功"，但 `bsd/kern/k60_init_blob.h` 为 **0 字节**；编译报 `kern_exec.c:8096: use of undeclared identifier 'k60_init_blob'` / `'K60_INIT_BLOB_LEN'`。连续 4 轮误判为"patch 顺序问题/树不干净"。
- **触发条件**：手工/脚本生成 `diff --git ... new file mode` 段时只写了 `--- /dev/null` / `+++ b/path` 和 `+` 内容行，漏写 `@@ -0,0 +1,N @@`。
- **为什么当初走错**：`git apply` 对 **缺 hunk 头的新文件段不报错**，按"无内容"处理并创建空文件；`git apply --check` 也通过，所以"检查过了"是假安全感。
- **正确做法**：生成后必须双验：(1) `git apply --check`；(2) `stat -c%s <新文件>` 确认 **非 0** 且 `head -2` 是预期内容。缺 hunk 头就补 `@@ -0,0 +1,<行数> @@`。
- **证据**：`scratch/HDR2.txt`（树里头文件 `-rw-r--r-- 0 bytes`、patch 内 `+#define K60_INIT_BLOB_LEN` 计数 1 却文件为空）；修复后 `scratch/TEST391.txt`（`git apply --check` OK、`header size 262784`）；生成器 `scratch/gen391d.py`。
- **30 秒判定**：任何"patch 里新增文件"的改动 → 应用后立刻 `stat -c%s` 新文件；为 0 即本条，不必查编译错误。

### P-14 改构建脚本前必须 `diff -u` 黄金脚本；删两行 `LD_KERNEL_ARCHIVES` 会让平台驱动整层不链接

- **症状**：内核能启动但 `panic: Unable to find driver for this platform: "J120AP". @IOPlatformExpert.cpp:2319`，且 `strings kernel.macho | grep -c ArmDTPlatform` = **1**（黄金为 **38**）。
- **触发条件**：为"清理 GPU 注入"编辑 `scripts/build-xnu-4k-baseline.sh`，把
  `EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")` 与
  `EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$PLATFORM_ARCHIVES")` 一并删掉。
- **为什么当初走错**：只看到"注入 Adreno 导致 `armcpu_spi_attach` 未定义"，就成片删除注入逻辑；这两行是**所有平台 archive 的唯一传递通道**，不是 GPU 专用。
- **正确做法**：改脚本前 `diff -u /opt/k60/trees/usb-cdc-mainline/out3/.../tree/scripts/build-xnu-4k-baseline.sh <本仓脚本>`；改后复查
  `grep -c 'LD_KERNEL_ARCHIVES'` 必须 = **2**，且构建后 `strings kernel.macho | grep -c ArmDTPlatform` = **38**、`pong_cpu_startup_finished` = 2。
- **证据**：`scratch/SCRIPTDIFF2.txt`（removed 2 行即这两条）；`scratch/STRINGS.txt`（golden ArmDTPlatform=38 / 修复前 ours=1）；`scratch/ARMIO.txt`（personality 表 `IOClass=ArmDTPlatform` 存在但驱动 0 符号 → 落到 `IOPanicPlatform`）。
- **30 秒判定**：panic 里出现 `Unable to find driver for this platform` → 先数 `ArmDTPlatform` 字符串数与 `LD_KERNEL_ARCHIVES` 行数，两个数不对就是本条。

### P-15 `cp -a` 覆盖已有 `tree/` 会让 unixnu 跳过整段补丁应用（日志里 `== kernel: patch` 计数为 0）

- **症状**：链接期出现莫名其妙的未定义符号（`_pong_cpu_startup_finished` 等），而补丁文件明明都在 series 里；`IOCPU.cpp` 里 `grep pong_cpu_startup_finished` = MISSING。
- **触发条件**：用 `cp -a` 把某次成功构建的 `.cache/xnu-work` 拷进新 out 目录后再跑 `unixnu build`。
- **为什么当初走错**：以为 `tree/` 只是源码缓存，实际它是"补丁已应用"的状态标记；`unixnu` 见 `tree/` 已存在即跳过解包+打补丁。
- **正确做法**：需要重建时**删 `tree/` 与 `build/` 让 unixnu 从零解包**；或保留树但手工补丁后再构建。每次构建后必须 `grep -c '== kernel: patch' build.log` = **192**。
- **证据**：`scratch/FULLREBUILD.txt`（`D series: 192`、`patches applied: 192`）；`scratch/COPYOUT.txt`/`FUNCDIFF.txt`（`== kernel: patch` 计数 0 的那轮）；`scratch/IOCPU.txt`（`our IOCPU.cpp MISSING` / `golden :69` 有定义）。
- **30 秒判定**：构建日志 `grep -c '== kernel: patch'` 不是 192（或 191）→ 树状态不对，别查符号。

### P-16 清 `tree/` 会连 `.cache/fakeroot` 与 `.cache/sources` 一起删：SDK 头 + DriverKit 缓存必须回填

- **症状**：`fatal error: 'Availability.h' file not found`（`mach/arm/vm_types.h:76` 引入）；或 `prepare-xnu-source.py` 报 `HTTPError: HTTP Error 403: rate limit exceeded`。
- **触发条件**：`rm -rf tree` 做干净重建。
- **为什么当初走错**：把 `.cache/` 当成可丢弃派生数据；实际 `fakeroot`（含 `usr/include/Availability.h`）与 `sources/xnu-driverkit-*.json` 是**外部获取**的输入，重建不会自动恢复。
- **正确做法**：清树前备份、清后立刻回填：
  `cp -a <旧树>/.cache/fakeroot <新树>/.cache/`；
  `cp -a <旧树>/.cache/sources <新树>/.cache/`（`xnu-driverkit-10063.121.3.json` 等 6 个）。
- **证据**：`scratch/FIX403.txt`（`old sources caches` 5 个 json 被复制、`DriverKit: 36 files`）；`scratch/FULLREBUILD.txt`（`headers: 16193` = `Availability.h`）；`scratch/L1ERR.txt`（403 堆栈）。
- **30 秒判定**：编译报 `Availability.h` 找不到 或 `HTTPError 403` → 直接查 `.cache/fakeroot/usr/include/Availability.h` 与 `.cache/sources/` 是否为空。

### P-17 `unixnu bootimg` 产出的 boot 镜像布局错误：`ksize` 写成 1,027,600，payload 落 UEFI 找不到的偏移

- **症状**：`fastboot boot` 报 `Booting OKAY` 但设备**完全静默**（无 CDC 枚举、无 fastboot、无 adb）。
- **触发条件**：用 `unixnu bootimg ... -o out.img` 直接出镜像。
- **为什么当初走错**：以为 `bootimg` 是官方出镜像步骤就该正确；实际它把 payload 放在 header 未声明的偏移。
- **正确做法**：以 `boot-0461-20261107.img` 为模板 splice：保持 `[0,4096)` header（`u32@8 = kernel_size = 548,774`、`u32@16 = ramdisk_size = 0`）、`[4096,552960)` kernel 区不动，**payload 从偏移 552,960 起**替换。
- **证据**：`scratch/STRUCT.txt`（0461: ksize=548774 / 0602: ksize=1027600, rsize=0, `extra=201330688`）；`scratch/SPLICE4.txt`（spliced 201,879,552、payload head 与 0461 逐字节同）。
- **30 秒判定**：新镜像 `u32@8` 不等于 548,774 → 布局错，别上机。

### P-18 内核写文件必须 `vnode_close(vp, 0, ctx)`；传 `FWRITE` 触发 `vnode_rele_ext kusecount` panic

- **症状**：`panic(cpu 0): vnode_rele_ext: vp ... kusecount(%d) out of balance with usecount(%d)`（`vfs_subr.c:2693-2694`），随后 `lock_mtx.c:194` 嵌套 panic stall。日志停在 `K60DATA attempt returned error=0 stage=4` 之后、init helper 之前。
- **触发条件**：内核里新写"写文件"逻辑时自选参数（我用了 `vnode_close(vp, FWRITE, ctx)` + `IO_SYNC|IO_NOCACHE` + `NOCRED`、无 resid）。
- **为什么当初走错**：`FWRITE` 名字看着"我在写所以传 FWRITE"很自然；实际 `vnode_rele_internal` 会因此递减**未被 acquire** 的 `v_writecount`。
- **正确做法**：照抄仓库内**已在设备验证**的写法 `patches/xnu/0340-k60-uilib-deploy.patch:7001-7013`：
  `vnode_open(path, O_CREAT|O_WRONLY|O_TRUNC, 0644, 0, &vp, ctx)` →
  `vn_rdwr(UIO_WRITE, vp, ..., 0, UIO_SYSSPACE, IO_SYNC, vfs_context_ucred(ctx), &resid, current_proc())` →
  **`vnode_close(vp, 0, ctx)`**。
- **证据**：`scratch/VNC0391.txt`（0340 原件与 0391 的逐项差异）；`scratch/BUILD_FIX.txt`（改为 0340 写法后 `CHECK OK / APPLIED`）；`scratch/VERIFY_PB.txt`（此后 `K60INIT: embedded helper write=0 resid=0`、`vnode_rele` 计数 0）。
- **30 秒判定**：`grep -n 'vnode_close' <新补丁>` 出现 `FWRITE` → 直接按本条改，不用排查别的。

### P-19 不要手工编译 init：`ld64.lld 18` 的 `-static` 未实现，产物是动态链接 → `EXEC_EXIT_REASON_BAD_MACHO`

- **症状**：`initproc failed to start -- exit reason namespace 9 subcode 0x1`；`namespace 9 = OS_REASON_EXEC`、`code 0x1 = EXEC_EXIT_REASON_BAD_MACHO`（`reason.h:96,244`）。
- **触发条件**：WSL 里 `clang -static -nostdlib ...` 编 init stub。
- **为什么当初走错**：`clang` 只给 `warning: Option '-static' is not yet implemented`，链接"成功"了，但产物 `flags=0x200085`（含 `DYLDLINK`）且带 `LC_LOAD_DYLINKER`，内核 `load_machfile` 判 BAD_MACHO。又误判为 AMFI 拒签（`namespace 9` 不是 CODESIGNING(3)）。
- **正确做法**：**不要自己编 init**。设备上的 `/private/var/pong/init` 是用 `write-pong-init-*.ps1` 四闸门 dd 写入的现成静态件（34,8xx B，源码级已是 `/sbin/launchd`）。
- **证据**：`scratch/STUBFORM.txt`（`flags=0x200085 DYLDLINK=True LC_LOAD_DYLINKER`、`ld64.lld: warning: -static not yet implemented`）；`scratch/PAGEZERO.txt`（对照 pong init `flags=0x1`、`__PAGEZERO 0x100000000`）；`scratch/EXECCODE.txt`（`EXEC_EXIT_REASON_BAD_MACHO 1`）。
- **30 秒判定**：panic `namespace 9 code 1` → 直接 `file <该 init>`，出现 `DYLDLINK` 即本条。

### P-20 黄金已在 `boot-0461` 进到 SpringBoard；真阻塞是 launchd(PID 1) 崩溃，不是内核缺件

- **症状**：长期把 `boot-0461-20261107.img` 当"失败镜像"，花多轮去"修 launchd 起来"；实际该镜像**已进系统**。
- **触发条件**：只看崩溃尾部、不看它前面已打印的 SpringBoard 加载序列。
- **为什么当初走错**：`boot-0461` 日志末段是 `initproc exited` panic，容易被当成"没进去"；实际同份日志前段有
  `Pong UI: 20G81 compatibility library entered SpringBoard` /
  `[SpringBoard] [backboardd] Pong UI: UIApplication -_run hooked`，
  崩溃发生在 launchd 读 `/System/Cryptexes/App/usr/libexec/webbookmarksd`（`errno 2`）之后。
- **正确做法**：判"是否进系统"必须同时看**前段**（SpringBoard/UIApplication 行）与**后段**（`initproc exited`）；后者是 launchd(PID 1) 崩，属 `apply()` 缺位导致 job 集与文件系统不一致。
- **证据**：`evidence/bootcap-20261107-212612/console.log` 第 1966/2055/2073 行（SpringBoard Pong UI img）、第 3550 行（`webbookmarksd ... errno 2` + `KX! 18 1 launchd sig=11`）、第 3555 行（`initproc exited namespace 2 subcode 0xb`）。
- **30 秒判定**：任何"某镜像没进系统"的判断 → 先 `grep -ac 'SpringBoard\|UIApplication' <log>`，>0 即已进系统，改查 launchd 崩溃。

---

### P-21 认 init 版本必须按「日志字符串组合」匹配，不能按文件名或单一标识猜

- **症状**：我先后把设备写回 `init-v10guard`、`init-v11drain`，两次都以为"恢复基线了"，但 boot 仍失败；实际 11-07 成功那次跑的是 **`init-v11drain`**，`init-v10guard` 少了 `console drainer`。
- **触发条件**：只凭日志里 `[v10guard]` 这种单一标识，或只按文件名 `init`/`init-v2` 去比对。
- **为什么当初走错**：`init-v11drain` 的 banner 仍打印 `HackiOS adapter [v10guard]`（版本名沿用），所以 `[v10guard]` 不能区分 v10guard / v11drain；而 `init-v10guard` 里根本没有 `console drainer` 字符串。
- **正确做法**：用**两个以上特征串的组合**判定：
  `alive, console ready` + `[v10guard]` + **`console drainer pid=%d`** + `var: write-check`
  → 唯一命中 `init-v11drain`（34,912 B，sha `12b9df42cb76c2ffe21a1326215abe2021ad02ce332b9215e7c2b0fe1ac26b94`）。
  写盘后必须 Gate3（整段 36,864 sha `eceb785e…`）+ Gate3b（裸 34,912 sha `12b9df42…`）双通过。
- **证据**：`scratch/V11CHK.txt`（v11drain 串全命中）、`scratch/VER11.txt`（v10guard drainer=0 / v11drain drainer=2、11-07 日志 drainer=1）、`scratch/WRITEV11.txt` 走查、`scratch/writev11.ps1` 的 Gate3 PASS 输出。
- **30 秒判定**：要恢复 init → 先 `grep -a 'Pong init:' <11-07日志> | head -25` 取全部标识串，再在 `deliverables/pong-init/init-v*` 上逐个 `strings | grep -c` 求交集；唯一命中的才是目标版本。

### P-22 同镜像同内核同 args 却出现 dyld 失败 ⇒ 先查 dyld shared cache 可见性，不要怀疑 init/内核

- **症状**：`boot-0461-20261107.img`（sha `5df3a070…`，内核 `d56edb6f…`）在 11-07 21:26 那次 boot 一路到 SpringBoard；今天用**同一个文件** boot，`KE 2 1 init /sbin/launchd` 之后立刻 `dyld[1]: Library not loaded: /usr/lib/libSystem.B.dylib ... (no such file, no dyld cache)`，`KX! 1 1 launchd ... ns=6 code=0x1`。
- **关键对照（必须记住）**：11-07 日志里 `shared_region ... vm_shared_region_start_address() failed` **同样出现两次**（:529/:539），但**没有任何 dyld 错误**，之后 launchd 还能从缓存加载 `/usr/lib/system/libdyld.dylib`（:977/:1179/:1482/:1972）。新日志在同样两行 shared_region 之后立刻 dyld 失败（:563）。
  ⇒ **shared_region 的这两行是噪声，不是判据；判据是「有没有 dyld 报错」。**
- **结论**：差异只在 **dyld shared cache 是否可见**。`PATHS p0..p7` 是 panic 期在异常上下文里做的 `vnode_lookup`，两次值完全相同（`p0=0 p1=2 p2=2 p3=2 p4=2 p5=2 p6=0 p7=2`），**不能当作 boot 期真值**，不要据此下结论。
- **正确做法**：①在 **boot 期、init 之前**加探针打印 `vnode_lookup` 结果（panic 期探针不可用）；②或用 `tools/apfs` 从 OS/SystemOS 镜像里确认 `System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64` 是否真的存在，再决定是否需要在 Data 侧补一份并 bindfs 到该路径。
- **证据**：`scratch/CENSUS.txt`（旧/新日志 dyld 行对照）、`scratch/IMGKERNELS.txt`（11-07 各镜像内核 sha 全不相同：0458 `77a2ca32` / 0459 `62135cde` / 0460 `a00ea847` / 0461 `d56edb6f`；out3 是 `78a0951a`，**都不是同一个**）、`scratch/KERNELSHA.txt`。
- **30 秒判定**：看到 `dyld[1]: Library not loaded ... no dyld cache` → 直接查 dyld shared cache 可见性；**不要**去改 init、不要怀疑 boot args、不要看 `PATHS p*`。

---

### P-23 同名不同物：`scratch/payload-0461.img` 不是 `boot-0461-20261107.img` 里的 payload

- **症状**：我拿 `/mnt/e/k60-work/scratch/payload-0461.img` 当"黄金 payload"去打包，结果它的 `unixnu.toml` 只有 **16 项 args**（`debug=0x144`，无 `k60_usblog=2`、无 `k60_skip_firmware_mount=1`、无 `amfi_get_out_of_my_way=1`），根本不可能产生 11-07 那份带串口日志的启动。
- **根因**：文件名都叫 `payload-0461`，但 `scratch/payload-0461.img` 与 `boot-0461-20261107.img` 内嵌的 payload **不是同一份**（前者是同日另一次迭代的中间产物）。判断一个镜像用哪套 args，**只能从该镜像内部提取**。
- **正确做法**：从镜像取 payload：
  `ksize=u32@8` → `off = 4096 + ceil(ksize/4096)*4096` → 读 201,326,592 B → `mcopy -i <payload> ::/EFI/UniXNU/unixnu.toml`。
  `boot-0461-20261107.img` 的真实 args = **28 项**，含 `debug=0x140`、`k60_skip_firmware_mount=1`、`k60_tolerate_cache_loader=1`、`k60_usblog=2`、`amfi_get_out_of_my_way=1` —— 与 11-07 日志 `boot-args =` 行逐项一致（`scratch/FINDREAL2.txt`：MATCH=28/0）。
- **附带纠正**：11-07 各镜像的内核 sha 全不相同（0458 `77a2ca32`、0459 `62135cde`、0460 `a00ea847`、0461 `d56edb6f`），out3 的 `78a0951a` 不在其中任何一个里；**不要再用"out3 黄金内核"当复现基准**。
- **证据**：`scratch/PACKPROBE.txt`（16 项 args，MISSING 一堆）、`scratch/PACKPROBE2.txt`（28 项全 OK）、`scratch/FINDREAL2.txt`（扫描 40 个镜像，只有 0450–0461 系列命中 28/0）。
- **30 秒判定**：要确认某镜像的 args → **从该 .img 现取**，不要读 `scratch/payload-*.img`；取完先数 `arg count`，与预期不符立即停。

---

### P-24（= 历史坑 64-2 的复发）换核必须重跑 `patch-armcpu-validate.py --apply`

- **症状**：`panic: "CPU configuration in device tree is invalid" @AppleARMCPU.cpp:111`，USB 不枚举、无串口日志、也不自动复位。
- **复发经过（2026-11-08）**：我用 `mcopy -o -i payload ::/EFI/UniXNU/Payloads/kernel.macho <新内核>` 直接换核，**绕过了 payload 步骤本会执行的 `tree/scripts/patch-armcpu-validate.py --apply`**。这不是新坑，`PITFALLS-FROM-HISTORY.md` 第 64 条「坑 2」写得一字不差。
- **正确做法（每次换核固定四步）**：
  1. `python3 <tree>/scripts/patch-armcpu-validate.py --check <kernel>` → 若输出 `original bytes match` 则必须 `--apply`；
  2. `--apply` 后必须再 `--check`，期望 **`already patched`**，并确认字节 `ff8304d1fc6f0ca9 → 20008052c0035fd6`（`mov w0,#1 ; ret`）；
  3. 打入 payload 后做**三段自检**：`header+kernel == template[0:552960]`、`ramdisk == payload` 逐字节、`trailer == template[201879552:]`；
  4. 核对 `ksize == 548774`、`ramdisk_size == 0`。
- **证据**：`scratch/ARMCPUFIX.txt`（`--check` 原文、`patched: mov w0,#1 ; ret`、`already patched`、三段自检全 True）；历史条目 `docs/PITFALLS-FROM-HISTORY.md:613` 第 64 条；`docs/references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md:28`。
- **30 秒判定**：看到 `AppleARMCPU.cpp:111` → **不要查内核代码、不要查 ADT**，先对打包用的 kernel 跑 `patch-armcpu-validate.py --check`；不是 `already patched` 就是这条。

---

### P-22 更正（2026-11-08 实测）：不是"cache 不见了"，而是 init 的 `DYLD_SHARED_CACHE_DIR` 指错路径

原 P-22 结论作废。**boot 期探针（0392）实测**：
```
K60DYLD /System/Library/Caches/com.apple.dyld                          rc=0
K60DYLD /System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64 rc=0   ← cache 一直都在
K60DYLD /private/preboot/System/Library/Caches/com.apple.dyld          rc=2   ← 不存在
K60DYLD /usr/lib/libSystem.B.dylib                                     rc=2   ← 正常（在 cache 内）
```
init 的 `env[]` 把 `DYLD_SHARED_CACHE_DIR=/private/preboot/System/Library/Caches/com.apple.dyld/`
（pong 真机 preboot 卷的路径）照搬到本移植，但本移植的 cache 在 `/System/Library/Caches/com.apple.dyld/`。
dyld 因此报 `(no such file, no dyld cache)`，再回退找 `/private/preboot/usr/lib/libSystem.B.dylib` 也失败 → `ns=6 code=0x1`。

**修复**：init 的两条环境变量改为
```
DYLD_SHARED_CACHE_DIR=/System/Library/Caches/com.apple.dyld/
DYLD_FALLBACK_LIBRARY_PATH=/usr/lib
```
实测结果（`evidence/usblog-20261108-135117/console.log`）：
`launchd_cache_loader reported as clean exit (was 0x0)`、
`K60PSX pid=24/45/79/44 err=0`、`assistantd/locationd/mediaserverd/tccd` 全部运行、
**`Pong UI: 20G81 compatibility library entered SpringBoard` + `UIApplication -_run hooked`**。

- **证据**：`scratch/INITV13.txt`（编译与自检）、`scratch/writev13.ps1` 的 Gate3/Gate3b 输出、上述日志。
- **30 秒判定**：`dyld[1]: Library not loaded ... (no such file, no dyld cache)` → 直接看 init 的 `DYLD_SHARED_CACHE_DIR` 指向的目录在设备上是否存在（用 0392 探针或 `ls`），不要怀疑 cache 丢失。

---

### P-26 launchd(PID 1) 崩溃的精确范围：只有 8 个 App-cryptex job；且 `bindfs` 覆盖只读根返回 EPERM

- **实测（2026-11-08，OS 镜像解析）**：`/System/Cryptexes/App` 与 `/System/Cryptexes/OS` 都是**符号链接**，分别指向
  `../../private/preboot/Cryptexes/App` 与 `../../private/preboot/Cryptexes/OS`；而本移植没有 preboot 卷 → 这些路径全部悬空。
  引用 App cryptex 的 LaunchDaemon **只有 8 个**：
  `Safari.passwordbreachd`、`SafariBookmarksSyncAgent`、`webinspectord`、`Safari.History`、
  `safarifetcherd`、**`WebBookmarks.webbookmarksd`（崩溃触发者）**、`AuthenticationServicesAgent`、`webkit.webpushd`。
- **崩溃机制**：`launchd` 对缺失程序做 `access(path, X_OK)` 得 `ENOENT` 后 **SIGSEGV**（`KX! n 1 launchd sig=11 ns=2 code=0xb`）→ 内核 `initproc exited` panic。
- **已试过的修法（失败）**：内核内嵌筛选后的 `launchd.plist`（22 个 CORE job，9,799 B）并写到 `/private/var/pong/launchd.plist`（`K60LC: write=0 resid=0` 成功），再由 init `mkdir`+`rename` 到 `/private/var/pong/xpc/launchd.plist`（`Pong init: curated launchd cache installed` 成功），最后 `mount("bindfs", "/System/Library/xpc", MNT_RDONLY, ...)` —— **失败：`result=-1 errno=1`（EPERM）**。只读根上的目录不能被 bindfs 覆盖。
- **下一步候选（未执行，需评估风险）**：
  1. **同尺寸就地覆盖**：把 curated plist 用填充字段补到原文件**完全相同的 1,384,579 B**，按 `apfs.py stat` 得到的 extent 物理块号，在 TWRP 里 `dd` 覆盖同一范围——不改 inode、不改 APFS 元数据，风险最小；先备份原 1.38 MB 范围。
  2. 整块重写 OS 窗（5.09 GB）——风险高，需完整备份，暂不推荐。
- **证据**：`scratch/CRYPTEX.txt`（8 个 job + 符号链接目标）、`scratch/COREPROG.txt`（22 个 CORE 程序在 OS 镜像里 **MISSING COUNT: 0**）、`evidence/usblog-20261108-143838/console.log`（`boot view ... result=-1 errno=1`、`webbookmarksd`、`initproc exited`）。
- **30 秒判定**：`initproc exited` + `webbookmarksd` → 直接按本条走；不要再怀疑 dyld/init/内核。

---

### P-27 密封根上 `bindfs` 一律 EPERM；`access`/`faccessat` 钩子对 launchd 无效；需用 APFS 二次挂载

- **实测（2026-11-08）**：
  - `mount("bindfs", "/System/Library/xpc", MNT_RDONLY, ...)` → `result=-1 errno=1`
  - `mount("bindfs", "/private/preboot", MNT_RDONLY, ...)` → 同样 `-1 errno=1`
  - 改成 `flags=0` 仍然 `-1 errno=1`
  ⇒ **只读密封根（OS 卷 `incompatible 0x8` = sealed）上的目录无法被 bindfs 覆盖**；pong 的五个 bindfs 视图在本移植全部不可用，日志里的 `optional boot view SKIP` 之后即使跑起来也会 EPERM。
- **secondary 实测**：内核里 `0390`（`access()` 前缀假成功）与 `0396`（`faccessat_internal` 同样逻辑）**都已编进内核**（`strings` 分别命中 1 次），但 launchd 崩溃前**两条打印都没有出现** ⇒ launchd 的 `access(path, X_OK)` 检查既不走 `access` 也不走 `faccessat` 系统调用（是 libSystem 用户态/其它路径解析），在 syscall 层拦截无效。
- **正确的下一步**：用 **APFS 真实挂载**把 Data 卷二次挂到 `/private/preboot`（macOS 的 `/Volumes` 就在密封根上正常挂载，说明 mount 本身不被密封阻止，只有 bindfs 的 vnode 覆盖被拒）。
  设备实测卷号：**Data = `/dev/disk2s1`**（5,210,112 块 × 4096 = 21,342,715,904 B，与 Data 窗 `0x4f8200000` 完全吻合）；OS = `disk1s1`（1,244,160 块）。
  挂载后 `/private/preboot/Cryptexes/App/...` 与 Data 根的 `Cryptexes/App/...` 同源，只需在 `/private/var/Cryptexes/App/...` 建 8 个 **0755 空文件**即可让 launchd 的 `access(X_OK)` 成功。
- **证据**：`scratch/INITV16.txt`/`INITV17.txt`（`app-cryptex stubs ready` 与 EPERM 打印）、`scratch/HOOKCHK.txt`（两个钩子都在内核里但未触发）、`scratch/NAMEI.txt`、`evidence/usblog-20261108-155056/console.log`（`webbookmarksd` + `initproc exited`）。
- **30 秒判定**：看到 `boot view ... result=-1 errno=1` → 不要再试 bindfs 的任何变体（RDONLY/0 都失败），直接上 APFS 二次挂载。

---

### P-28 `mount("apfs", "/private/preboot", MNT_RDONLY, payload)` → **errno 79 = ENEEDAUTH**

- **实测（2026-11-08，init-v18）**：init 在 Data 卷根建好 `Cryptexes/App/...` 的 8 个 0755 空文件后
  （日志 `Pong init: app-cryptex stubs ready` 正常），用与 `/private/var` 相同的 APFS 2142 payload
  `mount("apfs", "/private/preboot", MNT_RDONLY, payload)`，device 传 `/dev/disk2s1`：
  `Pong init: preboot remount result=-1 errno=79`。Darwin errno 79 = **ENEEDAUTH**。
- **含义**：APFS 对同一容器二次挂载要求认证（不是密封阻止、也不是 EPERM）。**「二次挂载 Data 到 /private/preboot」这条路不可行**，不要再试其它 flags 变体。
- **同时已排除**：bindfs 到 `/private/preboot`（MNT_RDONLY 与 flags=0 都 EPERM）、bindfs 到 `/System/Library/xpc`（EPERM）、内核 `access`/`faccessat` 钩子（不触发）。见 P-27。
- **剩下唯一可行方向**：直接替换 OS 窗里的 `/System/Library/xpc/launchd.plist`（同尺寸就地覆盖，不改 inode/元数据）。
  **关键偏移仍未确证**：窗口前 1 MB 很可能是保留区，若 APFS 容器从 `窗口 + 0x100000` 开始，
  则文件位置 = `0x100000(OS 窗) + 0x100000(容器前) + 1062050×4096`，即 **`bs=4096 skip=1062562`**。
  下次设备可用时**第一步就是只读读 32 字节验证是否 `bplist00`**，验证通过再谈写。
- **证据**：`evidence/usblog-20261108-160004/console.log`（`preboot remount result=-1 errno=79`）、`scratch/INITV18.txt`（sha `e8c65936…`）。
- **30 秒判定**：`preboot remount ... errno=79` → 直接放弃二次挂载，转向 OS 窗同尺寸覆盖；看到 `errno=1` → 是 bindfs，别再试。

---

### P-29 设备 OS 窗内容 ≠ 本地 `096-57366-083.dmg`：不能按 dmg 的块号/内容推算

- **实测（2026-11-08）**：把 `096-57366-083.dmg` 解出的 `launchd.plist` 前 64 字节作为指纹
  （`62706c6973743030d6000100…417070457874656e73696f6e735d4c61756e63684461656d6f6e735f1012`），
  对设备 unixnu 分区的 **OS 窗全量 4.75 GB（0x12fc08600，19 个 256 MB 分块）** 做逐块搜索：
  **19/19 全部 hit=-1，RESULT_NOT_FOUND**。
- **含义**：设备上的 OS 内容与本地 dmg **不是同一份镜像**；`NXSB` 在设备 64 MB 头内的分布也与 dmg 完全不同
  （设备在 0x104420/0x10c420/0x10e420… 每 0x2000 一次；dmg 的容器 superblock 在块 0）。
  ⇒ **禁止**用 dmg 的 APFS 块号 + 窗偏移去定位或改写设备上的 OS 文件（会写坏无关区域）。
- **仍成立的事实**：SHNGROOT 清单的窗口偏移是**分区内字节偏移**（Data 窗 `0x261100000` + `0x100000` 内容起点，
  与 init 写盘公式吻合，已多次 Gate3 验证）；OS 窗 = `0x100000`、SystemOS = `0x12fe00000`、Data = `0x261100000`。
  每个窗口**前 1 MB 是保留区**，内容从 `+0x100000` 起。
- **因此**：想改 OS 里的文件，只能在**运行中的系统**里做（ro 挂载挡死了），或改内核行为；离线改写不可行。
- **证据**：`scratch/scanlp*`（扫描脚本）、`scratch/PREP_PLANA.txt`、`scratch/LBA2.txt`、`scratch/PLAN_A.txt`。
- **30 秒判定**：要改 OS 窗内文件前，先用 64 字节指纹全窗扫描确认能定位；扫不到就**立即放弃**离线改写。

---

### P-30 `namei()` 层路径重定向也不触发 ⇒ launchd 的 "access(...)" 行很可能是它自己合成的日志，不是真的路径解析

- **实测（2026-11-08，内核 `dea5e777` / 镜像内 `50d1b6c6`）**：在 `namei()` 入口对 `cn_pnbuf` 做
  `strncmp(path, "/System/Cryptexes/App", 21)` 并改写为更短的 `/private/var/pong...`（理论上必然放得下，
  因为替换串比原串短 4 字节）。补丁已确认编入内核（`strings kernel.macho | grep -c 'K60 redirect'` = 1，
  且镜像内 kernel sha 一致），init 也在 `/private/var/pong` 建好了 8 个 0755 空文件
  （`Pong init: app-cryptex stubs ready at /private/var/pong`）。
  **但整个启动过程中 `K60 redirect:` 一次都没有打印**，launchd 仍在同一位置 SIGSEGV。
- **叠加此前结论**：`access()`（0390）、`faccessat_internal`（0396）、`namei()`（0397）**三层钩子全部不触发**。
  ⇒ 结论：`access(/System/Cryptexes/App/usr/libexec/webbookmarksd, X_OK) failed with errno 2` 这行**不是内核在
  路径解析时打印的**，而是 launchd 自己在 `posix_spawn`/exec 失败后合成的描述（它拿到的 errno 来自 exec 而非
  access(2)）。因此**在 syscall/路径层拦截无效**，必须让那个程序文件真的存在，或改服务缓存。
- **已死的路（不要再试）**：bindfs 覆盖密封根（EPERM）、APFS 二次挂载（ENEEDAUTH 79）、离线改 OS 窗（设备 OS 内容
  与 dmg 不一致，指纹全窗 4.75 GB 扫描 0 命中）、access/faccessat/namei 三层内核钩子（均不触发）。
- **仍可能有效的方向**：①在**运行中的系统里**让 `/private/preboot` 可写（需要 preboot 卷或可挂载介质）；
  ②改 launchd 服务缓存（需要能写 `/System/Library/xpc`）；③换一条不依赖 launchd 拉起 SpringBoard 的启动路径（需调研 pong 是否有）。
- **证据**：`scratch/CHK397.txt`（内核含 0397）、`scratch/CHKIMG.txt`（镜像内 kernel `50d1b6c6` 含 `K60 redirect`）、
  `evidence/usblog-20261108-163128/console.log`（无 `K60 redirect`、仍 `webbookmarksd` + `initproc exited`）。
- **30 秒判定**：想靠内核钩子绕过 App cryptex → **先确认钩子会打印**；不打印就立刻停，别再改钩子。

---

### P-31 pong 的 Goodix 触摸驱动能编进 20G81 内核，但 HID 发布层 ABI 不匹配：`IOHIDEventSystemClientCreateWithType` 不存在

- **实测（2026-11-08，内核 `a1973538`，198 补丁）**：把 pong ios16 分支的
  `zzzz…-pong-touch-console.patch`（36.6 KB：`bsd/dev/pong_goodix.c` + `pong_input.c` + `pong_input.h` + `conf/files` + `bsd_init.c` + `MiniIOMobileFramebuffer.cpp`）
  与 `zzzz…-pong-physical-keys.patch`（12.0 KB：`pong_buttons.c`）顺序加入 series，**构建通过**（内核 54,001,664 B，含 `Pong Goodix Berlin-D` 与全部 goodix 诊断串）。
  启动后日志：**`Pong touch HID: unavailable IOHIDEventSystemClientCreateWithType; SKIP`** —— 触摸协议层跑起来了，但**事件发布层调用的 IOHID API 在 20G81 内核里不存在**，驱动自行跳过。
- **含义**：pong 的 `pong_input.c` 面向更新的 IOHIDFamily（iPadOS 17/18）；20G81 需要按 `ShengHidInput` 的旧 ABI 重写发布层（`OFFICIAL-DRIVER-MAP.md` 第 6 项已写明「`ShengHidInput` 需按 20G81 IOHIDFamily 重对」）。
- **ADT 已就绪（重要）**：`scripts/make-pong-adt.py` **本来就生成** `/arm-io/pong-touch`（spi-base `0x990000`、tlmm-base `0x0f000000`、gcc-base `0x00100000`、rsc-base `0x17a20000`、cmd-db-base `0x80860000`、gpio-offset `0x00100000`、pins `<16 17 18 19 21 20>`）与 `/arm-io/pong-buttons`（core-base `0x0c400000`、cnfg-base `0x0c42d000`、observer-base `0x0c440000`、ee `0`、pon-ppid `0x013`、volume-up-ppid `0x18d`）。本次只把 `max-x/max-y` 由 pong 的 `1080/2412` 改为 K60 的 `14400/32000`。
- **证据**：`scratch/WIRE_DRIVERS.txt`（series 196→198）、`scratch/DRVCHK.txt`（内核含驱动）、`evidence/usblog-20261108-165317/console.log`（`Pong touch HID: unavailable ...`）。
- **30 秒判定**：看到 `IOHIDEventSystemClientCreateWithType` 不可用 → 直接改发布层 ABI，不要再调 SPI/ADT 参数。

### P-32 系统能长时间运行，但 `watchdogd` 反复崩溃最终导致复位（不是 launchd 崩）

- **实测（2026-11-08）**：`disabled.plist` 修掉 launchd 的 App-cryptex 崩溃后，系统可持续运行到锁屏（日志 342 KB，`home request returned locked=1 screen=1 dim=0`），
  但之后出现 `Process[324] crashed: watchdogd. Too many corpses being created.`、`KX! 5 51 watchdogd exit=0 sig=5`，最终设备自动复位回 fastboot。
  **没有** `initproc exited` / `webbookmarksd` —— launchd 侧已修好，复位来自 watchdogd 崩溃链（可能叠加 ABL 开启的硬件看门狗）。
- **含义**：需要 PMIC/看门狗驱动（`pong_buttons.c` 已提供 PMIC-arbiter 只读访问框架），或先禁用 `com.apple.watchdogd`（`disabled.plist` 再加一项）以延长稳定运行时间。
- **证据**：`evidence/usblog-20261108-163843/console.log` 末尾；`evidence/usblog-20261108-165317/console.log`。
- **30 秒判定**：复位但日志无 `initproc exited` → 查 `watchdogd`，不要怀疑 launchd。

---

### P-33 触摸/按键驱动默认是**关闭**的（要 boot-arg），且用户态 HID 发布层无法在 WSL 重建

- **症状**：驱动都编进内核、启动后却完全没有 `Pong keys:` / `goodix:` 日志，按电源/音量/触摸都没反应。
- **根因 1（门控）**：pong 的两个驱动入口都要求 boot-arg：
  `pong_goodix_init()`: `if (!PE_parse_boot_argn("pong_touch",&enabled,...) || !enabled) return;`
  `pong_buttons_init()`: `if (!PE_parse_boot_argn("pong_buttons",&enabled,...) || !enabled) return;`
  没传 → 直接 return，等于没编。**修复 = patch 0399**：把两处 `enabled=0` 改 `enabled=1` 并忽略缺失的参数（默认开）。
- **根因 2（用户态）**：即使内核驱动工作了，事件还要靠用户态 `userland/touch.c` 经
  `IOHIDEventSystemClientCreateWithType` 发布；20G81 没有这个变体（日志 `Pong touch HID: unavailable ...`）。
  已给 `touch.c` 加回退到 `IOHIDEventSystemClientCreate`（老 API），但 **`libpong-ui.dylib` 由 `userland/build.py:compile_ui` 用 macOS `xcrun`+iPhoneOS SDK 编译**，WSL 无法重建；仓库/交付物里也没有预编译产物。
- **可行出路**：①在 macOS 上跑 `userland/build.py` 重新生成 `libpong-ui.dylib` 并重打 0340 的 blob；②把 HID 发布搬进内核（20G81 自带 `IOHIDEventService` / `IOHIDEventCreateKeyboardEvent`），彻底摆脱 macOS 依赖（推荐）。
- **附带结论**：**不要用「每 2 秒重发 DCS 0x29/0x51」的保活线程**去维持亮屏——按电源键熄屏后会被强行点亮，与 iOS 的睡眠逻辑打架；正确做法是让电源键事件进 SpringBoard。
- **证据**：`scratch/KEYSHOOK.txt`（门控原文）、`scratch/INITV21.txt`、`scratch/UILIB.txt`（build.py 需 xcrun）、`evidence/usblog-20261108-165317/console.log`。
- **30 秒判定**：驱动编了但无任何驱动日志 → 先查 `PE_parse_boot_argn` 门控；有 `unavailable IOHID...` → 是用户态库 ABI。

---

### P-34 schema-v2 ADT：`/arm-io` 子节点只来自 DTS 的 `unixnu,adt-name`，且属性必须命中白名单

- **症状**：`pong_goodix` / `pong_buttons` 打印 `missing/incompatible DT; SKIP`，即使内核驱动已编入、boot-arg 门控也已默认打开。
- **根因（两层）**：
  1. `scripts/unixnu/devicetree.py:generate()` 里 `/arm-io` 的子节点**不是**从 profile 的 `["adt"]` 来，而是
     `hardware = [entry for entry in root.walk() if 'unixnu,adt-name' in entry.properties]` —— 只有 `dts/mondrian.dts` 里
     带 `unixnu,adt-name = "..."` 的节点才会被导出。
  2. `hardware_properties()` 只导出**白名单**里的属性名：
     `STRINGS = {compatible, device_type, reg-names, interrupt-names, clock-names, method}`
     `U32 = {phandle, …, pong,smmu-stream-id, pong,ufs-spi, …}`
     `U64 = {redistributor-stride, pong,ufs-hc-base, …}`
     **`spi-base / tlmm-base / gcc-base / rsc-base / cmd-db-base / gpio-offset / pins / max-x / max-y / core-base / cnfg-base / observer-base / ee / pon-ppid / volume-up-ppid` 全部不在白名单里 → 会被静默丢弃。**
- **正确做法（三步）**：
  1. `dts/mondrian.dts` 增加两个节点，带 `unixnu,adt-name = "pong-touch"` / `"pong-buttons"` 并按 pong 的命名写出全部属性；
  2. 在 **UniXNU 框架仓**的 `scripts/unixnu/devicetree.py` 里把上述 15 个属性名加进 `U32`/`U64` 白名单（注意：`tree/scripts` 每次构建从框架仓重新拷贝，改 tree 里的会被覆盖）；
  3. 重新 `unixnu payload` → `unixnu bootimg`/splice → 上机。
- **证据**：`scratch/ADTNEW.txt`（ADT 里 `pong-touch`/`pong-buttons`/`spi-base` 全部 `-1`）、`scratch/WHITELIST.txt`（白名单原文，15 个属性命中数全 0）、`scratch/DTSNODE.txt`（`ufs@1d84000` 的 `unixnu,adt-name = "ufshc"` 范例）。
- **30 秒判定**：驱动报 `missing/incompatible DT` → 先 `strings kernel.macho.adt | grep <节点名>`；不在就按本条查 DTS + 白名单，不要改驱动断言值。

---

### P-35 禁用 daemon 要照 pong 的 DENY 策略，且必须做成**可运行时撤销**的数据，不能硬编码

- **背景**：`boot-0461` 之前 `launchd` 崩在 App-cryptex 的 `webbookmarksd`；用 `disabled.plist` 禁掉 8 个 App-cryptex job 后 launchd 稳定，系统能跑到锁屏。
- **pong 的权威做法**：`userland/mkjobs.py:216` 的 `DENY` 元组包含
  `'watchdog', 'CommCenter', 'wifi', 'WiFi', 'bluetooth', 'BTServer', 'locationd', 'softwareupdate',
  'datamigrator', 'backupd', 'thermalmonitord', 'keybagd', 'nfcd', ... 'syncdefaultsd', 'photoanalysisd', 'avconferenced'`
  —— 注释原文：“these start, crash and are asked for again, over and over”。
  **所以 `watchdogd`/`syncdefaultsd` 这类被禁是 pong 的既定策略，不是掩盖症状。**
- **但**：`wifi`/`bluetooth`/`locationd` 也在 pong 的 DENY 里——那是**pong 当时没有对应驱动**。我们将来驱动 WiFi/BT/location 后必须能重新启用，**所以禁用名单绝不能硬编码进 init**。
- **实现（init-v24，34,904 B，sha `1671eb78…`）**：init 运行时读 `/private/var/pong/disabled-labels.txt`（一行一个 label，`#` 注释），生成 XML 版 `disabled.plist` 写到
  `/private/var/db/com.apple.xpc.launchd/disabled.plist`；文件不存在时用内置缺省（**只有 8 个 App-cryptex + `com.apple.watchdogd`，共 9 项，不含 wifi/bt/location**）。
  日志判据：`Pong init: disabled.plist wrote %u labels`。
- **注意**：`/private/var` 是 APFS Data 卷，TWRP 下无法写；要改名单只能通过内核 blob（同 0394 机制）或等系统起来后用能写 Data 的通道。
- **证据**：`scratch/PONGDENY.txt`（DENY 原文）、`scratch/INITV24.txt`（编译与字符串）、`scratch/disabled-labels.txt`（缺省名单）。
- **30 秒判定**：要禁某个 daemon 前先查 pong 的 `DENY` 有没有它；没有就是我们在发明策略，停下来先查驱动缺什么。

---

### P-36 门控默认值 `enabled=0`：驱动永远第一行 return，且静默无日志

- **症状**：实体键/触摸无任何内核日志、无 `/dev/pong-*` 节点，用户态报
  `verified PMIC input unavailable` / `real touch device unavailable`；一切看起来像"驱动没跑"。
- **根因**：pong 原始补丁 `uint32_t enabled=0;`，boot-arg 门控 `if (!enabled) return;`。
  之前修门控时只改成 `(void)PE_parse_boot_argn(...)`（忽略返回值），**没改默认值 0** →
  没传 boot-arg 时 `enabled` 永远是 0 → 第一行就 return。2026-11-08 18:02 那次实体键
  可用（日志 `Pong keys: arbiter v7 …`）是 `enabled=1` 时期；后来用原始 pong 补丁覆盖把
  默认值带回 0，实体键跟着炸。
- **修复**：`uint32_t enabled=1;`（touch 补丁 920 行、keys 补丁 271 行，commit `7da999e`）。
- **30 秒判定**：任何"驱动静默不运行"先 `grep 'uint32_t enabled='` 看默认值；是 0 就直接改 1。

### P-37 `devfs_make_node(...,"%s",name)`：设备被建成字面 `/dev/%s`

- **症状**：`input_ready()` 返回 true，但用户态永远打不开 `/dev/pong-buttons`。
- **根因**：`devfs_make_node` **不接受 printf 格式串**，`"%s", name` 把字面 `%s` 当节点名。
- **修复**：直接传 `name`。
- **30 秒判定**：任何 devfs 节点打不开，先 `grep devfs_make_node` 看有没有 `%`。

### P-38 K60 触摸 GENI SE 是 **SE4**，不是 SE1；时钟阻塞是 S_AHB 的 HWCG 位

- **症状**：原始 SE4 日志 `s_ahb=0x80000002`（bit31 halt + **bit1 HWCG**），se4=0x4220（已开）。
- **根因**：`K60-TOUCH-PARAMS.md:90` 明确 `spi@990000` = QUP0 **SE4**（pinctrl function `qup4`）。
  我曾误改 7 处 GCC 偏移为 SE1，已回退（commit `7da999e`）。真正阻塞是 S_AHB 的 HWCG 位，
  Linux `clk_branch2_enable` 会先清 bit1。
- **修复**：保持 SE4 常量（`0x274dc` 家族）+ 在 vote 后清三个 CBCR 的 bit1。
- **30 秒判定**：`s_ahb=0x80000002` 时先清 bit1，别乱改 SE 编号。

### P-39 **补丁间有硬依赖顺序**：GPU scanout 必须先于 touch，否则 hunk 上下文对不上

- **症状**：`git apply` 报 `error: patch failed: iokit/Kernel/MiniIOMobileFramebuffer.cpp:1032`，
  说 touch 补丁打不上，但单独看补丁内容完全正确。
- **根因**：touch 补丁的最后一个 hunk 上下文里有 `if (!gpuFrame) drawLayer(s, src, dst);`，
  而 **`gpuFrame` 是 GPU scanout 补丁引入的变量**（`pong-gpu-scanout.patch:42` 定义 `bool gpuFrame=false`、
  `:71` 使用）。若 GPU 补丁不在 touch 之前应用，目标树里没有 `gpuFrame`，上下文永远不匹配。
- **更深一层的坑**：hunk 头写的是 `@@ -1032,6 +1032,10 @@`，但实际 `kPEGraphicsMode` 在所有历史树里都在
  **989 行**（`out/out2/out3` 三棵树的 `show()` 都是 885 行）。**行号本身就偏了 43 行**——
  所以即使顺序对了，靠行号也定位不到，只能靠上下文。
- **诊断方法**：`git apply --check -C1 <patch>` 会打印 `Context reduced to (1/1) to apply fragment at 989`
  ——**这句话直接告诉真实行号**，是排错的最快入口。
- **修复**：series 顺序必须是 **GPU 三补丁 → touch → keys**（当前 `SERIES-FINAL.txt` 尾部 5 行）。
- **30 秒判定**：touch/keys 补丁 apply 失败先查 `grep -n 'gpuFrame'` 在 series 里的位置；GPU 不在前面就是顺序错。

### P-40 构建读的是 `$B/tree/.cache/xnu-work`，不是 device 仓的 `iokit/`

- **症状**：改 device 仓（`/tmp/usb-cdc-mainline/device`）里的 `iokit/Kernel/MiniIOMobileFramebuffer.cpp`
  完全不生效；查行号还会被这份"已打过补丁的产物副本"误导（`show()` 在 899 行 vs 真实树 885 行）。
- **根因**：`build-xnu-4k-baseline.sh` 把 xnu 从 `feeds/xnu-<sha>`（**原始 apple-oss xnu，无 iokit/Kernel/MiniIOMobileFramebuffer.cpp**）
  克隆到 `$B/tree/.cache/xnu-work`，再由 UniXNU 框架的 overlay 注入该文件。
  真正的编译目标是 **`/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`**。
- **关键事实**：`feeds/xnu-c465a9f8` 里**根本没有** `iokit/Kernel/MiniIOMobileFramebuffer.cpp`（已 find 验证）；
  这个文件来自 UniXNU 框架的 `iokit/` overlay。
- **诊断方法**：`grep -a 'prepare XNU' /tmp/build-v15.log` 会打印 `git clone --shared ... /opt/.../tree/.cache/xnu-work`，
  以及 `feeds/xnu-<sha>` 的真实路径。
- **30 秒判定**：要改/查 xnu 里某个文件，先 `find /opt/k60/trees/k60build/out-baseline -name '<file>' -path '*.cache/xnu-work*'`
  ——**改 device 仓的 iokit/ 副本是无效的**。

### P-41 镜像启动 0 字节日志 ≠ 设备坏：先用历史镜像做对照

- **症状**：`fastboot boot` 后控制台日志 0 字节、设备自动回 fastboot，看起来像设备/UEFI 坏了。
- **正确诊断顺序**（本轮实测有效）：
  1. 刷一颗**历史确认能启动的镜像**（如 `boot-0442-20261107.img`，11-07 15:24）
  2. 若它能正常启动并抓到日志（本轮抓到 204,641 B），则**设备、UEFI、打包流程、fastboot 全部正常**
  3. 问题一定在**新内核本体**
4. **本轮实证**：`boot-0442-20261107.img` 启动成功（日志 204,641 B，Darwin 22.6.0 Sat Nov 7 15:03:08），
   而 199/207 版全部 0 日志复位 → 定位到补丁顺序问题（P-39）。
- **30 秒判定**：0 日志复位时**不要先说设备坏了**，先刷一颗历史镜像做对照，30 秒就能排除设备因素。

### P-42 `out`/`out2`/`out3` 是历史构建树，可直接用于对照

- **价值**：`/opt/k60/trees/usb-cdc-mainline/out{,2,3}/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`
  三棵**已打过补丁的完整 xnu 工作树**都还在（各自 1537/1537/1558 行，`show()` 都在 885 行）。
- **用途**：验证补丁能否应用、查真实行号、比对不同时期补丁状态，**不需要重新构建**。
- **30 秒判定**：想判断某个 hunk 是否真能打，直接拿其中一棵树 `git apply --check`，比新建树快得多。

### P-43 `#if defined(PONG)` 在 `bsd_init.c` 里恒为假 → 输入驱动调用被预处理器删除

- **症状**：`bsd_init.c` 里明明写着 `pong_goodix_init(); pong_buttons_init();`，但
  `bsd_init.o` 里 `llvm-nm | grep pong_` **一个符号都没有**，内核里也没有输入驱动日志。
- **根因**：`bsd_init.c` **不 include `<pexpert/arm64/board_config.h>`**，所以 `PONG` 宏在这个
  translation unit 里**未定义**，`#if defined(PONG)` 整段被预处理器删掉。
  （`pong_buttons.c` / `pong_goodix.c` 自己有 include，所以驱动代码本身能编译。）
- **修复**：把这一段的 `#if defined(PONG)` 改成 `#if 1`（或显式 `#include <pexpert/arm64/board_config.h>`）。
- **验证方法**：`llvm-nm bsd_init.o | grep pong_` 必须看到 `U _pong_goodix_init` / `U _pong_buttons_init`。
  **看不到就是被预处理器删了，与补丁内容无关。**
- **30 秒判定**：驱动"编进去了但不运行"时，先 `llvm-nm <含调用的>.o | grep <符号>`；没有 U 引用就是 `#if` 门控问题。

### P-44 改补丁必须改**三方**（repo 补丁 / device 补丁 / 构建树），只改一处会被覆盖

- **三方位置**：
  1. `E:\hackios\UniXNU-mondrian\patches\xnu\<补丁>`（git 真源）
  2. `/tmp/usb-cdc-mainline/device/patches/xnu/<补丁>`（buildv15 会从 repo 覆盖这里）
  3. `$B/tree/.cache/xnu-work/...`（**构建真正编译的树**，每次清树重建）
- **本轮实证的踩坑链**：
  - 只改树 → 下次构建清树即失效
  - 只改 repo → device 侧/buildv15 同步前不生效
  - 只改 device → repo 下次覆盖回旧版
  - `buildv15.sh` 第 15-19 行只同步 **5 个固定补丁**；其余补丁靠 series 从 device 读
- **正确流程**：先改 repo 补丁 → `cp` 到 device → 改树里的文件（或重建让它重新应用）→ 构建 → 验证树里值。
- **30 秒判定**：改完先 `grep` 三方是否都是新值，再按构建键；只改一处必然白费。

### P-45 构建产物 sha 变了对不上时，先确认读的是哪棵树

- **本轮踩坑**：`/tmp/k60build` 是 UniXNU 框架 checkout（不是构建工作目录）；
  真正的构建树是 `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work`。
  我一度对照错误的树得出"sha 全对不上"的错误结论。
- **30 秒判定**：`grep -a 'prepare XNU' /tmp/build-v15.log` 会打印真实 clone 路径；按它判断。

### P-46 hunk 头反复失配 → **已根治：构建前自动重算**

- **症状**：手改补丁正文（加注释、加代码）后忘了同步 `@@ -a,b +c,d @@` 的数字，导致
  `git apply` 报 `corrupt patch at line N` 或编译报 `unterminated conditional directive`（因为
  `git apply` 按头部行数截断，把文件末尾的 `#endif` 丢掉了）。
- **本轮踩坑次数**：至少 4 次（`pong_buttons.c` 149→150、143→147、`bsd_init.c` 6,10→6,12→6,16 等）。
- **根治**：`/mnt/e/k60-work/scratch/fix-patch-hunks.py` 扫描所有 `.patch`，按正文实际行数重算每个
  `@@` 头（含 `-0,0 +1,N` 新文件形式），并已**集成进 `buildv15.sh` 的第 2b 步**——
  每次构建前自动运行，手改正文再也不会弄坏构建。
- **30 秒判定**：任何 `corrupt patch` / `unterminated` 报错，先跑一次
  `python3 E:/k60-work/scratch/fix-patch-hunks.py`，通常直接解决。

### P-47 `if (!PE_parse_boot_argn(...) || !enabled) return;` —— 真正的门控杀手

- **症状**：`enabled=1` 已设、`#if defined(PONG)` 已修、`llvm-nm` 能看到调用，**驱动仍然不运行**。
- **根因**：`PE_parse_boot_argn` 在 boot-arg **不存在时返回 FALSE**，于是
  `!PE_parse_boot_argn(...)` = `true`，`||` 短路，**直接 return**。`enabled=1` 那个默认值**根本没被求值**。
- **修复**：拆成两句——
  ```c
  (void)PE_parse_boot_argn("pong_buttons",&enabled,sizeof(enabled));
  if (!enabled) return;
  ```
- **验证（本机实测，内核 `7f99d2fa`，日志 `usblog-20261109-122746`）**：
  ```
  Pong keys: arbiter v7 channels=768 PON=407 GPIO6=434; power=1 up=1 down=1
  ```
- **30 秒判定**：驱动"条件都满足却仍不跑"时，先看门控那行有没有 `||`——有 `|| !PE_parse_...` 就是它。

### P-48 触摸 `configuration()` 失败的真实报错（终于可见）

- 驱动跑起来后首次拿到真实报错：`Pong touch: missing/incompatible Pong DT; SKIP`
- **含义**：`configuration()` 里 `SecureDTLookupEntry` 或属性读取失败。
- **已确认可用**：ADT nub 已发布（`ArmDTPlatform: published DT nub pong-touch`）、
  ADT 节点属性齐全（`pong-touch@13296`：spi-base/tlmm-base/gcc-base/rsc-base/cmd-db-base/gpio-offset）。
- **下一步排查点**：`configuration()` 里查的**节点路径**是否与 ADT 实际路径一致（`/arm-io/pong-touch` vs 其它）。

### P-49 **触摸修到“能通过 configuration()”反而是灾难：SE 未开时钟时访问会挂死整机**

- **症状**：`configuration()` 断言失败时会打印 `missing/incompatible Pong DT; SKIP` 然后
  **安全返回，系统正常启动**；一旦把断言改对让它通过，`touch_thread` 启动，
  **启动后控制台 0 字节、整机死、自动复位回 fastboot**。
- **根因**：`configuration()` 通过后执行 `touch_thread` → `bring_up()` → `clocks_on()` →
  `geni_spi_init()` → **访问 QUP0 SE4 寄存器**。而 `clocks_on()` 只检查投票（vote）是否写下去，
  不保证 SE 分支真的上了时钟。**对未上时钟的 SE 做寄存器访问会把互连挂住**，
  整机在早期就死掉，连 `K60 USBLOG` 都来不及输出——所以表现为 0 日志。
- **本轮实证（2026-11-09）**：
  - 内核 `7f99d2fa` / `a1494b2a`（断言仍要求 14400×32000 → 失败 → 跳过）：**能启动**，
    日志 60-217 KB，实体键 HID 全通
  - 内核 `8a5595f1` / `fb147b79`（断言放宽/改对 → 通过 → 启动 thread）：**0 日志，整机死**
  - 反复 4 次以上，全部一致
- **修复**：加 boot-arg 门控 `k60_touch_se=1`（**默认关闭**）。`configuration()` 通过后只打印
  已核验的 DT 值（`Pong touch: DT ok (...)`），然后直接返回；只有显式给 boot-arg 才启动
  `touch_thread` 去碰 SE。
- **30 秒判定**：改触摸后如果**启动 0 日志但历史镜像能启动**，立刻回退那个“让 configuration 通过”的改动
  ——不是设备坏，是 SE 访问把互连挂死了。历史镜像对照法见 P-41。

### P-51 `make -j8` 缓冲输出：日志长时间不更新 ≠ 构建卡住

- **症状**：`/tmp/build-v15.log` 的 mtime 停在 16:06:57 长达 4 分钟，看起来像卡死。
- **真相**：XNU 的 `make -r -j8` 把子进程输出**缓冲**到结束才刷，编译实际一直在推进。
  证据：`pgrep -af 'make.*build_all'` 显示 `make -r -j8 -f MakeInc.top build` 在跑，
  且有 3 层 make 嵌套（25800/25854/29329/29330）。
- **判据**：
  ```bash
  pgrep -af 'make.*build_all' | head -2    # 有进程 = 在编译
  ```
  **不要**用 `tail -f` 或日志 mtime 判断进度。
- **30 秒判定**：日志不动时先 `pgrep -af 'make.*build_all'`，有进程就是正常。

### P-52 补丁锚点依赖「全部前序补丁后的真实状态」：不能凭记忆生成

- **症状**：BT 的 `0502-k60-bt-qbt-bsd-init.patch` 在 209 条 series 里 apply 失败，
  报 `patch failed: bsd/kern/bsd_init.c:1337`。
- **根因**：该补丁的锚点假设 `pong_goodix_init()` 在 `k60_usblog_start()` **之后**。
  但实测 201 条系列后，`bsd_init.c` 的真实结构是：
  ```
  1160: extern void pong_goodix_init(void);
  1161: pong_goodix_init();
  1162:     extern void pong_buttons_init(void);
  1163:     pong_buttons_init();
  ...
  1340:     extern void k60_usblog_start(void);
  1341:     k60_usblog_start();
  ```
  **触摸/按键在 1160 行，比 usblog 早 180 行**——与之前假设相反。
- **正确做法**：不要手写锚点。而是：
  1. `git clone --shared` 一份 feed 到 `/tmp/xxx-regen`
  2. 按 series 顺序 apply **到目标补丁的前一条**为止
  3. 在真实文件上做编辑
  4. `diff -u` 生成补丁
  5. `git apply --check` 验证
- **30 秒判定**：补丁在 series 里失败时，先查它依赖的文件在**真实树**里长什么样，
  不要按记忆或旧版本改。

### P-53 补丁插入位置必须在 series **末尾**（不能插在中间）

- **症状**：把 `0334b-k60-autoreset.patch` 插在 `0334` 之后、`0387` 之前，导致
  `0339-k60-xpc-report.patch` apply 失败（`patch failed: bsd/dev/k60_usblog.c:1510`）。
- **根因**：0339/0341 等补丁也改 `k60_usblog.c`，插入的代码改变了上下文。
- **修复**：把新补丁放在 series **最后一条**（第 201/209 条），因为它们是对「全部补丁应用后」
  的状态生成的。
- **30 秒判定**：新补丁 apply 失败且报「后续补丁上下文不符」→ 把它移到 series 末尾。

### P-54 镜像 args 是从 payload 的 `unixnu.toml` 读的，不是从 `packv15.sh` 猜

- **症状**：我一度从 `/mnt/e/.../boot-v15.img` 里 grep `args = "` 读到 10 项 `0x144`，
  以为 args 替换失败。
- **根因**：读到的是**别处的残留字符串**。正确做法是：
  1. `ksize = struct.unpack_from('<I', d, 8)[0]`
  2. `rat = 4096 + ((ksize + 4095) & ~4095)`
  3. `payload = d[rat : rat+201326592]`
  4. `mcopy -n -i payload ::/EFI/UniXNU/unixnu.toml`
  5. 从 toml 里正则取 `args = "..."` 并 `split()`
- **实测对照**：`boot-0461`/`boot-0442` = 972 B / 28 项 / `0x140`；
  `boot-v15`（旧版）= 896 B / 25 项含 `k60_touch_se=1`（危险！）；新安全版 = 490 字符 / 24 项。
- **30 秒判定**：验证镜像 args 一律走 payload 提取，不看 `packv15.sh` 源码推测。

### P-55 `packed_data_ramdisk` 会写 ADT 的 `ephemeral-storage = 1`

- **位置**：`scripts/make-pong-adt.py:146` 与 `:233`
  ```python
  *([('ephemeral-storage', struct.pack('<I', 1))] if args.packed_data_ramdisk else []),
  ...
  [('PackedRAMDisk', bytes(16))] if args.packed_data_ramdisk else []),
  ```
- **含义**：若开启，ADT 会声明 `ephemeral-storage = 1` 并带 `PackedRAMDisk` 占位。
  这**可能意味着 Data 卷来自镜像内嵌 ramdisk，不依赖盘上数据**——对「他人能否复现」是正面因素。
- **待验证**：`board.toml` 当前**未设置** `packed_data_ramdisk`（grep 无命中），
  所以现状是「依赖盘上 Data 卷」。要提升可复现性需要显式开启并验证。
- **30 秒判定**：讨论复现性时先查 `grep -n 'packed_data_ramdisk' board.toml`；
  没有就是依赖盘上。

### P-56 「日志里没有某驱动输出」不等于「驱动没运行」

- **两重原因**：
  1. **printf 时机早于 USB 控制台枚举**：`usblog-20261108-213652` 证明触摸驱动的
     `goodix: clocks stay off` 出现在 `K60 USBLOG: st=2`（USB 未枚举）之前，
     是后续 ring buffer 回放的。
  2. **`bsd_init.c` 里驱动初始化在 1160 行**，早于 `k60_usblog_start()`（1340 行）180 行。
- **所以「0 日志就挂死」的推理链要小心**：可能是
  (a) 真的挂在很早的位置，或
  (b) 挂在 USB 枚举之前但 ring 里其实有内容（只是没回放成功）。
- **判据**：区分方法是在**驱动入口最前面**加一行无条件 printf（`K60T: 1 init entry`），
  然后看上机后这行有没有出现。出现了 → ring 有效，挂死在它之后；没出现 → 挂在更早。
- **30 秒判定**：不要把「日志无输出」当成「代码没执行」，先加最前面的埋点验证。

### P-57 `NativeMetal` 是悬空 submodule 声明（已清理）

- **症状**：`.gitmodules` 声明 `[submodule "drivers/NativeMetal"]`，但
  `git ls-tree HEAD drivers/NativeMetal` **无条目**，目录为空，`git submodule update --init` 报
  `pathspec did not match any file(s) known to git`。
- **根因**：历史遗留，gitlink 从未提交。
- **已处理**：删除 `.gitmodules`（它是唯一条目，删后文件为空 → 一并删除）与空目录。
- **30 秒判定**：`git submodule status` 报错或为空但 `.gitmodules` 有条目 → 检查 gitlink 是否存在。

---

### P-58 音频有**两道门控**，只设一道不会执行，两道都过得挂死

- **症状**：传 `pong_aw882xx=1` 但不传 `pong_audio=1` 时，日志里**完全没有 `AW882xx` 输出**。
- **根因**：调用链有两道独立门控
  ```
  bsd_init.c
    └─ pong_audio_bootstrap()                    [0505 集成]
         ├─ 门控1: PE_parse_boot_argn("pong_audio") || mode == 0 → return 0   ← 卡在这
         └─ aw882xx_bootstrap()                  [0504 内部调用]
              └─ 门控2: pong_aw882xx
                   └─ aw882xx_worker → aw882xx_probe()
  ```
  证据：`0504-k60-audio-pong-audio.patch:870` `if (!PE_parse_boot_argn("pong_audio", &mode, ...) || mode == 0) return 0;`
- **修复**：必须**两个都传**：`pong_audio=1 pong_aw882xx=1`
- **但**：两道都传后（内核 `6419fe95`，26 tokens）**0 日志整机死、自动复位**。
  说明 `aw882xx_probe()` → `aw882xx_bus_init()` 访问 **GENI I2C `0x880000`** 时挂死
  ——与触摸 SE4 是同一类问题（GENI 控制器未正确上时钟/未初始化就访问）。
- **当前状态**：两个 arg 已从 boot-args 移除，回到安全状态（24 tokens / 490 字符）。
- **30 秒判定**：音频无输出先查**两道门控是否都传**；两道都传后 0 日志 → 是 GENI I2C 挂死，不是门控问题。

### P-59 GENI 控制器（SPI SE4 / I2C SE）访问前必须有更强的前置校验

- **两处独立复现**：
  1. **触摸**：`k60_touch_se=1` → `clocks_on()` → `geni_spi_init()` → 0 日志挂死
  2. **音频**：`pong_audio=1 pong_aw882xx=1` → `aw882xx_bus_init()` 访问 GENI I2C `0x880000` → 0 日志挂死
- **共同点**：都是在**首次访问 GENI SE 寄存器**时整机死、零输出。
- **含义**：这不是某一个驱动的 bug，而是 **K60 上 GENI 控制器的访问前置条件我们没满足**。
  可能缺：GDSC 电源域、NoC 路径、SE 时钟真使能、TLMM 引脚复用。
- **官方解法**：`QcomGeniSpi` 组件（`GeniSpi.h:211-212` 明确「caller must know that」SE 时钟已在跑），
  且 sheng 的 `TouchProbe.cpp:399-424` 有完整的前置序列（GPLL0 投票 + 等 lock + 5 分支投票 + 引脚配置）。
- **30 秒判定**：任何 GENI 驱动（SPI/I2C）上机前，必须先确认前置序列完整；
  否则 0 日志挂死，且**无法从日志定位**（因为输出都还没起来）。

### P-60 「120Hz 生效」是错的表述：软件排帧 ≠ 面板切档

- **我之前（以及 `HANDOFF.md`）写成**：「120Hz 生效」「从 60Hz 提升到 120Hz」。
- **准确事实**（subagent `7fe96011` 纠正，证据行号）：
  - 日志 `K60 DISPLAY: TimingElements 1440x3200 at 120 Hz` 确实从 60 变成 120 ✅
  - 但那是 **`0506` patch 让 `refreshHz()` 返回 120** —— **软件层按 120 排帧**
  - `PongDsiPanel.cpp` 只发 `0x11`（sleep out）/`0x29`（display on）/`0x51`（亮度）
    （`:220/228/236`），**没有任何 DSI 切档命令**
  - `grep -rn 'panelHz|dsiSet' drivers/` → **空**（zizhan 有，我们没有）
- **结论**：**面板实际扫描率未验证**。正确表述是：
  > 「软件层按 120Hz 排帧（`refreshHz()`=120），硬件扫描率未验证」
- **要真正验证需要**：
  1. 发 DSI 切档命令（zizhan 有实现可参考）
  2. 或在面板侧测量（示波器 / 面板自报告）
- **30 秒判定**：任何「刷新率提升」的说法，先问「有没有发 DSI 切换命令」；
  没有就是软件排帧，不是硬件切档。

### P-61 subagent 的结论必须交叉验证：本轮的 3 个「前提纠正」

- 本轮 5 个 subagent 中，**3 个推翻了任务书的前提**。这不是 agent 出错，而是**任务书基于过时/错误假设**。

| Subagent | 任务书假设 | 实际 |
|---|---|---|
| `5898cb8e`（OS/电源）| 「DarwinBoot 落后官方 129 行」| 2539/2829 是**字节**；我们 `DarwinBoot.c` **反而多 28 行** |
| `7fe96011`（SMMU/显示）| 「我们有三份自己写的 SMMU」| `pong_goodix.c` **零行 SMMU**；官方 `ArmSmmu4K` **已在用** |
| `7fe96011` | 「K60 没有 GOP」| **有**（`SimpleFbDxe` 编进固件），但不适用的理由不同 |
| `77f4d518`（USB/基带）| 「K60 没有 GLINK/QRTR/SMEM」| **DT 层全在**，缺的是代码 |

- **教训**：
  1. **派任务前必须自己先核实前提**，否则 agent 会花大量时间纠正而非推进
  2. **agent 说「任务前提错误」时，认真对待** —— 本轮 3/5 都是这种情况
  3. 任务书里写「已知 X」时，必须标**证据来源和日期**
- **30 秒判定**：派 agent 前，对每个「已知前提」问一句「证据在哪、什么时候的」。

### P-62 亮度功能完全没暴露给 iOS（发现但未修）

- **事实**：`pong_panel_set_brightness()`（`PongDsiPanel.cpp:247`）**全树 0 调用者**。
- 验证：`grep -rn 'brightness|backlight|IODisplayParameters' iokit/Kernel/MiniIOMobileFramebuffer.cpp` → **0 命中**
- 24 个 selector（`PongDsiPanel.cpp:48-72`）**无亮度**
- **后果**：iOS 里调亮度滑块**不会有任何效果**（屏幕保持 boot-arg 写死的 255）。
- **正确修法**（来自 `AppleARMBacklight` 的 **OS 契约**，不是它的硬件层）：
  - 但**必须避开两个已记录的坑**：
    - `AppleARMBacklight.cpp:350-355` **int-236**：只发 `backlight-control` 不满足类一致性 → **屏幕停止更新**
    - `:11-12` **int-229**：重名 → **panic**
  - 所以 `backlight-proposed.patch` **刻意不发布** `backlight-control`，
    只加 `k60_panel_brightness=0..255` boot-arg（默认 255 不变）作为安全调试旋钮
- **30 秒判定**：讨论「屏幕亮度」前先确认面板 IC 类型；
  K60 是 **DCS**（`PongDsiPanel.cpp:6-7`），不是 I2C 背光 IC（sheng 是 KTZ8866×2）。

### P-63 **所有「0 日志挂死」的真正根因：`io_submap` 只有 8 MiB，`ml_io_map` 满了会 panic**

- **铁证**（真机 panic，`evidence/usblog-20261108-192302/console.log`）：
  ```
  K60PANICFMT caller=0xfffffff007a5365c fmt=kmem_%s(%p, %zd, 0x%x): failed with %d @%s:%d
  kmem_alloc(0xfffffff16796ab00, 458752, 0x100021): failed with 3 @vm_kern.c:178
  K60PANIC: ring kept; restart reason -> bootloader
  ```
  `458752 = 0x70000` = `GCC_SIZE`；`failed with 3` = `KERN_NO_SPACE`。

- **因果链**（全部有源码依据）：
  1. `pong_goodix.c` 的 `touch_thread` 一次要 4 个窗口：
     `TLMM 0x200000(2 MiB)` + `GCC 0x70000(448 KiB)` + `SE 0x4000` + `cmd_db 0x20000` ≈ **2.56 MiB**
  2. `osfmk/arm/io_map.c:65`：`#define IO_MAP_SIZE (8ul << 20)` —— **全内核共享 8 MiB**
  3. `io_map.c:128`：`kmem_alloc(io_submap, ..., KMA_NOFAIL)` —— **忽略返回值**
  4. 满了 → `KERN_NO_SPACE` → `KMA_NOFAIL` → `__kmem_failed_panic`（`vm_kern.c:1002`）
  5. **panic 发生在 `clocks_on()` 之前、`geni_spi_init()` 之前**

- **这解释了本轮所有现象**：
  | 现象 | 真实原因 |
  |---|---|
  | `k60_touch_se=0` 系统正常 | 线程不启动，不申请窗口 |
  | `k60_touch_se=1` 0 日志 | **`ml_io_map` 就 panic 了，比任何寄存器访问都早** |
  | `pong_audio=1 pong_aw882xx=1` 0 日志 | 同样原因（音频另有 4 处 `ml_io_map`）|
  | 前 3 轮所有寄存器级修复无效 | **根本没走到寄存器** |

- **共享 8 MiB 的还有**：`0300-k60-usblog-ep0.patch`（10 处）、`0334`（7 处）、
  `0402`（8 处）、`0500`（4 处）、`0503`（4 处）、`0504`（5 处）等。

- **修复**（保守版，只动 TLMM）：
  ```c
  // 原来：TLMM_SIZE = 0x200000 (2 MiB)
  // 改为：TLMM_SIZE = 0x10000 (64 KiB)，并把基址 rebase 到 gpio_offset
  tlmm = ml_io_map(TLMM_PHYS + gpio_offset, TLMM_SIZE) - gpio_offset;
  ```
  省下 **1.94 MiB**。`GPIO_CFG(n) = tlmm + gpio_offset + 0x1000*n` 计算不变。

- **为什么不缩 GCC**：GCC 偏移分布 `0x0~0x27580` + `0x33000` + `0x62018`，
  **跨度 0x70000 无法用单窗口缩小**。缩它需要拆成 2 个窗口（`0x0~0x2000` 和 `0x12000~0x14000`），
  改动面大、风险高。优先缩 TLMM（省 1.94 MiB，零语义变化）。

- **30 秒判定**：任何驱动加 `ml_io_map` 前，先算总预算。
  **累计接近 8 MiB 时必然 panic，且表现为「0 日志挂死」，会被误判成寄存器访问问题。**
  查法：`grep -c ml_io_map` 各补丁 + 手动累加 SIZE。

### P-64 缩小 MMIO 窗口时**必须覆盖最大引脚偏移**：TLMM 64 KiB 让 pin 20 越界

- **现象**：P-63 把 `TLMM_SIZE` 从 2 MiB 缩到 64 KiB 后，`k60_touch_se=2`
  走到 `bring_up()` 的 GPIO 时 **kernel data abort**：
  ```
  K60KEXC msg=Kernel data abort. pc=0xfffffff00774e78c ... esr=0x96000010
          far=0xfffffff8c6f4a004
  x9:  0xfffffff8c6f4a000   x10: 0x0000000000000002
  Pong touch: DIAG mapped tlmm=0xfffffff8c6f4a000 ... (rebase 前)
  ```
  `x10=2` 正是 `gpio_set(pin, true)` 写的值（GPIO_IO 的 bit1 = 输出高）。

- **根因**：TLMM 的访问偏移是 `gpio_offset + 0x1000*n`。
  K60 触摸引脚 `pins[] = {16,17,18,19,21,20}`，**最大 n = 21** →
  需要到 `0x15000 + 4 = 0x15004`。而 64 KiB 窗口只到 `0x10000`
  → **pin 20 的 `GPIO_IO(20) = 0x14004` 落在窗口外** → data abort。

- **精确复算**：
  ```
  mapped_base = tlmm + gpio_offset = 0xfffffff8c6f36000
  窗口范围     = [0xfffffff8c6f36000, +0x10000) 即上界 0xfffffff8c6f46000
  GPIO_IO(20) = reported_tlmm + 0x100000 + 0x1000*20 + 4
              = 0xfffffff8c6e36000 + 0x24004 = 0xfffffff8c6f4a004
  超出窗口 0x4004 字节
  ```

- **修复**：`TLMM_SIZE` 64 KiB → **128 KiB（0x20000）**。
  覆盖 `0x15004`（pin 21）且有 0xAFB4 余量；仍比原 2 MiB 小 **16 倍**。

- **通用教训（比这个 bug 更重要）**：
  **缩 MMIO 窗口前，必须枚举该窗口内所有访问偏移并取最大值。**
  公式：`需要的大小 = max(offset) + access_width`，不是「看起来够用」。
  ```bash
  # 检查方法：列出所有访问偏移
  grep -oE '(tlmm|gcc|se) \+ 0x[0-9a-f]+' <文件> | sort -t+ -k2 -u
  ```

- **30 秒判定**：data abort 的 `far` 值减去映射基址，就是**越界的偏移**。
  对着它找是哪个 `#define X(n)` 算出来的。

### P-65 **GENI 时钟链真正断点：`CMD_ROOT_OFF`（bit31）关闭，不是 DFS_EN**

- **排查过程（两次搞错寄存器，都记下来）**：
  1. 先以为 `DFS_EN` 在 `CMD` 寄存器 → 写 `CMD |= 1` → `cmd` 读回仍是 `0x80000000`，无效
  2. 才发现 Linux 定义（`clk-rcg2.c:24-31`）：
     ```c
     #define CMD_REG          0x0
     #define CMD_UPDATE       BIT(0)      ← CMD bit0 是"提交配置"，不是 DFS_EN
     #define CMD_ROOT_OFF     BIT(31)     ← CMD bit31 = root 关闭
     #define SE_CMD_DFSR_OFFSET 0x14
     #define SE_CMD_DFS_EN    BIT(0)      ← DFS_EN 在 DFSR，不在 CMD
     ```
  3. 我们的 `dfsr = 0x21` → **bit0 早就是 1，DFS 一直是使能的**

- **真正根因**：`cmd = 0x80000000` → **`CMD_ROOT_OFF` bit31 = 1**
  Linux `clk-rcg2.c:74`：
  ```c
  return (cmd & CMD_ROOT_OFF) == 0;   // bit31=1 → root 关闭 → 不出时钟
  ```
  **RCG root 被关掉时，任何频率配置（DFS 或普通）都不产生时钟。**

- **实证（关键突破）**：
  ```
  DFSEN post cmd=0x80000000 cbcr=0x80004220   ← 写 CMD 后 cbcr 短暂变 ON（bit31=1）
  CLKPROOF se4_cbcr=0x4220                     ← 但随后又变回 OFF
  ```
  `cbcr` 能变 `0x80004220` 说明**时钟硬件本身可用**，只是没被正确保持。

- **修复**：
  ```c
  /* 1. 清 CMD_ROOT_OFF */
  wr(GCC_QUP0_SE4_CMD, rd(GCC_QUP0_SE4_CMD) & ~(1u << 31));
  /* 2. 提交（CMD_UPDATE）*/
  wr(GCC_QUP0_SE4_CMD, rd(GCC_QUP0_SE4_CMD) | 1u);
  for (500 次) { 等 bit0 清零 }
  ```

- **通用教训**：
  **改 RCG 前先读 `CMD` 寄存器判断 root 是否开着。** `cmd & BIT(31)` = 0 才继续。
  这比查频率表、divider、DFS 档位都更优先。

- **30 秒判定**：时钟不输出时，第一步读 `CMD` 看 bit31；若为 1，先清它，
  再谈频率配置。顺序错了会在错误的寄存器上浪费多轮。

### P-66 **`CMD_ROOT_OFF` 写不进去：RCG root 由硬件授权控制，软件无法强制开启**

- **实测（`evidence/usblog-20261109-190657`，内核 `09b0d5d0`）**：
  ```
  ROOT_ON pre  cmd=0x80000000 cbcr=0x80004220
  ROOT_ON post cmd=0x80000000 cbcr=0x80004220     ← 写完 cmd 完全没变
  CLKPROOF se4_cbcr=0x4220                        ← 之后又变了
  ```

- **事实 1：`CMD` bit31（`CMD_ROOT_OFF`）写不进去**
  写 `wr(cmd, rd(cmd) & ~(1u<<31))` 后回读仍是 `0x80000000`。
  → **这是只读状态位**，root 使能由硬件/固件授权，不由软件写 CMD 控制。

- **事实 2：CBCR bit31 语义确认为 CLK_OFF=1**
  | 值 | bit31 | 含义 |
  |---|---|---|
  | `0x80004220` | 1 | **OFF** |
  | `0x4220` | 0 | **未 OFF** |

  **注意**：我此前一度把 `0x80004220` 当成"ON"，方向读反了，已更正。

- **事实 3：时钟状态在两次读取之间翻转**
  `clocks_on()` 期间是 `0x80004220`(OFF)，到 `geni_transfer()` 时是 `0x4220`(未 OFF)。
  说明有其它机制（HWCG 门控 / GCC 投票 / 电源域）在动态控制。

- **结论**：**RCG root 的使能不归 XNU 软件控制。**
  要真正打开 SE4 时钟，需要：
  1. **RPMh/RSC 投票**（我们禁止访问，HR-01）
  2. 或 **GDSC/电源域**（QUP 无 GDSC，见 P-63 附注）
  3. 或 **依赖 ABL 在 Android 启动时已打开**（需验证 Android 侧时钟状态）

- **这条对触摸修复的意义**：
  即使 GENI 全部寄存器配置正确、FIFO 逃生开了、DFS 档位选对了，
  **只要 SE4 的 RCG root 没被授权，SPI 传输就永远不完成**。
  这是**架构级阻塞**，不是驱动 bug。

- **30 秒判定**：写 `CMD` 后回读不变 → 该位只读。
  不要继续在 CMD/CBCR 上试写，转去查授权路径（RPMh / 电源域 / 固件）。
### P-67 **时钟其实一直在运行：`cbcr=0x4220` 的 bit31=0 就是"未关闭"**

- **我连续两轮把 CBCR 语义读反了**，这里一次性纠正：

  | `CLOCK_OFF = (1u<<31)` | 含义 |
  |---|---|
  | `0x80004220` | **bit31=1 → 时钟 OFF** |
  | **`0x4220`** | **bit31=0 → 时钟在运行（未关闭）** |

- **实测时间线（`evidence/usblog-20261109-190657`，内核 `09b0d5d0`）**：
  ```
  clocks_on() 期间:  se4_cbcr = 0x80004220   ← OFF
  geni_transfer() 时: CLKPROOF se4_cbcr = 0x4220   ← 未 OFF = 运行中
  ```
  **时钟在 `clocks_on()` 之后自己打开了**（很可能是 `wr(GCC_QUP0_SE4_CFG...)` 或 GENI 访问唤醒的）。

- **因此**：
  - ❌ "SE4 时钟没运行" —— **错误**
  - ❌ "需要清 `CMD_ROOT_OFF`" —— **错误**（该位只读，且时钟已开）
  - ❌ "这是架构级阻塞" —— **错误**

- **真正的阻塞点回到 GENI 引擎**：
  ```
  GENI pre  status=0 clk_cfg=0x51 trans_cfg=0 word_len=0x4   ← 配置全对
  GENI cmd0 readback=0x18000000                              ← 命令被接受
  SPI transfer: status=0, sent=36, received=0                ← 但永不完成
  ```
  `status & M_CMD_DONE` 从未置位 → `M_CMD_DONE` 不是 bit0！

- **下一步必须验证**：`GENI_M_IRQ_STATUS`（`se+0x610`）的 `M_CMD_DONE` 位定义
  是否与我们对 `status` 的解读一致。我们用的 `M_CMD_DONE = (1u<<0)`，
  但 `status=0x41` 的 bit0=1 却没被识别为 DONE —— **说明位定义可能错**。

- **30 秒判定**：判断时钟是否在跑，只看 `cbcr & (1u<<31)`。
  **bit31=0 = 在跑**。不要再看 bit30（那不是 ON 标志）或其他位。
### P-69 **阶段门控的插入位置必须在"危险调用之前"，不是之后**

- **症状**：新加的 `k60_touch_se=7`（本意是"只走 bitbang，不碰 GENI/RPMh"）
  上机后 **0 日志整机死**（`evidence/usblog-20261109-192255`，0 B）。

- **根因**：门控插在了 `io_supply_on()` **之后**：
  ```c
  if (!problem) {
      spi_transfer=geni_transfer;
      if (goodix_probe(false)) return true;
      if (touch_stage < 6) return false;      // stage 5 停在这
      if (io_supply_on()) { ... }             // ← stage 7 也会执行！
  }
  ...
  if (touch_stage < 7) return false;          // ← 门控在这里，太晚了
  spi_transfer = bitbang_transfer;
  ```
  `touch_stage=7` 时 `7 < 6` 为假 → 继续执行 `io_supply_on()`
  → `rpmh_write()` → `wr(TCS(rsc+0xd00))` 且 `rsc=0` → **非法地址 data abort**。

- **修复（两处）**：
  1. `if (touch_stage == 6 && io_supply_on())` —— 只有 stage 6 允许碰 RPMh
  2. bitbang 循环里的 `if (attempt==0 && touch_stage == 6 && io_supply_on())`
  3. **并在 `bring_up()` 最前面**加 `if (touch_stage >= 7) goto bitbang_only;`
     —— 让 stage 7 完全跳过 `clocks_on()` / `geni_spi_init()` / 200ms 失败传输

- **通用教训**：
  **给新阶段加门控时，必须确认它在整条调用链上位于所有危险调用之前。**
  只在一个位置加 `if (stage < N) return` 是不够的 —— 如果中途还有别的
  `if (stage < M)`（M < N）分支，新阶段会从那些分支"漏"过去。

- **检查方法**：加新阶段后，`grep -n 'touch_stage'` 全文列出所有门控点，
  按执行顺序逐个确认新阶段会走哪条路。

- **30 秒判定**：新 stage 一上机就 0 日志 → 先查它是否漏过了某个危险调用，
  而不是怀疑新功能本身。

### P-70 **K60 触摸 SPI 引脚角色：MISO 是 GPIO 17，不是 16**

- **背景**：FDT 的 `qupv3_se4_spi_active` 只给出引脚**集合**
  `pins = "gpio16\0gpio17\0gpio18\0gpio19"`（function `qup4`），
  **没有说明**哪个是 MISO / MOSI / CLK / CS。

- **我们原来的假设（来自 pong 参考实现，从未核对）**：
  `MISO=16, MOSI=17, CLK=18, CS=19`

- **实测（24 种排列一次扫描，`evidence/usblog-20261109-195627`，内核 `7bfc16a4`）**：
  ```
  PERM0  miso=16 mosi=17 clk=18 cs=19  -> 00 00 00 00
  PERM7  miso=17 mosi=16 clk=19 cs=18  -> ff ff ff ff   ★
  PERM8  miso=17 mosi=18 clk=16 cs=19  -> ff ff ff ff   ★
  其余 22 种                            -> 00 00 00 00
  ```
  **两个 `ff` 的共同点是 `miso=17`** → **MISO 实际在 GPIO 17**。

- **`ff ff ff ff` 的意义**：MISO 被拉高。SPI 空闲态（CS 未选中或芯片未驱动）
  通常是**高电平**，说明这条线**终于连到芯片侧**了；而 `00` 说明那条线根本不是 MISO
  （悬空被拉低或接错）。

- **修正**：`pins[]` 的 MISO/MOSI 位置需要交换：
  ```c
  // 原（错）：MISO=pins[0]=16, MOSI=pins[1]=17
  // 新（对）：MISO=pins[1]=17, MOSI=pins[0]=16
  ```
  剩余 CLK/CS 还需在 `miso=17` 的 6 种组合里确认（PERM6 `mosi=16 clk=18 cs=19`
  最符合 Qualcomm 标准顺序）。

- **通用教训**：
  **FDT 的 pinctrl `pins` 属性只保证"这四根线属于这个 SE"，不保证顺序。**
  在写 bitbang 或手搓 SPI 前，必须用排列扫描（24 种）实测确定角色，
  不能从别的板子照抄。一次扫描就能省掉多轮猜测。

- **30 秒判定**：bitbang 读全 `00` → MISO 选错；读全 `ff` → MISO 大概率对了，
  但芯片没响应（需查 CS/CLK 或供电）。

### P-71 **Android v4 的 header_size 不是 kernel 起点**

- **症状**：cand12 的 `fastboot boot` 返回 OKAY，但没有 CDC 控制台，随后回到 fastboot；`console-20261112-094738.json` 记录 0 字节。
- **根因**：重打包脚本把偏移 20 的 `header_size=1584` 当成数据起点。v4 的头结构长 1584，整页长 4096；kernel 必须从 4096 开始，ramdisk 必须从 `4096 + align4096(kernel_size)` 开始。本次 ramdisk 被放到 550448，而正确地址是 552960，覆盖了 UEFI gzip 尾部。
- **证据**：cand7 的固件流可解压到 EOF，后接 1866 字节 FDT；cand12 的同一流报 `incorrect data check`。cand12 位于错误偏移的 FAT 与当前 `payload.img` 逐字节相同，SHA256 `49b60bcbc51307ff449e24e72e1c76dd12621c3ff8d156ebceac4a3d9a126a95`，无需回退内核功能。
- **修复**：使用已存在的 `scripts/build-bootimg.py:29-47` 布局；重打包工具迁入 `scripts/repack-boot.py`，保留完整 4096 字节头页，按页对齐 kernel/ramdisk，并在写出前验证固件 gzip 和附加 FDT。
- **检查**：`python3 scripts/test-repack-boot.py` 覆盖真实偏移下的固件解压、跨页载荷、固件 CRC 损坏及签名区截断。重建命令：`python3 scripts/repack-boot.py --template /root/k60/work/touch-gpu/gpu8-start.img --ramdisk /root/k60/work/out-cand/mondrian/ipados-16.6.1-20G81/mondrian/payload/payload.img --output /mnt/e/k60-ios/boot-cand13-20261112.img`。
- **30 秒判定**：有 `ANDROID!` 不等于镜像可启动；从 **4096** 取 kernel 区域，用 `zlib.decompressobj(31)` 检查 EOF 和附加 FDT。不要只在整包里搜索诊断字符串。

### P-72 **UFS Data 后端不能被 payload 门禁强制挂 RAM seed**

- **症状**：修正 v4 偏移后的 cand13 仍无 CDC 日志并回到 fastboot（`console-20261112-100518.json`）。实际 `unixnu.toml` 比可用 cand7 多了 `initrd = "Payloads/scratch-data.img"`。
- **确定的不一致**：`configs/mondrian_defconfig` 选择 `XNU_OWNER_DATA_UFS=y`、`XNU_NATIVE_RAM_BLOCK=n`；`pong-ufs-data.patch` 明确从已安装的 UFS IOMedia 挂 Data，不使用 seed mapping 或 RAM fallback。旧 `core/scripts/unixnu/payload.py:41-53` 却要求所有 OWNER_DATA_MOUNT 内核提供 RAM seed，导致打包命令恢复了已知不可用的 RAM Data 路径。
- **修复**：payload 按所选后端决定 seed 前提：UFS Data 不需要 seed，传 seed 则报冲突；内存 Data 保持原始 seed 要求。只重建 payload，无需回退当前触摸、显示、电池或重编内核。
- **检查**：`python3 core/scripts/test-payload-data.py`；构建 `./core/unixnu payload -D work/device-ui --out work/out-cand`，确认无 `initrd`、无 `scratch-data.img`、ADT 无 RAMDisk，同时保留 `/arm-io/pong-touch`。
- **边界**：cand13 的零日志不能单独证明 RAM seed 是第二次复位的唯一原因；以去掉冲突后的实机结果判定。

### P-73 **共享 ADT 转换不能漏掉已工作的 CPU/UFS 合同**

- **症状**：cand14 仍在 CDC 枚举前复位（`console-20261112-101525.json`）。语义对比 cand7 与实际 cand14 ADT，除新触摸节点外，还少了 `/cpus/max_cpus`、8 个 `cpu-id` 和 9 个 UFS `pong,*` 属性。
- **根因**：`core/scripts/unixnu/devicetree.py` CPU 生成仅输出 `reg`，缺少逻辑 CPU ID；`hardware_properties` 的类型集合也未包含 DTS 已有的 UFS 属性。`drivers/NativeUfs/NativeUfs.cpp:155-178` 在首个 MMIO 前逐一验证这些属性，缺失就拒绝启动。
- **修复**：生成从零开始连续的逻辑 `cpu-id` 和启用 CPU 总数，保留原 MPIDR；把已有 UFS 绝对窗口按 u64、stream/IRQ/计数按 u32 转小端。没有改硬件地址，没有绕过驱动验证。
- **检查**：`python3 core/scripts/test-devicetree-handoff.py` 覆盖禁用 CPU 导致的逻辑编号间隙、物理 affinity 保持、UFS 窗口宽度与字节序。新载荷必须与 cand7 的 CPU/UFS 合同一致，同时保留新触摸节点。
- **边界**：这些是确定的合同缺失；是否解释所有前控制台复位，以修复后实机结果判定。

### P-74 **启动演示用 delayed unlock 不能成为正常锁屏行为**

- **症状**：cand15 已恢复桌面，用户指出应先出现锁屏而非直接进桌面。
- **根因**：`userland/ui_compat.c` 的 10 秒延迟 callback 主动调用 `SBLockScreenManager unlockUIFromSource:withOptions:` source24；这是缺输入时展示桌面的 workaround，不是原生锁屏流程。
- **修复**：保留主队列上的渲染偏好与 screen-on，删除自动 unlock，局部函数改为 `present_initial_screen` / `start_ui_presentation`，正常本地认证路径不变。已重生成实际 0340 嵌入库（95824B，SHA256 `85f2431d238e7b6250483d69c2fddb11e9d63cf5c9c01c2a192ec54ec896b82a`，4KiB 签名通过）。
- **检查**：启动后保留原生锁屏；只有真实用户输入才能进入解锁路径。触摸缺失不能用自动解锁掩盖；最终以屏幕及状态转换判定。

### P-75 **壁纸目录可见不等于原生壁纸已选中**

- **症状**：cand16 原生锁屏已出现，但用户确认壁纸全黑；stock-wallpaper bind 和 aliases=4 均成功。
- **确定的不一致**：20G81 原始素材只有 iPad 目录，默认目录按设备名和精确 logicalScreenClass 筛选，当前 phone 界面无法自动命中。成功挂载仅证明素材可见。
- **修复**：在原生主队列初始亮屏后，保留已有图片/颜色/动态壁纸，仅对确认为空的配置选择完整的真实 7410 WWDC 2022 bundle。使用原始 `WKWallpaperBundle initWithURL:` 和 `WKSystemShellWallpaperManager setLockScreenWallpaperRepresenting:mirrorToHomeScreen:completion:`，不改文件名、筛选谓词或认证状态。
- **调试证据**：`kern.pong_diagnostic` 现复用于 SpringBoard/backboard，输出实际 homeButtonType、现有内容、HEIC 文件验证与原生提交。setter completion ABI 是 void()，回调返回不能当成像素成功。源码/API/真实资产依据记录在 `work/touch-gpu/wallpaper-native20G81.json`。
- **检查**：下一版必须实际显示素材；`existing-content=-1`、文件缺失或 ABI 不符都明确报未实现前提，不伪造成功。COM8 已实测收到 13300 字节并返回 help；这是 CDC 诊断通道，不是 LLDB/Apple usbmux。
- **cand18 实证**：`console-20261112-115737.log` 78716B，真实 `K60UI` 日志显示 `locked=1 homeButtonType=2`、`existing-content=1`，因此原生设置未提交。`k60_wallpaper_reset=1` 仅供本次恢复镜像显式重新选择真实 stock；默认不替换已有内容。新日志列出 lock/home 配置属性与对象类，既不把已有配置当作像素证明，也不把 callback 返回当成功。

## 台账维护规则

1. 新坑确认后**当场追加**（与 ISSUES 同步，不等收尾）。
2. 「30 秒判定」必须写成一个可立即执行的动作或一条否决规则，不写空泛口号。
3. 证据栏必须有实物：文件+行号、日志路径、sha、commit。没有的标「待验证」。

---

## 台账编号已知问题（2026-11-09 审计）

| 问题 | 说明 | 处理 |
|---|---|---|
| P-22 出现两次 | 第二条是「P-22 更正」，属合理的更正记录 | 保留 |
| P-25 缺失 | 编号跳过，可能早期被合并/删除 | 保留空缺，不重排（重排会破坏所有外部引用）|
| P-01~P-09 零补位 | 早期用 `P-01` 格式，后期用 `P-10+` | 无需处理，grep 时两种都要匹配 |

**维护规则补充**：新条目继续用 `P-NN`（两位数），**不要重排历史编号**——所有文档、
commit message、issue 回复里都有 `P-NN` 引用。
