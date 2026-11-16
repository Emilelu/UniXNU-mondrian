# WiFi silent 死因与固件 blob 的 residency

> 底稿：本页由 `feat/wifi-ledger-fold` 分支上的两版账本（`96e0a23`、`f9e5d0c`）重排而成。
> 那一支保留「排除法怎么一格一格走」的全过程与每一版被推翻的措辞；本页只写当前事实
> 与当前结论。要查某条判断是哪天、被哪张镜像推翻的，看那一支。

状态（2026-11-16）：**`c2`/`c3` 所涉及的 UFS lease 故障已有因果证据**——受控对照与
0012 源码链支持 P-215（§10），不等于所有旧 silent 逐图结案。`c0` 是无判别力的
`invalid-measurement`；trial `wifi-20261114a`、独立 bt-s4b-c，以及未核验归档/实际调用路径
的旧图不在这一直接归因范围。MHI 方面，`c7` 直接观测到硬件 `exec_env=SBL`、`MHISTATUS=READY/SYSERR0`、
`MHICTRL` 请求 M0，而 host `ee=PBL`、`pm_state=POR`；抓取未见 EE 处理或完整镜像 BHIE 发起。
当前结论只到 **SBL/READY 后续转换未完成，原因待验**（§11）。`c8` 暂停，先审重复下载、
重入与 READY→M0 协议。

本页回答两个问题，答案都在这里：

1. 11.19 MB 的 PWF2 固件放进内核，会不会撞上装载边界？——**本文实测值未触发所列静态硬检查**：
   余量最小的一项（117 MB 镜像 vs `ReadFile` 的 128 MB）也有 1.14×（§3）。
   这不是所有镜像的实际装载路径或 pool 状态都已核验的声明。
2. 那么旧 wifi 镜像的 0 字节能否统一归因？——**不能**。`c2` silent / `c3` alive 的受控
   对照与源码链支持所涉及的 UFS lease 故障：`patches/wifi/0004` 让
   `PongUfsTransport::hostBringUp()` 索取 Apps SMMU lease，修前分配晚于这一调用（§10）。
   blob、版式、驻留、窗口等共存因素不足以单独解释这一对的差异；其它旧图的归档、
   链接和实际调用路径须逐图核验，不能用 `-Wl,-force_load` 或 PWF2 在场代替。
   `c0` 的身份不符仅使该格无判别力；`c1` 修 UUID 后仍 silent 只排除 UUID 是唯一充分解释。

## 0. 结论

| # | 结论 | 证据 | 推翻条件 |
|---|---|---|---|
| 1 | `c2`/`c3` 对照与源码链支持所涉及的 UFS lease 故障；不统包旧 silent | `c3` = `c2` + `patches/wifi/0012`（20,480 B），同版式同容器，`c3` alive / `c2` silent（§10.1–§10.2） | 同配方复测或源码/产物核验改变变量隔离、调用链或结果；不同旧图不能仅凭补丁名并入 |
| 2 | 所审 UFS lease 路径不受 `pong_wifi=0` 保护 | `c2`/`c3` 都是 `pong_wifi=0`；所列源码中开关挡住 worker，不挡 UFS 的 lease 调用（§10.2） | 同上；其它镜像需先核验归档与调用路径 |
| 3 | 所列实测值未触发所审静态硬边界；不等于逐图运行路径已证 | 段 12,992,512 vs 256 MB；span 129,642,496 vs 254 MB；镜像 117,305,344 vs 128 MB；段数 15/64；重叠 0；XNU 无上限常量（§3–§5） | 见 §0.1 |
| 4 | 带真 PWF2 的已飞镜像里有一张 alive | 全库 join：11 张带真容器 → 1 alive（`c3`）/ 10 silent；不带容器的 47 张 → 38 alive / 8 silent（§9.2） | 再飞同类得到不同分组 |
| 5 | 内核总大小不能单独区分已观测样本的生死 | `bt-s4b-20261115b` 106.5 MB alive 而同尺寸的 `c` silent；`adsp-20261115c/d/e` 128,991,232 B 三张全 alive（§2、§9.2）；bt-s4b-c 的独立原因不由 P-215 代答 | 若主张另一配方存在尺寸边界，需隔离其它变量并核验实际失败路径，不以异配方大小相关性定因 |
| 6 | `c7` 取样时处于 SBL/READY，后续转换未完成；原因未定 | `usblog-20261116-122546:632` 的硬件 `exec_env=1`、`MHISTATUS=0x101`、主机 `MHICTRL=0x200` 请求 M0；software `ee=0`、`pm_state=2`；未见 EE 处理或完整镜像 BHIE 发起日志（§11.4） | 后续同镜像/可复核探针记录到转换进展，或新证据改变对本次采样的解释；按 §11.8 分层记录，不以单字段结案 |

### 0.1 各判断的推翻条件

每条判断都要写明可复核条件与适用范围；一次异配方的 silent 不能自动推翻或证实另一配方的机制。

- **§0 第 3 行（边界）**：出现 `__TEXT` vmsize > 256 MB 仍过 `ParseKernel`；或实测 span
  > 253,388,800 仍过 :196；或内核镜像 > 134,217,728 字节仍被 `ReadFile` 接受；或
  vmsize≠0 的段数 ≥ 64 被接受；或在 xnu-work 找到任何以 `__TEXT` 大小为输入的上限
  （grep 之外还要读 `pmap_bootstrap` 与 KTRR 相关代码）。
- **§0 第 1、2 行（UFS lease）**：在已核验同配方、同归档与同调用路径的对照中，重复
  0012 干预得到不同结果，或发现变量未隔离/源码链不适用，均需重审。其它镜像只凭
  「带/不带 0012」与 silent/alive 不能直接归因，silent 也可能有独立原因。
- **§0 第 6 行（MHI）**：取得覆盖转换前后、并区分硬件寄存器、host 状态与事件处理的可复核记录；
  `exec_env` 单独变化不构成 MHI 或 Wi-Fi 成功判据。c8 目前暂停，先审下载与状态转换协议（§11.8）。

## 1. 固件是怎么进的内核，容器长什么样

- 构建期：`/opt/k60/trees/k60build/wifi/native-mhiboot/PongWifiFirmware.s`（215 B）用
  `.incbin` 把 `PongWifiFirmware.bin`（11,189,974 B）放进 `.section __TEXT,__const`
  （`t2`/`c2`/`c3`/`c4`–`c7` 那一行改成 `.section __DATA,__const`，落到
  `__DATA_CONST,__const`），符号 `_pong_wifi_firmware` / `_pong_wifi_firmware_end`。
- 链接期：`patches/wifi/0010` 用 `-Wl,-force_load` 把整个归档拉进内核（wifi 版双 hunk：
  `KERNEL_EXTRA_ARCHIVES` 与 `PLATFORM_ARCHIVES` 都加；main 版只有前者——mondrian 走
  `PLATFORM_ARCHIVES`，见 [WIFI-REBUILD-CHECKLIST.md](../../plans/WIFI-REBUILD-CHECKLIST.md) §3）。
- 运行期解析在 k60-wifi 树 `drivers/PongWifi/PongWifiPlatform.cpp:554-556`：
  `memcmp(...,"PWF2",4)` → `memcpy(&count,...+4,4)` → 逐条 `pong_wifi_firmware+8+i*40`
  按 name 匹配，`off>total||len>total-off` 拒收。

### 1.1 真容器与占位头：怎么区分

内核里 `PWF2` 这个四字节串会出现多次，**第一个命中不一定是容器**。判定手法
（脚本 `E:/k60-work/scratch/refmine/probe-pwf2kind.py`）：把每个命中处的 `count`
读出来，按 `offset+len` 取各条 entry 的最大跨度，**跨度 > 1 MB 才算真容器**。

- 反例：`z0` 上按第一个命中读 `count` 得到 **1,852,788,736**（垃圾值）——那个命中在
  `__TEXT,__cstring` 里，是日志字面量。
- 真容器（span 11,189,974）：`wifi-20261114a`（count 4，span 11,067,094）、
  `wifi-20261115a`/`h2`/`mhi3`/`mhi4`/`z0`/`c0`/`c1`（在 `__TEXT,__const`）、
  `t2`/`c2`/`c3`/`c4`–`c7`（在 `__DATA_CONST,__const`，文件里排在第二个命中处）。
