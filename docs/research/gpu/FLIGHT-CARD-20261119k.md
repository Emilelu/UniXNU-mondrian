# 飞行卡 k：把 GPU 档位从「启动投一次」改成「可以再投」

- **镜像**：`gpu-perf-20261119`
- **日期**：2026-11-19（判据写在镜像之前，`check-flight-card.py` 会核对指纹）
- **上游依据**：`kmu1757/UniXNU-t970` 的 z164 `gpu-perf` 提交（HFI id 30 `GX_BW_PERF_VOTE`、
  boot-arg 只动 GX 档、DDR 档沿用启动值），按用户 m44837「转向参考这个和 zizhan」移植

## 1. 为什么飞这一张

`usblog-20261119-151837`（卡 j，34 条稳态样本）里 `present()` 已经落在 120 fps 预算内
（`sum` 8,281 µs ≤ 8,333 µs），但其中**最大的一项仍是 `gpu` 5,983 µs**——一次 18.4 MB 的 blit。
同一天卡 d 的对照实验证明这件工作本身只要 1,835 µs（10.04 GB/s）：

| 同一 18.4 MB | 耗时 | 吞吐 |
|---|---|---|
| 对照实验里的纯拷贝（卡 d） | 1,835 µs | 10.04 GB/s |
| 真实扫出路径里的 `gpu`（卡 j） | 5,983 µs | 3.08 GB/s |

差 3.3 倍，而两次是同一个 API、同一块目标。剩下的解释只有一类：**执行时 GPU 不在高频**。
这不是猜测——`drivers/PongAdreno/PongAdrenoPower.c:186-187` 只投一次启动票
（`table.default_gpu_index=2`，注释 `DT initial-pwrlevel11 -> ascending wire index2`），
此后全内核**没有任何一处**再改档；zizhan/t970 都在 GX 起来之后重投，t970 还把它做成了 boot-arg。

## 2. 改了什么

| 文件 | 改动 |
|---|---|
| `drivers/PongAdreno/PongAdrenoGmu.h` | `PongGpuGmuDevice` 记住 `perf_gpu_index` / `perf_bus_index` / `perf_votes`；声明 `PongAdrenoGmuVotePerf()` |
| `drivers/PongAdreno/PongAdrenoGmu.c` | 启动投票成功处记下两个索引；新增 `PongAdrenoGmuVotePerf()`：档位 1..13 之外拒绝、GX 未持有则拒绝、有未完成 HFI 头则 `PongGpuBusy`、发 HFI id 30 `{1,档位,DDR档}`、1 秒等到回复才记账 |
| `drivers/PongAdreno/PongAdrenoPlatform.cpp` | `PongAdrenoCpStart()` 成功之后读 `gperf`，非零即投票并打一行 `GPU level vote from gperf` |

**默认不投**：不写 `gperf` 时行为与以前逐字节相同。升频改变功耗与发热，不由默认值决定。

启动行实测：`board.toml` 30 项 596 B，加 `gperf=13` 后 **605 B ≤ 607**（DarwinBoot 上限），
所以这一飞不需要挤掉任何已有参数。

## 3. 前置条件（缺一条就不飞）

- P1 内核里必须有 `GPU level vote from gperf` 与 `PongAdrenoGmuVotePerf` 两个串（`strings kernel.macho`）
- P2 `image-arg-audit: OK` 且命令行 ≤ 607 B，且命令行里确实有 `gperf=13`
- P3 `verify-boot-image: OK`、`kernel archives: 4`
- P4 插件沿用 `metal-plugin-20261119p`（含 `gmem,nocb`），本飞不改插件
- P5 设备在 fastboot，`K60_AGENT_ID=lead`

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

- **V1** 至少一条 `MiniIOMobileFramebuffer: N frames` 且 N ≥ 5
- **V2** 至少一条 `Pong Metal: c<n>/0` 且 n ≥ 5
- **V3** 至少 20 条 `scanout frames=` 且其中 `imports >= 20`
- 任一不成立 ⇒ 判 **INVALID**，不算判据失败，也不得用这一飞谈性能

### 4.2 成功判据

- **S1** `panic(` / `K60KEXC` / `crashed: backboardd` / `DeviceLost` / `CP/SMMU fault` /
  `GPU copy not retired` 各 0 条
