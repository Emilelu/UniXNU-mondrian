# W1 决策单：一次只读采集定案 UFS LUN

- 日期：2026-11-20 21:20
- 适用：Android 已启动、adb 可用；**只读**，不 build、不 boot、不 flash、不写任何块设备。
- 判官：`scripts/check-w1-lun-evidence.py`（PASS=0，PENDING=2，FAIL=1）；
  包装：`scripts/check-w1-lun-preflight.py`（PENDING 退 0，FAIL 退 1）。
- 本文不假设 LUN 5；LUN 5 只是待验证的期望值。A、B 两腿都成立才算 PASS。

## 0. 先看结论

| 采集结果 | 判定 | 下一步 |
|---|---|---|
| A 的 L=5；B 的 byte2=0x05、byte3=0x01；README 非空 | PASS | W1 关闭，写进 doc20/21 |
| A 的 L=5；B 缺失（无 bsg、无工具或 EACCES） | PENDING | 保留 A，补 B；不要写成 PASS |
| A 缺失；B 有值 | PENDING | 补 A；不要用 B 反推盘号 |
| A=5；B 的 byte2=4 或 byte3=0 | FAIL | 真实矛盾，停查，交回原始输出 |
| A=4；B 的 byte2=4、byte3=1 | FAIL（默认期望 5） | 这是「W1 假设可能错」，不是采集错误；停查，交回，不自行改期望 |
| HCTL 格式坏、`/proc/scsi/scsi` 与 A 不一致、描述符短/IDN 不是 0x02 | FAIL | 采集本身坏了，重采 |

**一次采集能定案的只有 Leg A + Leg B。** Leg C 只做身份绑定；EFS 字节是 W2，服务数与 RF 是 F3。

## 1. 固定变量（同一个 shell 里执行）

```sh
if [ -d /mnt/e/k60-work/evidence ]; then
  ROOT=/mnt/e/k60-work/evidence
else
  ROOT=E:/k60-work/evidence
fi
CAP=$ROOT/w1-lun-$(date +%Y%m%d-%H%M%S)
mkdir -p "$CAP"

if [ -d /mnt/e/k60-work/wt-k55 ]; then
  REPO=/mnt/e/k60-work/wt-k55
else
  REPO=E:/k60-work/wt-k55
fi

adb shell getprop ro.serialno > $CAP/serialno.txt 2>&1
adb shell getprop ro.build.fingerprint > $CAP/fingerprint.txt 2>&1
adb shell getprop ro.boot.hardware > $CAP/hardware.txt 2>&1
adb shell uname -a > $CAP/uname.txt 2>&1
adb shell id > $CAP/id.txt 2>&1
```

这些文件只把采集绑定到一台设备和一次启动；它们不是 LUN 证据。

## 2. 步骤 1：把 modemst1 绑到父磁盘

不要从 `sdf` 字母猜 LUN。先读 by-name 链接，取父磁盘，再用 sysfs 与 `lsblk` 交叉确认。

```sh
adb shell ls -l /dev/block/by-name/modemst1 > $CAP/modemst1-link.txt 2>&1
adb shell readlink -f /dev/block/by-name/modemst1 > $CAP/modemst1-real.txt 2>&1
MODEMST=$(tr -d '\r' < $CAP/modemst1-real.txt)
case $MODEMST in
  /dev/block/sd[a-z]*) SDF=$(basename $MODEMST | sed -E 's/[0-9]+$//') ;;
  *) echo UNEXPECTED_MODEMST=$MODEMST; SDF= ;;
esac
if [ -z "$SDF" ]; then
  echo STOP: modemst1 did not bind to a /dev/block/sd* disk
  echo Keep the capture directory: $CAP
  exit 2
fi
```

再确认父磁盘：

```sh
adb shell readlink -f /sys/class/block/$SDF > $CAP/disk-sysfs.txt 2>&1
adb shell ls -l /sys/class/block/$SDF > $CAP/disk-link.txt 2>&1
adb shell lsblk -o NAME,MAJ:MIN,SIZE,TYPE,PKNAME,MOUNTPOINT > $CAP/lsblk.txt 2>&1
adb shell cat /proc/partitions > $CAP/proc-partitions.txt 2>&1
```

`lsblk` 不存在时，`lsblk.txt` 会留下错误；用 `disk-sysfs.txt` 与 `/proc/partitions` 继续。
`SDF` 必须是整盘（如 `sdf`），不是分区（如 `sdf1`）；脚本已经去掉末尾数字，但仍要人工看一眼 `lsblk` 的 `PKNAME`。

