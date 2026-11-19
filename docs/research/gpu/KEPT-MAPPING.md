# 保留映射（token/evict）的设计草案

写于 2026-11-19，在 `gpu-vaddr-20261119` 起飞之前。**这不是已经采纳的方案**：飞行卡 i 的
F3 明确写着，如果地址会重复而导入仍然贵（H2），就**不要**动这件事，先去 bridge 的
`HostMemory` 路径查。这里只把「如果 H1 成立，要改哪几处」写清楚，免得下次重新推导一遍。

## 1. 要解决的问题（两条，可能是同一个原因）

| 症状 | 证据 | 位置 |
|---|---|---|
| 每帧导入 18.4 MB 有时 63 µs、有时 15,000 µs | `usblog-20261119-125434` 帧 1/3/5 贵、2/6 便宜 | `drivers/PongMetal/GpuScanoutPresenter.h` 的 `newBufferWithBytesNoCopy` |
| 映射只增不减 | 6 帧 198 次映射 / 9 次解映射；320 次采样后 `outstanding` 仍在涨 | `drivers/PongAdreno/submit/NativeAdrenoVm.cpp:390` 的 `lifetime` 行 |

如果 H1 成立，两条都来自「presenter 每帧对同一个 surface 新建一次导入」，而内核在
`PongAdrenoScanout.cpp:202` 每帧 `map->release()`，所以下一帧拿到的是个新的用户 VA。

## 2. 内核侧（`drivers/PongAdreno/PongAdrenoScanout.cpp`）

zizhan 的实现已经读过，形状如下（`E:/hackios/UniXNU-zizhan/drivers/PongAdreno/PongAdrenoScanout.cpp`）：

- `struct Kept {IOMemoryDescriptor *source; size_t offset, bytes; IOMemoryDescriptor *memory;
  IOMemoryMap *map; uint32_t token; uint64_t used;};` 加 `constexpr unsigned KeptCount=4;`（`:105-107`）。
  注释原文：「Mappings kept per compositor surface (CoreAnimation cycles a few), so the presenter
  can keep its GPU import instead of re-importing 16 MiB a frame.」
- `Pending` 增加 `int slot; uint32_t evict; IOMemoryDescriptor *evictMemory; IOMemoryMap *evictMap;`（`:98-99`）。
- 交付时 `pending.map=map; if(pending.slot>=0){kept[pending.slot].map=map;token=kept[pending.slot].token;}`
  并把 `token`/`evict` 写进 `PongScanoutFrame`（`:1062-1065`）。
- `Complete` 里「让本帧不保留的东西在这里释放」：`drop(pending.evictMemory,pending.evictMap)`（`:1372`）。
- 开关 `pong_scanout_cache`（默认 1，`:980`）。

我们要改的等价物：`Pending`（本仓 `drivers/PongAdreno/PongAdrenoScanout.cpp` 的 `struct Pending`）加
`slot/evict/evictMemory/evictMap`；`pong_scanout_frame` 按 `(source, offset, bytes)` 找槽；
`Complete` 把本帧的 `map/memory` 移进槽，只释放被 `evict` 的那一个。**默认关**（`pong_scanout_cache=0`
起步），因为保留映射就是保留了内核资源，必须能一键退回当前行为。

## 3. wire（`drivers/PongAdreno/PongScanoutWire.h`）

现在 `struct PongScanoutFrame {uint64_t sequence,address,bytes,stride;uint32_t width,height,format,reserved;};`
= 48 B。zizhan 是 56 B：

```c
struct PongScanoutFrame {uint64_t sequence,address,bytes,stride;
                         uint32_t width,height,format,token,evict,target;};
static_assert(sizeof(PongScanoutFrame)==56,"Pong scanout wire");
```

`static_assert` 会抓住两侧不一致——这是这条改动能安全落地的唯一原因。`target` 我们用 0
（我们拷进固件帧缓冲，没有 `db[]`）。

## 4. presenter 侧（`drivers/PongMetal/GpuScanoutPresenter.h`）

我们 11-18 删掉的那个缓存**按 `(base, bytes)`** 做键，那是不安全的，因为内核每帧就 `release()`。
正确形状是按 **token** 做键：

```objc
if (frame.token && imported_ && importedToken_ == frame.token) { /* reuse */ }
else { imported_ = [device_ newBufferWithBytesNoCopy:...]; importedToken_ = frame.token; }
```

`frame.token == 0` 时必须每帧新导入（内核没有背书这帧的映射会被保留），这条要写成测试。

## 5. 验收判据（下一张卡用）

- 保留映射开启后 `imports==frames` 仍然成立，且 `import` 稳态中位 < 500 µs；
- `PONG VM: lifetime` 的 `outstanding` 在长跑里**不再单调增长**（这是 P-244 的正面判据）；
- 关掉 `pong_scanout_cache` 时回到今天的行为（同样的 `import` 双峰），证明开关真的起作用；
- 出现任何 `CP/SMMU fault`、`GPU copy not retired`、画面破损 ⇒ 立刻回退，且回退后必须重飞一次证明回退有效。
