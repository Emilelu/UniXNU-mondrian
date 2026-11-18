# K60 EPSS 只读探针（power §5 起点）

日期：2026-11-18。范围：官网 power 页 §5 的第一条，CPU 频率（EPSS）。
本文只记录**离线可验证**的部分：寄存器事实、纯算术模块、默认关闭的只读探针、host 断言。
设备测试按用户 2026-11-18 的指示暂缓，本文不声称任何真机频率读数。

## 1. 官方要求

官网快照 `E:/k60-work/scratch/power-page-20261117.txt`：

- `:105-118`：CPU 用 EPSS 频率表与工作点请求；外设供电投票要有归属与引用计数；
  OS 电源回调、休眠/唤醒、负载测量；16 ms governor；GPU GMU/HFI；触摸 boost 1 s；
  帧下限 300 ms / 60%；fence 等待 1 ms。
- `:119-121`：平台睡眠由 PSCI CPU_OFF 关辅核，boot CPU 等待 lid/power/wake-after，
  10 s watchdog 喂狗，背光 1500/600 ms，触摸 60 ms。

## 2. 本仓库此前状态

`drivers/` 里没有任何 EPSS/cpufreq/ApplePMGR/platform-sleep 实现；与供电相关的只有：

- `drivers/PongPower/K60PmicRail.h`：只读的 RPMh cmd-db / DRV-2 TCS 账本（`0x80860000`、
  `0x17a20000`、ld02 tag `0x1c6`），不写寄存器、不投票。
- ADSP Route A 的 lcx/lmx 投票（ADSP bring-up 用），不是 CPU 频率。

因此 §5 此前是 0%。

## 3. 现场设备树证据

对 `E:/k60-work/reports/live-6033dbec-fdt.dtb` 反编译（`dtc`，2026-11-18），K60 的 EPSS
与 SM8550 参考是同一套窗口：

```
/soc/qcom,cpufreq-hw-epss
  compatible = "qcom,cpufreq-hw-epss"
  reg = <0x17d91000 0x1000 0x17d92000 0x1000 0x17d93000 0x1000
         0x17d09804 0x04 0x17d09808 0x04 0x17d0980c 0x04>
  reg-names = "freq-domain0","freq-domain1","freq-domain2",
              "pdmem-domain0","pdmem-domain1","pdmem-domain2"
  qcom,lut-row-size = <4>; qcom,skip-enable-check; qcom,perf-lock-support
  interrupts = <0x1e>, <0x1f>, <0x13>; #freq-domain-cells = <2>
/soc/dcvs/... compatible = "qcom,dcvs-hw"; dcvs-hw-type = <2>;
  reg = <0x17d90000 0x4000 0x17d90100 0xa0>; qcom,shared-offset = <0x90>
```

CPU 到 domain 的映射（`qcom,freq-domain`，phandle 0x06）：

| CPU | domain | 说明 |
|---|---|---|
| 0–3 | 0 | 4 个 A510 小核 |
| 4–6 | 1 | 3 个 A710 大核 |
| 7 | 2 | 1 个 X3 超大核 |

板级 bootargs 带 `cpufreq.default_governor=performance`。

## 4. 与 SM8550 参考的对照

参考实现：`UniXNU-sheng` `origin/main` `package/CpuFreqProbe.cpp`（19,979 B，BSD-2-Clause-Patent）。

- 相同：三个 domain 窗口、`0x1000` 范围、LUT 偏移 `0x100`、4 字节行、`0x0` enable、
  `0x20` domain state、`0xb0` dcvs ctrl、`0x320` perf state、L3 `0x17d90000` + `0x90` 投票；
  LUT 行语义（bit31:30 source、18:16 core count，1=turbo、7:0 L；source 0 = GPLL0/2，
  其他 = 19.2 MHz × L）。
- 不同：参考的 CPU 数是 3/4/1（SM8550），K60 是 **4/3/1**。任何逐核 perf_state 行、
  quiet/boost 逻辑都必须按 K60 的核数改写，不能照抄。
- 参考的模式 1–4：只读、domain 0 请求、全 domain + L3 请求、governor。K60 这一步只做模式 1。

## 5. 已实现

