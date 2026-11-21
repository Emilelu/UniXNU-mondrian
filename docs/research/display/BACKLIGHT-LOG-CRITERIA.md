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
| C3 | 我们真正要的那一行 | 打 `0001` 后出现**越界请求**：`brightness level 4095 -> level 2047` 或 `brightness level 4294967295 -> level 0` | 打过 `0001`、整次飞行没有一行两字段不等 | OS 从不发越界值。此时证据只能是 C2（缺陷存在：两字段恒等），`0001` **不因此进系列**——它没有可观测的行为差异 |
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
