# 05 — 未决问题逐条结案（charger .ko 反编译）

> 目标件：`/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko`
> 247,776 B，ELF64 LSB aarch64 relocatable，BuildID `e852b83c589f773d7cb09e6793ac59fd33086c58`
> 地址为**节内偏移**（VMA 全 0）。证据全部来自 `llvm-objdump -dr` / `llvm-readelf -p` / `llvm-nm -S`。
> 本文结案 `02-GLINK-CONTRACT.md` §8 与 `03-REVERSE.md` 遗留的 5 个问题，并新增 bcdev 字段表。

## 0. 结案摘要

| # | 原未决问题 | 结论 | 关键证据 |
| --- | --- | --- | --- |
| 1 | 头第 4 字（`+0xc`）请求与响应不对称 | **已解**：请求 `+0xc` 是 `battery` 槽位（恒 0），`+0x10` 才是 prop_id；响应 `+0xc` 直接是 prop_id | `0x3350` `stp wzr,w22` + `0x3648` 硬编码 `0x0a` |
| 2 | `0x37` / `0x48` 语义 | `0x37` = **shutdown 命令**，12 B，仅 `(x1 & ~2) == 1`（重启）时发；`0x48` **不是 rx opcode**——主跳转表把它映射到 `0x24a8`（`Unknown opcode: %u.`），只发不收 | `0x2850`、`.rodata+0x9` 表项、`0x24a8` |
| 3 | type 字段 1/2 语义 | `1` = REQ_RESP（属性 GET/SET、0x40/0x41/0x44、ship mode、shutdown）；`2` = NOTIFY（订阅 28 B、subsys-up 28 B） | `0x11dc`、`0x15a0`、`0x4120` 逐帧比对 |
| 4 | `check_status_work` 的 4 条请求 | ① usb GET idx0(ONLINE) ② wls GET idx0(ONLINE) ③ 任一在线 → battery GET idx4(CAPACITY) ④ 电量 ≤99% → battery GET idx7(VOLTAGE_NOW)，与 DT `qcom,shutdown-voltage` 比较后置 `+0x6fa` | `0x156c` 全函数，4 处 relocation 均 `.text+0x688` |
| 5 | `0x40/0x42/0x43/0x44/0x51` 语义 | **都不是通知**，是 REQ_RESP：`0x40`=无线固件握手（24 B 发/16 B 收，`+0xc==1` 置 `+0x30f`）、`0x41`=固件分片（144 B，直接 `pmic_glink_write`）、`0x42/0x43`=两阶段完成量（`+0x118`/`+0xf8`）、`0x44`=版本读取（12 B 请求，回包存 `+0x314`）、`0x50`=小米域 GET（回包 52/32/116 B 拷到 `+0x620`/`+0x628`/`+0x1f0`）、`0x51`=小米域 SET 应答（走通用 `0x2168`） | 逐分支 asm |

新增发现：

- `0x41` 在 02 的 opcode 表里没有——因为它在主跳转表里落到未识别分支（**只发不收**）。
- 无线升级用 `+0x30f` 作放行旗标、`+0xf8`/`+0x118` 作两阶段完成量，是模块里唯一绕过 `battery_chg_write` 的发送路径。
- `wls_prop_map[6]`（值 `0x03`）经 `0x34` 取回后缓存在 `bcdev+0x364`，被 `wls_psy_get_prop` 当作 property 3 直读，**不发请求**。

## 1. 未决 1：头第 4 字不对称（已解）

### 1.1 请求侧：`+0xc` 是 battery 槽位

```
    3344: 37f80336     	tbnz	w22, #0x1f, 0x33a8
    3348: d2900148     	mov	x8, #0x800a            // =32778
    334c: f2c00028     	movk	x8, #0x1, lsl #32      ; type = 1
    3350: 2901dbff     	stp	wzr, w22, [sp, #0xc]   ; +0xc = 0，+0x10 = 下标
    3354: b90017ff     	str	wzr, [sp, #0x14]       ; +0x14 = value = 0
    3358: f90003e8     	str	x8, [sp]               ; +0x0 = owner，+0x4 = type
    335c: b9416688     	ldr	w8, [x20, #0x164]      ; GET opcode（battery = 0x30）
    3364: 52800302     	mov	w2, #0x18              // =24
    336c: b9000be8     	str	w8, [sp, #0x8]         ; +0x8 = opcode
    3370: 94000000     	bl	0x3370                 ; R_AARCH64_CALL26 .text+0x688
```

