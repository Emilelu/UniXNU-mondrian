# sheng 内核线参考审计（iOS 27 / 24A446）

用户 2026-11-20 定的铁则 12：内核层与驱动层的参考源必须包含 `E:/hackios/UniXNU-sheng`，
不能只写「参考过」，要给补丁名与 file:line。本文逐条回答三个问题：sheng 的补丁里哪些与 Wi-Fi 有关、
我们这一边哪些是它已经解过的、我们有没有重复发明。

## 坐标

- 仓库 `E:/hackios/UniXNU-sheng`，`origin/main` 抓到的是 a68ee4e（键盘盖那条提交）。
- `board.toml:9` `os_profile = "ipados-27.0.1-24A446"` —— 与我们同一个 OS profile，同一套 Darwin 26 调用。
- 它的 `patches/xnu-12377/series` 有 **25** 条（`grep -vE '^#|^$' | wc -l`，不是 18；18 大约只数了带 `sheng-` 前缀的那些）。
- 我们的 `patches/xnu-12377/series` 现在是 31 条（本次合并后：删掉一条重复的、补一条 540 字节事件）。

## 三条与 Wi-Fi 直接有关

### 1. sheng-wifi-association-event.patch —— 我们照它补了 0542

改 `bsd/kern/kern_event.c` 的 `kev_post_msg_internal()`。原文把 5 个描述符的总长和 `MLEN`（256 B）比，
超过就 `EMSGSIZE`；12377 的同名函数在 `.cache/xnu-work/bsd/kern/kern_event.c` 里一字不差（`total_size > MLEN`
在合并前的源码里紧挨着 `m = m_get(wait, MT_DATA)`）。24A446 的关联结果是 540 字节的 `pong_assoc_event27`，
所以 OUR 的 `pong_kev_post`（`drivers/PongWifi/PongWifiNet.cpp:68` 把 `_kev_post_msg` 绑成 `pong_kev_post`）
在真 27 内核上每投一次关联结果就会被内核丢掉，而用户态在等一个永远不会到的 kevent。

sheng 的修法是把 IEEE80211 类放宽到 `MCLBYTES` 并用 `m_getcl` 分配簇，同时对每个描述符做上限检查。
我们落成 `patches/xnu-12377/0542-k60-association-event-cluster.patch`（BSD-2-Clause-Patent，
`Co-authored-by: UniXNU-sheng contributors`），注释写明来源；`patch -p1 --dry-run` 在合并前的
12377 源码上 offset -1 通过。

**这条的意义**：它是「离线全绿、上机才发现」的典型——host 测试、ABI 测试、符号计数都不会失败，
因为丢事件发生在内核里，不在我们代码里。

### 2. sheng-wifi-launchd-cache.patch —— C2 的答案，而且我们已经有同一套机制

改 `bsd/kern/kern_exec.c` 的 `native_gpu_addon_prepare()`（sheng 的 hunk 在 `@@ -8675,3 +8675,19 @@`）。
它做两件事：

- 把 owner overlay 的 `/private/var/ngpu/xpc` 挂到 `/System/Library/xpc`，只覆盖
  `foreground_user_endpoints.plist` 与 `launchd.plist` 两个文件；
- 把 `/private/var/ngpu/wifi-bin` 挂到 `/usr/libexec`，只覆盖 `launchd_cache_loader` 与
  `unixnu-wpa_supplicant` 两个文件，并把 `unixnu-wpa_supplicant` 作为 xpcproxy 认可的系统可执行入口。

也就是 C2（27 的 wifid 是否要签名 launchd 与 `org.unixnu.wifi.control`）的答案：**要**，而且路径是
「预编译的 launchd 字典里加 job + 系统路径下的签名可执行文件」，不是往 `/usr/sbin` 里塞一个自签二进制。
注释还点明 detached signature 要过 trust cache，所以签名文件必须跟 addon 一起走。

我们这边同一套机制已经在 `patches/xnu-12377/0527-k60-bt-launchd-cache.patch` 里（蓝牙线做的）：
它把 `/private/var/ngpu/xpc` 挂到 `/System/Library/xpc`（同样两个 plist），把 `/usr/sbin` 挂给
`QcaBluetooth.runtime`，并且用 `native_bt_runtime_bin_stage == 5 && !native_bt_runtime_bin_status`
当前置条件。**wifi 侧要做的不是新写一套挂载，而是给同一个 helper 再加一条 `/usr/libexec` 的
`unixnu-wpa_supplicant` 与一个 xpc job**，这属于 27 用户态线的工作，不是驱动代码。

