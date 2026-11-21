# 27 线 GPU 离线判读器 / 门禁草案

第三件产出。它不是「再造一个 judge 脚本」，而是把**判据字段**钉死：哪些字段现在就能
从日志里读、哪些要先加打印、哪些必须有 dyld cache 才能判。字段来源按官方
`gpu-diagnostics` 页的七类保留证据与导出清单来，不按我们的方便来。

## 0 三条不变量

1. **判不了就退 2，不退回 0。** 缺输入、缺字段、导出目录缺文件，都是「判不了」（P-279）。
2. **每个数字都要有口径。** 带宽必须写「只算扫描出侧」还是「读写两侧」；帧率必须写
   「按实测面板周期」还是「按 8,333 µs」——两种口径能差 5%（面板实测 7,385–7,679 µs）。
3. **判据字段先于判据结论。** 没有 `offers=` 就判不出交付够不够，那就先加打印，
   不是先写阈值。

## 1 三个输入面（判读器只吃文件，不碰设备、不联网）

| 输入 | 形态 | 来源 | 谁产生 |
| --- | --- | --- | --- |
| A 控制台日志 | 文本 | `read-sheng-log.py --wait 60` 的产物，或 CDC-ACM 抓取 | 内核 + presenter + 驱动 |
| B 诊断导出包 | 目录，≤8 MiB | `sheng-diag-export=240` 一次性导出：`gpu.trace.bin`、`kernel.latency.bin`、`kernel.rings.txt`、`kernel.boalloc.bin`、`kernel.cpus.bin`、`kernel.ptime.bin`、`kernel.touch.bin`、`kernel.client.bin`、`backboardd/frames.trace`、崩溃报告、`diag-skipped.txt` | 内核经官方导出器 |
| C 飞行卡 | Markdown | `docs/research/gpu/FLIGHT-CARD-*.md` 的读数段 | 人写，判读器只做交叉核对 |

A 是主输入，B 只在 A 的字段不够时用，C 永远不参与判决（它是人写的摘要，只能用来复核）。

## 2 字段表（官方证据类 → 我方字段 → 判据）

「官方类」列是 `gpu-diagnostics` 页七类保留证据的编号（1 前台大块分配、2 后台预留、
3 提交前延迟、4 释放与完成处理、5 后台并发与异常、6 GPU pass 耗时、7 显示更新空档）。

