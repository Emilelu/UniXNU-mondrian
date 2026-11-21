# sheng 内核线参考审计（iOS 27 / 24A446）

用户/lead 于 2026-11-20 要求：内核层与驱动层的参考源必须包含 `E:/hackios/UniXNU-sheng`，不能只写「参考过」，
要给补丁名与 file:line。本文逐条回答三个问题：sheng 的补丁里哪些与 Wi-Fi 有关、我们这一边有哪些它已经解过、
我们有没有重复发明。此项是 lead 的参考源要求，不是仓库的 agent 消息铁则 12（那条讲 steer/followup）。

## 坐标与规模

- 仓库 `E:/hackios/UniXNU-sheng`：本地 checkout HEAD 是 `a68ee4e`；审阅的 `origin/main` 是
  `c8f92b208068eeaa4cd2b0f592671f04ee70076e`。已核对的是 `sheng-wifi-launchd-cache.patch`
  （blob `7f483117ef0988ce1afe81f1e4d9f67fa019db52`）与 `check-wifi-launchd.py`
  （blob `dd9f5ddad970b9e33da74be5e7a5fdc0d7e4c88e`）；生产打包脚本、bringup 补丁、
  `WifiNet.cpp`、`check-wifi-association.py` 随 revision 不同。下文源码行号以 Git blob 为准，
  不以本地工作树为准；同一 `os_profile` 不代表每个后来共用文件都是同一 OS ABI。
- `board.toml:9` `os_profile = "ipados-27.0.1-24A446"` —— 与我们同一个 OS profile 家族。
- 它的 `patches/xnu-12377/series` 有 **25** 条（`grep -vE '^#|^$' | wc -l`），不是 18；18 大约只数了带
  `sheng-` 前缀的那部分。
- 我们的 `patches/xnu-12377/series` 现在是 **31** 条（删掉重复的 availability 补丁、加入 0542 之后）。
- 25 条里与 Wi-Fi 直接有关 **2** 条（第 10、12 条），共用加载器 **1** 条（第 11 条），Wi-Fi 用户态前置 **2** 条
  （第 5、6 条），其余 20 条无关。下面逐条给出目标 hunk 与复用判断。

## A. sheng 的 25 条

