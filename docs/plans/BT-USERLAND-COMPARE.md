# 蓝牙用户态：iOS 16 与 iOS 27 的修复难度对比

状态（2026-11-19 00:35）：内核侧工作已完成并验证（0518 = d11 PASS，0519/0520 = d12 观测）。
本文件回答用户 2026-11-18 的决定性问题：**先修 iOS 16 的用户态，还是把用户态留给 iOS 27。**
数字带“约”的都是估算，带文件:行的都是本机可复查的证据。

## 1. 结论

1. **iOS 16 的用户态不是“再补一点”，而是三件互相独立的工作**：换掉 BlueTool、让 bluetoothd 认 QCA、
   把自编用户态放进 sealed System 卷。前两件里第二件是版本锁定的逆向工程，第三件在内核侧。
2. **iOS 27 的用户态已经做完并在他机验证**（sheng 配对/A2DP、aston 24A446），代价是它锁死在 24A446
   的 bluetoothd 哈希上；K60 要付的是**内核 bring-up**，不是用户态。
3. 因此建议：**iOS 16 停在“内核已可用的测试床”，用户态投入转向 iOS 27**；除非 iOS 27 的内核
   bring-up 在可控时间内卡死，才回头做 20G81 的 daemon 重定位。

## 2. 事实基础

### 2.1 内核侧（已完成的共同底座）

- 0500–0518 在 iOS 16 上把 GENI/UART、H4、patch/NVM、GIC INTID、DT 发布、MAC 全部打通；
  d11（0518）达到 `power=1 result=0 … tlv_sent=629 tlv_acks=28`、`[bluetooth sk] ctl_register error=0`。
- 0519/0520 加了三个电源节点探针与 `com.apple.uart.bluetooth` 控制名别名，d12 观测到
  `[bluetooth power] nodes ready major=17`、两个控制名注册均 error=0。
- 同一份 qbt 源码在 feat/ios27 分支只按 `bsd/dev/qbt*` 应用即与 iOS 16 逐字节一致
  （`qbt_k60.c` 2239 行，sha256 4a1a4e26…），**内核层与系统版本弱耦合**。

### 2.2 iOS 16.6.1（20G81）的现成用户态是什么样

从 IPSW 根文件系统解出的原件（`/home/emilelu/ld2/usr/sbin/`）：

| 事实 | 证据 |
| --- | --- |
| bluetoothd 原生就说 UART.SK | 字符串 `com.apple.uart.sk.bluetooth` |
| bluetoothd 与 BlueTool 的 XPC 契约 | `RunBuiltinScript`、`RunCommand`、`kMsgId`、`kMsgArgs`，回包键 `result`、`manufacturer`、`firmware`、`output` |
| bluetoothd **完全不认识 QCA** | `strings bluetoothd | grep -i 'QCA\|Qualcomm\|wcn'` 零命中（只有 ExtDupFilter… 的误匹配） |
| 芯片表只有 BCM/CSR 语义 | `Server/Chipsets/LEHardwareModel.cpp`；`Couldn't find a platform / chipset / firmware combination for the HW`；`Unknown platform/chipset/manufacturer combination, restarting` |
| BlueTool 内置固件表是 BCM 专用 | 0x100014f10 的 24 字节条目表；QCA 无条目 → `Error - no firmware for th…` → 返回 10 |

d12 实测（`E:/k60-work/evidence/usblog-20261119-000246/console.log`）：BlueTool 每次启动都打印
`Device not open yet, use 'device' to open it.`（:2085/:2876/:3287/:3528/:3730），从不开 transport socket，
约 33 s 后被 30 s XPC 看门狗杀死（:2871 `KX! 15 137 BlueTool exit=1`），launchd 连续重启 5 次。
bluetoothd 自 1723 起再无日志，也没有任何 `[bluetooth sk] connect` —— **它卡在 BlueTool 这一步**。

反汇编 `runCommandForCurrentConfig`（0x100015fa4）给出打印之后的调用顺序：`getManufacturer` → `MGIsDeviceOneOfType`（0x100040284）→ `getVendor` →
`MGCopyAnswer("ReleaseType")` → `stat("/etc/bluetool/<HWModel>.<phase>.script")` →
`stat("/etc/bluetool/<platform>.<phase>.script")` → 内置 firmwareList。其中只有 MobileGestalt 的同步 XPC 没有超时，
而看门狗的取消点（0x100042cf0）只有工作函数返回才会执行，因此“约 33 s 被杀”等于“卡在 MG 这一次同步调用里”，
`stat`/`fopen` 都是本地 VFS 不会无限等待。**这个卡点在内核之外**：内核侧没有可做的补丁，除非伪造 MG 回复（用户态）。

### 2.3 iOS 27（24A446）的参考实现

`E:/hackios/QcaBluetooth`（BSD-2-Clause-Patent）：

| 文件 | 行数 | 作用 | 版本锁定 |
| --- | --- | --- | --- |
| `userland/BlueTool.c` | 63 | 只做 XPC 适配：`RunBuiltinScript` → `sysctlbyname("kern.qbt_power_on"/"kern.qbt_boot"/"kern.qbt_firmware")`，回 `manufacturer=29` 与固件串 | 无，通用 |
| `userland/Type0.c` | 217 | 能力发布 dylib（QcaBTType0.dylib），按 `qbt_ios27_layout.h` 直接写 bluetoothd 的模型槽 | 有，24A446 布局 |
| `tools/native_ios27.py` | 496 | 按**硬编码 VM 地址**打 4 个补丁（vendor_routing / volatile_root_keys / h4_shutdown / capability_adapter） | 有：sha256 `cfd94854…`、UUID `8E49197B…` |
| `tools/build-userland.py` | 87 | 构建 + 签名 + 校验原哈希/UUID/entitlement 不变 | 有 |

