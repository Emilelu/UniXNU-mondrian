# 飞行卡 2026-11-19 · `gpu-consolidated-20261119`

第一张把**已上机证明的四条线**（面板 120 Hz 切档、12-bit 背光、电池 sample-dirty、wifi tip）
与 GPU 实验放在同一个镜像里的飞行。在此之前每一张 GPU 镜像都跑在 60 Hz 面板上，
帧率数字里同时混着「渲染慢」和「面板只给 60 Hz 拍」两个原因（P-236 同族：先把环境定死再量）。

镜像目录：`gpu-consolidated-20261119`

## 1. 这张镜像里有什么

| 来源 | 内容 | 先前证据 |
| --- | --- | --- |
| `feat/120hz-panel` | `K60Backlight.cpp`、`K60BacklightCodec.h`、`PongDsiPanel` 的 11 包切档、`patches/display/0620` | `120hz-7` PASS：11 包 rc 0、`te` 55→120/s、SpringBoard 172、backlight `conformance=1 control=1` |
| `fix/battery-sample-dirty-build` | 电池采样脏位修复 + ADSP owner/rail/glink 栈 | `5beaffb2` 合并前的分支证据 |
| `test/wifi-he-scan` | wifi 线尖端（仅代码与文档，状态仍 `parked`） | wifid 能开 80211 user client |
| `feat/gpu-metal-hw` | 逐阶段计时、纹理 untile 路径、gmem 渲染模式、`publishMapped` 探针 | cards k/m/n/o |

切档与背光**改为默认开启**（`p120=0` / `vsync=120` / `k60_backlight_control=0` 是退出开关），
因为 arm64 命令行只有 607 B 而上限已用到 596 B，装不下 `p120=1`(7 B) 与
`k60_backlight_control=1`(24 B) 两者。

## 2. 前置条件（不满足就不要飞）

- **P1** 构建走 `scripts/build-strict.sh`，`eight-step` 通过、`image-arg-audit: OK`、
  `verify-boot-image: OK`、`kernel archives` 四项齐全。
- **P2** 内核里能找到探针串：`publish sample`、`wskipped=`、`PONG WC: distrust latched`、
  `imports=%llu import=`。缺任何一条说明镜像不是这棵树编的。
- **P3** 内核里能找到面板与背光串：`K60 PANEL: INTF1` 与 `conformance=`。
- **P4** 插件 bundle 的 `PongAdrenoMetal` 含 `gmem,nocb`（`strings … | grep -E '^(gmem,nocb)$'`）。
- **P5** `K60_AGENT_ID` 已设置（boot claim 要署名）。
- **P6** 设备在 fastboot；只 `fastboot boot`。

## 3. 这次要回答的问题

1. 面板在**合并后**还会不会切到 120 Hz？合并不是文本拼接，切档调用点在
   `PongAdrenoScanout.cpp` 的首帧路径上，任何一次冲突取舍都可能把它摘掉。
2. 背光在合并后还是两端可调吗（`conformance=1 control=1`）？
3. 120 Hz 面板 + GPU 路径同时在场时，帧间隔分布是什么形状？此前 12.45 fps、
   帧间隔中位 28.9 ms 是在 60 Hz 面板上量的，不能直接拿来当基线。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

