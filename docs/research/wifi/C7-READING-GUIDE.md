# `c7` 判读指南：从 console.log 到 §11 定稿

> 用途：把 `c7` 的 `console.log` 读成 [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §11 的结论。
> `c7` 已于 2026-11-16 12:25 飞完（`usblog-20261116-122546`），实测落在四支之外，
> 见 §4；§11 已按那一节定稿。本页保留四支判据，是为了让下一次「判据全落空」有对照，
> 以及给 `c8` 留判据（§5）。

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

四支之外的形状有**两种**，必须先分清（`c7` 命中的是第二种）：

- **四支全不成立、且往好的方向走**：`timeout` 行根本不出现、`ee` 变成 MISSION 的值、
  `Pong Wifi` 继续往 net 阶段走。这时整节换标题：「MHI 已通，进入 net 阶段」，
  §13 第 1 条口子关闭，`docs/INDEX.md` 的 BLOB 行同步改。
- **四支全不成立、且卡在原地**：`timeout` 行出现了，但六个状态量里**设备侧是活的**
  （`exec_env` 不是 0）。这不是「没反应」，是「两边互相等」——见 §4。

## 3. 两种容易读错的形状

1. **驱动侧有、MHI 侧没有**（`QCA6490 MSI entered the GIC handler` 出现，
   但 `Pong MHI: irq entered` 不出现）：这不是 A 支。GIC 侧通，说明中断线是活的，
   缺的是 MHI 的 `request_irq` 有没有挂上、或者挂在了另一个 INTID 上。
   判 A 支必须**两条都没有**。
2. **`entered` 在涨但 `MSI=0`**：这是 `MsiStatus` 读到 0 的形状（2 号打印），
   说明中断是「假唤醒」——PARF 的 level 没有被清或者聚合器被别人的中断带着进来。
   它和 B 支不是一回事：B 支看的是 MHI 事件环，这里看的是 PCIe 侧聚合器。
3. **MHI 侧有 `irq entered`、驱动侧 `MSI entered the GIC handler` 是 0**（`c7` 的实际
   形状，与第 1 条正好相反）：这不是「GIC 通、MHI 没挂上」，而是**两套 handler 的唤醒
   来源不同**——MHI 的 `irq entered` 由兼容层每毫秒无条件重放触发（§4.1），
   驱动的 MSI handler 只在 `MsiStatus` 非零时留痕。**前者出现不构成任何证据，
   后者缺席才是证据**。

## 4. `c7` 的实测：第五支（2026-11-16 12:25 已飞）

证据 `E:/k60-work/evidence/usblog-20261116-122546`：`console.log` 227,186 B / 3,367 行 /
SpringBoard 128 / panic 标记 0；`boot.json` `imageSha256 4D187A71…F45F`、
`bootExitCode 0`、`returnedToFastboot false`。§0 的三件事全部成立（身份对、不是 silent、
十阶段全过）。

关键只有两行：

    :608  Pong MHI: irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00
    :632  Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1
          mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200

按 §2 的顺序逐支核：

| 支 | 实测 | 判定 |
|---|---|---|
| A | `irq entered` 出现；但 `QCA6490 MSI entered the GIC handler` **0 次**、`MsiStatus 0` **0 次** | 形状不命中；且 `irq entered` 这一行**证明力为零**（见 §4.1） |
| B | 形状命中（`found no new events` ×3、两条 `rp` 指向同一槽） | **归因错**：环空不是地址问题，是设备在 SBL 里没东西可发 |
| C | `event type=` **0 次**，但 `exec_env=1` = `MHI_EE_SBL` | 不命中：设备侧动了 |
| D | `EE event` **0 次**、`ee` 仍 0 | 不命中：没有事件可记，不是没记账 |

### 4.1 为什么 `irq entered` 不能当证据

兼容层每毫秒把所有已注册 IRQ 无条件置 pending：`Ath12kWifi/shim/src/lx_rt.c:597`
`lx_irq_raise_all()` 对每一项 `g_irq[i].used` 置 `pending = 1`，由 `:355` 的
`lx_pump()` 驱动（`g_irq_polling` 默认 1，`:32`），调用点在
`drivers/PongWifi/ath11k/PongAth11k.c:83`。**handler 一定会被调用**，所以
「handler 被调用了」永远不能证明「硬件发了中断」。

只有驱动自己那条能说话：`QCA6490 MSI entered the GIC handler`
（`PongWifiPlatform.cpp:646`，只在 `MsiStatus` 读到非零时打）**0 次** ⇒ GIC 没在
INTID 172 上抬过任何东西。

### 4.2 结论：不是超时，是死锁

`exec_env=1` ⇒ 设备已离开 PBL、收完 512 KiB SBL、正在 SBL 里等 AMSS。
`amss entries` / `Pong MHI: vec` 两条打印 **各 0 次** ⇒ `mhi_download_amss_image()`
从未被调用，5,296,128 B 的 AMSS 只被 `memcpy` 进了 BHIE 段表，一个字节都没送到设备。

推 AMSS 的唯一入口是事件环里的 `MHI_PKT_TYPE_EE_EVENT`
（`main.c:893` → `:900-903` `DEV_ST_TRANSITION_SBL`，全目录唯一排队点 `main.c:902`
→ `pm.c:823-834` `if (fbc_download) mhi_download_amss_image()`）。
设备不发 EE 事件是因为它在等 AMSS，主机不推 AMSS 是因为它在等 EE 事件 ——
**两边都在等对方**。`-110` 只是 20 s 之后宿主放弃等待的表现。

SBL 那 512 KiB 是走 BHI 送进去的：`load type=2` = `MHI_FW_LOAD_FBC`
（`internal.h:32-37`，「BHI in PBL followed by BHIe in SBL」）——前半段成功、
后半段没开始。

### 4.3 对 §11 的影响

§11 标题从「进行中」改成实测结论（十阶段全通、SBL 已进、AMSS 未推），新增
§11.4–§11.8 五小节；§11.3 的四支判据表**保留原样**并加一列实测读数，
用来记「判据全落空」这件事本身。

## 5. `c8` 的唯一判据

`c8` = 主动推 AMSS（不等 EE 事件）。读它只看一件事：**`exec_env` 在推 AMSS 前后
是否从 1 变 2**。

| 读数 | 含义 | 下一步 |
|---|---|---|
| `exec_env` 1 → 2，且 `amss entries` 出现 | AMSS 推成功、设备进 AMSS，死锁解除 | 看 `MHI_IN_MISSION_MODE` 是否成立，转正常起网 |
| `amss entries` 出现但 `exec_env` 仍 1 | AMSS 送了、设备没接受（校验 / 段表 / BHIe 通道） | 查 BHIE 段表与 `mhi_fw_load_bhie` 返回值 |
| `amss entries` 仍 0 次 | 主动推路径没生效（插桩没进去 / 调用点没接上） | 先验镜像身份，再查插桩锚点 |

读 `c8` 时仍然按 §0 的三件事先验身份与非 silent；仍按 §4.1 的规矩，不用
`irq entered` 判硬件。若 `c8` 推完 AMSS 而 `QCA6490 MSI entered the GIC handler`
仍是 0，那才是「MSI 未到」成为独立发现的第一刻。

## 6. 定稿前的自查

1. 本文与 §11 里**每一个数字**都要能追到一份 `console.log` 的某一行；
   引用格式统一写成 `usblog-20261116-XXXXXX` 目录名 + 行号（镜像名只作附注，
   从同目录 `boot.json` 的 `image` 字段取，不凭记忆补）。
2. 字节数、行数、SpringBoard 次数一律以 `capture.json` 的 `bytes` 与整文件计数为准；
   与 Lead 的 `grep -c` 有差时按 [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §10.1 的
   脚注写法注明，不改数。
3. **打印条数以 payload kernel 里的格式串为准，不以任何清单为准**——`c7` 之前口头说
   「八条」，镜像里实有 10 处（驱动 3 + MHI 7）。数错一次就会把「某个函数没被调用」
   误读成「打印丢了」。
4. 改完只跑 `check-docs.py` 与 `render-eight-step-table.py --check` 两道；
   构建类门禁（iron-4 / iron-5 / hard-33 / P-165 / P-166）的红与本改动无关。

## 7. 一句话

四支不是四个假说，是**四个层**：A 看线有没有电，B 看环有没有动，C 看设备有没有动，
D 看软件有没有认。写文档时按层写，不按「最可能」写。
而 `c7` 证明还有第五层：**两边都在等对方**——这一层不在任何一支里，
只有把「设备侧状态量」和「主机侧调用有没有发生」摆在一起才看得见。
