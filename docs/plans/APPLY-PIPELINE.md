# APPLY-PIPELINE — 生成并写入 iOS 16 的 OS 窗口

本文只讲一件事：把设备上 **stock 的 OS 窗口**替换成 Pong `apply()` 改过的
`pong-ios1661-system.cdr`。SHNGROOT、SystemOS、Data 一概不动。

设备当前（交接结论）的 OS 窗口从未跑过 `userland/build.py apply`，所以
`/sbin/launchd` 仍是 Apple 的 stock launchd，`/System/Library/LaunchDaemons`
仍是整份 stock 作业集。Pong 这一层做的事全部在 `apply()` 里：

- `/System/Library/{LaunchDaemons,NanoLaunchDaemons,LaunchAngels}`、
  `System/Library/xpc/launchd.plist{,sig}` 移到 `/pong/stock-config`
  （`UniXNU-pong userland/build.py:462-468`）；
- `System/Library/LaunchDaemons` 变成指向 `/pong/LaunchDaemons` 的符号链接，
  里面只有 `prepare()` 筛过的作业（`build.py:469`，筛选逻辑 `build.py:157-218`）；
- `/sbin/launchd` 改名为 `/sbin/launchd.ios`，原位置放 4 KiB 静态 init
  （`build.py:470`，init 由 `build.py:407` 编译）；
- `/System/Cryptexes/OS` 改指 `/private/preboot`，并补 dyld 缓存链接
  （`build.py:477-485`）；
- `private/var/staged_system_apps/*.app` 移到 `/Applications`
  （`build.py:486-492`）。

没有这些，launchd 走的是 stock 作业集和 stock 二进制，SIGSEGV 是预期结果。
**窗口内容变了，长度不变**：`prepare()` 用 `/bin/cp -c` 克隆原窗口
（`build.py:430-432`），`apply()` 只在这个副本上原地改（`build.py:449-508`），
所以产物的字节数必须等于设备窗口记录的长度。

---

## 0. 三步总览

| 步骤 | 在哪做 | 产物 | 设备侧影响 |
| --- | --- | --- | --- |
| ① 取得原始 OS 窗口镜像 | macOS（IPSW）或 recovery（设备读回） | `stock-os-window.cdr`，长度 = `OS.size` | 读回为只读 |
| ② `prepare` + `apply` | macOS runner（Actions） | `pong-ios1661-system.cdr` + sha256 + size | 无 |
| ③ 写回 OS 窗口 | recovery + adb | 设备 unixnu 的 OS 窗口字节 | 只写 `[OS.offset, OS.offset+OS.size)` |

第②步的 workflow 是 [`.github/workflows/ios16-os-window.yml`](../.github/workflows/ios16-os-window.yml)。

---

## 1. 需要的输入

| 输入 | 用途 | 20G81 / iPad7,1 的已知值 | 是否入库 |
| --- | --- | --- | --- |
| `OS` 组件（整盘镜像） | `--os-image`，也就是 OS 窗口本身 | `096-57366-083.dmg`：4,250,815,697 B，UDIF/LZFSE；`UDTO` 转 raw 后 5,096,113,664 B（9,953,347 扇区） | 否 |
| `Cryptex1,SystemOS` | `--system-cryptex`（挂载成目录，只读） | `096-56782-083.dmg`：2,665,480,192 B，本身已是 raw APFS（`NXSB@32`，无 UDIF 尾），等于 SystemOS 窗口长度 | 否 |
| Data 镜像 | 只作为 `apply()` 的可写 APFS 目标 | 可为空卷；真实种子非必需 | 否 |

