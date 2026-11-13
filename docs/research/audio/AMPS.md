# 扬声器功放 — K60 (SM8475 / cape) 判定与纯 AP 只读路径

> 目标子系统：扬声器功放（AW882xx / WSA883x 判定）、GENI I2C、GCC 时钟、TLMM
> 日期：2026-11-14
> 状态：① 同型 ✅ ② 官方 ⚠️ ③ 反编译 ✅ ④ 广域 ✅ ⑤ 方案 ✅ ⑥ 深挖 ✅ ⑦ 本机验证 ⏳ ⑧ 上机 ❌

## 1. 结论

1. **K60 的扬声器功放是 Awinic AW882xx 系列（两颗），不是 WSA883x。**
   live FDT 里 `wsa-macro@3240000` 与 `wsa2-macro@31E0000` **都是 `status = "disabled"`**
   （`live-fdt.dts:23475-23502`、:23532-23559），其下的 `wsa883x@02170221/222` 自然也不生效；
   真正挂在总线上的是 `i2c@880000` 下的 `aw882xx_smartpa@34` / `@35`（`live-fdt.dts:13318-13341`）。
2. **两颗功放的 I2C 地址是 0x34（左/ch0）与 0x35（右/ch1）**，走 **QUPV3 wrapper 2 的 SE0**
   （`i2c@880000` = 主线 `sm8450.dtsi:981-999` 的 `i2c15`，clocks = `GCC_QUPV3_WRAP2_S0_CLK`）。
3. **具体是哪一颗 AW882xx（AW88261 / AW88262 / AW88395 …）尚未确定** —— DT 只写 `awinic,aw882xx_smartpa`。
   必须靠**读寄存器 0x00 的 chip ID** 才能定（AW88261 = `0x2113`）。**这是本子任务唯一能在 ADSP 之前完成的实机验证。**
4. **K60 与 phk110 的功放板级差异很大，时序不能照抄**：

| 项目 | phk110（POCO X5 Pro） | K60（mondrian） |
|---|---|---|
| 型号 | AW88261 ×2（chip ID `0x2113`） | AW882xx ×2（型号待读） |
| I2C 总线 | 串行引擎 3（GPIO12 data / GPIO13 clock） | QUPV3 wrapper2 SE0（0x880000），GPIO56 SCL / GPIO57 SDA |
| I2C 地址 | 0x34 / 0x35 | 0x34 / 0x35 |
| reset 引脚 | **两颗都没有** | **@34 = GPIO1，@35 = GPIO3**（`live-fdt.dts:13322/13335`） |
| sound-channel | @35 = ch0（左），@34 = ch1 | **@34 = ch0，@35 = ch1**（`:13325/13338`，相反） |
| spksw | — | @34 有 `spksw-gpio = GPIO52`；@35 **没有** |
| IRQ | — | @34 = GPIO88，@35 = GPIO63，flags 0x2008 |

→ **reset 引脚与 sound-channel 都相反**，直接搬 phk110 的 `prepare()` 会把左右声道弄反、并跳过必要的复位。

## 2. live FDT 逐条（③ 反编译）

### 2.1 `i2c@880000`（`live-fdt.dts:13301-13342`）

| 属性 | 值 |
|---|---|
| `compatible` | `qcom,i2c-geni` |
| `reg` | `<0x880000 0x4000>` |
| `interrupts` | `<0 0x175 4>`（GIC SPI 373） |
| `pinctrl-0` | `<0x100>`（active 组） |
| alias | `qupv3_se15_i2c = "/soc/i2c@880000"`（:33889、:34286） |

引脚（`live-fdt.dts:3562-3593` `qupv3_se15_i2c_pins`，phandle 0x2da）：
active phandle **0x100**：pins `"gpio56"` `"gpio57"`，function `"qup15"`，`drive-strength = <2>`（2 mA），`bias-pull-up`；
sleep phandle 0x101：function `"gpio"`，2 mA，`bias-disable`。

> 主线 `pinctrl-sm8450.c:1472-1473`：`[56] = PINGROUP(56, qup15, ibi_i3c, …)`、`[57] = PINGROUP(57, qup15, ibi_i3c, …)`
> → **qup15 是 function 1**（`PINGROUP` 里第一个可选 function 的索引为 1）。
> 与 Pong 的写法 `pin(n, 3u | (1u << 2), -1)` 一致：`[1:0] = 3`（pull-up）、`[5:2] = 1`（function 1）。

