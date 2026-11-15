# 12. modem 镜像的固件装载契约（2026-11-15）

Lead 在 reply 里批准了案 A：固件把 modem 镜像摆到固定物理地址 `0x8bc00000`，接受 boot.img
从 201,891,840 B 涨到约 235,446,272 B（+32 MiB）。这份文档是给固件侧开工用的**接口契约**，
不是实现：本线不碰 `uefi-mondrian`、不改 `make-pong-adt.py`、不出镜像。

一句话结论：

- **输入**：payload FAT 的 `EFI/UniXNU/MODEM/modem.bNN`，27 个**平铺文件**；不要容器头，不要压缩；
- **输出**：`0x8bc00000..0x9ee00000`（320,864,256 B），拷 109,060,761 B、清 211,012,967 B，
  11 处空洞（790,528 B）保持不动；
- **发布**：`/chosen/memory-map` 下 `K60ModemImage` 属性，16 字节 `{u64 paddr, u64 len}`，小端；
- **落点建议**：不要做独立 DXE，做成 DarwinBoot boot 路径里的一个库调用（理由见 §3.3）；
- **需要 Lead 裁决的三件事**见 §0。

## 〇、需要 Lead 裁决的三件事

| 编号 | 事项 | 本线建议 | 依据 |
| --- | --- | --- | --- |
| D1 | 装载代码的落点：独立 DXE，还是 DarwinBoot boot 路径里的库调用 | **库调用**（`ImageCarrierLib` + 一个调用点） | payload 卷只读，独立 DXE 写不进 ADT；独立 DXE 失败也无法拒绝启动（§3.3） |
| D2 | ADSP 分支是否第一版就做 | **不做**，第一版只做 modem；`K60AdspImage` 名字保留 | ADSP 线已选内核内嵌 23.5 MB blob（`reply-adsp-20261115.md:4-28`），且 ADSP 窗口在固件内存图里没有 descriptor（§5.3） |
| D3 | +32 MiB 之后 ABL staging 的余量 | 先按 ~4.8 MiB 余量做，第一张图必须从固件日志核对 DTB 地址 | `MemoryMapLib.c:39-51` 的实测漂移公式（§1.5） |

Lead 已裁决（2026-11-15）：D1 采纳库调用（`ImageCarrierLib` + `DarwinBoot::Boot` 调用点，不做独立 DXE）；D2 第一版只做 modem，`K60AdspImage` 保留不发布；D3 在 §1.5 末尾追加两条硬要求（三行 level-1 日志，缺一不可上机判定）。

## 一、输入：payload FAT 里放什么

### 1.1 目录与文件名

| 项 | 值 | 依据 |
| --- | --- | --- |
| 目录 | `EFI/UniXNU/MODEM/` | 与现有 `EFI/UniXNU/Payloads/kernel.macho` 同级（`mdir` 实测 payload.img） |
| 文件 | `modem.b01..b13`、`modem.b15..b20`、`modem.b22..b29`，共 **27** 个 | `pong_modem_table.h` 里 `bytes > 0` 的行；`scripts/gen-modem-table.py:98-101` |
| 不装 | `modem.mdt`、`modem.b00`、`modem.b31` | mdt 只在构建期用来生成表（`gen-modem-table.py:60-77`）；b00/b31 的 `p_type=0`，不是 PT_LOAD（05-MODEM-IMAGE.md §2） |
| 每个文件的大小 | 必须**恰好等于**表里该行的 `bytes` | `gen-modem-table.py:70` 在构建期就是这么断言的 |

表本身（30 行、每行的 paddr/bytes/bss/名字）见 `docs/research/cellular/05-MODEM-IMAGE.md` §3；
固件不要手抄，见 §2.6。

### 1.2 容器头：不要；压缩：不要

Lead 问「是否需要 NGPUADD2 那样的容器头、容器要不要压缩」。答案是两个都不要：

1. **容器头没有可放的位置语义**。ADSP 的容器 ABI（12 B 头 + 24 B 记录 + NUL 名字，
   `reply-adsp-20261115.md:4-12`）记录里只有 `nameLen/mode/size/packedSize`，**没有 paddr**；
   modem 每个文件的目标地址只存在于段表里。走容器仍然要带表，等于多一份必须同步的格式
   （P-197 的形状），换不到任何东西。
