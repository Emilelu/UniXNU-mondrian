# 27 板上的 hw_init：sheng 的 `gpuHwInit()` 去哪了，缺的是什么

来源与范围：`E:/hackios/UniXNU-sheng/package/GpuPowerProbe.cpp`（sheng 板，A740/SM8550）、
`E:/hackios/xnekom-ios27/drivers/PongAdreno/`（27 板，A730/SM8475）、
`E:/hackios/k60-gpu-27/drivers/PongAdreno/`（16.6.1 线，同 A730）。三棵树都在本机。
本文只回答一件事：**把 hw_init 从 sheng 搬到 27 板，要搬什么、27 已经有什么、缺的那一段在 27 上会怎样**。

## 0. 结论

1. **「搬运 gpuHwInit」这个前提不成立。** 27 板自己的
   `drivers/PongAdreno/PongAdrenoCp.cpp:213 hardware_init()` 已经在核内把 sheng
   `GpuPowerProbe.cpp:1567 gpuHwInit()` 的同一份序列跑完了，且有 9 处按 A730 修正或更严
   （见 §2）。所以这一项不是「缺代码」，是「两份实现的一致性没人逐条比过」。
2. **真正缺的是一段，不是一份：** sheng 有 `gpuRestart()`（`GpuPowerProbe.cpp:1627`，在
   `:1640` 重跑 `gpuHwInit()`，并在 `:1774` 把重启钩子交给 submit 层），27 侧
   `grep -rn "gpuRestart\|recover\|RBBM_SW_RESET_CMD" drivers/PongAdreno/` 在实现文件里零命中，
   `hardware_init()` 只有一个调用点 `PongAdrenoCp.cpp:372`。⇒ hang 之后 27 没有复位重跑的路径。
3. **`RBBM_CLOCK_*` 在 27 上只有一个写入者**：`hardware_init()` 里的
   `PongAdrenoCp.cpp:252`（53 条 leaf 表）+ `:255`（顶层使能 + 回读校验）。启动之后没有任何路径
   再写这批寄存器。16 线「只投一次启动票」的形状在 27 上同样存在（§3），差别是 27 多了
   运行期调档 `gperf` → HFI 30 和一条真正的 GPU 中断拥有者（§5）。
4. 一条会改变排期的读数：27 侧 `PongAdrenoGmemBytes=0x200000`（2 MiB，`PongAdrenoGmu.h:19`），
   而 sheng 写的是 16 MiB 基址上的 3 MiB UCHE GMEM 窗口（`GpuPowerProbe.cpp:1586-1587`）。
   27 **故意不写**这个窗口（`PongAdrenoCp.cpp:234-236` 注释：gen7_4_0 的
   `uche_gmem_alignment=0`）。因此「把 sheng 的 GMEM 窗口搬过来」在 27 上是**倒退**，
   不是补齐。

## 1. 27 侧的调用链（谁在什么时候跑 hw_init）

| 顺序 | 位置 | 做什么 |
| --- | --- | --- |
| 1 | `PongAdrenoCp.cpp:372` | `if(!hardware_init()){note("CP hardware initialization failed",1);return kIOReturnIOError;}` —— 唯一调用点 |
| 2 | `PongAdrenoCp.cpp:213-267` | `hardware_init()` 本体：寄存器序列 → hwcg → pwrup 列表打包发布 |
| 3 | `PongAdrenoCp.cpp:397-401` | `gpu->irq.attach(&gpu->ops.registers)`；`armcpu_spi_attach(332,false,interrupt,…)`；`gpu->irq.programMask(nullptr)`；`gpu->irq_attached=true` |
| 4 | `PongAdrenoPlatform.cpp:557` | boot-arg `gperf` → `PongAdrenoGmuVotePerf` → HFI 30（`PongAdrenoGmu.c:260`），运行期调档 |

sheng 对应：`gpuHwInit()` 在 `:1702`（bring-up）与 `:1640`（重启）各调一次；
中断在那棵树里没有拥有者（`GpuPowerProbe.cpp:1616` 注释「Nothing services the GPU interrupt
yet; status is polled」），所以它把 `RBBM_INT_0_MASK` 一次性写成 `0x33d283c2`。

