# arm64e 探针判据（P0–P4）

本文只定义判据：没有探针代码，没有构建，没有上机。五条硬性要求出自
`E:/hackios/UniXNU/docs/zh/porting/arm64e.md:16-25`；那一次 F0 捕获的原始值与限制在
`docs/research/power/12-ARM64E-EVIDENCE.md`。本文是 P0–P4 判据的唯一位置，12 号文只留证据，
避免两个地方各写一套期望值。

判词只有三种：`PASS`、`FAIL`、`INCOMPLETE`（以及输入本身不成立时的 `INVALID`）。
“一个核算出来”不是 `PASS`；“八个核里七个没读”不是 `FAIL`，是 `INCOMPLETE`；
“八个核读了但 MPIDR 重复”是 `INVALID`，不是 `PASS`。

## 1 先做普查：八核逐核一行

SM8475 的硬件 MPIDR 是扁平的 `0x000`…`0x700`，Aff1 就是 CPU 序号；Android sysfs 的
`4/3/1` 是 L2/L3 缓存簇，不是 MPIDR。下表是**预期**，不是测量：每一行必须由探针打印的
`MPIDR_EL1` 与 `MIDR_EL1` 填，不能抄表。

| CPU | 预期 `MPIDR_EL1` | 预期 `MIDR_EL1.PartNum` | 核 | Android 的 L2/L3 簇 |
| --- | --- | --- | --- | --- |
| 0 | `0x000` | `0xD46` | Cortex-A510 | 0 |
| 1 | `0x100` | `0xD46` | Cortex-A510 | 0 |
| 2 | `0x200` | `0xD46` | Cortex-A510 | 0 |
| 3 | `0x300` | `0xD46` | Cortex-A510 | 0 |
| 4 | `0x400` | `0xD47` | Cortex-A710 | 1 |
| 5 | `0x500` | `0xD47` | Cortex-A710 | 1 |
| 6 | `0x600` | `0xD47` | Cortex-A710 | 1 |
| 7 | `0x700` | `0xD48` | Cortex-X2 | 2 |

`MIDR_EL1.PartNum` 是 `[15:4]`；实施者 `Implementer` 是 `[31:24]`，ARM 为 `0x41`。
MPIDR 的 `Aff1` 是 `[15:8]`、`Aff0` 是 `[7:0]`；扁平表意味着 `Aff1` 等于 CPU 序号、
`Aff0` 为 0。实际值与上表不符时记录实际值，不要为了对上表去改探针的绑核。

来源：MPIDR 扁平表在 `docs/plans/MONDRIAN-OFFICIAL-PAGES.md:154-156`；CPU 4/3/1 的域映射在
`docs/research/power/01-EPSS-PROBE.md:51-52`；PartNum 0xD46/0xD47/0xD48 在
`docs/reference/AGENT-COORDINATION-route-a-18.md:9`；八核常量在
`drivers/PongPower/K60CpuFreqPlan.h:27`。

## 2 P0：每个核重读 ID 寄存器

### 2.1 读什么

每个核执行：

- `MRS x0, ID_AA64ISAR1_EL1`
- `MRS x1, ID_AA64ISAR2_EL1`
- `MRS x2, MPIDR_EL1`
- `MRS x3, MIDR_EL1`

`ID_AA64ISAR1_EL1` 的字段偏移以 `E:/hackios/xnu-12377/osfmk/arm64/proc_reg.h:3139-3172`
为准：`APA [7:4]`、`API [11:8]`、`GPA [27:24]`、`GPI [31:28]`。`ID_AA64ISAR2_EL1`
的 `APA3`/`GPA3` 只写字段名，不抄位偏移：本仓 12377 的 `proc_reg.h:3174-3184` 只定义
`WFxT`/`RPRES`/`BC`/`CSSC`，没有 `APA3`/`GPA3`；照旧 header 借偏移会读到别的字段。
探针打印 ISAR2 原值，解码时用 ARM ARM 当前字段表，并在结果里写清用了哪一版。

### 2.2 通过条件

逐核判：

`((APA | API) != 0 && (GPA | GPI) != 0) || (APA3 != 0 && GPA3 != 0)`

这是页面 `arm64e.md:18` 的**成对**规则，不是四个字段都非零。`APA` 与 `API` 是地址组的
两种编码，`GPA` 与 `GPI` 是通用组的两种编码；`APA3`/`GPA3` 是 ISAR2 上的另一条路，
两组必须同时存在才算那条路成立。

### 2.3 失败形状