2. **平铺的名字就是索引**。27 个文件的名字 `modem.bNN` 直接对到表的第 NN 行，
   固件按表拷、内核按表校验，两边共用同一份生成的表即可（§2.6）。
3. **不压缩**：内核路径与固件路径都没有链接 zlib（ADSP 线在 `CARRIER-BLOB-PLAN.md:19` 已记录
   同一结论）；PAS 要求段字节原样落在物理地址上，压缩只会多一条解压路径。modem 段本身已是
   厂商固件，压缩率不可预期。
4. 如果将来一定要一份容器，modem 的容器**只能**当「打包运输格式」，
   进固件后仍要先按名字查表拿 paddr；本契约不采用。

### 1.3 卷容量与 boot.img 算术

| 量 | 值 | 依据 |
| --- | --- | --- |
| 当前 payload 卷 | 192 MiB = 201,326,592 B | `board.toml:96` `size_mib = 192` |
| 当前已用 | 105,520,740 B（`kernel.macho` 105,504,768 + `kernel.macho.adt` 15,972） | `mdir` 实测 |
| modem 全部文件 | 109,072,529 B（30 个文件，含 mdt 与不装载的 b00/b31） | 01-ANDROID-INVENTORY.md §image 目录 |
| 相加 | 214,593,269 B ⇒ 卷至少 204.7 MiB | — |
| 新卷 | **224 MiB = 234,881,024 B**，余 20,287,755 B | 建议值 |
| 新 boot.img | **约 235,446,272 B**（+33,554,432 B） | 201,891,840 + 32 MiB |

### 1.4 构建期门禁（硬检查，任何一条不过就不该出图）

1. `EFI/UniXNU/MODEM/` 里恰好 27 个文件，名字与表一致，大小逐字节等于表里的 `bytes`；
2. 卷 `size_mib` ≥ 224，且 `payload.img` 实际大小等于 `size_mib × 1 MiB`（现有构建已检查）；
3. ADT 的 `/chosen/memory-map` 有 `K60ModemImage`，长度 16（§3）；
4. 固件侧的表与内核侧 `pong_modem_table.h` 逐行一致（§2.6 的宿主测试）；
5. boot.img 尺寸落在 ABL staging 余量内（§1.5）。

### 1.5 新风险：+32 MiB 之后 ABL staging 只剩约 4.8 MiB

`MemoryMapLib.c:39-51` 记录了 ABL 把 DTB（x0）与拼接 initrd 停在 `0xA8300000..0xB8000000`
这段 `ABL Staging` 保留区里，并给了漂移规律：**DTB 地址随 boot.img 大小线性下移**
（1 MiB 镜像 → `0xB6760000`；193 MiB 镜像 → `0xAA760000`）。用这两点外推：

- 当前 201,891,840 B：DTB ≈ `0xAA7D6000`；
- 新 235,446,272 B：DTB ≈ `0xA87D6000`；
- 距描述符下界 `0xA8300000` 只剩 **0x4D6000 ≈ 4.84 MiB**。

initrd 一端是以 `0xB8000000`（`Display Reserved` 起点）为锚向下长的：192 MiB 卷时约 214.5 MiB，
224 MiB 卷时约 246.5 MiB，起点降到 ≈ `0xA8980000`，仍在描述符内，余量 ≈ 6.5 MiB。

**结论**：235 MB 的图应当装得下，但这是本线算出来的估算，不是实测；第一张图必须先抓固件日志
核对 DTB 与 initrd 地址。同时它是一个**新预算**：卷再涨超过约 4 MiB（≈228 MiB 以上）就会把 DTB
顶出描述符，那时要么加长 `ABL Staging`（`MemoryMapLib.c:51` 的 length），要么换载具。
这也说明 modem 之后不要再往同一个卷里塞第二条 66 MB 级的固件（wifi 线的候选）。

`scripts/verify-boot-image.py` 本身没有尺寸上限（`:44` 只定义 header 大小，`:94-141` 是结构检查），
所以「超历史样本」不是脚本会拒，而是上面这段固件余量。

