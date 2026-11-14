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

2026-11-14 04:50 之后 `adb devices` 与 `fastboot devices` 一直全空，
`Get-PnpDevice -PresentOnly` 里没有任何 `VID_2717`/`VID_18D1`/`VID_1209` 在线项
（只剩键盘/摄像头/蓝牙/读卡器），`HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` 里也只剩
`BthModem0/1` 的 COM3/COM4，没有 `USBSER000`。同机 peer 线
（`usblog-20261114-bts1b-run1`）在同一时刻掉到 `port-not-observed`、`bytes=0`，
说明是整机状态而不是某一张镜像。**需要人工长按电源键约 10 秒强制重启**。

等待期间已经把三族阶梯全部构建并逐张验证完，设备一回来就能连续跑：

| 族 | 镜像 | 内核 | 证明什么 |
| --- | --- | --- | --- |
| 库存基线 | `wifi-20261115z0` | 54,181,888 B 无 WiFi 代码 | 这台手机能不能启动这张 FD |
| 小固件 | `wifi-20261115t0…t8` | 54,804,480 B，23 字节占位固件 | 11.2 MB blob 是不是元凶 |
| 真固件 | `wifi-20261115a…g` + `p` | 65,978,368 B，六文件包 | 真正的分级 bring-up |

17 张全部通过 `verify-boot-image.py` 与 `argcheck1.py`（命令行 574–606 字节，
都在 DarwinBoot 的 607 字节上限内）。runner 是
`E:\k60-work\evidence\wifi-trial\ladder6-run.ps1`：先跑控制镜像 `a`，再跑
全十级镜像 `g`（一次启动打出所有 `stage N` 行，最后一条即故障块），
首张零字节控制台就停（exit 12）。只有 `g` 也静默时才退回线性阶梯
`b → c → p → d → e → f`；只有 `a` 本身没有控制台时才退到体积二分 `z0 → t0 → t1`；
`z0` 也零字节则以 exit 13 收尾，说明问题在手机或 FD，与 WiFi 无关。
判读表见 `STAGE-BRINGUP.md` §6，装载规则见同文 §7。

---

## 10. `docs/engineering/BOOT-ARGS.md` —— 9 个 WiFi boot-arg 未登记（hard-8 / P-156）

**文件**：`docs/engineering/BOOT-ARGS.md`（不在 wifi 写作用域）
**判据**：`scripts/check-boot-args.py` 要求 `drivers/` 里每个
`PE_parse_boot_argn("…")` 的键都在 BOOT-ARGS.md 里有 `### \`name\`` 或
`| \`name\` |` 条目。实测缺 9 个，导致 `check-rules.py` 的 `hard-8` 与 `P-156` 失败。

**状态：已应用并提交**（`36af00f` "docs(boot-args): document the nine wifi boot args and the real 607-byte limit"）。
`scripts/check-boot-args.py` 现在报 ✅「覆盖 config 29 / 源码 20 个参数（已文档化 49）」
✅「已声明范围的 7 个参数都在范围内」，`check-rules.py` 的 `hard-8` 与 `P-156` 转绿。
下面保留当时的合并请求原文与离线验证记录，供复核。

**完整替换文本**：`E:\k60-work\evidence\wifi-trial\BOOT-ARGS-MERGE.md`（135 行）。
它做四件事：

1. 修正字节预算。现有文字写「上限 608 字节，当前 30 项 591，余 17」——
   **两个数都错**。真判据是 `DarwinBoot.c:678-684`：
   `if ((Index >= sizeof (CommandLine) - 1) || (Request->BootArgs[Index] > 0x7f)) return EFI_BAD_BUFFER_SIZE;`
   而 `BootArgs.h:8` 的 `DARWIN_BOOT_LINE_LENGTH` 是 608 → **合法上限 607**，
   且出现任何非 ASCII 字节同样直接返回。这个返回发生在 `ReadFile`/`ParseKernel` **之前**，
   屏幕停在 REQUEST 阶段、**串口一个字节都没有**、设备自己回 fastboot。
   实测 board.toml 当前 29 项 = 575 字节。
   （旁证：bt 线 `usblog-20261114-bts1b-run1` 的 args 是 610 字节，正是 0 字节 +
   `port-not-observed`。框架 `payload.py:30-38 check_args()` 只拦 >1000，
   注释里的「1024-byte buffer」是过时的，不会替我们拦住 607–1000。）

2. 补 9 行表格（`| 参数 | 所属 | 接受值 | 未设时 | 陷阱 |`）：
   `pong_wifi`(==1) / `k60_wifi_rsc`(0..2) / `k60_wifi_stage`(0..10) /
   `pong_wifi_dma_mib`(64..128) / `pong_wifi_diag` / `pong_wifi_test` /
   `pong_wifi_alt` / `pong_wifi_band`(0/2/5) / `pong_wifi_cycle`。
   第三列必须是 `N..M` 或 `≤N` 形式——`check-boot-args.py` 只解析这两种才会把它当
   范围判据去校验 board.toml 的值（P-156 的机制）。

