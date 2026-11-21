# 27 侧日志格式表：判读器要读的字段，今天到底由哪一行打印

状态：证据（`docs/research/gpu/`），2026-11-21。对应 27 树 `E:/hackios/xnekom-ios27`、
分支 `feat/xnu27-data-gate`。全部行号为该树实测，不引推断。

一句话结论：**两份草案要改的两个文件，在 27 树与本线 16.6.1 树上逐字节相同**，所以草案在
两棵树都 `git apply --check` 通过，不需要 rebase；但「今天相同」不是契约，所以这张表把判读器
依赖的每一个格式串钉到 27 侧的 `文件:行`，并写清带上草案之后它们变成什么形状。

## 1. 两棵树的一致性（先给结论，再给证据）

| 文件 | 27 树行数 | 本线行数 | `diff -u` |
| --- | --- | --- | --- |
| `drivers/PongAdreno/PongAdrenoScanout.cpp` | 213 | 213 | 空 |
| `drivers/PongMetal/PongMetalScanout.h` | 252 | 252 | 空 |

两份草案对 27 树的适用性（`git apply --check`，只检查不落盘）：

```
cd E:/hackios/xnekom-ios27
git apply --check E:/hackios/k60-gpu-27/patches/proposed/pong-scanout-offer-count.patch  # 通过
git apply --check E:/hackios/k60-gpu-27/patches/proposed/pong-metal-client-gap.patch      # 通过
```

⇒ 带上草案时**不需要先对齐两棵树**。但下面的格式串一旦在 27 树人手上被改动，草案仍会「能应用」
（上下文够近）而打印出判读器读不出的行——所以表里每一行都给了判读器的正则，改动方一眼能看出
它动了谁的输入。

## 2. 行前缀从哪来

判读器的 `STAGE`/`BENCH` 正则要求行以 `Pong Metal: ` 开头；内核那三条以 `PONG SCANOUT: ` 开头。
两个前缀分别来自两个不同的函数，**都不是**打印点自己写的：

| 侧 | 产生者 | 27 侧行号 | 事实 |
| --- | --- | --- | --- |
| 用户态 | `report(const char*,int)` | `drivers/PongMetal/PongMetalPlugin.mm:36` | `char line[768];` 在 `:45`，前缀格式 `"Pong Metal: %s status=0x%x\n"` 在 `:46`，截断时强制补换行在 `:49`，`write(2,…)` 在 `:52` |
| 内核 | `note(const char*,uint64_t,unsigned)` | `drivers/PongAdreno/PongAdrenoScanout.cpp:36` | `char text[180];` 与格式 `"PONG SCANOUT: %s sequence=%llu status=0x%x\n"` 在 `:38`，`IOLog` + ramoops 在 `:39` |

`report()` 的 `:38-45` 注释记着一次事故：缓冲 256 时速率行尾部被静默截断，飞行里读到「字段在、
值为空」，分不清 0 和「没打」。这是本表要防的同一种失败，只是发生在格式串这一层。

## 3. 判读器今天要读的字段 × 27 侧今天的格式 × 草案之后

判读器（`E:/hackios/k60-gates/scripts/judge-gpu27.py`）的正则与行号：

| 常量 | 行 | 正则 |
| --- | --- | --- |
| `STAGE` | `:70-73` | `Pong Metal: scanout frames=(\d+) at [\d.]+ s; last frame: wait=(\d+) us copy=(\d+) us done=(\d+) us(?: client=(\d+) us)?; imports=(\d+) import=(\d+) us encode=(\d+) us submit=(\d+) us\s*gpu=(\d+) us sum=(\d+) us` |
| `SCANOUT_VERSION` | `:77` | `scanout version=(\d+)` |
| `OFFERS` | `:80` | `offers=(\d+) dropped=(\d+)` |
| `CLIENT` | `:84` | `client=(\d+) us` |
| `PANEL` | `:74` | `te\s*(\d+)/s` |

### 3.1 内核侧（`PongAdrenoScanout.cpp`）

| 字段 | 27 侧今天 | 27 侧行号 | 草案之后 | 判读器要求 |
| --- | --- | --- | --- | --- |
| 帧行整体 | `"PONG SCANOUT: frame=%llu prepare=%llu us offer_and_copy=%llu us total=%llu us addr=0x%llx bytes=%llu\n"`，`char text[260]` | `:203-204`（`IOLog` 在 `:206`） | 行首插 `scanout version=%u offers=%llu dropped=%llu `，缓冲改 `char text[384]`，并在 `:206` 前加截断补换行 | 三个字段各自的正则；**不要求整体前缀之外的结构** |
| `scanout version=` | 不存在 | — | `scanout version=%u`，值取 `unsigned(mode.version)`（1 = 48 B 帧，2 = 56 B 帧） | `scanout version=(\d+)`，取值 ∈ {1,2} |
| `offers=` / `dropped=` | 不存在 | — | `offers=%llu dropped=%llu`，**顺序固定、相邻** | `offers=(\d+) dropped=(\d+)`：改序或插入别的字段会让它整体读不到 |
| `PONG SCANOUT:` 前缀 | 已存在 | `:38`（`note`）、`:204`（帧行） | 不变 | 判读器不依赖内核侧前缀，但飞行卡 grep 依赖 |