| # | 补丁 | 目标 hunk / 关键行 | 判断 |
|---|---|---|---|
| 1 | `zzye-sheng-cpu-idle.patch` | `osfmk/kern/processor.c @@ -2032,3 +2032,21`；`:15 sheng_cpu_idle_mach` | 仅参考（空闲统计 API） |
| 2 | `zzyf-sheng-amp.patch` | `sched_clutch.c @@ -1379/-1401/-1473/-6359/-6444`；`BCM2837.h @@ -17` | 仅参考（Edge/AMP） |
| 3 | `zzyd-sheng-audio-addon-mount.patch` | `kern_exec.c @@ -8139/-8594`；挂 audio HAL | 不适用（音频） |
| 4 | `source-storage-runtime.patch` | `bsd_init.c @@ -796,2 +796,6`；`:7 native_source_storage_start` | 不适用（存储；我们 stage 0 不挂根） |
| 5 | `zzzz-sheng-ipados27-bringup.patch` | 1981 行/35 文件；`kern_exec.c @@ -4332`、`kpi_vfs.c @@ -105`、`cpu.c @@ -139`、`proc_reg.h @@ -1103`（`T0SZ_USER 17`）、`start.s @@ -879`、`vm_dyld_pager.c @@ -145`、`BCM2837.h @@ -8`（`HAS_16BIT_ASID 1`） | **Wi-Fi 用户态前置**；只到 bsd_init 的部分等价 |
| 6 | `vmwait-dyld-pager-source-release.patch` | `vm_dyld_pager.c @@ -1330,8 +1330,32`、`@@ -1362,6 +1386,11`；释放 source page 防 APFS UPL 自等待 | **未解**；4 KiB dyld fixup 的用户态前置 |
| 7 | `zzzzzz-sheng-latency-trace.patch` | `exception.c @@ -922/-933`；`sheng_user_fault_hook` | 不适用（诊断） |
| 8 | `zzzzzzzz-sheng-exit-latency.patch` | `kern_exit.c @@ -1638/-1647`；`sheng_user_exit_hook` | 不适用 |
| 9 | `zzzzzzzzz-sheng-unnest-trace.patch` | `vm_unix.c @@ -809/-833`；`sheng_unnest_hook` | 不适用 |
| 10 | `sheng-wifi-launchd-cache.patch` | `kern_exec.c @@ -8675,3 +8675,19`；两个整目录 union 挂载：`/private/var/ngpu/xpc`→`/System/Library/xpc`，`/private/var/ngpu/wifi-bin`→`/usr/libexec`；四个路径是挂载后存在性探针 | **直接 Wi-Fi**；0527 只重叠 xpc 挂载，没有 Wi-Fi `/usr/libexec` 视图和自有 supplicant job |
| 11 | `sheng-bluetooth-runtime.patch` | `kern_exec.c @@ -8711`；`bluetooth=1` 时挂 `/usr/lib`、`/usr/sbin` | 共用加载器；不是 Wi-Fi job 或运行证据 |
| 12 | `sheng-wifi-association-event.patch` | `kern_event.c @@ -8912,22 +8912,21`；`:9-10 maximum = IEEE80211 ? MCLBYTES : MLEN`；`:17` 逐描述符上限；`:30 m_getcl` | **直接 Wi-Fi**；0542 已完全等价 |
| 13 | `sheng-main-thread-profile.patch` | `sleh.c @@ -767/-804`、`mach_msg.c @@ -384/-392/-946/-1042` | 不适用（PMU/SB 诊断） |
| 14 | `sheng-cache-input-diagnostic.patch` | `exception.c @@ -1064/-1071`；cache-log | 不适用 |
| 15 | `sheng-bluetooth-exit-diagnostic.patch` | `kern_exit.c @@ -1650`、`exception.c @@ -1053`；bluetoothd/BlueTool | 不适用 |
| 16 | `zzzzzzzzzz-sheng-sigp-reinit-assert.patch` | `osfmk/arm/cpu_common.c @@ -942,7 +942,8`；`sheng_sigp_recovered` | 仅参考（CPU 信号恢复） |
| 17 | `sheng-appsync-runtime.patch` | `kern_exec.c @@ -8727`；挂 UniXNUAppSync.dylib | 不适用 |
| 18 | `sheng-appsync-user-trust.patch` | `appsync_trust.inc` 新 111 行；`kern_exec.c @@ -2102`、`kern_trustcache.c @@ -553/-810`、`ubc_subr.c @@ -44/-4836/-4909`、`trust_caches.h @@ -152` | 不适用 |
| 19 | `zzzzzzzzzzz-sheng-edge-matrix.patch` | `sched_clutch.c @@ -1401/-4952/-5000/-6399/-6486` | 仅参考（Edge 计数器） |
| 20 | `zzzzzz-sheng-bsd-checkpoints.patch` | `bsd_init.c @@ -81/-586/-799/-821/-844` | 启动诊断；仅参考 |
| 21 | `sheng-bootstrap-checkpoints.patch` | `startup.c @@ -1/-923/-945`、`bsd_init.c @@ -1305/-1326` | 启动诊断；仅参考 |
| 22 | `sheng-headless-startup-checkpoints.patch` | `boot_progress.h @@ -17`、`kern_exec.c @@ -10094` | 启动诊断；仅参考 |
| 23 | `sheng-startup-failure-log.patch` | `kern_exec.c @@ -10118/-10130`、`debug.c @@ -1252` | 启动诊断；仅参考 |
| 24 | `sheng-process-exit-log.patch` | `kern_exit.c @@ -2081`；`boot_log_process_exit` | 启动诊断；仅参考 |
| 25 | `sheng-platform-sleep.patch` | `cpu.c @@ -99`（定义 `arm64_platform_sleep_hook`）、`@@ -1141/-1183`；`cpu_common.c @@ -416/-934`；`IOPMrootDomain.cpp @@ -565/-8507`；`platform-sleep=1` 解除禁用 | **关键交叉**；我们只有符号存储，没有调用点 |

## B. 我们 31 条里与 sheng 有交集的部分