- 某个核的地址组为 0，且 `APA3`/`GPA3` 不同时非零：该核 `FAIL`。
- 某个核的通用组为 0，且 `APA3`/`GPA3` 不同时非零：该核 `FAIL`。
- `MRS` 在 EL1 产生同步异常（`ESR_EL1.EC=0x18`，或实际落到 EL2 后没有返回）：记录异常形状，
  该核 `INCOMPLETE`；不要把它写成“没有 PAuth”。
- 某个核根本没跑起来或没打印：该核 `INCOMPLETE`；八行不齐时整次 P0 不能判 `PASS`。

### 2.4 要打印的那一行

`P0 cpu=%u mpidr=%#llx midr=%#llx isar1=%#llx isar2=%#llx apa=%u api=%u gpa=%u gpi=%u verdict=%s`

原始值和判词分开打印。判词行只能引用同一行的原始值；不要再出现“判读层的 gate 把四个字段
全要求非零”那种把判词 bug 当成被测对象结论的形状（P-274）。

### 2.5 F0 那串数字怎么读

F0 记录的是 `ISAR1=0x0010011101211052`、`ISAR2=0`，只读了一个核，镜像没有哈希。
按上面的偏移解出 `APA=0b0101`、`API=0`、`GPA=1`、`GPI=0`：`0b0101` 是
`FPACCOMBINE`（`1=PAuth、2=EPAC、3=PAuth2、4=FPAC、5=FPACCOMBINE`），不是
“PAuth + EPAC + PAuth2”三个编码相加；`API=0` 是地址组的第二种编码为 0，不是“通用密钥
PACGA 不在”——通用组由 `GPA=1` 满足。按页面成对规则，被读到的那一个核满足第 1 条；
另外七个核没读，所以整次 P0 仍是 `INCOMPLETE`。

那次探针自己的 `RESULT no FEAT_PAuth` 来自 `apa && api && gpa && gpi` 这个 gate，以及把
`GPA`/`GPI` 读成 `[15:12]/[19:16]`（那是 `JSCVT`/`FCMA`）。**只能引原始数字，
不能引那行判词。**

### 2.6 能证明 / 不能证明

| 能证明 | 不能证明 |
| --- | --- |
| 被读到的每个核，这一次启动时 ID 寄存器的原始值，以及按字段表解出的 APA/API/GPA/GPI | 密钥寄存器可写；PACIA/AUTIA 可执行；内核已经启用 PAC |
| 八核是否被真正采到、MPIDR 是否互异 | 下一次启动或另一个镜像的相同值（镜像哈希必须一起记） |
| 哪个核与另外几个核不同 | 不同是因为熔丝、固件、集群掉电还是探针绑核错误（那要下一层证据） |

## 3 Census, not sample

**Census 是八行，不是一行加一句总结。** 页面要求“每个启用的 CPU”，ID 寄存器又是 per-PE 的；
一个核的 `APA` 不能外推到八个核。异构的 A510/A710/X2 可以有不同的实现或熔丝，固件可以关掉
某个核的 PAC，探针也可能只在启动核上跑了一圈却打印了“所有核”。

只有一核报 `0b0101` 时，按下面判，不要取最大值、不要平均、不要用 `MIDR` 反推：

| 观测 | 判词 | 下一步 |
| --- | --- | --- |
| 八行都在，八行都满足成对规则 | `PASS P0` | 记哈希，进 P1/P2 |
| 八行都在，只有一行 `0b0101`，其余七行两组里有 0 | `FAIL P0`（或 `SPLIT`） | 不能说“SoC 支持 PAC”；查那七个核是熔丝、固件还是探针绑核 |
| 只有一行，另外七行没打印 | `INCOMPLETE` | 先把八个核都跑起来；现在既不能判过也不能判不过 |
| 八行都在，但 MPIDR 重复或漏了某个 CPU | `INVALID` | 绑核/迁移错了，重测；重复行不是八核证据 |
| 八行都在，一行 `0b0101`，其余行 `MRS` 异常 | `INCOMPLETE` | 记录异常；异常不是“没有 PAuth” |
| 八行都在，一行 `0b0101`，其余行是“CPU_ON 失败/没起来” | `INCOMPLETE` | 先修 bring-up；不要把没跑起来的核算成 0 |

一句话：**“一个核报 0b0101”只能写成“八个采样核中的一个报 0b0101”，不能写成“这颗 SoC 支持
PAC”。** 这句话要贴在结果旁边，不是贴在章节开头。

## 4 P1：五组密钥寄存器（10 个 MSR）

