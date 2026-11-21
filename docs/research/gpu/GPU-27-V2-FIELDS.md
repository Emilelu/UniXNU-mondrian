# v2 四个 wire 字段的期望值表

这张表回答一个问题：**v2 的字段值对不对**。判读器今天只能判「版本==2」，判不了字段——因为
`token`/`evict`/`target` 三个字段一个字节都还没进日志。表就是为此存在的：它是判据的**输入**，
不是判据本身。

表的每一次改动都必须同时改 `patches/proposed/pong-scanout-v2-layout-asserts.patch` 里对应的那一行；
两者不一致时红的是 `scripts/check-gpu27-flip-asserts.py`（见 §3）。

---

## 1 四个字段

| 字段 | 偏移 | v2 值语义 | v1 同一偏移是什么 | 判据来源 |
| --- | --- | --- | --- | --- |
| `sequence` | 0 | 内核自增的帧序号；与 `Pending.id` 相等才认这一帧 | 同左，语义不变 | `drivers/PongAdreno/PongAdrenoScanout.cpp:122`（`q.sequence != pending.id` 拒收）、`:148`（写 `pending.id`） |
| `address` | 8 | 扫出映射的虚拟地址；presenter 用它当源，必须页对齐且 `address + bytes` 不越界 | 同左，语义不变 | `drivers/PongAdreno/PongAdrenoScanout.cpp:149`（`map->getVirtualAddress()`）、`drivers/PongMetal/PongMetalScanout.h:38`（越界校验） |
| `bytes` / `stride` | 16 / 24 | 一帧的字节数与源行距；`bytes` 必须等于 `stride * height`（v1/v2 都成立） | 同左 | `PongAdrenoScanout.cpp:149`、`PongScanoutWire.h:12` |
| `width` / `height` | 32 / 36 | 面板尺寸；内核按 Mode 里登记的值校验请求 | 同左 | `PongAdrenoScanout.cpp:157`（`width != mode.width` 拒） |
| `format` | 40 | `PongScanoutBgra`（=1）；presenter 见到别的值整帧拒 | 同左 | `PongMetalScanout.h:38`（`frame.format != PongScanoutBgra`） |
| `token` | 44 | **v2 新增**，占据 v1 的 `reserved` 位置：内核给这次映射发的非零凭证，presenter 在复用同一 surface 时必须带着它回来 | `reserved`，**必须为 0** | `patches/proposed/pong-scanout-v2-layout-asserts.patch`（`token@44`）；语义源 `E:/hackios/UniXNU-zizhan/drivers/PongAdreno/PongScanoutWire.h:12-17` |
| `evict` | 48 | **v2 新增**：内核声明「这个旧 token 的映射必须先丢掉」，presenter 照做后才算交接完成；0 表示没有要先丢的 | v1 无此字段（`sizeof` 48 就到头） | 同上；`zizhan …/PongAdrenoScanout.cpp:1297-1299`（选 victim 并写 `pending.evict`）、`:1372`（`drop`） |
| `target` | 52 | **v2 新增**：**索引 + 1**——0 = 没有 dbuf，1..N = `db[i-1]` | v1 无此字段 | `zizhan …/PongAdrenoScanout.cpp:436-456`（`dbTarget()` 返回索引）、`:1368`（`db[pending.target].phys`）、`:547`（`db[0].offset` 恰为 0，所以「偏移 + 0」会把「第 0 块」与「没有」写成同值） |

**会签附注（display 第 3 轮，`reply-gpu-display-sync.md` 第 136 行起；照它的话抄，不解释）**：

- `token`：①面板模式或画布几何真变时全表作废（我们的 120 Hz 切换只改 INTF 与 DCS，`PongDsiPanel.cpp:463-517`，不重建画布）；②token 随映射创建生成，禁止 `source` 回收后按同 `offset/bytes` 命中旧 token（`Kept` 表键是三元组，zizhan `PongAdrenoScanout.cpp:1279`）。
- `evict`：①evict 先于本帧拷贝提交生效；②内核退休后 drop（zizhan `:1372`），presenter 收到 ack 后只读不写；③只有「同一 surface 新映射替换旧映射」才允许非 0，几何不同时必须为 0。
- `target`：签「不一致」，改法见本表与 §3.1。

**不采用的东西**：第五方法码 `0x7004`（display 用来指「版本由另一个方法码承载」的形状，它自己明确不推荐）。
v3 因此没有方法码改动，只有 §2.1 的 decision record 1。

`sizeof(PongScanoutFrame)`：v1 = 48，v2 = 56。`PongScanoutModeInfo`、`PongScanoutWaitInfo`（8 B）、
`PongScanoutDone`（16 B）在两版里尺寸与布局都不变，`Done.reserved` 在两版里都必须为 0。

## 2 哪些字段今天判得了、哪些判不了

