# ldoc2 / pm8350c_l2：从 AP 侧点亮触摸 IOVDD 的完整契约

本文记录 **K60（mondrian / SM8475）上 `pm8350c_l2`（触摸 IOVDD 1.8 V）如何由 XNU 侧
通过 RPMh 投票点亮**。这是触摸、音频、电池三条线的共同堵点。

状态（2026-11-14）：**已实测打通**。yibiya 的 `fix/goodix-reset-handshake` 分支
（`d82df47 fix(touch): request actual IOVDD through RPMh`）在真机上拿到 ACK，
observer 侧确认 `ready/enable/valid=1800mV`，随后 BERLIN/9916R 固件、IC-info 校验、
1488 字节配置下载与坐标模式 ACK 全部通过，BackBoard 打开了真实 `pong-touch` 设备
（`console-20261114-050030.log`）。Lead 自己的只读探针独立复现了其中的地址与身份字节。

## 1. 为什么必须走 RPMh

- `pm8350c_l2` 是 RPMh 管理的 PMIC5 LDO。AP 侧**没有** SPMI 通道（`K60LDO rev=11
  ppid=0x241 apid=-1`），直接写 SPMI 会被拒（`raw PMIC RW is denied`）。
- 固件树里**没有任何** RPMh/RSC 实现：在 `uefi-mondrian` 里
  `grep -rli -e rpmh -e apps_rsc Platforms Common Silicon` 为 0 命中。所以只能在
  XNU 侧投票。
- 早期尝试走 Qualcomm secure-I/O（`TZ_IO_ACCESS_READ/WRITE`，`smc #0`，
  function `0xc2000501`/`0xc2000502`）被 monitor 以 `-2` 拒绝，一次投票都没写成。
  **结论：用直接 MMIO 映射 `0x17a20000`，不要用 secure-I/O helper。**

## 2. 硬件常量（设备 DTB + 实测）

| 项 | 值 | 来源 |
| --- | --- | --- |
| APSS RSC DRV2 物理基址 | `0x17a20000`，64 KiB | DTB `/soc/rsc@17a00000` 的 `reg` 第三段 |
| cmd-db 物理基址 | `0x80860000`，128 KiB | DTB `/reserved-memory/aop_cmd_db_region@80860000` |
| cmd-db magic | `0x0c0330db` | 实测 `K60RAIL cmd-db magic=0xc0330db version=1` |
| TCS 偏移 | `0xd00` | DTB `qcom,tcs-offset` |
| TCS 步长 | `0x2a0`（672） | 实测 v2 布局 |
| 命令槽步长 | `20` 字节 | 实测 v2 布局 |
| **本板 TCS 编号** | **3**（不是 4） | yibiya 实测；DT 在 Android 上是 active0..2/sleep3..4，**不要按 DT 推** |
| `ldoc2` VRM 地址 | `0x42c00` | 实测 `K60RAIL ldoc2 address=0x42c00` |
| `ldoc2` aux 身份字节 | `01 2a 00 00`（4 字节） | 实测 `l0=10753` = `0x2a01`，即这 4 字节的小端 u16 读法 |
| 电压请求 | 1800 mV 写 `0x42c00` | yibiya 实测 |
| 使能请求 | 1 写 `0x42c04` | yibiya 实测 |

**`ldoc2` 的 aux 是身份，不是电平表。** 这一点极其重要：Lead 的只读探针把 aux 当
u16 电平数组解析，于是打印出 `levels=1 l0=10753`——看起来像"只有一个电平 10753 mV"，
实际是 4 个身份字节 `01 2a 00 00`。按电平表理解会得出"这个 rail 没有 1800 档"的错误
结论，从而永远投不出票。校验方式：`le16(aux) == 0x2a01` 且后两字节为 0。

## 3. RSC v2 寄存器布局（本板 `drv_id=0x20700`）

