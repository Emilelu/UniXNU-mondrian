# TDM — 扬声器的 PRI_TDM_RX_0 通路（预研）

> **已过时（2026-11-17）**：本文「扬声器走 PRI_TDM_RX_0（0x9000/0x9100）」的结论已被推翻。K60 的扬声器后端是 **TERTIARY TDM RX（AFE 0x9020 / 组 0x9120）**，引脚 gpio121/123/122/124。本文的 AFE 参数结构、启动顺序与 phk110 差异仍然有效，但端口 / 组 / 引脚三处请以 `VENDOR-AUDIO-CONFIG.md` 与 `VENDOR-AUDIO-KERNEL.md` 为准。

状态行：① 同型 ✅ ② 官方 ✅（live FDT）③ 反编译 ✅ ④ 广域 ✅ ⑤ 方案 ✅ ⑥ 深挖 ✅ ⑦ 本机验证 ⏳ ⑧ 上机 ❌（本线代码冻结，上机归 Lead 队列）

本文只做预研与落盘，不改补丁、不改 EIGHT-STEPS 的 done 状态（Lead m05983）。

## 0. 结论

1. **K60 的两颗 AW88261 扬声器不走 MI2S 主机模式，走 PRI_TDM_RX_0**：AFE 端口 `0x9000`、组 `0x9100`，
   由 ADSP（AFE 服务）驱动——AP 侧只发 APR/GPR 参数，不碰 LPAIF 寄存器。
2. `tert_mi2s_pinctrl` 在 live FDT 里 `status = "disabled"`（`live-fdt.dts:23656-23664`），tert MI2S 主机模式是死的；
   tert TDM（0x9020/0x9120）倒是 ok，但扬声器的对齐证据全部指向 PRI。
3. `GAP-ANALYSIS.md:115`（第 1 步）写的「TDM 引脚 121/123/122/124、tx-lines=3、dev-id=2」是 **tert 那套**；
   扬声器实际是 **PRI：gpio126(sck)/129(ws)/127(din)/128(dout)、dev-id 0x9000、group 0x9100**（§2、§5）。
   已在该行末尾加了警告标注（本线写作用域内只动这一处措辞，不改步骤与判据）。

## 1. 三方一致的证据链

| 来源 | 行 | 内容 |
|---|---|---|
| phk110 `docs/phk110/waves/wave1-hwmap.md:42` | audio 行 | 扬声器 AW88261×2，I2C qup3（0x35/0x34），**PRI_TDM_RX_0** |
| phk110 `hakios.sound.c:10-11` | 头注释 | "Android's PRI_TDM_RX_0, AFE port 0x9000 in group 0x9100 (with 0x9002, unused)" |
| phk110 `hakios.speaker.c:430-431` | amplifiers[] | `0x35 device 0 "0x35, slot 0"`、`0x34 device 1 "0x34, slot 1"` |
| live FDT `:20486-20506` | dai-tdm-pri-rx | group-port `0x9000`、group-id `0x9100`、clk `0x177000` |
| live FDT `:13318-13339` | aw882xx_smartpa | 0x34 sound-channel 0、0x35 sound-channel 1（i2c@880000 = SE15，同探针）|

live FDT 副本：`/mnt/e/k60-work/scratch/audio-work/live-fdt.dts`（34,801 行，取自设备 dtb 反编译，不入仓库）。

## 2. PRI_TDM 引脚真值（live FDT pinctrl@f000000，:1347 起）

| 信号 | GPIO | function（DT 名）| GPIO_CFG[5:2] 编码 | active drive | 方向 |
|---|---|---|---|---|---|
| sck | 126 | `mi2s0_sck` | **1**（funcs 下标）| 8 mA（寄存器 3）| 输出（output-high）|
| ws | 129 | `mi2s0_ws` | **1** | 8 mA | 输出（output-high）|
| din | 127 | `mi2s0_data0` | **1** | 8 mA | 输入（无 output 位）|
| dout | 128 | `mi2s0_data1` | **1** | 8 mA | 输入（无 output 位；SoC 是主机但该脚走 LPAIF 内部方向）|

- **编码是 funcs 数组下标，不是全局枚举序号**：`PINGROUP(id, f1..f9)` 把 `funcs[] = {gpio, f1, ...}`（pinctrl-sm8450.c:14-59），
  `msm_pinmux_set_mux()` 写 `i << 2`（pinctrl-msm.c）；gpio126/129/127/128 的 `mi2s0_*` 都占下标 1，与 `PONG_AUDIO_GPIO_FN_QUP15 1u`（`PongAudioRegs.h:44`，gpio56 的 qup15 同占下标 1）同一算法。
  （早前一轮把编码猜成枚举序号 33–40，作废。）
