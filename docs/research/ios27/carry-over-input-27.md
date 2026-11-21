# 输入线（触摸 / 实体按键）的 16 线资产与 27 现状

日期：2026-11-22（第二版：按 Lead m01904 扩成「16 线验证证据 / 27 侧现状 / 移植判据」三列，只扩 `to-port` 与 `ported`）

## 〇、数字怎么数的（每个数都带命令）

口径（Lead m01981，工具见 `k60-gates` 提交 `39238c33` 的 `scripts/series-count.py`）：本文件所有计数一律写成「**N 条补丁行（M 带号 + K 无号）**」，并注明是哪条命令、在哪棵树上量的。

| 量 | 命令 | 结果 |
| --- | --- | --- |
| 16 线 `patches/xnu/series`（本仓 @ `feat/input-27`） | `python3 scripts/series-count.py --tree E:/hackios/k60-input27`（脚本在 `E:/hackios/k60-gates/scripts/`） | **240 条补丁行（129 带号 + 111 无号）** |
| 27 设备仓自辖层 `patches/xnu-12377/series`（同树） | 同上 | **30 条补丁行（28 带号 + 2 无号）**；无号为 `ptrauth-string-discriminator.patch`、`armcpu-sleep-hook.patch` |
| 同名两文件在 `k60-gates` 检出上 | `python3 scripts/series-count.py --tree E:/hackios/k60-gates` | `patches/xnu/series` 240（129+111）；`patches/xnu-12377/series` **36 条（34 带号 + 2 无号）** |
| 27 实际输入清单（**装配树内测得，本仓没有这个文件**） | `grep -c . /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/xnu-patches.list` | **105**，全部来自 `patches/xnu-12377/`；来自 `patches/xnu/` 的为 **0** |

**三点必须写清**：
1. `check-series-numbering.py` 的正则是 `^(?P<num>\d{4})(?P<suffix>[a-z]*)-…\.patch$`（该脚本 `:37-38`），**只认四位编号**；`zzz…-pong-touch-console.patch` 这类无编号条目根本不进它的计数。所以「134」与「240」不矛盾——是两个量，**引用时必须带「（M 带号 + K 无号）」才不会让下一个人对不上**。
2. `xnu-patches.list` 只存在于装配树（构建产物），本仓没有；所以「105 行」永远要写成「在装配树 `…/mondrian_ios27/` 内测得」。
3. 清单里唯一命中 `pong|touch|keys` 的是 `patches/xnu-12377/native-pac-keys.patch`——那是 **PAC 指针认证的 keys**，不是按键，别当输入线证据。

## 一、27 的装配层：差集在哪

`board.toml:369` 的四层是 `arch:patches/xnu/series`、`soc:patches/xnu-12377/series`、`os:patches/xnu/series`、`device:patches/xnu-12377/series`。其中带 `arch:`/`os:` 前缀的经 `scripts/unixnu/patches.py:12-22` 的 `resolve_path(ctx, reference, modules)` 解析到**profile/框架根**，不是本设备仓；本设备仓只贡献 `device:patches/xnu-12377/series`（28 条编号条目）。

实测（27 装配树 `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/`）：`xnu-patches.list` 105 行**全在 `patches/xnu-12377/`**，`patches/xnu/` 0 行；`tree/.cache/xnu-work` 里 `bsd/dev/pong_goodix.c`、`bsd/dev/pong_buttons.c`、`bsd/kern/pong_userland.c`、`iokit/Kernel/MiniIOMobileFramebuffer.cpp` **四个都 absent**，`pong_goodix_init`/`pong_buttons_init`/`pong_touch_post`/`pong_userland` 四个符号 grep **全 none**。

结论：触摸/按键驱动只存在于本仓 16 线的 `patches/xnu/series`（240 条非注释行，touch `:197`、keys `:198`），27 的装配路径不读这个文件。

## 二、`to-port` / `ported` 逐条三列

### A. `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`（`patches/xnu/series:197`）— **to-port**

