# 04 — prop 映射与 wire prop_id 语义（charger .ko 反编译）

> 目标件：`/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko`
> 247,776 B，ELF64 LSB aarch64 relocatable，BuildID `e852b83c589f773d7cb09e6793ac59fd33086c58`
> 所有地址均为**节内偏移**（VMA 全 0），与 `01-SYMBOL-MAP.md` §1.2 一致。
> 证据一律来自 `llvm-objdump -d/-dr`、`llvm-readelf -x .rodata`、`llvm-nm -S` 的原始输出。

## 0. 结论摘要

1. `.ko` 在 `battery_chg_probe` 里为四个属性域各建一条**五字段记录**（`0x7c4–0x844`）：
   `{map 指针, 运行时副本指针, 条目数, GET opcode, SET opcode}`。四域分别是 battery / usb / wireless / xiaomi。
2. 四张 map 在 `.rodata` 里分别是 `0x2d68`(25 项) / `0x2dcc`(13 项) / `0x2e00`(7 项) / `0x2e1c`(187 项，全 0)。
3. **wire 上的 `prop_id` 就是该域 map 数组的下标**，不是 map 里的值。三处独立证据：`battery_psy_get_prop`(0x3348–0x3370)、`battery_psy_set_prop`(0x35e0/0x3654)、rx 回包侧(0x2448/0x23a4/0x23c8)。
4. map 里的值才是 `enum power_supply_property`（小米 vendor 版），用于 `psy` 属性表匹配。
5. 回包方向反过来：**服务端必须原样回显请求里的下标**，`.ko` 用下标做边界检查后写入 `bcdev->*_prop_cache[index]`，越界直接丢弃（`b.hs 0x2470`，且**不 complete**，请求方会 250 jiffies 超时）。
6. 已用 `check_status_work` 的三处真实取值反向锚定三个下标：idx4 = CAPACITY、idx7 = VOLTAGE_NOW、usb/wls idx0 = ONLINE。

## 1. 取证方法

```bash
K=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
llvm-nm -S --defined-only  "$K" | grep -iE 'prop_map|psy_get|psy_set'
llvm-readelf -x .rodata    "$K" | sed -n '2,12p'      # 跳转表 + map 原始字节
llvm-objdump -d --start-address=0x7c4  --stop-address=0x8b0 "$K"
llvm-objdump -d --start-address=0x32a8 --stop-address=0x34b8 "$K"
llvm-objdump -d --start-address=0x34b8 --stop-address=0x372c "$K"
llvm-objdump -d --start-address=0x234c --stop-address=0x2464 "$K"
```

符号尺寸（`llvm-nm -S`）：

| 符号 | 偏移 | 大小 |
| --- | --- | --- |
| `battery_prop_map` | `0x2d68` | `0x64` = 100 B = 25×4 |
| `usb_prop_map` | `0x2dcc` | `0x34` = 52 B = 13×4 |
| `wls_prop_map` | `0x2e00` | `0x1c` = 28 B = 7×4 |
| `xm_prop_map` | `0x2e1c` | `0x2ec` = 748 B = 187×4 |
| `battery_psy_get_prop` | `0x32a8` | `0x210` |
| `battery_psy_set_prop` | `0x34b8` | `0x274` |
| `usb_psy_get_prop` | `0x2d68`→实际 `0x2d68` 是 map；函数在 `0x2d68` 之后 | `0x1bc` |
| `wls_psy_get_prop` | `0x3110` | `0x198` |
| `usb_psy_set_prop` | `0x2f24` | `0x1d8` |
| `wls_psy_set_prop` | `0x38d8` | `0x10`（空实现） |

> 注：`usb_psy_get_prop` 的 `llvm-nm` 地址与 `usb_prop_map` 都是 `0x2d68`，因为 map 在 `.rodata`、函数在 `.text`，两节各自从 0 起算。写文档时不要混用。

## 2. 四域记录结构（probe `0x7c4–0x844` 原始 asm）

