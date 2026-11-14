# PongCellular — K60（mondrian / SM8475）基带驱动

> 状态：**L1 已编进内核**（2026-11-14，build-strict tag `cellular-l1-20261114d`，exit 0，kernel.macho `b7dadeb5…` 54,173,696 B）；**L2 已落地待构建**（PAS 握手 + `pong_modem` 门控调用点，见 §0 与 `docs/research/cellular/06-MODEM-PAS.md`）。
> L1 版内核没有调用点，启动时不会打印任何 `K60MODEM` 日志；L2 版同样默认静默——只有 `pong_modem=1` 才会探测，且没有载体时在 `carrier absent` 处停下。
> 产物核验：`conffiles: listed … bsd/dev/pong_modem_image.c …` 出现，且 `strings -a kernel.macho | grep -c 'modem.b'` = 27（30 段减去 b14/b21/b30 三个纯 bss 行）。
> 取证：`docs/research/cellular/01-ANDROID-INVENTORY.md`、`02-DT-TRUTH.md`、`03-SCOPE.md`、`04-DT-NODES.md`、`05-MODEM-IMAGE.md`。
> 仓库铁则 ★3 的 `docs/K60-CELLULAR-CHECKLIST.md` 尚未建立；本轮 L1 能开工，是因为 Lead 的任务书直接点名要它，
> 且交付物**不含任何对硬件的写操作**（只做内存搬运与纯算术校验），可在宿主上完整验证。

## 0. 当前代码（6 个文件）

| 文件 | 作用 |
|---|---|
| `K60ModemImage.h` | `K60ModemSegment` / `K60ModemPlan` / `K60ModemRead` 与两个入口函数 |
| `K60ModemImage.c` | `k60_modem_plan()` 校验段表、`k60_modem_copy()` 按字节搬运并逐段清 bss |
| `pong_modem_table.h` | **生成物**（`scripts/gen-modem-table.py`），30 行段表 + `K60_MODEM_BASE/WINDOW/SEGMENTS` |
| `K60ModemPas.h` | SMC 编码器（`K60M_SCM_*`）、`K60_PAS_MODEM 4u`、carrier 16 B 签名 `k60_modem_carrier_ok()` |
| `K60ModemPas.c` | `smc #0` 内联汇编 + 四个 PAS 调用（auth_and_reset / init_image / mem_setup / shutdown），失败行 `K60MODEM scm cmd=… rc=… x0=… x1=…` |
| `K60ModemBoot.c` | `k60_modem_bring_up()` 五步判决日志 + `k60_modem_probe_from_handoff()`（`pong_modem=1` 门控，默认 0 静默） |

进内核的路径：`patches/xnu/0620-k60-modem-image.patch`（L1 三文件）+ `patches/xnu/0621-k60-modem-pas.patch`（L2 三文件 + `kern_exec.c` Data 挂载后调用点）
+ `patches/xnu/series` + `scripts/append-conffiles.py` 的 `bsd/dev/pong_modem_image.c` / `pong_modem_pas.c` / `pong_modem_boot.c` 三条目。

宿主验证：

```bash
python3 scripts/tests/test-k60-modem-image.py
mkdir -p /mnt/e/k60-work/artifacts/tests
gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular \
    -o /mnt/e/k60-work/artifacts/tests/t-modem \
    scripts/tests/test-k60-modem-loader.c drivers/PongCellular/K60ModemImage.c && /mnt/e/k60-work/artifacts/tests/t-modem
```

## 1. 这个目录将来装什么

只装 **L1 + L2** 两个层次（见 `03-SCOPE.md` §0）：

| 层 | 组件 | 复用来源 | 状态 |
|---|---|---|---|
| L1 | 镜像段表与搬运（`modem.mdt` → `mpss_region`） | `drivers/PongPower/K60AdspImage.c` 的第二实例 | **已落地**（`K60ModemImage.c`） |
| L1 | modem PAS 握手（`MEM_SETUP` / `INIT_IMAGE` / `AUTH_AND_RESET`，peripheral=4） | `drivers/PongPower/K60AdspPas.c` | **已落地**（`K60ModemPas.c` + `K60ModemBoot.c`，`pong_modem` 门控） |
| L1 | MSS 上电时序（PM8350C S6/S4 + AOSS qmp + IPCC ready） | `drivers/PongPower/` RPMh 投票代码 | 未开始 |
| L2 | GLINK 多通道化（承载 `IPCRTR`） | `drivers/PongPower/QcomGlink.c`（当前 `MAX_CHANNELS=1`） | 未开始 |
| L2 | QRTR 协议族 + 名字服务 + `servreg` 查询 | 无（照 Linux `net/qrtr/` 协议定义自研） | 未开始 |

