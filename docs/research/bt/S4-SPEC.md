# S4 — 蓝牙固件随内核下发（kernel-embedded blob）

状态（2026-11-15 04:54）：**通道已换**。原方案（payload 的 `<kernel>.gpuaddon` 槽 + DarwinBoot 拷进 boot
window + `/chosen/memory-map/GpuAddon`）被真机否证（P-197：固件根本没有这个拷贝器，两次上机都只有一行
`addon: unusable range 0 0`）。现在固件走 Metal 那条已验证的路：**`.incbin` 汇编嵌进内核**，
镜像 `bt-s4b-20261115b`（受控正向）与 `bt-s4c-20261115a`（同基线负向）已构建并离线核验
（`boot.img` `2402def9…` / `535c395a…`），**上机仍未做**，⑦ 仍是 `done = false`。

## 0 一句话

S4 不需要把 106 个 QCA 文件写进 `/private/var/ngpu/firmware/qca`，也不需要固件配合：`scripts/gen-k60-bt-blob.py`
把 NGPUADD2 容器写成 `k60_bt_blob.s`（`.incbin` + 长度常量），`0510` 把这个文件编进内核，
`k60_bt_addon_load()` 优先读链接进来的 `k60_bt_blob`，读不到才回落老的 devicetree 路径。
整条链路**不需要**改固件、不需要 Data seed、不需要 zlib、不需要新 DXE。

## 1 为什么这是唯一可行的通道（排除表）

| 候选通道 | 结论 | 证据 |
|---|---|---|
| Data seed 里的 `/private/var/ngpu/firmware/qca` | **不存在**。bring-up 构建根本没有 Data seed | `/opt/k60/trees/k60build/bt-out/mondrian/ipados-16.6.1-20G81/mondrian/payload/payload.json`：`data_ramdisk_sha256 = null`（`gpu_addon_sha256` / `trust_cache_sha256` 同样是 null）；`bt-s2-20261114b/build-manifest.json` 的 `components` 里没有 data 项 |
| 内核 seed 写入器（照 0610 的 `k60_metal_seeds.c`） | 可行但更贵：要先建目录，再写 106 个文件 | `0398-k60-pong-runtime-directories.patch` 的 `k60_mkdir_paths[]` 只有 `/private/var/ngpu`、`/private/var/ngpu/addons`、`/private/var/ngpu/daemons`，没有 `firmware` 前缀；`0610-k60-metal-seeds.patch` 的 `k60_metal_seed_write()` 是逐文件 vnode 写入 |
| 内核内嵌 hex blob（照 0391/0401） | 弃用：102 万字节 → 约 2.3 MB 补丁文本，会成为仓库最大补丁 | `0391`（35 KB blob）195,794 B；`0401`（1.6 MB blob）1,668,068 B；六个规范文件 raw 373,320 B → 12 B/行 hex ≈ 2.3 MB |
| 内核侧 zlib 解压 | **不可能**：PONG 内核没编 zlib | `libkern/conf/files` 有 `OPTIONS/zlib optional zlib`，但 `nm kernel.development | grep -i inflate` 为空，构建树里也没有 `zlib/*.o` |
| `.incbin` 汇编嵌入 | 本构建系统不支持 | `bsd/conf/files` / `iokit/conf/files` / `osfmk/conf/files` 里没有任何 `.s` 条目；wifi 的 `.incbin` 只因为它由独立脚本用 `xcrun clang` 编成 kext 归档 |
| 在 Linux 上编辑 Data seed | 工具只读 | `tools/apfs/apfs.py` 没有 write/create/insert；`scripts/k60-make-data-seed.py:116` 直接 `SystemExit('this script needs macOS hdiutil and diskutil')` |
| NGPUADD2 的"内核消费者" | **从来不存在**：`zzy-native-gpu-addon-mount.patch` 是 bindfs 联合挂载，不是容器解析器；`native_gpu_addon_write` 只有调用点（`zzyb-native-cryptex-os-view.patch:160`），定义在哪都不存在；两个 zzy 补丁都不在 `patches/xnu/series` | `grep -rn 'native_gpu_addon_write|NGPUADD2' patches/` 只命中那一行调用 |

真正的通道是**启动镜像**本身：DarwinBoot 已经从 payload FAT 里读 `<kernel>.gpuaddon`。

## 2 旧通道机制（**已被 P-197 否证，留档对照**）

> 下面六条是 2026-11-14 的"逐行证据"，其中第 3–4 条是**假设**：`DarwinBoot.c:588-651` 里没有
> 任何 `addon` 字样（`git grep -ci 'addon' HEAD` 在 uefi-mondrian 零命中），那 64 行是
> `WritePongRam` 与启动流程。真机证据：`usblog-20261115-012913/console.log:192` 只有
> `[bluetooth] addon: unusable range 0 0`——ADT 单元存在但从未被填过地址。见 `PITFALLS.md:4720`（P-197）。

1. 构建期 `payload.py:215`：`if addon: shutil.copyfile(addon, payloads/'kernel.macho.gpuaddon')`。
2. `payload.py:224`：`generate(dtb, ctx.board, unique_chip_id=seed, data=..., trust=..., addon=bool(addon), ...)`；
   `devicetree.py:339`：`mappings += [('GpuAddon', bytes(16))] if addon else []` —— **ADT 里的 16 字节单元是自动生成的**，
   不需要改 `board.toml`。
3. `DarwinBoot.c:588`：`Status = ReadFile(Root, TreePath, SIZE_64MB, &Addon, &AddonSize)`（`EFI_NOT_FOUND` 容忍）；
   `:590-599` 校验 `NGPUADD2` 魔数、`AddonSize >= 24`、头部 `total == AddonSize`，且"有文件就必须有 ADT 单元"、
   "有单元就必须有文件"，否则 `EFI_COMPROMISED_DATA`。
4. `DarwinBoot.c:609`：`AddonAddress = ALIGN_VALUE(TrustCacheAddress + TrustCacheSize, SIZE_16KB)`，整块落在
   `WINDOW_SIZE = SIZE_256MB`（`:20`）里；`:646-651` `CopyMem` 后 `WriteUnaligned64` 把地址/长度写进 ADT 单元。
5. 内核侧读法就是 trust cache 的现成惯用法：`bsd/kern/kern_trustcache.c:772-773` `extern vm_map_address_t phystokv(pmap_paddr_t pa);`
   + `:823-836` `SecureDTLookupEntry(NULL, "chosen/memory-map", &memory_map)` → `SecureDTGetProperty(..., "TrustCache", ...)`
   → `phystokv(range->paddr)`。S4 只是把 `"TrustCache"` 换成 `"GpuAddon"`。
6. 类型定义：`pexpert/pexpert/device_tree.h:295-298` `typedef struct DTMemoryMapRange { vm_offset_t paddr; size_t length; } DTMemoryMapRange;`；
   `SecureDTLookupEntry` `:180`，`SecureDTGetProperty` `:249`，`kSuccess` `:129`。

## 3 容器格式

与 `scripts/make-gpu-addon.py:111` 完全一致：

```
b'NGPUADD2' + u32 count + u32 0 + u64 total(= 24 + len(body))
每个文件:
  u32 nameLen(含 NUL) | u32 mode | u64 size | u64 packedSize
  name 补到 8 字节对齐 | data 补到 8 字节对齐
```

蓝牙记录**不压缩**（`packedSize == size`）：内核没有 zlib，解析器遇到 `packed != raw` 直接返回 `-ENOENT`
（"A compressed record cannot be served"），绝不吐错误数据。

命名：容器内路径为 `qca/<name>`（如 `qca/hpbtfw20.tlv`），内核按 basename 匹配，同时剥掉请求里的 `qca/` 前缀，
所以 `ka60_firmware_get()` 传入的 `qca/hpbtfw20.tlv`、`hpbtfw20.tlv` 都能命中。

## 4 内核侧交付：`patches/bt/0004` = `patches/xnu/0510`（2026-11-15 改为内嵌 blob）

| 项 | 值 |
|---|---|
| 文件 | `patches/bt/0004-k60-bt-firmware-addon.patch` = `patches/xnu/0510-k60-bt-firmware-addon.patch`（字节相同） |
| 大小 / 行数 | 15,718 B，**289 增 / 1 删**，动两个文件：`bsd/dev/qbt_k60.c` 与 `osfmk/conf/files.arm64` |
| sha256 | `3309d123624bf4461a5ce4e6e197e613546af51ebc894967ad8084a21f7eaa87` |
| 接线 | `patches/xnu/series:208`（紧跟 `0509`，早于 audio 组） |
| 依赖 | 必须在 `0500`/`0507`/`0508`/`0509` 之后（基线就是打完全系列后的 `qbt_k60.c`）；`osfmk/conf/files.arm64` 的新行插在 `lz4_encode_arm64.s` 之后（**2026-11-16 从 `WKdmCompress_4k.s` 之后挪来**：那个位置正是 `0620-k60-adsp-blob.patch` 的上下文，先插会让 0620 的 `@@ -22,6 +22,7 @@` 对不上，整条 series 在 0620 处 `patch does not apply`） |

**这个补丁是怎么重做出来的**（可复现）：`0510` 只改 `bsd/dev/qbt_k60.c`，所以在空仓库里按序
`git apply --include='bsd/dev/qbt_k60.c'` 打 `0500`→`0501`→`0502b`→`0507`→`0508`→`0509` 得到 1871 行的基线，
再把旧 `0510` 打上去（`git apply -R --check` 通过即证明基线精确），然后在新基线上写内嵌 blob 的改动，
`git diff` 导出。主机侧用 `gcc -fsyntax-only -DK60_BT_HOST_TEST` 编译过（只剩两条既有的
`K60_QUP_HW_VER_REG` 重定义警告）。

改动六处：

1. `#if defined(__arm64__)` 里 `typedef uint64_t pmap_paddr_t __kernel_ptr_semantics;` + `extern vm_map_address_t phystokv(pmap_paddr_t pa);`
   —— `pmap_paddr_t` 的 typedef 在 `osfmk/arm/pmap_public.h:40`，被 `MACH_KERNEL_PRIVATE` 挡住，BSD 编译单元看不到，
   所以必须像 `bsd/kern/kern_trustcache.c:772-773` 那样连 typedef 一起声明（**第一版只写了 extern，真机构建在
   `qbt_k60.c:60: error: unknown type name 'pmap_paddr_t'` 处失败，host 测试发现不了这一类**）。
2. 容器常量 `K60_BT_ADDON_MAGIC/HEADER/MAX_BYTES/MAX_NAME`。
3. 纯解析器 `k60_addon_find()` + 内核装载器 `k60_bt_addon_load()` + 单条读取 `k60_bt_addon_read()`。
4. `k60_bt_firmware_read()` **先**试 addon，再走 vnode 根（`/private/var/ngpu/firmware/qca` → `/vendor/firmware` …）。
5. `qbt_k60_start()` 里在起线程前 `(void)k60_bt_addon_load()`：不管走哪条通道，都在 `bsd_init`
   就把固件准备好，工作线程起来时直接可用。
6. **新增（2026-11-15）内嵌 blob 通道**：`extern const uint8_t k60_bt_blob[];` +
   `extern const uint64_t k60_bt_blob_len;`（由 `k60_bt_blob.s` 提供），
   `k60_bt_addon_load_blob()` 校验长度/魔数/头部后把 `k60_addon_copy` 直接指向这段只读数据
   （**不拷贝、不释放**），成功即返回；`k60_addon_copy` 因此从 `uint8_t *` 变成 `const uint8_t *`。
   `k60_bt_addon_load()` 在 `k60_addon_status = -ENOENT` 之后第一件事就是调它，
   读不到（`k60_bt_blob_len == 0`，即构建时没带 `--bt-blob`）才走老的 devicetree 路径——
   所以负向对照仍然打印 `addon: no GpuAddon property`。

日志（全部走 `k60_log`，即 `[bluetooth] ...`，level ≤ 3 才打印）：

| 行 | 含义 |
|---|---|
| `addon: linked blob bytes=1027584 records=106` | **新**成功行：内嵌 blob 已校验并接管（`k60_addon_loaded()`） |
| `addon: loaded bytes records 1027584 106` | 旧通道成功行（devicetree 路径，留作回退） |
| `addon: serving 201560 0` | 命中一条（例：`hpbtfw20.tlv` 201,560 B） |
| `addon: no GpuAddon property` | ADT 没这个单元（构建时没带 `--gpu-addon`），属正常降级 |
| `addon: blob bad magic` / `blob bad header` / `bad blob length` | 内嵌容器与长度常量不一致（构建期 `test-k60-bt-blob.py` 本应先拦住） |
| `addon: unusable range …` / `bad header …` | 旧通道：DarwinBoot 写了单元但内容不合格（P-197 的实测症状） |
| `addon: bad magic` / `no kernel mapping` / `no memory for the copy` | 旧通道：容器或内存异常 |

## 5 构建侧（Lead 权限，未合并）

### 5.1 固件目录

构建需要两样东西，都不进 git（`.gitignore` 忽略 `/firmware/`、`*.bin`）：

```
firmware/bluetooth/manifest.json     # 只有 name → {bytes, sha256}，可以入库（需否定规则）
firmware/bluetooth/qca/<106 files>   # 厂商固件本体，永不入库
```

manifest 由 `scripts/stage-bluetooth-firmware.py`（草稿：`E:/k60-work/scratch/bt-s4/stage-bluetooth-firmware.py`，
已在 fakeroot 里跑通）从 `E:/k60-work/firmware/qca6490-bt`（113 文件 / 1,063,407 B）按内核白名单筛出 106 条生成；
被排除的 7 个名字内核永远不会请求：`hpbtfw20.ver`、`hpnv21.301`、`hpnv21.302`、`hpnv21_sony.302`、
`hpnv21g.301`、`hpnv21g.302`、`hpnv21g_sony.302`。

### 5.2 打包器（新文件 `scripts/make-bt-firmware-addon.py`）

下面这份是**已跑通**的版本（§6 的 106 记录端到端验证就是用它产出的容器），可以整段落盘：

```python
#!/usr/bin/env python3
"""Pack the Bluetooth firmware set into an NGPUADD2 addon for the boot image.

Why this exists (S4, 2026-11-14): a bring-up build has no Data seed at all
(payload.json data_ramdisk_sha256 = null), so the kernel reader's
/private/var/ngpu/firmware/qca root can never resolve.  DarwinBoot already
copies <kernel>.gpuaddon out of the payload FAT into the boot window and
publishes its runtime address in /chosen/memory-map/GpuAddon
(DarwinBoot.c:588-651); bsd/dev/qbt_k60.c reads that range before any vnode
root.  So the firmware rides the boot image.

Container = the one scripts/make-gpu-addon.py writes:
    b'NGPUADD2' + u32 count + u32 0 + u64 total
    per file: u32 nameLen (NUL included), u32 mode, u64 size, u64 packedSize,
              name padded to 8, data padded to 8
Bluetooth records are stored UNCOMPRESSED (packedSize == size) because the PONG
kernel links no zlib; the kernel reader rejects a compressed record instead of
serving garbage.

Usage:
    scripts/make-bt-firmware-addon.py OUT.bin [--source DIR] [--manifest FILE]
                                        [--prefix qca] [--list]

The source directory defaults to firmware/bluetooth/qca (the stage script's
output), the manifest to firmware/bluetooth/manifest.json.  Names are checked
against the kernel whitelist and against the manifest's bytes+sha256, so a
stale or half-copied firmware tree fails here instead of on the device.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b'NGPUADD2'
HEADER = 24
# Exactly the whitelist qbt_k60.c enforces (k60_firmware_name_ok).
NAME_RE = re.compile(r'(?:wcn)?(?:hp|ht)(?:btfw[0-9a-f]{2}\.tlv|nv[0-9a-f]{2}g?(?:\.bin|\.[b][0-9a-f]{2,4}))\Z')


def pad(data):
    return data + bytes(-len(data) % 8)


def read_manifest(path):
    document = json.loads(path.read_text())
    files = document.get('files')
    if not isinstance(files, dict) or not files:
        raise SystemExit(f'{path}: no files table')
    return document, files


def collect(source, prefix, files):
    rows = []
    for name in sorted(files):
        if not NAME_RE.match(name):
            raise SystemExit('Unsupported Bluetooth firmware name: ' + name)
        path = source / name
        if not path.is_file():
            raise SystemExit('Bluetooth firmware missing from the source: ' + str(path))
        data = path.read_bytes()
        expected = files[name]
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != expected['bytes'] or digest != expected['sha256']:
            raise SystemExit('Bluetooth firmware identity mismatch: ' + name)
        rows.append((prefix + '/' + name, 0o644, data))
    return rows


def build(rows):
    body = b''
    for name, mode, data in rows:
        encoded = name.encode() + b'\0'
        if len(encoded) > 160 or '..' in name.split('/') or name.startswith('/'):
            raise SystemExit('Bad addon path ' + name)
        body += struct.pack('<IIQQ', len(encoded), mode, len(data), len(data))
        body += pad(encoded) + pad(data)
    return MAGIC + struct.pack('<IIQ', len(rows), 0, HEADER + len(body)) + body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--source', type=Path, default=ROOT / 'firmware/bluetooth/qca')
    parser.add_argument('--manifest', type=Path,
                        default=ROOT / 'firmware/bluetooth/manifest.json')
    parser.add_argument('--prefix', default='qca')
    parser.add_argument('--list', action='store_true',
                        help='print the record names and exit')
    args = parser.parse_args()
    document, files = read_manifest(args.manifest)
    rows = collect(args.source, args.prefix.strip('/'), files)
    if args.list:
        for name, mode, data in rows:
            print(f'{mode:04o} {len(data):8d} {name}')
        return 0
    if args.output.exists():
        raise SystemExit('Refuse to overwrite ' + str(args.output))
    blob = build(rows)
    args.output.write_bytes(blob)
    print(f'Bluetooth addon: {len(rows)} records, '
          f'{sum(len(data) for _, _, data in rows)} bytes of firmware, '
          f'{len(blob)} bytes at {args.output}')
    print(f'Bluetooth addon sha256 {hashlib.sha256(blob).hexdigest()}')
    print(f'source {args.source} ({document.get("repository", "?")} '
          f'{document.get("commit", "?")})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

### 5.3 `scripts/build-strict.sh` 三处改动

```diff
@@ 用法注释
-#   scripts/build-strict.sh <tag> --fd <file.fd> [--kernel-arg NAME=VALUE ...]
+#   scripts/build-strict.sh <tag> --fd <file.fd> [--gpu-addon <file>]
+#                               [--kernel-arg NAME=VALUE ...]

@@ 参数解析
 FD=""
 KARGS=()
+ADDON=""
 while [ $# -gt 0 ]; do
     case "$1" in
         --fd) FD=${2:?--fd needs a file}; shift 2 ;;
+        --gpu-addon) ADDON=${2:?--gpu-addon needs a file}; shift 2 ;;
         --kernel-arg) KARGS+=("${2:?--kernel-arg needs NAME=VALUE}"); shift 2 ;;
         *) die "unknown argument: $1" ;;
     esac
 done
@@ 参数校验
 [ -f "$FD" ] || die "--fd $FD does not exist"
+if [ -n "$ADDON" ]; then
+    [ -f "$ADDON" ] || die "--gpu-addon $ADDON does not exist"
+fi

@@ payload 步骤（P-159/P-175 注释之后）
 PAYLOAD_CMD=("$BUILD/unixnu" build payload -D "$DEV" --out "$OUT" --kernel "$KERNEL")
+[ -z "$ADDON" ] || PAYLOAD_CMD+=(--gpu-addon "$ADDON")
 for kv in "${KARGS[@]:-}"; do

@@ manifest components
         "boot_img_path": "$RUN/boot.img",
+        "gpu_addon": "$(sha_or_empty "$ADDON")",
+        "gpu_addon_path": "${ADDON:-}",
```

（`unixnu build payload --gpu-addon` 是本框架已有的开关：`payload.py:144` `addon = expand(args.gpu_addon)`，
`:145-146` 校验 `NGPUADD2` 魔数，`:215` 复制为 `Payloads/kernel.macho.gpuaddon`，`:224` 给 ADT 加上 `GpuAddon` 单元。）

### 5.4 `.gitignore`

```diff
 /firmware/
