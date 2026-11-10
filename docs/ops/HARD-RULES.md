# K60 移植铁则（HARD RULES）

> **这是唯一权威的「绝对禁止」清单。改任何代码之前必须先读本文件。**
> 与本文件冲突的任何研究文档、agent 产出、历史代码，**以本文件为准**。
> 每条铁则都带「违反后果」和「检查方法」。

---

## 使用方式（强制）

**改代码前**：
1. 全文扫一遍本文件
2. 用 `grep` 检查你要改的文件是否踩到某条铁则：
   ```bash
   # 例：检查是否有 RSC 访问
   grep -n '17a00000\|17a20000\|rsc_phys\|RSC_PHYS' <你改的文件>
   ```
3. 如果踩到，先看「检查方法」确认是否已正确规避

**代码审查时**：按铁则编号逐条 grep。

---

## 铁则 1（HR-01）：**绝对禁止访问 RSC 寄存器**

### 违反后果
**整机立即死，零控制台输出，只能长按电源重启。**

### 禁止范围
| 地址 | 说明 |
|---|---|
| `0x17a00000` | RSC 基址 |
| `0x17a20000` | RSC "DRV 2" 窗口（AP 侧投票窗口）|

**不只是「读寄存器」——连 `ml_io_map()` 映射都可能触发。** 安全做法是不映射。

### 唯一合法替代
| 需求 | 替代方案 |
|---|---|
| 给某个电源轨投票 | **依赖 Android warm boot 已打开的轨道**，XNU 侧不做上电动作 |
| 读 RPMh 状态 | 从 `cmd_db`（`0x80860000`，**普通内存，安全**）读命令 ID，但不发 RSC 事务 |
| 必须上电 | 直接返回 `-EOPNOTSUPP`，让调用方 fail-closed |

### 证据出处
- `GOODIX-TOUCH-PORT.md:99-105`（finding `0246`：注释原文「这台机器上 RSC 一个寄存器都读不得：首次读 TCS 就整机死」）
- finding `0248`（只读探针也以首读死告终）
- `docs/research/touch/05-plan.md:9`
- `docs/research/bt/EVIDENCE.md:86,271`
- `docs/research/power/01-same-hardware.md:32`
- `docs/research/power/02-official-docs.md:15,59`
- `docs/research/power/03-reverse-and-device-data.md:350`

### 检查方法
```bash
# 任何新增/修改的驱动都要过这一条
grep -n '0x17a00000\|0x17a20000\|RSC_PHYS\|rsc_phys' <文件>
```
**命中且不是「注释说明为何不访问」= 违规。**

### 已发生的违规（2026-11-09）
`pong_goodix.c` 的 `touch_thread` 里：
```c
se=ml_io_map(SE_PHYS,SE_SIZE);rsc=ml_io_map(RSC_PHYS,RSC_SIZE);  ← 违规
```
**后果**：`k60_touch_se=1` 时 0 日志整机死，浪费了 **4 轮**排查（前 3 轮都在猜 GCC 时钟）。
**修复**：`rsc = 0;`，从判空条件里删掉 `!rsc`。

### 连带的同类风险（必须一起查）
| 位置 | 风险 |
|---|---|
| `PongAdsp.cpp:45,77,571,576` | 无条件 `mapWindow(gRsc, 0x17a20000, 0x10000)` + `rd(gRsc,0)` → **上电即整机死** |
| `PongPlatformResources.cpp:34-42,47-82` | `IODeviceMemory::withRange(0x17a20000, 0x10000)` → **禁止直接复用** |

---

## 铁则 2（HR-02）：**GENI 控制器（SPI/I2C）访问前必须完成完整前置序列**

### 违反后果
**整机死，零控制台输出**（死在 USB gadget 初始化之前，所以连日志都没有）。

### 必须的前置顺序（来自 sheng `TouchProbe.cpp:399-424`）
1. **GPLL0 投票 + 等 lock**（`GCC+0x62018` bit0，轮询 `PLL_MODE bit31`）
2. **QUP 分支投票**（`GCC_VOTE`，注意 **K60 是 QUP0 用 bit 6-14，不是 sheng 的 QUP1 bit 18-26**）
3. **等分支时钟离 off**，判定式必须含 HWCG（`!(cbcr & CLK_OFF) || (cbcr & 2)`）
4. **配置 TLMM 引脚功能**（在碰引擎**之前**）
5. **映射 SE + wrapper 两个窗**
6. 若 `IF_DISABLE_RO` bit0=1：需要 `use_dma` 或 `allow_fifo_disabled`

### SoC 地址禁止照抄 sheng
| 项 | sheng（SM8550）| **K60（SM8475）** |
|---|---|---|
| QUP wrapper | QUP1 `0xac0000` | **QUP0 `0x990000`** |
| 投票位 | 18-26 | **6-14** |
| GPLL0 enable | `0x52018` | **`0x62018`** |
| GCC 基址 | — | `0x100000` |

