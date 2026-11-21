# 显示与亮度线的线内规则

这份文件是本线（官方适配表第 3 行 `porting/display`：GopFramebuffer / DisplayTimingProbe /
AppleARMBacklight / GeniI2c）自己的作业规则，来源是已经踩过的坑和 Lead 的裁决。
规则只约束本线，不改共享树（`k60-gates`、`board.toml`、`patches/xnu/series`、`docs/engineering/*`）。

## L1 引行号：结论行必须带它的条件行

**规则**：写出「某分支会怎样」时，必须同时引三样——`if` 条件行、结论行、以及收尾的 `else`（如果有）。
只引结论行不算证据。

**为什么**：R4 就是这么错的。我曾在 `DISPLAY-27-DELTA.md` §10 报「`K60Backlight.cpp:384-433`
落空分支用未初始化 `goal` 去 `publish`」，Lead 让我单独出 patch 草案。复核发现 `goal` 根本不会未初始化：
`setProperties()` 是三支收尾——`brightness-nits`（`:392-396`）、`brightness`+`FadePeriod`（`:397-401`）、
`else { return kIOReturnSuccess; }`（`:402-404`），`:428 publish(goal)` 永远在已赋值之后。
我把 `:410 if (nitsRequest)` 的**日志** else（`:415-418`）读成了**请求**的 else。

**复核命令**（任何时候怀疑自己引错分支，先跑这个）：

```sh
awk 'NR>=384 && NR<=432{printf "%d: %s\n", NR, $0}' drivers/PongAdreno/K60Backlight.cpp
grep -n "setProperties\|publish(" drivers/PongAdreno/K60Backlight.cpp
```

**归档**：R4 不删除，`DISPLAY-27-DELTA.md` §10 保留「已撤回：误读」段 + 三支行号 + 判据命令。
撤回的结论留在文件里，比删掉更有用——下次谁再读 §10，能看见它为什么错。

## L2 判据先写后飞

任何需要上机才能证明的结论，**先**把「要看到哪一行、出现几次、失败长什么样」写成文档，再谈飞行。
已按这条产出：

- `docs/research/display/BACKLIGHT-LOG-CRITERIA.md`（`0001` 的预写字形：C1–C5 判据表 + 离线判读命令 + 前置条件）

**为什么**：上机窗口稀缺，日志回来时人只记得「大概看到过一行」。预写字形把判读从记忆里搬到文件里，
也让 Lead 能在我飞行之前先否掉坏判据。

## L3 数字必须实测

字节数、行数、槽位数一律用脚本算，不手算。已经错过一次：预算表里手算得到
「恢复 673 B / 加 `k60_dpu` 682 B / 超 76」，用 Python 在 `board.toml` 上实测是
**661 / 671 / 超 64**，而且「删一项要连它的前导空格一起减」这半条也被漏掉过一次。

```sh
python3 - <<'PY'
import tomllib
d = tomllib.load(open('board.toml','rb'))
args = d['payload']['kernel_args']
print(len(args), 'items', len(' '.join(args)), 'bytes')
PY
```

## L4 自造的名字不许进结论

我在 `WIRE-VERSION-REVIEW.md` 里给「版本不塞进 48 B 帧记录」起了个临时名字「57 槽」，结果 gpu27
拿着这个词去头文件里找结构，全树 grep 不到。规则：**结论里只许出现头文件里的名字或 `文件:行`**；
临时叫法只能在讨论里用，且必须当场写明「这不是结构名，真名是 X」。
（该处已在 §9 更正为第五方法码 `0x7004`。）

## L5 不猜接口

27 的显示契约（wire v2 字段）没会签完之前，不写 `K60DisplayTimingProbe.cpp` 骨架——
骨架会把未定的接口形状钉死，后面改起来比不写更贵（Lead 2026-11-21T16:58 裁决，押后）。

## L6 交付形态：草案进 `patches/proposed/`，不进 series

改 16.6.1 已封闭系列的行为，一律以 `patches/proposed/NNNN-*.patch` 提交，`git apply --check` 必须通过，
头部写清「为什么」与「只适用 27 分支」。**不进 `patches/xnu/series`**——那是已发布历史。
当前两张：`0001`（日志字段）、`0002`（`k60_backlight_control` 默认翻 0，等 27 显示契约与 wire v2 同批）。

## L7 文档里的中文不许出现 ASCII 双引号

`docs/research/eight-step/display-27.toml` 因为正文里写了 `"不适用"`、`len(" ".join(args))`、`[payload."adt"]`
三次 `TOMLDecodeError`。规则：中文正文里的引用一律用「」，命令与键名放进代码块或改用无引号写法。

## L8 提交前复核身份

提交固定 `Emilelu <kimiuso@vip.qq.com>`；提交后必须

```sh
git log -1 --format='%an <%ae> | %cn <%ce>'
```

