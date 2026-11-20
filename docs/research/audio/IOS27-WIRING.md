# iOS 27 接线清单（音频）

这份文件回答「文件搬过去之后，27 树还要补什么才能编译、能跑」。
可搬清单在 [IOS27-MIGRATION.md](IOS27-MIGRATION.md)，判据行在它 §6；这里只写接线。

## 1. 编译单元与依赖

`drivers/PongAudio` 里只有五个纯 C 单元加 `PongAudioAmp.c` 会进内核编译，它们对外的全部依赖是：

| 符号 | 用途 | 27 树上谁提供 |
| --- | --- | --- |
| `ml_io_map` / `ml_io_map_wcomb` | 把寄存器窗口映射进内核 | XNU 本体，无版本契约 |
| `PE_parse_boot_argn` | `pong_audio=1` 之类的开关 | XNU 本体 |
| `delay_for_interval` / `NSEC_PER_USEC` | `wait_us()` 的底座，功放 SYSST 轮询 | XNU 本体 |
| `printf` | 每一步的证据行 | XNU 本体 |
| `k60_pmic_glink_send_audio` | 走 PMIC GLINK 的 adsp_apps 通道 | `drivers/PongPower`（`QcomGlink.c` + `K60AudioGlink.c`），power 线 |

⇒ 功放这一半（GENI I2C、ACF 回放、开关、SYSST）**不依赖 GLINK**，`PongAudioAmp.c` 可以单独编译、
单独在 27 上跑出 `amp0 id=0x2113`。只有 AudioReach 图那半边需要 GLINK，而它不在本清单里。

表里第一个函数**在宿主上真的跑过**：`sh scripts/tests/portability/run-probe.sh` 把零页当 MMIO 调用
`pong_audio_amp_probe()`——`pong_audio_probe` 缺席时它返回 0 且一行不打印，传入 1 时打印
`amp probe start` 并在第一个缺失的硬件答案处停下（零页 ⇒ `amp probe stop: GPLL0 not locked`），
ASan/UBSan 无报错。⇒ 入口自门控、每条失败路径都有名字，27 上找不到日志时先怀疑驱动宏 `XNU_PONG_AUDIO` 与门控，
而不是怀疑函数没被调到。

这张表不是推断：`scripts/tests/portability/run.sh` 用只声明这六个符号与三个类型
（`vm_offset_t` / `vm_size_t` / `boolean_t`）的桩头文件，把 `PongAudioAmp.c` 编过，
输出 `STUBS OK PongAudioAmp.c`。用的是 `-fsyntax-only` 而不是 `-c`：文件里有 arm64 的
`dsb sy`，x86 宿主汇编器不认它，而解析、类型检查与 `-Werror` 警告照跑。
桩的大小就是 27 树必须提供的内核面的**上界**——少一个符号，这个脚本就红。

桩只能证明「声明够用」，不能证明「不需要更多符号」——所以还有一道链接级检查：
```sh
sh scripts/tests/portability/run-deps.sh
# DEPS OK undefined=6, all named in IOS27-WIRING.md
```
它把 conf/files 会带的那两个文件（`PongAudioAmp.c` 与 `PongAudioGeniI2c.c`）用 `-DXNU_PONG_AUDIO` 编成对象，
`ld -r` 合成一个 relocatable object 后逐个看未定义符号，凡是不在本表里的就失败，并点名缺哪一行。
那「六」个里，27 树真正要提供的是四个内核接口（`ml_io_map`、`PE_parse_boot_argn`、`delay_for_interval`、`printf`），
另两个是宿主 C 库的痕迹（常量字符串让 `printf` 变成 `puts`、栈保护）。
反向也可复现：随便编一个引用未知内核 API 的对象，
`sh scripts/tests/portability/run-deps.sh --object /tmp/unknown.o` 打印
`FAIL: the glue needs k60_bogus_api, which IOS27-WIRING.md section 1 does not name` 并以 1 退出。

**27 的构建比这里严，但不是同一组旗标**：同一对源在 `-Wall -Wextra -Werror` 下、gcc 与 clang 各编两遍
（驱动宏开与关）都干净，`sh scripts/tests/portability/run-warnings.sh` 打
`WARNINGS OK 8 builds, both sources, macro on and off`。27 自己用的是另一组：`makedefs/MakeInc.def:184` 的
`USE_WERROR := 1`、`:195-200` 以 `-Weverything` 开头并把 `$(WERROR)` 拼进去，消费点在
`makedefs/MakeInc.rule:521`。那组旗标下这两个源不是干净的——`-DXNU_PONG_AUDIO` 时 clang 18.1.3 报
83 条 `-Wunsafe-buffer-usage`（Amp 的 ACF 表 78 条，Geni 的发送环 5 条：`PongAudioGeniI2c.c:17`、
`:44`、`:45`、`:126`），宏关时 Geni 仍报 5 条。是否因此变红由 `BUILD_WERROR` 决定：
`MakeInc.def:185-190` 允许覆盖，而本仓的 27 包装脚本 `scripts/build-xnu-generic.sh:840` 与
`scripts/build-xnu-4k-baseline.sh:1443` 都传 `BUILD_WERROR="${XNU_BUILD_WERROR:-0}"`——默认构建里它们只是
warning，`XNU_BUILD_WERROR=1` 时才成为错误。

所以 `run-warnings.sh` 的绿只说明「宿主这组旗标干净」，**不等于「27 的旗标干净」**，两组也不是包含关系
（27 关掉了 sign-compare / sign-conversion，宿主没开 `-Weverything`）。复现脚本与两种 clang 的读数在
`E:/k60-work/scratch/audio27-warning-review/review_exact_xnu_20261120_1332_v2.sh`。不要为了让哪一行变绿去改
驱动或加 `-Wno-`：那五条是真实的可疑索引，要修就单独作为一个改动，量代码而不是量旗标。

这些系统头在 27 树里也还在（2026-11-20 实测）：八个 `<...>` 全部解析得到——`kern/clock.h` → `osfmk/kern/clock.h`、
`pexpert/arm64/board_config.h` → `pexpert/pexpert/arm64/board_config.h`、`string.h` → `osfmk/arm/string.h`（靠构建的 `-I osfmk/arm`）等。
`python3 scripts/check-audio27-includes.py <树>` 打 `INCLUDES OK 8 headers resolve in …`；
改名或删一个就点名 `h (from 源:行)` 并退 1。桩头证明「声明够用」，这一行证明「树里真有这些文件」。
宿主先变红，比在 27 构建里撞一个 warning 便宜；这条和符号表一样，量的都是「27 会拿到什么」。

### 这四个接口在 27 基线里确实还在（2026-11-20 实测）

桩与链接级检查用的都是本仓写的头文件：它们证明「声明够了」，不证明「27 树真的还这么声明」。
后者是树的事实，所以有一道只读检查，输入就是一棵真的 27 源树：

```sh
python3 scripts/check-audio27-kernel-api.py /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc
#   ml_io_map            osfmk/arm/machine_routines.h:603  (maps a physical window ...)
# API OK 4/4 xnu-12377.121.6 ac9718f: ml_io_map osfmk/arm/machine_routines.h:603, …
```

这一行自带两样东西：版本与提交（`xnu-12377.121.6` + `ac9718f`），以及每个名字的 `file:line`。
理由很实际——「绿了，但量的是另一棵树 / 另一个提交」与「真的绿了」在事后从一条不带出处的日志里
分不出来（P-251、P-256 都是这么来的）。

实测位置（`xnu-12377.121.6`，`ac9718f`）：

| 符号 | 27 树里的声明 |
| --- | --- |
| `ml_io_map` | `osfmk/arm/machine_routines.h:603` |
| `ml_io_map_wcomb` | `osfmk/arm/machine_routines.h:607` |
| `PE_parse_boot_argn` | `pexpert/pexpert/pexpert.h:351` |
| `delay_for_interval` | `osfmk/kern/clock.h:327` |

它检查两件事：名字还在，以及**声明的形状**与胶水的假设一致（返回类型与每个参数的类型；参数名不同不算漂移）。
少了或改了形状就报 `SIGNATURE CHANGED` 并打印两者——`delay_for_interval(uint32_t)` 这种少一个参数的情形，
桩头文件看不见，只有真树能看见。

脚本跳过生成头（`static_if.h`）、别的架构（`i386`/`x86`/`x86_64`）和本清单自己搬进去的
`PongAudio*`/`K60*` 头。最后一条不是洁癖：在已接线的树上，`ml_io_map` 会先「命中」
`bsd/dev/PongAudioRegs.h` 这个我们自己写的声明，检查就变成自证。剩下的风险只有
`k60_pmic_glink_send_audio`（power 线）与 `printf`/`NSEC_PER_USEC` 这类稳定接口。

### 桩头文件本身也是被量的对象

上面这一节量的是「27 树里声明还在、形状没变」。但如果 `scripts/tests/portability` 里的桩头写得比内核宽，宿主编译就永远看不见那个差异——两条线各自全绿，真机上才截断。2026-11-20 就有一处：桩说 `void delay_for_interval(uint64_t interval, uint64_t scale)`，而 `osfmk/kern/clock.h:327` 是 `extern void delay_for_interval(uint32_t interval, uint32_t scale_factor)`。胶水的调用点在 `PongAudioAmp.c:111`，传的是 `uint32_t us` 与 `NSEC_PER_USEC`（`1000ull`），所以那条 64 位声明把「第二个参数在真机上要窄化成 32 位」这件事整个盖住了。同一轮还把 `int PE_parse_boot_argn(...)` 改成 `boolean_t`（`pexpert/pexpert/pexpert.h:351`），把 `printf` 的来源注释指到 `osfmk/kern/misc_protos.h:183`（`bsd/sys/systm.h` 里没有它），把 `NSEC_PER_USEC` 的来源注释指到 `osfmk/mach/clock_types.h:84`。

