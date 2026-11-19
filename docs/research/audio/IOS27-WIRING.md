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

## 2. 谁调用、哪一行证明它被调过

| 函数 | 16 树的调用者 | 27 上的调用者 | 证明它跑过的日志行 |
| --- | --- | --- | --- |
| `pong_audio_amp_probe()` | 内核初始化，`patches/audio/0001-k60-audio-amp-probe.patch:3515`（`bsd_init.c`）调一次 | 同样是内核初始化，**没有任何用户态进程参与** | `PongAudio: amp probe start (read pass first, then a replay pass …)`（`PongAudioAmp.c:921`），收尾 `PongAudio: amp probe done found=%u/2 …`（:970） |
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
