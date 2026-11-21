# W1 / W2 / F3 一次只读采集执行单

- 日期：2026-11-21
- 适用：K60 已启动 Android、adb 可用；**只读**，不 build、不 boot、不 flash、不写任何块设备。
- 本单回答：W1 的控制器 LUN；W2 的四个 storage 首 4 KiB 是否仍是独立参照；F3 的 Android 侧基线。
- **执行人：只有 Lead 在设备上执行。** 本单不授权 cellular agent 执行 adb，也不授权 build、boot 或 flash；Lead 执行前先确认设备已在 Android 且 adb 可见。
- **顺序固定：W1 两腿 → W2 四块 → F3 基线。** 不得跳步、不得并行、不得用后面的结果补前面的结论。
- **本单不能单独关闭 F3。** F3 的定案行只存在于 27 console；本单的 F3 段只采基线并把 F3 保持 `PENDING`。见 §7.2。
- 判据来源：[`21-IOS27-W1-AND-BLOCKER-REVIEW.md`](21-IOS27-W1-AND-BLOCKER-REVIEW.md)、[`22-W1-READONLY-CAPTURE.md`](22-W1-READONLY-CAPTURE.md)、[`23-W2-FULL-SUPERBLOCK.md`](23-W2-FULL-SUPERBLOCK.md)。

## 0. 先读：判定规则

1. **只有 PASS 才继续。** 任何一步的判官返回非 0、任何一项不等于期望值、任何缺腿或 `PENDING`，都立即停止。
2. `PENDING` 不是 PASS，也不是“先跳过”；缺 bsg、缺工具、短读、缺 QRTR 表都属于这一类。
3. 失败后保留整个 `CAP`，在 `STOP.txt` 写“停在哪一步、原始输出、判官原文、RC”。不要删文件、不要改描述符字节、不要改 `--expect-lun` 让灯变绿。
4. **整条作废**：只要 W1 或 W2 有一段不是 PASS，就不许继续到下一段，也不许把后面的结果拿来补前面的结论。W1/W2 已 PASS、F3 只是基线的，按 §7.4 单独写“W1/W2 通过，F3 PENDING”。
5. **复位规则**：本单没有任何一步需要设备复位。W1-A、W1-B、W2 四个 storage、F3-A 都在同一次 Android 启动里完成；`adb root` 只重启 adbd，不是设备重启。若设备真的重启，从 §1 重新开始并新建 `CAP`，不要往旧目录追加。
6. 本单的 `OVERALL: PASS` 只表示“W1 双腿 + W2 四块参考内容 + 本地文件互相一致”，不表示 W2 的 27 读回已通过，也不表示可以起飞。
7. 每个会产生判据的命令上方都有 `# 定案：` 注释，写明它对应哪条判据的哪一半；变量赋值、`mkdir`、`stop` 和辅助 readlink 只是 plumbing，不产生判据。

## 1. 固定变量与设备身份

在**同一个 shell** 里执行下面整块；如果中途换 shell，先重跑本块，否则空变量会读到错误路径。

```sh
if [ -d /mnt/e/k60-work/evidence ]; then
  ROOT=/mnt/e/k60-work/evidence
  REPO=/mnt/e/k60-work/wt-k55
else
  ROOT=E:/k60-work/evidence
  REPO=E:/k60-work/wt-k55
fi
SERIAL="${SERIAL:-$(adb get-serialno 2>/dev/null | tr -d '\r')}"
[ -n "$SERIAL" ] || { echo "STOP: no adb serial"; exit 2; }
CAP="$ROOT/w1-lun-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CAP"
stop() { echo "STOP: $*"; echo "KEEP: $CAP"; exit 2; }

# 定案：确认设备处于 adb device 态；fastboot/offline 直接排除本次采集。
adb devices -l                                              > "$CAP/adb-devices.txt" 2>&1
# 定案：记录 Android release，作为 CAP provenance；不是 W1/W2 判据。
adb -s "$SERIAL" shell getprop ro.build.version.release     > "$CAP/android-release.txt" 2>&1
# 定案：fingerprint 锁定这一次系统；换系统后同一 CAP 不可混用。
adb -s "$SERIAL" shell getprop ro.build.fingerprint         > "$CAP/fingerprint.txt" 2>&1
# 定案：hardware 记录板型；防止把别的设备当 K60。
adb -s "$SERIAL" shell getprop ro.boot.hardware             > "$CAP/hardware.txt" 2>&1
# 定案：内核串记录本次启动；后续 W2 读回必须同源。
adb -s "$SERIAL" shell uname -a                             > "$CAP/uname.txt" 2>&1
# 定案：记录 adbd 身份；W2 需要 uid 0，先留基线。
adb -s "$SERIAL" shell id                                   > "$CAP/id.txt" 2>&1
# 定案：飞行模式记录；F3 不能把无业务当 modem 死。
adb -s "$SERIAL" shell getprop persist.radio.airplane_mode_on > "$CAP/airplane.txt" 2>&1

{
  # 定案：README 给判官提供 provenance；缺它 W1 只能 PENDING。
  echo "purpose=W1/W2/F3 read-only capture"
  echo "captured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "adb_serial=$SERIAL"
  echo "source=Android adb read-only; no block-device write"
  echo "commands=docs/research/cellular/W1-W2-COLLECTION-RUNBOOK.md"
} > "$CAP/README.txt"
```

