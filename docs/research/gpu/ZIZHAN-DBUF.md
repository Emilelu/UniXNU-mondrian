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
   —— 只换目标就能拿到 zizhan 的数，但**画面不会上屏**（DPU 还在取固件帧缓冲）。
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