### 2.2 `aw882xx_smartpa@34`（`:13318-13329`）

| 属性 | 值 |
|---|---|
| `compatible` | `awinic,aw882xx_smartpa` |
| `reg` | `0x34` |
| `irq-gpio` | `<0x3c 0x58 0x2008>` → phandle 0x3c（TLMM）、**GPIO88**、flags 0x2008 |
| `reset-gpio` | `<0x3c 0x01 0x00>` → **GPIO1** |
| `dc-flag` / `sync-flag` | 0 / 1 |
| `sound-channel` | 0 |
| `aw-cali-mode` | `"aw_none "` |
| `spksw-gpio` | `<0x3c 0x34 0x00>` → **GPIO52** |
| 供电属性 | **无**（没有 `vdd-supply` 之类） |

### 2.3 `aw882xx_smartpa@35`（`:13331-13341`）

同形状，差异：`reg = 0x35`、`irq-gpio` → **GPIO63**、`reset-gpio` → **GPIO3`、`sound-channel = 1`、
**没有 `spksw-gpio`**、也没有供电属性。

> **没有供电属性 = DT 不声明功放供电**，说明它由 boot 链/PMIC 默认态提供（Pong 与 touch 的注释都是这个口径）。
> 上机必须先读回 rail 状态，**不许**假定已通电就写功放寄存器。

## 3. 总线侧：GCC 时钟（⑥ 深挖，源 = `gcc-sm8450.c`）

`/home/emilelu/k60tmp/gcc-sm8450.c`（3,487 行，与主线 `/home/emilelu/wifi-inputs/linux/drivers/clk/qcom/gcc-sm8450.c` 的 qupv3 段一致）。

| 时钟 | `halt_reg`(CBCR) | `enable_reg`（AP 投票寄存器） | `enable_mask` | 行 |
|---|---|---|---|---|
| `gcc_qupv3_wrap2_core_clk` | 0x33280 | **0x62010** | BIT(0) | :2404-2409 |
| `gcc_qupv3_wrap_2_s_ahb_clk` | 0x2e008 | **0x62010** | BIT(1) | :2618-2625 |
| `gcc_qupv3_wrap_2_m_ahb_clk` | 0x2e004 | **0x62010** | BIT(2) | :2603-2610 |
| `gcc_qupv3_wrap2_core_2x_clk` | 0x3328c | **0x62010** | BIT(3) | :2391-2396 |
| `gcc_qupv3_wrap2_s0_clk` | **0x2e00c** | **0x62010** | BIT(4) | :2417-2422 |
| `gcc_qupv3_wrap2_s0_clk_src` | —（RCG） | cmd_rcgr **0x2e014** | — | :888-896 |

- **wrapper2 的投票寄存器是 0x62010，不是 0x62008**（0x62008 是 wrapper0/wrapper1 的）。
  touch 驱动用的是 wrapper0 SE4，所以它的 0x62008 不能照抄。
- `BRANCH_HALT_VOTED`（`clk-branch.c:50-59`）：halt 判据是 CBCR 的 `CLK_OFF` 位；**硬件时钟门控生效时
  CBCR 会报 CLK_OFF**，所以「CLK_OFF == 0」是假阴性判据（PITFALLS 已记录同一坑）。
- RCG 偏移（`clk-rcg2.c` + touch 补丁算术交叉验证）：`CFG = cmd_rcgr + 0x4`、
  `SE_CMD_DFSR = cmd_rcgr + 0x14`、`SE_PERF_CFG(l) = cmd_rcgr + 0x1c + 4l`、
  `SE_PERF_M_DFSR(l) = cmd_rcgr + 0x5c + 4l`、`SE_PERF_N_DFSR(l) = cmd_rcgr + 0x9c + 4l`。
- GPLL0：`enable_reg 0x62018` BIT(0)；PLL_MODE 在 `+0x0`，lock 位 BIT(31)（`gcc-sm8450.c:50-55`）。

### 3.1 Pong 的总线初始化（`PongAudio.cpp:130-144`，形状可复用，索引要换）

```
gcc.w(0x62008, gcc.r(0x62008) | (15u<<18) | (1u<<27));       // ← K60 必须换成 0x62010 且重新选 bit
gates[] = {0x3314c, 0x33140, 0x28004, 0x28008, 0x28610};      // ← Pong 的 wrapper1 SE5，K60 不适用
i2cPins = {48, 49}; pin(n, 3u | (1u<<2), -1);                 // ← K60 是 {56, 57}
se.open(0xa94000, 0x4000); proto = (se.r(0x68) >> 8) & 0xff;  // ← K60 是 0x880000
level: for i<8: cfg = gcc.r(0x28618 + 0x1c + 4i); 选档        // ← K60 是 0x2e014 + 0x1c + 4i
se.w(0x28, se.r(0x28)|0x7f); se.w(0xe30, se.r(0xe30)|15);
se.w(0x24, 0x7f); se.w(0x20, 1); se.w(0xe18, 0);
se.w(0x7c, level); se.w(0x48, 0x21);                          // GENI_SER_M_CLK_CFG
se.w(0x278, (5u<<20)|(11u<<10)|22);                           // SCL counters: hs 5 / fs 11 / 22
```

> **K60 上必须改的四处**：投票寄存器 0x62008→0x62010、SE 基址 0xa94000→0x880000、
> RCG 0x28618→0x2e014、引脚 48/49→56/57。其余（GENI 寄存器偏移、SCL 计数器、DFS 选档算法）可直接复用。

## 4. 功放寄存器表（AW882xx 家族，源 = `hakios.speaker.c:355-401`）

这些偏移在 **AW882xx 整个家族**上位置相同（phk110 的驱动注释明确说「registers that every chip of the family
has at the same place and that reading does not change」，`hakios.speaker.c:1118`）。

| 偏移 | 名称 | 语义 |
|---|---|---|
| **0x00** | `AW_ID` | **读 = chip ID；写 `0x55aa` = 软复位** |
| 0x01 | `AW_SYSST` | 状态（见下方位定义） |
| 0x02 | `AW_SYSINT` | 中断状态（读即清除） |
| 0x03 | `AW_SYSINTM` | 中断屏蔽（默认 `0xffff`） |
| 0x04 | `AW_SYSCTRL` | bit0 `PWDN`、bit1 `AMPPD`、bit8 `HMUTE`、bit14 `ULS_HMUTE` |
| 0x05 | `AW_SYSCTRL2` | `[9:0]` 音量衰减：`[9:6]` 6 dB 步进、`[5:0]` 1/8 dB |
| 0x06 | — | I2S control |
| 0x08 | `AW_I2SCTRL3` | bit6 `TXEN` |
| 0x14 | `AW_DBGCTRL` | bit3 `EF_OR`（fuse 两份副本 or/and 选择） |
| 0x21 | `AW_VBAT` | `[9:0]` 电池电压：× 6025 / 1023 mV |
| 0x22 | `AW_TEMP` | `[9:0]` 温度（℃，二补数） |
| 0x23 | `AW_PVDD` | `[9:0]` boost 供电 |
| 0x24 / 0x25 | `AW_ISNDAT` / `AW_VSNDAT` | 电流/电压采样 |
| 0x50 | `AW_VSNTM1` | 校准值 = `8192 × (1000 + icalk) / (1000 + vcalk)` |
| 0x78 / 0x79 / 0x7c / 0x7d | `AW_EFRH4/EFRH3/EFRL4/EFRL3` | fuse（算 icalk/vcalk） |

状态位（`AW_SYSST`）：`PLLS 1<<0`、`OTHS 1<<1`、`OCDS 1<<3`、`CLKS 1<<4`、`NOCLKS 1<<5`、`WDS 1<<6`、
`SWS 1<<8`、`BSTS 1<<9`、`BSTOCS 1<<11`、`UVLS 1<<14`、`OVP2S 1<<15`；
`PLL_CHECK = CLKS|PLLS`；`FAULTS = OVP2S|UVLS|BSTOCS|WDS|NOCLKS|OCDS|OTHS`。

chip ID 表（`hakios.speaker.c:340-350`）：0x2013 AW88264 / 0x2032 AW88266 / 0x2049 AW88395 / 0x2055 AW88256 /
0x2066 AW88166 / 0x2071 AW88350 / **0x2113 AW88261** / 0x2183 AW88399 / 0x2308 AW88230。

### 4.1 读写事务（`PongAudio.cpp:108-110`）

```
读：写 1 字节 {reg}（带 stop）→ 读 2 字节 → value = (rx[0] << 8) | rx[1]     // 高字节先到（大端）
写：写 3 字节 {reg, value>>8, value}
地址 = 0x34 + amp（0/1）→ 与 K60 的 0x34/0x35 完全同形状
```

## 5. 纯 AP 只读验证方案（本子任务可独立完成的部分）

**不碰 LPASS、不需要 ADSP。** 全部是 AP 自己的寄存器：

| 步骤 | 动作 | 判据 |
|---|---|---|
| A1 | 映射 GCC 0x100000 一页（0x62010/0x62018 所在页），投 GPLL0 与 wrapper2 五个 bit | 回读 0x62010 的 bit0..4 全为 1 |
| A2 | 映射 TLMM GPIO56/57 页（`0xf000000 + 0x100000 + 0x1000*n`），配 function 1 / 2 mA / pull-up | 回读 config `[5:2] == 1` |
| A3 | 映射 GENI SE15 0x880000 一页，读 `GENI_FW_REVISION_RO(0x68)` | `(v >> 8) & 0xff == 3`（I2C） |
| A4 | 按 §3.1 形状初始化 GENI（换掉四处索引），选 DFS 档 | `SE_GENI_STATUS(0x40)` 无 error 位 |
| A5 | 对 0x34 / 0x35 各发一次「写 1 字节 reg=0x00 + 读 2 字节」 | 得到 chip ID；0x2113 → AW88261 |
| A6 | 只读 fuse 0x78/0x79/0x7c/0x7d 与 0x01/0x04/0x06 | 打印原始值，**不解释、不写** |
| A7 | 打印 GPIO1/3/43/52/88/63 的 config/IO 原始值 | 记录 Android 退出时的引脚状态 |

失败即停（不重试、不写任何功放寄存器）。**A5 的结果直接决定「移植哪份驱动」这个硬问题。**

## 6. 已交付代码

`drivers/PongAudio/`（4 个源文件 + 1 个说明，均 BSD-2-Clause-Patent）：

| 文件 | 内容 |
| --- | --- |
| `PongAudioRegs.h` | 上面全部地址/偏移/位定义，每条带来源标注（L = `live-fdt.dts`、G = `gcc-sm8450.c`、S = Pong 参考树、M = 主线 `geni-se.h`/`i2c-qcom-geni.c`、H = `hakios.speaker.c`） |
| `PongAudioPlan.h` | 探针的判定逻辑做成纯函数：pad 地址与 pad 配置字、CBCR「是否在跑」判据、GCC 三窗口路由、DFS 档可用性、AW882xx 字节序与 chip id 表。无 MMIO、无内核头 → 这些判定由宿主单测钉住，而不是靠上机试 |
| `PongAudioGeniI2c.h` / `.c` | Pong `GeniI2c.c` 的移植，符号改 `pong_geni_*` 避免与 Pong 副本冲突，状态机逻辑逐字保留 |
| `PongAudioAmp.c` | A1–A7 的实现：8 页 TLMM 回读 → GCC wrapper2 投票 → I2C 引脚 → SE15 引擎 → 放 reset → 只读 13 个寄存器；每次传输前 `bus_recover()` 把可能卡死的状态机走回 Idle；boot-arg `pong_audio_probe=1` 才跑，失败只报数不 panic |
| `README.md` | 逐步骤做了什么、为什么是这个顺序、期望日志形状、上机命令、八步自评 |

补丁：`patches/audio/0001-k60-audio-amp-probe.patch`（45,655 B，1,218 行，7 段）+ `patches/audio/series`。

- 5 个文件**逐字**放进 `bsd/dev/`：应用后已用 `cmp` 证明与 `drivers/PongAudio/` 完全一致；
- `bsd/conf/files` 加两条对象（`bsd/dev/PongAudioGeniI2c.c standard`、`bsd/dev/PongAudioAmp.c standard`）；
- `bsd/kern/bsd_init.c` 加一段调用，锚在 0505 的 `pong_audio_bootstrap()` 之后。
- **顺序要求**：必须在 `patches/xnu/0501` 与 `0505` 之后，因为两处锚点分别由 0501（`bsd/dev/qbt/btqca.c`）和 0505（`pong_audio_bootstrap()`）建立；而 0501 又依赖 0300/0243/0340 已加进 `bsd/conf/files` 的 `k60_usblog` / `k60_uilib` / `k60_console_export` 三行。**已用真实链验证**（不是合成预映像）：在构建缓存 `.../tree/.cache/xnu-work` 的 `bsd/conf/files`+`bsd/kern/bsd_init.c` 上按 0501 → 0505 → 本补丁顺序 `patch -p1 --forward` 落地，**rc=0、无 reject**。本补丁**无 fuzz**，只有行偏移（conf/files +6、bsd_init.c +15）；链条中唯一带 fuzz 的是 0505 自身（`Hunk #1 succeeded at 1329 with fuzz 1 (offset -19 lines)`，它的锚点与该前映像有 1 行差异，与本补丁无关）。四个新文件与 `drivers/PongAudio/` 逐字节相同。完整 transcript 见 `patches/audio/README.md`。
- 编译核验：`PongAudioAmp.c` 与 `PongAudioGeniI2c.c` 都在真实 XNU bsd 构建目录里用 `-fsyntax-only` + `-DARM64_BOARD_CONFIG_PONG` + `-Werror` 过了（`PASS: PongAudioAmp.c` / `PASS: PongAudioGeniI2c.c`），因此 `#if defined(PONG)` 里的代码确实被编译过。**守卫本身也验证过**：`E:/k60-work/scratch/audio-work/probe-pong.c` 只做 `#if !defined(PONG) #error`，用同一套 flags 编译得到 `PASS: probe-pong.c`，即 `PONG` 由 `board_config.h` 定义、探针不是死代码（这是「静默不跑」这类故障的必要前提）。

