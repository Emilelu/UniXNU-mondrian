# 02 · GLINK 契约 — .ko 期望的通道 / 服务 / opcode / 属性

> 目标：回答“K60 侧要提供什么，`qti_battery_charger_main_m81.ko` 才能跑起来”。
> 地址约定同 01：`.text` 内偏移直接写 `0x...`，其它节写 `节名:0x..`；行内 `\x01` 是 printk 级别字节。
> 本文的 opcode/属性细节已由 `04-PROP-MAP.md` 与 `05-OPEN-QUESTIONS.md` 细化并订正；L1 服务层契约见 `../battery/PMIC-GLINK-SERVICE.md`。

## 0. 结论摘要

1. **.ko 完全不接触 GLINK 环 / SMEM / SMP2P。** 它只调用 3 个 `pmic_glink_*` 内核符号，是标准的 **pmic_glink 客户端**（动态注册），协议消息就是 `pmic_glink_write()` 的缓冲区。
2. 客户端身份：**name=`battery_charger`**（`.rodata:0x259a`）、**id=`0x800a`**（u32）；probe 注册成功后立刻把 `bcdev->state` 置 1，等 `state_cb(1)` 到来才 queue `battery_chg_subsys_up_work`。
3. 消息 = **16 字节头 + payload**：`+0 owner(u32)`、`+4 type(u32)`、`+8 opcode(u32)`、`+0xc` 在请求侧恒 0、在响应侧是 `prop_id`。rx 侧只校验 `opcode(+8)` 与总长度，**不校验 owner/type**。
4. opcode 空间很小：`0x04`（subsys up / 订阅通知）、`0x30/0x32/0x34/0x50`（GET 属性，按域）、`0x31/0x33/0x35/0x51`（SET 属性）、`0x36`（ship mode）、`0x37`（shutdown）、`0x40`（无线固件握手）、`0x41`（固件分片，**只发不收**）、`0x42/0x43`（无线升级两阶段完成量）、`0x44`（固件版本读取），其余落进 Unknown opcode / Incorrect response length 分支。逐条语义见 `05-OPEN-QUESTIONS.md`。
5. **现有 104 字节 `k60-adsp-glink-handoff` 只覆盖 L0 传输层（GLINK 环 + SMEM + SMP2P），缺 L1 pmic_glink 服务层**（客户端注册表、按 id 路由、request/response 完成语义、通知下发）。要让此 .ko 在 K60 上工作，必须再定义 L1 契约（§7 给出最小字段集与 opcode 集）。

## 1. 事实：没有「裸 GLINK」痕迹

| 检查 | 命令 | 结果 |
|---|---|---|
| 是否有 GLINK/IPCRTR/SMEM/SMP2P 符号 | `llvm-nm -u` | **没有**任何 `glink_*`、`ipc_router_*`、`qcom_smem_*`、`smp2p_*` 符号 |
| 是否有 pmic_glink 符号 | `llvm-nm -u` | 只有 3 个：`pmic_glink_register_client`、`pmic_glink_unregister_client`、`pmic_glink_write` |
| 模块依赖 | `.modinfo` | `depends=panel_event_notifier,pmic_glink` |
| 是否出现通道名/GUID 字符串 | 扫 `.rodata`/`.data` 全部可打印串 | 没有 `IPCRTR`、`glink`、`smp2p`、`adsp`、GUID 形态串；与传输相关的只有 `.rodata:0x25aa` `Error in registering with pmic_glink %d` 和 `.rodata:0x1aa8` `Error unregistering from pmic_glink, rc=%d` |

**结论**：通道名、服务名、端口号由内核 `pmic_glink` 核心（`drivers/soc/qcom/pmic_glink.c` + `pmic_glink_rpmsg`）内部决定，**不在 .ko 里**；.ko 只认 `pmic_glink_register_client()` 返回的 client 句柄。所以仅凭 .ko 无法反推 GLINK 通道名/GUID——这一点必须在 L1 契约里另行取证（见 §8）。

## 2. 客户端注册（唯一入口）

`battery_chg_probe` 在 `0xa90–0xad4` 构造栈上 client 结构并注册：

