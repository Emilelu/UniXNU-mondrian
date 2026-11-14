# PongCellular — K60（mondrian / SM8475）基带驱动，第一阶段

> 状态：**仅占位目录**。本目录当前没有任何可编译源码，只有这份 README 与范围声明。
> 取证结论见 `docs/research/cellular/01-ANDROID-INVENTORY.md`、`02-DT-TRUTH.md`、`03-SCOPE.md`。
> 仓库铁则 ★3：**在 `docs/K60-CELLULAR-CHECKLIST.md` 存在并逐条走完之前，不写本目录的硬件代码。**

## 1. 这个目录将来装什么

只装 **L1 + L2** 两个层次（见 `03-SCOPE.md` §0）：

| 层 | 组件 | 复用来源 | 状态 |
|---|---|---|---|
| L1 | modem PAS 加载器（`modem.mdt` → `mpss_region`） | `drivers/PongPower/K60AdspPas.c` + `K60AdspImage.c` 的第二实例 | 未开始 |
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
| GLINK 通道名 | `"IPCRTR"` | DT `glink-edge/qcom,modem_qrtr/qcom,glink-channels` |
| GLINK intents | `(0x800,5)`、`(0x2000,3)`、`(0x4400,2)` | DT 同节点 `qcom,intents` |
| GLINK remote-pid | `1`（AP = 0） | DT `glink-edge/qcom,remote-pid` |
| CX 供电轨 | PM8350C **S6**（phandle `0x1e`） | DT `cx-supply` |
| MX 供电轨 | PM8350C **S4**（phandle `0x9c`，`msslvl`） | DT `mx-supply` |
| IPCC 信号 | client 0：fatal=0, handover=1, ready=2, stop-ack=3, shutdown-ack=7 | DT `interrupts-extended` |
| modem root PD | `soc=msm, domain=modem, subdomain=root_pd, qmi_instance_id=180` | `/vendor/firmware_mnt/image/modemr.jsn` |

## 3. 禁止事项（双系统铁则）

1. **永不 `fastboot flash`** 任何分区 —— boot 分区归 Android，只允许 `fastboot boot`。
2. **L1/L2 阶段只读** `modemst1`/`modemst2`/`fsg`/`fsc`，不写。
3. **加载 modem 前先查它是否已在运行** —— 从 Android 热重启进 XNU 时，modem 可能仍活着；
   直接 `PAS_AUTH_AND_RESET` 会打断一个正在运行的 modem（`03-SCOPE.md` §5）。
4. 不在本目录写 IPA 代码（`03-SCOPE.md` §4.1：全有或全无）。

## 4. 开工前必须存在的前置件

- [ ] `docs/K60-CELLULAR-CHECKLIST.md`（铁则 ★3）
- [ ] `dts/mondrian.dts` 补上 `mpss_region` / `remoteproc-mss` / modem `glink-edge`（`02-DT-TRUTH.md` §9）
- [x] `03-SCOPE.md` §3.1 的未解项已澄清：`qrtr-lookup` 的表格写在
      `/data/vendor/qrtr/qrtr-lookup.txt`，modem（node 0）侧 36 个 QMI 服务在应答（`01` §5.4.1）

三条都没满足 → **本目录保持空壳**。
