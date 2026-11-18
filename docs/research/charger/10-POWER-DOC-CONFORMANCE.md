# 10 — 电池状态上报：官网 §4 逐条对照

> 目的：把官网 `https://unixnu.com/zh/porting/power` §4「实现电池状态上报」的每个要求，落到本仓库的
> 文件、行号、测试与真机证据上；有缺口的地方必须写成缺口，不用“已覆盖”掩盖。
> 取材：官网正文抓取自 2026-11-17，本地快照 `E:/k60-work/scratch/power-page-20261117.txt:68-81`；
> 代码基线 `fix/power-doc-conformance`（从 `fix/battery-sample-dirty` 263ee626 切出）。
> 边界：本文件只描述测量值发布；充电控制仍归固件，见文末 §9。官网 §4 还附有 Sheng PD/PPS/MiPPS 充电认证与 Linux 充电读取镜像（`:82-104`），属于主机控制充电器的独立实现，本板未纳入本驱动。官网 §5「实现调频与电源操作」的 CPU EPSS/GPU 调频与 platform-sleep 同样是独立工作流：本分支的 `drivers/PongPower` 只有 ADSP Route A 的 rail ledger/lcx/lmx 投票和只读 `K60PmicRail`，没有 `CpuFreqProbe`/`ShengPlatformPower`/`GpuPowerProbe` 的 K60 实现。

## 0. 一句话结论

驱动已经具备：单请求状态机、协议五要素校验、有效/缺失/失败三态、原始值到 OS 值的显式换算、
IOPMPowerSource 子类、工作循环、三个定时器、首帧后才注册、适配器字典、断链置 stale。
2026-11-18 03:22 已构建上一版 battery-only 镜像 `E:/k60-work/artifacts/power-conformance-20261118e/boot.img`
（sha256 `8b1df0193f5e9dcc5455612fc0ec9bb070b258b1a8591dde22c6f5176a1fbcf1`，payload
`9c96ac4956151fbc1b1fdccc3cd0c3cef77b29d9a4618d6e5f3c72a3e084eb99`，kernel
`9df566917f55d7a31573457523422b706c648c629dccb66d96c581b498bcc319`），包含 `592523aa`
（缺失电池首帧）、`6750c7bd`（服务重启生命周期复位）与 `af759fe4`（容量百分比发布）；
2026-11-18 09:38 已用 `fastboot boot` 上机。
2026-11-18 11:07 构建 image f（sha256 `024466905dec75cbab5d2525f68936d6f18650a4b0d3aed6551d5ccc3df94c6e`），
包含 `0bad0c61`（剩余时间按 charging 选择 TimeToFull/TimeToEmpty）；11:13 上机，`console.log` 244,122 B，
C1/C2 PASS，C3 对同会话 3 行低电流 Android 基线 PASS（|ΔV|=46mV、|ΔSOC|=1.00pp、|ΔT|=1.00°C，
Android 侧 <100mA，电流未比较）；8 行全窗口在 11:56 符号修正后 FAIL（Android 原始
+490/+144/+107/+335/+254mA 归一化为放电，XNU 报 +397mA 充电），见 §7.9。image f 是当前最新镜像。
2026-11-18 02:42 的 image d（sha256 `9e66ef5531feaa4fc4fe6d741049980ce9cb870061bab6055a0275efa9560b00`）是上一版，包含前两项但不含容量修正。
2026-11-18 01:21 的上一版 image c 已上机：`console.log` 233,732 B，C1 PASS（`:429`、`:530`），
C2 PASS（14 次刷新命中），首帧 `:530` 发布 SOC=91.00%、4292mV、397mA、35.30°C；`:530`–`:3470`
连续 14 条完整 `physical source …` 样本证明持久刷新。C3 仍需匹配热/电状态的 Android 同窗口基线：
用 route-c 冷战基线（28.3°C）判 FAIL，只差温度 +7°C；用 01:28 暖基线判 FAIL，差电压/电流。
image e 第一次上机：`console.log` 254,167 B，C1 PASS（`:407`、`:515`），C2 PASS（12 次刷新命中）；
`:515`–`:3682` 共 12 条完整样本，全部 SOC=100.00%、4566/4566mAh、397mA、external=1、charging=1；
首帧 `:515` 为 4390mV、35.20°C。11:56 修正电流符号后，同窗口 9 行 Android 基线 FAIL：Android
原始 +516/+147/+129/+155/+225mA 归一化为放电，而 XNU 报 +397mA 充电，最大 |ΔV|=77mV、|ΔSOC|=0、
|ΔT|=1.80°C；3 行匹配电流基线同样 FAIL（原始 +516/+317/+276mA），原「C3 PASS」是未归一化的假通过。
2026-11-18 10:04–10:14 第二次 image e 上机（`controlled-final-20261118-100431`）再次得到 12 条完整样本；
36 行全窗口在符号修正后 FAIL（原始 +663/+133/+147/+169/+188mA 归一化为放电，最大 |ΔV|=91mV、
|ΔT|=0.80°C），3 行匹配基线也 FAIL（原始 +365/+343mA），原「C3 PASS」作废；详见 §7.10。
2026-11-18 10:31–10:36 第三次 image e 上机（`usblog-boot-20261118-1031`）得到 12 条完整样本，全部 SOC=99.00%、4419/4464mAh、397mA、external=1、charging=1，C1/C2 PASS；这是首次在真机看到非 100% 的容量值，为 0.01% -> 百分比转换提供实际输入，见 §7.8。
真机插拔/放电/超时/服务重启仍待完成（host 第 15 节只模拟状态转换）；服务重启生命周期复位已补（`6750c7bd`，image e 包含），
IOKit 级验证仍待完成。

## 1. §4 开头：参考实现的选择（官网 :69-74）

| 参考 | 用途 | 本仓库对应 |
| --- | --- | --- |
| `ShengBattmgr.h` / `ShengBattmgr.c` | 请求/响应格式、刷新状态机、单位转换 | `drivers/PongPower/K60Battmgr.h`、`K60Battmgr.c`；协议字段来自 m81.ko 反编译，见 `docs/research/charger/02-GLINK-CONTRACT.md`、`04-PROP-MAP.md` |
| `ShengBattery.cpp` | IOPMPowerSource 属性、工作循环、计时器、通知 | `drivers/PongPower/K60Battery.cpp` |
| `BatteryProbe.cpp` | 类注册与服务启动 | `K60Battery.cpp:505` `k60_physical_battery_start()`，由 `patches/xnu/0602-k60-physical-battery.patch` 在 `IOService::publishResource("IOBSD")` 后调用 |
| XNU `IOPMPowerSource.h` | 属性设置与状态发布 API | 继承 `IOPMPowerSource`（`K60Battery.cpp:53`），使用 `setPSProperty` / `updateStatus` / `registerService` |
| Linux `qcom_battmgr.c` | Qualcomm 协议变体与属性处理 | 只作为协议对照；K60 的 owner=32778、opcode/property 映射以本机 m81.ko 为准（`K60Battmgr.c:23-30`） |

## 2. §4 第一段：协议校验、单请求、超时（官网 :75）