**Lead 对 D3 的裁决（2026-11-15）追加两条硬要求：**

a) 固件第一版必须在启动日志打印三个数，缺一不可上机判定：
   - chosen DTB 的物理地址：固定前缀 `modem-image: chosen dtb at `；
   - modem 窗口起止：固定行 `modem-image: window 0x8bc00000..0x9ee00000`（字面地址必须逐字符一致）；
   - ABL staging 结束地址：固定前缀 `modem-image: abl staging ends at `。
   前缀是验收脚本 grep 的锚点：固件不得改名、不得合并成一行。
b) 这三行必须是**默认可见**的打印（level 1），**不得挂在 debug 参数后面**；
   验收直接用 `grep -a` 命中，不允许「开 debug 再看」。

### 1.6 被拒绝的输入形态

| 形态 | 为什么拒 |
| --- | --- |
| 一个 306 MiB 的扁平窗口文件（把空洞也写成零） | 卷要 ≥ 407 MiB（`105,520,740 + 320,864,256 = 426,384,996`），boot.img ≈ 470 MB；且空洞在两种载具里都必须保持不动（§2.3） |
| 单个容器文件（ADSP 12B/24B 格式） | §1.2：没有 paddr 字段，平白多一份格式 |
| 压缩包 + 固件解压 | 固件没有解压库，且 PAS 要原样字节 |

## 二、输出：写到哪、写多少

### 2.1 目标与长度上限

| 项 | 值 | 依据 |
| --- | --- | --- |
| base | `0x8bc00000` | `pong_modem_table.h:3`；DT `dts/mondrian.dts:229-234`；`MemoryMapLib.c:31` |
| 长度上限 | `0x13200000`（320,864,256 B） | `pong_modem_table.h:4`；同上三处一致 |
| 末段结束 | 正好 `0x9ee00000` = base + window | 05-MODEM-IMAGE.md §3.2 |
| 固件内存属性 | 已登记为 `MEM_RES` / `UNCACHEABLE` / `Reserv` | `MemoryMapLib.c:31`，**不需要新增保留区** |

写越界一行都不允许：任何 `paddr + bytes + bss > base + window` 必须让装载失败（§四）。

### 2.2 对齐

| 对象 | 要求 | 实测/依据 |
| --- | --- | --- |
| carveout base | 2 MiB 对齐 | `0x8bc00000 = 1118 × 0x200000` |
| carveout 长度 | 2 MiB 对齐 | `0x13200000 = 153 × 0x200000` |
| 每个段的 paddr | **4 KiB 对齐**即可 | 30 段实测全部 4096 对齐（05 §3） |
| 每个段的长度 | 任意字节 | 文件末尾不对齐；例如 b19 结束于 `0x90b7de0f`、b25 结束于 `0x9de7b25e` |

⇒ 不要按 2 MiB 去校验段地址，也不要按页大小去截断长度。2 MiB 只是 carveout 自身的属性，
固件如果要用块拷贝加速，可以按 4 KiB 或 2 MiB 分块，但落点与长度必须逐字节精确。

### 2.3 写入量与空洞

| 量 | 值 |
| --- | --- |
| 拷贝 | 109,060,761 B（27 个文件） |
| 清零（bss） | 211,012,967 B |
| 合计写 | 320,073,728 B |
| 空洞（不写） | 790,528 B = 0x000C1000，11 处 |

11 处空洞的位置与大小见 05 §3.2（seg7/8/9/10/12/16/17/21/23/24/25 之前）。**空洞必须保持不动**：
内核的 `k60_modem_copy()` 只清 bss、从不清空洞（`K60ModemImage.c:70-92`），固件若清空洞，
两种载具产出的内存内容就不一致了。

### 2.4 bss 规则（容易做错的一条）

`bss` 不是只有 3 个纯 bss 段才有：30 行里凡 `bss > 0` 的行都要清。

| 量 | 值 |
| --- | --- |
| 3 个纯 bss 段（b14/b21/b30） | 179,552,256 B（4096 + 163,696,640 + 15,851,520） |
| 其余段尾部的 bss | 31,460,711 B |
| 合计 | 211,012,967 B |