## 3. 步骤 2：Leg A（HCTL 第四段）

```sh
adb shell readlink -f /sys/class/block/$SDF/device > $CAP/device-link.txt 2>&1
tr -d '\r' < $CAP/device-link.txt | xargs -r basename > $CAP/hctl.txt 2>&1
adb shell cat /proc/scsi/scsi > $CAP/proc-scsi-scsi.txt 2>&1
adb shell ls -l /sys/class/scsi_device > $CAP/scsi-devices.txt 2>&1
```

期望：`device-link.txt` 只有一行，末段是 `H:C:T:L`；`hctl.txt` 形如 `0:0:0:5`；
`/proc/scsi/scsi` 含 `Host: scsi0 Channel: 00 Id: 00 Lun: 05`。

| 字段 | 含义 | 合法范围 | 本单期望 |
|---|---|---|---|
| H | SCSI host 号 | 非负整数 | 记录即可 |
| C | channel | 通常 0 | 记录即可 |
| T | target | 通常 0 | **不是 LUN**，不能拿它代替 L |
| L | SCSI LUN，也就是 UFS LU 号 | 0..31 | **5** |

`device-link.txt` 为空或 `readlink` 失败 ⇒ Leg A PENDING。
读到了但末段不是四段整数 ⇒ 采集坏了，FAIL，重采。
`proc-scsi-scsi.txt` 存在但没有 `Host: ... Lun: ...` 行，或其中 L 与 A 不一致 ⇒ FAIL，不要删文件消噪。

## 4. 步骤 3：Leg B（UFS Unit Descriptor，IDN 0x02）

### 4.1 找 bsg 节点

```sh
adb shell ls -l /dev/bsg > $CAP/bsg-nodes.txt 2>&1
adb shell ls -l /dev | grep -i ufs >> $CAP/bsg-nodes.txt 2>&1
BSG=$(adb shell 'for n in /dev/bsg/ufs-bsg0 /dev/bsg/ufs-bsg /dev/ufs-bsg; do [ -c $n ] && { echo $n; break; }; done' | tr -d '\r')
if [ -z "$BSG" ]; then echo LEG_B_PENDING: no bsg node; fi
```

没有 `/dev/bsg/*` 就是 Leg B PENDING；**不要**用 `sg_inq` 或 `/dev/block/sdf` 的 SCSI CDB 顶替。

### 4.2 找工具

```sh
UFS_TOOL=$(adb shell 'command -v ufs-utils || command -v ufs-tool' | tr -d '\r' | head -1)
if [ -n "$UFS_TOOL" ]; then
  adb shell "$UFS_TOOL" -v > $CAP/ufs-tool-version.txt 2>&1 || true
else
  echo LEG_B_PENDING: no ufs-utils or ufs-tool
fi
```

设备上没有工具时 Leg B 记 PENDING；不要从网络临时下载二进制。若 Lead 另行提供已核验的 aarch64 工具，
把来源和 sha256 写进 `README.txt`，只允许 `desc -t 2 -i 5 -s 0 -r -D ... -p ...` 这一组只读选项。

### 4.3 读 LUN 5 的 Unit Descriptor

```sh
if [ -z "$BSG" ] || [ -z "$UFS_TOOL" ]; then
  echo LEG_B_PENDING: no bsg node or no ufs tool
else
  adb shell "$UFS_TOOL" desc -t 2 -i 5 -s 0 -r -D /data/local/tmp/unit-desc-L5.bin -p "$BSG" > $CAP/unit-desc-L5.txt 2>&1
  adb shell ls -l /data/local/tmp/unit-desc-L5.bin > $CAP/unit-desc-L5-size.txt 2>&1
  adb pull /data/local/tmp/unit-desc-L5.bin $CAP/unit-desc-L5.bin > $CAP/unit-desc-pull.txt 2>&1
  xxd -g1 -l 16 $CAP/unit-desc-L5.bin > $CAP/unit-desc-L5-hex.txt 2>&1 || od -An -tx1 -N16 $CAP/unit-desc-L5.bin > $CAP/unit-desc-L5-hex.txt 2>&1
fi
```

若 `desc` 返回 EACCES：只有设备已授权 root 时才执行 `adb root` 后重跑；生产 adbd 不允许 root 时 Leg B 记 PENDING。
不允许为了拿 bsg 去 `mount -o remount,rw /`、改 init 或 `dd` 块设备。

