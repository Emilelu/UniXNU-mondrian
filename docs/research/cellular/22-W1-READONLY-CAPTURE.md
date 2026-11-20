# W1 只读取证单：一次采集定案 UFS LUN

本文是给 Lead 的**只读**采集单，用来把 W1 从 PENDING 推到 PASS 或 FAIL。
它不启动内核、不刷机、不写任何块设备；全部命令在已启动的 Android 侧执行。
采集完成后，`scripts/check-w1-lun-evidence.py` 就是唯一判官。

## 0. 边界与安全

- 只读：不运行 `dd`、不 `mount -o rw`、不写 `/dev/block/*`、不 `fastboot`。
- 普通权限优先：先按下面的命令直接跑；只有 `/dev/bsg` 返回 EACCES 时，才使用设备上**已经授权**的 root（`adb root` 或 `su`）。生产版本 adbd 不允许 root 时，Leg B 记 PENDING，不要为了取证去解锁或 remount。
- 允许的写只有两处，且都不碰块设备：`adb push` 把工具放到 `/data/local/tmp`，以及 `ufs-utils -D` 把描述符写到 `/data/local/tmp`。任何 `-w`、`-e`、`-c` 选项都不许出现。
- 目录名用 `w1-lun-YYYYMMDD-HHMMSS`，这样 `check-w1-lun-preflight.py` 能自动找到最新一次采集。

## 1. 先记录设备身份

```sh
# WSL 用 /mnt/e/k60-work/evidence；Windows Git Bash 用 E:/k60-work/evidence。
# 两者都可被 K60_W1_EVIDENCE_ROOT 覆盖；wrapper 只在 evidence 根下自动找最新 w1-lun-*。
if [ -z "${K60_W1_EVIDENCE_ROOT:-}" ]; then
  if [ -d /mnt/e/k60-work/evidence ]; then
    K60_W1_EVIDENCE_ROOT=/mnt/e/k60-work/evidence
  else
    K60_W1_EVIDENCE_ROOT=E:/k60-work/evidence
  fi
fi
CAP="$K60_W1_EVIDENCE_ROOT/w1-lun-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CAP"

adb shell getprop ro.serialno          > "$CAP/serialno.txt" 2>&1
adb shell getprop ro.build.fingerprint > "$CAP/fingerprint.txt" 2>&1
adb shell getprop ro.boot.hardware     > "$CAP/hardware.txt" 2>&1
adb shell uname -a                     > "$CAP/uname.txt" 2>&1
adb shell id                           > "$CAP/id.txt" 2>&1
```

这些文件只用于把采集绑定到一台设备和一次启动；它们不是 LUN 证据。

## 2. 把 modemst1 绑到父磁盘（不要从字母猜）

先找 by-name 链接：

```sh
adb shell 'ls -l /dev/block/by-name/modemst1' > "$CAP/modemst1-link.txt" 2>&1
adb shell 'readlink -f /dev/block/by-name/modemst1' > "$CAP/modemst1-real.txt" 2>&1
```

如果 by-name 不存在，退回到实际路径：

```sh
adb shell 'find /dev/block -name modemst1 2>/dev/null' > "$CAP/modemst1-find.txt" 2>&1
```

从 `modemst1-real.txt` 取得分区节点，再取父磁盘。例如节点是
`/dev/block/sdf1`，父磁盘就是 `sdf`；节点是 `/dev/block/sdf` 时父磁盘也是 `sdf`。
用 sysfs 再确认一次，不要只凭名字：

```sh
SDF=sdf                    # 按上一步的实际父磁盘替换
adb shell "readlink -f /sys/class/block/$SDF" > "$CAP/disk-sysfs.txt" 2>&1
adb shell "ls -l /sys/class/block/$SDF"       > "$CAP/disk-link.txt" 2>&1
adb shell 'lsblk -o NAME,MAJ:MIN,SIZE,TYPE,PKNAME,MOUNTPOINT' > "$CAP/lsblk.txt" 2>&1
adb shell 'cat /proc/partitions' > "$CAP/proc-partitions.txt" 2>&1
```

`lsblk` 不存在时，`lsblk.txt` 会留下明确错误；用 `disk-sysfs.txt` 和
`/proc/partitions` 继续。不要因为 `sdf` 看起来像第 6 个字母就把它当成 LUN 5。