本机已有的分量在 `E:\hackios\UniXNU\out\ipsw\20G81\`（`UniXNU` 的忽略输出目录，
不是仓库内容），同目录的 `096-*.dmg.json` 记录了成员名与长度。

Data 为什么可以合成：`prepare()` 只把 `--data-image` 克隆成
`pong-ios1661-data.cdr`（`build.py:430-432`），`apply()` 把从 **OS 镜像** 里
抽出的 `data-root` 合并进这个卷（`build.py:495-505`），其内容不会进入
`pong-ios1661-system.cdr`。所以 workflow 直接
`hdiutil create -size 512m -fs APFS` 造一个目标；要复现真实种子时再传
`data_image_url`。

`OS` / `Cryptex1,SystemOS` 的成员名由 IPSW 的 `BuildManifest.plist` 决定，
Pong 的本地文件名见 `UniXNU-pong scripts/build-userdata.py:35-38`；
成员解析方式见 `UniXNU-pong scripts/fetch-ios16-assets.py:143-167`
（按 `DeviceClass=j120ap`、`RestoreBehavior=Erase`、`ApChipID=0x8011`、
`ApBoardID=0xc` 选 identity，再取 `Manifest[component].Info.Path`）。

IPSW 下载地址（与 `UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml:12`、
`UniXNU-pong/board.toml [ipsw] url` 是同一个对象）：

```
https://updates.cdn-apple.com/2023SummerFCS/fullrestores/042-44385/366890C4-D9B5-4938-B399-C19FB58DBEE0/iPad_Pro_HFR_16.6.1_20G81_Restore.ipsw
```

大文件三种给法：workflow 用 HTTP range 从 URL 里只抽两个成员（默认）；
直接给三个分量的 URL（`source=urls`）；或把本机已抽出的
`os-image.dmg` / `systemos-image.dmg` 作为 artifact 上传后取用
（`source=artifact`）。仓库里不放 IPSW、不放 `.cdr`。

---

## 2. 第①步 A：从 IPSW 取 OS 窗口（macOS）

```sh
# 1. 只抽 BuildManifest 里 OS 与 Cryptex1,SystemOS 两个成员（workflow 已内置）。
# 2. OS 是 UDIF .dmg，窗口要的是整盘裸字节，用 UDTO 转 raw：
hdiutil convert -format UDTO -o stock-os-window "096-57366-083.dmg"
#    -> stock-os-window.cdr

# 3. 两个硬校验，缺一不可：
[ "$(dd if=stock-os-window.cdr bs=1 skip=512 count=8 2>/dev/null)" = "EFI PART" ] || echo "not a GPT disk"
stat -f %z stock-os-window.cdr        # 必须等于设备 SHNGROOT 里 OS.size
```

本机对 `096-57366-083.dmg` 的实测（`tools/apfs/dmg.py info`，只读）：

```
image size 5096113664 (5.10 GB) in 9953347 sectors
  3 chunks ignore, 2904 chunks lzfse, 313 chunks raw
  id=1 out=512+512 Primary GPT Header
  id=3 out=17408+5096079360 Apple_APFS
```

也就是：GPT 在 512，APFS 分区从 17,408 开始，整盘 5,096,113,664 B——
和 `docs/DATA-SPACE-2026-10-31.md:29` 记录的 OS 窗口长度一致。
镜像用 LZFSE 压缩，所以必须在 macOS 上用 `hdiutil` 解成 raw；顺带的好处是
`prepare()` 随后读的是裸 APFS 容器，不需要 Python 的 `lzfse` 模块
（`tools/apfs/apfs.py:232-256` 只在 UDIF 输入时才解压）。

SystemOS 的 `096-56782-083.dmg` 不是 UDIF：文件尾没有 `koly`，偏移 32 处直接是
`NXSB`，长度 2,665,480,192 B 就是窗口长度，直接挂载即可，不要再转一次。

`EFI PART@512` 不是可选项：`PongUfsTransport.cpp:589-594` 把 OS 窗口声明为
`{"OS", ..., "EFI PART", 512}`，`PongUfsTransport.cpp:418-431` 在发布磁盘前
读首块并比对签名，不匹配直接 `SHNGROOT window signature mismatch`。
SystemOS 窗口的签名是 `NXSB@32`，两者不要混。

尺寸的历史记录（来自 `docs/DATA-SPACE-2026-10-31.md:27-32` 的安装清单）：

| 窗口 | 分区内起点 | 长度 |
| --- | ---: | ---: |
| OS | 1 MiB（1,048,576） | 5,096,113,664 B |
| SystemOS | 4862 MiB | 2,665,480,192 B |
| Data | 7420 MiB | 258 MiB（GPT） |

这张表只是历史快照；**写之前必须用第 3 节的 SHNGROOT 实测值覆盖它**。

## 3. 第①步 B：从设备读回（recovery）

读回的意义有两个：确认设备窗口就是 stock（与 IPSW 转出的镜像 sha256 一致），
以及在窗口曾被改过时拿到真正的基线。

### 3.1 预检

```sh
ADB="adb -s 6033dbec"          # recovery ADB；自定义 server 端口时加 -P 5038
TARGET=/dev/block/by-name/unixnu

