# 背光日志字形（预写判据）

这份文档是给 **`patches/proposed/0001-k60-backlight-log-requested-level.patch`** 的判据，
写在上机之前。Lead 2026-11-21 的决定：这条判据由 Lead 排飞行，本线不等它；
但「要看到哪一行、出现几次、失败长什么样」必须先写死，否则上机拿到日志也只能靠回忆判读。

## 1. 这条判据要证明什么

`K60Backlight::setProperties()` 在 brightness 分支里把**同一个变量打了两次**：

```c
/* drivers/PongAdreno/K60Backlight.cpp:416-417 */
IOLog("K60 BACKLIGHT: brightness level %u -> level %u dbv 0x%x\n",
      goal, goal, (unsigned)k60backlight::dbvFromLevel(goal));
```

第一个字段应当是**请求值**、第二个是**映射后的等级**，实际两处都是 `goal`。
后果不是排版问题：27 线的亮度证据行要回答「系统到底发了什么」，而这行给出的两个数字恒等，
**无法区分「系统请求 2047」与「系统请求 4095 被夹到 2047」**。
`0001` 把第一处改成 `requested`（`K60BacklightCodec.h:62-67` 的 `clampLevel` 只夹上下限，
所以越界请求是唯一能让两个字段分开的输入）。

再强调一次：**`published level …` 那一行不能当证据**。它在任何请求到达之前写（`K60Backlight.cpp:374-381`，
注释 `:372-373` 自己写了 publish 时 `req` 还是 0,0），只能证明服务起来了。

## 2. 两种字形

| 字形 | 触发键 | 格式串 | 位置 | 能否区分请求与等级 |
| --- | --- | --- | --- | --- |
| **A 形** | `brightness-nits`（有符号 16.16 尼特） | `K60 BACKLIGHT: brightness-nits %d.%05u -> level %u dbv 0x%x` | `K60Backlight.cpp:411-414` | **能**（第一字段就是尼特值） |
| **B 形** | `brightness`（+ 可选 `FadePeriod`） | `K60 BACKLIGHT: brightness level %u -> level %u dbv 0x%x` | `K60Backlight.cpp:416-417` | **不能**（两处都是 `goal`，缺陷所在） |

判据只需要 B 形。A 形出现时说明 27 的 CoreBrightness 走尼特通道，那时 `0001` 的价值退化为「日志一致性」，
不影响它是否安全。

## 3. 要看到什么（判据表）

| # | 观察 | 通过形态 | 失败形态 | 失败的含义与下一步 |
| --- | --- | --- | --- | --- |
| C1 | 有没有 B 形行 | `grep -c "K60 BACKLIGHT: brightness level"` ≥ 1 | 0 行 | `setProperties()` 没被以 `brightness` 键调用：要么服务没被 CoreBrightness 采纳（看 `published … conformance=` 与 `control=`），要么这本 OS 只发 A 形。**不能**据此判 `0001` 无用，只能判「本镜像不可触发」 |
| C2 | B 形行的两字段 | 至少一行两字段**恒等**（例：`brightness level 1024 -> level 1024 dbv 0x…`） | 出现两字段不等 | 打 `0001` 之后才会不等；若**未打**补丁却看到不等，说明这份日志来自别的构建，整份判据作废 |
| C3 | 我们真正要的那一行 | 打 `0001` 后出现**越界请求**：`brightness level 4095 -> level 2047` 或 `brightness level 4294967295 -> level 0` | 打过 `0001`、整次飞行没有一行两字段不等 | OS 从不发越界值。此时证据只能是 C2（缺陷存在：两字段恒等），`0001` **不因此进系列**——它没有可观测的行为差异。要让 C3 可达，用 §8 的探针（`patches/proposed/0003`） |
| C4 | dbv 与等级是否自洽 | `level 0 -> dbv 0x0`；`level ≥ 1 -> dbv 0x4..0xfff` | `level ≥ 1` 却是 `dbv 0x0`，或 `dbv > 0xfff` | 编解码问题（`K60BacklightCodec.h:119-125`），与本补丁无关，另开一条 |
| C5 | 一次拖动写几行 | 一行一次请求，一次拖动「a handful」（`K60Backlight.cpp:405-409` 的原话） | 一次拖动几十行 | 有别的客户端在轮询写 `brightness`，先查是谁，再谈亮度曲线 |