> 下面的命令默认在同一个 shell 里执行。若你按代码块分开复制，先重新设置
> `CAP`、`SDF`（以及后面的 `BSG`、`UFS_TOOL`），否则空变量会把命令变成
> 对错误路径的读取。

## 3. Leg A：HCTL 的最后一段

SCSI sysfs 的规范名是 `H:C:T:L`；普通 UFS LU 的第四段 `L` 就是控制器 LUN，
`T` 通常是 0，**不能拿 T 当 LUN**。

```sh
adb shell "readlink -f /sys/class/block/$SDF/device" > "$CAP/device-link.txt" 2>&1
adb shell "basename \$(readlink -f /sys/class/block/$SDF/device)" > "$CAP/hctl.txt" 2>&1
adb shell 'cat /proc/scsi/scsi' > "$CAP/proc-scsi-scsi.txt" 2>&1
adb shell 'ls -l /sys/class/scsi_device' > "$CAP/scsi-devices.txt" 2>&1
```

`device-link.txt` 必须只有一行，末段形如 `0:0:0:5`；`hctl.txt` 应该是
`0:0:0:5`。如果 `readlink -f` 失败或输出为空，Leg A 是 PENDING，不是 0。

`proc-scsi-scsi.txt` 必须包含同一行，例如：

```text
Host: scsi0 Channel: 00 Id: 00 Lun: 05
```

如果该文件存在但没有 `Host: ... Lun: ...` 行，或列出的 HCTL 与
`device-link.txt` 不一致，判官会直接 FAIL；不要删除这个文件来“消除噪声”，
要记录真实输出。

## 4. Leg B：UFS Unit Descriptor（IDN 0x02）的 byte 2/3

### 4.1 找 bsg 节点

```sh
adb shell 'ls -l /dev/bsg' > "$CAP/bsg-nodes.txt" 2>&1
adb shell 'ls -l /dev | grep -i ufs' >> "$CAP/bsg-nodes.txt" 2>&1
```

常见节点是 `/dev/bsg/ufs-bsg0`，也有设备用 `/dev/ufs-bsg`。
把实际节点记到变量：

```sh
BSG=/dev/bsg/ufs-bsg0      # 按 bsg-nodes.txt 的实际值替换
```

若两个位置都没有字符设备，Leg B 记 PENDING；不要用 `sg_inq` 或
`/dev/block/sdf` 的 SCSI CDB 顶替。

### 4.2 工具

优先用设备上已有的 `ufs-utils` 或 `ufs-tool`：

```sh
adb shell 'command -v ufs-utils || command -v ufs-tool' > "$CAP/ufs-tool-path.txt" 2>&1
adb shell 'ufs-utils -v 2>/dev/null || ufs-tool -v 2>/dev/null' > "$CAP/ufs-tool-version.txt" 2>&1
```

没有工具时，可以先在 `/data/local/tmp` 放一个**已经验证过**的 aarch64 构建
（来源和 sha256 必须写进 README.txt）；不要从设备上随便下载二进制。工具只要
支持 `desc` 的 `-t/-i/-s/-D/-p` 这组选项即可。`-i` 是描述符 index（也就是
LU 号），`-s 0` 是 selector，`-t 2` 是 Unit Descriptor，`-r` 是只读，
`-D` 把原始描述符写成文件。

### 4.3 读 LUN 5 的 Unit Descriptor

```sh
UFS_TOOL=/data/local/tmp/ufs-utils   # 按实际路径替换

adb shell "$UFS_TOOL desc -t 2 -i 5 -s 0 -r -D /data/local/tmp/unit-desc-L5.bin -p $BSG" \
  > "$CAP/unit-desc-L5.txt" 2>&1

adb shell 'ls -l /data/local/tmp/unit-desc-L5.bin' > "$CAP/unit-desc-L5-size.txt" 2>&1
adb pull /data/local/tmp/unit-desc-L5.bin "$CAP/unit-desc-L5.bin" > "$CAP/unit-desc-pull.txt" 2>&1
xxd -g1 -l 16 "$CAP/unit-desc-L5.bin" > "$CAP/unit-desc-L5-hex.txt" 2>&1 || \
  od -An -tx1 -N16 "$CAP/unit-desc-L5.bin" > "$CAP/unit-desc-L5-hex.txt" 2>&1
```

