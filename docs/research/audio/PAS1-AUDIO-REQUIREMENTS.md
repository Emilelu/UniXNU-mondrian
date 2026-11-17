# PAS1-AUDIO-REQUIREMENTS — 音频线对 PAS1 provider 的依赖、降级与仲裁

状态行（沿用 CODEC.md 的 ①–⑧ 记法）：① 同型 ✅ ② 官方 ⚠️ ③ 反编译 ✅ ④ 广域 ✅ ⑤ 方案 ✅ ⑥ 深挖 ✅ ⑦ 本机验证 ⏳ ⑧ 上机 ❌

本文回答 Lead m06642 与 2026-11-15 reply md 点名的三件事，并按 2026-11-15 的载具 ABI 与五阶段契约对齐：
**GPR/APM 服务注册与 GLINK 独占的仲裁（§1.2，两案代价）**、**PAS1 未就绪时的降级形态（§2.1，`-1000` 的具体表现）**、
**AFE 参数下发在时序里的位置（§3.1 三道门 / §3.2 重试边界）**；§0.1 是载具 ABI 与音频的关系，末尾是 `TDMS.md` §8 五条的机器可读版。
只写 `docs/research/audio/`；battery 线的契约文件（`PAS1-PROVIDER-CONTRACT.md`、`INTEGRATION-ORDER.md`、
`HANDOFF-PUBLISH.md`、`GLINK-HANDOFF.md`）属 adsp-handoff 线 scope，本文只引用不改。
行号均为 2026-11-15 实测；标 `待实测` 的条目本机没有对应源码或需要上机/构建后确认。

---

## 0. 音频对 provider 的依赖（总览）

| # | 依赖 | provider 要给什么 | 依据 |
|---|---|---|---|
| 1 | ADSP 在跑 | PAS1 载入 + `PAS_AUTH_AND_RESET` 成功；lease.flags 精确 == 15 | `PAS1-PROVIDER-CONTRACT.md:72`；`ADSP-PAS1.md:38-44`；载体见 §0.1 |
| 2 | GLINK 交出来 | publish 后把 `/chosen/k60-adsp-glink-handoff`（104 B）交给 consumer，成功后无 release 入口 | `PAS1-PROVIDER-CONTRACT.md:84`；`K60BatteryConfig.h:36-45` |
| 3 | AFE 服务可达 | 不额外提供：音频自己发 GPR 参数包，不碰 LPAIF 寄存器 | `TDMS.md` §3；`q6afe.c:1080-1160` |

**provider 不需要替音频做的事**：不发 AFE 参数、不开 `adsp_apps` 通道、不碰 TLMM 引脚复用、不读 ACF。
provider 的产物是「ADSP 在跑 + GLINK 可用」两件事；剩下全是 consumer 侧。

### 0.1 载具 ABI（2026-11-15 定案）与音频的关系

adsp-handoff 线的容器提案已被 Lead 批准，ADSP 载体由 Lead 统一实现（内核内嵌 blob）。定案要素：

| 项 | 定案值 | 依据 |
|---|---|---|
| 头 | **12 字节**：`K60A` magic + `u32 count` + `u32 reserved` | `CARRIER-BLOB-PLAN.md:19` |
| 记录 | **24 字节顺序记录**：`{u32 nameLen, u32 mode, u64 size, u64 packedSize}`，26 条 | 同上 |
| 名字 | **带 NUL**（`adsp.mdt` / `adsp.bNN`，`nameLen=9`）；名字与 body 均 8 字节对齐 | 同上 |
| 总长 | **23,506,184 B** = A(12) + 26×(24 + A(9)) + ΣA(raw) = 16 + 1,040 + 23,505,128 | `CARRIER-BLOB-PLAN.md:105-118` |
| 内容 | 26 个 `adsp.*`：MDT 5,404 + b00–b23/b25（b24 纯 BSS，不落盘） | `CARRIER-BLOB-PLAN.md:27-61` |
| 待定 | `mode` / `size` 的生产语义（fixture 用 mode=0644、`size==packedSize`） | `CARRIER-BLOB-PLAN.md:23` |

**与现有 reader 线格式不兼容**：当前生产 reader 是 Metal 风格 flat 布局（8 字节头 + 10 字节记录 + 8 字节无 NUL 名字，总长 23,505,608 B），
对提案直接返回 `-7`（`CARRIER-BLOB-PLAN.md:21`）。生产 reader 的升级属 Lead scope，本文只登记事实。

**对音频的影响（四条，全部是无依赖）**：

1. **音频不读载体**。音频没有 `K60AdspRead` 句柄、不解析 blob、不关心记录格式；它只消费 provider 的成功结果
   （`lease.flags == 15` + 104 字节属性）。载体格式变与不变，音频侧零代码改动。
2. **载体把 ADSP 的启动时机从「Data 卷之后」提前到「内核内嵌、`vfs_mountroot` 之前」**，正好与 publish 的时序一致
   （`INTEGRATION-ORDER.md:35`：「Lead 的早期 carrier/SCM/资源路径已经可用；不得等待 rootfs」）——
   音频的等待窗口因此是确定的：`publish` 一返回就动手。
3. **载体 pin 生命周期属 provider**。契约要求 MDT 与全部 `.bNN`「stable、immutable 并 pin 至 `image_close`」
   （`PAS1-PROVIDER-CONTRACT.md:49`）；音频不持有任何 pin，也不得要求 provider 为音频延长 pin。
4. **内核尺寸 +23.5 MB**（Lead 已确认装得下）。音频侧只受镜像尺寸影响，不受运行时内存布局影响——音频不 map 载体。


---

## 1. GPR/APM 服务注册（Lead 点名的硬冲突点）

### 1.1 音频需要什么

- **GLINK 通道**：`adsp_apps`，intent **512 B × 20**。三方一致：`sm8450.dtsi:2811-2815`
  （`qcom,glink-channels = "adsp_apps"; qcom,intents = <512 20>`）、
  `references/pong-power/PongAudio.cpp:438`（`sheng_adsp_channel("adsp_apps",512,20,1,&client,nullptr)`）、
  `references/pong-power/ShengGpr.h` 头注释。
- **K60 实现**：按官方 power 页的 560 字节消息上限，`K60AudioGlink` 使用 560 B × 20（2026-11-18 起）；上面 512 是 vendor DT 与 Pong 参考的旧值。
- **协议头**：24 字节 GPR（`struct gpr_hdr`，`include/linux/soc/qcom/apr.h:79-90`），布局与我们 0504 的
  `pong_gpr_encode` 逐字一致（version/header 字数/总长 → dst_domain/src_domain → src_port → dst_port → token → opcode）。
