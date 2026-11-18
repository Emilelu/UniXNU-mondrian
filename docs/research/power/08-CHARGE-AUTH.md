# K60 充电认证移植（power §4 :82-88）

日期：2026-11-18。范围：官网 power 页 §4「sheng 的 PD、PPS 和 MiPPS」（快照
`E:/k60-work/scratch/power-page-20261117.txt:82-88`）。本文记录 **独立的
`feat/charge-auth` 分支**：协议状态机已移植，并以 `k60_charge_auth=0` 默认关闭的
方式接入 `K60Battery` 的串行请求队列；HMAC-SHA256 与 `read_random` 已接内核回调。
仍没有 UCSI 数据角色路径，也没有上机。按用户 2026-11-18 的指示，充电认证单独开
分支；上机测试与插拔测试另行安排。

## 1. 官方要求

- sheng 的 DSP 电池管理器负责 PD/PPS 合约、充电泵、电流限制和温度调节；
  `package/ShengChargeAuth.c` 用 HMAC-SHA256 认证两个电量计，再认证提供
  SVID `0x2717` 与有效 PDO2 的小米充电器。
- USB 请求把数据角色切换为 host；认证在每次连接时运行一次，与电池管理器共用串行请求队列。
- Linux 工具通过小米 `qcom-battery` sysfs 接口运行同一份 C 状态机；主机协议检查覆盖
  认证和连接变化，实际协商功率需要连接充电器测量。
- 官方同时说明边界：固件拥有充电控制时，驱动只发布测量值；主机控制的充电器需要独立的
  控制协议、限值和温控策略（`:81`）。本移植只做“认证”，不取得充电控制权。

## 2. sheng 参考

`UniXNU-sheng` `origin/main` `6c42e10`（2026-11-17），BSD-2-Clause-Patent：

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `package/ShengChargeAuth.c` | 13,630 B | 状态机、协议常量、HMAC 校验、诊断属性 |
| `package/ShengChargeAuth.h` | 2,703 B | `ShengChargeAuth` 结构、crypto 回调、18 状态 |
| `package/tests/charge_auth_host.c` | 8,678 B | host 测试，以 macOS CommonCrypto 为对端 |

实现于 `2359a86`（2026-11-16）。`ShengBattery.cpp` 在串行电池请求队列里调用
`observe`/`next`/`receive`/`timeout`（`:116`、`:166`、`:353`、`:377`），
`chargeAuthEnabled` 默认 true，由 boot-arg `authentication` 关闭。
完成 HostRole 需要 `qcom_ucsi_data_host`/`qcom_ucsi_request_data_host`
（`ShengBattery.cpp:163-164`）与 UCSI 发送。

## 3. K60 移植

新文件：`drivers/PongPower/K60ChargeAuth.h`、`K60ChargeAuth.c`。

- 提交 `5449a0bf` `feat(power): add the charge authentication port`（2 文件，351 行）。
- 提交 `ab96b0b5` `test(power): cover the charge authentication flow`（host 测试）。
- 提交 `c6c0307a` `feat(power): wire charge authentication into the battery queue`
  （`K60Battery.cpp`、`K60ChargeAuth.c/.h`、`scripts/build-k60-physical-battery.py`）。
- 提交 `685aecb0` `test(power): cover the charge-auth suspension path`
  （host 测试扩到 99 项）。
- 头文件保留 `extern "C"`，源文件只依赖 `<string.h>`，可按 C11 单独编译：
  `cc -Wall -Wextra -Werror -std=c11 -c drivers/PongPower/K60ChargeAuth.c`。
- 许可证与 sheng 相同：BSD-2-Clause-Patent，`Copyright (c) 2026, UniXNU contributors`。

API：

