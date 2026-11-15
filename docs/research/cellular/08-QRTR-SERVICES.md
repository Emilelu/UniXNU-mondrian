# QRTR 服务号清单（上机比对用）

> 编号说明：Lead 指定的文件名是 `05-QRTR-SERVICES.md`，但 `05` 已被 `05-MODEM-IMAGE.md`
> （段表与搬运）占用，本目录编号不重复，故本篇用下一个空号 `08`。

本篇只有一个用途：上机跑 `pong_modem=2` 之后，把内核打印的 `K60MODEM qrtr:` 行
与本文的表格逐条对上，判断「内核枚举到的服务集合」与「Android 侧 modem 自己注册的
服务集合」是否一致。本文不改代码、不发 QMI、不做任何写操作。

## 1. 数据来源

原表在 `docs/research/cellular/01-ANDROID-INVENTORY.md:409-452`，来自设备 `6033dbec` 的
`/data/vendor/qrtr/qrtr-lookup.txt`（8209 B，2026-11-14 11:59，Android 主栈在管 modem、
remoteproc 状态 running）。抓取方式见同文 §5.3：`qrtr-lookup` 把结果写进文件，
stdout 只有表头——按 stdout 判空是工具用法错误。

对着原表数：**node 0 共 37 行**，其中 22 行有服务名、15 行 `qrtr-lookup` 显示 `<unknown>`
（那是工具自己的名字表没有该编号，不是服务不存在）。同文正文写「36 个服务」，
与它自己引用的表差 1 行——最可能是没把 `4097`（version 显示 `N/A`）算进去。
上机比对以**行**为准，不以正文的 36 为准。

## 2. 内核会打印什么（对照的锚点）

| 日志行 | 出处 | 含义 |
| --- | --- | --- |
| `K60MODEM qrtr: channel up` / `down` | `drivers/PongCellular/K60ModemLink.c:82` | GLINK 通道 `IPCRTR` 打开/关闭，modem 主动开 |
| `K60MODEM qrtr: sent hello and new_lookup (0x0a) from port 0x4000` | `K60ModemLink.c:254` | 通道 up 后各发一次 HELLO 与 NEW_LOOKUP |
| `K60MODEM qrtr: service 21 (0x15) instance 0 node 0 port 21` | `K60ModemLink.c:104` | 每收到一个 NEW_SERVER 打一行（service 十进制 + 十六进制） |
| `K60MODEM qrtr: verdict ok services=37 node0=37 wanted=5 malformed=0 polls=N` | `K60ModemLink.c:262` | 判决行；`services` 是收到的条数（含重复）、`node0` 是其中来自 node 0 的、`wanted` 是命中 §3 五号的条数 |

服务表上限 `K60_QRTR_MAX_SERVICES = 64`（`drivers/PongCellular/K60ModemQrtr.h:27`）：
超过 64 条只计数不入表，但 `services`/`wanted` 仍继续累加。

## 3. 五个判据服务（当前镜像的 wanted 集合）

`k60_qrtr_wanted()`（`drivers/PongCellular/K60ModemQrtr.c:102`）只认这五个号，
`verdict` 要求 `from_node0 != 0 && wanted != 0`（同文 :173）。

| 服务号 | 十六进制 | Android 侧名字（原文） | instance | node | port（Android 侧） | 证明什么 |
| --- | --- | --- | --- | --- | --- | --- |
| 21 | 0x15 | Modem embedded file system service | 0 | 0 | 21 | EFS 在跑 → NV/EFS 通道存在，是后续读写 NV 的前提 |
| 1 | 0x01 | Wireless Data Service | 0 | 0 | 82 | 数据业务栈（PDP/网卡）已就绪 |
| 11 | 0x0b | User Identity Module service | 0 | 0 | 80 | SIM/UIM 在跑 → 后面取身份、开卡都在它上面 |
| 3 | 0x03 | Network Access Service | 0 | 0 | 77 | 网络注册/搜网栈在跑 |
| 16 | 0x10 | Location service (~ PDS v2) | 0 | 0 | 111 | 定位服务，且 version=2，与 v1 同号不同版本 |

**port 会变**：QRTR 的 port 是 modem 启动时动态分配的，跨一次 modem 复位就不保证相同。
比对时 service / node / instance 三条必须一致，port 只要与 §5 表同量级即可，不作判据。

## 4. DIAG 4097（0x1001）：会被打印，但不计入 verdict

| 服务号 | 十六进制 | Android 侧名字（原文） | instance | node | port |
| --- | --- | --- | --- | --- | --- |
| 4097 | 0x1001 | DIAG service (MODEM:CMD) | **1** | 0 | 28 |

三条特殊性：

