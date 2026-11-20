# 文档总索引（INDEX）

> 唯一文档入口。目标：新接手的人 5 分钟内知道**先读什么、文档在哪、哪些已过时**。
>
> 最后更新：2026-11-16。本索引由 `scripts/check-docs.py` 校验相对链接与登记覆盖；
> 该检查不证明硬件结论或上机门禁覆盖完整。
>
> **先读当前审计：[2026-11-16 重新审视](audits/REASSESSMENT-2026-11-16.md)**。记录 WiFi/BT 证据边界、ADSP 发布链保护缺口、同步 partial 结果与逐提交研判欠账。

---

## 0. 先读这五份

| 顺序 | 文档 | 为什么先读 |
|---|---|---|
| 1 | [`../README.md`](../README.md) / [`../README_EN.md`](../README_EN.md) | 设备身份、八步进度、仓库结构、构建入口 |
| `engineering/REPO-MAP.md` | **仓库与目录登记表**：三个组件仓库路径、构建副本、yibiya 镜像、打镜像该用哪个 DTB |
| 2 | [`engineering/STATUS.md`](engineering/STATUS.md) | 当前硬件状态明细与变更记录 |
- 2026-11-19 iOS 迁移边界（只保留可转移的活）：[IOS-SCOPE](engineering/IOS-SCOPE.md)
| 3 | [`engineering/EIGHT-STEP-SPEC.md`](engineering/EIGHT-STEP-SPEC.md) | 八步流程的完整定义（目的/必做/证据/通过条件/反模式） |
| 4 | [`engineering/HARD-RULES.md`](engineering/HARD-RULES.md) | 铁则 ★1–★37，从踩过的坑提炼的可执行规则 |
| 5 | [`engineering/PITFALLS.md`](engineering/PITFALLS.md) | 坑记录 P-01–P-276，每条含症状/根因/判据/教训 |

**要做触摸/GPU 之前，额外读：**
- [`research/EIGHT-STEPS.toml`](research/EIGHT-STEPS.toml) — 该硬件的八步证据，⑦ 未通过不得刷机
- [`research/SOURCES.toml`](research/SOURCES.toml) — 必须考察的参考源清单

---

## 1. 目录结构

```
docs/
├─ INDEX.md              本文件
├─ engineering/          ★ 核心工程文档（铁则、坑、硬件真值、八步规范、现状）
├─ research/             ★ 八步证据与研究清单（EIGHT-STEPS.toml / SOURCES.toml）
├─ state/                工作状态快照（会话指令、下一步、可信度台账）
├─ plans/                实施方案
├─ audits/               对比审计与诊断记录
├─ reference/            长期参考（决策、问题、USB、历史台账）
├─ ops/                  运行手册
└─ archive/              已过时/被取代的交接与旧索引
```

---

## 2. engineering/ —— 核心工程文档

