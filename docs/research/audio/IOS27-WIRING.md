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

### 两种布局：16 线种树，27 树原地构建

两个脚本（`apply-audio27-wiring.py`、`add-audio-conffiles.py`）都认两种布局：

- `<tree>/.cache/xnu-work/bsd/conf/files` —— 16 线构建脚本种出来的树；
- `<tree>/bsd/conf/files` —— iOS 27 输出树，直接在内核源里构建。

**锚点就是 `bsd/dev/unix_startup.c` 那一行**（该树 `bsd/conf/files:108`，后接三个制表符与 `standard`）。
不是 `bsd/dev/pong_buttons.c`：27 树没有这个文件，它只存在于 16 线的补丁系列里——下一个迁移的人
看到默认锚点失败时，第一反应会是「锚点选错了」，所以这里写死。

锚点行必须**回显**：`audio conffiles: anchor line '…'`（`repr` 形式，制表符可见）。只报
`lines 0 -> 2` 而不回显，等于没锚上（条目写进了别的段落）与锚上了在日志里长得一样——
P-171/P-245 那一族就是这样漏过去的。失败路径的顺序也不许改：先放源文件，再因锚点缺失退出 1。

在该树副本上实测：

```sh
python3 scripts/apply-audio27-wiring.py <tree> --anchor "<unix_startup.c 那一整行>"
# audio conffiles: anchor line 'bsd/dev/unix_startup.c\t\t\tstandard'
# audio conffiles: pong_audio lines 0 -> 2
# audio wiring: OK sources=9 conf=2
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
（`PongAudioAmp.c:62`，带 7 行注释说明两种来路）。两个宏是**同一份实现的两个开关**，不是两条路径：

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
——`PongAudioAmp.c:98`，x86 宿主汇编器不认），再用 `nm -g --defined-only` 数导出符号：

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
   # build-xnu-generic.sh 的 :375/:520 已经是这种写法；EXTRA_MAKE_ARGS 透传给 make。
   EXTRA_MAKE_ARGS="PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO" sh scripts/build-xnu-generic.sh
   ```

   理由是「可转移」这三个字：全局 `EXTRA_CFLAGS` 会把 `-DXNU_PONG_AUDIO` 塞给**每一个**对象，
   于是「音频的宏开没开」不再是这一条线的性质，任何一处的行为变化都可能是别人编进来的；
   每目标文件写法把定义钉在 `PongAudioAmp.c` 上，别的单元看不到它，判据才可证。
   `scripts/build-xnu-generic.sh` 是框架构建器的**逐字副本**，`scripts/refresh-xnu-generic.py`
   刷新会整体覆盖（只留文件头），所以不往里面加行——用上面的变量，或由上游把这条写进构建器。

   现存的替代口径（只在没有 `EXTRA_MAKE_ARGS` 口子时用）：`XNU_EXTRA_CFLAGS` 在脚本 :286 是
   **替换**不是追加，只写 `-DXNU_PONG_AUDIO=1` 会连 :286 的默认 `-Wno-*` 一起丢掉，
   要先把那七条拼回来再追加；:841 以 `CFLAGS_EXTRA` 交给内核 `make`（`MACHINE_CONFIGS=BCM2837`，
   :833-842），所以它到得了每个单元——这也正是上一条要避开的原因。


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
真机上再对 `amp probe start`（`PongAudioAmp.c:921`）——两者的区别是「内核里有没有这段代码」
与「这段代码跑没跑」，先证前者。

本清单的门禁不读任何 out 树（迁移清单、桩、符号、宿主探针、判据测试都在临时目录或宿主上跑），
所以不存在写死 16 线产物路径的问题；以后若加读产物的检查，路径必须取 `K60_OUT`，不许钉
`out-baseline`。


### 第四处改动：27 上谁调用它（内容归音频，承载归 27 补丁系列）

前三处让胶水**编进内核**，但没有一处让它在启动时**跑起来**。16 树上是补丁替我们做的：
`patches/audio/0001-k60-audio-amp-probe.patch:3508-3522` 在 `bsd/kern/bsd_init.c` 里插了一段

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

- 文件：`E:/k60-work/scratch/audio-27/k60-audio-amp-probe-call.patch`（876 B，sha256 `46b3c0cd4a35cb739712a1e42ea974735ba60b014fac19798e957354ae51f4bd`）
- 在真 27 源树（`ac9718f xnu-12377.121.6`）的干净副本上 `git apply --check` → `APPLY CHECK OK`
- 落位编号由 Lead 分配（不占号）；series 里建议名 `05xx-k60-audio-amp-probe-call.patch`
- 重新生成：在 27 源树的干净副本上跑 `apply-audio27-wiring.py <copy> --hook-init`，
  再 `git diff` 只取 `bsd/kern/bsd_init.c` 那一个文件；块本身来自 `INIT_BLOCK`（sha256 前 16 位
  `c41d0c6743591c9d`），改块就必须重生成补丁，两者不许分头演化

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

`check-audio27-preflight.sh` 已含这一步（输出行 `ok   wiring dry run`）。
## 2. 谁调用、哪一行证明它被调过

| 函数 | 16 树的调用者 | 27 上的调用者 | 证明它跑过的日志行 |
| --- | --- | --- | --- |
| `pong_audio_amp_probe()` | 内核初始化，`patches/audio/0001-k60-audio-amp-probe.patch:3515`（`bsd_init.c`）调一次 | 同样是内核初始化（`--hook-init` 写进 `bsd/kern/bsd_init.c`；内容已批，承载走 27 补丁系列），**没有任何用户态进程参与** | `PongAudio: amp probe start (read pass first, then a replay pass …)`（`PongAudioAmp.c:921`），收尾 `PongAudio: amp probe done found=%u/2 …`（:970） |
| `pong_audio_amp_play()` | 内核播放图启动之后，`patches/audio/0003-k60-audio-afe-selftest.patch:717` | 27 上由「启动扬声器图的那段代码」在第一个周期前调用；图不在本清单里，所以 27 的第一版只能由内核自检（`pong_audio=1`）当调用者 | `PongAudio: amp%u play pll=%u status=0x%04x …`（:819）→ `amp%u play unmuted volume=0x%03x`（:842）→ `amp play done playing=%u/2`（:887） |
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

`drivers/PongAudio/tests/run-glink-multislot-tests.sh`（800 例）编译的是
`drivers/PongPower/QcomGlink.c` 与 `drivers/PongPower/K60AudioGlink.c` —— **power 线的源**。

- 这条测试在 27 树里归 **power 搬**，音频不复制那两个文件，也不修改它们。
- 音频这一侧只写调用方契约：`int k60_pmic_glink_send_audio(const uint8_t *, unsigned)`
  （声明在 `drivers/PongPower/K60PmicGlinkAudio.h:37`，实现在 `K60PmicGlinkAudio.cpp:47`）。
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
