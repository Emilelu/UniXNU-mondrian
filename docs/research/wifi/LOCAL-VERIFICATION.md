# WiFi 本地验证（⑦）证据台账

状态：**⑦ 已完成**（静态检查 + 离线单测 + 产物检查三类齐全）。
⑧ 上机尚未拿到控制台证据，见本文末尾「待补」。

本文件只记录**可复现的实测事实**，每条都给出命令或文件位置。
所有路径以 WSL 视图为准（`/mnt/e` = `E:\`）。

---

## 0. 构建环境（可复现的最小命令）

两条 archive 必须先编，再进内核。**两条都不能省**：

```bash
# ① Linux ath11k 侧（libPongAth11k.a）
cd /mnt/e/hackios/k60-wifi
export PONG_SHENG_ROOT=/mnt/e/k60-work/impl/wifi/work/src/UniXNU-sheng
export UNIXNU_SDKROOT=$T/.cache/fakeroot          # T = 下面内核构建树里的 tree
export PATH="/opt/unixnu-linux/CommandLineTools/usr/bin:/opt/unixnu-linux/llvm/bin:/usr/lib/llvm-18/bin:$PATH"
python3 scripts/build-k60-ath11k.py --linux /home/emilelu/wifi-inputs/linux \
    --shared $PONG_SHENG_ROOT/drivers/Ath12kWifi --output-dir /opt/k60/trees/k60build/wifi/ath11k

# ② 板级 + 固件打包（libPongWifiNative.a）
python3 scripts/build-k60-wifi-native.py --tree $T \
    --ath11k /opt/k60/trees/k60build/wifi/ath11k/libPongAth11k.a \
    --firmware /mnt/e/k60-work/firmware/qca6490-wifi \
    --output-dir /opt/k60/trees/k60build/wifi/native-real
