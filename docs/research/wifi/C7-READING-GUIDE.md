# `c7` 判读指南：直接观测、待验假设与分层验收

> 用途：把 `c7` 的 [console.log](<E:/k60-work/evidence/usblog-20261116-122546/console.log>) 读成
> [BLOB-RESIDENCY.md](<BLOB-RESIDENCY.md>) §11 的证据边界，而不是替未知原因定论。
> `c7` 已于 2026-11-16 12:25 飞完（`usblog-20261116-122546`）。按 Lead 2026-11-16 15:12
> 纠正：当前只能定位 **SBL/READY → 后续转换未完成**；旧四支归因与「第五支死锁」定论撤回。
> §2 保留失效判据作历史对照；`c8` 主动推 BHIE 仍是待验实验，目前暂停，先做协议审查（§5）。

## 0. 先确认这三件事，否则不要读下面的表

1. **镜像身份**：`wifi-20261116c7`，[boot.img](<E:/k60-work/artifacts/wifi-20261116c7/boot.img>)
   sha256 前缀 `4d187a71c4d3`，payload kernel 前缀 `1b91d332006d`，
   `built_at 2026-11-16T10:17:04+08:00`，series 227（`59d8037521a5b07b`），
   `kernel_args = ['pong_wifi=1', 'k60_wifi_rsc=2']`，`wifi_archive 99a610eede5f`，`fd cf4485712c29`。
   与 `c6` 的差只有 `c7d059d` 那 101 行插桩（段表 `__DATA` 53,149,696 → 53,215,232）。
2. **不是 silent**：[capture.json](<E:/k60-work/evidence/usblog-20261116-122546/capture.json>)
   的 `bytes` 必须 > 0 且 `portSeen=true`。若是 0 字节，先回
   [BLOB-RESIDENCY.md](<BLOB-RESIDENCY.md>) §10 按 silent 处理，本指南不适用。
3. **前序路径仍到 READY**：`device in READY state` 必须出现（本次 `console:628`）。
   没到 READY，先比对 `usblog-20261116-081646`（c6）。到 READY 或前序十阶段均有日志，
   也不等于硬件已进 M0、完整 BHIE 已完成或 WiFi 已通。

## 1. `c7` 到底多打了什么（实测字符串，不是推测）

从 `c7` 的 payload kernel 里直接取出的格式串，共 **10 处**新增打印
（`c7d059d` 改了 `drivers/PongWifi/PongWifiPlatform.cpp` 与 `scripts/build-k60-ath11k.py`）：

**驱动侧 3 处**（`PongWifiPlatform.cpp`）

| # | 打印 | 语义与边界 |
|---|---|---|
| 1 | `QCA6490 MSI entered the GIC handler` | 驱动侧这个 GIC handler 首次执行留痕（`PongWifiPlatform.cpp:646`，只打一次）；打印不以 `MsiStatus` 非零为条件 |
| 2 | `PongWifi\[6\]: MSI entered with MsiStatus 0 (entry %u)` | handler 进来了但 `MsiStatus` 读到 0（前 3 次，`:648-649`）；单凭 0 不能确定空唤醒原因 |
| 3 | `PongWifi: runtime state=%u … MSI=%u entered=%u empty=%u receiver=%x dma-mib=%lu` | 每 15 s 一次的计数行（`:703-708`）：`MSI`=非零 MsiStatus 次数，`entered`=驱动 GIC 入口次数，`empty`=空状态次数；不是 MHI 软件轮询次数，且未到该循环不能把缺行当成计数 0 |

**MHI 侧 7 处**（`build-k60-ath11k.py` 注入 `boot.c` / `pm.c` / `main.c`）

| # | 打印 | 语义与边界 |
|---|---|---|
| 4 | `Pong MHI: amss entries=%u last dma=%#llx len=%zu` | 完整镜像 BHIE 路径的入口与主机侧段表信息；打印本身不证明 DMA 送达或设备接受 |
| 5 | `Pong MHI: vec\[%d\] dma=%#llx size=%#llx` | 前 3 个向量（`bhi_vec`）的地址与大小；不是完整向量表或传输完成证明 |
| 6 | `Pong MHI: irq entered er_index=%u dev rp=%#llx host rp=%#llx` | MHI 事件处理 handler 首次执行时，CPU 所见共享 `rp` 的 DMA 地址值与主机虚拟 `rp`；可由软件轮询触发，不证明 GIC 投递 |
| 7 | `Pong MHI: irq found no new events` | CPU 本次将共享 `rp` 换算到主机地址后，未见与本地主机 `rp` 的差异（前 3 次）；不证明设备从未写过 |
| 8 | `Pong MHI: event type=%d` | CPU 解析到的前 32 个事件类型；缺席只表示抓取未见该处理留痕 |
| 9 | `Pong MHI: EE event execenv=%d` | EE 事件处理日志中的执行环境；必须与硬件 `exec_env`、软件 `ee` 分开记录 |
| 10 | `Pong MHI: timeout after %u ms ee=%d pm_state=%d exec_env=%d mhi_state=%d MHISTATUS=%#x MHICTRL=%#x` | 等待 MISSION 超时那一刻的六个状态量；控制请求、硬件状态与软件状态不能互相替代 |

