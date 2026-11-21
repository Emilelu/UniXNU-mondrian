# 实体按键 16.6.1 → 27 的注入契约差异（对称表）

日期 2026-11-21 · 输入线（input27）· 纯离线：16 侧读 16.6.1 装配树，27 侧读 27 feed / 27 仓 / sheng 27 参照
16 侧路径前缀：`/opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`
27 侧路径前缀：`/opt/k60/trees/ios27-out/feeds/IOHIDFamily-f53ac321/` 与 `E:/hackios/xnekom-ios27/`

## 一、五条结论

1. **报告格式（report ID 2 + 四个 Consumer 位）与语义两头都没变**：一是 16.6.1 用户态直接给 `0x0c/0x30|0xe9|0xea`（`userland/touch.c:66-69`），二是 27 内核描述符把同样四个 usage 排成 report 2（sheng `NativeHidInput.cpp:47-49`），且 27 的 stock 映射把它们翻成系统键（`IOHIDConsumer.cpp:117` → `NX_POWER_KEY`、`:143` → `NX_KEYTYPE_SOUND_UP`、`:146` → `NX_KEYTYPE_SOUND_DOWN`）。这条在 27 侧有源码实证，不再是推算。
2. **变的是载体**：16 是「内核驱动写字符设备 → backboardd 里的用户态插件读 → 造虚拟 HID 服务派发」（`bsd/dev/pong_input.c:96-106` 建 `/dev/pong-touch` 与 `/dev/pong-buttons`；`userland/touch.c:368` 打开、`:386-392` 过滤与派发），27 是「内核驱动把按下集合交给 sink → 内核 IOHIDDevice 直接出 report」（sheng `ButtonProbe.cpp:198` 设 sink、`:183-188` 推送掩码；`NativeHidInput.cpp:340-350` 组 `{2, down|mask&0xe}`）。**27 侧不存在 `/dev/pong-buttons` 这条通道**。
3. **取样与中断在 27 不需要新设计**：16 是内核线程读 PMIC arbiter v7（`pong_buttons.c:107` 线程、`:75` map 走查、`:103` 发布、`:155` `assert_wait_deadline` 等待），sheng 的 27 实现是同一套寄存器语义（`ButtonProbe.cpp:128-134` 读 RT_STS 组掩码、`:86-123` 中断内应答后唤醒线程、`:109` 连续中断后屏蔽 PDC 引脚）。**K60 侧要的是重放 16 的 `pong_buttons.c`（171 行，27 上 0 冲突），不是照抄 sheng 的实现**。
4. **ADT 侧有一条真实的回归陷阱**：驱动按名字死找 `/arm-io/pong-buttons` 并断言六个值（`pong_buttons.c:42`、`:45-50`、`:56-58`），而 16 仓 `board.toml` **今天没有这个节点**（只有 `[adt.buttons.*]`，`board.toml:268/272/275`）——2026-11-12 两次 upstream pick 先加后删（`97b84eb7` 加、`3b3ff9ce` 删），那些节点当时只活在 `/opt` 装配输入里（同一教训记在 `docs/research/EIGHT-STEPS.toml:406`）。27 仓已把它写回 `board.toml:284-299`，并在 `:285-287` 注释里写明「干净重建会打印 `Pong keys: DT node /arm-io/pong-buttons not found`」。**27 上绝不能只搬 `/buttons`。**
5. **不加 boot-arg**：16 的驱动编译期默认开（`pong_buttons.c:163` `enabled=1`，且注释说明 `PE_parse_boot_argn` 缺省返回 FALSE 会让 `||` 短路），sheng 用 `sheng-buttons=1` 门控（`ButtonProbe.cpp:216`）。K60 沿用「默认开」，`BOOT-ARGS-PENDING.toml` 的 608 B 预算不动。

## 二、对称差异表