| 我们 | 交集 | 结论 |
|---|---|---|
| `0542-k60-association-event-cluster.patch:16-43` | sheng #12 `sheng-wifi-association-event.patch:3-30` | 等价已解；归一化可执行 diff 相同，0542 只差上下文偏移与署名 |
| `0527-k60-bt-launchd-cache.patch:36-41` | sheng #10 的 xpc 挂载 | 部分重叠；0527 没有接入 Wi-Fi `/usr/libexec` 视图和自有 supplicant job。`launchd_cache_loader` 在参考补丁里是系统路径可见性探针，不能据此说目标系统缺这个文件 |
| `armcpu-sleep-hook.patch:13` | sheng #25 | **不等价**：我们只定义函数指针（`= NULL`），ArmCpu.cpp:477-479 赋值，XNU 没有调用点；`platform-sleep=1` 实际不生效 |
| `0540-k60-psci-smp.patch`、`0532-k60-cpu-start-completion.patch` | 无 sheng 对应；对位 catalog `component:ArmCpu` | 不是重复 sheng；是我们 fork ArmCpu 后的链接补齐。catalog 版自己调 `psciCall(..., 0xc4000003, ...)` |
| `bcm2837-machine-config.patch` + 0540/0541 | sheng #5 | **只到 bsd_init 的部分等价**，不是整条 bringup |
| `0530-k60-spi-availability.patch` | 无 sheng 对应；对位我们早先的 `availability-spi.patch` | 内部重复已删，series 只留 0530 |
| `0526/0527` 的挂载 helper | sheng #10/#11 同类机制 | 复用相同类型的目录挂载 helper；触发条件、执行顺序与服务对象不同。Wi-Fi 若需该视图，应复用机制而不是写第二套 |

当前已落地的直接 Wi-Fi 补丁只有 0542；0526/0527 是加载器机制（由蓝牙线持有）。
C2 的 `/usr/libexec`、job、缓存与信任路径仍未集成；是否需要进一步适配，应由目标用户态证据决定，不能由补丁数量推断完成。

## C. 540 字节关联事件

原 `kev_post_msg_internal()` 把消息总长与 `MLEN` 比较并拒绝超限，之后用 `m_get`；`MLEN` 不是固定 256 B，
12377 的 `bsd/sys/mbuf.h:631,674` 从配置相关的 `_MSIZE` 扣除 header 得出它。24A446 关联结果
`pong_assoc_event27` 是 540 B，加 16 B `en0` 描述符与 24 B 内核事件头，总消息 580 B。
`PongWifiNet.cpp:68` 把 `_kev_post_msg` 绑定为 `pong_kev_post`，所以原内核在
`kev_post_msg_internal()` 返回 `EMSGSIZE`——不是 kext 符号缺失。

0542 把 Apple IEEE80211 事件上限设为 `MCLBYTES`，逐描述符检查剩余容量，并在大于 `MLEN` 时用 `m_getcl`。
源码坐标 `bsd/kern/kern_event.c:8912-8957`，分配见 `bsd/kern/uipc_mbuf.c:1839-1860`。
离线回归 `scripts/tests/test-wifi-association-event.py` 把真实补丁应用在原始片段上并编译执行：基线拒绝 580 B，
补丁版本在 `MLEN=224` 与 `MLEN=256` 下各过 19 项边界、拷贝与分配检查；它不证明 socket 订阅者收到事件，
也不替代设备上的关联与 wifid 观察。

## D. launchd / supplicant（C2 仍未回答）

sheng #10 在 `native_gpu_addon_prepare()` 里调用 `native_gpu_addon_mount()`：`/private/var/ngpu/xpc` 挂到
`/System/Library/xpc`，`/private/var/ngpu/wifi-bin` 挂到 `/usr/libexec`，并传入
`foreground_user_endpoints.plist`、`launchd.plist`、`launchd_cache_loader`、`unixnu-wpa_supplicant`
作为挂载后检查的路径。公共 12377 helper（`4eaf2b9d86068badc3af9b023d4b80582b2798d5` 的
`patches/xnu-12377/zzy-native-gpu-addon-mount.patch:23,298`）使用 bindfs 与 `MNT_RDONLY | MNT_UNION`，
挂整个目录；它检查两个探针路径可见，不读内容、不验签。stage/status `5/0` 只能说明挂载及两次
路径查找成功。