- `msm_regval_to_drive(val) = (val+1)*2` mA → drive-strength `0x08` = 寄存器值 3；bias-disable = pull 0。
- 节点行号：`pri_tdm_clk :1647`（sleep 0x289 :1649 / active **0x28a** :1665）、`pri_tdm_sync :1682`（0x28c :1700）、`pri_tdm_din :1717`（0x28e :1735）、`pri_tdm_dout :1751`（0x290 :1769）。
- **PRI 全系孤儿（fdt-refs.py 第二遍审计）**：pri_aux_pcm 0x279–0x288、pri_tdm 0x289–0x290、pri_mi2s_mclk 0x299 起——**refs 全 0**，
  没有 `pri_tdm_pinctrl`/`pri_mi2s_pinctrl` 消费节点；sound 节点只引 `qcom,tert-mi2s-gpios = <0x5ec>`（:23630）。
  → **移植时 PRI_TDM 的四根引脚必须由驱动直配 TLMM**（与 phk110 `hakios.sound.c:201-221` 同一做法），不能指望 DT pinctrl 框架。
- tert 对照：被引用的 active 组是顶层平铺的 0x5cd(gpio121)/0x5ce(gpio123)/0x5cb(gpio122)/0x5cc(gpio124)（:5315-5362，drive 0x02=2 mA），
  由 `tert_tdm_pinctrl`（:23666-23674，phandle 0x5ec）`pinctrl-0` 持有；:1785-1918 那组 8 mA active（0x292/294/296/298）refs=0。

## 3. AFE 编号与参数包（phk110 `hakios.sound.c`，APSL-2.0 只作事实参考，不搬代码）

- 命令/模块/参数 ID 全表：`hakios.sound.c:324-336`——`DEVICE_START 0x000100e5`、`DEVICE_STOP 0x000100e6`、`SET_PARAM_V2 0x000100ef`、
  `SVC_CMD_SET_PARAM 0x000100f3`、`MODULE_AUDIO_DEV_INTERFACE 0x0001020c`、`PARAM_ID_TDM_CONFIG 0x0001029d`、`MODULE_TDM 0x0001028a`、
  `PARAM_ID_PORT_SLOT_MAPPING_CONFIG 0x00010297`、`MODULE_GROUP_DEVICE 0x00010254`、`PARAM_ID_GROUP_DEVICE_ENABLE 0x00010256`、
  `PARAM_ID_GROUP_DEVICE_TDM_CONFIG 0x0001029e`、`MODULE_CLOCK_SET 0x0001028f`、`PARAM_ID_CLOCK_SET 0x00010290`。
- 端口/组：`PORT 0x9000`、`GROUP 0x9100`、`GROUP_OTHER_PORT 0x9002`、`CLOCK_PRI_TDM_IBIT 0x200`、`CLOCK_INVERT_COUPLE_NO 4`（:338-343）。
- 五个参数结构体（全部 packed，:349-385）：
  - `struct afe_param { module, param; size, reserved }` —— 参数头，16 字节 APR 头之后紧跟；
  - `struct afe_clock_set { version, id, hz; attribute, root; enable }` —— `afe_clock()` 发 `{1, 0x200, 48000*32*2, 4, 0, on}`（:423-428），
    位时钟 = 48k × 32b × 2 slot = **3.072 MHz**；
  - `struct afe_group_tdm { version; group; ports[8]; channels, rate, bits; slots, slot_bits; slot_mask }`；
  - `struct afe_tdm { version, channels, rate, bits; data_format, sync_mode, sync_source, slots, data_out, invert_sync, data_delay, slot_bits; slot_mask }`；
  - `struct afe_slot_mapping { version; channels, bits; align; offsets[8] }`。
- `afe_on()`（:432-468）顺序：**clock(true) → 组 TDM config → 组 enable → 端口 TDM config → slot mapping（MODULE_TDM）→ DEVICE_START**，
  任一步失败即整段退出；回包判据 `APR_BASIC_RSP_RESULT` 且 `words[0]==opcode` 且 `words[1]==0`（command()，:291-320）。
- 端口参数与服务参数的区别（afe_service_param :387 / afe_port_param :405）：端口参数包前 2 字节填 PORT、+2 填长度，走 `SET_PARAM_V2`；
  服务级参数（时钟、组）走 `SVC_CMD_SET_PARAM`。

- **这些包已经编码成字节流**：`drivers/PongAudio/PongAudioAfe.h`（纯函数；GPR 24 字节头、svc/port 两种 set-param 信封、上面五个参数结构与 DEVICE_START，另有 57 对 profile 的三字节写流）。宿主 `afe_cases()` 钉住每个字段的偏移、端序与拒绝路径。它已随 `patches/audio/0001` 进内核，`0003` 的 AFE selftest include 它。

