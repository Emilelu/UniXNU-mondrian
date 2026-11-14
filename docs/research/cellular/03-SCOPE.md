# 03 — 范围判定：基带在本次移植里算不算"范围内"

> 前置：`01-ANDROID-INVENTORY.md`（Android 侧实机清单）、`02-DT-TRUTH.md`（DT 真相）
> 判定对象：`porting.toml` `[[area]] id = "cellular"`（`porting.toml:191-223`，当前 `status = "planned"`）
> 本文只做**范围判定**，不写一行 cellular 驱动代码。

---

## 0. 结论

**把 cellular 判为"范围内，但只到枚举（enumeration）为止"，不做数据/语音。**

具体分三层：

| 层 | 内容 | 判定 | 理由摘要 |
|---|---|---|---|
| **L1 固件加载** | 读 `modem_a` 分区 → 解析 `modem.mdt` 段表 → PAS 搬进 `mpss_region` → 等 `ready` | ✅ **在范围内，且已有 70% 代码** | ADSP 的 PAS 加载器已在 `drivers/PongPower/K60AdspPas.c` 跑通，modem 是"第二个实例" |
| **L2 QRTR 枚举** | GLINK `IPCRTR` 通道 → AF_QIPCRTR → `servreg` 查询 → 读出固件版本串 | ✅ **在范围内**（这就是 `completion` 的判据） | 通道名/intents 在 DT 里写死；`modemr.jsn` 给了 PD 身份；GLINK 传输已有 |
| **L3 数据/语音** | IPA 数据面、QMAP、mbn 选择、EFS/NV 代读、SIM 访问、IMS/VoLTE | ❌ **不在范围内** | IPA 是"全有或全无"（§4.2）；EFS 需要 `tftp_server` 等价物；mbn 选择是 Android 用户态逻辑；VoLTE 依赖 Android 的 IMS 栈 |

`porting.toml` 里写的 completion 是
**"A device boot shows the modem enumerated over QRTR with a readable firmware revision."**
—— 它恰好落在 L2，**不要求 L3**。所以当前 `status = "planned"` 是准确的，
不需要改成 `not-applicable`，也不需要把 completion 改小。

---

## 1. 为什么"不做"不等于"不记录"

`porting.toml:210-213` 的 findings 已经写了这条：

> "The port currently has no baseband support at all; Android modem stack is untouched."
> "Recording it as planned rather than not-applicable keeps the gap visible."

本文用实测数据支持这个决定：

- XNU 侧 grep `qrtr|qmi|baseband|cellular` → **只有 WiFi 的 MHI QRTR**（`patches/wifi/0001-*.patch`
  里的 `nw_qrtr_mhi_register`），**modem 路径零代码**。
- DT 侧 `dts/mondrian.dts` 198 行里 **没有** `mpss_region`/`remoteproc-mss`/`qcom,ipa`/modem `glink-edge`。
- 也就是说：**从"设备树有描述"到"XNU 能枚举 modem"之间，目前是 0 行代码的距离**。
  如果把它标成 `not-applicable`，这条 0 行代码的鸿沟就会从看板上消失。

---

## 2. L1（固件加载）：为什么说"已有 70% 代码"

`drivers/PongPower/` 里已经有一套**跑通过的** PAS 加载器（ADSP 用）：

| 已有件 | 文件 | 对 modem 的可复用度 |
|---|---|---|
| PAS SCM 调用序列 | `K60AdspPas.c` | **100%** —— `QCOM_SCM_SVC_PIL=0x02`、`PAS_INIT_IMAGE=0x01`、`PAS_MEM_SETUP=0x02`、`PAS_AUTH_AND_RESET=0x05`，调用形状 `scm(command, arginfo, a, b, c)`、`smc #0` 用 x0..x7，成功判据 `x0==0 && x1==0` |
| ELF32 段表解析 | `K60AdspImage.c` | **100%** —— 同样的 `e_phoff=52`/`e_phentsize=32`，只需换 `e_phnum`（ADSP 26 → modem 32） |
| SMEM 分区 | `K60Smem.c/.h`（`k60_smem_find`/`k60_smem_alloc`） | **100%** —— modem 的 `IPCRTR` FIFO 也在 `smem_region@80900000` 里 |
| GLINK 协议 | `QcomGlink.c/.h` | **~60%** —— 协议层（`VERSION/OPEN/CLOSE/TX_DATA/RX_DATA/RX_DONE/READ_NOTIF/SIGNALS`、intent 数组、FIFO 头尾指针）可复用；但 `QCOM_GLINK_MAX_CHANNELS = 1` 和"exclusively leased K60 PMIC endpoint"的假设必须改 |

