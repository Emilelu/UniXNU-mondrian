# 21 — 27 起飞门禁：W1 LUN 取证与 cellular 第三条 blocker 评审

- 日期：2026-11-20 18:55（20:30 追加 W1 预检与 27 UEFI 描述符自证）
- 状态：离线评审。未构建、未上机、未改共享仓；只读 Linux 内核源码、27 UEFI 源与本地文档。
- 结论一：**W1 仍是 PENDING。** `doc20 §29.3` 的 `LUN 5（sd 字母）` 是推断，不是控制器证据；
  `sdf` 字母、分区名 `modemst1`、我们自己的 `K60UFS volume ... lun=5` 都不能独立证明 LUN。
- 结论二：**不建议给 cellular 加第三条 flight blocker。** 本轮在默认参数下没有找到
  「结构检查通过、起飞即死」的 cellular 路径；真正的缺口是「27 产物里根本没有 cellular」，
  那是覆盖缺口，不是飞行致死。若要加，只能是独立的 boot-arg 政策检查，不应混进 blocker 台账。

## 1. 为什么 `lun=5` 现在不算证据

`E:/k60-work/wt-pitfall/docs/research/cellular/20-IOS27-PORT-PLAN.md:987` 的 W1 行要求
`K60UFS volume name=modemst1 lun=5 first=… last=…`；同文件 `:1000-1013` 的独立参照表把
四个分区都写成 `LUN 5（8 MiB）`。但那张表的来源是 Android 侧 `sdf3`…`sdf6` 四个分区：

- `sdf` 是 Linux 扫描到第几个磁盘时给的字母，**字母本身不携带 LUN**；
- `sdf3`…`sdf6` 同属一个 `sd` 设备，只能证明它们共享同一个 SCSI 设备，不能证明该设备的 LUN；
- `8 MiB` / `1 MiB` 是分区大小，和 LUN 编号无关；
- `K60UFS volume ... lun=5` 是我们自己的代码把「选中的 LUN」回显出来，属于自证，不是独立证据。

所以 W1 需要一次**只读**采集，把「sd 字母 → SCSI LUN → UFS Unit Descriptor」这条链闭合。
采集不需要写任何块设备，也不需要 root 之外的特权；没有 root 时只能做 Leg A/C，Leg B 留 PENDING。

## 2. W1 的可执行取证判据

### 2.1 Leg A：`/sys/block/sdf/device` 的 HCTL 末字段

命令（设备在 Android、adb 可用时）：

```sh
adb shell 'readlink -f /sys/class/block/sdf/device'
adb shell 'lsblk -o NAME,HCTL,SIZE,MODEL /dev/sdf 2>/dev/null || lsblk -o NAME,HCTL /dev/sdf'
adb shell 'cat /proc/scsi/scsi'
```

`/sys/class/block/sdf/device` 是指向 SCSI 设备的符号链接，解析后的**路径最后一段**就是
`H:C:T:L`。例：

```
/sys/devices/platform/soc/1d84000.ufshc/host0/target0:0:0/0:0:0:5
```

最后一段 `0:0:0:5` 的第四个字段 **L = 5**，这才是要读的字段。

依据（Linux 主线，本轮只读核对）：

- `drivers/ufs/core/ufshcd.c`：`ufshcd_scsi_add_wlus()` 用
  `__scsi_add_device(hba->host, 0, 0, wlun, NULL)` 加 well-known LU；随后
  `host->max_id = UFSHCD_MAX_ID`（值为 1）、`host->max_lun = UFS_MAX_LUNS`，
  再 `scsi_scan_host(hba->host)`。
- `drivers/scsi/scsi_scan.c`：`scsi_scan_host_selected(shost, SCAN_WILD_CARD, SCAN_WILD_CARD,
  SCAN_WILD_CARD, …)` 对 LUN 做全扫描；普通 LU 的 `sdev->lun` 就是扫描到的 LUN。
- `drivers/scsi/scsi_sysfs.c`：设备名由 `dev_set_name(..., "%d:%d:%d:%d", host_no, channel, id, lun)`
  拼出；所以 HCTL 的 L 字段就是 `sdev->lun`。

