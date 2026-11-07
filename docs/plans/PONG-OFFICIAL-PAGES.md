# Pong 官方设备页精读：逐域实现方案（Nothing Phone 2 / SM8475）

> 范围：只读精读 `E:/hackios/UniXNU/docs/devices/` 下全部 `pong*.md` 设备页及 `index.md` 的 pong 行；只产出本文件，不改任何代码。
>
> 参照树：`Chengdong-Yu/UniXNU-pong`，commit `e0ee6df109b4b5dc706cac660d4f8210dc911dac`（iPadOS 18.7.10 / 22H374 / Darwin 24）。
>
> 目标对照：`mondrian`（Redmi K60，SM8475，iPadOS 16.6.1 / 20G81 / Darwin 22）。pong 的硬件事实与组件拆分可借用，22H374 的 ABI/偏移不可照抄。
>
> 证据标签：`PAGE` = 设备页原文；`TOML` = 同 commit 的 `porting.toml`；`CFG` = `configs/pong-*-sm8475.json`；`REPO` = 本地 `E:/hackios/UniXNU-pong`；`未核实` = 页面没有给出。

## 0. 一页结论

1. 五个 `pong*.md` 文件里只有两个是真正的 pong 设备记录：`pong.md`（Chengdong-Yu）和 `pong-agxmx666.md`（AGXMX666）。`pong-hxzbaka.md`、`pong-y3d4.md` 只有一行仓库链接；`pong-kmu1757.md` 是误放在 pong 前缀下的 Galaxy Tab S7+ / S20+ SM8250 页面，不是 Nothing Phone 2。
2. `pong.md` 是唯一完整页：1567 行、32 个 `##` 区域（13 个核心域 + 19 个追加域）、186 条 Evidence 链接（74 个去重路径），证据文件覆盖 services73 → services167（页内多处引用 services72 的设备状态）；所有区域 `status = implemented`。
3. `pong-agxmx666.md` 是早期快照：523 行、13 个区域、14 条链接（3 个去重路径），只覆盖 services72 → services73。它能作为最小 bring-up 基线，但没有 GPU / Display / Network / Audio / Power 的后期实现细节。
4. `implemented` 的含义是“该域的实现/构建记录已建立”，不是“已在真机验收”。每个核心域的 Completion criteria 都写着“在设备上观察该接口的实际工作结果并保存对应日志”，大量 findings 以“设备结果待确认 / 待观察”结尾。
5. 对 mondrian 的直接借鉴顺序：先抄 `pong.md` 的 GPU → Display → Network → Audio → Power 证据链；抄硬件常量、组件拆分、初始化顺序和故障边界，不抄 22H374 的 ABI/偏移。

## 1. 阅读清单与 status 对照

### 1.1 页面元数据

| 文件 | H1 标题 | Format | Documentation（index.md） | 仓库 | 钉住 commit | 可见区域 | Evidence 链接 |
|---|---|---|---|---|---|---|---|
| `pong.md` | Nothing Phone (2) (pong) | 2 | Porting record | `Chengdong-Yu/UniXNU-pong` | `e0ee6df109b4b5dc706cac660d4f8210dc911dac` | 32 个 `##`（13 核心 + 19 追加） | 186 条 / 74 个去重路径 |
| `pong-agxmx666.md` | Nothing Phone (2): UniXNU UEFI bring-up (AGXMX666) | 2 | Porting record | `AGXMX666/UniXNU-pong` | `ffdad781cb16b42a1fb5c984f77998253b821d8c` | 13 | 14 条 / 3 个去重路径 |
| `pong-hxzbaka.md` | 无 H1，只有仓库链接 | 1 | Repository link | `hxzbaka/UniXNU-pong` | — | 0 | 0 |
| `pong-kmu1757.md` | Galaxy Tab S7+ (SM-T970) / S20+ (SM-G986N) SM8250 bring-up (kmu1757) | 2 | Record pending | `kmu1757/UniXNU-y2q` | — | 0（7 行占位，含 `device.soc must match board.toml` 错误） | 0 |
| `pong-y3d4.md` | 无 H1，只有仓库链接 | 1 | Repository link | `Y3d4/UniXNU-pong-clean` | — | 0 | 0 |

`index.md:179-183` 的五行为：

- `pong`：SM8475 / Format 2 / Porting record / `Chengdong-Yu/UniXNU-pong`
- `pong-agxmx666`：SM8475 / Format 2 / Porting record / `AGXMX666/UniXNU-pong`
- `pong-hxzbaka`：SM8475 / Format 1 / Repository link / `hxzbaka/UniXNU-pong`
- `pong-kmu1757`：SM8250 / Format 2 / Record pending / `kmu1757/UniXNU-y2q`
- `pong-y3d4`：SM8475 / Format 1 / Repository link / `Y3d4/UniXNU-pong-clean`

### 1.2 十三域 status 对照

| 域 | `pong.md` | `pong-agxmx666.md` | `pong-hxzbaka.md` | `pong-kmu1757.md` | `pong-y3d4.md` |
|---|---|---|---|---|---|
| Configuration | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Firmware and boot | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| CPU and interrupts | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Memory and DMA | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Storage and root | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Display | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Input | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| GPU | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Network | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Audio | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Power | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Image assembly | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |
| Diagnostics | `implemented` | `implemented` | 无记录 | 无记录 | 无记录 |

### 1.3 `pong.md` 的 19 个追加区域（全部 `implemented`）

| # | 区域 | 主题 |
|---|---|---|
| 1 | `mobilegestalt-device-information` | USB 型号/容量/MobileGestalt 设备信息 |
| 2 | `native-category-volume` | 原生媒体/铃声分类音量 |
| 3 | `native-ringtone-display-wake` | 原生铃声、显示唤醒与 alpha |
| 4 | `main-gpu-metal-ringer149` | 主 GPU/Metal 与铃声选择器 |
| 5 | `adreno-ringer-freeze150` | Adreno 铃声冻结修复 |
| 6 | `control-center-native-ringtone151` | 控制中心与原生铃声转码 |
| 7 | `upstream-metal-keyboard152` | 上游 Metal 与原生键盘 |
| 8 | `gpu-guide-memory-bgra153` | GPU 指南、内存与 BGRA |
| 9 | `gpu-real-execution-hotpath155` | GPU 真实执行热路径 |
| 10 | `metal-interface-ui-stalls156` | Metal 接口与 UI 卡顿 |
| 11 | `gpu-priority-timing160` | GPU 频率、优先级与时间线 |
| 12 | `audio-wake-active-acquire162` | 唤醒音频与 active acquire |
| 13 | `audio-prepare-command-stages163` | 音频 prepare 命令阶段 |
| 14 | `lock-sound-admission164` | 锁屏音与 admission |
| 15 | `scheduling-metal-audio-clock165` | Metal 调度与音频时钟 |
| 16 | `submit-retirement-publication166` | 提交/退休发布顺序 |
| 17 | `frame-ownership-pac167` | 帧所有权与 PAC |
| 18 | `local-runtime-integration` | 本地运行时集成 |
| 19 | `cumulative-runtime-pr167` | 累积运行时 PR |

### 1.4 `implemented` 的读法

- `pong.md:71-77`（Configuration）给出的 Completion criteria 是：“在设备上观察该接口的实际工作结果并保存对应日志”。这一定义贯穿 13 个核心域。
- `porting.toml` 的 evidence 带 `reported_kind = "host-build"`、`"device-capture"`、`"device-boot"`。`implemented` 只说明该轮构建/记录已写入，未说明对应硬件路径通过验收。
- 例：`pong.md` 的 GPU 域 Current limits 是“未进行性能基准；尚未取得services82设备帧率或稳定性结果”；Audio 域是“实体PCM播放尚未确认”；Network 域是“扫描已确认；设置列表、关联与IP联网仍需新一轮实机结果”。这三个域都标 `implemented`。

## 2. 十三域逐域抽取

> 每域依次给出：status / 组件与 Procedure / Current limits / Development findings 原文 / Evidence 文件。`pong-agxmx666.md` 的 Procedure 与 `pong.md` 基本逐字相同，表格中以“同左”标注；不同处单独写出。

### 2.1 Configuration（`pong.md:48-90`；`pong-agxmx666.md:29-66`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | 选择 ARM64、SM8475、22H374 和 Pong 四层配置，数组完整列出。 | 同左 |
| Current limits | SM8475公共层与Pong聚合源码分目录固定；平台组件进一步拆分待完成。 | 同左 |
| 实现落点（TOML paths） | `board.toml`、`feeds.toml`、`unixnu.lock`、`.gitmodules`、`configs/**`、`dts/**`、`migration/format2/**`、`scripts/*format2*`、`scripts/*native*sources*`、`scripts/pong_native_inputs.py`、`scripts/build-pong-profile-kernel.py`、`.github/workflows/**`、`README.md`、`README_EN.md` | — |

**Development findings — `pong.md`（原文）**

- 格式2原生构建依赖已补齐公开固定来源、local.toml路径和配置前置条件；本轮为未发布的本地源码审计。
- drivers/ 下 12 个板级驱动已拆到 Chengdong-Yu/pong-\* 独立仓库并以 submodule 引用，路径名不变；AdrenoMetal 仍 pin 上游 c6d29ca。

**Development findings — `pong-agxmx666.md`（原文）**

- 格式2解析、DTS编译、Darwin24内核及启动镜像构建成功；公开源固定版本已补齐。

**Evidence**

- `pong.md`：`README.md`、`migration/ipados18/services136-usb-mux-manual-reset-audio.md`、`services129-prm-usb-dma.md`、`services74-source-audit.md`、`services76-upstream-audit.md`。
- `pong-agxmx666.md`：`migration/ipados18/services73-smmu-audio.md`。

### 2.2 Firmware and boot（`pong.md:91-129`；`pong-agxmx666.md:67-104`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | 复用 Pong UEFI，DarwinBoot24 接管真实可分配区间并使用 PSCI。 | 同左 |
| Current limits | 固件输入与UEFI源码在独立仓库。 | 同左 |
| 实现落点（TOML paths） | `drivers/DarwinBoot24/**`、`scripts/build-darwinboot24*` | — |

**Development findings — `pong.md`（原文）**

- 现有设备可进入桌面，物理内存与可分配内存分别记录。
- drivers/DarwinBoot24 改为 Chengdong-Yu/pong-darwin-boot24 submodule，路径与构建脚本不变。

**Development findings — `pong-agxmx666.md`（原文）**

- 现有设备可进入桌面，物理内存与可分配内存分别记录。

**Evidence**

