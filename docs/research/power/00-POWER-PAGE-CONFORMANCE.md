# 官网 power 页逐节对照（§1–§6）

本文件是 `https://unixnu.com/zh/porting/power` 的**整页**状态表。快照
`E:/k60-work/scratch/power-page-20261117.txt` 共六节：§1 目标接口 :8-15、
§2 DSP 传输 :16-27、§3 音频流 :28-67、§4 电池 :68-104、§5 调频与电源操作 :105-121、
§6 构建并验证 :123-131。`docs/research/charger/10-POWER-DOC-CONFORMANCE.md`
只覆盖 §4 的电池测量；§2/§3 由音频分支负责，本分支不重复实现。

状态用语：**已验证**＝真机证据；**部分**＝有代码但缺设备证据或只覆盖一部分；
**委派**＝另一条工作流负责；**未实现**＝本树没有对应代码。

## §1 目标接口（:8-15）

| 输入 | 本分支状态 | 证据与缺口 |
| --- | --- | --- |
| DSP 固件/PAS ID、预留内存、邮箱、共享内存、时钟电源归属 | 已验证（传输链）/部分（整节） | Route A ADSP 启动在 image e/f 上 `rc=0`，PAS1 `epoch=1 flags=15`；`docs/research/charger/02-GLINK-CONTRACT.md`、`docs/plans/OFFICIAL-DRIVER-MAP.md:44`。2026-11-20 起这条链有上机判读器：`scripts/judge-k60-handoff-console.py` 按 publish(epoch/104 B/flags=15) → 同 epoch adopt(非零 tx/rx) → 真实通道 up → 样本 的顺序判定，`audio-probe-ax/run1-20261119-0100` 与 `audio-probe-aw/run1-20261118-2245` 两份真机 console 都 PASS（33 项用例，见 `battery/PMIC-GLINK-SERVICE.md` §9）；载体分支把 PAS 载荷改到板级 carveout `0x9fd00000`，整节仍未覆盖音频端点与时钟归属 |
| 音频 codec/功放、总线、时钟、路由、拓扑、格式、OS ABI | 委派 | 音频分支 `feat/audio-adsp-merge`（2026-11-18 时 HEAD `c74aea80`，145 commits ahead，未合并） |
| 电池电量计/固件协议、属性 ID、单位、电流符号、通知 | 已验证（测量）/部分（全节） | `K60Battmgr.c`、`K60Battery.cpp`；`charger/04-PROP-MAP.md`；19 个 wire 属性号已机器可读（`charger/WIRE-PROPS.toml` + `check-battmgr-wire.py`，三份材料互校，12 项夹具）；属性 9 静默、USB 输入电流边界见 §4 |
| 电源时钟域、OPP 表、稳压器、固件投票、温控限制 | 部分（离线） | EPSS/GPU OPP 表现场 FDT 已确认；只有路线 A 的 TCS4 lcx/lmx 两条真实投票，CPU/GPU 电压仍无写路径，见 `power/07-RAIL-ORDERING.md`。温控限制自 2026-11-20 有离线契约 `K60ThermalMap`（9 个 AP 侧 zone、90/95/110/115/125 °C 阶梯、`allow_raise` 直接喂 `k60_rail_plan` 的 `thermal_ok`，host 125 项，见 `power/10-THERMAL-MAP.md`）：它可以**拒绝**升压，但既不读传感器也不写寄存器——真机温度证据目前不可用（`power-conformance-thermal-20261119-0436` 的 capture 是 `port-not-observed`，0 字节 console） |
| 固件清单记录来源和版本 | 部分 | `power/06-FIRMWARE-MANIFEST.md` 记录 ADSP 26 段/充电器 .ko/carrier FD 的哈希与来源；整机其他固件与认证密钥未覆盖 |

## §2 DSP 传输（:16-27）

- 本树有 GLINK/SMEM/邮箱与 Route A 启动代码（`K60Adsp*`、`QcomGlink.c`），
  电池通道的登录/订阅/单请求/超时/断链 stale 已在 image e/f 上验证。
- 官方列出的通道注册 API（`sheng_adsp_channel`）、560 字节上限、回调复制到有界队列、
  断链取消与重连协商属于**音频分支**的实现范围；本分支只消费电池通道。
- 电池通道这一半现在可机器判读：`scripts/judge-k60-handoff-console.py` 把 `published authenticated PAS1 epoch=E bytes=104 flags=15`、
  同 epoch 的 `adopting`（tx/rx 非零）、`actual PMIC_RTR_ADSP_APPS channel up` 与至少一条 `sample=` 串成一条链，
  缺任何一环就指出第一个断点（只"发布成功"而没被 adopt 的 console 会被判成"通道不可用"，
  这正是 `battery/HANDOFF-PUBLISH-SPEC.md` §0 第 5 条要求的区分）。两份真机 console PASS，33 项用例。
- 其余（通道注册 API、560 字节上限、回调复制到有界队列、断链取消与重连协商）仍属**音频分支**范围，
  本分支只消费电池通道。
- 状态：**部分**（电池通道已验证并有了判读器，音频侧委派）。

## §3 音频流（:28-67）

- 本树没有音频端点/流引擎/OS 音频 ABI；`drivers/PongPower` 只有电池与 ADSP 启动路径。
- 状态：**委派（音频分支）**，本文件不评估。

