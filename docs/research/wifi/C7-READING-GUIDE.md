# `c7` 判读指南：从 console.log 到 §11 定稿

> 用途：Lead 飞完 `c7` 把 `console.log` 交过来之后，按这一页直接把
> [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §11 改写成实测版，不再来回一轮。
> 本文只写「哪一行读数指向哪一层、该改哪一段」，不写任何 MHI 归因——
> 归因必须等 `c7` 的字节。

## 0. 先确认这三件事，否则不要读下面的表

1. **镜像身份**：`wifi-20261116c7`，`boot.img` sha256 前缀 `4d187a71c4d3`，
   payload kernel 前缀 `1b91d332006d`，`built_at 2026-11-16T10:17:04+08:00`，
   series 227（`59d8037521a5b07b`），`kernel_args = ['pong_wifi=1', 'k60_wifi_rsc=2']`，
   `wifi_archive 99a610eede5f`，`fd cf4485712c29`。
   与 `c6` 的差只有 `c7d059d` 那 101 行插桩（段表 `__DATA` 53,149,696 → 53,215,232）。
2. **不是 silent**：`capture.json` 的 `bytes` 必须 > 0 且 `portSeen=true`。
   若是 0 字节，先回 §10 按 silent 处理，本指南不适用。
3. **十阶段仍然全过**：`device in READY state`（`:620` 附近）必须出现。
   没到 READY 说明 c7 连 c6 的位置都没到，先比对 `usblog-20261116-081646`（c6）。

## 1. `c7` 到底多打了什么（实测字符串，不是推测）

从 `c7` 的 payload kernel 里直接取出的格式串，共 **10 处**新增打印
（`c7d059d` 改了 `drivers/PongWifi/PongWifiPlatform.cpp` 与 `scripts/build-k60-ath11k.py`）：

**驱动侧 3 处**（`PongWifiPlatform.cpp`）

| # | 打印 | 语义 |
|---|---|---|
| 1 | `QCA6490 MSI entered the GIC handler` | GIC 里**我们这个 handler** 第一次被调用（`PongWifiPlatform.cpp:646`，只打一次） |
| 2 | `PongWifi\[6\]: MSI entered with MsiStatus 0 (entry %u)` | handler 进来了但 `MsiStatus` 读到 0（前 3 次，`:648-649`） |
| 3 | `PongWifi: runtime state=%u … MSI=%u entered=%u empty=%u receiver=%x dma-mib=%lu` | 每 15 s 一次的计数行（`:703-708`）：`MSI`=非零 MsiStatus 次数，`entered`=GIC 入口次数，`empty`=空状态次数 |

**MHI 侧 7 处**（`build-k60-ath11k.py` 注入 `boot.c` / `pm.c` / `main.c`）

| # | 打印 | 语义 |
|---|---|---|
| 4 | `Pong MHI: amss entries=%u last dma=%#llx len=%zu` | 交给设备的段表条数、最后一条（向量表）的 DMA 地址与长度 |
| 5 | `Pong MHI: vec\[%d\] dma=%#llx size=%#llx` | 前 3 个向量（`bhi_vec`）的地址与大小 |
| 6 | `Pong MHI: irq entered er_index=%u dev rp=%#llx host rp=%#llx` | MHI 事件中断第一次进来时的环索引与两侧 `rp` |
| 7 | `Pong MHI: irq found no new events` | 中断进来了但 `ev_ring->rp == dev_rp`（前 3 次） |
| 8 | `Pong MHI: event type=%d` | 事件环里前 32 个事件的类型 |
| 9 | `Pong MHI: EE event execenv=%d` | EE 事件携带的执行环境 |
| 10 | `Pong MHI: timeout after %u ms ee=%d pm_state=%d exec_env=%d mhi_state=%d MHISTATUS=%#x MHICTRL=%#x` | READY→MISSION 超时那一刻的六个状态量 |

> 计数口径：Lead 的指示里说「八条」，实测是 **10 处打印**——驱动侧 3 处、MHI 侧 7 处。
> 本文按实测写；若将来 `c7` 有第二版插桩，以 kernel 里的格式串为准重数一遍。

## 2. 四支判据：看到什么 → 指向哪一层 → 改哪一段

四支**互斥**，按顺序判：先看 1/2/3（GIC 有没有进来），再看 6/7（环有没有动），
再看 8（有没有 event），最后看 9/10（EE 有没有到、软件有没有认账）。

| 支 | 判据（按这个顺序找行） | 指向 | 改哪一段 |
|---|---|---|---|
| **A** | ① `QCA6490 MSI entered the GIC handler` 与 ② `Pong MHI: irq entered` **都没有**，且 ③ `runtime` 行 `entered=0` | MSI 没到 GIC：PARF MSI0 → SPI140 这条路没送出 | §11.2 加「实测：legacy 路由在 MISSION 阶段没有送出中断」；§11.3 A 支从「判据」改成「实测结论」；§11.4 补一句「silent 结论不受影响」。下一步写 ITS vs legacy 的对照实验 |
| **B** | `Pong MHI: irq entered` 出现（`entered` 在涨），但 `irq found no new events` 出现，且 **没有** `event type=` 行 | 中断到了，事件环 `rp` 不动：设备没写环，或环地址/ `iova_start` 不对 | §11.3 B 支写实测；§11.2 补 `dev rp` / `host rp` 的两个实测值；新增一句「`iova_start=0` 从疑点升级为待验项」，并列出 §4 的地址空间对照 |
| **C** | 有 `event type=` 行，但**没有** `EE event execenv=` | 设备侧没进 SBL/MISSION：事件发了但类型里没有 EE | §11.3 C 支写实测（把 event type 的实际取值列出来）；§11 新增一小段「段表交接是否可信」，引用 4/5 两条打印的实际值（`entries`、`last dma`、`vec[0..2]`） |
| **D** | 有 `EE event execenv=%d`，但 `timeout` 行的 `ee=0` | 事件到了，软件状态机没记账（`mhi_pm_st_worker`） | §11.3 D 支写实测；§11 新增「execenv 实测值与 `ee` 字段不一致」一段，引用 10 号打印的全部六个字段 |

**第五种（四支全不成立）**：`timeout` 行根本不出现、`ee` 变成 MISSION 的值、
`Pong Wifi` 继续往 net 阶段走。那就不是 §11 的小改，而是整节换标题：
§11 从「进行中」改成「MHI 已通，进入 net 阶段」，§13 的第 1 条口子关闭，
`docs/INDEX.md` 里 BLOB 那一行的措辞同步改。

## 3. 两种容易读错的形状

1. **驱动侧有、MHI 侧没有**（`QCA6490 MSI entered the GIC handler` 出现，
   但 `Pong MHI: irq entered` 不出现）：这不是 A 支。GIC 侧通，说明中断线是活的，
   缺的是 MHI 的 `request_irq` 有没有挂上、或者挂在了另一个 INTID 上。
   判 A 支必须**两条都没有**。
2. **`entered` 在涨但 `MSI=0`**：这是 `MsiStatus` 读到 0 的形状（2 号打印），
   说明中断是「假唤醒」——PARF 的 level 没有被清或者聚合器被别人的中断带着进来。
   它和 B 支不是一回事：B 支看的是 MHI 事件环，这里看的是 PCIe 侧聚合器。

## 4. 定稿前的自查（Lead 的三条合一）

1. 本文与 §11 里**每一个数字**都要能追到一份 `console.log` 的某一行；
   引用格式统一写成 `usblog-20261116-XXXXXX` 目录名 + 行号（镜像名只作附注，
   从同目录 `boot.json` 的 `image` 字段取，不凭记忆补）。
2. 字节数、行数、SpringBoard 次数一律以 `capture.json` 的 `bytes` 与整文件计数为准；
   与 Lead 的 `grep -c` 有差时按 §10.1 的脚注写法注明，不改数。
3. 改完只跑 `check-docs.py` 与 `render-eight-step-table.py --check` 两道；
   构建类门禁（iron-4 / iron-5 / hard-33 / P-165 / P-166）的红与本改动无关。

## 5. 一句话

四支不是四个假说，是**四个层**：A 看线有没有电，B 看环有没有动，C 看设备有没有动，
D 看软件有没有认。写文档时按层写，不按「最可能」写。
