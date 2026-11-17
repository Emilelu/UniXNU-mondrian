# 10 — 电池状态上报：官网 §4 逐条对照

> 目的：把官网 `https://unixnu.com/zh/porting/power` §4「实现电池状态上报」的每个要求，落到本仓库的
> 文件、行号、测试与真机证据上；有缺口的地方必须写成缺口，不用“已覆盖”掩盖。
> 取材：官网正文抓取自 2026-11-17，本地快照 `E:/k60-work/scratch/power-page-20261117.txt:68-81`；
> 代码基线 `fix/power-doc-conformance`（从 `fix/battery-sample-dirty` 263ee626 切出）。
> 边界：本文件只描述测量值发布；充电控制仍归固件，见文末 §9。

## 0. 一句话结论

驱动已经具备：单请求状态机、协议五要素校验、有效/缺失/失败三态、原始值到 OS 值的显式换算、
IOPMPowerSource 子类、工作循环、三个定时器、首帧后才注册、适配器字典、断链置 stale。
尚未完成：带本轮改动的镜像重建与真机复测、真机插拔/充放电脚本化验证、服务重启的 IOKit 级验证、
与 Android 的 ≥3 对同窗口 C3（当前只有 2 行 XNU sample，判 INVALID 而不是 FAIL）。

## 1. §4 开头：参考实现的选择（官网 :69-74）

| 参考 | 用途 | 本仓库对应 |
| --- | --- | --- |
| `ShengBattmgr.h` / `ShengBattmgr.c` | 请求/响应格式、刷新状态机、单位转换 | `drivers/PongPower/K60Battmgr.h`、`K60Battmgr.c`；协议字段来自 m81.ko 反编译，见 `docs/research/charger/02-GLINK-CONTRACT.md`、`04-PROP-MAP.md` |
| `ShengBattery.cpp` | IOPMPowerSource 属性、工作循环、计时器、通知 | `drivers/PongPower/K60Battery.cpp` |
| `BatteryProbe.cpp` | 类注册与服务启动 | `K60Battery.cpp:464` `k60_physical_battery_start()`，由 `patches/xnu/0602-k60-physical-battery.patch` 在 `IOService::publishResource("IOBSD")` 后调用 |
| XNU `IOPMPowerSource.h` | 属性设置与状态发布 API | 继承 `IOPMPowerSource`（`K60Battery.cpp:46`），使用 `setPSProperty` / `updateStatus` / `registerService` |
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
- 请求发出成功后 `k60_battmgr_sent()` 才设置 `flight`（`:92-97`），FIFO 背压时由 `K60Battery.cpp:302-305` 重试，未写入不算已发。
- 收到匹配应答后 `finish_field()` 清 `flight` 并把 cursor 推进（`:140-157`）。

### 2.3 超时后才推进刷新周期

- 每个请求由 `requestTimer` 计时（`K60Battery.cpp:309` 设置 `kRequestMs=3000`，`:25`）。
- `requestAction()`（`K60Battery.cpp:375-387`）打印超时行后调用 `k60_battmgr_timeout()`：
  `timeouts++`、`poisoned=1`、清 `valid/fresh/completed/last_fresh`（`K60Battmgr.c:206-213`）。
- 其后必须 `transport.reopen()` 才继续（`K60Battery.cpp:386`）；`pump()` 在 `poisoned` 时不发请求（`:297`）。
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
`k60_battmgr_sample()` 在正常路径（`K60Battmgr.c:235-278`）和电池缺失路径（`:224-229`）都复制
`s->valid = b->last_fresh; s->failed = b->failed; s->raw[i] = b->value[i]`，所以 OS 侧可以同时回答
“哪些值有效、哪些失败了、原始值是多少”。

### 3.2 快照字段（官网要求的存在/外接/充电/容量/电压/电流/温度/剩余时间）