```asm
     a90: adrp  x9, .rodata+0x259a          ; name = "battery_charger"
     a94: adrp  x10, battery_chg_callback.cfi_jt
     a98: adrp  x11, battery_chg_state_cb.cfi_jt
     a9c: mov   w23, #0x1
     aa0: mov   w8, #0x800a                 ; client id
     aa4: add   x9, x9, #0x0
     aa8: add   x10, x10, #0x0
     aac: add   x11, x11, #0x0
     ab0: add   x1, sp, #0x8                ; &client
     ab4: mov   x0, x19                     ; dev
     ab8: str   w23, [x20, #0x240]          ; bcdev->state = 1（先置 up）
     abc: str   x19, [x20]                  ; bcdev->dev = dev
     ac0: str   w8, [sp, #0x10]             ; client+0x8 = 0x800a
     ac4: str   x9, [sp, #0x8]              ; client+0x0 = "battery_charger"
     ac8: stp   x20, x10, [sp, #0x18]       ; client+0x10 = bcdev, client+0x18 = msg_cb
     acc: str   x11, [sp, #0x28]            ; client+0x20 = state_cb
     ad0: bl    pmic_glink_register_client
     ad4: cmn   x0, #0xfff                  ; 非错误指针 = 成功
     ad8: str   x0, [x20, #0xa0]            ; bcdev->client
     adc: b.lo  0xb34                       ; 成功 → strb w23,[x20,#0x618]
```

推导出的 client 结构（5 个字）：

| 偏移 | 值 | 含义 |
|---|---|---|
| `+0x00` | `.rodata:0x259a` → `battery_charger` | 客户端名（同时是 debugfs 目录名） |
| `+0x08` | `0x800a`（u32，写进 8 字节槽的低半） | 客户端 id / owner 域 |
| `+0x10` | `bcdev` | priv，回调第一个参数 |
| `+0x18` | `battery_chg_callback.cfi_jt` | 消息回调 `(priv, data, len)` |
| `+0x20` | `battery_chg_state_cb.cfi_jt` | 状态回调 `(priv, state)` |

错误处理（`0xad4–0xaec`）：返回值是错误指针时，`-517`(EPROBE_DEFER) 原样返回，否则转 `-12`(ENOMEM)。`battery_chg_remove`（`0x10a4`）逆序拆除：`device_init_wakeup(0)` → `debugfs_remove` → `class_unregister` → `unregister_reboot_notifier`×2 → `pmic_glink_unregister_client`。

## 3. 消息格式

### 3.1 16 字节头

| 偏移 | 字段 | 证据 |
|---|---|---|
| `+0x00` | `owner`（u32）：`0x800a` 或 `1` | 所有发送点；callback 不校验 |
| `+0x04` | `type`（u32）：观察值 `1`（普通请求）、`2`（subsys-up 首条） | §3.4 |
| `+0x08` | `opcode`（u32） | `0x2138: ldr w8,[x1,#8]`——callback 只从这里取 opcode |
| `+0x0c` | 请求侧恒 0；**响应侧是 `prop_id`** | 请求见 `usb_psy_set_prop` `0x2fcc`；响应见 `0x23a4`（`[msg+0xc]` 作 prop_id） |

callback 入口（`0x2130–0x2164`）：

```asm
    2130: ldrb  w8, [x0, #0x618]     ; client 已注册？
    2134: cbz   w8, 0x2470           ; 否 → 直接返回 0
    2138: ldr   w8, [x1, #0x8]       ; opcode = data[8]
    213c: mov   x20, x1
    2140: sub   w9, w8, #0x4
    2144: cmp   w9, #0x4d            ; opcode ∈ [4, 0x51]
    2148: b.hi  0x24a8               ; 越界 → 报错分支
    214c: adrp  x10, .rodata+0x9     ; 78 字节跳转表
    2154: adr   x11, 0x2168
    2158: ldrb  w12, [x10, x9]
    215c: add   x11, x11, x12, lsl #2
    2164: br    x11
```

### 3.2 请求模板（driver → peer）

`usb_psy_set_prop` 的属性请求（`0x2fb8–0x2fe8`，24 字节）：