| 文件 | 一句话摘要 |
|---|---|
| [`STATUS.md`](engineering/STATUS.md) | 当前硬件状态明细、重新审视结论与历史变更记录 |
| [`IOS27.md`](engineering/IOS27.md) | **iOS 27.0.1 线**：iPhone 16 Pro Max（iPhone17,2）、arm64e 4 KiB、xnu-12377 + Darwin 26、F0–F4 阶段门与 IPSW 哈希；`--os ios-27.0.1-24A446` 选择 |
| [`EIGHT-STEP-SPEC.md`](engineering/EIGHT-STEP-SPEC.md) | 八步流程规范：① 同型 ② 官方 ③ 反编译 ④ 广域 ⑤ 方案 ⑥ 深挖 ⑦ 核验 ⑧ 上机 |
| [`FIRMWARE-REBUILD.md`](engineering/FIRMWARE-REBUILD.md) | **固件卷重建手册**：谁在构建、为什么它不可复现、Mu_Basecore 必须停在记录的 pin 上（P-217）、现场四个卷、P-154 已关闭与下次重建的实验协议 |
| [`BOOT-PROCEDURE.md`](engineering/BOOT-PROCEDURE.md) | **启动流程唯一入口**（铁则 8）：门禁 → 先挂串口抓取 → `fastboot boot` → 判读"控制台没出现"=早启动挂死 |
| [`HARD-RULES.md`](engineering/HARD-RULES.md) | 铁则 ★1–★37，每条含来源、硬规则、判别方法 |
| [`PITFALLS.md`](engineering/PITFALLS.md) | 坑记录 P-01–P-276：症状 → 真因 → 判别 → 教训 |
| [`LINE-MAP.md`](engineering/LINE-MAP.md) | 逐行的“谁在做什么”地图：每条 bring-up 线对应的源码、补丁、证据与负责人 |
| [`GPU-IOSURFACE-ROOT-CAUSE.md`](engineering/GPU-IOSURFACE-ROOT-CAUSE.md) | GPU Metal 加速失败的根因：用户态按注册名找 `IOSurfaceRoot`，mini 实现注册成 `IOCoreSurfaceRoot` |
| [`TAGS.md`](engineering/TAGS.md) | tag 策略：只留 boot-proven、main 基线、版本里程碑三种 |
| [`PITFALL-TO-RULE-INDEX.md`](engineering/PITFALL-TO-RULE-INDEX.md) | 坑 → 铁则反查表 |
| [`TOOLBOX.md`](engineering/TOOLBOX.md) | 可复用工具与脚本清单 |
| [`PLAYBOOKS.md`](engineering/PLAYBOOKS.md) | 操作手册 PB-1–PB-10 |
| [`ANDROID-HW-TRUTH.md`](engineering/ANDROID-HW-TRUTH.md) | Android 实机实测的硬件真值（协议、寄存器、固件路径） |
| [`K60-TOUCH-DT-EVIDENCE.md`](engineering/K60-TOUCH-DT-EVIDENCE.md) | K60 触摸节点的 DT 权威数据 |
| [`K60-TOUCH-CHECKLIST.md`](engineering/K60-TOUCH-CHECKLIST.md) | 触摸八步核对清单 |
| [`TOUCH-STATEMACHINE.md`](engineering/TOUCH-STATEMACHINE.md) | 官方 Goodix 驱动状态机逐段提取（481 行） |
| [`ENVIRONMENT.md`](engineering/ENVIRONMENT.md) | 构建环境、工具链路径、SSH 主机 |
| [`LOCAL-ASSETS.md`](engineering/LOCAL-ASSETS.md) | 本地资源索引（参考仓库、固件、镜像） |
| [`REPO-INVENTORY.md`](engineering/REPO-INVENTORY.md) | 全部 git 仓库清单与用途 |
| [`DISK-HYGIENE.md`](engineering/DISK-HYGIENE.md) | 磁盘卫生：空间门禁判据、回收顺序、WSL 虚拟盘压缩（需管理员） |
| [`AGENT-BUS.md`](engineering/AGENT-BUS.md) | 协作通道：`scripts/k60-bus.py` 追加式消息总线、游标语义、与 reply md 的分工 |
| [`BRANCH-INVENTORY-20261119.md`](engineering/BRANCH-INVENTORY-20261119.md) | 分支全量盘点：49 条未合入分支逐条列出 ahead/behind、内容、证据、被谁包含与建议动作（用户逐条确认用） |
| [`PATCH-CATALOG.toml`](engineering/PATCH-CATALOG.toml) | **门禁数据源**：series 内每个补丁的用途与归属（`check-patch-series.py` 用它判“series 外的补丁未登记”） |
| [`COMPONENT-PINS.toml`](engineering/COMPONENT-PINS.toml) | **门禁数据源**：catalog 与本地工作树不一致的组件及理由（`check-component-pin.py`，hard-40） |
| [`DOC-CITATIONS-BASELINE.toml`](engineering/DOC-CITATIONS-BASELINE.toml) | **门禁数据源**：文档 `file:line` 引用的历史欠账基线（`check-doc-citations.py --update-baseline` 重生成） |
| [`README.md`](engineering/README.md) | 本目录的简介与阅读顺序 |

---

## 3. research/ —— 八步证据与研究清单

