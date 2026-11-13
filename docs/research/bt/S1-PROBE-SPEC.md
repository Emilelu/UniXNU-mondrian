# S1 只读探针规格（k60bt_stage=1）

状态：规格 + 可直接应用的补丁已完成，**未合入构建**。补丁：`patches/bt/0001-k60-bt-readonly-probe.patch`（2,939 B，2 个 hunk，`git apply --check` 通过）。
上游计划：`docs/research/bt/RESEARCH.md` §5（阶段 S1）与 §8（I-5）。

## 1. 目的

回答唯一一个决定整条线生死的问题：**在这台 K60 上，对 QUPV3_2 / SE20 窗口的第一次寄存器访问会不会像触摸（QUP0 SE4）和音频（I2C）那样零日志打死机器。**

- 支撑事实（M）：`docs/research/GENI-ACCESS-PRECONDITIONS.md` 记录两次独立复现，控制台 0 字节。
- 反面证据（本轮新增）：mainline SM8450 GCC 只建模 4 个 GDSC（`linux-gcc-sm8450-v6.6.c:3235-3239`），vendor `k60-android-gcc-waipio.c` 全文无 `gdsc`；因此 sheng 的 `gcc_qupv3_wrap0_gdscr` **不适用于 SM8475**，首要怀疑改为 wrapper 声明的 NoC/interconnect（FDT `qmondrian.dts:10707-10720` 的 `interconnect-names="qup-core","snoc-llcc","qup-ddr"`，本 port 无 ICC 框架）。

## 2. 变更（补丁内容）

对 `bsd/dev/qbt_k60.c`（由 `patches/xnu/0500-k60-bt-qbt-new-files.patch` 创建，1,249 行）做两处插入：

1. 在 `static int k60_bt_power_on(void)` 之前插入 4 个寄存器常量 + `k60_bt_probe()`：
   - `k60_map()` GCC（0x00100000）、SE20（0x00894000）、wrapper（0x008C0000）；**不 map** TLMM/GIC/SMMU；
   - `k60_serial_clock(true)`（现成函数，0500 内：GPLL0 投票 + 5 个 QUPV3_2 分支投票 + halt 轮询 + CBCR 打印）；
   - 4 次只读：`SE_GENI_STATUS`、`GENI_IF_DISABLE_RO`、`GENI_FW_REVISION_RO`、`QUP_HW_VER_REG`，外加 `K60_GCC_WRAP2_SE20_HALT`；
   - 用 `k60_log()` 打印一行，返回 0。
2. 在 `k60_worker()` 里 `int e = k60_bt_power_on();` 之前插入：
   `if (k60.stage == 1) { int p = k60_bt_probe(); k60_power_result(true, p); return; }`
   —— 这样 S1 在 worker 线程里跑完即退出，**不进入** `k60_bt_power_on()` 的 GPIO/XO/BT_EN/DMA/中断路径。

## 3. 寄存器与字段的出处（不允许猜）

| 值 | 出处 |
|---|---|
| `SE_GENI_STATUS = 0x040` | `linux-geni-se-v6.6.h:78` |
| `GENI_IF_DISABLE_RO = 0x064`，`FIFO_IF_DISABLE = BIT(0)` | `:81`、`:129-130` |
| `GENI_FW_REVISION_RO = 0x068`，协议字段 `GENMASK(15,8)` | `:82`、`:132-134` |
| `QUP_HW_VER_REG = 0x0004`（wrapper），期望 `QUP_SE_VERSION_2_5 = 0x20050000` | `linux-qcom-geni-se-v6.6.c:114`、`linux-geni-se-v6.6.h:287` |
| SE20 = wrapper 0x8C0000 的第 6 个 SE（0x894000） | live FDT `mondrian.dts:10707-10720`、`:11041`、别名 `:21484` |
| GCC QUPV3_2 vote 0x62010、SE20 halt 0x2E610、core 0x33280、core_2x 0x3328C、m_ahb 0x2E004、s_ahb 0x2E008 | 0500:109-124；vendor `k60-android-gcc-waipio.c:1371,3075` |

## 4. 上机步骤（严格执行，顺序不可换）

