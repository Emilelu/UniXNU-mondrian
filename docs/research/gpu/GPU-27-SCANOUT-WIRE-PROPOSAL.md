# 扫出 wire 版本号冲突：中立规格提案

状态：提案 v2 · 2026-11-21 · 提出方 gpu-agent（K60 GPU 线）· **display 已复「覆盖无缺口」，本文按它点的六项补全**
会签通道：`E:/k60-work/scratch/reply-gpu-display-sync.md`（追加式，不覆盖对方段落）
本文件只解决**框**：版本号怎么表达、两种布局怎么共存、错配怎么 fail-closed。
`token`/`evict`/`target` 三个字段的**语义与所有权归 display 线**，本文不裁决。

display 复签的两句原话（供复核）：**「57 槽与 48 B 包装都能覆盖、无缺口」**。
前半句里的「57 槽」我无法在两棵树里映射到任何结构（zizhan `SlotMax=8`、`KeptCount=4`、
`DbMax` 都不是 57；`PongScanoutWire.h` 里也没有 57 字节的记录），所以本文按
**「48 B 帧 + 56 B 帧两代包装都被覆盖」**理解；若「57 槽」指的是别的结构，请点名，
我再补一节——不猜。

v2 相对 v1 的增量，就是 display 点的六项：§2.1 版本位置（写明偏移）、§2.2 谁是权威、
§2.3 不匹配行为、§2.5 断言清单、§2.6 27 侧读者行号与两处硬编码、§2.7 是否碰 NGPWait。

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

**决定怎么记（写给以后想重开的人）**：display 答出「57 槽」之后，本节只加**一行 decision record**——
选了哪个形状、依据是它的哪一句（`文件:行`）、以及另一个形状为什么被排除。这里**不摆并列选项表**：
并列表会被后来的人读成「还在选」，而决定一旦写下就不该反复重开。

**版本整数长在哪里（display 六项之一）**：只在 `PongScanoutModeInfo` 的**第一个字段**，
即 40 B Mode 回复的偏移 **0**，类型 `uint32_t`。`PongScanoutFrame`、`PongScanoutWaitInfo`、
`PongScanoutDone` 三条记录**都不带版本**——它们的布局由 Mode 里那一个整数唯一决定。
理由：`wait` 的请求与回复尺寸是内核按 `sizeof` 比的（`PongAdrenoScanout.cpp:129`），
若 frame 自带版本，内核必须在知道布局之前先读它，等于把 I1 反过来用；
而 Mode 是**在 wait 之前、由 presenter 主动请求**的，且尺寸早已固定 40 B，
是唯一一个「旧 presenter 不用改结构也能读懂新内核」的位置（I2）。

Mode 的调用形态见 `PongMetalScanout.h:229-231`：`in=nullptr, inSize=0, out=&mode, outSize=40`，
先比 `size!=sizeof(mode)` 再读 `mode.version`——这两步都不变，变的是第二步接受的取值集合。

### 2.2 谁说什么

| 角色 | 义务 |
| --- | --- |
| 内核 | 在 `PongScanoutMode` 回复里填**自己实际会用的** `version`；按该版本的尺寸校验 `outBytes`；不认识的 `version` 不会被请求，因为它自己定 |
| presenter | 启动时先取 Mode（40 B，尺寸不变）→ 读 `version` → **按该版本决定自己传多大的 frame 缓冲** → 不认识的版本立刻拒绝并打印 |
| 双方 | 不得用「sizeof 凑上了」推断版本；不得在未读 Mode 之前就 `wait` |

**权威是单向的（display 六项之一）**：版本整数**只有内核能定**。它不是协商、不是握手、
也不是两侧各自声明——presenter 只做一件事：把内核给的整数映射到「我这侧要用多大的缓冲」。
由此有三条禁令，写进两侧注释：

1. presenter **不得**在 `version` 与自己的期望不符时「试试 56 B 行不行」——试就是 I1 禁止的猜布局；
2. presenter **不得**把 `mode.bytes`、`mode.stride` 反推成版本（这两项在两代里都可能相同，
   zizhan 的 5760 与本树的 5760 就一样，反推必然错）；
