# 20 — 把 cellular 这一线搬到 iOS 27：现在的账与搬法

日期：2026-11-20（05:33 对真实 27 树做过一次干跑）。范围：`patches/xnu/062*`（基带与 IPA）与 `drivers/PongCellular/`。

## 1. 边界

27 侧 cellular 在 SpringBoard 打通前不动：新 main 从 stage-0 起，主仓归档为 `archive/ios16-20261120`。
本文回答一个问题——**等 27 能起桌面了，这条线要按什么顺序、改哪些地方搬过去**；同时在 16 线上把与页大小/内核版本有关的隐患先拆掉。

## 2. 这条线在 16 线上由六个补丁组成

| 补丁 | 大小 | 碰的是什么 | 27 树上的干跑结果 |
|---|---|---|---|
| `0620-k60-modem-image.patch` | 8,158 B | 新增 `bsd/dev/pong_modem_image.{c,h}`、`pong_modem_table.h` | **apply 干净** |
| `0621-k60-modem-pas.patch` | 21,440 B | 新增 `pong_modem_boot.c`、`pong_modem_pas.{c,h}`，并在 `bsd/kern/kern_exec.c` 插一处调用 | 新增部分干净；**call site 不 apply**（`kern_exec.c:7834`） |
| `0622-k60-modem-qrtr.patch` | 170,730 B | 12 个 `bsd/dev/` 新文件（QRTR、GLINK、RMTFS、EFS、memshare、SMP2P） | **apply 干净** |
| `0623-k60-ipa.patch` | 174,551 B | 新增 `pong_ipa*.{c,h}` 十一对 | **apply 干净** |
| `0624-k60-ipa-call-site.patch` | 596 B | `kern_exec.c` 第二处调用（`k60_ipa_probe_from_handoff()`） | **不 apply**（`kern_exec.c:7930`） |
| `0621-k60-io-submap-budget.patch` | 1,712 B | `osfmk/arm/io_map.c` 的 `IO_MAP_SIZE` 8 MiB → 32 MiB | **不适用**：27 的 `io_map.c` 已没有这个宏（见 §6） |

`series` 里它们的顺序（16 线第 225–230 行）是：0620、0621-pas、0622、0623、0624、0621-io-submap。

## 3. 编号撞车，搬过去必须先重排（Lead 2026-11-20 05:40 批准）

27 线的 `patches/xnu-12377/series` 与 16 线的 `patches/xnu/series` 是两个独立命名空间，`06xx` 在 27 线上全空（现有只到 `05xx`），所以：

| 16 线 | 27 线 | 内容 |
|---|---|---|
| 0620 + 0621 的新增部分 | `0626-k60-modem-image.patch` | 镜像段表 + `pong_modem_boot.c`/`pong_modem_pas.{c,h}` |
| 0622 | `0627-k60-modem-qrtr.patch` | QRTR / GLINK / RMTFS / EFS / memshare / SMP2P |
| 0623 | `0628-k60-ipa.patch` | IPA 十一对文件 |
| 0621 / 0624 的两处调用 | `0629-kern-exec-call-sites.patch` | 合成一个补丁 |
| 0621-k60-io-submap-budget | 不搬 | 见 §6 |

series 行尾注释按 Lead 要求写「ported from 16 line 0620..0623」，方便两线对账。
把 0621 的新增部分并进 0626 而不是另开一号，是因为 Lead 批的三个号要正好对应三组只加文件的补丁；
若要 0621 单独占号，只改 `scripts/port-cellular-to-xnu27.py` 里的映射表即可（§12）。
## 4. 页大小：唯一的硬编码已拆掉

16 线是 16 KiB 页，27 线用 4 KiB 页。盘点下来只有一处按 4 KiB 写死：

- `drivers/PongCellular/K60ModemLink.c` 的 `k60_qrtr_rmtfs_low_alloc()`：`max_pnum` 上限原写 `((1ull << 32) - bytes) >> 12`。
  已改成 `((1ull << 32) - bytes) / ptoa_64(1)`——`max_pnum` 的单位是物理页，除以真实页大小后「低于 4 GiB」在两种页大小下意思一致（提交 `1b842ff6`）。
  4 KiB 内核上结果与旧式完全相同，所以 16 线行为不变。

其余位置都是页大小自适应的：`round_page()`/`ptoa_64()`/`pmap_find_phys()` 按内核自己的页大小工作；`K60_MODEM_PROBE_PAGE 0x1000` 是映射长度，`ml_io_map` 会向上取整；**`K60_IPA_GSI_PAGE_SIZE 0x1000` 不能改**——那是 GSI 硬件的 TRE 环粒度（`_Static_assert(K60_IPA_GSI_TRE_BYTES * K60_IPA_GSI_TRE_COUNT == 0x1000)`），与 VM 页无关。

### 4.1 27 侧 API 与 4 KiB 常量的逐项核对（2026-11-20 06:00）

四个补丁共引用 8 个内核符号，逐个在 `/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc` 里查过：

| 符号 | 27 树里的位置 | 结论 |
|---|---|---|
| `ml_io_map_unmappable` | `osfmk/arm/machine_routines.h:611` | 有，签名不变 |
| `kmem_alloc_contig` | `osfmk/vm/vm_kern_xnu.h` | 有；第 5 参数仍是 `max_pnum` |
| `ptoa_64` | `osfmk/vm/vm_kern.c` 等 | 有，唯一 VM 页换算点已改用它 |
| `flush_dcache64` | `osfmk/arm/caches_internal.h:43`（实现 `osfmk/arm64/caches_asm.s:440`） | 有 |
| `pmap_find_phys` | `osfmk/arm64/pmap.c` 等 | 有 |
| `PE_parse_boot_argn` | `osfmk/console/video_console.c` 等 | 有 |
| `kernel_map` / `kmem_free` | `osfmk/vm/vm_kern.c` | 有 |
| SMC 调用 | **27 树没有 `scmCall`** | 不受影响：我们自带 `__asm__ volatile("smc #0" ...)`（`drivers/PongCellular/K60ModemPas.c:34`），从 Pong 那套 `scmCall` 依赖里摘出来了 |

4 KiB 常量盘点（只有第一条曾是风险，已修）：

| 位置 | 性质 | 判断 |
|---|---|---|
| `k60_qrtr_rmtfs_low_alloc()` 的 `>> 12` / `ptoa_64(1)` | VM 页 | **已改**为 `ptoa_64(1)`，16 KiB 与 4 KiB 内核同义 |
| `K60_MODEM_PROBE_PAGE 0x1000` | `ml_io_map_unmappable` 的**字节长度**（只看 carveout 头部的载体） | 不是页粒度，16 KiB 内核下照样映射 |
| `K60M_ASSIGN_RECORD 4096u` | SCM 内存归属记录的 scratch 尺寸（Pong 原样 4 KiB 记录） | 与页大小无关 |
| 0622 的 `k60_modem_map(K60_MODEM_IPCC_BASE, 0x1000)` | IPCC 寄存器块字节长度 | 寄存器块 4 KiB，与 VM 页无关 |
| 0623 的 `0x1000` / `/4096u` / `K60_IPA_GSI_PAGE_SIZE` | GSI 的 TRE 粒度、SMMU4K 叶表粒度 | **硬件粒度**，16 KiB CPU 页不能改它 |

### 4.2 头文件与内核宏：27 树全部可用（2026-11-20 06:02）

八个 carried 文件共 `#include <...>` 13 个头文件，逐条在 27 树里 `find` 过：

- 10 个内核头全部命中（`osfmk/arm/machine_routines.h`、`osfmk/vm/vm_kern.h`、`osfmk/kern/*.h`、`pexpert/pexpert.h`、`osfmk/mach/*.h` 等）；
- 只有 `stdint.h` / `stddef.h` / `stdbool.h` 报 MISSING —— 那是编译器自带的，不进内核树。

内核宏逐个核对（我们源码里实际用到的）：

| 宏 | 27 树位置 | 结论 |
|---|---|---|
| `KMA_DATA` / `KMA_ZERO` / `KMA_NOFAIL` | `osfmk/vm/vm_kern.c` | 有，语义不变 |
| `VM_KERN_MEMORY_IOKIT` | `osfmk/mach/vm_statistics.h` | 有 |
| `VM_WIMG_DEFAULT` | `osfmk/arm/memory_types.h` | 有 |
| `round_page` | `osfmk/mach/vm_param.h` | 有 |
| `kernel_map` | `osfmk/vm/vm_kern.h` | 有 |

两件值得写下来的事：

1. **27 的 `PAGE_SHIFT` 是运行期变量**：`osfmk/mach/arm/vm_param.h:60-72` 里 `PAGE_SHIFT_CONST 12` 与 `extern int PAGE_SHIFT_CONST` 并存，`PAGE_SIZE` 由 `1 << PAGE_SHIFT` 得出。这从上游侧证实了 `>> 12` 在 27 上必错、`ptoa_64(1)` 必对——§4 的那次修改不是预防性洁癖。
2. **`KMA_PERMANENT` 只剩 IPA 一处，是安全的**：`drivers/PongCellular/K60Ipa.c:892` 用它分配 IPA 的 filter/route 区，而该文件**没有任何 `kmem_free`**（`grep -n kmem_free K60Ipa.c` 空），生命周期到重启为止；k47 那次 panic 的死因是「永久映射 + 后释放」，RMTFS 那条路径已经去掉永久标志。

## 5. call site：不 apply 的原因不是行号，是上下文块在 27 上还不存在

16 线的两处调用挂在 `main` 的 K60 data-mount 补丁（`0614`）里那段 `native_owner_data_stage = 3; vnode_lookup("/private/var", …)` 尾巴上。
干跑显示 27 的 `kern_exec.c`（9,078 行，`feeds/xnu-3199e8bc`，git `ac9718f`）里既没有 `native_owner_data_stage`，也没有那段 `vnode_lookup`——那段本身也是要在 27 上先落的补丁。
所以顺序是：**先把 data-mount 补丁搬到 27，再在它的新位置后面接两处 probe**。接法（P-155）：

```
cp <27 tree>/bsd/kern/kern_exec.c /tmp/kern_exec.27.c
$EDITOR /tmp/kern_exec.27.c        # 在 data-mount 块的尾部插 k60_modem_probe_from_handoff() 与 k60_ipa_probe_from_handoff()
diff -u <27 tree>/bsd/kern/kern_exec.c /tmp/kern_exec.27.c > 0627-kern-exec-call-sites.patch
```

顺序不能反：modem 的 probe 读 payload FAT 里的 `md0`，IPA 的 probe 复用同一份 metadata。

### 5.1 锚点契约（给 27 侧 data-mount 用）

16 线两段 probe 的位置不是随便挑的：它们嵌在 `native_owner_data_prepare(proc_t p, user_addr_t scratch)`
里（函数起于 16 线构建树的 `bsd/kern/kern_exec.c:7803`），紧贴数据卷从「只读准备」切到可写阶段的
`native_owner_data_stage = 3;`（同文件 :7941）之前——因为基带要求 Data 已挂载才能读 EFS。

所以 27 侧只要满足一条：**新写的 data-mount 里把 stage 推进到 3 的那一行之前**，插两段 probe。
`scripts/port-cellular-to-xnu27.py` 的缺省锚点就是这个字符串，语句名一致时不用带 `--anchor`；
若 27 用了别的写法（`stage = 2`、`kNativeOwnerDataStageWritable` 等），用 `--anchor "<原文>"` 指给新行。

### 5.2 锚点可以自动找（`--anchor-auto`）

等 Lead 的 data-mount 落地期间，生成器已经把「找锚点」做成一条命令的一半：

```sh
python3 scripts/port-cellular-to-xnu27.py --tree <27树> --out patches/xnu-12377 --anchor-auto
```

`find_anchor()` 分两级找：先找含 `native_owner_data_stage` 且以 `;` 结尾的行（探针要紧贴把 stage 推到 3 的那一行），
找不到再退到 `native_owner_data_prepare(` 或 `vnode_lookup("/private/var"`。恰好一行才返回，
零行说 `no line stages the Data mount yet`（当前真实 27 树就是这条），两行及以上说 `anchor is ambiguous`
并列出行原文——**绝不猜**。找到时先打印 `K60 PORT27 anchor <原文>`，再照常写 0626/0627/0628/0629。

自测覆盖三种树（一行、两行、零行），输出 `K60 PORT27 PASS renumbering, anchor insertion, auto anchor, refusal,
verification, series, build list`；readiness 里 `anchor lines=0` 一行仍是 note，不影响 exit code。

### 5.3 一个「补丁之间会不会打架」的不变量

三条补丁都是新增文件，所以各自 `git apply --check` 通过并不等于**顺序打完**也通过——两个补丁若都
新建 `bsd/dev/pong_modem_link.c`，第二条必然失败，而逐条检查永远看不见。readiness 因此多了一行：

```
K60 READY ok   all 36 sections create new files, no target twice
```

判据是「每个 `+++ b/` 段落都有一个 `new file mode` 与它配对」加上「路径集合两两不交」。任一不成立就
`DRIFT` 并点名是哪个补丁的几比几、或哪个文件被两条补丁同时碰（`patch_sections()`）。

同一段还断言 0629 要调的两个入口确实由前面的补丁提供（`k60_modem_probe_from_handoff` 在 0626、
`k60_ipa_probe_from_handoff` 在 0628）：`K60 READY ok   both probe symbols are defined by the patches`。否则 0629 打完会在链接期报未定义。

## 6. `0621-k60-io-submap-budget` 在 27 上没有对应物

16 线的 `osfmk/arm/io_map.c` 有一张所有调用者共用的 8 MiB `io_submap`，`kmem_alloc(io_submap, …, KMA_NOFAIL)` 撑爆时会 panic（P-219），所以才把宏抬到 32 MiB。
27 的 `io_map.c` 只有 117 行，`IO_MAP_SIZE` / `io_submap` / `io_range` **都不存在**了，改法变成：

- VM 初始化前（`startup_phase < STARTUP_SUB_KMEM`）：从 `virtual_space_start` 往上偷地址空间，`pmap_map_bd`；
- VM 初始化后：`kmem_alloc(kernel_map, …, KMA_NOFAIL | KMA_PAGEABLE | KMA_IO)`，再 `pmap_map`。

也就是说 27 上没有「一张固定大小的子图」这回事，P-219 的失败模式不再以同样形式存在，这个补丁**应当判为 not-applicable 而不是搬**。
我们的调用点都在 exec 之后（`startup_phase >= STARTUP_SUB_KMEM`），走的是 `kmem_alloc(kernel_map, …)` 那条分支，所以早期 `virtual_space_start` 窗口（由 `osfmk/vm/vm_resident.c:2352` 的 `pmap_startup()` 给出）与我们无关；27 上唯一的余量问题退化成「`kernel_map` 够不够」，与 16 线同一量级。

