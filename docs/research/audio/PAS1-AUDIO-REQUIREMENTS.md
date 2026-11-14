# PAS1-AUDIO-REQUIREMENTS — 音频线对 PAS1 provider 的依赖、降级与仲裁

状态行（沿用 CODEC.md 的 ①–⑧ 记法）：① 同型 ✅ ② 官方 ⚠️ ③ 反编译 ✅ ④ 广域 ✅ ⑤ 方案 ✅ ⑥ 深挖 ✅ ⑦ 本机验证 ⏳ ⑧ 上机 ❌

本文回答 Lead m06642 点名的三件事：**GPR/APM 服务注册与 GLINK 独占的仲裁**、**PAS1 未就绪时的降级形态**、
**AFE 参数下发在时序里的位置**；末尾是 `TDMS.md` §8 五条的机器可读版。
只写 `docs/research/audio/`；battery 线的契约文件（`PAS1-PROVIDER-CONTRACT.md`、`INTEGRATION-ORDER.md`、
`HANDOFF-PUBLISH.md`、`GLINK-HANDOFF.md`）属 adsp-handoff 线 scope，本文只引用不改。
行号均为 2026-11-15 实测；标 `待实测` 的条目本机没有对应源码或需要上机/构建后确认。

---

## 0. 音频对 provider 的依赖（总览）

| # | 依赖 | provider 要给什么 | 依据 |
|---|---|---|---|
| 1 | ADSP 在跑 | PAS1 载入 + `PAS_AUTH_AND_RESET` 成功；lease.flags 精确 == 15 | `PAS1-PROVIDER-CONTRACT.md:41`；`ADSP-PAS1.md:38-44` |
| 2 | GLINK 交出来 | publish 后把 `/chosen/k60-adsp-glink-handoff`（104 B）交给 consumer | 契约第 7 条（`PAS1-PROVIDER-CONTRACT.md:55`） |
| 3 | AFE 服务可达 | 不额外提供：音频自己发 GPR 参数包，不碰 LPAIF 寄存器 | `TDMS.md` §3；`q6afe.c:1080-1160` |

**provider 不需要替音频做的事**：不发 AFE 参数、不开 `adsp_apps` 通道、不碰 TLMM 引脚复用、不读 ACF。
provider 的产物是「ADSP 在跑 + GLINK 可用」两件事；剩下全是 consumer 侧。

---

## 1. GPR/APM 服务注册（Lead 点名的硬冲突点）

### 1.1 音频需要什么

- **GLINK 通道**：`adsp_apps`，intent **512 B × 20**。三方一致：`sm8450.dtsi:2811-2815`
  （`qcom,glink-channels = "adsp_apps"; qcom,intents = <512 20>`）、
  `references/pong-power/PongAudio.cpp:438`（`sheng_adsp_channel("adsp_apps",512,20,1,&client,nullptr)`）、
  `references/pong-power/ShengGpr.h` 头注释。
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

### 1.2 与 `K60AdspOwnerLease` 的 GLINK 独占（bit2）怎么仲裁

契约原文（不可改，属 adsp-handoff 线）：

- 第 3 条（`:51`）：「acquire 返回后，provider **排斥其他 GLINK worker、复位/重启和资源撤销路径**。pin 必须覆盖所有 revalidate 之间的解锁窗口」。
- 第 7 条（`:55`）：「提交成功后，GLINK 交给既有 consumer，provider 不再运行竞争 worker，资源/token/epoch 必须持续保留。**本 API 没有成功后的 release 入口**」。
- `lease.flags` 必须精确 == `K60AdspHandoffRequired` == 15（bit0 Authenticated、bit1 ResourcesHeld、**bit2 GlinkExclusive**、bit3 FreshHostFifos）。

判定分四步：

1. **bit2 约束的是 acquire 持有期内的 provider**，不是 publish 之后的 consumer。契约第 7 条把 GLINK「交给既有 consumer」；
   音频在 publish 之后开 `adsp_apps` 属于 consumer 行为，不是第二个 provider worker，**不违反第 3 条**。
