# 触摸/帧/GPU 唤醒与 fence 规则（官网 §5 :115-117）

状态：**纯规则模块 + host 40 项断言；没有输入源、没有线程、没有消费者、未上机**。
官网 `https://unixnu.com/zh/porting/power` §5 在 CPU/GPU 调频之后还有四条规则
（快照 `E:/k60-work/scratch/power-page-20261117.txt:115-117`）：

> 触摸：收到触摸报告后，P 频域和 GPU 保持最高档，直到最后一次报告后 1 s
> （cpufreq-boost-ms、gpu-dcvs-boost-ms）。
> 帧：最近 4 个窗口中有 2 个有 GPU 提交时，所有 CPU 频域在 300 ms 内不低于各自最高档的 60%。
> GPU 从空闲降频后恢复工作时，50 ms 内以当前频率的两倍运行，至少 578 MHz。
> fence 等待：等待者睡眠到 fence 中断为止，最长 1 ms（gpu-pause-us），不再轮询。

## 1. 本树缺什么

- 没有 `native_hid_input_events`（sheng 用它数触摸报告），K60 的触摸驱动也不在本分支；
  触摸事件目前没有任何统一入口。
- Adreno 提交路径在 `drivers/PongAdreno/submit/`，但没有「每 16 ms 窗口是否有提交」的计数，
  也没有帧窗口/boost 状态；`NativeAdrenoUserClient.cpp` 只做提交与统计。
- GPU 空闲/唤醒没有状态机；EPSS/GPU 规划模块只有档位算术，没有事件输入。
- fence 等待仍在提交路径里轮询/超时，没有统一的 1 ms 预算。

## 2. 已实现的规则

`drivers/PongPower/K60BoostPlan.h` + `.c`：

- `k60_boost_touch(state, now)` / `k60_boost_touch_active(state, now)`：
  最后一次触摸后 1000 ms 内为真；正好 1000 ms 为假（严格小于）。
- `k60_boost_window(state, now, submitted)`：把一个 16 ms 窗口压进 4 位历史，
  bit0 最新；记录最近一次提交时间。由调用方采样「这个窗口有没有提交」。
- `k60_boost_frame_count()` / `k60_boost_frame_active(state, now)`：
  只有凑满 4 个窗口、其中至少 2 个有提交、且距最近提交不到 300 ms 时才为真；
  刚启动窗口不足 4 个时不误判。
- `k60_boost_cpu_floor_khz(top_khz)`：最高档 × 60 %（向下取整）。
- `k60_boost_gpu_wake_khz(current_khz, top_khz)`：`max(2×当前, 578000)`，再用 top 封顶。
  本板 top 900 MHz，所以 578 MHz 实际落在 580 MHz 档附近。
- `k60_boost_fence_ok(start_us, now_us)`：0..1000 µs 为真；超时或时间倒流为假。

Host 测试 `scripts/tests/test-k60-boost-plan.c`，40 项：

```sh
cc -Wall -Wextra -Werror -std=c11 -o /tmp/tboost \
  scripts/tests/test-k60-boost-plan.c drivers/PongPower/K60BoostPlan.c
/tmp/tboost
```

结果：`TESTS OK 40 checks (0 failures)`。覆盖触摸 999/1000 ms 边界、4 窗口移位与掩码、
2/4 帧门槛、300 ms 边界（331/332）、60 % 取整、578 MHz 下限与 top 封顶、1 ms fence 边界、
空指针。

## 3. 边界

- 规则模块没有任何输入：没有触摸事件、没有帧窗口采样、没有 GPU 空闲状态、没有 fence 中断。
- 没有和 CPU/GPU governor 连接：`K60CpuFreqPlan` 的 boost 参数、`K60GpuFreqPlan` 的
  `after_up`/floor 都还不知道这些规则存在。
- 触摸保持「P 频域和 GPU 最高档」需要 board 策略知道每个域的 top；本模块只给 CPU floor，
  GPU 侧只给唤醒频率，不直接改档。
- 未上机；1 s/300 ms/50 ms/1 ms 都是官网数字，没有在本板测过实际效果。

## 4. 下一步（需要设备或其他线）

1. 在触摸驱动或 HID 路径埋一个计数，把报告时间喂给 `k60_boost_touch`。
2. 在 Adreno 提交完成路径按 16 ms 窗口采样，喂 `k60_boost_window`。
3. governor 线程把 `cpu_floor_khz` 作为下限、把 touch/frame 作为 boost 输入；
   GPU 唤醒 boost 在 idle→work 边沿生效 50 ms。
4. fence 路径改成 sleep-until-interrupt，记录实际等待直方图，确认 1 ms 预算是否合理。

## 5. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:115-117`。
- sheng：`package/GpuPowerProbe.cpp` 的 `gpu-dcvs-boost-ms`、
  `package/CpuFreqProbe.cpp` 的 `cpufreq-boost-ms`/`cpufreq-frame-ms`/`cpufreq-frame-pct`。
- 相邻模块：`docs/research/power/01-EPSS-PROBE.md`、`04-GPU-FREQUENCY.md`。
