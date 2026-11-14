# GPU 部署链研究：增量事实

> 适用范围：K60（mondrian / SM8475）iOS 16.6.1 内核，2026-11-14。
> 本文只记录 `k60_metal_mkdir` 的 mkdir 修复、旧普通文件的 unlink 自愈、P-196 容器长度修复**之外**的新事实；上述三项已合并进 main，本文不复述其实现。
> 日志行号均为 `/mnt/e/k60-work/evidence/<usblog>/console.log` 的行号。本文不含新的构建或上机动作。

## 1. 真机日志：部署失败不会改变 prepare 的返回状态

### 1.1 usblog-20261114-150931（旧 0610，deploy 0/6）

- :375 `K60DATA attempt enter`
- :455 `K60DATA mount returned error=0 result=0 rw=1`
- :479 `K60UILIB deploy bytes=113904 resid=0 error=0`
- :480 `K60METAL open /private/var/ngpu/addons/PongAdrenoMetal.bundle/Info.plist error=20`
- :481 `K60METAL deploy files=0/6 error=20`
- :482 `K60DATA root lookup error=0 vnode=0xfffffff48fa7b4c0`
- :483 `K60DATA mounted ro=0 fstype=apfs`
- :484 `K60DATA mkdir ok=1/36 [... ngpu=17 ngpu/addons=17 ngpu/daemons=17 ...]`
- :486 `K60DATA launchd policy err=0`
- :488 `K60DATA attempt returned error=0 stage=4 device=900000a`
- :602 `PONG ADRENO: startup begin`（其后 22 个阶段均 `result=0 a=0x0 b=0x0`）
- :644 `PONG ADRENO: startup COMPLETE; hardware armed result=0 a=0x40000007 b=0x20010000`
- :1106 `Pong UI: installed software-only camera filter prewarm policy`
- :1665 `Pong UI: optional camera-filter GPU prewarm skipped (software-only platform)`

### 1.2 usblog-20261114-212253（旧 0610，deploy 0/6）

- :371 `K60DATA attempt enter`
- :451 `K60DATA mount returned error=0 result=0 rw=1`
- :476 `K60METAL open /private/var/ngpu/addons/PongAdrenoMetal.bundle/Info.plist error=20`
- :477 `K60METAL deploy files=0/6 error=20`
- :486 `K60DATA attempt returned error=0 stage=4 device=900000a`

### 1.3 usblog-20261114-215159（unlink 版 + P-196 修复前）

- :374 `K60DATA attempt enter`
- :454 `K60DATA mount returned error=0 result=0 rw=1`
- :479 `K60METAL removed a stale file at /private/var/ngpu/addons/PongAdrenoMetal.bundle`
- :480 `K60METAL entry 5 body out of range`
- :481 `K60METAL deploy files=5/6 error=22`
- :490 `K60DATA attempt returned error=0 stage=4 device=900000a`

### 1.4 读法

1. **deploy 的返回值被丢弃。** `patches/xnu/0610-k60-metal-plugin-deploy.patch:252` 是 `(void)k60_metal_deploy(p, scratch);`，所以 deploy 报 0/6 或 5/6 时，`native_owner_data_prepare` 仍然打印 `K60DATA attempt returned error=0 stage=4 device=900000a`（150931:488、212253:486、215159:490）。**`stage=4`/`error=0` 不能作为部署成功的判据，只能看 `K60METAL` 行本身。**
2. `K60METAL removed a stale file at /private/var/ngpu/addons/PongAdrenoMetal.bundle`（215159:479）是 unlink 自愈第一次在真机触发：说明此前某次旧部署确实在该路径留下了一个普通文件。若后续启动反复出现这一行，说明每次部署又在重建同一个普通文件，应优先查 deploy 的 mkdir 路径而不是重启。
3. `K60DATA mkdir ok=1/36 [... ngpu=17 ngpu/addons=17 ngpu/daemons=17 ...]`（150931:484）里的 `ngpu`、`ngpu/addons`、`ngpu/daemons` 三个 17（EEXIST）不是 0398 循环自己造成的：`k60_metal_deploy` 的四次固定 mkdir 在同一个 prepare 里更早执行（0610 的 kern_exec hunk 在 `:237-252`，位于 0398 的 `k60_mkdir_paths` 循环之前）。ok=1 是这次确实新建的那一个目录。
4. 三次采集里 Data 卷都在 deploy 之前挂载成功（`K60DATA mount returned error=0 result=0 rw=1`），且同一日志里 Adreno 22 个启动阶段仍全部 result=0（150931:644 `startup COMPLETE`）。部署失败没有破坏 GPU 硬件 bring-up，它是用户态 Metal 之前的最后一层。