**唯一真正新的东西**：

1. modem 的 carveout 常量（`0x8bc00000` / `0x13200000`）—— 来自 DT，已取证（`02` §2）
2. modem 的 PAS 服务 id —— 需要从 TZ 侧确认（ADSP 用的那套 id 不能直接套）
3. 供电轨预置（PM8350C S6/S4）—— 触摸/电源线已有 RPMh 投票代码可参考
   （`docs/research/touch/POWER-RPMH-LDOC2.md` 是同一套 TCS 投票机制的完整文档）
4. IPCC `ready`/`stop-ack` 等待 + smp2p `stop` 位

→ **L1 的工程量是"照 ADSP 的形状再写一遍 + 改常量"，不是新理论。**
这是判定"在范围内"的最强理由。

---

## 3. L2（QRTR 枚举）：为什么 completion 判据是可实现的

`completion` 要求"device boot shows the modem enumerated over QRTR with a readable firmware revision"。
拆成可验证的子步骤：

| 步骤 | 需要什么 | 已有/缺 | 验证方式 |
|---|---|---|---|
| 1. GLINK 通道 `IPCRTR` 建立 | DT: `qcom,glink-channels = "IPCRTR"`、3 组 intents（`0x800×5`、`0x2000×3`、`0x4400×2`） | GLINK 协议已有，多通道化缺 | 对端在通道建立后会发 `OPEN` ack；Android 侧同名通道在 `/sys/class/remoteproc/remoteproc2/.../IPCRTR` 可见（已取证） |
| 2. AF_QIPCRTR 内核协议 | Linux 里是 `net/qrtr/` 一个独立协议族（`QIPCRTR`，`/proc/net/protocols` 已见） | **缺**（XNU 无此协议族） | 能 `socket(AF_QIPCRTR)` 并收发 |
| 3. QRTR 名字服务 | 需要 QRTR NS 逻辑（`QRTR_TYPE_NEW_LOOKUP` 广播 → `NEW_SERVER` 回应） | **缺** | 能列出 `servreg`/`gps_service` |
| 4. `servreg` 查询拿版本 | `modemr.jsn` 给出 `soc=msm, domain=modem, subdomain=root_pd, qmi_instance_id=180` | **缺** | 返回 `MPSS.DE.2.0.c1-CN-Jan 13 2026-02:08:51` 或等价版本串 |

**最小可行路径**（建议按这个顺序做，每步都能独立验证）：

```
① GLINK IPCRTR 通道 up          → 打印通道名 + 对端 intent 数
② 裸 QRTR 报文（不建协议族）     → 手工组 HELLO/NEW_LOOKUP，走 GLINK 发出去，收到回应
③ 建 AF_QIPCRTR 协议族          → 把 ② 的逻辑包成 socket API
④ QMI servreg 查询              → 拿到版本串 = completion 达成
```

**关键判断：② 就足以证明"modem 已枚举"。**
不一定要先做完 ③（完整协议族）才能验证 —— 这也是为什么 completion 判据是合理的、不是空头支票。

### 3.1 一个必须承认的未解项

Android 侧 `qrtr-lookup` 在本会话**列不出任何服务**（`01` §5.4：只有表头，rc=0）。
可能原因：SELinux（`u:r:ksu:s0` 上下文）、或者 `qrtr-lookup` 依赖的 NS 未响应。

**这直接影响 L2 的可行性判断**：如果连 Android 自己的工具都列不出服务，
那"枚举成功"的判据需要重新定义（例如改成"能收到 `servreg` 对 `NEW_LOOKUP` 的回应"，
而不是"能列出服务表"）。

→ **L2 开工前必须先解决这个未解项**（在 Android 侧用 `strace`/`logcat` 或直接读 `qrtr-lookup` 源码确认）。
这写进 `next_action`。

---

## 4. L3（数据/语音）：为什么明确排除

### 4.1 IPA 是"全有或全无"

