# DarwinBoot 内存三节点与「一次上机分开 pool 通道」的判据

Written 2026-11-15 at the Lead's request (reply md item 3, main=3e59ba5). Three
questions are answered: (1) the three memory nodes line by line — what each one
returns and prints on failure; (2) the window arithmetic reconciled against
`board.toml` owned_memory_size and the 5120 MiB arena, with the bt 106.5 MB
alive/dead pair as the ruler; (3) the one-flight discriminator that separates
the pool/window channel from everything else, including a firmware-print
proposal for the Lead to approve. **Nothing here is built or flown.**

## 0. 结论先行

- 三处节点在本检出是 `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c`（969 行）；
  Lead 引用的 :558/:607/:656 来自已不存在的旧路径，映射为 ReadFile 定义
  :85-127（调用 :699）、AllocateWindow 定义 :452-513（调用 :751）、
  FreePool(Image) :818（成功路径）与 :903（Fail 路径）。
- 「窗口分配失败」在固件日志上是**一行独一无二的 `NO WINDOW … BIG RUN …`**
  （屏幕第 0 行）+ Logger 的 `DARWINBOOT: no window …` + 最多 8 行 `FREE …`；
  「窗口成功但内核静默」则必然出现过 `\fDARWINBOOT: hand-off to the kernel`
  大字块。两者互斥，一次上机即可分开。
- 算术：窗口 4.5 GiB 只能从 arena（0x900000000、5120 MiB）出；内核镜像（两份
  副本）进 DXE Heap（384 MiB）而不进 arena。arena 级余量 512 MiB。静态算术
  **不预测**任何一张已飞镜像 NO WINDOW——bt 非单调对（同 106,541,056 B 一活一死）
  也说明尺寸不是变量。
- 缺口：这些行走屏幕/Advanced Logger，不走 usblog 控制台（它在 bsd_init 之后才
  起），所以 0 字节的 capture.json 对两种死法长得一样。判据在 §5。

## 1. 谁在跑：FD 接线与行号映射

`mondrian.dsc:120` 与 `mondrian.fdf:89` 都 INF
`DarwinBootPkg/Driver/DarwinBoot.inf` → 实际编译的是
`Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c`。
BLOB-RESIDENCY.md 引用的 `drivers/DarwinBoot22/…` 在本检出不存在。

| Lead 引用 | 当前文件 | 内容 |
|---|---|---|
| :558（AllocatePool 整块） | :85-127（ReadFile 定义），调用点 :699 | 内核整镜像 `AllocatePool (*Size)` |
| :607（4.5 GiB 连续窗口） | :452-513（AllocateWindow 定义），调用点 :751 | `AllocatePages (AllocateAddress, …)` |
| :656（FreePool(Image)） | :818（成功路径）；:903（Fail 标签） | 窗口拿到、段拷贝完之后才释放 |

## 2. 三处节点逐行

### 2.1 ReadFile（:85-127；调用 :697-699）

调用：`ReadFile (Root, Request->KernelPath, SIZE_128MB, &Image, &ImageSize)`，
`SIZE_128MB` = 134,217,728（`DarwinBoot.h`）。

- :98 `Root->Open (…, EFI_FILE_MODE_READ, 0)` — 失败直接返回（`EFI_NOT_FOUND` 等）。
- :103-105 先 `GetInfo (…, NULL)` 探长度（预期 `EFI_BUFFER_TOO_SMALL`）。
- :107 `Info = AllocatePool (InfoSize)` — 失败 `EFI_OUT_OF_RESOURCES`。
- :111 `(Info->Attribute & EFI_FILE_DIRECTORY) || (Info->FileSize == 0) || (Info->FileSize > Limit)`
  → `EFI_BAD_BUFFER_SIZE`。mhi5/z0/t2 的 117,305,344 与上限差 16,912,384 B。
- :116 `*Data = AllocatePool (*Size)` — **整镜像一次进 DXE pool**；失败
  `EFI_OUT_OF_RESOURCES`。
- :120-121 `File->Read`；`Actual != *Size` → `EFI_DEVICE_ERROR`。
- :124 失败时 `FreePool (*Data)` 并置 NULL。

打印：**ReadFile 自身不打印任何东西**。失败时 Boot() 的 Fail 标签（:898-913）
在屏幕第 0 行画 `BOOT FAILED READ KERNEL <status>`（Stage=`L"READ KERNEL"`
在 :697 就画上了），再 `Print (L"DARWINBOOT: boot refused: %r; firmware
retained\n")`，释放全部指针后返回 BDS（回到 fastboot）。

