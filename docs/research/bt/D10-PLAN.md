# d10 单变量飞行计划（bt-0517-power-order，2026-11-18）

状态：**计划，未批准、未上机。** 候选产物已于 2026-11-18 16:47 构建并通过离线门禁；是否飞行由 Lead 决定。bt-agent 不开机、不刷机。

## 1. 唯一变量

- 回滚基线：d8 观测镜像 `E:/k60-work/artifacts/bt-d8-tlv/boot.img`，
  sha256 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`。
- 上一候选：d9 `E:/k60-work/artifacts/bt-0516-uart-clock/boot.img`，
  sha256 `8a211a7608186990951a94a6c26b04dc0c1d4ea53ab937cbcfb55d8acc447095`，已 FAIL。
- 候选：`E:/k60-work/artifacts/bt-0517-power-order/boot.img`，
  sha256 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`，201,887,744 B。
- 与 d9 的唯一运行时差别：`patches/xnu/0517-k60-bt-power-order.patch`
  （64 行，3 hunk，sha256 `ebd0fe356a28281169b6d6aebe177020672ccbe4237a8b78735a4429ec7f5cbe`），
  只改 `k60_bt_power_on` 的顺序与 `K60_BT_EN_LOW_MS/HIGH_MS`：
  BT_EN 低 100 ms → 串口时钟 → QUP/engine → UART/wake IRQ → XO pulse/BT_EN 高 → 60 ms → 引脚 → `qbt_geni_start`。
- 不改：90 s boot budget、10 s command deadline、243 B 段长、下载模式/type、状态机、时钟/SMMU/窗口、
  106 文件固件、`board.toml`、任何地址。d8 产物与 d9 产物都保持不动。

## 2. 候选身份与离线证据

| 项 | 值 |
| --- | --- |
| build manifest | `E:/k60-work/artifacts/bt-0517-power-order/build-manifest.json` |
| 构建时间 / tag | `2026-11-18T16:47:01+08:00` / `bt-0517-power-order` |
| repo head / dirty | `2c7d948dc5f8c6f597cf708c4fb2e34a960c4564` / 0 |
| series | 237 条；全文件 `3339e34f664d8eee48ab366ec98bffd00018aafe82821c1b7f9b5eecd8dcbcba`；前 236 行 `e7de3927…` |
| 0517 / base / applied | 补丁 `ebd0fe35…`；base `35887d2f8d7fea837fd25937e74e32fdeaf0b37b7c02e04fd7ac7e1be8a0f6ca`；applied `4a3947d5926d8a636d29d914530509cdf7208ed46fcb3e2022002798e8792b0e`（2235 行） |
| kernel.log | `:254` 记录 `0517-k60-bt-power-order.patch` |
| boot.img | `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69` |
| kernel / payload / payload_kernel | `c40e42770038054443264583bd1b1646650abacf5b353e54b914607b283e73f6` / `9acde5345d716f09c4a4a457026c2c49aab80be9472d18256c5380765554c254` / `a44053e4473c094718df4ca21985e0541c59d0e22d231269b021647dbf7c1bb2` |
| ADT / dtb / fd / bt_blob | `db9982047de192883a54d1849606795f08d2913513316eb040d872f04901833f` / `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` / `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` / `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037` |
| boot.json | `hardware_tested=false`，非设备飞行 |

离线检查（2026-11-18）：

- `python3 scripts/verify-boot-image.py --manifest .../build-manifest.json` → `verify-boot-image: OK`。
- `python3 scripts/check-image-args.py` 由构建记录为 `image-arg-audit: OK (31 arguments, 598 bytes)`。
- 八步 build 6 项通过；kernel archives 4 个全在 kernel.macho；metal/bt blob container self-consistent。
- 宿主 0517 套件 52 cases、0516 套件 82 cases、d8 adapter 90 cases，全部 0 failure；
  这是 host-only 软件契约，不是控制器/UART/DMA/IBS 证据。

## 3. 飞前检查（Lead 执行，任何一项红就不飞）

1. `bash scripts/k60-device.sh state` 返回 `fastboot`；记录设备序列 `6033dbec`。
2. `sha256sum E:/k60-work/artifacts/bt-0517-power-order/boot.img` 必须等于
   `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`。
3. `python3 scripts/verify-boot-image.py --manifest E:/k60-work/artifacts/bt-0517-power-order/build-manifest.json` → OK。
4. 保留 d8 回滚镜像（`0297012d…`）与 d9 上一候选（`8a211a76…`）。
5. 只用 `fastboot boot`；绝不 `fastboot flash`，绝不写 `persist` / `/dev/block/sda38`。