DT 只给 IPA 的**基址、尺寸、硬件版本**（`0x3e00000`/`0x84000`、`gsi-base 0x3e04000`/`0xfc000`、`ipa-hw-ver=0x16`）。
**每个通道的 ring 数量、深度、doorbell 布局是驱动代码里的常量，不在 DT 里**
（`02` §4.2）。这意味着：

- 不能"先做一半 IPA" —— GSI 环没配对，一个包也过不去
- 移植 IPA 等于移植 Linux 的 `drivers/net/ipa/` 整个子系统（约 2 万行），
  还要接 SMMU（`ipa_smmu_ap/uc/wlan/11ad` 四个上下文）
- IPA 固件本身也要 PAS 加载（`ipa_fws`，`pas-ids = 0xf`）

**结论：IPA 不在本次移植范围内。** 没有 IPA 就没有数据面，所以 L3 的数据部分整体排除。

### 4.2 EFS/NV 需要 `tftp_server` 的等价物

modem 固件起来后，会通过 QMI 向主机请求 NV 项（IMEI、射频校准、运营商配置等）。
Android 侧的应答者是 `tftp_server`（pid 2027，见 `01` §7.3），
它从 `modemst1`/`modemst2`（sdf3/sdf4，各 8 MiB 裸分区）读出数据、经共享内存递给 modem。

**XNU 侧不做这件事的后果**：modem 能起来、能被枚举（L2 达成），
但会停在"无网络"状态 —— 这**正好符合 L1/L2 的目标**，不构成 L2 的阻塞。

**但要写清楚**：这也是为什么 completion 判据只能是"枚举 + 版本串"，
不能是"能打电话" —— 后者需要 EFS 路径 + SIM 访问 + IMS 栈，工作量是 L1/L2 的十倍以上。

### 4.3 mbn 选择是 Android 用户态逻辑

`persist.radio.mbn_default`/`mbn_hw_sub0`/`mbn_sw_sub0`/`mbn_sw_sub1` 这组 property
（`01` §3.5）是 Android 的 `modemManager`/`qmipriod` 算出来的，
它决定"这张卡该加载哪个运营商配置"。这套逻辑不在固件里，在 Android 的 HAL 里。
→ 即使 L3 只做数据，也要重写这套选择逻辑。**排除。**

### 4.4 VoLTE/IMS 完全在 Android 侧

`gsm.sim.operator.alpha = "China Telecom,China Mobile"`，
两卡都走 VoLTE（`hVoLTE_OPNMKT_CT` / `Volte_OpenMkt-Commercial-CMCC`）。
IMS 注册、SIP 栈、音频通路全在 Android 用户态。
→ **永久排除**（这不是移植，是重写一个电话应用栈）。

---

## 5. 双系统约束：这是本 area 最容易被忽略的风险

设备是双系统（Android + XNU，靠 `unixnu` 分区切换，boot 分区归 Android）。
modem 固件、EFS/NV、SIM 身份都在 Android 侧（`porting.toml:198` 的 inputs 已写）。

**具体风险**：

| 风险 | 说明 | 缓解 |
|---|---|---|
| **modem 状态跨系统残留** | 从 Android 热重启进 XNU 时，modem 可能仍处于 Android 拉起的运行态。XNU 若直接 PAS `AUTH_AND_RESET`，会**打断一个正在运行的 modem** | 加载前先读 MSS 的 `state`/`smem` 状态位；或在 XNU 启动流程里显式 `stop` 再 `start` |
| **EFS 写冲突** | 两套系统都能写 `modemst`（若 XNU 实现了写路径） | L1/L2 阶段**只读不写** `modemst`/`fsg`/`fsc` |
| **Android 侧数据被破坏** | 误刷 `modem_a` 会丢基带 | 铁则：**永不 `fastboot flash`**；只 `fastboot boot` |
| **SIM 状态不一致** | Android 关机时可能把 SIM 置为 `ABSENT` | 枚举阶段不依赖 SIM 状态 |

**这条要写进 `patches/cellular/README.md` 的"禁止事项"里。**

---

## 6. 与官方组件目录的关系

仓库铁则要求"写驱动前先查官方组件目录"。本 area 的结论：