### 4.1 读写哪些寄存器

| 组 | 低 64 位 | 高 64 位 |
| --- | --- | --- |
| A 地址 | `APIAKeyLo_EL1` | `APIAKeyHi_EL1` |
| B 地址 | `APIBKeyLo_EL1` | `APIBKeyHi_EL1` |
| A 数据 | `APDAKeyLo_EL1` | `APDAKeyHi_EL1` |
| B 数据 | `APDBKeyLo_EL1` | `APDBKeyHi_EL1` |
| 通用 | `APGAKeyLo_EL1` | `APGAKeyHi_EL1` |

同时读 `SCTLR_EL1` 的四个独立使能位：`EnIA[31]`、`EnIB[30]`、`EnDA[27]`、
`EnDB[13]`。`[29:28]` 是 RES1，不是 EnDA/EnDB；`[31:28]=0xF` 不能证明四个位都开了
（`proc_reg.h:610-624`）。

### 4.2 什么时候写

- **XNU 第一次使用 PAC 之前**：boot CPU 可以写五组新值（五组各不相同，Lo/Hi 各 64 位），
  立即读回。若此时 `SCTLR_EL1` 的 EnIA/EnIB/EnDA/EnDB 已有非零位，说明 PAC 已经在用，
  不要覆盖活密钥；记录现状，P1 判 `INCOMPLETE`，等一个更早的探针点。
- **XNU 起来之后**：只在每个核上做“读原值→写回同一个值→再读”的安全测试；不要改活密钥再恢复，
  那会让已经签过的指针失效。这个测试能证明“MSR 完成且值没变”，不能单独证明“没有陷入 EL2”。
- **每个核都要做**。只做 boot CPU 时，P1 只能写“boot CPU”，整次判 `INCOMPLETE`；页面要求的是
  XNU 能写五组寄存器，不是“一个核能写”。

### 4.3 通过条件

- 五个 128 位值逐组读回相等（Lo 与 Hi 分别比较，不要拼错字节序）。
- XNU 之后四个使能位全为 1。
- 每个被采到的核都满足；缺一个核就是 `INCOMPLETE`。

### 4.4 失败形状

- `MSR` 没有完成，或 EL1 收到同步异常 `ESR_EL1.EC=0x18`（MSR/MRS trap）：该核 `FAIL`。
  如果陷进 EL2 后没有回到 EL1，EL1 可能根本看不到 ESR；记录实际向量和“没有返回”，不要
  假装看到了 `EC=0x18`。
- 读回值与写入值不同：`FAIL`（寄存器别名、写被忽略、或探针读错寄存器）。
- XNU 之后四个使能位仍为 0：`FAIL`（密钥写了但 PAC 没启用）。
- 只做了 boot CPU，或只在 XNU 之后写回原值而没有异常证据：`INCOMPLETE`，不是 `PASS`；
  EL2 静默模拟时 EL1 看不到陷入，这一点必须在结果里写明。

### 4.5 要打印的那一行

`P1 cpu=%u mpidr=%#llx key=%s lo=%#llx hi=%#llx back_lo=%#llx back_hi=%#llx sctlr=%#llx`

### 4.6 能证明 / 不能证明

| 能证明 | 不能证明 |
| --- | --- |
| 被测核在 EL1 执行了五组密钥寄存器的写/读，且读回一致 | EL2 没有把这些访问陷入并静默模拟（EL1 看不到 HCR_EL2/ESR_EL2） |
| XNU 之后四个使能位是否真的置 1 | 密钥的随机性、每启动唯一性、或密钥没有被别的代码覆盖 |
| 哪个核没有完成 | 所有启用核都会在真实用户态路径上使用这组密钥 |

## 5 P2：每核 PACIA/AUTIA 往返（EL1 和 EL0）

### 5.1 前置

先确认 `SCTLR_EL1.EnIA[31]` 为 1。`EnIA=0` 时 `PACIA` 按架构是 NOP，“指针没变”
不是“没有 PAC”的证据，只能判 `INCOMPLETE`。

### 5.2 EL1 往返

对每个核，取局部对象地址 `p`（栈或静态对象，规范地址），用固定 `modifier`：

1. `s = PACIA(p, modifier)`；要求 `s != p`。
2. `AUTIA(s, modifier) == p`；不相等即 `FAIL`。
3. 同一次运行：`PACIB(p, modifier) != s`；对 `s` 做 `AUTIB` 必须失败（`EC=0x1C`）
   或返回 `!= p`。A/B 两组密钥必须不同，
   跨密钥还原成功说明密钥没有分开或探针用错了寄存器。先确认 A/B 的 128 位值不相等（P1 的
   读回或 XNU 的密钥表）；相等时 P2 判 `INCOMPLETE`，不要用一个必然相同的签名去证明“分开”。
