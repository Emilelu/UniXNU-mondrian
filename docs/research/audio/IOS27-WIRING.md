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