`scripts/check-audio27-stubs.py <xnu-tree>` 把桩里这五条声明（`ml_io_map`、`ml_io_map_wcomb`、`PE_parse_boot_argn`、`delay_for_interval`、`printf`）与常数 `NSEC_PER_USEC`（`1000ull`，胶水用它把微秒换成 `delay_for_interval` 的单位；常数写错比声明写错更安静）与真树逐一比对；比较的是同一个规范形（返回类型加每个参数类型，参数名不算），和 `check-audio27-kernel-api.py` 用同一把尺子：

```sh
python3 scripts/check-audio27-stubs.py /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc
# STUBS OK 6/6 declarations and constants match xnu-12377.121.6 ac9718f
```

把桩改回 64 位就如实报红（自测过）：

```
STUB DRIFT: delay_for_interval: the stub (sys/systm.h) says void delay_for_interval(uint64_t, uint64_t),
            osfmk/kern/clock.h:327 says void delay_for_interval(uint32_t, uint32_t)
STUBS FAILED: 5 declaration(s) compared, 0 missing, 1 drifted
```

一个细节：`printf` 在 27 树里最早的命中来自 `bsd/net/packet_mangler.h:99` 的宏体，所以脚本只接受「看起来像原型」的命中（名字之前是类型串、整行不含 `#`），否则会拿宏体当声明。宿主用例 `scripts/tests/test-audio27-stubs.py` 五例把这个过滤器也钉住了（声明一致、漂移、宏体先出现、缺名字、非 XNU 树）。预检里是两行：`ok   27 stub checker is honest`，以及有 `XNU27_REPO` 时的 `ok   27 stubs match the declarations`。

### 名字会不会撞车

胶水要被放进一棵不是为它写的树里，而「名字看起来是私有的」不是证据：撞名会在链接阶段炸，
离原因很远。`scripts/check-audio27-collisions.py <xnu-tree>` 用桩把头文件编译出两个真实对象，
从 `nm -g --defined-only` 读出胶水**对外可见的十一个符号**（`pong_audio_amp_probe/play/stop`、
`pong_geni_event/poll/prepare/start_read/start_read_bytes/start_write/start_write_bytes/timeout`），
再到树里的 `bsd osfmk pexpert iokit libkern` 找同名项；命中就点名 `file:line` 并退 1。
两处豁免都很窄：接线自己装进去的 `PongAudio*`/`PongCodec*` 文件，以及 `--hook-init` 改的那一个文件
（按它写进去的注释 `K60 audio amplifier probe` 认）。没有第二条，一棵**钩对了**的树会报自己跟自己撞名——
2026-11-20 05:56 实测就是这样被 preflight 抓到的；豁免之后输出 `(skipping the wiring hook: bsd/kern/bsd_init.c)`
+`COLLISION OK`，而在别处再写一份 `pong_audio_amp_probe` 仍然红。

```
$ python3 scripts/check-audio27-collisions.py /tmp/x27real
COLLISION OK: 11 exported symbols, none of them in /tmp/x27real

$ echo 'int pong_geni_poll(void) { return 0; }' > /tmp/x27clash/osfmk/kern/k60_clash.c
$ python3 scripts/check-audio27-collisions.py /tmp/x27clash
  pong_geni_poll             osfmk/kern/k60_clash.c:1
COLLISION: 1 of 11 glue symbols already appear in /tmp/x27clash: pong_geni_poll
```

两处刻意的保守：只看**对外可见**的符号（`static` 的不管，它们撞不了），以及头文件里的声明也算命中
——同一名字在树里另有一份声明，说明那个名字已经被别人占了，迟早冲突。装进 `bsd/dev` 的那几个
`PongAudio*.c` 自己会被跳过，否则这条检查永远在报自己。
### 拷贝清单必须等于编译器打开的清单

`apply-audio27-wiring.py` 决定拷什么，靠的是读 `#include "Pong…"`；那是对源码的一种读法，不是编译器的答案。两者只要有一处不同——某个头文件再去 include 另一个头文件、或者某个源改用尖括号——applier 在树里拷九个文件，构建停在第十个上，而树里没有任何东西说明原因。

`scripts/check-audio27-closure.py` 把同样两个源交给 `cc -MM`（对着 `scripts/tests/portability` 的桩头），比较两个集合：

```
$ python3 scripts/check-audio27-closure.py
CLOSURE OK: 7 headers, the applier copies what the compiler opens
```

- 编译器打开、applier 不拷 → 红，并点名：`CLOSURE: the compiler opens PongAudioExtra.h; the applier does not copy it`。
- applier 拷了、编译器没打开 → 只打印 `copied but never opened: …`，不红：那是多余的重量，不是坏构建。
- 这一轮它抓到的真问题：`kernel_set()` 原来只递归 `.c`，头文件再 include 的头文件不会被跟随，于是「transitively」在文档里成立、在代码里不成立；宿主用例 `a header reached only through another header is copied` 把新行为钉住。
- 四例夹具：仓库自身绿、尖括号 include 被点名、头文件链被跟随、编译器拒绝时报 refusal。注意 refusal 只能由 `#include` 一个不存在的头触发——纯语法错 `-MM` 也能过，因为它只做预处理。

### 产物判据：这颗内核里到底有没有音频

前面所有检查量的都是**源码和对象**：清单、桩、宏、链接需求、接口、空跑接线。它们合起来仍不能回答
一个问题——真正要上机的那颗 27 内核里，音频代码到底在不在。这正是 P-251 的形状：门禁全绿，产物里
没有那个东西。而 27 stage-0 现在只到 bsd_init，F4 之前没有任何音频日志可以读，所以这一条必须从
**产物的字节**里取：

```sh
python3 scripts/check-audio27-kernel.py <kernel.macho | boot.img | PongAudioAmp.o>
# audio27 kernel: boot.img 201,895,936 B sha256 90051b6e6871
# audio27 kernel: strings 3/3 (boot argument, probe start, probe done)
# audio27 kernel: symbols unreadable (nm: … file format not recognized); the strings decide
# AUDIO27 OK boot.img
```

判据是三样东西，缺一个就 exit 1 并点名：

| 类别 | 内容 |
| --- | --- |
| 启动参数 | `pong_audio_probe`（探针唯一的入口开关） |
| 证据行 | `amp probe start` / `amp probe done found=` |
| 符号 | `pong_audio_amp_probe` / `pong_audio_amp_play` / `pong_audio_amp_stop` |

符号先试 `llvm-nm-18`、`llvm-nm`、`nm`：GNU nm 根本读不了 Mach-O（实测 `file format not
recognized`），而「文件被 strip 了」与「拿错工具了」在日志里长得一样，所以不可读时把 nm 的原话
打进那一行，并让字符串单独决定结论——half evidence 不许冒充 full evidence。

两次真实产物的正反结果：显示线的 `kernel.macho`（54,181,888 B，sha256 438de64f08af）→
`strings 0/3` + `symbols 0/3` + `AUDIO27 FAILED`；16 线 cc 的 `boot.img`（201,895,936 B，
sha256 90051b6e6871）→ `strings 3/3` + `AUDIO27 OK`。

预检里它是一行：给了 `XNU27_KERNEL` 就跑，不给就打印 `skip`。27 的 F1 产物一出来，
第一件事就是用这条命令量一遍：

```sh
XNU27_KERNEL=<built kernel> sh scripts/check-audio27-preflight.sh
```

### 27 上先判探针：一条命令、三种答案
27 没有 AFE 端点，`--playback` 那套 S1–S8 是 16.x 的扬声器图，在 27 上会在第一个 period
之前停住。F4（内核走到 `bsd_init`）之后，27 上的第一个判据是**无 flag 的探针模式**：

```sh
python3 scripts/judge-audio-capture.py E:/k60-work/evidence/usblog-<ts>/
```

| 退出码 | 输出 | 27 上意味着什么 |
| --- | --- | --- |
| 0 | `VERDICT: SUCCESS - amplifiers identified` | 探针跑完、`found=2/2`、两个 id 都在已知表 |
| 1 | `probe started but never finished` 或 `FAILED` | 走到了探针，硬件答案不对：GPLL0 没锁、总线没起来、id 不认识 |
| 2 | `VERDICT: probe never ran (no 'amp probe start')` | 这段代码没跑：系列没打 0531，或启动参数没带 `pong_audio_probe=1`——不是硬件结论 |

**2 不是红**：它说的是「这次捕捉对硬件什么都没说」。27 stage-0 的捕捉（还没到 `bsd_init`）
本来就应当是 2；那时若报 1，反而说明 `amp probe start` 被写进了别处。报告里紧跟判决的两行
提示就是为这两种「没跑」写的，免得把接线问题读成硬件问题。

**判决之后：`triage-audio27.py` 说下一步做什么**。判决只说硬件答没答，说不出「为什么没答」——
一次没有 PongAudio 行的捕捉，可能是镜像没接线，也可能是启动在 `bsd_init` 之前就停了。同一次捕捉
带上这次飞的镜像就能分开：

```sh
python3 scripts/triage-audio27.py E:/k60-work/evidence/usblog-<ts>/ \
    --kernel out/.../kernel/kernel.macho
```

末行是 `NEXT: …`，取值只有这几种：

| 情况 | `NEXT` 说的 |
| --- | --- |
| 判决 0 | 跑 `--replay`，判 ACF 两半 |
| 判决 1 | 停住前最后一条 PongAudio 行 |
| 有 PongAudio 行，但镜像早于接线 | 先打系列与每目标宏，再 build |
| 镜像有代码，捕捉停在 `bsd_init` 之前 | 拿最后一行对 F4 的期望 |
| 镜像只缺启动参数 | 命令行加 `pong_audio_probe=1` |

不给 `--kernel` 时它不猜：说 `pass --kernel`，因为不带镜像这两件事在日志里长得一样。
它只读：不 boot、不写、不改任何东西，退出码沿用判决的 0/1/2。

### 启动参数只有一个名字：六处必须同名

探针只在 `pong_audio_probe=1` 时动手（`drivers/PongAudio/PongAudioAmp.c` 的 951 行是那句判空调用）。
这个字面量同时出现在六个地方，任何一处漂移都会让一次飞行读起来像硬件结论：