### 6.1 宿主单测（八步 ⑦ 的本地核验，147 例）

`drivers/PongAudio/tests/` **不进内核、也不进补丁**：它只编译 `PongAudioGeniI2c.c`（纯状态机，无 XNU 头依赖），
用假 MMIO 喂 `M_IRQ_STATUS` 序列，把「读事务必须两段（写指针持 stop → 读数据）」这类只靠上机才会暴露的错误变成可重复的本地检查。
`PongAudioAmp.c` 依赖内核头，不能宿主编译；所以它的**判定逻辑**被抽到 `PongAudioPlan.h`（纯函数、无 MMIO），由单测逐条钉住，留在 `.c` 里的只剩 MMIO 时序——那部分只能靠语法检查与一次上机说话。

```
# Windows 侧没有 cc/gcc/clang（PATH 里只有 winuxcmd），必须在 WSL 里跑：
wsl.exe -e bash -lc 'cd /mnt/e/hackios/k60-audio && sh drivers/PongAudio/tests/run-tests.sh'
# → TESTS OK 147 cases   (cc -std=gnu11 -Wall -Wextra -Werror)
```

覆盖范围：

| 组 | 断言内容 |
| --- | --- |
| `register_map_cases` | `TLMM_PHYS+GPIO_OFF == 0x0f100000`；GPIO88 寄存器地址 `0x0f158000` 落在 `pinctrl@f000000` 的 `0x1000000` 窗口内；GCC 三个 1 页窗口分别覆盖 `RCG_SE15 0x2e014` / `CBC_CORE 0x33280` / `CBC_CORE_2X 0x3328c` / `VOTE_WRAP2 0x62010`；`AW_SYSST_FAULTS == 0xc86a`；`PLLS|CLKS == 0x11`；`PWDN|AMPPD|HMUTE == 0x103`；codec reset GPIO 43；TX core clock id `0x30c` |
| `prepare_cases` | 可用引擎返回 0 且 `config == (3<<24)|0x21`；逐条断言 `DMA_MODE=0`、`TX_PACK0=0x7f8fe`、`TX_PACK1=0xffefe`、`RX_PACK0/1` 同值、`BYTE_GRAN=0`、`M_IRQ_CLEAR=0xffffffff`、`M_IRQ_EN==WANTED`、`SE_IRQ_EN` 追加 `SE_M_IRQ_EN`；四个拒绝条件（proto≠I2C / `IF_DISABLE&1` / `CLK_CFG` 无 bit0 / `SCL_COUNTERS==0`）各自返回 -1 |
| `write_cases` | `phase=TxWait`、`TX_LEN=2`、`M_CMD0 == (OP_WRITE<<27)|(0x34<<9)`、`TX_WATERMARK=1`；忙时第二次 start 返回 -1；只收 `TX_WATERMARK` → Pending 且 FIFO 写 1 word `0x3421`（byte0 在 bits7:0）；再收 `CMD_DONE` → Done |
| `read_cases` | 首命令带 `STOP_STRETCH`、`TX_LEN=1`；写阶段 `CMD_DONE` → **Pending**（不是完成）且 `phase=ReadDone`、`RX_LEN=2`、`M_CMD0 == (OP_READ<<27)|(0x34<<9)` 无 stop；`RX_FIFO_STATUS=2` + `RX_FIFO=0x1321` → `bus.rx=0x1321`、`bus.data=0x21`；RX FIFO 空 → `ErrNoData` |
| `failure_cases` | `M_ERRORS` 位 → Failed + `ErrBus` + `error_status` 保留；TxWait 阶段直接 `CMD_DONE` → `ErrState`；Idle 收中断 → `stray++` 且 Pending；超时阶梯 Cancelling(写 CANCEL) → Aborting(写 ABORT) → Failed(`ErrTimeout`)；写 9 字节 / 写 0 字节 / 5 字节指针 / 读 5 字节全部 -1 |
| `poll_cases` | poll 读到 `TX_WATERMARK` 后写同值 `M_IRQ_CLEAR` 并推进到 `WriteDone` |
| `recovery_cases` | 卡死状态机拒绝新传输（`start` 返回 -1）；从 Cancelling 再走 2 步、从 TxWait 走 3 步即回到 Idle 并可再发传输——`PongAudioAmp.c` 的 `bus_recover()` 每次读寄存器前都走这段阶梯 |
| `plan_cases` | `pong_audio_pad_phys` 四个实测点（GPIO1 `0x0f101000`、GPIO3 `0x0f103000`、GPIO43 `0x0f12b000`、GPIO88 `0x0f158000`）与 0x1000 步进；pad 配置字（pull/function/drive/output 位域、高位保留、eGPIO→APPS 所有权、drive 向下取整不越界）；`pong_audio_cbcr_running` 的四种组合（含「HWCG 时 CLK_OFF 置位仍算在跑」）；GCC 三窗口路由（含窗口前后一字的边界）；DFS 档判定五例 |
| `chip_id_cases` | `pong_audio_amp_value(encode_amp_value(id)) == id` 对 9 个已知 ID 全成立；`pong_audio_amp_value(0x1321) == 0x2113`（AW88261），与 `PongAudioAmp.c` 的大端拼装一致；未知 ID 必须回落 `"unknown"` 而不是猜一个型号 |

