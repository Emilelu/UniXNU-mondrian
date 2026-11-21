# 触摸 16 → 27 注入契约差异（对称表）

一句话结论：**报告内容与"服务身份"不变，变的是注入通道的所在侧**——16.6.1 由用户态 backboardd 侧造
`IOHIDEvent` 对象、经虚拟 HID 服务派发；27 的内核 IOHIDFamily 里**没有** `IOHIDEventCreate*` 工厂
（`IOHIDEvent.h` 内 grep 0 命中），注入必须改由内核 `IOHIDDevice` 子类提交 **report 描述符**，并且
两处 27 专有动作不可省：`DigitizerCollectionDispatch` 属性、以及 `0x800` edge-tip 位（27 的
IOHIDFamily 源码里 `FromEdgeTip` **0 命中**，得靠槽位包装补）。

判据口径：每行给「16 侧 `文件:行` / 27 侧 `文件:行` 或『27 侧不存在』」；只凭 sheng 参考实现推出、
本机 27 树内无法直接核的，逐条标「按 sheng 的推算，待 27 侧 X 验证」。

## 一、报告格式（进 HID 的东西长什么样）

| # | 项目 | 16 侧（file:line） | 27 侧（file:line） |
| --- | --- | --- | --- |
| 1.1 | 有没有 HID 报告描述符 | **没有**。16 不提交 report，直接造事件对象：`userland/touch.c:261` 造 hand 事件、`:270` 造 finger 事件 | **有，且是唯一通道**。`drivers/ShengHidInput/NativeHidInput.cpp:33-60` 三份描述符；触摸是 report 3：10 个 finger（Tip Switch、`0x47` Touch Valid、Contact ID、X/Y 各 16 位、0..0x7fff）+ Contact Count |
| 1.2 | 触摸事件族的 transducer / usage | 定制页 `0x0d`/usage `0x04`（Digitizer/Touch Screen，DisplayIntegrated）：`userland/touch.c:70` `DIGITIZER_HAND 3`、`:261` 作为 hand 的 transducer 传入 | 由描述符决定：`NativeHidInput.cpp:33-60` 的 digitizer 集合；27 侧内核消费点 `IOHIDFamily/IOHIDEventDriver.cpp:1123` 认 `kHIDUsage_Dig_TouchPad`/vendor DFR/`DigitizerCollectionDispatch` 三条路 |
| 1.3 | 触点编号 | `userland/touch.c:270`：`index = i+1`、`identity = i+2`（1 基 vs 2 基，刻意错开） | 描述符里 Contact ID 8 位（`NativeHidInput.cpp:33-60`）；sheng 提交 `id & 0xff`（`NativeHidInput.cpp:246-482` 的 touchSend 内） |
| 1.4 | 触点上限 | `userland/touch.c:78` `MAX_FINGERS 10`；`:239` 越界丢弃 | 描述符固定 10 个 finger（`NativeHidInput.cpp:33-60`）；**27 侧无 K60 专属上限**，沿用 10 |
| 1.5 | 坐标刻度 | 内核给原始坐标，用户态归一：`userland/touch.c:251-252` 用 `PONG_TOUCH_COORD_MAX` 除；hand 事件带上归一值 `:261-262` | 描述符声明 0..0x7fff；生产者归一：sheng `transformCoordinate` = `value*32767/(max-1)`，max 取 30480×20320（`NativeHidInput.cpp:246-482`） |
| 1.6 | DisplayIntegrated 字段 | `userland/touch.c:76` 定义 `0xb0019`，`:264` 设在 hand、`:274` 设在每个 finger | **27 侧不存在该整数字段路径**：27 内核 feed 里没有 `IOHIDEventSetIntegerValue` 式字段写入（`IOHIDEvent.h` 无 `IOHIDEventCreate*`）；显示内嵌由描述符/服务属性表达 |
| 1.7 | IsBuiltIn 字段 | `userland/touch.c:265` 设 `0x4` | 同上：27 无该字段写入点；等价物是服务属性 `Built-In`（`NativeHidInput.cpp:453` 区段） |
| 1.8 | 集合派发（多指是否一个 hand） | 由 16 的"hand 事件 + append finger"表达：`userland/touch.c:261`、`:270`、`:276` append、`:278` 一次 dispatch | **必须显式开**：`IOHIDFamily/IOHIDEventDriver.cpp:1123` 只有 `conformTo(...TouchPad)`/vendor DFR/`getProperty(kIOHIDDigitizerCollectionDispatchKey, gIOServicePlane)==kOSBooleanTrue` 三者之一成立才 `_digitizer.collectionDispatch = true`；属性发布在 `:1132`。sheng 在 `NativeHidInput.cpp:453` 区段设 `DigitizerCollectionDispatch`，注释说明了不设的后果（一次触摸被当成整个触点集 ⇒ 无缩放、无系统手势） |

