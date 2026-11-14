# K60 亮度方案（BRIGHTNESS-PLAN）

> 目标：把显示线从「面板点亮（0x51 0xff 一次性）」推进到「OS 级亮度服务」——iOS 滑块真正改变
> 面板亮度，且 IORegistry 里能读到发布/请求/回读/失败计数。
> 八步：本文覆盖 ②官方 / ③反编译（参考实现）/ ④广查 / ⑤方案；⑥深挖与⑦验证见 §7 与
> `scripts/check-brightness-encoder.py`；⑧上机由 Lead 执行。
> 本文所有结论都带 `文件:行` 引用；未经引用的推测一律标注「待验证」。

## 1. 结论先行

K60 **没有独立背光 IC**：live FDT 里只有 `pm8350c` 的 `lcd_backlight_ctrl` GPIO 使能，亮度只能走
面板的 **DSI DCS 0x51（online DBV）**——这是显示线既有的唯一硬件通路
（`docs/research/display/RESEARCH.md:75-77`：`bl_ctrl_dcs`、`bl-inverted-dbv`、
`qcom,bl-update-flag=delay_until_first_frame`）。

现状缺口（已核实，不再重复调研）：

| 事实 | 引用 |
|---|---|
| `pong_panel_set_brightness(level)` 已实现（DCS 0x51），返回 0 成功 | `drivers/PongAdreno/PongDsiPanel.cpp:247-260` |
| 该函数**全仓零调用者** | 全仓 grep `pong_panel_set_brightness` 只命中定义与头文件 |
| 启动时只发一次 `0x51 0xff`，之后亮度恒为最大 | `drivers/PongAdreno/PongDsiPanel.cpp:236-243` |
| iOS 侧没有任何亮度属性/服务，滑块无效果 | `docs/engineering/PITFALLS.md:808-821`（P-62） |

所以本线要补的不是硬件驱动，而是 **OS 与面板之间的两层**：面向 CoreBrightness 的**服务层**
（发布 IODisplayParameters、接收 `setProperties`）与把 OS 域编码成 DBV 的**编码层**
（`0..2047 → 0..255`、FadePeriod → 线性渐变序列）。这正是官方指南
`docs/zh/porting/display.md:80-114`（§3/§4）对「DSI 命令背光」设备的原话要求：**必须在面向 OS
的亮度服务下实现传输与编码两层**。

## 2. ②官方：指南到底要求什么

`E:/hackios/UniXNU/docs/zh/porting/display.md:80-114`：

- §3：先按硬件选择**传输**（I2C / DSI 命令 / PWM）并按其目标**编码**；参考实现
  `package/AppleARMBacklight.cpp`（KTZ8866 + GENI I2C）与 `package/GeniI2c.h`（GENI 状态机）。
  复用前必须记录：控制器数量、寄存器编码、亮度范围、I2C 引脚/从地址/时钟、中断、供电顺序。
- §3 末句（对本线是硬约束）：**「DSI 命令或 PWM 背光的设备必须在面向 OS 的亮度服务下实现传输与
  编码两层」**。
- §4 五步：①板级引擎映射/时钟投票/中断路由；②实现目标控制器的亮度**编码、写入与回读**（按面板
  连接匹配控制器数量与更新顺序）；③传输完成或取消后才发起下一次，服务请求在**工作循环**处理，
  确认失败处理后再启用渐变调光；④**发布的属性必须与系统接受的请求匹配**——iPadOS 17 用
  `IODisplayParameters` 亮度范围 + `backlight-control` + `brightness` + `FadePeriod`，
  iPadOS 27 还要毫尼特、滑块表、校准参数与 `brightness-nits`；⑤构建服务与注册封装。
- 验收（`display.md:108-114` 原文）：最低/中间/最高设置有对应回读与**可见**亮度、渐变调光完成、
  超时计数稳定；参考实现用 `native_backlight_stats` 记录**发布、请求、回读、中断、失败**；
  控制器写入与系统 UI 调整要分别验证。

## 3. ③反编译/参考实现：`AppleARMBacklight.cpp` 给了什么、K60 不要什么

参考实现 `E:/hackios/UniXNU-sheng/package/AppleARMBacklight.cpp`（468 行，类名 `ShengBacklight`）。

### 3.1 必须照抄的 OS 契约