踩坑记录：Windows 侧 `cc` 不存在（第一次跑直接 `command not found`）；测试里若只定义不使用的辅助函数，`-Werror` 会因 `-Wunused-function` 失败——本例把三处 `expect_eq` 改成 `expect` 后才通过。

为什么加 recovery（本轮）：一次无人应答的 cancel 会把状态机留在 `Cancelling`，之后每次 `start` 都被拒为 busy，
于是第二颗功放的日志会变成「三次读无应答」——把第一颗的超时栽给第二颗，正好是最难从日志里看出来的误判。
`bus_recover()` 只用公开 API（`pong_geni_busy` + `pong_geni_timeout`）走 2–3 步回 Idle，恢复次数打在
`amp probe done … recovered=N` 里，不隐藏也不 panic。

### 需要 Lead 合并的部分（本子任务写作用域之外）

1. **登记到序列**：在 `patches/xnu/series` 的 `0505-k60-audio-integration.patch` 之后追加一行 `../audio/0001-k60-audio-amp-probe.patch`，然后跑 `python3 scripts/sync-device-input.py`。依据（读代码所得，与 P-90 的表述不一致，落地前请核对行号）：`scripts/sync-device-input.py:131-138` 是**把 `patches/xnu/series` 写进** `scratch/SERIES-FINAL.txt`（方向是 repo → scratch），而 `scripts/porting-gate.py` 要求三份一致（repo series == SERIES-FINAL == `device/series`）；`patches/` 整棵树都在 `sync-device-input.py:35-47` 的镜像清单里，所以 `../audio/…` 这条相对路径成立；框架按 `path = series.parent / entry` 解析并 `git apply`（`/mnt/e/hackios/UniXNU/scripts/unixnu/patches.py:23,59`），`scripts/check-porting-paths.py` 用同样的相对解析做存在性检查。**这条链已用 `git apply` 实测**（0500→0502b→0501→0502→0503→0504→0505→本补丁，全部 rc=0、零 fuzz、零 reject，见 `patches/audio/README.md`）；
2. `board.toml` → `[kernel] kernel_args` 追加 `pong_audio_probe=1`——不加则补丁完全惰性（一次 boot-arg 查询后返回）；
3. `docs/INDEX.md` §3 按既有格式追加 `audio/CODEC.md`、`audio/SOUNDWIRE.md`、`audio/AMPS.md` 三行（`check-docs.py` 只强制顶层文件，但仓库惯例是登记）；
4. `docs/research/EIGHT-STEPS.toml` 的 `[hardware.audio]` 段**已经存在**（`:353-386`，`status = "parked"`、
   `parked_why = "PAS1 owner 缺失（电池与音频共用）；且 io_submap 仅 8 MiB 会 panic"`、①–⑥ `done = true`、
   ⑦⑧ `done = false`）→ **不要新增**，改为：`parked_why` 删掉、`status` 改 `"active"`，并把 ⑦ `verify` 补成
   `done = true` + `local_verified = true` + `static_check` / `unit_test` / `artifact_check` 三字段
   （`scripts/eight-step-gate.py:119-123` 要求三者都非空），⑧ 保持 `done = false`（未上机）。
   整段替换稿见下面片段 4。注：`eight-step-gate.py:91` 只对 `status == "active"` 的硬件做硬检查，所以这次改 `parked`→`active`
   会把音频线正式纳入 build/flash 门禁——⑦ 的三字段就是为此准备的。

