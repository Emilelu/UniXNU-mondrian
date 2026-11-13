# S1 只读探针规格（k60bt_stage=1）

状态：**S1a 已上机一次 → 0 字节控制台、板子挂死，不可判定**（§0）；**S1b 已生成、接入构建并构建完成**（§0.1，镜像 `bt-s1b-20261114a`），待物理断电复位后上机。
补丁：`patches/bt/0001-k60-bt-readonly-probe.patch` = `patches/xnu/0507-k60-bt-readonly-probe.patch`（8,331 B / 192 行 / 25 个打点，sha256 `6136fc67c849a95277296477284811210a7c69d13264e19483179f9c4c52fc96`），接在 `patches/xnu/series:205`（0502 之后、0503 之前）。
上游计划：`docs/research/bt/RESEARCH.md` §5（阶段 S1）与 §8（I-5）。
⑥ 深挖依据：`docs/research/bt/06-DEEP-DIVE.md`（F1–F3 就是本规格多读 4 个寄存器的原因）。

## 0. S1a 上机实测（2026-11-14 04:51，唯一一次）

| 项 | 值 |
|---|---|
| 镜像 | `/mnt/e/k60-work/artifacts/bt-s1-20261114b/boot.img`，sha256 `2fef132a394c14178db52fde2dd6c705d5cab10a0e597092c8adb1512a6c8378` |
| 内核 | `kernel_built 78bf198636d01ffe6e453623e0d311da8a7dd3ee940f68035f84ade9620bcf8f`（series 224） |
| boot args | `k60bt=1 k60bt_stage=1 k60bt_warm=1`（已在 payload 的 `unixnu.toml` 里核实） |
| fastboot | `Sending 'boot.img' (197156 KB) OKAY [4.532s]`、`Booting OKAY`、exit 0 |
| 捕获 | `/mnt/e/k60-work/evidence/usblog-20261114-bts1b-run1/`：`capture.json` state=`port-not-observed`、`bytes=0`、`portOpened=false`、`stopReason=port-timeout`、`panicMarker=null`、空日志 sha256 `E3B0C442…B855` |
| 之后 | `adb devices` 空、`fastboot devices` 空、Windows PnP 无任何 Qualcomm/CDC 设备 → `scripts/k60-device.sh` 所述「USB 掉线的挂死，只能物理断电」 |

结论（四条，都已确定）：

1. **这次上机不可判定**：控制台 0 字节，没有任何 `[bluetooth]` 行，所以探针跑到第几步完全未知。
2. **挂死来自 `k60bt=1` 路径，不来自构建**：同一颗 `kernel.macho` 在**不带** `k60bt` 的镜像（`bt-s1-20261114a`，boot_img `7b6b02fc…`）里正常跑到用户态（`capture-budget-complete`，3,192 行 / 214,089 B）。
3. **顺带拿到的 iOS 侧事实**：那次成功的控制台里 `bluetoothd` 已经起来，并反复打印
   `marconi-bt: Unable to match bluetooth service in device tree.` / `bluetooth: Unable to match bluetooth service in device tree.` /
   `Not a valid MAC address (all 00s).` / `bluetoothd: No bluetooth on this device.`
   —— 与 `RESEARCH.md` §2/§3 一致：20G81 只有用户态栈，且它要求设备树里有一个 `bluetooth` 节点 + 非零 MAC 才会继续。
4. **所以 S1b 的目标不是「再读一遍寄存器」，而是「让死机点可观测」**：先等控制台真的活着并能排空，再在**每一次寄存器访问之前**打一行点。

### 0.1 S1b 镜像（2026-11-14 05:23 构建完成，尚未上机）