每一行要清的区域是 `[paddr + bytes, paddr + bytes + bss)`；它与该行的拷贝区间不重叠，
所以先清后拷、先拷后清都可以。内核的做法是先清后拷、且从不假设 carveout 已零
（`K60ModemImage.c:83`），固件照同一条规则做。

### 2.5 缓存与内存属性

- 这块内存在固件里已经是 `UNCACHEABLE`（`MemoryMapLib.c:31`），DXE 通过 identity mapping 直接写，
  写穿到 DDR；**不需要** cache flush，也**不要**用 `AllocatePages` 去“借”这块地址
  （它已经是 `Reserv`，分配器不会给，强行分配会改坏内存图）。
- 与内核侧一致：内核用 `ml_io_map_unmappable(K60_MODEM_BASE, 0x1000, 0x2)` 只映射头页
  （`K60ModemBoot.c:124`），PAS 之前由 SCM 负责可见性。
- 固件写完到内核 AUTH_AND_RESET 之间隔着完整的 XNU 启动，不需要额外的 DSB/屏障
  （仍建议在拷贝结束处放一条 `MemoryFence()`，成本为零）。

### 2.6 表只有一份

现在 `scripts/gen-modem-table.py` 只生成内核头（`pong_modem_table.h`，`:91-104`）。
契约要求它**再加一个固件输出**（例如 `--firmware-header`）：同样的 30 行，但用固件自己的
结构体（不要 include `K60ModemImage.h`）。验收方式：宿主测试 `scripts/tests/test-k60-modem-image.py`
把两份生成物的 (paddr, bytes, bss, name) 逐行比对，任何一行不同就让测试红——这是防止两份表漂移的唯一手段。

## 三、发布：`/chosen/memory-map` 的 16 字节

### 3.1 属性名与布局

| 项 | 约定 | 依据 |
| --- | --- | --- |
| 属性名 | `K60ModemImage`（在 `/chosen/memory-map` 节点下，与 `RAMDisk` / `PackedRAMDisk` / `TrustCache` 同级） | `make-pong-adt.py:231-232` 的 memory-map 节点 |
| 长度 | 恰好 16 字节 | `pong_adt_contract.py:83` 对 16 字节是硬约束；`DarwinBoot.c:251` / `:268` 也要求 16 |
| 布局 | 前 8 B `u64` physical base，后 8 B `u64` bytes，**小端** | `NativeRamBlock.cpp:210-213` 用两次 `memcpy` 解码（arm64 = 小端）；`DarwinBoot.c:809-815` 用 `WriteUnaligned64` 写入 |
| 值 | `{0x8bc00000, 0x13200000}`（或全零表示“未发布”） | 本契约 §2.1 |

### 3.2 属性怎么写进 ADT

构建期：`make-pong-adt.py:232` 给 memory-map 加一条 16 字节占位（与 `PackedRAMDisk` 同形）。
运行时：**`DarwinBoot::Boot` 在它自己的 ADT 副本上写**，和 RAMDisk 一模一样：
`AdtNode` 在遍历时记下这个属性的偏移（现在只有 `RamdiskOffset` / `TrustCacheOffset`，
`DarwinBoot.c:208`、`:283-290`），然后在 `:809-815` 附近多写一对 `WriteUnaligned64`。

`DarwinBoot` 现在**不会**拒绝未知属性名：`AdtNode` 在 `memory-map` 下只挑 `Candidate`（RAMDisk）与
`TrustCandidate`（TrustCache），其它名字走通用校验后静默跳过（`DarwinBoot.c:283-290`）。
所以加 `K60ModemImage` 不需要动它的名字匹配逻辑，只需要新增一个偏移输出。

### 3.3 为什么不让独立 DXE 来写（关键结论）

三条硬事实：

1. **payload 卷是只读的**：`UniXNURamDiskDxe.c:324` `mMedia.ReadOnly = TRUE`。
   独立 DXE 可以读 `.adt` 文件，但**写不回去**。
2. **ADT 只有被读进内存后才可写**：`DarwinBoot.c:708` 拼出 `.adt` 路径，`:721` 把文件读进 `Tree`
   并校验，`:809-815` 才写属性。独立 DXE 拿不到这个 `Tree`。
