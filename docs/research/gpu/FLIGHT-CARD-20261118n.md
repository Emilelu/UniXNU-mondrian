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

- 镜像目录：`/mnt/e/k60-work/artifacts/gpu-publish-probe-20261118/`
- 构建：`bash scripts/build-strict.sh gpu-publish-probe-20261118 --fd …/gpu-drawfix-20261118-cf4485712c29.fd`
- 插件沿用 `metal-plugin-20261118k`（这一飞不碰 `drivers/PongMetal`，避免第二个变量）
- 串口采集由 `scripts/flash.sh` 负责，证据落 `E:/k60-work/evidence/usblog-<时间戳>/`

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

（上机后填写。）

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
