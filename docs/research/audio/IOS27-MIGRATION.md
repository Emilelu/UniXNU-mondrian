# iOS 27 迁移清单（audio 线）

Lead 2026-11-20 定：新 main 从 iOS 27 stage-0 起步、先打通 SpringBoard，期间任何线都不往 main 合代码。
audio 线只搬「与 OS 无关」的东西：

> 只搬内核侧纯 C 模块 + host 测试 + 判据文档；AFE/TDM 参数表、ADSP blob、`0504`、`0003` 都不搬。

## 1. 可搬（纯 C，无内核头，今天就有 host 测试）

| 文件 | 行 | 作用 | host 覆盖 |
| --- | --- | --- | --- |
| `PongAudioGeniI2c.c` / `.h` | 176 / 110 | GENI I2C 控制器（FIFO、状态机、总线恢复） | 是 |
| `PongCodecLpi.c` / `.h` | 78 / 62 | LPASS LPI 时钟/电源序列 | 是 |
| `PongCodecMacro.c` / `.h` | 88 / 71 | WSA/VA macro 寄存器计划 | 是 |
| `PongCodecProbe.c` / `.h` | 237 / 122 | codec 探测与身份判定 | 是 |
| `PongCodecSwr.c` / `.h` | 201 / 133 | SoundWire 帧/端口计划 | 是 |
| `PongAudioAcf.h` | 305 | AW88261 ACF 表装载 | 是（PONG_ACF_FILE 存在时逐字节比对） |
| `PongAudioAmpProfile.h` | 172 | 两颗功放的 ACF 表（0x34 / 0x35） | 是 |
| `PongAudioAmpReplay.h` | 150 | ACF 回放序列 | 是 |
| `PongAudioPlan.h` | 149 | 探针计划（寄存器写入顺序） | 是 |
| `PongAudioPlayback.h` | 130 | 播放档寄存器计划 | 是 |
| `PongAudioRing.h` | 200 | PCM 环与槽记账（纯结构 + 内联） | 是 |
| `PongAudioTlmm.h` | 125 | 焊盘 mux/drive/输出使能计算 | 是 |
| `PongCodecPlan.h` | 335 | codec 计划结构 | 是 |

这一组是硬件契约：GENI I2C 的 FIFO 语义、AW88261 的 ACF 寄存器、TLMM 的 mux 值都不随 iOS 版本变。

## 2. 需要胶水但可搬（内核 API，非版本契约）

| 文件 | 行 | 依赖 | 说明 |
| --- | --- | --- | --- |
| `PongAudioAmp.c` | 1018 | `ml_io_map`、`PE_parse_boot_argn`、`printf`、`clock` | 功放探针、播放档与扬声器开关（`spk_switch_drive()`）；这些接口在 iOS 27 仍在，只是调用点要重接 |
| `PongAudioRegs.h` | 162 | 同上 | 寄存器地址与位域常量 |

搬的时候只换接线（谁在什么时候调用 `pong_audio_amp_probe()` / `pong_audio_amp_play()`），不动实现。

## 1b. 只为 host 测试随行

| 文件 | 行 | 说明 |
| --- | --- | --- |
| `PongAudioAfe.h` | 705 | AFE/TDM 参数表。本机固件里没有 AFE 服务（25 个 blob 对齐扫描零命中，v1/v2 封装都被 status=2 拒），所以**内核接线不许调用它**；但 `tests/test-pong-audio-geni-i2c.c:30` include 了它、979 个用例覆盖它的编码器，测试搬过去就必须带上它 |

## 3. 不搬

| 对象 | 为什么不搬 |
| --- | --- |
| `patches/xnu/0504-k60-audio-pong-audio.patch` | AudioReach 图 + GPR 编解码 + 端点选择，绑 iOS 16 树的文件位置与 `bsd/conf` 接线 |
| `patches/audio/0003-k60-audio-afe-selftest.patch` | 自检/探针脚本，依赖 0504 的结构 |
| `firmware/adsp`（adsp.b00..b25） | 固件 blob，按目标版本另配 |
| `PongAudio.driver` HAL bundle | HAL 层冻结，按 sheng 在 27 重接 |