3. **独立 DXE 的失败不会拒绝启动**：DXE Core 对返回错误的驱动只记一笔，接着走 BDS/菜单，
   所以“缺文件就让固件退”这个语义在独立 DXE 里做不到；而 `DarwinBoot` 的 `Fail:` 路径
   （`DarwinBoot.c:898-913`）会画屏、打印 `boot refused; firmware retained` 并返回菜单。

⇒ 建议把装载做成 **`ImageCarrierLib`（新库）+ `DarwinBoot::Boot` 里的一个调用点**。
这仍然是“一次固件改动”，与 Lead 说的“一个 DXE 做两份装载”在功能上等价，但能写 ADT、能拒绝启动。

### 3.4 推荐形状（D1-lib）：改动清单

| 位置 | 改动 |
| --- | --- |
| `Platforms/Xiaomi/.../ImageCarrierLib/`（新） | `ImageCarrierLoad(volume, const table, ...)`：打开卷→按表读文件→写物理→清 bss→返回 `{base, bytes}` |
| `DarwinBoot.c:208` | `AdtNode` 增加一个 `UINTN *ModemImageOffset` 输出 |
| `DarwinBoot.c:283-290` 附近 | `Path == 2` 时记录 `K60ModemImage` 的偏移，重复出现即 `EFI_COMPROMISED_DATA` |
| `DarwinBoot.c:721` 之后 | 调 `ImageCarrierLoad`（在 RAMDisk 放置之前或之后都可，二者不共享地址） |
| `DarwinBoot.c:809-815` 附近 | 成功时 `WriteUnaligned64(TreeAddress + ModemImageOffset, base)` 与 `+8 = bytes` |
| `DarwinBoot.c:898-913` | 失败沿用现有 `Fail:`（`Stage = L"MODEM IMAGE"`，屏幕上直接看到阶段名） |

### 3.5 备选形状（D2：独立 DXE）

若 Lead 坚持独立 DXE，发布只能走另一条通道：DXE 把 `{base, bytes}` 写进一个 UEFI 变量，
`DarwinBoot` 在 `:809` 附近读变量并写 ADT；同时 DXE 的失败要靠“变量缺失 + DarwinBoot 拒绝”来兜底。
代价是多一条变量通道、多一处失败面，且“拒绝启动”仍然要落到 `DarwinBoot`；不推荐。

### 3.6 属性的语义

- 它是**声明**，不是“加载成功”的证明：内核现在**不读**它（`K60ModemBoot.c:124` 用常量映射 +
  16 字节签名自检），所以属性写错也不会改变内核行为；
- 全零 = 未发布（构建期占位、或本次启动没有载具）；
- 将来若要读，按 `NativeRamBlock.cpp:210-213` 的两次 memcpy 解码，并校验
  `base == 0x8bc00000 && bytes == 0x13200000`，不一致就当未发布。

### 3.7 构建期契约检查（新增到 `pong_adt_contract.py`）

1. 有 `K60ModemImage` ⇒ 长度必须 16，且值要么全零、要么恰好 `{0x8bc00000, 0x13200000}`；
2. 卷里有 `EFI/UniXNU/MODEM/` ⇒ 属性必须存在；没有该目录 ⇒ 属性必须不存在；
3. `PackedRAMDisk` 的既有规则（`:82-84`）不动。

## 四、失败语义

| 情况 | 返回码 | 屏幕/日志 | 是否拒绝启动 |
| --- | --- | --- | --- |
| payload 里没有 `EFI/UniXNU/MODEM/` | —（跳过） | `modem-image: no carrier in payload, skipped` | 否（其它线的镜像照常启动） |
| 目录在、缺文件 | `EFI_NOT_FOUND` | `modem-image: modem.bNN missing` | **是** |
| 文件大小 != 表 | `EFI_COMPROMISED_DATA` | `modem-image: modem.bNN size 12345, table says 67890` | **是** |
| 行越界（`paddr + memsz > base + window`） | `EFI_COMPROMISED_DATA` | `modem-image: row N outside 0x8bc00000..0x9ee00000` | **是** |
| 行未 4 KiB 对齐 | `EFI_COMPROMISED_DATA` | `modem-image: row N paddr 0x... unaligned` | **是** |
| 表自身不自洽（段数/末段不等于 window 末尾） | `EFI_COMPROMISED_DATA` | `modem-image: table inconsistent` | **是** |
| 属性已非零（重复发布/重复执行） | `EFI_COMPROMISED_DATA` | `modem-image: range already published` | **是**（照 `DarwinBoot.c:726-727` 的先例：非零占位即视为损坏） |
| 卷打不开/读错误 | `EFI_DEVICE_ERROR` / 透传 | `modem-image: read modem.bNN failed: %r` | **是** |