**结论：这个补丁不搬**（not-applicable）。

27 上的等价机制就是上面两条分支本身：早期 `virtual_space_start`（`pmap_startup()` 给出的窗口），之后 `kmem_alloc(kernel_map, …)`。
16 线的 0626 号（`0621-k60-io-submap-budget`）在 27 上**没有对应的 062x**，看到清单时不要以为漏搬了。

## 7. 生成产物的重建链

`0622` 与 `0623` 不是手写的：

- `scripts/update-modem-qrtr-patch.py` ← `drivers/PongCellular/K60Modem*.{c,h}` + `K60Smem.h` + `QcomGlink.{c,h}` + `K60PmicRail.h`，把 `#include "K60…"` 改名成 `pong_…`，写盘前检查条件编译配平、carried 文件不得残留 `K60…`/`Qcom…` 头名；
- IPA 那台对应 `0623`，同样按 `FILES` 逐段重建。

搬到 27 树后先跑两台生成器，再跑 `scripts/tests/test-k60-modem-image.py`（30 段、地址连续）——这两步能证明 carried 副本与源码一致，不需要编内核。

### 7.1 27 上存储数据面会「优雅地拒绝」，不会链接失败

`0627`（= 16 线的 0622）里，`k60_qrtr_rmtfs_rw` 的块读走 `native_pong_ufs_read_named_volume()`，
而 27 树没有 `drivers/NativeUfs`。0622 里那是一个**同文件弱定义兜底**（`__attribute__((weak))` 外部引用在静态映像里不成立，k51 链接期踩过）：

```c
+native_pong_ufs_read_named_volume(const char *name, uint64_t offset,
+    uint8_t *buffer, size_t length)
+{
+	(void)name; (void)offset; (void)buffer; (void)length;
+	return 0;
+}
```

调用点是 `if (native_pong_ufs_read_named_volume(...) == 0) { return -1; }`，所以 27 stage-0 的行为是：

- 内核**能编能链**（不需要先搬 `drivers/NativeUfs`）；
- modem 的 RMTFS 读请求会拿到 `result 1`（拒绝），而不是 panic 或脏数据；
- 等到 UFS 只读入口搬过来、`KERNEL_EXTRA_ARCHIVES` 里的强定义胜出，同一份 `0627` 不改一行就变成真读。

代价是**静默**：兜底那句不打印，飞行日志里只会看到 modem 的 rw 没被服务。等 k54 上机前要给它补一行 `printf`（`printf` 在内核里可用），否则 27 上分不清「UFS 没搬」和「分区名不对」。这条已记入 §9 的待办。

## 8. 搬之前就能在 16 线上做掉的验证

| 项 | 命令 | 期望 |
|---|---|---|
| carried 一致 | `python3 scripts/update-modem-qrtr-patch.py --check` | 无 stale |
| 镜像布局 | `python3 scripts/tests/test-k60-modem-image.py` | `TESTS OK 30 segments` |
| 宿主逻辑 | `bash /mnt/e/k60-work/artifacts/run-host-tests.sh` | 28 行 PASS |
| 记录一致 | `K60_DEVICE_INPUT=… python3 scripts/porting-gate.py --quick` | 通过 |

## 9. 27 侧还需要决定的事

1. **UFS 只读入口的归属**：`native_pong_ufs_read_named_volume()` 现在挂在 `drivers/NativeUfs/PongUfsTransport.cpp`，是 Lead 授权的只读新增。27 树的 NativeUfs 若与 16 不同源，这个入口要重新谈一次。
2. **Data 命名空间**：Pong 的注释写明 RF 初始化会立刻要求读写文件，所以 PAS 必须在 native Data 挂载之后（`PongModemRuntime.cpp:271-277`）。27 的挂载时机要先测出来。
3. **sysmon 接线**（k54）：`K60ModemSysmon.*` 已写好并有宿主测试，但没有调用者、没进 0622；它属于版本无关的硬件契约，可以安全一起搬。
4. **IPA 的 SMMU 口径**：`b9de56b9` 放宽了 `ArmSmmu4K` 对 Device-nGnRE（writeback=2）的限制，仍在 `drivers/PongAdreno/ArmSmmu4K/` 里，搬 27 前需要那棵树的主人确认它是否已经吸收。

## 9.1 IPA 运行期分配没有页上限（27 线已修，见 §34）

`drivers/PongCellular/K60Ipa.c:892` 的 `kmem_alloc_contig(kernel_map, &address, bytes, mask, 0, 0, ...)` 第 5 参数传 0，
即不限制物理页，只靠分配后的 `ptoa_64(page)+bytes > 1<<36` 检查拒绝——命中就返回 `K60IpaRuntimeFailed`，不重试。
16 线上没暴露（IPA 没打开过），27 的内存布局未必一样。若要补，照 RMTFS 的写法给 `max_pnum` 一个 36 位上界并保留一次重试；
因为改的是 IPA 路径、本线当前无法上机验证，先记录不动。

**2026-11-20 11:45 更新**：27 线已经落了这个修法（§34），0623 与 0628 重新生成；16 线（`feat/cellular`）的 `K60Ipa.c` 一行没动，因为 k54 镜像必须能由 HEAD 复现，随 k55 一起落。

## 10. 干跑记录（2026-11-20 05:32，只读）

树：`/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc`（git `ac9718f`，`kern_exec.c` 9,078 行、`io_map.c` 117 行、`osfmk/arm` 与 16 线同布局）。
命令：对六个补丁逐个 `git apply --check -v`，没有任何写操作。

| 补丁 | 结果 |
|---|---|
| 0620 | 三个文件全部 `Checking patch …` 通过 |
| 0621 | `error: patch failed: bsd/kern/kern_exec.c:7834`（新增的三个文件本身没问题） |
| 0622 | 十二个新文件全部通过 |
| 0623 | 十一个新文件全部通过 |
| 0624 | `error: patch failed: bsd/kern/kern_exec.c:7930` |
| 0621-io-submap | `error: patch failed: osfmk/arm/io_map.c:62`（宏已不存在） |

## 11. 解除封锁后的顺序

1. SpringBoard 在 27 打通；
2. 搬 data-mount 补丁，再按 §5 生成 call-site 补丁（0626/0627）；
3. 跑两台生成器搬 `0628`/`0629`，`test-k60-modem-image.py` 过；
4. `io-submap` 判 not-applicable，改为量一次 `virtual_space_start` 窗口（§6）；
5. 第一飞只用 `pong_modem` + `pong_qrtr=2`，判据沿用 `scripts/judge-cellular-flight.py`——它只看日志行，与 OS 版本无关。

## 12. 生成器：scripts/port-cellular-to-xnu27.py

把重排与 call site 重生成做成一条命令，避免手抄：

```
python3 scripts/port-cellular-to-xnu27.py --tree <27 XNU 树> --out <输出目录>
python3 scripts/port-cellular-to-xnu27.py --tree <27 XNU 树> --out <输出目录> --anchor "native_owner_data_stage = 3;"
```

缺省锚点就是 data-mount 块里那行；Lead 落地后指向新行号即可。它做四件事：

- `0626` = 0620 全文 + 0621 去掉 call-site hunk 后的部分；
- `0627` = 0622 原样，`0628` = 0623 原样；
- `0629` 在 `kern_exec.c` 的锚点行前插入两段 probe（先 modem 后 IPA），再用 unified diff 生成；
- 锚点缺失或命中多行 → 退出码 2 并打印命中次数；`--self-test` 在临时树里验证「重排 + 插入 + 拒绝」三件事（输出 `K60 PORT27 PASS renumbering, anchor insertion, refusal`）。
- `--verify` 对产出的每个补丁跑 `git -C <27 树> apply --check`，逐条打印 `K60 PORT27 VERIFY 0626 ok`；锚点缺失时 0629 记 `skipped (not produced)`，其余三条照样验证，退出码仍是 2。

2026-11-20 05:55 `--verify` 对真实 27 树实跑：

```
K60 PORT27 FAIL anchor 'native_owner_data_stage = 3;' matches 0 lines, need exactly one
K60 PORT27 VERIFY 0626 ok
K60 PORT27 VERIFY 0627 ok
K60 PORT27 VERIFY 0628 ok
K60 PORT27 VERIFY 0629 skipped (not produced)
rc=2
```

2026-11-20 05:41 对真实 27 树跑过：三个只加文件的补丁全部 `git apply --check` rc=0；`0629` 因为锚点还不存在而按设计拒绝（退出码 2）。


**series 行格式（2026-11-20 06:08 修正）**：`series-port.txt` 一度把注释写在文件名后面，那是错的——
两个消费方都按「整行就是路径」解析：16 线 `scripts/porting-gate.py:416` 对整个 series 做 `.split()`，
27 线 `check-blob-patches.py:60-80` 只跳过以 `#` 开头的行、其余整行当相对路径。行尾注释会被当成文件名。
现在注释全部独占一行，`--self-test` 也加了守卫：任何非注释行含空格或不以 `.patch` 结尾即失败
（输出 `K60 PORT27 PASS renumbering, anchor insertion, refusal, verification, series`）。
另外 `series-port.txt` 改为**先写后验锚点**：锚点缺失时它照样产出，方便先把 series 准备好。
## 13. 就绪检查：scripts/check-ios27-readiness.py

§4、§4.1、§4.2 的每一条都是「某天在某个 27 树上量到的」，27 树会往前走。把测量值写死在脚本里，
变化时一条命令就会喊出来，不必等补丁打不上才发现：

```
python3 scripts/check-ios27-readiness.py --tree /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc
```

它核对四类预期，全部打印成 `K60 READY ok|DRIFT|note` 行：

- 六个 16 线补丁的 `git apply --check` 返回值（0620/0622/0623 期望 0；0621、0621-io-submap、0624 期望 1，各自附原因）；
- 8 个内核符号是否仍能在 27 树里 grep 到；
- `drivers/PongCellular/*.[ch]` 里 13 个 include 是否都能在 27 树里找到；
- `bsd/kern/kern_exec.c` 里锚点 `native_owner_data_stage = 3;` 的行数（现在应为 0，data-mount 落地后变 1，提示可以生成 0629）。

退出码：0 全部符合预期、1 有漂移、2 树不存在或缺 `kern_exec.c`。2026-11-20 06:04 实测：

```
K60 READY ok   0621-k60-modem-pas.patch rc=1 (its call-site hunk waits for the 27 data mount)
K60 READY ok   8 kernel symbols present
K60 READY ok   13 includes resolve
K60 READY note anchor lines=0 (expected 0 until the data mount lands)
K60 READY OK every recorded expectation still holds
```

漂移路径也验过：指向 16 线 feed 树时它报 `K60 READY DRIFT 0621-k60-io-submap-budget.patch expected rc=1 got rc=0`、
`K60 READY CHANGED 1 expectation(s) drifted`、退出码 1；`--self-test` 输出 `K60 READY PASS expectations compared, drift detected`，已进宿主套件。

## 14. 构建接线：补丁只放文件，`bsd/conf/files` 要另一条腿

2026-11-20 06:11 审计三个 port 补丁的实际文件表（脚本内 `conf_entries()` 直接读补丁的 `+++ b/` 行）：

| 补丁 | 字节 | 文件 |
|---|---|---|
| `0626-k60-modem-image.patch` | 29,161 | 6 个（`pong_modem_image/pas/boot/table`） |
| `0627-k60-modem-qrtr.patch` | 170,730 | 12 个（`pong_modem_qrtr/link/rmtfs/memshare/efs/smp2p` + `qcom_glink`） |
| `0628-k60-ipa.patch` | 174,551 | 19 个（`pong_ipa*` 14 个 + `pong_mdt`） |

三个补丁**全是新文件**，没有一个 hunk 动 `bsd/conf/files`、`board.toml` 或 `scripts/`。
16 线能编，是因为构建驱动在种子之后补了一次：
`scripts/append-conffiles.py`（`ANCHOR = "bsd/dev/pong_buttons.c\t\t\tstandard"`，条目 25 条），
注释写明 P-171「a conf/files hunk cannot be anchored at patch time (the tree is rebuilt)」。

27 树 `bsd/conf/files`、`files.arm64`、`files.x86_64` 里 `pong_`/`qcom_glink` 计数都是 **0**
（`grep -rn 'pong_' /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc/bsd/conf/` 无输出），
所以即使 0629 的调用点打上去了，链接也只会得到一堆 `Undefined symbols`。

工具现在同时产出 `conffiles-port.txt`（18 行，`bsd/dev/<源>.c` + 三个制表符 + `standard`，从补丁文件表推出，不是手抄），
`--self-test` 加了守则：空表、重复行、缺制表符、不以 `.c` 起头、缺 `pong_modem_link.c` 都失败
（输出 `K60 PORT27 PASS renumbering, anchor insertion, refusal, verification, series, build list`）。

两条落地路线，等 Lead 裁决：

1. **构建期追加**（照 16 线）：在 27 的构建驱动里加一步，把 `conffiles-port.txt` 的 18 行插到某个稳定锚点之后。
   需要先在 27 树里挑一行已存在的 `bsd/dev/*.c ... standard` 当锚点——16 线的
   `bsd/dev/pong_buttons.c` 在 27 的 stage-0 里并不存在，锚点得重新选，且这一步同时决定
   「谁负责在 27 线上维护这张表」。
2. **补丁自带**（新增 0630）：把 18 行作为一个追加式 hunk 打进 series。
   27 的 feeds 树是钉死的 commit（`xnu-12377.121.6` / `ac9718f`），文件尾部的上下文稳定，
   P-171 的顾虑在这里不成立；代价是以后主线上游一改 `bsd/conf/files` 尾部，就要跟着 rebase。

本文的倾向是路线 1（与 16 线同一套维护责任，不把构建接线塞进补丁序列），但这一条要 Lead 定，
因为 27 线的构建驱动不在本分支。

### 14.1 Lead 裁决（2026-11-20 07:41）

`bsd/conf/files` 的追加锚点定为 `bsd/dev/unix_startup.c`（27 树 `bsd/conf/files:108` 有这一行）。构建侧的追加器由 Lead 写，本线只交 `conffiles-port.txt`；作为交换，`scripts/check-ios27-readiness.py` 把这一行本身当成期望：它不见了就报
`K60 READY DRIFT the conffiles appender anchor bsd/dev/unix_startup.c is missing from bsd/conf`，而不是等构建期才发现没有东西可以挂靠。

## 15. 外部符号依赖：0628 的 IPA 需要一个不属于本线的驱动

2026-11-20 06:14 审计：把 carried 源码里所有 `extern` 声明抽出来，逐个看它是否由我们自己定义。