决定性反证：`battery_psy_set_prop` 的 property `0x21` 分支**把常量 10 写进 `+0x10`**，而不是写 `0x21`：

```
    3648: d2c00148     	mov	x8, #0xa00000000       // =42949672960（低字 0，高字 0x0a）
    3650: b90017f5     	str	w21, [sp, #0x14]       ; value = val
    3654: f800c3e8     	stur	x8, [sp, #0xc]         ; +0xc = 0，+0x10 = 10
```

`battery_prop_map[10] = 0x21`（见 `04-PROP-MAP.md` §4），故 `+0x10` 携带的是 **map 下标**，`+0xc` 是上游 `struct qcom_battmgr_property_request` 里的 `__le32 battery` 槽位（单电池机型恒 0）。

### 1.2 响应侧：`+0xc` 直接是 prop_id

```
   2440: b9401684     	ldr	w4, [x20, #0x14]      ; result
   2444: 35000fe4     	cbnz	w4, 0x2640             ; 非 0 → printk 后丢弃（不 complete）
   2448: b9400e88     	ldr	w8, [x20, #0xc]        ; prop_id = 下标
   244c: b9416269     	ldr	w9, [x19, #0x160]      ; 条目数 25
   2450: 6b09011f     	cmp	w8, w9
   2454: 540000e2     	b.hs	0x2470             ; 越界丢弃，不 complete
   2458: b9401289     	ldr	w9, [x20, #0x10]       ; value
   245c: f940ae6a     	ldr	x10, [x19, #0x158]     ; 运行时副本
   2460: b8287949     	str	w9, [x10, x8, lsl #2]  ; cache[index] = value
```

对应上游 `struct qcom_battmgr_message.intval { property; value; result; }`（`drivers_power_supply_qcom_battmgr.c:125-136`）：请求比回包多一个 `battery` 槽位。**不对称是协议本身的设计，不是解析错误。**

## 2. 未决 2：`0x37` 与 `0x48`

### 2.1 `0x37` = shutdown 命令（12 B，无载荷）

`battery_chg_shutdown`（`0x2830`）：

```
    2850: d2900149     	mov	x9, #0x800a             // =32778
    2854: 927ef82b     	and	x11, x1, #0xfffffffffffffffd   ; x1 & ~2
    2858: f2c00029     	movk	x9, #0x1, lsl #32       ; type = 1
    285c: 528006ea     	mov	w10, #0x37              // =55
    2860: f100057f     	cmp	x11, #0x1
    2868: f90007e9     	str	x9, [sp, #0x8]          ; +0x0 = owner，+0x4 = type
    286c: b90013ea     	str	w10, [sp, #0x10]        ; +0x8 = 0x37
    2870: 540001a0     	b.eq	0x28a4                  ; 仅 (x1 & ~2) == 1 才发
    ; 不发时直接返回 0：
    2894: 2a1f03e0     	mov	w0, wzr
    ; 发送路径：
    28a4: d10ce013     	sub	x19, x0, #0x338
    28b8: 94000000     	bl	0x28b8                  ; printk
    28bc: 910023e1     	add	x1, sp, #0x8
    28c0: 52800182     	mov	w2, #0xc                // =12
    28c8: 94000000     	bl	0x28c8                  ; R_AARCH64_CALL26 .text+0x688
```

帧 = `{owner=0x800a, type=1, opcode=0x37}` 共 12 B。触发条件 `(x1 & ~2) == 1` 即 reboot notifier 的 `val` 去掉 `SYS_POWER_OFF`（bit1）后等于 `SYS_RESTART`：**只在重启时发，关机（val==2）不发**。

### 2.2 `0x48` 不是 rx opcode

主跳转表（`.rodata+0x9`，索引 `opcode-4`）第 `0x48-4 = 0x44` 项是默认值 `0xd0`，解析到 `0x24a8`：

```
    24a8: d503249f     	bti	j
    24ac: 90000000     	adrp	x0, 0x2000 <...>        ; R_AARCH64_ADR_PREL_PG_HI21 .rodata+0x24af
    24b0: 90000001     	adrp	x1, 0x2000 <...>        ; R_AARCH64_ADR_PREL_PG_HI21 .rodata+0xa0d
    24b4: 91000000     	add	x0, x0, #0x0            ; .rodata+0x24af = "Unknown opcode: %u."
    24b8: 91000021     	add	x1, x1, #0x0            ; .rodata+0xa0d  = "handle_message"
    24bc: 2a0803e2     	mov	w2, w8                  ; opcode
    24c0: 94000000     	bl	0x24c0                  ; printk
    24c4: 17ffffeb     	b	0x2470                  ; 返回 0，不 complete
```