### 2.1 五要素校验（owner / 消息类型 / opcode / 属性 ID / 响应长度）

全部在 `K60Battmgr.c:159-198` 的 `k60_battmgr_receive()`：

| 要素 | 校验 | 失败后果 |
| --- | --- | --- |
| owner | `le32(data) == K60_BATTMGR_OWNER`（32778，`K60Battmgr.h:12`） | `ignored++`，返回 `K60BmIgnored`（`:161`） |
| 消息类型 | 通知要求 `TYPE_NOTIFY`；属性应答要求 `TYPE_REQUEST` | `ignored++`（`:164`、`:184`） |
| opcode | 通知须 `OP_NOTIFY`；订阅应答须 `OP_NOTIFY_ENABLE`；属性应答须匹配当前 `fields[cursor].opcode` | `ignored++`（`:163`、`:174`、`:184`） |
| 属性 ID | 属性应答 `le32(data+12) == fields[cursor].property` | `ignored++`（`:184-185`） |
| 响应长度 | 属性应答 24 B；model 应答 16+128 B；通知 16 B；订阅应答必须等于配置的 `notify_reply_bytes` 且类型匹配 | `ignored++` 或 `errors++`（`:164`、`:177-178`、`:189`、`:195`） |

补充：`value_valid()`（`K60Battmgr.c:107-125`）对每个字段做物理范围校验；越界值走
`:199-203` 的失败分支：清 `valid` 位、置 `failed` 位、`errors++`。model 为空、含不可打印字符或
等于 `Debug_Board` 时也拒绝（`:126-139`）。

### 2.2 每次只有一个未完成请求

- `k60_battmgr_next()` 在 `b->flight != 0` 时直接返回 0（`K60Battmgr.c:76-91`）。
- 请求发出成功后 `k60_battmgr_sent()` 才设置 `flight`（`:92-97`），FIFO 背压时由 `K60Battery.cpp:333-336` 重试，未写入不算已发。
- 收到匹配应答后 `finish_field()` 清 `flight` 并把 cursor 推进（`:140-157`）。

### 2.3 超时后才推进刷新周期

- 每个请求由 `requestTimer` 计时（`K60Battery.cpp:341` 设置 `kRequestMs=3000`，`:25`）。
- `requestAction()`（`K60Battery.cpp:407-419`）打印超时行后调用 `k60_battmgr_timeout()`：
  `timeouts++`、`poisoned=1`、清 `valid/fresh/completed/last_fresh`（`K60Battmgr.c:206-213`）。
- 其后必须 `transport.reopen()` 才继续（`K60Battery.cpp:418`）；`pump()` 在 `poisoned` 时不发请求（`:329`）。
  这保证迟到的旧应答不可能满足下一轮的同一属性（`K60Battmgr.h:78-81` 注释）。

## 3. §4 第二段：有效/缺失/失败三态与快照（官网 :76）

### 3.1 三态分离

`K60Battmgr` 有 `valid`、`fresh`、`completed`、`last_fresh`、`last_completed`、`failed` 六个位图
（`K60Battmgr.h:31-42`）。每条属性应答只会进入三种结局之一：

| 结局 | 条件 | 位图变化 |
| --- | --- | --- |
| 有效 | `result==0` 且 `value_valid()` | `valid|=BIT`、`fresh|=BIT`、`completed|=BIT`（`K60Battmgr.c:199-200`） |
| 失败 | 远端非 0 或值越界 | `valid&=~BIT`、`failed|=BIT`、`errors++`（`:201-202`） |
| 未完成/缺失 | 本轮未收到该属性的应答 | `completed` 无该位；超时时 `failed` 补上未完成位（`:210`） |

快照结构 `K60BatterySample`（`K60Battmgr.h:50-62`）同时携带：
`valid`（本轮有效位）、`failed`（本轮失败位）、`raw[K60BmFields]`（原始线值），以及全部 OS 值。
`k60_battmgr_sample()` 在正常路径（`K60Battmgr.c:230-282`）和电池缺失路径（`:224-229`）都复制
`s->valid = b->last_fresh; s->failed = b->failed; s->raw[i] = b->value[i]`，所以 OS 侧可以同时回答
“哪些值有效、哪些失败了、原始值是多少”。

`publish()` 的缺失电池分支（`K60Battery.cpp:163-191`）也调用 `rawNumbers(s)`，因此
`K60BatteryFailedFields` 和全部 `K60Raw*` 在电池缺失时同样可见；有效位图仍由
`K60BatteryValidFields` 携带。

### 3.2 快照字段（官网要求的存在/外接/充电/容量/电压/电流/温度/剩余时间）

| 官网字段 | `K60BatterySample` 成员 | 发布键 | 代码 |
| --- | --- | --- | --- |
| 电池存在 | `present` | `kIOPMBatteryInstalledKey`（`setBatteryInstalled`） | `K60Battery.cpp:225` |
| 外接电源 | `external` | `kIOPMPSExternalConnectedKey` | `:226` |
| 充电状态 | `charging` | `kIOPMPSIsChargingKey` | `:226` |
| 容量 | `capacity_hundredths` / `current_mah` | `kIOPMPSCurrentCapacityKey`（百分比）/ `K60CapacityHundredths`（0.01%）/ `AppleRawCurrentCapacity`（mAh）/ `K60CurrentCapacityBasis`（来源说明） | `:192,196,203,231` |
| 满充/设计容量 | `full_mah` / `design_mah` | `kIOPMPSMaxCapacityKey`（固定 100%）/ `AppleRawMaxCapacity` / `NominalChargeCapacity` / `DesignCapacity` | `:192,196,203` |
| 电压 | `voltage_mv` | `kIOPMPSVoltageKey` | `:192` |
| 电流 | `current_ma` / `current_source` | `kIOPMPSAmperageKey` / `InstantAmperage` | `:193,195,230` |
| 温度 | `temperature_hundredths` | `kIOPMPSBatteryTemperatureKey` | `:195` |
| 剩余时间 | `time_remaining_min` | `kIOPMPSTimeRemainingKey` | `:194` |
| 循环次数 | `cycles` | `kIOPMPSCycleCountKey` | `:193` |
| 适配器 | `adapter_mv/ma/type` | `kIOPMPSAdapterDetailsKey` 字典 | `:291-326` |

### 3.3 原始值 → OS 值换算（含发布出来的 raw 键）

