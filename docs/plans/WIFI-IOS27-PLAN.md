# Wi-Fi 迁移到 iPadOS 27.0.1（24A446）方案

状态：准备阶段（build-only，分支 feat/wifi-ios27-abi）。本文件只给形状、证据和上线路径；飞行要等 fork 的 ios27 分支走到 bsd_init、能取到 24A446 的 IO80211Family/wifid 二进制之后再排。

## 1. 目标与验收

目标系统：os_profile ipados-27.0.1-24A446（board.toml:9、porting.toml:6 已写）。验收沿用官方 network 页面：固件与 QRTR 起来、扫描产生 BSS 记录、scan/auth/association/address/RX/TX 逐项通过，并且设置页 Wi-Fi 列表出现 5 GHz 行 Emilelu_5G、点进去能加入、拿到 192.168.31.x、能持续收发。行出现与可用这条在 16.6.1 上已由 mission34b / mission36 关掉（SBL-MISSION §36/§37），27 上要重做一遍。

## 2. 已确定的 24A446 形状（来源：UniXNU-sheng origin/main c8f92b2）

| 项 | 形状 | 我们这边的落点 |
|---|---|---|
| 扫描记录 | 0x8e8 = 2280 字节，elements 2048 B 在 0x8c，时间戳 0x8d0，尾部 16 B | PongWifiAbi.h 的 PONG_SCAN_RECORD_24A446 / PONG_SCAN_ELEMENTS_BYTES；PongWifiNet.cpp 单一 scan_result 结构 |
| 关联请求 | 0x290 = 656 B（network 在 0x10，key 在 0x4c）；老 0x250 与 22H374 的 0x384 也接受 | kAssociate 按 req_len 分三档，只取前 0x8c 字节有意义 |
| 关联完成事件 | 540 B，result 在 0x214、has_result 在 0x218 | PongWifiAbi.h 的 pong_assoc_event27；NotifyAssociate 分支 |
| 扫描请求 86 | 0x14e8 = 5352 B；names 0xc（8 条、每条 40 B）、type 0x200、channels 0x210（12 B 一条） | pong_scan_multiple_parse / pong_scan_frequencies |
| 扫描请求 10 | channels 0x44/0x48 | 同上的单频道表解析 |
| 能力位 | 12 字节请求里回 22（命名扫描）与 46（等扫描完成事件） | pong_wifi_caps_fill；19 字节请求保持 22H374 老位图 |
| 绑定路径 | 27 走 ifnet ioctl（SIOCGA80211/SIOCSA80211）+ apple80211req | if_ioctl 上限已从 5120 改为 PONG_SCAN_REQUEST_MAX |
| 元素区 | 站 IE_MAX 与 nw_abi.h 都要放大 | 两个 builder 都写 ie[2048]、IE_MAX 2048；27 站构建出 ath11k-abi27 |

## 3. 已经离线验证的

- 16 头（ath11k-abi1）与 27 头（ath11k-abi27）各编译一次 kext，产物 native-abi27 / native-abi27s，ie[2048] 与 unsigned diagnostics 都在。
- host 自检：pong-abi-selftest.c 31 项、test-pong-abi.py 28 项、test-pong-he、test-pong-sae 全过；参考漂移检查会在 sheng 检出存在时对照 0x8e8/2048/0x8d0/12 等常量。
- 27 的 teardown：PongWifiPlatform.cpp:68 的 stopRequested、worker 循环头 :811、:836 的 nw_wifi_stop；PongWifiNet.cpp:1206 的 pong_wifi_net_stop 与 :1028 的 pong-wifi-stop 属性入口。两代站头各编译一次，llvm-nm 见 _pong_wifi_station_stop 与 _pong_wifi_net_stop（SBL-MISSION §42）。

## 4. 仍未验证的风险（按优先级）

1. selector 0 信封（0x3c30 进 / 0x3c00 出）：16 的 wifid 用 user client；27 是否完全不碰 selector 0 还没有二进制可证。拿到 24A446 的 IO80211Family 与 wifid 后第一件事就是核对这一处。
2. 27 的 wifid 是否要求签名 launchd 服务 unixnu-wpa_supplicant / org.unixnu.wifi.control：sheng 的用户态方案带它，我们的 4-way 在内核里。若 27 的 wifid 只认该服务，要么补服务，要么证明 ABI 正确即可。
3. 6 GHz：官方 WCN7850 页面写明 59 个被动频道要跳过；我们的扫描请求解析目前不区分 6 GHz，27 上要把 PONG_SCAN_FREQUENCIES 的上限与频道表按 band 过滤。
4. 系统不能保存网络口令（官方页面已写），27 上用户每次开机要重连；这不是缺陷，不要写成 WiFi 回归。
5. t970 与 zizhan 都是 22H374 树，27 的形状只能继续以 sheng 为准；不要把它们的 ABI 抄回来。

## 5. 上线路径

1. fork 的 ios27 分支走到 bsd_init（能启动到用户态）时，取 24A446 的 IO80211Family 与 wifid，核对 selector 0 信封、扫描请求实际长度、能力位实际取值。
2. 用 feat/wifi-ios27-abi 的 builder 出 27 镜像（station 用 ath11k-abi27），先 build-only 验证九步 §⑦ 的三件套（静态检查、host 单测、产物检查）。
3. 第一次上机只验证「固件+QRTR 起来、扫描出 BSS、设置页出现 5 GHz 行」；association/DHCP/HTTPS 分第二、第三趟，不要一次全押。
4. 每趟都按 BOOT-PROCEDURE 与 boot-and-capture.ps1 记录 boot.json；未飞的镜像要么飞要么删，不许留下 P-218 欠账。

## 6. 边界

c8 5eacc301 保持 HOLD；只 fastboot boot；不写 /dev/block/sda38；仓库不放凭据。WPA3 仍是最后的 TODO（t970 的洁净室单元是起点），应用层 WebKit 0xdead10cc 由 lead 那条线负责。