| 位置 | 漂了会怎样 |
| --- | --- |
| 驱动 ``PE_parse_boot_argn("pong_audio_probe", …)`` | 换名字 = 老命令行的开关没人读，探针一行不打印 |
| `scripts/check-image-args.py` 的 `ALLOWED_ADDITIONS` | 名字不在白名单 = 镜像参数审计拒绝这行，命令行里根本没有它 |
| `scripts/judge-audio-capture.py` 的提示 | 提示让操作者设一个没人读的开关 |
| `scripts/triage-audio27.py` 的 `NEXT` | 同上，而且是在已经白飞一次之后才说 |
| 本页的「启动参数」行 | 读者照着设，但页面与代码不是同一个名字 |
| `docs/engineering/BOOT-ARGS.md` 的条目 | 仓里的 `check-boot-args.py` 直接红：驱动读了一个文档没覆盖的参数 |

`scripts/check-audio27-bootargs.py` 把这六处一起量：从驱动里取名字与**要求的值**（`mode != 1u` 的那个 1），
再要求其余五处出现同一个 `名字=值`。读数：

```sh
python3 scripts/check-audio27-bootargs.py
# BOOTARGS OK 1 call(s) name pong_audio_probe=1 in the driver, the allow list,
#   the judge hint, the triage hint and the wiring page
```

反向各有名字：白名单删掉它 → `… is absent from ALLOWED_ADDITIONS in scripts/check-image-args.py, so the
image audit drops the flag the driver reads`；判官提示换成别的参数 → `no 'pong_audio_probe=1' in
scripts/judge-audio-capture.py`；驱动不再比那一位 → `no mode comparison decides the value`；页面丢了那行 →
`… has no 启动参数 row naming pong_audio_probe`。宿主 `scripts/tests/test-audio27-bootargs.py` 八例把这几条钉住。

文档那处不是假想：2026-11-20 11:30 实测，27 迁移这棵树的 `BOOT-ARGS.md` 里**没有** `pong_audio_probe`
条目，`python3 scripts/check-boot-args.py` 直接报「缺少 1 个参数」，而音频自己的门禁当时还是绿的（它只量代码）。
补上条目后才两边一致；`check-boot-args.py` 也进了预检（`boot arguments are documented`），这样「驱动读了、
文档没写」不会再只靠人记得。共享仓 `k60-gates` 里那份 `BOOT-ARGS.md` 仍是旧的，条目由 Lead 决定何时进 main。

预检里因此多三行：`boot argument checker is honest`（八例）、`audio boot argument is wired`（这门禁本身）、
`boot arguments are documented`（仓里原有的覆盖门禁）。三行都不看设备、不 boot。
### 页面让你跑的命令，必须真能跑

`docs/research/audio/*.md` 里的每条 `scripts/名字.py` 都是一个承诺。两份东西会分头漂：

- **页面指向不存在的文件**。读者照着敲，得到 `No such file or directory`，然后开始怀疑设备。
- **工具存在但没人写它**。下一轮（包括我自己）只会重新发明一遍，或者去猜参数。

`scripts/check-audio27-commands.py [repo]` 两个方向一起量：页面里的每条 `scripts/…py|sh` 必须在本树里；
确实住在别的仓的那五个（`build-xnu-generic.sh`、`build-ios27-linux.sh`、`refresh-xnu-generic.py` 在 k60-gates，
`build-sheng-audio-hal.py`、`check-audioreach-host.py` 在 sheng）写进 `EXTERNAL`，并且**那个位置也被检查**——
借口不会硬化成假设；k60-gates 或 sheng 检出不在本机时只给 `COMMANDS NOTE`，不算失败（换了机器也能跑）。
反向：本线自有的二十一个音频工具里，任何一个没有页面提到它就失败。

它第一次跑还抓到一个真缺陷：九个工具把 `--help` 当成位置参数，于是
`scripts/check-audio27-lines.py --help` 打印的是 `LINES FAILED: --help has no docs/, so there is nothing to read`，
`judge-audio-capture.py --help` 退 2。想知道怎么用的读者拿到的是一句「你给的目录不存在」。现在这十个工具都在
`main()` 开头统一处理 `-h/--help`：打印自己的 docstring、退 0；门禁对每个被页面引用的自有 python 工具真跑一次 `--help`。

```
COMMANDS NOTE: scripts/build-xnu-generic.sh is not in this tree; the gates checkout holds it at /mnt/e/hackios/k60-gates/scripts/build-xnu-generic.sh
COMMANDS OK <citations> citation(s) resolve (…), <tools> audio tool(s) are cited, <help> of them answer --help　（数字随页面增长；carry 与 adsp 的页面数不同，读数也不同）
```

宿主 `scripts/tests/test-audio27-commands.py` **六例**：全部兑现 / 页面指向不存在的文件 / 借口的位置缺那份文件（红）/
根本没有那个检出（NOTE，不红）/ 工具没人写 / `--help` 不答。预检两行：`commands gate is honest`、
`27 command citations resolve`。
### 行数由脚本自己数（2026-11-20 12:10）

以前每加一行检查，就要手改三处散文：预检脚本本身、`docs/research/audio/IOS27-MIGRATION.md:69` 的「五十行 ok」、`porting.toml` 的「50 host rows plus one skip」。三处都靠人记，加完从不重跑，越走越旧。

静态数行不行。预检的行不全由 `run "名字"` 打出：`optional_row`、`seam_row` 两个 helper 按 rc 打 `ok`/`skip`/`FAIL`，另有十几处裸 `printf`。按调用点数只得到 49，真实是 51——差的那两行正好是「取不到就 skip」的那类。

所以让脚本数自己。头部一行 `ROWS_EXPECTED` 是唯一口径，末尾一段外壳带 `K60_PREFLIGHT_INNER=1` 把自己再跑一遍，只数 `^(ok|skip|FAIL) ` 开头的行：与常量不符就打 `ROWS FAILED <printed> rows printed, <declared> declared` 再打 `PREFLIGHT FAILED` 退 1；相符时末行是

```
PREFLIGHT OK <N> rows (<ok> ok, <skip> skip, <fail> FAIL), as declared
```

末行仍以 `PREFLIGHT OK` 开头，别处的 `grep` 和 `tail -1` 不用改。

另外两处散文由 `scripts/check-audio27-rows.py` 钉住：读同一个 `ROWS_EXPECTED`，要求 ① 脚本里还留着那句比对（否则常量本身也成了散文）② 每个音频页面里「N 行 ok」「M 行 skip」加起来等于它 ③ `porting.toml` 的「N host rows plus one skip」里 N+1 等于它。中文数字（十、两）也认。读数：

```
ROWS NOTE: <page>:<line> counts <ok> ok and <skip> skip
ROWS OK <N> rows declared, counted the same in <k> page claim(s) and the record
```

顺手抓到的旧账：`IOS27-USERLAND.md:84` 写着「八行 ok」——那是预检只有八行时的说法，一直没人改。现在那句不写数字，只说末行是 `PREFLIGHT OK N rows (…), as declared`，N 就是脚本头部的常量。

预检两行：`row count gate is honest`（宿主用例 `scripts/tests/test-audio27-rows.py`，九例）与 `row count holds`。

### 文档里引用的日志行，必须真是驱动会打印的

27 的两份页面反复告诉读者「看哪一行输出」。但一行被引用、却没有任何 `printf` 能打印出来时，
门禁全绿、读者却永远等不到那行——这比不写更糟。

`scripts/check-audio27-loglines.py` 把两份页面里所有反引号包起来的 `PongAudio: …` 行与格式串比对：
转换符接受任意值、`…` 允许跳过若干字段、其余字段必须是格式串里的字面前缀（引用可以截断一行）。
打印点有两处：`drivers/PongAudio/*.c`（搬过来的源码）与 `patches/audio/*.patch`（16 线补丁里
TDM pad 那几行，27 不搬但文档会引用）。

```sh
python3 scripts/check-audio27-loglines.py
# LOGLINES OK 9 quoted lines, all printed by 203 formats
```

这门禁自己也被反向量过，而且第一次写错了：最早的版本逐字段严格比对，把 4 条正常引用判红——
省略号后的字段、被截断的行、以及 TDM pad 那行（它在 `patches/audio/0003` 里，不在源码里）。
补上省略号、前缀截断和第二个打印点之后才全绿。教训记在这里：引用与格式串的比对规则本身要有
反向用例，否则门禁会先冤枉文档。

现在往 `IOS27-MIGRATION.md` 里加一行没人打印的引用，会得到
`LOGLINES FAILED: docs/research/audio/IOS27-MIGRATION.md:<行> quotes '<被引用的那一行>',
which no printf prints`，退出码 1；删掉那行又回到 0。

**补丁链不在的分支**（carry 只带源码、不带 `patches/audio/`）不会默默变绿：对不上格式串、
而 `patches/audio/` 又不存在的引用打一行
`LOGLINES NOTE: … only the 16-line patch chain prints it, and patches/audio is not on this branch`，
总数里点名「1 of 9」。这样「这条引用属于 16 线」是个可见的结论，而不是一条消失的检查。

宿主用例 `scripts/tests/test-audio27-loglines.py` 五例（打印出来的行 / 没人打印的行 / 补丁链不在
时给 NOTE / 没有 docs 目录 / 没有格式串），预检里是两行：`ok   logline checker is honest` 与
`ok   27 pages quote printed lines`。

### 页面里的 `file:line` 也是一个承诺

日志行对得上格式串还不够：页面还写着 `PongAudioAmp.c:955` 是那行 `amp probe start`。在它上面加十行，
承诺就断了，而所有门禁照绿——读者跳到 955 行只看到空行，于是认为驱动不打印。

`scripts/check-audio27-lines.py` 钉住五处锚点（`:63` 的宏开关、`:105` 的 `dsb sy`、`:111` 的
`delay_for_interval`、`:955` 的探针横幅、`:1004` 的 `amp probe done`），每处要求「该行含该 token」；
再把两份页面里所有 `PongAudioAmp.c:NNN` 引用与锚点集合比对——引用了一个没人钉的行号就算失败，
因为它要么过期、要么从未被验证。