`unit-desc-L5.bin` 的头部应为：

| 字节 | 字段 | 合法值 | 判据 |
|---|---|---|---|
| 0 | `bLength` | 通常 `0x2d` 或 `0x30`，以设备为准 | `>= 5` 且不大于文件长度 |
| 1 | `bDescriptorIDN` | `0x02` | 必须是 Unit Descriptor |
| 2 | `bUnitIndex` | `0x05` | 必须等于 Leg A 的 L |
| 3 | `bLUEnable` | `0x01` | 必须是 enabled |
| 4 | `bBootLunID` | 0..2 | 记录，不当作 LUN 编号 |

字段偏移来自 27 UEFI feed 的 packed `UFS_UNIT_DESC`（`Ufs.h:873-893`），
并由 Linux v6.12 的 `ufshcd_read_desc_param()` 按字节切片独立闭合
（`drivers/ufs/core/ufshcd.c:3637-3703`，commit
`adc218676eef25575469234709c2d87185ca223a`）。这两个字段都是单字节，
没有端序问题。

如果读到的文件不足 5 字节、`bDescriptorIDN` 不是 0x02、`bLUEnable` 不是
0/1、`bBootLunID > 2`，判官会 FAIL。不要手工截断或补零来“修好”文件。

## 5. Leg C：仅作身份绑定，不是通过条件

有 sg3_utils 时记录：

```sh
adb shell "sg_inq -p 0x00 /dev/block/$SDF" > "$CAP/vpd-00.txt" 2>&1
adb shell "sg_inq -p 0x83 /dev/block/$SDF" > "$CAP/vpd-83.txt" 2>&1
adb shell "sg_inq -p 0xb0 /dev/block/$SDF" > "$CAP/vpd-b0.txt" 2>&1
```

`0x83` 只把这次采集绑定到同一个 LU；**没有任何标准 SCSI VPD 页直接报告
UFS LUN**，所以 `0x83` 不能替代 Leg A/B。没有 sg3_utils 就跳过，并在
`README.txt` 写“skipped”。

## 6. 落盘布局与自检

最小采集目录：

```text
w1-lun-YYYYMMDD-HHMMSS/
  README.txt                 # 时间、serial、fingerprint、命令、工具 sha256
  device-link.txt            # 只有一行，末段 H:C:T:L
  unit-desc-L5.bin           # 至少 5 字节，IDN 0x02
  proc-scsi-scsi.txt         # 含同一 HCTL 行
  hctl.txt
  bsg-nodes.txt
  ufs-tool-version.txt
  vpd-83.txt                 # 有就记，没有可省
```

`README.txt` 至少写：

```text
capture_time=...
adb_serial=...
build_fingerprint=...
kernel=...
modemst1_link=...
parent_disk=sdf
bsg=/dev/bsg/ufs-bsg0
ufs_tool=/data/local/tmp/ufs-utils
ufs_tool_sha256=...
commands=see this sheet
```

生成校验和：

```sh
( cd "$CAP" && sha256sum * > sha256sums.txt )
```

跑判官（PASS=0，PENDING=2，FAIL=1）：

```sh
python3 scripts/check-w1-lun-evidence.py "$CAP"
```

判官的 PASS 条件是：Leg A 的 L=5、Leg B 的 `bUnitIndex=5` 且
`bLUEnable=1`、`README.txt` 非空；`proc-scsi-scsi.txt` 若存在，必须列出
同一个 HCTL。它不要求 Leg C。

## 7. 结果怎么读

| 现场 | 判官 | 结论 |
|---|---|---|
| A=5，B=index5/enable1，README 有 | PASS | W1 可关闭；把 HCTL 与描述符写进 doc20/21 |
| A=5，B 缺失 | PENDING | 写「HCTL=5，Descriptor PENDING」，继续补 Leg B |
| A=5，B=index4 | FAIL | 真实矛盾；停查，不能二选一 |
| A=4，B=index4 | FAIL（默认 expect=5） | 先裁决假设；确认真的是 LUN 4 后，记录并显式 `--expect-lun 4` 重跑，不能为了绿灯直接改 |
| B=enable0 | FAIL | 该 LU 未使能；不是 LUN 编号问题 |
| HCTL 格式错 / proc 不列该 HCTL | FAIL | 采集本身有问题，重采 |
| 没有 bsg 或没有工具 | PENDING | 不是 W1 的反证，只是证据缺口 |

