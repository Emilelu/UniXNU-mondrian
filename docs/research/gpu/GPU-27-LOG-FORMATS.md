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

| 行 | 最坏长度 | 草案缓冲 | 余量 | 备注 |
| --- | --- | --- | --- | --- |
| 内核帧行 | 288 B（八个字段各按 20 位 + `0x` 地址） | 384 B | 96 B | 另加截断补换行，避免截断行粘到下一条 |
| 用户态速率行 | 377 B（十一个字段） | 640 B | 263 B | `report()` 自己还有 768 B 缓冲与截断补换行 |
| `note()` 行 | < 180 B | 180 B | — | 不参与判据 |

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
