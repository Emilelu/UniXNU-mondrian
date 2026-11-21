# 翻 `PONG_SCANOUT_V2_LAYOUT` 0→1 之前必须为真的五件事

这份文件只做一件事：让「可以翻了」这句话**可判定**。它不是计划，不是说明，也不复制 flip 条件——
flip 条件与 flip owner 只在 `GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.5 维护，这里只指回去（P-259：
同一件事抄第二份，就多一处会过期）。

每条都给一个现在能跑的命令或一个 `文件:行`。跑不出来的条目不写进来。

---

## 1 五条

| # | 必须为真 | 判据 | 现在 |
| --- | --- | --- | --- |
| 1 | display 会签在案，且它**逐行**签了 `token`/`evict`/`target` 的语义 | 会签文件里有一段以 `dbuf` 为主题的同意（不是「已阅」），逐行给出「一致 / 不一致」；不一致时说清正确读法。日期与引文抄进本表第 1 行的 `recorded:` 备注；三行缺一不算（表的形状见 `GPU-27-V2-FIELDS.md` §3.1） | **是**（2026-11-21 第 3 轮）：`token`、`evict` 签一致并附条件；`target` 签**不一致**，已按它的读法改成「索引 + 1」，记录见 proposal §2.1 的 decision record 1 |
| 2 | v2 layout 补丁进入某个 series | `grep -rn "pong-scanout-v2-layout-asserts" patches/*/series` 恰好 1 行，且 `python3 scripts/check-series-numbering.py` 通过 | **否**——补丁在 `patches/proposed/`，不在任何 series |
| 3 | offset 补丁排在那份之前 | 同一 series 中 `pong-scanout-assert-offsets` 的行号小于 v2 layout 的行号 | **否**（约束已写在补丁头，series 未建） |
| 4 | 四个偏移由编译器断住 | ①离线：`g++ -std=c++17 -Wall -Wextra -c E:/k60-work/scratch/prop/v2_layout_probe.cpp -o /tmp/v2probe.o` 退出 0；②翻后构建：`PONG_SCANOUT_V2_LAYOUT=1` 编译通过，且 wire 头里的四条 `static_assert`（56 / `token`@44 / `evict`@48 / `target`@52）与补丁 hunk 逐字一致；③常设：`python3 E:/hackios/k60-gates/scripts/check-gpu27-flip-asserts.py` 按 sha256 比对两份拷贝 | ①**是**（已跑，`COMPILE OK`）；②待；③**休眠中**（补丁不在 series ⇒ 退 0 并自己说明；进 series 那天自动变判据） |
| 5 | 翻开关的那次飞行能判 | 一条命令问两半：`check-gpu27-postflip.py` 既要飞行里出现 `PONG SCANOUT: … scanout version=2`（缺这个字段是红，不是「未测量」），也要两份 flip 断言逐字一致，再把判读器自己的 budget 结论并进来。命令与三态期望见 §2.3 | **是（判据已可跑，等真飞行）**——11 个反例全过；真机上还没有 v2 飞行 |

### 已记录的会签（第 1 条）

```
recorded: 2026-11-21  reply-gpu-display-sync.md 第 136 行起（display 第 3 轮）
          token 一致 —— 附两条：几何真变时全表作废；token 随映射创建生成，禁止按同 offset/bytes 命中旧 token
          evict 一致 —— 附三条：先于本帧拷贝生效；内核退休后 drop，ack 后只读不写；仅同 surface 新换旧时可非 0
          target 不一致 —— 原「字节偏移 + 0 = 无 dbuf」自相矛盾（db[0].offset 就是 0），改为「索引 + 1」
          备注：它同时签了备选（保留偏移 + 哨兵 0xFFFFFFFF），我们选了索引方案，理由见 proposal §2.1
```

第 1 条的 `recorded:` 长这样（**只写日期与引文，不写 flip 条件**）：

```
recorded: 2026-XX-XX  reply-gpu-display-sync.md 第 N 轮 · "token 是同一 surface 复用映射的凭证；
          evict 是必须先丢掉的旧 token；target 是扫出映射里的字节偏移"
```

## 2 现在跑一次（全部离线，不碰设备）

```sh
cd E:/hackios/k60-gpu-27
grep -rn "pong-scanout-v2-layout-asserts" patches/*/series      # 期望：没有输出（第 2 条为否）
grep -rn "pong-scanout-assert-offsets"      patches/*/series      # 期望：没有输出
python3 scripts/check-series-numbering.py                         # 期望：通过（与上面两条否并不矛盾：
                                                                  #   没有 series 就没有编号可错）
```

第 4 条③现在就能跑，它自己会说自己是休眠的：

```sh
python3 E:/hackios/k60-gates/scripts/check-gpu27-flip-asserts.py
# 期望：dormant: pong-scanout-v2-layout-asserts is in no series, and the header carries no v2 assertions
#       （exit 0）  ——--strict 才把它算成失败
```

第 4 条①要在 WSL 里跑（MSYS 没有 g++）：

```sh
wsl -e bash -lc 'g++ -std=c++17 -Wall -Wextra -c /mnt/e/k60-work/scratch/prop/v2_layout_probe.cpp -o /tmp/v2probe.o && echo COMPILE OK'
# 期望：COMPILE OK
```

探针证明的是**四个数本身**（一个同样排列的 56 B 结构体），不是树里的头文件——树里现在还没有那三个
字段，所以它只能证明数对，不能证明树对。第 4 条②才是证明树的那一半。

### 2.3 第 5 条：翻后的那半（这条命令本身就是判据）

自包含：路径、参数、三态期望各一行。跑不动时先看 `--help`，别猜。

```sh
cd E:/hackios/k60-gates
python3 scripts/check-gpu27-postflip.py <console.log> \
    --judge=scripts/judge-gpu27.py \
    --flip-asserts=scripts/check-gpu27-flip-asserts.py \
    --lane-root=E:/hackios/k60-gpu-27
# 期望 exit 0：PASS the flight says version=2 and the two copies of the flip asserts agree
# 期望 exit 1：FAIL …（the frame line says version=1, not 2 / none says `scanout version=`
#               / the header carries 3 of 4 v2 assertions / 判读器自己的 FAIL）
# 期望 exit 2：cannot judge …（no PONG SCANOUT line / 断言仍是 dormant / 判读器 INVALID
#               / 三个路径少给一个——本工具没有默认值，也不读环境变量）
```

三个路径**都是必填**，不是风格问题：同一份工具要在两棵树里跑（本 lane 有 wire 头，共享树只有本仓库），
写死默认值对其中一个调用者必然错，而「猜一个路径」和「报错」相比，前者会**看起来像判决**。
缺参数一律退 2（与 `check-io-map-budget.py` 的 `source == "default"` 退 2 同一个理由）。

合成夹具（**全部自称 SYNTHETIC**，没有一条来自真飞行）：今天就能跑，不需要设备。

```sh
cd E:/hackios/k60-gates
F=scripts/tests/fixtures/gpu27/postflip
python3 scripts/check-gpu27-postflip.py $F/postflip-v2-ok.log \
    --judge=scripts/judge-gpu27.py --flip-asserts=scripts/check-gpu27-flip-asserts.py \
    --lane-root=E:/hackios/k60-gates/$F/lane-postflip-in-step          # 期望 exit 0
python3 scripts/check-gpu27-postflip.py $F/postflip-v2-no-version.log \
    --judge=scripts/judge-gpu27.py --flip-asserts=scripts/check-gpu27-flip-asserts.py \
    --lane-root=E:/hackios/k60-gates/$F/lane-postflip-in-step          # 期望 exit 1（字段缺席）
python3 scripts/check-gpu27-postflip.py $F/postflip-v2-ok.log \
    --judge=scripts/judge-gpu27.py --flip-asserts=scripts/check-gpu27-flip-asserts.py \
    --lane-root=E:/hackios/k60-gates/$F/lane-postflip-half              # 期望 exit 1（断言只剩三条）
python3 scripts/check-gpu27-postflip.py $F/postflip-v2-ok.log \
    --judge=scripts/judge-gpu27.py --flip-asserts=scripts/check-gpu27-flip-asserts.py \
    --lane-root=E:/hackios/k60-gates/$F/lane-preflip                    # 期望 exit 2（还没翻）
python3 scripts/tests/test-check-gpu27-postflip.py                     # 期望 TESTS OK: 11 cases
```

夹具为什么在 `scripts/`：`sync-device-input.py` 的 ITEMS 镜像 `scripts/` 而不镜像 `docs/`，所以放在
`docs/` 下的输入**永远不可能**因为「没同步」而红——那条判据就只在有人手跑的那一刻有效（P-205 家族）。

**为什么「字段缺席」在这一条里是红，而在判读器里是 unmeasured**：判读器测「这一侧花了多少」，没人测
就是没人测；这条门禁测「树声称自己已经翻了」，缺席本身与声称矛盾。两处判断不同、两处都写了理由——
这也是两份门禁不能合成一份的原因（一个判据一个输入面）。

## 3 第 5 条的反例（比正例更有用）

- 翻开关后飞行仍打印 `scanout version=1` ⇒ 内核还是 v1，**立即停**：要么补丁没进 series，要么镜像里
  带的是旧 kext。不要继续看帧率，那组数没有意义。
- `scanout version=2` 出现、但 presenter 打 `scanout frame wait stopped` ⇒ 两侧尺寸不同步，回到 §2.3 的
  四向矩阵找是哪一向。
- `scanout version=2`、无 `BadArgument`、但 `dropped/offers > 5%` ⇒ 布局通了、记账没通，属 display 的
  dbuf 记账，不是本开关的问题。
- 翻后飞行里**一条 `PONG SCANOUT:` 行都没有** ⇒ 判不了（exit 2），不是通过：扫出路径根本没跑。
- HEAD 里四条断言只剩三条（有人删了一行）而 series 里仍有那份补丁 ⇒ exit 1，报
  `the header carries 3 of 4 v2 assertions`。这是「翻了但 v2 字段缺席」在编译期那一侧的样子；
  飞行里没有 `scanout version=` 是它在运行期那一侧的样子，两者都红。

## 4 与其它文档的关系

| 想问什么 | 去哪 |
| --- | --- |
| flip 条件与 owner | `GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.5（唯一维护处） |
| 版本语义、四向矩阵、断言清单 | 同一文件 §2.1 / §2.3 / §2.5 |
| 第 5 条那条命令本身 | `E:/hackios/k60-gates/scripts/check-gpu27-postflip.py`（夹具 `scripts/tests/fixtures/gpu27/postflip/`） |
| 第 4 条③比的是哪两行 | `E:/hackios/k60-gates/scripts/check-gpu27-flip-asserts.py`（它同时提供 `--strict`） |
| 27 侧读者行号与两处硬编码 | 同一文件 §2.6 |
| 休眠补丁与它为什么现在不成立是对的 | `patches/proposed/README.md` 的 Dormant 段 |
| 翻不过去时先查什么 | 本文 §3 |