1. 它是全表唯一 `version` 列显示 `N/A` 的行（`qrtr-lookup` 对 0x1001 没有版本号可填）。
2. 它是 node 0 上唯一 `instance = 1` 的行（其余全是 0）。
3. 当前 `k60_qrtr_wanted()` 的 case 是 `{1, 3, 11, 16, 21}`，**不含 4097**，所以 `wanted`
   不会因 DIAG 增加，`verdict` 也不因它变绿。要把它算进判据，必须改
   `K60ModemQrtr.c:102` 的 switch 再**重建内核**：改的是进镜像的源文件，
   重建会产出新 kernel/boot.img，排队中的镜像 `cellular-l3-20261114d`
   （boot.img `5cf3df7f…`）就与分支不再一致，上机结果无法回溯到某个提交。
   所以本轮不改，等这条线自己的镜像上机、结论落定之后再单独做一次带新镜像的改动。
4. 仍然要列它的原因：DIAG 是开机很早就会出现的服务。上机若只看到 `4097` 而看不到
   `21/1/11/3/16`，说明 GLink 通了、名字服务也回了，但回复覆盖不全——这是「半成功」，
   与「一条都没回」是两种不同的故障。

## 5. node 0 全量 37 行（原样，含 `<unknown>`）

行号指 `docs/research/cellular/01-ANDROID-INVENTORY.md` 的源文件行号。

| 源行 | Service | Version | Instance | Node | Port | 名字（原文） | 本篇判据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 415 | 65508 | 1 | 0 | 0 | 19 | `<unknown>` | — |
| 416 | **21** | 1 | 0 | 0 | 21 | Modem embedded file system service | ✅ wanted |
| 417 | 24 | 1 | 0 | 0 | 23 | Thermal mitigation device service | — |
| 418 | **4097** | N/A | 1 | 0 | 28 | DIAG service (MODEM:CMD) | 观察，不计 |
| 419 | 23 | 1 | 0 | 0 | 35 | Thermal sensors service | — |
| 420 | 36 | 1 | 0 | 0 | 36 | Persistent device configuration service | — |
| 421 | 17 | 1 | 0 | 0 | 54 | Specific absorption rate service | — |
| 422 | 34 | 1 | 0 | 0 | 55 | Coexistence service | — |
| 423 | 85 | 1 | 0 | 0 | 62 | `<unknown>` | — |
| 424 | 76 | 1 | 0 | 0 | 72 | `<unknown>` | — |
| 425 | 50 | 1 | 0 | 0 | 73 | `<unknown>` | — |
| 426 | 12 | 1 | 0 | 0 | 74 | Phonebook Management service | — |
| 427 | **3** | 1 | 0 | 0 | 77 | Network Access Service | ✅ wanted |
| 428 | 47 | 1 | 0 | 0 | 79 | `<unknown>` | — |
| 429 | **11** | 1 | 0 | 0 | 80 | User Identity Module service | ✅ wanted |
| 430 | 228 | 1 | 0 | 0 | 81 | `<unknown>` | — |
| 431 | **1** | 1 | 0 | 0 | 82 | Wireless Data Service | ✅ wanted |
| 432 | 4 | 1 | 0 | 0 | 83 | Quality Of Service service | — |
| 433 | 26 | 1 | 0 | 0 | 84 | Wireless data administrative service | — |
| 434 | 8 | 1 | 0 | 0 | 85 | AT service | — |
| 435 | 77 | 1 | 0 | 0 | 86 | `<unknown>` | — |
| 436 | 5 | 1 | 0 | 0 | 87 | Wireless Messaging Service | — |
| 437 | 75 | 1 | 0 | 0 | 91 | `<unknown>` | — |
| 438 | 74 | 1 | 0 | 0 | 92 | `<unknown>` | — |
| 439 | 42 | 1 | 0 | 0 | 94 | Data system determination service | — |
| 440 | 2 | 1 | 0 | 0 | 96 | Device Management Service | — |
| 441 | 48 | 1 | 0 | 0 | 97 | `<unknown>` | — |
| 442 | 68 | 1 | 0 | 0 | 98 | `<unknown>` | — |
| 443 | 73 | 1 | 0 | 0 | 99 | `<unknown>` | — |
| 444 | 78 | 1 | 0 | 0 | 100 | `<unknown>` | — |
| 445 | 29 | 1 | 0 | 0 | 101 | Circuit switched videotelephony service | — |
| 446 | 7 | 1 | 0 | 0 | 102 | Authentication service | — |
| 447 | 86 | 1 | 0 | 0 | 103 | `<unknown>` | — |
| 448 | 71 | 1 | 0 | 0 | 104 | `<unknown>` | — |
| 449 | 33 | 1 | 0 | 0 | 105 | IMS application service | — |
| 450 | 18 | 1 | 0 | 0 | 107 | IMS settings service | — |
| 451 | **16** | **2** | 0 | 0 | 111 | Location service (~ PDS v2) | ✅ wanted |

