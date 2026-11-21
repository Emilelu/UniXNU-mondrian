# iOS 27 显示线：三个实现的接入点与 boot-arg 预算

对象：官方《适配驱动》表第 3 行 `porting/display` 的三个实现——
`DisplayTimingProbe`、`AppleARMBacklight`、`GeniI2c`——在 27（`24A446`）上的
接入点，以及 27 的 608 字节 boot-arg 预算核算。

树：`E:/hackios/k60-display27`，分支 `feat/display-27`，基 `main` = `4b744c2e`。
配套：`docs/research/display/DISPLAY-27-DELTA.md`（差异表，含全部行号）、
`docs/research/eight-step/display-27.toml`（八步 fragment）。
全部离线：没有构建、没有上机、没有改共享树。

---

## 0. 结论摘要

| 实现 | 官方位置 | K60 在 27 上的接入点 | 结论 |
| --- | --- | --- | --- |
| `DisplayTimingProbe` | `DisplayTimingProbe.cpp`（121 行），`porting/display.md:44-78` | **新文件**，与 `PongDsiPanel.cpp` 的 INTF 读数合并；新参数 `k60_dpu=1`（9 B） | 要写；INTF 侧可以逐字复用（八个偏移已证相同），MDP 侧按 catalog 表驱动、K60 那一行留空 |
| `AppleARMBacklight` | `AppleARMBacklight.cpp`（468 行），`porting/display.md:89-100` | 已有的 `K60Backlight.cpp` + `K60BacklightCodec.h`：真缺 2 条（六键字典、arm64e 伪装）、已获批 1 条（默认值翻 0）、已撤回 1 条（未知属性分支） | 已有 12/14 条契约；「未知属性用未初始化 goal 发布」经复核不成立（`:402-404` 已返回成功） |
| `GeniI2c` | `GeniI2c.h`（120 行），`porting/display.md:89-91` | **不接入**：K60 是 `bl_ctrl_dcs`，亮度走 DSI DCS `0x51`，没有 I2C 背光 IC | 不适用；只在"将来出现外置背光 IC"时按官方顺序接 |

预算一句话：**27 的命令行不是「在 596 B 上加」，而是 `os_overrides` 整表替换后的
104 B 起算**；把 16.6.1 的 30 项恢复回来是 661 B（34 项，`debug` 取 override 的
`0x14e`），**已经超 54 B**，再加 `k60_dpu=1` 是 671 B、超 64 B。所以按 Lead 的
「按读者分摊」重排：显示线只认领有读者的 14 项 **224 B**（余 383 B），
另外 18 项 401 B 交回其他线，3 项 44 B 无读者（Lead 已裁删除）（§4.4）。
落地口径是 **A+B = 626 B，仍超 19 B**：三个逐字节算过的收口选项在 §4.7
（Lead 2026-11-21T16:58 已裁 **O1 → 603 B，余 4**）。`k60_backlight_control=0` 那 23 B 仍建议用
「改代码默认值」消掉（§2.2，已获批）。

wire 侧另有一件只审不改的事：版本号中立法案由 gpu27 出、Lead 会签，本线只审覆盖
（`docs/research/display/WIRE-VERSION-REVIEW.md`）。

---

## 1. `DisplayTimingProbe`：27 的接入点

### 1.1 它做什么（27 侧逐行）

`DisplayTimingProbe.cpp`（121 行，参考实现）：

- `:4-7` 头注释给出硬件事实：MDSS `0xae00000`、MDP 子块 `0xae01000+0x8f000`
  （`qcom,sm8550-dpu`）、双 DSI（`dsi@ae94000`/`dsi@ae96000`）、面板 NT36532E、
  DPU 9.2 catalog（intf1/2 `0x35000/0x36000`、CTL n `0x15000+0x1000n`、
  VIG `0x4000+0x2000n`、DMA `0x24000+0x2000n`）。
- `:30-39` 常量表：`kMdp`、`kIntf{0x35000,0x36000}`、INTF 的七个偏移、
  pipe 的四个偏移、CTL 的五个偏移、`kPipeMore[9]`、`kCtlMore[7]`、`kTearCheck`、`kAutorefresh`。
- `:42-111` 线程：`IOSleep(150000)` → 采 `frame count` 两次（隔 1 s，µs 记进
  `native_dpu_stats[18]`）→ 读 10 条 pipe、`PE_current_console` 的 `v_baseAddr`、
  CTL0..3；level≥2 加读 VIG0/1 九寄存器 + CTL0 七寄存器 + 两接口 tear/autorefresh；
  level 3 把 VIG0/1 的 src0 写回、CTL0 flush 写 `0x3`、测锁存 µs。
- `:114-121` `sheng_dpu_probe()` 解析 `sheng-dpu` 1..3。

### 1.2 K60 侧已有的东西

`drivers/PongAdreno/PongDsiPanel.cpp`：

- `:69` `unsigned panel_measured_hz;` —— 已经有一个"测出来的帧率"变量。
- `:84` 八个 INTF 偏移：`IntfConfig 0x04, IntfVsyncPeriod 0x0c, IntfCountEnable 0xa8,
  IntfFrameCount 0xac, IntfLineCount 0xb0, IntfTearCheckEn 0x284, IntfTearSyncVsync 0x288,
  IntfTearAutorefresh 0x2b4, IntfTeCount 0x298`。
