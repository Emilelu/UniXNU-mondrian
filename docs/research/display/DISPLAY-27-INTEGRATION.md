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
| `AppleARMBacklight` | `AppleARMBacklight.cpp`（468 行），`porting/display.md:89-100` | 已有的 `K60Backlight.cpp` + `K60BacklightCodec.h`，改 4 处、加 1 个实验参数 | 已有 11/14 条契约；真缺 3 条（六键字典、未知属性分支、arm64e 伪装） |
| `GeniI2c` | `GeniI2c.h`（120 行），`porting/display.md:89-91` | **不接入**：K60 是 `bl_ctrl_dcs`，亮度走 DSI DCS `0x51`，没有 I2C 背光 IC | 不适用；只在"将来出现外置背光 IC"时按官方顺序接 |

预算一句话：**27 的命令行不是"在 596 B 上加"，而是 `os_overrides` 整表替换后的
104 B 起算**；把 16.6.1 的 30 项恢复回来就是 673 B，**已经超 66 B**；
显示线自己的新增只有 9 B（`k60_dpu=1`），另有 23 B 的 `k60_backlight_control=0`
建议用"改代码默认值"消掉。

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

### 2.1 必须改（不改正则会出错）

**(a) 未知属性分支**：`K60Backlight.cpp:384-433` 是 `brightness-nits` / `brightness`
二分支，落空走 `:415-418` 的 `else`（只打一行日志），然后仍然 `:428 publish(goal)`——
而 `goal` 在这一支**没有赋值**。27 的 CoreBrightness 会发 `brightness-nits-cap`
一类属性（`drivers/sheng-backlight.md:46`：其它属性返回成功、无效果），落进来就是
一次未定义亮度写（可能 0 → 黑屏）。改法：把 `goal` 初始化为当前等级，或在 `else`
里直接 `return kIOReturnSuccess;` 且不改亮度。判据：上机后滑块最小位置亮度不跳变。

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

### 2.2 建议改（形态 A 的字节优化）

`k60_backlight_control` 现在的默认值是"发"（`:339-341`），形态 A 要求镜像带
`k60_backlight_control=0`（23 B）。27 的预算是负的（§3），**建议把默认值翻成 0**：
`:339` 的 `uint32_t controlArg = 1;` → `0`，`:341` 的条件随之变成"只有 `=1` 才发"。
参数保留，实验时仍可用 23 B 打开。这省下的是命令行的字节，不改任何行为语义。

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

### 4.3 三组数字

| 组 | 参数数 | 字节 | 相对 607 |
| --- | --- | --- | --- |
| 16.6.1 板级 `[payload].kernel_args`（现值） | 30 | **596** | 余 11 |
| 27 `os_overrides`（现值） | 7 | **104** | 余 503 |
| 27 = override + 恢复板级其余 28 项（去重后共 35 项） | 35 | **673** | **超 66** |
| 27 = 上一行 + 显示线新增 `k60_dpu=1` | 36 | **682**（追加 +1 空格 = 683） | **超 76** |

两个共享参数（`-v`、`amfi_get_out_of_my_way=1`）已在 override 里，所以恢复的是 28 项。

**这张表最要紧的一句**：27 上"把 16.6.1 的参数全部恢复"本身就已经超 66 B。
显示线这次只加 9 B，超限的 66 B 不是显示线造成的，但显示线必须在预算表里
把这件事写清楚，否则 27 镜像一构建出来就停在 REQUEST。

### 4.4 显示线的参数集（逐项字节）

必需（缺了显示线不成立）：

| 参数 | 字节 | 为什么必需 | 16.6.1 出处 |
| --- | --- | --- | --- |
| `pong_adreno_start=1` | 19 | GPU 起来才有 GPU 拷贝扫描输出 | board.toml |
| `pong_metal=1` | 12 | 同上（Metal 服务） | board.toml |
| `pong_gpu_scanout=1` | 18 | 帧所有权走 GPU（`PongAdrenoScanout.cpp:154-211`） | board.toml |
| `sheng-gpu-addon=1` | 17 | 27 的 GPU 侧附件（sheng 树同名） | board.toml |
| `k60_usblog=2` | 12 | 显示证据的唯一出口（`K60 PANEL:`/`K60 BACKLIGHT:` 行） | board.toml |
| `k60_console_export=1` | 20 | 同上（控制台导出） | board.toml |
| `applog=1` | 8 | 同上（IOLog 落盘） | board.toml |
| **小计** | **106**（含 6 空格 112） | | |
| `k60_dpu=1` | **9**（追加 +1 空格 = 10） | 本线新增：27 的 DPU 探针 | 新 |

可选（按需出现，不进默认镜像）：

| 参数 | 字节 | 何时用 |
| --- | --- | --- |
| `k60_backlight_control=1` | 23 | 实验形态 B（发布 `backlight-control`）；默认 0 时不出现（§2.2 建议） |
| `k60_backlight_calibration=1` | 29 | 实验六键字典（DELTA §9 U1）；默认不出现 |
| `k60_dpu=2` / `=3` | 9 | 探针级别；level 3 另有开关要求（§1.3） |
| `log-display=1` | 13 | 只在需要 27 自己的显示日志时（16.6.1 用 `k60_usblog`） |
| `p120=0` / `vsync=…` | 5 / 9 | 退回 60 Hz（默认 120 Hz，`PongDsiPanel.cpp:566-577`） |
| `k60_backlight=1` | 15 | 不必要：服务无条件启动，board.toml 里也没有这个参数 |
| `k60_panel=0` | 11 | 只在"boot framebuffer 不是这块面板"时（QEMU / 换屏） |