即：若 ADSP 真的回 `0x48`，`.ko` 只会打印 `BATTERY_CHG: handle_message: Unknown opcode: 72.` 并让请求方 250 jiffies 后超时 `-110`。全仓 `mov #0x48` 的 3 处（`0xaf38`/`0xb058`/`0xb150`）都在 `wls_bin_store` 里，是**固件分片长度字段**，与 opcode 无关。

> 订正：`02-GLINK-CONTRACT.md` §4 把 `0x48` 标成「收（预留）/只 complete」，应为「**未识别**」；「只 complete」的是 `0x47`（主表 `0x47-4` 项 → `0x2464`）。

## 3. 未决 3：type 字段

| type | 出现位置 | 帧长 | 语义 |
| --- | --- | --- | --- |
| `1` | 属性 GET/SET、ship mode、shutdown、0x40、0x41、0x44、0x50/0x51 | 12 / 16 / 24 / 52 / 144 | REQ_RESP：带 opcode，等一次完成 |
| `2` | 订阅 `{0x800a,2,0x04,...}`、subsys-up | 28 | NOTIFY：无 transaction，ADSP 主动推 |

订阅帧（`battery_chg_subsys_up_work` `0x11b0`）：

```
    11d8: d2900149     	mov	x9, #0x800a             // =32778
    11dc: f2c00049     	movk	x9, #0x2, lsl #32       ; type = 2
    11e0: 5280008a     	mov	w10, #0x4               // =4（REQUEST_NOTIFICATION）
    11e4: 910023e1     	add	x1, sp, #0x8
    11e8: 52800382     	mov	w2, #0x1c               // =28
    11f4: f801c3ff     	stur	xzr, [sp, #0x1c]
    11f8: f80143ff     	stur	xzr, [sp, #0x14]
    11fc: f90007e9     	str	x9, [sp, #0x8]          ; +0x0 = owner，+0x4 = 2
    1200: b90013ea     	str	w10, [sp, #0x10]        ; +0x8 = 0x04
    1204: 94000000     	bl	0x1204                  ; battery_chg_write
    1208: 37f80980     	tbnz	w0, #0x1f, 0x1338
    120c: 52801900     	mov	w0, #0xc8               // =200
    1210: 94000000     	bl	0x1210                  ; msleep(200)
```

与上游 `qcom_battmgr_enable_worker()`（`drivers_power_supply_qcom_battmgr.c:1286-1299`，`.hdr.type = PMIC_GLINK_NOTIFY`、`.hdr.opcode = BATTMGR_REQUEST_NOTIFICATION`）**逐字节一致**。

## 4. 未决 4：`check_status_work` 的 4 条请求

函数 `battery_chg_check_status_work` `0x156c`（`0x1f8` B）。帧基址 `sp`，`+0xc` 恒 0，`+0x10` 是下标；4 次 `bl` 全部重定位到 `.text+0x688`（`battery_chg_write`）。

