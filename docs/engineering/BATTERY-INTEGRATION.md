# 电池栈编译集成（SA-01）

> 来源：subagent SA-01，2026-11-12
> 状态：只读调研完成，结论已落库，改动已按此执行
> 关联：`docs/research/battery/RESEARCH.md`、`drivers/PongPower/`、`patches/xnu/0602-k60-physical-battery.patch`

---

## 1. `scripts/build-xnu-4k-baseline.sh` 需要的 4 处改动

上游 1,293 行 vs 我们 1,244 行，8 个 hunk，**电池相关 4 个**：

| # | 上游行 | 我们的位置 | 内容 |
|---|---|---|---|
| 1 | 576 | 558 | `bsd_init.o_CFLAGS_ADD` 加 `-DXNU_K60_PHYSICAL_BATTERY=${XNU_K60_PHYSICAL_BATTERY:-0} ` |
| 2 | 625 | 607 | `IOKitBSDInit.cpo_CFLAGS_ADD` 加同一宏（**最关键**，0602 的调用点在这个文件）|
| 3 | 1112-1127 | 1094-1098 | bootstrap 链接块：`BOOT_ARCHIVES` + `if [ "${XNU_K60_PHYSICAL_BATTERY:-0}" = 1 ]` → `K60_BATTERY_ARCHIVE=${XNU_K60_PHYSICAL_BATTERY_ARCHIVE:-$ROOT/build/k60-physical-battery/libK60PhysicalBattery.a}` → force_load → `EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$BOOT_ARCHIVES")` |
| 4 | 1170-1184 | 1140 的 `fi` 与 1141 之间 | 正式链接块：`echo K60DIAG` + 同一检查 + `PLATFORM_ARCHIVES`/`PLATFORM_DEPENDENCIES` 加归档 |

**dtor lowering 不用改脚本** —— 两个版本都没有该 flag，它在 `build-k60-physical-battery.py:313-317` 和 `unixnu/kernel.py:79` 的 `CROSS_EXTRA_FLAGS` 里。

**不要照抄的 hunk**：`ditto`→`cp`(206)、`installhdrs` host vars(238)、空行(438)、末尾 make host vars(1280)。这些是上游自己的环境适配。

## 2. `configs/mondrian_defconfig`

本地 68 行，在 `CONFIG_XNU_BUILD_ARCHIVES=y` 后追加两行（对应上游 69-70）：

```
# K60 PMIC-GLINK battery: registers only after an authenticated PAS1 lease
CONFIG_XNU_K60_PHYSICAL_BATTERY=y
```

⚠️ **不要抄**上游的 `OWNER_DATA_VOLUME_UUID` —— 那是它自己的 seed。

## 3. `0602` 补丁与宏的完整链路

补丁只改 `iokit/bsddev/IOKitBSDInit.cpp`，hunk `@@ -109,8 +109,16 @@`，宏出现在两处：
- `IOKitBSDInit()` 前加 `extern "C" void k60_physical_battery_start(void);`
- `publishResource("IOBSD")` 之后加调用

**链路**：

```
configs/mondrian_defconfig
  CONFIG_XNU_K60_PHYSICAL_BATTERY=y
    ↓ unixnu/config.py:82-107  parse_config（去 CONFIG_ 前缀，y→True）
  XNU_K60_PHYSICAL_BATTERY = True
    ↓ unixnu/kernel.py:11-18   xnu_env（True→'1'）
  环境变量 XNU_K60_PHYSICAL_BATTERY=1
    ↓ build-xnu-4k-baseline.sh:576/625  ${...:-0}
  make 为 bsd_init.o / IOKitBSDInit.cpo 加 -D
```

`patch -p1 --dry-run` 在 xnu 8796 树上**干净通过**。

## 4. `scripts/build-k60-physical-battery.py`

345 行，与上游逐字节相同。

**参数**：`--tree` / `--output-dir`(必填) / `--framework` / `--hardware-dtb`(必填) / `--battery-module`(必填) / `--charging-wire` / `--discharging-wire` / `--notification-wire` / `--sdk-root` / `--emit-config-only`

**输出**：`K60BatteryConfig.generated.c`、`K60BatteryProtocol.generated.h`、`captured-board-config.bin`、`build-report.json`、`libK60PhysicalBattery.a`

