# K60 EPSS 只读探针（power §5 起点）

日期：2026-11-18。范围：官网 power 页 §5 的第一条，CPU 频率（EPSS）。
本文记录寄存器事实、纯算术模块、默认关闭的只读探针、host 断言，以及 2026-11-18 三次真机
mode 1 读数：17:30 image i 的早期快照、17:55 image j 在电池 `begin` 后的第二次快照
（后者把 d1/d2 从“辅核未启动”的 0 变为 `enable=1`），和 18:22 image k 的逐行 LUT dump
（66 条有效档位全部读出）。设备测试只做到只读快照；投票写入路径已加守卫但尚未在真机执行。

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
- 参考的模式 1–4：只读、domain 0 请求、全 domain + L3 请求、governor。K60 已实现模式 1–3
  （2/3 为带守卫的瞬态写入，未上机），governor 只有纯逻辑核心。

## 5. 已实现

| 提交 | 内容 |
|---|---|
| `1d7ea7fa` `feat(power): add a read-only EPSS probe` | `K60CpuFreqPlan.h/.c`、`K60CpuFreqProbe.cpp`、build 列表、battery start 钩子 |
| `e785355f` `test(power): cover the EPSS plan arithmetic` | `scripts/tests/test-k60-cpufreq-plan.c` |
| `64ae77fd` `feat(power): add the EPSS level vote write sets` | `k60_cpufreq_build_votes/build_l3_vote`、探针 mode 2/3 |
| `25ce9bdc` `test(power): cover the vote write sets` | 偏移/核数/L3/容量不足断言 |
| `c39bf8ec` `feat(power): add the EPSS governor window core` | `K60CpuFreqGovernor` 状态与单窗口决策 |
| `4a510725` `test(power): drive the governor window sequence` | 降档闩锁/立即升档/boost 释放/错误入参 |
| `950742e9` `feat(power): add a late EPSS read after battery start` | 电池 `begin` 成功后 5 s 再读一次（仍只读、仍受 `k60_cpufreq=1` 限制） |
| `eba8de2a` `feat(power): dump the EPSS look-up table rows` | mode 1 早期读取逐行打印 raw/kHz/cores/turbo；延后读取只保留摘要，避免重复 51 行 |
| `42ca4421` `feat(power): guard and undo EPSS votes` | enable/表项守卫、写后回读、恢复写前原值；mode 2/3 改为瞬态验证写 |
| `70dd3794` `test(power): cover the EPSS vote guard` | host 覆盖守卫/回读/恢复，128 项 |

`K60CpuFreqPlan`（纯 C，无 MMIO）：

- `k60_cpufreq_row_khz/row_cores/row_turbo`：解 LUT 行。
- `k60_cpufreq_build_table`：升序、去 turbo、按 cap 截断、遇到重复频率停止（硬件表尾两行相同）。
- `k60_cpufreq_pick_highest`：cap 以内最高档。
- `k60_cpufreq_target`：参考 governor 的单窗口决策（忙 90% 直接拉满；否则
  `当前频率 × busy × 1.25` 的最低档；帧下限 60%；共享簇 boost/quiet 地板）。
- `k60_cpufreq_step`：升档立即、降档连续 4 窗口才落地。
- `k60_cpufreq_domain_of_cpu/domain_cores`：K60 的 4/3/1 映射。
- `k60_cpufreq_busy_permille/domain_busy`：参考的调度器空闲换算——每 CPU
  `(elapsed - idle) * 1000 / elapsed`，域内取最忙的 CPU（不是平均）；空闲计数
  超过窗口按 0 忙处理，结果上限 1000。
- `k60_cpufreq_build_votes`：把「一个档位」展开成参考的写集合——总是写 `perf_state 0x320`，
  dcvs 控制位为 1 且该 domain 多于 1 核时，再按 `0x320 + 4×i` 写每核一行（K60 为 4/3/1 核，
  不是参考的 3/4/1）；调用方缓冲区不足时返回 0 且一条都不写。