+!firmware/bluetooth/
+firmware/bluetooth/*
+!firmware/bluetooth/manifest.json
```

### 5.5 三份补丁的落地文件

§5.2–§5.4 的三处改动已经导出成可直接 `git apply` 的补丁（在仓库外，供 Lead 合并）：

| 文件 | 目标 | 内容 |
|---|---|---|
| `/mnt/e/k60-work/scratch/bt-s4/lead/bt-lead-0001.patch` | 新增 `scripts/make-bt-firmware-addon.py` | §5.2 的打包器（100755） |
| `/mnt/e/k60-work/scratch/bt-s4/lead/bt-lead-0002.patch` | `scripts/build-strict.sh` | §5.3 的 `--gpu-addon` 转发 + manifest 记录 |
| `/mnt/e/k60-work/scratch/bt-s4/lead/bt-lead-0003.patch` | `.gitignore` | §5.4 的 `firmware/bluetooth/` 例外 |

三份都已在真实仓库上 `git apply --check` 通过；`0002` 还额外做了端到端验证（§6.2）。
**这三份已经由 Lead 合进 `main`**（`277e09e` + `dbc2cd5`），本分支重基后与之逐字节相同，不再作为待办。

### 5.6 内嵌 blob 的构建侧（2026-11-15，已提交 `ccd4dfc`）

Lead 在 P-197 之后直接指派本线做这一步，所以 `scripts/` 的这三处由本分支提交（不再是仓库外补丁）：

| 文件 | 改动 |
|---|---|
| `scripts/gen-k60-bt-blob.py`（新，6,794 B） | 把 NGPUADD2 容器写成 `.section __DATA,__const` + `.globl _k60_bt_blob` + `.p2align 3` + `.incbin "<绝对路径>"` + `.globl _k60_bt_blob_len` + `.quad <total>`；**不带 `--container` 时写一字节桩 + `.quad 0`**，让其它线的构建完全不受影响（内核看到长度 0 就回落到 devicetree 路径） |
| `scripts/tests/test-k60-bt-blob.py`（新，12,159 B） | 9 条夹具用例 + 真实产物模式 `--assembly <file> [--container <file>]`：核对长度常量 = 容器字节数、头部 total/count 自洽、每条记录 8 字节对齐且在界内、记录恰好铺满容器、`packed == size`（内核没有 zlib） |
| `scripts/build-xnu-4k-baseline.sh`（:311-324） | 在 metal blob 块之后新增 `0510` 的生成块：`K60_BT_ASM=$ROOT/.cache/xnu-work/osfmk/arm64/k60_bt_blob.s`，只在 `patches/xnu/0510-…` 存在时执行；`K60_BT_BLOB` 非空且文件存在才传 `--container`。生成器用 `"$ROOT/scripts/gen-k60-bt-blob.py"`（树内脚本，不写死别的检出路径，P-193） |
| `scripts/build-strict.sh` | 新参数 `--bt-blob <file>`（用法行 + 解析分支 + 存在性校验）；kernel 步骤前 `export K60_BT_BLOB` 并打印 `build-strict: bt blob <sha256> <bytes> bytes`；manifest 的 `components` 增加 `bt_blob` / `bt_blob_path`；boot.img 之后用 `test-k60-bt-blob.py --assembly <生成的 .s> --container <输入容器>` 核对这一对（失败即 `die`） |

生成位置为什么是 `$ROOT/.cache/xnu-work`：`unixnu build kernel` 调的是 **device mirror**（`K60_DEVICE_INPUT`）里的
`scripts/build-xnu-4k-baseline.sh`，那里的 `$ROOT` 就是镜像根；metal 的 `.s` 也写在同一个目录
（`build-xnu-4k-baseline.sh:305`），所以两者共用一条已被验证的路径。

## 6 离线验证（已完成，2026-11-14 10:20）

1. `gcc -fsyntax-only -std=gnu11 -Wall -DK60_BT_HOST_TEST …`：0 error；只有三条**既有**告警
   （`K60_QUP_HW_VER_REG` 重定义、`armcpu_spi_mask` 恒真、KERNEL-only 辅助函数未使用）。
2. host 自检：`qbt_k60 host checks passed`（时钟算术 4 条 + 解析器 5 条：两个名字命中、缺名 `-ENOENT`、
   截断缓冲 `-ENOENT`、坏魔数 `-ENOENT`）。
3. **端到端**：用 §5.2 的打包器把真实固件（`E:/k60-work/firmware/qca6490-bt`）打成容器
   → `addon 1,027,584 B`（106 条 / 1,022,742 B 固件），sha256 `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037`；
   再用同一个 `qbt_k60.c` 的 `k60_addon_find()` 逐条比对源文件字节：
   `addon check: 106 records verified, 0 bad`（另加"不存在的名字"和"坏魔数"两条否定用例）。
4. **第一次真机构建失败的教训**（2026-11-14 10:29，`bt-s4-20261114a`）：host 测试全绿，但内核构建报
   `bsd/dev/qbt_k60.c:60:34: error: unknown type name 'pmap_paddr_t'` 与 `:1323:39: error: use of undeclared identifier 'pmap_paddr_t'`。
   原因：`pmap_paddr_t` 的 typedef 在 `osfmk/arm/pmap_public.h:40`，被 `MACH_KERNEL_PRIVATE` 挡住；`vm/pmap.h`
   只给了 `pmap_find_phys` 的原型。修法就是照 `kern_trustcache.c:772-773` 连 typedef 一起声明。
   **结论：凡是从别的编译单元抄 extern，必须同时确认它用到的 typedef 在这个单元可见**；host 测试
   （`-DK60_BT_HOST_TEST` 走的是 shim 分支）永远不会发现内核侧的 include 缺口，只有真构建能发现。
5. 门禁：`check-docs.py` 绿；`check-rules.py` 在提交前只有 hard-10/hard-11/hard-33/P-165/P-166
   这几条"未提交/未同步构建输入"的预期红（提交并 `sync-device-input.py` 后复验）。
6. **真机构建已通过**（2026-11-14 10:41，tag `bt-s4-20261114b`，`--kernel-arg k60bt=1`）：
   `build-strict.sh` 跑完 `eight-step 通过 30 项检查` → kernel → payload → bootimg → manifest，退出码 0；
   `verify-boot-image.py` 报 `OK`。产物：`boot.img` sha256 `82ff78b49abaafd87fbe1ccea633df30f22e3d8adc52153ffe5d5d465e5af1bf`（201,887,744 B）、
   `kernel_built 9e8ae4107a1e7c9bfc0197cc4b21a5d27301119a30a3821d9a60ce5d511e2358`、
   `payload 570f61e9f18abc3b5845ed7d70221b2a485d462150495516e934d66e954e771d`、
   `adt 079cf3c76e5ffbc881325301b1d00891b38e2f910cce450e9ac601fcd46c589a`。
   **注意：这一版没有 `--gpu-addon`**（构建侧开关还没合并，见 §5.3），所以镜像里没有 `kernel.macho.gpuaddon`、
   ADT 里也没有 `GpuAddon` 单元——它只证明 0510 的内核代码能编译链接，S4a 的 `addon: loaded` 行不会出现。
   这一版恰好是 S4 的**负向对照**：`k60bt=1` 但没有 addon 时，应打印 `addon: no GpuAddon property`
   然后回落到 vnode 根（同样找不到固件），控制台必须仍然完整。
   代码确实进了内核：`strings -a kernel.macho` 各命中一次 `NGPUADD2`、`loaded bytes records`、
   `no GpuAddon property`、`addon: %s %llu %llu`（`chosen/memory-map` 6 次，其中 2 次是本补丁新增）。

## 6.1 负向对照（已完成，2026-11-14 10:26–10:31）

板子回来了（`adb devices` = `6033dbec  device`）。用 `bt-s2-20261114b` 做对照启动——它构建于 0510 之前，
镜像里**没有** addon 读取器，启动参数里也**没有** `k60bt`：

- 证据目录 `E:/k60-work/evidence/usblog-20261114-102611-797`，`capture.json` `state=captured-budget-complete`、
  `bytes=224240`、`panicMarker=null`、`resetMarker=K60 USBLOG: restart reason published`（`k60_autoreset=300` 正常复位）。
- 控制台里 `K60 BT` 行 0 条、`addon:` 行 0 条——这既因为该镜像没有 0510，也因为 `0508` 在没有 `k60bt=1` 时惰性。
  所以这条对照只证明"不带 k60bt 的普通启动仍然健康"（224,240 B 控制台、无 panic、正常 autoreset），
  **不能**用来判定 0510 的行为；0510 的负向对照要用 `bt-s4-20261114b` 再跑一次（未执行，见 §7）。
- 用户态仍报 `marconi-bt/bluetooth: Unable to match bluetooth service in device tree.`、
  `bluetoothd: No bluetooth on this device.`——S3 的 IORegistry 发布还没上机验证，这仍是 S3/S4 的待办。
- `record-boot.py` 已记账：series `f1c22d7d05bb1b17`（227 个补丁），129 条 SpringBoard 行。

## 6.2 正向镜像（已构建，2026-11-14 13:43–13:49）

用 §5.2 的打包器 + §5.3 的 `--gpu-addon` 开关做了**带固件的正向镜像**（**2026-11-15 起作废**：P-197 之后
固件不再走 payload 的 addon 槽，见 §6.4）。因为 `scripts/build-strict.sh`
的改动属 Lead 权限，本次构建用的是**仓库外的临时副本**：`/tmp/bt-s4a/scripts/build-strict.sh`
（= 仓库原文件 + `bt-lead-0002.patch`，只把 `REPO` 指回 `/mnt/e/hackios/k60-bt`）。

固件先落到仓库的 gitignore 区：`firmware/bluetooth/qca/` 106 个文件 1,022,742 B +
`firmware/bluetooth/manifest.json`（`git status --porcelain` 仍为 0 行，`.gitignore` 的 `/firmware/` 覆盖）；
打包器输出 `out/pong-bt-firmware.bin` 1,027,584 B，sha256
`febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037`（与 §6 第 3 条同一个容器）。

构建命令（**必须用隔离输出树**，见 `S1-PROBE-SPEC.md` §4.3）：

```bash
K60_OUT=/opt/k60/trees/k60build/bt-out-s1c \
K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device \
bash /tmp/bt-s4a/scripts/build-strict.sh bt-s4a-20261114c \
  --fd /mnt/e/k60-work/artifacts/fd/bt-s2-20261114b-cf4485712c29.fd \
  --gpu-addon /mnt/e/hackios/k60-bt/out/pong-bt-firmware.bin \
  --kernel-arg k60bt=1
```

结果：`build-strict.sh` 退出码 0（`eight-step 通过 30 项检查` → kernel → payload → bootimg → manifest），
`verify-boot-image.py --manifest` 报 `OK`，`check-image-args.py` 报 `OK (30 arguments, 583 bytes)`。

| 项 | 值 |
|---|---|
| boot.img | `f886223a33e4fad666de766d9739b998c9200cc3c010850391e5bce64ac7ae0f`（201,887,744 B） |
| kernel_built | `ba805e4c1027bdefa3d8bbcdc54e7e682a1727ee0a03cab815bea5c62c77a5f2`（54,185,984 B） |
| payload | `1e62d4819f1ba06e062ddf065c38fb49b7b31d361ceeb53a60744dfd5d995d40` |
| payload_kernel | `a92d7b1e494ce55fb0f03dcc990e40b9c06a26032a6afac0a363a3ae35c299c3` |
| adt | `c304361e317be2033f3e46bd69e19bfa6eb4384772ce545f3c95871cdd4929f1` |
| dtb | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| fd | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |
| gpu_addon | `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037` |

容器确实进了镜像（三项独立核对）：

1. payload FAT `::/EFI/UniXNU/Payloads` 现在 5 个文件，含 `kernel.macho.gpuaddon` **1,027,584 B**，
   余量 145,285,120 B。
2. 用 `mcopy` 把它取出来与 `out/pong-bt-firmware.bin` `cmp` → **逐字节相同**，sha256 一致。
3. payload 里的 `kernel.macho.adt`（15,788 B）`strings` 命中 `GpuAddon` 1 次、`TrustCache` 0 次、
   `PackedRAMDisk` 0 次、`RAMDisk` 0 次——正是 `devicetree.py:339` 只在给了 addon 时才加单元的预期。

内核侧代码同样在：`strings kernel.macho` 命中 `NGPUADD2` 1 次、`loaded bytes records` 1 次、
`no GpuAddon property` 1 次、`chosen/memory-map` 6 次。
（`addon: serving` 是格式化串 `addon: %s %llu %llu`，按字面搜不到，属预期。）

构建期的两个坑，都值得记：

- `K60_EIGHT_STEP_ITEMS=bluetooth` 被八步门禁直接拒绝（`EIGHT-STEPS.toml` 没有该硬件项，§8），
  所以本镜像构建时**不设**该变量，manifest 记 `eight_step_items = all`。
- `K60_OUT` 指到一个全新目录（`bt-out-s4a`）会立刻被 P-185 拒绝：
  `tree/.cache/fakeroot is missing: this output tree has never been built`。复用已 bootstrap 过的
  `bt-out-s1c` 才通过。**隔离不等于新建**：隔离的是一棵本线专用的树，不是每次一个新目录。

## 6.3 重基后的正向镜像（2026-11-14 23:47–23:57，`bt-s4a-20261114f`）

> **已作废（2026-11-15）**：P-197 证明固件不填 `GpuAddon` 单元，所以这一族镜像的期望行
> `addon: loaded bytes records …` 永远不会出现，实测只有 `addon: unusable range 0 0`。
> 当前正向镜像是 §6.4 的 `bt-s4b-20261115a`。本节留作"通道为什么换"的对照记录。

`main` 在 22:51–23:36 之间又落了三个门禁提交（`314497d`、`f02acff`，后者修了
`build-strict.sh` 里 `$ROOT`/`$M` 的 P-196 误判与 P-194 的"第一次构建没有 manifest"死锁），
本分支 `git rebase origin/main` 后重建成 `bt-s4a-20261114f`。它在 2026-11-14 晚间是推荐上机的 S4a 镜像
（`c` 构建于更早的重基之前，series 227）；2026-11-15 起被 §6.4 取代。

命令与 §6.2 相同，只是 harness 换成 `/tmp/bt-rb/scripts/build-strict.sh`（= 重基后的仓库文件 +
`bt-lead-0002.patch`，`REPO` 指回 `/mnt/e/hackios/k60-bt`），tag 用 `bt-s4a-20261114f`。

结果：退出码 0，`eight-step 通过 30 项检查` → `kernel d4e1bed3…` → payload → bootimg →
`✅ kernel archives: 4 enabled archive(s) all present` → `✅ k60_metal_blob.s: container table is
self-consistent` → `image-arg-audit: OK (30 arguments, 583 bytes)`；`verify-boot-image.py --manifest` 报 `OK`。
series 228，`frozen 82f4196a43a61dcacf28440b5fb393aefc4e7a7f1fc636d30fd2eea70e01a29a`。

| 项 | 值 |
|---|---|
| boot.img | `efe87cd79088c990558f44f4aa07d10dc5b01965b18aea4a5df7c6a3b79fef50`（201,887,744 B） |
| kernel_built | `d4e1bed3d8d729f4cd90e340ba70f3aa2c4bbd7cb48653158168bd0b2c658aee`（105,508,864 B） |
| payload | `567f1e3548933ddaa58d92c5751b071865c8ce976ce3dba598a09fbdd164ec7c` |
| payload_kernel | `7d4e23088215b9e6fd478f82df526fa94cb451c33cfdfb29ea4117868fb0e987` |
| adt | `a1b01484c052ffecd99d5ab80ba038a8773535942c210012a40f681291c0ab7c`（16,024 B） |
| dtb | `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd` |
| fd | `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` |
| gpu_addon | `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037`（1,027,584 B） |

manifest 的 `components` 现在有 `gpu_addon` 与 `gpu_addon_path` 两项（`bt-lead-0002` 带来的），
这正是把 addon 变成**可追溯构建输入**的关键：只写进 payload 而不写 manifest，镜像就不可复现。

三项独立核对（与 §6.2 同法，重基后重做）：

1. 树的 payload FAT `::/EFI/UniXNU/Payloads` 五个文件，含 `kernel.macho.gpuaddon` 1,027,584 B，余量 93,962,240 B。
2. `mcopy` 出来的 addon sha256 = `febdc20d…` = 打包器输出（逐字节相同）；ADT 16,024 B，sha256 与 manifest 一致。
3. ADT 里 `GpuAddon` 命中 1 次、`TrustCache` 0 次；内核 `strings` 命中 `NGPUADD2` 1 次、
   `loaded bytes records` 1 次、`no GpuAddon property` 1 次。

**P-190 的修复也在这一版里得到验证**：重基前注册表因 `CONFIG_XNU_K60_PHYSICAL_BATTERY=y` 却没有
`k60_physical_battery_start` 符号而拒绝构建（它想拦的正是"被 force_load 进死分支"）；重基后
main 的 `check-kernel-archives.py` 以符号为准，构建前判"树里没有内核，无可检查"（`skip: … configured
but not built`），构建后判 `✅ kernel archives: 4 enabled archive(s) all present`，
而 `llvm-nm-18 kernel.macho | grep -c k60_physical_battery_start` = 2。所以那条红是"树里的内核早于
`3c0e1e3`"，不是代码缺陷；把旧内核挪走后注册表即转绿（`失败 0 条`）。

## 6.4 内嵌 blob 的正向镜像（2026-11-15 03:26，`bt-s4b-20261115a`）

> **已被 §6.5 取代**：`a` 这一版的冻结输入里混进了两个 `scripts/__pycache__/*.pyc`，与负向对照
> 的冻结清单不一致，按 P-201 不能当对照判据。上机用 §6.5 的 `bt-s4b-20261115b`。

P-197 之后 S4 换了通道（§0/§2），`bt-s4a-*` 这一族**全部作废**：它们的 addon 只存在于 payload 槽里，
而固件不填那个槽。新镜像是 `bt-s4b-20261115a`，固件真的在 `.text` 旁边的 `__DATA,__const` 里。

命令（用 **main 自己的** `scripts/build-strict.sh`，没有本地补丁）：

```sh
K60_OUT=/opt/k60/trees/k60build/bt-out-s1c \
K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device \
bash scripts/build-strict.sh bt-s4b-20261115a \
  --fd /mnt/e/k60-work/artifacts/fd/bt-s2-20261114b-cf4485712c29.fd \
  --bt-blob /mnt/e/hackios/k60-bt/out/pong-bt-firmware.bin \
  --kernel-arg k60bt=1
```

结果：退出码 0，`eight-step 通过 30 项检查` → `bt blob febdc20d… 1027584 bytes` →
`kernel 4fce5d35…`（106,541,056 B，比 `f` 大 1,032,192 B ≈ 容器 + 对齐）→
`✅ kernel archives: 4/4` → `✅ k60_metal_blob.s` / `✅ k60_bt_blob.s: container table is self-consistent` →
`image-arg-audit: OK (30 arguments, 583 bytes)` → `verify-boot-image.py --manifest` `OK`。
series 228，`frozen b7572a96695a82d3d9f8a82931c8b312d791d1d07193fa78b5610e14bd51b009`。

| 项 | 值 |
|---|---|
| boot.img | `7ee92d515715de56d2845f632369203faac12df0090f0fbe1bcc606eb43d925d`（201,887,744 B） |
| kernel_built | `4fce5d35578edb80150d27ebb06791fb90407b82cb3a5eb8350151679ba66d02`（106,541,056 B） |
| payload | `3f7ae2c29402e7d9290c4fc5973d23e56e7ac19840c715a4131a7153bf97da3d` |
| payload_kernel | `c0e7da70b9f5f4d040a3c89a58aa9ae9a31be27a6774a7b257ff61d514579517` |
| adt | `69c0c97fdf476ed3925ee8bf4d978501e9a492d2f16b4d34f6500af243a24fb0` |
| dtb / fd | `2d044eaa…33cd` / `cf448571…5d0f`（与前几版相同） |
| bt_blob | `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037`（1,027,584 B） |
| bt_blob_path | `/mnt/e/hackios/k60-bt/out/pong-bt-firmware.bin` |
| gpu_addon | 空——**故意不传** `--gpu-addon`，证明固件只走内核内嵌这一条 |

四项独立核对，证明 blob 真的在核心里：

1. `llvm-nm-18 kernel.macho` → `fffffff0071b8818 S _k60_bt_blob` 与
   `fffffff0072b3618 S _k60_bt_blob_len`，两地址相差 1,027,584 = 容器字节数。
2. 在 `kernel.macho` 里按字节搜容器的前 4 KiB → 偏移 1,787,928；把该偏移起的 1,027,584 字节取出来算
   sha256 = `febdc20d…` = 打包器输出（逐字节相同）。
3. `strings kernel.macho` 命中 `addon: blob bad magic` 与 `linked blob`（新代码路径真的编进去了）。
4. `python3 scripts/tests/test-k60-bt-blob.py --assembly <tree 的 k60_bt_blob.s> --container <容器>`
   → `✅ … container table is self-consistent`；`verify-boot-image.py --manifest` `OK`。

## 6.5 受控对照对（2026-11-15 04:13–04:54，`bt-s4b-20261115b` + `bt-s4c-20261115a`）

P-201 要求一对判据来自同一基线。`bt-s4b-20261115a` 的 `frozen-before.txt` 有 455 条，其中两条是
`scripts/__pycache__/{pong_adt_contract,research-gate}.cpython-312.pyc`；重编译得到的哈希与记录值不同
（`py_compile` 非确定性），所以**无法复现**同一份 455 条清单。做法改为：两次构建都用**同一个干净的
453 条清单**（先删 `__pycache__`，`PYTHONDONTWRITEBYTECODE=1`），于是这一对是**构造上受控**的。

```sh
# 正向（内嵌固件）
K60_OUT=/opt/k60/trees/k60build/bt-out-s1c \
K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device \
bash scripts/build-strict.sh bt-s4b-20261115b \
  --fd /mnt/e/k60-work/artifacts/fd/bt-s2-20261114b-cf4485712c29.fd \
  --bt-blob /mnt/e/hackios/k60-bt/out/pong-bt-firmware.bin \
  --kernel-arg k60bt=1

# 负向（只少 --bt-blob，其余完全相同）
K60_OUT=/opt/k60/trees/k60build/bt-out-s1c \
K60_DEVICE_INPUT=/opt/k60/trees/k60build/bt-device \
bash scripts/build-strict.sh bt-s4c-20261115a \
  --fd /mnt/e/k60-work/artifacts/fd/bt-s2-20261114b-cf4485712c29.fd \
  --kernel-arg k60bt=1
```

两次都退出码 0，HEAD 同为 `68a38f3`，series 同为 228（`b31855c9…9dab`），`frozen-before.txt`
**逐字节相同**（453 行，sha256 `931d391d56c639fe9ea23e3eee66606e6519df4d85d98bdcc9d620001164d08e`）。

| 项 | 正向 `bt-s4b-20261115b` | 负向 `bt-s4c-20261115a` |
|---|---|---|
| boot.img | `2402def923f48c4609541655119082b12965b806d41601844560a2e9be3fa14f` | `535c395aa3a695b3554cfac5f87518e42ea37174c1eccc917c7637c04a383101` |
| kernel_built | `e8e0f13b7bd6f636012a8bb709ac77639a7f4937eb9a2795550d8259fe8481d7`（106,541,056 B） | `7f049b7c5fc5d3d6dbdadd76a033fb80ddfce55d7eeb69417fba0992a1e43ca6`（105,508,864 B） |
| payload | `36c7e2c8f0f994f1a807540790b62644396dd13719a902ecc022220625f7f238` | `0634b28d187eff4e5512e4ac10b4810a280ecccab83174d6926e737d94bbf62d` |
| payload_kernel | `2ed1dc9e846e5288a2ef1d7f42ddaf4bb1e6e6cbec2a24f989c1657f255f44ab` | `f95eee9408681b54967f8f3cf4e9e95c8a154a0b0f207274c7fbe95dba029843` |
| adt | `50dfee28e209e5e35b614bf37b49b3ceb91628480a4863321624f7e20eb217dc` | `25fa7b08622de7e42b767676e1112c0488cf26aa3e0bd40a99183affbf2736c8` |
| bt_blob | `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037` | 空（`gen-k60-bt-blob.py` 写一字节桩） |
| gpu_addon | 空（故意不传） | 空 |
| 启动参数 | 30 项 / 583 B，`k60bt=1` | 同左 |

内核侧的对照证明：

1. `llvm-nm-18`：正向 `_k60_bt_blob` @ `fffffff0071b8818`、`_k60_bt_blob_len` @ `fffffff0072b3618`，
   相差 1,027,584 = 容器字节数；负向两者 @ `…8818` / `…8820`，相差 8 = 一字节桩 + 对齐。
2. 按字节搜容器前 4 KiB：正向在偏移 1,787,928 命中，取 1,027,584 字节算 sha256 = `febdc20d…`（逐字节相同）；
   负向 `find` 返回 −1，容器**不存在**。
3. 正向与 `a` 的 payload 内核只差 4 段（(4960,4967)、(4969,4975) 代码签名、412159–412261 两处构建时间戳、
   (106540248,106540269) `_PrelinkKCID`）——即只差戳；正向与负向差 70,057,045 字节。
4. 两份 `frozen-before.txt` 逐字节相同（见上），所以"差 1,032,192 B"只可能来自容器本身。
5. `test-k60-bt-blob.py --assembly` 对两份生成的 `.s` 都报 `container table is self-consistent`；
   负向那份是 `_k60_bt_blob_len: .quad 0` 的桩，内核 `k60_bt_addon_load_blob()` 见长度 0 即静默回落。

## 7 上机阶梯（板子回来后）

> ✅ **2026-11-15 15:36 Lead 裁决：改代码、不砍启动参数。本节前提现在是「一枚 `k60bt=1`（30 项 / 583 B，不变）跑完整 S4」。**
> 阻断 1/2/3 由新增的 `patches/xnu/0511-k60-bt-s4-unblock.patch`（= `patches/bt/0005`，3,718 B，sha256
> `07b862dd…f39a`，`patches/xnu/series:209`）一次解掉：`k60.stage` 默认 0（探针改为显式 `k60bt_stage=1` 或
> 任一 `k60bt_step=N` 才进）、`k60_bt_power_on()` 冷启动只打一行 `power: cold boot, rails not voted
> (k60bt_warm=0)` 后继续、addon 门闩变成「`native_gpu_addon_stage >= 1 || k60_bt_blob_len > 0`」；阻断 4
> 由 `main` 的 `3ea8d71` + `dafa502` 在构建期解掉（`build-strict.sh` 默认 `UNIXNU_UNIQUE_CHIP_ID=4B36305400000001`
> 并转发 `--unique-chip-id`）。旧的「stage+warm+addon 要 628 B、超 607 B 上限 21 B」算术不再适用——一个参数都不加。
>
> 下面保留 2026-11-15 14:00 的原始复核记录（历史，供对照）：
> `bsd/dev/qbt_k60.c:2073` 把 `k60.stage` 初始化成 1 之后才解析 `k60bt_stage`，所以 583 B 的
> `k60bt=1` 让 worker 走 S1c 探针分支并在 `:2008` `return`，**永远到不了** `k60_bt_power_on()` →
> `qbt_boot()`；即使补上 `k60bt_stage=2`，`:1814` 的 `k60.warm_boot` 默认 false 会让
> `k60_bt_power_on()` 直接返回 `-EOPNOTSUPP`(102)。另有 `:1998` 的
> `while (&native_gpu_addon_stage && native_gpu_addon_stage < 1)` 门闩：链进内核的
> `native_gpu_addon_stage` 只有 `bsd/kern/kern_exec.c:7700` 的定义（`__DATA,__common`，加载值 0），
> `qbt_k60.c:341` 的弱定义 `= 1` 被它盖掉，只有命令行带 `sheng-gpu-addon=1` 才会被
> `native_gpu_addon_prepare()` 改写。三条都补齐要 628 B，超 607 B 上限 21 B。第四条：
> `k60_bt_local_address()`（`:353`）要 `/chosen/unique-chip-id`，而 `kernel.macho.adt`
> （15,972 B，sha256 与 §6.5 的 `adt` 一致）里 `grep -c unique-chip-id` = 0——`make-pong-adt.py:159`
> 只在传 `--unique-chip-id` 时才写这条属性，`build-native-bootimg-local.py` 从来不传。
> 当时的建议是「裁决前不要飞这两枚镜像」；`linked blob` 那行在 `qbt_k60_start()` 里、线程起来之前
> 就打，不受上述四条影响，所以它一直是这对镜像唯一能验的判据。

**镜像要重出**：`0511` 落进 series 之后，正向用 **`bt-s4b-20261115c`**（内嵌 blob；HEAD 同时含 `0511`
与 `main` 的 identity 种子），负向对照用 **`bt-s4c-20261115c`**（同一命令、只少 `--bt-blob`，所以
`k60_bt_blob_len == 0`，走回落路径；ADT 也随 `3ea8d71` 变了，所以 `…a` 不能再当对照）。
`bt-s4b-20261115b` / `bt-s4c-20261115a` 是 `0511` 之前的受控对，只剩 §6.5 的证明价值；
`bt-s4-20261114b` 是旧基线（series 227、旧 `build-strict.sh`），按 P-201 不再作为对照。

**已重出（2026-11-15 16:25）**：HEAD `5190337`，series 229 / `67baff88…bca`，frozen 同一基线
`0254f9d5…585e`，30 项 / 583 B。正向 `bt-s4b-20261115c`：boot.img `2dc1054e…968`、kernel `8fc5ab58…45e`
（106,541,056 B）、payload_kernel `96401d1f…c906`、adt `dbcab086…1afbf`、bt_blob `febdc20d…2037`。
负向 `bt-s4c-20261115c`：boot.img `dbf089c0…8d03`、kernel `5046e338…029e`（105,508,864 B）、
payload_kernel `a352bf57…5a20`、adt `3042f2ca…2c8a`、bt_blob 空。`verify-boot-image` 与
`image-arg-audit` 双双 OK；registry 84 条 0 失败（P-165 确认 229 个补丁全部应用）。

| 级 | 镜像 | 参数 | 期望（关键行） |
|---|---|---|---|
| S4- | `bt-s4c-20261115c` | `k60bt=1` | 负向对照：`[bluetooth] addon: no GpuAddon property`，随后回落到 vnode 根（同样找不到），控制台完整、无 panic |
| S4a | **`bt-s4b-20261115c`** | `k60bt=1` | `[bluetooth] addon: linked blob bytes=1027584 records=106` |
| S4b | **`bt-s4b-20261115c`** | `k60bt=1` | `[bluetooth] addon: serving 201560 0`（rampatch），随后 `serving 6319`/`6602`（NVM） |
| S4c | **`bt-s4b-20261115c`** | `k60bt=1` | `[bluetooth] power=1 result=0 baud=… firmware=<build label>`（裸 printf）+ `[bluetooth] QCA controller version 0x…`（`0511` 新增的 level-1 行），即上电→取 MAC→`qbt_boot()`→`qca_read_soc_version()` 全程无错，且**不再出现** `no platform identity` |

（`bt-s4a-20261114c`/`f`/`bt-s4a-20261115a` 全部作废：它们把固件放在 payload 的
`kernel.macho.gpuaddon` 槽里，而固件从不填那个槽（P-197）。它们的实测结果**不是**失败，而是
`addon: unusable range 0 0`——那正是 P-197 的真机证据。）

S4a 与 S4b 用同一个镜像：`linked blob` 在 `qbt_k60_start()` 里就打（`k60_bt_addon_load_blob()`），
`serving` 要等 qbt 真正取固件才打，是同一轮启动里的前后两段，不是两次构建。

判定：只认 `capture.json` 的 `verdict`/`panicMarker`；控制台 0 字节时用 `0331` 的 K60PREV 重放读上一轮尾巴。
失败即回退到不带 `--bt-blob` 的构建（内核代码对缺失 blob 是静默降级，见 §4 日志表）。

### 7.1 日志等级闸门：S4 判据逐条审计（2026-11-15）

`bsd/dev/qbt_k60.c:1545`（= `patches/xnu/0500-k60-bt-qbt-new-files.patch:971`）的 `k60_log()` 只有
`if (level <= 3) printf("[bluetooth] %s\n", line);`，而 `bsd/dev/qbt/qbt_linux.h:97` 的
`bt_dev_info` 是 **level 6**（`bt_dev_dbg` 是 level 7，更不可能）。所以下列十个调用点
**永远不上控制台**——不是「可能打不出」，是一定打不出：

| 文件:行（0500 内） | 内容 |
|---|---|
| `btqca.c:70` / `:72` / `:74` / `:76` | `QCA Product ID` / `SOC Version` / `ROM Version` / `Patch Version` |
| `btqca.c:146` | `QCA FW build version: %s` |
| `btqca.c:563` / `:572` / `:845` | `QCA Downloading %s` |
| `btqca.c:764` | `QCA controller version 0x%08x` |
| `btqca.c:999` | `QCA setup on UART is completed` |

**S4c 的原判据 `QCA controller version 0x…` 即死于此闸门**，已从上表移到本节。Lead 2026-11-15 裁决：
**不放宽闸门**（全局 3→6 会让每条蓝牙路径永远多 9–11 行），只给 `btqca.c:764` 补一条专用 level-1 行，
已落在 `0511`（`btqca.c:764-771`：`qbt_linux_log(hdev->q, 1, "QCA controller version 0x%08x", soc_ver);`，
紧跟原 `bt_dev_info`）。所以 `0511` 之后 S4c 能同时看到两条判据；上表其余九个调用点仍然永不上控制台。

**其余判据逐条核对，全部可见**：

| 判据 | 出处 | 等级 |
|---|---|---|
| `addon: linked blob bytes=1027584 records=106` | `k60_addon_loaded()` | 1 |
| `addon: serving 201560 0` | `k60_addon_note("serving", …)` | 1 |
| `addon: no GpuAddon property` / `no chosen/memory-map` | `k60_bt_addon_load()` | 3 |
| `addon: unusable range` / `bad magic` / `bad header` / `short GpuAddon property` | 同上 | 1 |
| `probe: armed` / `awake` / `core created` / `transport ready` / `addon gate passed` | `k60_probe_mark()` | 1 |
| `[bluetooth] power=%u result=%d baud=%u firmware=%s` | `k60_power_result()`，**不经 `k60_log`** | 裸 printf |
| `QCA Failed to request file: %s (%d)` / `QCA Failed to get version (%d)` / `Wrong packet received %d %d` / `Failed to run HCI_RESET (%d)` | `bt_dev_err` | 3 |

**代价**：固件名只在**失败**时才印到控制台（三处 `QCA Failed to request file: %s`）。成功路径上
能证明「固件真被取走」的可打印证据只有 `addon: serving <bytes> 0` 与 `power=… firmware=<build label>`。

**未解决的观测盲区**：`qbt_k60.c:1531` 的 `k60_log(NULL, 6, candidate)` 是唯一会打印「实际服务的是
哪个 alias 名」的语句，也是 level 6 ⇒ 死。所以即使拿到 `serving 201560 0`，也只能凭 201,560 B
这个唯一体积反推是 `hpbtfw20.tlv`；6,319 B 对应 13 个 `hpnv20*`、6,602 B 对应 5 个 `hpnv21*`，
NVM 一级**无法**从字节数定位到具体文件（清单见 `firmware/bluetooth/manifest.json`）。

### 7.2 c 对上机结果与 0511 逐 hunk 二分（2026-11-15 晚）

**c 对已飞**：负向 `bt-s4c-20261115c`（`dbf089c0…8d03`）到桌面、判据全中——`console.log:192`
`[bluetooth] addon: no GpuAddon property` 逐字命中，`:186` `K60 BT: published local address
ee:98:c5:8a:6b:4e`（identity 种子在 BT 上确认，第 4 项阻断关闭；证据
`usblog-20261115-162553/console.log`，245,222 B / 3,535 行）。正向 `bt-s4b-20261115c`
（`2dc1054e…968`）**0 字节**、port-not-observed、returnedToFastboot=True（证据
`usblog-20261115-163144`）。两个假设被 Lead 排除：不是内核体积——两枚正向都是 106,541,056 B
逐字节相同，负向 −1,032,192 B，106.5 MB 能起；不是 blob 本身——旧正向 b 携带同一个
`febdc20d` blob 到过桌面。负向带 0005 能起 ⇒ 0005 单独安全；唯一剩余变量是 **0005+blob 组合**。

**逐 hunk 二分**（Lead 裁决：不要动 blob、不动参数、不动 607 B 闸门）：四张图各只带 0005 的
一个 hunk + blob，判据是**到桌面（SB>100）**，不是 BT 自己的行。hunk 划分：

| hunk | 内容（`0511` 内） | 变体文件 | 提交 | 镜像 |
|---|---|---|---|---|
| h1 | addon 闸门 `|| k60_bt_blob_len>0`（`qbt_k60.c:2006-2015`） | `0511a…-h1` | `e296d9e` | `bt-bisect-h1` |
| h2 | warm 去掉 `return -EOPNOTSUPP`（`qbt_k60.c:1818-1827`） | `0511b…-h2` | `00aa205` | `bt-bisect-h2` |
| h3 | stage 默认 0（`qbt_k60.c:2096-2105`） | `0511c…-h3` | `40cdafd` | `bt-bisect-h3` |
| h4 | btqca 等级行（`btqca.c:764-771`） | `0511d…-h4` | `3bcaac3` | `bt-bisect-h4` |

镜像（全部 `k60bt=1` / 30 参数 / 583 B，boot.img 均 201,887,744 B，`bt_blob febdc20d…2037`）：

| 镜像 | boot.img | kernel_built | payload_kernel | frozen | series |
|---|---|---|---|---|---|
| `bt-bisect-h1` | `3936416f…abe6` | `f4ba4245…57e7` | `252afd1a…dcf0` | `0d3ee7ae…1130` | 229 / `d8c1cee2…07de` |
| `bt-bisect-h2` | `e2862637…ab81b` | `40ded59a…2419` | `cae9330b…57fab` | `cbc44962…b3cf` | 229 / `30319819…a24a` |
| `bt-bisect-h3` | `182e73de…1102` | `ee96b73d…5c7c` | `a8e2a142…0a9` | `912bb990…5d3` | 229 / `9d21a68b…05b` |
| `bt-bisect-h4` | `d9977a2e…197b` | `1573f6bf…e44` | `d4f91491…db9` | `33c52fcf…76c` | 229 / `62c2c818…fdb` |

frozen/series 每张不同是预期：series 指向单 hunk 变体（变体文件在仓库里，进 frozen 列表）。
每张图构建前必须把 series 换 hunk 并**提交**——构建内合规门禁硬拒 dirty series
（iron-2 "1 tracked file(s) modified but not committed: patches/xnu/series"），第一轮死于此。

**预测**：h1 单独时 h3 不在 ⇒ stage 仍为 1 ⇒ 上电线程 20 s 睡眠后走**默认第 9 步的首次真机探针**
（完整寄存器阶梯；`qbt_k60_start()` 在 `bsd_init.c:1352`、紧跟 `:1341` 的 USB 控制台 worker，
所以此时控制台已起，故障会留字节）；h2/h3/h4 单独时要么在闸门前空转要么纯装饰 ⇒ 预期到桌面。
四张全到桌面 ⇒ 凶手是 h1+h2+h3 组合（早启动无延迟固件路径），下一步组合二分先试 h1+h3。
若 h1 单独就静默，怀疑对象移向 `k60_bt_addon_load_blob()` 的调用时机——把它移到 bring_up 之后，
首行换成 level-1 具名日志 `blob: addr=… len=…`，另开一轮。

**收尾**：`bt-restamp-20261115`（全量 0511，series `67baff88…bca`、frozen `0254f9d5…585e`，
与 c 对逐字节一致）只为重建 P-165 戳记让注册表回绿，**不是飞行镜像**。五个提交均未 push
（五个提交已由 Lead 在 Windows 侧推上，`5190337..8ec4883`）。

**h13 组合图与 0509 OSData 修复（2026-11-15 晚）**：飞行顺序 h1 → h3 → h13；h1
silent 即停飞并执行 load_blob 后移预案。`bt-bisect-h13`（0511e = h1+h3 合并，commit
`670e138`）：boot.img `0f3a455d…27db`、kernel `141bd513…b3bf`、payload_kernel
`4233a2b7…2e4`、frozen `94792777…3e91`、series 229 / `ec4eee05…c109a`；h2 不在 ⇒
warm 拒绝仍在 ⇒ 早启动只做 addon+transport+闸门+一次冷启拒绝——h13 silent 钉死
早启动无延迟路径，h13 到桌面则真凶是 h2 的上电续路。0509 已按法 ① 修 OSData
（commit `ad49ff2`，三属性 + radio `device_type` 经 `k60_bt_string_property`，
NUL 在内；宿主侧断言 `scripts/tests/test-k60-bt-0509-properties.py` 25 cases 全过），
下一张全量 0511 恢复镜像必须带上。

**h13 实飞判读（2026-11-15 21:26，Lead 飞）**：证据 `usblog-20261115-212643`
（console.log 237,533 B，supervisor rc=0、无 panic）。`:192` `addon: linked blob
bytes=1027584 records=106`；`:193` `power=1 result=-102 baud=115200 firmware=`
（result=-102 = −EOPNOTSUPP，来自 `:1814` 的 warm 拒绝——h2 才收窄它）；无
probe: armed / transport ready / s1 map，内核侧 BT 未 arm；内核进桌面（SpringBoard
13 行、getBytes:range ×36 属 C 族预期、K60 BT ×1）；用户态同 h3：`:1309` marconi
匹配不到 DT 服务、`:1310` MAC 全 00、`:1311` 拿到 ee:98:c5:8a:6b:4e（旧 0509
OSString 后果）。**三张一致结论：h1 过门闩进 S1 map / h3 卡 gate / h13 冷启被拒，
单 hunk 与 h1+h3 组合都不致死 ⇒ 全量 0005 的 silent 死因收敛到 h2（和/或 h4）。**

**h12 图（2026-11-15 22:54 构建，待飞）**：0511f = h1+h2 两 hunk（不含 h3/h4），
验证 H12_EQUALS_FULL_MINUS_H3_H4 + H12_CHECK_OK。boot.img
`0eb30032…9af2`（201,887,744 B）、kernel `67252a00…`、payload_kernel `0e74cf5e…`、
payload `ee3abfc9…`、adt `313bb5ba…`、frozen list `8e39be87…`、series 229 /
`cd4acbf6…`、blob `febdc20d…`、30 参数 / 583 B、head `364499d`。判读：silent ⇒
h2 单独致死（再把 h2 拆子 hunk 二分：只收窄 warm 判定 / 只有冷启续路）；到桌面 ⇒
凶手是 h4 或 h2+h4 组合，再出 h124。

**h12 实飞判读（2026-11-15 23:00，Lead 飞）**：证据 `usblog-20261115-230047`（220,889 B /
3,196 行，SpringBoard 132、panic 0、rc=0）。S1–S9 全过：`:707` s1 map（gcc=fffffff8be6b6000
uart=fffffff8be8ab000 qup=fffffff8be8af000）、`:709/:712` s2 gpll0_cmd=1 locked=1、`:717` s3
qup_vote_after=0000020f、`:719-:727` s4 halt（core=00004220 m_ahb=00000000 s_ahb=80000002）、
`:729-:733` s5、`:735` s6、`:737-:741` s7 rcg_cfg 00100000→00100001、`:743-:751` s8
fw_rev=00000204 qup_hw_ver=30080000、`:753-:760` s9 dma、`:761` done、`:762` **power=1
result=0** —— 电源/时钟/QUP 段首次真机成功。判读：h2 不是凶手；只剩 h4 单独或 h2+h3 组合。
`getBytes:range:` 在 h12 为 0 次（h1 36、全量 36–37），C 族与身份发布链的旁证，三态表归
display 线；`firmware=` 为空属预期（固件下载在下一段）。

**h123 决定性图（2026-11-15 23:18 构建，待飞）**：0511g = h1+h2+h3（不含 h4），
H123_EQUALS_FULL_MINUS_H4 + H123_CHECK_OK；boot.img `580b2795…e9a6`（201,887,744 B）、
kernel `bf3aee6b…445b`（106,541,056 B）、payload_kernel `0140faa5…fe33`、payload
`15b7b9ba…583d`、adt `b082c73d…41c2`、frozen `0fa2c372…28e7`、series 229 / `d80464df…8115`、
blob `febdc20d…`、30 参数 / 583 B、head `540f51b`；verify-boot-image OK + image-arg-audit OK。
h4 单独 silent ⇒ h4 是凶手、h123 证实 h2+h3 无害；h4 单独起 ⇒ h2+h3 组合是凶手、h123 决定。

**h23 与 h4 单独实飞（2026-11-15 深夜，Lead 飞）**：`bt-bisect-h23`（0511h = h2+h3，不含
h1/h4）**到桌面**——证据 `usblog-20261115-235417`（console 3,233 行 / 225,486 B、SpringBoard 128
行、panic 0、rc=0、`:453` disk5s1 vol-uuid 1BCD69FF Data 正常、`:192` blob 链入）。两个可观测性
副作用：`:193` 的 `probe: armed` **消失**（h3 把 stage 默认 0 之后早启动探针不再挂载，h12 有、h23
没有；这不是失败），`getBytes:range` **0 次**。`bt-bisect-h4` 单独飞（`usblog-20261115-230627`，
253,946 B、SB 13、panic 0、`[bluetooth]` 只有 5 行、停在 transport ready、getBytes 36）也**到桌面**。

**六张实测矩阵（全部 Lead 飞）**：

| 图 | 组合 | SB | getBytes | power 行 |
|---|---|---|---|---|
| h1 | h1 | 13 | 36 | 1（未成功） |
| h13 | h1+h3 | 13 | 36 | 1（result=-102） |
| h4 | h4 | 13 | 36 | 0 |
| h12 | h1+h2 | **132** | **0** | **1（result=0）** |
| h23 | h2+h3 | **128** | **0** | 0（探针未挂载） |
| h123 | h1+h2+h3 | **silent** | — | — |
| 全量 | h1+h2+h3+h4 | **silent** | — | — |

两条硬结论：① **h2 是 `getBytes:range` 消失的必要条件**——含 h2 的 h12/h23 都是 0 次，不含 h2 的
四张都是 36 次；这与 0509 的 ad49ff2 无关（二分图都不含它），所以 C 族的真凶是「冷启动早退导致身份
发布走错分支」，不是属性类型，C 族验证不必等 ad49ff2。② **致命集必须含 h4**：h23（h2+h3）能起、
h4 单独也能起、全量 silent ⇒ 凶手是 h4 × {h1,h2,h3} 的交互；此前「必须含 h3 且含 h2 或 h4」的
推断被 h23 推翻。下一张只出 **h124（h1+h2+h4）**：能起 ⇒ 致命组合是 h3+h4，再出 h34 收口；
h124 silent ⇒ 致命组合是 h4+h1 或 h4+h2，用 0512 的三个开关在 h124 上逐条关断，比再切 hunk 快。
**h124 决定性图（2026-11-16 00:20 构建，待飞）**：0511i = h1+h2+h4（不含 h3），
H124_EQUALS_FULL_MINUS_H3 + H124_CHECK_OK；boot.img `b6d293e5…e641`（201,887,744 B）、
kernel `a6980b9c…0f06`、payload_kernel `0f73563d…87a5`、payload `86d8bb57…2080`、
adt `4db35f3c…d12a`、frozen `b0c08d35…4792`、series 230 / `21eda89a…2240`、blob
`febdc20d…`、30 参数 / 583 B、head `f742288`、dirty 0；verify-boot-image OK +
image-arg-audit OK。series 为 230 是因为 0512 已在序列尾部。判读：能起 ⇒ 致命组合是 h3+h4，
下一张 h34 收口；silent ⇒ 致命组合是 h4+h1 或 h4+h2，用 0512 三个开关在 h124 上逐条关断。

**h124 实飞判读（2026-11-16 00:45 飞，Lead 飞，证据 `usblog-20261116-004519`）**：**能起**——
console.log 223,630 B / 3,229 行、SpringBoard **132**、panic 标记 0、supervisor rc=0、getBytes:range **0 次**；
`:192` blob 链入、`:193` `probe: armed delay=20s step=9`、`:703-:706` awake/core created/transport
ready/addon gate passed、`:708` s1 mapped（gcc=fffffff757695000 uart=fffffff75788a000
qup=fffffff75788e000）、`:710/:713` s2 gpll0_cmd=00000001 locked=1、`:718` s3 qup_vote_after=0000020f、
`:720` 起 s4 halt 回读、S1–S9 全程、`:762` probe: done、`:763` **power=1 result=0 baud=115200 firmware=**、
`:455` disk5s1 vol-uuid 1BCD69FF、`:485` K60DATA mounted ro=0、`:1037` Early boot complete。

**七张矩阵收敛（全部 Lead 飞）**：h1 SB13/36/probe armed 有/power 1；h13 SB13/36/有/1(−102)；
h4 SB13/36/有/0（停 transport ready）；h12 SB132/**0**/有/1(result=0)；h23 SB128/**0**/**无**/0；
h124 SB132/**0**/有/**1(result=0)**；全量 silent。⇒ ① 能起的三张（h12/h23/h124）都含 h2，
**h2 是「不再 silent」的必要条件**；② 全量 = h124 + h3，而 h124 能起、h23（h2+h3）能起、h4 单独能起
⇒ **致命集是 h3 × h4 两两交互**，不需要 h1、也不需要 h2 同时在场（比「必须含 h4」更窄）。
③ 对照 h23（探针不跑）与 h124（探针全程跑通）：**h3 是「让探针看不见」的 hunk，h4 是「让内核起不来」
的 hunk**，两者叠加才 silent。④ C 族归因按 h2 口径改写：不是 0509 OSData 修复直接生效，而是 h2 让
冷启动早退消失后身份发布第一次真正执行。

**h34 实飞判读（2026-11-16 01:45 飞，Lead 飞，证据 `usblog-20261116-014536`）**：**能起**——
console.log 134,032 B / 2,264 行、SpringBoard **128**、panic 标记 0（`panic(`/`panic: `/`Debugger called`/
`stackshot` 各 0）、`getBytes:range` **0 次**、`:186` `K60 BT: published local address ee:98:c5:8a:6b:4e`、
`:192` `[bluetooth] addon: linked blob bytes=1027584 records=106`（`[bluetooth]` 全篇仅此 1 行）、
`:300` K60DATA attempt enter、`:304` APFS UUID 1BCD69FF 绑到 Data UFS 窗口 /dev/disk5s1、
`:481` K60DATA mounted ro=0、`:973` Early boot complete、`:2196` Pong UI 开发版 SpringBoard 激活门。
`probe: armed`/`probe: done`/`power=` 三行全无（h3 把早启动探针整段拿掉，可观测性副作用，与 h23 同形）。

**结论更新（比七张矩阵再窄一步）**：h34 = h3+h4 能起 ⇒ **致命集不是纯 {h3,h4}，还必须带 h1 或 h2
之一**。因此 h3×h4 两两交互的结论被推翻，改为「h4 × h3 × (h1|h2) 三元组，h1 与 h2 至少一个在场」。
下一步按 Lead 判读树：出 h134（h1+h3+h4）与 h234（h2+h3+h4）各一张，两张即可定位是 h1 还是 h2 在放大。

**h34 决定性图（2026-11-16 01:06 构建）**：`bt-bisect-h34` = 0511j（h3+h4，不含 h1/h2），
boot.img `3b7d79b7…b1873`（201,887,744 B）、kernel `556ad11d…c45947`、series 230 /
`dfa2f138…19a34`、blob `febdc20d…2037`、30 参数 / 583 B `k60bt=1`、verify + image-arg-audit OK。
判读树：silent ⇒ 致命集锁定 {h3,h4}，再在 h34 上逐条关断 `pong_bt_smmu=0` / `pong_bt_rcg=0` /
`pong_bt_noboot=1`；能起 ⇒ 还需 h1 或 h2 之一在场，出 h134 与 h234 各一张。

### 7.3 静默死亡的机制假设与判据（2026-11-16）

九次飞行的矩阵把致命集合收敛为 **h4 × {h1,h2,h3} 的交互**：h1/h3/h4/h12/h13/h23 都能起桌面，
h123（h1+h2+h3）与全量（h1+h2+h3+h4）都是 0 字节；h4 单独不致死，h1+h2+h3 也不致死。真正写硬件的
是 stage=0 时的 `k60_bt_power_on()`（`bsd/dev/qbt_k60.c:1814`）与随后的 `qbt_boot()`；probe 路径
（stage=1）只读寄存器。

写序（实测行号取自 c 构建的 applied tree）：

1. `k60_map()` 五个区间——0507 probe s1 已证明映射与读访问安全（h12 `:707`）；
2. `kmem_alloc_contig()` + `pmap_find_phys()` 取 DMA 缓冲物理地址；
3. `k60_smmu_bypass()`（0508，`bsd/dev/qbt_k60.c:640`）——**第一次写 apps_smmu**；
4. `k60_uart_pins_idle()` / `k60_gpio_output()`——第一次写 TLMM；
5. SE 复位、`k60_gcc_set_se_rate()`（`bsd/dev/qbt_k60.c:765`）、GENI 传输；
6. `qbt_boot()` 经 GENI DMA 下载 106 段固件。

#### 假设 a：SMMU 流映射

BT 流 0x483 取 `banks-1-bank_from_top` 的上下文组，写 SCTLR=0 / CBAR=0x10000 / CBA2R=1 /
S2CR=bank / SMR=0x80000000|0x483，逐项回读。

- 若是它：日志会出现 `smmu plan sid 0x483 slot … bank … action install` 与 `smmu sid 0x483
  slot … SMR … S2CR … CBAR … CBA2R … SCTLR …` 两行（level 1）。两行都没有 = 死在
  `kmem_alloc_contig()`/`pmap_find_phys()`；出现 `reserved context bank already used` = 与
  其他流（UFS / DWC3）撞组。
- 代码检查：规划器会拒绝"别人的 SMR 已指向我选的 bank"并换 bank，但只在**当时**成立——BT 在
  `bsd/kern/bsd_init.c:1352` 运行时 UFS 还没装自己的 bypass，BT 会先占 `banks-1`；UFS 之后若
  拒绝共用，根挂载就会失败。这条路径真机从未跑通，保持一级嫌疑。
- 单独关掉：`pong_bt_smmu=0`。

#### 假设 b：RCG / 时钟

`k60_gcc_set_se_rate()` 向 qupv3_wrap2_s5 的 CMD_RCGR（0x2e618）写 ROOT_EN + CMD_UPDATE，并等
SE20 halt（0x2e008）。

- 若是它：`k60_gcc_wait_halt()` 超时会返回 -ETIMEDOUT 并打日志（可见失败，不静默）；真正静默的
  形态是写 CMD_UPDATE 之后总线挂死、没有下一行。
- 代码检查：这条路径只写 SE 自己的 RCG，不碰 UFS 的 RCG；但同一个 GCC 块在 SE 时钟关闭时被写，
  可能触发 NoC slave error（SError → panic，串口无输出）。注意 h4 是 btqca 的日志等级行，本身
  不写硬件——它只能通过"让 stage 0 之后的路径继续往下走"参与，所以交互假设要优先怀疑 h4 让
  `qbt_boot()` 之后的某一步真正执行到。
- 单独关掉：`pong_bt_rcg=0`（两处 `k60_gcc_set_se_rate()` 都跳过）。

#### 假设 c：固件下载 DMA

`qbt_boot()` 通过 GENI DMA 把 106 段固件写进那块 contig 缓冲。bypass 若没落在 0x483 上（或落错
bank），DMA 会触发 SMMU 翻译错误 → 外部 abort → 静默。

- 若是它：`full: qbt_boot enter` 之后没有输出，而 `full: dma buffer and smmu bypass ready` 与
  `full: uart pins parked` 都在。
- 单独关掉：`pong_bt_noboot=1`（只跑到固件下载之前）。

#### 运行形态与判据

`pong_bt_late=1` 时日志顺序固定：

```
late: armed, waiting for the K60DATA deploy point        （早启动，线程挂起）
late: released by the K60DATA deploy point               （kern_exec.c 部署点）
late: released, starting the full ladder                 （工作线程醒来）
full: power_on enter
full: dma buffer and smmu bypass ready
full: uart pins parked
…
full: qbt_boot enter
```

**最后一行就是死亡点**，而且此时 console 与 `/private/var` 都已在（Data 已挂载），不会再出现
"0 字节"的盲区。不加 `pong_bt_late=1` 时行为与 0511 逐字节等价（宿主侧断言见
`scripts/tests/test-k60-bt-0512-late-start.py`：四个 `pong_bt_*` 的默认值、以及三条裸调用只剩
受保护形态），所以这一版镜像在不加该参数时也能直接当 C 族（0509 OSData）图飞。映射也一并推迟：
`k60_bt_power_on()` 第一步就是 `k60_map()`，早映射没有额外诊断价值；`k60_bt_addon_load()` 的
快照仍留在早启动（DarwinBoot 窗口会被 VM 回收）。

### 7.4 断网也能出图：本地 kernelcache

prelink 默认从 IPSW 取 kernelcache，网络中断时构建会死在 range reader（SSL EOF）。设
`UNIXNU_KERNELCACHE=<K60_OUT>/ipsw/20G81/kernelcache.decompressed`（第一次成功构建就已经落盘）
即走本地文件，断网也能出图。这一条对每条线都有用，已写进构建包装脚本
`scratch/bt-s4/bisect/wsl-build-one.sh`。
### 7.5 0510 与 0620 在 `osfmk/conf/files.arm64` 的上下文撞车（2026-11-16）

合并 main 之后，`0510` 原来把 `k60_bt_blob.s` 插在 `WKdmCompress_4k.s` 之后（hunk `@@ -22,6 +22,7 @@`），
而 `0620-k60-adsp-blob.patch` 的 hunk 头也是 `@@ -22,6 +22,7 @@`，上下文正是
`k60_metal_blob.s` / `WKdmCompress_4k.s` 这一段；0510 先插一行，0620 的上下文整体错位，
series 到 0620 就 `patch does not apply`（d1 构建实测）。
修法：0510 的插点挪到 `lz4_encode_arm64.s` 之后（`@@ -25,6 +25,7 @@`），后续没有补丁引用那一段。
新 sha256 `3309d123624bf4461a5ce4e6e197e613546af51ebc894967ad8084a21f7eaa87`（15,718 B）。
全量重放校验：232 个补丁 `git apply` 顺序打完 `BAD=0`，三行 blob 分别落在 24 / 25 / 30 行。

d 系列第一张图 `bt-d1-smmu`（全量 0511 + `pong_bt_smmu=0`，31 参数 / 598 B）已按此配方构建并校验：
boot_img `bd1f5bc6f4cb96f9ec8995ca86a0f0d0769879c75a933dc7a2d130b3718d45b5`，
series {232, `dcc7bb45d311dc5f`, namespace `names+sizes`}，`verify-boot-image: OK`、`image-arg-audit: OK`。

### 7.6 d 系列第一张图 `bt-d1-smmu` 实飞：SMMU 路径被排除（2026-11-16 04:19）

`bt-d1-smmu`（全量 0511 + `pong_bt_smmu=0`，31 参数 / 598 B，boot_img
`bd1f5bc6f4cb96f9ec8995ca86a0f0d0769879c75a933dc7a2d130b3718d45b5`，kernel `d40ae0b9…`，
series 232 / `dcc7bb45d311dc5f`（P-214 namespace 已带），blob `febdc20d…`，head `eb3cd83`）
由 Lead 实飞，结果**仍 silent**：证据 `E:\k60-work\evidence\usblog-20261116-041744`，
`port-not-observed`、`bytes=0`、`complete=False`、`returnedToFastboot=True`，supervisor rc=2，
端口 84 s 内从未出现；`record-boot.py` 正确拒记（0 SpringBoard 行）。

判读：关掉 `k60_smmu_bypass()` 之后一样静默 ⇒ **SMMU / stream-mapping 这条路径（§7.3 假设 a）被排除**。
这与 wifi 线的结论互不矛盾：wifi 的 silent 是「lease 抢在分配之前」，发生在 UFS bring-up 里、
与本线 `k60_smmu_bypass()` 的 SID 映射不是同一段代码。

下一步按 Lead 的指令继续一次一张：d2 = 全量 0005 配方 + `pong_bt_rcg=0`（验 §7.3 假设 b），
d3 = 全量 0005 配方 + `pong_bt_noboot=1`（验假设 c：固件下载整段不跑）。

### 7.7 d 系列第二张图 `bt-d2-rcg` 实飞：RCG 路径也被排除（2026-11-16 04:34）

`bt-d2-rcg`（全量 0511 + `pong_bt_rcg=0`，31 参数 / 597 B，boot_img
`7f83bc0c1da0e1869f4e43438c3a0fd09706aff9f3a6f60f16e9a59fabd44101`，kernel `c68c54ed…`，
series 232 / `dcc7bb45d311dc5f`（P-214 namespace 已带），blob `febdc20d…`，head `ffc1de1`）
由 Lead 实飞，结果**仍 silent**：证据 `E:\k60-work\evidence\usblog-20261116-043417`，
`state=port-not-observed`、`bytes=0`、`complete=false`、`portSeen=false`、`returnedToFastboot=true`，
console.log 0 B（sha256 `e3b0c442…b855` 即空文件）。

判读：跳过 `k60_gcc_set_se_rate()` 的两个调用点之后一样静默 ⇒ **共享 RCG 复位停掉 UFS 参考时钟
（§7.3 假设 b）排除**。至此 §7.3 的 a、b 两条都被实飞否证，只剩假设 c（固件下载的 DMA 缓冲
没进 IOMMU，落到 UFS 正在用的页上）——d3（`pong_bt_noboot=1`）正是它的判据。

### 7.8 十一格矩阵收敛：致命集恰好是 {h1, h2, h3}，h4 无关（2026-11-16 04:38，04:56 补齐 h2 单格）

Lead 把 23:18 就构建好、但一直没飞的 `bt-bisect-h123` 补飞了：证据
`E:\k60-work\evidence\usblog-20261116-043650`，`port-not-observed`、`bytes=0`、
`returnedToFastboot=True`、supervisor rc=2 —— **silent**。

十一格矩阵（全部 Lead 实飞；每一格的 `SpringBoard` / `getBytes` / `armed` / `power`
四列都是 2026-11-16 在证据目录里重新数出来的，不是抄旧结论）。
构建过的十一张现在**每一张都飞过了** —— 此前 h2 单独那张从 23:18 一直躺到 04:48 才补飞，
正是 P-218 要堵的缺口：

| 配方 | h1 | h2 | h3 | h4 | SB | getBytes | armed | power | 结果 |
|------|----|----|----|----|----|----------|-------|-------|------|
| h1   | ✓ |   |   |   | 13  | 36 | 有 | 1 / result=0   | 起 |
| h2   |   | ✓ |   |   | 13  | 35 | 有 | 无             | 起，停 transport ready |
| h3   |   |   | ✓ |   | 12  | 36 | **无** | 无       | 起（stage 0：早启动探针整段不跑，`[bluetooth]` 只有 `:192` blob 链入一行）|
| h13  | ✓ |   | ✓ |   | 13  | 36 | **无** | 1 / result=-102| 起（−EOPNOTSUPP，warm 拒绝）|
| h4   |   |   |   | ✓ | 13  | 36 | 有 | 无             | 起，停 transport ready |
| h12  | ✓ | ✓ |   |   | 132 | 0  | 有 | 1 / result=0   | 起，S1–S9 全过 |
| h23  |   | ✓ | ✓ |   | 128 | 0  | **无** | 无         | 起（同 h3：探针未挂载，只有 blob 一行）|
| h124 | ✓ | ✓ |   | ✓ | 132 | 0  | 有 | 1 / result=0   | 起，S1–S9 全过 |
| h34  |   |   | ✓ | ✓ | 128 | 0  | **无** | 无         | 起（同 h3：探针未挂载，只有 blob 一行）|
| **h123** | ✓ | ✓ | ✓ |   | **0** | 0（空日志）| 无 | 无 | **silent**（port-not-observed，0 B）|
| 全量 0005 | ✓ | ✓ | ✓ | ✓ | 0 | 0（空日志）| 无 | 无 | silent（0 B）|

证据目录：h1 `usblog-20261115-211515`、h2 `usblog-20261116-044817`、h3 `usblog-20261115-212105`、
h13 `usblog-20261115-212643`、h4 `usblog-20261115-230627`、h12 `usblog-20261115-230047`、
h23 `usblog-20261115-235417`、h124 `usblog-20261116-004519`、h34 `usblog-20261116-014536`、
h123 `usblog-20261116-043650`；`armed` 列指 `:193` 的 `probe: armed delay=20s step=9`。

结论一：**致命集 = {h1, h2, h3} 三者齐备**。h123 去掉任意一个都能起（去 h1 = h23 起、
去 h2 = h13 起、去 h3 = h12 起），所以三者都是必要条件、一个都不能少；全量 0005 也 silent
与「它包含 h1+h2+h3」一致。此前「h2 是必要条件」「致命集是 h3×h4」两条推断都作废。

结论二：**0621 才是真凶，h1/h2/h3 只是让阶梯走到那一步**。三个 hunk 各自做的事是
（h1）打开 addon 闸门、（h2）去掉冷启动早退、（h3）把 stage 默认设 0 让完整阶梯真的跑起来——
它们本身没有一行写硬件地址，作用是让 `k60_bt_power_on()` **第一次真正执行到**
`k60_map(&k60.tlmm, … 1 MiB)` 这一步；那一步撞穿的是全内核共享的 8 MiB `io_submap`
（P-219，见 §7.11），而 `io_submap` 预算不够是 main 的既有缺陷（0621 修的就是它）。
所以「silent」不是蓝牙代码有毒，而是蓝牙阶梯替整个内核把这个预算缺陷暴露出来：
d1/d2/d3 三张开关图全 silent 也正是因为 `k60_map(&k60.tlmm, …)` 在 `k60.no_smmu` /
`k60.no_rcg` / `k60.no_boot` 三个判断**之前**就执行（§7.9、§7.13）。

方法教训（Lead 亲述）：四个 hunk 有 15 个非空子集，本轮只飞了 9 个，缺的那一格正好是决定性的。
二分要么飞满全部子集，要么在矩阵里把「已构建未飞」显式标出来。

这条教训已经落成门禁 **P-218**（`docs/engineering/PITFALLS.md:5526`，
`scripts/check-bisect-coverage.py`，main `216902a` / snap-r211）：拿每张 `build-manifest.json` 的
`boot_img` 与 `evidence/*/boot.json` 的 `imageSha256` 做差集，`--prefix bt-bisect-` 一跑就列出
「构建完但没飞」的镜像。写它时又踩了三次同形坑（拿账本当飞行记录、按哈希 join 但账本存截断路径、
用 plain utf-8 读 PowerShell 写的带 BOM `boot.json`），三条都记在 P-218 里。

h2 单格是十一格里最后补上的那一张：证据 `E:\k60-work\evidence\usblog-20261116-044817`，
console 3,379 行 / 235,151 B、SpringBoard 13、`getBytes:range` 35、panic 0；`:192` blob 链入、
`:193` probe armed、`:702-:704` awake / core created / transport ready —— 停在 transport ready，
没有 `addon gate passed`，也没有 `power=` 行（h2 单独不含 h1 的门闩，根本走不到上电那一步）。

d 系列进展（截至 2026-11-16 06:46 已全部收敛）：d1（`pong_bt_smmu=0`）、
d2（`pong_bt_rcg=0`）、d3（`pong_bt_noboot=1`）三张全部 silent ⇒ §7.3 的假设 a、b、c
全部否证（§7.6、§7.7、§7.9）；d4（`pong_bt_late=1`）第一次把死因打印成内核 panic
（`kmem_alloc(…, 1048576, 0x100021): failed with 3`，§7.10）；d5（0621 抬高 `IO_MAP_SIZE`
到 32 MiB + `pong_bt_late=1`）把 panic 消掉、阶梯推进到 `qbt_boot` 内部（§7.13）。
三个开关之所以都没用，是因为 `k60_map(&k60.tlmm, …)` 在 `k60.no_smmu` / `k60.no_rcg` /
`k60.no_boot` 三个判断**之前**就执行 —— 它们关的是阶梯后段，而死亡点在第四个大窗口的分配上。
「h123 + `pong_bt_noboot=1`」交叉格因此不再需要：d4/d5 已经把根因钉在 `io_submap` 预算上。

### 7.9 d 系列第三张图 `bt-d3-noboot` 实飞：固件下载段也被排除（2026-11-16 05:33）

Lead 实飞 `bt-d3-noboot`（全量 0511 + `pong_bt_noboot=1`，31 参数 / 600 B，boot.img
`07c139238cf4f3dff8d56e9145d05254ba7efb2cd5b0ebf4e7c697a3df0a817e`）：证据
`E:\k60-work\evidence\usblog-20261116-053306`，`bootAccepted` true / `bootExitCode` 0 /
`returnedToFastboot` true，capture `port-not-observed`、`bytes=0`、`portSeen=false`、
`portOpened=false`、`stopReason=fastboot-return`，console.log 0 B（空文件哈希
`e3b0c442…b855`）—— **silent**。

| 图 | 关掉的路径 | 结果 |
|----|-----------|------|
| d1 `pong_bt_smmu=0` | `k60_smmu_bypass()` | silent |
| d2 `pong_bt_rcg=0` | `k60_gcc_set_se_rate()` 两个调用点 | silent |
| d3 `pong_bt_noboot=1` | `qbt_boot()` 固件下载整段 | silent |

⇒ §7.3 的三条机制假设 a（SMMU/SID 与 UFS 冲突）、b（共享 RCG 复位停掉 UFS 参考时钟）、
c（固件下载 DMA 缓冲未进 IOMMU）**全部被实飞否证**。三张图都仍是「全量 0511 + blob +
`k60bt=1`」，所以死亡点比这三段都早：要么在进入 `k60_bt_power_on()` 之前（worker 线程启动、
`k60_map()`、DMA 分配、门闩判断），要么在 `k60_bt_power_on()` 内部三开关之外的那几步
（`k60_map()` / `kmem_alloc_contig()` / `pmap_find_phys()` / TLMM pins）。

下一格（Lead 判据树）：`h123 + pong_bt_noboot=1` 交叉格——把「三开关之外」与「{h1,h2,h3} 齐备」
这两个条件交叉，判断死亡点是否只在全量配方里才被触发。

### 7.10 d 系列第四张图 `bt-d4-late` 实飞：第一行内核 panic，死因是 io_submap 只有 8 MiB（2026-11-16 05:52）

Lead 实飞 `bt-d4-late`（全量 0511 + `pong_bt_late=1`，31 参数 / 601 B，boot.img
`87b819f90ddfdd48ac78beebe93b7ddc690b7d48d84a49465ff9ef189a9472d3`）：证据
`E:\k60-work\evidence\usblog-20261116-055237`，capture `state=captured` / `complete=true` /
**`bytes=27727`** / `portSeen=true` / `portOpened=true` / `stopReason=fastboot-return` /
`panicMarker="K60PANIC: ring kept"` / `resetMarker="K60 USBLOG: restart reason published"`，
console.log 27,727 B / 492 行 —— 第一次不是 0 字节。

晚启动生效、console 一直写到死点：

| 行 | 内容 |
|----|------|
| :193 | `[bluetooth] addon: linked blob bytes=1027584 records=106` |
| :194 | `[bluetooth] late: armed, waiting for the K60DATA deploy point` |
| :480 | `K60UILIB deploy bytes=113904 resid=0 error=0` |
| :481 | `[bluetooth] late: released by the K60DATA deploy point` |
| :482 | `[bluetooth] late: released, starting the full ladder` |
| :483 | `[bluetooth] full: power_on enter` |
| :484 | `[bluetooth] power: cold boot, rails not voted (k60bt_warm=0)` |
| :485 | `K60PANICFMT caller=0xfffffff007b83384 fmt=kmem_%s(%p, %zd, 0x%x): failed with %d @%s:%d` |
| :486 | `K60PANICARGS kmem_alloc(0xfffffff3447b1240, 1048576, 0x100021): failed with 3 @vm_kern.c:178` |
| :487 | `K60PANIC: ring kept; restart reason -> bootloader` |
| :489 | `K60METAL deploy files=6/6` |
| :491 | `K60DATA mounted ro=0 fstype=apfs` |

**解码**：`1048576` = 1 MiB；`3` = `KERN_NO_SPACE`（`osfmk/mach/kern_return.h:83`）；
`0x100021` = `KMEM_NOFAIL(0x1) | KMEM_PAGEABLE(0x20) | KMEM_PERMANENT(0x100000)`
（`osfmk/vm/vm_kern.h:313-337`）。这一组合正是 `io_map()` 走 **非 unmappable** 分支时传给
`kmem_alloc()` 的旗标（`osfmk/arm/io_map.c:120-129`）：

```c
kma_flags_t kmaflags = KMA_NOFAIL | KMA_PAGEABLE;
if (unmappable) kmaflags |= KMA_DATA; else kmaflags |= KMA_PERMANENT;
kmem_alloc(unmappable ? kernel_map : io_submap, &start, alloc_size, kmaflags, VM_KERN_MEMORY_IOKIT);
```

`io_submap` 是**全内核 8 MiB**（`io_map.c:65` `#define IO_MAP_SIZE (8ul << 20)`，`:76`
`kmem_suballoc(kernel_map, …, IO_MAP_SIZE, …)`）。全量阶梯往这个 8 MiB 里塞：

