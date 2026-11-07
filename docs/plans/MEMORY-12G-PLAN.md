# K60 可用内存提升到 12 GiB 实施方案

> 调研日期：2026-11-08。范围：只读调研 + 本文件；不改 UEFI、`board.toml`、`dts`，不构建，不碰设备。
> 本文只说三件事：现在 iOS 实际拿到多少、12 GiB 在 K60 上到底怎么分解、若要做需要按什么顺序改和验。
> 结论先行：**K60 的 12 GiB 是装机 DRAM 容量，不是 XNU 单窗口可用量。** 六段 `/memory/reg` 合计 12013 MiB（11.73 GiB）；XNU arm64 只管理一段连续物理内存，最大连续可用段是 `[0x840000000,0xA69B78000)` = 8.652 GiB，而 DarwinBoot 的窗口解析上限是 8 GiB。只改 `MemoryMapLib.c` / `board.toml` / `dts`，可以把 `dram_size` 改成真实的 12 GiB、把固件可分配高段扩到 8.652 GiB、把 iOS 窗口推到 8 GiB；**要让 XNU 管到全部约 10 GiB 物理段，必须另做 arm64 多区间 pmap/vm_page 补丁**；12 GiB 全部可用仍然做不到，因为低区约 1.41 GiB 加高区顶部 356.5 MiB 是 modem/adsp/camera/HYP/UEFI/DXE 等的硬保留。

## 1. 现状：iOS 实际拿到多少，为什么“不到 8G”

### 1.1 `dram_size`、`owned_memory_size`、DTS memory 节点不是一回事

| 数值 | 当前值 | 位置 | 真实作用 |
|---|---:|---|---|
| `dram_size`（物理 DRAM 声明） | `"0x140000000"` = 5 GiB | `board.toml:98`（`[payload]` 下） | 必须等于硬件 DTS 的 `/memory` 节点 size；经 `devicetree.py:302-310` 写入 ADT `/chosen/dram-size`。XNU 只在 `arm_init.c:643-664` 把它读进 `gDramBase/gDramSize`，**不参与 `memSize` 计算**。 |
| `owned_memory_size`（DarwinBoot 窗口） | `"0x130000000"` = 4.75 GiB | `board.toml:162`（`[payload."adt"]` 下） | 经 `devicetree.py:319-323` 写入 ADT `/chosen/darwinboot-memory-size`；DarwinBoot 的 `AdtNode()`（`DarwinBoot.c:249-272`）读取并校验，`DarwinBoot.c:636-637` 写成 `boot_args->memSize` 和 `memSizeActual`。**这才是 iOS 实际拿到的内存。** |
| DTS `/memory` 节点 | `memory@900000000`，`reg = <0x9 0x00000000 0x1 0x40000000>` = 5 GiB | `dts/mondrian.dts:29-32` | `devicetree.py:302-307` 要求**恰好一个 memory 节点、恰好一组 reg**；它是 ADT `/chosen/dram-base` 和 `/chosen/dram-size` 的唯一来源，不是 XNU 窗口，也不是完整硬件内存表。 |
| 当前 `MemoryMapLib.c` 高段 Conv | `XNU High Arena` `[0x900000000,0xa40000000)` = 5 GiB | `MemoryMapLib.c:94` | UEFI `gMemoryDescriptor` 里 DarwinBoot 可分配的唯一高段 arena；它决定 `AllocateWindow()` 能扫描到的 `EfiConventionalMemory` 连续 run。 |

链条可以写成：

```text
board.toml:98 dram_size ──必须相等──> dts/mondrian.dts:29-32 memory@900000000 (5 GiB)
        └── devicetree.py:302-310 ──> ADT /chosen dram-base=0x900000000, dram-size=0x140000000
                                      └── arm_init.c:643-664 ──> gDramBase/gDramSize（仅 is_dram_addr 使用，不是 memSize）

board.toml:162 owned_memory_size=0x130000000 (4.75 GiB)
        └── devicetree.py:319-323 ──> ADT /chosen darwinboot-memory-size=0x130000000
                                      └── DarwinBoot.c:249-272,580,636-637 ──> boot_args->memSize/memSizeActual
                                                                              └── arm_vm_init.c:1847-1857 ──> XNU managed / hw.memsize
```

pong 的模型可作为这个分离的参照（任务给的 `git -C E:/hackios/UniXNU-pong show origin/main:scripts/make-pong-adt.py` 在当前 pong 仓返回 `fatal: path ... does not exist`；同内容副本在 `E:/hackios/UniXNU-mondrian/scripts/make-pong-adt.py`，以下按该副本引用）：

- `DRAM_BASE = 0x80000000`（`scripts/make-pong-adt.py:23`）；
- `--dram-size` 是必填的物理 DRAM 总量（`:78-80`），写入 `/chosen/dram-size`（`:155-156`）；
- `--window-size` 是可选的 DarwinBoot 窗口（`:81-82`），写入 `/chosen/darwinboot-memory-size`（`:157-158`）；
- `scripts/pong_adt_contract.py:136-137` 对 `dram-base`/`dram-size` 做必填 8 字节检查，对 `darwinboot-memory-size` 做可选 8 字节检查。

pong 的 `dts/pong.dts:6-10` 也明确把 `memory@80000000` 的 12 GiB 说成“physical DRAM the boot chain reports, not the usable-range sum”。K60 要照搬的是这个“`dram-size` 与窗口分离”的模型，不是照搬 pong 的连续 12 GiB 物理布局。

### 1.2 现在实际拿到多少

