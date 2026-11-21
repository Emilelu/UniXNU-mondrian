# W2 完整 4 KiB 超级块判据

2026-11-20 22:30。本文把「W2 只判 16 字节头」扩成一条可执行的完整判据：
拿到 4096 字节后，哪些偏移必须等于什么，哪些字段只能标 `unknown`，以及
什么情况是 `PENDING` 而不是 `FAIL`。2026-11-21 又给 27 侧 console 加了同一
窗口的两段全块 SHA-256：offset 0 的 4096 字节，以及 offset 512 的 3584 字节。

这不是待办清单。没有 4 KiB 采集时判 `PENDING`；有 4096 字节但不满足下表时判
`FAIL`。两者都不允许用「先算通过」绕过。

## 1. 范围与术语

- **W2 头判据**：`scripts/judge-cellular-flight.py` 里的 `EFS_HEADS`，只比较
  offset 0 的 16 字节。它是必要条件，不是充分条件，现在只作兼容样本保留。
- **完整超级块**：每个 storage 的 **offset 0 起 4096 字节**，不是整个分区。
  4096 字节之外的内容不属于本判据。
- **27 console 全块摘要**：同一窗口的 SHA-256，两段必须同时出现：
  `offset=0 bytes=4096` 对应完整块，`offset=512 bytes=3584` 对应
  `0x200..0xfff` 数据段。它是飞行日志的压缩证据，不是离线字段级判据的替代。
- **storage**：RMTFS 的 `/boot/modem_fs1` … `/boot/fsc`，编号 1..4。
  它不是控制器 LUN；W1 仍 `PENDING`，本文的对应关系只是内容参照。
- **独立参照**：2026-11-20 在 Android 侧只读取得的
  `E:/k60-work/evidence/efs-ground-truth-20261120/sdf3.bin` … `sdf6.bin`。
  原始镜像**不进入仓库**（可能含 modem 身份/校准数据）；仓库只保存下表的
  常量与哈希。

## 2. storage 与参照文件