- **tiny 家族 `t0c`/`t1c` 的 PWF2 是占位头**：`count=4`、四条 entry 各 **23 B**
  （`amss.bin` 4096/23、`amss20.bin` 8192/23、`m3.bin` 12288/23、`regdb.bin`
  16384/23）、span **16,407**，头后 4096 字节里只有 46 个非零字节；对应节
  `__TEXT,__const` 只有 593,943 B（真容器那一节是 11,767,510 B）。

### 1.2 PWF2 头与实际 payload 不一致（早期内核）

`mhi4` 内核里（文件偏移 589,824）头声明 `count=6`，但只有 entry[0] 非空
（`amss.bin` offset 4096、5,470,128 B）；entry[1..5] 全空。而 `__const` 里实际塞了
4 个真实固件（与 `/mnt/e/k60-work/firmware/qca6490-wifi/` 逐字节相同）：

| 文件 | bytes | const 内偏移 |
|---|---|---|
| amss.bin | 5,470,128 | 581,632 |
| amss20.bin | 5,296,128 | 6,053,888 |
| m3.bin | 266,684 | 11,472,896 |
| regdb.bin | 24,278 | 11,743,232 |

四文件合计 11,057,218 B；PWF2 区总长 11,189,974 B。头只描述第一个文件意味着运行期除了
`amss.bin`（以及 TCSR HW major==2 时改名的 `amss20.bin`，`PongWifiPlatform.cpp:553`）
之外，`m3.bin` / `regdb.bin` 用头里的空 entry **取不到**。

**这一条在 `c2`/`c3` 之后的新容器上不再成立**：`c3` 的容器六条 entry 全部有 payload
（`amss.bin` 4096/5,470,128、`amss20.bin` 5,476,352/5,296,128、`bdwlan.elf`
10,772,480/59,932、`bdwlang.elf` 10,833,920/59,936、`m3.bin` 10,895,360/266,684、
`regdb.bin` 11,165,696/24,278），span 11,189,974，容器 sha `3f68db4dc0927742…`
与 `c2` 逐字节相同。头失配因此是**早期打包脚本的缺陷**，已不在当前链路里。

## 2. 段级对照：wifi 版内核与能起内核差在哪

payload kernel = boot.img ramdisk 槽 `EFI/UniXNU/Payloads/kernel.macho`（`mtype` 提取）。
18 个 `LC_SEGMENT_64`，其中 vmsize≠0 的 15 个参与装载。

| 段 | baseline（thermal-20261114f，alive） | mhi4（0 字节） | 差 |
|---|---|---|---|
| `__TEXT` vmaddr | 0xfffffff007004000 | 同 | — |
| `__TEXT` vmsize | 1,720,320 | **12,992,512** | **+11,272,192（固件）** |
| `__DATA_CONST` | 917,504 @0x…71a8000 | 933,888 @0x…7c68000 | +16,384 |
| `__TEXT_EXEC` | 8,355,840 @0x…7288000 | 8,765,440 @0x…7d4c000 | +409,600 |
| `__PRELINK_TEXT` | 7,421,952 @0x…4420000 | 同 | — |
| `__PLK_TEXT_EXEC` | 22,757,376 @0x…4b34000 | 同 | — |
| `__DATA` | 1,638,400 | 1,867,776 | +229,376 |
| span（Base→End） | 66,285,568 | 78,327,808 | +12,042,240 |

三条对照否证「仅凭内核总大小就能区分这些样本生死」的模型，不排除别的配方有自己的边界：

1. **105 MB alive 家族的 `__TEXT` 与 54 MB 基线相同（1,720,320）**——它们的体积全部
   来自 `__DATA` 52,920,320。所以「内核大」与「`__TEXT` 大」是两件互不蕴含的事。
2. **bt 同尺寸一活一死**：`bt-s4b-20261115b` 与 `bt-s4b-20261115c` 同为 106,541,056 B、
   同 blob、只差一个补丁（series 228 `b31855c932b4…` → 229 `67baff88e1bb…`），
   b 进桌面（`usblog-20261115-140927`，213,434 B）、c 0 字节
   （`usblog-20261115-163144`）。任何「内核大于 N MB 就死」的阈值模型被否证。
3. **129 MB 也 alive**：`adsp-20261115c/d/e` 三张 kernel **128,991,232 B**
   （`__DATA` 76,414,976、span 141,111,296，都比 117 MB 家族大），同 4.5 GiB 窗口、
   无 PWF2，全部进桌面（`usblog-20261115-213413` 214,232 B、`-220912` 221,484 B、
   `-223916` 220,234 B）。阈值模型第二次被否证，这次把 117 MB 也包在里面。

**驻留位置不能单独解释这一对的差异**：`t2`/`c2`/`c3`/`c4`–`c7` 的容器位于
`__DATA_CONST,__const`，而非早期的 `__TEXT,__const`（`__TEXT` 回到 1,802,240、
`__DATA_CONST` 12,124,160）；`c2` silent、`c3` alive——同一驻留位置两种结果。
这是所列样本的对照，不是所有驻留方案都与启动无关的全局定理。

对齐不变：`__TEXT` vmaddr 两边都是 0xfffffff007004000（DarwinBoot.c:194 校验
`Base & EFI_PAGE_MASK`）；xnu-work `osfmk/arm64/arm_vm_init.c:2306` 的
`assert(segDATACONSTB == segTEXTB + segSizeTEXT)` 在 mhi4 上仍成立
（0x7004000 + 12,992,512 = 0x7c68000 = `__DATA_CONST` vmaddr）。

## 3. DarwinBoot 路径上的四个硬检查，逐个对数

装载顺序（`drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c`）：
`ReadFile` 整块进 DXE pool（:558，上限 `SIZE_128MB`）→ `ParseKernel`（:561）
→ 读 `.adt` 得 WindowSize（:568/:575/:580）→ `AllocateWindow`（:607）
→ 段拷贝（:627-630）→ `FreePool(Image)`（:656）。

| # | 检查 | 位置 | 实测值 | 上限 | 余量 |
|---|---|---|---|---|---|
| 1 | 单段大小 vs `WINDOW_SIZE` | :168 | `__TEXT` 12,992,512 | 268,435,456（256 MB） | 20.7× |
| 2 | 内核 VA 跨度 vs `WINDOW_SIZE - 2 MB` | :196 | 129,642,496（z0/mhi5）；`c7` 129,757,184 | 253,388,800 | 1.95× |
| 3 | 内核镜像文件 vs `ReadFile` 的 `SIZE_128MB` | :558 | 117,305,344（z0/mhi5）；`c7` 117,342,208 | 134,217,728 | **1.14×**（全文最窄） |
| 4 | 段数 / 段间重叠 | :160 / :190-191 | 15 / 0 | 64 / 无 | 4.3× / — |