- `pong.md`：`migration/format2/README.zh.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

### 2.3 CPU and interrupts（`pong.md:130-172`；`pong-agxmx666.md:105-142`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | 使用 0x000..0x700 affinity、GICv3 和 19.2 MHz timer。 | 同左 |
| Current limits | 请求频率并非持续有效频率测量；未运行性能基准。 | 没有声明新的多核稳定性测试结果。 |
| 实现落点（TOML paths） | `drivers/ArmCpu/**`、`drivers/ArmDTPlatform/**`、`scripts/build-pong-armcpu*`、`scripts/build-pong-platform*` | — |

**Development findings — `pong.md`（原文）**

- services90基于services89八核first boot完成记录，新增非RT/非绑定线程的空闲核心排序X2→A710→A510；保留全部native推荐核心、RT和绑定规则，编译通过，实机性能待确认。
- services81实际启动8核，EPSS最高非boost请求为CPU0-3 1804800kHz、CPU4-6 2496000kHz、CPU7 2995200kHz；性能问题不能简单归因于没有开启多核。
- drivers/ArmCpu、drivers/ArmDTPlatform 改为 Chengdong-Yu/pong-arm-cpu、pong-arm-dt-platform submodule。

**Development findings — `pong-agxmx666.md`（原文）**

- CPU 4/3/1 拓扑保持 SM8475；受管内存沿用已启动实现。

**Evidence**

- `pong.md`：`services99-speaker-network-data.md`、`migration/format2/README.zh.md`、`services75-performance.md`、`services82-runtime-performance.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

### 2.4 Memory and DMA（`pong.md:173-212`；`pong-agxmx666.md:143-180`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | 从实际不连续 DRAM 和保留区接管已取得所有权的 RAM。 | 同左 |
| Current limits | 尚未接通全部物理内存。 | 同左 |
| 实现落点（TOML paths） | `configs/pong-memory-sm8475.json`、`drivers/PongAdreno/ArmSmmu4K/**` | — |

**板级参数（`CFG:configs/pong-memory-sm8475.json`）**

- `physical_bytes = 12884901888`（12 GiB）。
- 六段 DRAM：`0x80000000` / `0x6a000000`；`0xf1400000` / `0xec00000`；`0x800000000` / `0x39900000`；`0x839f00000` / `0x1e00000`；`0x840000000` / `0xc0000000`；`0x900000000` / `0x180000000`。
- 保留区分段管理；页面明确“不能将物理空洞分配给 VM”。早期受管容量 9728 MiB。

**Development findings — `pong.md`（原文）**

- 物理容量12GiB；此前受管容量9728MiB，不能将物理空洞分配给VM。
- drivers/PongAdreno/ArmSmmu4K 随 PongAdreno 迁到 Chengdong-Yu/pong-adreno submodule。

**Development findings — `pong-agxmx666.md`（原文）**

- 物理容量12GiB；此前受管容量9728MiB，不能将物理空洞分配给VM。

**Evidence**

- `pong.md`：`services99-speaker-network-data.md`、`migration/format2/README.zh.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

### 2.5 Storage and root（`pong.md:213-254`；`pong-agxmx666.md:181-218`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | 原生 UFS + 22H374 IOStorageFamily，独立 OS/SystemOS/Data 窗口。 | 同左 |
| Current limits | 分区与镜像输入本地保存。 | 同左 |
| 实现落点（TOML paths） | `drivers/NativeUfs/**`、`scripts/*ufs*`、`scripts/*storage*`、`scripts/*os-delta*` | — |

**板级参数（`REPO:README.md:37`）**

- `NativeUfs`：SM8475 UFS host `0x01d84000`、SID `0xe0`、SPI 265；`SHNGROOT v1` 三窗口（OS/SystemOS/Data）。

**Development findings — `pong.md`（原文）**

- 8GiB可写UFS Data已有启动记录；本轮只准备本机OS更新，未写入手机。
- drivers/NativeUfs 改为 Chengdong-Yu/pong-ufs submodule；RootLayout 与 SmmuTakeover 路径不变。

**Development findings — `pong-agxmx666.md`（原文）**

- 8GiB可写UFS Data已有启动记录；本轮只准备本机OS更新，未写入手机。

**Evidence**

- `pong.md`：`services130-root-smmu-order.md`、`services116-runtime-adapters.md`、`services99-speaker-network-data.md`、`services73-smmu-audio.md`。
- `pong-agxmx666.md`：`services73-smmu-audio.md`。

### 2.6 Display（`pong.md:255-309`；`pong-agxmx666.md:219-256`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | Pong 1080x2412、stride4320；DCS背光和原有显示服务。 | 同左 |
| Current limits | 120Hz为显示模式；新一轮实际帧率与滑块调光未确认。 | 实际高刷新率和背光仍需设备反馈。 |
| 实现落点（TOML paths） | `configs/pong-display-sm8475.json`、`drivers/PongPower/PongBacklight*`、`scripts/*display*` | — |

**Development findings — `pong.md`（原文）**

- services83驱动耗时约40–52ms/帧；services84复用线性纹理并将scanout导入限定为三帧，保留缓存维护和真实fence。
- services85 DBV写入后回读32并永久停用；services86加入LP优先、锁存等待和有界重试，保留真实错误及后续请求。
- services86显示服务连续SIGSEGV引发SpringBoard/replicatord退出；services87修复GPU连接所有权回退，桌面结果待实机确认。
- services87 写00b4后读22/00/b4，services88修正GET字节序，保留原始DBV和真实错误，允许后续请求。
- drivers/PongPower/PongBacklight\* 随 PongPower 迁到 Chengdong-Yu/pong-power submodule。

**Development findings — `pong-agxmx666.md`（原文）**

- 桌面与壁纸已有显示；120Hz是请求值，不代表测得帧率。

**Evidence**

- `pong.md`：`services142-wake-usb-audio.md`、`services132-wake-usb-ownership.md`、`services112-wifi-audio-phone-input.md`、`services110-adsp-poster-textinput.md`、`services107-interface-namer-handshake.md`、`services98-first-frame-launch-policy.md`、`services97-native-endpoint-handoff.md`、`migration/format2/README.zh.md`、`services82-runtime-performance.md`、`services83-official-peripherals.md`、`services84-peripheral-interfaces.md`、`services85-backlight-startup.md`、`services88-native-peripherals.md`、`services92-peripherals-latency.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

### 2.7 Input（`pong.md:310-360`；`pong-agxmx666.md:257-294`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | Goodix Berlin-D，PM8350实体按键转HID/原生音量控制。 | 同左 |
| Current limits | 短按和音频联动需设备确认。 | 音量实际生效及独立电源按下/释放后的锁屏动作尚未确认。 |
| 实现落点（TOML paths） | `userland/touch.c`、`userland/touch.h`、`patches/xnu-ipados18/**`、`drivers/GoodixTouch/**`、`userland/ui_compat18.c` | — |

**Development findings — `pong.md`（原文）**

- services83已有真实音量按下/释放与共享增益更新；services84将待确认边沿的去抖读取缩短为8ms，回退轮询16ms。
- services86实体gain显示独立短暂HUD，达到上下限停止重复，保留PMIC transition来源。
- services88删除notify直改增益/HUD，实体音量键经标准键盘/Consumer报告进入原生HID parser；电源与触控路径保留。
- 用户确认services112系统输入法正常；该结论不等于音量键已验证。services113保留原输入法和按键实现。

**Development findings — `pong-agxmx666.md`（原文）**

- services72真实音量press/release到达SBVolumeControl，电源down到达Consumer HID；本轮核对22H374事件接口，未新增虚构设备。

**Evidence**

- `pong.md`：`services133-parity-audio-usb.md`、`services110-adsp-poster-textinput.md`、`services109-audio-plugin-keyboard.md`、`services74-source-audit.md`、`services82-runtime-performance.md`、`services83-official-peripherals.md`、`services84-peripheral-interfaces.md`、`services88-native-peripherals.md`、`services92-peripherals-latency.md`、`services94-native-volume-wlan.md`、`services95-hid-driverkit-wait.md`。
- `pong-agxmx666.md`：`services73-smmu-audio.md`。

### 2.8 GPU（`pong.md:361-422`；`pong-agxmx666.md:295-332`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | SM8475 A730、实际固件、SMMU、Turnip与22H374 Metal ABI。 | 同左 |
| Current limits | 未进行性能基准；尚未取得services82设备帧率或稳定性结果。 | 复杂壁纸和长时间稳定性没有新增结论。 |
| 实现落点（TOML paths） | `drivers/PongAdreno/**`、`drivers/PongMetal/**`、`patches/mesa/**`、`patches/metal2vulkan/**`、`scripts/*metal*`、`scripts/*adreno*`、`scripts/*turnip*` | — |

**Development findings — `pong.md`（原文）**

- services89桌面后出现BV opcode fault（0x2000/0x70970001）；services90按Nothing gen7与Linux a7xx补齐IB1LIST起止标记，保留fence、同步和故障BO所有权，编译通过，是否消除故障待确认。
- services81已有实际GPU scanout完成记录；一段日志为49帧/7873ms，驱动约55ms/帧。
- services82配套内核与Metal前端使用8项源映射/导入缓存和独立source_id，保留实际fence和DMA隔离；已编译。
- services86为scanout建立独立Vulkan上下文，缩小缓存维护范围，真实fence和错误保留策略不变。
- services86独立Vulkan device与Turnip全局dw连接冲突，导致backboardd空指针崩溃；services87撤销该路径，复用单一真实设备/独立queue。
- services113: actual compiled NativeAdrenoUserClient now allocates stable 128-entry chunks on demand; preserves BO/queue/fence ownership. Device refusal reason and original status retained. Wallpaper outcome pending.
- drivers/PongAdreno、drivers/PongMetal、drivers/AdrenoMetal 改为独立 submodule（pong-adreno、pong-metal、pong-adreno-metal）。

**Development findings — `pong-agxmx666.md`（原文）**

- 已有桌面硬件渲染记录，保留此前高RAM BO和copy分配修补。

**Evidence**

- `pong.md`：`services135-codecs-usb-global-metal.md`、`services133-parity-audio-usb.md`、`services128-speaker-identity-usb.md`、`services126-audio-package-latency.md`、`services125-wake-scanout-usb.md`、`services124-scanout-startup.md`、`services123-keyboard-gpu-memory.md`、`services116-runtime-adapters.md`、`services111-association-metal-route.md`、`services99-speaker-network-data.md`、`services98-first-frame-launch-policy.md`、`services97-native-endpoint-handoff.md`、`migration/format2/README.zh.md`、`services75-performance.md`、`services76-upstream-audit.md`、`services82-runtime-performance.md`、`services92-peripherals-latency.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

### 2.9 Network（`pong.md:423-483`；`pong-agxmx666.md:333-370`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | Pong PCIe0/QCA6490，82项PHY序列、GPIO80/94/95/96/204、RPMh。 | 同左 |
| Current limits | 扫描已确认；设置列表、关联与IP联网仍需新一轮实机结果。 | 本轮未启动；SMMU启用、QMI固件、扫描与联网仍未确认。 |
| 实现落点（TOML paths） | `drivers/PongWifi/**`、`configs/pong-wifi-sm8475.json`、`scripts/*wifi*`、`scripts/*ath11k*` | — |

**Development findings — `pong.md`（原文）**

- services89在物理电源采样中提前退出、未加载固件；services90在既有稳定期限内重试失败的完整SPMI样本，仍需真实物理供电就绪，继续使用Pong活动槽QCA6490固件，编译通过。
- services83完成真实station和13个热点扫描，未再见RDDM；services84修补19字节能力枚举、媒体列表和物理接口查询。
- services86实际扫描15个BSS，未见关联/DHCP成功；界面缺失主因为显示服务崩溃。
- services88根据22H374 IO80211原生用户客户端补齐selector0请求转交、selector1/7能力查询，移除自制设置页面和board私有控制API；扫描/连接复用真实station。
- services89修补新增原生请求15KiB OOL描述符在readBytes/writeBytes前未prepare的错误，输入输出配对prepare/complete；保留services88接口与运行时，启动恢复待实机确认。
- 用户确认services112 Wi-Fi连接正常，services113不改动QCA6490固件、关联路径或现有Data配置。
- drivers/PongWifi 改为 Chengdong-Yu/pong-wifi submodule。

**Development findings — `pong-agxmx666.md`（原文）**

- services72 PCIe link/BAR及128MiB散页DMA建表成功，停在SMMU context readback；services73按SM8475实现修正先TCR2/TCR后TTBR，编译通过。

**Evidence**

- `pong.md`：`services112-wifi-audio-phone-input.md`、`services111-association-metal-route.md`、`services108-native-audio-port-query.md`、`services107-interface-namer-handshake.md`、`services104-system-peripheral-order.md`、`services100-native-speaker.md`、`services99-speaker-network-data.md`、`services98-first-frame-launch-policy.md`、`services97-native-endpoint-handoff.md`、`services74-source-audit.md`、`services76-upstream-audit.md`、`services79-upstream-runtime-audit.md`、`services81-wifi-firmware.md`、`services82-runtime-performance.md`、`services83-official-peripherals.md`、`services84-peripheral-interfaces.md`、`services88-native-peripherals.md`、`services92-peripherals-latency.md`。
- `pong-agxmx666.md`：`services73-smmu-audio.md`。

### 2.10 Audio（`pong.md:484-556`；`pong-agxmx666.md:371-408`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | ADSP/GPR/APM、TFA9873双扬声器、MI2S LPAIF0 tertiary/SD0。 | 同左 |
| Current limits | 实体PCM播放尚未确认；不发布不存在的输入端口。 | 尚无StartIO、PCM完成或实际出声证据；不公开麦克风。 |
| 实现落点（TOML paths） | `drivers/PongPower/PongAudio*`、`drivers/PongPower/PongIOAudio2.h`、`drivers/PongPower/ShengAudioReach*`、`userland/PongAudioPlugIn.c`、`userland/audio-route.c`、`scripts/*audio*` | — |

**Development findings — `pong.md`（原文）**

- services83实体HAL已连接但未见StartIO；services84删除插件内非法重入客户端HAL的路由线程，补齐身份和class qualifier过滤。
- services86实体gain/mute变化通知HAL属性缓存，记录真实设备发现结果；尚无StartIO或出声确认。
- services88删除SpringBoard直改增益客户端，补齐标准HAL静音对象、OwnedObjects/ControlList与通知；现有UID匹配通用驱动，尚无StartIO或PCM出声证据。
- services113 preserves the repaired real HAL port selection; fixes the ADSP mapping failure that prevented physical output readiness. Audible PCM remains unconfirmed.
- drivers/PongPower 音频源改为 Chengdong-Yu/pong-power submodule。

**Development findings — `pong-agxmx666.md`（原文）**

- services72 APM、功放和现代HAL初始化成功；audiomxd因独立AirPlay路由RPC超时退出。services73在launchd前选择原生集成音频provider，运行时已编译。

**Evidence**

- `pong.md`：`services142-wake-usb-audio.md`、`services141-native-usb-pcm.md`、`services137-native-mux-speaker-sd1.md`、`services135-codecs-usb-global-metal.md`、`services134-speaker-usb-qup.md`、`services133-parity-audio-usb.md`、`services132-wake-usb-ownership.md`、`services131-usb-conflict-isolation.md`、`services130-root-smmu-order.md`、`services129-prm-usb-dma.md`、`services128-speaker-identity-usb.md`、`services127-native-audio-rootful.md`、`services126-audio-package-latency.md`、`services116-runtime-adapters.md`、`services112-wifi-audio-phone-input.md`、`services111-association-metal-route.md`、`services110-adsp-poster-textinput.md`、`services109-audio-plugin-keyboard.md`、`services107-interface-namer-handshake.md`、`services104-system-peripheral-order.md`、`services100-native-speaker.md`、`services99-speaker-network-data.md`、`services98-first-frame-launch-policy.md`、`services97-native-endpoint-handoff.md`、`services94-native-volume-wlan.md`、`services83-official-peripherals.md`、`services84-peripheral-interfaces.md`、`services88-native-peripherals.md`、`services74-source-audit.md`、`services79-upstream-runtime-audit.md`、`services82-runtime-performance.md`。
- `pong-agxmx666.md`：`services73-smmu-audio.md`。

### 2.11 Power（`pong.md:557-605`；`pong-agxmx666.md:409-446`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | SM8475 ADSP/RPMh、PMIC battery管理和Pong电源策略。 | 同左 |
| Current limits | 动态充电图标、充放电和插拔更新仍需设备观察。 | 系统挂起恢复尚未完成。 |
| 实现落点（TOML paths） | `drivers/PongPower/**`、`configs/pong-power-sm8475.json`、`userland/sleepserver/**` | — |

**Development findings — `pong.md`（原文）**

- services90对照Nothing qti_battery_charger修正0x04通知订阅为TYPE_NOTIFY，兼容精确匹配的订阅响应，继续向IOPMPowerSource发布真实状态；充电显示待实机确认。
- services84按Nothing协议使用USB_ADAP_TYPE=7识别源，并按最大电流/输入限值描述适配器；不改固件充电控制。
- services86同轮fresh快照、真实VBUS存在判断、两轮source确认和5秒刷新，充电控制仍归固件。
- services112 REC: ADSP stage9 failed at whole-carveout CPU mapping, leaving battery/audio unavailable. services113 loads bounded physical slices with original Pong PAS/MDT inputs; device result pending.
- drivers/PongPower 改为 Chengdong-Yu/pong-power submodule。

**Development findings — `pong-agxmx666.md`（原文）**

- DSP readiness和电池协议已有日志；控制器值保持Pong板级来源。

**Evidence**

- `pong.md`：`services127-native-audio-rootful.md`、`services110-adsp-poster-textinput.md`、`services107-interface-namer-handshake.md`、`services104-system-peripheral-order.md`、`services74-source-audit.md`、`services83-official-peripherals.md`、`services84-peripheral-interfaces.md`、`services92-peripherals-latency.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

### 2.12 Image assembly（`pong.md:606-644`；`pong-agxmx666.md:447-484`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | `scripts/package.sh --check` 走 deps/preflight/patches；CI 的 package job 跑 `scripts/package.sh --os … --skip-prelink`，再跑 `scripts/finalize-pong-adt.py`：用本地同一份 `make-pong-adt-ipados18.py` 与同一组参数（12 GiB DRAM、4 GiB 窗口、单 CPU）重写 payload 里的 ADT，并重打 boot.img 与 PONGFAT1 包装的 boot.img.pong。 | Darwin24/XNU11417与22H374原始组件，格式2硬件输入与固定ABI。 |
| Current limits | CI 尚未在 macOS runner 上运行；真机未刷入。prelink slide 尚未在本板表达，流水线用 --skip-prelink。devicetree.generate() 要求单段 /memory，自定义 DT 属性不透传。 | Apple镜像、固件和ABI二进制均需本机准备。 |
| 实现落点（TOML paths） | `scripts/package.sh`、`scripts/finalize-pong-adt.py`、`scripts/build-pong-hardware-dtb.py`、`scripts/install-unixnu-inputs.py`、`kits/PongPlatform24/**`、`os-profiles/**`、`board.toml`、`.github/workflows/package.yml`、`scripts/build-ipados18*`、`scripts/build-pong-profile-kernel.py`、`scripts/make-pong-adt-ipados18.py`、`scripts/build-xnu-ipados18.sh`、`patches/xnu-ipados18/**` | — |

**Development findings — `pong.md`（原文）**

- scripts/package.sh --check --no-deps 在 Linux 上通过：1 个补丁、pong_ipados18_defconfig、OS ipados-18.7.10-22H374。release 只跑 kernel/package/firmware/payload，不含 userdata；本板内核需要 MACHINE_CONFIGS=PONG，共享 kernel 步骤写死 BCM2837，因此由 kits/PongPlatform24 作为组件 recipe 编译；共享 kernel 步骤的 tree 已有真实 drivers/ 目录，设备 builder 另用一棵树并在编完后回填 mach.development.pong。bootimg 的 validate 只认 v0-v2 头，board 覆写 header_version = 0。本板固件只认 PONGFAT1 包装的 ramdisk，故规范产物 boot/boot.img 之外另出 boot.img.pong。userdata 不走 unixnu userdata：它写 SHNGROOT v2 且缺 Data 窗口，本板 RootLayout.h 只接受 v1 且强制 OS/SystemOS/Data 三窗口。
- package.yml 去掉未使用的 blacktop/tap/ipsw；porting-record.yml 改为 submodules: recursive，与 drivers/ submodule 拆分对齐。

**Development findings — `pong-agxmx666.md`（原文）**

- services73使用匹配22H374的IOStorage/IOGPU导入；内核43834376字节，启动镜像102514688字节，构建完成。

**Evidence**

- `pong.md`：`migration/format2/README.zh.md`。
- `pong-agxmx666.md`：`services73-smmu-audio.md`。

### 2.13 Diagnostics（`pong.md:645-709`；`pong-agxmx666.md:485-523`）

| 项 | `pong.md` | `pong-agxmx666.md` |
|---|---|---|
| status | `implemented` | `implemented` |
| Components | `PongPlatform24` | `PongPlatform24` |
| Procedure | 保留屏幕启动日志和ramoops，REC抓取完整console。 | 同左 |
| Current limits | 没有运行测试、性能基准、镜像哈希或镜像回读比较。 | 本轮未启动，SMMU、联网、PCM声音和按键动作仍需设备结果确认。 |
| 实现落点（TOML paths） | `migration/ipados18/**`、`scripts/pong_adt_contract.py`、`userland/settings_compat18.c`、`userland/init.c`、`porting.toml`、`.github/**` | — |

**Development findings — `pong.md`（原文）**

- 已读取services81 REC console及Data中的Sileo/音频诊断，按具体错误修补。
- services82保留内核启动日志，减少launchd额外活动日志，并限制没有实际蓝牙传输层的反复拉起。
- services86已提取REC console和对应IPS，区分显示主故障与后续进程退出；可选softwareupdated重复SIGSEGV已设置停用。
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。
- porting-record.yml 改为 submodules: recursive，与 drivers/ submodule 拆分对齐。

**Development findings — `pong-agxmx666.md`（原文）**

- services72的REC日志与audiomxd超时堆栈已分析，services73修补只构建、未启动。

**Evidence**

- `pong.md`：`.github/workflows/porting-record.yml`、`services142-wake-usb-audio.md`、`services141-native-usb-pcm.md`、`services140-native-lockdown-audio-volume.md`、`services139-usb-native-configuration.md`、`services137-native-mux-speaker-sd1.md`、`services135-codecs-usb-global-metal.md`、`services134-speaker-usb-qup.md`、`services133-parity-audio-usb.md`、`services132-wake-usb-ownership.md`、`services131-usb-conflict-isolation.md`、`services130-root-smmu-order.md`、`services129-prm-usb-dma.md`、`services116-runtime-adapters.md`、`services74-source-audit.md`、`services82-runtime-performance.md`、`services85-backlight-startup.md`、`services91-autocapture-wifi.md`、`services94-native-volume-wlan.md`、`services95-hid-driverkit-wait.md`。
- `pong-agxmx666.md`：`migration/format2/README.zh.md`。

## 3. GPU / Display / Network / Audio / Power 实现细节

> 这一节把页面 Procedure、Development findings 和页面 Evidence 指向的 service note 合并为可执行方案。数字均带来源；页面没有给出的标 `未核实`。

### 3.1 GPU（Adreno 730 / ABI1 / 22H374）

**组件名**

- `PongAdreno`（`Chengdong-Yu/pong-adreno`）：Adreno 730 的 GMU / CP / HFI / ZAP / SMMU / scanout，Cape GPUCC（`REPO:README.md:38`）。
- `PongMetal`（`pong-metal`）：22H374 的 A730 Metal 前端与 GOP 扫描输出（`REPO:README.md:39`）。
- `AdrenoMetal`（`pong-adreno-metal`）：Adreno Metal 前端，pin 上游 `c6d29ca`（`pong.md:69`、`REPO:README.md:36`）。
- `NativeAdrenoUserClient`：按需分配稳定 128-entry chunks，保持 BO/queue/fence 所有权（`pong.md:386`）。
- `NativeBridgeMetalFrontend.mm`、`NativeMetalObjects.rs`、`PrimeShaders.h`、`QueuePriority.h`、`SharedShaderCache.h`（`TOML` paths：`drivers/PongMetal/**`）。
- Turnip / Mesa 补丁：`patches/mesa/**`；Metal 转译层：`patches/metal2vulkan/**`。

**板级参数**

| 参数 | 值 | 来源 |
|---|---|---|
| SoC / GPU | SM8475 / Adreno 730（A730） | `pong.md:377` |
| Metal ABI | 22H374 ABI1；arm64；native 4 KiB | `pong.md:843`、`pong.md:889`；services135 |
| GPU 早期连续池 | 512 MiB，失败逐级缩小 | `services99-speaker-network-data.md:26` |
| 启动时 BO 池 | 128 MiB（`pong_gpu_scanout=1`） | `services124-scanout-startup.md:16` |
| 4 KiB 映射记录 | 131072 → 262144 项 | `services99-speaker-network-data.md:26` |
| 源映射/导入缓存 | 8 项源映射 + 独立 `source_id` | `pong.md:383` |
| IOSurface 导入缓存 | 最多 64 项 / 64 MiB / 1 秒 | `services123-keyboard-gpu-memory.md:13` |
| 扫描输出格式 | BGRA opaque；22H374 8-bit compositor | `pong.md:404`；services123 |
| 面板时序交叉值 | 1080×2412、stride 4320 | `pong.md:271` |
| 最高档请求 | 900 MHz + DDR level 11（GMU HFI 投票/ACK） | `services160-gpu-clock-priority-timeline.md:7` |
| 单 ring 准入 | 低/普通/高优先级分别 1/2/8 个在途任务 | `services160-gpu-clock-priority-timeline.md:10` |
| 优先级方法 | ABI1 method18；method17 为 128IB 批量提交 | `services160-gpu-clock-priority-timeline.md:8` |
| 8-bit compositor 选项 | UUID `FAF7D7EA-18F0-3C2D-816C-AC56D16C40A3`；force-FP16=121、EDR-mirror=146、display-headroom float=20 | `services123-keyboard-gpu-memory.md:16` |
| GPU client 隔离 | 10 个独立 GPU client scope | `pong.md:298`（services110 摘要） |

**初始化顺序（按页面 findings 与 evidence 回推）**

1. **早期平台启动**：`PongAdrenoPlatform` 初始化 GPUCC、实际 GPU 固件、CP/IRQ 与 GMU/HFI；先以 `pong_gpu_scanout=0` 启动，确认 CP/固件/IRQ 与 backboardd 的 Metal 设备创建成功，但不产生 swap（`services123-keyboard-gpu-memory.md:7`、`services124-scanout-startup.md:7`）。
2. **安全固件与 SMMU**：SMMU/GMU/CP 认证 fence 与 ZAP/PAS 必须真实通过后才发布 IOAcceleratorES；GPU PAS/ZAP 与 ADSP PAS 共用同一个 SCM 会话锁，整个中断恢复过程持锁（`services99-speaker-network-data.md:22`、`services124-scanout-startup.md:7`）。
3. **单一真实 Metal/Vulkan 设备**：复用 backboardd 已创建的真实 `MTLDevice`，为 scanout 建立独立 command queue。禁止新建第二个 Nmb/Vulkan device——Turnip 的 `tu_knl_darwin.cc` 使用进程全局 `dw` 连接，第二个 instance 的枚举会关闭第一个 device 的 BO/connection，导致 `tu_init_hw<A7XX> +180` 空地址写入和 backboardd 连续 SIGSEGV（`services87-display-recovery.md:7-15`）。
4. **打开 scanout**：改用 `pong_gpu_scanout=1`，保留 128 MiB BO 池；链路为 `backboardd -> 0x4148 独立用户连接 -> Pong framebuffer 物理描述符 -> offered source pages -> Metal blit -> 实际 command completion -> PongScanoutComplete`。尝试 GPU 帧后要再次检查 quarantine；未知 DMA 完成不能回退为并行 CPU 写（`services124-scanout-startup.md:16-18`）。
5. **帧导入与退休**：scanout 只保留有界的三组有效导入；真实 fence、源帧引用和失败映射保留；空闲/未提交副本做 user/kernel 成对退休；可选缓存淘汰在真实 surface 完成之后异步执行（`services132-wake-usb-ownership.md`、`services142-wake-usb-audio.md:5`）。
6. **Metal 前端与提交**：ABI1 method17/18、单 ring FIFO、真实 CP 时间戳（`CP_REG_TO_MEM` 64 槽、最多 8 个在途任务）、O3 frontend、按 CPU 读取 PAC 特性寄存器但不启用 arm64e（`services160-gpu-clock-priority-timeline.md:8-12`、`services167-frame-ownership-and-pac.md`）。

**可执行落地步骤**

1. 在 `configs/mondrian_defconfig` 保持 `CONFIG_XNU_PONG_ADRENO_PLATFORM=y`，构建并 `-force_load libPongAdrenoPlatform.a`；确保 `PongAdrenoScanout.cpp` 与 `0232` 诊断写入一起链接（本仓 `GPU-ENABLE-PLAN.md` 已给出 K60 的补丁 rebase 细节）。
2. 第一阶段只传 `pong_adreno_start=1`，收集 `PONG ADRENO:` 的 CP 成功日志。
3. 第二阶段加 `pong_gpu_scanout=1`，确认 `PONG SCANOUT: GPU frame completed` 和真实 fence 完成，再谈 `pong_metal=1`。
4. 不要一次打开 `pong_gpu_only=1`；它是“是否真的 GPU 上屏”的决定性单轮实验，不能与 ABI2 或 A740 特性混用。

**故障边界**

- BV opcode fault `0x2000/0x70970001`：按 Nothing gen7 与 Linux a7xx 补 IB1LIST start `0x00d` / end `0x00e`，保留 fence/同步/故障 BO 所有权（`services90-gpu-wlan-power-cpu.md:19-21`）。
- 第二 Vulkan device 是已知回归路径；不要以“独立上下文”为名重引入（`services87-display-recovery.md:8-15`）。
- A740 的两 ring 抢占、ABI2 地址空间切换、Darwin26 偏移不适用于 SM8475/22H374；不要伪造 GPU 核数或完成事件（`pong.md:865`、`pong.md:988`、`pong.md:1073`）。
- 22H374 仍是 arm64；PAC 只做 per-CPU 特性记录，不声称 arm64e 执行（`pong.md:1448-1450`）。

### 3.2 Display（NT37705 / DCS / 1080×2412）

**组件名**

- `PongPower/PongBacklight*`（`pong-power`）：NT37705 DCS 背光（`REPO:README.md:40`）。
- `configs/pong-display-sm8475.json`：面板与 DCS 参数（`CFG`）。
- 显示服务：backboardd / `CoreBrightness.CBDisplayContaineriOS` / SpringBoard / replicatord；`PongMetal` 的 scanout 前端（`pong.md:277`、`services85-backlight-startup.md:9-13`）。

**板级参数（`CFG:configs/pong-display-sm8475.json`）**

| 参数 | 值 |
|---|---|
| panel | `NT37705 Visionox AMOLED command mode` |
| 分辨率 | 1080 × 2412 |
| refresh_hz | `[120, 90, 60]` |
| brightness transport | DSI DCS，version 1 |
| controller | `0x0ae94000` |
| register_bytes / channel | 1024 / 0 |
| brightness range | minimum_nonzero 10，maximum 4095；`bl_inverted_dbv: true` |
| wire byte order | most significant first；Nothing MIPI helper low/high 配合 `bl-inverted-dbv` swap |
| write / read command | `0x51` / `0x52` |
| write / read mode | HS / LP with BTA |
| runtime_validated | false |

**初始化顺序（按 findings 与 service notes 回推）**

1. **背光服务发布**：`PongBacklight` 按真实 backboardd IPS 的 22H374 默认映射初始化 NT37705；面板真实回读 `level=32 max=4095` 后才发布背光服务（`services85-backlight-startup.md:9-15`）。
2. **CoreBrightness 适配窗口**：22H374 的 `CoreBrightness` 在缺少 Apple 面板校准时先调用 slider→logical 计算默认极值，再分配自己的默认曲线；换算函数检查空曲线后仍无条件读首项，导致 `_DisplaySliderToLogicalBrightnessInternal + 272` 零地址崩溃。适配器只在该初始化窗口使用运行时内置软件默认曲线插值，曲线存在后调用原函数（`services85-backlight-startup.md:25-34`）。
3. **DBV 写入/回读**：`0x51` 在 HS 写，`0x52` 在 LP with BTA 读；返回 `22 00 b4 21` 时有效载荷为高字节 `00`、低字节 `b4`，即 DBV 180。必须按 MSB-first 解码并限制到 DT 的 0–4095；旧小端把 `46080` 当有效值并永久停用服务是错误路径（`services88-native-peripherals.md:11`）。
4. **scanout 导入**：复用线性纹理、最多三帧导入、保留缓存维护与真实 fence；GPU 帧完成后才释放真实 surface；空闲可选导入有界保留，`kNoResource`/未提交失败仍按原路径清退（`pong.md:275-277`、`services142-wake-usb-audio.md:5`）。
5. **睡眠/唤醒**：显示在 `scanout kNoResource` 后停止更新时，先保留三组有效导入，不做 GPU 复位或撤销映射；真正未提交失败才清退；Metal 完成回调先释放 IOSurface 写者状态，再把可选缓存淘汰交给单后台任务（`services142-wake-usb-audio.md:5`）。

**可执行落地步骤**

1. 先用 `pong-display-sm8475.json` 对齐 1080×2412、stride 4320、refresh 模式与 DCS 命令集。
2. 在 `PongBacklight` 中实现 NT37705 `0x51/0x52` 的 HS/LP-BTA 读写，回读解析按 MSB-first；写入后必须真实回读并保留错误。
3. 显示服务启动前确认 GPU scanout 模块已初始化；scanout 只接受单层全屏、BGRA 4Bpp、planeCount=0、源/目标均为 (0,0,panelW,panelH) 的 swap。
4. 睡眠唤醒路径单独做：先测 `kNoResource` 停止点，再启用有界 idle 导入保留和真实 surface 完成释放。

**故障边界**

- `services86` 的独立 Vulkan 上下文导致 backboardd/replicatord 退出；`services87` 已撤销，显示路径必须复用单一真实 device（`pong.md:277`、`services87-display-recovery.md:7-15`）。
- 120 Hz 是显示模式/请求值，不是测得帧率；页面 Current limits 明确“120Hz为显示模式；新一轮实际帧率与滑块调光未确认”（`pong.md:287`）。
- 驱动耗时约 40–52 ms/帧（`pong.md:275`）；GPU 日志另一段为 49 帧 / 7873 ms、约 55 ms/帧（`pong.md:382`）。这是慢帧证据，不是性能目标。

### 3.3 Network（QCA6490 / PCIe0 / ath11k）

**组件名**

- `PongWifi`（`pong-wifi`）：QCA6490，PCIe0 + MHI + ath11k，SID `0x1c01`（`REPO:README.md:42`）。
- `configs/pong-wifi-sm8475.json`：板级 profile（`CFG`）。
- `PongWifiPlatform.cpp` / `PongWifiNet.cpp` / `ath11k/PongAth11k.c`（本仓 `WIFI-PORT-PLAN.md` 已逐文件列出；页面路径为 `drivers/PongWifi/**`）。
- IO80211 native user client、en0 station、InterfaceNamer、mobile Wi-Fi manager。

**板级参数（`CFG:configs/pong-wifi-sm8475.json`）**

| 参数 | 值 |
|---|---|
| PCI vendor / device | `0x17CB` / `0x1103`（QCA6490 / WCN6855 家族） |
| subsystem vendor / device | `0x17CB` / `0x0108` |
| revision | 1 |
| BAR0 | `0x60200000`，2 MiB |
| PCIe regions | PARF `0x1c00000/0x3000`、PHY `0x1c06000/0x2000`、DBI `0x60000000/0xf1d`、ELBI `0x60000f20/0xa8`、iATU `0x60001000/0x1000`、config `0x60100000/0x100000` |
| GPIO | WLAN_EN 80、BT_EN 81、SW_CTRL 82、XO_CLK 204、PERST 94、WAKE 96 |
| SID map | RID 0 → SID `0x1c00`，RID `0x100` → SID `0x1c01` |
| PHY 序列 | 82 项 `{offset,value,delay}`；状态寄存器 offset `0x214`、bit 6 |
| 固件槽位 | 活动槽 `modem_b/image/qca6490`（services81 实测） |
| QMI 标识 | chip `0x12`、board `0xff`、SoC `0x400c1211`；加载 `amss20.bin`、`bdwlang.elf`、`m3.bin`、`regdb.bin` |
| 通道数 | 102 个硬件 channel（services81/104） |
| DMA | 早期 128 MiB 散页；services103/104 为 64 MiB 固定页 / SID1c01 |
| 能力枚举 | 19 字节（services84）；IO80211 selector 0/1/7（services88） |

**初始化顺序（按 findings 与 service notes 回推）**

1. **电源与 SPMI**：RPMh/PMIC 上电；物理电源采样要求 enable、in-regulation、电压下限全部真实；在已有 100 ms 稳定期限内重读完整 SPMI 样本，单次 observer 失败不能直接退出，也不能把部分旧数据当完整样本（`services90-gpu-wlan-power-cpu.md:23-27`）。
2. **PCIe0 link / SMMU**：PARF/PHY 82 项序列 → PCIe link/BAR；SMMU context 若 readback 停滞，按 SM8475 修正“先 TCR2/TCR 后 TTBR”（`pong-agxmx666.md:353`、services73）；建立 SID `0x1c01` 的 native 4K 页表与 128 MiB（后改 64 MiB）DMA。
3. **固件加载**：从当前活动槽 `modem_b/image/qca6490` 只读提取固件；QMI 返回 chip/board/SoC 后按实际值选择 `amss20.bin`、`bdwlang.elf`、`m3.bin`、`regdb.bin`；MHI `SYS_ERROR/RDDM/FATAL_ERROR` 首次出现即标记失败并停止 WMI、屏蔽 MSI、拉低 PERST、保留 DMA（`services81-wifi-firmware.md:5-24`）。
4. **ath11k 注册**：mac80211 的 `registered` 回调只保存通知；MAC start/add_interface 移到 QMI bring-up 工作返回且 `ATH11K_FLAG_REGISTERED` 已置位之后；只有真实 station 建立后才发布网络接口（`services81-wifi-firmware.md:17-20`）。
5. **IO80211 用户客户端**：selector0 使用 `0x3c30` envelope（command、length、`0x3c00` payload、`0x28` request）；selector1 标示已实现 ioctl 通道；selector7 不宣告未实现快速路径；15 KiB OOL 描述符必须在 readBytes/writeBytes 前 prepare、完成后 complete（`services88-native-peripherals.md:12`、`pong.md:447`）。
6. **InterfaceNamer 与 en0**：InterfaceNamer 超时完成可解除 wifid manager 与 SpringBoard 阻塞；真实 device count 1、扫描 29 个 BSS 后出现首帧和持续 swap；用户确认 services108/services112 Wi-Fi 修复/连接正常（`pong.md:448`、services107/108/112）。

**可执行落地步骤**

1. 先用 `pong-wifi-sm8475.json` 对 K60 live FDT 逐项比对（本仓 `WIFI-PORT-PLAN.md` 已确认 K60 与 Pong 的 PCIe0 六个窗口、GPIO 80/81/82/94/95/96/204、82 项 PHY 序列表基本一致；需改 K60 的时钟表索引、PMIC 轨身份、`use-nv-mac`、固件路径与子设备 ID）。
2. 先只做 PCIe + SMMU + BAR + MSI 的枚举日志，确认 `0x17cb:0x1103` 出现。
3. 再做 QMI 固件加载与 `ATH11K_FLAG_REGISTERED`，最后才开 IO80211 user client 和 InterfaceNamer。
4. 任何 MHI/RDDM 错误都停在保留 DMA 的状态，不要用重试掩盖固件失败。

**故障边界**

- `ath11k split-BSS callback` 为空会导致 panic；必须接真实 BSS adapters，不能用空回调（`pong.md:297`、services112）。
- mobile HAL 默认 setter 会被拒绝；不要伪造默认端口或设备状态（`pong.md:297`）。
- 15 KiB OOL 描述符的 prepare/complete 必须成对；否则 `readBytes/writeBytes` 前的未 prepare 错误会复发（`pong.md:447`）。

### 3.4 Audio（ADSP / AudioReach / TFA9873）

**组件名**

- `PongPower/PongAudio*`、`PongIOAudio2.h`、`ShengAudioReach*`（`pong-power`）：ADSP PAS1、TFA9873 双功放、WCD938x、NT37705 DCS 背光、电池（`REPO:README.md:40`）。
- `userland/PongAudioPlugIn.c`、`userland/audio-route.c`：AudioServerPlugIn / VirtualAudio 路由。
- ADSP / GPR / APM / AudioReach；`AudioConverterService` / `IOAudio2`；CoreAudio `AMCP::IOAudio2`。

**板级参数（`CFG:configs/pong-power-sm8475.json`）**

| 参数 | 值 |
|---|---|
| ADSP PAS | `pas_id = 1`；`firmware_path = /pong/firmware/adsp.mbn` |
| ADSP memory | base `2238709760`（0x85700000），40 MiB；SMEM base `2156920832`，2 MiB |
| ADSP IPC | `mutex = 32780288`；`ipcc_base = 248610816`；`ipcc_irq = 261`；`remote_pid = 2`；SMP2P in/out `443/429`；GLINK items `[478,479,480]` |
| codec / amps | WCD938x；2 × `tfa,tfa98xx`，I2C controller `11091968`、address `52/53`；`amplifier_model = TFA9873` |
| amp reset | GPIO `[1,89]`，active high，assert 10 ms / release 10 ms |
| App SMMU SID | `0x1801` |
| PCM route | `MI2S-LPAIF-RX-TERTIARY`，48 kHz、2 ch、32 bit；pins `[121,122,123,124]`；`lpaif_type = 0`；`interface_index = 2`；`sd_line_index = 2` |
| PCM 数据线 | `rx-lines = 0x2`（SD1 playback），`tx-lines = 0x1`（SD0 feedback）；AudioReach `I2S_SD1 = 2`（`services137-native-mux-speaker-sd1.md:17-29`） |
| PRM clock | id `0x104`，3.072 MHz（48 kHz × 2 ch × 32 bit） |
| DMA | `pong-audio-dma` 独占 64 KiB；8 个 period buffer，每个 3840 bytes |
| TFA B0 | 32-bit stereo：`TDMNBCK=2`、slot length 31、sample size 31；左右功放取 slot0/slot1（`services144-data128-components-audio.md:21`） |
| 音量/增益 | native 0..16 线性幅度 + 16 段真实 dB；media `0.6473`、ringer `0.2974`；physical control `1`、mute `0`；ringer `0.6763`；S16→Q31；volume4/gain1039/mute0 时 peak 66496（services141/142/145） |

**初始化顺序（按 findings 与 service notes 回推）**

1. **ADSP 固件**：PAS1 按原始 Pong PAS/MDT 输入加载，使用有界物理切片而不是整段 carveout；stage 9/10 → 11/12/13，GPR channel up，APM ready（`services99-speaker-network-data.md:22`、`services104-system-peripheral-order.md:5-13`、`pong.md:580`）。
2. **AudioReach 图**：在 prepare 前恢复 endpoint / converter / shmem media；通过真实 VAD 查询 `prts` 端口、`rtcf` 32 字节请求选择可用 `ptbo` 输出端口、`vcsp` 读取音量能力；不再反复设置默认设备号（`services99-speaker-network-data.md:20`、`services163-audio-prepare-command-stages.md`）。
3. **MI2S / PRM / TFA**：PRM `0x104` 输出 3.072 MHz；tertiary MI2S 用 SD1 播放、SD0 反馈；配置 TFA9873 `KEY2` volatile、`TDMSPKE`、`TDMNBCK=2`、slot 31、sample 31；左右功放分别取 slot0/slot1（`services137-native-mux-speaker-sd1.md:17-29`、`services144-data128-components-audio.md:21`）。
4. **IOAudio2 启动**：`AudioConverterService`/`IOAudio2` 启动；S16 环显式转物理 Q31；读取提交样本范围（状态页 +0x20 是独占结束样本位置，不是 host 时间）；等待真实 DSP `WRITE_DONE` 和功放状态（`services128-speaker-identity-usb.md:12`、`services141-native-usb-pcm.md`）。
5. **音量与短音**：native 0..16 线性振幅 + 16 段 dB 元数据；短音停止先停新提交，最多 100 ms 处理 `WRITE_DONE`，再保留最多 80 ms 物理队列尾部（`services144-data128-components-audio.md:23`）；`lock-sound-admission164` 进一步做 StartIO/StopIO 串行与 400 ms drain。
6. **唤醒恢复**：`audio-wake-active-acquire162` 在 running engine 上恢复 retained/new HAL 客户端输出流；先以 live source clock 关功放，再关 APM/MI2S；启动时恢复 volatile TDM route；`audio-prepare-command-stages163` 做 5 s 静音 DMA warm hold。

**可执行落地步骤**

1. 先移植 ADSP PAS1 + GPR/APM（`PongAudio.cpp`/`ShengAudioReach` 结构），用真实 `adsp.mbn` 和 64 KiB DMA lease 验证 stage 11/12/13。
2. 按 `pong-power-sm8475.json` 的 PCM route 建 MI2S：48 kHz stereo S32_LE、interface_index 2、SD1 playback、PRM 0x104 3.072 MHz。
3. 配 TFA9873：I2C 0x34/0x35，reset GPIO 1/89，`TDMNBCK=2`、slot 31、sample 31，左右 slot0/1；保留原厂 CNT/MTP/保护。
4. 最后接 AudioServerPlugIn、native 0..16 音量、`IOAudio2` 启停和短音 admission；用真实非零 PCM + `WRITE_DONE` + 功放状态三层证据验收，不以编译或非零 PCM 代替出声。

**故障边界**

- ADSP stage9 whole-carveout CPU mapping 失败会让电池/音频同时不可用；必须改为有界物理切片并保留原始 PAS/MDT 输入（`pong.md:580`）。
- `audiomxd` 会因独立 AirPlay 路由 RPC 超时退出；`services73` 在 launchd 前选择原生集成音频 provider（`pong-agxmx666.md:391`）。
- `audiomxd` 在只读 native status +0x18 上会 SIGBUS；services127 改为共享 RW status（`pong.md:536`）。
- TFA status11 在 PCM 后仍为 `8040`，说明功放模拟通路未开；`services134` 加 `KEY2` volatile 配置和真实 amp 状态检查（`pong.md:528`）。
- 用户只确认“较小的锁屏音效”；媒体与其他声音未恢复，熄屏/解锁静音仍未解决（`services144-data128-components-audio.md:29-31`）。

### 3.5 Power（ADSP / RPMh / PMIC battery）

**组件名**

- `PongPower`（`pong-power`）：ADSP PAS1、TFA9873 双功放、WCD938x、NT37705 DCS 背光、电池（`REPO:README.md:40`）。
- `QcomRpmh` / `PongPlatformResources`：RPMh 轨与 APSS active TCS4（`CFG:configs/pong-power-sm8475.json:113-131`；本仓 `WIFI-PORT-PLAN.md` 提到 K60 树缺少这两个文件）。
- PMIC `PMIC_RTR_ADSP_APPS` 通道、`qti_battery_charger`、`IOPMPowerSource`、PowerUI / sleepserver。

**板级参数（`CFG:configs/pong-power-sm8475.json`）**

| 参数 | 值 |
|---|---|
| battery owner / channel | `32778` / `PMIC_RTR_ADSP_APPS` |
| battery property IDs | status 0、present 2、capacity 4、voltage_uv 7、current_ua 9、temperature_decic 12、counter_uah 14、cycles 15、full_design_uah 16、full_uah 17、time_to_full_s 19、time_to_empty_s 20 |
| charger writes | `false`（充电控制归固件） |
| power TCS | active TCS 4；GPU TCS 3；`PongPlatformResources / APSS active TCS4` 串行化 |
| CPU caps | `[1804800, 2496000, 2995200]` kHz；`pong_cpu_policy` 默认 `fixed-highest-non-boost` |
| GPU policy | `pong_gpu_pwrlevel` 默认 DT level 0；requested 900 MHz / DDR 11；`frequency_runtime_qualified=false` |
| suspend/resume | `suspend_resume_implemented = false` |

**初始化顺序（按 findings 与 service notes 回推）**

1. **RPMh / PMIC**：PongPower 初始化 RPMh 轨和 PMIC；ADSP PAS1 stage 9→13、APM ready 后电池协议才有真实数据（`services104-system-peripheral-order.md:5-13`）。
2. **充电通知**：对照 Nothing `qti_battery_charger.c`，0x04 通知订阅用 `TYPE_NOTIFY`（属性请求仍 `TYPE_REQUEST`）；精确匹配订阅响应后，由真实通知/周期读取刷新 `IOPMPowerSource`（`services90-gpu-wlan-power-cpu.md:25-27`）。
3. **USB 适配器**：按 Nothing 协议 `USB_ADAP_TYPE=7` 识别源，按最大电流/输入限值描述适配器；不修改固件充电控制（`pong.md:578`）。
4. **充电状态机**：同轮 fresh 快照 → 真实 VBUS 存在判断 → 两轮 source 确认 → 5 秒刷新；充电控制仍在固件（`pong.md:579`）。
5. **电池页**：PowerUIAgent 对外部电源的同步 CoreDuet 查询可阻塞电池页；改为从真实 `IOPMPowerSource` 的 `ExternalConnected` 读取，不存在有效属性时保留原实现（`services104-system-peripheral-order.md:23-25`）。

**可执行落地步骤**

1. 先接 `QcomRpmh`/`PongPlatformResources`，完成 APSS active TCS4 与 PMIC 轨初始化；K60 的 PMIC 物理身份要按 K60 FDT 替换，不能照抄 Pong 的 PMIC 型号。
2. 实现 ADSP PAS1 有界切片加载，确认 stage 11/12/13 与 APM ready。
3. 订阅 0x04 `TYPE_NOTIFY`，向 `IOPMPowerSource` 发布真实 battery status/capacity/voltage/current/temperature。
4. 接 `USB_ADAP_TYPE=7`、fresh VBUS、两轮确认、5 秒刷新；充电图标与插拔更新最后验收。

**故障边界**

- ADSP stage9 整段 carveout 映射失败会让电池/音频都不可用；不要以“重新上电”掩盖，按 bounded physical slices 修（`pong.md:580`、services113）。
- 未发布电源不能当作 0%；services103 重新发布真实 100% / 4428 mV（`services104-system-peripheral-order.md:7-8`）。
- 动态充电图标、充放电和插拔更新仍待设备观察（`pong.md:589`）；系统挂起恢复在 agx 页明确“尚未完成”（`pong-agxmx666.md:437`）。

### 3.6 跨域初始化依赖（页面证据合并）

按页面 findings 的依赖关系，可执行顺序为：

1. **Firmware/UEFI**（DarwinBoot24、PSCI）→ **CPU**（GICv3、19.2 MHz timer、8 核）→ **Memory/SMMU**（12 GiB 不连续 DRAM、4 KiB 页表）。
2. **Storage**（NativeUfs、SID 0xe0、OS/SystemOS/Data 三窗口）→ 根卷 `EmbeddedDeviceTypeRoot` 发布（services85）。
3. **Power**（RPMh/PMIC、ADSP PAS1 stage 9→13、电池协议）→ **Display**（NT37705 背光、CoreBrightness 默认曲线）。
4. **GPU**（GPUCC/CP/GMU/ZAP/SMMU → Metal device → scanout）→ **Display** 的 GPU scanout 帧路径。
5. **Network**（PCIe0/QCA6490 → ath11k → en0/IO80211 → InterfaceNamer）与 **Audio**（ADSP → AudioReach → MI2S/TFA → IOAudio2）可在 GPU/显示之后并行推进；两者都依赖 Power 的 RPMh/ADSP。
6. **Packaging/Diagnostics** 是贯穿全过程的产物与取证层：每次只装差量 OS band，保留 Data/SystemOS，REC console + ramoops + reset commit 标记作为验收证据。

## 4. Evidence 的 commit / 脚本 / 仓库

### 4.1 页面钉住的 commit

| 页面 | 仓库 | commit | 说明 |
|---|---|---|---|
| `pong.md` | `Chengdong-Yu/UniXNU-pong` | `e0ee6df109b4b5dc706cac660d4f8210dc911dac` | `porting.toml` source record；本页所有 186 条 Evidence 均指向该 commit |
| `pong-agxmx666.md` | `AGXMX666/UniXNU-pong` | `ffdad781cb16b42a1fb5c984f77998253b821d8c` | 早期 services72-73 快照 |

### 4.2 页面提到的 core / upstream commit

| commit | 含义 / 出现位置 |
|---|---|
| `066c8d8` → `f0721e9` | UniXNU core fast-forward；upstream delta 仅设备记录（services129，`pong.md:87`） |
| `40d21cc` | UniXNU 同步点；构建记录保存真实上游 HEAD（services76，`pong.md:89`） |
| `c6d29ca` | AdrenoMetal 上游 pin（`pong.md:69`） |
| `6790e7c` | core 版本（main-gpu-metal-ringer149，`pong.md:843`） |
| `a0f0287` | AdrenoMetal 版本（services149） |
| `a9a2cbb` / `36c4e44` | Adreno740 main / Qualcomm KGSL ring allocation（`pong.md:885`；`TOML` inputs） |
| `28b3028` | Sheng 版本（upstream-metal-keyboard152） |
| `831a9dc` | AdrenoMetal 版本（services152） |
| `135b0da` | core 版本，包含 latest main `04573c5`（frame-ownership-pac167 / services166） |
| `d6bd3dd` | upstream `fix/gpu-scheduling-and-metal` 完整 core merge（scheduling-metal-audio-clock165） |
| `88604d0` / `278333f` | BGRA opaque GPU scanout 适配来源（services133） |
| `aaa2d739` | remote main packaging / AppCryptex 变更（cumulative-runtime-pr167） |

### 4.3 12 个 `Chengdong-Yu/pong-*` 子模块（`e0ee6df` 本地记录）

| 路径 | 仓库 | 记录的 submodule commit |
|---|---|---|
| `drivers/ArmCpu` | `pong-arm-cpu` | `ac65513a780255a8b6771ae280068ef9586497d7` |
| `drivers/ArmDTPlatform` | `pong-arm-dt-platform` | `09ecfcf62ea109c036500d8a1dbf88ef234831b8` |
| `drivers/AdrenoMetal` | `pong-adreno-metal` | `418c550887db141455270c151628d657dd545a7f` |
| `drivers/NativeRamBlock` | `pong-ram-block` | `eebcdb67e990a262293463e4e73e83859a39a9b4` |
| `drivers/DarwinBoot24` | `pong-darwin-boot24` | `86d300d3b21489b473973199b5b4ff3e77acfb2a` |
| `drivers/NativeUfs` | `pong-ufs` | `3c7e354504c241888316ab626a064bca011e4d38` |
| `drivers/PongAdreno` | `pong-adreno` | `3e8ffa2424e7915a1cc35da14b043057a87707e7` |
| `drivers/PongBootCapture` | `pong-boot-capture` | `af2c5ca0653f0ce9b44ee7f8ac0895cb2cde7ef8` |
| `drivers/PongMetal` | `pong-metal` | `ccdbc294a9fa95b341fa6f926870ca07ddc663a4` |
| `drivers/PongPower` | `pong-power` | `c37179ed12ba7f981b2b088aea482b969085eb84` |
| `drivers/PongUsb` | `pong-usb` | `6070a991b58f03f7062f6c9757343ffaceb1f631` |
| `drivers/PongWifi` | `pong-wifi` | `d2e33ca6e0f6a3b3e7881a45ab36c6920e7afb07` |

`pong.md:69` 另记 `AdrenoMetal 仍 pin 上游 c6d29ca`，指该 submodule 内部对上游 AdrenoMetal 的 pin，不是上表的 submodule commit。

### 4.4 页面点名的脚本、配置与产物

| 路径 | 作用 |
|---|---|
| `scripts/package.sh` | `--check` 走 deps/preflight/patches；`--os … --skip-prelink` 为 CI package job 主入口 |
| `scripts/finalize-pong-adt.py` | 用 `make-pong-adt-ipados18.py` 同参数重写 ADT；重打 `boot.img` 与 `boot.img.pong` |
| `scripts/make-pong-adt-ipados18.py` | 生成 ADT：12 GiB DRAM、4 GiB 窗口、单 CPU |
| `scripts/build-pong-hardware-dtb.py`、`scripts/install-unixnu-inputs.py` | 板级 DTB 与输入安装 |
| `scripts/build-xnu-ipados18.sh`、`scripts/build-ipados18*` | 内核/运行时构建 |
| `kits/PongPlatform24/**` | 组件 recipe；`MACHINE_CONFIGS=PONG` |
| `os-profiles/ipados-18.7.10-22H374` | OS profile |
| `configs/pong_ipados18_defconfig`、`configs/pong_ipados18_ci_defconfig` | 内核配置 / CI 配置 |
| `.github/workflows/package.yml` | macOS runner 的 package / payload job（页面称尚未跑） |
| `.github/workflows/porting-record.yml` | 改为 `submodules: recursive`，让 porting record 看到 drivers 树 |
| `configs/pong-display-sm8475.json`、`pong-memory-sm8475.json`、`pong-power-sm8475.json`、`pong-usb-sm8475.json`、`pong-wifi-sm8475.json` | 板级 profile（display/power/memory/wifi 已在本文件引用） |

### 4.5 `pong.md` 全部 74 个去重 Evidence 路径

```text
# 根 / 元数据（7）
README.md
porting.toml
.gitmodules
.github/workflows/porting-record.yml
migration/format2/README.zh.md
migration/ipados18/runtime-fixes-and-build-overlay.md
migration/ipados18/sileo.md

# services（67）
migration/ipados18/services73-smmu-audio.md
migration/ipados18/services74-source-audit.md
migration/ipados18/services75-performance.md
migration/ipados18/services76-upstream-audit.md
migration/ipados18/services79-upstream-runtime-audit.md
migration/ipados18/services81-wifi-firmware.md
migration/ipados18/services82-runtime-performance.md
migration/ipados18/services83-official-peripherals.md
migration/ipados18/services84-peripheral-interfaces.md
migration/ipados18/services85-backlight-startup.md
migration/ipados18/services87-display-recovery.md
migration/ipados18/services88-native-peripherals.md
migration/ipados18/services90-gpu-wlan-power-cpu.md
migration/ipados18/services91-autocapture-wifi.md
migration/ipados18/services92-peripherals-latency.md
migration/ipados18/services94-native-volume-wlan.md
migration/ipados18/services95-hid-driverkit-wait.md
migration/ipados18/services97-native-endpoint-handoff.md
migration/ipados18/services98-first-frame-launch-policy.md
migration/ipados18/services99-speaker-network-data.md
migration/ipados18/services100-native-speaker.md
migration/ipados18/services104-system-peripheral-order.md
migration/ipados18/services107-interface-namer-handshake.md
migration/ipados18/services108-native-audio-port-query.md
migration/ipados18/services109-audio-plugin-keyboard.md
migration/ipados18/services110-adsp-poster-textinput.md
migration/ipados18/services111-association-metal-route.md
migration/ipados18/services112-wifi-audio-phone-input.md
migration/ipados18/services116-runtime-adapters.md
migration/ipados18/services123-keyboard-gpu-memory.md
migration/ipados18/services124-scanout-startup.md
migration/ipados18/services125-wake-scanout-usb.md
migration/ipados18/services126-audio-package-latency.md
migration/ipados18/services127-native-audio-rootful.md
migration/ipados18/services128-speaker-identity-usb.md
migration/ipados18/services129-prm-usb-dma.md
migration/ipados18/services130-root-smmu-order.md
migration/ipados18/services131-usb-conflict-isolation.md
migration/ipados18/services132-wake-usb-ownership.md
migration/ipados18/services133-parity-audio-usb.md
migration/ipados18/services134-speaker-usb-qup.md
migration/ipados18/services135-codecs-usb-global-metal.md
migration/ipados18/services136-usb-mux-manual-reset-audio.md
migration/ipados18/services137-native-mux-speaker-sd1.md
migration/ipados18/services139-usb-native-configuration.md
migration/ipados18/services140-native-lockdown-audio-volume.md
migration/ipados18/services141-native-usb-pcm.md
migration/ipados18/services142-wake-usb-audio.md
migration/ipados18/services143-mobilegestalt-device-information.md
migration/ipados18/services144-data128-components-audio.md
migration/ipados18/services145-native-category-volume.md
migration/ipados18/services146-volume-ringtones-incremental.md
migration/ipados18/services147-ringtone-wake.md
migration/ipados18/services149-ringer-main-gpu.md
migration/ipados18/services150-adreno-freeze-ringer.md
migration/ipados18/services151-ringtone-control-center.md
migration/ipados18/services152-upstream-metal-keyboard.md
migration/ipados18/services153-gpu-guide-memory-bgra.md
migration/ipados18/services155-gpu-hot-path-and-priming.md
migration/ipados18/services156-metal-entrypoints-and-ui-stalls.md
migration/ipados18/services160-gpu-clock-priority-timeline.md
migration/ipados18/services162-sleep-audio-active-acquire.md
migration/ipados18/services163-audio-prepare-command-stages.md
migration/ipados18/services164-lock-sound-admission.md
migration/ipados18/services165-scheduling-metal-audio-clock.md
migration/ipados18/services166-submit-retirement-publication.md
migration/ipados18/services167-frame-ownership-and-pac.md
```

### 4.6 `pong-agxmx666.md` 的全部 Evidence 路径

```text
migration/format2/README.zh.md
migration/ipados18/services73-smmu-audio.md
porting.toml
```

## 5. 作者页完整度与直接借鉴结论

### 5.1 完整度排名

| 排名 | 页面 | 度量 | 内容覆盖 | 结论 |
|---|---|---|---|---|
| 1 | `pong.md`（Chengdong-Yu） | 1567 行 / 32 区域 / 186 条 Evidence / 74 去重路径 / services73-167 | 13 核心域 + 19 追加域；GPU、Display、Network、Audio、Power 均有从早期 bring-up 到 services167 的递进证据 | **最完整，主参考页** |
| 2 | `pong-agxmx666.md`（AGXMX666） | 523 行 / 13 区域 / 14 条 Evidence / 3 去重路径 / services72-73 | 仅早期格式2/内核/启动镜像与 services73 的 SMMU 顺序修补 | 可作最小基线，不能作为外设实现参考 |
| 3 | `pong-hxzbaka.md` | 1 行 | 只有仓库链接（Format 1） | 无文档可读 |
| 4 | `pong-y3d4.md` | 1 行 | 只有仓库链接（Format 1） | 无文档可读 |
| — | `pong-kmu1757.md` | 7 行 | Galaxy Tab S7+/S20+ SM8250；`Record pending` + `device.soc must match board.toml` | 不是 pong 页，忽略 |

### 5.2 为什么 `pong.md` 可直接借鉴

- 同 SoC：`SM8475`、Adreno 730、QCA6490、UFS、TFA9873/NT37705 均为 Pong 实测板级值；`pong.md` 的 Procedure 与 TOML paths 直接给出每个域的源码落点。
- 有完整演进链：从 `services73`（并引用 `services72` 的设备状态）的格式2/内核基线，到 `services124/125` 的 GPU scanout，`services81/104/107/108/112` 的 QCA6490，`services85/88` 的 NT37705 背光，`services128/137/141/144` 的 TFA9873，`services90/104` 的电池，全部有设备日志摘要或下一步。
- 有负面边界：明确记录第二 Vulkan device 崩溃、DBV 小端误读、ADSP stage9 carveout 失败、TFA status 8040、MHI RDDM 等真实故障，避免重复踩坑。
- 有构建/打包细节：`package.sh`、`finalize-pong-adt.py`、`PONGFAT1`、`SHNGROOT v1` 三窗口等，可直接对照 mondrian 的 `package.yml` 与 `RootLayout.h`。

### 5.3 对 mondrian 的分域借用表

| 域 | 可直接借用 | 必须替换/重验 |
|---|---|---|
| GPU | `PongAdreno` 的 GMU/CP/HFI/ZAP/SMMU/scanout 拆分；ABI1 单 ring、64 槽 CP 时间戳、BGRA opaque、真实 fence/退休模型 | 22H374 Metal ABI 与 Turnip/translator 版本；A740 特性不得开；K60 的 GPUCC/DT 电压档要按 K60 FDT |
| Display | NT37705 DCS 的 `0x51/0x52` 命令、MSB-first DBV、三帧导入、CoreBrightness 默认曲线适配方法 | 1080×2412/stride4320 是 Pong 面板；K60 面板参数必须另取；120 Hz 不是实测帧率 |
| Network | QCA6490 PCIe0 六个窗口、82 项 PHY 序列、GPIO 80/81/82/94/95/96/204、SID `0x1c01`、ath11k/QMI/RDDM 处理 | K60 时钟表索引、PMIC 物理轨、`use-nv-mac`、固件路径、子设备 ID；本仓 `WIFI-PORT-PLAN.md` 已给差异表 |
| Audio | ADSP PAS1/GPR/APM、AudioReach endpoint/converter/shmem、MI2S tertiary/SD1、PRM `0x104` 3.072 MHz、IOAudio2 启停与短音 admission | Pong 的 TFA9873 双功放；K60 是 AW882xx（见本仓 `BT-AUDIO-PORT-PLAN.md`）；PCM 数据线/时钟按 K60 codec 重排 |
| Power | PongPower 的 RPMh/PMIC battery、0x04 `TYPE_NOTIFY`、USB_ADAP_TYPE=7、VBUS 两轮确认、5 秒刷新 | K60 的 PMIC 型号/轨/电池属性；Pong 的 `charger_writes=false` 策略可保留；suspend/resume 未实现，不能声称完成 |

### 5.4 页面与源记录的差异（精读发现）

- `pong.md` 有 32 个 `##` 区域；`porting.toml` 有 32 个 `[[area]]` 加 1 个 `[[areas]]`（`safari-metal-residency159`，status 亦为 `implemented`）。该 `[[areas]]` 拼写错误使 `safari-metal-residency159` 没有被生成到设备页，页面缺这一节。
- `pong.md` 的 Audio Procedure 写“MI2S LPAIF0 tertiary/SD0”，但同一页 Evidence 的 `services137` 明确纠正为：`rx-lines = <2>`（SD1 playback）、`tx-lines = <1>`（SD0 feedback）、AudioReach `I2S_SD1 = 2`。以 services137 为准。
- `pong.md` 的 Configuration 说“12 个板级驱动”，`porting.toml` 的 `.gitmodules` 与本地 `git submodule status` 也是 12 个；但 `PongBootCapture` 与 `NativeRamBlock` 未在核心 13 域的 Procedure 中单独出现，属于支撑驱动。

### 5.5 `pong.md` 19 个追加区域的 Development findings（原文）

以下区域均 `status = implemented`；原文按 `pong.md` 顺序摘录，供 GPU/音频深挖时检索。

**mobilegestalt-device-information（`pong.md:710-750`）**

- services142 Finder recognition and native pairing/session succeeded. Old disk_usage contained negative free capacity and wrapped Data capacity.

**native-category-volume（`pong.md:752-792`）**

- Native selector2 scalar order matches driver. The actual endpoint is not muted but runs at1/16 gain.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**native-ringtone-display-wake（`pong.md:794-833`）**

- Ringer native volume0.6763 is nonzero; missing sound not resolved by another global gain boost. Existing78 ringtone resources retained.
- CPU scanout copied source alpha while GPU supplied opaque alpha; idle optional import retention and start/stop Busy window corrected.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**main-gpu-metal-ringer149（`pong.md:835-873`）**

- 148 default ringtone file resolves; objc_direct short setter/getter prevented native ringer adaptation.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**adreno-ringer-freeze150（`pong.md:875-914`）**

- Matching kernel, UI, init, independent codec and Metal bridge compiled; deployment in progress.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**control-center-native-ringtone151（`pong.md:916-955`）**

- 78 native M4R ringtone tracks transcoded to ALAC; UI telemetry adaptation, Metal plugin and matching bounded-memory Rust bridge compiled. Device deployment pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**upstream-metal-keyboard152（`pong.md:957-996`）**

- Darwin24 kernel, boot, Turnip, Metal frontend/plugin, UI and init compiled; boot command967bytes. No tests, benchmarks or image verification. Device outcome pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**gpu-guide-memory-bgra153（`pong.md:998-1039`）**

- Matching Darwin24 kernel, Turnip GMEM paths and153 Metal frontend/plugin compiled; native4K signatures; boot command965bytes. No tests, benchmarks or image verification.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**gpu-real-execution-hotpath155（`pong.md:1041-1081`）**

- 155 actual GPU scanout and827/827 completions; no CP fault in captured boot. User still reports slow UI; not a performance success claim.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**metal-interface-ui-stalls156（`pong.md:1083-1124`）**

- Optimized Rust/front-end/plugin built; only624MiB changed OS bands installed. Fastboot Sending2.328s/Booting10.175s OKAY; device observation pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**gpu-priority-timing160（`pong.md:1126-1169`）**

- Darwin24 kernel, Metal frontend and Turnip linked;80MiB changed OS bands installed; temporary Fastboot boot succeeded. Device timing pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**audio-wake-active-acquire162（`pong.md:1171-1216`）**

- Substantive HAL stream-resume, TFA clock/stop order and real-completion ownership changes; device result pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**audio-prepare-command-stages163（`pong.md:1218-1265`）**

- Matched kernel/Rust/ObjC compiled;56MiB OS changed bands installed; Fastboot Sending2.331s/Booting10.174s OKAY; native USB auto-configured. Audible wake recovery still requires device observation.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**lock-sound-admission164（`pong.md:1267-1312`）**

- Darwin24 kernel and matched Turnip compiled;48MiB OS changed bands installed; Fastboot Sending2.332s/Booting10.177s OKAY. Native audio client/tail and GPU stage capture pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**scheduling-metal-audio-clock165（`pong.md:1314-1361`）**

- Darwin24/Rust/Metal/Turnip/codec builds complete;96MiB changed-band installation; Fastboot Sending2.333s/Booting10.172s OKAY; actual device results pending.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**submit-retirement-publication166（`pong.md:1363-1407`）**

- Final166 rebuilt matchedDarwin24/Rust/Metal/Turnip after latest135b0da merge;112MiB changedOS bands installed; actual9216submits without capturedCP/SMMU fault; frame traces reveal CPU handoff overhead.

**frame-ownership-pac167（`pong.md:1409-1462`）**

- Darwin24 kernel,Turnip,O3 Metal frontend and matched plugin compiled;96MiB changed OS bands installed.
- Real scanout; no captured CP/SMMU error through5120submits.30216ranges became1793requests/473105us; typical handoff0.3-0.4ms, poster41-267ms backlog remains.8CPUs report address/genericPAC, key-access unprobed. Native audio clock corrected24MHz to19.2MHz; audible wake recovery unresolved.
- drivers/ 板级驱动拆为 Chengdong-Yu/pong-\* submodule；本 area 路径下的文件随对应仓库迁出，路径名不变。

**local-runtime-integration（`pong.md:1464-1517`）**

- services85完整内核与匹配运行时已编译，96MiB OS更新已安装；Fastboot Sending/Booting均OKAY，Data/SystemOS保留。
- services113: official rootful Procursus/Sileo, genuine iphoneos-arm repository indices and mobile sileolists permissions staged; expanded writable OS and real package configuration required before qualifying installation.

**cumulative-runtime-pr167（`pong.md:1519-1567`）**

- Merged native helper/UI/audio/sleep/Sileo/phone/route binaries, frontend,ArmCpu and changed GPU units compiled. Prepared Mesa source reproduces all25 changed source files; current device results remain separately recorded.
- drivers/ 下 12 个板级驱动拆为 Chengdong-Yu/pong-\* submodule；路径名与相对 include 保持不变，package.yml 已有 submodules: recursive。

## 6. 附录：`pong.md` 32 个区域与起始行

| # | 区域 | 起始行 | status |
|---|---|---|---|
| 1 | Configuration | 48 | implemented |
| 2 | Firmware and boot | 91 | implemented |
| 3 | CPU and interrupts | 130 | implemented |
| 4 | Memory and DMA | 173 | implemented |
| 5 | Storage and root | 213 | implemented |
| 6 | Display | 255 | implemented |
| 7 | Input | 310 | implemented |
| 8 | GPU | 361 | implemented |
| 9 | Network | 423 | implemented |
| 10 | Audio | 484 | implemented |
| 11 | Power | 557 | implemented |
| 12 | Image assembly | 606 | implemented |
| 13 | Diagnostics | 645 | implemented |
| 14 | mobilegestalt-device-information | 710 | implemented |
| 15 | native-category-volume | 752 | implemented |
| 16 | native-ringtone-display-wake | 794 | implemented |
| 17 | main-gpu-metal-ringer149 | 835 | implemented |
| 18 | adreno-ringer-freeze150 | 875 | implemented |
| 19 | control-center-native-ringtone151 | 916 | implemented |
| 20 | upstream-metal-keyboard152 | 957 | implemented |
| 21 | gpu-guide-memory-bgra153 | 998 | implemented |
| 22 | gpu-real-execution-hotpath155 | 1041 | implemented |
| 23 | metal-interface-ui-stalls156 | 1083 | implemented |
| 24 | gpu-priority-timing160 | 1126 | implemented |
| 25 | audio-wake-active-acquire162 | 1171 | implemented |
| 26 | audio-prepare-command-stages163 | 1218 | implemented |
| 27 | lock-sound-admission164 | 1267 | implemented |
| 28 | scheduling-metal-audio-clock165 | 1314 | implemented |
| 29 | submit-retirement-publication166 | 1363 | implemented |
| 30 | frame-ownership-pac167 | 1409 | implemented |
| 31 | local-runtime-integration | 1464 | implemented |
| 32 | cumulative-runtime-pr167 | 1519 | implemented |

## 7. 附录：本次精读的边界

- 已完整读取 `pong.md`（1-1567 行）、`pong-agxmx666.md`（1-523 行）、`pong-hxzbaka.md`（1 行）、`pong-kmu1757.md`（1-7 行）、`pong-y3d4.md`（1 行）以及 `index.md` 的 pong 行（179-183）。
- `pong.md` 的 74 个 Evidence 链接全部指向同一 commit `e0ee6df...`；`pong-agxmx666.md` 的 14 条链接全部指向 `ffdad78...`。
- 页面没有给出、因此标为未核实的内容：Pong GPU 的实际制造工艺/温度曲线、K60 与 Pong 的 PMIC 逐轨对应、K60 面板型号与 DSI 时序、Pong 的 suspend/resume 完成状态（`configs/pong-power-sm8475.json:130` 明确 `suspend_resume_implemented=false`）。
- 本文没有修改 `patches/`、`series`、`drivers/`、`userland/`、`board.toml`、`dts/`、`uefi-pong` 或任何构建脚本；所有实现建议都是“按 pong 页提取的落点”，未在 K60 上编译或烧写。
