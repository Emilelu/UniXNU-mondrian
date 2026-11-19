# 稳压器、互连与温控的执行顺序（官网 §5 :108）

状态：**研究记录 + 纯顺序/回滚模型（`K60RailPlan`，107 项断言）；没有新增寄存器写路径**。
官网要求「实现工作点请求和状态回读，按规定顺序执行目标稳压器、互连和温控要求」
（`E:/k60-work/scratch/power-page-20261117.txt:108`）。
本文件回答三件事：K60 现在有没有这些写路径、允许写到什么程度、下一步按什么顺序做。

## 1. 官网要求

- :107 读取目标 LUT、参考时钟和使能状态——EPSS 只读探针已做，GPU OPP 表已解析。
- :108 工作点请求和状态回读，按稳压器 → 互连 → 温控的顺序执行。
- :109 为外设电源投票明确所有权和引用计数；停止依赖的 DMA 和中断后再释放资源。
- :110 OS 电源回调、睡眠/唤醒，见 `power/02-PLATFORM-SLEEP.md`。

## 2. 现有写路径

| 路径 | 文件 | 实际行为 | 授权状态 |
| --- | --- | --- | --- |
| ADSP 启动投票 | `drivers/PongPower/K60AdspRouteA.c:216-267` | 只写 TCS4 的 `lcx.lvl`/`lmx.lvl`，active-only；先查 TCS3 冲突、清旧命令、发 msgid/address/data、置 control 16/24、轮询完成（最多 200000 次），最后关命令位 | HR-01 唯一授权例外（`docs/ops/HARD-RULES.md:31-35`） |
| 触摸 IOVDD | `drivers/PongAdreno/PongAdrenoPower.h:41-48`、`PongAdrenoPlatform.cpp:562`、`patches/xnu/...pong-touch-console.patch:38,194` | 注释写明「DRV2/TCS3 voltage+enable transaction」；零表示两条新命令被接受且 TCS idle，不表示 PMIC 校验或触摸就绪 | **不在 HR-01 文本例外内**；启用前必须取得用户/Lead 批准 |
| GPU 电源表 | `drivers/PongAdreno/PongAdrenoPower.c:143-189` | 从 cmd-db 构造 gfx/mx/cx、SH0/MC0/ACV/CN0、12 档带宽命令；只生成表，不写寄存器、不发 HFI | 只读规划 |
| PMIC 账本 | `drivers/PongPower/K60PmicRail.h` | 只读 DRV-2/cmd-db 采样，ledger magic `RL60` | HR-01 四条件只读 |
| 投票账本 | `drivers/PongPower/K60PowerVotePlan.c` | 16 资源 × 32 所有者的引用计数，拒绝重复占用；释放分三步：stop-dma、mask-irq、drop-vote | 纯记账，无消费者、不写硬件 |
| 执行顺序模型 | `drivers/PongPower/K60RailPlan.c` | 纯函数生成 regulator→interconnect→frequency→readback 步骤；温控门、容量不足、高频低压/低带宽拒绝，回读成功才提交 | 纯规划，无消费者、不读写寄存器 |

没有 CPU 电压/互连/温控写路径：EPSS 投票（`K60CpuFreqProbe.cpp` mode 2/3）
只写 EPSS 的 `PERF_STATE`/L3 `VOTE` 寄存器，**不经过 RPMh，也不改 lcx/lmx**；
GPU 规划不写 HFI；温控驱动不存在（`drivers/PongPower` 里的 thermal 命中都只是电池温度字段）。
2026-11-19 新增的 `K60RailPlan` 只生成顺序步骤和回滚状态，仍不读写任何寄存器。

## 3. 顺序约束（未来实现必须遵守）

1. **先读状态**：目标 LUT、当前 level、enable、TCS idle、当前电压/互连档位。读失败就停，
   不猜默认值。
2. **温控先行**：抬频前检查温度/电流余量；没有温控输入时只能保持当前档，不能主动升档。
   降频不依赖温控。
3. **稳压器先于频率**：先投目标电压（或确认已在目标档），再请求更高频率；降频时反过来，
   先降频再降电压。
4. **互连先于频率**：带宽/NoC 档位先于 CPU/GPU 频率请求；释放时先停 DMA、屏蔽中断，
   再撤互连和电压投票（`K60PowerVotePlan` 的三步顺序）。
5. **最后才是状态回读和日志**：读回实际 level/电压/带宽，与请求不一致按失败处理。
6. **失败回滚**：任何一步失败都退回上一个已确认档位，不能留下「高频低压」中间态。

以上 1–6 已落成纯 C 模型：`k60_rail_plan()` 以 `confirmed` 为起点，升档且 `thermal_ok=0`
返回 -2；容量不足返回 -3（`count` 保持 0）；参数非法或升频却降低电压/带宽返回 -4。
升档顺序 regulator→interconnect→frequency→readback，降档顺序
frequency→interconnect→regulator→readback；同频只改电压/带宽时先执行抬升、再按反向执行
下降；`k60_rail_commit()` 只在回读成功时前移已确认点。

## 4. 与 HR-01 的关系

HR-01 只允许路线 A 的 TCS4 `lcx.lvl`/`lmx.lvl` 两条命令；0x17a00000 绝对禁止；
其它 TCS 写和 `CONTROL_TRIGGER` 需要明确批准。因此：

- CPU/GPU 的电压或互连投票**不能**复用触摸 IOVDD 的 DRV2/TCS3 事务；
- 如果后续要做 CPU/GPU 电压投票，必须先由用户/Lead 扩大 HR-01 授权范围，并给出
  单次、只读/只写白名单和失败回滚方案；
- 在那之前，本分支只保留纯规划（EPSS/GPU/boost/vote/rail）和路线 A 的既有例外。

## 5. 结论

- §5 :108 的「稳压器 → 互连 → 温控」顺序目前**有纯顺序/回滚模型，没有完整写路径**：
  `K60RailPlan` 覆盖顺序、温控门、容量与回读提交（host 107 项），但真实投票仍只有 ADSP
  的 lcx/lmx 两条。
- 下一步只能在 HR-01 扩权后接真实消费者；纯逻辑模型和审计已经落地，不能新增寄存器写；
  真机验证仍被 m13517 暂缓。
- 温控是最大缺口：没有热区、没有温度到频率的闭环，也没有 GPU 频率上限。

## 6. 参考

- 官网快照：`E:/k60-work/scratch/power-page-20261117.txt:105-110`。
- HR-01：`docs/ops/HARD-RULES.md:24-72`。
- 路线 A 实测：`E:/k60-work/evidence/usblog-20261114-railh/console.log:477-479`。
- EPSS：`docs/research/power/01-EPSS-PROBE.md`；GPU：`04-GPU-FREQUENCY.md`；
  投票：`03-POWER-VOTES.md`；睡眠：`02-PLATFORM-SLEEP.md`。