2. **但现有传输层只有一个通道槽**：`drivers/PongPower/QcomGlink.h:17` `#define QCOM_GLINK_MAX_CHANNELS 1u
   /* exclusively leased K60 PMIC endpoint */`、`:77` `QcomGlinkChannel channel[QCOM_GLINK_MAX_CHANNELS]`；
   `K60PmicGlink.cpp:84` 已占该槽开 `PMIC_RTR_ADSP_APPS`。音频要开 `adsp_apps`，**必须把上限改到 2 或另起实例**——
   这是音频线自己的改动（`drivers/PongAudio/` + `QcomGlink.h` 一处常量），**不动 battery 的契约与 consumer**。
3. **FIFO 是共享物理资源，绝不能另起实例**：一对 SMEM FIFO（`qcom_glink_adopt` 采纳 APSS 索引已归零的 FIFO，`QcomGlink.h:86`），
   两个实例会互相踢坏对方的消息与 intent 计数。**仲裁方式 = 一个 `QcomGlink` 实例、两个通道槽、一个 poll 循环**：
   PMIC 通道照旧，音频通道在 publish 之后才 open（`open_now` 由 consumer 决定）。
4. **revalidate 窗口内不发包**：契约要求 pin 覆盖所有解锁窗口。实现上由 consumer 在每次发包前调用
   `k60_adsp_owner_revalidate(&lease)` 并核对 epoch 未变；失败即停发（降级见 §2），不新增锁、不新增 provider API。

一句话给 provider 实现者：**音频不做第二个 GLINK owner；音频是 publish 之后的 consumer，
复用同一个 QcomGlink 实例的第二个通道槽，发包前 revalidate。**

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

speaker 路径（PRI_TDM）照同一形态，逐级降级：

| 阶段 | 条件 | 音频行为 | 具名错误（待实现，值待排） |
|---|---|---|---|
| 门控 | `pong_audio=0` | 不起线程，零副作用 | — |
| handoff | `/chosen/k60-adsp-glink-handoff` 缺失 / 长度 != 104 / flags != 15 | 不 adopt FIFO、不开通道、**零寄存器访问** | `PongAudioErrNoHandoff` |
| lease | acquire 未跑或返回 `K60_ADSP_OWNER_UNAVAILABLE (-1000)` | 同上 | `PongAudioErrNoLease` |
| epoch | `revalidate` 失败或 epoch 变化 | 停发新包；in-flight 包等应答或超时 | `PongAudioErrStaleLease` |
| APM | `GET_SPF_STATE` 超时或 `status != 1` | 不发任何 AFE 参数，**不碰 TLMM 引脚复用** | `PongAudioErrApmNotReady` |
| AFE | 任一 `SET_PARAM_V2` 返回非 0 status | 逆序回滚已下发的参数（group disable → clock off），一次失败即停 | `PongAudioErrAfeRefused` |
| 探针/回放 | 与 PAS1 无关（GENI 直连 SE15） | 照常走 `pong_audio_probe=1` 的只读 + 回放路径 | — |

三条要点：

1. **零寄存器访问**。`PongCodecProbeErrLpass` 的原话是「the three votes are the Lead's, not ours」——TDM 引脚复用、AFE 参数同理，
   全是 ADSP 侧资源；PAS1 没好之前一个寄存器都不碰（含 TLMM）。
2. **具名错误**。调用方拿枚举原因，不是总线挂死。枚举放 `drivers/PongAudio/`（新头或 `PongAudioRegs.h` 扩展），值在实现时排定。
3. **不重试风暴**。APM 不 ready 时一次失败即停，等下一次显式触发；与回放层 `transfer_run()` 的有界等待同一形态。

---

## 3. AFE 参数下发在时序里的位置（Lead 问题 ③）

**结论：`acquire` 之后、`publish` **之后**——即 consumer 侧，publish 完成之后。**

论证：

1. 契约时序（`INTEGRATION-ORDER.md:39-44`）：1 PAS1 acquire+revalidate → 2 SMP2P item 443 ready → 3–5 TCSR 最终临界区
   （partition、32 字节全零 descriptor、`build_existing`、self-parse）→ 6 解锁后复核并 `setProperty /chosen/k60-adsp-glink-handoff`（精确 104 B）
   → 然后才 `publishResource(IOBSD)` 与 `k60_physical_battery_start()`，因此也早于 `setconf()`/`vfs_mountroot()`。
   **acquire 与 publish 之间是 provider 的临界区**，第 3 条明说排斥一切其他 worker——此时发 AFE 参数就是违反独占。