| 文件 | 说明 |
|---|---|
| [`EIGHT-STEPS.toml`](research/EIGHT-STEPS.toml) | **门禁数据源**：逐硬件的 ①~⑧ 证据、⑦ 三类核验、⑧ success/failure 预测 |
| [`SOURCES.toml`](research/SOURCES.toml) | **门禁数据源**：每个子系统必须考察的参考源，逐条填 `examined` + `finding` |
| [`LINE-RESEARCH-MAP.md`](research/LINE-RESEARCH-MAP.md) | 每条研究线当前查到哪一步、下一步出口判据是什么 |
| [`wifi/MHI-AMSS-PROTOCOL.md`](research/wifi/MHI-AMSS-PROTOCOL.md) | MHI/AMSS 协议逐字段拆解：为什么 c7/c8 停在 READY 而没有 AMSS 下载证据 |
| `01-same-hardware.md` | 触摸调研 ① 同型 |
| `02-official-docs.md` | 触摸调研 ② 官方 |
| `03-reverse-and-device-data.md` | 触摸调研 ③ 反编译/取证 |
| `13-STAGE-ONE-ROOT-CAUSE-MATRIX.md` | 触摸阶段一：根因候选与区分性测试矩阵 |
| `14-RETAINED-KO-INIT-AUDIT.md` | 留存 Goodix 模块：重定位感知的初始化调用链审计 |
| `04-device-data.md` | 触摸调研 ④ 设备数据 |
| `05-plan.md` | 触摸调研 ⑤ 方案 |
| `06-deep-dive.md` | 触摸调研 ⑥ 深挖 |
| `07-verification.md` | 触摸调研 ⑦ 核验 |
| `08-on-device.md` | 触摸调研 ⑧ 上机 |
| `09-CLOCK-FIX-PLAN.md` | GENI 时钟修复方案 |
| `10-SE-HANG-ROUND3.md` | SE 挂死第三轮诊断 |
| `wifi/RESEARCH.md` | **WiFi 八步 ①②③**：Pong 同 SoC 同芯片的 PCIe0 冷启动、PWF2 固件包、K60 本机真值 |
| `wifi/BOOT-DEATH-BISECT.md` | **WiFi series 死因考古（静态）**：0618 MHI 注入不存在、0011 stage 门与 229 series 均被对照排除，剩余差异与缺失的对照格子 |
| `wifi/BLOB-RESIDENCY.md` | **11.19 MB 固件 blob 与装载边界**：最窄余量 1.14×（117 MB 镜像 vs `ReadFile` 128 MB），可证伪判断、五格判别矩阵、全家族实测段表与 `z0` 上机判决（silent） |
| `wifi/BOOT-DEATH-SUSPECT.md` | **WiFi ⑧ 死因账本**：mhi3/mhi4 静默前无任何内核输出的证据、过期内核混淆项、四个嫌疑（__TEXT 11.2 MB 固件 blob / 窗口算术 / 退役 touch 探针 / `pong_wifi=1`）与逐个反证方法 |
| `wifi/T2-PATCH.md` | **WiFi T2 备胎补丁**：把 11.19 MB PWF2 容器从 `__TEXT,__const` 挪到 `__DATA,__const` 的一行 diff（已验证可正反向 apply）、t2 构建配方、飞行前三项离线校验 |
| `wifi/MSI-TOPOLOGY.md` | **WiFi 中断拓扑**：PCIe0 的三条 MSI 路径（PARF `MSI0`→SPI140/INTID172 实走、DT `msi-map` 指向 ITS 的 `0x5980`/`0x5981`、`pcie0_msi` 32 条 SPI 768..799 已 disabled）、为什么选 legacy、单 INTID 能看见与看不见什么、c5/c6 飞行证据 |
| `wifi/SBL-QUEUE.md` | **WiFi SBL 队列候选**：c7 的 `ee=0 exec_env=1` 与官方 `MhiBoot.c` 的 `BHI_EXECENV` 轮询/BHIe 路径、`pong_sbl_pushed` 一次锁、`wifi-20261118sbl-gated` 镜像身份与首飞失败记录 |
| `wifi/SBL-DIRECT.md` | **WiFi SBL 直接推送候选**：队列路径在 `mhi_sync_power_up` 超时后失效的复盘、同一 worker pass 直接调用 `mhi_download_amss_image` 的官方等价实现、`BHIE_TXVECSTATUS` 诊断与 `wifi-20261118sbl-direct` 判据 |
| `wifi/SBL-MISSION.md` | **WiFi SBL mission 轮询候选到可用网络**：直接 BHIe 后缓存 `ee=1` 导致 `mhi_sync_power_up` 超时；mission4 将 `ready_timeout_ms` 延到 60 s 并创建 IPCR 通道；mission8 首次 WPA2 关联；mission9 用 4 参数 `initWithTask` 修掉打开 IONetworkStack 的 panic；mission10 让 namer 找到服务；mission11 由原生 configd/IPConfiguration 取得 192.168.31.134 并验证 RX/TX，mission13 从头再飞一次：DHCP 192.168.31.227、in 23,397 / out 28,455、tcp443 in 22,315 / out 27,138，26/26 judge 通过（应用探针 job 未运行，记入 limits） |
| `wifi/DARWINBOOT-POOL.md` | **WiFi 死因收窄②**：DarwinBoot 三处内存节点（ReadFile 的 AllocatePool / AllocateWindow 4.5 GiB 连续窗口 / FreePool(Image)）逐行失败形态与打印、board.toml:235 与 5120 MiB arena 的窗口算术对账、一次上机分开 pool 通道的判据 + 固件打印提案 |
| `audio/RESEARCH.md` | **音频八步 ①②③**：Pong 的 ADSP PAS1 + AudioReach/PRM + WCD938x（约 107 KB）、官方无组件、K60 待测项 |
| `battery/RESEARCH.md` | **电池 ①②④**：ADSP GLINK 交接租约的四标志、解锁链、单位转换 |
| `bt/RESEARCH.md` | **蓝牙八步 ①②③**：QCA6490 走 GENI UART 的硬件真值、官方组件分工、与 iOS 27 用户态的对齐点 |
| `bt/HANDOFF.md` | **蓝牙线交接**：从 0516 到 0525 的每一步、每次飞行的判据与缺口、恢复时的第一步 |
| `bt/S4-SPEC.md` | **蓝牙 S4 规格与沿革**：传输层 ABI、电源节点、改速、官方启动参数，逐条带文件:行与产物哈希 |
| `bt/MARCONI-AOP-GAP.md` | **marconi-bt 的真实身份**：三个 AOP/SPU 控制通道驱动，不是 HCI 端点 |
| `plans/BT-USERLAND-COMPARE.md` | **用户态难度对比**：iOS 16 伪装路线与 iOS 27 重定位路线的估时与不可迁移性 |