第一次跑就抓到三处过期引用（`PongAudioAmp.c` 的 `:62`→`:63`、`:98`→`:105`、`:921`→`:955`，都是文件长到 1,018 行之后
留下的）。现在 `LINES OK 5 anchors hold and 5 citation(s) point at them`；token 被挪走时报
`LINES FAILED: … no longer holds 'amp probe start'; the token is on line(s) nowhere`，引用没被钉住时报
`… cites PongAudioAmp.c:<一个没人钉住的行号>, which no anchor covers (anchors: [63, 105, 111, 955, 1004])`。

宿主用例 `scripts/tests/test-audio27-lines.py` 五例，预检里两行：`ok   27 line citations are honest` 与
`ok   27 pages cite live lines`。
### 判决用的芯片表与驱动里的那张必须是同一张

`judge-audio-capture.py` 判探针成败时有一条：每个报上来的 id 必须在它的 `KNOWN` 表里。驱动回答同一个
问题用的是 `PongAudioPlan.h` 的 `pong_audio_amp_name()`。两张表都是手写的，于是会分头长：往驱动加一颗
芯片，判据就把好探针判成 `FAILED`，下一次飞行白飞。

`scripts/check-audio27-chips.py` 把两张表都读出来逐项比，两个方向都算失败。现在
`CHIPS OK 9 ids agree between scripts/judge-audio-capture.py and drivers/PongAudio/PongAudioPlan.h`；
驱动多一颗时报 `CHIPS FAILED: 0x2308 is absent in scripts/judge-audio-capture.py`，名字改了则两边名字都
打出来。宿主用例 `scripts/tests/test-audio27-chips.py` 五例，预检两行：`ok   chip table checker is honest`
与 `ok   judge and driver agree on chips`。
### 两种布局：16 线种树，27 树原地构建

两个脚本（`apply-audio27-wiring.py`、`add-audio-conffiles.py`）都认两种布局：

- `<tree>/.cache/xnu-work/bsd/conf/files` —— 16 线构建脚本种出来的树；
- `<tree>/bsd/conf/files` —— iOS 27 输出树，直接在内核源里构建。

**默认锚点跟着布局走**：种树布局用 `bsd/dev/pong_buttons.c`（16 线补丁自带的那一行），
原地构建的 27 树用 `bsd/dev/unix_startup.c`（该树 `bsd/conf/files:108`，后接三个制表符与 `standard`）。
`--anchor` 仍然可以盖掉两者。这样写是因为 27 树没有 `pong_buttons.c`：它只在 16 线的补丁系列里，
而下一个迁移的人看到默认锚点失败时，第一反应会是「锚点选错了」，不是「布局不同」。

锚点行必须**回显**：`audio conffiles: anchor line '…'`（`repr` 形式，制表符可见）。只报
`lines 0 -> 2` 而不回显，等于没锚上（条目写进了别的段落）与锚上了在日志里长得一样——
P-171/P-245 那一族就是这样漏过去的。失败路径的顺序也不许改：先放源文件，再因锚点缺失退出 1。

### 你说的那个钩子：`scripts/k60-conf-files-hook.py`

`scripts/build-xnu-generic.sh:15-18` 每打完一轮补丁就调一次 `K60_CONF_FILES_HOOK`，那一行有三个问题：

```sh
if [ -n "${K60_CONF_FILES_HOOK:-}" ] && [ -f "${K60_CONF_FILES_HOOK}" ]; then
  python3 "${K60_CONF_FILES_HOOK}" "$ROOT" || echo "K60: conf/files hook failed"
fi
```

① 它用 `python3` 调用，所以钩子必须是 Python 文件；② 失败被 `|| echo` 吞掉，只剩一行没人 grep 的日志
（P-245 原来的形状）；③ 这个变量只能放一个路径，而音频与 power 都要往同一个 `conf/files` 里加行。

所以构建驱动指向的是**串接钩子**而不是追加器本身：

```sh
# 27 build driver
K60_CONF_FILES_HOOK=<repo>/scripts/k60-conf-files-hook.py sh scripts/build-xnu-generic.sh
# 需要时：K60_CONF_FILES_HOOK_EXTRA=<另一个 owner 的追加器>[:<再一个>]
# 需要时：K60_CONF_FILES_ANCHOR=<一行这棵树真的有的>（转给音频追加器）
```

它先跑音频追加器，再依次跑 `K60_CONF_FILES_HOOK_EXTRA` 里冒号分隔的各个 owner（`.py` 用同一个解释器启动），
最后自己数一遍 `conf/files` 里 `PongAudio` 的行数并打一行判决：

```
K60: conf-files hook ok audio=2 extra=0 tree=/path/to/tree
```

任一步非零或行数不足两行时是 `K60: conf-files hook FAILED: <步骤> exited <n>` 并退 1。
退 1 仍然会被构建脚本吞掉——但日志里「没有那句 `conf-files hook ok`」现在就是证据：
绿构建加上没有这句，等于这棵内核里没有音频条目；而真正的兜底仍是产物判据
（`check-audio27-kernel.py`：没有音频的内核直接 `AUDIO27 FAILED`）。

宿主测试 `scripts/tests/test-conf-files-hook.py` 五例（写成功、锚点缺失、额外 owner 成功、额外 owner 失败、
没种树），预检里是 `conf-files hook is honest`。

在真 27 树副本上实测（不带 `--anchor`，走布局默认）：

```sh
python3 scripts/apply-audio27-wiring.py <tree> --hook-init
# audio conffiles: anchor line 'bsd/dev/unix_startup.c\t\t\tstandard'
# audio conffiles: pong_audio lines 0 -> 2
# audio wiring: OK sources=9 conf=2 init=1
```

写进去的是 `bsd/conf/files:109` 与 `:110` 两行（`PongAudioGeniI2c.c`、`PongAudioAmp.c`），
`bsd/dev` 下九个文件（两个 `.c` 加七个头）。**只读别人的输出树**：验证都在 `/tmp` 副本上做。
### 在真的 27 源树上走了一遍（2026-11-20 05:40 实测）

前面几节是在 `/tmp` 里照 27 的形状搭的空树。这一节是把 `cp -a` 出来的**真源树**
（`/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc`，`git log -1` = `ac9718f xnu-12377.121.6`）接上：

```
$ python3 scripts/apply-audio27-wiring.py /tmp/x27real --anchor "$(printf 'bsd/dev/unix_startup.c\t\t\tstandard')"
audio conffiles: anchor line 'bsd/dev/unix_startup.c\t\t\tstandard'
audio conffiles: pong_audio lines 0 -> 2
audio conffiles: both entries listed
audio wiring: sources 9 (added 9, refreshed 0, current 0)
audio wiring: OK sources=9 conf=2

$ python3 scripts/check-audio27-kernel-api.py /tmp/x27real | tail -1
API OK 4/4 xnu-12377.121.6 ac9718f: PE_parse_boot_argn pexpert/pexpert/pexpert.h:351,
  delay_for_interval osfmk/kern/clock.h:327, ml_io_map osfmk/arm/machine_routines.h:603,
  ml_io_map_wcomb osfmk/arm/machine_routines.h:607

$ grep -n PongAudio /tmp/x27real/bsd/conf/files
109:bsd/dev/PongAudioGeniI2c.c			standard
110:bsd/dev/PongAudioAmp.c			standard
```

也就是说：真树的锚点、两行 conf、九个文件、四个接口，一次全对；不需要先把树构建起来。

### 为什么不在 27 源树外面直接编这两个 `.c`

「拿真头文件编一遍胶水」听起来比桩更强，实测走不通一半：

- `PongAudioGeniI2c.c` 用 `-nostdinc -ffreestanding -target arm64-apple-ios27.0` 加
  `-I EXTERNAL_HEADERS -I bsd -I osfmk -I pexpert -I libkern -I SETUP -I osfmk/arm` 编得过
  ——但它只 include 自己的头文件，能过说明的是「这个头自洽」，不是「胶水与内核兼容」。
- `PongAudioAmp.c` 会走到 `osfmk/kern/assert.h` 的 `#include <mach_assert.h>`，而这个头是**构建时生成**的
  （`SETUP/setup.sh`），源树里根本没有；再往下还有 `IOKit/IOInterrupts.h`（SDK 侧）与
  `kern_types.h` 的 `clock_t` 重定义，都是构建自己的 include 顺序与生成头才能消掉的东西。

结论：外面的编译**不能**当作 27 的判据，能当判据的只有两样——源码级检查（`API OK` / 迁移清单 / 符号表）
和**构建产物**（`scripts/check-audio27-kernel.py`，见上一节）。真编译只有走真实构建一条路，
而它由 Lead 的 F1 流水线负责；接线对不对，看那次的 `AUDIO27 OK` 或 `AUDIO27 FAILED`。
### 第零道闸：驱动宏 `XNU_PONG_AUDIO`

`PongAudioAmp.c` 的整个函数体在一个 `#if` 里：`#if defined(PONG) || defined(XNU_PONG_AUDIO)`
（`PongAudioAmp.c:63`，带 7 行注释说明两种来路）。两个宏是**同一份实现的两个开关**，不是两条路径：

- 16.x 用 `PONG`，它是**机配置**：`patches/xnu/zzzz-pong-machine.patch` 新增
  `pexpert/pexpert/arm64/PONG.h`，把 `SUPPORTED_ARM64_MACHINE_CONFIGS` 从
  `BCM2837 T6000 T8101 T8103 VMAPPLE` 扩到含 `PONG`（补丁 :105-108），构建脚本再传
  `MACHINE_CONFIGS=PONG`（`build-xnu-4k-baseline.sh:248`、`build-darwin24-linux.sh:97/117`）。
- 27 不引入 `PONG`。机配置决定 `arm_init`、platform expert 与中断控制器接线；bring-up 阶段
  另造一份机配置等于同时动两个未知量。音频改用**驱动级宏** `XNU_PONG_AUDIO`，由 board/config
  打开，与机配置解耦，27 基线继续 `BCM2837`。

宏没打开会怎样：文件仍然编译通过，只是编成**空翻译单元**——「静默编空」。979 例 host 测试照旧
全绿，内核里一行 `PongAudio:` 都没有。所以验证不看日志，看符号表：

