# ShengUfs 验证表与根发布层的移植草案（2026-11-17）

> 状态：只读审计产出，未改任何代码。来源 `references/ShengUfs@9d527ae`（本地参考树），
> 许可证 `BSD-2-Clause-Patent`（每个文件头 SPDX 已写明）。
> 目标代码树：`drivers/NativeUfs`。合并这条线必须另开 `feat/ufs-verified-table`，不要进 `docs/porting-gap-audit`。

## 0. 为什么要它

`drivers/NativeUfs` 目前有 11 个头/实现（约 1,832 行），负责根设备的 probe 与 SHNGROOT 窗口；
`PongUfsTransport.cpp` 提供 `PongUfsBlock`（IOBlockStorageDevice）与三个窗口（`RootDiskWindow` :55、
`gRootWindows[3]` :63、`PongUfsBlock` :225、`init` :422）。**没有**「验证过的根哈希表缓存」与
「根窗口发布顺序」这两层。参考树 ShengUfs 比 catalog pin `99d8bcd` 新，多出的正是：

| 文件 | 行数 | 作用 |
|---|---|---|
| `VerifiedTableCache.h` | 166 | 按窗口哈希表页做 4 KiB 认证缓存；`VrootTable`/`VrootCacheEntry`/`VrootCacheStats`/`VrootTableCache`，模板 ops：`lock/unlock/sleep/wakeup/readPage/sha256` |
| `RootPublication.h` | 84 | 根窗口发布顺序 `ufsBuildRootPlan`（SystemOS 优先、OS 最后）、`ufsPrepareRootWindows`/`ufsPublishRootWindows`（失败时保留已发布对象的生命周期） |
| `RootWindowRead.h` | 54 | 窗口读路径 `ufsWindowGeometry`、`UfsWindowGuard`（锁）、`ufsReadWindow`（按 4 KiB 校验+拷贝，`kDataMax` 分块） |
| `tests/VerifiedTableCache.cpp` | 191 | 缓存命中/未命中/等待/淘汰/失败/丢弃 |
| `tests/RootPublication.cpp` | 86 | 发布顺序与失败路径 |
| `tests/RootWindowRead.cpp` | 97 | 几何校验与读写边界 |

## 1. 现有头文件的差异（先只抄不接线）

| 文件 | 我们 vs 参考 |
|---|---|
| `CompletionWait.h` | **逐字节相同** |
| `RootDiagnostics.h` | **逐字节相同** |
| `RootCommands.h` | 有差异（我们 329 行 vs 参考 602 行——参考多出近一倍，必须逐段 diff） |
| `RootLayout.h` | 有差异（我们 254 vs 参考 231） |
| `RootQueue.h` | 有差异（我们 63 vs 参考 66） |
| `RootTransportLayout.h` | 有差异（我们 44 vs 参考 34） |
| `SmmuTakeover.h` | 有差异（145 vs 参考 127） |
| `TransferPoll.h` | 行数相同（28 vs 28）但内容有差异 |

差异可能是参考树更新（补了字段/注释）而非语义不同；**必须先逐文件 diff 再抄**，不能整目录覆盖。
`GccUfs.h` 只在参考树有；我们 `NativeUfs.cpp:26` 用常量 `kGccUfsPage` 自己读，不依赖该头。

## 2. 接线点（我们的代码）

- `PongUfsTransport.cpp:55` `RootDiskWindow`、`:63` `gRootWindows[3]`：窗口选择与 `baseByte/size` 的权威来源。
- `PongUfsTransport.cpp:225` `PongUfsBlock`、`:422` `init()`：读/写块入口，`doAsyncReadWrite` 目前没有「按窗口哈希表校验块」的步骤。
- `PongUfsTransport.cpp:258` `native_pong_log_ufs_window_media()` 与 `:300` APFS UUID 检查：只是媒体枚举/日志，不是完整性校验。
- `NativeUfs.cpp:184` `mapPhysical(kGccUfsPage,...)`：GCC 寄存器页，与本层无关。

**接入方式**：给 `PongUfsBlock` 增加一个 `Ops` 适配器：
`lock/unlock` 用现有 `mutex`；`sleep/wakeup` 用 `IOLockSleep`/`IOLockWakeup`（或 `IOCommandGate`）；
`readPage(table,page,dst)` 走现有 transport 的 4 KiB 读；`sha256(data,bytes,out)` 用内核 crypto 或本地实现。
`doAsyncReadWrite` 在读路径调用 `vrootTableEntry()` 得到的 32 字节哈希与块比较，失败返回 `kIOReturnIOError`。
发布顺序用 `ufsBuildRootPlan`/`ufsPrepareRootWindows`/`ufsPublishRootWindows` 替换现在 `gRootWindows` 的启动循环。