## 2. 逐条对照表

判定列：**同** = 值与顺序一致；**异** = 值或写法不同（给出后果）；**27 不做** = 27 有意不写；
**27 额外** = 27 侧多出来的写法。

| # | sheng `GpuPowerProbe.cpp` | 27 `PongAdrenoCp.cpp` | 判定 | 27 上会导致什么 / 离线怎么验 |
| --- | --- | --- | --- | --- |
| 1 | `:1568-1569` 清 `GBIF_HALT`、`RBBM_GBIF_HALT` 并回读 | `:217` 同样的两个写，`:219-224` 再读 ACLK/CX/ACK 并 `note("GBIF traffic released",…)` | 同（27 多一次观测） | 27 日志有 `GBIF traffic released`；四值非 0 即 GBIF 未放行。离线：`grep -c "GBIF traffic released"` |
| 2 | `:1570` `SECVID_TSB_CNTL=0` | `:225-226` 另清 `TRUSTED_BASE_LO`/`TRUSTED_SIZE` | 同（27 更全） | 受保护域为空；ZAP/PAS13 仍做认证（`authorize()`） |
| 3 | `:1581` `RBBM_GBIF_CLIENT_QOS_CNTL=0x2120212` | `:227` 在 `PongCpGbif` 表里（`PongAdrenoCpProfile.h:1180-1185`，含 QSB side0-3 0x00071620） | 同 | 表行数：sheng 1 条 QOS，27 5 条（多 4 条 QSB） |
| 4 | `:1617` `RBBM_INT_0_MASK=0x33d283c2`（一次性） | `:228` 写 **0**；`:399` `programMask()` 再装（`submit/NativeAdrenoIrq.cpp:84-85` 写 + 回读） | **异**：sheng 无中断拥有者所以烧死掩码；27 有无拥有者由 `armcpu_spi_attach(332)` 决定 | 27 若 `GPU IRQ332 owner` 那行 `status!=0`，掩码退回 0、`idle()` 走 `IODelay(20)` 轮询（`PongAdrenoCp.cpp:62-66`）。离线：查 `GPU IRQ332 owner` 行的 route/affinity |
| 5 | `:1582` `UCHE_GBIF_GX_CONFIG=0x10240e0` | `:228` 同值 | 同 | — |
| 6 | `:1583` `PERFCTR_GPU_BUSY_MASKED=0xffffffff` | `:229` 同值 | 同 | — |
| 7 | `:1584-1585` `UCHE_TRAP_BASE`/`WRITE_THRU_BASE=0x1fffffffff000` | `:230-231` 同值（LO/HI 两次 32 位写） | 同 | — |
| 8 | `:1586-1587` `UCHE_GMEM_RANGE_MIN=0x1000000`、`MAX=+3MiB-1` | **不写**（`:234-236` 注释 `uche_gmem_alignment=0`） | **27 不做** | 27 的 GMEM 是 2 MiB（`PongAdrenoGmu.h:19`），设备的 GMEM 基址广告为 0。搬 sheng 的窗口会让 UCHE 指向不存在的 16 MiB 基址 ⇒ 是倒退。离线：`grep -n "uche_gmem_alignment"` 看注释与 `PongAdrenoGmemBytes` |
| 9 | `:1588` `UCHE_CACHE_WAYS=1<<23` | `:232` `0x800000` | 同 | — |
| 10 | `:1597` `UCHE_CMDQ_CONFIG=(6<<16)\|(6<<12)\|(9<<8)\|(1<<3)\|(1<<2)\|2` = `0x6690e` | `:232` `0x6690e` | 同（27 写成常量） | — |
| 11 | `:1589-1590` `CP_AHB_CNTL=1`、`RBBM_PERFCTR_CNTL=1` | `:233` 同值 | 同 | — |
| 12 | `:1606-1608` NC_MODE 三件，bank 位硬编码 3 | `:237-239` `const uint32_t bank=(PongAdrenoHighestBankBit-13)&3;` → `PongAdrenoGmu.h:28` 的 16 ⇒ 3 | 同值（27 由 DT 推） | 换到别的板只改 DT。离线：跑 `armcpu`/`adt` 检查脚本时核 `HighestBankBit` |
| 13 | `:1591` `HANG_INT_CNTL=(1<<30)\|0xcfffff` | `:240` 同值 | 同 | — |
| 14 | `:1592` `UCHE_CLIENT_PF=(1<<7)\|1` | `:240` `0x81` | 同 | — |
| 15 | `:1602` `RB_CMP_DBG_ECO_CNTL \|= 1<<11` | `:241` 同（读改写） | 同 | — |
| 16 | `:1594` `CP_PROTECT_CNTL=(1<<0)\|(1<<1)\|(1<<3)` = 11 | `:242` `11` | 同 | — |
| 17 | `:1599-1601` APRIV 三件 `0x6f/0x0f/0x0f` | `:248` 同值 | 同 | — |
| 18 | 无 | `:249` `CP_CHICKEN_DBG`/`CP_BV_CHICKEN_DBG`/`CP_LPAC_CHICKEN_DBG` 各写 1 | **27 额外** | 仅 27 有；sheng 没有这三个写。属「27 更严」，不是缺口 |
| 19 | `:1574` `CGC_MODE_CNTL=0x00020202`（A740） | `:250` `0x20000`（= 16.6.1 线 `PongAdrenoCp.cpp:250` 的同值） | **异** | 27 的 CGC 使能位比 sheng 少两档（bit17/23 未置）。后果只在时钟门控的粒度上，**没有公开文档能说清少这两档会发生什么**（位语义无公开出处，此格不填推测）。离线：`grep -n "CGC_MODE_CNTL" ` 两树对比即可复现差异 |
| 20 | `:1575-1576` CGC DELAY `0x10111`、HYST `0x5555` | `:250-251` 同值 | 同 | — |
| 21 | `:1577-1580` `RBBM_CLOCK_CNTL!=0x8aa8aa82` 才写 leaf 表 + 顶层使能 | `:252` 无条件写 53 条 leaf；`:255` 无条件写顶层使能 + 回读 | **异**（写法） | 27 每次 hw_init 都重写，且回读不等于 `0x8aa8aa82` 就失败返回。sheng 是「已在就跳过」。对 hang 后重跑更安全；对启动路径多 53 次 MMIO |
| 22 | leaf 表 = `NativeAdrenoA740Hwcg`（A740，54 条） | `PongCpHwcg`（A730，53 条，`PongAdrenoCpProfile.h:1125`） | **异**（表源） | 12 行数值差异见 `docs/research/gpu/GPU-27-CONTRACT-DIFF.md` §7.2；27 用 A730 表是**对的**，搬 A740 表才会引入 A730 上未验证的位 |
| 23 | `:1595-1596` `CP_PROTECT` 表 = `NativeAdrenoA740Protect` | `:247` `PongCpProtect`（45 条，`PongAdrenoCpProfile.h:1187`） | 需逐条核（未做） | 45 vs sheng 的 A740 条数不同；表值决定越权访问是被拦还是照样写。**离线可做**：两表逐行 diff（本文未做，见 §6 第 3 条） |
| 24 | `a7xx_patch_pwrup_reglist`（环形缓冲里的 power-up 列表） | `:258-264` `PongCpRestore` + `NativeAdrenoPwrupList::pack(counts,nullptr,nullptr,…)`，dynamic 三元组以 `PIPE_NONE/RBBM_PERFCTR_CNTL=1` 收尾 | 同（27 在核内打包） | 离线：`NativeAdrenoPwrupList` 的主机测试（若存在）+ 飞行里 `[vm map]`/pwrup 相关行 |
| 25 | 末尾 `gpuWr64(A740_CP_SQE_INSTR_BASE,…)` | 在 `submit/NativeAdrenoCpInit.cpp`（`:6` 注释说明该寄存器） | 同（不同文件） | 离线：`NativeAdrenoCpInit` 的交付 |
| 26 | `:1627 gpuRestart()`：`busHalt` → `RBBM_SW_RESET_CMD` 1/0 → `gpuHwInit()` `:1640` → `ring.restart` → `CP_SQE_CNTL` → `CpInit.run` → `idle` → 必要时 `CP_SET_SECURE_MODE 0` | **不存在** | **缺** | hang 之后 27 没有复位重跑路径：`faulted()` 只 poison 并保留 BO，没有 `native_adreno_set_restart` 的注册点（sheng `:1774`） |