- `:136-236` `panel_intf_rate(phase, ms)`：TE 计数器高位当帧计数、帧计数只在命令 FIFO
  提交时前进、行计数按自动刷新间隔——注释 `:136-143` 说明为什么三者都要读。
- `:100-118` `probe_page()/probe_read()`：13 个 slot 的页映射，已有失败回退。

**对比结论（已逐字核对）**：`PongDsiPanel.cpp:84` 与 `DisplayTimingProbe.cpp:32-33`
的 INTF 偏移**八个全部相同**；页基址也相同（`PongDsiPanel.cpp:505`
`0x0ae35000 + active*4096` vs `DisplayTimingProbe.cpp:31` `kIntf{0x35000,0x36000}`）。
⇒ K60 的 27 探针**不需要重写 INTF 采样**，只需要：

1. 把 `panel_intf_rate()` 的输出接到一个稳定的统计数组（现在是 `panel_measured_hz` 单值）；
2. 新加 MDP/DPU 侧读数（VIG/CTL），**按 catalog 表驱动**，不是硬编码；
3. 参数化级别（0 关 / 1 INTF / 2 +VIG·CTL / 3 +写回）。

### 1.3 三个文件级决定

| 决定 | 选择 | 理由（含行号） |
| --- | --- | --- |
| 放哪里 | 新文件 `drivers/PongAdreno/K60DisplayTimingProbe.cpp` + `.h`，由 `PongDsiPanel.cpp` 在 `pong_panel_bringup()` 成功后启动线程 | `PongDsiPanel.cpp:520-560` 是唯一确认"DSI 已映射、面板已亮"的地方；探针在那之前读寄存器没有意义（`DisplayTimingProbe.cpp:42` 的 `IOSleep(150000)` 是同一个道理） |
| 参数名 | `k60_dpu=1`（9 B），同时接受 `sheng-dpu` 作为别名（别名只解析、不必出现在命令行） | 官方页面的 `sheng-dpu` 是 sheng 板的参考实现参数名；本仓先例是 `k60bt` 而不是 `bluetooth`（`docs/engineering/BOOT-ARGS.md` 的改名记录）。省 2 B |
| level 3 | **默认禁止**，需要 `k60_dpu=3` 显式请求；且第一次写回前先打印将要写的地址与值 | `DisplayTimingProbe.cpp:100-110` 的 level 3 会**写** VIG src0 与 CTL flush；K60 的 catalog 未核实（DELTA §9 U2），写错等于把扫描输出指到别处 |

### 1.4 复用/适配/拒绝（对 sheng 逐条）

| sheng 的东西 | 判定 | 依据 |
| --- | --- | --- |
| INTF 偏移与页基址 | **copied** | 与 `PongDsiPanel.cpp:84,:505` 逐字相同 |
| 采样间隔（`IOSleep(150000)`、两次隔 1 s） | **copied** | `DisplayTimingProbe.cpp:42`；与 `panel_intf_rate()` 的 200/500 ms 不冲突（一个粗一个细） |
| `native_dpu_stats[18]` 形状 | **adapted** | 本仓已有 `probe_frames[4]`/`panel_measured_hz`（`PongDsiPanel.cpp:69,:80`）；27 上加一个 18 项数组即可，不复用变量名 |
| MDP 子块 `0xae01000+0x8f000` | **rejected（暂）** | K60 的 `RESEARCH.md` 记 `0xae00000+0x84000`；两者不同源，见 DELTA §9 U2 |
| DPU 9.2 catalog（sm8550） | **adapted（表驱动）** | K60 是 SM8475；偏移进表、缺表即只做 INTF |
| 双 DSI（`dsi@ae96000`） | **rejected** | K60 单 DSI（`RESEARCH.md`、`PongDsiPanel.cpp:33` 只有 `DsiPa`） |
| level 3 写回 | **adapted（默认关）** | 见 §1.3 |

### 1.5 验收判据（离线可写、上机可读）

- 离线：新文件的寄存器偏移表必须是**引用**（`constexpr` + 注释指到 `RESEARCH.md` 的行），
  不能出现从 sheng 抄来的字面量 `0xae01000`。
- 上机 level 1：`K60 DPU: intf1 te <n>/s frames <n>/s over 1000 ms`，且 `<n>` 与
  `K60 PANEL: INTF1 …` 同一量级（60 或 120）。
- 上机 level 2：`K60 DPU: pipe VIG0 src=0x… size=…:… stride=… format=0x…` 与
  `PE_current_console` 的几何一致（否则说明 catalog 偏移错，直接退回 level 1）。
- 上机 level 3：只在 `K60 DPU: catalog unknown` 不出现时才允许；写回前后打印
  `ctl0 flush latch <µs>`，官方参考值是 5.4 ms 内锁存（`display.md:70-72`）。

---

## 2. `AppleARMBacklight`：27 的接入点