| 列 | 内容 |
| --- | --- |
| **16 线验证证据** | `E:/k60-work/evidence/usblog-20261114-150931/console.log`：`:683` `goodix: COORD-ON ack=80`；`:687` `Pong touch: Berlin-D ready, SPI 0x990000 reset=20 irq=21 raw axes=14400x32000 transport=GPIO SPI`；8 行 `goodix: type=1 finger=…`（`grep -c` = 8）；4 行 `Pong touch HID: type=…`（`grep -c` = 4）；`:1425` `Pong touch HID: display-integrated digitizer opened`；同日志 `grep -ci springboard` = 253 行。核验方式：`grep -n 'COORD-ON\|Pong touch HID\|Berlin-D ready' usblog-20261114-150931/console.log` |
| **27 侧现状** | 补丁不在清单：`grep -c 'pong-touch' <build>/xnu-patches.list` = **0**；驱动文件 `bsd/dev/pong_goodix.c` **absent**；符号 `pong_goodix_init` **none**（`grep -rl pong_goodix_init <build>/tree/.cache/xnu-work` 空）；两个前置锚点也 absent：`bsd/kern/pong_userland.c`、`iokit/Kernel/MiniIOMobileFramebuffer.cpp` |
| **移植判据** | 解冻后第一次带输入的构建：`grep -c 'pong-touch-console' $BOARD_DIR/xnu-patches.list` ≥ 1 **且** 同一次启动日志出现 `goodix: COORD-ON ack=80` 与至少 1 行 `Pong touch HID: type=`（无串口时以 0546 控制台/画面为准，P-300） |

### B. `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch`（`:198`）— **to-port（依赖 A）**

| 列 | 内容 |
| --- | --- |
| **16 线验证证据** | `E:/k60-work/evidence/usblog-20261108-180257/console.log:229`：`Pong keys: arbiter v7 channels=768 PON=407 GPIO6=434; power=1 up=1 down=1`（同串在 `usblog-20261108-182056:235`、`192302:236`、`193525:236` 复现，共 4 次启动）。核验：`grep -rn 'Pong keys: arbiter' /e/k60-work/evidence/usblog-*/console.log` |
| **27 侧现状** | 补丁不在清单（`grep -c 'pong-physical-keys' …` = **0**）；`bsd/dev/pong_buttons.c` **absent**；`pong_buttons_init` **none**；依赖的先决条件同样不在：`bsd/sys/pong_input.h` absent。ADT 侧相反：六属性已在 `board.toml:284-299` 且 ADT 字节已验（`adt-27-buttons-check.md`） |
| **移植判据** | 同一次构建里 keys 补丁在 touch 之后应用（`git apply` rc=0）**且** 启动日志出现 `Pong keys: arbiter v%u … power=%u up=%u down=%u` 且 `power/up/down` 至少一个为 1（按住键的一次观测），另有一次 `ioreg -c IOHIDDevice -n "Offline HID input probe"` 有实例 |

### C. `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-goodix-resume.patch` — **ported（不再是独立补丁）**

| 列 | 内容 |
| --- | --- |
| **16 线验证证据** | **未找到**：`grep -rln 'did not resume\|brl_resume' /e/k60-work/evidence/*/console.log` = 0 命中，即没有一次 16.6.1 启动留下这条补丁的日志（它是在 `pong-touch-console` 内被合并进去的）。 |
| **27 侧现状（量出来的，不是「已并入」）** | 27 重放副本 `~/input27-fsyntax/xnu/bsd/dev/pong_goodix.c`（touch 补丁以 `--exclude bsd/conf/files --exclude iokit/…MFB.cpp` 应用后）：`:1287-1302` 实际内容是「注释 brl_resume → `touch_reset()`（:1289）→ `if (!goodix_probe(true))` 失败打印 `Pong touch: controller failed identification after resume reset` 并 `goto out` → `goodix_write(touch_address,&clear,1)` 失败打印 `Pong touch: cannot clear the resumed report status` 并 `goto out` → `goodix_apply_config(fw_buffer_address)` → 再 `goodix_probe(true)`，失败打印 `Pong touch: identification lost after config apply`」。与 16 线补丁（`k60-gates/patches/xnu/…-pong-goodix-resume.patch` 新增行 `:7-21`）的**差异三处**：① 16 版失败是 `thread_terminate(current_thread());return;`（杀线程），27 版是 `goto out`（让启动继续）；② 两条 printf 文本不同（`did not resume after reset; SKIP` ↔ `failed identification after resume reset`；`cannot acknowledge resumed report; SKIP` ↔ `cannot clear the resumed report status`）；③ 27 版多出 `goodix_apply_config()` + 第三次 `goodix_probe(true)`，16 版补丁没有这两步。命令：`sed -n '1280,1305p' ~/input27-fsyntax/xnu/bsd/dev/pong_goodix.c`、`grep -n '^+' …-pong-goodix-resume.patch` |
| **移植判据** | 27 上**不需要**再应用这条补丁：判据是重放后的 `pong_goodix.c` 里 `grep -c 'did not resume after reset'` 应为 0（已 0）且 `grep -c 'brl_resume'` 应为 1（已 1）；若将来有人把它当独立补丁再打一次，`git apply --check` 应失败（16 线补丁锚 `:878`，27 版已无该上下文） |

