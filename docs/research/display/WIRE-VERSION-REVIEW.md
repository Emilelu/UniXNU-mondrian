# wire 版本号中立法案 —— 显示线覆盖审查

Lead 2026-11-21 16:36 的裁决：版本号中立法案由 gpu27 出提案、Lead 会签，**显示线只审
「另加一个方法码承载版本（临时名「57 槽」，真名 `0x7004`，该形状已不采用）」与「48 B 包装」
两种形状是否覆盖本线全部过线字段**，不改 wire 一行。

- 审查对象：`drivers/PongAdreno/PongScanoutWire.h`（15 行）与官方
  `E:/hackios/UniXNU/drivers/GopFramebuffer/NativeGOPWire.h`（17 行）。
- 本文件只回答「覆盖 / 不覆盖」，不裁形状：实现归 gpu27，会签归 Lead。

> **一行结论（2026-11-21，回答 gpu27 的第 3 次追问）**：**不存在「57 槽」**——它不是任何头文件里的结构，
> 是我第 2 轮给「版本不塞进帧记录、另起一个方法码承载」起的临时名，真名是第五方法码 `0x7004`；
> v2 已按 56 B 帧记录定稿，这个形状没有被采纳。
>
> **对齐 `PongScanoutModeInfo` 的前提（本线认的一条）**：四条记录里只剩 `version`@0 一个版本位——
> `PongScanoutWire.h:10` 的 `version` 就是 40 B 记录的第一个字段；`Frame.reserved`@44 被内核在
> `PongAdrenoScanout.cpp:149` 写成字面量 `0`，`Done.reserved`@12 被 `:122` 当垃圾哨兵校验
> （非 0 直接 `kIOReturnBadArgument`），两处都不是空位；`WaitInfo` 加版本即 16 B，破
> `NativeGOPWire.h:16` 的 `sizeof(NGPWait)==8`。**附带条件**：`PongAdrenoScanout.cpp:75`
> 只把版本**写进** Mode、从不比较（全文件没有 `mode.version` 的判读），所以「版本只在偏移 0」
> 只覆盖内核→presenter 一个方向；presenter 必须在 Mode 时 latch 版本、对不匹配的后续帧不提交
> （内核收不到这种拒绝，`PongAdrenoScanout.cpp:129` 只对未知 op 返回 `kIOReturnBadArgument`）。

## 1. 本线过线的字段全集

四条记录，尺寸与官方逐个对齐（`PongScanoutWire.h:14-15` 的 `static_assert`：
40/8/48/16；官方 `NativeGOPWire.h:16-17` 是 8/48/16/40/32/16）。

| 记录 | 尺寸 | 字段（偏移） | 16.6.1 定义 | 官方对应 |
| --- | --- | --- | --- | --- |
| `PongScanoutModeInfo` | 40 B | `version`@0、`format`@4、`width`@8、`height`@16、`stride`@24、`bytes`@32 | `PongScanoutWire.h:10` | `NGPMode` `NativeGOPWire.h:6` |
| `PongScanoutWaitInfo` | 8 B | `timeout_ms`@0 | `PongScanoutWire.h:11` | `NGPWait` `:13` |
| `PongScanoutFrame` | 48 B | `sequence`@0、`address`@8、`bytes`@16、`stride`@24、`width`@32、`height`@36、`format`@40、`reserved`@44 | `PongScanoutWire.h:12` | `NGPSwap` `:14` |
| `PongScanoutDone` | 16 B | `sequence`@0、`status`@8、`reserved`@12 | `PongScanoutWire.h:13` | `NGPComplete` `:15` |

另有四个方法码与两个常量过线：`Mode 0x7000` / `Wait 0x7002` / `Complete 0x7003` /
`Memory 0x5343`（`PongScanoutWire.h:5-6`）、格式 `Bgra=1`、版本 `PongScanoutVersion=1`、
未提交哨兵 `PongScanoutNotSubmitted=0x4e4f444d`（`:9`）。

读点三处：`PongAdrenoScanout.cpp:75` 填 mode、`:122` 校验 Complete、`:149` 构造 Frame。

