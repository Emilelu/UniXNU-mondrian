# 输入线（触摸 / 实体按键）的 16 线资产与 27 现状

日期：2026-11-22
对应：Lead m01829 第三条（27 系列只有 34 条、只有 3 条是搬过来的），以及 `docs/research/ios27/CARRY-OVER-INVENTORY.md` 的纪律 1（新增内核能力前先查 16 线）。
本文件只交**输入线**的表，供 Lead 登记进 CARRY-OVER-INVENTORY.md；我不改那份清单。

## 一、27 的装配层里到底有没有输入线

`board.toml:369`（27 设备仓）写死四层：

```
patch_series = ["arch:patches/xnu/series", "soc:patches/xnu-12377/series",
                "os:patches/xnu/series", "device:patches/xnu-12377/series"]
```

对照本仓文件系统：

| 层 | 目录 | 条目数（非注释行） | 含 touch/keys 补丁吗 |
| --- | --- | --- | --- |
| device 层 | `patches/xnu-12377/series` | 30 | **不含**（只有 `ptrauth-string-discriminator`、`armcpu-sleep-hook`、`0500/0501/0502b` BT 族等） |
| 16 线系列 | `patches/xnu/series` | 240 | 含：`zzz…-pong-touch-console.patch`（:197）、`zzz…-pong-physical-keys.patch`（:198） |

结论（机器可核）：**27 的装配层里没有任何一层指向 `patches/xnu/series`**，触摸/按键驱动补丁只存在于 16 线那 240 条里。所以「27 上没有触摸/按键驱动」不是印象，是 `board.toml:369` 与两个 series 文件的差集。（顺带一条与清单的差异：清单写 27 系列 34 条，本仓 HEAD 上数到 30 条非注释行——以 Lead 的口径为准，我不改数。）

## 二、16 线输入资产逐条

| 16 线资产（位置） | 作用 | 27 现状 | 处置 | 依据 |
| --- | --- | --- | --- | --- |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`（`patches/xnu/series:197`，63,484 B，6 个路径） | Goodix BERLIN-D 全驱动 + `/dev/pong-touch` 环形队列 + `pong_touch.h` + `bsd_init` 调用 + MFB 控制台 hunk | 未在 27 层；重放实验：9 个声明路径里 6 个 0 冲突，3 个卡在前置补丁 | **to-port** | `docs/research/ios27/replay-evidence` 对应条目；`adt-27-buttons-check.md` 同批 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-physical-keys.patch`（`:198`，13,668 B） | PMIC arbiter v7 三键采样，`pong_buttons.c` | 同上；单独 `git apply` 报 `bsd/sys/pong_input.h: No such file`（依赖 touch 先落） | **to-port（依赖上一条）** | 27 侧重放记录（touch 之后 rc=0） |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-goodix-resume.patch` | 探测成功后 `touch_reset()` + 重新 `goodix_probe(true)` + 清屏 | 逻辑已在 touch-console 内（27-applied `bsd/dev/pong_goodix.c:1287-1298`） | **ported（不需要单独重放）** | 单独重放报 `patch failed: bsd/dev/pong_goodix.c:878` |
| 五个诊断补丁：`…-touch-bitbang-probe` / `-touch-pad-level` / `-touch-reset-level` / `-touch-frame-probe` / `-touch-miso-pull` | 纯 `printf` 探针（`K60BB`/`K60PAD`/`K60RST`） | 27 重放后的驱动里这些标记 0 命中 | **not-needed** | 26 侧 `pong_goodix.c:1001`/`:1029` 已是官方式诊断 |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-spmi-probe.patch` | 找 SPMI 表里 PPID `0x241`（sheng 的 PM8350C LDO2）给触摸供电 | K60 触摸 AVDD 是 TLMM GPIO 71（`pong_goodix.c:61-65` 断言 `avdd_gpio==71`） | **not-needed** | 27 仓 `board.toml:265` `avdd-gpio = 71` |
| `zzzzzzz-pong-hackios-userland-abi.patch`（`patches/xnu/series:54`） | 创建 `bsd/kern/pong_userland.c`，是 touch 的 `bsd/conf/files` hunk 的锚 | 27 上自己就失败（`bsd/conf/files:383`、`libkern/conf/files:109`） | **to-port，归用户态 ABI 线** | `docs/research/ios27/handoff-prerequisites-27.md` |
| `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` | 以 `--- /dev/null` 手工造 `iokit/Kernel/MiniIOMobileFramebuffer.cpp` | 27 feed 里没有该文件；该补丁自身在 27 上失败（`iokit/conf/files:79` 等三处） | **to-port，归显示线** | 同上 |
| `userland/touch.c`（427 行，跑在 backboardd 里） | 16 的注入桥：字符设备 → 虚拟 HID 服务 → 数字转换器/键盘事件 | 27 内核 feed 里没有 virtual-service 客户端 API，也没有 `IOHIDEventCreate*` 工厂 | **not-needed（载体换侧）** | `docs/research/ios27/touch-contract-diff-27.md` 二、载体 |
| `0214-k60-console-font-scale.patch`（同族先例） | 面板控制台字号/几何 | 27 已有对应物，且上游刚 cherry-pick 过（`5023708a` → `8b70cab4`） | **ported** | Lead m01330；`patches/xnu-12377/k60-console-font-scale.patch` |

## 三、这条清单为什么要先查

今晚两次重造轮子（ramoops 控制台、自动复位）都发生在「没查 16 线就先写」之后。输入线的同类风险很具体：

- 我要写的 `/dev/pong-touch` 与环形队列在 16 线已经有 88 行成品（`bsd/dev/pong_input.c`），27 上**不需要重新设计**；
- 触摸「配置完成要等 `reply[0]==0x80`」与「`0x91/0x01` 开坐标」是 16.6.1 上机换来的真因（补丁 `:1031-1032`、`:1046-1048`），27 上重放即得，不要「重新发现」；
- 按键的「DT 六属性缺一个就 SKIP」在 16 线已经用日志验证过（`Pong keys: DT node … not found`），27 的 `board.toml:284-299` 已补齐。

## 四、给 Lead 的登记建议（我不动清单）

在 `CARRY-OVER-INVENTORY.md` 补三行即可覆盖输入线：

1. `zzz…-pong-touch-console` → `to-port`（前置：用户态 ABI + 显示 MFB 两补丁）
2. `zzz…-pong-physical-keys` → `to-port`（依赖上一条）
3. 五个诊断 + spmi-probe → `not-needed`（只在 16 的排障期有意义）

另：`patches/xnu/series` 有 240 条而 27 只引用 30 条的 device 层，这个差集本身就是「迁移丢资产」的量化口径，可直接作为清单表格的一行。