一次误写成 `kimiiso@vip.qq.com`，靠 amend 才修回来。

## L9 只写自己的 lane

不写 `k60-gates`、不写别人的 worktree、不与 main 合并、不构建、不上机（上机由 Lead 排）。
跨线的事（gpu27 的 wire 提案、24A446 CoreBrightness 提取）只回签与审查，不动手实现。


## L10 能用编译期开关解决的，不要占启动参数

27 命令行 O1 之后只剩 4 B，任何一个新参数都装不进去（`k60_backlight_probe=1` 要 22 B，加进去 625 B 超 18）。
默认关、只在专用诊断镜像里存在的东西，一律走源码 `#ifndef X / #define 0` 加构建注入 `-D`（现成通道：
`XNU_EXTRA_CFLAGS`，见 `scripts/build-xnu-4k-baseline.sh:574`），并把「关掉时镜像里不存在该字面量」
做成一条可跑的断言（范例 `docs/research/display/check-probe-absent.py`）。
判断顺序：能不能不占字节 → 能不能用编译期开关 → 才轮到删别人的参数（那不是本线能裁的）。


## L11 「不该出现」的断言必须有一条会让它出现的自测

`check-probe-absent.py` 三条自测里，最有价值的是第三条（把 marker 塞进假 release，脚本 rc=1）——
前两条只能证明它打印 OK，第三条才证明它会**失败**。没有这条自测的断言只是打印。
写法：断言 + 一组「故意违规」的输入，断言在违规输入上必须返回非 0。

## 裁决记录（2026-11-21T19:33）

1. **补丁头的 Subject 不挪**：`git am` 要求 `Subject:` 在前，这是工具约束不是排版偏好；
   「Stacked on 0001, never alone」放在 Subject 之后的第一行 prose 与代码块第一行注释即算到位。
2. `k60_backlight_probe` 的「删注册表行」要求**作废**：它从未进过 `BOOT-ARGS.md`、
   `BOOT-ARGS-PENDING.toml`、`ALLOWED_ADDITIONS`（三处 `grep -c` 为 0），没有行可删。


## L12 官方 / 别人实现类断言：先查共享库

库：`E:/k60-work/kb/kb.sqlite`（WSL `/mnt/e/k60-work/kb`）。2026-11-22 实测 schema
`meta / docs / chunks / vecs / cache`，`docs` 6,194 行、`chunks` 142,260 行——与广播数字一致。

- 命中：写 `文件:节`，不写「我记得」。
- 未命中：才联网，并附 URL。
- 都没有：写「未证」，不写推测。
- 引擎脚本 `kb_engine.py` 广播给的路径（`/mnt/e/k60-work/kb/`）下**当前不存在**（该目录只有 `kb.sqlite`），
  到它出现前用 SQL 直查：`select d.path, c.section, substr(c.text,1,400) from chunks c join docs d on d.id=c.doc_id where c.text like '%<term>%' limit 5;`

## L13 环境变量（踩过才记）

- `NO_PROXY=localhost,127.0.0.1,::1`——IPv6 回环**不带方括号**，写成 `[::1]` 会让 curl 把整条当域名。
- `HF_ENDPOINT=https://hf-mirror.com`——取模型/权重一律走镜像，直连会被墙住并拖成超时。

## L14 P-300：0 字节日志不等于「内核没跑」

27 内核目前没有任何串口输出，`0 字节` 只说明**我们听不到**，不说明它没执行到。
本线的措辞纪律：正式图没出现 marker 时写「本镜像不可触发（探针未编入）」，**不写**「内核没跑」；
两者在 0 字节场景下不可区分，写成后者就是把「无观测」当「有结论」（与 L2 同源）。

## L15 上机冻结（2026-11-22T03:02 起）

`k60-gates/docs/engineering/BOOT-FREEZE.md` 的 `state = "frozen"`，`scripts/flash.sh` 在每次 `fastboot boot`
前读它，只有用户本人改成 `lifted` 才放行；环境变量绕过等同铁则 9 违规。
对本线的含义：诊断图飞行**现在不可能发生**，汇报里写「被冻结」而不是「待排」。
解冻条件见该文档五条（同一次启动内日志通路 / 或屏幕侧第一行打点、离线三连证据、自动引导、自动复位）。

## L16 P-307：ramoops 在 DRAM，复位即归零

读卡器读到的永远是「刚被复位清掉的窗口」⇒ **读空不是证据**。任何以 log 通道为依据的结论，
先回答四问：`lifetime`（活多久）/ `read_moment`（什么时刻读）/ `writer`（谁写）/ `loss_condition`（什么条件丢）。
门禁 `k60-gates/scripts/check-channel-lifetime.py` 只扫 `k60-gates/docs`（`ROOT` 取 `parents[1]`），
2026-11-22 在它自己那棵树上报 rc=1，与本线无关；本线若写通道类段落，主动把四问答上。
