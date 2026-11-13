# patches/bt — Bluetooth line patches

`scripts/check-patch-series.py:24` and `scripts/check-build-applied.py:27` read only
`patches/xnu/series`, and the build mirrors `patches/xnu` into the build input — so a patch that
lives **only** here never reaches the kernel image. This directory is the line's own archive; the
copy that builds is `patches/xnu/0507-k60-bt-readonly-probe.patch`, wired at
`patches/xnu/series:205` (after `0502`, before `0503`), byte-identical to the file below
(same sha256).

| Patch | Purpose | Applies to |
|---|---|---|
| `0002-k60-bt-s2-smmu-rcg-reset.patch` | S2 前置修复：F1（`k60_smmu_*` planner + `kmem_alloc_contig`/`pmap_find_phys`，stream `0x483`）、F11（`k60_gcc_set_se_rate()` 打开 SE20 RCG 根时钟）、F3（`k60_stop_engine()` 改用 0xc40/0xd40 的 `TX/RX_RESET_DONE`）、F12（rate 写完后等 SE20 CBCR halt）。18,393 B / 391 行，sha256 `c4bf1ded55fe9bd03b7c10943ed41fff47464037c06c893b6dfd0984f02fd4f2`；对应 `patches/xnu/0508-k60-bt-s2-smmu-rcg-reset.patch`（`series:206`）。规格：`docs/research/bt/S2-SPEC.md`。 | the `bsd/dev/qbt_k60.c` created by `0500`, **after** `0001` |
| `0001-k60-bt-readonly-probe.patch` | Adds `k60_bt_probe(unsigned step)` and a `k60bt_stage=1` early return to `bsd/dev/qbt_k60.c`. It sleeps `k60bt_delay` (default 20 s, cap 120 s) so the CDC console is up, prints a mark before every access (36 marks), and walks nine `k60bt_step` rungs: s1 map GCC/UART/wrapper (zero MMIO); s2 GPLL0 vote + lock poll; s3 QUPV3_2 vote 0x62010 + read-back; s4 five halt reads; **s5 read-only SE20 RCG (CMD 0x2e618, CFG, DFSR, decode ROOT_OFF/ROOT_EN/UPDATE)**; **s6 set `CMD_ROOT_EN` and poll `ROOT_OFF` clear**; **s7 write CFG then latch `ROOT_EN`/`UPDATE`**; s8 GENI identity 0x040/0x064/0x068/0x2ac + wrapper 0x004; s9 0xc40/0xd40/0xe40/0x040 again. Returns before any pin muxing, BT_EN pulse, DMA setup or interrupt installation. | the `bsd/dev/qbt_k60.c` created by `patches/xnu/0500-k60-bt-qbt-new-files.patch` |

Verified with `git apply --check` against the full `bsd/` tree extracted from 0500 (`qbt_k60.c` 1,249 lines, sha256
`8451c8706ecf75a79fba49ba7e3bda769ee73fcac5f357a46c9d484df3878748`), then `clang -fsyntax-only` with the out3
`.CFLAGS`: 0 error. Patch sha256 `05dd342b83d3d035e05495280d9bee9d40624f9732240b7323146964e7b8b2e1` (13,001 B, 280 lines, 36 marks, 8 step gates).
The deviations these rungs decide are F1–F3 and F11/F12 in `docs/research/bt/06-DEEP-DIVE.md`; F11 (the SE20 RCG root is never enabled by 0500) is the leading explanation for the S1a zero-byte death.
Rationale, boot commands, expected console lines and verdict table:
`docs/research/bt/S1-PROBE-SPEC.md`.

## Wiring status

Wired with **option B**: a separate patch `patches/xnu/0507-k60-bt-readonly-probe.patch` appended
to `patches/xnu/series` at line 205 (numbered 0507, not 0503, because the integrated series
already uses 0503–0506 for audio and the 120 Hz clock). After editing the series, both
`K60_DEVICE_INPUT=<mirror> python3 scripts/sync-device-input.py` and
`python3 scripts/check-rules.py` must run, otherwise iron-4/hard-33 (`series 三处一致`) and
P-165/P-166 (`check-build-applied.py`) go red.

Option A (fold the hunks into `0500`) remains valid and would keep `series` untouched, since 0500
creates the file it patches. It was not used because the probe is expected to be rewritten again
after the ladder returns data.