关键背景：UniXNU 侧对这个镜像还有一份 `AllocateZeroPool` 整镜像副本，且它的
`FreePool` 在 DarwinBoot 拿完窗口之后（MemoryMapLib.c 的 DXE Heap 注释）——
**窗口申请那一刻，pool 里躺着两份内核镜像**（§4 对账用这个量）。

### 2.2 AllocateWindow（:452-513；调用 :750-752）

- :473 `GetMap` 取内存图；失败原样返回。
- 循环 :478-489 只扫 `EfiConventionalMemory`；:479 `RunEnd` 合并相邻
  conventional 描述符；:481-482 记 `BestBytes/BestStart`（全图最大 run）。
- :482-483 `Candidate = ALIGN_VALUE (start, 2 MB) + (Kernel->Base & 0x1FFFFF)`。
- :484 `(Candidate < start) || (End < Candidate) || (End - Candidate < WindowSize)`
  三段式拒绝。
- :485 `gBS->AllocatePages (AllocateAddress, EfiLoaderCode, EFI_SIZE_TO_PAGES (WindowSize), &Candidate)`。
- 全部失败 → `EFI_OUT_OF_RESOURCES`。

失败打印（**只在失败路径出现，成功时一行都没有**）：

1. 屏幕第 0 行 `NO WINDOW %lx BIG RUN %lx @ %lx`（WindowSize、BestBytes、BestStart，:491-493）；
2. Logger（DEBUG_ERROR）`DARWINBOOT: no window 0x%lx, biggest run 0x%lx at 0x%lx`（:498-499）；
3. 最多 8 行 `FREE %lx + %lx`（屏幕）+ `DARWINBOOT: free 0x%lx + 0x%lx`
   （Logger）——只列 conventional 且 ≥0x400 页（≥2 MiB）的块（:501-507）。

随后 Fail 标签画 `BOOT FAILED PRIMARY RAM 0000000000000009`
（`EFI_OUT_OF_RESOURCES` = 9，Stage=`L"PRIMARY RAM"` 在 :750），
`Print (L"DARWINBOOT: boot refused: Out of Resources; firmware retained\n")`。

WindowSize 来源：:721 AdtNode 从 ADT 读 `darwinboot-memory-size`
（:300-302，`DarwinWindowSizeValid` 上限 8 GiB）；:723 为 0 时回退
`WINDOW_SIZE`（SIZE_256MB）。本机该值 = `board.toml:235`
`owned_memory_size = "0x120000000"`（4.5 GiB；2026-11-14 从 4.75 GiB 降下来）。

### 2.3 FreePool(Image)（:818 成功路径；:903 Fail 路径）

成功路径的完整顺序（窗口申请在前、释放在后）：

1. :750-752 `PRIMARY RAM` → `AllocateWindow`（**此刻两份镜像还在 pool 里**）；
2. :756-765 AudioAddress 16 页（`AllocateMaxAddress, EfiReservedMemoryType` —
   注意是 Reserved 类型，**不消耗 conventional**，不会啃窗口候选）；
3. :767-775 Args/Tree/Ramdisk/TrustCache/Trampoline 布局，:775
   `Used > WindowSize - BLOCK_SIZE` → `EFI_BAD_BUFFER_SIZE`；
4. :777-783 `COPY PAYLOAD`：`ZeroMem` 整个窗口 + 逐段 `CopyMem`；
5. :794-795 `Args->MemorySize = WindowSize; MemorySizeActual = WindowSize`；
6. :804-813 树/ramdisk/trustcache 拷进窗口；
7. :816 `FreePool (TrustCaches)`；:818 `FreePool (Image); Image = NULL`；
   :819 `FreePool (Tree)`；:820 `FreePool (TreePath)`。

Fail 路径（:898-913）释放同一组指针（:902-906），回滚 Owned 页（:907-909）、
AudioAddress 16 页（:910）、窗口页（:912），打印
`DARWINBOOT: boot refused: %r; firmware retained`。

## 3. 两种死法在固件日志上长得不一样在哪

