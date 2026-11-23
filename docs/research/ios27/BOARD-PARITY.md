# BOARD-PARITY — K60 iOS 27 板级配置与成功先例的逐项差异

状态：**只读审计**（冻结期，未构建、未上机、未写 `/dev/block/sda38`）。
对象：`E:/hackios/k60-gates/board.toml`（27 profile `ios-27.0.1-24A446`）对比
`E:/hackios/UniXNU-sheng/board.toml`（`ipados-27.0.1-24A446`，已进 SpringBoard）。
同芯片对照：`E:/hackios/UniXNU-zizhan/board.toml`（SM8475，`ipados-18.7.10-22H374`）。

复现：

```bash
python3 scripts/compare-board-parity.py --ours . --theirs /mnt/e/hackios/UniXNU-sheng
python3 scripts/compare-board-parity.py --ours . --theirs /mnt/e/hackios/UniXNU-zizhan \
    --profile ipados-18.7.10-22H374
```

脚本只读 `board.toml` / `configs/*`，两分钟以内，不调用构建器。

## 1. 组件 include

| 侧 | 数量 | 列表 |
|---|---|---|
| 我们（27） | 3 | `ArmDTPlatform`, `ArmCpu`, `XnuPrelink` |
| sheng（27） | 11 | `Adreno740`, `AdrenoMetal`, `AppleKeyStoreState`, `DarwinBoot`, `GopFramebuffer`, `PongPlatform`, `RamBlock`, `ShengPreflight`, `ShengUfs`, `XnuPrelink`, `ArmDTPlatform` |
| zizhan（18.7） | 1 | `PongPlatform24` |

sheng 侧独有 8 个：`Adreno740`、`AdrenoMetal`、`AppleKeyStoreState`、`DarwinBoot`、`GopFramebuffer`、`RamBlock`、`ShengPreflight`、`ShengUfs`。
（`PongUfs` 只在我们的 16.6.1 profile 里；27 profile 的 include 覆盖成上面三项。）

## 2. kernel archives

我们 8 条：

```
build-corecrypto-14.py                       build-corecrypto-14.py --namespace
build-libpthread-kernel.py                   build-firehose-stub.py --tree .
build-k60-platform-archives.py --tree .      build-k60-fileset-reference.py --tree . --skip-build
component:ArmDTPlatform                      component:ArmCpu
```

sheng 19 条，其中 13 条我们完全没有：

```
build-adreno740-accelerator.py            build-adreno740-kits.py
build-fileset-release-reference.py --tree . --lto
build-gop-legacy-display-27.py
build-sheng-source-storage.py --policy-dir scripts/policies/ipados-27.0.1-24A446
component:Adreno740                        component:AppleKeyStoreState
component:RamBlock                         component:ShengUfs
fetch-adreno-inputs.py                     fetch-sheng-dts.py
prepare-sheng-gmu-votes.py                 prepare-sheng-gmu.py
prepare-sheng-gpu-smmu.py
```

（`build-fileset-release-reference.py --tree . --lto` 我们也有同名脚本，但差 `--lto`，
用的是 Mac 侧预建的 LTO 参考 + `--skip-build`。）

## 3. payload `kernel_args`

我们 10 项：`-v`、`serial`、`debug`、`kt_fixed_zones`、`-no_slto_panic`、`use_contiguous_hint`、
`amfi_get_out_of_my_way`、`k60_fontscale`、`-uketextconsole`、`-ukedeferredconsole`、`-enable_kprintf_spam`。
sheng 52 项；**sheng 有而我们没有的键 47 个**：

```
appsync armcpu-self-ipi armcpu-spi-ipi native-source-storage native-ufs-root
offline-hid-home offline-hid-input offline-key-events offline-legacy-cpu-present
offline-legacy-gop offline-legacy-phase offline-legacy-pm offline-legacy-register
offline-legacy-transfer offline-legacy-unit-scale offline-legacy-validate
offline-mobile-graphics-client offline-mobile-graphics-load
sheng-adsp sheng-aks sheng-aks-sls sheng-audio sheng-backlight sheng-bluetooth
sheng-buttons sheng-cpufreq sheng-data-persist sheng-disable-watchdogd
sheng-dpu-scanout sheng-fb-bgra sheng-fb-gpu sheng-gpu-addon sheng-gpu-dcvs
sheng-gpu-metal sheng-gpu-power sheng-keyboard sheng-lite sheng-log sheng-no-lc
sheng-smp sheng-touch sheng-touch-hid sheng-usb sheng-vsync sheng-vsync-fixed sheng-wifi
```

> 参数本身不产生行为：每一条都要有对应组件/补丁读它。这张表的用途是**列出候选缺口**，
> 不是「全部照抄」。例如 `sheng-dpu-scanout`、`sheng-fb-gpu` 在没有 `GopFramebuffer` 时无人读取。

## 4. defconfig 差异（按类分组，节选）

