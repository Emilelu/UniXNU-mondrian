# patches/bt — Bluetooth line patches (staged, not build-wired)

These patches are **not applied by the build**. `scripts/check-patch-series.py:24` and
`scripts/check-build-applied.py:27` read only `patches/xnu/series`, and the build mirrors
`patches/xnu` into the build input. A patch living here is a reviewed artefact for the Lead,
not a change that reaches the kernel image.

| Patch | Purpose | Applies to |
|---|---|---|
| `0001-k60-bt-readonly-probe.patch` | Adds `k60_bt_probe()` and a `k60bt_stage=1` early return to `bsd/dev/qbt_k60.c`: maps GCC/UART/wrapper, enables the serial clock (GPLL0 + five votes + halt poll), then performs four read-only GENI reads and returns before any pin muxing, BT_EN pulse, DMA setup or interrupt installation. | the `bsd/dev/qbt_k60.c` created by `patches/xnu/0500-k60-bt-qbt-new-files.patch` |

Verified with `git apply --check` against the file extracted from 0500 (1,249 lines).
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