| 步骤 | 窗口分配失败 | 窗口成功、内核静默 |
|---|---|---|
| 屏幕第 0 行 | `READ KERNEL` → `PRIMARY RAM` → **`NO WINDOW 120000000 BIG RUN <x> @ <y>`** → `FREE …`（≤8 行） | `READ KERNEL` → `PRIMARY RAM` → `COPY PAYLOAD` → `MEMORY MAP` → `EXTRA RAM` → `READY TO ENTER` |
| Logger | `DARWINBOOT: no window 0x120000000, biggest run 0x<y> at 0x<z>` + `free …` 行 | （无 no-window 行） |
| 屏幕大字块 | 不出现 | `\fDARWINBOOT: hand-off to the kernel`（:861，form feed 清屏）+ `kernel va/pa`、`entry words`、`CurrentEL …`（:861-874）——内核从此不画任何东西时，**这就是留在屏幕上的最后内容** |
| 失败横幅 | `BOOT FAILED PRIMARY RAM 0000000000000009` + `boot refused: Out of Resources; firmware retained` | 无（横幅只在 goto Fail 时画） |
| 额外成功行 | 无 | `DARWINBOOT: ARM64 va=… pa=… args=… entry=… owned=…`（:846）、`video base=…`（:848）、`command line: %a`（:850）、`inputs validated; exiting boot services`（:851）、`%u owned RAM banks, %lu MiB usable…`（:839） |

一句话：**`NO WINDOW` 行只在窗口/池失败时出现；`hand-off to the kernel`
大字块只在窗口分配成功后才可能出现。** 两者互斥——一次上机就能分开。

现状缺口：这两类行都走屏幕与 Advanced Logger（Log Buffer 0xA7905000，
RtData 32 KiB，MemoryMapLib.c），**不走 usblog 控制台**——`k60_usblog_start()`
在 bsd_init 用户态线程起来之后才打（patch 0300-k60-usblog-ep0），所以窗口阶段
死在它之前时，0 字节的 capture.json 对两种死法长得完全一样
（bytes=0、port-not-observed、fastboot-return），这正是 §5 要补的采集通道。

## 4. 窗口算术对账（bt 106.5 MB 活/死对照当标尺）

输入（全部实测）：

| 量 | 值 | 来源 |
|---|---|---|
| arena（XNU High Arena） | 0x900000000 + 0x140000000 = **5120 MiB** 单个 conventional run | MemoryMapLib.c |
| 窗口 | 0x120000000 = **4608 MiB** | board.toml:235 → ADT → DarwinBoot :721 |
| DXE Heap | 0xC7000000 + 0x18000000 = **384 MiB** conventional | MemoryMapLib.c |
| Kernel 保留 | 0xBB000000 + 0x0C000000 = 192 MiB **Reserved** | MemoryMapLib.c（非 conventional，窗口永远不用它） |
| 其它 | Log Buffer 32 KiB RtData、ramoops 4 MiB WT、ABL Staging 253 MiB Reserved | 均非 conventional，不进窗口候选 |

推导：

1. **窗口只能从 arena 出**。DXE Heap 384 MiB 装不下 4.5 GiB 连续请求（:484 的
   `End - Candidate < WindowSize` 直接跳过）；其余 conventional 块更小。
   Candidate = 0x900000000 + 0x4000（2 MB 对齐 + Base 偏移 0x4000），
   End − Candidate = 0x13FFFC000 = 5,368,692,736 ≥ 4,831,838,208。
   **若 arena 在窗口申请瞬间完好，窗口必成**；arena 级余量 = 536,854,528 B ≈ 512 MiB。
2. **内核镜像不进 arena**。ReadFile 的 `AllocatePool (*Size)`（:116）与 UniXNU
   的 AllocateZeroPool 副本都从 DXE Heap 取页。bt 标尺：2 × 106,541,056 =
   213,082,112 B（203.2 MiB）；z0/mhi5/t2：2 × 117,305,344 = 234,610,688 B
   （223.8 MiB）；mhi4：2 × 65,978,368 = 125.8 MiB。384 MiB Heap 减去 UEFI
   基线（菜单栈、树/trustcache/initrd 的 pool 副本等）后三者都放得下——
   **静态算术不预测任何一张已飞镜像 NO WINDOW**。
3. **什么时候才会 NO WINDOW**：只有 pool 需求溢出 Heap、继续从 arena 取页，
   且把 5120 MiB run 啃掉超过 512 MiB，最大 run 才会跌破 4608 MiB。溢出量离
   这个阈值还很远——所以「pool 通道」在静态算术上同样没有落脚点；它保持为
   嫌疑的唯一理由是我们从未在屏幕上核对过 `NO WINDOW` 行是否出现过（§5）。
