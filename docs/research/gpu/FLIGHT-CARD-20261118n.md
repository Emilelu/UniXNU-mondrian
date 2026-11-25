# 上机卡：`gpu-publish-probe-20261118`

## 1. 这次只改一件事

内核 KMD 的 `NativeAdrenoVm::publishMapped()` 每次提交都把**每一个已映射 BO 的整段**清+失效
（`drivers/PongAdreno/submit/NativeAdrenoVm.cpp:331`，`disable_preemption()` 内），耗时只跟映射集合有关、
跟命令数无关。四张图的 `submit` 恒在 10.2–11.5 ms 且完全不随搬运形状变化（纹理 11_478 / 逐行 11_483 /
纹理 10_181 µs），`r(submit,gpu)=0.007` 又排除了「在等 GPU」，所以这条 O(映射字节) 的维护是头号嫌疑。

问题是**没人打印过这段**：`native_adreno_cache_stats[5]` 只写不读，仓库里没有任何地方把它读出来。
所以这一飞只做一件事——让这段自己报数：

- `PONG VM: publish sample n=… objects=… imported=… owned=… combined=… bytes=… us=… calls=… cachebytes=…`
  每 32 次 `publishMapped()` 一行，报**它到底维护了多少字节、花了多少微秒**。
- `PONG SUB: sample n=… buffers=… referenced=… publish=… us`
  每 32 次提交一行，报这次提交**自己引用了多少字节**，以及同一趟维护的耗时。

行为零改动：维护顺序、两个跳过守卫、失败路径全部原样。

## 2. 镜像与前提

- 镜像目录：`/mnt/e/iOS Port/Work/artifacts/gpu-publish-probe-20261118/`
- 构建：`bash scripts/build-strict.sh gpu-publish-probe-20261118 --fd …/gpu-drawfix-20261118-cf4485712c29.fd`
- 插件沿用 `metal-plugin-20261118k`（这一飞不碰 `drivers/PongMetal`，避免第二个变量）
- 串口采集由 `scripts/flash.sh` 负责，证据落 `E:/iOS Port/Work/evidence/usblog-<时间戳>/`

## 3. 前置检查（不满足就不飞）

- **P1** 构建 `EXIT=0`，`verify-boot-image: OK`，`image-arg-audit: OK`，30 个参数 ≤607 B。
- **P2** 内核里**有**这两条格式串：`strings kernel.macho | grep -c "publish sample"` = 1、
  `grep -c "PONG SUB: sample"` = 1。没有就是归档没带上探针，**不要飞**。
  （`libPongAdrenoPlatform.a` 里 `llvm-nm-18 … | grep -c NativeAdrenoSubmit` 应为非零。）
- **P3** 设备 `fastboot devices` 可见。
- **P4** 上位卡 `FLIGHT-CARD-20261118m.md` 的结论仍然是 PASS（纹理路径是基线）。
- **P5** `git status --porcelain` 为空且分支与远端齐平。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

- **S1** 无 `K60KEXC`、无 `panic(`、无 `Debugger called`。
- **S2** 控制台至少 2 行 `PONG VM: publish sample`，且至少 2 行 `PONG SUB: sample`。
- **S3** 这一飞**仍然出帧**：至少一行 `MiniIOMobileFramebuffer: N frames` 且 N>0，且客户端
  `Pong Metal: c<n>/0 d<m>` 的 n>0。零帧一律判**无效**（不是失败），可以原地重飞一次。

### 4.2 路径身份

- **S4** 仍有 `scanout frames=` 且 `imports==frames`（P-234 的单位修复仍在），
  仍有一行 `scanout copy texture untile …`（上一飞的形状没被打回）。

### 4.3 假设是否成立

- **S5** `PONG VM … bytes=` 在一次飞里稳定（相邻样本相对差 ≤10%），说明映射集合是固定工作集，
  而不是每帧新建——这是「O(映射字节)」成立的前提。
- **S6** `PONG VM … us=` 的中位数 **≥ 同一飞 `submit` 中位数的 50 %**（`submit` 由 `scanout` 报告行的
  `submit=<n> us` 取中位数）⇒ 头号嫌疑成立：`publishMapped()` 就是那 10 ms。