| 字段 | 原始单位（ADSP） | OS 值 | 换算 | 代码 |
| --- | --- | --- | --- | --- |
| 容量百分比 | 0.01%（`K60BmCapacity`） | `CurrentCapacity` 百分比；`K60CapacityHundredths` 保持 0.01%；`AppleRawCurrentCapacity` 为估算 mAh | `percent = (capacity_hundredths + 50) / 100`，钳位 0..100；`capacity_hundredths = raw`；`current_mah = (SOC_hundredths × full_uAh + 5,000,000) / 10,000,000`，上限 `full_mah` | `K60Battmgr.c:248-253`、`K60Battery.cpp:44-51,192,203` |
| 满充/设计容量 | µAh | `AppleRawMaxCapacity`/`NominalChargeCapacity` mAh；`MaxCapacity` 固定 100% | `/1000` | `:249`、`K60Battery.cpp:192,196,203` |
| 电压 | µV | mV | `/1000` | `:254` |
| 电流 | µA（带符号） | mA | `charging_current_sign × raw/1000`；无电池电流时，充电中外接电源用 USB 电流 `raw/1000` | `:255-265` |
| 温度 | 0.01 °C | 0.01 °C（IOPMPowerSource 约定） | 原样保留 | `:267` |
| 剩余时间 | 秒 | 分钟 | 充电中取 `TimeToFull`，否则取 `TimeToEmpty`；`/60`；`0xffff` 或无值 → `-1` → 发布为 `0xffff`（unknown） | `:268-272`、`K60Battery.cpp:194` |
| 适配器电压/最大电流 | µV / µA | mV / mA | `/1000`；输入限流取二者较小值 | `:273-278` |
| 适配器功率 | — | W | `mV × mA / 1,000,000` | `K60Battery.cpp:300` |

电池 `CURRENT_NOW`（属性 9）在该 ADSP 上不应答；`K60Battmgr.c:144-147` 直接跳过该字段，因为一次超时会毒化整个 channel epoch。
因此充电中的 `current_ma` 只能取 USB 输入电流（`:256-261`），放电中为 0；这不是固定值顶替，而是本板唯一可读的充电电流。

原始值本身也发布为 `K60Raw*` 属性（`K60Battery.cpp:111-116` 声明，`:261-276` `rawNumbers()` 赋值；缺失分支在 `:170` 调用）：
`K60RawStatus`、`K60RawCapacityHundredths`、`K60RawVoltageMicrovolts`、`K60RawCurrentMicroamps`、
`K60RawTemperatureHundredths`、`K60RawFullChargeMicroampHours`、`K60RawDesignChargeMicroampHours`、
`K60RawUsbVoltageMicrovolts`、`K60RawUsbCurrentMicroamps`、`K60RawTimeToFullSeconds`、
`K60RawTimeToEmptySeconds`、`K60RawUsbAdapter`。失败位图发布为 `K60BatteryFailedFields`（`:263`），
与 `K60BatteryValidFields` 配对，满足“有效读数与缺失/失败状态分开保存”。

### 3.4 充电电流符号

`charging_current_sign` 来自板级配置，只接受 `+1` / `-1` / `0`（`K60Battmgr.c:48-57`）。
Route-c 真机行的 `measured sign=-1`（`console.log:401`）与充电中 `current=397mA` 正号
（`:534`，status=1、external=1）一致，说明“放电为正”的线序已被取反为 OS 的“充电为正”。
样本层还有两道一致性拒绝：status=2（放电）不允许正电流，status=1（充电）不允许负电流
（`K60Battmgr.c:266`）。

## 4. §4 第三段：IOPMPowerSource、工作循环、响应队列、计时器（官网 :77）

- 类声明：`class K60Battery : public IOPMPowerSource`（`K60Battery.cpp:53`）。`begin()` 在
  `:429-437` 重置 `stopped`/`published`/`up`/`waitingSince`/`lastRefreshLog`/`publishFailed`，再调
  `IOPMPowerSource::start(provider)`（`:438`）；同一对象 stop/start 不会因旧状态保持静默。
- 工作循环：`IOWorkLoop::workLoop()`（`:442`）；所有 GLINK 回调、定时器动作都在该 loop 上执行。
- 响应队列：GLINK 的 `receive` 回调只把数据交给 `k60_battmgr_receive()`，不在回调里发下一笔；
  `K60Battery.cpp:379-380` 注释明确要求先把 RX_DONE 放回 FIFO，再由 `pollAction` 的 `pump()` 发送。
- 计时器：`pollTimer`（20 ms，`kPollMs`）、`requestTimer`（3000 ms，`kRequestMs`）、
  `refreshTimer`（5000 ms，`kRefreshMs`）均在 `:443-445` 创建、`:447-452` 加入 loop；
  `shutdownAction` 在 `:462-471` 取消三个定时器并关闭 transport。
- 解码器只在快照完整后更新属性：`receive()` 收到 `K60BmCycleDone` 才调用 `k60_battmgr_sample()`，
  成功才 `publish()`（`:364-368`）。

## 5. §4 第四段：registerService、updateStatus、一致性、适配器（官网 :78）

### 5.1 首帧有效属性后才注册

`publish()` 只在 `k60_battmgr_sample()` 返回 1 时被调用；在注册之前，所有属性已经通过
`setPSProperty` 写入（`K60Battery.cpp:213-231`），然后：

1. `updateStatus()`（`:235`）把属性字典复制到电源源快照；
2. `if (settingsChangedSinceUpdate) return;`（`:236`）——复制失败则不暴露半套初始属性；
3. 首次成功才走 `registerSource()`（`:277-290`）：`registerService()` 后用 `isInactive()` 检查是否真的生效；
   未生效则清 `published` 并打印 `registerService left the source inactive; retrying on the next sample`
   （`:286`），下一次有效样本会重试。正常路径的调用点是 `:237`；缺失电池分支在 `:188` 也调用同一函数。

### 5.2 后续变化 updateStatus

每一帧合格样本都会重新设置属性并调用 `updateStatus()`（`:213-237`）；`IOPMPowerSource::updateStatus()`
只在 `settingsChangedSinceUpdate` 为真时通知客户端（XNU `iokit/Kernel/IOPMPowerSource.cpp:174`），
避免无变化刷新风暴。变化日志只在外部/充电/满/容量变化时打印（`:238-246`）。

### 5.3 存在/外接/充电与容量、测量值一致

- `present=1` 走正常发布；无电池走 `setBatteryInstalled(false)`、保留 stale，并同样发布
  `K60BatteryFailedFields`/`K60Raw*` 诊断属性和注册服务（`:163-191`）。
- `external = usb || wireless`（`K60Battmgr.c:241`）；`charging = external && status==1`、`full = external && status==4`（`K60Battmgr.c:243`）。
- `status==1 && !external` 直接拒绝样本（`K60Battmgr.c:244`）；满充/设计容量比值必须在 [0.5, 1.5]（`K60Battmgr.c:233-234`）。
- 容量与测量值同帧来自同一 `K60BatterySample`，不存在跨帧拼接。

### 5.4 适配器信息

`updateAdapter()`（`K60Battery.cpp:291-326`）填 family / voltage / amperage / watts 四项；
family 映射见 `:33-43`。USB 已连接但 adapter type 缺失时仍填 `kIOPSFamilyCodeUSBUnknown`，不丢整个字典
（`:303-308`）；未外接时只填 disconnected family（`:302`）。可选失败字段不填 0 瓦假事实（`:293-295` 注释）。

## 6. §4 第五段：订阅通知、周期刷新、断链 stale（官网 :79）

- 订阅：`k60_battmgr_channel_up()` 在配置了非零 `notify_reply_bytes` 时置 `subscribe_due`
  （`K60Battmgr.c:64-69`）；`next()` 生成 type2/op4 请求（`:81-86`）；只有收到类型/长度匹配且
  data[12..] 全 0 的应答才 `subscribed=1`（`:174-182`）。