实现位置不变：`drivers/PongAdreno/K60Backlight.cpp`（512 行）+
`drivers/PongAdreno/K60BacklightCodec.h`。27 的契约逐条对照在
`DISPLAY-27-DELTA.md` §5（14 条，11 条已具备）。本节只写**要动的地方**。

### 2.1 要动的地方（(a) 已复核撤回，(b)(c) 仍在）

**(a) 未知属性分支（复核后：不需要改，原文的缺陷不成立）**：
`:392-404` 是 `brightness-nits`（`:392-396`）/ `brightness`+`FadePeriod`（`:397-401`）/
`else { return kIOReturnSuccess; }`（`:402-404`）三支，`goal` 只在前两支赋值，
**不存在**「用未初始化 `goal` 去 `publish()`」的路径；`:415-418` 的 `else` 是
「非 nits 请求」的日志分支（条件在 `:410`），不是请求落空分支。27 的
`brightness-nits-cap` 一类属性落到 `:402-404` 返回成功、不改亮度，正是
`drivers/sheng-backlight.md:46` 要求的行为。复核判据：
`git show HEAD:drivers/PongAdreno/K60Backlight.cpp | sed -n '384,404p'`。
⇒ 原「必须改」清单的第一条降为「已满足」。这个函数里唯一值得动的是日志字段
（`:416-417` 把 `goal` 打了两次），已单独提成
`patches/proposed/0001-k60-backlight-log-requested-level.patch`，不进 ②③ 的结论。

**(b) 六键 calibration 字典的去留**：`:209-247` 现在**故意不发**
`backlight-calibration-parameters`，理由是 20G81 的 CoreBrightness 读十键不查 NULL
（`:230-246`，判据 int-236，lr `CoreBrightness+0xfbaa4`）。24A446 是否也这样**未知**
（DELTA §9 U1）。接入方式：保留"不发"为默认，把字典放在
`k60_backlight_calibration=1`（29 B，仅实验镜像）后面，代码位置在
`publishCalibration()` 末尾 `:246` 之后。回退：开参数后 backboardd SIGSEGV 即永久关闭。

**(c) arm64e 元类伪装**：`:134-158` 的 vtable slot 替换在 ptrauth 构建被拒绝；
sheng 的做法是 `gImpersonating` 标志 + 手写 `getMetaClass()`
（`AppleARMBacklight.cpp:324-343` 与 `:437-440`）。27 的内核是否 arm64e 未定
（DELTA §9 U4），所以接入方式是**两种都留**：arm64 走旧路径（已证可用），
ptrauth 构建走 sheng 路径；用 `#if` 判 `__arm64e__` 即可，不新增文件。

### 2.2 已获批的改动（形态 A 的默认值翻转）

`k60_backlight_control` 现在的默认值是「发」（`:339-341`），形态 A 要求镜像带
`k60_backlight_control=0`（23 B）。**Lead 2026-11-21 批准**在 27 分支把默认值翻成 0：
`:339` 的 `uint32_t controlArg = 1;` → `0`，`:341` 的条件随之变成「只有 `=1` 才发」。
参数名不变，实验时仍可用 23 B 打开。

三条约束（Lead 原话的要点）：参数名不变、提交信息写明「27 默认由后端裁决」、
差异表记一行「这是行为改变，不是优化」。第三条已记在
`DISPLAY-27-DELTA.md` §6 的结论行。

**交付形态（Lead 2026-11-21T16:58 裁）**：这个改动**不直接改源码、也不进 series**，
作为独立草案 `patches/proposed/0002-k60-backlight-let-the-backend-decide.patch` 提交
（`git apply --check` 已过，`diff` 只动 `:330-339` 一处注释块与 `:339` 一行）。
草案头写明「只适用于 27 分支，16.6.1 封闭系列不得取此补丁」。

**这是行为改变，不是优化**：同一份文件在 16.6.1 上默认发布 `backlight-control`、
在 27 上默认不发布，判据行 `control=` 的默认值因此随 OS 版本变化，读日志时
不能跨版本比较这一位。字节上省 23 B 只是副作用。

### 2.3 不动的地方

- `publish()`（`:172-204`）已发 brightness + BrightnessMilliNits，27 侧同形。
- `publishCalibration()` 的 marketing table / Lmax·Lmin·LmidProduct（`:211-229`）
  与 sheng 的形状一致，含 LmaxProduct 的 4 字节 OSData（`:218-221` vs
  `AppleARMBacklight.cpp:290-293`）。
- 亮度写入路径 `writeLevel()`（`:252-260`）→ `pong_panel_set_brightness(dbv)`
  → DCS `0x51`（`PongDsiPanel.cpp:247`）。27 不需要改成 I2C（见 §2.4）。
- 请求交给工作循环（`:420-428`）已经符合 `display.md:89-91` 的"不能阻塞"要求。

### 2.4 验收判据

- 上机日志一行：`K60 BACKLIGHT: published level <n> dbv 0x… conformance=<0|1> control=<0|1> stats=… req=…`（`:374-381`）。
- 形态 A 的判据（16.6.1 已成立，27 上重新取）：`conformance=0 control=0 stats=3,0,2047,2047`，
  backboardd 崩溃 0 次，SpringBoard 行数 > 0。