对普通 LU（有容量、能读写的那个）而言，SCSI LUN 与 UFS Unit Descriptor 的 `bUnitIndex` 是同一个编号。
**不要把 T 当 LUN**：UFS HBA 的 `max_id` 是 1，T 通常是 0。

补充：`scsi_sysfs.c` 没有导出 `lun` 属性，所以不要找 `/sys/.../device/lun`；该文件不存在不是采集失败。
`lsblk` 的 `HCTL` 列在部分 Android toybox 上不可用，此时以 `readlink -f` 的输出为准。

### 2.2 Leg B：UFS Unit Descriptor 的 `bUnitIndex` / `bLUEnable`

UFS Query READ DESCRIPTOR，descriptor IDN = `0x02`（Unit Descriptor），index = L，
selector = 0，length 请求 `0x40`。返回字节的含义：

| 偏移 | 字段 | 判据 |
|---|---|---|
| 0 | `bLength` | 以设备返回为准；至少覆盖到 byte 4，且与响应长度一致 |
| 1 | `bDescriptorIDN` | 必须等于 `0x02` |
| 2 | `bUnitIndex` | 必须等于 Leg A 的 L（候选为 5） |
| 3 | `bLUEnable` | `0x01` 表示该 LU 使能；`0x00` 是禁用 |
| 4 | `bBootLunID` | 只是 boot LUN 选择位（0/1/2），**不是** LU 编号，不能拿来当 LUN |

Linux 的常量也在同一位置（`include/ufs/ufs.h`）：`QUERY_DESC_IDN_UNIT = 0x2`、
`UNIT_DESC_PARAM_UNIT_INDEX = 0x2`、`UNIT_DESC_PARAM_LU_ENABLE = 0x3`、
`UNIT_DESC_PARAM_BOOT_LUN_ID = 0x4`。

**27 树自己的读取代码（比只抄常量更硬的自证）。** 本地 27 UEFI feed
`/opt/k60/trees/ios27-out/feeds/mu_basecore-8f10084c/`（git HEAD
`cfb93724a06ff86ff5ba971413368a7809ee42a5`）实际就是这样读的：

- `MdePkg/Include/IndustryStandard/Ufs.h:32`：`#pragma pack(1)`，所以结构体没有对齐填充；
- `Ufs.h:873-893`：`UFS_UNIT_DESC` 的前五个字段依次是
  `UINT8 Length; UINT8 DescType; UINT8 UnitIdx; UINT8 LunEn; UINT8 BootLunId;`，
  即 byte 0/1/2/3/4；`UnitIdx` 就是 `bUnitIndex`，`LunEn` 就是 `bLUEnable`；
- `Ufs.h:658-667`：`UfsUnitDesc = 0x02`（`UFS_DESC_IDN`，即 IDN `0x02`）；
- `UfsPassThru.c:996-1007`：`UfsRwDeviceDesc(Private, TRUE, UfsUnitDesc, Index, 0,
  &UnitDescriptor, &UnitDescriptorSize)` 真的发出 QUERY READ DESCRIPTOR；随后
  `if (UnitDescriptor.LunEn == 0x1)` 用 byte 3 判断 LU 是否使能；
- `UfsPassThruHci.c:1045-1077`：该函数填 UPIU——
  `Packet.Opcode = UtpQueryFuncOpcodeRdDesc`（`Ufs.h:472`，值为 `0x01`）、
  `Packet.DescId = DescId`、`Packet.Index = Index`、`Packet.Selector = 0`。

因此 byte 2/3 的偏移不是从文档推出来的：27 树按 packed `UFS_UNIT_DESC` 的字段偏移
读回 `UnitIdx`，并直接比较 `LunEn` 与 `0x1`。字段是 `UINT8`，不存在大小端转换；
UPIU 的 `Index` 是请求的 L，返回的 `UnitIdx` 必须与它一致。

**Linux 侧的独立消费者（pinned mainline）。** 复核的 revision 是
`torvalds/linux` `v6.12` tag 对象 `06090c9b622a7e1f797e775db4c035e0d779b76e`，
commit `adc218676eef25575469234709c2d87185ca223a`：

