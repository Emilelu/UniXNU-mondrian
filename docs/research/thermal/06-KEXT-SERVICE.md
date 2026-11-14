# 06 · 内核侧：发布 mTPL 的 IOKit 服务

本篇记录热管理线**内核态**那一半：把 `drivers/PongThermal/K60Tsens.c` 的 32 路读数与
`K60ThermalLevel.c` 的压力等级，做成 `thermalmonitord` 能打开的 `AppleSMCSensorDispatcher`。
代码在 `drivers/PongThermal/K60ThermalService.{h,c}`，构建脚本 `scripts/build-thermal-kext.sh`，
产物 `build/thermal-kext/libK60ThermalKext.a`（sha256 `8fa4bf72e931d3d79e66d281ed43849ab129e36fd0a71b0a272d0fcd6dfbb8d4`）。

**本篇的诚实边界**：服务已经能编译、符号已核验、219 个内核导入全部在 `all-kpi.exp` 里；
三处集成（内核链接行、启动钩子、ADT tsens 节点）已于 2026-11-14 由 Lead 落进仓库源码，
但全部默认关闭（`XNU_PONG_THERMAL=0`），从未用 `=1` 真正构建过内核，也从未上机，
所以 step ⑤ 仍是 `done = false`。三处落地的现状见 §6。

---

## 1. 为什么必须是内核服务

`05-PRESSURE-LEVEL.md` §1 已经从消费者那一侧说明了契约：`thermalmonitord` 用
`IOServiceMatching("AppleSMCSensorDispatcher")` 找 nub，然后开 user client，selector 0 取 key 数量、
1 取 key 码表、2 取值，取 key `mTPL`（0x6d54504c）作为 `OSThermalPressureLevel` 直接
`notify_post` `com.apple.system.thermalpressurelevel`。**daemon 不做换算，也不做通知** —— 通知是它自己的
动作，内核只需要答对三个 selector。

所以这一半的验收标准不是"能读到温度"，而是"daemon 能打开它并拿到正确的 0..4"。

## 2. 对象模型

三个类，都在 `K60ThermalService.h` 声明、`K60ThermalService.cpp` 实现：

| 类 | 基类 | 职责 | 出处 |
|---|---|---|---|
| `K60ThermalSensor` | `IOService` | 一个 tsens 控制器。映射 TM 与 SROT 两个窗口，1 s 定时采样 16 个 STATUS 字，把 32 个读数以 `K60Temp00..K60Temp31` 属性公布 | `K60ThermalService.h:58-90` |
| `AppleSMCSensorDispatcher` | `IOService` | daemon 按类名查找的 nub。挂两个 `K60ThermalSensor`，把 32 路读数折叠成 5 个压力域再算等级 | `K60ThermalService.h:113-127` |
| `AppleSMCSensorDispatcherUserClient` | `IOUserClient` | 四个 selector 的实现，校验 entitlement | `K60ThermalService.h:94-111` |

**为什么是两个 `K60ThermalSensor`**：GPU 在 tsens0 的 idx14/15，而小核 `cpu-0-0..3`、NPU
`nspss-0..2`、DDR 全在 tsens1（`K60ThermalLevel.c` 的 `k60tl_sensor_input[32]` 表，映射依据见
`05-PRESSURE-LEVEL.md` §4）。只挂一个控制器会让一半域永远没有读数 —— 这不是优化，是正确性
（`K60ThermalService.h:117-120` 的注释即此意）。

**为什么由 `k60_thermal_start()` 自己创建而不是匹配 DT 节点**：见 §5 的 ADT 缺口。

## 3. selector 契约

dispatch 表是文件作用域常量（`K60ThermalService.cpp:323-328`），与参考实现
`ThermalLevel.cpp:160-166` 同布局：