- **期望**：`adb-devices.txt` 里本机 serial 后是 `device`，不是 `fastboot`；`android-release.txt` 非空；`id.txt` 至少有 `uid=`。
- **取值范围**：serial 必须与后面 `adb -s` 用的完全一致；Android release 记录即可；`ro.boot.hardware` 记录即可。
- **对应判据**：provenance，不是 LUN/EFS 判据。
- **失败时看到什么**：`no adb serial`、`adb: device offline`、`error: no devices/emulators found`。看到任一就停，不要自行 `fastboot boot`。
- **复位**：不需要。若设备重启，回到本块。

<a id="W1"></a>

## 2. W1 Leg A：从 modemst1 绑到父磁盘，再读 HCTL 末段

```sh
# 定案：把 modemst1 解析到真实分区；父盘不是猜的。
adb -s "$SERIAL" shell "readlink -f /dev/block/by-name/modemst1" > "$CAP/modemst1-real.txt" 2>&1
# 定案：取第一行并去 CR；空值/多行会在这里暴露。
MODEMST=$(tr -d '\r' < "$CAP/modemst1-real.txt" | head -n 1)
case "$MODEMST" in
  /dev/block/sd[a-z]*) SDF=$(basename "$MODEMST" | sed -E 's/[0-9]+$//') ;;
  *) stop "modemst1 did not resolve to /dev/block/sd*: $MODEMST" ;;
esac
case "$SDF" in
  sd[a-z]) ;;
  *) stop "parent disk is not a whole sd disk: $SDF" ;;
esac
printf '%s\n' "$SDF" > "$CAP/sdf.txt"

adb -s "$SERIAL" shell "readlink -f /sys/class/block/$SDF"        > "$CAP/disk-sysfs.txt" 2>&1
adb -s "$SERIAL" shell "ls -l /sys/class/block/$SDF"              > "$CAP/disk-link.txt" 2>&1
# 定案：device-link 的末段就是 H:C:T:L；Leg A 的唯一地址来源。
adb -s "$SERIAL" shell "readlink -f /sys/class/block/$SDF/device" > "$CAP/device-link.txt" 2>&1
# 定案：第二份独立 HCTL；与 device-link 不一致就是 FAIL。
adb -s "$SERIAL" shell cat /proc/scsi/scsi                        > "$CAP/proc-scsi-scsi.txt" 2>&1
# 定案：lsblk 只是旁证；不参与 L=5 判定。
adb -s "$SERIAL" shell lsblk -o NAME,MAJ:MIN,SIZE,TYPE,PKNAME,MOUNTPOINT > "$CAP/lsblk.txt" 2>&1
# 定案：分区表也是旁证；不取代 HCTL 与 proc-scsi。
adb -s "$SERIAL" shell cat /proc/partitions                       > "$CAP/proc-partitions.txt" 2>&1

# 定案：归一成 H:C:T:L 四段；格式不对不能进判官。
tr -d '\r' < "$CAP/device-link.txt" | sed 's#.*/##' > "$CAP/hctl.txt"
HCTL=$(tr -d '\r' < "$CAP/hctl.txt")
printf '%s\n' "$HCTL" | grep -Eq '^[0-9]+:[0-9]+:[0-9]+:[0-9]+$' || stop "device-link has no H:C:T:L tail: $HCTL"
# 定案：Leg A 的一半就是 L=5；L 不等于 5 直接停。
L=${HCTL##*:}
[ "$L" = "5" ] || stop "HCTL L=$L, expected 5; do not change --expect-lun"
# 定案：Leg A 的另一半：proc 里同一 Lun；只有 device-link 不算通过。
grep -Eq "Host: scsi[0-9]+ Channel: [0-9]+ Id: [0-9]+ Lun: 0*5" "$CAP/proc-scsi-scsi.txt" \
  || stop "proc-scsi-scsi does not list Lun 05"
```