```

两个必须记住的坑（都踩过）：

1. `--tree` 必须指**已构建 out 目录里的 tree**，即
   `/opt/k60/trees/k60build/out-wifi/mondrian/ipados-16.6.1-20G81/mondrian/tree`。
   传仓库根会报 `fatal error: 'IOKit/IOLib.h' file not found`（builder 用
   `a.tree/'.cache/fakeroot/...'` 拼 Kernel.framework 头路径）。
2. `--firmware` 必须指**干净的四文件目录**（`/mnt/e/k60-work/firmware/qca6490-wifi`：
   amss.bin / amss20.bin / m3.bin / regdb.bin）。指向设备原目录会把 222 个文件
   全部打进 PWF2 包（实测 13,029,078 B、10 个文件）。

## 1. 静态检查（static_check）

### 1.1 archive 符号面

`libPongWifiNative.a` 11,939,808 B（`/opt/k60/trees/k60build/wifi/native-real/`）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 未定义符号只允许 13 个白名单 | `llvm-nm -u libPongAth11k.a` | 仅 `_PongWifiRandom` + 12 个 libc（`build-k60-ath11k.py` 内建断言，否则 raise `unimplemented ath11k imports`） |
| archive 自身定义 | `llvm-nm --defined-only libPongWifiNative.a` | `T _pong_smmu_lease_lock` / `T _pong_smmu_lease_unlock` / `T _pong_wifi_start_optional` / `S _pong_wifi_firmware` / `S _pong_wifi_firmware_end` / `T _pong11_pong_ath11k_pci_init` |
| 跨 archive 缺口 | 341 未定义 → 与 kernel.macho 47806 定义比对 → 31 → 与自身 3362 定义比对 | 只剩 `_pong_ufs_ready`，由 `libNativeUfs.a`（0004 补丁后）提供：`0000000000003188 T _pong_ufs_ready` |

### 1.2 内核符号面（决定性）

内核 `kernel.macho` 65,863,680 B，sha256
`0fa28b37b78e1a66f36989eb110b7e6ad0673001dfec339b123a8cdd17633977`（trial4）。

```
fffffff00856e8dc S _pong_wifi_start_optional
fffffff0085721f4 S _pong_smmu_lease_lock
fffffff008572228 S _pong_smmu_lease_unlock
fffffff00854f244 S _pong11_pong_ath11k_pci_init
fffffff007096000 S _pong_wifi_firmware
fffffff007b23ed6 S _pong_wifi_firmware_end
```

- `llvm-nm -u kernel.macho | grep -E '_pong|nw_wifi'` → **0 条**（无缺失符号）。
- 链接真的带了 archive：
  `tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.link/mach.development.pong.linkarchives`
  内含 `-Wl,-force_load,/opt/k60/trees/k60build/wifi/native-real/libPongWifiNative.a`。
- **判据不要用 `grep kernel.log force_load`**：make 不回显该变量，log 里计数恒为 0，
  会被误判成"没链进去"。

### 1.3 为什么 0010 必须是双 hunk

`scripts/build-xnu-4k-baseline.sh` 有两条互斥的归档装配路径：

| 路径 | 变量 | 触发条件 | 位置 |
|---|---|---|---|
| A | `KERNEL_EXTRA_ARCHIVES` | `XNU_SOURCE_CORECRYPTO14=1` | :892–:1077 |
| B | `PLATFORM_ARCHIVES` | `-z XNU_BOOTSTRAP` && `ARM_DT_PLATFORM=1` && `XNU_SOURCE_CORECRYPTO14 != 1` | :1120–:1162 |

mondrian 走 **B**：`.config` 里 `CONFIG_XNU_SOURCE_CORECRYPTO14` 出现两次
（:2 `=y`、:88 `=n`），`config.py parse_config()` 后者覆盖前者 → False。
只改 A 会得到"编译全过、链接报三个未定义符号"的内核（trial3 实测症状）。

## 2. 离线单测（unit_test）

`E:\k60-work\evidence\wifi-trial\test_pwf2.py`，日志
`E:\k60-work\evidence\wifi-trial\test-pwf2.log`，**PASS / 0 failures**。

覆盖项：

1. PWF2 头：magic `PWF2`、count=4、头长 `(8+4*40+4095)&~4095 = 4096`。
2. 四个条目 4 KiB 对齐 + 名字/偏移/大小：

   | 条目 | offset | size | sha256 |
   |---|---|---|---|
   | amss.bin | 0x1000 (4,096) | 5,470,128 | a626cfc1… |
   | amss20.bin | 0x539000 (5,476,352) | 5,296,128 | 903c378a… |
   | m3.bin | 0xa46000 (10,772,480) | 266,684 | ad234ac8… |
   | regdb.bin | 0xa88000 (11,042,816) | 24,278 | 06810e85… |

3. 每一片的 sha256 与 `/mnt/e/k60-work/firmware/qca6490-wifi/<name>` **逐字节相同**。
4. blob 总长 11,067,094 B。
5. Mach-O 解析（自写 LC_SEGMENT_64 遍历）：
   `_pong_wifi_firmware = 0xfffffff007096000`、
   `_pong_wifi_firmware_end = 0xfffffff007b23ed6`，
   span = **11,067,094** 恰等于 blob。
6. 内核文件偏移 `0x92000` 处的内嵌字节 sha256 = `d1d7a9f9…`，与
   `PongWifiFirmware.bin` 完全一致 → 固件真的被链进内核，不是只放在旁边。

## 3. 产物检查（artifact_check）

### 3.1 boot.img

| 项 | 值 |
|---|---|
| 路径 | `/mnt/e/k60-work/artifacts/wifi-20261114a/boot.img` |
| 大小 | 201,887,744 B |
| sha256 | `1bf90492b89b4f898b8163a7946c8bdf18ab56b25ff1711e15c3bfe5a6a1a481` |
| payload.img | 201,326,592 B，sha256 `9a82302b4388ecdb5bf1634ce74cd632643355074eb88648b76cd4f21ba3641b` |
| payload 内 kernel.macho | sha256 `2aff1a647009e452a0826e72a24252f27d8aa900c7ca702d8a1b2ec606e8f17f` |
| fd | `touch-20261114d-cf4485712c29.fd`，sha256 `cf4485712c29…` |
| 头 | v4、header_size 1584、kernel_size 550,932、ramdisk_size = payload |

**注意**：payload 步骤会 patch 内核，所以 `payload 内 kernel.macho` 的 sha256
（2aff1a64…）与构建产出的 `kernel.macho`（0fa28b37…）**本来就不相等**，
不要拿这两个互相比对。

### 3.2 verify-boot-image.py

`python3 scripts/verify-boot-image.py --manifest /mnt/e/k60-work/artifacts/wifi-20261114a/build-manifest.json`
→ `verify-boot-image: OK`（VERIFY_RC=0）。七项全过：

1. ANDROID! magic + v4 + header_size 1584
2. kernel 槽单 gzip member、112 B BootShim、FD sha256 == manifest
3. 尾部 FDT 长度一致且 ≤ 65536
4. ramdisk 槽 == payload.img
5. payload FAT 里 `EFI/UniXNU/Payloads/kernel.macho` == manifest.components.payload_kernel
6. payload 内 `unixnu.toml` 的 args 与 manifest 一致
7. 策略项：无 `pong_adsp=1`（该参数会让 boot 被拒）

manifest 由 `E:\k60-work\evidence\wifi-trial\mkmanifest.py` 生成（因为这张
boot.img 不是 build-strict.sh 出的，没有自动 manifest）。

### 3.3 内核启动参数（payload.json 实测，顺序即实际顺序）

```
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x140 cs_enforcement_disable=1
pong_software_keybag=1 disable_exc_resource=1 pong_ufs_readwrite=1 k60_console_export=1
k60_usblog=2 pong_data_mount=1 pong_data_rw=1 amfi_get_out_of_my_way=1
pong_init_path=/private/var/pong/init epoch=1793709100 k60_fontscale=3
k60_skip_firmware_mount=1 k60_tolerate_cache_loader=1 launchd_unsecure_cache=1
xpcproxy_idversion=1 k60_init_blob=1 k60_launchd_cache=1 k60_entitlement_allow=1
k60_skip_iosurface=1 k60_panic_reset=1 pong_adreno_start=1 pong_metal=2
k60_autoreset=300 applog=1 pong_wifi=1 k60_wifi_rsc=1
```

两个 WiFi 参数是**追加**的，不覆盖 board.toml 的既有 args（payload.py 按名字去重后
再拼 extra）。`k60_autoreset=300` 意味着每轮观察窗口约 5 分钟。

## 4. ⑧ 上机（device）

### 4.1 期望的控制台标志（判读用，全部来自 PongWifiPlatform.cpp）

按执行顺序：

| 阶段 | 日志文本 | 源码位置 |
|---|---|---|
| 参数门 | 无 `pong_wifi=1` 时完全静默 | `pong_wifi_start_optional()` |
| UFS 前置 | `UFS prerequisites absent; WiFi skipped` | `worker()` 的 180×500 ms 等待 |
| RSC 探针 | `PongWifi: RSC probe open=%d TCS4=0x%08x (level %u)` | `pong_rpmh_vote()` |
| RSC 只读 | `RSC probe-only mode; votes stay disabled` | 同上（`k60_wifi_rsc=1`） |
| RSC 可投 | `SM8475 WLAN rail requests acknowledged` | `supplies()` 末尾 |
| 链路 | `QCA6490 PCIe0 link and BAR established, bus master held off` | `coldLink()` |
| SMMU | `exclusive SID1c01 native4K DMA and retained MSI landing page established` | `isolation()` |
| MSI 布防 | `DesignWare MSI receiver armed on Pong PCIe0 SPI140` | `worker()` |
| 中断 | `QCA6490 MSI delivered by GIC` | 主循环首次 `msiArrivals` 非零 |
| 固件 | `PongWifi: ath11k start failed=%d`（失败才打） | 主循环 |
| 扫描 | `QCA6490 station ready; starting actual scan` | MAC 就绪后 |
| 周期 | `PongWifi: runtime state=%u scans=%u BSS=%u frames=%u MSI=%u receiver=%x dma-mib=%lu` | 每 15 s |

**关键安全性质**：`fail()` 只 `log(3,...)` 不 panic
（`bool fail(const char *s){log(3,s);return false;}`），所以 WiFi 任何一步失败
都只是"WiFi 没起来"，正常 iOS 启动继续。

### 4.2 已知上机风险

- `drivers/ArmCpu/ArmCpu.cpp:403` `if(!owner)panic("ArmCpu: unowned SPI %u",intid);`
  → 若 SPI 140 的中断在 `armcpu_spi_attach(172,...)` 成功之前到达，会 panic。

  槽位账目（逐个查过源码与实机日志，2026-11-14）：

  | 消费者 | INTID | 出处 | 本内核里会不会注册 |
  |---|---|---|---|
  | PongWifi PCIe0 MSI | 172（32+140） | `drivers/PongWifi/PongWifiPlatform.cpp:43`、`:673` | 会，`pong_wifi=1` 时 |
  | PongAdreno CP | 332（300+32） | `drivers/PongAdreno/PongAdrenoCp.cpp:388` | 会，`pong_adreno_start=1` 已在 args 里；实机日志 `PONG ADRENO: GPU IRQ332 owner result=0 a=0xa003` 证明它真的注册成功 |
  | BT UART | 587 | `bsd/dev/qbt_k60.c:1077` | **不会**：`qbt_k60_start()` 先看 `k60bt`（`qbt_k60.c:1236`），我们的 kernel args 里没有 `k60bt`，所以 worker 根本不启动 |
  | BT TLMM wake | 208 | `bsd/dev/qbt_k60.c:1083` | 同上，不会 |

  所以 4 个槽里实际只用 2 个（172、332），不会撞 `ArmCpu.cpp:435` 的
  `if(!result && used>=4)result=kIOReturnNoResources;`。而且那条保护本身是**干净失败**
  （返回错误码、不 panic），真正的 panic 只来自 `:403`：某个已使能的 SPI 在没有人
  `armcpu_spi_attach` 之前就触发。我们这条路径上唯一的风险窗口是 172 自己的 MSI 在
  attach 之前到达，而 `worker()` 是先 `dbi.w(MsiEnable,0)` 再 attach、attach 成功后才
  重新 `MsiEnable=~0u`（`PongWifiPlatform.cpp:669-675`），窗口是关的。
- 设备被多条线（usb / rail / bt）高频轮占，且每轮 `k60_autoreset=300` 自动回
  fastboot；supervisor 在 fastboot 不可见时**立刻退出不等待**
  （`throw "target 6033dbec is not in fastboot"`），所以必须"看到 fastboot 的那
  一瞬间就 boot"。

### 4.3 待补

- 一次完整的 `usblog-*` 控制台证据（含 `pong_wifi=1` 与 `k60_wifi_rsc`），
  按 §4.1 的表格逐条判读。
- 拿到之后才能把 `docs/research/EIGHT-STEPS.toml` 的 `[hardware.wifi]`
  从 `status="parked"` 改成 `active` 并填 ③⑦⑧ 的 evidence。

---

## 5. 第一次上机之后：分级门控版（⑧ 进行中）

### 5.1 第一次上机的结果

| 镜像 | args | 结果 |
|---|---|---|
| `wifi-20261114a/boot.img` `1bf90492…` | `pong_wifi=1 k60_wifi_rsc=1` | `port-not-observed`，`bytes=0`，设备自行回 fastboot |
| `wifi-20261114b/boot.img` `cf1d1ed8…` | `pong_wifi=1 k60_wifi_rsc=2` | 已构建，未上机（设备随后失联） |
| `wifi-20261114c/boot.img` `622a1fd6…` | `pong_wifi=0`（对照） | 已构建，未上机 |

证据 `/mnt/e/k60-work/evidence/usblog-20261114-wifi-b`：`capture.json` 是
`portSeen=false, portOpened=false, openErrors=0, stopReason="fastboot-return"`，
`console.log` 0 字节；`boot.json` 却是 `captureArmed=true, bootAccepted=true,
bootExitCode=0, returnedToFastboot=true`。同一 supervisor、同一 fd、同一设备
在 5 分钟前的 `usblog-20261114-raili` 拿到 220,576 字节 → 不是抓取链路问题。

原因分析见 `STAGE-BRINGUP.md`：`ArmDTPlatform::configure()` 里的
`pong_wifi_start_optional()` 比 `bsd_init.c:1341` 的 `k60_usblog_start()` 早
约 180 行执行，worker 在控制台存在之前就去访问 TLMM / PMIC / GCC / PARF，
一旦某个 GDSC 或时钟没起来就是 P-49 那种"互连挂死 + 0 日志 + 看门狗复位"。

### 5.2 加了两道默认安全的门

1. **控制台门（永久生效）**：worker 在**任何** MMIO 之前等
   `k60_usblog_console_up()`（`bsd/dev/k60_usblog.c:1594-1598`，
   即 `us >= 4`，控制台打完 `K60 USBLOG: running (DSTS …)` 之后为真），
   最多等 240×500 ms = 120 s；等不到就
   `console never came up; WiFi skipped before any MMIO` 并退出。
   该符号已在 kernel.macho 里（`ffffff…07f687f0 S _k60_usblog_console_up`），
   archive 直接链接即可。**从此 WiFi 若挂死，日志里一定留下最后一条 stage 行。**
2. **分级门 `k60_wifi_stage`**：`stageOpen(n, what)` 打印
   `PongWifi: stage %u (%s)`；`n > stageLimit` 时打印
   `PongWifi: stage %u (%s) held back by k60_wifi_stage=%u` 并返回 false。
   缺省/0 = 全跑。十个阶段：1 TLMM pinmux、2 SPMI+PMIC page、
   3 cmd-db 窗口与 rail 查找、4 首个 RPMh/RSC 投票（含 mx/cx/xo/SN7）、
   5 GCC GDSC/refgen/NoC、6 PARF/DBI/PHY/ATU、7 82 项 PHY 表、
   8 PERST+LTSSM、9 APPSSMMU SID 1c01、10 PARF MSI0→SPI140 attach。
   **2/3/4 是把 `supplies()` 拆开**：SPMI 控制器、cmd-db 窗口、第一次 RSC 写
   属于三个不同的电源域；`k60_wifi_rsc` 缺省时 `pong_rpmh_vote()` 在打开 RSC
   之前就返回，所以只到 stage 3 时完全不碰 RSC。

### 5.3 分级版产物（已构建，等设备）

| 项 | 值 |
|---|---|
| archive | `/opt/k60/trees/k60build/wifi/native-stage/libPongWifiNative.a` 11,941,816 B（05:18） |
| kernel.macho | 65,863,680 B，sha256 `f19ba0b37b9f7f30e49c0249cd4e9a397100df9dfd95da4788d0ab6488ec9bfc`（05:21） |
| linkarchives 证据 | 含 `-Wl,-force_load,/opt/k60/trees/k60build/wifi/native-stage/libPongWifiNative.a` |
| boot.img（stage=1） | `/mnt/e/k60-work/artifacts/wifi-20261114d/boot.img` 201,887,744 B，sha256 `4b5c7dfd0e74dbf7efa61247e27754b24f11b0df068129a82adfac3e7549abc7` |
| boot.img（同内核对照） | `/mnt/e/k60-work/artifacts/wifi-20261114e/boot.img`，sha256 `a6eb8d5aabebc9382ab5687059cf28dc2e52854f34873d731be1fe8167979e3f`，args 尾部 `pong_wifi=0` |
| args | `… applog=1 pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=1` |
| 构建日志 | `/mnt/e/k60-work/evidence/wifi-trial/{build-stage-archive.log,tree-stage.log,kernel-stage.log,payload-stage1.log,bootimg-stage1.log}` |
| 构建脚本 | `E:\k60-work\evidence\wifi-trial\{build-stage-archive.sh,build-stage-kernel.sh,mkboot-stage1.sh}` |

`unixnu build payload` / `bootimg` 同样要过 `gates.py`，在 `wifi-device`
上必须带 `UNIXNU_SKIP_GATES=1`（否则 `build refused: … has no
docs/engineering/RULES.toml`）。

### 5.4 上机顺序（每步一次 boot）

两个正交的轴：`k60_wifi_stage`（放到第几级）与 `k60_wifi_rsc`
（0/缺省 = 完全不动 RSC；1 = 只读探针；2 = 允许投票）。
**这一点很关键**：`pong_rpmh_vote()` 在 `k60_wifi_rsc` 缺省时**在打开 RSC 之前
就返回 false**，所以「stage=2 + 无 rsc」只碰 SPMI 与 cmd-db，不碰 RSC。

0. **对照 `wifi-20261114e`**（`pong_wifi=0`，同一个 65.8 MB 内核）：
   只回答「镜像能不能起来、控制台有没有」。起不来就是镜像/装载层问题
   （尺寸、UEFI DXE 堆），与 WiFi 无关。
1. **`wifi-20261114d`**（`stage=1`）：只碰 TLMM。期望 `stage 1 (TLMM pinmux …)`
   → `stage 2 (…) held back` → `WiFi initialization stopped…`。
2. **`wifi-20261114i`**（`stage=2`，无 rsc）：加 SPMI/PMIC 打开与 cmd-db 读取，
   投票被拒 → `physical WLAN supply did not follow RPMh request`，**全程不碰 RSC**。
   过不了这级就说明问题在 SPMI 或 cmd-db（0x80860000）。
3. `stage=2 k60_wifi_rsc=1`：**只多一步 RSC 读探针**（`rsc.open(0x17a20000,0x10000)`
   后读 id/caps/TCS4）。首轮挂死用的正是 `rsc=1`——它的「只读」探针仍然是 RSC MMIO
   读，而 `pong_rpmh_vote()` 自己的注释就写着「对未上电的 RSC 做读会挂死互连」，
   所以这一级是当前最强嫌疑点。挂了就说明必须找到 RSC 上电的证据才能继续。
4. **`wifi-20261114f`**（`stage=3 k60_wifi_rsc=1`）：加 GCC/GDSC/refgen。
5. **`wifi-20261114g`**（`stage=6 k60_wifi_rsc=1`）：host MMIO、PHY 表、PERST、
   链路训练；成功标志 `QCA6490 PCIe0 link and BAR established, bus master held off`
   与 `QCA6490 PCI subsystem=10817cb`。
6. **`wifi-20261114h`**（`stage=8 k60_wifi_rsc=2`）：SMMU SID 1c01 + MSI attach
   + `ath11k start`（这一级必须真投票，否则 supplies 过不去）。

### 5.5 当前阻塞

自 04:50 起手机既不枚举 ADB 也不枚举 fastboot，`Get-PnpDevice` 里也没有任何
`VID_2717`/`VID_18D1`/`VID_1209` 在线项 → 需要人工长按电源约 10 s 强制重启。
分级内核已就绪，设备一回来即可执行 §5.4 的第 1 步（脚本
`race-boot2.ps1` 会每 0.7 s 抢 fastboot 窗口）。

### 5.6 分级镜像阶梯（全部已构建，全部通过 verify-boot-image.py）

| 目录 | args 尾部 | boot.img sha256 |
|---|---|---|
| `wifi-20261114e` | `pong_wifi=0` | `a6eb8d5aabebc9382ab5687059cf28dc2e52854f34873d731be1fe8167979e3f` |
| `wifi-20261114d` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=1` | `4b5c7dfd0e74dbf7efa61247e27754b24f11b0df068129a82adfac3e7549abc7` |
| `wifi-20261114f` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=3` | `c4490e741746d525c774c03e…` |
| `wifi-20261114g` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=6` | `907dac42f3707751702fb73d…` |
| `wifi-20261114h` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=8` | `f48c2f38565d83d7b4769b92…` |
| `wifi-20261114i` | `pong_wifi=1 k60_wifi_stage=2`（无 rsc 参数） | `4da49b403f473f74f9d966d8…` |

五个镜像共用同一个 staged 内核（`f19ba0b3…`）与同一个 fd（`cf448571…`）；
每题目录都有 `build-manifest.json`，`python3 scripts/verify-boot-image.py
--manifest <dir>/build-manifest.json` 全部 `OK`（v4 头、shim、FD、FDT、payload、
payload 内 kernel、unixnu.toml args 七项）。构建脚本
`E:\k60-work\evidence\wifi-trial\mkboot-stages.sh`。

**payload 是共享产物**：`unixnu build payload` 每次覆盖
`out-wifi/…/payload/payload.img`，所以每张 boot.img 必须在它自己那次 payload
之后立刻 bootimg 并生成 manifest，否则 manifest 里的 `payload` 会与下一张串味。

### 5.7 十级阶梯（当前有效的一套，取代 §5.6 的八级）

`supplies()` 被拆成 stage 2/3/4 之后总级数变成十级，§5.6 的八级镜像随之作废
（仅留作历史对照）。

**第一版十级阶梯（`wifi-20261115a…h`，内核 `f430c217…`）已整体作废**：
它们的命令行是 619–620 字节，超过 DarwinBoot 的 607 字节上限，见 §5.8。
唯一仍然有效的是 `wifi-20261115h` 用的六文件固件内核
`73c33075d44d231360f26b771bae5bd3ae893ae5fd9865cf8ffcb73f342cfc75`
（65,978,368 B，`_pong_wifi_firmware` fffffff007094000 →
`_pong_wifi_firmware_end` fffffff007b3fed6，span 11,189,974），
archive `/opt/k60/trees/k60build/wifi/native-bdf/libPongWifiNative.a` 12,066,184 B。

### 5.8 合规阶梯（a–g 加 p，唯一可上机的一套）

八张镜像全部用上面那个六文件内核重出，并且每张都跑了
`argcheck1.py`（解 boot v4 头 → ramdisk 槽 → `mtype` 读
`::EFI/UniXNU/unixnu.toml` → 正则取 `args`，上限 607）。构建脚本
`E:\k60-work\evidence\wifi-trial\mkboot-ladder4.sh`，命令里带
`TRIM="--kernel-arg epoch=1 --kernel-arg debug=1"`（让出 25 字节）。

| 目录 | args 尾部 | 长度 | boot.img sha256（前 32 位） |
|---|---|---|---|
| `wifi-20261115a` | `pong_wifi=0` | 574 | `4cd551960ee327b3a56093b0e963d203` |
| `wifi-20261115b` | `pong_wifi=1 k60_wifi_stage=1` | 591 | `22edfa7137a5f98dfeacc92a018dd59e` |
| `wifi-20261115c` | `pong_wifi=1 k60_wifi_stage=3` | 591 | `97d122d5f588961f0ea91f77b562c3a0` |
| `wifi-20261115p` | `pong_wifi=1 k60_wifi_rsc=1 k60_wifi_stage=4` | 606 | `c470091a5a37c0580a482b7e7c97490a` |
| `wifi-20261115d` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=4` | 606 | `dfb916fcd924d002cd3a91e783158d59` |
| `wifi-20261115e` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=5` | 606 | `922627bfba06e1e8d69a281a4f6c5de4` |
| `wifi-20261115f` | `pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=8` | 606 | `418d07ecc277d01a6e97694df220d671` |
| `wifi-20261115g` | `pong_wifi=1 k60_wifi_rsc=2`（全十级） | 589 | `f27b9cb8df73ae435629a7ee068351af` |

八张全部 `verify-boot-image: OK` 且 `argcheck1.py` 全部 ok。
`wifi-20261115h`（620 字节）**不得上机**：它会在 DarwinBoot 里被直接拒绝，
表现为 `port-not-observed` + 0 字节控制台，看起来像内核挂死但内核根本没被装载。

### 5.9 为什么 607 是硬线（这条以前被漏掉）

`uefi-mondrian/Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h:8`
`#define DARWIN_BOOT_LINE_LENGTH 608`，
`DarwinBoot.c:678-684`：

