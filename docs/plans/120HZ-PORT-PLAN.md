> **⚠️ 数据源更正（2026-11-07，Lead 核实后追加，优先级高于本文件 §2/§3）**
>
> 本文件原 §2/§3 的面板参数取自 **`qcom,mdss_dsi_sharp_qhd_plus_dsc_cmd`** —— 一个 Qualcomm
> **通用参考面板**（实测 27/35 个 fdt 都带它），**不是 K60 的实测面板**。
> 依据：`D:/Android/k60-ios/deliverables/ZCODE-RESEARCH-REPORT.md:396`（U6-C5）。
>
> K60 真机面板是 **`qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`**（`hwid.project=14`，
> `D:/Android/k60-ios/AGENT-COORDINATION.md:1778`），它有 **60/90/120 三档**：
> `timing@0`=60Hz（DCS `0x2F=0x02`）、`timing@1`=90Hz（`0x2F=0x01`）、`timing@2`=120Hz（`0x2F=0x00`），
> 三档 **phy-timings 与 clockrate `0x47868C00`(1.2 GHz) 逐字节相同**
> （`ZCODE-RESEARCH-REPORT.md:384`，U6-C4）。
>
> **因此：本文件里 sharp_qhd_plus 的 `0xC6` 切档序列在真机上大概率是错命令，禁止使用。**
> 切档必须改用 m11a 的 DCS `0x2F`。
>
> 另据同一份证据：内核侧 `fb_hz=N`(1..240) 只改 **CoreAnimation 节拍**（TimingElements/vsync/present），
> **不改面板扫描率**；**真 120Hz 需要新增 DSI host/PHY/PLL 驱动，而这块当前完全缺失**。
> 只改 `fb_hz=120` 的后果被明确记录为：CA 按 8.33 ms 绘制、面板仍 60 Hz 扫描、CPU 拷贝翻倍、撕裂概率升高。

# K60 120 Hz 移植方案（GPU scanout 生效之后执行）

> 状态：方案稿，**未实施**。每条结论后附 `文件:行`；无法证实的集中在 §5。
> 取证基准一：`patches/xnu/series` 第 101/102/104/130 行（= 当前 K60 内核的显示补丁集）。
> 取证基准二：`E:/hackios/work-display/xnu`（= xnu-8796.141.3 + `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch`
> + 0210/0211/0213 的展开树）。该树行号与既有文档一致：`HANDOFF-2026-10-31.md:234` 引的
> `MiniIOMobileFramebuffer.cpp:1172` 正是 vsync 周期那一句（本树 `:1172`），
> `READING-INDEX.md:111` 的日志串也出自本树 `:452`。
> 引用约定：
> `PLAN:Lx` = `D:/Android/k60-ios/deliverables/K60-120HZ-PLAN.md`；
> `HANDOFF:Lx` = `E:/hackios/UniXNU-mondrian/docs/HANDOFF-2026-10-31.md`；
> `IDX:Lx` = `E:/hackios/UniXNU-mondrian/docs/READING-INDEX.md`；
> `RPT:Lx` = `D:/Android/k60-ios/deliverables/ZCODE-RESEARCH-REPORT.md`（2026-10-30 的复核报告，晚于 PLAN）；
> `zizhan:<path>:Lx` = `E:/hackios/UniXNU-zizhan`；
> `pong:<patch>:Lx` = `E:/hackios/UniXNU-pong` 的 `patches/xnu/<patch>`，**行号是补丁文件自身行号**；
> `mfb:Lx` = `E:/hackios/work-display/xnu/iokit/Kernel/MiniIOMobileFramebuffer.cpp`。

---

## 0. 一页结论

1. **内核侧"发布 120 Hz"已经是 0 行代码**：`refreshHz()` 读的是 boot-arg `fb_hz`（默认 60），四个消费点
   （TimingElements 速率、presenter 节拍、vsync 定时器、迟到阈值）全部自动跟随（§3.1）。
   `PLAN:L74` 说"60 Hz 是 0210 里硬编码"，准确说法是"默认值 60，可由 `fb_hz` 覆盖"。
2. **真正缺的只有面板侧**：整棵 K60 内核没有一行 DSI/MDSS/PLL 代码（`RPT:L30`、`RPT:L414`；本树
   `grep -i "dsi\|mdss\|pll" mfb` 零命中）。面板现在是 ABL 点亮的、纯软件 memcpy 到 boot framebuffer
   （`HANDOFF:L232-236`）。
3. **120 Hz 的最小改动集是一张 DCS 长包 + 一个 boot-arg**，但要先解决一个**数据源冲突**：
   `PLAN` 的面板参数来自通用参考面板 `sharp_qhd_plus_dsc_cmd`，而 `RPT:L396` 实测 K60 真机面板是
   `m11a_42_02_0a_dsc_cmd`，三档 60/90/120、切档走 `0x2F`/`0x8B`（`RPT:L397`）。
   照 `PLAN` 的 `0xC6` 序列发下去，在真机上大概率是**发错命令**（§2.2 给出定标办法）。
