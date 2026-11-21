# 翻 `PONG_SCANOUT_V2_LAYOUT` 0→1 之前必须为真的五件事

这份文件只做一件事：让「可以翻了」这句话**可判定**。它不是计划，不是说明，也不复制 flip 条件——
flip 条件与 flip owner 只在 `GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.5 维护，这里只指回去（P-259：
同一件事抄第二份，就多一处会过期）。

每条都给一个现在能跑的命令或一个 `文件:行`。跑不出来的条目不写进来。

---

## 1 五条

| # | 必须为真 | 判据 | 现在 |
| --- | --- | --- | --- |
| 1 | display 会签在案，且它**逐行**签了 `token`/`evict`/`target` 的语义 | 会签文件里有一段以 `dbuf` 为主题的同意（不是「已阅」），逐行给出「一致 / 不一致」；不一致时说清正确读法。日期与引文抄进本表第 1 行的 `recorded:` 备注；三行缺一不算（表的形状见 `GPU-27-V2-FIELDS.md` §3.1） | **否**——在等「57 槽」的回答，三行也还没签 |
| 2 | v2 layout 补丁进入某个 series | `grep -rn "pong-scanout-v2-layout-asserts" patches/*/series` 恰好 1 行，且 `python3 scripts/check-series-numbering.py` 通过 | **否**——补丁在 `patches/proposed/`，不在任何 series |
| 3 | offset 补丁排在那份之前 | 同一 series 中 `pong-scanout-assert-offsets` 的行号小于 v2 layout 的行号 | **否**（约束已写在补丁头，series 未建） |
| 4 | 四个偏移由编译器断住 | ①离线：`g++ -std=c++17 -Wall -Wextra -c E:/k60-work/scratch/prop/v2_layout_probe.cpp -o /tmp/v2probe.o` 退出 0；②翻后构建：`PONG_SCANOUT_V2_LAYOUT=1` 编译通过，且 wire 头里的四条 `static_assert`（56 / `token`@44 / `evict`@48 / `target`@52）与补丁 hunk 逐字一致；③常设：`python3 E:/hackios/k60-gates/scripts/check-gpu27-flip-asserts.py` 按 sha256 比对两份拷贝 | ①**是**（已跑，`COMPILE OK`）；②待；③**休眠中**（补丁不在 series ⇒ 退 0 并自己说明；进 series 那天自动变判据） |
| 5 | 翻开关的那次飞行能判 | `python3 E:/hackios/k60-gates/scripts/judge-gpu27.py <console.log> --json` 里 `stats.scanout_version == 2`，且无 `BadArgument`、`dropped <= offers/20`、`client <= 8333`（后两项在草案带上后才出现） | **否**（还没有带 v2 的飞行） |

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

## 3 第 5 条的反例（比正例更有用）

- 翻开关后飞行仍打印 `scanout version=1` ⇒ 内核还是 v1，**立即停**：要么补丁没进 series，要么镜像里
  带的是旧 kext。不要继续看帧率，那组数没有意义。
- `scanout version=2` 出现、但 presenter 打 `scanout frame wait stopped` ⇒ 两侧尺寸不同步，回到 §2.3 的
  四向矩阵找是哪一向。
- `scanout version=2`、无 `BadArgument`、但 `dropped/offers > 5%` ⇒ 布局通了、记账没通，属 display 的
  dbuf 记账，不是本开关的问题。

## 4 与其它文档的关系

| 想问什么 | 去哪 |
| --- | --- |
| flip 条件与 owner | `GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.5（唯一维护处） |
| 版本语义、四向矩阵、断言清单 | 同一文件 §2.1 / §2.3 / §2.5 |
| 27 侧读者行号与两处硬编码 | 同一文件 §2.6 |
| 休眠补丁与它为什么现在不成立是对的 | `patches/proposed/README.md` 的 Dormant 段 |
| 翻不过去时先查什么 | 本文 §3 |