```
    158c: d10aa013     	sub	x19, x0, #0x2a8         ; work → bcdev
    1594: 39514808     	ldrb	w8, [x0, #0x452]
    1598: 35000728     	cbnz	w8, 0x167c              ; 已处理过 → 打印后重来
    159c: d2900154     	mov	x20, #0x800a            // =32778
    15a0: f2c00034     	movk	x20, #0x1, lsl #32      ; type = 1
    15a4: f800c3ff     	stur	xzr, [sp, #0xc]         ; +0xc = 0
    15a8: b90017ff     	str	wzr, [sp, #0x14]       ; value = 0
    15ac: f90003f4     	str	x20, [sp]               ; owner/type
    15b0: b9419e68     	ldr	w8, [x19, #0x19c]      ; usb GET opcode 0x32
    15b8: 52800302     	mov	w2, #0x18               // =24
    15c0: b9000be8     	str	w8, [sp, #0x8]
    15c4: 94000000     	bl	0x15c4                  ; ① usb idx0（+0x10 = 0）
    ; ② wls idx0
    15d8: b941d668     	ldr	w8, [x19, #0x1d4]      ; wls GET opcode 0x34
    15e8: b9000be8     	str	w8, [sp, #0x8]
    15ec: 94000000     	bl	0x15ec
    ; 任一在线才继续
    15f4: f940ca68     	ldr	x8, [x19, #0x190]      ; usb 副本
    15f8: b9400108     	ldr	w8, [x8]                ; usb cache[0] = ONLINE
    15fc: 35000088     	cbnz	w8, 0x160c
    1600: f940e668     	ldr	x8, [x19, #0x1c8]      ; wls 副本
    1604: b9400108     	ldr	w8, [x8]                ; wls cache[0] = ONLINE
    1608: 34000248     	cbz	w8, 0x1650             ; 都离线 → 返回
    ; ③ battery idx4 = CAPACITY
    1610: d2c00088     	mov	x8, #0x400000000        // =17179869184（+0x10 = 4）
    1618: b90017ff     	str	wzr, [sp, #0x14]
    161c: f800c3e8     	stur	x8, [sp, #0xc]
    1620: f90003e9     	str	x9, [sp]
    1624: b9416668     	ldr	w8, [x19, #0x164]      ; battery GET 0x30
    162c: 52800302     	mov	w2, #0x18
    1634: b9000be8     	str	w8, [sp, #0x8]
    1638: 94000000     	bl	0x1638
    1640: f940ae68     	ldr	x8, [x19, #0x158]
    1644: b9401108     	ldr	w8, [x8, #0x10]        ; battery cache[4]
    1648: 71018d1f     	cmp	w8, #0x63               ; <= 99 ?
    164c: 54000369     	b.ls	0x16b8                  ; 是 → ④
    ; ④ battery idx7 = VOLTAGE_NOW
    16bc: d2c000e8     	mov	x8, #0x700000000        // =30064771072（+0x10 = 7）
    16c4: b90017ff     	str	wzr, [sp, #0x14]
    16c8: f800c3e8     	stur	x8, [sp, #0xc]
    16d0: b9416668     	ldr	w8, [x19, #0x164]
    16d8: 52800302     	mov	w2, #0x18
    16e0: b9000be8     	str	w8, [sp, #0x8]
    16e4: 94000000     	bl	0x16e4
    ; 与 DT qcom,shutdown-voltage 比较
    16fc: f940ae68     	ldr	x8, [x19, #0x158]
    1700: b9423e62     	ldr	w2, [x19, #0x23c]      ; DT 阈值
    1704: 5289ba69     	mov	w9, #0x4dd3             // =19923
    1708: 72a20c49     	movk	w9, #0x1062, lsl #16   ; 0x10624dd3
    170c: b9401d08     	ldr	w8, [x8, #0x1c]        ; battery cache[7]
    1710: 9b097d08     	mul	x8, x8, x9
    1714: d366fd08     	lsr	x8, x8, #38             ; / 400
    1718: 6b02011f     	cmp	w8, w2
    171c: 540000e9     	b.ls	0x1738
    1720: ...                                 ; printk(.rodata+0xb6a)
    1738: ...                                 ; printk(.rodata+0x138)
    174c: 52800c80     	mov	w0, #0x64               // =100
    1750: 94000000     	bl	0x1750                  ; msleep(100)
    1754: 52800028     	mov	w8, #0x1
    1758: 391bea68     	strb	w8, [x19, #0x6fa]      ; 置 STATUS 覆盖旗标
    175c: 17ffffbd     	b	0x1650
```

语义链：**有线或无线任一在线时**读电量；电量 ≤99% 时读电压，除以 400 后与 DT `qcom,shutdown-voltage`（`probe` `0xba8: of_property_read_variable_u32_array` 写入 `bcdev+0x23c`）比较，触发后 `msleep(100)` 并置 `bcdev+0x6fa`。该旗标被三个 psy 的 `get_prop` 读取（`0x2e8c` usb / `0x3208` wls / `0x33c8` battery），用于覆盖上报的 STATUS。

## 5. 未决 5：`0x40/0x41/0x42/0x43/0x44/0x51`

### 5.1 `0x40` = 无线固件握手（24 B 发，16 B 收）

`wireless_fw_update`（`0x3f44`）：

