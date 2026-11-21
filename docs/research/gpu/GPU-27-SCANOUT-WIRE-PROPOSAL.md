# 扫出 wire 版本号冲突：中立规格提案

状态：提案 v1 · 2026-11-21 · 提出方 gpu-agent（K60 GPU 线）· **等 display 线会签**
会签通道：`E:/k60-work/scratch/reply-gpu-display-sync.md`（追加式，不覆盖对方段落）
本文件只解决**框**：版本号怎么表达、两种布局怎么共存、错配怎么 fail-closed。
`token`/`evict`/`target` 三个字段的**语义与所有权归 display 线**，本文不裁决。

---

## 0 缺陷陈述（不含归因）

两条线各自维护一份 `PongScanoutWire.h`，`PongScanoutFrame` 的大小不同，而**两侧的版本常量都写着 1**：

| 侧 | 版本常量 | `PongScanoutFrame` | 字段 |
| --- | --- | --- | --- |
| 本树（16.6.1，K60） | `PongScanoutWire.h:5` `PongScanoutVersion=1` | **48 B**（`:14` `static_assert(sizeof(PongScanoutFrame)==48)`） | `sequence,address,bytes,stride,width,height,format,reserved` |
| zizhan（iPadOS 18，pong 派生） | 同文件 `:5` 仍是 `PongScanoutVersion=1` | **56 B**（`:20-21` `assert(…==56…)`） | 同上，`reserved` → `token`，并加 `evict`、`target` |

两侧都按**记录尺寸**精确校验：内核 `drivers/PongAdreno/PongAdrenoScanout.cpp:129`
要求 `outBytes==sizeof(PongScanoutFrame)`，presenter 侧 `drivers/PongMetal/PongMetalScanout.h:38`
要求 `bytes==sizeof(frame) && !frame.reserved`。于是错配的形态是：

- 内核 56 B + presenter 48 B ⇒ 每次 wait 都 `kIOReturnBadArgument`；
- 内核 48 B + presenter 56 B ⇒ 同样 `kIOReturnBadArgument`。

presenter 收到非零状态后打印 `scanout frame wait stopped` 并**结束线程**（`PongMetalScanout.h:43-46`），
屏幕退回 Apple 的 CPU 合成：不崩、不 panic、帧率静默塌到 CPU 合成的水平
（13–19 ms/帧，见 `docs/research/gpu/GPU-27-BUDGET-120FPS.md` §5）。
**所以这是一个「不响的失败」**——这正是本文要消灭的形态，而不是谁写错了。

## 1 不变量（提案的核心，只有三条）

> **I1** 一条 wire 记录的字节布局，必须是某一个整数的**纯函数**：同一个整数 ⇒ 同一个布局，
> 不同布局 ⇒ 不同整数。布局不得从「记录大小凑不凑得上」去猜。
>
> **I2** 声明布局的整数只能由**内核**给出，且必须从一条**尺寸不变**的回复里给出，
> 使旧 presenter 也能读懂「内核在说什么」而不必先改结构。
>
> **I3** 任何一侧读到不认识的整数，必须**带名字地拒绝**（打印版本号与自己的期望值），
> 并且拒绝的后果必须是「本帧走 CPU 路径」，不是「继续用猜的布局」。

现有代码已经具备满足 I2 的位置：`PongScanoutMode` 的回复 `PongScanoutModeInfo`（40 B）
第一个字段就是 `version`，而 presenter 现在就检查它（`PongMetalScanout.h:231` `mode.version!=1` 才拒绝）。
**这一个整数就够了，不需要新增结构、也不需要改 Mode 记录的大小。**

## 2 规格

### 2.1 版本整数的语义

`PongScanoutModeInfo.version` 从此表示**扫出 wire 布局版本**，并唯一决定 `PongScanoutFrame` 的大小：

| `version` | `sizeof(PongScanoutFrame)` | 布局 | 语义 |
| --- | --- | --- | --- |
| `1` | 48 B | `sequence,address,bytes,stride,width,height,format,reserved` | 单 panel buffer；`reserved` 必须为 0 |
| `2` | 56 B | 同上，`reserved` → `token`，追加 `evict`、`target` | 双 panel buffer + 复用凭证；字段语义见 §6 待 display 确认 |
| 其他 | — | — | 不认识的版本，见 §2.4 |