- **首个交换**：`GET_SPF_STATE` 问 APM 是否 ready（应答 `APM_CMD_RSP_GET_SPF_STATE 0x02001007`，payload `{status}`，1 = ready）。
- **APM 端口**：src_port = dst_port = **1**（`GPR_APM_MODULE_IID` == `APM_MODULE_INSTANCE_ID`，
  `include/dt-bindings/soc/qcom,gpr.h:14`、`audioreach.h:41`；`audioreach.c:290` 的 `__audioreach_alloc_pkt(..., GPR_APM_MODULE_IID, ...)`）。
- **AFE 服务端口**：`dest_port = 0`（`q6afe.c:1094/1146/1300/1703/1848/1883` 六处）。

**协议选择（一处必须写死的判定）**：K60 走 **GPR**（24 字节头、域 ADSP=2 / APPS=3、APM 端口 1、GLINK 通道 `adsp_apps`），
不是 phk110 的 **APR**（12 字节头、域 4/5、`APR_SVC_AFE 4`、通道 `apr_audio_svc`，见 `hakios.adsp.c:2471,2489-2503`）。
`sm8450.dtsi` 里唯一的音频 GLINK 通道就是 `adsp_apps`（:2813），没有 `apr_audio_svc` 节点——**照 phk110 的 APR 写会连不上**。
`include/linux/soc/qcom/apr.h` 同时定义 `struct apr_hdr`（12 B，APR 服务栈）与 `struct gpr_hdr`（24 B，GPR 路由），两者不是同一层。

### 1.2 与 `K60AdspOwnerLease` 的 GLINK 独占（bit2）怎么仲裁（Lead 点名的硬冲突）

契约事实（2026-11-15 定稿版，`PAS1-PROVIDER-CONTRACT.md`）：

- flags 表（`:72`）：bit0 Authenticated / bit1 ResourcesHeld / **bit2 GlinkExclusive** / bit3 FreshHostFifos，**精确合计 15**。
- 排他义务（`:50`）：「禁止 reset/restart、**并行 GLINK worker**、掉票或 token 过期跨越解锁窗口」——这条约束的是 **provider 在 acquire 持有期内**的行为。
- 发布后（`:84`）：「Published 后 abort 是 no-op，**资源/token 持续保留**」；契约没有成功后的 release 入口，也**没有说 publish 之后只许一个通道**。
- 软件 lease 覆盖范围（`:80`）：「逻辑软件 lease 覆盖阶段 2–4 及阶段 5 的 commit」——音频在 publish 之后才动 GLINK，落在 lease 边界之外。

所以冲突不在「能不能开第二个通道」，而在**谁来开、开在哪一层**。两个方案都要写代价：

#### 方案 A（推荐）：同一个 `QcomGlink` 实例 + 第二个通道槽

状态（2026-11-17）：`drivers/PongPower/QcomGlink.h:17` 已是 `#define QCOM_GLINK_MAX_CHANNELS 2u`（原为 `1u`），
`:77` 的 `QcomGlinkChannel channel[QCOM_GLINK_MAX_CHANNELS]` 随之两槽；原型补丁 0002 已退役。传输层 `QcomGlink.c` **零改动**：
`grep channel[` 的全部命中都是按 `MAX_CHANNELS` 的循环或 `by_lcid`/`by_rcid` 的线性查找（`QcomGlink.c:112-150,202,218,341`），没有 `channel[0]` 直取。

代价（四条，都要让 provider 实现者知道）：

1. **跨线改动**：`drivers/PongPower/` 是 adsp-handoff 线 scope；用户 2026-11-17 已把该目录划给音频线，本次落地由音频线完成。
2. **内存**：两槽使 `sizeof(QcomGlink)` 从 960 B 涨到 2,056 B（每槽 904 B，含 20 个本地 intent 槽；宿主实测），对内核可忽略。
3. **provider 必须接受「publish 后有两个 consumer」这个事实**：PMIC 通道与音频通道共享同一对 SMEM FIFO、同一个 `qcom_glink_poll()` 循环与同一个 IPCC kick；
   但**每个槽的 intent 表、lcid/rcid、分片状态完全独立**（`QcomGlink.c:249-282` 按 rcid 分发），一个 consumer 卡住不会吃掉另一个的消息（宿主 376 条断言已证）。
4. **独占语义要改写一句**：bit2 约束 provider 自己，不约束 consumer 数量；契约第 7 条「交给既有 consumer」应读成「交给同一实例上的既有与新增槽」。

证据（已落地，可直接复核）：`drivers/PongPower/QcomGlink.h:17` 现为 `#define QCOM_GLINK_MAX_CHANNELS 2u`
（2026-11-17 音频线落地；历史原型补丁 `patches/audio/0002-k60-glink-multislot.patch` 已退役），
`drivers/PongPower/K60PmicGlink.cpp:128` 打印 `QcomGlink max_channels=2u local_intents=20 channel_bytes=904 audio_intent_bytes=11200` 构建标签；
`drivers/PongAudio/tests/test-glink-multislot.c`（两个消费者各注册 `PMIC_RTR_ADSP_APPS` 与 `adsp_apps`，
自扮 DSP 做 OPEN/advertise/TX_DATA，断言各收各的 rx、乱序 open 不串、重放不串、陌生名字不给 ACK、陌生 rcid 计入
`dropped`、`stop` 两槽各回调一次；runner 直接编译真实源，`sh drivers/PongAudio/tests/run-glink-multislot-tests.sh`
→ `TESTS OK 376 cases`）。详见 `GLINK-MULTISLOT.md`。

#### 方案 B：provider 把 GPR/APM 的 open 也纳入自己

做法：provider 在 publish 后自己 `qcom_glink_channel("adsp_apps", 560, 20, ...)`，向音频暴露一对 send/receive API
（GPR 帧、token、intent 全由 provider 管）；音频不再直接碰传输层。

代价（五条）：

1. **B 不省传输层改动**：provider 内部仍需同一实例的第二槽（另起第二个实例会踢坏 FIFO——`qcom_glink_adopt()` 采纳的是同一份
   APSS 索引已归零的 FIFO，`QcomGlink.h:86`），所以 A 的槽位工作 B 也要做。
