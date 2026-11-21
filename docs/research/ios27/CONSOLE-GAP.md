instrument: ramoops console mirror at 0xA7000000 + firmware reader
lifetime: 只在**同一次上电周期内**存在。ramoops 落在 DRAM，长按电源或复位后 DRAM 归零，内容必然丢失（P-307；该事实 2026-10-30 已记进 `docs/archive/PROGRESS-2026-10-30-PM.md` §三）。
read_moment: 只有两种合法读法——① 同一次启动内由内核自己读回来（本内核尚未实现）；② 设备**未断电**地 warm reset 后由固件 DXE 读（`RamoopsDumpDxe`，`uefi-mondrian` c52a080）。跨 Android 重启、跨长按电源一律读不到。
writer: 内核 `pong_ramoops_console_write()`（`patches/xnu-12377/0546-k60-ramoops-console-27.patch` 装进 `console_write()` / `console_write_unbuffered()`），写到物理 `0xA7000000` 起的 2 MiB 环形缓冲，12 字节头 `{sig,start,size}`，`sig = 0x43474244`。
loss_condition: 掉电、长按电源、固件在启动时重新训练/清 DRAM、以及任何复位都会清空；此外内核若从未走到 `pong_ramoops_console_init()`，头部根本不会被写，读数器看到的是「空窗口」。

# 27 内核没有控制台：两次 0 字节飞行的真实含义

日期：2026-11-21
证据命令都在下面，数字来自当前盘上的两个内核。

## 一句话

27 内核里**没有任何把文字送到 USB 串口的代码**。所以那两次 `fastboot boot` 得到 0 字节，不能用来判断内核有没有跑起来——镜像在构建时就注定了不会出字。

## 实测

```
$ llvm-nm-18 --defined-only <kernel> | grep -oE '_(pong|k60)_[a-z0-9_]*(console|serial)[a-z0-9_]*'
== ipados-16.6.1-20G81 (cellular-k49)
_k60_console_export_sysctl
_k60_serial_clock
_k60_usblog_console_up
_pong_ramoops_console_init
_pong_ramoops_console_write
== ios-27.0.1-24A446 (ios27-out)
_k60_serial_clock
```

17 条控制台/串口符号里 27 只剩一个 `_k60_serial_clock`（时钟，不是输出通道）。`pong_ramoops*` 也不在，所以连「panic 前的最后一屏」这条后路也没有。

## 它们本来是哪些补丁带来的

| 补丁 | 作用 | 27 series 里有吗 |
| --- | --- | --- |
| `patches/xnu/0243-k60-console-export.patch` | `k60_console_export` sysctl + `k60_usblog_console_up()` 状态机 | 无 |
| `patches/xnu/0300-k60-usblog-ep0.patch` | EP0 上的 USB 日志通道（真正把字节推出去的那一层） | 无 |
| `patches/xnu/0306-k60-console-snapshot.patch` | 控制台快照（重放最后一屏） | 无 |
| `patches/xnu/0331-k60-prevlog-replay.patch` | 上一次启动的残留日志重放 | 无 |
| `patches/xnu/0232-k60-pong-adreno-ramoops-bridge.patch` | `pong_ramoops_console_init/write` | 无 |

`patches/xnu-12377/series` 共 33 条，`grep -E 'console|usb'` 只命中 `0543-k60-ios27-panel-console.patch` 与 `0544-k60-console-font-scale.patch`——**它们在屏上画字，不在串口上出字**。两者不是同一件事：`0543` 解决「内核能动之后屏幕上看得见」，`0300` 解决「我们这边收得到」。

## 由此被推翻的结论

- 「设备静默挂死、需要人工复位」——挂死是真的（两次都没回 fastboot），但**它不是从日志推出来的**，是从「设备不枚举」推出来的；0 字节本身不构成内核没跑的证据。`F2-PREDICTION.md` 里 INVALID 的定义仍然成立，只是原因换了：不是「跑了但 gadget 没枚举」，而是「构建里没有 gadget 这一层」。
- 「prelink 的 203 个桩在 console 之前可达性为 0，所以可以飞」——这个论证的方向仍然对，但它依赖「console 会起来」；console 根本不在这颗内核里，所以那次飞行不可能验证它。