4. **顺序不能反**：软件 framebuffer 一帧 CPU 拷贝 9–10 ms，8.33 ms 的帧窗装不下（`HANDOFF:L238`），
   所以必须先满足 §1 的 GPU scanout 判据，再切面板。当前这两件事都还没就绪（§1.4）。

---

## 1. 前置条件：GPU scanout 生效的判据

### 1.1 构建面（缺一不可）

| # | 条件 | 证据 |
|---|---|---|
| B1 | 内核链接了 Adreno 平台归档（`libPongAdrenoPlatform.a`，含 `PongAdrenoScanout`） | `scripts/build-xnu-4k-baseline.sh:957-973`（`PONG_ADRENO_PLATFORM=1` 才编译）、`:979-983`（`-force_load`）；源文件清单见 `scripts/build-pong-adreno-platform.py:83` |
| B2 | `patches/xnu/series` 含三个 scanout 补丁 | 当前**不含**：`series` 共 144 行，与 GPU 相关的只有 `:87`（ui-foundation）和 `:96`（panel-selection）；`*pong-gpu-scanout.patch`、`*pong-gpu-only-display.patch`、`*pong-source-row-pitch.patch` 均无条目 |
| B3 | 启动参数 `pong_gpu_scanout=1` | `drivers/PongAdreno/PongAdrenoScanout.cpp:33`（`enabled!=1` 直接 return）；`drivers/PongAdreno/README.md:62` |

B2 的含义：补丁文件在仓库里（`patches/xnu/zzzz…-pong-gpu-scanout.patch` 等），但**没有被 series 应用**，
所以 `mfb` 里现在根本没有 `pong_scanout_frame` 的调用（本树 grep 零命中）。在 B2 补齐之前，
`pong_gpu_scanout=1` 不会有任何效果。

### 1.2 运行面：日志判据（逐条可 grep）

| # | 判据 | 日志/行为 | 证据 |
|---|---|---|---|
| R1 | 交接初始化成功 | `PONG SCANOUT: actual framebuffer handoff available sequence=0 status=0x0` | 驱动在 `PongAdrenoScanout.cpp:55` 打这一行；`note()` 的前缀在 `:23-27` |
| R2 | 初始化没有被静默拒绝 | 若 `PE_current_console()` 的宽高/stride/depth/rotate 与 `vinfo` 不符，函数**直接 return 且不打日志** | `PongAdrenoScanout.cpp:44-55`（判据是"R1 那行必须出现"，不是"没有报错"） |
| R3 | 每帧真的走了 GPU | `PONG SCANOUT: GPU frame completed sequence=N status=0x0`（前 3 帧） | `PongAdrenoScanout.cpp:158-159` |
| R4 | CPU 合成被跳过 | `show()` 里 `gpuFrame` 为真时 `drawLayer()` 不执行；mfb 5 秒行的 `us each in the driver` 应掉到接近 0 | `pong:…-pong-gpu-scanout.patch:70-71`；统计行 `mfb:1001-1006` |
| R5 | 没有进入隔离态 | 不出现 `GPU copy not retired; retain pages and previous frame`；一旦出现 `poisoned=true`，此后所有帧返回 2，**只能重启恢复** | `PongAdrenoScanout.cpp:154-157`、`:139` |

### 1.3 决定性判据（唯一能排除"其实还在 CPU 画"的实验）

以 `pong_gpu_only=1` 启动：该参数让"没有完成的 GPU 帧"时**不做 CPU 合成**，直接返回（画面会停/黑）。

- 屏幕**照常刷新** + 无 `PONG GPU ONLY: no completed GPU frame; CPU composition disabled` → GPU scanout 生效。
- 屏幕冻结 + 该行出现 → 仍在 CPU 路径。

证据：`pong:…-pong-gpu-only-display.patch:55-62`（`fGpuOnly` 分支）、`:32-34`（boot-arg 解析）、`:53`
（只有返回值 `==1` 才算 GPU 帧；`2` 是 DMA 不确定，必须让位给 CPU 或停屏）。

> 注意：Metal 插件那条路有独立判据 —— `drivers/PongMetal/PongMetalScanout.h:44`
> 打 `actual GPU scanout copy completed`（前 3 次），失败分支在 `:59/:69/:75/:79`
> （`GPU scanout disabled by boot policy` / `scanout connection unavailable` / `scanout mode refused` /
> `scanout mapping refused`）。两条路任一生效都满足本方案的前提，但**必须有一条的日志证据**。

### 1.4 今天的状态（诚实记录）