- **期望输出**：`device-link.txt` 只有一行，末段形如 `0:0:0:5`；`hctl.txt` 为 `0:0:0:5`；`proc-scsi-scsi.txt` 含 `Host: scsi0 Channel: 00 Id: 00 Lun: 05`。
- **取值范围**：H/C/T 非负整数，T 通常是 0；**L 是 0..31，本单期望 5**。不要把 T 当 LUN。
- **对应判据**：W1 Leg A；`check-w1-lun-evidence.py` 会要求 HCTL 元组与 `/proc/scsi/scsi` 完全一致。
- **失败时看到什么**：`readlink: ... No such file or directory`、空文件、末段不是四段整数、`L=0/4`、`proc-scsi-scsi` 没有 `Host: ... Lun:` 行或与该 HCTL 不一致。任一都停；L≠5 是“假设可能错”，不是可以改期望值的理由。
- **复位**：不需要。Leg A 与 Leg B 必须同一次启动；中间不要重启。

## 3. W1 Leg B：UFS Unit Descriptor（IDN 0x02）的 byte 2/3

```sh
# 定案：找 bsg/UPIU 节点；没有节点 Leg B 只能 PENDING。
adb -s "$SERIAL" shell 'ls -l /dev/bsg /dev/ufs-bsg* 2>/dev/null' > "$CAP/bsg-nodes.txt" 2>&1
# 定案：选一个可查询的 bsg 节点；空值停。
BSG=$(adb -s "$SERIAL" shell 'ls -1 /dev/bsg/* /dev/ufs-bsg* 2>/dev/null | head -n 1' | tr -d '\r')
[ -n "$BSG" ] || stop "no bsg node; Leg B PENDING, not PASS"
printf '%s\n' "$BSG" > "$CAP/bsg.txt"

# 定案：找能发 UPIU query 的工具；sg_inq VPD 不能替代。
UFS_TOOL=$(adb -s "$SERIAL" shell 'command -v ufs-utils || command -v ufs-tool' | tr -d '\r' | head -n 1)
[ -n "$UFS_TOOL" ] || stop "no ufs-utils/ufs-tool; Leg B PENDING, not PASS"
printf '%s\n' "$UFS_TOOL" > "$CAP/ufs-tool.txt"
# 定案：记录工具哈希，保证描述符来源可追溯。
UFS_TOOL_SHA=$(adb -s "$SERIAL" shell "sha256sum '$UFS_TOOL' 2>/dev/null" | awk '{print $1}' | tr -d '\r')
printf '%s\n' "${UFS_TOOL_SHA:-unknown}" > "$CAP/ufs-tool-sha256.txt"

# 定案：这条直接读回 IDN 0x02 的 byte2/3；Leg B 的字节来源。
adb -s "$SERIAL" shell "$UFS_TOOL desc -t 2 -i 5 -s 0 -r -D /data/local/tmp/unit-desc-L5.bin -p $BSG" \
  > "$CAP/unit-desc-L5.txt" 2>&1

# 只有出现 Permission denied/EACCES 时才允许 adb root；它只重启 adbd，不是设备复位。
# 定案：只有 EACCES 才提权；提权失败仍是 PENDING，不是 PASS。
if grep -qiE 'permission denied|EACCES' "$CAP/unit-desc-L5.txt"; then
  adb -s "$SERIAL" root > "$CAP/adb-root.txt" 2>&1 || true
  adb -s "$SERIAL" wait-for-device
  [ "$(adb -s "$SERIAL" shell id -u | tr -d '\r')" = "0" ] \
    || stop "desc needs root but adb root is unavailable; Leg B PENDING"
  adb -s "$SERIAL" shell "$UFS_TOOL desc -t 2 -i 5 -s 0 -r -D /data/local/tmp/unit-desc-L5.bin -p $BSG" \
    > "$CAP/unit-desc-L5.txt" 2>&1
fi

# 定案：把描述符原样落到 host，判官才能逐字节读。
adb -s "$SERIAL" pull /data/local/tmp/unit-desc-L5.bin "$CAP/unit-desc-L5.bin" \
  > "$CAP/unit-desc-pull.txt" 2>&1
[ -s "$CAP/unit-desc-L5.bin" ] || stop "unit descriptor was not pulled; Leg B PENDING"
# 定案：前五字节就是判据；od 只读，不改字节。
od -An -tx1 -N16 "$CAP/unit-desc-L5.bin" > "$CAP/unit-desc-L5-hex.txt" 2>&1
```

