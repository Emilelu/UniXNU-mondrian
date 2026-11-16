# GLINK 多槽：把音频通道接进同一个 QcomGlink 实例

> 状态：2026-11-15。**离线原型**——不改 drivers/PongPower/、不上机、不申请 run 2。
> 结论先行：传输层本身已经是每槽独立的，唯一挡住第二个消费者的是 QcomGlink.h:17 的一个常量；
> 真正的风险不在协议，而在**建槽时机**和**消费者侧的单通道假设**。

---

## 0. 三句话

1. **一个实例、两个槽**：音频的 GPR 通道（adsp_apps，intent 512 B × 20）必须挂在 K60PmicGlink 已经
   qcom_glink_adopt() 采纳的**同一对 SMEM FIFO** 上。另起实例会互相踢坏 intent 计数与 FIFO 索引
   （QcomGlink.h:86 的 adopt 要求 APSS 侧索引为零）。
2. **建槽必须早于远端 OPEN**：QcomGlink.c:331-364 收到 QCOM_GLINK_OPEN 时按名字在 channel[] 里找
   **已注册**的槽，找不到就 unknown_opens++ + last_unknown + note_unknown() 后**丢弃**（不回 OPEN_ACK）。
   所以 qcom_glink_channel() 必须在 DSP 发 OPEN 之前调用。
3. **协议侧不需要改**：progress() / handle_data() / by_lcid() / by_rcid() / stop() 全部按
   QCOM_GLINK_MAX_CHANNELS 循环，没有一处 channel[0] 直接下标。把上限从 1 改成 2，
   两个通道就各走各的状态机。

---

## 1. 现有实现的接口面（实读 drivers/PongPower/QcomGlink.{h,c}）

### 1.1 环几何

| 项 | 事实 | 出处 |
| --- | --- | --- |
| FIFO 结构 | {volatile uint32_t *head, *tail; volatile uint8_t *data; uint32_t length;}，索引是**字节偏移** | QcomGlink.h:43-47 |
| 合法几何 | length ∈ [256, 65536] 且 8 对齐；head/tail 4 字节对齐、8 对齐、小于 length | QcomGlink.c:21-28 |
| 采纳条件 | *tx.head == 0 且 *rx.tail == 0（新认证 epoch 的宿主 FIFO 才允许），否则 QcomGlinkArgument | QcomGlink.c:97-109 |
| 发送保留 | 发送方留 8 B 让满 FIFO 不显空，再留 16 B 给 READ_NOTIF；tx_avail 先扣 24 B | QcomGlink.c:7-8, 38-45 |
| 消息对齐 | 每条消息 align8() 补齐；控制消息 8 B，INTENT 16 B，TX_DATA 头 16 B | QcomGlink.c:17, 66-80 |
| 描述符 | desc[0]=远端 tx tail、desc[1]=APSS tx head、desc[2]=APSS rx tail、desc[3]=远端 rx head；TX FIFO 用 {&desc[1], &desc[0]}，RX 用 {&desc[3], &desc[2]} | K60PmicGlink.cpp:74-80 |

**关键：这两个 FIFO 是整条链路共享的**，与槽无关。多槽只影响**消息体里的 lcid/rcid 由谁消费**，
不影响环本身。

### 1.2 interrupt / doorbell 语义

- 仓库侧只有一个回调：qcom_glink_adopt(g, tx, rx, kick, kick_context)（QcomGlink.h:86）；
  kick 只在 kick_pending 置位时被调用一次（QcomGlink.c:486, 503, 519, 523）。
- 实现侧（电池栈）是 **IPCC**：*(ipccWindow.va + 0x0c) = ipcc_client << 16 | ipcc_signal
  （K60PmicGlink.cpp:162-170，前后各有 dmb oshst / dsb sy）。
- 接收方向是**轮询**：qcom_glink_poll() 每次处理有界条数（budget = rx.length / 8 + 1，
  QcomGlink.c:479），由拥有者在中转到达时调用。
- **多槽后 doorbell 不变**：一次 kick 唤醒的是整条链路，两个消费者共用一个 poll 循环。
  这也意味着**任何一方都不能自己停链**——qcom_glink_stop() 会把 broken 置 1 并对**所有**槽
  回调 state(0)（QcomGlink.c:197-207）。

### 1.3 打点位置（本板无串口，屏幕 / USB 日志就是日志）

