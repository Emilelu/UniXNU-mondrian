# 探针的开关：两种实现、选哪种、以及一条可跑的断言

> 状态：离线定稿（2026-11-21）。Lead 裁决走「编译期开关，0 B」；本文是这条裁决的实现说明，并给出「开关关掉时镜像里不存在该字面量」的可跑断言。
> 适用：`patches/proposed/0003-k60-backlight-probe-the-clamp.patch`（只适用 27 分支，叠在 0001 之上）。

## 0 为什么不是启动参数

| 方案 | 字节 | 结论 |
| --- | --- | --- |
| `k60_backlight_probe=1` | 21 字符 + 1 分隔空格 = **22 B** | 放不进。O1 之后 603 B，上限 607 B，只剩 4 B；加进去 625 B，超 18 |
| `k60bl_probe=1`（缩短） | 15 B | 仍 619 B，超 12 |
| 编译期开关 | **0 B** | 采纳（Lead 2026-11-21T19:23） |

并且这个名字从未进过任何注册表，所以「撤掉」是空操作，不需要删行。实测：

```
grep -c k60_backlight_probe docs/engineering/BOOT-ARGS-PENDING.toml   -> 0
grep -c k60_backlight_probe scripts/check-image-args.py               -> 0
grep -c k60_backlight_probe docs/engineering/BOOT-ARGS.md             -> 0
```

`ALLOWED_ADDITIONS`（`scripts/check-image-args.py:44` 起）里的背光键只有 `k60_backlight`、`k60_backlight_control`、`k60_backlight_invert` 三个，也没有它。

## 1 实现 A：源码常量

做法：新增一个被跟踪的头，里面写

```c
#define K60_BACKLIGHT_PROBE 0    /* 诊断图改成 1 */
```

`K60Backlight.cpp` 改成 `#if K60_BACKLIGHT_PROBE`。

- 成本：诊断图与正式图的**源码不同**。要让两张图的 `git` 状态都干净，诊断图必须多一个「改成 1」的提交，或者带着脏工作树构建。
- 致命的一点：这个 1 会随合并、cherry-pick、`git checkout` 泄漏进正式图，而构建记录里看不出来——回读一份 `kernel.macho` 无法判断它是哪张图。Lead 要的「输入相同、只差一个开关」在这里证不了：源码本身就不相同。

## 2 实现 B：构建脚本注入 `-D`（本线选它）

做法：源码里

```c
#ifndef K60_BACKLIGHT_PROBE
#define K60_BACKLIGHT_PROBE 0
#endif
```

只有诊断图在构建命令里多一个 flag：

```sh
XNU_EXTRA_CFLAGS=-DK60_BACKLIGHT_PROBE=1 ./scripts/build-xnu-4k-baseline.sh ...
```

选择理由，四条按分量排：

1. **源码与补丁集完全相同**，所以「series 指纹相等」这一条能成立——两张图的差异只在构建命令行。A 做不到。
2. **开关状态留在构建记录里**：`XNU_EXTRA_CFLAGS` 会原样出现在构建日志与 `ps` 里，事后能回答「这张图是怎么编出来的」。
3. **默认 0 是 fail-safe 方向**：忘记加 flag 得到正式图；A 忘记改回来得到带探针的正式图，那是错的方向。
4. 不需要改脚本：`XNU_EXTRA_CFLAGS` 已经是现成通道——`scripts/build-xnu-4k-baseline.sh:574` 把它读成 `EXTRA_CFLAGS` 的默认值，`:581`/`:989`/`:1384`/`:1387` 逐项追加 `-D`，`:1392` 全局注入，`:1444` 交给 `RC_NONARCH_CFLAGS`；`scripts/build-xnu-generic.sh:281`/`:586`/`:597` 同构。

已知限制：这个变量同时会喂给所有 target，所以只传一次的构建必须干净重建（切换开关后别复用同一 `OUT` 目录里已编好的对象）。

## 3 两张图各记什么

证据目录里每个镜像一张表，四个指纹都要，缺一列就无法证明「只差一个开关」：

