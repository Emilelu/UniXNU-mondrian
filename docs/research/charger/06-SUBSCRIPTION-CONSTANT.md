# 06 — 订阅应答常量定值（`K60_BATTERY_NOTIFY_REPLY_TYPE` / `K60_BATTERY_NOTIFY_REPLY_BYTES`）

> 目标：把仓库里两个一直为 0 的生成常量定死，交给 handoff 发布者（touch agent）使用。
> 结论：**`TYPE = 1`、`BYTES = 16`**，证据来自 K60 ADSP 固件自身的 opcode-0x04 handler，不是从 Linux 的宽松 ACK 反推。
> 取证件：`/mnt/e/k60-work/firmware/adsp/adsp.b14`（3,167,652 B，sha256 `2284e98961fc542ca215a4e94c7ad00269f03d0a2651a5d7c2cf5329c8ade00d`），
> 以及 `/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko`（247,776 B，BuildID `e852b83c589f773d7cb09e6793ac59fd33086c58`）。
> ADSP 段 14 的 `p_vaddr = 0x60000000`，**文件偏移 = link 地址 − 0x60000000**；下文所有 ADSP 地址都是 link 地址。

## 0. 结案摘要

| 常量 | 定值 | 唯一依据 | 消费者接受条件 |
| --- | --- | --- | --- |
| `K60_BATTERY_NOTIFY_REPLY_TYPE` | `1`（REQ_RESP） | ADSP `0x601559cc: memw(r2+#0x4) = #0x1` | `K60Battmgr.c:51` 白名单 `{1,2}` |
| `K60_BATTERY_NOTIFY_REPLY_BYTES` | `16` | ADSP `0x601559f0: r3 = #0x10`（帧总长） | `K60Battmgr.c:52` 白名单 `{12,16,24,28}` |

订阅**请求**保持原样不变：28 B `{owner=0x800a, type=2, opcode=4, 四个零字}`（`K60Battmgr.c:80-85`、`.ko 0x11d8-0x1204`）。
变的只有**应答**的形状：16 B、type 1、`+0xc` 是 result 字（成功为 0，参数缺失为 `0x206`）。

## 1. 为什么这个值必须"定死"而不是"猜"

三处消费者，各自的严格程度不同：

1. **仓库 codec**（最严）`drivers/PongPower/K60Battmgr.c:47-56`：
   `k60_battmgr_init()` 只在 `(reply_type == 1 || reply_type == 2) && reply_bytes ∈ {12,16,24,28}` 时保存这对值，否则保持 0。
   而 `:63-68` 的 `k60_battmgr_channel_up()` 用 `b->subscribe_due = b->notify_reply_bytes != 0` 决定是否订阅 —— **常量为 0 就等于永不订阅，只剩属性轮询**。
   即使订阅了，`:162-171` 的 ACK 校验还要求 `bytes == notify_reply_bytes && type == notify_reply_type`，并且 `+0xc` 起逐 4 字必须全 0。
2. **生成器**（旧版）`scripts/build-k60-physical-battery.py` 的 `qualification()`：没有 `--notification-wire` 时返回 `(0, 0)`，于是头文件里写出 `0u / 0u` 加一句 "zero until capture"。结果是整条订阅路径在产物里被静默关掉。
3. **上游 Linux**（最松）`drivers_power_supply_qcom_battmgr.c:1000-1011`：`payload_len = len - sizeof(struct pmic_glink_hdr)`，只要 `payload_len >= 4`（总长 ≥ 16）就接受，`case BATTMGR_REQUEST_NOTIFICATION: battmgr->error = 0` —— **不读 type、不读长度、不读 payload**。
   所以"上游能跑"不能证明任何 type/长度取值，仓库 `K60Battmgr.h` 旧注释写的 "must be measured, not inferred from Linux's loose ACK" 是对的。

既然不能猜、又必须给值，唯一正当的取证方向是**问服务端**：ADSP 固件里谁在回 opcode 4，它组的是什么帧。

## 2. ADSP 固件侧证据（逐指令）

### 2.1 opcode 分发器 `0x60155570`

