# patches/display — 亮度服务（OS 级 backlight）

本目录存放显示线**亮度**部分的补丁记录。它与 `patches/xnu/series` 的补丁性质不同，必须分清：

| | `patches/xnu/*.patch` | 本目录 |
|---|---|---|
| 作用对象 | `.cache/xnu-work` 里的 XNU 源码树 | 仓库自己的 `drivers/`、`scripts/`、`docs/` |
| 如何生效 | 由 `scripts/build-strict.sh` 按 `patches/xnu/series` 顺序 `git apply` | 由 `scripts/sync-device-input.py` 同步进 `K60_DEVICE_INPUT` |
| 何时需要 | 改 Apple 的 XNU 源码 | 改我们自己的驱动源码 |

**不要把本目录的补丁登记进 `patches/xnu/series`。** `patches/xnu/series` 的每一行都必须指向
`patches/xnu/` 下真实存在的文件（`scripts/check-porting-paths.py` 会报 error），而且 series 里的补丁
会以 `git apply` 打到 xnu 树上，路径前缀是 `iokit/`、`bsd/`，与这里的 `drivers/PongAdreno/` 不匹配。
`patches/wifi/README.md` 记录过相反的教训：那份 README 之前写着「这些补丁从未被应用」。

## 补丁清单

### `0620-k60-display-brightness.patch`（1006 行，7 文件）

亮度从「面板点亮」推进到「OS 级亮度服务」的全部改动：

| 文件 | 作用 |
|---|---|
| `drivers/PongAdreno/K60BacklightCodec.h` | **产物 D：DCS 编码器**（纯头文件，无 IOKit）。level↔DBV、nits↔level、FadePeriod↔毫秒、线性渐变插值、`bl-inverted-dbv` 反转。host 可单测。 |
| `drivers/PongAdreno/K60Backlight.cpp` | **产物 A/B/C**：`K60Backlight : IOService`，发布 `IODisplayParameters`（产物 A）、override `setProperties()` 接收 backboardd 请求并驱动渐变（产物 B）、`k60_backlight_start()` 用 preModLoad/postModLoad 动态注册并 impersonate 成 `AppleARMBacklight`（产物 C）。 |
| `drivers/PongAdreno/PongAdrenoScanout.cpp` | 接线：bring-up 成功后调 `k60_backlight_start()`（同归档内互相引用，避免 `0395-k60-panel-call.patch` 那种跨归档链接问题）。 |
| `scripts/build-pong-adreno-platform.py` | 把 `K60Backlight` 加进 `libPongAdrenoPlatform.a` 的编译名单（macOS 侧）。 |
| `scripts/build-pong-adreno-platform-linux.py` | 同上（Linux/WSL 侧，构建机实际用的是这个）。 |
| `scripts/check-brightness-encoder.py` | host 单测：编译编码器头文件并断言 DBV 换算与渐变序列。 |
| `docs/research/display/BRIGHTNESS-PLAN.md` | 八步流程的 ①②③④⑤⑥ 证据与四产物设计说明。 |

## 如何让这些改动进入镜像

```bash
# 1. 同步仓库 -> 本线专属的构建输入（不要用别的线的 device 目录，P-190）
K60_DEVICE_INPUT=/opt/k60/trees/display-device PYTHONIOENCODING=utf-8 \
  python3 scripts/sync-device-input.py

# 2. 严格构建（必须带自己的 K60_OUT，否则会混进别的线的补丁）
K60_OUT=/opt/k60/trees/display-out K60_DEVICE_INPUT=/opt/k60/trees/display-device \
  PYTHONIOENCODING=utf-8 bash scripts/build-strict.sh <tag> --fd <firmware.fd>
```

原因见 `scripts/build-xnu-4k-baseline.sh:263-289`：构建树里的 `patches/xnu` 是指向 device checkout 的
符号链接，`PONG_NATIVE_DRIVER_SOURCE` 由此推导，所以 `drivers/PongAdreno` 的源码只从 `K60_DEVICE_INPUT`
读取——改仓库里的 `drivers/` 而不 sync，构建看不到。

## 补丁的另一个用途：重放

本补丁在仓库里已经应用（源码就在 `drivers/`、`scripts/`、`docs/` 下），保留一份 `.patch` 是为了：

1. **评审**：一次看完 7 个文件的改动，不用翻整棵树；
2. **重放**：在干净 checkout 上 `git apply patches/display/0620-k60-display-brightness.patch` 可复现同一改动。

```bash
git apply --check patches/display/0620-k60-display-brightness.patch   # 已在树上时应报 already applied / 冲突
```

## 回退开关（不上机也能降级）

全部走 boot-arg，不改代码即可逐项关掉（`drivers/PongAdreno/K60Backlight.cpp` 的 `k60_backlight_start`）：

| boot-arg | 默认 | 作用 |
|---|---|---|
| `k60_backlight=0` | 1 | 完全不启动亮度服务，行为退回改动前（面板停在 bring-up 的 0x51 0xff）。 |
| `k60_backlight_control=0` | 1 | 只发 `IODisplayParameters`，**不发** `backlight-control`。用于验证 P-62 的降级路径：万一 impersonate 失败，只发 backlight-control 会触发 int-236（屏幕停更），此时用这个开关把服务降级成「只发布参数」。 |
| `k60_backlight_invert=1` | 0 | 反转 DBV（面板 DT 里有 `bl-inverted-dbv`，但实测 8 位 DBV 下 0xff 最亮，故默认不反转；真机若发现方向相反再用它）。 |

## 上机判据（交给 Lead 执行，本线不自 boot）

1. `K60 BACKLIGHT: published level 2047 dbv 0xff control 1 (impersonated)` 出现在启动日志；
2. `ioreg` 里 `K60Backlight` 服务带 `backlight-control=true` 与 `IODisplayParameters`；
3. 拖 iOS 亮度滑块：`native_backlight_stats[1]`（请求数）递增，`[2]`/`[4]` 跟随；
4. min/mid/max 三档回读值不同且屏上可见变化；
5. 拖滑块过程中屏幕持续更新（不停更 = int-236 未回归）；
6. `native_backlight_stats[5]`（写失败）保持 0。

完整预测与失败判据见 `docs/research/EIGHT-STEPS.toml` 的 `[hardware.brightness.step.device.prediction]`。
