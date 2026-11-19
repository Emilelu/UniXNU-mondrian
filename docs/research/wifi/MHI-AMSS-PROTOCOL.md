# MHI 固件下载：AMSS 那一次 BHIe 到底由谁触发（c8 之前的离线审查）

> 目的：c7 只把状态钉到「硬件在 SBL/READY、host `ee` 还是 PBL、转换没发生、原因未定」。
> 本文只读源码，回答一个问题：**c8 之前要先排除什么**，以及 c8 的结果该怎么分层验收。
> 证据基线：k60-wifi `82086f1`（docs(wifi): audit held c8 execution path）与它生成到
> `/opt/k60/trees/k60build/wifi/ath11k-c8/mhi/` 的补丁后源码；pinned Linux
> `drivers/bus/mhi/`（mainline 5.x 口径）。本文不含任何设备结论。

## 0. 一句话

主线 MHI 的 AMSS 下载**没有独立入口**：它挂在「收到 EE 事件 → 排队 DEV_ST_TRANSITION_SBL →
FBC 下载」这条链上；补丁后源码里这条链有**两条**可达路径（PBL 直入 FBC、以及 queued SBL 再入），
两条都**忽略** `mhi_download_amss_image()` 的返回值，且**没有去重/取消**。
所以 c8 若「推了 AMSS 但状态机没往前走」，先要分清是**第二次调用重放了已下载内容**，
还是**第一次调用失败被吞掉**。

## 1. 主线调用链（行号按 pinned Linux）

| 位置 | 代码 | 含义 |
|---|---|---|
| `linux:drivers/bus/mhi/host/main.c:893` | `case MHI_PKT_TYPE_EE_EVENT:` | 事件环里唯一的 EE 事件入口 |
| `main.c:896` | `MHI_TRE_GET_EV_EXECENV(local_rp)` | 从 TRE 取设备执行环境 |
| `main.c:900-903` | `MHI_EE_SBL` → `DEV_ST_TRANSITION_SBL` | SBL 环境只排队一个状态转换 |
| `main.c:904-906` | WFW/AMSS → `DEV_ST_TRANSITION_MISSION_MODE` | 已进 AMSS 才直接进 MISSION |
| `pm.c:823` | `case DEV_ST_TRANSITION_SBL:` | 状态机消费者 |
| `pm.c:830` | `mhi_cntrl->ee = MHI_EE_SBL;` | host 侧缓存值在这里才更新 |
| `pm.c:832` | `mhi_create_devices(mhi_cntrl);` | 建 MHI 设备节点 |
| `pm.c:833-834` | `if (mhi_cntrl->fbc_download) mhi_download_amss_image(...)` | **AMSS 下载的唯一常态触发点** |
| `pm.c:836` | `mhi_uevent_notify(...)` | 通知用户态 |
| `boot.c:633` | `mhi_download_amss_image()` | FBC 的 BHIe 阶段 |
| `boot.c:640` | `if (!image_info) return -EIO;` | 没有 fbc_image 就失败 |
| `boot.c:643-645` | `mhi_fw_load_bhie(..., &image_info->mhi_buf[entries-1])` | 只推 **vector table（最后一项）**，它内部按表遍历数据段 |
| `boot.c:646-653` | `dev_err("MHI did not load AMSS, ret:%d")` + `MHI_PM_FW_DL_ERR` | 失败会置错误态 |

`DEV_ST_TRANSITION_SBL` 在整个 `drivers/bus/mhi/` 下只有 **两个**命中：`main.c:902`（排队点）与
`pm.c:823`（消费点）。**没有 EE 事件，就没有这次下载**——这是 c7「AMSS 未推」的结构性解释。

## 2. 补丁后多出来的两条路径（82086f 审计）

`scripts` 侧把 FBC 下载改成「硬件已报 SBL 就可以直接推」，于是 `pm.c` 的转换表在
`/opt/k60/trees/k60build/wifi/ath11k-c8/mhi/pm.c` 里成了本地快照：

| 路径 | 位置 | 行为 | 风险 |
|---|---|---|---|
| A：PBL 直入 FBC | 生成源码 `boot.c:622-644` | 条件 `fbc_download && hardware SBL` 成立就置 host `ee = SBL` 并调用 `mhi_download_amss_image()`；**返回值被忽略** | 下载失败会静默继续，host 以为自己进了 SBL |
| B：queued SBL 再入 | `pm.c:826-839`（`pm.c:809-811` 先拼本地 transition 快照） | 状态机照常消费 queued `DEV_ST_TRANSITION_SBL`，在 FBC 下**再调一次** `mhi_download_amss_image()`；`:837` 返回值同样被忽略 | 第二次调用不是「第二次硬件完成」，是重放 |

调度器只阻止**同一个 worker 递归**，不阻止「A 之后再顺序执行 B」。所以：

- **A 成功 → B 会再推一遍**（浪费，但通常无害；若设备已离开 SBL，BHIe 可能直接失败并被吞）；
- **A 失败 → B 可能补推成功**，也可能同样失败——**日志里看不到返回码**，只剩 uevent/超时；
- 任何一次成功后 **没有取消 B** 的路径（无 dedup key、无状态标志）。