```
    4110: 79412d09     	ldrh	w9, [x8, #0x96]         ; 固件版本高 16 位
    4114: 79412908     	ldrh	w8, [x8, #0x94]         ; 固件版本低 16 位
    4118: 7200029f     	tst	w20, #0x1              ; force 参数
    411c: d290014a     	mov	x10, #0x800a            // =32778
    4120: f2c0002a     	movk	x10, #0x1, lsl #32      ; type = 1
    4124: 33103d09     	bfi	w9, w8, #16, #16        ; 合成 u32 版本
    4128: 5280080b     	mov	w11, #0x40              // =64
    412c: 5a9f0128     	csinv	w8, w9, wzr, eq         ; force==0 → ~version；否则 0
    4130: 390c3e7f     	strb	wzr, [x19, #0x30f]      ; 先清放行旗标
    4134: f90007ea     	str	x10, [sp, #0x8]         ; +0x0 = owner，+0x4 = 1
    4138: 290223eb     	stp	w11, w8, [sp, #0x10]    ; +0x8 = 0x40，+0xc = 版本
    413c: 79463268     	ldrh	w8, [x19, #0x318]       ; 上次结果码
    4140: 910023e1     	add	x1, sp, #0x8
    4148: 290323e2     	stp	w2, w8, [sp, #0x18]     ; +0x10 = 入参 w2，+0x14 = 结果码
    414c: 52800302     	mov	w2, #0x18               // =24
    4150: 94000000     	bl	0x4150                  ; battery_chg_write
    4178: 394c3e68     	ldrb	w8, [x19, #0x30f]      ; 回包是否放行
    417c: 350000e8     	cbnz	w8, 0x4198
    4198: 52807d00     	mov	w0, #0x3e8              // =1000
    41a0: 94000000     	bl	0x41a0                  ; msleep(1000)
```

回包分支 `0x22ac`：`22b0: cmp x2,#0x10`（必须 16 B）、`22b8: ldr w8,[x20,#0xc]`、`22bc: cmp w8,#0x1`、`22c0: b.ne 0x2464`、`22c4: strb w8,[x19,#0x30f]`。**`+0x30f` = 无线固件升级放行旗标。**

### 5.2 `0x41` = 固件分片推送（144 B，直接 pmic_glink_write）

```
    41ec: f9400109     	ldr	x9, [x8]                ; 固件长度
    41f0: d347fd3a     	lsr	x26, x9, #7             ; 总片数 = 长度 >> 7
    41f4: 350000ba     	cbnz	w26, 0x4208
    4220: 12001939     	and	w25, w9, #0x7f          ; 末片余数
    4228: f90007e8     	str	x8, [sp, #0x8]          ; owner/type
    422c: 52800828     	mov	w8, #0x41              // =65
    4234: b90013e8     	str	w8, [sp, #0x10]         ; +0x8 = 0x41
    4258: 1100077b     	add	w27, w27, #0x1         ; 片序号
    425c: b90097fb     	str	w27, [sp, #0x94]        ; +0x8c = 片序号
    4260-429c: ldp/stp ×8                          ; 128 B 分片拷到 +0xc
    42ac: f9405260     	ldr	x0, [x19, #0xa0]        ; client 句柄
    42b4: 52801202     	mov	w2, #0x90               // =144
    42bc: 94000000     	bl	0x42bc                  ; pmic_glink_write（绕过 battery_chg_write）
    423c: 52800fa1     	mov	w1, #0x7d               // =125
    4244: 94000000     	bl	0x4244                  ; wait_for_completion_timeout(+0xf8)
```

帧 = `12 B 头 + 128 B 分片 + 4 B 片序号` = 144 B。**全模块唯一不经 `battery_chg_write` 三道闸门的发送路径**，完成量 `bcdev+0xf8`，超时 125 jiffies。

### 5.3 `0x42 / 0x43` = 两阶段完成量

```
    22cc: d503249f     	bti	j
    22d0: f100405f     	cmp	x2, #0x10
    22d4: 540014a1     	b.ne	0x2568                  ; 长度不符 → printk
    22d8: b9400e82     	ldr	w2, [x20, #0xc]
    22dc: 7100045f     	cmp	w2, #0x1
    22e0: 540015c1     	b.ne	0x2598
    22e4: 91046260     	add	x0, x19, #0x118         ; complete(&bcdev->wls_handshake)
    22e8: 14000061     	b	0x246c
    22ec: d503249f     	bti	j
    22f0: f100405f     	cmp	x2, #0x10
    22f4: 54001401     	b.ne	0x2574
    22f8: b9400e88     	ldr	w8, [x20, #0xc]
    22fc: 7100051f     	cmp	w8, #0x1
    2300: 54000b81     	b.ne	0x2470
    2304: 9103e260     	add	x0, x19, #0xf8          ; complete(&bcdev->wls_chunk)
    2308: 14000059     	b	0x246c
```

