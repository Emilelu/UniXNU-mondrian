# WiFi silent 死因与固件 blob 的 residency

> 底稿：本页由 `feat/wifi-ledger-fold` 分支上的两版账本（`96e0a23`、`f9e5d0c`）重排而成。
> 那一支保留「排除法怎么一格一格走」的全过程与每一版被推翻的措辞；本页只写当前事实
> 与当前结论。要查某条判断是哪天、被哪张镜像推翻的，看那一支。

状态（2026-11-16）：**silent 已结案**——死因是 UFS SMMU lease 被提前索取（P-215，§10），
单变量证据是 `c3` 与 `c2` 只差 20,480 B 代码；**MHI 阶段已定位到「AMSS 从未被下载」**
——`c7` 的十阶段全通、设备进 SBL（`exec_env=1`）、事件环为空、`amss entries` 打印
0 次，说明 `mhi_download_amss_image()` 从未被调用：设备在 SBL 等 AMSS，主机在等
EE 事件，是死锁而不是超时（§11）。下一步只有一件事——`c8` 主动推 AMSS。

本页回答两个问题，答案都在这里：

1. 11.19 MB 的 PWF2 固件放进内核，会不会撞上装载边界？——**不会**：这条路径上每个
   硬边界都被实测值绕开，余量最小的一项（117 MB 镜像 vs `ReadFile` 的 128 MB）也有
   1.14×（§3）。
2. 那么 2026-11-14 至 11-16 那十张 0 字节的 wifi 镜像为什么死？——**UFS 侧**：
   `patches/wifi/0004` 让 `PongUfsTransport::hostBringUp()` 在 UFS 启动时索取 Apps
   SMMU lease，而锁只在 `pong_rpmh_init()` 里分配、后者晚于 UFS（§10）。blob、版式、
   驻留、窗口、参数、Data UUID 六条轴全是**观测轴**，它们与死亡同步变化只是因为
   `-Wl,-force_load` 把 wifi 归档（含这段 lease 代码）一起带进内核。

## 0. 结论

| # | 结论 | 证据 | 推翻条件 |
|---|---|---|---|
| 1 | silent 的死因是 UFS SMMU lease 未就绪时被索取，不是 blob / 版式 / 窗口 | `c3` = `c2` + `patches/wifi/0012`（20,480 B），同版式同容器，`c3` alive / `c2` silent（§10.1） | 找到一张带 0012 仍 silent、或去掉 0012 仍 alive 的镜像 |
| 2 | `pong_wifi=0` 挡不住死因 | 同上：`c2`/`c3` 都是 `pong_wifi=0`；开关只挡住 worker，挡不住 UFS 更早的那次索取（§10.2） | 同上 |
| 3 | 装载边界全不触发 | 段 12,992,512 vs 256 MB；span 129,642,496 vs 254 MB；镜像 117,305,344 vs 128 MB；段数 15/64；重叠 0；XNU 无上限常量（§3–§5） | 见 §0.1 |
| 4 | 带真 PWF2 的已飞镜像里有一张 alive | 全库 join：11 张带真容器 → 1 alive（`c3`）/ 10 silent；不带容器的 47 张 → 38 alive / 8 silent（§9.2） | 再飞同类得到不同分组 |
| 5 | 「内核总大小」不是轴 | `bt-s4b-20261115b` 106.5 MB alive 而同尺寸的 `c` silent；`adsp-20261115c/d/e` 128,991,232 B 三张全 alive（§2、§9.2） | 一张 >117 MB 且带 PWF2 的 alive 镜像不构成推翻（`c3` 已如此），要的是「>117 MB 且带 PWF2 仍 silent 而小镜像 alive」的反向证据 |
| 6 | MHI 停在「AMSS 从未被下载」，不是链路问题 | `c7`：十阶段全通、设备 `exec_env=1`（SBL）、`MHISTATUS=0x101`（READY 且无 SYSERR）、事件环 `rp` 前后一致；`amss entries`/`vec` 打印 **0 次** ⇒ `mhi_download_amss_image()` 从未被调用（§11.3–§11.4） | `c8` 推完 AMSS 后 `exec_env` 仍不从 1 变 2；或 `amss entries` 打印出现、设备仍不回 EE 事件 |

### 0.1 各判断的推翻条件

每条判断都能被一行实测推翻；写在这里是为了让下一个人知道该看什么。

