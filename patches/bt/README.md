# patches/bt — Bluetooth line patches

`scripts/check-patch-series.py:24` and `scripts/check-build-applied.py:27` read only
`patches/xnu/series`, and the build mirrors `patches/xnu` into the build input — so a patch that
lives **only** here never reaches the kernel image. This directory is the line's own archive; every
file below is byte-identical to its `patches/xnu/` twin (same sha256) and wired in `patches/xnu/series`:

| here | builds as | series line |
|---|---|---|
| `0001-k60-bt-readonly-probe.patch` | `patches/xnu/0507-k60-bt-readonly-probe.patch` | 205 |
| `0002-k60-bt-s2-smmu-rcg-reset.patch` | `patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch` | 206 |
| `0003-k60-bt-s3-identity-publish.patch` | `patches/xnu/0509-k60-bt-s3-identity-publish.patch` | 207 |
| `0004-k60-bt-firmware-addon.patch` | `patches/xnu/0510-k60-bt-firmware-addon.patch` | 208 |

| Patch | Purpose | Applies to |
|---|---|---|
| `0004-k60-bt-firmware-addon.patch` | S4 固件通道：在 `bsd/dev/qbt_k60.c` 里加 NGPUADD2 读取器，从 `/chosen/memory-map/GpuAddon` 用 `phystokv` 取启动镜像里 DarwinBoot 复制好的固件容器（`k60_addon_find()` 纯解析器 + `k60_bt_addon_load()` 快照 + `k60_bt_addon_read()`），并让 `k60_bt_firmware_read()` **先**走 addon 再走 vnode 根；容器不压缩（内核无 zlib，压缩记录直接 `-ENOENT`）。12,877 B / 291 行，sha256 `4d6e3c1a89b60a55cc146294ec4e9abcfac4521aed0d3787da20df5e22218b04`（237 增 / 1 删）；对应 `patches/xnu/0510-k60-bt-firmware-addon.patch`（`series:208`）。规格与构建侧交付片段：`docs/research/bt/S4-SPEC.md`。 | the post-series tree (`bsd/dev/qbt_k60.c`), **after** `0001`/`0002`/`0003` |
| `0003-k60-bt-s3-identity-publish.patch` | S3 身份与发布：把 0500 的弱符号空壳 `k60_bt_local_address()` 换成**强定义**（SecureDT 读 `/chosen/unique-chip-id`，FNV-1a 域 `unixnu-bluetooth`，`address[0] = (address[0] & 0xfe) \| 2`，无种子则 fail closed），新增 `iokit/Kernel/MiniBluetooth.cpp`（164 行）在 `native_pong_ui_services_start()` 里建/补 `/arm-io/bluetooth` 节点、写 `local-mac-address` 与 `/chosen/mac-address-bluetooth0`、发布名为 `bluetooth` 的 `K60BluetoothRadio` IOService，另加 `MiniDrivers.h`/`MiniIOSurface.cpp`/`iokit/conf/files` 三处接线；整条路径由 `k60bt=1` 门控。10,265 B / 304 行，sha256 `429630d61fcd06554cc8094ca3381ec49d0485f8c8b025d60f7a5fe8c1208edf`（198 增 / 11 删）；对应 `patches/xnu/0509-k60-bt-s3-identity-publish.patch`（`series:207`）。规格：`docs/research/bt/S3-SPEC.md`。 | the post-series tree (`bsd/dev/qbt_k60.c`, `iokit/Kernel/Mini{Drivers.h,IOSurface.cpp}`, `iokit/conf/files`), **after** `0001`/`0002` |
| `0002-k60-bt-s2-smmu-rcg-reset.patch` | S2 前置修复：F1（`k60_smmu_*` planner + `kmem_alloc_contig`/`pmap_find_phys`，stream `0x483`）、F11（`k60_gcc_set_se_rate()` 打开 SE20 RCG 根时钟）、F3（`k60_stop_engine()` 改用 0xc40/0xd40 的 `TX/RX_RESET_DONE`）、F12（rate 写完后等 SE20 CBCR halt）。18,393 B / 391 行，sha256 `c4bf1ded55fe9bd03b7c10943ed41fff47464037c06c893b6dfd0984f02fd4f2`；对应 `patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch`（`series:206`）。规格：`docs/research/bt/S2-SPEC.md`。 | the `bsd/dev/qbt_k60.c` created by `0500`, **after** `0001` |
| `0001-k60-bt-readonly-probe.patch` | Adds `k60_bt_probe(unsigned step)` and a `k60bt_stage=1` early return to `bsd/dev/qbt_k60.c`. It sleeps `k60bt_delay` (default 20 s, cap 120 s) so the CDC console is up, prints a mark before every access (36 marks), and walks nine `k60bt_step` rungs: s1 map GCC/UART/wrapper (zero MMIO); s2 GPLL0 vote + lock poll; s3 QUPV3_2 vote 0x62010 + read-back; s4 five halt reads; **s5 read-only SE20 RCG (CMD 0x2e618, CFG, DFSR, decode ROOT_OFF/ROOT_EN/UPDATE)**; **s6 set `CMD_ROOT_EN` and poll `ROOT_OFF` clear**; **s7 write CFG then latch `ROOT_EN`/`UPDATE`**; s8 GENI identity 0x040/0x064/0x068/0x2ac + wrapper 0x004; s9 0xc40/0xd40/0xe40/0x040 again. Returns before any pin muxing, BT_EN pulse, DMA setup or interrupt installation. | the `bsd/dev/qbt_k60.c` created by `patches/xnu/0500-k60-bt-qbt-new-files.patch` |