| selector | 处理函数 | scalar in/out | struct in/out | 行为 | 出处 |
|---|---|---|---|---|---|
| 0 | `sCount` | 0 / 1 | 0 / 0 | 写 `kK60SmcKeys = 1`（本板只报一个 key） | `K60ThermalService.cpp:279-284` |
| 1 | `sKeys` | 0 / 0 | 0 / 60 | 15 个 uint32 槽，`out[0] = 0x6d54504c`（`mTPL`），其余 0 | `K60ThermalService.cpp:286-293` |
| 2 | `sValues` | 0 / 0 | 0 / 60 | 15 个槽，`out[0]` = 当前压力等级 0..4 | `K60ThermalService.cpp:295-310` |
| 3 | `sWrite` | 0 / 0 | 88 / 0 | 校验长度后计数并丢弃（本板没有可写的热状态） | `K60ThermalService.cpp:312-321` |

`selector >= 4` 返回 `kIOReturnUnsupported`（`K60ThermalService.cpp:334`）。
常量定义在 `K60ThermalService.h:34-47`：`kK60SmcSlots = 15`、`kK60SmcArrayBytes = 60`、
`kK60SmcWriteBytes = 88`、`K60SMC_KEY_MTPL = 0x6d54504cu`、
`K60SMC_ENTITLEMENT = "com.apple.private.smcsensor.user-access"`。

**entitlement 是硬门槛**：`initWithTask` 里 `copyClientEntitlement(owningTask, K60SMC_ENTITLEMENT) !=
kOSBooleanTrue` 就 `return false`（`K60ThermalService.cpp:253-260`），与参考实现同法。所以哪怕服务
在跑，没有该 entitlement 的进程也打不开 —— 这也意味着**自测不能靠随便一个用户态程序**。

**容量检查刻意不做**：`IOExternalMethodArguments` 在本树里没有 `structureOutputCapacity` 字段
（`IOKit/IOUserClient.h:134-146` 只有 `structureInput/Size/Descriptor`、`scalarOutput/Count`、
`structureOutput/Size/Descriptor`），所以两个输出 selector 只判 `structureOutput` 非空，
由 dispatch 表的 60 字节声明来约束容量 —— 与参考实现完全一致。

## 4. 读路径与等级计算

- **映射**：`mapWindow()` 两种来源（`K60ThermalService.cpp:70-99`）。由 `k60_thermal_start` 创建时用
  `IOMemoryDescriptor::withPhysicalAddress(base, 0x1000, kIODirectionInOut)->map(kIOMapAnywhere |
  kIOMapInhibitCache)`；由 DT nub 创建时退回 `getDeviceMemoryWithIndex(index)`。窗口大小按页取
  `0x1000`，因为 DT 声明的 `0x1ff` 只是寄存器区长度（`mondrian.dts:16439-16455`）。
- **基址来源**：`kK60TsensWindows[2] = {{0xc263000, 0xc222000}, {0xc265000, 0xc223000}}`
  （`K60ThermalService.cpp:347-353`），逐字对应 DT 的 `reg`（`mondrian.dts:16440` / `:16450`）——
  这是**引用**不是猜测（铁则 5）。
- **采样**：`sampleOnce()`（`K60ThermalService.cpp:171-187`）调 `k60tsens_read_controller(tm, readings)`，
  对每个 valid 读数 `setProperty("K60Temp<nn>", ...)`，并更新 `K60ThermalSamples` /
  `K60ThermalFailedReads` 两个计数器。定时器 1 s（`kPollMs`，`K60ThermalService.cpp:34`），
  与 daemon 的轮询周期同量级（`05-PRESSURE-LEVEL.md` §1）。
- **SROT 只读两个字**：`publishProperties()` 读 `SROT_HW_VER` 与 `SROT_CTRL` 并公布为
  `K60TsensVersion` / `K60TsensCtrl`（`K60ThermalService.cpp:189-198`）。**这两个属性正是 ③ 缺的
  现场值**：`SROT_CTRL bit0` 就是 `TSENS_EN`，上机后第一件事就是看它。