- **S7** `PONG SUB … referenced=` 与 `PONG VM … bytes=` 同量级（0.5×–2×）⇒ 引用集本身就有 18–37 MB，
  说明**即使只维护被引用的 BO 也省不下**，必须换路线（见 F6 的处理）。
- **S8** 帧率不低于上一飞的 7.28 fps（这一飞不该变慢超过 10 %；探针本身每 32 次一行可以忽略）。

## 5. 结果登记

**飞了**：`usblog-20261118-201603`（312,098 B / 4,095 行，`capture.json complete=true`，
`panicMarker null`、`resetMarker null`，20:16:06→20:20:27）。
镜像 `gpu-publish-probe-20261118`，`boot.img 5325a62e…`，内核 `1d103c5d…`。

### 5.1 判据结果

| 判据 | 结果 | 实测 |
| --- | --- | --- |
| S1 无 panic / 异常 | PASS | `K60KEXC` 0，panic 0 |
| S2 探针行存在 | PASS | `PONG VM` 84 行、`PONG SUB` 84 行、`scanout` 119 行 |
| S3 仍然出帧 | PASS | `MiniIOMobileFramebuffer` 最多 90 帧，客户端 `c754` |
| S4 纹理路径 + `imports==frames` | PASS | 形状行 `texture untile`，4 行；`imports` 与 `frames` 逐行相等 |
| S5 映射字节稳定 ≤10 % | **FAIL** | 370,245,632 → 762,343,424 B，漂移 105.9 % |
| S6 `publishMapped` ≥50 % 的 `submit` | **PASS** | publish 中位 10,107.5 µs，`submit` 中位 12,274 µs ⇒ **82.3 %** |
| S7 `referenced` 与 `bytes` 同量级 | **FAIL** | `referenced` 中位 20,114 B，`referenced/mapped = 0.00` |
| S8 帧率 ≥7.28 fps | PASS | 与上一飞同量级 |
| 命中的失败规则 | **F6（按字面条件）** | `imported=39 > 0` 且 `bytes=690,958,336 > 36 MB` |

**结论：S6 成立 —— 被测延迟位于 `publishMapped()` 这一段。但这不能单独说明根因。**
S5、S7 失败；F6 的字面条件命中，但不能据此直接改 cache policy 或缩小维护集合，详见 5.2。

### 5.2 计数器的测量窗口与证据边界

```
PONG VM: publish sample n=2688 objects=613 imported=39 owned=0 combined=574 \
         bytes=690958336 us=10107 calls=565 cachebytes=139517952
```

- `n=2688` 是此 `NativeAdrenoVm` 的静态采样序号；该行的 `objects=613` 和 `bytes=690,958,336`
  是该次抽样遍历中通过两个 skip guard 的映射数及其总长度，并非实际执行 cache maintenance 的对象/字节数。
- `calls=565`、`cachebytes=139,517,952` 是 `publishMapped()` 循环前后读取全局
  `native_adreno_cache_stats[3]` / `[1]` 的差值。它们是在单次被抽样调用前后读取的，不是前 32 次或开机累计；
  全局计数也可能混入并发维护。`cachebytes` 记成功维护函数的请求字节数；物理页批处理会把不在内核 DRAM
  范围内、实际跳过的设备页仍计入请求字节，所以它不等于实际执行 cache-line 操作的字节。
- 对 84 个 VM 样本的独立复核：`calls` 最小/中位/最大为 390/610/693；`cachebytes` 请求量最小/中位/最大为
  93.3/135.3/137.6 MiB。单个 `n=2688` 样本是 565 次 batch、139,517,952 B（133.1 MiB）。
  这些数据与先前把该计数器误作累计而算出的「52 KB/提交」相矛盾；后者已撤回。
- 耗时确实落在该函数段：VM `us` 中位数 10,107.5 µs，配对 SUB `publish` 中位数 10,152 µs。
  但同一对象/映射/请求维护量的样本 `us` 可从 3,047 到 10,341 µs，且 counters 是全局计数，
  因此不能据此判定成本按对象数还是按实际 cache-line 工作量变化。
- S7 的 `referenced` 是 command processor 的 indirect-buffer 字节数，不是 GPU 命令间接访问的全部 texture、
  render-target 等资源。`referenced/mapped` 很小只能证明两种计量范围不同，不能证明只维护 `buffers[]`
  足以保持所有资源同步。

