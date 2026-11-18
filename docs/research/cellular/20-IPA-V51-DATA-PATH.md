# 20 — K60 IPA v5.1 数据通路（IPA/GSI、QMAP、PDP）

- 日期：2026-11-18
- 状态：**研究完成；M0 编译骨架、M1 固件校验/暂存/PAS 15 路径、handoff 调用点、IP0 时钟投票、IPA5.1 资源表初始化、GSI 能力/所有权预检（M2 前置）、可宿主测试的 M2 GSI command-DMA 与 SMMU 规划模块，以及 M2 运行时 glue（1 MiB ring、0x8000 SMMU 表块、ArmSmmu4K 三区间页表、SID 0x5c0、SMEM item 497（TCSR SMEM mutex 0x1f43000 下分配/复用）、GSI MMIO/回调，pong_ipa=2 门控）已实现并通过 host tests 与内核编译验收（kernel af9b211f（EE0 后置语义修复 + ArmSmmu4K Device-nGnRE 支持 + SMMU IDR/context 诊断 + SMEM item 497 分配修复），k13 标准与 M2 诊断镜像）；固件加载区已按活 FDT 修正为 `memory-regions -> ipa_gsi_region@8b910000/0xa000`（metadata 仍在 `ipa_fw_region` 最后 8 KiB）；尚未上机，数据面未实现，K60 数据面仍为 ENETDOWN，不能声称可上网。**
- 范围：按 `E:/hackios/UniXNU/docs/zh/porting/baseband.md` 第 2、4 节，给出 K60（mondrian/SM8475）IPA v5.1 数据面的硬件事实、v4.2 复用边界、分阶段计划和首个离线测试。
- 结论：L1/L2 已有基础，L3 控制桥可枚举，**L4（IPA/GSI + QMAP mux + net TX/RX）数据面仍缺失，M0 只有编译骨架、M1 已有固件暂存/PAS 15 路径、payload FAT handoff 调用点与 IP0 时钟投票**；K60 不是 Coachz 的 v4.2 + PCIe/MHI 组合，不能直接套用 QcomBaseband 的 IPA 适配层。

路径缩写：`BASE = E:/hackios/UniXNU/docs/zh/porting/baseband.md`；`QB = E:/hackios/UniXNU/drivers/QcomBaseband`；`DIPA = E:/k60-work/vendor-src/kernel-sm8450-modules/qcom/opensource/dataipa/drivers/platform/msm`；`K60 = E:/hackios/k60-cellular/drivers/PongCellular`；`DTTRUTH = E:/hackios/k60-cellular/docs/research/cellular/02-DT-TRUTH.md`；`FDT = E:/k60-work/reports/live-6033dbec-fdt.dtb`（二进制 FDT，行号不适用）。

## 1. 官方四层要求与 K60 现状

`BASE:9-16` 把基带移植分为四层：

| 层 | 官方要求 | K60 现状 | L4 缺口 |
|---|---|---|---|
| L1 SoC/板级 | 电源、时钟、保留内存、固件启动、中断、DMA、EFS/NV | modem PAS 已按 `docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md` 推进；IPA 保留内存已在 DT；IPA 固件未加载，IPA 时钟/电源未证实 | IPA 的 power/clock/interconnect 资源尚未建模 |
| L2 控制桥 | QMUX 帧、QMI client 分配、服务发现/回复路由 | `K60ModemLink.c` 已接 GLINK/QRTR，能枚举 AppleBaseband；IPA 服务 0x31 未服务 | 缺 IPA QMI 服务端 |
| L3 iOS 接口 | 基带服务、channel、异步读写与启动交互 | `coachz_baseband_*` 控制桥和 PDP 控制对象存在 | 数据回调仍落到 ENETDOWN |
| L4 数据通路 | IPA/GSI、QMAP mux、系统 NIC TX/RX | **缺失（M0 骨架 + M1 固件校验/暂存/PAS 15 路径、handoff 调用点、IP0 时钟、IPA5.1 资源表初始化、GSI 能力/所有权预检、M2 host 模块（GSI command DMA、SMMU 规划）与 M2 运行时 glue（1 MiB ring、0x8000 SMMU 表、ArmSmmu4K、SMEM 497 在 TCSR mutex 下分配、GSI MMIO，pong_ipa=2 门控）；已进入内核编译并生成 k13 标准与 M2 诊断镜像，未上机，未验证真实 GSI/IRQ）** | 全部 |

L4 逐项状态：