| storage | Android by-name | 参照文件 | 4096 字节 sha256 |
|---|---|---|---|
| 1 | `modemst1` | `sdf3.bin` | `94c2aa725f4e8c5d3de317e8cd39f7efc1588866e7d2854011d10e4656a1a6bb` |
| 2 | `modemst2` | `sdf4.bin` | `8610958511c22e7c44736363ac2b9c2d8e87bd16d78540fa2d4e97be1c489726` |
| 3 | `fsg` | `sdf5.bin` | `e9a62f2a22e469b8008da4dc2733148ae4abcf887c9e1277a7646123fdbc31b4` |
| 4 | `fsc` | `sdf6.bin` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7` |

四个文件都是 4096 字节。`fsc` 的 4096 字节全零；**storage 4 全零是正确结果**，
不是「没有数据」。对 storage 1/2/3，全零是错误结果。

## 3. 字段表

### 3.1 offset 0x00..0x27：十个 LE32

所有值都是小端 32 位；写成 8 位十六进制便于逐字节比对。

| offset | width | storage 1 | storage 2 | storage 3 | storage 4 | 语义 |
|---|---|---|---|---|---|---|
| 0x00 | u32 | `00000010` | `00000011` | `00000014` | `00000000` | unknown |
| 0x04 | u32 | `00000003` | `00000003` | `00000003` | `00000000` | unknown |
| 0x08 | u32 | `000001d8` | `000001d8` | `000001d8` | `00000000` | unknown |
| 0x0c | u32 | `c4a9fa20` | `80600200` | `00000000` | `00000000` | unknown |
| 0x10 | u32 | `0027fe00` | `0027fe00` | `0027fe00` | `00000000` | unknown |
| 0x14 | u32 | `0027fe00` | `0027fe00` | `0027fe00` | `00000000` | unknown |
| 0x18 | u32 | `c4d1f820` | `80880000` | `0027fe00` | `00000000` | unknown |
| 0x1c | u32 | `00000000` | `00000000` | `00000000` | `00000000` | unknown |
| 0x20 | u32 | `c4d1f820` | `80880000` | `0027fe00` | `00000000` | unknown |
| 0x24 | u32 | `00000000` | `00000000` | `00000000` | `00000000` | unknown |

`unknown` 不是说这些字节不重要；它们必须逐字节等于上表，否则判 `FAIL`。
`unknown` 只是说：当前没有格式定义能把它们命名成「长度/校验/版本」之类的字段，
所以不能根据名字推断行为。

### 3.2 offset 0x28..0x3f：label、一个字节、四个 LE32

| offset | width | storage 1 | storage 2 | storage 3 | storage 4 | 语义 |
|---|---|---|---|---|---|---|
| 0x28 | 7 bytes | `IMGEFS1` | `IMGEFS2` | `IMGEFSG` | 7 个 `00` | ASCII label（已知） |
| 0x2f | u8 | `18` | `17` | `12` | `00` | unknown |
| 0x30 | u32 | `ee0000cd` | `e40000cd` | `10000000` | `00000000` | unknown |
| 0x34 | u32 | `a1f362e5` | `a1f345d6` | `49917432` | `00000000` | unknown |
| 0x38 | u32 | `00000001` | `00000001` | `00000000` | `00000000` | unknown |
| 0x3c | u32 | `00000102` | `00000102` | `00000101` | `00000000` | unknown |

0x2f **不是 label 长度**：label 只有 7 字节，而这里是 `0x18`/`0x17`/`0x12`。
在找到 QEFS 定义前，它只能作为 opaque 期望字节，不能写成「label 长度」或
「字符串长度」。

### 3.3 offset 0x40..0xfff：零填充与不透明数据块

| offset | width | 期望 | 语义 |
|---|---|---|---|
| 0x40 | 448 bytes | 全零 | zero padding（已知） |
| 0x200 | 3584 bytes | 按 storage 的 data sha256 | opaque QEFS 块（结构 unknown） |

| storage | 0x200..0xfff data sha256 |
|---|---|
| 1 | `3cc3383e26ddccc6c173df925379e3692c817ee6a8c55ce60506eab2b33210c6` |
| 2 | `66df4116cab50b05d3e9a3122f19b28f9654cd3ed63d9cffc393ff37fff59183` |
| 3 | `32efa564d9ccc53fdc201920cb30b87f7aed2bcfc79e02d643ef919f2e6e4f0c` |
| 4 | `6cf1b57d59e7111bc218dfb01dda93ac0f776715599a1c69f89035bd20c16a10` |

0x200 起看起来是加密/压缩的 QEFS 块。当前没有块内字段定义，因此**只能整段
比较 sha256**；不要按偏移猜某个 4 字节是长度或校验和。

## 4. 判决规则

判官是 `scripts/check-efs-full.py`：

```sh
python3 scripts/check-efs-full.py --storage 1 --file /path/to/sdf3.bin
python3 scripts/check-efs-full.py --storage 1 --file /path/to/sdf3.bin --explain
```

### PASS

以下全部成立：

1. 文件正好 4096 字节；
2. 0x00..0x27 的十个 LE32 全部等于上表；
3. 0x28..0x2e 的 7 字节 label 等于上表；
4. 0x2f 等于上表；
5. 0x30..0x3f 的四个 LE32 全部等于上表；
6. 0x40..0x1ff 全部为零；
7. 0x200..0xfff 的 data sha256 等于上表；
8. 完整 4096 字节的 sha256 等于上表。

第 8 条是最终封口；第 7 条让「头对、数据错」有单独的诊断，不会只报一个
full sha 不匹配。

### FAIL

任一条成立：

- 文件长于 4096 字节（读多了，不是「完整一块」）；
- 上述任一字段不等于期望值；
- padding 有任何非零字节；
- data sha256 或 full sha256 不等于期望值。

**头 16 字节匹配但完整块不匹配，仍是 FAIL**，不能降级成 `PENDING`。这正是
W2 头判据单独使用时最容易漏掉的情况。

### PENDING

- 文件不存在；或
- 文件短于 4096 字节。

短读不是「块内容错」，是采集不完整；所以 `PENDING`，退出码 2，不阻塞线内
preflight。只有拿到完整 4096 字节后才进入 PASS/FAIL。

### storage 4 的特殊形状

storage 4 的 4096 字节全零：

- 全零且长度正确 ⇒ `PASS`；
- 任意非零字节 ⇒ `FAIL`；
- 不能因为「全零看起来像没有数据」就判 `PENDING` 或跳过。

## 5. unknown 字段怎么定

当前能命名语义的只有：

- 0x28..0x2e：ASCII label；
- 0x40..0x1ff：zero padding；
- 0x200..0xfff：opaque QEFS 块（只能整段哈希）。

其余字段（0x00..0x27、0x2f、0x30..0x3f）都是 **unknown**。定语义只有两条
合法路径：

1. 找到产生该超级块的 QEFS/EFS 格式定义或源码，能指到具体结构体字段；
2. 在**同一 modem 状态**下再做一次独立只读采集，逐字节对比，确认哪些字节
   稳定、哪些会变。

在做到其中一条之前：

- 不把 0x2f 叫 label 长度；
- 不把 0x00/0x04/0x08 叫版本号、块大小或校验；
- 不写「根据某字段判断 EFS 是否有效」的代码；
- 判官只比较常量，不解释常量。

如果未来采集与上表不同，先停：可能是 EFS 状态真的变了，也可能是采到了不同
storage/offset。不要为了变绿自动更新上表；要按 W1 的「真实矛盾必须停查」
处理。

## 6. 采集方式

采集步骤、权限边界和落盘清单在
[`22-W1-READONLY-CAPTURE.md`](22-W1-READONLY-CAPTURE.md)。本文只强调三点：

- 只读：`adb exec-out dd if=/dev/block/by-name/<name> bs=4096 count=1` 这类
  命令只读块设备；不写 `/dev/block`、不 mount rw、不 fastboot。
- 每个 storage 单独一个文件，文件名带 storage 和采集时间；不要把四个块拼在
  一起。
- 原始文件留在 `E:/k60-work/evidence/` 下，不进仓库；仓库只进哈希、字段表
  和测试用的合成零块。

没有 adb root 或没有可读块设备时，W2 完整块保持 `PENDING`；这不是反证，
也不能用 16 字节头代替。

### 6.1 采集后本地自动核

采集完把本地文件交给组合判官；它不调用 adb，只读传入的文件：

```sh
CAP=/mnt/e/k60-work/evidence/w1-lun-YYYYMMDD-HHMMSS
python3 scripts/check-capture-bundle.py \
  --leg-a "$CAP/device-link.txt" \
  --leg-b "$CAP/unit-desc-L5.bin" \
  --readme "$CAP/README.txt" \
  --proc "$CAP/proc-scsi-scsi.txt" \
  --console "$K60_CONSOLE" \
  --efs-block "1=$CAP/sdf3.bin" \
  --efs-block "2=$CAP/sdf4.bin" \
  --efs-block "3=$CAP/sdf5.bin" \
  --efs-block "4=$CAP/sdf6.bin"