### 3. zzzz-sheng-ipados27-bringup.patch —— 机配置这一层它已经解过

1981 行、35 个文件，含 `pexpert/pexpert/arm64/BCM2837.h`（`@@ -0,0 +1 @@` 段在补丁第 1964 行附近）、
`osfmk/arm64/start.s`、`osfmk/arm/cpu_common.c`、`osfmk/arm/pmap/*`、`osfmk/arm64/cpu.c`、
`bsd/kern/bsd_init.c`、`bsd/vfs/kpi_vfs.c` 等。它的路线是**在 12377 上把 BCM2837 机配置坐实**，
而不是像 16 线那样新建一个 `PONG.h`——这正是 main 的 `driver_records = "DEVELOPMENT_ARM64_BCM2837"`
（`board.toml:373-376`）走的路，也是 `bcm2837-machine-config.patch` 建 `config/MASTER.arm64.bcm2837` 的原因。

对我们的 B4/B5：**12377 的导出面不是缺口**。我们在 16 线看到的 `psci_smp_*` / `_pong_cpu_startup_finished`
来自我们自己 fork 的 `drivers/ArmCpu/ArmCpu.cpp` 遮蔽了 catalog 的 `component:ArmCpu`（catalog 版自带
`psciCall(hvc, 0xc4000003, …)`，不引用这两个符号）；main 的 `d7cf3300` 已经用 `0540-k60-psci-smp.patch`
（真实现，不是 stub）把它补齐，`0541-k60-virtual-timer-guard.patch` 处理 `CNTP_CTL_EL0`。sheng 没有 psci 补丁，
因为它没有 fork ArmCpu。

## 相邻但不是 Wi-Fi 的一条

`source-storage-runtime.patch` 在 `bsd/kern/bsd_init.c` `vfsinit()` 之后 `weak_import` 地调
`native_source_storage_start()`，是它 stage-0 到 root 的存储路径，和我们的 UFS/PongUfs 不同源；
我们 27 线当前 `CONFIG_XNU_NATIVE_UFS=n`（stage 0 不挂根），所以不跟。

## 我们重复发明了什么（本次审计的真实产出）

1. **`patches/xnu-12377/availability-spi.patch` 与 main 的 `0530-k60-spi-availability.patch` 完全重复**。
   两者都改 `EXTERNAL_HEADERS/Availability.h`、都给 `__SPI_AVAILABLE` 空定义；0530 还多给
   `__SPI_DEPRECATED` 与 `__SPI_DEPRECATED_WITH_REPLACEMENT`，注释也写得更完整。我们那条是 2026-11-20
   凌晨在旧 main 上自己写的，合并时才发现 main 早就有了。**已删除自己的那条，series 只留 0530。**
2. **`0540-k60-psci-smp.patch` 与 catalog `component:ArmCpu` 重复**，但那是因为我们 fork 了 ArmCpu
   （`drivers/ArmCpu/ArmCpu.cpp`，779 行）才需要外部 psci 入口。要么把 fork 收回 catalog，要么留 0540——
   归 27 线裁决，不属 wifi。
3. **launchd cache 挂载我们写在 BT 补丁里（0527），sheng 写在 wifi 补丁里**，同一套 `native_gpu_addon_mount`。
   我们不是重复发明，但**分工写反了**：wifi 的守护进程要用这个挂载，却由蓝牙线提供。做 27 用户态时要么把
   它提成公共补丁，要么让 wifi 补丁复用 0527 的 helper，不要写第二份。

## 结论（给下一步用）

- 540 字节事件：**必须**有内核侧放宽，已落 0542；否则 27 上关联结果永远到不了用户态。
- C2：sheng 的 `sheng-wifi-launchd-cache.patch` 就是答案，落到我们树上=给 0527 的 helper 加
  `/usr/libexec/unixnu-wpa_supplicant` 与一个 xpc job；这是 27 用户态线的工作。
- B4/B5：sheng 证明 12377 不需要 PONG.h，也不需要外部 psci；我们的 0540/0541 已经把这条补齐。
- 不抄 1981 行的 bringup：我们的等价物是 `bcm2837-machine-config.patch` + 0540 + 0541。
- sheng 剩下的 22 条（cpu-idle / amp / appsync / bluetooth / latency trace / checkpoints / edge matrix）
  与本线无关，不引入。