## 下一步（按顺序，都可离线验）

1. 把 `0243` + `0300` 移植到 `patches/xnu-12377/series`，判据是重编后 27 内核 `llvm-nm` 里出现 `_k60_usblog_console_up`，且 16 线内核符号集不变。
2. 移植前先确认这两条补丁在 12377 上的依赖面：它们碰 `iokit/` 与 `osfmk/` 的哪些文件，是否与已落的 `0540/0541/0542` 重叠。
3. 只有第 1 条绿了，`fastboot boot` 的 0 字节才重新成为「有信息量的 0 字节」；在那之前任何飞行都是盲飞（铁则 8）。

## 纪律

- 不许用「屏幕上有字」代替「串口有字」：两者的失败面不同（面板控制台在 `0543`，串口在 `0300`）。
- 不许把这次发现写成「内核没跑」——它只说明**我们听不到**，说明不了它有没有说话。

## 移植顺序（实测过依赖，不是猜的）

在干净 12377 树（`/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc`）上逐条 `git apply --check`：

| 补丁 | 触碰 | 干净树上 |
| --- | --- | --- |
| `0232` ramoops bridge | `osfmk/arm/arm_init.c` | 需要重切（它扩的是 16 树里已有的 `pong_ramoops_*` 块） |
| `0243` console export | `bsd/conf/files`、`bsd/dev/k60_console_export.c`、`osfmk/arm/arm_init.c`、`osfmk/arm64/pong_ramoops_console.h` | 整条拒收；**它改的是 `0232` 加进来的 `pong_ramoops_console_write()`**（hunk `@@ -117,8 +119,12 @@` 把 `__atomic_exchange_n` 换成计数版） |
| `0300` usblog EP0 | `bsd/conf/files`、`bsd/dev/k60_usblog.c`、`osfmk/arm/arm_init.c`、`bsd/kern/bsd_init.c` | **新增文件 `bsd/dev/k60_usblog.c` 单独 apply 成功**；四处锚点全要重切 |

结论：这是一条**链**，不是三条独立补丁——`0232` 建 ramoops 底座，`0243` 在底座上加导出与总量/丢弃计数，`0300` 在其上把字节推上 EP0。按 0243、0300 的顺序单独移植会得到两个「能编但没人调用」的模块，症状仍是 0 字节，而且更难查（与 P-190 同形：归档链接了、符号在、代码从没跑）。

三条锚点的重切面：
1. `bsd/conf/files` —— 16 线用 `pong_buttons.c`/`unix_startup.c` 附近的锚，27 侧必须换成 `bsd/dev/unix_startup.c` 那一族（`append-conffiles.py` 的 27 模式已经在处理同类问题）。
2. `osfmk/arm/arm_init.c` —— 0243 的 hunk 上下文是 16 树里 `pong_ramoops_diagnostic_write()` 之上的块；12377 没有这个块，要先落 0232 并把底座切到 `arm_init()` 里合适的初始化点（`arm_vm_init` 之后、`PE_init_iokit` 之前）。
3. `bsd/kern/bsd_init.c` —— 0300 要在 `bsd_init()` 的 console worker 启动处挂钩；27 的 `bsd_init.c` 已因 `0531`（audio 调用点）改过一行，重切时必须落在同一文件的不同位置，顺序上先 `0531` 再 `0300`，否则 0531 的 `-U1` 锚点会被挤动。

判据（缺一不可）：
- 重编后 27 内核 `llvm-nm --defined-only | grep -c '_k60_usblog_console_up\|_k60_console_export_sysctl\|_pong_ramoops_console_write'` = **3**；
- `bsd/conf/files` 里三个条目各出现一次；
- 16 线内核的符号集**不变**（回归：同一份 16 树重建后 5 个符号仍在）；
- 只有前三条都绿，才允许把「0 字节」重新当成有信息量的观测。

