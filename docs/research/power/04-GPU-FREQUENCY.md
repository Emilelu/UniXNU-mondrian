# GPU 调频（官网 §5 的 GPU 条目）

状态：**GMU XO 忙碌计数器、HFI id 30 投票与 16 ms governor 线程已实现，host 140 项断言；
opt-in（`pong_gpu_dcvs=1`）。image o（02:14）验证了线程与计数器读取（24 条窗口、无 panic）；
image q（02:36，`pong_gpu_dcvs=2`）进一步验证了 HFI id 30 投票：升一档被接受、随即还原到 floor 也被接受；
提交窗口现在会先布防 50 ms 唤醒档（`34ab1da1`），仍无真实负载数据**。
官网 `https://unixnu.com/zh/porting/power` §5 对 GPU 的要求只有一句（快照
`E:/k60-work/scratch/power-page-20261117.txt:114`）：

> GPU：读取 GMU XO 忙碌计数器，按让 GPU 约一半时间忙碌的档位通过 HFI 投票，同时投该档位的带宽。

同段的触摸/帧/fence 规则（:115-117）会改变这个档位：触摸后 GPU 保持最高档到最后一帧后 1 s；
最近 4 个窗口有 2 个有提交时 CPU 各域不低于 60 %；GPU 从空闲恢复时 50 ms 内以两倍频率运行、
至少 578 MHz。触摸与提交窗口已接（`aa3bada7`/`34ab1da1`），fence 未接。

## 1. 本板已有的硬件事实

- **13 个 GPU OPP**：`drivers/PongAdreno/PongAdrenoPowerProfile.h:2-16` 按 Android 降序给出
  900 / 862 / 815 / 765 / 710 / 645 / 580 / 515 / 440 / 364 / 323 / 285 / 220 MHz，
  每档还带 GX/CX 电压 corner 与 bus 索引。
- **HFI 线序**：`drivers/PongAdreno/PongAdrenoPower.c:152-161` 把同一张表按**升序**装进
  performance 表：wire index 1 = 220 MHz，wire index 13 = 900 MHz，index 0 是 level 0。
  规划模块刻意沿用这个 1 基索引，投票时不需要第二次映射。
- **带宽表**：`PongAdrenoDdrBandwidth[12]`（`PongAdrenoPowerProfile.h:17`），
  `PongAdrenoPower.c:173-185` 把它编成 HFI bandwidth 段；HFI id 30 的第三个字是
  **bus index（带宽档索引）**，不是 kB/s。每档的索引就是 `PongAdrenoPowerLevels[].bus`，
  DCVS 已经按档投票；哪一档配哪条带宽由这张保留表决定，不能由本模块猜。
- **忙碌计数器**：`PongAdrenoCpProfile.h:306-307` 已有
  `GEN7_GMU_CX_GMU_POWER_COUNTER_XOCLK_0_L/H = 0x1f844/0x1f845`，即 19.2 MHz XO tick。
  本树还没有任何代码读它。
- **HFI 传输**：`PongAdrenoHfi.h` 有 `PongAdrenoHfiExchange()`，一条命令在途、失败即毒化；
  id 30 的 GX_BW_PERF_VOTE 载荷是 `{1, level, bus index}`（sheng 参考同 id 同形状；第三字是带宽档索引，不是字节数）。

## 2. 参考实现（UniXNU-sheng origin/main，2026-11-17）

`package/GpuPowerProbe.cpp` 148,992 B，`gpu-dcvs=1` 时在 Metal 服务发布后启动：

- 每 16 ms 读一次 XO 忙碌计数器；窗口工作量 = 忙碌 tick × 该窗口实际频率，
  跨档位求和后取「让这段保持 50 % 忙碌」的频率（`msm_gpu_devfreq` upthreshold 50）。
- 立即升到不低于该频率 1.1 倍的最低档；整段忙碌超过 85 %（或连续 50 ms 无停顿）直接到顶。
- 连续 4 个窗口（刚升档后 5 个）都只需要下一档的 0.8 倍才降一档；80 ms 无工作回落到 floor。
- 每次换档都是一条 HFI id 30 的 GX_BW_PERF_VOTE，同时带该档的 bus index（带宽档）；`gpu-dcvs-min` 设 floor。

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
- `k60_gpu_vote_payload(level, bus_index, out)`：生成 `{1, level, bus index}` 三字载荷，
  越界返回 0。**只生成载荷，不发送。**

Host 测试 `scripts/tests/test-k60-gpu-freq-plan.c`，123 项：

```sh
cc -Wall -Wextra -Werror -std=c11 -o /tmp/tgpu \
  scripts/tests/test-k60-gpu-freq-plan.c drivers/PongPower/K60GpuFreqPlan.c
/tmp/tgpu
```