头部逐字节判读：

| byte | 字段 | 期望 | 取值范围 | 判据 |
|---|---|---|---|---|
| 0 | `bLength` | 常见 `0x2d`/`0x30` | ≥5 且 ≤ 文件长度 | 短于 5 或大于文件长度 ⇒ FAIL |
| 1 | `bDescriptorIDN` | `0x02` | 必须 `0x02` | 其它值 ⇒ FAIL |
| 2 | `bUnitIndex` | `0x05` | 必须等于 Leg A 的 L | 不等 ⇒ FAIL（真实矛盾） |
| 3 | `bLUEnable` | `0x01` | 0 或 1 | `0` 或其它 ⇒ FAIL |
| 4 | `bBootLunID` | 0 | 0..2 | >2 ⇒ FAIL；**不是 LUN 编号** |

- **期望输出**：`unit-desc-L5-hex.txt` 形如 `2d 02 05 01 00 ...`。
- **对应判据**：W1 Leg B；`bUnitIndex` 必须等于 HCTL 的 L，`bLUEnable=1`。
- **失败时看到什么**：`no bsg node`、`no ufs-utils/ufs-tool`、`Permission denied` 且 root 不可用、`desc` 返回非 0、pull 后 0 字节、`byte1 != 02`、`byte2 != 05`、`byte3 != 01`。遇到任一都停；**不要用 `sg_inq` 的 VPD 页替代 UPIU query**。
- **复位**：不需要。`adb root` 只重启 adbd；重启后 `wait-for-device` 再继续同一 CAP，不要重启设备。

## 4. W1 封口：写 README、跑判官

```sh
{
  # 定案：README 是判官的 provenance 输入；没有它 PASS 不成立。
  echo "capture_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "adb_serial=$SERIAL"
  echo "build_fingerprint=$(tr -d '\r' < "$CAP/fingerprint.txt")"
  echo "android_release=$(tr -d '\r' < "$CAP/android-release.txt")"
  echo "kernel=$(tr -d '\r' < "$CAP/uname.txt")"
  echo "modemst1_link=$MODEMST"
  echo "parent_disk=$SDF"
  echo "hctl=$HCTL"
  echo "bsg=$BSG"
  echo "ufs_tool=$UFS_TOOL"
  echo "ufs_tool_sha256=${UFS_TOOL_SHA:-unknown}"
  echo "commands=docs/research/cellular/W1-W2-COLLECTION-RUNBOOK.md"
} > "$CAP/README.txt"

cd "$REPO" || stop "repo not found: $REPO"
# 定案：判官把 A/B/README/proc 合成一个 rc；rc=0 才是 W1 PASS。
python3 scripts/check-w1-lun-evidence.py "$CAP" --expect-lun 5 > "$CAP/w1-judge.txt" 2>&1
W1RC=$?
cat "$CAP/w1-judge.txt"
[ "$W1RC" -eq 0 ] || stop "W1 judge rc=$W1RC; W1 is not PASS"
```

- **期望输出**：`K60 W1 LUN PASS expect=5 hctl=0:0:0:5 descriptor=index=5 enable=1 bootlun=0 readme=present`，`W1RC=0`。
- **对应判据**：Leg A 的 L=5；Leg B 的 index=5、enable=1；README 非空；`/proc/scsi/scsi` 若存在必须列出同一 HCTL。
- **失败时看到什么**：`K60 W1 LUN PENDING ...`（rc=2；缺腿或 README 空）、`K60 W1 LUN FAIL ...`（rc=1；HCTL/描述符矛盾、IDN 错、短读、proc 不一致）。**rc=2 也停**，不要补猜。
- **复位**：不需要。W1 通过后直接进 W2；中间不要重启，否则重跑 §1。

<a id="W2"></a>

## 5. W2：四个 storage 各读 4096 字节

W2 需要读块设备；先确认 adbd 是 root。`adb root` 只重启 adbd，不是设备复位。