- 配置值是 `owned_memory_size = 0x130000000` = **4.75 GiB**（`board.toml:162`）。
- 2026-11-07 的 USB 控制台日志已经给出设备侧证据：`vm_page_bootstrap: 1208993 free pages, 36191 wired pages`（`E:/k60-work/evidence/usblog-20261107-112028/console.log:17`）。K60 这套 XNU 是 4 KiB 页：`1,208,993 + 36,191 = 1,245,184` 页，`1,245,184 × 4096 = 0x130000000` = **4.75 GiB**；同一日志的 `K60RV 1 launchd[1] mem=4864 actual=4864 managed=4864`（`:569`）也证明三数都是 4864 MiB。
- 最后一次有**屏幕照片**的内存三数是 4096 MiB（`docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md:112-117`）；4.75 GiB 这一档在 `docs/state/STATE-2026-11-07.md:221` 仍被标注为“是否已上机验证”未核实。两者不矛盾：4.75 GiB 是当前配置/控制台证据，4 GiB 是历史屏幕证据。

### 1.3 为什么“不到 8G”

1. **`dram_size` 不是窗口。** 它只进入 `gDramBase/gDramSize`（`osfmk/arm/arm_init.c:643-664`），唯一消费者是 `is_dram_addr()`（`osfmk/mach/arm/vm_param.h:301-302`，`osfmk/arm/pmap/pmap.c:5667`）。`hw.memsize` 在 iOS 分支使用 `max_mem`，即 `arm_vm_init.c:1847-1857` 的 `mem_size = args->memSize`，不是 `gDramSize`（`bsd/kern/kern_mib.c:915`）。历史 ADT 就曾经是 `dram-base=0x80000000`、`dram-size=0x300000000`（12 GiB），而当时的 XNU 窗口仍然只有 4 GiB（`docs/reference/AGENT-COORDINATION.md:1799`）——这直接证明只改 `dram_size` 不会让 `hw.memsize` 变大。
2. **当前 `owned_memory_size` 只有 4.75 GiB**，小于 8 GiB；当前 arena 也只有 5 GiB（`MemoryMapLib.c:94`），窗口在 arena 内再扣掉内核基址偏移 `0x20000` 和页对齐余量，实际只能到 4.75 GiB 左右。`ISSUES.md:212-220` 记录 5 GiB 窗口因 `arena == window` 差 128 KiB 被 `NO WINDOW` 拒绝，4.5 GiB 能正常起，最后 4.75 GiB 通过。
3. **单窗口物理上限不是 12 GiB。** 六段内存不连续；`[0x100000000,0x800000000)` 是 28 GiB 无 DRAM 空洞（`MEASURED-HIGH-WINDOW-2026-11-02.md:50-53`）。唯一长连续段是 `[0x840000000,0xA80000000)` = 9 GiB，扣掉顶部 `0xA69B78000` 起的保留区后是 **8.652 GiB**；`DarwinWindowSizeValid()` 又限制 `size <= 0x200000000`（`drivers/DarwinBoot22/DarwinBootPkg/Driver/WindowSize.h:6-8`），`devicetree.py:319-323` 也只接受 256 MiB–8 GiB。**8 GiB 是单窗口硬上限，12 GiB 单窗口在物理上不存在。**
4. **低区不等于可用内存。** 低区两段合计 1.838 GiB（1882 MiB），但 `MemoryMapLib.c:11-61` 把 HYP、SMEM、CUCP、cdsp_secure_heap、video、slpi、cdsp、mpss、cvp、camera、adsp、xbl/ramoops 等全部标成 `MEM_RES`；低区真正空闲的只有约 435 MiB（见 §3）。所以“12 GiB 装机”不可能变成“12 GiB iOS 可用”。

### 1.4 T1 的冲突必须保留

`docs/state/TRUST-LEDGER.md:11-13` 的 T1 写明：`AGENT-COORDINATION.md:1778,1792,1782` 说“设备实测 DRAM 12 GiB”，而 `MEASURED-HIGH-WINDOW-2026-11-02.md:39-57` 原文说“手写 `base=0x80000000,size=12 GiB` 的 DTS **不是**硬件实测；`swinfo.fingerprint=mondrian:12` 也不是可靠 SKU 证据”，状态是**冲突未解**。

本文的处理方式：

- 不把 `swinfo.fingerprint=mondrian:12` 当作唯一证据；只用 serial `6033dbec` 的 live `/memory/reg` 六段原始字节（`live-6033dbec-memory-reg.bin`，SHA-256 `729587c3f0c5c469768dce73a833b3ba35fd9abb091ff22e28141ed34fc0cec6`）及其合计 **12013 MiB**作为“约 12 GiB 装机容量”的工作依据，并保留 `ddr_size=0xc`（live FDT `/memory` 属性）作为旁证。
- 六段合计不是精确 12 GiB：12013 MiB 比 12 GiB（12288 MiB）少 **275 MiB**，这 275 MiB 不在 `/memory/reg` 里，具体用途**未核实**；本文不编造。
- 因此本文的“12 GiB”一律指**装机容量/物理 DRAM 口径**；凡是“XNU 可用”“`hw.memsize`”都单独按窗口计算，不混用。

## 2. 真机内存地图（六段）

数据源：`E:/k60-work/reports/live-6033dbec-fdt.dtb`（919,210 bytes，FDT v17，SHA-256 `95c02052b773a1b8df8ec20f6368ba80c87717206ed40682046e2ad6f29fdac8`），用 Python 解析根节点 `/memory` 的 `reg`；同一数据也见 `MEASURED-HIGH-WINDOW-2026-11-02.md:39-49`。复核脚本（无第三方依赖，只打印 memory 节点；表 2 就是它的输出）：

