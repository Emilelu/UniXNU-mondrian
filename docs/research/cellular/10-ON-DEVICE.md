# 上机实测记录（cellular L3）

> **状态：已上机一次（2026-11-15），结论是「载具缺失」，不是枚举失败。**
> 只有拿到真实日志的行才填值，其余一律 `TODO` / `未出现`；
> 填入时必须同时给出日志行原文与日志文件路径。

镜像与分支的对应关系：待上机镜像是 `cellular-l3-20261115a`，它的代码状态是提交 `aa6b985`（已并入 `origin/main` 的 `ecda32f`）。
本篇之后只会新增文档提交（`docs/` 下），不会再改任何进镜像的文件——所以即使 HEAD 前进，
镜像仍然精确对应 `c350220`，回溯时以本节记录的 tag 与 sha256 为准。

## 1. 抓取信息

| 项 | 值 |
| --- | --- |
| 镜像 tag | `cellular-l3-20261115a` |
| boot.img sha256 | `47009f2d49814fcd95d7e12c556f567069367a289fdb5cccb6b9ae92d46c25a3` |
| boot.img 字节数 | 201891840 |
| kernel sha256 | `2841d160f3cb474861d858c39bf0be74bf929499b31e4b1526678dc9f29e0e03` |
| kernel 字节数 | 105504768 |
| series 条数 | 227 |
| series sha256 | `1d1351130f9ece8b1c0bace828431b4259f4eca073b3360af57e484215428f98` |
| frozen 指纹 | `30fdf3fff19f45aaf7c4b4ebfebe763e5e674bc8b9f6250236c6c2ac33fddc5c` |
| 命令行参数个数 / 字节数 | 30 / 588（`check-image-args.py` 实测） |
| 上机内核命令行里的门控 | `pong_modem=2`（`build-manifest.json` 的 `kernel_args_requested` = `['pong_modem=2']`，`payload_args` 末位即 `pong_modem=2`） |
| 日志文件路径 | `E:\k60-work\evidence\usblog-20261115-141845\console.log` |
| 日志文件字节数 | 221401 |
| 抓取时间（本地时区） | 2026-11-15 14:18:45 |
| 设备 serial | TODO（Lead 未提供） |
| 从 Android 冷启动还是 warm switch | TODO（Lead 未提供；决定 SMEM/GLINK 是否是新 epoch，见 09 篇用例 F） |

**先确认门控再读结论**：命令行里没有 `pong_modem` 或等于 0 时，日志里一行 `K60MODEM` 都不会有，
那不代表失败（09 篇用例 A）。

## 2. 判据矩阵（照 09 篇的 A–J 十种用例）

每行先填「命中行原文」（从日志里逐字复制，含数字），再填「结论」。
没有命中的行写 `未出现`，不要留空——留空无法区分「没查」和「查了没有」。

**载具前置（先查这两行，再对 A–J）**：日志里出现
`K60MODEM qrtr: smem item … missing` 和/或 `K60MODEM carrier absent: no modem image staged at …`
⇒ 这是**载具缺失**，不是 `verdict no reply`，也不是任何一项 PAS 失败：
A–J 全部不适用，结论直接写「载具缺失」，依据 11-CARRIER.md §0。
`judge-qrtr.sh` 命中这两行会直接输出 `verdict: carrier-absent` 并跳过 wanted 号一段。

| 用例 | 形态（09 篇） | 命中行原文 | 结论 |
| --- | --- | --- | --- |
| A | 无输出（门控关闭） | 未出现 | 不适用（门控已开，日志有 `K60MODEM probe begin`） |
| B | `carrier absent` + `pas skipped` | `K60MODEM qrtr: smem item 480 missing rc=-5`（481 行）／ `K60MODEM carrier absent: no modem image staged at 0x8bc00000`（482 行）／ `K60MODEM pas skipped, nothing was handed to the secure monitor`（483 行） | **载具缺失**：镜像从未被放进 carveout，PAS 没有发出任何 SCM 调用；不是枚举失败（11-CARRIER.md §0） |
| C | `cannot map the carveout head` | 未出现 | — |
| D | PAS 七行全成（plan/copy/auth_reset/init_image/mem_setup） | 未出现 | — |
| E1 | `scm cmd=0x5` + `auth_reset failed` | 未出现 | — |
| E2 | `scm cmd=0x1` + `init_image failed seg=…` | 未出现 | — |
| E3 | `scm cmd=0x2` + `mem_setup failed` | 未出现 | — |
| F | `glink fifo not fresh`（无 verdict 行） | 未出现 | — |
| G | `modem not ready`（无 verdict 行） | 未出现 | — |
| H | `verdict no reply services=0 … polls=500` | 未出现 | — |
| I | `verdict ok … wanted=…` | 未出现 | — |
| J | `malformed=` 非 0 | 未出现 | — |

判决行原文（`K60MODEM qrtr: verdict …`）：未出现（日志里没有 verdict 行，因载具前置已命中）

四个数字直接抄下来，不要换算：`services=` 未出现 ／ `node0=` 未出现 ／ `wanted=` 未出现 ／ `malformed=` 未出现 ／ `polls=` 未出现

## 3. 与 Android 侧 37 行基线的差异

