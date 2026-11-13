# WiFi 接线：需要 Lead 合并的改动

> 2026-11-14 · 由 wifi agent 产出
> 本文件列的每一处都在 wifi agent 写作用域之外（`board.toml` / defconfig 选择 / 构建环境）。
> wifi agent 已在 `/opt/k60/trees/wifi-device` 与 `out-wifi` 上**实测验证**这套改动能让
> `libPongWifiNative.a` 真正链进内核。

---

## 1. `board.toml` —— patch_series 加 WiFi 系列

**文件**：`board.toml`（device 仓根）
**行**：20

```diff
--- a/board.toml
+++ b/board.toml
@@ -18,7 +18,7 @@
 # The K60 series still carries every patch; the shared layers have empty series for now.
-patch_series = ["device:patches/xnu/series"]
+patch_series = ["device:patches/xnu/series", "device:patches/wifi/series"]
 archives = ["component:ArmDTPlatform", "component:ArmCpu", "component:PongUfs"]
 driver_records = "DEVELOPMENT_ARM64_PONG"
```

**为什么必须**：`UniXNU/scripts/unixnu/patches.py:12` 的 `plan()` 只遍历
`ctx.board['kernel']['patch_series']`。当前全仓**没有任何东西**引用
`patches/wifi/series` → 10 个补丁永不应用。

**验证**：`/opt/k60/trees/wifi-device` 里按此顺序 `git apply` 0001–0010，
10 个全部干净应用，零冲突。

**顺序**：`patches/wifi` 必须在 `patches/xnu` **之后**（0004 改
`drivers/NativeUfs/PongUfsTransport.cpp`，0005 改 `drivers/ArmDTPlatform/ArmDTPlatform.cpp`，
这些文件的当前形态由 `patches/xnu` 决定）。

---

## 2. defconfig —— 切到 `mondrian_wifi_defconfig`

**文件**：`board.toml` 第 17 行，或 `unixnu defconfig mondrian_wifi`

```diff
--- a/board.toml
+++ b/board.toml
@@ -14,7 +14,7 @@
 [kernel]
-defconfig = "mondrian_defconfig"
+defconfig = "mondrian_wifi_defconfig"
 config_fragments = ["arch:configs/common.config", "soc:configs/sm8475.config", "os:configs/ipados.config"]
```

**为什么必须**：`configs/mondrian_wifi_defconfig` = 现 `mondrian_defconfig` 全量
+ 末尾一行 `CONFIG_XNU_PONG_WIFI=y`。`UniXNU/scripts/unixnu/kernel.py:19` 的
`xnu_env()` 把 `CONFIG_XNU_*` 转成环境变量 `XNU_*=1`，这是
`build-xnu-4k-baseline.sh:922` 的 `if [ "${XNU_PONG_WIFI:-0}" = 1 ]` 唯一入口。

**副作用（重要）**：切 defconfig 会让 work 目录从
`.../mondrian/ipados-16.6.1-20G81/mondrian` 变成 `.../mondrian_wifi`
（`config.py:149-166`：目录名 = config_name 去掉 `_defconfig`）。
**代价是丢掉 24 GB 的增量编译缓存，下一次构建是全量。**

**替代方案（wifi agent 实测用的）**：不切 defconfig，直接往
`out-*/…/mondrian/.config` 追加 `CONFIG_XNU_PONG_WIFI=y`。等价、保缓存，
但不是"仓库唯一真源"，不建议长期用。

---

## 3. 构建环境 —— 显式传 archive 路径

```bash
export XNU_PONG_WIFI=1
export XNU_PONG_WIFI_ARCHIVE=/opt/k60/trees/k60build/wifi/native-real/libPongWifiNative.a
```

**为什么必须**：`build-xnu-4k-baseline.sh:923`（PLATFORM_ARCHIVES 分支里是 :1144）的默认值是
`${XNU_PONG_WIFI_ARCHIVE:-$ROOT/build/pong-wifi/libPongWifiNative.a}`，
而 `build-k60-wifi-native.py` 的默认输出是 `<tree>/build/k60-wifi/`。
两者不一致 → 不显式传就会 `test -f` 失败。