```sh
grep -rhoE 'extern [a-zA-Z_].*\(' drivers/PongCellular/*.c drivers/PongCellular/*.h \
  | sed 's/.*[ *]\([a-zA-Z_][a-zA-Z0-9_]*\) *(.*/\1/' | sort -u
grep -rhoE '\b(native_[a-z_]+|pong_[a-z_]+)\(' drivers/PongCellular/*.c drivers/PongCellular/*.h | sort -u
```

结果分三类：

| 类别 | 符号 | 27 线上从哪来 |
|---|---|---|
| 内核 API | `ml_io_map_unmappable`、`pmap_find_phys`、`flush_dcache64`、`delay` | 27 树自身（§4.1 已逐个核对过路径） |
| 本线自备 | `k60_modem_scm_invoke`、`k60_modem_qrtr_probe`、`k60_modem_rails_vote`、`k60_modem_transport_prepare/stale`、`coachz_*` | carried 的 `bsd/dev/pong_*.c` 自己定义 |
| **别的线** | `ArmSmmu4KBuild`、`ArmSmmu4KProgramDisabledContext` | **没有**：定义在 `drivers/PongAdreno/ArmSmmu4K/`，属 GPU 线 |
| 弱兜底 | `native_pong_ufs_read_named_volume` | 无 `drivers/NativeUfs` 时走 0627 里的弱定义（§7.1） |

`drivers/PongCellular/K60Ipa.c:737` / `:739` 是这两个符号的 `extern`，`:1036` / `:1066` 是调用点；
`K60Ipa.c:675-676` 的注释已经写明「bsd/dev does not see the ArmSmmu4K headers」，所以结构体是本地镜像定义的。
27 的 feeds 树是纯 XNU，`ls /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc/drivers` **不存在**，
`grep -rl ArmSmmu4K` 在该树下零命中——也就是说 0629 的调用点解决之后，**0628 仍会在最终链接期缺这两个符号**。

三条出路：

1. GPU 线把 `drivers/PongAdreno/ArmSmmu4K/` 带到 27 线（连同我们提交 `b9de56b9` 的 writeback==2 放宽），
   本线不动代码。这是唯一的「真功能」路线：IPA 要真的把 SMMU 表写进去。
2. 照 `native_pong_ufs_read_named_volume` 的做法，在 `K60Ipa.c` 里加弱定义兜底（返回非 0，打印一行
   `ipa smmu: no ArmSmmu4K in this kernel`）——27 stage-0 能链，IPA 的 SMMU 段确定性拒绝而不是链接失败。
   代价：16 线要重生成 0623 并重建镜像（当前 k53 镜像 `f9afac0d…` 对应的 head 是 `11458c12`，改了就分叉），
   所以要与 k53 的 slot 排期协调，不在它飞之前动。
3. 27 侧先不编 IPA（`pong_ipa` 缺省即 gated，k44 mode3 已实测），把 0628 推迟到 F3/F4。

本文倾向 **2 在 16 线先落地 + 1 在 27 线成立后自然胜出**（弱定义被强定义覆盖，与 UFS 读同一套机制），
但改 `K60Ipa.c` 的时机要与 k53 飞行协调，属于 Lead 的排期决定。

## 16. Lead 的三条裁决（2026-11-20 06:22）与本线的落点

| 裁决 | 内容 | 本线落点 |
|---|---|---|
| conffiles | 走构建期追加，**驱动与表归 Lead**；本线继续产出 `conffiles-port.txt` 并报路径 | `patches/xnu-12377/conffiles-port.txt`（18 行，从 `+++ b/` 推） |
| IPA 归属 | `K60Ipa.c:892` 的上界与重试、以及 ArmSmmu4K 弱定义兜底，**都归 cellular 线**；GPU 线只管 ArmSmmu4K 本体 | 两份草稿：`E:/k60-work/scratch/k60ipa-smmu-weak.txt`、`k60ipa-runtime-alloc.txt`，排在 k53 飞完之后 |
| ArmSmmu4K | 选弱定义兜底，但排在 k53 判读之后；(a) 真功能路线等 GPU 线优先级上来，`b9de56b9` 随 (a) 一起走 | 同上，同一批应用 |
| data-mount 锚点 | Lead 的 F1 还没出图，**别等**；先让 0626/0627/0628 与工具「贴一条命令全绿」 | 本节即为此 |

### 17.1 产物与一条命令

27 侧的四个产物现在住在仓库里，不是 `/tmp`：

```
patches/xnu-12377/0626-k60-modem-image.patch      29,161 B
patches/xnu-12377/0627-k60-modem-qrtr.patch      170,730 B
patches/xnu-12377/0628-k60-ipa.patch             174,551 B
patches/xnu-12377/series-port.txt                    396 B  (注释独占一行 + 四个 bare 名)
patches/xnu-12377/conffiles-port.txt                 650 B  (18 行 bsd/dev/*.c + standard)
```

复现与判绿：

```sh
python3 scripts/port-cellular-to-xnu27.py \
  --tree /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc --out patches/xnu-12377 --verify
python3 scripts/check-ios27-readiness.py \
  --tree /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc --self-test
python3 scripts/check-ios27-readiness.py \
  --tree /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc
```

锚点没落地时第一条按设计 exit 2（`anchor … matches 0 lines`），但 0626/0627/0628、`series-port.txt`、
`conffiles-port.txt` 都照写；第二条 exit 0；第三条现在全绿。

`check-ios27-readiness.py` 新增三项期望，树往前走就变成 DRIFT（提醒重新生成，而不是静悄悄过期）：

1. `patches/xnu-12377/` 里五个产物都在，且 `conffiles-port.txt` 的条目集合**逐项等于**三个补丁装的 `.c`；
2. 27 树 `bsd/conf` 里 `pong_`/`qcom_glink` 计数为 0——Lead 的构建期追加一落地，这一项就报 DRIFT；
3. 27 树里 `ArmSmmu4KBuild` 不存在——GPU 线把它带过来时，这一项报 DRIFT，弱定义兜底就可以退休。

实测输出：

```
K60 READY ok   5 port artifacts, 18 build entries
K60 READY ok   bsd/conf still lists no pong/glink source
K60 READY ok   ArmSmmu4K still absent from the 27 tree
K60 READY OK every recorded expectation still holds
```

## 17. 剥掉一个 hunk 要连它的文件头一起剥

`0626` 是「0620 的全部 + 0621 去掉调用点 hunk」。第一版 `strip_call_site()` 只从 `@@ -7834,2 +7834,10 @@`
那一行截断，补丁末尾于是留下了：

```
--- a/bsd/kern/kern_exec.c
+++ b/bsd/kern/kern_exec.c
```

没有 hunk。`git apply --check` 对这段返回 0（什么都不做），`--verify` 报 ok，所以 29,161 B / 七个 `+++`
目标的产物被当成干净的。这不是无害的：它让 0626 自称碰 `kern_exec.c`，读者会以为调用点在这一条里，
而真正的调用点是 0629。

发现它的是 readiness 新加的结构不变量——三个补丁的所有 `+++ b/` 目标必须落在 `bsd/dev/` 之下：

```
K60 READY DRIFT the patches leave bsd/dev: bsd/kern/kern_exec.c
```

修法（`strip_call_site()` 内）：剥 hunk 时连同紧贴在它前面的 `---`、`+++` 与 `diff --git` 行一起剥掉，
之后再清空行。0626 现在是 **29,107 B / 六个目标**，`--self-test`、`--verify`、readiness 全绿。
本条的教训记在 P-206：`git apply --check` 的 0 只证明没有冲突，不证明补丁说了它该说的话。

## 18. 对照 [基带与移动网络适配](https://unixnu.com/zh/porting/baseband) 的五步：我们有什么、缺什么

这一节把官方页面（Coachz/SC7180 示例）的五节逐条映射到本线现状。左边是页面要求，右边是仓库里的对应物；
「缺」的那列只写**没有实现**的，不写「还没上机」。

### 18.1 划分实现层

| 页面说的层 | 我们的对应物 | 状态 |
|---|---|---|
| SoC 与板级：电源、时钟、保留内存、固件启动、中断、DMA、EFS/NV | `drivers/PongCellular/K60ModemBoot.c`（PAS 四步）、`K60ModemPas.c`（SCM smc）、`K60ModemLink.c`（SMP2P/GLINK/QRTR）、`K60ModemRmtfs.c`、`K60ModemMemshare.c`、`K60ModemEfs.c`、`K60ModemGpt.c` | 有；EFS 读的宿主侧闭合，设备侧未验证 |
| 控制桥：QMUX 帧、QMI 客户端分配、服务发现与回复路由 | `QcomBaseband` 组件（`components.toml:564`，pin `dd0199cf`，产物 `libQcomBaseband.a`；`board.toml:14/21` 已选）、`patches/qcombaseband/0001-coachz-defer-publication.patch` | 有；27 树要重新 pin 组件 |
| iOS 接口：基带服务、通道、异步读写、启动交互 | QcomBaseband 的 appleservice 类（内核里 `COACHZ baseband: %d of %u services published`，22 个） | 有；类名/方法号要按 iOS 27 的 kext 重核 |
| 数据通路：IPA/GSI、QMAP mux、网卡收发 | `K60Ipa.c`、`K60IpaGsi.c`、`K60IpaQmi.c`（`INIT_DRIVER` 154 字节、`INIT_COMPLETE` 构造器都在） | 有代码，设备上一次都没打开过（`pong_ipa` 门控） |

### 18.2 启动 modem 并建立 QMI

页面要求的顺序是：记录电源/复位/时钟/互连/中断/固件内存/SMMU → 加载 MBA/MPSS 并提供原厂 FSG/EFS → 确认 SMP2P 就绪 → 建 GLINK/QRTR、跟踪服务发布 → IPA 在 modem 启动前配置、`ipa-setup-ready` 后建 GSI 端点、再走 QMI `INIT_DRIVER`/`INIT_COMPLETE`。

| 页面步骤 | 我们的证据 | 状态 |
|---|---|---|
| 电源/复位/时钟 | k41–k53 的 S3 六行（`power ok cx=… mss=… xo=…`、`init_image ok metadata=`、`mem_setup ok base=`、`auth_reset ok`） | 设备验证 |
| 原厂 FSG/EFS | RMTFS 服务 14/1 端口 `0x102` + `k60_efs_*` 拷贝引擎 + `native_pong_ufs_read_named_volume` | 协议与拷贝在宿主闭合；k51/k53 待飞 |
| SMP2P 就绪与两个应答 | `K60ModemSmp2p.h`：停位释放、`ipa` 条目的时钟问答（`bit0` 完成 / `bit1` 投票） | k53 待飞 |
| GLINK/QRTR 与服务发布 | k31–k45：名称服务器端口 53、RMTFS 宣告后 modem 立刻 open（25 字节） | 设备验证到「会开口要 EFS」 |
| IPA 先于 modem 启动、`ipa-setup-ready` 后建 GSI | `K60Ipa.c:1170/1364` 的 `pong_ipa` 门控、`K60IpaGsi.c:541` 的冷启动注释 | **顺序未按页面执行**：我们都把 IPA 关着，先让 modem 跑起来 |
| QMI `INIT_DRIVER`/`INIT_COMPLETE` | `K60IpaQmi.c:174/218`（154 字节与应答解析） | 构造器有，没接线 |

结论：2 的前半（modem 起得来、QRTR 通、服务能宣告）已经走在页面的路线上；IPA 那一段我们刻意反过来做——
先把 QMI/EFS 打通，再打开 IPA，因为 K60 的 IPA 从来没用一次性打开成功过（k47 的 panic 与 k48 的 4 GiB 问题都在那一侧）。

### 18.3 接入 iOS 桥接层

页面要求：发布 `AppleBaseband`、`AppleBasebandPCIControl` 与每通道 `AppleBasebandPCIInterface`，用 `ABPInterfaceProtocol` 匹配 `pbl`/`sahara`/`qmux1`/`qmux2`，按目标 OS 核对 UserClient 类名、方法号、参数大小与异步完成参数；`coachz_baseband_configure(send, del_client)` 转发服务变化；CTL 分配 QMI 客户端与本地 QRTR 端口；BSP 激活、VINYL Tape 与运营商包分段的应答规则；DT 里加 `/chosen/coachz-baseband`、`/baseband`、`baseband-chipset` 与根节点 `compatible`。

我们这边：22 个服务已由 QcomBaseband 发布（k6x 的 console 行），`board.toml` 把 `QcomBaseband` 进了 `include` 与 `archives`，DT 侧有 `pong-*` 节点与 `baseband-*` 属性。**缺的是「按 iOS 27 核对」**：27 stage-0 起来后，类名、方法号、参数大小、异步完成参数、`ABPInterfaceProtocol` 名称表都要对 27 的 kext 重新过一遍——这是 27 线第一次真正需要 iOS 侧代码的时刻，也是本线目前唯一必须等 27 树的东西。

### 18.4 接通移动数据

页面要求：`kOnline`、NAS 注册/驻留/附着、DPM 打开 IPA 硬件端口、WDA raw IP/QMAPv4、端点 `{3,4}`→`{4,1}`、WDS 绑定 QMAP mux、`pdp_ip0..3`（MTU 1492）、按 mux 分发、收发/断开/飞行模式/modem 复位逐项验证、eSIM 的 UIM/APDU 与 VINYL。

我们这边：**一项都没开始**。这不是遗漏，是顺序——27 stage-0 的 SpringBoard 都还没打通，数据面要等基带在 27 上重新跑到「modem 持续运行、QMI 服务响应」之后。计划里它排在 k53 判读、IPA 打开、SIM 身份读取之后。

### 18.5 构建与记录

| 页面要求 | 我们 |
|---|---|
| `QcomBaseband` 进组件选择，`component:QcomBaseband` 归档 | `board.toml:14`（include）与 `:21`（archives）已有 |
| 更新时 `components.toml` 与 submodule 同提交 | 16 线 pin 写在 `scripts/build-qcom-baseband.py` 的 docstring（`dd0199cf`）；源不在本仓库，由 `UniXNU/components.toml:564` 的 `QcomBaseband` 条目 fetch 到 `drivers/QcomBaseband`，产物 `build/qcom-baseband/libQcomBaseband.a`。**27 树要重新 pin**（27 侧目前还没有这个组件） |
| `scripts/build-qcom-baseband.py --coachz` | 已有，27 侧要跟着 conffiles 追加一起接 |
| `porting.toml` 分别记录 modem 启动、QMI、SIM 身份、网络注册、数据、复位、eSIM | `porting.toml` 的 cellular 区已记「启动」与「QMI 枚举」；SIM/注册/数据/eSIM 尚未记（没做过） |

### 18.6 这张表对 27 迁移的直接影响

1. 27 侧第一飞能覆盖的只有 18.2 的前半（起 modem、QRTR、RMTFS），与 16 线同一套判据——`judge-cellular-flight.py` 不依赖 OS 版本。
2. 18.3 是 27 特有的工作量，且**必须等 27 的 kext**；在那之前动它只能靠猜。
3. 18.4 全部排在 18.2/18.3 之后，不要提前开工。
4. 18.5 里「27 树 pin `QcomBaseband`」与本线的 `conffiles-port.txt` 是同一步的两个半边，落地时要一起做。