## §4 电池（:68-104）

详细逐条表在 `charger/10-POWER-DOC-CONFORMANCE.md` §7.2。摘要：

| 条目 | 状态 |
| --- | --- |
| 协议 owner/type/opcode/property/length、单请求、超时 | 已验证（host 95 项 + image e/f 日志） |
| 有效/缺失/失败三态、原始值→OS 换算、register/updateStatus、adapter | 已验证（host）；缺失包未在真机复现 |
| 订阅、周期刷新、断链 stale | 已验证（image f 12-14 条样本） |
| 与 Android/OEM 对照（C3） | 部分：只有低电流 3 对 PASS；匹配电流窗口因属性 9 静默、XNU 只能发 USB 输入电流而 FAIL |
| 真机插拔、放电、超时、服务重启 | 未完成（host 第 15/16 节只模拟状态转换） |
| 充电认证 PD/PPS/MiPPS（:82-88） | 部分（仅移植，默认关闭）：sheng 的 `ShengChargeAuth.c` 已移植为 `K60ChargeAuth.c`（host 状态机 99 项 + HMAC-SHA256 5 项 RFC 4231 向量，已并入 `run-k60-power-host.sh` 的 1915 项 / 10 套件并作为 `CARRY.toml` 第八个模块随 27 线搬运），并默认关闭地接入 `K60Battery` 串行队列，只有 property 7 值 6/7/8 的 fresh sample 启动；`k60_charge_auth=1`（18 B）在 596 B 基线下会到 614 B 超过 607，本分支因此未启用该参数；无 UCSI 数据角色、未上机，K60 固件侧的认证字段与密钥没有来源 |
| Linux 充电读取镜像（:89-104） | 对读已接入（读取器本体不实现）：`scripts/judge-k60-battery-mirror.py` 把我们的 sample 行与 sheng 的镜像报告按同一基准单位比对（容量/电压/电流幅值/温度/外接/充电状态，容差 60 mV、150 mA、3.00 pp、3 °C），差值为 10/100/1000 倍时点名单位滑档；21 项 fixture，随 power runner 的 `battery-mirror` 套件运行并作为第四个判读器进入 `CARRY.toml`（4 judges / 96 cases）。**镜像读取器不做**：K60 上没有 Linux，`/sys/class/power_supply` 永远不存在，这一半的输入只能来自别人在同一 SoC 上跑的 Linux（sheng 仓库），本线不产出、也不假装能产出；结果是「读的那半接上了，采样/写的那半依赖外部 Linux 报告」。判读器输出末行 `SIDES ours=… sheng=…` 标明哪一侧缺失或自相矛盾，两侧不平权 |

## §5 调频与电源操作（:105-121）