- 通知：`OP_NOTIFY` 只接受 type2/16 B 和四个已知 property group（`:163-172`），置 `sample_dirty` 并触发刷新。
- 周期刷新：`refreshTimer` 每 5000 ms 调 `k60_battmgr_refresh()`（`K60Battery.cpp:420-426`）；
  `k60_battmgr_refresh()` 在周期/请求进行中只置 `refresh_due`，完成后由 `receive()` 补下一轮
  （`K60Battmgr.c:70-75`、`K60Battery.cpp:377`）。
- 传输断开：`pollAction()` 检测 `transport.poll() < 0 || !alive()` 时取消两个定时器、打印
  `physical transport stopped error=%d; no DSP/FIFO reset`（`:382-390`）；通道 down 回调和握手超时也走
  `stale()`（`:354-358`、`:392-397`）。`stale()` 保留最后测量值并置 `K60BatteryStale=true`（`:152-159`）。

## 7. §4 第六段：原始对照、插拔/充放电/超时/服务重启（官网 :80）

### 7.1 原始读数与发布属性对照

原始值通过 `K60Raw*` 属性（§3.3）直接可见；OS 值通过标准 IOPMPowerSource 键可见。对照表就是 §3.3，
两边使用同一个 `K60BatterySample` 的 `raw[]` 和转换后字段，不存在二次采样。

### 7.2 已验证 / 待验证矩阵

| 验证项 | 状态 | 证据 / 缺口 |
| --- | --- | --- |
| 协议响应 | 已验证 | Route-c 真机：`console.log:189` adopting、`:401` channel up、`:534` 首帧、`:761` 第二帧；image c：`:429` channel up、`:530` 首帧；image e：`:407` channel up、`:515` 首帧，第三次 image e：`:401` channel up、`:465` 首帧；host 测试 95 项覆盖应答/拒绝/超时 |
| 有效 / 缺失 / 失败三态 | 已验证 | `K60BatteryValidFields` 与 `K60BatteryFailedFields` 分别给出本轮有效和失败字段，缺失 pack 走 `K60Battery.cpp:163-191` 的独立分支并保留 `K60Raw*`；host 第 11–13 节覆盖原始值、缺失样本和超时位图；第 16 节覆盖缺失 pack 的 external 快照 |
| OS 可见更新 | 已验证 | Route-c `:534` `physical source published`、`:761` `physical source updated`；image c `:530` 发布后 `:753`–`:3470` 连续 14 条刷新/更新，`:3464` SOC 由 91.00% 变为 90.00%；image e `:515`–`:3682` 连续 12 条完整样本；第三次 image e `:465`–`:3577` 连续 12 条完整样本；字段值与原始值换算一致（见 §7.3、§7.4、§7.6、§7.8） |
| 状态一致性与适配器 | 已验证 | 同一样本在 `K60Battery.cpp:225-231` 设置 installed/external/charging/full/warn/critical；`K60Battmgr.c:244` 拒绝 status=1 无外接、`:263` 拒绝 status=2 正电流；适配器 family/电压/电流/瓦数由 `K60Battery.cpp:291-326` 生成，失败字段保持缺失，不发布 0 瓦；第 16 节覆盖容量/满充一致性、mAh 估算与适配器限流 |
| 响应超时 | host 已验证 | `test-k60-charger-subscription.c` 第 13 节：timeout 只标记未完成字段，poisoned epoch 生效；真机未制造超时 |
| 缺失电池首帧 | 代码已实现 / host 部分 | `K60Battery.cpp:163-191`：首帧 `present=0` 也发布 `K60BatteryFailedFields`/`K60Raw*` 并调用 `registerSource()`；第 12 节覆盖缺失样本的 raw USB 电压与 failed 位，最终 image e/f 已包含该修复，IOKit 级 absent 注册未上真机 |
| 插拔电源 | host 状态机已验证 / 真机未验证 | 第 15 节构造 USB 在线 1→0 与 status 1→2，断言 `external`/`charging`/`usb_connected` 翻转；真机脚本化插拔仍需要人工在同一次 usblog 里观察 |
| 充放电 | host 状态机已验证 / 真机未验证 | 第 15 节覆盖 status 1 充电、status 2 放电、status 4 full、status 1 无外接拒绝、status 2 正电流拒绝；Android 侧实际充电/放电段未采样 |
| 服务重启 | host 部分验证 / 代码路径补齐 | 第 14 节“transport restart drops and republishes”验证 manager 重新 channel_up 后会丢弃旧 epoch 并重发；`begin()` 在 `K60Battery.cpp:429-437` 清除 `stopped`/`published` 等生命周期状态后再 `start`（commit `6750c7bd`，已包含在 image e/f），IOKit 级 stop/start 未在真机执行 |
| 订阅 / 周期刷新 / 断链 stale | 已验证（断链真机未制造） | 订阅请求与 in-flight `K60Battmgr.c:81-85`/`:95`、通知 `:163-172`、应答校验与 `subscribed` 置位 `:174-182`；5 s 刷新 `K60Battery.cpp:420-426`；`transport.poll()<0` 取消定时器并 `stale()` `:382-397`，通道 down `:354-358`；`stale()` 保留最后值并置 `K60BatteryStale=true` `:152-159` |
| 与 OEM/目标电量计逐项对照 | 部分（仅低电流 3 对 PASS） | image f 11:13 的同会话 3 行低电流基线 PASS（`judge-android.txt`：|ΔV|=46mV/±60mV、|ΔSOC|=1.00pp/±3pp、|ΔT|=1.00C/±3C；Android 侧 <100mA，电流未比较）；11:47 的 13 对匹配电流窗口归一化后 |ΔI|=29mA/±150mA，但 |ΔV|=119mV/±60mV，C3 FAIL；image e 两个匹配窗口在 11:56 符号修正后均 FAIL，旧 PASS 作废（§7.10） |
| 固件充电所有权 | 边界已确认 | 驱动只发布测量值，不写充电器、不改限流、不做 PD/PPS 认证（§9 与官网 :81）；主机控制充电需要单独的 `ShengChargeAuth.c` 等价工作流 |

### 7.3 Route-c 实测数值（2026-11-17 23:18 boot）

- 首帧 `console.log:534`：SOC=89.00%、charge=4078/4582mAh、design=5500mAh、cycles=749、
  voltage=4217mV、current=397mA（current-source=usb）、temp=28.80°C、external=1、charging=1、full=0、subscribed=1。
- 第二帧 `console.log:761`：SOC=88.00%、charge=4032/4582mAh、voltage=4211mV、current=397mA、temp=28.80°C。
- 换算核对：`4217 mV = 4217000 µV / 1000`；`397 mA = 397000 µA / 1000`；
  `89.00% = 8900 × 0.01%`；`4078 mAh ≈ 8900 × 4582 / 10000`（四舍五入误差在 1 mAh 内）。
- `judge-battery.py` 结果：C1 PASS（`:401,:534`）、C2 PASS（`:534,:761`）、
  C3 INVALID（只有 2 对，阈值 `MIN_PAIRS=3`，`judge-battery.py:107`）。报告 `E:/k60-work/scratch/judge-routec.txt`。

