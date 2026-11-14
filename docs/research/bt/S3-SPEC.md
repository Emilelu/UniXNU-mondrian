# S3 — 身份与发布：让 bluetoothd 看见「这台机器有蓝牙」

Status: 2026-11-14 写就，离线静态验证通过（`git apply --check` + `clang -fsyntax-only`），
**未上机**。本文件对应 `patches/bt/0003-k60-bt-s3-identity-publish.patch` =
`patches/xnu/0509-k60-bt-s3-identity-publish.patch`（字节相同）。

## 0. 这一步解决什么

`0500` 的内核后端能把 SE20 拉起来、能下固件、能跑 H4，但**用户态根本不会来找它**。
实测证据（`bt-s1-20261114a` 那次健康启动，`E:/k60-work/evidence/usblog-20261114-bts1-run1/console.log`）：

```
com.apple.server.bluetooth: Bluetooth Super Server Robot Destroyer
could not find BT_DEVICE_ADDRESS env variable
marconi-bt: Unable to match bluetooth service in device tree.
marconi-bt: Not a valid MAC address (all 00s).
bluetooth: Unable to match bluetooth service in device tree.
bluetooth: Not a valid MAC address (all 00s).
FindLocalMacAddress did not find bootargs for random address generation
bluetoothd: No bluetooth on this device.
```

三件事同时缺：

1. **设备树节点**：`/arm-io` 下没有 `device_type = "bluetooth"` 的子节点 → `Unable to match bluetooth service in device tree`。
2. **MAC**：节点里没有 `local-mac-address`，`/chosen` 里也没有 `mac-address-bluetooth0`，boot-args 里没有 `wlan.debug.generate-mac`/`wlan.factory` → `Not a valid MAC address (all 00s)`。
3. **IOService**：没有任何叫 `bluetooth` 的服务 → `No bluetooth on this device`。

`0500` 里对这三件事的准备只有一个**弱符号空壳**：

```c
__attribute__((weak)) int k60_bt_local_address(uint8_t address[6]) { (void)address; return -ENOENT; }
```

所以即使 S1/S2 全部通过，worker 也会停在 `-ENOENT`，`qbt_boot()` 根本不会被调用。
S3 就是把这三件事补齐。

## 1. 参照实现（sheng，已在真机跑通）

`E:/hackios/UniXNU-sheng/package/BluetoothProbe.cpp:222-264` 的 `address()`，逐条对应：

| 步骤 | sheng 做法 | 本补丁做法 |
|---|---|---|
| 取种子 | `IORegistryEntry::fromPath("/chosen")` → `getProperty("unique-chip-id")`，要求 ≥ 8 字节 | `SecureDTLookupEntry(NULL,"/chosen")` + `SecureDTGetProperty(...,"unique-chip-id",...)`，要求 ≥ 8 字节 |
| 派生 | FNV-1a：offset `0xcbf29ce484222325`、prime `0x100000001b3`，先过 17 字节域 `"unixnu-bluetooth"`，再逐字节过种子 | 同域、同常量、同顺序（`K60_BT_MAC_DOMAIN`/`K60_BT_FNV_OFFSET`/`K60_BT_FNV_PRIME`） |
| 取 6 字节 | `address[i] = hash >> (i*8)`，然后 `address[0] = (address[0] & 0xfe) \| 2` | 同 |
| 全零种子 | 拒绝（必须见过至少一个非零字节） | 同，返回 `-ENOENT` |
| 写节点 | `node->setProperty("local-mac-address", …)` | 同（`/arm-io/bluetooth`，不存在则建） |
| 写 /chosen | `chosen->setProperty("mac-address-bluetooth0", …)` | 同 |
| 发布服务 | `new IOService` + `setName("bluetooth")` + `device_type/transport-encoding/transport-speed/local-mac-address` + `attach(getPlatform())` + `registerService()` | 同（`K60BluetoothRadio` 子类，`start()` 里 `registerService()`） |

sheng 的 ADT 节点（`dts/sheng.dts:17-25`）是 `transport-encoding = <1>`（H4）、
`transport-speed = <3200000>`；K60 的运行波特率是 `K60_BT_RUN_BAUD = 3000000`，
所以本补丁发布 `transport-speed = 3200000` 会与后端不一致 —— **见 §4 的待决项**。

## 2. 补丁内容（5 个文件，198 增 / 11 删）

1. `bsd/dev/qbt_k60.c`
   - 加 `#include <pexpert/device_tree.h>`（`SecureDTLookupEntry`/`SecureDTGetProperty`）。
   - 删掉 `extern int k60_bt_local_address(...) __attribute__((weak));` 声明。
   - 把弱空壳换成**强定义**：读 `/chosen/unique-chip-id` → FNV-1a → 6 字节本地管理地址。
     失败路径全部 `-ENOENT`（**fail closed**：没有平台种子就宁可不发布，也不发全零 MAC）。
   - worker 调用点去掉 `k60_bt_local_address ? … : -ENOENT` 的存在性判断（定义现在恒在）。