| 窗口 | 大小 | 出处 |
|------|------|------|
| GCC | `K60_GCC_SIZE 0x001F4200` ≈ 2 MiB | `patches/xnu/0500-k60-bt-qbt-new-files.patch:107` |
| TLMM | `K60_TLMM_SIZE 0x00100000` = 1 MiB | 同上 :96-97（注释：covers GPIO204 at +0xCC000） |
| APPS SMMU | `K60_APPS_SMMU_SIZE 0x00100000` = 1 MiB | `patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch:63` |
| UART / QUP / GIC | 16 KiB / 8 KiB / 64 KiB | 0500:75 / :78 / :101 |

同一进程里还有 60 处 `ml_io_map` 调用点（usblog 10、display 6、audio 8、touch 8、adsp 8 …）
共享这 8 MiB，另有 `K60_PSTORE_SIZE 0x200000`、`AW882XX_TLMM_SIZE 0xd0000` 等大块。
早启动时序下 8 MiB 已被占掉大半，再要 2 MiB 连续的 GCC 窗口 → `KERN_NO_SPACE` → panic。

**这解释了 §7.8 的致命集**：h1 打开 addon 门闩、h2 去掉冷启动早退、h3 把 stage 默认设 0，
三者齐备才让 `k60_bt_power_on()` 真的执行到 `k60_map(&k60.tlmm, …1 MiB…)` 与
`k60_smmu_bypass()`（再 1 MiB）；`0507` 的只读探针只 map gcc/uart/qup（无 TLMM/SMMU），
所以探针全过而全量阶梯 panic。d4 的晚启动把这次失败推到 K60DATA 挂载之后，console 才活到
把死因写出来。

