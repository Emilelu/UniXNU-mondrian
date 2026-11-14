# S4 — 蓝牙固件随启动镜像下发（boot-image addon）

状态（2026-11-14 10:20）：**内核侧已交付并离线验证**（`patches/bt/0004` = `patches/xnu/0510`，`patches/xnu/series:208`）；
**构建侧未合并**（`scripts/` 属 Lead 写权限，片段见 §5）；**上机未验证**——板子不在（`fastboot devices` 为空，
`adb devices` 只有表头），S4 的 ⑦ 仍然是 `done = false`。

## 0 一句话

S4 不需要把 106 个 QCA 文件写进 `/private/var/ngpu/firmware/qca`：把固件按 `make-gpu-addon.py` 的
NGPUADD2 容器塞进启动镜像的 `<kernel>.gpuaddon` 槽，DarwinBoot 会把它复制进 boot window 并把运行时物理地址
写进 `/chosen/memory-map/GpuAddon`，内核在 `bsd/dev/qbt_k60.c` 里用 `phystokv` 直接读。整条链路**不需要**
改固件、不需要 Data seed、不需要 zlib、不需要新 DXE。

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

## 2 通道机制（逐行证据）

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

## 4 内核侧交付：`patches/bt/0004` = `patches/xnu/0510`

| 项 | 值 |
|---|---|
| 文件 | `patches/bt/0004-k60-bt-firmware-addon.patch` = `patches/xnu/0510-k60-bt-firmware-addon.patch`（字节相同） |
| 大小 / 行数 | 12,877 B / 291 行，**237 增 / 1 删**，只动 `bsd/dev/qbt_k60.c` |
| sha256 | `4d6e3c1a89b60a55cc146294ec4e9abcfac4521aed0d3787da20df5e22218b04` |
| 接线 | `patches/xnu/series:208`（紧跟 `0509`，早于 audio 组） |
| 依赖 | 必须在 `0500`/`0507`/`0508`/`0509` 之后（基线就是打完全系列后的 `qbt_k60.c`） |

改动五处：

1. `#if defined(__arm64__)` 里 `typedef uint64_t pmap_paddr_t __kernel_ptr_semantics;` + `extern vm_map_address_t phystokv(pmap_paddr_t pa);`
   —— `pmap_paddr_t` 的 typedef 在 `osfmk/arm/pmap_public.h:40`，被 `MACH_KERNEL_PRIVATE` 挡住，BSD 编译单元看不到，
   所以必须像 `bsd/kern/kern_trustcache.c:772-773` 那样连 typedef 一起声明（**第一版只写了 extern，真机构建在
   `qbt_k60.c:60: error: unknown type name 'pmap_paddr_t'` 处失败，host 测试发现不了这一类**）。
2. 容器常量 `K60_BT_ADDON_MAGIC/HEADER/MAX_BYTES/MAX_NAME`。
3. 纯解析器 `k60_addon_find()` + 内核装载器 `k60_bt_addon_load()` + 单条读取 `k60_bt_addon_read()`。
4. `k60_bt_firmware_read()` **先**试 addon，再走 vnode 根（`/private/var/ngpu/firmware/qca` → `/vendor/firmware` …）。
5. `qbt_k60_start()` 里在起线程前 `(void)k60_bt_addon_load()`：DarwinBoot 的 window 是 `EfiLoaderCode`
   内存，VM 之后可能回收，所以在 `bsd_init` 就快照一份（1 MB 以内）。

日志（全部走 `k60_log`，即 `[bluetooth] ...`，level ≤ 3 才打印）：

| 行 | 含义 |
|---|---|
| `addon: loaded bytes records 1027584 106` | 成功：容器已快照，106 条记录 |
| `addon: serving 201560 0` | 命中一条（例：`hpbtfw20.tlv` 201,560 B） |
| `addon: no GpuAddon property` | ADT 没这个单元（构建时没带 `--gpu-addon`），属正常降级 |
| `addon: unusable range …` / `bad header …` | DarwinBoot 写了单元但内容不合格 |
| `addon: bad magic` / `no kernel mapping` / `no memory for the copy` | 容器或内存异常 |

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

## 7 上机阶梯（板子回来后）

前提：构建时带 `--gpu-addon`（§5.3），启动参数只需 `k60bt=1`（S2/S3 的写法不变）。

| 级 | 参数 | 期望（关键行） |
|---|---|---|
| S4a | `k60bt=1` | `K60 BT: addon: loaded bytes records 1027584 106` |
| S4b | `k60bt=1` | `K60 BT: addon: serving 201560 0`（rampatch），随后 `serving 6319`/`6602`（NVM） |
| S4c | `k60bt=1` | qbt 打印 `QCA controller version 0x…`（btqca.c:764 的等价行），拿到 rom_ver/board-id |

判定：只认 `capture.json` 的 `verdict`/`panicMarker`；控制台 0 字节时用 `0331` 的 K60PREV 重放读上一轮尾巴。
失败即回退到不带 `--gpu-addon` 的构建（内核代码对缺失单元是静默降级，见 §4 日志表）。

## 8 八步账本缺口（必须由 Lead 补）

`docs/research/EIGHT-STEPS.toml` **没有 `[hardware.bluetooth]`** 段：`grep -n '^\[hardware' docs/research/EIGHT-STEPS.toml`
只列出 touch / gpu / storage / display / bootchain / buttons / wifi / audio / battery；`K60_EIGHT_STEP_ITEMS=bluetooth`
会被 `scripts/eight-step-gate.py` 直接拒绝（"K60_EIGHT_STEP_ITEMS 里有不存在的硬件项: bluetooth"）。
但 `docs/research/bt/FIRMWARE.md:34`、`docs/research/bt/HANDOFF.md:90-118` 却声称
`[hardware.bluetooth.step.*]` 已存在——这是本轮发现的**文档缺陷**：要么条目从未写入，要么被 reset 掉了。

建议的 Ledger 片段（放 `[hardware.wifi]` 之前，①–⑥ 引 `RESEARCH.md`/`06-DEEP-DIVE.md`/`S1-PROBE-SPEC.md`/`S2-SPEC.md`/`S3-SPEC.md`/`S4-SPEC.md` 的对应小节，
⑦ 引本文 §6，⑧ 引 S1c 触摸成功那次上机）：

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
| 构建时带了 addon 但 ADT 没单元（老 `devicetree.py`） | DarwinBoot `EFI_COMPROMISED_DATA`，**开不了机** | `devicetree.py:339` 已按 `addon=bool(addon)` 自动生成；构建前用 `make-bt-firmware-addon.py --list` 确认文件存在即可 |
| boot window 余量 | `WINDOW_SIZE = SIZE_256MB`，内核 + ADT + ramdisk + trust + addon 1 MB | 余量充足；`Used > WindowSize - BLOCK_SIZE` 时 DarwinBoot 自己报 `EFI_BAD_BUFFER_SIZE` |
| 快照占 1 MB 内核内存 | 可忽略 | `IOMallocData` 一次性，不释放 |
| 命名/压缩不匹配 | 解析器 fail closed | 打包器与解析器共用同一白名单正则，坏名字在构建期就报错 |

## 10 下一步

1. Lead 合并 §5.2/§5.3/§5.4（`scripts/` + `.gitignore`）。
2. 板子回来后按 §7 跑 S4a→S4c，把 `capture.json` 与关键行写进本文 §7 与 `HANDOFF.md` 的账本。
3. 拿到 `rom_ver`/`board-id` 后把 §5.1 的 106 文件清单收窄到实际需要的 3–4 个（可省 900 KB）。