基线出处：`docs/research/cellular/08-QRTR-SERVICES.md` §5（来自设备 `6033dbec` 的 `/data/vendor/qrtr/qrtr-lookup.txt`）。
比对规则：service / instance / version 三条必须一致；**port 不作判据**（随 modem 复位变化）。
「XNU 侧实测」列填命中的那条 `K60MODEM qrtr: service …` 行的 port 值，没命中写 `未出现`。

本轮日志 `K60MODEM qrtr: service` 行 0 条（枚举从未开始），下表 37 行「XNU 侧实测」全部是 `未出现`，不再逐行重复注明。

| 服务号 | 名字（Android 侧原文） | instance | version | XNU 侧实测（port） |
| --- | --- | --- | --- | --- |
| 65508 | `<unknown>` | 0 | 1 | TODO |
| **21** | Modem embedded file system service | 0 | 1 | TODO |
| 24 | Thermal mitigation device service | 0 | 1 | TODO |
| **4097** | DIAG service (MODEM:CMD) | 1 | N/A | TODO |
| 23 | Thermal sensors service | 0 | 1 | TODO |
| 36 | Persistent device configuration service | 0 | 1 | TODO |
| 17 | Specific absorption rate service | 0 | 1 | TODO |
| 34 | Coexistence service | 0 | 1 | TODO |
| 85 | `<unknown>` | 0 | 1 | TODO |
| 76 | `<unknown>` | 0 | 1 | TODO |
| 50 | `<unknown>` | 0 | 1 | TODO |
| 12 | Phonebook Management service | 0 | 1 | TODO |
| **3** | Network Access Service | 0 | 1 | TODO |
| 47 | `<unknown>` | 0 | 1 | TODO |
| **11** | User Identity Module service | 0 | 1 | TODO |
| 228 | `<unknown>` | 0 | 1 | TODO |
| **1** | Wireless Data Service | 0 | 1 | TODO |
| 4 | Quality Of Service service | 0 | 1 | TODO |
| 26 | Wireless data administrative service | 0 | 1 | TODO |
| 8 | AT service | 0 | 1 | TODO |
| 77 | `<unknown>` | 0 | 1 | TODO |
| 5 | Wireless Messaging Service | 0 | 1 | TODO |
| 75 | `<unknown>` | 0 | 1 | TODO |
| 74 | `<unknown>` | 0 | 1 | TODO |
| 42 | Data system determination service | 0 | 1 | TODO |
| 2 | Device Management Service | 0 | 1 | TODO |
| 48 | `<unknown>` | 0 | 1 | TODO |
| 68 | `<unknown>` | 0 | 1 | TODO |
| 73 | `<unknown>` | 0 | 1 | TODO |
| 78 | `<unknown>` | 0 | 1 | TODO |
| 29 | Circuit switched videotelephony service | 0 | 1 | TODO |
| 7 | Authentication service | 0 | 1 | TODO |
| 86 | `<unknown>` | 0 | 1 | TODO |
| 71 | `<unknown>` | 0 | 1 | TODO |
| 33 | IMS application service | 0 | 1 | TODO |
| 18 | IMS settings service | 0 | 1 | TODO |
| **16** | Location service (~ PDS v2) | 0 | 2 | TODO |

汇总行：命中 0 ／ 37；五个判据号命中 0 ／ 5。

## 4. 结论与证据升级条件

### 4.1 结论

**枚举未成立——载具缺失**（依据第 2 节用例 B：481-483 行）。
modem 镜像从未被放进 `0x8bc00000` 的 carveout，PAS 一步都没跑，QRTR 自然没有东西可枚举。
这不是 QRTR/PAS 代码的观测结果，而是「没跑起来」，所以不满足 §4.2/§4.3 的升级条件。
载具三案与裁决见 `docs/research/cellular/11-CARRIER.md`。

### 4.2 把 `EIGHT-STEPS.toml` 的 ⑧ 从 prediction 改成 done 的条件

三条**同时**满足才改：

1. 日志里有 `K60MODEM qrtr: verdict ok` 且 `wanted >= 3`（09 篇用例 I）；
2. 第 3 节表里至少三个判据号（`21` / `1` / `11` / `3` / `16` 中任意三个）在 XNU 侧实测命中；
3. 第 1 节的 tag、boot.img sha256、日志路径三项齐全，任何人可据此复现同一次上机。

任一条不满足就保持 `done=false`，并把实际形态写进 `step.device` 的 prediction 之外的位置（不改 prediction 原文）。

### 4.3 往 `porting.toml` 的 `evidence` 加行的条件

只加 `kind = "device"` 且 `reference` 指向本篇的记录，`result` 必须包含：判决行原文 + 命中的判据号个数。

**不加的情况**：只有 `carrier absent`（用例 B）、只有 `not fresh`（用例 F）、只有 `modem not ready`（用例 G）——
这三种是「没跑起来」，不是观测结果，属于下一步的输入而不是证据。

`completion`（"A device boot shows the modem enumerated over QRTR with a readable firmware revision"）
在 §4.2 三条满足之前**不动**；即使满足，也只更新 `status` 与 `evidence`，
`completion` 还要求可读的 firmware revision，那属于 L4 范围。

### 4.4 本轮不做的事

- 不改 `K60ModemQrtr.c` / `K60ModemLink.c`（DIAG 4097 进 verdict 的改动等这次结论落定后单独做）；
- 不 boot（上机由 Lead 执行）；
- 不在本篇写任何未实测的数字。