- `k60_cpufreq_build_l3_vote`：L3 共享投票，写 `0x90`，值同样是 LUT 行号。
- `k60_cpufreq_vote_allowed`：拒绝 enable=0、表为空、档位不在表内、写条数超限；`k60_cpufreq_check_readback`
  逐条比较回读值；`k60_cpufreq_build_restore` 用写前保存的原值生成恢复写集合。
- `k60_cpufreq_governor_reset/governor_window`：参考 16 ms 循环的纯逻辑版——每个 domain 保存
  当前档、降档计数、quiet 计数；忙 90% 立即升，降档连续 4 窗口才落地；boost 结束后的
  共享簇按半速地板保持 12 个 quiet 窗口。**没有线程调用它**，寄存器仍由探针负责。

`K60CpuFreqProbe`（默认关闭，boot arg `k60_cpufreq` 选模式）：

- mode 1（只读）：映射三个 domain 窗口与 L3，读 LUT/enable/state/dcvs/vote，
  **不写任何寄存器、不轮询**；每个 domain 打印 `base/enable/state(kHz)/dcvs/vote/rows/top/level`，
  L3 打印 `vote/rows/top/level`。早期读取随后按解析顺序逐行打印
  `row=<i> raw=0x<...> khz=<...> cores=<...> turbo=<...>`（L3 前缀 `L3 row=`），
  每域最多 `table.count` 行；电池 `begin` 成功后 5 s，`k60_cpufreq_probe_late()`
  再做一次只读摘要读取（日志 `late read begin/end`），让 d1/d2 在辅核启动后可见；
  延后读取不重复逐行 dump。它不是轮询，也不写寄存器。
- mode 2：只给 domain 0 投最高非 turbo 档（参考的 mode 2 语义）。
- mode 3：三个 domain 都投最高非 turbo 档，再投 L3（参考的 mode 3 语义）。
- mode 2/3 的写入是**瞬态验证写**：写前检查 enable 与档位，保存每个目标寄存器的原值，写后逐条回读，
  再立即写回原值；日志带 `readback=ok|mismatch restored=<n>`。因此它验证写路径，不会留下持续投票；
  仍未在真机上执行过。enable=0 的域（例如辅核启动前的 d1/d2）会直接拒绝写入。
- 大于 3 的值直接打印 "modes 1-3 are implemented" 并返回。
- 调用点：`k60_physical_battery_start()` 开头做第一次读取；电池 `begin` 成功后
  （`K60Battery.cpp` 的同一入口）延迟 5 s 做第二次读取。这是当前 archive 唯一由
  userland 触发的 IOKit 入口；探针不需要 ADSP 租约，也不经过电池配置解析。

## 6. 构建与验证

- host 测试：`cc -Wall -Wextra -Werror -std=c11`，**TESTS OK 128 checks (0 failures)**。
  覆盖 LUT 解码、turbo 跳过、表尾去重、cap、highest、hispeed/frame/quiet/boost 地板、
  4 窗口降档、4/3/1 映射，以及投票写集合的偏移（`0x320`、`+4×i`、L3 `0x90`）、
  dcvs 开/关的写条数、缓冲区不足拒绝、enable/档位守卫、写后回读、恢复原值，以及 governor
  的单窗口序列（降档闩锁、立即升档、boost 释放后的半速地板、错误入参），以及空闲换算
  （满忙/半忙/全闲/超计/零窗口）和 4/3/1 域的“最忙 CPU”选择。断言使用合成的 LUT 行；
  真机 image k 已把 66 条有效档位逐行读出。