结果：`TESTS OK 123 checks (0 failures)`，覆盖升序/去重/越界、19.2 MHz 换算与夹取、
50 % 保持、1.1 倍升档、85 % 到顶、0 忙碌降档、4/5 窗口下降、80 ms 空闲、投票载荷边界、
kHz→档位查询（含档间值）与唤醒档（两倍频率、578 MHz 下限、到顶夹取、空表），
以及 2026-11-19 01:41 抽出的 DCVS 窗口规则（见 §3.1）。

### 3.1 运行时接线（2026-11-19 凌晨）

参考 zizhan 的 GMU 忙碌计数器与 DCVS 线程（同 SM8475，BSD-2-Clause-Patent），移植为：

- `drivers/PongAdreno/PongAdrenoGmu.c`：新增 `PongAdrenoGmuEnableBusyCounter()`
  （掩码 `0xff000000`、选择 `0x20`、使能后回读）、`PongAdrenoGmuBusyTicks()`
  （连续读 `XOCLK_0_L/H/H`，高字稳定才接受）与 `PongAdrenoGmuSetLevel()`
  （HFI id 30 `{1, level, bus index}`，100 ms 上限；超时或错误毒化 HFI 会话）。
  寄存器常量加在 `PongAdrenoRegisters.h`；生成脚本会扫描 `Gmu.c` 的 `GEN7_*` 名字，
  缺一个就拒绝生成。
- `drivers/PongAdreno/PongAdrenoDcvs.cpp`：16 ms 线程；每窗口读计数器、按 625/12 ns
  一个 XO tick 换算、空闲转活跃时给 50 ms 唤醒档，然后走 `k60_gpu_governor_window()`
  决策并通过 `PongAdrenoGmuSetLevel()` 投票。连续 8 次投票被拒就停止线程并毒化，
  不空转；每 10 s 打一条汇总，日志前缀 `PONG ADRENO: ` 以便和 ramoops 诊断对齐。
- 策略仍留在 host 测试覆盖的 `K60GpuFreqPlan`：新增 `k60_gpu_level_for_khz()` 与
  `k60_gpu_wake_level()`，线程不自己算档位。
- 2026-11-19 01:41（`ff49b5a6`）把整条窗口规则也搬进了这个模块：
  `k60_gpu_dcvs_reset()` / `k60_gpu_dcvs_window()` / `k60_gpu_dcvs_voted()`。
  线程只剩读计数器、投票、汇总和停止报告；空闲累计、空闲转活跃时布防唤醒档、
  唤醒到期、floor/top 夹取、连续 8 次被拒停止都在 host 侧断言（`1db88bc2`；`34ab1da1` 后 140 项）。
  顺带修掉一处与文档不符的行为：旧代码的 `refused` 计数跨整个运行累加，
  一次成功投票也不清零；现在按文档「连续 8 次」在成功投票后清零。
- 2026-11-19 02:05：接上官网 §5 :116 的**提交窗口**输入。`PongAdrenoCp.cpp` 导出只读的
  `pong_adreno_cp_pending()`（`CP_RB_RPTR != CP_RB_WPTR` 表示 CP 尚未回收，CP 未启动返回 -1），
  DCVS 线程每 16 ms 把该窗口喂给 host 测试覆盖的 `K60BoostPlan`
  （`k60_boost_window()`），每 10 s 额外打一条
  `PONG ADRENO: DCVS frames result=<0..4> a=<d0 floor kHz<<32|active> b=<累计提交窗口>`。
  floor 按 d0 顶部 1,804,800 kHz 的 60 % 计算（`K60BoostPlan` 的 40 项 host 断言覆盖
  两窗口/四窗口判定、提交窗口滑动与 60 % 下限）。CPU 侧自 `cbdf382f` 起由采样线程把
  `framing` 交给 governor 并写 60 % 下限；GPU 侧 `34ab1da1` 新增
  `k60_gpu_dcvs_submit()`，提交窗口活跃且 GPU 空闲时先布防 50 ms 唤醒档，不等忙碌
  计数抬升。host 140 项覆盖这两处。
- 启动开关：boot-arg `pong_gpu_dcvs=1`（默认 0）；`pong_gpu_max_level`（默认 13）、
  `pong_gpu_dcvs_min`（默认 1）、`pong_gpu_dcvs_boost_ms`（默认 50）可调。
  `PongAdrenoPlatform.cpp` 在 Adreno 启动记录完成后才调用 `pong_adreno_dcvs_start()`，
  CP 启动失败则不启动。

## 4. 边界

- **DCVS 验证到「空闲 + 单次投票」**：image o 02:14 上机验证线程与计数器读取（24 条窗口、
  计数器恒 0）；image q 02:36 用 `pong_gpu_dcvs=2` 验证 HFI id 30 投票被接受（升档、还原各一次，
  错误码 0）。仍缺的是**负载驱动**：没有一次「忙碌计数升高 → governor 升档 → 投票 → 频率/帧时间变化」
  的闭环数据；带宽档由静态 bus index 选择，HFI 不接受字节级的动态带宽需求；image p（抽出的窗口规则）与含 CP 提交窗口的镜像仍未上机。
