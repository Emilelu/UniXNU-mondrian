# K60 触摸时钟修复 —— 完整可行性确认方案

> 2026-11-09 15:00。三方交叉验证（Linux 源码 + 官方 sheng 实现 + 我们真机日志）。
> **本文确认方案完整可行后才动手改代码**（遵循用户指示）。

## 0. 结论先行

**根因是判定式错误，不是时钟真的没开。改 20 行代码即可让触摸走过 SE 门。**

## 1. 证据链（三方独立来源）

### 证据 1：我们自己的真机日志（最强）
`docs/research/touch/06-deep-dive.md:31`，日志 `usblog-20261108-213652`：
```
goodix: clocks stay off: 0 0x80000002 0x4220
```
| CBCR | 值 | bit31 (CLK_OFF) | bit1 (HWCG) | 真实状态 |
|---|---|---|---|---|
| `M_AHB` | `0x00000000` | 0 | 0 | **已开** |
| `S_AHB` | **`0x80000002`** | **1** | **1** | **HWCG 空闲，访问时唤醒（正常）** |
| `SE4` | `0x00004220` | 0 | 0 | **已开** |

我们的判定：`(M | S | SE4) & CLOCK_OFF` → 因为 S 的 bit31=1 → **永真** → 永远 `return false`。

### 证据 2：Linux clk-branch.c（本地副本 `impl/bt/research/02-official-docs/assets/clk-branch.c`）
```
:16-26  clk_branch_in_hwcg_mode()  读 hwcg_reg 的 hwcg_bit
:61-72  clk_branch_wait()
        /*
         * Skip checking halt bit if we're explicitly ignoring the bit or the
         * clock is in hardware gated mode
         */
```
**HWCG 模式下 Linux 整体跳过 halt 检查** —— 官方立场：HWCG 分支的 CLK_OFF 不算"没开"。

### 证据 3：官方 sheng `TouchProbe.cpp:404-406`（SM8550 同 SoC 家族，已验证可用）
```cpp
// Branches with hardware clock gating (bit 1) show CLK_OFF while idle and wake on access,
// so only a branch without that bit must have CLK_OFF clear.
auto running = [](uint32_t cbcr) { return !(cbcr & TB_CBCR_CLK_OFF) || (cbcr & 2u); };
:409-412
ok = running(M_AHB) && running(S_AHB) &&
     !(CORE & CLK_OFF) && !(CORE_2X & CLK_OFF) && !(S4 & CLK_OFF);
:421
if (!ok) { fail(2, -110); return false; }   // never touch the engine without running clocks
```
**关键**：sheng 对 M_AHB/S_AHB 用宽松判定（含 HWCG），对 CORE/CORE_2X/S4 用硬判定。

## 2. 修复方案（20 行，改 3 处）

### 改动 1：修正判定式（核心）
```c
/* 现在（错） */
if (!((rd(M_AHB_CBCR) | rd(S_AHB_CBCR) | rd(SE4_CBCR)) & CLOCK_OFF)) return true;

/* 改为（对） */
static inline bool cbcr_running(uint32_t cbcr) {
    /* HWCG (bit1) branches show CLK_OFF while idle and wake on access
     * (Linux clk-branch.c:61-72, sheng TouchProbe.cpp:404-406). */
    return !(cbcr & CLOCK_OFF) || (cbcr & 2u);
}
for (int i = 0; i < 1000; i++) {
    uint32_t m = rd(GCC_QUP0_M_AHB_CBCR);
    uint32_t s = rd(GCC_QUP0_S_AHB_CBCR);
    uint32_t se4 = rd(GCC_QUP0_SE4_CBCR);
    if (cbcr_running(m) && cbcr_running(s) && !(se4 & CLOCK_OFF)) return true;
    sleep_us(10);
}
printf("goodix: clocks stay off: m=%#x s=%#x se4=%#x\n", m, s, se4);
```

### 改动 2：**删掉 HWCG 清除**（这是有害的）
```c
/* 之前我加的（错！）—— 会把 S_AHB 的正常 HWCG 状态破坏掉 */
wr(GCC_QUP0_M_AHB_CBCR, rd(GCC_QUP0_M_AHB_CBCR) & ~2u);
wr(GCC_QUP0_S_AHB_CBCR, rd(GCC_QUP0_S_AHB_CBCR) & ~2u);
wr(GCC_QUP0_SE4_CBCR,  rd(GCC_QUP0_SE4_CBCR) & ~2u);
```
**必须删除**：HWCG 位是硬件正常状态，清掉可能导致时钟分支行为异常。

### 改动 3：分阶段打印（诊断用）
在访问 SE 前打印所有 CBCR 原始值，这样即使挂死也能从上次输出看到状态。

## 3. 为什么这次一定不会再挂死

| 风险 | 保障 |
|---|---|
| 判定误判 → 进 SE 但时钟没开 | `cbcr_running()` 与 sheng 逐字一致 + 真机数据验证 |
| 清 HWCG 破坏时钟 | 改动 2 明确删除 |
| 进 SE 后挂死 | 保留 `k60_touch_se=1` 门控（默认关），只有显式开启才进 |
| 改坏构建 | `fix-patch-hunks.py` 自动校正 hunk |

## 4. 执行顺序（安全）

1. **改代码 + 构建**（不动 boot-arg，`k60_touch_se` 保持关闭）
2. **刷机验证系统仍正常启动** ← 这一步确认改动无害
3. **加 `k60_touch_se=1` 再刷** ← 这一步才真正测试 SE
4. 看日志：
   - 出现 `Pong touch: clocks ok m=0 s=0x80000002 se4=0x4220` → **判定修好了**
   - 下一步出现 GENI 识别日志 → **SE 通了**
   - 0 日志挂死 → 退回改动 2 的检查（是否还有别处清 HWCG）

## 5. 剩余未知（诚实列出）

| 未知 | 影响 | 应对 |
|---|---|---|
| GENI `IF_DISABLE_RO` bit0=1（FIFO 被禁） | 即使时钟对了，FIFO 仍可能被拒（`GeniSpi.c:80` 硬拒 −95） | 有两个钩子：`use_dma` 或 `allow_fifo_disabled`。我们的代码是否已处理？需查 |
| Goodix 固件加载协议 | SE 通了之后才暴露 | 分阶段推进 |
| AVDD GPIO71 上电时序 | 探测失败可能 | 分阶段 |

**但这些都是 SE 通之后的问题。当前第一步只需让时钟判定正确。**