## 真正的第一块砖不是 0232，而是 `zzzzz-pong-ramoops-minimal`

依赖是四层，前一层不在 27 里，后三层就不可能起：

| 顺序 | 补丁 | 在 27 series | 干净 12377 树上 |
| --- | --- | --- | --- |
| 1 | `zzzzz-pong-ramoops-minimal.patch` | 无 | `osfmk/console/serial_console.c:509` 拒收；`arm_init.c`、`osfmk/arm64/pong_ramoops_console.h` 两处新增文件没问题 |
| 2 | `0232` diagnostic bridge | 无 | 依赖 1 的 `pong_ramoops_*` 变量 |
| 3 | `0243` console export | 无 | 改的是 2 加进来的 `pong_ramoops_console_write()` |
| 4 | `0300` usblog EP0 | 无 | 只有新增文件 `bsd/dev/k60_usblog.c` 能单独落地 |

### 但第一块砖目前**编不进去**，原因和 0532 是同一个

`zzzzz-pong-ramoops-minimal.patch` 在 `serial_console.c` 里加的三个钩子全部包在

```c
#if defined(PONG) && defined(XNU_PONG_RAMOOPS_CONSOLE) && XNU_PONG_RAMOOPS_CONSOLE
```

而 27 的机器配置是 `BCM2837`，`-DPONG` 在构建命令里出现 **0 次**（`0532` 当初就是栽在这里：`#if defined(PONG)` 的守卫让定义永远不生成）。所以即使把这三处钩子原样搬过去、`git apply` 全绿，**它们也会被预处理器整段删掉**，症状与完全没打补丁一样：0 字节。

移植时必须做两件事，缺一不可：

1. **改键**：`defined(PONG)` 换成 27 侧真实存在的键（建议 `XNU_PONG_RAMOOPS_CONSOLE` 单独作开关，由构建传 `-D`，与 `PongAudioAmp.o_CFLAGS_ADD` 那条已跑通的通道同形），并在 `scripts/build-ios27-linux.sh` 里接线；
2. **重切锚点**：`serial_console.c:509` 的上下文在 12377 里已变，`console_write()` / `console_write_unbuffered()` 两个函数体是稳定的，锚点应落在函数定义行而不是上面的注释块。

判据也要加一条，否则第一件事无法验证：**重编后 `llvm-nm` 里 `_pong_ramoops_console_write` 出现 1 次，且 `strings kernel.macho | grep -c pong-ramoops` 非 0**——只看「符号在」不够，`0532` 那次符号在而代码从未执行，教训是「符号在 ≠ 代码跑」，所以再加一条**运行期**判据：串口日志里必须出现 `pong-ramoops` 自报的一行（移植时顺手在 `pong_ramoops_console_write()` 首次调用时打一行 `pong-ramoops: console attached`）。

## 2026-11-21 22:10 —— 27 内核第一次定义了控制台接收端

`patches/xnu-12377/0546-k60-ramoops-console-27.patch` 改成无条件编译后，同一棵树重建的内核里出现了：

```
fffffff00ad8a56c S _pong_ramoops_console_write
fffffff00ad8a768 S _pong_ramoops_console_init
fffffff00addd728 s _k60_serial_clock
```

`scripts/check-kernel-console.py --kernel …` 从 `FAIL: the kernel defines none of …` 变成
`ok console: the kernel defines _pong_ramoops_console_write, _pong_ramoops_console_init`（rc=0）。
此前第三次 0 字节飞行的直接原因就在这里：钩子被 `#if defined(XNU_PONG_RAMOOPS_CONSOLE)` 整段删掉，
因为那个 `-D` 从未到达编译器（P-301）。

**这一步证明的**：内核里有代码会往 ramoops 环形缓冲写。

**这一步没有证明的**（按顺序）：
1. **写的东西有没有内容**。钩子只镜像 `console_write()`；如果 27 的 console 从未被初始化、也没有任何
   调用者，镜像仍然空。判据是 init 之后立刻用同一个写路径打一行自报（实现里已保留 `pong_ramoops_base`
   的 NULL 检查，所以这行不会在映射失败时炸）。