- `include/ufs/ufs.h:207-216` 把 `UNIT_DESC_PARAM_UNIT_INDEX` 定为 `0x2`、
  `UNIT_DESC_PARAM_LU_ENABLE` 定为 `0x3`；`ufs.h:191` 的
  `QUERY_DESC_IDN_UNIT = 0x2`，`ufs.h:439` 的
  `UPIU_QUERY_OPCODE_READ_DESC = 0x1`；
- `drivers/ufs/core/ufs-sysfs.c:888-932` 的 `ufs_sysfs_read_desc_param()` 把
  `param_offset`/`param_size` 都当 `u8` 字节参数，`param_size > 8` 直接 `-EINVAL`；
- `drivers/ufs/core/ufshcd.c:3637-3703` 的 `ufshcd_read_desc_param()` 在 `:3664`
  发 `UPIU_QUERY_OPCODE_READ_DESC`，`:3676` 校验 `param_offset >= buff_len`，
  `:3696-3697` 用 `memcpy(..., &desc_buf[param_offset], ...)` 按字节切片；
  `ufshcd.c:3817-3832` 的 `ufshcd_read_unit_desc_param()` 只是原样透传；
- byte 2 有真实策略消费者：`ufshcd.c:5130-5181` 的 `ufshcd_lu_init()` 在
  `:5168-5170` 比较 `desc_buf[UNIT_DESC_PARAM_UNIT_INDEX]` 与
  `UFS_UPIU_RPMB_WLUN`；
- byte 3 在 mainline **只有 sysfs 呈现，没有内核策略消费者**：
  `ufs-sysfs.c:1594` 的 `UFS_UNIT_DESC_PARAM(lu_enable, _LU_ENABLE, 1)` 以
  `1` 字节读取，`:916-919` 的 `case 1` 直接 `0x%02X` 打印；不能把
  “Linux 读了 bLUEnable”写成“Linux 据此门控 LUN”。

单字节访问不存在端序转换；`get_unaligned_be16/32/64` 只用于 size 2/4/8 的参数。
这与 27 树的 packed 结构互相独立地闭合了 byte 2/3 的偏移。

读取路径：

- 优先用现成的 `ufs-tool`（Western Digital 的用户态工具）或设备上已有的 UFS query 工具；
- 没有工具时看 `/dev/bsg/ufs-bsg*` 是否存在：Linux `ufs_bsg` 接受 UPIU QUERY REQUEST
  （transaction code `0x16`、query function `0x01`），但 `sg_inq`/`sg_raw` 发的是 SCSI CDB，
  **不能**替代 UPIU query；
- 若两者都没有，把 Leg B 标成 **PENDING**，不要用 VPD 或分区名补位。

判据：**Leg A 与 Leg B 必须同时成立，W1 才能从 PENDING 改为 PASS。**
只有 Leg A 成立时，状态写成「HCTL 说 L=5，Descriptor 未采」，仍然是 PENDING。
Leg A 说 5、Leg B 说 4 是真实矛盾，必须停下来查，不能二选一。

### 2.3 Leg C：`sg_inq` 的 VPD 页（身份，不是 LUN）

如果设备上有 sg3_utils：

```sh
adb shell 'sg_inq -p 0x00 /dev/sdf'   # Supported VPD pages
adb shell 'sg_inq -p 0x83 /dev/sdf'   # Device Identification
adb shell 'sg_inq -p 0xb0 /dev/sdf'   # Block Limits
```

结论要说清楚：**没有任何标准 SCSI VPD 页直接报告 UFS LUN。**

- `0x83` 是 Device Identification，给 NAA / SCSI name string 等身份信息；它能把这次采集绑定到
  同一个 LU，但名字里不保证含 LUN，不能当 LUN 判据；
- `0xb0` 是 Block Limits（最大/最优传输长度等），与 LUN 编号无关；
- `0x00` 只列出设备支持哪些页，不报告 LUN。

所以 Leg C 的用途是「身份绑定 + 记录设备能力」，不是 W1 的通过条件。没有 sg3_utils 时可以跳过，
但要在记录里写明跳过原因。

### 2.4 一次采集的验收表

