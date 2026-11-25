# iOS 27 驱动架构归属矩阵（第二版 · 参考源优先级）

> 目的：回答「27 的每个硬件层，架构与思路是否严格跟着官方维护的 sheng 最新代码与官方文档」。
> 用户 2026-11-21 定的口径（本版核心）：
> **默认一切照官方 sheng 与官方文档；只有「硬件本身不同、根本抄不了」的部分，才去参考其他同 SoC 实现。**
> pong 谱系（16.6.1 我们自己的历史）只作行为对照，**不作为 27 的架构来源**。

## 参考源优先级（自上而下，不许跳级）

1. **官方 sheng 主干**：`E:/iOS Port/Sources/Repos/UniXNU/UniXNU-sheng`（同 `ipados-27.0.1-24A446` profile，27 是它在维护的那条）。
2. **官方文档**：`unixnu.com/zh/...`（本地镜像 `E:/iOS Port/Sources/Repos/UniXNU/UniXNU/docs/zh`），每步要 `{#anchor}`（iron-17）。
3. **同 SoC 实现**：`UniXNU-t970`（SM8550）、`UniXNU-zizhan`、`UniXNU-liuqin` —— **仅当 1、2 都没有对应实现**，
   且必须写明「硬件哪里不同，所以官方那份不能用」。
4. pong 谱系 / 我们自己 16.6.1 的代码：只允许用来**解释旧行为**（为什么当年这么做），不允许作为新代码的蓝本。

## 三条判定规则

1. **官方有同能力实现（通用层）** → 直接 adopt 官方，我们只提供设备数据（ADT/DTS/toml 属性）。
2. **官方有实现、但硬件参数不同** → 保留官方驱动，把差异做成数据，不 fork 代码。
3. **官方无对应实现**（硬件独有，例如我们的 modem/baseband 栈）→ 才允许自研；此时参考源是第 3 级同 SoC，
   并且要在矩阵里写清「官方为什么没有」「同 SoC 谁有、差在哪」。

任何一行若写成「保留我们的 fork」而不属于规则 2/3，必须在矩阵里给出反证（为什么官方那份用不了），
否则一律按规则 1 处理。**「先 fork 一版以后再合」在本线是禁止项。**

## 矩阵（每行必须给 文件:行 依据）

| 层 | 官方对应物（sheng / 27） | 我们的现状 | 规则 | 决定 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 固件 | catalog `DarwinBoot` pin `3c75734`（fileset 分支） | vendored fork + `ImageCarrierLib` | 2（官方逻辑 + 我们的载具） | **已 adopt**：catalog parser 移植并加越界检查 | `components.toml:58` |
| CPU | `component:ArmCpu` `93a5030c`（psciConduit + opt-in SMP） | 779 行 fork（与 xnekom 逐字节相同） | 1（官方有）→ 暂缓 | **stage-0 保留 fork，F2 后必须切回官方**：三条缺口用补丁/数据补 | `drivers/ArmCpu/ArmCpu.cpp:1` |
| 显示 | `NativeLegacyDisplay.cpp`（27 独立栈 659 行） | 16.6.1 改 Mini 栈 + `K60Backlight` | 1（官方有） | **重写到官方栈**：Mini 栈在 27 是死路 | `K60Backlight.cpp:230` |
| GPU | `Adreno740` kit + sheng `GpuPowerProbe.cpp:1568` | Metal 前端是官方件的落后副本（差约 292 行） | 2（同架构、落后） | **re-vendor 官方件** + wire ABI v1→v2 | `GPU-27-CONTRACT-DIFF.md:1` |
| 音频 | `zzyf-sheng-amp.patch` + `zzyd-sheng-audio-addon-mount.patch` | `PongAudio`（970 行骨架，PAS1 TODO） | 1（官方有） | **adopt addon mount 路线**，只留 codec 数据 | `board.toml:360` |
| 存储 | `ShengUfs` + source-storage policy（190 槽） | `NativeUfs` + 47 KB 自研 transport | 1（官方有） | **默认 adopt ShengUfs + source-storage**；route D 可行性已给出 | `board.toml:360` |
| 电源 | `ShengPlatformPower` / `ShengBattery` / `CpuFreqProbe` | `K60PmicRail` / `K60Battery` / `K60Battmgr` | 1 + 2（电压/rail 数据） | **默认 adopt 官方框架**，rail 差异做成数据 | `K60Battmgr.c:161` |
| WiFi | `Ath12kWifi`（SM8550 / QCN92xx） | `Ath11k`（QCA6490） | 3（芯片不同） | **keep 设备驱动**，ABI/策略/扫描照官方；参考 t970 | `board.toml:21` |
| 蓝牙 | `QcaBluetooth` | 0500–0513 系列自研 | 3（部分硬件差异） | **keep 传输层 + 对齐官方 H4/TLV/NVM** | `board.toml:14` |
| 蜂窝 | 上游无实现（baseband 栈本线独有） | IPA/QRTR/rmtfs 自研 | 3（官方无） | **允许自研**，写明「上游没有」；参考 zizhan 行为 | 上游无实现，见 `docs/research/cellular/20-MODEM-BRINGUP-FLIGHT.md:1` |
| USB | `QcomDwc3` | usb 线自研 gadget + 控制台 | 待 usb27 判 | 默认按规则 1 处理，等 usb27 给官方对应物 | `board.toml:76` |
| 输入 | `ShengNovatekTouch` / `ShengHidInput` / `QcomGeniSpi` | Goodix Berlin + Geni SPI | 3（芯片不同） | **keep 设备驱动 + adopt 官方 HID 路径**；参考 t970 | `board.toml:267` |

## 各线要交的东西（一步到位）

每条线在 `docs/research/<lane>/ARCH-27.md` 回答四句：

1. **官方对应物**：`文件:行`；没有就写「上游无实现」并给全仓 grep 命中数。
2. **规则编号**：属于 1 / 2 / 3 的哪一类，附证据（不是判断）。
3. **差异清单**：规则 2 列出全部设备数据项；规则 3 列出「官方为什么没有 + 同 SoC 谁有 + 差在哪」。
4. **决定与成本**：adopt / data-only / rewrite；rewrite 要给「先做哪块、多少行、何时能上机、中间态如何不倒退」。

## 门禁（下一步实现）

`scripts/check-driver-arch.py`：每个 `docs/research/eight-step/*-27.toml` 的硬件项必须在本文档矩阵里有行，
该行要有规则编号、决定、至少一个 `文件:行` 依据；写「待定」超过一轮即失败。
「偷偷 fork 一版带进 27」会在账本层被拦住，而不是等上机才发现。