sheng 的打包链明确：job `org.unixnu.wifi.supplicant` 以 root 执行
`/usr/libexec/unixnu-wpa_supplicant -Dsheng -ien0 -c/private/var/ngpu/etc/wifi/wpa_supplicant.conf -q -s`，
`RunAtLoad`/`KeepAlive`；cache 与 Mach-O 分别签名并记录 CDHash。它保留 `com.apple.wifid`，
由自己的服务承担认证。这是 sheng 为 ath12k/mac80211 后端做的选择，不是 stock 24A446 wifid 的普遍要求。

反例足以区分「挂载」「验签」「导入」：sheng 的蓝牙启动报告记录到挂载 `5/0`、loader 信任 CDHash 并交付，
而 PID 1 仍以 namespace `7`、subcode `1` 报 `No service cache`；packed cache 与三份运行副本的长度、
FNV-1a 都不同。`check-wifi-launchd.py` 的 `hardware_service_started=False` 只限定该次 host 检查
（测试 job、host `libxpc`、detached signature、篡改拒绝与 job 冲突），不是硬件服务运行证据。

K60 的 0526/0527 复用同类挂载机制，目前由蓝牙路径触发，没有 Wi-Fi `/usr/libexec` 视图或 supplicant job。
**C2 保持 open**：先确认目标 wifid 实际调用谁，再决定是否增加独立 job；不要把 `com.apple.wifid` 误写成
我们自己的 job。

## E. bringup 与平台睡眠：不是等价物

sheng #5 的 1981 行里，除了到 bsd_init 的机配置，还带 47 位用户地址空间（`T0SZ_USER 17`）、4 KiB pmap 几何、
16-bit ASID、GPU sandbox 放行、bindfs、dyld 4K fixup 与 OS* 空值安全。我们目前只走到 bsd_init：
`bcm2837-machine-config.patch` 建 `config/MASTER.arm64.bcm2837`，0540/0541 补 CPU 与虚拟定时器。
**这些是「尚未实现」，不是「已用等价物替代」**；27 用户态一开就会撞 47 位 VA/4K fixup。

sheng #6 的 `vmwait-dyld-pager-source-release.patch:21-55` 是 dyld 4K fixup 的直接前置，我们无对应，属未解。
sheng #25 的平台睡眠有完整调用链；我们的 `armcpu-sleep-hook.patch` 只存指针，没有调用点，不能算解过。

## F. 我们重复发明了什么

1. `0542` 对 sheng #12 是**有意移植**，已带 BSD-2-Clause-Patent 与
   `Co-authored-by: UniXNU-sheng contributors`，不算重复发明。
2. `availability-spi.patch` 与 main 的 `0530-k60-spi-availability.patch` 完全重复；已删自己那条，series 只留 0530。
3. `0540/0532` 的重复对象是 **catalog ArmCpu / 我们自己的 fork**，不是 sheng。要么收回 fork，要么保留并承认这是
   fork 的代价；这条由 27 线按 build graph 决定。
4. launchd cache 挂载我们写在 BT 补丁 0527 里，sheng 写在 Wi-Fi 补丁里：不是重复发明。若 C2 证实需要该视图，
   可以共用同一挂载与 cache 合并机制；Wi-Fi 是否启用应独立于蓝牙 gate，不能因为「同机制」就推断已解。

## G. 结论

- 540 字节事件：若参考 producer 的 580 B 信封就是目标事件，则内核侧必须放宽；已落 0542。
  该条件依赖目标消费者确实接收此事件，运行时证据仍未取得。
- C2：sheng 记录的是它自己的 supplicant 选择，不是 stock 24A446 wifid 的普遍要求；保持 open。
- C3：判据改为 I 节的离线阶梯——L0 已完成，L1/L1b 离线可做，L2/L3 仍阻塞；证据只到 L0 或 L1b 时 C3 保持 open，
  `kSupportedChannels` 的 0x80 位不动。
- B4：三个内核符号存在；事件能否送达另由 0542 与运行时验证回答。
- B5：内核页表、DMA/SMMU 的 4 KiB 几何仍未验收。B6 的 `ie_bytes=2048` 是扫描元素字段宽度，两者独立；匹配的宽度戳也不能证明 station API 已编进归档。
- bringup：我们只到 bsd_init，不能把 sheng 的 47 位 VA/4K pmap/16-bit ASID/dyld fixup 说成已解决。

