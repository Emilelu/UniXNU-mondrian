# WiFi 固件 blob 的 residency：11.19 MB `__TEXT,__const` 会不会撞上任何装载边界

状态：静态判定 + 四张有效 silent 判决（`z0`、`t2`、`c1`、`c2`，§10/§11）+ 一张判为测量无效的正式 C 格（`c0`，`invalid-measurement`，§11）+ 对 `docs/engineering/FIRMWARE-REBUILD.md` 三条主张的交叉核对（§12）+ **一张带真 PWF2 却进桌面的反例（`c3`）与已证实的死因（UFS SMMU lease，P-215）**（§13）。没有构建。本文回答任务 G 的一个问题：

> `__TEXT,__const` 里 11.19 MB 的 PWF2 固件，会不会让内核的 `__TEXT` 段在
> DarwinBoot 的段加载路径上触发某种边界（段大小、对齐、还是 kernelcache 的
> `__TEXT` 上限）？

结论先行（§0）：**这条路径上的每一个硬边界都被实测值绕开了，余量最小的
一项（117 MB 镜像 vs `ReadFile` 的 128 MB）也有 1.14×。** 本文不下
「所以不是体积死因」的结论——那是 C1/C2 上机判据
（[BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §7）的事——只把
「哪里可能有边界、边界在哪、离边界多远」钉到 文件:行。§10 记 E 格（`z0`）
的上机判决（silent）与它为 §7 各口子带来的格位更新。

## 0. 结论先行

| # | 候选边界 | 实测值 | 上限 | 余量 | 判定 |
|---|---|---|---|---|---|
| 0.1 | 单段大小 vs `WINDOW_SIZE`（256 MB） | `__TEXT` vmsize **12,992,512** | 268,435,456 | 20.7× | 不触发（[DarwinBoot.c:168](../../../drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c)） |
| 0.2 | 内核 VA 跨度 vs `WINDOW_SIZE - 2 MB`（254 MB） | **129,642,496**（z0/mhi5） | 253,388,800 | 1.96× | 不触发（DarwinBoot.c:196） |
| 0.3 | 内核镜像文件 vs `ReadFile` 的 `SIZE_128MB` | **117,305,344**（z0/mhi5） | 134,217,728 | 1.14× | 不触发（DarwinBoot.c:558） |
| 0.4 | `MAX_SEGMENTS` 64 | 15（vmsize≠0） | 64 | 4.3× | 不触发（DarwinBoot.c:160） |
| 0.5 | VA 段间重叠 | prelink 段在低地址，不与 `__TEXT` 相交 | 无重叠 | — | 不触发（DarwinBoot.c:190-191） |
| 0.6 | XNU 侧 `__TEXT` 大小上限常量 | grep 全树 0 命中 | 不存在 | — | 不存在（§5） |
| 0.7 | 页/16 KB 对齐 | 两内核 `__TEXT` vmaddr 同为 0xfffffff007004000 | 页对齐 | — | 不变（§2） |

真正的存量差异只有一条（§2）：固件把 `__TEXT` 从 1.64 MiB 撑到 12.39 MiB；
105 MB alive 家族的体积来自 `__DATA` 52.9 MB，`__TEXT` 与 baseline 相同。
「边界触发」假说在这条路径上没有落脚点；§7 列出仍然开着的三个口子。

口径提醒（2026-11-16 `c3` 判决后第三次更新）：`__TEXT` = 12,992,512 的死格
（mhi3/mhi4/z0/c0/c1）都带同一个 blob，`__TEXT` = 1,720,320 的活格都不带；
但 `t2`/`c2` 把 blob 移出 `__TEXT` 之后仍然 silent——「`__TEXT` 驻留跟着死亡走」
已被两张独立镜像**推翻**（§10.3 第 2 条、§11.2）。`__TEXT` 12.99 MB 的驻留嫌疑
**已被推翻**，不再是待重测项：`c1`（`c0` 只改种子 UUID 一行）段表与 `c0` 逐项相同、
仍然 0 字节（§11.1），所以那 12.99 MB 版式是**有效**的 silent 格。
「内核总大小」这一轴也已被否证两次（`bt` 同尺寸一活一死；`adsp` 129 MB 三张全 alive，
§11.3）。

**2026-11-16 01:51 追加（`c3`）：连「11.19 MB PWF2 数据进内核」这条残余轴也被推翻。**
`wifi-20261116c3` 与 `c2` 同一 117 MB 版式、同一真 PWF2 容器（逐字节相同），
只多 20,480 B 惰性锁代码，就进了桌面（`usblog-20261116-015128`，console 221,429 B、
SpringBoard 133 次，§13.1）。已证实的死因是 `patches/wifi/0004` 插进
`PongUfsTransport::hostBringUp()` 的 UFS SMMU lease 段（P-215，§13.2）：
`pong_smmu_lease_lock()` 在 `pong_rpmh_init()` 之前被调用，`smmuLeaseLock == NULL`
时返回 false ⇒ `transportFailure("Apps SMMU lease unavailable")` ⇒ UFS transport
放弃 ⇒ 没有根设备 ⇒ 控制台 worker 起来之前就死 ⇒ 0 字节。**尺寸、段表、驻留、
窗口、参数、UUID 六轴之所以全被否证，是因为它们本来就不是原因。**
现在仍开着的只剩 §7.1 的 pool 通道与 §7.4 的驱动体静态注册链，而这两条都是
在「UFS 死因」被移除之前做的观察——`c3` 之后要重新看它们还剩下多少内容（§13.3）。

待议（Lead 指示，wifi 线在本树留的四处未提交改动只折有依据的部分、其余记一行）：
wifi 原稿把 §7.4 写成「blob 位置与 pool/窗口之外唯一还活着的解释」——本页不采
「唯一」口径：§7.1 与 §7.4 是两条平行的未否证通道，谁被否证等分开它们的上机判据
（k60-wifi 树 DARWINBOOT-POOL.md §5 + 本文 §10.4）。wifi 原稿写「registerService/
metaclass 注册都还在」，但 PongWifiPlatform.cpp:718 在开关检查后就 return，注册代码
不执行，本页只记实测成立的：调用点（ArmDTPlatform.cpp:227-228）、锁序
（PongWifiPlatform.cpp:716-718 先 `pong_rpmh_init()` 后开关、:727-730 两把
IOLockAlloc）、861 个 `_pong11_*` 符号（llvm-nm 实测 mhi4 内核）、bt 非单调对
（series 228→229，manifest 实测）。

### 0.1 各判断的推翻条件

每条判断都能被一行实测推翻；写在这里是为了让下一个人知道该看什么。

- **0.1 被推翻**：出现 `__TEXT` vmsize > 256 MB 的内核仍过 `ParseKernel`；或本内核实测
  `__TEXT` vmsize ≠ 12,992,512。
- **0.2 被推翻**：实测 span > 253,388,800 的内核能过 :196；或 z0/mhi5 span ≠ 129,642,496。
- **0.3 被推翻**：内核镜像文件 > 134,217,728 字节仍被 `ReadFile` 接受；或 z0/mhi5
  镜像 ≠ 117,305,344（余量 16,912,384 B，本文余量最小的一项）。
- **0.4 被推翻**：vmsize≠0 的段数 ≥ 64 的内核被接受。
- **0.6 被推翻**：在 xnu-work 找到任何以 `__TEXT` 大小（而不是页对齐）为输入的断言或
  上限——grep 之外还要读 `pmap_bootstrap` 与 KTRR 相关代码。
- **「边界假说」整体**：不需要额外推翻——§0 已逐条证伪；`c3` 之后连「blob 在场」
  这条也不再是候选（§13）。§7.1 的 pool 通道与 §7.4 的驱动体静态注册链**都不是**
  死因：真正的死因是 UFS SMMU lease（P-215，§13.2），它既不在 pool 里也不在
  wifi 归档的静态注册链里。这两条留在 §7 只作为「当时还开着、现在被 `c3` 关掉」
  的历史记录。
- **「内核总大小」这一轴**：已被两次否证，不需要再设计对照——`bt-s4b-20261115b`
  （106,541,056 B）alive 而同尺寸的 `c` silent；`adsp-20261115c/d/e`
  （128,991,232 B）三张全 alive（§11.3）。要推翻这条「已否证」结论，只需给出
  一张 >117 MB 且带 PWF2 的 alive 镜像。
- **「11.19 MB PWF2 数据进内核」这条残余轴——已于 2026-11-16 01:51 被推翻**：
  推翻条件当初写的就是「一张带真 PWF2 的 alive 镜像」，`wifi-20261116c3` 就是那张
  （真容器 6 条、span 11,189,974，与 `c2` 逐字节相同；console 221,429 B、
  SpringBoard 133 次，§13.1）。全库 join 因此从 10 张 0 alive 变成 **11 张 1 alive**
  （§11.3 表已加「真容器」列）。所以「blob 在场」只是**观测轴**，不是因果轴——
  把观测轴写成因果轴，是本页 2026-11-15 那版最严重的措辞错误，教训写在 §13.3。

## 1. 固件怎么进的 `__const`

- 构建期：`/opt/k60/trees/k60build/wifi/native-mhiboot/PongWifiFirmware.s`（215 B）
  以 `.incbin` 把 `PongWifiFirmware.bin`（11,189,974 B）放进
  `.section __TEXT,__const`，符号 `_pong_wifi_firmware` / `_pong_wifi_firmware_end`。
- 链接期：`patches/wifi/0010` 用 `-Wl,-force_load` 把整个归档拉进内核
  （wifi 版双 hunk：`KERNEL_EXTRA_ARCHIVES` 与 `PLATFORM_ARCHIVES` 都加；
  main 版只有前者——mondrian 走 `PLATFORM_ARCHIVES`，见
  [WIFI-REBUILD-CHECKLIST.md](../../plans/WIFI-REBUILD-CHECKLIST.md) §3 硬差异 ①）。
- 运行期解析在 k60-wifi 树 `drivers/PongWifi/PongWifiPlatform.cpp:554-556`：
  `memcmp(...,"PWF2",4)` → `memcpy(&count,...+4,4)` → 逐条
  `pong_wifi_firmware+8+i*40` 按 name 匹配，`off>total||len>total-off` 拒收。

**PWF2 头与实际 payload 不一致（实测，mhi4 内核）**：头声明 `count=6`，
但只有 entry[0] 非空（`amss.bin` offset 4096 bytes 5,470,128）；entry[1..5]
全空。而 `__const` 里实际塞了 4 个真实固件（与
`/mnt/e/k60-work/firmware/qca6490-wifi/` 逐字节相同）：

| 文件 | bytes | const 内偏移 |
|---|---|---|
| amss.bin | 5,470,128 | 581,632 |
| amss20.bin | 5,296,128 | 6,053,888 |
| m3.bin | 266,684 | 11,472,896 |
| regdb.bin | 24,278 | 11,743,232 |

四文件合计 11,057,218 B；PWF2 区总长 11,189,974 B。头只描述第一个文件
意味着：运行期除了 `amss.bin`（以及 TCSR HW major==2 时改名的
`amss20.bin`，PongWifiPlatform.cpp:553）之外，`m3.bin` / `regdb.bin`
用头里的空 entry **取不到**。这对「死亡在加载前」的题目没有影响
（解析只发生在 worker 内、console gate 之后），但它独立说明这份 blob
的打包脚本与解析器失配——修打包或修解析都不影响本文的 residency 判断。

## 2. 段级对照：唯一变大的是 `__TEXT`

payload kernel = boot.img ramdisk 槽 `EFI/UniXNU/Payloads/kernel.macho`
（mtype 提取）。18 个 `LC_SEGMENT_64`，其中 vmsize≠0 的 15 个参与装载。

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

关键对照（推翻「大的内核段」这个粗提法）：**105 MB alive 家族**
（springboard-20261114c 105,480,192 B、gpu-20261114n 105,476,096 B、
brightness-4 105,500,672 B）的 `__TEXT` vmsize 同样是 1,720,320——
它们的体积全部来自 `__DATA` 52.9 MB。所以「内核大」从来不是变量，
变量精确为「`__TEXT` 只读段 +11.27 MB」。

**`t2` 已把「`__TEXT` 驻留」这一项推翻（2026-11-15）**：`t2` 把 blob 从
`__TEXT` 移到只读 `__DATA_CONST`，`__TEXT` 回到 1,802,240 B（其余同 117 MB
版式），上机仍然 silent（§10.3 第 2 条）——驻留位置不是死因。但 66 MB + blob +
`pong_wifi=0` 的 C 格至今没飞，「blob 本身是不是变量」仍开着。

**bt 线把「内核大小阈值」模型也否证了（2026-11-15）**：bt-s4b-20261115b 与
bt-s4b-20261115c 同为 106,541,056 B、同 blob、只差一个补丁——b 进桌面
（`usblog-20261115-140927`，213,434 B），c silent（`usblog-20261115-163144`，
0 B）；bt-s4c-20261115c 105,508,864 B 也进桌面（`usblog-20261115-162553`，
245,222 B）。同一尺寸一活一死：任何「内核大于 N MB 就死」的阈值模型都被否证。
到这一步，能解释 silent 的只剩 pool/窗口通道与内核初始化路径的差异（§7.1、§7.4、§10.4）。

对齐不变：`__TEXT` vmaddr 两边都是 0xfffffff007004000（内核基址 4 KB
对齐，DarwinBoot.c:194 校验 `Base & EFI_PAGE_MASK`）；
xnu-work `osfmk/arm64/arm_vm_init.c:2306` 的
`assert(segDATACONSTB == segTEXTB + segSizeTEXT)` 在 mhi4 上仍成立
（0x7004000 + 12,992,512 = 0x7c68000 = `__DATA_CONST` vmaddr）。

读法（2026-11-15 傍晚，`t2` 与 bt 对之后）：**「驻留形态已否证，不是嫌疑、
是排除」**。`t2`（blob 移进 `__DATA_CONST` 12,124,160、`__TEXT` = 1,802,240）
仍然 silent（usblog-20261115-161102，0 字节）——§10.3 第 2 条宣判完毕。bt
非单调对再补一刀：bt-s4b-20261115b 106,541,056 B、series 228
（b31855c932b4…，manifest 实测）→ alive（usblog-20261115-140927，console
213,434 B）；bt-s4b-20261115c **同尺寸** 106,541,056 B、series 229
（67baff88e1bb…）→ silent（usblog-20261115-163144，0 字节；Lead：228→229
只多 1 个补丁）；bt-s4c-20261115c 105,508,864 B、series 229 → alive
（usblog-20261115-162553，console 245,222 B）。尺寸/窗口阈值模型对 117 MB 与
65.9 MB 都不成立。§2 的段级对照保留为**记录**而非嫌疑；剩下能解释 silent 的
是两条平行通道：§7.1（pool/窗口）与 §7.4（驱动体静态注册链）。

## 3. DarwinBoot 路径上的四个硬检查，逐个对数

装载顺序（drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c）：
`ReadFile` 整块进 DXE pool（:558，上限 `SIZE_128MB`）→ `ParseKernel`（:561）
→ 读 `.adt` 得 WindowSize（:568/:575/:580）→ `AllocateWindow`（:607）
→ 段拷贝（:627-630）→ `FreePool(Image)`（:656）。

1. **单段上限**（:168）：`Segment->Size > WINDOW_SIZE` 即 256 MB。
   `__TEXT` 12.39 MB，余量 20.7×。固件再大 20 倍才够到这条线。
2. **跨度上限**（:196）：`End - Base > WINDOW_SIZE - SIZE_2MB` 即 254 MB。
   最大实测是 z0/mhi5 的 129.6 MB（mhi4 78.3 MB、105 MB 家族 117.6 MB），余量 1.96×。
   注意这条检查量的是 **vmsize 和**，与文件大小无关。
3. **镜像文件上限**（:558）：`SIZE_128MB`。最大实测是 z0/mhi5 的 117.3 MB
   （mhi4 65.98 MB），余量 16.1 MiB = 1.14×——全文最窄的一条，仍远离上限。
4. **段数**（:160）与**重叠**（:190-191）：15/64；两两重叠 0（§4 算术）。

`AllocateWindow`（:420-478）本身只看内存地图里最大的
`EfiConventionalMemory` run 能不能容纳 WindowSize——它**不读内核段**。
固件 blob 对它唯一的影响是 :619 的 `Used > WindowSize - BLOCK_SIZE`
（Used = kernel span + args/tree/ramdisk/trustcache 的 16 KB 对齐和），
对 4.5 GiB 窗口远不可及。这一步的真实失败模式是「NO WINDOW」
（内存碎片），其定量模型与实测的分叉已在
[BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §3.3 记录，本文不外推。

## 4. VA 布局：`__TEXT` 长大不碰任何人

新 kcgen 的 vmaddr 顺序见 xnu-work
`osfmk/arm64/arm_vm_init.c:165-181` 的注释
（`__PRELINK_TEXT → __PLK_DATA_CONST → __PLK_TEXT_EXEC → __TEXT → …`）。
实测两内核：

- `__PRELINK_TEXT` 恒 0xfffffff004420000、`__PLK_TEXT_EXEC` 恒
  0xfffffff004b34000——**两者都在 `__TEXT` 之下的低地址**（0x…4xxxxxxx < 0x…7004000）。
- `__TEXT` 从 0x…7004000 起向高地址长：baseline 末端 0x…71a8000，
  wifi 末端 0x…7c68000。向高地址方向的邻居是 `__DATA_CONST`（紧邻断言 §2），
  不是 prelink 段。
- 算术验证：0xfffffff007004000 + 12,992,512 = 0xfffffff007c68000（=
  `__DATA_CONST` vmaddr）；与低地址 prelink 段永无交叠，:190-191 的
  两两重叠检查通过。

## 5. XNU 侧没有 `__TEXT` 大小上限常量

`grep -rn 'KERNEL_TEXT_MAX\|kPrelinkTextMax\|MAX_KERNEL_TEXT'` 在
xnu-work 的 osfmk/pexpert/libsa/bsd 全树 **0 命中**。`arm_vm_init.c` 对
`__TEXT` 只做三件事：取段基（:2087 `getsegdatafromheader("__TEXT",
&segSizeTEXT)`）、设只读页表（:1415 `arm_vm_page_granular_RNX`，带
`ARM64_GRANULE_ALLOW_BLOCK | ARM64_GRANULE_ALLOW_HINT`）、断言
`__DATA_CONST` 紧邻（:2306）。没有大小断言；KTRR 锁的是
`__PRELINK_TEXT` 到 `__LAST`（注释 :165-181），与固件落在 `__TEXT`
还是别处无关。

## 6. 判别矩阵：下一张镜像能推翻哪一条

本文的回答是「这条路径上没有边界」，但「没有边界」不等于「体积无关」——§7.1 的
pool 通道仍然存在。要把两者分开靠五格对照；这里只列格子与每格能推翻什么，不排期。
E 格、F 格（`t2`）已飞并各得一条有效判决（silent，§10）。C 格（正式镜像
`wifi-20261116c0`）也飞了，但判决是 `invalid-measurement`（§11）：镜像被
`mondrian_wifi_defconfig` 的种子 Data UUID 在根挂载阶段打死，没有测到版式、
驻留或 pool。其余格子仍未飞。

| 格子 | 内核 | `__TEXT` | blob | `pong_wifi` | 上机记录 | 该格能推翻什么 |
|---|---|---|---|---|---|---|
| A | 54.2 MB stock（thermal / bt / …） | 1.64 MiB | 无 | 0 | 已飞，**alive** | 基线 |
| B | 54.8 MB tiny（`t0c` / `t1c`，kernel 54,804,480，`__TEXT,__const` 593,943） | 1.82 MiB | 4×23 B 占位（PWF2 count=4，`amss.bin`/`amss20.bin`/`m3.bin`/`regdb.bin` 各 23 B） | 0 / 1 | **从未飞** | `t1c` alive ⇒ 驱动存在 + `pong_wifi=1` 本身无害，死因需要真 blob 或与之同步变化的东西 |
| C | 66 MB（正式重出 `wifi-20261116c0`；trial `a2` 同形；`c1` = 只改该 UUID 一行） | 12.39 MiB | 11.19 MB | 0 | **两飞：`c0` 测量无效（`usblog-20261115-213221`）、`c1` silent（`usblog-20261115-231707`）** | `c0` 的 boot.img 唯一带种子 Data UUID（§8 扫描），死在根挂载；`c1` 修好该行后段表与 `c0` 逐项相同、仍然 0 字节 ⇒「种子 UUID ⇒ 零字节」这条单变量假设不成立（§11.1），本格仍未测到版式 |
| D | 117 MB（`mhi5`） | 12.39 MiB | 11.19 MB | 1 | **从未飞** | 主要探 `ReadFile` 的 128 MB 上限与 span，与 blob 边界问题无关 |
| E | 117 MB（`z0`，正式镜像，与 `mhi5` 只差 `pong_wifi`） | 12.39 MiB | 11.19 MB | 0 | **已飞，silent（0 B，`usblog-20261115-135859`；§10）** | 驱动 vs blob：E 静默而 105 MB 家族 alive ⇒ blob 被钉住、驱动被洗清；E alive ⇒ 驱动有罪 |
| F | 117 MB（`t2`，blob 移入只读 `__DATA_CONST`，`__TEXT` 1.80 MiB；`c2` 同版式复现） | 1.80 MiB | 11.19 MB（在 `__DATA_CONST`） | 0 | **两飞都 silent（`t2` `usblog-20261115-161102`、`c2` `usblog-20261116-000136`；§10.3、§11.2）** | F 静默 ⇒ `__TEXT` 驻留被推翻，死因不在驻留位置；F alive ⇒ 驻留位置被钉住 |

读法：C 是「体积」那一问的判决格（66 MB + blob + `pong_wifi=0`），但
`wifi-20261116c0` 这一飞**没有执行这个判决**：它由 `mondrian_wifi_defconfig`
构建，该文件在 `k60-wifi` @ `fff0fb19` 的 :46 指名了种子 Data UUID
`6DCCF70A-…`，内核在根挂载阶段等这个卷超时后自 panic（P-152 机制），console 在
根挂载之后才起来，所以读数是 0 字节（§11）。`c0` 的 manifest 也记着同一个
构建树（`repo.head = fff0fb19`）。重测条件：`c1`——只把该
`CONFIG_XNU_OWNER_DATA_VOLUME_UUID` 一行改成设备卷
`1BCD69FF-24A5-48B1-94B6-8FE592B2F597`，其余不动。`a2` 仍是 trial 级（P-201）；
`z0` 是 117 MB 的 E 格，不顶替 C。原先写在这段里的「C 静默 ⇒ 体积方向仍活」
已按 `invalid-measurement` 撤回。

B 是 C 的对照格：B 出声而 C 静默 ⇒ 11.19 MB blob 被钉成唯一变量；B 也静默 ⇒
死因不需要 blob。E 是「驱动 vs blob」的对照格（与 `mhi5` 只差 46 字节 / 8 处构建
时间戳，见 k60-wifi `docs/research/wifi/BOOT-DEATH-SUSPECT.md` §3b）：**已飞，
verdict = silent**（§10）。按这条读法，驱动这一支被洗清（§10.2：`pong_wifi=0` 时
worker 根本没启动），blob / 117 MB 版式这一支被钉住但没被证明——它的推翻条件写在
§10.3。F 格（`t2`）已经飞完：**silent**，`__TEXT` 驻留被推翻（§10.3 第 2 条）。

**2026-11-16 01:51 后这张矩阵的结局（`c3`，§13）**：G 格（`c3`）是 F 格加一行惰性锁
代码，带**逐字节相同**的真 PWF2 容器、同 117 MB 版式、同窗口、同 `pong_wifi=0`，
**进了桌面**。所以本矩阵里所有「blob 在场 ⇒ 死」的读法全部作废：A/B/C/D/E/F 六格
否证的是六条**观测轴**，而真正的因果轴是 UFS SMMU lease（P-215，§13.2）——它不在
任何一格的自变量里。矩阵保留原样，作为「观测轴怎么被逐条打掉」的记录。

## 7. 当时仍然开着的口子（本节保留静态判定时的原样）

`z0` 与 `t2` 上机后各口子的格位变化见 §10.4；`c3` 之后两条口子都关闭（§13.3）。
本节不删，因为「当时为什么觉得它们还开着」本身是记录的一部分。

1. **DXE pool 碎片化**（:558 → :607 的顺序）：65.9 MB（C 格）或 117.3 MB（E 格）
   整块 `AllocatePool` 之后才申请 4.5–4.75 GiB 连续窗口。blob 使 pool 占用多
   11.27 MB，可能改变 `AllocateWindow` 看到的最大 run——E 格把这笔 pool 占用翻倍
   （117 MB），它比 C 格更容易先撞上 pool 通道；读 E 的结果时要把这一点算进去。
   这条只能靠上机的「NO WINDOW」行或 C1/C2 判据分辨，静态无解。
2. **105 MB 家族的成功不能反证 65.9 MB 必成**：105 MB 在 `__DATA`
   （可写、按需填零），65.9 MB 的超额在 `__TEXT`（整段只读映射，
   页表路径 :1415 不同）。段属性不同，静态不能互相担保。
3. **PWF2 头失配**（§1）说明 blob 打包链有第二个作者；在头与 payload
   一致之前，任何「固件加载成功」的运行期判断都要先核对一致性。
4. **驱动体/归档人格的静态注册链（Dart/中断/时钟路径）**：`pong_wifi=0` 没有
   把 wifi 归档砍到零——k60-wifi 树实测，ArmDTPlatform.cpp:227-228 在
   `#if XNU_PONG_WIFI` 下无条件调 `pong_wifi_start_optional()`；该函数
   （PongWifiPlatform.cpp:716-718）先 `pong_rpmh_init()`（:727-730，两把
   IOLockAlloc：powerLock/smmuLeaseLock）再 `PE_parse_boot_argn("pong_wifi")`，
   开关为 0 只挡住其后的注册/发布；mhi4 内核 llvm-nm 实测 861 个 `_pong11_*`
   符号、`_pong_wifi_firmware`/`_end` 容器映射（无论 `__TEXT` 还是
   `__DATA_CONST`）都在。这条路径在 z0/t2 上都没有被排除——它与 §7.1 是两条
   平行的未否证通道（口径见 §0 待议）；判决需要一张「不链 wifi 归档、同
   117 MB 版式」的对照，或 C1/C2（BOOT-DEATH-BISECT.md §7）加一次屏幕判读。

## 8. 证据清单

| 事实 | 证据 |
|---|---|
| 段表逐段扫描（含 105 MB 家族） | `E:/k60-work/scratch/refmine/probe-segs.py`、`probe-seg.py`、`probe-allwifi.py`（46 张 boot.img 汇总） |
| 窗口值逐镜像 | `probe-window3.py`：ADT 属性 `darwinboot-memory-size` 解码——thermal/springboard/gpu/base/touch=0x130000000（4.75 GiB）alive；brightness-4=0x120000000（4.5 GiB）alive；wifi-20261114a/mhi3=0x130000000 死；mhi4/mhi5/z0/t2/bt-s4b-20261115c=0x120000000（z0 与 t2 已判 silent）；a2/t1/t1c=0x130000000 未飞 |
| `z0` 判决 | `scripts/judge-z0.sh usblog-20261115-135859 --expect-arg pong_wifi=0` → `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]`；MSYS 与 WSL 两侧 `RC=2`；参数自检 manifest `["pong_wifi=0"]` + 镜像字节 `pong_wifi=0 x1` |
| `t2` 判决 | `scripts/judge-z0.sh usblog-20261115-161102 --expect-arg pong_wifi=0` → `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]`；MSYS 与 WSL 两侧 `RC=2`；参数自检 manifest `["pong_wifi=0"]` + 镜像字节 `pong_wifi=0 x1` |
| 六张 silent 图 + bt 三图逐段实测 | `probe-silent6.py`（E:/k60-work/scratch/refmine/，复用 probe-family 段解析与 probe-window3 窗口解码）：§9 表的 kernel/段/窗口数字全部出自它；`wifi-20261116c0` 的段表由 `E:/k60-work/scratch/table4.py` 单测（§11） |
| alive 归属（join image sha → evidence） | `probe-join2.py`：thermal adc796b6→usblog-20261115-003922（232,670 B）；springboard 3ada9562→003207；gpu ba783b74→212253；brightness e41eb797→013520（185,701 B）；a2/mhi5/z0/t1/t1c 全库零命中（从未上机） |
| `__const` 内固件逐字节匹配 | `probe-const.py` / `probe-const2.py`：四文件与 `/mnt/e/k60-work/firmware/qca6490-wifi/` 相同；非零字节合计 7,030,971 |
| DarwinBoot 检查 | drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c:160,168,190-191,194-196,558,607,619 |
| XNU 侧无上限 | xnu-work（`.cache/xnu-work`）grep `KERNEL_TEXT_MAX\|kPrelinkTextMax\|MAX_KERNEL_TEXT` = 0 命中 |
| VA 布局注释 | xnu-work `osfmk/arm64/arm_vm_init.c:165-181`（顺序）、:2087（取段）、:1415（RNX）、:2306（紧邻断言） |
| 解析器 | k60-wifi 树 drivers/PongWifi/PongWifiPlatform.cpp:553-556 |
| §7.4 调用点与锁序 | k60-wifi 树 drivers/ArmDTPlatform/ArmDTPlatform.cpp:227-228、drivers/PongWifi/PongWifiPlatform.cpp:716-718（先 `pong_rpmh_init()` 后开关）与 :727-730（两把 IOLockAlloc） |
| §7.4 符号计数 | WSL `llvm-nm-18` 扫 mhi4 payload kernel：52,274 个符号，`_pong11_*` = 861，`_pong_wifi_firmware`/`_pong_wifi_firmware_end` 各 1 |
| bt 非单调对 series | `E:/k60-work/artifacts/bt-s4b-20261115b/build-manifest.json`（series 228 b31855c932b4…）与 `bt-s4b-20261115c/`（series 229 67baff88e1bb…）；两图 boot.img 窗口同 0x120000000 |
| PWF2 失配 | mhi4 kernel 文件偏移 589,824 处头（count=6，entry[0] amss.bin，1..5 全空）vs 四文件实测偏移（§1 表） |
| 判定器落位 | `scripts/judge-wifi-boot.py`、`scripts/judge-z0.sh`、`scripts/check-arg.py` 与两份自测已在 main（合并 `4f56970`，登记 `3e6f110`，tag `snap-r198`）；本文引用写 main 上的路径，不写分支或 scratch 副本 |
| `c0` 判决（`invalid-measurement`） | Lead 2026-11-15 裁决 + 实测：`E:/k60-work/artifacts/wifi-20261116c0/boot.img` 里 `6DCCF70A-…` ×1、`1BCD69FF-…` ×0；构建树 `k60-wifi` @ `fff0fb19`，该树 `configs/mondrian_wifi_defconfig:46` 指名种子 UUID；采集 `usblog-20261115-213221` 0 字节 / `port-not-observed` / `returnedToFastboot`。按 P-152（`docs/engineering/PITFALLS.md:3811-3819`）自 panic，未测到版式/驻留/pool |
| 构建配置扫描（53 张 wifi/bt boot.img） | 全镜像字节计数 `6DCCF70A-…` / `1BCD69FF-…`（脚本 `E:/k60-work/scratch/refmine/uuid-scan.py`）：56 个 wifi/bt 产物里 3 个没有 boot.img；扫描到的 53 张中**只有 `c0` 带种子 UUID**（seed=1/dev=0），其余 52 张（含 `wifi-20261114a`、mhi3、mhi4、z0、t2、bt-s4b-b/c）都是 seed=0/dev=1 ⇒ 该缺陷只覆盖 `c0`，不能把前五张 wifi silent 一并判无效 |
| P-209 门禁形状（已落 main `011669a`，tag `snap-r201`） | `scripts/check-defconfig-uuid.py`：defconfig 指名非本机 Data UUID 即硬失败；种子 UUID 必须显式标 `# SEED-UUID: intentional` |
| `c1` 判决（有效 silent） | 产物 `E:/k60-work/artifacts/wifi-20261116c1`（`built_at` 2026-11-15T23:10:57、`repo.head=e33e64557fa7`、series 224、`kernel_args=["pong_wifi=0"]`）；boot.img `76171061046f…` 内 `6DCCF70A-…` ×0 / `1BCD69FF-…` ×1；段表与 `c0` 逐项相同；采集 `E:/k60-work/evidence/usblog-20261115-231707` 0 字节 / `port-not-observed` / `returnedToFastboot=true`；`scripts/judge-z0.sh` → `silent [exit 2]`（§11.1） |
| `c2` 判决（有效 silent，blob 在 `__DATA_CONST`） | 产物 `E:/k60-work/artifacts/wifi-20261116c2`（`built_at` 2026-11-15T23:40:04、`repo.head=9fd2018a80b3`、series 224）；boot.img `dc7e4186f737…`；段表/节表与 `t2` 逐项相同；PWF2 落在 `__DATA_CONST,__const` size 11,919,062 @ 1,806,336；采集 `E:/k60-work/evidence/usblog-20261116-000136` 0 字节（§11.2） |
| 129 MB alive 对照 | `adsp-20261115c/d/e`：kernel 128,991,232 / `__TEXT` 1,720,320 / `__DATA` 76,414,976 / `__DATA_CONST` 917,504 / span 141,111,296 / 窗口 0x120000000 / 无 PWF2；采集 `usblog-20261115-213413`（214,232 B）、`-220912`（221,484 B）、`-223916`（220,234 B），SpringBoard 128/132/120（§11.3） |
| 全库 blob×alive join（`c3` 后修订） | `E:/k60-work/scratch/refmine/scan-blob3.py`（319 个产物目录，按 `image_sha256` 对 `E:/k60-work/evidence/*/boot.json`，BOM 用 `utf-8-sig`）：带真 PWF2 已飞 **11 张 → 1 alive（`c3`）/ 10 silent**；不带 PWF2 已飞 47 张 → 38 alive / 8 silent（§11.3） |
| `c3` 判决（带真 PWF2 且 alive） | 产物 `E:/k60-work/artifacts/wifi-20261116c3`（`built_at` 2026-11-16T01:34:21、`repo.head=3207bd3c019c`、series 226 `d83fb1890e93`、`kernel_args=["pong_wifi=0"]`）；boot.img `5a19e1103f07…`（payload kernel 117,325,824 B，fd `cf4485712c29`，wifi_archive 见 manifest）；PWF2 容器与 `c2` **逐字节相同**（sha `3f68db4dc0927742`、span 11,189,974、6 条）；采集 `E:/k60-work/evidence/usblog-20261116-015128` console 221,429 B / 3,204 行 / SpringBoard 133 / `K60DATA` 12 / `Early boot complete` 1（§13.1） |
| 死因（P-215，UFS SMMU lease） | `patches/wifi/0004` 在 `drivers/NativeUfs/PongUfsTransport.cpp` 的 `hostBringUp()` 里插 lease 段；`pong_smmu_lease_lock()` 原本只在 `pong_rpmh_init()` 里 `IOLockAlloc`，而后者唯一调用点在 `pong_wifi_start_optional()`，晚于 UFS 启动；`patches/wifi/0012-drivers-PongWifi-lease-lock-lazy-init.patch` 改成首次使用时自建锁（§13.2） |
| FIRMWARE-REBUILD 三条核对 | §12：`audio-probe-j/run1`、`usblog-20261115-012317`（SpringBoard ×129 各一）；`fd-hist3.py`（107 次飞行的内嵌 FD 判代）；`fd-dates.py`（130 个归档 .fd 的 2 个 distinct 三元组）；`/e/hackios/UniXNU/scripts/unixnu/firmware.py:69` |

口径备注：本文所有「alive / 0 字节 / 未飞」都来自 evidence 采集目录与
artifact `boot.json` 按 image sha256 的 join（`probe-join2.py`），与
[BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §3 同源。

ADT 口径（2026-11-15 起）：main `3ea8d71` 把 identity seed 接进板级契约——
`board.toml [payload."adt"]` 增 `unique_chip_id = "required"`，`build-strict.sh`
把 `UNIXNU_UNIQUE_CHIP_ID` 转发给 build payload，新构建的 ADT 会带
`/chosen/unique-chip-id`。上表窗口值全部来自 3ea8d71 **之前**的镜像（它们的 ADT
sha 只在那批镜像内可比）；`t2` 及以后的窗口必须逐镜像重解，不能沿用上表，也不能
拿旧 ADT sha 当新镜像的属性清单。

## 9. 实测对照表（本节的数字都来自 `mtype` 解出的 payload kernel）

`__TEXT` / `__DATA` 是段 vmsize，span 是 `Kernel.End - Kernel.Base`；`PWF2` 与
`Pong MHI` 是内核镜像里出现的字符串次数（用来判断 blob 与 ath11k MHI 日志是否
被链接进来），`pong_wifi` 取自同目录 `build-manifest.json` 的 `kernel_args_requested`。

| 镜像 | kernel B | `__TEXT` | `__DATA` | span | PWF2 | Pong MHI | `pong_wifi` | 上机 |
|---|---|---|---|---|---|---|---|---|
| thermal-20261114f | 54,173,696 | 1,720,320 | 1,638,400 | 66,285,568 | 0 | 0 | 0 | **alive**（232,670 B） |
| springboard-20261114c | 105,480,192 | 1,720,320 | 52,920,320 | 117,600,256 | 0 | 0 | 0 | **alive**（220,944 B） |
| gpu-20261114n | 105,476,096 | 1,720,320 | 52,920,320 | 117,583,872 | 0 | 0 | 0 | **alive**（262,275 B） |
| brightness-4 | 105,500,672 | 1,720,320 | 52,920,320 | 117,616,640 | 0 | 0 | 0 | **alive**（185,701 B，4.5 GiB 窗口） |
| wifi-20261116a2 | 65,978,368 | 12,992,512 | 1,867,776 | 78,327,808 | 2 | **0** | 0 | 从未飞（trial 级） |
| wifi-20261116mhi4 | 65,978,368 | 12,992,512 | 1,867,776 | 78,327,808 | 2 | 11 | 1 | silent（0 B） |
| wifi-20261116mhi3 | 65,978,368 | 12,992,512 | 1,867,776 | 78,327,808 | 2 | 11 | 1 | silent（0 B） |
| wifi-20261115z0 | 117,305,344 | 12,992,512 | 53,149,696 | 129,642,496 | 2 | 11 | **0** | silent（0 B，`usblog-20261115-135859`；§10） |
| wifi-20261116mhi5 | 117,305,344 | 12,992,512 | 53,149,696 | 129,642,496 | 2 | 11 | 1 | 从未飞 |
| wifi-20261114a | 65,863,680 | 12,877,824 | 1,867,776 | 78,213,120 | 2 | 0 | 1 | silent（0 B，`usblog-20261114-wifi-b`；trial 无 series） |
| wifi-20261116t2 | 117,305,344 | **1,802,240** | 53,149,696 | 129,642,496 | 2 | 11 | 0 | silent（0 B，`usblog-20261115-161102`；blob 容器在 `__DATA_CONST` 12,124,160） |
| bt-s4b-20261115b | 106,541,056 | 1,720,320 | 52,920,320 | — | 0 | 0 | —（kargs `k60bt=1`） | **alive**（213,434 B，`usblog-20261115-140927`） |
| bt-s4b-20261115c | 106,541,056 | 1,720,320 | 52,920,320 | 118,648,832 | 0 | 0 | —（kargs `k60bt=1`） | silent（0 B，`usblog-20261115-163144`，与 b 同尺寸同 blob 只多一个补丁） |
| bt-s4c-20261115c | 105,508,864 | 1,720,320 | 52,920,320 | — | 0 | 0 | —（kargs `k60bt=1`） | **alive**（245,222 B，`usblog-20261115-162553`） |
| wifi-20261116c0 | 66,002,944 | 12,992,512 | 1,867,776 | 78,344,192 | 2 | 11 | 0 | 测量无效（0 B，`usblog-20261115-213221`；种子 UUID，§11） |
| wifi-20261116c1 | 66,002,944 | 12,992,512 | 1,867,776 | 78,344,192 | 2 | 11 | 0 | silent（0 B，`usblog-20261115-231707`；§11.1） |
| wifi-20261116c2 | 117,305,344 | **1,802,240** | 53,149,696 | 129,642,496 | 2 | 11 | 0 | silent（0 B，`usblog-20261116-000136`；blob 在 `__DATA_CONST` 12,124,160，§11.2） |
| wifi-20261116c3 | 117,325,824 | **1,802,240** | 53,149,696 | **12,124,160** | 2 | 11 | 0 | **alive**（221,429 B，`usblog-20261116-015128`；同 `c2` 版式 + 惰性锁 20,480 B，§13.1） |
| adsp-20261115c | 128,991,232 | 1,720,320 | 76,414,976 | 141,111,296 | 0 | 0 | — | **alive**（214,232 B，`usblog-20261115-213413`） |
| adsp-20261115d | 128,991,232 | 1,720,320 | 76,414,976 | 141,111,296 | 0 | 0 | — | **alive**（221,484 B，`usblog-20261115-220912`） |
| adsp-20261115e | 128,991,232 | 1,720,320 | 76,414,976 | 141,111,296 | 0 | 0 | — | **alive**（220,234 B，`usblog-20261115-223916`） |

八条从这张表直接读出来的结论（都不是「结论」，是可推翻的事实）：

1. **`z0` 不是 66 MB 的 C 格**：它 117,305,344 B，`__DATA` 53,149,696 与 105 MB
   alive 家族同量级，是 `mhi5` 的孪生（只差 `pong_wifi`）。66 MB 那一格是
   `c0`/`c1`（66,002,944 B，§11/§11.1）：`c0` 测量无效、`c1` 有效 silent。
   `z0` 已飞、silent（§10），所以这一格回答的是「驱动 vs blob」，不是「体积」。
2. **`a2` 与 `mhi4` 的唯一差别是 `pong_wifi`**：两者 kernel B、`__TEXT`、`__DATA`、
   span 完全一致，`Pong MHI` 串数为 0 与 11（a2 没链 ath11k MHI 日志，mhi4 链了）。
   但 `a2` 是 P-201 的 trial 级——它的 manifest 没有 `series` 键，身份不可复核。
3. **105 MB alive 家族的 `__TEXT` 与 54 MB 基线完全相同（1,720,320 B）**，体积全部
   来自 `__DATA`；wifi 家族的 `__TEXT` 是 12,992,512 B。所以「内核大」与「`__TEXT`
   大」是两件互不蕴含的事，前者已被 alive 样本证明无害，后者才是 wifi 家族独有的。
4. **`t2` 的 `__TEXT` 只有 1,802,240 B 却仍 silent**（blob 容器移入
   `__DATA_CONST` 12,124,160 B）：`__TEXT` 驻留被上机数据推翻（§10.3 第 2 条）。
5. **bt 同尺寸一活一死**：bt-s4b-20261115b 与 bt-s4b-20261115c 同为
   106,541,056 B、同 blob、只差一个补丁，b alive、c silent——任何「内核大于
   N MB 就死」的阈值模型被否证（§2 末）。
6. **129 MB 也 alive**：`adsp-20261115c/d/e` 三张 kernel 128,991,232 B
   （`__DATA` 76,414,976、span 141,111,296，都比 117 MB 家族大），同一 4.5 GiB
   窗口、无 PWF2，全部进桌面。阈值模型因此被第二次否证，且这次把 117 MB 也包住
   （§11.3）。
7. **带 PWF2 的已飞镜像里已经有一张 alive（2026-11-16 改）**：`wifi-20261116c3`
   带与 `c2` **逐字节相同**的真 PWF2 容器（span 11,189,974、6 条），console
   221,429 B、SpringBoard 133 次（§13.1）。全库 join 因此是 11 张 / 1 alive。
   2026-11-15 那版写的「没有一张 alive」当时是对的，但它是**观测轴**不是因果轴：
   `c3` 与 `c2` 的唯一差别是 20,480 B 的惰性锁代码（§13.2）。
8. **`c3` 与 `c2` 的差只有一处，而那一处就是死因**：两张同 117 MB 版式、同段表、
   同 PWF2 容器，`c3` 多出的 20,480 B 全在 `patches/wifi/0012`——把
   `pong_smmu_lease_lock()` 的锁分配从「`pong_rpmh_init()` 里建」改成「首次使用时
   建」。所以六条被否证的轴（尺寸/段表/驻留/窗口/参数/UUID）不是「被绕开」，
   而是**从来不在因果链上**；因果链在 UFS transport 上（§13.2）。

这张表的生成方式：`mtype -i <boot.img 的 ramdisk 卷> ::EFI/UniXNU/Payloads/kernel.macho`
再按 `LC_SEGMENT_64` 解段；脚本 `E:/k60-work/scratch/refmine/probe-family.py`。
## 10. 上机判决：`z0` 与 `t2` 都是 silent（2026-11-15）

§6 的 E 格（`z0`）与 F 格（`t2`）都已经飞了，都 silent。本节记两次判决、
为什么读得动、三条推翻条件的走向，以及两次飞行给 §7 三个口子带来的格位变化。
措辞守 Lead 的裁决：`__TEXT` 驻留在 `t2` 之前是首要嫌疑，`t2` 之后是**已推翻项**。
（2026-11-16 补：`c0` 判测量无效后「12.99 MB 驻留」一度只剩待重测；`c1`/`c2`
两飞之后这一项也已推翻，见 §11.1/§11.2。）

### 10.1 两飞两判

| 项 | 值 |
|---|---|
| 采集目录 | `E:/k60-work/evidence/usblog-20261115-135859` |
| boot.img sha256 | `c2e069f0088a0728e24dbc89338edee2ba9d5f453265d63d42ccb64bc3303728`（容器 201,887,744 B；payload kernel 117,305,344 B） |
| 时间 | 13:59:01.478 → 14:00:27.593，86.114 s；`capture-events` 13:59:03.230 ready → 14:00:27.272 finished `port-not-observed` |
| console.log | **0 字节**；`portSeen=false`、`portOpened=false`、`stopReason=fastboot-return` |
| 判定 | `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]` |
| 参数自检 | manifest `kernel_args_requested = ["pong_wifi=0"]`；镜像字节 `pong_wifi=0 x1`（两道都过，不是忘传参数的 trial） |

死亡签名与 mhi3（`usblog-20261115-002804`，86.746 s）/ mhi4
（`usblog-20261115-002243`，86.758 s）逐字段相同：同样 `port-not-observed`、
同样 `returnedToFastboot`、同样 `fastboot-return`。判定器在 MSYS 与 WSL 两侧
都给 `silent` / `RC=2`（`scripts/judge-z0.sh` 的 helper 路径已改成脚本自身相对 + 候选根
探测，找不到就 exit 4 拒判，绝不读成 silent）。

#### `t2`（2026-11-15 16:11 飞）

| 项 | 值 |
|---|---|
| 采集目录 | `E:/k60-work/evidence/usblog-20261115-161102` |
| boot.img sha256 | `de9bf9db…`（payload kernel `d7fde1cd…`，117,305,344 B；series 224 `34cf51e4…`） |
| 段形态 | `__TEXT` **1,802,240**、`__DATA_CONST` **12,124,160**（blob 容器整段移入只读 `__DATA_CONST`）、`__DATA` 53,149,696——与 `z0` 只差 blob 的段归属 |
| console.log | **0 字节**；`port-not-observed`、`returnedToFastboot=true`、`bootExitCode=0` |
| 判定 | `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]` |
| 参数自检 | manifest `kernel_args_requested = ["pong_wifi=0"]`；镜像字节 `pong_wifi=0 x1` |

与 `z0` 同一个死亡签名（`port-not-observed` + `fastboot-return` + 0 字节），
判定器在 MSYS 与 WSL 两侧都 `silent` / `RC=2`。

### 10.2 这个空读数读得动

`pong_wifi=0` 时驱动**主动返回**：`patches/wifi/0001-drivers-PongWifi-vendor-
zizhan-087416a.patch:1939-1946` 的 `pong_wifi_start_optional()` 先
`PE_parse_boot_argn("pong_wifi", &enabled, sizeof enabled)`，`enabled != 1` 就
`return`，worker（PWF2 解析 / MHI / RSC 投票）从未 `kernel_thread_start`。所以：

- marker 全 0（`PongWifi:` 0、`held back by k60_wifi_stage` 0、`Pong MHI` 0）是
  「驱动没执行」的**预期读数**，不是「驱动没被链进来」——§1 已证 blob 与解析器
  都在镜像里。
- 这一格与 `mhi5` 只差 `pong_wifi` 一个开关（同 series、同 blob、同 117 MB 版式，
  差 46 字节 / 8 处构建时间戳）；与 mhi4 差版式（117 vs 66 MB）与开关两项。
- 因此这一格能干净地回答「驱动运行路径是不是死因」：**不是**。它回答不了的事
  写在 §10.3。

### 10.3 三条推翻条件

1. **推翻「117 MB 版式 + blob 致死」**：任何 117 MB / `__TEXT` = 12,992,512 /
   `pong_wifi=0` 的镜像进用户态（哪怕只到 `SpringBoard` 一行）⇒ 这一读法作废，
   差异必须落到窗口、pool 或 args 上。
2. **推翻「`__TEXT` 驻留是死因」——已推翻（2026-11-15）**：`t2`（blob 移出
   `__TEXT` 到只读 `__DATA_CONST`，`__TEXT` 回到 1,802,240 B，其余同 117 MB
   版式）飞完 verdict = silent（`usblog-20261115-161102`）。驻留形态已被两种
   形态否证：105 MB alive 家族把体积放在可写 `__DATA` 仍进桌面；`t2` 把 blob
   放在只读 `__DATA_CONST` 仍 silent。死因回到驱动之外的差异。
3. **「blob 是变量」这一条已被 `c3` 推翻**（2026-11-16 01:51 改写；此前一版写的是
   「没有被推翻，反而被坐实」）：C 格（66 MB + blob + `pong_wifi=0`）两次飞行都是
   0 字节（`c0` 测量无效 §11、`c1` 有效 silent §11.1），`c2` 把 blob 搬进
   `__DATA_CONST` 同样 0 字节（§11.2）——这些都还成立。但 `wifi-20261116c3`
   带**逐字节相同**的真 PWF2 容器进了桌面（§13.1），所以「blob 在场」不再分生死。
   正确写法（P-215 的教训）：那 10 张 0 alive 是**观测轴**的证据，不是因果轴的
   证据；因果轴要一次单变量干预才成立，而那次干预就是 `patches/wifi/0012`。

三条都不涉及静态量：它们都是「再飞一张」就能证伪的句子，不需要新代码。

### 10.4 §7 三个口子的格位更新

1. **DXE pool 碎片化（§7.1）——`c3` 之后已关闭**（下面这段是历史记录；`c3` 用
   同一 117 MB 版式、同一 pool 占用进了桌面，说明 pool 不是通道）。`z0` 是 117.3 MB 整块进
   pool，比 C 格翻倍，窗口 4.5 GiB（余量约 223 MiB），仍然 silent；而 mhi4
   （65.9 MB、同一窗口）也 silent。两格之间差约 51 MB pool 占用而结果相同，所以
   pool 占用本身没有把 4.5 GiB 窗口推过线。`t2`/`c2` 把 blob 移出 `__TEXT` 后仍
   silent，驻留形态被否证——到这一步，这条与 §7.4 的驱动体静态链一样，还没有被
   上机数据否证。**但**：0 字节的 console 里没有 `NO WINDOW` 行可读，
   `AllocateWindow` 到底走到哪一步仍是静态空白。
   **2026-11-16 追加的反向压力**：`adsp-20261115c/d/e` 三张 **128,991,232 B** 内核
   （`__DATA` 76,414,976、span 141,111,296，都比 117 MB 家族大）在同一 4.5 GiB
   窗口下全部进桌面（§11.3）。若 pool 占用是通道，这三张应该先撞线；它们没有。
   所以这条通道要么被「PWF2 在场」触发（而不是被总量触发），要么与 pool 无关——
   这条区别目前没有镜像能分开。
2. **105 MB 家族不能反证（§7.2）——对照仍成立，但不再指向驻留**。`z0` 的
   `__DATA` 53,149,696 与 brightness-4 的 52,920,320 同量级，差在 `__TEXT` 的
   11.27 MB 与 args；同一 4.5 GiB 窗口下 105 MB 家族 alive、117 MB 的 `z0` 死。
   `t2`/`c2` 把 `__TEXT` 收回之后仍死，两格合起来把「`__TEXT` 体积」与「驻留
   位置」都洗掉。**105 MB 这一档现在也解释不了死**：`bt-s4b-20261115b`
   （106.5 MB）alive 而 `bt-s4b-20261115c`（同尺寸）silent，`adsp` 三张 129 MB
   全 alive——「体积」不再是可用的自变量。剩余差别只能落在「PWF2 数据是否在内核里」
   与内核初始化路径上（§11.3）。
3. **PWF2 头失配（§7.3）——不受影响**。`z0` 与 `t2` 都是 `pong_wifi=0`，
   解析器不运行；这一条仍然是任何 `pong_wifi=1` 飞行的待办。
4. **驱动体/归档人格静态注册链（§7.4）——与 pool 平行的未否证通道**。§7.4 的
   路径（`pong_wifi=0` 下 `pong_wifi_start_optional()` 仍被调用、`pong_rpmh_init()`
   先于开关检查执行、861 个 `_pong11_*` 符号与 PWF2 容器映射）在 `z0`/`t2` 上都
   没有被排除。bt 非单调对（b 与 c 同 106,541,056 B、同 4.5 GiB 窗口，series
   228→229）一活一死：两图尺寸与窗口相同，静态 pool 算术给出相同的占用预测，
   解释不了结果的翻转——死亡随「补丁 × flavor」非单调。要一次上机分开这条通道
   与 pool 通道，判据在 k60-wifi 树 `docs/research/wifi/DARWINBOOT-POOL.md` §5
   （`NO WINDOW` 行与 hand-off 大字块互斥）与
   [BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §7 的 C1/C2。

## 11. C 格（`c0`）判决：`invalid-measurement`，不是版式判决（2026-11-15 21:32）

**结论行：这次飞行没有测到 C 格要测的东西。** `c0` 由 `mondrian_wifi_defconfig`
构建，该 defconfig 指名了种子 Data UUID `6DCCF70A-…`，内核在根挂载阶段自
panic；`__TEXT`/PWF2 布局、驻留、pool 三条假设在本格上**既未被证实也未被否证**。
重测条件：`c1`（只改该 UUID 一行）——**已飞，仍然 0 字节**，见 §11.1：
「种子 UUID ⇒ 零字节」不成立，但 C 格的版式判决由 `c1` 补上（有效 silent）。

| 项 | 值 |
|---|---|
| 采集目录 | `E:/k60-work/evidence/usblog-20261115-213221` |
| boot.img | `25c9821510ca50032617b61e63b058580722e375ee5b533badf3d74c07a9d074`（201,887,744 B；payload kernel `1600744e…`，66,002,944 B） |
| manifest | `E:/k60-work/artifacts/wifi-20261116c0/build-manifest.json`；series 224 `34cf51e4…`；`kernel_args_requested = ["pong_wifi=0"]` |
| 构建树 | `k60-wifi` @ `fff0fb19`（`feat/wifi-bringup`，`dirty_files=0`）；`configs/mondrian_wifi_defconfig:46` = `CONFIG_XNU_OWNER_DATA_VOLUME_UUID="6DCCF70A-6FD6-403E-ACED-95313CD7CBB8"` |
| 实测字节 | boot.img 内 `6DCCF70A-…` ×1、`1BCD69FF-…` ×0；同一扫描下其余 52 张 wifi/bt 图全部相反（§8） |
| ADT 窗口 | `0x120000000`（4.5 GiB；bt-s4b-b / bt-s4c-c / adsp-c 三张能起的同值） |
| 读数 | console.log **0 字节**；`port-not-observed`、`returnedToFastboot`、`fastboot-return`；`scripts/judge-z0.sh … --expect-arg pong_wifi=0` → `silent` / exit 2 |

为什么这读数不能当 C 格判决：

1. **`c0` 与它要对照的镜像差的不止一个变量**：`mondrian_wifi_defconfig` 比
   `mondrian_defconfig` 少 `CONFIG_XNU_GPU_ADDON`（51.4 MB `__DATA` addon）与
   `CONFIG_XNU_K60_PHYSICAL_BATTERY`，把 Data UUID 换成种子 UUID，多
   `CONFIG_XNU_PONG_WIFI`。所以「66 vs 106 MB」本身就是多变量对照（见下表的扣子）。
2. **种子 UUID 是确定性自 panic**：P-152（`docs/engineering/PITFALLS.md:3811-3819`）
   记录过同一配置的症状——`PONG APFS: wait for Data UUID 6DCCF70A-…, timeout=5s`
   → `K60DATA UFS Data window not published` → `dataerr=2` self-panic
   `@kern_exec.c:8463`。`c0` 的 0 字节 / `port-not-observed` / `returnedToFastboot`
   与「死在根挂载阶段」一致；但这条要由 `c1` 确认：2026-11-07 那批同样带种子
   UUID 的采集（`bootcap-20261107-113650` 等）是**有** console 输出的，说明
   console 起来的时机随构建而变。**`c1` 已经飞了，仍是 0 字节**（§11.1）⇒
   本格归因按当时的预设重开：种子 UUID 是真的缺陷，但不是零字节的充分原因；
   零字节另有原因，且那个原因在修好 UUID 之后依然在场。
3. **PWF2 头失配（§1）的形状数据不受影响，但「与死因无关」尚未成立**：头/payload
   失配（count=6、只有 entry[0]）是静态事实；它是不是死因，在本格上没有测到——
   `c0` 根本没跑到解析器。

这一格唯一能留下的东西是**形状**：`__TEXT` 是 `c0` 唯一超过所有能起内核对应段
的段（其余段大小见下表；完整逐段表在 k60-wifi 树
`docs/research/wifi/BOOT-DEATH-SUSPECT.md` §3d，脚本 `E:/k60-work/scratch/table4.py`）。
形状不是判决——要把它变成判决，得先有 `c1` 的有效读数（`c1` 已飞，读数在
§11.1；下表保留 `c0` 当时的形状，用来对照 `c1` 段表逐项相同这件事）：

| surface | `c0`（66.0 MB） | bt-s4b-b（106.5 MB，能起） | 差 |
|---|---|---|---|
| `__TEXT` vmsize | 12,992,512 | 1,720,320 | +11,272,192 |
| `__TEXT,__const` | 11,767,510 @0x2000 | 548,936 @0x1d60 | +11,218,574 |
| PWF2 容器 / 符号跨度 | 1 个，`0xaabed6`（11,189,974 B） | 无 | — |
| `__TEXT_EXEC` | 8,781,824 | 8,388,608 | +393,216 |
| `__LINKEDIT` | 6,668,288 / 6,663,376 | 6,569,984 / 6,568,720 | +98,304 |
| `__DATA` vmsize/filesize | 1,867,776 / 294,912 | 52,920,320 / 51,576,832 | −51,052,544（无 GPU addon） |

**读这张表必须带的扣子**：能起的 106/129 MB 内核带着 51.4 MB 的 GPU/Metal addon
（`PongMetalBridge` ×4、`libvulkan` ×6，落在 `__DATA,__data`），而 `c0` 因为
`mondrian_wifi_defconfig` 没有 `CONFIG_XNU_GPU_ADDON`，完全没有这份 addon。所以
「66 vs 106 MB」是两变量对照：**blob 进、GPU addon 出**。要单变量，下一格应是
「GPU addon + 无 PWF2」或「66 MB 版式 + 同尺寸惰性 `__const`」——两者都要 Lead
的构建决定（k60-wifi 树 §3d 末尾同文）。

`c1` 的重测条件只有一条：把 `k60-wifi` 树 `configs/mondrian_wifi_defconfig` 的
`CONFIG_XNU_OWNER_DATA_VOLUME_UUID` 从种子 UUID 改成设备卷
`1BCD69FF-24A5-48B1-94B6-8FE592B2F597`（`docs/plans/MONDRIAN-OFFICIAL-PAGES.md:564`），
其余一行不动；P-209（`scripts/check-defconfig-uuid.py`，已落 main `011669a`，tag `snap-r201`）落库后这条由门禁硬挡。

### 11.1 `c1` 复测：种子 UUID 不是零字节的充分原因

`c1` 就是上面那一条重测条件的产物：只把 `CONFIG_XNU_OWNER_DATA_VOLUME_UUID`
一行改成设备卷，其余不动。

| 项 | 值 |
|---|---|
| 产物 | `E:/k60-work/artifacts/wifi-20261116c1`；`built_at` 2026-11-15T23:10:57；`repo.head = e33e64557fa7`；series 224 `34cf51e4…`；`kernel_args = ["pong_wifi=0"]` |
| boot.img | `76171061046f74a1ce8273505d3caf80254f70938ebfd5904a274fd109d38673`（201,887,744 B；payload kernel `bd22476d5521`，66,002,944 B；fd `cf4485712c29`；wifi_archive `6e9f2d5547a4`） |
| 段表 | kernel 66,002,944 / `__TEXT` 12,992,512 / `__DATA` 1,867,776 / `__DATA_CONST` 933,888 / `__TEXT_EXEC` 8,781,824 / `__LINKEDIT` 6,668,288 / span 78,344,192 —— **与 `c0` 逐项相同** |
| 修复是否生效 | boot.img 内 `6DCCF70A-…` ×0、`1BCD69FF-…` ×1（`c0` 是 ×1/×0，见 §11 表） |
| 采集 | `E:/k60-work/evidence/usblog-20261115-231707`：`capture.json` `state=port-not-observed`、`bytes=0`、`portSeen=false`、`portOpened=false`、`stopReason=fastboot-return`、`logSha256=E3B0C442…`（空串的 sha256）；`boot.json` `bootExitCode=0`、`returnedToFastboot=true`；`console.log` **0 字节** |
| 判定 | `scripts/judge-z0.sh` → `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]`，RC=2 |

**判决：`silent`。** 这条读数把「种子 Data UUID ⇒ 零字节」这条单变量假设否掉了——
配置缺陷是真的（P-152 的机制、`c0` 的字节计数都成立），但它不是 `c0` 零字节的
**充分**原因。所以：

- `c0` 维持 `invalid-measurement`：它确实没测到版式，理由不变。
- `c1` 也没测到版式，但它测到了另一件事——**把种子 UUID 修掉之后，66 MB + 真 blob +
  `pong_wifi=0` 仍然是 0 字节**。这一格因此不能再用「配置缺陷」解释。
- 「0 字节与种子 UUID 的因果」这一问要重开。原先把 2026-11-07 那批带种子 UUID 却
  有 console 输出的采集当作反例，现在这个反例更硬：**同一缺陷下有时有声有时无声**，
  说明 console 起来与否取决于别的东西（构建版式），不能由 UUID 单独决定。

### 11.2 `c2`：blob 搬进 `__DATA_CONST` 的第二张，仍然 silent

`c2` 是 `t2` 那行 `.section __DATA,__const` 的复现，同时换回工作基线 defconfig
（设备 UUID、`pong_wifi=0`）。

| 项 | 值 |
|---|---|
| 产物 | `E:/k60-work/artifacts/wifi-20261116c2`；`built_at` 2026-11-15T23:40:04；`repo.head = 9fd2018a80b3`；series 224；`kernel_args = ["pong_wifi=0"]` |
| boot.img | `dc7e4186f737…`（201,887,744 B；payload kernel `92c0ca3a03d0`，117,305,344 B；fd `cf4485712c29`；wifi_archive `de3f48a53f1f`） |
| 段表 | kernel 117,305,344 / `__TEXT` **1,802,240** / `__DATA_CONST` **12,124,160** / `__DATA` 53,149,696 / `__TEXT_EXEC` 8,798,208 / `__LINKEDIT` 6,668,288 / span 129,642,496 |
| 与 `t2` 的关系 | 段表与节表**逐项相同**（`diff` 为空；内核字节不同） |
| 与 `z0` 的关系 | 只有两项不同：`__TEXT` −11,190,272、`__DATA_CONST` +11,190,272 —— 就是 blob 从 `__TEXT,__const` 搬到 `__DATA_CONST,__const` |
| PWF2 落点 | `__DATA_CONST,__const` size 11,919,062 @ 文件偏移 1,806,336；另一处字面量在 `__TEXT,__cstring` @ 1,664,502 |
| 采集 | `E:/k60-work/evidence/usblog-20261116-000136`：`console.log` **0 字节**，判 `silent` |

**判决：`silent`。** 意义有两层：①`t2` 的读数被独立复现了一次，不是单张镜像的
意外；②blob 的**两种驻留形态**（`__TEXT,__const` 与 `__DATA_CONST,__const`）都
silent，所以「驻留位置」这一轴现在有两种形态的否证，不再是只靠 `t2` 一张。

### 11.3 口径：已飞镜像的 blob 与否，与「总大小」的排除

全库 join（脚本 `E:/k60-work/scratch/refmine/scan-blob3.py`，扫 319 个产物目录、
按 `image_sha256` 对上 `E:/k60-work/evidence` 的 `boot.json`）：

| 组 | 张数 | 真 PWF2 容器 | alive（console > 1 KB） | silent（console = 0 B） |
|---|---|---|---|---|
| 已飞，内核带真 PWF2 | **11** | 11 | **1**（`c3`） | **10** |
| 已飞，内核不带 PWF2 | 47 | 0 | 38 | 8 |

带真 PWF2 且已飞的十一张是：`wifi-20261114a`、`wifi-20261115a`、`wifi-20261115h2`、
`wifi-20261116mhi3`、`wifi-20261116mhi4`、`wifi-20261115z0`、`wifi-20261116t2`、
`wifi-20261116c0`、`wifi-20261116c1`、`wifi-20261116c2`、`wifi-20261116c3`——
**前十张 0 字节，`c3` alive（221,429 B，§13.1）**。

不带 PWF2 的八张 silent 全在 usb 与 bt 线（`bt-s1-20261114b`、`bt-s4b-20261115c`、
`bt-bisect-h123`、`usb-20261114c`、`usb-20261114f`、`usb-20261114h2`、
`usb-20261115b`、`usb-20261115c`），与本问题无关。

「真容器」这一列是 Lead 2026-11-16 01:59 要求加的，理由是 `c3` 这个反例证明单轴
表格本身不够：同一列「blob 有」里混着两种东西——真容器（span 11,189,974、6 条或
4 条 entry，payload 合计 11,057,218 B）与 tiny 家族的 4×23 B 占位（span 16,407，
`t0c`/`t1c`）。判定手法：`E:/k60-work/scratch/refmine/probe-pwf2kind.py` 读容器头
`count` 与各条 `offset+len` 的最大跨度，跨度 > 1 MB 才算真容器。

**「总大小」这一轴由 129 MB 的 alive 反证排除**：`adsp-20261115c/d/e` 三张
kernel **128,991,232 B**（比 117 MB 家族还大 11.7 MB），`__DATA` 76,414,976 B、
span 141,111,296 B，全部进桌面（`usblog-20261115-213413` 214,232 B、
`usblog-20261115-220912` 221,484 B、`usblog-20261115-223916` 220,234 B，
SpringBoard 分别 128 / 132 / 120 次）。它们不带 PWF2、`pong_wifi` 不存在。
所以「内核大于 N MB 就死」的阈值模型被否证两次（`bt-s4b-20261115b` 106.5 MB 进桌面、
`bt-s4b-20261115c` 同尺寸 silent 是一次；adsp 129 MB alive 是第二次，且这次把
117 MB 也包在里面）。

（2026-11-16 01:51 之前本段写的是「剩下能解释 silent 的只有两条：pool/窗口通道与
11.19 MB PWF2 进内核这件事本身」。`c3` 之后这两条都不再成立：pool 占用与版式跟
`c2` 相同却活了，blob 逐字节相同也活了——见 §13。）

## 12. 交叉核对 `docs/engineering/FIRMWARE-REBUILD.md`（2026-11-16）

只读核对，不改该文档。三条主张逐条给证据；结论是两条要收回、一条成立。

### 12.1 「`4bbe7601…` 那四张都进过 SpringBoard」——**不成立**

该文档 §3 的表（`origin/main` `207e108` 的 `:35`）把
`4bbe76017eb4…` 标为「重建出来的卷，且上机成功进过 SpringBoard」，并说这是
「本节的关键」。实测：

| 产物 | 采集目录 | console.log | SpringBoard 计数 | `returnedToFastboot` |
|---|---|---|---|---|
| `audio-probe-20261114j` | `E:/k60-work/evidence/audio-probe-j/run1` | 222,415 B | **129** | false（`bootExitCode=0`） |
| `audio-probe-20261114k` | `E:/k60-work/evidence/usblog-20261115-012317` | 220,748 B | **129** | false（`bootExitCode=0`） |
| `audio-probe-20261115l` | **无** | — | — | — |
| `audio-probe-20261115m` | **无** | — | — | — |

- `l` 与 `m` 在 `E:/k60-work/evidence` 全量 644 个条目里**没有任何 `boot.json`
  指向它们**（按 `image_sha256` `5fe546b2…` / `2283aaa9…` 全量扫 json）；它们自己的
  `artifacts/*/boot.json` 都写 `hardware_tested: false`，`fd_sha256` 同为
  `4bbe76017eb4…`。`ls /e/k60-work/evidence | grep -E 'usblog-20261115-0[3-6]'`
  为空 ⇒ 2026-11-15 03:00–06:00 这两张的构建时段没有任何采集。
- 所以「四张都进过桌面」应为「其中 `j`、`k` 两张进过桌面」。P-154 的「部分推翻」
  本身不必收回（`j`/`k` 确实证明了重建卷能找到 payload），但那句话的证据基础
  从四张缩到两张。
- 附带一条采集布局的坑：`audio-probe-j` 的证据在**子目录** `run1/`、`run2/` 里，
  按 evidence 顶层目录 join 会漏掉它——早前把 `j` 判成「无证据」就是这个原因。

### 12.2 「`4bbe7601…` 是包序修好之后重建的卷」——**时间上不成立**

- 包序修复 = `00aaeea`「fix(firmware): let the vendored UniXNUPkg win over the staged
  copy」，commit 时间 **2026-11-13 15:13:07 +0800**（`board.toml` 把
  `{uefi}/Platforms/Xiaomi` 从第 4 位挪到第 2 位，`{uefi}` 之后、`{tree}/package` 之前）。
- 扫 2026-11-12/11-13 的 107 次飞行（脚本 `E:/k60-work/scratch/refmine/fd-hist3.py`：
  解 boot.img kernel 槽的 gzip、取 `blob[112:112+3145728]`、校验 `_FVH` 后 sha256）：
  **101 次是 `cf4485712c29`**，**6 次是 `4bbe76017eb4`，全部落在 2026-11-13
  15:08–15:49**：`usblog-20261113-orderfd`（15:08:56）、`orderfd2`（15:10:24）、
  `orderfd-keepk`（15:18:24）、`noseed`（15:24:36）、`keepadt`（15:46:19）、
  `keepdtb`（15:49:22）。
- **`4bbe7601` 首现 15:08:56，比 `00aaeea` 早约 4 分钟**，所以它不是「修好顺序
  之后」的产物；那 6 次也全部 `returnedToFastboot=true`，console 尾部是
  `initproc exited -- exit reason namespace 2 subcode 0xb` + `K60PANICARGS`
  （`orderfd` 那张是 panic 寄存器转储）⇒ **内核起来了、根挂载失败，不是 P-154 的
  `no boot entry found`**。
- P-154 的原始失败现场**零留存日志**：`E:/k60-work/evidence` 与
  `E:/k60-work/artifacts` 下 490 个非空 `console.log` 里，`no boot entry found`、
  `UNIXNURAMDISK`、`menu: shown`、`UNIXNU: config` 全部 0 命中。11-12/11-13 的
  `boot.json` 大多指向 `E:\k60-work\usb-a-stage\out\`（无 build-manifest），所以
  只能用镜像内嵌 FD 字节判代。结论：「失败样本都来自 P-176 修复之前」这条
  **既不能证真也不能证伪**，能证的只有「现存唯一重建卷在修复前后各飞过一次」。

### 12.3 「同一 uefi pin ⇒ 同字节」——**成立，且可证伪点已找到**

- `/e/k60-work/artifacts/fd` 共 130 个 `.fd`，全扫后只有 **2 个 distinct
  (sha, 内嵌日期, 内嵌时间, workspace)**：`cf4485712c29` ×126（`Nov  2 2026` +
  `10:03:21`，workspace `/home/emilelu/hackios/uefi-mondrian` ×2、`/mnt/e/` ×0）、
  `4bbe76017eb4` ×4（`Nov 13 2026` + `03:38:39`，workspace
  `/mnt/e/hackios/uefi-mondrian` ×2、`/home/emilelu/` ×0）。没有第三卷。
- `/e/hackios/uefi-mondrian` HEAD `9b79562` 的 `git log -1 --format=%ct` =
  **1794541119** = UTC 2026-11-13 03:38:39 ⇒ **`4bbe7601` 的 `SOURCE_DATE_EPOCH`
  精确等于当前 uefi HEAD**。ct `1793613801`（Nov 2 10:03:21Z）在 uefi-mondrian 的
  38 个提交里查无 ⇒ `cf448571` 来自 2026-11-02 那个已消失的 Linux 检出。
- 因此两卷 sha 差异**完全可以由不同 pin 解释**，不能拿来反驳「同源同字节」。反过来
  这条也说明「FD 的 sha 是 pin 的身份」成立；P-154 的「`cf448571` 无法复现」也就有了
  机制解释——现树是 `9b79562`，重建只能得到 `4bbe7601` 那类字节。
- 机制行号：`/e/hackios/UniXNU/scripts/unixnu/firmware.py` **:69**
  `env.setdefault('SOURCE_DATE_EPOCH', git(uefi, 'log', '-1', '--format=%ct').strip())`，
  注释在 :68；**:85-86 是 `fd_path` 与 `st_size` 校验**。该行由 `850776a`
  （2026-10-19 20:11:04）引入，早于所有现场镜像。

### 12.4 两处文档缺陷（建议改，未改）

1. `FIRMWARE-REBUILD.md` §2（`:25-26`）写「`firmware.py:85` 把 `SOURCE_DATE_EPOCH`
   固定」——行号错，实际 **:69**（:85 是 fd 存在性与大小校验）。
2. 同文 §5（`:64-65`）第 5 步「两个卷用 `strings` 对比 initrd 追踪行」在现有两卷上
   **无行可比**：`initrd`、`RamDisk`、`UNIXNU`、`menu:`、`no boot entry` 在两卷里
   ASCII 与 UTF-16（`strings -e l`）都是 0 命中。这一步要么换手法，要么删。

## 13. `c3`：带真 PWF2 却进桌面，死因是 UFS SMMU lease（2026-11-16 01:51）

本节把前面十二节从「排除法账本」变成「有真因的账本」。Lead 2026-11-16 01:59 的裁决
与本节的实测一致：**真因已证实（P-215），尺寸/段表/驻留/窗口/参数/UUID 六轴之所以
全被否证，是因为它们本来就不是原因。**

### 13.1 `c3` 判决：`alive`，带逐字节相同的真 PWF2 容器

| 项 | 值 |
|---|---|
| 产物 | `E:/k60-work/artifacts/wifi-20261116c3`；`built_at` 2026-11-16T01:34:21；`repo.head = 3207bd3c019c`（`feat/wifi-bringup`，`dirty_files=0`）；series 226 `d83fb1890e93`；`kernel_args_requested = ["pong_wifi=0"]` |
| boot.img | `5a19e1103f07b1f5612bb903c1060ea6b01db7ae9d0bba414739a8f74616fc5f`（201,887,744 B；payload kernel 117,325,824 B；fd `cf4485712c29`；dtb `2d044eaa…`） |
| 段表 | `__TEXT` **1,802,240** / `__TEXT_EXEC` 8,814,592 / `__DATA` 53,149,696 / `__DATA_CONST` **12,124,160** / `__LINKEDIT` 6,684,672 / `__PRELINK_TEXT` 7,421,952 / `__PLK_TEXT_EXEC` 22,757,376 / span **129,675,264** |
| 节表 | `__TEXT,__const` 574,953 @11,712；`__TEXT,__cstring` 1,080,892 @586,665；`__DATA_CONST,__const` 11,919,062 @1,806,336 |
| PWF2 容器 | 6 条：`amss.bin` 4096/5,470,128、`amss20.bin` 5,476,352/5,296,128、`bdwlan.elf` 10,772,480/59,932、`bdwlang.elf` 10,833,920/59,936、`m3.bin` 10,895,360/266,684、`regdb.bin` 11,165,696/24,278；span 11,189,974；**sha `3f68db4dc0927742…`，与 `c2` 逐字节相同** |
| 内核字符串 | `PWF2` 2 / `PongWifi` 32 / `Pong MHI` 11 / `pong_wifi` 25 |
| 采集 | `E:/k60-work/evidence/usblog-20261116-015128`：`console.log` **221,429 B**（`capture.json` 的 `logSha256 = A62070715CC790A5…`、`state = captured-budget-complete`、`portSeen = true`、`stopReason = budget`、`panicMarker = null`）；`boot.json` `bootExitCode = 0`、`returnedToFastboot = false` |
| 判读 | SpringBoard **133** 次、`K60DATA` 12、`Early boot complete` 1、`Apps SMMU lease` **0**、`PongWifi` 0、`MHI` 0 |

**与 `c2` 的唯一差别是 20,480 B 代码**：
`patches/wifi/0012-drivers-PongWifi-lease-lock-lazy-init.patch`（117,305,344 →
117,325,824 B，差值正好 20,480）。版式、段表、PWF2 容器、窗口、`pong_wifi=0` 全都同形。
所以这一对是**单变量干预**，不是又一次排除法。

### 13.2 死因：UFS SMMU lease 被提前索取（P-215）

调用链（实测行号，`k60-wifi` 树）：

- `drivers/NativeUfs/PongUfsTransport.cpp:29` `extern "C" bool pong_smmu_lease_lock(void) __attribute__((weak_import));`
- 同文件 `:143` `hostBringUp()`；`:174-181` 是 `patches/wifi/0004` 插进去的 lease 段：
  `if (pong_smmu_lease_lock && pong_smmu_lease_unlock) { lease.held = pong_smmu_lease_lock(); if (!lease.held) return transportFailure("Apps SMMU lease unavailable"); }`；
  `:602` `if (!hostBringUp()) return false;`
- `drivers/PongWifi/PongWifiPlatform.cpp:152` `IOLock *powerLock,*smmuLeaseLock;`；`:729`
  在 `pong_rpmh_init()` 里 `IOLockAlloc`；`:716-718` 先 `pong_rpmh_init()` 再查开关；
  唯一调用点 `pong_wifi_start_optional()` 由 `ArmDTPlatform.cpp:227-228` 在
  `registerService()` 之后调。
- `patches/wifi/0001` 的修前实现：`if(!smmuLeaseLock) return false; IOLockLock(...); return true;`

**UFS 是根设备，必然先启动**（能起的日志里 `PONG_UFS` 在 115 行、
`ArmDTPlatform: registered platform` 在 147 行）。于是 UFS 索取 lease 时
`smmuLeaseLock == NULL` ⇒ lock() 返回 false ⇒ `transportFailure("Apps SMMU lease
unavailable")` ⇒ 整个 UFS transport 放弃 ⇒ 没有根设备 ⇒ 内核在 console worker
起来之前就死 ⇒ **0 字节**。

修法（`patches/wifi/0012`，单变量）：`if(!smmuLeaseLock) smmuLeaseLock=IOLockAlloc();
if(!smmuLeaseLock) return false; IOLockLock(smmuLeaseLock); return true;` —— 分配搬进
lock() 自己，`pong_rpmh_init()` 里那次分配保留。补丁注释原文写的就是这条理由
（"the first client to want it is not necessarily the WiFi worker: NativeUfs takes
the same lease in hostBringUp()"）。

**为什么这条能解释前面十二节的全部负结果**：`pong_wifi=0` 只挡住 worker 之后的注册，
挡不住 UFS 在更早的 `hostBringUp()` 里索取同一把锁。所以只要 wifi 归档被
`-Wl,-force_load` 链进内核（`patches/wifi/0010`），**即使驱动开关是 0**，UFS 也会
因为这把锁未分配而失败。尺寸、段表、blob 位置、窗口、参数、Data UUID 全都不是原因，
它们只是恰好与「链了 wifi 归档」同步变化。

### 13.3 方法论：观测轴 ≠ 因果轴（Lead 要求写进 P-215）

本页 2026-11-15 那版写过一句「带 PWF2 的已飞镜像没有一张 alive……所以『blob 在场』
是目前唯一没有被任何 alive 镜像打过的轴」。join 方法没错（11 张里 10 张 0 字节是实测），
**错在结论强度**：一张表能证明「这条轴与生死同步」，不能证明「这条轴导致生死」，
除非做过单变量干预。正确写法就是当时写在 §0.1 里的那句推翻条件——「推翻条件 = 一张
带真 PWF2 的 alive 镜像」——**推翻条件写对了，只是没等到它出现就把它写成了因果**。

三条可复用的写法：

1. 观测轴表格的结论列只能写「这是目前唯一还分得开生死的观测轴」，不能写「这是死因」。
2. 每条轴必须带一行推翻条件（本页 §0.1 做到了，这是唯一挡住错误扩写的东西）。
3. 单变量干预之后，旧表要**保留原样并标注结局**，不要删——被推翻的过程本身是记录
   （§6 矩阵、§7 两条口子、§9 结论 7 都按这个方式处理）。

### 13.4 `c3` 之后还剩什么

- **§7.1 pool 通道**：关闭。`c3` 与 `c2` 同 117 MB 版式、同 pool 占用，一个活一个死。
- **§7.4 驱动体静态注册链**：关闭。`c3` 上 `PongWifi` 串 0 次、`MHI` 0 次——
  `pong_wifi=0` 时 worker 确实没跑，系统照样进桌面；死因在 UFS 侧，不在 wifi 归档的
  静态注册链上。
- **仍开的两件**：①PWF2 头失配（§1）——早期 mhi4 内核里 entry[1..5] 全空的观察需要
  在 `c2`/`c3` 这类新容器上重测（`c2`/`c3` 的六条 entry 都有 payload）；
  ②`pong_wifi=1` 的 MHI 阶段（`c3` 是 `pong_wifi=0`，驱动没跑，`c4` 才是功能判决）。
- **本页此后不再改归因**：等 `c4`（`c3` + `pong_wifi=1`）落盘，按 Lead 的判读分支
  重写：`c4` alive 且 MHI 通 ⇒ 本页按「silent 已解决、进入 MHI 阶段」收尾；
  `c4` alive 但 MHI 不通 ⇒ 本页分「silent 段」与「MHI 段」两段；`c4` silent ⇒
  `pong_wifi=1` 还有第二个独立缺陷，回到二分。

