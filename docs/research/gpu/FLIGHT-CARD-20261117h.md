# 上机卡 2026-11-17e —— 打开 addon 联合挂载，让 Metal 能找到 PongAdrenoMetal.bundle

## 1. 目的

上一飞（`gpu-loadmark-20261117`）证明插件被 dyld 装进 backboardd（`:1288 Pong Metal: plugin loaded`），
但除构造函数外没有任何 `Pong Metal:` 输出 ⇒ Metal 从未向插件要过设备。

上游 `8cdfcff feat(gpu): decouple the GPU addon mount from the offline broker` 的提交说明写明：

> The plugin is reached through MetalPluginName -> /System/Library/Extensions/PongAdrenoMetal.bundle,
> a sealed read-only volume, so zzy-native-gpu-addon-mount is not optional for scanout: it is the only
> way that bundle can exist.

也就是说：插件虽然装进了 `/private/var/pong`（init 注入）与 `/private/var/ngpu/addons`（我们的双 root 部署），
但 **Metal 只会在 `/System/Library/Extensions/<MetalPluginName>.bundle` 找它**，而那是只读卷。
唯一通路是 `zzy-native-gpu-addon-mount.patch` 把 `/private/var/ngpu/addons` 联合挂载上去，
该补丁由 boot-arg `sheng-gpu-addon=1` 打开。

本飞只做这一件事：打开 `sheng-gpu-addon=1`，验证联合挂载成功，并观察插件是否因此被 Metal 实例化。

## 2. 前提证据（上机前必须全部成立）

| 编号 | 证据 | 结果 |
| --- | --- | --- |
| P1 | `board.toml` 的 `kernel_args` 含 `sheng-gpu-addon=1`，且总字节 ≤ 607 | 30 项 / 597 B |
| P2 | `0398-k60-pong-runtime-directories.patch` 在 series 中，创建 `/private/var/ngpu`、`addons`、`daemons` | 是（series:214） |
| P3 | `zzy-native-gpu-addon-mount.patch` 在 series 中，gate 名为 `sheng-gpu-addon`，校验路径为 `PongAdrenoMetal.bundle/Info.plist` | 是（series:215） |
| P4 | `CONFIG_XNU_GPU_ADDON=y` | 是（defconfig:27） |
| P5 | `check-patch-apply.py` 通过 | 见构建日志 |
| P6 | `image-arg-audit: OK` 且点名 `sheng-gpu-addon=1` | 见构建日志 |
| P7 | `verify-boot-image: OK` | 见构建日志 |

本卡判定的镜像：`gpu-addon4-20261117`（`boot.img` 的 sha256 见 §5，构建后回填）。

## 3. 抓取

`K60_DEVICE_INPUT=/opt/k60/trees/gates-device K60_FORCE_NEW=1 bash scripts/flash.sh <boot.img> 240`，
证据落 `E:/k60-work/evidence/usblog-<时间戳>/`（`console.log` + `capture.json` + `boot.json`）。

## 4. 判据

**成功（S，全部满足才算修好一步）**

- **S1** `K60KEXC` 命中 0（无内核异常）。
- **S2** `console.log` 出现 `K60GPUADDON addons stage=5 status=0` —— 联合挂载完成，且
  `/System/Library/Extensions/PongAdrenoMetal.bundle/Info.plist` 通过该联合可见。
- **S3** `Pong Metal:` 行数 ≥ 2（构造函数之外的任何一行，说明 Metal 真的向插件要了设备）。
- **S4** `present #` 命中 ≥ 1（`GpuScanoutPresenter` 真的出了一帧）。
- **S5** `crashed: backboardd` 命中 0。

**失败（F，任一命中即判 FAIL，并在卡片 §5 记录命中的是哪一条）**

- **F1** 出现 panic / `K60KEXC` / 抓取被复位中断。
- **F2** `K60GPUADDON addons stage` 小于 5（在 §5 记下 stage 与 status 的具体值）。
- **F3** `Pong Metal:` 行数 ≤ 1（插件仍未被实例化）。
- **F4** `present #` = 0。
- **F5** `crashed: backboardd` ≥ 1。

## 5. 结果登记
### 2026-11-17 13:13 — gpu-addon4-20261117

- 镜像：`gpu-addon4-20261117/boot.img`，sha256 `0614aa977e7e7b212517a4fea3460c934e1fc9347a7ed3f3a7902988d5722622`
- 证据：`E:/k60-work/evidence/usblog-20261117-130912`（198,320 B，抓取完整、未因 panic/复位中断）
- 实测：S1 通过（`K60KEXC` 0）；S2 通过（`:484 K60GPUADDON addons stage=5 status=0 daemons stage=4 status=2`）；
  S3 通过（`Pong Metal:` **91** 行，含 `:1370 real Vulkan-backed device created status=0x0`、
  `:1374 real device returned to stock20G81 discovery`、`:1382 real GPU scanout worker ready`）；
  S4 未通过（`present #` **0**）；S5 通过（`crashed: backboardd` **0**，崩溃只有 syncdefaultsd/mmaintenanced）。
- 判决：**FAIL(F4)** —— Metal 设备发现与插件实例化首次成立，但还没有一帧被提交、呈现。
- 新观测：`Pong Metal: S c0/0 d0 p0 x6 R0 D0 F0 M0k C0 B0` 出现 4 次（`x6` = 6 个越过 import 的帧，
  `c0`/`p0` = 0 提交 0 呈现）；`Pong Metal: W metal2vulkan: … Turnip Adreno (TM) 725 …` 8 次
  （bridge 已与真实 Vulkan 设备通信）；`PONG SCANOUT: actual framebuffer handoff available sequence=0 status=0x0`（:180/:181）。
- 本轮修的缺陷：`Info.plist` 只有 `NSPrincipalClass`，缺 `MetalPluginName` / `MetalPluginClassName`
  （Metal 读的是这两个键），插件被 dyld 装载但从未实例化。修法：`scripts/ensure-metal-plugin-keys.py`
  + `stage-metal-plugin.sh` 在暂存阶段补齐（blob 走 `.incbin`，必须在暂存文件上改），
  测试 `test-metal-stage-keys.py` 3 例 + `test-metal-blob-info-plist.py` 3 例。


（上机后填写：镜像名、boot.img sha256、证据目录、S1–S5 与 F1–F5 的实测值、判决。）
