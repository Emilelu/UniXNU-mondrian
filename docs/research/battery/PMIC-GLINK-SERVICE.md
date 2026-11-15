# pmic_glink 服务层契约（L1）

> 本文回答一个问题：`qti_battery_charger_main_m81.ko` 与 `drivers/PongPower/` 之间缺的到底是什么。
> 结论：缺的不是 SMEM 分配器、不是 PAS1 装载器、也不是编解码器——这三样仓库里都已经有了；
> 缺的是「把它们串起来的调用者」，以及「ADSP 侧 pmic_glink 服务端的固件装载」。
>
> 上游参考实现（Linux `qcom_battmgr`）与实物模块（`.ko`）的字段、opcode、帧长在本文逐条对齐，
> 每条都附可复现命令与原始输出片段。

---

## 0. 结论摘要

1. **两层模型**：104 字节 `k60-adsp-glink-handoff` 只描述 L0（SMEM 分区 + GLINK 环 + SMP2P 就绪位）。
   `.ko` 走的是 L1：`pmic_glink` 服务层。两层互不替代，104 字节 blob **不改也不删**。
2. **L1 的服务端在 ADSP 固件里**，不在 AP 内核里。ADSP 固件 `adsp.b14`/`adsp.b17` 里能直接找到
   `PMIC_RTR_ADSP_APPS`、`/dev/ipc_router`、`pmic_glink.c` 与 `xm_*` 系列属性处理函数的错误串。
3. **客户端参数已确定**：client name = `battery_charger`（`.rodata+0x259a`），client id = `0x800a`
   （= 上游 `PMIC_GLINK_OWNER_BATTMGR` = 32778）。
4. **仓库里已实现 L1 编解码器**：`K60Battmgr.c`（254 行）已按 24 B 请求 / 16 B 通知 / 24 B 响应 /
   16+128 B Model 特例完整编解码，并被 `K60Battery.cpp` 接入 IOPMPowerSource。
5. **两处真实缺口**（不是「没有代码」，是「代码没被接上」）：
   - **缺口 A**：没有任何内核代码调用 `k60_handoff_build()` 并把结果发布到 `/chosen` 的
     `k60-adsp-glink-handoff` 属性；`K60Battery.cpp:426` 在消费这个属性，但生产者缺位。
   - **缺口 B**：`K60_BATTERY_NOTIFY_REPLY_TYPE/BYTES` 生成值恒为 `0`，导致 `subscribe_due=0`，
     当前实现**永不发订阅请求**，因此永远收不到 `0x07` 通知。
6. **「头第 4 字不对称」已解**（原列为未决问题）：请求帧 `{owner,type,opcode,battery=0,property,value}`
   里 `+0xc` 是 `battery` 槽位、`+0x10` 才是 `property`；响应帧 `{owner,type,opcode,property,value,result}`
   里 `+0xc` 就是 `property`。两者不是同一个字段，不存在不对称。

---

## 1. 两层模型

```
      ┌─────────────────────────── AP 侧（XNU）───────────────────────────┐
 L1   │ K60Battery.cpp  ──►  K60Battmgr.c  ──►  K60PmicGlink.cpp          │
      │  (IOPMPowerSource)   (24/16/28 B 帧)    (PMIC_RTR_ADSP_APPS 通道)  │
      └──────────────────────────────┬───────────────────────────────────┘
                                     │ GLINK FIFO（tx/rx 环，SMEM 里）
 L0   │ K60PmicGlink.cpp discover():  k60_smem_find(desc/tx/rx/smp2p)     │
      │ K60HandoffBuild.c:            k60_smem_alloc + 104 B blob         │
      │ K60AdspPas.c / K60AdspBoot.c: AUTH_AND_RESET / INIT_IMAGE / ...   │
      └──────────────────────────────┬───────────────────────────────────┘
                                     │ SMC (PAS1)
                               ┌─────┴─────┐
                               │  ADSP FW  │  pmic_glink 服务端（adsp.b14/b17）
                               └───────────┘
```

- **L0（`docs/research/battery/GLINK-HANDOFF.md`）**：104 字节 blob 的逐字段校验。它保证「SMEM 分区里
  有 32 B 的 GLINK desc、tx/rx 环、20–340 B 的 SMP2P 项，且 host 侧的 head/tail 初始为 0」。
