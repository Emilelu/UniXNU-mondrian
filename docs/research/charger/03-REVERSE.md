# 03 · 关键路径反编译 — init / probe / write / callback / 状态机 / ship mode

> 约定：地址 = 节内偏移（详见 01 §1.2）。所有 `asm` 片段都是 `llvm-objdump -dr` 的**原始输出**（含重定位行），可用 §9 的命令逐字节复现。

## 0. 结论摘要

1. 模块骨架极薄：`init_module` 只做 `__platform_driver_register(&battery_chg_driver)`，`cleanup_module` 只做 `platform_driver_unregister`；驱动名 `qti_battery_charger`，of_match 含 `qcom,battery-charger` 等 4 组。
2. `battery_chg_probe`（`0x754`，0x950 B）是唯一的组装点：`devm_kmalloc(0x738)` 分配 bcdev → 建 4 张 prop map → 注册 pmic_glink client（id `0x800a`）→ 注册 3 个 power_supply（battery/usb/wireless）→ thermal zone → reboot notifier×2 → class `qcom-battery` → debugfs `battery_charger` → 排 4 类 work。
3. **所有出向报文只有一个出口**：`battery_chg_write`（`0x688`）。它有三道闸门（`state==0`、`bcdev+0x30e`、`bcdev+0x30c`），然后 `pmic_glink_write` + 250 jiffies 等完成，超时返回 `-110`。
4. rx 由 `battery_chg_callback`（`0x211c`）按 `data+8` 的 opcode 走 78 字节跳转表（`.rodata:0x9`）分发到 11 个有效分支；`0x04/0x36/0x37/0x48` 统一 `complete(&bcdev->wait)`，`0x32/0x34` 把 `prop_id/value` 写进缓存，`0x30` 收 128 B 板名。
5. 状态机由 `battery_chg_state_cb`（GLINK up → queue）驱动 `battery_chg_subsys_up_work`，后者按固定顺序发 4 条请求（subsys-up 握手 → 限流值 → usb 属性 → usb 类型）；`chg_type/ffc/pd_verifed` 等只在调试打印里出现（`.rodata:0x400`、`.rodata:0x904`），不构成独立状态机。
6. ship mode / shutdown 各是一条 16 字节请求 `{0x800a, 1, 0x36, 0}`，挂在 reboot notifier（优先级 `0xff`）上；`ship_mode` 由 `bcdev-0x13`（即 `bcdev+0x30d` 使能字节）门控。

## 1. 模块骨架

```asm
0000000000000000 <init_module>:                  ; .init.text
       0: paciasp
       8: stp   x29, x30, [sp, #-0x10]!
      10: adrp  x0, .data+0x68                   ; &battery_chg_driver
      14: adrp  x1, __this_module
      1c: add   x1, x1, #0x0
      20: bl    __platform_driver_register
      30: ret

0000000000000000 <cleanup_module>:               ; .exit.text
      10: adrp  x0, .data+0x68
      18: bl    platform_driver_unregister
      28: ret
```

`battery_chg_driver`（`.data:0x68`，0xf0 B）的字段由重定位确定：`+0x00` probe→`battery_chg_probe.cfi_jt`、`+0x08` remove→`battery_chg_remove.cfi_jt`、`+0x28` name→`.rodata:0x755` `qti_battery_charger`、`+0x50` of_match_table→`.rodata:0x2bd8`、`+0x88` shutdown→`battery_chg_shutdown.cfi_jt`。

## 2. `battery_chg_probe`（0x754，0x950 B）

### 2.1 入口与 bcdev 分配

```asm
     754: paciasp
     758: sub   sp, sp, #0xc0
     780: add   x19, x0, #0x10          ; dev = platform_device+0x10
     784: adrp  x1, .rodata+0x1e7f      ; "battery_chg_probe start\n"
     790: mov   x0, x19
     7a4: bl    _dev_err
     7a8: mov   w0, #0x32               ; 50
     7ac: bl    msleep                  ; 先睡 50 ms
     7b0: mov   w1, #0x738              ; sizeof(*bcdev) = 1848
     7b4: mov   w2, #0xdc0              ; GFP_KERNEL
     7bc: bl    devm_kmalloc
     7c0: cbz   x0, 0xaf4               ; 失败 → -ENOMEM
     7c4: adrp  x8, .rodata+0x2d68      ; battery_prop_map
     7cc: str   x8, [x0, #0x150]
     7d0: mov   x8, #0x19               ; 25 项
     7d4: movk  x8, #0x30, lsl #32      ; GET 0x30
     7d8: str   x8, [x0, #0x160]
     7dc: mov   w8, #0x31               ; SET 0x31
```