## 19. carried 文件的两个 include：一个要跨线携带，一个不该带

`check-ios27-readiness.py` 新加的「引用头文件审计」（每个 `+#include "…"` 必须由补丁集自己安装，或者在 27 树里找得到）第一次跑就把这件事翻出来：

```
K60 READY DRIFT 4 quoted include(s) resolve nowhere: pong_pmic_rail.h (pong_ipa.c)
  pong_smem.h (pong_ipa.c) pong_pmic_rail.h (pong_modem_link.c) pong_smem.h (pong_modem_link.c)
```

两个头都不属于 cellular 的 0620..0623：

| 头 | 16 线来源 | 大小 | 我们的调用点 |
|---|---|---|---|
| `pong_smem.h` | `patches/xnu/0611-k60-smem-handoff.patch`（`bsd/dev/pong_smem.h` + `.c`） | 25 + 151 行 | `K60ModemLink.c` 14 处、`K60Ipa.c` 3 处（`k60_smem_partition/find/alloc`） |
| `pong_pmic_rail.h` | `patches/xnu/0613-k60-adsp-pas.patch`（`bsd/dev/pong_pmic_rail.h` + `.c`） | 60 + 243 行 | **零处**：`k60_rail_probe()` 在 `drivers/PongCellular/` 下没有任何调用者 |

三个补丁 `git apply --check` 全绿，但 27 树既没有这两个文件，也没有能提供它们的补丁——这就是「补丁打得上 ≠ 编得过」。

### 19.1 处理方式

1. **`pong_smem` 携带**：0611 的这两个 section 只 include 自己（`pong_smem.c` 只有一行 include 自己的头，头只用 `<stdint.h>`），所以 `port-cellular-to-xnu27.py` 新增 `CARRY = (("0611-k60-smem-handoff.patch", ("bsd/dev/pong_smem.h", "bsd/dev/pong_smem.c")),)`，把这两段**逐字节**搬成 `0630-k60-smem.patch`（8,005 B），`conffiles-port.txt` 因此多一行 `bsd/dev/pong_smem.c`（19 条）。
2. **`pong_pmic_rail` 不带**：`k60_rail_probe()` 零调用者，携带 246 行驱动只为满足一个 include 是把另一条线的代码拖进来。改成在生成时删掉这一行 include（`DROPPED_INCLUDE`），并让 readiness 断言「没有任何 ported 补丁还需要 pmic rail」。

删一行不等于改一行：hunk 头里的行数必须跟着重算，否则 `git apply` 报 `corrupt patch at line 3561`。`drop_include()` 改成按 hunk 体重新数增删与上下文行，重写 `@@ -a,b +c,d @@`。

### 19.2 结果

```
K60 READY ok   6 port artifacts, 19 build entries
K60 READY ok   38 patch targets, all under bsd/dev
K60 READY ok   all 38 sections create new files, no target twice
K60 READY ok   19 quoted includes resolve inside the patch set or the tree
K60 READY ok   no ported patch needs the pmic rail driver
K60 READY OK every recorded expectation still holds
```

| 产物 | 大小 | 说明 |
|---|---|---|
| `0626-k60-modem-image.patch` | 29,107 B | 不变 |
| `0627-k60-modem-qrtr.patch` | 170,701 B | 少了 pmic include |
| `0628-k60-ipa.patch` | 174,480 B | 少了 pmic include |
| `0630-k60-smem.patch` | 8,005 B | 0611 的 smem 对，逐字节 |
| `series-port.txt` | 485 B | 五条 bare 名 + 注释 |
| `conffiles-port.txt` | 681 B | 19 条 |

`0629` 没重生成：它要等 27 树的 data mount 锚点，仓库里那份仍是对着真实树生成的。

### 19.3 Lead 裁决（2026-11-20 07:41）：0630 保留

`0630-k60-smem.patch` 不移交 power/adsp 线。等他们真把 `0611`/`0613` 整体搬到 27 时，删 `0630` 一个文件即可，`0626`–`0629` 一行不动（`0627`/`0628` 里对 `pong_smem.h` 的 include 由那次搬运自己满足）。

## 20. 编译前的第二道检查：150 个头文件在 27 树里都在

§19 的教训是「补丁打得上 ≠ 编得过」。补丁集内部的自洽（引用审计）解决了其中一半——补丁之间互相提供的头；另一半是**补丁依赖的目标树头文件**，这类缺失只有编译器会告诉你，而且是在二十分钟的构建之后。

### 20.1 方法

16 线的构建树给每个目标文件留了 `.d` 依赖清单，里面是编译器真正打开过的绝对路径：

```
<tree>/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/bsd/DEVELOPMENT/pong_modem_link.d
<tree>/.cache/xnu-work/bsd/dev/pong_modem_link.c
<tree>/.cache/xnu-work/bsd/sys/proc.h
```

（注意 `<tree>/.cache/xnu-work` 是打完补丁的工作副本，仓库里的同名文件不是编译器看到的那个。）把 `.cache/xnu-work/` 之后的部分当成相对路径，逐个问 27 树有没有。

自身的文件（`pong_*`、`qcom_glink*`）跳过：它们由补丁集安装，那条由 §19 的引用审计负责。

### 20.2 结果

```
K60 DEPS OK 150 headers from 8 objects, none missing
```

150 个系统头文件（`bsd/`、`osfmk/`、`libkern/`、`pexpert/`、`iokit/`、`EXTERNAL_HEADERS/`）在 27 树里都还在原路径。这不能证明 API 语义没变（签名、结构体布局、宏的含义都可能变），但能证明**路径这一层不需要为 27 改一行 include**。

同一个工具跑在 16 线自己身上是 0 缺失，这是它该有的对照组。

### 20.3 一道跑的还有「打得进去」

```
0626-k60-modem-image.patch   rc=0
0627-k60-modem-qrtr.patch    rc=0
0628-k60-ipa.patch           rc=0
0630-k60-smem.patch          rc=0
```

四个补丁对真实 27 树 `git apply --check` 全绿（`0629` 仍要锚点）。`0627`/`0628` 在删掉 pmic include、重算 hunk 头之后重新验过。

### 20.4 什么时候再跑

27 树每次更新（换 xnu 版本、重新 pin component）后跑这两条，顺序固定：

```sh
python3 scripts/check-ios27-readiness.py --tree <27 tree>
python3 scripts/check-ios27-deps.py \
  --deps <16 tree>/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/bsd/DEVELOPMENT \
  --work <16 tree>/.cache/xnu-work \
  --tree <27 tree>
```

缺一个头 = 27 改了名或删了它，先回头看 16 线那处调用，再决定是改 include 还是携带实现。

## 21. 交接清单：27 侧落地需要做的四件事（按顺序）

这一节写给接手 27 树的人。全部命令都在 /opt 的 27 树旁边执行，仓库侧只需要 `patches/xnu-12377/`。

### 21.1 打补丁

```sh
cd <27 tree>
git apply -p1 <repo>/patches/xnu-12377/0626-k60-modem-image.patch
git apply -p1 <repo>/patches/xnu-12377/0627-k60-modem-qrtr.patch
git apply -p1 <repo>/patches/xnu-12377/0628-k60-ipa.patch
git apply -p1 <repo>/patches/xnu-12377/0630-k60-smem.patch
# 0629 需要 data mount 锚点，见 21.3
```

四个补丁都只新建 `bsd/dev/pong_*.{h,c}` 与 `bsd/dev/qcom_glink.{h,c}`，不改任何既有文件，所以 git apply 只有新增，没有冲突面。

### 21.2 构建期追加 conffiles

`bsd/conf/files` 在 27 树里没有这些条目（`pong_` / `qcom_glink` 计数为 0），打完补丁直接构建会在链接期报 `Undefined symbols`。`conffiles-port.txt` 是现成的 19 行：

```
bsd/dev/pong_modem_link.c			standard
...
```

按 27 构建流水线自己的方式追加（16 线是 `scripts/append-conffiles.py`，锚点 `bsd/dev/unix_startup.c`，见 P-171「conf/files 的 hunk 不能在第 7 步锚定」）。**不要**在补丁里带 `bsd/conf/files` 的 hunk。

### 21.3 两个调用点（0629）

27 树现在**还没有** Data 挂载阶段（`native_owner_data_stage` 0 行命中），所以 0629 无从生成。等 27 树有了那一行：

```sh
python3 scripts/port-cellular-to-xnu27.py --tree <27 tree> --out patches/xnu-12377 --anchor-auto
# 或显式：--anchor "<把 stage 推到 3 的那一行原文>"
```

工具会先打印命中的锚点原文，再生成 `0629-kern-exec-call-sites.patch`；锚点 0 行或 2 行以上直接 exit 2，不会产出半截补丁。两个 probe 分别由 0626（`k60_modem_probe_from_handoff`）与 0628（`k60_ipa_probe_from_handoff`）提供——readiness 有断言，改名前会先红。

### 21.4 第一次起飞前的两条检查

```sh
python3 scripts/check-ios27-readiness.py --tree <27 tree>
python3 scripts/check-ios27-deps.py --deps <16 tree>/build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/bsd/DEVELOPMENT \
  --work <16 tree>/.cache/xnu-work --tree <27 tree>
```

两条都该是 ok。第一次 27 起飞的预期见 §7.1：存储读会**优雅拒绝**（27 没有 `drivers/NativeUfs`，弱定义兜底返回 0），所以 `rmtfs rw ... refused` 是这一阶段的正常结果，不是失败；真正的失败是 panic、S3/S6 缺行或 `rmtfs` 一行都没有。

### 21.5 交接面之外

- 27 的 `board.toml` 与 `QcomBaseband` 组件 pin 不属本线（§18 表格第 5 行）：该驱动是组件目录 fetch 来的，本仓库只有 `patches/qcombaseband/`。本线交的是随补丁走的东西——`0626`/`0627`/`0628`/`0630`、`series-port.txt`、`conffiles-port.txt`。
- `drivers/PongAdreno/ArmSmmu4K` 属 GPU 线；IPA 需要的两个符号在本线用弱定义兜底，等 k53 判读后才落。
- 0629 之外不需要再动 `kern_exec.c`；IPA 的 `kmem_alloc_contig` 上界与重试也在 k53 之后。

## 22. readiness 的第二种模式：已集成树

`scripts/check-ios27-readiness.py` 现在有两种判断，按树自身切换，仍然是一条命令：

| 树的状态 | 判据 | 期望输出 |
|---|---|---|
| pristine（还没打补丁） | `bsd/dev/pong_modem_link.c` 不存在 | 老模式：六个已记录的 rc、8 个内核符号、150 个头、6 个产物、38 个目标、19 条 include |
| 已集成（合过补丁与 conffiles） | 同左文件存在 | 新模式：系列里每条补丁反向可撤销、38 个目标都在树里、19 条构建项都在 `bsd/conf`、两个探针调用点各出现一次、Data mount 锚点仍恰有一行 |

新模式检查的是「打进去之后」，正好补上老模式只盯着「能不能打进去」的空档（P-208 是同一个教训的另一半）。
两个失败样例都跑过：

- 真实 27 树（pristine）：`K60 READY OK every recorded expectation still holds`，rc=0。
- 合成已集成树（把 0626/0627/0628/0630 真打进去、抄 19 条 conffiles、伪造锚点与两个探针）：只报一条
  `K60 READY DRIFT 0629-kern-exec-call-sites.patch: patch file missing; generate it with --anchor-auto once the tree stages the data mount`，rc=1
  ——这正是当前仓库的真实状态（0629 还没生成），说明检查不会因为缺一件就静默放行（P-209）。

Lead 侧接线完成后的用法不变：

```
python3 scripts/check-ios27-readiness.py --tree <27 树>
```

rc=0 就可以开始第一次带基带的内核构建；rc=1 的每一行都写明是哪一条期望变了。

## 23. 27 侧 conffiles 的实测差（2026-11-20 08:37）

实测对象：`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree`。
种子后的 `.cache/xnu-work/bsd/conf/files` 目前 `pong_` 计数为 0，
即 27 线的驱动源码还没有任何 conffiles 条目。

### 20.1 锚点必须换

27 侧 `scripts/append-conffiles.py` 里的 `ANCHOR = "bsd/dev/pong_buttons.c			standard"`
在本线不存在：`pong_buttons.c` 来自 16 线的补丁，27 的移植序列（0626–0630）不装它。
种子后的 `bsd/conf/files:108` 是 `bsd/dev/unix_startup.c			standard`——这正是 Lead 07:41 裁决的落点。
不改就只会打印 `conffiles: anchor missing, entries not added` 并返回 1。

### 20.2 条目差 18 条

27 侧现列 8 条（smem / handoff / adsp_startup / adsp_boot / adsp_pas / adsp_image / fat / pmic_rail），
我们的 `conffiles-port.txt` 是 19 条，差的就是下面 18 条（缺一条 `pong_smem.c` 两边都有）：

- `bsd/dev/pong_ipa.c`
- `bsd/dev/pong_ipa_gsi.c`
- `bsd/dev/pong_ipa_qmap.c`
- `bsd/dev/pong_ipa_qmi.c`
- `bsd/dev/pong_ipa_qmi_server.c`
- `bsd/dev/pong_ipa_qmi_transport.c`
- `bsd/dev/pong_ipa_qrtr.c`
- `bsd/dev/pong_ipa_smmu.c`
- `bsd/dev/pong_mdt.c`
- `bsd/dev/pong_modem_boot.c`
- `bsd/dev/pong_modem_efs.c`
- `bsd/dev/pong_modem_image.c`
- `bsd/dev/pong_modem_link.c`
- `bsd/dev/pong_modem_memshare.c`
- `bsd/dev/pong_modem_pas.c`
- `bsd/dev/pong_modem_qrtr.c`
- `bsd/dev/pong_modem_rmtfs.c`
- `bsd/dev/qcom_glink.c`

### 20.3 顺序：先打补丁再追加

追加器对`不存在于 .cache/xnu-work 的源文件`是`静默丢弃`（`dropped absent`），
而我们的 18 个源文件全部由 0626–0630 新建。所以追加必须在 `git apply` 之后、编译之前；
反过来做不会报错，只会在链接期变成 Undefined symbols。

### 20.4 复核方式

本线 `scripts/check-ios27-readiness.py` 的 `conf_anchor()` 已经盯着这条链：
它在种子树的 `bsd/conf/files`/`files.arm64` 里找 `bsd/dev/unix_startup.c` 这一行，
并断言五份产物的 `+++ b/` 目标集合与 `conffiles-port.txt` 逐项相等。
追加器落地后，`patch_artifacts()` 里那条`27 树 bsd/conf 计数为 0`的期望会 DRIFT，
提醒我们把期望值改成 19。

