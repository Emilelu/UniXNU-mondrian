# K60 内存窗口定性：4 GiB 的来源、上限与 12 GiB 可行性（2026-11-02，只读审计）

> **本文件 = 内存窗口专题的权威源（SSOT）**。其余文件（ISSUES/HISTORY-LEDGER/READING-LIST/INDEX）提到内存窗结论只留一句 + 指向本文；相关坑见 PITFALLS-FROM-HISTORY 第 5 条，阶梯试验记录见 DECISIONS/ISSUES 对应编号。

> 范围：不改 `/tmp/k60build`、不动 git 仓库、不上机、不构建。所有引用为 WSL/Windows 只读文件。
> 回答的问题：4 GiB 是硬限制还是我们自己设的限制；12 GiB 全量可用需要改什么。

## 0. 结论（A/B/C）

| 命题 | 判定 | 一句话理由 |
|---|---|---|
| 当前 4 GiB | **A（我们自己设的限制）** | 4 GiB 来自 `board.toml` 的 `owned_memory_size = "0x100000000"`，一处参数；硬件与 XNU 都不含 4 GiB 上限 |
| 提到 ~5.5–7.5 GiB | **A + 一次未定性排障** | 几何上放得下（最大连续空闲 ~8.65 GiB），但 7 GiB 实测试过「内核零输出」，根因未定位，必须先跨过这个坎 |
| 12 GiB 全量 | **C + B** | C：单窗口物理不可能——6 个不连续 bank + 4–32 GiB 共 28 GiB 无 DRAM 空洞；B：要吃下零散 bank 需给 XNU arm64 加多段物理内存管理（现仅支持单区间，x86 的 `pmap_memory_regions[]` 在 arm64 不存在），无先例、工作量大、收益仅 ~3 GiB 碎段 |

**核心修正**：旧结论「12 GiB 物理不可能」对**单一连续窗口**成立，但其表述混淆了两件事——4 GiB 不是硬限制；真正的上限链是「单区间架构 × 物理连续段长度 × 加载器 8 GiB 解析上限」，当前可用上限约 **7–7.5 GiB**（需先解决 7g 静默失败）。

---

## 1. Q1：4 GiB 的来源（`mem=4096` 不是 boot-arg）

**没有任何脚本/boot-arg 加 `mem=4096`。** `kernel_args` 里没有 mem 类参数（`UniXNU-mondrian/board.toml:125`）。屏幕上的 `mem=4096 actual=4096 managed=4096` 是 K60 自加探针的打印，数值链路：

| 值 | 来源 | file:line |
|---|---|---|
| 窗口尺寸 | `board.toml` `[payload."adt"] owned_memory_size = "0x100000000"` | `~/hackios/UniXNU-mondrian/board.toml:164` |
| → 写进 ADT | `devicetree.py` 校验 256 MiB–8 GiB、2 MiB 对齐后 emit `chosen/darwinboot-memory-size` | `/tmp/k60build/scripts/unixnu/devicetree.py:318-322` |
| → 加载器读 | `AdtNode()` 匹配 `darwinboot-memory-size`（须在 /chosen 直下），过 `DarwinWindowSizeValid` | `~/hackios/UniXNU-mondrian/drivers/DarwinBoot22/DarwinBootPkg/Driver/DarwinBoot.c:249-252, 269-272`；`WindowSize.h:6-8` |
| → boot_args | `Args->MemorySize = WindowSize; Args->MemorySizeActual = WindowSize;` | `DarwinBoot.c:636-637` |
| → XNU | `gPhysBase = args->physBase; mem_size = (gPhysBase+args->memSize)&~PAGE_MASK - gPhysBase; mem_actual = args->memSizeActual ?: mem_size` | `xnu-work/osfmk/arm64/arm_vm_init.c:1841-1859` |
| → 屏幕三数 | `k60_dbg_mem_mib/actual_mib/phys_mib = args->memSize/mem_actual/mem_size >> 20` | `arm_vm_init.c:1896-1898`；打印点 `osfmk/kern/task.c:7531`（K60RV 行）、`iokit/Kernel/MiniIOMobileFramebuffer.cpp:1072` |