### 2.2 bcdev 关键字段（由 probe 的 `str` 偏移与各回调交叉确定）

| 偏移 | 内容 | 首次写入地址 |
|---|---|---|
| `+0x00` | `dev` | `0xabc` |
| `+0x08` | `class`（`qcom-battery`） | `0xe34` 前 `__class_register` 的第二个参数 `.bss:0x18`，`remove` 用 `class_unregister(bcdev+0x8)` 印证 |
| `+0xa0` | `pmic_glink_client *` | `0xad8` |
| `+0xa8` | `rw_lock`（mutex） | `0x924` `__mutex_init` |
| `+0xd8` | `completion wait`（每请求完成） | `0x6dc` 清、`0x2468` complete |
| `+0xf8` / `+0x118` | 另两个 completion（固件/VDM 等待者） | `0x22ec` / `0x22cc` |
| `+0x140` | `debug_board_buf`（128 B） | `0x21d4` 读、probe 分配 |
| `+0x150/0x158/0x160/0x164/0x168` | battery `{map, 副本, 25, GET 0x30, SET 0x31}` | `0x7c4–0x7e4` |
| `+0x188/0x190/0x198/0x19c/0x1a0` | usb `{map, 副本, 13, GET 0x32, SET 0x33}` | `0x80c` 起 |
| `+0x1c0/0x1c8/0x1d0/0x1d4/0x1d8` | wireless `{map, 副本, 7, GET 0x34, SET 0x35}` | `0x870` 起 |
| `+0x1f8/0x200/0x208/0x20c/0x210` | xiaomi `{map, 副本, 187, GET 0x50, SET 0x51}` | `0x8c8` 起 |
| `+0x218` | `debugfs_root` | `0xe68` `debugfs_create_dir` 结果；`remove` 用 `debugfs_remove(bcdev+0x218)` 印证 |
| `+0x228` | `wireless_fw_name`（字符串） | `0xb74` `of_property_read_string` |
| `+0x23c` | `shutdown_voltage`（u32 数组） | `0xb98` |
| `+0x240` | `state`（1 = up） | `0xab8` 预置 1、`0x2744` 由 state_cb 写入 |
| `+0x248` | `subsys_up_work`（delayed_work） | `0x98c` 起 |
| `+0x278` | `update_usb_type_work` | 同上 |
| `+0x2a8` | `check_status_work` | 同上 |
| `+0x30c` / `+0x30e` | `block_tx` / `is_not_debug_board` 闸门字节 | `0xea8` debugfs bool / `0x2234` strcmp |
| `+0x30f` | `pd/attached 通知标志`（`0x40` 置位） | `0x22ac` |
| `+0x314` | `0x44` 通知写入的端口/typec 值 | `0x230c` |
| `+0x320` / `+0x338` | `reboot_notifier`（ship_mode / shutdown），优先级 `0xff` | `0xb54` / `0xb70` |
| `+0x358` / `+0x35c` | 限流值 / usb 限流值（带脏标记） | `0x121c` / `0x1274` |
| `+0x618` | client 注册成功标志 | `0xb34` `strb w23,[x20,#0x618]` |
| `+0x620` / `+0x628` | `0x51` 大块数据缓冲（32 B / 16 B） | `0x2324` |

### 2.3 pmic_glink 注册（`0xa90–0xb40`）