### 7.4 Conformance image c 实测（2026-11-18 01:21 boot）

镜像 `E:/k60-work/artifacts/power-conformance-20261118c/boot.img`（sha256
`f0869f889f34425a36ed0a20d15fe80fa0b0d51cac3c2e65ef511e95908b049d`），console
`E:/k60-work/evidence/power-conformance/usblog-boot-20261118-0120/console.log`（233,732 B）。

- 启动链：`:127` board ownership init rc=0、`:128` installed rc=0、`:130` platform install
  rc=0 carrier_rc=0、`:143` Route A resources held、`:188` published authenticated PAS1
  epoch=1 flags=15、`:189` K60Battery adopting、`:429` actual PMIC_RTR_ADSP_APPS channel up
  measured sign=-1、`:530` 首帧。
- 连续完整样本（同一行格式，均含 `physical source published|updated|refreshed`）：

| sample | 行 | SOC | voltage | current | temp |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `:530` | 91.00% | 4292 mV | 397 mA | 35.30°C |
| 7 | `:753` | 91.00% | 4255 mV | 397 mA | 35.10°C |
| 13 | `:775` | 91.00% | 4255 mV | 397 mA | 35.10°C |
| 19 | `:1345` | 91.00% | 4226 mV | 397 mA | 35.30°C |
| 25 | `:2099` | 91.00% | 4246 mV | 397 mA | 35.50°C |
| 31 | `:2567` | 91.00% | 4261 mV | 397 mA | 36.00°C |
| 37 | `:2687` | 91.00% | 4263 mV | 397 mA | 36.00°C |
| 43 | `:2925` | 91.00% | 4264 mV | 397 mA | 36.00°C |
| 49 | `:3106` | 91.00% | 4261 mV | 397 mA | 36.00°C |
| 55 | `:3181` | 91.00% | 4264 mV | 397 mA | 35.90°C |
| 61 | `:3305` | 91.00% | 4262 mV | 397 mA | 35.90°C |
| 67 | `:3404` | 91.00% | 4262 mV | 397 mA | 35.90°C |
| 72 | `:3464` | 90.00% | 4261 mV | 397 mA | 35.80°C |
| 73 | `:3470` | 90.00% | 4260 mV | 397 mA | 35.80°C |

- `judge-battery.py`（`--window-start 1794927869 --window-end 1794927891`，route-c 冷战 Android
  基线 28.3°C）：C1 PASS（`:429,:530`）、C2 PASS（14 hits）、C3 FAIL，仅温度超差
  ΔT=+7.00/+6.80/+7.00/+7.20°C（阈值 ±3°C），|ΔV|≤51mV、|ΔSOC|≤2.00pp；报告
  `E:/k60-work/scratch/judge-conformance-0120.txt`。
- 同一日志改用 route-c dmesg 窗口 `16447–16652`（122 行，28.2–29.2°C）：C1/C2 PASS、C3 FAIL，
  8 对全部仅温度超差 ΔT=+6.40~+7.30°C（|ΔV|=53mV/±60、|ΔSOC|=3.00pp/±3，电流跳过），报告
  `E:/k60-work/scratch/judge-conformance-0120-dmesg.txt`。
- 同一日志改用 2026-11-18 01:28 暖 Android 基线（36.3–37.0°C）判：C1/C2 PASS，C3 FAIL，
  `:530` ΔV=78mV/±60、ΔI=-384mA/±150，后续 `:753`/`:775` ΔI=-462/-616mA；报告
  `E:/k60-work/scratch/judge-conformance-0128b.txt`。结论：XNU 侧已有 14 条完整样本，C3
  缺的是同窗口、同温度/电压/电流量级的真实 Android 基线，而不是 XNU 样本数量。

### 7.5 image d 构建（2026-11-18 02:42，未上机）

- `E:/k60-work/artifacts/power-conformance-20261118d/boot.img` 201,887,744 B，sha256
  `9e66ef5531feaa4fc4fe6d741049980ce9cb870061bab6055a0275efa9560b00`；payload
  `0f23f3675efe1df8c45a66833272f88d901bb747c5405e862c0505fe96924749`（201,326,592 B）；
  kernel `7cafead24179a329178ff65e11ea6dfa18ffdab0ecd1e7081946c5eddbab7742`（129,077,248 B）。
- 由 `fix/power-doc-conformance` `8e6031eb` 构建，battery archive
  `b5e35df60af92401dc60bb891a85c82081e5e38949655d8889b000aa45800748`；
  `check-image-args.py` = `image-arg-audit: OK (30 arguments, 598 bytes)`，payload 内核参数含
  `pong_handoff_publish=1`；`verify-boot-img-payload.py` OK（payload sha `0f23...`，
  payload kernel probe-patched，payload.json kernel `7caf...`）。
- `strings` 验证内核含 `K60BatteryFailedFields`、`K60RawStatus`、`K60RawVoltageMicrovolts`、
  `K60RawCurrentMicroamps`、`K60RawUsbAdapter`、`registerService left the source inactive`、
  `physical source refreshed`。
- 该镜像尚未上机；C3、插拔、放电与服务重启仍未获得新证据。

### 7.6 最终 image e 构建与上机（2026-11-18 03:22 构建，09:38 上机）

- `E:/k60-work/artifacts/power-conformance-20261118e/boot.img` 201,887,744 B，sha256
  `8b1df0193f5e9dcc5455612fc0ec9bb070b258b1a8591dde22c6f5176a1fbcf1`；payload
  `9c96ac4956151fbc1b1fdccc3cd0c3cef77b29d9a4618d6e5f3c72a3e084eb99`（201,326,592 B）；
  kernel `9df566917f55d7a31573457523422b706c648c629dccb66d96c581b498bcc319`（129,077,248 B）。
- 构建树为 `fix/battery-sample-dirty-build` `1a64347f`（含 `592523aa`/`6750c7bd`）；battery archive
  由 `fix/power-doc-conformance` `845f439b`（含 `af759fe4` 容量百分比）编译后注入，
  `11e4da65586b183e117127083350c1021732d0b7d8f6e5fa8b83bf4a034ef804`（116,960 B）；
  `check-image-args.py` = `image-arg-audit: OK (30 arguments, 598 bytes)`，payload 内核参数含
  `pong_handoff_publish=1`；`verify-boot-img-payload.py` OK（payload sha `9c96ac...`，
  payload kernel probe-patched `e92b0660cc27be67...`，payload.json kernel `9df566...`）。
- `strings` 验证内核含 `K60BatteryFailedFields`、`K60RawVoltageMicrovolts`、
  `AppleRawCurrentCapacity`、`AppleRawMaxCapacity`、`registerService left the source inactive`、
  `physical source refreshed`。
- 2026-11-18 09:38:44 已用 `fastboot boot` 上机：boot.json 记录 `bootAccepted=true`、`bootExitCode=0`；
  `console.log` 254,167 B、`complete=true`、logSha256 `B13B63F04FB13D7F8D28873BA4954E125EF7F589A9B36E220FF8855CB8106763`。
  C1 PASS（`:407`、`:515`），C2 PASS（12 次命中）。