- `actual` = `boot_args->memSizeActual`（加载器恒等于窗口）；`managed` = `mem_size`（窗口按页向下取整）。
- **去掉 `owned_memory_size` 的默认值**：`DarwinBoot.c:20` `#define WINDOW_SIZE SIZE_256MB` + `:580` `if (WindowSize == 0) WindowSize = WINDOW_SIZE` → **256 MiB**。
- XNU 侧 cap 链：`arm_init.c:611-617`（`maxmem` boot-arg 或 `hw.memsize` PE 默认，两者均未设置 → 无 cap）；`arm_vm_init.c:1922-1927`（仅当传入非 0 cap 才截断）。
- 预留开关：`k60_capmanaged=1` 可把 managed 压到 `mem_actual`（`arm_vm_init.c:1912-1918`），默认关；当前加载器下是 no-op。

## 2. Q2：ADT 与真机 12 GiB 布局

### 现役 ADT（`4g-quiet/extracted/verify.adt`，14,672 字节，本次实解）

**没有任何 memory 节点**。内存信息只有三个标量（`/chosen` 直下）：
- `dram-base = 0x900000000`、`dram-size = 0x140000000`（5 GiB arena 声明）
- `darwinboot-memory-size = 0x100000000`（4 GiB 窗口）
- `/chosen/memory-map` 里只有 `TrustCache` 占位（16 字节全零）

生成链：`devicetree.py:302-304` 强制「DTS 恰一个 memory 节点、恰一段 reg」→ 写入 dram-base/size。即「ADT handoff requires one contiguous DRAM range」是**工具链硬约束**。

注：用户提到的 `mondrian.ours.dtb` 在 `~/k60-archive/2026-11-02/misc/mondrian.ours.dtb`，其 `/memory@80000000` 为 `base=0x80000000 size=0x300000000`（12 GiB 单段）——这是**早期手工编写、未实测**的值，正是 `measured-high4g/build-verification.json` 里被替换掉的 `dram-base old=0x800000000→新 0x900000000`、`dram-size old=0x300000000→新 0x140000000` 的旧值来源。现役 ADT 由 `dts/mondrian.dts:29-32`（memory@900000000，5 GiB）生成，不是从该 dtb 转的。

### 真机 DRAM 布局（serial 6033dbec，Android 实测）

6 个 bank（`reports/live-6033dbec-memory-reg.bin`，MEASURED-HIGH-WINDOW-2026-11-02.md 已解码，sha256 `729587c3…`）：

| Base | Size | End | 相对 4 GiB |
|---|---|---|---|
| 0x80000000 | 0x6a000000 (1.66 GiB) | 0xea000000 | 低 |
| 0xf4600000 | 0xba00000 (186 MiB) | 0x100000000 | 低 |
| 0x800000000 | 0x37500000 (885 MiB) | 0x837500000 | **高** |
| 0x837b00000 | 0x1e00000 (30 MiB) | 0x839900000 | **高** |
| 0x840000000 | 0xc0000000 (3 GiB) | 0x900000000 | **高** |
| 0x900000000 | 0x180000000 (6 GiB) | 0xa80000000 | **高** |

- **[0x100000000, 0x800000000) = 28 GiB 完全无 DRAM**（空洞）；[0x839900000, 0x840000000) 还有 103 MiB 小空洞。
- 唯一长连续段：0x840000000–0xa80000000（9 GiB，两个 bank 首尾相接）。
- **4 GiB 以上的保留区**（`reports/live-6033dbec-iomem.utf8.txt:322-330`，iomem 只标 "reserved"、未标属主）：`a69b78000–a77dfffff`（~232.5 MiB，主块）+ `a77e0a000–a77e41fff` 六个碎片 + `a77e42000–a7fffffff`（到段顶）。→ 高段可用上限 **0x840000000..0xa69b78000 ≈ 8.65 GiB**。
- 低段保留区（FDT `/reserved-memory`，全在 <0x100000000）：modem `mpss_region 0x8bc00000+306 MiB`、ADSP `0x9fd00000+49 MiB`、CDSP `0x89900000+32 MiB`、SLPI `0x88000000+25 MiB`、QTEE `0xe9b00000+5 MiB`、HYP `0x80000000+6 MiB`、帧缓冲 `splash 0xb8000000+43 MiB` 等（全表见 `reports/mem-audit-dump2.txt`）。modem/GPU/其它核的保留**全在低段**；高段 9 GiB 内只有段顶那 ~354 MiB。