```asm
     a90: adrp  x9, .rodata+0x259a        ; "battery_charger"
     a94: adrp  x10, battery_chg_callback.cfi_jt
     a98: adrp  x11, battery_chg_state_cb.cfi_jt
     a9c: mov   w23, #0x1
     aa0: mov   w8, #0x800a               ; client id
     ab0: add   x1, sp, #0x8
     ab4: mov   x0, x19
     ab8: str   w23, [x20, #0x240]        ; bcdev->state = 1
     abc: str   x19, [x20]                ; bcdev->dev = dev
     ac0: str   w8, [sp, #0x10]           ; client.id = 0x800a
     ac4: str   x9, [sp, #0x8]            ; client.name = "battery_charger"
     ac8: stp   x20, x10, [sp, #0x18]     ; priv, msg_cb
     acc: str   x11, [sp, #0x28]          ; state_cb
     ad0: bl    pmic_glink_register_client
     ad4: cmn   x0, #0xfff
     ad8: str   x0, [x20, #0xa0]
     adc: b.lo  0xb34                     ; 成功
     ae4: cmn   w25, #0x205               ; == -517 ?
     aec: mov   w25, #-0x205              ; 透传 EPROBE_DEFER
     af4: mov   w25, #-0xc                ; 其它 → -ENOMEM
     b34: strb  w23, [x20, #0x618]        ; 置“已注册”
     b38: add   x23, x20, #0x320          ; reboot_notifier #1
```

### 2.4 其余注册动作（按地址顺序）

| 地址 | 动作 | 参数/字符串 |
|---|---|---|
| `0xb74` | `of_property_read_string` | `qcom,wireless-fw-name` → `bcdev+0x228` |
| `0xb98` | `of_property_read_variable_u32_array` | `qcom,shutdown-voltage` → `bcdev+0x23c` |
| `0xbc0` | `of_property_count_elems_of_size` | `qcom,thermal-mitigation` |
| `0xc04` | `devm_power_supply_register` | `batt_psy_desc`（`.rodata:0x3188`，name `battery`） |
| `0xc98` | `thermal_zone_device_register` | `.data:0x250` `psy_tzd_ops` |
| `0xcb0` | `devm_power_supply_register` | `usb_psy_desc`（`.data:0x198`，name `usb`） |
| `0xcf4` | `of_property_read_variable_u32_array` | `qcom,thermal-mitigation`（失败打印 `.rodata:0xa5d`，%s=`battery_chg_parse_dt`） |
| `0xd40` | `devm_power_supply_register` | `wls_psy_desc`（`.rodata:0x31f0`，name `wireless`） |
| `0xd84/0xd8c` | `pmic_glink_unregister_client` / `unregister_reboot_notifier`×2 | 错误路径 |
| `0xdbc/0xddc/0xdfc` | `of_find_property` | `mi,support-2s-charging`、`mi,support-dual-panel`、`mi,support-soc-update` |
| `0xe34` | `__class_register` | `.data:0x158` groups，class 名 `.rodata:0x130a` `qcom-battery` |
| `0xe68` | `debugfs_create_dir` | `.rodata:0x259a` `battery_charger`（失败 `.rodata:0x584`，%s=`battery_chg_add_debugfs`） |
| `0xea8` | `debugfs_create_bool` | `.rodata:0x4d9` `block_tx` → `bcdev+0x30c` |
| `0xf08` | `battery_chg_write` | 使能通知（失败 `.rodata:0x1a45`，%s=`battery_chg_notify_enable`） |
| `0xf34` | `device_init_wakeup(dev, true)` | — |
| `0xf48/0xf5c` | `queue_work_on` / `queue_delayed_work_on` | 排 subsys_up / check_status |
| `0xf8c` | `queue_work`（blank state） | `notify_blankstate_changed_work` |
| `0xfb4` | `queue_work`（panel） | `qti_battery_register_panel_notifier_work`（另有 sec 版） |

注册顺序值得注意：**先注册 pmic_glink client，再注册 power_supply**，而 `bcdev->state` 在注册前就置 1——所以 `battery_chg_write` 在 psy 注册完成前就可能被调用（debugfs/notify 路径）。

## 3. `battery_chg_write`（0x688，0xc8 B）——唯一出口