### D. `zzzzzzz-pong-hackios-userland-abi.patch`（`patches/xnu/series:54`）— **to-port，归用户态 ABI 线**

| 列 | 内容 |
| --- | --- |
| **16 线验证证据** | **未找到逐条证据**（它是 16 线的环境前置，不是某个输入行为；我能给的只有它在 16 系列里被应用、且 16.6.1 那次启动的 SpringBoard 253 行日志证明用户态确实起来——但这不能单独归因给它）。 |
| **27 侧现状** | 27 重放时它自己失败：`bsd/conf/files:383`、`libkern/conf/files:109` 上下文不匹配；它创建的 `bsd/kern/pong_userland.c` 在 27 树 absent |
| **移植判据** | 该线报「已移植」时，判据 = `git apply --check` 在带四层清单的树上 rc=0 **且** `grep -c 'bsd/kern/pong_userland.c' bsd/conf/files` = 1；在此之前本线继续按「阻塞」记账 |

### E. `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` — **to-port，归显示线**

| 列 | 内容 |
| --- | --- |
| **16 线验证证据** | **未找到逐条证据**（同上：它是显示/用户态前置） |
| **27 侧现状** | 该补丁以 `--- /dev/null` 手工造 `iokit/Kernel/MiniIOMobileFramebuffer.cpp`；27 树里该文件 absent，重放报 `iokit/conf/files:79`、`bsd/kern/bsd_init.c:1305`、`bsd/kern/kern_memorystatus.c:222` 三处失败 |
| **移植判据** | 显示线报「已移植」时，判据 = 27 树上 `test -f iokit/Kernel/MiniIOMobileFramebuffer.cpp` 为真 **且** touch 的 MFB hunk 能 `git apply --check` rc=0 |

### 附：`ARM64_BOARD_CONFIG_PONG` 守卫（Lead m01904 提醒的同族坑）

实测：`grep -c ARM64_BOARD_CONFIG_PONG` 在两个输入补丁里都是 **0**（`zzz…-pong-touch-console.patch`、`zzz…-pong-physical-keys.patch`），所以输入线**不存在**「原样打进去等于没打」的问题；27 源树里该宏只出现在 `build/armcpu/build-report.json`、`build/armdt-platform/build-report.json` 这类构建报告里，源码 0 处。这条对 `0300-k60-usblog-ep0.patch` 成立，对输入线不成立——但共享的 `bsd/kern/bsd_init.c` hunk 是要当心的：它与 `0300`/`k60_usblog_start()` 落在同一文件，谁先落谁定锚点。

## 三、`not-needed`（按要求不给证据，只留一句理由）

| 资产 | 理由 |
| --- | --- |
| 五个诊断补丁（bitbang / pad / reset / frame / miso-pull） | 纯 `printf` 探针，27 重放后的驱动里 `K60BB`/`K60PAD`/`K60RST` 全 0 命中；27 自己的诊断是 `pong_goodix.c:1001` 的 ack 打印与 `:1029` 的 `COORD-ON` |
| `…-pong-touch-spmi-probe.patch` | 它找 SPMI 表里 PPID `0x241`（sheng 的 PM8350C LDO2）给触摸供电；K60 触摸 AVDD 是 TLMM GPIO 71（`pong_goodix.c:61-65` 断言、`board.toml:265` `avdd-gpio = 71`），16.6.1 的真因也不是电源 |
| `userland/touch.c`（16 的注入桥） | 27 内核 feed 无 virtual-service 客户端 API、无 `IOHIDEventCreate*` 工厂，载体换到内核 `IOHIDDevice` 子类（`docs/research/ios27/touch-contract-diff-27.md` 二栏） |