**不在 wire 上的**（先排除，免得被当成缺口）：面板刷新率与 tear-check 走 INTF
（`PongDsiPanel.cpp:84` 的八个 INTF 常量、`:136-236` `panel_intf_rate`），scanout 窗口
走 `PongScanoutMemory=0x5343` 选择子。两者都与版本号无关。

## 2. 版本号今天在哪，空位真的空吗

版本只在 mode 记录里，offset 0（`PongScanoutWire.h:10`）。`Frame` 与 `Done` 没有版本字段，
各有一个 `reserved`（`Frame`@44、`Done`@12）—— 但它们**不是空闲空间**，两处都在用：

- `PongAdrenoScanout.cpp:149` 用花括号初始化把 `Frame` 最后一位写成字面量 `0`：
  `{pending.id, …, mode.format, 0}`。
- `PongAdrenoScanout.cpp:122` 把 `Done.reserved` 当垃圾检查：
  `if(q.reserved || !pending.offered || …) return kIOReturnBadArgument;` —— 任何非零都拒收。

所以「48 B 包装」不是零改动方案：它要么改这两处，要么放弃在 `Frame`/`Done` 里带版本。

## 3. 覆盖判定

| 记录 / 常量 | 0x7004 承载（原「57 槽」，作废名） | 48 B 包装 | 判据 |
| --- | --- | --- | --- |
| `ModeInfo.version` | 覆盖 | 覆盖 | 已在 @0，两种形状都不动 |
| `Frame`（8 字段） | 覆盖 | 覆盖，**代价是改 `:149` 的初始化** | 版本进 `reserved`@44 |
| `Done`（3 字段） | 覆盖 | 覆盖，**代价是改 `:122` 的零校验** | 版本进 `reserved`@12 |
| `WaitInfo.timeout_ms` | 覆盖（不需要版本） | 覆盖（不需要版本） | 加版本即 16 B，违反 `:16` 断言 |
| 方法码 / `NotSubmitted` / `Bgra` | 覆盖 | 覆盖 | 与版本无关 |
| 官方 `NGPTransfer`(16 B) / `NGPPresent`(32 B) | 不涉及 | 不涉及 | 官方有、本线不过线 |

**结论：两种形状都能覆盖本线的全部过线字段，成本形状不同**——0x7004 动的是调用点（新方法码），
48 B 包装动的是两个已在用的校验点。**两者都没有被采纳**：v2 走 56 B 帧记录 + `ModeInfo.version`@0。

## 4. 两种形状各自必须写死的条件

48 B 包装：

1. `Frame.reserved`@44 **改名为 `version`**（不是只改注释：只改注释就没有可断言的名字）。
2. `:149` 的初始化把 `0` 换成协商到的版本号；`:122` 的零校验改成**精确等值**检查
   （`q.reserved != version ⇒ 拒收`），不能退化成「非零就收」—— 那会放掉本来要挡的垃圾。
3. 加偏移断言：`sizeof==48` 且 `offsetof(version)==44`；`Done` 同理 `offsetof(version)==12`、
   `sizeof==16`。现有的断言只有尺寸（`PongScanoutWire.h:14-15`）。
4. 版本不匹配时 `Done` 必须**拒绝 retire**（走 `kIOReturnBadArgument` 一路），否则 GPU 拷贝
   完成的事件会退掉别人的一帧。

0x7004 承载（原「57 槽」，**已不采用**，以下条件仅存档）：

1. 给出方法码常数与调用点，以及索引是否随方法码变化。
2. `Wait` 无处放版本时怎么办：加版本即 16 B，与官方 `NativeGOPWire.h:16` 的
   `sizeof(NGPWait)==8` 冲突；若提案要动这条断言，等于改官方 ABI，会签时必须写明。
3. `ModeInfo.version` 与槽位版本谁权威；两处不一致时的行为。

## 5. 本线不接受的三种写法

1. **拿哨兵或方法码当版本**：`0x4e4f444d` 是状态值，`0x7000/0x7002/0x7003` 是方法码；
   混进版本域会让 `:122` 与 `:126` 的判断失去意义。
2. **只加注释不加字段**：`:75` 与 `:149` 要能写出版本，注释做不到。
3. **把 `Wait` 撑到 16 B**：同时改掉官方断言，跨 16.6.1 与 27 两个 ABI。

