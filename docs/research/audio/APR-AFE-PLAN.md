# AFE 两条后路：APR 重封装 vs AR/CDC-DMA 转向

判据在 `FLIGHT-CARD-20261119CA.md`：ca 探针的两个 token（0x00025a00 设备启动、0x00025a01 组使能）
的 rx status 决定走哪一条。本文把两条路的落点先写死，判决一到直接改代码。

## 0. 现状（已证）

| 事实 | 证据 |
| --- | --- |
| GPR 上 legacy AFE 五个参数包全部 `status=2` | bz console 509-531（step 1/2 `0x000100fc`、3/4 `0x000100ef`、5 `0x000100e5`） |
| 改 TDM 语义值（16 bit / 长同步 / 3.072 MHz）不影响 status | bz 全篇与 bx 完全一致 |
| 改 speaker 模块 id 为上游 `AUDIO_IF_SINK 0x0700117C` 被拒 | by console 1596-1614，step 7/9/10 status=1 |
| 请求确实到达 AFE 服务（域 2、端口 4）并回 EFAILED | by console 540-556 的 `src=2:0x4` rx 行 |
| 四个 TERT TDM 焊盘原先停在功能 0，bx 后 sck/ws 为 mi2s2 输出 | bx console 288-291（`cfg 0x00000001 -> 0x00000204`） |
| 焊盘修好后功放 SYSST 从 `0x0020`(NOCLKS) 变 `0x0000`，但 PLLS/CLKS 仍 0 | bx console 1756/1766 |
| 图侧全部被接受（open / SET_CFG / MEM_MAP / PRM / PREPARE / START 均 status=0） | bx console 556-572、1718-1735 |

⇒ 唯一没通的是**物理位时钟**，而它只能由 AFE 端口真正启动来产生。

## 1. 关键差异：封装层

t970 用 **APR 甲板**（`bsd/dev/qcom/T970Apr.c` + `T970Apr.h`，补丁内 20 字节头），我们用 **GPR 24 字节头**。

| 项 | 我们（GPR） | t970（APR） |
| --- | --- | --- |
| 头长 | 24 B，6 words | 20 B，5 words |
| word0 | `version(0) | hdr_words<<4 | packet_bytes<<8` | `put16(2<<8 | (20/4)<<4)` = 0x0252，字节 2..3 回填总长 |
| 域字段 | word1 = `dest_domain | src_domain<<8`（ADSP=2, APPS=3） | `put8(svc), put8(APPS=3), put16(port)` 与 `put8(svc), put8(ADSP=2), put16(port)` |
| 端口 | src 0x2001（client）→ dst 4（AFE） | src/dst 端口都是 0（AFE 服务） |
| group 参数 opcode | `AFE_SVC_CMD_SET_PARAM_V2 0x000100fc` + `param_hdr_v3`(16 B, 带 instance) | `AFE_SVC_CMD_SET_PARAM 0x000100f3` + 12 B `param_hdr_v1`(module, param, size, 0) |
| 端口参数 opcode | `AFE_PORT_CMD_SET_PARAM_V2 0x000100ef` | 同 0x000100ef（这一条两边一致） |
| 时钟 | PRM `REQUEST_HW_RSC 0x0100100f`（模块实例 2、param 0x0800102c） | `AFE_MODULE_CLOCK_SET 0x0001028f` / `AFE_PARAM_ID_CLOCK_SET 0x00010290`，payload 20 B：`version=1, clock_id, hz, attribute(u16), 0(u16), enable(hz!=0)` |
| 时钟 id | `0x204`（TERT_TDM_IBIT） | `0x200`（PRI_TDM_IBIT），6.144 MHz |

t970 的启动顺序（`afeStart`）与我们相同，但多了两件事：

1. 先发两个 **HW vote**：`AFE_CMD_HW_VOTE`，block = `AFE_HW_BLOCK_MACRO` / `AFE_HW_BLOCK_DCODEC`，
   payload = `u32 block + char[8] client`（`"LPASS_HW_MACRO"` / `"LPASS_HW_DCODEC"`），失败只记不致命。
2. 时钟**先试服务级**（port=0），失败再试端口级（port≠0）；两者都失败才算死。
   端口启动失败时若当初是服务级时钟成功，会补发一次端口级时钟再重试 `portStart`。

## 2. 路 A（ca 两个 status 都是 0）：把六步改成 APR 封装

改动集中在两个文件，不动图侧：

- `patches/audio/0001-k60-audio-amp-probe.patch` 里的 `drivers/PongAudio/PongAudioAfe.h`：
  - 新增 `pong_afe_apr_hdr()`：20 B 头，返回 20；新增 `pong_afe_apr_finish(buf,n)` 把 n 写进 `buf[2..3]`。
  - `pong_afe_svc_set_param()` 增加一个 v1 变体 `pong_afe_svc_set_param_v1()`：opcode 0x000100f3、
    `put32(12+size)` + 3×`put32(0)` + 12 B `param_hdr_v1`（无 instance 字段）。
  - `pong_afe_port_set_param()` 改用 APR 头（opcode 与布局不变）。
  - `pong_afe_step_opcode()`：`PongAfeStepClock` 返回 0x000100f3（不再是 PRM 0x0100100f）；
    `PongAfeStepGroupTdm/GroupEnable` 返回 0x000100f3。
  - 时钟 payload 改成 t970 的 20 B `clock_set` 形状；`clock_id` 先按 `0x204`（TERT）试，
    失败再退 `0x200`（PRI），hz 用 `PONG_AFE_TDM_CLK_HZ`（当前 3.072 MHz）。
  - 新增 `pong_afe_apr_hw_vote()` 与两个 block 常量，在六步之前发两票。