**F6 状态**：按本卡原有字面条件（`imported>0` 且映射总 `bytes>36 MB`）命中；但其「改变导入页 cache policy」
建议尚未由本探针证明正确或有效。保持现有行为，不做按 `buffers[]` 限缩、去掉维护或 cache-policy 变更。
下一步须把单次映射遍历的 per-class 耗时、实际维护/跳过的物理页数、引用资源完整性分别测出来，
并确认计数器归属与并发边界，再制定独立判据。

### 5.3 下一飞（单变量）

先实现只读诊断：在 `publishMapped()` 内区分 imported/write-combined/owned 的映射数、遍历耗时、
请求维护耗时与实际处理/跳过的页数；确认串行化或改用调用本地计数，避免全局计数被并发污染。
不改变 cache maintenance 的范围、属性或顺序。下一张上机卡必须把计量语义、有效性条件和失败处置写在构建前；
只有新证据能区分对象遍历、cache 操作与并发干扰后，才讨论功能修复。

### 5.4 追加读数：耗时是双峰的，不是常数

把 84 个 VM 样本按 `us` 排序，得到清晰的**两簇**（`E:/iOS Port/Work/scratch/bimodal_publish.py`）：

| 簇 | 样本数 | `us` 中位 | 范围 | objects 中位 | imported 中位 | calls 中位 | cachebytes 中位 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 低 | 22 | **3,142** | 1,396–3,582 | 601 | 86 | 598 | 134.9 MiB |
| 高 | 62 | **10,328** | 6,694–11,886 | 631 | 81 | 610 | 135.4 MiB |

两簇的输入量几乎相同（objects 601 vs 631、imported 86 vs 81、calls 598 vs 610、cachebytes 134.9 vs
135.4 MiB），耗时却差 3.3 倍；而且**序列是交错的**（`HLHHHHHLHHHLHLHH…`），不是预热、
不是"前 N 次慢"。高簇内部还分得出 ≈6.7–7.1 ms 与 ≈10.1–10.5 ms 两级。

⇒ 「每次提交固定 10 ms」的说法不成立，应改为**状态相关**：同一段代码在两种状态下相差 3.3 倍。
这与 P-237 的结论互相独立：即便计数窗口读对了，也不能用对象数或请求字节数解释耗时。
候选状态是 CPU/GPU 频率档位、被抢占、或某一类页在两簇里是否真的被维护——探针还没测这些，
所以**这一条只是界定了问题，不是结论**。下一飞必须让探针同时报"实际处理/跳过的页数"与
"本段是否发生抢占/等待"，才能把 3.1 ms 与 10.3 ms 分开。

失败规则（命中即按此处理，不再即兴发挥）：

- **F1** 命中 S1 的反面（panic / 异常）⇒ 探针引入回归，回滚 `1e691b6d`，不解释、不重飞。
- **F2** 没有 `PONG VM` 行 ⇒ 探针没进内核（先查 P2 的产物再决定），**不要**因为「没数据」去改判据。
- **F3** 零帧 ⇒ 判无效（P-236），重飞一次；两次都零帧再查 boot 侧。
- **F4** `PONG VM us` **< 20 %** 的 `submit` ⇒ 假设不成立，`publishMapped()` 不是那 10 ms；下一个嫌疑按顺序是
  `reassertWriteCombined`（`NativeAdrenoSubmit.cpp:130`，自述约 0.65 ms）、ring 整段 cache publish
  （`NativeAdrenoRing.cpp:245`）、写合并审计（`SubmitAuditBytes=256 KiB`），届时先给它们各加一条同样的探针，
  仍然一次只测一个。
- **F5** `objects` >16 但 `bytes` 很小 ⇒ 成本是**每次调用的固定开销**而非字节数，改法不同（合并调用）。
- **F6** `imported` >0 且 `bytes` > 36 MB ⇒ 维护覆盖的不止两块 18.4 MB 表面；此时 S7 若同时成立，
  说明「只维护被引用 BO」省不下，正解是让 GPU 写的那批导入页对 CPU 不可缓存（`write_combined_` 路径
  `NativeAdrenoMemory.cpp:296`）或去掉每提交的整段维护，且必须写清正确性论证。
- **F7** 出现 `GPU copy not retired`、`K60SCANOUT` 毒化或帧内容花掉 ⇒ 立即停止这条线，先修正确性。
