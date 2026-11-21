# wire 版本号中立法案 —— 显示线覆盖审查

Lead 2026-11-21 16:36 的裁决：版本号中立法案由 gpu27 出提案、Lead 会签，**显示线只审
「57 槽」与「48 B 包装」两种形状是否覆盖本线全部过线字段**，不改 wire 一行。

- 审查对象：`drivers/PongAdreno/PongScanoutWire.h`（15 行）与官方
  `E:/hackios/UniXNU/drivers/GopFramebuffer/NativeGOPWire.h`（17 行）。
- 本文件只回答「覆盖 / 不覆盖」，不裁形状：实现归 gpu27，会签归 Lead。

## 1. 本线过线的字段全集

四条记录，尺寸与官方逐个对齐（`PongScanoutWire.h:14-15` 的 `static_assert`：
40/8/48/16；官方 `NativeGOPWire.h:16-17` 是 8/48/16/40/32/16）。

| 记录 | 尺寸 | 字段（偏移） | 16.6.1 定义 | 官方对应 |
| --- | --- | --- | --- | --- |
| `PongScanoutModeInfo` | 40 B | `version`@0、`format`@4、`width`@8、`height`@16、`stride`@24、`bytes`@32 | `PongScanoutWire.h:10` | `NGPMode` `NativeGOPWire.h:6` |
| `PongScanoutWaitInfo` | 8 B | `timeout_ms`@0 | `PongScanoutWire.h:11` | `NGPWait` `:13` |
| `PongScanoutFrame` | 48 B | `sequence`@0、`address`@8、`bytes`@16、`stride`@24、`width`@32、`height`@36、`format`@40、`reserved`@44 | `PongScanoutWire.h:12` | `NGPSwap` `:14` |
| `PongScanoutDone` | 16 B | `sequence`@0、`status`@8、`reserved`@12 | `PongScanoutWire.h:13` | `NGPComplete` `:15` |

另有四个方法码与两个常量过线：`Mode 0x7000` / `Wait 0x7002` / `Complete 0x7003` /
`Memory 0x5343`（`PongScanoutWire.h:5-6`）、格式 `Bgra=1`、版本 `PongScanoutVersion=1`、
未提交哨兵 `PongScanoutNotSubmitted=0x4e4f444d`（`:9`）。

读点三处：`PongAdrenoScanout.cpp:75` 填 mode、`:122` 校验 Complete、`:149` 构造 Frame。

**不在 wire 上的**（先排除，免得被当成缺口）：面板刷新率与 tear-check 走 INTF
（`PongDsiPanel.cpp:84` 的八个 INTF 常量、`:136-236` `panel_intf_rate`），scanout 窗口
走 `PongScanoutMemory=0x5343` 选择子。两者都与版本号无关。

## 2. 版本号今天在哪，空位真的空吗

版本只在 mode 记录里，offset 0（`PongScanoutWire.h:10`）。`Frame` 与 `Done` 没有版本字段，
各有一个 `reserved`（`Frame`@44、`Done`@12）—— 但它们**不是空闲空间**，两处都在用：

- `PongAdrenoScanout.cpp:149` 用花括号初始化把 `Frame` 最后一位写成字面量 `0`：
  `{pending.id, …, mode.format, 0}`。
- `PongAdrenoScanout.cpp:122` 把 `Done.reserved` 当垃圾检查：
  `if(q.reserved || !pending.offered || …) return kIOReturnBadArgument;` —— 任何非零都拒收。

所以「48 B 包装」不是零改动方案：它要么改这两处，要么放弃在 `Frame`/`Done` 里带版本。

## 3. 覆盖判定

| 记录 / 常量 | 57 槽 | 48 B 包装 | 判据 |
| --- | --- | --- | --- |
| `ModeInfo.version` | 覆盖 | 覆盖 | 已在 @0，两种形状都不动 |
| `Frame`（8 字段） | 覆盖 | 覆盖，**代价是改 `:149` 的初始化** | 版本进 `reserved`@44 |
| `Done`（3 字段） | 覆盖 | 覆盖，**代价是改 `:122` 的零校验** | 版本进 `reserved`@12 |
| `WaitInfo.timeout_ms` | 覆盖（不需要版本） | 覆盖（不需要版本） | 加版本即 16 B，违反 `:16` 断言 |
| 方法码 / `NotSubmitted` / `Bgra` | 覆盖 | 覆盖 | 与版本无关 |
| 官方 `NGPTransfer`(16 B) / `NGPPresent`(32 B) | 不涉及 | 不涉及 | 官方有、本线不过线 |