- 上机样本（均 SOC=100.00%、4566/4566mAh、397mA、current-source=usb、external=1、charging=1、full=0、subscribed=1）：
  `:515` s1 4390mV 35.20°C；`:665` s7 4359mV 35.30°C；`:775` s13 4353mV 35.30°C；
  `:1297` s19 4322mV 35.30°C；`:2225` s25 4349mV 35.50°C；`:2693` s31 4362mV 35.90°C；
  `:2902` s37 4359mV 36.00°C；`:3128` s43 4360mV 35.90°C；`:3304` s49 4356mV 35.70°C；
  `:3477` s55 4355mV 35.60°C；`:3589` s61 4354mV 35.50°C；`:3682` s67 4356mV 35.50°C。
- C3 对同窗口 9 行 Android 基线：11:56 电流符号修正后 FAIL。Android 原始
  +516/+147/+129/+155/+225mA 按 negative=charging 归一化为放电，XNU 报 +397mA 充电，出现符号相反；
  最大 |ΔV|=77mV、|ΔSOC|=0、|ΔT|=1.80°C（报告 `sign-audit-20261118-1156/imagee-first-full9.txt`）。
  同会话 3 行匹配电流基线 `android-matched3.tsv`（1794965733 4347mV/516mA、1794965769 4379mV/317mA、
  1794965775 4369mV/276mA）同样因三对符号相反 FAIL；最大 |ΔV|=43mV、|ΔSOC|=0、|ΔT|=1.10°C
  （报告 `sign-audit-20261118-1156/imagee-first-matched3.txt`）。旧 `judge-android-matched3.txt` 的 PASS 作废。
  旧 route-c dmesg 窗口 16447–16652 仍因冷战基线（ΔSOC +12pp、ΔT +7.3°C）判 FAIL，不是同状态基线。
- 该镜像的插拔、放电、超时与服务重启仍未获得真机脚本化证据；第 15 节只证明 manager 对待发布样本的状态转换，不代替真机插拔。

### 7.7 第二次 image e 上机与匹配 C3（2026-11-18 10:04–10:14）

- controller 输出 `E:/k60-work/evidence/power-conformance/controlled-final-20261118-100431`；日志
  `E:/k60-work/scratch/controlled-final-image-e.log`。fastboot 预采只有 `battery-voltage: 4393`（10:08 为 4394），
  `battery-current`/`battery-soc`/`battery-temperature` 均 `FAILED (remote: 'GetVar Variable Not found')`，
  所以没有可用的 OEM 电流/SOC/温度基线。
- Android 基线 `android-data.tsv` 36 行（epoch 1794967492–1794967691）：SOC 100%、电压 4249–4417mV、
  电流 -453–1525mA、温度 35.10–36.40°C、status=2（充电）。
- image e `console.log` 260,551 B，C1 PASS（`:488`、`:538`），C2 PASS（12 次命中）；首帧 `:538`
  为 4366mV、397mA、SOC=100.00%、35.60°C；12 条完整样本均 SOC=100.00%、4464/4464mAh、397mA、
  external=1、charging=1、full=0。
- 全 36 行窗口在 11:56 符号修正后 FAIL：Android 原始 +663/+133/+147/+169/+188mA 归一化为放电，
  XNU 报 +397mA 充电，出现符号相反；最大 |ΔV|=91mV/±60mV、|ΔSOC|=0、|ΔT|=0.80°C
  （报告 `sign-audit-20261118-1156/imagee-second-full36.txt`）。旧 route-c dmesg 窗口（16447–16652）
  仍因 ΔSOC +12pp、ΔT +6.7~7.6°C 判 FAIL，是冷基线状态不匹配。
- 同会话匹配电流 3 行基线 `android-matched3.tsv`（1794967527 4351mV/365mA/100%/35.50°C、
  1794967533 4353mV/343mA/100%/35.50°C、1794967573 4362mV/63mA/100%/36.00°C）在符号修正后 FAIL：
  前两对原始 +365/+343mA 归一化为放电，与 XNU +397mA 充电相反；第三对 63mA 低于 100mA 未比较。
  最大 |ΔV|=43mV、|ΔSOC|=0、|ΔT|=0.60°C（报告 `sign-audit-20261118-1156/imagee-matched3.txt`）。
  旧 `judge-android-matched3.txt` 的 PASS 作废。
- 结论：11:56 之前的 image e 匹配电流 C3 PASS 都是未归一化 Android 电流符号造成的假通过；本轮没有代码改动，
  符号修正与复核见 §7.10。

### 7.8 第三次 image e 上机与 99% 容量（2026-11-18 10:31–10:36）

- 设备处于 fastboot 且没有其他 boot watcher（用户规则 m08099）时直接 `fastboot boot` image e；证据
  `E:/k60-work/evidence/power-conformance/usblog-boot-20261118-1031`，`boot.json` 记录
  startedAt 10:31:11、bootAccepted true、bootExitCode 0、finishedAt 10:36:36，`console.log` 237,388 B。
- C1 PASS（`:401` channel up、`:465` 首帧）、C2 PASS（12 次刷新命中，报告 `judge-c1c2.txt`）；`:465`–`:3577` 共 12 条完整样本，
  全部 SOC=99.00%、charge=4419/4464mAh、design=5500mAh、cycles=750、397mA、external=1、charging=1、
  full=0；首帧 4350mV/35.50°C，后续 4284–4324mV/35.70–36.50°C；`:3583` 为 `K60AUTORESET` 300 s。
- 这是第一次在真机看到非 100% 的容量值（`SOC=99.00%`），为 0.01% -> 百分比转换提供实际输入；
  `CurrentCapacity` 的最终用户态值仍由 `K60BatterySmoke` 的主机检查覆盖（`capacity(9900)=99`），没有单独抓取 IORegistry。
- 该次没有 Android 同窗口基线，不用于 C3 判定；§7.7 的匹配电流 3 行 PASS 已在 11:56 符号修正后作废，见 §7.10。

### 7.9 最终 image f 构建与上机（2026-11-18 11:07 构建，11:13 上机）

- `E:/k60-work/artifacts/power-conformance-20261118f/boot.img` 201,887,744 B，sha256
  `024466905dec75cbab5d2525f68936d6f18650a4b0d3aed6551d5ccc3df94c6e`；payload
  `8949e8ef0d3321602535685925f64c648df340902449fc54c4c69c0431c2e43b`（201,326,592 B）；
  kernel `d8ee7d8eebdb2907b3dc121767f88c0e2a6b75eedeef4d21b5d9a13b0139e1e4`（129,077,248 B）。
- 构建树 `fix/battery-sample-dirty-build` `1a64347f`；battery archive 由 `fix/power-doc-conformance`
  当前源（含 `0bad0c61` 剩余时间选择）编译后注入，
  `fa46b01a8d35703a9c950df5a06ecfa529da747b2ace2be3ec5eeb4fd9553b4c`（116,960 B）。
  `check-image-args.py` = `image-arg-audit: OK (30 arguments, 598 bytes)`，payload 内核参数含
  `pong_handoff_publish=1`；`verify-boot-img-payload.py` OK（payload @557056，payload kernel probe-patched
  `e20a9c2b043f693d...`，payload.json kernel `d8ee7d8...`，FD `cf4485712c2999c1...`）。