- **L1（本文）**：跑在这条通道之上的 12 B 头 + 业务负载。L0 通只能说明「管道打通了」，
  不说明「对端会回答 `0x30` 属性请求」。
- 因此：**L1 需要一份新契约，而不是把 104 字节改大**。改 104 字节会同时破坏已发布的
  `K60BatteryConfig.c` 解析器与 `patches/xnu/0611` 的消费方。

---

## 2. 仓库里已有的实现（全部在 git，分支 `feat/charger`）

| 组件 | 文件 | 作用 | 状态 |
|---|---|---|---|
| L1 编解码器 | `drivers/PongPower/K60Battmgr.c`（254 行）/`.h`（74 行） | 24 B 属性请求、28 B 订阅、16 B 通知、24 B 响应、16+128 B Model | 已实现，已接入 |
| 通道传输 | `drivers/PongPower/K60PmicGlink.cpp`（130 行） | `qcom_glink_channel(&native,"PMIC_RTR_ADSP_APPS",256,4,...)` | 已实现 |
| SMEM 分配 | `drivers/PongPower/K60Smem.c:113` `k60_smem_alloc()` | 从 SMEM 分区分配项（改编自 pong-power `QcomSmem.c`） | 已实现 |
| 104 B 组装 | `drivers/PongPower/K60HandoffBuild.c:33` `k60_handoff_build()` | `plan_ok()` 校验 + 逐字段写出 | 已实现，**无内核调用者** |
| PAS1 装载 | `drivers/PongPower/K60AdspPas.c`（90 行） | `AUTH_AND_RESET`/`INIT_IMAGE`/`MEM_SETUP`/`SHUTDOWN` | 已实现 |
| 启动编排 | `drivers/PongPower/K60AdspBoot.c:178` `k60_adsp_probe_from_handoff()` | 映射 ramdisk → FAT → 映射 carveout → `k60_adsp_bring_up()` | 已实现，需 boot-arg `pong_adsp` |
| 消费方 | `drivers/PongPower/K60Battery.cpp:347` `begin()` | 读 `/chosen` 属性 → 解析 → 开传输 → 发布电源 | 已实现，被上面两处缺口卡住 |

关键行号：

- `K60Battmgr.h:12` `#define K60_BATTMGR_OWNER 32778u`（= `0x800a`）
- `K60Battmgr.h:13-16` `REQUEST_BYTES 24` / `NOTIFY_BYTES 28` / `MODEL_BYTES 128`
- `K60HandoffBuild.h:14` `#define K60_HANDOFF_BYTES 104u`
- `K60BatteryConfig.h:17` `#define K60_ADSP_HANDOFF_PROPERTY "k60-adsp-glink-handoff"`
- `K60PmicGlink.cpp:84` `qcom_glink_channel(&native, "PMIC_RTR_ADSP_APPS", 256, 4, intents, &callbacks, this, 1)`
- `K60AdspBoot.c:185` `PE_parse_boot_argn("pong_adsp", &enabled, sizeof(enabled))`（默认 0，不跑）
- `patches/xnu/0614-k60-adsp-call-site.patch:13` 调 `k60_adsp_probe_from_handoff()`

---

## 3. L1 契约

### 3.1 客户端注册

`.ko` 的注册点 `0xa90–0xad4`（`battery_chg_probe` 内）：

```
$ llvm-objdump -dr --start-address=0xa90 --stop-address=0xad8 qti_battery_charger_main_m81.ko
     a90: adrp x9, ...      R_AARCH64_ADR_PREL_PG_HI21  .rodata+0x259a
     a94: adrp x10, ...     R_AARCH64_ADR_PREL_PG_HI21  battery_chg_callback....cfi_jt
     a98: adrp x11, ...     R_AARCH64_ADR_PREL_PG_HI21  battery_chg_state_cb....cfi_jt
     a9c: mov  w23, #0x1
     aa0: mov  w8, #0x800a                    ; client id
     aa4: add  x9, x9, #0x0
                            R_AARCH64_ADD_ABS_LO12_NC   .rodata+0x259a
     aa8: add  x10, x10, #0x0
                            R_AARCH64_ADD_ABS_LO12_NC   battery_chg_callback....cfi_jt
     aac: add  x11, x11, #0x0
                            R_AARCH64_ADD_ABS_LO12_NC   battery_chg_state_cb....cfi_jt
     ab0: add  x1, sp, #0x8                   ; &client（栈上）
     ab8: str  w23, [x20, #0x240]             ; bcdev->state = 1
     abc: str  x19, [x20]                     ; bcdev->dev
     ac0: str  w8,  [sp, #0x10]               ; client.id   = 0x800a
     ac4: str  x9,  [sp, #0x8]                ; client.name = "battery_charger"
     ac8: stp  x20, x10, [sp, #0x18]          ; client.priv + client.callback
     acc: str  x11, [sp, #0x28]               ; client.state_cb
     ad0: bl   ...          R_AARCH64_CALL26  pmic_glink_register_client
```