- **§0 第 3 行（边界）**：出现 `__TEXT` vmsize > 256 MB 仍过 `ParseKernel`；或实测 span
  > 253,388,800 仍过 :196；或内核镜像 > 134,217,728 字节仍被 `ReadFile` 接受；或
  vmsize≠0 的段数 ≥ 64 被接受；或在 xnu-work 找到任何以 `__TEXT` 大小为输入的上限
  （grep 之外还要读 `pmap_bootstrap` 与 KTRR 相关代码）。
- **§0 第 1、2 行（死因）**：任何一张「链了 wifi 归档、没带 0012」却 alive 的镜像，
  或任何一张「带了 0012」却 silent 的镜像。
- **§0 第 6 行（MHI）**：`c8` 推完 AMSS 之后 `exec_env` 仍停在 1（SBL）；或 `amss entries`
  打印出现、设备却仍停在 SBL 不发 EE 事件。

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

三条对照把「体积」这条轴彻底打掉：

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

**驻留位置也不是轴**：`t2`/`c2`/`c3`/`c4`–`c7` 把容器从 `__TEXT,__const` 搬到
`__DATA_CONST,__const`（`__TEXT` 回到 1,802,240、`__DATA_CONST` 12,124,160），
其余逐项相同；`c2` silent、`c3` alive——同一驻留位置两种结果。

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
容纳 WindowSize——它**不读内核段**。固件 blob 对它唯一的影响是 :619 的
`Used > WindowSize - BLOCK_SIZE`（Used = kernel span + args/tree/ramdisk/trustcache 的
16 KB 对齐和），对 4.5 GiB 窗口远不可及。这一步的真实失败模式是「NO WINDOW」（内存碎片），
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

## 6. 六格判别矩阵：观测轴是怎么被逐条打掉的

这张表是 2026-11-15 设计的对照计划。**它现在只是记录**——每一格的结局列写的就是
「这条观测轴最后怎么了」。没有一格的结局是「死因」。

| 格 | 内核 | `__TEXT` | blob | `pong_wifi` | 结局 | 打掉了什么 |
|---|---|---|---|---|---|---|
| A | 54.2 MB stock（thermal / bt / …） | 1.64 MiB | 无 | 0 | alive | 基线 |
| B | 54.8 MB tiny（`t0c`/`t1c`，kernel 54,804,480，`__TEXT,__const` 593,943） | 1.82 MiB | 4×23 B 占位（PWF2 count=4、span 16,407） | 0 / 1 | **从未飞** | 判别价值已被 `c3` 抢走：它只能再确认一遍「链了归档就得带 0012」 |
| C | 66 MB（`c0` / `c1`，66,002,944） | 12.39 MiB | 11.19 MB 真容器 | 0 | `c0` 测量无效（种子 UUID）；`c1` silent | 「种子 UUID ⇒ 零字节」不成立（§10.4） |
| D | 117 MB（`mhi5`） | 12.39 MiB | 11.19 MB | 1 | 从未飞 | 判别价值已被 `c3` 抢走 |
| E | 117 MB（`z0`，与 `mhi5` 只差 `pong_wifi`） | 12.39 MiB | 11.19 MB | 0 | silent（`usblog-20261115-135859`） | 「驱动活体」——但 `pong_wifi=0` 时 worker 本来就没跑，这条读法只能证明「worker 没跑也死」 |
| F | 117 MB（`t2`；`c2` 复现） | 1.80 MiB | 11.19 MB（`__DATA_CONST`） | 0 | 两飞都 silent | 「`__TEXT` 驻留」 |
| G | 117 MB（`c3` = `c2` + 0012 惰性锁） | 1.80 MiB | 11.19 MB（`__DATA_CONST`，与 `c2` 逐字节相同） | 0 | **alive**（`usblog-20261116-015128`） | 一次单变量干预，把前六格的所有观测轴一起打成观测轴 |

G 格之后这张表的读法只有一句：**A–F 否证的是六条观测轴，不是六条因果轴**。
真正的因果轴是 UFS SMMU lease（§10.2），它不在任何一格的自变量里。

## 7. pool / 窗口通道：已关闭

2026-11-15 那一版把这条列为主要嫌疑之一（`ReadFile` 在 :558 把整个内核吃进 DXE pool，
之后 :607 才申请 4.5 GiB 连续窗口；blob 使 pool 占用多 11.27 MB，可能改变
`AllocateWindow` 看到的最大 run）。`c3` 关掉了它：

- `c3` 与 `c2` 同 117 MB 版式、同 pool 占用、同窗口（0x120000000 = 4.5 GiB）、
  同真 PWF2 容器，**一个活一个死**。同池占用两种结果 ⇒ pool 不是通道。