| 镜像 | series 指纹 | boot.img sha256 | kernel.macho sha256 | FD sha256 | 构建命令里的开关 |
| --- | --- | --- | --- | --- | --- |
| 正式 | 待飞 | 待飞 | 待飞 | 待飞 | 无 |
| 诊断 | 待飞 | 待飞 | 待飞 | 待飞 | `XNU_EXTRA_CFLAGS=-DK60_BACKLIGHT_PROBE=1` |

取证命令：

```sh
# series 指纹：补丁集内容 + 基线提交，两者都相同才算输入相同
git rev-parse HEAD
sha256sum patches/xnu/series
while read -r p; do case "$p" in ''|\#*) continue;; esac; sha256sum "patches/xnu/$p"; done < patches/xnu/series

# 三个产物
sha256sum <out>/boot.img <out>/kernel.macho
sha256sum <out>/<carrier>.fd
```

判据：**两张表的 series 指纹必须逐字节相同**；boot.img / kernel.macho / FD 三行必须不同（不同才对，因为开关进去了）；差异清单只允许出现「一个编译期开关」这一项。

## 4 一条可跑的断言

`docs/research/display/check-probe-absent.py`：

```sh
python3 docs/research/display/check-probe-absent.py \
    --release <out>/kernel.macho --diagnostic <diag-out>/kernel.macho
```

它读两个常量串：

- `MARKER = "K60 BACKLIGHT: probe request not built"` ——只在探针块的失败路径里出现，开关关掉时整块不编译，这个串不可能存在；
- `REQUEST_FORMAT = "K60 BACKLIGHT: brightness level %u -> level %u dbv 0x%x"` ——`K60Backlight.cpp` 的请求行格式串，用来挡住「拿错文件也能通过」的情况。

判据：正式图 marker **0 次**，诊断图 marker **恰好 1 次**；两者的 REQUEST_FORMAT 都 ≥1 次。退出码 0 通过、1 失败，每次调用打印所读文件的 sha256（正好喂 §3 的表）。

自测记录（2026-11-21，fixtures 在 `E:/k60-work/scratch/probe-selftest/`，真假内核用同长度字节串模拟）：

```
好对          rc=0  OK probe absent from the release image, present once in the diagnostic image
只给 release  rc=0  note: --diagnostic not given; the positive half of the assertion was skipped
坏 release    rc=1  FAIL …: release image carries the probe marker 1 time(s); it was built with -DK60_BACKLIGHT_PROBE=1
```

第三条是关键：它证明这条断言会在探针泄漏进正式图时**真的失败**，而不是永远打印 OK。

## 5 判据分工（写死）

| 镜像 | 能判什么 | 不能判什么 |
| --- | --- | --- |
| 诊断图 | P1–P5（`BACKLIGHT-LOG-CRITERIA.md` §8.3）：4095 → `brightness level 4095 -> level 2047 dbv 0xfff`、只出现一次、面板最亮不黑屏、参数缺失时不许出现 4095 | 正式图的行为（多了探针） |
| 正式图 | 「本镜像不可触发（探针未编入）」+ `strings` 断言通过 | **任何**关于 0001 有效性的结论；禁止用正式图判补丁无效 |

## 6 失败形态与原因

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| 正式图出现 marker | 构建环境里残留 `XNU_EXTRA_CFLAGS`，或复用了诊断图的 `OUT` 目录 | 清环境、干净重建，重跑断言 |
| 诊断图 marker 0 次 | `-D` 没传到 C++（只对 C target 生效），或源码没编进去 | 看构建日志里的 `EXTRA_CFLAGS`；确认 `K60Backlight.cpp` 在 27 series 里 |
| 诊断图 marker >1 次 | 同一格式串被多个 target 编译 | 记录次数，判据按「存在的形态」看，不按次数 |
| 两个文件都查不到 REQUEST_FORMAT | 传错文件（不是 27 的 kernel.macho） | 换文件，别改判据 |

## 7 未定项

- 27 的 `boot.img` / `kernel.macho` / FD 的实际产出路径依赖构建树（`OUT` 由构建脚本决定），上面的 `<out>` 属占位，飞行时以构建日志打出的路径为准。
- 诊断图会多出一次「上电即最亮」的可见效果（探针在 `publishFirst()` 之后跑），这是预期副作用，不是故障。
