# d11 累积飞行计划（bt-0518-gic-intid，2026-11-18）

状态：**d11 已于 2026-11-18 22:19 飞行，PASS。** 候选产物于 18:08 构建并通过离线门禁；d10（0517）21:32 飞行 FAIL，d11（0517+0518）22:19 飞行 PASS，NVM 预算失败消失，见 §9。0518 由此获得单一变量因果证据：UART RX 中断此前挂在 INTID 587 而不是 619，每段 ack 只能等 10 s 命令期限。

## 1. 先读：d11 不是 d10 的替代品

- d10 = 0517 单变量，候选 `E:/iOS Port/Work/artifacts/bt-0517-power-order/boot.img`，sha256 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`，**已于 2026-11-18 21:32 飞行，FAIL**（见 `D10-PLAN.md` §8）。
- d11 = 0517 + 0518 累积候选，候选 `E:/iOS Port/Work/artifacts/bt-0518-gic-intid/boot.img`，sha256 `d6beec4c6bfbb09c1d11076db0239ead0ee357dd2ba58bfb4f92a69c9d7158ec`，**已于 2026-11-18 22:19 飞行，PASS**（见 §9）。
- **相对 d10 的唯一运行时差别是 0518**（GIC INTID 修正）。相对 d9（0516）则同时多了 0517 和 0518 两个变量。
- 因此权威顺序是 **先 d10，后 d11**；d10 已飞 FAIL，但 fallback 从 d9 的 21 段变成 1 段，失败形状并非完全不变。
  - d10 FAIL 且失败形状不变 → d11 才有单变量意义：只把 0518 叠在 d10 上，检验“UART/TLMM handler 挂错 INTID”是否为 NVM 失败的原因。
  - d10 PASS → NVM 失败已由 0517 消除；**不要为了 NVM 再飞 d11**。0518 仍是真实的源码缺陷，但它的验证应另立目标，不能借 d10 的成功把 0518 一起追认。
  - 本次 d10 FAIL 但形状改变；d11 相对 d10 仍是单变量，已于 22:19 飞行 PASS：NVM 27 段全部在 1 ms 量级完成，证明此前的 ~10 s/段不是控制器慢，而是 UART RX 中断未送达、每段只能等 10 s 命令期限。
- 只有明确豁免 d10 时，d11 才可作为“0517+0518 累积候选”飞行；此时相对 d9 是两个变量，**不得声称单变量，也不得把结果单独归给 0517 或 0518**。

## 2. 0518 改了什么

- 新常量：`K60_BT_UART_GIC_INTID = (32u + K60_BT_UART_GIC_SPI)` = **619**；`K60_TLMM_GIC_INTID = (32u + K60_TLMM_GIC_SPI)` = **240**。
- 四个调用点全部改用 INTID：`k60_gic_mask`、`armcpu_spi_mask`、UART 的 `armcpu_spi_attach`、TLMM wake 的 `armcpu_spi_attach`。
- 依据：`drivers/ArmCpu/ArmCpu.cpp:784-814` 的 `armcpu_spi_attach(uint32_t intid, ...)` 直接拿 `intid` 写 `GICD_ISENABLER` / `GICD_IROUTER` / `GICD_ICFGR`，并拒绝 `intid < 32`；它要的是 GIC INTID，不是 DT 的 SPI 号。既有调用者也都是 `SPI + 32`（UFS 265+32、PCIe 32+140、pong 32+481）。
- 旧代码直接传 587 / 208，实际把 UART RX handler 挂到了 INTID 587、TLMM handler 挂到了 INTID 208；真实线是 619 / 240。症状与 d8/d9 的 10,000/10,001 ms 应答一致：handler 收不到 RX 中断，`qbt_geni_service` 只能靠健康定时器或 10 s 命令期限运行。
- 这是**源码对照得出的具体缺陷**，不是设备计数器证明；d8/d9 console 没有 IRQ attach 行或中断计数，不能把“10 s”单独当成 INTID 证据。
- 0518 不改 0517 的上电顺序/100-60 ms、90 s budget、10 s command deadline、243 B 段长、下载模式/type、状态机、SMMU、地址或固件。

## 3. 候选身份与离线证据

| 项 | 值 |
| --- | --- |
| build manifest | `E:/iOS Port/Work/artifacts/bt-0518-gic-intid/build-manifest.json` |
| 构建时间 / tag | `2026-11-18T18:08:47+08:00` / `bt-0518-gic-intid` |
| repo head / dirty | `3aa6910a720eddbc65c5adacfb75660231899450` / 0 |
| series | 238 条；全文件 `4a39a8d2fddf0da93dbcab18a2302c69bab8f34955d56e9172c1a395e8b12e11`；前 237 行 `3339e34f664d8eee48ab366ec98bffd00018aafe82821c1b7f9b5eecd8dcbcba`；前 236 行 `e7de39278e0eb0da1c5a5036e0645466885678eefdf57835e279f0bef2717db2` |
| 0518 补丁 | `patches/xnu/0518-k60-bt-gic-intid.patch`，51 行 / 2,280 B，4 hunk，sha256 `c1e2cb96ac79b26089e4a495741165d800ee8e730b0a460ab2e476853809e13f` |
| base / applied | `4a3947d5926d8a636d29d914530509cdf7208ed46fcb3e2022002798e8792b0e`（2235 行，post-0517）/ `4a1a4e269fce5f2bf3d964f8610d3c7943f3329aed2dce2da681dd45705ef5fb`（2239 行） |
| kernel.log | `:271` 记录 `0518-k60-bt-gic-intid.patch` |
| boot.img | `d6beec4c6bfbb09c1d11076db0239ead0ee357dd2ba58bfb4f92a69c9d7158ec`（201,887,744 B） |
| kernel / payload / payload_kernel | `6f44a07f6d86a0c25e55a152a4587da645314139e2abdad1aa07e8164726b624` / `1a6cf06fdc6ff8380e8dce4bbdb908760b5a9d226094e0e4be42a9ea9bb2ee16` / `46da4e247b91969ed72962f084a5850f97c71d370bcaacbf5eab973c4d85830e` |
| ADT / dtb / fd / bt_blob | `4b91e5495fbf1d30c941030918040fcceb096b75af29976526d6bfd02bb27242` / `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` / `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` / `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037` |
| boot.json | `kernel_sha256=83b52b566b9cd0e0a2f13854f7da4c67175c956d798d009dcf94fc5d7cb7707c`，`hardware_tested=false` |

离线检查（2026-11-18）：

- `python3 scripts/verify-boot-image.py --manifest .../build-manifest.json` → `verify-boot-image: OK`。
- `python3 scripts/check-image-args.py` → `image-arg-audit: OK (31 arguments, 598 bytes)`。
- 八步 build 6 项通过；kernel archives 4 个全在 kernel.macho；metal/bt blob container self-consistent。
- 宿主：0518 套件 **35 cases / 0 failure**；0517 **53 / 0**；0516 **82 / 0**；d8 adapter **90 / 0**。
- **以上全部是 HOST-ONLY + 离线构建证据**，不证明控制器 UART/DMA/IBS、真实 NVM 完成或蓝牙可用。

## 4. 飞前检查（claim 持有者执行，任何一项红就不飞）

1. `bash scripts/k60-device.sh state` 返回 `fastboot`，记录设备序列（当前 `6033dbec`）；不是 fastboot 就停。
2. 按统一 supervisor 的机器级 boot claim 规则取得 claim；若另一个 agent 已持有 claim 或 COM 口已被 collector 占用，**不得启动**。本仓没有 claim 文件，不能用一个本地文件假装 claim。
3. `sha256sum E:/iOS Port/Work/artifacts/bt-0518-gic-intid/boot.img` 必须等于 `d6beec4c6bfbb09c1d11076db0239ead0ee357dd2ba58bfb4f92a69c9d7158ec`。
4. `python3 scripts/verify-boot-image.py --manifest E:/iOS Port/Work/artifacts/bt-0518-gic-intid/build-manifest.json` → OK。
5. d10 与 d11 均已有设备结果：d10（0517）21:32 FAIL；d11（0517+0518）22:19 PASS（本页 §9）。后续若再飞，只能针对新的单变量，不得重复 d11。
6. 回滚镜像必须同时保留并核对：d8 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`，d10 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`。d9 的 `8a211a76…` 当前不可用，不得声称保留。
7. 只用 `fastboot boot`；绝不 `fastboot flash`，绝不写 `persist` / `/dev/block/sda38`。
8. 显式传构建输入，不依赖默认路径：`K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device`。`/opt/k60/trees/usb-cdc-mainline/device` 不存在；不要为此改 `flash.sh` 塞 BT 专用默认值。

## 5. 执行

```sh
export K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device
bash scripts/k60-device.sh state
bash scripts/flash.sh E:/iOS Port/Work/artifacts/bt-0518-gic-intid/boot.img
```

`flash.sh` 先跑 porting / 八步（flash）/ 启动流程 / 研究四道门，再由单一 supervisor 先武装 capture 再 `fastboot boot`。保留完整 console、`boot.json`、`capture.json` 与屏幕照片（若早期失败）。

## 6. 预先写死的判据

### 为什么 0518 值得在 d10 之后单变量飞行

- 0517 检验的是官网上电顺序/100-60 ms；0518 检验的是另一个独立缺陷：UART/TLMM 的 GIC handler 挂错 32 个 INTID。
- d8/d9 的 NVM 第一次 i=0..5 每段约 10,000 ms、fallback i=0..19 为 0 ms、i=20 立即失败，形状与“RX 中断没送到，只能等 10 s 期限”一致；但这是**假设**，必须由 d11 的实际 console 判决。
- 如果 d10 失败且 d11 成功，0518 是唯一差别，才能说“INTID 修正消除了本次 NVM 失败形状”。如果 d10 已经成功，d11 对这个症状没有信息量。

### 成功（全部满足才算）

- `boot.json`：`imageSha256` 等于 `D6BEEC4C...`（大小写不敏感）、`bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`。
- `capture.json`：`complete=true`、`panicMarker=null`、`resetMarker=null`；`stopReason` 不作为成功条件。
- console 出现 `[bluetooth] boot: enter speed=3000000 budget=90000ms`。
- PATCH 流程结束；没有 `[bluetooth] boot: budget exhausted`。
- 最后一个 NVM attempt 的 `[bluetooth] tlv done type=2 ...` 为 `ret=0`（不是 `-60`）。
- 最终 `[bluetooth] power=1 result=0`（若日志格式仍是 `result=%d`）。
- **不要求**新的 IRQ 计数行：当前 console 没有 attach/ack 计数器，不能把不存在的观测写成成功条件。
- 这只证明“本次传输/下载软件路径没有撞预算且 NVM 调用返回 0”，**不证明控制器逐段接受、NVM 内容正确、HCI 可用或蓝牙可配对**。

### 失败（任一出现即失败）

- `boot: budget exhausted at op=...` 再次出现（尤其 NVM `op=0xfc00`）。
- NVM 任一段最后 `e=-60`，或 `done type=2 ... ret=-60`。
- `power=1 result=-60`、panic、reset、镜像哈希不匹配。
- attach 相关错误导致 power 失败（按 console 的首个错误行记录，不自行补原因）。
- 日志缺失、采集不完整：判“未定位”，不是成功，也不是“慢”。

### 禁止的推断

- 不得因为 `armcpu_spi_attach` 返回 0 就说 INTID 修好了：旧代码同样返回 0，只是写了一条合法但错误的 INTID。
- 不得从 `sent/acks/final` 推断 NVM 完成；`final=1` 是累计状态，不是完成布尔；`acks=1` 也不证明 602 段逐段被控制器接受。
- 不得把“没有崩溃/没有 panic”当成功。
- 不得把预算耗尽解释成“控制器慢”或“NVM 全部正常”；必须看新增观测。
- 不得用 d8/d9/d10 的失败形状替代 d11 的实际 console。
- 不得在未获批准时改 budget、10 s deadline、243 B 段长、下载模式/状态机、地址或 SMMU。

## 7. 结果处理

- **d10 FAIL、d11 PASS**：记录为“在 0517 之上，0518 是唯一差别，NVM 预算失败消失”；下一阶段才是 HCI/蓝牙栈功能验证。仍不能宣称“蓝牙已修好”。
- **d10 FAIL、d11 FAIL 且形状不变**：0518 不足以解释 NVM -60；下一步增加控制器/UART 观测（如 `trace_hci` 或 vendor TLV 事件），而不是直接改预算、段长、下载模式、状态机或地址。
- **d10 FAIL、d11 FAIL 但形状改变**：保留完整 console，按新增的首个异常行定位；仍须 Lead 批准后才能改下一项。
- **d10 PASS**：d11 不用于 NVM；0518 记为“源码修正、未上机”，若要验证 GIC 修复另立计划。
- **豁免 d10、直接 d11**：只能记录“0517+0518 累积候选”的结果，不得把成功或失败归给其中任一项。
- 任何离线门红：停飞，先修证据，不带已知未闭合项上机。

## 8. 边界

- d10 与 d11 均由 bt-agent 按用户 2026-11-18 先到先得规则、在无其他 supervisor/collector 时飞行；下一次飞行仍须重新确认单设备单写者。
- d8 产物 `E:/iOS Port/Work/artifacts/bt-d8-tlv` 与 d8 结论不变：PATCH 软件路径返回成功、两次 NVM 失败、`result=-60`、蓝牙不可用。
- d9 的 FAIL 结论不变；0518 不是对 d9 或 d10 的追认。
- d11 把 `EIGHT-STEPS.toml` 的蓝牙 device 步从 false 改为 true：设备已观测到 patch+NVM 下载、HCI reset、BD_ADDR 设置和 UART SK 注册成功；这只证明传输/下载路径，不证明蓝牙可用。
- 不再改 budget/段长/状态机/地址；下一步是用户态 DT 的 bluetooth 服务节点与 BD_ADDR 来源。
- 关联：`D10-PLAN.md`、`S4-SPEC.md` §7.25、`HANDOFF.md` item 45、`docs/research/EIGHT-STEPS.toml` 的 bluetooth 块。

## 9. d11 飞行结果（2026-11-18 22:19–22:23，PASS）

- 设备 6033dbec；镜像 sha256 `d6beec4c6bfbb09c1d11076db0239ead0ee357dd2ba58bfb4f92a69c9d7158ec`；命令 `K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device bash scripts/flash.sh /mnt/e/iOS Port/Work/artifacts/bt-0518-gic-intid/boot.img 220`；supervisor rc=0。
- `boot.json`：bootAccepted=true、bootExitCode=0、returnedToFastboot=false，22:19:28 开始、22:23:33 结束。
- `capture.json`：state=captured-budget-complete、complete=true、bytes=278123、panic/reset=null、stopReason=budget；console 278123 B，logSha256 `591CD9A6256F1D16F3D87AE4642DED4D90B73208D9A457D57CBDF50715BB0162`。
- console：PATCH `type=1 segs=602 sent=602 acks=1 final=0 ret=0`；NVM 单轮 27 段，26 段 `dt_ms=1`、末段 124 B `dt_ms=120`，`type=2 segs=27 sent=629 acks=28 final=0 ret=0`；`boot: nvm done`；`boot: hci reset done`；`boot: bdaddr check done`；`boot: uart setup done e=0`；`boot: set bdaddr done e=0`；`boot: return e=0 baud=3000000`；`power=1 result=0 ... firmware=BTFW.HSP.2.1.0-00570-PATCHZ-1 tlv_sent=629 tlv_acks=28 tlv_final=0`；`[bluetooth sk] ctl_register com.apple.uart.sk.bluetooth error=0`。
- 结论：按预声明判据 **PASS**。d11 相对 d10 的唯一运行时差别是 0518，因此 NVM 的 `-60` 与每段约 10 s 停顿由 GIC INTID off-by-32 解释：`armcpu_spi_attach` 需要 INTID，旧代码传 SPI 587/208，UART RX 从未送到 INTID 619，每段 ack 只能等 10 s 命令期限；修正后 ack 在约 1 ms 内到达。0518 是本次修复，不是 0517。这是传输/下载路径的修复，不等于蓝牙可用。
- 用户态仍未完成：`marconi-bt: Unable to match bluetooth service in device tree`、`marconi-bt: Not a valid MAC address (all 00s)`；`bluetoothd` 已由 `xpcproxy` 拉起（console:1680），`com.apple.server.bluetooth` 已 attached 但只进入 msg loop。下一步是设备树的 bluetooth 服务节点与 BD_ADDR 来源，不是再改 NVM。