- **IPA/GSI**：M0 只有常量与版本解码；M1 已落地 MDT 解析、ipa_fws 布局校验、`k60_ipa_firmware_stage()` 暂存、`k60_ipa_clock_vote()` 的 IP0 TCS4 投票、`k60_ipa_resources_prepare()` 的 IPA5.1 QMB/timer 与源/目的资源表初始化、`k60_ipa_gsi_check()` 的 GSI 能力/所有权预检（status/channels/events、command12/event0、EE0；PAS 前拒绝已启用的 foreign EE0，PAS 后 `k60_ipa_gsi_check_caps()` 则要求 EE0 已由 TZ 启用）和 `k60_ipa_firmware_start()` 的 PAS 15 顺序，并由 `k60_ipa_probe_from_handoff()` 从 payload FAT 的 `IPA/ipa_fws.mbn` 调用；M2 host 模块已提供 `K60IpaGsi.c` 的 GSI 3.0 command-DMA 状态机（EE0、event0/command12、ring 与 IPA5.1 表命令）和 `K60IpaSmmu.c` 的 SMMU 流规划/编程；M2 运行时已由 `k60_ipa_runtime_start()` 接入内核 MMIO/SMMU（`kmem_alloc_contig()` 分配 1 MiB ring 与 0x8000 表块、`ArmSmmu4KBuild()` 建三区间页表、SID 0x5c0、SMEM item 497（经 `k60_ipa_runtime_smem_item()` 在 TCSR SMEM mutex 0x1f43000 下分配或复用）、GSI 回调），但尚未上机，仍没有真实的 GSI 中断处理，也没有在硬件上读过 IPA_VERSION。`K60/K60ModemLink.c:261-282` 明确写着 "K60 has no IPA/GSI data path yet"，`coachz_modem_data_send()` 直接丢包并返回 `-50 (ENETDOWN)`。
- **QMAP mux**：没有 WDA Set Data Format、没有 QMAP endpoint 配置、没有 mux 1..4 注册。
- **net interface**：QcomBaseband 的 `coachz_bb_pdp.cpp:122-156` 会注册 `pdp_ip0..pdp_ip3`，`:83-120` 有 raw-IP TX/RX；但 K60 的 `coachz_modem_data_send` 是 ENETDOWN，所以 ifnet 只能挂载、不能通包。
- **WDS/QOS binding**：没有 DPM Open Port、没有 WDS Bind Mux Data Port（0x00a2）、没有 QOS Bind Data Port（0x002b）。
- **PDP/eSIM**：PDP 控制路径可复用，数据面未接；eSIM 的 UIM/APDU/VINYL 流程未实现（`BASE:62`）。

## 2. 硬件事实

