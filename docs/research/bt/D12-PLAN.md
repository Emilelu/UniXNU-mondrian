# d12 诊断飞行计划（bt-0520-uart-control-alias，2026-11-18）

状态：**已构建、离线门禁通过、已飞行（2026-11-19 00:02:48–00:06:52），观测不完整，见 §9。**

d12 和 d10/d11 不同：d10/d11 是修复候选，d12 是**观测候选**。它不改变固件下载、状态机、上电时序、budget、段长或地址，只增加内核侧的三处观测，用来回答 d11 遗留的一个问题：BlueTool 为什么 exit=1。

## 1. 要回答的问题

d11（0518）已把内核栈打通：patch 602 段、NVM 27 段、HCI reset、BD_ADDR、`com.apple.uart.sk.bluetooth` 注册全部成功，console:1278 `power=1 result=0`。但用户态 BlueTool 仍然 `exit=1`（console:2877 `KX! 16 136 BlueTool exit=1`），并且：

- d11 console 里 `[bluetooth sk]` 只有 `ctl_register` 一行，**没有 connect 行**，说明 BlueTool 在退出前没有连上内核控制通道；
- `/dev/btreset`、`/dev/btwake`、`/dev/btpoweroff` 在 20G81 这套 prelink roots 下不存在（`profile.toml` roots 没有 `com.apple.driver.AppleBluetooth`），也没有任何打开记录。

静态逆向（`BlueTool.20G81`，sha256 `7BB2055F…190FCE5`）给出的 exit=1 路径只有两条：**（a）launchd 传进来的 `-F` 参数不是 boot/init/deepsleep，立即退出 1**；**（b）XPC 处理里 30 s 看门狗超时**（`0x1000430f0`，打印 "BlueTool timed out! Exiting..." 后 exit 1）。其余失败路径是 exit 3/4/10，不是 1。

两者只能靠运行时观测区分，所以 d12 记录：

1. **BlueTool 的真实 argv**（`K60ARG` 行）——直接判定 `-F` 是否合法；
2. **BlueTool 是否连上控制通道**，以及连的是哪个名字（`[bluetooth sk] connect … control=…`）；
3. **是否打开 `/dev/bt*` 电源节点**（`[bluetooth power] …` 行）。

## 2. 0519 与 0520 改了什么

`0519-k60-bt-userspace-power-nodes.patch`（sha256 `7e547a20a52cdf446b0e38ec376a64057cf4c542c188e25bd1e36df9ac8a63d8`）：

- 在 `qbt_transport.c` 里注册三个字符设备 `btreset` / `btwake` / `btpoweroff`（`cdevsw_add` + `devfs_make_node`，`DEVFS_CHAR`、`UID_ROOT/GID_WHEEL`、`0666`），每个 open/close/write/ioctl 打一行 `[bluetooth power] …`，当前一律返回成功（探针，不是最终语义）。
- `MiniBluetooth.cpp` 的 `K60_BT_TRANSPORT_SPEED` 由 `3200000u` 改为 `3000000u`：48 MHz 的 QUPV3 源分不出 3.2 Mbaud（`0500:1247` 的 `k60_geni_source_hz(3200000,16)` 会 `-ERANGE`），而 `qbt_boot` 结束时链路就在 3.0 Mbaud（`K60_BT_RUN_BAUD`）。这是让设备树属性与真实链路一致，不改任何分频计算。

`0520-k60-bt-uart-control-alias.patch`（sha256 `15d553964af34bcaf2555a90b1f73548cdabcd45634f14e1cfc20ee3a663d61a`）：

- 在 `qbt_transport.c` 里额外注册一个同名回调的内核控制别名 `com.apple.uart.bluetooth`（stock BlueTool 的默认名字；`bluetoothd` 用 `com.apple.uart.sk.bluetooth`）。connect 日志带上 `control=%s`，可以区分是谁连的。
- 在 `kern_exec.c` 的 `exec_mach_imgact` 里，`exec_extract_strings()` 成功之后，对 `BlueTool` / `bluetoothd` 打一行 `K60ARG <basename> argc=%d` 加最多 4 个 argv（每个截 64 字节）。名字取 `imgp->ip_vp->v_name`（此时 `p_comm` 还是 `xpcproxy`）。不新增任何库调用、不拷贝用户地址。