- `strings` 验证内核含 `K60BatteryFailedFields`、`K60RawVoltageMicrovolts`、
  `AppleRawCurrentCapacity`、`AppleRawMaxCapacity`、`registerService left the source inactive`、
  `physical source refreshed`。
- 2026-11-18 11:13:50 `fastboot boot` 上机（controller `controlled-final-20261118-111022`，
  日志 `E:/k60-work/scratch/controlled-final-image-f.log`）：boot 记录 `Booting OKAY`，
  `console.log` 244,122 B、`complete=true`、`K60AUTORESET` 300 s 后发布 `restart reason published`。
  C1 PASS（`:436` channel up、`:490` 首帧），C2 PASS（12 次刷新命中，`:490`、`:665`、`:751`）。
- 上机样本（均 SOC=98.00%、4375/4464mAh、design=5500mAh、cycles=750、397mA、current-source=usb、
  external=1、charging=1、full=0、subscribed=1）：`:490` s1 4344mV 35.80°C；`:665` s7 4314mV 35.70°C；
  `:751` s13 4310mV 35.70°C；`:1297` s19 4293mV 35.70°C；`:2156` s25 4306mV 36.00°C；
  `:2609` s31 4271mV 36.00°C；`:2827` s37 4323mV 36.10°C；`:3051` s43 4323mV 36.30°C；
  `:3218` s49 4321mV 36.10°C；`:3387` s55 4320mV 36.10°C；`:3466` s61 4321mV 35.90°C；
  `:3563` s67 4323mV 35.80°C。
- 同会话 Android 基线 `android-samples.tsv` 8 行（epoch 1794971442–1794971483，SOC 99%，
  4319–4360mV，电流 0–490mA，34.8–35.0°C，status=2）；取连续 3 行低电流窗口
  `android-low.tsv`（1794971448 4359mV/11mA、1794971453 4360mV/0mA、1794971459 4352mV/92mA）
  判 C3：PASS 3 对，最大 |ΔV|=46mV/±60mV、|ΔSOC|=1.00pp/±3pp、|ΔT|=1.00C/±3C；
  |ΔI| 未比较（两侧没有同时 ≥100mA 的稳态窗口），报告 `judge-android.txt`。
- 全 8 行窗口在 11:56 符号修正后仍 FAIL：Android 原始 +490/+144/+107/+335/+254mA 归一化为放电，
  XNU 报 +397mA 充电，两侧符号相反；最大 |ΔV|=83mV/±60mV、|ΔSOC|=1.00pp、|ΔT|=1.30°C，
  |ΔI| 因符号相反未比较（报告 `sign-audit-20261118-1156/imagef-full8.txt`）。低电流 3 行窗口
  PASS 不能替代全窗口通过；11:47 的匹配电流窗口见 §7.10。
- 旧 route-c dmesg 窗口 16447–16652 仍因冷战基线判 FAIL（rc=1），不是同状态基线。
- 该镜像的插拔、放电、超时与服务重启仍未获得真机脚本化证据；第 15 节只证明 manager 对待发布样本的状态转换，
  不代替真机。image e 不含 `0bad0c61`，image f 起包含该修正。

### 7.10 Android 电流符号复核与 C3 旧结论作废（2026-11-18 11:56）

- 官网 :76 要求“确认目标协议的单位和充电电流符号”。K60 的 Android/qcom 电量计在充电时
  `current_now` 为负；XNU 按 Apple IOPMPowerSource 约定以正电流表示充电，两侧原始符号相反。
- 证据来自同一次 11:40 Android 采集（`E:/k60-work/evidence/power-conformance/matched-current-20261118-114010`）：
  - `android-dmesg.txt` 的 `fg_update_status` 行显示 ibat 为 +258/+910mA 时 `rm` 从 4188 降到 4180mAh，
    ibat 转为 -335/-446/-166/-416/-380/-350mA 后 `rm` 从 4179 升到 4193mAh，同时 vbat 从 4329mV 升到 4394mV；
    可见正电流是放电、负电流是充电。
  - 同一文件的 healthd 行 `battery l=97 v=4390 ... st=2 c=-368000 chg=a`：status=2 充电、AC 供电时
    healthd 原始电流仍为 -368000µA，直接确认负值=充电。
- 修正：`773452af` 在 `scripts/judge-battery.py` 增加 `--android-current-sign {negative,positive}`
  （默认 `negative`），比较前先归一化 Android 电流；`5d7f9b45` 更新测试夹具并保留 positive=charging
  旧采集的显式开关。`test-judge-battery.py` = 22 cases PASS。
- 复核结果（报告目录 `E:/k60-work/evidence/power-conformance/sign-audit-20261118-1156`）：
  - image e 第一次 3 行匹配窗口：FAIL，Android 原始 +516/+317/+276mA 归一化为放电，XNU +397mA 充电；
    最大 |ΔV|=43mV、|ΔT|=1.10°C（`imagee-first-matched3.txt`）。旧 PASS 作废。
  - image e 第二次 3 行匹配窗口：FAIL，原始 +365/+343mA；63mA 对未比较；|ΔV|=43mV、|ΔT|=0.60°C
    （`imagee-matched3.txt`）。旧 PASS 作废。
  - image e 9 行/36 行全窗口：FAIL，符号相反；|ΔV| 77/91mV（`imagee-first-full9.txt`、
    `imagee-second-full36.txt`）。
  - image f 11:13 低电流 3 行：PASS，|ΔV|=46mV、|ΔSOC|=1.00pp、|ΔT|=1.00°C，电流未比较
    （`imagef-low.txt`）。这是目前唯一有效的 C3 PASS。
  - image f 11:13 全 8 行：FAIL，原始 +490/+144/+107/+335/+254mA 归一化为放电（`imagef-full8.txt`）。
  - image f 11:47 的 13 对匹配电流窗口：FAIL 仅电压，|ΔV|=119mV/±60mV、|ΔT|=1.60°C、
    |ΔI|=29mA/±150mA（`imagef-matched-current.txt`）。归一化后电流幅值已对齐，剩余差距是电压，
    说明符号修正本身正确。
  - 同一 11:47 数据的 13 行全窗口：FAIL，早期原始 +582/+1566/+1448/+1161/+929mA 为放电，
    |ΔI|=191mA（`imagef-all-negative.txt`）；把开关切回 `--android-current-sign positive` 会复现旧错误，
    |ΔI| 最大 1169mA（`imagef-all-legacy-positive.txt`）。