## 3. 分三步落地（建议顺序）

1. **只读搬运**（不改行为）：把 3 个头文件 + 3 个测试复制到 `drivers/NativeUfs/`（或 `tests/`），
   用独立 host 编译跑通 3 个测试（参考树测试是纯 host 的 `Ops` mock，不依赖 IOKit）。
   验收：`tests/VerifiedTableCache.cpp`、`RootPublication.cpp`、`RootWindowRead.cpp` 全过；
   `NativeUfs.cpp` 编译不变。
1.5 **验证头与策略表（2026-11-17 审计补的前置）**：参考实现把 `VerifiedTableCache` 接到
   `vr_open_header`/`vr_open` 得到的 `vr_view` 上（`references/ShengUfs/NativeUfs.cpp:2169-2330` 的
   `configureCachedTable`、`readPolicyTable`、`verified_root_key`）。本仓当前 `RootLayout` 只校验
   SHNGROOT manifest 前 4064 字节的 SHA-256（`RootLayout.h:180-250`），**没有**签名头、`VR_KEY_BYTES`
   公钥和 LUN 0 的 `<window>.vroot` 策略表；没有这些输入，`VrootTable` 的 `pageHashes`/`firstLba` 无从填写。
   因此第 2 步之前必须先移植 `verified_root.h` 的 kernel 侧（不是本分支的 `tests/support` host 副本）
   与策略表读取/签名校验，并加 host fixture；在这之前 `native-vroot-cache` 必须保持关闭。
2. **接缓存**：实现 `VrootOps` 适配器与 `VrootTableCache` 实例；在 `PongUfsBlock::doAsyncReadWrite` 的读路径
   接入 `vrootTableEntry`。先只对 `OS`/`SystemOS` 两个只读窗口启用，`Data` 窗口暂不启用（P-152/P-153）。
   验收：host 单测 + 构建；上机必须由 Lead 安排（根挂载面，不可自行刷）。
3. **接发布顺序**：把窗口启动改成 `ufsBuildRootPlan` + `ufsPrepareRootWindows` + `ufsPublishRootWindows`，
   保留现有 `gRootWindows` 的字段来源；失败时按参考实现保留已发布对象。
   验收：上机日志 `PONG APFS` 三窗顺序与 `K60DATA mounted ro=0` 不变；回退只需还原一个调用点。

## 3.1 步骤 1 执行记录（2026-11-17 03:04）

- 分支 `feat/ufs-verified-table`（从 `origin/main` `74c0d24e` 拉出），HEAD `848b7b87d3276cecf504e2662193f9db7c0d2876`，已推 origin。
- 复制 3 头 + 3 测试 + `tests/support/{verified_root.h,verified_root.c}`；`RootWindowRead.cpp:80` 做一处 GCC `initializer_list` 等价改写；提交 `7273dc64`，文档/CREDITS 提交 `848b7b87`。
- 三个 host 测试全过：`RootPublication`（7 组）、`RootWindowRead`（7 组）、`VerifiedTableCache`（并发 `hits=714 misses=886 reads=886 evictions=884 waits=3889`）。
- 未接任何运行路径，`NativeUfs.cpp`/`PongUfsTransport.cpp` 未改，未 boot。

## 3.2 步骤 1.5 执行记录（2026-11-17 03:40）

- 分支 `feat/ufs-verified-table`，从步骤 1 的 `848b7b87` 继续。
- 从 `UniXNU/VerifiedRoot@974f043d0c71ba2e60331483a41c6c6d35274ee3`（catalog pin；本地 submodule `def0266` 没有 `vr_open_header`）复制 kernel 侧
  `k60-ufs-verified:drivers/NativeUfs/verified_root.h`、`k60-ufs-verified:drivers/NativeUfs/verified_root.c`、`k60-ufs-verified:drivers/NativeUfs/xnu_crypto.c`；接口 `VerifiedBlockPolicy.h` 取自 `UniXNU/VirtioMmioBlock`。
- 新增 `k60-ufs-verified:drivers/NativeUfs/RootPolicyTable.h`：按签名头里的 `image_bytes` 选 policy，header-only 时从 LUN 0 读
  `<window>.vroot`，先 `vr_open_header` 再校验表哈希并填充 `vr_view.hashes`；full envelope 直接 `vr_open`。
- 新增 `tests/RootPolicyTable.cpp` 与 `tests/check-verified-root.py`：生成真实 RSA-3072 / PKCS1v1.5-SHA256 的
  full/header-only manifest，覆盖选 policy、LUN 0 读表、错 anchor、错表、截断头、低 generation、改 header 字节。
