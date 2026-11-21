# F1 平台线交接（一页）

> 给 F1 那张镜像用的一次性检查单。目的只有一个：把「1 核还是 8 核」这个问题用产物回答掉，让首帧判读不带猜。
> 依据：Lead m01179 ②（F1 一出镜像立刻跑，不必等）；`docs/research/ios27/SMP-STEP-DECODE.md` §6.2（两块可粘贴脚本，已自测）。

## 0. 一句话

镜像一落地，先跑 §6.2 的两块脚本，把 `VERDICT` 那一行连同产物路径回给 Lead；**`AGREE` 之前不读任何 SMP 判读表**。

## 1. 谁在什么时刻做什么

| 序 | 谁 | 时刻 | 动作 |
|---|---|---|---|
| 1 | Lead / 构建线 | F1 构建完成 | 产出 `<OUT>/stage/EFI/UniXNU/` 下的 `pong-boot-manifest.json` 与 `kernel.macho.adt` |
| 2 | **platform27（本条线）** | 产物可读、**上机之前**（纯离线，只读文件） | 跑 §2 的两块脚本，回一行结论 + 产物路径 |
| 3 | Lead | 收到结论后 | 上机取首帧；日志里若有 `ArmCpu:` 行，交回本条线判读 |
| 4 | platform27 | 拿到 `ArmCpu:` / `psci:` 行 | 按 `SMP-STEP-DECODE.md` §2 的 A 表逐行判：A0 注册、A1 MPIDR、A7 `CPU_ON` 返回码、A8「未加入」、A12 收尾快照 |

本条线不 boot、不 flash、不改 `board.toml`；只读 `stage/EFI/UniXNU/` 下的两个文件。

## 2. 跑什么

```sh
# PAYLOAD = F1 产物目录，例如 /mnt/e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/stage/EFI/UniXNU
PAYLOAD=<F1 产物目录>
cd /mnt/e/hackios/k60-platform27          # 块 2 要 import scripts/pong_adt_contract.py
MANIFEST=$PAYLOAD/pong-boot-manifest.json
ADT=$PAYLOAD/kernel.macho.adt
```

两块的正文照抄 `docs/research/ios27/SMP-STEP-DECODE.md` §6.2（块 1 读 `boot_args cpus=`，块 2 读 ADT 的
`/cpus` 子节点数与每个节点的 MPIDR / `state`，最后打 `VERDICT:`）。不要凭记忆重写——那两块是自测过的原文。

## 3. 期望输出与判读

| 观察 | 含义 | 下一步 |
|---|---|---|
| `manifest cpus = 1` + `ADT /cpus children: 1 ['/cpus/cpu0']` + `VERDICT: AGREE on 1 core(s)` | 配置与产物一致，stage-0 就是单核 | 回 Lead 一行；SMP 表本轮不用；0542 保持「备着」，0543 不写 |
| `manifest cpus = 8` + `ADT … children: 8` + `AGREE on 8 core(s)` | 配置侧已被改成 8 核，且生成器也已放开 | 回 Lead 一行；0542 转为「在用」；0543 仍等 Lead 把 SMP 排进阶段（§6.3） |
| `VERDICT: DISAGREE - …` | 两处不等（例如 manifest 说 8、ADT 只有 1） | **停**：先回报这一行，不读 A 表；这是产物内部矛盾，不是核起不来的问题 |
| `manifest cpus = ABSENT` | `boot_args` 里没有 `cpus=`，XNU 回落到 DT 拓扑 | 以 ADT 节点数为准回 Lead，并注明「靠 DT 拓扑」 |
| `No such file: pong-boot-manifest.json` 或 `kernel.macho.adt` | 构建没走到 payload 阶段 | 不是平台线问题；交回构建线，附路径 |
| ADT 里 `state=<absent>` 或 `<empty>` | 生成器版本比当前脚本旧 | 记下来回 Lead，别当成「没有 running 核」的证据 |

## 3.5 证据通道四问（P-307，Lead 广播 2026-11-22）

第 3 步「日志里若有 `ArmCpu:` 行」里的那个日志，是一个**有寿命的通道**，不是一直存在的记录。
按 `scripts/check-channel-lifetime.py` 的四问写死，读判读表之前先读这一段：

| 问 | 本线通道（USB CDC-ACM 控制台 / ramoops 镜像）的答案 |
|---|---|
| `lifetime` | 只在**同一次启动内**有效。ramoops 落在 DRAM，掉电或复位即归零（P-307）；控制台环也只是内存里的环形缓冲，`bsd_init` 起来前根本不存在（P-300） |
| `read_moment` | 两种：同一次启动内从 USB 控制台读；或在**复位之前**从 ramoops 镜像读。跨复位的「上次启动日志」在本板不存在——读卡器在 DXE 里读到的那块已经被复位清掉 |
| `writer` | XNU 的 `kprintf` → 串口/控制台驱动（`bsd_init` 之后才注册）与 ramoops 后端；固件层此前不写 |
| `loss_condition` | 任何一次复位、掉电、长按电源、或固件重新训练内存，都会让 ramoops 归零；控制台本身在 `bsd_init` 之前不存在 |

两条由此而来的判读纪律：

- **0 字节日志不能解读成「内核没跑」**（P-300）。黑屏 + 空日志只能证明「我们听不到」，不能证明执行到哪。
  所以本表第 4 步「拿到 `ArmCpu:` 行再判」是**条件式**的：拿不到就不是「A 表全灭」，而是「本次没有证据」。
- 本轮 `docs/engineering/BOOT-FREEZE.md` 的 `state = "frozen"`：任何 `fastboot boot` 被 `scripts/flash.sh` 拦。
  本条线本来就不上机，冻结只影响「谁去取那些日志行」——取日志也必须先解冻，或在同一次启动内接上通路。

## 4. 回报格式（一行 + 路径）

```
platform27 F1 对账：<N> 核（manifest cpus=<N|ABSENT>，ADT /cpus=<N>），VERDICT=<AGREE|DISAGREE>；产物 <PAYLOAD>
```

`DISAGREE` 时把两块的原始输出贴全（比结论有用）。

## 5. 边界

- 判 SMP 只用**没跳过图像验证**的产物；`--skip-image-verification` 出的镜像（`build-native-bootimg-local.py:138-139`
  `'skipped by request'`）不得用于这个判断（`ADT-MULTICORE-PROPOSAL.md` §1.3、§4）。
- `MPIDR` 一律按小端读：`reg` 打印的 `00010000` 是 `0x100`。
- 本条线不写 `porting.toml`（Lead 认领）、不写 `step.device`。
