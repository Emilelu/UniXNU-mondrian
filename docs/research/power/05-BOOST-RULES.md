# 触摸/帧/GPU 唤醒与 fence 规则（官网 §5 :115-117）

状态：**规则模块 + host 40 项断言；触摸与帧输入已接线并在真机触发，触摸写回已在 image ab 上机成立（d0 `state=15->94`、`hw=1804800kHz`），票数预算与全簇 boost 由 `43af2a5c` 修正，image ac 待上机**（触摸计数补丁 `0626-k60-touch-activity.patch`，消费方 `aa3bada7`，重开窗口 `9b8a36b6`，预算/boost `43af2a5c`；GPU 预唤醒 `34ab1da1`，host 140）。
官网 `https://unixnu.com/zh/porting/power` §5 在 CPU/GPU 调频之后还有四条规则
（快照 `E:/iOS Port/Work/scratch/power-page-20261117.txt:115-117`）：

> 触摸：收到触摸报告后，P 频域和 GPU 保持最高档，直到最后一次报告后 1 s
> （cpufreq-boost-ms、gpu-dcvs-boost-ms）。
> 帧：最近 4 个窗口中有 2 个有 GPU 提交时，所有 CPU 频域在 300 ms 内不低于各自最高档的 60%。
> GPU 从空闲降频后恢复工作时，50 ms 内以当前频率的两倍运行，至少 578 MHz。
> fence 等待：等待者睡眠到 fence 中断为止，最长 1 ms（gpu-pause-us），不再轮询。

## 1. 已经接上的输入

- 触摸：`patches/xnu/0626-k60-touch-activity.patch` 在 `bsd/dev/pong_input.c` 里加一个
  `uint32_t` 计数和 `pong_touch_report_count()`，每次 `pong_touch_post()` 入队后自增；
  CPU 采样线程与 GPU DCVS 线程每 16 ms 读这个计数，计数变化就是一次触摸报告。
- GPU 提交：`pong_adreno_cp_pending()` 读 CP 环读写指针，采样线程每 16 ms 把
  「这个窗口有没有提交」喂给 `k60_boost_window()`。
- GPU 空闲/唤醒：DCVS 线程用忙碌计数从零转非零作为空闲→工作边沿，唤醒档保持
  `pong_gpu_dcvs_boost_ms`（默认 50 ms）；`34ab1da1` 起，提交窗口判定为活跃
  （最近 4 个窗口有 2 个提交）且 GPU 空闲时先调用 `k60_gpu_dcvs_submit()` 布防同一
  唤醒档，不等计数器抬升。

## 1.1 仍然缺什么

- fence 等待仍在提交路径里轮询/超时，没有统一的 1 ms 预算，也没有 fence 中断消费者。
- 触摸计数只有「有没有新报告」，没有报告时间戳与触点数量；1 s 窗口从采样线程看到计数的
  那个 16 ms 窗口起算，最坏晚 16 ms。
- 没有温度/throttle 读数；触摸保持与帧下限都不检查温度。
- 触摸已有真机数据（image x，2026-11-19 05:47）：触摸后 12 条 `touch boost` 日志、7 条 `tb=1`
  样本，报告计数 1→7；但 mode 8 的 10 s 写回窗口在 ~20 s 就已恢复，触摸发生在 ~121 s，
  所以只有 governor 抬档、没有寄存器写入，`9b8a36b6` 补了重开窗口，但投票仍受 100 s 上限；`a0e8a060` 才让信号窗口脱离该上限。
- 触摸写回在 image ab（07:18）成立：win=6937 `touch window` 后 d0 写 `level=13 state=15->94`，win=6976 样本 `hw=1804800kHz tb=1`，窗口末 `restore domains=3 votes=27`。同轮第二触（win=7207）只写 5 票就 `votes=32` 恢复，说明票数当时是整轮累计；`43af2a5c` 改为每窗口重置，并让 `boost` 对每个域取 top（原先只作用于共享簇，轻触摸抬不动 d0）。image ac 带这份修复，待上机。
- 帧仍无真机数据：image w 的 276 条样本全部 `fr=0`，启动全程没有 GPU 提交。

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