```sh
# 定案：块设备读取要 uid 0；没有 root 不能读，不能假装通过。
ROOT_UID=$(adb -s "$SERIAL" shell id -u | tr -d '\r')
if [ "$ROOT_UID" != "0" ]; then
  adb -s "$SERIAL" root > "$CAP/w2-adb-root.txt" 2>&1 || true
  adb -s "$SERIAL" wait-for-device
  ROOT_UID=$(adb -s "$SERIAL" shell id -u | tr -d '\r')
fi
[ "$ROOT_UID" = "0" ] || stop "W2 needs uid 0; adb root unavailable"

# 定案：四个 storage 固定顺序；每个独立判 PASS/FAIL。
for spec in "1 modemst1" "2 modemst2" "3 fsg" "4 fsc"; do
  set -- $spec
  n=$1
  name=$2
  # 定案：by-name 解析证明读的是目标分区，不是别的 storage。
  adb -s "$SERIAL" shell "readlink -f /dev/block/by-name/$name" > "$CAP/storage$n-link.txt" 2>&1
  grep -q '^/dev/block/sd' "$CAP/storage$n-link.txt" || stop "storage $n ($name): no by-name block node"
  # 定案：唯一取数命令；4096 B 原样读，不做转换。
  adb -s "$SERIAL" exec-out "dd if=/dev/block/by-name/$name bs=4096 count=1" \
    > "$CAP/storage$n-$name.bin" 2> "$CAP/storage$n-dd.err"
  # 定案：长度是 W2 的第一半；短读/长读都停。
  bytes=$(wc -c < "$CAP/storage$n-$name.bin" | tr -d ' ')
  printf '%s\n' "$bytes" > "$CAP/storage$n-size.txt"
  [ "$bytes" -eq 4096 ] || stop "storage $n ($name): read $bytes bytes, need 4096"
  # 定案：完整哈希是 W2 的第二半；逐块对照参照。
  sha256sum "$CAP/storage$n-$name.bin" | awk '{print $1}' > "$CAP/storage$n-sha256.txt"
  # 定案：首 16 B 是 W2 的逐字节半边；od 只读。
  od -An -tx1 -N16 "$CAP/storage$n-$name.bin" | tr -d ' \n' > "$CAP/storage$n-head.txt"
  # 定案：判官把字段/padding/data/full sha 合起来；rc=0 才是该块 PASS。
  python3 scripts/check-efs-full.py --storage "$n" --file "$CAP/storage$n-$name.bin" \
    > "$CAP/w2-full-$n.txt" 2>&1
  rc=$?
  cat "$CAP/w2-full-$n.txt"
  [ "$rc" -eq 0 ] || stop "W2 storage $n judge rc=$rc; W2 is not PASS"
done
```

四个 storage 的独立参照（全部 4096 字节）：

| storage | by-name | 首 16 字节 hex | 完整 4096 sha256 |
|---|---|---|---|
| 1 | `modemst1` | `1000000003000000d801000020faa9c4` | `94c2aa725f4e8c5d3de317e8cd39f7efc1588866e7d2854011d10e4656a1a6bb` |
| 2 | `modemst2` | `1100000003000000d801000000026080` | `8610958511c22e7c44736363ac2b9c2d8e87bd16d78540fa2d4e97be1c489726` |
| 3 | `fsg` | `1400000003000000d801000000000000` | `e9a62f2a22e469b8008da4dc2733148ae4abcf887c9e1277a7646123fdbc31b4` |
| 4 | `fsc` | 32 个 `0` | `ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7` |

- **期望输出**：每块 `K60 EFS FULL PASS storage=N size=4096 sha256=... data_sha256=...`，rc=0。
- **取值范围**：文件必须**正好 4096 字节**；storage 1/2/3 的首 16 字节与上表逐字节相等；**storage 4 全零才是 PASS**，不是“没有数据”。
- **对应判据**：W2 完整 4 KiB 参考内容；storage 4 全零是正确形状，storage 1/2/3 全零是 FAIL。
- **失败时看到什么**：`PENDING ... need 4096`（短读）、`FAIL ... file is N bytes; expected exactly 4096`（长读）、`0x00 LE32 is 0x00000000, expected 0x00000010`（错 offset/错 storage）、`0x200..0xfff data sha256 ...`、`full 4096-byte sha256 ...`、`0x40..0x1ff is not all zero`。任一都停；不要为了变绿改参照表或补零。
- **复位**：不需要。四个 storage 必须同一次启动读完；中途重启就从 §1 重来。