3. 内核**不得**因为「presenter 这次传了 56 B」就改自己的版本——内核的版本是它自己的实现事实，
   不是对端传来的信息。这一条保证「同一镜像里版本是常量」，可被断言检查（§2.5）。

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

**矩阵旁边要单独说的一句：`Done` 不带版本，帧身份靠 `sequence`。**
会签方常常只读这张矩阵，然后从「版本不匹配就失败」推出一条更宽的规则——「所有记录都必须精确等值检查」。
不必：`PongScanoutDone` 在**所有版本**里都是 16 B、`reserved` 恒 0，`PongAdrenoScanout.cpp:122`
的 `if (q.reserved || …)` 原样成立，v2 也不往它里面塞版本。

那「版本不匹配时会不会把按钮退到错误的帧上」靠什么挡住？靠同一行的
`q.sequence != pending.id`：**帧的身份是序列号**，不是版本，也不是长度。于是：

- 旧 presenter 拿旧帧号来退 ⇒ 序列号不匹配 ⇒ 拒绝，不会误退；
- 新内核多出来的 `token`/`evict`/`target` 只在 `PongScanoutFrame`（wait 的回复）里，`Done` 一个字节没变。

因此 §2.4 第 1 行（版本不认识）与第 3 行（内核被旧版本请求）是**必须**的 fail-closed，
而 `Done` 的零校验**不需要**跟着版本走——把它也改成版本条件，反而会在 v1 内核 + v2 presenter 的
降级组合里制造一条没人测过的分支。

### 2.4 fail-closed 的三条可观测形态

| 场景 | 期望日志 | 期望状态码 | 后果 |
| --- | --- | --- | --- |
| presenter 不认识 Mode 里的版本 | `scanout version=<v> unsupported (expects 1,2)`（presenter 侧，一次） | — | 不启动扫描出线程，CPU 合成继续 |
| presenter 缓冲尺寸与内核不符 | `scanout frame wait stopped status=<n> version=<v> expect=<bytes>`（presenter 侧，一次） | `kIOReturnBadArgument` | 线程结束，CPU 合成继续 |
| 内核被不认识的版本请求 | 内核侧一次性打印 `scanout mode: client version mismatch` | `kIOReturnBadArgument` | 该次调用失败，不改变状态 |

三条都要求**把版本号和期望字节数打出来**。只打 `kIOReturnBadArgument` 等于没打——上一轮就是这个形态，
花了两次飞行才定位到「不是内核没接、是尺寸不符」。

### 2.5 断言清单（display 六项之一）

这些断言必须**两侧各有一份**，且都在编译期。它们的作用不是「检查别人」，是让
「1 = 48 B、2 = 56 B」在两侧各自成为**不可漂移的事实**：只要有人重排字段，编译就红，
不必等到一次飞行里看到 `kIOReturnBadArgument`。

| 断言 | 值 | 为什么必须 | 现在有吗 |
| --- | --- | --- | --- |
| `sizeof(PongScanoutModeInfo)==40` | 40 | Mode 是版本通道，它一变，旧 presenter 就连「内核在说什么」都读不到 | 有（`PongScanoutWire.h:14`） |
| `offsetof(PongScanoutModeInfo,version)==0` | 0 | 版本必须在**固定偏移**，否则旧 presenter 要按新布局读它 | **没有，本次要加** |
| `sizeof(PongScanoutWaitInfo)==8` | 8 | 请求记录，内核按 `sizeof` 比（`PongAdrenoScanout.cpp:129`） | 有 |
| `sizeof(PongScanoutDone)==16` | 16 | 完成记录，内核按 `sizeof` 比（`:120`） | 有 |
| `offsetof(PongScanoutDone,reserved)==12` | 12 | `:122` 把偏移 12 的 `reserved` 当场判非零即错，字段一动这句就误判 | **没有，本次要加** |
| `offsetof(PongScanoutFrame,address)==8` | 8 | 三个 8 B 头字段的位置是两代共同的，v2 不得挪 | **没有，本次要加** |
| `offsetof(PongScanoutFrame,reserved)==44` | 44 | **v1 专属**：这个偏移就是 v2 里 `token` 的位置，改名不挪位是本提案的前提 | **没有，本次要加** |
| `sizeof(PongScanoutFrame)==48` | 48 | v1 布局 | 有（`:14`） |
| `offsetof(PongScanoutFrame,token)==44` | 44 | **v2 专属**：与上一条同一个数，写死两份是为了让两代各自成立 | 仅有 `sizeof==56`（zizhan `:20-21`），偏移没有 |
| `offsetof(PongScanoutFrame,evict)==48` / `target==52` | 48 / 52 | v2 专属尾部两个 4 B 字段 | 没有 |