$ADB get-state                                  # 必须是 recovery
$ADB shell "readlink -f $TARGET"                # 例如 /dev/block/sda38
name=$($ADB shell "readlink -f $TARGET" | sed 's#.*/##')
parent=$($ADB shell "basename \$(dirname \$(readlink -f /sys/class/block/$name))")
$ADB shell "blockdev --getsize64 $TARGET"       # 34359738368
$ADB shell "cat /sys/class/block/$name/start"   # 53342976
$ADB shell "cat /sys/class/block/$name/size"    # 8388608
$ADB shell "cat /sys/class/block/$parent/queue/logical_block_size"  # 4096
$ADB shell "ls /sys/class/block/$name/holders"  # 必须为空
$ADB shell 'cat /proc/mounts' | grep -c unixnu  # 必须是 0
```

这些检查与 `scripts/install-k60-ufs-data.py:76-102` 完全同源；几何不符就停，
不要试着"绕过"。

### 3.2 解析 SHNGROOT，拿到 `OS_offset` / `OS_len`

```sh
$ADB exec-out dd if=$TARGET bs=4096 count=1 status=none > shngroot-before.bin

python3 - <<'PY'
import hashlib, struct
raw = open('shngroot-before.bin', 'rb').read()
assert len(raw) == 4096 and raw[:8] == b'SHNGROOT', 'no SHNGROOT header'
version, count, total = struct.unpack_from('<IIQ', raw, 8)
assert version == 1 and 2 <= count <= 4, 'unsupported manifest'
assert hashlib.sha256(raw[:4064]).digest() == raw[4064:], 'header checksum'
for i in range(count):
    name, off, size, block, flags = struct.unpack_from('<32sQQII', raw, 24 + 128 * i)
    print(name.split(b'\0')[0].decode(), 'offset=%d size=%d block=%d flags=%d' % (off, size, block, flags))
PY
```

格式与 `drivers/NativeUfs/RootLayout.h:162-215` 一致：`version@8`、`count@12`、
`imageBytes@16`、条目从 24 起每 128 字节，`name[32] offset u64 size u64
block u32 flags u32 sha256[32] reserved[40]`，头部校验在 4064。
`install-k60-ufs-data.py:104-120` 和 `install-pong-ufs-data.py:72-87` 读的是同一份结构。

### 3.3 读回窗口

```sh
OS_offset=1048576          # 用 3.2 打出来的值
OS_len=5096113664          # 用 3.2 打出来的值

$ADB exec-out dd if=$TARGET bs=4096 \
  skip=$((OS_offset/4096)) count=$((OS_len/4096)) status=none > stock-os-window.cdr