**先例**：ADSP 线早就在同一处踩过并绕开——`patches/xnu/0613-k60-adsp-pas.patch:362-370` 的注释
写明 `ml_io_map()` 从 8 MiB 的 io_submap 分配、32 MiB 请求会 panic，改用
`ml_io_map_unmappable()`（进 kernel_map）。

#### 修法：0513 `patches/xnu/0513-k60-bt-io-windows.patch`（孪生 `patches/bt/0007`）

4,660 B，sha256 `0517653d13a18c966c5a57df4537da004d630ef04875e17a76e0263d2c812cad`，
单文件 `bsd/dev/qbt_k60.c`，+36/−4 行（2026-11-16 补了三行注释：0621 走另一条路，两者不叠加时各自动作）：

- 加 `extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, unsigned int flags);`
  与 `#define K60_WIMG_IO 0x7u`（`VM_WIMG_IO` = COHERENT|NOT_CACHEABLE|GUARDED，`osfmk/arm/memory_types.h:43`）。
- 新增 `k60_map_big()`：KERNEL 下走 `ml_io_map_unmappable(…, K60_WIMG_IO)`，语义与 `k60_map()` 相同
  （幂等早退 + `-ENOMEM` 契约）。
- GCC（阶梯 + 探针）、TLMM、APPS SMMU 四处改用它；UART/QUP/GIC 保持 `k60_map()`。
- 映射完 GIC 后打一行 `full: windows mapped, gcc/tlmm/smmu charged to kernel_map`，让「改动没生效」
  与「改动生效但仍死」在 console 上可区分。
