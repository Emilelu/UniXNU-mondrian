# 08 内核内建 tsens 驱动（patch 落地）

> 2026-11-14。`06-KEXT-SERVICE.md` 走的是 kext 归档路线（`drivers/PongThermal/*.cpp` + `-force_load`），
> 需要 `XNU_PONG_THERMAL=1` 整树构建、链接行与启动钩子三处集成。本篇是另一条路线：把只读驱动
> 直接做成 `bsd/dev/pong_thermal.c`，用补丁进树、用 `bsd/conf/files` 登记、用 `bsd_init.c` 起线程。
> 两条路线共享同一份寄存器语义与同一张 32 项传感器表，区别只在「谁把它链接进内核」。

## 1 为什么还要一条 in-tree 路线

| 维度 | kext 归档（06/07 篇） | in-tree 驱动（本篇） |
| --- | --- | --- |
| 进入内核的方式 | `-Wl,-force_load` 归档 + 链接行 | 补丁把 `.c` 放进 `bsd/dev/`，`conf/files` 编译进内核 |
| 需要的开关 | `CONFIG_XNU_PONG_THERMAL=y` 整树重建 | 无开关，补丁在就编 |
| 需要的集成改动 | 链接行、启动钩子、ADT 节点（3 处，跨线） | 只有补丁本身（1 处，本线写作用域内） |
| 服务能力 | 发布 `mTPL` 给 `thermalmonitord`（IOKit user client） | 无，只有内核日志与域温度 |
| 依赖 macOS 侧 | 是（归档由 Xcode SDK 编） | 否（CLT clang 即可，P-170） |

所以 in-tree 路线是「先让 32 路读数在真机上可见」的最短路径：它不需要 Lead 级的三处集成，
也不需要 iPhoneOS SDK。压力等级已在这一层发布（§3）；`mTPL` 仍归 kext 路线。

## 2 补丁结构（`patches/xnu/0617-k60-thermal-tsens.patch`，9 段）

| 段 | 目标 | 内容 | hunk 头 |
| --- | --- | --- | --- |
| 1 | `bsd/conf/files` | 在 `bsd/dev/pong_buttons.c\t\t\tstandard` 之后插四行：`pong_thermal.c`、`pong_thermal_level.c`、`pong_thermal_zones.c`、`pong_thermal_pm.cpp` | `@@ -400,6 +400,10 @@` |
| 2 | `bsd/kern/bsd_init.c` | 在 `\t\tpong_buttons_init();` 之后插 `K60_PONG_LOCAL` 注释 + `extern void pong_thermal_init(void);` + 调用 | `@@ -1161,6 +1161,10 @@` |
| 3 | `bsd/dev/pong_thermal.c` | 新文件，312 行（母本 `drivers/PongThermal/pong_thermal.c` 的逐字副本） | new file mode 100644 |
| 4 | `bsd/dev/pong_thermal_level.c` | 新文件，131 行（母本 `K60ThermalLevel.c`：五域等级算术） | new file mode 100644 |
| 5 | `bsd/dev/pong_thermal_zones.c` | 新文件，199 行（母本 `K60ThermalZones.c`：DTS 自己的 32 个 zone 的被动档） | new file mode 100644 |
| 6 | `bsd/dev/pong_thermal_pm.cpp` | 新文件，116 行（母本 `pong_thermal_pm.cpp`：发布层） | new file mode 100644 |
| 7 | `bsd/sys/pong_thermal.h` | 新文件，198 行（母本 `K60ThermalKernel.h`） | new file mode 100644 |
| 8 | `bsd/sys/pong_thermal_level.h` | 新文件，80 行（母本 `K60ThermalLevel.h`） | new file mode 100644 |
| 9 | `bsd/sys/pong_thermal_zones.h` | 新文件，97 行（母本 `K60ThermalZones.h`：zone 表的数据结构） | new file mode 100644 |

第 6 段是**本树 `bsd/conf/files` 里第一个 `.cpp`**。构建系统本来就支持：`makedefs/MakeInc.rule:423-428`
的 P_RULE 注释写明「generate .co from .cp or .cpo from .cpp」，`SETUP/config/mkmakefile.c:252-254`
处理 `%CXXFILES` 时只比较文件名末字符，`bsd/conf/Makefile.template:72` 就有 `%CXXFILES` 钩子
（与 `iokit/conf/Makefile.template:54` 同构，`iokit/conf/files:13-22` 已有 10 条 `.cpp`）。
C++ 编译同时带 `CFLAGS` 与 `CXXFLAGS`（`MakeInc.rule:426`），所以 `-DAPPLE -DKERNEL -DXNU_KERNEL_PRIVATE`
与 `-std=gnu++1z -fapple-kext`（`MakeInc.def:571`）都在。

`patches/xnu/series` 第 230 行登记本补丁，排在 `0616-k60-init-legacy-helper.patch` 之后 ——
因为它的两个锚点（`pong_buttons.c` 那行、`pong_buttons_init()` 那行）由**更早的补丁**生成，
必须等它们全部落地后本补丁才能干净应用。

### 2.1 为什么锚点能用（P-171 的边界）

P-171 说「改构建期文件的补丁，锚点必须来自代码仓库里的稳定源」，不能来自 `.cache/xnu-work`。
本条补丁的两个锚点都是**补丁自己生成的稳定行**：`bsd/dev/pong_buttons.c` 由按键线补丁加入，
`pong_buttons_init()` 由同一个补丁加入，两者都写死在 series 里、每次构建都从 `refer/xnu` 干净 clone
再按序应用，因此它们在下一次构建里必然出现且字节相同。这与 P-171 的失败案例（锚在
「上一次成功构建后的树」的随机行）不是一回事。

