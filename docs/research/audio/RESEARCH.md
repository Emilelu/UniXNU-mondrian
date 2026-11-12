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

---

## ④ 广域：官方 power 页给出的完整路径与 SM8550 硬事实

来源：https://unixnu.com/zh/porting/power （2026-11-12 读取）

### 硬前置

> 先完成[平台内存、中断和 DMA](/zh/porting/platform)。

与 WiFi 相同：音频排在平台之后。我们的 UFS 已提供 DMA 与中断。

### 要确认的四类输入（文档第 1 节）

| 功能 | 需要的输入 | 产物 |
|---|---|---|
| DSP | 固件/PAS ID、内存预留、邮箱中断、共享内存布局、时钟与电源归属 | 固件加载器 + 消息传输 |
| 音频 | codec/功放 ID、总线、时钟、路由、DSP 拓扑、支持格式、OS 音频 ABI | 端点配置、流引擎、OS 服务 |
| 电池 | 电量计或固件协议、属性 ID、单位、电流符号、通知消息 | 测量值解码器 + power-source 服务 |
| 电源 | 时钟域、OPP 表、稳压器、固件投票、温控限制 | 板级策略 |

### DSP 传输（`ShengAdsp` / `AdspProbe.cpp`）

```c
sheng_adsp_channel(name, intent_size, intent_count, initiator, callbacks, context);
sheng_adsp_send(...);   // 0=已入队  -1=队列满或消息过长  -2=参数错
#define SHENG_ADSP_MAX_MESSAGE 512
```

**所有权**：回调运行在 DSP 线程，必须把字节**复制到有界队列**再唤醒消费者工作循环；
请求处理和等待放在消费者侧。

**结果判据**：通道能打开、完成一次有超时的请求/响应、报告失败并重连。

### 音频流（AudioReach / GPR）

**SM8550 上决定通路能否启动的五个细节（文档原文）**：

1. **DSP 接收的缓冲区地址是 32 位，高 32 位放流索引（`0x1001 & 0xf`）。周期缓冲区要放在 4 GiB 以下。**
2. DSP 先给小 GLINK intent，请求后再给大的。**远端 intent 表满时也要保留新给的 intent。**
3. PRM 请求从 PRM 自己的端口发出，用 PRM 时钟 ID；**TX core 时钟是 `0x30c`，不是设备树里的编号。**
4. **VA macro 和 TX macro 都要打开 TX SoundWire master 的时钟门控。**
5. **CoreAudio 假定 host clock 为 24 MHz。时基为 19.2 MHz 时，音频服务必须在启动时修正这个常量，
   否则音频服务器的 IO 周期会长 25%，播放和录音都会卡顿。**

**第 5 条对我们的 K60 尤其重要** —— SM8475 的时基也是 19.2 MHz，
如果我们做音频而不修正这个常量，就会出现「能出声但卡顿」的假成功。

### 麦克风采集的参考路由（SM8550）

| 阶段 | 参考取值 |
|---|---|
| Codec | WCD938x，复位 gpio108，供电 ldob15，TX master（`0x6d30000`）上的 SoundWire 设备 1 |
| 模拟 | AMIC3、micbias 3、ADC2 |
| 链路 | codec 数据端口 1 通道 2 → master 端口 2 |
| 数字 | TX decimator 0 读 `SWR_MIC1`，codec DMA TX3 |
| 格式 | 单声道，48 kHz |
| iOS | HAL 插件的输入端口；**iOS 只在 Thunderbolt 传输类型下接受它** |

**验证命令**：`audio=4` 在启动时读两秒，`[mic]` 与 `[mic capture]` 日志给出
返回周期、字节数、非零样本比例和峰值。

### 与 K60 的差异

| 项 | sheng（SM8550）| K60（SM8475）|
|---|---|---|
| Codec | WCD938x | **待实测**（Pong 也用 WCD938x，同 SoC 大概率相同）|
| 功放 | CS35L43（I2C）| **K60 有独立的 aw882xx smart PA** |
| reset gpio | 108 | 待实测 |
| 供电 | ldob15 | 待实测（Pong 注释：PM8350 S10B 供 WCD RXTX/buck/IO 1.8V）|
| TX master | `0x6d30000` | 待实测 |
| 时基 | 19.2 MHz | **19.2 MHz（相同，第 5 条硬事实直接适用）** |

---

## ⑤ 方案（初稿，待 ③ 实测后细化）

按官方顺序，前置是 DSP 传输通：