| 腿 | PASS | FAIL | PENDING |
|---|---|---|---|
| A：HCTL | 末字段 L=5 | L=其它值（记录实际值，W1 的期望值就要改） | 拿不到 `readlink` 输出 |
| B：Unit Descriptor | index=5，`bUnitIndex=5`，`bLUEnable=1` | `bUnitIndex`≠5、`bLUEnable=0`、IDN≠0x02 | 没有 UPIU query 工具/设备 |
| C：VPD 0x83 | 已记录，且与同一个 `/dev/sdf` 对应 | 读失败只记为证据缺口，不单独判 W1 失败 | 没有 sg3_utils |

**W1 PASS = A 与 B 同时 PASS，且 C 已记录（或明确跳过）。**
A 单独成立只能写成「HCTL=5，Descriptor PENDING」，不能写成「W1 PASS」。

**最小定案集（只读）：**

- Leg A：`/sys/class/block/<sdX>/device` 解析后的**路径最后一段** `H:C:T:L`，读**第四个字段 L**；
  不要读 `T`，也不要找不存在的 `/sys/.../device/lun`。
- Leg B：UFS Query READ DESCRIPTOR，IDN `0x02`，读 **byte 2 `bUnitIndex`** 与 **byte 3 `bLUEnable`**；
  byte 4 是 `bBootLunID`，不是 LU 编号。
- `sg_inq`：**没有任何标准 VPD 页或其中某个字节直接报告 UFS LUN。** `-p 0x83` 的 NAA/SCSI name
  只能把采集绑定到同一个 LU，`-p 0xb0` 只是块限制；两者都不能替代 Leg A/B，不存在「读 VPD 第 N 字节
  就能定 LUN」的捷径。

### 2.5 采集落盘形状

一次采集放在一个新目录，例如 `E:/k60-work/evidence/w1-lun-20261120-1900/`：

```
lsblk.txt
device-link.txt
proc-scsi-scsi.txt
vpd-00.bin
vpd-83.bin
vpd-b0.bin
unit-desc-<L>.bin   # L = Leg A 的末字段；byte2 才是权威
README.txt          # adb serial、Android build、命令、工具版本、sha256
```

`README.txt` 必须写：设备序列号、Android build fingerprint、每条命令的原始输出、
是否 root、`ufs-tool`/sg3_utils 的版本、每个二进制文件的 sha256。
所有命令只读；不要 `dd` 写块设备，不要 `mount`，不要碰 `persist`。

判定器：`python3 scripts/check-w1-lun-evidence.py <采集目录>`。退出码 `0` = PASS、`2` = PENDING、
`1` = FAIL；默认假设 LUN 5，可用 `--expect-lun` 改假设。它要求 Leg A 与 Leg B 同时存在且一致，
`README.txt` 非空才算 provenance；同时存在多个 descriptor 文件会被判为歧义，需用
`--descriptor` 指定。

### 2.6 构建 preflight：PENDING 不能变成红门禁

W1 的证据只可能来自上机后的只读采集，仓库新检出时必然没有。如果直接把判官的
`2`（PENDING）当失败，线内 preflight 会永远红，最后只会被人绕过。所以线内入口是
`scripts/check-w1-lun-preflight.py`，它调用判官后做三态映射：

| 判官结果 | wrapper 退出码 | 构建影响 |
|---|---|---|
| PASS `0` | `0` | 继续 |
| PENDING `2` | `0` | 打印 `PREFLIGHT PENDING`，不阻塞；缺采集目录也走这里 |
| FAIL `1` | `1` | 阻断；矛盾或畸形采集必须停下来查 |

采集目录默认取 `K60_W1_EVIDENCE` 指定的目录，否则在 `K60_W1_EVIDENCE_ROOT`
（默认 `/mnt/e/k60-work/evidence` 或 `E:/k60-work/evidence`）下取最新的
`w1-lun-*`。判官单独的 CLI 仍保留 `0/2/1`，便于人工复判。门禁登记在
`docs/engineering/RULES.toml` 的 `gate-w1-lun`；三态测试在
`scripts/tests/test-w1-lun-preflight.py`。

### 2.7 伪证据清单