| 层 | 可观测点 | 出处 |
| --- | --- | --- |
| 传输层计数器 | rx_messages、tx_messages、rx_data、unknown_opens、dropped | QcomGlink.h:79 |
| 未服务通道名 | last_unknown[32]、unknown_names[96]（去重、空格分隔） | QcomGlink.h:80-81；QcomGlink.c:287-306 |
| 消费者访问器 | K60PmicGlink::received() = native.rx_messages、transmitted() = native.tx_messages | K60PmicGlink.h:26-27 |
| 内核日志行 | IOLog("K60Battery: adopting authenticated PAS1 GLINK epoch=%llu desc=%x tx=%x/%x rx=%x/%x (no FIFO reset)") | K60PmicGlink.cpp:128 |
| 日志出口 | k60_usblog（0300-k60-usblog-ep0.patch，级别 0/1/2，刷机主日志通道） | docs/engineering/BOOT-ARGS.md:38 |

**多槽之后最便宜的一个判据，不需要新代码**：unknown_names 现在只会写「没人服务过的 OPEN 名字」。
一旦音频槽注册成功，它就再也不会出现 adsp_apps；反过来说，**unknown_names 里出现 adsp_apps 就是
「音频建槽太晚」的直接证据**。

---

## 2. 每槽的状态机已经是独立的

逐个函数核过（QcomGlink.c）：

| 函数 | 行 | 是否按槽 |
| --- | --- | --- |
| qcom_glink_channel() | 112-137 | 线性找 !used 槽，满则返回 0（QcomGlinkFull 语义） |
| by_lcid() / by_rcid() | 139-150 | 全槽线性查找；by_rcid 还要求 remote_open |
| reset_channel() | 176-186 | 单槽（清 local[4] / remote[48] / 状态位） |
| progress() | 210-247 | 遍历所有槽：CLOSE → RX_DONE(_W_REUSE) → OPEN → advertise → state(1) |
| handle_data() | 249-282 | by_rcid() 定位槽，按 liid-1 索引该槽的 local intent，完成后回调该槽的 receive |
| receive_one() OPEN | 331-364 | 按**名字**匹配槽；未匹配则计数并丢弃 |
| receive_one() INTENT | 393-421 | by_rcid() 定位槽，写该槽的 remote[48] 表 |
| qcom_glink_send() | 490-525 | 只用传入的 c->remote[]，与其它槽无关 |
| qcom_glink_stop() | 197-207 | 遍历所有槽回调 state(0)（**唯一一处跨槽动作**） |

结论：**唯一的单槽假设是数组长度**。这也是为什么原型只有一行。

---

## 3. 原型：一行补丁 + 242 条宿主断言

### 3.1 补丁（不进任何 series）

patches/audio/0002-k60-glink-multislot.patch（1,078 B / 18 行）：

    -#define QCOM_GLINK_MAX_CHANNELS 1u /* exclusively leased K60 PMIC endpoint */
    +/* Two slots: the leased PMIC endpoint the battery stack opens, and the
    + * audio GPR channel ("adsp_apps") of the same instance. Every path below
    + * already runs per slot, so this bound was the only thing keeping the
    + * second consumer out. See docs/research/audio/GLINK-MULTISLOT.md. */
    +#define QCOM_GLINK_MAX_CHANNELS 2u

- 用 diff -u 生成（P-155 口径），patch -p1 与 git apply 都能解析（P-162 门禁 --all 实测 307 个补丁全过）。
- **不在** patches/audio/series，也**不在** patches/xnu/series——它是一份可复核的原型，不是一个待应用的补丁。
- 代价（宿主实测 sizeof）：QcomGlinkChannel 712 B；QcomGlink 从 **960 B** 涨到 **1,672 B**（+712 B）。
  两个槽都在 K60PmicGlink 的成员里（K60PmicGlink.h:37），不涉及堆分配。

### 3.2 宿主测试

drivers/PongAudio/tests/test-glink-multislot.c（24 KB）+ run-glink-multislot-tests.sh。

测试自己扮演 DSP：往 rx FIFO 里塞真实的 GLINK 消息（VERSION_ACK / OPEN / OPEN_ACK / INTENT /
TX_DATA / RX_DONE），从 tx FIFO 里读回 AP 侧写的东西。没有 MMIO、没有 SMEM、没有设备。

    $ sh drivers/PongAudio/tests/run-glink-multislot-tests.sh
    two-slot prototype: QCOM_GLINK_MAX_CHANNELS=2, sizeof(QcomGlinkChannel)=712, sizeof(QcomGlink)=1672
    TESTS OK 242 cases