stat -c %s stock-os-window.cdr 2>/dev/null || stat -f %z stock-os-window.cdr
shasum -a 256 stock-os-window.cdr
```

Windows 主机注意：`adb exec-out` 是二进制流，**不要用 PowerShell 的 `>`**
（会按 UTF-16/CRLF 处理）。用 `cmd /c "adb ... > file"`、Git Bash 或 WSL。

读回长度必须恰好等于 `OS_len`；同一窗口两次读回的 sha256 要一致
（`scripts/inspect-k60-data.py` 的 capture 也是这么做的）。

---

## 4. 第②步：Actions 上 `prepare` + `apply`

### 4.1 输入

`workflow_dispatch`：

| 输入 | 说明 |
| --- | --- |
| `source` | `ipsw`（默认，HTTP range 抽成员）/ `urls` / `artifact` |
| `ipsw_url` | 默认 20G81 的 Apple URL |
| `os_image_url`、`systemos_image_url` | `source=urls` 时的直链 |
| `data_image_url` | 可选；空则造 512 MiB APFS |
| `expected_os_bytes` | 默认 `5096113664`；必须等于设备 `OS.size`，`0` 关闭校验 |
| `os_offset_bytes` | 默认 `1048576`；只用于 `artifact.json` 里报告的 dd 命令 |
| `artifact_mode` | `split`（默认，≤1900 MiB 分片）/ `whole` |
| `runner` | 默认 `macos-14` |

### 4.2 关键步骤与不变量

1. **转 raw**：`hdiutil convert -format UDTO`，校验 `EFI PART@512`，并断言
   字节数 = `expected_os_bytes`。
2. **挂载源**：OS 与 SystemOS 都以只读挂到临时目录，交给
   `build.py prepare --os-root ... --system-cryptex ...`（参数定义
   `build.py:547-549`）。`prepare()` 会再次校验两边都是 16.6.1 / 20G81
   （`build.py:397-402`），并检查 SystemOS 的 split dyld 缓存
   （`build.py:416-418`）。
3. **克隆**：`prepare()` 产出 `pong-ios1661-system.cdr` / `pong-ios1661-data.cdr`
   （`build.py:430-432`），并写 `build-plan.json`，其中 `os_source` 是原始
   镜像的绝对路径（`build.py:419-429`）。
4. **卸载源再 apply**：OS 源和它的克隆有相同的 APFS 卷 UUID，同时挂载通常会被
   diskarbitration 拒绝或混淆；workflow 在 `apply` 前 `hdiutil detach` 两个源挂载。
5. **apply**：`sudo` 下运行（`build.py:450` 要求 euid 0）。它会拒绝已存在
   `apply-complete.json` 的目录（`build.py:453`）和与源 `samefile` 的目标
   （`build.py:454-458`）。
6. **验收**（workflow 内置，失败即停）：
   - 产物长度仍等于 `expected_os_bytes`；
   - `EFI PART@512` 仍在；
   - `/sbin/launchd.ios` 存在，`/sbin/launchd` 是静态 init；
   - `System/Library/LaunchDaemons -> /pong/LaunchDaemons`；
   - `/pong/stock-config/LaunchDaemons` 保存了 stock 作业；
   - `System/Cryptexes/OS -> /private/preboot`；
   - dyld 缓存链接指向 `/private/preboot/System/Library/Caches/com.apple.dyld`
     （对应 `build.py:469-485`）。

### 4.3 产物

- `pong-ios1661-system.cdr`（或 `split` 分片 + `REASSEMBLE.sh`）
- `pong-ios1661-system.cdr.sha256`
- `pong-ios1661-system.cdr.size`
- `artifact.json`（含窗口 offset/size、目标设备、建议 dd 命令）
- `build-plan.json`、`apply-complete.json`、`jobs-report.json`

`split` 分片拼回：

```sh
sh REASSEMBLE.sh
# 等价于：cat pong-ios1661-system.cdr.part-* > pong-ios1661-system.cdr
```

---

## 5. 第③步：recovery + adb dd 写回

### 5.1 变量与前置断言

```sh
ADB="adb -s 6033dbec"
TARGET=/dev/block/by-name/unixnu
OS_offset=1048576          # 来自 3.2 的实测值
OS_len=5096113664          # 来自 3.2 的实测值
IMG=pong-ios1661-system.cdr
PARTITION_BYTES=34359738368

[ $((OS_offset % 4096)) -eq 0 ] || { echo "offset must be 4 KiB aligned"; exit 1; }
[ $((OS_len % 4096)) -eq 0 ]    || { echo "length must be 4 KiB aligned"; exit 1; }
[ $((OS_offset)) -ge 4096 ]     || { echo "offset inside the SHNGROOT header"; exit 1; }
[ $((OS_offset + OS_len)) -le $PARTITION_BYTES ] || { echo "window exceeds unixnu"; exit 1; }
[ "$(stat -c %s "$IMG" 2>/dev/null || stat -f %z "$IMG")" -eq "$OS_len" ] || {
  echo "artifact is not exactly OS_len bytes; the window record would be inconsistent"; exit 1; }
```

### 5.2 备份窗口头部（写前必做）

```sh
# 头部 8 MiB（足以覆盖 GPT 主表和一个 APFS 容器的开头）
$ADB exec-out dd if=$TARGET bs=4096 skip=$((OS_offset/4096)) count=2048 status=none > os-head-8MiB.bin
shasum -a 256 shngroot-before.bin os-head-8MiB.bin

# 可选但推荐：整窗备份（OS_len 字节，5 GB 级）
$ADB exec-out dd if=$TARGET bs=4096 skip=$((OS_offset/4096)) count=$((OS_len/4096)) status=none > os-window-before.cdr
```

回退时把 `os-window-before.cdr` 用同一套命令写回去即可；SHNGROOT 从未改动，
不需要改表。

### 5.3 分块写入（1 GiB/块，4 KiB 扇区）

```sh
split -b 1024m -d -a 2 "$IMG" os-part-
i=0
for part in os-part-*; do
  bytes=$(stat -c %s "$part" 2>/dev/null || stat -f %z "$part")
  [ $((bytes % 4096)) -eq 0 ] || { echo "$part is not 4 KiB aligned"; exit 1; }

  $ADB push -z lz4 "$part" /tmp/os-part.cdr
  seek=$(( (OS_offset + i * 1024 * 1024 * 1024) / 4096 ))
  count=$(( bytes / 4096 ))
  $ADB shell "dd if=/tmp/os-part.cdr of=$TARGET bs=4096 seek=$seek count=$count conv=notrunc,fsync"
  $ADB shell 'rm -f /tmp/os-part.cdr'
  i=$((i + 1))