## 4. 执行

```sh
bash scripts/k60-device.sh state
bash scripts/k60-device.sh boot E:/k60-work/artifacts/bt-0517-power-order/boot.img
```

按现有 usblog 流程采集 console 与 `boot.json` / `capture.json`；保留完整日志与屏幕照片（若早期失败）。

## 5. 预先写死的判据

### 为什么 0517 值得单变量飞行

- 官网 `https://unixnu.com/zh/porting/bluetooth` 明确要求：BT_EN 拉低 100 ms → 串口时钟 →
  QUP version/protocol → engine → UART/wake IRQ → BT_EN 拉高 60 ms → 引脚。
- d8/d9 的 K60 顺序是 BT_EN 低 50 ms → XO/BT_EN 高 → 50 ms → 串口时钟/engine/IRQ，
  即 BT_EN 在时钟和 engine 之前拉高，且低/高电平都比官网短。
- d8 与 d9 的 NVM 失败形状相同：PATCH 602 段后，NVM 第一轮在 i=5 附近出现约 10 s 等待，
  随后 `budget exhausted`、`ret=-60`；fallback 也在约 20 段后撞预算。0517 只消除“上电顺序/时序”
  这一个官网差异；若失败形状改变，说明该差异相关；若完全不变，说明 NVM 根因不在这一项。
- 这是假设检验，不是从 d8/d9 反推 0517 已修好。

### 成功（全部满足才算）

- `boot.json`：`imageSha256` 等于 `6C631BC4...`（大小写不敏感）、`bootAccepted=true`、
  `bootExitCode=0`、`returnedToFastboot=false`。
- `capture.json`：`complete=true`、`panicMarker=null`、`resetMarker=null`；`stopReason` 不作为成功条件。
- console 出现 `[bluetooth] boot: enter speed=3000000 budget=90000ms`。
- PATCH 流程结束；最后一个 `[bluetooth] tlv done type=2 ...` 的 `ret=0`（不是 `ret=-60`）。
- 没有 `[bluetooth] boot: budget exhausted`。
- 最终 `[bluetooth] power=1 result=0`（若日志格式仍是 `result=%d`）。
- 这只证明“传输/下载软件路径在这次观测中没有撞预算且 NVM 调用返回 0”，
  **不证明控制器逐段接受、NVM 内容正确或蓝牙可用**。

### 失败（任一出现即失败）

- `boot: budget exhausted at op=...` 再次出现。
- NVM 任一段最后 `e=-60`，或 `done type=2 ... ret=-60`。
- `power=1 result=-60`、panic、reset、镜像哈希不匹配。
- 日志缺失、采集不完整：判“未定位”，不是成功，也不是“慢”。

### 禁止的推断

- 不得从 `sent/acks/final` 推断 NVM 完成；`final=1` 只是累计 status，不是完成布尔；
  `acks=1` 也不证明 602 段逐段被控制器接受。
- 不得把“没有崩溃/没有 panic”当成功。
- 不得把预算耗尽解释成“控制器慢”或“NVM 全部正常”；必须看新增观测。
- 不得用 d8/d9 的失败形状替代 d10 的实际 console。

## 6. 结果处理

- 成功：记录为“0517 的官网上电顺序/100-60 ms 在本次 d10 观测中消除了 NVM 预算失败”；
  下一阶段才是 HCI/蓝牙栈功能验证。仍然不能宣称“蓝牙已修好”。
- 失败且形状不变：说明上电顺序不是 NVM -60 的充分原因；下一步应增加控制器/UART 观测
  （例如 `trace_hci` 或 vendor TLV 事件），而不是直接改预算、段长、下载模式、状态机或地址。
- 失败但形状改变：保留完整 console，按新增的首个异常行定位；仍须 Lead 批准后才能改下一项。
- 任何离线门红：停飞，先修证据，不带已知未闭合项上机。

## 7. 边界

- bt-agent 不开机、不刷机；设备观测与 d10 由 Lead 执行或明确授权。
- d8 产物、d8 结论（PATCH 软件路径返回成功、两次 NVM 失败、`result=-60`、蓝牙不可用）不变。
- d9 的 FAIL 结论不变；0517 不是对 d9 的追认，而是新的单变量。
- 本页不改变 `EIGHT-STEPS.toml` 的 ⑧，也不把 0517 宿主用例算成设备证据。
- 未批准前不飞、不重建、不改预算/段长/状态机/地址。
