# 四条线 + Power 对官网页面的逐条对齐（生成物）

由 `python3 scripts/check-lane-conformance.py --render` 生成，**不要手改**：改
`docs/research/power/LANE-CONFORMANCE.toml`。门禁核对五件事——引用的句子确实在页面上、
证据文件确实存在、`verified` 行写的那行证据确实在文件里、非 `verified` 的行写了理由、
同一 lane 里同一句要求没有被两行重复引用（P-259）。

页面：`docs/zh/porting/power.md`（unixnu.com/zh/porting/power）。

合计 30 行：verified 22，partial 8。

## adsp（7 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `dsp-firmware-auth` | 2 | 按目标硬件适配固件认证、预留内存和电源投票 | `drivers/PongPower/K60AdspPas.c`<br>`k60_adsp_auth_and_reset` | partial | SMC 认证与 0x9fd00000 载入点都写进了驱动与 0613 补丁（P-255 的 clobber 契约有门禁），但没有上机：认证成功的证据只有离线语义，没有 DSP 侧回执 |
| `dsp-channel-callback` | 2 | 实现 `ShengAdspClient` 的通道状态和接收回调 | `drivers/PongPower/K60Battery.cpp`<br>`const K60PmicGlink::Client callbacks = {state, receive};` | verified | — |
| `dsp-channel-name` | 2 | 通道名、接收缓冲大小和打开方向采用目标服务协议的定义 | `drivers/PongPower/K60BatteryConfig.h`<br>`#define K60_ADSP_HANDOFF_PROPERTY "k60-adsp-glink-handoff"` | verified | 通道名在 :17；104 字节 handoff 记录在 :16，RX 偏移/长度在 :27；打开调用在 K60Battery.cpp:585 使用这份 config |
| `dsp-send-result` | 2 | 处理 `sheng_adsp_send` 返回值 | `drivers/PongPower/K60Battery.cpp`<br>`if (rc != QcomGlinkOk) {stale("GLINK send refused"); return;}` | verified | — |
| `dsp-channel-open` | 2 | 通道能够打开 | `drivers/PongPower/K60Battery.cpp`<br>`if (!transport.open(config, handoff, callbacks, this)) {` | verified | 打开失败时打印 transport initialization rejected 并返回 false，不发布服务 |
| `dsp-request-timeout` | 2 | 完成一次有超时的请求/响应 | `drivers/PongPower/K60Battery.cpp`<br>`if (self->waitingSince && milliseconds() - self->waitingSince >= kRequestMs) {` | verified | kRequestMs 是 3000 ms；requestTimer 也在 :426 设了同一超时，超时后标记 stale 并重开通道 |
| `dsp-channel-reconnect` | 2 | 报告失败并重连 | `drivers/PongPower/K60Battery.cpp`<br>`if (!self->transport.reopen()) {self->transport.close(); return;}` | verified | GLINK send 失败在 :423 报告并返回；重开失败就关闭，避免把旧通道当成新会话 |

## battery（7 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `battery-owner-check` | 4 | 接收值前核对 owner | `drivers/PongPower/K60Battmgr.c`<br>`if (!data \|\| bytes < 12 \|\| le32(data) != K60_BATTMGR_OWNER) {b->ignored++; return K60BmIgnored;}` | verified | owner 是回复的第一个 32 位字；对不上就计入 ignored 并丢弃。消息类型/opcode/property 由 fields[] 编码，回复长度在 k60_battmgr_init 里校验 |
| `battery-one-outstanding` | 4 | 每次保留一个未完成请求 | `drivers/PongPower/K60Battmgr.c`<br>`if (b->flight \|\| b->poisoned) return 0;` | verified | — |
| `battery-snapshot-units` | 4 | 将以 0.01% 为单位的容量值转换为百分比 | `drivers/PongPower/K60Battery.cpp`<br>`const int32_t percent = (int32_t)((s.capacity_hundredths + 50) / 100);` | verified | K60Battery.cpp:60 的四舍五入转换；判读器把档位错误命名为 unit slip，而不是测量偏差 |
| `battery-register-service` | 4 | 初始有效属性准备好后调用 `registerService()` | `drivers/PongPower/K60Battery.cpp`<br>`registerService();` | verified | — |
| `battery-firmware-ownership` | 4 | 固件负责充电控制时保留其所有权 | `drivers/PongPower/K60Battmgr.c`<br>`Charging control remains entirely firmware-owned.` | partial | 只有 K60Battmgr.c:5 的注释声明固件所有权；驱动确实不发充电写请求，但注释不是可执行判据，也没有上机用例证明固件仍在控制。charge-auth 是独立参数且默认关闭 |
| `battery-property-numbers` | 4 | 使用前确认目标协议的单位和充电电流符号 | `docs/research/charger/PROP-NUMBERS.toml`<br>`verdict = "same"` | verified | 18 行 16→27 属性号逐行判定，全部 same |
| `battery-device-verification` | 4 | 验证插拔电源、充放电、响应超时和服务重启 | `docs/research/charger/07-DEVICE-CRITERIA.md`<br>`C1 订阅 → C2 四属性 → C3 Android 对照` | partial | C1/C2/C3 判据与判读器都在，真插拔、放电、超时与服务重启一次没做；上机只由 Lead 排 |