### 3.2 用户态侧（`PongMetalScanout.h`）

| 字段 | 27 侧今天 | 27 侧行号 | 草案之后 | 判读器要求 |
| --- | --- | --- | --- | --- |
| 速率行整体 | `"scanout frames=%u at %llu.%03llu s; last frame: wait=%llu us copy=%llu us done=%llu us; imports=%llu import=%llu us encode=%llu us submit=%llu us gpu=%llu us sum=%llu us"`，`char rate[512]`，随后 `report(rate,0)` | `:146-147`（`report` 在 `:153`） | `done=%llu us;` 与 `; imports=` 之间插 ` client=%llu us`，缓冲改 `char rate[640]` | `STAGE` 的可选组 `(?: client=(\d+) us)?`：**两种形状都要能解析** |
| `client=` | 不存在 | — | `client=%llu us`，值 = 两帧交来的间隔 | `client=(\d+) us`；缺席记 `unmeasured`，不记坏 |
| `Pong Metal: ` 前缀 | 由 `report()` 加 | `PongMetalPlugin.mm:46` | 不变 | `STAGE` 要求该前缀，缺了整行不匹配 |

`PongMetalScanout.h:143-145` 的注释是同一个家族的另一例：三个外层跨度曾「按毫秒算、仍标 us」，
让 48 ms 的帧读成 48 µs，把 P-234 判成「拷贝几乎免费」。格式串与单位写在同一行时，改一处就会
让判据读错数——这是本表存在的理由。

### 3.3 27 侧根本没有打印的两个字段

`abi=kernel=<v>/<size> client=<v>` 与 `gpuonly=<0|1>` 在 27 树 `drivers/`、`patches/` 下
`grep` **零命中**（`grep -rn "abi=kernel=\|gpuonly=" drivers patches`）。它们分别属于用户态 open
路径与 XNU 合成策略，不在本轮两份草案的文件里 ⇒ 带上草案之后**仍然**是 `unmeasured`，这是正确
行为，不是漏项。

## 4. 缓冲账（截断会让字段「在但为空」）

发送端算好不算数：一条诊断要穿过几层接收端，任何一层小一号，字段就变成「在但为空」。
下表每行给一层，最后两列说明它对本轮两个字段意味着什么。

| 层 | 位置 | 缓冲 / 上限 | 截断时的行为 | 对本轮字段 |
| --- | --- | --- | --- | --- |
| 内核 `snprintf`（帧行） | `drivers/PongAdreno/PongAdrenoScanout.cpp:203-204` | `char text[260]` | 无处理，`snprintf` 的返回值即「本应写多少」 | 草案改 `text[384]`，最坏 288 B；并在 `n >= sizeof(text)` 时打印 `PONG SCANOUT: line clipped n=%d of %u`，让飞行自己证否「截断」 |
| 内核 `IOLog` | 本仓无 XNU 源，见 §4.1 | 未知（不在本仓可引） | 未知 | 这就是上面那条 clip 行存在的理由：**不能假定它够大** |
| 内核 `note()` 与其 ramoops | `PongAdrenoScanout.cpp:36-39` | `char text[180]` | 同 `snprintf` | `note()` 行不参与判据，但同族风险；不进本轮字段 |
| ramoops 数据区 | `patches/xnu/0300-k60-usblog-ep0.patch:84` `PONG_RAMOOPS_DATA_BYTES (0x00200000U - HEADER)` | 2 MiB 减头部 | 追加时按剩余容量截断（`…-pong-settings-pmsg.patch:109-110`） | 单行 640 B 与 2 MiB 相比不成问题；只有整段写满才丢 |
| 用户态 `snprintf`（速率行） | `drivers/PongMetal/PongMetalScanout.h:146-147` | `char rate[512]` | 同 `snprintf` | 草案改 `rate[640]`，最坏 377 B |
| 用户态 `report()` | `drivers/PongMetal/PongMetalPlugin.mm:45-51` | `char line[768]`，前缀 `Pong Metal: ` + 后缀 ` status=0x%x\n`（25 B） | `needed >= sizeof(line)` 时强补换行；`:48-50` | 640 + 25 = 665 < 768，**够**；这就是「发送端算好、接收端也够」的那一环 |
| 控制台与 sysctl | `PongMetalPlugin.mm:51` `write(2,…)`、`:52-53` `sysctlnametomib("kern.pong_diagnostic")` | 无长度上限（写多少传多少） | 无 | 同上 |
| 遥测行 | `NativeBridgeMetalFrontend.mm:1606-1610`：`char text[200]`，`if(n>90)n=90` | **每行 90 B** | 硬截到 90 | 速率行**不能**走遥测通道；`streamTelemetry()`（`PongMetalPlugin.mm:60-73`）只搬 `S/T/G/J/V/N/F/W` 行 |
| 状态行 | `PongMetalPlugin.mm:245` `char status[240]` → `native_bridge_metal_status` | 240 B | 取决于该函数 | 与本轮两个字段无关，但同属「接收端先算好」的例子 |

