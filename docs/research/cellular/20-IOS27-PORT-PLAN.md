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

## 9.1 待办：IPA 运行期分配没有页上限

`drivers/PongCellular/K60Ipa.c:892` 的 `kmem_alloc_contig(kernel_map, &address, bytes, mask, 0, 0, ...)` 第 5 参数传 0，
即不限制物理页，只靠分配后的 `ptoa_64(page)+bytes > 1<<36` 检查拒绝——命中就返回 `K60IpaRuntimeFailed`，不重试。
16 线上没暴露（IPA 没打开过），27 的内存布局未必一样。若要补，照 RMTFS 的写法给 `max_pnum` 一个 36 位上界并保留一次重试；
因为改的是 IPA 路径、本线当前无法上机验证，先记录不动。

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
| 控制桥：QMUX 帧、QMI 客户端分配、服务发现与回复路由 | `drivers/QcomBaseband`（`component:QcomBaseband`，`board.toml:14/21` 已选）、`patches/qcombaseband/0001-coachz-defer-publication.patch` | 有；27 树要重新 pin 子模块提交 |
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
| 更新时 `components.toml` 与 submodule 同提交 | 16 线已 pin；**27 树要重新 pin**（27 侧目前还没有 `drivers/QcomBaseband`） |
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