## H. 契约差异与最小补证

两份只读复核（launchd、频道/ABI）把「已实现」「参考一致」与「目标 24A446 已证明」分开。下表是当前能证明的范围。

| 契约 | 可以证明 | 仍不能证明 |
|---|---|---|
| C3 频道位 | sheng 对 supported 与 hardware-supported 共用静态 20 频道，并单独置 `flags |= 0x80`；scan/current 的 `fill_channel()` 不加该位（`package/WifiNet.cpp:500-506,695-699`）。我方动态枚举，未加该位；代际锁定后才排除 ≥5925 MHz（`drivers/PongWifi/PongWifiNet.cpp:900-918`）。 | 真实 24A446 消费者要求、忽略还是拒绝 0x80。zizhan 的「比较完整 flag word」仍是继承解释，不是本次取得的消费者反汇编（`SBL-MISSION.md:921-928`）。 |
| C1 selector / ioctl | 我方现有 selector-0 标注为 22H374：输入总长 0x3c30，payload 容量 0x3c00 位于 +8，40 B 请求位于 +0x3c08（`PongWifiNet.cpp:1038-1049`）；0x3c00 是容量上限，不是固定返回量，scalar GET 可回 4 B、SET 回 0（`:1095-1097,1123-1149`）。sheng 的 macOS 分支保留 selector-0，同时保留 ioctl（`WifiNet.cpp:761-774`）。 | 不能从 sheng 非 macOS 分支拒绝 user client，推出 stock 24A446 wifid 普遍只走 ioctl。`newUserClient` 是建立连接，长度契约在 selector 调用与其 caller/receiver。 |
| scan 请求/结果 | sheng 与我方都有 request-86 0x14e8：SSID count +0x8、list +0xc、type +0x200、channel count/list +0x210/+0x214；结果 0x8e8，IE +0x8c/2048 B，timestamp +0x8d0（`WifiScan.h:2-35,79-89`、`WifiScanResult.h:2-23`）。 | 这两个头文件注明来源是 IO80211 **26C5035r（macOS）**，不能无条件当作 24A446 wire 证据。与我方常量、static_assert、fixture 对齐只证明实现/模型一致（`test-pong-abi.py:40-85,110-123`）。 |
| association | sheng 区分 legacy 0x250/592 B 字段 +0xc 与新 0x290/656 B 字段 +0x10；事件 540 B，result +0x214、valid +0x218（`WifiNet.cpp:96-128`）。我方另保留 22H374 0x384（`PongWifiAbi.h:35-58`）。sheng 有早期设备报告（WPA2/DHCP/流量/join-result，`reports/ipados27-wifi-association.md:25-32`）。 | 报告对应早期提交 `fa9af675…`，不能补成当前 pinned blob 的真实 wire bytes，也不能替代 K60 24A446 验收。注释里的 `__performAssociation`/`_dispatchAsyncAssocEvent` 是可追查线索，不是随附二进制证据。 |
| 22H374 正证据 | mission34b/36 记录过真实 5 GHz Settings 行与连接可用；修复点是 1024 B IE/完整元素，不是加入 0x80（`SBL-MISSION.md:1224-1242`）。 | 这是 22H374 的正证据，不能外推到 24A446。 |

### H.1 最小补证（按契约分别验收）

- **C3：** 带目标 build 与进程身份的真实 24A446 GET 27（与 254 区分）请求与回复、原始 `{version,channel,flags}`；
  同一 5 GHz BSSID 的 scan/current 完整 flag；消费者保留/过滤结果；对应的 Settings 行。或提供 provenance/UUID
  匹配的消费者解析、比较反汇编。捕获某个 flag 只证明观察值，不自动证明其必要性。
- **C1：** 先确认真实 caller 走 ioctl 还是 `IOServiceOpen`/selector。若走 selector，记录 input size、output
  capacity 与 actual size、request type 与返回码；不能把 0x3c00 上限当成固定返回长度。
- **scan/association：** 取得目标 24A446 request-86、scan-result 请求大小与字段，以及真实 association
  请求/完成事件的长度、关键偏移与消费结果；或由匹配目标二进制的 caller/parser 交叉确认。驱动自身代码、
  static_assert 与 synthetic fixture 不能替代这一层。