```python
import struct
b = open(r'E:/k60-work/reports/live-6033dbec-fdt.dtb', 'rb').read()
h = struct.unpack_from('>10I', b, 0)
struct_at, str_at, str_size = h[2], h[3], h[8]
strings = b[str_at:str_at + str_size]
def name(off):
    end = strings.find(b'\0', off)
    return strings[off:end].decode('ascii', 'replace')
pos, stack = struct_at, []
while True:
    tok = struct.unpack_from('>I', b, pos)[0]; pos += 4
    if tok == 1:
        end = b.find(b'\0', pos); stack.append(b[pos:end].decode('ascii', 'replace'))
        pos = (end + 1 + 3) & ~3
    elif tok == 2:
        stack.pop()
    elif tok == 3:
        length, nameoff = struct.unpack_from('>II', b, pos); pos += 8
        val = b[pos:pos + length]; pos = (pos + length + 3) & ~3
        if stack and stack[-1] == 'memory' and name(nameoff) == 'reg':
            c = [struct.unpack_from('>I', val, i)[0] for i in range(0, len(val), 4)]
            for i in range(0, len(c), 4):
                print('0x%x/0x%x' % ((c[i] << 32) | c[i + 1], (c[i + 2] << 32) | c[i + 3]))
    elif tok == 9:
        break
```

| # | Base | Size | Exclusive end | GiB | MiB | 区域 |
|---|---:|---:|---:|---:|---:|---|
| 1 | `0x80000000` | `0x6a000000` | `0xea000000` | 1.656 | 1696 | 低区 A |
| 2 | `0xf4600000` | `0x0ba00000` | `0x100000000` | 0.182 | 186 | 低区 B |
| 3 | `0x800000000` | `0x37500000` | `0x837500000` | 0.864 | 885 | 高区 C |
| 4 | `0x837b00000` | `0x01e00000` | `0x839900000` | 0.029 | 30 | 高区 D |
| 5 | `0x840000000` | `0xc0000000` | `0x900000000` | 3.000 | 3072 | 高区 E |
| 6 | `0x900000000` | `0x180000000` | `0xa80000000` | 6.000 | 6144 | 高区 F |
| **合计** | `0x80000000` 起不连续 | `0x2eed00000` | — | **11.731** | **12013** | 低 1882 MiB + 高 10131 MiB |

计算：

- 低区 = 段 1 + 段 2 = `0x6a000000 + 0x0ba00000 = 0x75a00000` = **1.838 GiB（1882 MiB）**，约 **1.75 GiB**（口语四舍五入）。
- 高区 = 段 3 + 段 4 + 段 5 + 段 6 = `0x37500000 + 0x01e00000 + 0xc0000000 + 0x180000000 = 0x279300000` = **9.894 GiB（10131 MiB）**，约 **10 GiB**。
- 合计 = `0x2eed00000` = **11.731 GiB（12013 MiB）**，不是精确 12 GiB；差额 275 MiB 未在 `/memory/reg` 中体现，未核实。
- 空洞：`[0x100000000,0x800000000)` = **28 GiB 完全无 DRAM**（`MEASURED-HIGH-WINDOW-2026-11-02.md:50-53`）；另有 `[0x839900000,0x840000000)` 112 MiB 小空洞和 `[0x837500000,0x837b00000)` 6 MiB 小空洞。
- 唯一长连续段：`[0x840000000,0xA80000000)`（段 5 + 段 6，首尾相接）= 9 GiB；顶部 `0xA69B78000..0xA80000000` 是 iomem 标注的保留区（约 356.5 MiB），实际可交给 XNU 的连续段是 `[0x840000000,0xA69B78000)` = **8.652 GiB（8859.5 MiB）**（`MEASURED-HIGH-WINDOW-2026-11-02.md:122-137`）。

## 3. 目标 12 GiB 的分解：哪些段可给 XNU、哪些必须保留

### 3.1 先把口径定死

按 §2 的 live 六段，**12013 MiB 的物理可见内存**可以拆成：

| 口径 | 数值 | 说明 |
|---|---:|---|
| 装机容量（名义） | 12288 MiB = 12 GiB | `ddr_size=0xc` / SKU 口径；与 `/memory/reg` 差 275 MiB，未核实 |
| `/memory/reg` 可见总量 | 12013 MiB = 11.731 GiB | 本文所有分解的分母 |
| 硬保留（MemoryMapLib + 高段顶保留） | 1803.6 MiB = 1.762 GiB | 低区 1447.1 MiB + 高区顶部 356.5 MiB |
| XNU 多区间理论上限 | 10209.4 MiB = 9.970 GiB | 低区空闲 434.9 MiB + 高区可用 9774.5 MiB |
| XNU 单窗口上限 | 8.652 GiB（loader 再压到 8 GiB） | 唯一连续段 E+F 扣顶保留 |

因此，**“12 GiB 全部给 XNU”在物理上不存在**：最大只能到约 9.97 GiB（而且要先给 arm64 加多区间支持）；低区 1.76 GiB 是 modem/adsp/camera/HYP/UEFI/DXE 等不可搬走的保留。

### 3.2 逐段预算