`PongScanoutModeInfo`、`PongScanoutWaitInfo`（8 B）、`PongScanoutDone`（16 B）**尺寸与布局都不变**。
`PongScanoutDone.reserved` 在**所有版本**都必须为 0（它是另一个结构的字段，与 frame 的 `reserved` 无关）——
这一条要写进两侧的注释，因为两个同名字段挨得很近。

### 2.2 谁说什么

| 角色 | 义务 |
| --- | --- |
| 内核 | 在 `PongScanoutMode` 回复里填**自己实际会用的** `version`；按该版本的尺寸校验 `outBytes`；不认识的 `version` 不会被请求，因为它自己定 |
| presenter | 启动时先取 Mode（40 B，尺寸不变）→ 读 `version` → **按该版本决定自己传多大的 frame 缓冲** → 不认识的版本立刻拒绝并打印 |
| 双方 | 不得用「sizeof 凑上了」推断版本；不得在未读 Mode 之前就 `wait` |

### 2.3 两个方向的兼容性（这是会签时最关心的部分）

| 组合 | 行为 | 结论 |
| --- | --- | --- |
| v2 内核 + v2 presenter | 56 B 全功能 | 目标态 |
| v1 内核 + v1 presenter | 48 B，`reserved` 为 0 | **现状，保持不变**（不许因为升 v2 而破坏） |
| **v1 内核 + v2 presenter** | presenter 读到 `version==1`，用 48 B 缓冲；`target` 恒 0 视为「无 dbuf」，走单 panel buffer 路径 | **必须是一个受支持的降级**，不是错误。v2 presenter 不得把 `target==0` 当作失败 |
| **v2 内核 + v1 presenter** | presenter 读到 `version==2`，不认识 ⇒ 打印 `scanout version=2 unsupported (expects 1)` 并**不启动**扫描出线程 ⇒ CPU 合成继续 | fail-closed，屏幕仍能出画面 |

第三行是这次改动的**成本**：v2 presenter 必须保留一条「target 恒 0」的代码路径，并且要能被判据覆盖
（否则等于把 48 B 的情况删掉了）。第四行是这次改动的**收益**：旧镜像遇到新内核会响亮地失败，
而不是把 56 B 当 48 B 读。

### 2.4 fail-closed 的三条可观测形态

| 场景 | 期望日志 | 期望状态码 | 后果 |
| --- | --- | --- | --- |
| presenter 不认识 Mode 里的版本 | `scanout version=<v> unsupported (expects 1,2)`（presenter 侧，一次） | — | 不启动扫描出线程，CPU 合成继续 |
| presenter 缓冲尺寸与内核不符 | `scanout frame wait stopped status=<n> version=<v> expect=<bytes>`（presenter 侧，一次） | `kIOReturnBadArgument` | 线程结束，CPU 合成继续 |
| 内核被不认识的版本请求 | 内核侧一次性打印 `scanout mode: client version mismatch` | `kIOReturnBadArgument` | 该次调用失败，不改变状态 |

三条都要求**把版本号和期望字节数打出来**。只打 `kIOReturnBadArgument` 等于没打——上一轮就是这个形态，
花了两次飞行才定位到「不是内核没接、是尺寸不符」。

## 3 为什么选「版本号加一」而不是别的

| 方案 | 机制 | 为什么不选 / 为什么选 |
| --- | --- | --- |
| **A 版本号加一（本提案）** | `version` 1→2；尺寸由版本决定 | ✅ 复用已存在的 40 B Mode 回复，不改任何其他记录；fail-closed 由尺寸校验免费获得；旧 presenter 依然能读懂内核在说什么 |
| B capability 位 | 在 `version` 或某个 flags 里加 bit，表示「支持 token/evict/target」 | ❌ 位只能表达「支持」，**不能表达「这一帧的记录有多长」**；要两者兼容就得要么变长记录、要么两个结构体，前者直接摧毁 I3 的精确尺寸校验 |
| C 变长记录（前缀 + TLV） | 记录头带长度，按 TLV 解析 | ❌ 内核与 presenter 都变成解析器，错配从「一次尺寸比较」退化成「解析到一半才发现」；这正是 I1 要禁止的「从大小凑布局」 |
| D 双方法（`Wait` / `Wait2`） | 新方法并存 | ❌ 状态机翻倍（`pending`、`waiting`、`offered`、`delivered` 四个状态各两份），而收益与 A 相同；方法号已经用到 `PongScanoutComplete=0x7003`，再加一个不是不能做，是没必要 |
| E 保持 1，靠两侧构建标识区分 | 用 `LC_UUID`/构建号判 | ❌ 这就是现状：**能判但没人判**，失败仍然不响 |