4. **窗口留给内核的空间**：`Used` = 各段 FileSize 和 + args + 树 + ramdisk +
   trustcache + trampoline（:767-776）。bt 标尺的段 span 约 66-68 MiB，即使
   Used 取 200 MiB 上界，留给内核的仍是 ≈4.4 GiB——窗口不是瓶颈；真正的窄口
   只有「arena 在窗口申请瞬间是否完整」这一处。

**非单调标尺（Lead 亲飞，payload kernel 字节为 mcopy 实测，manifest sha 佐证）：**

| flight（usblog 目录） | 镜像 | payload kernel 字节 | series | 结果 |
|---|---|---|---|---|
| usblog-20261115-140927 | bt-s4b-20261115b | 106,541,056 | 228 b31855c9… | **alive**（console 213,434 B） |
| usblog-20261115-163144 | bt-s4b-20261115c | **106,541,056（同尺寸）** | 229 67baff88… | **silent**（0 B，fastboot-return） |
| usblog-20261115-162553 | bt-s4c-20261115c | 105,508,864 | 229 67baff88… | **alive**（console 245,222 B） |

同 106,541,056 B 一活一死（Lead：series 228→229 只多 1 个补丁），同 series 229
的另一个 flavor 又活——**尺寸/窗口阈值模型对 117 MB 与 65.9 MB 都不成立**。
变量在 228→229 的那一个补丁 × flavor 交互，或一个非单调通道（pool 基线随图
漂移、DART/中断/时钟初始化顺序）。两者都只能靠 §5 的一次上机判读分开。

## 5. 一次上机分开 pool 通道的判据

**已存在、且只在窗口/池失败时出现的行**（不改固件就能判读）：

1. 屏幕第 0 行 `NO WINDOW … BIG RUN … @ …`（:491-493）；
2. Logger `DARWINBOOT: no window 0x…, biggest run 0x… at 0x…`（:498-499）；
3. `FREE … + …`（≤8 行，:501-507）；
4. `BOOT FAILED PRIMARY RAM 0000000000000009` + `boot refused: Out of
   Resources; firmware retained`（:898-913）。

判读规则：一次上机后看到上面任何一行 ⇒ **pool/窗口通道实锤**，回到窗口/arena
调参；看到 `\fDARWINBOOT: hand-off to the kernel` 大字块且没有 NO WINDOW ⇒
**窗口分配成功、死在 hand-off 之后**（内核侧/驱动体静态路径/DART-中断-时钟），
pool 通道被一次排除。

采集通道（两个零固件改动选项）：

- **A 全程录屏/拍照**：z0 全程约 86 s（BLOB-RESIDENCY §10.1 记录），boot 期间
  屏幕依次 READ KERNEL → PRIMARY RAM → COPY PAYLOAD → READY TO ENTER →
  hand-off 大字块；失败帧在 fastboot 返回后可能仍留在屏上。零固件改动，一次
  上机即出结果。
- **B Advanced Logger**：失败返回 fastboot 后进 UEFI 菜单 Tools → Advanced
  Logger，翻 Log Buffer（0xA7905000）里的 DEBUG_ERROR 行。**该缓冲跨 fastboot
  往返是否保留未经实测**——需要一次带屏幕核对的验证飞行。

**固件改动提案（若 A/B 都不可行，交 Lead 审批；本轮不建图）**：

在 `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c` 加一个
`WriteBreadcrumb (CONST CHAR16 *Tag)`：把 ≤32 字节的 tag 顺序追加写入 ramoops
区（0xA7000000、4 MiB、WriteThrough，MemoryMapLib.c 已声明；写入前用
GetMemoryMap 找到该描述符并按其属性映射，不裸写 volatile 指针）。调用点与内容：

| 插入点 | tag | 读到它说明 |
|---|---|---|
| :699 `ReadFile` 成功后 | `RD` + ImageSize | 镜像进 pool 成功 |
| :751 `AllocateWindow` 成功后 | `WINDOW OK` + Address + BestBytes | 窗口分配成功 → pool 通道被一次排除 |
| :493 NO WINDOW 分支 | `NO WINDOW` + BestBytes | 窗口失败 → pool 通道实锤 |
| :899 Fail 标签 | `FAIL` + Stage | 卡在哪个 stage（读最后一笔） |
| :874 hand-off DEBUG 块后 | `HANDOFF` | 已 ExitBootServices 交接 → 死因全在内核侧 |