```asm
    2fb8: mov   x9, #0x800a
    2fc0: movk  x9, #0x1, lsl #32     ; x9 = {owner=0x800a, type=1}
    2fc4: ldr   w22, [x22]
    2fc8: str   wzr, [sp, #0x14]      ; +0x14 = 0
    2fcc: stur  x8, [sp, #0xc]        ; x8 = 0x7<<32 → +0xc = 0, +0x10 = 7 (prop_id)
    2fd0: str   x9, [sp]              ; +0x00 = 0x800a, +0x04 = 1
    2fd4: ldr   w8, [x20, #0x19c]     ; bcdev->usb_get_opcode = 0x32
    2fe4: str   w8, [sp, #0x8]        ; +0x08 = opcode
    2fdc: mov   w2, #0x18             ; len = 24
    2fe8: bl    battery_chg_write
```

→ **24 字节 = `{owner, type=1, opcode, 0, prop_id, value}`**（`+0xc` 恒 0，`prop_id` 在 `+0x10`，`value` 在 `+0x14`）。

同一模板的其它长度：

| 场景 | 长度 | 内容 | 证据 |
|---|---|---|---|
| ship mode | 16 | `{0x800a, 1, 0x36, 0}` | `0x279c–0x2808`：`mov x8,#0x800a; movk x8,#1,lsl#32; mov w9,#0x36; stp x8,x9,[sp,#8]; mov w2,#0x10` |
| subsys up 首条 | 28 | `{0x800a, 2, 0x04, 0, 0, 0, 0}` | `0x11d8–0x1204`：`mov x9,#0x800a; movk x9,#2,lsl#32; mov w10,#4; str x9,[sp,#8]; str w10,[sp,#0x10]; mov w2,#0x1c` |
| 属性 GET | 24 | `{owner, 1, opcode, 0, prop_id, 0}` | `battery_psy_get_prop` / `usb_psy_get_prop` 同模板 |
| 无线固件头 | 116 | `0x74` 字节 | `wireless_chip_fw_store` `0xacf8`（`mov w2,#0x74`） |
| 无线固件分块 | 148 | `0x94` 字节 | `wls_bin_store` `0xade4`（`mov w2,#0x94`） |
| 无线调试透传 | 220 | `0xdc` 字节 | `wls_debug_store` `0xbb28`（`mov w2,#0xdc`） |

### 3.3 响应/通知模板（peer → driver）

rx 侧统一从 `data+0xc` 读 `prop_id`、`data+0x10` 读 `value`、`data+0x14` 读 `rc`：

| opcode | 期望长度 | 解析 | 证据 |
|---|---|---|---|
| `0x30` | 必须 `0x90`(144) | 拷 `data+0x10` 起 128 B → 与 `"Debug_Board"` 比较 → `bcdev+0x30e` | `0x21cc–0x2234` |
| `0x31`/`0x33`/`0x35` | `0x18` 取 rc；`0x20`/`0x34` 只 complete | `rc=data+0x14`；非 0 打印 `Error in response for opcode %#x prop_id %u, rc=%d` | `0x216c–0x21a0` |
| `0x32` | `0x18`(且 `data+0x14==0`) / `0x20` / `0x34` | `prop_id=data+0xc`（`>=13` 丢弃）；`value=data+0x10` → `usb_prop_cache[prop_id]` | `0x223c–0x23a4` |
| `0x34` | 同上 | → `wls_prop_cache[prop_id]`（7 项） | `0x2274` |
| `0x40` | `0x10` | `data+0xc==1` → `bcdev+0x30f = 1` | `0x22ac` |
| `0x42` | `0x10` | `data+0xc==1` → `complete(bcdev+0x118)` | `0x22cc` |
| `0x43` | `0x10` | `data+0xc==1` → `complete(bcdev+0xf8)` | `0x22ec` |
| `0x44` | `0x10` | `bcdev+0x314 = data+0xc` | `0x230c` |
| `0x50` | `0x34`(52)→拷 32 B 到 `+0x620`；`0x20`(32)→拷 16 B 到 `+0x628`；`0x74`(116)→拷 96 B 到 `+0x1f0` | `memcpy(…, data+0x10, …)` | `0x2324` |
| `0x51` | `0x18`(24)→读 rc；`0x20`/`0x34`→只 complete | 通用 SET 应答 | `0x2168` |
| `0x04`/`0x36`/`0x37`/`0x47` | 任意 | 只 `complete(bcdev+0xd8)` | `0x2464` |
| `0x48` | 任意 | **未识别**：打印 `Unknown opcode: %u.` 后返回 0，**不 complete** | `0x24a8` |