> 这就是 c8 之前必须先解决的可观测性问题：**当前插桩看不到 `mhi_download_amss_image()` 的返回值**，
> 也分不清「哪一次调用成功了」。

## 3. c7 已观测到的事实（只作边界，不作因果）

证据 `E:/k60-work/evidence/usblog-20261116-122546/console.log`（227,186 B / 3,367 行 / SpringBoard 128）：

```
:608  Pong MHI: irq entered er_index=0 dev rp=0xa0001a00 host rp=0xfffffff9bb055a00
:610  Pong MHI: irq found no new events
:632  Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200
```

- 硬件侧：`exec_env=1` = SBL、`mhi_state=1` = READY、`MHISTATUS=0x101` = ready 且 SYSERR=0；
  `MHICTRL=0x200` 是**主机写下去请求 M0**，不是「设备已在 M0」。
- host 侧：`ee=0`（PBL 初值）、`pm_state=2` = `MHI_PM_POR`（`internal.h:128/142`）。
- 共享 `er_ctxt->rp` 的初值由主机在 `init.c:391-393` 写成 `rbase`，CPU 侧读到的值不推进，
  **只证明主机没消费**，不证明设备没写、也不证明 DMA 可见性正常（`init.c:480-535` 里
  CCABAP/ECABAP/CRCBAP 是三个独立上下文指针，IOVA 包络 `0..dma_mask` 只是范围）。
- 抓取里没有 `amss entries` / `vec` / `event type=` / `EE event` 打印，只能说明
  **抓取期间没看到这些代码路径的输出**，不能反推设备行为。

## 4. 尺寸算术（避免再把 vector table 当数据段）

`boot.c:372-405`：`entries = DIV_ROUND_UP(alloc_size, seg_size) + 1`；`boot.c:430-434` 把
vector table 拷进最后一项。以 c7 的 `amss20.bin = 5,296,128 B`、`sbl=524288` 计：

- `DIV_ROUND_UP(5,296,128, 524,288) = 11` 个**数据** buffer；
- 加上 vector table → `entries = 12`；
- 10 个满块 + 尾块 `5,296,128 - 10×524,288 = 53,248 B`；
- vector table 里 11 个数据项（不是 12 个）。
- `vector bytes=5296128` 是**文件长度**，不是 vector table 的字节数——这两个数不能混。

## 5. c8 之前建议补的三件（都在 wifi 线，不在本仓 main）

1. **返回值可见**：给 A/B 两处 `mhi_download_amss_image()` 各包一层，打印 `site=A|B ret=%d`
   与调用前后的 `ee/pm_state`；失败时打印 `image_info->entries` 与最后一段长度。
2. **去重/取消**：加 `amss_dl_state`（IDLE/DOWNLOADING/DONE/FAILED）；B 看到 DONE 就跳过并打印
   `site=B skipped`，看到 DOWNLOADING 就打印并返回，避免重放把失败掩盖成「已下载」。
3. **READY→M0 协议**：`mhi_set_mhi_state(MHI_STATE_M0)` 之后确认设备侧 `MHISTATUS` 的
   `MHISTATE` 字段变化，而不是只看主机请求已写入。

## 6. c8 的分层验收（不许合并成一格）

| 层 | 看什么 | 通过含义 |
|---|---|---|
| L1 BHIe 返回 | `site=A/B ret=0`，且 `amss entries=12 vec=11` | 主机确实把 AMSS 推完 |
| L2 硬件 EE | 之后的 `exec_env` 从 1 变 2（AMSS）或 4（WFW） | 设备接受了镜像并跳转 |
| L3 MHI M0 | `mhi_state` 到 2、host `ee` 进 MISSION、事件环 rp 推进 | MHI 协议层通了 |
| L4 QMI/ath11k | `QMI`/`ath11k: ...` 注册行、`wifi` 设备节点 | 芯片固件起来了 |
| L5 netdev | `ifconfig`/扫描出现接口 | 端到端可用（不是 c8 的目标） |

**c8 的最低可判定结果**：L1 有明确 ret，L2 有 `exec_env` 变化或明确不变。
若 L1 成功而 L2 不动，问题在设备侧（镜像/签名/段表）；若 L1 失败，先看 ret 与 entries。

## 7. 与文档其它部分的关系

- silent（0 字节）已结案于 P-215（UFS SMMU lease），与本文无关。
- **注意分支**：main 上的 `BLOB-RESIDENCY.md` / `BOOT-DEATH-BISECT.md` 还是旧快照，
  `C7-READING-GUIDE.md` 在 main 上**不存在**；MHI 段的结案版在
  `feat/wifi-final-conclusion`（`ea7f72d`）的 `BLOB-RESIDENCY.md` §11 与 `C7-READING-GUIDE.md` §3–§5，
  合并时以那份为准。本文只补充「c8 之前要排除什么」，不替它下结论。
- c7 的四支判据表（A/B/C/D）在指南 §3 保留为历史；c7 实测落在四支之外，原因是
  **两支相等**（设备在 SBL、主机在等 EE），不能写成「死锁」定论。
- 本文所有源码行号指向 pinned Linux；补丁后源码行号指向 `/opt/k60/trees/k60build/wifi/ath11k-c8/`，
  不同构建树可能漂移，引用时带树名。