2. **provider 从「传输/所有权所有者」变成「协议参与者」**：要解析 24 字节 GPR 头、分配 token、处理 `RX_INTENT_REQ`/`READ_NOTIF`/
   `INTENT` 重放、维护 per-channel 分片状态。这些逻辑 `QcomGlink.c` 已经实现且被宿主测试覆盖，搬进 provider 等于复制一遍并让两条线共同维护。
3. **音频仍要 lease 语义**：发包主体还是音频（AFE 六步的时序、失败回滚、静音都在音频侧），provider 只是代发；`revalidate`/epoch 检查一步都不能少。
4. **故障定位被切两段**：provider 说「收发正常」、音频说「DSP 回非 0」，中间多一层要联合排查；而 A 的边界是「GLINK 传输正确」与「AFE 参数正确」各测各的。
5. **与契约措辞冲突**：第 7 条说 provider「不再运行竞争 worker」；B 让 provider 变成长期跑 RX 循环的 worker，语义上要从「移交」改成「代理」，契约得再改一次。

**仲裁结论（一句话给 provider 实现者）**：音频不做第二个 GLINK owner、也不要求 provider 当代理；publish 之后音频是既有实例上的
第二个 consumer，发包前 revalidate；provider 只需接受 `QCOM_GLINK_MAX_CHANNELS` 为 2（2026-11-17 已落地）—— 不需要新 API、新锁或新 worker。
方案 B 只在 provider 明确不愿意暴露多槽时才考虑，代价比 A 大。

**裁决（2026-11-15，Lead）**：采纳方案 A——provider 只把 `QCOM_GLINK_MAX_CHANNELS` 扩到 2，不给新 API、新锁、新 worker；「音频不做第二个 owner」由 adsp-handoff 线写进契约；方案 B 封存。2026-11-17 传输层已落成 `2u`，0002 退役；`adsp_apps` consumer 注册仍待 provider 线。可勾选交接清单见 §9。

### 1.3 GPR 常量真值 vs 0504 现值（三处已于 2026-11-15 修正）

| 常量 | mainline 真值 | `ShengGpr.h` | 0504 现值（已修正） | 判定 |
|---|---|---|---|---|
| `GPR_VERSION` | `GPR_PKT_VER 0x0`（`apr.h:104`） | `0u` | `0u`（0504:121） | 已修正；曾为 `3u`——头低 4 位是版本，DSP 只认 0 |
| `GPR_OP_BASIC_RESULT` | `GPR_BASIC_RSP_RESULT 0x02001005`（`apr.h:108`） | `0x02001005u` | `0x02001005u`（0504:127） | 已修正；曾为 `0x02000002u` |
| `GPR_OP_APM_GET_SPF_STATE` | `APM_CMD_GET_SPF_STATE 0x01001021`（`audioreach.h:38`） | `0x01001021u` | `0x01001021u`（0504:128） | 已修正；曾为 `0x0100100Du`，那是 `APM_CMD_SHARED_MEM_UNMAP_REGIONS`（`audioreach.h:62`） |
| `GPR_HEADER_BYTES` | 24（`sizeof(struct gpr_hdr)`） | `24u` | `24u`（0504:122） | 一致 |
| `GPR_DOMAIN_ADSP` / `APPS` | 2 / 3（`qcom,gpr.h:9-10`） | `2u` / `3u` | `2u` / `3u`（0504:124-125） | 一致 |
| `GPR_PORT_APM` | 1（`audioreach.h:41`） | `1u` | `1u`（0504:126） | 一致 |
| APM 应答 | `APM_CMD_RSP_GET_SPF_STATE 0x02001007`（`audioreach.h:39`） | `0x02001007u` | 同 | 一致 |
| 最大包 | — | `GPR_MAX_PACKET 512u` | 同 | 一致（`adsp_apps` intent 也是 512 B） |

**已修正**（2026-11-15，Lead 批准的定向解冻）：`patches/xnu/0504-k60-audio-pong-audio.patch` 由 `diff -u` 重新生成，只动这三行常量，补丁仍是 973 行 / 29,471 B（三处等长替换，sha256 `d2642742010209693ded8c4a36a9c94f949757ada91651d218deded40bc99963`），`scripts/check-patch-apply.py` 通过（P-162）。宿主侧由 `drivers/PongAudio/tests/test-pong-audio-geni-i2c.c` 的 `afe_gpr_cases()` 钉死三值：`PONG_AFE_GPR_VERSION == 0`、`PONG_AFE_GPR_BASIC_RSP_RESULT == 0x02001005`、`PONG_AFE_GPR_APM_GET_SPF_STATE == 0x01001021`，改回旧值即红（`PongAudioAfe.h:88-95` 是这些常量的宿主副本）。

---

## 2. PAS1 未就绪时音频怎样降级

已有范式（逐字，`drivers/PongAudio/PongCodecProbe.c:37-41`）：

```c
if (!lpass_ready) {
	/* The three votes are the Lead's, not ours. Refusing here means
	 * the caller gets a named reason instead of a bus hang. */
	p->error = PongCodecProbeErrLpass;
	return -1;
}
```

speaker 路径（TERT TDM）照同一形态，逐级降级：

| 阶段 | 条件 | 音频行为 | 具名错误（已实现） |
|---|---|---|---|
| 门控 | `pong_audio=0` | 不起线程，零副作用 | — |
| handoff | `/chosen/k60-adsp-glink-handoff` 缺失 / 长度 != 104 / flags != 15 | 不 adopt FIFO、不开通道、**零寄存器访问** | `PongAudioErrNoHandoff` (-2001) |
| lease | acquire 未跑或返回 `K60_ADSP_OWNER_UNAVAILABLE (-1000)` | 同上 | `PongAudioErrNoLease` (-2002) |
| epoch | `revalidate` 失败或 epoch 变化 | 停发新包；in-flight 包等应答或超时 | `PongAudioErrStaleLease` (-2003) |
| APM | `GET_SPF_STATE` 超时或 `status != 1` | 不发任何 AFE 参数，**不碰 TLMM 引脚复用** | `PongAudioErrApmNotReady` (-2004) |
| AFE | 任一 `SET_PARAM_V2` 返回非 0 status | 逆序回滚已下发的参数（group disable → clock off），一次失败即停 | `PongAudioErrAfeRefused` (-2005) |
| 探针/回放 | 与 PAS1 无关（GENI 直连 SE15） | 照常走 `pong_audio_probe=1` 的只读 + 回放路径 | — |