- 四个 host 测试全过：`RootPublication`、`RootWindowRead`、`VerifiedTableCache`、`RootPolicyTable`。
- 未接 `NativeUfs.cpp`/`PongUfsTransport.cpp`，`native-vroot-cache` 仍关闭，未 boot。

## 3.3 步骤 2a 执行记录（2026-11-17 04:20）

- 分支 `feat/ufs-verified-table`，从步骤 1.5 的 `14cf0488` 继续。
- 新增 `k60-ufs-verified:drivers/NativeUfs/RootWindowVerifier.h`：把 full envelope 与 header-only 两条路径收进同一个 `RootWindowVerifier`；
  header-only 时 `rootWindowVerifierConfigure` 校验签名头、按 `<window>.vroot` 读表、用调用方提供的 page-hash/where/scratch/缓存数组
  逐页哈希并核对整表 digest，之后只保留 page hash 与 `VrootTableCache`，`rootWindowVerifierVerify` 用 `vrootVerifyBlock` 校验单块。
  所有缓冲区由调用方持有，适配器不分配内存，也不依赖 IOKit。
- 新增 `tests/RootWindowVerifier.cpp`：覆盖 full envelope、header-only 首次读表/缓存命中、错误块、坏表拒绝和缺缓存内存拒绝；
  `tests/check-verified-root.py` 同时编译并运行 `RootPolicyTable` 与 `RootWindowVerifier`。
- 宿主测试全过：`RootPublication`、`RootWindowRead`、`VerifiedTableCache`、`RootPolicyTable`、`RootWindowVerifier`。
- 本节记录时尚未把 `RootWindowVerifier` 接进 `PongUfsTransport.cpp`；步骤 2b 已在 §3.4 完成，3b 的 prepare/start 拆分见 §3.6。运行路径还需要在 `PongUfsBlock` 里分配 header/page-hash/where/缓存内存、
  定义 `VrootOps` 的 `lock/sleep/wakeup/readPage`，并决定 `NATIVE_VERIFIED_BLOCK` 构建开关；`native-vroot-cache` 仍关闭，未 boot。

## 3.4 步骤 2b 执行记录（2026-11-17 04:40）

- 分支 `feat/ufs-verified-table`，从步骤 2a 的 `aaeb262b` 继续；`PongUfsTransport.cpp` 在 `#if NATIVE_VERIFIED_BLOCK` 下接入 `RootWindowVerifier`，默认关闭。
- `PongUfsBlock` 增加 per-window verifier、`vrootLock` 和 header/page-hash/where/scratch/512 页（2 MiB）缓存；`start()` 对非 Data 窗口先 `rootPolicySelect` 再 `rootWindowVerifierConfigure`，失败不发布该窗口。Data 保持旧路径（P-152/P-153）。3b 已把 `start()` 拆成 `prepareForPublish`/`publishWindow`，见 §3.6。
- `doAsyncReadWrite` 的读路径改用 `ufsReadWindow` + `rootWindowVerifierVerify`：每 4 KiB 先校验后复制，失败只把该请求以 `kIOReturnNotPrivileged` 完成，不调用 `transportFailure`、不复制数据；写路径不变。`bounce` 从 4096 扩到 `kDataMax`，`free()` 对应释放。
- 构建开关：`k60-ufs-verified:scripts/build-pong-ufs-probe-macos.py --verified-root` 传 `-DNATIVE_VERIFIED_BLOCK=1`（默认关）；`k60-ufs-verified:scripts/build-xnu-4k-baseline.sh` 用 `XNU_NATIVE_UFS_VERIFIED_ROOT=1` 传递。启用时内核链接还必须有 `verified_root_policies` 与 `verified_root_key`，由 `UniXNU/build-sheng-source-storage.py` 的 policy bundle 生成。
- 新增 `k60-ufs-verified:tests/RootWindowReadVerified.cpp`：用 mock cache/transport 走 `ufsReadWindow` 的 verify-before-copy 路径，覆盖 full envelope 与 header-only 两条读路径；`k60-ufs-verified:tests/check-verified-root.py` 同时编译运行。
- 宿主测试全过：`RootPublication`、`RootWindowRead`、`VerifiedTableCache`、`RootPolicyTable`、`RootWindowVerifier`、`RootWindowReadVerified`。`native-vroot-cache` 仍关闭，未 boot。
- 2026-11-17 07:00 补测：`k60-ufs-verified:tests/RootWindowVerifier.cpp` 增加 130 块、两页策略表（4,160 B）的 header-only fixture，验证尾页只哈希真实表字节；UFS 提交 `2f60acde`。

