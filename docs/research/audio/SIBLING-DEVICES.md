# 同 SoC 参考设备调研（SM8475 / SM8550）

> 2026-11-19 补记。起因：音频流 0x1801 的首笔 PCM 写入杀死 ADSP 传输时，K60 侧一直在
> 自造地址/令牌约定，而没有先横向核对已经出过声的同 SoC 仓库（用户 m27121 的批评）。
> 这份文档固定调研结果：读了哪些仓库、各自处在什么状态、哪些事实来自它们、哪些被拒绝。
> AGENTS.md「Research before writing code」要求先 survey 再动手，本表即为该步骤的记录。

## 1. 参考仓库一览

| 仓库 | 设备 | SoC | 音频状态 | 许可证 |
| --- | --- | --- | --- | --- |
| `E:/k60-work/ref/pong-power`（`UniXNU-pong` 的 `drivers/` 子模块，pin `c37179e`） | Nothing Phone 2（pong） | SM8475 | **已出声**：ADSP AudioReach 播放 + SMMU 直通 | BSD-2-Clause-Patent |
| `E:/hackios/UniXNU-zizhan` | 小米 MIX Fold 2（zizhan） | SM8475 | 同血统驱动，未出声（README 注明 CS35L41 尚未接入） | BSD-2-Clause-Patent |
| `E:/hackios/UniXNU-sheng` | 小米平板 6S Pro（sheng） | SM8550 | 早期参考，I2S 路径 + SMMU bypass 配方 | BSD-2-Clause-Patent |
| `E:/hackios/UniXNU-pong` | Nothing Phone 2 | SM8475 | 上面 pong-power 的宿主仓库 | BSD-2-Clause-Patent |

四个仓库的 `LICENSE` 首行一致：`Copyright (c) 2026, UniXNU contributors` /
`SPDX-License-Identifier: BSD-2-Clause-Patent`，与 K60 仓库同许可证，代码可直接复用。

## 2. UniXNU-pong：唯一在 SM8475 上出过声的基线

`E:/k60-work/ref/pong-power/PongAudio.cpp`：

- `:214-235` `setupDma()`：从 `/chosen` 读 `pong-audio-dma` 租约（16 B：pa、bytes，4 KiB 对齐、
  不超 4 GiB），`planUfsSmmu(0x1801, dmaPa, BufferBytes, read, 78, 120)` +
  `configureUfsSmmu(plan, 0x1801, read, write)`，成功后打印
  `PongAudio: UEFI DMA=%llx SID1801 physical pass-through bank=%u`。
- `:231` `dspAddress = dmaPa | (1ull << 32)`；`:268` `ar_map(..., dspAddress, BufferBytes)`；
  `:295` `ar_write(b, sizeof b, Port, request, dspAddress + slot*PeriodBytes, handle, PeriodBytes)`。
  **map 与 write 用同一个带 bit32 的地址**，这是 K60 之前的 `at`/`au` 一直缺的一半。
- `:294` `const unsigned request = 0x10000000u | (++writeToken & 0x0fffffffu)`：握手令牌是本仓库
  自己的 0x1000_0000 序号形态，不是 mainline 的「长度<<16」形态。
- 常量：`Port = 0x2001`、`PeriodFrames = 480`、`PeriodBytes = 3840`、`Slots = 8`、
  `BufferBytes = 65536`、`TableBytes = 65536`。
- 注释原文（`:220-228` 附近）：“The DSP shared-memory protocol already uses a UEFI-reserved
  contiguous low32 buffer, with the stream index in the high word. As in Sheng real audio
  transport, this stream needs physical pass-through, not a second translation of its physical
  addresses. Lease only Pong SID1801 and retain every unrelated firmware/UFS/WLAN stream and bank.”

## 3. UniXNU-zizhan：同驱动血统，SMMU 表构造的细节来源

- `drivers/PongPower/PongAudio.cpp:124-132` `setupDma()` 与 pong 同构：
  `dma.open(dmaPa, BufferBytes, kIOMapWriteCombineCache)` → `smmu.open(0x15000000, 0x100000)` →
  持 `pong_smmu_lease_lock()` → `planUfsSmmu(0x1801, dmaPa, BufferBytes, read, 78, 120)` →
  `ArmSmmu4KBuild` / `ArmSmmu4KEncodeContext` → 直接写寄存器。
- `drivers/PongAdreno/ArmSmmu4K/ArmSmmu4KContext.c` 的编码常量：`cbar=0x1f300`、`cba2r=1`、
  `mair0=0xff44`、`sctlr=0x1067|(stall<<7)|(continue<<8)`、`tcr2=(7u<<15)|(1u<<4)|width_code`。
- 但 README 明确写「蜂窝未实现；CS35L41 功放尚未接入」——它不是出声证据，只能证明
  **SMMU 直通租约在 SM8475 上可行**。

## 4. UniXNU-sheng：早期参考，SoC 不同，常量不能直搬

- `package/ShengAudioReach.h:30-50`：`AR_MOD_WR_SHMEM 0x07001000`、`AR_MOD_I2S_SINK 0x0700100A`、
  `SG_PLAY 0x4001`、`SG_SPEAKER 0x4005`、`AR_IID_PLAY_SHMEM 0x6001`、`SPEAKER_I2S 0x6051`。