| 官网字段 | `K60BatterySample` 成员 | 发布键 | 代码 |
| --- | --- | --- | --- |
| 电池存在 | `present` | `kIOPMBatteryInstalledKey`（`setBatteryInstalled`） | `K60Battery.cpp:214` |
| 外接电源 | `external` | `kIOPMPSExternalConnectedKey` | `:215` |
| 充电状态 | `charging` | `kIOPMPSIsChargingKey` | `:215` |
| 容量 | `current_mah` / `capacity_hundredths` | `kIOPMPSCurrentCapacityKey` / `K60CapacityHundredths` | `:170,174` |
| 满充/设计容量 | `full_mah` / `design_mah` | `kIOPMPSMaxCapacityKey` / `NominalChargeCapacity` / `DesignCapacity` | `:170,174` |
| 电压 | `voltage_mv` | `kIOPMPSVoltageKey` | `:170` |
| 电流 | `current_ma` / `current_source` | `kIOPMPSAmperageKey` / `InstantAmperage` / `K60CurrentCapacityBasis` 来源说明 | `:171,173,220` |
| 温度 | `temperature_hundredths` | `kIOPMPSBatteryTemperatureKey` | `:173` |
| 剩余时间 | `time_remaining_min` | `kIOPMPSTimeRemainingKey` | `:172` |
| 循环次数 | `cycles` | `kIOPMPSCycleCountKey` | `:171` |
| 适配器 | `adapter_mv/ma/type` | `kIOPMPSAdapterDetailsKey` 字典 | `:259-294` |

### 3.3 原始值 → OS 值换算（含发布出来的 raw 键）

| 字段 | 原始单位（ADSP） | OS 值 | 换算 | 代码 |
| --- | --- | --- | --- | --- |
| 容量百分比 | 0.01%（`K60BmCapacity`） | `K60CapacityHundredths` 保持 0.01%，`current_mah` 由 SOC×满充算 | `capacity_hundredths = raw`；`current_mah = (SOC_hundredths × full_uAh + 5,000,000) / 10,000,000`，上限 `full_mah` | `K60Battmgr.c:245-250` |
| 满充/设计容量 | µAh | mAh | `/1000` | `:246` |
| 电压 | µV | mV | `/1000` | `:251` |
| 电流 | µA（带符号） | mA | `charging_current_sign × raw/1000`；无电池电流时，充电中外接电源用 USB 电流 `raw/1000` | `:252-262` |
| 温度 | 0.01 °C | 0.01 °C（IOPMPowerSource 约定） | 原样保留 | `:264` |
| 剩余时间 | 秒 | 分钟 | `/60`；`0xffff` 或无值 → `-1` → 发布为 `0xffff`（unknown） | `:265-269`、`K60Battery.cpp:172` |
| 适配器电压/最大电流 | µV / µA | mV / mA | `/1000`；输入限流取二者较小值 | `:270-275` |
| 适配器功率 | — | W | `mV × mA / 1,000,000` | `K60Battery.cpp:268` |

原始值本身也发布为 `K60Raw*` 属性（`K60Battery.cpp:102-106` 声明，`:181-192` 赋值）：
`K60RawStatus`、`K60RawCapacityHundredths`、`K60RawVoltageMicrovolts`、`K60RawCurrentMicroamps`、
`K60RawTemperatureHundredths`、`K60RawFullChargeMicroampHours`、`K60RawDesignChargeMicroampHours`、
`K60RawUsbVoltageMicrovolts`、`K60RawUsbCurrentMicroamps`、`K60RawTimeToFullSeconds`、
`K60RawTimeToEmptySeconds`、`K60RawUsbAdapter`。失败位图发布为 `K60BatteryFailedFields`（`:180`），
与 `K60BatteryValidFields` 配对，满足“有效读数与缺失/失败状态分开保存”。

### 3.4 充电电流符号

`charging_current_sign` 来自板级配置，只接受 `+1` / `-1` / `0`（`K60Battmgr.c:48-57`）。
Route-c 真机行的 `measured sign=-1`（`console.log:401`）与充电中 `current=397mA` 正号
（`:534`，status=1、external=1）一致，说明“放电为正”的线序已被取反为 OS 的“充电为正”。
样本层还有两道一致性拒绝：status=2（放电）不允许正电流，status=1（充电）不允许负电流
（`K60Battmgr.c:263`）。

## 4. §4 第三段：IOPMPowerSource、工作循环、响应队列、计时器（官网 :77）

- 类声明：`class K60Battery : public IOPMPowerSource`（`K60Battery.cpp:46`），`begin()` 先调
  `IOPMPowerSource::start(provider)`（`:397`）。