### 合并申请的精确片段（照抄即可）

1）`docs/engineering/BOOT-ARGS.md` 的「一览」表加一行——**这是门禁硬要求**：`scripts/check-boot-args.py:47` 会扫 `drivers/**` 里所有 `PE_parse_boot_argn` 的 key，`PongAudioAmp.c` 新增了一个，缺行会让 hard-8（★8 boot-args）与 P-156 同时变红（实测输出：`❌ BOOT-ARGS.md 缺少 1 个参数: pong_audio_probe (drivers/)`）：

```markdown
| `pong_audio_probe` | 音频 / 功放 | 必须 == 1 | 未设 = 不探测 | 只读探测两颗 AW882xx（GENI I2C 读 chip id/状态）；只写 TLMM/GCC/GENI 自身，不写功放寄存器 |
```

长度核对：`porting-gate.py --quick` 的 `[A] length` 现在是 575/608，追加 ` pong_audio_probe=1` 共 19 字节 → 594，既 ≤ 600（porting-gate 门禁）也 ≤ 608（★8 硬上限），**不需要为它腾位置**。

2）`board.toml` → `[kernel] kernel_args` 加一个 token：

```toml
pong_audio_probe=1
```

3）`docs/INDEX.md` §3 加三行：

```markdown
| [`audio/CODEC.md`](research/audio/CODEC.md) | **音频 codec 侧**：WCD938x 同型判定、live FDT 逐条、供电 rail 表、DT 映射表 |
| [`audio/SOUNDWIRE.md`](research/audio/SOUNDWIRE.md) | **音频 SoundWire 侧**：宏与 SWR master 地址、寄存器表、PRM 前置、io_submap 预算 |
| [`audio/AMPS.md`](research/audio/AMPS.md) | **音频功放侧**：AW882xx 判定、GENI I2C 路径、只读探针方案 A1–A7 |
```