头部字节：

| 字节 | 字段 | 合法值 | 判据 |
|---|---|---|---|
| 0 | `bLength` | 通常 0x2d 或 0x30 | >=5，且不大于文件长度 |
| 1 | `bDescriptorIDN` | 0x02 | 必须是 Unit Descriptor |
| 2 | `bUnitIndex` | 0x05 | 必须等于 Leg A 的 L |
| 3 | `bLUEnable` | 0x01 | 必须是 enabled |
| 4 | `bBootLunID` | 0..2 | 只记录，**不是 LUN 编号** |

文件不足 5 字节、IDN 不是 0x02、`bLUEnable` 不是 0/1、`bBootLunID>2` ⇒ FAIL；
不要手工截断或补零来修文件。

## 5. 步骤 4：Leg C（仅身份绑定，不是通过条件）

有 sg3_utils 就记录：

```sh
adb shell sg_inq -p 0x00 /dev/block/$SDF > $CAP/vpd-00.txt 2>&1
adb shell sg_inq -p 0x83 /dev/block/$SDF > $CAP/vpd-83.txt 2>&1
adb shell sg_inq -p 0xb0 /dev/block/$SDF > $CAP/vpd-b0.txt 2>&1
```

`0x83` 只把采集绑定到同一个 LU；标准 SCSI VPD 没有直接报告 UFS LUN 的页。没有 sg3_utils 就跳过并在 README 写 `skipped`。

## 6. 步骤 5：落盘、校验、判官

最小目录至少要有：

```text
README.txt
device-link.txt
hctl.txt
unit-desc-L5.bin
proc-scsi-scsi.txt
bsg-nodes.txt
ufs-tool-version.txt
```

`README.txt` 至少写：

```text
capture_time=...
adb_serial=...
build_fingerprint=...
kernel=...
modemst1_link=...
parent_disk=...
bsg=...
ufs_tool=...
ufs_tool_sha256=...
commands=see W1-DECISION-SHEET.md
```

然后：

```sh
( cd "$CAP" && find . -maxdepth 1 -type f ! -name sha256sums.txt -exec sha256sum {} + > sha256sums.txt )
cd "$REPO"
python3 scripts/check-w1-lun-evidence.py $CAP; echo JUDGE_RC=$?
python3 scripts/check-w1-lun-preflight.py --evidence $CAP; echo PREFLIGHT_RC=$?
```

`JUDGE_RC`：0=PASS，2=PENDING，1=FAIL。`PREFLIGHT_RC`：PENDING 也会退 0；只有矛盾/畸形才退 1。

## 7. 两腿矛盾怎么处置

1. **A 与 B 都指向 5**：PASS；把 `hctl.txt`、`unit-desc-L5-hex.txt`、`README.txt` 交回。
2. **A=5，B 缺失**：PENDING；只写「HCTL=5，Descriptor PENDING」，不能写 PASS。
3. **A=5，B 的 byte2=4 或 byte3=0**：FAIL；真实矛盾，停查，交回原始 A/B，不二选一。
4. **A=4，B 的 byte2=4、byte3=1**：FAIL（默认期望 5）；这是「W1 的期望值可能错」，不是采集错。
   停查并把 A/B 原始输出交回 Lead；**不要**自行改 `--expect-lun` 让灯变绿。
5. **A 缺失、B 有值**：PENDING；B 不能反推盘号。
6. **`device-link` 与 `/proc/scsi/scsi` 不一致**：FAIL；采集坏，重采。
7. **没有 bsg 或没有工具**：PENDING；这是证据缺口，不是 W1 的反证。

## 8. Leg B 的字节序自证（file:line）

本节回答「为什么 byte2 是 bUnitIndex、byte3 是 bLUEnable」，不是从别处抄形状。

27 UEFI feed `mu_basecore-8f10084c`，HEAD `cfb93724a06ff86ff5ba971413368a7809ee42a5`：

- `MdePkg/Include/IndustryStandard/Ufs.h:32` 是 `#pragma pack(1)`，结构按字节紧排。
- `Ufs.h:873-893` 的 `UFS_UNIT_DESC` 前五个字段依次是 `UINT8 Length`、`DescType`、`UnitIdx`、`LunEn`、`BootLunId`；逐行定义在 `Ufs.h:874`/`:875`/`:876`/`:877`/`:878`，即 byte0..4：

  | byte | 字段 | 27 UEFI 行 | 类型 |
  |---|---|---|---|
  | 0 | `Length` | `Ufs.h:874` | `UINT8` |
  | 1 | `DescType` | `Ufs.h:875` | `UINT8` |
  | 2 | `UnitIdx` | `Ufs.h:876` | `UINT8` |
  | 3 | `LunEn` | `Ufs.h:877` | `UINT8` |
  | 4 | `BootLunId` | `Ufs.h:878` | `UINT8` |

  `Ufs.h:32` 的 `#pragma pack(1)` 加五个单字节字段，声明顺序就是字节偏移；这不是从 Linux 源码推的。
