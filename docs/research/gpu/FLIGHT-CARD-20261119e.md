# 飞行卡 e：`gpu-submit-20261119` —— `submit` 那 3.0 ms 是内核还是转译器

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

## 5. 结果登记

（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入。）