AFE/TDM 参数表不进内核接线：它只按 §1b 随 host 测试走。

## 4. 迁移步骤与判据

1. 先在本仓跑 `python3 scripts/check-audio-sources.py`：它用真实补丁链重建 `bsd/dev`，再和
   `drivers/PongAudio` 逐字节比对（2026-11-20 的漂移就是这样发现的：`PongAudioAmp.c` 的副本比
   0001 的产物少 27 行，正好缺 `spk_switch_drive()`，而其余门禁全绿）。期望
   `OK: drivers/PongAudio matches the patch chain`。
   再跑 `python3 scripts/check-audio-migration.py --compile`：它把第 1、2 节的清单
   和 `drivers/PongAudio` 的实际文件逐一对照（目录里出现未分类文件、清单里的文件缺失、
   冻结项混进可搬表都会报错），再用 `-I.` 把五个纯 C 单元逐个 `-Wall -Wextra -Werror`
   编一遍；同时核对表里每个文件的行数（表与磁盘对不上就报错，防止文档变陈旧）。
   期望 `OK: the migration list matches the driver directory`，以及一行
   `pong guards: 1 in the portable set (1 expected, PongAudioAmp.c)`。这一行不是装饰：可搬集里
   **只允许那一条**两向守卫（`#if defined(PONG) || defined(XNU_PONG_AUDIO`）；任何文件被单独
   包进 `#if defined(PONG)`，在 27 上就整份编空，症状要等到链接期才出现。检查器对多出来的守卫
   直接报 `… guards on PONG alone; on 27 that file compiles to nothing`。
   再跑 `sh scripts/tests/portability/run.sh`：它用桩头文件把胶水文件 `PongAudioAmp.c` 编过，
   期望 `STUBS OK PongAudioAmp.c`（六个内核符号 + 三个类型的内核面）。
   这几条加上判据测试、功放 host 测试与（有 sheng 检出时的）audioreach 测试，可以用一条命令全跑：
   `sh scripts/check-audio27-preflight.sh` → 首行 `repo <path> <branch> @ <sha>`（量的是哪棵树），
   随后五十行 `ok`、一行随环境的 `skip`（`27 kernel carries the audio`，要 `XNU27_KERNEL`）。启动参数那三行（`boot argument checker is honest`、`audio boot argument is wired`、`boot arguments are documented`）量的是同一个名字在六处是否一致：驱动里的 `PE_parse_boot_argn`、镜像参数白名单、判官与 triage 的提示、接线页的「启动参数」行，以及 `BOOT-ARGS.md` 的条目。 其中两行看 `K60_GATES`——`27 driver takes the conf hook` 与 `27 driver takes the define` 量的是 `k60-gates` 里那份 27 构建驱动有没有把钩子与每目标宏交进构建，没接时说的是 `not wired yet` 而不是给一句绿；没给 `K60_GATES` 时这两行变 `skip`，总数就是四十八行 `ok` / 三行 `skip`。第三处接缝 `framework passes env to builder` 不依赖驱动，永远量。不过它要有框架检出（默认 `/tmp/UniXNU`，`UNIXNU=` 可指路）：没有时这一行变 `skip`，总数就是四十九行 `ok` / 两行 `skip`——干净 clone 的实测就是这个形状。整跑以 `PREFLIGHT OK` 收尾。若 `XNU27_REPO` 指的树已经被系列按顺序打到 0531，`27 patch emits unchanged` 会打 `skip`（emitter 退出 3，原文 `… nothing to emit`）：那棵树已经是「系列形态」，不是本块形态，没有可重新生成的东西。每一行自带它量的那棵树的身份：xnu27 那行带
   `xnu-12377.121.6 ac9718f` 与四个接口各自的 `file:line`，`27 stubs match the declarations` 带同一版本的 `STUBS OK 6/6`（桩头写得比内核宽，宿主编译就看不见窄化，见 WIRING 的桩一节），sheng 那两行带 `(c8f92b2)`，
   `27 kernel carries the audio` 报产物自己的大小与 sha256。（2026-11-20 05:3x 实测
   979 cases / 182 checks / `API OK 4/4` / `SHENG ABI OK 16/16` 全过。）这条命令还在
   **从远端重新 clone 的分支副本**里跑过一遍（`git clone --branch feat/audio-ios27-carry …`）：
   全 `ok`，说明这条分支自带它需要的一切，不依赖本仓工作树、16 线补丁或未提交文件。
   四行要一棵 27 源树（`XNU27_REPO`）：`27 kernel interfaces are there`、`27 tree has no clashing symbols`、
   `27 patch emits unchanged`、`27 series carries the patch`。；若系列把 0531 注释掉了并在注释里点名，这一行改成 `SERIES HOLD …` 加 `SERIES OK … (held, not listed)`，退出码仍是 0（详见 WIRING 的「0531 现在为什么没有列进系列」一节）最后一行装的是第三份拷贝：同一个调用块
   在系列里落地之后，它必须与生成器现算的**代码**相同（`SERIES NOTE …` 后接 `SERIES OK 0531-… <size> B sha256 <digest> inserts
   the emitter code`）；上下文宽度与注释文风是交付决定，门禁不比字节；系列还没 book 它时打印 `skip … the Lead books it and the emitter is the source`，
   而不是绿一行。系列目录默认 `/mnt/e/hackios/k60-gates/patches/xnu-12377`，`XNU27_SERIES` 可改；
   另两行要 sheng 检出：`sheng abi constants hold` 与 `sheng inject contract holds`（见 IOS27-USERLAND.md 第 7 节）；
   `27 kernel carries the audio` 要一颗产物（`XNU27_KERNEL`），sheng 那两行要 sheng 检出
   （`SHENG_REPO`）；缺了会打印 `skip`，不算失败。