**第一次尝试的教训（已修正）**：最初的 hunk 锚在 `bsd/dev/pong_fat.c` 之后，而那行不是 series 的产物 ——
它是 `K60_CONF_FILES_HOOK`（`build-xnu-4k-baseline.sh:11-19`）在 format-1 构建路径里追加的，
build-strict 走的 unixnu 路径根本不跑该 hook。结果 `git apply` 在 `bsd/conf/files:406` 直接失败，
日志 `error: patch failed: bsd/conf/files:406 / patch does not apply`。锚点必须选 series 内补丁确实写入的行。

### 2.2 应用链

`build-strict.sh` → `unixnu build kernel` → `scripts/unixnu/patches.py:prepare()`：
按 `board.toml:20` 的 `kernel.patch_series = ["device:patches/xnu/series"]` 逐行解析，
从 `refer/xnu` `git clone --shared` 建 `.cache/xnu-work`，再逐个 `git apply`（**无 fuzz 回退**）。
因此 hunk 上下文必须精确 —— 本地验证方式：在一棵「已打完 229 个补丁」的树上跑
`git apply --check`（本补丁 2026-11-14 实测 `APPLY_CHECK_OK`）。

## 3 驱动本体（`bsd/dev/pong_thermal.c`，312 行）

```
pong_thermal_init()                        // bsd_init.c 在 pong_buttons_init() 之后调用
  ├─ PE_parse_boot_argn("pong_thermal", &enabled, sizeof(enabled))   // 默认 1，=0 只打日志
  ├─ ml_io_map(TM 0x0c263000, 0x1000) / ml_io_map(SROT 0x0c222000, 0x1000)   // tsens0
  ├─ ml_io_map(TM 0x0c265000, 0x1000) / ml_io_map(SROT 0x0c223000, 0x1000)   // tsens1
  ├─ 读 SROT_HW_VER(0x000) / SROT_CTRL(0x004)  →  ver=a.b.c ctrl=0x… enabled=0/1
  ├─ pong_thermal_dump()                   // 2 行控制器行 + 32 行传感器行
  └─ kernel_thread_start(pong_thermal_worker) → thread_deallocate

pong_thermal_worker()                      // 1 s 一轮
  ├─ clock_interval_to_deadline(1000, NSEC_PER_MSEC, &deadline)
  ├─ assert_wait_deadline((event_t)pong_thermal_controllers, THREAD_UNINT, deadline)
  ├─ thread_block(THREAD_CONTINUE_NULL)
  ├─ 每轮重采样；任一分域温度变化 ≥ 1 ℃ 或满 30 轮时打一行 little/big/gpu/npu/ddr
  ├─ level = k60tl_step(&state, domains)                 // 五域等级（粗视图，只进日志）
  ├─ zone_level = k60tz_step(&zone_state, milli_c)       // DTS 32 zone 的等级 0..3（发布这个）
  └─ pong_thermal_pm_publish(zone_level)                 // 每轮都调
```

发布层（`bsd/dev/pong_thermal_pm.cpp`，C++，本树 `bsd` 的第一个 `.cpp`）：

```
pong_thermal_pm_publish(level)             // 由 worker 每轮调用，不在 bsd_init 里调一次
  ├─ 与上次发布过的等级相同 → 直接返回（去重，等级不变不打扰 root domain）
  ├─ root = IOService::getPMRootDomain();  NULL → 返回（此时 IOKit 还没起来，不是错误）
  ├─ key 懒创建一次：OSSymbol::withCStringNoCopy(kIOPMThermalLevelWarningKey)
  ├─ value = (uint32_t)level               // 0..3，板子自己的档位，见下表
  ├─ number = OSNumber::withNumber(value, 32)
  ├─ root->systemPowerEventOccurred(key, number)   // 唯一的 thermal 入口
  └─ number->release(); printf("PongThermal: level %s (%u) published as %s=%u")
```

**为什么必须每轮调用而不是在 `pong_thermal_init` 里发一次**：`bsd_init` 在 `bsd/kern/bsd_init.c:1166-1167`
调 `pong_thermal_init()`，而 `IOKitBSDInit()` 在 `:1325` —— 中间隔着整个 `bsd_autoconf`。
`gRootDomain` 由 `IOPMrootDomain::start()` 赋值（`iokit/Kernel/IOPMrootDomain.cpp:1519`、`:1526`），
所以 init 那一刻 `getPMRootDomain()` 必然是 NULL。第一次成功的发布就是发布层真正上线的时刻。

**发布的数值是板子自己的档位 0..3，不再映射到 Apple 的 0/5/100/110**（决策与理由见
`LEVEL-MAP.md` §4）。`0..3` 直接来自 `bsd/dev/pong_thermal_zones.c` 里 DTS 的被动 trip：
32 个 tsens zone 各带 2 或 3 档被动 trip（同温度的重复 trip 去重后），最高 zone 胜出。

| 板子档位 | 含义 | 发出去的值 | `thermalWarningState` |
| --- | --- | --- | --- |
| 0 | 没有任何被动 trip 被越过 | 0 | 0 |
| 1 | 某个 zone 的最低温被动 trip 被越过 | 1 | 0（只进 "Power Status" 字典并广播，`IOPMrootDomain.cpp:8172-8188`） |
| 2 | 某个 zone 的第二档被越过 | 2 | 0（同上） |
| 3 | 某个 zone 的第三档被越过 | 3 | 0（同上） |