> 计数口径：Lead 的旧指示里说「八条」，实测是 **10 处打印**——驱动侧 3 处、MHI 侧 7 处。
> 本文保留全部格式串；若将来有第二版插桩，以对应 kernel 的格式串重数。

## 2. 历史四分支表：归因已失效，不再作为决策规则

**本表只保留旧判读的形状和错误归因，不再按 A→B→C→D 排他分类，也不据此直接改驱动或定稿。**
旧表把硬件中断、软件轮询、CPU 所见环值和设备状态混成互斥因果；现行读法是 §4 的分栏记录与 §5 的分层验收。

| 历史支 | 当时的日志形状 | 原归因（已撤回） | 失效原因与现行边界 |
|---|---|---|---|
| **A** | GIC 首次入口日志与 `Pong MHI: irq entered` 都没有，且 `runtime` 行 `entered=0` | MSI 没到 GIC，PARF MSI0 → SPI140 路由没送出 | MHI handler 另有软件轮询来源；缺日志需结合打印条件与观测窗口，不能单独证明路由必错，更不能把未出现的 `runtime` 行补成 0 |
| **B** | 有 `irq entered` / `found no new events`，但无 `event type=` | 中断到了，设备没写环或环地址 / `iova_start` 不对 | handler 执行不证硬件中断；共享 `rp` 初值由主机写入，CPU 看到不变不能排除 DMA 可见性、上下文交接或设备写入问题 |
| **C** | 有 `event type=`，但无 `EE event execenv=` | 设备没进 SBL/MISSION | 事件类型、硬件 EE 与软件处理不是同一观测；无 EE 处理日志不能反推硬件 EE 未变 |
| **D** | 有 `EE event execenv=`，但 timeout 的 `ee=0` | 软件状态机没有记账 | 需核对事件值、顺序、工作项执行与取样时点；不能仅凭这两个字段认定工作线程故障 |

旧表之外也不能再补一个「第五支死锁」结论。超时行中 `exec_env` 非 0 只提供执行环境的采样，
不证明设备正在等主机；没有 timeout 或单独进入 AMSS，同样不能直接把结论升级成 WiFi 通。

## 3. 容易读错的日志组合

1. **驱动 GIC 侧有、MHI 侧没有**：只说明该驱动入口有留痕，而抓取未见 MHI 的首次入口打印。
   MHI IRQ 注册、分发对象、使能时序和打印覆盖均需核查；不能直接判成「挂在另一个 INTID」。
2. **驱动 `entered` 在涨但 `MSI=0`**：记录为 handler 执行时 `MsiStatus` 读到 0。
   PARF level、聚合器、状态读取与清除时序等仍待查；「假唤醒」不是由这两个数独立证实的原因。
3. **MHI 有 `irq entered`，驱动 GIC 入口日志缺席**（本次 c7）：先分清唤醒源。
   前者可以来自兼容层 `lx_irq_raise_all()` 的软件轮询；它对 CPU 所见事件环仍有观测价值，
   但不是 GIC 证据。后者只能写成当前抓取未见驱动 GIC handler 留痕，不能强推硬件路由或设备行为。

## 4. `c7` 实测：SBL/READY → 后续转换未完成

证据 [console.log](<E:/k60-work/evidence/usblog-20261116-122546/console.log>)：227,186 B / 3,367 行 /
SpringBoard 128 / panic 标记 0；[boot.json](<E:/k60-work/evidence/usblog-20261116-122546/boot.json>)
`imageSha256 4D187A71…F45F`、`bootExitCode 0`、`returnedToFastboot false`。
这些是镜像身份与正常 iOS 启动记录，不是 WiFi 验收证据。