## 3. Q3：7 GiB / 8 GiB 失败的原始证据与定性

### 8 GiB（候选 `archive/2026-11-02/candidates/8g`，窗口=arena=8 GiB @0x840000000）

- 原始屏幕行**未找到归档**；文档级证据：`MEASURED-HIGH-WINDOW-2026-11-02.md:135-137`「loader returned to the UniXNU menu because DXE holds part of the arena, leaving no contiguous 8 GiB run」；`reports/boot7g-loader.txt:20-21` 同述。
- 机制可复现且代码可指：`DarwinBoot.c:422-478 AllocateWindow()` 要求**单段连续 ConventionalMemory ≥ 窗口**；失败时打 `NO WINDOW <size> BIG RUN <bytes> @ <addr>`（`:461-464`）并列出 FREE 段 → 返回菜单。旁证：`F:\Redmi K60-20190100-000545.log:34-35`（无高 arena 的旧固件）`DARWINBOOT: no window 0x100000000, biggest run 0x13138000 at 0xC7000000`——同一失败形态；同时证明 RamPartitionDxe 不把 DRAM bank 枚举为 Conv，**Conv 只有 MemoryMapLib 里两条**（DXE Heap 384 MiB + XNU High Arena）。
- **定性：窗口分配失败（loader 侧），XNU 未被尝试。** 属「映射没建立」中的「根本没能分配」，非 pmap/zone 问题。

### 7 GiB（候选 `7g`，窗口 7 GiB @0x840000000，arena 8.625 GiB）

原始证据 `reports/boot7g-loader.txt`（2026-11-02 17:47 屏摄转写，sha 与候选 JSON 一致）：

```
kernel  va 0xfffffff004420000  pa 0x8400200000     # 转写位数存疑，实际应为 0x840020000
args    pa 0x8433E8000  window 0x1c0000000 bytes   (= 7 GiB, ACCEPTED)
owned trampoline pa 0x843F00000 (186 bytes)
HANDOFF EXIT RETURN 0000000000000000               # ExitBootServices 成功
green bar at the top => DarwinEnter trampoline ran # 仅证明 trampoline 执行
```

之后**内核零输出**（`dts/mondrian.dts:23-24` 注释与 MEASURED 文档一致记载）。

- **能排除的类别**：不是「窗口没建立」（分配/清零/ExitBootServices/trampoline 全过）；不是「pmap/PTE 上限」「zone/页表内存不足」（那些在控制台起来之后才会触发，且会打印 panic）。
- **不能排除**：trampoline → 内核入口 → 控制台可见首行之间任意点挂死/复位。注意本条 16.6.1 流水线**没有编进 stage-bar 入口探针**（`package-textonly.py` 无 entry-probe 步骤；board.toml 提到的蓝/紫条属于另一探针），所以「只有绿条」无法区分「内核入口没执行」与「执行了但死在控制台之前」。
- 混杂因素（必须声明）：7g/8g 内核 sha `1a18c6a2`（KX!+textonly），该内核在 4 GiB 几何下的候选 `4g-diag` **未实测**（`build-verification.json` `hardware_tested:false`），不能排除内核自身回归。
- 已知同形机制：pong 的 0172 发现——窗口覆盖 AP 译码不到的「DRAM」时，首次触碰即无 panic 无输出挂死（`arm_vm_init.c:1875-1884` 注释）。但 7g 窗口全段都在 Android「System RAM」内（iomem 320-322 行），此机制**无证据支持**。
- **定性：未定性（"查不到"）。** 现有证据只能定到「trampoline 后、控制台输出前」。

## 4. Q4：sheng 逐项差异（关键：sheng 没有 8 GB 证据）

