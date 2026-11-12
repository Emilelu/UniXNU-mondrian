# 电池 / 充电 八步调研（① 同型 / ② 官方 / ④ 广域）

> 目标子系统：电池与充电（IOPMPowerSource）
> 日期：2026-11-12
> 状态：①②④ 完成，③ 待实测，⑤⑥⑦⑧ 待办

---

## ① 同型：yibiya 的 K60Battery

来源：yibiya `fix/touch-gpu-bringup` 的 `fix(touch,power): land the handshake,
config download and battery link`

| 文件 | 大小 | 作用 |
|---|---|---|
| `drivers/PongPower/K60Battery.cpp` | 446 行 | IOPMPowerSource 子类：initProperties / publish / updateAdapter / 三个定时器 |
| `drivers/PongPower/K60BatteryConfig.h` | 3,137 B | `K60BatteryConfig`（112 B）与 `K60AdspGlinkHandoff`（104 B）结构 |
| `drivers/PongPower/K60BatteryConfig.c` | 5,032 B | 配置与交接租约的解析 |
| `drivers/PongPower/K60BatterySmoke.c` | 6,677 B | 冒烟测试 |
| `scripts/build-k60-physical-battery.py` | 17,875 B | 生成配置与嵌入 |
| `patches/xnu/0602-k60-physical-battery.patch` | 1,274 B | 接入内核 |

### 硬前置：ADSP GLINK 交接

`K60Battery::begin()` 的签名就写明了依赖：

```cpp
bool K60Battery::begin(IOService *provider, const K60BatteryConfig &config,
                       const K60AdspGlinkHandoff &handoff)
{
    ...
    const K60PmicGlink::Client callbacks = {state, receive};
    if (!transport.open(config, handoff, callbacks, this)) {
        IOLog("K60Battery: physical transport initialization rejected ...");
        return false;
    }
}
```

`K60AdspGlinkHandoff` 的头文件注释写明：

> A real platform/loader PAS1 owner, not a boot argument, supplies this lease.
> It must initialize the APSS FIFOs while ADSP is stopped, authenticate PAS1,
> retain its power/XO/interconnect requirements and relinquish GLINK completely.

**四个必须由 PAS1 owner 提供的标志**：
```c
K60AdspAuthenticated  = 1u << 0
K60AdspResourcesHeld  = 1u << 1
K60AdspGlinkExclusive = 1u << 2
K60AdspFreshHostFifos = 1u << 3
K60AdspHandoffRequired = 15u   // 四个全要
```

**结论：电池依赖 ADSP，ADSP 依赖 PAS1。我们没有 ADSP。**
这解释了为什么电池无法独立推进。

---

## ② 官方：组件目录

`components.toml` 25 个组件里没有电池组件。官方实现全在 UniXNU-sheng 的
板级 `package/` 下（`ShengBattmgr.c/h`、`ShengBattery.cpp`、`BatteryProbe.cpp`）。

---

## ④ 广域：官方 power 页的电池章节

来源：https://unixnu.com/zh/porting/power （2026-11-12 读取）

### 六步流程（文档第 4 节）

1. 实现目标电量计读取或固件请求。用参考 PMIC GLINK 协议时，接收值前核对
   **owner、消息类型、opcode、属性 ID 和响应长度**。
   **每次保留一个未完成请求，处理其超时后再推进刷新周期。**
2. 分别保存有效读数与缺失/失败状态。快照包含：电池存在、外接电源、充电状态、
   容量、电压、电流、温度、剩余时间。**记录每项原始值到 OS 值的转换。**
3. 用选定 XNU 头文件继承 `IOPMPowerSource`，创建工作循环、响应队列和
   请求/刷新计时器。
4. **初始有效属性准备好后调用 `registerService()`，后续变化调用 `updateStatus()`。**
5. 订阅变化通知并安排周期刷新。传输断开时取消请求并把读数标为过期。
6. 将原始读数与发布属性对比目标电量计或原厂系统读数。

### 参考实现的单位转换（可直接复用）

| 量 | 转换 |
|---|---|
| 电压 / 电流 | 微单位 → 毫单位 |
| 容量 | 0.01% → 百分比 |
| 时间 | 秒 → 分钟 |

**使用前必须确认目标协议的充电电流符号。**

### 参考源文件

| 源码 | 用途 |
|---|---|
| `ShengBattmgr.h/.c` | 请求/响应格式、刷新状态机、单位转换 |
| `ShengBattery.cpp` | IOPMPowerSource 属性、工作循环、计时器、通知 |
| `BatteryProbe.cpp` | 类注册与服务启动 |
| XNU `IOPMPowerSource.h` | power-source 属性设置与状态发布 API |
| Linux `qcom_battmgr.c` | Qualcomm 电池管理器协议变体 |

### 结果判据

> OS 收到单位明确、及时更新的测量值。固件负责充电控制时保留其所有权，
> 驱动实现测量值发布。主机控制的充电器需要独立的控制协议、限值和温控策略。

---

## 结论与解锁条件

**电池被 ADSP 挡住。** 推进顺序必须是：

```
PAS1（ADSP 认证与启动）
  -> GLINK 通道
    -> PMIC GLINK
      -> 电池协议
        -> IOPMPowerSource
```

任何跳过前两层的做法都只会得到 `physical transport initialization rejected`。

**解锁条件**：先完成音频的 DSP 传输（`ShengAdsp` 形状），因为两者共用同一套
PAS1 + SMEM + SMP2P + GLINK 基础设施。

---

## ⑤⑥⑦⑧ 待办

- [ ] ③ 反编译：K60 的 PMIC GLINK owner / 消息类型 / 属性 ID（实测）
- [ ] ⑤ 方案：在 DSP 传输通之后按官方六步实现
- [ ] ⑥ 深挖：电流符号的判定方法
- [ ] ⑦ 核验：单位转换的离线单测（可先做，不依赖设备）
- [ ] ⑧ 上机：与 Android 侧读数对比
