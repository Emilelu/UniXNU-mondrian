# K60 cellular 补丁系列

> 状态：**空系列**。`series` 文件目前为空（只有注释），因为 cellular 的第一行代码还没写。
> 本文件与 `series` 的存在是为了让"cellular 这块地"在仓库里有位置，
> 避免以后有人在 `patches/` 里另起一套命名。
> 取证与范围判定见 `docs/research/cellular/01-ANDROID-INVENTORY.md`、`02-DT-TRUTH.md`、`03-SCOPE.md`。

## 为什么现在没有补丁

`docs/research/cellular/03-SCOPE.md` §8 给出的顺序是：

1. 先澄清 Android 侧 `qrtr-lookup` 为什么列不出服务（L2 的验收判据依赖它）
2. 再把 DT 节点补进 `dts/mondrian.dts`（只加节点，不启驱动）
3. 然后才多通道化 GLINK
4. 然后才 PAS 加载 modem
5. 最后裸 QRTR 报文验证枚举

**第 2 步之前不应该出现任何 `drivers/PongCellular/` 的可编译代码**，
所以本目录在那一轮之前保持空。

## 将来的补丁形状（预留给下一步）

参照 `patches/wifi/` 的组织方式，预期会是：

| # | 文件（预期命名） | 作用 |
|---|---|---|
| 0001 | `0001-dts-mondrian-cellular-nodes.patch` | `dts/mondrian.dts` 加 `mpss_region`/`remoteproc-mss`/modem `glink-edge`/`qcom,ipa` 节点（字节抄自活 FDT） |
| 0002 | `0002-drivers-PongCellular-pas.patch` | `drivers/PongCellular/` 的 modem PAS 加载器（照 `K60AdspPas.c` 第二实例） |
| 0003 | `0003-drivers-PongPower-glink-multichannel.patch` | `QcomGlink.c` 打破 `QCOM_GLINK_MAX_CHANNELS=1`，加 `IPCRTR` 通道 |
| 0004 | `0004-drivers-PongCellular-qrtr.patch` | QRTR 报文 + `servreg` 查询（L2 完成） |

**以上全是预期，未生成。** 生成前必须先过 `docs/engineering/EIGHT-STEP-SPEC.md` 的 ⑦ 核验门。

## 禁止事项

同 `drivers/PongCellular/README.md` §3：永不 `fastboot flash`；只读 `modemst`；
加载前检查 modem 是否已在运行；不碰 IPA。