- `series` 没有 scanout 补丁（§1.1 B2）→ 内核 `show()` 里没有 GPU 交接点。
- `board.toml:14` 的 `[components]` 只有 `ArmDTPlatform/ArmCpu/XnuPrelink/PongUfs`，没有 GPU 组件；
  `HANDOFF:L224-225` 记录 `drivers/PongAdreno/` 源码存在但"未进链接"，当前生效的是 0212 空加速器。
- 结论：**§1 尚未满足**。120 Hz 的第一步不是改显示，而是把 §1.1 的 B1–B3 打通并拿到 R1/R3/R5 的日志。

---

## 2. 面板切 120 Hz 的最小改动集

### 2.1 数据源 A：`PLAN` 的数值（任务指定；对象 = `sharp_qhd_plus_dsc_cmd`）

| 项 | 120 Hz 档 | 60 Hz 档 | 来源 |
|---|---|---|---|
| 节点 | `qcom,mdss_dsi_sharp_qhd_cmd`（cmd 模式） | 同 | `PLAN:L4` |
| `panel-framerate` | **0x78 = 120** | 0x3c = 60 | `PLAN:L21`（原文注"唯一必改项"） |
| `panel-width/height` | 0x2d0=720 / 0xc30=3120（DSC 后） | 同 | `PLAN:L22-23` |
| H/V porch、pulse | 72/20/4、39/12/2 | 同 | `PLAN:L24-29` |
| `mdp-transfer-time-us` | 0x1efd = 7933 | 同 | `PLAN:L30` |
| `display-topology` | `<0x02 0x02 0x02>` | 同 | `PLAN:L31` |
| DSC | bpp 8、slice 360×8、per-pkt 1 | 同 | `PLAN:L32-36` |
| `phy-timings` | `[00 1a 07 06 16 21 07 07 07 02 04 00 17 0c]` | `[00 10 03 03 11 1e 04 04 03 02 04 00 03 09]` | `PLAN:L41-42`（**两档不同**） |
| `timing-switch-command` | `39 01 00 00 00 00 34 c6 00 12 44 00 08 00 0b 01 20 25 30 01 49 01 49 …` | `… c6 00 12 88 …` | `PLAN:L48-49` |
| 差异点 | `0xC6` 的第二参数 `0x1244` ↔ `0x1288` | | `PLAN:L52` |

按这份数据，最小集 = ①整段 52 字节 DCS 长包（`0x39`，长度 `0x34`）②PHY 的 14 字节换成 120 Hz 档
③DSI PLL 位率翻倍（`PLAN:L60-65` 的像素时钟 155.4→310.8 MHz，双 DSI 每 lane-pair 77.7→155.4 MHz）。

**但这份数据不能直接上机**：
- `PLAN:L48-49` 的字节流被 `…` 截断，只有前 18 字节；`0x34`=52 字节的 payload 缺后 34 字节 → 无法照抄。
- `PLAN:L98-100` 自己承认"PLL 来源未确认""`0xC6` 语义未知"。

### 2.2 数据源冲突（**必须先定标，否则会发错命令**）

`RPT`（2026-10-30，晚于 PLAN，用自写 FDT 解析器复核过 dtbo）给出的是另一块面板：

| 项 | `PLAN`（sharp_qhd_plus_dsc_cmd） | `RPT`（m11a_42_02_0a_dsc_cmd） | 证据 |
|---|---|---|---|
| 节点是否在 fdt15 | 称在 | **不在**；fdt15 实测 31 个面板节点，无此名 | `RPT:L396` |
| 真机面板 | 未区分 | `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`，`mi,panel-id="M11A" 42 02 00` | `RPT:L397` |
| 档位 | 2 档（120/60） | **3 档**：timing@0=60、timing@1=90、timing@2=120 | `RPT:L397` |
| 切档命令 | `0xC6` = `0x1244/0x1288` | DCS **`0x2F`**（60=0x02 / 90=0x01 / 120=0x00）配 **`0x8B`**（60=0x00 / 90=0x10 / 120=0x00） | `RPT:L397` |
| PHY timings | 两档不同 | **三档逐字节相同** `[00 27 0a 0a 1b 25 0a 0b 0b 0a 02 04 20 0f]` | `RPT:L397`、`RPT:L417` |
| clockrate | 未记 | 三档同为 `0x47868C00` = 1.2 GHz | `RPT:L397`、`RPT:L404` |
| panel-type | 日志写"video"（自造字符串） | `dsi_cmd_mode`（带 TE：te-check-enable / te-using-te-pin / te-pin-select / te-dcs-command=0x01） | `RPT:L410`；日志串出处 `patches/xnu/0210-k60-display-native-canvas.patch:66` |
| DSC | 720 宽、slice 360×8 | 720 宽、slice **720×32**、per-pkt 2、bpp 8 | `RPT:L397` |