## 2. 构建链：main 上尚未记录的几处

### 2.1 build-strict 的 P-196 门禁读取未定义的 ROOT

- `origin/main:scripts/build-strict.sh:255-256` 的 P-196 容器门禁引用 `$ROOT/.cache/xnu-work/...`，但整个脚本没有给 `ROOT` 赋值（`git show origin/main:scripts/build-strict.sh | grep ROOT` 只有这两行）。
- 脚本启用了 `set -u`，因此每次 strict build 都会在写完 boot.img 之后以 `ROOT: unbound variable` 退出；镜像已经生成，但构建被判失败，后续所有校验也不会执行。
- `feat/gpu-user` 的 `e17efd8` 在 `scripts/build-strict.sh:73` 增加 `ROOT=$M/tree`（门禁现在位于 `:260-262`）。在 main 合入等效修复前，从 main 构建必须带这一行，否则 100% 在最后一步失败。

### 2.2 全新的 K60_OUT 必须先产生 .config

- `scripts/build-strict.sh:108` 从 `$M/.config` 读取 `CONFIG_XNU_GPU_ADDON=y`，`:126` 读取 `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`。
- 全新的 OUT 目录没有 `.config` 时两条 `sed` 都取到空值，GPU 插件不会被 stage（`K60_METAL_PLUGIN_DIR` 不导出，`k60_metal_blob.s` 不生成），battery archive 也不会构建——构建继续跑，但产物缺功能。
- 必须先执行：`cd /opt/k60/trees/k60build && ./unixnu defconfig mondrian_defconfig -D /opt/k60/trees/gpu-user-device --out /opt/k60/trees/gpu-user-out`，得到 4360 B 的 `.config`。之后再跑 `build-strict.sh`。

### 2.3 首次构建的 battery archive 需要后一步才生成的 hardware.dtb

- `scripts/build-battery-archive.sh:33-35`：`DTB=$M/device-tree/hardware.dtb`，`[ -f "$DTB" ] || die "device tree $DTB missing; build the kernel once first"`。
- 该 dtb 实际由 payload 步骤生成：`/opt/k60/trees/k60build/scripts/unixnu/devicetree.py:402 def compile_hardware(ctx)`，调用点在 `scripts/unixnu/payload.py:232-233`。而 `build-strict.sh` 把 battery archive 排在 kernel/payload 之前，所以全新 OUT 的第一次 battery 构建必然 die。
- 绕法（与 payload 同参数）：`mkdir -p $M/device-tree; dtc -I dts -O dtb -o $M/device-tree/hardware.dtb -i /mnt/e/hackios/UniXNU-sm8475-common/dts /mnt/e/hackios/k60-gpu-user/dts/mondrian.dts` → 4024 B，与 `k60build/out-baseline` 的同名产物同尺寸。

### 2.4 P-194 的首次构建死锁

- `scripts/tests/test-series-source.py:63-68` 的 `newest_manifest()` 按当前分支过滤 manifest；`:130-136` 在找不到 manifest 时硬失败：`a build manifest is available to compare against`。
- 于是「从未构建过的分支」永远过不了这道「只有构建才会产生 manifest」的门禁，形成死锁。
- `feat/gpu-user` 的 `3c84bf5` 增加 `K60_SKIP_MANIFEST_CHECK=1` 逃逸（`:131-133` 打印 skip 行）；上游 `314497d` 只放宽了 scratch 副本断言，没有放宽 manifest 必需这一条。

### 2.5 registry 必须带同一组环境变量

- `scripts/check-rules.py` 必须用与 `build-strict.sh` 相同的 `K60_OUT`/`K60_DEVICE_INPUT`（build-strict 在 `:50-51` 导出），否则 iron-4、hard-33、P-165、P-166 会因为「默认 out-baseline / 默认 usb-cdc-mainline device」而假红。

## 3. boot-args 字节预算

| 集合 | 项数 | 字节 |
| --- | --- | --- |
| origin/main 当前 `board.toml` | 29 | 575 |
| 本线（`pong_metal=1` + `sheng-gpu-addon=1`） | 30 | 593 |
| 再加 `pong_gpu_scanout=1` | 31 | 612 |

- 上限有两个：`scripts/check-image-args.py:40` 的 `DARWIN_BOOT_LINE_MAX = 607`，`scripts/porting-gate.py:411` 的 `length <= 600`。
- 593 B 时两处余量分别是 14 B 与 7 B；`sheng-gpu-addon=1` 单项 19 B。
- 下一轮若要加 `pong_gpu_scanout=1`（+19 B → 612 B），必须先腾出至少 12 B。可删的候选：`k60_autoreset=300`（19 B）、`applog=1`（8 B）、`k60_fontscale=3`（15 B）、`k60_panic_reset=1`（18 B）——按 P-160 的要求，任何删改都要带真实启动对照。