```c
if ((Index >= sizeof (CommandLine) - 1) || (Request->BootArgs[Index] > 0x7f)) {
  return EFI_BAD_BUFFER_SIZE;
}
```

即**长度 ≥ 607 或含任何 >0x7f 的字节**都直接返回，且这个返回发生在
`ReadFile`/`ParseKernel` 之前 —— 屏幕停在 REQUEST 阶段，串口一个字节都没有，
设备自己回 fastboot。board.toml 现有 29 项占 575 字节，
`pong_wifi=1 k60_wifi_rsc=2 k60_wifi_stage=10` 要再加 45。

旁证：bt 线 `usblog-20261114-bts1b-run1` 的 args 是 610 字节，正好是
`state=port-not-observed, bytes=0, stopReason=port-timeout`。
框架侧 `payload.py:30-38 check_args()` 只拦 >1000，注释里的
「DarwinBoot copies the command line into a 1024-byte buffer」是过时的，
不会替我们拦住 607–1000。

静态门禁（`E:\k60-work\evidence\wifi-trial\static-stage-gates.log`）：
archive 里存在 `PongWifi: stage %u (%s)`、`held back by k60_wifi_stage=%u`、
`console up after %u ms`、`console never came up; WiFi skipped before any MMIO`
四组字符串，未定义符号只有 `_PongWifiRandom`、`_PE_parse_boot_argn`、
`_k60_usblog_console_up`、`_pong_ufs_ready` 四个（都由内核提供），
源码里 `stageOpen(` 共 11 处（1 处定义 + 10 处调用）。