```

- 没有 `--console` 或 `--efs-block` 时，W2 头/完整块显示 `SKIP`，不会伪造
  `PASS`；
- 没有 W1 的 `device-link.txt`、`unit-desc-L5.bin` 或 `README.txt` 时，W1
  显示 `PENDING`（退出码 2），不是 `PASS`；
- 任一份已给证据矛盾或畸形，显示 `FAIL`（退出码 1）；
- 四份完整块只给了一部分时，`W2 FULL` 显示 `PENDING` 并列出缺少的 storage；
- `scripts/w1-capture-plan.sh` 末尾会打印同一组合命令，且只把实际存在的
  本地文件加进去。

### 6.2 27 侧 console 全块摘要

27 的 rmtfs 路径不再只打印 16 字节头。它每服务一个非空读，就打印两行摘要：

```text
K60MODEM qrtr: rmtfs block storage=1 direction=0 offset=0 bytes=4096 sha256=<64hex>
K60MODEM qrtr: rmtfs block storage=1 direction=0 offset=512 bytes=3584 sha256=<64hex>
```

合法组合只有两组：

| offset | bytes | 覆盖范围 | 对照 |
|---|---|---|---|
| `0` | `4096` | 完整 4096 B | 第 2 节的 full sha256 |
| `512` | `3584` | `0x200..0xfff` | `check-efs-full.py` 的 data sha256 |

判官 `scripts/judge-cellular-flight.py` 的规则：

- 非严格模式：出现任一行 block，就必须两行齐全；缺一行是 `FAIL`，不是 `PENDING`。
  一行 block 都没有时，保持旧的 16 字节头行为（block 项 `SKIP`）。
- 严格模式 `--require-efs-bytes`：**每个被 rmtfs 服务过的 storage** 都必须两行齐全；
  即使该 storage 一行 block 都没出现，也算缺摘要并 `FAIL`，不能只判「方便的那一块」。
- offset/bytes 不是上表两组之一、direction 非 0、storage 不在 1..4、sha256 不是 64 位
  十六进制，都是 `FAIL`。
- 严格模式不再接受「头对、没有全块摘要」。但它**不**把「四个 storage 都出现」当必要
  条件，因为 modem 启动可能只读其中一部分；「四个 storage 都齐全」仍由离线
  `check-efs-full.py` 的四份 4096 B 文件判定。

为什么是摘要而不是原始字节：console 每条日志都有固定开销，4096 B 原始字节会膨胀成
8192 个十六进制字符，既难读也容易截断。SHA-256 让「整段窗口是否逐字节等于参照」变成
一次比较；字段级定位仍由离线的 `check-efs-full.py` 完成。两者不是互相替代：console
摘要证明**27 读回的窗口**与参照一致，离线判据证明**参照本身的每个字段**符合表。

## 7. 与 W2 头判据、F3 的关系

顺序是硬的：

```text
W1（哪个盘） -> W2 头 16 字节 -> W2 console 全块摘要 -> W2 离线 4 KiB -> W3/W4（modem 是否继续） -> PAS4/RF
```

- W2 头 PASS、console 摘要或离线完整块 FAIL：先查读取长度/offset/window 是否真的
  覆盖 4096，再查是否把不同 storage 的窗口混用；不要用「RF 没起来」解释字节错。
  头对但 `offset=512` 摘要不对，说明 16 字节之后的 3584 字节已经分叉。
- W2 头、console 摘要与离线完整块都 PASS、但 modem 不继续：进入 F3 的 W3/W4/PAS4 判据，
  不要回头改 EFS 字节。
- W1 仍 `PENDING` 时，本文的 storage→分区对应只是内容参照；不要把它写成
  控制器 LUN 证据。

## 8. 采集之后谁判谁签

这一节固定角色，避免把「脚本 PASS」误当成「可以起飞」。

### 8.1 分工

| 步骤 | 谁做 | 入口 | 产物 | 自动判？ |
|---|---|---|---|---|
| 1. 设备只读采集 | **Lead**（设备权限唯一持有者） | `scripts/w1-capture-plan.sh` 打印的命令；在 Android 侧执行 adb | CAP 下的 `device-link.txt`、`unit-desc-*.bin`、`README.txt`、可选 `sdf3..6.bin` / console | 否 |
| 2. W1 控制器 LUN | 脚本 | `scripts/check-w1-lun-evidence.py` | PASS / PENDING / FAIL | 是 |
| 3. W2 console 全块摘要 | 脚本 | `scripts/judge-cellular-flight.py` | PASS / FAIL / INVALID | 是；两段 SHA-256 覆盖 4096 B 全窗口 |
| 4. W2 离线完整 4 KiB | 脚本 | `scripts/check-efs-full.py` | PASS / PENDING / FAIL | 是；逐字段 + 两段哈希 |
| 5. 组合 | 脚本 | `scripts/check-capture-bundle.py` | 每项一行 + `OVERALL` | 是，仅限本地文件 |
| 6. provenance 与形状 | **人**（Lead 签，lane 只核对本地文件） | 看 README 的 serial/build/UTC、`xxd`、by-name 对照 | 签核备注 | 否 |
| 7. 飞行账本 / F3 | **Lead** | `IOS27-FLIGHT-BLOCKERS.toml` 与飞行账本 | open / closed | 否 |

采集脚本本身只打印计划，不执行 adb；`check-capture-bundle.py` 也不调用 adb。
所以「脚本 PASS」只证明**给定的本地文件彼此一致**，不证明文件来自哪台设备，
更不证明可以起飞。

### 8.2 三种判决怎么读

- **PASS**：已提供的 W1 腿齐全且一致，README 非空；W2 若提供也必须一致。
  如果输出里 `W2 FULL  SKIP`，只能签「W1 + 已提供的 W2 console 摘要」，不能签
  「W2 离线完整块 PASS」。
- **FAIL**：至少一项矛盾或畸形。先读该项的第一条 reason，再决定是重采还是停查；
  **不要**为了变绿修改 `check-efs-full.py` 的参照表。一个错位移的样本会报成
  `0x00 LE32 is 0x00000000, expected 0x00000010`，这不是 EFS 状态，是采集 offset
  错了。
- **PENDING**：缺文件或短读，退出码 2。它不是「块内容错」的反证，也不是允许
  猜值的许可；把缺的那一腿补上再判。
- 组合判决的优先级固定为 **FAIL > PENDING > PASS**。只要有一项 FAIL，整体就是
  FAIL；只有缺项且无矛盾才是 PENDING。

### 8.3 fsc 全零：看着像失败，实际是正确

`storage 4` 对应 Android by-name `fsc`（参照文件 `sdf6.bin`），其 4096 字节
**全零是正确形状**：`check-efs-full.py --storage 4` 应判 PASS，组合判官也应把
它算作已提供且通过。

必须人看的是「零属于哪个 storage」：

- `storage 4` 全零 → PASS，不要因为「没有数据」而改判 PENDING/FAIL；
- `storage 1/2/3` 全零 → FAIL，不能套用 fsc 的例外；
- `sdf3..sdf6` 只是内容参照，不是控制器 LUN 证据；W1 的 LUN 仍以 Leg A/B 为准。

### 8.4 合成输入的一次自证

设备窗口之前，先用不含真实 EFS 数据的合成输入跑通整条 AUTOCHECK：

```sh
python3 scripts/tests/test-capture-autocheck-e2e.py
```

它构造三个假采集，并打印三种判决：

1. **PASS**：Leg A `0:0:0:5`、Leg B `index=5 enable=1`、README 齐全，再加
   synthetic console 里的正确 16 字节头
   `1000000003000000d801000020faa9c4`，以及 `offset=0/4096` 与
   `offset=512/3584` 两段正确摘要；`OVERALL: PASS`。
2. **FAIL**：同一个 W1，加一个把 storage 1 头整体后移 512 字节的合成块；判官报
   `W2 FULL FAIL    storage=1: 0x00 LE32 is 0x00000000, expected 0x00000010`，
   `OVERALL: FAIL`。这说明「错位移」会被字段级 reason 指出来，而不是笼统报坏。
3. **PENDING**：只给 Leg A + README，故意缺 Leg B；判官报
   `Leg B: unit-desc.bin / unit-desc-*.bin is absent`，`OVERALL: PENDING`。

这个自证只使用合成头、零数据和仓库里的 synthetic console fixture；不调用 adb，
不读取真实 EFS 镜像，也不能替代设备采集。它证明的是**链路会正确区分三种判决并
指出缺项/错项**，不是 W1/W2 的硬件结论。

### 8.5 签核边界

- 采集由 Lead 做，lane 不自行 boot、不自行 adb、不把合成 fixture 当设备证据。
- 脚本自动判可以签「本地文件一致」；provenance、storage 对照、fsc 全零是否属于
  当前设备，必须由人看过后写进签核备注。
- 只有 Lead 能把 W1/W2 写进飞行账本或宣布 F3 可开始；`check-capture-bundle.py`
  不写账本，也不改 blocker 状态。
- F3 仍等三条 stage-0 blocker 关闭；W1 控制器 LUN 和完整 4 KiB 采集仍
  `PENDING`，不得为了变绿放宽。

本文只定义判据、判官和签核边界，不改驱动、不构建、不上机。W1 与完整 4 KiB
采集都还是待采集项；F3 的三条 stage-0 blocker 未关闭前没有飞行窗口。