`((drv_id >> 16) & 0xff) == 2` → **v2**。实测
`K60RAIL rsc drv_id=0x20700 version=2 stride=672 cmd=20 ctrl=0x14 enable=0x1c
msgid=0x30 addr=0x34 data=0x38`，与参考实现
`UniXNU-sheng/package/QcomRpmh.c:53-57` 的 `qcom_rsc_layout()` 完全一致。

| 字段 | TCS 内偏移 |
| --- | --- |
| `irq_status` | `0x04` |
| `irq_clear` | `0x08` |
| `wait_for_cmpl` | `0x10` |
| `control` | `0x14` |
| `status` | `0x18` |
| `cmd_enable` | `0x1c` |
| `cmd_msgid` | `0x30` |
| `cmd_addr` | `0x34` |
| `cmd_data` | `0x38` |

常量：`MSGID_WRITE_RESPONSE = 8 | 1<<8 | 1<<16`（本板实测用 `0x10108`）、
`CONTROL_ACTIVE_MODE = 1<<16`、`CONTROL_TRIGGER = 1<<24`。

## 4. 投票序列（两条命令，电压 + 使能）

前提：持锁（`pong-rsc` 互斥量，与 GPU 的 ARC 投票共用同一把，因为 TCS3 只有一个
owner）。前置检查全部通过才动手：

1. 读 `caps = rd(rsc, 0xc)`；`count = (caps>>12)&63`、`ncpt = (caps>>27)&31`。
   要求 `count >= 8`、`2 <= ncpt <= 16`，否则 `ENXIO`/`EINVAL`。
2. 读 TCS3 的 `idle`(`+0x18`)、`control`(`+0x14`)、`enabled`(`+0x1c`)。
   **`!idle || enabled || (control & (1<<24))` 就返回 `EBUSY`** —— 光看 idle 不够，
   已 armed 或原因不明的旧租约不能抹掉。
3. 扫 TCS3 与 TCS4 的已保留命令槽：若已有 `address == 0x42c00` 的请求，取
   `voltage = max(1800, 已有值)`，且已有值必须落在 `1800..1980`；若已有
   `address == 0x42c04` 且值 > 1 则 `EINVAL`。**永不降低已有请求。**
4. 检查 TCS4 没有与 `0x42c00`/`0x42c04` 冲突的 in-flight 命令，否则 `EBUSY`。
5. **先置 quarantine**（`tcs3_quarantined = true`），此后任何失败都保持隔离，
   绝不去回收未确认的事务。
6. `wr(rsc, 0xd00, rd(rsc,0xd00) & ~(1<<3))` 清本 TCS 的 trigger；
   `control &= ~(1<<24)` 后写回，poll 直到相等（500 µs）；
   `control &= ~(1<<16)` 后写回，poll 直到相等（500 µs）；
   `wr(base+0x1c, 0)`、`wr(rsc, 0xd08, 1<<3)`，poll `rd(rsc,0xd04) & (1<<3) == 0`。
7. 写两条命令：`msgid=0x10108`、`addr=0x42c00`/`0x42c04`、`data=1800`/`1`
   （槽位 `base+0x30+20*i`、`+0x34+20*i`、`+0x38+20*i`）。
8. `wr(base+0x10, 3)`、`wr(base+0x1c, 3)`、`wr(base+0x14, 1<<16)`，
   poll `control == 1<<16`（500 µs）。
9. `wr(base+0x14, (1<<16)|(1<<24))` 触发。
10. 等完成：最多 10000 次 × 10 µs（100 ms），每次读
    `first = rd(base+0x3c)`、`second = rd(base+0x50)`、`idle = rd(base+0x18)`；
    要求两条命令都 `(x & 0x10100) == 0x10100`（ISSUED|COMPL）且 `idle`，
    并且期间出现过"未完成"（`progressed`）或 `rd(rsc,0xd04) & (1<<3)`。
11. 收尾：`wr(base+0x1c, 0)`、`wr(rsc,0xd08,1<<3)`、
    `wr(base+0x14, rd(base+0x14) & ~(1<<24))`，然后解除 quarantine、记
    `retained_voltage`。

**IRQ3 全程保持屏蔽**，靠轮询而不是中断。