## 6. 交给 gpu27 提案的六个空

| # | 提案里要有 | 为什么显示线在意 |
| --- | --- | --- |
| 1 | 版本位置：槽索引，或 `offsetof`+字段名 | 本线在 `:75`/`:149` 写、`:122` 读 |
| 2 | `ModeInfo.version` 与包装内版本谁权威 | 两处都能写时读点会分叉 |
| 3 | 版本不匹配的行为（特别是 `Done`） | 关系到 retire 是否可能退错帧 |
| 4 | 断言清单（尺寸 + 偏移） | 没有偏移断言，改名与注释无法区分 |
| 5 | 27 侧读者行号 | 27 上必须真有人读，否则等于没中立 |
| 6 | 是否触碰 `sizeof(NGPWait)==8` | 触碰即改官方 ABI，会签要写明 |

## 7. 判据（提案落地后可直接跑）

```sh
# 版本常量定义与使用点应各只有一处
git grep -n "PongScanoutVersion" drivers/
# 尺寸断言在，且要有新增的偏移断言
git grep -n "static_assert(sizeof(PongScanout" drivers/PongAdreno/PongScanoutWire.h
# 若选 48 B 包装：这两处必须一起改，不能只改一处
git grep -n "q.reserved" drivers/PongAdreno/PongAdrenoScanout.cpp
# 27 侧读者（提案给行号后替换）
git grep -n "version" <提案给的 27 侧文件>
```

## 8. 边界

- 不改 `PongScanoutWire.h`、不改 `NativeGOPWire.h`、不改断言，也不裁形状。
- 显示线**没有硬偏好**：另一种形状动调用点、48 B 包装动两个已在用的校验点，代价相当。
  若要一句建议：48 B 包装少一个新槽位常数、少一处跨文件约定，但必须先改 `:122`/`:149`。
- **用词更正（第 3 轮，见 §9）**：本文此前把「版本由另一个方法码承载」叫作「57 槽」，那个数字不来自
  任何头文件，是本文的临时命名。真名是**第五方法码 0x7004**；本文所有「57 槽」字样按 0x7004 读，
  并且**这个形状最终没有被采纳**（v2 按 56 B 帧记录定稿）。

## 9. 第 3 轮回签（2026-11-21，对应 `E:/k60-work/scratch/reply-gpu-display-sync.md` 第 136 行起）

gpu27 的 `GPU-27-V2-FIELDS.md` §3.1 要求显示线对 v2 的三个新字段逐行签「一致 / 不一致」，
理由是他们自己的话：尺寸错了编译器会红，语义错了要到「画面丢帧、错帧」才暴露，而那已经是一次白飞。
本节就是回签，判据全部给到 `文件:行`；权威副本在同步通道文件里，这里是本线存档。

### 9.1 先说用词：没有「57 槽」

- 我此前用「57 槽」指「版本不塞进 48 B 帧记录、由另一个方法码单独承载」这个形状（本文 §4、§8 旧文）。
  **这个数字不来自任何代码**：本仓 `PongScanoutWire.h:5-6` 是四个方法码、`:10-13` 是四条记录；
  官方 `NativeGOPWire.h:12` 是五个选择子；`NativeAdrenoPublish.cpp:51-54` 是四个方法码。给不出「文件:行」。
- 那个形状的真名是**第五方法码 0x7004**，接入点三处：
  `PongScanoutWire.h:5-6`（enum 加常量）、`PongAdrenoScanout.cpp:129`（未知 op 落
  `kIOReturnBadArgument`，因此 v1 内核天然拒绝 0x7004，presenter 可据此判别版本）、
  `PongAdrenoNativeGlue.cpp:20`（`op+PongScanoutMode`，op 4 即 0x7004）。不改 `sizeof` 断言、不改 wait。
- **不推荐采用**：v2 已按 56 B 定稿，0x7004 只是把「谁对数」推迟成一次额外调用，没有收益。

### 9.2 三行回签