| 提交 | 内容 |
|---|---|
| `1d7ea7fa` `feat(power): add a read-only EPSS probe` | `K60CpuFreqPlan.h/.c`、`K60CpuFreqProbe.cpp`、build 列表、battery start 钩子 |
| `e785355f` `test(power): cover the EPSS plan arithmetic` | `scripts/tests/test-k60-cpufreq-plan.c` |
| `64ae77fd` `feat(power): add the EPSS level vote write sets` | `k60_cpufreq_build_votes/build_l3_vote`、探针 mode 2/3 |
| `25ce9bdc` `test(power): cover the vote write sets` | 偏移/核数/L3/容量不足断言 |

`K60CpuFreqPlan`（纯 C，无 MMIO）：

- `k60_cpufreq_row_khz/row_cores/row_turbo`：解 LUT 行。
- `k60_cpufreq_build_table`：升序、去 turbo、按 cap 截断、遇到重复频率停止（硬件表尾两行相同）。
- `k60_cpufreq_pick_highest`：cap 以内最高档。
- `k60_cpufreq_target`：参考 governor 的单窗口决策（忙 90% 直接拉满；否则
  `当前频率 × busy × 1.25` 的最低档；帧下限 60%；共享簇 boost/quiet 地板）。
- `k60_cpufreq_step`：升档立即、降档连续 4 窗口才落地。
- `k60_cpufreq_domain_of_cpu/domain_cores`：K60 的 4/3/1 映射。
- `k60_cpufreq_build_votes`：把「一个档位」展开成参考的写集合——总是写 `perf_state 0x320`，
  dcvs 控制位为 1 且该 domain 多于 1 核时，再按 `0x320 + 4×i` 写每核一行（K60 为 4/3/1 核，
  不是参考的 3/4/1）；调用方缓冲区不足时返回 0 且一条都不写。
- `k60_cpufreq_build_l3_vote`：L3 共享投票，写 `0x90`，值同样是 LUT 行号。

`K60CpuFreqProbe`（默认关闭，boot arg `k60_cpufreq` 选模式）：

- mode 1（只读）：映射三个 domain 窗口与 L3，读 LUT/enable/state/dcvs/vote，
  **不写任何寄存器、不轮询**；每个 domain 打印 `base/enable/state(kHz)/dcvs/vote/rows/top/level`，
  L3 打印 `vote/rows/top/level`。
- mode 2：只给 domain 0 投最高非 turbo 档（参考的 mode 2 语义）。
- mode 3：三个 domain 都投最高非 turbo 档，再投 L3（参考的 mode 3 语义）。
- 大于 3 的值直接打印 "modes 1-3 are implemented" 并返回；mode 2/3 从未在真机上执行过。
- 调用点：`k60_physical_battery_start()` 开头。这是当前 archive 唯一由 userland 触发的
  IOKit 入口；探针不需要 ADSP 租约，也不经过电池配置解析。

## 6. 离线验证

- host 测试：`cc -Wall -Wextra -Werror -std=c11`，**TESTS OK 80 checks (0 failures)**。
  覆盖 LUT 解码、turbo 跳过、表尾去重、cap、highest、hispeed/frame/quiet/boost 地板、
  4 窗口降档、4/3/1 映射，以及投票写集合的偏移（`0x320`、`+4×i`、L3 `0x90`）、
  dcvs 开/关的写条数、缓冲区不足拒绝。LUT 行是合成的；真机表尚未读，因此断言的是算术而不是实测频率。
- archive：`build/k60-battery/libK60PhysicalBattery.a` **123,816 字节**，
  sha256 `c42a8f7b3d89a9d160ecfbfe733757897c7fc3a840048bf6f5aa66965a43a16c`；
  `llvm-nm` 可见 `_k60_cpufreq_probe`、`_k60_cpufreq_build_table`、`_k60_cpufreq_target`、
  `_k60_cpufreq_build_votes` 等 19 个 cpufreq 符号。