- **新增一条 27 专属判据**：滑块从最小到最大，日志里 `brightness-nits` 请求的
  16.16 值应单调，且 `dbv` 单调；若出现 `goal=0` 的意外写（(a) 的 bug），第二次
  滑动就会看到 `dbv 0x0` 卡住。
- 虚拟平台判据（DELTA §10 R2）：MobileGestalt `IsVirtualDevice` 必须为 false，
  否则亮度请求被 `VMBLControl` 静默吃掉，以上全部日志都会"正常"但屏幕不变。

---

## 3. `GeniI2c`：27 的接入点（结论：不接入）

### 3.1 为什么

K60 的面板背光**没有独立 IC**：live FDT 是 `bl_ctrl_dcs`（`docs/research/display/RESEARCH.md`，
`bl-max 0xfff`、`bl-min 0x1`、`bl-inverted-dbv`、`qcom,bl-update-flag=delay_until_first_frame`），
亮度就是 DSI DCS `0x51` 两字节（`PongDsiPanel.cpp:541-551`）。
`GeniI2c` 是 sheng 的两颗 KTZ8866（I2C `0x11`，SPI `0xa84000`/`0x988000`，
`AppleARMBacklight.cpp:43-49`）用的传输层。官方 `display.md:80-87` 也把选型写成
"选 I2C / DSI 命令 / PWM 三选一"。

⇒ 27 上 K60 的亮度接入点是 **DCS**，`GeniI2c` 一行都不需要。

### 3.2 它编码的纪律仍然适用

`GeniI2c.h:97-115` 的 API 形状（`prepare` → `start_write/start_read` →
`event` → `poll`/`timeout`，见 `GeniI2c.h:97-115`；寄存器表 `:1-60`）本质是
"一次传输有明确的四段生命周期，且必须有超时"。DSI 侧的对应物在
`PongDsiPanel.cpp:320` `dsi_dcs()` + `:67` `dsi_mdp_waits`（MDP-busy 等待计数）+
`:405` `dsi_write0()`。27 上要保证的是同一件事：**每次 DCS 写都有上界等待和失败计数**，
而不是无限等 MDP。这条已经在 16.6.1 成立，27 不改。

### 3.3 如果将来真出现外置背光 IC

接入顺序（按官方 `display.md:89-91`）：`geni_i2c_prepare()` → 写寄存器
（`start_write_bytes` 或 `start_write_buffer`）→ `geni_i2c_event()` 收中断 →
`geni_i2c_timeout()` 兜底；服务侧仍然在 `K60Backlight::setProperties()` 里只记请求、
在 work loop 里做传输。那时才需要新 boot-arg（GPIO/时钟/供电），预算另算。

---

## 4. 608 字节 boot-arg 预算

### 4.1 上限与判定方式（逐处核到）

| 事实 | 位置 |
| --- | --- |
| 上限 608 字节缓冲 | `uefi-mondrian/Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h:8` `#define DARWIN_BOOT_LINE_LENGTH 608` |
| 缓冲区 | `uefi-mondrian/.../DarwinBoot.c:771` `CHAR8 CommandLine[DARWIN_BOOT_LINE_LENGTH]` |
| **合法上限 607 字节**（含空格，留 NUL） | `DarwinBoot.c:794` `if ((Index >= sizeof (CommandLine) - 1) \|\| (Request->BootArgs[Index] > 0x7f)) return EFI_BAD_BUFFER_SIZE;` |
| 超限的后果 | 固件在进内核前返回，屏幕停在 REQUEST、串口 0 字节（不是 panic，没有日志） |
| 27 的 loader 是同一个 | `xnekom-ios27/drivers/DarwinBoot22/…/BootArgs.h:8` 也是 608（对照：`UniXNU-zizhan/drivers/DarwinBoot24/…/BootArgs.h:8` 是 1024，勿混） |

字节口径：`n` 个参数的总长 = 各参数字节之和 + `n-1` 个分隔空格。

### 4.2 `os_overrides` 是整表替换（决定 27 的起算点）

`UniXNU/scripts/unixnu/profiles.py:9-16` 的 `merge()` 对 list 走
`result[key] = deepcopy(value)`（**替换**，不是拼接）；`:52-56` 取
`os_overrides[os_name]` 叠在板级之上、`remove` 列表逐点删键。
打包文档 `UniXNU/docs/zh/porting/packaging.md:83` 只说"仅对该配置合并到板级之上的表"，
没写 list 语义——以代码为准。

⇒ `board.toml` 的 `.os_overrides."ios-27.0.1-24A446".payload.kernel_args`
**替换掉** 基础 30 项。27 的命令行起算点是 **7 项 = 104 B**：

```
-v serial=3 debug=0x14e kt_fixed_zones=120 -no_slto_panic use_contiguous_hint=0 amfi_get_out_of_my_way=1
```

### 4.3 三组数字（实测，不手算）

字节数的取法：把 `board.toml` 里的列表原样 `len(" ".join(args))`，空格计入。
四个数字都在本树的 `board.toml` 上跑出来，可复现。

