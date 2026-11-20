# iOS 27 stage 0：音频不在构建里，这是设计

> 2026-11-20。这里只回答一件事：stage 0 的 27 构建里没有音频线，所以任何「音频 0 符号」的读数都不是回归。
> 迁移阶段与 F1/F3/F4 的分工见 `IOS27-MIGRATION.md`，接缝判据见 `IOS27-WIRING.md`。

## 一、谁把音频关掉的

`k60-gates/board.toml` 的 `[os_overrides."ios-27.0.1-24A446"]` 有三处：

- `remove = ["kernel.pong_native_driver_source"]`，注释写明 stage 0 不建 Pong 驱动树，F3 回来；
- `components.include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink"]`，没有 PongUfs 或其他 Pong 组件；
- 27 的 defconfig 与 16.6.1 分开，音频的 conf/files 行只在接线 applier 跑过之后才存在。

再往下还有两道闸：

1. 构建驱动 `scripts/build-ios27-linux.sh` 只有在 `"$ROOT/scripts/k60-conf-files-hook.py"` 存在时才设
   `K60_CONF_FILES_HOOK`；gates 检出里没有这个文件，所以变量根本不设，stage 0 不往 conf/files 里加任何
   lane 对象。
2. `patches/xnu-12377/series` 把 `0531-k60-audio-amp-probe-call.patch` 注释掉了（HOLD）。系列自己的注释
   写了顺序：先强制加载 `PongAudioAmp.o`，再列调用点补丁；在那之前列 0531 会让内核链接失败。

于是「内核里没有音频符号」是这三件事同时成立的结果。它不是链接器丢了对象，也不是 27 回归。

### 谁能改变这个状态

要把音频线放回构建，下面三处必须同时改；少一处就仍是惰性：

- `k60-gates/board.toml:360`：把 `"PongUfs"` 加回 `components.include`（现在只有 `ArmDTPlatform`、`ArmCpu`、`XnuPrelink`；组件定义在 `UniXNU/components.toml:552`）。
- `k60-gates/board.toml:352`：从 `remove` 数组里删掉 `"kernel.pong_native_driver_source"`（`remove` 块可以整块删掉）。
- `k60-gates/scripts/`：放入 `k60-conf-files-hook.py` 和它调用的 `add-audio-conffiles.py`（音频仓同名文件；后者在 `:34-35` 写 `bsd/dev/PongAudioGeniI2c.c`、`bsd/dev/PongAudioAmp.c` 两行），`build-ios27-linux.sh:52` 才会看见钩子并设 `K60_CONF_FILES_HOOK`。

谁能验（第三条同时读 `conf/files`；三行都成立才是 stage 0）：

```sh
sed -n '360p' "$K60_GATES/board.toml"          # include 里没有 PongUfs
sed -n '352p' "$K60_GATES/board.toml"          # remove 里有 kernel.pong_native_driver_source
test ! -e "$K60_GATES/scripts/k60-conf-files-hook.py" && ! grep -n 'PongAudio' "$XNU27_TREE/bsd/conf/files" && echo 'stage 0: hook absent, conf/files has no PongAudio line'
```

这三条只关掉 stage 0 的惰性，不放行 0531：系列仍按 `patches/xnu-12377/series:52` 的注释，先强制加载 `PongAudioAmp.o`，再列调用点补丁。改完后对产物重跑 `scripts/check-audio27-kernel.py`，读到 `strings 3/3` 与 `symbols 3/3` 才算音频真的进了构建。

## 二、三分钟自证

需要三样东西。前四条自证只用 `python3`，不编译内核；第 5 条整跑会调用宿主编译器跑 host 套件。

- `K60_GATES`：`k60-gates` 检出，里面要有 `board.toml` 与 `patches/xnu-12377/series`；
- `XNU27_TREE`：27 的 XNU 源码树（`xnu-12377.121.6` 级别）。整跑预检把同一棵树叫 `XNU27_REPO`，两个名字各用各的命令，值指向同一路径；
- `XNU27_KERNEL`：stage 0 构建出的 `kernel/kernel.macho`，或从 `payload.img` 的
  `EFI/UniXNU/Payloads/` 取出的同名文件。

整跑还需要一个框架检出（`UNIXNU=` 指路，默认 `/tmp/UniXNU`）：没有时 `framework passes env to builder` 一行 `skip`，不是失败。

### 0. 七步记录本身

音频的七步记录在 `docs/research/eight-step/audio-27.toml`；只读检查：

```sh
python3 scripts/check-audio27-eight-step.py
```

期望 `AUDIO27 EIGHT-STEP OK: 7 steps, ... no device step`。它只查记录形状与引用（七步、每步
`recorded_at`、`evidence` 数组、official 的 `docs/zh` 章节、verify 三类检查、没有 device 步），
不构建，也不证明音频能出声。

### 1. 产物里真的没有音频

```sh
python3 scripts/check-audio27-kernel.py "$XNU27_KERNEL"
```

期望读数是三行加一个非零退出码：

```text
audio27 kernel: strings 0/3 (...)
audio27 kernel: symbols 0/3 (...)
AUDIO27 FAILED: ...
```