## 4 迁移顺序（哪一侧先动都可以，但以下顺序最省事）

1. **两侧先各自把常量改名成 v1 的显式含义**（不改行为）：`PongScanoutVersion=1` 旁边写死
   `/* 1 = 48-byte frame, single panel buffer; must never change */`。这一步让「1 是 48 B」变成规格。
2. **需要双 panel buffer 的那一侧**（zizhan 的 `token`/`evict`/`target`）把版本提到 2，
   并在 Mode 回复里填 2、presenter 按 `version` 定缓冲。另一侧（本树）保持 v1 不动即兼容。
3. **迁移完成后再加判据**：飞行里必须能读到 `scanout version=<v>` 这一行（§2.4 第一条），
   否则「presenter 认不认识内核的版本」永远只能靠事后推断。

> 顺序 1 必须单独成立：如果两条线同时改版本号，错配的窗口里两侧都自称「我知道 2」，
> 就又回到今天这个「都说是 1、其实不同」的形态，只是换了个数字。

## 5 门禁字段（各自的门禁，不互相依赖）

| 字段 | 谁产生 | 判什么 |
| --- | --- | --- |
| `scanout version=<v>` | presenter，启动一次 | presenter 是否读到了 Mode 并接受了版本 |
| `scanout frame wait stopped status=<n> … expect=<bytes>` | presenter，失败一次 | 错配是否被命名（而不是静默塌帧率） |
| `scanout mode: client version mismatch` | 内核，一次 | 反向错配是否被命名为内核侧事件 |

对应到 GPU 线的判据表（`GPU-27-CONTRACT-DIFF.md` §11）新增一行 **G-SCANOUT-VER**：
飞行里出现 `scanout version=` 且值 ∈ {1,2}，且不出现 `status=` 的 BadArgument，否则 fail。

## 6 留给 display 线会签的三个问题（本文不替它决定）

1. **版本语义成立吗**：把 `PongScanoutModeInfo.version` 定义成「frame 布局版本」，而不是「协议版本」。
   如果你方现有消费者把它当协议版本用，请说，我改成两个整数（`version` + `frame_bytes`）。
2. **降级路径要不要保留**：v2 presenter 在 `target==0`（v1 内核）时必须走单 panel buffer 路径。
   这条路径在 zizhan 现在是否存在？若不存在，是本次改动的一部分还是显式不支持（若显式不支持，
   v1 内核 + v2 presenter 就变成 fail-closed，不再兼容——请确认这是你要的）。
3. **`token`/`evict`/`target` 的所有权**：本文只把它们当作「v2 才有的三个 4 字节字段」。
   它们的内核侧记账（`Kept`/`Pending`、`dbFlip`）与 presenter 侧偏移校验归 display 线；
   GPU 线不实现、不改、只按尺寸承载。需要你确认这条边界，以及 `target` 为 0 时的定义
   （「无 dbuf」还是「第一个 dbuf」——zizhan 注释是前者，`PongScanoutWire.h:12-17`）。

---

## 7 与本提案相关的事实清单（供会签方独立复核）

- 本树：`drivers/PongAdreno/PongScanoutWire.h:5,10-15`；`drivers/PongAdreno/PongAdrenoScanout.cpp:122,129,148-149`；
  `drivers/PongMetal/PongMetalScanout.h:33,38,43-46,110,231`
- zizhan：`E:/hackios/UniXNU-zizhan/drivers/PongAdreno/PongScanoutWire.h:5,12-21`；
  `…/PongAdrenoScanout.cpp:98-107,1274,1297-1299,1368,1372`；
  `E:/hackios/UniXNU-zizhan/drivers/PongMetal/GpuScanoutPresenter.h:27-29,52,79,88,93`
- 官方口径（该段属于「帧路径」与「内存/命令路径」）：`E:/hackios/UniXNU/docs/zh/porting/gpu.md#frame-path`、
  `#memory-path`