> 注意：client 结构体建在栈上（`add x1, sp, #0x8` 作为第一参数传给
> `pmic_glink_register_client`），五个字依次是 name / id / priv / callback / state_cb。
> 这解释了为什么 `.ko` 不需要 `devm_pmic_glink_client_alloc()`——它自己管生命周期。

`.rodata+0x259a` 处字节：

```
$ llvm-readelf -x .rodata qti_battery_charger_main_m81.ko | grep -A1 '0x00002590'
0x00002590 5f63616c 6c626163 6b006261 74746572 _callback.batter
0x000025a0 795f6368 61726765 72004572 ...      y_charger.Er
```

| 字段 | 值 | 来源 |
|---|---|---|
| client name | `battery_charger` | `.rodata+0x259a` |
| client id | `0x800a`（32778） | `mov w8,#0x800a` → `[client+0x8]` |
| 通道名 | `PMIC_RTR_ADSP_APPS` | **不在 .ko 里**（`grep -c PMIC_RTR_ADSP_APPS` = 0）；在 `dts/mondrian.dts:174,191` 与 ADSP 固件里 |

### 3.2 帧格式

12 字节公共头，`__le32 × 3`：`{owner, type, opcode}`。`owner` 恒为 `0x800a`；`type` 1 = 请求/响应，
2 = 通知。帧长由 opcode 决定：

| 方向 | opcode | 帧长 | 布局 |
|---|---|---|---|
| 请求 | `0x30`/`0x32`/`0x34`/`0x50` 等属性 GET | 24 B | `{owner,1,opcode,battery=0,property,value}` |
| 请求 | `0x04` 订阅通知 | 28 B | `{owner,2,0x04,battery_id,power_state,low_cap,high_cap}` |
| 请求 | `0x36` ship mode | 16 B | `{owner,1,0x36,battery_id}` |
| 请求 | `0x02` subsys-up | 28 B | `{owner,2,0x02,...}` |
| 响应 | `0x30` 属性值 | 24 B | `{owner,1,0x30,property,value,result}` |
| 响应 | `0x30` Model | 144 B | `{owner,1,0x30,property,model[128]}` |
| 通知 | `0x07` | 16 B | `{owner,2,0x07,notification_code}` |

**请求与响应的 `+0xc` 不是同一字段**：请求在 `+0xc` 放 `battery`（恒 0），`+0x10` 才是 `property`；
响应在 `+0xc` 直接放 `property`。这正是上游结构体的定义差异：

```c
/* drivers/power/supply/qcom_battmgr.c（上游） */
struct qcom_battmgr_property_request {   /* :99-104，24 B */
    struct pmic_glink_hdr hdr;           /* +0x00 owner/type/opcode */
    __le32 battery;                      /* +0x0c */
    __le32 property;                     /* +0x10 */
    __le32 value;                        /* +0x14 */
};
struct qcom_battmgr_message {            /* :125-136 */
    struct pmic_glink_hdr hdr;
    union {
        struct { __le32 property; __le32 value; __le32 result; } intval; /* +0x0c/+0x10/+0x14 */
        struct { __le32 property; char model[128]; } strval;             /* 132 B 负载 */
    };
};
```

`.ko` 侧实测印证（`battery_chg_callback` 的 `0x30` 分支从 `data+0x10` 拷 128 B Model）：