- 反向压力也指向同一结论：`adsp` 三张 129 MB（`__DATA` 76,414,976、span 141,111,296，
  都比 117 MB 家族大）在同一 4.5 GiB 窗口下全部进桌面。若 pool 占用是通道，它们应该
  先撞线；它们没有。

**仍留一个静态空白**（不影响结论，只影响「为什么」的完整度）：0 字节的 console 里没有
`NO WINDOW` 行可读，`AllocateWindow` 到底走到哪一步无法从旧证据里读出来。`c3` 的
alive 是从反面关闭这条通道的，不是从正面证明窗口申请成功。

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
| 死因调用链 | `drivers/NativeUfs/PongUfsTransport.cpp:29,143,174-181,602`；`drivers/PongWifi/PongWifiPlatform.cpp:152,716-718,729,787-788`；`drivers/ArmDTPlatform/ArmDTPlatform.cpp:227-228` |
| `c0` 测量无效 | `E:/k60-work/artifacts/wifi-20261116c0/boot.img` 内 `6DCCF70A-…` ×1、`1BCD69FF-…` ×0；构建树 `k60-wifi` @ `fff0fb19` 的 `configs/mondrian_wifi_defconfig:46` 指名种子 UUID；P-152（`docs/engineering/PITFALLS.md:3811-3819`）；P-209 门禁 `scripts/check-defconfig-uuid.py`（main `011669a`，tag `snap-r201`） |
| 构建配置扫描（53 张 wifi/bt boot.img） | `E:/k60-work/scratch/refmine/uuid-scan.py`：56 个产物里 3 个没有 boot.img；扫到的 53 张中**只有 `c0` 带种子 UUID**，其余 52 张都是设备 UUID |
| P-215 原文 | main `docs/engineering/PITFALLS.md:5337` 起；Check：`scripts/tests/test-pong-smmu-lease.py`、registry id `P-215` |
| MHI 固件加载链 | pinned linux（`/home/emilelu/wifi-inputs/linux`）`drivers/bus/mhi/host/boot.c:490,555-575,633-653`；`main.c:893-906`；`pm.c:196-204,823-836,1277-1298`；`internal.h:32-37,78-79,143-162`；`common.h:111-115`；`include/linux/mhi.h` 的 `enum mhi_ee_type` / `enum mhi_state` |
| 兼容层无条件重放 IRQ | `Ath12kWifi/shim/src/lx_rt.c:32,315,347,355,597`；调用点 `drivers/PongWifi/ath11k/PongAth11k.c:83`；驱动侧真证据 `drivers/PongWifi/PongWifiPlatform.cpp:566,644,646,649,706` |
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
| wifi-20261116c7 | 117,342,208 | **1,802,240** | 53,215,232 | 129,757,184 | 2 | **18** | 1 + `rsc=2` | **未飞**（§11.3 判据待落） |

从这张表直接读出来的事实（都可推翻）：

1. `z0` 不是 66 MB 的 C 格：它 117,305,344 B，是 `mhi5` 的孪生（只差 `pong_wifi`）。
   66 MB 那一格是 `c0`/`c1`。
2. `a2` 与 `mhi4` 的唯一差别是 `pong_wifi`（`Pong MHI` 串数 0 vs 11），但 `a2` 是
   P-201 的 trial 级——manifest 没有 `series` 键，身份不可复核。
3. 105 MB alive 家族的 `__TEXT` 与 54 MB 基线完全相同；`__TEXT` 12,992,512 是 wifi
   家族独有的。
4. `t2`/`c2` 的 `__TEXT` 只有 1,802,240 仍 silent，而 `c3`/`c4`–`c6` 同版式 alive ⇒
   驻留位置与生死无关。
5. bt 同尺寸一活一死；adsp 129 MB 三张全 alive ⇒ 阈值模型两次被否证。
6. `c3` 与 `c2` 的差只有 20,480 B（`patches/wifi/0012`），而那就是死因。
7. `c4`/`c5`/`c6` 与 `c3` 段表逐项相同，只差 `kernel_args`（`pong_wifi=1`、
   `k60_wifi_rsc`）与补丁——三张都 alive，所以 `pong_wifi=1` 与 RSC 投票本身不致死。

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
`usb-20261115b`、`usb-20261115c`），与本问题无关。

**这张表只能当观测轴读**：它证明「带真容器与生死高度同步」，不能证明「容器导致生死」。
`c3` 是那张推翻条件（一张带真 PWF2 的 alive 镜像），推翻之后剩下的因果解释是
`patches/wifi/0004` 的 lease 段——它随 wifi 归档一起被 `-force_load` 带进内核，
与容器同步出现，但不是容器。写法教训见 §10.5。