| 看起来像证据 | 为什么不是 |
|---|---|
| `sdf` 字母 | 扫描顺序，不是 LUN |
| `modemst1` / `sdf3` 分区名 | 只证明 GPT 名字和分区归属，不证明控制器 LUN |
| `K60UFS volume ... lun=5` | 我们自己的选择回显，自证 |
| `8 MiB` 分区大小 | 与 LUN 编号无关 |
| `/sys/.../device/lun` | 该属性不存在；存在性本身不是证据 |
| VPD `0x83` / `0xb0` | 身份 / 块限制，不含 LUN |
| `bBootLunID` | boot LUN 选择位，不是 LU index |
| 四个分区都在 `sdf` 上 | 只证明共享 SCSI 设备，不证明 LUN=5 |

## 3. 27 flight gate 评审：cellular 需要第三条 blocker 吗

### 3.1 `--flight-ready` 现在实际证明什么

`E:/hackios/k60-gates/scripts/check-ios27-artifacts.py` 的结构检查包括：

- kernel.macho 是 arm64e 的 `MH_EXECUTE` 或 `MH_FILESET`；`MH_FILESET` 必须有 `LC_FILESET_ENTRY`；
- payload 里的 kernel 与声明的 transform 一致；
- ADT `/chosen/random-seed` 是 256 B 的全同值（固定 slide）；
- chip-id `8140`、unique-chip-id `4d4f4e445249414e`；
- boot.img v4 的 FD 与 payload 字节相等。

`open_blockers()`（`:320`）逐行解析 `[[blocker]]`，任何 `state != "closed"` 都算 open；
`flight_ready()`（`:345`）在以下任一条件失败：

1. `MH_FILESET` 的 prelink `missing_refs` 非零；
2. prelink `stubbed_refs` 非零；
3.  blocker 台账里有任何 open 条目。

当前台账只有两条 open：

- `loader-rejects-fileset`：shipped DarwinBoot.efi 只接受 `MH_EXECUTE`/subtype 0；27 kernel 是
  `MH_FILESET`/subtype `0xc0000002`，catalog pin 还要求 `com.apple.kernel` 子类型等于集合子类型。
- `prelink-map-unresolved`：round-17d 的 kernel.json 有 28 bundles/384 unresolved refs，
  29 bundles/2262 items/2688 sites 指向 `_unixnu_fileset_unmapped` panic stub。

这两条都是**loader/XNU 层的飞行致死项**；cellular 不在它们的判据里。

### 3.2 它看不见 cellular

`check-ios27-artifacts.py` 不读补丁 series、不读 `board.toml` 的组件 include、不读 boot args，
也不检查 `QcomBaseband`/`PongUfs`。按设备仓的 order of record：

- `E:/hackios/k60-gates/patches/xnu-12377/series` 里没有我们的 0626–0630；
- `E:/hackios/k60-gates/board.toml:360` 的 27 include 只有
  `["ArmDTPlatform", "ArmCpu", "XnuPrelink"]`，没有 `QcomBaseband`；
- 27 的 boot args 里没有 `pong_modem` / `pong_ipa`（`board.toml` 无匹配）。

所以按当前产物，cellular 根本不在 27 内核里。gate 通过只说明「产物结构 + 两条 blocker」，
不说明「cellular 在」。这是**静默缺失**，不是「结构通过但起飞即死」。

**DRIFT 关闭条件**：设备仓 `patches/xnu-12377/series` 缺 0626–0630 是已知的 F2 欠账，不是本线回归。
F2（27 stage-0 起飞到 SpringBoard）通过后，由设备仓 owner（Lead）把 0626–0630 按序落进
`device:patches/xnu-12377/series` 并在产物中复验；在此之前 series 检查保持红是正确状态，
不得为了变绿放宽门禁，也不得把补丁直接塞进共享 main。

### 3.3 默认参数下，cellular 没有找到飞行致死路径

`E:/k60-work/wt-pitfall/patches/xnu-12377/0629-kern-exec-call-sites.patch:10-25` 在
`mount()` 成功之后、`native_owner_data_stage = 3` 之前调用两个 probe，但用的是：

```c
(void)k60_modem_probe_from_handoff();
(void)k60_ipa_probe_from_handoff();
```

返回值被丢弃，所以 probe 返回 `-1` 不会中断 `exec`。两个 probe 的第一行都是 boot arg 检查：