| 字段 | 本线判 | 依据 | 附带条件（必须写进 gpu27 的文档，否则没人守） |
| --- | --- | --- | --- |
| `token` @44 | **一致** | zizhan `PongScanoutWire.h:12-14` 注释；`PongAdrenoScanout.cpp:1279` 的 `Kept` 表按 `source+offset+bytes` 命中复用 | (a) 面板模式/画布几何真变时全表作废——本线 120 Hz 切换只写 INTF 与 DCS（`PongDsiPanel.cpp:463-517`），不重建画布，所以无需清表；但任何真正换几何的 `Mode` 路径必须清表。(b) token 随映射创建生成，禁止 `source` 回收后按同 `offset/bytes` 命中旧 token——表键是三元组，回收再分配能造出同键不同块。 |
| `evict` @48 | **一致（附三条时序）** | zizhan `PongAdrenoScanout.cpp:1296-1299`（选 victim 写 `pending.evict`）、`:1372`（退休后 `drop`） | (a) evict 必须先于本帧拷贝提交生效，presenter 不得在本帧提交后再用该 import 下命令。(b) 内核在帧退休后 drop（`:1372`），presenter 收到 ack 后可继续读、不得再写。(c) 只有「同一 surface 的新映射替换旧映射」才允许非 0；几何不同（`stride`/`bytes` 变了）时必须为 0。 |
| `target` @52 | **不一致——必须改语义** | zizhan `PongAdrenoScanout.cpp:547` 是 `db[0].offset=0;db[dbN]={b,rounded};++dbN;`：`db[0]` 在 presenter 映射里的偏移就是 0；而 `dbTarget()`（`:436-456`）返回**索引**（`pick()` `:440`、`:449` `t=dbFlipped`），消费点全是索引（`db[pending.target].phys` `:1368`、`db[target].offset` `:1276`） | 见 §9.3 |

### 9.3 `target` 为什么必须改

gpu27 的写法是「扫出映射里的**字节偏移**；0 = 无 dbuf」。在它们自己的参考实现里这句话自相矛盾：

- `db[0]` 的映射偏移**就是 0**（`zizhan …:547`），所以「偏移 0」既可能是第 0 块缓冲，也可能是「没有 dbuf」；
- 内核实际传的是**索引**（`:436-456` 返回 `db[]` 下标），消费点也按索引取（`:1368`、`:1276`）；
- 后果不是措辞问题：dbuf 开启且选中第 0 块时内核发 `target=0`，presenter 判成「没有 dbuf」→ 跳过翻页
  （`:1368` 的条件是 `pending.target!=dbShown && pending.target!=dbFlipped` 才翻）→ **帧停在面板旧缓冲**。
  这正是「语义错了要到丢帧/错帧才暴露」那一类，只有白飞才看得见。

两条可实施替代，本线两条都签：

1. **索引 + 1（推荐）**：`0 = 无 dbuf`，`1..N = db[i-1]`。0 天然不可达，`db[0]` 也照样能表达；
   消费点改 `db[pending.target-1]`，只需动 `zizhan :1368` 那一行。
2. **保留偏移、换哨兵 `0xFFFFFFFF`**：真实偏移原样，`0xFFFFFFFF`（32 位字段）表示无 dbuf。
   与 zizhan 自己的「不在映射里」哨兵 `~0ull`（`:288` 注释、`:440` 判断）同口径。

### 9.4 面板周期口径（同时回答 gpu27 的预算问题）

- gpu27 的预算表里出现两个数：实测 7,385–7,679 µs 与名义 8,333 µs。**用名义 8,333 µs 作预算帧时间。**
- 实测值来自 `period` 回退字段（最短单次 line-count wrap），本线代码自己写明了为什么不能用它：
  `PongDsiPanel.cpp:223-228` —— 一个 7.6 ms 间隙算出来是 131 Hz，而同一次 500 ms 窗口里 61 个 wrap
  是 122 Hz；`panel_measured_hz` 取的是 wrap 平均（`:229`）。
- 面板健康判据读 `te <N>/s`，阈值 `te ≥ 110/s`；`period` 只作旁证。依据
  `docs/research/gpu/FLIGHT-CARD-20261119j.md:79` 同一行同时打了 `te 120/s` 与 `period 7679 us`，
  两者不一致时以 `te` 为准。

## 10. 本次回签改了本线什么、没改什么

