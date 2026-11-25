# ADSP rail-only 采样器离线审计（2026-11-16）

**结论：当前采样器不能作为 rail-only 上机候选，更不能授予供电或 SCM 权限。**

> 注：本文是 2026-11-16 的离线审计快照；2026-11-17 的 Route A 真机运行已通过 resources 并启动 ADSP，见 [ADSP-ROUTE-A.md](ADSP-ROUTE-A.md) 第 6 节。
审计对象为分支 `feat/adsp-handoff-owner` 的 `c2805ec5d2ac246077d969459fecec375014e0e0`。
生产 [resources_cb](../../../drivers/PongPower/K60AdspBoard.c#L241) 保持 `K60BoardUnsupported=-63`、
不置 resources；第一步源代码/宿主修复已被 Lead 16:32 验收，PAS/handoff 功能尚未验收。
本次仅核对来源、执行合成宿主反例、记录阻塞；没有改 driver、patch、启动参数或调用时序。

## 一、来源与适用范围

| 编号 | 一手来源与固定版本 | 本次取用；边界 |
| --- | --- | --- |
| X | [小米 K60 Android S：rpmh-rsc.c](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/soc/qcom/rpmh-rsc.c) | `mondrian-s-oss` 解析到 `989b27aa8391a2ede9b067b53877c4c3343955fe`；[提交说明](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/commit/989b27aa8391a2ede9b067b53877c4c3343955fe) 为 Redmi K60 Android S、Qualcomm `qcom-S-LA.VENDOR.1.0.r1-11900-r1.0.r1_00029.0`。对应本板 downstream 五类 TCS 模型；不是本次 XNU 运行状态。 |
| XT | [小米 TCS 类型](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/include/dt-bindings/soc/qcom%2Crpmh-rsc.h#L9-L13)、[内部类型数](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/soc/qcom/rpmh-internal.h#L14-L18) | sleep=0、wake=1、active=2、control=3、fast=4，`TCS_TYPE_NR=5` 是类型数，不能当 slot 数。 |
| U | [Linux 固定提交寄存器表](https://github.com/gregkh/linux/blob/458c6079fc1d41d564c37679c8ace02cd83ee817/drivers/soc/qcom/rpmh-rsc.c#L157-L204) | 固定 `458c6079fc1d41d564c37679c8ace02cd83ee817`；v2.7/v3.0 布局交叉核验。不可拿另一 SoC 的 DRV 窗口替换本板 DT。 |
| A | [Linux v6.1 rpmhpd.c](https://github.com/torvalds/linux/blob/v6.1/drivers/soc/qcom/rpmhpd.c#L450-L486) | ARC 发送的是 corner；active/sleep/wake 请求时机不同。[609–635](https://github.com/torvalds/linux/blob/v6.1/drivers/soc/qcom/rpmhpd.c#L609-L635) 为 ARC hlvl→vlvl 辅助表；不是 mV 实测。 |
| D | [Linux v6.1 cmd-db.c](https://github.com/torvalds/linux/blob/v6.1/drivers/soc/qcom/cmd-db.c#L177-L196) | 按资源名返回命令地址；不返回聚合或实际轨状态。[230–241](https://github.com/torvalds/linux/blob/v6.1/drivers/soc/qcom/cmd-db.c#L230-L241) 为命令地址内的 slave-id 解析。 |
| B | [本板导出 DTS](E:/iOS Port/Work/scratch/dtb/mondrian.dts#L5119-L5130) | RSC 的 named windows、逻辑 drv-id、TCS 偏移和配置；必须和同一次采样的 version/caps 分开记录。 |

以上远端原文均通过固定地址读取成功（HTTP 200、完整内容）。GPL 来源仅用于寄存器事实与语义核验，
未移植其实现。当前实现与内嵌副本的问题属于本仓库代码，不以 Linux 有此接口推导 XNU 已满足条件。

## 二、DRV-2 几何与字段矩阵

本板 DTS 给出四个各 `0x10000` 的窗口，依次为 `drv-0=0x17a00000`、`drv-1=0x17a10000`、
`drv-2=0x17a20000`、`drv-3=0x17a30000`；`qcom,drv-id=2`，`qcom,tcs-offset=0xd00`。
X [1237–1251](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/soc/qcom/rpmh-rsc.c#L1237-L1251)
先取逻辑 id，再查名为 drv-N 的 resource。因此本板的物理窗口与 caps 字段移位各有依据；
历史日志把 `0x20700` 标为 drv_id，实际它是版本字（2.7），不是逻辑 id 2。

| 项 | 来源支持的含义 | 当前实现/具体阻塞 |
| --- | --- | --- |
| caps | X:49–54、1125–1132：selected base+`0x0c`；`max_tcs=(caps>>(6*logical_drv_id))&0x3f`，`ncpt=(caps>>27)&0x1f`。本板逻辑 id=2，shift=12。 | 当前不读 caps、不保存 ncpt；固定 `K60_RAIL_SLOTS=5` 没有几何依据。 |
| DT 分组 | X:1154–1175 按 DT 顺序分配，零数量/control 不占槽；本板 `<2 3 0 2 1 2 3 0 4 1>` 推得 active0–2、sleep3–4、wake5–6、fast7。 | 这是配置模型，不是正在执行哪个请求的证明；当前 0–4 漏 wake/fast。不能用 upstream 四类解析器解释该 downstream 五类表。 |
| 步长 | X:41–42：TCS=672(0x2a0)、command=20(0x14)；U:v3 command=24(0x18)。 | `cmd_stride` 已声明却未用于扫描，所有 slot 只读 command0。 |
| TCS_STATUS | v2 +0x18、v3 +0x28；X:70 注释 zero if busy，X:779–795 按整个值 zero/nonzero 打印 BUSY/IDLE。 | 当前 `(status & 1) != 0` 缺乏该来源支撑；不能以 TCS idle 代替 command completion。原始值应保留。 |
| CMD_STATUS | v2 +0x3c、v3 +0x40；X:79–93、800–810：issued bit8、complete bit16。 | 当前 layout/record 没有此字段；+0x18 与 +0x3c 不是同一状态。完成语义还须结合响应请求，不能无条件要求或推导电源已好。 |
| CMD_ENABLE | v2 +0x1c、v3 +0x2c，一 command 一 bit；X:491–512。 | 当前忽略 enable；禁用的非零残留也可 `valid=1`。 |
| CMD_MSGID | v2 +0x30、v3 +0x34；X:89–93、483–499：length=8，write bit16，response-request bit8；等待请求可设 response-request。 | 当前不读；请求响应的 bit 不是已收到 ACK 的证据。 |
| ADDR/DATA | v2 +0x34/+0x38，v3 +0x38/+0x3c；完整地址还需 slot×tcs_stride + command×cmd_stride。 | 当前首个地址命中即返回，重复/冲突记录丢失；记录缺 command index。软件 `complete` 不是硬件完成位。 |
| 访问范围 | caps、DT 配置、映射 bounds、实际访问许可是四种约束，应取经审查的合法交集。 | 当前未证明每个拟读槽/command 可访问；本文不授权把扫描扩成 8×16。未知许可必须阻断，不能猜数值。 |

[历史 touch 日志](E:/iOS Port/Work/evidence/usblog-20261110-191312/console.log#L627) 曾报
`caps=0x800c8104 count=8 ncpt=16 ver=0x20700`；用上述字段算术确实得到 8/16。
但 [railh 日志](E:/iOS Port/Work/evidence/usblog-20261114-railh/console.log#L477-L479) 只有 cmd-db magic、
ldoc2、版本/布局三行，没有同次 caps 或 LCX/LMX 记录。不得拼成一份同 boot 快照。
假设已批准的 v2 8×16 窗口，最后 CMD_STATUS 偏移算术为 `0xd00+7*672+15*20+0x3c=0x20c8`；
end=`0x20cc` 小于映射长度，只说明 bounds 算术，不说明该地址可访问。
未来需检查整数乘加、对齐、每字段 end≤长度、受支持版本/数量、DT 分组总数与 caps 一致；
中断扫描、截短窗口、未知版本/权限须记录为 coverage incomplete，不能报 rail absent。

## 三、每种观测究竟证明到哪一级

| 观测 | 可报告 | 不能报告 |
| --- | --- | --- |
| map 返回非零 | 虚拟映射调用成功 | 所有映射页/寄存器均可安全读；轨有电 |
| 某地址实际 load 返回版本/caps | 该次、该地址可读到原始值及其布局候选 | 整个窗口所有槽可访问；所有请求归本 owner |
| cmd-db 按名命中 | LCX/LMX 的命令地址/元数据 | 该轨当前被投票、聚合值或 PMIC 生效值 |
| ADDR 命中、DATA 非零 | 该 slot+command 留有某值的请求记录 | 已触发、已接受、当前 active 状态、持续供电 |
| enable/msgid/issued/complete | 命令启用、格式及事务状态的原始留痕；解释须注明类型和来源 | AOP 全部投票者当前聚合、ARC/PMIC 生效、handoff 后继续存活 |
| 软件 complete/valid/Inherited | 旧 helper 的分支结果 | 硬件完成、供电继承、ResourcesHeld、SCM 权限 |

X [470–477](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/soc/qcom/rpmh-rsc.c#L470-L477)
明确该函数只把请求写入 TCS buffer、不触发，且用于 active/sleep/wake。
X [244–257](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/soc/qcom/rpmh-rsc.c#L244-L257)
清 enable/wait 时不清 ADDR/DATA，所以非零残留可在失效后存在。
A:479–486 又区分立即生效的 ACTIVE_ONLY 与未来 sleep/wake 应用的请求。
LCX/LMX DATA 必须标注 ARC corner/level index，不作毫伏，也不调用 mV 意义的 level_index 转换。
本次没有找到并验证本板 AOP 聚合/ARC 生效状态的合法观察契约，此项仍是功能阻塞。

## 四、真实入口图与四条件审计

```text
successful Data mount -> k60_data_mounted=1
  -> 0614/0619 late hook
     -> startup_claim(2) succeeds ? legacy probe_from_handoff : excluded
        -> pong_adsp nonzero -> bring_up -> rail_inherit -> rail_pass
     -> pong_rail_probe nonzero -> rail_probe
```

依据：[0614](../../../patches/xnu/0614-k60-adsp-call-site.patch#L8)、
[0619](../../../patches/xnu/0619-k60-adsp-glink-handoff.patch#L343)、
[legacy gate](../../../patches/xnu/0613-k60-adsp-pas.patch#L208)。实际晚期调用点先 legacy 后独立 probe；
两者并不共享 attempted 门。known caller 排序不能证明 public entry 对未来/直接调用有保护。

| 条件 | 当前入口行为 | 判定 |
| --- | --- | --- |
| Data==1 | 已知 late hook 在成功 Data mount 后；两个 rail entry 都不查 Data。 | 仅调用点有序，入口自身不闭合。 |
| 显式参数==1 | late wrapper 与 inherit cache miss 只要求非零；probe 无内部检查；cache hit inherit 不解析参数。 | 不是统一严格 opt-in。 |
| 只读 | rail 源码是 loads，无 TCS/trigger store。 | 源码层只读；不推导全部地址许可，不授权新访问。 |
| 一次 attempt | 只有事后 recorded ledger；map 失败无记录。probe 在 cache 判断之前 map/read。 | 不满足，失败与从未尝试混同。 |

[K60PmicRail.c:357–377](../../../drivers/PongPower/K60PmicRail.c#L357) 的任一 map 失败都不 store；
[inherit:395–414](../../../drivers/PongPower/K60PmicRail.c#L395) 无 ledger 会重试。
[probe:444–524](../../../drivers/PongPower/K60PmicRail.c#L444) 已 map cmd-db/DRV 并读取诊断，
到 [:529](../../../drivers/PongPower/K60PmicRail.c#L529) 才查 cache；已有结果也不能避免重读。
`w[0]` 在 519/522/523 多次 load，无 cache 时 530 再读；它们不是一次原子快照。
probe 的独立 diagnostic walk 在 476–497 使用数据库 offsets/counts/aux，没有逐次 fits 校验；
某个 ldoc2 lookup 成功不等于其余 entries 都合法。
header 的“single-shot/only prints”与实现不符。内嵌 0613 rail 源与 canonical 仅 include 名不同，缺陷同步存在。

legacy 中 [inherit:416–422](../../../drivers/PongPower/K60PmicRail.c#L416) 的 Inherited 仍返回 0，
继而 [bring_up](../../../patches/xnu/0613-k60-adsp-pas.patch#L223) 可 copy/SCM；旧门保留不表示它安全。
本轮不启用 pong_adsp/pong_handoff_publish。生产 owner 独立经过 resources=-63，拒绝修复保持不动。
[ops HR-01](../../ops/HARD-RULES.md#L46) 的 Data/opt-in/只读/单次约束适用；
工程历史文档所说可写不能扩大本轮授权，两个 HARD-RULES 文件均未改动。

## 五、执行过的宿主反例

两个 harness 均直接链接当前 canonical 源，使用合成内存；无物理内存访问。
断言刻画并复现“当前行为”，退出 0 表示反例复现成功，**不表示合规通过或驱动已修好**。

### 5.1 helper：9 个案例

源码 [helper-audit.c](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/helper/helper-audit.c)、
执行命令 [run.sh](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/helper/run.sh)、
[原始结果](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/helper/results.log)。
编译 C11/O1/Wall/Wextra/Werror；每例重置合成数组，检查数组字节未变。

| 案例 | 当前结果 | 说明 |
| --- | --- | --- |
| command0 正对照 | complete=1 valid=1 | 仅夹具分支对照。 |
| slot5 唯一匹配 | Missing | 0–4 扫描漏 slot5。 |
| v2 command1 唯一匹配 | Missing | 漏非首 command。 |
| v3 command1 唯一匹配 | Missing | stride 变化没有补全扫描。 |
| enable=0 的非零残留 | valid=1 | 没有启用状态判据。 |
| msgid=0、CMD_STATUS=0 | valid=1 | 命令格式/事务状态被忽略。 |
| TCS_STATUS=2 | valid=0，not idle | 与来源的 whole-value nonzero 打印不同；不是声称硬件一定产生 2。 |
| 首匹配 DATA=0、后匹配=16 | 首个 invalid 立即返回 | 后续矛盾请求丢失。 |
| 截短窗口、真实匹配在后面 | Missing | coverage incomplete 与完整未命中未区分。 |

结果为 `AUDIT REPRODUCED 9/9 ... failures=0`；日志 10 行/1277 B，
SHA256 `1e1bca11ae9a340de7ff1ac4c9e5222b4271189cbbe4caace7a153498bf2de89`。

### 5.2 KERNEL entry：10 个独立进程

源码 [entry-audit.c](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/entry/entry-audit.c)、
[runner](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/entry/run-entry-audit.sh)、
[完整方法](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/entry/AUDIT.md)、
[运行汇总](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/entry/run.log)、
[校验清单](E:/iOS Port/Work/artifacts/adsp-board-20261116/rail-audit/entry/artifact-sha256.txt)。
GCC13.3.0，C11/O0/Wall/Wextra/Werror/`KERNEL=1`，fake pexpert/machine/sys 头与 map/parse stub；
没有 PAS/SCM 链接。每个案例新 exec，先断言原 static ledger 为空；cache 案例再显式 seed。
计数为真实 map/parser stub 调用，**没有对 volatile loads 逐条插桩，不宣称读取次数**。

| 案例 | cmd-db map | DRV map | parse | 当前结果 |
| --- | ---: | ---: | ---: | --- |
| inherit DB map 失败两次 | 2 | 0 | 2 | 两次 -63，无 ledger，失败重试。 |
| inherit DRV map 失败两次 | 2 | 2 | 2 | 两次 -63，失败重试。 |
| inherit 失败→probe | 2 | 0 | 1 | 第二入口再次尝试。 |
| seed ledger→probe | 1 | 1 | 0 | cache 不能防 remap。 |
| probe，Data0/arg off | 1 | 1 | 0 | 无入口门仍返回 0。 |
| cache inherit，Data0/arg off | 0 | 0 | 0 | 无条件查 cache 返回 0，不能作为授权。 |
| inherit，Data0/arg1 | 1 | 1 | 1 | 未查 Data。 |
| inherit，Data1/arg2 | 1 | 1 | 1 | 接受非零 2，非严格 1。 |
| inherit，arg off 负对照 | 0 | 0 | 1 | cache miss 的 off 门有效。 |
| inherit 成功→probe | 2 | 2 | 1 | 同 boot 两入口重复映射。 |

10 个进程全部 exit0、`PASS_EXPECTED_CURRENT_BEHAVIOR`；24 项 manifest 校验通过。
运行汇总 SHA256 `734aec89d5765c612f608a3d035bc95ba276e52fb342faa80f63733bd21f10b1`。
被测 C 的前后 SHA256 均为 `1a170aacba3d5a26ff48162794720da44451b4567588578c79d848cd5b86c504`；
H 均为 `cf72a5c9f7f6f46e5124b1bcf58f15e03be50834b5fee9057cdb7bc5d0c3d77b`。
这与 helper 测试一致；审计测试没有改被测源码。

## 六、唯一采样入口：待实现的契约

下图是修复设计约束，**不是已实现或已通过的测试结果**。

```text
UNATTEMPTED
  ineligible (Data!=1 / parse false / value!=1) -> refuse, no access
  eligible CAS winner -> ATTEMPTING, before first map
ATTEMPTING
  second caller -> busy/refuse, no map/read, no wait/poll
  every recoverable exit -> TERMINAL(result), including all failures
TERMINAL(result)
  every caller -> cached result/diagnostics; no map/read; never reset
```

一个入口供 probe/inherit 使用；attempted 与结果分开，先设保守失败，再执行受审查的读。
DB map 失败、DRV map 失败、parser/layout/bounds/permission 失败都永久消耗该次 attempt；
terminal cache 损坏也只报 corrupt，不重新采样。使用 acquire/release 发布不可变结果；重入不 spin。
所有诊断要在同一次有界 pass 收集，之后仅打印 cache；不能另有 raw dump 绕过入口。
cache 必须保留 recorder/gate/Data/物理窗口/逻辑 id/version/caps/覆盖范围/停止字段/原始值；
每条请求记录 slot+command index、类型、enable、msgid、TCS/CMD status、addr/data，保留多个匹配。
“完整请求观测”“覆盖不足”“字段不一致/失败”分开；均不等同“供电继承成立”。

未来实现后的验收轨迹至少包括：缺参/parse false 但输出1、0/2/-1、Data0→Data1、
两种 map 失败后跨入口重入、两个入口成功后复用、坏 magic/越界 aux、未知 layout、截短扫描、
duplicate/disabled/zero、claim 竞争与重入、terminal cache 损坏。断言 claim 早于首 map，
单 boot map/read attempt≤1，所有后续访问增加事件0，writes/SCM/resource-success=0。
本次 entry10 没有测试并发、原始 load 次数或未来状态机，不把这个契约算作已通过。

## 七、未闭合项与后续交付边界

| 阻塞 | 已有证据 | 仍需的结果 |
| --- | --- | --- |
| 扫描覆盖/许可 | 固定版模型、DT 分组、helper 反例 | 同次 version/caps 与被批准的 slot/command 范围；有界完整记录实现及离线验证。 |
| 一次 attempt | entry10 复现失败重试和 cache remap | 前置共享 claim、失败 terminal、所有诊断复用、事件计数验收。 |
| 原始快照语义 | enable/msgid/TCS/CMD status 有来源 | 状态变化/多条请求保留策略；不以重复读取制造完成等待或假称原子快照。 |
| 功能供电证据 | TCS 只证明请求留痕 | 本板可合法取得的 AOP 聚合/ARC 生效/retention 契约；当前未知，不猜地址或碰别的 DRV。 |
| legacy 授权 | 旧 Inherited 可放行 SCM | 后续方案必须切断“请求观测→供电授权”；当前两个功能参数保持关闭。 |
| late publisher | [startup claim](../../../drivers/PongPower/K60AdspStartup.c#L5) 一次 CAS；[Battery:421](../../../drivers/PongPower/K60Battery.cpp#L421) 在 property lookup 前已置 attempted。 | 另交 reservation→Data后执行→单次消费者通知的调用图/阶段表/host trace；不能只把 publish 搬晚或第二次 claim(1)。 |

late-owner 设计应保留 early owner1 reservation，late resume 消费同一 reservation/epoch，不重抢 startup；
legacy owner2 继续被排除。battery 需区分“等待依赖”与“已执行一次”，只在有效 lease commit 后通知一次，
失败不建服务，Poisoned/Published 继续保留所有权。此处只列下一份设计的验收项，未变更 0602/0614/0619。

生产拒绝的既有宿主证据见 [refusal log:27](E:/iOS Port/Work/artifacts/adsp-board-20261116/refusal/host-tests.log#L27)：
`map_smem=0 alloc=0 init=0 mem=0 load=0 auth=0 publish=0`；排他证明所需只读 map 不在该下游计数中。
本审计不把该证据写成 Native 执行或硬件验证。任何 rail-only 构建/启动仍须 Lead 新的具体裁决；
真实候选镜像的完整参数与字节数尚不存在，旧 592/593 B 估算不作证据。