4. 用三组不同的 `(p, modifier)` 重复；三组都出现 `s == p` 才判“没有改指针”，一组相同按
   PAC 碰撞处理，重测。

### 5.3 EL0 往返

同一组往返从用户态跑一遍，并证明它跑在哪个核上。EL0 不能读 `MPIDR_EL1`，所以每核归属
不能靠用户态自报：由内核在进入 syscall 时记录当前 `MPIDR_EL1`，用户态把结果与该记录配对；
没有配对就是 `INCOMPLETE`。EL0 不需要读密钥寄存器，EL0/EL1 共用同一组密钥
（`arm64e.md:52-54`）。

### 5.4 失败形状

| 观测 | 判词 | 说明 |
| --- | --- | --- |
| `PACIA` 处 `ESR_EL1.EC=0x00` | `FAIL` | 指令 UNDEFINED：该核没有实现这条指令，或探针跑在错误的异常级 |
| `PACIA` 处 `ESR_EL1.EC=0x09` | `FAIL` | `ESR_EC_PTRAUTH_INSTR_TRAP`：PAC 指令被陷入（通常是 `HCR_EL2.API=1`，但 EL1 读不到 HCR_EL2） |
| `MSR` 处 `ESR_EL1.EC=0x18` | `FAIL` | 密钥寄存器访问被陷入；P1 也会看到同类形状 |
| `AUTIA(s) != p` | `FAIL` | 签名/还原不匹配；先排除 modifier、字节序、密钥组用错 |
| `PACIA` 完成但 `s == p` 且 EnIA=1 | `FAIL` | 指令被当成 NOP，或探针读错寄存器；不是“PAC 正常” |
| 跨密钥 `AUTIB(PACIA(p))` 成功返回 `p` | `FAIL` | A/B 没有分开，或探针用了同一组密钥 |
| `AUTIA` 用错 modifier/key 后，`ESR_EL1.EC=0x1C`（`ESR_EC_PAC_FAIL`） | 记录，不判 P2 失败 | FPACCOMBINE 在认证指令上同步失败；这是“失败形状正确”，不是“往返通过” |
| 用错 modifier/key 后，`ESR_EL1.EC=0x21`/`0x25`（IABORT/DABORT EL1） | 记录，不判 P2 失败 | pre-FPAC 的坏指针在**使用**时才 abort；两种形状都要能解释 |

`HCR_EL2` 在 EL1 读不到。页面 `arm64e.md:24` 写“清除 `HCR_EL2.APK/API` 会使访问陷入”，
与 ARM ARM 的“置 1 生效”相反；本文按 ARM ARM 的“置 1 生效”理解，但探针只记录实际
`ESR_EL1` 形状和“有没有返回”，不去猜 HCR 的位值。陷进 EL2 后 EL1 可能什么都看不到，
这种情况判 `INCOMPLETE`，不能判 `PASS`。

### 5.5 要打印的那一行

`P2 cpu=%u mpidr=%llx el=%u p=%llx s=%llx back=%llx s_b=%llx`

### 5.6 能证明 / 不能证明

| 能证明 | 不能证明 |
| --- | --- |
| 被测核在 EL1 和 EL0 执行 PACIA/AUTIA 时指针确实改变并还原 | 内核所有指针类（函数指针、数据指针、ObjC 消歧）都用了正确密钥 |
| A/B 两组密钥在往返中确实不同 | 用户态每个进程都被正确签名；dyld/kernel collection 的签名链完整 |
| 失败形状是 UNDEFINED、PTRAUTH trap、PAC fail 还是 abort | `HCR_EL2` 的配置值（EL1 不可见） |

## 6 P3：SoC 支持页

这一条没有寄存器，是行政项，必须排在 P0–P2 之后。

- 通过：`E:/hackios/UniXNU/docs/zh/porting/soc-support.md` 点名 SM8475 与
  `xNekom/UniXNU-sm8475-common`（`feeds.toml:7-14` 固定
  `20a30fd623dbcfacdd71350a24fae67a2158884f`），并且 P0–P2 的结果按 `arm64e.md:25`
  记进设备的 `porting.toml`。
