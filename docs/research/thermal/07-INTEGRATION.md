# 07 内核集成（已落地）

> 本文原先把 `06-KEXT-SERVICE.md` §6 列出的三个集成缺口——内核链接行、启动钩子、ADT tsens 节点——
> 写成改动清单。2026-11-14 这三处已由 Lead 直接落进仓库源码（写作用域是 advisory，见 §7），
> 并顺带解决了一个构建顺序上的硬约束：冷树上 `EXPORT_HDRS` 与 `all-kpi.exp` 都还不存在。
> §1 是落地后的现状，§2-§5 保留原方案（含落地时的实际差异），§6 是仍未满足的验收判据。

## 1 现状（2026-11-14 落地后）

| 项 | 状态 | 出处 |
| --- | --- | --- |
| 只读驱动 / 压力等级 / IOKit 服务 | 已写，离线编译并核验符号 | `build/thermal-kext/libK60ThermalKext.a`，sha256 `8fa4bf72e931d3d79e66d281ed43849ab129e36fd0a71b0a272d0fcd6dfbb8d4`，160 defined / 10 required / 219 imports |
| 内核链接行 | **已落地** | `scripts/build-xnu-4k-baseline.sh:934-943`，`XNU_PONG_THERMAL=1` 时调 `build-thermal-kext.sh --no-export-list` 并 `-Wl,-force_load` |
| 启动钩子（`k60_thermal_start` 的调用者） | **已落地** | `drivers/ArmDTPlatform/ArmDTPlatform.cpp:27-31`（声明）与 `:232-233`（`registerService()` 之后调用） |
| ADT tsens 节点 | **已落地** | `scripts/make-pong-adt.py:217-234`（两个节点）+ `arm-io` 子节点列表；生成 12600 B / 15 节点 |
| Info.plist 两条 personality | 已写，ADT 节点已存在故可命中 | `drivers/PongThermal/Info.plist`（`thermal-sensor@c263000` / `@c265000`） |

服务本身不依赖 ADT：`K60ThermalSensor::mapWindow()` 优先用 `kK60TsensWindows` 常量表 +
`IOMemoryDescriptor::withPhysicalAddress()` 自建两个窗口；只有在实例由 ADT nub 拉起时才从
`pong,tsens-tm-base` / `pong,tsens-srot-base` 两个属性读基址（`K60ThermalService.cpp` §start）。
所以 ADT 节点既让 `ioreg` 能看到 `thermal-sensor@c263000`，也给匹配路径提供了不依赖 `reg` 的基址。

## 2 构建顺序（硬约束）

`scripts/build-xnu-4k-baseline.sh` 的相关顺序：

- `:221-252` `installhdrs` → 生成 `.cache/fakeroot`（真 Kernel.framework Headers/PrivateHeaders）
- `:896` `KERNEL_EXTRA_ARCHIVES="-L$KERNEL_SDKROOT/usr/local/lib/kernel -lfirehose_kernel $CRYPTO_ARCHIVE"`
- `:929-932` `ARM_DT_ARCHIVE` 的 `-Wl,-force_load` 范式（每个归档都紧跟一条 `KERNEL_ARCHIVE_DEPENDENCIES`）
- `:1073-1074` `LD_KERNEL_ARCHIVES` / `XNU_EXTERNAL_KERNEL_ARCHIVES` 传给 make
- `:1255` `make -C .cache/xnu-work build`

现有归档（ArmDTPlatform、ArmCpu、NativeUfs …）由 macOS 侧的 `scripts/build-k60-platform-archives.py` 生成：
该脚本 `:50` 的表格逐项调 `build-pong-platform-macos.py`，而后者 `:31` 用 `xcrun --sdk iphoneos`
（`:22-23` 虽写 Darwin/Linux，实际需要 Xcode）。WSL 上的等价物就是本线的
`scripts/build-thermal-kext.sh`：同一套 clang（`/opt/unixnu-linux/llvm/bin/clang++`）+ `.cache/fakeroot`
+ `.cache/xnu-work` + `EXPORT_HDRS`，产出的归档同样是 Darwin 格式。

**硬约束**：`all-kpi.exp` 是构建产物
（`build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/all-kpi.exp`），源码树里没有 `*.exp`
（在 `.cache/xnu-work` 下 `find -name '*.exp'` 零命中），所以冷树第一遍构建时它不存在，
而 `build-thermal-kext.sh` 原先把它当必需输入。

因此脚本新增 `--no-export-list`：缺失时跳过导入预检并打印警告，manifest 里
`kernel_imports_all_exported` 记为 `"unchecked"`。实测两种模式产出的归档 sha256 完全一致
（`8fa4bf72…`，预检不改变字节）；正式链接时以 ld 为准，预检只是提前报错的手段。

