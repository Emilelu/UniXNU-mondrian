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

1. **它不负责唤醒任何人**。唤醒由 `dsh-agent-message` 直接投递进目标会话完成（2026-11-20 实测：offline 的 audio 会话被投递后立刻 `claimed` 并开始跑）。总线的职责见 §7。
2. **不是身份认证**。`--from` 是自我声明，写错了没人拦。签名不值当，纪律补：每条线只用自己的名字。
3. **不持久保存历史决策**。总线是运行时状态，不是归档：需要留档的结论进 `docs/`，总线里的讨论可以被清理。
4. **不跨机**。同一个 `E:` 盘，同一台机器。

清理：`E:\k60-work\bus\bus.jsonl` 可以直接删（游标会让每条线从头读，所以删之前先 `read` 一遍或把游标一起删）。

## 6. 备选方案与不选它的理由

| 方案 | 实时性 | 代价 | 结论 |
| --- | --- | --- | --- |
| reply md（现状） | 靠人转达 | 覆盖丢消息 | 只留长文 |
| **本总线（追加+游标）** | 轮次内即时（`read`/`wait` 阻塞即到） | 无 | **采用**：审计 + 广播（唤醒交给 agent-message） |
| 本地 broker（127.0.0.1 长轮询/推送） | 亚秒推送 | 要有人起守护进程、端口、崩溃恢复 | 不需要：agent-message 已经提供了推送 |
| **`send_agent_message`（dsh-agent-message）** | **真推送，可唤醒 offline 会话** | 一次一个 session id | **采用**：指派与 ack |
| git push/fetch 传消息 | 分钟级 | 污染历史、冲突 | 不用 |

「真推送」现在是 `send_agent_message` 的职责，不需要把几条线改成 subagent。

## 7. 职责划分（2026-11-20 晚修订：唤醒交给 agent-message）

用户装了 `dsh-agent-message` 之后，本文件原先设计的两套唤醒机制**都作废**：

| 曾经的设计 | 为什么不需要了 |
| --- | --- |
| 后台 `bus.py wait` + 收尾 re-arm 链 | agent-message 直接把消息投进目标会话并给它一轮，不需要轮询、不需要链；链本身还脆（我的 watcher 被杀过一次就断了） |
| 每 30 分钟总线巡检定时任务 | 同上；留着只会变成「登记了但没在用」——P-251 正是这个形状 |
| `schedule_create` 只能在 `this_session` 生效 | 现在无关：投递靠 session id，`list_peer_agents` 一次就能取到五条线的 id |

现行分工：

| 用途 | 工具 |
| --- | --- |
| 指派、裁决、ack、催办 | **`send_agent_message`**（即时、双向、能唤醒 offline 会话；配合 `check_delivery` 看 claimed/discarded） |
| 决策落盘、广播一条打全体 | **总线** `python3 scripts/k60-bus.py send --from lead --to '*' ...`（追加一行，可 grep） |
| 「谁积压了、哪条线没读」的全局视图 | `python3 scripts/k60-bus.py doctor` / `threads --for <lane>` |
| 长报告正文 | reply md |

保留总线而不用消息替代的三个理由：

1. **审计**。`send_agent_message` 的投递不落盘到仓库，事后无法回答「谁在什么时候被谁指派了什么」；`E:\k60-work\bus\bus.jsonl` 是可 grep 的文本。
2. **广播**。`to` 只接受一个 session id，发五条线要发五次，而广播是「同一条决策要所有线知道」的常见形状。
3. **session id 会变**。新开会话就是新 id，总线不依赖它，换会话也照样通。

### 7.1 仍然成立的边界

`send_agent_message` 的 `mode` 决定打扰程度：`followup`（默认，排一轮新工作）、`inject`（在下一步补上下文）、
`steer`（在最近可处理边界介入）。**默认用 `followup`**：`inject`/`steer` 会打断对方正在做的事，
只在「必须立刻停手」时用。`claimed` 只表示对方认领了消息，不代表完成——要结论就明说「回我一行 ack」。

## 8. 新线接入（三行）

```bash
python3 scripts/k60-bus.py doctor                 # 看路径与各线游标
python3 scripts/k60-bus.py read --for <lane>      # 先读积压
python3 scripts/k60-bus.py send --from <lane> --to lead --body "上线"
```

`<lane>` ∈ `lead / audio / bt / cellular / power / wifi`。新增线时同步改 `scripts/k60-bus.py` 的 `LANES`（`doctor` 用它列游标）。
