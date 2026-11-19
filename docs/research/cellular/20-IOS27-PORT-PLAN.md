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