只有 100 与 110 会改状态机（`IOPMrootDomain.cpp:8133-8134`），而这两个值要求「CPU 到 110/115/125℃」
与「GPU/NPU 到 95℃、DDR 到 90℃」同时成立；DTS 的档位彼此并不齐（95℃ 在 GPU 是第 1 档、在 CPU 只是第 2 档；
110℃ 在 CPU 是第 1 档、在 GPU 是第 3 档），硬映射就得在本层发明一条跨传感器的混合规则。
所以这一版发 0..3：**纯遥测，不触发任何动作**。`LEVEL-MAP.md` §4 记录了什么条件下才值得改发 100/110。
**这一层只上报**：不装执行器、不写时钟、不碰 trip —— 决策记录见 `TRIP-DESIGN.md` §3.5。

寄存器语义与 `06` 篇完全一致（同一张 32 项表、同一套解码）：
`TM_Sn_STATUS(n) = 0xa0 + 4n`，`LAST_TEMP = [11:0]` 符号扩展后 ×100 得毫摄氏度，
`VALID = bit21`，`SROT_HW_VER` 的 major/minor/step 拆位见 `K60ThermalKernel.h`。
**全程只读**：没有任何对映射窗口的写、没有中断、不编程 trip、不碰 SROT_CTRL。

### 3.1 日志串（上机判据）

```
PongThermal: tsens0 tm=0xc263000 srot=0xc222000 ver=1.2.3 ctrl=0x1 enabled=1
PongThermal: tsens0[0] aoss-0 zone24 54900 mC
…（32 行）…
PongThermal: little=60000 big=67000 gpu=53000 npu=49000 ddr=52000 mC
```

串口里 `grep -c 'PongThermal: '` 应 ≥ 36（2 控制器 + 32 传感器 + ≥2 轮域温度），
并且第一次成功发布后还会出现下面这行（等级变化时各出现一次）：

```
PongThermal: level nominal (0) published as Thermal_Level_Warning=0
```

判据：出现任意一行 `published as Thermal_Level_Warning=` 即证明发布层接通了 root domain；
同等级只发一次是设计（`pong_thermal_pm.cpp:87-89` 的 `have_last && level == last` 直接 return），
所以冷机 208 轮采样恰好只有一条；`CRITERIA.toml` 的 `published.line` 因此写 `min = 1, max = 1`，
多一条才是去重坏了；
若串口里 36 行都在、却一行 `published as` 都没有，说明 `getPMRootDomain()` 一直是 NULL
（IOKit 没走到 `IOPMrootDomain::start`），这本身就是一条有价值的结论。

## 4 离线核验（本轮已做）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 纯算术单测 | `cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongThermal -o build/thermal/test-kernel scripts/tests/test-k60-thermal-kernel.c` | `TESTS OK 264` |
| 既有解码单测 | 同法 `test-k60-thermal-tsens.c` | `TESTS OK 16` |
| 压力等级单测 | 同法 `test-k60-thermal-level.c` | `TESTS OK 72` |
| 等级阶梯单测 | 同法 `test-k60-thermal-zones.c` | `TESTS OK 478` |
| 补丁 ↔ 母本一致性 | `python3 scripts/check-thermal-kernel-patch.py` | `thermal kernel patch: OK (14 checks)` |
| 补丁可应用性 | 在已打完 229 个补丁的树上 `git apply --check` | `APPLY_CHECK_OK` |
| 上机判据可机读 | `python3 scripts/check-thermal-log.py --self-test` | `self-test OK`（干净日志过、每处改动挂） |
| 判据对真机日志 | `python3 scripts/check-thermal-log.py --log /mnt/e/iOS Port/Work/evidence/usblog-20261115-003922/console.log` | 17 过 / 4 挂，挂的正是 `level.line` 等只适用于 `thermal-20261115a` 之后的判据（该镜像还没有阶梯），脚本自己打出这条 note |

`check-thermal-kernel-patch.py` 做 14 项：从 patch 重建七个新文件并与 `drivers/PongThermal/`
母本逐字节比对；series 登记且为最后一行；`conf/files` 四条登记（含 `.cpp` 保留扩展名）；
`bsd_init.c` 的 extern 与调用都在；母本里没有「经映射指针的写」；发布层用的是
`systemPowerEventOccurred` + `kIOPMThermalLevelWarningKey` + `getPMRootDomain`、发的就是 level 本身，
且没有 `setFrequency` / `ml_io_map` / MSR 写 / trip 写（即没有偷偷变成执行器）；zone 表恰好 32 行、
每行档数 2 或 3、温度与滞回递增、tag 是 `tsens<控制器>[<索引>]`、不含 `mx-pe` 与 `isense_trim`
（这两个 zone 的 trip 不是温度）。任何一项不成立就退出非零。

## 5 仍未完成

1. ~~**从未构建过含本补丁的内核**~~ **已构建（2026-11-14 20:38）**：`build-strict.sh thermal-20261114c`
   在自己的构建树（`K60_DEVICE_INPUT=/opt/k60/trees/thermal-device`、`K60_OUT=/opt/k60/trees/thermal-out`）
   里跑通全链（八步门禁 30 项 → 补丁应用 230/230 → 内核 → 合规门禁 → payload → bootimg）：
   `kernel.macho` 54,173,696 B，sha256 `ed0bfe2327ea55244eb95b3313264404dd43fb1d4b0caa68846dc729853331d1`，
   `strings | grep -c 'PongThermal: '` = **10**（§3.1 预言的全部串都在），
   `llvm-nm` 有 `_pong_thermal_init`/`_pong_thermal_worker`/`_pong_thermal_sample`/`_pong_thermal_sensors`/
   `_pong_thermal_controllers` 五个符号；payload kernel sha256 `827797e6ae11174908c3c161b67a1c30614b8fb6fbabf0f1b4675f1eaebe935e`，
   boot.img sha256 `09a38cb7085eef1aa97bcf8810b5b456906dbc524cd21349638e8d51a3c952f1`，
   manifest `/mnt/e/iOS Port/Work/artifacts/thermal-20261114c/build-manifest.json`。