| [`battery/HANDOFF-PUBLISH.md`](research/battery/HANDOFF-PUBLISH.md) | **ADSP 交接发布者**：早期钩子、持续所有权、只读live发现/104字节发布、通知资格与离线测试；平台adapter已接线，板级资源与停机证明仍缺 |
| [`battery/INTEGRATION-ORDER.md`](research/battery/INTEGRATION-ORDER.md) | **ADSP 交接集成时间轴**：六步与 IOKitBSDInit/电池/root 挂载的前后界限、默认关闭门控、零交接访问宿主断言和未来检查清单 |
| [`battery/PAS1-PROVIDER-CONTRACT.md`](research/battery/PAS1-PROVIDER-CONTRACT.md) | **PAS1 provider 契约**：acquire/revalidate/abort 参数、返回码、持续所有权及未就绪行为；真实 provider 仍为 battery/audio/charger 共享阻塞 |
| [`battery/CARRIER-BLOB-PLAN.md`](research/battery/CARRIER-BLOB-PLAN.md) | **ADSP 生产 blob 契约**：冻结顺序 K60A ABI、26文件/23,506,184字节、生成器/校验器与host断言要求；Lead负责build-strict/归档接线，完整platform adapter另见下文，板级ownership服务未安装 |
| [`battery/PAS1-PROVIDER-INSTALL.md`](research/battery/PAS1-PROVIDER-INSTALL.md) | **PAS1 平台安装**：完整回调/source/log矩阵、runtime安装点、native SCM/映射安全、31/34宿主场景；板级ownership/资源/stopped服务仍缺，硬件未验证 |
| `charger/01-SYMBOL-MAP.md` | **充电器 ③ 反编译**：`qti_battery_charger_main_m81.ko` 的 675 个符号、232 个函数、对外依赖只有 pmic_glink/power_supply/typec/debugfs/panel |
| `charger/02-GLINK-CONTRACT.md` | **充电器 GLINK 契约**：client `battery_charger`/id `0x800a`、16 B 头、opcode 表、四张 prop map；104 B handoff 只覆盖 L0；§10 钉死 ADSP 侧名字三元组寻址（无端口/GUID） |
| `charger/03-REVERSE.md` | **充电器关键路径**：probe/write/callback 跳转表/subsys-up/ship mode，逐条附 objdump 原始片段 |
| `charger/04-PROP-MAP.md` | **充电器属性映射**：四张 prop map 的 .rodata 偏移与 25/13/7/187 条目、wire prop_id 实为该域 map 的**下标**、与 `K60Battmgr.c` 字段表 18 项逐项交叉验证 |
| `power/LANE-CONFORMANCE.toml` | **逐条对齐官方页面**：24 行（adsp 5 / battery 7 / charger 1 / thermal 2 / power 9），每行引用页面上逐字存在的一句话、一条存在的证据、状态与理由；`scripts/check-lane-conformance.py` 核句子/证据/理由，`--render` 生成 `power/LANE-CONFORMANCE.md`；2026-11-20 结论 verified 19、partial 5 |
| `power/27-WORKORDER.md` | **27 侧待办（生成物）**：`python3 scripts/check-hw-contracts.py --workorder` 在指定的 27 检出上把契约表现算一遍，按 drift / moved / missing 三类列出每一行：本仓那一行的原文、27 侧的候选位置（按契约文本里的关键字找——`copy27` 的行号是我们这边的偏移，在 27 侧不可信）、以及该行要做什么；没有 27 检出时不生成条目。手改即红（P-259），27 树动过就要重新生成 |
| `charger/PROP-NUMBERS.toml` | **16 → 27 属性号对照**：18 行（12 个 IOKit 键、5 个字符串属性、1 张 wire 表），逐行给出两侧值、`file:line` 依据与三档结论（相同 / 不同且已知谁改 / 查不到）；`scripts/check-prop-numbers.py` 两侧各开一次文件核对，`--render` 生成 `charger/PROP-NUMBERS.md` |
| `charger/05-OPEN-QUESTIONS.md` | **充电器未决结案**：+0xc 不对称、`0x37` shutdown、`0x48` 未识别、type 1/2、`check_status_work` 四条请求、无线升级 0x40–0x44/0x51，附 bcdev 字段表 30 项 |
| `charger/06-SUBSCRIPTION-CONSTANT.md` | **订阅应答常量定值**：`K60_BATTERY_NOTIFY_REPLY_TYPE = 1` / `_BYTES = 16`，依据 ADSP opcode-0x04 handler `0x60155910` 逐指令 + 四字节锚点 + 全固件 30 处 `0x800a` 组包点穷举；含生成器/测试落点与交给 touch agent 的交接段 |
| `charger/07-DEVICE-CRITERIA.md` | **充电器 ⑧ 判据**：订阅成立（`subscription-ack=1/16` → `subscribed=1`）、四属性区间（3.3–5.0 V / 0.1–6 A / 1–100 % / 0–60 °C）、与 Android 同窗口（±60 mV、±150 mA 仅 \|I\|≥100 mA、±3 pp、±3 °C，ΔT≤10 s），每条附失败行原文 |
| `charger/10-POWER-DOC-CONFORMANCE.md` | **电池上报 §4 逐条对照**：协议五要素、单请求/超时、有效-失败位图、原始值→OS 换算、register/updateStatus、adapter、断链 stale；逐条挂 `K60Battmgr.c` / `K60Battery.cpp` 行号与 route-c 实测值，未闭项单列 |
| [`power/00-POWER-PAGE-CONFORMANCE.md`](research/power/00-POWER-PAGE-CONFORMANCE.md) | **整页 §1–§6 对照**：每节状态、证据与归属；§2/§3 委派音频分支，§4 电池测量约 85 %，§5 CPU/GPU 大部分已上机（约 82 %），触摸写回已上机，平台睡眠默认启动已上机（image z 到 SpringBoard），platform-sleep=1 已进 IOCPUSleepKernel 并完成 prepare/restore 与 timer 唤醒，但完整恢复挂死，§6 构建链通且 mode 5–8 已上机 |
| [`power/01-EPSS-PROBE.md`](research/power/01-EPSS-PROBE.md) | **CPU 频率 §5 起点**：现场 DTB 证明 EPSS 三窗口/4 字节 LUT/L3 dcvs 与 SM8550 参考一致，板级 CPU→domain 为 4/3/1；只读探针默认关闭（`k60_cpufreq=1`），纯算术 host 155 项断言；mode 5 只读采样、mode 6/7/8 写回均已上机（d0 双向），触摸 1 s 写回亦已于 image ab 上机，平台睡眠等待路径见 `power/02-PLATFORM-SLEEP.md` |
| [`power/02-PLATFORM-SLEEP.md`](research/power/02-PLATFORM-SLEEP.md) | **平台睡眠调研**：官网 §5 末段要求与 sheng `ShengSleep.cpp`/ArmCpu 挂起路径逐项对照；K60 现场 FDT 只有 PMK8350 电源键、无开盖传感器，TLMM 基址 `0x0f000000`、汇总中断同为 SPI 208；`ArmCpuSleep.h`/等待路径、XNU hook `0623` 与 timer-only 板级 hook 已实现（host 1038 + 73 项）；w9/w10 已进 IOCPUSleepKernel、prepare/restore 与 timer PPI 27 唤醒成立，但 w9 panic Spurious wakeup、w10 在 secondary `processor_start` 硬挂，完整恢复未过，iOS16 暂停；TLMM/PON 电源键路由、喂狗与背光触摸恢复仍缺 |
| [`power/03-POWER-VOTES.md`](research/power/03-POWER-VOTES.md) | **外设投票记账**：官网 §5 的所有权/引用计数要求做成 16 资源×32 owner 的纯逻辑（shared/exclusive、重复申请 -3、最后释放返回 1、stop-dma→mask-irq→drop-vote）；host 58 项；不写 RSC/TCS（HR-01），无消费者、未上机 |
| [`power/04-GPU-FREQUENCY.md`](research/power/04-GPU-FREQUENCY.md) | **GPU 调频 §5**：现场 13 档 OPP（900-220MHz）与 HFI 升序 wire index、XO 忙碌计数器与带宽表；GMU 忙碌计数器、16 ms governor 线程、HFI id 30 投票与提交预唤醒已实现（host 140 项）；image o/q 上机验证计数器与投票被接受，仍无负载驱动的升档闭环 |
| [`power/05-BOOST-RULES.md`](research/power/05-BOOST-RULES.md) | **触摸/帧/GPU 唤醒/fence 规则**：官网 :115-117 的 1 s 触摸保持、4 窗口 2 帧的 60 % CPU 下限、GPU 双倍/578 MHz/50 ms、1 ms fence 预算，host 40 项；触摸计数（补丁 0622）与 CP 环提交窗口已接线，CPU/GPU 线程已消费；image ab 07:18 触摸把 d0 写到 state=15->94、hw=1804800kHz，票数改每窗口、boost 覆盖全簇（43af2a5c），fence 仍无消费者 |
| [`power/06-FIRMWARE-MANIFEST.md`](research/power/06-FIRMWARE-MANIFEST.md) | **电源固件清单**：ADSP 26 段 + mdt 的完整 sha256、充电器 .ko、carrier FD/UEFI 输入；记录来源压缩包与缺失段 b24，声明整机清单与认证密钥仍无来源 |
| [`power/07-RAIL-ORDERING.md`](research/power/07-RAIL-ORDERING.md) | **稳压器/互连/温控顺序**：审计现有 TCS4 lcx/lmx、触摸 IOVDD TCS3、GPU 电源表与投票账本；给出读状态→温控→电压→互连→频率→回读的顺序和 HR-01 边界 |
| [`power/08-IOS27-POWER-PORT.md`](research/power/08-IOS27-POWER-PORT.md) | **iOS27 电源移植清单**：iOS16 平台睡眠停在完整恢复硬挂；列出八个纯 C 策略模块/十套 host 1915 项、K60 现场事实、catalog ArmCpu + sheng xnu-12377 补丁（927a458）的复用/重写矩阵、移植顺序与验收判据；八模块 freestanding portability preflight；`CARRY.toml` + `check-power-carry.py` 钉住 16 个文件哈希并可用 `--target` 比对 iOS27 检出，另钉住四个 console 判读器的哈希与夹具用例数（43 项测试）；`check-ios27-power-preflight.py` 把模块哈希、PONG report 门控、builder 路由、判读器与八份契约表是否随树带入合成一份 27 侧前置检查（52 项测试） |
| [`power/09-CHARGE-AUTH.md`](research/power/09-CHARGE-AUTH.md) | **充电认证移植**：官网 §4 :82-88 的 sheng `ShengChargeAuth.c` 状态机移植到 `K60ChargeAuth.c`（单电芯单电量计、适配器 SVID 0x2717/PDO2、18 诊断属性），host（仅状态机）99 项；已默认关闭地接入 `K60Battery` 串行队列与 HMAC-SHA256/`read_random` 回调，仅 property 7 值 6/7/8 启动；无 UCSI 数据角色、未上机 |
| [`power/10-THERMAL-MAP.md`](research/power/10-THERMAL-MAP.md) | **温控跳变点地图（纯模型）**：现场 FDT 的 82 个温区/18 个冷却设备与 9 个 AP 侧可行动温区、90000/95000/110000/115000/125000 阶梯、最坏读数聚合与 `allow_raise`/两个 throttle 的派生规则；host 125 项（含与 `K60RailPlan` 温控门的交叉断言）；不读传感器、不下发冷却动作，主动降温仍按方案 1 park |
| [`power/11-SHENG-REFERENCE.md`](research/power/11-SHENG-REFERENCE.md) | **sheng 参考源（铁则 12）**：可引用的检出（`references/UniXNU-sheng` @ bc05635，170 文件/3 目录）；24 个 xnu-12377 补丁里只有 3 个碰电源；与契约表的对应（7 行已被 sheng 解、3 行是同源移植不可当独立来源、其余无交集）；`CONFIG_XNU_OWNER_*` 不解释 27 侧缺行，缺行来自 stage-0 未链接电池/温控 archive |
| [`power/12-ARM64E-EVIDENCE.md`](research/power/12-ARM64E-EVIDENCE.md) | **arm64e 五条硬性要求的离线证据**：FEAT_PAuth 已实测（`ISAR1` APA=0b0101，探针判词是 gate bug）、4 KiB 只在 host/构建成立；EL1 五组密钥寄存器与每核 PACIA/AUTIA 未测（sheng 只是跨 SoC 机制旁证）；给出 P0-P4 最小探针判据（寄存器、期望值、失败形状），文档不含探针代码 |
| `display/RESEARCH.md` | **显示结论层（本板真值）**：面板 m11a 1440x3200 DSC cmd 单 DSI 三档 60·90·120、5 条供电轨、DSI `0xae94000` / PHY `0xae94400` / MDP `0xae00000`、XML 缺口与已转派的 owner |
| `storage/RESEARCH.md` | **存储结论层（本板真值）**：UFS PHY `0x1d80000` + `qcom,ufs-phy-qmp-v4-cape`、控制器 `0x1d84000` / ICE / HWKM、IRQ SPI 265、与 liuqin 的双源交叉验证 |
| `memory/RESEARCH.md` | **内存布局结论层（本板真值）**：DDR 保留区与寄存器窗口，以及跨板边界——DXE Heap `0xC7000000` 与 Kernel `0xBB000000` 绝不可跨板抄 |
| `springboard/RESEARCH.md` | **壁纸上机判读卡**：0618 K60WALL / v24dp boot view / F1 7410 提交三组日志原文 → 结论，含半成功形态 |
| `springboard/WALLPAPER-CHAIN.md` | **壁纸链完整取证**：OS 窗 /Library/Wallpaper 实存、两行 SKIP 在 mount 前、P-27/P-198、F1–F5 方案与 host 验证 |
| `springboard/APPEX-REGISTRATION.md` | **小组件 .appex 零 spawn 离线取证（收窄版）**：注册链角色盘点、LS/MobileInstallation 注册库缺失、C1–C4 取舍与上机判据 |
| `11-KEY-EVIDENCE-RING.md` | 关键证据闭环清单 |
| `GENI-ACCESS-PRECONDITIONS.md` | GENI 引擎可访问性前置条件 |
| [`ios-mondrian-traps.md`](research/ios-mondrian-traps.md) | **Same phone, second port**: 16 KiB granule, the 9 GiB window and its four rules, a pinned physmap seed, the splash FB alias, the 607-byte boot-args ceiling, SPMI PPID, and the slot a failed boot deactivates |
| [`REFERENCE-INDEX.md`](research/REFERENCE-INDEX.md) | **参考仓库事实索引（人读）**：42 个参考仓库逐条 文件:行 + 可信度，按供电/音频/WiFi/触摸/显示/GPU/存储/USB/电池分区；机器可读部分同源进 `SOURCES.toml` |

