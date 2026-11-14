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

`drivers/PongAudio/`（源文件与说明，均 BSD-2-Clause-Patent）：

| 文件 | 内容 |
| --- | --- |
| `PongAudioRegs.h` | 上面全部地址/偏移/位定义，每条带来源标注（L = `live-fdt.dts`、G = `gcc-sm8450.c`、S = Pong 参考树、M = 主线 `geni-se.h`/`i2c-qcom-geni.c`、H = `hakios.speaker.c`） |
| `PongAudioPlan.h` | 探针的判定逻辑做成纯函数：pad 地址与 pad 配置字、CBCR「是否在跑」判据、GCC 四窗口路由（含 GPLL0 的 PLL 窗口）、DFS 档可用性、AW882xx 字节序与 chip id 表。无 MMIO、无内核头 → 这些判定由宿主单测钉住，而不是靠上机试 |
| `PongAudioAcf.h` | A5 的落点：AW88261 配置档（ACF）的读取与校验做成纯函数 —— 头判据、按 `dev_index + profile + kind` 定位块、两种和校验、16×16 寄存器对表、双 PA 通道映射、fuse → icalk/vcalk → vcalb。无 MMIO、无内核头，见 §8.8 |
| `PongAudioGeniI2c.h` / `.c` | Pong `GeniI2c.c` 的移植，符号改 `pong_geni_*` 避免与 Pong 副本冲突，状态机逻辑逐字保留 |
| `PongAudioAmp.c` | A1–A7 的实现：8 页 TLMM 回读 → GCC wrapper2 投票 → I2C 引脚 → SE15 引擎 → 放 reset → 只读 13 个寄存器；然后对每颗应答的功放跑一遍**回放层**（软复位 + 57 对 Music profile + fuse 算的 vcalb + 静音音量，见 §9）；每次传输前 `bus_recover()` 把可能卡死的状态机走回 Idle；boot-arg `pong_audio_probe=1` 才跑，失败只报数不 panic |
| `README.md` | 逐步骤做了什么、为什么是这个顺序、期望日志形状、上机命令、八步自评 |

补丁：`patches/audio/0001-k60-audio-amp-probe.patch`（78,394 B，2,070 行，10 段，sha256 `d85264ca07cd0f91…13d0`）+ `patches/audio/series`。

- 8 个文件**逐字**放进 `bsd/dev/`：应用后已用 `cmp` 证明与 `drivers/PongAudio/` 完全一致；
- `bsd/conf/files` 加两条对象（`bsd/dev/PongAudioGeniI2c.c standard`、`bsd/dev/PongAudioAmp.c standard`）；
- `bsd/kern/bsd_init.c` 加一段调用，锚在 0505 的 `pong_audio_bootstrap()` 之后。
- **顺序要求**：必须在 `patches/xnu/0501` 与 `0505` 之后，因为两处锚点分别由 0501（`bsd/dev/qbt/btqca.c`）和 0505（`pong_audio_bootstrap()`）建立；而 0501 又依赖 0300/0243/0340 已加进 `bsd/conf/files` 的 `k60_usblog` / `k60_uilib` / `k60_console_export` 三行。**已用真实链验证**（不是合成预映像）：在构建缓存 `.../tree/.cache/xnu-work` 的 `bsd/conf/files`+`bsd/kern/bsd_init.c` 上按 0501 → 0505 → 本补丁顺序 `patch -p1 --forward` 落地，**rc=0、无 reject**。本补丁**无 fuzz**，只有行偏移（conf/files +6、bsd_init.c +15）；链条中唯一带 fuzz 的是 0505 自身（`Hunk #1 succeeded at 1329 with fuzz 1 (offset -19 lines)`，它的锚点与该前映像有 1 行差异，与本补丁无关）。八个新文件与 `drivers/PongAudio/` 逐字节相同（`PongCodecPlan.h` 仍不在其中：内核侧还没有 `.c` include 它；`PongAudioAcf.h`/`PongAudioAmpProfile.h`/`PongAudioAmpReplay.h` **在**，被 `PongAudioAmp.c` include，见 §9）。完整 transcript 见 `patches/audio/README.md`。
- 编译核验：`PongAudioGeniI2c.c` 曾在真实 XNU bsd 构建目录里用 `-fsyntax-only` + `-DARM64_BOARD_CONFIG_PONG` + `-Werror` 过（`PASS: PongAudioGeniI2c.c`）。回放层加入后这轮**没有复现**同一核验：fakeroot 的 `usr/include` 没有 `stdint.h`，而 `mach/arm/vm_types.h:75` 要 include 它，四种 flags 变体都在 `uintptr_t` 上失败——与本次改动无关，是 flag 集合缺 include 路径。替代证据：(a) 镜像 j 的内核构建（build-manifest `kernel_built`）证明旧 5 文件在真实 kernel flags 下编译通过；(b) 回放层全部语义在宿主侧被 584/602 例单测钉住（§9.3）。不再声称 `PASS: PongAudioAmp.c`。