## 3. `RBBM_CLOCK_*` 在 27 上谁有权写（Lead 点名项）

三条事实，逐条给位置：

1. **唯一的寄存器写入者**是 `hardware_init()`：`:252` 53 条 leaf、`:255` 顶层使能 + 回读。
   全树 `grep -rn "RBBM_CLOCK" drivers/` 只命中 `PongAdrenoCp.cpp:135,252,253,255` 与
   `PongAdrenoCpProfile.h` 的常量定义（`:421-437`）。**启动之后再没有任何路径重写**。
2. **唯一的「票」**是启动时那一次：`PongAdrenoPower.c:186-187`
   `table.default_gpu_index=2;` / `table.default_bus_index=PongAdrenoPowerLevels[11].bus;`
   → `PongAdrenoGmu.c:206-207` 把它作为 `default_vote[]={1,gpu_index,bus_index}` 发出去
   （HFI 启动票）。运行期只有 `PongAdrenoGmuVotePerf`（`PongAdrenoGmu.c:242-260`，HFI 30）
   改等级，它**不碰** `RBBM_CLOCK_*`。
3. 27 侧的 `gperf` 就是这条运行期票的开关：`PongAdrenoPlatform.cpp:554-560`
   （默认关，注释「without gperf nothing changes」）。16.6.1 上这条收益是
   `gpu 5,983→2,935 µs`，同一份代码，同一位置。