三条要点：

1. **零寄存器访问**。`PongCodecProbeErrLpass` 的原话是「the three votes are the Lead's, not ours」——TDM 引脚复用、AFE 参数同理，
   全是 ADSP 侧资源；PAS1 没好之前一个寄存器都不碰（含 TLMM）。
2. **具名错误**。调用方拿枚举原因，不是总线挂死。枚举在 `drivers/PongAudio/PongAudioAfe.h:55-100`，值与名字由 `status_cases()` 钉住（`PongAudioErrNoLease = -2002`）。
3. **不重试风暴**。APM 不 ready 时一次失败即停，等下一次显式触发；与回放层 `transfer_run()` 的有界等待同一形态。

### 2.1 `-1000` 的具体形态（`pong_audio_probe=1` 下到底会发生什么）

先分清三个码（`PAS1-PROVIDER-CONTRACT.md:90-94`、`CARRIER-BLOB-PLAN.md:77`、`INTEGRATION-ORDER.md:56`）：

| 音频看到的 | 来自 | 含义 |
|---|---|---|
| `-1000`（`K60_ADSP_OWNER_UNAVAILABLE`） | 直接调 `k60_adsp_owner_acquire()`，且 ops/image_reader 未安装或平台不可用 | wrapper 清零 lease，**早于任何 SMEM/TCSR mapping**；没有 ADSP、没有 GLINK |
| `-42`（`K60PublishPasFailed`） | runtime 在 `pong_handoff_publish` 路径上的映射 | provider 起了但 PAS1/发布失败；属性不会出现 |
| `-4`（`K60ConfigNoOwnership`） | 一次性 consumer 读属性时 | 属性缺失；默认门控保持关闭 |

对音频的含义（**结论：codec-only 路径照走，ADSP 路径整段跳过**）：

1. **回放层与 PAS1 无关，必须继续跑**。`pong_audio_probe=1` 的 60 步 AMP 回放（软复位 + 57 对 Music profile +
   fuse 算出的 vcalb + 静音音量）走 GENI/SE15 I2C，不经过 ADSP、不需要 lease、不碰 GLINK。`-1000` 时它仍是唯一能产出
   证据的路径（`AMPS.md` §9）。回放层结束保持功放掉电/静音（PWDN/AMPPD/HMUTE 保留、ULS_HMUTE 置位、TXEN 清零），
   **没有 bit clock 不会出声**。
2. **ADSP 侧整段跳过，但必须打印具名原因**。建议措辞（实现时按 `IOLog` 风格落地）：

```text
PongAudio: PAS1 owner unavailable (acquire rc=-1000); ADSP path disabled
PongAudio: codec-only path: amp probe + 60-step replay continue, AFE/GPR skipped
PongAudio: speaker path unavailable: PongAudioErrNoLease (no GLINK, no AFE)
PongAudio: no handoff property; GLINK adopt skipped
```

   前两行给「降级了、但 codec 侧照常」；后两行给「为什么没有声音」的具名原因。不要打印成
   `PongAudio: skeleton stage=ADSP_WINDOWS (PAS1 loader TODO)` 这类含糊行——那会把「没有 provider」和「provider 坏了」混在一起。
3. **不重试、不等待、不轮询属性**。契约明说缺属性的一次性 consumer「在映射前返回 `-4`，不自动等待晚到属性」（`:94`）。
   音频同样：一次 acquire 失败即定案，本次启动不再尝试；下一次显式触发（重启或 `pong_audio_probe=1` 再跑）才重新探测。
4. **不许把 codec-only 当成功**。`pong_audio_status()` 必须能区分「AMP 回放完成」与「speaker 通路可用」：
   前者 success，后者 `PongAudioErrNoLease`。⑧ 的判据仍然需要 PAS1 + AFE + 出声，codec-only 不推进 ⑧。

## 3. AFE 参数下发在时序里的位置（Lead 问题 ③ / 2026-11-15 追问）

**结论：`acquire` 之后、`publish` **之后**——即 consumer 侧；具体姿势是「lease 有效期内 + `adsp_apps` 通道 up + APM `GET_SPF_STATE` 返回 ready 之后」。**

论证：

1. 契约时序（`INTEGRATION-ORDER.md:34-40` 的五阶段/六步边界表）：runtime preflight → 阶段1 claim（缺依赖 `-1000`
   早于 mapping）→ 阶段2 stopped prepare → 阶段3 六步1 PAS1（INIT → MEM_SETUP → COPY/BSS/CACHE → AUTH_AND_RESET）→ 阶段4 六步2 SMP2P（item 443 ready）
   → 六步3–5 最终 TCSR（build_existing + self-parse）→ 阶段5 六步6 publish（commit 原子无覆盖写 104 字节），「同步返回、IOBSD、physical battery，
   因此也早于 setconf/root 挂载」（`:40`）。**acquire 与 publish 之间是 provider 的逻辑 lease 区间**，排他义务（`PAS1-PROVIDER-CONTRACT.md:50`）
   明说排斥一切并行 worker——此时发 AFE 参数就是违反独占。
2. AFE 参数的物理载体是 GPR over GLINK。GLINK 的 adopt 依据正是 `/chosen/k60-adsp-glink-handoff` 那 104 字节
   （线格式见 `K60BatteryConfig.h:36-45`：magic `0x4842364b`、version 1、bytes 104、flags、epoch、SMEM/ADSP 基址、
   desc/TX/RX 偏移、`host_tx_head`/`host_rx_tail`/remote PID 2/SMP2P item 443）。**publish 之前这个属性不存在，音频连 FIFO 都没得用。**
3. 所以 AFE 参数下发属于 **consumer 侧**，不在 provider 内部：provider 只保证「ADSP 在跑 + GLINK 交出来」，
   不替任何消费者发协议包。音频在属性就位后自己 adopt、建 `adsp_apps` 槽、`GET_SPF_STATE`、再发 `TDMS.md` §3 的参数包。
4. 文字时序（加了「lease 有效期」与「通道 up」两道门）：

```text
provider:  acquire(flags==15) -> SMP2P(443) -> TCSR -> /chosen(104B) -> publish
                                                                  |
consumer:                                                          v
           adopt FIFO -> 建槽 "adsp_apps"(560x20) -> 等 channel up
           -> GET_SPF_STATE(status==1) -> AFE 六步(TDMS §3)
           每一步发包前 revalidate(lease) 且 epoch 未变
```