## 6. 本地组合自检（不碰设备）

```sh
cd "$REPO" || stop "repo not found: $REPO"
# 定案：本地组合判官要求 W1 双腿+W2 四块+README 一致；不替代设备判官。
python3 scripts/check-capture-bundle.py \
  --leg-a "$CAP/device-link.txt" \
  --leg-b "$CAP/unit-desc-L5.bin" \
  --readme "$CAP/README.txt" \
  --proc "$CAP/proc-scsi-scsi.txt" \
  --efs-block "1=$CAP/storage1-modemst1.bin" \
  --efs-block "2=$CAP/storage2-modemst2.bin" \
  --efs-block "3=$CAP/storage3-fsg.bin" \
  --efs-block "4=$CAP/storage4-fsc.bin" \
  > "$CAP/bundle.txt" 2>&1
BRC=$?
cat "$CAP/bundle.txt"
[ "$BRC" -eq 0 ] || stop "bundle rc=$BRC; do not report OVERALL PASS"
```

- **期望输出**：`K60 CAPTURE BUNDLE PASS`；`W1 LUN PASS ...`；`W2 FULL PASS all four storages match`；`W2 CONSOLE SKIP no --console supplied`；`OVERALL: PASS`。
- **取值范围**：`W2 CONSOLE SKIP` 是预期的，因为本单不采 27 console；**它不是 W2 飞行 PASS**。`OVERALL: PASS` 只覆盖本地文件。
- **对应判据**：W1 双腿 + W2 四块 + 本地一致性。
- **失败时看到什么**：`W1 LUN PENDING/FAIL`、`W2 FULL PENDING missing storage N`、`W2 FULL FAIL storage=N: ...`、`OVERALL: PENDING/FAIL`。任一非 0 都停。
- **复位**：不需要；本段完全在 host 上。

<a id="F3"></a>

## 7. F3 只读查询：Android 基线，不是 27 定案

F3 的顺序是 **W1 → W2 → W3/W4 → PAS4/RF**。W1/W2 是“盘和字节”，F3 是“modem 是否接受并继续”。Android 只能给出 F3 的参照基线；27 的 F3 必须等 console。下面两段都只读。

### 7.1 F3-A：Android 侧基线（同一次启动，不需要复位）

```sh
# 定案：Android 基线，不是 27 F3；只用来排除 modem 根本没起。
adb -s "$SERIAL" shell getprop gsm.version.baseband       > "$CAP/f3-baseband.txt" 2>&1
# 定案：SIM 状态基线；两路 ABSENT 时 F3 基线不成立。
adb -s "$SERIAL" shell getprop gsm.sim.state              > "$CAP/f3-sim-state.txt" 2>&1
# 定案：运营商只记录，不作为 F3 通过条件。
adb -s "$SERIAL" shell getprop gsm.sim.operator.alpha     > "$CAP/f3-sim-operator.txt" 2>&1
# 定案：飞行模式基线；不能把无业务当 modem 死。
adb -s "$SERIAL" shell getprop persist.radio.airplane_mode_on > "$CAP/f3-airplane.txt" 2>&1
# 定案：四个 remoteproc 是 Android 侧 modem 是否运行的直接证据。
adb -s "$SERIAL" shell 'for i in 0 1 2 3; do echo "==$i"; cat /sys/class/remoteproc/remoteproc$i/name /sys/class/remoteproc/remoteproc$i/state /sys/class/remoteproc/remoteproc$i/firmware; done' \
  > "$CAP/f3-remoteproc.txt" 2>&1
# 定案：只读旧服务表；不运行 qrtr-lookup（它会写文件）。
adb -s "$SERIAL" shell 'cat /data/vendor/qrtr/qrtr-lookup.txt' > "$CAP/f3-qrtr-lookup.txt" 2>&1

# 定案：node0 行数判断表是否完整；少于 30 行不能当基线。
awk 'NF>=5 && $4==0 {n++} END{print "node0=" n+0}' "$CAP/f3-qrtr-lookup.txt"
# 定案：21/1/11/3/16 是 F3 关注服务号；缺一基线不完整。
awk '$4==0 && ($1==21 || $1==1 || $1==11 || $1==3 || $1==16) {print}' "$CAP/f3-qrtr-lookup.txt"
# 定案：mss/running/modem.mdt 三行同时出现，才证明 modem 真跑。
grep -A2 '4080000.remoteproc-mss' "$CAP/f3-remoteproc.txt"
# 定案：两路 baseband 才算双 SIM 基线；只有一份不完整。
grep -o 'MPSS.DE.2.0.c1-CN' "$CAP/f3-baseband.txt" | wc -l
# 定案：至少一路 LOADED；两路 ABSENT 则基线不成立。
grep -o 'LOADED' "$CAP/f3-sim-state.txt" | wc -l
```