| 段 | 原始 | 必须保留 | 可给 XNU（多区间） | 保留依据（MemoryMapLib.c 行号） |
|---|---:|---:|---:|---|
| 低区 A `[0x80000000,0xea000000)` | 1696.0 MiB | 1447.1 MiB | 248.9 MiB（碎） | `:11` HYP 6 MiB；`:31` mpss 306 MiB；`:34` adsp 49 MiB；`:33` camera 8 MiB；`:21` cdsp_secure_heap 70 MiB；`:24` cdsp 32 MiB；`:23` slpi 25 MiB；`:22` video 7 MiB；`:32` cvp 7 MiB；其余见 `:12-20,25-30,35-61,63-75,83` |
| 低区 B `[0xf4600000,0x100000000)` | 186.0 MiB | 0 | 186.0 MiB | 无任何 MemoryMapLib 描述符 |
| 高区 C `[0x800000000,0x837500000)` | 885.0 MiB | 0 | 885.0 MiB | 无描述符；注意 pong HYP 风险见 §6.4 |
| 高区 D `[0x837b00000,0x839900000)` | 30.0 MiB | 0 | 30.0 MiB | 无描述符 |
| 高区 E `[0x840000000,0x900000000)` | 3072.0 MiB | 0 | 3072.0 MiB | 无描述符；与 F 首尾相接 |
| 高区 F `[0x900000000,0xa80000000)` | 6144.0 MiB | 356.5 MiB（顶部） | 5787.5 MiB | `0xA69B78000..0xA80000000` 为 live iomem 保留（`MEASURED-HIGH-WINDOW-2026-11-02.md:66`）；该段没有独立 MemoryMapLib 行，需按 §4.1 新增 `XNU High Top Reserve` |
| **合计** | **12013.0 MiB** | **1803.6 MiB** | **10209.4 MiB** | — |

### 3.3 不能给 XNU 的东西（按类别）

- **HYP**：低区 `0x80000000 + 6 MiB`（`MemoryMapLib.c:11`，live FDT `/reserved-memory/hyp_region@80000000`）。pong 的 `HYP Reserved 0x830000000+0x10000000` 不能直接搬（见 §6.4）。
- **modem / MPSS**：`mpss_region 0x8bc00000 + 0x13200000` = 306 MiB（`:31`）。
- **ADSP**：`adsp_region 0x9fd00000 + 0x03100000` = 49 MiB（`:34`）。
- **camera**：`camera_region 0x9f500000 + 0x00800000` = 8 MiB（`:33`）。
- **CDSP / CDSP secure heap**：`:24` 32 MiB、`:21` 70 MiB；**SLPI** `:23` 25 MiB；**video** `:22` 7 MiB；**CVP** `:32` 7 MiB。以上 modem/ADSP/camera/CDSP/SLPI/video/CVP/HYP 合计约 **510 MiB**。
- **显示 / 触摸相关**：`Display Reserved 0xB8000000 + 0x02B00000` = 43 MiB（`:52`，`splash_region` 同值）；不要设为 Conv，否则面板扫描/控制台会写同一块内存（GPU-ENABLE-PLAN 已记录同类风险）。
- **ABL / UEFI / DXE**：`ABL Staging 0xA8300000 + 0x0FD00000` = 253 MiB（`:51`）；`UEFI FD`、`FD Reserved`、`CPU Vectors`、`Info Blk`、`MMU PageTables`、`Log Buffer`、`UEFI Stack`、`SEC Heap`、`Sched Heap`、`FV Region`、`UEFI RESV` 见 `:63-74`；`Kernel` 192 MiB `:75`；`DXE Heap 0xC7000000 + 0x18000000` 384 MiB `:83`（这是 UEFI 自己的 `Conv`，不是 XNU 的）。
- **低区其余保留**：`DT BLOB`、AOP、SMEM、CUCP、tme、ipa、spss、spu、xbl、global_sync、ramoops、qheebsp、cpusys、hyp_reserved、trust_ui、TZ STATS、tags、QTEE 见 `:12-20,25-30,35-61`。

### 3.4 单窗口结论

- 单窗口最大连续物理段是 `[0x840000000,0xa69b78000)` = **8.652 GiB**；arena 还要扣掉内核基址偏移 `0x20000` 才能和窗口对齐（`ISSUES.md:216`），所以实际能交给 DarwinBoot 的窗口最大 **8 GiB**（`WindowSize.h:6-8`、`devicetree.py:319-323`）。
- 8 GiB 不是“12 GiB 的 2/3 临时值”，而是**这块板 + 当前 XNU 单区间架构的单窗口硬顶**。12 GiB 单窗口从未存在过；旧的 `[0x100000000,0x380000000)`（10 GiB Conv）完全落在 4–32 GiB 空洞里，已在 `MEASURED-HIGH-WINDOW-2026-11-02.md:50-53` 被判死。
- 要超过 8 GiB，必须让 XNU arm64 从“一个 `{physBase, memSize}`”改成“多段物理内存 region”；现有树里 `pmap_memory_regions[]`/`pmap_add_memory_region` 只在 `osfmk/i386`、`osfmk/x86_64` 存在，arm64 没有入口（`DECISION-MEMORY-12GIB-2026-11-02.md:14,115-120`）。这是内核子系统级工作，不是本计划的 UEFI 步骤。

## 4. 分步实施

> 实施原则：一次只改一个变量；每轮只 `fastboot boot`，不 flash；每轮保留上一版 FD/镜像和回滚命令；任何一步没有达到 §5 判据就停，不叠加下一步。本节全部是“计划中的改动”，本次不执行。

### 4.1 第 1 步：`MemoryMapLib.c` 恢复低段 + 新增/替换高段 Conv

文件：`E:/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c`（当前 123 行）。

**1a. 先确认低段没有再次被截断。** 低段必须从 `:11` 的 `HYP` 一直到 `:61` 的 `QTEE`，以及 `:63-74` 的 UEFI 系统区、`:75` 的 `Kernel` 和 `:83` 的 `DXE Heap` 全部在场。当前工作树的 `Conv` 有两条：`:83 DXE Heap` 和 `:94 XNU High Arena`；旧描述里的“只有 DXE Heap 一条 Conv”对应修复前基线，不要据此删掉 `:94`。若工作树是 `E:/k60-work/reports/MemoryMapLib-before-repair-20261102-143625.c` 那种截断件，按 `MEASURED-HIGH-WINDOW-2026-11-02.md:55-59` 从 `e06211de` 恢复后再做下面的新增：