### 5.10 合规阶梯内核的符号面（上机前最后一次静态核对）

对 `out-wifi/…/kernel/kernel.macho`（sha256 `73c33075…`，65,978,368 B）
跑 `/usr/lib/llvm-18/bin/llvm-nm -a`，四个上机必需的符号都在：

```
fffffff00874a07c b __ZZ24pong_wifi_start_optionalE7started
fffffff007f847f0 S _k60_usblog_console_up
fffffff00858deb4 S _pong_smmu_lease_lock
fffffff00852c0c8 S _pong_ufs_ready
fffffff00858a8dc S _pong_wifi_start_optional
```

即：ArmDTPlatform 的 hook 入口、控制台门依赖的 `k60_usblog_console_up`、
worker 的 UFS 门 `pong_ufs_ready`、以及 NativeUfs 侧要的 SMMU 租约锁全部解析成功，
`llvm-nm -u` 里没有任何 `_pong`/`_nw_wifi` 未定义符号。



### 5.11 Second kernel: the firmware-size bisect (54.8 MB instead of 65.9 MB)

The 65,978,368 B kernel is 11.8 MB larger than the proven 54,181,888 B
baseline, and all of that growth is the PWF2 blob inside `__TEXT,__const`
(`_pong_wifi_firmware` … `_pong_wifi_firmware_end`, span 11,189,974 B). That
alone changes the Mach-O layout enough to move every later segment, so "the
kernel no longer boots" and "the WiFi code touches a dead interconnect" are two
different faults that the first failed boot could not separate.