**`XNU_PONG_WIFI=1` 是否需要手工 export**：如果走第 2 条（切 defconfig），
`xnu_env()` 会自动设，**不用手工 export**。只有走"追加 .config"的替代方案时
才需要手工 export（因为 `kernel.py` 的 `xnu_env` 也会读它，但仍需保证
`.config` 里有那一行）。

---

## 4. archive 的构建方式（前置产物）

`libPongWifiNative.a` 不是 `unixnu build kernel` 自动产的，必须先单独跑两步：

```bash
# 步骤 1：ath11k
export PONG_SHENG_ROOT=/mnt/e/k60-work/impl/wifi/work/src/UniXNU-sheng
python3 scripts/build-k60-ath11k.py \
  --linux /home/emilelu/wifi-inputs/linux \
  --output-dir /opt/k60/trees/k60build/wifi/ath11k

# 步骤 2：wifi-native
T=/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree
export UNIXNU_SDKROOT=$T/.cache/fakeroot
export UNIXNU_SDK_VERSION=17.0
export PATH="/opt/unixnu-linux/CommandLineTools/usr/bin:/opt/unixnu-linux/llvm/bin:/usr/lib/llvm-18/bin:$PATH"
python3 scripts/build-k60-wifi-native.py \
  --tree $T \
  --ath11k /opt/k60/trees/k60build/wifi/ath11k/libPongAth11k.a \
  --firmware /mnt/e/k60-work/firmware/qca6490-wifi \
  --output-dir /opt/k60/trees/k60build/wifi/native-real
```

**坑（踩过两次）**：

1. `--tree` 必须是 `out-*/…/mondrian/tree`，**不是 repo 根**。传 repo 根会
   `fatal error: 'IOKit/IOLib.h' file not found`（builder 用 `a.tree/'.cache/fakeroot/...'`
   拼 Kernel.framework 头路径）。
2. `--firmware` 必须是**干净四文件目录**（`amss.bin` / `amss20.bin` / `m3.bin` /
   `regdb.bin`）。它会把目录里**所有**文件打进 PWF2 包；指向原始 222 文件目录
   会得到 13 MB / 10 文件的包。

产物：`libPongWifiNative.a` 11,939,808 B、`PongWifiFirmware.bin` 11,067,094 B。

---

## 5. 门禁（`gates.py`）—— 正式构建必须解决的阻塞

`UniXNU/scripts/unixnu/gates.py` 的 `GATED = ('build','bootimg','vendor_boot','ipsw','release')`，
`build` 属门禁命令。它要求：

1. `ctx.device/scripts/check-rules.py` 存在；
2. `K60_REPO or ctx.device` 下有 `docs/engineering/RULES.toml`。

**device 仓（`/opt/k60/trees/usb-cdc-mainline/device` 与 `wifi-device`）都没有
`docs/engineering/RULES.toml`** → 会报：

```
unixnu: build refused: /opt/k60/trees/wifi-device has no docs/engineering/RULES.toml,
so the registry cannot run. Point K60_REPO at the device repository that produced this build input.
```

**解法（二选一，需 Lead 定）**：

- **A（推荐）**：`export K60_REPO=/mnt/e/hackios/k60-wifi` —— 该仓有
  `docs/engineering/RULES.toml` 与 `scripts/check-rules.py`，门禁能真跑。
- **B**：`export UNIXNU_SKIP_GATES=1` —— 只打印
  `GATES SKIPPED on request; the result is not gated`，**`build-strict.sh` 会硬拒**，
  只能用于 trial。

---

## 6. 验证这套接线是否真的生效（三条硬判据）

```bash
K=out-wifi/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho

# 1) 符号真的被链进来了（force_load 生效）
llvm-nm -a $K | grep -E "_pong_wifi_start_optional|_pong11_pong_ath11k_pci_init"

# 2) 固件包真的进了 __TEXT,__const
llvm-nm -a $K | grep -E "_pong_wifi_firmware$|_pong_wifi_firmware_end$"
llvm-objdump --macho --section-headers $K | grep -i const

# 3) 没有未定义符号（`llvm-nm -u` 应为空或不含 pong 前缀）
llvm-nm -u $K | grep -E "_pong|_pong11" || echo "OK: no undefined pong symbols"
```