⇒ **真缺口不是「谁有权写」，而是「写了之后没人再写」**：GMU 若在 hang 后重新上电，
`RBBM_CLOCK_*` 的 leaf 状态按 sheng 的注释（`:1577` 的 `if` 判断）是会丢的——sheng 靠
`gpuRestart()` 重跑 `gpuHwInit()` 找回来；27 没有重启路径，所以「丢了」这件事在 27 上
**只能表现为帧变慢，不会自愈**。这一条要等 27 上出现 hang 飞行才能确认，目前是设计缺口而非实测。

## 4. 27 侧多出来的一段：中断拥有者

sheng 那棵树没有中断拥有者，所以它把掩码一次性烧成 `0x33d283c2` 并靠轮询。27 侧有：

- `PongAdrenoCp.cpp:397` `gpu->irq.attach(&gpu->ops.registers)`
- `PongAdrenoCp.cpp:398` `armcpu_spi_attach(332,false,interrupt,nullptr,&route,&affinity)`
  （注释：Pong DT SPI `0x12c`、level high、GIC INTID 300+32）
- `PongAdrenoCp.cpp:399` `gpu->irq.programMask(nullptr)`（掩码头在 `NativeAdrenoIrq.cpp:84-85`，写后回读）
- `PongAdrenoCp.cpp:400` 失败则 `RBBM_INT_0_MASK=0` 并返回错误
- `PongAdrenoCp.cpp:96-110` 中断里只做三件事：解码、唤醒、fatal 时清掩码；不做分配、不改环

因此「27 上谁保证 `RBBM_INT_0_MASK` 有值」的答案是：`programMask()`，且它的前置条件是
**`armcpu_spi_attach(332)` 成功**。若 SPI 未挂上，掩码为 0、`idle()` 退回 `IODelay(20)`
（`:62-66`），表现为每次等待固定多 20 µs——这是一条能在飞行里直接读出来的差别。

## 5. 与预算表的关系

- 本文不改变 `docs/research/gpu/GPU-27-BUDGET-120FPS.md` 的任何结论：那三条（交付模型、
  CPU 合成墙、零拷贝）都不经过 hw_init。
- 唯一相交处是 `gperf`：预算表 §6/§8 把「运行期调档」记为 27 侧已就位（
  `PongAdrenoGmu.c:260` + `PongAdrenoPlatform.cpp:557`），本文 §3 给出它的上游（启动票）与
  它管不到的范围（`RBBM_CLOCK_*`）。

## 6. 离线能验的三件事（都不需要上机）