- `package/AudioProbe.cpp:285-294`：三条音频流 `{0x1001, 0x1081, 0x1061}` 各自
  `smmu_plan_bypass(&io, kStreams[i], gAudio.bufferPa, kBufferBytes)` + `smmu_configure_bypass`。
- `:305-317` 注释给出 32 位地址的决定性解释：“The DSP takes 32-bit buffer addresses (its client
  hands it 32-bit IOVAs; i491 to i495: a buffer above 4 GiB was refused with status 1) …
  The DSP takes it as address | stream index << 32 … i491 to i495 sent a 36-bit address, whose
  upper word the DSP read as stream 8 and refused with status 1.”
- `:763` `ar_map(..., gAudio.dspAddr, kBufferBytes)`：**map 同样用带 bit32 的地址**。
- `package/SmmuBypass.h`：apps SMMU 最后一个 context bank（`SCTLR=0`、`CBAR=0x10000`、`CBA2R=1`）
  是共享 bypass bank；流若要用它，S2CR 必须写 **TYPE=TRANSLATE 且低 8 位写 bank 号**
  （该固件上 TYPE=BYPASS 的 S2CR 读回是 FAULT），并且 **先写 S2CR 再写 SMR**
  （`SMR = 0x80000000 | stream`）。
- sheng 是 SM8550、I2S secondary/SD1、16-bit，K60 是 SM8475、TERT TDM、AW882xx 功放，
  所以它的 `I2S_SECONDARY/SD1` 取值没有搬，只搬协议与 SMMU 配方。

## 5. K60 自身的硬证据（不依赖参考仓库）

- `E:/k60-work/scratch/audio-work/live-fdt.dts:20784-20793`：
  `spf_core_platform/qcom,msm-audio-ion` 的 `iommus = <0x5b 0x1801 0x00>`、
  `qcom,smmu-sid-mask = <0x00 0x0f>`、`qcom,iommu-dma-addr-pool = <0x10000000 0x10000000>`、
  `qcom,smmu-enabled`、`qcom,smmu-version = <0x02>`、`dma-coherent`。
  → DSP 侧音频缓冲的 SID 是 **0x1801**，流号取地址高字的低 4 位，与 pong/sheng 完全一致。
- `E:/k60-work/vendor-src/kernel-sm8450-modules/qcom/opensource/audio-kernel/asoc/msm_dailink.h:385-392`：
  `CONFIG_TARGET_PRODUCT_MONDRIAN` 分支把 `tert_tdm_rx_0` 的 codec 定义为
  `aw882xx_smartpa.2-0035` / `aw882xx_smartpa.2-0034`（CPU 为 `snd-soc-dummy-dai`），
  即 K60 的扬声器在 TERT TDM RX，而不是 MI2S。
- `docs/research/EIGHT-STEPS.toml:463` 与 `porting.toml:143/145/146` 记录的真机时序：
  au（七步全 0、不写 PCM）活满 300 s；av/aw（写 PCM）在第一笔写入处掉传输。

## 6. 采纳 / 改编 / 拒绝

| 事实 | 决定 | 依据 |
| --- | --- | --- |
| 音频流 SID 0x1801、地址高字带流号 | 采纳 | K60 DT `iommus <0x5b 0x1801>` + pong `:231` + sheng `:312` |
| map 与 write 用同一个 tagged 地址 | 采纳 | pong `:268/:295`、sheng `:763`；aw 只改 write 不改 map 仍死 |
| 租 apps SMMU 顶部 context bank 作 stage-1 bypass | 采纳 | pong `:214-235`、zizhan `:124-132`、`SmmuTakeover.h` 全文 |
| 先 S2CR 后 SMR、S2CR 写 bank 号而非 TYPE=BYPASS | 采纳 | `SmmuBypass.h`（sheng 固件读回证据） |
| 令牌 `0x10000000 | seq` | 采纳 | pong `:294`；mainline 的「长度<<16」在 Pong 系固件上未验证 |
| PeriodFrames 480 / PeriodBytes 3840 | 拒绝（保留 K60 的 1024 / 8192） | K60 HAL 自检按 8192 B 槽跑通 64,512 帧 |
| sheng 的 I2S secondary/SD1/16-bit | 拒绝 | K60 是 TERT TDM + AW882xx，见 `msm_dailink.h:385-392` |
| mainline q6apm 的 iommu 域内 DMA 地址 | 拒绝（K60 无 q6apm-dai iommu 节点） | 64 条 `iommus` 里没有 audio/AGM 节点 |

## 7. 对镜像 ax 的意义

`79442ca7` 把上表前三行落成代码：`pong_play_dsp_address()` 给地址加 bit32、map 与 write 都用它、
`pong_audio_smmu_lease(0x1801)` 按 `SmmuTakeover.h` 的顺序租顶部 bank，并在第一笔写之前打印
SMMU 审计（sCR0/IDR/SMR/S2CR）。判据：`PongAudio: SMMU stream 0x1801 leased to bypass bank`
之后应出现 `PCM write done slot=0`；若仍静默，审计里的 SMR/S2CR/SMMUEN 就是下一变量的选择依据。