```
$ llvm-objdump -d --start-address=0x21cc --stop-address=0x2238 qti_battery_charger_main_m81.ko
    21cc: cmp  x2, #0x90              ; 144 B = 12 头 + 128 Model + 4
    21d0: b.ne 0x234c                 ; 长度不符 → 走 0x234c 的 24/32/52 B 分支
    21d4: ldr  x8, [x19, #0x140]      ; bcdev->model_buf
    21d8: cbz  x8, 0x234c
    21dc: ldp  x10, x9,  [x20, #0x20]
    21e0: ldp  x12, x11, [x20, #0x10] ; 从 data+0x10 起（跳过 12 B 头 + property）
    21ec: stp  x10, x9,  [x8, #0x10]
    21f0: stp  x12, x11, [x8]
    ...                               ; 共 8 组 ldp/stp = 128 B
    2224: ldr  x0, [x19, #0x140]
    2228: bl   strcmp                 ; 第二参 .rodata+0x1aee = "Debug_Board"
    222c: cmp  w0, #0x0
    2230: cset w8, eq
    2234: strb w8, [x19, #0x30e]      ; +0x30e = (板名 == "Debug_Board")
```

### 3.3 完成语义

每个请求都要等到同 opcode 的响应，否则 250 jiffies 超时返回 `-110`（`-ETIMEDOUT`）：

```
$ llvm-objdump -dr --start-address=0x6d0 --stop-address=0x74c qti_battery_charger_main_m81.ko
     6d0: add  x19, x20, #0xa8            ; bcdev+0xa8 = 请求互斥量
     6d4: mov  x0, x19
     6d8: bl   ...   R_AARCH64_CALL26  mutex_lock
     6dc: str  wzr, [x20, #0xd8]!         ; 清 completion（bcdev+0xd8）
     6e0: ldur x0, [x20, #-0x38]          ; pmic_glink client 句柄
     6e4: mov  w2, w21                    ; len
     6e8: mov  x1, x22                    ; data
     6ec: bl   ...   R_AARCH64_CALL26  pmic_glink_write
     6f0: mov  w21, w0
     6f4: cbnz w0, 0x708                  ; 写失败 → 直接解锁返回
     6f8: mov  w1, #0xfa                  ; 250 jiffies
     6fc: mov  x0, x20
     700: bl   ...   R_AARCH64_CALL26  wait_for_completion_timeout
     704: cbz  w0, 0x72c                  ; 超时 → 0x72c
     708: mov  x0, x19
     70c: bl   ...   R_AARCH64_CALL26  mutex_unlock
     710: mov  w0, w21
     ...
     72c: adrp x0, ...  R_AARCH64_ADR_PREL_PG_HI21  .rodata+0xe75
     730: adrp x1, ...  R_AARCH64_ADR_PREL_PG_HI21  .rodata+0x1c26
     73c: bl   ...   R_AARCH64_CALL26  printk
     744: bl   ...   R_AARCH64_CALL26  mutex_unlock
     748: mov  w21, #-0x6e                ; -110 = -ETIMEDOUT
```

响应侧统一走 `0x2464` 完成尾：

```
$ llvm-objdump -d --start-address=0x2464 --stop-address=0x2488 qti_battery_charger_main_m81.ko
    2464: bti j
    2468: add x0, x19, #0xd8
    246c: bl  complete
    2470: bti j
    2474: ldp x20, x19, [sp, #0x10]
    2478: mov w0, wzr
```

> 推论（对 L1 实现的要求）：**没有 transaction id**。未回答的请求会让整条通道失去同步，
> 因此 `K60Battmgr.c:194` 的 `k60_battmgr_timeout()` 把通道标记 `poisoned`，
> 必须 CLOSE/ACK/OPEN 之后才能再发。这与 `.ko` 的 250 jiffies 硬超时是同一约束的两种表达。

### 3.4 通知

`.ko` 的 `0x07` 分支（`0x24c8`）先无条件打印收到的通知码，再走第二张跳转表：

```
$ llvm-objdump -dr --start-address=0x24c8 --stop-address=0x2514 qti_battery_charger_main_m81.ko
    24c8: bti  j
    24cc: cmp  x2, #0x10                 ; 负载必须是 16 B
    24d0: b.ne 0x25b0
    24d4: ldr  w2, [x20, #0xc]           ; notification code 在 +0xc
    24d8: adrp x0, ...  R_AARCH64_ADR_PREL_PG_HI21  .rodata+0x2489
    24dc: adrp x1, ...  R_AARCH64_ADR_PREL_PG_HI21  .rodata+0x14cc
    24e8: bl   ...   R_AARCH64_CALL26  printk   ; 先无条件打印通知码
    24ec: ldr  w9, [x20, #0xc]
    24f0: sub  w8, w9, #0x30             ; 索引 = code - 0x30
    24f4: cmp  w8, #0x20                 ; 0x30..0x50
    24f8: b.hi 0x2660                    ; >0x50 走另一条
    24fc: adrp x9, ...  R_AARCH64_ADR_PREL_PG_HI21  .rodata+0x57  ; 第二张表
    2500: add  x9, x9, #0x0
    2504: adr  x10, 0x2470               ; 表基址 0x2470
    2508: ldrb w11, [x9, x8]
    250c: add  x10, x10, x11, lsl #2
    2510: br   x10
```

