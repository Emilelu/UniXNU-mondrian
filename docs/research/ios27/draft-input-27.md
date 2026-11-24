# 27 线触摸 / 按键补丁草案（0001 / 0002）

日期：2026-11-24　分支：`feat/input-27`　状态：草案，未进任何 series，未构建

## 一句话结论

16.6.1 的 touch / keys 两个补丁在 27 装配树上的三个断点全部改锚后，草案 0001、0002 按顺序 `git apply` 均 rc=0，产物为 1,375 + 171 + 107 + 24 行的四个文件与两处 `bsd_init.c` 调用点；唯一没进草案的是 `iokit/Kernel/MiniIOMobileFramebuffer.cpp` 那一段——27 树上该文件不存在，归显示线创建。

## 三个断点与改锚

| # | 16 线锚点 | 27 树事实 | 草案改法 |
| --- | --- | --- | --- |
| 1 | `bsd/conf/files:385` 起，上下文含 `bsd/kern/pong_userland.c`（该行由 userland-abi 前置补丁创建） | 27 树 `bsd/conf/files` 637 行里没有任何 `pong_*` 行，`:385` 是 `bsd/security/audit/audit_session.c` | 改成文件尾部追加：`bsd/dev/k60_adreno_grant.cpp`（27 树 `:637`）之后追加 `bsd/dev/pong_input.c`、`bsd/dev/pong_goodix.c`（0001）与 `bsd/dev/pong_buttons.c`（0002） |
| 2 | `bsd/kern/bsd_init.c` 的 touch 块 `@@ -1147,6 +1147,16 @@`，后面跟着 `#endif /* DEVFS */` | 27 树同段在 `:1162-1169`（`#if DEVFS` … `#endif /* DEVFS */`），行号整体 +15 | 由 `git diff` 重新生成，落点 `:1169-1181`，上下文与 27 树逐字一致 |
| 3 | keys 的 `bsd_init.c` 块 `@@ -1153,6 +1153,8 @@`，嵌在 touch 新建的 `#if defined(PONG)` 块里 | 27 树上该块不存在，必须 0001 先落 | 0002 依赖 0001，顺序 apply；缩进统一为单 tab |

另：16 线 touch 补丁里 `iokit/Kernel/MiniIOMobileFramebuffer.cpp` 的 hunk（`:1533` 起）**未进草案**——27 装配树 `tree/.cache/xnu-work` 没有这个文件（`find` 0 命中），它由 `zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 以 `--- /dev/null` 形式创建、归显示线。触摸控制台首帧那一步必须在显示线落 MFB 之后单独接。

## 草案文件

| 文件 | 行数 | 内容 |
| --- | --- | --- |
| `patches/input27-drafts/0001-input27-pong-touch.patch` | 1,529 | 新建 `bsd/dev/pong_goodix.c`（1,375 行）、`bsd/dev/pong_input.c`（107 行，含队列）、`bsd/sys/pong_input.h`（24 行）；`bsd/kern/bsd_init.c` 加 PONG 定义 + `pong_goodix_init()`；`bsd/conf/files` 尾部两行 |
| `patches/input27-drafts/0002-input27-pong-buttons.patch` | 345 | 新建 `bsd/dev/pong_buttons.c`（171 行）；`bsd/dev/pong_input.c` 拆出按键队列（107 行）；`bsd/sys/pong_input.h` 加 `PONG_BUTTON_*`；`bsd_init.c` 加 `pong_buttons_init()`；`bsd/conf/files` 尾部一行 |

两份都是从 16 线原补丁（`E:/hackios/k60-gates/patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`、`…z-pong-physical-keys.patch`）在同一棵 27 树上 apply 后用 `git diff` 重新生成的，因此**代码内容与 16 线逐字一致**，只有锚点与顺序是 27 侧事实。

## 复现与验证

```sh
# 27 装配树（只读源）
T=/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work
rsync -a "$T"/ /tmp/v/xnu/ && cd /tmp/v/xnu && git init -q && git add -A && git commit -qm base
git apply --check patches/input27-drafts/0001-input27-pong-touch.patch   # rc=0
git apply          patches/input27-drafts/0001-input27-pong-touch.patch
git apply --check patches/input27-drafts/0002-input27-pong-buttons.patch # rc=0
git apply          patches/input27-drafts/0002-input27-pong-buttons.patch
```

实测（2026-11-24，`$HOME/input27-draft-verify`）：0001 `git apply --check` 五个文件全过、apply rc=0；0002 在 0001 之上 check/apply 均 rc=0。落点核验：`bsd_init.c:1176-1179` 为 `extern void pong_goodix_init(void);` / `pong_goodix_init();` / `extern void pong_buttons_init(void);` / `pong_buttons_init();` 四行（extern 与调用各一行，单 tab 缩进），`:1181 #endif /* DEVFS */` 未动；`bsd/conf/files` 尾部 6 行 = `k60_console_export.c`、`k60_usblog_reset.c`、`k60_adreno_grant.cpp`、`pong_input.c`、`pong_goodix.c`、`pong_buttons.c`。四个文件行数 1375 / 171 / 107 / 24 与 16 线一致。

唯一警告：`0001` 应用时 `git apply` 报 `new blank line at EOF`（`pong_goodix.c` 末行空行，16 线原文件就是这样），不影响 `--check` 与编译。

## 与既有资产的关系

- **不再需要 userland-abi 前置补丁**（原 16 线 `bsd/conf/files` hunk 依赖它创建 `bsd/kern/pong_userland.c` 行）：改为尾部追加后，input 线的 conf 注册自足。
- **仍需要显示线的 MFB**：只有 `PE_initialize_console(NULL, kPEReleaseScreen)` 那一步（16 线 touch 补丁 `:1533`），与驱动本体无关。
- **SPI 空指针守卫与 333 kHz 时序**：原样保留在 `pong_goodix.c` 内（`spi_transfer_unset()` 默认值、`bb_delay_us = 2`、`divisor` 计算），草案未改一行——见 `docs/research/ios27/touch-contract-diff-27.md` 五、既有资产。
- **0547 顺序**：`pong_buttons_init()` 落 `:1179`，0547 的 `k60_usblog_start()` 落 `:1350-1353`，相隔 171 行，两者互不影响（见 `carry-over-input-27.md` 五）。

## 下一步判据

1. 显示线交付 `MiniIOMobileFramebuffer.cpp` 后，把 16 线 touch 补丁的 MFB hunk 单独接进 27 线（判据：`iokit/conf/files` 有 `MiniIOMobileFramebuffer.cpp` 行、`PE_initialize_console` 调用点编译通过）。
2. 解冻后用四层清单构建，`pong_goodix_init` / `pong_buttons_init` 出现在 `llvm-nm` 的 defined 符号里（判据：两个符号 + `pong_touch_post`、`pong_touch_device_ready`）。
3. 上机首条判据：`goodix: COORD-ON ack=80` 与 `Pong keys: arbiter v7 … power=1 up=1 down=1` 同一次启动日志内出现（16 线证据 `usblog-20261114-150931/console.log:683`、`usblog-20261108-180257/console.log:229`）。