---

## 6.5 0010 必须同时改两条归档装配路径（2026-11-14 实测）

`build-xnu-4k-baseline.sh` 有**两条互斥**的归档装配路径，内核只会走其中一条：

| 路径 | 变量 | 生效条件 | 行 |
|---|---|---|---|
| A | `KERNEL_EXTRA_ARCHIVES` | `XNU_SOURCE_CORECRYPTO14=1` | 整块 :892–:1077，0010 的 hunk1 在 :922 |
| B | `PLATFORM_ARCHIVES` | `ARM_DT_PLATFORM=1` 且 `XNU_SOURCE_CORECRYPTO14 != 1` | :1120 起，0010 的 hunk2 在 :1143 |

**mondrian 走的是 B。** `out-*/…/mondrian/.config` 里
`CONFIG_XNU_SOURCE_CORECRYPTO14` **出现两次**（:2 `=y`、:88 `=n`），
`config.py parse_config()` 逐行赋值、后者覆盖前者 → False → A 整块被跳过。

0010 初版只加了 A 的 `KERNEL_EXTRA_ARCHIVES`，结果：
`kernel.log` 里 `force_load` 计数 **0**、`LD_KERNEL_ARCHIVES` 计数 **0**，
链接期报三个未定义符号：

```
Undefined symbols for architecture arm64:
  "_pong_smmu_lease_lock", referenced from:
      __ZN12_GLOBAL__N_111hostBringUpEv in libNativeUfs.a(PongUfsTransport.o)
  "_pong_smmu_lease_unlock", referenced from:
      __ZN12_GLOBAL__N_111hostBringUpEv in libNativeUfs.a(PongUfsTransport.o)
  "_pong_wifi_start_optional", referenced from:
      __ZN13ArmDTPlatform9configureEP9IOService in libArmDTPlatform.a(ArmDTPlatform.o)
```

这三个符号都在 `libPongWifiNative.a` 里（`llvm-nm --defined-only` 有
`T _pong_smmu_lease_lock` / `T _pong_smmu_lease_unlock` / `T _pong_wifi_start_optional`），
纯粹是没 force_load。→ **0010 已重写为双 hunk**，两条路径都加。
只改一条会得到一个"编译全过、链接失败"的内核，症状很像缺符号，实际是接线错。

---

## 7. 不在本文件范围内但需要知道的

- `patches/wifi/0010` 改的是 `scripts/build-xnu-4k-baseline.sh`。
  `tree/scripts/` 的内容来自 **device 仓**（`unixnu/tree.py` 的 `_copy_scripts`
  从 `ctx.device` 拷），所以 **0010 必须应用到 device 仓**才算接线——
  只应用到 `k60-wifi` 工作树无效。
- `scripts/build-strict.sh` 的 `freeze()` **不哈希 `patches/wifi`**（只哈希
  `board.toml` / `dts` / `patches/xnu` / `scripts`），`SERIES_SHA/COUNT` 也只取
  `patches/xnu/series`。→ 改 `patches/wifi` 不会触发冻结校验，但也不会被记录进
  `build-manifest.json` 的 series 字段。**这是可观测性缺口，建议 Lead 决定是否
  扩展 freeze 清单。**

---

## 8. `docs/research/EIGHT-STEPS.toml` —— WiFi 的 ③ 与 ⑦ 已具备证据

**文件**：`docs/research/EIGHT-STEPS.toml`（共享仓 `UniXNU-mondrian`，当前由 touch 线持有，故此处只给片段）
**位置**：`[hardware.wifi.step.decompile]` 与 `[hardware.wifi.step.verify]`

