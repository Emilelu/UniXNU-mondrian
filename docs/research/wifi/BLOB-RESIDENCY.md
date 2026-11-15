# WiFi 固件 blob 的 residency：11.19 MB `__TEXT,__const` 会不会撞上任何装载边界

状态：静态判定 + 两张上机判决（`z0`、`t2`，都是 silent，§10）。没有构建。本文回答任务 G 的一个问题：

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

口径提醒（2026-11-15 `t2` 判决后更新）：`__TEXT` = 12,992,512 的死格
（mhi3/mhi4/z0）都带同一个 blob，`__TEXT` = 1,720,320 的活格都不带；
但 `t2` 把 blob 移出 `__TEXT` 之后仍然 silent——「`__TEXT` 驻留跟着死亡走」
已被上机数据**推翻**（§10.3 第 2 条）。仍然开着的是 §7.1 的 pool 通道与
66 MB + blob 的 C 格（至今没飞）。

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
- **「边界假说」整体**：不需要额外推翻——§0 已逐条证伪；仍然活着的是 §7.1 的 pool
  通道（是「量」的问题，不是「边界」）——`t2` 之后它是唯一未被上机数据否证的通道
  （§10.4）。

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
到这一步，能解释 silent 的只剩 pool/窗口通道与内核初始化路径的差异（§7.1、§10.4）。

对齐不变：`__TEXT` vmaddr 两边都是 0xfffffff007004000（内核基址 4 KB
对齐，DarwinBoot.c:194 校验 `Base & EFI_PAGE_MASK`）；
xnu-work `osfmk/arm64/arm_vm_init.c:2306` 的
`assert(segDATACONSTB == segTEXTB + segSizeTEXT)` 在 mhi4 上仍成立
（0x7004000 + 12,992,512 = 0x7c68000 = `__DATA_CONST` vmaddr）。

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
E 格与 F 格（`t2`）已飞（2026-11-15，都 silent），判决见 §10；其余格子仍未飞。

| 格子 | 内核 | `__TEXT` | blob | `pong_wifi` | 上机记录 | 该格能推翻什么 |
|---|---|---|---|---|---|---|
| A | 54.2 MB stock（thermal / bt / …） | 1.64 MiB | 无 | 0 | 已飞，**alive** | 基线 |
| B | 54.8 MB tiny（`t0c` / `t1c`） | 1.82 MiB | 4×23 B 占位 | 0 / 1 | **从未飞** | `t1c` alive ⇒ 驱动存在 + `pong_wifi=1` 本身无害，死因需要真 blob 或与之同步变化的东西 |
| C | 66 MB（`a2`，trial 级，**没有**正式重出） | 12.39 MiB | 11.19 MB | 0 | **从未飞** | C alive ⇒ blob、`__TEXT` 体积、65.9 MB 镜像三者同时被洗清（与 mhi4 只剩 `pong_wifi` 之差） |
| D | 117 MB（`mhi5`） | 12.39 MiB | 11.19 MB | 1 | **从未飞** | 主要探 `ReadFile` 的 128 MB 上限与 span，与 blob 边界问题无关 |
| E | 117 MB（`z0`，正式镜像，与 `mhi5` 只差 `pong_wifi`） | 12.39 MiB | 11.19 MB | 0 | **已飞，silent（0 B，`usblog-20261115-135859`；§10）** | 驱动 vs blob：E 静默而 105 MB 家族 alive ⇒ blob 被钉住、驱动被洗清；E alive ⇒ 驱动有罪 |
| F | 117 MB（`t2`，blob 移入只读 `__DATA_CONST`，`__TEXT` 1.80 MiB） | 1.80 MiB | 11.19 MB（在 `__DATA_CONST`） | 0 | **已飞，silent（0 B，`usblog-20261115-161102`；§10.3）** | F 静默 ⇒ `__TEXT` 驻留被推翻，死因不在驻留位置；F alive ⇒ 驻留位置被钉住 |