| 条目（行号） | 状态 | 证据/缺口 |
| --- | --- | --- |
| CPU：16 ms 读空闲、1.25 倍余量、4 窗口降频（:113） | 部分（d0 双向写回已上机；d1/d2 的 PDMEM perf-lock 投票已接入但未上机） | `K60CpuFreqPlan` 纯算术 + governor 核心（host 203 项，含 mode 5 的 idle 换算、quiet 收敛、mode 6 的 lowest 选择与限频上限夹取）；写前 enable/档位守卫、写后回读、恢复原值已离线（commit `42ca4421`）；image i 2026-11-18 17:30 早读 d0 enable=1 state=1.5552 GHz vote=11 rows=14 top=1.8048 GHz，d1/d2 因辅核未启动读到 0；image j 17:55 在电池 begin 后 5 s 延后读取，d1 enable=1 state=0.6336 GHz vote=16、d2 enable=1 state=0.7872 GHz vote=19，d0/L3 不变（L3 vote=13 rows=15 top=1.7088 GHz）；image k 18:22 转储 66 条有效 LUT 档位（d0/d1/d2/L3 = 14/17/20/15，top 1.8048/2.496/2.9952/1.7088 GHz），所列 raw 行 cores=4/turbo=0，18:16 字段不是域核数；PDMEM perf-lock 投票（`0x17d09804/8/c`，先写 PDMEM 再写 `perf_state`，恢复时写回原值）已按 t970/zizhan 的同 SoC 策略接进 voteDomain 与 mode 7/8，离线编译与 host 通过，尚未上机；mode 10 另按 zizhan 的 L3 follow 策略让 L3 随最快域移动（boost 时到顶，写前保存、结束恢复），host/编译通过但未上机；mode 5 于 2026-11-18 23:19 以 image l 上机：274 条 `sample win=`，d0 busy 0..1000、governor 300 MHz..1.8048 GHz、hw 691.2/1555.2 MHz，d1/d2 按 shared-cluster 下限停在半档附近（image l 暴露 quiet 被降档清零的 bug，已由 `d1d3c3e3` 修复；image m 23:53 复测：busy=0 时 d1/d2 governor 已到 633.6/787.2 MHz 最低档，d0 在 300 MHz/1.8048 GHz 跟随负载，88 条样本）；mode 5 只读、不写寄存器，没有 `sample stop`（300 s autoreset 先到）；mode 6 于 2026-11-19 02:47 以 image n 首次真机写入：d0 `state=81->15->81`、`readback=ok restored=1`（1.5552 GHz → 300 MHz → 恢复）；mode 7（首个降档窗口后 10 s 只降档写回、升档拒绝、结束恢复，commit `545315da`/`9242990d`）已于 2026-11-19 03:26 以 image r 上机：`armed win=854 d0 level=9`、`apply d0 level=9 (1324800kHz) readback=ok state=81->69`、`restore domains=1 votes=1`，首次把 governor 降档决策写进 EPSS 并恢复；mode 8（双向写回，commit `ea8e4e20`）于 03:58 以 image s 上机：`mode8 reseed d1 state=33`/`d2 state=41`、`armed win=625 d0 level=13`，d0 升到 1.8048 GHz（`state=81->94`）再降到 1.1328/1.5552 GHz（`state=94->59`/`81`），11 票后 `restore domains=2 votes=11`，恢复后硬件回到 1.5552 GHz；d1 写回 `state=130->130` 且 hw 仍 2.496 GHz，说明 EPSS 不接受大核簇持续投票；按 Linux `qcom-cpufreq-hw.c` 的 `0x30c`=REG_INTR_STATUS、bit2=GT_IRQ_STATUS 与 `0x20` 低字节做限频上限夹取已接进 governor（host 203 项，未上机），cap 低于最低档时跳过投票；mode 1 只读行新增 limits 原始值与 cap，所有 voteDomain 路径（mode 2/3/6/7）也按 cap 重建 LUT、cap 低于最低档时跳过（archive 145,920 B sha256 `708602a0…`，未上机）；mode 2/3 瞬态写仍未执行。2026-11-19 21:55 的 image w11（离线构建、**未上机**，boot.img 201,887,744 B sha256 `6db4e6b7…`）已带当前探针，参数 30 项 601 B（board 契约 596 B + `k60_cpufreq=1` − `applog=1`），等 slot 后用 `scripts/judge-k60-mode1-console.py` 判只读 A |
| GPU：GMU XO 忙碌计数、50 % 目标、HFI 投票带带宽档（:114） | 部分（投票已被接受，仍无负载） | `K60GpuFreqPlan`（host 140 项，含抽出的 DCVS 窗口规则与提交预唤醒）+ `PongAdrenoGmu` 忙碌计数器/投票 + `PongAdrenoDcvs` 16 ms 线程，opt-in `pong_gpu_dcvs=1`，已构建进 image o/p；CP 环提交窗口（`pong_adreno_cp_pending`）已喂入 boost 规划，60 % 下限已由 CPU governor 消费（见下行）；image o 02:14 上机 24 条窗口、计数器恒 0；image q 02:36 用 =2 探针验证升档/还原两次 HFI 投票均被接受；`34ab1da1` 让提交窗口先布防 50 ms 唤醒档，仍无负载驱动读数；HFI id 30 第三字是 bus index（带宽档索引），已按档投票，不是字节级带宽 |
| 触摸后 CPU P 域与 GPU 最高档保持 1 s（:115） | 部分（CPU 写窗口已上机，P 域不受控、GPU 未测） | 补丁 `0626-k60-touch-activity.patch` 在内核触摸队列里导出 `pong_touch_report_count()`；CPU 采样线程把计数变化喂 `k60_boost_touch()`、以 `boost` 进 governor，GPU DCVS 线程在窗口内把目标档强制为 top（commit `aa3bada7`，host 40 项）。image x 05:47 上机触摸：12 条 `touch boost active/released`、7 条 `tb=1`，计数 1→7，d0 governor 抬到 1,804,800 kHz，但 mode 8 的写窗口在 ~20 s 就已 `restore domains=1 votes=5`，触摸（~121 s）没有写进寄存器。commit `9b8a36b6` 让触摸/帧各自重开短窗口（1 s/300 ms，总票数 32），image y 未上机。image ab（`a6a51bc5`，`forceVote` 强制信号窗口首票）于 07:18 上机触摸：win=6937 `touch window`，d0 `apply level=13 state=15->94`，win=6976 `hw=1804800kHz tb=1`——**硬件第一次跟随触摸写回**，窗口末 `restore domains=3 votes=27`；但 32 票预算当时整轮累计，第二触（win=7207）5 票即耗尽。`43af2a5c` 把预算改成每窗口一份，并让 `boost` 对每个域取 top（原先只作用于共享簇，轻触摸抬不动 d0）；host 154 项；image ac 于 07:34/07:43 两次上机（`restore domains=2 votes=9`/`votes=7`），但窗口内没有触摸（276/273 条全 `tb=0`），轻触摸抬 d0 与第二触预算仍未验证。d1/d2 抬档仍不受 EPSS 控制 |
| 帧：4 窗口中 2 个有提交时 CPU 各域 300 ms 内不低于 60 %（:116） | 部分（已接线，未触发） | `K60BoostPlan` 4 窗口/2 帧/300 ms/60 % 规则（host 40 项）；CPU 采样线程每 16 ms 读 `pong_adreno_cp_pending()` 喂 boost，再把 `k60_boost_frame_active()` 作为 `framing` 传给 governor，mode 8 的升档窗口会把它写成 perf-state 投票（commit `cbdf382f`，archive `9f119715`）；image w 05:07 上机 276 条样本全部 `fr=0`——启动全程 CP 环没有提交窗口，下限一次也没激活；真实 GPU 负载下的 300 ms/60 % 效果仍未验证 |
| fence 等待睡眠到中断、最长 1 ms（:117） | 部分（离线） | `K60BoostPlan` 1 ms 预算函数（host 40 项）；提交路径未改 |
| 外设投票所有权/引用计数、先停 DMA/中断再释放（:109） | 部分（离线） | `K60PowerVotePlan` 纯记账（host 58 项）；无消费者、不写 RSC/TCS |
| OS 电源回调、休眠保存/恢复（:110） | 部分（已进 IOCPUSleepKernel，唤醒恢复挂死） | `ArmCpu::quiesceCPU` 在 `platform-sleep=1` 时进入 `ml_arm_sleep`，GIC 使能保存/恢复与 PSCI CPU_OFF 已接；w9/w10 已从 `sleepSystem` 进入 `IOCPUSleepKernel` 并完成 prepare/restore 与 timer 唤醒，但完整恢复未过，见下行 |
| 目标稳压器、互连、温控顺序（:108） | 部分（顺序模型离线；无写路径） | 路线 A 的 TCS4 lcx/lmx 仍是唯一真实投票；`K60RailPlan` 纯 C 模型（commit `2db8ae79`/`b94cd1ba`）实现 regulator→interconnect→frequency→readback（降档反向、同频先抬后降、温控拒绝升档、容量不足/高频低压/低带宽拒绝、回读成功才提交、回读失败由 k60_rail_rollback 生成反向回滚），host 134 项（含回读失败回滚）；CPU/GPU 电压、互连、温控仍无写路径，见 `power/07-RAIL-ORDERING.md`；下一次上机的 mode 8 仍先写 d0 的 PDMEM/perf_state，rail 顺序模型暂不接线 |
| 平台睡眠（:119-121） | 部分（等待与 timer 唤醒已证，完整恢复挂死） | `power/02-PLATFORM-SLEEP.md`：`ArmCpuSleep.h` + `ArmCpu.cpp` 等待路径（GIC 使能保存/恢复、CNTV 期限、timer PPI 27、storm 掩码、PSCI CPU_OFF），XNU hook `0623`，板级 `K60PlatformSleep.cpp`（timer-only，10 s tick）；`test-armcpu-sleep.c` 1038 项 + `K60SleepPlan` 73 项，十套件 1915 项全过；w9（boot.img `0fc5a223…`、kernel `d87590f6…`、payload `2800c16a…`，30 项/607 B）于 11:39 用 `platform-sleep=1 platform-sleep-wake-after=5 k60_slp=6` 进入 `IOCPUSleepKernel`，`K60TRACE: sleep enter cpus=8`、halt 7..1、`resumed`，`ArmCpu: sleep report phase=5 last_intid=27 last_reason=2`、`K60Sleep: report prepares=1 restores=1`，证明 timer 唤醒成立；随后 panic `Spurious wakeup of cpu 1 @IOCPU.cpp:334`（secondary 在 CPU_OFF 前未置 Stopped）。w10（commit `24746184`，boot.img `4399eea5…`、kernel `20a0aac9…`、payload `0e686049…`）先把 secondary 置 Stopped，console 显示 halt 7..1、secondaries done、resumed、同样的 report，但没有 `wake cpus done`/`IOCPUSleepKernel` 退出，13:29:07 后硬挂，用户手动复位 fastboot；完整恢复（secondary `processor_start`）仍未通过。0624 boot-complete helper 与 0625 K60TRACE 只用于 bring-up，0625 发布前移除或标注。iOS16 暂停上机，iOS27 用 catalog ArmCpu + sheng xnu-12377 补丁重做，见 `08-IOS27-POWER-PORT.md`；PON SPI 481/INTID 513 路由、看门狗喂狗、背光/触摸恢复仍未接；`scripts/judge-k60-sleep-console.py`（28 项测试）把这段尾巴机械化——w8 判 HALT 未完成、w9 判 resume panic、w10 判唤醒后硬挂，不再靠肉眼比较两份 console |
| 负载下测量频率并逐项验证（:111） | 部分（只读） | mode 5 的 image l 已有 274 条真机采样：d0 从 1000 busy/top 档降到 0 busy/300 MHz，证明 16 ms 采样、按域取最忙 CPU、4 窗口降档链路；但 mode 5 的探针不写 EPSS，EPSS 硬件自身仍在 691.2/1555.2 MHz（d0）、2.496 GHz（d1）、2.9952 GHz（d2）之间移动；mode 7 的受限期写回（只降）已于 03:26 以 image r 上机：win=854 后写入 d0 level=9（1,324,800 kHz）、`state=81->69`、10 s 后恢复，硬件回到 1.5552 GHz；GPU 无真机读数，负载/温度/throttle 未测 |