| 契约 | 参考实现位置 | K60 怎么做 |
|---|---|---|
| CoreBrightness 按 `backlight-control=true` 找服务，从 `IODisplayParameters.brightness` 读 min/max | `:350-366`（publishFirst） | 同：`setProperty("backlight-control", true)` + 发布 `IODisplayParameters` |
| 下发形式 `{brightness, FadePeriod(16.16 秒)}` 走 `setProperties` | `:422-448` | 同：override `IORegistryEntry::setProperties`（`iokit/IOKit/IORegistryEntry.h:655-661` 是虚函数） |
| 亮度域 `kMaxLevel=2047`、FadePeriod 上限 5000ms、步长 16ms | `:31-32` | 同，常量进 `K60BacklightCodec.h` |
| iPadOS 27：`brightness-nits`（signed 16.16）+ 毫尼特/滑块表/校准参数 | `:265-313`、`:422-430` | 同（见 §4 产物 A） |
| 不阻塞 backboardd 亮度线程：请求进原子字 + 1µs 定时器，工作循环取走 | `:400-428`（int-277/278 教训） | 同 |
| 渐变在工作循环的定时器里逐 16ms 线性插值 | `fadeStep`/`beginFade` | 同（编码进 codec 的 `fadeLevel/fadeDbv`） |

### 3.2 必须避开的坑（原文注释）

- **int-229 类名重名**：不能叫 `AppleARMBacklight`，`AppleARMPlatform` 已定义该类，重名注册即
  panic（`AppleARMBacklight.cpp:9-12`）。K60 的平台类是 `ArmDTPlatform : IODTPlatformExpert`
  （`drivers/ArmDTPlatform/ArmDTPlatform.cpp:39,53`），**不是** `AppleARMPlatform`，但预链接镜像里
  确实带着官方 `AppleARMBacklight` 类（`kernel.macho` 里有
  `AppleARMBacklight::setBacklightEnableGated` 等符号串），所以重名风险同样存在 → 我们的类叫
  `K60Backlight`。
- **int-236 只发 `backlight-control` 不满足类一致性**：CoreBrightness 只有在
  `IOObjectConformsTo(service, "AppleARMBacklight")` 成立时才把它当内置屏背光，进而启动 libEDR
  server；否则 QuartzCore 的同步发送持显示服务锁阻塞，**屏幕停止更新**（`:352-360` 注释）。P-62
  当年就是因为这个坑才刻意不发布 `backlight-control`。
  → K60 必须**同时**做 `backlight-control` 与 impersonate（§3.3）。
- **int-275/276 沙箱拒绝对非该类服务设 FadePeriod**：backboardd profile 只允许对
  `AppleARMBacklight` 设亮度键，deny 日志原文
  `deny iokit-set-properties iokit-class:ShengBacklight property:FadePeriod`（`:315-330` 注释）。
  → 必须 impersonate + `setProperty("NativeSandboxGrantProcess","backboardd")`。

### 3.3 impersonate 的机制（K60 照抄形态）

`AppleARMBacklight.cpp:315-345`：`OSSymbol::withCString("AppleARMBacklight")` →
`OSMetaClass::getMetaClassWithName` 取官方元类；arm64e 分支只置标志由手写 `getMetaClass()` 应答；
否则复制 vtable（`kSlots=320`）、把槽位 `kGetMetaClass=7` 换成返回官方元类的函数、`dmb ish` 后换掉
实例的 vtable 指针。

K60 的内核**不是 arm64e**：`scripts/build-xnu-4k-baseline.sh:1257` 的
`ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64`，`__has_feature(ptrauth_calls)` 为假 →
走 vtable 复制分支即可，类定义仍可用标准 `OSDefineMetaClassAndStructors`（实例 vtable 槽 7 已被
换掉，`OSDynamicCast` 到 `K60Backlight` 会失败，所以事件源回调一律 `static_cast`）。

### 3.4 K60 **不需要**的部分

| 参考实现的东西 | 为什么 K60 不需要 |
|---|---|
| GENI I2C 状态机（`GeniI2c.h` 120 行：`GENI_M_CMD0 0x600`、`GENI_M_IRQ_STATUS 0x610`、`GENI_TX_FIFO 0x700`…） | 没有背光 IC，没有 I2C 从地址 0x11 |
| GCC 时钟投票 `kGccVote=0x52008` / `kVoteBits` / `kHalt[]` | 走 DSI 命令 FIFO，DSI 控制器已在扫描出图时上电 |
| SPI 中断挂接 `kSpi[2]={354,466}`、250ms 重试 240 次 | DSI DMA 完成是轮询等待，已有 25ms 超时（`PongDsiPanel.cpp:107-190`） |
| 双引擎（两颗 KTZ8866） | 单 DSI、单面板 |

## 4. K60 需要的四个产物

