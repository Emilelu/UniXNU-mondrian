# 05 · 热压等级（thermal pressure level）：从 32 个传感器到 macOS 的 mTPL

本篇记录热管理线里**唯一不碰硬件**的那一半：把本板 32 个 tsens 传感器的读数映射成 macOS 的
`OSThermalPressureLevel`。数据与算术已落地为 `drivers/PongThermal/K60ThermalLevel.{h,c}`，主机单测
`scripts/tests/test-k60-thermal-level.c` 72 项断言全过；**发布这个值的 IOKit 服务尚未写**（见 §6）。

---

## 1. 为什么必须有这一半

XNU 自己不算热压等级。macOS 侧唯一的消费者是 `thermalmonitord`：

- 它 `IOServiceMatching("AppleSMCSensorDispatcher")`，selector 0 取 key 数量，selector 1 取 key 码表，
  selector 2 按码表顺序取 15 个 32 位值；一个 1.0 s 的 runloop timer 轮询（**没有通知，是轮询**）。
- 然后取 key `mTPL`（0x6d54504c）的值，值变了就 `notify_set_state` + `notify_post`
  `com.apple.system.thermalpressurelevel`。**这个值本身就是 OSThermalPressureLevel**，daemon 不做换算。
- Foundation 再把它翻成 `NSProcessInfoThermalState`：1、2 → Fair，3 → Serious，4 → Critical，其余 → Nominal。
- 客户端必须持有 `com.apple.private.smcsensor.user-access`（Apple 原实现 `initWithTask` 里检查）。

出处：参考移植 SM8550 的 `ThermalLevel.h:6-25`（从 thermalmonitord of macOS 27.3 26C5035r arm64e 切片
读出的地址：`-[SensorDispatcherHelper init]` 0x10000c0b0、timer 0x100011ed0、`readKeysFromSensorDispatcher`
0x10000c234、`updateAllThermalLoad:` 0x10000ca48、`updateThermalNotification:` 0x10000f828），以及
`ThermalLevel.cpp:6-21` 的服务说明。等级枚举见 `libkern/OSThermalNotification.h`：
nominal 0 / moderate 1 / heavy 2 / trapping 3 / sleeping 4。

**没有这一半的后果**：本板在 macOS 下永远报 nominal，而固件/内核在真实降频 —— 上层拿不到任何信号。

---

## 2. 五个输入域与它们的 trip 点（全部来自本板 DTB）

参考实现用 4 个输入（3 个 CPU 频域 + GPU）。本板的 DT 里 **CPU 两个簇的 trip 完全相同**，而 NPU 与 DDR
各有一组不同的 trip，所以这里用 5 个输入：little / big / gpu / npu / ddr。每个输入的阈值都取该域自己
zone 的 trip，**没有一个是编的**。

| 输入 | zone（DT 行） | trip 1 | trip 2 | trip 3 |
|---|---|---|---|---|
| cpu-little | `cpu-0-0` :7680 | 110 ℃ / 10 ℃ 滞后（`cpu0-emerg-cfg` :7706, :7707 = 0x1adb0 / 0x2710） | 115 ℃ / 5 ℃（`reset-mon-cfg` :7700, :7701 = 0x1c138 / 0x1388） | 125 ℃ / 1 ℃（`thermal-engine-config` :7688, :7689 = 0x1e848 / 0x3e8） |
| cpu-big | `cpu-1-0` :7213 | 110 ℃ / 10 ℃（`cpu4-emerg0-cfg` :7239, :7240） | 115 ℃ / 5 ℃（`reset-mon-cfg` :7233, :7234） | 125 ℃ / 1 ℃（`thermal-engine-config` :7221, :7222） |
| gpu | `gpuss-0` :7575 | 95 ℃ / 5 ℃（`tj_cfg` :7601, :7602 = 0x17318 / 0x1388） | 115 ℃ / 5 ℃（`reset-mon-cfg` :7595, :7596） | 125 ℃ / 1 ℃（`thermal-engine-config` :7583, :7584） |
| npu | `nspss-0` :7848 | 95 ℃ / 5 ℃（`junction-config` :7874, :7875） | 115 ℃ / 5 ℃（`reset-mon-cfg` :7868, :7869） | 125 ℃ / 1 ℃（`thermal-engine-config` :7856, :7857） |
| ddr | `ddr` :7995 | 90 ℃ / 5 ℃（`ddr0-config` :8009, :8010 = 0x15f90 / 0x1388） | 115 ℃ / 5 ℃（`reset-mon-cfg` :8016, :8017） | 125 ℃ / 1 ℃（`thermal-engine-config` :8003, :8004） |

CPU 的两个簇在 DT 里各有 4 个 trip，但 `thermal-engine-config` 与 `thermal-hal-config` 是同一组数
（都是 125 ℃ / 1 ℃，:7688/:7689 与 :7694/:7695），所以去重后只有 3 个不同阈值。`thermal-hal-config`
是 Android HAL 的入口，XNU 侧不需要它，记在这里是为了说明"为什么 4 个 trip 只用 3 个"。