**温控与主动降温（2026-11-19 决定）**：只读实现已由 `feat/thermal-tsens` 验收——22 个传感器读数与 5 个温区校准正确，压力等级经 IOPMrootDomain 发布（2026-11-15 真机：`PongThermal: tsens0[3] cpuss-2 zone27 43.0 C`、`level trapping (3) published as Thermal_Level_Warning=3`）。它**不会**因过热执行降温：真正的冷却动作（cpufreq-cdev）未接，这是第 ⑧ 步不判完成的唯一原因。可抄性已排查：pong 无 thermal 动作；zizhan 的 `ZizhanTsensCore.h` 只读、仓库只有 inventory/readonly 脚本；sheng 的 `CpuFreqProbe.cpp` 无温度输入；Linux K60 的 `cpufreq-cdev` 是 Linux thermal framework 绑定，不能直接搬。降频与 120 fps 共用一份热预算，所以本轮决定 **方案 1（park）**：保留只读监控与等级上报，主动降温策略不做，⑧ 步不再以它为阻塞；重访触发是 GPU 120 fps 飞行完成并做一次热预算实测，届时用默认关闭的 `pong_thermal_cap=1` 做方案 2 的飞行测试。曾尝试把该分支的 0617 补丁导入本分支（image u：mode 9 + thermal），2026-11-19 04:36 上机后串口 0 字节、设备失联需强制复位；该导入已由 `27ceb919` 回滚，thermal 只留在自己的分支。后续用不含温控补丁的 image t（只含 mode 9）复测，07:56 同样 0 字节卡死，说明共同因素是 mode 9 而非温控补丁；mode 9 已由 `3a0a5511` 禁用。2026-11-19 对比 sheng 最新 `origin/main c8f92b2`：其 `CpuFreqProbe.cpp:132-142` 从不写 EPSS `DCVS_CTRL 0xb0`，只在 bit0 已为 1 时写每核 `perf_state` 行；我们的 mode 9 主动置 bit0 是唯一多出来的动作，故已把探针改为只读控制位、不再写 `0xb0`（mode 9 仍禁用）。2026-11-20 另补一层**纯契约**（仍然不降温）：`drivers/PongPower/K60ThermalMap.c` 把现场 FDT 的跳变点做成等级与建议模型，host 125 项，其 `allow_raise` 直接喂 `K60RailPlan` 的温控门（`:108`），见 `power/10-THERMAL-MAP.md`；它不读传感器、不下发任何冷却动作，park 决定不变。