- **期望输出 / 取值范围**：
  - `f3-baseband.txt`：两路都以 `MPSS.DE.2.0.c1-CN` 开头（本机 2026-11-20 基线为 `MPSS.DE.2.0.c1-CN-Jan 13 2026-02:08:51` 两份）；空或只有一份 ⇒ 基线不完整。
  - `f3-sim-state.txt`：`LOADED,LOADED`；至少一路 `LOADED` 才算 modem 有 SIM 基线，两路都 `ABSENT` ⇒ F3 基线不成立。
  - `f3-sim-operator.txt`：本机基线 `China Telecom,China Mobile`；只记录，不作为 F3 通过条件。
  - `f3-airplane.txt`：`1`；飞行模式开着时 Android 不发起数据/语音业务，F3 判读不能把“没有数据”当成 modem 死。
  - `f3-remoteproc.txt`：四个 `running`；必须看到 `4080000.remoteproc-mss`、`running`、`modem.mdt` 三行同时出现。缺一 ⇒ modem 在 Android 侧都没起，F3 基线不成立。
  - `f3-qrtr-lookup.txt`：node 0 至少 30 行，且包含 service `21`（EFS）、`1`（WDS）、`11`（UIM）、`3`（NAS）、`16`（PDS）；本机旧基线 36 行。文件不存在或 0 字节 ⇒ F3 基线 PENDING，**不要运行 `qrtr-lookup` 去补**（它会写 `/data/vendor/qrtr/qrtr-lookup.txt`，不是纯读）。
- **对应判据**：F3 的 Android 参照；不是 27 的 W3/W4。
- **失败时看到什么**：`getprop` 空、`Permission denied`、remoteproc 不是 `running`、`cat: ... No such file`、node 0 少于 30 行或缺 21/1/11/3/16。任一都停；写“F3 baseline PENDING”，不要把 Android 基线当成 27 F3 PASS。
- **复位**：不需要。F3-A 与 W1/W2 同一次启动；若重启，回 §1。

### 7.2 F3-B：27 console 的定案行（未来一次飞行，不是本单的设备命令）

只有拿到 27 console 后，才允许用下面这些**本地只读 grep** 判 F3。没有 console 就写 `F3 PENDING`，不要用 Android 结果补。

```sh
CONSOLE="${K60_CONSOLE:-}"
if [ -n "$CONSOLE" ] && [ -f "$CONSOLE" ]; then
  # 定案：W1 console 的一半：名字解析到 LUN 5；缺行 F3 PENDING。
  grep -nE 'K60UFS volume name=modemst1 lun=5' "$CONSOLE"
  # 定案：W2 console 的定案：27 读回首 16 B 与参照逐字节相等。
  grep -nE 'K60MODEM qrtr: rmtfs rw storage=1 direction=0 .*bytes=4096 head=1000000003000000d801000020faa9c4' "$CONSOLE"
  # 定案：W3 的一半：同一 storage 出现第二次 rw，才说明 modem 继续读。
  grep -nE 'K60MODEM qrtr: rmtfs rw storage=1 direction=0' "$CONSOLE"
  # 定案：W3 的另一半：fsg/fsc 也被打开，范围不是只读一块。
  grep -nE 'K60MODEM qrtr: rmtfs open path=/boot/(fsg|fsc)' "$CONSOLE"
  # 定案：W4 的定案：服务数/verdict/dms/bridge 至少出现；缺一 PENDING。
  grep -nE 'K60MODEM qrtr: (verdict|wait) |K60MODEM qrtr: dms revision|bridge enabled' "$CONSOLE"
else
  # 定案：没有 console 的负判据：只能写 PENDING，不能拿 Android 补。
  echo "F3 CONSOLE PENDING: no 27 console"
fi
```

