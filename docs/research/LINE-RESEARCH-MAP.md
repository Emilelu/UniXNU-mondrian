# 分支研究文件地图（LINE-RESEARCH-MAP）

> 最后更新 **2026-11-17 00:20；2026-11-17 05:45 复核**。生成命令见文末。
> 用途：回答「这条线的研究到底写在哪个检出的哪个分支」，以及「main 上看不到什么」。
> 这不是文档索引（那是 [docs/INDEX.md](../INDEX.md)），是**物理分布**索引。

## 0. 结论

- 2026-11-17 05:45 复核：main 的 `docs/research/` 有 **67 个 `.md`（80 个文件）**；16 个原有检出分支上合计 **108** 个不在 main 的文件：cellular 19、wifi 14、thermal 12、bt 11、audio-merge 9、usb 7、display 6、gates 6、adsp-handoff 5、audio 3、buttons 3、springboard 3、wifi-lead 3、gpu-user 2、ios-profile 1、UniXNU-zizhan 4。
- 另有 `k60-charger` 2 个、三个临时 wifi worktree（`k60-wifi-mhi-preload` 9、`k60-wifi-cache` 8、`k60-wifi-ipa` 8）共 25 个；全部检出合计 135 个分支研究文件。
- 两个检出的 wifi 研究重叠（`k60-wifi` 14 个、`k60-wifi-lead` 3 个，后者全部是前者的副本）；音频的 `AMPS.md`/`CODEC.md`/`SOUNDWIRE.md` 在 `k60-audio` 与 `k60-audio-merge` 各一份。
- **未登记在 `docs/engineering/TREE-OWNERS.toml` 的检出现有 6 个**：`UniXNU-zizhan`、`k60-audio-merge`、`k60-wifi-mhi-preload`、`k60-wifi-cache`、`k60-wifi-ipa`、`k60-pitfalls`。铁则 11 要求一个检出只有一个主人，未登记=无人负责。
- 下面 §2 的逐文件条目是 **2026-11-17 00:20 的 97 文件快照**；05:45 复核新增的 11 个文件（以及临时 worktree）尚未补条目，搬运前按当前树重建。

## 1. 结案搬运规则（建议）

1. 一条线**结案时整目录搬回 main**，而不是挑文件：研究之间的相互引用比单个文件重要。
2. 搬运前先在本表登记目标文件；搬完后删掉对应行。
3. 重复文件以**有主人的检出**为准（`k60-wifi` 而非 `k60-wifi-lead`；`k60-audio-merge` 若合并成功则以它为准）。
4. 未登记检出的主人先补 `TREE-OWNERS.toml` 再谈搬运。

## 2. 逐检出清单（2026-11-17 00:20 的 97 文件快照）

| 检出 | 分支 | HEAD | 主线研究文件数 |
|---|---|---|---|
| `UniXNU-zizhan` | `main` | `034a0b0` | 4 |
| `k60-adsp-handoff` | `feat/adsp-handoff-owner` | `161c4518` | 4 |
| `k60-audio` | `feat/audio-codec` | `5a8d8065` | 3 |
| `k60-audio-merge` | `feat/audio-merge` | `81801af0` | 6 |
| `k60-bt` | `feat/bt-research` | `ed93d189` | 10 |
| `k60-buttons` | `feat/buttons` | `71a067a2` | 3 |
| `k60-cellular` | `feat/cellular` | `7ee599e0` | 18 |
| `k60-display` | `feat/display` | `a322b587` | 6 |
| `k60-gates` | `feat/gpu-metal-hw` | `786e96f9` | 1 |
| `k60-gpu-user` | `feat/gpu-user` | `042de9d9` | 2 |
| `k60-ios-profile` | `feat/ios-profile` | `10deb6bb` | 1 |
| `k60-springboard` | `feat/springboard` | `9b8d78ad` | 3 |
| `k60-thermal` | `feat/thermal-tsens` | `c7b170b9` | 12 |
| `k60-usb` | `feat/usb-console` | `f5aa46de` | 7 |
| `k60-wifi` | `feat/wifi-bringup` | `136f95c2` | 14 |
| `k60-wifi-lead` | `feat/wifi-integration` | `b4dbb3a0` | 3 |