`AllocateWindow`（:420-478）本身只看内存地图里最大的 `EfiConventionalMemory` run 能不能
容纳 WindowSize——它**不读内核段**。:619 另检查
`Used > WindowSize - BLOCK_SIZE`（Used = kernel span + args/tree/ramdisk/trustcache 的
16 KB 对齐和），所列值对 4.5 GiB 窗口远不可及；更早的 pool 分配仍可能影响内存地图。
窗口申请的一种失败模式是「NO WINDOW」（内存碎片），
其定量模型与实测的分叉见 [BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §3.3，本文不外推。

## 4. VA 布局：`__TEXT` 长大不碰任何人

新 kcgen 的 vmaddr 顺序见 xnu-work `osfmk/arm64/arm_vm_init.c:165-181` 的注释
（`__PRELINK_TEXT → __PLK_DATA_CONST → __PLK_TEXT_EXEC → __TEXT → …`）。实测两内核：

- `__PRELINK_TEXT` 恒 0xfffffff004420000、`__PLK_TEXT_EXEC` 恒 0xfffffff004b34000——
  两者都在 `__TEXT` 之下的低地址。
- `__TEXT` 从 0x…7004000 起向高地址长：baseline 末端 0x…71a8000，wifi 末端 0x…7c68000。
  向高地址方向的邻居是 `__DATA_CONST`（紧邻断言 §2），不是 prelink 段。
- 算术：0xfffffff007004000 + 12,992,512 = 0xfffffff007c68000（= `__DATA_CONST` vmaddr）；
  与低地址 prelink 段永无交叠，:190-191 的两两重叠检查通过。

## 5. XNU 侧没有 `__TEXT` 大小上限常量

`grep -rn 'KERNEL_TEXT_MAX\|kPrelinkTextMax\|MAX_KERNEL_TEXT'` 在 xnu-work 的
osfmk/pexpert/libsa/bsd 全树 **0 命中**。`arm_vm_init.c` 对 `__TEXT` 只做三件事：
取段基（:2087 `getsegdatafromheader("__TEXT", &segSizeTEXT)`）、设只读页表
（:1415 `arm_vm_page_granular_RNX`，带 `ARM64_GRANULE_ALLOW_BLOCK | ARM64_GRANULE_ALLOW_HINT`）、
断言 `__DATA_CONST` 紧邻（:2306）。没有大小断言；KTRR 锁的是 `__PRELINK_TEXT` 到
`__LAST`（注释 :165-181），与固件落在 `__TEXT` 还是别处无关。

## 6. 六格判别矩阵：历史计划与现行证据边界

这张表是 2026-11-15 设计的对照计划（后来补 G 格）。**它现在只是记录**：未飞的格
不产生结果，`c0` 身份不符使格无判别力；单变量证据来自 `c2`/`c3`，不替其它格逐图定因。

| 格 | 内核 | `__TEXT` | blob | `pong_wifi` | 结局 | 打掉了什么 |
|---|---|---|---|---|---|---|
| A | 54.2 MB stock（thermal / bt / …） | 1.64 MiB | 无 | 0 | alive | 基线 |
| B | 54.8 MB tiny（`t0c`/`t1c`，kernel 54,804,480，`__TEXT,__const` 593,943） | 1.82 MiB | 4×23 B 占位（PWF2 count=4、span 16,407） | 0 / 1 | **从未飞** | 未飞，无对照结果；`c3` 已证明真容器可 alive，但不能替 tiny 预测结果 |
| C | 66 MB（`c0` / `c1`，66,002,944） | 12.39 MiB | 11.19 MB 真容器 | 0 | `c0` 测量无效（种子 UUID）；`c1` silent | 仅排除 UUID 错配是这组 silent 的唯一充分解释；不否定 P-152 机制（§10.3） |
| D | 117 MB（`mhi5`） | 12.39 MiB | 11.19 MB | 1 | 从未飞 | 未飞，无对照结果；不能凭 `c3` 替此图归因 |
| E | 117 MB（`z0`，与 `mhi5` 只差 `pong_wifi`） | 12.39 MiB | 11.19 MB | 0 | silent（`usblog-20261115-135859`） | 「驱动活体」——但 `pong_wifi=0` 时 worker 本来就没跑，这条读法只能证明「worker 没跑也死」 |
| F | 117 MB（`t2`；`c2` 复现） | 1.80 MiB | 11.19 MB（`__DATA_CONST`） | 0 | 两飞都 silent | 「`__TEXT` 驻留」 |
| G | 117 MB（`c3` = `c2` + 0012 惰性锁） | 1.80 MiB | 11.19 MB（`__DATA_CONST`，与 `c2` 逐字节相同） | 0 | **alive**（`usblog-20261116-015128`） | 与 `c2` 的单变量干预支持所涉及的 UFS lease 故障，不统包 A–F |

旧版曾写「A–F 把六条轴全部打掉」，这一推断过强：B/D 未飞，C 中 `c0` 无效，
其它格也并非都隔离了同一变量。G 与 F 中 `c2` 的对照加上源码链，才支持所涉及的
UFS lease 故障（§10.2）；它不把所有旧图的具体故障点变成已知。

## 7. pool / 窗口通道：排除仅限所列配方与已观测对照

2026-11-15 那一版把这条列为主要嫌疑之一（`ReadFile` 在 :558 把整个内核吃进 DXE pool，
之后 :607 才申请 4.5 GiB 连续窗口；blob 使 pool 占用多 11.27 MB，可能改变
`AllocateWindow` 看到的最大 run）。现有证据收窄了这一假设，而非全局关闭所有旧图的 pool 风险：

- **受控对照**：`c3` 与 `c2` 同 117 MB 级版式、同窗口（0x120000000 = 4.5 GiB）、
  同真 PWF2 容器，**一个活一个死**。两图文件大小仍差 20,480 B、span 也有差异（§9.1）；
  不能声称实测 pool 地图逐字节相同。对这一配方，「真容器/117 MB 占用必然使窗口失败」
  不成立，配合 0012 干预与源码链支持 UFS lease 解释。
- **间接反例**：`adsp` 三张 129 MB（`__DATA` 76,414,976、span 141,111,296，
  都比 117 MB 家族大）在同一 4.5 GiB 窗口下全部进桌面，反对单纯按文件大小划死线。
  它们是异配方，不证明旧 wifi 图的 pool 碎片、分配顺序或最大 run 相同。

**未知**：0 字节的旧 console 没有 `NO WINDOW` 或装载阶段留痕，无法由此读出各图
`AllocateWindow` 实际走到哪一步。`c3` alive 说明它自身通过了启动所需步骤，不是
其它旧图窗口申请成功、也不是所有旧 silent 都与 pool 无关的直接证据。

## 8. 证据清单

| 事实 | 证据 |
|---|---|
| 段表逐段扫描 | `E:/k60-work/scratch/refmine/probe-family.py`、`probe-segs.py`、`probe-silent6.py`、`probe-1115alive2.py`、`probe-c456b.py`（`mtype` 解 ramdisk 槽 → `LC_SEGMENT_64`） |
| 窗口值逐镜像 | `probe-window3.py`、`probe-win2.py`：ADT 属性 `darwinboot-memory-size` 解码 |
| PWF2 容器真伪 | `probe-pwf2kind.py`（span > 1 MB 判据）、`probe-c3c.py`、`probe-c3d.py`、`probe-pwf2off.py`（按节表归属定位） |
| 全库 blob × alive join | `scan-blob3.py`：319 个产物目录，按 `image_sha256` 对 `E:/k60-work/evidence/*/boot.json`（BOM 用 `utf-8-sig` 读） |
| 判定器 | main 的 `scripts/judge-wifi-boot.py`、`scripts/judge-z0.sh`、`scripts/check-arg.py` 与两份自测（合并 `4f56970`，登记 `3e6f110`，tag `snap-r198`）；本文引用一律写 main 上的 `scripts/` 路径 |
| DarwinBoot 检查 | `drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c:160,168,190-191,194-196,558,607,619` |
| XNU 侧无上限 | xnu-work `grep 'KERNEL_TEXT_MAX\|kPrelinkTextMax\|MAX_KERNEL_TEXT'` = 0 命中 |
| VA 布局 | xnu-work `osfmk/arm64/arm_vm_init.c:165-181`（顺序）、:2087、:1415、:2306 |
| 解析器 | k60-wifi 树 `drivers/PongWifi/PongWifiPlatform.cpp:553-556` |
| 所涉及 UFS lease 的源码链（不等于所有旧图运行轨迹） | `drivers/NativeUfs/PongUfsTransport.cpp:29,143,174-181,602`；`drivers/PongWifi/PongWifiPlatform.cpp:152,716-718,729,787-788`；`drivers/ArmDTPlatform/ArmDTPlatform.cpp:227-228` |
| `c0` 测量无效 | `E:/k60-work/artifacts/wifi-20261116c0/boot.img` 内 `6DCCF70A-…` ×1、`1BCD69FF-…` ×0；构建树 `k60-wifi` @ `fff0fb19` 的 `configs/mondrian_wifi_defconfig:46` 指名种子 UUID；P-152（`docs/engineering/PITFALLS.md:3811-3819`）；P-209 门禁 `scripts/check-defconfig-uuid.py`（main `011669a`，tag `snap-r201`） |
| 构建配置扫描（53 张 wifi/bt boot.img） | `E:/k60-work/scratch/refmine/uuid-scan.py`：56 个产物里 3 个没有 boot.img；扫到的 53 张中**只有 `c0` 带种子 UUID**，其余 52 张都是设备 UUID |
| P-215 原文 | main `docs/engineering/PITFALLS.md:5337` 起；Check：`scripts/tests/test-pong-smmu-lease.py`、registry id `P-215` |
| MHI 固件加载链 | pinned linux（`/home/emilelu/wifi-inputs/linux`）`drivers/bus/mhi/host/boot.c:372-405,430-434,490,555-575,633-653`；`init.c:391-393,480-535`；`main.c:893-906`；`pm.c:196-204,823-836,1277-1298`；`internal.h:32-37,78-79,128,142-162`；`common.h:111-115`；`include/linux/mhi.h` 的 `enum mhi_ee_type` / `enum mhi_state` |
| 兼容层无条件重放 IRQ | `Ath12kWifi/shim/src/lx_rt.c:32,315,347,355,597`；调用点 `drivers/PongWifi/ath11k/PongAth11k.c:83`；驱动侧 GIC 入口及状态日志 `drivers/PongWifi/PongWifiPlatform.cpp:566,644,646,649,706` |
| `c7` 判读 | `E:/k60-work/evidence/usblog-20261116-122546/console.log`（227,186 B / 3,367 行 / SpringBoard 128）；关键行 :608 与 :632；`boot.json` 的 `imageSha256 4D187A71…F45F` |
| MHI 拓扑 | k60-wifi `docs/research/wifi/MSI-TOPOLOGY.md`：驱动走 DesignWare legacy（PARF MSI0 = 1u<<23 → GIC SPI 140 = INTID 172，`PongWifiPlatform.cpp:43`、:683；`ArmCpu.cpp:403` 对 unowned SPI panic）；设备树 `msi-map` 指向 ITS `msi-controller@17140000`（event base 0x5980/0x5981）；真机 Android 走 ITS（`/proc/interrupts` 的 ITS-MSI 524289..524306）；第三个节点 `/soc/qcom,pcie0_msi@0x17110040`（32 个 SPI 768..799）status=disabled |

口径备注：本文所有「alive / 0 字节 / 未飞」都来自 evidence 采集目录与 artifact
`boot.json` 按 image sha256 的 join，与 [BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §3 同源。
**采集目录可能有子目录**（`audio-probe-j/run1`、`run2`），按 evidence 顶层 join 会漏。

ADT 口径（2026-11-15 起）：main `3ea8d71` 把 identity seed 接进板级契约——`board.toml`
`[payload."adt"]` 增 `unique_chip_id = "required"`，`build-strict.sh` 把
`UNIXNU_UNIQUE_CHIP_ID` 转发给 build payload，新构建的 ADT 会带 `/chosen/unique-chip-id`。
`t2` 及以后的窗口必须逐镜像重解，不能沿用旧表，也不能拿旧 ADT sha 当新镜像的属性清单。

## 9. 实测对照表

### 9.1 全家族段表与上机记录

`__TEXT` / `__DATA` / `__DATA_CONST` 是段 vmsize，span 是 `Kernel.End - Kernel.Base`；
`PWF2` 与 `Pong MHI` 是内核镜像里出现的字符串次数，`pong_wifi` 取自同目录
`build-manifest.json` 的 `kernel_args_requested`。

| 镜像 | kernel B | `__TEXT` | `__DATA` | span | PWF2 | Pong MHI | `pong_wifi` | 上机 |
|---|---|---|---|---|---|---|---|---|
| thermal-20261114f | 54,173,696 | 1,720,320 | 1,638,400 | 66,285,568 | 0 | 0 | 0 | **alive**（232,670 B） |
| springboard-20261114c | 105,480,192 | 1,720,320 | 52,920,320 | 117,600,256 | 0 | 0 | 0 | **alive**（220,944 B） |
| gpu-20261114n | 105,476,096 | 1,720,320 | 52,920,320 | 117,583,872 | 0 | 0 | 0 | **alive**（262,275 B） |
| brightness-4 | 105,500,672 | 1,720,320 | 52,920,320 | 117,616,640 | 0 | 0 | 0 | **alive**（185,701 B，4.5 GiB 窗口） |
| bt-s4b-20261115b | 106,541,056 | 1,720,320 | 52,920,320 | — | 0 | 0 | —（`k60bt=1`） | **alive**（213,434 B，`usblog-20261115-140927`） |
| bt-s4b-20261115c | 106,541,056 | 1,720,320 | 52,920,320 | 118,648,832 | 0 | 0 | —（`k60bt=1`） | silent（0 B，`usblog-20261115-163144`） |
| bt-s4c-20261115c | 105,508,864 | 1,720,320 | 52,920,320 | — | 0 | 0 | —（`k60bt=1`） | **alive**（245,222 B，`usblog-20261115-162553`） |
| adsp-20261115c | 128,991,232 | 1,720,320 | 76,414,976 | 141,111,296 | 0 | 0 | — | **alive**（214,232 B，`usblog-20261115-213413`） |
| adsp-20261115d | 128,991,232 | 1,720,320 | 76,414,976 | 141,111,296 | 0 | 0 | — | **alive**（221,484 B，`usblog-20261115-220912`） |
| adsp-20261115e | 128,991,232 | 1,720,320 | 76,414,976 | 141,111,296 | 0 | 0 | — | **alive**（220,234 B，`usblog-20261115-223916`） |
| wifi-20261114a | 65,863,680 | 12,877,824 | 1,867,776 | 78,213,120 | 2 | 0 | 1 | silent（`usblog-20261114-wifi-b`；trial 无 series） |
| wifi-20261116mhi3 | 65,978,368 | 12,992,512 | 1,867,776 | 78,327,808 | 2 | 11 | 1 | silent（`usblog-20261115-002804`） |
| wifi-20261116mhi4 | 65,978,368 | 12,992,512 | 1,867,776 | 78,327,808 | 2 | 11 | 1 | silent（`usblog-20261115-002243`） |
| wifi-20261116a2 | 65,978,368 | 12,992,512 | 1,867,776 | 78,327,808 | 2 | **0** | 0 | 从未飞（trial 级，P-201） |
| wifi-20261116mhi5 | 117,305,344 | 12,992,512 | 53,149,696 | 129,642,496 | 2 | 11 | 1 | 从未飞 |
| wifi-20261115z0 | 117,305,344 | 12,992,512 | 53,149,696 | 129,642,496 | 2 | 11 | **0** | silent（`usblog-20261115-135859`） |
| wifi-20261116c0 | 66,002,944 | 12,992,512 | 1,867,776 | 78,344,192 | 2 | 11 | 0 | 测量无效（`usblog-20261115-213221`，种子 UUID，§10.3） |
| wifi-20261116c1 | 66,002,944 | 12,992,512 | 1,867,776 | 78,344,192 | 2 | 11 | 0 | silent（`usblog-20261115-231707`） |
| wifi-20261116t2 | 117,305,344 | **1,802,240** | 53,149,696 | 129,642,496 | 2 | 11 | 0 | silent（`usblog-20261115-161102`） |
| wifi-20261116c2 | 117,305,344 | **1,802,240** | 53,149,696 | 129,642,496 | 2 | 11 | 0 | silent（`usblog-20261116-000136`） |
| wifi-20261116c3 | 117,325,824 | **1,802,240** | 53,149,696 | 129,675,264 | 2 | 11 | 0 | **alive**（221,429 B，`usblog-20261116-015128`） |
| wifi-20261116c4 | 117,325,824 | **1,802,240** | 53,149,696 | 129,675,264 | 2 | 11 | **1** | **alive**（221,888 B，`usblog-20261116-072728`） |
| wifi-20261116c5 | 117,325,824 | **1,802,240** | 53,149,696 | 129,675,264 | 2 | 11 | 1 + `rsc=1` | **alive**（221,969 B，`usblog-20261116-075300`） |
| wifi-20261116c6 | 117,325,824 | **1,802,240** | 53,149,696 | 129,675,264 | 2 | 11 | 1 + `rsc=2` | **alive**（221,551 B，`usblog-20261116-081646`；MHI `-110`，§11） |
| wifi-20261116c7 | 117,342,208 | **1,802,240** | 53,215,232 | 129,757,184 | 2 | **18** | 1 + `rsc=2` | **alive**（227,186 B，`usblog-20261116-122546`；MHI `-110`，§11.4） |

从这张表直接读出来的事实（都可推翻）：

1. `z0` 不是 66 MB 的 C 格：它 117,305,344 B，是 `mhi5` 的孪生（只差 `pong_wifi`）。
   66 MB 那一格是 `c0`/`c1`。
2. `a2` 是名义上的 `pong_wifi` 对照（`Pong MHI` 串数 0 vs 11），但它是
   P-201 的 trial 级——manifest 没有 `series` 键，身份不可复核，不能声称与 `mhi4` 只有这一变量不同。
3. 105 MB alive 家族的 `__TEXT` 与 54 MB 基线完全相同；`__TEXT` 12,992,512 是 wifi
   家族独有的。
4. `t2`/`c2` 的 `__TEXT` 只有 1,802,240 仍 silent，而 `c3`/`c4`–`c6` 同类版式 alive ⇒
   驻留位置不能单独解释这些样本的差异，不推出其它旧图与驻留无关。
5. bt 同尺寸一活一死；adsp 129 MB 三张全 alive ⇒ 阈值模型两次被否证。
6. `c3` 与 `c2` 的差为 20,480 B（`patches/wifi/0012`）；对照加源码链支持这一对所涉及的 UFS lease 故障。
7. `c4`/`c5`/`c6` 与 `c3` 段表逐项相同，只差 `kernel_args`（`pong_wifi=1`、
   `k60_wifi_rsc`）与补丁——三张都 alive，说明这些已观测配方允许 worker/RSC 路径继续，不是所有旧图的安全性证明。

### 9.2 全库 join：带真 PWF2 与不带，各自的生死分布

| 组 | 张数 | 真 PWF2 容器 | alive（console > 1 KB） | silent（console = 0 B） |
|---|---|---|---|---|
| 已飞，内核带真 PWF2 | **11** | 11 | **1**（`c3`） | **10** |
| 已飞，内核不带 PWF2 | 47 | 0 | 38 | 8 |

带真 PWF2 且已飞的十一张：`wifi-20261114a`、`wifi-20261115a`、`wifi-20261115h2`、
`wifi-20261116mhi3`、`wifi-20261116mhi4`、`wifi-20261115z0`、`wifi-20261116t2`、
`wifi-20261116c0`、`wifi-20261116c1`、`wifi-20261116c2`、`wifi-20261116c3`。
（`c4`–`c7` 四张也是带真容器且 alive，但这张 join 表是 `c3` 那一轮跑的，
未把 `c4`–`c7` 计入；按 §9.1 的逐镜像 PWF2 实测补上后应为 **15 张 / 5 alive**
（`c3`、`c4`、`c5`、`c6`、`c7`）。）

不带 PWF2 的八张 silent 全在 usb 与 bt 线（`bt-s1-20261114b`、`bt-s4b-20261115c`、
`bt-bisect-h123`、`usb-20261114c`、`usb-20261114f`、`usb-20261114h2`、
`usb-20261115b`、`usb-20261115c`），属于独立故障集合；尤其不能把 bt-s4b-c 改判为 P-215。

**这张表只能当观测轴读**：它证明「带真容器与生死高度同步」，不能证明「容器导致生死」。
`c3` 是那张推翻条件（一张带真 PWF2 的 alive 镜像）。P-215 的因果证据来自另一个层次：
`c2`/`c3` 受控对照与 `patches/wifi/0004`、0012 的源码链，而非 join 本身。
旧表仍含 `c0` 的零字节观测（其测量身份无效），也含 trial `wifi-20261114a`；
11/1 与 47/38 是历史统计口径，不是十一张镜像都已隔离变量或逐图归因。写法教训见 §10.5。

## 10. UFS lease 故障的因果证据与逐图边界（P-215）

### 10.1 单变量证据：`c3` 与 `c2`

| | `c2` | `c3` |
|---|---|---|
| 产物 | `wifi-20261116c2`，built 2026-11-15T23:40:04 | `wifi-20261116c3`，built 2026-11-16T01:34:21 |
| `repo.head` | `9fd2018a80b3` | `3207bd3c019c` |
| series | 224 | 226 `d83fb1890e93` |
| kernel B | 117,305,344 | 117,325,824（**+20,480**） |
| 段表 | `__TEXT` 1,802,240 / `__DATA_CONST` 12,124,160 / `__DATA` 53,149,696 | **逐项相同** |
| PWF2 容器 | 6 条、span 11,189,974、sha `3f68db4dc0927742…` | **逐字节相同** |
| 窗口 / `pong_wifi` | 4.5 GiB / 0 | 同 |
| 采集 | `usblog-20261116-000136`，0 字节 | `usblog-20261116-015128`，221,429 B、SpringBoard 133 |
| 判定 | silent | **alive** |

差的 20,480 B 全部来自 `patches/wifi/0012-drivers-PongWifi-lease-lock-lazy-init.patch`。
这次**受控单变量干预**与下节源码链相互支持，构成本账本对所涉及 UFS lease 故障的因果证据。
它不是每一张旧 silent 都重跑过同一实验的替代证据。

口径脚注（`c3` 的计数两处差异）：本页写 console.log **221,429 B / 3,204 行 / SpringBoard 133**，
Lead 那侧记 3,202 行 / 132 次。字节数两边一致；行数与计数差来自统计方式——
本页按 `capture.json` 的 `bytes` 与整文件计数（含 supervisor 头尾行），
Lead 用的是 `grep -c` 粗计。**以 `capture.json` 为准**，差异只在这两个派生计数上。

### 10.2 所审源码链、间接时序与运行时缺口

- `drivers/NativeUfs/PongUfsTransport.cpp:29`
  `extern "C" bool pong_smmu_lease_lock(void) __attribute__((weak_import));`
- 同文件 `:143` `hostBringUp()`；`:174-181` 是 `patches/wifi/0004` 插进去的 lease 段：
  `if (pong_smmu_lease_lock && pong_smmu_lease_unlock) { lease.held = pong_smmu_lease_lock();
  if (!lease.held) return transportFailure("Apps SMMU lease unavailable"); }`；
  `:602` `if (!hostBringUp()) return false;`
- `drivers/PongWifi/PongWifiPlatform.cpp:152` `IOLock *powerLock,*smmuLeaseLock;`；
  `:729` 在 `pong_rpmh_init()` 里 `IOLockAlloc`；`:716-718` 先 `pong_rpmh_init()` 再查开关；
  唯一调用点 `pong_wifi_start_optional()` 由 `ArmDTPlatform.cpp:227-228` 在
  `registerService()` 之后调。
- 修前实现（`patches/wifi/0001`）：`if(!smmuLeaseLock) return false; IOLockLock(...); return true;`

**间接时序证据**：所引能起日志中 `PONG_UFS` 在 115 行、
`ArmDTPlatform: registered platform` 在 147 行，支持 UFS bring-up 早于后者。结合修前
源码，若这一调用时 `smmuLeaseLock == NULL`，则 lock() 返回 false ⇒
`transportFailure("Apps SMMU lease unavailable")` ⇒ UFS transport 放弃；根设备不可用
可导致启动无法继续。这条机制与 `c2` 0 字节、0012 后 `c3` alive 的对照相符。
**不是同次故障留痕**：`c2` 的零字节没有提供当次 lease 返回值、panic 行或精确停点，
不能把上述源码推导补写成捕获到的完整运行轨迹，更不能外推所有旧图。

修法（`patches/wifi/0012`，单变量）：`if(!smmuLeaseLock) smmuLeaseLock=IOLockAlloc();
if(!smmuLeaseLock) return false; IOLockLock(smmuLeaseLock); return true;` —— 分配搬进
lock() 自己，`pong_rpmh_init()` 里那次分配保留。补丁注释原文：
"the first client to want it is not necessarily the WiFi worker: NativeUfs takes
the same lease in hostBringUp()"。

**可证的范围**：所审源码里 `pong_wifi=0` 只挡住 worker 之后的注册，不挡 UFS
在 `hostBringUp()` 索取同一把锁；这解释了为何 `c2` 的开关为 0 仍不能防护该机制。
`-Wl,-force_load` 能使相关实现被链接，但「归档在场」不等于「每张镜像都以同一时序
走到同一失败分支」；未核 series、archive 及实际调用路径的旧图仍未知。

| 证据层 | 现有材料能支持到哪里 | 不能据此声称什么 |
|---|---|---|
| 可证/受控 | `c2` silent、`c3` alive；0012 干预与上述源码链支持所涉及的 UFS lease 故障 | 所有旧 silent 同因、或带 0012 的任意配方都必 alive |
| 间接 | 已列旧图的结构/参数/字符串观察可与该机制相容；能起日志支持时序 | 没有逐图归档与调用路径核验时，不能由 PWF2/字符串/补丁名直接转成定因 |
| 未知或不可判 | `c0` 身份不符，trial `wifi-20261114a` 无 series，独立 bt-s4b-c，以及其它未核输入/路径 | 不补 c0 同次 panic，不把 bt-s4b-c 并入 P-215，不编造缺失 series/archive/调用记录 |

### 10.3 `c0`：`invalid-measurement`（保留这一条，因为它是「先 diff 构建配置」的样本）

`c0` 由 `mondrian_wifi_defconfig` 构建，该文件在 `k60-wifi` @ `fff0fb19` 的 `:46`
指名了种子 Data UUID `6DCCF70A-…`。这证明构建身份不符，因此它不能作为隔离版式/体积
变量的有效格。**本次采集没有同次 panic 行，不能断言它实际到达根挂载、等卷超时或在
某个行号崩溃**，更不能用零字节反推先发生的是 UUID 故障还是其它早期故障。

P-152 的既有机制记录保留作背景：`PONG APFS: wait for Data UUID 6DCCF70A-…, timeout=5s`
→ `K60DATA UFS Data window not published` → `dataerr=2` self-panic `@kern_exec.c:8463`。
这是机制参照，**不是 `c0` 本次日志中的已观测序列**。

- 实测字节：`c0` 的 boot.img 内 `6DCCF70A-…` ×1、`1BCD69FF-…` ×0；全库 53 张 wifi/bt
  boot.img 里**只有这一张**带种子 UUID。
- 重测 `c1`（只改该 UUID 一行）已飞：boot.img 内 `6DCCF70A-…` ×0 / `1BCD69FF-…` ×1，
  段表与 `c0` 逐项相同，仍然 0 字节 ⇒ **只排除「UUID 错配是这组 silent 的唯一充分解释」**。
  这不否定 P-152 的 UUID 故障机制，也不证明 `c0` 的实际停点或 `c1` 与其同因；
  `c0` 维持 `invalid-measurement`，`c1` 是修正 UUID 后的有效 silent，但无日志崩点仍未知。
- 门禁 P-209（`scripts/check-defconfig-uuid.py`，main `011669a`，tag `snap-r201`）：
  defconfig 指名非本机 Data UUID 即硬失败，种子 UUID 必须显式标 `# SEED-UUID: intentional`。

### 10.4 `c4`/`c5`/`c6`：修后配方的 alive 证据

三张都是 `c3` + `pong_wifi=1`（`c5` 加 `k60_wifi_rsc=1`，`c6` 加 `k60_wifi_rsc=2`），
段表与 `c3` 逐项相同，三张全部 alive（§9.1）。所以：

- 在这些带 0012 的已观测配方中，`pong_wifi=1` 时系统能进桌面。
- 同样仅对这些样本，`k60_wifi_rsc=1`（只读探针）与 `=2`（投票）未阻止启动；
  不是其它配方的安全性定理，也不是对修前 silent 的第二次单变量验证。

### 10.5 方法论：观测轴 ≠ 因果轴

2026-11-15 那一版写过一句「带 PWF2 的已飞镜像没有一张 alive……所以『blob 在场』是
目前唯一没有被任何 alive 镜像打过的轴」。join 方法没错（11 张里 10 张 0 字节是实测），
**错在结论强度**：一张表能证明「这条轴与生死同步」，不能证明「这条轴导致生死」，
除非做过单变量干预。正确写法就是当时写在推翻条件里的那句——「推翻条件 = 一张带真
PWF2 的 alive 镜像」——**推翻条件写对了，只是没等到它出现就把它写成了因果**。

三条可复用的写法：

1. 「这是目前唯一还分得开生死的观测轴」只是当时样本的历史措辞，不能作为现行规则；
   观测相关性须限定样本、输入完整性和时点，不把它升级为死因。
2. 每条候选轴写清适用范围与推翻条件；还需独立干预和可核验路径支撑因果结论。
3. 单变量干预之后，旧表要**保留原样并标注结局**，不要删——被推翻的过程本身是记录
   （§6 矩阵按这个方式处理；完整过程在 `feat/wifi-ledger-fold` 分支）。

## 11. MHI 阶段：c7 的直接读数与尚未完成的转换

> 2026-11-16 15:12 更正：c7 定位到 SBL/READY 后的转换未完成；上一版的「死锁已证实」、
> 「AMSS 一个字节未送」和「rp 证明事件环/DMA 正常」均撤回。主动发起 BHIE 是待验证实验，
> c8 当前暂停，先审重复下载、重入与 READY→M0 协议。

### 11.1 c4/c5/c6 的阶段记录

三张都带 `pong_wifi=1`，段表逐项相同（§9.1），且都进桌面。MHI 阶段的观测以
`usblog-20261116-081646`（c6）为例：

| 阶段 | c6 console 行 | 直接观测 |
|---|---|---|
| 1–4 | :482-490 | 电源轨、REFCLK 与初始化阶段日志 |
| 5 | :490-500 | 五条轨报告 physical ready、observerErrors=0，rail 请求被确认 |
| 6 | :502 | PHY_CTRL=900->900 mux=2 CLKREF=1 |
| 7 | :503 | 82-entry vendor QMP PHY table |
| 8 | :513-518 | QCA6490 PCI subsystem=10817cb、link/BAR、SID 1c01 context 与 64 MiB wired DMA 预算 |
| 9 | :586-587 | 64 MiB 映射日志、SID1c01 DMA 与 retained MSI landing page |
| 10 | :588-592 | PARF MSI0/SPI140 配置、receiver armed、32 MSI vectors |
| MHI 注册 | :596-600 | regs、channels=128、start 参数 ee=0 state=0 |
| 复位与 READY | :608-620 | serial、amss20 文件读取、load type=2、轮询后报告 READY |
| 等待结束 | :622-635 | 等待后返回 -110（ETIMEDOUT）；返回码不是根因判定 |

`firmware amss20.bin bytes=5296128` 是主机侧读取文件，不是完整镜像的设备接收确认。
READY 是 `pm.c:196-204` 的 `mhi_poll_reg_field` 轮询结果，不证明 MSI 到达或共享 DMA 上下文可见。
阶段日志证明初始化代码执行到了这些位置，不能概括成「PCIe/DMA/中断全通」。

### 11.2 路由拓扑是背景，不是因果结论

k60-wifi `docs/research/wifi/MSI-TOPOLOGY.md` 记录当前配置：

- 驱动配置 DesignWare legacy：PARF MSI0 = `1u<<23` → GIC SPI 140 / INTID 172
  （`PongWifiPlatform.cpp:43,683`）。
- 设备树 `msi-map` 指向 ITS `msi-controller@17140000`，event base 0x5980/0x5981；
  Android `/proc/interrupts` 有 ITS-MSI 524289..524306。
- `/soc/qcom,pcie0_msi@0x17110040`（SPI 768..799）节点为 disabled。

这些拓扑事实不足以判定 c7 的原因。复位清零与 READY 由寄存器轮询获得，不是中断握手；
也不能仅凭拓扑不同推断 legacy 路由必错。IRQ 证据边界见 §11.6。

### 11.3 飞前四支判据（仅保留为历史排查假设）

> 原先四支不是经验证的因果分类，也未穷尽原因。下面保留观测形状和候选方向，
> 不沿用「handler 被调用 ⇒ MSI 到达」「未见 EE ⇒ 设备没进 SBL」等旧推论。

| 支 | 原先约定的形状 | 候选方向（未证实） | c7 读数与限制 |
|---|---|---|---|
| A | MHI `irq entered` 恒 0 | MSI/GIC 路由 | :608 出现；软件轮询足以调用该 handler，不能据此排除硬件中断问题 |
| B | `entered` 增长但 `found no new events` | 上下文、DMA 可见性、环推进 | :610/:612/:620 未见新事件；只证明 CPU 所见没有推进，不判设备是否写过 |
| C | 有 event type、无 EE event | 事件内容与设备转换 | 抓取未见 event type；:632 硬件报告 SBL，未见 EE 处理不能推出设备没进 SBL |
| D | 有 EE event、主机 `ee` 未更新 | EE 处理与主机状态机 | 抓取未见 EE event，主机 ee=PBL；没有足够证据归因于 worker 或排除它 |

c7 是探针图：新增格式串实测 10 处（驱动侧 3 + MHI 侧 7，`c7d059d`，
`PongWifiPlatform.cpp` 与 `scripts/build-k60-ath11k.py`）。打印条数以 payload kernel 格式串为准，
不以 Lead 信里的清单为准。打印存在于镜像与打印出现在抓取中是两个问题。

### 11.4 c7 的直接观测

证据 `E:/k60-work/evidence/usblog-20261116-122546`：console.log 227,186 B / 3,367 行 /
SpringBoard 128；capture.json bytes=227186、panicMarker=null、stopReason=budget。
boot.json imageSha256=`4D187A71C4D3E0931E4E90353E69EFD53C93E61A00B56E09817AEADF47A1F45F`，
bootExitCode=0、returnedToFastboot=false。原始输出：

    :608  Pong MHI: irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00
    :610/:612/:620  Pong MHI: irq found no new events
    :618  Pong MHI: load type=2 image bytes=524288 vector bytes=5296128
    :628  Pong MHI: device in READY state
    :632  Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200

| 字段 | c7 读数 | 能支持的结论 | 边界 |
|---|---|---|---|
| hardware `exec_env` | 1 | 寄存器读数对应 MHI_EE_SBL | 不能说明设备为何没有后续转换（`include/linux/mhi.h`） |
| `mhi_state` | 1 | MHI_STATE_READY | 不是 Wi-Fi 已可用 |
| `MHISTATUS` | 0x101 | READY=1、state field=1、SYSERR=0 | 不证明 DMA/事件交接正确（`common.h:111-115`） |
| `MHICTRL` | 0x200 | RESET 位清零，控制字段请求 M0 | 请求值不等于设备已处于 M0 |
| host `ee` | 0 | 主机缓存仍为 MHI_EE_PBL | 不能证明设备没有产生未被观察到的事件 |
| `pm_state` | 2 | MHI_PM_POR（`internal.h:128,142`） | POR 不是 M0；不在错误态也不能说明等待超时的原因 |

本次抓取未见 `amss entries`、`Pong MHI: vec`、`event type=`、`EE event execenv=` 或驱动 GIC
首次入口字符串。结论限定为：**SBL/READY 后的转换未完成，未观察到 EE 处理或完整镜像 BHIE 阶段发起**。
未出现的原因及设备侧具体停点仍需验证，不把这组读数改写成已证实的双向等待。

### 11.5 指针、DMA 与地址范围的证据边界

c7 :608 的 `dev rp=0xa0001a00` 来自共享 event context，`host rp=0xfffffff9bb055a00` 是主机环指针。
pinned Linux `init.c:391-393` 先由主机令 `ring->rp = ring->wp = ring->base`，并令
`er_ctxt->rp = er_ctxt->wp = er_ctxt->rbase`。所以共享 rp 仍是初始值、CPU 没看见推进，
**不能证明设备读过上下文、DMA 可见性正常或设备没有写过**。`found no new events` 是软件读取后的分支记录。

`iova_start=0..dma_mask` 是地址包络；`init.c:480-535` 分别配置 CCABAP、ECABAP、CRCBAP
指向 channel/event/command context，另配 CTRL/DATA base 与 limit。`0xa0000000` 在该范围内，
不叫「物理 0」矛盾；落在包络内也不是设备访问成功的证据。上下文交接、缓存/DMA 可见性与实际指针配置仍未排除。

### 11.6 IRQ 日志的边界

`Ath12kWifi/shim/src/lx_rt.c:32,355,597` 的轮询路径通过 `lx_irq_raise_all()` 软件置 pending，
调用点包括 `PongAth11k.c:83`。因此 MHI 侧 `irq entered` 不能证明硬件 MSI 送达 GIC。

c7 抓取没有 `QCA6490 MSI entered the GIC handler`，只表示未观察到该入口留痕。
源码 `PongWifiPlatform.cpp:642-649` 中，`:646` 的首次入口日志在 `:647 if(pending)` 之前，
**不受 MsiStatus 非零条件保护**；旧文对该条件的描述也撤回。其缺席不能单独推出路由必错，
或推断设备在 SBL 无需发中断。需要分开核查设备事件产生、内存可见性、MSI 配置/递送与主机处理；
不能把「设备不必发」和「路由必错」当成穷尽二选一。

`QCA6490 MSI delivered by GIC` 又是另一处日志：`PongWifiPlatform.cpp:690` 在
`nw_wifi_start()` 返回非零时直接 `goto done`，`:692` 的 delivered 检查只在成功后的
runtime 循环中执行。c7 `usblog-20261116-122546/console.log:646-647` 已记录
`ath11k start failed=-110` 与 stopped，故失败路径不经过 delivered 检查。
**这条日志缺失不证明 MSI 未到，也不是最终 `msiArrivals=0` 的测量**；同一路径也没有
runtime 末次计数可补。驱动 GIC 首次入口日志在 pending 分支前，而 MHI handler 可由
软件重放；三处日志的执行条件分别核对，不能互相替代。

### 11.7 固件路径：BHI 前缀与完整镜像 BHIE 分开记录

`load type=2` 是 MHI_FW_LOAD_FBC（`internal.h:32-37`：BHI in PBL followed by BHIe in SBL）。
c7 :616-618 记录同一文件 5,296,128 B 和初次 image 524,288 B，BHI 已发过该文件 512 KiB 前缀。
所以不能写「AMSS 一个字节未送」。与此不同，完整镜像 BHIE 入口的 `amss entries` / `vec` 日志未观察到；
主机准备好段表、进入 BHIE 函数、BHIE 返回成功、设备进入 AMSS 是分别需要证据的步骤。

既有事件驱动路径（pinned Linux 静态调用链）：

1. `main.c:893-903` 解析 MHI_PKT_TYPE_EE_EVENT；SBL 事件排队 DEV_ST_TRANSITION_SBL。
2. `pm.c:823-834` 消费该转换、将 host ee 设为 SBL；fbc_download 时调用 mhi_download_amss_image。
3. `boot.c:633-645` 用 `image_info->mhi_buf[image_info->entries - 1]` 调用 mhi_fw_load_bhie，
   最后一项是 vector table。

这条路径说明 EE 处理与 BHIE 调用存在依赖，不解释 EE 处理为什么未见；不能据此推导设备必须等主机先推，
更不能把主动发 BHIE 写成已证实修复。READY→M0、事件产生/可见性与软件状态机的先后关系均待审。

BHIE 核算（由 c7 :618 的尺寸推算，**不是已观察到的 entries 日志**）：
`ceil(5,296,128 / 524,288)=11` 个数据 buffer，即 10 个满块（5,242,880 B）加 53,248 B；
`entries=12` 包含最后的 vector table，vector 中有 11 个 data-vector 项（索引 0–10）。
`boot.c:372-405` 使用 `DIV_ROUND_UP(alloc_size, seg_size)+1`；`:430-434` 将每项实际复制字节数
写入 vector size（末数据 buffer 的分配容量与有效尾长要区分）。旧的 entries=11 说法算错，不沿用。

`c2`/`c3` 所涉及 UFS lease 的 P-215 证据独立成立；本节记录的是进桌面后的 MHI 等待超时，不能用前一机制的结论代替 MHI 因果验证。

### 11.8 c8 暂停与分层验收

c8 主动发起 BHIE 当前 **HOLD**。wifi-agent 的离线复核 `82086f1069717f269c47ef194b02f660d9f0d3ef`
见 [MHI-STATE-MACHINE.md §4](https://github.com/Emilelu/UniXNU-mondrian/blob/82086f1069717f269c47ef194b02f660d9f0d3ef/docs/research/wifi/MHI-STATE-MACHINE.md#L118)
（:118-199）与 [§6](https://github.com/Emilelu/UniXNU-mondrian/blob/82086f1069717f269c47ef194b02f660d9f0d3ef/docs/research/wifi/MHI-STATE-MACHINE.md#L248)
（:248-290）。本页核对了保留的 `/opt/k60/trees/k60build/wifi/ath11k-c8/` 生成源码：

- `mhi/boot.c:622-644` 的 direct 分支只检查 FBC 与硬件 SBL，写 host `ee=SBL` 后调用
  `mhi_download_amss_image()`，**`:644` 忽略返回值**；它没有测试 SBL 工作项是否已排队，
  也没有 download-in-progress/completed 守卫。
- `mhi/pm.c:809-824` 先把 transition list 拼入本地列表、处理 PBL/firmware handler；
  `:826-839` 的 queued SBL 分支在 FBC 条件下仍会再次调用 AMSS（`:837` 同样忽略返回）。
  协作调度阻止同一 running worker 递归执行，但不消除已排队的 SBL：它可以在 direct
  调用返回后由本次或后次 worker **顺序再次调用**。这是条件可达路径，不是 c7/c8 设备实测；
  第二次函数调用也不等于第二次硬件传输完成，须区分错误态、寄存器访问与调度次序。
- 构建证据另有边界：c8 留存 `logs/eight-step.log:2-4` 的 build 选择仅六项/36 checks，
  未含 WiFi；该离线审计也确认 flash 模式漏选 parked WiFi，绿色通用门禁不能作 WiFi
  飞行许可。现存生成源/对象/归档的 hash 一致只证明当前文件一致性；mutable intermediates、
  依赖 symlink 以及恢复前未留存的临时 native-builder 精确 hash 仍是历史编译归属缺口。

文档的有限合并不再以“必须飞过 c8”作为前提；协议、去重、失败传播和构建验证缺口
交对应实现线审查，本线只引用事实，不改 driver/patch/gate。恢复实验须另有明确授权，
并分别记录以下各层证据：

| 层 | 需要的直接证据 | 能证明到哪里 |
|---|---|---|
| BHIE 发起/返回 | 函数入口、entries/vector、调用返回值与采样时点 | 入口打印只证执行到此，不代表传输成功 |
| 硬件 EE 与 MHI | exec_env、MHISTATUS/MHICTRL 前后原值，硬件是否进入 M0 | exec_env 1→2 至多证明进入 AMSS 环境，不等于 Wi-Fi 通 |
| 主机状态与事件环 | host ee/pm_state、EE event 内容与处理记录、共享指针与可见性核验 | 分别核对硬件读数与软件缓存是否同步 |
| QMI 与 ath11k | QMI 交互和 ath11k 注册结果 | 不替代 netdev/扫描验收 |
| netdev 与数据 | netdev、扫描结果、关联及数据收发 | 逐项报告，不能从一个 EE 值结全部硬件 |

判读方法同步在 [C7-READING-GUIDE.md](C7-READING-GUIDE.md) §5。

## 12. 与 `docs/engineering/FIRMWARE-REBUILD.md` 的关系（已并入 main）

本文 2026-11-15 那一版对 `FIRMWARE-REBUILD.md` 做过三条交叉核对，结论已被 main 吸收，
细节留在 `feat/wifi-ledger-fold` 的 `96e0a23` / `f9e5d0c` 与
`E:/k60-work/artifacts/refmine-20261116-fold/`。现在只需记住三件事：

1. **「四张 audio-probe 都进过 SpringBoard」不成立**：只有 `audio-probe-20261114j`
   （证据在子目录 `audio-probe-j/run1`）与 `-20261114k`（`usblog-20261115-012317`）
   有进桌面证据；`l`/`m` 从未上机（`hardware_tested=false`，无采集目录）。
   main 侧 §3 表格已按此改写。
2. **`4bbe76017eb4` 不是「包序修好之后」才出现的卷**：它首现于
   `usblog-20261113-orderfd`（15:08:56），比 `00aaeea`（15:13:07）早约 4 分钟；
   那 6 次飞行的 console 尾部是 `initproc exited -- exit reason namespace 2 subcode 0xb`
   ——根挂载失败，不是 P-154 的 `no boot entry found`。
3. **「同源同字节」不成立**（main 的 P-216）：`SOURCE_DATE_EPOCH` 只固定
   `__DATE__`/`__TIME__` 与 PE 时间戳，LLD 派生的 CodeView build-id 仍然每次不同。
   同检出同 pin 重建三次得 `ce12d145a71e` / `77ad2474a468` / `9f20de15388a`。
   所以 **FD 的 sha 是「这一次构建」的标识，不是身份**；能不能用只能上机。
   两卷的 sha 差异本来也确实来自不同 uefi pin（`4bbe7601` ↔ `9b79562` 的
   `%ct = 1794541119` = UTC 2026-11-13 03:38:39；`cf448571` 内嵌
   `Nov  2 2026 10:03:21` 的 `ct 1793613801` 在 uefi 38 个提交里查无，
   workspace 串是 `/home/emilelu/hackios/uefi-mondrian` 而非 `/mnt/e/…`）。

**已修**：`FIRMWARE-REBUILD.md` §2 曾把 `SOURCE_DATE_EPOCH` 的行号写成 `:85`，
实际是 **`:69`**（`env.setdefault('SOURCE_DATE_EPOCH', git(uefi, 'log', '-1', '--format=%ct').strip())`，
注释在 `:68`；`:85-86` 是 `fd_path()` 与 `st_size` 校验）。2026-11-16 由本线在本分支上
改成 `:69` 并注明后两句，main 侧同步时以本分支为准。

## 13. 还开着的口子

按「离结论的距离」列出仍需分开记录的事项：

1. **MHI 后续状态转换仍待定位**（§11）：`c7` 只证明采样时硬件处于 SBL/READY、主机请求 M0、
   host `ee` 仍为 PBL 且抓取未见 EE 处理或完整镜像 BHIE 发起日志。c8 主动 BHIE 当前暂停；
   先审重复下载、重入与 READY→M0 协议，再按 §11.8 分层取证。
2. **PWF2 头失配**：`wifi-20261114a` 与 `mhi3`/`mhi4` 的 PWF2 头 `count=6` 但只有
   `entry[0]=amss.bin` 非空（`entry[1..5]` 全空），而 `__const` 里实际有四个真固件
   （`amss.bin` 5,470,128 / `amss20.bin` 5,296,128 / `m3.bin` 266,684 /
   `regdb.bin` 24,278，合计 11,057,218，区总长 11,189,974）⇒ 运行期取不到 `m3`/`regdb`。
   `c2`/`c3` 起容器改成六条全有 payload（sha `3f68db4dc0927742`），这一条**在新图上
   已经不存在**，只在旧图上留作记录。
3. **tiny B 格（`t0c`/`t1c`）从未飞**：只有占位头的静态事实，无受控启动结果；
   `c3` 不能替它预测结果，本轮也不据此授权补飞。
4. **旧图逐图归因仍有边界**：`wifi-20261114a` 是 trial 级，manifest 无 `series` 键，
   身份不可复核（P-201）；`c0` 身份不符，仅使格无判别力；`c1` 修 UUID 后仍 silent，
   不能补无日志崩点；独立 bt-s4b-c 不由 P-215 解释。其它未核验 series/archive/实际调用路径
   仍记未知，不编造它们已走过 UFS lease 失败分支。

**已有限排除，不再作统因**：内核总大小的单一阈值、`__TEXT`/容器驻留位置、pool/窗口
占用不能单独解释 `c2`/`c3` 及所列已观测对照；`pong_wifi=0` 不能保护所审 UFS lease 路径。
Data UUID、参数、C++ 全局构造器、`__init_entry_set`、ADT 窗口值、固件卷 DTB 等旧排除
仍须按对应材料的样本与静态范围读取，不构成所有旧 silent 的全局排除清单。