## §6 构建并验证（:123-131）

- 构建链已打通：battery archive → `./unixnu defconfig/tree/kernel/payload/bootimg`，
  image f 三次上机（C1/C2 PASS、低电流 C3 PASS）；image g/h 只做链接验证；image i 于
  2026-11-18 17:30 上机完成 EPSS 早期 mode 1 只读（d0 enable=1、state=1.5552 GHz、rows=14、
  top=1.8048 GHz；d1/d2 辅核未启动读到 0；L3 rows=15）；image j 于 17:55 上机，在电池
  `begin` 后 5 s 第二次读取，d1 `enable=1 state=0.6336 GHz vote=16`、d2
  `enable=1 state=0.7872 GHz vote=19`，三域均可读；image k 于 18:22 上机，转储
  66 条有效 LUT 档位（14/17/20/15），`capture.json complete=true`、console 133,807 B。三个镜像构建时
  `k60_cpufreq` 尚未声明、且缺 `applog=1`；`91e64b4e` 已把它加入 `ALLOWED_ADDITIONS`，用去掉
  `applog=1` 的 board 快照重跑 image k 得到 `OK (30 arguments, 603 bytes)`；构建配置中的
  `applog=1` 已恢复，见 `power/01-EPSS-PROBE.md` §6。
  image l 于 2026-11-18 23:19 以 `k60_cpufreq=5` 上机（boot.img 201,887,744 B，sha256
  `86d1933f…`；console 159,147 B，sha256 `c2ee7fa3…`），274 条 `sample win=`，只读且未写 EPSS；
  `capture.json` complete=true、panicMarker=null，300 s autoreset 先到，没有 `sample stop`。
  image m 于 23:53 复测 quiet 修复（boot.img sha256 `51ddb82a…`，console 114,585 B sha256
  `a96a98f5…`，88 条 `sample win=`）：busy=0 时 d1/d2 governor 为 633.6/787.2 MHz 最低档，
  d0 在 300 MHz/1.8048 GHz 跟随负载；mode 5 只读。02:47 的 image n 用 mode 6 完成首次真机 EPSS 写入：
  d0 `state=81->15->81`、`readback=ok restored=1`，只降不升；mode 2/3 升档仍未执行。
   image r 于 2026-11-19 03:26 以 `k60_cpufreq=7` 上机（boot.img sha256 `684aa20d…`，参数 gate
   `OK (30 arguments, 603 bytes)`；console 164,926 B，sha256 `ed4080bb…`，277 条 `sample win=`，
   panicMarker=null）：`mode7 armed win=854 d0 level=9` 后写入 `level=9 (1324800kHz) readback=ok
   state=81->69`，10 s 后 `mode7 restore domains=1 votes=1`；同轮出现一次 `raise refused`。
   image s 于 03:58 以 `k60_cpufreq=8` 上机（boot.img sha256 `47c21976…`，参数 gate `OK (30 arguments, 603 bytes)`；
   console 165,881 B，sha256 `d98bdc30…`，277 条 `sample win=`）：d0 双向写回共 11 票后
   `mode8 restore domains=2 votes=11`，升档 `state=81->94`（1.8048 GHz）、降档 `state=94->59`（1.1328 GHz），
   恢复后硬件回到 1.5552 GHz；d1 的写回 `state=130->130`、采样 hw 仍 2.496 GHz，大核簇没有被接管。
   image w 于 05:07 以同一模式上机（boot.img sha256 `005b3095…`，kernel `ca262497…`，参数 gate
   `OK (30 arguments, 603 bytes)`，console 166,296 B sha256 `de6160f6…`，276 条 `sample win=`）：
   新增的 CP 环采样与 `framing` 调用路径执行正常，但每条样本都是 `fr=0`——启动全程没有 GPU
   提交，帧下限未激活；mode 8 仍完成 d0 双向写回与 `restore domains=2 votes=3`。
   image x 于 05:47 以同一模式上机并触摸屏幕（boot.img sha256 `5fd27783…`，kernel `f1605e01…`，
   console 169,977 B sha256 `47d94a2e…`，2500 行）：12 条 `touch boost` 日志、7 条 `tb=1`、
   报告计数 1→7，d0 governor 在触摸窗口内为 1,804,800 kHz；但 `mode8 restore domains=1 votes=5`
   发生在触摸之前，`hw` 仍为 1,555,200 kHz。`9b8a36b6` 的触摸/帧重开写窗口进了 image y（boot.img sha256 `71141ac7…`），但所有投票仍受
   100 s 的 `kApplyLatestEndWindow` 限制；`a0e8a060` 去掉信号窗口的该上限（仍受 32 票预算），
   image z（boot.img sha256 `59921097…`，`OK (30 arguments, 603 bytes)`）用这份代码构建，
   06:47 尝试上机时设备不在 fastboot，空窗随后被 wifi/audio watcher 占用，image y/z 均未上机。
 - image ab 于 07:18 上机（boot.img sha256 `a0563a08…`，kernel `e5a26b91…`，30 项 603 B，
   console 176,279 B sha256 `4fbecff2…`，276 条样本）：`forceVote` 让触摸窗口真正写入，
   win=6937 `touch window span=63`、d0 `level=0 state=36->15` 后 `level=13 state=15->94`，
   win=6976 样本 `d0=1000/1804800kHz/hw1804800kHz … tb=1`，窗口末 `restore domains=3 votes=27`；
   第二触 win=7207 只写 5 票就 `votes=32` 触发恢复，暴露票数是整轮累计；且 `boost` 只作用于
   共享簇，轻触摸不会抬 d0。`43af2a5c` 改为每窗口重置票数、`boost` 对每个域取 top，host 154 项，
   archive 137,520 B（`5d6d1203…`），image ac 用这份代码构建。
 - image ac 于 07:34 与 07:43 两次上机（boot.img sha256 `0d5a5411…`，kernel `001003aa…`，30 项 603 B）：
   启动与 mode 8 写回正常（`restore domains=2 votes=9` 与 `votes=7`），但采集窗口内没有触摸，
   276/273 条样本全 `tb=0`；「轻触摸抬 d0」与「第二触仍有预算」仍未上机验证。
   GPU DCVS（GMU 忙碌计数器 + HFI 投票 + 16 ms 线程，窗口规则已抽进 host 140 项的模块）已实现；image o 02:14 验证线程与计数器读取，image q 02:36 验证 HFI 投票被接受，但还没有负载驱动的升档
   （`E:/k60-work/artifacts/power-conformance-20261119o/boot.img`，201,887,744 B，sha256
   `b8e44043…`，kernel `d2b246bc…`；参数 gate OK，30 项 605 字节；`pong_gpu_dcvs=1` 默认关闭），o/q 均已上机，只缺负载驱动的升档闭环。