**结论：两种形状都能覆盖本线的全部过线字段，成本形状不同**——57 槽动的是调用点（新槽位），
48 B 包装动的是两个已在用的校验点。

## 4. 两种形状各自必须写死的条件

48 B 包装：

1. `Frame.reserved`@44 **改名为 `version`**（不是只改注释：只改注释就没有可断言的名字）。
2. `:149` 的初始化把 `0` 换成协商到的版本号；`:122` 的零校验改成**精确等值**检查
   （`q.reserved != version ⇒ 拒收`），不能退化成「非零就收」—— 那会放掉本来要挡的垃圾。
3. 加偏移断言：`sizeof==48` 且 `offsetof(version)==44`；`Done` 同理 `offsetof(version)==12`、
   `sizeof==16`。现有的断言只有尺寸（`PongScanoutWire.h:14-15`）。
4. 版本不匹配时 `Done` 必须**拒绝 retire**（走 `kIOReturnBadArgument` 一路），否则 GPU 拷贝
   完成的事件会退掉别人的一帧。

57 槽：

1. 给出槽位索引常数，以及索引是否随方法码变化。
2. `Wait` 无处放版本时怎么办：加版本即 16 B，与官方 `NativeGOPWire.h:16` 的
   `sizeof(NGPWait)==8` 冲突；若提案要动这条断言，等于改官方 ABI，会签时必须写明。
3. `ModeInfo.version` 与槽位版本谁权威；两处不一致时的行为。

## 5. 本线不接受的三种写法

1. **拿哨兵或方法码当版本**：`0x4e4f444d` 是状态值，`0x7000/0x7002/0x7003` 是方法码；
   混进版本域会让 `:122` 与 `:126` 的判断失去意义。
2. **只加注释不加字段**：`:75` 与 `:149` 要能写出版本，注释做不到。
3. **把 `Wait` 撑到 16 B**：同时改掉官方断言，跨 16.6.1 与 27 两个 ABI。

## 6. 交给 gpu27 提案的六个空

| # | 提案里要有 | 为什么显示线在意 |
| --- | --- | --- |
| 1 | 版本位置：槽索引，或 `offsetof`+字段名 | 本线在 `:75`/`:149` 写、`:122` 读 |
| 2 | `ModeInfo.version` 与包装内版本谁权威 | 两处都能写时读点会分叉 |
| 3 | 版本不匹配的行为（特别是 `Done`） | 关系到 retire 是否可能退错帧 |
| 4 | 断言清单（尺寸 + 偏移） | 没有偏移断言，改名与注释无法区分 |
| 5 | 27 侧读者行号 | 27 上必须真有人读，否则等于没中立 |
| 6 | 是否触碰 `sizeof(NGPWait)==8` | 触碰即改官方 ABI，会签要写明 |

## 7. 判据（提案落地后可直接跑）

```sh
# 版本常量定义与使用点应各只有一处
git grep -n "PongScanoutVersion" drivers/
# 尺寸断言在，且要有新增的偏移断言
git grep -n "static_assert(sizeof(PongScanout" drivers/PongAdreno/PongScanoutWire.h
# 若选 48 B 包装：这两处必须一起改，不能只改一处
git grep -n "q.reserved" drivers/PongAdreno/PongAdrenoScanout.cpp
# 27 侧读者（提案给行号后替换）
git grep -n "version" <提案给的 27 侧文件>
```

## 8. 边界

- 不改 `PongScanoutWire.h`、不改 `NativeGOPWire.h`、不改断言，也不裁形状。
- 显示线**没有硬偏好**：57 槽动调用点、48 B 包装动两个已在用的校验点，代价相当。
  若要一句建议：48 B 包装少一个新槽位常数、少一处跨文件约定，但必须先改 `:122`/`:149`；
  57 槽保持 `reserved` 的原义（垃圾检查），代价是 `Wait` 的规则要单独写。