**第二个冷树依赖（落地时才发现）**：`build/xnu/ios-obj/EXPORT_HDRS` 同样是 xnu make 的产物
（`:1255` 才生成），在 `:938` 调用本线脚本时并不存在。实测证明只用 `.cache/fakeroot` 的
`Kernel.framework/Versions/A/{Headers,PrivateHeaders}` 就能编译同三个源（改动前后归档字节一致），
于是 `build-thermal-kext.sh` 把 `EXPORT_HDRS` 降级为可选：缺失（或 `K60_XNU_EXPORT_HDRS=none`）时
打印一行 WARNING 并用 `$FR_INCLUDES` 顶上，`EH_INCLUDES` 为空。两种模式实测都是
160 defined / 10 required / 219 imports，且 **sha256 相同**（`8fa4bf72e931d3d79e66d281ed43849ab129e36fd0a71b0a272d0fcd6dfbb8d4`）。

## 3 改动一：链接行

在 `scripts/build-xnu-4k-baseline.sh` 的 `KERNEL_EXTRA_ARCHIVES` 初值（`:896`）之后、其它 `if` 分支之间插入：

```bash
if [ "${XNU_PONG_THERMAL:-0}" = 1 ]; then
    K60_XNU_TREE=$ROOT bash "$ROOT/scripts/build-thermal-kext.sh" --no-export-list
    THERMAL_ARCHIVE=$ROOT/build/thermal-kext/libK60ThermalKext.a
    test -f "$THERMAL_ARCHIVE"
    KERNEL_EXTRA_ARCHIVES="$KERNEL_EXTRA_ARCHIVES -Wl,-force_load,$THERMAL_ARCHIVE"
    KERNEL_ARCHIVE_DEPENDENCIES="$KERNEL_ARCHIVE_DEPENDENCIES $THERMAL_ARCHIVE"
fi
```

要点：

- 位置必须在 `installhdrs`（`:221-252`）之后，因为脚本要读 `.cache/fakeroot` 与 `EXPORT_HDRS`；`:896` 满足。
- 默认 `XNU_PONG_THERMAL=0`，不改变现有内核（对照组的字节应完全一致，见 §6 第 1 步）。
- `-Wl,-force_load` 不能省：静态归档里没有其它目标文件引用 `k60_thermal_start` 时，ld 不会拉入成员，
  这正是 P-190 说的"归档必须验符号"的另一半——链接也要强制加载。

### 3.1 已离线验证这条链接行

`scripts/build-thermal-link-check.sh`（本线新增）用 ld64 的 `-r` 部分链接把这条链接行的语义先证明一遍，
不需要整棵内核重编：

- 造一个五行 caller（`extern "C" int k60_thermal_start(void);` + 一个调用它的探针函数），
  等价于 §4 的 ArmDTPlatform 钩子——真实钩子所在文件不在本线写作用域，故用同符号的替身。
- 对照组：`ld -r caller.o` 不加 `-force_load` → `_k60_thermal_start` 仍然未定义（证明这个标志是必需的，
  不是装饰）。
- 实验组：`ld -r caller.o -force_load libK60ThermalKext.a` → `_k60_thermal_start` 已解析，
  且合并对象里 218 个归档导入逐个在 `all-kpi.exp` 内，0 个未解析。

实测输出（2026-11-14，`build/thermal-link-check/`）：

```
build-thermal-link-check: control OK (k60_thermal_start still undefined without the flag)
build-thermal-link-check: -force_load resolved k60_thermal_start
build-thermal-link-check: 218 archive imports, all in all-kpi.exp
build-thermal-link-check: LINK OK
```

一个附带观察（重要，避免过度解读这个判据）：`ArmDTPlatform.cpp` 自己的 237 个导入里有 51 个
`IOPlatformExpert::` 成员**不在** `all-kpi.exp`（例如 `__ZN16IOPlatformExpert14getChipSetTypeEv`），
而该归档早就挂在内核链接行里、内核也构建成功。原因：`all-kpi.exp` 是**给 kext 用的导出白名单**，
而 `-force_load` 进来的归档是**内核本体的一部分**，它的导入由内核自己的目标文件解析，不受该白名单约束。
所以"218 个导入全在 all-kpi.exp"是一个**比链接器要求更严**的充分条件（这也是当初选它的原因：
离线就能给出结论），但不能反过来说"不在表里就一定链接失败"。

## 4 改动二：启动钩子（已落地）

落地位置：`drivers/ArmDTPlatform/ArmDTPlatform.cpp:27-31`（声明，紧随 `pong_adreno_start_optional` 的 `#endif`）
与 `:232-233`（`configure()` 内、`registerService()` 与 adreno 钩子之后、`return true` 之前）。
两种开关组合都编译通过：`XNU_PONG_THERMAL=0` 时 `llvm-nm -u` 看不到 `k60_thermal` 引用，`=1` 时看到 1 个。

原方案文字（保留）：

`drivers/ArmDTPlatform/ArmDTPlatform.cpp:23` 之后加：

```cpp
#if XNU_PONG_THERMAL
extern "C" int k60_thermal_start(void);
#endif
```

在 `configure()` 里 `registerService()` 之后（现有 `:216` `pong_cpu_start` 与 `:224-226` adreno 调用之后）加：