```
    7c4: 90000008     	adrp	x8, 0x0 <__cfi_check>          ; R_AARCH64_ADR_PREL_PG_HI21 .rodata+0x2d68
    7c8: 91000108     	add	x8, x8, #0x0                  ; R_AARCH64_ADD_ABS_LO12_NC .rodata+0x2d68
    7cc: f900a808     	str	x8, [x0, #0x150]              ; bcdev+0x150 = battery map 指针
    7d0: d2800328     	mov	x8, #0x19                     ; 25 项
    7d4: f2c00608     	movk	x8, #0x30, lsl #32            ; 高半 = 0x30 → +0x164 = GET opcode
    7d8: f900b008     	str	x8, [x0, #0x160]              ; bcdev+0x160 = {count=25, get=0x30}
    7dc: 52800628     	mov	w8, #0x31                     ; 0x31 = SET
    7e0: b9016808     	str	w8, [x0, #0x168]              ; bcdev+0x168 = SET opcode
    7e4: 90000008     	adrp	x8, 0x0 <__cfi_check>          ; .rodata+0x2dcc
    7e8: 91000108     	add	x8, x8, #0x0
    7ec: f900c408     	str	x8, [x0, #0x188]              ; bcdev+0x188 = usb map
    7f0: d28001a8     	mov	x8, #0xd                      ; 13 项
    7f4: f2c00648     	movk	x8, #0x32, lsl #32            ; GET 0x32
    7f8: f900cc08     	str	x8, [x0, #0x198]
    7fc: 52800668     	mov	w8, #0x33                     ; SET 0x33
    800: b901a008     	str	w8, [x0, #0x1a0]
    804: 90000008     	adrp	x8, 0x0 <__cfi_check>          ; .rodata+0x2e00
    808: 91000108     	add	x8, x8, #0x0
    80c: f900e008     	str	x8, [x0, #0x1c0]              ; bcdev+0x1c0 = wls map
    810: d28000e8     	mov	x8, #0x7                      ; 7 项
    814: f2c00688     	movk	x8, #0x34, lsl #32            ; GET 0x34
    818: f900e808     	str	x8, [x0, #0x1d0]
    81c: 528006a8     	mov	w8, #0x35                     ; SET 0x35
    820: b901d808     	str	w8, [x0, #0x1d8]
    824: 90000008     	adrp	x8, 0x0 <__cfi_check>          ; .rodata+0x2e1c
    828: 91000108     	add	x8, x8, #0x0
    82c: f900fc08     	str	x8, [x0, #0x1f8]              ; bcdev+0x1f8 = xiaomi map
    830: d2801768     	mov	x8, #0xbb                     ; 187 项
    834: f2c00a08     	movk	x8, #0x50, lsl #32            ; GET 0x50
    838: f9010408     	str	x8, [x0, #0x208]
    83c: 52800a28     	mov	w8, #0x51                     ; SET 0x51
    844: b9021008     	str	w8, [x0, #0x210]
```

整理成表：

| 域 | map 指针 | 运行时副本 | 条目数 | GET | SET |
| --- | --- | --- | --- | --- | --- |
| battery | `bcdev+0x150` ← `.rodata+0x2d68` | `+0x158` | `+0x160` = 25 | `+0x164` = 0x30 | `+0x168` = 0x31 |
| usb | `+0x188` ← `.rodata+0x2dcc` | `+0x190` | `+0x198` = 13 | `+0x19c` = 0x32 | `+0x1a0` = 0x33 |
| wireless | `+0x1c0` ← `.rodata+0x2e00` | `+0x1c8` | `+0x1d0` = 7 | `+0x1d4` = 0x34 | `+0x1d8` = 0x35 |
| xiaomi | `+0x1f8` ← `.rodata+0x2e1c` | `+0x200` | `+0x208` = 187 | `+0x20c` = 0x50 | `+0x210` = 0x51 |

## 3. 运行时副本（probe `0x848–0x8ac`）

map 本身是只读常量，`probe` 用 `devm_kmalloc` 另开四块可写缓存，**map 只用来做属性号→下标搜索**，值落在副本里。