| 项 | 值 |
|---|---|
| 构建 tag | `bt-s1b-20261114a`，仓库 head `7d06d1b`（dirty 0，series 224） |
| boot.img | `/mnt/e/k60-work/artifacts/bt-s1b-20261114a/boot.img`，201,887,744 B，sha256 `a9fe69b9e10030039878086cf4f594b20b19fdc432811e2de61ca73fb9e56a9c` |
| 内核 | `kernel_built 356bd8493d69333d19ac2c6b33cbc7efc22d91554469f63382f452cea620a00d`（54,173,696 B） |
| payload | `8cb0c26a5cd0ea312de96bd3acf12c471194511f3c6d4b9d9ac2766192c844f3`；ADT `9ab17e468f5fc5390328b03f672236997f2eea7c22b1ac0f4548ccd8ac461c1e` |
| boot args | payload 行尾 `… applog=1 k60bt=1 k60bt_stage=1 k60bt_warm=1`（manifest 记录的 `kernel_args` 三项齐全） |
| 校验 | `scripts/verify-boot-image.py --manifest …` → `verify-boot-image: OK` |
| 上机状态 | **未上机**：板子自 S1a 起处于 USB 掉线挂死，必须先物理断电复位 |

同一镜像可加 `k60bt_delay=20 k60bt_step=6`（默认即此值）或把 step 调低做二分。

## 1. 目的

回答唯一一个决定整条线生死的问题：**在这台 K60 上，对 QUPV3_2 / SE20 窗口的第一次寄存器访问会不会像触摸（QUP0 SE4）和音频（I2C）那样零日志打死机器。** 并机械判定 ⑥ 深挖留下的 F2/F3。

- 支撑事实（M）：`docs/research/GENI-ACCESS-PRECONDITIONS.md` 记录两次独立复现，控制台 0 字节。
- 反面证据：mainline SM8450 GCC 只建模 4 个 GDSC（`linux-gcc-sm8450-v6.6.c:3235-3239`），vendor `k60-android-gcc-waipio.c` 全文无 `gdsc`；因此 sheng 的 `gcc_qupv3_wrap0_gdscr` **不适用于 SM8475**，首要怀疑改为 wrapper 声明的 NoC/interconnect（live FDT `mondrian.dts:10707-10720` 的 `interconnect-names="qup-core","snoc-llcc","qup-ddr"`，本 port 无 ICC 框架）。

## 2. 变更（S1b 补丁内容）

对 `bsd/dev/qbt_k60.c`（由 `patches/xnu/0500-k60-bt-qbt-new-files.patch` 创建，1,249 行）做两处插入，共 192 行 diff：

1. 在 `k60_xo_release()` 之后、`k60_bt_power_on()` 之前插入：

   - 8 个寄存器常量（出处见 §3）+ 4 个探针常量：
     `K60_PROBE_DELAY_SECS=20`、`K60_PROBE_MAX_DELAY_SECS=120`、`K60_PROBE_MAX_STEP=6`、`K60_PROBE_DRAIN_US=2000`；
   - `k60_probe_mark(step)`：`k60_log()` 打一行 **再** `IODelay(2000)`，让 CDC 环在下一访问前排空；
   - `k60_probe_u32(tag, value)`：`probe: <tag>=%08x` + 2 ms 排空；
   - `k60_bt_probe(unsigned step)`：**6 个可分子步骤**，每步**先打点再访问**：
     - `s1` map GCC(0x00100000)/SE20(0x00894000)/wrapper(0x008C0000)（不 map TLMM/GIC/SMMU），打印三个 VA；
     - `s2` 读 `GPLL0_CMD`(0x62018) → 置 BIT(0) → 轮询 `gcc+0x0` BIT(31) 锁定位（1000×1 µs，失败即 `-ETIMEDOUT` 返回）；
     - `s3` 读 QUPV3_2 投票 0x62010 → 或上 `K60_GCC_VOTE_ALL` → 回读；
     - `s4` **逐个**读 5 个 halt 寄存器（core 0x33280 / core_2x 0x3328C / m_ahb 0x2E004 / s_ahb 0x2E008 / se20 0x2E610），每个都单独打点；
     - `s5` 逐个读 `SE_GENI_STATUS` 0x040 / `GENI_IF_DISABLE_RO` 0x064 / `GENI_FW_REVISION_RO` 0x068 / `G_MANUAL_RFR` 0x2AC + wrapper `QUP_HW_VER_REG` 0x004；
     - `s6` 逐个读 `SE_DMA_TX_IRQ_STAT` 0xC40 / `SE_DMA_RX_IRQ_STAT` 0xD40 / 未命名 0xE40 / 复读 0x040；
     - 收尾打 `probe: done`。
   - **不写任何设备分区、不拉 BT_EN、不做引脚 mux、不装中断、不碰 DMA**；唯一的写是 GPLL0 使能位和 QUPV3_2 投票（与 0500 既有 `k60_serial_clock()` 完全同一对写）。