- 位置：`patches/xnu/series` 末尾（233 条），紧随 0512，理由同 §7.5 的 0510/0620 教训——
  末尾插行不动任何后续补丁。

整条 series 重放（`git apply`，pristine `xnu-c465a9f8`）：**APPLIED=233 BAD=0**。
host 测试 `scripts/tests/test-k60-bt-0513-io-windows.py`：**TESTS OK 28 case(s)**。

**下一张图**：`bt-0513-iowin-late`（全量 0513 + `pong_bt_late=1`，与 d4 唯一差别是窗口分配器）。
判据：panic 消失且日志过 S9 ⇒ io_submap 就是死因；仍 panic 在同一行 ⇒ 1 MiB 不是 GCC/TLMM/SMMU
而是别的调用点，按 `K60PANICARGS` 的地址回查。

### 7.11 设计约束：`ml_io_map` 的 IO 子图是全内核共享预算（P-219，2026-11-16）

§7.10 的 panic 不是蓝牙一处写错，而是一条**全内核设计约束**被撞上：`osfmk/arm/io_map.c:65`
把 `io_submap` 固定成 `IO_MAP_SIZE (8ul << 20)`，`:76` 用 `kmem_suballoc(kernel_map, …)`
一次性预留；此后**每一个**走 `ml_io_map()`（非 unmappable 分支）的窗口都从这同一个 8 MiB 里切。
子图只预留 VA，没 map 的部分不花物理页——所以预算是**地址空间预算**，不是内存预算。

Lead 在已应用树上把可解析的调用点全部量了一遍（P-219，main `caad898`，
`scripts/check-io-map-budget.py` + `scripts/tests/test-check-io-map-budget.py`）：

| 统计 | 数值 |
|------|------|
| 可解析 `ml_io_map` 调用点 | 37 处，合计 `0x73a900` = **7.23 MiB / 8 MiB** |
| 尺寸是运行时变量的调用点 | 另 7 处（不在静态统计内） |
| `k60_usblog` 单文件 | ≈ 5.2 MiB（APPS SMMU 1 MiB ×3 + GCC 1 MiB ×2 + SPMI/IMEM/DWC3/EUSB2） |
| `qbt_k60` 单文件 | ≈ 4.2 MiB（GCC 2 MiB + TLMM 1 MiB + APPS SMMU 1 MiB + UART/QUP/GIC 小窗口） |

**约束（写进设计规则，不是一次性修法）**：给任何驱动加 IO 窗口，必须先算「本窗口 + 全树已有总和」，
7.23 MiB 的底数意味着**再加 1 MiB 就已经越界**；`check-io-map-budget.py` 在已应用树上量总和，
越界即红。这也解释了 §7.8 的致命集为什么是 {h1, h2, h3} 三者齐备：只有三者同时在场，
`k60_bt_power_on()` 才会走到第四次 `k60_map()`（TLMM 1 MiB），而 d1/d2/d3 三个开关都在它之后。

**两条修法并行、不可同时飞**（Lead 定）：

| 修法 | 做法 | 归属 |
|------|------|------|
| 0621 `k60-io-submap-budget` | 把 `IO_MAP_SIZE` 从 8 MiB 抬到 **32 MiB**（子图只预留 VA，不花物理页） | Lead / main |
| 0513 `k60-bt-io-windows` | BT 自己的大窗口改走 `ml_io_map_unmappable()`，记到 `kernel_map` | 本线 |

0513 的注释已补一句：main 的 0621 走另一条路（抬高 `IO_MAP_SIZE`），两者不叠加时各自动作——
所以两条可以各自单飞验证，但同一张图里只带一条。

**两条修法的代价对照（Lead 2026-11-16 要求写清）**：

| 维度 | 0621 抬预算（`IO_MAP_SIZE` 8 → 32 MiB） | 0513 搬窗口（`ml_io_map_unmappable`） |
|------|------------------------------------------|----------------------------------------|
| 花什么 | **只花 VA**：子图 `kmem_suballoc` 预留的是地址空间，没 map 的部分不占物理页 | 不占 `io_submap`，改记 `kernel_map`（同样只花 VA，但落进内核主映射） |
| 作用面 | 全内核**所有** `ml_io_map` 调用点都受益（37 处 / 7.23 MiB 的底数被一起放宽） | 只影响蓝牙这三个窗口（GCC 2 MiB / TLMM 1 MiB / APPS SMMU 1 MiB） |
| 代价 | 子图上限变大 ⇒ 地址空间预算的**失控风险变成全树的**：以后再有人加窗口不会立刻撞墙，缺陷被推迟而不是被发现 | 这三个窗口**不再走 `io_submap` 的统一 WIMG 策略**（`io_map()` 给非 unmappable 的是 `KMA_PERMANENT` + `VM_WIMG_IO`；unmappable 走 `KMA_DATA`），缓存属性由调用方自己保证，写错不会被框架兜住 |
| 归属 | Lead / main（`0621-k60-io-submap-budget.patch`，P-219） | 本线（`0513-k60-bt-io-windows.patch`） |

**为什么先飞 0621**：① 它修的是**缺陷本身**（8 MiB 对 7.23 MiB 的底数明显不够），
而 0513 是**绕开缺陷**——只有三个窗口搬走，下一个驱动还会撞上同一堵墙；② 它落在 main 上，
所有线（display / usb / wifi / adsp）都受益，不必每条线各自搬自己的窗口；③ 它只有一行
（`#define` 改数字），回归面比 0513 的 36 行小得多。0513 的价值因此不是「另一个修法」，
而是**收窄蓝牙自己的地址空间占用**这一整洁化项，等 0621 落地、d6 验证完再决定要不要合。

### 7.12 d5 / d6 配方：改了什么、排除了什么

| 配方 | series | 启动参数 | 这条配方要回答的问题 |
|------|--------|----------|----------------------|
| d5 `bt-d5-iomap` | main 227 条 + 0507..0512 六条（**不含 0513**，含 0621） | `k60bt=1 pong_bt_late=1` | 「抬高 IO_MAP_SIZE 是否足以让 `k60_bt_power_on()` 越过那次 1 MiB 分配」——排除了 0513 的代码路径，只验预算本身。**已飞 06:41–06:46：panic 消失，阶梯进到 `qbt_boot` 内部（§7.13）** |
| d6 `bt-d6-iowin`（待出） | **全量 0511 + 0512 + 0621 + 0513**（= d5 的 233 条再追加 0513，共 234 条） | `k60bt=1 pong_bt_late=1` | 「0513 单独是否够、和 0621 是否等价」——与 d5 的差别**只有窗口分配器**（0513 把 GCC/TLMM/APPS SMMU 三个大窗口改走 `ml_io_map_unmappable`），一次只加 0513 |

d6 的纪律：series 尾部在 `0512` 之后追加 `0513-k60-bt-io-windows.patch`（第 234 条），
参数与 d5 完全一致（31 项 / 598 B），构建前 `touch patches/xnu/series`（`ops_edit_file` 不改
mtime，P-194 会判 series 过期），并把 `0513` 与 `0621` 同列时的测试不变式放开（现在 host 测试
断言两者永不同列——出 d6 时这条断言要改成「d6 状态下允许同列」）。

判据（两条共用）：`:483` `full: power_on enter` 之后不再出现 `kmem_alloc(… 0x100021)` panic，
且出现 `power=1 result=…` 或 `full:` 后续行。仍 panic 在同一行 ⇒ 看 `K60PANICARGS` 的地址回查
是哪个窗口；d5 与 d6 都死 ⇒ 一起看 unmappable 分支的 `KMA_DATA` 旗标与 `VM_WIMG_IO`。

**d6 的判读树（Lead 定）**：d6 也起 ⇒ 两条修法**等价**，可以只用 0621（少一个补丁，0513 只留作
「收窄蓝牙地址空间占用」的整洁化项，不必进 main）；d6 死 ⇒ **0513 本身有问题**（`KMA_DATA` /
`VM_WIMG_IO` 旗标或 unmappable 分支的 pmap 属性），把它从分支上删掉。d5 已经在真机上把 panic
消掉，所以 d6 要回答的只剩「0513 这条路能不能走」——不再是「哪条能救命」。

### 7.13 d5 图 `bt-d5-iomap` 实飞：panic 消失、阶梯越过 io_submap，停在固件下载之后（2026-11-16 06:41–06:46）

**证据** `E:/k60-work/evidence/usblog-20261116-064150`：`boot.json` imageSha256
`491C62DE4C217CE63659DEFD0272584D205C828F3F432F377D5902C2679DFB3E`（= `bt-d5-iomap`）、
bootAccepted true / bootExitCode 0 / returnedToFastboot false；
`capture.json` state `captured-budget-complete`、bytes **224,863**、portSeen/portOpened true、
openErrors 0、stopReason `budget`、panicMarker null；
`console.log` **3,241 行**、sha256 `917B5AA981AB978564560839F78C1833F6242483E9F3A463FE2861B64CA8A20B`、
SpringBoard **132** 行、`getBytes:range` **0** 次、panic 标记 0（`K60PANICFMT` / `K60PANICARGS` /
`panic(` / `Debugger called` 全 0；`:475` 的 `K60PANIC: restart windows ready` 是重启窗口标记，
不是 panic）、心跳 16 条（t=15…240）。

**阶梯逐行**（行号即 console.log 行号）：

| 行 | 内容 | 说明 |
|----|------|------|
| :192 | `addon: linked blob bytes=1027584 records=106` | 内嵌 blob 链入 |
| :193 | `late: armed, waiting for the K60DATA deploy point` | 0512 门闩挂起 |
| :482 | `late: released by the K60DATA deploy point` | K60DATA deploy 点放行 |
| :483 | `late: released, starting the full ladder` | |
| :484 | `full: power_on enter` | |
| :485 | `power: cold boot, rails not voted (k60bt_warm=0)` | d4 的 panic 就在这行之后 |
| :486 | `smmu plan sid 0x483 slot 110 bank 72 … dma 0x90bc20000` | 0508 的 SMMU 旁路 |
| :487 | `smmu sid 0x483 … SMR 0x80000483 S2CR 0x48 CBAR 0x10000 CBA2R 0x1 SCTLR 0` | 回读确认 |
| :488 | `full: dma buffer and smmu bypass ready` | **d4 在这里 panic（kmem_alloc 1 MiB）** |
| :489 | `full: uart pins parked` | TLMM 1 MiB 窗口已拿到 |
| :493 | `clocks vote cbcr core=0x4220 … se=0x80004220` | GCC 2 MiB 窗口已拿到 |
| :494 | `full: qbt_boot enter` | 进入固件下载 |
| :707 | `QCA controller version 0x12110201` | 115200 下读到 SOC 版本 |
| :708 | `addon: serving 146068 0` | rampatch（`wcnhpbtfw*.tlv`）从内嵌 blob 供出 |
| :724 | `addon: serving 6442 0` | NVM（`*nv.bin`）从内嵌 blob 供出 |

**结论一：0621（`IO_MAP_SIZE` 8→32 MiB）解决了 panic。** 同一配方（含 0621、不含 0513）下，
d4 里 `:484` 之后必然出现的 `K60PANICFMT … kmem_%s(%p, %zd, 0x%x)` 与
`K60PANICARGS kmem_alloc(…, 1048576, 0x100021): failed with 3 @vm_kern.c:178` 全部消失，
smmu/gcc/tlmm 三个大窗口都拿到了 VA，阶梯推进到 `qbt_boot enter`。⇒ §7.10 的根因判断成立，
且 0621 这条修法在真实设备上足够。

**结论二：新的停点在 `qbt_boot()` 内部、NVM 供出之后。** 到采集窗口结束（06:46:14，约 240 s）
为止：`[bluetooth]` 只有 15 行，最后一行是 `:724` 的 NVM serving；`k60_power_result()` 的
`printf("[bluetooth] power=%u result=%d baud=%u firmware=%s\n", …)`（`patches/xnu/0500` 的
`k60_power_result`）**一次也没有出现** ⇒ `qbt_boot()` 在窗口内没有返回。注意 `k60_log` 只打印
`level <= 3`（`patches/xnu/0500` `k60_log`：`if (level <= 3) printf(...)`），
`bt_dev_info` 走 `qbt_linux_log(..., 6, ...)` 被静音 —— 所以「没有更多行」本身不代表卡住，
**真正有判据力的是缺 `power=` 行**（它是无条件 `printf`）。同一时刻系统其余部分完全正常：
桌面 132 行 SpringBoard、16 条心跳（t 到 240）、`bluetoothd`/`bluetoothuserd` 都起来了
（`:1044`/`:1053`），userspace 仍是 `:1345` marconi-bt 匹配不到 device tree 服务、
`:1346` MAC 全 0、`:1347` 拿到 `ee:98:c5:8a:6b:4e`、`:1459` Server attached 进消息循环。

**下一张图要加的观测（而不是换修法）**：`qbt_boot()` 里每个阶段一条 level-1 行
（rampatch 之后 / NVM 之后 / `qca_set_bdaddr` 之后 / 返回前），再加一条硬超时保证
`k60_power_result()` 一定会打印 —— 现在 `QBT_COMMAND_TIMEOUT` 是 10 s（`patches/xnu/0500`），
若某条命令反复重试则永远走不到结果行。这样下一张图能直接读出「卡在 rampatch→NVM 之间」
还是「卡在 bdaddr」。

### 7.14 d6 图 `bt-d6-iowin` 实飞：0513 与 0621 等价（2026-11-16 08:54–08:59）

**图**：`bt-d6-iowin`，配方 = 全量 0511 + 0512 + 0621（main 自带）+ 0513 在最后一条，series
234 条 / names+sizes `4305c6cc2821bcb7`；参数 `k60bt=1 pong_bt_late=1`（31 项 / 598 B）；
boot_img `9f4e2a90c5b5bf6a656eab738d7038e4a6b8a3da2c5dcc5cce5c5896f2e7a3b3`。
即 d5 的 233 条再加一条 0513（把 BT 的 gcc / tlmm / smmu 三个大窗口从 `io_submap` 搬到
`kernel_map`，P-219 的另一种修法）。