## 24. 数据挂载的锚点在种子树里已经有了：0629 生成并可应用（2026-11-20 08:50）

§20 量出 27 侧 conffiles 缺 18 条，前提是「补丁要先打进去」。打补丁需要 0629，而 0629 要等 Data mount 的锚点；
Lead 07:41 说「锚点我这边还没有，别等」。现在种子树的 `.cache/xnu-work` 里它已经在了。

实测（tree = /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work）：

| 事实 | 数值 |
|---|---|
| `bsd/kern/kern_exec.c` 行数 | 10,234 |
| `native_owner_data_stage` 出现 | 5 处：8152 `= 0`（定义）、9015 `= 1`、9032 `= 2`、9035 `= 3`、9046 `if (!error) ... = 4` |
| `--anchor-auto` 首次结果 | `anchor is ambiguous, 5 candidates` |
| 收窄后的锚点 | 9035 `native_owner_data_stage = 3;` |
| 0629 | 1,274 B，hunk `@@ -9029,12 +9029,28 @@` |
| 插入位置 | `if (error) goto done;` 与 `native_owner_data_stage = 3;` 之间（与 §5.1 契约一致） |
| 五个补丁 `git apply --check` | 全部 OK（0626 / 0627 / 0628 / 0629 / 0630） |

三处修正：

1. `find_anchor()` 收窄：候选多于一行时先按 `STAGE_THREE = re.compile(r"native_owner_data_stage\s*=\s*3\s*;")` 过滤，
   只剩一行才返回，仍多行才报 ambiguous。变量走 0→1→2→3→4，只有「推到 3」那行在 Data 挂上之后执行；
   插在 `= 1`/`= 2` 会把探针放进重试与回滚路径。
2. `verify()` 改用绝对路径：相对路径加 `git -C tree` 会让 git 在树内找补丁，报
   `error: can't open patch 'patches/xnu-12377/0626-k60-modem-image.patch'`；改 `os.path.abspath()` 后 5/5 ok。
3. readiness 的两条不变量原来是「所有 `+++ b/` 目标都在 `bsd/dev`」「每个段落都是新文件」，call-site 补丁天生违反：
   现在允许唯一例外 `bsd/kern/kern_exec.c`，且必须只由 0629 改、段落允许不是新文件；0621 的 `rc=1` 期望只在锚点缺席时断言
   （种子树里它 apply 成功是正确行为，不是漂移）。

结果：

- 种子树：`K60 READY OK every recorded expectation still holds`（39 个目标、call-site 只改 kern_exec.c、0629 已生成）
- feed 树：同样绿（`anchor lines=0` 只是 note）
- 工具自测：`K60 PORT27 PASS renumbering, anchor insertion, auto anchor, refusal, verification, series, build list`
- 「先 apply 五个补丁 → 再追加 19 条 conffiles → 再编译」这条路第一次具备可执行的全部输入。

补记（2026-11-20 09:00）：三段已经在副本上跑通，脚本 `scripts/verify-27-line.sh`。

`bash scripts/verify-27-line.sh --tree /opt/k60/trees/ios27-out/.../tree/.cache/xnu-work` 会：
1. `git clone --shared` 出一个副本（对象复用，只复制工作文件），把种子树里 3 个未提交修改（`EXTERNAL_HEADERS/Availability.h`、
   `EXTERNAL_HEADERS/CoreEntitlements/CoreEntitlements.h`、`bsd/conf/Makefile.arm64`）以 diff 形式带进去；
2. 按序 `git apply` 0626/0627/0628/0629/0630；
3. 用 `conffiles-port.txt` 在 `bsd/dev/unix_startup.c` 之后追加条目，先断言 19 个源都在副本里。

实测输出：`K60 TRIAL ok   seed modifications carried`、五个 `applies`、
`K60 TRIAL ok   appended 19 build entries, bsd/conf now lists 19`、`K60 TRIAL PASS seed, five patches and the build entries on one clone`
（`bsd/conf/files` 633 行 → 652 行）。真树一行未改；副本用完即删（`--keep` 保留）。

这一步把「补丁打得上」「conffiles 追得上」「条目指向的源真的存在」三件事合到一次可重放的动作里，
也解释了 §20.3 的顺序坑：追加器看不到的源会被静默跳过，所以追加必须排在 `git apply` 之后。

## 25. 追加器本身就是我们仓里的那份：锚点要换，且它是共享件（2026-11-20 09:05）

27 树 `scripts/append-conffiles.py` 与本仓 `scripts/append-conffiles.py`（以及 `UniXNU-mondrian` 那份）逐字同源，
第 12 行都是 `ANCHOR = "bsd/dev/pong_buttons.c\t\t\tstandard"`（源码里是字面 `\t`，运行时才是制表符）。
`pong_buttons.c` 来自 16 线补丁，27 的 0626–0630 不装它 ⇒ 27 上这个锚点必然缺失，
脚本只会打印 `conffiles: anchor missing, entries not added` 并返回 1。

两个事实合起来决定改法：

1. 锚点必须换成种子后确实存在的行（27 的 `bsd/conf/files` 第 108 行 `bsd/dev/unix_startup.c\t\t\tstandard`，与 Lead 07:41 裁决一致）；
2. 条目表必须按线取：27 用 `patches/xnu-12377/conffiles-port.txt`（19 条，由补丁自装），16 线仍用原来的 8 条。

最小改动草案（未入仓，归 Lead 裁决；只在副本上验证过）：`ANCHOR` 换成 `unix_startup.c`，`ENTRIES` 改为
「`<repo>/patches/xnu-12377/conffiles-port.txt` 存在则读它，否则退回原 8 条 `LEGACY`」。副本验证：19 条全部列出，
`bsd/conf/files` 由 1 行变 20 行（锚点 + 19），二次运行打印 `all entries already listed`，幂等。

另有一条与顺序相关的行为已在本节 §20.3 记过、这里再点一次：追加器对「源不在 `.cache/xnu-work`」的条目是**静默跳过**
（只有产生 `dropped` 时才打印），所以 `git apply` 必须排在追加之前——`scripts/verify-27-line.sh` 把这层顺序写成了断言。

## 26. 弱定义：让 0628 在没有 ArmSmmu4K 的树上也能链接（2026-11-20 09:15）

0628 的 `pong_ipa.c` 里有两个入口是对 GPU 线的外部引用（源文件 `K60Ipa.c:737-740`）：
`ArmSmmu4KBuild()` 与 `ArmSmmu4KProgramDisabledContext()`，实现在
`drivers/PongAdreno/ArmSmmu4K/`。27 树是纯 XNU，既没有那个驱动也没有它的归档，
所以「补丁能 apply」并不等于「内核能链接」——这是一条只在最终链接才现形的缺口。

改法：在同一个翻译单元里给出**弱定义**（返回 −1 并打印一行 `K60IPA smmu: no ArmSmmu4K in this kernel`），
归档里的强符号在最终链接时覆盖它，与 `pong_modem_link.c` 对 `native_pong_ufs_read_named_volume` 的做法一致。
没有另起一个 shim 文件，因为 `K60IpaArmSmmuConfig` 等六个结构体是 `K60Ipa.c` 的文件内私有类型，
shim 只能重新声明成不完整类型，而跨翻译单元的类型不一致链接器不会替我们检查。

重新生成后的尺寸：0623 `174,551 → 175,356`（+805 B）、0628 `174,480 → 175,285`，
补丁里的 `+__attribute__((weak))` 行共 2 条；0626 29,107 / 0627 170,701 / 0629 1,274 / 0630 8,005 不变，
conffiles 仍 19 条（没有新增文件，所以条目表不动）。

新的不变量：`check-ios27-readiness.py` 的 `weak_fallbacks()` 要求 0628 同时出现两条
`+__attribute__((weak))` 与两个入口名，否则 `K60 READY DRIFT the 27 set no longer answers for …`。
把弱定义删掉再跑，实测报 `weak lines=0`（漂移路径是验证过的，不是只写了断言）。


一条写记录时踩到的教训（与代码无关，但同类错误会再犯）：`porting.toml` 的 `evidence` 条目是**单行内联表**，
TOML 1.0 不允许 `{ … }` 跨行，所以把 `kind` / `reference` / `result` 拆成两行写会在
`tomllib` 里报 `Invalid initial character for a key part`，行号指向的是那条目自己的第一行，很容易误以为是编码或转义问题。
插入后先 `tomllib.loads()` 再落盘，坏内容就不会进仓库。
遗留：`feat/cellular` 上 `K60Ipa.c` 仍是裸 `extern`——k54 镜像由那条线构建，
判读前不改它，避免镜像无法由 HEAD 复现；等 16 线也落这处改动时，那边的 0623 会一起变，series 指纹随之更新。

## 27. 门禁接上共享追加器：`--appender` 与两条实测（2026-11-20 09:30）

Lead 09:23 裁决：`verify-27-line.sh` 当构建前门禁，但**副本不能代替**真树上那一次追加；
追加器由 Lead 在 `k60-gates/scripts/append-conffiles.py` 落，加 `--verify` / `--apply` 两个模式，
门禁与构建共用同一份逻辑。

本线的接法：`scripts/verify-27-line.sh` 增加 `--appender <py>`。给了就走共享实现
（`python3 <appender> --verify <clone> <conffiles-port.txt>`，非 0 即 `K60 TRIAL FAILED the shared appender refused the clone`），
没给就仍走脚本内嵌的那段 python（保持可在没有共享实现时独立使用）。

三路实测（种子树 `.cache/xnu-work`）：

| 路径 | 结果 | 退出码 |
|---|---|---|
| 不给 `--appender`（内嵌） | `K60 TRIAL ok   appended 19 build entries, bsd/conf now lists 19` → `K60 TRIAL PASS` | 0 |
| 桩 `--verify` 返回 0 | `K60 TRIAL ok   the shared appender accepted the clone` → PASS | 0 |
| 桩返回 1 | `K60 TRIAL FAILED the shared appender refused the clone` | 1 |

退出码必须直接测（`bash … > log 2>&1; echo $?`），不能接 `| tail`——管道会把 `$?` 换成 tail 的状态，
我第一版就是这么「测」的，三路全是 0，看起来像拒绝路径没生效。

待办：构建脚本 `scripts/build-ios27-linux.sh` 的插入点在 `defconfig`（第 45 行）与
`unixnu build kernel`（第 46 行）之间；该文件在 `k60-gates`（owner = lead），本线只给片段，不代改。

## 28. 27 线从共享资源里实际要什么（2026-11-20 09:45）

27 的内核构建读的是**设备仓**（`/mnt/e/hackios/k60-gates`，owner = lead），不是本仓。
`board.toml:369` 的 `patch_series = ["arch:patches/xnu/series", "soc:patches/xnu-12377/series",
"os:patches/xnu/series", "device:patches/xnu-12377/series"]`，注释写明 `patches/xnu-12377/series`
是「the order of record」。本仓 `patches/xnu-12377/` 只是生成地，复制过去这件事不属于本仓。

新工具 `scripts/check-ios27-device.py --device <设备仓> [--patches <本仓目录>] [--self-test]`
把两边逐项对比（board.toml 里有没有 `device:patches/xnu-12377/series`、series 是否含我们的补丁
且顺序与 `series-port.txt` 一致、每个补丁两边 sha256 是否相同、27 package 是否含 `QcomBaseband`），
输出 `K60 DEVICE ok|DRIFT|note`，exit 0/1/2。真实设备仓当前的结果：

```
K60 DEVICE ok   board.toml lists device:patches/xnu-12377/series
K60 DEVICE DRIFT 5 of 5 ported patches are not in the device series: 0626… 0627… 0628… 0630… 0629…
K60 DEVICE DRIFT the device repository has no copy of: 0626… 0627… 0628… 0630… 0629…
K60 DEVICE note QcomBaseband is not in the 27 package include list
K60 DEVICE CHANGED 2 expectation(s) drifted
```

`--self-test` 用临时目录造三份设备仓（完整 / 少一条 series 条目 / 同名但内容不同），
输出 `K60 DEVICE PASS agreement, missing entry, differing copy`。

### 28.1 清单：每一样东西在哪、谁负责、缺什么

| 资源 | 事实（实测） | 27 现状 | 计划 |
|---|---|---|---|
| 五个补丁 + series 条目 | 设备仓 `patches/xnu-12377/` 里只有 BT 系列 0500–0523 与两处上游补丁（`armcpu-sleep-hook.patch` 等）；我们 0626–0630 一条都没有，文件也不存在 | 构建器读不到 ⇒ 27 内核里没有 cellular | 把 0626–0630 复制进设备仓同名目录，并按 `series-port.txt` 的顺序（0626 0627 0628 0630 0629）追加到 `series`；设备仓 owner 是 lead，本线只交清单与检查器 |
| `QcomBaseband` 控制桥 | `UniXNU/components.toml:564`：repo `UniXNU/QcomBaseband`、rev `dd0199cf`、path `drivers/QcomBaseband`、输出 `build/qcom-baseband/libQcomBaseband.a`，运行期 id 含 `AppleBaseband`/`AppleBasebandPCIControl`/`pdp_ip0..3` | 27 package 的 include 只有 `ArmDTPlatform`/`ArmCpu`/`XnuPrelink`（`board.toml:360`） | 基带桥接真正接上时再进 include + archives（16 线在 `board.toml:14/21` 已有）；那之前 27 不需要它 |
| `PongUfs` / `ShengUfs` | `components.toml:552` id=`PongUfs`、`:121` id=`ShengUfs`（repo `UniXNU/ShengUfs`、rev `99d8bcd3`、输出 `build/sheng-ufs/libShengUfs.a`、legacy 名 `NativeUfs`） | 27 stage-0 有意不带（`board.toml:359` 注释「No PongUfs at stage 0; it returns in F3」） | rmtfs 读 EFS 要它；0627 的弱定义让 27 能链接、读返回 refused，F3 带回来后才真正读盘 |
| `ArmSmmu4K` | `components.toml:397`：repo `UniXNU/ArmSmmu4K`、rev `83969cd8`、path `kits/ArmSmmu4K` | 27 树无 | 0628 已有弱定义兜底；GPU 线把它带进来时 readiness 的 `no ArmSmmu4K` 那条会 DRIFT，提醒撤掉弱定义 |
| `append-conffiles.py` | 设备仓 `scripts/`，owner = lead；anchor 仍是 `bsd/dev/pong_buttons.c`（16 线的源） | 27 上必然 `anchor missing, entries not added` 并返回 1 | 932 B 草案（anchor → `unix_startup.c`、entries 读 `conffiles-port.txt`）+ Lead 的 `--verify`/`--apply` |
| 本仓生成物 | `patches/xnu-12377/{0626..0630, series-port.txt, conffiles-port.txt}` 在 `feat/cellular-ios27` | 设备仓没有 | 即第一行；`check-ios27-device.py` 是这件事的门禁 |

