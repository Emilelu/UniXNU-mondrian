# abi27e 缺的两个站 API

2026-11-20 的 `ath11k-abi27e/libPongAth11k.a` 通过了成员架构和 `stamp/header` 绑定，但 `llvm-nm`
里既没有定义也没有引用 `nw_wifi_power` / `nw_wifi_scan_frequencies`；`scripts/check-wifi-station-archive.py`
因此退 1。这一页只定案「这两个 API 对 24A446 意味着什么」，不提出实现。

| API | 精确原型 | 我方调用点 | abi27e | 驱动归档的引用 | 24A446 消费证据 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| `nw_wifi_power` | `void nw_wifi_power(int enabled);`（生成侧车 `abi/nw_abi.h:79`） | `drivers/PongWifi/PongWifiNet.cpp:707`，在 `apple80211()`（:674）的 `case kPower`（:703）里，且只在 `gModern27Client` 已置位时调用 | 无（成员只有 `PongAth11k-linked.o`，`llvm-nm` 无此行） | `PongWifiNet.late.o` 里是强 `U` | 无：24A446 无线栈不在 pinned kernelcache（305 个 kext 无无线 kext），且这是本线私有 ABI，Apple 二进制不能直接引用该符号 | 无证据，保持 open |
| `nw_wifi_scan_frequencies` | `int nw_wifi_scan_frequencies(const uint8_t *ssid, size_t len, const uint32_t *mhz, size_t count);`（生成侧车 `abi/nw_abi.h:73`） | `drivers/PongWifi/PongWifiNet.cpp:758-760`，同一函数的 `case kScanReq/kScanReqMultiple`（:709）里；声明是 `weak_import`（:57-58），缺席时退回 `nw_wifi_scan` | 无（同上） | `PongWifiNet.late.o` 里是 `U`，并带 `l_nw_wifi_scan_frequencies$auth_ptr$ia$25242` | 无：同上；它只在带频道的扫描请求里被调用 | 无证据，保持 open |

## B4 结论：缺的不是内核导出，是站归档定义

2026-11-21 对 27 候选内核 `kernel.macho` 的 `com.apple.kernel` 取导出，共 24,572 个符号。
把驱动归档和 station 归档的 undefined 逐个对照：

| 归档 | undefined | kernel | same-archive | 另一归档 | station API | absent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `libPongWifiNative.a` | 352 | 314 | 36 | 0 | 2 | 0 |
| `libPongAth11k.a` | 13 | 12 | 0 | 1 | 0 | 0 |

352 个驱动 undefined 里 **350 个已解析**（314 kernel + 36 same-archive），唯缺 station 的两个 API；
station 的 13 个里 12 个 kernel + 1 个另一归档，0 absent。所以「27 里根本没有」的符号是 0。
`_nw_wifi_power` 与 `_nw_wifi_scan_frequencies` 只能由
station 归档定义；`ath11k-abi27e` 仍只编 16 的 `src/nw_sta.c`，没有把 `src/nw_mainline.c`
编进去（`scripts/build-k60-ath11k.py:720-722`）。

### 每个 API 的四项

| API | (a) 27 侧调用点 | (b) 16.6.1 怎么满足 | (c) 27 semantics 变了什么 | (d) 最小补丁形态 |
| --- | --- | --- | --- | --- |
| `nw_wifi_power` | `PongWifiNet.cpp:707`，`apple80211()`（:674）的 `case kPower`（:703）里，`gModern27Client` 为真才调用 | 16.6.1 c8 的 `native-c8/libPongWifiNative.a` 用 `llvm-nm -u` 没有 `_nw_wifi_power`；16 的 `ath11k/libPongAth11k.a` 只导出 `_nw_wifi_scan`。16 路径在 `:704` 只断开链路，没有站上电/断电入口 | 27 新增 `void nw_wifi_power(int enabled)`（`abi/nw_abi.h:79`）；`enabled` 是 0/1，无单位；站实现置 `radio.pending`、`radio.enabled=!!enabled`，清 join/scan，`clear_connection(...NW_STA_IDLE/OFF)`，全程持 `boundary_lock`（`nw_mainline.c:266-271`）。16 没有这个驻留态 | 补进 station 归档：编译 `src/nw_mainline.c:266`（语义版），或在 16 的 `sta` 变换里加 `void nw_wifi_power(int enabled){(void)enabled;}`（仅链接）。**不要**补进内核导出；改驱动避开等于删掉 27 的 `kPower` 分支 |
| `nw_wifi_scan_frequencies` | `PongWifiNet.cpp:758-760`，`case kScanReq/kScanReqMultiple`（:709）里；声明 `weak_import`（:57-58） | 16.6.1 c8 的 native 没有 `_nw_wifi_scan_frequencies`；16 的 station 只导出 `_nw_wifi_scan`。16 路径在 `asked=false` 时退回 `nw_wifi_scan(ssid,len)`，扫全频道 | 27 新增 `int nw_wifi_scan_frequencies(const uint8_t*, size_t, const uint32_t*, size_t)`（`abi/nw_abi.h:73`）；频道是 MHz，最多 32（`:72`），逐项 2400–7125，`-EINVAL`/`-ENETDOWN`；持 `boundary_lock` 合并重复扫描并设 12 s deadline（`nw_mainline.c:223-236`）。16 只有 `(ssid,len)` | 补进 station 归档：编译 `src/nw_mainline.c:223`（语义版），或加 `if (count > NW_WIFI_SCAN_FREQUENCIES_MAX) return -EINVAL; return nw_wifi_scan(ssid,len);`（仅链接，忽略 mhz）。**不要**补进内核导出；驱动已有 weak 退回，但会退回全频道，不算补语义 |

