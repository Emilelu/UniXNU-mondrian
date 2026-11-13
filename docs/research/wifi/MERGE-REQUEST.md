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