零帧的一飞**判无效**，不算任何 F 规则命中。有效要求：
`MiniIOMobileFramebuffer: <n> frames` 有 n>0、`Pong Metal: c<n>/0` 有 n>0、至少一条 `scanout frames=`。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`。
- **S2** 面板切档：至少一条 `K60 PANEL: INTF1 after the UI frame te 120/s`。
- **S3** 背光：至少一条 `conformance=1 control=1 stats=`。
- **S4** GPU 仍出帧：至少一条 `scanout frames=`，且客户端 `Pong Metal: c<n>/0 d<m>` 的 n>0。
- **S5** `imports` 等于 `frames`（每一行都成立），证明扫出仍是一帧一导入。
- **S6** 帧间隔中位 < 40 ms（比上一轮 60 Hz 面板下的 28.9 ms 更差即算回归——
  120 Hz 拍只会让等待变短，变长说明合并引入了新开销）。
- **S7** 存储与电池不回归：`K60DATA` 挂载成功、无 `transportFailure`、
  无 `PONG_UFS: no Apps SMMU lease` 之外的 UFS 失败行。

### 4.3 失败规则

- **F1** 出现 panic／`K60KEXC`／`crashed: backboardd` ⇒ 回滚合并，先修再谈 GPU。
- **F2** 没有 `K60 PANEL: INTF1` 任何一行 ⇒ 面板代码没进镜像，合并丢了文件。
- **F3** 只有 `te 55/s` 而没有 `after the switch` / `after the UI frame` 行 ⇒
  切档调用点在合并里失效，按 `PongAdrenoScanout.cpp` 的首帧路径逐个对照。
- **F4** 有 `conformance=` 但不是 `conformance=1 control=1` ⇒ 背光回归，停飞。
- **F5** 有效性不成立 ⇒ 判无效，重飞同一张镜像一次；连续两次无效再查镜像。
- **F6** `imports` 不等于 `frames` ⇒ 扫出路径回归，先查 `PongAdrenoScanout.cpp:195-196` 的释放顺序。

## 5. 结果登记

**镜像** `gpu-consolidated-20261119`
`boot.img sha256 ea157138d76f20af79b4eda43b20aa110d71690ff282fd5906dfd74f6a538ce9`
kernel `f835582494c3cbc0a1ccbe5d7661c7d1b653663a3b33f3ba6e45f9853d80c4f6`（105,676,800 B）
payload kernel `488b2decd6f2d1efd219c5ac68bc4f12928c87376cc86221d4929d60df64caba`
payload adt `9a28970faf3c72ed71f61fc1e1ef9d9b1806a0bdd9cae7681312da1b1a69a720`
series 228 / 30 args / 596 B / metal plugin `metal-plugin-20261118l`

**证据** `usblog-20261119-025400`（240,846 B / 3,423 行，`capture.json complete=true`，
`logSha256 A33E140DABDD695702D9FEA6BFFA0B1E9B3D37F11C7C197F37BCA11504AEA3E3`，supervisor rc=0）

### 5.1 判据

| 判据 | 结果 | 实测 |
| --- | --- | --- |
| S1 无 panic / K60KEXC / backboardd 崩 | ✅ | `panic(` 0、`K60KEXC` 0、`crashed: backboardd` 0 |
| S2 面板 te 120/s（after the UI frame） | ✅ | `before the switch te 60/s` → `after the switch te 122/s` → `after the UI frame te 120/s`（period 7529 µs） |
| S3 backlight conformance=1 control=1 | ✅ | `conformance=1 control=1 stats=4,0,2047,2047 req=0,0,1,1` |
| S4 GPU 仍出帧 | ✅ | `scanout frames=` 5 行、`MiniIOMobileFramebuffer` 最大 5 帧、`Pong Metal: c7/0 d7` |
| S5 imports==frames | ✅ | 5/5 行成立 |
| S6 帧间隔中位 < 40 ms | ⚠️ 未测到 | 见 5.3：屏幕静止，5 帧/202 s 是「没有工作」不是「工作慢」 |
| S7 K60DATA 挂载、无 transportFailure | ✅ | `K60DATA` 12 次、`transportFailure` 0、`Early boot complete` 1、SpringBoard 135 行 |

失败规则：**无命中**（F1–F6 均未触发）。

### 5.2 这次真正回答的问题

1. **合并没丢切档调用点。** 这是本卡片存在的首要理由。`K60 PANEL: INTF1 before the
   switch te 60/s` → `after the UI frame te 120/s`，说明首帧路径上的切档在合并后的树里
   仍然执行，11 包序列仍然被接受（无 DCS failure）。
2. **背光没回归。** `conformance=1 control=1`，与 `brightness-19` 的判据一致。
3. **GPU 扫出没回归。** `imports == frames` 逐行成立，纹理 untile 形状仍是 `texture untile
   source=5888 scanout=5760 rows=3200`。

### 5.3 S6 为什么判「未测到」而不是「失败」

五个 stage 样本的时间戳是 88 s、90 s、142 s、202 s —— 屏幕上的内容没有变化，合成器
不需要重绘。此时量「帧间隔」量到的是**空闲**，把它记成性能回归会让下一步优化一个
不存在的问题。这与 P-236 是同一类错误：判据必须能在它声称的条件下失败。

本卡的 S6 需要前置条件：**必须先有持续动画**。可行的驱动方式（按可实现性排序）：
从宿主侧注入 HID 触摸事件（USB 控制台已通）、或让 SpringBoard 播放一段已知动画、
或用 `k60_uilib` 已有的诊断口触发一次连续重绘。没有驱动之前，S6 应当写为
「在 N 秒窗口内帧数 ≥ M 且帧间隔中位 < 40 ms」，而 M 由驱动方式决定。

### 5.4 阶段中位数（n=5，仅供参考，样本太少）

`import` 55 µs、`encode` 19,396 µs、`submit` 8,420 µs、`gpu` 7,283 µs、`sum` 30,248 µs。
首帧的 `encode` 明显偏高（28,866 µs），末帧只有 593 µs —— 纹理 untile 的一次性成本
分摊在前几帧上，这与「每帧都重建线性纹理」的预期一致，但 5 个样本不足以定论。

### 5.5 结论与下一步

结论：**合并后的镜像在 120 Hz 面板上稳定运行，显示与背光无回归，GPU 路径无回归。**
帧率尚未在「有负载」的条件下测量过。

下一步，按此顺序：
1. 给 S6 加动画驱动，重测 120 Hz 下的真实帧节拍（这是所有后续优化的基线）。
2. `present()` 的阶段数在 120 Hz 下要重新取样（`submit` 与 `gpu` 各占一半）。
3. 三个 capability selector 的拒绝（`supportsConditionalLoadStore` /
   `supportsComputeCompressedTextureWrite` / `isLargeMRTSupported`）在同一次飞行里
   仍然出现，位于 `SpringBoard[26:1200]`，说明它们确实由 SpringBoard 在问。
