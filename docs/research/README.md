# 研究文档全量索引

本目录下每个 `.md` 都必须在本文件登记（`scripts/check-docs.py` 校验）。
按目录分组，标题取每份文件的一级标题；结论层摘要见 [`../INDEX.md`](../INDEX.md) §3。

## 根目录

| 文件 | 标题 |
|---|---|
| [`01-same-hardware.md`](01-same-hardware.md) | 触摸 ① 同型项目收集 |
| [`02-official-docs.md`](02-official-docs.md) | 触摸 ② 官方驱动文档与配套文件 |
| [`03-reverse-and-device-data.md`](03-reverse-and-device-data.md) | 触摸 ③ 反编译资料 + 真机数据 |
| [`04-device-data.md`](04-device-data.md) | 触摸 ④ 广域验证矩阵 |
| [`05-plan.md`](05-plan.md) | 触摸 ⑤ 方案（更新：K60 板级层已实现） |
| [`06-deep-dive.md`](06-deep-dive.md) | 触摸 ⑥ 深挖记录（3 轮） |
| [`07-verification.md`](07-verification.md) | 触摸 ⑦ 核验结论 |
| [`08-on-device.md`](08-on-device.md) | 触摸 ⑧ 真机验证记录 |
| [`09-CLOCK-FIX-PLAN.md`](09-CLOCK-FIX-PLAN.md) | K60 触摸时钟修复 —— 完整可行性确认方案 |
| [`10-SE-HANG-ROUND3.md`](10-SE-HANG-ROUND3.md) | K60 触摸 SE 挂死 —— 第 3 轮定位（2026-11-09 15:40） |
| [`11-KEY-EVIDENCE-RING.md`](11-KEY-EVIDENCE-RING.md) | 关键证据：clocks_on() 曾经成功执行过（2026-11-09 15:55） |
| [`GENI-ACCESS-PRECONDITIONS.md`](GENI-ACCESS-PRECONDITIONS.md) | GENI 访问前置条件缺失 —— 跨驱动统一根因（2026-11-09 17:10） |
| [`LINE-RESEARCH-MAP.md`](LINE-RESEARCH-MAP.md) | 分支研究文件地图（LINE-RESEARCH-MAP） |
| [`REFERENCE-INDEX.md`](REFERENCE-INDEX.md) | REFERENCE-INDEX.md —— 参考仓库事实索引 |
| [`SUBAGENT-DELIVERABLES.md`](SUBAGENT-DELIVERABLES.md) | Subagent 交付物台账 |

## audio/

| 文件 | 标题 |
|---|---|
| [`audio/ADSP-CARRIER.md`](audio/ADSP-CARRIER.md) | ADSP 固件载体决策（round 32，2026-11-13） |
| [`audio/ADSP-MD0.md`](audio/ADSP-MD0.md) | md0 的地址形态：设备写进来的是内核 VA，不是物理地址 |
| [`audio/ADSP-PAS1.md`](audio/ADSP-PAS1.md) | ADSP PAS1 — 参数与调用序列（实测记录） |
| [`audio/GAP-ANALYSIS.md`](audio/GAP-ANALYSIS.md) | 音频 / DSP 差距分析（SA-02） |
| [`audio/RESEARCH.md`](audio/RESEARCH.md) | 音频八步调研（① 同型 / ② 官方 / ③ 反编译） |
| [`audio/VENDOR-ADSP-NODE.md`](audio/VENDOR-ADSP-NODE.md) | 厂商 FDT 里的 ADSP/PAS 节点（官方来源，可直接抄） |

## battery/

