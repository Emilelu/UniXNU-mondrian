# K60 充电认证移植（power §4 :82-88）

日期：2026-11-18。范围：官网 power 页 §4「sheng 的 PD、PPS 和 MiPPS」（快照
`E:/k60-work/scratch/power-page-20261117.txt:82-88`）。本文记录 **独立的
`feat/charge-auth` 分支**：协议状态机已移植并通过 host 断言，但还没有接进
`K60Battery`/`K60Battmgr`，没有 crypto 适配层，没有 UCSI 数据角色路径，也没有上机。
按用户 2026-11-18 的指示，充电认证单独开分支；上机测试与插拔测试另行安排。

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

- **没有接线**：`K60Battery.cpp`/`K60Battmgr.c` 不引用 `K60ChargeAuth`，
  `scripts/build-k60-physical-battery.py` 的源列表也没有这两个文件，因此
  `build/k60-battery/libK60PhysicalBattery.a` 与 image g/h/i 都不包含它。
- **没有 crypto 适配层**：`K60ChargeCrypto.random`/`hmac` 必须由板级提供；
  XNU 有 SHA-256 但本树还没有把 HMAC-SHA256 包成这两个回调，也没有随机源接线。
- **没有数据角色路径**：K60 树里 grep 不到 UCSI/TypeC 驱动，`host_ready` 没有设置者；
  若适配器 PDO2 有效，状态机在 HostRole 等 5 s 后以 `-95` 失败。电量计认证仍可完成。
- **没有充电控制**：不写充电器、不改限流、不做 PD/PPS 合约或温控策略，符合官方 `:81`
  的所有权边界；认证成功只表示“电量计/适配器身份得到确认”，不表示功率协商成功。
- 密钥与种子是协议公开常量，源文件按 sheng 原样移植；本文不复制密钥值。

## 5. Host 断言

`scripts/tests/test-k60-charge-auth.c`，85 项，0 失败；ASan/UBSan 下同结果：

```sh
cc -Wall -Wextra -Werror -std=c11 -Idrivers/PongPower \
  scripts/tests/test-k60-charge-auth.c drivers/PongPower/K60ChargeAuth.c -o /tmp/tca
/tmp/tca   # TESTS OK 85 checks (0 failures)
```

覆盖：单/双电量计 ack、challenge→digest→mark、适配器 SVID/PDO2 分支、9 次重试后
tries=10/result=`-60`、reconnect 后旧应答被吞掉、52 字节 Get 短应答拒绝 `-61`、
18 个诊断属性含一个错误后进 Done、错误 property 的应答被忽略。

## 6. 下一步

1. 在 `K60Battmgr` 的串行请求队列里加认证状态机的槽位，保持“一次一个未完成请求”。
2. 用内核 SHA-256 实现 HMAC-SHA256 与随机源回调，先做 host 对端校验。
3. 找到 K60 的 TypeC/UCSI 数据角色路径，或在没有该路径时明确只认证电量计、跳过适配器
   HostRole（需要产品决策）。
4. 通过 boot-arg 默认关闭，接入后再构建新镜像；上机前先确认 `K60Battmgr` 的
   epoch/超时语义不被认证请求破坏。

## 7. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:82-88`、`:81`。
- sheng：`origin/main` `package/ShengChargeAuth.c`、`.h`、`package/ShengBattery.cpp`、
  `package/tests/charge_auth_host.c`。
- K60 分支：`feat/charge-auth`，提交 `5449a0bf`、`ab96b0b5`。
- 电池测量与固件所有权：`docs/research/charger/10-POWER-DOC-CONFORMANCE.md` §9。