> 01–08 是早期按八步逐份写的调研，`EIGHT-STEPS.toml` 是它们的结构化汇总与门禁数据源。
> 两者冲突时以 `EIGHT-STEPS.toml` 为准。

---

## 4. state/ —— 工作状态快照

| 文件 | 说明 | 状态 |
|---|---|---|
| `state/SESSION-DIRECTIVES-2026-11-07.md` | 2026-11-07 会话的用户指令总账 | 参考 |
| `state/STATE-2026-11-07.md` | 2026-11-07 的当前真相快照 | **过时**，现以 `engineering/STATUS.md` 为准 |
| `engineering/BATTERY-INTEGRATION.md` | **电池栈编译集成**：构建脚本 4 处改动、defconfig 开关、宏链路、归档构建时机、无 PAS1 时的运行时行为 |
| `BOOT-ARGS.md` | **Boot 参数参考**：每个参数的接受值/默认/陷阱，608 字节预算，三个 GPU 开关的串行依赖 |
| `state/TRUST-LEDGER.md` | 数值可信度台账（T/E/C 分级） | 参考 |
| `state/NEXT-STEPS.md` | 当时的推进顺序 | **过时** |

---

## 5. plans/ —— 实施方案

| 文件 | 说明 |
|---|---|
| [`SHENGUFS-VERIFIED-TABLE-PORT.md`](plans/SHENGUFS-VERIFIED-TABLE-PORT.md) | 把 sheng 的已验证 UFS 根策略表搬进 PongUfs 的方案与出口判据 |
| `plans/GPU-ENABLE-PLAN.md` | Adreno 730 scanout 启用方案（47 KB，6 章节） |
| [`plans/BACKLOG.md`](plans/BACKLOG.md) | **白天待办**：上游追平（全动态查询）+ P0~P3 实现优先级 |
| [`plans/GPU-TODO.md`](plans/GPU-TODO.md) | **GPU/Metal 待办**：官方 AdrenoMetal 8 个性能提交、pong-metal 中间层 diff、内核侧对齐、缺失文件清单 |
| `plans/APPLY-PIPELINE.md` | 生成并写入 iOS 16 OS 窗口的完整流程 |
| `plans/K60-TOUCH-PARAMS.md` | K60 Goodix / GENI-SPI 触摸参数表 |
| `plans/120HZ-PORT-PLAN.md` | 120Hz 移植方案 |
| [`plans/WIFI-REBUILD-CHECKLIST.md`](plans/WIFI-REBUILD-CHECKLIST.md) | **WiFi 对照镜像重出核对清单**：从 origin/main 按 4.5 GiB 窗口重出，对照 mhi3/mhi4 逐字段；五条硬差异（0010 装配路径、series 224 vs 229、`.config` 开关、buttons 节点、freeze 盲区） |
| [`plans/WIFI6-WPA3-PLAN.md`](plans/WIFI6-WPA3-PLAN.md) | **Wi-Fi 6 / WPA3 方案**：HE 只发 HE Cap（HE Operation 由 AP 发）、先解析关联响应再触发 `BSS_CHANGED_ASSOC`；SAE 必须先迁控制面，再补 EC/BN provider，含 P0–P4 与证据清单 |
| 其余 | 见目录 |