| 项目 | 值 | 证据 |
|---|---|---|
| IPA wrapper 基址 / IPA 窗口 | `ipa-base = 0x3e00000`，大小 `0x84000`；`qcom,entire-ipa-block-size = 0x200000`（整块 0x3e00000..0x4000000） | `DTTRUTH:246-259, :269` |
| IPA 寄存器块 | `qcom,ipa-cfg-offset = 0x140000` 是 IPA wrapper 到 IPA 寄存器的偏移；故寄存器块 = `0x3e00000 + 0x140000 = 0x3f40000`，映射长度 `0x84000` | `DTTRUTH:268`；`DIPA/ipa_v3/ipa_i.h:2188`；`DIPA/ipa_v3/ipa.c:9185-9202`；`DIPA/ipa_v3/dump/ipa5.0/ipa_hwio.h:5763` |
| IPA 版本寄存器 | `HWIO_IPA_VERSION` 在 IPA 寄存器块 `+0x28`，即 `0x3f40028`；`0xffffffff`/0 表示不可读或未上电 | `DIPA/ipa_v3/dump/ipa5.0/ipa_hwio.h:5981-5991` |
| GSI 基址 / 窗口 | `gsi-base = 0x3e04000`，大小 `0xfc000`（与 ipa-base 重叠，是 GSI 独立视图） | `DTTRUTH:259` |
| GSI 3.0 寄存器偏移（相对 GSI 基址） | 通道 doorbell `0x24000 + 0x12000*EE + 0x8*ch`；事件 doorbell `0x24800` 同 stride；`GSI_STATUS=0x25000`、`GSI_CH_CMD=0x25008`、`EV_CH_CMD=0x25010`、`GSI_EE_GENERIC_CMD=0x25018`、`GSI_HW_PARAM_2=0x25040`。K60 绝对地址：通道 doorbell `0x3e28000`、事件 doorbell `0x3e28800`、`GSI_STATUS=0x3e29000` | `DIPA/gsi/gsihal/gsihal_reg.c:1856-1882`；`DIPA/gsi/gsi.h:91-103`（`GSI_VER_3_0=10`） |
| IPA / GSI 中断 | IPA IRQ = 654（0x28e），GSI IRQ = 432（0x1b0），均为 GIC SPI、level-high（flags 4）；`interrupt-names = ipa-irq, gsi-irq` | `FDT` 的 `//soc/qcom,ipa@3e00000/interrupts`；GSI 432 与 Coachz 参考值一致（`QB/ipa/coachz_gsi.c:7`） |
| IPA 固件名 / 路径 | `IPA_SUBSYSTEM_NAME = "ipa_fws"`；默认路径 `IPA_FWS_PATH = "ipa/ipa_fws.elf"` | `DIPA/ipa_v3/ipa.c:56`；`DIPA/ipa_v3/ipa_i.h:418` |
| IPA 固件加载序列 | 按 `firmware-names` 匹配 index，用同 index 解析 `memory-regions` phandle，拼 `<name>.mdt`，`request_firmware` → `memremap` → `qcom_mdt_load(dev, fw, fw_name, pas_id, virt, phys, size, NULL)` → `qcom_scm_pas_auth_and_reset(pas_id)` | `DIPA/ipa_v3/ipa.c:8104-8167`；同 index 解析见 `:8117-8128` |
| K60 DT 的固件/内存配对 | `firmware-names = "ipa_fws"`，`memory-regions = <0xb5> -> ipa_gsi_region@8b910000`，`pas-ids = <0x0f>`（PAS 15） | `DTTRUTH:263-265` |
| IPA 保留内存 | `ipa_fw_region@8b900000` = 0x8b900000, 0x10000 (64 KiB)；`ipa_gsi_region@8b910000` = 0x8b910000, 0xa000 (40 KiB) | `DTTRUTH:193-194` |
| SMP2P | `/soc/qcom,smp2p-modem`：`qcom,smem = <0x1b3 0x1ac>`（435/428），local-pid 0，remote-pid 1，`interrupts = (2,2,1)`；子节点 `qcom,smp2p-ipa-1-out`/`-in`，entry-name `ipa`，bit 0 | `DTTRUTH:343`；`FDT` 的 `qcom,smp2p-ipa-1-*` 节点（`smem-states`/`interrupts-extended`）；但 APQ 平台被忽略，见 `DIPA/ipa_v3/ipa.c:11140-11143` |
| IPA SMMU | `ipa_smmu_ap/uc/wlan/11ad` 的 `iommus = <&apps_smmu 0x5c0/0x5c1/0x5c2/0x5c3 0>`，即 stream ID 0x5c0..0x5c3（1472..1475）；`apps-smmu@15000000` 的 `reg = <0x15000000 0x100000 0x151ce000 0x20>`（base + TCU），`qcom,num-context-banks-override = 0x4e`（78）、`qcom,num-smr-override = 0x78`（120）、`qcom,use-3-lvl-tables`、`qcom,skip-init`、`dma-coherent`；`ipa_smmu_ap` 还有 `qcom,iommu-dma-addr-pool = <0x20000000 0x20000000>`、`qcom,additional-mapping = <0x146a8000 0x146a8000 0x2000>`、`qcom,ipa-q6-smem-size = <0x9000>` | `FDT` 的 `apps-smmu@15000000` 与 IPA 子节点；节点清单见 `DTTRUTH:279-284` |
| v5.1 APQ WAN endpoint 候选 | `IPA_CLIENT_APPS_WAN_PROD` = IPA endpoint 2、GSI channel 11；`IPA_CLIENT_APPS_WAN_CONS` = IPA endpoint 23、GSI channel 1（字段顺序见 `ipa_ep_num`/`ipa_gsi_chan_num`） | `DIPA/ipa_v3/ipa_utils.c:5623-5628`, `:5377-5383`, `:1081-1089`, `:8091`, `:8120-8122` |
| 硬件版本 | DT `qcom,ipa-hw-ver = 0x16`（22），`qcom,platform-type = 1`；dataipa `enum ipa_ver` 第 22 项为 `IPA_5_1_APQ`，`ipa3_get_hw_type_index()` 对 `IPA_HW_v5_1` + APQ 走 `IPA_5_1_APQ`，v5.0/v5.1 使用 `GSI_VER_3_0` | `DTTRUTH:266, :271`；`DIPA/ipa_v3/ipa_utils.c:305-331`, `:7650-7653`；`DIPA/ipa_v3/ipa.c:7401-7404` |
| IPA QMI 握手 | IPA 服务 0x31；AP host instance 1，modem instance 2；`INIT_DRIVER=0x21`、`INIT_COMPLETE=0x22`、`DRIVER_INIT_COMPLETE=0x35`、`INDICATION_REGISTER=0x20`、`INIT_DRIVER` 超时 60 s | `QB/ipa/coachz_ipa_qmi.h:8-15` |
| WDS/QOS 数据端口 | 端点必须为 `{type 4 (embedded), interface 1}`；DPM Open Port 在第一次 WDS bind 前；WDS Bind Mux Data Port 0x00a2、QOS Bind Data Port 0x002b；WDA Set Data Format 走 raw IP + QMAP 双向，下行最多 32 datagrams / 32768 bytes | `QB/baseband/coachz_bb_data.h:5-16`, `:23-41` |

**版本证据边界（不要过度解读）：** `0x16 = 22` 只是 DT 原始值；`IPA_HW_v5_1` 的原始数值在本地缺失的 kernel header 中，不能证明 `0x16` 就等于 `IPA_HW_v5_1`。但 `IPA_5_1_APQ` 是第 22 项、且 v5.1 路径选 GSI 3.0，和 K60 的 GSI 3.0 寄存器表吻合，因此本文以 **IPA v5.1 APQ** 为工作假设；`DTTRUTH:266` 的“4.11 世代”标签与 dataipa 表不一致，不应据此选 v4.11 寄存器表。最终以 M1 读 `IPA_VERSION` 为准。

## 3. QcomBaseband v4.2 可复用与 K60 专属边界

