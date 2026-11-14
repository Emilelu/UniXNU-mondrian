# SoundWire / LPASS 宏 — K60 (SM8475 / cape) 寄存器级事实

> 目标子系统：LPASS 宏（va/tx/rx/wsa/wsa2）、SoundWire master、LPI pinctrl
> 日期：2026-11-14
> 状态：① 同型 ✅ ② 官方 ⚠️ ③ 反编译 ✅ ④ 广域 ✅ ⑤ 方案 ✅ ⑥ 深挖 ✅ ⑦ 本机验证 ⏳ ⑧ 上机 ❌

## 1. 结论

1. **K60 上 WCD938x 的 TX SoundWire master 是 VA 宏的 `va_swr_master`，基址 0x033b0000**，
   不是独立 `tx_swr`。`tx-macro@3220000` 在 live FDT 里**没有** `tx_swr_master` 子节点（`live-fdt.dts:23421-23428`），
   而 `wcd938x-tx-slave` 明确挂在 `va_swr_master` 下（:23369-23373）。这与主线 `sm8450.dtsi` 的 cape/waipio 布局一致。
2. **SWR 控制器版本应为 v1.7**（`COMP_HW_VERSION` 读回 `0x01070000`）：DT 的 `va_swr_master` 中断对
   `<0 0x1f0 4>, <0 0x208 4>`（496/520）与主线 `soundwire-controller@33b0000` 完全对应；Pong 的判定也是
   `v17 = (version == 0x01070000)`（`PongWcd938.h:88-91`）。
3. **任何 LPASS 宏/SWR 寄存器访问之前必须先拿到 PRM 时钟投票**（`AR_HW_MACRO` + `AR_HW_DCODEC` +
   `AR_CLK_TX_CORE_MCLK 0x30c @19.2 MHz`），而 PRM 走 ADSP/GPR → **阻塞在 Lead 的 PAS1**。
4. **io_submap 全内核只有 8 MiB**（`/opt/k60/trees/lead-device/osfmk/arm/io_map.c:66` `#define IO_MAP_SIZE (8ul << 20)`），
   音频侧必须按页小窗口映射，禁止整块映射 LPASS。

## 2. LPASS 宏与 SWR master 地址（③ 反编译，全部来自 Android live FDT）

| 节点 | 物理基址 | 窗口大小 | DT 行 | 备注 |
|---|---|---|---|---|
| `lpass-cdc` | — | — | :23316-23323 | phandle 0x4bd，`qcom,lpass-cdc-version = 0x06`，`qcom,num-macros = 0x03` |
| `lpass-cdc-clk-rsc-mngr` | — | — | :23326-23334 | 8 个时钟（tx_core/rx_core/wsa_core/va_core/wsa2_core/rx_tx_core/wsa_tx_core/wsa2_tx_core） |
| `va-macro@33F0000` | **0x033f0000** | 0x1000 | :23336-23347 | `qcom,is-used-swr-gpio = 1`、`va-dmic-sample-rate = 0x927c0`(600 kHz)、`default-clk-id = 0` |
| `va_swr_master` | **0x033b0000** | 0x2000（Pong 用 0x10000） | :23349-23367 | `swr_master_id = 3`、`interrupts = <0 0x1f0 4>, <0 0x208 4>`、`swr-num-dev = 5`、`swr-num-ports = 3`、`is-always-on = 1`、`mipi-sdw-block-packing-mode = 1`、port-mapping 完整（0x22-0x2d） |
| `tx-macro@3220000` | **0x03220000** | 0x1000 | :23421-23428 | `is-used-swr-gpio = 0`、`tx-dmic-sample-rate = 0x249f00`(2.4 MHz)、`default-clk-id = 0`；**无 swr_master 子节点** |
| `rx-macro@3200000` | **0x03200000** | 0x1000 | :23430-23439 | `rx_mclk_mode_muxsel = 0x33a40d8`、`rx-bcl-pmic-params = [00 03 48]`、`default-clk-id = 5` |
| `rx_swr_master` | **0x03210000** | 0x2000 | :23441-23456 | `swr_master_id = 2`、`interrupts = <0 0x9b 4>`、`swr-num-dev = 2`、`swr-num-ports = 6` |
| `wsa-macro@3240000` | **0x03240000** | 0x1000 | :23475-23502 | **status = disabled**；`swrm-io-base = 0x3250000`、`swr_master_id = 1`、`interrupts = <0 0xaa 4>` |
| `wsa2-macro@31E0000` | **0x031e0000** | 0x1000 | :23532-23559 | **status = disabled**；`swrm-io-base = 0x31f0000`、`swr_master_id = 4`、`interrupts = <0 0xab 4>` |
| `lpi_pinctrl@3440000` | **0x03440000** | 0x17000 | :20800-20812 | `compatible = "qcom,lpi-pinctrl"`，clock-names `lpass_core_hw_vote` / `lpass_audio_hw_vote` |
| LPI slew | **0x034da000** | 0x1000 | — | Pong 的 `slew.open(0x034da000,0x1000)`（`PongWcd938.h:59-120` 第 6 步） |

