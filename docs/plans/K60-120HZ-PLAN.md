# K60 120Hz 显示方案（离线调研，等根挂载后再实施）

> 数据来源：`D:\Android\k60-ios\dtb\dtbo_a_fdt15.dtb` 的
> `qcom,mdss_dsi_sharp_qhd_cmd` 节点（K60 真实面板，非通用参考面板）。
> 本文所有数值均为**实测提取**，不是推断。

## 1. 面板事实（先纠正两个常见误解）

| 说法 | 事实 |
|---|---|
| "K60 是 LTPO" | ❌ **不是**。面板是 **Sharp QHD AMOLED，LTPS 背板** |
| "只能 60Hz" | ❌ 面板 dtbo **原生提供 120Hz timing**（`timing@0`）|

K60 的刷新率是**固定档位切换**（60 ↔ 120），不是 LTPO 的 1–120 连续可变。
没有 90Hz 档，也没有 LTPO 的自适应帧率。

## 2. 两个 timing 档的完整参数

| 参数 | timing@0（**120Hz**）| timing@1（60Hz）| 备注 |
|---|---|---|---|
| `panel-framerate` | **0x78 = 120** | 0x3c = 60 | 唯一必改项 |
| `panel-width` | 0x2d0 = 720 | 同 | **DSC 压缩后**宽度（实际 1440）|
| `panel-height` | 0xc30 = 3120 | 同 | DSC 压缩后（实际 3200）|
| `h-front-porch` | 0x48 = 72 | 同 | |
| `h-back-porch` | 0x14 = 20 | 同 | |
| `h-pulse-width` | 0x04 | 同 | |
| `v-front-porch` | 0x27 = 39 | 同 | |
| `v-back-porch` | 0x0c = 12 | 同 | |
| `v-pulse-width` | 0x02 | 同 | |
| `mdp-transfer-time-us` | 0x1efd = 7933 | 同 | |
| `display-topology` | `<0x02 0x02 0x02>` | 同 | |
| `dsc-bit-per-pixel` | 0x08 | 同 | |
| `dsc-slice-width` | 0x168 = 360 | 同 | |
| `dsc-slice-height` | 0x08 | 同 | |
| `dsc-slice-per-pkt` | 0x01 | 同 | |
| `compression-mode` | "dsc" | 同 | |

### phy-timings（DSI 物理层时序，**两档不同**）

```
120Hz: [00 1a 07 06 16 21 07 07 07 02 04 00 17 0c]
 60Hz: [00 10 03 03 11 1e 04 04 03 02 04 00 03 09]
```

### timing-switch-command（运行中切档用）

```
→120Hz: 39 01 00 00 00 00 34 c6 00 12 44 00 08 00 0b 01 20 25 30 01 49 01 49 ...
→ 60Hz: 39 01 00 00 00 00 34 c6 00 12 88 00 08 00 0b 01 20 25 30 01 49 01 49 ...
```

差异在寄存器 `0xC6` 的第二个参数：**`0x1244`（120Hz）↔ `0x1288`（60Hz）**。
这是最省事的运行期切档方式——不用重发整个 `on-command`。

## 3. 计算校验（像素时钟）

DSC 压缩后每行 720 像素，HTotal = 720 + 72 + 20 + 4 = **816**
VTotal = 3120 + 39 + 12 + 2 = **3173**

| 刷新率 | 像素率 = 816 × 3173 × fps | 双 DSI（÷2）|
|---|---|---|
| 60 Hz | 155,376,480 ≈ **155.4 MHz** | 77.7 MHz/lane-pair |
| 120 Hz | 310,752,960 ≈ **310.8 MHz** | 155.4 MHz/lane-pair |

两者都在 DSI 4-lane 能力内，所以 **120Hz 不需要改 lane 数或电压**，只需换 timing 档。

## 4. 当前代码状态

日志实测：
```
K60 DISPLAY: panel 1440x3200 DSC video mode, canvas 1440x3200 native, stride 5760, 60 Hz
K60 DISPLAY: TimingElements 1440x3200 at 60 Hz
```
`60 Hz` 是 A2 在 `patches/xnu/0210-k60-display-native-canvas.patch` 里**硬编码**的。

## 5. 实施步骤（根挂载 + 八核之后再做）

### P1：固定 120Hz（最简单）
1. 在 `0210-k60-display-native-canvas.patch` 里把 TimingElements 的刷新率从 60 改 120
2. 同步把 `v-front-porch/v-back-porch/v-pulse-width` 换成上表值（**与 60Hz 相同，实际不用改**）
3. 唯一实质改动：`IOFramebuffer` 的 vsync 周期 `1000000000/120 = 8,333,333 ns`
4. 判据：日志 `K60 DISPLAY: TimingElements 1440x3200 at 120 Hz`，且画面不撕裂

### P2：60/120 运行期切换
1. 实现 `timing-switch-command` 下发（改 `0xC6` 的 `0x1244`/`0x1288`）
2. 暴露一个 sysctl 或 boot-arg 供测试
3. 判据：切档后画面连续、无闪黑

### P3：与 iOS 显示栈对接
- `IOFramebuffer` 的 `IOFBCurrentPixelClock` 要跟着变（155.4 → 310.8 MHz）
- `CADisplayLink` 的 preferredFramesPerSecond 上限才会到 120
- SpringBoard/UIKit 的 ProMotion 支持：iOS 16 在非 Apple 硬件上默认 60，需要伪装成支持 ProMotion 的机型（这层较深，最后做）

## 6. 风险与前置条件

| 风险 | 说明 |
|---|---|
| DSI PLL 未按 120Hz 重算 | 如果 A2 的补丁里 PLL 是按 60Hz 写死的，只改 framerate 会导致花屏/黑屏。**需先确认 0210 补丁里 PLL 的来源** |
| DSC 参数不匹配 | slice-height=8 在两档相同，所以风险低 |
| 面板 `0xC6` 寄存器语义未知 | `0x1244`/`0x1288` 是厂商私有，只能照抄，不能推导 |

**结论**：面板硬件与 dtbo 都支持 120Hz，参数已完整提取；
真正的工作量在"确认 A2 补丁里的 PLL/时钟是否可配置"，而不是找时序。
建议在根挂载 + 八核稳定后再做，避免把显示问题与启动问题混在一起。