拒绝启动的实现方式不需要新机制：`DarwinBoot` 的 `Fail:` 已经会画 `BOOT FAILED <stage> <status>`、
打印 `boot refused; firmware retained` 并回到菜单（`DarwinBoot.c:898-913`）。
“目录不存在就跳过”是唯一允许继续启动的分支——这样其它线的镜像不会因为没装 modem 文件而变砖。

## 五、ADSP 分支

### 5.1 ADSP 线现在的选择

ADSP 的答复（`E:/k60-work/scratch/reply-adsp-20261115.md:4-28`）明确：

- 容器 ABI：12 B 头 + 24 B 记录 + NUL 名字，总长 23,506,184 B；mode `0644`；
  `size == packedSize == raw`；不压缩；
- 载体：**内核内嵌**（`k60_adsp_blob`），生成器与 reader 适配由 ADSP 线做，`build-strict.sh --adsp-blob`
  与 MAIN-BASELINE 由 Lead 落；
- 与 `PAS1-PROVIDER-CARRIER.md:7` 一致：ADSP 选“内核内嵌只读固件 bundle（option B）”，理由是不加新 DXE。

### 5.2 与「两条线共用一次固件改动」的冲突

cellular 的答复说一个 DXE 同时做 `K60AdspImage` 与 `K60ModemImage`；ADSP 的答复说 ADSP 走内嵌 blob。
这两条是同一轮（`main = 2f9f991`）发出的，**互相冲突**。本线建议：

- 第一版固件改动**只做 modem 分支**；`K60AdspImage` 的名字与 16 字节布局在契约里保留，但**不发布**；
- 这样 ADSP 线继续按它已批准的 23.5 MB 内嵌方案走，固件侧不阻塞它；
- 若 Lead 要求 ADSP 也走固件，先看 §5.3 的三件事——不是改几行就能做。

### 5.3 如果 ADSP 也要走固件，必须先解决三件事

1. **固件内存图里没有 ADSP 装载窗口的 descriptor**。`MemoryMapLib.c:11-34` 的区域在
   `video_region`（`0x85700000 + 0x700000 = 0x85E00000`）之后直接跳到 `slpi_region`（`0x88000000`），
   `0x86300000..0x89400000` 没有任何条目；`adsp_region` 在 `0x9FD00000`，是另一块。
   而 `MemoryMapLib.c:39-51` 记录过同一个坑：没有 descriptor 的区域第一次读就 `0x96000010`
   level-2 translation fault。⇒ 要加 descriptor（可能是新保留区，也可能要修 ADSP 的加载基址）。
2. **ADSP 窗口被段 + 空洞正好填满**：24 段拷 23,494,284 B、清 25,925,684 B、共写 49,419,968 B，
   段间空洞 1,960,256 B，合计 **51,380,224 B = 整个 span**（`K60AdspPas.h:23-24`）。
   所以不能把容器原样放进窗口再原地展开（会自我覆盖）⇒ DXE 必须解析 `adsp.mdt` 的 ELF32 按段写，
   或另找一块暂存区。
3. **段 10 的链接地址 `0x86e0b2c0` 不是页对齐**（`CARRIER-BLOB-PLAN.md:85`），必须按字节偏移/长度写。

### 5.4 两个分支的共用面