- 失败：两页仍只有 SM8550；或入了表但 P0–P2 没有带 `file:line` 的结果。
- 注意两个不同的门：`arm64e.md:21` 要求“SoC 仓库列在 SoC 支持页”，`arm64e.md:29-31` 的
  “受支持设备”表是另一件事。现在 `soc-support.md:126-134` 只把 SM8550 当示例，
  受支持设备表只有 sheng/SM8550/开发中。

| 能证明 | 不能证明 |
| --- | --- |
| 文档层面列了 SM8475 与该仓库 | 硬件本身有 PAC；P0–P2 的结果是真的 |
| 入档流程走完 | 别的 SM8475 板子也能用同一结论 |

## 7 P4：运行期 TCR 的两个 granule

构建常量（`porting.toml` 的 granules 证据）：`TCR_EL1_BOOT=0x00000022a5192519`，
`T0SZ=T1SZ=25`（39 位 VA），`TG0=0b00`、`TG1=0b10`，`ARM_PGBYTES=4096`，
`ARM_PGSHIFT=12`；`scripts/check-ios27-granules.sh:35-40` 断言的就是这两个字段。

运行期在 pmap 初始化后、第一次返回用户态后各读一次 `TCR_EL1`，只比字段：

- `TG0 [15:14] == 0b00`
- `TG1 [31:30] == 0b10`

不要拿整个寄存器跟 `TCR_EL1_BOOT` 比：ASID/IRGN/ORGN/SH/EPD/TBI/IPS 在运行期会合法地变。
也不要把 TG0 与 TG1 当同一个编码：TG0 的 4 KiB 是 `0b00`，TG1 的 4 KiB 是 `0b10`，
两个值本来就不相等。

- 通过：F2 的 stage-0 镜像到 `bsd_init`，两处日志里两个字段都对。
- 失败：pmap 初始化 panic；任一字段不是 4 KiB 的编码。
- 16.6.1 的 4 KiB 启动说明这颗 SoC 与启动链能做 4 KiB 翻译，不替代 12377/arm64e 的运行期
  `TCR_EL1` 检查。

| 能证明 | 不能证明 |
| --- | --- |
| 被读到的核在那一刻的 stage-1 granule 是 4 KiB | stage-2 granule；每个进程的地址空间；16.6.1 那条线的 12377 行为 |
| `TCR_EL1_BOOT` 与运行期字段的一致性 | 4 KiB 页表的所有边界条件（大页、COW、压缩）都正确 |

## 8 探针没写回来怎么办

**没有那一行，不等于硬件没有那个能力。** 日志里“P1 没出现”至少有三种原因，判词完全不同：

| 日志形状 | 发生了什么 | 判词 | 能写进结论的句子 |
| --- | --- | --- | --- |
| 没有 `K60PAC: probe ... start`，也没有任何 `P0`–`P4` 行 | 探针没进镜像、没被选中、没执行 | `INVALID`（这次捕获不是探针证据） | “这次启动没有跑探针”，不是“没有 PAC” |
| 有 `start` 行，但只到某一步，后面整段没有 | 探针跑了，停在半路（CPU_ON 失败、异常、提前返回） | `INCOMPLETE` | “探针跑到 Pn 之前/第 n 个核”，不是“硬件不支持” |
| 有该步的行，行里有 `verdict=FAIL`、`EC=...` 或读回不相等 | 探针到了，测到了负结果 | 按该步判 `FAIL`/`INCOMPLETE` | “这一核这一步返回了这个形状” |

判定的第一步不是看 P0/P1 的数字，而是看**探针自己有没有留下开始、步进、结束三种标记**。没有这三种标记，日志只能证明“没有输出”，不能证明“没有能力”。

### 8.1 探针必须留下的三种标记

这不是新代码，是探针实现和验收时要对齐的日志契约。

| 标记 | 例子 | 用途 |
| --- | --- | --- |
| 开始 | `K60PAC: probe v3 start image_sha256=<64 hex> cpus=8` | 证明探针在镜像里并执行了；没有它，后面所有缺失都归“没跑” |
| 步进 | `P0 begin`、每核一行、`P0 end ok=8 missing=0`；P1/P2/P4 同样 | 把“做到哪”和“结论是什么”分开；缺的是行，不是能力 |
| 结束 | `K60PAC: done P0=PASS P1=INCOMPLETE P2=SKIP P4=NO-BSD_INIT` | 证明探针走完了；没有它，日志末尾的空白是“没走完” |

没有 `start` 行时，先查镜像哈希和补丁是否在镜像里，再谈硬件；没有 `done` 行时，先查最后一条步进行，再谈“没有输出”。

