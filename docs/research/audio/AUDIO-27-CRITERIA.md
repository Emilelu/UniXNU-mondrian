# 音频 27 的七步可执行判据

## 一、结论

音频线的七个八步步骤现在各有一条可复跑命令、一条固定输出和一条负向用例。判据不是页面里的句子，而是 `scripts/check-audio27-criteria.py` 从源码、官方页、DTS 和记录里重新算出来的七行；记录里 `criterion_expect` 与算出的行不一致时，检查器直接报错，不让文案和事实漂移。

当前读数（2026-11-22，carry `feat/audio-ios27-carry`）：

    CRITERIA same_model OK: Pong stack recorded; K60 AW88261 0x34/0x35 differs from CS35L43; probe entry and boot arg present
    CRITERIA official OK: power.md audio section has 6 stream steps, 5 hard facts and 6 mic steps
    CRITERIA decompile OK: DT adsp 0x9fd00000+0x03100000 with 9 unmeasured zeros; amp 0x34/0x35 reset 1/3; TX core 0x30c at 19.2 MHz
    CRITERIA wide OK: 29 catalog components, none named AudioProbe/AdspProbe/PongAudio; sheng AudioReach reference recorded
    CRITERIA plan OK: three seams named; define gate is PongAudioAmp.o.json; 0531 dormant gate cited
    CRITERIA deep OK: probe order pads->mute->GCC->I2C->SE15->reset->probe; APM query 0x01001021 expects 0x02001007 status 1
    CRITERIA verify OK: preflight 58/4 rows; residue 21, hold 17, builder 13 cases recorded
    CRITERIA OK 7 of 7 step(s)

退出码 0 只表示七条判据的输入都成立；它不表示内核已构建、设备已上机或扬声器已出声。

## 二、七条判据

| 步骤 | 命令 | 固定输出（记录里的 `criterion_expect`） | 负向用例 |
|---|---|---|---|
| ① same_model | `python3 scripts/check-audio27-criteria.py --step same_model` | Pong 栈文件名、K60 `aw882xx`、CS35L43 差异、探针入口和 boot-arg 都在 | `CriteriaTest.test_same_model_fails_without_amp_token` |
| ② official | `... --step official` | 官方音频段六步、五条硬事实、麦克风六步都在 | `...test_official_fails_without_hard_fact` |
| ③ decompile | `... --step decompile` | DT 的 ADSP 基址/大小、九个 0、四颗地址/reset、TX core 0x30c/19.2 MHz | `...test_decompile_fails_with_wrong_adsp_size` |
| ④ wide | `... --step wide` | 目录 29 个组件且没有音频组件；sheng AudioReach/GENI I2C 参考已登记 | `...test_wide_fails_when_catalog_names_audio` |
| ⑤ plan | `... --step plan` | 三处构建接缝、对象记录判据、0531 dormant 门禁都在 | `...test_plan_fails_without_define_seam` |
| ⑥ deep | `... --step deep` | 探针顺序固定，APM 查询 opcode/端口/回包码固定 | `...test_deep_fails_when_probe_order_breaks` |
| ⑦ verify | `... --step verify` | 21/17/13 三组用例、预检 4 条 PAC 行、58 条总行数记录在案 | `...test_verify_fails_without_hold_case_count` |

`criterion_negative` 不写“应该失败”的描述，写的是能跑的 unittest 方法名。完整 harness 在 `scripts/tests/test-audio27-criteria.py:1`。

## 三、每条判据读什么

### ① same_model

检查器要求 `docs/research/audio/RESEARCH.md` 同时出现 `PongAdsp.cpp`、`PongAudio.cpp`、`PongWcd938.h`、`aw882xx` 和 `CS35L43`；要求 `drivers/PongAudio/PongAudioAmp.c` 有 `pong_audio_amp_probe` 和 `PE_parse_boot_argn("pong_audio_probe"`；要求 `drivers/PongAudio/PongAudioRegs.h` 有 `0x34u`/`0x35u`。这是“同型存在、同型不同芯片、K60 入口可定位”三件事，不是“Pong 能跑所以 K60 能跑”。

- Pong 的栈清单和大小在 `docs/research/audio/RESEARCH.md:11-23`。
- Pong 的 WCD938x/PM8350 真值和“采到 PCM 前不要宣布麦克风”在 `docs/research/audio/RESEARCH.md:25-40`。
- K60 两颗 AW88261 与 Pong CS35L43 的差异在 `docs/research/audio/RESEARCH.md:186-195`。
- 探针入口和 boot-arg 在 `drivers/PongAudio/PongAudioAmp.c:944-953`。

### ② official

检查器读 `UniXNU:docs/zh/porting/power.md` 的音频段：标题 `## 3. 实现音频流`、六条流步骤、五条 SM8550 硬事实、`### 麦克风采集` 和六条采集步骤。少一条就红。