- 工作循环：`IOWorkLoop::workLoop()`（`:401`）；所有 GLINK 回调、定时器动作都在该 loop 上执行。
- 响应队列：GLINK 的 `receive` 回调只把数据交给 `k60_battmgr_receive()`，不在回调里发下一笔；
  `K60Battery.cpp:347-348` 注释明确要求先把 RX_DONE 放回 FIFO，再由 `pollAction` 的 `pump()` 发送。
- 计时器：`pollTimer`（20 ms，`kPollMs`）、`requestTimer`（3000 ms，`kRequestMs`）、
  `refreshTimer`（5000 ms，`kRefreshMs`）均在 `:402-404` 创建、`:406-411` 加入 loop；
  `shutdownAction` 在 `:421-431` 取消三个定时器并关闭 transport。
- 解码器只在快照完整后更新属性：`receive()` 收到 `K60BmCycleDone` 才调用 `k60_battmgr_sample()`，
  成功才 `publish()`（`:334-337`）。

## 5. §4 第四段：registerService、updateStatus、一致性、适配器（官网 :78）

### 5.1 首帧有效属性后才注册

`publish()` 只在 `k60_battmgr_sample()` 返回 1 时被调用；在注册之前，所有属性已经通过
`setPSProperty` 写入（`K60Battery.cpp:204-220`），然后：

1. `updateStatus()`（`:224`）把属性字典复制到电源源快照；
2. `if (settingsChangedSinceUpdate) return;`（`:225`）——复制失败则不暴露半套初始属性；
3. 首次成功才 `registerService()`（`:226-228`），随后用 `isInactive()` 检查注册是否真的生效；
   未生效则清 `published` 并打印 `registerService left the source inactive; retrying on the next sample`
   （`:229-234`），下一次有效样本会重试。

### 5.2 后续变化 updateStatus

每一帧合格样本都会重新设置属性并调用 `updateStatus()`（`:204-224`）；`IOPMPowerSource::updateStatus()`
只在 `settingsChangedSinceUpdate` 为真时通知客户端（XNU `iokit/Kernel/IOPMPowerSource.cpp:174`），
避免无变化刷新风暴。变化日志只在外部/充电/满/容量变化时打印（`:236-238`）。

### 5.3 存在/外接/充电与容量、测量值一致

- `present=1` 才走正常发布；无电池走 `setBatteryInstalled(false)` 且保留 stale（`:153-168`）。
- `external = usb || wireless`（`:239-241`）；`charging = external && status==1`、`full = external && status==4`（`:243`）。
- `status==1 && !external` 直接拒绝样本（`:244`）；满充/设计容量比值必须在 [0.5, 1.5]（`K60Battmgr.c:233-234`）。
- 容量与测量值同帧来自同一 `K60BatterySample`，不存在跨帧拼接。

### 5.4 适配器信息

`updateAdapter()`（`K60Battery.cpp:259-294`）填 family / voltage / amperage / watts 四项；
family 映射见 `:33-43`。USB 已连接但 adapter type 缺失时仍填 `kIOPSFamilyCodeUSBUnknown`，不丢整个字典
（`:271-276`）；未外接时只填 disconnected family（`:270`）。可选失败字段不填 0 瓦假事实（`:261-262` 注释）。

## 6. §4 第五段：订阅通知、周期刷新、断链 stale（官网 :79）

- 订阅：`k60_battmgr_channel_up()` 在配置了非零 `notify_reply_bytes` 时置 `subscribe_due`
  （`K60Battmgr.c:64-69`）；`next()` 生成 type2/op4 请求（`:81-86`）；只有收到类型/长度匹配且
  data[12..] 全 0 的应答才 `subscribed=1`（`:174-182`）。
- 通知：`OP_NOTIFY` 只接受 type2/16 B 和四个已知 property group（`:163-172`），置 `sample_dirty` 并触发刷新。
- 周期刷新：`refreshTimer` 每 5000 ms 调 `k60_battmgr_refresh()`（`K60Battery.cpp:388-394`）；
  `k60_battmgr_refresh()` 在周期/请求进行中只置 `refresh_due`，完成后由 `receive()` 补下一轮
  （`K60Battmgr.c:70-75`、`K60Battery.cpp:345`）。