```
60155598:  r0 = add(r30,#-0x4)                 ; 出参：消息指针
6015559c:  r1 = add(r30,#-0x10)                ; 出参：长度
601555a0:  call 0x601584f0                     ; 收一条 glink 消息
601555d8:  r2 = memw(r2+#0x0)                  ; owner
601555e0:  p0 = cmp.eq(r2,##0x800a)            ; 只处理 battery_charger
601555f4:  r2 = memw(r2+#0x8)                  ; opcode
601555f8:  p0 = cmp.gtu(r2,#0x51)              ; 越界 → 默认分支 0x60157e4c
6015560c:  r3 = memw(r2<<#0x2+##0x602bfc28)    ; 4 字节绝对地址跳转表
60155610:  jumpr r3
```

跳转表 @ `0x602bfc28` 前 6 项实测（python 直读 b14）：

| index（opcode） | 原始 4 字节 | 目标 |
| --- | --- | --- |
| 0 | `14561560` | `0x60155614` |
| 1 | `d0561560` | `0x601556d0` |
| 2 | `4c7e1560` | `0x60157e4c`（默认） |
| 3 | `2c581560` | `0x6015582c` |
| **4** | `10591560` | **`0x60155910`** |
| 5 | `185a1560` | `0x60155a18` |

### 2.2 opcode 4 handler `0x60155910`（全文关键段）

```
60155910:  r2 = memw(r30+#-0x4)                ; 入参：消息
6015591c:  p0 = cmp.eq(r2,#0x0)
60155920:  if (p0) jump:nt 0x60155a14           ; 空消息 → 直接返回，不回包
60155928:  r2 = memw(##0x603caff8)             ; 应答缓冲（全局）
60155940:  r0 = #0x10                          ; 只申请 16 字节
60155944:  call 0x6014e8d0                     ; 分配
6015594c:  memw(##0x603caff8) = r0
60155980:  r2 = memw(r2+#0x10)                 ; 请求 +0x10 → 栈 r30-0x54
6015598c:  r2 = memw(r2+#0x14)                 ; 请求 +0x14 → 栈 r30-0x50
60155998:  r2 = memw(r2+#0x18)                 ; 请求 +0x18 → 栈 r30-0x4c
601559a0:  r0 = add(r30,#-0x58)                ; 三个字组成的入参结构
601559a4:  call 0x6024ede0                     ; 使能通知（返回 result）
601559b0:  memw(r2+#0xc) = r0                  ; ★ 应答 +0xc = result
601559c0:  memw(r2+#0x0) = ##0x800a            ; ★ 应答 +0x0 = owner
601559cc:  memw(r2+#0x4) = #0x1                ; ★ 应答 +0x4 = type 1
601559d8:  memw(r2+#0x8) = #0x4                ; ★ 应答 +0x8 = opcode 4（回显）
601559e0:  r0 = memw(##0x603cafe0)             ; glink 上下文
601559e8:  r2 = memw(##0x603caff8)             ; 缓冲
601559ec:  r1 = #0x0
601559f0:  r3 = #0x10                          ; ★ 帧总长 16
601559f4:  call 0x60154f80                     ; 发送
60155a04:  if (p0) jump:nt 0x60155a10           ; 成败都走同一条收尾
60155a10:  jump 0x60155a14 → 0x60157e50 → 0x601584d4
```

**四字节原始锚点**（python 直读 b14，偏移 = 地址 − 0x60000000）：

| 地址 | 文件偏移 | 字节 | 指令 |
| --- | --- | --- | --- |
| `0x601559a4` | `0x1559a4` | `1eca1f5a` | `call 0x6024ede0` |
| `0x601559b0` | `0x1559b0` | `03c082a1` | `memw(r2+#0xc) = r0` |
| `0x601559c0` | `0x1559c0` | `0ac0423c` | `memw(r2+#0x0) = ##0x800a` |
| `0x601559cc` | `0x1559cc` | `81c0423c` | `memw(r2+#0x4) = #0x1` |
| `0x601559d8` | `0x1559d8` | `04c1423c` | `memw(r2+#0x8) = #0x4` |
| `0x601559f0` | `0x1559f0` | `03c20078` | `r3 = #0x10` |
| `0x601559f4` | `0x1559f4` | `c6faff5b` | `call 0x60154f80` |

### 2.3 result 字：只可能是 0 或 `0x206`

`0x6024ede0`（opcode 4 专用子处理）：

