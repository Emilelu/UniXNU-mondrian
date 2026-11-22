# ccache 进 iOS 27 内核构建：接上了，但今天不可能命中

日期：2026-11-22　分支：`diag/menu-hold-20261121`　判据：对象构建记录与 `ccache -s`，不是脚本里的字样

## 一句话

ccache 已经在内核编译命令链上：`scripts/build-ios27-linux.sh:101-108` 导出 `CCACHE`（存在 ccache 时），
XNU 自带开关 `makedefs/MakeInc.def:170` `CCACHE ?=` / `:175` `KCC = $(CCACHE) $(CC)` 把它拼进编译命令。
**但每个对象仍然是 0 命中**：XNU 三条编译规则都带 `-MJ`（`MakeInc.rule:513`/`:521`/`:543`），ccache 4.9.1
判其 `unsupported_compiler_option`，对象全部不进缓存。接与不接读数相同——P-301 的形状，区别在于这次量了。

## 四段耗时（实测，见 `docs/engineering/IOS27.md:481-492`）

| 阶段 | 每次重建 | 固件卷复用 | ccache 能帮到哪一段 |
| --- | --- | --- | --- |
| profile / fetch / defconfig | 4 s | 5 s | 不能：git 与 submodule |
| kernel + 链接 + payload 打包 | 452 s | 451 s | **只有 XNU 的 C/汇编/C++ 编译**，今天全被 `-MJ` 挡住 |
| 固件卷（EDK II `-n 8` + GenFds） | 519 s | 3 s | 不能：EDK II 自己的构建系统，本仓的 `CCACHE` 到不了；提速靠复用键 |
| bootimg 与产物检查 | 0 s | 171 s | 不能：192 MB payload 的 FAT 打包，纯 I/O |
| 合计 | 975 s | 630 s | |

按四段口径：kernel 450–760 s、payload 与 kernel 同在这 452 s 一行内（`mark payload` 在 `unixnu build payload`
之后，`scripts/build-ios27-linux.sh:113`）、固件卷 0 s（复用 3 s）或 ~519 s、bootimg 171 s。kernel 单独没有 stage
mark；冷树没有 `.o.json` 时 `scripts/unixnu/kernel.py:205` 先跑一跳 bootstrap（`:211-219`）再跑正式一跳（`:225`），
`kernel-bootstrap.log` 与 `kernel.log` 各 181 MB，这就是 760 s 上界的来源；要精确到秒，下次构建补 `mark kernel`。
预链接（`XnuPrelink`）与 `ld` 链接是链接步骤，ccache 只代理编译器，天然不覆盖。

## 接线点（都在上游 XNU 与框架里，本仓只负责传变量）

- `feeds/xnu-3199e8bc/makedefs/MakeInc.def:170` `CCACHE ?=`；`:175` `KCC = $(CCACHE) $(CC)`；
  `:176` `KC++ = $(CCACHE) $(CXX)`；`:851` `AS = $(CCACHE) $(CC)`
- 用它的规则：`MakeInc.rule:521`（C）、`:513`（汇编）、`:543`（C++）——三条都带 `-MJ`
- 内核真正的 `CC` **不是** `scripts/build-xnu-generic.sh:72` 的 `HOST_CC`（那只是 host 工具）：
  `MakeInc.cmd:227` 用 `$(XCRUN) -find clang` 解析出 `/opt/unixnu-linux/llvm/bin/clang-24`。
  所以 PATH 里放个叫 clang 的壳子无效，只有 `CCACHE` 变量有效
- 变量怎么到 make：`scripts/build-ios27-linux.sh:110-111` 调 `unixnu build kernel`，
  框架 `scripts/unixnu/kernel.py:186` 把 `os.environ` 原样传给 builder
- `CCACHE` 是普通 make 变量，环境里的同名变量被 `?=` 尊重，所以 `export` 即可到达；
  P-301 里失效的是点号命名的 `PongAudioAmp.o_CFLAGS_ADD`，两者不是一回事
- 缓存目录也钉在同一处（`scripts/build-ios27-linux.sh:104-107` → `/opt/k60/trees/.ccache`）：
  ccache 默认写 `~/.cache/ccache`，若构建写默认目录而读数用 `/opt/...`，会看到“永远 0 命中”的假象

## 为什么还是 0 命中

用真实 clang 复现（`python3 scripts/check-ccache.py --probe`，本机 0.7 s）：

```
-MJ: 0 hit(s), 0 miss(es), 2 unsupported option | no -MJ: 1 hit(s), 1 miss(es)
```

ccache 调试日志给出的原因是 `Compiler option -MJ is unsupported` → `Result: unsupported_compiler_option`，
对应 `ccache -s` 的 `Uncacheable calls` 行。ccache 直到 4.14.3 都没支持 `-MJ`（issue #446，2019-07-28 开、仍 open），换版本不是出路。

也不能把 `-MJ` 删掉了事：`.o.json` 是“编译参数真的到达编译器”的唯一证据（框架 `scripts/unixnu/kernel.py:205` 读
`startup.o.json`，`scripts/check-boot-progress-code.py:33` 等也读），删了等于把 P-301 的检测手段一起删掉。

## 怎么读命中率

```sh
CCACHE_DIR=/opt/k60/trees/.ccache ccache -s
```

只看三行：`Hits`（含 `Direct`/`Preprocessed`）、`Misses`、`Cache size`。对照判据：

- 接上了但 `-MJ` 还在：`Hits 0`、`Uncacheable calls` ≈ 对象数（数千）、`Cache size` 停在 `0.0 GiB`
- 接上了且 `-MJ` 不再挡：同一棵树第二次构建 `Hits` 接近“未改动对象数”、`Cache size` 上涨
- 没接上：这些数字不动（`ccache --print-stats` 的 `stats_updated_timestamp` 不前进）

离线版 `python3 scripts/check-ccache.py`：报二进制与版本、`CCACHE_DIR`、接线三态（`wired` 退 0 / `not wired` 退 1 /
`cannot tell` 退 2），并核对“构建写哪个目录、你在读哪个目录”；`--self-test` 用 7 个假树自检（含“只有注释里写着
CCACHE”和“PATH 壳子”两个陷阱），`--probe` 用真 clang 重放上面的 `-MJ` 对比，全部不跑构建。

## 移交单（本仓改不了）

> 让 `MakeInc.rule:513/521/543` 的 `-MJ` 变成可选（或增加一条不带 `-MJ` 的编译路径），
> 同时把 `scripts/unixnu/kernel.py:205` 等依赖 `.o.json` 的校验改成不依赖它；否则等
> ccache 支持 `-MJ`（ccache#446）。由框架/XNU 维护者（Lead）决定并实施。