## 4. phk110 的参数值（移植 GPR/APM 时要换成 K60 DT 的值，见 §5）

| 参数 | phk110（redwood）| K60 live FDT |
|---|---|---|
| 位时钟 | 3.072 MHz（`RATE*SLOT_BITS*SLOTS`）| DT 只给 `clk-rate 0x177000` = **1.536 MHz** → 1 slot×32b 或 2 slot×16b；`tdm-max-slots = <0x08>`（:23650）|
| slots | 2 × 32 bit，mask 3 | 待定（见 §5 推算）|
| 端口 0x9000 TDM config | channels 2、bits 32、sync_mode 0、sync_source 1、invert 1、delay 1、slot_mask 3 | DT 同名属性全同（invert-sync 1、delay 1、sync-src 1、sync-mode 1、data-out 0、clk-internal 1）|
| slot mapping | offsets {0, 4}（两通道字节偏移）| 待定 |
| 组成员 | 0x9000 + 0x9002 | DT `group-num-ports = <0x01>`，只有 0x9000；K60 TERT 为 0x9020，单成员（a7d82acf 已删 0x9022）|
| 时钟 attribute | 4（`CLOCK_INVERT_COUPLE_NO`）| DT `tdm-clk-attribute = 0x01`（:23649）；`mi2s-tdm-is-hw-vote-needed = <1 0 1 0 0 0>`（:23651）→ **PRI 与 TERT 都要 hw vote** |

## 5. K60 dai-tdm-pri-rx 节点逐字（:20486-20506，phandle 0x49c）

```
qcom,msm-cpudai-tdm-data-delay    = <0x01>
qcom,msm-cpudai-tdm-invert-sync   = <0x01>
qcom,msm-cpudai-tdm-data-out      = <0x00>
qcom,msm-cpudai-tdm-sync-src      = <0x01>
qcom,msm-cpudai-tdm-sync-mode     = <0x01>
qcom,msm-cpudai-tdm-clk-internal  = <0x01>
qcom,msm-cpudai-tdm-clk-rate      = <0x177000>   /* 1,536,000 Hz */
qcom,msm-cpudai-tdm-group-port-id = <0x9000>
qcom,msm-cpudai-tdm-group-num-ports = <0x01>
qcom,msm-cpudai-tdm-group-id      = <0x9100>
子节点 qcom,msm-dai-q6-tdm-pri-rx-0（0x49d）: data-align 0x00, dev-id 0x9000
```

同参数的还有 pri-tx 0x9001/0x9101（:20508）、sec-rx 0x9010/0x9110、sec-tx 0x9011/0x9111、tert-rx 0x9020/0x9120（:20574）、tert-tx 0x9021/0x9121。
`qcom,msm-dai-mi2s`（:20041）的 tert 是 `tx-lines=3 / rx-lines=0 / dev-id=2`（:20061-20067）——GAP-ANALYSIS 引的就是这套，属于 tert MI2S 主机模式，与扬声器无关。

**slot 推算**（1.536 MHz ÷ 48 kHz = 32 bit/帧）：要么 1 slot × 32 bit（单声道到一颗 PA，另一颗吃第二根数据线），
要么 2 slot × 16 bit。AW88261 的 I2S 入口是标准 I2S（ACF `0x06=0x34e8/0x38e8`），vendor 驱动读 `qcom,tdm-max-slots=8` 但真正下发到 AFE 的
slot 数来自 audio-kernel 的 mixer 控件，本机没有 vendor audio-kernel 源码——**这是留给 PAS1 线的第一个问题**。

## 6. sound-channel 与 ACF dev_index（写驱动前必须核对的一处）

K60 自己的 DT：`aw882xx_smartpa@34` → `sound-channel = <0x00>`（:13325）、`@35` → `<0x01>`（:13338）。
mainline `aw88261.c:1177-1186` 把 DT 的 audio-channel 读进 `aw_dev->channel`，`aw88395_lib.c:535/796/914` 用 `channel == cfg_dde[i].dev_index` 选块
→ **channel 就是 ACF dev_index**。phk110（redwood）的表是 `0x35=device 0`、`0x34=device 1`，**与 K60 DT 相反**。
我们的 judge 目前按 phk110 断言 `AMP_DEV_INDEX = {0:1, 1:0}`（探针 amp0 = 0x34 → dev_index 1）；
**若 run 2 实测 dev_index 与 K60 DT 一致（0x34 → 0），以实测为准并回改 judge 与 AMPS §8.5**——这正是 judge 交叉验证设计要抓的点。

## 7. 许可证与可搬性