---

## 6. audits/ —— 对比审计与诊断

| 文件 | 说明 |
|---|---|
| `audits/PONG16-DIFF-AUDIT.md` | 与 pong `ios16` 分支的机械差异审计 |
| `audits/FORK-REVIEW.md` | Fork 巡查与吸收记录 |
| `audits/REFERENCE-WALL-AUDIT-2026-11-02.md` | 对照 ios-sweet-k60 已验证墙的审计 |
| `audits/USERLAND-ROUTES-2026-11-02.md` | 三种 userland 路线对比 |
| [`audits/PORTING-GAP-AUDIT-2026-11-16.md`](audits/PORTING-GAP-AUDIT-2026-11-16.md) | 移植疏漏审计（2026-11-17 快照，G1–G8 + 逐条修正）：文档与门禁数据源之间的差距清单。**注意：本文的 P 编号是 2026-11-17 的编号空间，与当前 PITFALLS.md 不同号** |
| [`ops/README.md`](ops/README.md) | `docs/ops/` 是 2026-11-12 的上游快照，本文件说明它与 engineering/ 的关系（不是权威，别按它判定） |
| 其余 | 见目录 |

---

## 7. reference/ —— 长期参考

| 文件 | 说明 |
|---|---|
| `reference/DECISIONS.md` | 决策记录 SSOT（D-YYYYMMDD-NN） |
| `reference/ISSUES.md` | 问题台账 SSOT（I-YYYYMMDD-NN） |
| `reference/HISTORY-LEDGER.md` | commit 级历史台账 |
| `reference/USB-LOG-CHANNEL.md` | USB 内核日志通道调研 |
| 其余 | 见目录 |

