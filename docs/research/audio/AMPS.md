# 扬声器功放 — K60 (SM8475 / cape) 判定、纯 AP 只读路径与寄存器回放层

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
- GPLL0：`enable_reg 0x62018` BIT(0)；PLL_MODE 在 `+0x0`，lock 位 BIT(31)（`gcc-sm8450.c:50-55`、
  `clk-alpha-pll.c:17` `PLL_MODE(p) = p->offset + 0x0`、`:34` `PLL_LOCK_DET BIT(31)`）。
  SE15 的父源是 `gcc_parent_map_0`（`gcc-sm8450.c:184-194`）= BI_TCXO / GPLL0_OUT_MAIN / GPLL0_OUT_EVEN，
  所以「GPLL0 没锁就投票分支」确实可能让总线挂死——这不是形式主义，见 §3.2。

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
> Pong 自己也没有投 GPLL0——它在 `:130` 之前就假定 GPLL0 已被更早的启动路径打开，**这一点不能照抄**（见 §3.2）。

### 3.2 HR-02 合规：访问 GENI 前的完整前置序列

`docs/ops/HARD-RULES.md:76-116` 的 HR-02（铁则 2）规定：碰 GENI 控制器前必须按序完成
「GPLL0 投票 + 等 lock → QUP 分支投票 → 等分支时钟离 off（判据含 HWCG）→ 配 TLMM 引脚 →
映射 SE/wrapper 两个窗 → 检查 IF_DISABLE」。违反的后果是整机死、零控制台输出；
2026-11-09 已经因音频 I2C 0x880000 发生过一次同型事故。

本分支的实现逐条对应（`drivers/PongAudio/PongAudioAmp.c`）：

| HR-02 步骤 | 本分支位置 | 依据 |
|---|---|---|
| 1. GPLL0 投票 + 等 lock | `gcc_gpll0_on()`：先读 `0x62018`，未置 BIT(0) 则写回，然后轮询 `PLL_MODE` 的 BIT(31) 最多 1000×10 µs；失败则 `amp probe stop: GPLL0 not locked` 并返回 | `gcc-sm8450.c:50-62`（enable_reg 0x62018 / enable_mask BIT(0) / offset 0x0 / LUCID_EVO）、`clk-alpha-pll.c:17,34`（PLL_MODE = offset+0x0、PLL_LOCK_DET = BIT(31)）、touch 补丁 `:212-217,:289-294` 的同一写法 |
| 2. QUP 分支投票 | `gcc_wrapper2_on()` 写 `0x62010 |= 0x1f` 并回读打印 | `gcc-sm8450.c:2391-2422,2603-2625`（wrapper2 五个 branch 的 enable_reg 都是 0x62010） |
| 3. 等分支离 off（含 HWCG） | 逐个 CBCR 轮询 `pong_audio_cbcr_running()` = `!(v & CLK_OFF) || (v & HWCG)`，最多 100×100 µs | `clk-branch.c:50-59` `BRANCH_HALT_VOTED`；HWCG 时 CBCR 会报 CLK_OFF，只判 CLK_OFF==0 是假阴性 |
| 4. 配 TLMM 引脚 | `i2c_pads_take()`（GPIO56/57 → function 1 / pull-up / 2 mA，已是 fn1 就不写）在 `se15_open()` **之前**调用 | `live-fdt.dts:3562-3593`（qup15 组）、`pinctrl-sm8450.c:1472-1473`（`[56] = PINGROUP(56, qup15, ibi_i3c, …)`） |
| 5. 映射 SE + wrapper | `pads_map()` 最先，`gcc_map()` 四页，`se15_open()` 里 `ml_io_map(0x880000, 0x4000)` | `live-fdt.dts:13301-13342`、`osfmk/arm/io_map.c:66,88-142`（8 MiB io_submap，按 16 KiB 页记账） |
| 6. IF_DISABLE / FIFO 模式 | `se15_open()` 读 `0x68` 校验 proto==3，`pong_geni_prepare()` 校验 `IF_DISABLE&1`、`CLK_CFG` bit0、`SCL_COUNTERS != 0`，任一不满足返回 -1（不硬闯） | 主线 `qcom-geni-se.c:316-352`、`geni-se.h:78-122` |

顺序在代码里是硬的：`pong_audio_amp_probe()` 依次 `pads_map → gcc_map → gcc_gpll0_on → gcc_wrapper2_on →
i2c_pads_take → se15_open`，任何一步 false 就 `return -1`，**不会带着未锁的 PLL 去碰分支，也不会在总线不可用时释放功放 reset**。
`bus_recover()`（`bcb8279` 引入）只做状态机阶梯（`pong_geni_timeout` × ≤3 回 Idle），不碰任何 GCC 寄存器，
因此不会绕开上述序列。