- 2026-11-19 04:36 的 image u（`k60_cpufreq=9` + 导入的 0617 thermal 补丁，boot.img sha256 `fab4fe61…`，30 项 603 字节）与 07:56 的 image t（只含 mode 9、无温控补丁，boot.img sha256 `567d9b62…`，30 项 603 字节）**都未能启动**：fastboot 接受镜像，但 CDC-ACM 串口从未枚举（`capture.json state=port-not-observed`、0 字节、`returnedToFastboot=false`），设备失联直到强制复位。两次唯一的共同因素是 mode 9，温控补丁没有被证明有罪；`3a0a5511` 已在入口拒绝 9，thermal 导入仍由 `27ceb919` 回滚、只留在自己的分支。
- 平台睡眠于 2026-11-19 落地：`ArmCpuSleep.h` + `ArmCpu.cpp` 等待路径（保存 GICD_ISENABLER、只留唤醒源、CNTV 期限、timer PPI 27、storm 掩码、PSCI CPU_OFF）、XNU hook `0623`、板级 `K60PlatformSleep.cpp`（timer-only，10 s tick）；`test-armcpu-sleep.c` 1038 项，七套件 1530 项全过，battery archive 140,048 B `f867efca…`。image z 首次 bootstrap 链接只带 GPU/电池 archive，电池新增的 `armcpu_sleep_register` 未定义，407ea557 在电池之前补 `-force_load libArmCpu.a` 后重建成功：boot.img 201,887,744 B sha256 `b167d4f9…`、kernel `df50f894…`、payload `facd5bc5…`，kernel 符号 `_armcpu_sleep_register`/`_k60_platform_sleep_register`/`_arm64_platform_sleep_hook` 都在；默认启动已于 2026-11-19 10:12 到 SpringBoard（console 168,735 B sha256 `4ec7b2c6…`，2491 行，panicMarker null，无 prepare/restore）；w9/w10 已进入 IOCPUSleepKernel 并完成 prepare/restore 与 timer PPI 27 唤醒，但 w9 panic Spurious wakeup、w10 在 secondary processor_start 硬挂，完整恢复未过。PON SPI 481/INTID 513 路由、看门狗喂狗、背光/触摸恢复仍缺。
- 缺：GPU 真机读数与投票结果、负载/温度/throttle 读数、外设转换与恢复的逐项验证、重启行为记录、主动降温（已按方案 1 park）。
- 状态：**部分**。
- 离线纯逻辑套件一条命令可复现：`bash scripts/tests/run-k60-power-host.sh`（WSL/Linux，可选一个输出目录）
  先跑 `scripts/check-power-portability.py`（八个策略模块必须无 IOKit/XNU 依赖、能以 freestanding C11 编译），
  再依次编译运行 CPU 目标档、GPU 目标档、boost 窗口、睡眠唤醒路径、外设投票、ArmCpuSleep 接口和
  跨模块数值钉住、温控跳变点地图与充电认证状态机（含 HMAC 向量）共 10 个套件，合计 1915 项断言（203/140/40/73/58/1038/134/125/99/5）；设 `K60_POWER_SANITIZE=1` 可加 ASan/UBSan 重跑同一套。`test-k60-power-conformance.c` 用 `_Static_assert` 把官网 §5 的
  1.25 倍余量、50 % GPU 目标、578 MHz 地板、1 s 触摸、300 ms/60 % 帧下限、50 ms GPU 唤醒、1 ms fence、
  10 s 喂狗、两帧/1500/600 ms 背光与 60 ms 触摸间隔钉在跨模块位置；每个套件必须打印自己记录的数量，
  数量漂移即失败。C 套件之后同一条命令再跑 python 那半——carry 清单、四个控制台判读器、27 预检，
  与硬件契约表核对（`HW-CONTRACTS.toml`，24 行 file:line 引用、13 行带独立第二来源）、再把那些第二来源
  逐字节读回来（`read-fdt-props.py` 自己 22 项用例）、并核对本节自己引用的数字（`check-power-counts.py` 17 项用例），共 11 个套件（`wire-props` 把 `charger/WIRE-PROPS.toml` 的 19 个 wire 属性号与驱动表、反编译表、厂商 `.rodata` 三处对齐；`prop-numbers` 逐行判定 `charger/PROP-NUMBERS.toml` 的 18 个 16→27 属性号，结论只允许 相同 / 不同且已知谁改 / 查不到）——并打印 `power-python: OK (11 suites)`，任一退出非零即整个 runner 失败。判读器没有
  runner 引用时会静默腐烂（充电认证套件就这样躺了一轮），所以两半都挂在这一个入口上。ADSP 那三个
  python 套件（SMCCC 文本门、image 与 MDT 读取器）挂在 `run-k60-handoff-host.sh`——第一个判的是内核
  补丁，三个都不在 power 的搬运集里。它只证明离线逻辑，不替代真机证据；ADSP/电池上机套件仍在
  `scripts/tests/run-k60-handoff-host.sh`。