## 二、载体（谁把报告送进 HID 栈）

| # | 项目 | 16 侧（file:line） | 27 侧（file:line） |
| --- | --- | --- | --- |
| 2.1 | 内核 → 用户态的通道 | 阻塞字符设备 `/dev/pong-touch`：`bsd/dev/pong_input.c:96` `cdevsw_add`、`:98` `devfs_make_node`、`:17` `QUEUE_SIZE 512`、`:30` `pong_touch_post`、`:36-37` 环形队列 + 写入 `mach_absolute_time()`、`:40` `wakeup`、`:68-77` 读侧 `msleep` | **27 侧不存在**：27 XNU feed 内无 `bsd/dev/pong_*`（本线重放补丁前）；27 上这条通道被内核 HID 设备取代 |
| 2.2 | 用户态注入 API | `IOHIDVirtualServiceClientCreateWithCallbacks`：`userland/touch.c:213`（原型 `:45-46`，回调结构 `:24`/`:158`） | **27 侧不存在于内核 feed**：27 IOHIDFamily feed 内无 virtual-service 客户端 API（`tools/IOHIDEventSystemMonitor.c:424` 只是监视器内部变量名）。用户态侧是否有等价 API 属 IOKit 框架，**待 27 侧验证** |
| 2.3 | 内核注入 API | 16 不注入 HID（只投递到字符设备） | `IOHIDDevice` 子类 + `handleReport`：声明 `IOHIDFamily/IOHIDDevice.h:509-517`（`virtual IOReturn handleReport(IOMemoryDescriptor*, ...)`），实现 `IOHIDFamily/IOHIDDevice.cpp:1494` → `handleReportWithTime`（`:1508`）；sheng 的调用点在 `NativeHidInput.cpp:246-482`（`NATIVE_HID_SOURCE_API` 下传 `kIOHIDReportTypeInput`） |
| 2.4 | 服务身份属性 | `userland/touch.c:188-205`：`PrimaryUsagePage/PrimaryUsage/DeviceUsagePage/DeviceUsage/DeviceUsagePairs`、`Built-In`、`Transport`（显示内嵌时 `"SPI"`）、`Manufacturer`、`Product`、`VendorID/ProductID`、`DisplayIntegrated`（`:204`） | 27 由 kext 的服务属性/描述符表达：`NativeHidInput.cpp:446` 先 `setProperty("HIDDefaultBehavior", true)`，`:453` 区段设 Built-In/DisplayIntegrated/DigitizerCollectionDispatch；`newTransportString()` = `"SPI"`（触摸单用）/`"Virtual"` |
| 2.5 | 服务创建重试 | `userland/touch.c:212-227`：20 次重试、每次等 2 s，等 `DeviceOpenedByEventSystem` 置位；失败打 `Pong touch HID: the event server has not opened …` | 27 侧无对应重试（内核 `start()` 一次性成功/失败）；**这是行为差异**，见 2.6 |
| 2.6 | 打开时机依赖 | 16 依赖事件服务器先起来（backboardd 已跑） | 27 内核侧 `start()` 早于 backboardd；显示内嵌属性必须自描述，否则事件在服务器起来前无处可去。**按 sheng 的推算，待 27 侧 IORegistry/backboardd 验证** |
| 2.7 | 唤醒（tap-to-wake）服务 | 独立的 consumer 服务（页 `0x0c` usage `0x01`）+ `tap_wake()`：`userland/touch.c:286` 注释、`:291-296` 发 `0x30` Power 键盘事件；`TouchDetectionMode` 低字节 1/0xfe/0xff（`:119`、`:140`） | 27 侧该服务与模式位**在内核 feed 内不存在**；由 backboardd/IOHIDEventSystem 侧负责。**待 27 侧验证**（与 buttons 契约差异表同一条待验项） |

