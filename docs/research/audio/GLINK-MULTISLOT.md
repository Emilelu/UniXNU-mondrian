# GLINK 多槽：把音频通道接进同一个 QcomGlink 实例

> 状态：2026-11-17。**传输层与音频桥已落地（离线）**——QCOM_GLINK_MAX_CHANNELS 2、MAX_LOCAL_INTENTS 20、
> K60AudioGlink 桥；未上机、不申请 run 2。
> 结论先行：传输层本身已经是每槽独立的，挡住第二个消费者的是 QcomGlink.h 的数组长度；
> 真正的风险不在协议，而在**建槽时机**和**消费者侧的单通道假设**——后者已由 K60AudioGlink 消掉。

---

## 0. 三句话

1. **一个实例、两个槽**：音频的 GPR 通道（adsp_apps，intent 512 B × 20）必须挂在 K60PmicGlink 已经
   qcom_glink_adopt() 采纳的**同一对 SMEM FIFO** 上。另起实例会互相踢坏 intent 计数与 FIFO 索引
   （QcomGlink.h:86 的 adopt 要求 APSS 侧索引为零）。
2. **建槽必须早于远端 OPEN**：QcomGlink.c:331-364 收到 QCOM_GLINK_OPEN 时按名字在 channel[] 里找
   **已注册**的槽，找不到就 unknown_opens++ + last_unknown + note_unknown() 后**丢弃**（不回 OPEN_ACK）。
   所以 qcom_glink_channel() 必须在 DSP 发 OPEN 之前调用。
3. **协议侧不需要改**：progress() / handle_data() / by_lcid() / by_rcid() / stop() 全部按
   QCOM_GLINK_MAX_CHANNELS 循环，没有一处 channel[0] 直接下标。把上限从 1 改成 2、
   本地 intent 表从 4 提到 20，两个通道就各走各的状态机。

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

## 3. 落地：两个常量 + 376 条宿主断言

### 3.1 源码（已落地）

`drivers/PongPower/QcomGlink.h:17` 自 2026-11-17 起就是：

    #define QCOM_GLINK_MAX_CHANNELS 2u /* PMIC endpoint + audio adsp_apps, one shared owner */

同文件还加了三个构建标签宏（`QCOM_GLINK_STRINGIFY_INNER` / `QCOM_GLINK_STRINGIFY` / `QCOM_GLINK_BUILD_TAG`），
`K60PmicGlink::open()` 在打开传输后打印
`K60Battery: GLINK transport QcomGlink max_channels=2u local_intents=20 channel_bytes=904 audio_intent_bytes=10240`。这行字符串是构建产物的
artifact 证据（`kernel.macho` 里可以 `strings` 到）：镜像 d（audio-probe-20261117d）的 kernel.macho 里 `QcomGlink max_channels=2u` 出现 1 处（d 时还未扩 local intents）；镜像 e（audio-probe-20261117e，kernel_built 3ac73816…）里 `QcomGlink max_channels=2u local_intents=20` 与 `PongAudio: glink adsp_apps slot queued (512x20)` 各 1 处；镜像 f（audio-probe-20261117f，kernel_built 0acca673…）里上述两个字符串与 `PongAudio: GPR GET_SPF_STATE send bytes=%u rc=%d` 各 1 处（0003 已在首个 up 回调发 24 B GPR）；镜像 i（audio-probe-20261117i，kernel_built 923f9f44…）里新的 `PongAudio: GPR GET_SPF_STATE send bytes=%u src=0x%x dst=0x%x rc=%d`、`QcomGlink max_channels=2u local_intents=20u` 与 `PongAudio: glink adsp_apps slot queued (512x20)` 各 1 处。

历史原型补丁 `patches/audio/0002-k60-glink-multislot.patch`（1,078 B / 18 行，原来是同一行 1u→2u 的 diff）
已于同日退役：源文件改成 2u 之后，它不再是可应用的补丁。它当年存在的意义是让宿主测试能在临时副本上
验证两槽路径；现在 `run-glink-multislot-tests.sh` 直接编译 `drivers/PongPower` 的真实源。

- 代价（宿主实测 sizeof）：QcomGlinkChannel 904 B（20 个本地 intent）；QcomGlink 从 **960 B** 涨到 **2,056 B**（+1,096 B）。
  两个槽都在 K60PmicGlink 的成员里（K60PmicGlink.h:37），不涉及堆分配；音频的 512×20 storage 是 `K60AudioGlink` 的成员，10,240 B。
- 音频桥：`K60AudioGlink.c/.h` + `K60PmicGlinkAudio.h`；`K60PmicGlink::attachAudio()` 只排队，
  `poll()` 的 `k60_audio_glink_service()` 负责真正 `qcom_glink_channel()`，`stop()` 时清槽；`k60_audio_glink_send()` 走 `qcom_glink_send()`，376 条断言覆盖本地队列、本槽 remote intent、TooBig 与 stop 后 -2002。GPR 首发也在 0003：`pong_audio_glink_state()` 第一次 up 时用 `pong_afe_gpr_spf_state_query()` 组 24 B `GET_SPF_STATE`（token 0x00010001，src 0x2001 / dst 1），经 `k60_pmic_glink_send_audio()` 发出；receive 回调解码 opcode/token。

### 3.2 宿主测试

drivers/PongAudio/tests/test-glink-multislot.c + run-glink-multislot-tests.sh。
runner 直接编译 `drivers/PongPower/QcomGlink.c`、`QcomGlink.h` 与 `K60AudioGlink.c`，不再复制、不再打补丁。