| 对象 | Coachz IPA v4.2（可参考） | K60 必须不同 |
|---|---|---|
| 总线 / 传输 | Apple PCIe modem 走 MHI；`QB/baseband/coachz_bb_data.h:5-16` 明确说 Apple 的 PCIe 端口是 `{3,4}` | K60 无 PCIe/MHI；modem 走 GLINK/SMEM 的 `IPCRTR`，`DTTRUTH:316-334`；PCIe 下无 modem 节点，`DTTRUTH:351` |
| 寄存器窗口 | `CIP_REG_PA=0x01e40000/0x7000`、`CIP_SHARED_PA=0x01e47000/0x2000`、`CIP_GSI_PA=0x01e04000/0x2c000`（`QB/ipa/coachz_ipa_proto.h:16-21`） | IPA wrapper 0x3e00000；IPA 寄存器块 0x3f40000；GSI 0x3e04000；GSI 3.0 偏移见 §2 |
| GSI doorbell | `CGSI_CH_C_DOORBELL_0=0x1e000`、`CGSI_EV_CH_E_DOORBELL_0=0x1e100`、`CGSI_GSI_STATUS=0x1f000`（`QB/ipa/coachz_ipa_v42.h:296-352`） | `0x24000`/`0x24800`/`0x25000`（GSI 3.0，见 `DIPA/gsi/gsihal/gsihal_reg.c:1856-1882`）；`coachz_gsi.c:180-194` 的 doorbell 写法可借用，常量必须换 |
| GSI 固件谁加载 | `QB/ipa/coachz_gsi.c:3-4` 假定 “modem loads the GSI firmware（qcom,gsi-loader=modem）”，GSI_STATUS 必须已 ENABLED | dataipa 里没有找到 `gsi-loader` 属性；K60 IPA 节点用 `firmware-names=ipa_fws` + PAS 15，应按 AP 侧 IPA FWS/PAS 路径处理，M1 验证。**UNKNOWN：K60 是否另有一个 modem 加载的 GSI 固件阶段** |
| ring / 描述符 | v4.2 固定 40 KiB，四 TRE ring（8+4+4+4 KiB）加四个 event ring（`QB/ipa/coachz_gsi.c:9-11`）；16 B TRE 可用（`coachz_ipa_v42.h` 的 CGS_ELEMENT） | K60 GSI 3.0 支持 4/8/16/32/64 B element（`DIPA/gsi/gsi.c:2804-2812`）；K60 的 40 KiB `ipa_gsi_region` 与 v4.2 相同，但 v5.1 APQ 的 channel 数/ring 深度是代码常量，DT 不描述（`DTTRUTH:287-299`）。**UNKNOWN：40 KiB 是否够 v5.1 APQ 的 WAN + command + LAN ring** |
| 端点 ID | v4.2 `AP_MODEM_TX=1, COMMAND_TX=6, LAN_RX=8, AP_MODEM_RX=9`（`QB/ipa/coachz_ipa_qmi.h:53-57`） | v5.1 APQ 候选：WAN_PROD endpoint 2/GSI 11，WAN_CONS endpoint 23/GSI 1（§2）；必须运行时读回校验，不能写死 |
| QMAP 版本 | `cbd_daps[] = { CBD_DAP_QMAPV4=8, CBD_DAP_QMAP=5 }`，顺序是 v4.2 先 QMAPv4 再 QMAP（`QB/baseband/coachz_bb_data.h:43`） | K60 v5.1 应先试 QMAPv5，再 QMAPv4，再 QMAP；**QMAPv5 的 DAP 常量 UNKNOWN**（本地无 IPA v5.x UAPI 头）。且 `coachz_bb_pdp.cpp:169-170` 把 `ul_dap == dl_dap == CBD_DAP_QMAPV4` 作为就绪条件，直接复用该文件只支持 QMAPv4 回退 |
| SMMU / DMA | v4.2 假定 apps SMMU bypass，固定物理地址（`QB/ipa/coachz_ipa_config.c:9-10`；`QB/platform/coachz/coachz_modem.c:28-39`） | K60 DT 有 `ipa_smmu_ap/uc/wlan/11ad`，stream ID 0x5c0..0x5c3；必须决定走 SMMU context 还是 bypass。固定 Coachz 物理地址 0x81400000/0x81700000/0x82000000 不可复用 |
| 控制面 | QcomBaseband 的 `coachz_bb_pdp.cpp:122-156` 是完整的 XNU ifnet/raw-IP 层，`pdp_ip0..3`、MTU 1492、PF_INET/PF_INET6 plumber 可直接借鉴 | K60 只替换底层 `coachz_modem_data_send/receiver`；上层 ifnet 和 WDS 控制逻辑可保留，但 QMAP 版本判断要改 |

**最小可复用结论：** QcomBaseband 的 **控制面**（QRTR/QMI 框架、WDS 0x00a2/QOS 0x002b、PDP 的 ifnet 形状）可借鉴；**数据面**（IPA 寄存器、GSI 3.0、QMAPv5、SMMU）必须按 K60 重写，不能照搬 v4.2。

## 4. 分阶段实现计划

### M0 — 仅编译骨架（IKM）