读法：C 是「体积」那一问的判决格（66 MB + blob + `pong_wifi=0`）——C 静默 ⇒
体积方向仍活（但边界已排除，只剩 §7.1）；C 出声 ⇒ 本文问题被实际否决，死因回到
驱动运行路径。**C 至今没有正式镜像**：`a2` 是 trial 级（P-201，manifest 无 series
键），而正式重出的 `z0` 实测不是 66 MB——它 117,305,344 B，与 `mhi5` 同尺寸、只把
`pong_wifi` 关掉（§9 的实测表）。所以 E 顶替不了 C：**E 静默只证明「blob（连同它
所在的 117 MB 版式）与 105 MB alive 家族的差是致命的」，证明不了 65.9 MB 这一档**；
同理 E alive 也不能替 C 洗清体积，它洗清的是驱动。

B 是 C 的对照格：B 出声而 C 静默 ⇒ 11.19 MB blob 被钉成唯一变量；B 也静默 ⇒
死因不需要 blob。E 是「驱动 vs blob」的对照格（与 `mhi5` 只差 46 字节 / 8 处构建
时间戳，见 k60-wifi `docs/research/wifi/BOOT-DEATH-SUSPECT.md` §3b）：**已飞，
verdict = silent**（§10）。按这条读法，驱动这一支被洗清（§10.2：`pong_wifi=0` 时
worker 根本没启动），blob / 117 MB 版式这一支被钉住但没被证明——它的推翻条件写在
§10.3。F 格（`t2`）已经飞完：**silent**，`__TEXT` 驻留被推翻（§10.3 第 2 条）。

## 7. 仍然开着的口子（本文不关闭它们）

`z0` 与 `t2` 上机后各口子的格位变化见 §10.4；本节保留静态判定时的原样。

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

## 8. 证据清单

| 事实 | 证据 |
|---|---|
| 段表逐段扫描（含 105 MB 家族） | `E:/k60-work/scratch/refmine/probe-segs.py`、`probe-seg.py`、`probe-allwifi.py`（46 张 boot.img 汇总） |
| 窗口值逐镜像 | `probe-window3.py`：ADT 属性 `darwinboot-memory-size` 解码——thermal/springboard/gpu/base/touch=0x130000000（4.75 GiB）alive；brightness-4=0x120000000（4.5 GiB）alive；wifi-20261114a/mhi3=0x130000000 死；mhi4/mhi5/z0/t2/bt-s4b-20261115c=0x120000000（z0 与 t2 已判 silent）；a2/t1/t1c=0x130000000 未飞 |
| `z0` 判决 | `judge-z0.sh usblog-20261115-135859 --expect-arg pong_wifi=0` → `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]`；MSYS 与 WSL 两侧 `RC=2`；参数自检 manifest `["pong_wifi=0"]` + 镜像字节 `pong_wifi=0 x1` |
| `t2` 判决 | `judge-z0.sh usblog-20261115-161102 --expect-arg pong_wifi=0` → `wifi-boot-judge: silent (console.log, 0 bytes on disk, capture.json declares 0) [exit 2]`；MSYS 与 WSL 两侧 `RC=2`；参数自检 manifest `["pong_wifi=0"]` + 镜像字节 `pong_wifi=0 x1` |
| 六张 silent 图 + bt 三图逐段实测 | `probe-silent6.py`（E:/k60-work/scratch/refmine/，复用 probe-family 段解析与 probe-window3 窗口解码）：§9 表的 kernel/段/窗口数字全部出自它 |
| alive 归属（join image sha → evidence） | `probe-join2.py`：thermal adc796b6→usblog-20261115-003922（232,670 B）；springboard 3ada9562→003207；gpu ba783b74→212253；brightness e41eb797→013520（185,701 B）；a2/mhi5/z0/t1/t1c 全库零命中（从未上机） |
| `__const` 内固件逐字节匹配 | `probe-const.py` / `probe-const2.py`：四文件与 `/mnt/e/k60-work/firmware/qca6490-wifi/` 相同；非零字节合计 7,030,971 |
| DarwinBoot 检查 | drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c:160,168,190-191,194-196,558,607,619 |
| XNU 侧无上限 | xnu-work（`.cache/xnu-work`）grep `KERNEL_TEXT_MAX\|kPrelinkTextMax\|MAX_KERNEL_TEXT` = 0 命中 |
| VA 布局注释 | xnu-work `osfmk/arm64/arm_vm_init.c:165-181`（顺序）、:2087（取段）、:1415（RNX）、:2306（紧邻断言） |
| 解析器 | k60-wifi 树 drivers/PongWifi/PongWifiPlatform.cpp:553-556 |
| PWF2 失配 | mhi4 kernel 文件偏移 589,824 处头（count=6，entry[0] amss.bin，1..5 全空）vs 四文件实测偏移（§1 表） |

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