2. **我们能不能读到它**。现在没有任何通路把物理 `0xA7000000` 的 2 MiB 取出来：内核死后没有 USB，
   firmware 也没有读 ramoops 的代码。这是下一个必须新建的东西（判据：不改内核、只换读法，能把上一次
   飞行的 ramoops 头 + 文本取到主机）。
3. **panic 输出会不会经过这个钩子**。XNU 的 panic 打印走 `printf` → `console_write`，理论上会被镜像；
   但 27 的 `debug=1` 会进调试器停住，这条要用一次带 `debug=0` 的飞行验证。

**纪律照旧**：没有 reader 之前，任何「内核静默挂死」的结论都不成立——现在的沉默可能是「没写」，也可能是
「写了但没人读」，两者在主机侧形状相同。

## 2026-11-21 23:10 — 读数器已在固件里，第一次飞行被账本门禁挡住

固件新增 `Platforms/Xiaomi/mondrianPkg/Drivers/RamoopsDumpDxe`（uefi-mondrian `c52a080`，
11,264 B EFI，进 `FV.FvMain` 的第一条 INF，Depex TRUE）：读 `0xA7000000` 的 12 字节头，
按 `start`/`size` 把环形缓冲的首 1,200 B 与尾 2,400 B 打到固件控制台，中间省略。
它只读不写；窗口里没有魔数时报 `RAMOOPS: no signature`，那就是「内核没走到控制台初始化」的答案。

镜像：`boot.img` 201,900,032 B `sha256 227fa8407fd96a9f5f47db239516ca97535df9065c3e6916c1569be1eb173196`，
FD 3,145,728 B `sha256 8102da7d766a`，payload 内 `kernel.macho` `b997f4eeb316`（含两个 sink 符号）。

**但这次飞不起来**：`scripts/flash.sh` 的八步门禁读的是 `docs/research/EIGHT-STEPS.toml`
（iOS 16.6.1 的账本），18 处引用在 27 树里解析不到 ⇒ `禁止刷机`。已登记 P-302：门禁必须按
`board.toml` 的 `os_profile` 选账本，27 线自己的 `EIGHT-STEPS-27.toml`（56 个条目）今天从没被读过。
修法是读取层适配两个 schema，不是改证据串。

**两次启动的分工**（读数器在 DXE 最先跑，所以每次读的是上一次留下的内容）：

| 次序 | 固件应打印 | 含义 |
| --- | --- | --- |
| 第 1 次 | `RAMOOPS: no signature … the window is empty` | 读数器活着；上一次没有写者（或 DRAM 没保留） |
| 第 2 次 | `RAMOOPS: sig ok, start … size …` + 文本 | 内核真的跑到控制台初始化并写了字 |

第 2 次之前若设备静默挂死需要长按电源，此时先别复位——第 2 次读的正是第 1 次留下的内容。

## 2026-11-22 03:59 —— 0547/0548 上了，但卡在 LTO 参考构建（不是内核链接）

`archive-06-build-k60-fileset-reference` 失败，两次：

```
RELEASE reference exit 2 log .../fileset-reference/snapshot-ccf90a9200b46e0d/snapshot-build.log
removed 67 unavailable forced exports; linking again
RELEASE reference exit 2  ->  error: the framework reference build failed (2)
```

`snapshot-build.log:1159366` 的 `Undefined symbols for architecture arm64e` **整块只有一族**：

```
__ZN26IOUnifiedAddressTranslator10gMetaClassE / superClassE / commitUnmapsEv /
prepareFWUnmapEyy / getPageTableEntryEy / setClientContextIDEjb / isPageFaultExpectedEyj /
removeClientContextIDEv / registerTaskForServiceEP4taskP9IOService /
createMappingInApertureEjP20IOMemoryDescriptorjym / getTotalPageTableMemoryEv /
getFirmwareAddressSpaceHandleEv / mapEP11IOMemoryMapj / doMapEP20IOMemoryDescriptoryyj /
unmapEP11IOMemoryMap / doUnmapEP20IOMemoryDescriptoryy / 7getModeEv / taskDiedEv /
__ZTV26IOUnifiedAddressTranslator
```