```
    848: 52800c81     	mov	w1, #0x64                     ; 100 B = 25×4（battery 副本）
    84c: 5281b802     	mov	w2, #0xdc0                    ; GFP 标志
    850: aa1303e0     	mov	x0, x19
    854: 94000000     	bl	0x854                          ; R_AARCH64_CALL26 devm_kmalloc
    858: f900ae80     	str	x0, [x20, #0x158]
    85c: b40014c0     	cbz	x0, 0xaf4                      ; 分配失败 → probe 错误路径
    860: b9419a88     	ldr	w8, [x20, #0x198]              ; usb 条目数 13
    86c: d37ef501     	lsl	x1, x8, #2                     ; 13×4
    870: 94000000     	bl	0x870                          ; devm_kmalloc
    874: f900ca80     	str	x0, [x20, #0x190]
    87c: b941d288     	ldr	w8, [x20, #0x1d0]              ; wls 条目数 7
    888: d37ef501     	lsl	x1, x8, #2
    88c: 94000000     	bl	0x88c
    890: f900e680     	str	x0, [x20, #0x1c8]
    898: b9420a88     	ldr	w8, [x20, #0x208]              ; xiaomi 条目数 187
    8a4: d37ef501     	lsl	x1, x8, #2                     ; 748 B
    8a8: 94000000     	bl	0x8a8
    8ac: f9010280     	str	x0, [x20, #0x200]
```

## 4. `battery_prop_map`（25 项，`.rodata+0x2d68`）

原始字节（`llvm-readelf -x .rodata`，`0x2d60` 行起）：

```
0x2d60  .......... 00 02 03 01 2e 00 0e 0c 08 11 21 22 1d 33 06 1c 07 16 18 48 3e 3c 00 14 15
```

| idx | 值 | `.ko` 内可证语义 | 判定依据 |
| --- | --- | --- | --- |
| 0 | 0x00 | STATUS | `battery_psy_get_prop` `33b0: cbnz w21` 对 property 0 走单独分支读缓存；`K60Battmgr.c:23` 亦用 `{0x30,0}` |
| 1 | 0x02 | 未定 | — |
| 2 | 0x03 | PRESENT | `K60Battmgr.c:24` `{0x30,2}`；map 值 0x03 与 mainline `PRESENT` 一致 |
| 3 | 0x01 | 未定 | — |
| 4 | **0x2e** | **CAPACITY** | `check_status_work` `1638: bl battery_chg_write`（+0x10=4）后 `1644: ldr w8,[x8,#0x10]` 读 cache[4] 并 `1648: cmp w8,#0x63`（99）比较 → 只能是电量百分比 |
| 5 | 0x00 | 未定 | — |
| 6 | 0x0e | 未定 | — |
| 7 | **0x0c** | **VOLTAGE_NOW** | `check_status_work` `16e4: bl battery_chg_write`（+0x10=7）后 `170c: ldr w8,[x8,#0x1c]` 读 cache[7]，再 `1704/1708/1710/1714` 用魔数 `0x10624dd3` + `lsr #38` 做 **除以 400**，与 `bcdev+0x23c` 阈值比较 → 电压 |
| 8 | 0x08 | 未定 | — |
| 9 | 0x11 | CURRENT_NOW | `K60Battmgr.c:27` `{0x30,9}`；map 值 0x11=17 与 mainline `CURRENT_NOW` 一致 |
| 10 | **0x21** | 见 §7.2（SET 特例） | `battery_psy_set_prop` `3548: b.eq 0x3608` 命中 property 0x21，且该分支硬编码 `+0x10 = 0x0a`（=10） |
| 11 | 0x22 | 未定 | — |
| 12 | **0x1d** | 见 §7.2（SET 特例） | `battery_psy_set_prop` `3548` 之前 `3544: cmp w21,#0x1d` → `0x35b4` 分支 |
| 13 | 0x33 | TEMPERATURE | `K60Battmgr.c:28` `{0x30,13}` |
| 14 | 0x06 | 未定 | — |
| 15 | 0x1c | 未定 | — |
| 16 | 0x07 | CYCLE_COUNT | `K60Battmgr.c:29` `{0x30,16}`；map 值 7 与 mainline 一致 |
| 17 | 0x16 | CHARGE_FULL_DESIGN | `K60Battmgr.c` `{0x30,17}`；map 值 22 与 mainline 一致 |
| 18 | 0x18 | CHARGE_FULL | `{0x30,18}`；map 值 24 与 mainline 一致 |
| 19 | **0x48** | **MODEL_NAME** | `battery_chg_callback` `21cc: cmp x2,#0x90`（144 = 12 头 + 128 + 对齐）把 `data+0x10` 起 128 B 拷到 `bcdev+0x140` 并 `strcmp` 与 `"Debug_Board"` 比较；map 值 72 与 mainline 一致 |
| 20 | 0x3e | TIME_TO_FULL_AVG | `{0x30,20}` |
| 21 | 0x3c | TIME_TO_EMPTY_AVG | `{0x30,21}` |
| 22 | 0x00 | 未定 | — |
| 23 | 0x14 | 未定 | — |
| 24 | 0x15 | 未定 | — |

