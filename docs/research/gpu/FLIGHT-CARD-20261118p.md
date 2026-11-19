# 上机卡 20261118p — Turnip 渲染模式：sysmem → gmem（官方默认）

## 1. 这次只改一件事

`drivers/PongMetal/PongMetalPlugin.mm:151` 的 `setenv("TU_DEBUG","sysmem,nocb",1)` 改成
`"gmem,nocb",1`。**只改渲染模式**：`nocb`（关闭 concurrent binning）保持不动，因为 Pong 的
BV/BR 调度仍未实现；其它环境变量、内核、补丁序列全部不变。

## 2. 为什么改它

`gpu-wc-class-20261118`（`usblog-20261118-233946`）的分类探针把 submit 的成本定到了
imported 帧的 cache 维护（93.2 MiB/次，publish 中位 6,635 µs），**而这一飞里最大的单项已经不是
submit，是 GPU 等待**：

| 阶段 | 中位（gpu-wc-class 这一飞） |
| --- | --- |
| `submit` | 8,171.5 µs |
| `encode` | 1,292.5 µs |
| **`gpu`** | **12,447.5 µs** |
| `publish`（在 submit 内） | 6,635 µs |

18.4 MB（1440×3200×4）用 12.4 ms ≈ **1.5 GB/s**，远低于 A730 的合理带宽。官方文档
`https://unixnu.com/zh/porting/gpu` 的默认渲染模式是 `gmem,nocb`，本机被插件强制成 `sysmem`，
而 `sysmem` 意味着每个 render pass 都直接写系统内存、没有 tile 驻留 —— 与「大面拷贝慢一个数量级」
的现象一致。gmem 路径在 Turnip 树里本来就存在（`tu_cmd_buffer.cc:1444` 的
`if (TU_DEBUG(GMEM)) { gmem_disable_reason = "TU_DEBUG(GMEM)"; return false; }`），不需要新补丁。

## 3. 前置检查（不满足就不飞）

- P1 插件 `strings` 含 `gmem,nocb`（不是 `sysmem,nocb`）。
- P2 内核与上一飞一致（`4c97a900…` 之后只在插件侧改动），`verify-boot-image: OK`。
- P3 命令行仍是 30 项 / ≤607 B，`image-arg-audit: OK`。
- P4 `K60_AGENT_ID` 已设置（机器级 boot claim 署名，rc=7 会拒）。
- P5 本卡先于镜像提交（`check-flight-card.py` 会拒「判据写在镜像之后」）。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

- `MiniIOMobileFramebuffer: N frames` 且 N > 0，同时 `Pong Metal: c<n>/0` 且 n > 0，
  且至少一条 `scanout frames=`。三者缺一 ⇒ 本次**无效**，不得当成失败规则命中。

### 4.2 路径身份

- `scanout copy texture untile` 仍出现且 `imports == frames`（拷贝形状没被顺手改掉）。

### 4.3 假设是否成立（这一飞唯一要回答的问题）

- **S4** `gpu` 中位 **< 6,000 µs**（对照 12,447.5 µs）。
- **S5** `copy` 中位 **< 18,000 µs**（对照 25,347 µs 最好值、今晚 16,154 µs 单条）。
- **S6** 采样窗口内 fps > 7.28（迄今最好一飞）。

### 4.4 成功判据汇总

- **S1** 无 `K60KEXC`、无 `panic(`、`crashed: backboardd` 0 次。
- **S2** 有效性三项齐全（见 4.1）。
- **S3** 形状行仍为 `texture untile`，`imports == frames`。
- **S4** `gpu` 中位 < 6,000 µs。
- **S5** `copy` 中位 < 18,000 µs。
- **S6** fps > 7.28。
- **S7** 无 `GPU copy not retired`、无 `poisoned`。
- **S8** `submit` 中位不得明显变差（< 10,000 µs），确认这次只动了 GPU 侧。

### 4.5 失败规则

- **F1** panic / `K60KEXC` / backboardd 崩 ⇒ 立刻回退 `sysmem,nocb`，不做第二次尝试。
- **F2** 有效性不成立（零帧且无崩溃）⇒ 判无效并重飞一次；连续两次无效 ⇒ 回退。
- **F3** `gpu` 中位仍 ≥ 10,000 µs ⇒ 渲染模式不是原因，下一步改成**减少搬运字节**（不再拷 18.4 MB）。
- **F4** `encode` 中位 > 5,000 µs ⇒ gmem 每次 pass 多了固定开销，记录并回退。
- **F5** 画面花屏/错位（用户目视）⇒ 立即回退，gmem 在 A730 上不可用。
- **F6** `submit` 中位 > 13,000 µs ⇒ 说明变量没被隔离，先修测量再谈结论。

## 5. 结果登记

（飞行后填写：镜像/内核/日志哈希、S1–S8 逐条、F 规则命中、下一步。）