5. 与 `PongCodecProbe` 的关系：codec 侧的 `lpass_ready` 入参就是这条时序的上游信号——
   `pong_codec_probe_start(..., bool lpass_ready, ...)`（`PongCodecProbe.h:95-103`）已经把它做成了参数，
   speaker 路径同样应把「PAS1 就绪」做成入参而不是内部等待。

### 3.1 三道门（缺一不发包）

| 门 | 判据 | 不满足时 |
|---|---|---|
| 属性门 | `/chosen/k60-adsp-glink-handoff` 存在、精确 104 B、flags == 15 | 不 adopt、不建槽（§2 降级表 handoff 行） |
| lease 门 | `k60_adsp_owner_revalidate(&lease)` 返回 0 且 `lease.epoch` 未变 | 停发、静音、`PongAudioErrStaleLease`（不重试） |
| 协议门 | `adsp_apps` 槽 `up == 1`（state 回调）且 `GET_SPF_STATE` 应答 `status == 1` | `PongAudioErrApmNotReady`；六步一步都不发 |

建槽必须先于 DSP 的 OPEN（`QcomGlink.c:331-364` 找不到同名 used 槽就把 OPEN 当 unknown 丢弃），
所以「adopt → 建槽」要在第一次 `qcom_glink_poll()` 之前完成，不能等第一条消息。

### 3.2 中途失效：哪一步能重试，哪一步必须整段重来

| 情况 | 能否就地重试 | 动作 |
|---|---|---|
| `qcom_glink_send()` 返回 `QcomGlinkAgain`（无远端 intent 或 FIFO 满） | **能**，同一步有界重试 | poll 一轮后重发同一份字节流，不推进步骤；超过有界次数 → 按「某步失败」处理 |
| 某步 `BASIC_RESULT` 的 status != 0 | 不能 | 逆序回滚（group disable → clock off），`PongAudioErrAfeRefused`；下次整段重来 |
| `revalidate` 失败 或 epoch 变化 | **不能** | 立即停发、静音、`PongAudioErrStaleLease`；重新 acquire 后**从 clock 第一步整段重来** |
| 重新 acquire 后 `GET_SPF_STATE` 仍不 ready | 不能 | 等下一次显式触发，不自行轮询 |
| 包本身格式错（版本/长度/字段） | 不能 | 宿主 `afe_gpr_cases()` 已钉死，运行期视为 bug，不出包 |

**为什么 lease 失效必须整段重来**：契约的软件 lease 覆盖阶段 2–5（`PAS1-PROVIDER-CONTRACT.md:80`），publish 后 `abort` 是 no-op、
资源/token 持续保留（`:84`），但「新启动、DSP crash/reset 后的恢复协议未实现」（`:84`）。也就是说 lease 失效时
**无法证明 DSP 侧 AFE 状态还在**；六个包都很便宜（每个 ≤ 52+payload 字节、一次往返），重发整段比「猜哪一步还有效」安全得多。
反过来，传输层 `Again` 与 DSP 状态无关，纯粹是 intent/FIFO 的流控，所以可以就地重试。

**一句话**：**传输层可重试，协议/所有权层的失效一律整段重来。**

## 4. `TDMS.md` §8 五条的机器可读版

`status`: `proven` = 证据已闭环；`pending` = 待实测/待实现。

```toml
[[requirement]]
id = "afe-after-pas1"
claim = "AFE 参数（TDMS §3 全套）只能在 PAS1 + GPR/APM 起来之后发"
evidence = "docs/research/audio/ADSP-PAS1.md:38-44; PAS1-PROVIDER-CONTRACT.md:50,80,84; INTEGRATION-ORDER.md:34-40; 本文 §3"
status = "proven"

[[requirement]]
id = "afe-ports"
claim = "端口 0x9020（TERT_TDM_RX_0）+ 组 0x9120；0x9022 不入组（K60 DT group-num-ports=1）"
evidence = "live-fdt.dts:20588-20596; docs/research/audio/VENDOR-AUDIO-CONFIG.md §1/§2"
status = "proven"

[[requirement]]
id = "afe-clock-attribute"
claim = "时钟 0x204（TERT_TDM_IBIT）、attribute 4、12.288 MHz（48k×32×8）由 PRM 请求发出"
evidence = "V: audio_prm.h:457,570; V: msm_common.c:407-417; pong_afe_prm_clock_request() + afe_prm_cases()"
status = "proven"

[[requirement]]
id = "io-submap-no-lpaif"
claim = "TERT TDM 的 LPAIF 窗不在 PongCodecPlan.h 五窗里；混合方案只需现有 TLMM 窗"
evidence = "drivers/PongAudio/PongCodecPlan.h:249-292; PongAudioRegs.h:23-26; TDMS.md §8.4"
status = "proven"

[[requirement]]
id = "slot-mapping-consistency"
claim = "slot 数/位宽与 slot mapping offsets 必须与 AFE 参数一致，否则两颗 PA 交换声道"
evidence = "docs/research/audio/TDMS.md §6; phk110 hakios.sound.c:453-461（slots 2 / bits 32 / offsets {0,4}）"
status = "pending"

[[requirement]]
id = "glink-second-channel"
claim = "音频复用同一 QcomGlink 实例的第二个通道槽，不另起实例、不做第二个 owner"
evidence = "QcomGlink.h:17,77; K60PmicGlink.cpp:84,128; GLINK-MULTISLOT.md; 本文 §1.2"
status = "pending"

[[requirement]]
id = "gpr-constants-fix"
claim = "0504 的三处 GPR 常量已按 mainline 修正（VERSION 0 / BASIC_RESULT 0x02001005 / GET_SPF_STATE 0x01001021），宿主断言钉死"
evidence = "apr.h:104,108; audioreach.h:38,39,62; ShengGpr.h:14,19,20; 0504:121,127,128; PongAudioAfe.h:88-95; test-pong-audio-geni-i2c.c afe_gpr_cases(); 本文 §1.3"
status = "proven"

[[requirement]]
id = "carrier-abi-audio-none"
claim = "内核内嵌载体（12 B 头 + 24 B 记录 + NUL 名字，23,506,184 B）对音频透明：音频不读载体、不持有 pin，只消费 provider 的 flags==15 与 104 字节属性"
evidence = "CARRIER-BLOB-PLAN.md:19,21,23,61,105-118; PAS1-PROVIDER-CONTRACT.md:49,72,84; INTEGRATION-ORDER.md:35; 本文 §0.1"
status = "proven"

[[requirement]]
id = "glink-arbitration-two-options"
claim = "GPR/APM 与 bit2 的仲裁已由 Lead 裁定（2026-11-15）：采纳方案 A 同实例第二槽（QcomGlink.h:17 两处常量 1u→2u 与 4→20、两槽 +1,096 B），方案 B provider 代理 GPR 封存；传输层上限与 MAX_LOCAL_INTENTS 2026-11-17 已由音频线落成，音频侧已用 K60AudioGlink 注册 adsp_apps（清单见 §9.2）"
evidence = "PAS1-PROVIDER-CONTRACT.md:50,72,80,84; QcomGlink.h:17,77,86; QcomGlink.c:112-150,249-282,331-364; drivers/PongPower/K60PmicGlink.cpp:128; test-glink-multislot.c; Lead 2026-11-15 reply md 裁决; 本文 §1.2/§9"
status = "pending"

[[requirement]]
id = "afe-live-lease"
claim = "AFE 六步必须在 lease 有效期内、adsp_apps 通道 up、SPF ready 之后发；传输层 Again 可就地重试，lease/epoch 失效必须整段重来"
evidence = "PAS1-PROVIDER-CONTRACT.md:80,84; INTEGRATION-ORDER.md:34-40; QcomGlink.c:331-364,490-525; 本文 §3.1/§3.2"
status = "proven"

[[requirement]]
id = "codec-only-without-pas1"
claim = "provider 返回 -1000 时音频必须仍跑 codec-only 路径（AMP 探测+60 步回放），打印具名原因，跳过 AFE/GPR，且不把 codec-only 当成功"
evidence = "PAS1-PROVIDER-CONTRACT.md:90,94; CARRIER-BLOB-PLAN.md:77; INTEGRATION-ORDER.md:56; PongCodecProbe.c:37-41; AMPS.md §9; 本文 §2.1"
status = "pending"

```