- **station 归档：** 现有三个候选都只有一个成员 `PongAth11k-linked.o`，都不定义
  `_nw_wifi_power` 与 `_nw_wifi_scan_frequencies`；唯一 arm64e 的 `ath11k-abi27e` 仍是
  `ARM64E (0x2)` 但缺这两个 API。驱动归档 `teardown27g` 把二者都记为 `U`。可接受的最小交付是：
  完整 arm64e station 归档；与驱动共同生成的 `nw_abi.h`；一份绑定「源码 revision、target、成员、生成头
  SHA-256、归档 SHA-256」的构建记录；以及 `llvm-nm --defined-only` 对两个 API 的实证。只匹配
  `abi/nw_abi.stamp` 的旁车文件不够，因为构建器只校验 `ie_bytes`，不校验 `header_sha256`。
  这套验收已写成 `scripts/check-wifi-station-archive.py`：一条命令同时查成员架构（arm64e）、两个 API
  是否为**已定义**符号、`stamp` 的 `ie_bytes=2048` 与 `header_sha256` 是否等于同目录 `nw_abi.h`；
  全部成立退 0，契约不符退 1，缺输入或工具退 2。实跑三个候选：`ath11k-abi27` 缺 stamp（退 2）、
  `ath11k-abi27s` 成员是 arm64、`ath11k-abi27e` 架构与 stamp 通过但两个 API 都缺（退 1）。
- **C2：** 见 D 节；先取目标 wifid 的 job、实际调用库与传输路径，再决定是否复用 0526/0527 增加 Wi-Fi 视图与
  独立 job。`5/0` 或 cache loader 交付都不是服务已运行。最小输入分别是：
  目标 build、原始 `com.apple.wifid` 的 Label/ProgramArguments/MachServices，以及按 job 定位的 wifid/实际 Wi-Fi 库
  的 UUID 与 SHA-256；同次启动的 image/源码/框架 revision、boot args、station archive hash 与 link map，用于排除临时定义。
  若采用自有服务，还需包内 job、Mach-O、配置、cache、`.sig` 的 hash/entitlement/CDHash/trust 成员；对照
  mount、loader trust/attach/deliver、PID 1 导入或退出码，并比较 packed/Data/系统路径/parser-input 的长度、
  hash 与 binary-plist trailer。最后记录实际 job label、exec/PID/UID/exit 或 xpcproxy/AMFI 拒绝原因，
  把 wifid 扫描/关联请求、EAPOL/装钥、端口授权、收到的关联事件和 DHCP/流量绑定到同一次连接。
  无额外服务时只扫描成功，不能关闭认证；完整 WPA2 装钥、授权与通信成功才证明所测路径无需该服务。

### H.2 文档层的纠正

- 「27 根本不走 user client / 全部走 ioctl」是 sheng 条件编译选择的推广，已删除该断言。
- 「两个描述符说明 27 daemon 按两个描述符取负载」是从 producer 反推 consumer，不成立。
- 「B5 的 4 KiB 与 B6 的 2048 一致即已验收」混淆了页/DMA 几何与扫描元素字段宽度；两者独立，且都不证明
  station API 已编进归档。
- 540 B 的「否则 27 关联结果到不了用户态」依赖目标消费者确实接收该事件；改为条件句。

## I. C3 的离线判据阶梯（0x80 属于哪个字段、谁写它、sheng 的 Ath12k 怎么处理）

三问三答都绑定 revision：sheng `origin/main` = c8f92b208068eeaa4cd2b0f592671f04ee70076e；我方 = eb019542…；
Ath12kWifi = f087c7ddac07e945f20d199dbaf6c95c6db3346a。

1. **字段。** `apple80211_channel` 是 `{uint32_t version; uint32_t channel; uint32_t flags;}`，装在
   `channels_list {uint32_t version; uint32_t count; channel list[401]; uint32_t unused;}` 里（4824 B）；
   见 `drivers/PongWifi/PongWifiNet.cpp:93-94`。0x80 落在**每条频道的第三个字 `flags`**，不在 list 头，
   也不在 selector 输入里。
