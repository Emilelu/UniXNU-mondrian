# 音频八步调研（① 同型 / ② 官方 / ③ 反编译）

> 目标子系统：音频（WCD938x codec + ADSP + AudioReach）
> 日期：2026-11-12
> 状态：①②③ 完成，④⑤⑥ 待办

---

## ① 同型：Pong 的音频实现

**来源**：`references/pong-power`，分支 `origin/port/ios18e-native-302`

| 文件 | 大小 | 作用 |
|---|---|---|
| `PongAdsp.cpp` | **34,547 B** | ADSP PAS1 启动 + SMEM/SMP2P/GLINK 传输 |
| `PongAudio.cpp` | **29,263 B** | AudioReach / PRM 命令通道与周期填充 |
| `PongIOAudio2.h` | 23,857 B | IOAudio2 驱动接口 |
| `PongAudioService.cpp` | 7,509 B | 音频服务注册 |
| `PongWcd938.h` | 6,262 B | WCD938x codec 前置条件与 PRM 投票 |
| `PongFirmware.c` | 5,488 B | 固件加载 |
| `PongGlyph.cpp` | 6,466 B | AW20036 Glyph LED（非音频，但同仓库）|

**总计约 107 KB。**

### 关键硬件真值（代码注释原文）

```
/* Pong SM8475 WCD938x prerequisites. Hardware inputs are the actual Pong
 * DTS and NothingOSS c402fcdb audio-kernel SWR/LPASS implementations.
 * AudioReach/PRM encoding is shared with UniXNU-sheng. Do not publish a
 * microphone until the physical capture graph actually returns PCM. */

// Actual DT: PM8350 S10B supplies WCD RXTX/buck/IO at 1.8V.
```

**三条要点：**
1. 硬件输入来自**实际 DT**，不是推断
2. SWR/LPASS 参考 **NothingOSS `c402fcdb`** 的 audio-kernel
3. AudioReach/PRM 编码与 **UniXNU-sheng 共享**
4. **明确警告**："在物理采集图真的返回 PCM 之前不要宣布麦克风可用"

### 平台地址

| 块 | 基址 | 大小 | 代码位置 |
|---|---|---|---|
| CMD DB（RPMh 资源）| `0x80860000` | `0x20000` | `PongWcd938.h` `rail()` |

**PM8350 S10B** 供 WCD RXTX/buck/IO，1.8V。

### PRM 投票机制

`PongWcd938::prmClock(id, rate)` 会为每个 rate 尝试两个频率（`rate` 与 `19200000` 或 `9600000`）× 两个 attribute（1 和 0），
任一被接受即成功。每次投票都打日志：

```
Pong WCD938: physical PRM clock=%x Hz=%u attribute=%u ACK=%u error=%d
```

**这是可复用的诊断模式。**

---

## ② 官方：UniXNU 组件目录

**查 `components.toml` 25 个组件：无音频组件。**

官方唯一的音频相关代码在 `UniXNU-sheng` 设备仓库里（`sheng_audio_service_start()` 被 Pong 引用），
但那是 Novatek/SM8550 的板级实现，不是可复用组件。

**结论**：官方无音频组件，参考链是 **Pong + UniXNU-sheng + NothingOSS audio-kernel**。

### 官方文档

`https://unixnu.com/zh/porting/power`（DSP、音频与电源）—— ④ 阶段读

---

## ③ 反编译：K60 本机真值

### 已知（来自 ANDROID-HW-TRUTH.md）

K60 与 Pong 同为 SM8475，音频 codec 大概率也是 **WCD938x**，
但**必须实测确认**。

### 待补的 ③ 项

- [ ] K60 的 audio codec 型号（`/proc/asound/cards` 或 DT `qcom,wcd938x`）
- [ ] K60 的 ADSP PAS ID（Pong 用 PAS1）
- [ ] K60 的 PMIC 轨道名（Pong 用 PM8350 S10B）
- [ ] K60 的 SWR 主/从配置
- [ ] K60 的扬声器/听筒/麦克风 GPIO
- [ ] K60 的 `aw882xx` 智能功放（K60 有独立的 smart PA，Pong 可能没有）

---

## ④⑤⑥ 待办

- ④ 广域：读 `unixnu.com/zh/porting/power`；查 UniXNU-sheng 的音频实现；
  查 NothingOSS audio-kernel 的 `c402fcdb`
- ⑤ 方案：决定先做 codec 还是先做 ADSP
- ⑥ 深挖：ADSP PAS 启动失败的诊断路径

---

## 风险与约束

1. **ADSP 是独立处理器**，需要 PAS（Peripheral Authentication Service）启动流程，
   和 GPU 的 GMU 类似但更复杂（涉及 SMEM/SMP2P/GLINK 三层传输）。
2. **AudioReach/PRM 是 Qualcomm 私有协议**，需要正确的 IID 与命令编码。
3. **K60 有独立的 smart PA（aw882xx）**，Pong 可能没有——这是额外的驱动。
4. **Pong 明确警告不要过早宣布麦克风可用**——说明这条线容易被"看起来通了"误导。

---

## 优先级建议

音频是 P3（新子系统），低于：
- P0 触摸 ⑦ 核验
- P1 GPU Metal 追平
- P2 UFS 对齐官方架构（已完成等待策略部分）

**而且 ADSP 启动比 GPU 的 GMU 更复杂**，建议放在 WiFi 之后。