## 四、给 Lead 的登记建议（我不动清单）

1. A `to-port`（前置：D/E 两条）
2. B `to-port`（依赖 A）
3. C `ported`（判据是「不要再打一次」，且 27 版与 16 版有三处行为差异）
4. `not-needed` 三类可合并成一行

另：`xnu-patches.list` 105 条全在 `patches/xnu-12377/`、`patches/xnu/` 0 条，这个「0」本身就是最省事的量化口径。

## 五、keys 的 `bsd_init.c` 锚点 vs `0547`（usblog EP0）：量出来的三个数

测量方法（全部在 27 装配树内；两份副本 `rsync -a` 到 `~/input27-anchor/a`、`/b`，脚本 `E:/k60-work/scratch/input27/anchor-test.sh`）：

- 源 = `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work`（HEAD `ac9718f`「xnu-12377.121.6」，soc 层是未提交改动）
- 补丁 = `patches/xnu/zzz…-pong-touch-console.patch`、`patches/xnu/zzz…-pong-physical-keys.patch`、`patches/xnu-12377/0547-k60-usblog-ep0-27.patch`
- 手法 = `git apply`；touch 带 `--exclude iokit/Kernel/MiniIOMobileFramebuffer.cpp --exclude bsd/conf/files`，keys 带 `--exclude bsd/conf/files`（这两条路径的前置不在输入线手里，见上文 D/E）

### 三个数

| 量 | 值 | 怎么量的 |
| --- | --- | --- |
| keys 的 hunk 落在哪 | `@@ -1153,6 +1153,8 @@` → 落进 touch 新建的 `#if defined(PONG)` 块：块体 `:1175-1180`，**新增两行在 `:1178-1179`**（`extern void pong_buttons_init(void);` / `pong_buttons_init();`） | 副本 a 应用 touch→keys 后 `nl -ba bsd/kern/bsd_init.c` |
| `0547` 的插入点落在哪 | `@@ -1334,7 +1334,11 @@` → 在 `qbt_k60_start();`（`:1349`）之后，**新增四行在 `:1350-1353`**，位于 `if (result == KERN_SUCCESS) {`（`:1347-1350`）块内 | 同副本上 `git apply --check --verbose 0547` 报 `Hunk #1 succeeded at 1346 (offset 12 lines)` |
| 两者相隔多少 | **171 行**（keys 最后一行 `:1179` → 0547 第一行 `:1350`）；两个 hunk 的上下文窗口（`:1175-1180` 共 6 行 / `:1346-1356`）之间**至少 165 行未触碰** | 同上，逐行数 |

### 两种落地顺序都实测过

| 顺序 | 结果 |
| --- | --- |
| 装配树 → touch → keys → 0547 | 三步全 `rc=0`；0547 以 `offset 12 lines` 落位 |
| 装配树 → 0547 → touch → keys | 三步全 `rc=0`；末态 `pong_buttons_init();` `:1179`、`qbt_k60_start();` `:1349`、`k60_usblog_start();` `:1353`，文件 1832 行 |

### 判断：不要在 keys 的 hunk 里补「先落 0547」的后置条件

1. 两处上下文不重叠（相隔 171 行，`git apply` 只读 3 行上下文），落地顺序自由，补条件没有收益。
2. 把 keys 的锚点改成「`k60_usblog_start();` 之后的稳定行」是**有害**的：那四行在 `bsd_autoconf()` 的 `if (result == KERN_SUCCESS)` 块尾，而 keys 现在落在 `#endif /* DEVFS */` 之后的 `#if defined(PONG)` 块（`bsd_init` 早期）；挪过去等于把按键初始化推到 `bsd_autoconf()` 末尾，时序变了。
3. 更糟的是**依赖反转**：改成那样以后，keys 就变成「必须在 0547 之后才能 apply」，而 0547 是新落、还可能被重打的补丁。

### 一行结论

**keys 与 `0547` 互不影响**（插入点相隔 171 行、上下文窗口不重叠，两种落地顺序实测全 `rc=0`）；keys 的硬前置只有 **touch**（它的 hunk 锚在 touch 新建的 `#if defined(PONG)` 块内），**不要**把 keys 重锚到 `k60_usblog_start();` 之后。
