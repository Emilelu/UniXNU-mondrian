# 27 line branch inventory (with flight status)

Generated: 2026-11-24 12:51; source: git for-each-ref refs/remotes/origin.

## Totals
- remote branches: 61
- ahead of main: 56
- non-archive: 34

## Non-archive branches ahead of main

| Ahead | Branch | Last commit | Status |
|---|---|---|---|
| 414 | feat/audio-adsp-merge | 2026-11-21 | build-only / unverified |
| 358 | feat/cellular-ios27 | 2026-11-20 | build-only / unverified |
| 358 | diag/menu-hold-20261121 | 2026-11-24 | build-only / unverified |
| 321 | feat/cellular-27 | 2026-11-22 | build-only / unverified |
| 319 | feat/cellular-k55 | 2026-11-21 | build-only / unverified |
| 276 | feat/cellular | 2026-11-20 | build-only / unverified |
| 192 | fix/bt-gic-sleep-fragment | 2026-11-20 | build-only / unverified |
| 190 | fix/ios27-black-screen-muse-20261122 | 2026-11-22 | build-only / unverified |
| 184 | feat/audio-ios27-carry | 2026-11-22 | build-only / unverified |
| 178 | feat/power-ios27-branch | 2026-11-22 | build-only / unverified |
| 120 | feat/wifi-ios27-abi | 2026-11-19 | build-only / unverified |
| 120 | backup/wifi-ios27-20261120 | 2026-11-19 | build-only / unverified |
| 108 | feat/gpu-27 | 2026-11-22 | build-only / unverified |
| 100 | feat/ufs-27 | 2026-11-22 | build-only / unverified |
| 68 | feat/xnu27-data-gate | 2026-11-22 | build-only / unverified |
| 67 | feat/xnekom-ios27-pick | 2026-11-21 | build-only / unverified |
| 64 | test/wifi-he-scan | 2026-11-19 | build-only / unverified |
| 56 | feat/wifi-ios27-tree | 2026-11-22 | build-only / unverified |
| 56 | feat/audio-official-27-mapping | 2026-11-21 | build-only / unverified |
| 53 | feat/wifi-station-archive-check | 2026-11-21 | build-only / unverified |
| 52 | feat/official-requirements-r80 | 2026-11-21 | build-only / unverified |
| 35 | feat/carrier-merge-trial | 2026-11-20 | build-only / unverified |
| 33 | feat/adsp-carrier | 2026-11-17 | build-only / unverified |
| 26 | xnekom-ios27 | 2026-11-20 | build-only / unverified |
| 25 | feat/platform-27 | 2026-11-22 | build-only / unverified |
| 18 | feat/input-27 | 2026-11-22 | build-only / unverified |
| 16 | feat/charge-auth | 2026-11-20 | build-only / unverified |
| 5 | docs/bt-data-mount-gate | 2026-11-20 | build-only / unverified |
| 4 | feat/display-27 | 2026-11-21 | build-only / unverified |
| 3 | feat/xnu27-psci-target | 2026-11-20 | build-only / unverified |
| 2 | docs/xnu-16-to-27-ladder | 2026-11-20 | build-only / unverified |
| 1 | feat/usb-27 | 2026-11-21 | build-only / unverified |
| 1 | feat/readme-pitfall-262 | 2026-11-20 | build-only / unverified |
| 1 | feat/osservices-27 | 2026-11-21 | build-only / unverified |

## Rules

1. Every branch here is a candidate implementation, not evidence. It must not be called working before an on-device flight.
2. Only MAIN-BASELINE.toml entries with state = "booted" count as passed; build-only must say why it has not flown.
3. Merge priority depends on whether the branch is needed for the stage-0 boot chain, not on commit count.
4. A line must hand over step 7 static checks plus prewritten pass/fail criteria before a flight slot; results go back into the baseline table.