- **S2** 恰好一条 `GPU level vote from gperf`，且该行状态为 0、打印了 settle 后的档位与 DDR 档
- **S3** 该行打印的 GX 档等于 **13**（最高档），DDR 档与启动票相同（不得被这个参数改动）
- **S4** 稳态（`frames >= 20`）`gpu` 中位 **< 3,000 µs**（本卡之前 5,983 µs）
- **S5** 稳态 `copy` 中位 **< 6,000 µs**（本卡之前 8,406 µs）
- **S6** 每条 stage 行 `imports == frames`（P-207 口径，防止拿错帧的样本）
- **S7** 面板 `te` ≥ 110/s（这条链上不允许为了 GPU 掉刷新率）
- **S8** 屏幕内容与上一飞一致（由用户目视；本卡不代替目视）

### 4.3 失败规则

- **F1** 没有 `GPU level vote from gperf` 行 ⇒ 先查 P1/P2，判「探针没进镜像」，不得读成「投票无用」
- **F2** 有该行但状态非 0 ⇒ 记录 `firmware_error` 与阶段，**不要再往上加档**；先判断是权限、参数还是 GMU 未接管
- **F3** 稳态 `gpu` 中位 ≥ 5,000 µs ⇒ 档位不是限制项；下一步转 fence 串行化 / vblank 排队 / GPU 频点实测
- **F4** 画面破损、闪屏或压不住的不稳定 ⇒ 立刻去掉 `gperf`，把结论写成「升档在 K60 上不安全」
- **F5** 零帧 ⇒ INVALID（P-236）
- **F6** 出现 `DeviceLost` 或 `CP/SMMU fault` ⇒ INVALID（P-244），不得以帧率为结论

## 5. 结果登记

### 5.1 飞行事实

| 项 | 值 |
|---|---|
| 镜像 | `gpu-perf-20261119`，`boot.img b0add41325199bd9a314b1ec981e4e12de6a17b3bde270c53b54e907ac3adc7f` |
| 内核 | `98fb8d874f2cda4b28374ece163bee2036041b2aa653c91c342c96f2f4c604a6`（105,693,184 B） |
| 命令行 | 31 条 605 B，末项 `gperf=13`（`image-arg-audit: OK`） |
| 插件 | `metal-plugin-20261119p` |
| 证据 | `E:\k60-work\evidence\usblog-20261119-163734`，`console.log` 249,356 B，supervisor rc=0，抓取完整 |

### 5.2 判据

| 判据 | 结果 | 实测 |
|---|---|---|
| S1 无 fault | ✅ | `panic(` / `K60KEXC` / `crashed: backboardd` / `DeviceLost` / `CP/SMMU fault` / `GPU copy not retired` 各 0 |
| S2 恰一条投票行、状态 0 | ✅ | 2 条 `PONG ADRENO: GPU level vote from gperf result=0 a=0xd b=0x2`（两条相同，见 5.5） |
| S3 GX 档 = 13、DDR 档不变 | ✅ | `a=0xd` = 13（最高档）、`b=0x2` = 启动票的 DDR 档，未被这个参数改动 |
| S4 稳态 `gpu` < 3,000 µs | ⏳ 未测到 | 4 帧、0 条稳态 stage 行 |
| S5 稳态 `copy` < 6,000 µs | ⏳ 未测到 | 同上 |
| S6 `imports == frames` | ✅（4/4） | 但样本只有 4 条，不足以支撑中位 |
| S7 面板 ≥110 Hz | ✅ | `K60 PANEL: INTF1 after the UI frame te 120/s … period 7386 us` |
| S8 画面一致 | ⏳ | 需目视 |

### 5.3 结论

**机制成立**：`PongAdrenoGmuVotePerf` 在 CP 起来之后把 GX 档投到 13、DDR 档沿用启动值，
GMU 应答 `result=0`，此后启动过程无 fault。这是本轮唯一新增的行为，它按设计工作。

**性能未测到**：这一飞屏幕静止（`Pong Metal: c8/0 d8`、4 帧、110.9 s 量级），
按 P-236 判 **INVALID**，因此**不能**用它说「升档有没有用」。卡里 S4/S5 记「未测到」而不是「失败」。

### 5.4 为什么又是静止屏（第三次）

`usblog-20261119-095547`（4 帧）、`usblog-20261119-163734`（4 帧）、`usblog-20261119-151837`
（5 帧但 34 条 stage）都是屏幕没有动画。判据一旦依赖「设备上恰好有东西在动」就不是判据。
对策见卡 l：`gperf` 出现时在同一个 offer 内把同一次拷贝重复 24 次（`scanout bench n=…`），
测量不再依赖屏幕。

### 5.5 一个观察

投票行打了**两次**，两行内容完全相同。`record()` 在平台启动路径里只调用一次，所以要么有第二个
调用者，要么 `record()` 自己输出两遍。记在这里，下一飞核对；不影响 plumb 是否生效。

- criteria-sha256: （见下条，指纹由门禁函数计算）