计数口径：`stats[1]` 就是请求计数（`K60Backlight.cpp:419`），但**它不是判据**——
它只能告诉你来过几个请求，不能告诉你第一个字段本来该是什么。判据只认日志行本身。

## 4. 命令（离线判读，不改设备）

```sh
# B 形行有几条、原样打出来
grep -c "K60 BACKLIGHT: brightness level" console.log
grep -n  "K60 BACKLIGHT: brightness level" console.log | head -20

# 两字段是否恒等（恒等打印 IDENTICAL，不等打印 SPLIT）
grep "K60 BACKLIGHT: brightness level" console.log | \
  awk '{ if ($4 == $7) print "IDENTICAL", $0; else print "SPLIT", $0 }' | sort | uniq -c

# A 形是否也在（决定这本 OS 走哪条通道）
grep -c "K60 BACKLIGHT: brightness-nits" console.log

# 服务是否被采纳（conformance / control 两位）
grep "K60 BACKLIGHT: published" console.log
```

字段位置按格式串固定：`K60 BACKLIGHT: brightness level <req> -> level <goal> dbv <dbv>`，
所以 `$4` 与 `$7` 就是那两个数字（`$1=K60 $2=BACKLIGHT: $3=brightness $4=level`…）。

## 5. 前置条件（写死，免得飞行白跑）

1. 构建带 `k60_backlight=1`（读者 `K60Backlight.cpp:494`；默认 1，可以不写）。
2. 形态 A（`k60_backlight_control=0`）**不影响** B 形行是否出现：16.6.1 上形态 A 已经观测到
   `req=` 计数上涨，请求照样进 `setProperties()`。
3. 日志取自**本仓本分支构建的镜像**；镜像哈希与 `boot.json` 一起留在判读记录里（否则 C2 的「来源不明」无法排除）。
4. 判读只读日志，不需要调试器、不需要内核符号——这是这份字形存在的理由（同 `:364-367` 的原则）。

## 6. 结论落点

- 判据通过（C1+C2，或 C3 出现 `SPLIT`）→ 写进 `docs/research/display/BACKLIGHT-LOG-CRITERIA.md` §7 的
  「最近一次判读」表，并把 `0001` 从「不进 series」改成「待 Lead 排批」。
- 判据不可触发（C1=0 或 C3 无 `SPLIT`）→ 结论写「**本镜像不可触发，补丁保留为草案**」，
  **不要**写成「补丁无效」：缺陷是代码事实（两处同一变量），只是没有可观测症状。

## 7. 最近一次判读

| 日期 | 镜像（哈希） | B 形行数 | 两字段 | 结论 |
| --- | --- | --- | --- | --- |
| — | — | 未飞 | — | 等 Lead 排飞行；在此之前 `0001` 停在 `patches/proposed/`，不进 series |

## 8. 探针：让 C3 从「等 OS 犯错」变成「自己问一次」（`0003`）

Lead 2026-11-21T19:12 批准加 `k60_backlight_probe=1`，三条约束写在这里：探针默认关、只在参数为 1 时自走一次、
探针关闭时本镜像不可触发这件事也要写进结论。

### 8.1 为什么非要有它

C3 依赖「OS 真发一次越界 brightness」。滑块不会发 4095——`K60BacklightCodec.h:62-67` 的 `clampLevel`
只在上限（2047）和下限（0）起作用，正常请求永远落在区间内，两个字段永远恒等。
没有探针，`0001` 就只能拿到 C2（证明缺陷存在），拿不到「补丁改变了可观测行为」，
补丁于是永久停在草案里。

### 8.2 探针做什么

`patches/proposed/0003-k60-backlight-probe-the-clamp.patch` 在 `publishFirst()` 末尾（`K60Backlight.cpp:382` 之后）
读 `k60_backlight_probe`，为 1 时构造一次 `{brightness: 4095}` 并调用自己的 `setProperties()`，只此一次。

4095 不是随便取的数：它是面板自己 12 位 DBV 域的上限（`K60BacklightCodec.h:53 kMaxDbv = 0xfff`），
也就是「调用方把 DBV 当等级传」时会传的值；经过 `clampLevel` 应落到 2047 / DBV 0xfff。

