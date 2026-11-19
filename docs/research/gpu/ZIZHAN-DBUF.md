# zizhan 的扫描目标和我们不一样：它写的是慢不了的那种内存

来源：`E:/hackios/UniXNU-zizhan`（zizhan 的完整移植树）。这一页只记录**可引用的机制**，
不推断没量过的数字。写它的原因：`FLIGHT-CARD-20261119d.md` 的判据 F4 需要提前知道
「如果目标端是慢的那个，下一步长什么样」。

## 1. 我们的目标端是固件帧缓冲

`drivers/PongAdreno/PongAdrenoScanout.cpp:72`

```cpp
scanout=IOMemoryDescriptor::withPhysicalAddress(physical,rounded,kIODirectionInOut);
```

`physical` 来自 `PE_current_console(&video)` 保留的那块固件控制台区间（`:40-77` 的注释解释了
为什么必须用它：Sheng 的 GOP presenter 给的是 device-memory descriptor，而 Pong console 是
`ml_io_map_unmappable()` 映射、`prepare()` 挂不上）。它是**设备内存**，不是内核 DRAM。
GPU 往这里写的每一次都直达 DRAM，没有写合并、没有缓存行。

我们的对照实验（`FLIGHT-CARD-20261119d.md`）就是为了量出这一点的代价：
同样 18.4 MB，`src-to-device`（GPU 自行分配的缓冲）与 `device-to-scanout`（固件帧缓冲）各要多久。

## 2. zizhan 的目标端是「显示缓冲」，有三种来源

`drivers/PongAdreno/PongAdrenoScanout.cpp:480-537` 建立 `db[]`（display buffers），
每个元素是 `{phys, offset}`，三种来源按优先级：

1. **加载器租给它的面板池**（`dbMode==1` 的第一选择）：
   `/chosen` 的 `pong-panel-pool` 属性是两个 `uint64`（`:482-484`，
   `data->getLength()==16` 才认），`lease[0]` 是物理基址、`lease[1]` 是字节数；
   `:489` 要求 `lease[0]` 页对齐且 `lease[0]+lease[1]<=0x100000000ull`（4 GiB 以下）；
   `:492` 用 `IOMemoryDescriptor::withPhysicalAddress(lease[0], n*stride, kIODirectionInOut)`
   整体包住，`:495` 每个 buffer 落一个 `db[]`。
2. **内核自己分配一段物理连续内存**（`dbMode==1` 的第二选择）：
   `:526 IOBufferMemoryDescriptor::inTaskWithPhysicalMask(kernel_task, kIODirectionInOut|kIOMemoryPhysicallyContiguous|kIOMemoryKernelUserShared, bytes, 0xFFFFF000ull)`
   —— 4 GiB 以下、物理连续；`:533` 用 `flush_dcache64(p, bytes, 1)` 把分配器清零留下的脏行刷掉
   （注释：「the allocator's zeroing must not sit dirty over what the GPU writes」）。
3. **退回固件 splash 区间**（`dbMode==2`，`:538-547`）：`end=0xb8000000+0x2b00000`，
   并且要先确认 8 个 SSPP 的源地址区间都不与这块重叠（`:540-545`），否则不启用。

`scanout` 最后指向的**不是**固件帧缓冲，而是这些 buffer（`:550-554`：
`m = dbPool ? dbPool : dbAlloc`，`scanout->release(); scanout = m;`）。

## 3. 因此 presenter 往「槽」里写，DPU 再把面板翻过去

`PongScanoutFrame` 比我们的多三个字段（zizhan `drivers/PongAdreno/PongScanoutWire.h`）：

```cpp
struct PongScanoutFrame {uint64_t sequence,address,bytes,stride;
                         uint32_t width,height,format,token,evict,target;};   /* 56 B */
static_assert(sizeof(PongScanoutFrame)==56 && sizeof(PongScanoutDone)==16,"Pong scanout wire");
```

- `target`：拷贝在 `scanout` 里的**字节偏移**（= 当前 dbuf 的槽位），
  presenter 的 `copyFromBuffer … destinationOffset:frame.target`（zizhan
  `drivers/PongMetal/GpuScanoutPresenter.h`）。
- `token`/`evict`：同一批页再次出现时的导入保留/淘汰令牌，让跨帧复用 GPU 导入变成
  **有内核背书**的合法缓存（我们曾因「无法证明同一虚拟地址仍是同一批页」而删掉了这种缓存）。

代价对比（zizhan 注释，`PongAdrenoNativeGlue.cpp:60-175`）：改用物理连续的内核缓冲后，
扫出那一趟从 **24–35 ms 降到 5–6 ms**（g40/g41）。

## 4. 我们这一侧还缺什么

要走到 zizhan 那条路，缺三样，按依赖顺序：