```sh
sh scripts/tests/portability/run-symbols.sh
# SYMBOLS OK off=0 XNU_PONG_AUDIO=3 PONG=3
```

它用真实代码生成编译这个文件（`cc -c`；为此 sed 掉唯一那条 `__asm__ volatile("dsb sy" ::: "memory");`
——`PongAudioAmp.c:105`，x86 宿主汇编器不认），再用 `nm -g --defined-only` 数导出符号：

| 编译开关 | 导出符号 | 含义 |
| --- | --- | --- |
| 无 | 0 | 宏没开 ⇒ 内核里没有音频胶水，正是要防的静默编空 |
| `-DXNU_PONG_AUDIO` | 3（含 `T pong_audio_amp_probe`） | 27 线打开 |
| `-DPONG` | 3 | 16 线打开，与上一行等价 |

这条同时是反向用例：若有人把 `#if` 写坏、让代码漏到宏外面，`off` 就不再是 0，门禁立刻红。
`scripts/check-audio27-preflight.sh` 把它列为独立一行（`ok   driver macro really switches it`）。

### 在 27 树上打开它：三处改动

宏是开关，落到树上要三处配合，缺一处就是静默编空。三处都在**构建侧**，不动机配置：

1. **源文件落位**：`drivers/PongAudio/` 的两个编译单元进内核树——
   `PongAudioAmp.c` 与它直接调用的 `PongAudioGeniI2c.c`（宿主探针同样要链这两个，
   `run-probe.sh` 就是这么链的），随行头文件由 `python3 scripts/check-audio-migration.py --copy DIR`
   按清单复制，避免手抄漏项。
2. **bsd/conf/files**：两行由**音频自己的**追加器写进去——`scripts/add-audio-conffiles.py`
   （`bsd/dev/PongAudioGeniI2c.c` 与 `bsd/dev/PongAudioAmp.c`）。不用 power 线的
   `scripts/append-conffiles.py`：那个文件按 `TREE-OWNERS.toml:139` 归 power，音频加行要改别人的表；
   而它的失败形状正是 P-245 那一族——打印 `anchor missing, entries not added`，外面一个 `|| true`
   就变成绿色构建加一树没有音频的内核。**判据是计数不是消息**：

   ```sh
   python3 scripts/add-audio-conffiles.py <tree>                   # 16 树：锚点是 pong_buttons 那一行
   python3 scripts/add-audio-conffiles.py --anchor "<line>" <tree> # 27 树：给一行它真的有的
   python3 scripts/add-audio-conffiles.py --check <tree>           # 只报数，不写
   ```

   默认锚点是按键驱动的 `bsd/dev/pong_buttons.c`（`standard`，制表符分隔）。**27 树没有这个文件**——
   它是 16 线补丁带进 `bsd/conf/files` 的，所以 27 上必须传 `--anchor` 指一行那棵树真的有的
   （构建树 `bsd/conf/files` 里任取一行，例如它自己的 `bsd/dev/*` 段落），计数判据不变。输出
   `audio conffiles: pong_audio lines 0 -> 2`；锚点缺失、源文件不在树里、写后仍不到两行，三种情况
   都是 exit 1 且把计数打出来；锚点缺失时还会打印 `pass --anchor with a line this tree has`，
   不再有「静默跳过」这一档。`--check` 给构建后复核用。宿主用例
   `scripts/tests/test-audio-conffiles.py`（7 例：追加、幂等、锚点缺失、自定锚点、源缺失、
   check 模式、未 seed 的树），`check-audio27-preflight.sh` 里是一行 `ok   conf-files appender is loud`。
   16 树上这两行是 `0001:3504-3505` 直接打进 `bsd/conf/files` 的，27 上不能打补丁（P-171）。

3. **宏**：唯一正确的落点是**每目标文件**的编译标志，不是全局变量：

   ```sh
   # 点号名变量不能 export，用命令前缀给进程环境；启动 shell 必须是 bash。
   PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1 bash scripts/build-xnu-generic.sh
   ```

   理由是「可转移」这三个字：全局 `EXTRA_CFLAGS` 会把 `-DXNU_PONG_AUDIO` 塞给**每一个**对象，
   于是「音频的宏开没开」不再是这一条线的性质，任何一处的行为变化都可能是别人编进来的；
   每目标文件写法把定义钉在 `PongAudioAmp.c` 上，别的单元看不到它，判据才可证。

   为什么是这个形态，而不是把 `EXTRA_MAKE_ARGS` 放进环境：`scripts/build-xnu-generic.sh:166` 是
   `EXTRA_MAKE_ARGS=()`，环境里的同名变量会被这一行清掉，于是
   `EXTRA_MAKE_ARGS="PongAudioAmp.o_CFLAGS_ADD=…" sh scripts/build-xnu-generic.sh` 是**静默无效**的：
   宏不定义、胶水编空、构建照样绿（P-245）。点号名变量不是合法的 shell 标识符，不能 `export`，
   但可以写成命令前缀作为进程环境；`make` 会把环境变量导入成同名变量，生成的
   `bsd/conf/Makefile` 对每个对象只写 `+=`（`SETUP/config/mkmakefile.c`），所以环境值是**追加**
   而不是覆盖，`makedefs/MakeInc.rule:521` 的 `$($@_CFLAGS_ADD)` 是消费点。**启动的 shell 必须是
   bash**：dash 会丢掉点号名环境变量（实测 `sh` 下到达 make 的是 0，`bash` 下是 1），而脚本头本来
   就是 `#!/usr/bin/env bash`，写成 `sh scripts/…` 就正好落进静默无效。三种写法在同一份复刻 `:166`
   重置的 harness 上实测：

   | 写法 | make 看到的 `PongAudioAmp.o_CFLAGS_ADD` |
   | --- | --- |
   | `EXTRA_MAKE_ARGS="…" sh scripts/build-xnu-generic.sh` | 空（无效） |
   | `PongAudioAmp.o_CFLAGS_ADD=… bash scripts/build-xnu-generic.sh` | `-DXNU_PONG_AUDIO=1` |
   | 两者同时 | 仍是 `-DXNU_PONG_AUDIO=1`（不叠加） |

   `scripts/tests/test-audio27-define.py` 把这几行钉住，预检里是一行 `ok   define delivery is honest`。
   `scripts/build-xnu-generic.sh` 是框架构建器的**逐字副本**，`scripts/refresh-xnu-generic.py`
   刷新会整体覆盖（只留文件头），所以不往里面加行——用上面的变量，或由上游把这条写进构建器。

   现存的替代口径（只在没有 `EXTRA_MAKE_ARGS` 口子时用）：`XNU_EXTRA_CFLAGS` 在脚本 :286 是
   **替换**不是追加，只写 `-DXNU_PONG_AUDIO=1` 会连 :286 的默认 `-Wno-*` 一起丢掉，
   要先把那七条拼回来再追加；:841 以 `CFLAGS_EXTRA` 交给内核 `make`（`MACHINE_CONFIGS=BCM2837`，
   :833-842），所以它到得了每个单元——这也正是上一条要避开的原因。

### 谁把这行交进构建：27 构建驱动的那一处

上面那条命令是人手敲的；真正跑 27 构建的是 `scripts/build-ios27-linux.sh`，它最后一步是
`python3 ./unixnu build kernel --device "$ROOT" "$@"`。这条链上有三处接缝，断掉时构建都是绿的：

| 接缝 | 断了会怎样 | 检查器认的形态 |
| --- | --- | --- |
| 驱动把不把 `K60_CONF_FILES_HOOK` 交给内核构建 | 追加器从不运行，`bsd/conf/files` 没有那两行，胶水不编进内核，构建照样绿 | `build kernel` 那一行带 `K60_CONF_FILES_HOOK=…/scripts/k60-conf-files-hook.py`，或 bash 版驱动自己 `export` |
| 驱动把不把 `PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1` 交进去 | 宏不定义，`PongAudioAmp.c` 编空（979 例仍然全绿） | 同一个 `env` 前缀里带这一对；bash 驱动可以 `export`，`#!/bin/sh` 不行 |
| 框架还把不把自己的环境交给设备构建器 | 上面两个变量止步于 CLI | `scripts/unixnu/kernel.py` 里 `env = dict(os.environ)` 与 `run(['bash', script], …, env=env)` 都还在 |

`scripts/check-audio27-builder.py` 查这三样，读数来自**真的驱动与真的框架**，不是本文档的副本。
预检里它们是三行，一行一处接缝——三处断掉的样子不同，混成一行就分不出是哪一处：

检查器的树必须明确：`--tree` 指向实际 k60-gates 检出（默认先看 `K60_REPO`，再看 `K60_GATES`，最后才用仓旁的 `k60-gates`）。钩子文件必须在这棵被检树里；音频仓有同名文件不算。

无可量的接缝现在返回 3，并在预检中显示 `skip`。驱动根本没提这个变量，或驱动写了默认钩子路径但目标文件不在树里，都不能显示 `ok`。只有接缝确实交给构建链才返回 0。

当前 stage 0 的实况是：`27 driver takes the conf hook` 为 `skip`（驱动树没有 `scripts/k60-conf-files-hook.py`，原因是 stage 0 有意不链接音频 lane 对象）；`27 driver takes the define` 与 `framework passes env to builder` 为 `ok`。没有 `XNU27_KERNEL` 时产物行也是 `skip`——两行 skip 都不表示接线通过，也不表示产物带音频。Stage-0 范围由板级 `board.toml` 决定；缺 hook 不是当前阶段的产物缺陷。

驱动里的两处分别是 `build-ios27-linux.sh:51-54`（`if [ -f … ]` 里先赋值再 `export K60_CONF_FILES_HOOK`）与
`:59-60`（`env "PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1" python3 ./unixnu build kernel`）。
钩子走 export、宏走 `env` 前缀，不是两种写法随便挑：点号名在 `#!/bin/sh` 里不能 export（P-260），而钩子名可以，
并且它必须在「文件在不在」的那个 `if` 里赋值，所以用的是「先赋值、再单独 export」两行形态。