- 改了：本节（§9、§10）与 §8 的用词更正。
- 没改：`PongScanoutWire.h`、`NativeGOPWire.h`、任何断言、任何 `patches/xnu` 文件；
  也没有改 `k60-gpu-27` 的树——`GPU-27-V2-FIELDS.md` §3.1 那三行由 gpu27 自己填并注明出处。
- 若 gpu27 按 §9.3 改 `target`，本线在这边只需要跟一件事：`zizhan :1368` 的消费点从
  `db[pending.target]` 变成 `db[pending.target-1]`（或哨兵比较），届时由 dbuf 立项统一改，不在这条线上。

## 11. v3 会签（2026-11-21，第 4 轮）

权威副本在 `E:/k60-work/scratch/reply-gpu-display-sync.md` 的「display-agent（第 4 轮）」段，
这里是本线存档。gpu27 的 v3 只动了提案 §2.1 的 decision record 1（`target` 改「索引 + 1」）
与 §6.1（「57 槽」作废），其余与 v2 逐字相同。

### 11.1 三点会签结论

| 要签的点 | 结论 | 本线给出的实现事实 |
| --- | --- | --- |
| 版本只在 `PongScanoutModeInfo` 偏移 0 | **同意** | `PongScanoutWire.h:10` 首字段即 `version`；`PongAdrenoScanout.cpp:75` 写入、`:117-118` 要求 `outBytes==sizeof(mode)` 后原样 `memcpy` ⇒ 它是 wait 前唯一通道。**但内核只写不比较**：全文件没有 `mode.version` 的判读（`:75` 写、`:129` 只比 Wait/Frame 尺寸、`:122` 只比 Done 的 `reserved`），所以这个通道只有内核→presenter 单向，presenter 必须自己 latch |
| 十条断言 | **同意** | 本树现在只有 `PongScanoutWire.h:14-15` 的四条 `sizeof`；缺 `offsetof(version)==0`、`offsetof(Done.reserved)==12`、`offsetof(Frame.address)==8`、`offsetof(Frame.reserved)==44`；v2 专属三条按休眠补丁处理 |
| `:149` 写 token、`:122` 原样 | **拆半签**：布局同意、值不同意 | `:149` 的第 8 项现在是字面量 `0`，换 `token` 只改位置语义（44 由 `offsetof` 钉住）；`:122` 是 Done 的检查（偏移 12），v2 不动。但「写什么 token、何时 evict」属 dbuf 立项（`Kept` 表 + 逐帧 map 记账），本树无此代码，所以不签「现在就写 token」 |

两条写进断言补丁注释的要求：
1. 四条记录都是标准布局 POD（只有 `uint32_t`/`uint64_t`），`offsetof` 合法；
2. `offsetof(Frame,reserved)==44` 与 `offsetof(Frame,token)==44` 是同一个数、故意两份，**不许合并**——
   合并后任何一次改名都会静默通过。

`target`@52 改「索引 + 1」：**复签同意**（我在第 3 轮签的两种替代之一），decision record 的追加式写法也对。

### 11.2 三个新问题的答复

**`format` 新取值（`2 = 直扫`）不接受**，因为它撞了三处精确比较：

| 位置 | 代码 | 后果 |
| --- | --- | --- |
| `drivers/PongMetal/PongMetalScanout.h:231` | `mode.version!=1 \|\| mode.format!=PongScanoutBgra` | 内核填 2 ⇒ presenter 连 version 都没读就 `scanout mode refused` |
| `drivers/PongMetal/PongMetalScanout.h:38` | `frame.format!=PongScanoutBgra` | 每帧 `scanout frame wait stopped` |
| `drivers/PongMetal/PongMetalScanout.h:233` | `mode.stride<mode.width*4` | 把「4 B/像素 + 线性 pitch」写进 mode 闸门，非线性 surface 会静默拒绝 |

⇒ 与 gpu27 自己否掉的「48 B 包装」是同一类成本。本线给的形状：`format` 低 16 位保留像素格式、
路径用 flag 位（`PongScanoutBgra=1`，直扫 = `1|0x10000`），presenter 比 `(format & 0xffff)==PongScanoutBgra`。
**内核侧代价为零**：本树只有 `:149` 一处读 `format`、没有任何比较（`PongScanoutWire.h:10`/`:12` 是声明）。