## 3.5 步骤 3a 执行记录（2026-11-17 05:20）

- 分支 `feat/ufs-verified-table`，从步骤 2b 的 `d785a91f` 继续。
- `k60-ufs-verified:drivers/NativeUfs/PongUfsTransport.cpp` 的 `pong_ufs_transport_start` 在拼好 `gRootWindows` 后调用 `RootPublication.h` 的 `ufsBuildRootPlan`：SystemOS 第一、OS 最后，Data 等其它窗口在中间；替换原来按 `wanted` 数组 OS→SystemOS→Data 的同步启动顺序。
- 只做发布顺序（3a），不接 `ufsPrepareRootWindows`/`ufsPublishRootWindows`：完整状态机还要把 `PongUfsBlock` 拆成 prepare/start、补 IOMedia 等待与异步客户端保留语义，属于上机验证面；本步不改变窗口内容、不改变 verified-root 默认关闭状态。
- `k60-ufs-verified:tests/RootPublication.cpp` 已覆盖 SystemOS 第一/OS 最后、重复名与缺失必需窗口拒绝；宿主测试仍全过，Mac probe 构建未跑，未 boot。


## 3.6 步骤 3b 执行记录（2026-11-17 07:51）

- 分支 `feat/ufs-verified-table`，从步骤 2b 的 `935f89c0` 继续；提交 `46545497` `feat(ufs): publish verified root windows asynchronously`（`PongUfsTransport.cpp` +215/−2）。
- `PongUfsBlock` 拆成 `prepareForPublish`（bounce/mutex、首块读取与签名、非 Data 的 `configureVerification`、Pong* 属性）与 `publishWindow`（`IOBlockStorageDevice::start`、online、`registerService`、`PongProbeRecord`）；原 `start` 保持 `prepareForPublish && publishWindow`。
- `verifiedVolumeUuid` 从 `verifier.view.volume_uuid` 生成大写 8-4-4-4-12；未 ready 或全零 UUID 返回 false。
- `#if NATIVE_VERIFIED_BLOCK` 下新增 `gPendingBlocks/gPendingAttached/gPendingStarted/gPendingUuid/gPendingCount/gPendingProvider/gPublicationPlan` 与 `PongUfsPublicationOps`：`prepare` 创建/init/attach/prepareForPublish，`validate` 只强校验 OS/SystemOS（Data 跳过，保留 P-152/P-153 的旧属性/祖先路径），`schedule` retain provider 后 `kernel_thread_start`，`start` 调 publishWindow，`wait` 调 `pongUfsWaitForMedia`，`discard` 只释放未 start 对象。各阶段写 `gRootDiagnostic.stage/publicationPhase/publicationWindow`。
- `pongUfsWaitForMedia` 每 100 ms 枚举 `IOMedia`（最多 300 次 = 30 s），OS/SystemOS 用 `UUID` 属性匹配，Data 仅按祖先匹配；每次命中都用 `ufsMediaHasAncestor` 确认祖先链回到本 `PongUfsBlock`，超时前每 5 s 打一条诊断。
- `pongUfsPublishThread` 调 `ufsPublishRootWindows`：Start 失败设 `kIOReturnIOError`、Media 失败设 `kIOReturnTimeout`，已 start 的对象保留；完成后 release provider。
- `pong_ufs_transport_start` 的 verified 路径调 `ufsPrepareRootWindows(publication, gRootWindowCount)`，非 Complete 返回 `transportFailure("root window preparation")`；成功直接返回，异步线程继续发布。`#else` 保留 3a 的同步发布循环。
- 参考实现：`references/ShengUfs/NativeUfs.cpp:2689-2742` 的 `publishThread` 与 `:2960-3040` 的 `Operations`。我们的 `prepareForPublish` 比参考多做首块读取与属性设置（沿用旧 `PongUfsTransport::start` 行为）；Data 不进入强校验的理由见 2026-11-17 07:15 证据：两个参考 policy 集都只有 `OS/`、`SystemOS/`。
- 验证：宿主测试全过（`RootPublication`、`RootWindowRead`、`VerifiedTableCache`、`RootPolicyTable`、`RootWindowVerifier`、`RootWindowReadVerified`，2026-11-17 07:51 复跑）；Mac probe 构建未跑，`NATIVE_VERIFIED_BLOCK` 默认关闭、`native-vroot-cache` 关闭、未 boot。上机验收仍需 `PONG APFS` 三窗顺序与 `K60DATA mounted ro=0` 日志，由 Lead 安排。
- 上机前检查 `build-report.json`：`verified_root` 必须是「compiled with verified_root.c and xnu_crypto.c…」；`verified_root_objects` 必须列出 `verified_root.o` 与 `xnu_crypto.o`，否则 `--verified-root` 没有生效，内核链接会缺 `vr_*` 符号。
- 上机日志判据：`PONG APFS: UUID … bound to … UFS window OS/SystemOS` 与 `K60DATA mounted ro=0` 必须同时出现；三窗顺序按 `UfsRootPlan`（SystemOS 第一、OS 最后）。如果先出现 `PONG_UFS TRANSPORT … stage=root window preparation/root window start/root media wait`，按 fail closed 处理，不得把部分窗口当成成功。
- 2026-11-17 08:16：`RootPublication` 宿主测试补 2 窗与 3 窗的合法顺序断言（`01950044`），六项宿主测试仍全过。
- 2026-11-17 08:36：`RootPublication`、`RootWindowRead`、`VerifiedTableCache` 三项在 `-fsanitize=address,undefined -fno-omit-frame-pointer` 下重编译并运行通过（无 ASan/UBSan 报告）；`VerifiedTableCache` 本轮 concurrent hits=740 misses=860 reads=860 evictions=858 waits=3706。`check-verified-root.py` 的 OpenSSL fixture 也通过 `CC`/`CXX` 包装脚本在 ASan/UBSan 下重跑，policy selection/header-only、per-window verifier、verified window read 三项 PASS。

