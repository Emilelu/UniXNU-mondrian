# P-271 待落盘条目（音频线起草，Lead 取用）

> 号是 Lead 2026-11-20 分配的：main 的 PITFALLS 最大号 P-265，P-262 已被占，P-263…P-270 已分给
> cellular / bt / main，P-271 留给我们。标题按 Lead 的意思收窄。本文件只在音频分支，
> 合分支时由 Lead 落盘到 `docs/engineering/PITFALLS.md`。

## P-271 — 一个数字被写在四处，加完不重跑，那句话就开始说谎

**现象**：`docs/research/audio/IOS27-USERLAND.md:84` 长期写着「`sh scripts/check-audio27-preflight.sh`
→ 八行 `ok` 与 `PREFLIGHT OK`」。那是 8 行的时代；2026-11-20 那一版已经打到 55 行。同一个数字还写在
另外三处：`scripts/check-audio27-preflight.sh` 的头部注释、
`docs/research/audio/IOS27-MIGRATION.md`（「随后五十四行 `ok`」）、以及
`porting.toml` 音频区的 `result = "… 54 host rows plus one skip …"`。
加检查行时只改脚本，另外三处照旧——加到第四次，三句话已经同时在说谎，而没有任何测试读它们。

**为什么「写个正则静态数一行」也不行**：在 `894a3ae` 那一版上，按 `run "名字"` 与
`*_row "名字"` 数得 49 个调用点，真实运行是 51 行。差的不是「十几个裸 printf」，是两处：
`optional_row` 与 `seam_row` 按子命令退出码 0/3/其他 打 ok/skip/FAIL，静态看只是一个调用点；
而 `27 series carries the patch` 与 `sheng audioreach host tests` 在成功路径上各有一条直写的 printf。
（那些行号只属于那一版，现在的形状已经不同，不要再引用它们当现状。）
结论：行数不能由读脚本的人算，只能由跑脚本的脚本算。

**做法**：一处常量、自己数自己、页面与记录变成可执行断言。

- `scripts/check-audio27-preflight.sh` 头部 `ROWS_EXPECTED`（脚本自己声明，页面不抄）；
- 同一脚本在 `set -u` 之前有一段外壳：`K60_PREFLIGHT_INNER=1 sh "$0" "$@" > "$inner"`，过滤内层
  `PREFLIGHT OK` 汇总行，`grep -cE '^(ok|skip|FAIL) '` 数出行数。不等就
  `ROWS FAILED %s rows printed, %s declared` + `PREFLIGHT FAILED` 退 1；相等则末行
  `PREFLIGHT OK %s rows (%s ok, %s skip, %s FAIL), as declared`（仍以 `PREFLIGHT OK` 开头，
  别处 `tail -1` 依赖它）；
- 每个「环境不在」的分支给每个检查各打一行 skip：没有 27 树是六行，没有 sheng 检出是三行，
  sheng 的 ABI 与注入不再挂在 host 测试成功之下。少一棵树只应该改变 ok/skip 的比例，不应该缩短整跑；
- `scripts/check-audio27-rows.py` 把散文变成断言：读 `ROWS_EXPECTED`，要求脚本里真的还有那段比对
  （匹配 `ROWS FAILED %s rows printed, %s declared`，否则常量本身也是散文），再把页面里每个
  「N 行 `ok` … M 行 `skip`」与 `porting.toml` 的「N host rows plus one skip」对账。
  配对按整句走：同一行会先说「这两行变 `skip`」再给总数，只抓相邻标签会把那句单独的 skip
  和下一组的 ok 配成一对，算出一个从未打印过的总数。围栏代码块里的示例输出不参与对账。
  成功行是 `ROWS OK <N> rows declared, counted the same in <k> page claim(s) and the record`；
  每条计数另有一行 `ROWS NOTE: … counts <ok> ok and <skip> skip` 把位置说清；
  同一门禁也拒绝页面抄旧读数：`PREFLIGHT OK <old> rows` 或 `ROWS_EXPECTED=<old>` 与声明不符就红；
  `--pac-only` 的四行单独解析，不要求等于整跑；
- `scripts/tests/test-audio27-rows.py` 十二例：一致 / 页面多报 / 记录漂移 / 常量被删 / 比对被删 /
  页面没写 / 同一行三种形状都对 / 示例读数漂移 / 示例常量漂移 / PAC-only 自己的四行 /
  真外壳接受声明行数 / 真外壳拒绝少一行。最后两例把外壳本身抽出来跑，
  所以它不只是「格式字符串还在」；
- 预检里两行：`row count gate is honest` 与 `row count holds`。

**可复现**：

下列比例以规范 sheng、原始 27 树、已接驱动和框架检出都存在，且未给 `XNU27_KERNEL` 为条件；路径按本机实际位置替换。
这证明检查项与文档计数一致，不证明内核产物或硬件成功。

```sh
K60_GATES=/mnt/e/hackios/k60-gates UNIXNU=/mnt/e/hackios/UniXNU \
  SHENG_REPO=/mnt/e/k60-work/UniXNU-sheng \
  XNU27_REPO=/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc \
  sh scripts/check-audio27-preflight.sh
# PREFLIGHT OK <N> rows (<ok> ok, <skip> skip, 0 FAIL), as declared
python3 scripts/check-audio27-rows.py .
# ROWS OK <N> rows declared, counted the same in <k> page claim(s) and the record
python3 scripts/tests/test-audio27-rows.py
# TESTS OK 12 cases
```

把 `IOS27-MIGRATION.md` 那条计数句里的 ok 数改小两行（skip 不动）再跑第二条：

```text
ROWS FAILED: docs/research/audio/IOS27-MIGRATION.md:<line> says <ok> rows ok and <skip> skip, which is <sum>,
but the preflight declares <N>
```

把 `porting.toml` 的 host rows 减二，得到：

```text
ROWS FAILED: porting.toml records <host> host rows plus one skip, which is <host+1>,
but the preflight declares <N>
```

**一般化**：任何「N 行全绿」的说法，只要 N 是手写的，它就在写下的那一刻开始过期；
而「数行」这件事在有多形态输出（ok/skip/FAIL、helper、裸 printf）的脚本里，静态阅读必然数错。
正确形状是**让产物报数、让门禁把文档里的数字当断言读**——一处常量，三处对账。

**边界**：常量仍然是手写的（加一行检查要加一），但只剩一处：写错时脚本自己红，
而不是三处散文同时安静地说谎。