```sh
git -C E:/hackios/uefi-mondrian show e06211de:Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c \
  > E:/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c
```

**1b. 把 `:94` 的 5 GiB `XNU High Arena` 替换为完整 8.652 GiB 连续段，并在它前面新增高段 C/D（多区间用）、高段顶保留、低区 B（多区间用）。** 具体要加的行如下（`AddMem` 必须保留：Silicium MemoryPeim 同时建 HOB 和 identity mapping；不要用 `HobOnlyNoCacheSetting`，见 `MEASURED-HIGH-WINDOW-2026-11-02.md:67-68`）：

```c
  // ---- Phase 1: single-window build (E+F run + top reserve) ----
  // Replace the old 0x900000000 + 0x140000000 (5 GiB) entry with the full
  // measured contiguous run [0x840000000,0xA69B78000) = 8.652 GiB.
  {"XNU High Arena",      0x840000000ULL, 0x229B78000ULL, AddMem, SYS_MEM, SYS_MEM_CAP, Conv, WRITE_BACK_XN},

  // [0xA69B78000,0xA80000000) is reserved in live iomem.  Keep it a separate
  // MEM_RES region; never let it become part of EfiConventionalMemory.
  {"XNU High Top Reserve", 0xA69B78000ULL, 0x16488000ULL, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},

  // ---- Phase 2 candidates: only after arm64 multi-range exists ----
  // High banks measured by serial 6033dbec /memory/reg.  Do not merge them
  // into one 12 GiB range: [0x100000000,0x800000000) is a 28 GiB hole.
  {"XNU High Bank C",     0x800000000ULL, 0x37500000ULL, AddMem, SYS_MEM, SYS_MEM_CAP, Conv, WRITE_BACK_XN},
  {"XNU High Bank D",     0x837B00000ULL, 0x01E00000ULL, AddMem, SYS_MEM, SYS_MEM_CAP, Conv, WRITE_BACK_XN},

  // Optional low bank for a future multi-range XNU.  Keep it out of the first
  // single-window build; it does not touch the E+F run used by DarwinBoot.
  {"XNU Low Bank B",      0xF4600000ULL, 0x0BA00000ULL, AddMem, SYS_MEM, SYS_MEM_CAP, Conv, WRITE_BACK_XN},
```

要点：

- `XNU High Arena` 的新长度 `0x229B78000` = `0xA69B78000 - 0x840000000`；不要写成 `0x280000000`（那会把顶部 356.5 MiB 保留区也吞掉）。
- `XNU High Bank C`/`D` 和 `XNU Low Bank B` 在本轮单窗口阶梯里不会改变 `DarwinBoot` 的窗口选择：`AllocateWindow()` 扫描所有 `EfiConventionalMemory`，取合并后最大的连续 run，E+F 仍是最大的；它们是为将来 arm64 多区间或 UEFI 完整内存表预留的，**不能把它们误当成“已经给 XNU 的 12 GiB”**。
- 低区 A 的碎片空闲约 249 MiB（最大四块 74.9 / 61.5 / 49.0 / 34.0 MiB）本轮**不加入** Conv；它们夹在 HYP/modem/UEFI 保留之间，先保持原样，等单窗口跑通、且多区间内核有眉目后再逐个测量。
- 不要动 `:83` 的 `DXE Heap`（这是 UEFI 的 384 MiB 堆，不是 XNU 窗口）；不要抄 pong 的 `HYP Reserved`（见 §6.4）。
- 同步改写 `:85-93` 的旧注释：它现在写的是 `[0x840000000,0xa40000000)` 8 GiB / “12 GiB window is impossible”。新注释应写实测 `[0x840000000,0xA69B78000)` = 8.652 GiB、顶部 `0xA69B78000..0xA80000000` 为 `MEM_RES`，并保留“12 GiB 单窗口 impossible、只做到 8 GiB 单窗口”的结论，避免下一位读者把旧 8 GiB 实验几何当成当前值。

### 4.2 第 2 步：`board.toml` 的 `dram_size` 改 0x300000000

文件：`E:/hackios/UniXNU-mondrian/board.toml`。

**2a. `:98` 改为：**

```toml
# Physical DRAM total reported by the live six-bank /memory/reg map (12013 MiB
# visible; ddr_size=0xc).  This is NOT the DarwinBoot window: the window is
# owned_memory_size below, and the handoff arena lives in MemoryMapLib.c.
dram_size = "0x300000000"
```

`dram_size` 必须等于 `dts/mondrian.dts` 的 `/memory` 节点 size，否则 `devicetree.py:306-307` 会直接报 `payload.dram_size differs from the hardware DTS`。

**2b. `:162` 的 `owned_memory_size` 不要跟着改成 12 GiB。** 它的合法上限是 256 MiB–8 GiB、2 MiB 对齐（`devicetree.py:319-323`），12 GiB 会被解析器拒绝；即使放宽解析器，`AllocateWindow()` 也找不到 12 GiB 连续 `EfiConventionalMemory`。按下面阶梯逐轮改：

| 阶梯 | `owned_memory_size` | 窗口 | 4 KiB 页总数（= 窗口/4096） | 目标 `hw.memsize`（bytes） |
|---|---:|---:|---:|---:|
| 当前/回归 | `0x130000000` | 4.75 GiB | 1,245,184 | 5,100,273,664 |
| 2 | `0x180000000` | 6 GiB | 1,572,864 | 6,442,450,944 |
| 3 | `0x1C0000000` | 7 GiB | 1,835,008 | 7,516,192,768 |
| 4 | `0x200000000` | 8 GiB | 2,097,152 | 8,589,934,592 |

