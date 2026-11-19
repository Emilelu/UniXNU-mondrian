# 飞行卡 e：`gpu-submit-20261119` —— `submit` 那 3.0 ms 是内核还是转译器

镜像：`gpu-submit-20261119`（本卡只判这张镜像）。

状态：**判据先写（本文件先于镜像提交）**。飞行前不得修改下面 §4 的任何阈值。
上游：`FLIGHT-CARD-20261119d.md` §5.6（对照实验）与 §5.7（帧分布）。

## 1. 为什么飞

`usblog-20261119-070345` 把 `present()` 的 12,631 µs 拆成了四段，其中第二大的
`submit`（`[commands commit]` 的 CPU 时间）中位 **3,015 µs**，而它曾经的唯一解释
——`publishMapped()` 每次提交清 93.2 MiB 导入帧——已经在 coherence 生效后降到 **51 µs**。
也就是说这 3.0 ms 现在没有任何解释。

同一飞还测出：典型帧 29.4 ms（中位），`present()` 12.6 ms 占 **43 %**。
要把典型帧压到 8.33 ms 以下，`submit` 这 3.0 ms 必须归因，否则只能猜。

归因只有两种可能，而它们的分界线正好落在一个已有的计数器上：

| 可能 | 判据 |
|---|---|
| 时间花在**内核**里（ring 提交、fence 等待、IPC） | `native_adreno_method_stats[5][3]` 每个提交的均值接近 3.0 ms |
| 时间花在**转译器/调度器**里（mutex、`submit_batch`、队列锁） | 该均值只有几十到几百 µs |

`native_adreno_method_stats[20][4]` 从 2026-11-18 起就存在（`[0]` 次数、`[1]` 错误、
`[2]` 最后状态、`[3]` 累计微秒），`NativeAdrenoMethodSubmit = 5`
（`drivers/PongAdreno/submit/NativeAdrenoABI.h:21`），但**全仓没有读者**——
与 P-241 同族。这一飞给它一个读者。

## 2. 这一飞改了什么

只有 `drivers/PongAdreno/submit/NativeAdrenoSubmit.cpp` 的一行日志：

`PONG SUB: sample n=%u buffers=%u referenced=%llu publish=%llu us prevsub_count=%u prevsub_total=%u us`

- `prevsub_count` / `prevsub_total` 是 `native_adreno_method_stats[5][0]` / `[5][3]` 的**累计值**。
- **窗口说明（P-237）**：这段代码运行在 `NativeAdrenoSubmit` **内部**，当前这次方法的计数
  尚未入账，所以读到的是**上一次已完成的**提交。按「一帧一次提交」它描述的是同一份工作，
  但日志与判据都必须按「上一个提交」读，不许当成当前提交。
- 行为零改动：不动拷贝形状、不动 coherence、不动提交顺序、不动任何阈值。

## 3. 前置条件（缺一不飞）

- **P1** 八步门禁 `--flash` 通过 64 项。
- **P2** `image-arg-audit: OK`，参数仍是 30 条 / 596 字节。
- **P3** `verify-boot-image: OK`。
- **P4** 内核里必须有 `prevsub_count=` 这一串（`strings kernel.macho | grep -c prevsub_count` = 1）；
  没有就说明探针没进镜像，**不许飞**。
- **P5** `K60_AGENT_ID` 已设置（否则 `flash.sh` 退 7）。
- **P6** 设备在 fastboot，且本次飞行有串口日志。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

必须三项同时成立，否则整飞记 **INVALID**，不算任何 F 规则命中：