| 共用（`ImageCarrierLib` 的主体） | modem 分支 | ADSP 分支（若做） |
| --- | --- | --- |
| 打开 payload 卷（SimpleFileSystem，`DarwinBoot.c:693-695` 同款） | 30 行表（§2.6） | 12 B/24 B 容器 + mdt ELF 解析 |
| 按名字读文件、校验大小 | 27 个平铺文件 | 26 个名字（NUL 结尾） |
| 写物理地址、清 bss、空洞不动 | 0x8bc00000 / 0x13200000 | 0x86300000 / 0x3100000 |
| 写 ADT 属性、失败拒绝启动、日志前缀 | `K60ModemImage` | `K60AdspImage` |

⇒ 抽象接口建议：`Load(volume, spec) -> {base, bytes}`，其中 `spec` 负责“名字→(paddr, bytes, bss)”的映射；
modem 的 `spec` 是表驱动，ADSP 的 `spec` 是容器 + ELF 解析。第一版只实现 modem 的 `spec`。

## 六、验收

1. 固件日志（建议格式，便于 grep；前三行是 D3 的 level-1 硬要求，见 §1.5）：
   `modem-image: chosen dtb at 0x...`
   `modem-image: window 0x8bc00000..0x9ee00000`
   `modem-image: abl staging ends at 0x...`
   `modem-image: 30 segments, copied 109060761, zeroed 211012967, gaps 790528 untouched`
   `modem-image: range 0x8bc00000..0x9ee00000 published as K60ModemImage`
2. 内核日志：`K60MODEM carrier present at 0x8bc00000`（`K60ModemBoot.c:139`）→ `plan rows=30 ...`
   → `auth_reset ok` → `init_image ok segments=27` → `mem_setup ok`；
3. 构建期：§1.4 的五条 + §3.7 的三条全过；
4. 第一张 235 MB 图：先跑 `verify-boot-image.py` 与 `check-image-args.py`（`pong_modem` 已在
   `check-image-args.py:44-50` 的白名单里），并从固件日志核对 DTB/initrd 地址（§1.5）；
5. 之后才排队上机（`--kernel-arg pong_modem=2`）；QRTR 的 verdict 判据不变（07 篇）。

## 七、引用清单

| 事实 | 出处 |
| --- | --- |
| mpss_region 基址/大小 | `dts/mondrian.dts:229-234`；`02-DT-TRUTH.md:192`；`MemoryMapLib.c:31`；`pong_modem_table.h:3-4` |
| 30 段几何、空洞、bss | `05-MODEM-IMAGE.md` §3、§3.2、§4 |
| 表生成器 | `scripts/gen-modem-table.py:60-109` |
| 内核搬运规则 | `drivers/PongCellular/K60ModemImage.c:12`、`:36-50`、`:70-92` |
| 16 字节范围格式 | `NativeRamBlock.cpp:210-213`；`DarwinBoot.c:809-815` |
| memory-map 属性放置 | `make-pong-adt.py:231-232`；`pong_adt_contract.py:82-84` |
| ADT 解析与未知属性跳过 | `DarwinBoot.c:208`、`:245-253`、`:283-290`、`:721` |
| payload 卷只读 | `UniXNURamDiskDxe.c:324-325` |
| 固件读卷的现成路径 | `DarwinBoot.c:14`、`:693-695`；`DarwinBoot.inf:34`；`UniXNURamDiskDxe.inf:30` |
| ABL staging 漂移 | `MemoryMapLib.c:39-51` |
| ADSP 容器 ABI 与内嵌选择 | `reply-adsp-20261115.md:4-28`；`CARRIER-BLOB-PLAN.md:9-23`；`PAS1-PROVIDER-CARRIER.md:7` |
| ADSP 窗口与空洞 | `K60AdspPas.h:23-24`；`CARRIER-BLOB-PLAN.md:85` |
| payload 卷与 boot.img 现状 | `board.toml:94-98`；`11-CARRIER.md` §2.1 |

## 八、本轮不做

- 不碰 `uefi-mondrian`、不改 `make-pong-adt.py`、不加固件表——本文只是契约；
- 不出镜像、不申请上机（Lead 已明确：契约交上去再开工 DXE）；
- L4 的顺序错误（先 QRTR 后 PAS）只记进 `11-CARRIER.md` 的「待办」，不改 `K60ModemBoot.c`；
- `porting.toml` 的 `status = "implemented"` 与 findings 保留。