- `Ufs.h:658-667` 的 `UFS_DESC_IDN` 把 `UfsUnitDesc` 定义为 `0x02`。
- `MdeModulePkg/Bus/Ufs/UfsPassThruDxe/UfsPassThru.c:996-1008` 用 `sizeof(UFS_UNIT_DESC)`、循环 `Index=0..7`，调用
  `UfsRwDeviceDesc(Private, TRUE, UfsUnitDesc, (UINT8)Index, 0, &UnitDescriptor, &UnitDescriptorSize)`；
  `:1004` 直接比较 `UnitDescriptor.LunEn == 0x1`。
- `UfsPassThruHci.c:1045-1077` 的 `UfsRwDeviceDesc()` 在 `Read` 时设 `Packet.Opcode = UtpQueryFuncOpcodeRdDesc`，
  并把 `DescId`、`Index`、`Selector` 原样放进请求；`Ufs.h:472` 把 `UtpQueryFuncOpcodeRdDesc` 定义为 `0x01`。

所以 `-t 2 -i 5 -s 0` 发出的就是「Unit Descriptor、index 5、selector 0」的读请求；返回结构的前五字节按 packed `UFS_UNIT_DESC` 解释。
五个字段都是 `UINT8`，单字节没有端序问题。

独立交叉核对（Linux v6.12，tag `06090c9b622a7e1f797e775db4c035e0d779b76e`，commit `adc218676eef25575469234709c2d87185ca223a`）：

- `include/ufs/ufs.h:207-216` 把 byte2 定义为 `UNIT_DESC_PARAM_UNIT_INDEX`、byte3 定义为 `UNIT_DESC_PARAM_LU_ENABLE`。
- `drivers/ufs/core/ufshcd.c:3637-3703` 的 `ufshcd_read_desc_param()` 发 `READ_DESC`，在 `:3676` 检查边界，
  在 `:3696-3697` 用 `memcpy(&desc_buf[param_offset], ...)` 按字节拷贝；`ufs-sysfs.c:888-932` 也按字节 offset/size 解释。
- `ufshcd.c:5130-5181` 的 `ufshcd_lu_init()` 在 `:5168-5170` 比较 `UNIT_DESC_PARAM_UNIT_INDEX` 与 RPMB WLUN。
- `bLUEnable` 在 mainline 只有 `ufs-sysfs.c:1594` 的 sysfs 呈现（`:916-919` 打印 `0x%02X`），没有内核策略消费者；
  所以只能说 Linux 的字节布局与 27 UEFI 一致，**不能**说 Linux 用 `bLUEnable` 门控 LUN。

## 9. 这次采集不能证明什么

- 不能证明 EFS 超级块内容正确：那是 W2，只比 storage 1..4 的首 16 字节；完整 4 KiB 是 F3。
- 不能证明 modem 继续读、服务数增长或 RF 初始化：那是 W3/W4 与 PAS4 之后的事。
- 不能从 `sdf` 字母、`modemst1` 名字、我们驱动打印的 `lun=5`、8 MiB 大小或 `bBootLunID` 反推 LUN。
- 不能证明第三方 `ufs-utils` 二进制本身可信；必须记录来源与 sha256。

## 10. 执行顺序（照这个顺序做）

1. 固定变量，记录设备身份。
2. 从 `modemst1` 取父磁盘，交叉确认 `SDF`。
3. 读 Leg A，保存 `device-link.txt`、`hctl.txt`、`proc-scsi-scsi.txt`。
4. 找 bsg 与工具；读 Leg B，保存原始 16 字节 hex。
5. 可选 Leg C。
6. 写 README，生成 `sha256sums.txt`，跑判官与 preflight。
7. 按第 7 节判定；PENDING 就保留缺口，FAIL 就交回原始输出。

采集完成后回传：`CAP` 路径、`hctl.txt`、`unit-desc-L5-hex.txt`、`README.txt`、判官输出与 RC。
