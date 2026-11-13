# Pong QCA6490 Wi-Fi

Pong 的 SM8475 / QCA6490 使用 PCIe0、MHI 和 ath11k。(https://unixnu.com/zh/porting/network)

## 接入

- `configs/pong-wifi-sm8475.json`：从本机 REC DT、PCI sysfs 捕获的板级输入。
- `configs/zizhan-wifi-sm8475.json`：MIX Fold 2 自己的 live DT 板级输入；zizhan 构建使用它。Pong 的 PHY 表、WLAN 供电列表和时钟数组不能直接用于 zizhan。
- `PongWifiPlatform.cpp`：Pong 的供电、PCIe/PHY、BAR、独立 SID `0x1c01`、
  native 4 KiB 页表和 MSI；UFS 就绪后再取得独立 context bank，保留 UFS 的 SID/队列。
- `ath11k/PongAth11k.c`：实际 Linux v7.0.14 ath11k PCI/MHI/QMI，连接 UniXNU 的 station ABI。
- `PongWifiNet.cpp`：Darwin 24 ifnet、Apple80211 ioctl、RX/TX 和网络事件。
- `scripts/build-pong-ath11k.py`：编译实际驱动；内部链接拒绝缺失实现，将 Linux shim 符号隔离。
- `scripts/build-pong-wifi-native.py`：编译板级/网络代码，合并归档并延后注册网络类。
- `CONFIG_XNU_PONG_WIFI=y`：构建并链接归档；`pong_wifi=1` 启动板级工作线程。

APSS DRV2 使用 Pong DT 的 active TCS4，保留 GPU 的 TCS3。使用 SM8475 GCC
`0x7bxxx`、真实 PHY 表和 cmd-db `SN7` 带宽投票。CPU 和 SMMU 的 DMA 环使用
Normal-NC，页表独立保留。使用 DesignWare 控制器的 MSI 接收器，按 Pong DT
`int_global_int` 路由到 SPI140（GIC INTID172）；PARF MSI0 为 bit23。
端点 MSI 数据为 0..31，Linux shim 的 IRQ base 800 仅作内部编号。无需 GIC MBIS
或虚构 ITS 命令完成。MSI 目标有单独保留页；中断先清 receiver 和 aggregator 再 EOI。

固件来自本机 modem 中 `image/qca6490`，仅嵌入忽略的本地构建产物。
BDF 按 QMI chip/board ID 使用 Nothing CNSS2 的文件命名规则，AMSS 按
实际硬件 major 选择；不将 PCI revision 当成固件 major，不随机选择 board-data。
高位 board ID 组合文件名时保留 QMI chip ID 决定的 `bdwlan`/`bdwlang` 前缀；
本机实际选中了哪一个文件仍以设备日志为准。
无线地址使用固件报告的地址，不伪造出厂 MAC。WPA nonce 使用 XNU `read_random`。

## 当前证据

真实 ath11k、PCI、MHI、QRTR、QMI、station 和网络代码已编译接入。
固件启动、MSI 实际到达、BSS 扫描、认证、地址配置及联网仍需分别记录真机结果。
只有 station 就绪且具有有效硬件 MAC 后才发布网络接口；失败记录原因并让 iOS 继续启动。
不会用空的成功实现替代固件、扫描或链接结果。

services44 按本机 DT 的 `gdsc-vdd-supply` 补接独立 collapse vote：
`0x162128` bit0，PCIe0 GDSCR 为 `0x17b004`。启用时只清除此 consumer 的位；
不使用 Sheng 的 collapse 寄存器。按 Nothing `pci-msm.c`，PHY 源在 GDSC
开启时选择，PIPE 分支在 PHY 表和稳定等待后再启用；补齐 `xo.lvl=3`
参考时钟投票和训练前的 lane-skew/PARF 配置。实际 link/扫描仍待真机日志。

`PongWifiPci.cpp` 是早期的只接收现有 PCI 交接的辅助代码，完整路径由
`PongWifiPlatform.cpp` 负责；它不被额外当作另一个 PCIe owner 启动。

services46 对照官方 network.md 补接 `nw_wifi_set_events`：在
`nw_wifi_start/step` 前安装回调，ifnet 仍等真实 MAC/信道表就绪才发布。
补齐 PHY rate-change 根时钟的 GPLL0 父时钟 vote 和 lock 等待，以及
slave Q2A 分支的 halt 检查。Cape 与 Waipio 共用 Nothing 的 gcc-waipio.c；
其中 Cape fixup 改 PLL 操作和部分 UFS/SDCC 定义，不能仅凭文件名判定
整个 PCIe 寄存器表不适配。没有放宽 DLL/端点 ID/MSI/DMA 的成功条件。
services45 仍停在 DetectQuiet，下一轮链路和固件扫描结果待实际日志。

services47 保存 services46 的 DetectQuiet 日志后，对照 Pong 的实际 DT 和
Nothing 的 gcc-waipio.h/c，补齐第二路 aggregate NoC（ID9/vote bit11），
恢复 active CLKREQ/PARF PM 配置，保留正常电源稳定等待；真实链路建立后
再配置 Pong 的 type1 memory aperture。没有延长训练超时来伪造成功。
链路、MSI、固件和扫描结果继续以实际日志为准。

services60 对照 services59 日志的 DLL 未激活，显式启用 PORT_LINK_CONTROL DLL_LINK_EN，清除 FAST_LINK，并以确定的 Gen1 target 训练；不降低实际端点或 DLL 成功条件。尚待本轮真机链路与扫描结果。

## iPadOS 18 IPv4 租约与路由

启用 Wi-Fi（`CONFIG_XNU_PONG_WIFI=y`、`pong_wifi=1`）时，原生
IPConfiguration 仍负责地址、续租和 DHCP 冲突检测。若当前 en0 地址已生效而
系统没有可用的默认路由或 DNS，`wifi-service18` 通过只读 Apple80211 请求
读取本次连接中与 DHCPREQUEST 匹配的 ACK，只把验证过的网关和 DNS 发布到独立
的 SystemConfiguration 会话；不会修改原生服务或设置固定地址。原生路由和
DNS 恢复后让回系统。地址丢失、租约失效或链路代次切换后释放该会话。

驱动只跟踪与本机 MAC、当前事务和当前链路一致的 ACK。拒绝的 ACK、NAK、
RELEASE、过期和断线不会保留旧快照；有 classless 路由选项的包交给原生
DHCP 路由策略。人工制造续租、断线和公网请求仅在本地验证镜像上开启。

详细设备结果见 [Wi-Fi 与 USB 记录](../../docs/progress/2026-11-04-wifi-usb.md)。