| 行 | 期望 | 判据 | 失败/不足时 |
|---|---|---|---|
| W1 console | `K60UFS volume name=modemst1 lun=5 ...` | 名字解析到 LUN 5 | 缺行 ⇒ F3 PENDING；不要用 Android W1 代替 console 行 |
| W2 console | `rmtfs rw storage=1 direction=0 ... bytes=4096 head=1000000003000000d801000020faa9c4` | 27 实际读回的首 16 字节与 storage 1 参照逐字节相等 | 全零/不同 ⇒ FAIL；先查 offset/窗口，不要改 EFS 字节 |
| W3 | 同一 storage 第二次 `rmtfs rw` 且 offset 不同；`fsg`/`fsc` 也 open | modem 接受 EFS 并继续读 | 只有一次读 ⇒ PENDING；不是传输 PASS |
| W4 | `wait ... services=` 从 2 涨到 >2，或 `verdict ok`；`dms revision`；`bridge enabled` | QMI/QRTR 下游起来 | 缺任一 ⇒ PENDING；不能反推 W2 字节正确 |
| 事故 | 无 panic、无 `permanent VM map` | F3 没把内核打死 | 出现即停，先查 panic，不要继续 RF 结论 |

**F3 的 PASS 条件**：W2 console 的 16 字节匹配 **且** W3 出现第二次读/fsg+fsc open **且** W4 的服务数/verdict/dms 至少按上表出现；缺一条就是 PENDING。只有 W4 起来、W2 没验过，不能宣布“EFS 通了”。

### 7.3 `[[deferred]]` 触发查询：只查，不配对

四份 proposal 的 trigger 都是同一条 console 打印，不是设备命令：

```sh
# 定案：命中返回地址才证明 target 被执行；没命中保持 hold。
grep -nE 'fileset: original component called an unmapped kernel function from 0x[0-9a-fA-F]+' "$CONSOLE"
```

若命中，取 ptrauth-stripped 的返回地址（日志证明 slide 时才归一化到 output collection），按半开区间判：

| target | 区间 | 命中后 |
|---|---|---|
| `_proc_parent` | `0xfffffff00b0de068 .. 0xfffffff00b0de1d8` | 只配对该 target 到 `0xfffffff00788e194`，addend 0，how reviewed |
| `___memcpy_chk` | `0xfffffff00ad05978 .. 0xfffffff00ad059bc` | 只配对到 `0xfffffff0074f90c0` |
| `_pmap_claim_reserved_ppl_page` | `0xfffffff00b416214 .. 0xfffffff00b41624c` | 只配对到 `0xfffffff007525f24` |
| `_pmap_free_reserved_ppl_page` | `0xfffffff00b41624c .. 0xfffffff00b416284` | 只配对到 `0xfffffff007525f2c` |

- **期望**：现在没有一行；没有命中就是 `hold`，不改 map、不改 kit。
- **命中时**：停，回传 console 路径 + sha256 + 行号；由 Lead 复核后只落这一条。不要同时配另外三条。
- **baseline**：`IOS27-PRELINK-POLICY.json` 的 208 项（3 missing + 205 stubbed）保持可比；205→201 不是验收数字。

### 7.4 本单结束时的唯一合法结论

- W1 PASS + W2 四块 PASS + `bundle OVERALL: PASS`：写 **“W1 PASS；W2 参考内容 PASS；W2 27 读回与 F3 PENDING”**。
- F3-A 基线不成立：写 **“W1/W2 已采；F3 baseline PENDING”**，不要写 F3 FAIL（除非 remoteproc/modem 明确不运行）。
- 任何 W1/W2 非 PASS：写 **“本单作废，停在第 N 步”**，不许继续 F3，也不许把后续结果补前面。
- 只有 Lead 能把 W1/W2/F3 写进飞行账本；本单和脚本都不改共享树、不构建、不上机、不写 map。

## 8. 出错时只做这三件事

1. 把判官原文、RC、出错命令和 `CAP` 路径写进 `CAP/STOP.txt`。
2. 保留原始二进制和日志；不要手工截断、补零、改 byte 2/3、改 `--expect-lun`。
3. 把 `CAP`、`hctl.txt`、`unit-desc-L5-hex.txt`、`w1-judge.txt`、`w2-full-*.txt`、`bundle.txt` 交回 Lead；由 Lead 决定重采还是停查。

**一句话**：W1 先闭合“哪个盘”，W2 再闭合“这四个 4 KiB 是不是参照”，F3 只记录基线；任何一步不是 PASS 就整条停，绝不跳过。