| 字段 | 官方类 | 从哪读 | 判据（通过条件） | 红的样子 |
| --- | --- | --- | --- | --- |
| `import=<us>` `encode=<us>` `submit=<us>` `gpu=<us>` `sum=<us>` | 6 | A：`Pong Metal: scanout bench n=<i>/<n> import=… encode=… submit=… gpu=… sum=…` | `gpu` 中位 < 3,000；`sum` 中位 < 6,000（卡 l 的 S3/S4） | `sum` ≥ 8,333 即单帧超预算 |
| `frames=<n>/<ms> (<x> a second)` | 7 | A：`Pong Metal: scanout frames=…` | 稳态 ≥ 110/s（`PANEL_MIN`） | 20/s 级 = 回落 CPU 合成 |
| `copy=<us>` `wait=<us>` `done=<us>` | 3,7 | A：present 整段与等待段 | `wait` 是客户端交帧时间，单独记账，不并入 `copy` | `copy` 里混进 `wait` 会得出「present 慢」的错误结论（卡 j 已踩） |
| `MiniIOMobileFramebuffer: <n> frames … <us> each in the driver, after <us> waiting for the GPU` | 7 | A：我们给 Apple 替身加的统计 | `waiting` 必须 ≤ 数十 µs | `waiting` 大 = 真的在等 GPU；小 = CPU 合成墙（实测 1 µs / 13,183 µs） |
| `scanout version=<v>` | — | A：（待加）presenter 启动时打印读到的 `mode.version` | `v ∈ {1,2}` 且两侧一致 | 见 `GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.4 三条 fail-closed 形态 |
| `abi=kernel=<v>/<sizeof> client=<v>` | — | A：（待加）userclient open 与 client open 各打一行 | 内核与客户端同 `v`、同 `sizeof` | 只差一版就 `kIOReturnUnsupported`（`NativeAdrenoUserClient.cpp:67`） |
| `offers=<n> dropped=<n>` | 3 | A：（待加）`pong_scanout_frame` 两个 `return 0` 分支计数 | 120 帧/秒时 `dropped` 必须为 0 | 非 0 = 交付窗口不够（单 pending 槽） |
| `gpuonly=<0/1>` | — | A：`pong_gpu_only` 生效值 | 判 120 fps 时必须为 1 | 为 0 时结论里必须写「含 CPU 合成回落」 |
| `client=<us>` | 6 | A：（待加）第 1 段计时 | ≤ 8,333 µs | 大于则再快的 present 也到不了 120 |
| `panel_period=<us>` | 7 | A：`K60 PANEL: … te 120/s … period <us>` | 记下来作为本帧预算 `T` | 面板 7,385–7,679 µs 与名义 8,333 差 5% |
| `DeviceLost` / `fault` 串 | 5 | A | 出现即整轮无效 | 任何 `DeviceLost` 都先判 validity 失败 |
| `GPU level vote from gperf` | 6 | A | 出现 = GMU 调档生效 | 不出现 = 仍在默认档 |
| pass 尺寸/渲染模式/附件 | 6 | B：`gpu.trace.bin`（`decode-gpu-trace.py`） | 与 A 的 bench 段自洽 | 导出解码失败 = 判不了 |
| 内存/分配/页准备/设备锁 | 1,2,4 | B：`kernel.boalloc.bin` | 前台大块分配有 backing 句柄复用 | 每次新分配 = 映射泄漏 |
| CPU 占用/最忙线程/异常寄存器 | 5 | B：`kernel.cpus.bin` + `kernel.client.bin` | 仅在 validity 失败时读 | — |

**只在 B 出现、A 不出现的字段**一律不算通过：官方导出是一次性快照（`sheng-diag-export=240`），
不能拿它证明稳态。

## 3 判决阶梯（与既有 `judge-gpu-perf.py` 同构，四层）

| 层 | 问题 | 判据 | 失败退出码 |
| --- | --- | --- | --- |
| L1 validity | 这一轮飞行本身能不能用 | 无 `DeviceLost`、无 fault 串、构建标识一致（运行时转换器 + Turnip 的 `LC_UUID`）、日志里有面板周期 | 3 |
| L2 path | 走的是哪条路径 | `gpuonly` 值、`scanout version`、`abi` 双侧、渲染模式行 | 3 |
| L3 numbers | 数字够不够 | §2 的阈值表（bench 中位、帧率、`gpu`、`sum`） | 1 |
| L4 judge | 结论 | 全绿才 0；缺输入 2 | 0/1/2/3 |

**退出码约定**（跟 `judge-gpu-perf.py` 一致，不另立一套）：`0` 通过、`1` 数字不达标、
`2` 判不了（缺输入/缺字段/导出缺文件）、`3` 本轮无效（validity/path 层失败）。

## 4 七条 G-* 判据的落地形式

来自 `docs/research/gpu/GPU-27-CONTRACT-DIFF.md:220`（§11），这里只写「用什么字段判」：

| 判据 | 字段 | 通过 |
| --- | --- | --- |
| G-ABI | `abi=` 行 | 双侧 `v` 与 `sizeof` 相同 |
| G-PUBLISH | 启动行 `real IOAcceleratorES provider published` | 出现一次，且之后无重复发布 |
| G-SELECTOR | `[gpu client text]` 首个问题行 | 无该行；或该行为已知无害项白名单 |
| G-HWCG | 启动后 `RBBM_CLOCK_CNTL` 回读值 | `0x8aa8aa82`（与 27 kit 的 `gpuHwInit()` 同判据） |
| G-FRAMEPATH | 七段中的五段有数 | 缺段要写明缺哪段（官方 §frame-path 的七行即账本行） |
| G-SCANOUT | `scanout version=` + 无 `BadArgument` | 版本 ∈ {1,2} 且 `PongScanoutNotSubmitted` 不连续出现 |
| G-DIAG | 导出包齐全 | 九个文件都在，`diag-skipped.txt` 里的跳过项要能解释 |

## 5 离线判不了的三块（必须以 2 退出，不许写成通过）

1. **Metal 用户态 selector 面**（`GPU-27-CONTRACT-DIFF.md:178` U1）：要 24A446
   `dyld_shared_cache_arm64e` 才能跑 `audit-metal-api-surface.py`。字段级输入契约见那份文档 §10.2。
2. **26 个 `fb_*` 之外的 27 WindowServer 是否仍驱动 `show`/`armVSync`**（U2，同 §10.1）。
3. **A730 上 12 行 HWCg 的行为方向**（U3）：判据本身可离线写（`GPU-27-CONTRACT-DIFF.md:216`），
   但结论要上机。

## 6 回归夹具（现在就有，不必等 27）

草案落地时用三轮既有飞行做夹具，判读器必须给出**已知的**结论：

| 夹具 | 来源 | 期望 |
| --- | --- | --- |
| 卡 j | `E:/k60-work/evidence/usblog-20261119-151837` | L1 通过、L2 判为含 CPU 合成、L3 数字红（20/s），退出 1 |
| bench 24 | `E:/k60-work/evidence/usblog-20261119-173454/console.log:2455-2506` | bench 中位 import 27 / encode 3,059 / submit 362 / gpu 2,470 / sum 5,907 → S3 绿、S4 绿（5,907<6,000）、整体退出 1（因缺 120 fps 侧证据） |
| P-241 飞行 | `E:/k60-work/evidence/usblog-20261119-044558` | L1 通过、L3 红（8.4 fps），退出 1 |

三条夹具的作用是防「判读器永远为红」（P-290 家族）——它必须在已知坏的飞行上红，
在已知好的段落上绿。

## 7 与官方检查脚本的分工

* `check-gpu-trace.py`、`check-native-adreno-scheduling.py`（官方，`scripts/`）：判**内核环
  与调度**的格式与不变量，输入是导出包，属于 G-DIAG/G-FRAMEPATH 的一半。
* 本草案的判读器：判**帧预算与路径选择**，输入是控制台日志，属于 G-FRAMEPATH 的另一半
  + G-ABI/G-SCANOUT/G-PUBLISH。
* 两者不重复：官方脚本对 `gpu.trace.bin` 的结论直接作为本判读器 G-DIAG 的输入，不重算。

## 8 落地顺序（原计划，已被 Lead 提前批准，见 §8.1）

1. 先加五处打印（`offers`/`dropped`、`gpuonly`、`client`、`abi`、`scanout version`）——
   它们同时是缺项表 `GPU-27-BUDGET-120FPS.md:241` 里的第 1、4、5 项。
2. 判读器本体写成 `scripts/judge-gpu27.py`（k60-gates 的资产，本线只出规格），
   用 §6 三条夹具做回归。
3. 门禁接线：`RULES.toml` 的 P-29x 由 Lead 分号，判据文本就是 §3 的四层表。

### 8.1 第 2 步已落地（2026-11-21，Lead 授权）

| 项 | 落点 | 状态 |
| --- | --- | --- |
| 判读器 | `E:/hackios/k60-gates/scripts/judge-gpu27.py`（commit `e286c58d`） | 已落地 |
| 回归夹具 | 同仓 `scripts/tests/fixtures/gpu27/` 三份（见 §6） | 已落地 |
| 回归测试 | 同仓 `scripts/tests/test-judge-gpu27.py` ⇒ `TESTS OK: 3 cases, plus a missing file and the json form` | 通过 |
| 仓库路径门禁 | `python3 scripts/check-repo-paths.py` ⇒ 389 文件 / 0 error / 15 warning（全为既有 sibling 路径 warn） | 通过 |

跑法（判据文本的唯一权威形态）：

```sh
python3 scripts/judge-gpu27.py <evidence dir | console.log> [--json]
```

三态与退出码还是本文件 §3 那一套：`PASS` 0 / `FAIL` 1 / `INVALID` 3 / 读不了 2。

### 8.2 第 1 步的两份离线草案（2026-11-21，Lead 授权写、不占 RULES 号、不进 series）

| 草案 | 落点 | 供判读器的字段 | 离线验证 |
| --- | --- | --- | --- |
| `patches/proposed/pong-scanout-offer-count.patch` | `drivers/PongAdreno/PongAdrenoScanout.cpp` | `scanout version=`、`offers=`、`dropped=` | `git apply --check` 通过 |
| `patches/proposed/pong-metal-client-gap.patch` | `drivers/PongMetal/PongMetalScanout.h` | `client=<us> us` | `git apply --check` 通过 |

字段形状不是猜的，是用判读器自己验的：把这两行按草案将要打印的形态写进一份临时日志后，
`judge-gpu27.py --json` 的 `unmeasured` 从 `['client us']` 变成 `[]`；只留这两行、
不留 `Pong Metal:` 那几条时，`unmeasured` 只剩 `['abi', 'gpuonly']`——也就是说草案覆盖的
三个字段确实被解析成「已观测」，而 `abi` 与 `gpuonly` 分属另外两棵树（用户态 open 路径、
XNU 合成策略），本线不改。两份草案**都未编译**：本线禁止构建，`git apply --check` 是离线能给的
最强说法，也是这里唯一声称的东西。

两条实现上的取舍写在这里，免得下一轮被当成缺陷：

- **三态是打印出来的字，不只是退出码**：`PASS`/`FAIL`/`INVALID` 各有一行 `verdict:`，
  门禁或人读日志时不必反查退出码表。
- **缺席的字段按「未观测」报，不按「良好」算**：`scanout version=`/`abi=`/`gpuonly=`/`offers=`/`client=`
  在 16.6.1 镜像上都不打印，判读器把它们列进 `unmeasured` 并照样允许 `PASS`（因为 A、B 两半
  才是 120 Hz 的定义）；一旦某个字段出现了却与预算矛盾，就是 `FAIL`。

三个字段接上之后，判据本身也收紧了两处，都写在 `scripts/judge-gpu27.py` 里：

| 字段 | 判据 | 为什么不是「有值就通过」 |
| --- | --- | --- |
| `offers`/`dropped` | `dropped * 20 > offers` 才 `FAIL`（即丢帧超过 5%） | bring-up 期少量丢帧不可避免（渲染服务端还没阻塞在 `wait`、上一帧还没 retire）；稳态 5% 不可接受，因为被拒的帧根本没有画。两个数都打印，换一条线还能重判 |
| `client=<us> us` | 大于 `8333 us` 即 `FAIL` | 这是「客户端多久交一帧」；超预算而 `gpu` 在预算内，说明瓶颈在客户端，不在拷贝 |

**两条 120 Hz 边界写进了判读器的 docstring 与正则注释，不再只写在报告里**（Lead 2026-11-21,
m01375）：①`us each in the driver` 是合成器自己在一帧内的成本、不是帧周期（30,654 µs 帧里
13,183 µs 在驱动内、约 22 ms 在等客户端交帧），所以判读器改用面板 `te N/s` 与 `client=` 回答
帧周期；②该统计的窗口是「pacing 释放 → 最后一层画完」，含交接与 `drawLayer()`、不含客户端唤醒
前的活，所以它只答「这一侧花了多少」。

### 8.3 第 1 步落地时抓到的一个真 bug

草案最初把 `client=` 插在 `done=… us;` 与 `imports=` 之间，而判读器的 `STAGE` 正则当时要求
`done=(\d+) us; imports=`——结果每一行 stage 日志都会变成不可解析：只有 bench 的飞行还好，
**只有 stage 行的飞机会被判成 `INVALID`**。这正是 P-290 家族（判据让仪表变瞎）。
修法是正则接受可选组 `(?: client=(\d+) us)?`，并加第 4 份夹具
`scripts/tests/fixtures/gpu27/gpu27-instrumented-drops-and-gap.log`：它用两份草案**将要打印的
原样行形态**，期望 `FAIL` 且同时说出 `dropped=200 of offers=800 (25.0%)` 与
`client frame took 14000 us, over the 8333 us budget`——草案与解析器从此不会再各走一路。
- **输出只用英文**：这台机器的控制台是 GBK，中文会变乱码；`单看 bench 不能判 120fps`
  这句原话保留在脚本 docstring 里，打印行给英文同义句。

## 9 引用

- 官方：`E:/hackios/UniXNU/docs/zh/porting/gpu-diagnostics.md`（§保留的证据、§采集策略、
  §导出内容、§读取与解码、§检查）、`E:/hackios/UniXNU/docs/zh/porting/gpu.md#frame-path`
- 本线：`docs/research/gpu/GPU-27-BUDGET-120FPS.md:262`（字段缺口）、
  `docs/research/gpu/GPU-27-CONTRACT-DIFF.md:220`（七条判据）、
  `docs/research/gpu/GPU-27-SCANOUT-WIRE-PROPOSAL.md:83`（三条 fail-closed 形态）
- 既有判读器（只读参考，不改）：`scripts/judge-gpu-perf.py` 的三层结构与退出码