`0x2660` 只认 `0x80`：

```
$ llvm-objdump -d --start-address=0x2660 --stop-address=0x2678 qti_battery_charger_main_m81.ko
    2660: cmp w9, #0x80
    2664: b.ne 0x2470                ; 其余全部忽略
    266c: ldr w8, [x19, #0x23c]
    2670: add x20, x19, #0x138
```

对应上游 `qcom_battmgr_notification()`（`:933-964`）的分发：`0x81`/`0x80`/`0x30` → `bat_psy`，
`0x32` → `usb_psy`，`0x34` → `wls_psy`。**通知帧是 16 B，不是 24 B**；`K60Battmgr.c:152`
的 `bytes != 16` 拒收与之一致。

### 3.5 opcode 表

| opcode | 方向 | 语义 | 证据 |
|---|---|---|---|
| `0x04` | 请求 | 订阅通知（type=2） | `0x2168`；上游 `:1291-1292` |
| `0x07` | 通知 | 属性组变更 | `0x24c8`；上游 `:951-957` |
| `0x30` | 请求/响应 | battery 属性 GET | `0x21cc`；上游 `:1096` |
| `0x32`/`0x34` | 请求/响应 | usb / wireless 属性 GET | 02 §4；上游 `:1199`/`:1240` |
| `0x36` | 请求 | ship mode（16 B） | `0x27fc` 模板 |
| `0x40` | 响应 | 置 `bcdev+0x30f`（仅 `data+0xc==1`） | `0x22ac` |
| `0x42` | 响应 | 完成 `bcdev+0x118` | `0x22cc` |
| `0x43` | 响应 | 完成 `bcdev+0xf8` | `0x22ec` |
| `0x44` | 响应 | 存 `data+0xc` → `bcdev+0x314` | `0x230c` |
| `0x48` | 响应 | 完成（与 0x04 同尾） | 02 §4 |
| `0x50` | 请求→响应 | 小米扩展 GET（XM prop map 187 项）；响应 52 B → 拷 32 B 到 `+0x620`、32 B → 拷 16 B 到 `+0x628`、116 B → 拷 96 B 到 `+0x1f0` | `0x2324` |
| `0x51` | 请求→响应 | 小米扩展 SET；响应走通用 ack 分支 | `0x2168` |

`0x22ac` 原始片段：

```
$ llvm-objdump -d --start-address=0x22ac --stop-address=0x22c8 qti_battery_charger_main_m81.ko
    22ac: bti  j
    22b0: cmp  x2, #0x10                 ; 负载必须是 16 B
    22b4: b.ne 0x255c
    22b8: ldr  w8, [x20, #0xc]           ; data+0xc
    22bc: cmp  w8, #0x1
    22c0: b.ne 0x2464                    ; 不是 1 也照样 complete
    22c4: strb w8, [x19, #0x30f]         ; 只有 ==1 才置位
```

### 3.6 属性域：wire `prop_id` 是「map 下标」，不是 map 里的值

probe 在 `0x7c4`–`0x83c` 为四个域各建一条 5 字段记录：

| 域 | map 指针（只读） | 运行时副本 | 条目数 | GET | SET |
|---|---|---|---|---|---|
| battery | `bcdev+0x150` ← `.rodata+0x2d68` | `+0x158` | `+0x160` = 25 | `+0x164` = `0x30` | `+0x168` = `0x31` |
| usb | `bcdev+0x188` ← `.rodata+0x2dcc` | `+0x190` | `+0x198` = 13 | `+0x19c` = `0x32` | `+0x1a0` = `0x33` |
| wireless | `bcdev+0x1c0` ← `.rodata+0x2e00` | `+0x1c8` | `+0x1d0` = 7 | `+0x1d4` = `0x34` | `+0x1d8` = `0x35` |
| xiaomi | `bcdev+0x1f8` ← `.rodata+0x2e1c` | `+0x200` | `+0x208` = 187 | `+0x20c` = `0x50` | `+0x210` = `0x51` |