3. 补 9 段 `### \`name\`` 逐个说明（所属 / 接受值 / 未设时 / 作用 / 陷阱 / 源码行号）。

4. 源码出处全部核实过：
   `PongWifiPlatform.cpp:72`(stage)、`:408`(dma_mib)、`:572`(test)、`:573`(alt)、
   `:574`(band)、`:647`(diag)、`:716`(pong_wifi)、`:744`(rsc)、
   `PongWifiNet.cpp:890`(diag)、`:892-893`(test && cycle)。

**顺带记一个上机约束**（与 §5 的阶梯镜像直接相关，数字为 `argmath.py` 实测）：
board.toml 的 575 字节里，`pong_wifi=1` 要 **12** 字节、`k60_wifi_rsc=2` 再加 **15**、
`k60_wifi_stage=10` 再加 **18**，合起来 **620 > 607**。**阶梯镜像必须同时覆盖两个让位项**：
`epoch=1793709100` 改 `epoch=1`（省 **9**）与 `debug=0x140` 改 `debug=1`（省 **4**），
两项合起来 620-13=**607** 以内的实测值是 589（`pong_wifi=1 k60_wifi_rsc=2 epoch=1 debug=1`）。
`--kernel-arg` 是按名覆盖，不会触发 P-166 序列检查。
`k60_fontscale=0` **不能**用来让位：`video_console.c:2844` 要求 `scale >= 2 && scale <= 4`，
0 会被忽略、字节照旧。

5. **离线验证过这个片段确实能关掉 hard-8 与 P-156**（脚本
   `E:\k60-work\evidence\wifi-trial\simulate-bootargs.py`，直接复刻
   `check-boot-args.py` 的两段逻辑，把片段追加在现有 BOOT-ARGS.md 之后跑）：

   ```
   current            documented=40 missing=9 ['k60_wifi_rsc', 'k60_wifi_stage', 'pong_wifi',
                      'pong_wifi_alt', 'pong_wifi_band', 'pong_wifi_cycle',
                      'pong_wifi_diag', 'pong_wifi_dma_mib', 'pong_wifi_test']
   with fragment      documented=49 missing=0
   range rows parsed: {'k60_touch_se': (0, 7), 'k60touchhz': (0, 15000000), 'touch_flip': (0, 3),
                       'k60_wifi_rsc': (0, 2), 'k60_wifi_stage': (0, 10), 'pong_wifi_dma_mib': (64, 128)}
   board.toml out of declared range: none
   RC=0
   ```

   即：9 个缺口全补上，且新登记的三条范围判据（`k60_wifi_rsc` 0..2、`k60_wifi_stage` 0..10、
   `pong_wifi_dma_mib` 64..128）对 board.toml 现值全部通过。片段全文在
   `E:\k60-work\evidence\wifi-trial\BOOT-ARGS-MERGE.md`。

---

## 11. `scripts/check-rules.py` 现状：8 条失败里只有 2 条是 WiFi 的

在 `/mnt/e/hackios/k60-wifi` 跑 `python3 scripts/check-rules.py --repo /mnt/e/hackios/k60-wifi`：
登记 65 条、执行 19 个不同命令、**失败 6 条**（BOOT-ARGS 落地前是 8 条）、waiver 37 条。
剩下的 6 条没有一条属于 WiFi：

| 规则 | 失败原因 | 归属 | 处理 |
| --- | --- | --- | --- |
| ~~`hard-8`~~ | ~~`pong_wifi_test (drivers/)`~~ | **WiFi** | ✅ 已修：§10 的 BOOT-ARGS.md 片段已落地（`36af00f`） |
| ~~`P-156`~~ | ~~`pong_wifi_test (drivers/)`~~ | **WiFi** | ✅ 同上 |
| `iron-3` | `eight-step-gate.py --build` 红在 touch 的 ④⑤⑥⑦ | touch 线 | 不是 WiFi：`[hardware.wifi]` 是 `status="parked"`，门禁只硬检查 active 项 |
| `iron-4` | `porting-gate.py --quick` 报 `[X] series 三处一致 不一致` | 共享仓 series | `SERIES-FINAL.txt` / 仓库 / 构建输入三份 `patches/xnu/series` 文本不一致，要 Lead 收敛 |
| `iron-5` | `sync-device-input.py --check` 报 11 个文件待同步 | 共享仓 | 见下 |
| `P-165`/`P-166` | 仓库有 3 个 `zzzz…-pong-touch-*.patch`、构建输入没有 | touch 线 | 清理 touch 的临时补丁 |
| `hard-33` | 输出里的 `=====` 分隔线被当失败行 | 检查器自身 | 与 WiFi 无关，属 check-rules 的解析瑕疵 |

`iron-5` 的 11 个待同步文件（`sync-device-input.py --check` 原文）：