每轮只改这一行；第 4 行就是当前单窗口架构的终点。**不要把 `0x300000000` 填进 `owned_memory_size`。**

### 4.3 第 3 步：`dts/mondrian.dts` 的 memory 节点

文件：`E:/hackios/UniXNU-mondrian/dts/mondrian.dts:18-32`。当前是：

```dts
	memory@900000000 {
		device_type = "memory";
		reg = <0x9 0x00000000 0x1 0x40000000>;  /* 5 GiB handoff arena */
	};
```

改为：

```dts
	/*
	 * Single-reg carrier for /chosen/dram-base + /chosen/dram-size.
	 * 12 GiB is the installed physical-DRAM total (ddr_size=0xc; six live
	 * /memory/reg banks sum to 12013 MiB).  This is NOT the DarwinBoot
	 * window and NOT a contiguous usable range: the actual six banks and
	 * the 4..32 GiB hole are described in MemoryMapLib.c, and the window
	 * is owned_memory_size in board.toml.
	 */
	memory@80000000 {
		device_type = "memory";
		reg = <0x0 0x80000000 0x3 0x00000000>;  /* 12 GiB physical total */
	};
```

原因：`devicetree.py:302-307` 强制“恰好一个 memory 节点 + 恰好一组 reg”，并把 `reg` 的 base/size 写进 ADT `/chosen/dram-base`、`/chosen/dram-size`；`devicetree.py:306-307` 又要求 `payload.dram_size` 与它相等。node 名必须跟 reg 的基址一致，所以从 `memory@900000000` 改成 `memory@80000000`；原来 18-28 行的“12 GiB is impossible”注释按上面的新口径改写（12 GiB 物理总量成立，12 GiB 单窗口仍然不可能）。

**注意**：这只是 ADT 元数据。它不会改变 `hw.memsize`；`gDramBase/gDramSize` 的 `is_dram_addr()` 会看到 `[0x80000000,0x380000000)` 这个范围，其中 `[0x100000000,0x380000000)` 是 28 GiB 空洞的前 10 GiB，见 §6.5 的风险与缓解。

### 4.4 第 4 步：UEFI 构建与验证命令

以下命令在 WSL/Linux 侧执行（Windows 路径按 `/mnt/e/...` 映射）；本次只写命令，不执行。

```sh
# 0) 先确认只改了计划中的文件
git -C /mnt/e/hackios/uefi-mondrian diff --check
git -C /mnt/e/hackios/UniXNU-mondrian diff --check

# 1) 构建 UEFI FD（脚本来自 uefi-mondrian/scripts/build-firmware.sh:1-22）
cd /mnt/e/hackios/uefi-mondrian
JOBS=8 bash scripts/build-firmware.sh
FD="Build/mondrianPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd"
sha256sum "$FD"
ls -l "$FD"

# 2) 生成 payload 和 boot image（输出路径以 unixnu status 为准）
cd /mnt/e/hackios/UniXNU
./unixnu build payload -D ../UniXNU-mondrian
./unixnu bootimg \
  --uefi ../uefi-mondrian \
  --dtb ../uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb \
  -D ../UniXNU-mondrian \
  --output mondrian-boot-12g.img
sha256sum mondrian-boot-12g.img

# 3) 只读检查编译后的 hardware DTB 的 memory 节点
dtc -I dtb -O dts -o /tmp/mondrian.dts \
  ../uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb
grep -A3 -E 'memory(@| \{)' /tmp/mondrian.dts

# 4) 只 fastboot boot，不 flash
bash ../UniXNU-mondrian/scripts/k60-device.sh boot /mnt/e/hackios/UniXNU/mondrian-boot-12g.img
```

构建成功后看 `board.toml:44` 约定的 FD 路径：`Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd`。`verify-firmware.py` 的默认根目录仍是旧的 `Mu-Silicium/Build/...`，不要被它的硬编码路径误导；以 `sha256sum`、FD 存在性和实际启动日志为准。

## 5. 每步验证判据

### 5.1 第 1 步（MemoryMapLib）源码/构建判据

```sh
grep -n 'XNU High' E:/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c
```

必须看到：

- `XNU High Arena` 的 size 是 `0x229B78000`，不是旧的 `0x140000000`；
- `XNU High Top Reserve` 的 base/size 是 `0xA69B78000/0x16488000`，且 `0xA69B78000 + 0x16488000 = 0xA80000000`；
- `XNU High Bank C` 的 end = `0x837500000`，`XNU High Bank D` 的 end = `0x839900000`，两者不交叉；
- 所有高段表达式 `base + size` 不进入 `[0x100000000,0x800000000)`；任何跨 4–32 GiB 空洞的 Conv 行直接判失败。

启动时看 `DARWINBOOT` 日志：

- 若 `NO WINDOW`，看 `BIG RUN`；对 8 GiB 窗口应看到接近 `0x229B78000` 的 run（至少不低于 `0x200020000`），且 `FREE` 列表里 `0x840000000 + ...` 存在；
- 若 `BIG RUN` 只有 `0x140000000`（5 GiB），说明新的 `XNU High Arena` 没有被编进 FD 或顶部保留把 E+F 切断了，回到第 1 步查。

### 5.2 第 2/3 步（board.toml + dts）ADT 判据

生成 payload 后，检查 `kernel.macho.adt` 的 `/chosen`：

- `dram-base = 0x80000000`
- `dram-size = 0x300000000`（12 GiB）
- `darwinboot-memory-size` = 当前阶梯值（首轮 `0x130000000`，之后按 §4.2）
- `dts` 编译结果里 `memory@80000000` 的 `reg = <0x0 0x80000000 0x3 0x0>`