读法：飞行后正常开机进 Android 一次，读 `/sys/fs/pstore/console-ramoops`
（或 `dmesg-ramoops`）。一趟上机 + 一趟 Android 开机 = 死点定位。前提与风险：
ramoops 是 Android pstore 契约区，正常 boot 时 Android 只读它（崩溃时才写），
固件写入必须用 MemoryMapLib 同款 WriteThrough 映射，且要确认 fastboot boot
这条路径不会先清掉该区（需要一次空跑验证残留）。

与 BOOT-DEATH-BISECT.md §7 的关系：C1/C2 飞 `wifi-20261116a2`（65.9 MB、
pong_wifi=0、4.75 GiB）时，C2 的「体积/驻留是死因」仍分不开「窗口没拿到」与
「拿到窗口后内核死」——本节的 NO WINDOW / hand-off 判读正好补上这一层；若先
飞 a2，建议同趟执行 A（录屏）判读。

该计划里的 trial 级 `wifi-20261116a2` 已被正式 C 格取代：
`wifi-20261116c0`（66 MB、`pong_wifi=0`、带 series 指纹，
`BOOT-DEATH-SUSPECT.md` §3c）才是 C1/C2 的正式镜像。构建 c0 暴露了
fresh-board fakeroot 缺陷（新 board 目录永远拿不到 `Availability.h` 家族，
且 `check-build-env.py:27` 硬编码 `mondrian` 目录导致 P-185 假绿）——已落
**P-206**（main `c97a4cf`，snap-r197）。c0 上机时同趟执行 A（录屏）：
alive/silent 二分直接分开「驱动扳机」与「pool/窗口通道」两条嫌疑。

**c0 飞行结果（2026-11-15 21:32）：silent。** 证据
`usblog-20261115-213221`（console.log 0 字节、`port-not-observed`、
`fastboot-return`、判 `silent` / exit 2），`boot.img`
`25c9821510…`、args 末项 `pong_wifi=0`。这一趟没有留下 NO WINDOW 与
hand-off 两个互斥读数（回复里没有录屏判读），所以 pool 通道**没有被这次
飞行排掉**；但它的算术变弱了：4.5 GiB 窗口、内核 66,002,944 B（62.94 MiB）、
固定开销 177 MiB ⇒ 余量约 272 MiB，而同机同日 106.5 MB（bt-s4b-20261115b）
与 129.0 MB（ADSP 载体）内核在**同一窗口**上都能进桌面。占用更少反而死，
说明单靠 pool 占用解释不了 c0 的 silent；剩下的对照面是内核内容布局
（`BOOT-DEATH-SUSPECT.md` §3d：`__TEXT` 12,992,512 / `__const` 11,767,510
是唯一超出非 wifi 内核的段）。下一张图若仍走 pool 判据，必须带 A 通道录屏。

## 6. 证据清单

- 飞行：`usblog-20261115-140927`（bt-s4b-20261115b，alive）、
  `usblog-20261115-163144`（bt-s4b-20261115c，silent）、
  `usblog-20261115-162553`（bt-s4c-20261115c，alive）、
  `usblog-20261115-135859`（z0，silent）、
  `usblog-20261115-161102`（t2，silent）、
  `usblog-20261115-213221`（wifi-20261116c0，silent，66,002,944 B 内核）。
- 源码：DarwinBoot.c :85-127 / :452-513 / :697-699 / :750-752 / :767-783 /
  :794-795 / :816-820 / :839 / :844-894 / :898-913；MemoryMapLib.c 的
  DXE Heap / XNU High Arena / Kernel / Log Buffer / ramoops / ABL Staging；
  board.toml:228-235；WindowSize.h。
- 构建：`wifi-20261116c0`（C 格，66,002,944 B 内核）与 fresh-board fakeroot
  缺陷 → P-206（main `c97a4cf`）；见 BOOT-DEATH-SUSPECT.md §3c。
- 姊妹文档（k60-refmine 树）：BLOB-RESIDENCY.md §2/§7.1/§7.4/§10.3/§10.4；
  BOOT-DEATH-BISECT.md §6.3/§7（C1/C2/C3/C4 与 judge-wifi-boot.py）。