- 六步流和图命令在 `UniXNU:docs/zh/porting/power.md:44-74`。
- 32 位地址/高字流索引、4 GiB、GLINK 小 intent 后大 intent、PRM 端口与 TX core `0x30c`、VA/TX macro 门控、24→19.2 MHz 修正在 `UniXNU:docs/zh/porting/power.md:76-82`。
- 麦克风六步在 `UniXNU:docs/zh/porting/power.md:87-100`。

### ③ decompile

检查器只认 `dts/mondrian.dts` 的 `pong-audio` 节点和 `drivers/PongAudio/PongAudioRegs.h` 的常量：

- `adsp-base = <0x0 0x9fd00000>`、`adsp-size = <0x0 0x03100000>`，见 `dts/mondrian.dts:54-59`。
- 节点内恰好九个未测量 0（tx master、codec reset/I2C、amp I2C、TX core clock、codec rail、mic bias、mic ADC、SWR index），见 `dts/mondrian.dts:61-70`。
- AMP0/1 reset 1/3、地址 `0x34u`/`0x35u` 在 `drivers/PongAudio/PongAudioRegs.h:47-53` 与 `:109-110`。
- TX core `0x30c`、19.2 MHz 在 `drivers/PongAudio/PongAudioRegs.h:155-157`。

九个 0 是“未测量”的显式标记，不是默认值。检查器把数量钉住，填错一个或漏填都会红。

### ④ wide

检查器数 `UniXNU:components.toml` 的 `[[component]]`，要求恰好 29 个，并要求全文没有 `AudioProbe`、`AdspProbe`、`PongAudio`；然后要求 `docs/research/audio/IOS27-SHENG-REFS.md` 有 `AudioReach` 和 `GENI I2C`。这证明“官方目录没有可直接取的音频 wheel”，不证明“官方没有音频文档”。

- 官方把 DSP/音频归到 `AdspProbe`/`AudioProbe` 的叙述在 `UniXNU:docs/zh/porting/drivers.md:45`。
- sheng 可借的 GENI I2C 与 AudioReach/HAL 范围在 `docs/research/audio/IOS27-SHENG-REFS.md:101-107`。

### ⑤ plan

检查器要求 `docs/research/audio/IOS27-WIRING.md` 同时有 `conf/files`、`apply-audio27-wiring.py`、`PongAudioAmp.o.json`、`EXTRA_MAKE_ARGS`、`check-audio27-builder.py`；要求提案页有 `check-audio27-hold.py` 和 `0531`。这是“三处接缝 + 对象记录判据 + 0531 门禁”三件事同时在场。

- 三处构建接缝在 `docs/research/audio/IOS27-WIRING.md:524-628`。
- 0531 的 dormant 门禁与解除条件在 `docs/research/audio/PAS1-CONSUMER-API-PROPOSED.md:271-299`。

### ⑥ deep

检查器在 `pong_audio_amp_probe()` 的函数体里按顺序找九个调用：

    pads_map() -> spk_switch_mute() -> gcc_map() -> gcc_gpll0_on()
    -> gcc_wrapper2_on() -> i2c_pads_take() -> se15_open(&level)
    -> amp_reset_release(PadAmp0Reset) -> amp_probe_one(0)

顺序错了就红：先释放 reset 再开总线会留下一个没有时钟的功放；先开 I2C 再投票 GCC 会在源未锁时访问 QUP。源码在 `drivers/PongAudio/PongAudioAmp.c:944-1004`。

APM 查询要求 `PONG_AFE_GPR_APM_GET_SPF_STATE`、`0x01001021u`、`PONG_AFE_GPR_APM_SPF_STATE`、`0x02001007u`、查询函数和两个端口常量都在 `drivers/PongAudio/PongAudioAfe.h:145-225`。它证明请求/回包的编码固定，不证明 DSP 真的回了 `status == 1`；后者要等 PAS1 起来。

### ⑦ verify

检查器读 `docs/research/eight-step/audio-27.toml` 的 `verify` 表：`local_verified = true`，`unit_test` 里同时有 residue 21 例、hold 17 例、builder 13 例，`artifact_check` 有 PAC 预检的 4 条行，`evidence` 记录预检总行数 58。四项都在才通过。

这三组用例各自证明的是：IOAudio2 那一个桩在 console 前不可达（`scripts/check-audio27-residue.py:1`）、0531 的 guard 今天仍是 `#if 1` 所以门禁 dormant（`scripts/check-audio27-hold.py:1`）、define 的判据必须是对象记录而不是构建脚本字面量（`scripts/check-audio27-builder.py:204-231`）。

## 四、机制先例

先例规则在 gates 仓的 `gates:docs/research/ios27/PRECEDENT-REQUIRED.md:5-25`：机制必须在 sheng、vermeer、cupid、asteroids、uke、muyu 这些已到 `bsd_init` 之后的机型上有 `仓库:文件:行`；上游或同 SoC 有人做过不算先例，自己的 fork 不算独立先例。