已排除的猜测（实测）：`grep -rln IOUnifiedAddressTranslator bsd osfmk iokit libkern` 在装配树里**只命中 `iokit/conf/Makefile.arm64`**；我们 `patches/xnu-12377/` 里 0 命中。
⇒ 不是 0547/0548 引进的引用，是**这一类自己的实现没进链接**。

下一轮先回答一个问题：`iokit/Kernel/IOUnifiedAddressTranslator.cpp` 在 27 树里存不存在、由哪个 `conf` 列表收录、
以及 `removed 67 unavailable forced exports` 那次重链删掉的 67 个导出里有没有它。

### 收窄：这是 0547/0548 引进来的一格，不是老病

同一台机器上按日志名数过一遍 `archive-06` 的成败：

```
build-ios27-console4/5/5b/6   fail=0      （0546 之后、0547 之前）
build-ios27-console7          fail=2      （0547 + 0548 之后）
build-ios27-roots/roots2/roots30  fail=0  （改 prelink roots 期间，同样没有 0547）
build-ios27-lto1..8,10        fail=0      （LTO 参考第一次成型时）
build-ios27-lto9              fail=1      （孤例，当时已重跑通过）
```

而这个日志里 `Undefined symbols` **只有两个块**（`:1159366`、`:1173133`），内容同一族
`IOUnifiedAddressTranslator`；`removed 67 … forced exports` 在**外层日志**里，不在这个日志里。

⇒ 结论：**0547 或 0548 让 RELEASE reference 链接少了一族符号**，而不是「LTO 参考一直是坏的」。
`IOUnifiedAddressTranslator` 的实现在 16 与 27 两棵树里都不存在（`ls` 实测 No such file），
`iokit/conf/Makefile.arm64:27` 只留了一行 `IOUnifiedAddressTranslator.cpo_INCFLAGS`。

**下一轮的实验（便宜、可判定）**：把 `0548` 从 series 里临时注掉、只余 `0547`，跑到 `archive-06` 为止；
若转绿则元凶是 0548（它的 `k60_console_export.c` 与 arm_init 三 hunk），反之元凶是 0547 的 1,337 行文件。
两次各约 4–10 分钟，判据只有一条：`grep -c "Undefined symbols" snapshot-build.log`。

## 2026-11-22 05:19 —— 构建全绿，内核里第一次同时有 usblog 与控制台导出

一条命令链跑完，五个判据全过（`build-ios27-console13` + 打包步）：

```
stage payload                   762s    total  765s
ok ADT identity: chip-id 8140, unique-chip-id 4d4f4e445249414e
ok boot.img: 201900032 bytes, hdr v4 1584, shim 112 B, FD 3145728 B sha256 8a551c362484, DTB 4307 B
artifacts: 201900032 byte boot.img sha256 d5664daa7f3e5495fe393099b1a4beeaed313cc08b0439452be0c27efa8c898b
stage firmware-and-bootimg      162s    total  844s
```

| 判据 | 读数 |
| --- | --- |
| `llvm-nm` 里 `k60_usblog\|k60_console_export\|pong_ramoops_console` | 5 个符号 |
| `check-kernel-console.py` | `ok console: the kernel defines _pong_ramoops_console_write, _pong_ramoops_console_init` |
| `boot.img` | 201,900,032 B, `sha256 d5664daa…`, FD `8a551c36…` |

`bsd/dev/k60_usblog.c`（1,337 行）与 `bsd/dev/k60_console_export.c`（186 行）**第一次真的被编译进 27 内核**。
之前四轮分别卡在：LTO 参考链接（框架侧）、钩子参数约定、iron-15 水位、`vm_kern_xnu.h` 缺失——
四者都不是逻辑错，而是两个组件对同一契约的理解不一致。