**最坏长度怎么来的**：内核帧行八个数字字段，每个按 `%llu` 的 20 位上限算，加 `0x%llx`
的地址与固定文字得 288；用户态速率行十一个字段按同样口径得 377。两个数都是上界，不是实测值。

### 4.1 这一层为什么只能写到「未知」

`IOLog` 的实现在 XNU 树里（`iokit/Kernel/IOLib.cpp` 一路到 `vprintf`），本 worktree
和 `E:/hackios/xnekom-ios27` 都不带内核源码，离线拿不到它的缓冲上限与截断行为。
两条都不做才是错的：假定它够大，就把「接收端截断」重新变成静默故障；假定它不够大，
就为了一个没有证据的限制去砍字段。所以草案选第三条路——**让它自证**：一旦
`snprintf` 的返回值触到自己的缓冲，就打印 `line clipped n=… of …`。飞行里没有这行
= 内核侧没截断；有这行 = 截断发生在我们的缓冲里，且数字给出还差多少。
若要在 27 上把这条彻底定死，证据是「一次带 `PONG SCANOUT: line clipped` 的飞行」或
「拿到 XNU 源的 `IOLog` 上限并写进本表」——两者都还不在手上，所以这一格写未知，不写猜测。

### 4.2 禁用通道：遥测行的 90 B 硬截

`native_bridge_metal_telemetry()` 每行只留 90 B——`NativeBridgeMetalFrontend.mm:1606-1610`
的 `char text[200];` 之后紧跟 `if (n > 90) n = 90;`——再由 `PongMetalPlugin.mm:60-73`
的 `streamTelemetry()` 逐行喂给 `report()`。它看起来和 `report()` 是同一条路，实际短了一大截。

- **可以走**：`S`/`T`/`G`/`J`/`V`/`N`/`F`/`W` 这些计数行。最长的 `S` 行实测
  （`S c325/0 d325 p80 x4 R1040 D13292 F307 M4500k C0 B184`，usblog-20261119-151837
  的 console.log 第 3440 行）不到 90 B。
- **禁止走**：本轮要的两个字段。用户态速率行最坏 377 B、内核帧行最坏 288 B，塞进
  90 B 会被静默切一半，而且**切完仍是一行合法文本**：判读器读不到 `client=` / `offers=`
  只会在 `unmeasured` 里列一项——于是飞行一场，结论是「没观测到」，真因是仪表自己砍掉了。
- 这一节是禁令不是备忘：将来若有人把速率行改道遥测，`§4` 的表和 `judge-gpu27.py` 的
  `unmeasured` 会同时变化，但**不会报错**。发现的唯一线索是「行比字段表短」。

## 5. 漂移时怎么复核（不靠记忆）

1. `diff -u E:/hackios/k60-gpu-27/<file> E:/hackios/xnekom-ios27/<file>`——先看是否仍逐字节相同；
2. 两棵树各跑一次第 1 节的 `git apply --check`——「能应用」不等于「应用后打印的行能被判读器读」；
3. 改过格式串就把 `E:/hackios/k60-gates/scripts/check-gpu27-judge-groups.py` 拉一次：它要求每个可选
   字段都有「带它」「不带它」两份夹具，且真飞行复算的绝对值仍对得上（卡 j：`gpu` 5,983 / `sum` 8,281）。

第 3 条只覆盖夹具形状，不覆盖 27 侧源码文本；把源码也纳入检查是另一件事，按 Lead 2026-11-21 的
裁决等第一张 27 图回来再定（现在还没有 27 飞行，规则写了也红不了，P-290）。

## 6. 引用

- 27 树：`E:/hackios/xnekom-ios27`（`feat/xnu27-data-gate`），文件与行号见各表。
- 本线：`patches/proposed/pong-scanout-offer-count.patch`、`patches/proposed/pong-metal-client-gap.patch`，
  逐字段契约见 `patches/proposed/README.md`。
- 判读器：`E:/hackios/k60-gates/scripts/judge-gpu27.py`、`scripts/check-gpu27-judge-groups.py`。
- 真飞行：`E:/k60-work/evidence/usblog-20261119-151837/console.log`（卡 j，34 条 stage 样本），
  飞行卡 `docs/research/gpu/FLIGHT-CARD-20261119j.md`。
- 官方页：`porting/gpu.md` 的 `{#frame-path}`（七段证据表要求每段有可归属的等待）与
  `gpu-diagnostics.md` 的「保留的证据」表（每条证据要能指到一行日志）。