消费方：

- CPU：`K60CpuFreqProbe.cpp` 的采样线程把 `k60_boost_touch_active()` 作为 governor 的
  `boost` 参数，mode 8 的写回窗口把 P 域抬到最高档；触摸后的 1 s 内每个 16 ms 窗口
  都会重新抬到 top，窗口结束后的第一个降档窗口才允许写回。`9b8a36b6` 起，触摸上升沿
  （或帧下限上升沿）会重开一个短写窗口：触摸 63 个窗口（1 s）、帧 19 个窗口（300 ms），
  `applyUntil` 取较晚者，总票数上限仍是 32；日志 `mode<7|8> touch window win=… span=… applyUntil=… domains=0x…`。
  信号窗口不受 100 s 的 `kApplyLatestEndWindow` 限制（`a0e8a060`），开机突发窗口仍受。
- GPU：`PongAdrenoDcvs.cpp` 在触摸窗口内把目标档强制为 `top`，并在 `DCVS touch top` /
  `DCVS touch release` 两条日志里记录报告计数与时间；窗口结束后恢复正常 governor。
  提交窗口另有 `DCVS prewake`：GPU 空闲时提前布防 50 ms 唤醒档，日志带档位、
  时间与累计唤醒次数；`k60_gpu_dcvs_window()` 不会重复布防同一次唤醒。
- 帧：CPU 采样线程把 `k60_boost_frame_active()` 作为 `framing` 参数，`k60_cpufreq_target()`
  把目标钳到 60 % 下限。

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

- 触摸计数已上机（image x 05:47）：`touch boost active/released`、`tb=1`、计数 1→7 都出现，
  「触摸 → tb=1 → governor 抬到 1,804,800 kHz」时序成立；image ab 更进一步：`touch window` 内 d0 写入 `state=15->94`，样本 `hw=1804800kHz`，硬件确实跟随，窗口末恢复原值。32 票预算已改为每窗口一份，`boost` 已覆盖每个域；image ac 待上机验证「轻触摸也抬 d0」与第二触仍有预算。
- 触摸保持把 P 域抬到 top 依赖 EPSS 接受写回：d0 已验证双向写回，d1/d2 的写回不被
  EPSS 接受（image s 的 `state=130->130`），所以「P 域」目前只有 d0 真正生效。
- GPU 触摸保持只改 HFI 投票目标，是否被固件接受取决于当时温度/负载；连续 8 次拒绝会停线程。
- fence 规则仍没有消费者；1 ms 预算只是函数。
- 1 s/300 ms/50 ms/1 ms 都是官网数字，没有在本板测过实际效果。

## 4. 下一步（需要设备或其他线）

1. 上机触摸：image ab 已确认 `touch window`、d0 `apply`/`state` 与 `hw` 跟随（07:18）；
   下一步用 image ac（`43af2a5c`）做一次轻触摸，确认 `boost` 直接抬 d0（不依赖触摸负载），
   并在同一轮里触摸两次，确认第二个窗口仍有完整 32 票预算、窗口末才 `restore`。
2. GPU 触摸：同一次启动加 `pong_gpu_dcvs=1`，确认 `DCVS touch top` / `DCVS touch release`
   两条日志，并核对 HFI 投票错误码。
3. 帧下限：等 Metal 提交路径可用后跑一段负载，确认 `fr=1` 时 CPU 投票抬到 60 %。
4. fence 路径改成 sleep-until-interrupt，记录实际等待直方图，确认 1 ms 预算是否合理。

## 5. 参考

- 官网快照：`E:/iOS Port/Work/scratch/power-page-20261117.txt:115-117`。
- sheng：`package/GpuPowerProbe.cpp` 的 `gpu-dcvs-boost-ms`、
  `package/CpuFreqProbe.cpp` 的 `cpufreq-boost-ms`/`cpufreq-frame-ms`/`cpufreq-frame-pct`。
- 相邻模块：`docs/research/power/01-EPSS-PROBE.md`、`04-GPU-FREQUENCY.md`。