`0x30` 分支原文（证明 16 字节头 + 128 字节负载）：

```asm
    21cc: cmp   x2, #0x90            ; len 必须 144
    21d0: b.ne  0x234c
    21d4: ldr   x8, [x19, #0x140]    ; bcdev->debug_board_buf
    21d8: cbz   x8, 0x234c
    21dc: ldp   x10, x9, [x20, #0x20]
    21e0: ldp   x12, x11, [x20, #0x10]
    21ec: stp   x10, x9, [x8, #0x10]
    21f0: stp   x12, x11, [x8]        ; 从 data+0x10 起共拷 0x80 字节
    ...
    2224: ldr   x0, [x19, #0x140]
    2228: bl    strcmp                ; strcmp(buf, "Debug_Board")
    2230: cset  w8, eq
    2234: strb  w8, [x19, #0x30e]     ; 1 = 不是 Debug_Board
```

完成语义：**每个请求都会 `complete(&bcdev->wait)`**（`0x2464` 通用尾部），`battery_chg_write` 等到即返回 0，超时（250 jiffies）返回 `-110`。所以 L1 服务端对任何请求**必须回一条同 opcode 的消息**，否则调用线程卡 250 jiffies 并打印 `Error, timed out sending message`。

### 3.4 `type` 字段的观察值

| 值 | 出现位置 | 说明 |
|---|---|---|
| `1` | 除 subsys-up 首条外的全部请求 | 普通请求 |
| `2` | `battery_chg_subsys_up_work` 首条（opcode `0x04`，len 28） | 唯一一处，语义未定（§8） |

rx 侧从不读 `data+0`/`data+4`，所以 peer 回复时可以照抄请求的 owner/type——这是最安全的做法。

## 4. opcode 表

| opcode | 方向 | driver 期望长度 | driver 动作 | 备注 |
|---|---|---|---|---|
| `0x04` | 发→收 | 任意（发 28） | 只 complete | subsys-up 握手，type=2 |
| `0x30` | 发→收 | 收必须 144 | 存 128 B 板名 → `bcdev+0x30e` | GET battery info 类 |
| `0x31` | 发→收 | 收 24/32/52 | 读 rc 报错，无数据落盘 | SET battery prop 应答 |
| `0x32` | 发→收 | 收 24/32/52 | `prop_id` → `usb_prop_cache[]` | GET usb prop |
| `0x33` | 发→收 | 收 24/32/52 | 读 rc 报错 | SET usb prop 应答 |
| `0x34` | 发→收 | 收 24/32/52 | `prop_id` → `wls_prop_cache[]` | GET wireless prop |
| `0x35` | 发→收 | 收 24/32/52 | 读 rc 报错 | SET wireless prop 应答 |
| `0x36` | 发→收 | 发 16 | ship mode 请求 | rx 侧同 `0x04` |
| `0x40` | 发→收 | 发 24 / 收 16 | `bcdev+0x30f = (data+0xc == 1)` | 无线固件握手（版本 + 结果码），回包置放行旗标 |
| `0x41` | 只发 | 144 | 无（直接 `pmic_glink_write`，等 `bcdev+0xf8`） | 无线固件分片推送：12 B 头 + 128 B 分片 + 4 B 片序 |
| `0x42` | 只收 | 16 | `complete(bcdev+0x118)` | 通知：固件/VDM 事件 |
| `0x43` | 只收 | 16 | `complete(bcdev+0xf8)` | 通知 |
| `0x44` | 发→收 | 发 12 / 收 16 | `bcdev+0x314 = data+0xc` | 无线固件版本读取（debugfs `wireless_fw_version`） |
| `0x48` | — | — | **未识别**（主跳转表落默认项） | 不存在；`0x47` 才是「只 complete」 |
| `0x50` | 发→收 | 收 52 → 拷 32 B 到 `+0x620`；收 32 → 拷 16 B 到 `+0x628`；收 116 → 拷 96 B 到 `+0x1f0` | GET xiaomi prop（187 项，运行期填充） |
| `0x51` | 发→收 | 收 24 → 读 rc；收 32/52 → 只 complete | SET xiaomi prop 应答（走通用 `0x2168` 分支） |
| 其它 | — | — | `.rodata:0x24b0` `Unknown opcode: %u`、`.rodata:0xa1c` `Incorrect response length %zu for opcode %#x` | 默认分支 |