## 三、取样（多久取一次、靠什么触发）

| # | 项目 | 16 侧（file:line） | 27 侧（file:line） |
| --- | --- | --- | --- |
| 3.1 | 中断还是轮询 | **轮询**。`bsd/dev/pong_goodix.c:445-447`「Local status sources stay enabled for polling; no interrupt output is enabled toward the GIC」，`:1256`「No TLMM interrupt is installed」；循环 `sleep_ms(8)`（`:1333` 区段） | 27 侧无 K60 触摸驱动（补丁未重放）；27 的 IOHIDEventDriver 只消费报告，不决定取样节奏。**沿用 16 的轮询设计**，除非上机证明需要 IRQ |
| 3.2 | 一帧到事件的映射 | `pong_goodix.c:1091`（UP）、`:1113`（DOWN/MOVE）、`:1125`（UP）三处 `pong_touch_post`；`bsd/dev/pong_input.c:30` 写入 ring | 27 侧对应物是 sheng 的 seqlock 快照 + `touchSend()`（`NativeHidInput.cpp:246-482`）：seq 为奇或未变则跳过、撕裂重读。**K60 移植应复用该模式**，不要直接照搬 16 的 ring |
| 3.3 | 抬指语义 | 16 用 `PONG_TOUCH_UP` 显式上报（`pong_goodix.c:1091`/`:1125`） | 27 描述符里 tip 位 2 表示抬起；sheng 对"消失的 id"补发 tip-up，按 **id 而不是槽位**匹配（`NativeHidInput.cpp:246-482`） |
| 3.4 | 失败/断流处理 | `pong_goodix.c:1320-1333`：复位后身份丢失即停轮询；连续 8 次真实失败才发 release（注释明确"不靠定时器或 IRQ 电平臆造触点"） | 27 侧无对应代码；移植时同一条铁则要保留（不许凭空发 release），否则 backboardd 会看到幽灵触点 |

## 四、新回归陷阱（16 上没有、27 上会出现）

