# 飞行卡：`gpu-pitch-20261119` —— 让 surface 只报一个行距

## 1. 为什么飞这一张

2026-11-19 的对照实验（`gpu-blitprobe2-20261119`，飞行 `usblog-20261119-070345`）把同一个
18,432,000 字节、同一个 `copyFromBuffer + commit + waitUntilCompleted` 形状拷到两个目标：

| 目标 | 耗时 | 吞吐 |
| --- | --- | --- |
| GPU 自有缓冲 | 1,993 µs | 9.25 GB/s |
| 固件帧缓冲 | 1,835 µs | 10.04 GB/s |

所以目标端不是瓶颈。真实路径的中位阶段是 `import 53` / `encode 424` / `submit 3,015` /
`gpu 5,302` / `sum 12,552` / `copy 12,631` µs —— 同一个拷贝比对照慢 6.7 倍，差别只有一个：
真实路径走的是 `copyFromTexture`（linear texture untile），因为 **surface 行距 5888、帧缓冲行距 5760**。

这 128 字节/行不是我们加的：`MiniIOSurface` 从 `IOSurfacePlaneBytesPerRow` 原样接受客户端给的值
（`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch` 里那段 `dictNumber(pd,
"IOSurfacePlaneBytesPerRow", 0)`；注释与行号见 `docs/research/gpu/ZIZHAN-DBUF.md` 之外的
2026-11-19 追查记录）。1440×4 = 5760 本来就是 64 的整数倍，我们自己的公式给出 5760。

这张卡验证一个单变量改动：**plane 是我们的，就只报一个行距**（自然对齐值 5760），
并把客户端请求值打进日志。若成立，untile、它的 5.3 ms 与那 128 字节/行的搬运一起消失。

## 2. 改了什么

- 同一个补丁文件里那段：不再采用 `IOSurfacePlaneBytesPerRow` 的请求值，一律用
  `alignUp(width * bytesPerElement, MINISURF_ROW_ALIGN)`；请求值与上报值不同时打印
  `MiniIOSurface: plane pitch asked=… reported=… (one pitch only)`。
- 没有别的改动。CPU 侧行为、参数行、插件字节均不变。

## 3. 前置条件（任一不成立就不飞）

- **P1** 构建全绿：八步 48 项、`image-arg-audit`、`verify-boot-image`、`kernel archives`。
- **P2** 内核里必须有 `plane pitch asked=` 这条串；没有就是补丁没进镜像。
- **P3** 插件钉住 `metal-plugin-20261119p`（`PongAdrenoMetal` sha256 前缀 `c7cfd63b`）。
- **P4** `K60_AGENT_ID` 已设，设备在 fastboot 或 adb（supervisor 会在 claim 内重启）。

## 4. 判据

### 4.1 有效性（先判这一层，P-236）

三项同时成立才算有效：`MiniIOMobileFramebuffer: N frames`（N>0）、
`Pong Metal: c<n>/0 d<n>`（n>0）、至少一条 `scanout frames=`。
若 `DeviceLost` 出现 ⇒ 按 P-244 判 INVALID（GPU 已死，帧率无意义）。

### 4.2 成功判据

- **S1** 无 `panic(`、`K60KEXC`、`crashed: backboardd`。
- **S2** 恰一条 `MiniIOSurface: plane pitch asked=… reported=…`，并记录两个数。
- **S3** `scanout copy …` 行报告的形状是 `single run`（而不是 `texture untile`）。
- **S4** 若为 `single run`：`encode` 中位 < 1,000 µs，`gpu` 中位 < 2,500 µs。
- **S5** `copy` 中位 < 10,000 µs（基线 12,631 µs）。
- **S6** 仍出帧且 `imports == frames`。
- **S7** 画面正确性**不由本卡判**：这只能由用户目视。日志只负责证明形状与数字。

### 4.3 失败规则

- **F1** panic / backboardd 崩 ⇒ 立即回滚这条改动。
- **F2** 没有 `plane pitch asked=` 行 ⇒ 改动没进镜像，不要读成「没有效果」。
- **F3** 仍是 `texture untile` 且 `reported=5888` ⇒ 我们的计算没生效（走了别的分配路径）。
- **F4** `single run` 但 `gpu` ≥ 5,000 µs ⇒ 对照的 1.9 ms 不适用于这条路径，需重新对照。
- **F5** 用户目视发现画面斜切/错行 ⇒ 回滚，并记录「客户端确实按它请求的 5888 写入」。
- **F6** 零帧 ⇒ 按 P-236 判 INVALID 并重飞同一张镜像、同一套判据，不许改阈值。

## 5. 结果登记

（飞行后写在这里；`criteria-sha256` 在第一次写入时钉入。）