### 8.2 P0–P4 各自的识别字形

| 判据 | 正常应有的行 | 少行时先判 | 到了但失败的形状 |
| --- | --- | --- | --- |
| P0 | `P0 begin` + 八行 `P0 cpu=... mpidr=... isar1=... isar2=... verdict=...` + `P0 end` | 0 行：探针没跑/没到；1–7 行：缺哪几核就列哪几核，`INCOMPLETE`；八行但 MPIDR 重复：`INVALID` | 某核 `EC=0x18`：`INCOMPLETE`（MRS 被陷入，不是“没有 PAuth”）；某核两组全 0：该核 `FAIL` |
| P1 | `P1 begin` + 每核每密钥一行 + `P1 end` | 完全没有：先看 P0 是否 PASS、探针是否在写密钥前退出；只有 boot CPU：`INCOMPLETE` | `EC=0x18`、读回不等、XNU 后 En 位为 0：`FAIL`；只有写回同值：`INCOMPLETE` |
| P2 | `P2 begin` + 每核 EL1/EL0 行 + `P2 end` | 完全没有：若 P1 未完成，P2 本来就不该跑；若 P1 完成仍没有，探针没进 P2 | `s==p` 且 EnIA=1、`AUTIA(s)!=p`、跨密钥成功：`FAIL`；`EC=0x00/0x09/0x18`：按表判 `FAIL`；`EC=0x1C`：记录形状，不判 P2 失败 |
| P3 | `P3 begin` + 页面/仓库/commit 行 + `P3 end` | 没有：行政步骤没做，不是硬件结论；P0–P2 未完成时 P3 不能单独 PASS | 页面仍只有 SM8550：`FAIL`；入了表但无 `file:line`：`FAIL` |
| P4 | `P4 begin` + 运行期 `TCR_EL1` 两次读数 + `P4 end` | 没有：先看 F2 是否到 `bsd_init`；没到就没有运行期 TCR，判 `INCOMPLETE` | `TG0!=0b00` 或 `TG1!=0b10`：`FAIL`；pmap panic：记录 panic，不判“4 KiB 不支持” |

**尤其注意 P0 的一行与八行**：F0 只有一行，另外七行不是“七个核没有 PAC”，而是“七个核没采到”。只有 `start` + `P0 begin` + 八行 + `P0 end` 同时存在，八行才是普查；否则最多是“一个核的样本”。

### 8.3 三种失败为什么在日志里长得一样

三种都表现为“你要找的那行不在”：

- 探针没跑：整段没有，连 `start` 都没有；
- 跑了一半：有 `start`，有前几步，缺后几步；
- 跑了但失败：行在，判词/异常在行里。

如果探针不打印 `start`/`begin`/`end`，后两种就和第一种无法区分；如果只打印最终判词，失败和没跑也无法区分。**所以先修日志契约，再修判据。** 看到空白时，答案不是“硬件不支持”，而是“这次捕获无法判定”，并把缺的标记列出来。

### 8.4 一次捕获的判词顺序

1. 日志为空、被截断、或没有镜像哈希：`INVALID`，先重捕；零字节日志不是挂起证据（P-118）。
2. 没有 `K60PAC: probe ... start`：`INVALID`，先确认镜像里有没有探针；不要进入 P0–P4。
3. 有 `start`、没有 `done`：按最后一条步进行判 `INCOMPLETE`，并写明停在哪一步、哪个核。
4. 有 `done`：按 §2–§7 的判据逐项判；`SKIP` 不是 `PASS`，`INCOMPLETE` 不是 `FAIL`。
5. 只有这时才把结果写进 `porting.toml`；缺行写缺行，异常写异常，不写“支持/不支持 PAC”。

## 9 上机前必须已经在镜像里

这一节是**上机前的镜像清单**，不是上机后的判词。飞行窗口只有一次：镜像里没有探针，
日志里就没有那一行，事后无法补测；缺行只能记“这次没测”，不能记“硬件不支持”。
所以先确认下面每一类行都在镜像里，再谈它跑出来是什么。

### 9.1 镜像本身

- 探针源码已经编进内核并链接进 `kernel.macho`，不是启动后再加载的 kext，也不是
  只放在文件系统里的脚本。
- 镜像里能找到启动行的格式串，且第一条 `K60PAC` 行就是它：

  ```
  K60PAC: probe v3 start image_sha256=<64 hex> cpus=8
  ```