**证据** `E:/k60-work/evidence/usblog-20261116-085439`：`bootAccepted` true、`bootExitCode` 0、
`returnedToFastboot` false；capture `captured-budget-complete`、bytes 240,620、
portSeen/portOpened true、openErrors 0、stopReason `budget`、panicMarker null；
console.log 3,440 行、sha256 `1BCF8490…D1577`、SpringBoard **132**、`getBytes:range` **0**、
panic 标记 0、心跳 17 条。

**阶梯（16 行 `[bluetooth]`，与 d5 逐行对照）**：

| 行 | d6 内容 | d5 是否有 |
| --- | --- | --- |
| :193 | `addon: linked blob bytes=1027584 records=106` | 有 |
| :194 | `late: armed, waiting for the K60DATA deploy point` | 有 |
| :483/:484 | `late: released by the K60DATA deploy point` / `starting the full ladder` | 有 |
| :485/:486 | `full: power_on enter` / `power: cold boot, rails not voted (k60bt_warm=0)` | 有 |
| :487 | **`full: windows mapped, gcc/tlmm/smmu charged to kernel_map`** | 无（0513 新增） |
| :488/:489 | `smmu plan sid 0x483 slot 110 bank 72 …` / `smmu sid 0x483 … SCTLR 0` | 有 |
| :490/:491 | `full: dma buffer and smmu bypass ready` / `full: uart pins parked` | 有 |
| :496 | `full: qbt_boot enter` | 有 |
| :709 | `QCA controller version 0x12110201` | 有 |
| :710/:726 | `addon: serving 146068 0`（rampatch）/ `addon: serving 6442 0`（NVM） | 有 |

**判据与结论**：Lead 给的判据是「d6 起且出现 `QCA controller version` 行 ⇒ 0621 与 0513 等价，
0513 标 superseded」。实测两条都成立 —— 图起（SB 132 / panic 0 / K60DATA mounted / Early boot
complete）、`:709` 读到控制器版本、两个固件分片都被取走、`:487` 证明三个大窗口确实走了
`ml_io_map_unmappable` 分支（`kernel_map`），而 d4 在同样位置必现的
`kmem_alloc(…, 1048576, 0x100021): failed with 3` panic 一次都没有。⇒ **两条修法等价，
0513 是「BT 窗口不进共享子图」的整洁化项，保留文件、移出 series，随 0621 一起收口。**

**仍缺的观测（d5 遗留，未因 d6 改变）**：`power=1 result=…` 行依旧没有打印，
`qbt_boot()` 在 NVM 之后、`qca_set_bdaddr` 之前没有返回；userspace 侧
`:1487` marconi-bt 匹配不到 device tree 的 bluetooth 服务、`:1499` 只拿到
`ee:98:c5:8a:6b:4e`。这两项分别属于本线的阶段日志补齐（下一张图）与 Lead 的 ADT 节点工作。

### 7.15 d7 配方：`QBT_BOOT_BUDGET` 与逐阶段日志（2026-11-16 09:45）

d5 与 d6 都未打印 `[bluetooth] power=1 result=…`：日志确认 rampatch 阶段返回，随后出现 NVM 文件的 serving 请求，但不能证明 NVM 下载已完成或已经全部交给控制器。要判断 `qbt_boot()` 的段级进展与返回位置，需要内部阶段日志；d7 结果见 §7.18。

**为什么之前看不到**：`k60_log()` 只放行 level ≤ 3（`qbt_k60.c:1581`），
而 btqca 的进度行是 `bt_dev_info`（level 6，被静音）；`bt_dev_err` 是 level 3
（会打印，但只在失败时）。所以「没有输出」既可能是卡住，也可能是成功路径本来就不出声。

**为什么需要整体预算**：0514 之前，`qbt_boot()` 没有覆盖整个启动流程的期限。
每条命令各自的 10 s `QBT_COMMAND_TIMEOUT` 不能证明整个流程会在 10 s 内返回；
rampatch 的 600 多个理论分段也不是 d5/d6 已完成或已超时的段数。
`qca_download_firmware()` 在段返回错误时 `goto out`（0515 的上下文明确保留此逻辑），
因此撤回“一段超时后继续下一段、必然耗上小时”的旧解释。0514 增加启动总预算，
但检查仍依赖执行流回到 `run()`，并非能抢占阻塞回调的独立看门狗。

**0514 的两件事（只加观测 + 一个上限）**：

| 改动 | 位置 | 作用 |
| --- | --- | --- |
| `QBT_BOOT_BUDGET 90000000000ULL`（90 s） | `qbt_internal.h` | 启动上限常量 |
| `uint64_t boot_deadline;` | `struct qbt` | 一个字段，服务阶段恒为 0 |
| `q->boot_deadline=q->ops.now_ns(q->ops.context)+QBT_BOOT_BUDGET;` / `=0;` | `qbt_linux.c` `qbt_boot()` | 只在启动路径武装，返回前解除 |
| `if (q->boot_deadline && t >= q->boot_deadline)` | `qbt_core.c` `run()` | 超预算即 `-ETIMEDOUT`，并打印当时等的 opcode |
| `boot: command timeout op=0x%04x` | 同上 | 单条命令超时也报 opcode |
| 12 条 `qbt_linux_log(q,1,…)` 阶段行 | `qbt_linux.c` / `btqca.c` / `qbt_k60.c` | enter / soc version / set speed / uart setup / rampatch / nvm / hci reset / bdaddr check / set bdaddr / return / qbt_boot returned |

**边界（Lead 三·明确要求）**：不改状态机、不改时钟 / SMMU / 窗口配置、不动
`board.toml`。0514 的 host 测试 `scripts/tests/test-k60-bt-0514-boot-observability.py`
（33 例）逐条断言这件事：被删掉的行只有 `run()` 里那一行超时分支、新增行不含任何
`k60_map` / `ml_io_map` / `k60_gcc_set_se_rate` / `k60_smmu_bypass` / 既有开关字段。

**配方**：series 234（d5/d6 的 233 条 + 0514 在最后一条），参数
`k60bt=1 pong_bt_late=1`（31 项 / 598 B），tag `bt-d7-obs`。

**判据**：

| 观察 | 结论 |
| --- | --- |
| 出现 `boot: budget exhausted at op=0x….` | `run()` 首先观察到全局预算到期；opcode 是当时等待的命令，不足以裁定控制器、事件匹配或 TX 排空根因 |
| 出现 `boot: command timeout op=0x….` 且没有 budget 行 | 当前 `run()` 调用观察到单命令期限；后续是否继续由调用者的错误路径决定，不能据此定位最终停点 |
| 出现 `full: qbt_boot returned e=…` | `qbt_boot()` 已返回；先按 e 与后续 power 行判成功或错误，不能直接归因服务循环 |
| 最后一条是 `boot: nvm done` | 已越过该日志点；后续日志开关、返回路径、`qca_disable_soc_logging` / `HCI_RESET` 是待查范围，尚不能断言卡死 |
| 最后一条是 `boot: rampatch done` | 已越过 rampatch 日志点；NVM 路径为后续待查范围，完成程度未知 |
| 连 `boot: enter` 都没有 | 先核对镜像身份、采集完整性及是否进入启动路径，再查地址派生与 `k60_bt_power_on()`，不能仅凭缺行定因 |
| 出现 `full: qbt_boot returned e=0` 但之后缺少进展证据 | 可确认本次启动返回成功；核对 power 行与服务循环的调用、泵送和观测点。缺行本身不能证明循环未调用，也不代表完整蓝牙功能可用；d5/d6 没有该 e=0 行，不能套用 |
| 有 budget 行、但 `boot: command timeout` 计数为 **0** | 不能推出每段正常：预算分支在命令期限分支之前；阻塞跨过两者时只会打印 budget。d7 的具体更正见 §7.18 |

> budget 与 command timeout 必须分开统计，但统计不等于机制证明。
> d7 的 budget 2 次 / timeout 0 次不能排除挂起或慢路径，需 d8 的逐段 ret/dt/统计。

### 7.16 两条通用规矩（Lead 2026-11-16 认可，适用于本线以外的所有硬件线）

**规矩一：只加观测的补丁，测试必须断言它没有碰状态。**
0514 的 33 例 host 测试里有五条专门做这件事：被删掉的行只有 `run()` 里那一行超时分支；
新增行不含 `k60_map` / `ml_io_map` / `k60_gcc_set_se_rate` / `k60_smmu_bypass` /
任何既有开关字段；`QBT_COMMAND_TIMEOUT` 的值不变。静态契约检查证明这些禁改项在补丁文本中未被修改，
不能证明运行时等价，也不能排除 console 日志引入的时序扰动；0514 还明确新增整体预算。
其他线的观测补丁也应声明边界并做相应检查，设备结论仍须依赖实测。

**规矩二：每条命令的独立期限不能替代整个流程的预算。**
多次成功但缓慢的调用可以累积较长耗时；错误是否继续必须读调用者的返回路径，
不能用理论段数乘以单命令期限冒充实测。本路径遇段错误会退出下载；d7 的
90 s 总预算由 0514 新增，现有证据不能说明每段是慢还是阻塞。设计整体预算时：
- 预算只绑启动路径（`struct qbt.boot_deadline` 在服务阶段恒为 0）——启动卡死是 bug，
  运行期慢是另一个问题，不能用同一个期限；
- 总预算与单命令期限分开；90 s 是当前观测图选值，是否足够要靠实测，不能用 d7 的 timeout=0 证明；
- 超预算时打印**当时在等的 opcode**，否则「超时了」这句话没有定位价值。

### 7.17 单变量二分的完整方法（十一格矩阵的最终解释）

这是本项目至今最完整的一次「单变量二分」，四个 hunk 的 15 个非空子集飞了 11 个，
最后收敛到 `{h1,h2,h3}` 三者齐备才 silent、`h4` 无关。方法本身可以直接照抄到别的硬件：

1. **先把变量定义清楚**：每个 hunk 只做一件事（h1 开闸门、h2 去冷启动早退、
   h3 把 stage 默认设 0 让完整阶梯跑起来、h4 加一条 btqca 判据行），
   并且为每个 hunk 生成一个**单 hunk 补丁**（`0511a`–`0511d`），
   校验方式是「全量 − 其余三 hunk = 这个单 hunk」的字节级等式（`H*_EQUALS_FULL_MINUS_*`）。
2. **判据先写死、再飞**：这一轮的判据是「到桌面（SpringBoard > 100）」，
   不是「有没有蓝牙自己的日志」——因为被观测对象可能整段不跑（h3 把早启动探针拿掉后，
   `probe: armed` 就消失了，那是可观测性副作用，不是失败）。
3. **每格都要飞，飞过的要能查**：h2 单独那张 23:18 构建、04:48 才补飞，中间一直躺在
   盘上没人知道——这正是 P-218 `scripts/check-bisect-coverage.py` 要堵的缺口
   （拿 `build-manifest.json` 的 `boot_img` 与 `evidence/*/boot.json` 的 `imageSha256`
   做差集）。**二分要么飞满，要么在矩阵里显式标「已构建未飞」。**
4. **中途结论必须能被下一格推翻**：本轮先后得出过「h2 是必要条件」「致命集是 h3×h4」
   「致命集必须含 h4」三条结论，全被后面的格子推翻。写结论时要写清它依赖哪几格，
   新格子一到就重算，不要用叙述惯性保住旧结论。
0. **跟上游拆分编译单元时，先查跨文件 static**（0514 的编译错误给的教训）：
   `qbt_linux.c` 调 `now()` 失败，因为 `now()` 是 `qbt_core.c` 的 static。上游把这些函数
   放在同一个编译单元里，我们拆开了。正解是走 `q->ops.now_ns(q->ops.context)` 这类 ops 表，
   不是抓符号。2026-11-16 全量审计过一遍（八个 `qbt_core.c` static：`now` `drained`
   `clock_on` `flush` `control` `tx_advance` `event` `run`）：**除已修的 `now()` 外
   没有别的跨文件引用**，也没有跨文件同名函数；`btqca.c:330` 那处 `event` 是注释里的
   "vendor specific event"，不是调用。审计脚本 `E:/k60-work/scratch/bt-s4/late3/audit-static.py`。
   编译器只能抓到「未声明」，抓不到「同名但语义不同」——所以这一步要主动做一次。
   **升格为通用规矩（Lead 2026-11-16 定）**：以后凡是「修一个 static 引用」，都要顺带做一次
   同名审计，不能只修报错那一处。这是 P-204（用计数/名字代替语义）的另一种形状。

> 这套方法已提炼成跨线通用文档 **`docs/engineering/BISECT-METHOD.md`**
> （五步 + 三个反例，adsp / modem / wifi 直接引用，不必各写一遍）。本节保留本线的
> 具体数字与 evidence 路径，通用表述以那份为准。

5. **矩阵收敛之后，别停在「谁是真凶」**：十一格只回答了「哪几个 hunk 一起才死」，
   真正的死因是 d4 的 panic 行（`kmem_alloc(…, 1048576, 0x100021): failed with 3`）
   指向的 8 MiB `io_submap`（§7.10/§7.11）。二分给的是**范围**，panic/日志给的是**机制**，
   两者缺一不可。

### 7.18 d7 图 `bt-d7-obs` 实飞：NVM 路径触发全局预算，根因待定（2026-11-16 15:12 更正）

Lead 在 13:04:46 飞了 `bt-d7-obs`（boot.img `76a4260bc762a22a3dc683e4042a0a13a8dea41f04defccede8f9a96719c7512`），
证据 `E:/k60-work/evidence/usblog-20261116-130444`。这是蓝牙线上第一张**打印启动预算失败与返回路径**的观测图，不是根因证明。

**采集**：capture.json `captured-budget-complete`、221,001 B、portSeen/portOpened true、openErrors 0、
stopReason `budget`、panicMarker **null**、13:04:48 → 13:09:09；console.log 3,180 行、
sha256 `DFCA52D1523BCDD27B56C91BB269A0A39AB49EB9F0D82E7559A1F2D420378772`、SpringBoard **132**、
心跳 16 条（t=15…240）、无 panic。boot.json 里 `bootAccepted=false` / `bootExitCode=-1` 是
supervisor 在预算内没等到「已接受」的回执，**不是启动失败**（SpringBoard 132 与全部阶梯行都在）。

**阶梯与时间线**（行号为 console.log 实测，时刻用心跳 t 定位）：

| 行 | 内容 | 时刻 |
| --- | --- | --- |
| :193 | `addon: linked blob bytes=1027584 records=106` | t≈0 |
| :484–:491 | late released → power_on enter → cold boot（rails not voted）→ smmu plan/sid → dma+smmu bypass ready → uart pins parked | t≈15 |
| :495 | clocks vote（cbcr core=0x4220 core2x=0x4220 m=0 s=0x80000002 se=0x80004220） | t≈15 |
| :496/:497 | `full: qbt_boot enter` / `boot: enter speed=3000000 budget=90000ms` | t≈15 |
| :709/:710 | `boot: soc version done e=0` / `boot: set speed done e=0` | t≈15 |
| :711/:712 | `QCA controller version 0x12110201` / `addon: serving 146068 0`（rampatch） | t≈15 |
| :721 | `boot: rampatch done` | t≈30 |
| :729 | `addon: serving 6442 0`（NVM） | t≈45 |
| :2044 | **`boot: budget exhausted at op=0xfc00 waiting=1`** | t≈105 |
| :2045 | `QCA Failed to send TLV segment (-60)` | t≈105 |
| :2046/:2047/:2048 | 回退文件名重读同一份 NVM（`hpnv21g.bin`）→ 立刻再撞预算 | t≈105 |
| :2049 | `QCA Failed to request file: qca/hpnv21g.bin (-60)` | t≈105 |
| :2050–:2053 | `boot: uart setup done e=-60` / `boot: return e=-60 baud=3000000` / `full: qbt_boot returned e=-60` / **`power=1 result=-60 baud=3000000 firmware=`** | t≈105 |

**稳定事实（15:12 更正后的结论）**：rampatch 下载阶段返回，NVM 文件路径开始，
最后 `run()` 首先观察到 90 s 全局预算；错误经 `qbt_boot()` 与
`power=1 result=-60 baud=3000000 firmware=` 返回。`0xfc00` 是
`EDL_PATCH_CMD_OPCODE`，`waiting=1` 是布尔等待状态，不是“只等一轮”，
也不能单凭它区分事件未匹配、TX 排空或控制器未应答。`-60` 是 Darwin 的 `ETIMEDOUT`。
机器正常启动（SpringBoard 132、panic 0）与**蓝牙启动功能失败**（result=-60）同时成立。

**撤回两次过度推论**：本线最初“卡在 NVM 第一段”没有逐段证据；Lead 13:40 提出的
“command timeout=0 ⇒ 每段正常、只是慢”同样不成立。15:12 Lead 与本线共同撤回：

- `run()` 先判断 `boot_deadline`，再判断单命令 `deadline`（`0514:48-63`）。
  若 `pump` / `wait_until` 阻塞并跨过两者，恢复时会先打印 budget 并返回，
  command timeout 行不会出现。因此 budget **2** / command timeout **0** 只是日志事实，
  不能证明每段都在 10 s 内完成，也不能排除阻塞。
- d7 没有逐段计数；6,442 B 按 243 B 计算约 27 段只是文件的理论分段数，
  不能假设未完成的 NVM 已完成 27 段，更不能用 65 s ÷ 27 得到“实测 2.4 s/段”。
  心跳只给粗粒度时间，不能代替每段耗时与返回值。
- 两次 `addon: serving 6442 0` 包含 `wcnhpnv21g.bin` → `hpnv21g.bin`
  fallback 重试。预算已经耗尽时，重试可立即失败；它不证明第二次成功传输。
- 是慢、阻塞、事件不匹配还是 TX 排空，现有 d7 日志不能裁定，须读 d8。

**d8 判读纪律（替代原“三支直接指定 d9 修法”的表）**：

| 观察 | 可得结论 / 仍不能得出的结论 |
| --- | --- |
| 某次 PATCH / NVM 的逐段 `e=0`、短 `dt_ms` | 该次调用成功返回；是否整文件完成还要看对应 `tlv done ... ret=0` 及 TLV final 状态 |
| 全局 `sent/acks` 增长 | 它们是整个 boot 的累计，含 rampatch（约 602 段）和 fallback；必须按每次 type/attempt 的基线取差，不能拿全局 sent≈27 判 NVM 完成 |
| `tlv seg` 的最后一段 `e!=0` | 日志在函数返回后才打印，可能直到预算耗尽才出现；这一段计入 `segs` 的尝试数，但不计作成功完成 |
| 缺少文件进入前的基线 / 明确 attempt 标识 | 按相邻 serving、逐段 i、type 与 done 行重建并标明不确定量，不能把 PATCH/NVM/fallback 混算 |
| 长 `dt_ms`、acks 不变或缺少后续段行 | 只限定观测停点，不能直接断言事件匹配或 TX 排空根因；结合 ret、done、final 与预算/复位证据进一步判断 |

每段打印增加 console 成本，d8 的耗时只代表**该观测镜像**；与 d7 心跳估时对比必须注明
观测扰动。**不预做 d9，不抬预算、不改 event 匹配**；保留现有 d8，实测后再选窄化观测或修法。

### 7.19 d8 配方：0515 打印 TLV 段速与计数器（2026-11-16 13:20）

d7 把问题从「什么都不打」缩到「NVM 路径预算失败、根因待定」，但它看不清**每段的实际耗时**：`struct qbt_stats`
里 `tlv_sent` / `tlv_acks` / `tlv_final_status` 早就在维护（`qbt.h:32-38`），可内核侧从未打印过。
0515 只做这件事 —— 把已有计数器与段速打出来。

| 改动 | 位置 | 作用 |
| --- | --- | --- |
| `tlv seg i=%u size=%d dt_ms=%u e=%d sent=%llu acks=%llu` | `btqca.c` `qca_download_firmware()` 循环 | 每段一行，`dt_ms` 用 `ops.now_ns()` 前后相减 |
| `tlv done type=%d segs=%u sent=%llu acks=%llu final=%llu ret=%d` | `out:` 之前 | 每次下载调用的汇总，PATCH / NVM / fallback attempt 分开，计数仍为 boot 全局累计 |
| `power=` 行追加 `tlv_sent=%llu tlv_acks=%llu tlv_final=%llu` | `qbt_k60.c` `k60_power_result()` | 失败路径也带计数器 |

**边界**：`QBT_BOOT_BUDGET`(90 s) / `QBT_COMMAND_TIMEOUT`(10 s) / `MAX_SIZE_PER_TLV_SEGMENT`(243) /
`dnld_mode` / `dnld_type` / 段表 / SMMU / 时钟 / 窗口 / `board.toml` 全部不动。host 测试
`scripts/tests/test-k60-bt-0515-tlv-counters.py`（28 例）把这条边界逐项断言，包括「传给
`qca_tlv_send_segment()` 的参数逐字未变」与「被删掉的行只有旧调用 2 行、旧 printf 2 行」。

- 补丁 `patches/xnu/0515-k60-bt-tlv-counters.patch`（2,727 B，+38/−4，sha256
  `120c4d57d1bf72bdee18770a520367bd68d46c1c96ffb185c5bbf51ec46c4cd6`），孪生
  `patches/bt/0009-k60-bt-tlv-counters.patch` 字节相同；全量重放 234 条 `BAD=0` 后再单独 apply 成功。
- **配方**：series 235（`… 0512 / 0514 / 0515`），参数 `k60bt=1 pong_bt_late=1`（31 项 / 598 B），
  tag `bt-d8-tlv`。
- **判据**：见 §7.18 的判读纪律；按 type/attempt 分开、累计取差、失败段不算完成，并注明 console 观测扰动。d8 已完成观测；不预做 d9。