2. `iokit/Kernel/MiniBluetooth.cpp`（**新文件，164 行**）
   - `K60BluetoothRadio : IOService`，`start()` → `registerService()`。
   - `k60_bt_node()`：先找 `/arm-io/bluetooth`；没有就 `OSTypeAlloc(IORegistryEntry)` 建一个，
     打上 `device_type="bluetooth"`、`compatible="qcom,wcn7850-bt"`、`unixnu,adt-name="bluetooth"`、
     `transport-encoding`/`transport-speed`（4 字节小端），再 `attachToParent(armio, gIODTPlane)`。
     这与本树 `publishDisplayNode()`（`…-pong-hackios-ui-foundation.patch:3330-3365`）同一个写法。
   - `MiniBluetoothPublishStub(IOService *)`：`PE_parse_boot_argn("k60bt")` 为 0 时**直接返回**，
     否则算地址 → 建/取节点 → 写两处 MAC → 发布 IOService → `IOLog("K60 BT: published local address …")`。
3. `iokit/Kernel/MiniDrivers.h`：加 `void MiniBluetoothPublishStub(IOService * provider);`。
4. `iokit/Kernel/MiniIOSurface.cpp`：在 `native_pong_ui_services_start()` 里
   `MiniAcceleratorPublishStub(provider);` 之后加一行调用。
5. `iokit/conf/files`：`iokit/Kernel/MiniBluetooth.cpp		optional iokitcpp`。

## 3. 为什么挂在 `native_pong_ui_services_start()` 里

因为**时序**：`bsd/kern/bsd_init.c` 的 `bsd_autoconf()` 里，
`native_pong_ui_services_start()` 在 `k60_usblog_start()` 和 `qbt_k60_start()` **之前**执行；
而 `xpcproxy /usr/sbin/bluetoothd` 要再晚约 850 行控制台才出现
（`E:/k60-work/evidence/usblog-20261114-touchd/console.log:995`）。
把发布点放在这里，节点和 IOService 在 bluetoothd 启动前很久就已经在注册表里了。

`#if` 条件沿用 `0212` 的模板：`defined(PONG) && (DEVELOPMENT || DEBUG) && !SECURE_KERNEL && XNU_K60_BT_PUBLISH`，
与 `MiniAcceleratorES.cpp` 完全一致，所以同一个 kernel 配置下一定会被编译进去
（`iokit/conf/files` 里的 `optional iokitcpp` 在本构建中确实参与编译，`MiniAcceleratorES.cpo` 就是证据）。

## 4. 待决项（Lead 写权限，S3 上机前必须做）

1. **平台种子**：`board.toml:218` 只有 `chip_id = "8015"`，**没有** `unique_chip_id`，
   所以现在构建出来的 `hardware.dtb`（4,024 B）里没有 `/chosen/unique-chip-id`（已 grep 确认）。
   没有种子时 `k60_bt_local_address()` 返回 `-ENOENT`，控制台会打印
   `K60 BT: no platform identity (-2); bluetooth not published`，行为与今天一致（fail closed）。
   两条路任选：
   - 在 `[payload."adt"]` 加 `"unique_chip_id" = "required"`（或直接给一个 16 进制种子），
     然后 `UNIXNU_UNIQUE_CHIP_ID=<hex> scripts/build-strict.sh …` —— `build-strict.sh` 本身不转发
     `--unique-chip-id`，但 `payload.py:160-163` 会读环境变量，而脚本继承调用者环境。
   - 或者给 `build-strict.sh` 加 `--unique-chip-id` 转发（Lead 写权限）。
   注意：种子一旦定下就**不要改**，否则蓝牙 MAC 会变（配对信息作废）。
2. **transport-speed 该写 3200000 还是 3000000**：sheng 写 3200000（它自己的运行波特率），
   K60 后端 `K60_BT_RUN_BAUD = 3000000`。本补丁暂时照抄 sheng 的 3200000，
   但 S5 接 UART.SK 通道时若 BlueTool 拿这个值去设波特率，就会与后端不一致。
   **上机看到 `[bluetooth sk] ctl_register … speed=` 行后按实测值改一次即可**（一行常量）。
