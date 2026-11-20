# 四条线 + Power 对官网页面的逐条对齐（生成物）

由 `python3 scripts/check-lane-conformance.py --render` 生成，**不要手改**：改
`docs/research/power/LANE-CONFORMANCE.toml`。门禁核对三件事——引用的句子确实在页面上、
证据文件确实存在、非 `verified` 的行写了理由（P-259）。

页面：`docs/zh/porting/power.md`（unixnu.com/zh/porting/power）。

合计 19 行：verified 16，partial 3。

## adsp（5 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `dsp-firmware-auth` | 2 | 按目标硬件适配固件认证、预留内存和电源投票 | `drivers/PongPower/K60AdspPas.c` | partial | SMC 认证与 0x9fd00000 载入点都写进了驱动与 0613 补丁（P-255 的 clobber 契约有门禁），但没有上机：认证成功的证据只有离线语义，没有 DSP 侧回执 |
| `dsp-channel-callback` | 2 | 实现 `ShengAdspClient` 的通道状态和接收回调 | `scripts/judge-k60-handoff-console.py` | verified | — |
| `dsp-channel-name` | 2 | 通道名、接收缓冲大小和打开方向采用目标服务协议的定义 | `drivers/PongPower/K60BatteryConfig.h` | verified | — |
| `dsp-send-result` | 2 | 处理 `sheng_adsp_send` 返回值 | `drivers/PongPower/K60Battmgr.c` | verified | — |
| `dsp-channel-result` | 2 | 通道能够打开、完成一次有超时的请求/响应、报告失败并重连 | `scripts/judge-k60-handoff-console.py` | verified | 判读器七条判据（CAPTURE/CHAIN/ADOPT/CHANNEL/SAMPLE/NO-FAILURE/ORDER）已在两份真机 console 上 PASS |

## battery（6 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `battery-owner-check` | 4 | 核对 owner、消息类型、 | `scripts/check-battmgr-wire.py` | verified | — |
| `battery-one-outstanding` | 4 | 每次保留一个未完成请求 | `drivers/PongPower/K60Battmgr.c` | verified | — |
| `battery-snapshot-units` | 4 | 将以 0.01% 为单位的容量值转换为百分比 | `scripts/judge-k60-battery-mirror.py` | verified | 单位错档会被命名成 unit slip 而不是测量偏差；与 sheng 的 Linux 报告对读通过 |
| `battery-register-service` | 4 | 初始有效属性准备好后调用 `registerService()` | `scripts/judge-battery.py` | verified | — |
| `battery-firmware-ownership` | 4 | 固件负责充电控制时保留其所有权 | `docs/research/battery/PAS1-PROVIDER-CONTRACT.md` | verified | 驱动只发测量请求，不写充电寄存器；charge-auth 是独立参数且默认关闭 |
| `battery-property-numbers` | 4 | 使用前确认目标协议的单位和充电电流符号 | `docs/research/charger/PROP-NUMBERS.toml` | verified | 18 行 16→27 属性号逐行判定，全部 same |

## charger（1 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `charger-independent-protocol` | 4 | 主机控制的充电器需要独立的控制协议、限值和温控策略 | `drivers/PongPower/K60ChargeAuth.c` | partial | 协议与 HMAC（RFC 4231 向量 5 项）都在 host 侧验证过，但从未上机；18 字节的参数只能在探针镜像里飞 |

## thermal（2 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `thermal-advise` | 5 | 按规定顺序执行目标稳压器、互连和温控要求 | `drivers/PongPower/K60ThermalMap.c` | partial | 9 个 AP 温区与 6 级阶梯有 125 项 host 断言，但热证据整批不可用（capture state port-not-observed、console 0 字节），只能拒绝升档，不能证明真实触发 |
| `thermal-limits` | 1 | 时钟域、OPP 表、稳压器、固件投票和温控限制 | `docs/research/power/HW-CONTRACTS.toml` | verified | — |

## power（5 行）

| id | § | 页面要求 | 证据 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `power-epss-lut` | 5 | 读取目标 LUT、参考时钟和使能状态 | `drivers/PongPower/K60CpuFreqPlan.c` | verified | — |
| `power-governor` | 5 | 每 16 ms 读取调度器记录的各 CPU 空闲时间 | `drivers/PongPower/K60CpuFreqPlan.c` | verified | — |
| `power-sleep-resume` | 5 | 休眠/唤醒时保存所需状态，恢复时钟与映射 | `scripts/judge-k60-sleep-console.py` | verified | 11 份真机 console 上跑过；0629 的报告门控已从 defined(PONG) 改成 K60_PLATFORM_SLEEP_REPORT |
| `power-vote-ownership` | 5 | 为外设电源投票明确所有权和引用计数 | `drivers/PongPower/K60RailPlan.c` | verified | — |
| `build-interface` | 6 | 构建并验证接口 | `scripts/judge-k60-mode1-console.py` | verified | — |