## UniXNU-zizhan（main @ 034a0b0）

- `UniXNU-zizhan:docs/research/2026-10-31-sibling-fps-survey.md` — 兄弟项目的帧率工作调研（2026-10-31，一手资料）
- `UniXNU-zizhan:docs/research/2026-11-02-sibling-gpu-update.md` — 兄弟项目 GPU 进展更新（2026-11-02，接 10-31 调研）
- `UniXNU-zizhan:docs/research/2026-11-04-sibling-hardware-survey.md` — 兄弟项目适配对照：GPU、Wi-Fi、内外屏（2026-11-04）
- `UniXNU-zizhan:docs/research/2026-11-07-device-reference-directions.md` — 从设备目录筛选的第一轮待验证方向

## k60-adsp-handoff（feat/adsp-handoff-owner @ 161c4518）

- `k60-adsp-handoff:docs/research/audio/ADSP-BRINGUP-PLAN-V2.md` — ADSP Bring-up Plan V2：QMP load_state、供电观测与后移发布
- `k60-adsp-handoff:docs/research/audio/ADSP-RAIL-INHERITANCE.md` — ADSP LCX/LMX 供电继承：四个问题的取证（round 33，2026-11-16）
- `k60-adsp-handoff:docs/research/audio/ADSP-RAIL-SAMPLER-AUDIT.md` — ADSP rail-only 采样器离线审计（2026-11-16）
- `k60-adsp-handoff:docs/research/audio/ADSP-RAIL-SAMPLER-DESIGN.md` — ADSP RSC Rail Sampler: Repair Design

## k60-audio（feat/audio-codec @ 5a8d8065）

- `k60-audio:docs/research/audio/AMPS.md` — 扬声器功放 — K60 (SM8475 / cape) 判定与纯 AP 只读路径
- `k60-audio:docs/research/audio/CODEC.md` — WCD938x codec — K60 (mondrian / SM8475 / cape) 事实与判定
- `k60-audio:docs/research/audio/SOUNDWIRE.md` — SoundWire / LPASS 宏 — K60 (SM8475 / cape) 寄存器级事实

## k60-audio-merge（feat/audio-merge @ 81801af0）

- `k60-audio-merge:docs/research/audio/AMPS.md` — 扬声器功放 — K60 (SM8475 / cape) 判定、纯 AP 只读路径与寄存器回放层
- `k60-audio-merge:docs/research/audio/CODEC.md` — WCD938x codec — K60 (mondrian / SM8475 / cape) 事实与判定
- `k60-audio-merge:docs/research/audio/GLINK-MULTISLOT.md` — GLINK 多槽：把音频通道接进同一个 QcomGlink 实例
- `k60-audio-merge:docs/research/audio/PAS1-AUDIO-REQUIREMENTS.md` — PAS1-AUDIO-REQUIREMENTS — 音频线对 PAS1 provider 的依赖、降级与仲裁
- `k60-audio-merge:docs/research/audio/SOUNDWIRE.md` — SoundWire / LPASS 宏 — K60 (SM8475 / cape) 寄存器级事实
- `k60-audio-merge:docs/research/audio/TDMS.md` — TDM — 扬声器的 PRI_TDM_RX_0 通路（预研）

## k60-bt（feat/bt-research @ ed93d189）

- `k60-bt:docs/research/bt/06-DEEP-DIVE.md` — 06 — Deep dive: the staged QCA6490 Bluetooth code, line by line
- `k60-bt:docs/research/bt/D8-NEXT.md` — d8 之后要证明什么（2026-11-16）
- `k60-bt:docs/research/bt/FIRMWARE.md` — K60 Bluetooth 固件实测（QCA6490，2026-11-14）
- `k60-bt:docs/research/bt/HANDOFF.md` — Handoff — K60 Bluetooth line (state at 2026-11-15)
- `k60-bt:docs/research/bt/MARCONI-AOP-GAP.md` — marconi / AOP：Pong 用户态蓝牙栈的缺口（2026-11-16）
- `k60-bt:docs/research/bt/RESEARCH.md` — K60 蓝牙研究报告（QCA6490，HCI over GENI UART → UART.SK）
- `k60-bt:docs/research/bt/S1-PROBE-SPEC.md` — S1 只读探针规格（k60bt_stage=1）
- `k60-bt:docs/research/bt/S2-SPEC.md` — S2 规格：把 F1 / F11 / F3 三个偏差修进 0500 后端
- `k60-bt:docs/research/bt/S3-SPEC.md` — S3 — 身份与发布：让 bluetoothd 看见「这台机器有蓝牙」
- `k60-bt:docs/research/bt/S4-SPEC.md` — S4 — 蓝牙固件随内核下发（kernel-embedded blob）