## 3.7 步骤 2b 构建入口补全（2026-11-17 07:40）

- 复核 `k60-ufs-verified:scripts/build-pong-ufs-probe-macos.py` 发现 `--verified-root` 原先只传
  `-DNATIVE_VERIFIED_BLOCK=1`，没有编译 `k60-ufs-verified:drivers/NativeUfs/verified_root.c` 与
  `k60-ufs-verified:drivers/NativeUfs/xnu_crypto.c`；因此启用开关后 `PongUfsTransport.cpp` 引用的
  `vr_xnu_crypto`、`vr_open`、`vr_verify_block` 没有实现，内核链接会失败（policy bundle 只补
  `verified_root_policies` 与 `verified_root_key`）。
- 修复：启用 `--verified-root` 时按同一 arm64-apple-ios16.0 target、`-std=gnu11`、`-mkernel` 编译
  `verified_root.c` 与 `xnu_crypto.c`，对象加入 `libNativeUfs.a`；`build-report.json` 记录
  `verified_root_objects`，源码摘要包含 `.c`。`k60-ufs-verified:scripts/build-xnu-4k-baseline.sh` 的
  `XNU_NATIVE_UFS_VERIFIED_ROOT=1` 传递路径不变。
- 验证：`python3 -m py_compile scripts/build-pong-ufs-probe-macos.py` 与 `--help` 通过；六项宿主测试全过
  （`RootPublication`、`RootWindowRead`、`VerifiedTableCache`、`RootPolicyTable`、`RootWindowVerifier`、
  `RootWindowReadVerified`）。Mac probe 构建仍需 macOS 工具链，未跑；`NATIVE_VERIFIED_BLOCK` 默认关闭、
  `native-vroot-cache` 关闭、未 boot。

## 4. 不抄的部分

- 参考树 `NativeUfs.cpp`（149,596 B）与我们版本差异过大，不整体替换；只抄 3 个头文件 + 3 个测试。
- `GccUfs.h` 不抄（我们用寄存器常量）。
- 任何需要改 `board.toml`/`dts` 的部分不在本草案内。

## 5. 风险与回退

- 根挂载（P-152/P-153）：任何验证失败必须 fail closed，不能把「表页读失败」当成「块通过」。
- 回退：三步各自独立提交；第 2、3 步的调用点用 `#if` 或运行时开关 `pong_ufs_verified_root=0` 保留原路径。
- 上机判据：`docs/research/wifi` 的 P-215 教训——0 字节日志不能证明「没坏」，必须有 `PONG APFS`/`K60DATA` 行与 SpringBoard。

## 6. 复算命令

```sh
wc -l /e/k60-work/references/ShengUfs/{VerifiedTableCache,RootPublication,RootWindowRead}.h
sha256sum /e/k60-work/references/ShengUfs/{CompletionWait,RootDiagnostics}.h drivers/NativeUfs/{CompletionWait,RootDiagnostics}.h
for f in RootCommands RootLayout RootQueue RootTransportLayout SmmuTakeover TransferPoll; do
  diff -u drivers/NativeUfs/$f.h /e/k60-work/references/ShengUfs/$f.h | head -40
done
```