## 4. 用户态 Metal 插件装载门禁链（PongMetalPlugin.mm）

源码：`/mnt/e/k60-work/impl/gpu-mac-build/src/PongMetal/PongMetalPlugin.mm`。

1. `:71` `sysctlbyname("kern.osversion")` 必须等于 `"20G81"`。
2. `:74` `PongMetalDeviceAbiAvailable(_MTLDevice)` 必须为真。
3. `:88-89` IORegistry 属性 `PongAdrenoCPReady` 与 `PongMetal20G81Enabled` 都必须为真——只有 Adreno 发布路径真的跑完，这两个门才开。
4. `:102-108` 设备匹配：`chip_id == 0x07030002`、`gmem_bytes == 0x200000`、`input_bits` 在 31..48。
5. `:165-192` `selectedClient()` 依次扫描两个目录：**`/System/Library/Extensions` 与 `/private/var/pong`**。后者是第二个真实的插件发现目录，之前没有记录；只修 addons union 不够，旧种子路径的 `.publish`/`.clients` 也会被读。
6. `:179/:182` `PongAdrenoMetal.publish` 与 `PongAdrenoMetal.clients` 必须 `S_ISREG`、`st_uid == 0`、`(st_mode & 022) == 0`；`:181` publish 首字符必须是 `'1'`；`:187` clients 中必须有一行等于 `getprogname()`（对 backboardd 即 `backboardd`）。
7. `:195` `startPresentation` 只对 backboardd 启动 `pongscanout`；其他进程即使装载成功也不会启动 GPU scanout worker。
8. 用户态判定 `MTLCreateSystemDefaultDevice` 的代码在 `userland/ui_compat.c:497`/`:508`（`dlsym`），`:510` 只在返回 nil 时打印 `Pong UI: optional camera-filter GPU prewarm skipped (software-only platform)`。

## 5. 本线已验证产物（构建，不是上机证据）

| 项 | 值 |
| --- | --- |
| tag | `gpu-user-20261114d` |
| manifest | `/mnt/e/k60-work/artifacts/gpu-user-20261114d/build-manifest.json` |
| kernel sha256 | `845f4609ae402cc880d05ee5d61360ff7ca0fa730d593253e749c798afb4ab81`（105,480,192 B） |
| boot.img sha256 | `a627dc70d87cd2bb6134d8eb8c34c97e06378bdff07e48d2bf8ac4724933ad84`（201,887,744 B） |
| series | 224 条，sha256 `34cf51e4d10e46eb3514d798a3e3208c3ac7f124dd8a982585e9eea1e8b9c8c0` |
| repo | head `e17efd8f8f4d77e95b50d4c2ce76e2d970350bc2`，dirty_files 0 |
| payload args | 30 项，含 `pong_metal=1` 与 `sheng-gpu-addon=1`（593 B） |
| llvm-nm | `native_gpu_addon_mount` = 1；`k60_metal_deploy` = 2（函数 + `.done`） |
| strings | `PongMetalBridge.dylib` = 3；`PongAdrenoMetal.publish` = 2；`PongAdrenoMetal.bundle/Info.plist` = 2 |
| 镜像校验 | `verify-boot-image.py --manifest` → OK；`check-metal-blob.py` → self-consistent；`check-image-args.py` → 30 arguments / 593 bytes |

构建在用户停手指令之前完成，未上机。该构建的 deploy 运行时行为没有日志，不能把上面的符号/字符串检查当成部署成功的证据。

## 6. 未决与下一步

- `sheng-gpu-addon=1` 生效时 `native_gpu_addon_prepare` 不打印任何 IOLog，只把结果写进 `native_gpu_addon_stage/status` 全局变量（`patches/xnu/zzy-native-gpu-addon-mount.patch:67-83`）。日志里无法直接确认 union 是否挂上，只能靠后续 `Pong Metal: real GPU scanout worker ready status=0x0` 或插件是否被发现来反推。
- deploy 返回值被丢弃（见 1.4 第 1 条），建议后续把 `k60_metal_deploy` 的返回值并入 `native_owner_data_status` 或单独打印，否则真机日志永远显示 `stage=4 error=0`。
- 插件有两个发现目录（见 4.5），部署链要保证 `/private/var/ngpu/addons` 的 union 视图与 `/private/var/pong` 的旧种子内容不会互相遮蔽；只部署一处时要以 `selectedClient()` 的实际命中目录为准。
