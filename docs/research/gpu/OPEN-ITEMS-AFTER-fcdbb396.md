# GPU metal — open items after `fcdbb396`

State: `fcdbb396 fix(gpu): publish the metal seeds only after the bundle is complete`
already reorders the seeds to `Info.plist → .clients → .publish` and is covered by
`scripts/tests/test-metal-seed-order.py` (3 cases).

Remaining before the next flight (no boot until all three are closed and the image is rebuilt):

## 1. Atomic seed write — `drivers/PongMetal/seeds/k60_metal_seeds.c:43-56`

Now `vnode_open(path, O_CREAT | O_WRONLY | O_TRUNC, ...)`: a crash mid-write leaves a
half `.clients`, and `selectedClient()` then silently returns false.

Copy the durability pattern recorded in
`E:/k60-work/research/sm8475/nagatoquin33-diting/AGENTS.md:1202`
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

Reference: `E:/k60-work/scratch/METAL-INJECT-PARITY.md` §7 (copy list) and
`E:/k60-work/scratch/EXEC-INJECT-SEMANTICS.md` (exec_inject is not the mechanism; the
per-exec read happens long before backboardd execs).