| # | 轴 | 16.6.1 侧 | 27 侧 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | 报告 ID / 位宽 | 无描述符，用户态逐事件造键（`userland/touch.c:388-392`） | report ID 2，四位：Menu `0x40`、Power `0x30`、Vol+ `0xe9`、Vol- `0xea`，各 1 bit + 4 bit 填充（sheng `NativeHidInput.cpp:47-49`）；出报 `{2,(down?1:0)\|mask&0xe}`（`:340-346`） | 变更（用户态 API → 内核描述符），语义不变 |
| 2 | 系统语义 | 依赖 SpringBoard 对虚拟服务 usage 的解释（无内核侧映射） | `IOHIDConsumer.cpp:117/143/146` 三条 usage → `NX_POWER_KEY`/`NX_KEYTYPE_SOUND_UP`/`NX_KEYTYPE_SOUND_DOWN`；调试键表 `IOHIDEventService.cpp:1416` 也认 `Csmr_Power` | 27 侧有源码实证（新增证据） |
| 3 | 事件通道 | 字符设备：`pong_input.c:96` `cdevsw_add`、`:98` `devfs_make_node`、`:105-106` 两个节点；`userland/touch.c:368` 打开 `/dev/pong-buttons`（30 次重试）、`:386-387` 只认 `PONG_BUTTON_DOWN/UP` | **27 侧不存在**该通道；替代是 sink 回调 `native_buttons_set_sink`（sheng `ButtonProbe.cpp:198`），由 `NativeHidInput.cpp:336-339` 转成 loop 动作 | 变更（新通道） |
| 4 | 按键编码 | 内核宏 `PONG_BUTTON_DOWN 4`/`UP 5`/`POWER 0`/`VOLUME_UP 1`/`VOLUME_DOWN 2`（`bsd/sys/pong_input.h:8-12`），塞进 `struct pong_touch` 的 `type/finger`（`:13-16`，24 B） | 掩码位 `kReportPower`/`kReportVolumeDown`/`kReportVolumeUp`（sheng `ButtonProbe.cpp:130-133`），落到 report 2 的 bit1/bit2/bit3 | 变更（编码换了，语义一一对应） |
| 5 | 取样/中断 | 内核线程 + `assert_wait_deadline`/`thread_block`（`pong_buttons.c:107`、`:155`）；`pong_buttons_init` 起线程（`:169`） | 中断内应答 + 唤醒一个线程，再由线程读电平（sheng `ButtonProbe.cpp:86-123`、`:179`、`:191-192`）；连续中断后屏蔽 PDC（`:109`） | 不变（同一 arbiter v7 布局），实现待重放 |
| 6 | 默认开关 | 编译期 `enabled=1`（`pong_buttons.c:163`） | sheng 用 `sheng-buttons=1` 门控（`ButtonProbe.cpp:216`） | 采用 16 的形状，不加 boot-arg |
| 7 | ADT `/arm-io/pong-buttons` | 16 仓 `board.toml` **无**（只有 `[adt.buttons.*]`：`:268`、`:272`、`:275`）；节点只在 `/opt` 装配输入里 | 27 仓 `board.toml:284-299` 六属性（core-base/cnfg-base/observer-base `u64`，ee/pon-ppid/volume-up-ppid `u32`），`:285-287` 记着重建丢节点的教训 | 27 侧已补，**须当作硬前提** |
| 8 | ADT `/buttons` | `board.toml:268-276`（`compatible`/`device_type`/`button-names`=hold,voldown,volup/`home-button-type`=2） | `board.toml:307-316` 同四字段；两侧同一生成点 `scripts/unixnu/devicetree.py:388-390`（只在 platform 里有 `buttons` 时才写该节点） | 不变（27 无缺项） |
| 9 | 全面屏手势语义 | `docs/zh/guide/mobilegestalt.md:42-44`：`/buttons` 无 `menu` + `home-button-type=2` ⇒ 锁屏上滑 | 27 侧内核源里无此项；语义由官方页规定（`docs/guide/mobilegestalt.md:27` 与 `:36-44`：SpringBoard 经 `BSPlatform homeButtonType` 读取，2 ⇒ 锁屏上滑） | **待验对象**：24A446 SpringBoard 二进制里的 `homeButtonType` 串 + 一次锁屏上滑解锁 |
| 10 | 长按复位钩子 | 无（`patches/buttons/README.md:116-124` 记为 out of scope） | 无 | 不变（不做） |

