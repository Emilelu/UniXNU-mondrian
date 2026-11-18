# GPU 调频（官网 §5 的 GPU 条目）

状态：**纯逻辑规划模块 + host 56 项断言；没有 GMU 读取、没有 HFI 投票、没有 governor 线程、未上机**。
官网 `https://unixnu.com/zh/porting/power` §5 对 GPU 的要求只有一句（快照
`E:/k60-work/scratch/power-page-20261117.txt:114`）：

> GPU：读取 GMU XO 忙碌计数器，按让 GPU 约一半时间忙碌的档位通过 HFI 投票，同时投该档位的带宽。

同段的触摸/帧/fence 规则（:115-117）会改变这个档位：触摸后 GPU 保持最高档到最后一帧后 1 s；
最近 4 个窗口有 2 个有提交时 CPU 各域不低于 60 %；GPU 从空闲恢复时 50 ms 内以两倍频率运行、
至少 578 MHz。这些输入本模块都还没有接。

## 1. 本板已有的硬件事实

- **13 个 GPU OPP**：`drivers/PongAdreno/PongAdrenoPowerProfile.h:2-16` 按 Android 降序给出
  900 / 862 / 815 / 765 / 710 / 645 / 580 / 515 / 440 / 364 / 323 / 285 / 220 MHz，
  每档还带 GX/CX 电压 corner 与 bus 索引。
- **HFI 线序**：`drivers/PongAdreno/PongAdrenoPower.c:152-161` 把同一张表按**升序**装进
  performance 表：wire index 1 = 220 MHz，wire index 13 = 900 MHz，index 0 是 level 0。
  规划模块刻意沿用这个 1 基索引，投票时不需要第二次映射。
- **带宽表**：`PongAdrenoDdrBandwidth[12]`（`PongAdrenoPowerProfile.h:17`），
  `PongAdrenoPower.c:173-185` 把它编成 HFI bandwidth 段；哪一档配哪条带宽要由调用方
  从保留表里取，不能由本模块猜。
- **忙碌计数器**：`PongAdrenoCpProfile.h:306-307` 已有
  `GEN7_GMU_CX_GMU_POWER_COUNTER_XOCLK_0_L/H = 0x1f844/0x1f845`，即 19.2 MHz XO tick。
  本树还没有任何代码读它。
- **HFI 传输**：`PongAdrenoHfi.h` 有 `PongAdrenoHfiExchange()`，一条命令在途、失败即毒化；
  id 30 的 GX_BW_PERF_VOTE 载荷是 `{1, level, bandwidth}`（sheng 参考同 id 同形状）。

## 2. 参考实现（UniXNU-sheng origin/main，2026-11-17）

`package/GpuPowerProbe.cpp` 148,992 B，`gpu-dcvs=1` 时在 Metal 服务发布后启动：

- 每 16 ms 读一次 XO 忙碌计数器；窗口工作量 = 忙碌 tick × 该窗口实际频率，
  跨档位求和后取「让这段保持 50 % 忙碌」的频率（`msm_gpu_devfreq` upthreshold 50）。
- 立即升到不低于该频率 1.1 倍的最低档；整段忙碌超过 85 %（或连续 50 ms 无停顿）直接到顶。
- 连续 4 个窗口（刚升档后 5 个）都只需要下一档的 0.8 倍才降一档；80 ms 无工作回落到 floor。
- 每次换档都是一条 HFI id 30 的 GX_BW_PERF_VOTE，同时带该档带宽；`gpu-dcvs-min` 设 floor。

本板 OPP 与 sheng 的 A740 表不同（sheng 9 档、floor 348 MHz），所以规则复用、数字不复用。

## 3. 已实现（纯逻辑）

`drivers/PongPower/K60GpuFreqPlan.h` + `.c`：

- `k60_gpu_build_table(descending_khz, count, out)`：把降序 profile 排成升序 wire 表，
  丢掉 0 与重复频率；返回档数（上限 13），参数不合法返回 0。
- `k60_gpu_busy_permille(busy_ticks, elapsed_us)`：按 19.2 MHz tick 换算忙碌千分比；
  窗口为 0 返回 0，计数器跑过时钟则夹到 1000（采样抖动不应产生 >100 % 的档位请求）。
- `k60_gpu_target(table, current, busy)`：50 % 目标 → 所需频率 → 1.1 倍余量 → 最低满足档；
  85 % 以上到顶；0 忙碌降一档（是否真的降由 governor 的窗口计数决定）。
- `K60GpuGovernor` + `k60_gpu_governor_window()`：升档立即生效并记 `after_up`；
  降档要 4 个连续安静窗口（刚升档后 5 个）；80 ms 空闲直接回最低档。
- `k60_gpu_vote_payload(level, bandwidth, out)`：生成 `{1, level, bandwidth}` 三字载荷，
  越界返回 0。**只生成载荷，不发送。**

Host 测试 `scripts/tests/test-k60-gpu-freq-plan.c`，56 项：

```sh
cc -Wall -Wextra -Werror -std=c11 -o /tmp/tgpu \
  scripts/tests/test-k60-gpu-freq-plan.c drivers/PongPower/K60GpuFreqPlan.c
/tmp/tgpu
```

结果：`TESTS OK 56 checks (0 failures)`，覆盖升序/去重/越界、19.2 MHz 换算与夹取、
50 % 保持、1.1 倍升档、85 % 到顶、0 忙碌降档、4/5 窗口下降、80 ms 空闲、投票载荷边界。

## 4. 边界

- 没有 GMU 映射，没有读 0x1f844/0x1f845，也没有 HFI 调用；模块不在 battery archive 里，
  因为还没有消费者。接入时要同时处理「一条 HFI 在途、失败毒化会话」的传输约束。
- 没有触摸/帧/fence 输入：`native_hid_input_events`、帧提交计数在 K60 上都不存在，
  所以 1 s 触摸保持、300 ms/60 % 帧下限、50 ms 双倍频率都未实现。
- 没有选择带宽：`bandwidth` 由调用方从保留的 power 表取；本模块不把 OPP 序号当带宽序号。
- 没有 governor 线程、没有 16 ms 定时器、没有设备读数或效果证据。

## 5. 下一步（都需要设备或其他线配合）

1. 只读探针：映射 GMU core 窗口（`0x03d00000` 段），读 XO 计数器与当前 perf 状态，
   只打印不投票；先用它确认计数器在 K60 固件上真的在动。
2. 投票：同一探针里发一条 HFI id 30，命令/应答各一次，失败按传输层规则毒化，不重试。
3. governor：16 ms 线程 + 触摸/帧信号，先只记录决策日志，确认不会和固件自身的 DVFS 打架。
4. 设备验收：负载下读频率与帧时间，逐档验证升/降/回落的可观察效果。

## 6. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:105-118`。
- sheng：`package/GpuPowerProbe.cpp`（origin/main 6c42e10），`gpu-dcvs`/span/min 注释段。
- 本板表：`PongAdrenoPowerProfile.h`、`PongAdrenoPower.c:152-188`、`PongAdrenoCpProfile.h:306-307`。
- 相邻工作流：`docs/research/power/01-EPSS-PROBE.md`（CPU 侧同一套 50 %/窗口思路）。
