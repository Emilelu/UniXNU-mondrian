# WiFi 固件 blob 的 residency：11.19 MB `__TEXT,__const` 会不会撞上任何装载边界

状态：静态判定。没有构建、没有上机。本文回答任务 G 的一个问题：

> `__TEXT,__const` 里 11.19 MB 的 PWF2 固件，会不会让内核的 `__TEXT` 段在
> DarwinBoot 的段加载路径上触发某种边界（段大小、对齐、还是 kernelcache 的
> `__TEXT` 上限）？

结论先行（§0）：**这条路径上的每一个硬边界都被实测值绕开了，余量最小的
一项也有 2.0×。** 本文不下「所以不是体积死因」的结论——那是 C1/C2
上机判据（[BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §7）的事——只把
「哪里可能有边界、边界在哪、离边界多远」钉到 文件:行。

## 0. 结论先行

| # | 候选边界 | 实测值 | 上限 | 余量 | 判定 |
|---|---|---|---|---|---|
| 0.1 | 单段大小 vs `WINDOW_SIZE`（256 MB） | `__TEXT` vmsize **12,992,512** | 268,435,456 | 20.7× | 不触发（[DarwinBoot.c:168](../../../drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c)） |
| 0.2 | 内核 VA 跨度 vs `WINDOW_SIZE - 2 MB`（254 MB） | **78,327,808**（mhi4） | 253,388,800 | 3.2× | 不触发（DarwinBoot.c:196） |
| 0.3 | 内核镜像文件 vs `ReadFile` 的 `SIZE_128MB` | **65,978,368** | 134,217,728 | 2.0× | 不触发（DarwinBoot.c:558） |
| 0.4 | `MAX_SEGMENTS` 64 | 15（vmsize≠0） | 64 | 4.3× | 不触发（DarwinBoot.c:160） |
| 0.5 | VA 段间重叠 | prelink 段在低地址，不与 `__TEXT` 相交 | 无重叠 | — | 不触发（DarwinBoot.c:190-191） |
| 0.6 | XNU 侧 `__TEXT` 大小上限常量 | grep 全树 0 命中 | 不存在 | — | 不存在（§5） |
| 0.7 | 页/16 KB 对齐 | 两内核 `__TEXT` vmaddr 同为 0xfffffff007004000 | 页对齐 | — | 不变（§2） |

真正的存量差异只有一条（§2）：固件把 `__TEXT` 从 1.64 MiB 撑到 12.39 MiB；
105 MB alive 家族的体积来自 `__DATA` 52.9 MB，`__TEXT` 与 baseline 相同。
「边界触发」假说在这条路径上没有落脚点；§7 列出仍然开着的三个口子。

### 0.1 各判断的推翻条件

每条判断都能被一行实测推翻；写在这里是为了让下一个人知道该看什么。

- **0.1 被推翻**：出现 `__TEXT` vmsize > 256 MB 的内核仍过 `ParseKernel`；或本内核实测
  `__TEXT` vmsize ≠ 12,992,512。
- **0.2 被推翻**：实测 span > 253,388,800 的内核能过 :196；或 mhi4 span ≠ 78,327,808。
- **0.3 被推翻**：内核镜像文件 > 134,217,728 字节仍被 `ReadFile` 接受。
- **0.4 被推翻**：vmsize≠0 的段数 ≥ 64 的内核被接受。
- **0.6 被推翻**：在 xnu-work 找到任何以 `__TEXT` 大小（而不是页对齐）为输入的断言或
  上限——grep 之外还要读 `pmap_bootstrap` 与 KTRR 相关代码。
- **「边界假说」整体**：不需要额外推翻——§0 已逐条证伪；仍然活着的是 §7.1 的 pool
  通道（是「量」的问题，不是「边界」）。

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
   mhi4 span 78.3 MB（105 MB 家族也才 117.6 MB），余量 3.2×。
   注意这条检查量的是 **vmsize 和**，与文件大小无关。
3. **镜像文件上限**（:558）：`SIZE_128MB`。65.98 MB < 128 MB，余量 2.0×。
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
pool 通道仍然存在。要把两者分开靠四格对照；这里只列格子与每格能推翻什么，不排期。

| 格子 | 内核 | `__TEXT` | blob | `pong_wifi` | 上机记录 | 该格能推翻什么 |
|---|---|---|---|---|---|---|
| A | 54.2 MB stock（thermal / bt / …） | 1.64 MiB | 无 | 0 | 已飞，**alive** | 基线 |
| B | 54.8 MB tiny（`t0c` / `t1c`） | 1.82 MiB | 4×23 B 占位 | 0 / 1 | **从未飞** | `t1c` alive ⇒ 驱动存在 + `pong_wifi=1` 本身无害，死因需要真 blob 或与之同步变化的东西 |
| C | 66 MB（`a2`，正式重出为 `z0`） | 12.39 MiB | 11.19 MB | 0 | **从未飞** | C alive ⇒ blob、`__TEXT` 体积、65.9 MB 镜像三者同时被洗清（与 mhi4 只剩 `pong_wifi` 之差） |
| D | 117 MB（`mhi5` / `z0`） | 12.39 MiB | 11.19 MB | 1 | **从未飞** | 主要探 `ReadFile` 的 128 MB 上限与 span，与 blob 边界问题无关 |

读法：C 是本文问题的判决格——C 静默 ⇒ 体积方向仍活（但边界已排除，只剩 §7.1）；
C 出声 ⇒ 本文问题被实际否决，死因回到驱动运行路径。B 是 C 的对照格：B 出声而
C 静默 ⇒ 11.19 MB blob 被钉成唯一变量；B 也静默 ⇒ 死因不需要 blob，需要重读
[BOOT-DEATH-BISECT.md](BOOT-DEATH-BISECT.md) §5 那条「console gate 之前不可达」的
静态论证。C 先飞（它同时覆盖那里的 C1 判据与本问题），B 后飞。

## 7. 仍然开着的口子（本文不关闭它们）

1. **DXE pool 碎片化**（:558 → :607 的顺序）：65.9 MB 整块 `AllocatePool`
   之后才申请 4.5–4.75 GiB 连续窗口。blob 使 pool 占用多 11.27 MB，
   可能改变 `AllocateWindow` 看到的最大 run。这条只能靠上机的
   「NO WINDOW」行或 C1/C2 判据分辨，静态无解。
2. **105 MB 家族的成功不能反证 65.9 MB 必成**：105 MB 在 `__DATA`
   （可写、按需填零），65.9 MB 的超额在 `__TEXT`（整段只读映射，
   页表路径 :1415 不同）。段属性不同，静态不能互相担保。
3. **PWF2 头失配**（§1）说明 blob 打包链有第二个作者；在头与 payload
   一致之前，任何「固件加载成功」的运行期判断都要先核对一致性。

## 8. 证据清单

| 事实 | 证据 |
|---|---|
| 段表逐段扫描（含 105 MB 家族） | `E:/k60-work/scratch/refmine/probe-segs.py`、`probe-seg.py`、`probe-allwifi.py`（46 张 boot.img 汇总） |
| 窗口值逐镜像 | `probe-window3.py`：ADT 属性 `darwinboot-memory-size` 解码——thermal/springboard/gpu/base/touch=0x130000000（4.75 GiB）alive；brightness-4=0x120000000（4.5 GiB）alive；mhi3=0x130000000 死；mhi4/mhi5/z0=0x120000000 死或未飞；a2/t1/t1c=0x130000000 未飞 |
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