两个完成量分别对应 §5.1 的 `0x40`（等 `+0x118`）与 §5.2 的 `0x41` 分片（等 `+0xf8`），都要求 `data+0xc == 1`。

### 5.4 `0x44` = 无线固件版本读取（12 B 请求）

```
    44a0: d1002015     	sub	x21, x0, #0x8           ; kobj → bcdev
    44a4: d2900149     	mov	x9, #0x800a             // =32778
    44ac: f2c00029     	movk	x9, #0x1, lsl #32       ; type = 1
    44b0: 5280088a     	mov	w10, #0x44              // =68
    44b8: 52800182     	mov	w2, #0xc                // =12
    44c4: f90007e9     	str	x9, [sp, #0x8]
    44c8: b90013ea     	str	w10, [sp, #0x10]        ; +0x8 = 0x44
    44cc: 94000000     	bl	0x44cc                  ; battery_chg_write
    44d4: b94316a3     	ldr	w3, [x21, #0x314]      ; 读回缓存
    44e8: 94000000     	bl	0x44e8                  ; scnprintf("%#x.")
```

回包分支 `0x230c`：`2310: cmp x2,#0x10`、`2314: b.ne 0x2580`、`2318: ldr w8,[x20,#0xc]`、`231c: str w8,[x19,#0x314]`（无条件存）、`2320: b 0x2464`。

### 5.5 `0x50` = 小米域 GET（回包 32/16/96 B），`0x51` = SET 应答

```
    2324: d503249f     	bti	j
    2328: f100d05f     	cmp	x2, #0x34               ; 52 B
    232c: 540002a1     	b.ne	0x2380
    2330: f9431268     	ldr	x8, [x19, #0x620]       ; 目标缓冲
    2334: b4000268     	cbz	x8, 0x2380
    2338: a942268a     	ldp	x10, x9, [x20, #0x20]   ; data+0x20..0x2f
    233c: a9412e8c     	ldp	x12, x11, [x20, #0x10]  ; data+0x10..0x1f
    2340: a901250a     	stp	x10, x9, [x8, #0x10]
    2344: a9002d0c     	stp	x12, x11, [x8]          ; 共 32 B
    2348: 14000047     	b	0x2464                  ; complete
```

`0x50`（GET）与 `0x51`（SET）构成小米私有属性域（`xm_prop_map` 187 项全 0，运行期填充）。**服务端最小实现可完全不实现这两个 opcode**——属性轮询用不到它们。

## 6. 新增：bcdev 关键字段表