GPLL0 的 lock 位与 enable 位**不在同一页**（`0x62018` 在 vote 窗口、`PLL_MODE` 在 GCC+0x0），所以 GCC 映射从三页扩成四页：
`PongAudioRegs.h` 新增 `PONG_AUDIO_GCC_PLL_WIN 0x0`、`PONG_AUDIO_GCC_PLL0_ENABLE 0x62018`、
`PONG_AUDIO_GCC_PLL0_MODE 0x0`、`PONG_AUDIO_GCC_PLL0_VOTE (1u<<0)`、`PONG_AUDIO_GCC_PLL_LOCK_DET (1u<<31)`；
`pong_audio_gcc_window()` 由 0/1/2 扩成 0/1/2/**3**（3 = PLL 窗口），四页合计 64 KiB。

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
| A1 | 映射 GCC 0x100000 的四页（GCC+0x0 PLL_MODE、+0x2e000 RCG、+0x33000 CBCR、+0x62000 vote），**先投 GPLL0 并等 lock，再投 wrapper2 五个 bit**（HR-02 顺序，见 §3.2） | `PongAudio: amp gcc gpll0 … locked=1` 后回读 0x62010 的 bit0..4 全为 1 |
| A2 | 映射 TLMM GPIO56/57 页（`0xf000000 + 0x100000 + 0x1000*n`），配 function 1 / 2 mA / pull-up | 回读 config `[5:2] == 1` |
| A3 | 映射 GENI SE15 0x880000 一页，读 `GENI_FW_REVISION_RO(0x68)` | `(v >> 8) & 0xff == 3`（I2C） |
| A4 | 按 §3.1 形状初始化 GENI（换掉四处索引），选 DFS 档 | `SE_GENI_STATUS(0x40)` 无 error 位 |
| A5 | 对 0x34 / 0x35 各发一次「写 1 字节 reg=0x00 + 读 2 字节」 | 得到 chip ID；0x2113 → AW88261（run 1 实测两颗都是 `0x2113`；选型结论见 §8） |
| A6 | 只读 fuse 0x78/0x79/0x7c/0x7d 与 0x01/0x04/0x06 | 打印原始值，**不解释、不写** |
| A7 | 打印 GPIO1/3/43/52/88/63 的 config/IO 原始值 | 记录 Android 退出时的引脚状态 |

失败即停（不重试、不写任何功放寄存器）。**A5 的结果直接决定「移植哪份驱动」这个硬问题** —— 已由 run 1 与 ACF 解析回答，见 §8。

## 6. 已交付代码

`drivers/PongAudio/` 与 `drivers/PongPower/`（源文件与说明，均 BSD-2-Clause-Patent）：

| 文件 | 内容 |
| --- | --- |
| `PongAudioRegs.h` | 上面全部地址/偏移/位定义，每条带来源标注（L = `live-fdt.dts`、G = `gcc-sm8450.c`、S = Pong 参考树、M = 主线 `geni-se.h`/`i2c-qcom-geni.c`、H = `hakios.speaker.c`） |
| `PongAudioPlan.h` | 探针的判定逻辑做成纯函数：pad 地址与 pad 配置字、CBCR「是否在跑」判据、GCC 四窗口路由（含 GPLL0 的 PLL 窗口）、DFS 档可用性、AW882xx 字节序与 chip id 表。无 MMIO、无内核头 → 这些判定由宿主单测钉住，而不是靠上机试 |
| `PongAudioAcf.h` | A5 的落点：AW88261 配置档（ACF）的读取与校验做成纯函数 —— 头判据、按 `dev_index + profile + kind` 定位块、两种和校验、16×16 寄存器对表、双 PA 通道映射、fuse → icalk/vcalk → vcalb。无 MMIO、无内核头，见 §8.8 |
| `PongAudioGeniI2c.h` / `.c` | Pong `GeniI2c.c` 的移植，符号改 `pong_geni_*` 避免与 Pong 副本冲突，状态机逻辑逐字保留 |
| `PongAudioAmp.c` | A1–A7 的实现：8 页 TLMM 回读 → GCC wrapper2 投票 → I2C 引脚 → SE15 引擎 → 放 reset → 只读 13 个寄存器；然后对每颗应答的功放跑一遍**回放层**（软复位 + 57 对 Music profile + fuse 算的 vcalb + 静音音量，见 §9）；每次传输前 `bus_recover()` 把可能卡死的状态机走回 Idle；boot-arg `pong_audio_probe=1` 才跑，失败只报数不 panic |
| `PongAudioRing.h` | PCM 环几何与 SPSC 队列：48 kHz 立体声 S24_LE、1024 帧周期（8192 B）、2 周期、256 帧启动阈值、14400 帧（300 ms）lead、65536 帧环；`pong_ring_queue_*` 提供无锁单生产者/单消费者入环出环，`pong_audio_submit()` 写、`pong_audio_ring_read()` 读。无 MMIO；0001 以 `bsd/dev/PongAudioRing.h` 放进补丁，0003 include。 |
| `PongAudioPlayback.h` | 播放图 12 步顺序：open/config speaker、open/config playback、config shmem、map、clock、prepare speaker/playback、一条成对的 start（SG 列表 count=2，0x4005 + 0x4001）、start speaker、start playback；token `0x00030000 + step`，opcode 固定（GRAPH_OPEN 0x01001000 / GRAPH_PREPARE 0x01001001 / GRAPH_START 0x01001002 / SET_CFG 0x01001006 / MEM_MAP 0x0100100C / PRM_REQUEST 0x0100100F），SG speaker 0x4005 / play 0x4001。0003 的 `pong_audio_play_send_step()` 用它组包，宿主 `play_cases()` 的 32 条断言钉住整张表。纯常量与判定，无 MMIO。 |
| `PongAudioServiceAbi.h` | K60 音频服务 ABI（`drivers/PongPower/`）：`PongAudio` service class、magic `0x53484155`、version 3、48 kHz 立体声 S24_LE（8 B/帧）、1024 帧周期、65536 帧环、14400 帧 lead；control page 88 B，含 `out_seq`/`ticks_per_frame_q32`/`out_anchor_host`/`out_frames` 供 19.2 MHz 时基握手，memory type control=0/output=1、selectors StartOutput=0/StopOutput=1/SetHostClock=4、state bits output running=1/ready=2；`out_write`/`out_read` 是 64-bit 单调帧计数。 |
| `PongAudioService.cpp` | `PongAudio : IOService` + `PongAudioUserClient`（`drivers/PongPower/`）：4 KiB control + 512 KiB out ring 由 `IOBufferMemoryDescriptor` 在内核/用户间共享，`clientMemoryForType` 映射，`externalMethod` 接受 StartOutput/StopOutput/SetHostClock（selector 4 要求 1 个 scalar input，按参考实现解析 AudioGetHostClockFrequency 并把 24 MHz 常量修正为实际 19.2 MHz 时基）；`IOTimerEventSource` 以 21333 µs 周期从 ring 取 8192 B 调 `pong_audio_submit()`，startOutput/stopOutput 用 `out_seq` 奇数/偶数发布 `ticks_per_frame_q32`/`out_anchor_host`/`out_frames`；`pong_audio_status() != PongAudioOk` 时 StartOutput 返回 `kIOReturnNotReady`。 |
| `userland/PongAudioPlugIn.c` | 输出-only AudioServerPlugIn（`userland/`）：`IOServiceGetMatchingService("PongAudio")` + `IOServiceOpen` + `IOConnectMapMemory64` 映射 control/out ring，`DoIOOperation` 把 Float32 转 S24/Q31 写 ring 并发布 `out_write`；`StartIO`/`StopIO` 走 `PongAudioUserClient` selector，`setHostClock()` 用 `dlsym(AudioGetHostClockFrequency)` 解析常量并调 selector 4，`StartIO` 读 `out_anchor_host` 算 `gZeroOrigin`，`GetZeroTimeStamp` 用 `out_seq` seqlock 生成 48 kHz 帧时钟；boot-arg `pong_audio=1` 时插件还会起一个 detached selftest 线程，最多等 30 s 连接服务、重试 StartIO，写 200×1024 帧 440 Hz 正弦并每 40 周期打印 `PongAudio HAL: selftest period=...`，用于没有 CoreAudio 播放流时验证 service timer、PCM submit 和低 DMA。`userland/build.py audio` 生成 `PongAudio.driver`。 |
| `README.md` | 逐步骤做了什么、为什么是这个顺序、期望日志形状、上机命令、八步自评 |

补丁：`patches/audio/0001-k60-audio-amp-probe.patch`（131,989 B，3,493 行，15 段，sha256 `d4ed7ab76c5c4960ad4e12629f748b77502333e83a1d956955546c3bc614e866`（前 8 位 `d4ed7ab7`））+ `patches/audio/0003-k60-audio-afe-selftest.patch`（49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`）+ `patches/audio/series`。

`patches/xnu/0617-k60-audio-hal-deploy.patch`（8,882 B，285 行，sha256 `7e9a8172d33c6029c3c7025395ca4ec91c27db146fd1092ba3119c38664c5728`）把 `PongAudio.driver` 以 `K60A` 容器带进内核：`bsd/dev/k60_audio_hal.c` 在 exec 阶段把 bundle 写进 `/private/var/pong/empty-hal`，随后 `k60_audio_hal_mount()` 用内核 bindfs（`native_bindfs_boot_mount` + `MNT_RDONLY|MNT_UNION`）把该目录挂到 `/System/Library/Audio/Plug-Ins/HAL`；`init` 的 bindfs 在 AMFI 之前一律被 EPERM 拒绝，所以挂载改由内核在 Data mount 之后完成。`scripts/gen-k60-audio-hal-blob.py` 生成 blob、`scripts/check-k60-audio-hal-blob.py` 校验，`build-strict` 在 `CONFIG_XNU_K60_AUDIO_HAL=y` 时先编译 bundle 并记录 manifest `audio_hal`。

- 13 个文件**逐字**放进 `bsd/dev/`：应用后已用 `cmp` 证明与 `drivers/PongAudio/`、`drivers/PongPower/` 完全一致；
- `bsd/conf/files` 加两条对象（`bsd/dev/PongAudioGeniI2c.c standard`、`bsd/dev/PongAudioAmp.c standard`）；
- `bsd/kern/bsd_init.c` 加一段调用，锚在 0505 的 `pong_audio_bootstrap()` 之后。
- **顺序要求**：必须在 `patches/xnu/0501` 与 `0505` 之后，因为两处锚点分别由 0501（`bsd/dev/qbt/btqca.c`）和 0505（`pong_audio_bootstrap()`）建立；而 0501 又依赖 0300/0243/0340 已加进 `bsd/conf/files` 的 `k60_usblog` / `k60_uilib` / `k60_console_export` 三行。**已用真实链验证**（不是合成预映像）：在构建缓存 `.../tree/.cache/xnu-work` 的 `bsd/conf/files`+`bsd/kern/bsd_init.c` 上按 0501 → 0505 → 本补丁顺序 `patch -p1 --forward` 落地，**rc=0、无 reject**。本补丁**无 fuzz**，只有行偏移（conf/files +6、bsd_init.c +15）；链条中唯一带 fuzz 的是 0505 自身（`Hunk #1 succeeded at 1329 with fuzz 1 (offset -19 lines)`，它的锚点与该前映像有 1 行差异，与本补丁无关）。十三个新文件与 `drivers/PongAudio/`、`drivers/PongPower/` 逐字节相同（`PongCodecPlan.h` 仍不在其中：内核侧还没有 `.c` include 它；`PongAudioAcf.h`/`PongAudioAmpProfile.h`/`PongAudioAmpReplay.h`/`PongAudioAfe.h`/`K60PmicGlinkAudio.h` **在**，被 `PongAudioAmp.c`/`pong_audio.c` include，见 §9）。完整 transcript 见 `patches/audio/README.md`。
- 编译核验：`PongAudioGeniI2c.c` 曾在真实 XNU bsd 构建目录里用 `-fsyntax-only` + `-DARM64_BOARD_CONFIG_PONG` + `-Werror` 过（`PASS: PongAudioGeniI2c.c`）。回放层加入后这轮**没有复现**同一核验：fakeroot 的 `usr/include` 没有 `stdint.h`，而 `mach/arm/vm_types.h:75` 要 include 它，四种 flags 变体都在 `uintptr_t` 上失败——与本次改动无关，是 flag 集合缺 include 路径。替代证据：(a) **镜像 k 的内核构建**证明 8 文件补丁（含回放层）在真实 kernel flags 下编译通过（`audio-probe-20261114k`，`kernel.log:228-231` 的 `0503 → 0504 → 0505 → 0001-k60-audio-amp-probe` 顺序，`kernel.macho` sha256 `0640f6c7…`，见 §9.5）；(b) 回放层与编码器全部语义在宿主侧被 956/974 例单测钉住（§9.3）。不再声称 `PASS: PongAudioAmp.c`。

### 6.1 宿主单测（八步 ⑦ 的本地核验，956 例；带真实 ACF 时 974 例）

`drivers/PongAudio/tests/` **不进内核、也不进补丁**：它只编译 `PongAudioGeniI2c.c`（纯状态机，无 XNU 头依赖），
用假 MMIO 喂 `M_IRQ_STATUS` 序列，把「读事务必须两段（写指针持 stop → 读数据）」这类只靠上机才会暴露的错误变成可重复的本地检查。
`PongAudioAmp.c` 依赖内核头，不能宿主编译；所以它的**判定逻辑**被抽到 `PongAudioPlan.h`，**写寄存器的语义**被抽到 `PongAudioAcf.h` / `PongAudioAmpProfile.h` / `PongAudioAmpReplay.h`（三者均纯函数、无 MMIO，见 §8.8 与 §9），由单测逐条钉住，留在 `.c` 里的只剩 MMIO 时序与打印——那部分只能靠上机说话。

codec 半（LPASS 宏 / SoundWire / WCD938x）走同一条路：`PongCodecPlan.h` 把「硬件可达之前就能定下来的决策」
写成纯函数——控制器版本判定、两套读事务寄存器组、事务号与命令字、FIFO 满判定、回包匹配、枚举位图与
slave-id 布局、LPI pad 配置字、五个窗口及其 io_submap 页数、以及「两票 PRM + `0x30c` 时钟都到位才许碰 LPASS」
这一条门。它们全是算术，不碰寄存器，所以现在就能钉死；等 Lead 的 PAS1/PRM 起来，上机代码只是套一层薄循环。
`PongCodecSwr.h` / `PongCodecSwr.c` 把那份决策变成**顺序**：读 `COMP_HW_VERSION` 定版本与寄存器组、
FIFO 满时拒绝（不写命令，避免「丢掉的命令」被误读成「从设备没应答」）、只在事务号属于自己时才收
回包（否则 `0x308 <- 1` 中止而不是拿同一个号重试）、超时中止并计数、枚举使能并锁存位图。
形状与 GENI 状态机一致：**里面不等待、不空转**，超时由调用方（知道启动预算）决定。

`PongCodecLpi.h` / `PongCodecLpi.c` 再把「LPI 引脚与 slew 的写入顺序」变成可测的顺序：四个 pad
（pin 0/1/2/14）逐个读改写，**全部写完之后**才写一次 slew 寄存器（S:`PongWcd938.h:80-82` 就是这个顺序）。
pad 与 slew 是两个不同的映射（`0x03440000` 与 `0x034da000`），所以回调也分成两对——否则一次 slew 写会落到 pad 0 上。
同样是五步状态机，里面不等待。

`PongCodecMacro.h` / `PongCodecMacro.c` 把 §6 的 VA/TX 宏时钟门写成**一张九行的表**：每行是「哪个宏、哪个寄存器、
 * 清哪些位、置哪些位」，走表执行。做成表而不是九行代码，是因为这九个寄存器都是读-改-写，而 K60 的复位值
 本机从没观测过（SOUNDWIRE.md §6 就是这么写的）——表让首次上机能把每一步读到的原值和写回值都打进日志，
 于是「复位值是否与参考假设一致」变成一个可回答的问题，而不是被隐藏。每步都重新读，因为第二步写的就是第一步
 写过的那个寄存器，不是「拼一个值写三次」。

`PongCodecProbe.h` / `PongCodecProbe.c` 是 codec 半的总编排器：把「LPI pad/slew → VA/TX 宏时钟门 →
控制器探测与初始化 → 枚举 → slave id → codec identity」这整条顺序串起来，自己拥有顺序、轮询预算与
「什么时候算失败」。`pong_codec_probe_start()` 在 `pong_codec_may_touch_lpass()` 的三票（macro/dcodec/0x30c）
不全时直接拒绝、**一个寄存器都不碰**；`pong_codec_probe_step()` 一步只做一个动作（一个 pad 的读改写、
一个宏门、一次寄存器访问或一次轮询），所以调用方可以把它放进任何不阻塞的循环，也能在上机时逐步打日志。
slave id 是两次普通寄存器读（`0x530+8n` / `0x534+8n`，S:`PongWcd938.h:108-109`），只有 codec 自己的
`0x50/0x51` 才走读事务——这一点被单测抓住过一次（最初把 slave id 也当成了读事务）。
`PongCodecPlan.h`、`PongCodecSwr.*`、`PongCodecLpi.*`、`PongCodecMacro.*` 与 `PongCodecProbe.*` **都不进补丁**：内核侧还没有任何 `.c` include 它们（只有宿主测试用），
补丁只装内核真正编译的文件。等 PAS1 起来、有 `.c` 调用它们时再一起入补丁。

`PongAudioAfe.h` 不在「不进补丁」之列：它虽是 TDM 扬声器通路的 AFE 参数离线编码器（GPR 24 字节头、svc/port 两种 set-param 信封、五个参数结构、DEVICE_START，编码规则见 `TDMS.md` §3），但 `pong_audio.c` 已 include 它并调用 76 字节 PRM 时钟编码器，所以它随 0001 进内核、由 0003 的自检与六步状态机调用；`pong_afe_step_packet()` 也已把六步完整包（76/96/56/88/80/28 B）交给 GLINK 发送路径，宿主 `afe_plan_cases()` 的 61 条断言钉住每个字节。

```
# Windows 侧没有 cc/gcc/clang（PATH 里只有 winuxcmd），必须在 WSL 里跑：
wsl.exe -e bash -lc 'cd /mnt/e/hackios/k60-audio-merge && sh drivers/PongAudio/tests/run-tests.sh'
# → TESTS OK 956 cases   (cc -std=gnu11 -Wall -Wextra -Werror)
# 带上真实 ACF（它不入库）：PONG_ACF_FILE=<aw882xx_acf.bin> sh drivers/PongAudio/tests/run-tests.sh
# → TESTS OK 974 cases
```

覆盖范围：

| 组 | 断言内容 |
| --- | --- |
| `register_map_cases` | `TLMM_PHYS+GPIO_OFF == 0x0f100000`；GPIO88 寄存器地址 `0x0f158000` 落在 `pinctrl@f000000` 的 `0x1000000` 窗口内；GCC 四个 1 页窗口分别覆盖 `RCG_SE15 0x2e014` / `CBC_CORE 0x33280` / `CBC_CORE_2X 0x3328c` / `VOTE_WRAP2 0x62010`；`AW_SYSST_FAULTS == 0xc86a`；`PLLS|CLKS == 0x11`；`PWDN|AMPPD|HMUTE == 0x103`；codec reset GPIO 43；TX core clock id `0x30c` |
| `prepare_cases` | 可用引擎返回 0 且 `config == (3<<24)|0x21`；逐条断言 `DMA_MODE=0`、`TX_PACK0=0x7f8fe`、`TX_PACK1=0xffefe`、`RX_PACK0/1` 同值、`BYTE_GRAN=0`、`M_IRQ_CLEAR=0xffffffff`、`M_IRQ_EN==WANTED`、`SE_IRQ_EN` 追加 `SE_M_IRQ_EN`；四个拒绝条件（proto≠I2C / `IF_DISABLE&1` / `CLK_CFG` 无 bit0 / `SCL_COUNTERS==0`）各自返回 -1 |
| `write_cases` | `phase=TxWait`、`TX_LEN=2`、`M_CMD0 == (OP_WRITE<<27)|(0x34<<9)`、`TX_WATERMARK=1`；忙时第二次 start 返回 -1；只收 `TX_WATERMARK` → Pending 且 FIFO 写 1 word `0x3421`（byte0 在 bits7:0）；再收 `CMD_DONE` → Done |
| `read_cases` | 首命令带 `STOP_STRETCH`、`TX_LEN=1`；写阶段 `CMD_DONE` → **Pending**（不是完成）且 `phase=ReadDone`、`RX_LEN=2`、`M_CMD0 == (OP_READ<<27)|(0x34<<9)` 无 stop；`RX_FIFO_STATUS=2` + `RX_FIFO=0x1321` → `bus.rx=0x1321`、`bus.data=0x21`；RX FIFO 空 → `ErrNoData` |
| `failure_cases` | `M_ERRORS` 位 → Failed + `ErrBus` + `error_status` 保留；TxWait 阶段直接 `CMD_DONE` → `ErrState`；Idle 收中断 → `stray++` 且 Pending；超时阶梯 Cancelling(写 CANCEL) → Aborting(写 ABORT) → Failed(`ErrTimeout`)；写 9 字节 / 写 0 字节 / 5 字节指针 / 读 5 字节全部 -1 |
| `poll_cases` | poll 读到 `TX_WATERMARK` 后写同值 `M_IRQ_CLEAR` 并推进到 `WriteDone` |
| `recovery_cases` | 卡死状态机拒绝新传输（`start` 返回 -1）；从 Cancelling 再走 2 步、从 TxWait 走 3 步即回到 Idle 并可再发传输——`PongAudioAmp.c` 的 `bus_recover()` 每次读寄存器前都走这段阶梯 |
| `plan_cases` | `pong_audio_pad_phys` 四个实测点（GPIO1 `0x0f101000`、GPIO3 `0x0f103000`、GPIO43 `0x0f12b000`、GPIO88 `0x0f158000`）与 0x1000 步进；pad 配置字（pull/function/drive/output 位域、高位保留、eGPIO→APPS 所有权、drive 向下取整不越界）；`pong_audio_cbcr_running` 的四种组合（含「HWCG 时 CLK_OFF 置位仍算在跑」）；GCC 四窗口路由（含窗口前后一字的边界、`0x62018` 必须落 vote 窗口而 `PLL_MODE` 落 PLL 窗口）；GPLL0 五个常量值；DFS 档判定五例 |
| `codec_cases` | SoundWire 版本判定（`0x01070000` → V1.7、高字节 2 → V2、其余 Unknown）；两套读事务寄存器组（V17 `0x320/0x328/0x334`、V2 `0x5024/0x5050/0x5040`）；事务号 `((issued+1)%14)+1`（首个是 2）与命令字 `1<<24 | device<<20 | txn<<16 | reg`；FIFO 满阈值 8；回包事务号匹配与数据取低 8 位；V17 中断掩码 `0xffffffff/0x1dfdfd`；枚举位图每 slave 2 bit 与 `0x530+8n` 的 id 寄存器、`0x000d01170223` 的 WCD938x 判定；LPI 四个 pin 与 pad 配置字；五个 LPASS 窗口（4 KiB 对齐、落在 `0x03100000..0x03600000`）与 **10 页 / 160 KiB** 的 io_submap 账；以及 `pong_codec_may_touch_lpass()` 的三票合取 |
| `swr_cases` | 假 128 KiB 寄存器窗（v2 的寄存器在 0x5000 以上，窗口必须够大）驱动的初始化序列与整条读事务：两版本共有的 `0x008/0x101c/0x500/0x1048/0x018`、v1.7 的 `0x314/0x1044/0x208/0x210` 与执行环境 1→2→3、v2 的 `0x5060/0x5008/0x5004` 与等 `0x5064` bit0 就绪、v1.7 与 v2 各自的寄存器组、未知版本拒绝且**不写任何寄存器**、FIFO 满时拒绝且**不写命令**、命令字 `1<<24|1<<20|1<<16|0x3000`、忙时第二次 start 被拒、空回包队列 → Pending、匹配回包 → Done 且 `data=0x5a`、外来事务号 → Failed + 写 `0x308<-1` + `aborts=1`、超时 → Failed + `timeouts=1` + 中止、枚举使能先写 `0x500<-1` 再锁存位图（slave1/2 在、slave3 不在）、事务号走 2..14、1 后回到 2 且 `reads` 计数正确 |
| `lpi_cases` | 两个映射分开的假窗（pad 块 16 页 + slew 块一个寄存器，slew 写落到 pad 0 会立刻显形）：slew 每 pin 2 bit 从 bit 0 起（pin 14 在 bit 6）、电平 1 = 清掉该对的两位后置低位（`0xaaaaaaaa` 的四个字段全变 `0x55`，高位保留）；四个 pad 是 0/1/2/14 而不是 0..3；五步顺序严格为 pin0→pin1→pin2→pin14→slew，且只写 5 次（4 pad + 1 slew）；pad 值 = `(old&~0x3f)|4|(i?2:0)`（pin 1 的原有高位保留）；`done()` 在第五步后才 true，完成后重复 step 不再写；slew 已是电平 1 时保持不变；无回调时不动寄存器也不崩 |
| `macro_cases` | 九步表的形状与内容（步数 9、越界与空指针被拒、step 0 是 VA `0x00` 置 bit0、step 7 是第一笔 TX 写）；`(old&~clear)|set` 四种组合（含「同一位既清又置，最终为置」）；假的两块宏窗各从非零复位值起跑，九步后 VA `0x00/0x04/0x80/0x08` 与 TX `0x00/0x04` 的最终值逐条对上；每步都记下读到的旧值与写回的新值（`old[0]` 是复位值、`old[1]` 是 step 0 写完之后的值）；完成后重复 step 不再写；无回调或空序列器不动寄存器也不崩 |
| `probe_cases` | 假的 pad/slew 窗 + 两块宏窗 + 128 KiB 控制器窗组成的 `FakeCodec` 驱动整条顺序：LPASS 三票不全 → 拒启动且**零写入**；回调不全 → 拒启动；v1.7 快乐路径（pad 全部先于宏、宏全部先于控制器；pad0 从 `0xffffffff` 得 `0xffffffc4`、其余 pad 得 `0x6`、slew `0x55`、VA/TX `0x00` 置 bit0、只有 identity 两个字节计 `reads`、`found_slave=1`、identity `0x1234`）；空位图 → `ErrNotFound`；位图上有别的 slave 但 id 不匹配 → `ErrNotFound`；控制器完全不应答 → `ErrTimeout` 且真的写了 `0x308<-1`；未知控制器版本 → `ErrSwr`；v2 快乐路径（等 `0x5064` bit0 后才枚举、identity `0x5678`）；v2 环境起不来 → `ErrTimeout`；走到 Done 后继续 step 不再写任何寄存器 |
| `chip_id_cases` | `pong_audio_amp_value(encode_amp_value(id)) == id` 对 9 个已知 ID 全成立；`pong_audio_amp_value(0x1321) == 0x2113`（AW88261），与 `PongAudioAmp.c` 的大端拼装一致；未知 ID 必须回落 `"unknown"` 而不是猜一个型号 |
| `acf_cases` | 合成 blob 的六种 header 拒绝（magic / entries 为 0 / 步长不整除 / 步长 < 0x30 / 表越界 / 过短）与接受；`find` 按 `dev_index + profile + kind` 三元组命中（同名不同 dev、kind 参与键、空 buffer）；翻一个字节即校验失败、`data_length` 越界被拒；8 位表头被拒、`count*4+4 != data_length` 被拒；`pair_at` 越界；channel 映射 `0x35→0`、`0x34→1`、其余 `0xff`；`ef_or` 三种 DBGCTRL；**amp0 vcalb `0x2052` / amp1 vcalb `0x2094`**、OR 与 AND 两条路径给出不同结果、10 位有符号值域两端（488 / 1511）；以及 `PONG_ACF_FILE` 存在时对**真实 blob** 的 13 条断言（十条目、步长 64、dev0/dev1 Music 各 57 对且校验通过、monitor 通过） |

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
   （`scripts/eight-step-gate.py:119-123` 要求三者都非空），⑧ 保持 `done = false`（未上机），但要补
   `[hardware.audio.step.device.prediction]` 的 `success` / `failure` 两行（`flash` 模式硬要求，见 `scripts/eight-step-gate.py:135-141`）——`feat/audio-merge` 已补，实测 `--flash` → `通过 48 项检查`、exit 0。
   整段替换稿见下面片段 4。注：`eight-step-gate.py:91` 只对 `status == "active"` 的硬件做硬检查，所以这次改 `parked`→`active`
   会把音频线正式纳入 build/flash 门禁——⑦ 的三字段就是为此准备的。

### 合并申请的精确片段（照抄即可）

1）`docs/engineering/BOOT-ARGS.md` 的「一览」表加一行——**这是门禁硬要求**：`scripts/check-boot-args.py:47` 会扫 `drivers/**` 里所有 `PE_parse_boot_argn` 的 key，`PongAudioAmp.c` 新增了一个，缺行会让 hard-8（★8 boot-args）与 P-156 同时变红（实测输出：`❌ BOOT-ARGS.md 缺少 1 个参数: pong_audio_probe (drivers/)`）：

```markdown
| `pong_audio_probe` | 音频 / 功放 | 必须 == 1 | 未设 = 不探测 | 探测两颗 AW882xx：先只读（GENI I2C 读 chip id/状态），再回放 Music profile（写寄存器，功放保持掉电+静音，见 AMPS §9）；另写 TLMM/GCC/GENI 自身 |
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
| [`audio/AMPS.md`](research/audio/AMPS.md) | **音频功放侧**：AW882xx 判定、GENI I2C 路径、探针方案 A1–A7、上机 run 1、A5 选型与 ACF 配置档（§8）、回放层（§9） |
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
catalog_result = "参考实现 pong-power（同 SM8475）与 phk110（WCD938x + AW88261）都没有 K60 的 vendor audio-kernel 源码；adsp.mbn 不在本机（可从手机 /vendor/firmware_mnt/image/adsp.b00-b18 取），aw882xx_acf.bin 已从手机 /vendor/firmware/ 只读取到并解析，见 §8.3"
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
unit_test = "drivers/PongAudio/tests/run-tests.sh → TESTS OK 584 cases（带真实 ACF 时 602 cases）（GENI 状态机 prepare/write/read/failure/poll/recovery + 寄存器表 + PongAudioPlan.h 全部判定函数 + PongAudioAcf.h 的 ACF 读取与校验 + PongAudioAmpProfile.h/PongAudioAmpReplay.h 的回放语义 + PongCodecPlan.h 的 SoundWire/WCD938x/LPI/slew 决策 + PongCodecSwr.c 的初始化序列与读事务状态机 + PongCodecLpi.c 的五步 pad/slew 顺序 + PongCodecMacro.c 的 VA/TX 宏九步时钟门表 + PongCodecProbe.c 的整条 codec 启动编排，见 AMPS.md §6.1 与 §9.3）"
artifact_check = "patches/audio/0001 三重自检：(a) 生成器自检 patch -p1 --dry-run 与 git apply --check 都过；(b) 真实链 patch -p1：0501→0505→本补丁 rc=0、无 reject（0505 在缺 0502 的短链上带 fuzz 1，与本补丁无关）；(c) 与框架同机制：在构建缓存 bsd/ 上按真实序列 0500→0502b→0501→0502→0503→0504→0505→本补丁 全部 git apply rc=0、零 fuzz、零 reject，落地 conf/files:119-120、bsd_init.c:1357-1358，五个新文件与 drivers/PongAudio/ cmp 逐字节相同（脚本 E:/k60-work/scratch/audio-work/gitchain-verify.sh，transcript 见 patches/audio/README.md）"

[hardware.audio.step.device]
done = false
evidence = "未上机。需要 Lead 先加 pong_audio_probe=1 并出镜像；本子任务不刷机（铁则 4/5）"

[hardware.audio.step.device.prediction]
success = "日志顺序为 amp probe start → gcc vote/clk → se15 ready → amp0/amp1 id=0x… → amp probe done found=2/2 failed=0 timeouts=0"
failure = "se15 no DFS level / I2C pads 未生效 / amp 三次读无应答：分别指向 GCC 投票、引脚复用、功放供电（DT 无供电属性，读不到 ID 优先怀疑没供电）"
```

### 构建与镜像（本次实际产物，2026-11-14 05:38）

第一次 strict 构建被门禁脚本的**硬编码路径**挡住（判的不是正在构建的这棵树），与音频补丁无关；
修完脚本后同一条命令一次通过：

| 步骤 | 结果 |
| --- | --- |
| `build-strict.sh audio-probe-20261114g` | `series=230 frozen=52de0e1d…`、`kernel 849ac4370e741930… 54181888 bytes`、`boot.img bedb656364657476194809051885dd497a4db2ea329f003cfdc389650e580aa2` |
| `verify-boot-image.py --manifest …/audio-probe-20261114g/build-manifest.json` | `verify-boot-image: OK` |
| 证明确实进了内核（P-170） | `bsd/conf/files:120-121` = `PongAudioGeniI2c.c` / `PongAudioAmp.c`；`…/bsd/DEVELOPMENT/PongAudioAmp.o` 存在；`kernel.macho` 里 `PongAudio` 字符串 **36** 处；`bsd_init.c:1369-1370` 有调用 |
| payload args 尾部 | `… applog=1 pong_audio_probe=1` |

修复的脚本硬编码（问题相同：门禁读的不是正在构建的树）。`scripts/` 里共**九个**脚本把
`/mnt/e/hackios/UniXNU-mondrian` 写死成仓库根，全部改成从脚本自身位置推导：

1. `scripts/eight-step-gate.py:41` → 自相对（`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`）；
   这是「音频线 ①–⑥ 全通过却被判禁止构建」的直接原因。
2. `scripts/sync-device-input.py:18-20` → 仓库自相对，并让 `K60_DEVICE_INPUT` / `K60_SERIES_FINAL` 可覆盖。
3. `scripts/porting-gate.py:31-40` → 仓库自相对，`BUILD_OUT`（`K60_OUT`）、`DEV`（`K60_DEVICE_INPUT`）、
   `SERIES`（`K60_SERIES_FINAL`）跟随环境；`XNU_WORK` / `KERNEL` 由 `BUILD_OUT` 拼。
4. `scripts/check-build-applied.py:28` → `INPUT` 跟随 `K60_DEVICE_INPUT`；顺带把默认值从
   `/tmp/usb-cdc-mainline/device` 换成持久路径 `/opt/k60/trees/usb-cdc-mainline/device`
   （软链指向同一个目录，符合铁则 1 的 `check-tmp-artifacts`）。
5. `scripts/check-docs.py:24`、`scripts/render-eight-step-table.py:24`、
   `scripts/research-gate.py:34`、`scripts/check-build-freshness.py:30`、
   `scripts/check-adsp-claims.py:18`、`scripts/repair-resource-forks-k60.py:22`、
   `scripts/flash.sh:18` → 同一处写法一并自相对化。

新增门禁 `scripts/check-repo-paths.py`（P-183）：任何脚本再写死主工作区路径、
或任何判定/构建脚本丢掉「从自身位置推导根」的写法，直接 FAIL；确实跨树的工具
（`pick-upstream.py` 把仓库名映射到路径）列在 `ALLOW` 里并写明理由。

构建输入用私有树 `/opt/k60/trees/usb-cdc-mainline/audio-device`（从共享树 `rsync`，series 230 行、含
`../audio/0001-k60-audio-amp-probe.patch`），输出用私有 `/opt/k60/trees/k60build/out-audio`；
**共享 device 树与 `scratch/SERIES-FINAL.txt` 都没有被写入**。

### 门禁现状（本分支 + 构建环境，2026-11-14 12:52 实测，已并入 main 的门禁工具）

| 检查 | 结果 |
| --- | --- |
| `check-docs.py` | ✅ 187 项 |
| `check-boot-args.py` | ✅ |
| `check-tmp-artifacts.py` | ✅ |
| `eight-step-gate.py --build` | ✅ 36 项（6 个硬件项，audio 在内） |
| `porting-gate.py --quick` | ✅ rc=0 |
| `check-repo-paths.py` | ✅ 135 个脚本，2 个跨树工具已登记（P-193） |
| `check-rules.py` | ✅ **0 失败**（71 条登记 / 37 条 waiver / 执行 25 个命令，`RC=0`） |
| `check-line-endings.py` / `check-build-freshness.py` | ✅ |

`check-rules.py` 只有把 `K60_DEVICE_INPUT` 指向私有输入才是这个结果：用默认的共享
`/opt/k60/trees/usb-cdc-mainline/device` 会红 5 条（iron-4 / iron-5 / hard-33 / P-165 / P-166），
原因是那份副本还留着 BT 线的 `0507`–`0510` 四个补丁、没有 touch 线的六个探针与本补丁——
**是共享副本漂移，不是本树的问题**。判据：`diff patches/xnu/series <共享输入>/patches/xnu/series`
非空、而与 `audio-device` 的同一份 diff 为空。

`iron-5` 还要求构建输入与仓库**逐文件**一致（`sync-device-input.py --check` 逐文件比对，与本树无关的共享副本漂移也会被点出来），
所以改过 `drivers/PongAudio/**` 或 `patches/audio/**` 之后要先跑一次同步，否则它会点名具体文件：

```
K60_DEVICE_INPUT=/opt/k60/trees/usb-cdc-mainline/audio-device python3 scripts/sync-device-input.py
```

复现命令（四个 `K60_*` 必须同时给，缺一个就会读到共享副本）：

```
cd <本 worktree>
K60_DEVICE_INPUT=/opt/k60/trees/usb-cdc-mainline/audio-device \
K60_OUT=/opt/k60/trees/k60build/out-audio \
K60_SERIES_FINAL=/mnt/e/k60-work/scratch/audio-work/SERIES-FINAL.txt \
bash scripts/build-strict.sh <tag> --fd <…silicon.fd> --kernel-arg pong_audio_probe=1
```

## 7. 上机结果与剩余阻塞

### 7.1 有效镜像（`j`，与当前 HEAD 同步）

`/mnt/e/k60-work/artifacts/audio-probe-20261114j/boot.img`
（sha256 `877d0a9d08ae0bff591ccb6d470a47eac46bdfa26a0d0ff4376a711c35723ef2`，`verify-boot-image: OK`），
manifest `/mnt/e/k60-work/artifacts/audio-probe-20261114j/build-manifest.json` 记
`repo.head e6351d8`、`dirty_files 0`、`series 230 / 37b91dbe…`、`frozen 1da672a9…`、
`kernel_args ["pong_audio_probe=1"]`；kernel `3c8853c8…`、payload `8c617c72…`、
payload_kernel `e34316b4…`、adt `ea5f4131…`、dtb `2d044eaa…`、fd `4bbe7601…`。

构建命令（私有树，共享镜像零写入）：

```
cd /mnt/e/hackios/k60-audio-merge
K60_DEVICE_INPUT=/opt/k60/trees/usb-cdc-mainline/audio-device \
K60_OUT=/opt/k60/trees/k60build/out-audio \
scripts/build-strict.sh audio-probe-20261114j \
  --fd /mnt/e/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --kernel-arg pong_audio_probe=1
```

镜像必须与 HEAD 同步：每改一次 `scripts/` 或补丁，冻结清单（`frozen`）就变，旧镜像的清单对不上
`check-build-freshness`。`j` 是当前有效版本；`g`（`034f5b5`，`frozen 52de0e1d…`）已被 GPLL0 合规改动
（`e889324`）取代，`f` 因为构建途中改了 `scripts/` 被冻结检查作废，`e`/`d`/`c` 更旧。
补丁应用顺序已在 `kernel.log:228-233` 证实：`0503 → 0504 → 0505 → 0001-k60-audio-amp-probe → 0506`。

`j` 之后唯一的内核侧改动是 `eb5f0c7`（`PongCodecPlan.h` + 宿主单测 + 文档）。冻结清单是
`find board.toml dts patches/xnu scripts`——**不含 `drivers/`**（那只是补丁的源，真正进树的是
`patches/audio/0001`，而本次没有重新生成它），所以重算 `frozen-before` 仍是 `1da672a9…`，
与 `j` 的清单逐行相同。**run 2 必须继续用 `j`，不要为这次改动重建镜像**：重建会得到一个新 sha，
而铁则 5 要的是同一个镜像两次 boot。

### 7.2 第一次上机（run 1 of 2，2026-11-14 12:10）

证据目录 `E:\k60-work\evidence\audio-probe-j\run1`（`console.log` 222,415 B / 3,333 行、
`capture.json` state=`captured-budget-complete`、`complete: true`、`stopReason: budget`、
`panicMarker: null`、`portSeen`/`portOpened` 都是 true、`boot.json` 记 `bootAccepted: true` / `bootExitCode: 0`）。
`scripts/judge-audio-capture.py` 判 **`VERDICT: SUCCESS - amplifiers identified`**（exit 0）。

驱动日志（`console.log:191-220`，逐字）：

```
PongAudio: amp probe start (amplifiers are read-only; AMPS.md A1-A7)   ← run 1 时的旧 banner；当前代码 banner 见 §9.2
PongAudio: amp gcc gpll0 vote=0x00000001 mode=0xe0000005 locked=1
PongAudio: amp gcc vote 0x0 -> 0x1f readback 0x1f
PongAudio: amp gcc clk wrap2_core halt=0x00004220 running=1
PongAudio: amp gcc clk wrap2_core_2x halt=0x00004220 running=1
PongAudio: amp gcc clk wrap2_m_ahb halt=0x00000000 running=1
PongAudio: amp gcc clk wrap2_s_ahb halt=0x80000002 running=1
PongAudio: amp gcc clk wrap2_s0 halt=0x00004220 running=1
PongAudio: amp i2c pad gpio=56 cfg=0x00000001 -> 0x00000007 readback=0x00000007
PongAudio: amp i2c pad gpio=57 cfg=0x00000001 -> 0x00000007 readback=0x00000007
PongAudio: amp se15 fw=0x00000303 proto=3 disabled=0x00000000 clock=0x00000011 scl=0x00000000
PongAudio: amp gcc dfs level=0 cfg=0x00000001
PongAudio: amp se15 ready config=0x03000021 status=0x00000000 level=0
PongAudio: amp reset amp0 gpio=1 released by this probe cfg=0x00000001 -> 0x000003c0
PongAudio: amp reset amp1 gpio=3 released by this probe cfg=0x00000001 -> 0x000003c0
PongAudio: amp0 addr=0x34 id=0x2113 chip=AW88261 status=0x0000 faults=0x0000 pll=0
PongAudio: amp0 mask=0xffff ctrl=0x3343 i2s=0x04e8 dbg=0xa003 vbat=0x0263 pvdd=0x0263 temp=0x0019
PongAudio: amp0 vcal=0x2000 fuse=0x83fd/0x5bf3/0x83fd/0x5bf3
PongAudio: amp1 addr=0x35 id=0x2113 chip=AW88261 status=0x0000 faults=0x0000 pll=0
PongAudio: amp1 mask=0xffff ctrl=0x3343 i2s=0x04e8 dbg=0xa003 vbat=0x0263 pvdd=0x0263 temp=0x0019
PongAudio: amp1 vcal=0x2000 fuse=0x8009/0x5bf7/0x8009/0x5bf7
PongAudio: amp probe done found=2/2 transfers=28 failed=0 timeouts=0 stray=0 recovered=0 gcc_misses=0
```

这一轮把 §5 的三个待实测项全部答掉：

| 待实测项 | 实测结论 | 依据 |
| --- | --- | --- |
| A5 chip ID 是哪一颗 | **两颗都是 Awinic AW88261（`0x2113`）**，与 phk110 同型号 | `amp0/amp1 addr=… id=0x2113 chip=AW88261` |
| A7 I2C 引脚是否已被 Android 配好 | **没有**：两颗引脚进内核时 `cfg=0x00000001`（function 0 = GPIO、2 mA、no-pull），是本探针改成 `0x00000007`（function 1 = qup15、pull-up、2 mA）后读回一致 | `amp i2c pad gpio=56/57 cfg=0x00000001 -> 0x00000007 readback=0x00000007` |
| 功放供电是否已使能 | **是**：`vbat=0x0263`（0x263×6025/1023 ≈ 2.56 V）、`pvdd=0x0263`、`status=0x0000`（`UVLS` 1<<14 与 `BSTOCS`、`NOCLKS` 全为 0） | `amp<N> … status=0x0000 faults=0x0000 … vbat=0x0263 pvdd=0x0263` |

附带得到的事实：
- `ctrl=0x3343` 的 bit0（`PWDN`）与 bit1（`AMPPD`）都是 1 → 芯片当前处于 power-down / amp power-down，
  即 **Android 关机后留下的状态**，符合「只读探针不初始化」的设计（§4 的 power-down 位定义）。
- `pll=0`、`i2s=0x04e8`（`TXEN` 1<<6 = 0）→ 没有 TDM 时钟，功放未启动，符合预期。
- `transfers=28`（2 颗 ×（1 次 ID 读 + 13 个只读寄存器））、`failed=0 timeouts=0 stray=0 recovered=0
  gcc_misses=0` → GENI 状态机与总线恢复路径在真实硬件上一次故障都没触发。
- 两颗 fuse 不同（`0x83fd/0x5bf3` vs `0x8009/0x5bf7`）而 `vcal` 都是 `0x2000`（= 8192）：
  这不是「两颗标定相同」，而是 `0x50` 的**上电默认值** —— 本次探针把复位线从低拉高后芯片回到默认态，
  `0x50` 从未被写过。按 §4 的公式复算，amp0 应为 `0x2052`、amp1 应为 `0x2094`，见 §8.7。

### 7.3 剩余阻塞（⑧ 仍未完成）

1. **run 2 没有有效证据**：铁则 5 要求同一镜像两次 `fastboot boot`，本轮只有 run 1 算数。
   需要说明的是：`boot-audio-twice.ps1` 在 run 1 结束后**自动**进了 run 2（`12:15:50` 建目录、
   `12:15:57` `fastboot` 报 `Booting OKAY`），但作业在 run 2 的抓取期间被用户叫停（「禁止擅自 boot」），
   因此 `run2/console.log` 是 **0 字节**、`capture.json` 根本没生成、`boot.json` 记 `bootAccepted: false`。
   这一轮**不构成**第二次证据，⑧ 仍按未完成记。run 2 必须等用户与 Lead 批准后单独跑：
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/boot-audio-twice.ps1 -Image E:\k60-work\artifacts\audio-probe-20261114j\boot.img -EvidenceRoot E:\k60-work\evidence\audio-probe-j2`
   （必须是新证据目录，脚本拒绝复用已有 `boot.json` 的目录）。
2. **播放通路**（TDM/MI2S → 功放）需要 LPASS 音频前端与 ADSP 图 → Lead 的 PAS1 + AudioReach。
3. **`aw882xx_acf.bin` 配置档**：**已解决**。此前记的路径（`/vendor/etc/`）是错的，实际在
   `/vendor/firmware/aw882xx_acf.bin`；设备停在 Android 时用 `adb pull` 只读取到（3,440 B，
   sha256 `ce0e16d22380565114f56e6a02e4f85959160baccc6c163df6ecaf9db20cbf9e`），未 boot、未写设备。
   十条目、两份 Music profile、monitor 表全部解析且校验通过，见 §8.3–§8.4；解析已做成纯函数（§8.8）。
### ⑧ 的判据（用两份历史 capture.json 校准，2026-11-14）

`capture.json` 里**没有** `verdict` 字段。能判的是这几个键，由
`scripts/capture-k60-usblog.ps1` 调 `Get-K60CaptureVerdict`（`scripts/k60-capture-state.ps1`）算出：
`state`（`captured` / `captured-truncated` / …）、`complete`、`stopReason`（`budget` /
`fastboot-return` / …）、`panicMarker`、`resetMarker`、`lastError`、`portSeen` / `portOpened` /
`openErrors`。

对照组（同一天、同采集器，一次好一次坏）：

| 证据目录 | 关键字段 | 真实结果 |
| --- | --- | --- |
| `E:\k60-work\evidence\usblog-20261113-noinitblob\capture.json` | `state: captured-truncated`、`complete: false`、`stopReason: budget`、`panicMarker: "K60PANIC"` | **正常启动**（SB=129） |
| `E:\k60-work\evidence\usblog-20261113-rev0340\capture.json` | `state: captured`、`complete: true`、`stopReason: fastboot-return`、`panicMarker: "K60PANIC"`、`openErrors: 24` | **坏启动**（SB=7） |

两条要点：

1. `panicMarker` 只是「采集器曾经搜过这个标记名」，**好坏两次启动取值完全相同**，把它当
   「发生了 panic」会一律误判；`complete: true` 也不代表内核好（坏的那次反而是 true）。
   健康启动本身就会打印横幅 `K60PANIC: restart windows ready`（`usblog-20261113-noinitblob/console.log:477`），
   这也是 `scratch/logstat.py` 的 panic 计数不可用的原因。
2. 本子任务的成败**不看** `state`/`complete`，只看 `console.log` 里 `PongAudio:` 的行：
   ① `amp probe start`（探针真的跑了）；② `amp gcc clk …` / `amp se15 ready …`（总线可用）；
   ③ `amp0/amp1 … id=0x…`（读到了 ID）；④ `amp probe done found=2/2 … failed=0 timeouts=0`（成功）。
   只有 ④ 出现且两颗 ID 都在已知表里，才算 ⑧ 成立；`state` 只用来解释「为什么没跑起来」。

判据已做成工具，不再靠人眼读 json：`scripts/judge-audio-capture.py <证据目录>…`
（它匹配的是驱动里 `printf` 的真实前缀：`amp probe start`（`PongAudioAmp.c:551`）、
`amp gcc clk`（`:286`）、`amp se15 ready`（`:419`）、`amp<N> … id=0x…`（`:526`）、
`amp probe done`（`:583`）；退出码 0 = 两颗都识别且 `failed=0 timeouts=0 recovered=0`，
1 = 跑了但失败，2 = 根本没跑）
（宿主单测 `scripts/tests/test-judge-audio-capture.py` 用合成采集钉住三种结局与两个陷阱：
`panicMarker` 带 K60PANIC 的健康启动仍判 SUCCESS、`complete: true` 救不回静默功放、
未知 chip id 即使 `found=2/2` 也判失败、缺 `console.log` 判「探针没跑」）。
两个历史目录跑出来的都是「probe never ran」——它们本来就早于本探针，说明工具不会把
「没跑」误读成「失败」或「成功」。

铁则 5 的「同一镜像两次 boot」也做成了机械执行器：
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/boot-audio-twice.ps1 -Image <boot.img> -EvidenceRoot <目录>`。
它先确认 `6033dbec` 已在 fastboot（不在就 `throw`，不写任何 `boot.json`），再跑两次
`boot-and-capture.ps1`，每次校验 `boot.json` 的 `imageSha256` 与入参一致（不一致就拒绝），
第二次前等设备回 fastboot，最后把两个目录交给 judge 并以它的退出码退出。
两次结果合并时**按严重度排序而不是取 exit code 最大值**（`severity()`：失败 1 重于没跑 2 重于成功 0）——
直接 `max()` 会让「探针没跑」盖住「跑了但失败」，正好把最有用的证据藏起来。
无设备实测：脚本解析通过、退出码 1、零证据目录 —— 拒绝而不是半启动
（`boot-audio-twice.ps1 -Image …/audio-probe-20261114g/boot.img -EvidenceRoot …/preflight-g2`，
输出 `target 6033dbec is not in fastboot; nothing was booted`，证据目录 0 个文件）。
`scripts/tests/test-judge-audio-capture.py` 已在 `porting.toml` 的 audio 区段登记（`scripts/tests/*audio*`），
否则 `check-porting-paths.py` 会报「no area claims tracked path」。

阻塞（不属于本子任务）：
- 播放通路（TDM/MI2S → 功放）需要 LPASS 音频前端与 ADSP 图 → Lead 的 PAS1 + AudioReach。
- 功放的 `aw882xx_acf.bin` 配置档已从手机 `/vendor/firmware/` 只读取到并解析完（§8.3–§8.4），
  不再是阻塞；剩下的是「等 PAS1/TDM 通路起来再写寄存器」（§8.9）。

## 8. A5 的结论：移植哪份功放驱动

A5（§5）原本只是「读一次 chip id」。它跑通之后，答案不止是型号，还牵出三件事：三份候选源码各自的许可证边界、
一颗真正能用的驱动需要的那份配置档到底在哪、以及两颗功放为什么**不能共用一张寄存器表**。本节把它们逐条钉死。

### 8.1 A5 已回答的部分（硬件，run 1 实测）

两颗功放都是 **Awinic AW88261**（chip id `0x2113`），与 phk110 同型号：

```
PongAudio: amp0 addr=0x34 id=0x2113 chip=AW88261 status=0x0000 faults=0x0000 pll=0
PongAudio: amp1 addr=0x35 id=0x2113 chip=AW88261 status=0x0000 faults=0x0000 pll=0
PongAudio: amp probe done found=2/2 transfers=28 failed=0 timeouts=0 stray=0 recovered=0 gcc_misses=0
```

所以「移植哪份驱动」不是「哪个型号的驱动」，而是「同一型号的三份实现里，哪一份的**代码**能进这个仓库、
哪一份只能当**事实来源**」。

### 8.2 三份候选与许可证边界（这是选型的真正约束）

| 候选 | 许可证 | 能拿什么 | 不能拿什么 |
| --- | --- | --- | --- |
| `patches/xnu/0503-k60-audio-aw882xx.patch`（本仓库） | BSD-2-Clause-Patent | **GENI 传输层可以留**：`aw882xx_geni_prepare`（`:198`）、`aw882xx_geni_wr`（`:192`）、`aw882xx_geni_rd`（`:186`），含 `IF_DISABLE` / `CLK_CFG` / `SCL_COUNTERS` 四条拒绝条件与 DMA 包长设置 | 寄存器语义层是空壳：`AW882XX_TODO_CHIP_ID_REG 0x0000u`（`:551`），`aw882xx_probe_one`（`:623`）/`aw882xx_start`（`:780`）都没有内容 |
| mainline `aw88261.c` / `aw88261.h`（`/home/emilelu/wifi-inputs/linux/sound/soc/codecs/`） | **GPL-2.0-only**（各自第 1 行 SPDX） | 事实：寄存器地址与位定义、`check_syspll`/`check_sysst` 的判据、`reg_update` 的写入顺序、vcalb 公式 | 一行代码都不能搬 |
| phk110 `hakios.speaker.c`（`/mnt/e/k60-work/references/phk110-port/drivers/audio/`） | kernel 侧 **APSL-2.0**（XNU 衍生） | 事实与结构：ACF 解析判据（`:525-640`）、prepare 顺序（`:738`）、monitor 表（`:1004`）、双 PA 通道映射（`:430-431`） | 同样不能搬 |

仓库自己的许可证是 `LICENSE:1-3` 的 **BSD-2-Clause-Patent**，`THIRD_PARTY_NOTICES.md` 只要求保留各组件的 SPDX、
没有 GPL 兼容条款 —— 所以 GPL-2.0-only 的 mainline 实现和 APSL-2.0 的 phk110 实现**都只能当文档用**。

**结论**：传输层继续用本仓库的 0503 补丁；寄存器语义层按上面两份的事实自己写，写成**纯函数**，
落点是新文件 `drivers/PongAudio/PongAudioAcf.h`（§8.8）。这样「能不能移植」变成一个可以被宿主单测证明的问题，
而不是一个需要信任某份外部代码的问题。

### 8.3 ACF 配置档：在手机上，而且不在 `/vendor/etc`

此前 §7.3 与本节都记过「`aw882xx_acf.bin` 本机没有，需要 Lead 从 vendor 分区取」，而且把路径写成
`/vendor/etc/aw882xx_acf.bin`。两处都错，实测更正：

```
adb shell 'find /vendor /odm /system -maxdepth 3 -iname "*acf*"'
# → /vendor/firmware/aw882xx_acf.bin
adb pull /vendor/firmware/aw882xx_acf.bin   # 只读，未写设备、未 boot
# → 3,440 B, sha256 ce0e16d22380565114f56e6a02e4f85959160baccc6c163df6ecaf9db20cbf9e
```

- 设备当时在 Android（`mondrian` / Android 17，`adb shell id` = `uid=0(root)`），因此这次取档**不涉及**任何启动动作。
- `/vendor/firmware/` 里还有一堆 `*_RTP.bin`（游戏音效），与功放无关；`ls /sys/module | grep aw8` 显示厂商模块 `aw882xx_dlkm` 正在跑，
  说明 Android 侧确实用它初始化过这两颗。
- **不进仓库**：`.gitignore` 含 `*.bin`。既有先例是 `proprietary-files.txt`（注释写明「Apple 文件不入库，构建期按 `board.toml` 的
  iOS 16.6.1 / 20G81 恢复 URL 抓取」）+ `scripts/fetch-ios16-assets.py` / `scripts/verify-firmware.py`，ACF 应走同一条路。
- 顺带取到的一条：`/vendor/firmware_mnt/image/` 里 `adsp.b00`–`adsp.b18` 齐全（`adsp.b02` 3,216,484 B、`adsp.b18` 11,511,192 B），
  `CODEC.md:173` 记的「`adsp.mbn` 仍缺」可以从这里补 —— 归 Lead 的 PAS1 线，这里只记位置。

### 8.4 ACF 格式（实测，与 mainline / phk110 的判据逐条对上）

头（LE32）：`id 0x0a15f908`（= `aw88395_data_type.h:19` 的 `ACF_FILE_ID`）、project `M11A`、custom `xiaomi`、
`entry_size 640 @0x34`、`entries 10 @0x38`、`table_at 0x50 @0x3c`、`hdr_version 1 @0x40`。
**dde 步长 = `entry_size / entries` = 64**（phk110 `hakios.speaker.c:543` 就是这么算的；把 `entry_size` 直接当步长会读出乱码）。

dde 字段偏移：`name@+4`(16 B)、`dev_index@+20`(u16)、`bus@+22`(u16)、`addr@+24`(u16)、`profile@+26`(u16)、
**`kind@+28`(u32)**、`length@+32`(u32)、`offset@+36`(u32)。实测 `bus` 与 `addr` **全是 `0xffff`（未填）** →
**只能靠 `dev_index` 区分两颗，不能靠 I2C 地址**。

十条目（`kind` 4 = 寄存器表、10 = monitor，`profile` 0 = Music，见 `hakios.speaker.c:404-406`）：

| dev_index | profile | kind | 大小 | 偏移 |
| --- | --- | --- | --- | --- |
| 0 | 6 | 4 | 292 | `0x2d0` |
| 0 | **0（Music）** | 4 | 292 | `0x3f4` |
| 0 | 10 | 4 | 292 | `0x518` |
| 0 | 1 | 4 | 292 | `0x63c` |
| 0 | 6 | **10（monitor）** | 192 | `0x760` |
| 1 | 6 | 4 | 292 | `0x820` |
| 1 | **0（Music）** | 4 | 292 | `0x944` |
| 1 | 10 | 4 | 292 | `0xa68` |
| 1 | 1 | 4 | 292 | `0xb8c` |
| 1 | 6 | 10 | 192 | `0xcb0` |

**十条校验和全部通过**。规则（phk110 `:604-611`）：寄存器表块 = `sum(block[4 : 0x3c + data_length])`，
monitor 块 = `sum(block[4 : length])`，与块首的 LE32 比较。早前按 `sum(block[4:length])` 算寄存器表会全红 —— 是算法错，不是文件坏。

Music 块头：`data_length@+0x10 = 232`、`count@+0x3c = 57`（`232 == 4 + 4×57` ✓）、`le32(+0x20)==2 && le32(+0x24)==2`
（16 位寄存器 × 16 位值），**寄存器对从 `+0x40` 起，LE16 reg + LE16 val**。

dev0 的 57 对（`03=ffff` 起，`0x50` **不在表里**，由 fuse 算）：

```
03=ffff 04=3240 05=1811 06=34e8 07=3020 08=00f6 09=6672 0a=0964 0b=2590 0c=1c64 0d=005b
0e=4a9b 0f=5064 10=d008 11=1f20 12=002b 13=2102 14=c003 15=0643 16=000a 30=866d 31=7193
32=4306 33=689b 34=90dc 35=d508 36=a835 37=f184 38=0800 3a=8884 3b=0666 3c=0ed2 3d=0663
3e=01ae 3f=0505 40=ffa0 51=00f3 52=3ee8 53=8005 54=1748 55=0202 56=3800 57=84c9 58=41d6
59=0000 5a=0000 5b=01c0 5c=0049 60=0fcd 61=796c 62=4a40 63=6077 64=0053 65=5ca1 66=40f9
67=508e 68=0048
```

**dev1 与 dev0 只差 5 对**：`05 1811→0811`、`06 34e8→38e8`、`07 3020→3111`、`08 00f6→00f7`、`0f 5064→5264`；
寄存器顺序完全相同。四份寄存器表各自的差异对数：prof6 4 对、prof0 5 对、prof10 **22 对**、prof1 4 对。
→ **两颗是独立标定的，绝不能共用一张表**；按 `dev_index` 分表是硬要求，不是风格问题。

monitor 表（dev0 与 dev1 **完全相同**）：`temp_count@0x2c / temp_size@0x30 / temp_at@0x34`、
`vbat_count@0x3c / vbat_size@0x40 / vbat_at@0x44`；实测 4 行 @`0x54`、5 行 @`0x84`，每行 12 B
（`int16 min`、`int16 max`、`u16 boost`、`u16 less` 单位 1/8 dB、`int32 vmax`）：

| 类型 | 行 |
| --- | --- |
| 温度 | `(7,100) less 0`、`(2,5) less 24`、`(-2,0) less 36`、`(-50,-5) less 64` |
| 电压(mV) | `(4100,5000) less 0`、`(3900,4000) less 4`、`(3700,3800) less 8`、`(3500,3600) less 12`、`(0,3400) less 16` |

### 8.5 两颗的通道映射（最容易搞反的一处）

phk110 `hakios.speaker.c:430-431` 写得很清楚：

```c
{ .address = 0x35, .device = 0, .where = "0x35, slot 0" },
{ .address = 0x34, .device = 1, .where = "0x34, slot 1" },
```

即 **I2C `0x35` ↔ `dev_index 0` ↔ slot 0（左声道）**，**`0x34` ↔ `dev_index 1` ↔ slot 1**。
而本仓库的探针把 `0x34` 叫作 **amp0**、`0x35` 叫作 **amp1**（`PongAudioRegs.h` 的 `PONG_AUDIO_AMP_ADDR0/1`）。
→ **探针的 amp0 要吃 ACF 的 `dev_index 1` 那份 profile**。移植时若按「amp0 → dev0」直觉写，两颗会各自加载对方的标定，
症状是「能出声但音量和保护点都不对」，属于最难从日志看出来的那类错误。
> **⚠️ 警告（写驱动前必读，Lead 2026-11-14 点名要求显眼处）**：`ACF dev_index` 与探针编号是**两套编号**——
> **`0x35 ↔ dev_index 0 ↔ 探针 amp1`，`0x34 ↔ dev_index 1 ↔ 探针 amp0`，方向相反**。
> 按探针编号直接选 profile 表会让两颗各自加载**对方的**标定（音量曲线、温度/电压保护点全错），
> 症状是「能出声但保护与音量都不对」，属于最难从日志看出的失败。这条映射已做成纯函数
> `pong_acf_channel_for_addr()`（`0x35→0`、`0x34→1`、其余 `0xff`）与
> `pong_amp_profile_for_addr()`（`0x35→dev0 表`、`0x34→dev1 表`、其余 `NULL`），由宿主单测钉住；
> `amp_replay_one()` 只按 **I2C 地址**选表，从不按探针编号。

### 8.6 写入语义：照抄 mainline 的 `reg_update`，不要照抄 ACF 里的字面值

`aw88261.c:393-490 aw88261_dev_reg_update()` 逐对写 57 个寄存器，但**有四处不是照写**：

1. `0x04`（SYSCTRL）：先 `amppd_st = reg_val & ~AMPPD_MASK`，读回当前值，只保留 `PWDN|AMPPD|HMUTE` 三位拼进新值，
   再强制 `ULS_HMUTE = 1`（`:420-434`）。→ **ACF 里的 `04=3240` 不能直接写**，必须走读-改-写语义。
2. `0x14`（DBGCTRL）：`efcheck_val = reg_val & ~EF_DBMD_MASK`，等于 `OR_VALUE 0x0008` 走 OR 校验，否则走 AND（`:437-443`）。
   K60 blob 写 `14=c003`、run 1 读回 `a003`，两者都走 **AND**。
3. `0x08`（I2SCTRL3）：`reg_val &= I2STXEN_MASK; reg_val |= I2STXEN_DISABLE_VALUE` —— **profile 阶段先把 TX 关掉**（`:447-450`）。
4. `0x50`（VSNTM1）：`continue`，**不写 ACF 的值**；循环结束后统一 `aw88261_dev_set_vcalb()` 算出来再写（§8.7）。

写完再 `set_volume(mute_volume)`。另有一处必须分清：**真正打开 TX 的位在 `I2SCFG1(0x13)` bit6**
（`aw88261.c:90-98 aw88261_dev_i2s_tx_enable()` 写的是 `AW88261_I2SCFG1_REG`），而 profile 阶段清的是 `I2SCTRL3(0x08)` bit6。
本仓库 `PongAudioRegs.h` 里的 `AW_REG_I2SCTRL 0x06` 实际是 **I2SCTRL1**，注释语义要按 `aw88261.h:14-70` 校正。

启动顺序（`aw88261_dev_start`，`:547`）也是判据的一部分：`pwd(false)` → 等 2 ms → `check_syspll`
（要求 `SYSST` 的 `CLKS_STABLE(bit4) | PLLS_LOCKED(bit0)`，失败先试 `PLLCTRL1.CCO_MUX` 切 DIVIDED 再回 BYPASS）
→ `amppd(false)` → 等 1 ms → `check_sysst`（要求 `BSTS(bit9) | SWS(bit8) | CLKS(bit4) | PLLS(bit0)`）
→ `i2s_tx_enable(true)` → `uls_hmute(false)` → `mute(false)` → 清中断。任一检查失败都要退回掉电态，而不是继续写。

### 8.7 vcalb：run 1 读到的 `0x2000` 是上电默认值

公式（`aw88261.c:358-391`）：`vcalb = (1 << 13) × (1000 + icalk) / (1000 + vcalk)`，写 `0x50`。
`icalk` / `vcalk` 来自 4 个 fuse 寄存器（`0x78/0x79/0x7c/0x7d`），字段是**有符号 10 位**：
`bits & 0x200` 置位时为负（`bits - 0x400`），再 `+1000`。OR / AND 由 `0x14` 的 `EF_DBMD` 位决定（§8.6）。

用 run 1 实测的 fuse 复算（C 程序按 16 位语义跑，不是纸算）：

| 功放 | fuse（`78/79/7c/7d`） | icalk | vcalk | vcalb |
| --- | --- | --- | --- | --- |
| amp0（`0x34`，dev_index 1） | `83fd / 5bf3 / 83fd / 5bf3` | −3 → 997 | −13 → 987 | **8274 = `0x2052`** |
| amp1（`0x35`，dev_index 0） | `8009 / 5bf7 / 8009 / 5bf7` | +9 → 1009 | −9 → 991 | **8340 = `0x2094`** |

而 run 1 读回的 `0x50` 两颗都是 `0x2000`（= 8192，即 `icalk == vcalk` 的默认值）。这不是公式错、也不是读数错：
**本次探针把两颗的复位线从低拉高**（`PongAudioAmp.c:168-187 amp_reset_release()`，日志 `released by this probe`），
芯片因此回到上电默认态，`0x50` 从未被写过。同理 `04=0x3343`、`06=0x04e8`、`14=0xa003`、`03=0xffff` 也都是默认值，
与 ACF 目标态（`04=3240`、`06=34e8`、`14=c003`）不同是必然的。→ **将来驱动必须在 start 之前自己算并写 `0x50`**。

### 8.8 已交付的 host 侧代码

`drivers/PongAudio/PongAudioAcf.h`（304 行，BSD-2-Clause-Patent）把上面 8.3–8.7 全部做成**纯函数**：
无 MMIO、无内核头，因此每一条都能在构建机上证明，而不是等上机。

| 函数 | 作用 |
| --- | --- |
| `pong_acf_header_ok` | magic、`entry_size % entries == 0`、`entry_size/entries >= 0x30`、表在文件内（phk110 `:525-640` 的三条判据） |
| `pong_acf_stride` / `pong_acf_count` | 步长（真实 64）与条目数（真实 10） |
| `pong_acf_find` | 按 `dev_index + profile + kind` 三元组定位块（**不是按地址**，ACF 里地址是 `0xffff`） |
| `pong_acf_checksum` / `pong_acf_block_ok` | 寄存器表与 monitor 块各自的和校验 |
| `pong_acf_pairs_ok` / `pong_acf_pair_count` / `pong_acf_pair_at` | 16×16 表头自洽、57 对、LE16 取值 |
| `pong_acf_channel_for_addr` | `0x35→0`、`0x34→1`（§8.5 的映射） |
| `pong_acf_ef_or` | `0x14` 的 `EF_DBMD` 决定 OR / AND |
| `pong_acf_fuse_value` | 10 位有符号 fuse 值 → `1000 + icalk` |
| `pong_acf_vcalb` | 公式 → 待写 `0x50` 的值（amp0 `0x2052` / amp1 `0x2094`） |

宿主用例 `acf_cases()` 把这些钉住：合成 blob 的六种 header 拒绝、find 的三元组语义、翻一个字节即校验失败、
8 位表拒绝、channel 映射、OR/AND 两条路径、fuse 值域两端（488 / 1511），以及**真实 blob 存在时的 13 条断言**
（十条目、步长 64、dev0/dev1 Music 各 57 对且校验通过、monitor 通过）。真实 blob 用环境变量喂，因为它不入库：

```
wsl.exe -e bash -lc 'cd /mnt/e/hackios/k60-audio-merge && sh drivers/PongAudio/tests/run-tests.sh'
# → TESTS OK 956 cases
wsl.exe -e bash -lc 'cd /mnt/e/hackios/k60-audio-merge && PONG_ACF_FILE=/mnt/e/k60-work/scratch/audio-work/refs/acf/aw882xx_acf.bin sh drivers/PongAudio/tests/run-tests.sh'
# → TESTS OK 974 cases
```

`PongAudioAcf.h` **现在进补丁了**（回放层让 `PongAudioAmp.c` include 它，见 §9）；`PongCodecPlan.h` 仍不进（内核侧还没有 `.c` include 它）。

### 8.9 A5 之后还差什么

1. **真正写寄存器的驱动**（soft reset → 57 对 → `0x50` → TX）：写路径本身已作为**回放层**落地（§9，`PongAudioAmpReplay.h` + `PongAudioAmp.c` 的 `amp_replay_one`），但没有时钟与音频帧、不走 start 序列，写进去的是一台「配置正确但不出声」的功放 —— 那正是 §4 警告的假成功；完整驱动的 start/monitor 等 PAS1/TDM 通路（Lead 的线）。
2. **ACF 的构建期抓取**：按 `proprietary-files.txt` 的先例加一条，避免 `*.bin` 入库。
3. **run 2**：⑧ 仍缺第二次 boot，须用户与 Lead 批准后单独执行（§7.3 第 1 条）。

## 9. 回放层：把 ACF 的寄存器语义接到 0503 的 GENI 传输层

§8 的结论是「语义层自己写」。这一节是它的**执行部分**：语义不再是文档里的表，而是探针在
`pong_audio_probe=1` 下真的走一遍、并把每一次写入与回读都打进日志的代码。**没有新增调用点**
（仍然是 `bsd_init.c` 里那一段），也不依赖 PAS1：功放挂在 AP 自己的 QUPV3 wrapper 2 上，写它不需要 DSP。

### 9.1 三个新文件与它们的分工

| 文件 | 内容 | 为什么是纯函数 |
| --- | --- | --- |
| `drivers/PongAudio/PongAudioAmpProfile.h` | 两份 Music profile：`pong_amp_profile_dev0` / `pong_amp_profile_dev1`，各 57 对 `(reg, val)`（`PONG_AMP_PROFILE_PAIRS`），外加 `pong_amp_profile_for_addr(addr)`：`0x35→dev0`、`0x34→dev1`、其余 `NULL` | 表是**生成**的（`E:/k60-work/scratch/audio-work/gen-profile-header.py`，脚本自带 checksum/count 断言），不是手抄；生成物入库、blob 不入库（`.gitignore` 忽略 `*.bin`） |
| `drivers/PongAudio/PongAudioAmpReplay.h` | 回放顺序：`pong_replay_steps(pairs) = pairs + 3`、`pong_replay_at(profile,pairs,index,…)` 逐步产出动作（`PongReplayWrite` / `Sysctrl` / `TxOff` / `Vcalb` / `Volume`）、`pong_replay_sysctrl(acf,hw)`、`pong_replay_db_to_reg()`、`pong_replay_volume()` | 「写什么、按什么顺序、哪几位保留硬件值」全部是算术；留在 `.c` 里的只有 MMIO 与打印 |
| `PongAudioAmp.c` 的 `amp_write()` / `profile_reg()` / `amp_replay_one()` | 3 字节写 `{reg, val>>8, val}`（AW882xx 是 16 位寄存器 + 16 位值，走 `pong_geni_start_write_bytes`），每步写完立刻回读并打印 | 只剩传输与日志 |

每颗功放 **60 步**：0 = 软复位（`0x00 ← 0x55aa`），1..57 = Music profile 的 57 对，58 = `0x50 ← vcalb`，
59 = `0x05 ← 静音音量`。四类特例（§8.6）全部落在 `pong_replay_at()` 里：`0x04` 返回 `PongReplaySysctrl`
（值由 `pong_replay_sysctrl()` 与硬件回读合并）、`0x08` 返回 `PongReplayTxOff`（值已清 bit6）、
`0x50` 与 `reg >= 0x70` 一律拒绝（由第 58 步单独写）。

### 9.2 日志形状（上机时要看到的）

banner 已改成不再自称只读：

```
PongAudio: amp probe start (read pass first, then a replay pass that writes the tuning table; AMPS.md A1-A7 and section 9)
...
PongAudio: amp0 replay 00 reg=0x00 wrote=0x55aa read=0x0000
PongAudio: amp0 replay 01 reg=0x03 wrote=0xffff read=0xffff
PongAudio: amp0 replay 02 reg=0x04 wrote=0x7343 read=0x7343 (three bits kept from hw)
PongAudio: amp0 replay 05 reg=0x06 wrote=0x38e8 read=0x38e8
PongAudio: amp0 replay 07 reg=0x08 wrote=0x00f6 read=0x00f6
PongAudio: amp0 replay 58 reg=0x50 wrote=0x2052 read=0x2052
PongAudio: amp0 replay 59 reg=0x05 wrote=0x1bc0 read=0x1bc0
PongAudio: amp replay done amp0=60 amp1=60 written=120 mismatched=0 failed=0 transfers=...
```

- 每次写后都读回；不等时该行末尾打印 ` differs`，读失败打印 `read=failed` 并计入 `failed`。
- `amp0` 用 `dev_index 1` 的表、`amp1` 用 `dev_index 0` 的表（§8.5）——日志里两颗写出的 `0x06` 分别是
  `0x38e8` 与 `0x34e8`、`0x05` 分别是 `0x1bc0` 与 `0x13c0`（同为静音，保留的高 6 位来自各自硬件回读）。
  这两处一对上，就证明表选对了。
- `scripts/judge-audio-capture.py` 的**探针**判据不需要改（`MARK_START` 是前缀匹配、`MARK_ID` 要求 `id=0x`
  且 `MARK_DONE` 要求 `amp probe done found=`，回放行不会误命中）；**回放判据**由同一脚本的 `--replay` 承担，见 §9.6。

### 9.3 宿主侧钉住了什么（956 例 / 带真实 ACF 974 例）

`ring_queue_cases()` 另有 27 条断言：SPSC 队列初始化、已用/剩余空间、写满拒绝、跨尾写入、整帧复制、容量边界，以及 `pong_audio_submit()` 的空缓冲/入环与 `pong_audio_ring_read()` 出环。

`replay_cases()` 新增 49 条断言，关键几条：

| 断言 | 防的是什么 |
| --- | --- |
| `pong_amp_profile_for_addr(0x35)` 指向 dev0 表、`0x34` 指向 dev1 表、`0x36` 为 `NULL`；且 `pong_acf_channel_for_addr` 给出 `0x35→0 / 0x34→1` | **按探针编号选表**（§8.5 那个陷阱）。两条函数必须同时成立，否则「0x34 是 amp0」的直觉会悄悄赢 |
| 两张表都 57 对、寄存器顺序完全相同、**恰好 5 个值不同**（`0x05/0x06/0x07/0x08/0x0f`），`0x14` 两侧都是 `0xc003`，`0x50` 两侧都不在表里 | 抄错表、或把「两颗共用一张表」当成优化 |
| 第 0 步是 `0x00 ← 0x55aa`、第 1 步是 `0x03 ← 0xffff`、第 58 步 `Vcalb→0x50`、第 59 步 `Volume→0x05`、60 越界拒绝 | 顺序被「顺手」改掉 |
| `pong_replay_sysctrl(0x3240, 0x3343) == 0x7343`（硬件在掉电态：保留 PWDN/AMPPD/HMUTE）与 `(0x3240, 0x0000) == 0x7240`（硬件在运行态：**不能顺手把它关掉**） | 把 ACF 的 `0x3240` 直接写进去——那会覆盖硬件当前的三位 |
| `0x08` 步动作是 `TxOff` 且值是 `0x00b6`（`0x00f6` 清掉 bit6） | 把 profile 阶段当成「打开 TX」 |
| 手编表里出现 `0x50` 或 `reg >= 0x70` 时 `pong_replay_at` 返回 false | 绕过 `0x50` 由 fuse 计算这条规则 |
| `pong_replay_db_to_reg(720) == 0x3c0`、`pong_replay_volume(0x1811) == 0x1bc0` | 音量编码（`((v/48)<<6)|(v%48)`，高 6 位保留硬件） |
| `PONG_ACF_FILE` 存在时，两张编译进代码的表与真实 blob **逐对相等**（`bad0 == 0 && bad1 == 0`） | 生成器与 blob 漂移 |

### 9.4 这一层故意**不**做的事

- **不走 start 序列**：没有 `pwd(false)` → `check_syspll` → `amppd(false)` → `check_sysst` → `tx_enable`（§8.6）。
  没有 bit clock 时那几步只会失败，然后把芯片退回掉电——白写一遍还多一类噪声。
- **不开 TX、不解静音**：profile 阶段清 `I2SCTRL3` 的 TXEN，`ULS_HMUTE` 被强制置 1，音量写的是 `MUTE_VOL`。
  两颗芯片跑完仍是「配置正确但不出声」。
- **不读 ACF 文件**：表在编译期就在代码里（`PongAudioAmpProfile.h`），因为内核侧没有文件系统可用；
  ACF 的构建期抓取仍是 §8.9 第 2 条。
- **不碰 LPASS**：TDM/MI2S 前端与 ADSP 图是 Lead 的 PAS1 线。K60 侧的事实清单（PRI_TDM_RX_0、引脚、AFE 参数、dai-tdm 节点）整理在 `TDMS.md`。

这一层的意义是：等 PAS1 与 TDM 通路到位时，「写寄存器」这段不再是未验证的新代码，而是已经在设备上
跑过一遍、每一步都有回读记录的东西；剩下的只是把它接到 start 序列与音频帧上。

### 9.5 构建核验（镜像 k、m、n、a、b 与 c）

`audio-probe-20261114k` 是回放层第一次进内核构建：HEAD `ec95bc6`、8 文件补丁 `d85264ca…`、
`scripts/build-strict.sh` 全流程通过（八步 36 项、`verify-boot-image: OK`）。

- `kernel.log:228-231` 补丁顺序 `0503 → 0504 → 0505 → 0001-k60-audio-amp-probe`；
- `kernel.macho` sha256 `0640f6c79c88b559a2a08c0cee23e5bbb9eb659c5072c1d93270af5ca7ada4ca`（54,181,888 B）；
- manifest `/mnt/e/k60-work/artifacts/audio-probe-20261114k/build-manifest.json`：`repo.head ec95bc6`、
  `dirty_files 0`、`payload f3a6eafb…`、`payload_kernel 18e04ebb…`、`adt 2b1552ac…`、`dtb 2d044eaa…`、
  `fd 4bbe7601…`、`boot_img f34f33e3…`；
- 这就是 §6 第 4 条那条无法复现的 `-fsyntax-only` 的替代证据：回放层是在真实内核 flags 下编过的；
- `f34f33e3…` 曾是 run 2 的候选镜像；**2026-11-15 复核后 k 与 l 都按 P-201 撤下队列**（两者的 series 停在 230 条旧基线、`payload_kernel` 只有 54 MB），现行镜像是 c（见下）。

**镜像 m（2026-11-15）**：rebase 到 `origin/main` 626cc9b 之后重建，HEAD `9afa1e1`、series 225 条（sha256 `8e455072…`，224 条加 0504 的常量修正）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `7e86d966…`（105,504,768 B）、`payload_kernel a3e27a2e…`、`payload d5a544ac…`、
  `adt acdd72b9…`、`dtb 2d044eaa…`、`fd 4bbe7601…`；
- `boot.img` sha256 `2283aaa9…`（201,887,744 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261115m/build-manifest.json`；
- manifest 用 `kernel_args_requested: ["pong_audio_probe=1"]`（旧脚本写的是 `kernel_args` 键），命令行审计 `image-arg-audit: OK (30 arguments, 594 bytes)`；
- 这是 §6 第 4 条 `-fsyntax-only` 的第二份替代证据：0504 的三处 GPR 常量修正也在真实 kernel flags 下编过；
- m 构建完曾挂着；2026-11-17 由 n 取代（n 带 TLMM、PRM 与最终 9 文件补丁，见下）。

**镜像 n（2026-11-17）**：闭环台账与 TLMM/PCM ring 落地之后重建，HEAD `960d723b`、series 225 条（sha256 `8e455072…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `0c7d368b…`（105,504,768 B）、`payload_kernel 7d16361c…`、`payload fe6a6554…`、`adt 74e091e4…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `3c6a6783…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261115n/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；
- n 构建完曾挂着；2026-11-17 由 a 取代（0504 骨架常量修正后重建，见下）。

**镜像 a（2026-11-17）**：修正 `pong_audio.c` 骨架里遗留的 PRI 常量后重建，HEAD `1d79f925`、series 225 条（sha256 `8e455072…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `19133189…`（105,504,768 B）、`payload_kernel b8d09838…`、`payload 66b7a904…`、`adt d9f52b27…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `cc903abb…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117a/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；
- a 曾是当前候选：9 文件补丁 + PRM 时钟 + TLMM/spksw + 0504 骨架常量（1024 帧周期、14400 帧 lead、12.288 MHz、clock 0x204、attribute 4）；构建完挂着，等 ADSP carrier + provider 落地再飞（run 2 未批准，不 boot）。

**镜像 b（2026-11-17）**：把 `PongAudioAfe.h` 真正编进 `pong_audio.c`（0003）后重建，HEAD `8cd08323`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `e0f72ced…`（105,504,768 B）、`payload_kernel c5955b18…`、`payload 70361d25…`、`adt 52a7dd28…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `73c267fb…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117b/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；
- `kernel.macho` 上 `AFE encoder selftest` 字符串 1 处；`kernel.log:226` 已应用 `0003-k60-audio-afe-selftest.patch`；b 已被 c 取代（见下）；构建完挂着，等 ADSP carrier + provider 落地再飞（run 2 未批准，不 boot）。

**镜像 c（2026-11-17）**：把具名拒绝状态（`PongAudioErrNoLease = -2002`）与 0003 的六段版本编进内核后重建，HEAD `d269d376`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `7a22eaf9…`（105,504,768 B）、`payload_kernel fa6fded6…`、`payload 4bdca213…`、`adt 56aec95c…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `d2a49537…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117c/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；
- `kernel.macho` 上 `AFE encoder selftest` 1 处、`PongAudioErrNoLease` 1 处、`PongAudio: speaker path unavailable` 1 处；`kernel.log:226` 已应用 0003；c 曾是当前候选，已被 d 取代（见下）。

**镜像 d（2026-11-17）**：把 `QCOM_GLINK_MAX_CHANNELS` 从 1 落成 2（`drivers/PongPower/QcomGlink.h:17`）并把两槽结构传给电池 archive 后重建，HEAD `26166d00`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `04fac20b…`（105,504,768 B）、`payload_kernel 62395c14…`、`payload c12c354e…`、`adt 320a3b61…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `bb754421…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117d/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；
- `kernel.macho` 上 `QcomGlink max_channels=2u` 1 处；`battery archive 6f441f8b…`；d 曾是当前候选，已被 e 取代。

**镜像 e（2026-11-17）**：把 `K60AudioGlink` 的 adsp_apps 桥接到电池 GLINK，并把 `QCOM_GLINK_MAX_LOCAL_INTENTS` 从 4 扩到 20 后重建；同时把电池 archive 加进 bootstrap 链接（否则 `pong_audio_start` 引用 `k60_pmic_glink_attach_audio` 时 bootstrap 链接会报未定义）。HEAD `cdddd116`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `3ac73816…`（105,504,768 B）、`payload_kernel faeb6f21…`、`payload d7701ef7…`、`adt d5bf2fd1…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `7d285418…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117e/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；`battery archive ffe975c6…`；
- `kernel.macho` 上 `QcomGlink max_channels=2u local_intents=20` 1 处、`PongAudio: glink adsp_apps slot queued (512x20)` 1 处、`AFE encoder selftest` 1 处、`PongAudioErrNoLease` 2 处；e 曾是候选，已被 f 取代（见下）。

**镜像 f（2026-11-17）**：把 GPR `GET_SPF_STATE` 首发接进 0003——`pong_audio_glink_state()` 第一次收到 `up` 时用 `pong_gpr_encode` 组 24 B 请求（token `0x00010001`）经 `k60_pmic_glink_send_audio()` 发出，`pong_audio_glink_receive()` 解码 opcode/token。HEAD `3b68cd38`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `0acca673…`（105,521,152 B）、`payload_kernel d0994240…`、`payload 52bf43e0…`、`adt 0ae8eb00…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `3b67e496…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117f/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；`battery archive 843ab01e…`；
- `kernel.macho` 上 `PongAudio: GPR GET_SPF_STATE send bytes=%u rc=%d` 1 处、`PongAudio: glink adsp_apps slot queued (512x20)` 1 处、`QcomGlink max_channels=2u local_intents=20` 1 处、`AFE encoder selftest` 1 处、`PongAudioErrNoLease` 2 处；f 曾是候选，已被 g 取代（见下）。

**镜像 g（2026-11-17）**：把 AFE 六步报文规划器 `pong_afe_step_packet()` 与 0003 的六步状态机接进内核后重建；`PongAudioState` 保存 `apm_ready / afe_step / afe_retry / afe_token`，`pong_audio_afe_send_step()` 用规划器发包，`PongAudio: APM ready; starting AFE six-step` 在 APM 状态 1 后出现，`PongAudio: AFE six-step complete; speaker path ready` 在六步全部 ACK 后出现。HEAD `ce066e67`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `60e2a779…`（105,525,248 B）、`payload_kernel 0935a49d…`、`payload 1157dbf1…`、`adt 58eba591…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `e5e69d91…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117g/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；`battery archive 843ab01e…`；
- `kernel.macho` 上 `PongAudio: AFE step %u send bytes=%u opcode=0x%08x token=0x%08x rc=%d` 1 处、`PongAudio: APM ready; starting AFE six-step` 1 处、`PongAudio: AFE six-step complete; speaker path ready` 1 处（另有此前 f 的 GPR/adsp_apps 字符串各 1 处）；g 已被 h/i 取代，未 boot、run 2 未申请。

**镜像 h（2026-11-17）**：把 GLINK 发送队列接进 `K60AudioGlink`——没有远端 intent 时 `k60_audio_glink_send()` 把最多 560 B 的包留在 pending，`k60_audio_glink_service()` 在 intent 出现后 flush；队列满返回 REFUSED，4096 B 仍返回 TooBig。HEAD `39826cbf`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`。
- `kernel_built` sha256 `a671b0c9…`（105,525,248 B）、`payload_kernel 3698642c…`、`payload 517f8a9a…`、`adt 6c7915aa…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `ce78d96c…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117h/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；`battery archive f67b86e7…`；
- `kernel.macho` 上 `PongAudio: GPR GET_SPF_STATE send bytes=%u rc=%d`、`PongAudio: glink adsp_apps slot queued (512x20)`、`PongAudio: AFE step %u send bytes=%u opcode=0x%08x token=0x%08x rc=%d`、`PongAudio: APM ready; starting AFE six-step`、`PongAudio: AFE six-step complete; speaker path ready`、`QcomGlink max_channels=2u local_intents=20` 各 1 处，`PongAudioErrNoLease` 2 处。

**镜像 i（2026-11-17）**：修正 0003 的 GPR 端口——`pong_afe_gpr_spf_state_query()` 组 24 B `GET_SPF_STATE`，src 0x2001 / dst 1（此前 `src_port=0` 与参考 `PongAudio.cpp`/`ShengGpr.c` 不一致）。HEAD `a863878f`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`；i 已被 j 取代（见下）。
- `kernel_built` sha256 `923f9f44…`（105,525,248 B）、`payload_kernel 57f76659…`、`payload 0e7980a4…`、`adt a0fe139e…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `07d6003b…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117i/build-manifest.json`；`kernel_args_requested: ["pong_audio_probe=1"]`，`image-arg-audit: OK (30 arguments, 594 bytes)`；`battery archive f67b86e7…`；
- `kernel.macho` 上 `PongAudio: GPR GET_SPF_STATE send bytes=%u src=0x%x dst=0x%x rc=%d` 1 处，`QcomGlink max_channels=2u local_intents=20u`、`PongAudio: glink adsp_apps slot queued (512x20)`、`PongAudio: AFE step %u send bytes=%u opcode=0x%08x token=0x%08x rc=%d`、`PongAudio: APM ready; starting AFE six-step`、`PongAudio: AFE six-step complete; speaker path ready` 各 1 处；i 已被 j 取代（见下）。

**镜像 j（2026-11-17）**：在 `board.toml` 写入 `[adt.chosen.bytes] pong-audio-dma` 16 字节零占位（UEFI `DarwinBoot.c` 分配 64 KiB `EfiReservedMemoryType` 并回写 `[PA,65536]`），同时把 `K60PmicGlink` 的音频 attach 延迟到 `open()`，避免 `pong_audio_start()` 早于电池 GLINK 时丢失唯一 adsp_apps 客户端。HEAD `4cf2a910`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `bfacd35c…`（105,525,248 B）、`payload_kernel 326e8fe3…`、`payload 5f6eaf1a…`、`adt 784c097a…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `dff33d7a…`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117j/build-manifest.json`；`battery archive 2d1015d0…`；
- `kernel.macho` 上 `K60Battery: deferred audio attach failed: %d` 1 处，`PongAudio: GPR GET_SPF_STATE send bytes=%u src=0x%x dst=0x%x rc=%d`、`PongAudio: glink adsp_apps slot queued (512x20)`、`PongAudio: AFE step %u send bytes=%u opcode=0x%08x token=0x%08x rc=%d`、`PongAudio: APM ready; starting AFE six-step`、`PongAudio: AFE six-step complete; speaker path ready`、`QcomGlink max_channels=2u local_intents=20u` 各 1 处；
- 从 `payload.img` 的 `EFI/UniXNU/PAYLOADS/kernel.macho.adt` 抽出 ADT，sha256 `784c097a6aa15566bf87f044fbf0e3ff7e613dc7a2cd365da9d0f51809a3f0e9` 与 manifest `components.adt` 一致，`/chosen/pong-audio-dma` 为 16 个零字节；
- j 已被 k 取代（见下），未 boot、run 2 未申请。

**镜像 k（2026-11-17）**：把 PCM 提交环和低 DMA lease 接进 0003——`PongAudioRing.h` 的 SPSC 环（65536 帧、8192 B 周期、256 帧启动阈值、14400 帧 lead）由 `pong_audio_submit()` 入环、`pong_audio_ring_read()` 作为后续服务周期泵；`pong_audio_dma_lease()` 从 `/chosen/pong-audio-dma` 读取 UEFI 分配的 64 KiB。HEAD `1f49b6ad`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `08186a2454df694e528187880b93cbd492b45e36103e40b5846b08f8b3f057b8`（105,525,248 B）、`payload_kernel a9ac45dc…`、`payload b47cc9d7…`、`adt 5d806da1…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `3079b8cd43513d4d4a45e34958c9b1d3958d22da5752f410ec143a78f1d02761`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117k/build-manifest.json`；`battery archive 2d1015d0…`；
- `kernel.macho` 上 `PongAudio: low DMA lease pa=0x%llx size=0x%x` 1 处，`PongAudio: low DMA unavailable`/`invalid`/`map failed` 各 1 处；既有 `PongAudio: GPR GET_SPF_STATE...`、`PongAudio: glink adsp_apps slot queued (512x20)`、AFE 六步三条、`K60Battery: deferred audio attach failed: %d`、`QcomGlink max_channels=2u local_intents=20u` 各 1 处；
- 从 `payload.img` 的 `EFI/UniXNU/PAYLOADS/kernel.macho.adt` 抽出 ADT，sha256 `5d806da1bae605e64672f95e69d38bf71d94770a021de2169123f9093759afa3`（16,024 B）与 manifest `components.adt` 一致，`/chosen/pong-audio-dma` 为 16 个零字节；
- k 已被 l 取代（见下），未 boot、run 2 未申请。

**镜像 l（2026-11-17）**：把 `PongAudioServiceAbi.h` 与 `PongAudioService.cpp` 加入电池归档，并在 `IOKitBSDInit()` 后发布 `PongAudio` IOService/UserClient。HEAD `b343c592`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `94b1df0ad6a3c81e864ad94496dbf9b7be76c6ff8f34a9f85c9cc0385ffe4939`（105,529,344 B）、`payload_kernel 3a0fb2df…`、`payload 1b2b5e48…`、`adt e94e88f5…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `7dcd95c38889c77d0007f1a014e9cc793c7f1532f5eb31be9ed735ea37ea6dc1`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117l/build-manifest.json`；`battery archive 85a0c28f465af4c5ea13b16ea6e31e98a56e58e9fa5273ca66d4eb3cbf63f004`（91,896 B）；
- `kernel.macho` 上 `PongAudioUserClient` 26 处（含 C++ mangled symbol）、`NativeSandboxGrantProcess` 1 处、`k60_audio_service` 符号 1 处、`pong_audio_service_start` 符号 1 处；`PongAudio: low DMA lease pa=0x%llx size=0x%x` 与既有 AFE/GPR 字符串各 1 处；
- 服务在 `pong_audio_status()==0` 前拒绝 StartOutput（`kIOReturnNotReady`），因此镜像 l 只证明服务/UserClient 形状与编译，不证明 PCM 到达 DSP；l 已被 m 取代（见下）。

**镜像 m（2026-11-17）**：把播放图接进 0003——AFE 六步完成后按 11 步顺序 open/config speaker、open/config playback、config shmem、map、clock、prepare 两图、start 两图；PCM 环达到 14400 帧 lead 后起播，8 个 AR write 槽各 8192 B，WRITE_DONE 释放槽并由 `pong_audio_pump_one()` 续写。HEAD `73970b1f`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `d136541dcf7d540300ebe932cb4af3084d30520bdafa07a8ceda3cb895f66e55`（105,545,728 B）、`payload_kernel 28a83990…`、`payload 34d1971a…`、`adt 2c1af6fd…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `6ba6034c2dc8e7c06c97eb18eae37651044bb60fb7da8b6d65fe46aea1e694a0`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117m/build-manifest.json`；`battery archive 85a0c28f465af4c5ea13b16ea6e31e98a56e58e9fa5273ca66d4eb3cbf63f004`（91,896 B）；
- `kernel.macho` 上八条 playback 字符串各 1 处：`PongAudio: playback step %u send bytes=%u opcode=0x%08x token=0x%08x rc=%d`、`PongAudio: playback graph opening after AFE`、`PongAudio: playback graph mapped; waiting for PCM lead`、`PongAudio: playback graph started; PCM streaming`、`PongAudio: PCM slot %u submit bytes=%u token=0x%08x address=0x%llx`、`PongAudio: PCM lead reached frames=%u; starting playback graph`、`PongAudio: PCM write done slot=%u address=0x%llx`、`PongAudio: playback stream primed slots=%u inflight=%u`；符号 `pong_audio_play_complete_step`/`pong_audio_play_send_step`/`pong_audio_play_submit_slot`/`pong_audio_submit`/`pong_audio_ring_read` 均在；
- 从 `payload.img` 的 `EFI/UniXNU/PAYLOADS/kernel.macho.adt` 抽出 ADT 16,024 B，sha256 `2c1af6fd90763db9698bb8fab5d1345b3fbe4c0c331ccd543433a6ed4d525cdf` 与 manifest `components.adt` 一致，`/chosen/pong-audio-dma` 为 16 个零字节；m 已被 n 取代（见下），未 boot、run 2 未申请。

**镜像 n（2026-11-17）**：把 PCM 周期真正写进低 DMA 槽——`pong_audio_play_submit_slot()` 在每次 AR write 前把 8192 B 周期从 `state->period` 复制到 `dma_va + slot * PONG_PLAY_PERIOD_BYTES`，`dma_va == 0` 时拒绝提交；`pong_audio_play_reap_slots()` 在每个泵周期递增 busy 槽的 age，连续 8 个泵周期没有 WRITE_DONE 就释放该槽并打印 `PongAudio: PCM slot %u write timed out`。`PongAudioPlayback.h` 新增 `PONG_PLAY_SLOT_COUNT 8`、`PONG_PLAY_PERIOD_BYTES 8192`、`PONG_PLAY_PRIME_SLOTS 4`、`PONG_PLAY_SLOT_TIMEOUT_PUMPS 8` 及 `pong_play_slot_expired()`/`pong_play_slot_address()`，`play_cases()` 增加 9 条槽断言。HEAD `f059db8d`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `098a1c96a810bb49064eed42fc678d37c1a2390dbf4be1c970503fb9ea6fc4c0`（105,545,728 B）、`payload_kernel 68d01e98…`（构建后 out-audio 树已清理，从 boot.img 的 payload 区抽出的 kernel.macho sha256 `68d01e98ff90c0f71473e92e9da45706c1a840ce306344c0303fa43b721cc47e`，同尺寸）、`payload 68446054…`、`adt 621e9b02…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `cc153e51961f8d74bbd7479fde107d59d834aedf4db669f704c1212fbe6cb4f6`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117n/build-manifest.json`；`battery archive 85a0c28f465af4c5ea13b16ea6e31e98a56e58e9fa5273ca66d4eb3cbf63f004`（91,896 B）；
- `kernel.macho` 上八条 playback 字符串各 1 处，另 `PongAudio: PCM slot %u write timed out` 1 处；既有 `PongAudio: low DMA lease pa=0x%llx size=0x%x`、`PongAudio: GPR GET_SPF_STATE...`、`PongAudio: glink adsp_apps slot queued (512x20)`、AFE 六步三条、`K60Battery: deferred audio attach failed: %d`、`QcomGlink max_channels=2u local_intents=20u` 各 1 处；
- 从 `payload.img` 的 `EFI/UniXNU/PAYLOADS/kernel.macho.adt` 抽出 ADT 16,024 B，sha256 `621e9b02b718c1654e9d689080a0c5c58b79c7d6089819f285502933f4454de6` 与 manifest `components.adt` 一致，`/chosen/pong-audio-dma` 为 16 个零字节；n 已被 o 取代（见下），未 boot、run 2 未申请。

**镜像 o（2026-11-17）**：把用户态 HAL 与服务就绪修正一起落进候选——`userland/PongAudioPlugIn.c` 是 output-only AudioServerPlugIn（`IOServiceOpen` + `IOConnectMapMemory64` 映射 control/ring，Float32→S24/Q31，`StartIO`/`StopIO` 走 `PongAudioUserClient` selector）；`PongAudioService.cpp` 的 `startOutput()` 改为 `pong_audio_status() != PongAudioOk` 时返回 `kIOReturnNotReady`（此前 `==0` 反了）。HEAD `cb59f6a0`、series 226 条（sha256 `27268442…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `1edac302c42813d2670986b183faa98f05855c78f51c7ad6fc38ef9c791f7507`（105,545,728 B）、`payload_kernel 764b2ff7…`、`payload 225603fd…`、`adt 4f90664b…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `5fa57b842b94316bdbaee8bf5cb8083d974f8431506c1c691bdb128d490dd3b1`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117o/build-manifest.json`；`battery archive ef91f371db9476cb5e0f4b768f530431d5162dce42226f84676cc0f45950b747`（91,896 B）；
- `kernel.macho`（从 boot.img 的 payload 区抽出，sha256 `764b2ff74e183a4301a066fddf2e56892675a7a29393c43905487b593e6bf343`，105,545,728 B）上八条 playback 字符串各 1 处，另 `PongAudio: PCM slot %u write timed out` 1 处；`PongAudioUserClient` 26 处（含 mangled symbol）、`NativeSandboxGrantProcess` 1 处、`k60_audio_service` 1 处、`pong_audio_service_start` 1 处；`PongAudio: low DMA lease pa=0x%llx size=0x%x` 与既有 AFE/GPR 字符串各 1 处；
- 从 `payload.img` 的 `EFI/UniXNU/PAYLOADS/kernel.macho.adt` 抽出 ADT 16,024 B，sha256 `4f90664bb340ab63ea67df352385b5b665944213b43602907afa30b3d63e759e` 与 manifest `components.adt` 一致，`/chosen/pong-audio-dma` 为 16 个零字节；用户态 HAL 已由 `userland/build.py audio` 编译为 `PongAudio.driver/PongAudio`（69,920 B，sha256 `fa4780ea…`），并从镜像 p 起随内核部署；o 已被 p 取代（见下），未 boot、run 2 未申请。

**镜像 p（2026-11-17）**：把用户态 HAL 真正带进候选镜像——`patches/xnu/0617-k60-audio-hal-deploy.patch`（7,396 B / 241 行，sha256 `ee69bfc645fcc305f6e34ddf04d3121832b783a2799c91c224deafd7ed5c79de`）新增 `bsd/dev/k60_audio_hal.c`（196 行），按 `K60A` 容器把 `PongAudio.driver/Info.plist`（0644）与 `PongAudio.driver/PongAudio`（0755）写入 `/private/var/pong/empty-hal`；`init` 已把该目录 bind 到 `/System/Library/Audio/Plug-Ins/HAL` 与 `/Library/Audio/Plug-Ins/HAL`，所以 mediaserverd 不需要 `apply()` 改 sealed system 就能看到插件。`scripts/gen-k60-audio-hal-blob.py`（3,954 B，sha256 `d28a017e…`）生成 blob，`scripts/check-k60-audio-hal-blob.py`（3,826 B，sha256 `b6cfbf85…`）校验容器；`CONFIG_XNU_K60_AUDIO_HAL=y` 让 `build-strict` 先编译 `PongAudio.driver`，manifest 的 `audio_hal` 为 `fa4780ea…`（69,920 B），并检查 `k60_audio_hal_blob.s`。HEAD `563a0117`、series 227 条（sha256 `c6b1e8d3…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `kernel_built` sha256 `19cccd2b07c061497de0107227251f0338519d0f39ee2694bfee461cedd03df4`（105,615,360 B）、`payload_kernel 030cdff7…`、`payload 5617a19a…`、`adt 2da47aa8…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `30347dd8cbbf3bf00d0e184e73036d896d8b91df8da4a38a9d8419dd86cec8cf`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117p/build-manifest.json`；`battery archive ef91f371…`（91,896 B）；
- `kernel.macho`（从 boot.img 的 payload 区抽出，sha256 `030cdff728f284513d8487f77b6d2957dd39e1459c9a88e922c509272dbe61bb`，105,615,360 B）上 `K60AUDIOHAL deploy files=%u/%u error=%d`、`bad magic`、`bad count`、`entry body out of range`、`entry name out of range`、`open`、`write`、`removed a stale file` 各 1 处；八条 playback 字符串与 `PongAudio: PCM slot %u write timed out` 仍各 1 处；`PongAudioUserClient` 27 处（比 o 多 1，插件 Info.plist 的 `AudioServerPlugIn_IOKitUserClients` 也在镜像里）、`k60_audio_hal_deploy`/`k60_audio_hal_blob`/`k60_audio_hal_blob_len`/`k60_audio_hal_blob_modes` 符号均在；ADT 16,024 B，sha256 `2da47aa8aee9b175e3a3646b88fb9827f0c325c812301fa60c5757954a9440f8` 与 manifest 一致，`/chosen/pong-audio-dma` 为 16 个零字节；p 已被 q 取代（见下），未 boot、run 2 未申请。

**镜像 q（2026-11-17）**：首个把音频线与 Route A 合成同一个内核的候选——从 `feat/adsp-handoff-owner` `c19f1297` 与音频 `a1a4af95` 合并为 `8d0c5379`（merge），并修正 `0619`/`0620` 的 `IOKitBSDInit.cpp`/`files.arm64` 上下文（`11d64f8d`、`f0cea04d`）。HEAD `f0cea04d`、series 230 条（manifest file sha256 `999d0c271e521701a44df4bc011ae5578d87f9e6ee4652403fb15e6c2ec1a322`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs sha256 `900941c0…`）、`kernel_built 19c63805…`（129,167,360 B）、`payload_kernel 65862f43…`、`payload 629e72f7…`、`adt 1577dc71…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `f762ec3d2dba878c6edfc47069b477b9829ed12579656d7cc7c45c5311f7a31d`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117q/build-manifest.json`；`audio_hal fa4780ea…`（69,920 B，构建树 `build/audio/PongAudio.driver`）；`battery archive d61b73e6d2e55ecace440c82a3a201da0f8f410123c0bdf2167e331fa5873d4e`（149,520 B）；
- 从 boot.img 的 payload 区抽出 `kernel.macho` 129,167,360 B / sha256 `65862f437ec6488b5fe26c918934864aba43a428063b99eac715494d12d1e73a`（= manifest `payload_kernel`）：八条 playback 字符串与 `PongAudio: PCM slot %u write timed out` 各 1 处；`K60AUDIOHAL deploy files=%u/%u error=%d`、`bad magic`、`bad count`、`entry %u body out of range`、`entry %u name out of range`、`open`、`write`、`removed a stale file` 各 1 处；`K60Handoff: published authenticated PAS1` 1 处，`K60PAS` 25 处，`K60ADSP` 17 处，`k60_adsp_blob` 2 处；`PongAudioUserClient` 27 处、`NativeSandboxGrantProcess` 1 处、`k60_audio_service` 1 处、`pong_audio_service_start` 1 处；
- ADT 16,108 B sha256 `1577dc715ea263d5495fdca5feb9370cdd13187d021f313af29cb0daa6c86ab4`（= manifest `adt`），`/chosen/pong-audio-dma` 为 16 个零字节；q 是历史候选（已被 r 取代，见下），未 boot、run 2 未申请。

**镜像 r（2026-11-18）**：严格按官方 power 页补齐播放链——`K60AudioGlink.h` 的 `adsp_apps` intent 从 512 提到 560 字节（20 个，storage 11,200 B），`pcm` 播放图的 PRM 时钟请求改从 `AR_PRM_IID`（2）发出，`PongAudioServiceAbi.h` 升到 version 3、control 88 B（`out_seq`/`ticks_per_frame_q32`/`out_anchor_host`/`out_frames`），`PongAudioService.cpp` 实现 `SetHostClock` selector 4 并按 19.2 MHz 时基发布 anchor/ticks，`userland/PongAudioPlugIn.c` 用 `dlsym(AudioGetHostClockFrequency)` 调 selector 4、用 `out_seq` seqlock 生成 `GetZeroTimeStamp`；`pong_audio_dma_lease()` 在 `/chosen/pong-audio-dma` 为空时用 `kmem_alloc_contig(... max_pnum=0xfffff ...)` 自建 64 KiB 低 4 GiB 缓冲。HEAD `82f86b40`、series 230 条（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `adsp_blob 66336946…`（26 records）、`kernel_built f739d730ff26b0e156565063c2dfe401045ee2dc53a9fef08242c1de06a32f61`（129,167,360 B）、`payload_kernel 656d96d8…`、`payload ab4404e5…`、`adt 75028a58…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `43372cf34cd49505db892b4cdcb37b19c473eae78f3d866c4e505a92f8d50f4a`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117r/build-manifest.json`；`audio_hal 128a47e76d8b50742271baf210d7eefccccf59493bf5a91306c1aabd55efd1ed`（70,000 B，`build/audio/PongAudio.driver`）；`battery archive 551f1aaff125ec603e6ba4a9048e7c20ae77c16708e1e72e65c320115ef6a0f1`（150,888 B）；
- kernel.macho 129,167,360 B / `656d96d8…`：八条 playback 与 `PongAudio: PCM slot %u write timed out` 各 1；`PongAudio: low DMA allocated pa=0x%llx size=0x%x`、`PongAudio: low DMA lease pa=0x%llx size=0x%x`、`PongAudio: glink adsp_apps slot queued (560x20)`、`PongAudioService: CoreAudio host clock=%llu Hz`、`K60AUDIOHAL deploy files=%u/%u error=%d`、`K60Handoff: published authenticated PAS1` 各 1；ADT 16,108 B / `75028a58…`，`/chosen/pong-audio-dma` 16 个零字节；r 于 2026-11-18 01:06 在设备上启动到 SpringBoard（证据 `E:/k60-work/evidence/audio-probe-r/run1-20261118-0105`：bootAccepted=true、bootExitCode=0、capture complete），console 记录 `K60AUDIOHAL deploy files=2/2 error=0` 与 amp probe/replay 成功；但 init 的三个 boot view 全部 EPERM（`Pong init: boot view /private/var/pong/empty-hal -> /System/Library/Audio/Plug-Ins/HAL result=-1 errno=1`），mediaserverd 没有看到 HAL，也没有 `PongAudio HAL`、`PongAudioService: CoreAudio host clock` 或 `PongAudio: low DMA allocated` 行。r 已被 s 取代，run 2 未申请。

**镜像 s（2026-11-18）**：把 HAL 的密封根挂载从 init 的 bindfs 移到内核——`k60_audio_hal.c` 的 `k60_audio_hal_deploy()` 在 Data mount 后写 bundle，并在同一调用末尾执行 `k60_audio_hal_mount()`；后者用 `struct mount_args` + `MNT_RDONLY|MNT_UNION` 把 `/private/var/pong/empty-hal` 挂到 `/System/Library/Audio/Plug-Ins/HAL`，再用 `vnode_lookup` 验证 `PongAudio.driver/Info.plist`。HEAD `61b05bfd`、series 230 条（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (30 arguments, 594 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs sha256 `900941c0…`）、`kernel_built 69aed1e0c5a9d4dd45f5ad5d8e3e6c5e1430579f9fb224bbe344c1d58da6ee85`（129,167,360 B）、`payload_kernel 2d4eafeb…`、`payload c87fe882…`、`adt 97feed85…`、`dtb 2d044eaa…`、`fd 38c1293b…`；
- `boot.img` sha256 `ededd95e7859a376801844f22e37331819832e69456c17c4356d6f1291adcf6d`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261117s/build-manifest.json`；`audio_hal 128a47e7…`（70,000 B，`build/audio/PongAudio.driver`）；`battery archive 551f1aaf…`（150,888 B）；
- 从 boot.img 的 payload 区抽出 `kernel.macho` 129,167,360 B / `2d4eafeb…`：`K60AUDIOHAL mount point=` 3 处（成功/挂载失败/查找失败三种格式）、`K60AUDIOHAL deploy files=%u/%u error=%d`、`PongAudioService: CoreAudio host clock=%llu Hz`、`PongAudio: low DMA allocated pa=0x%llx size=0x%x`、`PongAudio: glink adsp_apps slot queued (560x20)`、`PongAudio HAL: K60 stereo service connected` 各 1 处；ADT 16,108 B / `97feed85…`，`/chosen/pong-audio-dma` 为 16 个零字节。s 于 2026-11-18 01:46 在设备上启动（证据 `E:/k60-work/evidence/audio-probe-s/run1-20261118-0143`；boot.json 的收尾被已结束的 watcher 打断，但 `console.log` 121,253 B 到 01:48:10 仍正常）：console 633 `K60AUDIOHAL deploy files=2/2 error=0`、635 `K60AUDIOHAL mount point=/System/Library/Audio/Plug-Ins/HAL files=2/2 error=0`、1595 `PongAudio HAL: K60 stereo service connected`、1604 `PongAudio HAL: AudioServerPlugIn initialized`，证明内核 bindfs 挂载和 HAL 加载成功；但没有播放流触发 StartIO，故尚无 CoreAudio host clock、低 DMA 或 PCM period 证据，pcm-submit-path 仍 open。run 2 未申请。

**镜像 v（2026-11-18）**：把音频路径收成一个 boot 门——`pong_audio=1` 同时启动 PCM/AFE 路径、触发 0619 的 authenticated PAS1 handoff（音频的 PMIC GLINK attach 需要它），并让 HAL 插件自动跑 boot-arg 播放自测（`PongAudio HAL: selftest period=...`）。HEAD `d95ca143`、series 230 条（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built ee8fcc1d1b9ceaa5be73ecaa5c64136c93d16e4c80fdaf17437ead2f51f6da24`（129,183,744 B）、`payload_kernel 6c0db672…`、`payload 463fef89…`、`adt f2f4601e…`、`dtb 2d044eaa…`、`fd e007de8a…`；
- `boot.img` sha256 `678107b0a8c3af3633fa8e36a31fa9f87b637e2eed27b722cc9a729e7106f93c`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261118v/build-manifest.json`；`audio_hal 2a3831cf0429e5fb7899ae0deaad3d890422291c27b9adbbb693fd5f2b0f6041`（86,704 B，含 selftest）；`battery archive 551f1aaf…`（150,888 B）；
- 构建完成，等待 free fastboot；HAL selftest 会在 `pong_audio=1` 时自动触发，run 2 未申请。

**镜像 w（2026-11-18）**：把低 DMA 的空 lease 修成真正的 fallback——ADT `/chosen/pong-audio-dma` 存在但 16 字节全零时，`pong_audio_dma_lease()` 打印 `PongAudio: low DMA lease invalid pa=0x%llx size=0x%llx; allocating below 4 GiB`，置 `pa=0; bytes=0x10000` 后继续走 `kmem_alloc_contig(... max_pnum=0xfffff ...)`，不再直接返回 NoLease；这是 `pong_audio=1` 路径能继续到 GLINK/AFE 的第一步（w 的 fallback 仍把普通内核映射当 DMA 地址，且 0xfffff 在 16 KiB 页上是 16 GiB，后续 y 修掉）。HEAD `9e45c158`、series 230 条（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built 8c8a294c70b379545d67145edad7fd9f014522ac6bb5d287ab90a52b4797bfb6`（129,183,744 B）、`payload_kernel 61e9964e…`、`payload d322d7cb…`、`adt d351294a…`、`dtb 2d044eaa…`、`fd e007de8a…`；
- `boot.img` sha256 `8aa4e8e8301fb54a9a82653af480d08aa3a40ae76bb6b8135f72ab73c9683aa3`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261118w/build-manifest.json`；`audio_hal 2a3831cf…`（86,704 B，含 selftest）；battery archive `551f1aaf…`（150,888 B，服务源码未变）；
- kernel.macho 129,183,744 B / `61e9964e…`：`K60AUDIOHAL mount point=` 3 处、`PongAudio: low DMA lease invalid`、`PongAudio: low DMA allocated pa=0x%llx size=0x%x`、`PongAudio: low DMA unavailable`、`PongAudio: glink adsp_apps slot queued (560x20)`、`PongAudioService: CoreAudio host clock=%llu Hz`、`PongAudio HAL: selftest period=`、`PongAudio HAL: selftest complete`、`PongAudio HAL: K60 stereo service connected` 各 1 处；ADT 16,108 B / `d351294a…`，`/chosen/pong-audio-dma` 仍为 16 个零字节；boot args 末尾 `pong_audio_probe=1 pong_audio=1`。w 构建完成，等待 free fastboot 后启动；run 2 未申请。

**镜像 y（2026-11-18）**：补齐低 DMA fallback 的两处剩余缺陷——`pong_audio_dma_lease()` 在空 lease 时仍走 `kmem_alloc_contig`，但分配后用 `ml_io_map()` 把物理页重新映射为 I/O 内存（DSP 直接读槽位，普通 cached 内核映射会让数据变旧）；`max_pnum` 从 `0xfffff` 改为 `(ppnum_t)(atop_64(4 GiB - bytes))`，因为 K60 RAM > 1 GiB 时页大小是 16 KiB（`PAGE_SHIFT_CONST = PAGE_MAX_SHIFT = 14`），0xfffff 实际是 16 GiB 上界。HEAD `19738a95`（代码 `b710e186`）、series 230 条（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built f49e7d4a381c18c5d43144b60e485ec5267901cdfe125aad00a85b9c29d8bd81`（129,183,744 B）、`payload_kernel 743ff87d…`、`payload b891fdf2…`、`adt 76dfb31a…`、`dtb 2d044eaa…`、`fd e007de8a…`；
- `boot.img` sha256 `26ac04a7672e02c0a2d01aa71f88f39f7b3a63afd78a77b04a385ccc2df296ec`（201,895,936 B），manifest `/mnt/e/k60-work/artifacts/audio-probe-20261118y/build-manifest.json`；`audio_hal 2a3831cf…`（86,704 B，含 selftest）；battery archive `551f1aaf…`（150,888 B，服务源码未变）；
- kernel.macho 129,183,744 B / `743ff87d…`：`K60AUDIOHAL mount point=` 3 处、`PongAudio: low DMA lease invalid`、`PongAudio: low DMA allocated pa=0x%llx size=0x%x`、`PongAudio: low DMA unavailable`、`PongAudio: glink adsp_apps slot queued (560x20)`、`PongAudioService: CoreAudio host clock=%llu Hz`、`PongAudio HAL: selftest period=`、`PongAudio HAL: selftest complete`、`PongAudio: AFE six-step complete; speaker path ready` 各 1 处；ADT 16,108 B / `76dfb31a…`；boot args 末尾 `pong_audio_probe=1 pong_audio=1`。y 于 2026-11-18 09:26 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-y/run1-20261118-0415`，bootAccepted=true、bootExitCode=0、returnedToFastboot=true）：console 190 为 `K60Handoff: published authenticated PAS1 epoch=1 bytes=104 flags=15`，240 为 `PongAudio: low DMA lease pa=0xdd4f4000 size=0x10000`，245 为 `PongAudio: glink adsp_apps slot queued (560x20)`，但没有 `PongAudio: glink adsp_apps up`；HAL selftest 的 `PongAudio HAL: StartIO result=1937010544` 是 kAudioHardwareNotRunningError。根因是音频槽直到 `k60_audio_glink_service()` 第一次请求才创建，晚于 DSP 的 adsp_apps OPEN，QcomGlink 按名匹配不到就丢弃。run 2 未申请。

**镜像 z（2026-11-18）**：为修复 y 的建槽时序，让 `K60PmicGlink::discover()` 在 PMIC_RTR_ADSP_APPS 槽之后调用 `k60_audio_glink_prepare()`，提前注册 adsp_apps 槽。HEAD `06c2a218`、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built 19755c20be30a44058cbb3364d85648f80867597869ae4711d5512c771e61bbe`（129,183,744 B）、`payload_kernel 57eae081…`、`payload a57abbc9…`、`adt f68dadc8…`、`audio_hal 2a3831cf…`（86,704 B，含 selftest）、`battery archive 3b8c86ec…`（150,888 B，含 K60AudioGlink/K60PmicGlink 改动）；
- `boot.img` sha256 `03de514ad1ec37079875dab0b96cfc37965a0923d14913e420f02dc545e6ab09`（201,895,936 B）；kernel.macho 129,183,744 B / `57eae081…`，`/chosen/pong-audio-dma` 仍为 16 个零字节；boot args 末尾 `pong_audio_probe=1 pong_audio=1`。
- 真机证据 `E:/k60-work/evidence/audio-probe-z/run1-20261118-0950`，bootAccepted=true、bootExitCode=0、capture state=captured-budget-complete complete=true、bytes=277,044、logSha256 `DC64D1BE…`：190 PAS1、191/192 GLINK transport/adopt、704/706 `K60AUDIOHAL` deploy/mount；但 209 `K60Battery: physical transport stopped error=-5; no DSP/FIFO reset`，随后 `PongAudio: PAS1 owner unavailable (acquire rc=-1000); ADSP path disabled`，无 GLINK up/APM/AFE。根因最初归为 `k60_audio_glink_prepare()` 用 `open_now=1` 在 PMIC 通道 up 前主动发 adsp_apps OPEN；改成 passive 后镜像 aa 仍在同一位置失败（见下），说明真正根因是**在 PMIC 通道 up 前让第二个 GLINK 槽参与握手**，与是否主动发 OPEN 无关。

**镜像 aa（2026-11-18）**：验证 passive 预注册仍不够。HEAD `9b5eee8c`（文档 `07922fea`）、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built 75af6cad5fb585e2a3d2042c22a924fae5ce79b319f1ea51e1a5b3f9fb812a2d`（129,183,744 B）、`payload_kernel d802a32b…`、`payload 780b34f0…`、`adt edb6e354…`、`audio_hal 2a3831cf…`（86,704 B，含 selftest）、`battery archive eb43869423e3106cc8f9b69ce40c5530f972353e5dbfc00a07e05ff7b3012a15`（150,888 B，含 K60AudioGlink/K60PmicGlink 改动）；
- `boot.img` sha256 `a234a22f72b9d390610a78408a8f3cfc94b8ac078ca8c705f8fda9f3879fb004`（201,895,936 B），manifest `E:/k60-work/artifacts/audio-probe-20261118aa/build-manifest.json`；
- 真机证据 `E:/k60-work/evidence/audio-probe-aa/run1-20261118-1010`，bootAccepted=true、bootExitCode=0、capture state=captured-budget-complete complete=true、bytes=269,364、logSha256 记录在 capture.json：190 PAS1、191/192 GLINK transport/adopt、240 `PongAudio: low DMA lease pa=0xdd4f4000 size=0x10000`；但 209 `K60Battery: physical transport stopped error=-5; no DSP/FIFO reset`，244 `PongAudio: codec-only path: amp probe + 60-step replay continue, AFE/GPR skipped`，246 `PongAudio: speaker path unavailable: PongAudioErrNoLease (no GLINK, no AFE)`，无 GLINK up/APM/AFE/PCM；判分脚本 FAIL（仅 PAS1/low DMA OK）。根因升级为在 PMIC 通道 up 前注册第二个 GLINK 槽会破坏共享 transport 握手；修复改为把 `k60_audio_glink_prepare()` 移到 `K60PmicGlink::channelState()` 的 PMIC up 回调，提交 `d4e11e87`，宿主 386 cases，新镜像 ab 见下。

**镜像 ab（2026-11-18）**：验证“PMIC up 回调里才建槽”仍不够。HEAD `193d1b9a`（代码 `d4e11e87`）、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built 6d7a4b3e…`（129,183,744 B）、`payload_kernel b547df1b…`、`payload e9bb8dc6…`、`adt 75f25888…`、`audio_hal 2a3831cf…`（86,704 B，含 selftest）、`battery archive 43759ca2…`（150,888 B，含 K60AudioGlink/K60PmicGlink 改动）；`boot.img` sha256 `91fbe72e…`（201,895,936 B），manifest `E:/k60-work/artifacts/audio-probe-20261118ab/build-manifest.json`。
- 真机证据 `E:/k60-work/evidence/audio-probe-ab/run1-20261118-1035`，bootAccepted=true、bootExitCode=0、capture state=captured-budget-complete complete=true、bytes=257,725、logSha256 `4C6A3789…`：189 PAS1、190 GLINK transport、191 adopting、239 `PongAudio: low DMA lease pa=0xdd4f4000 size=0x10000`、243 `PongAudio: glink adsp_apps slot queued (560x20)`、245 APM pending、567 `K60Battery: actual PMIC_RTR_ADSP_APPS channel up`；没有 `K60Battery: physical transport stopped`，也没有 `PongAudio: glink adsp_apps up`/APM/AFE/PCM/CoreAudio host clock；HAL selftest 仍为 `PongAudio HAL: StartIO result=1937010544`（0x73746F70）。根因：`k60_audio_glink_service()` 在 `requested` 时仍立即调用 `k60_audio_glink_prepare()`，但音频 attach 到 243 行才发生，DSP 的 adsp_apps OPEN 在此之前已被当成未知通道丢弃；PMIC 到 567 才 up，之后不会重发 OPEN。结论：槽必须在 `K60PmicGlink::discover()` 就注册（早于 DSP OPEN），但注册后要能保持静默，直到 PMIC 通道 up 才发 OPEN_ACK/OPEN——即 QcomGlink 的 hold-open 机制。

**镜像 ac（2026-11-18）**：验证“discover 早注册 + hold、PMIC up 才 release”的 hold 语义。HEAD `706a658e`（hold 提交 `59d4cc0b`）、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built 716beccef49f2575a3b7bfffcf8a46e6d6cc78443c83e8894599258f802eee34`（129,183,744 B）、`payload_kernel 5586e935…`、`payload 84ac3a16…`、`adt 26bd3153…`、`audio_hal 2a3831cf…`（86,704 B，含 selftest）、`battery archive b6ee09ac…`（152,040 B，含 K60AudioGlink/K60PmicGlink 改动）；`boot.img` sha256 `4eb27470…`（201,895,936 B），manifest `E:/k60-work/artifacts/audio-probe-20261118ac/build-manifest.json`。
- 真机证据 `E:/k60-work/evidence/audio-probe-ac/run1-20261118-1100`，bootAccepted=true、bootExitCode=0、capture state=captured-budget-complete complete=true、bytes=270,489、logSha256 `B3277916…`：190 PAS1、191/192 GLINK transport/adopt、239 `PongAudio: low DMA lease pa=0xdd4f4000 size=0x10000`、242 `PongAudio: glink adsp_apps slot queued (560x20)`、244 APM pending、533 `K60Battery: actual PMIC_RTR_ADSP_APPS channel up`、536 `K60Battery: physical transport stopped error=-5; no DSP/FIFO reset`；没有 GLINK up/APM/AFE/PCM；HAL selftest 仍 `StartIO result=1937010544`。结论：把 OPEN_ACK 也压到 PMIC up 后会让 DSP 等 ACK 超时并重置共享 transport；`02caba7f` 改为 DSP OPEN 立即回 OPEN_ACK、只把我方 OPEN 延迟到 release，宿主 386 cases；新镜像 ad 见下。

**镜像 ad（2026-11-18）**：验证立即 OPEN_ACK + 只延迟我方 OPEN。HEAD `02caba7f`、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built 85738be3d45f2315e4292db326c981e6ce223a4460415a7b6fa6da7c07ccddd7`（129,183,744 B）、`payload_kernel 5fa4ec9b…`、`payload 46ff54f8…`、`adt 01c23446…`、`audio_hal 2a3831cf…`（86,704 B，含 selftest）、`battery archive 0a389491…`（152,120 B，含 K60AudioGlink/K60PmicGlink/K60AudioGlink 改动）；`boot.img` sha256 `d673c7ad…`（201,895,936 B），manifest `E:/k60-work/artifacts/audio-probe-20261118ad/build-manifest.json`。
- kernel.macho 129,183,744 B / `5fa4ec9b…`：`K60Battery: audio GLINK slot reserve failed: %d`、`K60Battery: deferred audio attach failed: %d`、`PongAudio: glink adsp_apps %s`、`PongAudio: AFE six-step complete; speaker path ready`、`PongAudio: PCM lead reached frames=%u; starting playback graph`、`PongAudio: playback graph started; PCM streaming`、`PongAudio: low DMA allocated pa=0x%llx size=0x%x`、`PongAudioService: CoreAudio host clock=%llu Hz`、`PongAudio HAL: selftest period=`、`PongAudio HAL: selftest complete` 各 1 处；ADT 16,108 B / `01c23446…` 的 `/chosen/pong-audio-dma` 仍为 16 个零字节。ad 于 2026-11-18 11:52 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-ad/run1-20261118-1128`，bootAccepted=true、bootExitCode=0、returnedToFastboot=true，capture state=captured complete=true、bytes=98,710、logSha256 `2CC098CE…`、panicMarker=`K60PANIC: ring kept`）：189 PAS1、190 GLINK transport、191 adopting、239 `PongAudio: low DMA lease pa=0xdd4f4000 size=0x10000`、243 `PongAudio: glink adsp_apps slot queued (560x20)`、245 APM pending、533 `K60Battery: actual PMIC_RTR_ADSP_APPS channel up`，**534 `K60Battery: physical transport stopped error=-5; no DSP/FIFO reset`**；1527 HAL connected、1528 factory accepted、1529 selftest requested、1530 `PongAudio HAL: StartIO result=1937010544`。随后 1554 出现独立的内核 data abort（pc `_vprintf_internal+0xd50`、lr `_vprintf_internal+0xf8`，栈 `_printf/_open1/_open1at/_openat_nocancel/_unix_syscall`），1577 `K60PANIC: ring kept; restart reason -> bootloader`；y/ab 没有 panic，z/aa/ac 只有 -5 没有 panic，暂按独立内核缺陷记录。结论：DSP OPEN 立即 ACK、只延迟我方 OPEN 仍在 PMIC up 后立刻 -5，说明**只要 PMIC 握手前就存在第二个槽（即使静默）DSP 也会重置共享 transport**；必须把建槽整个推迟到 PMIC up 之后，由我方主动 OPEN。

**镜像 ae（2026-11-18，构建失败）**：尝试把音频槽改为 PMIC up 后 active OPEN。首次构建在 battery archive 编译失败：`QcomGlink.c:516:21: error: expected expression`，原因是 C 文件里用了 C++ 函数式 cast `unsigned(...)`；改成 `(unsigned)(...)` 与 `(unsigned)le32(raw + 4)` 后 amend 进诊断提交 `1c3d01af`，因此 ae 没有产物、没有上机，随后直接构建 af。

**镜像 af（2026-11-18）**：验证“PMIC up 前完全不建音频槽、PMIC up 回调里才建 initiator 槽并发我方 OPEN”。HEAD `26f3835d`（`fix(audio): create the audio slot only after PMIC up`）、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、`verify-boot-image: OK`、`image-arg-audit: OK (31 arguments, 607 bytes)`。
- `adsp_blob 66336946…`（26 records，inputs `900941c0…`）、`kernel_built b87b946adee722e22d29f86f3be36aa4e379cd4572bd3c5cd78d99beab606532`（129,183,744 B）、`payload_kernel 8a0c1239…`、`payload 9951704b…`、`adt 08a8ac952053238f05e8648782b921e8fb7b1c966b2f263e05bf3d0202defc71`、`audio_hal 2a3831cf…`（86,704 B，含 selftest）、`battery archive 360a26b1fa84f56ebfc85083bd058ab7d9d5eed10a4b8ab3b3850e5e5673f8e3`（152,896 B）；
- `boot.img` sha256 `aaad4817358708e4619dd95d382b6c96ce5653a71a5b4b037fef83ef055d3c35`（201,895,936 B），manifest `E:/k60-work/artifacts/audio-probe-20261118af/build-manifest.json`；
- kernel.macho 129,183,744 B / `8a0c1239…`：`K60Battery: audio GLINK slot opened`、`K60Battery: audio GLINK open failed: %d`、`K60Battery: deferred audio attach failed: %d`、`PongAudio: glink adsp_apps %s`、`PongAudio: AFE six-step complete; speaker path ready`、`PongAudio: PCM lead reached frames=%u; starting playback graph`、`PongAudio: playback graph started; PCM streaming`、`PongAudio: low DMA allocated pa=0x%llx size=0x%x`、`PongAudioService: CoreAudio host clock=%llu Hz`、`PongAudio HAL: selftest period=`、`PongAudio HAL: selftest complete` 各 1 处；ADT 16,108 B / `08a8ac95…` 的 `/chosen/pong-audio-dma` 仍为 16 个零字节。设计：`k60_audio_glink_service()` 在 PMIC up 前只保存 request、不建槽；`K60PmicGlink::channelState()` 的 up 回调调用 `k60_audio_glink_open()` 建 initiator 槽，`progress()` 同轮发我方 OPEN；宿主测试 `TESTS OK 497 cases`。af 于 2026-11-18 12:26 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-af/run1-20261118-1215`，bootAccepted=true、bootExitCode=0、returnedToFastboot=false、capture state=captured-budget-complete complete=true、bytes=260,494、logSha256 `0CB00B89…`）：189 PAS1、190 GLINK transport、240 low DMA lease pa=0xdd4f4000、244 glink adsp_apps slot queued、245 APM pending、530 `K60Battery: audio GLINK slot opened`、531 `K60Battery: actual PMIC_RTR_ADSP_APPS channel up`；随后 battery sample 到 34，**没有** physical transport stopped/QcomGlink: stop，也没有 `PongAudio: glink adsp_apps up`/APM/AFE/PCM/clock；HAL 1503 connected、1504 factory accepted、1505 selftest requested、1506 起 StartIO result=1937010544。结论：PMIC up 后建 initiator 槽不再触发 -5，但 DSP 不回应我方 adsp_apps OPEN。
- **镜像 ag（2026-11-18，GLINK 诊断）**：HEAD `b82ce0fe`（`fix(glink): trace the audio open handshake`）、built_at 12:47:39、series 230（sha256 `999d0c27…`）、`repo.dirty_files 0`、verify-boot-image OK、image-arg-audit OK (31 arguments, 607 bytes)；`kernel_built bc253864989f7e3e3a2465dcb473d6f9ab4fa8a92566b3d92d5dc73c06a008e8`（129,183,744 B）、`payload_kernel 0f8f92d3…`、`payload f7e9dc50…`、`adt 1a747737…`、`battery archive 7bf94341…`（153,968 B）、`boot.img 49f121f2…`（201,895,936 B），manifest `E:/k60-work/artifacts/audio-probe-20261118ag/build-manifest.json`；kernel.macho 新增 `QcomGlink: slot %s lcid=%u open_now=%d`、`QcomGlink: OPEN sent %s lcid=%u`、`QcomGlink: channel up %s lcid=%u`、`QcomGlink: rx OPEN name=%s p1=%u known=%d hold=%d`、`QcomGlink: rx OPEN_ACK lcid=%u known=%u sent=%u`、`QcomGlink: stop rc=%d cmd=%u …` 与每 128 次 poll 的 `ch %s lcid=%u sent=%u acked=%u remote=%u held=%u txavail=%u rxavail=%u` 各 1 处；watcher 已武装（后于 12:48 在 free fastboot 上启动）。**ag 实机结果（12:48–12:54，证据 `E:/k60-work/evidence/audio-probe-ag/run1-20261118-1238`，bootAccepted=true、bootExitCode=0、returnedToFastboot=false、capture state=captured-budget-complete complete=true、bytes=264,186、logSha256 `448914D7B74DFEAEEA24AC1B59ACC21867E70A5154361ED8C92850EA42717FAA`，console 3,920 行）**：190 `QcomGlink: slot PMIC_RTR_ADSP_APPS lcid=1 open_now=1`、203 `OPEN sent PMIC_RTR_ADSP_APPS lcid=1`、206–210 依次收到 `rx OPEN name=IPCRTR p1=1 known=0`、`pcie_drv p1=2 known=0`、**`adsp_apps p1=3 known=0 hold=-1`**、`fastrpcglink-apps-dsp p1=4 known=0`、`LOOPBACK_CTL_LPASS p1=5 known=0`，211 `rx OPEN_ACK lcid=1`；548 `ch adsp_apps lcid=2 sent=1 acked=1 remote=0 held=0 txavail=16360 rxavail=0`。**根因确定**：DSP 在 PMIC 握手期间就发来 adsp_apps 的 OPEN（rcid=3），此时音频槽还没建，`QcomGlink.c` 按名字找不到就丢弃；之后 DSP 只 ACK 我方 OPEN、不重发自己的 OPEN，`remote_open` 永远为 0，通道无法 up。无 `QcomGlink: stop`、无 transport stopped，HAL selftest 仍 `StartIO result=1937010544`。修复提交 `234558f4 fix(glink): adopt a remote OPEN that beat the slot`（3 files +125/−1）：`QcomGlink.h` 新增 `QCOM_GLINK_MAX_PENDING_OPENS 8u`、`QcomGlinkChannel.open_ack_pending`、`QcomGlink.pending_open[8]`；`QcomGlink.c` 的 unknown OPEN 分支用 `note_pending_open()` 记住名字与 rcid，`qcom_glink_channel()` 建槽时按名采纳（置 `rcid/remote_open/open_ack_pending`，打印 `QcomGlink: adopt remote OPEN %s rcid=%u`），`progress()` 在 `send_open` 后补发 `OPEN_ACK(rcid)` 并打印 `QcomGlink: late OPEN_ACK`，PMIC up 前仍不写任何字节；宿主 `TESTS OK 611 cases`。**镜像 ah（2026-11-18 13:10）**：HEAD `234558f4`、series 230（`999d0c27…`）、`repo.dirty_files 0`、verify-boot-image OK、image-arg-audit OK (31 arguments, 607 bytes)；`kernel_built 9f5c3eb8ae5a6bc30295660d828f1b3e260f5516efc5388a6e41c50a9dcf83e9`（129,183,744 B）、`payload_kernel 683b409b…`、`payload e55964a3…`、`adt 4dc245cd…`、`battery archive e97c8ea0…`（154,712 B）、`boot.img b99d1560b1185fc4f5290ee4dc0ac8e45256255000646dd2ec0cf89f893fa7a6`（201,895,936 B）；kernel.macho 上 `QcomGlink: adopt remote OPEN`、`QcomGlink: late OPEN_ACK` 各 1 处；watcher 已武装（PID 4852，等 free fastboot），run 2 未申请。

**镜像 ah–ak（2026-11-18，通道打通与 AFE 协议定位）**：ah（HEAD `234558f4`，boot.img `b99d1560…`）13:16 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-ah/run1-20261118-1300`，capture 260,929 B、logSha256 `0A30029A…`）：514 adopt remote OPEN adsp_apps rcid=3、518 OPEN sent、519 rx OPEN_ACK、520 late OPEN_ACK、521 channel up、522 PongAudio: glink adsp_apps up、523 GPR GET_SPF_STATE；随后 DSP 发来 1 对 8 字节 INTENT，524 QcomGlink: stop rc=-5 cmd=5 p1=3 p2=1 avail=1136，旧 INTENT 分支把重复且 busy 当 corrupt，bc3781e5 改为只计 dropped（更大 intent 替换最小空闲槽；宿主 800 cases）。ai（HEAD `bc3781e5`，boot.img `024bc2e7…`、kernel `252aaa88…`、battery `be50e93d…`）13:41 启动（证据 `E:/k60-work/evidence/audio-probe-ai/run1-20261118-1330`，257,769 B、`8E1E66FC…`）：508 GLINK up、511 APM ready、512 step 0 发 76 B、513 rx 32 kind=1 opcode=0x02001005 token=0x00020000 status=2；根因是 APM 命令头字段顺序（address lsw/msw、mem_map_handle、payload_size，size 在 +36），9d0b1095 修正后宿主 974 cases。aj（HEAD `9d0b1095`，boot.img `f6400722…`、kernel `8995e4a2…`）14:27 启动（证据 `E:/k60-work/evidence/audio-probe-aj/run1-20261118-1408`，275,679 B、`B8517605…`）：546 step 0、547 rx 32 kind=6 opcode=0x02001002 status=0（PRM 接受）、548 step 1 发 96 B、549 rx 32 kind=1 opcode=0x02001005 token=0x00020001 status=1、607 step 1 refused。ak（HEAD `721415bc`，boot.img `ce905f9f…`、kernel `71a666ed…`）14:49 启动（证据 `E:/k60-work/evidence/audio-probe-ak/run1-20261118-1438`，255,568 B、`CCB92CE3…`）：558–562 重复同一形状；把 GPR 目的端口从 0 改为 AFE 4 后 status 从 1 变 2（ADSP_EBADPARAM），说明这条 legacy svc 包未被 K60 固件接受。源码复核：vendor 的 afe_svc_cmd_set_param_v1（apr_audio-v2.h:12521-12533）与 port 0x100EF（:2028-2048）属 APR 合同（20 字节头、src/dst svc、域 ADSP4/APPS5），而 QcomGlink/PRM 走 GPR（24 字节头、域 ADSP2/APPS3）；AGM 的 TDM 端点走 graph/module API（graph_module.c:390-469,665-755），其 pcm_tdm_api.h 与板级 ACDB 不在本地。live DT 的 qcom,msm-cpudai-tdm-group-num-ports = <0x01> 只声明 0x9020，而 pong_afe_step_packet() 仍填 ports[1]=0x9022；a7d82acf 删除第二个成员、新增 pong_audio_group_probe=1 让 step 1 成功后停住，并打印响应的 src/dst domain 与 echoed opcode，镜像 al 待启动。

**镜像 al–ao（2026-11-18，单成员与 AFE v2）**：al 两次构建失败。第一次被 compliance registry 挡住：`docs/research/audio/GLINK-MULTISLOT.md` 与 `PAS1-AUDIO-REQUIREMENTS.md` 的改动（611→800 条断言、PAS1 2,056→2,328 B）没有进入 14c795c4——Windows `git status` 干净，但 WSL git 没有 core.autocrlf，看到工作树比 index 新；从 WSL 补提交 48bb3d51 后两侧都干净。第二次在 payload 阶段被 `unixnu: the kernel command line is 632 bytes; DarwinBoot accepts at most 607` 挡住：31 个参数已占满 607 B，新增 `pong_audio_group_probe=1`（25 B）超限，`build-strict: FATAL: payload build failed`，无 manifest。am 因此不带额外 boot-arg，只验证 a7d82acf 的单成员 group 配置：HEAD 48bb3d51、built_at 16:02:06、series 230（sha256 999d0c27…）、dirty_files 0、verify-boot-image OK、image-arg-audit OK (31 arguments, 607 bytes)；kernel_built a71af7ec…、payload_kernel a8ec5f78…、payload e9a6cee1…、adt 186de876…、audio_hal 2a3831cf…（86,704 B）、battery archive be50e93d…（154,800 B）、boot.img 344d6d78…（201,895,936 B）。16:02 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-am/run1-20261118-1545`，bootAccepted=true、bootExitCode=0、returnedToFastboot=false、capture 273,504 B、logSha256 DFB6ABEF…）：516 glink up、582 APM ready、583 step 0 发 76 B、584 rx kind=6 opcode 0x02001002 status=0、585 step 1 发 96 B、586 rx kind=1 opcode 0x02001005 token 0x00020001 status=2 src=2:0x4 dst=3:0x2001 echoed=0x000100f3、587 refused。响应来自 ADSP 域端口 4 并回显我们的 opcode，说明 AFE service 端口存在、包被解析，status=2 是 ADSP_EBADPARAM 而不是路由失败；单成员假设被否定。vendor `apr_audio-v2.h` 对账：group 44 B 负载、0x9020/0x9120 与 v1 96 B 信封都与结构体一致，但 `AFE_PARAM_ID_TDM_LANE_CONFIG` 注释（:13383-13386）要求 group device TDM 参数走 **AFE_SVC_CMD_SET_PARAM_V2**（0x000100fc，`struct afe_svc_cmd_set_param_v2` :12535-12547 = apr_hdr + mem_mapping_hdr + u32 payload_size + param_hdr_v3 16 B）。an 只把 v1 信封字段重排成 v2 顺序（d7176f89），构建中途取消、未上机。ao 改用真正的 V2（HEAD a7a6a24b、宿主 975 例、补丁 0001 124,889 B / 3,306 行 / sha256 69563e71…；group TDM 100 B、group enable 60 B、port 步骤 88/80/28 B 保持 v1 信封），构建成功：built_at 16:34:21、kernel_built 70e94cf1…、payload_kernel 3446bdb7…、adt 82e54e04…、battery be50e93d…（154,800 B）、boot.img e6edd1c8…（201,895,936 B），31 args/607 B，等待 free fastboot。

**镜像 aq–av（2026-11-18，TDM sink 打开与成对启动）**：aq（HEAD 24d63f85、boot.img dd54626a…、kernel 611f9d5d…）把未用 group 成员从 0xffff 改成 0（vendor q6afe 用 kzalloc 填 group 端口），17:08 启动（证据 `E:/k60-work/evidence/audio-probe-aq/run1-20261118-1655`）：534 glink up、537 APM ready、538 step 0、540 step 1 100 B v2 信封、542 refused opcode 0x000100fc status=2——零端口假设也被否定；GPR 上的 AFE 服务端口对 legacy APR 信封一律回 EBADPARAM。ar（HEAD 68a8640d、boot_img 3b9662a9…、kernel bd461f9b…）让被拒的 AFE 步骤跳过（48bdc975），17:35 启动（证据 `E:/k60-work/evidence/audio-probe-ar/run1-20261118-1725`）：AFE step 1–5 全部 status=2 并 skip、543 six-step complete、544 playback graph opening、545 step 0 296 B、546 GRAPH_OPEN status=0、547 step 1 128 B I2S speaker 配置、548 status=1 EFAILED、549 refused。as（`run1-20261118-1750`）与 at（`run1-20261118-1820`）加入 playback 跳过梯子（45aa88ac）：at 的 1605 START speaker 仍 status=1（1607），1609 START playback，1611 `playback graph started; PCM streaming` 之后没有 PCM slot 行。判读：K60 功放接在 TERT TDM RX（vendor `asoc/msm_dailink.h:385-392` 的 mondrian 分支把 `tert_tdm_rx_0` 的 codec 定义为 `aw882xx_smartpa.2-0035`/`2-0034`），不是 MI2S，speaker 子图应用 TDM sink（0x0700100E）而不是 I2S sink（0x0700100A）。
au（HEAD 95f3aafa、boot.img 0beac500…、kernel dd7b9ab4…、0504 30,334 B/994 行、0003 25,571 B/797 行）把 speaker 设备改成 TDM sink（TDM_INTF 44 B + TDM_LANE 4 B + HW_EP_MF 12 B + FRAME_SIZE 4 B，四个 16 B 参数头 = 168 B），并把 low-DMA 映射改成 write-combined；20:10 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-au/run1-20261118-1925`，bootAccepted=true、bootExitCode=0、returnedToFastboot=false、capture 261,192 B、logSha256 `178F12007E11A623798B9B6108B54454CC6144AAEC0E4C5E4B75C08639183D67`）：574/576/578/580/582/584/587 七步全部 status=0（含 168 B TDM 配置 577 与 PRM 588），586 map done handle=0xb0d8c0b8、589 waiting for PCM lead；1617 PCM lead 15360，1618/1620 两个 PREPARE 均 status=0，1624 START speaker 64 B → 1626 status=1、1628 skip，1629 START playback → 1631 `started without the speaker; not streaming`。即 TDM sink 模块在 K60 固件上真实存在且接受配置，唯一失败是 device subgraph 0x4005 单独 GRAPH_START 回 ADSP_EFAILED。
av（本段提交）把 11 步扩成 12 步：两个 PREPARE 之后新增 `PongPlayStartPair`，用一条 GRAPH_START（PARAM_SG_LIST count=2，0x4005 + 0x4001）成对启动（mainline q6apm 的 graph_start 就是一次带全部 subgraph），若成对启动被拒则回落到原来的两次单独启动；同时删掉 `pong_play_slot_address` 的 `| (1ull << 32)`——租约与分配都保证 pa < 4 GiB（0003 的检查是 `pa > 0x100000000ULL - bytes`），旧写地址是 0x1_dd4f4000，而 MEM_MAP 映射的是 0xdd4f4000，at 在第一笔 PCM 提交后约 30 s 复位与该越界地址吻合。宿主 `TESTS OK 978 cases`；0001 124,969 B/3,308 行、0003 25,956 B/808 行、0504 31,052 B/1,013 行；镜像 av 待构建。

**镜像 av–aw（2026-11-18，成对启动与写路径隔离）**：av（HEAD `620918d2`、boot.img `13a3fb310e8b9de7b41c908be4d9e9399394d368c1806b6a59642a9e186d72a8`、kernel `dc4edfae…`）21:15 在 free fastboot 上启动（证据 `E:/k60-work/evidence/audio-probe-av/run1-20261118-2112`，bootAccepted=true、bootExitCode=0、returnedToFastboot=true、capture state=captured-disconnected bytes=99,343）。七步配置全 status=0（168 B TDM speaker、MEM_MAP handle 0xb0d8c0b8、PRM 0x02001002 status=0）；成对 `GRAPH_START`（72 B，SG 列表 count=2、0x4005 + 0x4001）回 **status=1**，随后两条单子图 START 都回 status=0。1573–1578 四个 8 KiB 槽按 0xdd4f4000/0xdd4f6000/0xdd4f8000/0xdd4fa000 提交（bit32 已删），紧接着 `K60Battery: hardware sample unavailable (PMIC channel down)`、`PongAudio: glink adsp_apps down`、`K60Battery: physical transport stopped error=-27; no DSP/FIFO reset`，全程没有 `PCM write done`。`-27` 是 `K60PmicGlink::poll()` 的 `remoteReady()` 守卫（`drivers/PongPower/K60PmicGlink.cpp:191-203`）在 SMP2P 远端状态失效时写的本地撤销码，不是发送错误码。aw 因此把启动顺序拆开：两个 PREPARE 之后直接只发 playback 子图 START（`PongPlayStartPair` 与 `PongPlayStartSpeaker` 都不发），第 11 步完成后即使 speaker 未启动也允许提交 PCM，用来判定掉线发生在写路径还是 TDM 扬声器路径；宿主 `TESTS OK 978 cases`、313 个补丁可解析、0003 为 26,528 B/818 行/`d16da368…`。
（`PongAudioPlayback.h` 由 11 步扩成 12 步，成对 START 的 token 为 `0x00030009`。）

**镜像 ax（2026-11-19，音频流 0x1801 的 SMMU bypass）**：aw 的隔离探针给出结论——1619 `playback graph started without the speaker; streaming the slots anyway` 之后，1623/1624 打印 `PCM slot 0 copy begin/copy done`，**再没有任何一行**（无 submit、无 refused、无 glink down、无 -27），而 au 全程不写缓冲时活满 300 s。即杀死传输的是第一笔 PCM WRITE 本身，与 TDM 扬声器是否启动无关。设备树 `spf_core_platform/qcom,msm-audio-ion`（`live-fdt.dts:20784-20793`）声明 `iommus = <0x5b 0x1801 0x00>`、`qcom,smmu-sid-mask = <0x00 0x0f>`、`qcom,iommu-dma-addr-pool = <0x10000000 0x10000000>`：DSP 用地址高字取流号（低 4 位），所以 map 与 write 都必须带 `| 1 << 32`，而这条流在固件里仍指向本内核从未填过的页表，第一次读就 fault → ADSP 复位。参考实现同 SoC：`E:/k60-work/ref/pong-power/PongAudio.cpp:214-235`（UniXNU-pong，Nothing Phone 2，pin c37179e）对同一条 SID 做 `planUfsSmmu(0x1801, dmaPa, BufferBytes, read, 78, 120)` + `configureUfsSmmu`，注释写明「this stream needs physical pass-through, not a second translation of its physical addresses」；`E:/hackios/UniXNU-zizhan/drivers/PongPower/PongAudio.cpp:124-132`（MIX Fold 2，同 SM8475）用同一配方。ax 因此：① `pong_play_dsp_address()` 给 dma_pa 置 bit32，map 与 slot 写地址共用；② 新增 `pong_audio_smmu_lease(0x1801)`——按 `drivers/NativeUfs/SmmuTakeover.h` 的几何校验（IDR0 bit30、IDR2 bit12、`pages=1<<(((idr1>>28)&7)+1)`、banks≤78、count≤120）取顶部 context bank（banks-1），确认 SCTLR.M=0、CBAR=0x10000、CBA2R∈{0,1} 后写 CBA2R=1、CBAR=0x10000、S2CR=`bank`、SMR=`0x80000000|0x1801` 并逐项回读；③ 新增只读 `pong_audio_smmu_audit()` 打印 sCR0/IDR0/IDR1/IDR2/sGFSR 与最多 24 条 SMR/S2CR，并对 0x1800/0x1801/0x1001 做掩码匹配查找；④ token 回到 Pong 的 `0x10000000 | sequence`。`ml_io_map` 每次只映射 4 KiB 并缓存最多 3 页（io_submap 预算，P-63）。宿主 `TESTS OK 979 cases`；`check-patch-apply.py --all` 313；0001 131,989 B/3,493 行/`d4ed7ab7…`。

**ax 真机与 ay（2026-11-19 01:20）**：ax（boot.img `2992f7df…`，证据 `E:/k60-work/evidence/audio-probe-ax/run1-20261119-0100`）的审计给出决定性事实——`SMMU stream 0x1800/0x1801/0x1001 -> smr[3] s2cr=0x00000003 type=0 bank=3`，三条流都被同一个**掩码组**（slot 3）接走；租约按顶部 bank 74 检查时回 `SMMU bank 74 already serves stream 0x0e0`（UFS 的 SID 已占用该 bank），于是拒绝租约；随后 `playback graph started without the speaker; streaming the slots anyway` 之后再无一行，与 aw 完全相同 → 写路径仍走掩码组指向的 bank 3 页表，物理地址在 DSP 侧照样 fault。ay 因此改两处：① 掩码组只在 SMR 索引更低时才被超越，所以 slot 取最低空闲项且必须低于任何匹配的掩码组（否则打印 `no idle stream group below %u` 并放弃）；② bank 从顶部向下最多试 8 个，逐个要求 SCTLR.M=0、CBAR=0x10000、CBA2R∈{0,1} 且没有 SMR 指向它；若该流已有精确（mask=0）SMR，则复用其 slot 并把 S2CR 指到新 bank。0003 现为 36,602 B/1,144 行/sha256 `f14115703b03daefd2c059513ae1f0000ef8596e005472018753fa0655ee822b`。

**镜像 ay 与 az（2026-11-19 02:10）**：ay（boot.img `e9eaa52a…`，证据 `E:/k60-work/evidence/audio-probe-ay/run1-20261119-0200`）把 tagged 地址同时用于 map 与写：1558 审计回 `sCR0=0x00260406 IDR0=0x4c017e71 IDR1=0x6000004b IDR2=0x00005111 sGFSR=0x00000000`、`audit smrs=113 valid=3 banks=75`，三条音频流仍由 slot 3 的掩码组接走；1566 租约被拒 `SMMU lease refused: no free context bank below 75`（顶部八个 bank 都被引用）。随后隔离探针照旧、playback START 回 0，1580–1587 四次 `PCM slot N send begin` 与 `PCM slot N submit … address=0x1dd4f4000/0x1dd4f6000/0x1dd4f8000/0x1dd4fa000`，1588 `playback stream primed slots=4 inflight=4`，之后 console 直接结束：**DSP 一次应答都没有**，AP 在毫秒级死亡。ax 与 ay 的差别只有 tagged 地址与失败的租约，而 sCR0 的 SMMUEN 为 0、掩码组本身是 bypass 形态，所以 apps SMMU 不是死因；剩余假设收敛到 ADSP 侧 XPU/VMID 保护与命令路径本身。stock 的音频缓冲来自 `sdsp_region`（`shared-dma-pool`、可复用、4 MiB 对齐、12 MiB，live-fdt.dts:369-376）经 `qcom,adsp` dma-heap（live-fdt.dts:18691-18695）分配，并用 SCM `hyp_assign_phys` 把页从 `VMID_HLOS` 转给 `VMID_LPASS`/`VMID_ADSP_HEAP`（`vendor-src/kernel-sm8450-modules/qcom/opensource/audio-kernel/dsp/msm_audio_ion.c:723-754`），而我们的缓冲只是 UEFI 在 4 GiB 以下随便分配的保留页（0xdd4f4000）。az 因此先加诊断：`PCM pump running`、`PCM reap enter/exit`、`PCM submit after start`，以及每个静默 return 的打印；同版还发一次零字节写（`PCM zero-byte probe send/rc`），让 DSP 在不读缓冲的前提下应答、拒绝或死亡，从而把「命令路径」与「读内存」分开。0003 现为 39,500 B / 1,236 行 / sha256 `60030042…`。


**镜像 ba（2026-11-19 02:42）**：ba（boot.img `5e918ea59977ba759cdfb2f6df0436652a68e076b89f43c6a13d69b53bbd17a6`，证据 `E:/k60-work/evidence/audio-probe-ba/run1-20261119-0245`，capture 103,334 B / logSha256 `A3632E227BE1C9E382500FB21E7AB0BFC3898BF3582AA619D52D7C163E4454E9`）把诊断（pump/reap/submit after start）与零字节写探针带进实机：1629 `PCM lead reached frames=15360`，1630 审计 `sCR0=0x00200406 IDR0=0x4c017e71 IDR1=0x6000004b IDR2=0x00005111 sGFSR=0x00000000`（SMMUEN 仍为 0），1635–1637 三条音频流都由 slot 3 的掩码组接走，1638 `SMMU lease refused: no free context bank below 75`；1640/1642 两条 PREPARE 回 status=0，1646 isolation probe 跳过 speaker START，1645 playback START（opcode `0x01001002`，token `0x0003000b`）回 status=0，1647 打印 `playback graph started without the speaker; streaming the slots anyway` —— **console 到此结束**：既没有 `PCM pump running`、也没有 `PCM submit after start`，更没有零字节探针的 send/rc 行。对照 aw（同一条隔离路径，但当时没有诊断）在同一行之后还能看到 `PCM slot 0 copy begin/copy done`，说明 ba 这次死得更早：不是写命令，而是 playback graph 一旦真正跑起来就没了。因此 bb 把零字节写从 `begin_stream` 提前到 playback START 完成处（`pong_audio_play_complete_step` 的末步分支），并把 `pong_audio_submit()` 的 pump 提前到 ring 容量检查之前：即使生产者把 ring 灌满，消费者仍会清槽，零字节写也一定会在任何真实周期之前发出，命令路径与内存访问就能在一次 boot 内分开。镜像 bb（2026-11-19 03:15，boot.img `b0e3289764260f1c20452a8b8e47f2bdf0014f397dd3e350885ad8f8ad1c8691`，证据 `E:/k60-work/evidence/audio-probe-bb/run1-20261119-0315`）在真机上走到 580 `playback graph mapped; waiting for PCM lead` 就再没有 PCM 行：1628 `PCM submit n=1 frames=1024 used=1024 running=0 inflight=0`，随后的 HAL 自检 `selftest complete frames=64512 read=64512` 正常收尾，系统活满 300 s。判读：submit 的两处 pump 被 `if (playback_running)` 挡住，而 lead 恰恰是由 pump 检查并发送两条 PREPARE 与 START 的，于是永远到不了 START，零字节探针也就没机会发出。bc 因此把这两处 pump 改回无条件调用（探针仍留在 START 完成处），这样第一次 submit 就能把 lead 推过阈值、发出 START，并在 START 完成时立刻发零字节写。
**镜像 bm 真机与 bn（2026-11-19 11:33）**：bm（boot.img `8daee1ae031c9c28e43601bb2852168393846ee6de22f8e1ce957171deb72bc9`，证据 `E:/k60-work/evidence/audio-probe-bm/run1-20261119-1133`；console 1,606 行、100,243 B、`logSha256 37C0AE9147F87F03423DC56D72081A977768A09B81B72548AED4DEFC47365B3B`、state=captured-disconnected、complete=false、panicMarker null、resetMarker null、lastDataAt 11:35:03.086，启动 11:33:37 ⇒ 又是 86 s)。尾部序列：`SMMU lease refused: no free context bank below 75`（候选 bank 只扫 8 个，bn 修正）；step 7/8 PREPARE 各收到 echoed=0x01001001；`pair START follows the playback prepare`；step 9 `send bytes=72 opcode=0x01001002 token=0x00030009` → rx status=1、`refused status=1`、`skipped, continuing`；step 10 `send bytes=64 token=0x0003000a` → rx status=0；step 11 `send bytes=64 token=0x0003000b` → rx status=0；`playback graph started; PCM streaming` 之后 console 直接结束（缓冲尾部丢失），既没有 `amp0/1 play` 行，也没有 bm 新加的 `SCM lend begin` 行。判读：恢复成对 START 后扬声器第一次被真正接受（step 10/11 都是 status=0，bj 的经验是删掉成对 START 后单发 speaker START 必被 status=1 拒绝）；但真实周期仍在启动后 86 s 把整机带走，尾部又被截断，所以 bm 没能回答「第三次 SMC 是否悬死」。bn 因此改走 pong/zizhan 的原始路线：`E:/k60-work/ref/pong-power/PongAudio.cpp:214-233` 的 `setupDma()` 只把 UEFI 低区 DMA 交给 `planUfsSmmu(0x1801, dmaPa, BufferBytes, …, 78, 120)` + `configureUfsSmmu()`，注释写明「SID1801 physical pass-through bank」，全程没有任何 hyp_assign/SCM 过户；zizhan 同样（`E:/k60-work/ref/zizhan/drivers/PongPower/PongAudio.cpp:128`）。bn 只改 0003：① 候选 bank 扫描从 `i < 8u`（banks=75 时只看 74..67）改成 `i + 2u < banks`，从最高 bank 一路往下；② 拒绝前新增诊断，打印最高 12 个 bank 的 `PongAudio: SMMU bank %u sctlr=0x%08x cbar=0x%08x cfg=0x%08x used=%u`；③ `g_pong_smmu_leased` 提前到提交路径之前；④ 四处 SCM 调用（提交 lend、探针 lend、WRITE_DONE reclaim、超时 reclaim）全部加 `!g_pong_smmu_leased &&` 前置条件——SMMU 旁路成功就不再过户，失败才回到逐周期借贷；⑤ 启动行改成 `PCM slots stay HLOS-owned; the SMMU bypass or a per-period lend carries them`。0003 = 49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`；真实前像 apply OK（产物 2,420 行）、313 补丁可解析。

**镜像 bl 真机与 bm（2026-11-19 10:50）**：bl（boot.img `68f7380a2891fad1b42a5e42f880a69b0ec1ad05bac03dc255fa2c921c75d868`，证据 `E:/k60-work/evidence/audio-probe-bk/run1-20261119-1050`，目录名沿用了 watcher 模板的 bk 基名；console 1,733 行、108,009 B、`logSha256 D47ED318A91A0AFF584D46E2DE5CE30A2CF763AA20E43A9CA5F5123376A218CF`、state=captured-disconnected、complete=false、panicMarker null、resetMarker null）。这次把整块 64 KiB 缓冲按周期借出：1712 `playback graph started without the speaker`；1713 `SCM lend pa=0xdd4f4000 bytes=0x10000 rc=0`（零字节探针也借整块）；1714/1715 探针 `send` 后的 `rc=0 inflight=1`；1726 `glink adsp_apps rx bytes=56 kind=3 opcode=0x05001004 token=0x10000000 status=0 src=2:0x6001 dst=3:0x2001`（DSP 回 WRITE_DONE）；1727 `SCM reclaim pa=0xdd4f4000 bytes=0x10000 rc=0`；1728 `PCM write done slot=0`；1732 `PCM slot 0 copy begin va=0xfffffff7520c5000`；1733 `copy done` —— console 到此为止：没有第二条 `SCM lend`、没有 `send begin`。判读：内核的 memcpy 本身成功（copy done 已经打印），死在 copy done 之后、第一条真实周期的借贷结果之前。首要假设是第三次 SMC 悬死——`smc #0` 不返回，看门狗直接把整机复位，所以既没有 panic 行也没有断开前的日志；另一种可能是该打印在死前没来得及刷出，或 DSP 真去读这 8 KiB 时被带走。旁证：探针的 lend/reclaim 从 `pong_audio_play_complete_step()`（GLINK 接收上下文）发起并正常返回，而真实周期的 lend 从 submit 路径发起；且 reclaim 目前把 HLOS 权限设成 7=RWX（stock UNMAP 也是 RWX），第二次 lend 的源 VM 因此带着 execute 位。bm 因此一次做三件事（只改 0003）：① `pong_audio_scm_transfer()` 在 SMC 之前打印 `PongAudio: SCM %s begin pa=0x%llx bytes=0x%llx src=%u dst=%u`，用来区分「SMC 悬死」与「打印丢失」；② reclaim 的 HLOS 权限从 7 改成 `PONG_SCM_PERM_RW`（6，读写就够拷贝用），排除 execute 位导致第二次 assign 异常；③ 恢复 av 的启动顺序——`PongPlayPreparePlayback` 之后先发 `PongPlayStartPair`（打印 `pair START follows the playback prepare`），被拒仍走既有 skip 逻辑继续 step 10/11，让 TDM 扬声器真正起来、之后 `pong_audio_amp_play()` 才会被调用。0003 = 49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`；真实前像 apply OK（产物 2,381 行）、313 补丁可解析。

**镜像 bk 真机（2026-11-19 10:21，逐周期过户首次跑通）与 bl**：10:21:52 的启动 `bootAccepted=true`、`bootExitCode=0`，证据 `E:/k60-work/evidence/audio-probe-bk/run4-20261119-1040`（console 108,646 B、`logSha256 D059517B…`、`lastDataAt 10:23:24.65`、`finishedAt 10:23:57`、`panicMarker null`、`state=captured-disconnected`）。这次 ADSP 活着：1581 `PongAudio HAL: StartIO result=0`；1588 `PCM lead reached frames=15360`；1625 `speaker START follows the playback prepare`；1645 `PongAudio: SCM lend pa=0xdd4f4000 bytes=0x2000 rc=0`（零字节探针借出 slot 0）；1650 `PongAudio: SCM reclaim pa=0xdd4f4000 bytes=0x2000 rc=0`；1651 `PongAudio: PCM write done slot=0 address=0x1dd4f4000`；1666 pump running；1680/1700 reap enter/exit；1715 `PCM slot 0 copy begin`；1716 `copy done`；1717 `PongAudio: SCM lend pa=0xdd4f4000 bytes=0x2000 rc=0`；1718 `PongAudio: PCM slot 0 send begin bytes=68`，console 到此为止。
判读：**逐周期过户的借贷/归还链路第一次完整跑通**——探针借方字节写、DSP 回 `0x05001004`、reclaim 归还，全部 rc=0；但第一条真实周期只把 8 KiB 的槽过户，而 shared-memory 映射覆盖整个 64 KiB 缓冲，DSP 处理写时校验整块区域，于是 send 之后整机再次复位（这次没有 panic 行，`panicMarker null`，与 bg 的 data abort 不同）。也就是说：逐周期借贷**不是**错在 HLOS 写入时机（memcpy 在借出之前完成、页面当时归 HLOS），而是错在**借出的范围**。
同一镜像里还补了一处：`pong_audio_play_reap_slots()` 的超时分支原本只清槽、不归还页面，整缓冲借贷之后那会让下一次 memcpy 直接 external abort；现在超时分支先 `pong_audio_scm_reclaim()` 再清槽（失败打印 `PCM slot %u timeout reclaim failed`）。据此的 bl 改动（只改 0003）：`pong_audio_scm_lend()` 与 `pong_audio_scm_reclaim()` 的字节数从 `PONG_PLAY_PERIOD_BYTES`（8 KiB）改为 `PONG_AUDIO_DMA_BYTES`（64 KiB），提交路径、零字节探针、WRITE_DONE 三处一致；启动打印改成 `PCM slots stay HLOS-owned; each write lends the buffer`。0003 = 49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`；真实前像 apply OK（产物 2,368 行）、313 补丁可解析、宿主 TESTS OK 979 例。

**镜像 bk 真机（2026-11-19 09:30 与 10:01）**：bk 的 boot.img 是 `beb4f7238a573a71a886f094fd85c3301dda840213ffd739ed8ed0901744205a`（kernel `46e372b358402cd8d7dc9d8be55f19845ed1b0a12692f8f85128df84bd1c959d`，verify-boot-image OK）。第一次触发在 09:30:44，boot.json 虽写同一 sha，但 `bootAccepted=false`、`bootExitCode=-1`，console（3,676 行）里只有更早镜像的打印（有 lease、无 HLOS-owned、无 SCM assign），属别的镜像在跑，那次证据作废。第二次触发在 10:01:31，`bootAccepted=true`、`bootExitCode=0`，证据目录 `E:/k60-work/evidence/audio-probe-bk/run3-20261119-1015`，console 1,000+ 行、139,260 B、`logSha256 63ACF30A…`、panicMarker `K60PANIC: ring kept`、10:03:11 断流、10:03:17 回 fastboot。
这次确实跑的是 bk：270 行 `PongAudio: PCM slots stay HLOS-owned; each write lends its slot`；538 `glink adsp_apps up`；541 APM ready；542-564 AFE 六步（step 1..5 仍 status=2 skipped，与 bc/be/bg 一致）；565 `AFE six-step complete`；567-581 playback step 0..6 全 rc=0，579 `playback map done handle=0xb0d8c0d8`；582 `playback graph mapped; waiting for PCM lead`。然后 **944 行 `PongAudio: glink adsp_apps down`**，早于任何 PCM 提交：没有 `PCM submit`、没有 `copy begin`、没有 `SCM lend`、没有 `PCM write done`、没有 `SCM reclaim`——逐周期过户一次也没跑。
ADSP 掉线立刻连锁：945 `K60Battery: GLINK epoch never became ready`；773 行 PMIC 请求超时 `op=30 property=7 responses=4 ... quarantining old channel`；775 `QcomGlink: OPEN sent PMIC_RTR_ADSP_APPS lcid=3`（健康启动是 lcid=1 且不重开）。内核侧 `pong_audio_glink_state(up=false)` 把 `service_ready` 清掉，于是 HAL 的 `PongAudio::startOutput()` 直接返回 `kIOReturnNotReady`；用户态 1512 行起 121 次 `PongAudio HAL: StartIO result=1937010544`，1937010544 = 0x73746F70 = fourCC stop = kAudioHardwareNotRunningError（PongAudioPlugIn.c:809 的 StartIO、:848 打印）。之后 console 以 `Mutex interlock[0xfffffff00c3117d8] timeout after 12584383 ticks`（K60PANICARGS 2083）收尾，属掉线后的互锁超时，不是音频数据中止。
对照：bc 1525 / be 1545 / bg 1670 / bi 1549 全部 `StartIO result=0` 且随后有 `PCM lead reached frames=15360`，而且这四次的 console 里没有 `glink adsp_apps down`、PMIC 通道是 `lcid=1` + `adopting authenticated PAS1 GLINK epoch=1` + `channel up`。09:30 那次跑的是更早的镜像，却在 943 行同样出现 `glink adsp_apps down` 与 lcid=3 重开 ⇒ 这次 ADSP 掉线更像启动环境/ADSP 固件状态，而不是 bk 的改动；但 bk 的核心路径仍未验证。
结论：bk 这一轮**没有测到**逐周期过户，不能记为失败；下一次上机先看 `glink adsp_apps down` 是否出现，出现就换一次干净启动（必要时先 boot be 作控制），不出现再判 `SCM lend` → `copy done` → `write done slot=N` → `SCM reclaim` 循环。

**镜像 bi 真机与 bk（2026-11-19 09:02）**：bi（boot.img `271113389015ce57710c4e1560196163e4fee85076037b5dfe3dd5d5de5667f2`，证据 `E:/k60-work/evidence/audio-probe-bi/run1-20261119-0815`，console 1,684 行，capture `state=captured`、`complete=true`、106,086 B、`logSha256 94337780C41FC9F5CC79C38B5F6D6437775CB31980CEBDC8CF48C02903D7195E`、panicMarker `K60PANIC: ring kept`）把六档目标列表全试了一遍：287–291 的五档含 HLOS 写法（hlos-first RW、RWX、全 RWX、HLOS+LPASS、HLOS+ADSP_HEAP）全部 `rc=-2`、`x0=0xfffffffffffffffe`、`x1=0x56`，292 只有 `{LPASS, ADSP_HEAP}` 一档 `rc=0`；此后 1,584 `PCM write done slot=0 address=0x1dd4f4000`（零字节探针的 WRITE_DONE `0x05001004` 到达，说明 DSP 确实读到了过户后的页），而 1,597 `PCM slot 0 copy begin va=0xfffffff1f3c56000` 之后 1,627 立刻 `K60KEXC msg=Kernel data abort. pc=0xfffffff007a98358 lr=0xfffffff0074d8414 esr=0x96000010 far=0xfffffff1f3c56000`：过户把 HLOS 从页上移走，内核自己写周期就 external abort。结论：这台固件的监视器只接受不含 HLOS 的目标列表，而那种列表让内核失去写权限，一次性过户走不通。bk 因此改成逐周期过户：`pong_audio_scm_transfer()` 统一发 7 参数调用，`pong_audio_scm_lend()`（源 `{HLOS}`、目标 `{LPASS, ADSP_HEAP}` RW）在写命令之前，`pong_audio_scm_reclaim()`（源 `{LPASS, ADSP_HEAP}`、目标 `{HLOS}` RWX）在 WRITE_DONE 的处理里，启动路径只打印 `PCM slots stay HLOS-owned; each write lends its slot`；bd 的单缓冲流控仍在，任何时刻只有一个槽在飞，HLOS 拷贝时页一定还在自己手里。
**镜像 bk（2026-11-19 08:56）**：bj 让 TDM 扬声器子图先起来，但两颗 AW88261 仍停在探针留下的 powerdown+mute 状态，PCM 通路走通也不会有声音。bk 在 `drivers/PongAudio/PongAudioAmp.c`（0001）里补上播放档：`pong_audio_amp_play()` 按主线 `aw88261.c` 的上电顺序逐颗执行——清 `SYSCTRL(0x04)` 的 PWDN、等 2 ms、清 AMPPD、等 1 ms、轮询 `SYSST(0x01)` 直到 PLLS|CLKS 同时置位（位时钟由已经启动的 TDM 接口提供，没有它就保持静音并回到 powerdown）、置 `I2SCFG1(0x13)` 的 I2STXEN、清 ULS_HMUTE、把 ACF 的音量写回 `SYSCTRL2(0x05)` 并清 HMUTE、连读两次 `SYSINT(0x02)` 清中断；`pong_audio_amp_stop()` 按相反顺序（清中断、ULS_HMUTE、−90 dB 音量并置 HMUTE、关 TXEN、等 1 ms、置 AMPPD、置 PWDN）。探针把引擎与两颗芯片的状态记进 `amp_ready/amp_found[]`，播放档不再重走 GENI/GCC/TLMM。0003 在 playback graph START 完成、且 speaker 子图已启动时调用一次 `pong_audio_amp_play()`（`play_speaker_started` 为假就不解除静音，因为那时没有位时钟）。补丁 0001 131,989 B，3,493 行，15 段，sha256 `d4ed7ab76c5c4960ad4e12629f748b77502333e83a1d956955546c3bc614e866`；0003 49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`。
**镜像 bj（2026-11-19 08:29）**：bi 的 SCM 阶梯解决页面归属后，扬声器还缺一步。au 里把 speaker 与 playback 两个子图放进同一条 GRAPH_START 被 DSP 以 status=1 拒绝，而 av 里分别单发 START 都是 status=0，因此 bj 在 `PongPlayPreparePlayback` 完成后先发 `PongPlayStartSpeaker`（`AR_SG_SPEAKER 0x4005`），收到完成再发 `PongPlayStartPlayback`；被拒时仍按原 `play_skips` 逻辑跳过并继续，不会阻塞 PCM 通路。补丁 49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`。

**镜像 bh 真机与 bi（2026-11-19 07:39）**：bh（HEAD `63b0ecc5`，boot.img `309301bc…`，证据 `E:/k60-work/evidence/audio-probe-bh/run1-20261119-0725`，console 1,629 行、capture `state=captured-disconnected`、101,730 B、`logSha256 777F5CDD…`、lastDataAt 07:41:18、`stopReason=fastboot-return`）在 287 行给出 `PongAudio: SCM assign pa=0xdd4f4000 bytes=0x10000 rc=-2 x0=0xfffffffffffffffe x1=0x56`：把 HLOS(0x03) 追加在 `{0x16, 0x25}` 之后的目标列表被监视器拒绝，页面仍归 HLOS，DSP 读不到（没有 WRITE_DONE），真实周期写后整机照旧复位。EVA 的同平台写法给出反例：`msm_cvp_dsp.c:17-21` 用 `hlosVM={VMID_HLOS}`、`dspVM={VMID_HLOS, VMID_CDSP_Q6}`、perms 全 `READ|WRITE|EXEC`，即 HLOS **可以**留在目标列表里，但列表必须升序且带 RWX。bi 因此把一次性调用换成变体阶梯（`pong_audio_scm_try`）：① `{HLOS,LPASS,ADSP_HEAP}` perms `{7,6,6}` ② 同序全 7 ③ 同序全 6 ④ `{HLOS,LPASS}` ⑤ `{HLOS,ADSP_HEAP}` ⑥ 最后才是已知会移走 HLOS 的 `{LPASS,ADSP_HEAP}`；每个变体打印 `PongAudio: SCM assign <label> … rc=…`，第一个 rc=0 即停，失败不变更任何状态（可安全重试）。

**镜像 bg 真机与 bh（2026-11-19 07:09）**：bg（HEAD `04ed1ad2`，boot.img `3609c3ca…`，证据 `E:/k60-work/evidence/audio-probe-bg/run2-20261119-0705`，console 1,963 行、capture `state=captured`、`complete=true`、123,460 B、`logSha256 9F27DBBE…`、`panicMarker K60PANIC: ring kept`、startedAt 07:09:17、lastDataAt 07:10:50）第一次把 SCM 过户接上：287 `PongAudio: SCM assign pa=0xdd4f4000 bytes=0x10000 rc=0 x0=0x0 x1=0x0`，即监视器接受了这 64 KiB 的 LPASS(0x16)+ADSP_HEAP(0x25) 目标列表。此后流程与 bf 相同（1,679 lead 15,360、1,680–1,690 SMMU 审计与租约拒绝、1,691–1,697 两条 PREPARE 与 playback START 都收到 `echoed`、1,698 隔离探针、1,699/1,700 零字节写 0x1dd4f4000 rc=0），但 1,703 出现整条线上**第一条 DSP 完成报文**：`glink adsp_apps rx bytes=56 kind=3 opcode=0x05001004 token=0x10000000 status=0 src=2:0x6001 dst=3:0x2001 echoed=0x0`（WRITE_DONE）。1,704 因为探针没有记账而报 `unknown slot address=0x1dd4f4000`；系统继续跑到 1,745/1,746 reap、1,748 `PCM slot 0 copy begin va=0xfffffff2bfd88000`，随后没有 copy done，K60KFRAME 转储后 `K60PANIC: ring kept; restart reason -> bootloader`。判读：过户解决了 DSP 读不了页的问题（它第一次成功读并回完成），但 assign 是**移交**而不是**出借**——stock 的目标列表只有 LPASS 与 ADSP_HEAP，HLOS 被移出后内核自己写 PCM 就 data abort。bh 因此把 HLOS(0x03, RW) 加回目标列表（count=3，`ext[2]=72`），并给零字节探针记账（`slot_busy[0]`/`slot_token[0]`/`inflight++`），让 WRITE_DONE 能匹配到槽 0、把完成路径端到端跑通。

补丁：`patches/audio/0003-k60-audio-afe-selftest.patch`（49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`）。
**镜像 bf 真机与 bg（2026-11-19 05:57）**

bf（boot.img `4302fa49bdbdeabbea7e803902fc6fd6261cc4c8777df905fe47dd61709a1bc8`，从 c57702b5 构建，证据 `E:/k60-work/evidence/audio-probe-bf/run1-20261119-0600`，console 1,600 行，capture 99,432 B / logSha256 `CB0FD0304335D95D48044C94D8CAD4407F02C2622AF420CF2BE36B7D0B125192`）把 PCM 槽搬到 SMEM 尾部，启动打印 `SMEM used end=0xbfae8` 与 `SMEM PCM buffer pa=0x80af0000 size=0x10000`。图上进程按预期走完：`PCM lead reached frames=15360`、两条 PREPARE 各收到 `rx bytes=32 kind=1 opcode=0x02001005 echoed=0x01001001`、playback START 收到 `echoed=0x01001002`、零字节探针 `send bytes=68 address=0x180af0000` 与 `rc=0 inflight=0`、`zero-byte probe answered; streaming real slots`；之后一行都没有（既无 `PCM pump running`，也无 `copy begin`/`send begin`/`submit`），capture 在 05:58:46.544 断流（启动后 86 s，panicMarker 为 null）。判读：把槽搬进 SMEM 尾部没有改变死法，首个 8 KiB 周期仍把整机带走。

注意 0504 里 `PONG_SMEM_PA 0x80900000`/`PONG_SMEM_SIZE 0x00010000`：内核只把 SMEM 窗口当成 64 KiB，而 bf 用的 0x80af0000 依赖补丁自己的 2 MiB 常量，很可能落在 DSP 的 SMEM 视野之外，所以 bf 的阴性结果不能证明「DSP 读不了 HLOS 页」不成立。

因此 bg 放弃 SMEM 覆盖（删掉 `pong_audio_smem_walk()`/`pong_audio_smem_pcm()` 与调用点），改回 loader 租约的 0xdd4f4000，并在租约成功后立刻调用 `pong_audio_scm_assign()`：把 16 页从 VMID_HLOS 转给 LPASS 与 ADSP_HEAP，这正是 stock `msm_audio_ion.c` 的 `IOCTL_MAP_HYP_ASSIGN` 对每个音频缓冲做的事。ABI 已按 LOS 5.15 源码逐字核对：`QCOM_SCM_SVC_MP 0x0c`、`QCOM_SCM_MP_ASSIGN 0x16`、arginfo `0x1117`（7 个参数，类型 RO/VAL/RO/VAL/RO/VAL/VAL），参数 = {mem_info 物理地址, 16, 源 VMID 列表物理地址, 4, 目标列表物理地址, 48, 0}；arm64 传输只把前四个放寄存器 x2..x5，参数多于四个时 x5 改成「装着 args[3..9] 的缓冲区物理地址」（`SCM_SMC_N_REG_ARGS 4`、`SCM_SMC_FIRST_REG_IDX 2`、`SCM_SMC_LAST_REG_IDX 5`、`SCM_SMC_FIRST_EXT_IDX 3`、`SCM_SMC_N_EXT_ARGS 7`），缓冲区里依次是 {4, 目标列表物理地址, 48, 0, 0, 0, 0}。结构：`mem_map_info{u64 addr,u64 size}` 16 B、`perm_info{u32 vmid,u32 perm,u64 ctx,u32 ctx_size,u32 unused}` 24 B，权限 RW=0x6，VMID HLOS=0x03 / LPASS=0x16 / ADSP_HEAP=0x25（与 DT `qcom,adsp-remoteheap-vmid = <0x16 0x25>` 一致）。调用打印 `PongAudio: SCM assign pa=… bytes=… rc=… x0=… x1=…`；若 HLOS 因此在第一次 memcpy 时失去写权限，会直接出现内核 data abort，这本身也是判据。

补丁：`patches/audio/0003-k60-audio-afe-selftest.patch`（49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`）。

**镜像 be 与 bf（2026-11-19 04:30）**

be 只发一次零字节写：`pong_audio_play_complete_step()` 在 playback START 完成后调用 `pong_audio_play_probe_zero()` 并置 `g_pong_probe_only`，`pong_audio_play_submit_slot()` 此后直接返回，真实周期一个都不发。真机（证据 `E:/k60-work/evidence/audio-probe-be/run1-20261119-0430`，console 4,242 行，capture `state=captured-budget-complete`、`complete=true`、281,894 B、`logSha256 25CF2A13…`、`lastDataAt 04:35:04`、`panicMarker=null`）：1556 `PCM lead reached frames=15360`，1573 `playback graph started without the speaker`，1574/1575 `PCM zero-byte probe send bytes=68 address=0x1dd4f4000` 与 `rc=0 inflight=0`，1576 `probe-only image; no PCM slot follows`，之后整机活满 300 秒，由 `K60AUTORESET: 300 s since boot` 自己回 fastboot。与 bc/bd 对照（同一探针之后立刻发真实 8 KiB 周期，约 21 ms 内整机死亡、DSP 零条 WRITE_DONE）可知：**命令路径、GLINK 与图启动都是好的，杀掉整机的是 DSP 真正去读我们交出的缓冲**。

bf 因此把 PCM 槽从 loader 租的低内存搬到 SMEM 尾部：`pong_audio_smem_pcm()` 在 `pong_audio_dma_lease()` 之后运行，映射 0x80900000 头 8 KiB，读 `m[19..22]` 的 heap 记录，再按 4-word 与 3-word 两种 item 布局各走一遍 512 项取较大的已用末尾，只有 `used_end + 64 KiB <= 2 MiB` 时才把 `dma_pa/dma_size/dma_va` 换成 `0x80900000 + 2 MiB - 64 KiB = 0x80AF0000`，否则保留租约并打印 `SMEM tail does not hold the slots`。同时删掉 `g_pong_probe_only` 的置位，探针后立刻发真实周期。第一次 bf 构建在 `git apply` 阶段被拒：`error: patch failed: bsd/dev/pong_audio.c:907 / patch does not apply`。原因是对 0003 做手工 hunk 重计数时把最后一段的上下文行弄丢了一行，而 `check-patch-apply.py` 只跑 `git apply --numstat`（只解析、不落盘），所以门禁全绿、构建才暴露。现在改为从真实前像重建：对原始 `pong_audio.c` 依次应用 0503、0504、0505 与 0001，再重放 0003 的改动并用 `git diff` 出包；生成的文件已用 `git apply` 在独立树上验证，与原先意图逐行一致（只去掉 fuzz 留下的一个空行）。0003 = 43,563 B / 1,344 行 / 5 段 / sha256 `9418c8e1cc01d2ecd67dd078f2f127d314cdc0b5103c4d79cd7d8beb0374ba31`。

同 SoC 参考复核：pong 与 rmx3551（Realme GT2 Pro，SM8450，Axiang-dev/UniXNU-rmx3551，从 Pong 派生）都用**同一份 64 KiB UEFI audio DMA 租约**并拿到真实 `DSP WRITE_DONE`（rmx3551 `migration/ipados18/services130-root-smmu-order.md` 明确写 USB 与音频各占互不重叠的 UEFI DMA 分区），所以 64 KiB 契约本身不是问题；sheng/asteroids/evb10 用 sheng 的 AudioProbe（SMMU bypass + 0xD0000000 低区）。全库唯一带 aw882xx 放大器的是 erhai（SM8750），其音频状态仍是 `planned`，没有可抄的成品。

**镜像 bd 与 be（2026-11-19 04:05）**

镜像 bd（boot.img `5547d8ce…`，HEAD `7ce14f40`）给槽提交加了 `inflight >= 1` 的流控，只让一个缓冲在飞。真机上它仍在 `playback graph started without the speaker` 之后立刻停住：1,620 行 console 的最后两行是零字节探针的 `PCM zero-byte probe send bytes=68 address=0x1dd4f4000` 与 `PCM zero-byte probe rc=0 inflight=0`，`PCM slot 0 send begin` 一行都没有——0 字节写被本地 GLINK 接受，随后第一次真实周期在打印前就把机器带走（capture lastData 04:07:01，起机 04:05:35，仍是一分钟出头）。与 bc 合起来：0 字节写不读缓冲，可以在 `rc` 之后存活；真实的 8 KiB 写无论带不带 tag、无论一个还是四个在飞，都必然杀死 DSP，而且 DSP 一条 WRITE_DONE 都没有回过。镜像 be 因此把探针变成唯一的一次写：`g_pong_probe_only` 置位后 `pong_audio_play_submit_slot()` 直接返回 false，图形与时钟照常启动、0 字节写照常发出、真实周期一个都不发，用一次上机分开「命令路径」与「读内存」。

补丁：`patches/audio/0003-k60-audio-afe-selftest.patch`（49,214 B，1,474 行，5 段，sha256 `fce6f9426a3784fc7efcd789de801a1523a8e407b70019ab87a3b8067e81d0fa`）。

**镜像 bc 与 bd（2026-11-19 03:35）**

bc 把零字节探针提到 playback graph START 完成处（boot.img d3a9956f…，证据 evidence/audio-probe-bc/run1-20261119-0335）：lead 15360 到达，两条 PREPARE 与 playback START 都是 status=0，随后先发一次零字节写（address=0x1dd4f4000，bytes=0），GLINK 接受 rc=0、DSP 不应答、机器不死；接着四个 8 KiB 槽全部 submit（token 0x10000001…0x10000004，tagged 地址 0x1dd4f4000…0x1dd4fa000），打印 playback stream primed slots=4 inflight=4，HAL 再提交一次后 pump 写第五个槽——console 停在 PCM slot 4 send begin b（中途截断），设备约 1 s 后回 fastboot。即：DSP 对四次真实写一条 WRITE_DONE 都没回，第五次写把整机打死；零字节写因不读缓冲而不触发。aw/av 在同一位置（prime 四个之后）死，at 更早。

bd 因此加流控：pong_audio_play_submit_slot() 在 inflight>=1 时直接返回，未收到 WRITE_DONE 之前最多只有一个 8 KiB 缓冲在 DSP 手上（0003 40,019 B / 1,241 行 / sha256 84475fad…）。若 bd 活满 300 s 且 inflight 长期为 1，则「第五个缓冲」是杀手、DSP 从未 drain；若 bd 仍在一次写后死，则任何真实写都会把 DSP 打死，方向转向缓冲归属（SCM MEM_PROT_ASSIGN 或 ADSP 自有内存）。

**ADSP/PAS1 前置（2026-11-17）**：provider 线在 K60 真机跑通 Route A，镜像 sha256 `6aa9107c30cab42bf4fd1a8555f5d622774eeb242fd79606ca2bec36226061f1`（201,887,744 B，源码提交 `f80c2e63`），console line 189 为 `K60Handoff: published authenticated PAS1 epoch=1 bytes=104 flags=15`，line 596 为电池 physical source `sample=4 … current=397mA`，owner stage 1-5 全部 rc=0；证据在 `E:/hackios/k60-adsp-handoff/docs/research/audio/ADSP-ROUTE-A.md`。这解除了等待 ADSP/PAS1 的前置，但**不等于音频线的 PCM 成功**：音频候选 q 已把 Route A 合并进同一内核（见上）；ADSP/PAS1 前置具备，但 `pcm-submit-path` 仍需一次至少一个 period 无 underrun 的测试，保持 open。

### 9.6 run 2 的判据（可执行）

Lead 定的 ⑧ 判据是四条：**PongAudioAmp 120 写 + 120 读全对**、**日志里没有 `AW882XX_TODO` 占位驱动**、
**ACF 编号与 I2C 地址按 §8.5 交叉验证**、以及回放确实跑过。它已经不是一个说法，而是
`scripts/judge-audio-capture.py --replay`：拿证据目录跑一遍，退出码就是结论。

```
wsl.exe -e bash -lc cd /mnt/e/hackios/k60-audio-merge && python3 scripts/judge-audio-capture.py --replay /mnt/e/k60-work/evidence/audio-probe-k/run1
```

不带 `--replay` 时行为与以前完全一致（只判探针），所以 run 1 的证据照旧是 SUCCESS；带 `--replay` 时把回放结论并进去，
两者按 `severity()` 取更严重者（失败 1 重于没跑 2 重于成功 0）。

| 检查 | 判据 | 抓的是什么 |
| --- | --- | --- |
| 起始行 | 每颗功放**恰好一条** `amp<N> replay start dev_index=… vcalb=… steps=60` | 同一颗跑了两遍 / 一颗没跑 |
| 编号交叉验证 | `dev_index` 必须等于 `{amp0: 1, amp1: 0}` | 按探针编号选表（§8.5 的陷阱），换了表立刻红 |
| vcalb | 不得是 `refused` | fuse 读不到却悄悄写 0 |
| 步数 | 每颗 60 条 `replay NN reg=… wrote=… read=…`，编号 0..59 齐全 | 中途放弃 / 少写一步 |
| 首尾 | 第 0 步 `0x00←0x55aa`、第 58 步 `0x50←vcalb`、第 59 步 `0x05←静音音量`（低 10 位 `0x3c0`） | 顺序被改、0x50 被当成普通表项 |
| 表选对了 | `0x06/0x07/0x0f` 三个 marker 必须等于各自那一半的值（dev0 `0x34e8/0x3020/0x5064`、dev1 `0x38e8/0x3111/0x5264`） | 两张表对调（数值只差 5 个寄存器，肉眼看不出） |
| TXEN | `0x08` 必须等于 `0x00b6` / `0x00b7`（bit6 已清） | profile 阶段把 TX 打开了 |
| 回读 | 任何一行带 `differs` 即失败 | 写进去没生效还报成功 |
| 驱动自己的账 | `amp replay done amp0=60 amp1=60 written=120 mismatched=0 failed=0` | 打印与行为不一致 |
| 占位驱动 | 任何含 `TODO` 且含 `AW882xx/aw882xx/PongAudio` 的行即失败 | 跑成了 0503 的 `AW882XX_TODO` 骨架（它由 `pong_aw882xx` 单独门控，不该出现） |

通过时最后一行是 `REPLAY VERDICT: SUCCESS - 120 writes, 120 readbacks, both halves on the right amplifier`；
不通过是 `REPLAY VERDICT: FAILED (N problem(s))` 加 N 条明细，每条点名是哪颗、哪一步、期望与实测。

无设备自检：拿 run 1（镜像 j，没有回放层）跑 `--replay` → `REPLAY VERDICT: the replay pass never ran`、退出码 2，
而同一目录不带开关仍是 `VERDICT: SUCCESS - amplifiers identified`（退出码 0）——新判据既不会把旧证据误判成失败，
也不会把「没跑」读成「跑对了」。

判据本身也有宿主单测：`scripts/tests/test-judge-audio-capture.py` 用合成日志钉住——完整回放 SUCCESS；
表对调失败并点名 `dev_index` 与那个寄存器值；单条回读不符、`written=119`、`mismatched=2`、少一条 step、
出现 `TODO` 行、`vcalb` 被 refused 全部判失败；常量（60 步、`{0:1, 1:0}`、两组 marker、`0x3c0`）也一起断言，
所以改表或改判据都过不了 `TESTS OK`。

### 9.7 一个已修掉的静默故障：GPR 的 GET_SPF_STATE 拿错了 opcode

0504 骨架里 `GPR_OP_APM_GET_SPF_STATE` 曾写成 `0x0100100D`。这个值在 ADSP 的 APM 命令表里不是「取 SPF 状态」，
而是 `APM_CMD_SHARED_MEM_UNMAP_REGIONS`（`/home/emilelu/wifi-inputs/linux/sound/soc/qcom/qdsp6/audioreach.h:62`）——
也就是说，这个包发出去不是「你起来了吗」，而是要求 DSP **解映射一段共享内存**。危险之处在于它不会明显报错：
若 DSP 接受该命令，应答仍走通用的 `GPR_BASIC_RSP_RESULT`（状态码未必非零），探针容易读成「APM 在线」；
而 AudioReach 的 graph open / set-param 全部依赖共享内存，之后的 GPR 通信才会失败，
失败点落在几百行之后，看起来与这里无关。这是推断而非实测——正因为无从在无串口的板子上区分，才用宿主断言把值钉死。

- 真值：`APM_CMD_GET_SPF_STATE = 0x01001021`（`audioreach.h:38`），应答 `0x02001007`（`:39`）；
- 同批修正的还有两处：`GPR_VERSION` `3u → 0u`（`include/linux/soc/qcom/apr.h:104` `GPR_PKT_VER 0x0`；
  版本放在 header 低 4 位，DSP 只认 0）、`GPR_OP_BASIC_RESULT` `0x02000002u → 0x02001005u`（`apr.h:108`）；
- 修正方式：`diff -u` 重生成补丁（不手写 hunk，P-155），`check-patch-apply.py` 通过（P-162），
  宿主 `afe_gpr_cases()` 用三条断言把这三个值钉死（改回旧值即红）。详见 `PAS1-AUDIO-REQUIREMENTS.md` §1.3。