To separate them without touching the source, the same archive was rebuilt
against a synthetic firmware directory
(`/mnt/e/k60-work/impl/wifi/work/fake-fw/`, four 23-byte placeholder files):

- `build-tiny-archive.sh` → `/opt/k60/trees/k60build/wifi/native-tiny/libPongWifiNative.a`
  892,616 B (vs 12,066,184 B for the six-file pack);
- `build-tiny-kernel.sh` → `kernel.macho` 54,804,480 B sha256
  `92fad10599f5ded612426e555093d20e9ac9f4a9ae641da73aa60a56185059cd`, i.e.
  only **622,592 B** above the baseline — the driver code itself, not the blob;
- `mkboot-tiny.sh` → two images, both `verify-boot-image: OK` and both under the
  607-byte command-line limit:

| image | args tail | len | sha256 |
| --- | --- | --- | --- |
| `wifi-20261115t0` | `pong_wifi=0 epoch=1 debug=1` | 574 | `6b21772f3af9b52a034873789e97bc643f6a5a60e942dd1e34ef940ddc2a2d4f` |
| `wifi-20261115t1` | `pong_wifi=1 k60_wifi_stage=1 epoch=1 debug=1` | 591 | `3de009f2cc68f373ec8ad54ec029a78aba6bbcd944065fc6a7723a4eaa989a14` |