- 12:19 的 Android 状态/电流复核（`E:/k60-work/evidence/power-conformance/android-status-current-20261118-1219/samples.tsv`）：
  同一次 `status=Charging` 下 `current_now` 从 +1002mA（净放电，charge_counter 停在 4173）变到
  -413mA（净充电，charge_counter 4172→4175）；说明 Android 的 status 表示“充电器已接入”，
  电流符号表示净电池电流方向，两者不是一回事。XNU 的 `Amperage` 是 USB 输入电流（电池电流属性 9
  不应答，无法读净电池电流），所以 XNU `charging=1` 且 `current=397mA` 也不表示净充电。
  C3 全窗口把两侧当成同一电流方向比较不成立；只有两侧 |I|<100mA 的低电流窗口可以比较电压/SOC/温度。
- 结论：11:56 之前所有 image e 匹配电流 C3 PASS 作废；C3 目前只有 image f 低电流 3 对 PASS，
  匹配电流窗口的电流幅值已对齐（ΔI 29mA），但电压仍超差（119mV）。全窗口通过仍要求同方向、
  同电流、同电压状态的 Android 基线；不能把低电流 PASS 当作 C3 完成。

## 8. Host 测试覆盖

`scripts/tests/test-k60-charger-subscription.c` 当前 95 项断言，覆盖：
字段校验/范围、有效-失败位图、原始值复制（4277000 µV / 2830 / 8900 百分之一）、
电池缺失路径、超时只标记未完成字段、transport 重启后丢弃旧 epoch 并重新发布，
以及第 15 节的插拔/充电/放电/full 状态转换、充电取 TimeToFull/否则取 TimeToEmpty 的剩余时间选择和非法状态拒绝，和第 16 节的容量一致性/适配器限流/缺失 pack 快照。
`scripts/tests/test-battery-units.py` 当前 28 项，覆盖 µV/µA、0.01% 和秒的边界与电流符号；
`test-judge-battery.py` 当前 22 项，覆盖 Android negative=charging 归一化、positive 旧采集显式开关和 dmesg 幅值比较。
运行方式见 `scripts/tests/run-k60-handoff-host.sh`（WSL gcc）。

## 9. 边界：固件所有权与未闭项

- 本驱动只发布测量值，不写充电器、不改电流限制、不做 PD/PPS 认证；固件继续拥有充电控制
  （官网 :81 的边界）。K60 的充电 IC 控制路径不在本文件范围内。
- 官网 §4 的「sheng 的 PD、PPS 和 MiPPS」（`:82-88`）与「sheng Linux 充电读取镜像」
  （`:89-104`）不属于本文件的测量值发布范围：本板 ADSP 固件拥有充电控制，驱动没有
  充电器认证或主机控制路径；若后续要主机控制充电，需要单独实现 `ShengChargeAuth.c` 等价的
  HMAC-SHA256 认证、PD/PPS/MiPPS 合约、限值和温控策略。当前检出的 `UniXNU-sheng`
  `origin/main` `1108068` 不含 `package/ShengChargeAuth.c`；`ShengBattmgr.c` 注释明确
  `no Xiaomi extensions or charger writes`，`sheng.md:519-524` 与 `fuxi.md:563-568` 都记录 ADSP 固件
  负责 PD/PPS 协商且两节电芯和 PD adapter `read unauthenticated`。因此官网 `:82-104` 是参考流程/工具路线，
  不是 K60 可直接复用的实现。
- 未闭项（必须在下一轮镜像与真机报告中关闭或明确保留）：
  1. 最终 battery-only 镜像 `E:/k60-work/artifacts/power-conformance-20261118f/boot.img`（sha256 `024466905dec75cbab5d2525f68936d6f18650a4b0d3aed6551d5ccc3df94c6e`）已于 2026-11-18 11:07 构建、11:13 上机，包含 `592523aa`/`6750c7bd`/`af759fe4`/`0bad0c61`；C1/C2 PASS、C3 对同会话 3 行低电流 Android 基线 PASS（`judge-android.txt`，|ΔV|=46mV、|ΔSOC|=1.00pp、|ΔT|=1.00°C），8 行全窗口在 11:56 符号修正后 FAIL（Android 原始正电流按 negative=charging 归一化为放电），见 §7.9/§7.10。上一版 image e（`8b1df...`）不含 `0bad0c61`（剩余时间按 charging 选择），已三次上机且 C1/C2 PASS，但 11:56 符号修正后其匹配电流 C3 PASS 全部作废（§7.10）；image d（`9e66ef...`）不含容量修正；§7.4 是 image c 的实测，§7.3 是改动前 route-c 对照。
  2. 真机插拔、放电、超时未执行；host 第 15 节已模拟插拔、充电/放电/full 状态转换和剩余时间选择（95 项），但不代替真机。服务重启的代码路径已补（`6750c7bd`，image e/f 包含），IOKit 级 stop/start 未上真机。
  3. C3 需要至少 3 对同方向、同电流、同电压状态的样本；image f 的低电流 3 对（11/0/92mA）PASS 但电流未比较；11:47 的 13 对匹配电流窗口归一化后 ΔI=29mA，但 ΔV=119mV 超差；image e 的旧匹配 PASS 在符号修正后全部 FAIL。全窗口通过仍要求更稳定的同电流 Android 基线，不能把低电流 PASS 当作 C3 完成。
  4. `K60Raw*` 属性已发布；`K60BatterySmoke` 现在读取并核对 `K60BatteryValidFields`（必须非零）、`K60BatteryFailedFields`、`K60RawVoltageMicrovolts`（`/1000` 应等于 `Voltage`）、`K60RawCurrentMicroamps`（电池电流 `/1000` 应等于 `Amperage`；仅 USB 输入电流时改用 `K60RawUsbCurrentMicroamps / 1000`）和 `K60RawTemperatureHundredths`（应等于 `Temperature`）；标准 `CurrentCapacity`/`MaxCapacity` 现在按官网发布为百分比（`MaxCapacity=100`），`AppleRawCurrentCapacity`/`AppleRawMaxCapacity` 保留 mAh，smoke 同时校验这两组值；缺失电池首帧注册尚未在真机验证。
- 设备状态（2026-11-18 12:28）：image f 11:47 采集已于 11:52:33 完成（`K60AUTORESET` 300 s 后发布 `restart reason published`，见 §7.10）；controller 报 `returnedToFastboot=False`，随后设备回到 `fastboot`（`k60-device.sh state` = fastboot，serial 6033dbec），`list-boot-watchers.ps1` 当时无 watcher；12:14–12:24 设备在 Android（serial 6033dbec），完成 12:19 的状态/电流复核；12:15 启动的 k60-audio-adsp audio-probe-af watcher 于 12:26:46 引导（`E:/k60-work/evidence/audio-probe-af/run1-20261118-1215`，image `AAAD48173587…`，`boot.json` `bootAccepted=false`/`bootExitCode=-1`，12:27 `console.log` 0 B），12:28 `k60-device.sh state` = none，占机期间不抢。10:47 的 k60-audio-adsp audio-probe-ab watcher（`E:/k60-work/evidence/audio-probe-ab/run1-20261118-1035`）已结束；此前 09:26 的 audio-probe boot（`E:/k60-work/evidence/audio-probe-y/run1-20261118-0415`，:568 SOC=100.00%）只是一个独立 audio 镜像的用户可见 100% 电池显示，不是本分支 image e/f，不作为 §4 一致性证据。