| 偏移 | 语义 | 证据 |
| --- | --- | --- |
| `+0x0` | `struct device *` | `0x26e0: ldr x0,[x19]` → `pm_wakeup_dev_event` |
| `+0x8` | debugfs kobj 基址 | `0x46c0: add x1,x0,#0x305`（→ `+0x30d`）、`0x44a0: sub x21,x0,#0x8` |
| `+0xa0` | `pmic_glink_client *` | `0x42ac: ldr x0,[x19,#0xa0]` → `pmic_glink_write` |
| `+0xa8` | 发送 mutex | `0x6d0: add x19,x20,#0xa8` → `mutex_lock` |
| `+0xd8` | 通用完成量 | `0x2468: add x0,x19,#0xd8` → `complete` |
| `+0xf8` | 无线分片完成量 | `0x2304` |
| `+0x118` | 无线握手完成量 | `0x22e4` |
| `+0x140` | Model 缓冲（128 B 目标） | `0x21d4` |
| `+0x150/158/160/164/168` | battery map / 副本 / 条目数 / GET / SET | `04-PROP-MAP.md` §2 |
| `+0x188/190/198/19c/1a0` | usb 域同上 | 同上 |
| `+0x1c0/1c8/1d0/1d4/1d8` | wls 域同上 | 同上 |
| `+0x1f8/200/208/20c/210` | xiaomi 域同上 | 同上 |
| `+0x23c` | DT `qcom,shutdown-voltage` | `0xba8` 写入，`0x1700` 读取 |
| `+0x240` | 通道 state（0 = 未就绪） | `0x6a4: ldar w8,[x8]` |
| `+0x2a8` | `check_status` 的 delayed_work | `0x158c: sub x19,x0,#0x2a8` |
| `+0x30c` | `block_tx`（debugfs bool，`.rodata+0x4d9`） | `0xea8` 创建 |
| `+0x30d` | `ship_mode_en`（debugfs bool） | `0x46c0` 写入、`0x2794: ldurb w8,[x0,#-0x13]` 读 |
| `+0x30e` | `is_debug_board`（Model == "Debug_Board"） | `0x2234: strb w8,[x19,#0x30e]` |
| `+0x30f` | 无线固件升级放行旗标 | `0x4130` 清、`0x22c4` 置、`0x4178` 读 |
| `+0x310` | 无线固件 CRC（u16） | `0x45a4: strh w8,[x20,#0x310]` |
| `+0x314` | 无线固件版本 / 升级耗时 ms | `0x231c` 写、`0x44d4`/`0x45e8` 读 |
| `+0x318` | 无线固件升级结果码（u16） | `0x413c` 读、`0x40c0: strh wzr,[x19,#0x318]` 清 |
| `+0x31c` | 无线升级超时 ms | `0x42dc: ldr w0,[x19,#0x31c]` → `__msecs_to_jiffies` |
| `+0x320/338` | reboot notifier ×2（优先级 0xff） | `0x28a4: sub x19,x0,#0x338` |
| `+0x358` | subsys-up 后的状态码 | `0x1214: ldr w20,[x19,#0x358]` |
| `+0x364` | `wls_prop_map[6]` 缓存（property 3 直读） | `0x1844` 写、`0x3158` 读 |
| `+0x370` | `generate_xm_charge_uvent` 的 work | `0x1784: sub x19,x0,#0x370` |
| `+0x620` | 小米 GET/SET 回包缓冲（32 B） | `0x2330` |
| `+0x628` | 小米回包第二块（32 B） | `0x2388` |
| `+0x6fa` | STATUS 覆盖旗标 | `0x1758` 写；`0x2e8c`/`0x3208`/`0x33c8` 读 |
| `+0x708` | `xm_batt_update_work` | `0xa38` 初始化 |

## 7. 仍真正未决

1. `0x41` 分片帧里 `+0xc` 起 128 B 是**原始固件字节**还是带偏移/校验，需真机抓包（`0x4260–0x429c` 是纯 `ldp/stp` 拷贝，未见变换）。
2. `0x40` 帧 `+0x10`（函数入参 `w2`）与 `+0x14`（`bcdev+0x318` 结果码）的确切语义。
3. `0x50` GET 的 52 B 回包里 `+0xc` 与 `+0x30` 两个未被读取的字。
4. `xm_prop_map` 187 项全 0，其运行期填充顺序（首次 `0x50` 交互）无静态证据。
5. `battery_psy_get_prop` 的 property 61→62 改写（`0x32e8/0x32f4`）意图仍不明（疑似 vendor 别名）。
6. `+0x452`（`check_status_work` 入口的 `ldrb`）与 `+0x23c` 阈值在 `probe` 之外的写入点未穷举。

## 8. 复现命令

```bash
K=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
# 未决 1：请求 +0xc 槽位与 +0x10 下标
llvm-objdump -dr --start-address=0x3344 --stop-address=0x3378 "$K"
llvm-objdump -dr --start-address=0x3648 --stop-address=0x3664 "$K"
# 未决 1：回包 cache[index]
llvm-objdump -dr --start-address=0x2440 --stop-address=0x2474 "$K"
# 未决 2：shutdown 帧（12 B）
llvm-objdump -dr --start-address=0x2830 --stop-address=0x28d0 "$K"
# 未决 2：0x48 落在未识别分支
llvm-objdump -dr --start-address=0x24a8 --stop-address=0x24c8 "$K"
llvm-readelf -p .rodata "$K" | grep -E '\[ *(24af|a0d)\]'
# 未决 3：订阅帧 type=2
llvm-objdump -dr --start-address=0x11d8 --stop-address=0x1214 "$K"
# 未决 4：check_status_work 四条请求
llvm-objdump -dr --start-address=0x159c --stop-address=0x1760 "$K"
# 未决 5：无线升级全流程
llvm-objdump -dr --start-address=0x3f44 --stop-address=0x43e4 "$K"
llvm-objdump -dr --start-address=0x44a0 --stop-address=0x44d8 "$K"
llvm-objdump -dr --start-address=0x2324 --stop-address=0x2350 "$K"
```
