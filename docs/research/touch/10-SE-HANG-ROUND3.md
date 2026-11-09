# K60 触摸 SE 挂死 —— 第 3 轮定位（2026-11-09 15:40）

> 结论先行：**agent 的时钟修复方向正确，但开启 `k60_touch_se=1` 后仍然 0 日志挂死。
> 挂死点在 `clocks_on()` 内部或更早，不在 SE 访问之后。**

## 实测记录

| 内核 | 代码状态 | `k60_touch_se` | 日志 | 结果 |
|---|---|---|---|---|
| `a020db8e` | 我的部分修复（HWCG 判定 + GPIO 顺序）| 0（关） | **216,056 B** | ✅ 正常启动到 SpringBoard |
| `50f71363` | agent 完整修复（+CORE/CORE_2X +GPLL0 +bit20）| **1（开）** | **0 B** | ❌ 挂死 |

**关键差异只有一个**：`touch_se=0` 时 `bring_up()` 不执行；`touch_se=1` 时执行 → 挂死。

## 这一轮排查的结论

### 已排除
1. **GCC 窗口大小**：`GCC_SIZE=0x70000`，`CORE_CBCR` 在 `gcc+0x33000`，`CORE_2X` 在 `gcc+0x3300c`，`VOTE` 在 `gcc+0x62008` —— 全部在 `0x100000~0x170000` 内，**地址合法**
2. **`cmd_db` 读**：`rpmh_address()` 读的是 `cmd_db`（内存，`0x80860000`），**不是 RSC 寄存器**，安全

### 高度怀疑（按风险排序）
| # | 嫌疑 | 依据 |
|---|---|---|
| **S1** | `clocks_on()` 里**首次读 `CORE_CBCR`（`0x33000`）/ `CORE_2X_CBCR`（`0x3300c`）** | 这两个 GCC 寄存器在 QUP0 core 域，**域未上电时读也可能挂死**（不只是写）|
| **S2** | `io_supply_on()` → `rpmh_write()` **写 RSC** | 我们铁律明确：`0x17a00000/0x17a20000` 首读整机死。但 0 日志说明没走到这里（前面 `goodix_probe` 就失败了？）|
| S3 | `geni_spi_init()` 访问 SE | 若 S1 的判定通过但时钟实际没开 |

**决定性判据缺失**：0 日志意味着**连 `clocks_on()` 里那行 `printf` 都没输出**。必须让 **printf 在第一次 CBCR 读之前**发生，才能区分 S1/S2/S3。

## 下一步（必须先做，再改代码）

**在 `touch_thread` 入口（`ml_io_map` 之前）加一行无条件 printf**：

```c
touch_thread(...) {
    printf("Pong touch: thread entered\n");   /* ← 新增，第一行 */
    tlmm=ml_io_map(...);
    ...
}
```

判据：
- **看到 `thread entered` 但后面 0 日志** → 挂死在 `ml_io_map` 或 `clocks_on()` 内 → S1
- **连 `thread entered` 都没有** → 挂死在 `kernel_thread_start` 之前，或线程没起来

这是一个**零风险的诊断改动**（只加一行 printf），必须做。

## 给用户的重要提示

**当前镜像（`50f71363` 但不带 `k60_touch_se`）是安全的**：系统能正常启动，实体键可用，自动复位可用。
`k60_touch_se=1` 会挂死，**不要开**，直到 S1/S2/S3 定位清楚。