> `PLAN:L52` 的 `0xC6` 是"**另一块面板**"的切档寄存器。在 K60 真机（m11a）上发它，
> 轻则无反应，重则黑屏（面板私有寄存器语义未知，`PLAN:L100`）。

**定标办法（一次只做一步，`HANDOFF:L207` 红线）**：
1. Android 侧只读：`adb shell ls /sys/firmware/devicetree/base/soc/` 找 `dsi@*` 的 `panel` 子节点，
   读 `panel-name` / `mi,panel-id`；或对 `vendor_boot` 的 dtbo 段跑 `dtc -I dtb -O dts`（`RPT:L396` 就是这么做的）。
2. 判据：出现 `m11a_42_02_0a` 且 `mi,panel-id=4d 31 31 41` → 走 §2.3 路径 B；出现 `sharp_qhd_plus_dsc_cmd`
   → 走路径 A。两者都不是 → 停，先补数据。
3. **本机当前无法做这步**：`PLAN:L3` 记的 `D:/Android/k60-ios/dtb/dtbo_a_fdt15.dtb` 在盘上已不存在
   （该目录不存在，`find` 只找到 `hardware.dtb`，1862 字节），`dtbo_a_fdt19.dtb` 同样不在。见 §5-2。

### 2.3 两条候选最小集

**路径 B（推荐，若有 m11a 证据）**
1. 取 `timing@2` 的 `qcom,mdss-dsi-timing-switch-command` **整段**（cmd 模式必须发完整 payload，
   `RPT:L410` 明确"不要只发 3 字节"），关键字节 `0x2F=0x00`、`0x8B=0x00`（`RPT:L397`）。
2. **不动** PHY/PLL：三档 `phy-timings` 与 `clockrate` 相同（`RPT:L397`）→ 链路位率不变，
   面板内部换档（cmd 模式带 GRAM 自刷新，`RPT:L410`）。
3. 内核发布侧只需 `fb_hz=120`（§3.1）。

**路径 A（仅有 sharp 证据时）**
1. PHY：`DSIPHY_CMN_TIMING_CTRL_0..13` 整组写 `[00 1a 07 06 16 21 07 07 07 02 04 00 17 0c]`
   （`PLAN:L41`；寄存器语义见 `RPT:L416-418`：14 字节就是这 14 个寄存器的直写值，**整组换，不要只改个别字节**）。
2. PLL 重锁到 120 Hz 档位率：约 550–621 Mbps/lane（`RPT:L419`；= `PLAN:L60-65` 的 155.4 MHz/lane-pair 量级）。
3. 最后发 `0xC6` 长包（`PLAN:L48`，**需补全 52 字节**）。

### 2.4 明确**不需要**改的东西

- DSC slice/几何：与帧率正交，`RPT:L403` 复算 1440×3200@120 净码率 4.424 Gbps、双 DSI 553 Mbps/lane，
  都在 D-PHY 能力内。`PLAN:L99` 的"slice-height=8 风险低"在 m11a 上连前提都不成立（真实是 32）。
- 画布尺寸：`PLAN:L79-80` 说"同步 v-front/back/pulse" —— 在本代码库里**没有对应字段**：
  `publishModes()` 只发布 `Active/Total/SyncRate/PreciseSyncRate`（`mfb:342-349`），porch 根本不进 TimingElements。
  所以这一步是 no-op，不要为它改代码。
- lane 数/电压：`PLAN:L65`、`RPT:L419` 一致，4 lane 不变。

---

## 3. 代码落点

### 3.1 内核侧：发布 120 Hz 的 TimingElements

| 位置 | 现状 | 要改成什么 |
|---|---|---|
| `mfb:85` | `#define kFBRefreshHz 60` | **不改**（这是全平台默认值，改了会波及别的板） |
| `mfb:158` | `TUNABLE(gRefreshHz, "fb_hz", kFBRefreshHz)` | 启动参数加 **`fb_hz=120`**（零代码；`TUNABLE` 在启动时解析一次，运行期不可改） |
| `mfb:191-194` | `refreshHz()` 返回 1..240 的 `gRefreshHz` | 若镜像里注入 boot-arg 不方便，唯一需要动的代码是这里：加一个 K60 专用 tunable 并在 `k60PanelNative()` 时优先返回（3 行；**不要**直接改 `:85`） |
| `mfb:319-369` | `publishModes()`：`rate = refreshHz() << 16`（`:327`），写 `TimingElements`/`ColorElements`（`:359-360`） | **不用改**，自动 120；`Active/Total` 是画布 1440×3200（`:342-349`），与 porch 无关 |
| `mfb:876-899` | `show()` 的 fb_beat：`period = 1/refreshHz()`（`:879`），目标相位 `3/8` 周期 | **不用改**，自动 8.333 ms |
| `mfb:1167-1178` | `armVSync()`：`period = 1/refreshHz()`（`:1172`） | **不用改**，通知周期自动 8.333 ms |
| `mfb:791-798` | `present()` 的"迟到"阈值 `1.25×period`（`:798`） | **不用改**，统计口径自动跟随 |

