# GPU/Metal 与 yibiya 上游的一致性对账

日期：2026-11-17
范围：`drivers/PongAdreno/`、`drivers/PongMetal/`、`scripts/build-pong-metal-plugin.py`、`scripts/gen-k60-metal-blob.py`、`scripts/stage-metal-plugin.sh`、`userland/init.c`、`patches/xnu/{*metal*,*gpu*,04*,06*}`。

对账基线：`E:/k60-work/references/yibiya-upstream`（`origin/main` = `27a33321`）。
工具：`E:/k60-work/scratch/gpu_vs_upstream.py`（按文件 sha256 比对，输出 SAME/DIFF/ONLY-OURS/ONLY-THEIRS）。

## 1. 总体结果

| 类别 | 数量 |
| --- | --- |
| SAME（逐字节相同） | 110 |
| DIFF（同名不同内容） | 17 |
| ONLY-OURS（我们自建、上游没有） | 28 |
| ONLY-THEIRS（上游有、我们没有） | 0 |

**关键结论：Metal 发现链路的代码与上游逐字节相同**，包括
`drivers/PongAdreno/PongAdrenoAccelerator.cpp`（`:44 setProperty("MetalPluginName","PongAdrenoMetal")`、
`:45 setProperty("MetalPluginClassName","PongAdrenoMetalDevice")`）、
`drivers/PongAdreno/submit/NativeAdrenoPublish.cpp`、
`drivers/PongAdreno/submit/NativeAdrenoAccelerator.cpp`。
因此「插件已装载但从未被实例化」不是代码漂移造成的，剩下的差异只在诊断/显示代码与部署配置。

## 2. DIFF 清单（15 个代码 + 2 个补丁）

| 文件 | 我方字节 | 上游字节 | 差异性质 |
| --- | --- | --- | --- |
| `drivers/PongAdreno/PongAdrenoPlatform.cpp` | 30511 | 21755 | 我方 22 阶段诊断 + `pong_rpmh_lock/unlock` 调用 |
| `drivers/PongAdreno/PongAdrenoPower.c` | 8967 | 7166 | 我方 RPMh IOVDD 修法（`40703be`，触摸供电必需） |
| `drivers/PongAdreno/PongAdrenoPower.h` | 2792 | 2026 | 同上 |
| `drivers/PongAdreno/PongAdrenoRegisters.h` | 1536 | 1447 | 我方补充寄存器定义 |
| `drivers/PongAdreno/PongAdrenoScanout.cpp` | 9630 | 9558 | 基本相同，少量诊断 |
| `drivers/PongAdreno/PongDsiPanel.cpp` | 14936 | 7347 | 我方面板初始化/计费工作（display 线） |
| `drivers/PongAdreno/PongDsiPanel.h` | 1093 | 822 | 同上 |
| `drivers/PongAdreno/submit/NativeAdrenoCpu.cpp` | 9219 | 9093 | 我方诊断 |
| `drivers/PongAdreno/submit/NativeAdrenoMemory.cpp` | 20433 | 19128 | 我方 64 页批量 + 诊断 |
| `drivers/PongAdreno/submit/NativeAdrenoMemory.h` | 8368 | 8181 | 同上 |
| `drivers/PongMetal/GpuScanoutPresenter.h` | 7361 | 5013 | 我方分段计时/探针 |
| `drivers/PongMetal/PongMetalPlugin.mm` | 12280 | 11351 | 我方 constructor 标记 + telemetry |
| `drivers/PongMetal/PongMetalScanout.h` | 8935 | 5455 | 我方 256 点采样探针 |
| `drivers/PongMetal/PongQuartzCorePolicy.h` | 5838 | 5558 | 我方 `once` 断言放宽（上游同一修法在 `044f0dd`） |
| `userland/init.c` | 27712 | 20889 | 我方 init 变体（`init-v24dp`） |
| `patches/xnu/0401-k60-embedded-init.patch` | 1668068 | 1586665 | 内嵌 init blob 不同（34904 vs 52376） |
| `patches/xnu/zzy-native-gpu-addon-mount.patch` | 7909 | 7892 | 我方加了诊断打印与 gate 改名（待回退） |

处置原则：
1. **保留**有真机/单元证据的差异（`PongAdrenoPower.*` 的 RPMh IOVDD、`NativeAdrenoMemory` 批量、`PongQuartzCorePolicy` 断言放宽、`PongDsiPanel.*` 显示工作）。
2. **回退**纯诊断且无证据的差异（`PongAdrenoPlatform.cpp` 的多余阶段行、`PongAdrenoRegisters.h` 多余定义）—— 逐个单变量验证后再动，避免一次改太多。
3. `zzy-native-gpu-addon-mount.patch` 的 `gpu-addon` 改名**回退为 `sheng-gpu-addon`**（与上游一致），字节预算另找。

## 3. 上游自身的缺陷（用户 m36317 要求一并修）

### YB-01 `zzy-native-gpu-addon-mount.patch` 的校验路径与真实 bundle 名不一致

`patches/xnu/zzy-native-gpu-addon-mount.patch:77-78`：

```
sizeof(extensions_point), "/System/Library/Extensions/AGXMetalA10.bundle",
"/System/Library/Extensions/NativeAdrenoMetal.bundle/Info.plist", &native_gpu_addon_stage,
```

但真实产物是 `PongAdrenoMetal.bundle`（`PongAdrenoAccelerator.cpp:44` 的 `MetalPluginName` 就是
`PongAdrenoMetal`，`scripts/gen-k60-metal-blob.py` 的 `FILES` 也全是
`addons/PongAdrenoMetal.bundle/*`）。**上游这张补丁在 `stage 3` 校验的是一个永远不存在的
`NativeAdrenoMetal.bundle`**，所以即使打开 `sheng-gpu-addon=1`，stage 校验也会停在 3 而不会走到
「挂载成功」。这正是「yibiya 没完善/有 bug」的一处，也是我们打开 addon 时必然踩到的坑。

修法：把校验路径改为 `/System/Library/Extensions/PongAdrenoMetal.bundle/Info.plist`，并补一个
`drivers/PongMetal/seeds/Info.plist` 的 `CFBundleIdentifier` 与 `MetalPluginName` 一致性断言，
防止将来 bundle 改名再漂移。

### YB-02（待核）上游 `present #` 的运行时前提未记录

`docs/plans/GPU-ENABLE-PLAN.md` §7.14 只记了 `present #` 的耗时数据，没有记录当次启动的完整
boot-arg 与 `sheng-gpu-addon` 状态。按 `:292` 的说法「第一轮不用」，则 `present #` 是在
**没有** addon 挂载的情况下出现的 —— 这与「Metal 只在 `/System/Library/Extensions` 找插件」的
模型矛盾，必须用一次可观测实验确认：`backboardd` 是否真的读过 `MetalPluginName`（
`NativeAdrenoPublish.cpp` 已内建该计数器），以及它读到的 bundle 路径是什么。

## 4. 下一步（顺序固定）

1. 回退 `gpu-addon` 改名为 `sheng-gpu-addon`，重新构建到 607 B 以内。
2. 修 YB-01（校验路径 + 一致性断言 + 单测）。
3. 用 `NativeAdrenoPublish.cpp` 的 `MetalPluginName` 读取计数器做一次离线可判读的上机（预写卡片），
   确认「谁在读、读的什么、有没有去 Extensions 找」。
4. 按结果决定是否打开 addon 挂载；若打开，必须同时验证 YB-01 修好后的 stage 1→5 全绿。