---

### 4.1 编码器（已落地）

`drivers/PongAudio/PongAudioAfe.h` 把 §3 的每个包编码成字节流：GPR 24 字节头（版本 0、头长 6 字、 域 3→2）、svc 与 port 两种 set-param 信封（各 16 字节）+ 12 字节参数块、五个参数结构（时钟 20 B、 组 TDM 44 B、组使能 4 B、端口 TDM 36 B、slot mapping 28 B）与 DEVICE_START（28 B）。纯函数、不写寄存器；`afe_cases()` 在宿主侧钉住 221 条断言，`afe_plan_cases()` 再用 61 条断言钉住 `pong_afe_step_packet()` 的六步完整包（总 956 例，其中 `ring_queue_cases()` 的 27 条钉住 `PongAudioRing.h` 的 SPSC 提交队列，`play_cases()` 的 32 条钉住 `PongAudioPlayback.h` 的 11 步播放图、9 条钉住八槽周期/超时）。provider 交出 GLINK 之后，consumer 侧只需要把 这些字节按 `pong_afe_step_*()` 给出的六步顺序交给传输层，不再自己算偏移。

## 5. provider 必须为 audio 保证什么（交给 provider 实现者的四条）

这四条是 §1.2 的落地版：每一条都能被实现者当成验收项，也能被 audio 侧当成失败原因。

1. **单实例多槽**：provider 不需要为音频新开 `QcomGlink` 实例。`drivers/PongPower/QcomGlink.h:17` 的
   `QCOM_GLINK_MAX_CHANNELS` 自 2026-11-17 起已是 `2u`（`:77` 的 `channel[QCOM_GLINK_MAX_CHANNELS]` 随之两槽），
   由同一个实例、同一个 `qcom_glink_poll()` 循环服务两个通道。**另起实例是错的**：一对 SMEM FIFO 是共享物理资源，
   `qcom_glink_adopt()`（`QcomGlink.h:86`）采纳的是同一份 APSS 索引已归零的 FIFO，两个实例会互相踢坏 intent 计数。（该方案 2026-11-15 已由 Lead 裁定采纳，可勾选清单见 §9。）

2. **建槽时机**：`qcom_glink_channel()` 必须在 DSP 发来 OPEN **之前**调用。`QcomGlink.c:331-364` 的 `case QCOM_GLINK_OPEN`
   按名字在 `channel[]` 里找已 used 的同名槽，找不到就 `unknown_opens++`、把名字记进 `last_unknown`、`note_unknown()` 后**丢弃**；
   找到才回 `QCOM_GLINK_OPEN_ACK` 并置 `remote_open`。所以音频侧在 publish 返回后立刻建 `adsp_apps`（560 B × 20 intent）槽，
   provider 只需保证 publish 成功时 FIFO 已就位、远端已 ready（SMP2P item 443）。

3. **独占语义改写**：`lease.flags` 的 bit2 `GlinkExclusive` 约束的是 **acquire 持有期内的 provider 自己**
   （契约第 3 条），不是「publish 之后只许一个 consumer」。契约第 7 条把 GLINK「交给既有 consumer」，且**没有成功后的 release 入口**——
   音频也不需要 release。正确读法是「单实例多槽」，而不是「第二个实例不许进」。provider 不需要为音频新增任何 API、锁或 worker。

   契约 2026-11-15 定稿版已按此读法自洽：flags 表在 `PAS1-PROVIDER-CONTRACT.md:72`，排他义务只约束 provider
   （`:50`），publish 后 `abort` 是 no-op、资源/token 持续保留（`:84`），软件 lease 只覆盖阶段 2–5（`:80`）；
   两种仲裁方案的代价对比见 §1.2（方案 B 是备选，不推荐）。

4. **发包时机**：AFE 参数（`TDMS.md` §3 的六步、`PongAudioAfe.h` 的字节）在 **publish 之后由 consumer 发**，
   provider 不替任何消费者发协议包、不解析 GPR、不碰 `adsp_apps` 通道内容。provider 的交付物只有三样：
   ADSP 在跑（PAS1 认证与 load 完成）、GLINK FIFO 可用（SMP2P 443 ready）、`/chosen/k60-adsp-glink-handoff` 的 104 字节属性就位。

## 6. 交付边界

- 本文是**需求文档**，不是实现：不加 `PongAudioErr*` 枚举（§2）、不动 `QcomGlink`（§1.2，扩槽属 provider 与音频的共同 scope，见 §5 第 1 条）。
  0504 的三处 GPR 常量已在 2026-11-15 的定向解冻里修正（§1.3），除此之外 0504 未动。