这里的 `rc=1` 是设计读数：脚本断言「27 内核带着音频」，stage 0 没有，所以它红。不要为了让这一行变绿
去打开音频；也不要把它当成链接错误的证据——它只说明产物里没有那三个字符串和三个符号。

`XNU27_KERNEL` 在完整预检里也是同一行检查。stage 0 上把它设成无音频内核，预检会如实报 `FAIL`；
不设则这一条是 `skip`。两种都符合设计，区别只是你要不要看这个读数。

### 2. 钩子不存在，接缝是 inert

```sh
python3 scripts/check-audio27-builder.py --tree "$K60_GATES" --seam hook
```

```text
BUILDER: hook not present -> seam inert (<path>); the checker checkout is not the driver target
```

`rc=3`。这个 3 不是失败：它说「没有可量的对象」，预检把它当 `skip`。define 与 framework 两条接缝在
stage 0 仍能读，都是 `BUILDER OK`，因为它们只证明驱动怎么把宏和环境递进去，不证明有对象。

### 3. 0531 在系列里是 HOLD

```sh
python3 scripts/check-audio27-series.py "$XNU27_TREE" --series "$K60_GATES/patches/xnu-12377/series"
```

```text
SERIES HOLD: 0531-... sits in ... unlisted, and the series file says why: '...'
SERIES OK 0531-... ... (held, not listed)
```

`rc=0`。它比的是「系列里那份补丁插入的代码」与生成器，不比字节；HOLD 只要求系列注释说明理由。
如果系列里删掉了 0531 却没有任何注释，它会退 1 并点名「does not list it and no comment says why」。

### 4. 弱调用没有被选中

```sh
python3 scripts/check-audio27-weak-link.py --tree "$K60_GATES"
```

```text
NOTE audio: switch off, the call site is not linked
```

`rc=0`。反过来，如果有效系列选中了 0531，而链接清单里没有 `PongAudioAmp.o` 或符号表里没有定义，
它退 1，并打印 `WEAK-LINK why: ld64-port rejects an undefined weak function reference...`；那是链接错误，
不是运行时静默。`__attribute__((weak))` 本身只算 policy note，不放行。

### 5. 整跑

```sh
K60_GATES=<gates> SHENG_REPO=<sheng> XNU27_REPO=<27 source> \
  sh scripts/check-audio27-preflight.sh
```

末行必须是 `PREFLIGHT OK ... rows (...), as declared`。stage 0 上 `27 driver takes the conf hook` 是
`skip`（理由就是上面第 2 条）；不给 `XNU27_KERNEL` 时 `27 kernel carries the audio` 也是 `skip`。
行数由脚本顶部的 `ROWS_EXPECTED` 决定并自检，页面不抄这个数字。只想看 PAC 那四条：

```sh
sh scripts/check-audio27-preflight.sh --pac-only
# PAC PREFLIGHT OK 4 rows (4 ok, 0 skip, 0 FAIL), as declared
```

## 三、这些 checker 的退出码怎么读

`0` 表示「它断言的事为真」；`1` 表示断言为假，行里点名是哪一条；`3` 表示「这里没有可量的对象」，
预检把它变成 `skip`；`2` 是用法或输入错误。`3` 不是通过：stage 0 的钩子读 `skip`，原因正是这条线
不在构建里。

| 脚本 | 0 | 1 | 3 |
| --- | --- | --- | --- |
| `check-audio27-kernel.py` | 三个字符串与三个符号都在 | 缺任一（stage 0 的期望读数） | 不产生 |
| `check-audio27-builder.py` | 接缝 wired | wired but wrong | 没有可量对象（钩子缺失或未被点名） |
| `check-audio27-series.py` | 与生成器一致，或 HOLD 有理由 | 插入代码不同，或未列且无注释 | 补丁还没入账，或旧接线树无法 emit |
| `check-audio27-weak-link.py` | 未选中，或选中且有定义 | 选中但缺链接证据 | 不产生 |
| `check-audio27-fptrs.py` | 四张 io 表成对，赋值点与调用点都对 | 任一表、赋值或调用不合 | 不产生 |
| `check-audio27-rows.py` | 页面与记录的行数都对得上 | 任一处漂移 | 不产生 |
| `check-audio27-preflight.sh` | 所有行 `ok` 或有理由的 `skip` | 任一行 `FAIL` 或行数不齐 | 不产生（它是汇总） |

## 四、这页不证明什么

- 不证明 27 音频能工作：stage 0 没有音频对象，F3 之后才有驱动树，F4 之后才可能有音频日志。
- 不证明链接器行为：真正的链接结论要等 `PongAudioAmp.o` 进链接清单，并由
  `check-audio27-weak-link.py` 读到 `T` 定义；stage 0 连对象都没有。
- 不证明硬件：没有构建、没有上机、没有设备访问。
- 不要把「产物看着没问题」当成判据。P-282 记的是同一类推理错误：本地工具链发不出某个标签时，产物会
  看起来「一切正常」，真正该问的是工具链能不能表达那个值。音频这边同理：0 个符号要先对照 board profile，
  再谈是不是缺陷。