2. `k60_worker()`：在 `qbt_create()` **之前**插入 stage==1 的分支：
   - 解析 `k60bt_delay`（默认 20 s，上限 120 s）与 `k60bt_step`（默认 6，范围 1–6）；
   - 打 `probe: armed delay=%us step=%u` → `IOSleep(delay*1000)` → 打 `probe: awake`；
   - 之后在 `qbt_create` / `qbt_transport_init` / addon 门之后各打一行（`probe: core created`、`probe: transport ready`、`probe: addon gate passed`）——这样连「死在 Skywalk provider 注册」都能区分；
   - 跑 `k60_bt_probe(step)` → `k60_power_result(true, p)` → **直接 return**，不进 `k60_bt_power_on()`。

   为什么要把 delay 放在 worker 最前面：`qbt_k60_start()` 由 0502 插在 `bsd_init.c` 的 `k60_usblog_start()` 之后，此时 USB gadget 还没枚举完；一个立刻访问 GENI 的线程足以在控制台出现第一个字节之前把机器打死——S1a 就是这么丢掉全部证据的。20 s 之后 CDC 控制台已经在正常打印（对照启动 4 s 内就有 K60 USBLOG 行）。

## 3. 寄存器与字段的出处（不允许猜）

| 值 | 出处 | 读它的原因 |
|---|---|---|
| `SE_GENI_STATUS = 0x040` | `linux-geni-se-v6.6.h:78` | 判定引擎是否 idle（M/S active = BIT(0)/BIT(12)） |
| `GENI_IF_DISABLE_RO = 0x064`，`FIFO_IF_DISABLE = BIT(0)` | `:81`、`:129-130` | FIFO 接口是否可用 |
| `GENI_FW_REVISION_RO = 0x068`，协议字段 `GENMASK(15,8)` | `:82`、`:132-134` | 协议必须 = 2，否则组件 `prepare()` 返回 `-ENXIO` |
| `QUP_HW_VER_REG = 0x0004`（wrapper），期望 `QUP_SE_VERSION_2_5 = 0x20050000` | `linux-qcom-geni-se-v6.6.c:114`、`linux-geni-se-v6.6.h:287` | 决定 16x 还是 32x 过采样 |
| `G_MANUAL_RFR = 0x2AC`，组件只用 0 / `G_RFR_OFF = 0x80000002` | 官方组件 `src/qbt_geni_regs.h:30,80`；`src/qbt_geni.c:18-21` | **F2**：0500:766 写了 `0x80000001`，既非 ready 也非 not-ready |
| `SE_DMA_TX_IRQ_STAT = 0xC40` / `SE_DMA_RX_IRQ_STAT = 0xD40`，reset-done = BIT(3) | `linux-geni-se-v6.6.h`（`TX_RESET_DONE`/`RX_RESET_DONE`） | S2 若重写 stop_engine，必须用这两个位 |
| `0xE40`（无名字） | **两边都没有定义**：mainline 头文件从 `SE_HW_PARAM_1 0xe28` 直接结束，`qbt_geni_regs.h` 亦无 | **F3**：0500:631/639 轮询它；若读出非零，`stop_engine()` 恒定 `-ETIMEDOUT` |
| SE20 = wrapper 0x8C0000 的第 6 个 SE（0x894000） | live FDT `mondrian.dts:10707-10720`、`:11041`、别名 `:21484` | 窗口身份 |
| GCC GPLL0 0x62018 BIT(0)、QUPV3_2 vote 0x62010、SE20 halt 0x2E610、core 0x33280、core_2x 0x3328C、m_ahb 0x2E004、s_ahb 0x2E008 | 0500:109-124；vendor `k60-android-gcc-waipio.c:1371,3075` | 投票与 halt 判定 |