检查器认三种「交到了」：`build kernel` 那一行自己带 `NAME=…`；驱动里 `NAME=…` + 之后一行 `export NAME`；
一行 `export NAME=…`。三种都要求值落在 `scripts/k60-conf-files-hook.py` 上，并且中间没有 `unset`。
**注释不算交付**：如果这个名字只出现在 `#` 后面，报的是
`BUILDER FAILED: … names K60_CONF_FILES_HOOK only in a comment, so the kernel line never carries it and a build reads as wired`；
如果它在别处被赋值、但没送到 `build kernel` 这条命令上，报的是 `BUILDER FAILED: … names … elsewhere but the kernel line does not carry it`。
在 `#!/bin/sh` 里 `export` 点号名仍是 `FAIL`（dash 直接拒绝），提示改用 `env` 前缀。第三处在没有框架检出时打 `skip`，不冒充绿。

当前驱动仅在目标文件存在时设置 hook；缺失时静默跳过。若要让缺失状态在构建开始前可见，提案 `docs/research/audio/STAGE0-HOOK-STATUS.patch` 会对显式给出的无效路径报错，并在默认 hook 缺失时打印 stage-0 说明。它没有应用到共享 gates。`scripts/tests/test-audio27-hook-status.py` 只在临时副本中 `git apply --check`、应用提案并运行截取的 hook 块，覆盖 5 种存在/缺失组合；不执行构建。

`scripts/tests/test-audio27-builder.py` 的十个用例把这几种形状各复现一遍：驱动未命名接缝、接好三行、被检树缺 hook、默认树选择与显式 `--tree` 覆盖、
「别处赋值但没送到」（FAIL）、「只在注释里」（FAIL）、「赋值后单独 export」（OK）、「赋了又 unset」（FAIL）、
`#!/bin/sh` 里 export 点号名（FAIL）、框架改成 `env = {}`（FAIL）、驱动与框架都不在（skip）。




### 一条命令：文件内的改动 + 第三处的命令行

复制与 conf/files 是两次文件编辑，中间还可能因为锚点不对半途停下，所以合成一个入口。判据仍是两个数：
进树了几个源文件、conf/files 认了几行。

```sh
python3 scripts/apply-audio27-wiring.py --check <tree>              # 只报缺什么，不写
python3 scripts/apply-audio27-wiring.py <tree> --anchor "<line>"    # 27 树
python3 scripts/apply-audio27-wiring.py <tree>                      # 16 树：默认锚点
# audio wiring: sources 9 (added 9, refreshed 0, current 0)
# audio conffiles: pong_audio lines 0 -> 2
# audio wiring: bsd_init not hooked (pass --hook-init); the glue compiles in and never runs
# audio wiring: OK sources=9 conf=2 init=0
```

末行带着 `init=`：0 表示没人调用它（下一节），1 表示 `bsd_init` 里已经有一处调用。
**不加 `--hook-init` 时脚本会主动打一行说「编进去也不会跑」**，因为这两件事在没有这一行时
在日志里长得一样。

它只搬内核编译真正需要的那一束：两个 `.c` 与它们递归 include 到的 `PongAudio*.h`（当前 9 个文件）。
`PongAudioAfe.h` 不在其中——16 线的 AFE 端点，本固件没有 AFE 服务，只随 host 测试走；
`K60PmicGlinkAudio.h` 也不在——发给 ADSP 的那一端归 power 线。第三处改动不是文件编辑，所以它只把
构建命令行打出来（`PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO`），不去改 `build-xnu-generic.sh`
（框架逐字副本，见上一项）。锚点不对时它先把源文件放好、再报 `pass --anchor` 并 exit 1，重跑一次就补齐，
所以中途停下是可见且可续的。宿主用例 `scripts/tests/test-apply-audio27-wiring.py`：锚点缺失必须失败、
命名锚点后只列两行、`--check` 不写、过期头文件被刷新、未 seed 的树被拒、冻结头文件不进树（6 例），
`check-audio27-preflight.sh` 里是一行 `ok   one command applies the wiring`。
验证不看日志，看产物，而且正反两跑都要给：

```sh
NM=llvm-nm-18 sh scripts/tests/portability/run-symbols.sh --object <build>/PongAudioAmp.o --expect on
# -> SYMBOLS OK object=... expect=on probe=1        (符号名是 Mach-O 的 _pong_audio_amp_probe)
NM=llvm-nm-18 sh scripts/tests/portability/run-symbols.sh --object <without-macro>/PongAudioAmp.o --expect off
# -> SYMBOLS OK object=... expect=off probe=0
sh scripts/tests/portability/run-symbols.sh        # 宿主三连：off=0 / XNU_PONG_AUDIO=3 / PONG=3
```

`probe=1` 与 `probe=0` 是同一个问题的两个答案：前者证明宏真的进了这次编译，后者证明这张
计数表本身会动（不会永远打印同一个数）。两者都在 `check-audio27-preflight.sh` 里。
真机上再对 `amp probe start`（`PongAudioAmp.c:955`）——两者的区别是「内核里有没有这段代码」
与「这段代码跑没跑」，先证前者。

本清单的门禁不读任何 out 树（迁移清单、桩、符号、宿主探针、判据测试都在临时目录或宿主上跑），
所以不存在写死 16 线产物路径的问题；以后若加读产物的检查，路径必须取 `K60_OUT`，不许钉
`out-baseline`。


### 第四处改动：27 上谁调用它（内容归音频，承载归 27 补丁系列）

前三处让胶水**编进内核**，但没有一处让它在启动时**跑起来**。16 树上是补丁替我们做的：
`adsp:patches/audio/0001-k60-audio-amp-probe.patch:3508-3522` 在 `bsd/kern/bsd_init.c` 里插了一段

```c
+#if 1
+	if (result == KERN_SUCCESS) {
+		extern int pong_audio_amp_probe(void);
+		(void)pong_audio_amp_probe();
+	}
+#endif
```

27 树没有这个补丁（补丁系列是 16 线的），所以这一段在 27 上没人写：胶水进树、编过、链过，
开机一行日志都不会有——正是 P-171 那一族的静默形状，只不过这次静默的是整个子系统。

因此 applier 带一个 **opt-in** 的 `--hook-init`，把调用点写进 `bsd/kern/bsd_init.c`：

```sh
python3 scripts/apply-audio27-wiring.py <tree> --anchor "<line>" --hook-init
# audio wiring: init anchor line '\tbsd_init_kprintf("calling vfsinit\\n");\n'
# audio wiring: bsd_init probe calls 0 -> 1
# audio wiring: OK sources=9 conf=2 init=1
```

三个设计选择，都是为了让它可判定，而不是让它聪明：

1. **锚点是 `bsd_init_kprintf("calling vfsinit\n");`**（27 的 xnu-12377.121.6 里在
   `bsd/kern/bsd_init.c:701`，`bsd_init()` 开头）。一行、唯一、不随配置漂移；早于 `vfsinit()`
   意味着此时 `printf` 已经可用（同一行上就是它），而探针只碰 MMIO、`delay_for_interval` 与 `printf`。
   锚点行**回显**（`%r`，制表符可见）：钩错位置与没钩上，在日志里必须分得开。
2. **不抄 16 线的 `if (result == KERN_SUCCESS)`**：27 的 `bsd_init()` 在那个位置没有 `result`。
   抄形状可以，抄判断不行——那里根本没有条件可判。
3. **不套 `#if defined(XNU_PONG_AUDIO)`**：那个宏只落在 `PongAudioAmp.o` 这一个对象上
   （每目标 `CFLAGS_ADD`，见上一节），`bsd_init.c` 看不到它，套上去等于把调用点编译掉。
   所以用 16 线同样的 `#if 1`，把「跑不跑」留给运行期：`pong_audio_probe=1` 才动手，
   否则探针自己立刻返回。

2026-11-20 05:54 在真 27 源树副本 `/tmp/x27real`（`ac9718f xnu-12377.121.6`）上实测：
`bsd_init probe calls 0 -> 1`，写进 `701` 之后、`vfsinit();` 之前，`grep -c` 得 1；
重跑打印 `bsd_init already hooked (probe calls 1)`。锚点不在树里时 exit 1 并给
`pass --init-anchor with a line this tree has`，**先放源文件再失败**的顺序不变。

**2026-11-20 06:20 裁决**：内容由音频写，承载走 27 补丁系列——补丁落在 `patches/xnu-12377/`，
由 Lead book 进 MAIN-BASELINE 与 sync，ownership 因此留在设备仓。音频分支只保留源与生成器
（`apply-audio27-wiring.py --hook-init`），提交消息写明 ported from 16 line
`patches/audio/0001:3508-3522`。

裁决同时加了一条硬要求：**调用点必须弱符号安全**。声明写成
`extern int pong_audio_amp_probe(void) __attribute__((weak));` 并在调用点判空，
否则 27 上胶水一旦被裁掉就是 `Undefined symbols`（cellular 线刚在 0628 上踩到同一形状：
`ArmSmmu4KBuild` 缺定义）。块内因此是 `if (pong_audio_amp_probe != NULL) {
(void)pong_audio_amp_probe(); }`，注释里写明「唯一的开关是 `pong_audio_probe=1`，不是 `XNU_PONG_AUDIO`」。

两种链接各走一遍（`scripts/tests/portability/run-weak-hook.sh`）：把 applier 写出的块原样放进一个
函数体，**不链** provider 时链接必须成功且不执行，链上 provider 时必须执行到（provider 里 `exit(42)`）：

```sh
sh scripts/tests/portability/run-weak-hook.sh
# WEAK OK absent links and skips, present runs (exit 42)
```

交付的补丁（`git diff` 形态，17 行，只碰 `bsd/kern/bsd_init.c`）：

- 文件：`E:/k60-work/scratch/audio-27/k60-audio-amp-probe-call.patch`（806 B，sha256 `3665a972557f4b15bcc232124e46f3984c2e5cec781d838845f0366b28eb8da4`，`-U1`：调用点前后各一行上下文）
- 在真 27 源树（`ac9718f xnu-12377.121.6`）的干净副本上 `git apply --check` → `APPLY CHECK OK`
- 落位编号由 Lead 分配：**`0531-k60-audio-amp-probe-call.patch`**（2026-11-20 06:34，`patches/xnu-12377/`；
  0530 是 SPI availability，之后的新 27 补丁从 0532 起）。Lead 复制这个文件、插进 series、`git apply --check`
  复验并登记 MAIN-BASELINE 与 sync；音频分支只留生成器与源。