要点：`TimingElements` 一旦在 `start()` 里发布就不再变（`mfb:359`）。所以 120 Hz 必须在**启动时**就报，
不能等切档成功后再改——这也是 zizhan 的做法：`fb_hz` 默认 120，第一帧时再切面板
（`zizhan:docs/progress/2026-11-01-120hz-and-cadence.md:112-115`、`:63`）。
代价是开机后最初几百毫秒内"CA 按 120 排、面板仍是 60"，可接受（同文 `:35` 的抖动分析）。

### 3.2 面板侧：DSI 切档（当前完全缺失，需新建一个 TU）

| 位置 | 要做什么 |
|---|---|
| **新建** `drivers/PongAdreno/PongDsiPanel.cpp`（+ `.h`） | 移植 zizhan 的四段：`dsiInit`（`zizhan:drivers/PongAdreno/PongAdrenoScanout.cpp:682`）、`dsiDcs`（`:694`）、`dsiSet`（`:734`）、`panelHz`（`:747`）；命令数组与寄存器枚举照 `:670-680` |
| DSI0 基址 | `0x0ae94000`，长度 `0x400`（`RPT:L404` 由 K60 `vendor_boot` fdt 实测；`zizhan:…:670` 同值） |
| 关键寄存器（相对 DSI0） | `HW_VERSION 0x000`、`CTRL 0x004`、`STATUS 0x008`、`CMD_DMA_CTRL 0x03c`、`DMA_CMD_LENGTH 0x04c`、`TRIG_CTRL 0x084`、`CMD_DMA_SW_TRIGGER 0x090`、`INT_CTRL 0x110`、`TPG_CTRL 0x15c`、`TPG_CMD_DMA_INIT_VAL 0x17c`、`TPG_DMA_FIFO_RESET 0x1ec`（`zizhan:…:670-673`） |
| 发送前自检 | 必须 `(ver>>28)==2` 且 `(ctrl&5)==5`，否则"不是运行中的 cmd-mode DSI 2.x"，直接放弃（`zizhan:…:691`）。这一条同时是**控制器有没有被 ABL 占用**的探针 |
| FIFO 流程 | 等 `DMA_BUSY` 清 → 等 `MDP_BUSY` 清（最多 ~20 ms，计入 `MDP-busy waits`）→ 组 word（`0x39` 长包：`1<<31|1<<30|0x39<<16|len` + 4 字节小端 payload）→ 写 `TPG_CMD_DMA_INIT_VAL` → `CMD_DMA_CTRL` 置 `1<<28` → `DMA_CMD_LENGTH` → `CMD_DMA_SW_TRIGGER=1` → 轮询 `INT_DMA_DONE` ≤25 ms → 复位 TPG/FIFO（`zizhan:…:694-733` 逐行） |
| 租约/互斥 | zizhan 用 `pong_dsi_try_acquire(PongDsiTiming)` 与背光共享 DSI（`:753`、`:760`）；K60 目前没有背光 DSI 通道，先做单占用即可，但**要留出这个锁的位置**，否则接 CoreBrightness 时会打架（`zizhan:docs/…:131`） |
| 调用点 | `drivers/PongAdreno/PongAdrenoScanout.cpp:139`（`IOLockLock(scanout_gate)` 之后、`poisoned` 检查之前）插入 `if (gpu_frame_seen && !panel_done) pong_panel_hz();`，**与 zizhan 完全同一位置**（`zizhan:…:1055` 的 `if(dbOn && !panelDone)panelHz();`） |
| 构建挂载 | `scripts/build-pong-adreno-platform.py:83` 的 `names=[…'PongAdrenoScanout'…]` 加入 `'PongDsiPanel'` |
| 切档后测量 | 加 `intfProbe`/`intfRate`（`zizhan:…:632`/`:648`）：INTF 帧计数 `0xac`、TE 计数 `INTF_TEAR_INT_COUNT 0x298>>16`，块偏移 `0x35000/0x36000/0x37000/0x38000`（内屏 INTF_1 = `0x36000`，`zizhan:…:630-631`） |

`pong_panel_hz()` 的骨架（参数化，命令表按 §2.3 的路径填）：

```c
/* 只做一次；由 pong_scanout_frame() 在拿到第一帧后调用 */
void pong_panel_hz(void) {
    if (panel_done) return;
    panel_done = true;                       /* 失败也不重试：避免每帧 25 ms 抖动 */
    if (!pong_dsi_init()) return;            /* ver/ctrl 自检失败即放弃 */
    intf_rate("before the switch");
    unsigned sent = 0;
    int rc = pong_dsi_set(kPanelSwitch120, sizeof kPanelSwitch120, /*lp=*/false, &sent);
    IOLog("K60 PANEL: timing switch to 120 Hz: %u packets, rc %d\n", sent, rc);
    if (rc) return;
    for (unsigned i = 0; i < 300; i++) IODelay(1000);   /* 300 ms，同 zizhan:772 */
    intf_rate("after the switch");                       /* 判据：≈120/s */
}
```

