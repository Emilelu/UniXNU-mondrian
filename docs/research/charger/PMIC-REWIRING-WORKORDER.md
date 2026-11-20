# PMIC / 设备侧 27 改线工单

> 只写工单，不改代码、不改驱动、不写寄存器。每一行回答三件事：**现在读到什么**、
> **改完应该读到什么**、**失败时日志里出现哪些字**。飞行窗口只有一次，按行对照，
> 不凭“看起来像成功”。

## 0 三条边界

1. **电池/充电不走 AP 的 SPMI。** 27 的设备树里没有 SPMI 节点；`K60PmicRail.c:2-3`
   记录 AP 侧 SPMI 探测得到 `apid=-1`，`pm8350c_l2` 只能走 RPMh。把 SPMI 节点补进来
   不是“更直接”，而是换了一条没有证据的路径。
2. **pmic_glink 的服务端在 ADSP 固件里。** AP 侧只做 L0 通道（SMEM/GLINK/SMP2P）与
   L1 编解码；`PMIC_RTR_ADSP_APPS` 是这条通道的名字，不是 AP 的 SPMI 控制器。
3. **本工单不授权写 PMIC。** 任何寄存器写入、rail vote、充电使能都要等 ⑧ 的真机判据
   先过；这里只列“改什么”和“怎么判”。

## 1 改线项

| # | 改什么 | 当前读数（带出处） | 目标读数 | 失败字样（照 grep） | 判据 |
| --- | --- | --- | --- | --- | --- |
| P-01 | 不新增 AP SPMI 节点；电池/充电保持 pmic_glink，ldoc2 保持 RPMh | `dts/mondrian.dts` 无 `spmi`/`pm8350` 节点；`K60PmicRail.c:2-3` 写 AP 无 PPID 0x241 的 SPMI 通道（内核 SPMI probe `apid=-1`） | 0 个 AP SPMI 节点；battery/charger 只走 `PMIC_RTR_ADSP_APPS`；rail 只走 RPMh | `spmi`、`apid=-1`、`no PMIC channel` | 不改这条路径；出现 SPMI 访问即回退 |
| P-02 | 保留 27 设备树的 `remoteproc-adsp`/`glink-edge`/`pmic_glink`/`battery-charger` 四层节点，确认驱动真的去 probe | `dts/mondrian.dts:192-231` 已有 `qcom,cape-adsp-pas`、`remote-pid=2`、`mboxes=<&ipcc 3 0>`、`qcom,glink-channels="PMIC_RTR_ADSP_APPS"`、`qcom,protection-domain="tms/servreg","msm/adsp/charger_pd"`、`qcom,battery-charger` | 同一组节点不被删、不被第二套 channel 替代；`K60PmicGlink.cpp:84` 仍以 256/4 打开该 channel | `GLINK epoch never became ready`、`physical transport initialization rejected error=` | C1 的 channel up 行出现，且 sign 为 +1 或 -1 |
| P-03 | 确认 handoff 发布先于 battery 启动；不合成 104 字节 lease | `K60HandoffRuntime.cpp:81` 成功时打印 `K60Handoff: published authenticated PAS1 epoch=%u bytes=104 flags=15`；`K60Battery.cpp:656-660` 从 `/chosen` 读 `K60_ADSP_HANDOFF_PROPERTY` 并解析 lease | 同一条 published 行出现在 `K60Battery: ... channel up` 之前；`/chosen` 里是平台 PAS1 owner 发布的 104 字节 | `K60Battery: blocked rc=-4`、`K60ADSP owner stage=1 rc=-1000` | C0：先有 published，再有 channel up |
| P-04 | 订阅常量落到生成头：`(type,bytes)=(1,16)`；不要手写第二份 | `K60Battmgr.h:64-69` 说明 reply type/bytes 来自 ADSP opcode 4 handler；`K60Battery.cpp:442-444` 打印运行时值；27 侧尚无一份捕获能证明它是 1/16 | channel up 行 `subscription-ack=1/16`，随后 sample 行 `subscribed=1` | `subscription-ack=0/0`、`subscribed=0`、`errors=` 递增、ACK 被拒 | C1：ack 被接受，不能只看配置常量 |
| P-05 | wire 属性表保持 19 项，不改 index/map；四属性按原 map 读 | `WIRE-PROPS.toml` 19 项：Status 0/0x00、Present 2/0x03、Capacity 4/0x2e、Voltage 7/0x0c、Current 9/0x11、Temperature 13/0x33、UsbOnline OP_USB 0/0x04 | 同一组值与 27 侧生成器一致；C2 四属性各在区间：3300–5000 mV、100–6000 mA（绝对值）、1.00–100.00%、0.0–60.0 °C | `no publication sample`、`raw-current=`、`raw-temp=`、`sign=0` | C2：首帧四属性都在区间 |
| P-06 | ldoc2 只读继承账本先成立；需要 vote 时也只写 RPMh，不写 SPMI | `K60PmicRail.c:2-3` 说 rail 在 applications RSC 后、AP 无 SPMI；`K60PmicRail.h:16-19` 规定 `k60_rail_inherit()` 单次测量、`k60_rail_probe()` 只打印已有账本 | 账本 `complete=1` 且 `valid=1`；若后续要 vote，用账本里的 RPMh 地址与 level，不猜 mV | `rail never measured`、`incomplete`、`invalid`、`busy`、`cmd-db` 解析失败 | 账本不完整就不投；先读后写 |
| P-07 | 27 侧暂不引入 charge-auth 代码；先把 C1/C2 跑通 | 27 的 `drivers/PongPower/` 没有 `K60ChargeAuth.c`（16.6.1 侧有，默认 off）；27 设备树只有 `battery-charger` 子节点 | 先有 `subscription-ack=1/16` + `subscribed=1` + C2 四属性；再谈独立充电协议 | `charge refused`、`k60_charge_auth=0`、`auth` 相关拒绝 | C2 不过不接 charge-auth |
| P-08 | 设备侧取一组 Android 同窗口基线，作为 C3 的对照，不拿 Android 值当 iOS 结果 | `ANDROID-HW-TRUTH.md:68-77`：capacity 100、temp 358（35.8 °C）、status Charging、current_now 836 mA、voltage_now 4333 mV、USB CDP | iOS 同一窗口的容量/温度/电流/电压与充电状态；偏差 ≤ ±60 mV / ±150 mA / ±3 pp / ±3 °C，时刻差 ≤10 s，至少 3 对 | `mismatch`、`stale`、`no publication sample`、样本对不足 3 对 | C3：先配对，再算偏差 |