| 组 | 参数 | 字节 | 相对 607 |
| --- | --- | --- | --- |
| 16.6.1 板级 `[payload].kernel_args`（现值） | 30 | **596** | 余 11 |
| 27 `os_overrides`（现值） | 7 | **104** | 余 503 |
| 27 = 板级 30 项恢复 + override 的外加四项（`debug` 取 `0x14e`） | 34 | **661** | **超 54** |
| 27 = 上一行 + `k60_dpu=1` | 35 | **671** | **超 64** |
| **本文提议的 27 override：只带读者**（§4.4 A 组） | **14** | **224** | **余 383** |
| **落地口径：A + B**（本线 + 其他线认领的全部有读者项，C 组已删） | **32** | **626** | **超 19** |

倒数第二行是显示线自己的账：14 项、224 B，余 383 B 留给 GPU/USB。
最后一行是 Lead 2026-11-21 裁定的落地口径（A+B），它**仍超 19 B**，收口见 §4.7：
19 B 不是再删一项就完事，得在 B 组里挑，所以给了三个逐字节算过的选项等一句裁决。

### 4.4 最小参数表（按读者分摊）

判据只有一条：**27 上有代码真的读它**（或门禁真的查它）。读者行号取自两处，
表里写明来源，27 树同步后行号会漂移，**以文件 + 符号为准**：

- `XNU:` = WSL `/opt/k60/scratch/applytest-6678/`（16.6.1 打过补丁的 XNU 树）
- `REPO:` = 本仓 `E:/hackios/k60-display27`（驱动与补丁）

#### A 组：本线认领（14 项 / 224 B / 余 383）

| 参数 | 字节 | 读它的 `文件:行` | 不带它的后果 |
| --- | --- | --- | --- |
| `serial=3` | 8 | `XNU:osfmk/arm/arm_init.c:894` | 串口/日志通道的级别回到默认，27 的证据只剩屏幕 |
| `debug=0x14e` | 11 | `XNU:osfmk/kern/debug.c:326`（`TUNABLE(debug_boot_arg,"debug",0)`） | KDB 与调试输出位全关，panic 页不落盘 |
| `kt_fixed_zones=120` | 18 | `XNU:osfmk/kern/kalloc.c:449` | 固定区上限回默认，大镜像 + 显示缓冲先撞 kalloc 上限 |
| `-no_slto_panic` | 14 | `XNU:osfmk/kern/startup.c:471` | SLTO 失败即 panic，27 上等于没有诊断机会 |
| `use_contiguous_hint=0` | 21 | `XNU:osfmk/arm64/arm_vm_init.c:2154` | 连续物理页提示回默认，帧缓冲 256 MB 窗口更容易抢不到 |
| `amfi_get_out_of_my_way=1` | 24 | `XNU:libkern/amfi/miniamfi.c:268`、`bsd/kern/kern_minimac.c:418` | 未签名驱动/预链接一律拒载，GPU 与显示服务都起不来 |
| `pong_adreno_start=1` | 19 | `REPO:drivers/PongAdreno/PongAdrenoPlatform.cpp:605` | 没有 GPU 服务 ⇒ 没有 GPU 拷贝扫描输出（NGP 路径失效） |
| `pong_metal=1` | 12 | `REPO:drivers/PongAdreno/PongAdrenoClient.cpp:202`、`PongAdrenoNativeGlue.cpp:30` | Metal 客户端不注册，合成器拿不到 present 通道 |
| `pong_gpu_scanout=1` | 18 | `REPO:drivers/PongAdreno/PongAdrenoScanout.cpp:52`、`patches/xnu/0600-k60-display-composition.patch:155` | 帧所有权退回 CPU 拷贝，`NGPComplete` 永远等不到 GPU 帧 |
| `sheng-gpu-addon=1` | 17 | `REPO:patches/xnu/zzy-native-gpu-addon-mount.patch:71` | GPU 附件不挂载，`pong_metal` 起来也没有可用驱动 |
| `k60_usblog=2` | 12 | `REPO:patches/xnu/0300-k60-usblog-ep0.patch:180` | 显示证据的唯一出口消失（`K60 PANEL:`/`K60 BACKLIGHT:` 行） |
| `k60_console_export=1` | 20 | `REPO:patches/xnu/0243-k60-console-export.patch:99` | 控制台快照不导出，早期首帧错误无法回读 |
| `applog=1` | 8 | `REPO:patches/xnu/zzzzzzzzzzzzzzzzzz-pong-hackios-launchd-exec.patch:11` | 用户态 exec 链路不落日志，SpringBoard 阶段的黑屏无法定位 |
| `k60_dpu=1` | **9** | 本线新增：`REPO:drivers/PongAdreno/K60DisplayTimingProbe.cpp`（计划文件，§1） | 27 的 DPU 探针不启动，DPU 9.2 常量与扫描输出地址只能靠猜 |
| **合计** | **224** | 14 项 + 13 空格 | |

`applog=1` 是唯一可以整项砍掉的（8 B，只影响用户态日志），其余每一项缺了都会
让「首帧」或「证据」两者之一不成立。

#### B 组：其他线认领（18 项 / 401 B）