```c
void k60_charge_auth_init(K60ChargeAuth *, const K60ChargeCrypto *);
void k60_charge_auth_set_gauges(K60ChargeAuth *, unsigned count);
void k60_charge_auth_reconnect(K60ChargeAuth *, uint64_t now_ms);
void k60_charge_auth_observe(K60ChargeAuth *, int online, int usb_type, uint64_t now_ms);
uint32_t k60_charge_auth_next(K60ChargeAuth *, uint64_t now_ms,
    uint8_t out[K60_CHARGE_REQUEST_BYTES]);
int k60_charge_auth_receive(K60ChargeAuth *, const uint8_t *, uint32_t, uint64_t now_ms);
void k60_charge_auth_timeout(K60ChargeAuth *, uint64_t now_ms);
uint32_t k60_charge_auth_wait_ms(const K60ChargeAuth *, uint64_t now_ms);
```

协议点：

| 项 | 值 |
| --- | --- |
| owner / type | `32778` / `1` |
| Get / Set | `0x50` / `0x51` |
| VerifyDigest / Authentic / SlaveAuthentic | `1` / `3` / `0xa5` |
| PdVerified / VdmState | `0x18` / `0x1a` |
| 请求缓冲 | 52 字节；scalar 24 字节，property 在 `+16`，值在 `+20` |
| 非 scalar | property 在 `+12`；52/32 字节请求带 challenge/seed 于 `+16` |
| 诊断 | 18 个属性；失败项置 invalid 并递增 cursor，结束后进 Done/Failed |

**单电量计适配**：sheng 是双电芯，状态机默认先认证 slave 0，再认证 slave 1。K60 是
单电芯（design `5500000` µAh），`k60_charge_auth_init` 把 `gauges` 设为 1，电量计
通过后直接进入适配器检查；双电量计板子可调用 `k60_charge_auth_set_gauges(a, 2)`
恢复 sheng 流程。`reconnect` 保留 gauge 数与未完成请求的队列槽位，旧连接的应答
不会推进新连接。

## 4. 边界

- **已接线，默认关闭**：`K60Battery` 用独立的 52 字节缓冲与 `authQueued`/`authSent`
  槽位接入状态机，保持“一次一个未完成请求”；`k60_charge_auth` 默认 0。构建脚本已把
  `K60ChargeAuth.c` 编进 `build/k60-battery/libK60PhysicalBattery.a`（136,000 B，
  sha256 `a5476c084b6efeea552b6298e8eff8044a95a46418da78bc4a9b785c0bb711db`），
  但该 archive 还没有链进任何镜像。
- **触发条件**：`publish` 对每个已发布样本调用 `observe(online = usb_connected,
  pd = pdType)`，其中 `pdType` 要求 `K60BmUsbAdapter` 有效且 property 7 原始值为
  6/7/8；`observe(online=1, pd=0)` 在 `K60ChargeAuth.c:116` 走 `reconnect()` 回到
  Idle，所以 PD 资格消失会立刻停掉旧认证。未通过限流校验的样本走 `observe(0,0)`
  并取消排队（`K60Battery.cpp:476-484`）；刷新失败由 manager 超时 → `stale` →
  channel down → `state(false)` → `k60_charge_auth_reconnect` 处理。属性 6 未请求，
  不用电压/电流推断 PD。
- **crypto 已接内核回调**：`K60ChargeHmac.h` 用 `<libkern/crypto/sha2.h>` 的
  SHA-256 加 0x36/0x5c 实现 RFC 2104 HMAC-SHA256（超过 64 字节的密钥先哈希），随机源
  用 `read_random`；`scripts/tests/test-k60-charge-hmac.c` 用自带 SHA-256 跑 RFC 4231
  用例 1/2/3/6/7（含 131 字节密钥）5 项全过；状态机 host 测试仍用假 crypto。密钥与
  种子是协议公开常量，本文不复制密钥值。
- **没有 UCSI 数据角色**：K60 树里没有 UCSI/TypeC 驱动，`host_ready` 没有设置者；
  若适配器 PDO2 有效，状态机在 HostRole 等 5 s 后以 `-95` 失败；电量计认证本身可以
  走完，但整体状态落到 Failed，18 个诊断属性不会执行（`K60ChargeAuth.c:170-174`）。