- 入参指针为 0 → `memh(r2+#0x0) = ##0x206`，返回 `0x206`；
- 正常路径 → `memw(##0x60329ee0)` 取状态块、`memb(r2+#0x3a8) = 1`，把入参 `+0xc/+0x8/+0x4` 存进状态块 `+0x2a8/+0x2a4/+0x2a0`；
- 尾部 `6024ef08: r2 = memuh(r30-0xa)`、`6024ef14: r0 = memh(r30-0x2)` → 成功返回 0。

对仓库的意义：ACK 的 `+0xc` **不是** payload，是错误码。仓库 `K60Battmgr.c:167-168` 对 `+0xc` 起逐 4 字判零，恰好把"成功"与"远端拒绝"分开：成功置 `subscribed = 1`，非 0 记一次 `errors` 并释放 flight。

### 2.4 发送包装 `0x60154f80` 确认 r3 就是长度

```
60154f80:  allocframe(#0x20)
60154f84:  memw(r30+#-0x8) = r0                ; ctx
60154f88:  memw(r30+#-0xc) = r1                ; buf
60154f8c:  memw(r30+#-0x10) = r2
60154f90:  memw(r30+#-0x14) = r3               ; len
60154fa8:  r2 = memb(##0x603cafe4)             ; 通道门控
60154fb4:  if (p0) jump:nt 0x60155058           ; 门控开 → 真发
60155058:  r0 = memw(r30+#-0x8)
6015505c:  r1 = memw(r30+#-0xc)
60155060:  r2 = memw(r30+#-0x10)
60155064:  r3 = memw(r30+#-0x14)               ; len 原样透传
60155068:  r4 = #0x1
6015506c:  call 0x601ee0c8                     ; glink send
6015507c:  dealloc_return
```

内层 `0x601ee0c8`：`r6 = r1; r5 = r2`（buf/len），`r7 = memw(r0+#0x4c)`（客户端句柄里的通道），`call 0x60007128`（互斥），`r3:2 = combine(r7,##0x104)` 后入队 —— 语义等价于 `send(handle, buf, len)`，与 `r3` 是长度一致。

全固件 `call 0x60154f80` 共 52 处，`r3 = #0x10` 字面量 49 处；各 handler 的应答长度与"12 B 头 + 若干字 payload"一一对应（属性 GET 24 B、订阅应答 16 B、无线 16 B、`0x50` 24 B 等）。

## 3. 穷举反证：`0x800a` 的 type 2 帧绝不是订阅应答

python 扫描全部 `memw(r2+#0x0) = ##0x800a` 组包点（每条向后看 16 条指令窗口）：

```
total 0x800a builders: 30
type histogram: Counter({1: 27, None: 2, 2: 1})
type2 rows: [('60158884', 2, 7, None)]
```

- **唯一** type=2 的 `0x800a` 组包点是 `0x60158884`：`+0x4 = #0x2`、`+0x8 = #0x7`、`+0xc = memub(r30-0x3)`、`r3 = #0x10` → `call 0x60154f80`。
  这是**主动通知**（opcode 7），与订阅应答无关；仓库 `K60Battmgr.c:151-160` 正是按 `type==2 && bytes==16 && opcode==7` 收通知，两边对齐。
- 另两处没有 type 字的（`0x60158ca4` opcode `0x43`、`0x60158e24` opcode `0x42`）把 owner/opcode 写到栈帧 `r30-0x20/-0x1c/-0x18`，由别的路径发送，不是应答。
- 通知族帧的 owner 是 `0x800b` / `0x800c`（`0x60158660`：owner `0x800b`、type 2、opcode `0x13`、len `0x18`；`0x60158788`：owner `0x800c`、type 2、opcode `(0x16 | v<<16)`、copy 16 B、len `0x20`）。
- 22 个 handler 的应答组包模式完全一致（先 `+0x4 = #0x1`，再回显 opcode）：`0x60155668 / 55740 / 558b8 / 559c0 / 55a7c / 55bb0 / 55c5c / 55e20 / 55f68 / 56060 / 5612c / 5620c / 56318 / 5641c / 56528 / 566d4 / 56f04 / 57434 / 57558 / 57748 / 57840 / 579bc / 57df8`。

→ **`owner=0x800a` 的出向帧里，只有 type 1 是应答；type 2 只用于 opcode 7 通知。**