`battery_psy_get_prop`（`0x32a8`）先拿 psy 属性枚举在 map 里**线性搜索**，命中后用**下标**当 `prop_id` 发请求：

```
$ llvm-objdump -dr --start-address=0x32e4 --stop-address=0x3374 qti_battery_charger_main_m81.ko
    32e4: ldr  w8, [x0, #0x160]        ; 条目数（battery = 25）
    32fc: ldr  x9, [x20, #0x150]       ; map 指针
    3304: ldr  w10, [x9, x22, lsl #2]  ; map[i]
    3308: cmp  w10, w21                ; == 调用方给的 psy 属性？
    330c: b.eq 0x3344                  ; 命中，i 即下标
    3318: b.ne 0x3304                  ; 继续扫
    3344: tbnz w22, #0x1f, 0x33a8
    3348: mov  x8, #0x800a
    334c: movk x8, #0x1, lsl #32       ; {owner=0x800a, type=1}
    3350: stp  wzr, w22, [sp, #0xc]    ; +0xc = 0，+0x10 = 下标
    335c: ldr  w8, [x20, #0x164]       ; GET opcode
    3364: mov  w2, #0x18               ; 24 B
    336c: str  w8, [sp, #0x8]          ; +0x8 = opcode
    3370: bl   battery_chg_write
```

回包侧对称：`+0xc` 当下标做边界检查、`+0x10` 当值写进 `*_prop_cache`（`0x23a4`–`0x23bc`）：

```
    23a4: ldr  w8, [x20, #0xc]         ; prop_id = 下标
    23a8: ldr  w9, [x19, #0x198]       ; 该域条目数
    23ac: cmp  w8, w9
    23b0: b.hs 0x2470                  ; 越界丢弃
    23b4: ldr  w9, [x20, #0x10]        ; value
    23b8: ldr  x10, [x19, #0x190]      ; 运行时副本
```

结论：

1. **wire `prop_id` = 该域 map 数组的下标**（`0..count-1`）；map 里的值才是 `enum power_supply_property`。
2. 服务端回 `0x30`/`0x32`/`0x34` 时，`+0xc` 必须**原样回显请求里的下标**；`.ko` 用它做边界检查后写
   `bcdev+0x158/0x190/0x1c8/0x200[下标]`。
3. map 里的枚举值是**小米扩展过的 `power_supply.h`** 排序，不是上游 `sm8350_*_prop_map` 的取值
   （例如 battery `map[4] = 0x2e`、`map[13] = 0x33`，上游枚举没有这些下标）。要把「下标 → 属性名」
   钉死，需要小米内核的 `power_supply.h`，本仓没有——这是 `04-PROP-MAP.md` 的取证边界。
---

## 4. 三方对照

| 维度 | 上游 `qcom_battmgr` | 实物 `.ko` | 本仓 `K60Battmgr.c` |
|---|---|---|---|
| owner | `PMIC_GLINK_OWNER_BATTMGR` = 32778 | `0x800a` | `K60_BATTMGR_OWNER 32778u` |
| client name | `battmgr` | `battery_charger` | 不适用（无 pmic_glink 核心） |
| 请求帧 | 24 B `{hdr,battery,property,value}` | 24 B 同形 | 24 B 同形（`out+16=property`） |
| 订阅帧 | 28 B，type=2 | 28 B，type=2 | 28 B，type=2 |
| 通知帧 | 16 B | 16 B | 16 B（`bytes != 16` 拒收） |
| Model 响应 | 132 B 负载 | 144 B 总长（12+128+4 对齐） | `16 + 128` |
| battery prop map | 19 项（`sm8350_bat_prop_map`，`:401-421`） | 25 项 | 18 字段 |
| usb prop map | 7 项 | 13 项 | 5 字段 |
| wls prop map | 5 项（`sm8350_wls_prop_map`，`:839-845`） | 7 项 | 1 字段 |
| 小米扩展 | 无 | `xm_prop_map` 187 项 + `0x50`/`0x51` | 无 |
| 超时 | 由 `pmic_glink` 核心 | 250 jiffies → `-110` | `poisoned` 标记 |