- **没有充电控制**：不写充电器、不改限流、不做 PD/PPS 合约或温控策略，符合官方 `:81`
  的所有权边界；认证成功只表示“电量计/适配器身份得到确认”，不表示功率协商成功。
- **超时隔离**：认证请求超时会清空槽位并 `reopen`/关闭当前 GLINK 通道，旧通道的
  迟到应答不能推进重试；这条路径不调用 `k60_battmgr_timeout`，所以不会置
  `K60Battmgr` 的 `poisoned`，但当前订阅和未完成 cycle 会作废，channel-up 后重新订阅。

## 5. Host 断言

`scripts/tests/test-k60-charge-auth.c`，99 项，0 失败；ASan/UBSan 下同结果（只测状态机）：

```sh
cc -Wall -Wextra -Werror -std=c11 -Idrivers/PongPower \
  scripts/tests/test-k60-charge-auth.c drivers/PongPower/K60ChargeAuth.c -o /tmp/tca
/tmp/tca   # TESTS OK 99 checks (0 failures)
```

覆盖：PD 类型 6/7/8 分类与 5/9 拒绝、单/双电量计 ack、challenge→digest→mark、
适配器 SVID/PDO2 分支、9 次重试后 tries=10/result=`-60`、reconnect 后旧应答被吞掉、
52 字节 Get 短应答拒绝 `-61`、18 个诊断属性含一个错误后进 Done、错误 property 的
应答被忽略、样本失配时暂停并取消排队、认证超时后旧应答不能推进重试。
host 侧只测状态机；`K60Battery` 的 `reopen`/GLINK 集成没有 host 覆盖。

`scripts/tests/test-k60-charge-hmac.c` 另有 5 项 RFC 4231 已知向量断言，补上生产 HMAC
的向量覆盖；状态机测试本身仍用假 crypto。

archive 的未定义符号已与内核导出表对照：310 个导入、141 个本 archive 定义，244 个外部
符号全部能在 `kernel.macho` 的 22,909 个导出里找到（缺失 0），包括 `_SHA256_Init`/
`_SHA256_Update`/`_SHA256_Final`、`_read_random`、`_bzero`。这只证明链接输入齐备，
不是链接测试，也没有上机。

## 6. 下一步

1. 上机时用 `k60_charge_auth=1` 只观察 `K60Battery: charge-auth` 行，不把认证结果
   当作充电许可；release board 的 575 B 可容纳这个 17 字节 token（含分隔空格 18 字节），但 2026-11-18
   的 603 B EPSS 探针镜像会到 621 B（超过 607），探针必须先移除另一项。
2. 找到 K60 的 TypeC/UCSI 数据角色路径，设置 `host_ready`；否则 PDO2 有效时
   HostRole 仍会在 5 s 后以 `-95` 失败（需要产品决策）。
3. 用 host 已知向量校验 `chargeHmac`，再把认证槽位接到真实固件的 PPS/MiPPS 合约；
   仍然不取得充电控制权。
4. 真机插拔、PDO2 有效/无效、认证超时与服务重启按用户安排另行测试。

### 6.1 接线前的约束（历史，2026-11-18 19:10 代码复核）

这一节保留接线前的复核记录，供追溯；其中“没有注入接口”“不能重新 next”
“pump 优先级”“接收/超时分流”“定时器粒度”“PD 判定缺字段”“crypto 未写”
“默认关闭”各项已在 `c6c0307a`/`685aecb0` 处理或明确为边界。

- **没有注入 52 字节请求的接口**：`K60Battmgr.h` 只暴露
  `k60_battmgr_next`（24/28 字节）、`k60_battmgr_sent`、`k60_battmgr_receive`、
  `k60_battmgr_timeout`。认证状态机不能借用 `k60_battmgr_next` 的槽位，必须在
  `K60Battery` 里单独维护 `authFlight` 和 52 字节的 `authRequest`。
- **发送失败不能重新 `next`**：`k60_charge_auth_next` 在构造请求时就置
  `pending=1`（`K60ChargeAuth.c:48-55`）。若 `transport.send` 返回
  `QcomGlinkAgain`，再次调用 `next` 只会得到 0；必须保留原 52 字节缓冲重发，
  或给状态机补一个“未发送/可重发”的状态。