相邻 4 行是 node 1（AP 自己）的，不是 modem 的，列在这里只为避免误读源文件：

| 源行 | Service | Version | Instance | Node | Port | 名字（原文） |
| --- | --- | --- | --- | --- | --- | --- |
| 466 | 1070 | 1 | 0 | 1 | 16387 | `<unknown>` |
| 467 | 52 | 1 | 1 | 1 | 16390 | Dynamic Heap Memory Sharing |
| 468 | 49 | 1 | 1 | 1 | 16409 | IPA control service |
| 469 | 4097 | N/A | 0 | 1 | 16414 | DIAG service (MODEM:CNTL) |

可靠性提醒：`<unknown>` 只代表 `qrtr-lookup` 的名字表里没有该编号，**不代表**服务无意义；
本篇不给它们编名字，因为编了就是猜测。上机时若这些号出现在 node 0，照实记录编号即可。

## 6. 上机比对流程（三步）

1. 抓日志：内核控制台或 `usblog` 里 `K60MODEM qrtr` 开头的全部行。
2. 数命中：`grep -c 'K60MODEM qrtr: service' ` 得到总条数，应与判决行的 `services` 相同；
   再用 `21 (0x15)`、`1 (0x1)`、`11 (0xb)`、`3 (0x3)`、`16 (0x10)` 五个模式各 grep 一次，
   命中个数应与 `wanted` 相同（同一服务多 instance 会多计）。
3. 逐条对表：把每条 `service … instance … node … port …` 与 §5 的 service/instance/node 对；
   port 不同不算失败（§3 末段）。

## 7. 判据矩阵（上机后按这张表下结论）

| 观察 | 结论 | 下一步 |
| --- | --- | --- |
| `verdict ok` 且 `wanted >= 3` | 枚举成立：GLink + QRTR 名字服务 + modem 固件回答三者都通 | 记入 `EIGHT-STEPS` 的 ⑧；再谈 L4（QMI client / servreg） |
| `verdict ok` 但 `wanted == 0` | 有 node 0 的 NEW_SERVER，但没有一个是这五个号 | 可能是 crash-dump/低功耗镜像，先看 `qrtr: service` 列表里是什么 |
| `verdict no`、`services > 0`、`node0 == 0` | 有回复但全来自别的节点 | 检查 SMP2P host 号与 GLINK 队列归属（§11/§12 的 host0=0↔host1=1） |
| `verdict no`、`services == 0` | 名字服务没回 | 按上面日志顺序定位：没 `channel up` → 通道没开；有 `not fresh` → 队列不是新 epoch；有 `modem not ready` → SMP2P 没就绪 |
| `malformed > 0` | 线格式不符 | 32 B 头偏移或大小端错，先跑宿主测试 `test-k60-modem-qrtr.c` 复核 codec |

## 8. 边界（本篇不改的事）

- 不发 QMI 请求：`verdict` 只依赖 modem 主动广播的 NEW_SERVER，不建立 client、不发 CTL。
- 不注册/注销 lookup：只发一次 NEW_LOOKUP，收满 64 条或 500 次 poll 即停。
- 不写 NV/EFS、不读 `modemst1`/`modemst2`/`fsg`/`fsc`、不碰 IPA（`docs/research/cellular/07-QRTR-ENUMERATION.md` §7）。
- 不改 `K60ModemQrtr.c` / `K60ModemLink.c`：本轮只产出文档，镜像与分支保持已推送的 `227bad8` 一致。
- 不自行 boot：上机由 Lead 在用户同意后执行。

## 9. 复现与出处

| 内容 | 命令 / 位置 |
| --- | --- |
| Android 侧服务表 | `adb -s <serial> shell 'su -c "cat /data/vendor/qrtr/qrtr-lookup.txt"'` |
| 原表在本仓库的引用 | `docs/research/cellular/01-ANDROID-INVENTORY.md:409-452` |
| 内核 side 日志格式 | `drivers/PongCellular/K60ModemLink.c:82`、`:104`、`:254`、`:262` |
| wanted 集合与 verdict | `drivers/PongCellular/K60ModemQrtr.c:102`、`:173` |
| 线格式与判据设计 | `docs/research/cellular/07-QRTR-ENUMERATION.md` §1-§5 |
| 门控取值 | `docs/engineering/BOOT-ARGS.md` 的 `pong_modem` 小节（0 静默 / 1 PAS / 2 QRTR+PAS） |