4）`docs/research/EIGHT-STEPS.toml:353-386` 整段替换（**不是新增**：该段已在，当前 `status = "parked"`）。
原来的 `parked_why` 行删掉，`status` 改 `"active"`，⑦ 补 `done/local_verified/static_check/unit_test/artifact_check`：

```toml
[hardware.audio]
status = "active"
name = "音频（WCD938x codec + SoundWire + AW882xx 功放）"

[hardware.audio.step.same_model]
done = true
evidence = "三平台同 WCD938x，SoundWire TX 枚举 ID 均为 0x000d01170223；功放同为 Awinic 家族（phk110 = AW88261 0x2113）。见 CODEC.md / AMPS.md"

[hardware.audio.step.official]
done = true
evidence = "主线 gcc-sm8450.c / geni-se.h / i2c-qcom-geni.c / clk-rcg2.c 逐条比对，寄存器与位域全部有出处（AMPS.md §3）"

[hardware.audio.step.decompile]
done = true
evidence = "live-fdt.dts（DTB sha256 95c02052…f29fdac8）解出宏/SWR/I2C/引脚/reset 的全部地址与中断；UEFI DTB 的音频节点被裁剪，取不到地址（CODEC.md §3、SOUNDWIRE.md §2）"

[hardware.audio.step.wide]
done = true
catalog_checked = true
catalog_result = "参考实现 pong-power（同 SM8475）与 phk110（WCD938x + AW88261）都没有 K60 的 vendor audio-kernel 源码；本机无 adsp.mbn、无 aw882xx_acf.bin"
evidence = "GAP-ANALYSIS.md / RESEARCH.md / EVIDENCE.md"

[hardware.audio.step.plan]
done = true
evidence = "先做纯 AP 只读验证（功放 chip id、供电、引脚回读），codec 侧等 ADSP PRM；AMPS.md §5 A1–A7"

[hardware.audio.step.deep]
done = true
evidence = "寄存器级细节：SWR 读事务、fs-gen 序列、PRM 三票、io_submap 8 MiB 预算（SOUNDWIRE.md §3–§5）"

[hardware.audio.step.verify]
done = true
local_verified = true
static_check = "PongAudioAmp.c / PongAudioGeniI2c.c 在真实 XNU bsd 构建目录 -fsyntax-only -Werror -DARM64_BOARD_CONFIG_PONG 全过（PASS: 两个文件）；并用 probe-pong.c 的 #if !defined(PONG) #error 证明该 flags 下 PONG 确实定义（守卫内代码非死代码）；check-docs.py exit 0"
unit_test = "drivers/PongAudio/tests/run-tests.sh → TESTS OK 147 cases（GENI 状态机 prepare/write/read/failure/poll/recovery + 寄存器表 + PongAudioPlan.h 全部判定函数，见 AMPS.md §6.1）"
artifact_check = "patches/audio/0001 三重自检：(a) 生成器自检 patch -p1 --dry-run 与 git apply --check 都过；(b) 真实链 patch -p1：0501→0505→本补丁 rc=0、无 reject（0505 在缺 0502 的短链上带 fuzz 1，与本补丁无关）；(c) 与框架同机制：在构建缓存 bsd/ 上按真实序列 0500→0502b→0501→0502→0503→0504→0505→本补丁 全部 git apply rc=0、零 fuzz、零 reject，落地 conf/files:117-120、bsd_init.c:1357-1358，四个新文件与 drivers/PongAudio/ cmp 逐字节相同（脚本 E:/k60-work/scratch/audio-work/gitchain-verify.sh，transcript 见 patches/audio/README.md）"

[hardware.audio.step.device]
done = false
evidence = "未上机。需要 Lead 先加 pong_audio_probe=1 并出镜像；本子任务不刷机（铁则 4/5）"

[hardware.audio.step.device.prediction]
success = "日志顺序为 amp probe start → gcc vote/clk → se15 ready → amp0/amp1 id=0x… → amp probe done found=2/2 failed=0 timeouts=0"
failure = "se15 no DFS level / I2C pads 未生效 / amp 三次读无应答：分别指向 GCC 投票、引脚复用、功放供电（DT 无供电属性，读不到 ID 优先怀疑没供电）"
```