1. **两份 hw_init 的寄存器序**：本文 §2 的表可 `grep -c` 复核。实测调用点计数
   （`sed -n '213,267p' drivers/PongAdreno/PongAdrenoCp.cpp | grep -c "wr(GEN7_\|wr64(GEN7_"`
   = **22**；`sed -n '1567,1620p' package/GpuPowerProbe.cpp | grep -c "gpuWr(\|gpuWr64(\|gmuWr("`
   = **39**）不是「27 少 17 次写」：27 把多个写串进同一条 `if(!wr(a)||wr(b)||…)`，两个整表
   （`PongCpHwcg` 53 条、`PongCpProtect` 45 条）走循环，sheng 侧则是逐条铺开。要判覆盖必须按
   §2 逐行比，不能按调用点数比——这正是本文存在的理由。
2. **中断拥有者的前置条件**：`grep -n "armcpu_spi_attach\|programMask\|irq_attached"` 在 27 树
   只有 `PongAdrenoCp.cpp:397-401`，在 sheng 树零命中——一条命令就能确认「27 有、sheng 没有」。
3. **`CP_PROTECT` 两表逐行 diff**（已完成，见 §7）：`PongAdrenoCpProfile.h:1187` 起的 45 条
   vs `NativeAdrenoA740HwInit.h` 的 `NativeAdrenoA740Protect`，再 vs 上游
   `a730_protect_regs`。结论是**只有 3 条不同、43 条同值**，且那 3 条不是代际差。

## 7. `CP_PROTECT`：两表逐行 diff（Lead 点名项）

### 7.1 三张表在哪

| 表 | 位置 | 条数 | 谁执行 |
| --- | --- | --- | --- |
| 27 侧 `PongCpProtect` | `drivers/PongAdreno/PongAdrenoCpProfile.h:1187-1235` | 45 | `PongAdrenoCp.cpp:247` 循环写 `GEN7_CP_PROTECT_REG+n` |
| sheng 用的 `NativeAdrenoA740Protect` | `drivers/Adreno740/NativeAdrenoA740HwInit.h:119-166` | 46 | `GpuPowerProbe.cpp:1596` 循环写 `A740_CP_PROTECT+i` |
| 上游 `a730_protect_regs` | `a6xx_catalog.c:1310-1360`（`DECLARE_ADRENO_PROTECT(a730_protect, 48)`，`:1362`） | 48 槽（45 实 + 45/46 两个 0 占位） | `a6xx_set_cp_protect()` |

值的编码在 `a6xx_gpu.h:228-240`：`NORDWR = (1<<31) | (len & 0x3FFF) << 18 | (reg & 0x3FFFF)`，
`RDONLY` 同式去掉 bit31。**区间编码在值里，不在下标里**——所以「27 从第 10 条起下标比 a730
小 1」只是排版差，不产生语义差；真正的语义差看值。

### 7.2 机械 diff 的结果：只有一组替换

用 `E:/k60-work/scratch/prop/protect_diff.py`（读三张表、解码、按集合比）跑出来的：

| 只有 a730/A740 有 | 只有 27 有 | 共同 |
| --- | --- | --- |
| `NORDWR(0x008de, len 1)` → 0x8de–0x8df 禁读禁写 | `RDONLY(0x008d0, len 0x170)` → 0x8d0–0xa3f 可读禁写 | 44 条 |
| `RDONLY(0x008e7, len 0x14b)` → 0x8e7–0xa32 可读禁写 | — | — |

也就是说：**45 条里 43 条与 a730 完全同值**（`PongCpProtect` 的 0–8、10–43、47 各条值都能在
`NativeAdrenoA740Protect` 里逐字找到），差异集中在 0x8d0–0xa3f 这一段。

### 7.3 这组替换在 A730 上的行为（逐段）

