# 启动参数对账：47 个 sheng-only 键里只有 6 个有读取者

`docs/research/ios27/BOARD-PARITY.md` 列出了「sheng 传了、我们没传」的 47 个键。
那是集合差，不是缺口清单——一个键如果没有代码读它，抄过来只是占掉 607 字节启动行。
本页回答第二个问题：**我们的内核读不读它**。

工具：`scripts/audit-boot-args.py --ours . --theirs <参考仓> --profile ios-27.0.1-24A446 --tree <装配树>`
（只读；扫描 `*.c/.cc/.cpp/.h/.hpp/.m/.mm` 里的 `PE_parse_boot_argn("…")`）。

## 1. sheng 有、我们没有的 47 个键

汇总：**reader 6 / mention 0 / absent 41**。

| 判定 | 键 | 第一个读取点 |
|---|---|---|
| reader | `offline-legacy-register` | `bsd/kern/bsd_init.c:556` |
| reader | `offline-mobile-graphics-client` | `bsd/kern/bsd_init.c:563` |
| reader | `offline-mobile-graphics-load` | `bsd/kern/bsd_init.c:548` |
| reader | `serial` | `osfmk/arm/arm_init.c:745` |
| reader | `sheng-gpu-addon` | `bsd/kern/kern_exec.c:8647` |
| reader | `sheng-no-lc` | `security/mac_process.c:922` |
| absent | `appsync`, `armcpu-self-ipi`, `armcpu-spi-ipi`, `native-source-storage`, `native-ufs-root`, `offline-hid-home`, `offline-hid-input`, `offline-key-events`, `offline-legacy-cpu-present`, `offline-legacy-gop`, `offline-legacy-phase`, `offline-legacy-pm`, `offline-legacy-transfer`, `offline-legacy-unit-scale`, `offline-legacy-validate`, `sheng-adsp`, `sheng-aks`, `sheng-aks-sls`, `sheng-audio`, `sheng-backlight`, …（共 41 个） | - |

41 个 `absent` 不是遗漏：它们由我们**没有 include 的组件**读取——
`offline-legacy-*` 属于 `GopFramebuffer`/`NativeLegacyDisplay`（`build-gop-legacy-display-27.py`），
`native-ufs-root`/`native-source-storage` 属于 `ShengUfs`，`sheng-aks*` 属于 `AppleKeyStoreState`。
组件不在树里，键就没有读者；先抄键不会让任何东西动起来。

6 个 `reader` 里，`offline-legacy-*` 三个在我们树里的读取点来自已移植的 `bsd_init.c` 片段，
默认关闭（不传即 0），`sheng-gpu-addon`/`sheng-no-lc` 同理。**结论：除非先把对应组件搬进来，
这 47 个键一个都不该抄。**

## 2. 我们有、sheng 没有的 5 个键（全部有读者）

| 判定 | 键 | 读取点 |
|---|---|---|
| reader | `-enable_kprintf_spam` | `pexpert/arm/pe_kprintf.c:54` |
| reader | `-ukedeferredconsole` | `osfmk/console/serial_console.c:555` |
| reader | `-uketextconsole` | `osfmk/console/video_console.c:3202` |
| reader | `k60_fontscale` | `osfmk/console/video_console.c:2838` |
| mention | `amfi_get_out_of_my_way` | `bsd/kern/kern_codesigning.c:254`（非 `PE_parse_boot_argn`，需另核） |

这三条控制台开关就是 27 内核能打字的全部原因：`-uketextconsole` 打开视频控制台、
`-ukedeferredconsole` 推迟串口控制台、`-enable_kprintf_spam` 是 DEVELOPMENT 构建里唯一
把 `disable_kprintf_output` 置 0 的路径（P-308）。

## 3. 对移植的含义

1. 启动行只剩 607 字节，按「键数」对齐是错的；按「读者」对齐才对。
2. `BOARD-PARITY.md` §3 的 47 条从「候选清单」降级为「组件搬来之前的噪声」。
3. 真正要搬的是组件（`GopFramebuffer`、`ShengUfs`、`AppleKeyStoreState`…），
   它们各自带自己的参数；等组件落地时再用同一脚本重扫一次，读者会从 `absent` 变成 `reader`。

## 4. 复现

```bash
python3 scripts/audit-boot-args.py \
  --ours . --theirs /mnt/e/iOS Port/Sources/Repos/UniXNU/UniXNU-sheng \
  --profile ios-27.0.1-24A446 \
  --tree /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work
```

输出 `ARGS candidates=47 reader=6 mention=0 absent=41`。
反向（我们的键对 sheng）输出 `candidates=5 reader=4 mention=1 absent=0`。
