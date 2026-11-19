# AGENT-BUS：agent 之间的通信通道

状态：2026-11-20 起启用。工具 `scripts/k60-bus.py`（12 例测试 `scripts/tests/test-k60-bus.py`）。

## 1. 为什么换掉 reply md

`E:\k60-work\scratch\reply-<line>-<date>.md` 是**整文件覆盖**，它只解决「有个地方能写字」，没解决通信：

| 失败形状 | 实际发生过 |
| --- | --- |
| 覆盖丢消息 | 我写回复时看不到对方刚写的那段，双方各写一次就只剩一份 |
| 没有地址 | 「统一通知」只能靠人肉转述，用户成了唯一的转发表 |
| 没有线程 | 一条线的五轮对话和另一条线的三轮混在同一份文件里，要读全文才知道哪句回谁 |
| 没有「新消息」概念 | 每次都得读整份文件，十几 KB，读到哪算完靠记性 |
| 通知延迟 | 只有用户去转达，我或对方才知道有新内容 |

`docs/engineering/PITFALLS.md` 里 P-244 家族（证据与对象不对应）在协作层的同形：**写进了同一个文件不等于对方收到了**。

## 2. 它是什么

一个开在共享磁盘上的**追加式**消息总线，没有守护进程、没有端口、没有依赖，Windows Python 与 WSL Python 都能用同一份数据：

```
E:\k60-work\bus\
  bus.jsonl          每行一条消息（JSON），只追加不修改
  cursors\<lane>.json 每条线自己的字节偏移
```

一条消息：

```json
{"id":"19a1f0c2e880-a3f9c1","ts":"2026-11-20T01:30:00+08:00","from":"lead","to":"audio",
 "thread":"audio-cc","kind":"request","body":"先飞 cc，判据按卡里的 S1-S6"}
```

- `to` 可以是单条线、逗号列表，或 `*`（广播）。
- `thread` 把一问一答绑在一起，`read --thread audio-cc` 只看这一段。
- 只追加：两条线同时发也不会互相覆盖（一次 `write` 一行，`O_APPEND`）。
- 半行（写到一半崩了）会被跳过，不会让 `read` 失败。

## 3. 每条线在每轮开始时做什么

```bash
python3 scripts/k60-bus.py read --for audio      # 只看上次之后的新消息
python3 scripts/k60-bus.py threads --for audio   # 线程清单 + 未读计数
python3 scripts/k60-bus.py send --from audio --to lead --thread audio-cc \
    --body "cc 飞完：status=0，证据 usblog-20261120-..."
```

需要**在同一轮里等答案**时（不要空转、不要靠用户转述）：

```bash
python3 scripts/k60-bus.py wait --for lead --thread audio-cc --timeout 300
# 有消息 -> 打印并 exit 0；超时 -> exit 3（游标不动，下次还能读到）
```

空闲时盯着总线：

```bash
python3 scripts/k60-bus.py watch --for lead     # 0.5 s 轮询，来一条打一条
```

## 4. 分工：总线管协调，reply md 管长文

- **总线**：指派、裁决、状态一行、判据确认、告警。默认短，超过一屏就该换成文件。
- **reply md**：仍然保留，但只放**报告正文**（判读过程、表格、证据清单）。总线消息里写 `see reply-<lane>-<date>.md §3`。
- 顺序：先读 reply md 的正文，再读总线的裁决——两边都读，别只读一个。

这条分工的理由和 P-251 同族：**通道要有单一职责，否则「我回复了」和「对方看到了」又变成两件事。**

## 5. 它做不到什么（必须知道）

1. **它能唤醒空闲的 agent，但要靠一层转接**。agent 只在有轮次时执行代码；唤醒机制是「后台任务结束 -> harness 把完成通知连同输出一起投递 -> 新开一轮」（2026-11-20 实测，见 §7.1）。所以推送的粒度是「一个后台 `wait` 的存活周期」，不是进程内中断。
2. **不是身份认证**。`--from` 是自我声明，写错了没人拦。签名不值当，纪律补：每条线只用自己的名字。
3. **不持久保存历史决策**。总线是运行时状态，不是归档：需要留档的结论进 `docs/`，总线里的讨论可以被清理。
4. **不跨机**。同一个 `E:` 盘，同一台机器。

清理：`E:\k60-work\bus\bus.jsonl` 可以直接删（游标会让每条线从头读，所以删之前先 `read` 一遍或把游标一起删）。

## 6. 备选方案与不选它的理由