3. **DT 节点双保险**：本补丁在注册表里建 `/arm-io/bluetooth`，但**不写进设备树二进制**。
   如果 bluetoothd 走的是 `SecureDTLookupEntry`/DT 平面而不是 IORegistry，还需要
   `board.toml` 加 `[adt.arm-io.bluetooth.string]` + `[adt.arm-io.bluetooth.u32]`（无需改 dts）：

   ```toml
   [adt.arm-io.bluetooth.string]
   device_type = "bluetooth"
   compatible = "qcom,wcn7850-bt"
   "unixnu,adt-name" = "bluetooth"

   [adt.arm-io.bluetooth.u32]
   transport-encoding = 1
   transport-speed = 3200000
   ```

   两者都给最稳（`devicetree.py:372-387` 会把 `[adt.arm-io.*]` 表导出成 `/arm-io` 子节点；
   `dts/mondrian.dts` 里加 `unixnu,adt-name` 节点是另一条等价路径）。

## 5. 预期控制台输出与判据

成功（有种子）：

```
K60 BT: published local address 02:xx:xx:xx:xx:xx
```

然后 bluetoothd 那几行应当**变化**：不再出现 `Unable to match bluetooth service in device tree.` /
`Not a valid MAC address (all 00s).` / `No bluetooth on this device.`。
第一次上机**不要求**蓝牙能用——只要求这三行消失或改变，就证明发布生效。

无种子（当前状态）：

```
K60 BT: no platform identity (-2); bluetooth not published
```

判据表：

| 现象 | 结论 |
|---|---|
| 出现 `K60 BT: published local address …`，且 bluetoothd 不再说 `No bluetooth on this device` | 发布生效，S3 通过 |
| 出现 `K60 BT: no platform identity` | 种子没进 ADT（§4.1 未做），代码本身没错 |
| 连 `K60 BT:` 都没有，且 `k60bt=1` 已带 | 发布钩子没被调用（`native_pong_ui_services_start` 提前 return，例如 `pong_software_ui=0`） |
| bluetoothd 改说 `IOServiceOpen returned …` 之类 | 发布生效但后端没起来 —— 回到 S1/S2 的判据 |
| 板子死机 | 与 S1a 同类：这条路径在 `qbt_k60_start()` 之后，先按 S1c 阶梯定位 |

## 6. 静态验证记录（⑦）

| 项 | 结果 |
|---|---|
| 补丁大小 | 10,265 B / 304 行，sha256 `429630d61fcd06554cc8094ca3381ec49d0485f8c8b025d60f7a5fe8c1208edf`，198 增 / 11 删 |
| 应用检查 | 在「series 全部打完之后」的干净树里 `git apply --check` → OK，apply 成功，`MiniBluetooth.cpp` 164 行 |
| `clang -fsyntax-only` `bsd/dev/qbt_k60.c` | rc=0，0 error，2 warning（均为 0500/0507 既有：`qbt_k60.c:342` `void **` 丢弃限定符、`:1362` `K60_QUP_HW_VER_REG` 重定义） |
| `clang -fsyntax-only` `iokit/Kernel/MiniBluetooth.cpp` | rc=0，0 error，17 warning（全部来自 XNU 头：`cs_blobs.h:199` c99 指定初始化、`IOLib.h:980` 嵌套/乱序指定初始化） |
| 接线 | `patches/xnu/series:207`（`0508` 之后、`0503` 之前），`patches/bt/series` 第三行 |

编译命令（可复现）：`E:/k60-work/scratch/bt-s3/verify3.sh`，它用
`/opt/k60/trees/lead-out/.../ios-obj/DEVELOPMENT_ARM64_PONG/{bsd,iokit}/DEVELOPMENT/.CFLAGS`
跑 `clang -target arm64-apple-ios16.0 -fsyntax-only`（`.CFLAGS` 里有 `-include meta_features.h`，
所以 cwd 必须是 `.CFLAGS` 所在目录）。

## 7. 风险与回滚

- **风险 1**：发布一个叫 `bluetooth` 的 IOService 会让 bluetoothd 提前 attach，然后因为后端没起来而
  打印一堆错误、甚至反复重启 bluetoothd。**缓解**：整条路径由 `k60bt=1` 门控；不带该 boot-arg 的镜像
  注册表与今天完全一致。真出问题时用不带 `k60bt` 的镜像即可恢复。
- **风险 2**：`k60_bt_local_address()` 从弱变强，若 `/chosen` 读取路径有问题会让 worker 提前返回
  `-ENOENT`（行为与今天相同，不是新故障）。
- **回滚**：`git revert` 该提交，或把 `patches/xnu/series` 里的 `0509` 行删掉再
  `sync-device-input.py`。

## 8. 上机顺序

S3 **不能**跳过 S1c/S2 单独上机：它只解决「用户态看得见」，不解决「GENI 能不能碰」。
推荐顺序：S1c 五档阶梯（A1→A5）→ `bt-s2-20261114b`（无参数，证明 0508 惰性）→ 带 `k60bt=1`
的 S3 镜像（本补丁）→ 看 `K60 BT:` 与 bluetoothd 三行是否变化。