## 10. silent 结案：死因是 UFS SMMU lease（P-215）

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
这是本账本里唯一一次**单变量干预**，也是唯一一次能把「观测轴」变成「因果轴」的飞行。

口径脚注（`c3` 的计数两处差异）：本页写 console.log **221,429 B / 3,204 行 / SpringBoard 133**，
Lead 那侧记 3,202 行 / 132 次。字节数两边一致；行数与计数差来自统计方式——
本页按 `capture.json` 的 `bytes` 与整文件计数（含 supervisor 头尾行），
Lead 用的是 `grep -c` 粗计。**以 `capture.json` 为准**，差异只在这两个派生计数上。

### 10.2 死因调用链

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

**UFS 是根设备，必然先启动**（能起的日志里 `PONG_UFS` 在 115 行、
`ArmDTPlatform: registered platform` 在 147 行）。于是 UFS 索取 lease 时
`smmuLeaseLock == NULL` ⇒ lock() 返回 false ⇒ `transportFailure("Apps SMMU lease
unavailable")` ⇒ 整个 UFS transport 放弃 ⇒ 没有根设备 ⇒ 内核在 console worker
起来之前就死 ⇒ **0 字节**。

修法（`patches/wifi/0012`，单变量）：`if(!smmuLeaseLock) smmuLeaseLock=IOLockAlloc();
if(!smmuLeaseLock) return false; IOLockLock(smmuLeaseLock); return true;` —— 分配搬进
lock() 自己，`pong_rpmh_init()` 里那次分配保留。补丁注释原文：
"the first client to want it is not necessarily the WiFi worker: NativeUfs takes
the same lease in hostBringUp()"。

**为什么这条能解释全部负结果**：`pong_wifi=0` 只挡住 worker 之后的注册，挡不住 UFS
在更早的 `hostBringUp()` 里索取同一把锁。只要 wifi 归档被 `-Wl,-force_load` 链进内核
（`patches/wifi/0010`），**即使驱动开关是 0**，UFS 也会因为这把锁未分配而失败。
尺寸、段表、blob 位置、窗口、参数、Data UUID 全都不是原因，它们只是恰好与「链了
wifi 归档」同步变化。

### 10.3 `c0`：`invalid-measurement`（保留这一条，因为它是「先 diff 构建配置」的样本）

`c0` 由 `mondrian_wifi_defconfig` 构建，该文件在 `k60-wifi` @ `fff0fb19` 的 `:46`
指名了种子 Data UUID `6DCCF70A-…`；内核在根挂载阶段等这个卷超时后自 panic
（P-152 机制：`PONG APFS: wait for Data UUID 6DCCF70A-…, timeout=5s` → `K60DATA UFS
Data window not published` → `dataerr=2` self-panic `@kern_exec.c:8463`），console 在
根挂载之后才起来，所以读数是 0 字节。

- 实测字节：`c0` 的 boot.img 内 `6DCCF70A-…` ×1、`1BCD69FF-…` ×0；全库 53 张 wifi/bt
  boot.img 里**只有这一张**带种子 UUID。
- 重测 `c1`（只改该 UUID 一行）已飞：boot.img 内 `6DCCF70A-…` ×0 / `1BCD69FF-…` ×1，
  段表与 `c0` 逐项相同，仍然 0 字节 ⇒ **「种子 UUID ⇒ 零字节」不是充分原因**。
  `c0` 维持 `invalid-measurement`，`c1` 是有效 silent。
- 门禁 P-209（`scripts/check-defconfig-uuid.py`，main `011669a`，tag `snap-r201`）：
  defconfig 指名非本机 Data UUID 即硬失败，种子 UUID 必须显式标 `# SEED-UUID: intentional`。

### 10.4 `c4`/`c5`/`c6` 把「`pong_wifi=1` 本身」也洗清了

三张都是 `c3` + `pong_wifi=1`（`c5` 加 `k60_wifi_rsc=1`，`c6` 加 `k60_wifi_rsc=2`），
段表与 `c3` 逐项相同，三张全部 alive（§9.1）。所以：

- `pong_wifi=1` 不再致死——`c3` 之后 lease 已修，worker 能跑，系统照样进桌面。
- `k60_wifi_rsc=1`（只读探针）与 `=2`（投票）本身也不致死。

### 10.5 方法论：观测轴 ≠ 因果轴

