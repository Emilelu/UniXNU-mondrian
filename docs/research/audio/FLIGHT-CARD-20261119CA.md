# 上机卡 2026-11-19ca —— 用 APR 甲板探测本机 ADSP 是否接受 legacy AFE 服务

## 1. 目的

bz 已经证明：把 TDM 语义改对（16 bit 位宽、长同步、3.072 MHz 时钟）之后，
GPR 上的 legacy AFE 五个参数包仍然全部 `status=2`（`0x000100fc` / `0x000100ef` / `0x000100e5`），
而每条请求都确实收到 AFE 服务（域 2、端口 4）的应答，只是回 EFAILED。
by 已经证明 speaker 图换上游 `AUDIO_IF_SINK 0x0700117C` 会被拒，本机 ADSP 只认 `0x0700100E`。
⇒ 缺位时钟不是参数值问题，也不是模块 id 问题，而是**这套 legacy AFE 参数在本机固件上被整体拒绝**。

t970（pong 的 fork）不用 GPR 24 字节头，而是 **APR 甲板**（20 字节头、version 2、hdr_len 5），
用 `AFE_SVC_CMD_SET_PARAM 0x000100f3`（v1）做 group/clock、`AFE_PORT_CMD_SET_PARAM_V2 0x000100ef` 做端口参数。

本飞只做一件事：用 APR 甲板发两个最小包 —— 一个 `DEVICE_START 0x000100e5`（port 0x9020）、
一个 `SET_PARAM 0x000100f3` group enable（module 0x00010254 / param 0x00010256 / group 0x9120）——
看本机 ADSP 是否应答。一次 boot 就能决定下一步走 APR 封装还是彻底放弃 legacy AFE。

## 2. 前提证据（上机前必须全部成立）

| 编号 | 证据 | 结果 |
| --- | --- | --- |
| P1 | 0003 补丁含 `pong_audio_afe_apr_probe()`，在六步完成后被调用 | 是（0003 = 55,181 B / 1,624 行 / sha256 6a6d7b04…） |
| P2 | 探针用 APR 甲板：`0x52,0x02` 头 + src 4:3 + dst 4:2 + token + opcode，总长写进字节 2..3 | 是 |
| P3 | 探针 token 固定 `0x00025a00`（start）与 `0x00025a01`（group enable） | 是 |
| P4 | 真实前像 apply 链（0503/0504/0505/0001 → 0003）通过，产物 2,565 行 | 是 |
| P5 | `check-patch-apply.py --all` 通过（313 补丁可解析） | 是 |
| P6 | 门禁 docs / eight / patches 全 0 | 是 |
| P7 | `verify-boot-image: OK` | 是（18:26 构建） |

本卡判定的镜像：`audio-probe-20261119ca`，
`boot.img` = `e3a6be73f2c4b6830aaa4592c43d7e4fe901b62394c4fcc12fc14d14c89efc30`（201,895,936 B）。

## 3. 抓取

```
powershell -NoProfile -ExecutionPolicy Bypass -File E:/hackios/k60-audio-adsp/scripts/boot-and-capture.ps1 \
  -Image E:\k60-work\artifacts\audio-probe-20261119ca\boot.img \
  -OutDir E:\k60-work\evidence\audio-probe-ca\run1-<HHMM> -Seconds 300
```

只 `fastboot boot`，不 flash。证据目录需含 `console.log`、`capture.json`、`boot.json`。

## 4. 判据

**成功（S，全部满足才算这一飞可判读）**

- **S1** `capture.json` 的 `state` 为 `captured` 或 `captured-budget-complete`，且 `console.log` ≥ 500 行。
- **S2** 出现 `PongAudio: APR probe start bytes=24 rc=0`。
- **S3** 出现 `PongAudio: APR probe group enable bytes=52 rc=0`。
- **S4** 出现 `token=0x00025a00` 的 `glink adsp_apps rx` 应答，并记下它的 `status` 值。
- **S5** 出现 `token=0x00025a01` 的 `glink adsp_apps rx` 应答，并记下它的 `status` 值。
- **S6** 按预置分支写出判决：两条 `status` 都为 0 → 走 APR 封装改造（t970 配方）；任一为 2 → 转 AR/CDC-DMA，不再在 legacy AFE 上耗。判决写进 §5。

**失败（F，任一命中即判 FAIL，并在 §5 记下命中的是哪一条）**

- **F1** 出现 panic、`K60KEXC`、或抓取被复位中断（`panicMarker` 非空 / 设备中途掉线）。
- **F2** `console.log` < 500 行或零字节（启动没到探针）。
- **F3** `APR probe start` 行缺失（探针没跑到）。
- **F4** `APR probe group enable` 行缺失。
- **F5** 两条 `token=0x00025a00/0x00025a01` 的应答都没有（包没到 AFE 服务，无法判读）。
- **F6** 出现 `glink adsp_apps down`（ADSP 掉线，本轮证据无效，需重飞同镜像）。

## 5. 结果登记

criteria-sha256: 2daa902bdf1f4f61b060e09b39c0b41852a65d32bc607a77fd12673d741a14c8

（上机后填写：镜像名、boot.img sha256、证据目录、S1–S6 与 F1–F6 的实测值、两条 rx 的 status、判决。）