下列保留原始 c7 关键输出（前缀数字是上述 console 的行号）：

```text
608  PongWifi[6]: Pong MHI: irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00
610  PongWifi[6]: Pong MHI: irq found no new events
612  PongWifi[6]: Pong MHI: irq found no new events
618  PongWifi[6]: Pong MHI: load type=2 image bytes=524288 vector bytes=5296128
620  PongWifi[6]: Pong MHI: irq found no new events
628  PongWifi[6]: Pong MHI: device in READY state
632  PongWifi[6]: Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200
```

### 4.1 直接观测：硬件状态、主机请求、软件状态分开

| 层 | c7 读数 / 日志 | 可支持的结论 | 不能推出 |
|---|---|---|---|
| 硬件执行环境 | `exec_env=1` | 取样时硬件 EE 为 `MHI_EE_SBL` | SBL 的具体等待条件、是否发过 EE/MSI 及其原因，或完整 AMSS 已下载 |
| 硬件 MHI 状态 | `mhi_state=1`、`MHISTATUS=0x101`，另有 `console:628` READY | 取样时 READY，`SYSERR=0` | 已进入 M0 / MISSION，或没有其它未采样故障 |
| 主机控制请求 | `MHICTRL=0x200` | 主机控制寄存器请求 M0 | 硬件已经接受请求并进入 M0 |
| 软件状态 | `ee=0`、`pm_state=2` | host `ee=MHI_EE_PBL`，`pm_state=MHI_PM_POR`（`BIT(1)=2`） | 数字 2 不是硬件 M0，也不等于已经进入后续软件状态 |
| 事件处理 / BHIE 入口 | `event type=`、`EE event`、`amss entries`、`vec[` 在本次抓取各 0 次 | 抓取未见 EE 处理或完整镜像 BHIE 入口留痕 | 设备绝未生成事件、共享内存始终没写过，或日志缺席就是完整调用轨迹 |

**当前定位只到 SBL/READY → 后续转换未完成。** `-110` 是 20 s 等待失败的返回，
不是「两边都在等对方」的因果证明；硬件 EE 与 host `ee` 不一致应保留为待解释现象。

### 4.2 共享 `rp` 与 IRQ：CPU 观测不等于设备 / GIC 证明

`console:608` 的 `dev rp=0xa0001a00` 是 CPU 读取共享 `er_ctxt->rp` 所见的 DMA 地址值，
`host rp=0xfffffff9bb055a00` 是主机虚拟地址；换算后落在同一槽。**共享 `er_ctxt->rp` 的初值是主机写入的。**
结合 `console:610/612/620` 的三次空环日志，只能说这些 CPU 检查未观察到相对主机游标的推进；
不能把两个地址的对应关系当成设备已读上下文、DMA 可见性正常或设备从未写过的证明。

兼容层 `Ath12kWifi/shim/src/lx_rt.c:597` 的 `lx_irq_raise_all()` 对每一项 `g_irq[i].used`
置 `pending = 1`，由 `:355` 的 `lx_pump()` 驱动（`g_irq_polling` 默认 1，`:32`），
调用点在 `drivers/PongWifi/ath11k/PongAth11k.c:83`。这是软件轮询重放，不是硬件 IRQ 投递记录。

本次 `QCA6490 MSI entered the GIC handler` 与 `MSI entered with MsiStatus 0` 各 0 次。
前一打印在 `PongWifiPlatform.cpp:646`，位于 `if (pending)` 之外，**不是只有非零 `MsiStatus` 才打印**。
零次表明本抓取未见该入口留痕，但尚不能判「PARF → GIC 路由必错」，也不能反推
「设备在 SBL 等 AMSS，所以无需发中断」。设备事件生成、上下文 / DMA 可见性、READY→M0 时序、
主机事件处理及中断使能 / 路由 / 观测覆盖仍未被这一组合排除，不能把它们缩成二选一。

**另查日志可达性**：`PongWifiPlatform.cpp:690` 的 `nw_wifi_start()` 失败会 `goto done`；
`:692` 的 `QCA6490 MSI delivered by GIC` 只在启动成功后的 runtime 循环检查
`msiArrivals`。c7 `console:646-647` 已记录 `ath11k start failed=-110` 与 stopped，
失败路径不经过 delivered 检查。因此缺失这条打印既不证明 MSI 未到，也不证明最终
`msiArrivals=0`；不能从未执行的日志点补出计数。它与 `:646` 的首次 GIC 入口日志、
由软件重放的 MHI handler 是三个不同的观测点。