`llvm-nm` 证据命令（只读）：

```sh
llvm-nm-18 -u /opt/k60/trees/k60build/wifi/native-c8/libPongWifiNative.a | grep -E 'nw_wifi_power|nw_wifi_scan_frequencies'
llvm-nm-18 -u /opt/k60/trees/k60build/wifi/teardown27g/libPongWifiNative.a | grep -E 'nw_wifi_power|nw_wifi_scan_frequencies'
llvm-nm-18 --defined-only --format=posix /opt/k60/trees/k60build/wifi/ath11k/libPongAth11k.a | grep nw_wifi_scan
```

第一行无输出；第二行两个符号都在；第三行只有 `_nw_wifi_scan T`。因此这两行不是 27 的导出缺口，
而是 station 源集合的缺口。把它们补进内核导出会满足链接，却绕过了 station 的驻留状态，属于层次错误。

## 为什么两行都不是「association 之前必须」

两个事实要分开，混在一起就会把线内打包要求当成 24A446 的需求：

- **链接期**：`nw_wifi_power` 是强引用，站归档不定义它，`PongWifiNet.late.o` 就链接失败（历史
  链接的 undefined 列表里有它）。`nw_wifi_scan_frequencies` 是 `weak_import`，站归档缺席也能链接，
  代价是扫描退回全频道（`PongWifiNet.cpp:758-760`）。这只证明「我们的 kext 必须和定义它的站配对」，
  不证明 Apple 的守护进程会走到这些路径。
- **运行期**：`nw_wifi_power` 只在 `gModern27Client` 置位后调用，而该标志由 24A446 形状的扫描/关联请求
  置位（`PongWifiNet.cpp:724`、`:813`、`:918`、`:954`）。也就是说首个扫描之前，本驱动不会调用它；
  24A446 是否在关联前要求电台断电/上电，仍要看它的消费者二进制。
- **消费者证据**：`nw_abi.h` 是本线与站之间的私有契约，`wifid`/`IO80211Family` 不会直接引用这两个符号；
  它们只能通过 selector 路径（`kPower`、`kScanReq`）间接到达。24A446 的 wifid/IO80211Family 目前没有
  可读二进制（`043-68526-711.dmg.aea` 加密，未解密），所以「谁在什么阶段调用」没有证据。

按 `SHENG-KERNEL-REFERENCE.md` I 节的阶梯，这里的证据只到 L0（源码/归档）；L1b 的 16/22H374 行为
不能外推到 24A446。两行结论因此都是第三档：**无证据，保持 open**。

## 什么会改变结论

- 24A446 wifid/IO80211Family 的反汇编，或一份 24A446 的 selector 调用记录：能看到 `kPower`/`kScanReq`
  在关联前是否发生，才能落到「SpringBoard 之前不需要」或「association 之前必须」。
- 一次设备日志：站归档不带这两个 API 仍能到 SpringBoard（会支持前者）；或关联卡在扫描/上电（会支持后者）。

在那之前，站归档仍必须定义两者——这是线内验收（`scripts/check-wifi-station-archive.py`），不是对 24A446
需求的证明。

## 关闭条件（两行各自）