| # | 陷阱 | 为什么在 27 才出现 | 判据 / 对策（file:line） |
| --- | --- | --- | --- |
| 4.1 | 少设 `DigitizerCollectionDispatch` | 16 用"hand + append"天然表达集合；27 由 IOHIDEventDriver 决定，默认给 Touch Screen 的集合派发是**关**的（`IOHIDEventDriver.cpp:1123` 三个条件全不满足时） | 判据：`IOHIDEventDriver.cpp:1132` 发布的 `Digitizer/collectionDispatch` 必须为真；对策：服务属性显式置上（sheng `NativeHidInput.cpp:453` 区段） |
| 4.2 | 27 不接受 `0x800` edge 位（源码里没有这个位） | 16 是用户态自己 `or` 进 finger mask（`userland/touch.c:74` 定义、`:271` 使用）；27 的 IOHIDEventDriver 源码内 `FromEdgeTip` **0 命中**，即使描述符也不会产生该位 | 对策：在 dispatch 槽（sheng 取 `kDispatch=198`，`NativeHidInput.cpp:84-244`）包装补位；UIKit 由 `0x800/0x1000/0x2000/0x40000` 推 edge 类型 1..4（sheng 注释）。**补强（2026-11-22 查库）**：同一内核注入路径在 17.7.11 的移植上已实测成立——`docs/devices/sirius-dddqmmx.md:366` 记录 `NativeHidInput::edge::mark` 置位后 `from_edge = 8`、底部边缘 Consumer Menu `0x40` 解锁进入 Home（kernel `e7c1f9eb`/`3b36199b`，payload `44f26ef0`/`ddd8d1fa`）。所以「内核侧补位这条路走得通」不再是推算（该页出处已查：`dddqmmx/UniXNU-sirius` 为 `57UU/UniXNU-sirius` 的 fork，`57UU` 本身 `fork=false`，2026-11-22 GitHub API 实测——不是我自己仓库的 fork，但它跑的是 17.7.11，不是 27）。**待验对象**：24A446 kernelcache 里 `IOHIDEventDriver` vtable 槽 198 的 diversity 是否等于 sheng 表里的 `kSlotDiversity[198] = 0x1134`（读法见 `E:/hackios/UniXNU-sheng/scripts/gen-hid27-abi.py` 的 fixup 遍历），以及我们自己的 `edge install` 计数是否记为 1 |
| 4.3 | Touch Valid = 0 被当成手掌 | 16 没有该位；27 描述符有 `0x47`，而 IOHIDEventDriver 把 0 解释为 hand/palm（sheng 描述符注释） | 对策：每个 finger 恒发 1（`NativeHidInput.cpp:33-60` 注释） |
| 4.4 | arm64e 上 vptr 未签名 → 包装即崩 | 16 无槽位包装、无这一层 | 对策：`NativeHidInput.cpp:84-244` 的 vptr 认证 + 每槽 IA-key 重签；`kSlotDiversity` 逐槽比对，不一致就不动 |
| 4.5 | 继续用 16 的字符设备 + 用户态虚拟服务 | 27 内核 feed 内无 virtual-service 客户端 API（2.2 行），且用户态注入要求 backboardd 插件 | 对策：27 走内核 `IOHIDDevice` 子类；`/dev/pong-touch` 只在"保留 16 行为做对照"时才有意义 |
| 4.6 | 只搬驱动不带 sink | 16 的 `pong_touch_post` 由 `pong_input.c` 提供（`bsd/dev/pong_input.c:30`）；27 上这条链路要换成"驱动 → sink 回调 → IOHIDDevice"，缺一环就只剩 ring 自嗨 | 对策：`native_touch_set_sink`（sheng `package/TouchProbe.cpp:342`）模式；K60 侧对应 `pong_touch_post` 改为触发 sink |

## 五、既有资产（不在 27 重做）

| 资产 | 16 侧证据 | 27 侧状态 |
| --- | --- | --- |
| SPI 传输空指针守卫 | `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch:669-676` `spi_transfer_unset()` 打印 `Pong touch: serial transport is not up yet` 并返回 false；`:678-679` 它是 `static bool (*spi_transfer)(const uint8_t*, uint8_t*, uint32_t)` 的默认值 | **27 侧不存在**（补丁未重放）；重放即带上，无需新写 |
| 位翻转时序与上限 | `pong_goodix.c:613` `bb_delay_us = 2`、`:618` `sleep_us(bb_delay_us)`、`:626` 注释「explicit half-cycle delays bound GPIO SPI to at most 500 kHz」 | 同上，随补丁重放 |
| GENI 分频与时钟打印 | `pong_goodix.c:464` `divider = (se_source_hz + hz - 1) / hz`、`:468` 打印 `SPI<=%u Hz`、`:1345` 默认 `hz = 4000000`、`:1354` boot-arg `k60touchhz`、`:1357` 上限 15 MHz | 同上 |
| 配置完成判据 | 补丁 `:1031-1032` `if (reply[0] == 0x80)` 才算完成，`:1037` 超时；`:1046-1048` `goodix_command(5, 0x91, &coordinates_on, 1, "COORD-ON")` | 同上；这两条是 16.6.1 上机的真因，27 不要再"重新发现"一次 |
| **口径更正** | 「333 kHz」在 16 驱动源码里**没有字面值**：默认 `hz = 4000000`（`:1345`），boot-arg 可改（`:1354`），位翻转路径由 `bb_delay_us=2` 限到 ≤500 kHz（`:626`）。`docs/research/touch/GROUND-TRUTH.md:90` 已注明该数字是配置值而非波形实测 | 27 侧要沿用**这套边界**（半周期 2 µs、divider 计算、4 MHz 默认、15 MHz 上限），不要沿用「333 kHz」这个数 |