## 三、27 侧仍未证实的点（写清归属，不写成事实）

### 3.1 `home-button-type = 2` 在 27 的 SpringBoard 里是否同样生效

- **依据**：27 内核 feed 里没有读该属性的代码——这是对的，属性由用户态平台层读；语义由官方页规定：`E:/hackios/UniXNU/docs/guide/mobilegestalt.md:27`（属性表：值 2 = 无机械 Home 键、用滑动手势）与 `:36-44`（`:44`「SpringBoard 通过 `BSPlatform homeButtonType` 读取该值。值为 2 时，锁屏使用上滑手势」）。ADT 侧已闭合：`/buttons` 四字段在 27 生成的 ADT 里逐字节存在（`adt-27-buttons-check.md`）。
- **待验对象**：① 24A446 的 SpringBoard 二进制里有没有 `homeButtonType` 选择器/字符串（`strings -a .../SpringBoard | grep -c homeButtonType`）；② 上机后锁屏**上滑解锁**一次（成功/失败）。

### 3.2 内核侧 Consumer 设备是否需要额外属性才被 backboardd 接受

- **依据**：27 的 stock 路径本身就是内核 HID 设备（`IOHIDDevice.cpp:1494`）；sheng 是唯一同 OS profile 且**独立**的实现（`E:/hackios/UniXNU-sheng` @ a68ee4e），其 `start()` 只要求 `HIDDefaultBehavior`（`NativeHidInput.cpp:446`），报告 2 的 Consumer 项 `0x40/0x30/0xe9/0xea` 与 K60 需要的三键一一对上（`NativeHidInput.cpp:47-49`）。
- **待验对象**：① `ioreg -p IOService -c IOHIDDevice -r -n "Offline HID input probe"` 的实例与属性行；② 按键按下后 `ioreg -p IOService -c IOHIDEventDriver` 下该设备 event driver 是否存在并收到事件（对应 `native_buttons_stats` 计数变化）。

## 四、这条线上要动的东西（按优先级）

1. 重放 16 的 `bsd/dev/pong_buttons.c` 与 `bsd/dev/pong_input.c` 改动（27 上 0 冲突，无 `--exclude` 需求见台账 ⑥deep 的重放记录）。
2. `board.toml` 保留 27 仓现状：`[adt.arm-io.pong-buttons.*]` 六属性 + `[adt.buttons.*]` 四字段，两者缺一即分别丢「内核能报」与「用户态能映射」。
3. 不新增 boot-arg；若将来要照 sheng 加门控，再按 `BOOT-ARGS-PENDING.toml` 的 608 B 预算逐项列字节。

## 五、引用对照（便于复核）

- 16 侧：`bsd/dev/pong_buttons.c:20,22-23,42,45-50,52,56-58,63,67,75,103,104,107,112,116,134,151,155,163,169`；`bsd/dev/pong_input.c:17,22,30,84,96,98,105-106`；`bsd/sys/pong_input.h:8-12,13-16`；`userland/touch.c:66-69,286,337,368,380,386-392`
- 27 侧：`IOHIDConsumer.cpp:117,143,146`；`IOHIDEventService.cpp:1416`；sheng `NativeHidInput.cpp:47-49,336-350,446,453`；sheng `ButtonProbe.cpp:86-123,109,128-134,179,183-188,191-192,198,216`；`E:/hackios/xnekom-ios27/board.toml:284-287,291-299,307-316`；`scripts/unixnu/devicetree.py:388-390`