**单缓冲直扫作第一档够用**，但判据不能只有 `imports=0`：窗口外不是掉帧而是撕裂带。
建议 `imports=0` + `te ≥110/s` + 连续 3 秒 frame count 与 te 计数同步；现成证据面是
`PongDsiPanel.cpp:463-517`（120 Hz 切换已在动 `TearSyncVsync` 100→50）与 `:223-229`（`period` 不可用、要读 `te <N>/s`）。

**CTL 基址冲突归本线**（飞行槽归 Lead）。离线两条独立来源已重合于 `0xae16000+i*0x1000`：
本树 `PongDsiPanel.cpp:115-127` 的六页只读探针，与 sheng `DisplayTimingProbe.cpp:36` 的
`kCtl 0x15000`/`stride 0x1000`（配 `:30 kMdp 0xae01000`）；t970 的 `0x2000+0x200*n` 是另一代 catalog。
**但 INTF 页有真实的 0x1000 分歧**：本树 `:505` 用 `0x0ae35000+active*4096`（120hz-7 实测
`INTF1 55/s→120/s` 走的就是这条），sheng `kIntf{0x35000,0x36000}` 配 `0xae01000` 会落
`0xae36000/0xae37000`。解法不需要新 boot-arg：`k60_dpu=1` 本来就采 INTF 帧计数，
把两个候选页都采、各打一行，200 ms 内 frame count 前进的那页就是真的（写进
`docs/research/display/DISPLAY-27-INTEGRATION.md` §1 的探针设计）。

## 12. te 同步口径（2026-11-21，回答 gpu27 第 6 轮）

**结论：display 用自己的 INTF 行判 te 同步；`at=` 只用于 gpu27 的零拷贝窗口，不用于判 te。**

三条依据：

1. **同一条内核日志里已有同窗口的两个计数器。** `PongDsiPanel.cpp:230` 一行内同时有
   `te <c>-><d>`（`IntfTeCount` 0x298 高 16 位，读点 `:190`/`:216`）与 `frames <e>-><f>`
   （`IntfFrameCount` 0xac，读点 `:189`/`:215`），窗口长度 `over %u ms` 由 `mach_absolute_time()`
   两端（`:192`/`:218`）算出——Δte、Δframes、Δt 同源同时钟，不需要跨进程减法。
2. **`at=` 与面板侧不是同一个时钟，且是否同源离线未证。** `at=` 来自
   `PongMetalScanout.h:34/:36/:43/:112/:132` 的 `clock_gettime(CLOCK_MONOTONIC)`；面板侧是内核
   `mach_absolute_time()`。27 树没有用户态 `clock_gettime` 实现可对照（`libsyscall/wrappers/`
   有 `mach_absolute_time.s`、无 clock_gettime wrapper；`bsd/kern/kern_time.c:128-129` 只有
   `clock_gettimeofday_and_absolute_time`）。按 L12/L5 只能写「未证」，拿未证时基做减法就是
   gpu27 自己担心的「两个都大概对、没人能判」。
3. **3 秒窗口不能在 `pong_panel_sample()` 里采。** `panel_intf_rate()` 以 `IODelay(1000)` 忙等到
   `milliseconds`（`:196-212`）；`:622` 的调用点在帧退休路径（`PongAdrenoScanout.cpp:185` 每帧调
   `pong_panel_sample()`），3 秒忙等会卡住出帧。3 秒窗口放探针线程（sheng `DisplayTimingProbe.cpp:42-111`
   先 `IOSleep` 再采的模型）。

**判据契约**：探针在 `k60_dpu=1`、UI 起来后调一次 `panel_intf_rate("te sync", 3000)`，判
`A ≥ 110`、`B ≥ 110`、`(d-c)` 与 `(f-e)` 相差 ≤ 2 帧；`B < 110` 且 `A ≥ 110` 是静态 UI 自刷新，
不是失败但不算零拷贝窗口。内核 `frames` 不等于 presenter `copies`，两侧各自成立才算零拷贝。
（同文写进 `DISPLAY-27-INTEGRATION.md` §1.5。）