| 文件 | 标题 |
|---|---|
| [`battery/CARRIER-BLOB-PLAN.md`](battery/CARRIER-BLOB-PLAN.md) | ADSP embedded carrier plan |
| [`battery/GLINK-HANDOFF.md`](battery/GLINK-HANDOFF.md) | K60 ADSP GLINK 交接契约（`k60-adsp-glink-handoff`） |
| [`battery/HANDOFF-PUBLISH-SPEC.md`](battery/HANDOFF-PUBLISH-SPEC.md) | 104 字节 `k60-adsp-glink-handoff` 发布规格 |
| [`battery/HANDOFF-PUBLISH.md`](battery/HANDOFF-PUBLISH.md) | K60 ADSP GLINK handoff publisher |
| [`battery/INTEGRATION-ORDER.md`](battery/INTEGRATION-ORDER.md) | ADSP handoff 集成顺序 |
| [`battery/PAS1-PROVIDER-CARRIER.md`](battery/PAS1-PROVIDER-CARRIER.md) | PAS1 image carrier decision |
| [`battery/PAS1-PROVIDER-CONTRACT.md`](battery/PAS1-PROVIDER-CONTRACT.md) | PAS1 provider 五阶段调用契约 |
| [`battery/PAS1-PROVIDER-INSTALL.md`](battery/PAS1-PROVIDER-INSTALL.md) | PAS1 platform provider installation |
| [`battery/PMIC-GLINK-SERVICE.md`](battery/PMIC-GLINK-SERVICE.md) | pmic_glink 服务层契约（L1） |
| [`battery/README.md`](battery/README.md) | 电池研究 |
| [`battery/RESEARCH.md`](battery/RESEARCH.md) | 电池 / 充电 八步调研（① 同型 / ② 官方 / ④ 广域） |

## charger/

| 文件 | 标题 |
|---|---|
| [`charger/01-SYMBOL-MAP.md`](charger/01-SYMBOL-MAP.md) | 01 · 符号地图 — qti_battery_charger_main_m81.ko |
| [`charger/02-GLINK-CONTRACT.md`](charger/02-GLINK-CONTRACT.md) | 02 · GLINK 契约 — .ko 期望的通道 / 服务 / opcode / 属性 |
| [`charger/03-REVERSE.md`](charger/03-REVERSE.md) | 03 · 关键路径反编译 — init / probe / write / callback / 状态机 / ship mode |
| [`charger/04-PROP-MAP.md`](charger/04-PROP-MAP.md) | 04 — prop 映射与 wire prop_id 语义（charger .ko 反编译） |
| [`charger/05-OPEN-QUESTIONS.md`](charger/05-OPEN-QUESTIONS.md) | 05 — 未决问题逐条结案（charger .ko 反编译） |
| [`charger/06-SUBSCRIPTION-CONSTANT.md`](charger/06-SUBSCRIPTION-CONSTANT.md) | 06 — 订阅应答常量定值（`K60_BATTERY_NOTIFY_REPLY_TYPE` / `K60_BATTERY_NOTIFY_REPLY_BYTES`） |
| [`charger/07-DEVICE-CRITERIA.md`](charger/07-DEVICE-CRITERIA.md) | 07 — ⑧ 真机验收判据（订阅 / 四属性 / Android 同窗口） |

## display/

| 文件 | 标题 |
|---|---|
| [`display/RESEARCH.md`](display/RESEARCH.md) | display/RESEARCH.md —— 显示 / 背光（K60 mondrian / SM8475） |

## evidence/

| 文件 | 标题 |
|---|---|
| [`evidence/README.md`](evidence/README.md) | 调研原始记录 |
| [`evidence/SA-BOOT-EVIDENCE-20261112.md`](evidence/SA-BOOT-EVIDENCE-20261112.md) | SA: boot evidence — the battery-enabled image reached SpringBoard, and touch stage 19 never ran |
| [`evidence/SA-CONFIG-CONSISTENCY.md`](evidence/SA-CONFIG-CONSISTENCY.md) | SA: defconfig / generated configuration consistency |
| [`evidence/SA-UPSTREAM-REVIEW-20261112.md`](evidence/SA-UPSTREAM-REVIEW-20261112.md) | SA-UPSTREAM-REVIEW-20261112 — K60（mondrian / SM8475 / taro）上游待合入提交审计 |

## memory/

| 文件 | 标题 |
|---|---|
| [`memory/RESEARCH.md`](memory/RESEARCH.md) | memory/RESEARCH.md —— 内存布局与跨板边界（K60 mondrian / SM8475） |