```
patches/xnu/0613-k60-adsp-pas.patch
patches/xnu/0614-k60-adsp-call-site.patch
scripts/append-conffiles.py
scripts/build-strict.sh
scripts/check-adsp-claims.py
scripts/check-build-freshness.py
scripts/check-docs.py
scripts/eight-step-gate.py
scripts/porting-gate.py
scripts/sync-device-input.py
scripts/tests/test-build-strict-gates.py
```

这 11 个都不在 WiFi 写作用域（`patches/xnu/` 与 `scripts/` 是共享资产），
而且同步它们会改到别的线正在用的构建输入，所以留给 Lead 统一处理。

**对 WiFi 线的实际影响**：`iron-3` 会让 `scripts/build-strict.sh` 拒绝构建（它硬跑
`eight-step-gate.py --build`），`iron-4`/`iron-5` 会让 `flash.sh` 的四道门报红。

## 12. `patches/wifi/series` 漂移已补齐：新增 0011

2026-11-14 复核发现系列只到 0010，而仓库里 `drivers/PongWifi/PongWifiPlatform.cpp`
在 `5483a39` / `1cc4892` / `309e96c` 三次提交后已经多出 USB 控制台门、十级
`k60_wifi_stage` 门与 refgen 注释修正 —— 也就是说**系列落后于代码 240 行**，
任何人按系列把 WiFi 移植到上游 device 树都会拿到没有门控的版本，正好会重现
04:48 那次 0 字节控制台。

- 新增 `patches/wifi/0011-drivers-PongWifi-k60-bringup-stages.patch`（141 行，
  49 增 10 删），只改 `drivers/PongWifi/PongWifiPlatform.cpp`。
- `patches/wifi/series` 追加该行，现 11 个补丁。
- 复核方法（可重跑）：把 `/mnt/e/k60-work/impl/wifi/repo`（干净的 device 基线，
  没有 `drivers/PongWifi`）复制到 `/tmp`，按 `series` 顺序 `git apply` 全部 11 个，
  然后与仓库 HEAD 逐文件比对 → **14 个 `drivers/PongWifi` 文件全部 `SAME`**，
  脚本 `E:\k60-work\evidence\wifi-trial\verify-series-repro.sh`。
- 同一份系列**不能**直接打在仓库 HEAD 上（0001–0010 的内容已由 `f4717ef` 提交，
  会报 `already exists in working directory` / `patch does not apply`）。系列只用于
  向上游 device 树移植，这一点已写进 `patches/wifi/README.md`。
- `scripts/check-patch-apply.py` 仍绿（P-162：只有改动过的补丁才校验）。

## 13. 顺带发现：别的线有 12 张镜像超过 DarwinBoot 的 607 字节命令行上限

跑 `E:\k60-work\evidence\wifi-trial\check-artifacts.py` 时，它顺手校验了 `E:\k60-work\artifacts\*` 下所有镜像。
结果里有 12 张**不是 WiFi 的**镜像命令行超限（判据见 §10 与 `STAGE-BRINGUP.md` §7：
`DarwinBoot.c:678-684` 在 `ReadFile` 之前就 `return EFI_BAD_BUFFER_SIZE`）：

| 镜像 | args 长度 |
| --- | --- |
| `bt-s1-20261114b` | 610 |
| `bt-s1b-20261114a` | 610 |
| `bt-s1c-20261114a` | 610 |
| `bt-s1c-20261114b` | 638 |
| `bt-s1c-a1-20261114a` … `bt-s1c-a4-20261114a` | 638（各 4 张） |
| `wifi-20261114f` / `g` / `h` | 619 / 619 / 620（WiFi 自己的旧图，已作废） |

这条**解释了蓝牙线 04:51 那次 `usblog-20261114-bts1b-run1` 的 `state=port-not-observed, bytes=0, stopReason=port-timeout`**：
镜像 `bt-s1-20261114b` 是 610 字节，内核根本没被装载，所以串口一个字节都不会有。
同一天 04:43 的 `rail-20261114i`（575 字节）能拿到 220,576 字节控制台，
差别就在这里，不是抓取链路、也不是内核。

建议：其它线在下次上机前用 `argcheck1.py` 过一遍自己的镜像
（`python3 E:\k60-work\evidence\wifi-trial\argcheck1.py <boot.img> …`，上限 607），
并考虑把 `payload.py` 的 `check_args()` 上限从 1000 改成 607 ——
那里现在注释写的是「DarwinBoot copies the command line into a 1024-byte buffer」，
与 `DarwinBoot.c` 的 608 不符，所以 `unixnu` 不会替任何人拦住 607–1000 的参数。

---
因此 WiFi 的 ⑦ 产物是用 `UNIXNU_SKIP_GATES=1` 的试构建路径出的，
⑧ 上机走的是唯一 supervisor `scripts/boot-and-capture.ps1`（不经过 `flash.sh`）。
**这两点必须在正式合并前由 Lead 决定**：要么把 touch 的 ④⑤⑥⑦ 补齐让 `iron-3` 转绿，
要么为 WiFi 的试构建路径留下明确记录（现记在 `LOCAL-VERIFICATION.md` §5.8 与本文 §5）。