- 重新生成用生成器，不要 `git diff` 手抄：

  ```sh
  python3 scripts/emit-audio27-patch.py <27 源树> --out /tmp/0531.patch \
      --expect 3665a972557f4b15bcc232124e46f3984c2e5cec781d838845f0366b28eb8da4 --check
  # audio patch: /tmp/0531.patch 806 B sha256 3665a972…
  # audio patch: APPLY CHECK OK
  ```

  它读 `INIT_BLOCK`（sha256 前 16 位 `c41d0c6743591c9d`），在内存里插进 `bsd/kern/bsd_init.c` 生成补丁；
  `--expect` 钉住 digest——块改了、补丁没跟着改，这一行立刻红。已接线的树会先把块剥掉再生成
  （`the tree already carries the hook; emitted from its stripped form`），所以「先 wire 再 emit」
  与「干净树 emit」拿到同一份字节。块与补丁不许分头演化，预检里两行盯着它：
  `27 patch emitter is honest`（生成器自带 5 例宿主测试）与
  `27 patch emits unchanged`（`XNU27_REPO` 在场时按上面那组参数真跑一遍）。

### 0531 现在为什么没有列进系列（2026-11-20 10:20 实况）

Lead 把 0531 从 `patches/xnu-12377/series` 里**注释掉了**，理由写在系列文件里：

```
# 0531-k60-audio-amp-probe-call.patch is deliberately NOT listed: the kernel link
# cannot resolve its call site. The call is `extern int pong_audio_amp_probe(void)
# __attribute__((weak));` guarded by `!= NULL`, and clang does emit N_WEAK_REF
# (verified in bsd_init.o's symbol table) -- but this ld64-port rejects an undefined
# weak function reference in the static/dynamic images the kernel is linked as, and
# accepts it only in the -kext form the kernel does not use. The result was
# `Undefined symbols for architecture arm64e: "_pong_audio_amp_probe", referenced
# from: _bsd_init in bsd_init.o; l_pong_audio_amp_probe$auth_ptr$ia$42271 in
# bsd_init.o` (snapshot-build.log:1173089, round 15). Stage 0 has no audio: the file
# stays here so the audio lane can list it again once PongAudioAmp.o is force-loaded
# into the link and the symbol has a definition, which is what makes the probe
# observable. A definition that returns 0 would not do: `AUDIO27 OK` has to tell
# 「not wired」 from 「wired to an empty shell」.
```

这条对音频线是硬事实，改的是我们的假设，不是别人的排版：`__attribute__((weak))` 在这种 ld64 上只解决**编译**，不解决**链接**。
clang 确实发了 `N_WEAK_REF`，但 arm64e 的认证指针桩 `l_pong_audio_amp_probe$auth_ptr$ia$42271` 仍然需要一个目标；
这个 ld64 只在 `-kext` 形态里接受未定义弱函数引用，而内核不是那种形态。于是顺序被钉死：
**先把 `PongAudioAmp.o` 强制加载进链接（即 `K60_CONF_FILES_HOOK` 那两行加每目标 `-DXNU_PONG_AUDIO`），再把 0531 列进系列**。
反过来先列，构建会在链接期红，而源码级门禁全绿。

一个诱人的捷径是给个返回 0 的定义让链接过去 —— 不行。`AUDIO27 OK` 要能区分「没接线」和「接了一个空壳」；
一个恒返回 0 的 `pong_audio_amp_probe()` 会让产物判据在没音频时也绿。

因此本线现在的状态是**有记录的暂缓**，门禁按这个状态判：

| 系列里的情形 | 门禁打印 | 退出码 |
| --- | --- | --- |
| 列着、代码与生成器一致 | `SERIES OK … inserts the emitter's code` | 0 |
| 列着、只有注释/排版不同 | `SERIES NOTE …` 后接 `SERIES OK` | 0 |
| 列着、代码不同 | `SERIES FAILED … inserts different code` | 1 |
| 在目录里、没列、注释里点了名 | `SERIES HOLD … the series file says why` 后接 `SERIES OK … (held, not listed)` | 0 |
| 在目录里、没列、没有注释 | `SERIES FAILED … no comment says why` | 1 |
| 目录里还没有这份补丁 | `series: no 0531 audio patch …` | 3（skip） |

宿主用例 9 例（`scripts/tests/test-audio27-series.py`）把后三行各钉一例，包括「注释掉但点了名」与「注释掉又没点名」必须一个有记录、一个失败。

### 第三份拷贝：系列里落地的那一份

同一个调用块一共三份拷贝：applier 的 `INIT_BLOCK`（源）、我们交付的补丁文件、以及 Lead book 进
`patches/xnu-12377/` 之后系列里那一份。前两份由上面两行钉住；第三份由 `scripts/check-audio27-series.py`
钉住——它从 27 源树重新生成一遍，再与系列里的 `0531-*.patch` 比较**插入的代码**（块注释、行注释与空白先去掉）。字节和上下文宽度只打附注：那是交付决定，不是契约。

```sh
python3 scripts/check-audio27-series.py <27 源树> [--series DIR]   # 默认 /mnt/e/hackios/k60-gates/patches/xnu-12377，XNU27_SERIES 可改
# SERIES NOTE: 0531-k60-audio-amp-probe-call.patch differs in bytes (series <digest>, emitter 3665a972…); the inserted code matches
# SERIES OK 0531-k60-audio-amp-probe-call.patch <size> B sha256 <digest> inserts the emitter code
# SERIES HOLD: 0531-k60-audio-amp-probe-call.patch sits in <series> unlisted, and the series file says why: '0531-k60-audio-amp-probe-call.patch is deliberately NOT listed: the kernel link'
# SERIES OK 0531-k60-audio-amp-probe-call.patch 1033 B sha256 983f1e2e… inserts the emitter code (held, not listed)
```

三种答案分开：`0` 一致、`1` 不一致或系列文件里没列它（列了才真的会被构建应用）、`3` 系列还没 book 它。
`3` 在预检里是 `skip` 而不是绿行——「还没有」和「已经对了」必须长得不一样，否则等 Lead 落地那天，
绿的到底是哪一种就没人分得出来。预检因此多两行：
**2026-11-20 07:19 Lead 已 book**：`/mnt/e/hackios/k60-gates/patches/xnu-12377/0531-k60-audio-amp-probe-call.patch`
，`series:52` 有这一行。系列里的字节与生成器不同（Lead 那份是 `-U1` 加一行注释，之后又重发过一次），大小与摘要因此会跟着 Lead 每次重剪而变，所以**文档不钉那两个数**：只要插入的代码相同，那一行就从 `skip` 变绿。最近一次实测是 1033 B / sha256 `983f1e2e…`：

```
ok   27 series carries the patch   SERIES OK 0531-k60-audio-amp-probe-call.patch 1033 B sha256 983f1e2e… inserts the emitter code
ok   27 series carries the patch   SERIES HOLD: 0531-k60-audio-amp-probe-call.patch sits in /mnt/e/hackios/k60-gates/patches/xnu-12377 unlisted, and the series file says why: …
ok   27 series carries the patch   SERIES OK 0531-k60-audio-amp-probe-call.patch 1033 B sha256 983f1e2e… inserts the emitter code (held, not listed)
```

这条门禁现在每一次预检都会重新证明「系列里那份 = 生成器那份」，Lead 以后改 series 时不会静默漂移。
### 如果系列先打上了：两边都不许再写一次

真实 27 流水线里 0531 由系列打，手工 `--hook-init` 只是没有系列时的路。两条路撞在一起时：

- applier 先数 `pong_audio_amp_probe()`：已有 1 处就打 `bsd_init already hooked (probe calls 1)` 并**不写**，退出 0；
- emitter 认出「树里有调用、但不是本块的写法」→ 退出 **3** 并打
  `bsd_init.c already calls the probe outside this block (the series form); nothing to emit`；
- 预检里 `27 patch emits unchanged` 因此从 `ok` 变 `skip`（`optional_row` 把 3 当「没有可量的东西」，既不冒充红也不冒充绿）。

2026-11-20 08:40 在一棵「按系列顺序打到 0531」的树上实测过：applier 报
`bsd_init already hooked (probe calls 1)`、调用行数前后都是 1，emitter 退出 3。
那棵树是把 `series` 逐条往一份纯净的上游副本上打出来的（44 条里 15 条应用成功，
0531 落在 `bsd/kern/bsd_init.c:716-719`；其余 29 条是别的线的前置文件不在裸源树里，不是音频的事）。

### 顺序也算一遍：前面有没有人改这几行

0531 的 hunk 靠上下文行定位（`bsd_init_kprintf("calling vfsinit\n");`）。如果系列里排在它前面的某个补丁
也改这几行，那么 0531 单独 `git apply --check` 能过、按系列顺序排到它时却过不去。
所以 `check-audio27-series.py` 现在多做一件事：把系列文件里排在 0531 之前的每一项，按文件取 hunk 覆盖的
旧文件行区间，与 0531 自己的区间直接比（unified hunk 本来就带三行上下文，不必再放宽）：

```
SERIES ORDER OK: 2 earlier patch(es) touch the same files, none inside the call site context
SERIES OK 0531-k60-audio-amp-probe-call.patch 806 B sha256 3665a972… matches the emitter
```

实测：真实系列里排在它前面、也改 `bsd/kern/bsd_init.c` 的是 `0502-k60-bt-qbt-bsd-init.patch`（hunk 在 1323）
与 `0509-k60-bt-s3-identity-publish.patch`（1316），而 0531 在 699 —— 两个函数相隔六百多行。
另在真树副本上把整条系列按顺序重放过一遍（个别 bt 补丁因缺前置源文件不过），0531 仍然落在
`bsd_init()` 那句 `calling vfsinit` 之后，探针调用在 `bsd_init.c:712-715`。