最简单的检查：`dtc -I dtb -O dts` 看 `memory` 节点；ADT 用 `scripts/audit-pong-adt.py` 或 `payload.py` 生成的报告看 `/chosen` 三个键。若 `devicetree.py` 报 `payload.dram_size differs from the hardware DTS`，说明 `board.toml:98` 与 dts 的 `reg` size 不一致；若报 `ADT handoff requires one contiguous DRAM range`，说明 dts 被写成了多个 memory 节点/多组 reg，改回单节点单组。

### 5.3 第 4 步（上机）内存判据

**A. `vm_page_bootstrap` 页数。** 这套 XNU 是 4 KiB 页；打印的两个数相加就是窗口字节数除以 4096：

```text
free_pages + wired_pages = memSize / 4096
```

当前 4.75 GiB 的实测：`1,208,993 + 36,191 = 1,245,184`（`usblog-20261107-112028/console.log:17`）。按 §4.2 阶梯：

| 窗口 | `vm_page_bootstrap` 总页数（free + wired） | 允许误差 | 对应 `sysctl hw.memsize` |
|---:|---:|---:|---:|
| 4.75 GiB | 1,245,184 | ±1%（约 ±12,450 页） | 5,100,273,664 |
| 6 GiB | 1,572,864 | ±1% | 6,442,450,944 |
| 7 GiB | 1,835,008 | ±1% | 7,516,192,768 |
| 8 GiB | 2,097,152 | ±1% | 8,589,934,592 |
| 12 GiB（**不应出现**） | 3,145,728 | — | 12,884,901,888 |

如果打印的 `free + wired` 与目标差很多（例如目标 8 GiB 却只有 1.2M 页），不要继续上更大窗口；先查 `memSize` 是否被 ADT 截断或 dts/board 不一致。**看到 3,145,728 页不是 12 GiB 成功，而是 `memSize` 跨了 4–32 GiB 空洞，按 §6.1 立即停止并回滚。**

**B. `/memory/reg` 复核。** 设备在 Android/recovery 时执行：

```sh
adb shell 'od -A x -t x8 /sys/firmware/devicetree/base/memory/reg'
```

应得到 §2 的六组 BE64 base/size；文件级 SHA-256 应为 `729587c3f0c5c469768dce73a833b3ba35fd9abb091ff22e28141ed34fc0cec6`（`live-6033dbec-memory-reg.bin`）。设备在 fastboot 时该命令不可用；只能以已归档的 `live-6033dbec-fdt.dtb`（SHA-256 `95c02052...`）作为基准，不要在 fastboot 状态声称重测过。

**C. iOS 侧 `sysctl hw.memsize`。** 进入 iOS 用户态后：

```sh
sysctl hw.memsize
sysctl hw.memsize_physical
```

`hw.memsize` 必须等于当前窗口的字节数（上表第三列），`hw.memsize_physical` 在当前 DarwinBoot 里与 `memSizeActual` 相同，也应等于窗口；不要拿 `gDramSize`/`dram-size=12G` 当作 `hw.memsize` 的期望值。屏幕上的 `K60RV ... mem=... actual=... managed=...` 与 `K60 MEM` 行是同一判据的辅助证据。

## 6. 风险

### 6.1 arena 跨越 4–32 GiB 空洞（最高优先级）

`[0x100000000,0x800000000)` 是 28 GiB 完全无 DRAM 的空洞（`MEASURED-HIGH-WINDOW-2026-11-02.md:50-53`）。绝不能写成一个 `{0x80000000, 0x300000000}` 的 Conv 描述符：它会让 DarwinBoot/DXE 把不存在的页当作 RAM，`DarwinBoot` 的 `ZeroMem` 在拷贝内核时会取同步外部异常（旧 `[0x100000000,0x380000000)` 的 `ESR 0x96000010`，`MEASURED-HIGH-WINDOW-2026-11-02.md:50-53`）。本方案的做法是**每个真实 bank 一个 Conv，空洞不建描述符**；`dram_size=0x300000000` 只作为 `/chosen/dram-size` 的物理总量声明，不进入 `MemoryMapLib` Conv 列表。

### 6.2 `0x840000000` 基址的 7 GiB 静默失败前科

`0x840000000` 正是 2026-11-02 的 7 GiB 实验基址：loader 接受了 7 GiB 窗口（`window 0x1c0000000`、`HANDOFF EXIT RETURN 0`、绿条），但 XNU 零输出；根因未定，且当时的 7g/8g 内核 SHA `1a18c6a2` 未在 4 GiB 几何下实测，不能排除内核自身回归（`DECISION-MEMORY-12GIB-2026-11-02.md:77-95`）。因此：

- 先把同一内核在 4.75 GiB 窗口、`[0x840000000,...]` arena 上跑一轮；若三数正确且能进用户态，再上 6/7/8 GiB；
- 7 GiB 前按 `DECISION-MEMORY-12GIB-2026-11-02.md:139` 加回入口 stage-bar（蓝条=内核入口已执行、紫条=MMU 前），否则无法区分“trampoline 参数错”和“内核 MMU/pmap 死”；
- 任何一轮“loader 绿条但无内核输出”都直接回滚，不继续加窗口。

### 6.3 GPU/触摸 DMA 抢页

