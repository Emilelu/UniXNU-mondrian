# 给 Lead 的序列建议（27 侧不要收录 goodix 家族 7 条补丁）

日期 2026-11-21 · 输入线（input27）· 只作建议，gates 与 xnekom-ios27 的 series 由 Lead 改

## 一句话结论

27 侧 `patches/xnu/series` 保持现状（只 :197 touch-console、:198 physical-keys），**不要**把 goodix 家族 7 条加进去；
其中 `zzzz…-pong-goodix-resume.patch` 若被加进任何一条会真正执行 `git apply` 的链路，会在 `bsd/dev/pong_goodix.c:878` 硬失败并把整条链拖死。

## 两条链路要分开说（这决定了「排除」写在哪里）

| 链路 | 顺序/清单来源 | 排除写在哪里才有效 |
| --- | --- | --- |
| 27 线：`unixnu build kernel` | `board.toml` 的 `patch_series` 四层（`scripts/unixnu/patches.py:12-30` 逐条解析，`:56-62` 逐条 `git apply`，任一失败即删 `.cache/xnu-work` 并报错） | 写进 `xnekom-ios27/patches/xnu/series`：不在清单里就不会应用。**当前 240 行的 series 本来就没有这 7 条 → 现状已是排除状态** |
| gates 线：`k60-gates/scripts/build-xnu-generic.sh` | `patches/xnu/*.patch` 的 glob 字典序（`:58-63`，`git apply --check` + `git apply`，无 fuzz；默认 `XNU_TAG` 见 `:16-17`） | 只能靠文件不在该目录、或改名/移出。**改 series 对这个脚本无效** |

结论：建议本身是「维持 27 series 现状 + 不要把这 7 条补进 27」，而不是「去 series 里删东西」；gates 侧只在有人想把 glob 链路指向 27 树时才需要动文件。

## 7 条补丁各自的排除理由（glob 序号 / 276）

参考序号：touch 247、k60-panic-report 248、keys 249、k60-cpp-void-ptr-assert 250，以下 7 条都排在 touch/keys 之后。

| 序号 | 补丁 | 结论 | 理由（附 27 侧证据） |
| --- | --- | --- | --- |
| 251 | `zzzz…-pong-goodix-resume.patch` | 已并入，必须排除 | 它要插的「重置 + 重新识别 + 清报告位」已在 touch-console 本体：27 应用后 `pong_goodix.c:1287-1298`（brl_resume 注释 + `touch_reset()` + `goodix_probe(true)` + clear + `goodix_apply_config`）；单独 `git apply` 在 27 上 `error: patch failed: bsd/dev/pong_goodix.c:878`（它假定的是没有这段折叠代码的旧文件） |
| 252 | `…-pong-touch-bitbang-probe.patch` | 不需要 | 纯诊断 printf（K60BB 初始化标记）；标记串在 27 应用后的 `pong_goodix.c` grep = 0；27 自己的通道诊断是 `:1001` 的 `goodix: %s ack=%02x` 与 `:1029` 的 `COORD-ON` |
| 253 | `…-pong-touch-pad-level.patch` | 不需要 | 纯诊断 printf（K60PAD cs/miso/clk/mosi/rst 电平），0 命中 |
| 254 | `…-pong-touch-reset-level.patch` | 不需要 | 纯诊断 printf（K60RST pin/沿），0 命中 |
| 257 | `…-pong-touch-frame-probe.patch` | 不需要 | 纯诊断 printf（帧长/rx0/rx1 计数），0 命中 |
| 259 | `…-pong-touch-miso-pull.patch` | 不需要 | 纯诊断 printf + MISO 下拉试验，用来分辨悬空/被驱动；16 线已答完，0 命中 |
| 260 | `…-pong-touch-spmi-probe.patch` | 不需要 | 它找 SPMI map 表里的 PPID 0x241（sheng 的 PM8350C LDO2）；K60 触摸 AVDD 是 TLMM GPIO 71：`pong_goodix.c:61-65` 断言 `avdd_gpio==71`、`:103`/`:130` 映射 TLMM bank6、`:180` `gpio_output(avdd_gpio,…)`，27 仓储 `board.toml:265` 同为 `avdd-gpio = 71`，且 16.6.1 的真因是坐标使能不是供电 |

## 我在台账里记了什么

`docs/research/eight-step/input-27.toml` 的 touch ⑥deep：判定表逐条（含 27 侧行号）、glob 实测序号、
「输入层 0 冲突、整链阻塞在前置层」的记账（含两条前置补丁的失败锚与所有者）。