1. **一个 4 GiB 以下原生物理连续、页对齐的缓冲**，并把它作为 `scanout` 换成 nouveau 目标
   —— **画面不会上屏**（DPU 还在取固件帧缓冲）。

   ⚠️ 2026-11-19 更正：这里原写「只换目标就能拿到 zizhan 的数」，**已被实测否掉**。
   `gpu-blitprobe2-20261119` 的对照实验把同一个 18,432,000 字节、同一个拷贝原语分别投向
   GPU 自有缓冲与固件帧缓冲：`src-to-device=1993 µs` 对 `device-to-scanout=1835 µs`
   （9.25 / 10.04 GB/s），固件帧缓冲甚至略快。所以换目标端本身**不产生任何收益**；
   zizhan 的 5–6 ms 与我们的 12.6 ms 之差来自拷贝**形状**（untile 纹理 vs 单次 copy），
   而形状的根因是 surface 行距 5888 与扫描行距 5760 不相等。要消掉它只有两条：
   让扫描缓冲也用 5888 行距（即自己拥有扫描缓冲），或者干脆不拷贝（DPU 直接扫 surface）。
   两条都需要本节第 1–2 步，所以下面仍按这个顺序做，但**不要**把它当成「换个目标就好」。
2. **DPU/SSPP/SMP 编程**：把面板的取数地址指到新缓冲并做翻转。zizhan 的 `dpuMap` /
   `sspp[]` / `SsppSrc0Addr` 就在同一文件里（`:539-547` 用到了它们），是一整套子系统。
3. **wire 升到 56 B** 并把 `target` 传下来，两侧 `static_assert` 同步。

第 1 步单独就值得先做：它能把「目标端慢」从假设变成数字，而且不需要动 DPU ——
代价是那几帧画面不会更新，判据要写成「对照 blit 的时间」，不是「画面对不对」。

## 5. 尚不能断言的事

- zizhan 的 5–6 ms 是在**它的**面板池上量的；我们没有那块池子的租约
  （`/chosen` 的 `pong-panel-pool` 在我们的 boot 行/DTS 里都没有），所以只能走第 2 种
  （内核分配），而内核分配能否拿到 4 GiB 以下的 18.4 MB 连续块**尚未验证**。
- 我们的固件帧缓冲到底是不是不可缓存、GPU 侧映射属性如何，**没有读回来过**；
  对照实验只能给出「快/慢」的结论，不会告诉我们属性值。

## 6. 面板池的确切契约（照抄 zizhan 的代码，2026-11-19 逐行读出）

这一段的目的：让「谁在什么时候分配多大的什么属性内存、往哪里写、内核怎么读」没有模糊处，
下一个人可以直接照它写固件侧或判断该不该写。

### 6.1 为什么必须由 loader 分配

zizhan 在 `drivers/DarwinBoot24/DarwinBootPkg/Driver/DarwinBoot.c:204-212` 的注释里写死了
理由，逐字：

> zizhan panel pool: 128 MiB below 4 GiB for the DPU (32-bit SSPP addresses, display SMMU
> bypassed), seven 17 MiB buffers … XNU owns no low RAM on this device (the 4 GiB window and
> extra banks all sit above 4 GiB), so the kernel cannot allocate it later (g152i, 2026-10-31);
> reserved here like the audio lease and published as `/chosen/pong-panel-pool` {pa, bytes}.

⇒ DPU 的 SSPP 源地址是 32 位、且显示 SMMU 被旁路 ⇒ 缓冲必须在 4 GiB 以下；
而 XNU 在这个 SoC 上没有任何 4 GiB 以下的页可分配。**这一条不适用于「能不能在内核里
`IOBufferMemoryDescriptor::inTaskWithPhysicalMask` 拿到」**——zizhan 自己那条 fallback
（`:526`）在他们的机器上**永远不可能成功**，他们也这么写了。

### 6.2 loader 侧的四步（`DarwinBoot.c:841-856`）

```c
if (mPanelPoolOffset != MAX_UINTN) {
  PanelAddress = 0xffffffffULL;                       /* AllocateMaxAddress ⇒ 只要 4 GiB 以下 */
  Status = gBS->AllocatePages (AllocateMaxAddress, EfiReservedMemoryType,
                               PANEL_POOL_PAGES, &PanelAddress);
  if (EFI_ERROR (Status)) {
    PanelAddress = 0;
    Print (L"DARWINBOOT24: panel pool SKIP %r after input release\n", Status);
  } else {
    ZeroMem  ((VOID *)(UINTN)PanelAddress, EFI_PAGES_TO_SIZE (PANEL_POOL_PAGES));
    FlushRange(PanelAddress, EFI_PAGES_TO_SIZE (PANEL_POOL_PAGES));
    Print (L"DARWINBOOT24: panel pool PASS 0x%lx, %u pages after input release\n",
           PanelAddress, PANEL_POOL_PAGES);
  }
  WriteUnaligned64 ((UINT64 *)(TreeAddress + mPanelPoolOffset),     PanelAddress);
  WriteUnaligned64 ((UINT64 *)(TreeAddress + mPanelPoolOffset + 8),
                    PanelAddress ? EFI_PAGES_TO_SIZE (PANEL_POOL_PAGES) : 0);
}
```