### 4.3 BHI 已送同文件前缀；完整 BHIE 阶段未观察到发起

`console:616-618` 记录文件 5,296,128 B，`load type=2` = `MHI_FW_LOAD_FBC`，
初次 BHI 的 `image bytes=524288`；打印中的 `vector bytes=5296128` 是待分段的完整固件字节数，
不是 vector table 自身的字节数。FBC 路径含 BHI in PBL followed by BHIE in SBL；
**BHI 已发送同一文件的 512 KiB 前缀**，硬件 EE 后续采样到 SBL。这个前缀不是另一份独立文件。

`amss entries` / `vec[` 各 0 次的准确写法是：**本次抓取未观察到完整镜像 BHIE 阶段发起**。
不能再写「AMSS 一个字节都没送到设备」，也不能把主机内存中的段表准备等同于 BHIE 成功。

旧源码调用链记录：`main.c:893` 的 `MHI_PKT_TYPE_EE_EVENT` 处理 → `main.c:900-903`
排队 `DEV_ST_TRANSITION_SBL` → `pm.c:823-834` 的 `if (fbc_download) mhi_download_amss_image()`。
它提示应审查 EE 事件处理到 BHIE 入口的交接，不独立证明设备是否生成过事件、事件为何未被处理，或已形成协议死锁。

**正确 BHIE 算术**（由 `console:618` 的字节数与 `console:596` 的 `seg=524288` 推算，不是实测 `entries`）：

- `ceil(5296128 / 524288) = 11` 个数据 buffer。
- `5296128 = 10 × 524288 + 53248`：10 个满块，最后 1 块 53,248 B。
- vector table 含 **11 个数据向量项**；分配数组另有最后一个 vector-table buffer，故 **`entries=12`**。
- 旧清单把总 `entries` 写成 11 是算术 / 计数口径错误，不能沿用。

### 4.4 地址空间：`iova_start=0` 不是物理 0 矛盾

`iova_start=0 .. dma_mask` 描述可用 IOVA 的包络，不是上下文必须放在 0 的声明。
`CCABAP` / `ECABAP` / `CRCBAP` 是独立的实际上下文基址指针；`0xa0000000` 在这个包络内，
不能把范围起点与实际指针不同叫作「物理 0 矛盾」。
实际指针值、映射、设备读取与共享内存可见性仍须独立取证；「在范围内」也不证明这些都正确。

### 4.5 待验假设与未排除项

- **待验假设**：EE 事件 → SBL 工作项 → 完整 BHIE 入口的交接可能未完成；主动发起 BHIE 是否改变
  后续转换尚未验证。这是实验方向，不是已证明的修复或唯一原因。
- **未排除项**：READY→M0 协议顺序 / 请求接受情况、设备事件生成、共享上下文与 DMA 可见性、
  host 事件环与状态工作项、中断使能 / 投递 / 路由及打印覆盖。c7 现有证据不能在其中唯一归因。
- **对 §11 的约束**：结论按本节的直接观测、待验假设、未排除项分栏写；历史 A–D 与「第五支」
  只能以失效归因保留，不能继续指导改代码或据此宣告 AMSS / MHI / WiFi 成功。

## 5. `c8` 暂停：先审协议，再分层验收

主动推完整 BHIE（不等旧 EE 触发路径）只是待验实验。**`c8` 当前 HOLD**，不构建、不重建、不 boot。