- archive（含逐行 dump 与写入守卫，commit `42ca4421`）：`build/k60-battery/libK60PhysicalBattery.a`
  **127,688 字节**，sha256 `77841710f182eb9cc1de5cca580c74c21203c9a30568f02dc6b9c0e68843180b`；
  `llvm-nm` 可见 `_k60_cpufreq_probe`、`_k60_cpufreq_probe_late`（0x65c）、
  `_k60_cpufreq_build_table`、`_k60_cpufreq_target`、`_k60_cpufreq_build_votes`、
  `_k60_cpufreq_vote_allowed/check_readback/build_restore`、
  `_k60_cpufreq_governor_window`、`_k60_cpufreq_domain_busy` 等 cpufreq 符号。本轮只重建
  archive，没有构建新镜像；image k 内仍是 `1cb58397…` 的旧 archive。
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
  注意 image h 内打包的是当时的 archive `c42a8f7b…`；governor 核心之后的 archive
  `7a19051a…` 还没有打包进任何镜像。
- 镜像 i 链接验证（**离线构建**，带 `k60_cpufreq=1`；随后于 17:30 首次上机，见下一条）：`E:/k60-work/artifacts/power-conformance-20261118i/boot.img`
  201,887,744 字节，sha256 `f2d91f1358f23d121d524c624eeafa8b03ff93b374eb3ae2515967f13b76d472`；
  kernel.macho `e39a45cba7ea6f3b96c5f2b85d639bff8ccb1fa33ff3d64aed4670bf6859efaf`，
  payload `d35816c3a500b83cf02e981aa5f93b8ccb76fcb6d933a0409b18132ad089a36e`。
  `verify-boot-img-payload.py`（carrier FD `cf4485712c29…`）OK：payload @ 557056、
  201,326,592 字节；payload 内 kernel probe-patched `ad6c3a58442bcb45…`，payload.json
  记录 pre-patch `e39a45cb…`；ADT `919565bf30140e35…`。payload 字符串含
  `K60CpuFreq: mode%u EPSS domains=%u cpus=%u lut-rows=%u` 及 mode 1/2/3 的全部行。
  **参数 gate 未通过**：镜像 30 个参数、603 字节；为容纳 `k60_cpufreq=1`，构建时临时从
  `k60-adsp-handoff/board.toml` 去掉了 `applog=1`，因此 `check-image-args.py` 报
  `k60_cpufreq` 不在 `ALLOWED_ADDITIONS`、且 board 的 `applog=1` 缺失。上机结束后必须
  恢复 board.toml 的 `applog=1`；该镜像只用于一次 EPSS 探针读取，不作为发布镜像。
  构建产物 `boot.json` 的 `hardware_tested` 为 `false`（构建时标记；本次已实际启动）。
- 镜像 j 链接验证（**离线构建**，含第二次只读读取；2026-11-18 17:52）：
  `E:/k60-work/artifacts/power-conformance-20261118j/boot.img` 201,887,744 字节，
  sha256 `ff5fd1780d03dbb906dc44d96c43560bd04ee3984c522ed13e4b7b5abed86401`；
  kernel.macho `0a53cc36422fd0b37b42d13240ced6780b3d7c6fdf0b2a0dbb9d8f396e16faba`，
  payload `8fd783ccdd8450053c53181db70429763c0c07554b9ea053becec583318114ba`。
  `verify-boot-img-payload.py`（carrier FD `cf4485712c29…`）OK：payload @ 557056、
  201,326,592 字节；payload 内 kernel probe-patched `21557f56a4cafda2…`，payload.json
  记录 pre-patch `0a53cc36…`；ADT `069a8e1b54aa0377…`。payload 字符串含
  `K60CpuFreq: late read` 2 次、`K60CpuFreq: mode=` 2 次。内核参数仍为 30 个、603 字节；
  `check-image-args.py` 与 image i 一样 REFUSED（`k60_cpufreq` 不在 `ALLOWED_ADDITIONS`、
  board 的 `applog=1` 缺失）。构建期间再次临时去掉 `applog=1`，构建结束后已恢复。