- `patches/audio/0003-k60-audio-afe-selftest.patch`：`pong_audio_afe_send_step` 里发送前调
  `pong_afe_apr_finish`；rx 匹配仍按 token（不变）；六步表加 HW vote 两行后
  `PongAfeStepCount` 从 6 变 8。
- host 测试：`drivers/PongAudio/tests/`（仓库内路径，参考 t970 的 `bsd/dev/qcom/T970Apr.c` 字节序）里给 `pong_afe_apr_hdr` / v1 参数头 / clock payload 加字节级断言
  （现有测试风格是逐字节比对，见 `test-pong-audio-geni-i2c.c`）。

风险：APR 与 GPR 是同一物理 GLINK 通道上的两种协议，**本机固件若只认 GPR，APR 包会被静默丢弃**
（ca 的 F5 就是这种情况）；反过来若 ca 的 S4/S5 有 status，说明两种协议并存，可安全切换。

## 3. 路 B（任一 status = 2）：转 AR / CDC-DMA

不再发 legacy AFE 包，让 AudioReach 图自己拥有硬件端点：

- speaker 图把 `AR_MOD_TDM_SINK 0x0700100E`（本机私有 TDM sink）换成
  `CODEC_DMA_SINK 0x07001023` 或保留 TDM sink 但把端口配置交给图内的 `AUDIO_IF` 模块。
  依据：上游 `audioreach.h` 里 `CODEC_DMA_SINK 0x07001023` 是标准媒体出口，
  且 by 已证明本机拒绝上游 `AUDIO_IF_SINK 0x0700117C`，所以**只能选本机认的 id**，
  需要先用一个只改 id 的探针镜像把候选 id 逐个试一遍（每个 id 一次 boot，status=0 即接受）。
- 图内模块链改成 `WR_SHARED_MEM_EP → PCM_DEC → PCM_CNV → CODEC_DMA_SINK`，
  端口/时钟由 DSP 侧 `AUDIO_IF` 的 `PARAM_ID_HW_EP_MF_CFG` 决定，HLOS 不再发 AFE 包。
- 代价：这条路要重做 speaker 图的 open payload（现在是 408 B 手写），
  且 CDC-DMA 需要 DSP 侧有对应的 `hw_ep` 实例，能否起来只能试。

## 4. 与 27 迁移的关系

两条路都只动内核侧纯 C（`drivers/PongAudio/*.h` + `bsd/dev/pong_audio.c`），
与 iOS 版本无关；host 测试随代码走。**16 的 AFE 参数表（`PongAudioAfe.h` 里的 group/tdm/slot 值）不带进 27**——
by 已证明固件代次不同会整体拒绝，27 上要按那时的固件重新标定。

## 5. 一个必须先说的判读陷阱：我们的 rx 解析器只认 24 字节 GPR 头

`pong_gpr_decode()`（`patches/xnu/0504-k60-audio-pong-audio.patch:197-225`）要求
`header_bytes >= 24`，否则返回 `PongGprBadHeader`，`pong_audio.c` 只打印
`PongAudio: glink adsp_apps rx bytes=%u (bad gpr)`（0003 补丁 1385-1386 行）。

APR 甲板的头是 **20 字节**（`field>>4 & 15` = 5 字），端口是 16 位、域是单字节，
token 在偏移 12、opcode 在 16（`T970Apr.c` 的 `begin()` 与 `apr_parse()` 一致）。
两种头在字节 0..3 的编码完全相同（`version | hdr_words<<4 | size<<8`，size 在 `[2..3]`），
差别只在 4 字节之后：GPR 是 `u32 dest_domain|src_domain<<8, u32 src_port, u32 dst_port`，
APR 是 `u8 svc, u8 domain, u16 port` ×2。

⇒ **如果本机 ADSP 用 APR 帧回应，ca 的 console 里不会出现带 status 的 `rx` 行，
而会出现 `rx bytes=N (bad gpr)`。** 这条也要算「包到了、有应答」，
只是我们这边解不开；flight card 的 F5（两条应答都没有）不覆盖它。
判读时请把 `(bad gpr)` 行的 bytes 与 token 位置一并记下。

路 A 的改造因此要多一步：`pong_gpr_decode()` 需要接受 `header_bytes == 20` 的帧，
按 APR 布局取 `src_svc/src_domain/src_port/dest_port`，否则 APR 路一开就会把自己的回包丢掉。

## 6. 若 ca 连 `(bad gpr)` 都没有

说明 ADSP 把 APR 帧整包丢了（协议不并存）。那时的动作不是改判据，而是：
先用同一份代码把六步的**信封**从 GPR 24 B 换成 APR 20 B、其余字段不动，
发一次最小 `GET_SPF_STATE`（APM 命令在 GPR 下已能成功，换封装后若仍成功，
说明通道接受 APR 帧），再决定要不要继续在 legacy AFE 上投。