- 高段 arena `0x840000000..0xA69B78000` 与当前显示帧缓冲 `0xB8000000..0xBAD00000`（`MemoryMapLib.c:52`）不重叠，这是好事；但 `0236` 的 `K60 FB` 探针仍必须确认 framebuffer 是 `outside` managed range，不能是 `INSIDE`（`patches/xnu/0236-k60-managed-memory-and-panel.patch:10-56`）。若窗口扩大后 `K60 FB` 变 `INSIDE`，控制台文本会覆盖面板扫描缓冲，表现为花屏/PTE 损坏。
- Adreno 的 BO pool 需要**物理连续** run（参考 `alioth` 的 768 MiB 例子：`E:/k60-work/references/unixnu-site/zh/devices/alioth.md:475`）。把 XNU 窗口推到 8 GiB 会占掉 E+F 的大部分，GPU 侧 768 MiB/1.5 GiB 连续分配可能失败；在 GPU 启用前不要把 `owned_memory_size` 直接锁死 8 GiB，至少保留 0.5 GiB 以上连续余量，或把 GPU pool 的预留页从 arena 中先扣掉。
- 触摸是 GENI-SPI（`spi@990000`，`MemoryMapLib.c:103` 的 QUP MMIO 区），不是大块 DMA；但 `tlmm`/`rsc`/`cmd-db` 都在低区，绝不能因为“低区空闲 435 MiB”就把低区散段全部设成 Conv。低区 A 的碎片本轮不暴露，就是为了避免触摸/PMIC 的 MMIO 与 DXE 分配互相踩。

### 6.4 pong 的 HYP 保留不能直接搬

`uefi-pong/Platforms/Nothing/pongPkg/Library/MemoryMapLib/MemoryMapLib.c:37` 有：

```c
{"HYP Reserved", 0x830000000, 0x10000000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},
```

即 `0x830000000..0x840000000` 共 256 MiB。K60 的 live `/memory/reg` 却把 `0x830000000..0x837500000` 算在段 C 内（`[0x800000000,0x837500000)`）；如果照抄 pong，会从段 C 切掉 117 MiB 并把高区切碎，而且 K60 的 live FDT `reserved-memory` 没有这个节点。`MEASURED-HIGH-WINDOW-2026-11-02.md:65-66` 明确要求“不要盲目照搬 pong 的 HYP 保留”。正确做法：K60 只保留 `:11` 的 `HYP 0x80000000+0x600000`；高区是否有 HYP 必须用 K60 自己的 iomem/secure monitor 证据确认，不能拿 pong 的 `0x830000000` 代填。

### 6.5 `dram-base=0x80000000` + `dram-size=12 GiB` 的 `is_dram_addr` 过覆盖

`gDramBase/gDramSize` 被 `is_dram_addr()` 用来决定 IO 映射的 cache 属性（`osfmk/arm/pmap/pmap.c:5655-5671`）。`dram-base=0x80000000, dram-size=0x300000000` 会让 `[0x80000000,0x380000000)` 中的 `[0x100000000,0x380000000)`（28 GiB 空洞的前 10 GiB）被误判为 DRAM；如果以后有 MMIO 落在这个范围，会从 Device-nGnRnE 变成 posted-combined，属于隐性风险。反过来，高区 `[0x840000000,0xA80000000)` 不在这个 `gDramBase/gDramSize` 里，若高区有 `VM_WIMG_IO` 映射也会被判成非 DRAM。短期没有该范围的 MMIO 时影响为零；若要在 12 GiB 声明下长期运行，建议给 arm64 的 `is_dram_addr` 换成按真实六段 bank 的 bitmap。这个改动属于内核补丁，不在本次 UEFI/DTS 计划内。

### 6.6 12 GiB 名义 vs 12013 MiB 实测

`ddr_size=0xc` 与 SKU 文案支持“12 GiB”，但六段 `/memory/reg` 只合计 12013 MiB；275 MiB 去向未核实（可能在更早的 firmware/XBL 阶段被保留，不在这棵 Linux FDT 的 `/memory` 里）。不要把 12013 MiB 硬说成 12288 MiB，也不要用 `swinfo.fingerprint=mondrian:12` 单独证明硬件容量（TRUST-LEDGER T1）。

### 6.7 DXE 占用与窗口/arena 的 0x20000 偏移

DarwinBoot 的候选基址是 `ALIGN_VALUE(run_start, 2 MiB) + (Kernel->Base & (2 MiB - 1))`（`DarwinBoot.c:453`），K60 的内核块内偏移实测为 `0x20000`（`ISSUES.md:216`）。因此窗口大小 + `0x20000` 必须小于 arena 长度；8 GiB 窗口需要 arena 至少 `0x200020000`，本方案的 `0x229B78000`（8.652 GiB）满足。若 UEFI 在 arena 里分配了页表/DXE 数据，`biggest run` 会变小；启动日志的 `FREE` 列表是唯一可信来源。另：`RamPartitionDxe` 的 UINT32 size narrowing 确实存在，但不是这次 8 GiB/7 GiB 失败的已证明原因（`MEASURED-HIGH-WINDOW-2026-11-02.md:69-70`），不要把它当作“改一行就好”的修法。

## 7. 本次边界

**本次只出方案，不改代码。**

- 只创建/修改 `E:/hackios/UniXNU-mondrian/docs/plans/MEMORY-12G-PLAN.md` 这一个文件。
- 不修改 `E:/hackios/uefi-mondrian/Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c`。
- 不修改 `E:/hackios/UniXNU-mondrian/board.toml`。
- 不修改 `E:/hackios/UniXNU-mondrian/dts/mondrian.dts`。
- 不构建、不生成 boot image、不碰设备、不 flash、不 push。
- 完成后只在 `E:/hackios/UniXNU-mondrian` 本地提交本文件，commit 信息 `docs(memory): plan the 12 GiB arena layout`。

另记一条项目治理事实：`docs/reference/PITFALLS-FROM-HISTORY.md:39-44` 记录“内存窗口问题已封案、不再调整”；本文件不改变该封案状态，只是方案。真要进入 §4 的实施，需要用户先显式重开这个决策，并重新走 `fastboot boot` 验证，不能把本文件当作已批准的上机指令。