| 项 | sheng（小米平板 6S Pro, SM8550, 8 GB） | mondrian（K60, SM8475, 12 GB） |
|---|---|---|
| os_profile / ABI | iPadOS 17.7.11 / Darwin 23，加载器 `drivers/DarwinBoot` | iPadOS 16.6.1 / Darwin 22，`drivers/DarwinBoot22` |
| DTS memory 节点 | `memory@80000000`，**2 GiB**（`dts/sheng.dts:9-12`） | `memory@900000000`，**5 GiB**（`dts/mondrian.dts:29-32`） |
| `payload.dram_size` | `0x80000000`（2 GiB，== DTS） | `0x140000000`（5 GiB，== DTS） |
| `owned_memory_size`（窗口） | **`0x130000000` = 4.75 GiB**（`board.toml:85`） | `0x100000000` = 4 GiB（`board.toml:164`） |
| boot-args 中的内存项 | 无 mem 类参数（`board.toml:74`） | 无（`board.toml:125`） |
| pmap/内存补丁 | 未找到内存相关项 | `k60_capmanaged`（默认关）+ K60 MEM/K60RV 打印 |
| 实机内存统计 | **未找到**——memory area 只有 source 级证据（`porting.toml` memory area）；GPU 130fps/WiFi/音频为 device 级证据，但**没有 managed-memory 数字** | 有：屏显 `mem=4096 actual=4096 managed=4096`、free_pages 样本 |

**要点**：sheng 证明了 UniXNU 在 >4 GiB（4.75 GiB 窗口）下能到 GUI——**4 GiB 不是 UniXNU 的原理上限**；但 sheng 从未把 8 GB 全量交给 XNU（窗口 4.75 GiB、DTS 只声明 2 GiB）。「sheng 8 GB 跑通」不能当作「8 GB 全用上」的证据。窗口 ≤8 GiB 的校验（`devicetree.py:320-321`）对两个设备相同；sheng 侧加载器的 `WindowSize.h` 本地无副本（uefi-sheng 未 clone），**未验证**，但其窗口 4.75 GiB 通过了同一 host 端校验。

## 5. Q5：XNU arm64 侧在 >4 GiB 时的真实要求

基于 `xnu-work`（xnu-8796.141.3 + PONG 补丁）：

1. **单区间**：`arm_vm_init.c:1841-1857`——`gPhysBase/mem_size` 来自 boot_args 单一 `{physBase, memSize}`。`pmap_memory_regions[]`/`pmap_memory_region_count` 只存在于 `osfmk/i386`、`osfmk/x86_64`；`pmap_add_memory_region`、`ml_static_mem_provider` 在全树**未找到**（arm64 无多段内存入口）。
2. **位宽/PTE**：arm64 PTE 64 bit；加载器实测打印 `ID_AA64MMFR0_EL1 0x1201100103111111`（PARange 足够，4 KiB granule 支持）。`pmap_map_bd`（`osfmk/arm/pmap/pmap.c:1866`，`io_map.c:114` 调用）只用于设备 IO 映射，与 >4 GiB 无关。
3. **唯一尺寸类硬闸**：`arm_vm_init.c:1928-1930`，`mem_size >= (VM_MAX_KERNEL_ADDRESS-VM_MIN_KERNEL_ADDRESS)/2` 才 panic；按 `osfmk/mach/arm/vm_param.h:231-236` 本配置内核 VA 跨 ~112 GiB → 阈值 ~56 GiB。7–12 GiB 远低于此。
4. **PE_state**：`arm_init.c:781-790` 只把 `dram-base/dram-size` 读进 `gDramBase/gDramSize`（信息性；唯一消费者 `vm_param.h:302 is_dram_addr`）。7g 时 dram-size(8.625 GiB) > memSize(7 GiB) 的不一致**不进入** mem_size 计算。
5. **iOS 真机 6/8 GB 的处理**：结构上无特殊分支——Apple 平台 DRAM 单段连续，iBoot 直接给一个大 memSize；XNU 侧预期大内存的证据如 `osfmk/kern/startup.c:974`（≥16 GiB 的 serverperfmode 分支）。**XNU 侧不存在 4 GiB 墙。**
6. **区带/页表开销**：vm_page 元数据随 mem_size 线性增长（8 GiB@16K 页 ≈ 52 万页，元数据 ~50 MiB 级），从窗口内静态区出，量级安全。

## 6. Q6：要做到 >4 GiB / 12 GiB 需要改什么 + 最小验证路径

### 要改的清单

