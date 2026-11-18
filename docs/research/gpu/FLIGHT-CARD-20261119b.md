# 飞行卡 b：证明 GPU SMMU 的 IO coherence，让每次提交不再清 93 MiB 导入帧

- 镜像 tag：`gpu-coherent-20261119`
- 卡片写于镜像之前（`check-flight-card.py` 要求 `card_mtime <= image_mtime`）
- 分支：`feat/gpu-metal-hw`
- 上机者：任一 agent（先到先得，机器级 boot claim 单写者）；本卡由 lead 执行

## 1. 为什么飞这一张

从 `gpu-consolidated-20261119`（`usblog-20261119-025400`）和之前三飞的实测，帧成本已经分解清楚：

| 阶段 | 中位（µs） | 证据 |
|---|---|---|
| `import` | 55 | 每帧一次 `newBufferWithBytesNoCopy`，已无缓存 |
| `encode` | 19,396 | 逐行/纹理拷贝命令的编码 |
| `submit` | 8,420 | `[MTLCommandBuffer commit]` |
| `gpu` | 7,283 | `waitUntilCompleted` |
| `sum` | 30,248 | 四段之和 |

而 `usblog-20261118-233946` 的 per-class probe 把 `submit` 拆开：`publish` 中位 **6,635 µs**，`ibytes` 中位 **97,742,848 B（93.2 MiB）**、`ibytes/cachebytes = 1.00`、`trusted` 恒 1、`wbytes` 恒 0。

结论：那 6.6 ms 是**导入帧的 clean+invalidate**，不是 write-combined、不是 owned 页。

关键事实（本轮读 zizhan 得到）：`NativeAdrenoVm::publishMapped()`、`acquireImported()`、`NativeAdrenoUserClient.cpp:268` 三处**都已有**跳过判据

```cpp
if (coherentMapping(m.writeback) || importedUntouched(m.memory)) { ...skips...; continue; }
```

而它们都要求 `native_adreno_io_coherent` 非零。**本仓库从来没有给这个变量赋过值**（`NativeAdrenoVm.cpp:20` 与 `NativeAdrenoUserClient.cpp:20` 都只是声明），所以三处跳过都是死代码。

`E:/hackios/UniXNU-zizhan/drivers/PongAdreno/PongAdrenoNativeGlue.cpp:64-72` 的注释记录了同一个病的实测修法：

> Only both proofs set native_adreno_io_coherent; imported IOSurfaces are then no longer cleaned and invalidated around every submission. **g40/g41 (forced on): the scanout blit went from 24-35 ms to 5-6 ms a frame.**

我们的 23–25 ms 正在那个区间里。

## 2. 改了什么

1. `drivers/PongAdreno/PongAdrenoNativeGlue.cpp`：移植 zizhan 的 `dramPage()` / `cpFence()` / `gpuCopyPage()` / `coherenceProbe()`，并在 `native_adreno_publish()` **之前**按 boot-arg 赋值：

   - `pong_gpu_coherent=2`（默认）⇒ 跑探针，**两个方向都过**才置 1；
   - `pong_gpu_coherent=1` ⇒ 强制开（不证明）；
   - `pong_gpu_coherent=0` ⇒ 关（现行行为）。

   探针不读 DTS、不参考 A740，而是**写和读真实页**：读方向要求 CPU 新写的值在 GPU 拷贝后仍在 DRAM（只有 CPU cache 有），写方向要求 GPU 写的值能被普通 cached load 读到；脏行数不足时最多重试 8 次（sheng int-150 见过一次被写回后就"无 coherence 也能过"的假阳性）。

2. `drivers/PongAdreno/submit/NativeAdrenoVm.cpp`：`PONG VM: publish sample` 行尾新增 `coherent=%u skipped=%llu`（`native_adreno_coherent_skips[2]`，即 `publishMapped()` 的跳过累计）。**没有这个字段，一次变快无法区分是跳过生效还是别的因素。**

3. `scripts/tests/test-gpu-coherence-probe.py`（新，20 项）：探针存在、默认值必须是 2、失败必须留 0、赋值必须在 `native_adreno_publish()` 之前、两个方向都真的被判据约束、三处跳过判据仍在、采样行两个字段都在、跳过计数取的是 `publishMapped` 槽位（槽 3 是 `acquireImported`，会读错成本）。

## 3. 前置条件（不满足就不飞）

- [ ] `bash scripts/build-strict.sh gpu-coherent-20261119 --fd …` 全绿，`image-arg-audit: OK`
- [ ] kernel.macho 里 `strings` 能查到 `PONG ADRENO: IO coherence %s (pong_gpu_coherent=%u, probe %s)` 与 `coherent=%u skipped=%llu`
- [ ] `python3 scripts/tests/test-gpu-coherence-probe.py` → `TESTS OK`
- [ ] `K60_AGENT_ID` 已设置（supervisor 署名，rc=7 拒绝空署名）
- [ ] 设备在 fastboot

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

零帧的一飞**不算判据失败**，判无效：

- `MiniIOMobileFramebuffer: N frames` 的 N > 0；
- `Pong Metal: c<n>/0` 的 n > 0；
- 至少一行 `PONG VM: publish sample`。

三者任一为 0 ⇒ 本次飞行判**无效**，不据此下任何 coherence 结论，直接重飞。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`（coherence 判断错会静默毁帧，也可能直接崩）。
- **S2** 出现且只出现一条 `PONG ADRENO: IO coherence on (pong_gpu_coherent=2, probe …)` 或 `off`。`off` 本身不是失败（那是探针如实的否定），但**必须据此判 F2**。
- **S3** `on` 时 `PONG VM: publish sample` 行尾 `coherent=1`，且 `skipped` 随样本**单调增长**（说明跳过路径真的在跑）。
- **S4** `publish` 中位（`us=` 字段）从 6,635 µs 降到 **< 2,000 µs**（跳过 93 MiB 导入帧的直接后果）。
- **S5** `submit` 中位从 8,420 µs 降到 **< 4,500 µs**。
- **S6** 帧仍然上屏：`scanout frames=` 行数 ≥ 2，`imports==frames`。
- **S7** 画面无可见破损（用户/截图确认），且 `GPU copy not retired` 0 次、`poisoned` 0 次。

### 4.3 失败规则

- **F1** `panic(` / `K60KEXC` / `crashed: backboardd` ⇒ coherence 判错，**立即把默认值改回 0**（`native_adreno_io_coherent` 恒 0），并在 PITFALLS 记一条。
- **F2** `IO coherence off` ⇒ 探针如实否定，**不得**强行 `pong_gpu_coherent=1` 再飞一次来"验证"；改为记录 probe 行（`d/a/r/w/s/k` 六字段）并分析是哪一方向没过（`k` 是停在哪个阶段）。
- **F3** `coherent=1` 但 `skipped` 不增长 ⇒ 跳过判据没进循环（`writeback` 位或 `imported()` 为假），不是 coherence 的问题，先修判据。
- **F4** `publish` 没降 ⇒ 那 6.6 ms 不是导入帧维护，**前面的 per-class 归因要重做**，不要继续改 coherence。
- **F5** 出现可见破损但无崩溃 ⇒ 缓存不一致已经发生，立刻回退默认值并保留日志。
- **F6** 有效性不成立（4.1）⇒ 判无效，重飞。

## 5. 结果登记

（飞行后由 judge 写入）