**关键**：sheng 在 QUP1 上验证过的「读 CORE 安全」**不能搬到 QUP0**。

### 证据出处
- `QcomGeniSpi/GeniSpi.h:211-212`（「the caller must know that」SE 时钟已在跑）
- `sheng/package/TouchProbe.cpp:399-424`
- `docs/research/GENI-ACCESS-PRECONDITIONS.md`（本文档的详细展开）

### 检查方法
```bash
grep -n 'geni_spi_init\|geni_transfer\|aw882xx_bus_init\|aw882xx_probe_one' <文件>
```
**命中 = 必须有对应的前置序列，且前置序列要在访问前执行完。**

### 已发生的违规（2026-11-09，两次）
| 驱动 | GENI | 结果 |
|---|---|---|
| 触摸 | SPI SE4 `0x990000` | 0 日志挂死 |
| 音频 | I2C `0x880000` | 0 日志挂死 |

---

## 铁则 3（HR-03）：**改任何 MMIO 访问前，先查该地址是否属于「已证明安全」集合**

### 违反后果
同上，整机死。

### 截至 2026-11-09 的实测状态
**已证明安全**（真机执行过且存活）：
```
GCC 窗口 0x1270004, 0x1270008, 0x1274dc, 0x1274e4, 0x1274e8, 0x1274f8, 0x162008
```

**从未执行过**（**新增访问 = 未知风险**）：
```
0x162018 (GPLL0 enable)
0x100000  (GPLL0 mode)
0x133000  (QUP0 CORE_CBCR)
0x13300c  (QUP0 CORE_2X_CBCR)
```

**禁止访问**：
```
0x17a00000, 0x17a20000 (RSC)
```

### 检查方法
```bash
# 列出你新增的所有 MMIO 偏移，逐个对照上面的清单
grep -oE 'gcc \+ 0x[0-9a-f]+' <文件> | sort -u
```

### 新增未知地址的正确做法
不要一次加多个未知访问。**一次只加一个**，上机验证存活后再加下一个。

---

## 铁则 4（HR-04）：**「0 日志」不等于「代码没跑到」——先验证 ring 是否存活**

### 原因
- 触摸/按键驱动在 `bsd_init.c` **1160 行**初始化，早于 `k60_usblog_start()`（**1340 行**）180 行
- 早期 printf 写入 ramoops ring，USB 起来后回放
- **但**：`K60PREV none` 表示 ring 在重启间**不存活**（DRAM 掉电）→ 挂死那次的 printf 永久丢失

### 因此
| 观测到的现象 | 真实含义 |
|---|---|
| 有日志，正常退出 | 代码跑到了，正常返回 |
| **0 日志** | 挂在 **USB 枚举之前**的任何位置，**无法从日志定位** |
| 有 `K60PREV none` | 上次启动的 ring 没保留（正常关机）|
| 有 `K60PREV begin` | 上次是热复位，ring 有内容（罕见）|

### 正确的诊断方法
**分段存活探测**：用 boot-arg 把代码分成 N 段，每段做到底就 return。
- 判据 = `capture.json` 的 `bytes`：**>100KB 活 / =0 死**
- 二分定位，不需要日志

### 检查方法
如果你准备「加 printf 看最后一行」——**先确认 ring 是否存活**（`grep K60PREV` 历史日志）。
如果不存活，改用分段探测。

---

## 铁则 5（HR-05）：**boot-args 必须从 payload 提取验证，不能看打包脚本源码**

### 原因
`packv15.sh` 里的 `G = ("...")` 只是**意图**，实际写进镜像的是 `/tmp/v15.toml` 的内容。
中间任何环节失败（mcopy 失败、模板被覆盖）都会导致「脚本看着对，镜像里是旧的」。

### 正确方法
```bash
ksize=$(python3 -c "import struct,io;print(struct.unpack_from('<I', io.open('$IMG','rb').read(), 8)[0])")
rat=$((4096 + ((ksize + 4095) / 4096 * 4096)))
dd if=$IMG of=/tmp/pay.img bs=1 skip=$rat count=201326592 2>/dev/null
mcopy -n -i /tmp/pay.img ::/EFI/UniXNU/unixnu.toml /tmp/toml.txt
python3 -c "
import io,re
s=io.open('/tmp/toml.txt',encoding='latin1').read()
m=re.search(r'args\s*=\s*\"([^\"]*)\"', s, re.S)
print(len(m.group(1).split()), 'tokens')
"
```

### 已发生的违规
曾验证出 `boot-v15` 镜像实际是 **25 tokens 含 `k60_touch_se=1`**（危险版本），
而 `packv15.sh` 当时显示 24 tokens 无 `touch_se` —— 差点上传了挂死镜像。