```asm
     688: paciasp
     690: stp   x29, x30, [sp, #-0x30]!
     6a0: add   x8, x0, #0x240
     6a4: ldar  w8, [x8]                  ; bcdev->state
     6a8: cbz   w8, 0x6c8                 ; state==0 → 直接返回 0
     6ac: ldrb  w8, [x0, #0x30e]           ; is_not_debug_board
     6bc: cbz   w8, 0x6d0
     6c0: ldrb  w8, [x20, #0x30c]          ; block_tx
     6c4: cbz   w8, 0x6d0
     6c8: mov   w21, wzr                   ; 两个闸门都非 0 → 返回 0（静默丢弃）
     6d0: add   x19, x20, #0xa8
     6d8: bl    mutex_lock                  ; R_AARCH64_CALL26 mutex_lock
     6dc: str   wzr, [x20, #0xd8]!         ; 清 completion
     6e0: ldur  x0, [x20, #-0x38]          ; client = bcdev+0xa0
     6e4: mov   w2, w21                    ; len
     6e8: mov   x1, x22                    ; data
     6ec: bl    pmic_glink_write           ; R_AARCH64_CALL26 pmic_glink_write
     6f0: mov   w21, w0
     6f4: cbnz  w0, 0x708                 ; 发送失败不等待
     6f8: mov   w1, #0xfa                  ; 250 jiffies
     700: bl    wait_for_completion_timeout
     704: cbz   w0, 0x72c                 ; 超时
     708: mov   x0, x19
     70c: bl    mutex_unlock
     710: mov   w0, w21
     728: ret
     72c: adrp  x0, .rodata+0xe75          ; "BATTERY_CHG: %s: Error, timed out sending message\n"
     730: adrp  x1, .rodata+0x1c26          ; "battery_chg_write"
     73c: bl    printk
     748: mov   w21, #-0x6e                ; -110 = -ETIMEDOUT
     74c: b     0x710
```

要点：`state` 用 `ldar`（acquire）读，与 `state_cb` 的 `str` 构成无锁状态机；`0x30e`（非 Debug_Board）与 `0x30c`（block_tx）同时为 1 时**静默丢弃**报文并返回 0（调用者以为成功）。

## 4. `battery_chg_callback`（0x211c，0x614 B）——rx 分发

### 4.1 头与跳转表

```asm
    211c: paciasp
    2128: stp   x20, x19, [sp, #0x10]
    2130: ldrb  w8, [x0, #0x618]          ; 已注册？
    2134: cbz   w8, 0x2470                ; 否 → 返回 0
    2138: ldr   w8, [x1, #0x8]            ; opcode = data+0x8
    2140: sub   w9, w8, #0x4
    2144: cmp   w9, #0x4d                 ; 4 .. 0x51
    2148: b.hi  0x24a8                    ; 越界 → Unknown opcode
    214c: adrp  x10, .rodata+0x9          ; 78 字节表
    2154: adr   x11, 0x2168
    2158: ldrb  w12, [x10, x9]
    215c: add   x11, x11, x12, lsl #2
    2164: br    x11                       ; target = 0x2168 + byte*4
```

### 4.2 跳转表逐项（`.rodata+0x9`，78 字节，值 = 目标相对 `0x2168` 的 4 字节倍数）

| opcode | 表项字节 | 目标 | 行为 |
|---|---|---|---|
| `0x04` | 191 | `0x2464` | complete |
| `0x05–0x2f` | 208 | `0x24a8` | 未知 opcode 报错 |
| `0x30` | 24 | `0x21c8` | 收 144 B 板名 |
| `0x31` | 0 | `0x2168` | SET 应答（校验长度/rc） |
| `0x32` | 53 | `0x223c` | usb prop → 缓存 |
| `0x33` | 0 | `0x2168` | SET 应答 |
| `0x34` | 67 | `0x2274` | wireless prop → 缓存 |
| `0x35` | 0 | `0x2168` | SET 应答 |
| `0x36` | 191 | `0x2464` | complete |
| `0x37` | 191 | `0x2464` | complete |
| `0x38–0x3f` | 208 | `0x24a8` | 未知 |
| `0x40` | 81 | `0x22ac` | `bcdev+0x30f = (data+0xc==1)` |
| `0x41` | 208 | `0x24a8` | 未知 |
| `0x42` | 89 | `0x22cc` | `complete(bcdev+0x118)` |
| `0x43` | 97 | `0x22ec` | `complete(bcdev+0xf8)` |
| `0x44` | 105 | `0x230c` | `bcdev+0x314 = data+0xc` |
| `0x45–0x47` | 208 | `0x24a8` | 未知 |
| `0x48` | 191 | `0x2464` | complete |
| `0x49–0x50` | 208 | `0x24a8` | 未知（注意：`0x50` 的 GET 应答也走“未知”，即 driver **不解析** `0x50` 响应内容，只 complete） |
| `0x51` | 111 | `0x2324` | 拷 32/16 B 数据 |

