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
| DSP 固件/PAS ID、预留内存、邮箱、共享内存、时钟电源归属 | 部分 | Route A ADSP 启动在 image e/f 上 `rc=0`，PAS1 `epoch=1 flags=15`；`docs/research/charger/02-GLINK-CONTRACT.md`、`docs/plans/OFFICIAL-DRIVER-MAP.md:44` |
| 音频 codec/功放、总线、时钟、路由、拓扑、格式、OS ABI | 委派 | 音频分支 `feat/audio-adsp-merge`（2026-11-18 时 HEAD `c74aea80`，145 commits ahead，未合并） |
| 电池电量计/固件协议、属性 ID、单位、电流符号、通知 | 已验证（测量）/部分（全节） | `K60Battmgr.c`、`K60Battery.cpp`；`charger/04-PROP-MAP.md`；属性 9 静默、USB 输入电流边界见 §4 |
| 电源时钟域、OPP 表、稳压器、固件投票、温控限制 | 部分（离线） | EPSS/GPU OPP 表现场 FDT 已确认；只有路线 A 的 TCS4 lcx/lmx 两条真实投票，CPU/GPU 电压与温控仍无写路径，见 `power/07-RAIL-ORDERING.md` |
| 固件清单记录来源和版本 | 部分 | `power/06-FIRMWARE-MANIFEST.md` 记录 ADSP 26 段/充电器 .ko/carrier FD 的哈希与来源；整机其他固件与认证密钥未覆盖 |

## §2 DSP 传输（:16-27）

- 本树有 GLINK/SMEM/邮箱与 Route A 启动代码（`K60Adsp*`、`QcomGlink.c`），
  电池通道的登录/订阅/单请求/超时/断链 stale 已在 image e/f 上验证。
- 官方列出的通道注册 API（`sheng_adsp_channel`）、560 字节上限、回调复制到有界队列、
  断链取消与重连协商属于**音频分支**的实现范围；本分支只消费电池通道。
- 状态：**委派（音频分支）**，本分支不宣称 §2 完成。

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
| 充电认证 PD/PPS/MiPPS（:82-88） | 部分（仅移植）：sheng 的 `ShengChargeAuth.c` 已移植到 `feat/charge-auth`（host 85 项，未接入电池队列）；本分支仍未接线，K60 固件侧的认证字段与密钥没有来源 |
| Linux 充电读取镜像（:89-104） | 未接入；参考脚本在 sheng 仓库 |

## §5 调频与电源操作（:105-121）