## 4. 上机步骤（严格执行，顺序不可换）

```bash
# 0) 设备必须是 fastboot 模式（序列号只认 6033dbec）；挂死的板子先物理断电
bash scripts/k60-device.sh state

# 1) 构建 + 本地验证
python3 scripts/sync-device-input.py
python3 scripts/check-rules.py
bash scripts/build-strict.sh <tag> --fd <fd> --kernel-arg k60bt=1 --kernel-arg k60bt_stage=1 --kernel-arg k60bt_warm=1
python3 scripts/verify-boot-image.py --manifest <artifact>/build-manifest.json

# 2) 先挂 CDC-ACM 捕获（铁律 8），再 fastboot boot；同一镜像两次
#    args: k60bt=1 k60bt_stage=1 k60bt_warm=1 [k60bt_delay=20] [k60bt_step=6]

# 3) 落账
python3 scripts/record-boot.py --image <boot.img> --log <evidence>/console.log
```

- `k60bt_warm=1` 是必须的：0500 的 `k60_bt_power_on()` 在 `!k60.warm_boot` 时直接返回 `-EOPNOTSUPP`。S1 不碰电源，但保留该参数以保持与后续阶段一致。
- 建议的两次：
  - **A1 / A2**：`k60bt_delay=20 k60bt_step=6`（两次同参，铁律 5 要求的「同一镜像两次」）；
  - **B**（只在 A 挂死时做）：把 `k60bt_step` 降到死点前一步，验证「去掉那次访问机器就不死」——这是把死因锁定到单条 load 的最强证据，而且能给出一条**健康启动 + 完整时钟读数**的记录。

## 5. 判据（只读 capture.json 的 `verdict` / `panicMarker`，不看 logstat.py 的 panic 计数）

S1b 的核心判据是「最后一行打点」——因为打点在访问**之前**，所以最后一条 `probe: sX ...` 就是死因。

| 观察 | 结论 | 下一步 |
|---|---|---|
| 出现 `probe: done` 且机器继续跑 | SE20 全窗口可达；读数值进 §5 表判定 | 进 S2 |
| 最后一行 = `probe: s1 map ...` | `ml_io_map` 死 | 查窗口归属/是否被 UEFI 占用 |
| 最后一行 = `probe: s2 read gpll0_cmd` / 更早 | **GCC 第一次访问就死** | 与 GENI 无关；转 GCC 前提（NoC/PD） |
| 最后一行 = `probe: s2 poll gpll0 lock` | GPLL0 锁不上 | 查 firmware 是否把 GPLL0 关掉 / 位定义 |
| 最后一行 = `probe: s4 read halt <name>` | 死在哪个 halt 寄存器 | 该分支的 CBCR 不可读 → 时钟域未上电 |
| 最后一行 = `probe: s5 read se status` | **SE20 第一个 load 即死**（与触摸/音频同因） | 停线；回填 `GENI-ACCESS-PRECONDITIONS.md` |
| 最后一行 = `probe: s6 read se rsvd_e40` 之类的后段 | 前面都通，只有某个偏移死 | 记录偏移，评估是否需要跳过该寄存器 |
| 停在 `probe: transport ready` 之后、`probe: addon gate passed` 之前 | 死在 addon 门（等不到 `native_gpu_addon_stage`） | 与 BT 无关的启动顺序问题 |
| 停在 `probe: core created` 之前 / 之后 | 死在 Skywalk provider 注册 | 先解决 transport 注册，再谈 GENI |
| 停在 `probe: armed` 之后没有任何行 | `IOSleep` 期间就死了（说明不是探针） | 查上一行之后的启动阶段 |

数值判据（拿到 `probe: done` 时）：