2. AFE 参数的物理载体是 GPR over GLINK。GLINK 的 adopt 依据正是 `/chosen/k60-adsp-glink-handoff` 那 104 字节
   （线格式见 `K60BatteryConfig.h:36-45`：magic `0x4842364b`、version 1、bytes 104、flags、epoch、SMEM/ADSP 基址、
   desc/TX/RX 偏移、`host_tx_head`/`host_rx_tail`/remote PID 2/SMP2P item 443）。**publish 之前这个属性不存在，音频连 FIFO 都没得用。**
3. 所以 AFE 参数下发属于 **consumer 侧**，不在 provider 内部：provider 只保证「ADSP 在跑 + GLINK 交出来」，
   不替任何消费者发协议包。音频在属性就位后自己 adopt、开 `adsp_apps`、`GET_SPF_STATE`、再发 `TDMS.md` §3 的参数包。
4. 文字时序：

```
provider:  acquire(flags==15) → SMP2P(443) → TCSR → /chosen(104B) → publish
                                                                  │
consumer:                                                         ▼
           adopt FIFO → open "adsp_apps"(512×20) → GET_SPF_STATE → AFE 六步(TDMS §3)
           revalidate 每次发包前
```

5. 与 `PongCodecProbe` 的关系：codec 侧的 `lpass_ready` 入参就是这条时序的上游信号——
   `pong_codec_probe_start(..., bool lpass_ready, ...)`（`PongCodecProbe.h:95-103`）已经把它做成了参数，
   speaker 路径同样应把「PAS1 就绪」做成入参而不是内部等待。

---

## 4. `TDMS.md` §8 五条的机器可读版

`status`: `proven` = 证据已闭环；`pending` = 待实测/待实现。

```toml
[[requirement]]
id = "afe-after-pas1"
claim = "AFE 参数（TDMS §3 全套）只能在 PAS1 + GPR/APM 起来之后发"
evidence = "docs/research/audio/ADSP-PAS1.md:38-44; PAS1-PROVIDER-CONTRACT.md:51,55; INTEGRATION-ORDER.md:39-44; 本文 §3"
status = "proven"

[[requirement]]
id = "afe-ports"
claim = "端口 0x9000（PRI_TDM_RX_0）+ 组 0x9100；0x9002 不入组（K60 DT group-num-ports=1）"
evidence = "live-fdt.dts:20486-20506; docs/research/audio/TDMS.md §3/§5"
status = "proven"

[[requirement]]
id = "afe-clock-attribute"
claim = "CLOCK_PRI_TDM_IBIT 0x200 与 attribute 的对应关系"
evidence = "phk110 hakios.sound.c:342,423-425（attribute 4，48k*32*2=3.072MHz）; K60 DT clk-rate 0x177000=1.536MHz; PRM 投票 RESEARCH.md:25-55"
status = "pending"

[[requirement]]
id = "io-submap-no-lpaif"
claim = "PRI_TDM 的 LPAIF 窗不在 PongCodecPlan.h 五窗里；混合方案只需现有 TLMM 窗"
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
evidence = "QcomGlink.h:17,77; K60PmicGlink.cpp:84; 本文 §1.2"
status = "pending"

[[requirement]]
id = "gpr-constants-fix"
claim = "0504 的三处 GPR 常量已按 mainline 修正（VERSION 0 / BASIC_RESULT 0x02001005 / GET_SPF_STATE 0x01001021），宿主断言钉死"
evidence = "apr.h:104,108; audioreach.h:38,39,62; ShengGpr.h:14,19,20; 0504:121,127,128; PongAudioAfe.h:88-95; test-pong-audio-geni-i2c.c afe_gpr_cases(); 本文 §1.3"
status = "proven"
```

---

### 4.1 编码器（已落地）

