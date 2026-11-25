# GPU metal — open items after `fcdbb396`

State: `fcdbb396 fix(gpu): publish the metal seeds only after the bundle is complete`
already reorders the seeds to `Info.plist → .clients → .publish` and is covered by
`scripts/tests/test-metal-seed-order.py` (3 cases).

Remaining before the next flight (no boot until all three are closed and the image is rebuilt):

## 1. Atomic seed write — `drivers/PongMetal/seeds/k60_metal_seeds.c:43-56`

Now `vnode_open(path, O_CREAT | O_WRONLY | O_TRUNC, ...)`: a crash mid-write leaves a
half `.clients`, and `selectedClient()` then silently returns false.

Copy the durability pattern recorded in
`E:/iOS Port/Work/research/sm8475/nagatoquin33-diting/AGENTS.md:1202`
(`zzzzzzzzzzzzzzzzzz-diting-gpu-addon-durability.patch`):
write `<path>.k60seed-tmp` → `vn_rdwr(..., IO_SYNC)` → `vnode_close` → `vnode_rename`
to the final name.

## 2. Bounded root wait before publishing IOAcceleratorES — `drivers/PongAdreno/PongAdrenoNativeGlue.cpp:53-56`

Publishing immediately stalls APFS / IOFindBSDRoot when the root volume is not mounted yet.

Copy `qiumochen-zizhan/drivers/PongAdreno/PongAdrenoNativeGlue.cpp:15-28,172`
(rootvnode bounded wait, 3000 × 100 ms) before the publish call.

## 3. Boot-progress telemetry — `drivers/PongAdreno/submit/NativeAdrenoPublish.cpp:36,107,737-745`

`name_reads` / `name_reader` are already collected but never printed, so a flight cannot
tell whether backboardd ever read `MetalPluginName`.

Copy the `M ... n%u` / `S...<P|F><macf>` line from
`takasugl-udon/package/GpuPowerProbe.cpp:1256-1290`.

## Flight criteria for the next image (write the card before building)

- `name_reads` mentions `backboardd`;
- `real Vulkan-backed device created` is not attributed to `adrenoprobed` (the official
  addon shadows `com.apple.bluetoothd` with that probe — its log line is a false positive);
- `first frame presented` >= 1;
- `crashed: backboardd` == 0.

Reference: `E:/iOS Port/Work/scratch/METAL-INJECT-PARITY.md` §7 (copy list) and
`E:/iOS Port/Work/scratch/EXEC-INJECT-SEMANTICS.md` (exec_inject is not the mechanism; the
per-exec read happens long before backboardd execs).

## 2026-11-18 判定：第 1 项（temp+rename）不必要，理由与证据

同一张 `gpu-mini-20261118` 连飞两次得到不同结果（`usblog-20261118-014232` 首帧成立、
`usblog-20261118-101832` 设备已建但 0 帧、`MiniIOSurface` 1 而非 2），镜像/内核/插件/命令行逐字节相同，
说明不确定性来自启动早期 seed 与 backboardd 首次读取的先后，而不是写入的字节完整性。

`selectedClient()` 的门是 `.publish` 首字符为 `'1'`；`fcdbb396` 把 `.publish` 放到最后写，
`8035d3df` 让任一步失败都不写 `.publish`，因此「publish 可见时 bundle 与 clients 已完整」已经成立。
`.publish` 内容只有 2 字节的单次 write，不存在部分可见。

第三项改动（temp + `IO_SYNC` + `vnode_rename`）需要 `vnode_rename` 原型，而本仓库树里没有该声明
（`grep -rn vnode_rename --include=*.h .` 零命中，XNU 源只在构建期展开），在无法核对签名的情况下
不引入猜测实现。若后续确实需要 durability，先确认 XNU 版本里 `vnode_rename` 的签名与 flags 再动手。

结论：第 1 项关闭（不实现），第 2 项 rootvnode 有界等待与第 3 项 `name_reads` 遥测保留。