- battery 契约文件（`PAS1-PROVIDER-CONTRACT.md`、`INTEGRATION-ORDER.md`、`HANDOFF-PUBLISH.md`、`GLINK-HANDOFF.md`）
  属 adsp-handoff 线 scope，本文只引用。
- 与 `TDMS.md` 的分工：TDMS 管**硬件事实**（引脚/参数/编号），本文管**对 provider 的依赖与时序**（服务注册/降级/AFE 时序）。
- **载体**：ADSP 载具（12 B 头 + 24 B 记录 + NUL 名字、23,506,184 B、内核内嵌）由 Lead 实现，音频不读、不 pin；本文 §0.1 只登记它对
  时序/所有权的影响。音频与载体的接口只有一条：「provider 成功 + 104 字节属性」，没有别的耦合。

---

## 9. 交接给 provider 实现者（可勾选接口清单）

本节是给下一个写 PAS1 provider（或接线的 agent）看的独立清单：不引用本文其它章节，
每条自带出处、判据与失败动作。状态：2026-11-15 Lead 裁决采纳「单实例第二槽」方案后，
音频线转入待命；本节所列即 provider 交付后音频侧的接线顺序。

### 9.1 provider 必须提供什么（函数签名级）

C ABI（adsp-handoff 线定稿，`PAS1-PROVIDER-CONTRACT.md:9-28`）：

```c
int k60_adsp_owner_install(const K60OwnerOps *ops, void *context);
int k60_adsp_owner_acquire(const K60BatteryConfig *config, K60AdspOwnerLease *lease);
int k60_adsp_owner_revalidate(const K60AdspOwnerLease *lease);
void k60_adsp_owner_abort(const K60AdspOwnerLease *lease);
int k60_adsp_owner_publish(const K60AdspOwnerLease *lease,
    const K60OwnerPublishOps *ops, void *context);
```

`acquire` 顺序执行阶段 1–4（claim → prepare_pas1 → auth_and_start → build_handoff），
`publish` 执行阶段 5（`INTEGRATION-ORDER.md:42`）。音频只直接调用
`k60_adsp_owner_acquire` 与 `k60_adsp_owner_revalidate`；不调用 install、阶段 API 与 abort。

- [ ] acquire 返回 0 时 lease 必须满足：`version == 1`、`bytes == sizeof(K60AdspOwnerLease)`、
      `flags` 精确等于 15（bit0 Authenticated / bit1 ResourcesHeld / bit2 GlinkExclusive /
      bit3 FreshHostFifos，`PAS1-PROVIDER-CONTRACT.md:72`）、`epoch` 非零、
      `token` 非空且指向持久 session（`PAS1-PROVIDER-CONTRACT.md:68,74`）。
- [ ] publish 返回 0 时 `/chosen/k60-adsp-glink-handoff` 必须存在且精确 104 字节。线格式
      （`K60BatteryConfig.h:36-45`，little-endian）：magic `0x4842364b`@0、version 1@4、bytes 104@8、
      flags@12、**64 位 epoch@16**（native lease 的 u32 epoch 不能直接序列化进这里，`PAS1-PROVIDER-CONTRACT.md:68`）、
      SMEM base@24 / bytes@32、ADSP base@40 / bytes@48、desc offset@56 / bytes@60、tx offset@64 / bytes@68、
      rx offset@72 / bytes@76、host_tx_head@80（应为 0）、host_rx_tail@84（应为 0）、remote pid@88（=2）、
      smp2p item@92（=443）、restart flag@96、reserved@100。
- [ ] 缺依赖时 acquire 返回 `-1000`，且必须早于任何 SMEM/TCSR mapping 发生
      （`PAS1-PROVIDER-CONTRACT.md:34,90`；阶段 2/3 失败同样归一 `-1000`，阶段 4 失败
      为 -44/-45/-46/-47/-43，`:91`）。
- [ ] publish 的失败码：无效参数 -40、属性已存在 -41、root/ready/restart 不就绪 -43、
      最终 blob/epoch/live 复核失败 -47、其他 commit 失败 -48；失败不得先写属性
      （`PAS1-PROVIDER-CONTRACT.md:38,54,93`）。
- [ ] 音频不通过 `k60_adsp_owner_acquire` 之外的路由拿 lease；不读载体、不 map SMEM、不碰 TCSR。

### 9.2 provider 必须保证什么

- [ ] **lease 语义**：逻辑软件 lease 覆盖阶段 2–4 与阶段 5 的 commit（`PAS1-PROVIDER-CONTRACT.md:80`）。
      lease 有效期内 provider 不得 reset/restart ADSP、不得运行竞争 GLINK worker、不得让 votes/exclusion
      或 token 过期跨越任何解锁窗口（`PAS1-PROVIDER-CONTRACT.md:50`）。
- [ ] **epoch**：非零「当前启动」epoch，绑定 cookie、板级配置与 SMEM items（`PAS1-PROVIDER-CONTRACT.md:74`）；
      同一启动内多次 revalidate 的 epoch 不变，重启/复位后必须取得新的非零值。音频用 epoch 判断
      「手里的 lease 是否还是本启动的」。
- [ ] **revalidate 失败的行为**：必须同时验证真实 backend 仍 live，不能只凭 token 非空或 flags==15 授权
      （`PAS1-PROVIDER-CONTRACT.md:74`）；失败返回非 0，音频据此停发 AFE 包并静音。
- [ ] **publish 后没有 release 入口**：Published 后 abort 是 no-op，资源/token 持续保留
      （`PAS1-PROVIDER-CONTRACT.md:84`）；provider 不回收 FIFO、不删
      `/chosen/k60-adsp-glink-handoff`。音频也不需要 release。
- [ ] **单实例多槽（2026-11-15 Lead 裁决，方案 A；2026-11-17 已落地传输层）**：`drivers/PongPower/QcomGlink.h:17` 的
      `QCOM_GLINK_MAX_CHANNELS` 现为 2u，同一实例、同一 `qcom_glink_poll()` 循环、
      同一 IPCC kick 服务 `PMIC_RTR_ADSP_APPS`（电池）与 `adsp_apps`（音频）两个槽。
      不新开第二个 QcomGlink 实例（一对 SMEM FIFO 只有一个采纳者：`qcom_glink_adopt` 要求
      `*tx.head==0 && *rx.tail==0`）、不新增 API、锁或 worker；「音频不做第二个 owner」。
      宿主 376 条断言已证明 `QcomGlink.c` 零改动、两槽各自分发；**音频侧已经用 `K60AudioGlink.c`
      把 `adsp_apps`（560×20 intent）注册封装好（`pong_audio_start()` 排队，`K60PmicGlink::poll()`
      在 `qcom_glink_poll()` 前 service），provider 不再需要编写注册代码**。provider 只需按契约提供
      `k60_adsp_owner_acquire()` 的真 lease 与已采纳的 FIFO；这一项不再由音频侧代做。