**一次采集能定案的只有 Leg A + Leg B。** `sdf` 字母、`modemst1` 名字、
我们自己驱动打印的 `lun=5`、8 MiB 大小、`bBootLunID` 都不是证据；
不要用它们补位。

## 8. 明确不要做的事

- 不要 `adb shell su -c 'dd if=/dev/block/sdf ...'`：读整个块设备既无必要，也会把
  采集变成大文件；W1 只需要 sysfs 和 5 字节描述符头。
- 不要为了拿到 `/dev/bsg` 去 `mount -o remount,rw /` 或改 `init`。
- 不要用 `sg_inq` 的 VPD 页猜 LUN；它没有这个字段。
- 不要修改 `unit-desc-L5.bin` 的 byte 2/3 让判官变绿。
- 不要在未记录工具 sha256 的情况下把第三方二进制放进 `/data/local/tmp`。

## 9. 代码锚点

- 判官：`scripts/check-w1-lun-evidence.py`
- 预检包装：`scripts/check-w1-lun-preflight.py`（PENDING→0，FAIL→1）
- 判据与伪证据表：`docs/research/cellular/21-IOS27-W1-AND-BLOCKER-REVIEW.md`
- Linux 描述符读取：`drivers/ufs/core/ufshcd.c:3637-3703`、
  `include/ufs/ufs.h:207-216`（v6.12，commit
  `adc218676eef25575469234709c2d87185ca223a`）
- 27 UEFI 描述符结构：`mu_basecore-8f10084c` 的 `Ufs.h:873-893`、
  `UfsPassThru.c:996-1007`

## 10. 接线范围（给 Lead）

`gate-w1-lun` 登记在本分支的 `docs/engineering/RULES.toml`。线内 preflight 的入口是
`E:/hackios/UniXNU/scripts/unixnu/gates.py:21-46`：它运行
`ctx.device/scripts/check-rules.py --repo <device-or-K60_REPO>`。因此：

- 只有 `--device` / `K60_REPO` 指向本分支时，本规则才会执行；规则里的
  `python3 scripts/check-w1-lun-preflight.py` 也从该 `REPO` 运行。
- 27 设备仓 `E:/hackios/k60-gates` 是 main，不包含这条规则；在它合入/移植之前，
  27 构建的 preflight **不会**自动执行 W1 门禁。不要把“k60-gates 没报错”当作 W1 已接线。
- 若只是验证接线，可临时把 `K60_REPO` 指向本分支并跑
  `python3 scripts/check-rules.py --only gate-w1-lun`；这只是验证，不是 27 构建的等价物。
- 采集目录默认放在 `E:/k60-work/evidence`（WSL 为 `/mnt/e/k60-work/evidence`）；
  wrapper 只在该根目录下找最新 `w1-lun-*`。放在别处时用 `--evidence` 显式指定。

## 11. W1/W2 之后的 F3 判据（2026-11-20 21:20）

W1 解决「哪个盘」，W2 解决「首 16 字节对不对」，F3 才解决「modem 是否接受这份 EFS 并继续启动」。
顺序是硬的：**W1 PASS → W2 PASS → W3/W4 → PAS4/RF**。任何一步都不能拿后一步的结果补前一步。

### 11.1 EFS 超级块按 storage 分别比

W2 只看 offset 0 的 16 字节；F3 要看**完整 4 KiB 超级块**，storage 1..4 各一次，按 storage 分别与独立来源比较。
独立来源是 2026-11-20 在 Android 侧只读取得的 `E:/k60-work/evidence/efs-ground-truth-20261120/sdf3.bin` … `sdf6.bin`；
对应关系是 Android `by-name` 的 `modemst1`/`modemst2`/`fsg`/`fsc`，不是控制器 LUN 的证明。

