# Boot-death suspects: why the wifi images died before any console output

Status: working hypothesis ledger (⑧). Written 2026-11-15 after
`wifi-20261116mhi3` and `wifi-20261116mhi4` both returned
`state=port-not-observed, bytes=0, returnedToFastboot=true` with a zero-byte
console. The rule for this file: **every row carries evidence and a way to
disprove it; nothing here is a code change.**

## 0. What is actually known

- The silence happens **before any kernel output**. `k60_usblog_start()` is
  called from `bsd_init.c` after `mac_policy_initbsd()` (patch
  `0300-k60-usblog-ep0.patch`, inserted after
  `if (result == KERN_SUCCESS)`), so a zero-byte console means the machine
  never reached that point: the kernel died or was never entered.
- Both flights were supervised (`usblog-20261115-002243` for mhi4,
  `usblog-20261115-002804` for mhi3): `bootAccepted=true`,
  `bootExitCode=0`, `returnedToFastboot=true`, capture side clean
  (`portSeen=false` is the device never enumerating CDC-ACM, not a collector
  fault).
- mhi3 and mhi4 differ **only** in the ADT window (`0x130000000` vs
  `0x120000000`): payload kernels byte-identical (`83b52b56…`), build args
  identical, boot.img sizes identical (201,887,744 B). The peer that boots,
  `bt-s4a-20261114f`, has the same 4.5 GiB window and differs from mhi4 in
  exactly one boot argument (`k60bt=1` instead of `pong_wifi=1`) — but a
  different kernel, so it is suggestive, not controlled.

## 1. The stale-kernel confound (established, not a suspect)

mhi3/mhi4 were built from `kernel.macho` (65,978,368 B, Nov 14 23:12) that
predates the rebase and the new `.config`. Kernel build picks it up whenever
the file is newer than the marker; `.config` changes do not invalidate it.
Consequences, all measured on the stale image:

| fact | stale (mhi3/mhi4) | mhi5 |
|---|---|---|
| kernel bytes | 65,978,368 | 117,305,344 |
| battery symbol | absent | `_k60_physical_battery_start` present |
| `__DATA` vmsize | 0x1c8000 (1.8 MiB) | 0x32b0000 (50.6 MiB) |
| `K60LDO` strings (retired touch probe) | 5 | 0 |
| series baked into image | 229 (pre-rebase) | 224 |

So mhi3/mhi4 tested **neither** the current series **nor** the current
config. Any "wifi images die" conclusion drawn from them is unsound; mhi5 is
the first image that tests the current tree.

## 2. Suspects

### S1. PWF2 firmware blob in `__TEXT,__const` (11.2 MB) — structural, still alive

- Source: `scripts/build-k60-wifi-native.py:102` emits
  `.section __TEXT,__const` + `.p2align 12` + `.incbin`; the whole PWF2
  container (PongWifiFirmware.bin, 11,189,974 B) lands in the kernel's
  read-only first segment.
- Measured: mhi5 `__TEXT` vmsize 0xc64000 (12.4 MB) with
  `__const` 0xb38ed6 (11.2 MB), vs every booting kernel
  (`bt-s4a`, `touch`, `brightness`, lead-out) at `__TEXT` 0x1a4000
  (1.6 MB) with `__const` 0x86028 (0.5 MB).
- Why it could kill: `DarwinBoot.c:195-196` rejects a kernel whose
  Base..End span exceeds `WINDOW_SIZE - 2 MB` — not the binding constraint
  here (mhi5 span 123.6 MB, stale 74.7 MB, both < 254 MB). The sharper risk:
  `AllocateWindow` (`:452-509`) must find `WindowSize` (4.5 GiB)
  **contiguous** in `EfiConventionalMemory` while the loader still holds the
  whole kernel image in pool; a bigger image shrinks the biggest run.
- How to disprove: fly mhi5 (same 11.2 MB `__TEXT`). If mhi5 reaches
  SpringBoard, the blob is exonerated. If mhi5 dies identically, rebuild one
  image with the firmware moved to `__DATA` (one-line change in
  `build-k60-wifi-native.py`) and fly it.