这些参数都有读者，但读者在 UFS/数据卷/launchd/安全策略那几条线上。显示线不认领，
列出来是为了让平台线能照表补人，而不是让它们悄悄消失。

| 参数 | 字节 | 读它的 `文件:行` | 不带它的后果（27 上） |
| --- | --- | --- | --- |
| `pong_init_path=/private/var/pong/init` | 37 | `REPO:patches/xnu/0392-k60-dyld-cache-probe.patch:38` | 用户态 init 路径回默认，27 的 init 探针不启动 |
| `pong_allow_unauthenticated_root=1` | 33 | `REPO:patches/xnu/zzzzzzzzz-pong-development-root-policy.patch:13` | 根卷策略回到签名校验，数据卷挂不上 |
| `k60_tolerate_cache_loader=1` | 27 | `REPO:patches/xnu/0314-k60-kern-exit-tolerate-and-clean.patch:33` | 缓存装载器失败即中止，27 的 dyld 缓存路径无回退 |
| `k60_skip_firmware_mount=1` | 25 | `REPO:patches/xnu/0320-k60-skip-firmware-mount.patch:25` | 固件卷挂载照旧，启动时间与卷布局都变 |
| `cs_enforcement_disable=1` | 24 | `XNU:bsd/kern/kern_cs.c:167` | 代码签名强制回到开，未签名二进制全部被拒 |
| `k60_entitlement_allow=1` | 23 | `REPO:patches/xnu/0330-k60-entitlement-allow.patch:26` | 权限降级策略生效，SpringBoard 起不来 |
| `pong_software_keybag=1` | 22 | `REPO:patches/xnu/0211-k60-display-startup.patch:6` | KeyMint 走硬件路径，本板会失败并挡住启动 |
| `disable_exc_resource=1` | 22 | `XNU:osfmk/kern/task.c:987` | 资源超限的信号照发，首帧路径容易被 EXC_RESOURCE 打断 |
| `pong_ufs_readwrite=1` | 20 | `REPO:drivers/NativeUfs/PongUfsTransport.cpp:186` | UFS 只读，数据卷 rootfs 都写不了 |
| `xpcproxy_idversion=1` | 20 | `REPO:patches/xnu/zzzzzzzzzzzzzzzzzz-pong-hackios-launchd-exec.patch:46` | xpcproxy 校验版本号，用户态服务拉起失败 |
| `k60_skip_iosurface=1` | 20 | `REPO:patches/xnu/0332-k60-skip-prelinked-load.patch:21` | **与显示同栈**：`IOSurface` 预链接加载走原路径，首帧可能卡在这里 |
| `k60_launchd_cache=1` | 19 | `REPO:patches/xnu/0394-k60-launchd-cache.patch:56` | launchd 缓存回退到逐项加载，启动变慢甚至超时 |
| `k60_panic_reset=1` | 17 | `REPO:patches/xnu/0334-k60-panic-reset-fastboot.patch:117` | panic 后不自动回 fastboot，上机循环要人工按键 |
| `k60_autoreset=300` | 17 | `XNU:bsd/dev/k60_usblog.c:199`（由 `patches/xnu/0300` 引入） | 黑屏后不回 fastboot，300 秒自动复位失效 |
| `pong_data_mount=1` | 17 | `REPO:patches/xnu/offline-owner-systemos-mount.patch:547` | 数据卷不挂载，27 上没有 `/private/var` |
| `k60_init_blob=1` | 15 | `REPO:patches/xnu/0391-k60-embedded-init.patch:52` | 内嵌 init 不启用，首进程路径回到苹果原版 |
| `pong_data_rw=1` | 14 | `REPO:patches/xnu/offline-owner-systemos-mount.patch:487` | 数据卷只读挂载 |
| `native-ufs=1` | 12 | `REPO:drivers/NativeUfs/NativeUfs.cpp:147` | 原生 UFS 驱动不启用，**没有根设备** |
| **合计** | **401** | 18 项 + 17 空格 | 全不带 ⇒ 27 连用户态都到不了 |

#### C 组：没有读者（3 项 / 44 B）—— Lead 已裁：整体删除

| 参数 | 字节 | 检索范围与结果 | 处理 |
| --- | --- | --- | --- |
| `-v` | 2 | XNU 全树 grep `"-v"` 只命中 `tests/`；`xnekom-ios27/drivers/DarwinBoot22` 与 `uefi-mondrian` 的 DarwinBoot 均无 | 删 |
| `epoch=1793709100` | 16 | XNU（`bsd`/`libkern`/`osfmk`）、`uefi-mondrian`、本仓 `drivers/`+`patches/` 均无 `PE_parse_boot_argn("epoch"`；只有 `bsd/sys/sysctl.h:1208` 的同名 sysctl 与 `drivers/ArmDTPlatform/ArmDTPlatform.cpp:154` 读的 FDT `boot-epoch` 属性，都不是这个参数 | 删（若别的线证明用户态读它，再花 16 B） |
| `launchd_unsecure_cache=1` | 24 | 同上三处 grep 零命中；`xpcproxy_idversion`（同族、有读者）已在 B 组 | 删 |

### 4.5 596 的去向，以及 A+B 为什么还超 19 B

