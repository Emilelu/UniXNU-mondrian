# GPU / Metal 待办（2026-11-12）

> 本文件记录 GPU 与 Metal 的移植欠账。每项都必须按八步流程走，
> 完成后在 `docs/research/EIGHT-STEPS.toml` 的 gpu 段更新证据。

## 现状（2026-11-12 实测）

| 组件 | 我们 | pong 最新 | 官方 AdrenoMetal | 差距 |
|---|---|---|---|---|
| `drivers/PongAdreno/PongAdrenoPlatform.cpp` | 26,279 B | 22,733 B | — | 我们多 3.5 KB（K60 RSC 直接映射 + 只映射已消费 GCC 页）|
| `drivers/PongMetal/NativeBridgeMetalFrontend.mm` | **109,178 B** | 166,152 B | **369,834 B** | **少 57 KB（vs pong）/ 260 KB（vs 官方）** |
| `NativeAdrenoMetalPlugin.mm` | 无 | — | 51,271 B | 缺 |
| `HostMetalCommandServer.mm` | 无 | — | 59,947 B | 缺 |
| `GpuScanoutPresenter.h` | 5,013 B | — | 12,636 B | 少 7.6 KB |

**内核侧我们比 pong 新；Metal 用户态严重落后。**

---

## 待办清单

### P0 —— 官方 AdrenoMetal 的性能优化（24 小时内 8 个提交）

官方仓库：`https://github.com/UniXNU/AdrenoMetal`
本地镜像：`references/AdrenoMetal`（main = `83b667824`）

| 提交 | 内容 | 价值 |
|---|---|---|
| `9c09d41` | `perf(bridge): lower on the lowering thread, submit at commit, warm pipelines` | 降低在 lowering 线程做、提交在 commit 做、预热管线 |
| `dfb5edc` | `perf(bridge): relaxed half arithmetic and Turnip driver facts in the runtime` | 放宽 half 运算 |
| `9ddfaf2` | `perf(turnip): let Turnip choose each pass's rendering, with concurrent binning` | Turnip 自选 pass 渲染方式 + 并发 binning |
| `20be9f9` | `perf(plugin): render every pass in tile memory` | 每个 pass 在 tile memory 内渲染（省带宽）|
| `54ac1a0` | `feat(diag): count what screen-size passes draw on` | 诊断：统计全屏 pass |
| `beeab71` | `fix(diag): keep the frame trace on macOS and through a reset` | 诊断：帧追踪跨 reset 保留 |
| `83b6678` | `feat(diag): send Turnip's log to the system log and a file` | 诊断：Turnip 日志进 syslog + 文件 |

**做法**：这些改动集中在 `NativeAdrenoMetalPlugin.mm` 和 `bridge/NativeMetalObjects.rs`，
不含平台地址，**可移植**。但要先确认它们的 API 是 21H461 还是 20G81。

### P1 —— pong-metal 的中间层

pong-metal 的 `NativeBridgeMetalFrontend.mm` 是 166,152 B，比我们多 57 KB，
比官方少 204 KB。它是「官方 → 20G81 适配」的中间产物，**最贴近我们的版本**。

需要 diff 出 pong 比我们多的 57 KB 是什么。

### P2 —— 内核侧对齐 pong-adreno

pong-adreno 有 `port/ios18e-native-302` 分支（`5bc6f4cc2`，2026-11-11），
我们只跟到 `main`（`3e8ffa242`，2026-11-03）。

需要 diff `port/ios18e-native-302` 对 `PongAdrenoPlatform.cpp` 等的改动，
判断哪些是 22G100 专有、哪些是硬件修复。

### P3 —— 补齐官方缺失文件

```
NativeAdrenoMetalPlugin.mm     51,271 B
HostMetalCommandServer.mm      59,947 B
IOGPUMetalDeviceShim.h         13,746 B
GpuScanoutClient.h              7,956 B
CacheExport.h                  17,362 B
NativeMetalBridgePhase.h       10,579 B
```

先判断哪些是 20G81 必需、哪些是 21H461 专有。

---

## 关键约束

1. **`pong_metal=1` 时 backboardd 崩溃**（`-[NSURL fileURLWithPath:]` nil）。
   当前用 `pong_metal=2` 绕开，但那样 `IOAcceleratorES` 发布 0 次、`native Metal entry` 0 次。
   **这是 ⑦ 核验必须解决的前提。**

2. **20G81 vs 21H461 ABI 差异**。官方 `AdrenoMetal` 的 `os_abi` 是
   `ipados-17.7.11-21H461`，我们是 `ipados-16.6.1-20G81`。
   移植前必须核对 `_MTLDevice` ABI、`NativeAdrenoAbiVersion`、`chip_id`、`gmem_bytes`。

3. **`chip_id` 不同**。官方是 A740（SM8550），我们是 A730v3（`0x07030002`）。
   GPU 命令流可能有差异。

---

## 下一步（按八步流程）

① 同型：已完成（pong / 官方）
② 官方：已完成（unixnu.com/zh/porting/gpu）
③ 反编译：已完成（live FDT `0x07030002`）
④ 广域：**需补充** —— 把官方 AdrenoMetal 加入 `SOURCES.toml` 的 gpu 段
⑤ 方案：待写（本次待办就是方案输入）
⑥ 深挖：待做（diff 出具体差异）
⑦ 核验：待做（ABI 静态对照 + 产物检查）
⑧ 上机：待做（`pong_metal=1` 下验证）

**先做 ④**：把 `references/AdrenoMetal` 与 `references/pong-metal` 加进 SOURCES.toml。