---

## 铁则 6（HR-06）：**补丁必须从「真实树」生成，不能手写 hunk**

### 违反后果
- `corrupt patch at line N`
- `unterminated conditional directive`
- 补丁 apply 后丢行（`#endif` 被吞）

### 正确流程
```bash
# 1. clone 一份干净 feed
git clone --shared --no-checkout <feed> /tmp/regen
git -C /tmp/regen checkout --detach <base-commit>
# 2. 按 series 顺序 apply 到「目标补丁的前一条」
# 3. 在真实文件上做编辑
# 4. diff -u 生成补丁
# 5. git apply --check 验证
```

### 补丁插入位置
**新补丁必须放在 series 末尾**，因为它的上下文是按「全部前序补丁应用后」生成的。
插在中间会让后续补丁 apply 失败。

### 已发生的违规（≥4 次）
手写 `@@` 计数导致 `#endif` 被吞、patch 体积从 931 行变 364 行等。

---

## 铁则 7（HR-07）：**series 引用的每个文件必须真实存在且已提交**

### 违反后果
**任何干净 clone 都无法构建。**

### 已发生的违规（2026-11-09 发现）
`patches/xnu/series:195` 引用 `0403-k60-goodix-fw.patch`，该文件**从未提交过**
（commit `6c1e1f1` 只加了 series 那一行）。

### 检查方法（每次改 series 后必须跑）
```bash
cd <repo>
while read -r f; do
  [ -z "$f" ] && continue
  git ls-tree HEAD "patches/xnu/$f" | grep -q . || echo "❌ 未提交或不存在: $f"
done < patches/xnu/series
```

---

## 铁则 8（HR-08）：**构建日志不动 ≠ 构建卡住**

### 原因
`make -j8` 缓冲输出，XNU 的 make 到结束才刷。

### 检查方法
```bash
pgrep -af 'make.*build_all' | head -1   # 有进程 = 在编译
```
**不要**看 `/tmp/build-v15.log` 的 mtime。

---

## 铁则 9（HR-09）：**UI/显示层「已工作」的东西，不要为了「用官方组件」而重写**

### 背景
官方依赖顺序表要求用 `GopFramebuffer` / `DisplayTimingProbe` / `AppleARMBacklight` / `GeniI2c`，
但我们自研的显示层**已在真机验证**：首帧 1440×3200 + 背光 + 120Hz + SpringBoard。

### 规则
- **已 device-verified 的能力**，除非官方组件能解决**具体缺陷**，否则**不动**
- 换组件前必须回答：「现有实现有什么具体问题？官方组件如何解决？」
- 答不出来 = 不换

---

## 铁则 10（HR-10）：**任何「已解决」的结论必须带真机证据，否则标「推断」**

### 禁止的表述
- 「应该能工作」
- 「官方验证过所以我们也行」（SoC 不同，见 HR-02）
- 「代码看起来对」

### 必须的表述
| 级别 | 要求 |
|---|---|
| `device-verified` | 有真机日志/截图，带日志路径 + 行号 + 镜像 sha256 |
| `host-verified` | 有真实编译输出（`rc=0`），不是 `-fsyntax-only` |
| `implemented` | 代码/补丁存在且 apply 干净 |
| `planned` | 只有设计 |
| **推断** | 只有逻辑链，**不得作为动手依据** |

### 官方校验器接受的五个值
`planned` / `implemented` / `host-verified` / `device-verified` / `not-applicable`
（`UniXNU/scripts/porting-record.py` 硬编码）

---


---

## 铁则 11（HR-11）：**区分「构建产物」与「设备盘上状态」**

### 为什么要这条
2026-11-09 审计 agent 搜索 60 个 `boot-*.img` 发现 TWRP 命中 0，
据此判定「TWRP 不可得，可复现性 C 级」。**这个判定是错的。**

真实情况：**TWRP 在设备盘上的 `boot` 分区里**，`fastboot reboot recovery` 就能进。
它不是我们的构建产物，是第三方独立刷入的。

### 规则
搜索某能力是否存在时，必须明确范围：

| 范围 | 决定什么 |
|---|---|
| **构建产物**（`boot-*.img`、`out/`）| 「别人从这个仓构建能拿到什么」|
| **设备盘上状态**（`/dev/block/by-name/*`）| 「维护者这台机器能做什么」|

**用构建产物否定设备能力 = 口径错误。**

### 检查方法
在断言「X 不存在」之前，明确回答：
1. 我搜的是构建产物还是设备盘上？
2. 如果搜的是构建产物，这个能力是否**本来就应该**在盘上（如 TWRP、已格式化分区）？
3. 有没有可能它是「前置条件」而非「构建产物」？