- **已构建（2026-11-16 13:56:24）**：`boot_img 0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`
  （201,887,744 B）、`kernel_built 6c96f7ccd641d0f751cd76669312c7279055e3232415d5b2d505b28c38065331`（106,598,400 B）、
  series {235, names+sizes `f7aa7d63470b891d`, file `9a2cfd416b5250854f8fda38d03ca095a631be296e0679bf9522ba445e73cbb8}`、
  head `91dcd07`、dirty 0；本树 `verify-boot-image: OK` + `check-image-args: OK (31 arguments, 598 bytes)`。

### 7.20 d8 实飞：PATCH 软件路径返回成功，NVM 两次尝试均失败（2026-11-16 16:58）

Lead 仅用 `fastboot boot` 飞行 `bt-d8-tlv`，未 flash。证据目录为 `E:/k60-work/evidence/usblog-20261116-164726`；`console.log` 为 3,749 行 / 255,020 B，sha256 `1ef1f5abf55f6036f36c729779aab3de53f667e782e9ba3492fb332109be7cd2`。`boot.json` 记录 `bootAccepted=true`、`bootExitCode=0`、`returnedToFastboot=false`；`capture.json` 记录 `complete=true`、`portSeen=true`、`portOpened=true`、`panicMarker=null`、`resetMarker=null`、`stopReason=budget`。SpringBoard 子串为 129 次、分布在 128 行；另有 17 条心跳、`getBytes:range=0`，未发现 panic/reset 标记。采集器的 `stopReason=budget` 是采集时限，不是蓝牙的 90 s 启动预算。

以下基线为按相邻 attempt 还原的 `(sent, acks)` 累计对；原图没有每个 attempt 的独立起始行，因此不是新增的起始快照。PATCH 前 `(0,0)` 来自本次首次下载及核心初始计数；NVM/fallback 基线取前一个 done，不能把全局数直接当本次成功段数。

| attempt / console.log 锚点 | 调用与返回 | 累计基线 → 结束 / 差值 | 关键结果 |
| --- | --- | --- | --- |
| PATCH / type=1；:713-1331 | i=0..601，共 602 次；602 次 `e=0`，大小合计 146,068 B；前 601 次 `dt_ms=0`，最后一次 10001 | `(0,0) → (602,1)` / `sent +602, acks +1` | :1330 `done segs=602 final=0 ret=0`，:1331 `rampatch done`；仅证明软件路径返回成功，不证明控制器逐段确认 |
| NVM 首次 / type=2；:1338-2781 | i=0..6；i=0..5 为 `e=0`，`dt_ms=10000,10000,10000,10001,10001,10001`；i=6 为 `e=-60, dt_ms=15` | `(602,1) → (609,7)` / `sent +7, acks +6` | :2778 `budget exhausted`，:2781 `done segs=7 final=0 ret=-60`；没有 NVM 完成标志 |
| NVM fallback / type=2；:2782-2806 | i=0..20；i=0..19 为 `e=0, dt_ms=0`；i=20 为 `e=-60, dt_ms=16` | `(609,7) → (630,28)` / `sent +21, acks +21` | :2803 再次 `budget exhausted`，:2806 `done segs=21 final=1 ret=-60` |

合计 630 次段调用，其中 628 次软件返回 `e=0`、2 次返回 `e=-60`；最终 :2807 `qca/hpnv21g.bin (-60)`、:2810 `qbt_boot returned e=-60`、:2811 `power=1 result=-60 ... tlv_sent=630 tlv_acks=28 tlv_final=1`。两次 `serving 6442` 只记录大小，没有文件名/哈希，不能证明实际内容相同；理论 27 段不等于本次执行或完成段数。

**计数与计时边界**：`segs` 在段函数返回后递增、包括失败尝试（`patches/xnu/0515-k60-bt-tlv-counters.patch:23-36`）；`sent` 在命令入队时增加，不是硬件收到的证明（`patches/xnu/0500-k60-bt-qbt-new-files.patch:1810-1816`）。同补丁 :1620-1623 的 `acks` 连非零 status 的 TLV report 也计入，`final` 是最后一次 report 的 status，不是确认数；没有逐包事件/真实 RX 时间，不能按 ACK 数建立逐段对应关系。`dt_ms` 是整毫秒截断，0 只表示观测区间不足 1 ms，不是耗时为零；计时包含该调用周围的统计成本，console 输出还会扰动后续时序。

**期限检查顺序**：`run()` 先 `pump/qbt_step`，再检查错误和完成谓词，只有未完成时才检查 `boot_deadline`，最后检查单命令 `deadline`（`patches/xnu/0500-k60-bt-qbt-new-files.patch:1791-1805`、`patches/xnu/0514-k60-bt-boot-observability.patch:43-64`）。因此跨过期限后才处理的响应仍可能先满足完成谓词；两个期限均过期时 budget 分支会隐藏 command-timeout 行。这个顺序是源码事实，不是对本次响应到达时刻的实测证明；它也不单独解释为何首次每段约 10 s、为何预算过期后的 fallback 仍连续快速 `e=0`。

**结论与未知**：d8 是有效诊断观测，不是蓝牙成功图；NVM 两次尝试均未完成，初始化 `result=-60` 与系统正常启动同时成立。现有日志不能区分控制器确认、缓存/队列中的晚到响应、重试语义与具体等待路径。保留独立 reassessment 的历史 HOLD，不以本次观测抹掉它。Lead 已交付冻结源码的宿主时序模型，软件事实与 d8 计数分组见 §7.21；真实 HCI adapter 与完整 fallback 的宿主证据已在 §7.22 实现并运行（test-only `916aaaa`，22 场景 / 24 变异 / 90 项断言），它仍不能证明控制器、UART/DMA/IBS 或蓝牙可用。未来观测若需独立起始计数及 response status/真实 RX 时间，须另行批准。当前不改运行代码，不抬预算、不改下载模式、分片、状态机或地址，不预做 d9、不再上机。
### 7.21 d8 宿主时序模型：哪些软件事实已证明、哪些仍是 UNKNOWN（2026-11-16 18:58）

Lead 在 `test/bt-d8-timing-model` 分支交付了 d8 宿主时序模型：代码 `0ccdfbba5ab626bf99be65d973e45b87e389f59c`，文档 `a1858958ccb4a5b84d44c2eaac643b4b614ca32f`，台账 `bce47bf99415e7d4418f9f48f8d2a48eb4b0d22a`。它抽取真实 `qbt_core.c`，以假时钟、假 pump、假平台回调执行实际 `event()` / `qbt_step()` / `run()` / `qbt_command()`；0514 按原 hunk 应用，0515 的观测 block 单独验证。结果 34 场景 / 84 断言 / 8 个输入拒绝守卫，`rc=0`；输入身份检查返回 `RECORDED_INPUTS_MATCH`，17 个回归夹具全过。

这是**冻结源码的宿主软件行为**（d8 manifest、frozen-before/after、235 条 series 的补丁字节、0500/0514/0515 源码 SHA、应用日志顺序与 `boot.img` SHA 都被绑定），不是 d8 时间线回放，也不是控制器、UART、DMA、IBS 或硬件行为。

**宿主模型已证明的软件事实**（判读 d8 时必须按这些事实读日志）：

| # | 已证明的软件事实 | 对 d8 判读的含义 |
| --- | --- | --- |
| 1 | `run()` 顺序是：pump/step → 错误 → 完成谓词 → 全局 `boot_deadline` → 单命令 `deadline`；两处期限比较都是 `>=`。 | 阻塞跨过两个期限时，budget 分支先打印并返回，command-timeout 行可以完全不出现。d7/d8 的 timeout 计数不能当作“每段都正常”的证据。 |
| 2 | 睡眠/等待被夹到单命令期限，但**不夹到全局 boot 期限**。 | 一次长睡眠可以跨过 90 s；budget 行只说明恢复执行时已过期，不能说明睡眠期间控制器或 TX 的状态。 |
| 3 | 晚到事件在期限检查前满足完成谓词，即可返回成功。 | 成功返回不代表响应在期限内到达；现有日志没有真实 RX 时间，不能把成功返回等同于硬件按时应答。 |
| 4 | 全局 TLV `acks`/`final` 的自增与“是否匹配本次等待”无关；非零 status 的 ack 不会置 `complete`。 | `acks` 是 report 计数，不是确认数；`final` 是最后一次 report 的 status，不是成功数。某次 attempt 的 `acks` 增长不能证明该次等待被回答。 |
| 5 | 同一 opcode 的旧事件可以完成新的等待。 | 相邻 attempt 的 `sent/acks/done` 只能按基线取差并标不确定，不能证明事件属于本次命令；d8 的 attempt 边界必须靠 `done` 行和相邻 `serving` 重建。 |
| 6 | 新命令会清 `complete`，但保留预算与统计。 | 不能用 `complete` 跨命令判断；`segs/sent/acks` 是 boot 全局统计，必须按 PATCH / NVM / fallback 分组。 |
| 7 | 0515 的 `dt_ms` 是整数截断；失败调用也计入 `segs`。 | `dt_ms=0` 只表示观测区间不足 1 ms，不是零耗时；`segs` 包含失败尝试；完成必须看对应的 `done ret=0` 与 final 状态。 |

**d8 设备观测的计数分组**（设备事实，不是宿主模型 replay；明细见 §7.20）：

| attempt | 调用数 / 软件返回 | 累计基线 → 结束 / 差值 | 完成判据 | 与宿主事实的关系 |
| --- | --- | --- | --- | --- |
| PATCH `type=1` | 602 次；602 次 `e=0`（大小合计 146,068 B） | `(0,0) → (602,1)` / `sent +602, acks +1` | `done segs=602 final=0 ret=0`，随后 `rampatch done` | 只证明软件调用与全局计数路径；不证明控制器逐段接受。 |
| NVM 首次 `type=2` | 7 次；前 6 次 `e=0`（dt_ms 约 10,000），第 7 次 `e=-60` / 15 ms | `(602,1) → (609,7)` / `sent +7, acks +6` | `done segs=7 final=0 ret=-60`；无 `nvm done` | `acks` 只增 6 而调用 7 次；可能是第 7 次没有 ack，不能仅凭差值证明非零 status 路径。budget 在命令期限之前，不能据此算每段耗时。 |
| NVM fallback `type=2` | 21 次；前 20 次 `e=0` / 0 ms，第 21 次 `e=-60` / 16 ms | `(609,7) → (630,28)` / `sent +21, acks +21` | `done segs=21 final=1 ret=-60` | 同 opcode 旧事件与全局计数语义使 `acks +21` 不能等同 21 段成功；`final=1` 是最后 status。 |
| 合计 | 630 次；628 次 `e=0`、2 次 `e=-60` | `sent 630 / acks 28 / final 1` | 两次 NVM 均 `ret=-60` | 初始化失败与系统正常启动同时成立；不构成蓝牙功能验收。 |

**计数语义硬事实（Lead 2026-11-16 19:31）**：`done` 行的 `segs` 是本次 `qca_download_firmware()` 调用的段数；`sent/acks` 是 `qbt_boot()` 入口 `memset()` 之后整个启动的累计。fallback 在 `qca_uart_setup()` 内部改名重试，不回到 `qbt_boot()`，所以 `sent/acks` **不重置**。d8 实测：NVM 首次 `done segs=7 sent=609 acks=7`，fallback `done segs=21 sent=630 acks=28`。任何断言“fallback 后 sent/acks 被重置”的测试都与实测矛盾，必须红。这也是「用计数代替语义」的反例：`segs` 是每次 attempt 的语义量，`sent/acks` 是 boot 全局累计量，两者不能混用。

**仍是 UNKNOWN（宿主模型与 d8 日志都不能回答）**：

- 控制器是否逐段接收/接受、TLV final 与硬件实际状态；完整 NVM 是否写入。
- UART/DMA/IBS 的真实时间线、真实 RX 时刻、晚到/缓存响应、TX 排空与重试语义。
- 首次 NVM 每段约 10 s、预算过期后 fallback 仍连续快速 `e=0` 的具体机制；d8 没有独立起始快照，`serving 6442` 也没有文件名/哈希，不能证明两次内容相同。
- 宿主模型没有 replay d8 的时间戳，不能证明 d8 实际走了某条被建模的分支；它也没有覆盖编译产物到 payload 的对应、flash 门禁或硬件行为。

**结论**：宿主模型把“源码允许什么行为”与“d8 实际发生了什么”分开：前者已由 34 场景/84 断言证明；后者仍只有 §7.20 的观测与计数，不能把任何候选机制升级成硬件结论。d8 仍是诊断观测，不是功能验收、main 基线或 d9 授权。

### 7.22 真实 HCI adapter 与完整 firmware fallback 的宿主证据（2026-11-16 已实现）

**状态与边界（2026-11-16 19:31 批准，20:53 实现并运行）**：Lead 批准范围就是本节的被测层表 + 场景矩阵 A/B/C + 六条负向控制，不扩。只允许 **test-only** 与 **docs-only** 两类提交，英文、分开提交、推到 `feat/bt-research`；不改运行代码、series、`board.toml`、预算、下载模式、段长、状态机、地址；不重建、不上机、不预做 d9。实现结果见下，Lead 的只读交叉测试没有被编辑。

**实现与运行证据（2026-11-16 20:53）**：

- 代码：`scripts/tests/test-bt-d8-adapter-host.py`（fail-closed runner）与
  `scripts/tests/fixtures/bt-d8-adapter-harness.c`、`bt-d8-adapter-support.c`；
  test-only 提交 `916aaaa552b8470fa63b992dac2a525226b7288d`。
- 命令：`python3 scripts/tests/test-bt-d8-adapter-host.py`（默认读取保留产物
  `/mnt/e/k60-work/artifacts/bt-d8-tlv`，也可显式传 `--artifact`）。
- 运行结果：`RAW_RC=0`，`TESTS OK: 90 case(s), 0 failure(s)`。90 = 19 项输入绑定
  + 3 项源码重建 + 22 个场景各 2 项（rc 与自检）+ 24 个变异孪生；日志
  `E:/k60-work/scratch/bt-s4/late3/run17.log`。
- 输入绑定负向证据：把 manifest 复制后追加一个换行再运行，得到
  `FAIL: manifest sha256 - 8151ea11e6edf808c689c58ad5fea82e870bf128d50daed35d340af6986f44e9`
  与 `REFUSED: manifest bytes differ from the retained d8 manifest`，退出码 2；
  没有回退到 latest，也没有读当前工作树。
- 回归：`test-k60-bt-0514-boot-observability.py` 33 项、
  `test-k60-bt-0515-tlv-counters.py` 28 项仍为 `TESTS OK`。

**批准时新增的实现约束**：

1. 输入绑定必须 fail-closed：manifest `3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0`、frozen-before/after、235 条补丁字节、head `91dcd0761aeb035c15de743478851fb8ce0c0417`、`boot.img` `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b` 任一不符即拒绝运行；不许 fallback 到 latest、不许读当前工作树状态、不许 fuzz 上下文。
2. 合成 TLV 与事件时刻只是合成输入：断言与日志都要拒绝写成“真实固件内容”或“控制器已接受”；文件名只用于区分 attempt。
3. 每条正向断言必须有能真红的孪生，并说清怎么让它红（改哪个合成输入或断言取反），不能只写“预期失败”。
4. 唯一归属：落地后 BT 宿主时序测试以本仓这一份为准（本线 owner）。Lead 的 `E:/hackios/k60-lead/scripts/tests/test-bt-d8-host-timing.py` 只是独立交叉核对，本线不得编辑那棵树；任何要进 main 或写进 ⑦ 的动作之前，必须先交一张断言级重叠表（两边都有/只有本线有/哪份权威），由 Lead 决定退役哪一份。不允许两份长期各自演化。
5. 测试只证明冻结源码上的软件路径，不替代设备 ⑧；`HOST-ONLY` / `NOT RUN` 清单必须出现在输出里。

**为什么要补**：§7.21 的宿主模型覆盖真实 `qbt_core.c`，但把 `qca_tlv_send_segment()` 换成了假边界；它没有执行 `qbt_linux.c` 的 Linux HCI adapter，也没有执行 `btqca.c` 的 `qca_download_firmware()` 主/回退全流程。d8 的 630 次段调用虽然来自真实镜像，仍缺少“adapter 如何把命令变成 qbt 命令、失败如何返回、fallback 如何在同一 `struct qbt` 上重试”的宿主证据。

**输入与重建（只读）**：

- 绑定 d8 manifest `3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0`、frozen-before/after、235 条 series 的补丁字节、head `91dcd0761aeb035c15de743478851fb8ce0c0417` 与 `boot.img` SHA `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`。
- 从 235 条 series 中逐条应用所有触及 `bsd/dev/qbt/` 的补丁（0500 新建，0511/0514/0515 修改），使用精确上下文而不信任 hunk 行号；任何上下文不唯一/不匹配即失败，不做 fuzz，不读工作树当前状态。
- 生成物放仓库外工作目录；只编译宿主可执行文件，不进入 XNU 构建、不生成 payload、不碰设备。

**被测真实代码与假边界**：

| 层 | 真实执行 | 允许的假件 |
| --- | --- | --- |
| qbt 核心 | `qbt_core.c` 全部（H4 解析、event、qbt_step、run、qbt_command、qbt_delay） | `qbt_platform` 的时钟、pump、wait_until、uart_write、uart_drained、receive、allocate/release、firmware_get/put 由夹具提供。 |
| Linux HCI adapter | `qbt_linux.c` 的 `__hci_cmd_sync_ev` / `__hci_cmd_sync` / `__hci_cmd_send` / `__hci_reset_sync` / `request_firmware` / `release_firmware` / skb 与分配助手 / `qbt_boot()` 的失败清理 | firmware 内容、事件到达时刻与 event 字节是合成输入；不假装真实固件或控制器。 |
| btqca 下载 | `btqca.c` 的 `qca_download_firmware()`、`qca_tlv_check_data()`、`qca_get_alt_nvm_file()`、`qca_uart_setup()`、`qca_set_bdaddr()`、fallback 调用链 | 固件文件为最小合法 TLV 合成字节；文件名只用于区分 attempt，不声称与 d8 的 6,442 B 相同。 |

**场景矩阵（每个场景都要有正向与破坏不变量的负向控制）**：

| 组 | 场景 | 期望 |
| --- | --- | --- |
| A. adapter 语义 | `__hci_cmd_sync_ev` 收到 status=0 的 command complete | 返回 skb，长度与首字节符合 adapter 约定，`qbt_command` 返回 0。 |
| A | status 非 0 | adapter 返回 `-EIO`；调用方拿到负值，不把 report 当成功。 |
| A | 空的 command-complete payload（`adapter_short`） | 返回 `-EIO`；不把短响应当完整事件。 |
| A | version 事件的 payload 超过声明长度（`adapter_version_overlong`） | 返回 `-EILSEQ`；不把截断的 version 当有效值。 |
| A | 无事件、跨过命令期限 | `-ETIMEDOUT`；检查没有误用 boot budget。 |
| A | 晚到事件先满足完成谓词 | 返回成功，但夹具记录事件注入时刻晚于名义期限；断言这是软件顺序，不是硬件按时。 |
| A | 同 opcode、在 TX 之前到达的事件（`adapter_early`） | 能完成新的等待；夹具显式标注“早到事件”，只证明软件顺序，不覆盖跨两次等待的旧 report（后者归 Lead 的时序测试）。 |
| A | `__hci_cmd_send` 的 skip 路径 | 只入队、不等完成；不产生 complete，不改变 `qbt` 的 service 状态。 |
| B. 完整下载 | PATCH 主文件多段，最后一段强制 `QCA_SKIP_EVT_NONE` | 每段经真实 adapter；最后一段有 ack；`done type=1 segs=N final=0 ret=0`。 |
| B | 把已是 `.bin` 的名字作为 `firmware_name` 交给 `qca_uart_setup()`（`download_alt_already_bin`） | 只请求同名 NVM 一次，失败即返回 `-ENOENT`；不生成另一个 alt 名。覆盖 setup 级对 `.bin` 的不重试，不是裸 helper 调用。 |
| B | `qca_uart_setup()` 的 NVM 主文件缺失且 `firmware_name` 为 NULL（`download_nvm_missing`） | setup 级回退到 `qca/hpnv21g.bin` 并成功（`e=0`）；断言主文件失败行与 fallback 请求行都出现。 |
| B | 非 `.bin` 扩展名的 alt 文件名 helper（合成输入，不声称是 d8 路径） | `qca_get_alt_nvm_file()` 只替换一次扩展名；第二次仍失败时返回原错误；记录两个文件名。 |
| B | NVM 主下载在段 N 返回错误 → `qca_uart_setup()` 的 fallback 改名并第二次下载 | 第二次使用 fallback 文件名与同一合成字节；成功则 `ret=0`；失败则保留第二次错误。 |
| B | fallback 下载也失败 | 最终错误来自 fallback；`done` 的 `type/ret` 可区分两次 attempt。`done segs` 只算本次 attempt 的段数，但 `sent/acks` 仍是 boot 全局累计（见 §7.21 计数语义硬事实）；断言 fallback 重置 `sent/acks` 的测试必须红。 |
| B | firmware_get 返回错误/`release_firmware` 调用次数 | 请求失败不 release；成功路径恰好 release 一次；避免 double-free。 |
| C. 失败/复位边界 | rampatch 失败 | `qca_uart_setup()` 立即返回，不进入 NVM；`qbt_boot()` 清理 `startup_owner`、`boot_deadline`、`ibs`、命令偏移与状态。 |
| C | NVM 失败 | 返回原错误；`qbt_boot()` 的 `info.state=3`、`info.error=e`，不得残留 `boot_deadline` 或半条命令。 |
| C | HCI_RESET / bdaddr 失败 | 错误向上返回；fallback 不会跨过 reset 失败被错误复用；`qbt_boot()` 的统计与状态按源码路径变化。 |
| C | 成功路径 | `startup_owner` 释放、`boot_deadline=0`、`info.state=2`、`stats.resets++`；服务阶段字段不被测试改写。 |

**矩阵与夹具场景的对应**：A 组 8 个 `adapter_status` / `adapter_short` / `adapter_timeout` / `adapter_tlv_status` / `adapter_late` / `adapter_early` / `adapter_version_mismatch` / `adapter_version_overlong`；B 组 8 个 `download_success` / `download_fallback_success` / `download_fallback_failure` / `download_nvm_missing` / `download_patch_fallback` / `download_skip_mode` / `download_alt_already_bin` / `download_alt_name`；C 组 6 个 `boot_success` / `boot_failure_cleanup` / `boot_fallback_success` / `boot_patch_fail` / `boot_bdaddr_fail` / `boot_reset_fail`。场景名就是运行日志与 `--scenario` 的键。

**负向控制（每条正向断言都要有能失败的孪生）**：

- 把 status 非 0 当成功 → 测试必须红。
- 把同一个 opcode 的旧事件当本次响应 → 测试必须红。
- 让 fallback 不重试或重试两次 → 测试必须红。
- 在失败路径保留 `boot_deadline` / `startup_owner` → 测试必须红。
- 把 `segs` 的失败尝试算作完成 → 测试必须红。
- 断言 fallback 后 `sent/acks` 被重置 → 测试必须红（与 d8 的 `sent 609→630` / `acks 7→28` 矛盾）。
- 把合成 TLV 当成真实固件内容或控制器接受 → 文档与断言都必须拒绝这种表述。

实现里共 24 个变异孪生，按层分组：A 组 8 个（`adapter_status_status_zero`、`adapter_short_not_short`、`adapter_timeout_answers`、`adapter_tlv_status_zero`、`adapter_late_early`、`adapter_early_disabled`、`version_mismatch_full`、`version_overlong_exact`）；B 组 9 个（`download_one_segment`、`download_no_fallback`、`fallback_failure_succeeds`、`nvm_primary_present`、`patch_primary_present`、`skip_mode_sync`、`alt_already_bin_name`、`alt_name_bin`、`firmware_release_count`）；C 组 7 个（`boot_success_speed`、`boot_failure_succeeds`、`boot_no_fallback`、`sent_acks_reset`、`boot_patch_fail_fallback`、`boot_bdaddr_fail_ok`、`boot_reset_fail_ok`）。每个孪生都真的把对应场景判红后再退出 0；例如 `firmware_release_count` 的红行是 `patch and NVM buffers are each released once: requests=2 puts=0`，`version_overlong_exact` 是 `overlong version payload is -EILSEQ: 0`，`boot_bdaddr_fail_ok` 是 `bdaddr failure is returned: 0`。

**验收标准**：

1. 全部场景在宿主确定性执行，退出码 0；每个场景有唯一名称与失败行号。
2. 输入绑定失败（manifest/frozen/series/patch SHA/boot.img 任一不符）必须拒绝运行，不能 fallback 到 latest 或其他 checkout。
3. 负向控制全部按预期失败；正向控制全部通过。
4. 输出明确打印 `HOST-ONLY` 与 `NOT RUN` 清单；日志可复现，不需要网络、设备、XNU 构建或 root。
5. 本仓权威分区与 ⑦ 补充证据候选见下；是否写入账本由 Lead 裁决。它不替代设备 ⑧。

**断言级权威分区（2026-11-16 21:26 Lead 裁决后重写）**

原则：两套测试都保留，但**每条断言只有一个 owner**；owner 之外只做交叉引用，不复制实现。
Lead 的 `E:/hackios/k60-lead/scripts/check-bt-d8-inputs.py` 优先承担输入身份；本仓运行前仍做同一身份的
拒跑，进 main/⑦ 前缩成调用它加本仓三条重建源码 SHA，不再维护第二份身份实现。

| # | 断言（一条一行） | owner | 引用位置 | 另一侧 |
| --- | --- | --- | --- | --- |
| 1 | d8 冻结身份：manifest/head/dirty/boot.img/frozen/235 条 series/namespace | Lead 输入检查器 | `E:/hackios/k60-lead/scripts/check-bt-d8-inputs.py:74-133`；`test-bt-d8-host-timing.py:85-111` 的 CLI 守卫 | 本仓 `test-bt-d8-adapter-host.py:111-191` 暂作运行前拒跑；进 main/⑦ 前改为调用 Lead 检查器，只留重建源码 SHA。 |
| 2 | 0500/0514/0515 补丁字节与重建后 `qbt_core.c`/`qbt_linux.c`/`btqca.c` 源码 SHA256 | 本仓 | 补丁字节 `:166-178`；源码钉 `test-bt-d8-adapter-host.py:50-60`（常量）与 `:430-470` 附近的重建校验 | Lead 输入检查器只钉补丁字节，不钉重建源码；本仓保留这三条 SHA。 |
| 3 | `run()` 错误→谓词→`boot_deadline`→命令期限，两期限均用 `>=` | Lead 时序 | `bt-d8-timing-harness.c:132-176` | 本仓不复制；boot 场景只间接执行。 |
| 4 | 精确期限注入、睡眠只夹命令期限、晚到事件先满足完成谓词 | Lead 时序 | `bt-d8-timing-harness.c:132-176` | 本仓不复制。 |
| 5 | 全局 TLV ack/final 与当前等待无关 | Lead 时序 | `bt-d8-timing-harness.c:114-115` | Lead 明确保留的两条 core 断言之一。 |
| 6 | stale 同 opcode 事件可完成新等待 | Lead 时序 | `bt-d8-timing-harness.c:219-223` | Lead 明确保留的另一条 core 断言。 |
| 7 | `qbt_deadline`/`qbt_drain`/调度器期限 | Lead 时序 | `bt-d8-timing-harness.c:182-203` | 本仓不复制。 |
| 8 | `dt_ms` 整数截断、0515 wrapper 汇总格式 | Lead 时序 | `bt-d8-timing-harness.c:250-267` | 本仓只经下载场景间接覆盖；不复制。 |
| 9 | TLV ack/final 语义经真实 adapter/下载链 | 本仓 | `bt-d8-adapter-harness.c:411-453`（success/fallback 的 `done` 行） | Lead 不复制 adapter 层；只保留 #5/#6。 |
| 10 | `sent/acks` 从 `qbt_boot()` 入口累计、fallback 不重置；`segs` 每 attempt、失败调用计入 | 本仓 | `bt-d8-adapter-harness.c:434-453`、`:456-469`；变异 `test-bt-d8-adapter-host.py:285-287` | Lead 的 `:264-267` 只验证 0515 汇总格式，不是累计语义；其文件应注明累计权威在本仓。 |
| 11 | 输入不符时 fail-closed 退出 2，不回退 latest | 本仓 | `test-bt-d8-adapter-host.py:78-80`、`:111-191` | Lead 输入检查器也拒跑，但入口不同；本仓保留运行前拒跑。 |
| 12 | adapter status/长度/version mismatch/overlong | 本仓 | `bt-d8-adapter-harness.c:324-352`、`:571-593` | Lead 不复制。 |
| 13 | adapter timeout/late/early/skip 路径 | 本仓 | `bt-d8-adapter-harness.c:354-408` | Lead 不复制；stale 跨等待归 #6。 |
| 14 | download success/patch/skip | 本仓 | `bt-d8-adapter-harness.c:411-432`、`:486-517` | Lead 不复制。 |
| 15 | NVM 主文件缺失/alt 名/已是 `.bin` | 本仓 | `bt-d8-adapter-harness.c:472-484`、`:595-630` | Lead 不复制。 |
| 16 | fallback 成功/失败、release 计数 | 本仓 | `bt-d8-adapter-harness.c:434-469`；变异 `test-bt-d8-adapter-host.py:306-307` | Lead 不复制。 |
| 17 | boot 成功/失败清理 | 本仓 | `bt-d8-adapter-harness.c:518-557` | Lead 不复制。 |
| 18 | boot patch/bdaddr/reset 失败与 fallback 边界 | 本仓 | `bt-d8-adapter-harness.c:558-570`、`:633-679` | Lead 不复制。 |
| 19 | 24 个变异孪生 | 本仓 | `test-bt-d8-adapter-host.py:254-308` | Lead 不复制；这是本仓独有价值。 |
| 20 | ⑦ artifact_check：payload 内核里的 `[bluetooth]` 行与哈希 | 本仓（候选） | 见下节；`logs/kernel.log:218/251/252`；payload strings 10907/11010 | Lead 不涉及；待 Lead 复核后写入账本。 |
| 21 | manifest→payload kernel 映射 | 本仓（候选） | `scripts/verify-boot-image.py:140-156`；`build-manifest.json` | 同上。 |
| 22 | ⑧ 设备结果 `result=-60` | Lead/设备 | `docs/research/EIGHT-STEPS.toml` 的 `[hardware.bluetooth.step.device]` | 两边都不因 90 个宿主用例改 ⑧；d8 仍是失败观测。 |

**请 Lead 删除/收窄的重复项**：按上表，Lead 时序夹具里除 #5/#6 两条 core 断言外，
以下 ack/final 计数断言与 adapter/下载层重叠，建议退役或改成只断言 `complete`/不 `complete`，
不再断言计数（计数权威在本仓 #9/#10）：

- `bt-d8-timing-harness.c:106-108` “TLV success report completes a matching wait”里的
  `tlv_acks == 1 && tlv_final_status == 0`。
- `:110-112` “TLV error report counts but cannot complete”里的 `tlv_acks == 1 &&
  tlv_final_status == 1`。
- `:126-127` “later TLV reports overwrite final status”里的 `tlv_acks == 2 &&
  tlv_final_status == 0`。
- `:229-232` “nonzero TLV reply increments ack then times out”里的 `tlv_acks == 1` 与
  `tlv_final_status == 1`。
- `:240-244` 第二条命令的 `tlv_sent == 2 && tlv_acks == 1` 只保留“boot budget/stats 不变”，
  计数部分退役。

`:264-267` 不是累计语义的重复项，它只验证 0515 汇总字符串格式；可保留，但应注明
“累计语义权威在 k60-bt”。输入身份侧不要求 Lead 删除：本仓会按 #1 收窄自己的入口。

**⑦ 补充证据候选（2026-11-16 21:30 只读核对，账本未改）**

Lead 的 21:26 裁决要求 artifact_check 与 manifest→payload 映射同时具备；两项现在都有只读证据：

1. **artifact_check**：`E:/k60-work/artifacts/bt-d8-tlv/logs/kernel.log:218` 是
   `patch 0500-k60-bt-qbt-new-files.patch`，`:251` 是 `0514-k60-bt-boot-observability.patch`，
   `:252` 是 `0515-k60-bt-tlv-counters.patch`。从 d8 `boot.img` 的 ramdisk FAT
   `EFI/UniXNU/Payloads/kernel.macho` 抽出的内核 sha256 为
   `72793ffd0a78e14b53321d3ef8b1c8579ae83a07f37900945849f6d2bf6e0286`，等于 manifest 的
   `components.payload_kernel`。`strings -a` 共 422201 行，`[bluetooth]` 出现在
   10907（`[bluetooth] %s`）与 11010（`[bluetooth] power=%u result=%d baud=%u firmware=%s
   tlv_sent=%llu tlv_acks=%llu tlv_final=%llu`）。提取脚本
   `E:/k60-work/scratch/bt-s4/extract-d8-payload.sh`，行号副本
   `E:/k60-work/scratch/bt-s4/d8-payload-bt-lines.txt`。
2. **manifest→payload 映射**：`python3 scripts/verify-boot-image.py --manifest
   /mnt/e/k60-work/artifacts/bt-d8-tlv/build-manifest.json` → `verify-boot-image: OK`。
   该脚本 `scripts/verify-boot-image.py:140-156` 从 boot.img 的 ramdisk payload FAT 读
   `EFI/UniXNU/Payloads/kernel.macho`，与 manifest 的 `payload_kernel` 比较；manifest 里
   `boot_img=0297012d…`、`payload=d1a7b51d…`、`payload_kernel=72793ffd…`、
   `kernel_built=6c96f7cc…`。这证明“这些字节在飞行镜像里”，不证明编译器到 payload 的
   可复现性，也不证明代码在控制器上执行。

两项都只是⑦的补充证据，不替代⑧；账本 `[hardware.bluetooth.step.verify].artifact_check`
等 Lead 复核后再决定是否写入。d8 之后要新增哪种设备观测，见
`docs/research/bt/D8-NEXT.md`。

**未覆盖边界（显式列出，避免“全绿=全懂”）**：控制器接收/接受与真实 RX 时间、UART/DMA/IBS 时间线、真实 d8 的 90 s 预算分支、`qca firmware vmalloc` 失败、`qca_disable_soc_logging` 失败、NVM 内容相等性、编译产物到 payload 的**可复现性**（字节映射已由 `verify-boot-image.py` 证明，但同一源码能否重编出同一 payload 未证明）、flash 门禁覆盖、d8 物理失败机制、蓝牙功能可用。上面任何一项都不能由本节的宿主用例推出。

**这套证据仍不能证明**：见上面的未覆盖边界；核心是控制器接收/接受、完整 NVM、UART/DMA/IBS 时间线、编译产物到 payload 的可复现性、flash 门禁覆盖、d8 物理失败机制或蓝牙功能可用。它只能证明：在冻结源码上，adapter 与完整 fallback 的**软件路径**按上述契约工作；artifact_check 只证明飞行镜像里存在对应字节。

**批准与交付（2026-11-16 19:31 批准，20:53 交付，21:26 Lead 裁决）**：test-only 提交 `916aaaa552b8470fa63b992dac2a525226b7288d`（3 文件 +1156）；`python3 scripts/tests/test-bt-d8-adapter-host.py` 得 `RAW_RC=0` / `TESTS OK: 90 case(s), 0 failure(s)`；输入绑定破坏时退出码 2；24 个变异孪生均真红。21:26 Lead 已把两套测试改为“一条断言一个 owner”的权威分区（见上表），并要求 ⑦ 的 artifact_check 与 manifest→payload 映射；两项候选证据已列上，账本与 ⑧ 未改。d8 之后要证明什么见 `docs/research/bt/D8-NEXT.md`。d8 结论不变：PATCH 软件路径返回成功、两次 NVM 尝试均失败、`result=-60`，蓝牙功能未证实。



---

## 8 八步账本沿革与 d8 当前范围

**当前有效状态（2026-11-16 16:58 d8 飞行完成）**：蓝牙 d8 是已完成的纯观测实验，
当前账本以 `docs/research/EIGHT-STEPS.toml` 为准：①–⑦覆盖 d8 离线观测改动，⑧记录了 Lead 的设备观测；
⑧完成表示观测结果已取得，不表示蓝牙功能可用。d8 的 PATCH 软件路径返回成功，两次 NVM 尝试均失败，最终 `result=-60`。
本树默认 `python3 scripts/eight-step-gate.py --flash` 已实际列出 7 项（含 bluetooth）、56 项通过、RC=0，
见 `E:/k60-work/scratch/bt-s4/d8-flash-gate-20261116.log`。原 d8 构建日志只有 6 项 build 检查，
不追改 manifest，也不把后补离线核验冒充原构建覆盖。
以下是 11-15 的历史沿革，不是本轮保留 parked 或跳过 flash 检查的依据。

**缺口**：`docs/research/EIGHT-STEPS.toml` 没有 `[hardware.bluetooth]` 段（`grep -n '^\[hardware'` 只列出
touch / gpu / storage / display / bootchain / buttons / wifi / audio / battery），于是
`K60_EIGHT_STEP_ITEMS=bluetooth` 会被 `scripts/eight-step-gate.py` 直接拒绝
（"K60_EIGHT_STEP_ITEMS 里有不存在的硬件项: bluetooth"）。而 `docs/research/bt/FIRMWARE.md:34`、
`HANDOFF.md:90-118` 曾声称 `[hardware.bluetooth.step.*]` 已存在——那是文档缺陷：条目从未写入。

**补丁**：`/mnt/e/k60-work/scratch/bt-s4/lead/bt-ledger.patch`（12,132 B，sha256
`7a31315374545bc458861d67b69dc00b4772b9a55c9bfbd1ea89eaa01a35f48f`），4 个文件
（+50/−3）。**Lead 已于 2026-11-15 合为 `8a497a4`**（`[hardware.bluetooth]` 现在在
`docs/research/EIGHT-STEPS.toml:342`），本分支不再携带该补丁：

| 文件 | 改动 |
|---|---|
| `docs/research/EIGHT-STEPS.toml` | 新增 `[hardware.bluetooth]` 段 48 行（`status = "parked"`，插在 `[hardware.wifi]` 之前） |
| `scripts/render-eight-step-table.py` | 从 `UNTRACKED` 删掉 `('蓝牙', 'planned')`，否则表格出现两行蓝牙（P-148 同一个坑） |
| `README.md` / `README_EN.md` | 用 `render-eight-step-table.py --apply` 重新生成：蓝牙从"—/planned"变成正式行 |

**验证（在 /mnt/e/k60-work/scratch/bt-s4/lead/ledger-repo 里实跑）**：`eight-step-gate.py --build` →
`5 个（touch, gpu, storage, display, bootchain）通过 30 项` rc=0；`--flash` → `通过 40 项` rc=0
（parked 项不参与整机口径，所以整机口径没有被放宽）；`K60_EIGHT_STEP_ITEMS=bluetooth ... --build` →
`声明范围: bluetooth[parked] / 通过 6 项检查` rc=0；`render-eight-step-table.py --check` → 一致。

**已撤回的旧解释**：11-15 曾把“等上机窗口”写成 parked，并把⑦ `done=false`
解释成“上机未做”。这是把⑦离线核验与⑧上机混在一起，导致默认 flash 只查其他硬件。
`K60_EIGHT_STEP_ITEMS` 仅影响 build，不能让 parked 项进入默认 flash。
15:28 的离线闭环不豁免 done=false、不改 gate：三类实际核验齐全后才将⑦置 true、
蓝牙设 active，当时⑧仍 false；16:58 的 d8 观测结果另见 §7.20。默认 `--flash` 必须实际列出 bluetooth。

**⑤ 方案里写进去的阶梯判据**（这是 Lead 要的"把 step-5 判据放进片段"）：五档 `k60bt=1 k60bt_step=N`
（1→4→5→7→9，每份 596 B）与"最后一行打点即死因"的判死表，以及 S4 三级
（负向 `addon: no GpuAddon property` / 正向 `addon: linked blob bytes=1027584 records=106` →
`serving 201560 0` → `power=1 result=0`）全部逐字写进 `[hardware.bluetooth.step.plan]`
与 `step.device.prediction`。

> **2026-11-15 补记**：写进账本的那条链里 `QCA controller version 0x…` 是死判据（§7.1），
> 已在本分支改成 `power=1 result=0`。Lead 于 15:36 确认 `docs/research/EIGHT-STEPS.toml` 的那两处
> 已在 `main` 的 `0eee1a8` + `2f9f991` 改掉，**不再导出补丁**；`docs/engineering/BOOT-ARGS.md:246`
> 的死判据与 `k60bt_stage` 语义随 `0511` 在本分支同一提交里直接改写（见该文件 §`k60bt_stage`）。

> 合进 main 的那一版写的是旧通道的正向判据 `addon: loaded bytes records 1027584 106`。
> P-197 之后正向镜像换成内嵌 blob，判据行改成 `addon: linked blob bytes=1027584 records=106`。
> 当时 `docs/research/EIGHT-STEPS.toml` 与 `docs/engineering/PITFALLS.md`（P-197 的 Check 行）都不在本线写权限内（本轮 Lead 已授权更新本线账本），
> 所以这三处判据改动同样导出成补丁交给 Lead：
> `/mnt/e/k60-work/scratch/bt-s4/lead/bt-ledger-blob.patch`（10,117 B，sha256
> `539473c2e2ab2578cbdcb1212047e2ed88a08f3616bd3e569841d79e0258cdc3`），在 `ccd4dfc` 上
> `git apply --check` 通过。本分支只保留 `docs/research/bt/*` 里的同名说明。

**旧的草案（已作废，留档对照）**——注意它 `status = "research"` 不是合法状态值，且 evidence 只有
章节号、没有 file:line 锚点，会被 `has_reference()` 判成"缺可核查引用"：

```toml
[hardware.bluetooth]
title = "Bluetooth (QCA6490 on UART SE20 0x894000)"
status = "research"

[hardware.bluetooth.step.same_model]
done = true
evidence = "docs/research/bt/RESEARCH.md §2 (sm8475 BT node, bt_qca6490 compatible)"

[hardware.bluetooth.step.official]
done = true
evidence = "vendor kernel qca btqca.c + sm8475 DTSI in docs/research/bt/EVIDENCE.md"

[hardware.bluetooth.step.decompile]
done = true
evidence = "docs/research/bt/06-DEEP-DIVE.md V1-V11 (window group, RCG, SMMU stream)"

[hardware.bluetooth.step.wide]
done = true
catalog_checked = true
catalog_result = "UniXNU/components.toml has no QcaBluetooth; sheng ships it as a submodule (feeds.toml gap)"
evidence = "docs/research/bt/RESEARCH.md §7"

[hardware.bluetooth.step.plan]
done = true
evidence = "docs/research/bt/S1-PROBE-SPEC.md / S2-SPEC.md / S3-SPEC.md / S4-SPEC.md"

[hardware.bluetooth.step.deep]
done = true
evidence = "docs/research/bt/06-DEEP-DIVE.md F1-F12"

[hardware.bluetooth.step.verify]
done = false
evidence = "S1c/S2/S3/S4 not yet run on device; images bt-s1c-*/bt-s2-20261114b built but unjudged"
```

## 9 风险

| 风险 | 影响 | 处置 |
|---|---|---|
| 旧通道：构建时带了 addon 但 ADT 没单元（老 `devicetree.py`） | 已无关——P-197 之后固件不再走 ADT 单元 | 保留 `--gpu-addon` 只为对照；正向镜像不传它 |
| 内核体积 +1,032,192 B（容器 + 对齐） | 内核 106,541,056 B，仍在 boot window 内 | 实测 `verify-boot-image` OK；要收窄时按 §10 第 3 条砍到 3–4 个文件 |
| 内嵌 blob 头部与长度常量不一致 | 内核打印 `blob bad magic`/`blob bad header` 并静默回落到旧路径 | 构建期 `test-k60-bt-blob.py` 先拦（9 条夹具，含 P-196 那类"长度没算 padding"的用例） |
| 命名/压缩不匹配 | 解析器 fail closed | 打包器与解析器共用同一白名单正则，坏名字在构建期就报错 |

## 10 下一步

1. ~~Lead 合并 §5.2/§5.3/§5.4~~——已合（`277e09e` + `dbc2cd5`）；内嵌 blob 的三处构建侧改动由本线提交（`ccd4dfc`）。
2. 板子回来后按 §7 跑 S4-（`bt-s4c-20261115a`）与 S4a→S4c（`bt-s4b-20261115b`），把 `capture.json` 与关键行写进本文 §7 与 `HANDOFF.md` 的账本。
3. 拿到 `rom_ver`/`board-id` 后把 §5.1 的 106 文件清单收窄到实际需要的 3–4 个（可省 900 KB 内核体积）。
4. S4 出结果**之后**才排 S1c 阶梯（a1/a4/a5/a7/a9）——阶梯验的是同一条 addon 取固件路径，
   通道换了，它的判据也跟着变，先跑会白烧一次窗口。