## 2 一次飞行的读法

按顺序读，前一项不过就不进入下一项：

1. **C0 lease**：`K60Handoff: published authenticated PAS1 epoch=` → `K60Battery: blocked rc=` 不出现。
2. **C1 订阅**：`actual PMIC_RTR_ADSP_APPS channel up; measured sign= subscription-ack=1/16`，
   且 10 s 内首帧 sample 行尾 `subscribed=1`。
3. **C2 四属性**：首帧 sample 的 voltage/current/SOC/temp 都在 §1 P-05 的区间。
4. **C3 对照**：至少 3 对 iOS/Android 同窗口样本，四条偏差都在阈值内。
5. **P-06 rail**：只在 C2 之后读账本；账本不完整时记录 `missing` 字段，不写 vote。

控制台过滤：

```sh
grep -E 'K60Handoff:|K60Battery:|K60ADSP|K60TRACE:' <console.log>
```

`K60Battery: blocked rc=-4` 是 **INVALID(no lease)**，不是电池失败；先回到 C0。
`subscription-ack=0/0` 是常量没进内核，不是 ADSP 拒绝；先查生成器/镜像，不要改协议。
`subscribed=0` 且 `errors=` 递增才是 ACK 被拒；按 `K60Battmgr.c` 的 type/bytes/result 白名单核对。

## 3 这张工单不做什么

- 不把 104 字节 handoff 改大；L0 与 L1 是两层，改大破坏已发布的解析器与消费方。
- 不在 AP 侧补 SPMI 控制器来“绕过”ADSP；那会把一条有固件服务端的路径换成无证据路径。
- 不在 C1/C2 未过时接 charge-auth、写 rail vote 或使能充电。
- 不把 Android 的 836 mA / 4333 mV / 35.8 °C 当成 iOS 的读数；它们只是 C3 的对照基线。

## 4 出处

- 设备树：`E:/hackios/xnekom-ios27/dts/mondrian.dts:187-232`。
- 通道/编码：`drivers/PongPower/K60PmicGlink.cpp:84`、`K60Battmgr.h:64-69`、`K60Battery.cpp:442-444,535`。
- 两层模型与两处缺口：`docs/research/battery/PMIC-GLINK-SERVICE.md:14-29`。
- 判据：`docs/research/charger/07-DEVICE-CRITERIA.md:8-17`；属性表：`docs/research/charger/WIRE-PROPS.toml`。
- rail：`K60PmicRail.c:2-3`、`K60PmicRail.h:16-19`。Android 基线：`docs/engineering/ANDROID-HW-TRUTH.md:68-77`。