### 4.1 OS/安全 owner（sheng=y，我们缺或 n）

| 键 | 我们 | sheng |
|---|---|---|
| `CONFIG_XNU_KERNEL_CHAINED_FIXUPS` | — | y |
| `CONFIG_XNU_OWNER_BOOT_MANIFEST` | n | y |
| `CONFIG_XNU_OWNER_ROOT_TRUST` | n | y |
| `CONFIG_XNU_OWNER_ROOT_AUDIT` | n | y |
| `CONFIG_XNU_NATIVE_RAM_BLOCK` | n | y |
| `CONFIG_XNU_SOURCE_STORAGE` | — | y |
| `CONFIG_XNU_SOURCE_STORAGE_TABLES` | — | `userdata` |
| `CONFIG_XNU_CRYPTO_BOOTSTRAP` | `prelinked` | `source` |

### 4.2 显示（sheng=y，我们=n）

`CONFIG_XNU_NATIVE_LEGACY_DISPLAY`（我们 `configs/mondrian_ios27_defconfig:22 = n`，sheng `configs/sheng_ipados27_defconfig:21 = y`）。

### 4.3 K60 专有（我们有，sheng 没有）

`CONFIG_XNU_ARMCPU`、`CONFIG_XNU_ARM_DT_PLATFORM`、`CONFIG_XNU_NATIVE_UFS`、
`CONFIG_XNU_OWNER_DATA_UFS`、`CONFIG_XNU_OWNER_UNION_SYSTEMOS`、`CONFIG_XNU_K60_PHYSICAL_BATTERY`、
`CONFIG_XNU_GPU_ADDON`、`CONFIG_XNU_PONG_ADRENO_PLATFORM`、`CONFIG_XNU_PONG_RAMOOPS_CONSOLE`、
`CONFIG_XNU_PONG_VOLATILE_PANIC_LOG`、`CONFIG_XNU_PONG_APFS_DEBUG`。

### 4.4 同芯片参考 zizhan（SM8475）有、我们缺的硬件族

`CONFIG_XNU_PONG_BACKLIGHT`、`CONFIG_XNU_PONG_POWER`、`CONFIG_XNU_PONG_WIFI`、`CONFIG_XNU_OWNER_CRYPTEX_FILES=y`。
我们的这些硬件走 27 的 `k60_*` 补丁与 `drivers/PongPower`，不是同一套组件；差异属**架构不同**，
不能按名字判缺口——但 zizhan 的 `PongPlatform24` 是 SM8475 上已验证的显示/电源实现，应作为
「DPU 基址、PMIC 轨道、MIPI 时序」的第一手来源（sheng 是 SM8550，`0xae01000` 不可照抄）。

## 5. 判定

| 项 | 判定 | 依据 |
|---|---|---|
| `GopFramebuffer` 组件缺失 | **确认为缺口** | 没有它就没有 `IOFramebuffer`/`IOMobileFramebuffer` provider；sheng 同 OS 同架构、`verified_devices=["sheng"]`；我们 27 defconfig 把 `NATIVE_LEGACY_DISPLAY` 关着，PE 文本控制台直写是唯一输出路径 |
| `DarwinBoot` 组件 | **确认为缺口（ABI）** | 我们的平台包是 Darwin 22（608 字节命令行、`BootFlags==0x2d0`），27 内核要求 1024/`0x470`；`Video[]` 偏移两边一致 |
| `RamBlock` / `AppleKeyStoreState` / `ShengPreflight` | 未知 | sheng 专有命名，需读组件源码判是否 27 必须 |
| `OWNER_BOOT_MANIFEST` / `ROOT_TRUST` / `ROOT_AUDIT` / `KERNEL_CHAINED_FIXUPS` | 未知 | 需读 `bsd/dev/*` 的实现与 27 profile 的 `[kernel]` 要求 |
| 47 个 sheng kernel 参数 | 候选清单 | 每条须找到读取它的代码，否则不生效 |
| zizhan 的 PONG_BACKLIGHT/POWER/WIFI | 架构不同 | zizhan 用 `PongPlatform24` 一体组件，我们用分拆组件 |

## 6. 下一步（全部离线）

1. 用 `GopFramebuffer` 的 `NativeLegacyDisplay.cpp` + `legacy-display-24A446.json` 抽出
   `NativeLegacyDisplay` / `NativeGOPPresenter` 两块，评估在 Linux 上编出
   `libNativeLegacyDisplay.late.a` 的最小集合（sheng 的 builder 合并了键鼠/USB/蓝牙，不能整支拷）。
2. 逐键读源码判定 §5 的「未知」项（`grep` 宏名 → 找到唯一读取点 → 记录 file:line）。
3. 对 zizhan 的 `PongPlatform24` 提取 SM8475 的 DPU/PMIC 常量，与我们的 `k60_*` 对照。
4. 上述三项完成后，才讨论解冻构建。