⇒ 显示线的**净新增**是 `k60_dpu=1` 一项、**9 字节**（追加时 10）。
其余 106 B 已经在"恢复板级参数"的 673 B 里。

### 4.5 超限 76 B 怎么办（交回 Lead 的账）

显示线只声明自己的 9 B；剩下 67 B 的削减属于平台线/其他线。下面给出**候选**
（字节都是逐项实测，取自已核的 board 参数表），**不是建议删除**：

| 候选 | 字节 | 与显示的关系 |
| --- | --- | --- |
| `pong_init_path=/private/var/pong/init` | 37 | 无（用户态 init 路径） |
| `pong_allow_unauthenticated_root=1` | 33 | 无 |
| `k60_tolerate_cache_loader=1` | 27 | 无 |
| `k60_skip_firmware_mount=1` | 25 | 无 |
| `cs_enforcement_disable=1` | 24 | 无 |
| `launchd_unsecure_cache=1` | 24 | 无 |
| `k60_entitlement_allow=1` | 23 | 无 |
| `pong_software_keybag=1` | 22 | 无 |
| `disable_exc_resource=1` | 22 | 无 |
| `k60_skip_iosurface=1` | 20 | **有**：`IOSurface` 与显示服务同栈，删它之前要确认不影响首帧 |
| `pong_ufs_readwrite=1` | 20 | 无 |
| `k60_autoreset=300` | 17 | 无（但见 `BOOT-ARGS-PENDING.toml` 的债） |

### 4.6 账本规则（新增参数必须落账）

| 规则 | 位置 | 对本线的含义 |
| --- | --- | --- |
| 门禁只认 `BOOT-ARGS.md` 的 `### \`name\`` 与表格首列 | `scripts/check-boot-args.py:24-28` | `k60_dpu`、`k60_backlight_calibration` 必须写进 `BOOT-ARGS.md` 的表格 |
| 门禁扫 `board.toml` 的 `[payload].kernel_args` | `scripts/check-boot-args.py:39-44` | **不看 `os_overrides`** ⇒ 27 的 override 里的参数门禁看不见，文档是唯一台账 |
| 门禁扫 `patches/**/*.patch` 与 `drivers/**` 的 `PE_parse_boot_argn("…")` | `scripts/check-boot-args.py:50-60` | 新文件里每解析一个参数，文档就必须有一条 |
| `BOOT-ARGS-PENDING.toml` 是"只许减少"的债（`count = 41`） | `scripts/check-boot-args.py:86-110` | 新参数**不能**塞进这里（加了就 42 条，门禁失败） |
| 缺文档即失败 | `scripts/check-boot-args.py:114` | 同上 |
| 取值必须落在 `BOOT-ARGS.md` 声明的范围内 | `scripts/check-boot-args.py:167` | `k60_dpu=3` 的上界要写在文档里 |

⇒ 本线要提交的账本改动（等 Lead 批，因为 `docs/engineering/BOOT-ARGS.md` 是共享文件）：
在 `BOOT-ARGS.md` 的显示小节加两行（`k60_dpu`、`k60_backlight_calibration`），
并在 `board.toml` 的 27 override 里加 `k60_dpu=1`。**这两处本线不自己改**（契约禁止改共享树）。

---

## 5. 交回 Lead 的三个决定

1. **`k60_dpu` vs `sheng-dpu`**：本文建议 `k60_dpu`（省 2 B，名字与本板实现一致），
   官方页面的 `sheng-dpu` 作为别名保留。若 Lead 要求"参数名与官方页面逐字一致"
   （便于照页面复现），则改回 `sheng-dpu=1`（11 B）。
2. **`k60_backlight_control` 的默认值翻转**（§2.2，省 23 B）：这是代码语义改动，
   会影响 16.6.1 与 27 的共同文件 `K60Backlight.cpp`；需要 Lead 确认是否允许在
   27 分支上改（改法是 `:339` 的 `1` → `0`，一行）。
3. **超限 76 B 的分摊**：显示线 9 B 已定；剩余 67 B 由平台线在 `os_overrides`
   的表里重新分配（候选表 §4.5）。本线不改 `board.toml`。

---

## 6. 本次没有做的事（边界）

- 没有构建、没有生成 boot.img、没有 `fastboot`（契约 §iron-16）。
- 没有改 `board.toml`、`docs/engineering/{BOOT-ARGS.md,BOOT-ARGS-PENDING.toml}`、
  `patches/`、`scripts/`。
- 没有写八步 fragment 的 `step.device`（Lead 的字段）；
  七步 `done` 保持 `false`，因为 27 侧一条读数都还没有。
- 27 的 CoreBrightness 二进制没拿到（DELTA §9 U1 的一手读数：只有 `.tbd` 链接桩）。