- 传输断开：`pollAction()` 检测 `transport.poll() < 0 || !alive()` 时取消两个定时器、打印
  `physical transport stopped error=%d; no DSP/FIFO reset`（`:354-358`）；通道 down 回调和握手超时也走
  `stale()`（`:322-326`、`:360-365`）。`stale()` 保留最后测量值并置 `K60BatteryStale=true`（`:142-149`）。

## 7. §4 第六段：原始对照、插拔/充放电/超时/服务重启（官网 :80）

### 7.1 原始读数与发布属性对照

原始值通过 `K60Raw*` 属性（§3.3）直接可见；OS 值通过标准 IOPMPowerSource 键可见。对照表就是 §3.3，
两边使用同一个 `K60BatterySample` 的 `raw[]` 和转换后字段，不存在二次采样。

### 7.2 已验证 / 待验证矩阵

| 验证项 | 状态 | 证据 / 缺口 |
| --- | --- | --- |
| 协议响应 | 已验证 | Route-c 真机：`console.log:189` adopting、`:401` channel up、`:534` 首帧、`:761` 第二帧；host 测试 71 项覆盖应答/拒绝/超时 |
| OS 可见更新 | 已验证 | `:534` `physical source published`、`:761` `physical source updated`，字段值与原始值换算一致（见 §7.3） |
| 响应超时 | host 已验证 | `test-k60-charger-subscription.c` 第 13 节：timeout 只标记未完成字段，poisoned epoch 生效；真机未制造超时 |
| 插拔电源 | 未验证 | 需要人工插拔并在同一次 usblog 里看 `external`/`charging`/`usb_online` 的变化；本轮未做 |
| 充放电 | 未验证 | Android 侧 sample 为充电中（status=2、current=0），XNU 侧 status=1；放电段未采样 |
| 服务重启 | host 部分验证 | 第 14 节“transport restart drops and republishes”验证 manager 重新 channel_up 后会丢弃旧 epoch 并重发；IOKit 级 stop/start 未在真机执行 |
| 与 OEM/目标电量计逐项对照 | 部分 | C1/C2 已过（route-c），C3 只有 2 对 XNU/Android 样本，判 INVALID；补 ≥3 对后才能结案 |

### 7.3 Route-c 实测数值（2026-11-17 23:18 boot）

- 首帧 `console.log:534`：SOC=89.00%、charge=4078/4582mAh、design=5500mAh、cycles=749、
  voltage=4217mV、current=397mA（current-source=usb）、temp=28.80°C、external=1、charging=1、full=0、subscribed=1。
- 第二帧 `console.log:761`：SOC=88.00%、charge=4032/4582mAh、voltage=4211mV、current=397mA、temp=28.80°C。
- 换算核对：`4217 mV = 4217000 µV / 1000`；`397 mA = 397000 µA / 1000`；
  `89.00% = 8900 × 0.01%`；`4078 mAh ≈ 8900 × 4582 / 10000`（四舍五入误差在 1 mAh 内）。
- `judge-battery.py` 结果：C1 PASS（`:401,:534`）、C2 PASS（`:534,:761`）、
  C3 INVALID（只有 2 对，阈值 `MIN_PAIRS=3`，`judge-battery.py:107`）。报告 `E:/k60-work/scratch/judge-routec.txt`。

## 8. Host 测试覆盖

`scripts/tests/test-k60-charger-subscription.c` 当前 71 项断言，覆盖：
字段校验/范围、有效-失败位图、原始值复制（4277000 µV / 2830 / 8900 百分之一）、
电池缺失路径、超时只标记未完成字段、transport 重启后丢弃旧 epoch 并重新发布。
运行方式见 `scripts/tests/run-k60-handoff-host.sh`（WSL gcc）。

## 9. 边界：固件所有权与未闭项

- 本驱动只发布测量值，不写充电器、不改电流限制、不做 PD/PPS 认证；固件继续拥有充电控制
  （官网 :81 的边界）。K60 的充电 IC 控制路径不在本文件范围内。
- 未闭项（必须在下一轮镜像与真机报告中关闭或明确保留）：
  1. 带本轮 conformance 改动的镜像尚未构建/未上机；§7.3 是改动前的 route-c 镜像。
  2. 真机插拔、放电、服务重启三项未执行。
  3. C3 需要至少 3 对同窗口样本；当前 2 对。
  4. `K60Raw*` 属性已发布但尚未被 `K60BatterySmoke` 读取验证（可扩展该工具）。