```bash
# 0) 设备必须是 fastboot 模式（序列号只认 6033dbec）
bash scripts/k60-device.sh state

# 1) 构建 + 本地验证（补丁合入后）
python3 scripts/sync-device-input.py
python3 scripts/check-rules.py
bash scripts/build-strict.sh
python3 scripts/verify-boot-image.py <boot.img>

# 2) 先挂 CDC-ACM 捕获（铁律 8：不挂捕获的 fastboot boot 一律无效）
#    VID_1209&PID_0001 / usbser.sys / 端口只从
#    HKLM\HARDWARE\DEVICEMAP\SERIALCOMM 的 \Device\USBSER000 取，DTR 必须拉高

# 3) 同一镜像跑两次
fastboot boot <boot.img>   # boot args: k60bt=1 k60bt_stage=1 k60bt_warm=1
fastboot boot <boot.img>

# 4) 记录
python3 scripts/record-boot.py --evidence <evidence-dir>
```

`k60bt_warm=1` 是必须的：0500 的 `k60_bt_power_on()` 在 `!k60.warm_boot` 时直接返回 `-EOPNOTSUPP`（PMIC 轨由 Android 冷启动/引导器留下）。S1 不碰电源，但保留该参数以保持与后续阶段一致。

## 5. 判据（只读 capture.json 的 `verdict` / `panicMarker`，不看 logstat.py 的 panic 计数）

| 观察 | 结论 | 下一步 |
|---|---|---|
| 控制台出现 `[bluetooth] clocks vote ...` 与 `[bluetooth] probe: se20 status=... fwrev=... proto=... qup_hw=... se_halt=...`，机器正常跑完 | **SE20 可达** | 进 S2（引脚 mux + 3.0 Mbaud + 引擎准备） |
| `[bluetooth] probe: mapped ...` 之后**任何日志都没有**，控制台 0 字节 | 首次访问即死机（与触摸/音频同因） | 停线；把结果回填 `GENI-ACCESS-PRECONDITIONS.md`；检查项：wrapper NoC/ICC、GDSC（备选）、SE 时钟边界 |
| 停在 `[bluetooth] clocks vote ...` 之后（halt 轮询超时） | 时钟分支不响应 | 检查 GPLL0 是否锁（`gcc+0x0` BIT(31)）、vote 位是否被 firmware 覆盖 |
| `[bluetooth] probe: map failed` | `ml_io_map` 拒绝该窗口 | 说明窗口已被其它驱动占用或未在设备树 enabled |
| `proto` 字段 ≠ 2 | boot firmware 没给 SE20 的 PROTOCOL 2 microcode | 与 `docs/porting/bluetooth.md:42-43` 的 ENXIO 情形一致，S3 前必须先解决 |

`qup_hw` 期望 `2005xxxx`（QUP_SE_VERSION_2_5）。若不是，说明 wrapper 版本与官方组件假设不符，S2 的引擎序列要按实际版本重查。

## 6. 接线（Lead 二选一，均在本线写权限之外）

- **选项 A（推荐，不动 series）**：把补丁的两个 hunk 合入 `patches/xnu/0500-k60-bt-qbt-new-files.patch`。0500 是「新建文件」补丁，改其内容不影响 `patches/xnu/series`，`check-build-applied.py` 仍匹配。
- **选项 B（独立补丁）**：在 `patches/xnu/` 放 `0503-k60-bt-readonly-probe.patch`，在 `patches/xnu/series` 末尾追一行，然后 `sync-device-input.py`。注意 series 长度变化会让 `check-pick-shrink.py` / `check-patch-series.py` 重新验证。

两种方式都必须跑：`python3 scripts/check-rules.py`、`python3 scripts/eight-step-gate.py --build`、`python3 scripts/check-docs.py`。

## 7. 风险与回滚

- 全部新增行为在 `k60bt=1` 且 `k60bt_stage=1` 时才执行；默认启动（不带 boot-arg）完全不进 S1 代码路径。
- S1 不写任何设备分区、不碰 `/dev/block/sda38`、不改 PMIC/RPMh；只读 GCC/UART/wrapper 寄存器。
- 回滚 = 从 `patches/xnu/series` 去掉该补丁（或把 stage 恢复为默认 1 之外的完整路径）。