### 6.1 宿主单测（八步 ⑦ 的本地核验，584 例；带真实 ACF 时 602 例）

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

```
# Windows 侧没有 cc/gcc/clang（PATH 里只有 winuxcmd），必须在 WSL 里跑：
wsl.exe -e bash -lc 'cd /mnt/e/hackios/k60-audio-merge && sh drivers/PongAudio/tests/run-tests.sh'
# → TESTS OK 584 cases   (cc -std=gnu11 -Wall -Wextra -Werror)
# 带上真实 ACF（它不入库）：PONG_ACF_FILE=<aw882xx_acf.bin> sh drivers/PongAudio/tests/run-tests.sh
# → TESTS OK 602 cases
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

新增门禁 `scripts/check-repo-paths.py`（**P-191**，编号在合入 main 时改过一次：main 上的
P-183 已被另一条「网络探测失败 ≠ 没推送」占用）：任何脚本再写死主工作区路径、
或任何判定/构建脚本丢掉「从自身位置推导根」的写法，直接 FAIL；确实跨树的工具
（`pick-upstream.py` 把仓库名映射到路径、`repair-worktrees.sh` 的参数就是目标主检出）
列在 `ALLOW` 里并写明理由。

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
| `check-repo-paths.py` | ✅ 135 个脚本，2 个跨树工具已登记（P-191） |
| `check-rules.py` | ✅ **0 失败**（71 条登记 / 37 条 waiver / 执行 25 个命令，`RC=0`） |
| `check-line-endings.py` / `check-build-freshness.py` | ✅ |

`check-rules.py` 只有把 `K60_DEVICE_INPUT` 指向私有输入才是这个结果：用默认的共享
`/opt/k60/trees/usb-cdc-mainline/device` 会红 5 条（iron-4 / iron-5 / hard-33 / P-165 / P-166），
原因是那份副本还留着 BT 线的 `0507`–`0510` 四个补丁、没有 touch 线的六个探针与本补丁——
**是共享副本漂移，不是本树的问题**。判据：`diff patches/xnu/series <共享输入>/patches/xnu/series`
非空、而与 `audio-device` 的同一份 diff 为空。

`iron-5` 还要求构建输入与仓库**逐文件**一致（`sync-device-input.py --check` 检查 709 个文件），
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
# → TESTS OK 584 cases
wsl.exe -e bash -lc 'cd /mnt/e/hackios/k60-audio-merge && PONG_ACF_FILE=/mnt/e/k60-work/scratch/audio-work/refs/acf/aw882xx_acf.bin sh drivers/PongAudio/tests/run-tests.sh'
# → TESTS OK 602 cases
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
- `scripts/judge-audio-capture.py` 不需要改：`MARK_START` 是前缀匹配，`MARK_ID` 要求 `id=0x`，
  `MARK_DONE` 要求 `amp probe done found=`——回放行不会误命中。

### 9.3 宿主侧钉住了什么（584 例 / 带真实 ACF 602 例）

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
- **不碰 LPASS**：TDM/MI2S 前端与 ADSP 图是 Lead 的 PAS1 线。

这一层的意义是：等 PAS1 与 TDM 通路到位时，「写寄存器」这段不再是未验证的新代码，而是已经在设备上
跑过一遍、每一步都有回读记录的东西；剩下的只是把它接到 start 序列与音频帧上。