### 产物 A：参数发布（OS 契约层）

在服务 `start()` 里、**`registerService()` 之前**发布（顺序照 `drivers/PongPower/K60Battery.cpp`
的 `publish()` 注释：「All initial properties must enter the IORegistry before a client can discover
the service.」）：

```
IODisplayParameters = {
  brightness            = { min: 0, max: 2047, value: <当前 level> }
  BrightnessMilliNits   = { min: 2000, max: 500000, value: level*500*1000/2047 }
}
backlight-marketing-table       = int32[3] { 2<<16, 140<<16, 500<<16 }
LmaxProduct                     = 4 字节 16.16（500<<16）
LminProduct / LmidProduct       = OSNumber(2) / OSNumber(140)
backlight-calibration-parameters = { lMin/lMid/lMaxProduct, lMin/lMid/lMaxPanel }（nits<<16）
backlight-control               = true          （impersonate 成功且 k60_backlight_control!=0 才发）
NativeSandboxGrantProcess       = "backboardd"  （同上，int-275/276）
```

依据：`AppleARMBacklight.cpp:265-313`（publish/publishCalibration）、`:350-366`（publishFirst）。

### 产物 B：服务（工作循环 + 请求落地 + 渐变）

- 类 `K60Backlight : public IOService`（`OSDeclareDefaultStructors`/`OSDefineMetaClassAndStructors`）。
- `setProperties(OSObject*)` override：先 `brightness-nits`，否则 `brightness`+`FadePeriod`，
  编码成 `goal` 与 `milliseconds`（用 codec 的 `levelFromNits`/`fadeMsFromFixed`），写原子字
  `gRequest = 1ull<<63 | goal<<16 | ms` 后 `request->setTimeoutUS(1)`，**不阻塞调用线程**。
- 工作循环上的 `requestFired` 取走请求 → `beginFade`；`fadeStep` 每 16ms 用 `fadeDbv()` 算目标
  DBV 并调用 `pong_panel_set_brightness(dbv)`（同一静态归档内直接调用，无链接问题）。
- 计数：`native_backlight_stats[16]` 与 `native_backlight_request[6]`，语义见 §5。

### 产物 C：注册封装（启动钩子 + boot-arg）

- 入口 `void k60_backlight_start(void)`，幂等（`__atomic_exchange_n(&attempted,1u,...)`）。
- boot-arg：`k60_backlight`（默认 1，0 = 完全不启动）、`k60_backlight_control`（默认 1，
  0 = 不发 `backlight-control`/`NativeSandboxGrantProcess`，P-62 的降级开关）、
  `k60_backlight_invert`（默认 0，反相 DBV 兜底）。
- 调用点：`drivers/PongAdreno/PongAdrenoScanout.cpp:42` 的 `pong_scanout_initialize()` 里、
  `pong_panel_bringup()` 成功之后。**理由（决定性）**：`PongAdrenoScanout.cpp:10-19` 注释说明
  `pong_panel_bringup` 必须从本 TU 调用才能把 `PongDsiPanel.o` 拉进静态归档；亮度服务与
  `PongDsiPanel.o` 同在 `libPongAdrenoPlatform.a`，从这里启动同样不受归档扫描顺序影响，
  且不需要像 0393 那样在 `MiniIOSurface.cpp` 里再开一个 extern（`patches/xnu/0393-k60-panel-bringup.patch`）。

### 产物 D：DCS 编码器（host 可验证）

`drivers/PongAdreno/K60BacklightCodec.h`（纯头文件，无 IOKit 依赖）：

- `dbvFromLevel(level)`：`0 → 0`（真关屏），`1..2047 → 1..255`，线性、单调、亮档永不为 0。
- `levelFromDbv(dbv)`：逆变换，用于把回读值报回 OS 域（往返在一个 DBV 步内闭合）。
- `levelFromNits(fixed16_16)`：iPadOS 27 的 `brightness-nits`。
- `fadeMsFromFixed(fixed)`：FadePeriod（16.16 秒）→ 毫秒，上限 5000。
- `fadeLevel(from,to,elapsed,period)` / `fadeDbv(...)`：渐变序列，不越界、正好落在 `to`。
- `applyInvert(dbv, invert)`：`bl-inverted-dbv` 兜底。

单测：`scripts/check-brightness-encoder.py`（编译上述头 + 断言，见 §7）。

## 5. 计数语义（验收判据的落点）

`native_backlight_stats[16]`（沿用参考实现的下标，K60 用不到的位置写 -1 或 0 并在注释里说明）：