| 需要的组件 | 官方/上游有吗 | 结论 |
|---|---|---|
| PAS 加载器 | XNU 侧无官方；Linux 有 `qcom_q6v5_pas` | 已有自研 `K60AdspPas.c` 可复用，**不需要新写** |
| GLINK | XNU 侧无官方；Linux 有 `drivers/soc/qcom/qcom_glink*` | 已有自研 `QcomGlink.c`，需多通道化 |
| QRTR | XNU 侧无官方；Linux 有 `net/qrtr/` | **必须自研**（但可照 Linux 的协议定义写，协议本身是公开的） |
| QMI | XNU 侧无官方；Linux 有 `drivers/soc/qcom/qmi_*.c` | L2 只需 `servreg` 一条，可手写报文 |
| IPA | XNU 侧无官方；Linux 有 `drivers/net/ipa/` | **排除**（§4.1） |

→ 没有任何一个组件能"直接用官方实现"，但 **L1/L2 所需的三件（PAS/GLINK/QRTR）都有清晰的参考实现**，
不是"从零发明协议"。

---

## 7. 范围判定的最终表述（给 porting.toml 用）

```toml
# 建议的 findings 增补（不改 status，不改 completion）
"The baseband is a PAS remote processor inside the SM8475 package: MSS MMIO at 0x04080000,
 firmware modem.mdt (QDSP6 ELF32, e_machine=0xA4) links exactly onto mpss_region
 0x8bc00000/0x13200000, and every PT_LOAD paddr falls inside that carveout."
"Scope is L1 firmware load + L2 QRTR enumeration only. IPA/QMAP data path, EFS/NV service,
 mbn selection and IMS are explicitly out of scope: the IPA ring geometry is driver code,
 not DT, and the EFS responder is an Android userspace daemon (tftp_server)."
"Reusable code already exists: K60AdspPas.c (PAS SCM sequence), K60AdspImage.c (ELF32 segment
 table), K60Smem.c, QcomGlink.c (single-channel, PMIC-shaped; must be generalized to
 carry the IPCRTR channel with its three DT-declared intent groups)."
```

**status 保持 `planned`。** 理由：L1/L2 已证明可行且有 70% 代码，但**一行都还没写**，
所以既不是 `not-applicable`，也还不能是 `in-progress`。

---

## 8. 建议的 next_action（按顺序）

1. **先解未解项**：Android 侧确认 `qrtr-lookup` 为什么列不出服务
   （`strace -f /vendor/bin/qrtr-lookup` 或读它的源码），否则 L2 的验收判据不成立。
2. **补 DT**：把 `02-DT-TRUTH.md` §1/§2/§4 的节点（`mpss_region`、`remoteproc-mss`、
   modem `glink-edge`、`qcom,ipa`）按活 FDT 的字节抄进 `dts/mondrian.dts`。
   **这一步只加节点、不启驱动**，可以独立验证（`dtc` 编译通过 + 与活 FDT 逐字节比对）。
3. **多通道化 GLINK**：把 `QCOM_GLINK_MAX_CHANNELS = 1` 改掉，先只加 `IPCRTR` 一条，
   用 Android 侧同名通道的存在作为对照。
4. **PAS 加载 modem**：照 `K60AdspPas.c` 写第二实例，carveout `0x8bc00000`/`0x13200000`，
   32 段表。**加载前必须处理"modem 可能仍在运行"的情况**（§5）。
5. **裸 QRTR 报文**：手工组 `NEW_LOOKUP`，走 `IPCRTR` 发出去，看有没有回应。
   —— 到这一步就可以宣布 completion 达成（或明确失败）。

**在 ① 完成前不要写 cellular 驱动代码。** 否则可能对着一个错误的验收判据做无用功。

---

## 9. 本文的诚实清单

| 项 | 状态 |
|---|---|
| X65 型号的直接证据 | **没有**。DT 只有 `cape`，固件不自报。本文只说"X65 级 modem 内置于 SM8475"，不伪造 DT 证据（`02` §10.1） |
| modem 的 PAS 服务 id | **未确认**。ADSP 的那套不能直接套，需要从 TZ 侧或 Android 的 `qcom_q6v5_pas` 日志确认 |
| `qrtr-lookup` 空结果的原因 | **未解**（§3.1）。这是 L2 的前置阻塞 |
| IPA ring 几何 | **未取**。DT 不描述，需从 `ipa-hw-ver=0x16` 对应的寄存器表取 |
| modem 起来后是否需要 EFS 才能"枚举" | **未验证**。理论上不需要（枚举是 QRTR 层），但没有实测 |
| `mba.mbn` 缺失是否影响加载 | **推测不影响**（新世代单镜像），未实测 |
