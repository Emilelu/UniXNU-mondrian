# md0 的地址形态：设备写进来的是内核 VA，不是物理地址

`bsd/dev/memdev.c` 的 `mdevadd()` 拿到的是 **页号**，并且把 `vmd0=` 后面的数字原样
当成内核虚拟地址用。两处原文（`CONFIG_MEMDEV_INSECURE` 的解析路径，omap4 树里同一份）：

```c
dev = mdevadd(devid, base >> 12, (unsigned)size >> 12, phys);   /* Go add the device */
```

```c
printf("Added memory device md%x/rmd%x (%08X/%08X) at %016llX for %016llX\n",
    devid, devid, mdev[devid].mdBDev, mdev[devid].mdCDev, base << 12, (uint64_t)size << 12);
```

板上实测（`usblog-20261113-124204` 之前的日志）：

```
Added memory device md0/rmd0 (...) at FFFFFFF0083B5000 for FFFFFFF00A3B5000
```

所以：

- 固件传进来的 `vmd0` 值是 `0xfffffff0083b5000`，即 **物理 `0x83b5000` + 内核段偏移
  `0xfffffff000000000`**；
- 这个 VA 在 `bsd_init` 阶段**没有页表映射**，直接读会 `esr 0x96000004`
  （translation fault, level 0），`far 0x0010000fff0085b3`，pc 落在 `k60_fat_open` 里；
- 正确做法是把 `md0` 的值减去 `0xfffffff000000000` 得到物理地址，再用
  `ml_io_map(phys, size)` 换成可读的内核 VA，然后才交给 FAT 读取器。

同一份 `memdev.c` 用 `base << 12` 打印，正好证明它存的是 VA 页号而非物理页号；
`mdPhys` 标志只在 `pmd0=` 这种物理记忆盘时置位，而板上走的是 `vmd0=`。

## 换算必须在「页」的单位上做

`mdevadd()` 的第 2 个参数是页号，`k60_adsp_note_window()` 收到的也是页号
（实测 `0xfffffff0083b5` 与 `0x2000`，后者 ×4096 = 32 MiB）。因此：

```
phys_pages = va_pages - (0xfffffff000000000 >> 12)      /* = va_pages - 0xfffffff000000 */
phys       = phys_pages << 12
size_bytes = pages << 12
```

先 `<< 12` 再减字节常量会无符号下溢：第一次实现就是这么错的，得到
`phys 0x10000fff0083b5`，`ml_io_map` 返回 `0xfffffff8dd67b3b5`，随后
`esr 0x96000010  far 0xfffffff8dd67b5b3`。页号和字节量混用是这一层的唯一陷阱。

## 大窗口不能用 ml_io_map：io_submap 只有 8 MiB

:



 走 ，所以 32 MiB 的 ramdisk 或 51 MiB 的
ADSP carveout 必然 panic：



 走 （同一文件
:128），kernel_map 足够大，是这条路上唯一可行的映射方式。


## 大窗口不能用 ml_io_map：io_submap 只有 8 MiB

`osfmk/arm/io_map.c:65`:

```c
#define IO_MAP_SIZE            (8ul << 20)
```

`ml_io_map()` 走 `kmem_alloc(io_submap, ...)`，所以 32 MiB 的 ramdisk 或 51 MiB 的
ADSP carveout 必然 panic：

```
K60PANICARGS kmem_alloc(0xfffffff16bfb9240, 33554432, 0x100021): failed with 3 @vm_kern.c:178
```

`ml_io_map_unmappable(phys, size, VM_WIMG_IO)` 走 `kmem_alloc(kernel_map, ...)`（同一文件
:128），kernel_map 足够大，是这条路上唯一可行的映射方式。


## 映射属性：DDR 必须是 cacheable，不是 device

`osfmk/arm/memory_types.h` 的定义：

```c
#define VM_WIMG_DEFAULT  (VM_MEM_COHERENT)                                        // 0x2
#define VM_WIMG_IO       (VM_MEM_COHERENT | VM_MEM_NOT_CACHEABLE | VM_MEM_GUARDED) // 0x7
```

我先按「IO 空间」传了 `0x4`（既不是 DEFAULT 也不是 IO，只有 GUARDED 位），
`pmap_map` 出来的属性非法，第一次读 FAT 引导签名就 **synchronous external abort**：

```
esr: 0x96000010   far: 0xfffffff90efbf1fe   (mapped base + 0x1FE)
```

ramdisk 与 ADSP carveout 都是 DDR，正确属性是 `VM_WIMG_DEFAULT`（0x2）；只有真正的
寄存器/设备窗口才用 `VM_WIMG_IO`（0x7）。