## k60-buttons（feat/buttons @ 71a067a2）

- `k60-buttons:docs/research/buttons/02-OFFICIAL.md` — 按键 ② 官方驱动文档与配套文件
- `k60-buttons:docs/research/buttons/03-REVERSE.md` — 按键 ③ 反编译资料 + 真机数据
- `k60-buttons:docs/research/buttons/04-WIDE.md` — 按键 ④ 广域参考（Reuse first）

## k60-cellular（feat/cellular @ 7ee599e0）

- `k60-cellular:docs/research/cellular/01-ANDROID-INVENTORY.md` — 01 — Android 侧 modem / QRTR / IPA 取证清单
- `k60-cellular:docs/research/cellular/02-DT-TRUTH.md` — 02 — DT 真相：modem / IPA / QRTR 在设备树里到底写了什么
- `k60-cellular:docs/research/cellular/03-SCOPE.md` — 03 — 范围判定：基带在本次移植里算不算"范围内"
- `k60-cellular:docs/research/cellular/04-DT-NODES.md` — 04 — 补 DT：四个 modem/IPA 节点的抄录、改写与零影响证明
- `k60-cellular:docs/research/cellular/05-MODEM-IMAGE.md` — 05 — modem 镜像段表与 L1 加载器（K60ModemImage）
- `k60-cellular:docs/research/cellular/06-MODEM-PAS.md` — 06 — modem PAS 握手与 boot-arg 门控（K60ModemPas / K60ModemBoot，L2）
- `k60-cellular:docs/research/cellular/07-QRTR-ENUMERATION.md` — 07 — QRTR 只读枚举：向 modem 的名字服务发一次 NEW_LOOKUP
- `k60-cellular:docs/research/cellular/08-QRTR-SERVICES.md` — QRTR 服务号清单（上机比对用）
- `k60-cellular:docs/research/cellular/09-QRTR-VERDICT-EXAMPLES.md` — QRTR 判决日志样例（上机对号入座）
- `k60-cellular:docs/research/cellular/10-ON-DEVICE.md` — 上机实测记录（cellular L3）
- `k60-cellular:docs/research/cellular/11-CARRIER.md` — modem 固件载体决策（L3 上机后，2026-11-15）
- `k60-cellular:docs/research/cellular/12-DXE-CONTRACT.md` — 12. modem 镜像的固件装载契约（2026-11-15）
- `k60-cellular:docs/research/cellular/13-FIRMWARE-ACCEPTANCE.md` — 13. 固件载具验收门禁（2026-11-15）
- `k60-cellular:docs/research/cellular/14-DXE-REQUEST.md` — 14 · 固件侧 modem 载具需求（DarwinBoot 库调用版）
- `k60-cellular:docs/research/cellular/15-FIRMWARE-CARRIER-LOADER.md` — 15 — 固件载具装载器实现规格（K60ModemImage）
- `k60-cellular:docs/research/cellular/16-FRAMEWORK-REQUEST.md` — 16 · 框架侧接口要求：ADT 占位与 MODEM/ 注入
- `k60-cellular:docs/research/cellular/17-OFFLINE-ACCEPTANCE-CHECKLIST.md` — 17 · 框架载具离线验收清单（框架已交付，待整链候选）
- `k60-cellular:docs/research/cellular/18-FAILURE-RECEIPT-MATRIX.md` — 18 · 离线验收前置条件与失败回执矩阵

## k60-display（feat/display @ a322b587）