- 镜像 j 首次上机（**只读 mode 1，含第二次读取**，2026-11-18 17:55:18–18:00:49，
  `E:/k60-work/evidence/power-conformance/epss-late-20261118-1755`）：`boot.json`
  `bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`；`capture.json`
  `complete=true`、`bytes=134249`、`stopReason=budget`、`reopenCount=0`、`openErrors=4`
  （COM5 早期重开口志，最终完整），console.log 134,249 字节，sha256
  `0651ccccc1a36f9ed16717da6256886313bc05f0af31a381cba2bef1007cb4e7`；日志末尾为
  `K60AUTORESET: 300 s since boot; resetting to fastboot`。早期探针在 `:189–:193`
  与 image i 相同；`ArmCpu` CPU 1–7 在 `:201–:207` 全部 PSCI start PASS；电池首帧
  `:238` 之后，第二次读取在 `:239–:244`：

  ```
  K60CpuFreq: late read begin (mode 1)
  K60CpuFreq: d0 base=0x17d91000 enable=1 state=81 (1555200kHz) dcvs=0 vote=11 rows=14 top=1804800kHz level=13 mode1=read-only
  K60CpuFreq: d1 base=0x17d92000 enable=1 state=33 (633600kHz) dcvs=0 vote=16 rows=17 top=2496000kHz level=16 mode1=read-only
  K60CpuFreq: d2 base=0x17d93000 enable=1 state=41 (787200kHz) dcvs=0 vote=19 rows=20 top=2995200kHz level=19 mode1=read-only
  K60CpuFreq: L3 base=0x17d90000 vote=13 rows=15 top=1708800kHz level=14
  K60CpuFreq: late read end
  ```

  判读：d1/d2 的早期 0 确为时序，不是域不可用；延后读取三个 domain 全部
  `enable=1`。d1/d2 的 `state` 33/41 即 633,600/787,200 kHz（读时负载低），
  `vote` 16/19 是各自最高档；d0 与 L3 不变。本轮仍无写入，mode 2/3 未执行。
- 镜像 i 首次上机（**只读 mode 1**，2026-11-18 17:30:19–17:35:43，
  `E:/k60-work/evidence/power-conformance/epss-probe-20261118-1730`）：`boot.json`
  `bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`；`capture.json`
  `complete=true`、`bytes=136714`、`stopReason=budget`、`reopenCount=0`，控制台
  `console.log` 136,714 字节，sha256 `a40ab2cfdeb9bbf4403bf157cc98585a10e2bdb92f7b64e42d637cc918578c60`；
  日志末尾有 `K60AUTORESET: 300 s since boot; resetting to fastboot`。探针行在
  `:189–:193`：

  ```
  K60CpuFreq: mode=1 EPSS domains=3 cpus=8 lut-rows=40
  K60CpuFreq: d0 base=0x17d91000 enable=1 state=81 (1555200kHz) dcvs=0 vote=11 rows=14 top=1804800kHz level=13 mode1=read-only
  K60CpuFreq: d1 base=0x17d92000 enable=0 state=0 (0kHz) dcvs=0 vote=0 rows=17 top=2496000kHz level=16 mode1=read-only
  K60CpuFreq: d2 base=0x17d93000 enable=0 state=0 (0kHz) dcvs=0 vote=0 rows=20 top=2995200kHz level=19 mode1=read-only
  K60CpuFreq: L3 base=0x17d90000 vote=13 rows=15 top=1708800kHz level=14
  ```

  判读：探针在 `k60_physical_battery_start()` 开头、辅核启动之前执行；控制台
  `:203–:209` 才依次启动 CPU 1–7。因此 d1/d2 的 `enable=0/state=0` 是读取时刻
  大核簇尚未上电的状态，不能据此判断 EPSS 域不可用。d0 的 `state=81`（81 × 19.2 MHz =
  1,555,200 kHz）与 `vote=11`、L3 `vote=13` 是第一批真机 EPSS 读数；d0/d1/d2 的
  `rows` 14/17/20 与 `top` 1,804,800/2,496,000/2,995,200 kHz 正好对应 K60 的 4/3/1 核
  SM8475 频率上限。本轮没有写任何寄存器，mode 2/3 未执行。