| 观察 | 结论 |
|---|---|
| `s5 fw_rev` 的 protocol 字段（`(fwrev>>8)&0xff`）≠ 2 | boot firmware 没给 SE20 的 PROTOCOL 2 microcode，组件 `prepare()` 会 `-ENXIO`（`docs/porting/bluetooth.md:42-43`）→ S3 前必须先解决 |
| `s5 qup_hw_ver` ≠ `0x2005xxxx` | wrapper 版本与官方假设不符 → S2 引擎序列要按实际版本重查 |
| `s6 rsvd_e40` ≠ 0 | **F3 成立**：`stop_engine()` 恒 `-ETIMEDOUT` → 先按 `TX/RX_RESET_DONE`(0xc40/0xd40 BIT(3)) 重写 |
| `s5 rfr` = `80000002` | 与组件 not-ready 编码一致 → 删掉 0500:766 的第三值 |
| `s4 halt *` 的 BIT(31) 仍置位 | 该分支未运行 → 投票没生效或时钟域未上电 |

## 6. 接线（已按选项 B 接入，留档）

- 已执行：`patches/xnu/0507-k60-bt-readonly-probe.patch` + `patches/xnu/series:205`，并跑过 `sync-device-input.py`（铁律 5：镜像同步）。
- 历史选项 A（把 hunk 折进 0500）未采用，因为 0500 是纯「新建文件」补丁，改动它会让已归档的 0500 sha256 失效、难以追溯。

## 7. 风险与回滚

- 全部新增行为只在 `k60bt=1` 且 `k60bt_stage=1` 时执行；默认启动完全不进 S1 代码路径。
- 最坏情况就是 S1a 已经发生过的那一种：挂死、需要物理断电。**不会再丢证据**——S1b 先等 20 s 让控制台活着，再逐访问打点。
- 回滚 = 从 `patches/xnu/series` 去掉 0507 一行（Patch 本身留在树里），或把 `k60bt` 去掉。

## 8. ⑦ 本地验证（S1b，已做）

| 项 | 命令 / 依据 | 结果 |
|---|---|---|
| 补丁 SHA-256 | `sha256sum patches/bt/0001-k60-bt-readonly-probe.patch` | `6136fc67c849a95277296477284811210a7c69d13264e19483179f9c4c52fc96`（8,331 B / 192 行） |
| 生成方式 | `E:/k60-work/scratch/bt-s1b/gen.py` 对 0500 抽出的 `qbt_k60.c` 做两处**带断言**的替换，再 `git diff` 出补丁（不手写 hunk） | `EXTRACT_OK`（抽出文件与参照 `8451c870…` 逐字节一致） |
| 补丁可应用 | 干净 0500 树上 `git apply --check` | `APPLY_CHECK_OK`；apply 后文件内 `probe: ` 命中 25 处 |
| 语法检查 | `BT_ROOT=<patched tree> python3 E:/k60-work/scratch/bt-s1/check.py bsd/dev/qbt_k60.c bsd/dev/qbt/qbt_core.c`（clang `-target arm64-apple-ios16.0` + out3 `.CFLAGS`） | `PASS bsd/dev/qbt_k60.c rc=0`、`PASS bsd/dev/qbt/qbt_core.c rc=0` |

- 探针只增加 MMIO 读取、一次 GPLL0 使能写与一次投票写（与 0500 既有的 `k60_serial_clock()` 同一对写），不含算术/越界写；`k60_gcc_wait_halt` 等既有函数的超时路径未改。

## 9. 交接（Lead 执行）

1. 构建并上机（§4）。**先物理断电复位**：S1a 那次把板子留在挂死状态。
2. 把最后一行 `probe: sX ...` 与 `capture.json` 的 `verdict`/`panicMarker` 回填本文件 §0 与本表。
3. 结论回填：`docs/research/GENI-ACCESS-PRECONDITIONS.md`（触摸/音频共用同一前提）、`docs/research/bt/06-DEEP-DIVE.md`（F2/F3 的结论行）、`docs/research/bt/RESEARCH.md` §5.4。
4. 若 S1 判「首访即死」→ 本线停在这里，写 blocker；若通过 → 进 S2（引脚 mux + RCG 3.0 Mbaud + 引擎准备，见 `RESEARCH.md` §5）。