## storage/

| 文件 | 标题 |
|---|---|
| [`storage/RESEARCH.md`](storage/RESEARCH.md) | storage/RESEARCH.md —— 存储 / UFS（K60 mondrian / SM8475） |

## touch/

| 文件 | 标题 |
|---|---|
| [`touch/01-same-hardware.md`](touch/01-same-hardware.md) | 触摸 ① 同型项目收集 |
| [`touch/02-official-docs.md`](touch/02-official-docs.md) | 触摸 ② 官方驱动文档与配套文件 |
| [`touch/03-reverse-and-device-data.md`](touch/03-reverse-and-device-data.md) | 触摸 ③ 反编译资料 + 真机数据 |
| [`touch/04-device-data.md`](touch/04-device-data.md) | 触摸 ④ 广域验证矩阵 |
| [`touch/05-plan.md`](touch/05-plan.md) | 触摸 ⑤ 方案（更新：K60 板级层已实现） |
| [`touch/06-deep-dive.md`](touch/06-deep-dive.md) | 触摸 ⑥ 深挖记录（3 轮） |
| [`touch/07-verification.md`](touch/07-verification.md) | 触摸 ⑦ 核验结论 |
| [`touch/08-on-device.md`](touch/08-on-device.md) | 触摸 ⑧ 真机验证记录 |
| [`touch/09-CLOCK-FIX-PLAN.md`](touch/09-CLOCK-FIX-PLAN.md) | K60 触摸时钟修复 —— 完整可行性确认方案 |
| [`touch/10-SE-HANG-ROUND3.md`](touch/10-SE-HANG-ROUND3.md) | K60 触摸 SE 挂死 —— 第 3 轮定位（2026-11-09 15:40） |
| [`touch/11-KEY-EVIDENCE-RING.md`](touch/11-KEY-EVIDENCE-RING.md) | 关键证据：clocks_on() 曾经成功执行过（2026-11-09 15:55） |
| [`touch/12-FDT-PIN-TRUTH.md`](touch/12-FDT-PIN-TRUTH.md) | K60 触摸 FDT 真值（2026-11-09 19:50） |
| [`touch/13-PMIC-SPMI-PATH.md`](touch/13-PMIC-SPMI-PATH.md) | 触摸供电：SPMI 直写方案（绕过 RSC） |
| [`touch/GROUND-TRUTH.md`](touch/GROUND-TRUTH.md) | K60 touch ground truth (measured, not inferred) |
| [`touch/PLAN-20261113.md`](touch/PLAN-20261113.md) | K60 触摸计划 v17（Lead 侧欠账已清，可交触摸 agent 执行） |
| [`touch/POWER-RPMH-LDOC2.md`](touch/POWER-RPMH-LDOC2.md) | ldoc2 / pm8350c_l2：从 AP 侧点亮触摸 IOVDD 的完整契约 |

## wifi/

| 文件 | 标题 |
|---|---|
| [`wifi/BLOB-RESIDENCY.md`](wifi/BLOB-RESIDENCY.md) | WiFi 固件 blob 的 residency：11.19 MB `__TEXT,__const` 会不会撞上任何装载边界 |
| [`wifi/BOOT-DEATH-BISECT.md`](wifi/BOOT-DEATH-BISECT.md) | WiFi series 死因考古（BOOT-DEATH-BISECT） |
| [`wifi/FIRMWARE.md`](wifi/FIRMWARE.md) | qca6490 WiFi 固件清单 |
| [`wifi/GAP-ANALYSIS.md`](wifi/GAP-ANALYSIS.md) | WiFi 差距分析（SA-03） |
| [`wifi/MHI-AMSS-PROTOCOL.md`](wifi/MHI-AMSS-PROTOCOL.md) | MHI 固件下载：AMSS 那一次 BHIe 到底由谁触发（c8 之前的离线审查） |
| [`wifi/RESEARCH.md`](wifi/RESEARCH.md) | WiFi 八步调研（① 同型 / ② 官方 / ③ 反编译） |