## 六、按「依据 + 待验对象」写清的两条未证（Lead m01829 口径：不许写没有对象的「待 27 侧验证」）

### 6.1 `home-button-type = 2` 的语义传导

- **依据**：`E:/hackios/UniXNU/docs/guide/mobilegestalt.md:27`（属性表：`home-button-type` = `2` · 无机械 Home 键，用滑动手势）、`:36` 节「Full-screen gestures」、`:44`「SpringBoard 通过 `BSPlatform homeButtonType` 读取该值。值为 2 时，锁屏使用上滑手势」。ADT 侧这一段已经闭合：`/buttons` 四字段在 27 生成的 ADT 里逐字节存在（`docs/research/ios27/adt-27-buttons-check.md`，16,648 B / 26 节点）。
- **待验对象**：① 24A446 的 SpringBoard 可执行文件里有没有 `homeButtonType` 这个选择器/字符串（`strings -a .../SpringBoard | grep -c homeButtonType`，二值结论）；② 上机后锁屏能不能**上滑解锁**（一次动作，成功/失败）。判真判假的顺序是 ① 先成立，再看 ②。

### 6.2 内核注入的 consumer/digitizer 设备是否被 27 backboardd 直接接受

- **依据**：27 的 stock 路径本身就是内核 HID 设备（`IOHIDDevice.cpp:1494` `handleReport(IOMemoryDescriptor * report, …)`）；sheng 是唯一同 OS profile（`ipados-27.0.1-24A446`）且**独立**的实现（`E:/hackios/UniXNU-sheng` @ a68ee4e），其 `start()` 只额外要求 `HIDDefaultBehavior`（`NativeHidInput.cpp:446`）。
- **待验对象**：① 上机后 `ioreg -p IOService -c IOHIDDevice -r -n "Offline HID input probe"` 的实例与属性行（`Built-In`、`DisplayIntegrated`、`Transport`）；② `ioreg -p IOService -c IOHIDEventDriver` 下有没有该设备对应的 event driver 实例。两条都是 IORegistry 的具体行，不再写成「待 27 侧验证」。

## 七、引用索引

- 16 侧：`userland/touch.c`（本仓）、`bsd/dev/pong_goodix.c`、`bsd/dev/pong_input.c`（16.6.1 构建树
  `/opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`）、
  `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`。
- 27 侧：`/opt/k60/trees/ios27-out/feeds/IOHIDFamily-f53ac321/IOHIDFamily/{IOHIDEventDriver.cpp,IOHIDDevice.h,IOHIDDevice.cpp,IOHIDEvent.h}`；
  sheng 参考实现 `drivers/ShengHidInput/NativeHidInput.cpp`、`package/TouchProbe.cpp`。
- 官方口径：`docs/zh/porting/input.md:19/:56/:58/:61/:65`（§1–§3：同一帧取坐标/ID/计数、`DigitizerCollectionDispatch` 类的派发语义、`sheng-touch-hid=1` 启用触发布路径）。