| storage | 引导路径 | 分区 | 4 KiB sha256 |
|---|---|---|---|
| 1 | `/boot/modem_fs1` | `modemst1` | `94c2aa725f4e8c5d3de317e8cd39f7efc1588866e7d2854011d10e4656a1a6bb` |
| 2 | `/boot/modem_fs2` | `modemst2` | `8610958511c22e7c44736363ac2b9c2d8e87bd16d78540fa2d4e97be1c489726` |
| 3 | `/boot/fsg` | `fsg` | `e9a62f2a22e469b8008da4dc2733148ae4abcf887c9e1277a7646123fdbc31b4` |
| 4 | `/boot/fsc` | `fsc` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7`（4096 个 0） |

三点读法：

- `fsc` 首块本来就是全零；对 storage 4 全零是正确结果，对 1/2/3 是错误结果。判据不能写成「非零即通过」，必须按 storage 分别比。
- 三个 EFS 超级块的头 12 字节同形（`xx000000 03000000 d8010000`），第 13 字节起才分叉；W2 的 16 字节足以区分，但不等于完整 4 KiB 正确。
- 表里的「LUN 5」只在 W1 PASS 后才是事实；W1 仍 PENDING 时，把这张表当作 storage 内容参照，不要把它当作控制器 LUN 证据。

如果 W2 的 16 字节匹配而完整 4 KiB 不匹配：先查读取长度/offset/window 是否真的覆盖 4 KiB，再查是否把不同 storage 的窗口混用；
如果完整 4 KiB 匹配而 modem 不继续：进入 11.2，不要回头改 EFS 字节。

### 11.2 W3/W4：modem 是否继续

- **W3**：同一 storage 出现第二次 `rmtfs rw`，且 offset 与第一次不同；`fsg`/`fsc` 也被 open。只有一次读、之后再无请求 ⇒ 内容被 modem 判为无效，或请求根本没被接受。
- **W4**：`K60MODEM qrtr: wait … services=` 从 2 涨到 >2，或出现新服务号；`replies` 非零；RMTFS 14/1 端口 0x102 有请求/应答。
- 服务数增长是**下游结果**，不能反过来证明 EFS 字节正确；W2/F3-1 才是因。
- `rmtfs open` 四次只证明路径与 storage 映射被打开，不证明读到数据；`rmtfs rw … served` 只证明我们没拒绝。

### 11.3 PAS4 之后的 RF 初始化

`PongModemRuntime.cpp:271-277` 在 PAS4 之前等 `pong_rfs_ready()`，注释写明 RF 初始化会立刻请求读写文件；
所以 EFS 是 PAS4 的**上游**，不是 PAS4 的产物。PAS4 之后要看的不是「再读一次 EFS」，而是 modem 的 RF/QMI 是否继续：

- `auth_reset` 已发出，`init_image ok`、`mem_setup` 等 PAS4 行出现；
- `K60MODEM qrtr: dms revision`（S4）出现；
- `verdict ok`（S5）出现；
- `bridge enabled` 与 COACHZ 发布（S6）出现；
- 无 panic、无永久 VM map 删除、服务数不回落。

判读顺序：

| 现场 | 结论 |
|---|---|
| EFS 4 KiB 全对，但无 PAS4/RF/QMI | 不是传输问题；查 modem 固件/EFS 版本或 PAS4 之后的门禁 |
| EFS 字节错，PAS4 未到 | 先修 offset/LUN/window，不要用「RF 没起来」解释字节错 |
| `rmtfs rw … refused` | 查 PongUfs/窗口/LUN；这不是 F3 的 RF 问题 |
| 服务数 >2 但 EFS 字节错 | 下游起来了也不能宣布 EFS 通；W2 仍然失败 |

### 11.4 F3 的前置与边界

- F3 需要 `PongUfs` 进 27 package、`QcomBaseband` 进 include/archives、27 data-mount 锚点落地；这三件不在本文范围，由 Lead 排。
- stage-0 仍有三条必需 blocker：`loader-rejects-fileset`、`prelink-map-unresolved`、`firmware-fileset-provider`（Lead `6bab6b9a`）。F3 之前没有飞行窗口；本节只定义证据顺序，不声称现在可飞。
- 本节只写判据，不改代码、不构建、不上机；W1 仍 PENDING，W2 的完整 4 KiB 仍是待采集项。