| 场景 | 断言要点 |
| --- | --- |
| 注册 | 两个不同名字各得一个槽、lcid 1/2、各自的 intent_size/intent_count 不被串改；**第三个注册被拒且不碰前两槽** |
| 建链 | 每个槽发自己的 OPEN（带自己的名字）；DSP **乱序** open（音频先、电池后）也各自拿到自己的 rcid；每槽 advertise 自己的 intent（电池 4×256、音频 2×512），state(1) 各一次 |
| 分发 | 音频的消息只进音频消费者、电池的只进电池；**交错**三条（A,B,A）一次 poll 后各槽保持自己的顺序 |
| 错序 / 重放 | 同一 liid 重放 → 仍只进同一消费者，另一个消费者零条；越界 liid → 判 QcomGlinkCorrupt 停链，**不投递给另一个槽** |
| 无人认领 | 未注册名字的 OPEN：不回应、不碰任何槽、unknown_opens=1、last_unknown/unknown_names 记名；陌生 rcid 的数据：dropped=1，两个消费者都没收到 |
| 发送 / 收尾 | 只有电池槽有远端 intent 时，音频槽 send 得 QcomGlinkAgain 并发 RX_INTENT_REQ（不越界发数据）；stop 对**两个**槽各回调一次 state(0)，第二次 stop 是 no-op；坏几何（非零索引、非 8 倍数长度、无 doorbell）被拒 |

文件头的 #error 与 main() 首条 expect_eq(QCOM_GLINK_MAX_CHANNELS, 2, ...) 一起保证：
**拿未打补丁的传输层去跑这个测试会直接编译失败**，不会静默退化成单槽还报绿。

### 3.3 它证明了什么、没证明什么

**证明了**：传输层在多槽下不会串——注册、建链、分发、重放、无人认领、停链六条路径都是逐槽隔离的；
以及「第二个消费者的接入点确实只有那一行」。

**没证明**（必须真机，且要等 provider 返回真 lease）：

- 真实 FIFO 几何：tx_bytes/rx_bytes 来自 lease（256..65536、8 对齐），宿主用的是 4,096；
- 真实 DSP 行为：adsp_apps 的 OPEN 是 DSP 主动发起还是我们发起、intent 512×20 是否被接受；
- 时序：K60PmicGlink::discover() 里 desc[1] == lease.host_tx_head 与 desc[2] == lease.host_rx_tail
  的比对（K60PmicGlink.cpp:78）在音频建槽之后是否仍成立；
- 中断 / 轮询节奏：真机上 kick 走 IPCC，两个消费者共享一个 poll 循环，谁的延迟预算是多少；
- SMP2P 443 ready 与 GLINK 通道建立的真实先后。

---

## 4. provider 落地后音频侧要改的三处

给 provider 实现者的 diff 清单（Lead m07917 第 ② 条，降级成这一节）：

1. **启动点**：音频 worker 现在是 pong_audio_probe=1 直启（patches/xnu/0504 的 pong_audio_bootstrap()）。
   将来要改成等 k60_adsp_owner_acquire() 成功、且 lease.flags 的 **bit2 K60AdspGlinkExclusive（=4）**
   置位之后才启动；acquire 失败就停在降级档（PAS1-AUDIO-REQUIREMENTS.md §2 的五级表）。
2. **GPR/APM 注册时机**：qcom_glink_channel(&native, "adsp_apps", 512, 20, storage, ...) 必须在
   **acquire 之后、publish 之前**调用——acquire 之后是因为 FIFO 与 epoch 还没交出来，publish 之前
   是因为 DSP 会在 SMP2P ready 后立刻开通道（见 §0 第 2 条：晚了就被当 unknown 丢弃）。
   与 PAS1-AUDIO-REQUIREMENTS.md §3 的时序图一致。
3. **epoch 绑定与降级**：音频的 QcomGlinkChannel * 必须与电池挂在**同一个 epoch** 上；
   k60_adsp_owner_revalidate() 失败时，音频侧要主动关掉 AFE 请求并静音（PongAudioAfe.h 的六个步骤
   不再下发），而不是继续往一个死通道里 send 拿 QcomGlinkAgain。

---

## 5. 怎么跑 / 边界

    sh drivers/PongAudio/tests/run-glink-multislot-tests.sh     # 期望 TESTS OK 242 cases

脚本把 QcomGlink.{h,c} 拷到临时目录、用补丁打上、再编译，**不改仓库里的 drivers/PongPower/**。
它不是任何门禁的一部分（RULES.toml 里没有规则跑它），需要人手跑——这也是它放在
drivers/PongAudio/tests/ 而不是 scripts/tests/ 的原因：它测的是原型，不是仓库当前状态。

边界：不改 drivers/PongPower/（2026-11-17 用户把该目录划给音频线，但 Lead 裁决 provider 只把
MAX_CHANNELS 扩到 2；本线不直接改文件）、不动 K60Battmgr.c（charger/USB 线）、不上机、不申请 run 2。