> **与 phk110 的差异（不许照抄）**：phk110 的 TX SWR master 在 0x03230000、VA 宏在 0x03370000、
> LPI 在 0x033c0000、slew 在 0x0355a000（`hakios.mic.c:394-400`、:485-489）。K60 全部不同。
> **Pong 的地址与 K60 完全一致**（Pong = SM8475），可以直接采用。

### 2.1 中断号（GIC SPI）

| master | DT interrupts | 十进制 |
|---|---|---|
| `va_swr_master` | `<0 0x1f0 4>`, `<0 0x208 4>` | 496, 520 |
| `rx_swr_master` | `<0 0x9b 4>` | 155 |
| `wsa-macro` | `<0 0xaa 4>` | 170（disabled） |
| `wsa2-macro` | `<0 0xab 4>` | 171（disabled） |

## 3. SWR 控制器寄存器表（⑥ 深挖，两源交叉）

来源：`PongWcd938.h:43-58`（读写事务）+ `:88-115`（初始化/枚举）；
`/mnt/e/k60-work/references/phk110-port/drivers/audio/hakios.mic.c:405-415`（偏移名）。

| 偏移 | 名称（hakios 命名） | 用途 | Pong 用法 |
|---|---|---|---|
| 0x000 | `COMP_HW_VERSION` | 版本 | `v17 = (r(0)==0x01070000)`，否则要求 `(r(0)>>24)==2` |
| 0x004 | `COMP_CFG` | 配置 | v17: `w(4,2)` 然后 `w(4,3)`；v2: `w(4,1)`→`w(4,2)`→`w(4,3)` |
| 0x008 | `COMP_CFG2` | 使能 | `w(8,1); IOSleep(1)` |
| 0x014 | `COMP_STATUS` | 状态 | （只读诊断） |
| 0x018 | — | 使能 | `w(0x18,1)` |
| 0x208 / 0x210 | 中断屏蔽 | v17 专用 | `w(0x208,0xffffffff); w(0x210,0x1dfdfd)` |
| 0x100 | `COMP_PARAMS` | 参数 | — |
| 0x104 | `COMP_MASTER_ID` | master 号 | — |
| 0x200 | `INTERRUPT_STATUS` | 中断状态 | — |
| 0x308 | 中止 | 读事务出错时 | `w(0x308,1)` |
| 0x500 | `ENUMERATOR_CFG` | 枚举使能 | `w(0x500,1)` |
| 0x504 | `ENUMERATOR_STATUS` | 枚举状态 | — |
| 0x101c | `MCP_FRAME_CTRL_BANK0` | 帧控制 | `w(0x101c,(1<<3)|7)` |
| 0x1044 | `MCP_BUS_CTRL` | 总线 | v17: `w(0x1044,4)` |
| 0x1048 | `MCP_CFG` | 配置 | `w(0x1048,(r(0x1048)&~(0x1f<<17))|(0x1f<<17))` |
| 0x104c | `MCP_STATUS` | 状态 | — |
| 0x1090 | `MCP_SLV_STATUS` | 从设备位图 | `status=r(0x1090); for(n=1;n<12;n++) if((status>>(2*n))&3)` |
| 0x530+8n / 0x534+8n | 设备 ID 低/高 | 枚举结果 | `id = r(0x530+8n) | (r(0x534+8n)<<32)` |
| 0x314 | — | v17: `w(0x314,7)`；v2: `w(0x314,7|(1<<31))` | |
| 0x320 / 0x328 / 0x334 | `readCommand` / `fifoStatus` / `readFifo` | **v1.7 的读事务寄存器组** | v17 时 Pong 覆盖默认值（默认 `0x5024/0x5050/0x5040`） |
| 0x5004 / 0x5008 / 0x5060 / 0x5064 | — | v2 专用 | `w(0x5060,1)`、`w(0x5008,0xffffffff)`、`w(0x5004,0x1ffff)`、轮询 `0x5064` |