| 分组 | 项数 | 字节 | 说明 |
| --- | --- | --- | --- |
| 板级 30 项中，本线认领（A 组 ∩ 板级） | 9 | 141 | `debug`/`amfi`/GPU 四项/日志三项 |
| 板级 30 项中，交回其他线（B 组） | 18 | 401 | 见上表 |
| 板级 30 项中，无读者（C 组） | 3 | 44 | 已裁删除（Lead 2026-11-21） |
| override 已有的四项（`serial`/`kt_fixed_zones`/`-no_slto_panic`/`use_contiguous_hint`） | 4 | 61 | 保留 |
| 本线新增（`k60_dpu=1`） | 1 | 9 | §1 |
| **A 组合计** | **14** | **224** | 余 383 |
| **A + B** | **32** | **626** | **仍超 19** |

⇒ 两件事同时成立：
1. 显示线自己的账是 **224 B**，达标（≤400），余 383 B；
2. 若其他线把 B 组 18 项全部认领，总账 **626 B**，还是超 19 B。超限没被消掉，
   只是从「显示线 76 B」变成「平台线 19 B」，并且 C 组删掉的 44 B 已经算在里面。
   再往下砍只能从 B 组出，而 B 组第一项就是 `native-ufs=1`（没有它没有根设备）——
   **如果 27 真的要继续瘦身，选项不是删参数，而是把 `debug=0x14e`（11 B）与
   `k60_usblog=2`（12 B）这类证据参数在「已验证的 stable 镜像」里换出来**，
   那属于发布策略，不是本线能定的（§5 已记）。

### 4.6 账本规则（新增参数必须落账）

| 规则 | 位置 | 对本线的含义 |
| --- | --- | --- |
| 门禁只认 `BOOT-ARGS.md` 里 `### name` 形式的标题与表格首列 | `scripts/check-boot-args.py:24-28` | `k60_dpu`、`k60_backlight_calibration` 必须写进 `BOOT-ARGS.md` 的表格 |
| 门禁扫 `board.toml` 的 `[payload].kernel_args` | `scripts/check-boot-args.py:39-44` | **不看 `os_overrides`** ⇒ 27 的 override 里的参数门禁看不见，文档是唯一台账 |
| 门禁扫 `patches/**/*.patch` 与 `drivers/**` 的 `PE_parse_boot_argn("…")` | `scripts/check-boot-args.py:50-60` | 新文件里每解析一个参数，文档就必须有一条 |
| `BOOT-ARGS-PENDING.toml` 是「只许减少」的债（`count = 41`） | `scripts/check-boot-args.py:86-110` | 新参数**不能**塞进这里（加了就 42 条，门禁失败） |
| 缺文档即失败 | `scripts/check-boot-args.py:114` | 同上 |
| 取值必须落在 `BOOT-ARGS.md` 声明的范围内 | `scripts/check-boot-args.py:167` | `k60_dpu=3` 的上界要写在文档里 |

⇒ 本线要提交的账本改动（等 Lead 批，因为 `docs/engineering/BOOT-ARGS.md` 是共享文件）：
在 `BOOT-ARGS.md` 的显示小节加两行（`k60_dpu`、`k60_backlight_calibration`），
并在 `board.toml` 的 27 override 里换成 A 组 14 项。**这两处本线不自己改**（契约禁止改共享树）。

### 4.7 落地口径：A + B 的 27 override（626 B），19 B 怎么收口

Lead 2026-11-21 的裁决是「按 A+B 落地、C 组删、`k60_dpu=1` 用 9 B 那版」。
把 A 组与 B 组合成一条列表就是 27 的完整命令行（`os_overrides` 是整表替换，§4.2；
下面这一行长 626 B，复制即用，别折行）：

```text
serial=3 debug=0x14e kt_fixed_zones=120 -no_slto_panic use_contiguous_hint=0 amfi_get_out_of_my_way=1 pong_adreno_start=1 pong_metal=1 pong_gpu_scanout=1 sheng-gpu-addon=1 k60_usblog=2 k60_console_export=1 applog=1 k60_dpu=1 pong_init_path=/private/var/pong/init pong_allow_unauthenticated_root=1 k60_tolerate_cache_loader=1 k60_skip_firmware_mount=1 cs_enforcement_disable=1 k60_entitlement_allow=1 pong_software_keybag=1 disable_exc_resource=1 pong_ufs_readwrite=1 xpcproxy_idversion=1 k60_skip_iosurface=1 k60_launchd_cache=1 k60_panic_reset=1 k60_autoreset=300 pong_data_mount=1 k60_init_blob=1 pong_data_rw=1 native-ufs=1
```

32 项、**626 B**（A 224 + 1 空格 + B 401），上限 607 ⇒ **超 19 B**。
压空格或缩写取值救不了：最短的可行改法是把 `debug=0x14e` 写成 `debug=0x14`（少 1 B，
且丢一个调试位），19 B 只能靠删项。三个选项都逐字节算过：