- 状态：2026-11-18 已实现，代码提交 `4405e3710e64ee249335bb4574b1d5b5f1336a4a`。新增 `K60Ipa.h`/`K60Ipa.c`，生成 `patches/xnu/0623-k60-ipa.patch`，host tests 与 patch gate 通过；内核构建通过，kernel sha256 `31991c62e390a6f61b4ebaad9b6228c4a0fb02f34b396d83cb746eb0ded7b2f8`（105,521,152 B），`llvm-nm` 确认 `_k60_ipa_probe`、`_k60_ipa_decode_comp_hw_version`、`_k60_ipa_marker`。
- 内容：新增 `K60Ipa.h`/`K60Ipa.c`，只放常量、结构体和空的 `k60_ipa_probe()`；不映射 MMIO、不写寄存器、不调用 PAS。
- 验收：内核编译通过；`nm` 能看到 `k60_ipa_probe`；编译期 static assert 为 `K60_IPA_CFG_BASE=0x3f40000`、`K60_GSI_BASE=0x3e04000`、`K60_IPA_IRQ=654`、`K60_GSI_IRQ=432`；启动不 panic、不改现有 modem 行为。
- 风险：XNU 构建文件需要新增条目（可能通过扩展 `patches/xnu/0622-k60-modem-qrtr.patch` 或新 patch）。
- 预计文件：`K60/K60Ipa.h`、`K60/K60Ipa.c`、对应 XNU patch。

### M1 — IPA 固件经 PAS 加载

- 状态：2026-11-18 已完成固件校验/暂存、IP0 时钟投票、PAS 15 路径与 handoff 调用点。新增 `K60Mdt.h`/`K60Mdt.c`（从 pong-power QcomMdt 的 BSD-2-Clause-Patent 实现移植并改名为 K60 命名空间）、`k60_ipa_firmware_check(blob,size,plan)`、`k60_ipa_firmware_stage(blob,size,region,region_size,metadata,metadata_size,plan)`、`k60_ipa_clock_vote()` 与 `k60_ipa_firmware_start(blob,size)`。真实 Xiaomi mondrian `ipa_fws` 已提取并校验：monolithic 40,376 B sha256 `305173004278a0fbb79aaff1683033226a423822499cc02f626768252d48b5b6`，PT_LOAD span 0x9000、metadata 0xe8c、3 个 load 段、relocatable；`K60IPA_FW_PASS`/`K60IPA_STAGE_PASS` 均通过。`k60_ipa_probe_from_handoff()` 通过 md0 的 payload FAT 读取 `IPA/ipa_fws.mbn`；`k60_ipa_firmware_start()` 先投 IP0、按活 FDT 的 `memory-regions -> ipa_gsi_region@8b910000` 映射 40 KiB 固件区、metadata 放 64 KiB `ipa_fw_region` 的最后 8 KiB（0x8b90e000）、按 K60Mdt 段表暂存、依次发 PAS 15 `INIT_IMAGE`/`MEM_SETUP`/`AUTH_AND_RESET`，然后读 `0x3f40028` 的 IPA_VERSION。内核 105,558,016 B sha256 `1bee79534cb8e2c2660774eff1a781da52baa163910c20d82f9768b32ebd4064` 的 llvm-nm 含 `_k60_ipa_firmware_stage`、`_k60_ipa_firmware_start`、`_k60_ipa_probe_from_handoff`；资源表初始化、GSI EE0 预检与固件区修正（活 FDT `memory-regions -> ipa_gsi_region@8b910000/0xa000`，metadata 在 `ipa_fw_region` 最后 8 KiB）后的该阶段内核为 105,562,112 B sha256 `7094936dd65b50e41f1ca9ef86ee48054fce0a39b08c1822e0445e704e2f4f8f`（后续 SMMU 诊断提交重编为 1a394bea，SMEM 分配修复提交 d828f3ab 后重编为 af9b211f）；尚未上机。
- 内容：按 `DIPA/ipa_v3/ipa.c:8104-8167` 的顺序实现：匹配 `firmware-names=ipa_fws`，取同 index `memory-regions`（当前是 `ipa_gsi_region@8b910000`），加载 `ipa_fws.mdt`，调 PAS 15 的 `auth_and_reset`。离线核对已完成：3 个 PT_LOAD 总 span 0x9000，40 KiB `ipa_gsi_region` 足够；metadata 0xe8c 放 64 KiB `ipa_fw_region` 的最后 8 KiB（0x8b90e000）。
- 验收：PAS 返回 0；能读 `0x3f40028` 得到非 0/非 0xffffffff 的 `IPA_VERSION`；打印 IPA 版本和时钟状态，不启动 GSI。
- 风险：原 40 KiB 配对风险已解除（3 段总 span 0x8568，metadata 0xe8c 走 `ipa_fw_region` 最后 8 KiB）。IP0 时钟已通过 RSC TCS4 投票；剩余风险是 `AUTH_AND_RESET` 后 `IPA_VERSION` 的轮询边界和硬件上的时钟/电源状态。
- 已落地文件：`K60/K60Ipa.c`、`K60/K60Mdt.c`、`patches/xnu/0624-k60-ipa-call-site.patch`、`scripts/tests/test-k60-ipa.c`、`scripts/tests/test-k60-mdt.c`；PAS 调用复用 `K60ModemPas.h`。调用点已实现，IP0 时钟也已在同一文件内投票；仍未上机。