| 地址段 | a730（上游） | 27 侧 | 在 K60 上会怎样 |
| --- | --- | --- | --- |
| 0x8d0–0x8dd、0x8e0–0x8e6 | **不保护**，`a6xx_catalog.c:1320` 写明「unprotected on purpose for tools like perfetto」 | 禁写 | 任何性能工具/自家探针写这两个窗（perf 计数器选择与状态就在这一带）会被 CP 拦下，触发 `CP_PROTECT_STATUS`，再走 `faulted()` → 设备 poison |
| 0x8de–0x8df | 禁读禁写 | 可读 | 27 更松：CP 能读这两格 |
| 0x8e7–0xa32 | 可读禁写 | 可读禁写（被 27 的 0x8d0–0xa3f 覆盖） | 相同 |
| 0xa33–0xa3f | 不在此对里 | 禁写 | 27 更严，属无害加固 |

### 7.4 「哪几条在 A730 上必须不同」的判定

**结论：这两条不是 A730/A740 的代际差，而是上游与厂商的分歧——两棵树跑的都是 A730。**

- sheng 的 `NativeAdrenoA740Protect` 注释就写着表来自 `a730_protect`，值与上游 `a730_protect_regs`
  逐条一致；27 的 `PongCpProtect` 来自 Nothing Phone (2) 的 gen7 表——那也是 A730。
- 因此「A730 必须不同」的候选只有一组：0x8d0–0xa3f 那一段。判定按三条可查事实：
  1. 上游为 A730 明确放开了 perfetto 窗口（注释就在 `a6xx_catalog.c:1320`），K60 的 A730 与此同族；
  2. 27 侧把这段封成禁写，换来的是「自家工具也写不进去」，没有任何 K60 证据表明需要这道封；
  3. 27 侧同时把 0x8de–0x8df 从禁读禁写降为可读，这条方向上**没有收益也没有风险证据**，
     但它说明这张表不是照着 a730 抄的，而是抄了另一台机器的表。
- 建议（不改代码，等 Lead 定）：K60 用 `a730_protect_regs` 的 45 条实值替换
  `PongCpProtect`；若要保留厂商封法，必须在飞行里先证明「写 0x8d0–0x8e6 会被拦且我们没有
  这类写者」。当前 27 树没有任何地方写这一段（`grep` 这 8 个偏移的实现为零），所以替换是
  纯放开，不会立刻引入越权写。
- 附带一条：`PongCpProtect` 少了 a730 的两个 0 占位（下标 45/46），若将来按 a730 补齐到 48 槽，
  必须整表对齐下标，否则第 46 条会落到别人的位置上。

### 7.5 怎么复核（不靠记忆）

```sh
python3 E:/k60-work/scratch/prop/protect_diff.py
# 期望输出：27 count 45 / a740 count 46 / only in 27: ('RDONLY','0x8d0','0x170','0xa40')
#           only in a740: NORDWR 0x8de len 1、RDONLY 0x8e7 len 0x14b / common 44
```

脚本读的是三处的原文（27 的宏式表、A740 kit 的 `{index,value}` 表），不做人工转录；改任何一张表
都会让这三行输出变化。

## 8. 引用

- `E:/hackios/UniXNU-sheng/package/GpuPowerProbe.cpp:1565-1645`（`gpuHwInit`）、`:1627-1690`（`gpuRestart`）、`:1774`（重启钩子注册）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoCp.cpp:213-267`（`hardware_init`）、`:397-401`（IRQ 拥有者）、`:62-66`（轮询回退）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoCpProfile.h:1125`（`PongCpHwcg`）、`:1180`（`PongCpGbif`）、`:1187`（`PongCpProtect`）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoGmu.h:19,28`（`PongAdrenoGmemBytes`、`PongAdrenoHighestBankBit`）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoGmu.c:206-207,242-260`（启动票、HFI 30）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoPower.c:186-187`（启动票的两个来源）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/PongAdrenoPlatform.cpp:554-560`（`gperf`）
- `E:/hackios/xnekom-ios27/drivers/PongAdreno/submit/NativeAdrenoIrq.cpp:84-85`（掩码写 + 回读）
- 官方页：`https://unixnu.com/zh/porting/gpu` 的 `#scheduling`（抢占/调档）与 `#memory-path`（映射与失效）
- 本线文档：`docs/research/gpu/GPU-27-CONTRACT-DIFF.md` §7.1/§7.2、`docs/research/gpu/GPU-27-BUDGET-120FPS.md` §6/§8