- 镜像 g 链接验证（**离线，未启动**）：`E:/k60-work/artifacts/power-conformance-20261118g/boot.img`
  201,887,744 字节，sha256 `7b0473aed1ce8c6ea6c0076bcce2b6e05070daa6a8994d9ff253625726e6b77c`；
  kernel.macho `8b75664005c86f2248510cbba85b5f118b04e3a79b91fb7068b686a5d7cf2aaa`，
  payload `39ea4cc5f3724774d6d6d6b57bca18e2eacef49c6a937a4b217f12839b77b4e9`。
  `verify-boot-img-payload.py` OK：payload @ 557056、201,326,592 字节；payload 内 kernel 为
  probe-patched `9aa990d1519fe091…`，payload.json 记录的是 pre-patch `8b756640…`；
  FD `cf4485712c29…`。`check-image-args.py` OK（30 个参数，598 字节）。
  payload 字符串里 `K60CpuFreq: d`/`K60CpuFreq: L3` 各 2 次、`K60CpuFreq: mode=` 1 次，
  kernel.macho 符号表含 `_k60_cpufreq_probe/build_table/pick_highest/target/step/domain_*`；
  `boot.json` 的 `hardware_tested` 为 `false`，即没有任何真机读数。
- 镜像 h 链接验证（**离线，未启动**，含 mode 2/3 投票代码）：`E:/k60-work/artifacts/power-conformance-20261118h/boot.img`
  201,887,744 字节，sha256 `7ef07b95ff0977a113b665e13bdbc38e50c74efa1ec86b7515f106d853cb7eba`；
  kernel.macho `f63db805b421d80066dda7c766c6f1cd7023e41b9e449471f1eb940a14a3b102`，
  payload `8d4e0969390f5dedc4c78996cec0306e5a59fb091109fbb3f935fccf8ea87966`。
  `verify-boot-img-payload.py` OK（payload 内 kernel probe-patched `93c2da73dd3a7db1…`，
  pre-patch `f63db805…`，FD `cf4485712c29…`）；`check-image-args.py` OK（30 个参数，598 字节）。
  payload 字符串含 `K60CpuFreq: mode%u vote d`、`K60CpuFreq: L3 vote skipped`，
  kernel.macho 有 14 条 `k60_cpufreq` 符号；`boot.json` 仍为 `hardware_tested=false`。

## 7. 未实现 / 边界

- 投票写集合已实现（mode 2/3），但**从未在真机上执行**：没有 enable 等待、没有写后读回校验、
  没有 dcvs 反馈；mode 1 是唯一有离线证据的模式。
- 没有 governor 线程、没有 idle 时间统计（参考用内核 `sheng_cpu_idle_mach`）、
  没有触摸/帧信号输入、没有 10 s 统计窗口。
- 没有平台睡眠（`ShengSleep.cpp` 等价物）、没有 GPU 频率（`GpuPowerProbe.cpp` 149 KB）、
  没有外设供电投票归属/引用计数。
- 没有任何真机 EPSS 读数；三个 domain 的 enable/state/LUT 仍未知。

## 8. 设备空窗时的上机步骤（当前暂缓）

1. 先用 mode 1（`k60_cpufreq=1`）确认表可读，再考虑 mode 2/3；当前候选 image h（sha256 `7ef07b95…`）。
2. 抓 `K60CpuFreq:` 开头的行：
   - `mode=1 EPSS domains=3 cpus=8 lut-rows=40`
   - `d0 base=0x17d91000 enable=… state=… (…kHz) dcvs=… vote=… rows=… top=…kHz level=… mode1=read-only`
   - `L3 base=0x17d90000 vote=… rows=… top=…kHz level=…`
   - mode 2/3 的行形如 `mode2 vote d0 level=… (…kHz) dcvs=… writes=…`、`mode3 vote L3 …`
3. 判读：`enable=1` 且 `rows` 在 10–40 之间、频率随 domain 递增，才说明表可读；
   `nomap` 或 `rows=0` 则先查窗口/时钟，不得进入 mode 2/3。mode 2/3 第一次上机只投最高档，
   并同时抓 `state` 是否跟随、温度与是否触发 throttle。

## 9. 参考

- 官网：`E:/k60-work/scratch/power-page-20261117.txt:105-121`
- 现场 DTB：`E:/k60-work/reports/live-6033dbec-fdt.dtb`
- 参考实现：`UniXNU-sheng` `origin/main` `package/CpuFreqProbe.cpp`
- 已有总表：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md`（§4 电池；§5 另行跟踪）