## charger（1 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `charger-independent-protocol` | 4 | 主机控制的充电器需要独立的控制协议、限值和温控策略 | `drivers/PongPower/K60ChargeAuth.c`<br>`Protocol constants from xiaomi-mipps-auth` | partial | 协议与 HMAC（RFC 4231 向量 5 项）都在 host 侧验证过，但从未上机；18 字节的参数只能在探针镜像里飞 |

## thermal（2 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `thermal-advise` | 5 | 按规定顺序执行目标稳压器、互连和温控要求 | `drivers/PongPower/K60ThermalMap.c`<br>`k60_thermal_advise` | partial | 9 个 AP 温区与 6 级阶梯有 125 项 host 断言，但热证据整批不可用（capture state port-not-observed、console 0 字节），只能拒绝升档，不能证明真实触发 |
| `thermal-limits` | 1 | 时钟域、OPP 表、稳压器、固件投票和温控限制 | `docs/research/power/HW-CONTRACTS.toml`<br>`id = "thermal-trip-warm"` | partial | 温控阶梯（9 个温区、6 级）和 HW-CONTRACTS 的 trip 行有离线判据；时钟域、OPP 表、稳压器和固件投票不在本仓热路径里，一行 trip id 不能覆盖它们 |

## power（13 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `power-epss-lut` | 5 | 读取目标 LUT、参考时钟和使能状态 | `drivers/PongPower/K60CpuFreqProbe.cpp`<br>`rows[i] = rd32(window->va, K60_CPU_FREQ_REG_FREQ_LUT + i * 4);` | partial | LUT 在 :116 读、使能在 :169 读；参考时钟是 K60CpuFreqPlan.h:30 的 19.2 MHz 常量，不是从硬件读回，所以这一行只覆盖读取路径的一半 |
| `power-domain-busiest` | 5 | 频域跟随其中最忙的 CPU | `drivers/PongPower/K60CpuFreqPlan.c`<br>`if (b > busy) busy = b;` | verified | 按域取最大而不是平均；:270 的 elapsed 形式也用同一规则 |
| `power-headroom` | 5 | 留 1.25 倍余量 | `drivers/PongPower/K60CpuFreqPlan.h`<br>`#define K60_CPU_FREQ_MARGIN 125u` | verified | 125/100 在 K60CpuFreqPlan.c:145-146 参与目标频率计算 |
| `power-down-window` | 5 | 连续四个较闲的窗口后才降频 | `drivers/PongPower/K60CpuFreqPlan.c`<br>`if (++*down >= K60_CPU_FREQ_DOWN_WINDOWS) {` | verified | K60_CPU_FREQ_DOWN_WINDOWS 是 4u；*down 跨窗口保留，升频时清零 |
| `power-sleep-resume` | 5 | 休眠/唤醒时保存所需状态，恢复时钟与映射 | `scripts/judge-k60-sleep-console.py`<br>`K60Sleep: report prepares>=1 restores>=1` | verified | 11 份真机 console 上跑过；0629 的报告门控已从 defined(PONG) 改成 K60_PLATFORM_SLEEP_REPORT |
| `power-vote-ownership` | 5 | 为外设电源投票明确所有权 | `drivers/PongPower/K60PowerVotePlan.c`<br>`state->owners[resource] \|= bit;` | verified | 每个 owner 一个 bit；同一 owner 重复 acquire 返回 -3（K60PowerVotePlan.c:21） |
| `power-vote-refcount` | 5 | 引用计数 | `drivers/PongPower/K60PowerVotePlan.c`<br>`state->counts[resource] = (uint16_t)(state->counts[resource] + 1);` | verified | count 与 owner 位一一对应，K60PowerVotePlan.h:47 写明 count 等于 owner 位数；release 递减 |
| `power-idle-cadence` | 5 | 每 16 ms | `drivers/PongPower/K60CpuFreqProbe.cpp`<br>`constexpr unsigned kSampleSleepMs = 16;` | verified | governorThread 以 IOSleep(kSampleSleepMs) 采样；16 ms 与页面的窗口一致 |
| `power-idle-source` | 5 | 读取调度器记录的各 CPU 空闲时间 | `drivers/PongPower/K60CpuFreqProbe.cpp`<br>`if (processor_info(processor_array[cpu], PROCESSOR_CPU_LOAD_INFO, &host,` | verified | 逐 CPU 读 PROCESSOR_CPU_LOAD_INFO 的 cpu_ticks[]，再用 tick_delta 求 idle/elapsed；:637 |
| `power-touch-boost-hold` | 5 | 直到最后一次报告后 1 s | `docs/research/power/05-BOOST-RULES.md`<br>`直到最后一次报告后 1 s` | verified | — |
| `power-frame-rule` | 5 | 最近 4 个窗口中有 2 个有 GPU 提交时 | `docs/research/power/05-BOOST-RULES.md`<br>`最近 4 个窗口中有 2 个有 GPU 提交时` | verified | — |
| `power-fence-wait` | 5 | 最长 1 ms | `docs/research/power/05-BOOST-RULES.md`<br>`最长 1 ms（gpu-pause-us）` | partial | 1 ms 睡眠预算写进了规则与 host 断言，但 fence 仍无消费者，未上机 |
| `build-interface` | 6 | 构建并验证接口 | `scripts/judge-k60-mode1-console.py`<br>`K60CpuFreq: mode=1 EPSS domains=3 cpus=8 lut-rows=40` | verified | — |