- phk110-port `drivers/audio/*` 是 APSL-2.0：**只作事实参考**（端口/组/参数 ID、结构体布局、启动顺序），代码不搬。
- mainline `sound/soc/qcom/` 没有 waipio/sm8450 的 TDM DAI（只有 apq8016/sc7180/sc7280/hdmi/cdc-dma）；
  `sm8450.dtsi` 走 AudioReach（`q6apm-lpass-dais :2832`、`q6prm-lpass-clocks :2844`，protection-domain "avs/audio" "msm/adsp/audio_pd"）
  与我们的 PAS1+GPR 计划同构。上游 `qcom,q6dsp-lpass-ports.h` 的 `PRIMARY_TDM_RX_0=24`/`TERTIARY_TDM_RX_0=56` 是 Q6 intf 枚举，
  **与 DT 里的 AFE 端口号 0x9000/0x9020 是两套编号，不能混用**。

## 8. 留给 PAS1 线的接口清单

1. AFE 参数（§3 全套）只能在 **PAS1 + GPR/APM 起来之后**发（ADSP-PAS1.md 的 SCM 序列；adsp 载入基址 0x86300000、跨度 0x3100000）。
2. 需要的端口/组：0x9000（PRI_TDM_RX_0）+ 组 0x9100；0x9002 是否入组按 K60 DT（group-num-ports=1）→ **不入**。
3. 时钟：K60 位时钟 1.536 MHz，`CLOCK_PRI_TDM_IBIT 0x200` 与 attribute 的对应关系需实测（PRM 投票见 RESEARCH.md:25-55）。
4. io_submap：PRI_TDM 的 LPAIF 寄存器窗**不在** `PongCodecPlan.h` 现有五窗里（va/tx/va_swr/lpi/slew）；
   若走「AP 侧直配引脚 + AFE 参数」的混合方案，TLMM 用现有 `PONG_AUDIO_TLMM_PHYS` 窗即可，无需新增 LPAIF 窗。
5. slot 数/位宽与 slot mapping 的 offsets 必须与 AFE 参数一致，否则两颗 PA 交换声道（§6 的映射陷阱会放大成听感错误）。

### 8.1 三块补充（详见 `PAS1-AUDIO-REQUIREMENTS.md`）

- **GPR/APM 注册与 GLINK 独占**：音频在 publish **之后**作为 consumer 开 `adsp_apps`（intent 560×20、APM 端口 1），不做第二个 owner；与 `K60AdspOwnerLease` 的 bit2 `GlinkExclusive` 不冲突（契约第 7 条「GLINK 交给既有 consumer」）。`QcomGlink.h:17` 的 `QCOM_GLINK_MAX_CHANNELS` 已于 2026-11-17 落成 `2u`（见 `AUDIO-CLOSURE.toml` 的 `glink-two-slot-in-kernel`），且**不能另起实例**（FIFO 是共享物理资源）。
- **降级**：照 `PongCodecProbe.c:37-41` 的具名错误范式，handoff / lease / epoch / APM / AFE 五级各有枚举；PAS1 没好之前零寄存器访问（含 TLMM 引脚复用）。
- **AFE 参数时序**：acquire 之后、publish **之后**（consumer 侧）。acquire 与 publish 之间是 provider 临界区，发参数即违反独占；且 GLINK 的 adopt 依据 `/chosen/k60-adsp-glink-handoff`（104 B）publish 时才出现。
- **provider 侧的验收项**：§8 五条的落地版是 `PAS1-AUDIO-REQUIREMENTS.md` §5 的四条（单实例多槽的 `QCOM_GLINK_MAX_CHANNELS` 已落成 2、`qcom_glink_channel()` 必须早于 DSP 的 OPEN、bit2 独占的正确读法、AFE 包由 consumer 在 publish 之后发）。
- **协议选择**：K60 走 24 字节 GPR（域 2/3、APM 端口 1、通道 `adsp_apps`），不是 phk110 的 12 字节 APR（域 4/5、通道 `apr_audio_svc`）；`sm8450.dtsi:2813` 只有 `adsp_apps`。

## 9. 与 AMPS.md 的衔接

- `AMPS.md:530`：run 1 读到 `i2s=0x04e8`、TXEN=0，「没有 TDM 时钟，功放未启动」——本文解释了那个 TDM 时钟该由谁给：ADSP 的 AFE（§3）。
- `AMPS.md §9.4`：「TDM/MI2S 前端与 ADSP 图是 Lead 的 PAS1 线」——本文是那条线的 K60 侧事实清单。
- 回放层（AMPS §9）写完 profile 后两颗 PA 仍是「配置正确但不出声」；出声还差：TDM 位时钟 + 帧同步（本文 §3/§5）、
  start 序列（AMPS §8.6）、播放图（PAS1 + AudioReach）。

---
来源行号全部实测于 2026-11-15；live FDT 行号指 `/mnt/e/k60-work/scratch/audio-work/live-fdt.dts`。