两行都 **blocked behind F2/SpringBoard**：第一次能到达 SpringBoard 的 24A446 飞行之前不得关闭；
判据在飞行前写死，事后从日志里挑句子不算。两行还有同一个前提——本线先给对应分支补一行 IOLog
（当前代码没有），否则飞行日志里没有可判的字形。

### `nw_wifi_power`

- **什么证据能关掉它**：24A446 的守护进程在关联之前通过 `apple80211` 的 `kPower` 子命令要求
  上电/断电。正证据是驱动在 `case kPower`（`PongWifiNet.cpp:703`）打出的调用行；反证据是
  同一次飞行里站归档**不定义**该 API 仍能完成关联（说明关联前不需要它）。
- **谁产出**：Lead 的 F2 飞行 + 本线在 `:703` 之后补的 IOLog；只有 Lead 能上机。
- **预写日志字形**：子串 `PongWifi: 27 client power`，后面必须同时有 `enabled=<0|1>`、
  `phase=<before-scan|after-scan>`、`seq=<n>`；站侧另有 `PongAth11k: power enabled=<0|1>`。
- **判读边界**：出现该子串且 `phase=before-scan`、`enabled=1`，才算「关联前必须」；整次飞行
  没有该子串且关联成功，才算「不必须」；只到 SpringBoard、没有关联，两边都不算。

### `nw_wifi_scan_frequencies`

- **什么证据能关掉它**：24A446 的扫描请求带显式频道列表（`kScanReqMultiple` 形状）并在关联前
  发生。正证据是驱动在 `:758-760` 附近打出的请求行；反证据是站归档缺席该 API（`weak_import`
  退回 `nw_wifi_scan`）仍能在 5 GHz 上完成扫描与关联。
- **谁产出**：同上（Lead 的 F2 飞行 + 本线补的 IOLog）。
- **预写日志字形**：子串 `PongWifi: 27 scan request`，字段 `channels=<count|none>`、
  `source=<frequencies|fallback>`、`ssid_len=<n>`；站侧 `PongAth11k: scan channels=<n>`。
- **判读边界**：`source=frequencies` 且 `channels>0` 在关联前出现，才算「必须」；只出现
  `source=fallback` 而 5 GHz 扫描/关联成功，才算「不需要」；只有 SpringBoard、没有扫描，仍 open。

关闭动作只有两种：证据落进上表「24A446 消费证据」列，或 Lead 明确把该项降级为「线内打包要求」。
不得用 16/22H374 的行为代替 24A446 的证据。

## 最小可编译补丁的形态（不实现）

这套树里没有站 ABI 的整数版本号：`include/nw_abi.h` 只有 include guard；唯一的版本号是
`include/nw_control.h:13` 的 `NW_CONTROL_VERSION 1`，那是 userspace 控制线，与这两个入口无关。
站 ABI 的版本锚是 `abi/nw_abi.stamp` 的 `ie_bytes=2048` 与 `header_sha256`；两个函数都已在头里
声明、不改变 `struct nw_bss_info` 布局，所以 **stamp 与版本号都不动**，要动的只是「谁定义这两个
符号」。`abi27e` 缺的不是声明，是它的源集合仍是 16 的（`scripts/build-k60-ath11k.py:720-722`
没有 `src/nw_mainline.c`）。

| API | 头里的声明（已存在，不改） | 最小可编译补丁的形状 |
|---|---|---|
| `nw_wifi_power` | `abi/nw_abi.h:79` `void nw_wifi_power(int enabled);` | 在 `scripts/build-k60-ath11k.py` 的 `sta` 变换（`:546-718`）里给 16 站追加 `void nw_wifi_power(int enabled) { (void)enabled; }`，只补链接；语义版是把 27 的 `src/nw_mainline.c:266` 加进 `common_sources`（`:720-722`），代价是整份 27 的 cfg80211/mac80211 源集合。 |
| `nw_wifi_scan_frequencies` | `abi/nw_abi.h:73`，上限 `:72` `NW_WIFI_SCAN_FREQUENCIES_MAX 32` | 同一位置追加 `int nw_wifi_scan_frequencies(const uint8_t *ssid, size_t len, const uint32_t *mhz, size_t count) { if (count > NW_WIFI_SCAN_FREQUENCIES_MAX) return -EINVAL; return nw_wifi_scan(ssid, len); }`，忽略 `mhz`、只补链接；语义版是编译 `src/nw_mainline.c:223`。 |

两行都只是形状：桩实现能过链接，不能关闭上面两行；哪一版成立仍取决于 F2/SpringBoard 的日志字形。