跳转表在 `.rodata:0x9`（78 字节，索引 `opcode-4`，目标 = `0x2168 + byte*4`），逐项换算见 03 §4。

## 5. 属性（prop_id）空间

probe 为四个域各建一份 `{只读映射表指针, kmalloc 运行时副本, 条目数, GET opcode, SET opcode}`：

| 域 | map 位置 | 条目数 | GET | SET | 运行时副本 |
|---|---|---|---|---|---|
| battery | `.rodata:0x2d68` | 25 | `0x30` | `0x31` | `bcdev+0x158` |
| usb | `.rodata:0x2dcc` | 13 | `0x32` | `0x33` | `bcdev+0x190` |
| wireless | `.rodata:0x2e00` | 7 | `0x34` | `0x35` | `bcdev+0x1c8` |
| xiaomi | `.rodata:0x2e1c` | 187 | `0x50` | `0x51` | `bcdev+0x200` |

`battery_prop_map`（25 个 u32，按 wire prop_id 顺序）：

```
0x00 0x02 0x03 0x01 0x2e 0x00 0x0e 0x0c 0x08 0x11 0x21 0x22 0x1d
0x33 0x06 0x1c 0x07 0x16 0x18 0x48 0x3e 0x3c 0x00 0x14 0x15
```

`usb_prop_map`（13 项）：`0x04 0x0c 0x08 0x11 0x10 0x25 0x00 0x40 0x00 0x00 0x33 0x00 0x00`

`wls_prop_map`（7 项）：`0x04 0x0c 0x08 0x11 0x10 0x00 0x03`

`xm_prop_map`（187 项）：`.rodata` 内全 0，运行时由 `0x50/0x51` 响应填充。

这些值是 `enum power_supply_property` 的排序索引（`battery_props`/`usb_props`/`wls_props` 数组下标），即“wire prop_id → psy 属性枚举”的映射。服务端按 `prop_id` 回填 `value`，driver 就写进 `bcdev->*_prop_cache[prop_id]`，再由 `*_psy_get_prop` 交出去。

## 6. 与 `docs/research/battery/GLINK-HANDOFF.md` 的 104 字节契约对比

### 6.1 两层模型

```
┌──────── 本 .ko（Linux 5.10 GKI，pmic_glink 客户端）────────┐
│ power_supply / debugfs / 状态机 → battery_chg_write()      │
│                                  └→ pmic_glink_write(...)  │  ← L1 服务层（缺口）
└────────────────────────────────────────────────────────────┘
              ▲ client 注册 / 按 id 路由 / 完成通知
┌──────────── pmic_glink 核心（内核内建）────────────┐
│ 服务名、通道、GUID、端口号由这一层决定，.ko 里没有  │
└────────────────────────────────────────────────────┘
              ▲ GLINK 报文（desc / tx / rx 环）
┌──── 104 B k60-adsp-glink-handoff（现有契约）────┐
│ flags / epoch / smem / adsp / desc+tx+rx / smp2p │
└──────────────────────────────────────────────────┘
```

### 6.2 逐项对照