**重要**：map 值是小米 vendor `enum power_supply_property`。已锚定的 0x00/0x04/0x07/0x0c/0x16/0x18/0x48 与 mainline 数值相同，但 **CAPACITY 是 0x2e(46) 而 mainline 是 41**、**TEMPERATURE 是 0x33(51) 而 mainline 是 44** —— 说明 vendor 枚举在中间插入了条目，不能用 mainline 枚举直接反查。完整枚举需小米 `include/linux/power_supply.h`（本仓与参考源均无）。

## 5. `usb_prop_map` / `wls_prop_map` / `xm_prop_map`

`usb_prop_map`（13 项）：`04 0c 08 11 10 25 00 40 00 00 33 00 00`

| idx | 值 | 语义 |
| --- | --- | --- |
| 0 | 0x04 | **ONLINE**（`check_status_work` `15f8: ldr w8,[x8]` 读 usb cache[0]，`15fc: cbnz` 即在线；map 值 4 = mainline `ONLINE`） |
| 1 | 0x0c | VOLTAGE_NOW（`K60Battmgr.c` `{0x32,1}` UsbVoltage） |
| 2 | 0x08 | 未定 |
| 3 | 0x11 | CURRENT_NOW |
| 4 | 0x10 | CURRENT_MAX（`{0x32,4}` UsbMaxCurrent；mainline 16） |
| 5 | 0x25 | INPUT_CURRENT_LIMIT（`{0x32,5}` UsbInputLimit） |
| 6 | 0x00 | 未定 |
| 7 | 0x40 | ADAP_TYPE（`{0x32,7}` UsbAdapter；mainline `USB_TYPE`=0x40 附近） |
| 8–9 | 0x00 | 未定 |
| 10 | 0x33 | 未定 |
| 11–12 | 0x00 | 未定 |

`wls_prop_map`（7 项）：`04 0c 08 11 10 00 03`

| idx | 值 | 语义 |
| --- | --- | --- |
| 0 | 0x04 | **ONLINE**（`check_status_work` `1604: ldr w8,[x8]` 读 wls cache[0]） |
| 1 | 0x0c | VOLTAGE_NOW |
| 2 | 0x08 | 未定 |
| 3 | 0x11 | CURRENT_NOW |
| 4 | 0x10 | CURRENT_MAX |
| 5 | 0x00 | 未定 |
| 6 | **0x03** | **无请求直读**：`wls_psy_get_prop` `314c: cmp w19,#0x3` → `3158: ldr w8,[x22,#0x364]` 直接返回 `bcdev+0x364`，**不发 0x34 请求**（此域唯一的本地属性） |

`xm_prop_map`（187 项）：`.rodata` 内**全 0**，运行期由 `0x50/0x51` 交互填充，无法静态判定语义。

## 6. 核心结论：wire `prop_id` = map 下标

### 6.1 发送侧（`battery_psy_get_prop` `0x32a8`）

