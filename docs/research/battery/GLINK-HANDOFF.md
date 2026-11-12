# K60 ADSP GLINK 交接契约（`k60-adsp-glink-handoff`）

这份文件记录的是**生产者必须提供什么**，全部从消费方源码读出，不是推断。

## 消费者

| 位置 | 作用 |
| --- | --- |
| `drivers/PongPower/K60BatteryConfig.h:17` | `#define K60_ADSP_HANDOFF_PROPERTY "k60-adsp-glink-handoff"` |
| `drivers/PongPower/K60Battery.cpp:427` | 读属性 → `K60AdspGlinkHandoff handoff;` |
| `drivers/PongPower/K60Battery.cpp:49,347` | `begin(provider, config, handoff)` |
| `drivers/PongPower/K60BatteryConfig.c:54` | `k60_adsp_handoff_parse()` 校验 |

仓库里**没有生产者**：`grep -rn 'k60-adsp-glink-handoff' drivers/ patches/` 只有上面这几个消费点。
音频走同一个缺失的生产者，所以这份契约同时决定电池和音频。

## 结构（`K60BatteryConfig.h:50-62`）

```c
typedef struct {
    uint32_t flags;
    uint64_t epoch;
    uint64_t smem_base, smem_bytes, adsp_base, adsp_bytes;
    uint32_t desc_offset, desc_bytes, tx_offset, tx_bytes, rx_offset, rx_bytes;
    uint32_t host_tx_head, host_rx_tail, remote_restart_flag;
} K60AdspGlinkHandoff;
```

## 字节布局（`K60BatteryConfig.c:54-75`，小端）

| 偏移 | 字段 | 校验 |
| --- | --- | --- |
| +0 | magic | 必须等于 `K60_ADSP_HANDOFF_MAGIC` |
| +4 | version | 必须等于 `K60_ADSP_HANDOFF_VERSION` |
| +8 | bytes | 必须等于属性长度本身（`K60_ADSP_HANDOFF_BYTES`，即 104） |
| +12 | flags | 必须 == `K60AdspHandoffRequired` |
| +16 | epoch | 必须非 0 |
| +24/+32 | smem_base/smem_bytes | 必须等于 config 里的值 |
| +40/+48 | adsp_base/adsp_bytes | 必须等于 config 里的值 |
| +56/+60 | desc_offset/desc_bytes | `desc_bytes == 32`，offset 8 字节对齐 |
| +64/+68 | tx_offset/tx_bytes | 256 ≤ bytes ≤ 65536，8 字节对齐 |
| +72/+76 | rx_offset/rx_bytes | 同上 |
| +80 | host_tx_head | **必须为 0** |
| +84 | host_rx_tail | **必须为 0** |
| +88 | remote_pid | 必须等于 config 的 `remote_pid`（ADSP = 2） |
| +92 | smp2p_item | 必须等于 config 的 `smp2p_item` |
| +96 | remote_restart_flag | 必须 ≤ 1 |
| +100 | 保留 | 必须为 0 |

`fits(offset, bytes, usable)` 里 `usable = smem_bytes - 4096`。

## 三条硬性语义要求

1. **必须是新会话**：`host_tx_head == 0 && host_rx_tail == 0`，否则返回
   `K60ConfigWrongEpoch`。源码注释写得很直白——继续用 Android 的通道 ID、或者猜旧 FIFO 里
   残留了什么，都不算接管。
2. **epoch 非 0**，且必须与本次 lease 对应；生产者不能复用上一个会话的值。
3. **资源必须与 ADT 一致**：`smem_base/smem_bytes`、`adsp_base/adsp_bytes`、`remote_pid`、
   `smp2p_item` 全部来自 `K60BatteryConfig`，由
   `scripts/build-k60-physical-battery.py` 从 ADT 生成（`/tmp/mbat2` 里的
   `K60BatteryConfig.generated.c`）。ADT 侧已经就绪（commit `bc7c1c8`，零警告编译）。

## 生产者要做的四件事

1. 从 ADT 取 `smem_region@80900000`、`adsp_region@9fd00000`、`glink-edge` 的 IPCC 邮箱
   （host0/ADSP2/IPCC3/0）与 `smp2p`（remote-pid 2 / local-pid 0）。
2. 在 SMEM 里切出 desc(32 B)、tx、rx 三个环，偏移 8 字节对齐，大小满足上表区间。
3. 用本次 lease 的 epoch 组装 104 字节 blob，`host_tx_head`、`host_rx_tail` 置 0，
   `remote_restart_flag` ≤ 1。