- 镜像 k 链接验证（**离线构建**，含逐行 LUT dump；2026-11-18 18:18）：
  `E:/k60-work/artifacts/power-conformance-20261118k/boot.img` 201,887,744 字节，
  sha256 `74e66779201fa61bd9038ddd3ae3e8f89a52de82576d43839a05779b27612f0b`；
  kernel.macho `6399b94e5f2cb81527917c5f2acbf6eb4993b93a943d82f958ca6567eaa19b10`，
  payload `89bfbb30ff57f1513484491d067c70fd7851d564a40f4b16d774d70ff6f381d3`。
  `verify-boot-img-payload.py`（carrier FD `cf4485712c29…`）OK：payload @ 557056、
  201,326,592 字节；payload 内 kernel probe-patched `3e124cb383572e91…`，payload.json
  记录 pre-patch `6399b94e…`；ADT `53ff51130bc81504…`，DTB `2d044eaa08b7e58c…`。
  payload 字符串含 `K60CpuFreq: %srow=%u raw=0x%08x khz=%u cores=%u turbo=%u` 1 次、
  `late read begin/end` 各 1 次。首次整镜像构建在 payload 步骤被拒：
  `kernel command line is 612 bytes; DarwinBoot accepts at most 607`，原因是
  `applog=1` 已恢复；随后临时去掉 `applog=1` 只重跑 payload/bootimg，参数为 30 个、603 字节，
  gate 仍因 `k60_cpufreq` 不在 `ALLOWED_ADDITIONS` 且 board 的 `applog=1` 缺失而 REFUSED；
  构建结束后 `applog=1` 已恢复。`boot.json` 的 `hardware_tested` 在构建时为 `false`；2026-11-18 18:22 已首次上机，逐行结果见下节。
- 镜像 k 首次上机（**只读 mode 1 + 逐行 dump**，2026-11-18 18:22）：证据目录
  `E:/k60-work/evidence/power-conformance/epss-lut-20261118-1822`；`boot.json` 的
  `bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`（18:22:22–18:27:54）；
  `capture.json` 为 `captured-budget-complete`、`complete=true`、133,807 B、
  `logSha256=15143B46F4CE069767EF752F5C4E2BDFB256AED8E311DE8876A61C2E5D9BD5CE`、
  `openErrors=5`（最后一次是 COM5 不存在）、`reopenCount=0`、`stopReason=budget`；
  `console.log` 133,807 B、同 SHA-256，早期 LUT 行在 `:189–:259`，延后读取在 `:304–:310`，
  未见 panic marker，300 s 后打印 `K60AUTORESET` 和 restart reason；采集脚本未在窗口内判定回到 fastboot，
  采集结束后通过 `k60-device.sh state` 独立确认 `fastboot`。

### 逐行 LUT（image k，2026-11-18 18:22）

早期只读 pass 在 `:191–:259` 打印了 66 条有效档位记录（d0 14、d1 17、d2 20、L3 15），
并非每窗 40 个物理槽的全量转储。四表的输出均为升序，最高档与表头摘要一致。每条记录的
`cores` 都是 4、`turbo` 都是 0，因此不能把 18:16 位当作本域核数；CPU 域归属仍使用 FDT 的
4/3/1 映射。`row` 是硬件 LUT 行号，也是这些条目保存在 `table.level` 中的值，而非排序后下标。

