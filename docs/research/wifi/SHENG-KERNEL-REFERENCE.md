# sheng 内核线参考审计（iOS 27 / 24A446）

用户/lead 于 2026-11-20 要求：内核层与驱动层的参考源必须包含 `E:/hackios/UniXNU-sheng`，不能只写「参考过」，
要给补丁名与 file:line。本文逐条回答三个问题：sheng 的补丁里哪些与 Wi-Fi 有关、我们这一边有哪些它已经解过、
我们有没有重复发明。此项是 lead 的参考源要求，不是仓库的 agent 消息铁则 12（那条讲 steer/followup）。

## 坐标与规模

- 仓库 `E:/hackios/UniXNU-sheng`：本地 checkout HEAD 是 a68ee4e；审阅的 `origin/main` 是
  `c8f92b208068eeaa4cd2b0f592671f04ee70076e`。Wi-Fi 补丁与检查脚本在两个树上 blob 相同。
- `board.toml:9` `os_profile = "ipados-27.0.1-24A446"` —— 与我们同一个 OS profile，同一套 Darwin 26 调用。
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
| 10 | `sheng-wifi-launchd-cache.patch` | `kern_exec.c @@ -8675,3 +8675,19`；`/private/var/ngpu/xpc`→`/System/Library/xpc`；`/private/var/ngpu/wifi-bin`→`/usr/libexec` | **直接 Wi-Fi**；与 0527 部分重叠 |
| 11 | `sheng-bluetooth-runtime.patch` | `kern_exec.c @@ -8711`；`bluetooth=1` 时挂 `/usr/lib`、`/usr/sbin` | 与 Wi-Fi 无关（同一 helper） |
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
| `0527-k60-bt-launchd-cache.patch:36-41` | sheng #10 的 xpc 两文件 | 部分重叠；缺 `/usr/libexec/launchd_cache_loader`、`/usr/libexec/unixnu-wpa_supplicant` 与 job |
| `armcpu-sleep-hook.patch:13` | sheng #25 | **不等价**：我们只定义函数指针（`= NULL`），ArmCpu.cpp:477-479 赋值，XNU 没有调用点；`platform-sleep=1` 实际不生效 |
| `0540-k60-psci-smp.patch`、`0532-k60-cpu-start-completion.patch` | 无 sheng 对应；对位 catalog `component:ArmCpu` | 不是重复 sheng；是我们 fork ArmCpu 后的链接补齐。catalog 版自己调 `psciCall(..., 0xc4000003, ...)` |
| `bcm2837-machine-config.patch` + 0540/0541 | sheng #5 | **只到 bsd_init 的部分等价**，不是整条 bringup |
| `0530-k60-spi-availability.patch` | 无 sheng 对应；对位我们早先的 `availability-spi.patch` | 内部重复已删，series 只留 0530 |
| `0526/0527` 的挂载 helper | sheng #11 同机制 | 功能等价，命名/粒度不同；Wi-Fi 未来应复用，不写第二套 |

直接 Wi-Fi 的只有 0542 一条；0526/0527 是加载器机制（由蓝牙线持有）；其余是核心启动、CPU 与工具链。
没有第二条需要从 sheng 照搬的 Wi-Fi 内核补丁。

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
作为挂载后检查的路径。12377 的 `native_gpu_addon_mount()`（`bsd/kern/kern_exec.c:8187`）挂整个目录
（`MNT_RDONLY | MNT_UNION`），`:8203` 的路径参数是存在性检查，不是文件白名单。

这只能说明 sheng 选择了这套 supplicant/launchd-cache 集成，不能推出所有 24A446 wifid 都必须如此。
`scripts/check-wifi-launchd.py:31-33` 构造 `org.unixnu.wifi.supplicant` job，`:111-115` 明确报告
`hardware_service_started=False`；那是缓存拼接/签名验证，不是硬件服务已启动的运行证据。
我们已有可复用的挂载基础 `patches/xnu-12377/0527-k60-bt-launchd-cache.patch`，但 **C2 保持 open**，
先取目标用户态或运行时证据，再决定是否为 0527 增加 `/usr/libexec` 与 job。

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
4. launchd cache 挂载我们写在 BT 补丁 0527 里，sheng 写在 Wi-Fi 补丁里：不是重复发明，但分工写反了。
   27 用户态时要么提成公共补丁，要么让 Wi-Fi 复用 0527 的 helper，不要写第二套。

## G. 结论

- 540 字节事件：必须有内核侧放宽，已落 0542；否则 27 上关联结果到不了用户态。
- C2：sheng 记录的是它自己的 supplicant 选择，不是 stock 24A446 wifid 的普遍要求；保持 open。
- C3：没有 24A446 二进制或 wifid 日志前不动 `kSupportedChannels` 的 0x80 位。
- B4：三个内核符号存在；事件能否送达另由 0542 与运行时验证回答。
- B5：4 KiB 页的宽度戳已在 27 站上双向验证；内核页表几何仍属 [SOC] 27 线。
- bringup：我们只到 bsd_init，不能把 sheng 的 47 位 VA/4K pmap/16-bit ASID/dyld fixup 说成已解决。