2026-11-15 那一版写过一句「带 PWF2 的已飞镜像没有一张 alive……所以『blob 在场』是
目前唯一没有被任何 alive 镜像打过的轴」。join 方法没错（11 张里 10 张 0 字节是实测），
**错在结论强度**：一张表能证明「这条轴与生死同步」，不能证明「这条轴导致生死」，
除非做过单变量干预。正确写法就是当时写在推翻条件里的那句——「推翻条件 = 一张带真
PWF2 的 alive 镜像」——**推翻条件写对了，只是没等到它出现就把它写成了因果**。

三条可复用的写法：

1. 观测轴表格的结论列只能写「这是目前唯一还分得开生死的观测轴」，不能写「这是死因」。
2. 每条轴必须带一行推翻条件；这是唯一挡住错误扩写的东西。
3. 单变量干预之后，旧表要**保留原样并标注结局**，不要删——被推翻的过程本身是记录
   （§6 矩阵按这个方式处理；完整过程在 `feat/wifi-ledger-fold` 分支）。

## 11. MHI 阶段：PCIe/MHI 控制链路十阶段全通、SBL 已进、AMSS 未推

> 缺的就是「EE 事件触发的那一次 AMSS 下载」。这一条是 `c7` 的实测结论（§11.4–§11.5），
> 不是推测；`c8` 的主动推送是唯一未做的干预（§11.8）。

### 11.1 `c4`/`c5`/`c6` 已经量到什么

三张都是 `c3` + `pong_wifi=1`，段表逐项相同（§9.1），三张全部进桌面。所以
「`pong_wifi=1` 会致死」这条已经不在候选里。MHI 的进展停在 `c6`：

| 阶段 | `c6` console 行 | 内容 |
|---|---|---|
| 1–4 | :482-490 | 电源轨、REFCLK、QMP PHY 表、PCIe 链接 |
| 5 | :500 | SM8475 WLAN rail 请求被确认（五条轨真值：smpe2 PPID=49e 1012 mV status=8f / smpb11 PPID=1b9 966 mV / smpb10 PPID=1b6 1800 mV / smpc1 PPID=29b 1900 mV / smpb12 PPID=1bc 1350 mV，observerErrors=0） |
| 6 | :502 | cold REFCLK PHY_CTRL=900->900 mux=2 CLKREF=1 |
| 7 | :503 | 82-entry vendor QMP PHY table |
| 8 | :513-518 | `QCA6490 PCI subsystem=10817cb`、link 与 BAR 建立、APPSSMMU SID 1c01 独占 4K context、wired DMA 预算 64 MiB |
| 9 | :586-587 | 64 MiB wired DMA 从 16384 spans 映射（35 个 native 4K 表页）、SID1c01 DMA 与 retained MSI landing page |
| 10 | :588-592 | PARF MSI0 → GIC SPI140 挂接、DesignWare MSI receiver armed、`ath11k: MSI vectors: 32`、`wcn6855 hw2.1` |
| MHI 注册 | :596-600 | `MHI register regs=0xfffffff97415c000 len=2097152 fw_data=0 fw_sz=0 sbl=524288 seg=524288`、`channels=128 timeout=2000`、`start timeout=20000 ee=0 state=0` |
| 复位 → READY | :608-620 | `serial=0x22d0a7f3 ee=0 fbc=1 fw_sz=0`、`firmware amss20.bin bytes=5296128`（主机侧读文件，不是推给设备）、`load type=2 image bytes=524288 vector bytes=5296128`、`reset cleared, polling MHISTATUS ready bit`、**`device in READY state`** |
| 卡住 | :622-635 | `Wait for device to enter SBL or Mission mode` → `ath11k: failed to power up mhi: -110`（ETIMEDOUT）→ `failed to start mhi: -110` → `Pong ath11k PCI/MHI initialization failed: -110` → `WiFi initialization stopped` |

读法：**PCIe 与 DMA 这一侧是通的**（十阶段全过、64 MiB wired DMA 真映射、MSI 武装、
设备真进 READY）。但这一行里有两处读法在 `c7` 之后要收回：`amss20.bin bytes=5296128`
是**主机侧读固件文件**，不是推给设备（§11.5）；`device in READY state` 是**轮询**
`MHISTATUS` 读到的（`pm.c:196-204` `mhi_poll_reg_field`），全程不经过中断。
所以 `c6` 只证明「寄存器读得通」，没有证明「中断到得了」。

### 11.2 拓扑事实（写判据之前必须先定这一层）

k60-wifi `docs/research/wifi/MSI-TOPOLOGY.md`：

- **我们走 DesignWare legacy**：PARF MSI0 = `1u<<23` → GIC SPI 140 = INTID 172
  （`PongWifiPlatform.cpp:43` `PcieGlobalIntid = 32 + 140`、`:683` `armcpu_spi_attach`；
  `ArmCpu.cpp:403` 对 unowned SPI 直接 panic）。