done
$ADB shell sync
```

`conv=notrunc,fsync` 与 `-z lz4` 来自 Pong 的写入纪律：
`UniXNU-pong scripts/install-pong-ufs-data.py:170-173`、
`scripts/install-k60-ufs-data.py:154-157`。分块是为了不把 5 GB 塞进
recovery 的 `/tmp`（`install-pong-ufs-data.py:38-39,146-175` 的 `--chunk-mib`
就是同一个理由）。

**写成整盘绝对块时**（目标是 `/dev/block/sda`，不是分区节点）：

```
绝对块 = 53342976 + OS_offset / 4096
```

`53342976` 是 unixnu 在 LUN 0 上的起始 4 KiB LBA
（`scripts/install-k60-ufs-data.py:21-24`，即 `FIRST_4K`）。按默认
`OS_offset=1048576` 算：`53342976 + 256 = 53343232`。

```sh
ABS=$((53342976 + OS_offset / 4096))
$ADB shell "dd if=/tmp/os-part.cdr of=/dev/block/sda bs=4096 seek=$ABS count=$count conv=notrunc,fsync"
```

推荐还是写分区节点（`$TARGET`，相对 seek）：范围天然被分区截断，和
`install-k60-ufs-data.py:155-157` 的写法一致。

### 5.4 写后校验

```sh
# 1) SHNGROOT 头没变
$ADB exec-out dd if=$TARGET bs=4096 count=1 status=none | shasum -a 256
shasum -a 256 shngroot-before.bin          # 两个值必须相同

# 2) 窗口首块仍是 GPT：EFI PART @ 512
$ADB exec-out dd if=$TARGET bs=4096 skip=$((OS_offset/4096)) count=1 status=none > os-first-4k.bin
dd if=os-first-4k.bin bs=1 skip=512 count=8 2>/dev/null; echo    # 期望 EFI PART

# 3) 整窗回读 sha256，与本地 artifact 比对
$ADB exec-out dd if=$TARGET bs=4096 skip=$((OS_offset/4096)) count=$((OS_len/4096)) status=none | shasum -a 256
shasum -a 256 "$IMG"
```

三步都过才算写完；任何一步不一致都按 5.2 的备份回退，不要继续启动。

---

## 6. 安全边界

- **只写 OS 窗口**：`[OS_offset, OS_offset+OS_len)`。`dd` 的 `seek/count`
  由 5.1 的断言限死；不 `dd` 头部块（offset 0），不碰 SystemOS（4862 MiB 起）
  和 Data（7420 MiB 起）。
- **不动 SHNGROOT**：不重写头部、不改 `imageBytes`、不改窗口表。头部只在
  5.4 里读出来比对。
- **不动其它分区**：目标固定 `unixnu`；不 `fastboot flash`，不 erase，
  不碰 `persist`。
- **写前必须有备份**：至少 `shngroot-before.bin` + `os-head-8MiB.bin`；
  第一次写整窗时建议连 `os-window-before.cdr` 一起留。
- **长度必须相等**：窗口记录是 `size`，不是"最多这么大"。多出的字节会被
  `count` 截断，少写的字节会留下 stock 尾部——两种都不允许，5.1 直接拒绝。
- **源与目标版本一致**：`prepare()` 已经强制 OS 根与 SystemOS 都是
  16.6.1 / 20G81（`build.py:397-402`），不要拿别的 restore 拼。

---

## 7. 当前缺口

- 两个 20G81 分量本机已有（`E:\hackios\UniXNU\out\ipsw\20G81\`），但本机是
  Windows，没有 `hdiutil`/Xcode，`prepare`/`apply` 只能在 Actions 或一台真实
  Mac 上跑。workflow 还没有实际跑过一次，`pong-ios1661-system.cdr` 尚未产出。
- 设备当前的 SHNGROOT 没有在本次工作中重新读回；`OS_offset=1048576`、
  `OS_len=5096113664` 分别来自 `docs/DATA-SPACE-2026-10-31.md:29` 的历史记录
  和 `dmg.py info` 的镜像长度。写前必须用 3.2 的脚本实测确认。
- `apply()` 需要在 macOS 上以 root 跑 `hdiutil`；第③步需要 recovery ADB
  （serial `6033dbec` 只是历史值，按实际设备改）。
- 写回后能否让 launchd 不再 SIGSEGV 取决于 Pong 的作业筛选与 init，
  本文只保证 OS 窗口里是 `apply()` 之后的字节；启动结果要单独记录。