| 能力 | 104 B handoff 覆盖 | 说明 |
|---|---|---|
| SMEM 分区与可写区间 | ✅ `smem_base/smem_bytes`（`usable = smem_bytes-4096`） | L0 |
| GLINK desc/tx/rx 三环 | ✅ `desc_offset/desc_bytes/tx_*/rx_*` | L0 |
| 每端 FIFO 头尾 | ✅ `host_tx_head/host_rx_tail`（新会话必须为 0） | L0 |
| 远端存活/重启 | ✅ `epoch`、`remote_pid=2`、`smp2p_item`、`remote_restart_flag` | L0 |
| **通道名 / 服务名 / GUID / 端口** | ❌ | .ko 内不存在，需另取证 |
| **客户端注册表（name/id → 回调）** | ❌ | 需实现 `pmic_glink_register_client` 的服务端语义 |
| **按 client id 路由上行报文** | ❌ | driver 期望 id=`0x800a` 的报文只给它 |
| **opcode / prop_id 语义** | ❌ | §4/§5 就是 L1 契约本体 |
| **请求-响应配对（completion + 250 jiffies）** | ❌ | 每请求必须回同 opcode 消息 |
| **主动通知（0x40/0x42/0x43/0x44/0x51）** | ❌ | 电池状态变化靠它驱动 |

### 6.3 结论（Lead 应发布的 handoff）

1. **现有 104 字节契约不用改、也不该删**：它正确描述了 L0（GLINK 环 + SMEM + SMP2P），`K60Battery`/`K60PmicGlink` 依赖它。
2. **但它不够**：只到“能收发字节”，没有“这些字节表示什么”。若 K60 侧真跑这版 .ko，缺 L1 会直接表现为：`pmic_glink_register_client` 无处实现 → probe 失败（`.rodata:0x25aa`）；即便注册成功，`battery_chg_subsys_up_work` 的 opcode `0x04` 无人应答 → 250 jiffies 超时 `-110`，之后所有属性读都是空缓存。
3. **建议新增第二份契约**（如 `docs/research/battery/PMIC-GLINK-SERVICE.md`，配一个 `k60-adsp-pmic-glink-handoff` lease），至少包含：
   - 服务/通道标识：pmic_glink 在 GLINK 上的通道名或 IPCRTR 端口号；
   - 客户端表：`{id(u32), name(char[32]), msg_cb, state_cb, priv}`，宿主侧注册、K60 侧按 `id` 路由；
   - 状态通告：`state_cb(1)` 的时机（服务端就绪 / 重启后重放）；
   - 完成语义：请求 → 同 opcode 响应 → `complete()`；250 jiffies 是 driver 侧硬编码；
   - 报文上限：`.ko` 最大发送 220 B（`wls_debug_store`），`0x30` 收 144 B，`0x51` 收 52 B → 建议 L0 单帧上限 ≥ 256 B。
4. **两条落地路线**（Lead 决策，本文不定）：
   - **A** 实现 pmic_glink 兼容服务端（真 GLINK/IPCRTR），原版 .ko 原样跑；需要 §8 的通道/GUID 取证。
   - **B** 在 `drivers/PongPower/K60PmicGlink.cpp` 直接提供 `pmic_glink_register_client/write/unregister_client` 三个符号 + 一个“假 ADSP 电池后端”（数据来自 K60 的 SMB/PMIC），绕开 GLINK 环。路线 B 的契约就是本文 §3–§5。

## 7. 最小可工作服务端（L1）

按 probe 的真实时序：

1. `pmic_glink_register_client(dev, {name="battery_charger", id=0x800a, priv, msg_cb, state_cb})` 必须返回非错误指针。
2. 注册成功后调用 `state_cb(priv, 1)` → driver queue `battery_chg_subsys_up_work`。
3. 对 `{0x800a, 2, 0x04, 0, 0, 0, 0}`（28 B）回一条 `opcode=0x04` 的消息（长度任意，建议 16/24 B）→ 解除首次等待。
4. 之后每条请求都回同 opcode 的消息，字段按 §3.3：
   - `0x30` → 144 B（`+0x10` 起 128 B 板名串，例如真实板名或 `"Debug_Board"`）；
   - `0x32`/`0x34` → 24 B `{owner,type,opcode,prop_id,value,rc=0}`；
   - `0x31`/`0x33`/`0x35`/`0x50` → 24 B（`+0xc=prop_id`、`+0x10=value`、`+0x14=0`）；
   - `0x51` → 52 B 或 32 B（`+0x10` 起 32/16 B 负载）；
   - `0x36`（ship mode）→ 16 B（保证 `+0x1f` 不置位）。