## 3. 候选身份与离线证据

| 项 | 值 |
| --- | --- |
| build manifest | `E:/k60-work/artifacts/bt-0520-uart-control-alias/build-manifest.json` |
| 构建时间 / tag | `2026-11-18T23:42:54+08:00` / `bt-0520-uart-control-alias` |
| repo head / dirty | `970839ffb848662af2c19ce17fed183b72aec35a` / 0 |
| series | 240 条；全文件 `af13b1c2590219cca7e11cd5bddde30ed2464d79292344ed355d6fd3410f2003`；前 239 行 `1cf9d873f5418c9928a845196c9b4a3f3fe5009f9ab5352cf67e6c2119dff620`；前 238 行 `4a39a8d2fddf0da93dbcab18a2302c69bab8f34955d56e9172c1a395e8b12e11` |
| 0519 补丁 | 144 行，sha256 `7e547a20a52cdf446b0e38ec376a64057cf4c542c188e25bd1e36df9ac8a63d8` |
| 0520 补丁 | 91 行 / 3,737 B，4 hunk，sha256 `15d553964af34bcaf2555a90b1f73548cdabcd45634f14e1cfc20ee3a663d61a` |
| kernel.log | `:272` 记录 `0519-k60-bt-userspace-power-nodes.patch`，`:273` 记录 `0520-k60-bt-uart-control-alias.patch` |
| 应用后源码 | `qbt_transport.c` 含 4 处 `ctl_alias` 与 4 处 `com.apple.uart.bluetooth`；`kern_exec.c` 含 `K60ARG`；`MiniBluetooth.cpp:40` `#define K60_BT_TRANSPORT_SPEED 3000000u` |
| boot.img | `9361ec1c89a7852db2ae9619a8ed89e859343a3d6bf1a9441029dda1cb82e876`（201,887,744 B） |
| kernel_built / payload / payload_kernel | `8bb86f36324b29b4634f257bf1f5f9825e655266bb1703045435efa7f1b5a393` / `4f95bf9eab126fd190ba2dd5aec827e3e7d16010da6ef01822af5d200ec4f5a5` / `4f1ac6ac8723e22655ea9e1b72a209f5b2d94a58b2719d9adad09d56a37dcc4c` |
| ADT / dtb / fd / bt_blob | `5aea66fab8ee74e2b96e96a3a576e6aec88939c9bc442a5194d600f6fce902b3` / `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` / `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` / `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037` |
| frozen | `frozen-before.txt`，list sha256 `47aea89b2bcb3b01013bd4a8ad4db700990e43379bdab2dfc803c292336237e7` |
| 八步 | `gates.eight_step = passed`（items: bluetooth） |
| kernel args | `k60bt=1 pong_bt_late=1`（与 d11 相同） |

离线检查（2026-11-18）：

- `python3 scripts/verify-boot-image.py --manifest .../bt-0520-uart-control-alias/build-manifest.json` → `verify-boot-image: OK`。
- `check-image-args` → `image-arg-audit: OK (31 arguments, 598 bytes)`。
- 宿主套件：0516 82/0、0517 53/0、0518 36/0、0519 29/0、0520 23/0、d8 adapter 90/0。
- `sync-device-input.py --check` → 822 个文件一致。
- **全部是 HOST-ONLY + 离线构建证据**，不证明 BlueTool 行为、不证明蓝牙可用。

## 4. 飞前检查（任何一项红就不飞）