| row | d0 raw / kHz | d1 raw / kHz | d2 raw / kHz | L3 raw / kHz |
|---|---|---|---|---|
| 0 | 0x0004000f / 300000 | 0x40040021 / 633600 | 0x40040029 / 787200 | 0x0004000f / 300000 |
| 1 | 0x40040017 / 441600 | 0x40040028 / 768000 | 0x40040030 / 921600 | 0x40040015 / 403200 |
| 2 | 0x4004001d / 556800 | 0x4004002e / 883200 | 0x40040036 / 1036800 | 0x4004001b / 518400 |
| 3 | 0x40040024 / 691200 | 0x40040034 / 998400 | 0x4004003d / 1171200 | 0x40040020 / 614400 |
| 4 | 0x4004002a / 806400 | 0x4004003a / 1113600 | 0x40040043 / 1286400 | 0x40040025 / 710400 |
| 5 | 0x40040031 / 940800 | 0x4004003f / 1209600 | 0x40040049 / 1401600 | 0x4004002a / 806400 |
| 6 | 0x40040037 / 1056000 | 0x40040045 / 1324800 | 0x40040050 / 1536000 | 0x4004002f / 902400 |
| 7 | 0x4004003b / 1132800 | 0x4004004b / 1440000 | 0x40040056 / 1651200 | 0x40040034 / 998400 |
| 8 | 0x40040040 / 1228800 | 0x40040051 / 1555200 | 0x4004005c / 1766400 | 0x40040038 / 1075200 |
| 9 | 0x40040045 / 1324800 | 0x40040056 / 1651200 | 0x40040062 / 1881600 | 0x4004003d / 1171200 |
| 10 | 0x4004004b / 1440000 | 0x4004005c / 1766400 | 0x40040068 / 1996800 | 0x40040042 / 1267200 |
| 11 | 0x40040051 / 1555200 | 0x40040062 / 1881600 | 0x4004006f / 2131200 | 0x40040048 / 1382400 |
| 12 | 0x40040057 / 1670400 | 0x40040068 / 1996800 | 0x40040075 / 2246400 | 0x4004004d / 1478400 |
| 13 | 0x4004005e / 1804800 | 0x4004006e / 2112000 | 0x4004007b / 2361600 | 0x40040053 / 1593600 |
| 14 | — | 0x40040074 / 2227200 | 0x40040081 / 2476800 | 0x40040059 / 1708800 |
| 15 | — | 0x4004007a / 2342400 | 0x40040087 / 2592000 | — |
| 16 | — | 0x40040082 / 2496000 | 0x4004008d / 2707200 | — |
| 17 | — | — | 0x40040093 / 2822400 | — |
| 18 | — | — | 0x40040098 / 2918400 | — |
| 19 | — | — | 0x4004009c / 2995200 | — |

判读：d0 的 14 档 0.3–1.8048 GHz、d1 的 17 档 0.6336–2.496 GHz、d2 的 20 档 0.7872–2.9952 GHz、
L3 的 15 档 0.3–1.7088 GHz 与 `rows/top/level` 摘要一致；早期 d1/d2 的 `enable=0` 仍只是辅核尚未启动，
延后读取 `:304–:310` 已变为 `enable=1`。本轮仍无写入，mode 2/3 未执行。

## 7. 未实现 / 边界

- 投票写集合已实现（mode 2/3），并已在代码层加入 enable/档位守卫、写后回读和恢复原值
  （commit `42ca4421`），但**从未在真机上执行**；没有 enable 等待、没有 dcvs 反馈，
  也没有验证恢复后的寄存器值。mode 1 已完成早读、延后读取和有效 LUT 行转储，延后读取的
  三个 domain 均 `enable=1`。记录中的 `vote` 是只读到的原寄存器值，并非探针写入。
- governor 只有纯逻辑核心，没有线程；idle 换算已经纯逻辑化（`k60_cpufreq_domain_busy`），
  但还没有内核 `sheng_cpu_idle_mach` 等价的采样调用、
  没有触摸/帧信号输入、没有 10 s 统计窗口；核心还没有被任何代码调用。
- 没有平台睡眠（`ShengSleep.cpp` 等价物）、没有 GPU 的 GMU 读取/HFI 投票（`GpuPowerProbe.cpp` 149 KB；现有纯逻辑规划 `docs/research/power/04-GPU-FREQUENCY.md`）、
  外设供电投票只有纯记账模块（`K60PowerVotePlan`），没有真实消费者或轨道名。