| 目标 | 改动 | 性质 |
|---|---|---|
| ~4.5–5 GiB | 只改 `board.toml` `owned_memory_size`（≤ 0x13FE00000，2 MiB 对齐）+ 重打 payload/bootimg | **纯参数（A）**，现 5 GiB arena 不动 |
| 5.5–7.5 GiB | `owned_memory_size` ↑ + `MemoryMapLib.c` arena 扩到 [0x900000000, 0xa69b78000) 内（基址不动约 5.65 GiB 顶）或回 0x840000000 基址（~8 GiB 顶，留 DXE 余量）+ `dts/mondrian.dts`/`dram_size` 同步 | 参数级（A），**但 0x840000000 基址正是 7g 静默失败的几何，必须先排障** |
| >8 GiB 窗口 | 另需解除双端 8 GiB 上限：`WindowSize.h:7`（`<= 0x200000000`）与 `devicetree.py:320-321` | 两行参数，但物理上只剩 0.65 GiB 余地，无意义 |
| 12 GiB 全量 | 给 arm64 加多段物理内存管理（pmap/vm_page/physmap 支持多区间 + 各 bank 保留区挖洞），工作量=内核子系统级、无上游先例 | **B（大改）**；且低段 bank 被 modem/HYP/TZ 重切，实际可并入量 ~2.5–3 GiB |
| 单窗口 12 GiB | 不可能 | **C**：6 bank 不连续 + 28 GiB 空洞（实测，§2） |

### 最小验证路径（不冒险地先证「>4 GiB 能被识别」）

1. **纯主机（零设备风险）**：已完成——本次审计的 `tools/mem-audit-dump.py` 可对任意候选 ADT/DTB 做结构核对。
2. **第一步上机（风险同现役 4 GiB）**：`owned_memory_size` 从 0x100000000 改为 **0x120000000（4.5 GiB）**，arena、dts、固件全部不动。4.5 GiB 窗口落在现役 5 GiB arena 内（候选基址 0x900020000，段内余量 ~0.5 GiB 给 DXE 顶部分配——8g 的教训是窗口=arena 必败，故第一步不贪满）。判据只看一行：屏幕 `K60 MEM`/`K60RV` 的 `mem=4608`。**不依赖用户区是否起来**。
3. **若 4.5 GiB 成功**：同基址阶梯 5 GiB（arena 同步+0.5 GiB 余量）→ 天花板 5.65 GiB；全程基址 0x900000000 不动。
4. **7 GiB 阶梯（回到失败几何前必做排障）**：先给 16.6.1 流水线加回入口 stage-bar（蓝条=内核入口 MMU-off 已执行；探针代码在构建链中存在，darwin24 线 0244 用过同思路），再上 7 GiB @0x840000000：有蓝条→死在 MMU/pmap 初始化（内核侧可查）；无蓝条→trampoline/入口参数问题（加载器侧可查）。
5. 全程不动 `unixnu` 以外分区、不 flash；每轮只改一个参数并回填 `build-verification.json`。

### 明确标注「未找到/未验证」

- 8g 失败的屏幕原始行（只有文档转述）；7g/8g 的屏幕照片文件不在归档。
- 7g 静默的根因（现有证据定不到子类别；内核 `1a18c6a2` 未在 4 GiB 实测=混杂因素）。
- sheng 侧 8 GB 实机内存统计（不存在）；sheng 加载器 `WindowSize.h`（uefi-sheng 未 clone 到本地）。
- iomem 高段保留区（0xa69b78000 起）的具体属主（modem/GPU/TZ 未标注）。
- `pong` 的 `owned_memory_size`（其 board.toml 无该键，走 256 MiB 默认窗口路径——与「703/1216 MiB」旧发现的时代配置，未深挖）。

## 附：本次取证产物

- `E:\k60-work\reports\mem-audit-dump.txt` — 现役 ADT 全量解码 + hardware.dtb + 真机 FDT reserved-memory
- `E:\k60-work\reports\mem-audit-dump2.txt` — mondrian.ours.dtb 与真机 FDT 内存段对照
- `E:\k60-work\tools\mem-audit-dump.py` / `mem-audit-dump2.py` / `mem-audit-archive.sh` — 只读解析脚本（可复跑）