- `k60-display:docs/research/display/08-on-device.md` — 显示 ⑧ 真机验证记录（背光发布层）
- `k60-display:docs/research/display/BACKBOARD-CRASH-FAMILIES.md` — backboardd 崩溃家族总表（A / B / C）
- `k60-display:docs/research/display/BRIGHTNESS-PLAN.md` — K60 亮度方案（BRIGHTNESS-PLAN）
- `k60-display:docs/research/display/HANDOFF-20261114.md` — 亮度线交接单（feat/display）
- `k60-display:docs/research/display/INT-236-CHAIN.md` — INT-236 连锁调查：backlight-control 打开时 backboardd 崩在哪里
- `k60-display:docs/research/display/STATS-INDEX.md` — 背光计数索引（native_backlight_stats / native_backlight_request）

## k60-gates（feat/gpu-metal-hw @ 786e96f9）

- `k60-gates:docs/research/gpu/FLIGHT-CARD-20261116.md` — 上机卡：GPU Metal 硬件加速 · `gpu-scanout2-20261116`

## k60-gpu-user（feat/gpu-user @ 042de9d9）

- `k60-gpu-user:docs/research/gpu-user/RESEARCH.md` — gpu-user 线研究记录：Metal 插件部署链
- `k60-gpu-user:docs/research/gpu/RESEARCH.md` — GPU 部署链研究：增量事实

## k60-ios-profile（feat/ios-profile @ 10deb6bb）

- `k60-ios-profile:docs/research/ios-profile/FEASIBILITY.md` — ios-profile/FEASIBILITY.md —— 换 iOS profile 的可行性（电话/短信/基带）

## k60-springboard（feat/springboard @ 9b8d78ad）

- `k60-springboard:docs/research/springboard/APPEX-REGISTRATION.md` — APPEX-REGISTRATION —— 桌面小组件 `.appex` 零 spawn 的离线取证（收窄版）
- `k60-springboard:docs/research/springboard/RESEARCH.md` — springboard/RESEARCH.md —— 壁纸 / 换壁纸后进不去系统 / 桌面小组件（K60 mondrian）
- `k60-springboard:docs/research/springboard/WALLPAPER-CHAIN.md` — WALLPAPER-CHAIN — 壁纸纯黑 / 换壁纸后进不去系统 / 桌面小组件加载不出来

## k60-thermal（feat/thermal-tsens @ c7b170b9）

- `k60-thermal:docs/research/thermal/01-SAME-HARDWARE.md` — 01 · 同型号硬件事实（Redmi K60 / mondrian / SM8475）
- `k60-thermal:docs/research/thermal/02-OFFICIAL-DOCS.md` — 02 · 官方依据（SM8475 / Qualcomm TSENS v2）
- `k60-thermal:docs/research/thermal/03-REVERSE.md` — 03 · 反编译 / 交叉取证：三组参考实现读 tsens 的方式
- `k60-thermal:docs/research/thermal/04-ANDROID-EVIDENCE.md` — 04 · Android 侧现场取证（K60 / mondrian / SM8475）
- `k60-thermal:docs/research/thermal/05-PRESSURE-LEVEL.md` — 05 · 热压等级（thermal pressure level）：从 32 个传感器到 macOS 的 mTPL
- `k60-thermal:docs/research/thermal/06-KEXT-SERVICE.md` — 06 · 内核侧：发布 mTPL 的 IOKit 服务
- `k60-thermal:docs/research/thermal/07-INTEGRATION.md` — 07 内核集成（已落地）
- `k60-thermal:docs/research/thermal/08-KERNEL-DRIVER.md` — 08 内核内建 tsens 驱动（patch 落地）
- `k60-thermal:docs/research/thermal/COOLING-DEVICES.md` — COOLING-DEVICES · 46 条 cooling-map 归类与三个没人实现的冷却设备
- `k60-thermal:docs/research/thermal/CRITERIA.toml` — 上机判据（thermal 线）—— 交给脚本读的那一版
- `k60-thermal:docs/research/thermal/LEVEL-MAP.md` — LEVEL-MAP · 154 个 DTS trip 怎么变成可发布的等级
- `k60-thermal:docs/research/thermal/TRIP-DESIGN.md` — TRIP-DESIGN · trip 阈值从哪来、板上有哪些 cooling device、XNU 侧该不该做执行器

## k60-usb（feat/usb-console @ f5aa46de）