```cpp
#if XNU_PONG_THERMAL
    if (k60_thermal_start() != 0) {
        IOLog("ArmDTPlatform: k60 thermal service did not start\n");
    }
#endif
```

范式与 `patches/wifi/0005-drivers-ArmDTPlatform-pong-wifi-hook.patch:1-25` 相同（同一文件、同一位置、
`#if XNU_PONG_*` 包住）。**注意**：`patches/wifi` 至今没有被任何 series/applier 引用
（`docs/research/wifi/GAP-ANALYSIS.md:65`），所以这次不要再走"只写补丁"的路——
`drivers/ArmDTPlatform` 是仓库源码，直接改仓库文件才有效。

## 5 改动三：ADT 节点（已落地，改用绝对地址属性）

`scripts/make-pong-adt.py:217-234` 新增两个节点，`:266` 处把它们插进 `arm-io` 子节点列表
（顺序 gic / touch / pong-buttons / tsens0 / tsens1 / 可选 ufs）：

```text
thermal-sensor@c263000  compatible=qcom,tsens-v2  pong,tsens-tm-base=0xc263000  pong,tsens-srot-base=0xc222000  pong,tsens-controller=0  #qcom,sensors=16  #thermal-sensor-cells=1
thermal-sensor@c265000  compatible=qcom,tsens-v2  pong,tsens-tm-base=0xc265000  pong,tsens-srot-base=0xc223000  pong,tsens-controller=1  #qcom,sensors=16  #thermal-sensor-cells=1
```

**与原方案的差异**：没有用 `reg`，改用绝对地址属性。原因：`ranges` 是
`<0, 0x17000000, 0x02000000>`（`:24-25`），**不覆盖** `0xc263000`，写 `reg` 只会得到一条无法翻译的
地址；而本仓 `pong-touch` / `pong-buttons` 已经确立了"绝对元数据属性"的范式
（`Absolute metadata avoids an incomplete arm-io interrupt/reg mapping`）。服务侧对应读取这两个属性
（见 §1 末段），所以节点有没有 `reg` 都不影响功能。

实跑验证：`python3 scripts/make-pong-adt.py --dram-size 0x300000000 --output /tmp/adt-thermal.adt`
→ `Pong ADT: 12600 bytes; cpu_count=1; dram=0x300000000`（改前 11944 B / 13 节点）；
`pong_adt_contract.parse_adt` 解析出 15 个节点，两个新节点的 `compatible` 均为 `b'qcom,tsens-v2\x00'`，
`pong,tsens-tm-base` 分别为 `0xc263000` / `0xc265000` 的小端 8 字节；生成器内部的 `audit_adt` 照常通过。
上机后仍需 `ioreg -l | grep thermal-sensor` 确认 `ArmDTPlatform: published DT nub ...` 两条日志。

## 6 验收判据

1. **对照组**：`XNU_PONG_THERMAL=0` 构建一次，产物与上次成功构建逐字节一致（至少 sha256 相同）。
2. **链接**：`XNU_PONG_THERMAL=1` 构建，ld 不报 unknown symbol；`strings kernel.macho | grep -c 'K60Thermal: '` ≥ 3
   （短标记思路同 P-170）。
3. **上机**（需 Lead 批准 ⑦⑧ + 设备 6033dbec + 用户明确同意，入口只能是 `scripts/flash.sh`）：
   串口依次出现
   `K60Thermal: tsens0 mapped, 16 sensors, version a.b.c` /
   `K60Thermal: dispatcher published` /
   `K60Thermal: service started, 2 controllers, 32 sensors`。
   判定只读 `capture.json` 的 `verdict` / `panicMarker`（铁则 7），不用 logstat 的 panic 计数。
4. **单变量**：一次只开一个变量（P-178）。`XNU_PONG_THERMAL`、ADT 节点、Info.plist 三件事不要同轮上机。

## 7 归属与落地记录

| 改动 | 文件 | 写作用域归属 | 状态 |
| --- | --- | --- | --- |
| 链接行 | `scripts/build-xnu-4k-baseline.sh:934-943` | 构建线 / Lead | 已由 Lead 落地（2026-11-14） |
| 启动钩子 | `drivers/ArmDTPlatform/ArmDTPlatform.cpp:27-31`、`:232-233` | DT 平台线 / Lead | 已由 Lead 落地（2026-11-14） |
| ADT 节点 | `scripts/make-pong-adt.py:217-234`、`:266` | DT 平台线 / Lead | 已由 Lead 落地（2026-11-14） |

thermal 线的写作用域只有 `drivers/PongThermal/**`、`docs/research/thermal/**`、`patches/thermal/**` 与
`scripts/build-thermal*.sh`、`scripts/tests/test-k60-thermal*.c`，以上三项均不在其中；
写作用域是协作约定而非锁，Lead 已按 task-3 直接改仓库源码落地（不走"只写补丁"的路，
理由见 §4 末段）。三项改动都只由 `XNU_PONG_THERMAL` 一个开关控制，默认关闭，不影响现有内核。