2. 在 27 树里跑 `python3 scripts/check-audio-migration.py --copy <27树>/drivers/PongAudio`：
   它按同一份清单复制 §1/§1b/§2 的 21 个文件与 `tests/` 的两个文件（共 23 个），分类检查不通过时
   直接拒绝复制。本仓实测 `--copy` 到空树后，`tests/run-tests.sh` 在副本里仍是 `TESTS OK 979 cases`。
3. 跑 `drivers/PongAudio/tests/run-tests.sh`，期望 `TESTS OK 979 cases`。
4. 可选：等 power 线把 `drivers/PongPower/QcomGlink.c` 与 `K60AudioGlink.c` 迁到 27 树之后，
   再跑 `drivers/PongAudio/tests/run-glink-multislot-tests.sh`（期望 `TESTS OK 800 cases`）。
   这套件编的是 PongPower 的传输源，不随本清单走。
5. 在 27 树加一个编译单元与一个初始化调用点（不进 `patches/xnu/0504`）；接哪个点、还缺什么
   依赖，见 [IOS27-WIRING.md](IOS27-WIRING.md)。
6. 判据：`run-tests.sh` 与 `scripts/tests/test-judge-audio-capture.py` 全绿、内核编译 0 错、工作树不碰 main。

## 5. 现状

2026-11-20 02:03 在本仓实测：`run-tests.sh` = `TESTS OK 979 cases`，
`run-glink-multislot-tests.sh` = `TESTS OK 800 cases`（本轮修了 4 处 bz 遗留断言：
PRM 时钟 12.288 MHz → 3.072 MHz 两处、group/port bit width 32 → 16 两处）。

`run-glink-multislot-tests.sh` 不属于本清单：它编译 `drivers/PongPower/QcomGlink.c` 与
`K60AudioGlink.c`，那是 power 线的传输源，音频分支带上它就会跨线复制。所以 27 树里它要等
power 搬完之后才可跑；音频侧自己的门禁是 `run-tests.sh` 与 `scripts/tests/test-judge-audio-capture.py`。