### M2 — GSI 初始化 / ring 分配

- 状态：2026-11-18 GSI 能力/所有权预检已实现（`K60Ipa.h`/`K60Ipa.c` 的 `k60_ipa_gsi_check()`，host `K60 IPA GSI PASS`，代码提交 `b636f2e5`）；M2 host 模块已落地（`K60IpaGsi.h`/`K60IpaGsi.c` 的 GSI 3.0 command-DMA、`K60IpaSmmu.h`/`K60IpaSmmu.c` 的 SMMU 流规划，host `K60 IPA GSI DMA PASS`/`K60 IPA SMMU PASS`，代码提交 `5c217091`）；M2 运行时 glue 已写入 `K60Ipa.c`：`kmem_alloc_contig()` 分配 1 MiB ring（64 KiB 对齐）与 0x8000 表块（页对齐），`ArmSmmu4KBuild()` 建 `{0x146a8000/0x2000, ring_pa/1MiB, SMEM item 497}` 三区间页表，`ArmSmmu4KProgramDisabledContext()` 后直接写 SMR/S2CR（SID 0x5c0），再调用 `k60_ipa_gsi_init()/start()/poll()`；整段由 boot arg `pong_ipa` 的级别门控：`pong_ipa=1` 只到 M1，`pong_ipa=2` 才运行 M2，避免新增参数把 arm64 命令行推过 DarwinBoot 的 607 字节上限。host tests 通过，内核 63645bc3（105,562,112 B）已编译；k10 M2 诊断镜像已生成四张（C `4661ab18` / C0 `a3caf67d` / IPA-only `1c466e33` / B-full `1b0cf4e3`，pong_ipa=2），但未上机。`k60_ipa_gsi_check_caps()` 的 PAS 后语义已修正为要求 `GSI_STATUS` bit0=1（EE0 enabled），缺失返回 `K60IpaGsiNoDevice`（提交 `4764d170`）；修复后的内核为 7094936d（105,562,112 B）。离线又发现 K60 PongAdreno 的 ArmSmmu4K 构建器会拒绝 DT additional-mapping 0x146a8000/0x2000 所需的 Device-nGnRE（writeback=2）；提交 `b9de56b9` 增加 writeback=2 支持并使用 MAIR index 2，重编内核 `06e31af4`（105,562,112 B）。k11 M2 诊断镜像：C `6177500f` / C0 `c3f58d8f` / IPA-only `9639b6c2` / B-full `9d128c7c`，均 `pong_ipa=2`。k12 在 `71e7c43` 增加 SMMU IDR/context 诊断后重编 `1a394bea`（105,562,112 B），标准镜像 C `58d9dc01` / C0 `b77cd1d8` / IPA-only `d1ffb983` / B `cabeef22`，M2 诊断镜像 C `603f25ce` / C0 `fb8764cb` / IPA-only `14a1eee6` / B-full `12428e2a`，全部未上机。提交 `d828f3ab` 修复 M2 运行时对 SMEM item 497 只查找不分配的问题：`k60_ipa_runtime_smem_item()` 在 TCSR SMEM mutex 0x1f43000 下调用 `k60_smem_alloc()`（已存在则 `k60_smem_find()`），失败即拒绝 SMMU 区间；重编内核 `af9b211f`（105,562,112 B），k13 标准/M2 诊断镜像已生成（hash 见 k13 清单），全部未上机。
- k8 M2 诊断镜像（2026-11-18 06:48）：C `boot-modem-c-diagnostic-m2.img` sha256 `5f73c42a7193855c754ad1d65efbe40b6f6682c4fbae466ff2abb2fbc063e554`；C0 `boot-modem-c-nocarrier-m2.img` sha256 `4d9eb4d81082602a818e46c9ebd4a3c9e7b5fd584a888421d877f1e10534f114`；IPA-only `boot-modem-ipa-only-m2.img` sha256 `61b54fa693d38808f514535ffda378e72d89473d84799d6dd386228ef5f7369f`；三张均 201,895,936 B，kernel_args 以 `pong_ipa=2` 结尾。
- 内容：映射 GSI 0x3e04000；按 `gsihal_reg.c:1856-1882` 写 `GSI_STATUS`/`GSI_CH_CMD`/`EV_CH_CMD`；从 `ipa_gsi_region` 分配 channel/event ring；16 B TRE 草案；轮询或中断 `gsi-irq=432`。
- 验收：`GSI_STATUS` 读到 ENABLED；每个 WAN/command/LAN 通道 state 到 `ENABLED`；ring 基址/长度打印且 64 KiB 对齐；无 GSI command timeout。
- 风险：v5.1 APQ 的 ring 数量/深度未知；40 KiB 可能不够；GSI 3.0 命令超时 50 ms 与 v4.2 不同需实测。
- 已落地文件：`K60/K60IpaGsi.h`、`K60/K60IpaGsi.c`、`K60/K60IpaSmmu.h`、`K60/K60IpaSmmu.c`；运行时 glue 在 `K60Ipa.c` 的 `k60_ipa_runtime_start()`/`k60_ipa_runtime_gsi_init()`/`k60_ipa_runtime_smmu()`/`k60_ipa_runtime_gsi()` 中实现，调用顺序必须是 GSI init → SMMU 页表 → GSI start：`k60_ipa_gsi_init()` 会清零同一块 0x8000 表块，先建 SMMU 会把页表擦掉。GSI 只轮询 event shadow，没有接 IRQ 432。