2. ~~**从未上机**~~ **已上机（2026-11-15 00:39，`thermal-20261114f`）**：
   `/mnt/e/iOS Port/Work/evidence/usblog-20261115-003922/console.log` 里有控制器行
   `PongThermal: tsens0 tm=0xc263000 srot=0xc222000 ver=2.8.0 ctrl=0x9d67fff9 enabled=1`（行 215）
   与 `tsens1 …`（行 225）、31 行传感器读数（40–43℃）、208 行五域温度行（随负载从 41–45℃ 升到 56℃），
   以及 1 行 `PongThermal: level nominal (0) published as Thermal_Level_Warning=0`（行 340）。
   `tsens0[3] cpuss-2 zone27` 这一行没有出现，**已查清是控制台丢行，不是传感器故障**：
   对该 console.log 逐字节搜索，`cpuss-2`、`tsens0[3]`、`zone27` 三个串的计数都是 0，
   既不是行被截断，也没有 `no-valid-reading` 行（那一串全文同样零命中）；原始字节里
   `tsens0[2] cpuss-1 zone26 42.2 C\n` 之后直接跟着 `Pong keys: PMIC windows mapped, …\n`
   （`pong_buttons.c` 的线程），再是 `tsens0[4] cpuss-3 zone28 41.0 C` —— 也就是
   `pong_thermal_init` 的 dump 序列与 `pong_buttons_init` 起的线程并发，
   `osfmk/console/serial_console.c:598` 的 `console_write_unbuffered` 不保证整行原子性，
   两行交错时丢的是整行。判据因此按「31 或 32 行」写（`CRITERIA.toml` 的 `sensor.lines`），
   丢哪一路由 `sensor.coverage` 报出来；下一轮若要确认，同时 grep `tsens0\[3\]` 与
   `no-valid-reading` 两个模式即可分清「丢行」与「无读数」；
   现场离最低档 90℃ 还差 34℃，所以 level 全程 nominal —— 这正是 `LEVEL-MAP.md` §5 要用
   `pong_thermal_bias` 验证 1/2/3 三档的理由。
3. ~~**没有压力等级**~~ **已有发布层，且已进内核**：三档压力等级经 `IOPMrootDomain::systemPowerEventOccurred`
   发布（`bsd/dev/pong_thermal_pm.cpp`，键 `kIOPMThermalLevelWarningKey`）。
   `build-strict.sh thermal-20261114f`（2026-11-15 00:17）跑通全链：`kernel.macho` 54,173,696 B、
   sha256 `e6557350fe37af880883ef3d24b3e20d2c5eff704e0f8c5e6975ade09b22ddce`，
   `strings | grep -c 'PongThermal: '` = **11**（比上一版多出的正是
   `PongThermal: level %s (%u) published as %s=%u`），`strings` 里同时出现
   `_pong_thermal_pm_publish` 与 `Thermal_Level_Warning`；payload kernel sha256
   `d923f2b2a059a96a737a7cc70288d8ed2f440f90c739c161f4b1694b15cd4bbc`、
   boot.img sha256 `adc796b63bad27821c491ddfb8ab7da8f6496b4ffd1b0b2e366ee6a301dc5d59`、
   manifest `/mnt/e/iOS Port/Work/artifacts/thermal-20261114f/build-manifest.json`。
   仍未验证的是**非 Apple kext 侧调用者上机是否无害**，以及 `thermalmonitord` 是否真会消费 —— 见 §7.4。
   注意这仍不是 `mTPL`：`mTPL` 是 SMC 键，需要 `AppleSMCSensorDispatcher`，属 kext 路线（`06`/`07` 篇）。
4. **等级阶梯层已进内核（2026-11-15 01:30，`thermal-20261115a`）**：`build-strict.sh` 全链再次跑通，
   `kernel.macho` 54,173,696 B、sha256 `153450de9196b99c395f38abc98f990ec0bb389a11196d02b37b8fd813a9a10a`，
   `strings | grep -c 'PongThermal: '` = **15**，其中新增 `PongThermal: level %u/3 %s (domains %u/3); closest %s %d.%d C, %d.%d C below tier %u`、
   同前缀的 `every tier crossed` 与 `no zone has a reading` 两个分支、以及 `PongThermal: bias %d mC added to every reading (validation only)`；
   `strings` 里还能找到 `_k60tz_table`/`_k60tz_step`/`_k60tz_closest`/`_k60tz_zone_level` 与 `_pong_thermal_pm_publish`。
   payload kernel sha256 `7bb198a0ef1a65217836952c69440c2279fb4d3b3777fae289c94b844c38090f`，
   boot.img sha256 `2b7973e5e150ac6c112274753bd08ec2c2011f7802411cae3918b890cc07fb25`，
   manifest `/mnt/e/iOS Port/Work/artifacts/thermal-20261115a/build-manifest.json`。
   **仍未上机验证等级随负载变化** —— `LEVEL-MAP.md` §5 给出 `pong_thermal_bias` 的 1/2/3 三档验证法与判据。
5. **没有 trip 编程与冷却设备**：本板 AP 侧 trip 全是被动 trip，且 `polling-delay` 多为 0，
   真要控温需要自己起策略，属后续工作。