### 28.2 结论

- **本仓之外真正缺的只有两处**：设备仓 `patches/xnu-12377/` 的副本与 series 条目；27 package 里的
  `QcomBaseband`（后者等 cellular 进 27 才需要）。其余共享件（`ArmSmmu4K`、`ShengUfs`/`PongUfs`、
  `QcomBaseband` 本体）都已在 `UniXNU/components.toml` 里登记了 repo 与 40 位 revision，新检出按
  `components.toml` 就能取到，不需要本仓保存副本。
- 因此 kernel 侧只有一份事实源（本仓 `drivers/PongCellular/*` → 生成的补丁），设备侧也是一份
  （`k60-gates`），两边之间必须靠「复制 + 检查」而不是「都改一遍」。
- 新检查器只做只读对比，不进 host 套件：它在设备仓还没副本时必然红，那是待办而不是回归。

### 28.3 把清单变成一条命令：`stage-ios27-device.py`（2026-11-20 09:50）

`scripts/stage-ios27-device.py --device <设备仓> [--patches <本仓目录>] [--out <目录>] [--self-test]`
只往暂存目录写，**不动设备仓**（owner 不同）。产出四样：

| 文件 | 内容 |
|---|---|
| `patches/xnu-12377/0626…0630` | 五个补丁的副本，与 `patches/xnu-12377/` 逐字节相同 |
| `series.expected` | 设备仓 `series` 原文 + 本仓 `series-port.txt` 的整段（含每条补丁的来源注释） |
| `series.diff` | 上述改动的 unified diff，`git -C <device> apply` 可直接用 |
| `apply.sh` | 三条落地命令 + 一条 `check-ios27-device.py` 复核 |

对真实设备仓的实测：`K60 STAGE ok 5 patches (953f3eb0ea22ef06 62845734e62ee893 28a9ad58dd407735
783818c138dd81d9 08b53cfd112292b7)`，diff 只有一个 hunk `@@ -77,3 +77,15 @@`，落在
`0541-k60-virtual-timer-guard.patch` 之后；追加的 12 行里有 5 条 bare 名与 7 行来源注释（旧文件 79 行 → 91 行），
顺序为 0626 0627 0628 0630 0629（0629 最后，因为它动 `kern_exec.c`，要在其余补丁把符号装进树之后）。

三种状态：设备仓一条都没有 → 追加并写全套；`series` 已含全部五条 → 报 dry，不重复追加；
只含一部分 → `K60 STAGE REFUSED`，因为那是手工动过的状态，不替人猜。

`--self-test` 在临时目录造一份假设备仓与假补丁集，跑完四步：
`K60 STAGE ok 2 patches … the series gains 2 entries` → 用 `git apply --check` 验 diff →
应用后与 `series.expected` 逐字节相同 → 二次运行是 no-op、半列状态被拒，
输出 `K60 STAGE PASS handoff, diff applies, rerun is a no-op, half state refused`。

分工不变：stager 在本仓（可测、可复现），落盘由设备仓 owner 执行；
`check-ios27-device.py` 事后复核，两者都用同一份 `series-port.txt` 当事实。

落地效果在假设备仓上验过（`/mnt/e/k60-work/scratch/ios27-device-fake`：真 `board.toml` + 真 78 行 `series`，
没有补丁文件）：落地前 `DRIFT the device repository has no copy of: 0626… 0629…`；
`git apply series.diff` + 拷五个补丁之后，`K60 DEVICE OK the device repository carries the 27 line`，
四条 ok 全绿，只剩 `note QcomBaseband is not in the 27 package include list`。
即：清单、暂存、复核三段现在闭合，剩下的动作只在设备仓 owner 手上。

### 28.4 Lead 10:05 四条裁决（已落档，不改代码）

1. **第 1 项现在不落盘**。新 main 的冻结条款是「SpringBoard 打通前任何线不得往 main 合代码」，而
   `k60-gates/patches/xnu-12377/` 就是 main。把 0626–0630 复制进去等于提前把 cellular 并进 27 主线，
   会在 F2 判据里混进五个与 `bsd_init` 无关的变量。暂存脚本保留、只在
   `E:/k60-work/scratch/ios27-device-stage/` 待命；F2 通过（`arm_init` → `bsd_init` → root-mount panic + cupid 一致）
   之后第一件事就是执行 A 或 B，那时 `check-ios27-device.py` 由 DRIFT 转 OK 就是并入的验收证据。
2. `check-ios27-device.py` 留着，**不许为了变绿放宽**。它现在报红是正确状态（待办不是回归）。
3. `QcomBaseband` 的 note 保持 note，等 cellular 真进 27 再加 include+archives。
4. k54 排队但今天大概率飞不了：设备在 Android（adb `6033dbec`），F1/F2 排在前面；顺序仍是
   GPU → power w11 → k54 → audio cc。27 stage-0 没到 `bsd_init` 之前，16 线镜像的飞行只是消耗窗口。

## 29. F3 的第一件要证明的事：EFS 字节对得上，不是 QRTR 发布（2026-11-20 10:20）

Lead 10:05 第 5 条要求的离线推演。结论先给：**先证「读到的字节与独立来源逐字节一致」，
QRTR 端口发布是它的下游结果，不能当第一判据。** 理由与判据行如下。

### 29.1 为什么顺序不能反

| 如果先看 QRTR 发布 | 会发生什么 |
|---|---|
| 服务表从 2 个涨到 8 个 | 只能证明「modem 的 QMI 栈起来了」，不能证明它读到的是 `modemst1` 而不是别的分区、也不是全零窗口 |
| 服务表没涨 | 三种原因混在一起：读被拒、读成功但内容是垃圾（modem 拒绝继续）、读成功且内容正确但 QMI 又被别的东西挡住。三者需要完全不同的下一步，而日志分不开 |
| 读成功的判据是 `served` | `served` 只说明我们没拒绝，不说明搬了正确范围：`k60_qrtr_rmtfs_rw` 里 offset 算错、LUN 选错、窗口没写完，都会打 `served` |

而 `PongModemRuntime.cpp:271-277` 明确写着 RF 初始化会在 PAS4 之前就要读 EFS
（`while(!pong_rfs_ready() …) IOSleep(20)`，注释「RF initialization can request readwrite files immediately」），
所以 EFS 是**因**、QMI 起来是**果**。判据要钉在因上。

### 29.2 四行判据（按顺序读，越靠前越硬）

| # | 判据行（console，形状固定） | 判定 | 不成立的读法 |
|---|---|---|---|
| W1 | `K60UFS volume name=modemst1 lun=5 first=… last=…` | 名字解析到了 **LUN 5**（`sdf`），不是 LUN 0 | 打 `lun=0` 或整行缺失 ⇒ 逐 LUN 的 GPT 查名没生效（k54 之前的死因） |
| W2 | `K60MODEM qrtr: rmtfs rw storage=1 direction=0 bytes=4096 head=1000000003000000d801000020faa9c4` | `head` 与 29.3 的独立参照**逐字节相等** | 全零 / 全 `ff` / 与参照不同 ⇒ 读对了协议、读错了盘或偏移 |
| W3 | 同一存储上出现**第二次** `rmtfs rw`，且 offset 不同；`fsg`/`fsc` 也被 open | modem 接受了这份 EFS 并继续往下走 | 只有一次读、之后再无请求 ⇒ 内容被 modem 判为无效（不是我们的传输问题） |
| W4 | `K60MODEM qrtr: wait … services=` 从 2 涨到 >2，或出现新服务号 | 下游确认：QMI 栈真的起来了 | 只有 W4 成立、W2 没验过 ⇒ 结论不完整，不能宣布「EFS 通了」 |

W2 是唯一不能被别的东西意外满足的一行：它需要「正确的盘 + 正确的偏移 + 正确的长度 + 窗口真的写到 modem 能读的地方」
四件事同时成立。W1 只证盘，W3/W4 只证下游。

### 29.3 独立参照：本轮从 Android 只读取到的首块（2026-11-20 10:12）

设备当时在 Android（adb `6033dbec`，root）。用 `adb exec-out dd if=/dev/block/<dev> bs=4096 count=1` 各取 4 KiB，
**只读、不写任何分区**，落在 `E:/k60-work/evidence/efs-ground-truth-20261120/`：