```
    32d8: 94000000     	bl	0x32d8          ; R_AARCH64_CALL26 power_supply_get_drvdata
    32dc: 12800788     	mov	w8, #-0x3d      ; -61 = -ENODATA，默认返回值
    32e0: b9000268     	str	w8, [x19]
    32e4: b9416008     	ldr	w8, [x0, #0x160]     ; 条目数 25
    32e8: 7100f6bf     	cmp	w21, #0x3d           ; property == 61 ?
    32ec: 528007c9     	mov	w9, #0x3e            ; 62
    32f4: 1a950135     	csel	w21, w9, w21, eq     ; 61 被改写成 62
    32f8: 34000128     	cbz	w8, 0x331c
    32fc: f940aa89     	ldr	x9, [x20, #0x150]    ; map 指针
    3300: aa1f03f6     	mov	x22, xzr              ; x22 = 下标
    3304: b876792a     	ldr	w10, [x9, x22, lsl #2]   ; map[i]
    3308: 6b15015f     	cmp	w10, w21             ; == 用户请求的 property ?
    330c: 540001c0     	b.eq	0x3344
    3310: 910006d6     	add	x22, x22, #0x1
    3314: eb16011f     	cmp	x8, x22
    3318: 54ffff61     	b.ne	0x3304
    331c: ...                                       ; 未找到 → printk + -2
    3344: 37f80336     	tbnz	w22, #0x1f, 0x33a8  ; 下标异常保护
    3348: d2900148     	mov	x8, #0x800a          ; owner 32778
    334c: f2c00028     	movk	x8, #0x1, lsl #32    ; type = 1 (REQ_RESP)
    3350: 2901dbff     	stp	wzr, w22, [sp, #0xc] ; +0xc = 0，+0x10 = 下标
    3354: b90017ff     	str	wzr, [sp, #0x14]     ; +0x14 = value = 0
    3358: f90003e8     	str	x8, [sp]
    335c: b9416688     	ldr	w8, [x20, #0x164]    ; GET opcode（battery = 0x30）
    3364: 52800302     	mov	w2, #0x18            ; 24 B
    336c: b9000be8     	str	w8, [sp, #0x8]       ; +0x8 = opcode
    3370: 94000000     	bl	0x3370               ; R_AARCH64_CALL26 .text+0x688 = battery_chg_write
```

→ 请求帧 = `{owner@+0, type=1@+4, opcode@+8, 0@+0xc, 下标@+0x10, 0@+0x14}`，24 B。

### 6.2 接收侧（`battery_chg_callback` 回包分支）

```
   2440: b9401684     	ldr	w4, [x20, #0x14]     ; result
   2444: 35000fe4     	cbnz	w4, 0x2640           ; result != 0 → printk 后丢弃
   2448: b9400e88     	ldr	w8, [x20, #0xc]      ; ★ +0xc = prop_id（下标）
   244c: b9416269     	ldr	w9, [x19, #0x160]    ; 条目数 25
   2450: 6b09011f     	cmp	w8, w9
   2454: 540000e2     	b.hs	0x2470           ; 越界 → 直接返回，不 complete
   2458: b9401289     	ldr	w9, [x20, #0x10]     ; value
   245c: f940ae6a     	ldr	x10, [x19, #0x158]   ; 运行时副本
   2460: b8287949     	str	w9, [x10, x8, lsl #2]    ; cache[index] = value
   2464: d503249f     	bti	j
   2468: 91036260     	add	x0, x19, #0xd8       ; &bcdev->wait
   246c: 94000000     	bl	0x246c               ; R_AARCH64_CALL26 complete
   2470: d503249f     	bti	j                    ; 返回 0（未 complete）
```

同构三份（usb 13 项 / wls 7 项）：

```
   23a4: b9400e88     	ldr	w8, [x20, #0xc]     ; usb 回包 prop_id
   23a8: b9419a69     	ldr	w9, [x19, #0x198]   ; 13
   23b0: 54000602     	b.hs	0x2470
   23b4: b9401289     	ldr	w9, [x20, #0x10]
   23b8: f940ca6a     	ldr	x10, [x19, #0x190]
   23bc: 14000029     	b	0x2460
   23c8: b9400e88     	ldr	w8, [x20, #0xc]     ; wls 回包 prop_id
   23cc: b941d269     	ldr	w9, [x19, #0x1d0]   ; 7
   23d4: 540004e2     	b.hs	0x2470
   23d8: b9401289     	ldr	w9, [x20, #0x10]
   23dc: f940e66a     	ldr	x10, [x19, #0x1c8]
   23e0: 14000020     	b	0x2460
```