- **设备树 `msi-map` 指向 ITS** `msi-controller@17140000`（phandle 0x237，
  event base 0x5980/0x5981）。
- **真机 Android 走 ITS**：`/proc/interrupts` 里 `ITS-MSI 524289..524306` 是活的。
- 第三个节点 `/soc/qcom,pcie0_msi@0x17110040`（32 个 SPI 768..799）status=disabled。

**`c6` 的 READY 握手不能证明「legacy 路由能送事件」**——这句推论在 2026-11-16 13:08
被收回：复位清零与 READY 位都是 `mhi_poll_reg_field` 轮询 `MHISTATUS` 读到的
（`pm.c:196-204`），不经过中断。中断通不通，只有驱动自己挂在真 GIC 上的那个 handler
能说话（§11.6）。

### 11.3 飞之前的判据表（保留原样：四支都没命中）

> 这张表是 `c7` 出图**之前**写的判据，保留它是为了让下一次看到「判据全落空」的人知道
> 该往哪加一支——`c7` 的实测落在四支之外（§11.5）。

`c7` = `c6` + MHI 诊断打印（k60-wifi `c7d059d`「instrument the READY to MISSION
stall」，2 files +101/−2；实测 **10 处**格式串，驱动侧 3 + MHI 侧 7；`scripts/build-k60-ath11k.py` 加 amss entries / last dma /
vec[0..2] 打印与 `Pong MHI: timeout after %u ms ee=%d pm_state=%d exec_env=%d
mhi_state=%d MHISTATUS=%#x MHICTRL=%#x`）。不改状态机、不改段长、不改 MSI 目标——
它是探针图，不是修复图。

| 支 | 观测 | 指向哪一层 | 下一步方向 |
|---|---|---|---|
| **A** | `Pong MHI: irq entered` 恒 0 | MSI 没到 GIC | MSI 拓扑：ITS vs PARF legacy（§11.2） |
| **B** | `entered` 在涨，但 `found no new events` | 事件环 `rp` 不动 | MHI 地址空间：`iova_start=0` 疑点 |
| **C** | 有 event type，但没有 `EE_EVENT` | 设备侧没进 SBL | 固件加载 / SBL 入口 |
| **D** | 有 EE event，但 timeout 行 `ee` 仍是 0 | 软件状态机没记账 | `mhi_pm_st_worker` |

`c7` 飞完之后四支的实际读数（逐条对照，不合并）：

| 支 | `c7` 实测 | 是否命中 |
|---|---|---|
| **A** | `irq entered` 出现了（:608），但这一行**不能**证明硬件发了中断（§11.6 兼容层无条件重放） | 形状不命中；且该行的证明力为零 |
| **B** | 形状命中：`irq entered` 有、`found no new events` 连打三次、两条 `rp` 一致 | **形状命中但归因错**——环空不是地址空间错，是设备在 SBL 里没东西可发 |
| **C** | `event type=` 0 次，但设备**已经在 SBL**（`exec_env=1`） | 不命中：设备侧动了，只是没发事件 |
| **D** | `EE event` 0 次，`ee` 仍是 0 | 不命中：不是软件没记账，是根本没有事件可记 |

所以第五支是「**设备在等 AMSS、主机在等事件**」：链路全通（十阶段）、设备有动作
（进了 SBL）、固件没推（AMSS 一个字节没发）、两边互相等。四支的共同前提是「设备侧
根本没有动作」，而这个前提本身被 `exec_env=1` 否掉了。

逐行的判读流程写在 [C7-READING-GUIDE.md](C7-READING-GUIDE.md)，其中四支之外的第五支
已经补进那一页。该页同时记了 `c7` 实测的 **10 处**新打印（驱动侧 3 处 + MHI 侧 7 处，
从 payload kernel 的格式串直接取出），比口头说的「八条」多两处——**打印条数以镜像里的
格式串为准，不以任何清单为准**。

### 11.4 `c7` 的实测：第五支——链路全通、AMSS 未推、设备空等

证据 `usblog-20261116-122546`（`console.log` 227,186 B / 3,367 行 / SpringBoard 128 /
panic 标记 0；`boot.json` `imageSha256 4D187A71…F45F`、`bootExitCode 0`、
`returnedToFastboot false`）。关键行只有两条：

    :608  Pong MHI: irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00
    :632  Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1
          mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200

六个字段逐个读（枚举与掩码取自 pinned linux，路径见 §8）：