- **折叠**：`sampleDomains()` 把本控制器 16 路读数按 `k60tl_input_of_sensor()` 折进 5 个域，
  域内取最热（`K60ThermalService.cpp:200-217`）；`AppleSMCSensorDispatcher::level()` 清空 5 域、
  依次采样两个控制器、再用**一个共享的** `K60TlState` 做滞回（`K60ThermalService.cpp:239-249`）。
- **只读性**：全文件没有任何对 `volatile` 的写、没有 `setInterruptType`/`registerInterrupt`、没有
  `notify_post`（本树也不导出 `notify_post`，见 §5）。这一点由 `grep -nE 'volatile[^;]*=' ` 与
  `llvm-nm -u` 双向核验。

## 5. 编译配方与符号核验

`scripts/build-thermal-kext.sh` 的存在理由（脚本头 `:1-33` 自述）：`K60ThermalService.cpp` 是内核
C++，既不能用 `build-thermal-driver.sh` 的 freestanding 配方（那里没有 IOKit 头），也不能用未打补丁的
feed（`osfmk/arm64/proc_reg.h` 末尾是 `#error processor not supported`，PONG 分支只存在于
`patches/xnu/zzzz-pong-machine.patch:120-131` 打过的树里）。它需要的四样东西全部来自一棵**已构建**的
本板 XNU 树（默认 `/mnt/e/hackios/UniXNU/out/mondrian/tree`）：

| 用途 | 路径 |
|---|---|
| isysroot（真 Kernel.framework 头） | `.cache/fakeroot` |
| 源码头（已打 PONG 补丁） | `.cache/xnu-work` |
| 生成头（含 MIG 输出） | `build/xnu/ios-obj/EXPORT_HDRS` |
| 内核导出符号表 | `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp` |

最后一行才是这个脚本的意义：**剩下的每个未定义符号都必须在 `all-kpi.exp` 里**，否则只会在内核链接
时失败（P-181/P-182、P-190：验符号不验文件名）。

踩过的四个坑（都写进脚本注释）：`-fno-c++-static-destructors -fno-use-cxa-atexit` 才能消掉内核不导出的
`___cxa_atexit` / `___dso_handle`；`llvm-nm` 对 Mach-O 加前导下划线，比对要同时试 `sym` 与 `_sym`；
`all-kpi.exp` 带缩进和 `#` 注释，必须先归一化再 `grep -qxF`；C 源必须用 `clang` 不能用 `clang++`
（否则按 C++ mangle，归档里就找不到 `_k60tsens_read_controller`）。

**构建结果（2026-11-14，可复现）**：

```
build-thermal-kext: defined 160 symbols, all 10 required ones present
build-thermal-kext: 219 kernel imports, all exported by the kernel
build-thermal-kext: archive .../build/thermal-kext/libK60ThermalKext.a (8fa4bf72e931d3d79e66d281ed43849ab129e36fd0a71b0a272d0fcd6dfbb8d4)
build-thermal-kext: BUILD OK
```

10 个必需符号：`_k60_thermal_start`、`_ZN16K60ThermalSensor5startEP9IOService`、
`_ZN16K60ThermalSensor13sampleDomainsEPi`、`_ZN16K60ThermalSensor18setPhysicalWindowsEyy`、
`_ZN24AppleSMCSensorDispatcher7publishEP16K60ThermalSensorS1_`、
`_ZN34AppleSMCSensorDispatcherUserClient14externalMethodEjP25IOExternalMethodArgumentsP24IOExternalMethodDispatchP8OSObjectPv`、
`_ZN34AppleSMCSensorDispatcherUserClient12initWithTaskEP4taskPvj`、`_k60tsens_read_controller`、
`_k60tl_step`、`_k60tl_input_of_sensor`。清单写在 `build/thermal-kext/thermal-kext-manifest.json`
（`build/` 已被 `.gitignore` 忽略，产物不入库，脚本入库）。

> 符号名必须写真实的 mangled 形式：`sampleDomains` 是 `13sampleDomains`（13 = 名字长度），
> 写成 12 会报 missing；`publish` 两个参数是 `...EP16K60ThermalSensorS1_`。这两个坑都实际踩过。