哪天有人把改这几行的补丁排到前面，这一行会变成 `SERIES FAILED: <补丁> edits bsd/kern/bsd_init.c:<行>…`；
宿主测试里两例正是这么造的（远处改一行 → OK；改到调用点那几行 → FAILED），共 7 例。`27 series checker is honest`（5 例宿主测试）与
`27 series carries the patch`（需要 `XNU27_REPO`；系列还没 book 时打印 skip）。

若系列把 0531 注释掉了、但注释里点了它的名，这一行打印 `SERIES HOLD: … and the series file says why: …`；
末行是 `SERIES OK … (held, not listed)`，退出码 0。**有记录的暂缓是一种状态，不是失败**：把「Lead 决定先不列」
和「谁忘了列」在日志里分开，正是这一行存在的理由。只有「补丁在目录里、系列没列、也没有一句注释解释」才是 `SERIES FAILED`。

### 空跑一遍：这条链路在一棵「像 27 的树」上走通

三处改动是**有顺序的**（复制 → 列进 conf/files → 编宏），第四处（`--hook-init`）接在后面，
单点检查都绿也可能整体走不通；
而 27 树恰好没有 16 线带的 `bsd/dev/pong_buttons.c`。`scripts/tests/test-wiring-dry-run.sh`
在临时目录里造一棵这样的树（conf/files 里只有 `bsd/dev/vfs_syscalls.c` 这一行），把三处改动
按顺序走一遍：默认锚点必须失败并提示 `--anchor`、命名锚点必须把计数从 0 推到 2、`--check` 必须同意、
不带 `--hook-init` 时必须打出「编进去也不会跑」、带上之后 `bsd_init.c` 里必须正好一处调用、
复制过来的 `tests/run-tests.sh` 必须仍报 979 例。判据一行：

```sh
sh scripts/tests/test-wiring-dry-run.sh
# DRYRUN OK files=23 conf=2 init=1 tests=TESTS OK 979 cases
```

`check-audio27-preflight.sh` 已含这一步（输出行 `ok   wiring dry run`）。两个套件都接受一个工作目录参数：不给时自己建临时目录并清理，给了就用调用者的目录、不删；`tmp/host` 一路传下去，所以并发跑也各有各的二进制。预检的 `ok   host suite four times at once` 就是 `scripts/tests/test-audio27-host-concurrency.py`（三例）同时起四份，断言没有 `Text file busy`。
## 2. 谁调用、哪一行证明它被调过

| 函数 | 16 树的调用者 | 27 上的调用者 | 证明它跑过的日志行 |
| --- | --- | --- | --- |
| `pong_audio_amp_probe()` | 内核初始化，`adsp:patches/audio/0001-k60-audio-amp-probe.patch:3515`（`bsd_init.c`）调一次 | 同样是内核初始化（`--hook-init` 写进 `bsd/kern/bsd_init.c`；内容已批，承载走 27 补丁系列），**没有任何用户态进程参与** | `PongAudio: amp probe start (read pass first, then a replay pass …)`（`PongAudioAmp.c:955`），收尾 `PongAudio: amp probe done found=%u/2 …`（:970） |
| `pong_audio_amp_play()` | 内核播放图启动之后，`adsp:patches/audio/0003-k60-audio-afe-selftest.patch:717` | 27 上由「启动扬声器图的那段代码」在第一个周期前调用；图不在本清单里，所以 27 的第一版只能由内核自检（`pong_audio=1`）当调用者 | `PongAudio: amp%u play pll=%u status=0x%04x …`（:819）→ `amp%u play unmuted volume=0x%03x`（:842）→ `amp play done playing=%u/2`（:887） |
| `pong_audio_amp_stop()` | 停机路径 | 同上 | `PongAudio: amp%u stopped muted and powered down`（:866） |
| `pong_audio_tdm_pads()` | `patches/audio/0003`:1497（`pong_audio_start()`） | 27 树若没有 pinctrl 框架，仍在初始化里手动 mux | `PongAudio: TDM pad %s gpio=%u cfg 0x%08x -> 0x%08x io=0x%08x` |

两条边界：

- **用户态不参与判据。** HAL bundle 冻结，用户态按 sheng 在 27 重接；27 stage-0 只到 `bsd_init`，
  所以在 HAL 接上之前，「探针跑过、功放上电、时钟到位」这些结论必须由上面四张表的日志行自证，
  不依赖 `StartIO`、`mediaserverd` 或 AudioServerPlugIn。
- **play 不是无条件调。** 16 树上它由播放图 START 之后触发，图失败就不调（`amp play skipped; the probe
  did not bring the bus up`，:879）。27 的第一版若还没有图，就把它接到 `pong_audio=1` 自检的末尾，
  并接受「没有位时钟时 `status=0x0020`（NOCLKS）」这个中间结果。

## 3. GLINK 通道归属（跨线契约）

`adsp:drivers/PongAudio/tests/run-glink-multislot-tests.sh`（800 例）编译的是
`drivers/PongPower/QcomGlink.c` 与 `adsp:drivers/PongPower/K60AudioGlink.c` —— **power 线的源**。

- 这条测试在 27 树里归 **power 搬**，音频不复制那两个文件，也不修改它们。
- 音频这一侧只写调用方契约：`int k60_pmic_glink_send_audio(const uint8_t *, unsigned)`
  （声明在 `adsp:drivers/PongPower/K60PmicGlinkAudio.h:37`，实现在 `K60PmicGlinkAudio.cpp:47`）。
  要求（16 树上已验证的行为，见 `K60AudioGlink.h`）：通道名 `adsp_apps`；单条最大 560 B
  （GPR 上限，`K60_AUDIO_GLINK_SEND_MAX`）；intent 20 条（`K60_AUDIO_GLINK_INTENT_COUNT`）；
  返回非零即发送失败；**音频从不自己打开通道**，只调用这个函数。
- 因此 27 的验收顺序是：power 的传输先到 ⇒ 音频的图/探针才有发送路径；功放那半边任何时候都能先跑。
`scripts/check-audio27-kernel-api.py` 除了四个接口，还会在树里找这个名字的定义并把结果打出来：

```
GLINK provider: not in this tree yet (k60_pmic_glink_send_audio belongs to the power
  line; the glue links only after it lands)
API OK 4/4 xnu-12377.121.6 ac9718f: …
```

命中时打 `GLINK provider: bsd/dev/K60PmicGlinkAudio.cpp defines …`。**这一行不是判据、不会让脚本变红**：
provider 归 power，27 基线里现在没有它是正常的。它存在的意义是让「胶水还缺一个提供者」变成每次都能读到的
事实，而不是文档里的一句愿望——等 power 把它搬进 27 树，这一行自己就变了，不需要谁来改脚本。

## 4. AFE 服务在 27 上不存在（`PongAudioAfe.h` 为什么只能随测试走）

证据指针：

- `docs/research/audio/AMPS.md:1099-1105`（「镜像 ca 与 cb」段）：对 25 个 `adsp` blob 做 4 字节对齐的
  u32 扫描（脚本 `E:/k60-work/scratch/audio-work/fw-aligned.py`），`AFE_SVC_SET_PARAM_V2 0x000100fc`、
  `AFE_PORT_SET_PARAM_V2 0x000100ef`、`AFE_PORT_DEVICE_START 0x000100e5`、
  `PRM_REQ_HW_RSC 0x0100100f`、group/TDM/clock 的**全部** module/param id 都是零命中；
  只有 `GPR_APM_GET_SPF_STATE 0x01001021` 在 `adsp.b18` 里出现一次。
- `PongAudioAfe.h` 里 `pong_afe_svc_set_param()` 上方的注释：v1 封装在更早的 AM 镜像上已被
  `GPR_IBASIC_RSP_RESULT status 2` 拒绝；v2 在 bz 上是同样的 2，改语义值（16 bit、长同步、3.072 MHz）无效。

⇒ `PongAudioAfe.h` 只按 [IOS27-MIGRATION.md](IOS27-MIGRATION.md) §1b 随 host 测试走，**27 的内核接线禁止调用它**；
`scripts/check-audio-migration.py` 保证它不在可搬表里。

## 5. 仍然悬着的一件事：PCM 缓冲归属

16.x 上八轮实验的结论（`AMPS.md` 的 bk…cc 段）：SCM `MEM_PROT_ASSIGN` 会把 HLOS 移出、逐周期过户
会让整机复位、无属主 carveout 能活满 300 s 但 DSP 一条 WRITE_DONE 都不回。也就是「DSP 能不能读到
那 64 KiB」在 16.x 上没解决。

27 上这一项的判据仍然只有一行：`WRITE_DONE replies=` 是否大于 0。进 27 之前先确认两件事：

1. UEFI 是否还往 `/chosen` 发布 `pong-audio-dma`（64 KiB）；没有这块区就先补 loader 侧。
2. 27 树是否保留了 SMMU 旁路能力（stream 0x1801 路由）；没有就先只做功放半边。

## 6. 进入顺序

1. 功放探针：`amp0 id=0x2113` —— 证明 GENI I2C 通。
2. ACF 回放：`amp replay done … mismatched=0` —— 证明两颗芯片的寄存器表对得上。
3. 开关与 SYSST：`read=0x00000002`、`ampN play status=0x0011` —— 证明位时钟真的到了功放。
4. 端点与 PCM：`--playback` 判据 S2/S3/S4 + `WRITE_DONE replies>0`。

前两步不依赖 DSP，也不依赖 HAL，是 27 stage-0 一旦到 `bsd_init` 就能争取的成果。

## 7. 不做的事

- 不搬 `PongAudioAfe.h` 进内核接线（见 §4）。
- 不搬 `patches/xnu/0504`、`patches/audio/0003`：绑 16 树的文件位置与 `bsd/conf`。
- 不复制 `drivers/PongPower` 的 GLINK 源（见 §3）。
- HAL bundle 冻结，用户态按 sheng 在 27 重接——那一半的接口、注入点与 host 基线在
  [IOS27-USERLAND.md](IOS27-USERLAND.md)。