6. **bias 三档验证只出了第一张（2026-11-15 03:00，`thermal-20261115b`）**：rebase 到 `main` 344e47d 后
   重新构建，`--kernel-arg pong_thermal_bias=85000` 写进 payload 的 `unixnu.toml`（`payload.py:130-133`，
   固件只读那份 TOML，P-159；镜像头 cmdline 不生效），因此**每一档都要单独构建**，不是拿一张镜像飞三次。
   `kernel.macho` 105,500,672 B、sha256 `d193f75c0ca64d239cb054128d3fff08d3e2a6da82528acecd0d635786255ff1`，
   `strings | grep -c 'PongThermal: '` 仍为 **15**（与 `thermal-20261115a` 相同），
   payload kernel `b6b860dd…`、boot.img `ba8b5c9e…`，manifest
   `/mnt/e/iOS Port/Work/artifacts/thermal-20261115b/build-manifest.json`（`kernel_args_requested` 里有
   `pong_thermal_bias=85000`）。**2026-11-15 13:52 已上机，判据全部达成**（结果见本条目末）。
   内核体积从 `thermal-20261115a` 的 54 MB 涨到 105 MB，原因是 rebase 后 defconfig 打开
   `CONFIG_XNU_GPU_ADDON=y`（Metal 插件 51,278,451 B 被 `.incbin` 进内核）与
   `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`；**这个体积在 4.5 GiB 窗口里已经跑过**——
   `gpu-20261114t`（`usblog-20261114-235957`）用的就是 105,476,096 B 的内核，日志里
   `K60RV 1 launchd[1] mem=4608 actual=4608 managed=4608`、`K60METAL deploy files=6/6 error=0`，
   `bootAccepted=true`。所以体积本身不是新风险。

**bias=85000 上机结果（2026-11-15 13:52–13:56，证据 `E:\iOS Port\Work\evidence\usblog-20261115-135227\`）**：
判定命令 `python3 scripts/check-thermal-log.py --profile bias-85000 --log <采集目录>/console.log`
→ **EXIT=0**，`22 passed, 0 failed, 0 advisory, 12 outside profile 'bias-85000'`，
`OK: every required criterion holds (profile bias-85000, 0 advisory)`。三行原文：

```
PongThermal: bias 85000 mC added to every reading (validation only)
PongThermal: tsens0[3] cpuss-2 zone27 43.0 C
PongThermal: level trapping (3) published as Thermal_Level_Warning=3
```

计数（我亲自复核，与判据一致）：控制器行 2、`polling 2 controllers every 1000 ms` 1、
传感器行 32/32（上一轮缺的 `tsens0[3] cpuss-2 zone27` 这次出现，丢行判断得到确认）、
域温度行 222、等级行 8 条（全部 `level 3/3 trapping (domains 3/3); closest aoss-0
127.6–134.3 C, every tier crossed`）、发布行 1 条（=3）、`crashed:.*backboardd` 0 条。
`capture.json`：`state=captured-budget-complete`、`bytes=252515`、panic/reset marker 均为
null；`boot.json`：`bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`。
构建的 series 是仓库 `patches/xnu/series` 的 225 行、sha256 `64056cd6…`（与
`K60_DEVICE_INPUT` 那份逐字节相同）。§7.4 的四个待确认由这轮（连同冷机
`thermal-20261114f`）回答了三项，见该节开头。

## 6 构建阻塞（2026-11-14，环境而非代码）

`build-strict.sh thermal-20261114a --fd touch-20261114a-cf4485712c29.fd` 在
`unixnu build kernel` 的合规门禁处被拒（`scripts/check-rules.py`），失败项与 thermal 代码无关：

| 失败项 | 原因 | 归属 |
| --- | --- | --- |
| `iron-2` / `hard-5` / `hard-10` / `hard-11` | 工作树有未提交文件（本轮正在提交的就是它们） | 提交后消失 |
| `iron-1` | 三个文件注释里写了 `/tmp/...` 路径，未进 `TMP-ALLOWLIST.toml` | **本轮已修**（改成引用 `01-SAME-HARDWARE.md §5` 与 `build/thermal/`） |
| `hard-8` / `P-156` | `k60-thermal` 与 `pong_thermal` 两个 boot-arg 未登记进 `BOOT-ARGS.md` | **本轮已修**（补两行，见 `BOOT-ARGS.md`） |
| `hard-38` | `.config` 与 defconfig 不一致 —— 从 `lead-out` 复制的旧 `.config` 里 `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`，本仓 defconfig 是 `not set` | **本轮已修**（删 `.config` 后用 `unixnu defconfig` 重生成） |
| `P-165` / `P-166` | 序列与构建输入不一致；`K60_DEVICE_INPUT` 未导出时比对的是共享目录 `usb-cdc-mainline/device`（含 BT 四个补丁） | 环境；设好 `K60_DEVICE_INPUT=/opt/k60/trees/thermal-device` 后 `patches/xnu` 与仓库逐项相同 |
| `iron-11` | `check-tree-owner.py` 见到未提交文件 | 提交后消失 |
| `hard-33` | `porting-gate.py --quick` 报「脏补丁 <= 1 → 2」 | 提交后消失 |

结论：这些都不是补丁或驱动的问题，而是「本地工作树尚未提交 + 构建输入没指对」造成的。
提交并重新同步 `K60_DEVICE_INPUT` 后重跑即可。

### 6.1 修完上面这批之后又撞到的四个坑（同样与驱动代码无关）

| 现象 | 根因 | 修法 |
| --- | --- | --- |
| `unixnu: XNU patch …/0617-k60-thermal-tsens.patch: git failed (1): error: patch failed: bsd/conf/files:406` | 第一段 hunk 锚在 `bsd/dev/pong_fat.c`，那行是 `K60_CONF_FILES_HOOK`（`build-xnu-4k-baseline.sh:11-19`）在 format-1 路径追加的；build-strict 走 unixnu，不跑该 hook | 改锚到 `bsd/dev/pong_buttons.c`（series 内补丁确实写入的行），`git apply --check` 通过 |
| `feeds.toml needs a source with kind = "soc" and name = "sm8475"` | `scripts/sync-device-input.py` 不复制 `feeds.toml` | `cp /opt/k60/trees/usb-cdc-mainline/device/feeds.toml /opt/k60/trees/thermal-device/` |
| `bash: …/scripts/build-battery-archive.sh: No such file or directory` | 从 `lead-out` 复制的 `.config` 里 `CONFIG_XNU_K60_PHYSICAL_BATTERY=y` | 删 `.config` 后 `unixnu defconfig` 重生成（§7 第 2 步） |
| `FileNotFoundError: …/thermal-device/.cache/firmware/k60-gpu/gmu_gen70000.bin` | `sync-device-input.py` 也不复制 `.cache/firmware`（GPU 固件由 `build-pong-adreno-platform-linux.py:91` 读取） | `rsync -a /opt/k60/trees/usb-cdc-mainline/device/.cache/firmware/ /opt/k60/trees/thermal-device/.cache/firmware/`（152 KB） |

这四条都是「自建构建输入目录比共享目录少了非仓库内容」这一类问题。下次从零建目录时，
`feeds.toml` 与 `.cache/firmware/` 要一起拷，否则会在链接前十几分钟才失败。

### 6.2 第五个坑：`IOPMPrivate.h` 不在导出头里（发布层第一次真构建时炸）

`build-strict.sh thermal-20261114e` 通过了合规门禁、八步门禁和 230/230 补丁应用，
在**真正的编译阶段**失败：

```
EXPORT_HDRS/iokit/IOKit/pwr_mgt/RootDomain.h:39:10: fatal error:
  'IOKit/pwr_mgt/IOPMPrivate.h' file not found