**明确不装**：IPA 数据面、QMAP、EFS/NV 服务、mbn 选择、IMS/VoLTE（`03-SCOPE.md` §4）。

## 2. 关键常量（已取证，勿凭记忆改）

| 常量 | 值 | 出处 |
|---|---|---|
| `mpss_region` 基址 / 大小 | `0x8bc00000` / `0x13200000`（306 MiB） | 活 FDT `/reserved-memory/mpss_region@8bc00000/reg` |
| MSS MMIO 窗口 | `0x04080000` + `0x10000` | 活 FDT `/soc/remoteproc-mss@04080000/reg` |
| MSS compatible | `"qcom,cape-modem-pas"` | 同上 `/compatible` |
| `modem.mdt` 类型 | ELF32 LE，`e_machine=0xA4`（QDSP6），`e_phnum=32`（30 个 PT_LOAD） | `od -An -tx1 -N 52` |
| `modem.mdt` 入口 | `0x8bc00000`（= carveout 基址） | 同上 `e_entry` |
| 镜像足迹 / 余量 | 320,073,728 B（`0x1313F000`）/ 790,528 B（`0x000C1000`） | `docs/research/cellular/05-MODEM-IMAGE.md` §3 |
| 纯 bss 段（无文件） | `b14` 4,096 B、`b21` 163,696,640 B、`b30` 15,851,520 B | 同上 §4 |
| **PAS id** | **4**（不是 1，也不是 IPA 的 15） | `make-pong-adt-ipados18.py:320` + `hakios.mpss.c:1050`；活 DT 无此属性，见 05 §5 |
| GLINK 通道名 | `"IPCRTR"` | DT `glink-edge/qcom,modem_qrtr/qcom,glink-channels` |
| GLINK intents | `(0x800,5)`、`(0x2000,3)`、`(0x4400,2)` | DT 同节点 `qcom,intents` |
| GLINK remote-pid | `1`（AP = 0） | DT `glink-edge/qcom,remote-pid` |
| CX 供电轨 | PM8350C **S6**（phandle `0x1e`） | DT `cx-supply` |
| MX 供电轨 | PM8350C **S4**（phandle `0x9c`，`msslvl`） | DT `mx-supply` |
| IPCC 信号 | client 0：fatal=0, handover=1, ready=2, stop-ack=3, shutdown-ack=7 | DT `interrupts-extended` |
| modem root PD | `soc=msm, domain=modem, subdomain=root_pd, qmi_instance_id=180` | `/vendor/firmware_mnt/image/modemr.jsn` |
| IPA（不碰） | `qcom,ipa@3e00000`，`pas-ids=<0x0f>`，IPAv4.5 | `dts/mondrian.dts:295-334` |

## 3. 禁止事项（双系统铁则）

1. **永不 `fastboot flash`** 任何分区 —— boot 分区归 Android，只允许 `fastboot boot`。
2. **L1/L2 阶段只读** `modemst1`/`modemst2`/`fsg`/`fsc`，不写。
3. **加载 modem 前先查它是否已在运行** —— 从 Android 热重启进 XNU 时，modem 可能仍活着；
   直接 `PAS_AUTH_AND_RESET` 会打断一个正在运行的 modem（`03-SCOPE.md` §5）。
4. 不在本目录写 IPA 代码（`03-SCOPE.md` §4.1：全有或全无）。
5. **不自行 boot**：镜像与脚本交给 Lead，由 Lead 在用户明确同意后执行 `fastboot boot`。

## 4. 开工前必须存在的前置件

- [ ] `docs/K60-CELLULAR-CHECKLIST.md`（铁则 ★3）—— 仍未建立，L1 是 Lead 任务书点名的例外
- [x] `dts/mondrian.dts` 补上 `mpss_region` / `remoteproc-mss` / modem `glink-edge` / `qcom,ipa`（d5a9939，12 个节点）
- [x] L1 段表已实测并与 DT carveout 逐字节吻合（`05-MODEM-IMAGE.md` §1）
- [x] `03-SCOPE.md` §3.1 的未解项已澄清：`qrtr-lookup` 的表格写在
      `/data/vendor/qrtr/qrtr-lookup.txt`，modem（node 0）侧 36 个 QMI 服务在应答（`01` §5.4.1）

第 1 条仍未满足，但 L1 的交付物是「纯宿主可验证的搬运器」，不含任何硬件写操作，因此不阻塞。
L2 的代码路径**默认完全静默**（`pong_modem` 缺省即不映射不打印不发 SMC），所以“真的发 SCM”
只发生在 Lead 显式带 `pong_modem=1` 上机的那一刻；CHECKLIST 必须在那之前补齐，且首次上机
首选预期结果就是 `carrier absent`（见 `06-MODEM-PAS.md` §5）。
