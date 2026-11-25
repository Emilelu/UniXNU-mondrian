# 上机卡：`gpu-wc-class-20261118`

## 1. 这次只改一件事

上一飞（`gpu-publish-probe-20261118`）拿到了 84 个 `PONG VM: publish sample` 样本：
`publishMapped()` 中位 **10.1 ms**，占 `submit` 的 82 %，而 `submit` 又是 `copy` 里最大的一项。
但**它维护的是谁的字节，仍然不知道**：

- 样本里 `combined=574` 只是「访问到 574 个 write-combined 对象」，
  `publishForDevice()` 在 `distrust_write_combined_=false` 时对这类对象**直接返回、不清 cache**，
  所以「访问数」不等于「维护字节数」。
- `cachebytes` 中位 135 MiB / 610 次调用，但这个总量里 imported / owned / write-combined
  各占多少，没有任何字段说。

上一轮我自己就在这上面栽过（P-237：把「单次调用的增量」当成「累计计数」，
推出「每次提交 52 KB」的错误结论）。所以这一飞**不再猜比例**，只加两个纯观测字段：

- `PONG VM: publish sample …` 行尾追加 `trusted=%u ibytes=%llu obytes=%llu wbytes=%llu wskipped=%llu`
  —— 分别是被维护的 imported 字节、owned 字节、以及**因为 distrust 而被维护**的
  write-combined 字节、以及**因为 trusted 而被跳过**的 write-combined 字节。
- `PONG WC: distrust latched submit=%u audit=%u lines=%u dirty=%u stale=%u status=0x%x resets=%u`
  —— 只在 trust 失效那一刻打**一行**。没有这行，日志永远分不清
  「一开机就已经不信任」和「跑到第 N 次提交才失去信任」，而这两者的原因完全不同。

行为零改动：维护顺序、两个跳过守卫、失败路径、`distrust_write_combined_` 的判定条件全部原样；
`wbytes`/`wskipped` 只是把 `if(distrust_write_combined_)` 这个**已经存在**的判断换成分支计数。

## 2. 镜像与前提

- 镜像目录：`/mnt/e/iOS Port/Work/artifacts/gpu-wc-class-20261118/`
- 构建：`bash scripts/build-strict.sh gpu-wc-class-20261118 --fd …/gpu-drawfix-20261118-cf4485712c29.fd`
- 插件沿用 `metal-plugin-20261118k`（这一飞不碰 `drivers/PongMetal`，避免第二个变量）
- 串口采集由 `scripts/flash.sh` 负责，证据落 `E:/iOS Port/Work/evidence/usblog-<时间戳>/`

## 3. 前置检查（不满足就不飞）

- **P1** 构建 `EXIT=0`，`verify-boot-image: OK`，`image-arg-audit: OK`，30 个参数 ≤607 B。
- **P2** 内核里**有**新字段：`strings kernel.macho | grep -c "wskipped="` ≥1；
  `grep -c "PONG WC: distrust latched"` ≥1。没有就是归档没带上探针，**不要飞**。
- **P3** 设备 `fastboot devices` 可见。
- **P4** 上位卡 `FLIGHT-CARD-20261118n.md` 的 §5.3 仍是当前结论（下一飞只做只读观测）。
- **P5** `git status --porcelain` 为空且分支与远端齐平。
- **P6** `K60_AGENT_ID` 已设置（机器级 boot claim 需要署名，缺失 rc=7）。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

- **S1** 无 `K60KEXC`、无 `panic(`、无 `Debugger called`。
- **S2** 至少 2 行 `PONG VM: publish sample`，且每行都带 `trusted=` 与 `ibytes=`。
- **S3** 这一飞**仍然出帧**：至少一行 `MiniIOMobileFramebuffer: N frames` 且 N>0，
  且 `Pong Metal: c<n>/0` 的 n>0。零帧一律判**无效**（可原地重飞一次），不是失败。

### 4.2 路径身份

- **S4** 仍有 `scanout frames=` 且 `imports==frames`；仍有一行 `scanout copy texture untile …`
  （纹理路径仍然是基线，没被打回逐行）。

### 4.3 假设是否成立（这一飞唯一要回答的问题）

- **S5** 每个样本 `ibytes + obytes + wbytes ≤ bytes`（被维护的三类不超过被访问总量），
  否则计数口径写反了，本飞的其他数字全部作废。
- **S6** 信任状态自洽：要么全程 `trusted=1` 且 `wbytes=0` 且至少一个样本 `wskipped>0`；
  要么出现过 **恰好一行** `PONG WC: distrust latched`，且此后的样本 `trusted=0`、`wbytes>0`。
  两者都不成立（例如 `trusted=0` 却没有任何 latched 行）⇒ 探针自身不可信。
- **S7** 归因落格（这是唯一的新结论）：取样本中位数，比较 `ibytes` 与 `wbytes` 谁占 `cachebytes` 的主体。
  只要其中一类 ≥70 %，本飞就给出**单一归因**；两类都在 30–70 % ⇒ 记为「混合」，下一步要分别处理。
- **S8** 帧率不低于上一飞的 7.28 fps 的 90 %（探针每 32 次一行，成本可忽略；掉下去说明观测本身有副作用）。

### 4.4 失败规则