- 启动前先对**实际要飞的那个文件**算 sha256，并让它与 `start` 行里的值逐字相等；
  不相等说明飞的不是这份镜像，整份捕获作废。
- 串口捕获在 boot 之前挂好；零字节日志不是“没能力”，是没抓到（P-118）。
- 版本号写进 `start` 行。没有版本号时，无法区分“旧探针少打了一行”和“新探针没跑”。

### 9.2 每一步必须有的行

这些是日志契约的形状。字段名可以按实现微调，但**每一行必须能单独回答
“哪个核、哪一步、读到什么、判词是什么”**；只打最终判词不够。

| 步骤 | 必须已经在镜像里的行 | 一行至少要带的字段 |
| --- | --- | --- |
| 启动 | `start` | 探针版本、镜像 sha256、`cpus=8` |
| P0 | `P0 begin`、每核一行、`P0 end` | `cpu`、`mpidr`、`midr`、`isar1`、`isar2`、`apa/api/gpa/gpi`、`verdict` |
| P1 | `P1 begin`、每核每密钥一行、每核 SCTLR 一行、`P1 end` | `cpu`、密钥名（APIA/APIB/APDA/APDB/APGA）、写入值、读回值、`verdict`；SCTLR 要带 `EnIA/EnIB/EnDA/EnDB` |
| P2 | `P2 begin`、每核 EL1 与 EL0 各一行、跨密钥检查行、`P2 end` | `cpu`、`el`、`p`、`s`、`autia`、`ec`、`verdict` |
| P3 | `P3 begin`、页面/仓库/commit 一行、`P3 end` | 页面路径、仓库、commit、P0–P2 结果位置 |
| P4 | `P4 begin`、两次运行期 `TCR_EL1` 行、`P4 end` | `stage=pmap|user`、`tcr`、`tg0`、`tg1` |
| 结束 | `done` | 每个 P 的最终判词；`SKIP` 与 `INCOMPLETE` 要原样出现 |

P0 的八行必须是八个不同的 `mpidr`。只有一行时，那一行是样本；八行齐全才是普查。
P1 的“每核每密钥”是五个密钥都要有写与读回，不是只写一组 A 密钥。
P2 的每个核要分别有 EL1 与 EL0；只有 EL1 不能替代 EL0。

### 9.3 异常必须带 EC

以下异常码是 P2 判词要区分的形状，探针的异常处理必须把它们打印出来，
不能只打印“trap”或直接静默返回：

| EC | 名称 | 探针必须打印 |
| --- | --- | --- |
| `0x00` | UNDEFINED | `EC=0x00 ESR=<hex> EL=<1|0>` |
| `0x09` | PTRAUTH instruction trap | `EC=0x09 ESR=<hex> EL=<1|0>` |
| `0x18` | MSR/MRS trap | `EC=0x18 ESR=<hex> EL=<1|0>` |
| `0x1C` | PAC fail | `EC=0x1c ESR=<hex> EL=<1|0>` |
| `0x21` | instruction abort | `EC=0x21 ESR=<hex> EL=<1|0>` |
| `0x25` | data abort | `EC=0x25 ESR=<hex> EL=<1|0>` |

没有 `EC` 行的异常，只能证明“发生了异常”，不能证明是哪一类；这次捕获对该步是
`INCOMPLETE`，不是 `FAIL`，更不是“硬件不支持”。

### 9.4 缺什么就不能飞什么

| 镜像里缺的东西 | 这次飞行不能得出的结论 | 正确判词 |
| --- | --- | --- |
| 没有 `start` 格式串，或镜像 sha256 对不上 | 不能得出任何 PAC 结论 | `INVALID`，先修镜像/捕获 |
| 有 `start`，没有 P0 八行 | 不能写“八核都有/都没有 PAC” | 只写已采到的核；其余 `INCOMPLETE` |
| 没有 P1 五行/五组读回 | 不能写“密钥已写入” | P1 `INCOMPLETE` |
| 没有 P2 的 EL1/EL0 行 | 不能写“EL0/EL1 的 PAC 可用” | P2 `INCOMPLETE` |
| 没有 P4 的运行期 TCR 行 | 不能写“运行期仍是 4 KiB” | P4 `INCOMPLETE`，先确认到 `bsd_init` |
| 没有 `done` | 不能写“探针走完” | 按最后一条步进行判 `INCOMPLETE` |

### 9.5 起飞前后各一条命令

同一个检查器先对镜像、再对镜像加串口各跑一次：

