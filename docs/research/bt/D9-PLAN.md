# d9 单变量飞行计划（bt-0516-uart-clock，2026-11-17）

状态：**2026-11-17 12:03 已飞，结果 FAIL（NVM ret=-60、power=-60）。** 本页原为飞行前计划；用户在 11:56 明确授权后，bt-agent 只执行了一次 `fastboot boot`，未 flash、未写 persist。

## 1. 唯一变量

- 基线：d8 观测镜像 `E:/iOS Port/Work/artifacts/bt-d8-tlv/boot.img`，
  sha256 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`，201,887,744 B。
- 候选：`E:/iOS Port/Work/artifacts/bt-0516-uart-clock/boot.img`，
  sha256 `8a211a7608186990951a94a6c26b04dc0c1d4ea53ab937cbcfb55d8acc447095`，201,887,744 B。
- 与 d8 的唯一运行时差别：`patches/xnu/0516-k60-bt-qbt-uart-clock.patch`
  （135 行，4 文件 +35/-10，sha256 `0134a31bedb65fe6669a7ce7745bc5b9fcb6a7cd44ac66f96f3f604bb01ac6c8`），
  即 QcaBluetooth `986d631` 的 control-byte 时钟/拒写重试修复。
- 不改：90 s boot budget、10 s command deadline、243 B 段长、下载模式/type、状态机、时钟/SMMU/窗口、
  106 文件固件、`board.toml`、任何地址。d8 产物保持不动。

## 2. 候选身份与离线证据

| 项 | 值 |
| --- | --- |
| build manifest | `E:/iOS Port/Work/artifacts/bt-0516-uart-clock/build-manifest.json` |
| 构建时间 / tag | `2026-11-17T01:47:01+08:00` / `bt-0516-uart-clock` |
| repo head / dirty | `32243230a5d7fccac3c19d76e9daae2bcbaf0bb5` / 0 |
| series | 236 条；`e7de39278e0eb0da1c5a5036e0645466885678eefdf57835e279f0bef2717db2` |
| kernel.log | `:253` 记录 `0516-k60-bt-qbt-uart-clock.patch` |
| boot.img | `8a211a7608186990951a94a6c26b04dc0c1d4ea53ab937cbcfb55d8acc447095` |
| payload / payload_kernel | `ad412eb7f036f47135f0eb2aac11423a2b0c74ded71727e3c3234c28a68e6aa7` / `04a9f9285338a551b13517b0135a3e6e82505679a33a961584300d988e95bf08` |
| bt_blob | `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037` |
| boot.json | `hardware_tested=false`，非设备飞行 |

离线检查（2026-11-17 01:57）：

- `python3 scripts/eight-step-gate.py --flash` → 7 个硬件项（touch, gpu, storage, display,
  bootchain, bluetooth, battery），56 项通过，RC=0；日志
  `E:/iOS Port/Work/scratch/bt-s4/0516-flash-gate-20261117.log`。
- `python3 scripts/verify-boot-image.py --manifest .../build-manifest.json` → OK。
- `python3 scripts/check-image-args.py --image ... --board board.toml` → 31 arguments / 598 bytes，OK。
- 宿主 0516 套件 81 cases、d8 adapter 90 cases、0514 33、0515 28，全部 0 failure；
  这是 host-only 软件契约，不是控制器/UART/DMA/IBS 证据。

## 3. 飞前检查（Lead 执行，任何一项红就不飞）

1. `bash scripts/k60-device.sh state` 返回 `fastboot`；记录设备序列 `6033dbec`。
2. `sha256sum E:/iOS Port/Work/artifacts/bt-0516-uart-clock/boot.img` 必须等于
   `8a211a7608186990951a94a6c26b04dc0c1d4ea53ab937cbcfb55d8acc447095`。
3. `python3 scripts/verify-boot-image.py --manifest E:/iOS Port/Work/artifacts/bt-0516-uart-clock/build-manifest.json` → OK。
4. 保留 d8 回滚镜像 `E:/iOS Port/Work/artifacts/bt-d8-tlv/boot.img`（sha `0297012d...`）。
5. 只用 `fastboot boot`；绝不 `fastboot flash`，绝不写 `persist` / `/dev/block/sda38`。

## 4. 执行

```sh
bash scripts/k60-device.sh state
bash scripts/k60-device.sh boot E:/iOS Port/Work/artifacts/bt-0516-uart-clock/boot.img
```

按现有 usblog 流程采集 console 与 `boot.json` / `capture.json`；保留完整日志与屏幕照片（若早期失败）。

## 5. 预先写死的判据

### d8 的时序事实（为什么 0516 值得单变量飞行）

- d8 console 共 630 条 `tlv seg`：621 条 `dt_ms=0`；9 条非零：PATCH 最后一段
  i=601 `dt_ms=10001 e=0`，NVM 第一轮 i=0..5 各 `dt_ms=10000/10001 e=0`；这 7 段合计
  70,004 ms。
- 随后 NVM i=6 在 15 ms 内以 -60 结束（90 s 预算已耗尽）；fallback i=0..19 `dt_ms=0`，
  i=20 `dt_ms=16 e=-60`，最后再次因预算以 -60 结束；全部非零 dt 合计 70,035 ms。
  0516 针对的正是“控制字节排在停钟之后”的 10 s 等待；这只是假设，d9 必须用下面的判据确认，
  不能从 d8 反推已修好。

### 成功（全部满足才算）

- `boot.json`：`imageSha256` 等于 `8A211A76...`（大小写不敏感）、`bootAccepted=true`、
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

- 不得从 `sent/acks/final` 推断 NVM 完成；`final=1` 只是累计 status，不是完成布尔。
- 不得把“没有崩溃/没有 panic”当成功。
- 不得把预算耗尽解释成“控制器慢”或“NVM 全部正常”；必须看新增观测。

## 6. 结果处理

- 成功：记录为“0516 传输修复在本次 d9 观测中命中”，下一阶段才是 HCI/蓝牙栈功能验证；
  仍然不能宣称“蓝牙已修好”。
- 失败：保留 d8 基线，按 console 的实际行判断；在 Lead 批准前不改预算、段长、下载模式、状态机或地址，
  不做第二次猜测式改动。
- 任何离线门红：停飞，先修证据，不带已知未闭合项上机。

## 7. 边界

- bt-agent 不开机、不刷机；设备观测与 d9 由 Lead 执行或明确授权。
- d8 产物、d8 结论（PATCH 软件路径返回成功、两次 NVM 失败、`result=-60`、蓝牙不可用）不变。
- 本页不改变 `EIGHT-STEPS.toml` 的 ⑧，也不把 0516 宿主用例算成设备证据。

## 8. d9 实飞结果（2026-11-17 12:03，FAIL）

- 证据目录 `E:/iOS Port/Work/evidence/usblog-20261117-115842`；boot.img `8a211a7608186990951a94a6c26b04dc0c1d4ea53ab937cbcfb55d8acc447095`，boot.json `bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`；capture.json `complete=true`、`bytes=282532`、`panicMarker=null`、`resetMarker=null`、`stopReason=budget`。
- console：PATCH `tlv done type=1 segs=602 sent=602 acks=1 final=0 ret=0`；NVM 第一次 `type=2 segs=7 ret=-60`；fallback `type=2 segs=21 ret=-60`；`power=1 result=-60`；仍无 `nvm done`。
- 对预声明判据：镜像哈希、boot 接受、capture 完整通过；但出现 `boot: budget exhausted`、最后一个 NVM `done type=2 ret=-60`、`power=1 result=-60`，因此 **FAIL**。
- 结论：0516 的 UART-clock/control 修复没有改变 NVM 失败形状；它不是足够修复。下一步在未取得控制器/UART 新观测前不要改预算、段长、下载模式、状态机或地址。