---

## 8. archive/ —— 已归档

已过时或被取代的交接、旧索引与历史盘点，16 个文件。**不要作为当前依据。**

---

## 9. 仓库根部的关键文件

| 文件 | 说明 |
|---|---|
| [`../README.md`](../README.md) / [`../README_EN.md`](../README_EN.md) | 设备简介与八步进度（中英互链） |
| [`../CREDITS.md`](../CREDITS.md) | 贡献者与全部外部来源 |
| [`../porting.toml`](../porting.toml) | 14 个子系统的记录（官网设备页数据源） |
| [`../board.toml`](../board.toml) | 设备配置与组件选择 |
| [`../AGENTS.md`](../AGENTS.md) | 仓库级 agent 约定 |
| `research/SUBAGENT-DELIVERABLES.md` | **Subagent 交付物台账**：落库文件 + 产出断言 + 提交，门禁验证断言成立 |
| `engineering/DIVISION-OF-LABOR.md` | **上下游分工与仓库覆盖**：哪些跟踪、哪些 pick、为什么参考实现不能 pick |

---

## 10. 门禁与检查

```bash
python3 scripts/research-gate.py            # 研究完整性（SOURCES.toml）
python3 scripts/eight-step-gate.py --build  # 八步 ①~⑥
python3 scripts/eight-step-gate.py --flash  # 八步 ①~⑦ + ⑧ 预测
python3 scripts/porting-gate.py --quick     # porting.toml schema + README 表格一致性
python3 scripts/render-eight-step-table.py --check
```

