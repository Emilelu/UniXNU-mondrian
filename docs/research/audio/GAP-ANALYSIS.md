# 音频 / DSP 差距分析（SA-02）

> 来源：subagent SA-02，2026-11-12
> 状态：只读调研完成，结论已落库
> 关联：`docs/research/audio/RESEARCH.md`（①②③④⑤⑥ 调研）、`docs/research/EIGHT-STEPS.toml`

---

## 1. 上游有没有可直接用的音频栈

**没有。** yibiya 上游只有「能编译、不能跑」的骨架；UniXNU-upstream 镜像 0 行音频代码。

扫描 19 个 ref（8 分支 + 5 tag + origin/*）。真音频文件只在 4 个分支：
`fix/boot-v4-repack`、`fix/touch-gpu-bringup`、`upstream-fix`、`fix/ui-startup-blob`。

| 文件 | 大小 | 说明 |
|---|---|---|
| `patches/xnu/0503-k60-audio-aw882xx.patch` | 25,561 B | 823 行 aw882xx.c：GENI I2C + GCC/TLMM + chip-id；**寄存器号全是 `AW882XX_TODO_*`**，`g_aw882xx_apply_todo_init=false` |
| `patches/xnu/0504-k60-audio-pong-audio.patch` | 29,471 B | 970 行 pong_audio.c：GPR 编解码 + AudioReach 11 种报文构造器齐备，但 `pong_audio_start()` 只做 4 个 `ml_io_map` 后打印 `skeleton stage=ADSP_WINDOWS (PAS1 loader TODO)`；`pong_audio_submit()` 直接 ENOTSUP |
| `patches/xnu/0505-k60-audio-integration.patch` | 730 B | 只加 `bsd/conf/files` + `bsd_init` 调 `pong_audio_bootstrap()`（boot-arg 关门）|
| `docs/plans/BT-AUDIO-PORT-PLAN.md` | 61,991 B | 移植计划 |

引入提交：`abd9eaa feat(patches): stage BT/audio/120Hz patch sets (0500-0506)`

**0504 文件头自述**：`compileable skeleton, not a working audio driver`（第 8 行）。

**强参考（本机、非 upstream）**：
- `UniXNU-sheng`：`AdspProbe.cpp` 34,367 / `AudioProbe.cpp` 64,915 / `ShengAudioReach.c` 17,119 / `ShengGpr.c` 4,165 / `ShengAudioPlugIn.c` 45,679
- `phk110-port`：`hakios.adsp.c` 123,950（3,244 行 PAS1→SMP2P→GLINK→QRTR→APR）/ sound 59,740 / speaker 43,467 / mic 73,999
  但 `devices/phk110/README.md:34` 自述 "audio not attempted yet"，`device.conf:27` `adsp=0`

---

## 2. 八步真实状态：**5/8，且文件头自相矛盾**

| 步 | done | 实际内容 |
|---|---|---|
| ① 同型 | true | Pong 音频栈 ~107 KB（PongAdsp 34,547 / PongAudio 29,263 / PongIOAudio2.h 23,857 / PongWcd938.h 6,262 / PongAudioService 7,509）|
| ② 官方 | true | components.toml 25 组件无音频，官方实现全在 UniXNU-sheng 板级 |
| ③ 反编译 | **false** | codec 型号 / PAS id / PMIC 轨道 / SWR / GPIO 全待测；aw882xx 零先例 |
| ④ 广域 | true | 官方 power 页；ShengAdsp channel/send，MAX_MESSAGE=512；AudioReach/GPR |
| ⑤ 方案 | true | 四步方案 + 两条 SM8550 硬事实 |
| ⑥ 深挖 | true | DT 节点已建（9 个 0 占位）+ 三条结论 |
| ⑦ 核验 | **false** | 未做 |
| ⑧ 上机 | **false** | 从未上机 |

**矛盾**：`[hardware.audio]` 头部写 `status="planned"` / `parked_why="尚未开始"`，与 5 个 `done=true` 冲突。

**「文档写了但代码没有」= ①④⑤⑥ 全部只产文档/DTS**；全仓零音频驱动源码。
**③ 反而被低估**：live FDT 已能填 9 个占位里的 8 个。

---

## 3. 我们仓库里有什么音频代码

**只有上游 0503-0505 三个 patch**（sha256 与上游逐字节相同：
`e83f02dd…` / `3c4bb560…` / `1a2b39a3…`），**没有一行自研音频驱动**。

- 编译产物：`pong_audio.o` 182,032 B、`aw882xx.o` 37,880 B（2026-11-12 11:07）
- `kernel.macho` 含 `"PongAudio: skeleton stage=ADSP_WINDOWS (PAS1 loader TODO)"`
- 上机记录：`docs/ops/PITFALLS.md` P-58/P-59/P-63 —— `pong_audio=1 pong_aw882xx=1` → **0 日志整机死**；
  根因 `io_submap` 全内核仅 8 MiB，`ml_io_map` 打满 panic（0503 4 处、0504 5 处 map）。boot-arg 已移除。
- `userland/` 无音频 HAL；无 PongAudioService；无 `drivers/audio`

### ⚠️ 发现一个真 bug：`adsp-base` / `adsp-size` 是错的

```
我们 dts:  adsp-base = 0x0a000000   adsp-size = 0x01c00000
K60 live FDT /reserved-memory/adsp_region@9fd00000 = 0x9fd00000 + 0x3100000
Pong 实际用: 0x85700000 + 0x2800000 (PongAdsp.cpp:45)
```

**两个值都不是。PAS1 会加载到错误的物理区。**

来源证据：`live-fdt.dts:191-193`、`UEFI MemoryMapLib.c:34`。

### DTS 现状

`dts/mondrian.dts` 3,903 B，只有 `pong-audio` + `ufs` 两个节点。
`pong-audio` 共 17 个属性，**9 个是 0 占位**：
`tx-master-base`、`codec-reset-gpio`、`codec-i2c-address`、`amp-i2c-address`、
`tx-core-clock-id`、`codec-supply-rail`、`mic-bias`、`mic-adc`、`swr-device-index`。

非零：`rsc-base` 0x17a20000、`cmd-db-base` 0x80860000、`adsp-base` 0x0a000000、
`adsp-size` 0x01c00000、`timebase-hz` 19200000、`coreaudio-assumed-hz` 24000000、
`period-buffer-limit` 0x100000000。

---

## 4. PAS1 归属：**没有任何代码在认证/启动 ADSP**

电池和音频卡在同一个缺失的 PAS1 owner 上。

- 全仓 PAS1 只有文档 + GPU 的 PAS13（`PongAdrenoCp.cpp:210`、`PongAdrenoZap.c:115`，
  是 ZAP shader 认证，不是 ADSP）
- `K60AdspGlinkHandoff` 只在三处：
  - `K60BatteryConfig.h:14-54`（结构 + flags=0xf）
  - `K60BatteryConfig.c`（解析）
  - `K60Battery.cpp:426-432`（从 `/chosen` 读 `k60-adsp-glink-handoff`，缺则报 blocked）
  - `K60PmicGlink.cpp:110-116`（flags==0xf 且 epoch!=0 才开 `PMIC_RTR_ADSP_APPS`）
- **该 property 无生产者**：全仓只有 `K60BatteryConfig.h:17` 定义；dts 无 `/chosen`
- `build-k60-physical-battery.py:286-287` 明写 `No firmware/PAS startup or synthetic handoff is generated`
- `drivers/PongPower` 内 grep `scm|pas_|auth_and_reset` = **0 命中**
- 上游 `porting.toml:159` 自认：`A live ADSP owns PAS1 on this board and no firmware-owned fresh GLINK handoff has been established`

**已有底座**：`QcomGlink.c` 21,672 B（adopt/channel/poll/send/reopen，加固版）+ `K60Smem.c` 4,667 B，
但**未进 conf/files、未链接**（0602 只改 `IOKitBSDInit.cpp` 并等 `libK60PhysicalBattery.a`）。

---

## 5. 最小出声路径（10 步，缺一不可）

| # | 要做的事 | 步 | 依赖 | 现在能不能做 |
|---|---|---|---|---|
| 1 | 修 `adsp-base`/`adsp-size` → `0x9fd00000`/`0x03100000`；填 8 个 DT 值（amp 0x34/0x35、amp reset 1/3、irq 88/63、spksw 52、codec reset 43、codec-supply pm8350_s10、TDM clk 0x177000=1.536 MHz / tx-lines=3 / dev-id=2、TDM 引脚 121/123/122/124）| ③⑥ | live FDT 已有值 | **能**（`tx-core-clock-id` 缺，需读 K60 Android audio-kernel）|
| 2 | 修 `io_submap` 8 MiB 预算（P-63）| ⑦前置 | P-63 修复方案 | **能**（未做）|
| 3 | PAS1 owner：移植 `PongAdsp.cpp:523-600`（SCM `PAS_INIT_IMAGE`→`MEM_SETUP`→分段 load→`AUTH_AND_RESET`；PAS id 1；SMP2P 443/429/423；GLINK 478/479/480；IPCC LPASS）| ⑤⑦ | SCM PIL + `adsp.mbn` + `adsp.b02..b36` | **缺固件**（本机 find 0 命中，须从 K60 `/vendor/firmware_mnt/image` 取）|
| 4 | SMP2P + GLINK + IPCC 通道 | ⑦ | PAS1 完成 | 缺 PAS1（QcomGlink.c 已有）|
| 5 | GPR/APM 图：0504 报文可用，但 SG/IID 全是 Pong 拓扑（0504:250-258 明写必须换 K60 枚举）| ③⑦ | APM + 实测 | 缺实测 |
| 6 | 低 4 GiB DMA：K60 内存从 `0x900000000`(36 GiB) 起，内核 ring 必 >4 GiB；须 UEFI 预留 64 KiB + `/chosen/pong-audio-dma` | ⑤⑦ | UEFI 改动 | 缺 UEFI 改动（`MemoryMapLib` 现无 audio 项）|
| 7 | AW882xx 初始化：0503 只有 GENI 通路 + 探测，寄存器表/ID/时序全无 | ⑦ | 厂商寄存器表 | 缺（需 Xiaomi `aw882xx_dlkm` 或 datasheet）|
| 8 | TDM/PRM：K60 1.536 MHz vs Pong 3.072 MHz/0x104 | ⑦ | 功放 + 实测 | 缺功放 |
| 9 | CoreAudio 接入：`PongAudioService.cpp` + `PongAudioPlugIn.c` + `PongAudioRoute.h` | ⑤⑦ | 图可用 + HAL | 缺 HAL |
| 10 | 时基修正 24→19.2 MHz | ⑦ | — | 能（未做）|

**判据**：提示音也走 CoreAudio→HAL→音频服务，所以第 9 项不可省。**仅做 3+5 不会出声。**

---

## 结论

1. **音频不是「上游修好了我们没取」** —— 上游也没有，只有骨架。这是真正的空白区，符合分工判断（他只有 2 个音频提交）。
2. **两个立刻能做的真 bug**：`adsp-base/size` 错、`io_submap` 8 MiB 预算（P-63）。
3. **PAS1 是硬阻塞**，电池和音频共用；没有固件 `adsp.mbn`。
4. `EIGHT-STEPS.toml` 的 audio 段头尾矛盾，需要修正。