- 真机已有三次 mode 1 读数：d0 早期即启用；d1/d2 在辅核启动前读为 0，image j 延后读取
  已变为 `enable=1`（state 633.6/787.2 MHz、vote 16/19），所以三域均可读，早期 0 只是时序。
  image k 已把 66 条有效 LUT 档位全部读出（d0/d1/d2/L3 = 14/17/20/15 行，见 §6 表）；仍没有负载下
  频率、温度或 throttle 读数；写后回读与恢复只在 host 算术中验证，真机尚未执行写入。

## 8. 后续上机步骤

1. image i 已完成早期 mode 1 只读读取（sha256 `f2d91f13…`）；image j 在电池 `begin`
   成功后 5 s 完成第二次读取（sha256 `ff5fd178…`，commit `950742e9`），三个 domain 均
   `enable=1`；image k（sha256 `74e66779…`，commit `eba8de2a`）在 18:22 走同一条只读路径，
   并把 66 条有效 LUT 档位全部打印。三个镜像都带 `k60_cpufreq=1`，构建时临时去掉 `applog=1`，
   只用于探针，参数 gate 仍未通过（`k60_cpufreq` 未加入 `ALLOWED_ADDITIONS`）。
   `k60-adsp-handoff/board.toml` 的 `applog=1` 已恢复。
2. d1/d2 的“辅核启动后补读”已经完成：image j 的 `late read` 在 `ArmCpu` CPU 1–7 全部
   PSCI start PASS、电池首帧发布之后执行，d1 `enable=1 state=33 (633600kHz) vote=16`、
   d2 `enable=1 state=41 (787200kHz) vote=19`。不需要再移动调用点，也不要在早期快照上
   判定大核簇失败。
3. 抓 `K60CpuFreq:` 开头的行：
   - `mode=1 EPSS domains=3 cpus=8 lut-rows=40`
   - `d0 base=0x17d91000 enable=… state=… (…kHz) dcvs=… vote=… rows=… top=…kHz level=… mode1=read-only`
   - `late read begin/end` 与第二次的 d0/d1/d2/L3 行
   - CPU 各域的行跟在对应摘要后，形如 `K60CpuFreq: row=0 raw=0x0004000f khz=300000 cores=4 turbo=0`；L3 行另带 `L3 ` 前缀。
   - mode 2/3 的行形如 `mode2 vote d0 level=… (…kHz) dcvs=… writes=… readback=… restored=…`、
     `mode3 vote L3 …`
4. 设备空窗：image k 于 2026-11-18 18:22:22 启动、18:27:54 结束；之后仍先跑
   `list-boot-watchers.ps1` 和 `k60-device.sh state`，不要与任何 `boot-and-capture`
   抢 fastboot；启动时 `audio-probe-at` watcher（PID 11116）的镜像尚不存在，只轮询。
5. 首次写入前：参数门禁须通过。启用状态守卫、写后回读和恢复原投票的路径已在代码中补齐
  （commit `42ca4421`/`70dd3794`，host 128 项），但仍不能仅凭 LUT 可读就执行早期 mode 2/3
  写入（d1/d2 在辅核启动前 `enable=0`）。首次验证应限定在 d0 单域，分别记录请求档位、
  寄存器回读、恢复值和负载下的 `state`，并观察温度与 throttle；d1/d2/L3 多域投票和 governor
  不与首测合并。`nomap`、`enable=0` 或无有效 LUT 时应拒绝写入。

## 9. 参考

- 官网：`E:/k60-work/scratch/power-page-20261117.txt:105-121`
- 现场 DTB：`E:/k60-work/reports/live-6033dbec-fdt.dtb`
- 参考实现：`UniXNU-sheng` `origin/main` `package/CpuFreqProbe.cpp`
- 已有总表：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md`（§4 电池；§5 另行跟踪）