其余 27 个 AP 传感器的 zone（aoss-0/1、cpuss-0..3、video、mdmss-0..3、camera-0/1）**有 trip 但没有冷却动作**，
在等级映射里记为 `K60TlNoInput`：它们照常被 `K60Tsens.c` 采样并打日志，只是不参与等级。

---

## 3. 映射规则（与参考实现逐条对齐）

1. **一个输入的电平 = 它越过的 trip 数**（0..3）。第一档 moderate，第二档 heavy，第三档 trapping。
2. **滞后**：trip 在其温度处被越过；一旦越过，只有当读数**低于 温度 − 滞后**才释放（thermal core 的规则）。
   注意"低于"是严格小于：110 ℃ / 10 ℃ 滞后的 trip 在 100000 m℃ 时仍然算越过，99999 才释放 —— 这一条
   主机测试里专门钉了两个断言（`test_input_level`）。
3. **板级电平 = 各输入电平的最大值**。
4. **没有读数的输入算 nominal，并且忘掉它越过的 trip**：读不到的传感器既不能抬高电平，也不能撑住电平。
5. **sleeping 永不上报**：本板没有任何 trip 代表它。

实现：`k60tl_input_level()` 做第 1、2 条（`trips == NULL` / `trips_count == 0` / `K60TL_NO_READING` 一律返回 0），
`k60tl_step()` 做第 3、4 条并维护每个输入自己的 `crossed[]` 状态。

与参考实现的一处**故意差异**：参考实现有 `THERMAL_LEVEL_STALE_ROUNDS = 3`，用 probe 的采样计数判断
"读数是不是旧的"（`ThermalLevel.h:99-120`）。本板没有后台采样线程 —— `k60tl_step()` 的调用者就是
`k60tsens_read_controller()` 的调用者，读数与等级在同一轮里同步产生，所以"旧读数"这个概念不存在；
一次读失败由调用者直接传 `K60TL_NO_READING`。这比 stale 计数更直接，也不需要额外状态。

---

## 4. 传感器 → 输入域对照表

`k60tl_sensor_input[32]` 的顺序与 `K60Tsens.c` 的 `k60tsens_sensor_table` 一致：tsens0 idx 0..15，然后
tsens1 idx 0..15（zone 24..55，见 01-SAME-HARDWARE.md §5.1）。

| 传感器 idx | zone | 输入域 |
|---|---|---|
| 0..4 | aoss-0, cpuss-0..3 | 不用 |
| 5..13 | cpu-1-0..8 | cpu-big |
| 14, 15 | gpuss-0, gpuss-1 | gpu |
| 16 | aoss-1 | 不用 |
| 17..20 | cpu-0-0..3 | cpu-little |
| 21..23 | nspss-0..2 | npu |
| 24 | video | 不用 |
| 25 | ddr | ddr |
| 26..29 | mdmss-0..3 | 不用 |
| 30, 31 | camera-0, camera-1 | 不用 |

---

## 5. 核验

- `cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongThermal scripts/tests/test-k60-thermal-level.c`
  → `TESTS OK 72`（4 组：trip 表本身、单输入电平与滞后边界、整板 step 与每输入状态、32 项传感器映射）。
- 交叉编译：`scripts/build-thermal-driver.sh` 用 `clang -target arm64-apple-ios16.6.1 -ffreestanding` 产出
  `build/thermal/K60ThermalLevel.o`（Mach-O 64-bit arm64 object），`llvm-nm --defined-only` 命中 6 个必需
  符号、`llvm-nm -u` 为空；`llvm-size -A` 报 `__const` 248 B（四张 trip 表 + 32 字节映射表 + 名字表）。
- 全部阈值与滞后在 `K60ThermalLevel.c` 的注释里逐条标了 DT 行号，测试里也把 110/10、95/5、90/5 三个
  关键数钉成断言 —— 改数就必须改测试。

---

## 6. 还缺什么（为什么这一半还不是"完成"）

1. **IOKit 服务本体**：一个 `AppleSMCSensorDispatcher` IOService + `AppleSMCSensorDispatcherUserClient`，
   selector 0/1/2 分别返回 key 数（1）、key 码表（mTPL）、值（现算的电平，最多 2 次/秒），selector 3 接受
   写入但什么都不做；类名必须是 Apple 的，因为 daemon 按类名匹配、其沙箱 entitlement 里写的是 user client 类名。
   参考实现是 `ThermalLevel.cpp:47-217`（`publish()` 设 `IOUserClientClass` 后 `registerService()`；
   用 boot arg `thermal-level=1` 才注册，默认关闭）。
2. **内核链接行与 IODeviceMemory 映射**：`K60Tsens.c` 的 `const volatile uint32_t *tm` 还没有人给它填
   `0xc263000` / `0xc265000` 的映射（铁则第 5 条：地址有 DT 出处，但映射代码要进内核构建）。
3. **上机**：SROT_HW_VER / SROT_CTRL bit0（TSENS_EN）与 32 路 STATUS 原始字从未读过（见 04 篇 §9），
   这决定了 `k60tsens_read()` 拿到的到底是不是真温度。

这三项都需要 ⑦⑧ 阶段（内核集成 + 上机窗口），不是本阶段能做的。