make[7]: *** [.../bsd/DEVELOPMENT/Makefile:3201: pong_thermal_pm.cpo] Error 1
```

| 环节 | 事实 |
| --- | --- |
| 依赖怎么来的 | `RootDomain.h:37-39` 在 `#ifdef XNU_KERNEL_PRIVATE` 里 `#include <IOKit/pwr_mgt/IOPMPrivate.h>`；`MakeInc.def:105` 的 `DEFINES` 恒带 `-DXNU_KERNEL_PRIVATE`，所以任何 include 它的 bsd 文件都会踩到 |
| 为什么导出目录没有 | `iokit/IOKit/pwr_mgt/Makefile` 的 `NOT_EXPORT_HEADERS` 明确列了 `IOPMPrivate.h`，`EXPORT_MI_LIST` 把它滤掉，因此 `EXPORT_HDRS/iokit/IOKit/pwr_mgt/` 只有 7 个头 |
| 为什么 bsd 拿不到源树那份 | bsd 组件的 `INCFLAGS`（`MakeInc.def:884-890`）只有 `EXPORT_HDRS/<各组件>` + `EXTERNAL_HEADERS` + fakeroot 的 `usr/local/include` 与 `platform`，不含源码树 `iokit/`，也不含 Kernel.framework 的 `PrivateHeaders` |
| 手工检查为何没发现 | 上一轮的 `-fsyntax-only` 脚本额外加了 `-I$W/iokit` 与 `-I$FR/…/PrivateHeaders`，**多给的 `-I` 掩盖了真实构建失败**。教训：手工语法检查必须逐字复刻 make 的 `INCFLAGS` |
| 修法 | 在母本里对这一个 include 关掉 private 段：先 `#include <IOKit/IOBufferMemoryDescriptor.h>` 与 `<sys/vnode.h>`（`RootDomain.h:31-35` 无条件 include 的那两个），再 `#undef XNU_KERNEL_PRIVATE`、`#include <IOKit/pwr_mgt/RootDomain.h>`、`#define XNU_KERNEL_PRIVATE 1`。需要的声明（`class IOPMrootDomain` :151、两个 `systemPowerEventOccurred` :177-183）都在 private 段之外 |
| 否决的两个替代 | 把 `IOPMPrivate.h` 拷进 `EXPORT_HDRS`（能编过，但每次重建树就消失，且违背上游 `NOT_EXPORT_HEADERS` 的意图）；给 `pong_thermal_pm.cpo_INCFLAGS` 加 `-I$(SRCROOT)/iokit`（`MakeInc.rule:427` 支持 per-object 追加，但要改 `bsd/conf/Makefile.template`，影响面比一个 include 窗口大） |

修完之后 `build-strict.sh thermal-20261114f`（2026-11-15 00:17）一次通过：
compliance 门禁 → 八步门禁 30 项 → 230/230 补丁 → 内核 `e6557350…` → payload → bootimg，
最后一行为 `✅ kernel archives: 3 enabled archive(s) all present in kernel.macho`。
`pong_thermal_pm.cpo` 这次真的编进了内核（§5 第 3 条的 strings 与符号证据）。

## 7 复现命令

```bash
# 1. 同步构建输入（把仓库镜像进自己的 device 目录）
K60_DEVICE_INPUT=/opt/k60/trees/thermal-device python3 scripts/sync-device-input.py
# 2. 用仓库 defconfig 生成 .config（不要复用别人 out 里的旧 .config）
cd /opt/k60/trees/k60build && ./unixnu defconfig -D /opt/k60/trees/thermal-device \
    --os ipados-16.6.1-20G81 --out /opt/k60/trees/thermal-out mondrian_defconfig
# 3. 严格构建
K60_OUT=/opt/k60/trees/thermal-out K60_DEVICE_INPUT=/opt/k60/trees/thermal-device \
    bash scripts/build-strict.sh thermal-<tag> --fd /mnt/e/iOS Port/Work/artifacts/fd/<fd>.fd
# 4. 验收
strings /opt/k60/trees/thermal-out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho \
    | grep -c 'PongThermal: '
```

注意：`unixnu defconfig` 的 positional 参数要写 `mondrian_defconfig`（写 `mondrian` 会报
`configs/mondrian not found`）；`--os` 要写 `ipados-16.6.1-20G81`（写 `16.6.1-20G81` 会被拒）。
device 目录里必须存在 `feeds.toml`，`sync-device-input.py` 不复制它（需手工从共享 device 拷一份）。