- 跨版本搬运可校验：`docs/research/power/CARRY.toml` 把八个纯 C 模块的 16 个文件与 872 项断言
  钉成清单，`python3 scripts/check-power-carry.py` 校验哈希、套件数与 portability 列表，
  `--target <树>` 逐文件比对另一棵检出（`--update` 刷新哈希）。2026-11-20 对
  `E:/hackios/xnekom-ios27` 实测六个模块 `SAME`、`K60ThermalMap` 三个 `MISS`：那份 iOS27
  检出停在温控提交之前，合并即可。清单同时钉住四个 console 判读器（handoff 33 / sleep 28 / mode1 14 / battery-mirror 21 例）：
  判读器搬过去先跑夹具，夹具打印的用例数与清单不符即失败，因为缩水的夹具就是 P-204 那种"绿而盲"。
  检查器自带 34 项测试（`scripts/tests/test-power-carry.py`）。
- 27 侧前置检查：`scripts/check-ios27-power-preflight.py`（22 项测试）把五件事合成一份输出——
  七个模块的哈希、`0629-k60-sleep-trace.patch` 里 report 是否仍被 `#if defined(PONG)` 包住、
  27 树的 `pick-xnu-builder.sh` 是否选 `build-xnu-generic.sh`、四个判读器是否已并入、七份契约表
  （`CARRY.toml`、`HW-CONTRACTS.toml` 与它生成的 `-IOS27.md`、`PROP-NUMBERS.toml` 与 `.md`、
  `LANE-CONFORMANCE.toml` 与 `.md`）是否随树带入——只搬了模块没搬表的树有代码却没有改线清单。
- 逐条对齐官网页面的表是 `docs/research/power/LANE-CONFORMANCE.toml`（24 行，adsp 5 / battery 7 /
  charger 1 / thermal 2 / power 9），`python3 scripts/check-lane-conformance.py` 核对三件事：
  `requirement` 的句子必须真的出现在 `docs/zh/porting/power.md` 那一节（防止凭记忆引一句不存在的话）、
  `evidence` 必须是一个存在的文件、非 `verified` 的行必须写 `why`；`--render` 生成
  `LANE-CONFORMANCE.md`（同一份表，给读者看）。2026-11-20 的结论是 24 行里 verified 19、partial 5
  （`dsp-firmware-auth` 只有离线证据、`charger-independent-protocol` 未上机、`thermal-advise` 的
  温控证据不可用、`battery-device-verification` 缺真插拔/放电/超时/服务重启、`power-fence-wait`
  的 1 ms 预算已写进规则但 fence 还没有消费者），夹具 16 项。这张表与 runner 无关，因为它依赖官方页面的本地副本
  `E:/hackios/UniXNU/docs/zh/porting/power.md`，搬出去的树没有那份副本。
  2026-11-20 对 `xnekom-ios27@ee910a78` 实测 3 个阻塞（温控三文件缺、PONG 门控、两个判读器缺），
  builder 路由已通过。

