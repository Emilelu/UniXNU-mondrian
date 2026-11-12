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