### 3.1 读事务（`PongWcd938.h:43-58`，逐字语义）

```
id = (++transaction % 14) + 1
fifo = swr.r(fifoStatus);  if (((fifo >> 8) & 31) >= 8) return false;      // FIFO 满
swr.w(readCommand, (1u<<24) | (device<<20) | (id<<16) | reg);
轮询 (swr.r(fifoStatus) >> 16) & 31 直到非零，然后 value = swr.r(readFifo)
校验 ((value >> 8) & 15) == id，否则 swr.w(0x308,1) 中止
20 ms 超时
```

> ⚠️ `readFifo` 读回值的位域（`(value>>8)&15 == id`）说明 FIFO 里打包了 transaction id；**具体字节序未在
> 本机证实**，上机时必须先做「读一个已知寄存器（如 `COMP_HW_VERSION`）并打印原始 32 位」的只读验证。

## 4. 时钟投票链（⑤ 方案的关键前置）

| 层 | phk110（SM6375，APR/AFE） | Pong / K60（SM8475，AudioReach PRM） |
|---|---|---|
| 宏块时钟 | `AFE_CMD_REMOTE_LPASS_CORE_HW_VOTE_REQUEST 0x000100f4`（`hakios.mic.c:239-241`），block 3 = `LPASS_HW_MACRO`、block 4 = `LPASS_HW_DCODEC`（:14-15） | `ar_prm_vote(...,AR_PRM_IID,token,block,1)` + `AR_OP_PRM_REQUEST 0x0100100F`；`AR_HW_MACRO 1`、`AR_HW_DCODEC 2`（`ShengAudioReach.h`） |
| 时钟 | AFE clock `0x30c`/`0x30d` @19.2 MHz | `ar_prm_clock_attr(...,AR_CLK_TX_CORE_MCLK 0x30c,19200000,...)`，参数 iid `0x0800102C`（audio hardware clock）；core vote 参数 iid `0x08001032` |
| 投票顺序 | — | `prmBlock(MACRO)` → `prmBlock(DCODEC)` → `prmClock(0x30c,19.2M)`，**三步都成功之后**才映射宏寄存器（`PongWcd938.h:59-120` 第 3-6 步） |
| 失败语义 | — | 「SM8475 PRM must acknowledge both macro requests before any LPASS macro/SoundWire access」；`va_macro qcom,default-clk-id = 0` 选的是 TX_CORE_CLK，**不要单独要求 VA 时钟分支**（Pong 注释：294 版被 DSP 真实拒绝） |

**结论：LPASS 侧一切寄存器读写在 ADSP/GPR 起来之前都做不了。** 这不是本子任务能绕过的，必须等 Lead 的 PAS1。

## 5. LPI 引脚配置（⑧ 上机前必须做对的一步）

Pong 的写法（`PongWcd938.h:79-81`）：

```
pins[]   = {0, 1, 2, 14};        // gpio0 = SWR TX clock, gpio1/2/14 = data0/1/2
shifts[] = {0, 2, 4, 6};
for i: old = lpi.r(pins[i]*0x1000);
       lpi.w(pins[i]*0x1000, (old & ~0x3fu) | (1u<<2) | (i ? 2u : 0u));   // function 1 + data bus-hold
slew 寄存器 0 里对应 2 bit 置 1
```

phk110 的等价物（`hakios.mic.c:485-489`）用 `lpi_slew = 0x0355a000`、`swr_pins = {0,1,2,14}`，语义相同。