4. 把 blob 作为属性 `k60-adsp-glink-handoff` 发布到电池驱动能读到的地方
   （`/chosen` 或 provider 上），并在已有 lease 时拒绝二次发布。

## 为什么不能绕过

`k60_adsp_handoff_parse` 的每一次拒绝都有明确返回码
（`K60ConfigBadEncoding` / `K60ConfigNoOwnership` / `K60ConfigBadResource` /
`K60ConfigWrongEpoch`），没有"缺属性就用默认值"的分支。所以电池驱动在没有生产者时
必然停在这里，而不是带着半真半假的状态上线——这是设计意图，不是缺陷。

## 生产者缺的两块，实测（2026-11-13，round 219）

写完契约后立刻去查"能不能照它实现"，答案是还缺两块，而且都能用路径说清：

**一、没有 SMEM 分配器。** `drivers/` 下 `k60_smem_*` 只有两族函数：

- `k60_smem_partition(...)` —— 定位分区
- `k60_smem_find(..., item_id, &offset, &size)` —— 查已有条目

`K60PmicGlink.cpp:60-69` 正是用它们把 lease 里的 `desc/tx/rx` 偏移与 SMEM 里**真实存在**
的条目逐项比对，比不上就 `error = -23` 退出。也就是说：lease 不能凭空写三个偏移，
SMEM 里必须先有三个真条目。而仓库里没有任何分配（alloc/lookup-write）接口，
分配器的缺失是硬缺口。

**二、没有 ADSP PAS1 装载器。** `grep -rln 'PAS1|pas1|auth_and_reset|adsp_pas' drivers/`
只命中 `drivers/PongAdreno/*`（GPU 的 ZAP/CP 路径）和 `drivers/PongPower/K60Battery.cpp`
里的注释。也就是说 PAS1 的 auth+reset 流程只有 GPU 侧有一份可参考实现，
ADSP 侧从未写过——这正是 `K60AdspGlinkHandoff` 一直"只有消费者没有生产者"的根因。

结论：这份契约仍然是必要的（它把"要什么"钉死了），但它不能替代那两块实现。
下一步的正当顺序是先在 ADSP 侧复刻 `PongAdrenoZap` 的 PAS 流程，再补 SMEM 分配，
最后才轮到发布属性——顺序颠倒就会退化成"属性对了但通道是假的"。

## 迁移评估：GPU 的 PAS 路径能借什么（round 220）

`PongAdrenoZap.c`（133 行）本身**不是** PAS 加载器，它只是两件事：
1. `PongAdrenoPlanZap()` —— 解析厂商 ZAP 的 ELF32 元数据，算出非法重叠；
2. `PongAdrenoStartZap()` —— 通过 `PongZapOps` 回调把校验后的地址交给调用者。

真正的 SCM 调用不在它里面，而在调用者：

- `drivers/PongAdreno/PongAdrenoCp.cpp:178-187` —— 注释写明
  `Same SMCCC64 SIP convention and QCOM A6 resume as Nothing's qcom_scm-smc.c`，
  实现就是内联 `asm volatile("smc #0" : "+r"(x0) … "+r"(x7) …)`。
- `drivers/PongAdreno/PongAdrenoPlatform.cpp:62` 同一种写法。
- `PongZapOps` 契约（`PongAdrenoZap.h:43`）里带 `ops->scm` 与
  `ops->smccc_width`（32 或 64），`PongAdrenoStartZap` 在
  `PongAdrenoZap.c:76` 处对 `!ops->publish || !ops->scm` 直接拒绝。

结论：**内核里没有独立的 SCM 驱动**（`grep -rl 'scm_call|qcom_scm|SCM_SIP' iokit/ bsd/ osfmk/`
零命中），SCM 是可复制的内联 `smc #0` 模式。ADSP 侧可以照抄这段约定，
不需要新增框架。

### 迁移到 ADSP 时必须重算的四项

| 项 | GPU 的值 | ADSP 的值 |
| --- | --- | --- |
| PAS id | 13（`PAS13 ZAP auth`） | 1（`PAS1`） |
| 固件目标 | GPU FW 区 + ZAP 元数据 | `adsp_region@9fd00000`，0x3100000 |
| 复位/GDSC | GX OOB/START 序列 | ADSP 需要单独的 GDSC + 复位释放顺序 |
| 通道 | CP 邮箱 fence | GLINK：IPCChost0/ADSP2、smp2p(2/0)、SMEM 三环 |

前三项都在 `remoteproc-adsp@3000000` 的 ADT 节点与我们已有的 vendor DTS 里能查到
（见 `docs/research/audio/VENDOR-ADSP-NODE.md`）。

### 顺序仍然是硬的