官网 `docs/zh/porting/bluetooth.md:87-103`：`payload.runtime.bluetooth_tool` + `bluetooth_target="ios27"`，
内核侧 `sheng-bluetooth-runtime.patch` 把它们挂到 `/usr/lib` 与 `/usr/sbin`；
“适配器锁定到一个 bluetoothd 哈希”。硬件证据：sheng（iPadOS 27，AirPods 配对/A2DP）、aston（24A446）。

### 2.4 K60 iOS 16 侧缺的“安装路径”

- `profiles/os/ipados-16.6.1-20G81/profile.toml` 的 `[payload]` 只有一行注释：
  “No text fixups and no trust cache yet: the K60 payload is still at the kernel-only stage.”
  **没有 `[payload.runtime]`**，所以没有 bluetooth_tool / Data seed / GPU addon 通道。
- 框架的 runtime 门禁：`scripts/unixnu/runtime.py:52-56` 造 Data seed 需要 root；
  `runtime.py:86-102` 才会调用用户的 `build-bluetooth-userspace.py`。
- sealed System 卷拒绝 bindfs：`patches/xnu/0404-k60-metal-deploy.patch:210-224` 记录了 P-27 的测量结果，
  最后走的是“不用 bindfs”。iOS 27 那条路是内核补丁直接挂载，iOS 16 线没有等价物。

## 3. 逐层对比

| 层 | iOS 16.6.1（20G81） | iOS 27.0.1（24A446） | 差距 |
| --- | --- | --- | --- |
| 内核 UART.SK / 固件 / 电源 | 已完成，d11 硬件通过 | 同一份 qbt 代码可原样编入（源码字节一致） | iOS 16 领先 |
| BlueTool | 需替换；源码已有（63 行），改 target 到 `arm64-apple-ios16.6` 即可 | 已有替换 + 签名 + 挂载 | 源码同源，iOS 16 只差安装 |
| bluetoothd 认 QCA | **不认识**：要新写 `native_ios16.py`（≈500 行地址重定位），或做身份伪装实验 | 已有 `native_ios27.py`，他机验证 | iOS 16 是数周级 RE |
| Type0 dylib | 需按 20G81 布局重写 | 已有 | 同上 |
| 安装路径 | 无 runtime 层；sealed root 拒绝 bindfs；Data seed 要 root | `payload.runtime` + 内核挂载补丁 | iOS 16 缺基础设施 |
| 硬件验证 | 无 | sheng、aston | iOS 27 领先 |

## 4. 两条路的估时与风险（估算）

**A. 在 iOS 16 上把蓝牙做到可用**

1. 安装路径（Data seed 需 root + runtime 层 + sealed 卷注入）：约 3–7 天，且可能被 sealed root 挡住；
2. BlueTool 替换：约 1–2 天（源码已有），依赖第 1 步；
3. bluetoothd 接受 QCA：
   - 身份伪装（BlueTool 回一个 BCM 身份，让 daemon 走已有芯片表）：约 2–5 天实验，**成功率未知**，
     QCA 对 BCM 私有 VSC 的回应可能让 daemon 再判死；
   - 正式重定位（`native_ios16.py` + `qbt_ios16_layout.h` + Type0 适配）：约 2–4 周，
     且**只对 20G81 这一个 build 有效**，等于把 iOS 27 已经付过的代价再付一次。
4. 合计：顺利 1–2 周（伪装路线），稳妥 4–6 周（重定位路线），成果不可迁移到 iOS 27。

**B. 在 iOS 27 上拿到可用蓝牙**

1. 内核 bring-up：F1 构建（已知失败点：`LD_KERNEL_LIBS` 未传给 fileset release-reference 链接，
   修一行即可重跑）→ F2 prelink 到 bsd_init → F3 存储 ABI → F4 面板/触摸。数周量级，风险集中在这里；
2. 用户态：**基本为零**——BlueTool/Type0/bluetoothd 补丁都是现成的，K60 只需 DTS 节点与 MAC 管道
   （0509 已实现）和 `payload.runtime` 接线，约 1–3 天；
3. 风险：24A446 哈希锁定，换 build 要重做 496 行地址；但那是一次性的、且已有方法论。

## 5. 建议

1. **iOS 16 线收尾**：内核侧到此为止（d11 PASS + d12 观测已记录），用户态不再投入。
   若一定要在 iOS 16 上再走一步，只做“BlueTool 身份伪装”这一个 2–5 天的实验，不做 daemon 重定位。
2. **用户态预算转给 iOS 27**：先恢复 F1（`build-fileset-release-reference.py` 里补
   `LD_KERNEL_LIBS=<sdk>/usr/local/lib/kernel/libcc_kext.a`），拿到第一个真实构建结果，
   再判断 F2 的距离。
3. **分界点**：若 F1/F2 在约两周内看不到 bsd_init，再回头评估 20G81 daemon 重定位是否值得。

## 6. 什么会改变这个结论

- iOS 27 的 prelink/arm64e 在 F2 阶段证明不可达（例如 24A446 组件无法在 K60 内核布局下解析）；
- 发现 20G81 的 bluetoothd 其实有未启用的 QCA 路径（目前字符串零命中，可能性低）；
- 出现第三方的 20G81 bluetoothd 补丁或 iOS 16 的 QCA 用户态实现可复用。
