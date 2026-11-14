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
| 大小 / 行数 | 15,672 B，**289 增 / 1 删**，动两个文件：`bsd/dev/qbt_k60.c` 与 `osfmk/conf/files.arm64` |
| sha256 | `316148931ab11fa9fbd79fbe7b878960e702b39d5e89babd0daa806655fccc96` |
| 接线 | `patches/xnu/series:208`（紧跟 `0509`，早于 audio 组） |
| 依赖 | 必须在 `0500`/`0507`/`0508`/`0509` 之后（基线就是打完全系列后的 `qbt_k60.c`）；`osfmk/conf/files.arm64` 的新行插在 `WKdmCompress_4k.s` 之后，所以 `0610` 的 conf hunk 仍能干净应用（实测 `APPLY_610_CONF_OK`） |

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

前提：启动参数只需 `k60bt=1`（583 B）。正向镜像用 §6.5 的 **`bt-s4b-20261115b`**（内嵌 blob）；
负向对照用 §6.5 的 **`bt-s4c-20261115a`**（同一 HEAD、同一冻结清单，只少 `--bt-blob`，所以
`k60_bt_blob_len == 0`，走回落路径）。`bt-s4-20261114b` 是旧基线（series 227、旧 `build-strict.sh`），
按 P-201 不再作为对照。

| 级 | 镜像 | 参数 | 期望（关键行） |
|---|---|---|---|
| S4- | `bt-s4c-20261115a` | `k60bt=1` | 负向对照：`[bluetooth] addon: no GpuAddon property`，随后回落到 vnode 根（同样找不到），控制台完整、无 panic |
| S4a | **`bt-s4b-20261115b`** | `k60bt=1` | `[bluetooth] addon: linked blob bytes=1027584 records=106` |
| S4b | **`bt-s4b-20261115b`** | `k60bt=1` | `[bluetooth] addon: serving 201560 0`（rampatch），随后 `serving 6319`/`6602`（NVM） |
| S4c | **`bt-s4b-20261115b`** | `k60bt=1` | qbt 打印 `QCA controller version 0x…`（btqca.c:764），拿到 rom_ver/board-id |

（`bt-s4a-20261114c`/`f`/`bt-s4a-20261115a` 全部作废：它们把固件放在 payload 的
`kernel.macho.gpuaddon` 槽里，而固件从不填那个槽（P-197）。它们的实测结果**不是**失败，而是
`addon: unusable range 0 0`——那正是 P-197 的真机证据。）

S4a 与 S4b 用同一个镜像：`linked blob` 在 `qbt_k60_start()` 里就打（`k60_bt_addon_load_blob()`），
`serving` 要等 qbt 真正取固件才打，是同一轮启动里的前后两段，不是两次构建。

判定：只认 `capture.json` 的 `verdict`/`panicMarker`；控制台 0 字节时用 `0331` 的 K60PREV 重放读上一轮尾巴。
失败即回退到不带 `--bt-blob` 的构建（内核代码对缺失 blob 是静默降级，见 §4 日志表）。

## 8 八步账本片段（已产出补丁，Lead 落地）

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

**状态取值为什么是 `parked` 而不是 `active`**：`active` 会让整机口径立刻要求蓝牙的 ①–⑥ 全部 done
（那是别的线的门禁负担，也等于把本线的进度绑成全仓库的阻塞项）；`parked` + `parked_why` 才是
"有镜像、等上机窗口"的准确表述，而且按 P-192 仍可用 `K60_EIGHT_STEP_ITEMS=bluetooth` 单独声明后
按 active 的证据规则被检查。⑦ 的 `done = false` + `local_verified = true` 与 battery 段同一写法：
离线三类核验齐全（表格显示 ✅），但上机未做，所以不写 done。

**⑤ 方案里写进去的阶梯判据**（这是 Lead 要的"把 step-5 判据放进片段"）：五档 `k60bt=1 k60bt_step=N`
（1→4→5→7→9，每份 596 B）与"最后一行打点即死因"的判死表，以及 S4 三级
（负向 `addon: no GpuAddon property` / 正向 `addon: linked blob bytes=1027584 records=106` →
`serving 201560 0` → `QCA controller version 0x…`）全部逐字写进 `[hardware.bluetooth.step.plan]`
与 `step.device.prediction`。

> 合进 main 的那一版写的是旧通道的正向判据 `addon: loaded bytes records 1027584 106`。
> P-197 之后正向镜像换成内嵌 blob，判据行改成 `addon: linked blob bytes=1027584 records=106`。
> `docs/research/EIGHT-STEPS.toml` 与 `docs/engineering/PITFALLS.md`（P-197 的 Check 行）都**不在本线写权限内**，
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
