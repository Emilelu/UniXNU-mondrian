# K60 cellular 补丁系列

> 状态：**本目录仍不含可生效的补丁**（`series` 只有注释）。这是刻意的：真正进内核的补丁挂在 `patches/xnu/series` 下，
> 由构建驱动统一应用；`patches/cellular/` 只是这块地的命名占位与规则说明。
> 本文件与 `series` 的存在是为了让"cellular 这块地"在仓库里有位置，
> 避免以后有人在 `patches/` 里另起一套命名。
> 取证与范围判定见 `docs/research/cellular/01-ANDROID-INVENTORY.md`、`02-DT-TRUTH.md`、`03-SCOPE.md`、`05-MODEM-IMAGE.md`。
>
> **L1 的补丁实际落点**：`patches/xnu/0620-k60-modem-image.patch`（三个 new file：`bsd/dev/pong_modem_image.c`、
> `bsd/dev/pong_modem_image.h`、`bsd/dev/pong_modem_table.h`），已追加进 `patches/xnu/series`，
> 并在 `scripts/append-conffiles.py` 里注册了 `bsd/dev/pong_modem_image.c`。
> **L2 的补丁实际落点**：`patches/xnu/0621-k60-modem-pas.patch`（`bsd/dev/pong_modem_pas.{c,h}` +
> `bsd/dev/pong_modem_boot.c` + `kern_exec.c` 调用点），同样挂 `patches/xnu/series`；
> `scripts/append-conffiles.py` 注册 `bsd/dev/pong_modem_pas.c` 与 `bsd/dev/pong_modem_boot.c`。
> **L3 的补丁实际落点**：`patches/xnu/0622-k60-modem-qrtr.patch`（`bsd/dev/pong_modem_qrtr.{c,h}` +
> `bsd/dev/qcom_glink.{c,h}` 的副本 + `bsd/dev/pong_modem_link.c`），同样挂 `patches/xnu/series`；
> `scripts/append-conffiles.py` 注册 `pong_modem_qrtr.c`、`pong_modem_link.c`、`qcom_glink.c`。

## 为什么现在没有补丁

`docs/research/cellular/03-SCOPE.md` §8 给出的顺序是：

1. ~~先澄清 Android 侧 `qrtr-lookup` 为什么列不出服务~~ —— **已完成（2026-11-14）**：
   结果写在 `/data/vendor/qrtr/qrtr-lookup.txt`，modem（node 0）侧 36 个 QMI 服务在应答
   （`docs/research/cellular/01-ANDROID-INVENTORY.md` §5.4.1）。L2 验收判据据此定稿。
2. 再把 DT 节点补进 `dts/mondrian.dts`（只加节点，不启驱动）
3. 然后才多通道化 GLINK
4. 然后才 PAS 加载 modem
5. 最后裸 QRTR 报文验证枚举

**第 2 步之前不应该出现任何 `drivers/PongCellular/` 的可编译代码** —— 这条已经越过：第 2 步（DT 节点）在 d5a9939 完成，
第 4 步（PAS 加载）的**搬运半截**也已完成（`K60ModemImage.c`，只有 plan/copy，没有 SCM 调用）。
越过的理由与边界写在 `drivers/PongCellular/README.md` 顶部：交付物不含任何硬件写操作，纯宿主可验证。

## 将来的补丁形状（预留给下一步）

参照 `patches/wifi/` 的组织方式，预期会是：

| # | 文件（预期命名） | 作用 |
|---|---|---|
| 0001 | `0001-dts-mondrian-cellular-nodes.patch` | `dts/mondrian.dts` 加 `mpss_region`/`remoteproc-mss`/modem `glink-edge`/`qcom,ipa` 节点（字节抄自活 FDT） |
| ~~0002a~~ | **已落地为 `patches/xnu/0620-k60-modem-image.patch`** | modem 镜像段表 + 搬运器（`K60ModemImage.c` / `pong_modem_table.h`） |
| ~~0002b~~ | **已落地为 `patches/xnu/0621-k60-modem-pas.patch`** | PAS 握手 + `pong_modem` 门控调用点（`K60ModemPas.{c,h}` / `K60ModemBoot.c` + `kern_exec.c` 锚 `native_owner_data_stage = 3;`） |
| ~~0003~~ | **不采用** | `QCOM_GLINK_MAX_CHANNELS=1` 是每实例上限，modem 用自己的 `QcomGlink` 实例即可，无需改 `PongPower` 的实现 |
| ~~0004~~ | **部分落地为 `patches/xnu/0622-k60-modem-qrtr.patch`** | QRTR 只读枚举：HELLO + `NEW_LOOKUP (0x0a)` + `NEW_SERVER` 表（`K60ModemQrtr.{c,h}` / `K60ModemLink.c` + `QcomGlink.{c,h}` 的 `bsd/dev` 副本）；QMI client 分配 / `servreg` 仍属 L4 |

除 0001（DT 节点，d5a9939）、0002a（镜像搬运，0620）、0002b（PAS 握手，0621）、0004 的只读枚举部分（0622）外，**其余仍是预期，未生成**。
生成前必须先过 `docs/engineering/EIGHT-STEP-SPEC.md` 的 ⑦ 核验门。

## 禁止事项

同 `drivers/PongCellular/README.md` §3：永不 `fastboot flash`；只读 `modemst`；
加载前检查 modem 是否已在运行；不碰 IPA。