两侧的写法建议（照抄即可，无需新增头文件）：

```c
static_assert(sizeof(PongScanoutModeInfo) == 40, "mode record is the version channel");
static_assert(offsetof(PongScanoutModeInfo, version) == 0, "version must stay at offset 0");
static_assert(offsetof(PongScanoutFrame, reserved) == 44, "v1: reserved is where v2 puts token");
static_assert(offsetof(PongScanoutDone, reserved) == 12, "the completion check is at offset 12");
```

（`offsetof` 需 `<stddef.h>`；本树 `PongScanoutWire.h` 目前没包含它，本次一并加。）

**已写成可直接粘的两份补丁**（`patches/proposed/`，草稿，不进 series，两侧都不改结构、不改运行期）：

- `pong-scanout-assert-offsets.patch` → `drivers/PongAdreno/PongScanoutWire.h`：四条 `static_assert`
  把四张记录的全部偏移、四个方法码与 `PongScanoutVersion`/`PongScanoutBgra` 钉住（`<stddef.h>` 一并加）。
- `pong-presenter-assert-offsets.patch` → `drivers/PongMetal/PongMetalScanout.h`：presenter 侧的同一批事实，
  写它**依赖**的那些（回复长度、它拒收的 `reserved`、它认的协议号），这样布局被改时红的是 presenter
  自己的编译单元，消息里点的是它的文件名，而不是只红一个头。

两份都在 27 树与本树 `git apply --check` 通过；断言文本另外用宿主 `g++ -std=c++17 -Wall -Wextra`
对同样的结构体定义编译过（`E:/k60-work/scratch/prop/wire_assert_probe.cpp`），所以偏移是编译器核过的，
不是读出来的。表里 v2 专属的三行（`token`/`evict`/`target`）不进这两份补丁——那要等 display 的 dbuf 立项，
现在加就是给不存在的字段写断言。

**v2 那三行已经写成第三份「休眠」补丁**（enabled only when the flip lands）：

- `flip condition: display signs dbuf semantics (token@44 / evict@48 / target@52) AND pong-scanout-v2-layout-asserts.patch is in series`
- `flip owner: gpu-agent (GPU line)` —— 翻 0→1 的动作属于该 owner 的提案分支，**不随 v3 或本文任何后续修订顺手改**。
- 开关为 0 时这些断言**不成立是设计，不是缺陷**：没有 v2 布局，它们就没有可描述的事实；翻了开关那天它们才成为判据（P-290 的形状：不运行的断言不是判据）。
- **flip 条件与 flip owner 只在本节维护**；`patches/proposed/README.md`、`docs/research/gpu/FLIP-READINESS.md`
  与八步 fragment 一律指回本节，不复制（P-259：抄一份就多一处会过期）。

补丁本身在两侧各一段，全部套在 `#if PONG_SCANOUT_V2_LAYOUT`（当前 `#define ... 0`）里。它**按现在的树是编译不过的，
这是故意的**：字段不存在时断言就是假事实。等 v2 立项把 0 改成 1，四个数（56 / `token`@44 / `evict`@48 /
`target`@52）在任何人构建 kext 之前就被编译器钉住。它要在 `pong-scanout-assert-offsets.patch` 之后应用
（那份带 `<stddef.h>`）；四个数本身也用宿主 C++17 对目标结构形状编译验证过
（`E:/k60-work/scratch/prop/v2_layout_probe.cpp`）。