表尾补 `0` 填充（`0x51` 之后无有效项）。`0x2168`（SET 应答）分支：

```asm
    2168: bti   j
    216c: cmp   x2, #0x18                 ; len == 24 ?
    2170: b.eq  0x21a0                    ; → 检查 rc
    2174: cmp   x2, #0x20                 ; len == 32 ?
    2178: b.eq  0x2464                    ; → 只 complete
    217c: cmp   x2, #0x34                 ; len == 52 ?
    2180: b.eq  0x2464
    2184: adrp  x0, .rodata+0xa1c          ; "Incorrect response length %zu for opcode %#x"
```

### 4.3 通用尾部

```asm
    2464: bti   j
    2468: add   x0, x19, #0xd8            ; &bcdev->wait
    246c: bl    complete
    2470: bti   j
    2474: ldp   x20, x19, [sp, #0x10]
    2478: mov   w0, wzr                   ; 恒返回 0
    2488: ret
```

`complete` 是**无条件**的：任何被识别（或落到默认分支）的消息都会唤醒 `battery_chg_write` 的等待者。默认分支（`0x24a8`）先打印 `.rodata:0xa1c`/`.rodata:0x24b0` 再落到 `0x2464`，所以“未知 opcode”的响应同样会解除等待。

## 5. 状态机

### 5.1 `battery_chg_state_cb`（0x2730）：GLINK 状态 → queue work

```asm
    2730: paciasp
    2740: cmp   w1, #0x1                  ; state == 1 (UP)
    2744: str   w1, [x0, #0x240]          ; bcdev->state = state
    2748: b.ne  0x2760
    274c: adrp  x8, system_wq
    2754: add   x2, x0, #0x248            ; &bcdev->subsys_up_work
    2758: mov   w0, #0x20                 ; WORK_CPU_UNBOUND
    275c: bl    queue_work_on
    2760: ret
```

### 5.2 `battery_chg_subsys_up_work`（0x11b0）：4 条初始化请求

```asm
    11b0: paciasp
    11d4: sub   x19, x0, #0x248           ; work → bcdev
    11d8: mov   x9, #0x800a
    11dc: movk  x9, #0x2, lsl #32          ; {owner=0x800a, type=2}
    11e0: mov   w10, #0x4                  ; opcode 4
    11e4: add   x1, sp, #0x8               ; buf
    11e8: mov   w2, #0x1c                  ; len 28
    11f4: stur  xzr, [sp, #0x1c]
    11f8: stur  xzr, [sp, #0x14]
    11fc: str   x9, [sp, #0x8]             ; +0x00/=0x800a, +0x04=2
    1200: str   w10, [sp, #0x10]           ; +0x08 = 4
    1204: bl    battery_chg_write
    1208: tbnz  w0, #0x1f, 0x1338          ; 负 → 错误路径
    120c: mov   w0, #0xc8                  ; 200
    1210: bl    msleep                     ; 稳定 200 ms
```

之后三条（`0x121c–0x12fc`）：

| 序号 | 条件 | 报文 | 目的 |
|---|---|---|---|
| 2 | `bcdev+0x358 != 0` | `{0x800a,1,0x31,0,0x0a,value}`（24 B） | SET battery prop 10（限流），成功后清脏标记 |
| 3 | `bcdev+0x35c != 0` | `{0x800a,1,0x32,0,0x07,0}`（24 B） | GET usb prop 7（USB 类型） |
| 4 | `usb_prop_cache[7] ∈ {6,1}` | `{0x800a,1,0x33,0,0x05,±value}`（24 B） | SET usb prop 5（限流），值取 `csneg w21,w21,wzr,ge` |

### 5.3 `battery_chg_update_usb_type_work`（0x1408）

`sub x19,x0,#0x278` 取 bcdev，发 `{0x800a,1,0x51,0,0x07,0}`（24 B，SET xiaomi prop 7），随后读 `usb_prop_cache[7]`（`[bcdev+0x190]+0x1c`）按值 4/5/6/7/8/9 分支更新 `usb_type`，末尾 `queue_work`/`complete`。

### 5.4 `battery_chg_check_status_work`（0x156c）与 `chg_type/ffc/pd_verifed`

