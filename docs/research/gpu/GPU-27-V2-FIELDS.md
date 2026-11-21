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
| `target` | 52 | **v2 新增**：扫出映射里的字节偏移（面板双缓冲的那半）；**0 = 没有 dbuf**，不是「第一个 dbuf」 | v1 无此字段 | `zizhan …/PongScanoutWire.h:12-17` 注释；`zizhan …/PongAdrenoScanout.cpp:1274`（`dbTarget()`）、`:1368`（`dbFlip`） |

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

## 4 引用

- 布局与版本语义：`GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.1
- 四向兼容矩阵：同文件 §2.3
- 27 侧读者行号与两处硬编码：同文件 §2.6
- 翻 0→1 的五条前置：`FLIP-READINESS.md`
- 官方口径：`unixnu.com/zh/porting/gpu` 的 `#frame-path` 与 `#memory-path`