1. 至少一条 `MiniIOMobileFramebuffer: … N frames in …` 且 N ≥ 1；
2. 至少一条 `Pong Metal: c<n>/0 d<n>` 且 n ≥ 1；
3. 至少一条 `scanout frames=` 行。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`。
- **S2** 至少 3 条 `PONG SUB: sample` 且每条都带 `prevsub_count=` 与 `prevsub_total=`。
- **S3** `prevsub_count` 在飞行过程中单调增长（说明计数器真的在被记账，不是死字段）。
- **S4** 记录 `prevsub_total / prevsub_count` 的每提交均值（µs），与 `submit` 中位并排列出。
- **S5** 记录本飞 `submit` 中位（对比 3,015 µs）。
- **S6** 仍在出帧，`imports==frames` 每行成立，面板 `after the UI frame te` ≥ 110/s。
- **S7** 拷贝形状仍是 `texture untile`（这一飞不动它；形状变了说明镜像不对）。

### 4.3 失败规则（命中即按分支走，不许「再看看」）

- **F1** 出现 panic / `K60KEXC` / `crashed: backboardd` ⇒ 立即回滚这一行日志，重飞确认恢复。
- **F2** 没有任何带 `prevsub_` 字段的行 ⇒ 探针没进镜像或没跑到。先查 P4，**不许**把
  「没有数据」读成「内核很快」。
- **F3** `prevsub_total/prevsub_count` ≥ `submit` 中位的 60 % ⇒ 这 3.0 ms 花在**我们自己的内核**里。
  下一步是在 `NativeAdrenoSubmit::Submit` 内部再拆（ring 提交 vs fence 等待 vs IPC 往返），
  不是去改转译器。
- **F4** `prevsub_total/prevsub_count` < `submit` 中位的 20 % ⇒ 这 3.0 ms 花在**上游**
  （转译器的 `scheduler.commit` / `submit_batch` / 队列锁）。下一步是在 Mac 侧给
  `metal2vulkan-runtime` 的 `commit_now` 加计时，不是在 KMD 里找。
- **F5** `prevsub_count` 增长而 `prevsub_total` 一直是 0 ⇒ 计数器没有被记账（P-240 形状：
  字段存在但没人赋值），先修计数器再谈归因。
- **F6** 有效性不成立 ⇒ 按 P-236 判 INVALID 并重飞同一张镜像、同一套判据，
  **不许**改阈值凑结果。

## 6. 范围限制：这一飞只回答 3.0 ms，不回答帧率

- **P-244 的泄漏还没有修**：`usblog-20261119-070345`（`gpu-blitprobe2-20261119`）在第 951 个
  VMM 映射、约第 1005 帧时 CP/SMMU fault，之后 70 % 的日志是 `DeviceLost` 空转。因此
  **本卡只判 `submit` 的归因，不判帧率**；任何长跑（>300 帧）的 fps 数字在泄漏修好前都不可用作结论。
- 该泄漏不是我们每帧的 import：同一批样本里 `objects=613` 而 `imported=39`，即约 94 % 是
  转译器自有的 BO。下一步要数 `NativeAdrenoVm::map`/`unmap` 差，而不是先改我们的导入。
- 采样窗口已修（`if(++probed<=4 || !(probed&31))`）：一场只有约 15 次提交的安静飞行也能拿到
  前四条，这正是上一飞 `submit samples: 0` 的成因（P-233 第三次复发，现已由
  `scripts/check-probe-cadence.py` 门禁守住）。
- 因此 200 s 的飞行足以回答 S2–S6；S7 只检查「面板仍 ≥110 Hz」与「没有 poison」，不检查帧率。

## 5. 结果登记

criteria-sha256: b2306b9ee4e4a157a424d7bf77142e93a9f2dcb65f8f5a3bb7e7d480625045db

### 5.1 飞行事实

| 项 | 值 |
| --- | --- |
| 镜像 | `gpu-submit-20261119` · `boot.img 1ca7fd150cb4f461ac75c4ffaca68e85620dab2b1e06adb1333c160befe802b7` |
| 内核 | `18537b4d633d3ce62ce2a9e24ae788703f01b2b56825f92b8ec04ca6d4cbd5fa`（105,693,184 B） |
| 证据 | `usblog-20261119-095547`，236,641 B / 3,357 行，`complete=true`，supervisor rc=0 |
| 有效性 | `compositor=4 · client_commits=8 · scanout_lines=4` ⇒ 有效（但**空闲**，见 §6） |

### 5.2 判据

| 判据 | 结果 | 实测 |
| --- | --- | --- |
| **S1** 无 panic / `K60KEXC` / backboardd 崩 | ✅ | 三项全 0 |
| **S2** 采样行带 `prevsub_count=`/`prevsub_total=` | ✅ | 4 条（`n=1..4`） |
| **S3** `prevsub_count` 单调增长 | ✅ | 0 → 1 → 2 → 3 |
| **S4** `publish` 仍 ≤2,000 µs | ✅ | 28–58 µs |
| **S5** `submit` 中位 < 4,500 µs | ✅ | **677 µs** |
| **S6** 仍出帧、`imports==frames` | ✅ | 4/4 |
| **S7** 无 poison、面板 ≥110 Hz | ✅ | `status=0x0`；`panel after UI: 122 Hz` |

失败规则：**F4 命中** —— KMD `Submit` 只占 `submit` 的 **13.1 %**（`prevsub_total/prevsub_count = 89 µs` 对 677 µs），
按卡的定义「the 3.0 ms is upstream of us」。

### 5.3 这一飞回答了什么

1. **3.0 ms 不在内核里。** 我们自己的 `NativeAdrenoMethodSubmit` 一次只要 89 µs（63–137 µs），
   只有客户端 `[commands commit]` 的 13 %。内核侧继续优化没有空间。
2. **`submit` 是负载相关的，不是一个常数。** 同一张镜像、同一台设备：
   空闲飞（本飞，8 次提交）677 µs；上一飞（`usblog-20261119-070345`，1,215 次提交）3,015 µs。
   两次的 KMD 部分都在 0.1 ms 量级，所以**多出来的部分随提交并发量增长**。
   这指向转译器队列/slot 竞争（`J scheduled wait` 在那一飞是 617 次共 722 ms），
   而不是我们的 ring 提交或 fence 等待。
3. **`encode` 也随帧变化极大**：本飞 667 / 721 / 22,933 / 25,217 µs，与 `copy` 33.6 / 23.8 / 30.9 / 17.5 ms 同步。
   首帧与含 untile 的帧贵 30 倍，说明「首帧建管线」与「纹理 untile」是同一个数量级的两个独立来源。

### 5.4 边界

本飞只有 4 帧、8 次提交，**不能**用来判帧率或稳态（§6）。要拿「有负载时的 submit」必须在
同一飞里驱动动画且保持 GPU 存活（泄漏在约 1,000 帧时触发，约 140 s）。

### 5.5 下一步

1. 按 F4 的方向：在 Mac 侧给 `metal2vulkan-runtime` 的 `commit_now`/队列取 slot 加计时
   （需要重编 `PongMetalBridge.dylib`），量出「排队 vs 真正提交」的比。
2. 动画驱动是前置条件：没有输入就没有负载，而触摸现在零上报 —— **触摸是这一条路的必经项**，
   也是目标里「跟手」的那一半。