### 3.3 与 pong 的 scanout 是不是同一个函数？

- pong 的 GPU 交接注入点是 **`IOMobileFramebuffer::show()`**：补丁在 `drawn = mach_absolute_time();`
  之前插入 `gpuFrame = pong_scanout_frame(...)`（`pong:…-pong-gpu-scanout.patch:39-62`，上下文 `:35-37`
  就是 `show()` 里那段 swap 统计）。我们 0213 也改 `show()`（`mfb:970-975` 首帧日志）→ **同一函数**。
- 但 **120 Hz 切档不要放 `show()`**，理由三条：
  1. `show()` 在 `fLock` 下每帧执行（`mfb:907`），切档只需一次，且要持 DSI 独占；
  2. `show()` 时 GPU 帧"刚被提交"，还没确认完成；切档应发生在"第一帧真的上屏之后"；
  3. zizhan 把它放在驱动侧 `pong_scanout_frame()` 的入口（`zizhan:…:1055`），我们照抄最省事，
     且与 `pong_scanout_quarantined()` 的语义一致（隔离态下不该碰面板）。

### 3.4 我们四个补丁各自改了什么（判断 120 Hz 该落在哪）

| 补丁（series 行） | 文件 | 函数/位置 | 与本方案的关系 |
|---|---|---|---|
| `0210-k60-display-native-canvas.patch`（`series:101`） | `MiniIOMobileFramebuffer.cpp` | 文件头加 `K60_PANEL_*`/`k60PanelNative()`；`start()` 里 `fWidth/fHeight` 取面板原生 1440×3200（展开树 `mfb:414-431`）；打 `K60 DISPLAY: panel … %u Hz`（`mfb:452`，用 `refreshHz()`） | **画布契约，不改速率**。日志里的 "60 Hz" 只是默认值的回显，不是硬编码点 |
| `0211-k60-display-startup.patch`（`series:102`） | `MiniIOSurface.cpp` | `native_pong_ui_services_start()`：默认开启显示服务（`pong_software_ui=0` 才关）；`getPlatform()` 显式转型 | 与速率无关 |
| `0213-k60-display-first-frame.patch`（`series:104`） | `MiniIOMobileFramebuffer.cpp` | `publishModes()` 加 `K60 DISPLAY: TimingElements … %u Hz`（`mfb:361-362`）；`show()` 加首帧日志（`mfb:972-975`）；`GetDisplayDevice` 返回 `kFBDisplayID=1`（`mfb:315-316`） | 只加日志/标识，**没有改 rate** |
| `0236-k60-managed-memory-and-panel.patch`（`series:130`） | `osfmk/arm64/arm_vm_init.c` | `arm_vm_init()` 里加 `K60 MEM:`/`K60 FB:` 诊断 + `k60_capmanaged` | 内存/诊断，**与 120 Hz 无关**（"panel" 只是打印 boot framebuffer 范围） |

结论：120 Hz 的"内核侧发布"落在 `refreshHz()` 的输入（boot-arg 或 `mfb:191-194`），
"面板侧切档"落在 `drivers/PongAdreno/PongAdrenoScanout.cpp:139` + 新 TU。**两者都不在 0210/0213 里。**

---

## 4. 风险与验证

### 4.1 三级判据（软件 → 硬件 → 观感，逐级独立）

**S 级（软件节拍，只能证明 CA 以为 120）**
- mfb 5 秒统计行：`MiniIOMobileFramebuffer: %u frames in %llu ms (%llu a second) …`
  （`mfb:1001-1006`）。括号里的 "a second" 在 60 Hz 面板上恒为 ~60，**它统计的是 `show()` 的出帧**，
  所以它升到 ~120 只能说明"有 120 帧被送进 show"，不能说明面板真的扫了 120 次。
- `reportFrameTimes()`：`from one frame to the next: N times under 10 ms, M under 18, …`
  （`mfb:780-783`，分桶边界 `10/18/26/35 ms` 在 `mfb:759`）。120 Hz 下 `under 10 ms` 应成为主桶；
  60 Hz 下主桶是 `under 18`。
- beat 等待：同一行里的 `%llu us for the next refresh`（`mfb:1002`）应 <1 ms。
- vsync 通知频率：`kFBNotifyVSync` 的定时器周期由 `mfb:1172` 决定；可在 `refresh-contract` 的
  `refresh notification %llu result=%x`（`patches/xnu/zzzz…-pong-refresh-contract.patch:24-27`）上数频率。