## 5. ACK 之后还要验的（否则等于没通电）

RPMh ACK 只代表"请求被接受"，不代表 PMIC 真的输出了 1.8 V。yibiya 的做法是再用
PMIC observer 读 `SID2 C200`（APID 181，type 4 sub 87）的 `ready/enable/valid`，
三个都满足且 `valid` 覆盖 1800 mV 才释放 RESET：

- 未投票时实测：`ready=0 enable=0 program=1800 valid=0 mode=7 status=3`
  （注意 `program=1800` 是**目标值寄存器**，不是输出）。
- Android 侧同一外设：`ready=1 enable=1 valid=1800`。
- 投票并 ACK 之后：`ready=1 enable=1 valid=1800` → 才允许 `gpio_output(RESET, true)`。

**`AVDD GPIO71` 的 IO 电平读数不能当供电证明**（`IO=3` 只说明 pad 在驱动高电平，
不说明 1.8 V 存在）。旧记录里把 `AVDD71 IO=3` 当"已供电"是错的。

## 6. 复位与上电顺序（Berlin D）

`brl_power_on` 的真实时序（`goodix_core.ko` 反汇编，`0x11104`，3136 字节）：

- **初次上电没有 8×0xAA 握手**（`0xaa` 的 8 处命中全在 `brl_esd_check`、
  `goodix_shortcircut_test`、`goodix_ts_pm_resume`，`brl_power_on` 内一处也没有）。
  所以 `goodix_dev_confirm()` 对 9916R 是错的。
- `0xc900`/`0xd807`/`0xd806`/`0xd006`/`0xd808` 是 Berlin-A 专用（`0xc900` 只出现在
  `brl_select_spi_mode` 内），不能用于 9916R。
- 正确顺序：供电（RPMh ACK + observer 验证）→ `AVDD GPIO71` 拉高 → 等 15 ms →
  释放 RESET → 等 100 ms → 读 chip ID。

## 7. SPI 引脚角色

QUP[4] L0..L3 = **GPIO16/17/18/19**（SM8475/SM8475P 数据手册 80-27620-1 Rev.AJ
Table 2-4，printed p44；Xiaomi mondrian-s-oss `pinctrl-cape.h` 确认 qup4 function
slot1）。`board.toml` 的 `bitbang-pins` 因此是
`"10000000110000001200000013000000"`（16,17,18,19）。

旧的 24-permutation 扫描只证明"某个 pad 在 pull-up 下浮高"，从未证明 lane 角色；
旧表 `"11000000120000001000000013000000"`（17,18,16,19）是错的。

## 8. 已知陷阱

- **不要把 aux 当电平表**（本文 §2）。这是 Lead 自己踩过的坑。
- **不要用 `0x17a00000`**（DRV0）。只映射 DRV2 `0x17a20000`。
- **不要用 secure-I/O SMC**（§1）。
- **不要按 DT 的 `qcom,tcs-offset`/active 划分猜 TCS 编号**：DT 说 active0..2，
  本板实测可用的是 TCS3。
- **不要在未持锁时投票**：GPU 的 ARC 投票与触摸 IOVDD 共用 TCS3。
- 投票失败后**不要重试抹掉**：事务已改，保持 quarantine，重新上电再来。

## 9. 参考

- yibiya `fix/goodix-reset-handshake`：`d82df47`（实现）、`71d8941`（契约文档）、
  `e72c735`（内核内初始化互斥量）、`f8c49f8`/`ec82bc9`/`fb74efc`（observer 取证）。
- `/mnt/e/hackios/UniXNU-sheng/package/QcomRpmh.c`（`qcom_cmd_db_find` /
  `qcom_rsc_layout` / `qcom_rpmh_active_request`）。注意该参考板是 SM8550，
  只能作结构参考，常量必须用本板实测值。
- Lead 的只读探针：`drivers/PongPower/K60PmicRail.c`，上机日志
  `E:\k60-work\evidence\usblog-20261114-railh\console.log:477-479`。