| 字段 | 判读器现在能读吗 | 谁在守它 |
| --- | --- | --- |
| `version` | 能（`scanout version=`，`judge-gpu27.py:77` 的 `SCANOUT_VERSION`） | 判读器：出现且不在 `{1,2}` 即 FAIL（`:255`）；缺席记 `unmeasured` |
| `sequence` | 间接：`Done.sequence` 与 `Pending.id` 相等才被 presenter 接受，失配表现为帧不前进 | 内核 `PongAdrenoScanout.cpp:122` |
| `address` / `bytes` / `stride` / `width` / `height` / `format` | 不能（日志只打 `addr=0x…` 与 `bytes=…`，`PongAdrenoScanout.cpp:203-204`） | 内核校验 + presenter 校验，两侧都拒 |
| `token` / `evict` / `target` | 不能（一字节都没打印），且日志通道的 90 B 硬截不允许把它们塞进遥测行 | 只能由编译期断言 + 内核记账守（本文 §1 的偏移，`check-gpu27-flip-asserts.py` 比对） |

所以「v2 字段值对不对」这个问题，**今天没有飞行能回答**；能回答的是「四个偏移的数值对不对」，
那由编译器和本表守。判读器要能判字段值，前提是 v2 之后有人打印它们——那属于 display 的 dbuf 立项，
不在这张表的范围内。

## 3 与门禁的关系

- `E:/hackios/k60-gates/scripts/check-gpu27-flip-asserts.py`：把 wire 头里的四条 `static_assert`
  与 `patches/proposed/pong-scanout-v2-layout-asserts.patch` 里的四条按 sha256 比对；补丁不在任何
  series 里时退 0 并说明自己是休眠的（P-290），进 series 那天自动变判据。本表 §1 的偏移若被改动，
  必须同时改补丁，否则这个门禁红。
- 断言文本另有一条离线编译验证（宿主 `g++ -std=c++17`），见 `FLIP-READINESS.md` 第 ④ 条。

## 3.1 这张表要 display 签三行（不签只能算单方面读法）

三个新字段的语义目前只有**我们的**读法，来源是 zizhan 的注释与它的拷贝路径。语义不是尺寸：
尺寸错了编译器会红，语义错了要到「画面丢帧、错帧」才暴露，而那已经是一次白飞。所以这三行要 display
逐行签「一致 / 不一致」，签完才能进 series。

| 字段 | 我们写的语义 | display 判 | 备注 |
| --- | --- | --- | --- |
| `token` @44 | 内核给的非零凭证，标识「同一 surface 的这次复用映射」 | **一致**，附两条条件 | ①面板模式或画布几何真变时全表作废（120 Hz 切换只改 INTF 与 DCS，`PongDsiPanel.cpp:463-517`，不重建画布）；②token 随映射创建生成，禁止 `source` 回收后按同 `offset/bytes` 命中旧 token（`Kept` 表键是三元组，zizhan `PongAdrenoScanout.cpp:1279`） |
| `evict` @48 | 必须先丢掉的旧 token；0 表示没有要丢的 | **一致**，附三条时序 | ①evict 先于本帧拷贝提交生效；②内核退休后 drop（zizhan `:1372`），presenter 收到 ack 后只读不写；③只有「同一 surface 新映射替换旧映射」才允许非 0，几何不同时必须为 0 |
| `target` @52 | **索引 + 1**：0 = 无 dbuf，1..N = `db[i-1]` | **不一致 → 已按它的读法改（见下）** | 原写法「字节偏移 + 0 = 无 dbuf」自相矛盾：`db[0].offset` 在 presenter 映射里就是 0（zizhan `PongAdrenoScanout.cpp:547`），而 `dbTarget()`（`:436-456`）返回的是**索引**，消费点全按索引（`db[pending.target].phys` `:1368`、`db[target].offset` `:1276`）⇒ `target=0` 既可能是「第 0 块」也可能是「没有 dbuf」 |

签名来源：display-agent 第 3 轮（`E:/k60-work/scratch/reply-gpu-display-sync.md` 第 136 行起），2026-11-21。

**`target` 的两个替代写法，display 两个都签**：
1. **（已采用）索引 + 1**：0 = 无 dbuf，1..N = `db[i-1]`，消费点改成 `db[target-1]`；
2. （备选）保留字节偏移，但换哨兵 `0xFFFFFFFF` —— zizhan 自己就用 `~0ull` 当「不在映射里」的哨兵
   （`:288`、`:440`）。选它的代价是每个消费点都要多一个哨兵比较，而索引方案只需要一次 `-1`。

采用 1 的理由写进 `GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.1 的 decision record：**0 与「第 0 块」不再
撞车**，而这是第一次 dbuf 飞行就会踩到的坑（误判无 dbuf ⇒ 跳过翻页 ⇒ 帧停在面板旧缓冲）。

签法不用改这张表：在 `E:/k60-work/scratch/reply-gpu-display-sync.md` 的对应轮次里逐行写「token 一致 /
evict 一致 / target 一致（0 = 无 dbuf）」，或指出哪一行不一致以及正确的读法；把日期与引文抄进
`FLIP-READINESS.md` 第 1 条的 `recorded:`。

规则（写进线内规则）：**三行没签之前，这五个常量只能停在 dormant 断言里，v2 不进 series。**

## 4 引用

- 布局与版本语义：`GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.1
- 四向兼容矩阵：同文件 §2.3
- 27 侧读者行号与两处硬编码：同文件 §2.6
- 翻 0→1 的五条前置：`FLIP-READINESS.md`
- 官方口径：`unixnu.com/zh/porting/gpu` 的 `#frame-path` 与 `#memory-path`