## 4. 四方对照

| 来源 | 对 opcode 4 应答的处理 | 与本定值是否冲突 |
| --- | --- | --- |
| **K60 ADSP 固件** | 组 `{0x800a, 1, 4, result}`，`r3 = 0x10` | —— 定值来源 |
| **`qti_battery_charger_main_m81.ko`** | `battery_chg_callback`（`0x211c`）跳转表 index 0 → `0x2464`，只 `add x0,x19,#0xd8; bl complete`，不读 type/长度/payload | 不冲突（零校验，任何形状都唤醒等待者） |
| **上游 Linux `qcom_battmgr`** | `payload_len >= 4` 即收，`battmgr->error = 0` | 不冲突（16 ≥ 16 下限） |
| **ShengBattmgr 参考实现** | `type == TYPE_REQUEST || type == TYPE_NOTIFY` 都接受，不校验长度 | 不冲突（type 1 在集合内） |
| **仓库 `K60Battmgr.c`** | 要求 `bytes == 16 && type == 1` 且 `+0xc` 起全 0 | 恰好匹配 |

`.ko` 的零校验是**必须解释清楚**的一点：它说明"厂商驱动能跑"并不能证明 type/长度，因为 `.ko` 根本不看。真正定义 wire 形状的是固件（发）和我们的 codec（收）。

## 5. 为什么 (1, 16) 是唯一自洽值

仓库 codec 的 ACK 判据是**全等**而非"至少"：`bytes != notify_reply_bytes` 或 `type != notify_reply_type` 就直接 `ignored++` 返回（`K60Battmgr.c:165-166`）。而 `k60_battmgr_timeout()`（`:194-200`）对任何未完成的 flight 都是**立即中毒**：

```c
if (b->flight == FLIGHT_NONE) return;
b->timeouts++; b->poisoned = 1;
b->valid = b->fresh = b->completed = b->last_fresh = 0;
b->cycle_active = 0;
```

也就是说：如果常量取错，第一个订阅 ACK 会被忽略 → 订阅 flight 超时 → 整个通道中毒（协议无 transaction id，只能靠重开通道恢复）→ 连属性轮询也一起死。所以"取个差不多的值试试"在这里不是保守做法，而是**直接制造挂死**。

候选矩阵（固件只发一种形状，其余都在等一个永远不会来的包）：

| 候选 | 固件是否会发 | 后果 |
| --- | --- | --- |
| **`(1, 16)`** | 是（`0x60155910`） | 订阅成功，进入属性轮询 |
| `(2, 16)` | 否（`0x800a` 的 type 2 只有 opcode 7 通知） | ACK 被忽略 → 超时 → poisoned |
| `(1, 24)` / `(1, 28)` / `(1, 12)` | 否 | 同上 |
| `(0, 0)`（旧状态） | —— | 永不订阅，只剩轮询（不挂死但丢通知） |

## 6. 复现

三份取证都能离线重跑（WSL，`wsl -u root -e bash -lc '...'`）：

```bash
# 1) 反汇编 ADSP 段 14（裸段需要先包成 ELF32 Hexagon，脚本见 _scratch/charger-ko/wrap_hexagon.py）
python3 wrap_hexagon.py /mnt/e/k60-work/firmware/adsp/adsp.b14 /tmp/adsp_b14.elf 0x60000000
llvm-objdump -D --triple=hexagon /tmp/adsp_b14.elf > /tmp/adsp_b14.dis
sed -n '/^ *60155910:/,/^ *60155a14:/p' /tmp/adsp_b14.dis

# 2) 校验四字节锚点 + 跳转表
python3 -c "
import struct, hashlib
b = open('/mnt/e/k60-work/firmware/adsp/adsp.b14','rb').read()
print(len(b), hashlib.sha256(b).hexdigest())
for va in (0x601559c0,0x601559cc,0x601559d8,0x601559f0,0x601559f4):
    print(hex(va), b[va-0x60000000:va-0x60000000+4].hex())
print([hex(x) for x in struct.unpack_from('<6I', b, 0x2bfc28)])
"
# 期望：0ac0423c 81c0423c 04c1423c 03c20078 c6faff5b；表首项 0x60155614，索引 4 = 0x60155910

# 3) 跑仓库 codec 的钉死测试（不需要真机）
cd /mnt/e/hackios/k60-charger
cc -Wall -Wextra -std=c11 -o /tmp/tk60sub scripts/tests/test-k60-charger-subscription.c
/tmp/tk60sub        # 期望输出 TESTS OK 30

# 4) 跑生成器的定值路径
python3 -c "import importlib.util as u; s=u.spec_from_file_location('g','scripts/build-k60-physical-battery.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print(m.MEASURED_NOTIFY_REPLY, m.qualification(None,None,None))"
# 期望：(1, 16) 与 (0, 1, 16, None, {'source': 'adsp-opcode4-handler', ...})
```