测试自己扮演 DSP：往 rx FIFO 里塞真实的 GLINK 消息（VERSION_ACK / OPEN / OPEN_ACK / INTENT /
TX_DATA / RX_DONE），从 tx FIFO 里读回 AP 侧写的东西。没有 MMIO、没有 SMEM、没有设备。

    $ sh drivers/PongAudio/tests/run-glink-multislot-tests.sh
    two-slot transport: QCOM_GLINK_MAX_CHANNELS=2, sizeof(QcomGlinkChannel)=904, sizeof(QcomGlink)=2056
    TESTS OK 376 cases

| 场景 | 断言要点 |
| --- | --- |
| 注册 | 两个不同名字各得一个槽、lcid 1/2、各自的 intent_size/intent_count 不被串改；**第三个注册被拒且不碰前两槽** |
| 建链 | 每个槽发自己的 OPEN（带自己的名字）；DSP **乱序** open（音频先、电池后）也各自拿到自己的 rcid；每槽 advertise 自己的 intent（电池 4×256、音频 2×512），state(1) 各一次 |
| 分发 | 音频的消息只进音频消费者、电池的只进电池；**交错**三条（A,B,A）一次 poll 后各槽保持自己的顺序 |
| 错序 / 重放 | 同一 liid 重放 → 仍只进同一消费者，另一个消费者零条；越界 liid → 判 QcomGlinkCorrupt 停链，**不投递给另一个槽** |
| 无人认领 | 未注册名字的 OPEN：不回应、不碰任何槽、unknown_opens=1、last_unknown/unknown_names 记名；陌生 rcid 的数据：dropped=1，两个消费者都没收到 |
| 发送 / 收尾 | 只有电池槽有远端 intent 时，音频槽 send 返回 `K60_PMIC_GLINK_AUDIO_OK` 并把一个最大 560 B 的包入队，service 在 intent 出现后 flush；队列满时第二个包返回 REFUSED（不越界发数据）；stop 对**两个**槽各回调一次 state(0)，第二次 stop 是 no-op；坏几何（非零索引、非 8 倍数长度、无 doorbell）被拒 |
| 音频桥 | `K60AudioGlink` 排队一个 `adsp_apps` 请求，`service()` 在第一次 `qcom_glink_poll()` 前调用 `qcom_glink_channel()`；DSP 的 OPEN + 20 个 INTENT 后 state 变 up，peer_data 只进音频 callback；state up 后 `pong_audio.c` 发 GPR GET_SPF_STATE（见 0003）；`stop()` 后无 transport 报 -2001 |
| 音频发送 | 音频槽有 remote intent 后 `k60_audio_glink_send()` 写 TX_DATA（local lcid 1、remote intent 0x2001、payload `gpr`）；无远端 intent 时返回 OK 并入队、队列满 REFUSED；4096 B 得 `QcomGlinkTooBig`；stop 后 -2002；无 transport -2001 |

文件头的 #error 与 main() 首条 expect_eq(QCOM_GLINK_MAX_CHANNELS, 2, ...) 一起保证：
**把 `QCOM_GLINK_MAX_CHANNELS` 退回 1 的传输层去跑这个测试会直接编译失败**，不会静默退化成单槽还报绿。

### 3.3 它证明了什么、没证明什么

**证明了**：传输层在多槽下不会串——注册、建链、分发、重放、无人认领、停链六条路径都是逐槽隔离的；
`K60AudioGlink` 能把 `adsp_apps` 作为第二个消费者排队、注册并按槽收数据；以及「第二个消费者的接入点确实只有数组长度」。

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
2. **建槽时机与桥接**：音频侧已经实现 `K60AudioGlink`——`pong_audio_start()` 排队，
   `K60PmicGlink::poll()` 在 `qcom_glink_poll()` 前调用 `k60_audio_glink_service()`，由后者调
   `qcom_glink_channel(&native, "adsp_apps", 512, 20, storage, ...)`；provider 不需要再写注册代码，
   只需保证 `K60PmicGlink::open()` 发生在 **lease 有效之后**（FIFO 与 epoch 已交出），并且首次 poll 早于
   DSP 在 SMP2P ready 后发来的 OPEN（见 §0 第 2 条）。
3. **epoch 绑定与降级**：音频的 QcomGlinkChannel * 必须与电池挂在**同一个 epoch** 上；
   k60_adsp_owner_revalidate() 失败时，音频侧要主动关掉 AFE 请求并静音（PongAudioAfe.h 的六个步骤
   不再下发），而不是继续往一个死通道里 send 拿 QcomGlinkAgain。

---

## 5. 怎么跑 / 边界

    sh drivers/PongAudio/tests/run-glink-multislot-tests.sh     # 期望 TESTS OK 376 cases

脚本直接编译当前 `drivers/PongPower/QcomGlink.c`、`QcomGlink.h` 与 `K60AudioGlink.c`，不复制、不打补丁。
它不是任何门禁的一部分（RULES.toml 里没有规则跑它），需要人手跑——它测的是传输层与音频桥，不是某个
单独的原型补丁。

边界：`drivers/PongPower/` 已于 2026-11-17 由用户划给音频线，本线把它改到 `MAX_CHANNELS=2`、
`MAX_LOCAL_INTENTS=20` 并加入 `K60AudioGlink` 桥；不动 `K60Battmgr.c`（charger/USB 线）、不上机、
不申请 run 2。