## 7.4 发布层上机后的四个待确认

这一层能编译、能进内核、host 侧算术全过，但它依赖四个**当时尚未在本板上验证过**的前提。
截至 2026-11-15 两轮上机（冷机 `thermal-20261114f`、bias=85000 `thermal-20261115b`）回答了三条：

- ① 已答 —— `published as` 行两轮都出现在 boot 后数秒内，`getPMRootDomain()` 在 worker 首轮即非 NULL；
- ② 已答 —— 两轮 `bootAccepted=true`、`bootExitCode=0`、无 panic marker，非 Apple 调用者没有引发 panic；
- ④ 已答 —— 全程发布各只 1 条（只在等级变化时发），无 workloop 卡顿迹象；
- ③ 仍未答 —— `thermalmonitord` 仍在 `userland/mkjobs.py:217` 的 DENY 里，用户态没有消费者。

其余四条按下面逐条读串口：

1. **`getPMRootDomain()` 何时非 NULL**。`pong_thermal_init` 在 `bsd_init.c:1166-1167` 被调用，
   `IOKitBSDInit()` 在 `:1325`；两者之间是 `bsd_autoconf`。若串口里始终没有 `published as` 行，
   说明在整机生命周期里 root domain 都没起来，或起得比预期晚得多 —— 无论哪种都是必须记录的事实。
2. **非 Apple kext 侧调用者是否无害**。`RootDomain.h:169-175` 的注释写着
   「Only Apple-owned kexts should have reason to call systemPowerEventOccurred」，但没有任何
   代码层面的检查（没有 entitlement 判定、没有 `IOCurrentTaskIsDriverKit` 之类）。本树里
   `systemPowerEventOccurred` 的生产者为 0，本驱动会是第一个。若上机后 panic 或 `Power Status`
   字典异常，这是第一个怀疑点。
3. **`thermalmonitord` 是否消费**。`userland/mkjobs.py:217` 目前把 `thermalmonitord` 列在 DENY 里，
   所以即使发布成功，用户态也没有消费者。要看到压力等级真正生效，得先放行该 daemon。
4. **发布频率与锁**。每轮（1 s）最多发一次，且只在等级变化时发。`systemPowerEventOccurred`
   内部持 `featuresDictLock`（`:8154-8156`），`setThermalState` 会自己 `runAction` 回
   `gIOPMWorkLoop`（`:8124`）。如果上机后看到 workloop 卡顿或 `Power Status` 属性更新丢事件，
   第一件事是把发布点从 worker 线程移到 `IOWorkLoop` 上再测一次。

## 8 2026-11-17 合并 main 后的重建（thermal-20261117c）

2026-11-17 把 `main`（74c0d24e）合入 `feat/thermal-tsens`：七个冲突按并集解决（README 两行
`battery`+`thermal`、`BOOT-ARGS.md` 的 `gprobe`+`pong_thermal_bias`、`TREE-OWNERS.toml` 两个
`[[tree]]`、`EIGHT-STEPS.toml` 的 battery/charger 全节+thermal 全节、`SUBAGENT-DELIVERABLES.md`
的 SA-04/SA-05+thermal SA-06、`patches/xnu/series` 保留 0619/0620/0621 并把 0617 移到最后），
commit `df4b6010`；`render-eight-step-table.py` 的 UNTRACKED 列表里重复的 thermal 行删掉，
commit `fb876fe1`。合并后 `tomllib` 解析 EIGHT-STEPS/TREE-OWNERS/porting.toml 全通过，
`porting.toml` 相对 main 只多一个 thermal area（15 vs 14 areas）。

构建 `thermal-20261117c`（fd `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f`）：

| 项 | 值 |
| --- | --- |
| 构建输入 | `sync-device-input.py` 同步 117 个文件；`--check` 811 文件全部一致 |
| series | 228 条，`file_sha256 4e52fc605a90b407dd1359746b6226fe9be06311fdc5941e8e6e5417183b9037` |
| frozen | `list_sha256 901811126d5b62ebc30aaacfb23c2ba426bc34be0803922c5360cb732d50ac2d` |
| kernel.macho | 105,521,152 B，sha256 `99470ca92c21f8cc3bba79f4a20bc8c9e9a1a3861dd4417c2663920e8251d4a8` |
| payload | `b0f0e69df21e12f8f41e86ade82eebdeca7c9b6a46f6e6f1fffc1c7bab984a67` |
| payload kernel | `f08c9d8965a19297a3bdefb77b58c657919884b96150e05ca682bf2819d6ac34` |
| payload adt | `39dffcb00afa600d381dc3284df901f225e75acf8aeb22b40d01732f9ff5a640` |
| dtb | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| boot.img | 201,887,744 B，sha256 `31441566e9b89c01ba0242628c99518e5ba84798d526bb8e785a3ee30e404a17` |
| manifest | `/mnt/e/iOS Port/Work/artifacts/thermal-20261117c/build-manifest.json` |

`python3 scripts/verify-boot-image.py --manifest …/build-manifest.json` 打印 `verify-boot-image: OK`；
`strings -a kernel.macho | grep -c 'PongThermal: '` = **15**（与 `thermal-20261115a` 相同，
即 §3.1 的全部串），且能找到 `_pong_thermal_init|_pong_thermal_worker|_pong_thermal_sample|
_pong_thermal_sensors|_pong_thermal_controllers|_pong_thermal_bias_mc|_pong_thermal_pm_publish|
_k60tz_table|_k60tz_step|_k60tz_closest|_k60tz_zone_level|_k60tz_names`。