### M3 — WDS/QOS QMI 握手 + QMAP mux 注册

- 内容：在 `K60ModemLink.c` 的 QRTR/QMI 分发里增加 IPA 服务 0x31：响应 `INIT_DRIVER`（0x21）、`INDICATION_REGISTER`（0x20）、`DRIVER_INIT_COMPLETE`（0x35），发送 `INIT_COMPLETE`（0x22）；随后做 DPM Open Port、WDS 0x00a2、QOS 0x002b、WDA Set Data Format（0x20），把 `{type 4, interface 1}` 填进 WDS/QOS 请求。
- 验收：IPA QMI 握手 4 条消息全部有应答；WDA 返回成功；mux 1..4 注册成功；日志出现 mux id、endpoint 2/23、DAP 值。
- 风险：QMAPv5 DAP 常量未确认；modem 可能只接受 QMAPv4；QMI 消息 TLV 版本差异；必须先 QMAPv5 → QMAPv4 → QMAP 回退。
- 预计文件：`K60/K60IpaQmi.c`（或扩展 `K60/K60ModemLink.c`）、`K60/K60IpaQmi.h`。

### M4 — PDP / net interface

- 内容：复用 `QB/baseband/coachz_bb_pdp.cpp:122-156` 的 XNU ifnet 形状，注册 `pdp_ip0..3`、`IFNET_FAMILY_CELLULAR`、MTU 1492、`PF_INET`/`PF_INET6` plumber；把 K60 的 WDS 客户端 family 状态映射到 `bb_pdp_poll`。
- 验收：`ifconfig pdp_ip0` 出现；`SIOCSIFMTU=1492` 成功；`PF_INET`/`PF_INET6` plumber 返回 0；接口初始 DOWN，WDS family 激活后变为 RUNNING。
- 风险：XNU 网络栈的 cellular family/ifnet 私有 API 版本适配；QMAP 未就绪时不要错误置 RUNNING。
- 预计文件：`K60/K60IpaNet.c`、`K60/K60IpaNet.h`；如需改动 `coachz_bb_pdp.cpp`，必须保留 BSD-2-Clause 头。

### M5 — RX/TX

- 内容：TX 从 `coachz_modem_data_send()` 进入 IPA WAN_PROD（endpoint 2/GSI 11）；RX 从 WAN_CONS（endpoint 23/GSI 1）回收 completion，按 QMAP mux 解出 IP 包，调用 `coachz_modem_data_receiver()`；buffer replenish 与 DMA 同步按 `coachz_ipa_rx.c` 的形状重写。
- 验收：`coachz_modem_data_send()` 返回 0、TX 计数递增；RX 回调收到包并交给 `pdp_ip`；`ping` 网关或 UDP echo 至少单向；掉包/错误计数可解释。
- 风险：QMAP 头/聚合格式、TRE 位域未验证；DMA cache 一致性；GSI completion 与 ifnet 队列的背压。
- 预计文件：`K60/K60IpaRx.c`、`K60/K60IpaTx.c`、`K60/K60IpaDma.h`。

### M6 — reset / flight mode

- 内容：把 IPA 停止/重启挂到 modem reset 与 flight mode：WDS/QOS 解绑、GSI halt、IPA uC stop、PAS reset；恢复时重新 M1→M5。SMP2P 在 APQ 上被 dataipa 忽略（`DIPA/ipa_v3/ipa.c:11140-11143`），仅作观测/复位信号使用。
- 验收：flight mode 切换时 `pdp_ip0..3` 全部 DOWN；modem reset 后 IPA 版本读回一致、无 panic、无内存泄漏、无 stale ring。
- 风险：reset 顺序与 modem PAS/SMP2P 竞争；IPA 时钟未建模会 hang；flight mode 与 Wi-Fi IPA 共用时钟域。
- 预计文件：`K60/K60IpaReset.c`、`K60/K60ModemBoot.c`（仅加入 reset hook）。

## 5. 许可证与代码来源

- QcomBaseband 的 IPA/Coachz 文件是 **BSD-2-Clause**：`QB/ipa/coachz_ipa_config.c:1`、`QB/ipa/coachz_gsi.c:1`、`QB/baseband/coachz_bb_data.h:1` 均为 `SPDX-License-Identifier: BSD-2-Clause`。可读、可改、可把控制面/ifnet 形状带进 K60，但必须保留版权与 SPDX 头。
- Linux dataipa 是 **GPL-2.0-only**：`DIPA/ipa_v3/ipa.c:1` 明确 `SPDX-License-Identifier: GPL-2.0-only`。**不能把 dataipa 的 C 代码复制进 XNU/BSD 树**；只能把寄存器偏移、字段值、版本表当作硬件事实，重写实现。寄存器宏/常量本身是事实，不构成代码复制。
- K60 现有驱动是 `SPDX-License-Identifier: BSD-2-Clause-Patent`（`K60/K60ModemLink.c:1`）；新文件保持同一许可证。
- 策略：**硬件事实/寄存器映射可参考；代码按 XNU 风格重写；不引入 GPL-2.0-only 源文件到内核树。**