**H 级（硬件真相，唯一可采信）**
- 面板 TE/INTF 帧计数 ≈ **120.2/s**：zizhan 实测值（`zizhan:docs/…:69` g155；`:76` g160 默认轮）。
  读法见 §3.2 的 `intfProbe/intfRate`（`zizhan:…:632-660`）。
- 判据格式：`PONG TE after the switch: INTF_1 te 120.x/s frames 120.x/s over NNN ms`（`zizhan:…:648-659`）。
- **没有这一行，就不能声称 120 Hz 生效**（`RPT:L422` 把"软件判据/硬件判据"分开验收的要求）。

**V 级（观感）**
- Dock 左右滑、多任务、设置页切换：60 Hz 面板 + `fb_hz=120` 会出现 33/33/17 ms 的节奏抖动
  （`zizhan:docs/…:33` 的成因分析），切档成功后应变成均匀 8.3 ms。
- 撕裂：cmd 模式面板有 GRAM 自刷新，撕裂概率低（`RPT:L410` 推断）；但 `fb_swapwait=0` 会在面板取帧期间
  被 GPU 覆写，zizhan 明确"不作默认"（`zizhan:docs/…:102-103`）。
- 亮度/颜色/闪烁：切档会同时改面板内部时序，zizhan 的首轮也只做到"用户目测无异常"
  （`zizhan:docs/…:119`），必须人眼过一遍。

### 4.2 反例：怎么知道"其实没生效"

| 现象 | 含义 | 证据 |
|---|---|---|
| S 级 ~120、H 级仍 ~60 | 只改了 `fb_hz`，面板没切 | `RPT:L384`（"只改 fb_hz 不会花屏，效果是 CA 按 8.33 ms 画、显示仍 60 Hz、CPU 拷贝翻倍、撕裂概率升高"） |
| 切档后黑屏/花屏/横纹 | 命令或 PHY/PLL 错（路径 A 未重配 PHY 就发 `0xC6` 的典型后果） | `PLAN:L98-100` |
| 出现 `GPU copy not retired…`，画面冻结 | scanout 进入隔离态，`poisoned` 后不再交接 | `PongAdrenoScanout.cpp:154-157` |
| `PONG GPU ONLY: no completed GPU frame` | CPU 合成被禁且没有 GPU 帧 → 画面停 | `pong:…-pong-gpu-only-display.patch:58-61` |
| 120 Hz 下重帧更多 | GPU 单帧 5–11 ms > 8.33 ms，变成 GPU 受限 | `zizhan:docs/…:72`、`HANDOFF:L238` |

### 4.3 验证顺序（一次一个变量）

1. 只开 GPU scanout（§1），`fb_hz` 仍 60：确认 R1/R3/R5 + 5 秒行的 `us each in the driver` 掉到 ~0。
2. 加 `fb_hz=120`，面板不动：S 级应到 ~120，H 级仍 60，观感应变差（抖动）——这是**预期的中间态**，
   用来证明软件链路已经通了。
3. 发切档命令（§2.3 路径 B 或 A）：H 级到 ~120.2/s 才算成功；同时 V 级人眼确认。
4. 想再压延迟才考虑 `pong_zc_async` / `fb_swapwait=0`（zizhan 的结论是默认不开，
   `zizhan:docs/…:100-103`），**不要和切档混在一轮**。

### 4.4 风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| 面板身份搞错（sharp vs m11a） | 发错私有寄存器 → 黑屏/花屏 | §2.2 定标；未定标前不发任何 DCS |
| DSI 控制器被 ABL/UEFI 占着 | 写入无效、读回异常，甚至挂死 | 先只读 `HW_VERSION/CTRL/STATUS`（`zizhan:…:682-693`）；有先例：触摸 RSC 被固件占用（`RPT:L404`） |
| PLL 位率不足 | 120 Hz 下 underrun/撕裂 | 路径 B 不需改 PLL（`RPT:L397`）；路径 A 必须重锁（`RPT:L415`） |
| `mdp-transfer-time-us=7933` 未随帧率减半 | 传输预算算错，可能掉帧 | `RPT:L437` 列为未验证；切档后用 TE 计数看是否稳定 120 |
| vsync 定时器与真实 TE 未锁相 | CA 提交相位漂移，偶发"差一拍" | `zizhan:docs/…:126-127` 的下一步；本方案不解决 |
| CPU 合成装不下 8.33 ms | 120 Hz 反而更卡 | §1 前置条件；`HANDOFF:L238` |
| 切档后无法回退 | 面板停在错误档位 | 面板状态不落盘，**重启即由 ABL 重新点屏**；不要写任何持久寄存器 |

---

## 5. 无法从现有资料确认的（不要当成已知）

1. **面板身份与档位**：`PLAN:L4` 说 `sharp_qhd_cmd`，`RPT:L396` 说该节点不在 fdt15、真机是 m11a 且三档。
   两份文档互相否定，**没有第三份证据**（原始 dtbo 不在盘上）。这是 ② 必须先定标的原因。