- **pump 的优先级**：`K60Battery::pump`（`K60Battery.cpp:327-342`）现在先检查
  `manager.flight`/`manager.poisoned`。接线后应先检查 `authFlight`，再让认证
  请求在 manager 空闲时优先发送；manager 的 `flight` 语义不能被认证请求改写。
- **接收与超时必须分流**：`receive`（`:360-381`）只调用
  `k60_battmgr_receive`，`requestAction`（`:407-418`）只处理
  `manager.flight` 并调用 `k60_battmgr_timeout`（会毒化 epoch）。认证在途时应走
  `k60_charge_auth_receive`/`k60_charge_auth_timeout`，不能毒化电池 manager 的
  epoch；真正断链时再统一走 `k60_battmgr_channel_down` 和
  `k60_charge_auth_reconnect`。
- **定时器粒度不一致**：`K60Battery` 的请求超时是 3000 ms（`kRequestMs`，
  `:25`），而认证的 VDM state 截止是 2000 ms、HostRole 截止是 5000 ms。
  认证不能只靠 `requestTimer` 判超时；`pollAction` 每 20 ms 调用 `pump` 时也要
  让状态机检查自己的 `due_ms`/`deadline_ms`。
- **PD 判定缺少字段**：`k60_charge_auth_observe` 只把 USB type 6/7/8 当作 PD；
  K60 的 `K60BatterySample` 只有 `adapter_type`（property 7），
  `K60Battmgr` 没有请求 USB type 6。直接拿 `adapter_type` 顶替会把“适配器类型”
  当成“线缆类型”；新增 property 6 又可能因固件不应答而毒化 epoch。接线前必须先
  做产品决策：找 UCSI/TypeC 路径，或明确只认证电量计并跳过适配器 HostRole。
- **crypto 适配层可行但未写**：XNU 已有 `<libkern/crypto/sha2.h>`
  （`NativeRamBlock.cpp:12`、`PongUfsTransport.cpp:22` 已用），sheng 的
  `chargeRandom` 用 `read_random`，`chargeHmac` 用 SHA-256 加 0x36/0x5c
  的 HMAC 构造。接线条目里应先用 host 已知向量验证 HMAC，再接内核回调。
- **默认关闭**：即使接线完成，也应先用独立 boot-arg 默认关闭；首次上机只观察
  认证请求/应答计数，不把认证结果当作充电许可。

### 6.2 接线落地（2026-11-18 20:30）

- `K60Battery.cpp` 增加 `auth`、`authEnabled`、52 字节 `authBuffer`、`authQueued`/
  `authSent`、`authTurn`；`pump` 与电池 manager 交替取请求，`QcomGlinkAgain` 时
  重发保存的缓冲，不再次 `next`。
- `receive` 先分流 `auth.pending` 的应答；`requestAction` 先处理认证超时，清槽位、
  `stale()`、置 `channelDeadline` 并 `reopen`/关闭通道，迟到应答被旧通道丢弃。
- 样本失配时 `observe(0)` 暂停认证并取消排队；只有 fresh sample 的 property 7
  ∈ {6,7,8} 才重新开始。
- `state()` 在通道 up/down 时重置 `authTurn`；通道 down 走 `k60_charge_auth_reconnect`，
  保留 gauge 数与未完成槽位语义。
- 构建脚本把 `K60ChargeAuth.c` 加入 archive；`K60Battery.cpp` 单独加
  `-I <tree>/.cache/xnu-work/EXTERNAL_HEADERS` 以解析 `libkern/crypto/sha2.h`。

## 7. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:82-88`、`:81`。
- sheng：`origin/main` `package/ShengChargeAuth.c`、`.h`、`package/ShengBattery.cpp`、
  `package/tests/charge_auth_host.c`。
- K60 分支：`feat/charge-auth`，提交 `5449a0bf`、`ab96b0b5`、`c6c0307a`、`685aecb0`。
- 电池测量与固件所有权：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md` §9。