### 2.6 27 侧读者行号与两处硬编码（display 六项之一，含它点出的两处）

27 树（`E:/hackios/xnekom-ios27`，`feat/xnu27-data-gate`）与 `feat/gpu-27` 的两个文件
**逐字节相同**，所以下面这些行号两侧通用：

| 读者 | 行 | 现在做什么 | 升 v2 时要改成什么 |
| --- | --- | --- | --- |
| 内核 · 完成校验 | `PongAdrenoScanout.cpp:122` | `if (q.reserved \|\| …)` —— `PongScanoutDone` 偏移 **12** 的 `reserved` 非零即 `kIOReturnBadArgument` | **不变**（Done 在所有版本都无版本字段、`reserved` 恒 0）。但要把这条写成注释：它守的是 Done，不是 Frame 的 `reserved` |
| 内核 · 尺寸闸门 | `:129` | `outBytes != sizeof(PongScanoutFrame)` 即 `kIOReturnBadArgument` | **不变**（`sizeof` 随版本变，闸门本身与版本无关） |
| 内核 · 填帧 | `:148-149` | `{id, address, length, stride, width, height, format, 0}` —— 最后一个 `0` 就是 `reserved`，落在**偏移 44** | v2 时**偏移 44 写给 `token`**，尾部补 `evict`、`target` 两个 4 B；v1 保持写 0。这是本提案唯一改动内核实际赋值的一处 |
| presenter · Mode 闸门 | `PongMetalScanout.h:231` | `mode.version != 1` 才拒绝（即只接受 1） | 接受 `∈ {1,2}`；不认识的整数打印版本号后拒绝（§2.4） |
| presenter · 帧闸门 | `:38` | `bytes != sizeof(frame) \|\| frame.reserved \|\| frame.format != PongScanoutBgra` | **`frame.reserved` 这一位不再无条件查**：v1 仍要求 0（它是 reserved），v2 它是 `token`、可以非零。改成按 `version` 分支，或只在 v1 路径上查——**这是最容易漏的一处**，漏了就是「v2 内核的帧一律被判坏」 |
| presenter · wait 请求 | `:33` | `PongScanoutWaitInfo wait{500}` | 不变（8 B，无版本） |

display 点出的两处硬编码，就是表里第 1 行与第 3 行：**`PongAdrenoScanout.cpp:149` 的
`Frame.reserved@44` 字面量 0** 与 **`:122` 的 `Done.reserved@12` 非零即坏参数**。
前者在 v2 下必须改成写 `token`（否则复用凭证永远是 0，等于没有凭证）；
后者必须保持原样，但要靠 §2.5 的 `offsetof` 断言钉住偏移 12。

### 2.7 是否碰 NGPWait（display 六项之一）

**不碰，而且不需要碰。** 名字核实如下（这一条我按 grep 结果原样写，不按印象写）：

| 名字 | 在 `feat/gpu-27` 与 27 树的 `drivers/` 下 | 说明 |
| --- | --- | --- |
| `NGPWait` | **零命中** | 只存在于 NGP 时代的旧客户端 `E:/hackios/UniXNU-pong/drivers/NativeMetal/GpuScanoutClient.h:70`（`NGPWait wait = {timeoutMs};`），配 `NGPMode`/`NGPSwap`/`NGPComplete` 四件套，wire 头是 `../NativeMobileDisplay/NativeGOPWire.h`——**那个头在那棵树里已不存在**（`UniXNU-pong/drivers/` 下没有 `NativeMobileDisplay`），那份客户端今天连编译都不成立 |
| `NGP_METHOD` | 两棵树各 **1 处，在注释里**：`drivers/PongAdreno/submit/NativeAdrenoPublish.cpp:51`「Methods 0x7000 + the presenter's NGP_METHOD numbers」 | 沿用下来的只有**方法号编号**，没有沿用结构体：今天的方法是 `PongScanoutMode=0x7000`、`PongScanoutWait=0x7002`、`PongScanoutComplete=0x7003`（`PongScanoutWire.h:5`） |

所以「是否碰 NGPWait」的准确答案是两层：