2. **dtbo 原件缺失**：`PLAN:L3` 的 `D:/Android/k60-ios/dtb/` 目录不存在（全盘只找到 `hardware.dtb`，1862 B；
   `dtbo_a_fdt19.dtb` 也没有）。因此 `PLAN:L48` 之外的 34 字节、以及 m11a `timing@2` 的完整 payload
   **都无法在此环境取出**——只能到设备/固件包里重新 dump。
3. **DSI 控制器是否可写**：`RPT:L404`/`L435` 把"ABL 遗留占用"列为待实测；K60 上没有任何人读过
   `0xae94000` 的寄存器。
4. **PLL 当前位率与可重锁性**：`PLAN:L98` 明说"未确认 0210 里 PLL 来源"（实际是根本没有 PLL 代码，
   `RPT:L414`）；`RPT:L404` 说"现配置是否满足 4.42 Gbps 未知"。
5. **INTF 寄存器偏移是否同 SM8450**：`zizhan:…:630-631` 的 `0x35000/0x36000/0x37000/0x38000` 来自 SM8450
   （OnePlus 10 Pro）；K60 是 SM8475，**未在本地核实**。若偏移不同，H 级判据会读错寄存器。
6. **面板上电默认档**：`PLAN` 假定 ABL 留在 60 Hz（`PLAN:L71-72` 的日志），但 m11a 有三档，
   上电是哪一档没有实测记录。
7. **iOS 侧是否真的跟随**：`RPT:L384` 的链路（TimingElements → `UIScreen.maximumFramesPerSecond` →
   `CADisplayLink`）是逆向推断，没有 userspace 实测；`PLAN:L91-92` 还提到"非 Apple 硬件默认 60 / 需要伪装
   ProMotion 机型"，`RPT:L384` 直接否定了这个前提（当前伪装的 iPad7,1 本身就是 ProMotion 机型）。
   两种说法冲突，**未验证**。
8. **`fb_beat` 在 8.33 ms + GPU 5–11 ms 重帧下是否有害**：zizhan 观察到 120 Hz 下重帧变 GPU 受限
   （`zizhan:docs/…:72`），K60 的 GPU 更快/更慢都未知。
9. **构建面是否已开 GPU**：`XNU_PONG_ADRENO_PLATFORM` 默认 0（`scripts/build-xnu-4k-baseline.sh:957`），
   K60 的 CI/镜像是否传 1、`series` 何时加入 scanout 补丁，都不在本仓库的静态证据里（§1.4）。

---

## 6. 一句话交付

先把 §1 的三条构建条件和五条日志判据做实（GPU 真的在写屏），再用**设备上的面板 id** 在 §2.3 的
路径 A/B 里二选一，把整段 52 字节 DCS 长包从 `pong_scanout_frame()` 的入口发一次，
最后用 INTF 帧计数（不是日志里的 "120 Hz"）验收。

---

## 7. 附：zizhan 的相关补丁（只列已读过 hunk 的）

| 补丁 | 作用 | 关键 hunk（补丁文件行号） |
|---|---|---|
| `patches/xnu-ipados18/0013-zizhan-latch-async.patch` | 让 `show()` 不等 latch：翻页返回 3（已翻、latch 未到），SwapWait 去轮询 CTL_FLUSH | `:14` 加 `pong_scanout_latch_poll` 声明；`:22` 加 `bool fLatchAsync`；`:53` `fLatchAsync=scanned==3`；`:82-99` SwapWait 先 poll，阻塞型等待每 1 ms 重查 |
| `patches/metal2vulkan/0021-zizhan-keep-two-empty-blocks.patch` | 修"动画第一帧顿 150–200 ms"（CA 新 surface 触发 64 MiB 块分配+映射） | `:15` `KEPT_EMPTY_BLOCKS: usize = 2`；`:47` `keep = !dedicated && kept_empty < KEPT_EMPTY_BLOCKS` |
| `0011-zizhan-panel-pool-canvases` / `0015-zizhan-panel-slot-mapping` / `0012-zizhan-swapwait` / `0009-zizhan-dpu-flip-cpu-frame` / `0020-zizhan-display-power-observer` | 零拷贝画布池、槽位映射、presented/replaced 语义、每帧 flip、显示电源观察 | **只从 `zizhan:docs/progress/2026-11-01-120hz-and-cadence.md:134-136` 的文件清单读到名字，未逐个读 hunk**（不猜） |

zizhan 的 H 级基线数值（`zizhan:docs/…:10-11`）：切档 8 包 / 5.7 ms，INTF_1 从 60.5/s → **120.2/s**，
moving fps 44.6 → 54–55，单拍（8.3 ms）帧 0 → 270–350。我们的验收线照这个量级定。