- `k60-usb:docs/research/usb/08-on-device.md` — 08 上机判读矩阵与实测：usb-20261115c（mode 2 回归）与 usb-20261115d（mode 1 判 P1/P2）
- `k60-usb:docs/research/usb/EIGHT-STEPS-usb.fragment.md` — EIGHT-STEPS.toml `[hardware.usb]` 段（待 Lead 合并）
- `k60-usb:docs/research/usb/IMAGE-ARGS-usb.fragment.md` — 交给 gates 线合并：`k60_usbvend` 的镜像参数白名单 + BOOT-ARGS 行
- `k60-usb:docs/research/usb/IOUSBHOST-BINDING.md` — IOUSBHost 绑定路径（只读调研）
- `k60-usb:docs/research/usb/QMP-PHY.md` — QMP USB3/DP Combo PHY（ssphy@88e8000）主机侧可验证部分
- `k60-usb:docs/research/usb/RESEARCH.md` — USB 设备模式 / Type-C 八步调研
- `k60-usb:docs/research/usb/UCSI.md` — UCSI / Type-C 角色判定：主机侧可验证部分

## k60-wifi（feat/wifi-bringup @ 136f95c2）

- `k60-wifi:docs/research/wifi/BOOT-DEATH-SUSPECT.md` — Boot-death suspects: why the wifi images died before any console output
- `k60-wifi:docs/research/wifi/CANDIDATE-LIFETIME-AUDIT.md` — Candidate lifetime audit: MHI allocations and powered MMIO
- `k60-wifi:docs/research/wifi/DARWINBOOT-POOL.md` — DarwinBoot 内存三节点与「一次上机分开 pool 通道」的判据
- `k60-wifi:docs/research/wifi/FAILURE-SNAPSHOT-LIFETIME-AUDIT.md` — WiFi failure snapshot allocation and MMIO lifetime audit
- `k60-wifi:docs/research/wifi/FAILURE-SNAPSHOT-PROPOSAL.md` — Failure-reachable WiFi snapshot proposal
- `k60-wifi:docs/research/wifi/IMAGE-BOUND-WRAPPER-PROPOSAL.md` — Offline image-bound wrapper: advisory-only revalidation
- `k60-wifi:docs/research/wifi/LOCAL-VERIFICATION.md` — WiFi 本地验证（⑦）证据台账
- `k60-wifi:docs/research/wifi/MERGE-REQUEST.md` — WiFi 接线：需要 Lead 合并的改动
- `k60-wifi:docs/research/wifi/MHI-SESSION-DESIGN.md` — Offline MHI session admission design
- `k60-wifi:docs/research/wifi/MHI-STATE-MACHINE.md` — MHI state machine: c7 observations and the held c8 path
- `k60-wifi:docs/research/wifi/MSI-TOPOLOGY.md` — MSI topology: configured routes and the limits of c7 evidence
- `k60-wifi:docs/research/wifi/STAGE-BRINGUP.md` — WiFi staged bring-up: why the first boot left no console
- `k60-wifi:docs/research/wifi/T2-PATCH.md` — T2 patch: put the PWF2 firmware container in `__DATA` instead of `__TEXT`
- `k60-wifi:docs/research/wifi/WIFI-FLASH-GATE-PROPOSAL.md` — WiFi 显式 flash 门禁提案

## k60-wifi-lead（feat/wifi-integration @ b4dbb3a0）

- `k60-wifi-lead:docs/research/wifi/LOCAL-VERIFICATION.md` — WiFi 本地验证（⑦）证据台账
- `k60-wifi-lead:docs/research/wifi/MERGE-REQUEST.md` — WiFi 接线：需要 Lead 合并的改动
- `k60-wifi-lead:docs/research/wifi/STAGE-BRINGUP.md` — WiFi staged bring-up: why the first boot left no console

## 3. 生成与复核

```sh
# 数据：每个检出当前分支、HEAD、docs/research 中不在 main 的文件（97 个）
wsl -u root -e python3 /mnt/e/k60-work/scratch/refmine/linemap.py
# 标题：取每个文件第一个 `# ` 标题
wsl -u root -e python3 /mnt/e/k60-work/scratch/refmine/linemap2.py
```

复核方法：`git -C /mnt/e/hackios/<检出> rev-parse --short HEAD` 与表中 HEAD 比对；
若分支已推进而本表未更新，按上表口径重跑两条脚本即可。