## 6. 还差什么（step ⑤ 为何仍是 done = false）

1. ~~没有内核链接行~~ **已落地（2026-11-14，Lead，位置修正过一次）**：`scripts/build-xnu-4k-baseline.sh:1137-1148`
   新增 `XNU_PONG_THERMAL` 块，默认关闭；打开时调 `scripts/build-thermal-kext.sh --no-export-list` 并对
   `build/thermal-kext/libK60ThermalKext.a` 做 `-Wl,-force_load` + 进 `PLATFORM_DEPENDENCIES`。
   第一版误插在 `KERNEL_EXTRA_ARCHIVES` 区（`if XNU_SOURCE_CORECRYPTO14 = 1` 的死分支里，本板该值为 `n`），
   等于永不生效；现在落在活的 `PLATFORM_ARCHIVES` 块内，见 `07-INTEGRATION.md` §3。
   同一变量还串起四环：`configs/mondrian_defconfig:63` → `build-ios16-pong-macos.py:148-151` →
   `build-pong-platform-macos.py:41` → 本链接行；缺任何一环，钩子都会被 `#if` 静默编掉。
   链接行的 `-force_load` 语义已用 ld64 部分链接离线验证（`scripts/build-thermal-link-check.sh`）。
2. ~~没有启动钩子~~ **已落地（2026-11-14，Lead）**：`drivers/ArmDTPlatform/ArmDTPlatform.cpp:27-31`
   声明 `extern "C" int k60_thermal_start(void);`，`:232-233` 在 `registerService()` 与 adreno 钩子之后
   调用它，两处都在 `#if XNU_PONG_THERMAL` 内。**没有走 `patches/thermal/`**：全仓没有 applier 引用
   该目录，写一个永不应用的补丁就是 `docs/research/wifi/GAP-ANALYSIS.md:65` 记录过的坑。
   两种开关组合都编译通过，`XNU_PONG_THERMAL=0` 时二进制里没有 `k60_thermal` 引用。
3. ~~ADT 里没有 tsens 节点~~ **已落地（2026-11-14，Lead）**：`scripts/make-pong-adt.py:217-234` 新增
   `thermal-sensor@c263000` / `@c265000` 两个节点，`:266` 插进 `arm-io` 子节点列表；因为
   `ranges`（`:24-25`，`0x17000000 + 0x02000000`）不覆盖 `0xc263000`，节点用绝对地址属性
   `pong,tsens-tm-base` / `pong,tsens-srot-base` 而不是 `reg`，与 `pong-touch` / `pong-buttons` 的既有
   范式一致。生成器实跑 12600 B / 15 节点，两个新节点的属性值已用 `parse_adt` 核对。
4. **没有上机**：设备 6033dbec 在 2026-11-14 12:05 之后从 adb 掉线，现在只在 `fastboot devices` 里
   （bootloader 态）。铁则 4 + 运行时规则：**没有用户明确同意不 boot**，故 `k60_thermal_start` 从未执行过。
   这是 §6 现在唯一剩下的缺口。

上机后的第一条判定证据：启动日志应出现
`K60Thermal: tsens0 mapped, 16 sensors, version <a>.<b>.<c>`（`K60ThermalService.cpp:129-133`）、
两行（两个控制器），然后是 `K60Thermal: dispatcher published`（`:235`）与
`K60Thermal: service started, 2 controllers, 32 sensors`（`:413-414`）。
若 SROT 映射失败会先打印 `K60Thermal: window 1 at 0x... did not map`（`:92-95`）——
这比"device not enabled"更早一步。

> 上面第 1～3 条的逐条落地清单（链接行插入点、钩子代码、ADT 节点与 ranges 缺口、
> 以及冷树上 `all-kpi.exp` 不存在时 `build-thermal-kext.sh --no-export-list` 的由来）见
> `docs/research/thermal/07-INTEGRATION.md`。