| 选项 | 删什么 | 落地字节 | 余量 | 代价 |
| --- | --- | --- | --- | --- |
| **O1（Lead 已裁 2026-11-21T16:58）** | `disable_exc_resource=1`（22 B + 1 空格，`XNU:osfmk/kern/task.c:987`） | **603** | 余 4 | 恢复 stock 行为：资源超限信号照发。它不在首帧的关键路径上，**不损失任何证据** |
| O2（未采纳） | `k60_console_export=1`（20 B + 1 空格，`patches/xnu/0243:99`） | 605 | 余 2 | 控制台快照不再导出，早期首帧错误只能从串口与日志行拼，属证据损失 |
| O3（未采纳） | `applog=1`（8 B）+ `k60_panic_reset=1`（17 B）+ 2 空格 | 599 | 余 8 | 用户态 exec 不落日志；panic 后不自动回 fastboot，上机循环要人工按键 |

O1 被选中的理由只有一条：它是三个里唯一「删掉之后能力回到出厂、而不是丢掉我们自己的观测」的项。
**最终命令行 = A+B 626 B 去掉 `disable_exc_resource=1` 及其前导空格 = 603 B，余 4 B**；
收口由 Lead 直接裁（2026-11-21T16:58：「选 O1……这条不用转平台线，我裁」），本线只落账。

落地后要一起核的两件事：
1. `os_overrides` 的列表即 27 全部命令行，板级 596 B 不会叠加（§4.2），所以 603/605/599 B 就是 27 的实测值（删项同时少一个空格，别按参数长度直接减）。
2. 门禁 `scripts/check-boot-args.py` 只看板级 `[payload].kernel_args`，看不见 override（§4.6），
   因此这条列表必须同时抄进 `docs/engineering/BOOT-ARGS.md` 的显示/平台小节，否则没人读它。

---

## 5. Lead 已裁决的三项（2026-11-21，记录在案）

1. **参数名用 `k60_dpu`（9 B）**，不用 `sheng-dpu`。理由（Lead 原话的意思）：
   板级参数统一 `k60_` 前缀，跨线引用不会与 sheng 的命名混淆，且省 2 B。
   官方页面的 `sheng-dpu` 在本文里作为别名出现，实现只认 `k60_dpu`（§1.3）。
2. **`k60_backlight_control` 的默认值可以翻 0**（27 分支，`K60Backlight.cpp:339` 的
   `1` → `0`），三条约束：参数名不变（仍可 `k60_backlight_control=1` 覆盖）、
   提交信息写明「27 默认由后端裁决」、`DISPLAY-27-DELTA.md` 记一行
   「这是行为改变，不是优化」。已按此记入 DELTA §6。
3. **超限按读者分摊**（不按线分摊）：A 组 224 B 交账，余 383 B 留给 GPU/USB；
   B 组 401 B 由对应线认领；C 组 44 B 删。**落地口径 = A+B = 626 B，仍超 19 B**，
   三个逐字节算过的收口选项在 §4.7，Lead 已裁 **O1 → 603 B**（2026-11-21T16:58，不转平台线）。
   2026-11-21 追加：落地口径、C 组删除、O1 收口都已写进本文；`k60_dpu=1` 按 9 B 那版。

顺带记两条边界（Lead 另有安排，本线不碰）：
- 24A446 的 CoreBrightness 提取由 Lead 派人做（`aea -d` → `hdiutil attach` →
  `dyld_shared_cache_arm64e`），本线按「取不到」的回退写死（DELTA §9 U1）。
- `v_baseAddr` / `Video[]` 属 `step.device`，Lead 在 F2 飞行时读；fragment 里只留
  一行待读项，`done=false` 保持。
- **wire 版本号中立法案**（2026-11-21）：提案由 gpu27 出、Lead 会签，本线只出覆盖审查
  ——`docs/research/display/WIRE-VERSION-REVIEW.md`，判「57 槽」与「48 B 包装」是否覆盖
  本线全部过线字段。**不改 wire、不改断言、不裁形状**。已记的关键事实：`Frame.reserved`@44
  在 `PongAdrenoScanout.cpp:149` 被写成字面量 `0`，`Done.reserved`@12 在 `:122` 被当垃圾
  校验（非零即 `kIOReturnBadArgument`），所以「48 B 包装」不是零改动方案。
- `check-lane-fragment.py` 收不了绝对路径（`/mnt/e/...` 被 `[\w.-]` 剥成 `mnt/e/...`）是 gates
  的 bug，Lead 已认领修复；本 fragment 现在把官方页写成「porting/display 官方页 + 行号」
  的形式只是为了当时过门禁，修好后可以换回绝对路径（更精确，不必再绕）。

## 6. 本次没有做的事（边界）

- 没有构建、没有生成 boot.img、没有 `fastboot`（契约 §iron-16）。
- 没有改 `board.toml`、`docs/engineering/{BOOT-ARGS.md,BOOT-ARGS-PENDING.toml}`、
  `patches/`、`scripts/`。
- 没有写八步 fragment 的 `step.device`（Lead 的字段）；
  七步 `done` 保持 `false`，因为 27 侧一条读数都还没有。
- 27 的 CoreBrightness 二进制没拿到（DELTA §9 U1 的一手读数：只有 `.tbd` 链接桩）。
