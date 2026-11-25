# marconi / AOP：Pong 用户态蓝牙栈的缺口（2026-11-16）

本文件记录一条**不再重复挖**的结论：内核侧的蓝牙 HCI 链路已经打通，
但 Pong 上的用户态蓝牙栈被上游**主动禁用**，缺一个 ADT 节点也修不好。

## 1. 内核侧已经证明的东西

- `patches/xnu/0509-k60-bt-s3-identity-publish.patch` 的 `MiniBluetoothPublishStub()`
  在设备树里建了 `/arm-io/bluetooth` 节点，属性为
  `device_type="bluetooth"`、`compatible="qcom,wcn7850-bt"`、
  `unixnu,adt-name="bluetooth"`、`local-mac-address`。
- 实飞日志（`usblog-20261116-064150`，d5 图 `bt-d5-iomap`）：
  - `:186 K60 BT: published local address ee:98:c5:8a:6b:4e` —— 发布发生了；
  - `:1347 bluetooth: Got local-mac-address: ee:98:c5:8a:6b:4e` —— 有一方读到了。
- 同一次飞行里，`qbt_boot()` 已经把控制器拉到可通信状态：
  - `:709 QCA controller version 0x12110201`（读回版本寄存器）；
  - `:710 addon: serving 146068 0`（rampatch TLV 被控制器取走）；
  - `:726 addon: serving 6442 0`（NVM 被控制器取走）。
- ⇒ **内核侧 HCI 传输（GENI/QUP UART + 固件下载）成立**，不是「蓝牙完全没通」。

## 2. 用户态仍然失败的证据

同一次飞行的 userspace 段：

- `:1345 marconi-bt: Unable to match bluetooth service in device tree.`
- `:1346 marconi-bt: Not a valid MAC address (all 00s)`
- `:1347 bluetooth: Got local-mac-address: ee:98:c5:8a:6b:4e`
- `:1459 com.apple.server.bluetooth: Server attached`

`:1345` 说明 `marconi-bt` **找不到它要的那个服务节点**，而 `/arm-io/bluetooth`
确实存在（`:186`/`:1347` 证明）。⇒ 它找的**不是** `/arm-io/bluetooth` 这个位置。

## 3. marconi 的真身：AOP / SPU 上的控制通道，不是 HCI 传输

对 kernelcache 做 `strings -a -n 8`，marconi 相关驱动是：

| 驱动 | IONameMatch | 说明 |
| --- | --- | --- |
| `AppleA7IOPV2Marconi` | `iop-marconi,s8000` | A7 IOP 上的 marconi 端点 |
| `AppleR5IOPT8006` | `iop-marconi,t8006` | R5 IOP 上的 marconi 端点 |
| `AppleSPUMarconiControl` | `aop-marconi-bt-control` | AOP 上的蓝牙控制通道 |

这三者都是 **AOP/SPU 侧的控制通道**（电源、唤醒、状态同步），
不是 PCIe/UART 上的 HCI 传输端点。真机 iPhone 上，蓝牙 HCI 走的是
`AppleBluetoothModule` 之类的传输驱动，marconi 只负责与 AOP 通话。

## 4. Pong 是故意挡掉 bluetoothd 的

`UniXNU-pong/userland/board_services18.py:84-89` 对 `com.apple.bluetoothd`
设了：

    _LimitLoadToDeviceTree = ['bluetooth', 'marconi-bt']

注释原文：*"requires a real Pong Bluetooth transport; none implemented"*。

⇒ Pong 的 userland 生成器**主动**把 `bluetoothd` 限制在「设备树里存在
`bluetooth` 或 `marconi-bt` 服务」这一条件下，而 Pong 从来没有实现过
真正的 Pong 蓝牙传输端点。这不是我们漏了一个 ADT 节点，是上游设计上
这条路就不通。

## 5. 结论（不再重复挖）

**内核侧 HCI 已通**（读到控制器版本、rampatch/NVM 被取走），
**用户态栈在 Pong 上被主动禁用**，属上游设计缺口，**不在本线范围**。

- 不要为了 `:1345` 去改 0509 的属性名、不要在 `board.toml` 里补
  `marconi-bt` 服务节点 —— 两者都不会让 `bluetoothd` 起来。
- 本线的判据停在**内核侧**：`[bluetooth] power=1 result=0` 与
  `QCA controller version` 行是否出现，以及 `qbt_boot()` 是否返回。
- 用户态栈若要打通，需要另开一条线：实现 Pong 的蓝牙传输端点
  （AOP marconi 控制通道 + HCI 传输），那是上游 userland 的工作。

## 6. 引用

- 证据：`E:\iOS Port\Work\evidence\usblog-20261116-064150\console.log`（d5 图 `bt-d5-iomap`）
- 内核侧发布：`patches/xnu/0509-k60-bt-s3-identity-publish.patch`
- userland 限制：`UniXNU-pong/userland/board_services18.py:84-89`
- 飞行记录：`docs/research/bt/S4-SPEC.md` §7.13、`docs/research/bt/HANDOFF.md` item 27