同一时间做了可搬性的独立验证：把第 1 节的 18 个文件（5 个 .c 模块
—— `PongAudioGeniI2c` / `PongCodecLpi` / `PongCodecMacro` / `PongCodecProbe` / `PongCodecSwr`
——加 13 个头）拷进一个空目录，只给 `-I.`，用 `cc -std=gnu11 -Wall -Wextra -Werror -c`
逐个编译，五个单元全部 `OK`、零内核头、零警告 ⇒ 第 1 节的「纯 C」不是分类推断，是实测。
这条验证现在由 `scripts/check-audio-migration.py --compile` 复现。
搬之前要让构建打开驱动宏 `XNU_PONG_AUDIO`：胶水整体在 `#if defined(PONG) || defined(XNU_PONG_AUDIO)` 里，两个宏都不开就会把音频静默编空（27 不引入 `PONG` 机配置，见 IOS27-WIRING.md 第零道闸）
（细节与判读顺序见 [IOS27-WIRING.md](IOS27-WIRING.md) §1「第零道闸」）。
胶水文件另有 `scripts/tests/portability/run.sh`：桩头文件只声明 `ml_io_map`、`ml_io_map_wcomb`、
`printf`、`delay_for_interval`、`NSEC_PER_USEC`、`PE_parse_boot_argn` 与三个类型，
`PongAudioAmp.c` 在里面 `-Wall -Wextra -Werror` 编过（`STUBS OK`）。

## 6. 每一项在 27 上靠什么日志行证明

27 stage-0 只走到 `bsd_init`，音频结论不可能在那之前出现——**下表每一项的前置条件都是 F4
（内核走到 `bsd_init` 并开始跑 PongAudio 代码）**，没有 F4 就没有任何一条可判。有了 F4 之后，
每项用一行日志证伪或证实，仍然可以喂给 `scripts/judge-audio-capture.py`：

| 项 | 27 上的证明行 | 判读 |
| --- | --- | --- |
| GENI I2C 通路 | `PongAudio: amp0 id=0x2113 chip=AW88261` | id 在已知表即通，超时计数非零即断 |
| ACF 两半回放 | `PongAudio: amp replay done amp0=60 amp1=60 written=120 mismatched=0` | `mismatched=0` 且 dev_index 与地址配对（0x34→1、0x35→0） |
| 扬声器开关 | `PongAudio: amp spk switch gpio=52 on=1 … read=0x00000002` | 回读 0x2 才算拉高 |
| I2S 端点 / 位时钟 | `--playback` 判据 S2/S3/S4 + `ampN play status=0x0011` | S 全过、status 含 PLLS\|CLKS 才算拿到时钟 |
| PCM 周期 | `WRITE_DONE replies=` > 0 | 0 表示 DSP 没消费，与 16.x 上的八轮结论同形 |

这些行在 27 上第一次出现的位置由 ROUTE-A 的 stage 定义决定，本表只钉「用哪一行判」，
不假设它出现的时机。

判据不用人眼看日志：一次捕捉目录就是全部输入，退出码三档——

```sh
python3 scripts/judge-audio-capture.py --playback E:/k60-work/evidence/usblog-<ts>/
# 0 = PASS（扬声器图 open/start 与 PRM 时钟都应答、开关读回 0x2）
# 1 = FAIL（走到了那段分支，某条判据没过）
# 2 = INVALID（没有可判的东西：日志缺失/为空，或分支根本没跑）
```

目录里的日志名不必须是 `console.log`——手工并目录后叫 `console-1.log` 或 `<ts>.log`
也能判，脚本取最大的 `*.log`；空目录给 2，不会伪装成 0 或 1。

上面那条是 **16.x 的 `--playback`**。在 27 上，F4 之后的第一个判据是**无 flag 的探针模式**：

```sh
python3 scripts/judge-audio-capture.py E:/k60-work/evidence/usblog-<ts>/
# 0 = SUCCESS：探针跑完、found=2/2、两个 id 都在已知表
# 1 = FAIL：走到了探针但硬件答案不对（GPLL0 没锁、总线没起、id 不认识）
# 2 = INVALID：没有任何 PongAudio 行——系列没打 0531 或启动参数没带 pong_audio_probe=1
```

2 在这里是「这次捕捉对硬件什么都没说」，不是「硬件坏了」。

判决之后再问一步：`python3 scripts/triage-audio27.py <evidence 目录> --kernel <这次飞的 kernel.macho 或 boot.img>`
把产物判据和判决合起来，末行 `NEXT:` 直接说下一步（跑 `--replay`、看停住前那一行、补启动参数、
还是先接线再 build）。不给 `--kernel` 时它说 `pass --kernel`，不猜。