这段顺序**已经落地**为 `drivers/PongAudio/PongCodecLpi.{h,c}`：五步状态机，step 0–3 逐个读改写 pad，
step 4 写一次 slew，里面不等待。pad 与 slew 是两个映射（`0x03440000` / `0x034da000`），所以回调是两对，
不是一对——一对的话一次 slew 写就会落到 pad 0 上。宿主单测 `lpi_cases` 钉住顺序、写次数与两个配置字。
**K60 的 LPI 基址是 0x03440000（Pong 一致），slew 是 0x034da000（Pong 一致）。**

> ⚠️ 注意 `live-fdt.dts:23336` 的 `va-macro` 有 `qcom,is-used-swr-gpio = 1`，而 `tx-macro` 是 `0`：
> 即 **SWR GPIO 由 VA 宏占用**。这与「TX SWR master 挂在 VA 宏下」是同一件事的两种表述，互为佐证。

## 6. `fs-gen-sequence` 与宏寄存器序列

DT（`live-fdt.dts:23326-23334`）：`fs-gen-sequence = <0x3000 1 1 0x3004 3 3 0x3004 3 1 0x3080 2 2>`。

Pong 在 SM8475 上实际写的（`PongWcd938.h:84-86`）：

```
va.w(0x00, va.r(0x00) | 1);            // MCLK_CONTROL: 使能
va.w(0x04, va.r(0x04) | 3);            // FS_CNT_CONTROL
va.w(0x04, (va.r(0x04) & ~2u) | 1);
va.w(0x80, va.r(0x80) | 2);            // TOP_CFG0
va.w(0x08, va.r(0x08) | 2);            // SWR_CONTROL
va.w(0x08, va.r(0x08) | 1);
va.w(0x08, va.r(0x08) & ~2u);
tx.w(0x00, tx.r(0x00) | 1);            // TX MCLK_CONTROL
tx.w(0x04, tx.r(0x04) | 1);            // TX FS_CNT_CONTROL
```

偏移命名（`hakios.mic.c:405-415`）：TX macro `MCLK_CONTROL 0x000`、`FS_CNT_CONTROL 0x004`、`SWR_CONTROL 0x008`、
`TOP_CFG0 0x080`、`SWR_CTRL 0x088`、`FREQ_MCLK 0x090`、`SWR_AMIC0_CTL 0x0d0`、`SWR_AMIC1_CTL 0x0d4`；
VA macro `MCLK_CONTROL 0x000`、`FS_CNT_CONTROL 0x004`、`TOP_CFG0 0x080`。

> **这是「用法级」序列，不是 vendor 完整序列**：读-改-写依赖寄存器复位值，而 K60 的复位值未实测。
> 上机第一步必须**先只读打印这些寄存器的原始值**，再决定是否照抄。

这段顺序**已经落地**为 `drivers/PongAudio/PongCodecMacro.{h,c}`，并且正是按上面那条警告设计的：
九步是一张表（宏 / 寄存器 / 清哪些位 / 置哪些位），每步都重新读，且把**读到的旧值与写回的新值**都记下来
（`old[9]` / `now[9]`）。首次上机因此可以直接打印「这一步读到的复位值是什么」，而不是照抄一个假设。
VA 与 TX 是两个映射，回调也是两对；顺序仍是 VA 先、TX 后，`SWR_CONTROL` 的置位与清位在 VA 内部完成。

## 7. io_submap 预算（P-58/P-59/P-63 的教训）

- `IO_MAP_SIZE = 8 MiB`（`/opt/k60/trees/lead-device/osfmk/arm/io_map.c:66`），`kmem_suballoc` 在 :76，
  `ml_io_map` 走 :128，空间不足直接 panic（`KERN_NO_SPACE`）。
- **`io_map()` 自己处理未对齐地址，但按整页记账**（`io_map.c:95-99`、`:141` 逐字）：
  `start_offset = phys_addr - trunc_page(phys_addr)`、`alloc_size = round_page(size + start_offset)`，
  函数末尾 `return start + start_offset;`。所以「请求 0x1000」实际从 8 MiB 里拿走**一整页**（arm64 页 = 16 KiB），
  返回的指针已含页内偏移。按 4 KiB 记账会把预算低估 4 倍——这是本表此前的错误，已改。