| 条目（行号） | 状态 | 证据/缺口 |
| --- | --- | --- |
| CPU：16 ms 读空闲、1.25 倍余量、4 窗口降频（:113） | 部分（真机只读） | `K60CpuFreqPlan` 纯算术 + governor 核心（host 151 项，含 mode 5 的 idle 换算、quiet 收敛与 mode 6 的 lowest 选择）；写前 enable/档位守卫、写后回读、恢复原值已离线（commit `42ca4421`）；image i 2026-11-18 17:30 早读 d0 enable=1 state=1.5552 GHz vote=11 rows=14 top=1.8048 GHz，d1/d2 因辅核未启动读到 0；image j 17:55 在电池 begin 后 5 s 延后读取，d1 enable=1 state=0.6336 GHz vote=16、d2 enable=1 state=0.7872 GHz vote=19，d0/L3 不变（L3 vote=13 rows=15 top=1.7088 GHz）；image k 18:22 转储 66 条有效 LUT 档位（d0/d1/d2/L3 = 14/17/20/15，top 1.8048/2.496/2.9952/1.7088 GHz），所列 raw 行 cores=4/turbo=0，18:16 字段不是域核数；mode 5 于 2026-11-18 23:19 以 image l 上机：274 条 `sample win=`，d0 busy 0..1000、governor 300 MHz..1.8048 GHz、hw 691.2/1555.2 MHz，d1/d2 按 shared-cluster 下限停在半档附近（image l 暴露 quiet 被降档清零的 bug，已由 `d1d3c3e3` 修复；image m 23:53 复测：busy=0 时 d1/d2 governor 已到 633.6/787.2 MHz 最低档，d0 在 300 MHz/1.8048 GHz 跟随负载，88 条样本）；mode 5 只读、不写寄存器，没有 `sample stop`（300 s autoreset 先到）；mode 6 于 2026-11-19 02:47 以 image n 首次真机写入：d0 `state=81->15->81`、`readback=ok restored=1`（1.5552 GHz → 300 MHz → 恢复），mode 2/3 升档仍未上机 |
| GPU：GMU XO 忙碌计数、50 % 目标、HFI 投票带带宽（:114） | 部分（投票已被接受，仍无负载） | `K60GpuFreqPlan`（host 123 项，含抽出的 DCVS 窗口规则）+ `PongAdrenoGmu` 忙碌计数器/投票 + `PongAdrenoDcvs` 16 ms 线程，opt-in `pong_gpu_dcvs=1`，已构建进 image o/p；CP 环提交窗口（`pong_adreno_cp_pending`）已喂入 boost 规划，60 % 下限只记录未投票；image o 02:14 上机 24 条窗口、计数器恒 0；image q 02:36 用 =2 探针验证升档/还原两次 HFI 投票均被接受，仍无负载驱动读数 |
| 触摸后 CPU P 域与 GPU 最高档保持 1 s（:115） | 部分（离线） | `K60BoostPlan` 触摸 1000 ms 规则与四窗口提交判定（host 40 项），CP 环已作为提交输入接入 DCVS；仍无触摸输入源，60 % CPU 下限没有投票消费者 |
| 帧：4 窗口中 2 个有提交时 CPU 各域 300 ms 内不低于 60 %（:116） | 部分（离线） | `K60BoostPlan` 4 窗口/2 帧/300 ms/60 % 规则（host 40 项）；提交路径尚未采样 |
| fence 等待睡眠到中断、最长 1 ms（:117） | 部分（离线） | `K60BoostPlan` 1 ms 预算函数（host 40 项）；提交路径未改 |
| 外设投票所有权/引用计数、先停 DMA/中断再释放（:109） | 部分（离线） | `K60PowerVotePlan` 纯记账（host 58 项）；无消费者、不写 RSC/TCS |
| OS 电源回调、休眠保存/恢复（:110） | 未实现 | 见 §5 平台睡眠 |
| 目标稳压器、互连、温控顺序（:108） | 部分（离线） | 只有路线 A 的 TCS4 lcx/lmx 真实投票；CPU/GPU 电压、互连、温控无写路径；顺序与回滚见 `power/07-RAIL-ORDERING.md` |
| 平台睡眠（:119-121） | 未实现 | `power/02-PLATFORM-SLEEP.md` 调研 + `K60SleepPlan` 掩码（host 53 项）；无 ArmCpuSleep、TLMM、PON、喂狗、背光/触摸恢复 |
| 负载下测量频率并逐项验证（:111） | 部分（只读） | mode 5 的 image l 已有 274 条真机采样：d0 从 1000 busy/top 档降到 0 busy/300 MHz，证明 16 ms 采样、按域取最忙 CPU、4 窗口降档链路；但探针不写 EPSS，EPSS 硬件自身仍在 691.2/1555.2 MHz（d0）、2.496 GHz（d1）、2.9952 GHz（d2）之间移动；GPU 无真机读数，负载/温度/throttle 未测 |

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
   GPU DCVS（GMU 忙碌计数器 + HFI 投票 + 16 ms 线程，窗口规则已抽进 host 123 项的模块）已实现；image o 02:14 验证线程与计数器读取，image q 02:36 验证 HFI 投票被接受，但还没有负载驱动的升档
   （`E:/k60-work/artifacts/power-conformance-20261119o/boot.img`，201,887,744 B，sha256
   `b8e44043…`，kernel `d2b246bc…`；参数 gate OK，30 项 605 字节；`pong_gpu_dcvs=1` 默认关闭），未上机。
- 缺：GPU 真机读数与投票结果、负载/温度/throttle 读数、外设转换与恢复的逐项验证、重启行为记录。
- 状态：**部分**。

## 汇总

排除 §2/§3（音频分支）后，本分支的完成度估计：§1 约 80 %、§4 约 85 %、
§5 约 65 %、§6 约 60 %；整页（含音频与充电认证）仍远未闭环。离线部分已经
把 OPP/EPSS、GPU 规划、boost、投票账本、睡眠掩码、固件清单和稳压器顺序审计
补齐；EPSS 写入守卫、回读与恢复、mode 5 的 16 ms 只读采样、mode 6 的只降 d0 写入路径均已离线
补齐（host 151 项），mode 5 已于 23:19（274 条）与 23:53（image m，88 条）两次上机，mode 6 已于 02:47（image n）完成首次真机写入；
image m 复测确认 quiet 修复后 d1/d2 已稳定到 633.6/787.2 MHz 最低档，d0 可降到 300 MHz，探针不写 EPSS；
GPU DCVS 也已接上 GMU XO 忙碌计数器、HFI id 30 投票与 16 ms 线程（host 123 项）；image o 02:14 上机后线程稳定、计数器恒 0，image q 02:36 的两次探针投票均返回成功，CP 环提交窗口已作为 boost 输入，但 60 % 下限只记录
（`pong_gpu_dcvs=1`）。image n 的 mode 6 结果：d0 `state=81->15->81`、`readback=ok restored=1`，
**写入与恢复都已在真机成立**，但仍只限 d0 单域、只降不升。下一步在同一域上观察负载下的 governor 决策与温度，
再考虑把决策写回；升档仍须先接电压/互连/温控顺序，触摸/帧信号（§5 :115-:117）仍缺。
电池插拔暂缓；充电认证移植已在 `feat/charge-auth` 分支（未接入）。

## 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt`。
- §4：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md`。
- §5：`docs/research/power/01-EPSS-PROBE.md`、`02-PLATFORM-SLEEP.md`、
  `03-POWER-VOTES.md`、`04-GPU-FREQUENCY.md`、`05-BOOST-RULES.md`、
  `06-FIRMWARE-MANIFEST.md`、`07-RAIL-ORDERING.md`。
- 驱动映射：`docs/plans/OFFICIAL-DRIVER-MAP.md`。