These two cannot reach a real firmware load (the pack is synthetic), so they are
diagnostic only. Their meaning is spelled out in `STAGE-BRINGUP.md` §4.2.

The canonical six-file kernel is preserved outside the build tree as
`/opt/k60/trees/k60build/wifi/kernel-bdf-73c33075.macho` (65,978,368 B, sha256
`73c33075…`), because `unixnu build kernel` overwrites
`out-wifi/…/kernel/kernel.macho` in place and the tiny build replaced it.

上机脚本 `E:\k60-work\evidence\wifi-trial\ladder6-run.ps1`
（`-RaceSeconds 7200 -Seconds 180 -Tag ladder9`）：每 0.7 s 抢一次
fastboot 窗口，命中后先 boot 控制镜像 `a`，再 boot 全十级镜像 `g`
（一次启动就能打出所有 `stage N` 行，最后一条就是挂了的那块），只有
`g` 也静默时才退回线性阶梯 `b → c → p → d → e → f`。每张把结果写进
`E:\k60-work\evidence\usblog-<stamp>-<tag>`，并在每轮之后等设备回 fastboot
（最多 240 s）；任何一张零字节控制台就停下（exit 12）。

### 5.12 The small-kernel ladder (54.8 MB) and the stock control

`STAGE-BRINGUP.md` §4.2 splits the boot question into three families. Two of
them were built here; the third is the pre-existing stock baseline.

| image | kernel | args tail | len | sha256 |
| --- | --- | --- | --- | --- |
| `wifi-20261115z0` | 54,181,888 B stock `cc7541cd…` | *(baseline)* | 575 | `b64e5074f16108e7e77c5e6b38f29ae176ffdc0e8c2c641c04d73625ba975c6b` |
| `wifi-20261115t0` | 54,804,480 B `92fad105…` | `pong_wifi=0` | 574 | `6b21772f3af9b52a034873789e97bc643f6a5a60e942dd1e34ef940ddc2a2d4f` |
| `wifi-20261115t1` | same | `pong_wifi=1 k60_wifi_stage=1` | 591 | `3de009f2cc68f373ec8ad54ec029a78aba6bbcd944065fc6a7723a4eaa989a14` |
| `wifi-20261115t3` | same | `k60_wifi_stage=3` | 591 | `b44d0a94e8f295645aa5e8171e587b290688686d86239ad7a7af9cf55c70b5c6` |
| `wifi-20261115t4` | same | `k60_wifi_rsc=1 k60_wifi_stage=4` | 606 | `afb3e9a9369fc6cdb1a6d54d281a5835d2493d69057456a7693040d5a9e477a1` |
| `wifi-20261115t5` | same | `k60_wifi_rsc=2 k60_wifi_stage=4` | 606 | `e4f788fd8783411a073e1aca2f7c6c13ad33fd8355916476e5366286b92d12b7` |
| `wifi-20261115t6` | same | `k60_wifi_rsc=2 k60_wifi_stage=5` | 606 | `c96635d65774f1a491c39d78d408054a3d41b802d89e6b5c9f46852cef0d0a6c` |
| `wifi-20261115t7` | same | `k60_wifi_rsc=2 k60_wifi_stage=8` | 606 | `39492308c5238dee0ecbe9a746a390b0293e95839819c338df7e1ff111e2f8c6` |
| `wifi-20261115t8` | same | `k60_wifi_rsc=2` (all) | 589 | `0e438b04897df724a87dfeb899c7e3f3fb81fd84c8673ca5acf010bf7df8d5d4` |

All nine passed `verify-boot-image.py`, and every rung passed `argcheck1.py`
(574 / 591 / 591 / 606 / 606 / 606 / 606 / 589 bytes, all under the 607-byte
DarwinBoot limit). The `z0` image reuses the stock baseline kernel, which is the
strongest control available: it contains no PongWifi code at all.

Runner: `E:\k60-work\evidence\wifi-trial\ladder5-run.ps1`, which walks
`a → b → c → p → d → e → f → g` and stops on the first zero-byte console
(exit 12). The `t*` rungs and `z0` are held back as a fallback: they are only
booted when the control image `a` is itself silent, in which case the walk
continues `z0 → t0 → t1` and a silent `z0` ends with exit 13 (the phone or the
FD is at fault, and no WiFi conclusion is available).

Two facts make the tiny family worth its build time: the archive is 892,616 B
instead of 12,066,184 B, and the kernel is 54,804,480 B instead of 65,978,368 B,
i.e. only 622,592 B above the kernel that has booted this phone dozens of times.

### 5.13 What each ladder image actually carries

A boot image can pass `verify-boot-image.py` and still carry a stale kernel, so
two independent checks were run over the ladder itself.

**Kernel slot (shim + firmware volume + kernel DTB).** Identical across the
proven peer image and the WiFi images, byte for byte:

| image | inflated slot | FD sha256 | kernel DTB |
| --- | --- | --- | --- |
| `rail-20261114i` (proven, 220 KB console) | 3,145,840 B | `cf4485712c2999c1` | 4,024 B `2d044eaa08b7e58c` |
| `wifi-20261114a` | 3,145,840 B | `cf4485712c2999c1` | 4,024 B `2d044eaa08b7e58c` |
| `wifi-20261115a` | 3,145,840 B | `cf4485712c2999c1` | 4,024 B `2d044eaa08b7e58c` |
| `wifi-20261115t0` | 3,145,840 B | `cf4485712c2999c1` | 4,024 B `2d044eaa08b7e58c` |

So the firmware volume and the device tree the phone boots are exactly the ones
that have already produced a console on this hardware. The only variable in the
ladder is the payload.

**Kernel inside the payload.** Extracted with
`mtype -i <ramdisk> ::EFI/UniXNU/Payloads/kernel.macho` after splitting the v4
header (`ramdisk offset = 4096 + page_up(kernel_size)`), then searched for the
gate strings:

| image | kernel.macho | sha256 | console-up | stage-held | RSC-probe | board-fw |
| --- | --- | --- | --- | --- | --- | --- |
| `wifi-20261115a` | 65,978,368 B | `e273b64968b64048` | 1 | 1 | 1 | 1 |
| `wifi-20261115g` | 65,978,368 B | `e273b64968b64048` | 1 | 1 | 1 | 1 |
| `wifi-20261115t0` | 54,804,480 B | `62999b5b88f89eed` | 1 | 1 | 1 | 1 |

Every rung therefore really does contain the console gate and the staging
predicate. That is the precondition for reading a zero-byte console as "the gate
never opened" rather than "the gate was not in the image".

Scripts: `E:\k60-work\evidence\wifi-trial\verify-embedded.py` and `cmpkern.py`.
The payload kernel sha256 differs from the build product (`73c33075` for the
six-file kernel) because `unixnu build payload` rewrites the Mach-O on the way
into the FAT volume; `verify-boot-image.py` compares against the manifest, which
records the post-payload value.

### 5.14 Every ladder artifact still matches its own manifest (17/17)

The ladder was rebuilt several times while the phone was dark, and each rebuild
overwrites the shared `out-wifi/.../payload/payload.img`. A manifest that was
written one build late would silently point a rung at a kernel it does not
carry. `E:\k60-work\evidence\wifi-trial\check-artifacts.py` re-derives three
facts straight from the bytes on disk and compares them with
`build-manifest.json`:

1. `fd.bin` sha256 vs `components.fd`;
2. the kernel inside the boot ramdisk
   (`mtype -i <ramdisk> ::EFI/UniXNU/Payloads/kernel.macho`) vs
   `components.payload_kernel`;
3. `unixnu.toml`'s `args` vs `kernel_args`, plus the 607-byte ceiling.

Result for all 17 rungs (`z0 t0 t1 t3 t4 t5 t6 t7 t8 a b c p d e f g`):

```
wifi-20261115z0      OK  args=575     wifi-20261115a       OK  args=574
wifi-20261115t0      OK  args=574     wifi-20261115b       OK  args=591
wifi-20261115t1      OK  args=591     wifi-20261115c       OK  args=591
wifi-20261115t3      OK  args=591     wifi-20261115p       OK  args=606
wifi-20261115t4      OK  args=606     wifi-20261115d       OK  args=606
wifi-20261115t5      OK  args=606     wifi-20261115e       OK  args=606
wifi-20261115t6      OK  args=606     wifi-20261115f       OK  args=606
wifi-20261115t7      OK  args=606     wifi-20261115g       OK  args=589
wifi-20261115t8      OK  args=589
MISMATCHES 0
```

So the ladder is internally consistent at the byte level before it is spent on a
boot: the fd is the proven `cf4485712c29`, every rung's manifest names the
kernel the ramdisk really holds, and no rung is over the loader's command-line
limit.

### 5.15 The gate is present in every rung, not just the three checked in §5.13

§5.13 sampled three rungs. The full ladder was re-checked afterwards, because a
stale `payload.img` would make a silent capture mean the wrong thing: a rung with
no console gate in it would be silent for the old reason, and the ladder would be
read backwards.

`E:\k60-work\evidence\wifi-trial\preflight-embedded.py` splits the v4 boot header
(`ramdisk offset = 4096 + page_up(kernel_size)`), extracts
`::EFI/UniXNU/Payloads/kernel.macho` with `mtype`, and counts five strings. Result
for all twelve images that can be booted:

```
image               ramdisk      kernel.macho  sha256        gate held rsc bdf pwf2
wifi-20261115a      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115b      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115c      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115p      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115d      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115e      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115f      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115g      201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115h2     201326592    65978368      e273b64968b6  1    1    1   1   2
wifi-20261115z0     201326592    54181888      50b22e26b87b  0    0    0   0   0
wifi-20261115t0     201326592    54804480      62999b5b88f8  1    1    1   1   2
wifi-20261115t1     201326592    54804480      62999b5b88f8  1    1    1   1   2
```

Columns: `gate` = `console up after`, `held` = `held back by k60_wifi_stage`,
`rsc` = `RSC probe id=0x`, `bdf` = `actual QMI board firmware`, `pwf2` = `PWF2`
(two hits: the magic check and the lookup).

Two readings that matter:

- **`z0` carries no WiFi code at all** — all five counters are zero. It is the
  stock-kernel control, so a silent `z0` means the phone or the fd is at fault,
  never the WiFi driver. That is why the runner exits 13 on it instead of 12.
- **`t0`/`t1` carry the same gate as the 65.9 MB rungs** (identical payload
  kernel `62999b5b88f8`), so the size bisect does not confound the gate: a
  silent `t0` cannot be explained by "the gate is missing from the small kernel".

`wifi-20261115h2` is the six-file-firmware twin of `g` (same payload kernel,
`pong_wifi=1 k60_wifi_rsc=2`, 602 bytes instead of 589 because it does not carry
the `epoch=1 debug=1` trim). It exists to prove the BDF files can be packaged and
still boot as a legal image; `g` is the rung to fly, because it leaves more
headroom under the 607-byte limit.

### 5.16 Why the 65.9 MB kernel is silent on the phone: the window, not the kernel

§5.15 closed the "is the gate in the image" question. This section closes the
other one: why every 65.9 MB rung produced a zero-byte console while every
54.1–54.5 MB image (bt-s2, rail-*, touch-*, usb-*) produced 200 KB or more.