### 9.3 音频侧拿到 lease 之后的调用顺序（每步附失败动作）

前置常量（consumer 侧，与 mainline 对齐）：GPR 头 24 字节、版本 0；域 ADSP=2 / APPS=3；
APM 端口 1；`GET_SPF_STATE 0x01001021`、`SPF_STATE 0x02001007`（payload status==1 即 ready）、
`BASIC_RSP_RESULT 0x02001005`；GLINK 通道名 `adsp_apps`、intent 560 B × 20。

顺序（0 → 6，任何一步失败按该步「失败时」执行，不跳步）：

0. **属性门**：读 `/chosen/k60-adsp-glink-handoff`。缺失 / 长度 != 104 / flags != 15 →
   打印 `PongAudio: no handoff property; GLINK adopt skipped`，跳过 1–6，codec-only 路径照走。
1. **lease 门**：`k60_adsp_owner_revalidate(&lease)` 返回 0 且 `lease.epoch` 与 acquire 时相同 → 继续。
   失败或 epoch 变 → `PongAudioErrStaleLease`，停发、静音，本次启动不再尝试。
2. **adopt**：用 104 字节属性里的 offset 构造 FIFO：`tx = {&desc[1], &desc[0], tx_bytes}`、
   `rx = {&desc[3], &desc[2], rx_bytes}`，调 `qcom_glink_adopt(&g, tx, rx, kick, ctx)`
   （`QcomGlink.h:86`）。要求 `*tx.head==0 && *rx.tail==0`，否则返回 Argument。
   失败 → 不碰 FIFO，打印具名原因，跳过 3–6。
3. **建槽**：在第一次 `qcom_glink_poll()` 之前、DSP 发 OPEN 之前调用
   `qcom_glink_channel(&g, "adsp_apps", 560, 20, storage, &client, ctx, 1)`
   （DSP 的 OPEN 按名字找已 used 槽，找不到就当 unknown 丢弃，`QcomGlink.c:331-364`）。
   返回 0（无槽）或 DSP 的 OPEN 先到 → 不重试 lease，报 `PongAudioErrNoLease` 类具名错误。
   音频侧已把这一步封装成 `K60AudioGlink`：`pong_audio_start()` 排队，`K60PmicGlink::poll()`
   在 `qcom_glink_poll()` 前调用 `k60_audio_glink_service()`；provider 不需要再写注册代码。
4. **协议门**：`qcom_glink_poll(&g)` 直到 `client.state(up=1)`；发 GPR `GET_SPF_STATE`
   （src_port=1、dst_port=1），等 `SPF_STATE` 且 payload status==1。
   超时或 status!=1 → `PongAudioErrApmNotReady`，一个 AFE 包都不发，等下一次显式触发。
5. **AFE 六步**：按 `drivers/PongAudio/PongAudioAfe.h` 的 `pong_afe_step_*` 顺序发六个包
   （Clock → GroupTdm → GroupEnable → PortTdm → SlotMapping → DeviceStart）。每个包已由该头编码成字节流
   （GPR 24 B 头 + svc/port 两种 16 B 信封 + 12 B 参数块，158 条宿主断言钉住偏移/端序），consumer 只负责按序交给
   传输层；每包等 `BASIC_RSP_RESULT` 且 status==0 再发下一包。六步参数值：
   - Clock：PRM 请求 `{clock_id 0x204, 12288000 Hz, attribute 4, root 0}`（48k × 32 × 8；`pong_afe_prm_clock_request()` 编 76 字节，opcode `0x0100100F`、src_port 7、dst_port 2）
- GroupTdm：组 0x9120、ports `{0x9020, 0x9022, 0xffff×6}`、2ch、48000、**24 bit**、2 slots、slot_bits 32、mask 3
- GroupEnable：`{0x9120, 1}`
- PortTdm：端口 0x9020、2ch、48000、**24 bit**、data_format 0、sync_mode 0、sync_src 1、slots 2、data_out 0、invert 1、delay 1、slot_bits 32、mask 3
- SlotMapping：2ch、32b、align 0、offsets `{0, 4, 0xffff×6}`
- DeviceStart：`{0x9020, 0}`
   失败时：`qcom_glink_send` 返回 Again → 同一步 poll 一轮后重发同一份字节流（有界次数）；
   `BASIC_RSP_RESULT` status!=0 → 逆序回滚（group disable → clock off），`PongAudioErrAfeRefused`；
   任一步前 revalidate 失败或 epoch 变 → 停发、静音，重新 acquire 后从 Clock 整段重来
   （恢复协议未实现，无法证明 DSP 侧 AFE 状态还在）。
6. **完成**：六步全绿后 speaker 通路可用；保持静音（无 bit clock 不出声）直到播放路径接通。

### 9.4 两条硬约束（2026-11-15 Lead 裁决）

- codec-only 成功**不推进 ⑧**：provider 返回 -1000 时，60 步 AMP 回放照走（GENI/SE15 I2C，与 PAS1 无关），
  但 `pong_audio_status()` 不得返回成功——必须返回 `PongAudioErrNoLease` 且带具名原因行。
  建议四行日志按以下原文落：

```text
PongAudio: PAS1 owner unavailable (acquire rc=-1000); ADSP path disabled
PongAudio: codec-only path: amp probe + 60-step replay continue, AFE/GPR skipped
PongAudio: speaker path unavailable: PongAudioErrNoLease (no GLINK, no AFE)
PongAudio: no handoff property; GLINK adopt skipped
```

- 仲裁已定：方案 A（单实例第二槽）为唯一方案，方案 B（provider 代理 GPR）封存。

---
来源：Lead m06642 / m07111 指令与 2026-11-15 reply md 裁决（§9）；行号实测于 2026-11-15。live FDT 副本 `/mnt/e/k60-work/scratch/audio-work/live-fdt.dts`（34,801 行，不入仓库）。