**差异要点**：小米在 AOSP 内核里给 battmgr 加了 `xm_prop_map`（187 项）与 `0x50`/`0x51` 两个私有
opcode。这解释了为什么 `.ko` 的 prop map 比上游宽，也说明**不能用上游 map 覆盖 `.ko` 的 map**。
`K60Battmgr.c` 只实现 18 个字段（够 `IOPMPowerSource` 用），是刻意收窄而非遗漏。

---

## 5. ADSP 固件证据

`/mnt/e/k60-work/firmware/adsp/`（23.5 MB，`adsp.b00`–`b25` + `adsp.mdt`）：

```
$ for f in adsp.b*; do echo "$f $(strings -a -n 5 $f | grep -c pmic_glink)"; done
adsp.b14 20
adsp.b17 12
（其余 0）
```

`adsp.b14`/`adsp.b17` 内的字符串（决定性）：

```
PMIC_RTR_ADSP_APPS
/dev/ipc_router
IPCRTR_RDR
pmic_glink
pmic_glink.c
Info: %s: pmic_glink_open(): openning brand new glink
Info: %s: pmic_glink_open() succeeds
Info: %s: pmic_glink_deinit(): glink closed
ERROR: %s: pmic_glink_tx(): glink handle is NULL
ERROR: %s: pmic_glink_state_change::glink_queue_rx_intent() returns error %d
pmic_glink.c:ERROR: xm_set_power_supply_properties property_id:%d, val:%d
pmic_glink.c:ERROR: xm_get_power_supply_ss_auth
pmic_glink.c:ERROR: xm_set_power_supply_push_wls_fw_bin: property_id:%d total_length:%d ...
```

结论：

1. `pmic_glink` 的**服务端在 ADSP 固件里**，`.ko` 只是客户端。
2. 通道名 `PMIC_RTR_ADSP_APPS` 在 ADSP 侧同名注册——这与 `dts/mondrian.dts:174`
   （`qcom,glink-channels = "PMIC_RTR_ADSP_APPS"`）和 `:191`（`qcom,pmic-glink-channel`）一致。
3. 因此「路线 A（真 pmic_glink 服务端）」在协议层**真实存在**，不是推测。
4. 仍缺：AP 侧 `pmic_glink.c` 里 `PMIC_RTR_ADSP_APPS` 对应的 ipc_router 端口号/GUID；
   ADSP 侧 battery 服务的 opcode 实现（固件是二进制，未反汇编）。

> 注意：`adsp.b14`/`adsp.b17` 是 PIL 分片，字符串偏移**不能**当 VA 用。要真正定位
> `pmic_glink_open` 的实现，需要按 `adsp.mdt` 的 program header 拼接后做 ELF 解析。

---

## 6. 缺口与推进顺序

### 缺口 A：104 B blob 没有生产者

```
$ grep -rn "k60_handoff_build(" --include=*.c --include=*.h --include=*.patch .
drivers/PongPower/K60HandoffBuild.c:33   （定义）
drivers/PongPower/K60HandoffBuild.h:35   （声明）
patches/xnu/0611-k60-smem-handoff.patch  （注释/声明/定义）
scripts/tests/test-k60-handoff-build.c   （测试）
```

消费方 `K60Battery.cpp:426` 在等 `/chosen` 上的 `k60-adsp-glink-handoff`，但没有任何内核代码
调用 `k60_handoff_build()` 并把它写到 `/chosen`。**这是 L0 的唯一阻塞点**。

### 缺口 B：订阅参数恒为 0

```
$ sed -n '277,280p' scripts/build-k60-physical-battery.py
    (out / 'K60BatteryProtocol.generated.h').write_text(
        '/* Zero until exact subscription ACK wire capture qualifies it. */\n'
        f'#define K60_BATTERY_NOTIFY_REPLY_TYPE {notify_type}u\n'
        f'#define K60_BATTERY_NOTIFY_REPLY_BYTES {notify_bytes}u\n')
```

`notify_type`/`notify_bytes` 来自 `qualification()`，没有 wire capture 时为 0 →
`K60Battmgr.c:66` `subscribe_due = 0` → 永不发 `0x04` 订阅 → 永远收不到 `0x07` 通知。
**这不会让属性读取失效**（属性轮询仍然工作），但会让「充电中/拔出」变成最多一个刷新周期才反映。