**仍然未证的三件（顺序即优先级）**：
1. 钩子写的东西有没有内容（需要 `pong_ramoops_console_init()` 成功后自报一行，`0334b` 之前先做这个）；
2. 我们读不读得到（ramoops 不跨复位，唯一读法是在**同一次启动内**经 USB 或屏幕）；
3. panic 输出是否经过该钩子。

**下一步（离线可做）**：按 `0300 → 0311 → 0308 → 0334b` 继续搬，其中 `0311 k60_prime_restart(int)`
与 `0308 k60_usblog_reset_to_fastboot()` 都是纯增量，不再需要改锚点。

### 2026-11-22 06:31 — 写入方只有 console_write，所以「console_init 之前」仍然无声

在 27 的 feed（`xnu-3199e8bc`）里查到的唯一写入方：

- `osfmk/console/serial_console.c:524` `console_write(char *str, int size)`（我们的钩子就在它函数体首行）
- `:626` `console_write_unbuffered(char c)` 通过 `console_write(&c, 1)` 转发，所以两个钩子实际是同一个出口
- panic 路径 `:713-782`（`Log to console by multiple methods`）也走 `console_write`，因此**一旦 `console_init()` 跑过，panic 文本会进 ramoops**
- `osfmk/kern/startup.c:582` 才调 `console_init()`

⇒ 四问的答案是：**writer** = `console_write`；**lifetime** = 从 `arm_init` 的映射到掉电；**read_moment** = 同一次启动内（复位即失，P-307）；**loss_condition** = 任何复位或断电。

**关键限制（必须写在判据前面）**：`console_init()` 之前内核没有任何东西调用 `console_write`，所以**黑屏若发生在 `console_init` 之前，ramoops 里一定是空的**——空不等于“没跑到”，只等于“没跑到能说话的地方”。因此下一次飞行的判据必须写成两段：

1. 日志里有 `pong-ramoops: console attached` ⇒ 映射成功，钩子已就位；
2. 日志里有 panic 文本或 kprintf 行 ⇒ 已经过了 `console_init`；
3. **两者都没有** ⇒ 结论只能是“停在 `console_init` 之前”，而不是“内核没启动”。

### 2026-11-22 07:42 — 第二条更早的通道：PE 文本控制台（`0543`，改的是 `pexpert/arm/pe_init.c`）

`0543-k60-ios27-panel-console.patch` 打的是 `pexpert/arm/pe_init.c`，逻辑是：解析到 `-v` 就把 loader 交来的帧缓冲切进文本模式（`PE_initialize_console(&PE_state.video, kPETextMode)` 再 `PE_initialize_console(NULL, kPEAcquireScreen)`）。

它比 ramoops 早得多——`pe_init` 在 `arm_init` 之前，`console_init()` 更晚（`startup.c:582`）。我们的启动行第一个参数就是 `-v`，所以这条通路的开关**已经打开**。

因此三条通道的时序现在是清楚的：

| 通道 | 起效时刻 | 我们能不能读 | 现状 |
| --- | --- | --- | --- |
| PE 文本控制台（屏） | `pe_init`，最早 | 靠人眼/拍照 | 开启（`-v`），但黑屏说明它没写出来或没切进文本模式 |
| ramoops（内存） | `arm_init` 末（`arm_init.c:711`，`arm_vm_init` 之后） | 需要 reader，且复位即失 | 已编进内核，等上机 |
| usblog EP0（USB） | `bsd_init` 之后 | 需要主机驱动 | `0547` 已编进内核 |

**这条给黑屏一个新的、可判定的解释**：如果 `PE_initialize_console` 成功，屏幕上至少应出现 `-v` 触发的 PE 输出；现在全黑 ⇒ 要么 `PE_state.video` 没被 loader 填充（固件没把帧缓冲信息传过去），要么文本模式切换在这块面板上不生效。下一轮可以直接查固件侧 `boot_args.Video` 是否非零（离线可查，`darwinboot_parsekernel.py` 的 ADT 解析已能读 boot_args）。