| 字段 | 值 | 读法 | 出处 |
|---|---|---|---|
| `exec_env` | **1** | `MHI_EE_SBL`——设备已离开 PBL、收完 512 KiB SBL、正在 SBL 里等 AMSS | `include/linux/mhi.h` 的 `enum mhi_ee_type`（PBL=0、SBL=1、AMSS=2） |
| `mhi_state` | **1** | `MHI_STATE_READY` | 同上 `enum mhi_state` |
| `MHISTATUS` | **0x101** | bit0 ready=1、bit8-15 mhistate=1、bit2 SYSERR=**0** ⇒ 设备无系统错误 | `drivers/bus/mhi/common.h:111-115` |
| `MHICTRL` | **0x200** | bit1 RESET=0（复位已释放）、bit8-15=2（M0） | 同上 |
| `ee` | **0** | 主机缓存的 `mhi_cntrl->ee` 还是初值 `MHI_EE_PBL`，**从未被 EE 事件更新** | `include/linux/mhi.h` |
| `pm_state` | **2** | 不在错误态（`MHI_PM_IN_ERROR_STATE` 要 ≥ `BIT(7)`） | `drivers/bus/mhi/host/internal.h:162` |

两条 `rp` 的读法：`dev rp = 0xa0001a00` 是设备写的事件环读指针（IOVA 视角），
`host rp = 0xfffffff9bb055a00` 是同一位置经 `mhi_to_virtual()` 后的主机虚拟地址；
两者指向**同一个槽**，且 `irq found no new events` 在 :610/:612/:620 连打三次 ⇒
事件环**确实是空的**，不是解析失败、也不是 rp 落后。

所以 `c7` 的判决是第五支：**设备在 SBL 等 AMSS，主机在等 EE 事件**。
两边都在等对方，这不是超时，是死锁；`-110` 只是 20 s 之后宿主放弃等待的表现。

### 11.5 为什么 AMSS 从来没被送出去

`amss entries`、`Pong MHI: vec` 两条打印在 `c7` 的 console 里**各 0 次**。这两条打印
的注入锚点（k60-wifi `c7d059d` 的 `scripts/build-k60-ath11k.py`，boot.c 段）是
`mhi_download_amss_image()` 函数体开头的局部变量声明，**只在这个函数被调用时才会执行**。
0 次 ⇒ 这个函数从未被调用，5,296,128 B 的 AMSS 只被 `memcpy` 进了 BHIE 段表
（`mhi_fw_load_handler` 的 `fbc_download` 分支），**一个字节都没有送到设备**。

调用链（pinned linux，行号实读）：

1. 设备在事件环里写一个 `MHI_PKT_TYPE_EE_EVENT` —— 这是**唯一**入口。
   `drivers/bus/mhi/host/main.c:893` `case MHI_PKT_TYPE_EE_EVENT:` → `:896`
   `enum mhi_ee_type event = MHI_TRE_GET_EV_EXECENV(local_rp);` → `:900-903`
   `case MHI_EE_SBL: st = DEV_ST_TRANSITION_SBL;`
2. `DEV_ST_TRANSITION_SBL` 在整个 `drivers/bus/mhi/host/` 里只有 **`main.c:902` 这一个
   排队点**（`grep -rn DEV_ST_TRANSITION_SBL` 只命中 `main.c:902` 与 `pm.c:823`）。
3. `pm.c:823` `case DEV_ST_TRANSITION_SBL:` → `:830` `mhi_cntrl->ee = MHI_EE_SBL;` →
   `:832` `mhi_create_devices()` → `:833-834` `if (mhi_cntrl->fbc_download)
   mhi_download_amss_image(mhi_cntrl);`
4. `boot.c:633` `int mhi_download_amss_image(struct mhi_controller *mhi_cntrl)` →
   `:643-645` `ret = mhi_fw_load_bhie(mhi_cntrl, &image_info->mhi_buf[image_info->entries - 1]);`
   （注释「Vector table is the last entry」）。

没有第 1 步，第 3 步永远不发生，`mhi_cntrl->ee` 永远停在 0——这正是 `c7` 的读数。
SBL 那 512 KiB 是走 BHI 送进去的：`load type=2` = `MHI_FW_LOAD_FBC`
（`internal.h:32-37`：`MHI_FW_LOAD_BHI`=0 / `MHI_FW_LOAD_BHIE`=1 / `MHI_FW_LOAD_FBC`=2，
注释「BHI in PBL followed by BHIe in SBL」）——BHI 段送 SBL、BHIe 段送 AMSS，
前半段成功、后半段没开始，与实测完全吻合。

### 11.6 中断证据的边界：handler 被调用不等于硬件发了中断