### 6.3 推论（对服务端的要求）

1. 服务端处理 `0x30/0x32/0x34/0x50` 时，**回包的 `+0xc` 必须逐字节等于请求里的 `+0x10`**。
2. 越界下标不会报错，只会**静默丢弃且不 complete** → 请求线程在 250 jiffies 后拿到 `-110`（`battery_chg_write` `748: mov w21,#-0x6e`）。
3. `result`（`+0x14`）非 0 时同样丢弃（`2444: cbnz w4`），但仍会走 0x2640 打印错误，**不 complete**。
4. 长度必须精确：`24`（普通属性）、`32`（usb/wls 也可 32，见 `2248/2280`）、`52`（`0x34`=`0x50` 域 52 B）、`144`（battery Model）。其它长度走 `0x234c/0x2380/0x23e4` 的二次分派或直接 printk 丢弃。

## 7. GET / SET 消费点

### 7.1 GET：请求 → 缓存 → 特例

`battery_psy_get_prop` 在 `3370` 发出请求后（阻塞等待完成），继续：

```
    3374: 37f80800     	tbnz	w0, #0x1f, 0x3474    ; battery_chg_write 失败 → 返回错误
    3378: 510086a8     	sub	w8, w21, #0x21       ; property - 0x21
    337c: 71009d1f     	cmp	w8, #0x27            ; 0..39 → 走 .rodata 跳转表
    3380: 54000188     	b.hi	0x33b0
    3384: 90000009     	adrp	x9, 0x3000
    338c: 1000008a     	adr	x10, 0x339c
    ; 表项示例：
    339c: d503249f     	bti	j
    33a0: b9423288     	ldr	w8, [x20, #0x230]   ; 直接取 bcdev+0x230（本地字段）
    33a4: 14000033     	b	0x3470
    ; property == 0（STATUS）分支：
    33b0: 35000155     	cbnz	w21, 0x33d8
    33b4: f940ae88     	ldr	x8, [x20, #0x158]
    33b8: b8767908     	ldr	w8, [x8, x22, lsl #2]   ; cache[index]
    33bc: 7100051f     	cmp	w8, #0x1
    33c0: b9000268     	str	w8, [x19]
    33c4: 54000581     	b.ne	0x3474
    33c8: 395bea88     	ldrb	w8, [x20, #0x6fa]   ; check_status_work 置的旗标
    33cc: 34000548     	cbz	w8, 0x3474
```

→ 属性 0x21–0x48 中的一部分**不发请求**，直接读本地字段（如 `+0x230`）；property 0（STATUS）会被 `+0x6fa` 覆盖。

`usb_psy_get_prop` / `wls_psy_get_prop` 同构，只是域记录不同：

```
    2d98: 94000000     	bl	0x2d98       ; power_supply_get_drvdata
    2d9c: 12800788     	mov	w8, #-0x3d   ; -ENODATA
    2da4: b9419808     	ldr	w8, [x0, #0x198]   ; usb 条目数 13
    2db0: f940c6c9     	ldr	x9, [x22, #0x188]  ; usb map
    2db8: b874792a     	ldr	w10, [x9, x20, lsl #2]
    2dc0: 540001c0     	b.eq	0x2df8
    ; wls：property == 3 直读本地字段
    314c: 71000e7f     	cmp	w19, #0x3
    3154: 540000a1     	b.ne	0x3168
    3158: b94366c8     	ldr	w8, [x22, #0x364]  ; bcdev+0x364
    3160: b9000288     	str	w8, [x20]
    3164: 14000043     	b	0x3270
    3168: b941d2c8     	ldr	w8, [x22, #0x1d0]  ; wls 条目数 7
    3170: f940e2c9     	ldr	x9, [x22, #0x1c0]  ; wls map
```

### 7.2 SET：只有两个属性可写

`battery_psy_set_prop`（`0x34b8`，`0x274` B）：