## 6. 明确未实现与下一步

**当前明确未实现：**

- 没有上机验证：`k60_ipa_probe_from_handoff()` 已能从 payload FAT 读取 `IPA/ipa_fws.mbn` 并调用 `k60_ipa_firmware_start()`，但还没有在硬件上执行过 PAS 15，也没有设备侧 IPA_VERSION 读数；host 侧可用 `k60_ipa_firmware_stage()` 验证真实映像。M2 运行时由 boot arg `pong_ipa` 的级别显式启用：`pong_ipa=1` 只到 M1，`pong_ipa=2` 才运行 M2（默认关闭）；k7 完整候选只设 `pong_ipa=1`，k13 M2 诊断镜像设 `pong_ipa=2`。
- `k60_ipa_firmware_start()` 映射固件区、GSI 与 IPA_VERSION 寄存器，IPA5.1 资源表已初始化，`k60_ipa_gsi_check()` 只读 GSI status/channels/events 和 command12/event0 状态；M2 运行时接着分配 ring/表块并启动 GSI command-DMA，但没有硬件执行过，也没有接 IRQ 654/432。
- GSI 运行时初始化、1 MiB ring 与 0x8000 表块已在内核代码里绑定（`kmem_alloc_contig`、`pmap_find_phys`、MMIO 回调、命令 channel12/event0），但没有硬件执行；没有 GSI IRQ 432 处理，只轮询 event shadow；`K60IpaGsi.c` 的宿主状态机测试仍是唯一的代码级证据。
- `K60IpaSmmu.c` 仍是宿主 SMMU 寄存器模型；内核页表由 `K60Ipa.c` 直接调用 `ArmSmmu4KBuild()` 构建（三区间、输出 36 位、8 表页），在 TCSR SMEM mutex 0x1f43000 下分配/复用 SMEM item 497（≥0x9000，失败即拒绝），并写 SID 0x5c0 的 SMR/S2CR；没有 SMMU 抢占/lease，没有硬件执行。宿主测试现在覆盖精确运行时几何：SMEM item 497 窗口按页对齐后为 0x9000，未对齐时最多 0xa000；0x9000 下得到 6 个表页、267 个叶页，0xa000 下得到 6 个表页、268 个叶页（8 个表页容量）。
- 没有 IPA QMI 服务 0x31 的 `INIT_DRIVER/INIT_COMPLETE/DRIVER_INIT_COMPLETE`。
- 没有 WDS 0x00a2 / QOS 0x002b / DPM Open Port / WDA Set Data Format。
- 没有 QMAP mux 注册、没有 QMAPv5 常量、没有 QMAPv4 回退。
- 没有 K60 IPA SMMU 配置；没有 pdp_ip 数据 TX/RX；`K60/K60ModemLink.c:261-282` 仍返回 ENETDOWN。
- 没有 reset/flight-mode 的 IPA 停止/恢复。

**首个最小安全离线测试：**

1. `ipa_fws.mdt`/`b00..b04` 已从 Xiaomi mondrian OS3.0.8.0 固件包提取到 `E:/k60-work/firmware/ipa_fws/`，并组装为 40,376 B 的 `ipa_fws.mbn`；该文件是验证输入，不应提交进仓库。
2. 使用已实现的 host-only gate `scripts/tests/test-k60-modem-ipa-fw.py --mdt <ipa_fws.mdt>`（不启动设备、不写内核）解析 ELF program headers，求所有 `PT_LOAD` 的 `p_memsz` 总和，打印每个段的 `p_paddr/p_filesz/p_memsz`；`--selftest` 可在没有固件时验证解析器。`K60Mdt`/`k60_ipa_firmware_check()` 提供同样的 span 与 metadata 约束，Python gate 与内核解析必须给出相同结论。
3. 与 DT 的两个 region 比较结果：`0x8568`（34,152 B）≤ `0xa000`，当前 `memory-regions -> ipa_gsi_region@8b910000` 可容纳全部 PT_LOAD；metadata `0xe8c` 走 `ipa_fw_region@8b900000` 的最后 8 KiB。M1 的 40 KiB 风险解除。
4. 同时用 `dtc`/FDT 属性导出核对 `firmware-names`、`memory-regions`、`pas-ids` 的 index 对齐（`DIPA/ipa_v3/ipa.c:8117-8128` 要求同 index）。

**下一步代码动作：** M0 骨架、M1 固件校验/暂存/PAS 路径、IP0 时钟与 payload FAT handoff 调用点、M2 host 模块与运行时 glue 已落地，内核 af9b211f 已编译（SMMU IDR/context 诊断 + SMEM item 497 分配修复），k13 标准与 M2 诊断镜像（C/C0/IPA-only/B-full）已生成；下一步是上机读 IPA_VERSION，确认 PAS 15、时钟投票与 GSI status，再用 `pong_ipa=2` 开一次受控 M2 运行时并抓 ring/GSI 状态。M2 未上机通过前不要写 QMAP 代码。