构建日志里的 `skip: CONFIG_XNU_PONG_THERMAL is not enabled in .config` 是 kext 归档路线的检查：
本轮走的是 in-tree 补丁 0617，defconfig 里该开关保持 `n`，十五个日志串与 `_pong_thermal_*` 符号
已经证明驱动确实编进内核；`check-kernel-archives.py` 仍报告四个已启用的归档全部在 kernel.macho 中。

### 8.1 本轮的门禁与测试

| 检查 | 结果 |
| --- | --- |
| `check-thermal-kernel-patch.py` | OK (14 checks)：series 228 条且 0617 最后，七个内核文件与 `drivers/PongThermal/` 逐字节一致，conf/files、bsd_init 调用、只读检查、发布层与 32 zone 阶梯全部成立 |
| `check-thermal-log.py --self-test` | `self-test OK: the clean logs pass and every mutation fails` |
| `check-docs.py` | 202 项，✅ 文档一致性通过 |
| `eight-step-gate.py --quick` | 通过 48 项检查，✅ 八步流程通过（可以刷机） |
| `render-eight-step-table.py --check` | ✅ README 的八步表格与 EIGHT-STEPS.toml 一致 |
| `porting-gate.py --quick` | ✅ 门禁通过（7 项警告） |
| host tests | TESTS OK 264（kernel）/ 72（level）/ 16（tsens）/ 478（zones）/ 260（log） |

### 8.2 构建输入的两个环境坑（与本补丁无关）

1. `/opt/k60/trees/thermal-device` 必须先用 `sync-device-input.py` 从仓库同步；停在 11-14 的
   旧目录会让合规门禁报「只在仓库有 0619/0620/0621」。同步后 `--check` 811 文件一致。
2. prelink 的 kernelcache 查找走 `UNIXNU_KERNELCACHE`；不导出时会回落到 `board.toml` 的远程
   URL，当前网络下报 `URLError: [SSL: UNEXPECTED_EOF_WHILE_READING]`。把
   `UNIXNU_KERNELCACHE=/opt/k60/trees/k60build/bt-out-s1c/ipsw/20G81/kernelcache.decompressed`
   导出后走本地缓存（先例：`E:/iOS Port/Work/scratch/bt-s4/bisect/wsl-build-d.sh:26`）。

结论：合并后的树在 `thermal-20261117c` 上完整构建通过，内核里仍是同一份 15 串/12 符号的
in-tree 驱动；下一次上机只需按 `CRITERIA.toml` 的 cold profile 判读。

## 9 2026-11-17 真机冷机（thermal-20261117c）

2026-11-17 12:28 用户授权后，用 `scripts/flash.sh` 把 `thermal-20261117c/boot.img` 通过
`fastboot boot` 启动（未 flash，未写任何分区）。证据目录
`E:\iOS Port\Work\evidence\usblog-20261117-122800`。

| 项 | 值 |
| --- | --- |
| boot.img | 201,887,744 B，sha256 `31441566e9b89c01ba0242628c99518e5ba84798d526bb8e785a3ee30e404a17` |
| console.log | 247,186 B，3,588 行，sha256 `C4F66F6953E81F666669A17FE22590014D4BD60E6186AE90F2B087A6D4421222` |
| boot.json | `bootAccepted=true`、`bootExitCode=0`，startedAt 12:28:02、finishedAt 12:32:26 |
| capture.json | `captured-budget-complete`、`complete=true`、`portSeen=true`、`portOpened=true`、`openErrors=0`、`panicMarker=null`、`resetMarker=null`、`stopReason=budget` |
| supervisor | rc=0，`captured-budget-complete; bytes=247186; complete=True` |
| 判据 | `python3 scripts/check-thermal-log.py --log ... --profile cold` → **21 passed, 0 failed, 0 advisory**，EXIT=0 |

计数：`PongThermal: ` 241 行；控制器 2 行（`tsens0 tm=0xc263000 srot=0xc222000 ver=2.8.0 ctrl=0x9d67fff9 enabled=1`、
`tsens1 tm=0xc265000 srot=0xc223000` 同值）；polling 1 行（2 controllers every 1000 ms）；
传感器 32 行、32/32 标签（`tsens0[3] cpuss-2 zone27 44.2 C` 在列）；域行 192 行；等级行 8 条，
全部 `level 0/3 nominal (domains 0/3); closest ddr ... C, ... C below tier 1`；published 恰 1 条
`level nominal (0) published as Thermal_Level_Warning=0`；bias 0 条；`no-valid-reading` 0 条；
`window mapping failed` / `no controller mapped` / `worker thread failed` / `disabled by boot-arg` /
`no zone has a reading` / `level 4/3` 全部 0 条。

原文三行：

```
PongThermal: tsens0[3] cpuss-2 zone27 44.2 C
PongThermal: level 0/3 nominal (domains 0/3); closest ddr 43.6 C, 46.4 C below tier 1
PongThermal: level nominal (0) published as Thermal_Level_Warning=0
```

日志里的 2 条 `panic` 是 `K60PANIC: restart windows ready` 与启动参数串 `k60_panic_reset=1`；
8 条 `crashed` 是 `syncdefaultsd` / `amfid` / `mmaintenanced` 的 userland corpse 消息（如
`Process[223] crashed: syncdefaultsd. Too many corpses being created.`），没有 thermal 相关 panic。
冷机温度 40-52 C，未触及最近被动档 90 C，故等级保持 0/3 是预期；高等级路径由
`thermal-20261115b` 的 `pong_thermal_bias=85000` 上机（22 passed，published=3）覆盖。

结论：合并 main 后的 `thermal-20261117c` 在 6033dbec 上完成 cold profile 的 21/21 判据，
32 路 tsens、0..3 阶梯与 `Thermal_Level_Warning` 发布层均在真机工作。