- image p：`boot.img` 201,887,744 B sha256 `5a03277403d68358c07910a551e3376e3aacebc8a877700f397d8e814a35b676`，
  kernel `4b9fa1f96302afc6604afaac306cd9c6b389ad5638c4d1b9b1c1f3f0147d3849`，
  payload `7a6c891224c6045dee50b79a55035b8b595095e259dadf704a2d4025d789387e`；
  参数 gate `OK (30 arguments, 605 bytes)`；平台 archive 含 3 个 `_k60_gpu_dcvs_*` 符号。
- **提交窗口、触摸与 60 % 下限已接，fence 未接**：`pong_adreno_cp_pending()` 把 CP 环
  占用喂给 `K60BoostPlan`，CPU 采样线程把 `framing` 传给 governor，mode 8 的升档窗口
  会写 60 % 下限；触摸计数补丁 `0622` 导出 `pong_touch_report_count()`，DCVS 线程在
  1 s 触摸窗口内把目标档强制为 top（`DCVS touch top`/`release`，commit `aa3bada7`）。
  仍缺 fence 截止时间与真实 GPU 负载：image w 的 276 条样本全部 `fr=0`，触摸保持也
  还没有真机触摸数据；50 ms 唤醒档现在既由计数器从零转非零触发，也由提交窗口
  提前布防（`34ab1da1`，日志 `DCVS prewake`）。
- **2026-11-19 02:14 真机（image o）**：启动 22 个阶段全部成功，`:714` 打出
  `PONG ADRENO: DCVS started result=0 a=0xd00000001 b=0x1`（top 13、floor 1、初始 level 1），
  之后每 10 s 一条 `DCVS window result=1 a=0x0 b=0x0`，共 24 条（约 4 分钟，控制台 138,144 B，
  sha256 `ba1d374b805be831935d07f8878c92854369105f3effb5c747b5357c4a9b756e`），
  无 `STOP DCVS`、无 panic、无失败投票。含义：16 ms 线程在 XNU 里稳定运行、GMU 忙碌计数器
  每次读取都返回 0（整轮无 GPU 提交），governor 停在 floor，HFI 投票路径一次也没走到。
- **2026-11-19 02:36 真机（image q，`pong_gpu_dcvs=2`）**：启动时先打
  `DCVS probe up result=0 a=0x200000000 b=0x1`（目标档 2，HFI 错误码 0，原档 1），
  紧接着 `DCVS probe restore result=0 a=0x100000000 b=0x0`（回 floor 1，错误码 0）。
  说明 **HFI id 30 `{1, level, bus index}` 投票在本板固件上被接受**，不只是构造出报文。
  整轮仍是空闲（29 条汇总窗口、计数器 0），所以「负载→升档」的闭环还没有数据；控制台
  139,802 B、sha256 `e6aae5c1941fe5f3132c863005b0d3f43d5bc1dd5e64263e015d146754489e36`，
  无 panic、无 `STOP DCVS`。
- **没有温控/电压顺序**：升档只发 HFI 投票，没有先检查温控、也没有按官网 §5 :108
  的顺序处理稳压器与互连；如果固件自己降频，投票可能被拒，连续 8 次拒绝会停线程。
- **带宽档来自静态表**：`PongAdrenoPowerLevels[13-want].bus` 是 power 表里的保留值，
  也是 HFI 的带宽档索引，不是动态测量的 kB/s 需求。官方“同时投该档位的带宽”在 HFI
  协议里就是投这个索引；若以后要按实测 DDR 压力换档，需要另立输入，当前没有证据要求。
- **只有一个消费者**：DCVS 线程与 CP 启动共用 GMU HFI 通道；线程在启动记录完成后才起，
  但之后没有暂停/恢复接口（GPU 目前没有拆卸路径）。

## 5. 下一步（都需要设备）

1. 设备探针：用 image o 启动一次 `pong_gpu_dcvs=1`，确认忙碌计数器在动、投票被接受，
   并记录 10 s 汇总里的档位分布。
2. 负载对照：跑一段 GPU 负载，比较投票前后的档位与帧时间，确认没有和固件 DVFS 打架。
3. 触摸/帧信号：触摸已接（补丁 0622 + commit aa3bada7），下一步在 image x 上机触摸；
   帧下限等 Metal 提交计数可用后验证 300 ms/60 %。
4. 温控与顺序：在升档前接入温度读取与电压/互连顺序，否则只保留降档方向。

## 6. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:105-118`。
- sheng：`package/GpuPowerProbe.cpp`（origin/main 6c42e10），`gpu-dcvs`/span/min 注释段。
- 本板表：`PongAdrenoPowerProfile.h`、`PongAdrenoPower.c:152-188`、`PongAdrenoCpProfile.h:306-307`。
- 相邻工作流：`docs/research/power/01-EPSS-PROBE.md`（CPU 侧同一套 50 %/窗口思路）。