5. 主动通知：`0x40`（`+0xc=1`）、`0x42`/`0x43`（解除固件/VDM 等待）、`0x44`（`+0xc=<值>` → `bcdev+0x314`）、`0x51`（大块）。
6. 断开/重启：`state_cb(0)` 与 `pmic_glink_unregister_client` 要能重入（driver 只在 remove 里反注册）。

最小可用子集（能让 `battery_psy` 读出非零数据）：`0x04` → `0x30` → `0x32`（usb 7 项）→ `0x34`（wireless 7 项）→ `0x50`（xiaomi 关键项）→ 周期性 `0x40/0x42/0x43/0x44`。

## 8. 未决问题

1. ~~头第 4 字不对称~~ → 已在 `05-OPEN-QUESTIONS.md` §1 结案：请求 `+0xc` 是上游 `struct qcom_battmgr_property_request` 里的 `__le32 battery` 槽位（单电池恒 0），`+0x10` 才是 **map 下标**；响应 `+0xc` 直接是下标。不对称是协议设计，不是解析错误。
2. ~~`type` 语义未知~~ → 已结案：`1` = `PMIC_GLINK_REQ_RESP`（所有属性 GET/SET 与 0x40/0x41/0x44/ship mode/shutdown），`2` = `PMIC_GLINK_NOTIFY`（订阅 `{0x800a,2,0x04,…}` 28 B 与 subsys-up），与上游 `qcom_battmgr_enable_worker()` 逐字节一致（`05-OPEN-QUESTIONS.md` §3）。
3. **通道名/服务名/GUID/端口** 不在 .ko 内——但已在 ADSP 固件分片 `adsp.b14`/`adsp.b17` 里找到 `PMIC_RTR_ADSP_APPS`、`/dev/ipc_router`、`IPCRTR_RDR`、`pmic_glink.c` 的日志串，说明服务端在 ADSP 侧、通道名即 `PMIC_RTR_ADSP_APPS`。仍缺 AP 侧 ipc_router 端口号与 ADSP 侧 battery 服务的 opcode 表。详见 `docs/research/battery/PMIC-GLINK-SERVICE.md` §5。
4. ~~`0x37`、`0x48` 语义未知~~ → 已在 `05-OPEN-QUESTIONS.md` 结案：`0x37` 是 **shutdown 命令**（`battery_chg_shutdown` 0x2830 发 12 B，仅重启时发）；`0x48` **不是 rx opcode**，主跳转表落默认项 `0x24a8`（`Unknown opcode: %u.`），「只 complete」的是 `0x47`。`0x40/0x42/0x43/0x44/0x51` 也已逐条结案。
5. ~~`prop_id → psy 属性` 方向待验证~~ → 已由 `04-PROP-MAP.md` 钉死：**wire prop_id = 该域 map 数组的下标**（决定性证据是 `battery_psy_set_prop` property `0x21` 分支把常量 10 写进 `+0x10`，而 `battery_prop_map[10] = 0x21`），map 里的值才是 `enum power_supply_property`。
6. 若要走路线 A，K60 内核必须提供 `vermagic 5.10.160-gki` 对应的 `pmic_glink`/`power_supply` 符号（含 `__versions` CRC），否则只能走路线 B。

## 9. 复现命令

```bash
KO=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
llvm-nm -u "$KO"                                   # 85 个未定义符号，确认只有 3 个 pmic_glink_*
llvm-readelf -p .modinfo "$KO"                     # depends=panel_event_notifier,pmic_glink
llvm-objdump -dr --start-address=0xa90 --stop-address=0xae0 "$KO"    # client 注册
llvm-objdump -dr --start-address=0x2130 --stop-address=0x2170 "$KO"  # callback 头 + 跳转表
llvm-objdump -dr --start-address=0x21c8 --stop-address=0x2240 "$KO"  # opcode 0x30
llvm-objdump -dr --start-address=0x2fb8 --stop-address=0x2ff0 "$KO"  # 24B 请求模板
llvm-objdump -dr --start-address=0x279c --stop-address=0x280c "$KO"  # ship mode 16B
llvm-objdump -dr --start-address=0x11d8 --stop-address=0x1208 "$KO"  # subsys up 28B
llvm-objdump -s -j .rodata "$KO" | head -40         # 跳转表字节 .rodata+0x9
```