## 7. 仓库改动

| 文件 | 改动 |
| --- | --- |
| `scripts/build-k60-physical-battery.py:27-31` | 新增 `MEASURED_NOTIFY_REPLY = (1, 16)` 与其依据注释 |
| `scripts/build-k60-physical-battery.py:222-224` | `qualification()` 默认返回实测对，`notify_evidence` 记 `source='adsp-opcode4-handler'` |
| `scripts/build-k60-physical-battery.py:241-246` | 抓包只做**确认**：`replies[0] != MEASURED_NOTIFY_REPLY` 直接 `raise ValueError('Wire capture contradicts ...')` |
| `scripts/build-k60-physical-battery.py:288-291` | 生成的头文件注释从 "Zero until ..." 改为实测说明 |
| `scripts/build-k60-physical-battery.py:9-11` | 模块 docstring 同步（订阅 ACK 不是推断值） |
| `drivers/PongPower/K60Battmgr.h:52-55` | 注释改为"来自 ADSP opcode-0x04 handler，16 B、type 1" |
| `scripts/tests/test-k60-charger-subscription.c`（新增 114 行） | 钉死配对与拒绝矩阵，30 条断言 |

生成器现在**无抓包也输出 `1u` / `16u`**，`subscription_qualified`（`:299`）因此恒为真；一旦将来真机抓到形状不同的 ACK，生成器会**报错**而不是悄悄改常量 —— 那是唯一允许推翻本定值的证据形式。

## 8. 交给 touch agent 的交接

handoff 发布者（GPT touch agent）只需要这三条：

1. **常量**：`K60_BATTERY_NOTIFY_REPLY_TYPE = 1`、`K60_BATTERY_NOTIFY_REPLY_BYTES = 16`。它们由 `scripts/build-k60-physical-battery.py` 生成到 `K60BatteryProtocol.generated.h`，消费点只有 `drivers/PongPower/K60Battery.cpp:350-351` 的 `k60_battmgr_init()`。**发布者不需要改这两个值，也不要在别处再写一份。**
2. **wire 形状**（发布者若自己组帧必须一致）：
   - 订阅请求 28 B：`owner=0x800a, type=2, opcode=4, payload=4 个零字`；
   - 订阅应答 16 B：`owner=0x800a, type=1, opcode=4, result（成功=0，参数缺失=0x206）`；
   - 通知 16 B：`owner=0x800a, type=2, opcode=7, +0xc=属性组(0x30/0x32/0x34/0x50/0x80)`；
   - 属性请求 24 B：`owner=0x800a, type=1, opcode, +0xc=0, +0x10=属性下标, +0x14=value`。
3. **失败语义**：ACK 的 `+0xc` 非 0 表示远端拒绝（ADSP 只会给 `0x206`）；任何未完成 flight 超时都会让 codec 进入 `poisoned` 状态，必须 `channel_down` + `channel_up` 重开才能恢复 —— 发布者不要在超时后继续往同一通道塞请求。

## 9. 残余风险

- 本定值**没有**真机 wire capture 佐证。它的强度来自"服务端代码怎么组包"这一手证据，而不是"我们观察到什么"。如果将来抓到 ACK 与此不符，按 §7 的机制：生成器会拒绝，本文件作废重写。
- ADSP 固件版本相关性：证据绑定 `adsp.b14` 的 sha256 `2284e989...`。换固件必须重跑 §6 的锚点校验。
- 订阅成功并不等于属性路径通：`K60Battmgr.c:172-192` 还要求属性应答 24 B / type 1 / opcode 与属性下标回显一致，model 字段另需 144 B。这部分与本次常量无关，见 `04-PROP-MAP.md`。