**时机**（关键）：必须在 `build-xnu-4k-baseline.sh:233` `installhdrs` 生成 `.cache/fakeroot/.../IOPMPowerSource.h` **之后**（否则 `ValueError 'Build the real Darwin22 Kernel SDK'`），且在 1231 的 `make build` **之前**。

实际做法：
1. 先跑一次主脚本（会在 1119/1179 报 missing 并 exit 1，此时 fakeroot 已好）
2. 跑本脚本
3. 再跑主脚本

**参数取值**：
- `--framework` 必须指向含 `scripts/unixnu/devicetree.py` 的 core —— 我们仓库没有 `scripts/unixnu`，用 `/opt/k60/trees/k60build`
- `--hardware-dtb` 可用 `/mnt/e/k60-work/reports/live-6033dbec-fdt.dtb`（六个必需 compatible 全有）
- `--battery-module`（`qti_battery_charger_main_m81` 的 AArch64 ELF）**本机没找到 —— 硬缺口**

## 5. 缺失的注册点

| 缺什么 | 证据 | 修法 |
|---|---|---|
| 构建输入树没有 `drivers/PongPower` | `sync-device-input.py --check` 报 17 个待同步 | 跑不带 `--check` 的同步 |
| `series` 三处不一致 | `porting-gate --quick` 阻断 | 三处：`SERIES-FINAL.txt`（尾行 0600，缺 0602）、`/tmp/usb-cdc-mainline/device/patches/xnu/series`、仓库 `series`（第 216 行已有）。两棵 device 树还缺 0602 补丁文件本身 |
| `porting.toml` power 区 paths 缺 `drivers/PongPower/**` | 上游 `porting.toml:153` 有；本地 `check-porting-paths.py` 报 13 条 error | 补上 |
| 没有任何地方调用归档构建脚本 | 全仓/上游 grep 只有脚本自身 | 必须显式加一步 |
| **不用加**：`board.toml` components/archives | 上游也没加 | — |
| **不用加**：`k60_battery=1` | 默认就是 1 | — |
| 过期文档 | `EIGHT-STEPS.toml:402` 说「我们仓库没有 PongPower 目录」 | 更新 |

## 6. 无 PAS1 租约时的运行时行为（读代码结论）

`K60Battery.cpp:416-434`：

```
/chosen 缺 k60-adsp-glink-handoff（拼写以 K60BatteryConfig.h:17 为准）
  → lease = K60ConfigNoOwnership (-4)
  → 打印 "K60Battery: blocked rc=-4: no authenticated exclusive PAS1/SMEM/GLINK
     platform handoff; no MMIO, FIFO writes or power-source publication"
  → return
```

**后果**：
- `new K60Battery` / `attach` / `begin` / `IOPMPowerSource::start` **全不执行**
- **一个电池对象都不创建**
- 系统无电池电源（用户态显示无电池/未知）
- **不 panic、不伪造电量**

`flags != 0xF` 或 `epoch == 0` 同样走 blocked。
即使租约有效，`K60PmicGlink::open():112` 与 `115-120` 的 RAM 重叠检查、
`discover()` 的 SMEM item 校验还会分别拒绝并只打日志。

**仓库里没有任何生产者写这个属性**（grep 只命中 `K60BatteryConfig.h:17`），
dts 也没有 ADSP 节点 —— **当前运行时必然是 blocked**。

## 7. 执行顺序（按重要性）

1. `configs/mondrian_defconfig` 加两行
2. 构建脚本 4 处（**IOKitBSDInit 的宏最关键**）
3. 构建输入同步（`sync-device-input.py`）
4. `series` 三处一致 + 0602 补丁文件拷贝到两棵 device 树
5. `porting.toml` power 区补 `drivers/PongPower/**`
6. 归档构建步骤（`build-k60-physical-battery.py`）
7. **首次开启时删 `IOKitBSDInit.cpo` / `bsd_init.o`** —— make 的 stamp 不追踪电池宏

## 8. 硬缺口

`--battery-module` 需要 `qti_battery_charger_main_m81` 的 AArch64 ELF，**本机没有**。
这个 ELF 是 `build-k60-physical-battery.py` 的必填输入，用来提取 PMIC GLINK 协议常量。
没有它，归档构建不出来，电池栈编不进去。

**获取方式**：从 K60 的 `/vendor/lib64/hw/` 或 Android 的 `qti_battery_charger` 模块里取，
或用 `--emit-config-only` 先生成配置看缺哪些字段。
