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

criteria-sha256: cea68767764f65ee4b6b795d7492690866934f67f571787f09096a0fcb8576d9

### 5.1 飞行事实

| 项 | 值 |
| --- | --- |
| 镜像 | `gpu-coherent-20261119` |
| boot.img | `58eb6724fcd67e8e8f593cb166be36671abfd7f8962e976ee200dd4e1b539a62` |
| 内核 | `0346eb3327597518ae9d157ee6ae347715f80e31f5ad175e7f4763121d33a5f3`（105,676,800 B） |
| payload 内核 | `f2cc116baab0c4ba1a1e33f154f36887d0d3a42cb83bb70a0999e355e23be0b2` |
| series | 228 `frozen=8bf21dcc01c9d52e6ec2dcdc1186069a58de69c23c9e38bfec60e92a1c51d6eb` |
| 参数 | 30 条 / 596 B（`pong_gpu_coherent` 不在命令行上，默认值 2 就是探针） |
| 证据 | `usblog-20261119-041606`，183,472 B，`capture.json complete=true`，supervisor rc=0 |
| 时间 | 2026-11-19 04:16:06 → 04:20 左右 |
| 事故 | 无：`panic(` 0、`K60KEXC` 0、`crashed: backboardd` 0 |

### 5.2 判据

| # | 判据 | 结果 |
| --- | --- | --- |
| 有效性 | 合成器报帧 / 客户端 commit / `scanout frames=` | ❌ **三者皆 0** ⇒ 本次飞行**无效**（P-236） |
| S1 | 无 panic、无 K60KEXC、无 backboardd 崩溃 | ✅ |
| S2 | 恰一条 `PONG ADRENO: IO coherence` 行 | ✅ **1 条，且结论是 on** |
| S3 | `coherent=1` 且 `skipped` 单调增长 | ⚠️ `coherent=1` 成立；但整场只有 **1 次**提交，`skipped=0` ⇒ 没有可增长的样本 |
| S4 | `publish` 中位 < 2,000 µs | ⚠️ 唯一一条样本 `us=25`（10 个对象、292 KB，全是 writeCombined 且被跳过）—— 这不是帧路径的样本 |
| S5 | `submit` 中位 < 4,500 µs | ⚠️ 无样本 |
| S6 | 仍出帧且 `imports==frames` | ❌ 没出帧 |
| S7 | 无 poison | ✅ |

**判定：INVALID（不是判据失败，是没有数据）。** 按 P-236，这一飞只能回答「探针跑没跑、说了什么」，不能回答「省了多少」。

### 5.3 这一飞真正的收获：K60 的 GPU 是 IO-coherent，第一次就证明成功

探针原始行（`console.log:681`）：

```
PONG ADRENO: IO coherence on (pong_gpu_coherent=2, probe d64/64 a1 r1024/0 w1024/1024 s0 k6)
```

按 `d%u/64 a%u r%u/%u w%u/%u s%x k%u` 逐字段读：

| 字段 | 值 | 含义 |
| --- | --- | --- |
| `d` | 64/64 | CPU 写脏的 64 条 cache line 全部仍在 cache 里（前提成立：数据确实没落到 DRAM） |
| `a` | 1 | 第一次尝试就通过，没有用上「最多 8 次」的重试 |
| `r` | 1024/0 | GPU 经 SMMU 读到的 1024 个字全对，而**按物理地址直接读 DRAM 得到 0 个** ⇒ GPU 的读穿过了 CPU 脏着的那层 cache |
| `w` | 1024/1024 | GPU 写回的 1024 个字，CPU 侧 1024 个都看得见 |
| `s` | 0 | CP 状态干净 |
| `k` | 6 | 停在第 6 阶段 = 全过（`pass` 要求 `k[0]==6 && k[1]>=48 && k[2]==1024 && k[4]==1024 && k[5]==1024`） |

两个方向都成立，所以 `native_adreno_io_coherent=1`，`NativeAdrenoVm::publishMapped()` 与
`acquireImported()` 的跳过判据**第一次真正生效**（而不是继续当死代码）。

这条结论的价值与 zizhan 的注释对得上：他那边的 g40/g41 强制开后扫出从 24–35 ms 降到 5–6 ms。
我们不必再猜「A730 是不是 ADRENO_QUIRK_HAS_CACHED_COHERENT behind a dma-coherent SMMU」——
本机实测是。**这是「抄 zizhan」里唯一带对方量化收益、且我们一次就验证通过的一项。**

### 5.4 为什么这一飞没有帧（不许当成 coherence 的副作用）

- 客户端停在 `Pong Metal: c0/0 d0 p14 x4 R6 D0 F0 M18 C0 B2 K60CB first command buffer requested`
  —— **建了命令缓冲但从未 commit**；`SpringBoard` 只有 3 行（上一张好镜像 135 行），
  `Early boot complete` 1、`K60DATA mounted` 1、`launchd` 77 行 ⇒ 系统起来了，界面没走到。
- 整场唯一的 `publishMapped()` 样本是 `objects=10 imported=0 bytes=299008 us=25`，
  即 CP 初始化那几次内部提交，**帧路径一次都没进**。
- 因此 coherence 的跳过分支在这次飞行里根本没有机会被执行（没有导入帧被维护），
  它不可能是「没出帧」的原因：改了开关却没走到那条路。
- 同形状的空飞以前出现过：`usblog-20261118-185517` 也是 `c0/0 d0`、零帧，
  同一张镜像 9 分钟后重飞就出了 359 帧 ⇒ **boot 侧抖动**，不是镜像回归。

### 5.5 下一步

1. **重飞同一张镜像**（`boot.img 58eb6724…`，判据不变），直到有效性成立再读 S4/S5。
   这是 P-236 的正确处置：无效不是失败，重飞不是放宽判据。
2. 若重飞后 `publish` 落到 <2,000 µs 且 `skipped` 随帧数增长 ⇒ coherence 成为默认，
   下一刀转向 `gpu`（7.3–12.8 ms）与 `encode`。
3. 若探针在重飞里又报 off（不该发生，但必须留退路）⇒ 读 `d/a/r/w/s/k` 判断是哪个方向没过，
   **不得**用 `pong_gpu_coherent=1` 强行绕过证明。
4. 顺带登记 P-240：「一个从未被赋值的开关让三处跳过判据全部成了死代码」。