### 已发生的违规
`repro-audit/RISKS.md` §R7 判定 TWRP 不可得（C 级）→ 实际是 B 级（标准刷入操作）。
详见 `docs/TWRP-FACT-CLARIFICATION.md`。


---

## 铁则 12（HR-12）：**派任务/写代码前必须核实「已知前提」，标证据来源和日期**

### 为什么要这条
2026-11-09 派了 5 个 subagent，**3 个推翻了任务书的前提**。不是 agent 出错，
是任务书基于**过时或错误**的假设，导致 agent 花大量时间纠正而非推进。

| Subagent | 任务书写的前提 | 实际（带证据） |
|---|---|---|
| `5898cb8e` OS/电源 | 「DarwinBoot 落后官方 129 行」 | 2539/2829 是**字节**不是行；我们 `DarwinBoot.c` **反而多 28 行**（739 vs 711）|
| `7fe96011` SMMU | 「我们有三份自己写的 SMMU」 | `pong_goodix.c` **零行 SMMU**（5 份副本实测 `smmu=0`）；官方 `ArmSmmu4K` **已在 `drivers/PongAdreno/` 里被编译使用** |
| `7fe96011` 显示 | 「K60 没有 GOP」 | **有**（`SimpleFbDxe` 在 `APRIORI.inc:29`、`DXE.inc:45`）；不适用的理由不同 |
| `77f4d518` 基带 | 「K60 没有 GLINK/QRTR/SMEM」 | **DT 层全在**（`qcom,smem` FDT:11809、`smp2p-modem` 11924、`glink-edge` 11309-11351、`mpss_region` 173-176），缺的是**代码** |

### 规则

**派 agent 前**，对每一个「已知 X」问三句：
1. **证据在哪？**（文件:行号 / 日志行 / commit / sha256）
2. **什么时候的？**（是否可能已过时）
3. **范围对吗？**（构建产物 vs 设备盘上，见 HR-11）

**证据不全的前提，任务书里必须写「待核实」而不是「已知」。**

### 检查方法
任务书里每个「已知/确认/已证实」的断言，后面必须有括号标注：
```
（证据：<文件>:<行号> 或 <日志路径>:<行号>，<日期>）
```
**没有标注的，一律改成「待核实」。**

### 同理适用于写代码
改代码前如果基于某条「已知」，先 `grep` 验证。本轮 `touch_thread` 里
`ml_io_map(RSC_PHYS,...)` 就是因为没核对「RSC 禁止访问」（HR-01 已记录 5 处研究文档），
浪费了 4 轮排查。

### 已发生的违规
- 2026-11-09：5 个任务书里 3 个前提错误
- 2026-11-09：`touch_thread` 违反 HR-01，4 轮排查作废

---

## 铁则 13（HR-13）：**结论必须区分「软件层声称」与「硬件层实测」**

### 为什么要这条
本轮把「120Hz 生效」当成结论写进 `HANDOFF.md`，但实际只是 **`refreshHz()` 返回 120**。
没有发任何 DSI 切档命令（`PongDsiPanel.cpp` 只发 `0x11/0x29/0x51`）。

### 规则
| 表述 | 需要的证据 |
|---|---|
| 「硬件 X 生效」 | 硬件侧测量：示波器 / 面板自报告 / 寄存器回读确认切换 |
| 「软件层按 X 配置」 | 代码路径 + 日志打印 |
| 「日志显示 X」 | 日志原文 |

**禁止**：用「软件层打印了 X」直接推「硬件 X 生效」。

### 检查方法
每写一句「XX 生效/工作/成功」，问：
- 这是**软件发生了什么**，还是**硬件发生了什么**？
- 如果是硬件，**测量手段是什么**？

### 已发生的违规
2026-11-09：「120Hz 生效」→ 实际是软件排帧，面板扫描率未验证。
已记入 `PITFALLS.md` **P-60**。

---

## 附：本文件与其他文档的关系

| 文档 | 用途 | 权威性 |
|---|---|---|
| **本文件（HARD-RULES.md）** | 绝对禁止清单 | **最高** |
| `PITFALLS.md` | 踩过的坑（症状→根因→修复） | 高 |
| `docs/research/<hw>/01-08` | 各硬件八步调研 | 中（可能过时）|
| `HANDOFF.md` | 交接状态 | 中 |
| `porting.toml` | 官方格式的能力记录 | 高（受官方校验器约束）|

**冲突时以本文件为准。**

---

## 维护规则

1. **每条铁则必须有**：违反后果 + 禁止范围 + 检查方法 + 已发生违规
2. **每次踩到新坑**，先判断是「新坑」还是「某条铁则的违反」
   - 是违反 → 在该铁则下追加「已发生违规」
   - 是新坑 → 先加进 `PITFALLS.md`，若它属于「绝对禁止」类，**同时加进本文件**
3. **禁止重排编号**（外部文档有引用）