```diff
--- a/docs/research/EIGHT-STEPS.toml
+++ b/docs/research/EIGHT-STEPS.toml
@@ [hardware.wifi.step.decompile]
-done = false
-evidence = "K60 的 PCI device id / BAR0 / subsystem_device / PCIe0 GDSC 偏移 / SPMI 通道号均未实测，列在 docs/research/wifi/RESEARCH.md 的待补项。"
+done = true
+evidence = "2026-11-14 用实机 live FDT（E:\\k60-work\\reports\\live-6033dbec-fdt.dtb，dtc 反编译 34801 行）逐节点实测并逐条对照 drivers/PongWifi/PongWifiPlatform.cpp：端点 17CB:1103 来自 /soc/mhi_qrtr_cnss 的 qcom,dev-id=<0x1103> 与 PongWifiPlatform.cpp:356 的 cfg.r(0)==0x110317cb；BAR0 0x60200000 来自 /soc/qcom,pcie@1c00000 的 ranges（mem32 段 0x60200000 + 0x100000）与 :368 的 bar.open(0x60200000,0x200000)；IOVA 0xA0000000 来自 cnss_pci_iommu_group 的 qcom,iommu-dma-addr-pool=<0xa0000000 0x10000000> 与 :40 的 constexpr Iova；MSI 来自 msi-map=<0 0x237 0x5980 1 …> 加 :42 的 PcieGlobalIntid=32+140 / ParfMsi0=1u<<23；SID 来自 iommu-map=<0 0x5b 0x1c00 1 …>（qcom,smmu-sid-base=<0x1c00>）；refgen 100 MHz 是 max-clock-frequency-hz 的 index 10（clock_names[8]=pcie_phy_refgen_clk），:233 已用 (1u<<8)|10u；GDSC 折叠票 0x162128 bit0（非 Sheng 的 0x152020）。82 项 PHY 表与 Pong 逐 cell 相同（different=0）。全套出处见 docs/research/wifi/GAP-ANALYSIS.md 的 ③ 表。"
@@ [hardware.wifi.step.verify]
-done = false
-evidence = "未做。"
+done = true
+local_verified = true
+evidence = "三类本地核验齐全：static_check（补丁全量 git apply --check、符号面 341→31→1→0 收敛、十处 stage 门逐行核对）、unit_test（PWF2 四文件与六文件包逐条 offset/size/sha256 校验，自写 LC_SEGMENT_64 解析器比对内核内嵌 blob）、artifact_check（scripts/verify-boot-image.py 七项全过；kernel.macho 里 _pong_wifi_start_optional / _pong_wifi_firmware(_end) / _pong_smmu_lease_lock(unlock) 全部存在，llvm-nm -u 无 pong 未定义符号）。台账见 docs/research/wifi/LOCAL-VERIFICATION.md。"
+static_check = "archive 符号面 341→31→1→0；0010 双 hunk 覆盖 KERNEL_EXTRA_ARCHIVES 与 PLATFORM_ARCHIVES 两条互斥路径；十处 stage 门行号与源码一致（见 LOCAL-VERIFICATION.md §2）。"
+unit_test = "PWF2 六条目 offset/size/sha256 全部与源文件一致，内核内嵌固件与包逐字节相同（LOCAL-VERIFICATION.md §3）。"
+artifact_check = "verify-boot-image: OK；linkarchives 含 -Wl,-force_load,…/libPongWifiNative.a；kernel.macho 65,978,368 B（LOCAL-VERIFICATION.md §4）。"
```

`[hardware.wifi.step.device]` 保持 `done = false`：⑧ 尚未取得任何一次带 WiFi 的启动证据
（见 `STAGE-BRINGUP.md` §5 与下节）。

---

## 9. 上机阻塞：设备自 04:50 起不再枚举

2026-11-14 04:50 之后 `adb devices` 与 `fastboot devices` 全空，
`Get-PnpDevice -PresentOnly` 里没有任何 `VID_2717`/`VID_18D1`/`VID_1209` 在线项，
同机 peer 线（`usblog-20261114-bts1b-run1`）也在同一时刻掉到 `port-not-observed`。
**需要人工长按电源键约 10 秒强制重启**，之后才能继续阶梯上机。