**必须叠在 `0001` 上**：单独打 `0003`，B 形行会打 `brightness level 2047 -> level 2047`——
那正是缺陷本身，什么也证明不了。两份补丁同批打，才能看到两字段分开。

### 8.3 探针判据

| # | 观察 | 通过形态 | 失败形态 | 含义与下一步 |
| --- | --- | --- | --- | --- |
| P1 | 探针那一行在不在 | 打 `0001`+`0003` 且 `k60_backlight_probe=1` 时，恰好**一行** `K60 BACKLIGHT: brightness level 4095 -> level 2047 dbv 0xfff` | 0 行 | 参数没进命令行（先查 `boot-args` 是否被 608 B 截断）、或服务没起来（看 `published …` 行）、或 `0003` 没打进镜像 |
| P2 | 出现几次 | **1 次**（`publishFirst()` 只跑一次） | ≥2 次 | 服务被重复 attach，是另一个缺陷，先记下来（`native_backlight_stats[0]` 会出现两次 published 行） |
| P3 | 两字段是否分开 | `4095` 与 `2047` 不等 | 两个都是 `2047` | `0001` 没打进镜像（`0003` 单独生效的典型形态）——这**不算** P1 失败，按 C2 记「缺陷仍在」 |
| P4 | 面板反应 | 面板跳到最亮，随后由 OS 接管（一次可见跳变） | 黑屏 | 探针走的是正常 `publish()` 路径，黑屏说明 `dbvFromLevel(2047)` 有问题（`K60BacklightCodec.h:119-125`），与本补丁无关 |
| P5 | 探针关着时 | `k60_backlight_probe` 不写或写 0 时，日志里**没有** `4095` 这一行 | 出现 4095 | 默认值被改成开（违反 Lead 的约束①），立即退回 |

### 8.4 探针关闭时的结论写法（约束③）

如果这一轮飞行没带 `k60_backlight_probe=1`（或字节不够、探针没进镜像），结论必须写成：

> `0001` 的 C3 在本镜像**不可触发**：探针未启用，OS 不发越界请求，两字段恒等；
> 缺陷是代码事实（`K60Backlight.cpp:416-417` 两处同一变量），不是「补丁无效」。

**不要**写「补丁无效」「无法验证」这种把两件事混在一起的句子——前者是行为判断，后者是条件缺失。

### 8.5 字节账：这个参数目前放不进去（待裁）

| 项 | 字节 | 依据 |
| --- | --- | --- |
| 27 命令行现状（A+B 组，已按 Lead 裁决 O1 删 `disable_exc_resource=1`） | **603 B** | `DISPLAY-27-INTEGRATION.md` §4.7 |
| 上限（含空格） | **607 B** | `uefi-mondrian/Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h:8` 的 608 含结尾 NUL |
| 余量 | **4 B** | 上面两行之差 |
| `k60_backlight_probe=1` | 21 B 字符 + 1 分隔空格 = **22 B** | `len()` 实测 |
| 加进去之后 | **625 B，超 18 B** | 603 + 22 |
| 压到 `k60bl_probe=1` | 15 + 1 = 16 B → 619 B，**仍超 12 B** | 名字救不了，余量只有 4 B |

三条可选的字节来源，本线不自行决定：

1. **编译期开关（0 B，本线建议）**：探针只在专用镜像里编进去（`K60_BACKLIGHT_PROBE`），
   判据镜像与探针镜像各记一份哈希；代价是「探针」与「用户可自证的镜像」不是同一个。
2. 删 `use_contiguous_hint=0`（21 B）→ 604 B：读者 `osfmk/arm64/arm_vm_init.c:2154`，
   且它在 27 的 override 七项里（有人为 27 加过），**本线不删**，要平台线确认它是否仍需要。
3. 删 `applog=1`(9 B) + `k60_console_export=1`(21 B) → 595 B：这两项是证据通道，不建议。

无论选哪条，`k60_backlight_probe` 一旦真的要进命令行，必须同时写进 `docs/engineering/BOOT-ARGS.md`
的表格（`scripts/check-boot-args.py:24-28` 只认那里的 `### name` 与表格首列），否则门禁看不见它。