| storage | 引导路径 | 分区 | LUN（`sd` 字母） | 首 16 字节 | 4 KiB sha256 |
|---|---|---|---|---|---|
| 1 | `/boot/modem_fs1` | `modemst1` = `sdf3` | 5（8 MiB） | `10000000 03000000 d8010000 20faa9c4` | `94c2aa725f4e8c5d3de317e8cd39f7efc1588866e7d2854011d10e4656a1a6bb` |
| 2 | `/boot/modem_fs2` | `modemst2` = `sdf4` | 5（8 MiB） | `11000000 03000000 d8010000 00026080` | `8610958511c22e7c44736363ac2b9c2d8e87bd16d78540fa2d4e97be1c489726` |
| 3 | `/boot/fsg` | `fsg` = `sdf5` | 5（8 MiB） | `14000000 03000000 d8010000 00000000` | `e9a62f2a22e469b8008da4dc2733148ae4abcf887c9e1277a7646123fdbc31b4` |
| 4 | `/boot/fsc` | `fsc` = `sdf6` | 5（1 MiB） | 全零 | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7`（= 4096 个 0 的 sha256） |

三点读法：

- 三个 EFS 超级块的头 12 字节是同一形状（`xx000000 03000000 d8010000`），第 13 字节起才分叉
  （`20faa9c4` / `00026080` / `00000000`）。所以 W2 只要 16 字节就能把三个存储区分开，不必搬 4 KiB。
- `fsc` 首块**本来就是全零**。这意味着「窗口全零」对 storage 4 是**正确**结果，对 1/2/3 是**错误**结果；
  判据不能写成「非零即通过」，必须按 storage 分别比。
- 四份首块都在 LUN 5 上；`lun=5` 是 W1 的期望值，`lun=0` 是 k54 之前的错法。

### 29.4 伪判据（写进判据表，免得下次又当成通过）

| 看起来像通过 | 实际不是 |
|---|---|
| `rmtfs rw … served` | 只证明我们返回了成功码；P-207 已经证明过「否定词以肯定词结尾」会把 `not-served` 读成 `served`，同理不要把「返回 0」当成「内容对」 |
| `rmtfs rw … vectors=0 served` | 0 个 scatter 项时什么都没搬，等于空转 |
| 窗口里全零 | 对 `fsc` 正确、对 `modemst1/2`/`fsg` 是错的（29.3） |
| modem 又发了几个 QRTR 包 | RX_DONE 的流动只能证明 transport 活着（k42 已证明它会在 35–45 秒后停），与 EFS 内容无关 |
| `rmtfs open` 打了四次 | open 只是路径与 storage 映射，四个镜像全 open 也不代表读到了数据 |

### 29.5 k54 与 F3 各证一段

| | k54（已构建，等 slot） | F3（27 侧，尚未开始） |
|---|---|---|
| 证什么 | W1 + `served`：名字解析到 LUN 5，读不再被拒 | W2 + W3：字节与独立参照一致，modem 继续要下一段 |
| 判据 | `judge-cellular-flight.py` 的 `volume lun chosen` 与 `rmtfs rw … served` | 上面 W2/W3 两行 |
| 失败时下一步 | 名字没解析到 LUN ⇒ 查 `findNamedVolumeOnLun` 与 GPT 表位置 | 字节不符 ⇒ 查 offset/窗口映射；字节符但 modem 不继续 ⇒ EFS 版本与 modem 固件不匹配 |

### 29.6 F3 需要的一行代码（只记录，不写）

W2 现在**没有**可读的日志：`k60_qrtr_rmtfs_rw`（`drivers/PongCellular/K60ModemLink.c:825`）只打
`storage=/direction=/vectors=` 与结果词。F3 之前要加一行，形状固定为：

```
K60MODEM qrtr: rmtfs rw storage=%u direction=%u bytes=%u head=%02x%02x…（前 16 字节，32 个 hex 字符）
```

- 位置：`k60_qrtr_rmtfs_rw` 返回 0 之后、调用点打印 `served` 之前，**每个 storage 只打一次**（静态去重），
  否则 modem 会连续读几百段，控制台会被冲掉。
- 成本：16 字节 hex 拼装，无额外内存；只在首次读时执行。
- 不写进 k54：k54 的镜像由 HEAD 构建，改它会让 `ab770b8c…`/`f38a7c9e…` 无法由 HEAD 复现（本线已踩过一次）。
  等 k54 判读完成后再落，进 k55。

### 29.7 F3 的链接前提：`coachz_baseband_*` 在 `QcomBaseband` 组件里

本轮顺带查清一件事，它决定 F3 什么时候必须把 `QcomBaseband` 加进 27 package：

- 五个补丁里有 **28 条 `+extern` 声明**（`0627`/`0628` 最多）。其中 `coachz_baseband_configure`、
  `coachz_baseband_enabled`、`coachz_baseband_qrtr`、`coachz_baseband_poll`、`coachz_baseband_report`、
  `coachz_baseband_new_server`、`coachz_baseband_del_server`、`coachz_modem_data_send`、
  `coachz_modem_data_receiver` 这 9 个**不在补丁集里，也不在 27 树里**，它们由
  `drivers/QcomBaseband/baseband/coachz_baseband.cpp` 定义（组件 @ `UniXNU/QcomBaseband` rev `dd0199cf`）。
- 其余 extern 由补丁集自身回答（`k60_modem_*` 在 `pong_modem_boot.c`/`pong_modem_pas.c`，`k60_ipa_marker` 在 `pong_ipa.c`），
  或由 27 树提供（`pmap_find_phys`、`ml_io_map_unmappable`、`flush_dcache64`、`delay`）。
- 结论：cellular 进 27 时 `QcomBaseband` **不是可选项而是链接前提**——`0627` 的 `K60ModemLink.c` 调 `coachz_baseband_*`，
  没有它就在链接期 `Undefined symbols`。这和 Lead「等 cellular 真进 27 再加 include+archives」一致，
  只是把「什么时候算真进」钉死为「F3 的第一次链接」。

## 30. 调用点位置的判据：应用成功不等于落在该落的地方（2026-11-20 10:24）

0629 能 `git apply --check` 通过，只证明上下文对得上；它不证明插入块落在
`if (error) goto done;` 之后、`native_owner_data_stage = 3;` 之前——若锚点被选到另一个 `= 3`，
补丁照样干净地打上，而基带在 Data 挂载之前就去读 EFS。所以把「位置」从意图变成可执行判据。

### 30.1 新脚本 `scripts/check-call-site-placement.py`

`--tree <xnu-work> [--stage 3] [--window 30] [--self-test]`，五条断言：

| # | 断言 | 不成立时的输出 |
|---|---|---|
| 1 | `native_owner_data_stage = 3;` 恰好一行 | `appears N times, need exactly one` |
| 2 | 每个探针恰好一个调用点（声明另计） | `has N call site(s) and M declaration(s)` |
| 3 | 先 modem 后 ipa | `k60_modem_probe_from_handoff is called after k60_ipa_probe_from_handoff` |
| 4 | 两者都在 stage 行之上、且不超过 30 行 | `is 37 lines above the stage, window is 30` |
| 5 | 两者都在最近一个 `goto done;` 之后（没有守卫时降级为 note） | `runs before the error guard above the stage` |

`--self-test` 六夹具：good / swapped（顺序反）/ double（两行 stage=3）/ order（探针被挪到 stage 之后）/
far（守卫与 stage 之间塞 40 行）/ 缺文件，输出
`K60 PLACEMENT PASS stage line, both probes, order, window, guard`。

### 30.2 接进三段路试跑

`scripts/verify-27-line.sh` 在五个补丁应用之后、追加 confiles 之前调用它，失败即
`K60 TRIAL FAILED the call-site block is not where the contract puts it`。种子树实测：

```
K60 TRIAL ok   0629-kern-exec-call-sites applies
K60 PLACEMENT ok   both probes run after the guard and before stage 3
K60 TRIAL ok   the call-site block sits between the guard and stage 3
K60 TRIAL ok   appended 19 build entries, bsd/conf now lists 19
K60 TRIAL PASS seed, five patches and the build entries on one clone
```

### 30.3 教训（P-265）

第一版脚本按「名字 + 左括号」数调用点，把 0629 块内的 `extern int …(void);` 也算进去，
于是正确的补丁被判成「调用了两次」。判据要能分「声明」与「调用」，否则它只会惩罚正确的产物。

### 30.4 同一分类器被 readiness 复用，集成模式第一次真正跑通

`check-ios27-readiness.py` 的 `call_sites()` 原来按出现次数数（`body.count(name)`），
集成树里每个探针同样命中两次，于是「已经打好的树」被判成
`K60 READY DRIFT call sites are not exactly once` —— P-265 的第二份副本。
现在 readiness 用 importlib 加载 `check-call-site-placement.py` 的 `inspect()`，两边共用一个分类器，
顺带把「顺序 / 窗口 / 守卫」三条也带进集成模式。

第一次用**真实集成树**跑集成模式（`verify-27-line.sh --keep` 留的副本，五个补丁 + 19 条 conffiles 全在）：

```
K60 READY ok   all 39 patch targets exist in the tree
K60 READY ok   all 19 build entries are in bsd/conf
K60 READY ok   both probes sit between the error guard and stage 3
K60 READY ok   the data mount anchor line is still there
K60 READY ok   only our own sources name ArmSmmu4KBuild, the weak fallback is what answers
K60 READY OK the integrated tree carries every ported patch and its wiring
```

这六行是 27 线第一次「补丁 + 构建表 + 探针位置 + 锚点 + 弱定义」同时在树里被测过；此前集成模式只有合成树覆盖。


## 31. 链接会不会红：把 19 个 extern 逐个问到出处（2026-11-20 10:50）

补丁能 apply、conffiles 齐全、探针在正确位置——这些都不回答「链接期还会不会
`Undefined symbols`」。`scripts/check-ios27-symbols.py` 补上这一格：读补丁要装的源码，
抽出每条 `extern` 声明，再回答它由谁定义，出处只有三种——补丁集自身、目标树、具名组件。

### 31.1 问答表（真实 27 树，19 条）

| 出处 | 数量 | 符号 |
|---|---|---|
| 补丁集自身 | 8 | `k60_ipa_marker` `k60_modem_qrtr_probe` `k60_modem_rails_vote` `k60_modem_scm_invoke`（条件编译对）`k60_modem_transport_prepare` `k60_modem_transport_stale` `coachz_modem_data_send` `coachz_modem_data_receiver` |
| 27 树 | 4 | `delay` → `osfmk/kern/clock.c`；`flush_dcache64` → `osfmk/arm64/caches_asm.s`；`ml_io_map_unmappable` → `osfmk/arm64/machine_routines.c`；`pmap_find_phys` → `osfmk/arm64/sptm/pmap/pmap.c` |
| `QcomBaseband` 组件 | 7 | `coachz_baseband_configure` `_del_server` `_enabled` `_new_server` `_poll` `_qrtr` `_report` |

两条对 F3 有用的结论：

1. `coachz_modem_data_send` / `coachz_modem_data_receiver` **不需要组件**——`pong_modem_link.c`
   自带桩（返回 ENETDOWN），所以数据面在 F3 里仍是关着的，但链接不缺东西。
2. 真正需要组件的只有 7 个 `coachz_baseband_*`，与 §29「QcomBaseband 是 F3 的链接前提」一致；
   §29 里按 `+extern` 行数数出来的「9 个」是行数不是符号数，这里改正。

### 31.2 四个坑：名字出现在文件里不等于它在文件里被定义

第一版判据是 `grep -rlw <symbol>`，它把四种非定义都算成定义（详见 P-266）：

- **调用**：`k60_modem_rails_vote();` 这一行带名字、带括号。
- **多行调用**：第一行以逗号或左括号结尾，和 K&R 参数表长得一样。
- **内核风格**：返回类型写在名字**上一行**（`void` 换行 `delay(`），单行看得见名字看不见类型。
- **汇编标签**：`_flush_dcache64:` 与 `LEXT(flush_dcache64)`——`` 在 `_` 前不是边界，正则先就没命中。

现在的做法是把声明**连接起来**读：从名字那行起按括号配平向后拼，右括号之后出现 `;` 是调用/声明，
出现 `{` 才是定义；`static` 定义回答不了 `extern`，除非两者在同一文件里分属条件编译的两支
（`pong_modem_pas.c` 的 `k60_modem_scm_invoke` 就是这种：`#ifdef K60_MODEM_SCM_TEST` 声明、
`#else` 定义）。

### 31.3 接进两处门禁

- `check-ios27-readiness.py`：pristine 模式新增一行
  `K60 READY ok   19 externs each have a provider: 8 patch set, 4 tree, 7 component`，
  并把「7 个 QcomBaseband 符号」写成期望（`EXPECTED_QBASEBAND = 7`）——组件若被绕过，
  这一行会漂移而不是静默通过。
- `verify-27-line.sh`：五个补丁 + conffiles 之后，对**克隆里**安装的 19 个 `.c` 跑一遍，
  失败即 `K60 TRIAL FAILED a symbol the clone installs has no provider`。这样「试跑全绿」
  才覆盖链接面，而不是只覆盖 apply 面。

漂移路径的取证：把 `--tree` 指向空目录，同一份源码报
`K60 SYMBOLS FAILED 4 symbol(s) resolve nowhere: delay flush_dcache64 ml_io_map_unmappable pmap_find_phys`
——正是那 4 个该由目标树回答的符号，说明三类出处是分别验证的，不是一条兜底。

### 31.4 第一次在克隆上跑就抓到一条

`verify-27-line.sh` 首跑报 `k60_modem_scm_invoke` 无处可去——不是链接真缺陷，而是它的定义是
`static`（上面那条条件编译对）。判据因此多了一类 `conditional`，输出
`K60 SYMBOLS ok   1 symbol(s) are static in their own file, live only under another configuration`。
这条修法留在了工具里，没有留成一次性的例外清单。


## 32. F3 之前要补的两个打包前提：一个管链接，一个管字节（2026-11-20 10:58）

§31 把「链接会不会红」量化成 7 个 `coachz_baseband_*` 符号。问到底，F3 之前缺的是两件性质不同的
东西：一件不补就连不上，另一件不补就算连上也读不出字节。两件都不在 27 profile 里，而且能在
`k60-gates/board.toml` 里指出是被哪一行拿掉的。

### 32.1 链接：7 个符号的两条来路都被关了

16 线拿到那 7 个符号，靠的不是组件清单——`board.toml:21` 的 `archives` 只有
`component:ArmDTPlatform`、`component:ArmCpu`、`component:PongUfs`。它是靠
`kernel.pong_native_driver_source`（`board.toml:45`）把整棵 `drivers/` 编进内核的：framework 把这个
键赋成 `PONG_NATIVE_DRIVER_SOURCE` 环境变量（`board.toml:40-44` 的注释写明由 `scripts/unixnu/kernel.py:191`
赋值），`build-xnu-4k-baseline.sh:250` 之后才找得到 ArmDT provider。

27 profile 把这条键整条 `remove` 了（`board.toml:346-353`），`.components.include` 里也没有
`QcomBaseband`（`:358-360` 只有 `ArmDTPlatform`、`ArmCpu`、`XnuPrelink`）⇒ 7 个符号在 27 上既没有驱动树
也没有组件，链接期就是 `Undefined symbols: _coachz_baseband_configure …`。

组件路线是现成的，只是要加两处：`include` 加 `QcomBaseband`，`archives` 加 `component:QcomBaseband`
（`components.toml` 里它的 `build = ["build-qcom-baseband.py"]`、输出 `build/qcom-baseband/libQcomBaseband.a`）。
两处必须同时加，因为 `scripts/unixnu/kernel.py:126-137` 的规则是：`archives` 里出现任何 `component:` 就进
**显式模式**，只构建被点名的组件（加依赖），并且随后用 `missing` 检查把「该有却没列」的组件点名报错。
27 的 `archives` 已经含两条 `component:`（`board.toml:383`），所以它本来就在显式模式里。

### 32.2 数据：`PongUfs` 不在 27 的 include 里

`board.toml:359` 的注释就是答案：「No PongUfs at stage 0; it returns in F3」；`:392` 记着
`native-source-storage=1` / `native-ufs-root=1` 也随它一起回来。PongUfs 在 16 线是 `archives` 里的
`component:PongUfs`（`:21`），27 的 include 里没有它（`:360`）。它缺席时，我们自己的弱定义
（`K60ModemLink.c:42-52`，返回 0）生效，每次 rmtfs 读都 `refused`，日志里只剩 `refused` 一个词。

**一处待核实，不当结论用**：`native_pong_ufs_read_named_volume` 的强定义究竟由 `libShengUfs.a` 里哪个
`.cpp` 产出。`components.toml` 给 PongUfs 的 `source_files` 只写 `["NativeUfs.cpp"]`，而本仓同一函数族的
实现在 `drivers/NativeUfs/NamedVolumeRead.cpp`；两者是否同一份源码，要看一次符号表或克隆，不能按名字
推断。这条不影响「PongUfs 必须进 27」的判断，只影响验收时该去哪找带地址的强符号。

### 32.3 顺序与验收行

顺序是死的：链接先、字节后。链接不通，内核到不了能读盘的阶段；链接通了但没有 PongUfs，
W1 那行 `K60UFS volume name=modemst1 lun=5 first=…` 根本不会出现——它由 PongUfs 侧打印，我们这侧
看不到它就没有第二种解释。这也是 §29 把「先证 EFS 字节」写成 W1–W4 的理由：`served` 只证明没拒绝。

四条验收行，都不需要新代码，只看 `board.toml` 与被构建的 `kernel.macho`：

1. 27 profile 的 `.components.include` 同时含 `PongUfs` 与 `QcomBaseband`；
2. 同 profile 的 `.components.archives` 同时含 `component:PongUfs` 与 `component:QcomBaseband`
   （16 线 `k60-cellular/board.toml:14` 与 `:21` 两处都已有这两个名字，27 是把它们照抄回来）；
3. `kernel.macho` 里 `_coachz_baseband_configure` 与 `_native_pong_ufs_read_named_volume` 都是强符号、带地址；
4. 控制台出现 W1 且 `lun=5`（`lun=0` 是 k54 之前的死因），才进入 W2 的字节比对。

### 32.4 一条随 k55 走的小改动

弱定义现在既不打印也不说明原因：27 stage 上 EFS 读被拒时只剩 `refused`，与「通道找错了」长得一样。
给它加一行诊断（例如 `K60MODEM efs: no named-volume reader in this kernel`）属于本分支，随 k55 一起走；
k54 的镜像必须能由当时的 HEAD 复现，所以不再回改。

边界：`k60-gates` 是 main，冻结条款未解。这两处 `board.toml` 何时落、由谁落按 Lead 10:05 的裁决走，
本线只写清楚补哪两处、怎么算补上了。

## 33. 27 的构建器拿不到原生 UFS 归档：开关和生产者住在两个文件里（2026-11-20 11:35）

### 33.1 三行事实

| 事实 | 位置 | 内容 |
|---|---|---|
| 谁选构建器 | `k60-gates/scripts/pick-xnu-builder.sh:23-24` | `ipados-16.6.1-20G81` → `build-xnu-4k-baseline.sh`；其它 profile 一律 `build-xnu-generic.sh` |
| 27 的链接行 | `k60-gates/scripts/build-xnu-generic.sh:646-650` | `XNU_NATIVE_UFS=1` 时 `UFS_ARCHIVE=$ROOT/build/sheng-ufs/libPongUfs.a`，紧接着 `test -f "$UFS_ARCHIVE"` |
| 真正的生产者 | `k60-gates/scripts/build-pong-ufs-probe-macos.py:31` 与 `:102` | `out = tree/'build/native-ufs'`、`libtool -static -o out/libNativeUfs.a`；只由 `build-xnu-4k-baseline.sh:432-441` 在 `XNU_NATIVE_UFS=1 && PONG_NATIVE_DRIVER_SOURCE` 时调用 |
| 16 线怎么链接 | `build-xnu-4k-baseline.sh:1054` 与 `:1278` | 同一个构建器写的是 `$ROOT/build/native-ufs/libNativeUfs.a` —— 与生产者一致 |

所以 `build/sheng-ufs/libPongUfs.a` 在两个仓库里只有 generic 这一处链接行与 `UniXNU/scripts/build-xnu-4k-baseline.sh:645`
提到，**没有任何脚本写它**。`CONFIG_XNU_NATIVE_UFS=y` 一开，27 的构建就停在 `test -f`。

### 33.2 为什么一直没暴露

`configs/mondrian_ios27_defconfig:20` 是 `CONFIG_XNU_NATIVE_UFS=n`，注释写着「PongUfs returns in F3」。
这条注释是事实，也是遮蔽：F3 一开开关，缺的东西并不是「PongUfs 组件没进包」——`components.toml` 的 PongUfs 没有
`build` 键（`build = None`），`scripts/unixnu/kernel.py` 的 `required` 集合只收有构建食谱的组件，
`component:PongUfs` 在 `archive_plan()` 里不会产生任何步骤——而是**归档本身没人产**。
同理 `QcomBaseband` 有 `build = ["build-qcom-baseband.py"]`，所以它在 include 里一出现就必须同时进 archives，
两者不是一种修法。

### 33.3 判据（`scripts/check-ios27-device.py` 新增）

`ufs_archive()` 做四步：读 27 kernel 块点名的 defconfig（`defconfig_path()` 取
`[os_overrides."ios-27.0.1-24A446".kernel]` 的 `defconfig`，缺省 `configs/mondrian_ios27_defconfig`）；看
`CONFIG_XNU_NATIVE_UFS=`；`y` 时从 `scripts/build-xnu-generic.sh` 抓 `UFS_ARCHIVE=$ROOT/<path>`；再要求
`scripts/` 里另有某行**同时**含该路径与写提示（`libtool`、`ar rcs`、` -o `、`cp `、`install -m`、`copyfile`、`copy2`）。

三态：`n` → ok；`y` 无写者 → DRIFT；`y` 有写者 → ok。只认「链接行以外还有写者」，因为链接行自己也会命中路径。
自测三夹具 → `K60 DEVICE PASS agreement, missing entry, differing copy, archive producer`；真仓现在多一行
`K60 DEVICE ok   the 27 defconfig keeps native UFS off (CONFIG_XNU_NATIVE_UFS=n)`，其余仍是 5 补丁缺副本的 DRIFT。

### 33.4 三条出路（不写代码，等 F3 排期）

1. generic 里补一步 `build-pong-ufs-probe-macos.py`，并把 `UFS_ARCHIVE` 指向 `build/native-ufs/libNativeUfs.a`（与 16 线一致）；
2. 只把路径改对、不管谁产 —— 不行，仍然没有写者；
3. 新写一个只产 `build/sheng-ufs/libPongUfs.a` 的脚本 —— 多一份与 probe 平行的编译器，不推荐。

推荐 (1)：两个仓库里唯一验证过的生产者就是 probe（k54 的符号表证明它产出的 reader 带 LUN 去重）。

### 33.5 附：k54 的符号表（把 §32.3 第 3 条变成实测）

`llvm-nm -a`（3.4 s，182,185 行，dump 在 `E:/k60-work/scratch/k54-nm.txt`）：

| 符号 | 地址 | 形式 |
|---|---|---|
| `_coachz_baseband_configure` | fffffff007a90058 | `external` |
| `_coachz_baseband_enabled` | fffffff007a8b1d8 | `external` |
| `_native_pong_ufs_read_named_volume` | fffffff007a84484 | `external` |
| `_ArmSmmu4KBuild` | fffffff007a66418 | `external` |
| `_ArmSmmu4KProgramDisabledContext` | fffffff007a66ee8 | `external` |

`llvm-nm -m` 里这五条都是 `external`，不是 `weak external`（k54 里 weak 一共 8 个，都是别的符号）⇒ 16 线拿到的
全是强定义。另有 `__ZZ33native_pong_ufs_read_named_volumeE13lastVolumeLun` 与 `…E14lastVolumeName` 两个函数内
静态量，说明 k54 里跑的是 `2b2183a7` 那版带 LUN 去重的 `PongUfsTransport.cpp`。27 侧没有这条强定义，只有
0628 的两个 weak 定义兜住 SMMU、`pong_modem_link.c:42-52` 兜住 reader。

## 34. IPA 分配器的上界：0 不是「默认」，是「不设界」（2026-11-20 11:45）

### 34.1 缺陷

`drivers/PongCellular/K60Ipa.c` 原来是这一行：

```c
kmem_alloc_contig(kernel_map, &address, bytes, mask, 0, 0,
    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT)
```

27 树的声明写着（`osfmk/vm/vm_kern_xnu.h:570`）：`@param max_pnum  The maximum page number to allocate, or 0.`，
而 `osfmk/vm/vm_resident.c:2015-2016` 把 0 翻译成 `max_pnum = PPNUM_MAX`。所以第五参传 0 不是「最小」也不是
「按默认」，是「整条物理内存随你挑」。旧代码在事后用 `ptoa_64(page) + bytes > (1ull << 36)` 拦：命中就
`return K60IpaRuntimeFailed`——页已经从分配器手里拿走、没有 `kmem_free`、没有重试、没有日志。k48 在 RMTFS 上
是同一个形状：八次分配全在 4 GiB 以上（`attempt 7 … phys=0x90e733000`），然后 `alloc … physical=0`。

### 34.2 改法

- `K60Ipa.h` 加两个 inline 与 `K60_IPA_RUNTIME_DMA_LIMIT = 1ull << 36`：
  `k60_ipa_runtime_ceiling(bytes, page_bytes, *ceiling)` 返回「page × page_bytes + bytes 仍在界内」的最大物理页号；
  `k60_ipa_runtime_address_fits(physical, bytes)` 是同一窗口的回读判断，带 `physical + bytes > physical` 防回绕。
  放头文件是因为两者都是纯整数运算，宿主测试不进内核就能跑。
- `k60_ipa_runtime_alloc` 先算 ceiling 再把它交给第五参；分配失败或回读越界就 `kmem_free` 还页后重试一次，
  两次都不行打 `K60IPA runtime alloc failed bytes= mask= attempts=`。`KMA_PERMANENT` 去掉——k47 的 panic 就是
  「永久映射被 `kmem_free`」（`vm_map.c:7940`）。
- 请求本身不可能满足时（bytes 为 0、页大小取不到、bytes ≥ 2^36）先打 `K60IPA runtime alloc refused bytes= limit=`，
  再返回 `K60IpaBadArgument`，不走进分配器。

### 34.3 两个数字只能留一个

早先的草稿把 ceiling 写成 `(1ull << 32) - bytes`，而代码自己的拒绝线是 `1ull << 36`。两个数并排放着，等于
「上界说 4 GiB、回读说 64 GiB」：ceiling 严于回读时，回读那半永远不触发，日志里那句 `limit=` 就成了假话；
反过来 ceiling 松了，回读才会兜住。这里取代码里已有的 2^36（IPA 的总线解码宽度），并让 ceiling 与回读共用
同一个宏 `K60_IPA_RUNTIME_DMA_LIMIT`，测试也按它写。教训不是「36 对 32 错」，而是「同一个界只能有一个真值」。

### 34.4 宿主测试

`scripts/tests/test-k60-ipa-runtime-ceiling.c`（`gcc -std=c11 -O1 -Wall -Wextra -Werror -Idrivers/PongCellular`）：
四个真实尺寸（4 KiB、16 KiB 页、1 MiB ring、20 MiB 表）逐个断言「ceiling×页 + bytes ≤ 界」「再高一页就越界」
「最高合法地址 fits」「第一个非法地址不 fits」；4 KiB 请求必须给出 `2^24 - 1`，20 MiB 请求必须把上界压到
`2^24 - 0x1400` 页；拒绝零字节、零页大小、空输出指针、等于与大于 2^36 的请求；回读拒绝 0、恰好到界、越一字节、
以及 `UINT64_MAX - 0xfff` 这种会回绕的和。输出 `K60 IPA RUNTIME CEILING PASS bound, readback, refusals, wrap`。

### 34.5 门禁

`scripts/check-ios27-readiness.py` 新增 `RUNTIME_BOUND` 与 `runtime_bound()`，在 0628 里要求四个记号：两个 inline 的
名字、带 `(ppnum_t)ceiling` 的那次调用、重试前的 `kmem_free(kernel_map, address, bytes);`。真实树输出
`K60 READY ok   the IPA allocator asks for a bounded page number`；把那次 cast 改回 0 实测报
`K60 READY DRIFT the 27 IPA allocator lost its bound` 与 `CHANGED 1 expectation(s) drifted`，改回后整份全绿。

### 34.6 边界

0623 由 `scripts/gen-ipa-patch.py` 重生（175,356 → 177,932 B），0628 由 `port-cellular-to-xnu27.py` 重生
（175,285 → 177,861 B），其余四个补丁字节不变。`scripts/verify-27-line.sh` 仍然 `K60 TRIAL PASS`。
16 线 `feat/cellular` 的 `K60Ipa.c` 一行没动，k54（boot `f38a7c9e…`）仍可由 HEAD 复现；这条修法随 k55 落 16 线。

## 35. 27 线的 C 从来没被编译过：一行 stray backslash 与补上的门禁（2026-11-20 12:00）

### 35.1 现象

0628 在 11:15 到 11:55 之间带着一行语法错误：两个弱定义兜底的诊断写成了
`printf("K60IPA smmu: no ArmSmmu4K in this kernel"" "` + 反斜杠 + `n");`。`"" "` 把字符串切成三段，反斜杠落在
字面量外面，gcc 报 `stray backslash in program`。两处（`K60Ipa.c` 754 与 768）都是这一行。

### 35.2 为什么整条链没发现

它进仓库的路径是：改 `drivers/PongCellular/K60Ipa.c` → `gen-ipa-patch.py` 重新生成 0623 →
`port-cellular-to-xnu27.py` 生成 0628 → `git apply --check` 通过 → readiness 全绿 → 提交。这一串里没有一步编译过
这段 C：`apply --check` 只比文本，`gen-ipa-patch` 只拼补丁，readiness 只查记号，`verify-27-line.sh` 到今早为止
只 apply、追加 conffiles、算 extern。而 27 线**没有**宿主测试运行器（`scripts/run-host-tests.sh` 只在 16 线），
所以那 18 个源在这一侧一次都没被编译器看过。弱定义兜底是 11:15 落的，等于说这段代码在 HEAD 上躺了 45 分钟。

### 35.3 抓到它的方法

把 16 线那份 `run-host-tests.sh` 的 `cd` 改成指向 27 线工作树再跑（它本来就是同一批源文件、同一批测试）。
`-DK60_HOST_TEST -Wall -Wextra -Werror` 立刻在两行上报错。问题不在「谁的代码错」，在「哪一侧有编译器」。

### 35.4 补上的门禁

`scripts/verify-27-line.sh` 在五个补丁全部 apply、调用点判据通过之后，把克隆里的 `bsd/dev/pong_*.c` 与
`qcom_glink.c` 逐个跑 `gcc -fsyntax-only -std=c11 -DK60_HOST_TEST -I<clone>/bsd/dev`，每装一个源文件就让它过一遍
宿主编译器，失败即 `K60 TRIAL FAILED <file> does not parse`。补丁集里每个源都带宿主 shim（`#ifdef K60_HOST_TEST`
引 `<stdio.h>` 而不是 `pexpert/pexpert.h`），所以这条不需要 16 线的头文件树。真实树上的输出：
`K60 TRIAL ok   every installed source parses on the host`，其后 conffiles 与 externs 两步照旧。

### 35.5 已打好的树也过一遍编译器

`check-ios27-readiness.py` 的集成模式（树里已经有 `bsd/dev/pong_modem_link.c` 时走的那半）补了同一步：
按 `conffiles-port.txt` 列出树里的 `.c`，逐个 `gcc -fsyntax-only -std=c11 -DK60_HOST_TEST -I<tree>/bsd/dev`，
失败即 `K60 READY DRIFT <n> installed source(s) do not parse: <file>: <第一行诊断>`。gcc 不在 PATH 上时只说
`note gcc is not on PATH, so the sources were not parsed`，不算漂移——工具不能因为环境缺件而报红。

实测（试跑克隆 `/mnt/e/k60-work/scratch/xnu27-trial-xIMvSW/xnu`）：干净时 `K60 READY ok   every installed source parses 
on the host` + `K60 READY OK`；往 `pong_modem_image.c` 尾部塞一行 `int x = ;` 后 `K60 READY DRIFT 1 installed 
source(s) do not parse: pong_modem_image.c: … In function ‘broken’` + `CHANGED 2 expectation(s) drifted`
（第二条是补丁反打失败，同一处改动本就该报两条）。

顺带一个只在这轮才看清的事实：`"" "` 把字符串切成三段**本身是合法的**（相邻字面量拼接），真正致命的是
落在引号外的那个反斜杠。所以判据只能抓编译器，抓不到「长得像笔误」的形状。

### 35.6 两道关都用 16 线的告警口径

两处编译关都带 `-Wall -Wextra -Werror`，与 16 线 `run-host-tests.sh` 同口径：19 个源在试跑克隆里全过
（`fail=0`）。理由是不带告警时「能编过」只等于语法正确，而 16 线一直按 -Werror 维护这些文件；
放宽反而会让同一份代码在两条线上有不同标准。

### 35.7 修完的尺寸

0623 177,932 → 177,924 B，0628 177,861 → 177,853 B（各 −8 B，正是两处 `"" "` 变成一处 `"`）。
其余四个补丁与 `conffiles-port.txt` 不变；readiness 仍 `K60 READY OK`。

## 36. 宿主测试套件进了仓库：`scripts/run-host-tests.sh`（2026-11-20 12:30）

### 36.1 为什么现在才进

这套命令在 `/mnt/e/k60-work/artifacts/run-host-tests.sh` 里活了几个星期，59 行、`cd` 写死 16 线路径。
按铁则 5，一个能通过但不在仓库里的检查对读仓库的人是隐形的；更直接的是 P-269——27 线的 C 之所以
从没被编译过，正因为这套命令只存在于 scratch 且只指向 16 线。它不是便利脚本，是门禁。

### 36.2 形状

`bash scripts/run-host-tests.sh [--list]`，`REPO` 由脚本自身位置推出（不写死路径），二进制默认进
`build/host-tests`，`K60_HOST_TEST_OUT` 可覆盖。两张表：`TESTS`（C/C++，每行 `名字|编译参数|源文件`）
与 `PY_TESTS`（`名字|命令`）。**源文件不在本检出就 skip 并计数，不算失败**——同一份脚本要在 16 线与
27 线上跑，两条线带的驱动不一样（27 线没有 `PongAdreno/ArmSmmu4K`、16 线没有 `K60Ipa.h` 的上界 inline）。
结尾一行 `K60 HOST PASS <n> suite(s), <m> skipped` 或 `K60 HOST FAILED <k> of <n>`。

### 36.3 27 线实测

`K60 HOST PASS 30 suite(s), 2 skipped, binaries in /mnt/e/k60-work/artifacts/tests27`。skip 的两条是
`test-k60-flight-fixtures.py` 与 `next-pitfall-id.py`——它们在 `feat/cellular`/main 上，27 线还没有。
27 线独有的 `test-k60-ipa-runtime-ceiling.c` 在表里，输出 `K60 IPA RUNTIME CEILING PASS bound, 
readback, refusals, wrap`。

### 36.4 与试跑脚本的分工

`verify-27-line.sh` 在克隆里对**装进补丁的**源做 `-fsyntax-only`（判据是「补丁集里的文本能编译」）；
`run-host-tests.sh` 在**本检出**上跑全部测试与自测（判据是「这些行为还对」）。两者不重叠：前者防 P-269
那种「只加文件的补丁」，后者防行为回归。