Verified with `git apply --check` against the full `bsd/` tree extracted from 0500 (`qbt_k60.c` 1,249 lines, sha256
`8451c8706ecf75a79fba49ba7e3bda769ee73fcac5f357a46c9d484df3878748`), then `clang -fsyntax-only` with the out3
`.CFLAGS`: 0 error. Patch sha256 `05dd342b83d3d035e05495280d9bee9d40624f9732240b7323146964e7b8b2e1` (13,001 B, 280 lines, 36 marks, 8 step gates).
The deviations these rungs decide are F1–F3 and F11/F12 in `docs/research/bt/06-DEEP-DIVE.md`; F11 (the SE20 RCG root is never enabled by 0500) is the leading explanation for the S1a zero-byte death.
Rationale, boot commands, expected console lines and verdict table:
`docs/research/bt/S1-PROBE-SPEC.md`.

`0004` was verified on the host: `gcc -fsyntax-only` 0 error, `qbt_k60 host checks passed` (the file's own
`K60_BT_HOST_TEST` main gained five parser assertions), and an end-to-end run that packed the real 106-file
firmware set into an addon (1,027,584 B, sha256 `febdc20d44ff23559b6012dc78f12e4287025cdc34463f868e64e9373c592037`)
and re-read every record through `k60_addon_find()`: `addon check: 106 records verified, 0 bad`
(`E:/k60-work/scratch/bt-s4/addon_check.c`).

`0002` and `0003` were verified the same way but against the **post-series** tree
(`/opt/k60/trees/k60build/…/.cache/xnu-work`), because they must apply on top of every other patch:
`git apply --check` OK, and `clang -fsyntax-only` with the lead-out `bsd`/`iokit` `.CFLAGS` reports 0 error
(`0003`: 2 pre-existing warnings in `qbt_k60.c`, 17 header-only warnings in `MiniBluetooth.cpp`).
Harness: `E:/k60-work/scratch/bt-s3/verify3.sh`.

## Wiring status

Wired with **option B**: separate patches appended to `patches/xnu/series` — `0507` at line 205,
`0508` at 206, `0509` at 207, `0510` at 208 (numbered 0507–0510, not 0503+, because the integrated series already
uses 0503–0506 for audio and the 120 Hz clock). After editing the series, both
`K60_DEVICE_INPUT=<mirror> python3 scripts/sync-device-input.py` and
`python3 scripts/check-rules.py` must run, otherwise iron-4/hard-33 (`series 三处一致`) and
P-165/P-166 (`check-build-applied.py`) go red.

Option A (fold the hunks into `0500`) remains valid and would keep `series` untouched, since 0500
creates the file it patches. It was not used because the probe is expected to be rewritten again
after the ladder returns data.
