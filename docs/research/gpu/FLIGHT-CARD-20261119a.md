# 飞行卡 2026-11-19 · `gpu-consolidated-20261119`

第一张把**已上机证明的四条线**（面板 120 Hz 切档、12-bit 背光、电池 sample-dirty、wifi tip）
与 GPU 实验放在同一个镜像里的飞行。在此之前每一张 GPU 镜像都跑在 60 Hz 面板上，
帧率数字里同时混着「渲染慢」和「面板只给 60 Hz 拍」两个原因（P-236 同族：先把环境定死再量）。

镜像目录：`gpu-consolidated-20261119`

## 1. 这张镜像里有什么

| 来源 | 内容 | 先前证据 |
| --- | --- | --- |
| `feat/120hz-panel` | `K60Backlight.cpp`、`K60BacklightCodec.h`、`PongDsiPanel` 的 11 包切档、`patches/display/0620` | `120hz-7` PASS：11 包 rc 0、`te` 55→120/s、SpringBoard 172、backlight `conformance=1 control=1` |
| `fix/battery-sample-dirty-build` | 电池采样脏位修复 + ADSP owner/rail/glink 栈 | `5beaffb2` 合并前的分支证据 |
| `test/wifi-he-scan` | wifi 线尖端（仅代码与文档，状态仍 `parked`） | wifid 能开 80211 user client |
| `feat/gpu-metal-hw` | 逐阶段计时、纹理 untile 路径、gmem 渲染模式、`publishMapped` 探针 | cards k/m/n/o |

切档与背光**改为默认开启**（`p120=0` / `vsync=120` / `k60_backlight_control=0` 是退出开关），
因为 arm64 命令行只有 607 B 而上限已用到 596 B，装不下 `p120=1`(7 B) 与
`k60_backlight_control=1`(24 B) 两者。

## 2. 前置条件（不满足就不要飞）

- **P1** 构建走 `scripts/build-strict.sh`，`eight-step` 通过、`image-arg-audit: OK`、
  `verify-boot-image: OK`、`kernel archives` 四项齐全。
- **P2** 内核里能找到探针串：`publish sample`、`wskipped=`、`PONG WC: distrust latched`、
  `imports=%llu import=`。缺任何一条说明镜像不是这棵树编的。
- **P3** 内核里能找到面板与背光串：`K60 PANEL: INTF1` 与 `conformance=`。
- **P4** 插件 bundle 的 `PongAdrenoMetal` 含 `gmem,nocb`（`strings … | grep -E '^(gmem,nocb)$'`）。
- **P5** `K60_AGENT_ID` 已设置（boot claim 要署名）。
- **P6** 设备在 fastboot；只 `fastboot boot`。

## 3. 这次要回答的问题

1. 面板在**合并后**还会不会切到 120 Hz？合并不是文本拼接，切档调用点在
   `PongAdrenoScanout.cpp` 的首帧路径上，任何一次冲突取舍都可能把它摘掉。
2. 背光在合并后还是两端可调吗（`conformance=1 control=1`）？
3. 120 Hz 面板 + GPU 路径同时在场时，帧间隔分布是什么形状？此前 12.45 fps、
   帧间隔中位 28.9 ms 是在 60 Hz 面板上量的，不能直接拿来当基线。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

零帧的一飞**判无效**，不算任何 F 规则命中。有效要求：
`MiniIOMobileFramebuffer: <n> frames` 有 n>0、`Pong Metal: c<n>/0` 有 n>0、至少一条 `scanout frames=`。

### 4.2 成功判据

- **S1** 无 `panic(`、无 `K60KEXC`、无 `crashed: backboardd`。
- **S2** 面板切档：至少一条 `K60 PANEL: INTF1 after the UI frame te 120/s`。
- **S3** 背光：至少一条 `conformance=1 control=1 stats=`。
- **S4** GPU 仍出帧：至少一条 `scanout frames=`，且客户端 `Pong Metal: c<n>/0 d<m>` 的 n>0。
- **S5** `imports` 等于 `frames`（每一行都成立），证明扫出仍是一帧一导入。
- **S6** 帧间隔中位 < 40 ms（比上一轮 60 Hz 面板下的 28.9 ms 更差即算回归——
  120 Hz 拍只会让等待变短，变长说明合并引入了新开销）。
- **S7** 存储与电池不回归：`K60DATA` 挂载成功、无 `transportFailure`、
  无 `PONG_UFS: no Apps SMMU lease` 之外的 UFS 失败行。

### 4.3 失败规则

- **F1** 出现 panic／`K60KEXC`／`crashed: backboardd` ⇒ 回滚合并，先修再谈 GPU。
- **F2** 没有 `K60 PANEL: INTF1` 任何一行 ⇒ 面板代码没进镜像，合并丢了文件。
- **F3** 只有 `te 55/s` 而没有 `after the switch` / `after the UI frame` 行 ⇒
  切档调用点在合并里失效，按 `PongAdrenoScanout.cpp` 的首帧路径逐个对照。
- **F4** 有 `conformance=` 但不是 `conformance=1 control=1` ⇒ 背光回归，停飞。
- **F5** 有效性不成立 ⇒ 判无效，重飞同一张镜像一次；连续两次无效再查镜像。
- **F6** `imports` 不等于 `frames` ⇒ 扫出路径回归，先查 `PongAdrenoScanout.cpp:195-196` 的释放顺序。

## 5. 结果登记

（飞完后填：镜像 sha256、证据目录、S1–S7 逐条、命中的 F 规则、帧间隔分布、结论与下一步。）