```sh
python3 scripts/check-pac-probe-capture.py --image <image>
python3 scripts/check-pac-probe-capture.py --image <image> --log <console.log>
```

第一条只回答「镜像里有没有 `K60PAC: probe v3 start` 这段格式串」：有就 `PASS`，
没有就 `INVALID` 并点名缺的字符串。它证明的是镜像里没有这段串，不是硬件没有
PAuth；格式串在、`start` 行却没出现，先查探针的选择/调用路径与串口，再谈 P0–P4。

第二条在飞行后判 P0–P4 与 `done` 是否都在：`INCOMPLETE` 会点名缺的那一行
（如 `P0 core=3 line`），`INVALID` 保留哈希/版本/CPU 数不符的原因，只有 `PASS`
才表示捕获合约完整，不表示 PAC 实验通过。退出码 0 PASS、1 INCOMPLETE、
2 INVALID、3 读不到文件。

## 10 结果怎么入档

每个 P 的结果至少带：镜像路径、字节数、sha256、串口原文、日期、探针版本、每核一行。
只写“支持 PAC”不算结果；只写“一个核 0b0101”也不算八核结果。

| 判据 | 入档位置 | 写法 |
| --- | --- | --- |
| P0 | `porting.toml` 的 `ios27-arm64e` evidence/limits | 八行原始值 + 每核判词；缺核写 `INCOMPLETE` |
| P1 | 同上 | 每个核的五组读回 + SCTLR 四位；只做 boot CPU 要写明 |
| P2 | 同上 | 每个核 EL1/EL0 的 `p/s/back` 与失败形状 |
| P3 | 同上 + `soc-support.md` | 页面链接、仓库、commit、P0–P2 的结果位置 |
| P4 | 同上 + `scripts/check-ios27-granules.sh` | 构建常量 + 运行期 `TG0/TG1` |

`docs/engineering/IOS27.md` 由 Lead 维护，本文不改它；它里面 F0 的捕获表只作为证据引用。
`porting.toml` 的 limits 不能再写“FEAT_PAuth is present”这种把一核原始值说成整机结论的句子；
应写成“F0 只读了一个核，APA=0b0101/API=0/GPA=1/GPI=0；其余七核、密钥写与 PACIA/AUTIA 未测”。

## 11 复现与引用

```sh
# 构建常量（host）
sh scripts/check-ios27-granules.sh ../UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree
```

页面：`E:/hackios/UniXNU/docs/zh/porting/arm64e.md:16-25`（五条要求、HCR 说明、入档要求）、
`:29-31`（受支持设备）、`:40`（缺省 arch）、`:52-54`（共用密钥与四个使能位）；
`E:/hackios/UniXNU/docs/zh/porting/soc-support.md:126-134`（SM8550 示例）。

本仓：`porting.toml` 的 `ios27-arm64e`、`feeds.toml:7-14`、`board.toml:332,368,378`、
`patches/xnu/series:19-21`、`docs/engineering/IOS27.md:73-83`（16 线的 4 KiB）与
`:245-276`（F0 捕获）、`patches/ios-mondrian/pac-probe-arm64e-gate.patch`、
`docs/engineering/PITFALLS.md`（P-255、P-274）。

内核：`E:/hackios/xnu-12377/osfmk/arm64/proc_reg.h:610-624`（SCTLR 使能位与 RES1）、
`:3139-3172`（ISAR1 偏移与 API 枚举）、`:3174-3184`（ISAR2 现有字段）、
`:2517`/`:2541`（`ESR_EC_PAC_FAIL=0x1C`）、`:2539`（`ESR_EC_MSR_TRAP=0x18`）、
`:2531`（`ESR_EC_PTRAUTH_INSTR_TRAP=0x09`）、`:2547`/`:2550`（IABORT/DABORT EL1）、
`osfmk/arm/commpage/commpage.c:509-517`（FPAC 特征位取自 API）、
`osfmk/arm64/platform_tests.c:2050-2071`（两种认证失败形状的断言）。

arm64e profile：`E:/hackios/UniXNU/profiles/arch/arm64e/patches/xnu/series` 与
`E:/hackios/UniXNU/patches/xnu-12377/native-pac-keys.patch`（十个密钥字、`HAS_NATIVE_PAC`）。

sheng：`E:/k60-work/references/UniXNU-sheng`（`patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch`、
`hal/ShengAudioPlugIn.c`、`board.toml`；同一 OS 目标、不同 SoC）。它只证明“同一代 12377
arm64e 内核在非 Apple SoC 上走签名路径”，不能替代本板的 P0–P2。