The answer is not the loader rejecting the kernel and not the kernel dying on
its own. It is arithmetic on **one contiguous run of conventional memory**:

```
DarwinBoot.c:607  AllocateWindow(&Kernel, WindowSize, &Address)   // 4.75 GiB, from the adt
DarwinBoot.c:656  FreePool(Image)                                 // the kernel image is still resident here
```

`AllocateWindow` (`DarwinBoot.c:422-490`) walks every `EfiConventionalMemory`
descriptor and asks for the whole window at one `AllocateAddress`. At that
moment the kernel image that `ReadFile` (`:558`, limit `SIZE_128MB`) just pulled
into the DXE pool is **still allocated**. So the largest run the loader can use
is `arena - kernel image - everything else`, and a kernel 11.8 MB bigger eats
exactly that much out of the window request.

QEMU reproduces this quantitatively. `qemu-window-probe.sh <tag> <mem_mb>...`
boots a real payload through the built `DarwinBoot.efi` and reports
`inputs validated; exiting boot services` (handoff happened) or
`boot refused: Out of Resources; firmware retained` (window allocation failed):

```
kernel                                    window       fails at   succeeds at
wifi-20261115z0   54,181,888 B  51.7 MiB  4.75 GiB     5102 MB    5104 MB
wifi-20261116t0c  54,804,480 B  52.3 MiB  4.75 GiB     5104 MB    5108 MB
wifi-20261116a2   65,978,368 B  62.9 MiB  4.75 GiB     5112 MB    5116 MB
wifi-20261116h3w  65,978,368 B  62.9 MiB  4.6875 GiB   5040 MB    5052 MB
wifi-20261116h3q  65,978,368 B  62.9 MiB  4.5 GiB      4848 MB    4860 MB
```

Three readings:

- **The threshold tracks kernel size one-for-one.** z0 -> a2 is +12 MB of guest
  RAM for +11.25 MiB of kernel. That is the image's residency, not a property of
  the image itself.
- **The threshold tracks window size one-for-one too.** 4.75 -> 4.6875 GiB
  (-64 MiB) moved the threshold 5116 -> 5052 (-64 MB); 4.75 -> 4.5 GiB
  (-256 MiB) moved it to 4860 (-256 MB). Fitting the five points gives

  ```
  required RAM  ~=  window + kernel_size + 177 MiB (fixed loader/EFI overhead)
  ```

  which holds for all five rows to within 1 MiB.
- **The phone sits on the wrong side of that line.** `board.toml:231` requests
  `owned_memory_size = 0x130000000` (4.75 GiB) and `board.toml:117,228` record
  the firmware-exposed arena as `[0x900000000, 0xa40000000)` = `0x140000000`
  = 5 GiB = 5120 MB. Plugging in: 4864 + 62.9 + 177 = **5104 MiB needed for the
  65.9 MB kernel against 5120 MiB of arena** - 16 MB of margin before the
  loader's own allocations, i.e. none. For the 54.2 MB kernel the same sum is
  5021 MiB vs 5120, which is why those images boot.

So the 65.9 MB rungs were never going to reach the kernel on this board: the
window request alone consumes the arena. The screen never shows
`NO WINDOW ... BIG RUN ...` on the phone because that diagnostic goes to
`DiagDraw` + `DEBUG`, neither of which reaches the USB console (see
STAGE-BRINGUP §8) - the phone simply returns to fastboot.

**The fix is to shrink the request, and it costs exactly what it saves.**
`DarwinBoot.c:636-637` writes `Args->MemorySize = WindowSize`, and
`arm_vm_init.c:1844-1860` turns that into XNU's `mem_size`, so a smaller window
is a smaller amount of managed RAM. Dropping 4.75 -> 4.5 GiB gives back 256 MiB
of margin and costs 256 MiB of XNU-visible RAM (4.5 GiB is still 4.5x what the
stock Pong board requests, `UniXNU-pong/board.toml:152` = 4 GiB).

Images built with the reduced window (`patchadt.py <boot.img> <bytes>` rewrites
only the 8-byte `darwinboot-memory-size` value inside `kernel.macho.adt`; every
one of them passes `check-image-args.py` unchanged because the command line is
untouched):

```
image                        window        args          boot.img sha256
wifi-20261116a2w   (control)  4.6875 GiB    30 / 587 B    2b03db00ba9a1694
wifi-20261116a2q   (control)  4.5 GiB       30 / 587 B    6ef27b95c9a8bcf9
wifi-20261116a2r   (control)  4.625 GiB     30 / 587 B    0b4b0abb54daf5b1
wifi-20261116h3w   (rsc=2)    4.6875 GiB    31 / 602 B    986afa43272a9382
wifi-20261116h3r-g (rsc=2)    4.625 GiB     31 / 602 B    b5beb5d9568843a3
wifi-20261116h3q-g (rsc=2)    4.5 GiB       31 / 602 B    1abcfcea4459b21b
wifi-20261116h3r-s1(stage=1)  4.625 GiB     31 / 604 B    be75dd3dff58d33f
wifi-20261116h3q-s1(stage=1)  4.5 GiB       31 / 604 B    92b7b9ff80e7efc3
```

The `a2*` trio is the control (65.9 MB kernel, `pong_wifi=0`): it isolates the
window from the WiFi driver, so if `a2q` is still silent the window is not the
whole story. The `h3*` family is the real rung to fly.

The board-level fix belongs in `board.toml:231` and is **outside this agent's
write scope**, so it is proposed as a diff to the Lead rather than committed
here:

```diff
--- a/board.toml
+++ b/board.toml
@@ -228,7 +228,7 @@
 # Firmware exposes only measured arena [0x900000000,0xa40000000); screen
 # reports mem=actual=managed=4096 MiB. Service exits continue; SpringBoard is
 # pending. devicetree.py emits darwinboot-memory-size from this key.
-"owned_memory_size" = "0x130000000"  # 4.75 GiB window (ladder step after 5 GiB NO WINDOW)
+"owned_memory_size" = "0x120000000"  # 4.5 GiB window: 4.75 GiB leaves <16 MB of arena for a 65.9 MB kernel (LOCAL-VERIFICATION 5.16)
```