### 门禁现状（对比 main f119a80 基线）

| 检查 | 本分支 | main 基线 | 归因 |
| --- | --- | --- | --- |
| `check-docs.py` | ✅ 187 项通过 | ✅ | — |
| `check-boot-args.py` | ❌ 缺 `pong_audio_probe` 一行 | ✅ | **本次引入**，补上片段 1 即绿 |
| `porting-gate.py --quick` `[X]` | ❌ `zzzz… 未同步 58532 vs 62104`、`series 三处一致 不一致` | ❌ 同样两条 | 环境漂移（他人 touch 补丁），非本次引入 |
| `eight-step-gate.py --build` | ❌ touch ④⑤⑥ 未 done | ❌ 同样三条 | 触摸线（他 agent），非本次引入 |
| `check-rules.py` | ❌ 5 条（= 上面 3 类之和） | ❌ 3 条 | 见上 |
| `sync-device-input.py --check` | ✅ | ✅ | — |

## 7. 待实测 / 阻塞

待实测（⑧）：
1. chip ID 到底是哪一颗（A5）。
2. I2C 引脚是否已被 Android 配好（A7 读回即可知，若已配好就不要重配）。
3. 功放供电是否已使能（DT 无供电属性，只能读回判断；**读不到 ID 时优先怀疑没供电**）。

阻塞（不属于本子任务）：
- 播放通路（TDM/MI2S → 功放）需要 LPASS 音频前端与 ADSP 图 → Lead 的 PAS1 + AudioReach。
- 功放的 `aw882xx_acf.bin` 配置档（Android `/vendor/etc/aw882xx_acf.bin`）本机没有，
  phk110 的驱动缺它就无法做 Music profile 初始化（`hakios.sound.c:1403-1405` 报错文本可证）。
  → 需要 Lead 从 K60 的 vendor 分区取；否则只能走「软复位 + 最小寄存器」路线。