```
    34e8: 94000000     	bl	0x34e8            ; power_supply_get_drvdata
    34ec: b9416008     	ldr	w8, [x0, #0x160]      ; 25
    34f8: f940aa89     	ldr	x9, [x20, #0x150]     ; map
    3500: b873792a     	ldr	w10, [x9, x19, lsl #2] ; map[i]
    3504: 6b15015f     	cmp	w10, w21
    3508: 540001c0     	b.eq	0x3540
    3538: 12800033     	mov	w19, #-0x2            ; 找不到 → -2
    3540: 37f800d3     	tbnz	w19, #0x1f, 0x3558
    3544: 710076bf     	cmp	w21, #0x1d            ; property 0x1d
    3548: 54000360     	b.eq	0x35b4
    354c: 710086bf     	cmp	w21, #0x21            ; property 0x21
    3550: 540005c0     	b.eq	0x3608
    3554: 128002b3     	mov	w19, #-0x16           ; 其它一律 -22 (EINVAL，只读)
    ; ---- property 0x1d ----
    35b4: b94002d5     	ldr	w21, [x22]            ; val
    35d0: 710002bf     	cmp	w21, #0x0
    35dc: 5a9fa2a9     	csinv	w9, w21, wzr, ge     ; 负数钳到 0
    35e0: 2901cfff     	stp	wzr, w19, [sp, #0xc]  ; +0xc=0，+0x10 = 下标（运行时搜出，=12）
    35e4: b90017e9     	str	w9, [sp, #0x14]       ; value
    35ec: b9416a88     	ldr	w8, [x20, #0x168]     ; SET opcode 0x31
    35f4: 52800302     	mov	w2, #0x18             ; 24 B
    35fc: b9000be8     	str	w8, [sp, #0x8]
    3600: 94000000     	bl	0x3600               ; battery_chg_write
    ; ---- property 0x21 ----
    3608: b94002d5     	ldr	w21, [x22]
    360c: b9423a83     	ldr	w3, [x20, #0x238]     ; 上限字段
    3628: b9423a88     	ldr	w8, [x20, #0x238]
    362c: 340004a8     	cbz	w8, 0x36c0            ; 上限为 0 → 直接成功返回
    3634: 128002b3     	mov	w19, #-0x16           ; 先置 -22
    3638: 37fff915     	tbnz	w21, #0x1f, 0x3558   ; val < 0 → -22
    363c: 6b15011f     	cmp	w8, w21
    3640: 54fff8cd     	b.le	0x3558            ; val >= 上限 → -22
    3648: d2c00148     	mov	x8, #0xa00000000      ; ★ 硬编码 +0x10 = 0x0a = 10
    3650: b90017f5     	str	w21, [sp, #0x14]      ; value = val
    3654: f800c3e8     	stur	x8, [sp, #0xc]        ; +0xc = 0，+0x10 = 10
    365c: b9416a88     	ldr	w8, [x20, #0x168]     ; SET 0x31
```

**`0x0a` 这个硬编码是「下标 = wire prop_id」的决定性证据**：`battery_prop_map[10] = 0x21`，代码在 property 0x21 的 SET 分支里直接把 `10` 写进 `+0x10`，而不是写 `0x21`。

`usb_psy_set_prop`（`0x2f24`）同构；`wls_psy_set_prop`（`0x38d8`，`0x10` B）是**空实现**（直接返回 0），即无线属性不可写。

## 8. 与 `drivers/PongPower/K60Battmgr.c` 字段表交叉验证

`K60Battmgr.c:23-29` 的 `fields[K60BmFields]` 用 `{opcode, property}`，其中 `property` 就是这里说的**下标**：