## 汇总

排除 §2/§3（音频分支）后，本分支的完成度估计：§1 约 80 %、§4 约 85 %、
§5 约 82 %（平台睡眠等待/定时唤醒已上机，完整恢复挂死）、§6 约 60 %；整页（含音频与充电认证）仍远未闭环。离线部分已经
把 OPP/EPSS、GPU 规划、boost、投票账本、睡眠掩码、固件清单和稳压器顺序审计
补齐；EPSS 写入守卫、回读与恢复、mode 5 的 16 ms 只读采样、mode 6 的只降 d0 写入路径均已离线
补齐（host 154 项），mode 5 已于 23:19（274 条）与 23:53（image m，88 条）两次上机，mode 6 已于 02:47（image n）完成首次真机写入；
image m 复测确认 quiet 修复后 d1/d2 已稳定到 633.6/787.2 MHz 最低档，d0 可降到 300 MHz，探针不写 EPSS；
GPU DCVS 也已接上 GMU XO 忙碌计数器、HFI id 30 投票与 16 ms 线程（host 140 项，含提交窗口预唤醒）；image o 02:14 上机后线程稳定、计数器恒 0，image q 02:36 的两次探针投票均返回成功，CP 环提交窗口已作为 boost 输入，60 % 下限也已接进 CPU governor
（`cbdf382f`，mode 8 升档窗口写回）；image w 05:07 采集 276 条样本全部 `fr=0`，启动全程没有 GPU 提交，下限未激活（`pong_gpu_dcvs=1`）。image n 的 mode 6 结果：d0 `state=81->15->81`、`readback=ok restored=1`，
**写入与恢复都已在真机成立**，但仍只限 d0 单域、只降不升。governor 写回已由 mode 7 实现并于 03:26 以 image r 上机
（只降、首个降档窗口后 10 s、最多 16 票、结束恢复原值、升档拒绝）：`armed win=854` 后 d0
`state=81->69`、`readback=ok`，10 s 后 `restore domains=1 votes=1`，硬件回到 1.5552 GHz；升档仍须先接电压/互连/温控顺序，
触摸/帧信号（§5 :115-:117）已接：触摸计数补丁 `0622` 与 CPU/GPU 消费方 `aa3bada7` 已进 image x（05:47 拿到 `tb=1`、计数 1→7，但写窗口先关）；`9b8a36b6` 重开窗口、`a0e8a060` 去掉 100 s 上限、`a6a51bc5` 强制首票，image ab 于 07:18 把 d0 写到 `state=15->94`、`hw=1804800kHz`（`restore domains=3 votes=27`）；`43af2a5c` 再把票数改为每窗口重置、`boost` 覆盖每个域，image ac 于 07:34/07:43 两次上机但窗口内没有触摸（276/273 条 `tb=0`），轻触摸与预算仍未验证；帧下限自 image w 起从 CP 环采样（276 条 `fr=0`）。mode 8 于 03:58 以 image s 把升档也写进 d0：`apply d0 level=13 (1804800kHz) readback=ok state=81->94`，与降档交替 11 票后 `restore domains=2 votes=11`；但 d1 的 `apply level=16 readback=ok` 之后 `state=130->130`、硬件仍是 2.496 GHz，EPSS 对大核簇的自主控制没有被这条路径接管，d1/d2 的写回应视为无效。
版本无关的 CPU 策略继续补齐：PDMEM perf-lock（`0x17d09804/8/c`）、L3 follow（`0x17d90000` + `0x90`）与 `0x30c` bit2（GT_IRQ_STATUS）+ `0x20` 限频上限夹取均已接进 `K60CpuFreqPlan`/探针（host 203 项、十套件 1915 项；`K60RailPlan` 的 134 项顺序/回滚断言与 `K60ThermalMap` 的 125 项也在此套件内），但都没有上机；下次有确认的测试计划时再验证。只读 A 的判据已固化为 `scripts/judge-k60-mode1-console.py`（14 cases；检查 capture、late read 三域 enable、L3 15 行、无写行与 SpringBoard，cap 公式只作 NOTE）。

温控只读线在 `feat/thermal-tsens` 已验收（22 传感器、等级发布），主动降温按方案 1 park，本分支不接线（导入尝试以 `27ceb919` 回滚）。电池插拔暂缓；充电认证移植已在 `feat/charge-auth` 分支（默认关闭接入；18 B 的参数装不进 596 B 基线剩下的 11 B）。

## 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt`。
- §4：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md`。
- §5：`docs/research/power/01-EPSS-PROBE.md`、`02-PLATFORM-SLEEP.md`、
  `03-POWER-VOTES.md`、`04-GPU-FREQUENCY.md`、`05-BOOST-RULES.md`、
  `06-FIRMWARE-MANIFEST.md`、`07-RAIL-ORDERING.md`。
- 驱动映射：`docs/plans/OFFICIAL-DRIVER-MAP.md`。
