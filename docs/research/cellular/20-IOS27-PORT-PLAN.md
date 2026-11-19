# 20 — 把 cellular 这一线搬到 iOS 27：现在的账与搬法

日期：2026-11-20。范围：`patches/xnu/062*`（基带与 IPA）与 `drivers/PongCellular/`。

## 1. 边界

27 侧 cellular 在 SpringBoard 打通前不动：新 main 从 stage-0 起，主仓归档为 `archive/ios16-20261120`。
本文只回答一个问题——**等 27 能起桌面了，这条线要按什么顺序、改哪些地方搬过去**，以及在 16 线上能提前做掉哪些与页大小/内核版本有关的隐患。

## 2. 这条线在 16 线上由六个补丁组成

| 补丁 | 大小 | 碰的是什么 | 与内核版本的关系 |
|---|---|---|---|
| `0620-k60-modem-image.patch` | 8,158 B | 新增 `bsd/dev/pong_modem_image.{c,h}`、`pong_modem_table.h` | 纯新增，无内核 API 面 |
| `0621-k60-modem-pas.patch` | 21,440 B | 新增 `pong_modem_boot.c`、`pong_modem_pas.{c,h}`，并在 `bsd/kern/kern_exec.c` 插一处调用 | 新增部分无版本依赖；call site 依赖行号 |
| `0622-k60-modem-qrtr.patch` | 170,730 B | 12 个 `bsd/dev/` 新文件（QRTR、GLINK、RMTFS、EFS、memshare、SMP2P） | 生成产物，纯新增 |
| `0623-k60-ipa.patch` | 174,551 B | 新增 `pong_ipa*.{c,h}` 十一对 | 生成产物，纯新增 |
| `0624-k60-ipa-call-site.patch` | 596 B | `kern_exec.c` 第二处调用（`k60_ipa_probe_from_handoff()`） | 只依赖行号与上下文 |
| `0621-k60-io-submap-budget.patch` | 1,712 B | `osfmk/arm/io_map.c` 的 `IO_MAP_SIZE` 8 MiB → 32 MiB | 依赖 `io_map.c` 的宏还在、`io_range` 的分配方式没变 |

`series` 里它们的顺序（第 225–230 行）是：0620、0621-pas、0622、0623、0624、0621-io-submap。

## 3. 编号撞车，搬过去必须先重排

`main` 自己有一条 `0621-k60-io-submap-budget`，与我们的 `0621-k60-modem-pas` 同号；`0622`/`0623`/`0624` 同理。
并入 27 线时把这条线整体顺延到 **0626 起**，并保持相对顺序（0626 镜像、0627 PAS、0628 QRTR、0629 IPA、0630 IPA call site、0631 io-submap 预算）。
顺延只改文件名与 `series` 里的行，不改补丁内容。

## 4. 页大小：本轮把唯一的硬编码拆掉了

16 线是 16 KiB 页，27 线用的 `patches/xnu-12377/series` 是 4 KiB 页（本工作树里没有这棵 27 树，按 Lead 记录）。
盘点下来只有一处按 4 KiB 写死：

- `drivers/PongCellular/K60ModemLink.c` 的 `k60_qrtr_rmtfs_low_alloc()`：`max_pnum` 上限原来写 `((1ull << 32) - bytes) >> 12`。
  已改成 `((1ull << 32) - bytes) / ptoa_64(1)`——`max_pnum` 的单位是物理页，除以真实页大小后「低于 4 GiB」在两种页大小下意思一致。
  4 KiB 内核上结果与旧式完全相同（`ptoa_64(1) == 4096`），所以 16 线的 k53 行为不变。

其余位置都是页大小自适应的，搬之前不用改：

- `round_page()`、`ptoa_64()`、`pmap_find_phys()` 都按内核自己的页大小工作；
- `K60ModemBoot.c` 的 `K60_MODEM_PROBE_PAGE 0x1000` 是**映射长度**，`ml_io_map` 会向上取整，不是页假设；
- `0621-k60-io-submap-budget` 是 MiB 级虚拟地址预算，与页大小无关；
- **`K60_IPA_GSI_PAGE_SIZE 0x1000` 不能改**：那是 GSI 硬件的 TRE 环粒度（`_Static_assert(K60_IPA_GSI_TRE_BYTES * K60_IPA_GSI_TRE_COUNT == 0x1000)`），与 VM 页无关。