2. **写者。** sheng 只在 supported/hardware-supported 应答里写它：`package/WifiNet.cpp:695-699`，
   循环体是 `fill_channel(...); out.chans.list[n].flags |= 0x80; n++;`。`fill_channel()`（`:500-506`）
   自己只给基位 `0x2|0x10`（>=4900 MHz）或 `0x2|0x8`（更低），不加 0x80。这份应答是**静态 20 条**
   （11×2.4 GHz + 9×5 GHz），不按硬件过滤，也不含 6 GHz。我方全树没有写 0x80 的地方：
   `PongWifiNet.cpp:581-584` 用同样的基位，`:900-918` 只整条丢弃 >=5925 MHz 的条目，并注明不改 flag 字。
3. **sheng 的 Ath12k 在 27 上怎么处理。** `drivers/Ath12kWifi` 是指向
   `https://github.com/UniXNU/Ath12kWifi.git` 的 gitlink，pin 上条。该模块只提供频率表
   （`nw_wifi_channel_list`）；src 下 0x80 只出现在 crypto/pci 上下文（`nw_crypto.c:25,56,62,63`、
   `nw_pci.c:17`、`nw_mac80211.c:79`），没有频道 flag 写者。所以 0x80 不是驱动或硬件事实，
   而是 Apple80211 shim 的策略位。

**语义边界。** 两棵树都没有 `APPLE80211_C_FLAG` 宏（我方全树 0 命中，sheng `package/` 里也没有
`struct channel {`），所以这个位的**名字**不能从现有源码推出，只能推出位置与写者。把 0x80 当成
「5 GHz 支持位」或「40/80 MHz 位」都是猜测，不写进文档。

**阶梯。** 每一级都写明它能证明什么、不能证明什么：

| 级 | 内容 | 状态 | 能证明 | 不能证明 |
|---|---|---|---|---|
| L0 | 上表三问（字段、写者、Ath12k 不参与） | 已完成 | 位在 flags；sheng 写、我们与模块都不写；不是硬件事实 | 消费者是否需要 |
| L1 | 反汇编 16.6.1 wifid 的 selector-27/254 回复解析，找 `and/tbz #7` 形态的 0x80 掩码 | 可做，未做 | 某一代 wifid 是否消费该位 | 24A446 是否同样 |
| L1b | 已有行为对照：mission19 的 102 条应答与 5 GHz 记录被 16/22H374 侧 daemon 接受 | 已有 | 不含 0x80 的完整字在某一代 daemon 上可用 | 24A446 |
| L2 | 24A446 消费者二进制（SystemOS 的 wifid，`043-68526-711.dmg.aea`；已解密成 6.0 GB APFS，尚未挂载）做 L1 的分析 | 输入待挂载 | 目标代的位语义 | 运行时行为 |
| L3 | 24A446 上机：GET 27 原始回复、同 BSSID 的 scan/current flags、Settings 行 | 阻塞（设备归 Lead） | 端到端 | — |

L1 的输入已经在盘上：`E:/k60-work/scratch/wifid-20G81`（Mach-O arm64，2,606,496 B，sha256 96a3c5df…），
反汇编 `E:/k60-work/scratch/wifid.fresh.dis`（17,398,042 B），以及
`E:/k60-work/scratch/wifid-filter-notes.md`（171 行，只覆盖扫描记录的 WAPI 过滤，不覆盖频道表消费者）。

**边界条款：** 证据只到 L0 或 L1b 时 C3 **必须保持 open**；到 L1 也只能说「16.6.1 这一代如何」，
不能关闭 24A446。C3 由此从「等一份取不到的日志」改成「等 L1 的反汇编结论，或 L2/L3 的任一目标代证据」。

**自审发现（不改驱动）：** `gModern27Client` 只在 `:724`（0x14e8 扫描）、`:813`（关联）、`:918`/`:954`
（2280 B 记录 / 当前网络）置位，而 `:911` 在 supported 应答里读它。所以 24A446 daemon 若在首个扫描或
关联请求之前就问频道表，拿到的仍是 102 条（含 6 GHz）。`SBL-MISSION.md:1634-1635` 已记这个顺序边界；
`PongWifiNet.cpp:906-909` 的注释读起来像过滤已生效，实际第一个应答不生效。