| 下标 | 语义 | K60 来源 |
|---|---|---|
| 0 | 阶段：1 已挂接、2 工作循环就绪、3 已发布、4 已以 AppleARMBacklight 发布、负数=失败步 | 同参考 |
| 1 | 亮度请求数 | `setProperties` 每次命中 +1 |
| 2 | 最后写入的 level | `fadeStep` |
| 3 | 回读 level | `pong_panel_brightness()` 反算（见下） |
| 4 | 回读 DBV | `pong_panel_brightness()` |
| 5 | 传输错误数 | `pong_panel_set_brightness()` 返回非 0 |
| 6-9 | GENI 专用 | K60 恒 -1 |
| 10-12 | 中断相关 | K60 恒 -1 / 0（无中断） |
| 13 | 超时数 | DSI DMA 超时由 `PongDsiPanel.cpp` 的 `dsi_failures` 计，本服务转记 |
| 14 | 挂接尝试 | K60 恒 1 |
| 15 | 完成的写入数 | 成功写入次数 |

**回读的诚实说明**：DCS 0x51 是只写命令，面板没有对应的读回命令，K60 也没有背光 IC 寄存器可读。
所以「回读」只能是**已成功写入的 DBV 的软件记录**（`PongDsiPanel.cpp:255` 的
`panel_brightness`），而不是从面板读回的真实值。本方案在 stats 里把「请求值」（[1]）与
「已写入值」（[2]/[4]）分开计数，避免把请求误当回读。真机验收时 min/mid/max 三档的
「回读值不同」判据按此解释：**不同且与请求一致**，可见变化由人眼确认。

## 6. 与 P-62 / int-236 的关系（为什么现在可以做）

P-62（`docs/engineering/PITFALLS.md:808-821`）当时的结论是「只加 `k60_panel_brightness` boot-arg、
刻意不发布 `backlight-control`」，因为 int-236 的教训是「只发 backlight-control 而不满足
`IOObjectConformsTo(service,"AppleARMBacklight")` → 屏幕停止更新」。

本方案把两者一起做：`backlight-control` **只在 impersonate 成功时**才发（`control == 1 &&
impersonate()`），与参考实现 `AppleARMBacklight.cpp:360` 完全同构；impersonate 失败则退化成
P-62 的旧行为（只发 `IODisplayParameters`，不声明 backlight-control），屏幕不会停更。
额外留 `k60_backlight_control=0` 作为一键回退。

## 7. 验证计划

| 层次 | 手段 | 产物 |
|---|---|---|
| 编码器（host） | `python3 scripts/check-brightness-encoder.py`：0..255 映射端点/单调/逆变换、nits 三档、FadePeriod 夹取、渐变序列单调且落点精确 | 本目录 + 脚本输出 |
| 静态（host） | `scripts/build-pong-adreno-platform.py` 编译新增源文件（arm64 kernel target）；`scripts/check-porting-paths.py`；`scripts/eight-step-gate.py --build` | 构建日志 |
| 产物（host） | `scripts/build-strict.sh` 产出 `kernel.macho`，`llvm-nm` 必须出现 `_k60_backlight_start`、`_native_backlight_stats` | `build-manifest.json` + nm 输出 |
| 真机（Lead） | ①上电后 `ioreg -l | grep -i backlight` 能看到 `backlight-control` 与 `IODisplayParameters`；②拖动亮度滑块，日志/计数变化；③`native_backlight_stats[1]` 递增；④min/mid/max 三档 `stats[2]/[4]` 不同且屏上可见；⑤渐变（FadePeriod）无跳变；⑥屏幕不停更（int-236 回归项） | 交给 Lead 执行，本线**禁止自行 boot** |

## 8. 开放问题（诚实标注，勿当结论）

1. 面板 live FDT 的 `bl-max=0xfff`（12 位）与 bring-up 实发的 `0x51 0xff`（8 位）不一致：
   本方案按 **8 位 DBV** 实现（与既有 `pong_panel_set_brightness` 的 0..255 契约一致）。若真机上
   8 位域过粗（255 档在暗端可见跳变），再评估 0x51 双字节 12 位写入——**待验证**，需要面板
   spec 或真机实验，不在本次改动内。
2. `bl-inverted-dbv` 是否在本面板上真的生效：bring-up 发 `0xff` 后面板亮，说明默认不反相；
   仍留 `k60_backlight_invert` 兜底，**待真机验证**。
3. iPadOS 27 的 `brightness-nits` 路径在本机（iPadOS 16.6.1 20G81）不会被使用，属于前瞻实现，
   仅由 host 单测覆盖，**待未来系统验证**。