`0x156c`（0x1f8 B）的调用序列是 `battery_chg_write`×4 + `printk`×3 + `msleep`：周期性状态刷新（4 条 GET）。`chg_type`、`ffc`、`pd_verifed` 只出现在调试格式化串里：

- `.rodata:0x400`：`BATTERY_CHG: %s: chg_type= %s tl:= %d  ffc:= %d, pd_verifed:= %d, FG_VENDOR_ID:= %d`
- `.rodata:0x904`：`BATTERY_CHG: %s: chg_type=%s tl:=%d  ffc:=%d, pd_verifed:=%d`
- `.rodata:0x2155`：debugfs 属性名 `pd_verifed`（`pd_verifed_show/store` 0x6144/0x61f4）

**没有**独立的 `chg_type/ffc/pd_verified` 状态机：这些值是 `battery_psy_get_prop` 从 `bcdev->*_prop_cache[]`/本地字段读出后直接返回，状态推进靠 `0x40/0x42/0x43/0x44` 通知与 `battery_chg_check_status_work` 的周期轮询。

## 6. ship mode / shutdown

`battery_chg_ship_mode`（0x2770，0xc0 B）—— reboot notifier 回调：

```asm
    2770: paciasp
    2794: ldurb w8, [x0, #-0x13]          ; notifier 在 bcdev+0x320，故 -0x13 = bcdev+0x30d
    2798: cbz   w8, 0x27b4                 ; 未使能 → 返回 0
    279c: mov   x8, #0x800a
    27a0: movk  x8, #0x1, lsl #32          ; {owner=0x800a, type=1}
    27a4: mov   w9, #0x36                  ; opcode 0x36
    27a8: cmp   x1, #0x3                   ; SYS_POWER_OFF?
    27ac: stp   x8, x9, [sp, #0x8]         ; 16 字节请求
    27b0: b.eq  0x27e4                     ; 只有 poweroff 才真正发
    27b4: ... 返回 0
    27e4: sub   x19, x0, #0x320
    27e8: adrp  x0, .rodata+0x1ae          ; "BATTERY_CHG: %s: set adsp shipmode\n"
    27ec: adrp  x1, .rodata+0x24e7          ; "battery_chg_ship_mode"
    27f8: bl    printk
    27fc: add   x1, sp, #0x8
    2800: mov   w2, #0x10                  ; len 16
    2804: mov   x0, x19                    ; bcdev
    2808: bl    battery_chg_write
    280c: tbz   w0, #0x1f, 0x27b4          ; 成功 → 返回 0
    2814: adrp  x0, .rodata+0x131d          ; "Failed to write ship mode: %d\n"
    2824: bl    printk
```

要点：只有 `x1 == 3`（poweroff）才发报文；使能位来自 `bcdev+0x30d`（`ship_mode_en_store` 0x469c 写它）；报文固定 `{0x800a, 1, 0x36, 0}`。

`battery_chg_shutdown`（0x2830，0xc0 B）结构相同（`printk` → `battery_chg_write` → `printk`），相关字符串：`.rodata:0x139` `Initiating a shutdown in 100 ms`、`.rodata:0x20c9` `Failed to write shutdown cmd to adsp: %d`、`.rodata:0xfe8` `start adsp shutdown`。两个 notifier 的优先级都是 `0xff`（`bcdev+0x330`/`+0x348`），即最高优先级、最先被调用。

## 7. debugfs / class 属性面

probe 建 `battery_charger` 目录（`.rodata:0x259a`）+ `block_tx` bool（`.rodata:0x4d9` → `bcdev+0x30c`），另外注册 class `qcom-battery`（`.rodata:0x130a`，144 个 class_attribute）。