`drivers/PongAudio/PongAudioAfe.h` 把 §3 的每个包编码成字节流：GPR 24 字节头（版本 0、头长 6 字、 域 3→2）、svc 与 port 两种 set-param 信封（各 16 字节）+ 12 字节参数块、五个参数结构（时钟 20 B、 组 TDM 44 B、组使能 4 B、端口 TDM 36 B、slot mapping 28 B）与 DEVICE_START（28 B）。纯函数、不写寄存器；`afe_cases()` 在宿主侧钉住 128 条断言（总 712 例）。provider 交出 GLINK 之后，consumer 侧只需要把 这些字节按 `pong_afe_step_*()` 给出的六步顺序交给传输层，不再自己算偏移。

## 5. provider 必须为 audio 保证什么（交给 provider 实现者的四条）

这四条是 §1.2 的落地版：每一条都能被实现者当成验收项，也能被 audio 侧当成失败原因。

1. **单实例多槽**：provider 不需要为音频新开 `QcomGlink` 实例。要求是把 `drivers/PongPower/QcomGlink.h:17` 的
   `QCOM_GLINK_MAX_CHANNELS` 从 `1u` 扩到 `2u`（`:77` 的 `channel[QCOM_GLINK_MAX_CHANNELS]` 随之变成两槽），
   由同一个实例、同一个 `qcom_glink_poll()` 循环服务两个通道。**另起实例是错的**：一对 SMEM FIFO 是共享物理资源，
   `qcom_glink_adopt()`（`QcomGlink.h:86`）采纳的是同一份 APSS 索引已归零的 FIFO，两个实例会互相踢坏 intent 计数。

2. **建槽时机**：`qcom_glink_channel()` 必须在 DSP 发来 OPEN **之前**调用。`QcomGlink.c:331-364` 的 `case QCOM_GLINK_OPEN`
   按名字在 `channel[]` 里找已 used 的同名槽，找不到就 `unknown_opens++`、把名字记进 `last_unknown`、`note_unknown()` 后**丢弃**；
   找到才回 `QCOM_GLINK_OPEN_ACK` 并置 `remote_open`。所以音频侧在 publish 返回后立刻建 `adsp_apps`（512 B × 20 intent）槽，
   provider 只需保证 publish 成功时 FIFO 已就位、远端已 ready（SMP2P item 443）。

3. **独占语义改写**：`lease.flags` 的 bit2 `GlinkExclusive` 约束的是 **acquire 持有期内的 provider 自己**
   （契约第 3 条），不是「publish 之后只许一个 consumer」。契约第 7 条把 GLINK「交给既有 consumer」，且**没有成功后的 release 入口**——
   音频也不需要 release。正确读法是「单实例多槽」，而不是「第二个实例不许进」。provider 不需要为音频新增任何 API、锁或 worker。

4. **发包时机**：AFE 参数（`TDMS.md` §3 的六步、`PongAudioAfe.h` 的字节）在 **publish 之后由 consumer 发**，
   provider 不替任何消费者发协议包、不解析 GPR、不碰 `adsp_apps` 通道内容。provider 的交付物只有三样：
   ADSP 在跑（PAS1 认证与 load 完成）、GLINK FIFO 可用（SMP2P 443 ready）、`/chosen/k60-adsp-glink-handoff` 的 104 字节属性就位。

## 6. 交付边界

- 本文是**需求文档**，不是实现：不加 `PongAudioErr*` 枚举（§2）、不动 `QcomGlink`（§1.2，扩槽属 provider 与音频的共同 scope，见 §5 第 1 条）。
  0504 的三处 GPR 常量已在 2026-11-15 的定向解冻里修正（§1.3），除此之外 0504 未动。
- battery 契约文件（`PAS1-PROVIDER-CONTRACT.md`、`INTEGRATION-ORDER.md`、`HANDOFF-PUBLISH.md`、`GLINK-HANDOFF.md`）
  属 adsp-handoff 线 scope，本文只引用。
- 与 `TDMS.md` 的分工：TDMS 管**硬件事实**（引脚/参数/编号），本文管**对 provider 的依赖与时序**（服务注册/降级/AFE 时序）。

---
来源：Lead m06642 / m07111 指令；行号实测于 2026-11-15。live FDT 副本 `/mnt/e/k60-work/scratch/audio-work/live-fdt.dts`（34,801 行，不入仓库）。