**第一步：DSP 传输（`ShengAdspClient` 形状）**
- 固件加载（PAS1）+ SMEM + SMP2P + GLINK + 邮箱
- 先建立 **ready/crash 通知路径**，再打开通道
- 判据：通道能打开 + 一次有超时的请求/响应

**第二步：AudioReach 图**
- 先做**播放**（比采集少 SoundWire 链路）
- 周期缓冲区必须放在 **4 GiB 以下**（第 1 条硬事实）
- 修正 CoreAudio 的 24 MHz 常量（第 5 条）

**第三步：采集（麦克风）**
- 需要 codec 上电 + SoundWire 枚举 + 模拟通路 + 数字通路四段

**第四步：接入 OS**
- 从 kernelcache 和框架确认音频 provider、必需方法、请求布局

---

## ⑥ 深挖待办

- [ ] K60 的 DSP PAS ID（Pong 用 PAS1）
- [ ] K60 的 codec 型号、reset gpio、供电轨道（实测）
- [ ] K60 的 aw882xx smart PA 的 I2C 地址与寄存器表
- [ ] K60 的 TX SoundWire master 基址
- [ ] K60 的时基确认（若非 19.2 MHz，第 5 条需重算）

---

## ⑥ 深挖（离线部分）：三条硬结论

### 一、DT 侧必须先建节点，否则驱动静默失败

实测我们的板级 DT：

```
/opt/k60/trees/usb-cdc-mainline/device/dts/mondrian.dts   3,032 B
包含：memory / ufs / pong-touch / pong-buttons
不含：audio / codec / wcd / sound / adsp / swr / aw8 / mic / spk
```

而现有两个驱动都是**按精确节点名查找并逐项断言值**：

```c
// pong_goodix 的 configuration()
if (SecureDTLookupEntry(NULL, "/arm-io/pong-touch", &entry) != kSuccess) return false;

// pong_buttons 的 configuration()
if (SecureDTLookupEntry(NULL, "/arm-io/pong-buttons", &e) != kSuccess) return false;
```

**音频驱动若照同样写法，缺节点就会像实体键一样静默返回 false。**
实体键那一轮我们已经把这种静默改成了逐条件诊断（P-142），音频必须从一开始就这么写。

**待办**：在 `mondrian.dts` 里建 `/arm-io/pong-audio`（或按 UniXNU 的 ADT 约定），
列出 codec、功放、TX master 基址、reset gpio、供电轨道。

### 二、五条 SM8550 硬事实中两条对 SM8475 直接适用

| # | 硬事实 | 对 K60 的适用性 |
|---|---|---|
| 1 | DSP 收 32 位缓冲区地址，高 32 位放流索引（`0x1001 & 0xf`）；周期缓冲区必须 < 4 GiB | ✅ **直接适用**（同为 Qualcomm DSP）|
| 2 | DSP 先给小 GLINK intent，请求后再给大的；远端表满时也要保留 | ✅ 直接适用（GLINK 层）|
| 3 | TX core 时钟是 `0x30c`，不是设备树编号 | ⚠️ **待实测**（时钟 ID 可能不同）|
| 4 | VA macro 和 TX macro 都要开 TX SoundWire master 时钟门控 | ⚠️ 待实测（macro 布局可能不同）|
| 5 | CoreAudio 假定 host clock 24 MHz；时基 19.2 MHz 时必须修正 | ✅ **直接适用**（SM8475 时基也是 19.2 MHz）|

**第 5 条最危险**：不修正会得到「能出声但卡顿」的假成功 ——
比彻底失败更难判断，因为第一耳朵听起来是好的。

### 三、K60 有独立的 aw882xx smart PA

```
sheng：CS35L43（I2C 功放）
K60：  aw882xx（smart PA，独立 I2C 地址与寄存器表）
```

**这是 sheng 没有的额外驱动**，必须在 DT 与代码里单独处理。
Pong 的 `PongWcd938.h` 只覆盖 codec，不含 smart PA —— 说明 Pong 的板子可能没有，
或者用别的方式处理。

**待办**：从 K60 的 Android 侧确认 aw882xx 的 I2C 地址与初始化序列。

---

## ⑥ 深挖待办（需要设备）

- [ ] K60 的 DSP PAS ID（Pong 用 PAS1，K60 待确认）
- [ ] K60 的 codec 型号（Pong 用 WCD938x，同 SoC 大概率相同，但需实测）
- [ ] K60 的 TX SoundWire master 基址（sheng 是 `0x6d30000`）
- [ ] K60 的时基确认（若非 19.2 MHz，第 5 条需重算）
- [ ] aw882xx 的 I2C 地址与寄存器表
- [ ] TX core 时钟 ID（sheng 是 `0x30c`）