上一轮曾有一条错判：「`c7` 的 `irq entered` 证明 MSI 真的到了 GIC，所以『MSI 没到』
已被排除」。**这条是错的，不要沿用。**

兼容层每毫秒把所有已注册 IRQ 无条件置 pending：`Ath12kWifi/shim/src/lx_rt.c:597`
`lx_irq_raise_all()` 对 `g_irq[i].used` 的每一项置 `pending = 1`，由 `:355` 的
`lx_pump()` 驱动（`g_irq_polling` 默认 1，见 `:32`），调用点在
`drivers/PongWifi/ath11k/PongAth11k.c:83`。所以 handler 一定会被调用，
**调用次数不能当硬件证据**。

有效的证据是驱动自己那条：「`QCA6490 MSI entered the GIC handler`」在 `c7` 里 **0 次**
（`PongWifiPlatform.cpp:646`，只在 `MsiStatus` 读到非零时打），`MsiStatus 0` 也是 0 次
⇒ GIC 没有在 INTID 172 上抬过任何东西。这条证据**依然指向 MSI 未到**。

但它不构成「AMSS 未下载」的独立原因：设备在 SBL 里等 AMSS 时本来就不会发 MSI，
所以「MSI 未到」与「AMSS 未推」是同一件事的两面。`c8` 推完 AMSS 之后若
`MSI entered` 仍是 0，那才是一条新的、独立的发现。

### 11.7 本节与 silent 结论的关系

silent 的结论（§10）**不依赖本节**：`c3` 已经用单变量把 0 字节结案，`c4`–`c6`
进一步证明「修好之后带 `pong_wifi=1` 也能进桌面」。本节只回答「进桌面之后 wifi 为什么
还没起来」，它的失败模式是**有日志的 -110 死锁**，与 0 字节不是同一类故障，
不能用 silent 时期的任何结论去解释它。

### 11.8 `c8` 的唯一判据

`c8` = 主动推 AMSS（不等 EE 事件）。读它只看一件事：**`exec_env` 在推 AMSS 前后
是否从 1 变 2**。

| `c8` 读数 | 含义 | 下一步 |
|---|---|---|
| `exec_env` 1 → 2，且出现 `amss entries` 打印 | AMSS 推成功、设备进 AMSS ⇒ 死锁解除 | 看 `MHI_IN_MISSION_MODE` 是否成立，转入正常起网 |
| `amss entries` 打印出现但 `exec_env` 仍 1 | AMSS 送了但设备没接受（校验 / 段表 / BHIe 通道） | 查 BHIE 段表与 `mhi_fw_load_bhie` 返回值 |
| `amss entries` 仍 0 次 | 主动推路径没有生效（插桩没进去 / 调用点没接上） | 先验镜像身份，再查插桩锚点 |

判据同时写在 [C7-READING-GUIDE.md](C7-READING-GUIDE.md) §5。

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

按「离结论的距离」排序，只有四条：

1. **AMSS 从未被推给设备**（§11）：`c7` 已定位到「设备在 SBL 等 AMSS、主机在等 EE 事件」
   的死锁，唯一未做的干预是 `c8` 主动推 AMSS。这是当前唯一的活跃工作，判据见 §11.8。
2. **PWF2 头失配**：`wifi-20261114a` 与 `mhi3`/`mhi4` 的 PWF2 头 `count=6` 但只有
   `entry[0]=amss.bin` 非空（`entry[1..5]` 全空），而 `__const` 里实际有四个真固件
   （`amss.bin` 5,470,128 / `amss20.bin` 5,296,128 / `m3.bin` 266,684 /
   `regdb.bin` 24,278，合计 11,057,218，区总长 11,189,974）⇒ 运行期取不到 `m3`/`regdb`。
   `c2`/`c3` 起容器改成六条全有 payload（sha `3f68db4dc0927742`），这一条**在新图上
   已经不存在**，只在旧图上留作记录。
3. **tiny B 格（`t0c`/`t1c`）从未飞**：它的判别价值已被 `c3` 抢走——现在飞它只能
   再确认一遍「链了 wifi 归档就得带 0012」，不再能分开任何东西。
4. **`wifi-20261114a` 是 trial 级**：manifest 无 `series` 键，身份不可复核（P-201）。

已经关闭的（不要再翻）：`__TEXT` 驻留、内核总大小阈值、pool/窗口通道、Data 卷 UUID、
`pong_wifi=0` 保护、C++ 全局构造器、`__init_entry_set`、容器所在段、ADT 窗口值、
控制台参数、固件卷 DTB。