离线依据为 wifi-agent `82086f1069717f269c47ef194b02f660d9f0d3ef` 的
[MHI-STATE-MACHINE.md §4、§6](https://github.com/Emilelu/UniXNU-mondrian/blob/82086f1069717f269c47ef194b02f660d9f0d3ef/docs/research/wifi/MHI-STATE-MACHINE.md#L118)：
生成目录 `/opt/k60/trees/k60build/wifi/ath11k-c8/` 中，`mhi/boot.c:622-644` 的 direct
AMSS 分支忽略返回值，且不取消 queued SBL；`mhi/pm.c:809-839` 仍可在 direct 返回后
由已排队 SBL 顺序再次调用 AMSS。调度器阻止同一 worker 的递归，不等于下载去重。
这是**有条件可达的源码路径**，不能写成 c7/c8 已发生重复下载；第二次调用也不等于
第二次设备传输完成。恢复前须审重复调用、错误传播、READY→M0 协议与完成状态处理。

同一审计 §6（:248-290）指出 build/flash 都漏选 parked WiFi；留存 c8 build gate 的
`logs/eight-step.log:2-4` 仅六项/36 checks，未检查 WiFi。当前源/对象 hash 一致性不补
mutable intermediates 与临时 native-builder 精确 hash 的历史归属缺口。这里仅引用，
不把绿色通用门禁当飞行许可，也不在本线修 gate。文档的有限合并不再要求先飞 c8。

若以后获准恢复实验，仍先核对 §0，并逐层保留独立证据，不能再设 `exec_env` 一个「唯一判据」：

| 验收层 | 需独立记录的证据 | 不能越层推出 |
|---|---|---|
| BHIE 发起与返回 | 镜像身份、入口 / 段表与长度、`mhi_fw_load_bhie` 返回值及对应状态 / 超时 | 入口打印不等于送达；返回成功不等于 WiFi 通 |
| 硬件 EE 与 MHI 状态 | BHIE 前后硬件 `exec_env`、`MHISTATUS` / `mhi_state`，并与 `MHICTRL` 请求分开；确认实际 M0 | `exec_env` 1→2 至多证明取样时进入 `MHI_EE_AMSS`，不证明 MHI 已在 M0 或网络可用 |
| host `ee` 与事件环 | 共享与本地游标、实际解析的事件 / EE、状态工作项与软件 `ee` 的时序 | CPU 所见环值不变不能证明设备没写；host `ee` 更新不等于 QMI / ath11k 成功 |
| QMI 与 ath11k 注册 | QMI 握手 / 服务就绪及 ath11k 初始化、注册的实际结果 | 固件环境进入 AMSS 不等于注册完成；注册也不等于 netdev 数据面可用 |
| netdev、扫描、关联、数据 | netdev 发布，真实扫描 BSS，目标关联结果，实际收发数据分别取证 | netdev 存在、扫描或关联单项成功，不能替代最终数据收发证据 |

`amss entries` 缺席时先核身份与日志 / 调用覆盖；出现而硬件 EE 仍为 SBL 时，记录具体返回与硬件状态，
不直接写成「设备拒绝」。即使 EE 到 AMSS 后 GIC 日志仍 0，也需结合各层证据审查，不能自动定为路由故障。

源码坐标（pinned Linux `/home/emilelu/wifi-inputs/linux`）：`drivers/bus/mhi/host/internal.h:128,142`
定义 POR；`init.c:391-393` 初始化共享 rp，`:480-535` 分开配置上下文指针与地址包络；
`boot.c:372-405,430-434` 给出 buffer 数及 vector 有效长度；`pm.c:1277-1298` 是等待 MISSION 的返回路径。
这些是源码与算术依据，不冒充 console 的设备行为记录。

## 6. 定稿前的自查

1. 日志数字追到 `usblog-20261116-122546` 与具体行；镜像名从同目录
   [boot.json](<E:/k60-work/evidence/usblog-20261116-122546/boot.json>) 的 `image` 取。
   **源码映射与算术预期另标来源**，不得把 `entries=12` 等推算冒充 c7 实测。
2. 字节数以 [capture.json](<E:/k60-work/evidence/usblog-20261116-122546/capture.json>) 的 `bytes` 为准；
   行数、SpringBoard 与 panic 标记按整份日志计数。与其它计数口径有差时按
   [BLOB-RESIDENCY.md](<BLOB-RESIDENCY.md>) §10.1 注明，不无声改数。
3. **保留 10 处格式串与原始 c7 输出**；缺打印只记为未观察到对应留痕，不补成设备行为或完整调用轨迹。
4. 逐项检查本页六个边界：SBL/READY 与 M0 请求分开；共享 `rp` / IRQ 不过度归因；BHI 前缀与完整 BHIE
   分开且 c8 暂停；11 数据 buffer / 12 总 entries；IOVA 包络与独立指针分开；五层验收各有证据。
5. 文档纠正运行只读门禁 `python3 scripts/check-docs.py` 与 `python3 scripts/render-eight-step-table.py --check`，
   并审阅完整差异；门禁通过不替代上述语义自审，也不是允许跳过 §5 协议审查与八步流程的构建 / 上机凭据。

## 7. 一句话

**c7 观察到硬件 SBL/READY、主机请求 M0、软件仍 PBL/POR，未见 EE 处理或完整 BHIE 入口；**
**后续转换未完成，原因未定。** 按层写观测、按证据留不确定项，不把一个因果定论换成另一个。