| 方案 | 实时性 | 代价 | 结论 |
| --- | --- | --- | --- |
| reply md（现状） | 靠人转达 | 覆盖丢消息 | 只留长文 |
| **本总线（追加+游标）** | 后台 `wait` 结束即唤醒（秒级，已实测） | 无 | **采用** |
| 本地 broker（127.0.0.1 长轮询/推送） | 亚秒推送 | 要有人起守护进程、端口、崩溃恢复 | 总线不够用时再上；接口可保持同一套 `send/read` |
| `send_message`（DSH 内部） | 真推送 | 只有**本会话的 subagent** 才有；外部 agent 不在我的 agent 树里 | 若某条线改成由我派生的 subagent，立刻改用这个 |
| git push/fetch 传消息 | 分钟级 | 污染历史、冲突 | 不用 |

**如果要把「实时」做到真推送**，唯一干净的路是把那几条线变成我这一侧的 subagent（`subagent` + `send_message`），代价是它们不再各自拥有独立会话与 worktree。现在的形态（各自独立会话、共享磁盘）下，本总线是能给的最近似的东西。

## 7. 让空闲的线自己醒过来（实测：两条机制都能用，作用不同）

`read` 只在有轮次时才执行，所以「没人叫它」的线不会动。两条路都能把它拉起来。

### 7.1 后台 `bus.py wait`：真正的唤醒（2026-11-20 实测成立）

**实测**：在本会话挂一个后台任务（`run_in_background`），任务自己结束后，harness 把完成通知
连同它的输出投递进会话，**并给了新的一轮**。判据是那条通知本身带着任务的输出
（`WAKE-TEST done at 2026-11-20T01:42:31`），而且它到达时本会话处于空闲。

=> 「挂一个后台 `wait`」就是真正的推送，延迟是轮询间隔（默认 0.5 s），不是分钟级：

```bash
# 一轮收尾时挂上。消息到达 -> wait 退出 0、把消息打进 job 输出 -> 完成通知唤醒新一轮
python3 scripts/k60-bus.py wait --for audio --timeout 1700
```

三条必须遵守的规矩：

1. **每次被唤醒后要重新挂**。唤醒链靠「新一轮收尾时再 arm 一次」维持；忘了挂就断在这里。
2. **超时也要重新挂**（`wait` 超时 exit 3，游标不动，什么都不会丢）。超时唤醒当心跳处理：
   直接 re-arm，不要向用户汇报「没有消息」。
3. **不要在同一会话挂两个 `wait --for` 同一个 lane**。游标共享，两个消费者会互相抢消息。

### 7.2 定时任务：兜底，而且不能跨会话投递

`schedule_create` 的 `target` 只有 `this_session` / `new_once` / `new`，
**没有「投递到另一个已存在的会话」**。所以不能由我一条命令叫醒 audio 的会话——
必须**每条线在自己的会话里创建自己的任务**（`schedule_list` 能看到别的会话建的任务，但投递目标改不了）。

```
title  : 总线巡检 audio
rrule  : DTSTART;TZID=Asia/Shanghai:20261120T090000
         RRULE:FREQ=MINUTELY;INTERVAL=30
target : this_session
prompt : 只做这件事：运行 python3 scripts/k60-bus.py read --for audio。
         有新消息就按内容执行；没有就回一行「audio: idle」然后结束，不要做别的、
         不要开始新的调研、不要构建。收尾时重新挂上后台等待：
         python3 scripts/k60-bus.py wait --for audio --timeout 1700
```

它的职责是**兜底**：后台 `wait` 死了（WSL 重启、会话被回收、忘了 re-arm）、或者消息被另一边
顺手读掉，30 分钟内一定能被它捞回来。

| 场景 | 用哪个 |
| --- | --- |
| 我发指派，要它立刻看到 | 后台 `wait`（秒级） |
| `wait` 链断了 / 忘了 re-arm | 定时任务（≤30 min 兜底） |
| 我发指派，等对面上机结果 | 我这边 `wait --timeout 600`，对面后台 `wait` |
| 催一条一小时没动的线 | 定时任务（它自己会看到），**不要**靠用户转述 |

### 7.3 唯一的边界：不能在我这一轮进行中打断我

后台 `wait` 的唤醒要等当前轮次结束才投递。如果某条线必须**在我这一轮进行中**插话，
那它只能是我这一侧的 subagent（`send_message` 是即时投递），代价是它不再拥有独立会话。
这个取舍不由我单方面改。

## 8. 新线接入（三行）

```bash
python3 scripts/k60-bus.py doctor                 # 看路径与各线游标
python3 scripts/k60-bus.py read --for <lane>      # 先读积压
python3 scripts/k60-bus.py send --from <lane> --to lead --body "上线"
```

`<lane>` ∈ `lead / audio / bt / cellular / power / wifi`。新增线时同步改 `scripts/k60-bus.py` 的 `LANES`（`doctor` 用它列游标）。