- **F1** panic / `K60KEXC` ⇒ 回滚这两个探针改动。它们只加分支计数，出现异常说明改错了位置。
- **F2** 零行 `PONG VM: publish sample` ⇒ 探针没进内核（先查 P2），不是「没有维护」。
- **F3** 零帧 ⇒ 判无效（P-236），先重飞一次，仍零帧再查合成器，不要在此卡上讨论性能。
- **F4** `trusted=1` 且 `publish us` 中位 ≤ 3,000 µs ⇒ **维护在信任态下是便宜的**，
  那 10.1 ms 属于 distrust 路径；下一步是查 `distrust latched` 那一次的 `dirty/lines`，
  而不是去动 `publishMapped` 的范围。
- **F5** `ibytes / cachebytes` > 0.8 ⇒ 维护的主体是**客户端刚写过的 imported 帧**，
  write-combined 集合不是成本；下一步是减少每帧导入的面数（或让导入页在提交间保持有效），
  这条路线必须连同「GPU 读的页在什么时候被回收」一起写清楚才允许动手。
- **F6** `wbytes / cachebytes` > 0.8 ⇒ 维护的主体是 **write-combined BO**，即 distrust 一直挂着；
  下一步是查为什么 trust 会失效（`audit … dirty=`），并验证 `reassertWriteCombined()` 是否
  真的把这些页重新写成 write-combined。

## 5. 结果登记

### 5.1 这一飞

| 项 | 值 |
| --- | --- |
| 镜像 | `gpu-wc-class-20261118` |
| boot.img | `b02be6d8d99ce6c014fbea75cd15057eeea34e1a9d78db8820286b2158fe1f85` |
| kernel | `4c97a9007681c6e513f72365a4f1d25552ca1efce446d1fa22ee1a0f0d6e48c9` (105,603,072 B) |
| 命令行 | 30 项 / 596 B（`pong_metal=1 pong_gpu_scanout=1 sheng-gpu-addon=1 k60_autoreset=300 applog=1`） |
| 证据 | `E:/iOS Port/Work/evidence/usblog-20261118-233946`（306,107 B / 3,9xx 行） |
| 上机时间 | 2026-11-18 23:39（`K60_AGENT_ID=lead`，先到先得的机器级 claim） |

### 5.2 S1–S8 逐条

| 判据 | 结果 | 实测 |
| --- | --- | --- |
| **S1** 无 panic | PASS | `K60KEXC` 0、`panic(` 0；SpringBoard 131 行 |
| **S2** ≥2 条带分类字段的 publish 样本 | PASS | 125 条 VM 样本，全部带 `trusted/ibytes/obytes/wbytes/wskipped` |
| **S3** 仍在出帧 | PASS | `scanout frames=` 192 条；`MiniIOMobileFramebuffer` 73 条 |
| **S5** 三类之和 ≤ 访问总量 | PASS | `ibytes 97,742,848 + 0 + 0 ≤ bytes` |
| **S6** 写合并信任态自洽 | PASS | `trusted` 恒 1、`wbytes` 恒 0、`wskipped` 中位 274,624,512 B、无 latch 行 |
| **S7** 单一类别 ≥70% | PASS | 归属 = **imported**（`ibytes/cachebytes = 1.00`） |
| **S8** 帧率不劣化 | 见 §5.4 | 窗口内 199 帧 / 5,010 ms ≈ 39.7 fps（这是合成器窗口，不是整机帧率） |

### 5.3 F 规则

未命中 F1–F4、F6；**命中 F5**（`ibytes/cachebytes > 0.8`）。

### 5.4 结论（这一飞回答的唯一问题）

1. **写合并不是元凶**：`trusted` 全程为 1，`wbytes` 恒 0，另有 274.6 MB 被 `wskipped` 跳过 —— 每次提交并没有真去清写合并页。这否掉了「`distrust_write_combined_` 从启动就为真」的猜测。
2. **被维护的主体是 imported 帧**：每次采样调用清+无效化 **93.2 MiB**（`97,742,848 B`）的导入页，`ibytes/cachebytes = 1.00`。
3. **量级对上了**：93.2 MiB / 64 B = 1.53M 条 cache line；实测 publish 中位 **6,635 µs**（max 7,878 µs），即约 4.3 ns/line —— 与 `dc civac` 每行的成本同阶。**所以 submit 的那几毫秒就是导入帧的 cache 维护，不是遍历开销，也不是写合并。**
4. 这一飞同时把 n 卡 §5.4 的「双峰」解释了一半：6.6 ms 档是「只维护导入帧」的常态，10.1 ms 档对应更大的导入集。
5. 下一步按 F5：**减少每帧导入的面数**（当前每帧重新导入 3–5 个客户端 surface），且必须先把映射生命周期写清楚 —— 见 `PongAdrenoScanout.cpp:195-196` 每帧 `release()` 的既有事实。

### 5.5 顺带观察（不构成判据）

- 触摸这一飞全程没有产出过一条已验证帧（`goodix: type=` 计数 0），但初始化序列与 11-14 那次可用飞行逐行相同（`CFG-DL wrote=1488/1488 bad=0`、`COORD-ON ack=80`）；`invalid contact report` 在可用飞行里也有 6 条，属常态噪声，不能当判据。
- 触摸诊断自身有窗口上限：`goodix_poll()` 的打印条件带 `observations < 40`，40 条之后整段不再输出，所以「poll 1024 之后到底有没有事件」这一飞看不到 —— 下一飞要按「触摸时刻窗口」重新设计取证。同一症状在 20:16 / 22:32 两飞也在（各 7 条 / 4 条），而 11-14、11-15 两次触摸可用的飞行里同样有 6 条 —— 所以这些报错是常态噪声，不是触摸失效的判据。
- `crashed:` 8 条，需在下一飞按进程名逐条核对是否与 GPU 有关。