- `K60ModemBoot.c:185-188`：没有 `pong_modem` 或值为 0 → 返回 0；
- `K60Ipa.c:1417-1419`：没有 `pong_ipa` 或值为 0 → 返回 0。

即使显式打开：

- `K60ModemBoot.c:198-230`：映射失败打印并返回 -1；carrier 不存在打印 `carrier absent` 并返回 0；
  否则 `k60_modem_bring_up()`，失败即返回 rc；只有 `enabled == 2` 才继续 QRTR。
- `K60ModemLink.c:1370-1469`：rails vote 的 QMP open/load_state 最多 10 次（每次约 12 s，
  总约 2 分钟），任一失败打印 `K60MODEM power failed: <why>` 返回 -1；没有 panic，也没有无界循环。
- `K60Ipa.c:1400-1405`：`k60_ipa_firmware_start()` 在当前 27 源里还是 stub，直接返回
  `K60IpaNotReady`，不会启动 IPA 硬件；`ipclk=1` 只做已在 k15/2026-11-18 验证过的 IP0 TCS4 投票。
- `K60Ipa.c:740-775`：`ArmSmmu4KBuild` / `ArmSmmu4KProgramDisabledContext` 是 weak 定义，
  没有强符号时打印 `K60IPA smmu: no ArmSmmu4K in this kernel` 并返回 -1，不会假装成功。
- `TransferPoll.h:13-27`、`K60Ipa.c:1190`、`K60IpaGsi.c:319`、`K60ModemLink.c:361` 都有界；
  本轮检查的 `K60Modem*`/`K60Ipa*` C 源里没有 `panic()`。

因此默认参数下，cellular 的最坏结果是「打印失败并继续」，不是「起飞即死」。
唯一接近飞行风险的是：显式 `pong_modem` 且 QMP 失败时，`kern_exec` 里可能停约 2 分钟；
这属于**打开实验后的 boot 时延/看门狗风险**，不是默认产物的结构问题。

### 3.4 真正的缺口是覆盖，不是 blocker

如果 27 产物没有 0626–0630，gate 仍可能绿；这会让「cellular 已迁移」成为假结论。
这应该由 **coverage 警告**解决，而不是第三条 flight blocker：

- 非阻塞警告：27 series 没有 0626–0630、include 没有 `QcomBaseband`、boot args 没有
  `pong_modem`/`pong_ipa` → 打印「cellular not in this artifact」；
- 若将来 cellular 进 27，警告变成「cellular 在产物里，但 HR-01 的 cx/mss/xo TCS4 仍是未验证」；
- 这些都不应让 `--flight-ready` 失败，因为它们不阻止 XNU 起飞。

### 3.5 建议

1. **现在不加第三条 blocker。** 两条 open 已经覆盖 loader 与 prelink；cellular 默认惰性，
   没有独立的飞行致死项。
2. 如果要防「打开 `pong_modem` 后 2 分钟卡住」，加一条**独立的 boot-arg 政策检查**
   （例如 `--cellular-guard`）：检测到 `pong_modem`/`pong_ipa` 且 HR-01 台账未验证时拒绝起飞。
   它是飞行策略，不是产物结构 blocker。
3. 如果 Lead 坚持要第三条 blocker，唯一能自洽的 id 是
   `cellular-enabled-without-hr01-evidence`：只在 boot args 真的带 `pong_modem`/`pong_ipa`
   时 open；默认产物下它必须是 closed/absent。不要把它写成结构检查。
4. 会让本结论改变的证据：默认 27 boot args 里出现 `pong_modem`/`pong_ipa`；或 0626–0630
   已进设备仓 series 且编译进内核；或在默认参数下观察到 cellular probe 的 panic/看门狗。
   出现任一条，重开本节。

## 4. 下一步

- W1：等一次只读采集（Leg A + Leg B），按 §2.4 判定并用 `scripts/check-w1-lun-evidence.py` 复核；在此之前保持 PENDING。
- 27：series/组件/boot args 的落盘仍由设备仓 owner 决定；本文件只给判据，不改共享仓。
- k55：本文件与 W2 的判据同属证据线；不构建、不上机。