| 机制 | 先例 | 结论 |
|---|---|---|
| ADSP PAS1 | `sheng:package/AdspProbe.cpp:325-327`、`:573-582` | 有先例：PAS_INIT_IMAGE、PAS_MEM_SETUP、AUTH_AND_RESET 的顺序 |
| GLINK/SMP2P | `sheng:package/AdspProbe.cpp:612`、`:646` | 有先例：`qcom_glink_init` 与 channel |
| GPR/APM 就绪查询 | `sheng:package/ShengGpr.h:20-21`、`sheng:package/ShengGpr.c:84-89` | 有先例：24 B 头、GET_SPF_STATE、回包首字 1 = ready |
| SoundWire/codec 采集 | `sheng:package/AudioProbe.cpp:768-769`、`:832`、`:988-1006`、`:1021` | 有先例：TX master、SWR FIFO、VA/TX macro 门控、master start |
| 功放控制机制 | `sheng:package/ShengCs35l43.c:10-48`、`sheng:package/AudioProbe.cpp:391-416` | 机制有先例（读 ID、errata、I2S/PLL、slot/gain），芯片不同 |
| K60 AW88261 寄存器序列 | 无先例 | **停在这一层**：K60 两颗 AW88261 的寄存器序列、I2C 地址和 reset 没有同芯片成功先例；不能把 Pong 的 CS35L43 表或 sheng 的 CS35 表写成 27 构建判据 |

Pong 是 SM8475 同 SoC 参考，不是 27 成功机型，所以只用于“同型”调查，不计入机制先例。AW88261 的地址 `0x34`/`0x35` 和 reset GPIO 1/3 来自 K60 自己的 DTS/Android 音频内核，是板级事实；这不是“同芯片已成功”的先例，检查器只把它当板级输入，不当成功证明。

## 五、负向 dry-run

七个判据各有一个会红的输入。命令：

    python3 -B scripts/tests/test-audio27-criteria.py

实测输出：

    Ran 12 tests
    OK
    TESTS OK 12 cases

十二个用例是：七条判据各一个反向输入、记录 `criterion_expect` 与计算行不一致、源文件缺失、根目录不存在、`--help`。每个反向输入都只改一个事实，断言检查器以 1 退出并打印该事实的名字；没有负向用例的判据不算完成。

| 判据 | 反向输入 | 期望的失败文本 |
|---|---|---|
| same_model | 去掉 RESEARCH.md 的 `aw882xx` | `RESEARCH.md does not contain` |
| official | 去掉 `0x1001 & 0xf` | `hard facts does not contain` |
| decompile | 改错 `adsp-size` | `adsp-size` |
| wide | 目录里加 `PongAudio` | `no longer empty for audio` |
| plan | 去掉 `EXTRA_MAKE_ARGS` | `EXTRA_MAKE_ARGS` |
| deep | 删掉 `gcc_map();` | `missing 'gcc_map()' in order` |
| verify | 删掉 `hold 17 cases` | `17 cases` |

## 六、结论分档

| 档 | 内容 |
|---|---|
| 有证据（`file:line`） | 七条判据的输入都在本仓或官方页有确定位置；当前命令 rc 0，七行固定输出；12 个用例（7 个逐条负向）全过 |
| 有推断 | K60 的 AW88261 必须有自己的寄存器序列；Pong/sheng 只能借 I2C 读写、回读、reset 时序的**组织方式**，不能借寄存器值 |
| 不知道 | AW88261 的实际初始化表、rail 电压/上电顺序、SoundWire 枚举结果、APM 图 ID/模块实例、真实 PCM 是否返回；这些要 F3/F4 或上机，不在本页声称 |

## 七、怎么复跑

全部七条：

    python3 scripts/check-audio27-criteria.py

单条：

    python3 scripts/check-audio27-criteria.py --step deep

换官方检出或换记录：

    python3 scripts/check-audio27-criteria.py --unixnu /path/to/UniXNU --record docs/research/eight-step/audio-27.toml

退出码：0 全过，1 任一判据失败或记录里的 `criterion_expect` 与计算行不一致，2 根目录/参数错误。`--unixnu` 缺省依次看 `UNIXNU_REPO`、`/mnt/e/hackios/UniXNU`、仓旁 `../UniXNU`、`E:/hackios/UniXNU`；找不到带 `docs/zh` 的检出时 ②/④ 会红，不会静默跳过。

## 八、不证明什么

- 不证明内核构建成功：本页没有跑构建，stage 0 仍有意不编音频。
- 不证明设备启动或 PCM 出声：没有 fastboot、没有 console 日志、没有 PCM 波形。
- 不解除 0531 的 HOLD：guard 仍是 `#if 1`，dormant 门禁退 0 只表示“今天还不是判据”，不是“条件已满足”。
- 不证明 AW88261 的寄存器序列：同芯片先例缺失，本页把它标成“无先例”并停在接口/板级事实层。