> 现在可以从本文 §3.2 直接推出候选值：订阅请求 28 B，回包若是「+0xc 起四个零字」则
> `notify_reply_bytes = 28`。`type` 需真机抓一次确认（`.ko` 的 `0x04` 分支按长度分派，
> 未固定 type）。**在抓到之前不要把猜的值写进生成器**——`K60Battmgr.c:163-166` 的注释
> 明确说明「宁可拒收也不接受含糊的 ACK」。

### 推进顺序

1. **（L0）补生产者**：在 AP 侧调用 `k60_smem_partition` → `k60_handoff_build()` →
   发布 `/chosen` 属性。这一步做完，`K60Battery.cpp` 的 `blocked rc=` 分支才会消失。
2. **（L0）补固件装载**：`adsp.b00`–`b25` 按 `adsp.mdt` 拼接后放进 ramdisk，
   由 `k60_adsp_probe_from_handoff()`（boot-arg `pong_adsp=1`）装载。
3. **（L1）抓订阅 ACK**：通道通后抓一次 `0x04` 回包，填 `notify_type`/`notify_bytes`。
4. **（L1）验证属性路径**：`0x30`/`0x32`/`0x34` 逐个跑通，对照 `K60Battmgr.c:106`
   `value_valid()` 的量纲范围。

---

## 7. 未决问题

| # | 问题 | 现状 |
|---|---|---|
| 1 | `+0xc` 在请求/响应里语义不同 | **已解**：请求是 `battery` 槽位，响应是 `property`（§3.2） |
| 2 | 通道名 / GUID / IPCRTR 端口 | 名字已定 `PMIC_RTR_ADSP_APPS`；端口号/GUID 仍缺（在 AP 内核 `pmic_glink.c` 里） |
| 3 | `type` 字段 1/2 的完整语义 | 1 = REQ_RESP，2 = NOTIFY（上游 `pmic_glink.h`）；`.ko` 的 `0x40`–`0x44` 是否也用 2 待抓 |
| 4 | `0x37`/`0x48` 语义 | 仍未知（02 §4 列为「同尾 complete」，未定位到业务动作） |
| 5 | `check_status_work` 的 4 条请求 | 未逐条展开（charger-ko 阶段二 05 文档负责） |
| 6 | `xm_prop_map` 187 项的具体含义 | 全 0 占位，需 ADSP 侧 `xm_*` 反汇编 |
| 7 | ADSP 侧 battery 服务的 opcode 实现 | 固件未反汇编 |

---

## 8. 复现命令

```bash
KO=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko

# 客户端名与 id
llvm-objdump -dr --start-address=0xa90 --stop-address=0xad8 $KO
llvm-readelf -x .rodata $KO | grep -A1 '0x00002590'  # 0x259a = battery_charger

# 通道名不在模块里
strings -a $KO | grep -c PMIC_RTR_ADSP_APPS        # 0

# 请求模板 / 完成语义
llvm-objdump -dr --start-address=0x688 --stop-address=0x74c $KO
llvm-objdump -d  --start-address=0x2464 --stop-address=0x2488 $KO

# callback 跳转表
llvm-objdump -d  --start-address=0x211c --stop-address=0x2170 $KO
llvm-objdump -d  --start-address=0x24c8 --stop-address=0x2514 $KO

# 通知分支
llvm-objdump -d  --start-address=0x2660 --stop-address=0x2678 $KO

# ADSP 固件里的服务端
for f in /mnt/e/k60-work/firmware/adsp/adsp.b*; do
  printf '%s %s\n' "$(basename $f)" "$(strings -a -n 5 $f | grep -c pmic_glink)"
done

# 本仓缺口
grep -rn "k60_handoff_build(" --include=*.c --include=*.h .
sed -n '277,280p' scripts/build-k60-physical-battery.py
```

---

## 相关文档

- [01-SYMBOL-MAP.md](../charger/01-SYMBOL-MAP.md) — `.ko` 的 675 个符号与 232 个函数
- [02-GLINK-CONTRACT.md](../charger/02-GLINK-CONTRACT.md) — client 注册、16 B 头、opcode 表、四张 prop map
- [03-REVERSE.md](../charger/03-REVERSE.md) — probe / write / callback 关键路径
- [GLINK-HANDOFF.md](GLINK-HANDOFF.md) — L0 的 104 字节契约
- [ADSP-PAS1.md](../audio/ADSP-PAS1.md) — PAS1 调用序列与镜像事实