1. **方法层不动**：三个方法号、以及 Mode（40 B 出）/ Wait（8 B 进）的尺寸，
   本提案一个字节都不改——`NGP_METHOD` 那套编号因此原样可用；
2. **记录层只有一处随版本变**：`PongScanoutWait` 的**回复**是 `PongScanoutFrame`，
   它的大小由 Mode 里那个整数决定（48 或 56）。换句话说，**同一个方法号，两种回复长度**，
   而这正是内核 `PongAdrenoScanout.cpp:129` 用 `sizeof` 精确校验、presenter `PongMetalScanout.h:38`
   用 `bytes` 校验的地方——错配会在这里响，不会在方法号上响。

如果 display 的意思是「v2 之后 NGP 那条老客户端也要能跑」，那需要另开一题（老路径缺头文件、
缺方法号到结构体的映射），本文不覆盖，也不假装覆盖。

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

## 6 会签记录与仍待 display 回答的一问

display 已复（`reply-gpu-display-sync.md`，2026-11-21）：**覆盖无缺口**，并给出六个必填项——
本文 v2 已按六项逐条落地（版本位置见 §2.1、权威见 §2.2、不匹配见 §2.3/§2.4、
断言清单见 §2.5、27 侧读者行号与两处硬编码见 §2.6、NGPWait 见 §2.7）。
原 v1 的三个问题，display 的复签已覆盖 1 与 2（接受「frame 布局版本」语义；两代包装都覆盖）；
第 3 项（`token`/`evict`/`target` 的记账所有权）按原边界不变：**GPU 线只按尺寸承载**。

仍待回答的一问：

1. **「57 槽」指什么结构**。原文是「57 槽与 48 B 包装都能覆盖」，我在两棵树里都找不到 57：
   zizhan `PongAdrenoScanout.cpp` 里是 `KeptCount=4`、`SlotMax=8`、`DbMax`，`PongScanoutWire.h`
   里没有任何 57 字节记录。若它指「v2 的 56 B + 1 B 对齐」或某个我方没读到的表，请点名；
   若不指结构而只是「两代都覆盖」的措辞，本提案无需改动。

**一条线内规则（v3 前有效）**：display 未答「57 槽」之前，v3 停在 §2.1 之外——不用猜的槽位推进，
也不把会签文件当成可推断的输入。要改的就等那句回答，其余条目一律不动。

另两条 v1 遗留的判断，display 复签后仍然成立，一并记在这里免得重新讨论：

- **降级路径必须存在**：v2 presenter 在 `target==0`（v1 内核）时走单 panel buffer 路径，
  这条已在 §2.3 第三行定为「受支持的降级」，不是错误；
- **`target==0` 的语义**按 zizhan 注释取「无 dbuf」（`PongScanoutWire.h:12-17`），
  不取「第一个 dbuf」——两者差一次 `dbFlip`，行为差一帧。

---

## 7 与本提案相关的事实清单（供会签方独立复核）

- 本树（与 27 树逐字节相同，行号通用）：`drivers/PongAdreno/PongScanoutWire.h:5,9-15`；
  `drivers/PongAdreno/PongAdrenoScanout.cpp:122,129,148-149`；
  `drivers/PongMetal/PongMetalScanout.h:33,38,43-46,110,229-231`
- zizhan：`E:/hackios/UniXNU-zizhan/drivers/PongAdreno/PongScanoutWire.h:5,12-21`；
  `…/PongAdrenoScanout.cpp:98-107,1274,1297-1299,1368,1372`；
  `E:/hackios/UniXNU-zizhan/drivers/PongMetal/GpuScanoutPresenter.h:27-29,52,79,88,93`
- NGP 时代的老客户端（本提案不覆盖，只用来回答 §2.7）：
  `E:/hackios/UniXNU-pong/drivers/NativeMetal/GpuScanoutClient.h:70`；
  方法号沿用关系见 `drivers/PongAdreno/submit/NativeAdrenoPublish.cpp:51`
- 官方口径（该段属于「帧路径」与「内存/命令路径」）：`E:/hackios/UniXNU/docs/zh/porting/gpu.md#frame-path`、
  `#memory-path`