1. `bash scripts/k60-device.sh state` 返回 `fastboot`，记录序列号（此前 `6033dbec`）。
2. 按统一 supervisor 的机器级 boot claim 规则取得 claim；若有别的 collector/supervisor 持有 COM 口或 claim，不得启动。
3. `sha256sum E:/k60-work/artifacts/bt-0520-uart-control-alias/boot.img` = `9361ec1c89a7852db2ae9619a8ed89e859343a3d6bf1a9441029dda1cb82e876`。
4. `verify-boot-image.py --manifest` → OK。
5. 回滚图必须同时核对：d8 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`、d10 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`、d11 `d6beec4c6bfbb09c1d11076db0239ead0ee357dd2ba58bfb4f92a69c9d7158ec`。
6. 只用 `fastboot boot`；绝不 `fastboot flash`，绝不写 `persist` / `/dev/block/sda38`。
7. 显式传 `K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device`。

## 5. 执行

```sh
export K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device
bash scripts/k60-device.sh state
bash scripts/flash.sh E:/k60-work/artifacts/bt-0520-uart-control-alias/boot.img
```

保留完整 console、`boot.json`、`capture.json`。

## 6. 预先写死的判据

d12 是诊断飞行，判据按"是否拿到可判定的观测"写，不按"蓝牙是否可用"写。

### 必须出现的观测（任何一项缺失都先当探针失败，不是 BlueTool 结论）

- `K60ARG BlueTool argc=…` 至少一行；
- 至少一次 `[bluetooth sk] connect … control=…`（哪个名字都算）；
- 若 BlueTool 打开电源节点，至少一行 `[bluetooth power] …`。

### 判定（拿到观测之后）

- **D12-A：`K60ARG BlueTool` 的 argv 里 `-F` 的值不是 `boot`/`init`/`deepsleep`（或根本没有 `-F`）** → exit=1 是参数路径，下一步是修正 launchd 传参或让 BlueTool 走默认参数，不需要再碰内核传输层。
- **D12-B：argv 合法且 BlueTool 连上了控制通道后才 exit=1** → 看门狗假设成立，下一步是记录 BlueTool 命令流（哪些 opcode、等什么事件），而不是继续加电源节点。
- **D12-C：argv 合法、但没有任何 connect、也没有电源节点打开** → BlueTool 在打开传输之前就退出了；下一步（0521）在 `ctl_ioctl` 的 `CTL_INFO` 解析路径和 BlueTool 的 exec→exit 时间差上取证，判定是 30 s 看门狗还是更早的失败。
- **D12-D：控制别名被连接，且 BlueTool 不再 exit=1** → 名字错配就是用户态推进的分界点；此时才谈 H4/HCI 流。

### 失败与禁止的推断

- 启动没到用户态（没有 `KE … bluetoothd`、没有 `com.apple.server.bluetooth`）→ 本次飞行对 BlueTool 无结论，按启动失败处理。
- 没有 `K60ARG` 行不等于"BlueTool 没有 exec"：`v_name` 匹配可能不中；必须先确认探针在别的 exec 上有效（例如 `K60ARG` 对其它进程是否有输出）才能下结论。
- 一次飞行**不得**声称"蓝牙可用"、"BlueTool 修好了"或"0519/0520 改变了内核栈"；内核栈自 d11 起未变。
- 不得把 d12 的结果归因给 0519 或 0520 的修复效果——它们只增加观测（0519 还改了 `transport-speed` 属性值，这一项若影响 BlueTool，必须由 D12-D 单独讨论）。

## 7. 结果处理

- 拿到 D12-A → 记 `D12-PLAN.md` §9，改用户态传参方案（需要先拿到 launchd plist 或 BlueTool 的 XPC 调用方），内核侧暂停加码。
- 拿到 D12-B/C → 0521 加"exec→exit 时间差 + ctl_info 查询日志"，仍不改下载/时序。
- 拿到 D12-D → 转 H4/HCI 数据通路验证（先看 bluetoothd 是否拿到 `IOService`/UART.SK 通道，再看 HCI Reset/Read Local Version 是否往返）。

## 8. 边界

- d12 只证明内核侧观测是否到位，以及 BlueTool 的 argv/连接/电源节点行为；不证明蓝牙可用、配对、A2DP。
- 0519 的电源节点是探针：open/ioctl 一律返回成功，语义不是最终实现；若 BlueTool 依赖真实 GPIO 复位语义，后续必须换成真实实现或 prelink `com.apple.driver.AppleBluetooth`。
- 回滚基线仍是 d8 `0297012d…`（已知可启动、BT 失败但系统可用）。