三条从这张表直接读出来的结论（都不是「结论」，是可推翻的事实）：

1. **`z0` 不是 66 MB 的 C 格**：它 117,305,344 B，`__DATA` 53,149,696 与 105 MB
   alive 家族同量级，是 `mhi5` 的孪生（只差 `pong_wifi`）。§6 的 C 格（66 MB +
   blob + `pong_wifi=0`）至今没有正式镜像，只有 trial 级的 `a2`。`z0` 已飞、
   silent（§10），所以这一格回答的是「驱动 vs blob」，不是「体积」。
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

这张表的生成方式：`mtype -i <boot.img 的 ramdisk 卷> ::EFI/UniXNU/Payloads/kernel.macho`
再按 `LC_SEGMENT_64` 解段；脚本 `E:/k60-work/scratch/refmine/probe-family.py`。
## 10. 上机判决：`z0` 与 `t2` 都是 silent（2026-11-15）

§6 的 E 格（`z0`）与 F 格（`t2`）都已经飞了，都 silent。本节记两次判决、
为什么读得动、三条推翻条件的走向，以及两次飞行给 §7 三个口子带来的格位变化。
措辞守 Lead 的裁决：`__TEXT` 驻留在 `t2` 之前是首要嫌疑，`t2` 之后是**已推翻项**。

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
都给 `silent` / `RC=2`（`judge-z0.sh` 的 helper 路径已改成脚本自身相对 + 候选根
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
3. **推翻「blob 是变量」**：66 MB + blob + `pong_wifi=0`（§6 的 C 格，正式镜像）
   进用户态而 `z0` 静默 ⇒ 死因落在 117 MB 版式（`__DATA` / span / pool），blob
   本身被洗清。这一格至今没有正式镜像，`t2` 之后它仍是「blob 是不是变量」的
   判决格。

三条都不涉及静态量：它们都是「再飞一张」就能证伪的句子，不需要新代码。

### 10.4 §7 三个口子的格位更新

1. **DXE pool 碎片化（§7.1）——唯一未否证的通道**。`z0` 是 117.3 MB 整块进
   pool，比 C 格翻倍，窗口 4.5 GiB（余量约 223 MiB），仍然 silent；而 mhi4
   （65.9 MB、同一窗口）也 silent。两格之间差约 51 MB pool 占用而结果相同，所以
   pool 占用本身没有把 4.5 GiB 窗口推过线。`t2` 把 blob 移出 `__TEXT` 后仍
   silent，驻留形态被否证——到这一步，能解释 silent 的通道里，这条是唯一还没有
   被上机数据否证的。**但**：0 字节的 console 里没有 `NO WINDOW` 行可读，
   `AllocateWindow` 到底走到哪一步仍是静态空白。
2. **105 MB 家族不能反证（§7.2）——对照仍成立，但不再指向驻留**。`z0` 的
   `__DATA` 53,149,696 与 brightness-4 的 52,920,320 同量级，差在 `__TEXT` 的
   11.27 MB 与 args；同一 4.5 GiB 窗口下 105 MB 家族 alive、117 MB 的 `z0` 死。
   `t2` 把 `__TEXT` 收回之后仍死，两格合起来把「`__TEXT` 体积」与「驻留位置」
   都洗掉——剩余差别落在 117 MB 版式本身（`__DATA` / span / pool 占用）与内核
   初始化路径上。
3. **PWF2 头失配（§7.3）——不受影响**。`z0` 与 `t2` 都是 `pong_wifi=0`，
   解析器不运行；这一条仍然是任何 `pong_wifi=1` 飞行的待办。

