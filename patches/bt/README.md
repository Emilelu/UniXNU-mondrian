# patches/bt — Bluetooth line patches (staged, not build-wired)

These patches are **not applied by the build**. `scripts/check-patch-series.py:24` and
`scripts/check-build-applied.py:27` read only `patches/xnu/series`, and the build mirrors
`patches/xnu` into the build input. A patch living here is a reviewed artefact for the Lead,
not a change that reaches the kernel image.

| Patch | Purpose | Applies to |
|---|---|---|
| `0001-k60-bt-readonly-probe.patch` | Adds `k60_bt_probe()` and a `k60bt_stage=1` early return to `bsd/dev/qbt_k60.c`: maps GCC/UART/wrapper, enables the serial clock (GPLL0 + five votes + halt poll), then performs nine read-only GENI loads (identity: 0x40/0x64/0x68/wrapper 0x4; deviation-deciding: `G_MANUAL_RFR` 0x2ac, DMA status 0xc40/0xd40, unnamed 0xe40, then 0x40 again) and returns before any pin muxing, BT_EN pulse, DMA setup or interrupt installation. | the `bsd/dev/qbt_k60.c` created by `patches/xnu/0500-k60-bt-qbt-new-files.patch` |

Verified with `git apply --check` against the full `bsd/` tree extracted from 0500 (`qbt_k60.c` 1,249 lines, sha256
`8451c8706ecf75a79fba49ba7e3bda769ee73fcac5f357a46c9d484df3878748`), then `clang -fsyntax-only` with the out3
`.CFLAGS`: 0 error. Patch sha256 `95e4b098e552619db135b455af5dbec96eae4450a2a8cdae1c6c61ce658ed8a3` (4,174 B, 80 lines).
The three deviations the extra reads decide are F1–F3 in `docs/research/bt/06-DEEP-DIVE.md`.
Rationale, boot commands, expected console lines and verdict table:
`docs/research/bt/S1-PROBE-SPEC.md`.

## Wiring options for the Lead

- **A (preferred, no series change):** fold the two hunks into
  `patches/xnu/0500-k60-bt-qbt-new-files.patch`. 0500 creates a new file, so editing its body
  keeps `patches/xnu/series` untouched and `check-build-applied.py` keeps matching.
- **B (separate patch):** add `0503-k60-bt-readonly-probe.patch` under `patches/xnu/`, append
  `0503-k60-bt-readonly-probe.patch` to `patches/xnu/series`, then run
  `python3 scripts/sync-device-input.py` and `python3 scripts/check-rules.py`.

Neither option is inside this line's write scope, so both are handed to the Lead.