四个门禁在 build / flash 前自动运行，任一失败即中止。
- 2026-11-18 GPU 帧路径成本定位、采样节奏教训（P-233）与时间单位缺陷（P-234）：[STATUS 摘要](engineering/STATUS.md) · [飞行卡 j](research/gpu/FLIGHT-CARD-20261118j.md) · [飞行卡 k](research/gpu/FLIGHT-CARD-20261118k.md) · [飞行卡 l](research/gpu/FLIGHT-CARD-20261118l.md)
- 2026-11-18 GPU 搬运形状对照：逐行比线性纹理慢 14.6 ms、`submit` 与形状无关（P-235）：[飞行卡 m](research/gpu/FLIGHT-CARD-20261118m.md)
- 2026-11-18 GPU 提交期维护归因（探针窗口的更正、双峰分布、P-237）：[飞行卡 n](research/gpu/FLIGHT-CARD-20261118n.md) · 正在飞的只读归因：[飞行卡 o](research/gpu/FLIGHT-CARD-20261118o.md)
- 2026-11-19 合并后第一次把 120 Hz 面板、12-bit 背光、电池与 wifi 与 GPU 放进同一张镜像：[飞行卡 a](research/gpu/FLIGHT-CARD-20261119a.md)
- 2026-11-19 `submit` 那 3.0 ms 到底是内核还是转译器：给一个从 11-18 起就没有读者的计数器装上读者 —— [飞行卡 e](research/gpu/FLIGHT-CARD-20261119e.md) · [STATUS](engineering/STATUS.md)
- 2026-11-19 证明 GPU SMMU 的 IO coherence，让每次提交不再清 93 MiB 导入帧（抄 zizhan 的探针，此前三处跳过判据是死代码）：[飞行卡 b](research/gpu/FLIGHT-CARD-20261119b.md)
- 2026-11-19 同一个 18.4 MB 拷进两个不同目标，用来分开「目标端慢」与「拷贝实现慢」：[飞行卡 d](research/gpu/FLIGHT-CARD-20261119d.md)
- 2026-11-19 让 surface 只报一个行距，验证 untile 与它 5.3 ms 能否一起消失：[飞行卡 f](research/gpu/FLIGHT-CARD-20261119f.md)
- 2026-11-19 帧拿到的映射地址是新的还是旧的：用来分开「保留映射能救 import」与「地址不是变量」：[飞行卡 i](research/gpu/FLIGHT-CARD-20261119i.md)
- 2026-11-19 保留映射（token/evict）的设计草案：如果 H1 成立要改哪几处、wire 48→56 B、以及验收判据：[KEPT-MAPPING](research/gpu/KEPT-MAPPING.md)
- 2026-11-19 GPU 负优化 A/B 第一半（行距默认改回 0）：[飞行卡 j](research/gpu/FLIGHT-CARD-20261119j.md)
- 2026-11-19 GPU 档位：把「启动投一次」改成可以在 GX 起来后重投（t970 z164）——[飞行卡 k](research/gpu/FLIGHT-CARD-20261119k.md)、[飞行卡 l](research/gpu/FLIGHT-CARD-20261119l.md)