| 字段 | `{opcode, idx}` | map 值 | 本文字节表一致？ |
| --- | --- | --- | --- |
| Status | `{0x30, 0}` | 0x00 | ✅ |
| Present | `{0x30, 2}` | 0x03 | ✅ |
| Capacity | `{0x30, 4}` | 0x2e | ✅（且被 `check_status_work` 独立证实） |
| Voltage | `{0x30, 7}` | 0x0c | ✅（除以 400 独立证实） |
| Current | `{0x30, 9}` | 0x11 | ✅ |
| Temperature | `{0x30, 13}` | 0x33 | ✅ |
| UsbOnline | `{0x32, 0}` | 0x04 | ✅（`check_status_work` 独立证实） |
| UsbVoltage | `{0x32, 1}` | 0x0c | ✅ |
| UsbAdapter | `{0x32, 7}` | 0x40 | ✅ |
| UsbMaxCurrent | `{0x32, 4}` | 0x10 | ✅ |
| UsbInputLimit | `{0x32, 5}` | 0x25 | ✅ |
| WirelessOnline | `{0x34, 0}` | 0x04 | ✅（`check_status_work` 独立证实） |
| Full | `{0x30, 18}` | 0x18 | ✅ |
| Design | `{0x30, 17}` | 0x16 | ✅ |
| Cycles | `{0x30, 16}` | 0x07 | ✅ |
| TimeToFull | `{0x30, 20}` | 0x3e | ✅ |
| TimeToEmpty | `{0x30, 21}` | 0x3c | ✅ |
| Model | `{0x30, 19}` | 0x48 | ✅（144 B 长度独立证实） |

结论：`K60Battmgr.c` 的字段表与 `.ko` 的 map 下标**完全自洽**，可作为 L1 服务端实现的权威属性索引。

## 9. 与上游 Linux `qcom_battmgr.c` 对照

| 项 | 上游（`E:/k60-work/scratch/power-work/assets/linux/drivers_power_supply_qcom_battmgr.c`） | 本 .ko |
| --- | --- | --- |
| battery map 条目 | `sm8350_bat_prop_map[]` `:401-421` = 19 项 | 25 项 |
| usb map 条目 | `sm8350_usb_prop_map[]` `:715-723` = 7 项 | 13 项 |
| wls map 条目 | `sm8350_wls_prop_map[]` `:839-845` = 5 项 | 7 项 |
| 额外域 | 无 | xiaomi 187 项（`0x50/0x51`） |
| wire prop_id 语义 | `property` 字段即枚举值本身 | **枚举值在 map 里的下标** |
| 请求结构 | `qcom_battmgr_property_request` `:99-104` `{hdr; battery; property; value}` | `{owner,type,opcode,0,index,value}` 同布局 |
| 回包结构 | `qcom_battmgr_message.intval` `:125-136` `{property; value; result}` | `+0xc=index, +0x10=value, +0x14=result` 同布局 |

→ 上游实现**不能直接照搬**：它把枚举值直接上线，小米版多了一层「枚举值 → 下标」的间接。这是本仓 L1 服务端最容易写错的一点。

## 10. 未决

1. `battery_prop_map` 中 14 个下标（1/3/5/6/8/11/14/15/22/23/24 等）的枚举名，需小米 `power_supply.h`。
2. `usb_prop_map` 中 0x08/0x11/0x33 等与 `wls_prop_map` 中 0x08/0x11/0x10 的确切属性名。
3. `xm_prop_map` 187 项全 0，静态不可判；需真机 `0x50/0x51` 抓包。
4. `battery_psy_get_prop` 中 `.rodata` 跳转表（`0x3384/0x338c`）覆盖的 40 个属性，其表项目标未逐项展开。
5. property 61→62 的改写（`32e8/32f4`）意图未定（疑似 vendor 兼容别名）。

## 11. 复现命令

```bash
K=/mnt/e/k60-work/firmware/qti_battery_charger_main_m81.ko
# 1) map 尺寸
llvm-nm -S --defined-only "$K" | grep -E 'prop_map$'
# 2) map 原始字节（25/13/7 项）
llvm-readelf -x .rodata "$K" | sed -n '/0x00002d60/,/0x00002e20/p'
# 3) probe 四域记录
llvm-objdump -dr --start-address=0x7c4 --stop-address=0x848 "$K"
# 4) 运行时副本分配
llvm-objdump -dr --start-address=0x848 --stop-address=0x8b0 "$K"
# 5) GET 下标 → 请求帧
llvm-objdump -dr --start-address=0x32a8 --stop-address=0x3390 "$K"
# 6) SET 两分支（含 0x0a 硬编码）
llvm-objdump -dr --start-address=0x34b8 --stop-address=0x372c "$K"
# 7) 回包 cache[index] = value
llvm-objdump -dr --start-address=0x234c --stop-address=0x2464 "$K"
```