## 5. call site 必须对合并后的 `kern_exec.c` 重生成

`0621` 与 `0624` 各改一处 `kern_exec.c`。27 树的行号与上下文都不同（16 线的 0624 是 `@@ -7930,6 +7930,14 @@`），照搬会打成错位置或干脆不 apply。配方（P-155）：

```
git -C <27 tree> show HEAD:bsd/kern/kern_exec.c > /tmp/kern_exec.27.c
cp <27 tree>/bsd/kern/kern_exec.c /tmp/kern_exec.27.c && $EDITOR /tmp/kern_exec.27.c   # 只插两处调用
diff -u <27 tree>/bsd/kern/kern_exec.c /tmp/kern_exec.27.c > 0627-kern-exec-call-sites.patch
```

两处调用可以合成一个补丁，但要保持「`k60_modem_probe_from_handoff()` 在前、`k60_ipa_probe_from_handoff()` 在后」的次序：
modem 的 probe 里会读 payload FAT 的 `md0`，IPA 的 probe 复用同一份 metadata。

## 6. 生成产物的重建链

`0622` 与 `0623` 不是手写的，仓库里有两台生成器：

- `scripts/update-modem-qrtr-patch.py` ← `drivers/PongCellular/K60Modem*.{c,h}` + `K60Smem.h` + `QcomGlink.{c,h}` + `K60PmicRail.h`，把 `#include "K60…"` 改名成 `pong_…`，并在写盘前检查条件编译配平、carried 文件不得残留 `K60…`/`Qcom…` 头名；
- IPA 那台对应 `scripts/update-modem-ipa-patch.py`（`0623`），同样按 `FILES` 逐段重建。

搬到 27 树后先跑两台生成器，再跑 `scripts/tests/test-k60-modem-image.py`（30 段、地址连续）——这两步能证明 carried 副本与源码一致，不需要编内核。

## 7. 搬之前就能在 16 线上做掉的验证

| 项 | 命令 | 期望 |
|---|---|---|
| carried 一致 | `python3 scripts/update-modem-qrtr-patch.py --check` | 无 stale |
| 镜像布局 | `python3 scripts/tests/test-k60-modem-image.py` | `TESTS OK 30 segments` |
| 宿主逻辑 | `bash /mnt/e/k60-work/artifacts/run-host-tests.sh` | 28 行 PASS（含 EFS/memshare/SMP2P/sysmon/判据 self-test） |
| 记录一致 | `K60_DEVICE_INPUT=… python3 scripts/porting-gate.py --quick` | 通过 |

## 8. 27 侧还需要决定的事

1. **UFS 只读入口的归属**：`native_pong_ufs_read_named_volume()` 现在挂在 `drivers/NativeUfs/PongUfsTransport.cpp`，是 Lead 授权的只读新增。27 树的 NativeUfs 若与 16 不同源，这个入口要重新谈一次。
2. **Data 命名空间**：Pong 的注释写明 RF 初始化会立刻要求读写文件，所以 PAS 必须在 native Data 挂载之后（`PongModemRuntime.cpp:271-277`）。27 的挂载时机要先测出来。
3. **sysmon 接线**（k54）：`K60ModemSysmon.*` 已写好并有宿主测试，但没有调用者、没进 0622；它属于「版本无关的硬件契约」，可以安全一起搬。
4. **IPA 的 SMMU 口径**：`b9de56b9` 放宽了 `ArmSmmu4K` 对 Device-nGnRE（writeback=2）的限制，仍在 `drivers/PongAdreno/ArmSmmu4K/` 里，搬 27 前需要那棵树的主人确认它是否已经吸收了这个改动。

## 9. 解除封锁后的顺序

1. SpringBoard 在 27 打通；2. 搬 `0626`/`0627`（纯新增 + 一个 call site），确认 `kern_exec.c` 干净；
3. 跑两台生成器搬 `0628`/`0629`，`test-k60-modem-image.py` 过；4. `0631` 的 io_submap 预算（若 27 的 `io_map.c` 结构未变）；
5. 第一飞只用 `pong_modem` + `pong_qrtr=2`，判据沿用 `scripts/judge-cellular-flight.py`——它只看日志行，与 OS 版本无关。