属性名（`.rodata` 里的 `device_attribute` 名，节选）：`soh`、`resistance`、`moisture_detection_status`、`moisture_detection_en`、`wireless_boost_en`、`fake_soc`、`wireless_fw_update`、`wireless_fw_force_update`、`wireless_fw_version`、`wireless_fw_crc`、`ship_mode_en`、`restrict_chg`、`restrict_cur`、`usb_real_type`、`usb_typec_compliant`、`real_type`、`verify_digest`、`connector_temp`、`authentic`、`chip_ok`、`vbus_disable`、`request_vdm_cmd`、`current_state`、`adapter_id`、`adapter_svid`、`pd_verifed`、`pdo2`、`bq2597x_*`、`master_smb1396_*`、`slave_smb1396_*`、`smb_iin_diff`、`cc_orientation`、`input_suspend`、`fastchg_mode`、`night_charging`、`blank_status`、`screen_cctog`、`shutdown_delay`、`soc_decimal`、`quick_charge_type`、`fake_cycle`、`fake_soh`、`deltafv`、`fake_temp`、`cycle_count_diff`、`thermal_remove`、`typec_mode`、`mtbf_current`、`smart_batt`、`sport_mode`、`apdo_max`、`die_temperature`、`fg_raw_soc`、`battcont_online`、`battmoni_isc/soa`、`over_peak_flag`、`current_deviation`、`power_deviation`、`average_current`、`average_temp`、`start_learn/stop_learn/set_learn_power/get_learn_*`、`constant_power`、`remaining_time`、`referance_power`、`nvt_referance_*`、`tx_mac`、`pen_mac`、`tx_iout`、`tx_vout`、`pen_soc`、`pen_hall3/4`、`rx_cr`、`rx_cep`、`bt_state`、`wireless_chip_fw`、`wls_bin`、`rx_vout`、`rx_vrect`、`rx_iout`、`tx_adapter`、`op_mode`、`wls_die_temp`、`wlscharge_control_limit`、`wls_debug`、`wls_fw_state`、`wls_car_adapter`、`wls_tx_speed`、`wls_fc_flag`、`fg1_*`（20 项）、`power_max`、`fg_vendor`、`fg_temp_max`、`fg_time_ot`、`atest`、`last_node`。

这些 `_show/_store` 中 **195 个函数**最终调用 `battery_chg_write`（见 01 §0）；`wls_*`/`fg1_*`/`*_learn_*` 等多为“读本地缓存/写本地字段”，只有协议相关的那批才真正发报文。

## 8. 未决问题

1. `battery_chg_check_status_work`（`0x156c`）的 4 条 `battery_chg_write` 具体 opcode/长度未逐条展开（本轮只取了调用序列），需要补 `0x156c–0x1764` 的完整反汇编。
2. `battery_chg_update_usb_type_work` 的 usb_type 分支映射（值 4/5/6/7/8/9 → `POWER_SUPPLY_USB_TYPE_*`）只确认了跳转结构，未逐值确认。
3. `0x40/0x42/0x43/0x44` 四个通知的真实业务含义（谁在等 `bcdev+0x118` / `bcdev+0xf8`）需结合 `wireless_fw_update`（0x3f44）与 `request_vdm_cmd_show`（0x5808）的等待点确认。
4. `bcdev+0x30e` 的语义链：`0x30` 响应的 128 B 板名与 `.rodata:0x1aee` `Debug_Board` 比较 → `0x30e`（1 = 非 Debug_Board）→ 与 `0x30c` 一起作为 `battery_chg_write` 的闸门。为什么“非 Debug_Board 且 block_tx”时要静默丢报文，需要结合小米产线逻辑确认。
5. `ship_mode` 回调里 `x1 == 3` 的 notifier 事件编号与 `struct notifier_block` 的 `SYS_POWER_OFF` 对应关系需与内核版本核对（5.10 的枚举值）。

## 9. 复现命令

```bash
KO=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
llvm-objdump -dr --section=.init.text "$KO"                            # init_module
llvm-objdump -dr --section=.exit.text "$KO"                            # cleanup_module
llvm-objdump -dr --start-address=0x754  --stop-address=0x10a4 "$KO"    # probe
llvm-objdump -dr --start-address=0x688  --stop-address=0x754  "$KO"    # battery_chg_write
llvm-objdump -dr --start-address=0x211c --stop-address=0x2730 "$KO"    # callback 全量
llvm-objdump -dr --start-address=0x2730 --stop-address=0x2770 "$KO"    # state_cb
llvm-objdump -dr --start-address=0x11b0 --stop-address=0x1408 "$KO"    # subsys_up_work
llvm-objdump -dr --start-address=0x2770 --stop-address=0x2830 "$KO"    # ship_mode
llvm-objdump -dr --start-address=0x2830 --stop-address=0x28f0 "$KO"    # shutdown
llvm-objdump -s -j .rodata "$KO"                                      # 字符串 + 跳转表
```