1. 内联 SMC（照抄 `PongAdrenoCp.cpp:187`）→ PAS1 auth + reset；
2. 把 ADSP 固件装进 `adsp_region` 并释放；
3. SMEM 分配器（当前缺失）→ 切 desc/tx/rx 三环；
4. 组 104 字节 blob 并发布 `k60-adsp-glink-handoff`；
5. 电池/音频各自的协议层才可能真正开始。

跳过第 3 步直接发布属性会通过 `k60_adsp_handoff_parse`，但
`K60PmicGlink.cpp:60-69` 的 SMEM 条目比对会以 `error = -23` 拒绝——
所以"假通道"在这个设计里是被挡住的，代价只是多一轮启动。

## 两个缺口的参考实现已找到（round 221）

之前记的“缺 SMEM 分配器、缺 ADSP PAS1 加载器”不是说没有参考，是说**本仓库里**没有。
参考实现在参考仓，且都是同平台（SM8475）的完整代码：

### SMEM 分配：`E:\k60-work\references\pong-power\QcomSmem.c:94`

```c
int qcom_smem_alloc(const QcomSmem *smem, const QcomSmemPartition *p, uint16_t item, uint32_t size)
{
    uint32_t at; int found, rc = walk_uncached(smem, p, item, &at, &found);
    if (rc) return rc;
    if (found) return QcomSmemExists;
    if (qcom_smem_find(smem, p, item, &offset, &bytes) == QcomSmemOk) return QcomSmemExists;
    const uint32_t aligned = align_up(size, 8), need = ENTRY + aligned;
    if (!size || aligned < size || (uint64_t)at + need > rd(smem, p->offset + 16)) return QcomSmemNoSpace;
    qcom_smem_write32(smem, p->offset + at, CANARY | (uint32_t)item << 16);
    qcom_smem_write32(smem, p->offset + at + 4, aligned);
    qcom_smem_write32(smem, p->offset + at + 8, aligned - size);
    qcom_smem_write32(smem, p->offset + at + 12, 0);
    for (uint32_t i = 0; i < aligned; i += 4) qcom_smem_write32(smem, p->offset + at + ENTRY + i, 0);
    qcom_smem_write32(smem, p->offset + 12, at + need);   /* entry complete, then bump `up` */
    return QcomSmemOk;
}
```

关键点，全部与本仓 `K60Smem.c` 的结构对得上（`PART_HEADER 32`、`ENTRY 16`、`CANARY 0xa5a5`、
`up = rd(offset+12)`、`down = rd(offset+16)`）：

1. 先 `walk_uncached` 串行走一遍目录，再 `find` 一次——两处都要，防并发与重复；
2. 条目头四字：`CANARY | item<<16`、`aligned`、`aligned-size`(padding)、`0`；
3. 数据区按 4 字节清零，长度 `aligned`；
4. **最后**才写 `up = at + need`，注释写明 “The entry is complete before the free mark moves over it”；
5. 空间判据是 `at + ENTRY + aligned <= down`。

也就是说：`up` 向上长、`down` 是硬上界，与 `partition_bounds()` 的
`PART_HEADER <= up <= down <= size` 完全一致。这不是猜的算法，可以直接复刻。

### ADSP PAS1 + GLINK：`E:\k60-work\references\pong-power\PongAdsp.cpp`（714 行）

文件头自述 `Pong SM8475 ADSP PAS1 boot and Qualcomm SMEM/SMP2P/GLINK transport`，
且明确 `No SM8550 PAS36 image is loaded`——正是我们要的那块。关键锚点：

| 行 | 内容 |
| --- | --- |
| `:244` | `asm volatile("smc #0" : "+r"(x0) … "+r"(x7) …)`，与 GPU 侧同一约定 |
| `:301` | `authenticateHeader(Image &image, uint32_t pas, uint64_t base)` —— PAS 元数据认证 |
| `:312-315` | 元数据必须有物理连续区 `phys & 4095 == 0`、`span >= bytes`、`phys+bytes <= 1<<36` |
| `:142-143` | `kickGlink()` → `ring(QCOM_IPCC_CLIENT_LPASS, QCOM_IPCC_SIGNAL_GLINK_QMP)`；`kickSmp2p()` → `…_SMP2P` |
| `:37` | 协议标识按 Pong live DT 与 NothingOSS `cape-adsp-pas` 保留 |

这说明此前判断的“要新写驱动”过重了：ADSP 路由是**移植已存在的实现**，
而不是从零设计。真正的工作量在于把它接到本仓的 `K60Smem.c` / `K60PmicGlink.cpp` 契约上，
并按 P-165 的规则以补丁形式落地。