## 9. 飞行结果（2026-11-19 00:02:48–00:06:52，D12-C 形态，观测门槛未完全达到）

- 设备 `6033dbec`，飞前 `bash scripts/k60-device.sh state` = `fastboot`，无其他 supervisor/collector；只 `fastboot boot`，未 flash。命令 `K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device bash scripts/flash.sh /mnt/e/k60-work/artifacts/bt-0520-uart-control-alias/boot.img 220`，supervisor rc=0。
- 证据 `E:/k60-work/evidence/usblog-20261119-000246`：`boot.json` bootAccepted=true、bootExitCode=0、returnedToFastboot=false；`capture.json` complete=true、bytes=264656、panic/reset=null、stopReason=budget；console logSha256 `2A5E3FA9…292D98`，264,656 B。
- 内核探针全部生效：`console:1349` `[bluetooth sk] ctl_register com.apple.uart.sk.bluetooth error=0 firmware=BTFW.HSP.2.1.0-00570-PATCHZ-1 speed=3000000`；`:1350` `[bluetooth sk] ctl_register com.apple.uart.bluetooth error=0`（0520 别名）；`:1351` `[bluetooth power] nodes ready major=17`（0519 的三个字符设备）。
- 参数观测（排除 D12-A）：`:1723` `K60ARG bluetoothd argc=1 [/usr/sbin/bluetoothd]`；`:2083`、`:2873`、`:3286`、`:3527`、`:3729` 五次 `K60ARG BlueTool argc=2 [/usr/sbin/BlueTool] [-R]`。`-R` 合法，20G81 的 launchd plist 也只传 `-R`，所以 exit=1 不可能是坏 `-F`。
- 连接观测（缺失）：整份 console **没有**任何 `[bluetooth sk] connect` 行，也没有任何 `[bluetooth power]` 的 open/ioctl/write 行。两个控制名在开机时都已注册成功（`:1349`/`:1350` 均 error=0），如果 BlueTool 走到 `socket(AF_SYSTEM,SOCK_STREAM,SYSPROTO_CONTROL)+CTLIOCGINFO+connect`，0520 的 `control=%s` 日志会打出来；没有打出来说明它在打开传输之前就死了。
- 时间差：`:2082` 是 `2026-11-03 04:32:51.607`（BlueTool exec 前一行），`:2867` 是 `04:33:24.445`，`:2871` 是 `KX! 15 137 BlueTool exit=1 sig=0`。即这次 BlueTool 的 exec→exit 约 **33 s**，与静态分析的 30 s XPC 看门狗（`dispatch_time(0, 0x6FC23AC00)`，`0x1000430f0` 处 `_exit(1)`）吻合；坏参数路线是瞬时退出，会紧贴 `:2083`。
- 判定：按 §6，argv 合法 + 无 connect + 无电源节点打开 → **D12-C 形态**。但 §6 的"必须观测"要求至少一次 `connect`，本次没有满足，所以先记 **探针门槛未达**：不能用"没有 connect 行"单独证明"BlueTool 没尝试"，只能证明它在 33 s 内没有走到 connect，再叠加时间差把"看门狗在传输打开之前触发"定为本次结论。下一次诊断必须补一个能看到"是否创建 AF_SYSTEM 控制 socket / 是否发起 CTLIOCGINFO"的探针（§7 的 0521 方向）。
- 排除项：0520 的控制别名已在开机时注册成功，stock BlueTool 默认名 `com.apple.uart.bluetooth` 的错配**不是**本次 exit=1 的直接原因；0519 的三个电源节点也从未被打开。
- 边界：只证明内核探针到位、argv 合法、BlueTool 在约 33 s 后被 30 s 看门狗杀死且死在传输打开之前；不证明它卡在哪一步（XPC 等待、芯片/平台探测、设备树读取都可能），不证明蓝牙可用。内核栈自 d11 起未变，0519/0520 不改变下载路径。