- 已占用：usblog ≈ 2 MiB、touch ≈ 0.7 MiB（同一套记账规则）。

已落地的功放探针（`drivers/PongAudio/PongAudioAmp.c`，代码里的实际映射）：

| 窗口 | 请求 | 实占（16 KiB 页） |
|---|---|---|
| TLMM 8 个 pad（GPIO 1/3/43/52/56/57/63/88） | 8 × 0x1000 | 128 KiB |
| GCC 三窗口（0x2e000 / 0x33000 / 0x62000） | 3 × 0x1000 | 48 KiB |
| GENI SE15（0x880000） | 0x4000 | 16 KiB |
| 合计 | | **192 KiB = 0x30000** |

可省未省：GPIO 0–3 落在同一个 16 KiB 页里，1/3 各映一次等于重复占用；改成按页去重可省 32 KiB，
但那是优化，不属于只读探针的目标。

未来 codec 侧（等 PRM/ADSP 解除阻塞后才映射）：

| 窗口 | 物理基址 | 请求 | 实占 |
|---|---|---|---|
| va_macro | 0x033f0000 | 0x1000 | 16 KiB |
| tx_macro | 0x03220000 | 0x1000 | 16 KiB |
| va_swr_master | 0x033b0000 | 0x2000 | 16 KiB（Pong 用 0x10000，浪费 48 KiB，不建议） |
| lpi_pinctrl | 0x03440000 | 0x17000 | 96 KiB（0x17000 向上取整到页） |
| slew | 0x034da000 | 0x1000 | 16 KiB |
| 合计 | | | **160 KiB = 0x28000** |

两段合计 **352 KiB**，在 8 MiB 内仍有充裕余量（对比 0504 骨架曾要 2 MiB 的 SMEM 窗口把总占用顶爆）。

## 8. 待实测清单（⑧ 上机时要回答的问题）

1. `swr.r(0x000)` 读回 `0x01070000`（v1.7）还是 `0x02xxxxxx`（v2）？→ 决定用哪套 FIFO 寄存器。
2. `va_macro` 的 `MCLK_CONTROL/FS_CNT_CONTROL/TOP_CFG0/SWR_CONTROL` 复位值是多少？
3. `MCP_SLV_STATUS(0x1090)` 是否出现 WCD938x 的枚举位？设备 ID 是否 `0x000d01170223`？
4. `readFifo` 的字节序与 transaction id 位置（先读 `COMP_HW_VERSION` 打印原始 32 位）。
5. LPI GPIO0/1/2/14 的 function 是否已经是 1（Android 退出时可能已配好，不要盲目重配）。

## 9. 阻塞点

- **一切 LPASS 寄存器访问都阻塞在 PRM 投票 → ADSP/PAS1（Lead）。**
- 已经能落地的是**顺序本身**：`drivers/PongAudio/PongCodecSwr.{h,c}` 把 §3.1 的读事务写成状态机
  （版本判定 → FIFO 满则拒绝且不写命令 → 写命令 → 轮询 → 校验事务号 → 收数据/中止），并在读到版本之后
  补上参考实现那段控制器初始化（两版本共有 + v1.7 / v2 各自追加，v2 还要等 `0x5064` bit0）；
  `PongCodecLpi.{h,c}` 负责 §5 的四个 pad 与 slew 的写入顺序。
  `PongCodecPlan.h` 提供寄存器号与判定，宿主单测（当前 584 例中的 `swr_cases`、`lpi_cases`、`macro_cases` 与 `probe_cases`）钉住全部转移。
  `PongCodecProbe.{h,c}` 把这三段与枚举、slave id、codec identity 串成一条可逐步推进的启动序列；
  三票（macro / dcodec / `0x30c`）不全时它一个寄存器都不碰。顺序已全部落地，只差真正的回调。
  **它们不碰 MMIO**：真正的 `read/write` 回调要等 PAS1 起来、拿到 PRM 投票之后才能接上。
- 本文件只交付「地址/寄存器/时序的形状」，不交付「可运行的 SoundWire 驱动」。
  可运行的只读部分在 `drivers/PongAudio/`（见 `AMPS.md`，纯 AP 路径，不碰 LPASS）。