两个不能省的细节：

1. **时机**：这段在 `FreePool(Image/Tree/TreePath)` **之后**、`GetMap` **之前**。zizhan 的注释
   解释了为什么（`DarwinBoot.c:836-840`）：Wi-Fi 内核的固件 payload 让临时 `ReadFile` 缓冲
   吃掉「唯一一段连续低内存」，所以必须在输入缓冲释放之后再要。
2. **失败也写属性**：`PanelAddress=0` 时属性写 `{0,0}` 而不是不写——内核据此知道自己
   没拿到租约，而不是去读一个没初始化的属性。

`PANEL_POOL_PAGES 32768` = 128 MiB（4 KiB 页）。ADT 侧只需一个 16 字节属性
`pong-panel-pool`，`AdtNode()` 里用 `PanelCandidate`/`mPanelPoolOffset` 定位（`:314-315`
只接受 `Path==1` 且只认第一次出现，重复属性直接判错）。

### 6.3 内核侧怎么用（`PongAdrenoScanout.cpp:477-500`）

```cpp
uint32_t usePool=1;(void)PE_parse_boot_argn("pong_panel_pool",&usePool,sizeof usePool);
uint64_t lease[2]={};
if(usePool) { /* /chosen 的 pong-panel-pool，长度必须正好 16 */ }
const uint64_t stride=rounded>SlotStride?rounded:SlotStride;   /* 每个池缓冲一个槽宽 */
zizhan_panel_pool::Layout poolLayout{};
if(lease[0] && !(lease[0]&4095) && lease[0]+lease[1]<=0x100000000ull &&
   zizhan_panel_pool::plan(lease[1],stride,want,DbMax,SlotMax,&poolLayout)) { … }
dbPool=IOMemoryDescriptor::withPhysicalAddress(lease[0],uint64_t(n)*stride,kIODirectionInOut);
for(unsigned i=0;i<n;++i){db[dbN]={lease[0]+uint64_t(i)*stride,uint64_t(i)*stride};++dbN;}
```

四条硬校验：`lease[0]` 非 0、页对齐、`lease[0]+lease[1] <= 4 GiB`、`plan()` 成立。

`zizhan_panel_pool::plan()`（`drivers/PongPower/ZizhanPanelPool.h:14-33`）的算法：
`total64 = pool_bytes / stride`；`buffers` 取 `requested_buffers`（<2 抬到 2），上限
`db_capacity-1`、再上限 **3**、再上限 `total64`；`slots = total64 - buffers`，上限
`slot_capacity` 与 `db_capacity-1-buffers`。

### 6.4 我们的数字（K60，1440×3200，行距 5760）

| 项 | 值 |
|---|---|
| 每个缓冲 | 5760 × 3200 = **18,432,000 B** |
| 池大小 | 32768 × 4096 = 134,217,728 B（128 MiB） |
| `total64` | ⌊134,217,728 / 18,432,000⌋ = **7** |
| `buffers` | min(3, 7) = **3**（内核自己的翻转缓冲） |
| `slots` | 7 − 3 = **4**（backboardd 的画布槽） |

正好七块（zizhan 那边是七块 17 MiB），所以 32768 页这个常量可以照搬，不需要按机型改。

### 6.5 落地顺序与判据

1. **固件**（`uefi-mondrian` 的 `Platforms/Xiaomi/DarwinBootPkg`）：加 `PANEL_POOL_PAGES`
   预留 + `/chosen/pong-panel-pool` 发布；判据是 boot log 出现
   `panel pool PASS 0x…, 32768 pages after input release`，且 `/chosen` 里属性长度 16、
   地址 < 4 GiB、页对齐。**这一步不改变任何画面**，可单独验证。
2. **内核**：读属性、`plan()` 出 3+4、把 `scanout` 指到第 0 块。判据是出现
   `PONG DBUF: pool … buffers=3 slots=4`，且 `copy` 变成同一行距的单次拷贝
   （`encode` 应落到 1 ms 量级）。**此时画面会停在最后一帧**，所以判据里不得包含
   「画面正确」。
3. **DPU**：`dbFindPipes()`/`intfProbe()`/`dpuMap()`/`sspp[]`（zizhan 同一文件
   `:520-620`），把面板取数地址指到池并做翻转，再开 `pong_panel_slot_take` 让
   backboardd 直接拿槽。判据是面板真的出现新帧（`scanout frames` 与实际画面同步）。

第 1 步是纯固件、可独立上机验证、失败也不影响现有启动路径；第 2 步开始才需要
「画面不上屏」的接受书；第 3 步是唯一能把 18.4 MB 拷贝彻底消掉的一步。