### S2. Window arithmetic with the new kernel size — computed, mhi5 is the test

- `need ≈ window + kernel_image + fixed` (`LOCAL-VERIFICATION.md`
  §5.16 model, fixed ≈ 177 MB measured on the stale pair). For mhi5 at 4.5 GiB:
  4608 + 112 + 177 = 4897 MB against a 5120 MB arena → slack ≈ +223 MB.
- The stale pair at 4.5 GiB was 4608 + 63 + 177 = 4848 → slack +272 MB, and
  **it still died silently**, so window slack alone does not rescue a boot.
- How to disprove: mhi5 again. Its result also refines the fixed overhead.

### S3. Retired touch `spmi-probe` patch (Lead's HR-01 hypothesis) — weakened

- The patch (`zzzzzz…-pong-touch-spmi-probe.patch`, 93 lines) maps SPMI
  core/observer and polls before `geni_spi_init()` in
  `pong_goodix.c` `bring_up()`. It was in the 229-line series that
  mhi3/mhi4 shipped, so they were exposed.
- Counterevidence: `K60LDO` probe output appears in many healthy captures
  (`usblog-20261113-045951` lines 624-643, `basef2`/`basef4` with
  SB=129) — the probe ran to completion on boots that reached userland.
- Also: it is **not** in the current 224-line series and mhi5 does not carry
  it, so the mhi5 flight is the cleanest test of this hypothesis available
  without another build.

### S4. `pong_wifi=1` kills the boot before the worker's first log — weak

- `ArmDTPlatform.cpp:228` calls `pong_wifi_start_optional()` after
  `registerService()`; the worker first waits up to 120 s for the console
  (`PongWifiPlatform.cpp:655`), so wifi code cannot explain a console that
  never starts.
- The peer flight `bt-s4a-20261114f` differs from mhi4 in exactly one arg
  (`k60bt=1` vs `pong_wifi=1`) and boots. But its kernel is the
  bt line's build (105.5 MB, no wifi objects), so this is suggestive, not
  controlled.
- How to disprove: the mhi5 flight; and if needed, a `pong_wifi=0` build
  of the **same** wifi kernel as an on-device control.

## 3. What each next flight decides

| flight | decides | if it boots | if it dies |
|---|---|---|---|
| mhi5 (ready, 4.5 GiB) | S1+S2 jointly, and retires the stale confound | blob and window model survive; next step is the MHI handshake logs | rebuild with firmware in `__DATA` (`S1` variant) becomes the next image |
| firmware-in-`__DATA` rebuild | isolates S1 | blob placement was the killer | S1 falsified; investigate loader/pool (`S2`) with the `NO WINDOW` diag line |
| `pong_wifi=0` same-kernel control | isolates S4 | wifi driver code implicated | arg/kernel-size interaction implicated |

## 4. Evidence index

- Flights: `/mnt/e/k60-work/evidence/usblog-20261115-002243` (mhi4),
  `usblog-20261115-002804` (mhi3); healthy peers
  `usblog-20261115-012913` (bt-s4a), `usblog-20261115-013520`
  (brightness-4), `usblog-20261114-150931` (touch-20261114a).
- Kernel forensics: `out-wifi/mondrian/…/kernel/stale/kernel-20261114-2312.macho`
  vs current `kernel.macho`; segment tables in the section above measured
  with `E:/k60-work/scratch/seg3.py`.
- Loader constraints: `DarwinBoot.c:168` (segment ≤ 256 MB),
  `:195-196` (span ≤ 254 MB), `:452-509` (contiguous
  `AllocateWindow`), `:723` (ADT `darwinboot-memory-size`),
  `:775` (`Used > WindowSize - BLOCK_SIZE`), `:794`
  (`Args->MemorySize = WindowSize`).
- Probe script: `E:/k60-work/scratch/seg3.py` (segment tables).
