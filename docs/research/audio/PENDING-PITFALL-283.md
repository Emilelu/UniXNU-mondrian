# P-283 待落盘条目（音频线起草，Lead 取用）

> 号由 `python3 scripts/next-pitfall-id.py` 在 2026-11-20 给出：`next P-283`。本文件只在音频分支，
> 合分支时由 Lead 落盘到 `docs/engineering/PITFALLS.md`。

## P-283 — 一条没有反例的断言，只是在复述当前代码

**现象**：`check-audio27-fptrs.py` 第一版已经能证明四张 io 表「按类型签名成对」、赋值点与成员一致、
调用点首参是自己的 ctx。四张表当时恰好只有 `read`/`write`/`ctx`，所以「没有裸 `void *` 跨层」这句话
从未被检验：把一条 `void *opaque` 加进 `PongGeniIo`、再在 `PongAudioGeniI2c.c` 里真做一次跨层赋值，
旧检查仍然全绿——因为它没有「表里多出一个字段」这条规则，只有「现有字段都对」。
0531 的弱调用也一样：源码里的 `__attribute__((weak))` 与理由都齐，但「选中系列却没人定义」没有任何
夹具，于是「缺定义是链接错误」只是注释里的一句话。

**为什么正例不够**：正例只证明检查器与当前文件形状兼容，不证明规则存在。门禁写完后如果只拿真树跑一遍，
得到的是「今天的代码恰好如此」；明天有人加字段、换赋值形状，门禁会安静地继续绿。反例必须动**被检对象**
本身（加字段、改原型、删赋值、换成错误来源），而不是只改期望字符串。

**做法**：每条断言至少一个能打红的夹具，失败行要点名对象。现在：

- `scripts/tests/test-audio27-fptrs.py` 十九例，其中 `bare_void_assignment` 给 `PongGeniIo` 加
  `void *opaque`，并在 `PongAudioGeniI2c.c` 做 `g->io.opaque = (void *)config;`，期望
  `PongGeniIo carries the field opaque, which is not one of its contexts (ctx)`；
- `scripts/tests/test-audio27-weak-link.py` 十四例，其中 `selected_without_definition` 给出「系列选中、
  链接清单有对象、符号表只有 `U`」的形状，期望 rc1、`no definition of pong_audio_amp_probe` 与
  `an undefined weak reference is a link error ... not a silent run-time fallback`；
- 其余反例覆盖少参数的生产者、从别的字段拷贝、把回调清零、整表拷贝错类型、删掉一个成员、非弱定义、
  `W` 空壳、错文件清单等。

**可复现**：

```sh
python3 scripts/tests/test-audio27-fptrs.py
# TESTS OK 19 cases
python3 scripts/tests/test-audio27-weak-link.py
# TESTS OK 14 cases
```

把 `PongGeniIo` 的 `void *opaque` 那条例子的期望删掉再跑，第一条会红并打印上面那句；把 0531 的定义行
从符号表夹具里删掉，第二条会红并打印链接错误。两只都是纯文本检查：不编译、不链接、不上机。

**一般化**：正例证明「现在能用」，反例证明「规则真的在」。没有反例的断言与注释同义；它保护的是写它的
那次提交，不是下一个人。

**边界**：这是私有预检，不进全局 blockers（stage 0 不编音频）；它不替代真实链接与真机；P-283 的号由
allocator 给，本文不手挑号。
