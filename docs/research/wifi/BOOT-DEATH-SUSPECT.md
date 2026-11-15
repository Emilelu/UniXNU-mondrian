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
  `0x120000000`). Kernel identity must be read from
  `build-manifest.json:components.payload_kernel`, **not** from
  `boot.json:kernel_sha256` — that field hashes the boot image's kernel slot
  (gzip of the 112 B shim plus the 3,145,728 B firmware volume, then the DTB),
  so it is `83b52b56…` on every image that shares the firmware volume (P-200).
  Measured the right way: mhi3 = `0addbb48…`, mhi4 = `e24a58f1…`, both
  65,978,368 B, differing in 47 bytes (26 in `__TEXT`, 21 in
  `__PRELINK_INFO`); `payload.img` is byte-identical and the boot images
  differ in 324 bytes. The peer that boots, `bt-s4a-20261114f`, has the same
  4.5 GiB window and differs from mhi4 in exactly one boot argument
  (`k60bt=1` instead of `pong_wifi=1`) — but a different kernel, so it is
  suggestive, not controlled.

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

### S1. PWF2 firmware blob in `__TEXT,__const` (11.2 MB) — **negated by the T2 flight on 2026-11-15**

- Source: `scripts/build-k60-wifi-native.py:102` emits
  `.section __TEXT,__const` + `.p2align 12` + `.incbin`; the whole PWF2
  container (PongWifiFirmware.bin, 11,189,974 B) lands in the kernel's
  read-only first segment.
- Measured on six payload kernels, section table of the `kernel.macho`
  extracted from each `boot.img` (`E:/k60-work/scratch/constsz.py`):

  | image | kernel bytes | `__TEXT` vmsize | `__const` | PWF2 magic | on device |
  |---|---|---|---|---|---|
  | springboard-20261114c | 105,480,192 | 0x1a1321 | 0x85e18 (0.52 MiB) | 0 | SpringBoard |
  | gpu-20261114t | 105,476,096 | 0x1a100e | 0x86028 (0.52 MiB) | 0 | SpringBoard |
  | brightness-9 | 105,500,672 | 0x1a1520 | 0x86038 (0.52 MiB) | 0 | SpringBoard |
  | wifi-20261116mhi5 | 117,305,344 | 0xc61645 | 0xb38ed6 (11.22 MiB) | 2 | untested |
  | wifi-20261116a2 | 65,978,368 | 0xc60ad5 | 0xb38ed6 (11.22 MiB) | 2 | silent |
  | wifi-20261116mhi3 | 65,978,368 | 0xc60c11 | 0xb38ed6 (11.22 MiB) | 2 | silent |

  The 11.19 MB delta between the two groups is exactly the firmware blob, and
  it is the only clean structural difference between kernels that reach
  SpringBoard and kernels that never print a byte. Inside `__TEXT` the blob is
  the first thing mapped: `__const` sits at file offset 0x2000
  (`addr 0xfffffff007006000` for mhi5), with `__cstring` only after it at
  file offset 0xb3aed6. Every booting kernel starts `__cstring` at 0x89008.
- **`a2` does not exonerate the blob.** `wifi-20261116a2` carries the same
  0xb38ed6 `__const`, so whatever it does on device says nothing about S1; it
  only tests the driver (`pong_wifi=0`, no MHI). The earlier plan "if a2 is
  silent, move on to residency" was wrong for exactly this reason.
- Why it could kill: `DarwinBoot.c:195-196` rejects a kernel whose
  Base..End span exceeds `WINDOW_SIZE - 2 MB` — not the binding constraint
  here (mhi5 span 123.6 MB, stale 74.7 MB, both < 254 MB). The sharper risk:
  `AllocateWindow` (`:452-509`) must find `WindowSize` (4.5 GiB)
  **contiguous** in `EfiConventionalMemory` while the loader still holds the
  whole kernel image in one `AllocateZeroPool`; a bigger image shrinks the
  biggest run (`MemoryMapLib.c:82-88` records a failure at a 320 MiB heap with
  "biggest run 0xF0A0000").
- How to disprove: fly T0 `wifi-20261115z0` (`pong_wifi=0`, kernel
  117,305,344 B, same 0xb38ed6 blob). SpringBoard reached → the driver is
  exonerated and the blob is still alive as a suspect for mhi5; silent →
  blob or its residency is the killer, and T2 (blob into `__DATA`, or read
  from the Data volume at runtime) becomes the next image.

- **Outcome — the disproving flight has been flown.** T0 `wifi-20261115z0`
  (blob in `__TEXT`, `pong_wifi=0`, kernel 117,305,344 B) was silent
  (`usblog-20261115-135859`, 0 bytes), so T2 was built and flown:
  `wifi-20261116t2` keeps the same 117,305,344 B kernel with the blob moved
  into `__DATA,__const` (ld placed it in `__DATA_CONST`, 12,124,160 B;
  `__TEXT` dropped 12,992,512 → 1,802,240) and it was **still silent**
  (`usblog-20261115-161102`, 0 bytes). S1 is therefore **negated — excluded,
  not a suspect**: blob residency is not the killer. What remains is the
  pool/window channel and the driver-body static path; see
  `DARWINBOOT-POOL.md`.

### S2. Window arithmetic with the new kernel size — **downgraded to bookkeeping**

- `need ≈ window + kernel_image + fixed` (`LOCAL-VERIFICATION.md`
  §5.16 model, fixed ≈ 177 MB measured on the stale pair). For mhi5 at 4.5 GiB:
  4608 + 112 + 177 = 4897 MB against a 5120 MB arena → slack ≈ +223 MB.
- **Why downgraded:** mhi4 already flew at 4.5 GiB with a 66 MB kernel and
  ≈ +272 MB of slack, and it was still silent. A model that predicts "safe"
  for a flight that died cannot be the explanation; keep it only to size the
  next image.
- It is not discarded because the loader really does need one contiguous
  4.5 GiB run, and a bigger kernel image does shrink the heap. But it is now a
  contributing-factor candidate behind S1, not a peer of it.

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

Order set by the Lead on 2026-11-15. Both T0 and T1 must come out of
`scripts/build-strict.sh` — a hand-packed control image carries no series
fingerprint and proves nothing (P-201).

One reading rule for the rebuild: the 11 `Pong MHI` format strings in the
archive are a **link check, not a health check**. `wifi-20261116mhi4` carried
the same 11 strings and still produced a zero-byte console, so their presence
says only that the right archive was linked in. Nothing in the flight evidence
may cite them as proof that the driver runs.

| order | flight | decides | if it boots | if it dies |
|---|---|---|---|---|
| **T0** | `wifi-20261115z0` (ready: `pong_wifi=0`, kernel 117,305,344 B, blob present, 4.5 GiB) | the driver vs the blob: same kernel as mhi5, wifi arg off | driver code is implicated → fly T1 to test the full stack | driver exonerated → the blob or its residency is the killer → go straight to T2 |
| **T1** | `wifi-20261116mhi5` (ready, 117,305,344 B, `pong_wifi=1`) — only after T0 boots | S1+S2 on the full wifi stack, and retires the stale confound | the MHI handshake logs become the next evidence | blob/loader interaction confirmed without the driver |
| **T2** | rebuild with the firmware in `__DATA` (or read from the Data volume at runtime) — **only if T0 is silent** | isolates blob placement | placement was the killer | S1 falsified; investigate loader/pool with the `NO WINDOW` diag line |
| **T3** | `wifi-20261116c0` — **flown 2026-11-15 21:32: silent (0 B console, `usblog-20261115-213221`)**; 66 MB, blob in `__TEXT`, `pong_wifi=0`, no GPU/battery | the formal C cell: driver trigger vs death without the driver | `pong_wifi=1` is the trigger → driver guilty → T1 | **invalid config, not a layout datum** (`6DCCF70A…` seed UUID, P-152) → §3e |
| **T4** | `wifi-20261116c2` (built 2026-11-15 23:35, not flown) — baseline config + `PONG_WIFI=y`, container in `__DATA_CONST` (§3f) | whether `__TEXT` placement/size is the killer once the config is one that boots | `__TEXT` growth is the killer — the only trait every silent wifi image shares | placement irrelevant → c3: the same image with a 64 KiB container stub |
| **T5** | `wifi-20261116c3` (built 2026-11-16 01:34, not flown) — the c2 recipe plus `patches/wifi/0012` (§3h) | the UFS lease: the lock was only allocated from `pong_wifi_start_optional()`, which runs after UFS asks for the lease, so the lease could never be held on a wifi kernel | the lease was the blocker; every earlier wifi flight died in `hostBringUp()` before the console worker | the lease return value is not the blocker → c4 drops the `transportFailure` and lets UFS continue without it |

The scope narrowing is deliberate: `__TEXT,__const` is `0xb38ed6` in z0, mhi5
**and** the 65.9 MB mhi4 kernel, so "blob lives in `__TEXT`" is not by itself
the difference between a boot and a silent death. What T0 isolates is the
117 MB kernel *with* the blob and the wifi driver switched off; only if that
image is also silent does moving the blob become the next thing worth testing.
If T0 boots, the volume/residency theory loses its base and T2 is dropped.

**Status after the flights (2026-11-15).** T0 was silent
(`usblog-20261115-135859`), so T2 was built and flown; T2 was silent too
(`usblog-20261115-161102`) — the "if it dies" cell of the T2 row came true:
S1 is falsified and the next step is the loader/pool analysis in
`DARWINBOOT-POOL.md` (the `NO WINDOW` diag line and its capture channels).
T1 (`wifi-20261116mhi5d`) is parked by the Lead. The bt pair adds a
non-monotonic datum: bt-s4b-20261115b (106,541,056 B) reached the desktop
(`usblog-20261115-140927`, console 213,434 B) while bt-s4b-20261115c (same
106,541,056 B, series 228→229, one patch) was silent
(`usblog-20261115-163144`, 0 bytes), and bt-s4c-20261115c (105,508,864 B,
series 229) reached the desktop again (`usblog-20261115-162553`, console
245,222 B) — the size/window model explains none of the three.

The formal C cell (`wifi-20261116c0`, 66 MB, `pong_wifi=0`) was built and flown
on 2026-11-15 21:32 — silent (`usblog-20261115-213221`, 0-byte console). With the
driver off and a kernel 40 MB smaller than the bt pair that boots, size no longer
explains the death: what is left is the kernel's content layout, and the only
segment that exceeds its non-wifi counterpart is `__TEXT` (§3d).

**That reading was overturned at 23:00 the same night.** The c0 payload kernel
embeds the *seed* Data volume UUID `6DCCF70A-…` instead of the volume the device
publishes (`1BCD69FF-…`); §3e shows the string test on six payload kernels. Under
P-152 that is a self-panic inside the root mount — before `k60_usblog_start()`, so
the 0-byte capture is the expected output — and only c0 carries it. The 117 MB
family (z0, t2, mhi5d) all embed the real UUID, so **their silence is still
unexplained** and the layout question is open for them, not answered by c0.

c1 repeated the c0 shape with the correct UUID and was silent as well
(`usblog-20261115-231707`, 0 bytes), so the seed UUID explains c0 only: it does
not account for the 117 MB family, and the Lead reads c1 as an invalid
measurement of the layout question rather than as a failed UUID fix. What all
six silent images share is `CONFIG_XNU_PONG_WIFI=y`; every image that boots is
the baseline shape. c2 (§3f) splits that in one variable: the booting config,
the container moved into `__DATA_CONST`, the driver still linked.

## 3a. The T0 control image (built 2026-11-15 03:49)

`wifi-20261115z0` — first image of this line that is both a control and a
`build-strict.sh` artifact, so its manifest carries the series fingerprint
that `wifi-20261116a2` lacked (P-201):

| field | value |
|---|---|
| series | 224 patches, `34cf51e4d10e46eb3514d798a3e3208c3ac7f124dd8a982585e9eea1e8b9c8c0` |
| `components.payload_kernel` | `ec094bc952930d30f5b18ee43a1e19e0d06898309ec46e80e43121595498ce22` |
| kernel bytes | 117,305,344 (same size as mhi5, different bytes: the arg is baked into the payload) |
| `__TEXT` / `__const` | 0xc64000 / `0xb38ed6` (11.22 MiB, PWF2 magic present twice) |
| `boot.img` | `c2e069f0088a0728e24dbc89338edee2ba9d5f453265d63d42ccb64bc3303728`, 201,887,744 B |
| ADT window | `0x120000000` (4.5 GiB) |
| boot args | 30, 587 B, last one `pong_wifi=0` |
| gates | eight-step passed, kernel archives 4/4, image-arg-audit OK, verify-boot-image OK |

Because the kernel size, the firmware blob and the window all match mhi5 and
only the boot argument differs, z0 is the controlled test of "driver versus
blob" that the plan needs.

### 3b. How tight the control is, measured on the two payloads

Both images carry a 117,305,344-byte `Payloads/kernel.macho` and the two
files differ in **46 bytes across 8 runs**, all of them build metadata:

| offset | bytes | what it is |
|---|---|---|
| 0x13b0-0x13bf | 16 | `LC_UUID` of the Mach-O |
| 0x64c7f-0x64c8d | 15 | `Sun Nov 15 03:45:55 CST 2026` (z0) vs `Sun Nov 15 02:28:53 CST 2026` (mhi5), the two `Darwin Kernel Version` strings |
| 0x6fdecd8-0x6fdeced | 22 | prelink session id in `__PRELINK_INFO` |

Every segment has the same size and the same content otherwise, including
the 11,767,510-byte `__TEXT,__const` that holds the PWF2 container
(`0xb38ed6` in z0, mhi5 **and** mhi4 — the blob did not move between the
three). So z0 tests exactly one variable: the last boot argument,
`pong_wifi=0` instead of `1`. Nothing about the firmware, its section, the
window or the kernel size can explain a difference in outcome.

The firmware section is present in mhi4 too, which matters for reading the
mhi3/mhi4 result: the 65.9 MB stale kernel already carried the 11.2 MiB
`__TEXT,__const` blob, so "blob in __TEXT" alone was never the difference
between the silent pair and the images that boot.

### 3c. The formal C cell: `wifi-20261116c0` (built and flown 2026-11-15: silent)

The Lead's C cell as a strict-build artifact: `configs/mondrian_wifi_defconfig`
(board dir `mondrian_wifi`, P-187) — the 66 MB wifi-only kernel, firmware blob
in `__TEXT`, `pong_wifi=0`, no GPU addon, no battery.

| field | value |
|---|---|
| series | 224 / `34cf51e4…` |
| kernel | `cab23f659f0410e1ad8af51bd580771a6a8beab4ae2dbaabfb3fd0af0f2bbd77`, 66,002,944 B |
| payload kernel | `1600744e7f501d607e1ea5f0e98651c3aaf35ac1baa3bd30ba5d45206391e252` |
| `boot.img` | `25c9821510ca50032617b61e63b058580722e375ee5b533badf3d74c07a9d074` |
| `__TEXT` / `__DATA` | 0xc64000 / vmsize 0x1c8000; PWF2 ×2, `Pong MHI` ×11, K60LDO ×0 |
| symbols | `_pong_wifi_start_optional`=1, `_k60_physical_battery_start`=0 |
| boot args | 30, last one `pong_wifi=0` |

It decides exactly the two-way split: boots → the driver is guilty
(`pong_wifi=1` is the trigger); silent → the death is independent of the
driver and the pool/window channel is the sole remaining suspect
(`DARWINBOOT-POOL.md` §5). The Lead queues it after the bt bisection pair
(h1→h3→h1+h3); every flight needs user + Lead approval and a recording.

Building it exposed two fixed infra gaps, both recorded on main:
- **P-206** (main `c97a4cf`, snap-r197): a fresh board dir's fakeroot never
  gets `Availability.h`/`AvailabilityInternal.h`/`TargetConditionals.h`
  (the AvailabilityVersions install at `build-xnu-4k-baseline.sh:43-51`
  ships only `AvailabilityVersions.h` + `availability.pl`, and
  `scripts/linux/prepare-xnu.py source` never runs in the ios16 path), and
  `check-build-env.py:27` hardcoded `…/mondrian` so P-185 graded the old
  tree instead of the active board dir (fake green). Worked around here by
  `cp -a` of the five items from the seeded `mondrian` fakeroot.
- `1438346`: without GPU addon the 0610 patch still demands
  `osfmk/arm64/k60_metal_blob.s`; the build now emits an empty K60M
  container (8 bytes, `K60METAL bad count 0` at runtime) instead of
  breaking the link.

### 3c result (flown 2026-11-15 21:32)

| field | value |
|---|---|
| evidence | `E:/k60-work/evidence/usblog-20261115-213221` |
| `boot.img` | `25c9821510ca50032617b61e63b058580722e375ee5b533badf3d74c07a9d074` (matches the built artifact) |
| console | **0 bytes**; `port-not-observed`, `returnedToFastboot`, `fastboot-return` |
| judge | `silent` / exit 2 (`scripts/judge-z0.sh … --expect-arg pong_wifi=0`) |
| args | `["pong_wifi=0"]`; payload args last item `pong_wifi=0` |

T3 is silent, and at first read that looked like the "if it dies" cell: driver
off (`pong_wifi=0` returns before the worker starts), boot argument off, and
40 MB smaller than the bt pair that boots. It is not, because the image was built
from a defconfig that named the wrong Data volume UUID (§3e): P-152 predicts a
self-panic inside the root mount and exactly this 0-byte, `fastboot-return`
capture, so the flight cannot say anything about segment layout. What it does
still establish is mechanical: a 66 MB kernel built from the wifi defconfig goes
through the same loader path as the 106 MB one. The layout suspects stay where
they were — on the 117 MB family.

## 3d. The 66 MB wifi kernel against the 106/129 MB kernels that boot

Method: `mcopy -o -i boot.img@@557056 ::/EFI/UniXNU/Payloads/kernel.macho`, then
walk `LC_SEGMENT_64` / `section_64` (`E:/k60-work/scratch/table4.py`). All four
images carry the same 4.5 GiB ADT window (`0x120000000`), so the window is not a
variable here. Sizes are vmsize unless two numbers are given (`vmsize /
filesize`).

**c0 is a shape reference, not a layout witness** (§3e): its silence is now
attributed to the seed Data UUID in its defconfig, so the table below compares
what a 66 MB wifi kernel looks like; it cannot be used to argue that `__TEXT`
kills. The layout question is carried by the 117 MB images (z0, t2, mhi5d),
which are not in this table.

| segment | c0 (66.0 MB, silent) | bt-s4b-b (106.5 MB, boots) | bt-s4c-c (105.5 MB, boots) | adsp-c (129.0 MB, boots) |
|---|---|---|---|---|
| `__TEXT` | **12,992,512** | 1,720,320 | 1,720,320 | 1,720,320 |
| `__DATA_CONST` | 933,888 | 1,949,696 | 917,504 | 917,504 |
| `__TEXT_EXEC` | 8,781,824 | 8,388,608 | 8,388,608 | 8,388,608 |
| `__KLD` | 16,384 | 16,384 | 16,384 | 16,384 |
| `__LASTDATA_CONST` | 16,384 | 16,384 | 16,384 | 16,384 |
| `__KLDDATA` | 16,384 | 16,384 | 16,384 | 16,384 |
| `__DATA` | 1,867,776 / 294,912 | 52,920,320 / 51,576,832 | 52,920,320 / 51,576,832 | 76,414,976 / 75,071,488 |
| `__BOOTDATA` | 294,912 | 294,912 | 294,912 | 294,912 |
| `__PRELINK_TEXT` | 7,421,952 | 7,421,952 | 7,421,952 | 7,421,952 |
| `__PRELINK_INFO` | 454,656 | 454,656 | 454,656 | 454,656 |
| `__PLK_TEXT_EXEC` | 22,757,376 | 22,757,376 | 22,757,376 | 22,757,376 |
| `__PRELINK_DATA` | 1,409,024 | 1,409,024 | 1,409,024 | 1,409,024 |
| `__PLK_DATA_CONST` | 3,670,016 | 3,670,016 | 3,670,016 | 3,670,016 |
| `__LINKINFO` | 278,528 | 278,528 | 278,528 | 278,528 |
| `__LINKEDIT` | 6,668,288 / 6,663,376 | 6,569,984 / 6,568,720 | 6,569,984 / 6,569,232 | 6,569,984 / 6,554,672 |

Sections that carry the difference:

| section | c0 | bt-s4b-b | bt-s4c-c | adsp-c |
|---|---|---|---|---|
| `__TEXT,__const` | **11,767,510 @0x2000** | 548,936 @0x1d60 | 548,936 @0x19e0 | 548,952 @0x2b00 |
| `__TEXT,__cstring` | 1,078,732 @0xb3aed6 | 1,029,200 @0x87da8 | 1,030,093 @0x87a28 | 1,025,710 @0x88b58 |
| `__TEXT,__os_log` | 133,439 @0xc424a2 | 133,439 @0x1831f8 | 133,439 @0x1831f5 | 133,439 @0x183206 |
| `__DATA_CONST,__const` | 723,408 | 1,733,576 | 705,480 | 703,984 |
| `__DATA,__data` | 168,432 | 51,449,096 | 51,449,096 | 74,943,752 |

Answers to the three questions:

1. **Which segment exceeds its non-wifi counterpart?** Only `__TEXT`, by
   11,272,192 B (of which `__const` alone is +11,218,574), plus `__TEXT_EXEC`
   +393,216, `__LINKEDIT` +98,304 and `__DATA_CONST` +16,384 against
   bt-s4c-c/adsp-c (against bt-s4b it is 1,015,808 smaller). Every other segment
   is byte-identical. `__TEXT` is 7.55× the 1,720,320 the three booting kernels
   use. The `__TEXT_EXEC` excess is not attributed to a kext by this table.
2. **Where is the 11.76 MB `__const`?** Inside `__TEXT,__const`, which starts at
   file offset 0x2000 and ends at 0xb3aed6. The PWF2 container sits at 0x8f000,
   and `_pong_wifi_firmware` → `_pong_wifi_firmware_end` spans 0xaabed6
   (11,189,974 B), so 73,536 B of `__const` is assembler/Mach-O padding, not
   firmware.
3. **PWF2 section count and total?** c0: one real container, 6 header entries,
   11,189,974 B of firmware payload. A raw byte search shows two hits; the
   second (0xc418b7) is a `__cstring` string coincidence, the same artifact as
   z0's 12,852,307 — the symbol span is the reliable measure. bt-s4b-b,
   bt-s4c-c and adsp-c: zero hits.

**Caveat that changes how the table reads.** The 106/129 MB kernels are not
"the same kernel with a bigger blob": their 51.4 MB `__DATA,__data` is the
Metal/GPU addon (`PongMetalBridge` ×4, `libvulkan` ×6), and c0 has no GPU addon
at all (`mondrian_wifi_defconfig`: empty K60M stub, `PongMetalBridge` ×0). So
the 66-vs-106 comparison carries two variables — the wifi blob is in, the GPU
addon is out — and a "66 MB minus PWF2" image would also be a "no GPU addon"
image. Sharper controls, if the Lead wants comparable shapes: a kernel with the
GPU addon **and** no PWF2 container, or a 66 MB kernel whose `__const` holds a
same-size inert section. Both need a build decision.

### 3e. Why c0 died: the wifi defconfig named the seed's Data UUID (P-152)

The c0 kernel was built from `configs/mondrian_wifi_defconfig`, and that file
named `6DCCF70A-6FD6-403E-ACED-95313CD7CBB8` — the volume UUID of the 32 MiB
committed seed — instead of `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`, the volume
the device publishes (`docs/plans/MONDRIAN-OFFICIAL-PAGES.md:564`; P-152,
`docs/engineering/PITFALLS.md:3809-3820`).

The UUID is compiled into the kernel as `XNU_OWNER_DATA_VOLUME_UUID`, so "did
this image name the right volume" is decidable offline on the payload kernel:

| payload kernel | UUID literal | flight |
|---|---|---|
| `wifi-20261116c0` | **6DCCF70A** (seed) | silent (T3) |
| `wifi-20261115z0` | 1BCD69FF | silent (T0) |
| `wifi-20261116t2` | 1BCD69FF | silent (T2) |
| `wifi-20261116mhi5d` | 1BCD69FF | not flown |
| `bt-s4b-20261115b` | 1BCD69FF | desktop |
| `adsp-20261115c` | 1BCD69FF | desktop |

Method: `mcopy -n -o -i boot.img@@557056
::/EFI/UniXNU/Payloads/kernel.macho`, then `grep -c -a` for each literal. Only
c0 matches the seed UUID; every image built from `mondrian_defconfig` names the
real volume.

P-152's failure path is a self-panic *inside* the root mount, not a hang after
it: `PONG APFS: wait for Data UUID 6DCCF70A…, timeout=5s` → `K60DATA UFS Data
window not published` → `K60PANICARGS … datastage=0 dataerr=2 @kern_exec.c:8463`.
The USB console starts only after `vfs_mountroot`: in a healthy capture the
first `K60 USBLOG` line is around line 470 and `K60DATA mounted` around 484
(`usblog-20261115-*/console.log`, ~3.3 k lines). A root-mount self-panic
therefore **must** leave a 0-byte capture and return to fastboot — c0's exact
signature.

Consequences:

- **c0 is a config death, not a layout datum.** §3d's c0 row is a shape
  reference; it cannot carry the argument that `__TEXT` or the blob inside it
  kills.
- **The 117 MB family keeps its silence unexplained.** z0, t2 and mhi5d embed
  the real UUID, so P-152 does not cover them; the layout suspects in §2 and
  the pool/window channel in `DARWINBOOT-POOL.md` are still open for those three.
- **Gate gap:** `scripts/check-data-identity.py:31` pins
  `configs/mondrian_defconfig`, and no gate reads the wifi defconfig — which is
  how a seed UUID reached a formal build. Proposed fix (Lead to number it):
  grade every `configs/*_defconfig` that sets `CONFIG_XNU_OWNER_DATA_MOUNT=y`.
- The one-line fix is `configs/mondrian_wifi_defconfig:46` (commit `92e6390`);
  the rebuild keeps everything else identical and is the next flight.

#### The rebuild: `wifi-20261116c1` (built 2026-11-15 23:10, not flown)

| field | value |
|---|---|
| kernel | `4139da76c9ed491b26bd1ffc8dba41aaf961e3071f3900b78b1351d2b6f08b9f`, 66,002,944 B |
| payload kernel | `bd22476d5521ae921af31369b336c87820224fc7bf4b4b7fc36903abc7b622b5` |
| payload ADT | `3887ddfee3d94db025665aa0f889c9b1d206b0aa1b07c9f6c816b5607f7eb6fe` |
| `boot.img` | `76171061046f74a1ce8273505d3caf80254f70938ebfd5904a274fd109d38673`, 201,887,744 B |
| series | 224 / `34cf51e4…` |
| args | 30, 587 B, last `pong_wifi=0`; `kernel_args_requested = ["pong_wifi=0"]` |
| window | `0x120000000` (the property name sits 36 B before the u64 in the image) |
| gates | 3 archives present, metal stub self-consistent, image-arg-audit OK, verify-boot-image OK |

Offline identity check on the payload kernel: `1BCD69FF` occurs once,
`6DCCF70A` zero times. The c0 and c1 payloads are both 66,002,944 B and differ
in **76 bytes** (LC_UUID, the two `Darwin Kernel Version` timestamps, the
prelink session id, and the UUID literal); every segment and section is
identical, including `__TEXT` 12,992,512 and `__const` 11,767,510 @0x2000.
The flight is therefore single-variable by construction, and its two outcomes
read cleanly:

- boots → P-152 was c0's whole death; the earlier wifi silences (z0, t2, mhi5d)
  still need their own explanation;
- silent → the wifi defconfig has a second killer, and the next split is the
  booting family's exact shape (`GPU_ADDON=y` plus `PHYSICAL_BATTERY=y`).

## 3f. c2: the 117 MB image with the container moved off `__TEXT` (built 2026-11-15 23:35, not flown)

After the c1 flight the Lead's matrix reads: every image that returns 0 bytes
carries `CONFIG_XNU_PONG_WIFI=y`, and every image that boots is the plain
baseline shape (GPU addon in `__DATA`, no PWF2 container). Size, kernel
arguments, blob residency and the Data UUID are each excluded by a flight, so
what `PONG_WIFI=y` adds is the remaining variable: (1) the 11,767,510 B PWF2
container inside `__TEXT,__const`; (2) the MHI/PARF driver and its const data,
which `pong_wifi=0` gates at initialisation but does not unlink.

c2 separates (1) from (2) by starting from the configuration that boots:
`configs/mondrian_defconfig` (GPU addon, physical battery, the correct
`1BCD69FF` Data UUID) plus `CONFIG_XNU_PONG_WIFI=y` through
`XNU_PONG_WIFI=1` and `XNU_PONG_WIFI_ARCHIVE`, with the T2 one-line diff
(`.section __DATA,__const` in `scripts/build-k60-wifi-native.py`). Against
mhi5 and z0 the only difference is which segment holds the 11,189,974 B
container; against the booting baseline the difference is the container plus
the driver.

| field | value |
|---|---|
| kernel | `24ebc11c80afb022d93e8926b2bcbfd7e31aaabdafd4eef8151d27cd74e33f3d`, 117,305,344 B |
| payload kernel | `92c0ca3a03d0001f339b773db7bec426b941d7839b8877faf9119f341b5f66d9` |
| payload ADT | `c354390d9c1034b70efa5ad85b698b13c7596a621cbf177edf7c29a833e01a1f` |
| `boot.img` | `dc7e4186f7378cea0cc6e9a3755609370a9b651983aa47375ee1099c5ad057e5`, 201,887,744 B |
| series | 224 / `34cf51e4…` |
| args | 30, 587 B, last `pong_wifi=0`; `kernel_args_requested = ["pong_wifi=0"]` |
| window | `0x120000000` (u64 at property name + 36 B) |
| wifi archive | `de3f48a53f1ff17c1ad4f4b36561f6ffb5c9edc114b539416f11cfd7465dc399` |
| gates | 4 archives present, metal blob self-consistent, image-arg-audit OK, verify-boot-image OK, eight-step 30 |

`build-manifest.json` records `gpu_addon` as empty here, because that field
only mirrors an explicit `--gpu-addon` argument; the plugin is embedded by the
build itself, which the kernel proves: `_k60_metal_blob` symbols (`__DATA,__const`) and
the strings `PongMetalBridge` ×4, `libvulkan` ×6, `AGXMetal` ×6.

### The single variable, measured on the payload kernel

| segment / section | c2 (117,305,344) | mhi5 / z0 (117,305,344) | bt-s4c-c (105,508,864) |
|---|---|---|---|
| `__TEXT` | 1,802,240 | 12,992,512 | 1,720,320 |
| `__TEXT,__const` | 574,905 @0x32c0 | 11,767,510 @0x2000 | 548,936 @0x19e0 |
| `__DATA_CONST` | 12,124,160 | 933,888 | 917,504 |
| `__DATA_CONST,__const` | 11,919,062 @0x1b9000 | 725,192 @0xc65000 | 705,480 |
| `__DATA` filesize | 51,576,832 | 51,576,832 | 51,576,832 |
| `__TEXT_EXEC` | 8,798,208 | 8,798,208 | 8,388,608 |
| `__LINKEDIT` | 6,668,288 / 6,664,608 | same | 6,569,984 / 6,569,232 |
| PWF2 container | 1, at 0x26b000 (`__DATA_CONST`) | 1, at 0x8f000 (`__TEXT,__const`) | none |

The container is intact, not a stub: header count 6, records are
`name[32] + u32 offset + u32 size` (stride 40), payload starts at container
offset 0x1000, and the six records (amss.bin 5,470,128; amss20.bin 5,296,128;
bdwlan.elf 59,932; bdwlang.elf 59,936; m3.bin 266,684; regdb.bin 24,278) end at
11,189,974 B, exactly the `_pong_wifi_firmware` → `_pong_wifi_firmware_end`
span (0xaabed6). The second naked `PWF2` hit at 0x1965f6 is a `__cstring`
coincidence: its count field reads 1852788736, so it is not a second container.

### What each outcome means

- boots (K60DATA mounted, SpringBoard ≥ 100 lines) → the killer is the
  `__TEXT` placement or the 11.19 MB `__TEXT` growth, which is now the only
  trait every silent wifi image shares;
- silent → segment placement is irrelevant and the next split is c3: the same
  image with a 64 KiB truncated container that keeps the PWF2 header and the
  six-record table but drops the payload.

§3g answers the layout half of this statically: no segment, span or `Used`
value of any wifi image is near a `DarwinBoot.c` limit, so the outcome above is
about content and placement only, never about the loader running out of window.
A note on the build script: `run-c2.sh` first asserted `gpu_addon` in the
manifest, and that field only mirrors an explicit `--gpu-addon` flag, so the
assertion measured the wrong object — the P-194 / P-200 / P-201 / P-211 family
("the field describes the flag, not the image"). It now proves the plugin and
the container from the payload kernel itself (`PongMetalBridge` and `PWF2`
string hits plus the `_k60_metal_blob` symbol), which is the only reading that
describes the artifact.

## 3g. Static arithmetic: segment sizes against the DarwinBoot window (2026-11-16)

The Lead's remaining layout hypothesis was that the wifi kernels push a segment
or the total image past a granularity the loader allocates in. It is answerable
without a flight: read every `LC_SEGMENT_64` from the payload kernel, add the
ADT size, and compare against the four limits `DarwinBoot.c` actually enforces.
Measured with `E:/k60-work/scratch/winmath3.py` (`mcopy` the payload kernel and
its `.adt` out of each `boot.img`, then follow the loader's own arithmetic):

| limit | `DarwinBoot.c` | value |
|---|---|---|
| one segment | `:168` `Segment->Size > WINDOW_SIZE` → `EFI_LOAD_ERROR` | 256 MiB |
| kernel span (`End - Base`) | `:195-196` `> WINDOW_SIZE - SIZE_2MB` | 254 MiB |
| `Used` inside the window | `:775` `Used > WindowSize - BLOCK_SIZE` → `EFI_BAD_BUFFER_SIZE` | 4606 MiB (4608 − 2) |
| window itself | `:452-513` one `AllocatePages` of `WindowSize` bytes | 4608 MiB (`0x120000000`) |
| image in the DXE pool | `:116` `AllocatePool(*Size)` + UniXNU's `AllocateZeroPool` copy | 2 × kernel bytes in a 384 MiB heap |

`Used` follows `:757-772`: `ALIGN(span, 16K) + page + ADT`, then `ALIGN(…, 16K)`,
then one more page for the trampoline.

| image | kernel B | Σ vmsize MiB | span MiB | max seg MiB | Used MiB | 2× image MiB | heap left MiB | args |
|---|---|---|---|---|---|---|---|---|
| wifi-20261116c2 | 117,305,344 | 113.37 | 123.64 | 50.69 | 123.68 | 223.74 | 160.26 | `pong_wifi=0` |
| wifi-20261115z0 | 117,305,344 | 113.37 | 123.64 | 50.69 | 123.68 | 223.74 | 160.26 | `pong_wifi=0` |
| wifi-20261116t2 | 117,305,344 | 113.37 | 123.64 | 50.69 | 123.68 | 223.74 | 160.26 | `pong_wifi=0` |
| wifi-20261116mhi5d | 117,305,344 | 113.37 | 123.64 | 50.69 | 123.68 | 223.74 | 160.26 | `pong_wifi=1` |
| wifi-20261116c1 | 66,002,944 | 64.45 | 74.71 | 21.70 | 74.75 | 125.89 | 258.11 | `pong_wifi=0` |
| wifi-20261116c0 | 66,002,944 | 64.45 | 74.71 | 21.70 | 74.75 | 125.89 | 258.11 | `pong_wifi=0` |
| wifi-20261116mhi4 | 65,978,368 | 64.43 | 74.70 | 21.70 | 74.74 | 125.84 | 258.16 | `pong_wifi=1` |
| bt-s4b-20261115b (alive) | 106,541,056 | 102.89 | 113.15 | 50.47 | 113.19 | 203.21 | 180.79 | `k60bt=1` |
| bt-s4b-20261115c (silent) | 106,541,056 | 102.89 | 113.15 | 50.47 | 113.19 | 203.21 | 180.79 | `k60bt=1` |
| bt-s4c-20261115c (alive) | 105,508,864 | 101.90 | 112.17 | 50.47 | 112.21 | 201.24 | 182.76 | `k60bt=1` |
| adsp-20261115c (alive) | 128,991,232 | 124.31 | 134.57 | 72.88 | 134.61 | 246.03 | 137.97 | — |
| springboard-20261114c (alive) | 105,480,192 | 101.89 | 112.15 | 50.47 | 112.19 | 201.19 | 182.81 | — |

Three conclusions, all static:

1. **No segment and no span is near its limit.** The largest single segment
   anywhere is 72.88 MiB (adsp, which boots) against 256 MiB; the largest span
   is 134.57 MiB against 254 MiB; the largest `Used` is 134.61 MiB against
   4606 MiB. The c2 image sits at 50.69 / 123.64 / 123.68 MiB — between the
   booting bt family and the booting adsp image. A granularity or size limit in
   the window is therefore not what separates them.
2. **The window-granularity hypothesis is negated.** Silent c2 and alive
   bt-s4c-c differ by 11.47 MiB of `Used` and 0.22 MiB of largest segment, in
   the direction that makes c2 the *safer* of the two; and the smallest image in
   the set (c0/c1, `Used` 74.75 MiB) is silent while the largest (adsp,
   134.61 MiB) boots. Whatever kills the wifi images is not their size, not
   their span, and not the segment table.
3. **The pool channel loses its capacity form too.** The two copies of the image
   that coexist while the window is requested (DarwinBoot's `AllocatePool` at
   `:116` plus UniXNU's `AllocateZeroPool` copy, freed only at `:818`) are
   223.74 MiB for c2/z0/t2/mhi5d, 125.89 MiB for c0/c1 and 246.03 MiB for the
   booting adsp image. c1 dies with 258.11 MiB of the 384 MiB heap still free,
   while adsp boots with 137.97 MiB free — so even "the heap ran out" cannot be
   the mechanism in its plain form. What remains of §7.1 is only the
   non-capacity part: whether the arena run is still intact at the instant
   `AllocatePages` runs (`DarwinBoot.c:485`), which no static number can settle.

So the layout family is now excluded by arithmetic as well as by the t2 flight,
and the C-cell flight is the only thing that can still separate "the driver's
code and const data are in the kernel" from "something in the boot path is
sensitive to this kernel's content". If c2 boots, the killer was the `__TEXT`
placement; if c2 is silent, the next split is c3 (64 KiB truncated container).

## 3h. The UFS lease hypothesis (2026-11-16)

The earlier reading of the boot logs — "the first log line is a GDSC vote that
happens before UFS comes up, so UFS cannot be the cause" — was wrong, and the
reason is worth recording: the console is a ramoops ring buffer, not a stream.
`patches/xnu/0300-k60-usblog-ep0.patch` only calls `k60_usblog_init()` from
`osfmk/arm/arm_init.c` (a read-only probe); the CDC worker that drains the ring
to the host starts in `bsd/kern/bsd_init.c`:

```
if (result == KERN_SUCCESS) {
    ...
    k60_usblog_start();
}
```

So a line's position in the ring records the order it was *written*, not that it
ever reached the host, and `bsd_autoconf()` runs `kminit()` → pseudo inits →
`IOKitBSDInit()` → `native_pong_ui_services_start()` → `k60_usblog_start()`.
Anything that makes `IOKitBSDInit()` return non-`KERN_SUCCESS` skips the worker
entirely, which is exactly the observed shape: 0 bytes on the host while the ring
holds plenty.

### The lease

`patches/wifi/0004` inserts this into `hostBringUp()` in
`drivers/NativeUfs/PongUfsTransport.cpp`:

```c
lease.held = pong_smmu_lease_lock();
if (!lease.held) return transportFailure("Apps SMMU lease unavailable");
```

`pong_smmu_lease_lock()` returned `false` whenever `smmuLeaseLock` was still
`NULL`, and that lock was only allocated in `pong_rpmh_init()`, whose only caller
is `pong_wifi_start_optional()` (reached from `ArmDTPlatform::configure()` via
`patches/wifi/0005`). UFS starts earlier — baseline logs put UFS at :115 and
ArmDTPlatform at :147 — so on every wifi kernel the UFS lease was taken before
anybody had allocated the lock. The result was not contention, it was an
uninitialised variable: the lease could not be held on any boot, and UFS stopped
with `Apps SMMU lease unavailable` before the console worker existed.

That accounts for the whole table: every wifi image carries 0001 and 0004 and is
silent; the baseline and ADSP series do not carry 0004 and boot.

### The fix

`patches/wifi/0012` allocates the lock on first use:

```c
extern "C" bool pong_smmu_lease_lock(void)
{
    if (!smmuLeaseLock) smmuLeaseLock = IOLockAlloc();
    if (!smmuLeaseLock) return false;
    IOLockLock(smmuLeaseLock);
    return true;
}
```

`pong_rpmh_init()` keeps its allocation (harmless, idempotent), and the unlock
keeps its guard. `scripts/tests/test-pong-smmu-lease.py` pins the order: the
allocation must precede the null check, the function must stay unique, and the
patch must remain the last entry in `patches/wifi/series`.

**Prediction for c3.** `wifi-20261116c3` is the c2 recipe plus 0012, nothing
else. If the hypothesis holds, c3 reaches userland (K60DATA mounted and
SpringBoard at least 100 lines). If c3 is silent too, the lease *return value* was
not the blocker, and the next single change is to make 0004 degrade instead of
failing — dropping the `return transportFailure(...)` — which separates "the lease
returns false" from "UFS never reaches the lease at all".

### The c3 build (2026-11-16 01:34, not flown)

`wifi-20261116c3` is the c2 recipe plus 0012 and nothing else, so the pair is a
single-variable comparison on the same 117 MB shape:

| | c2 | c3 |
| --- | --- | --- |
| kernel | 117,305,344 B `24ebc11c` | 117,325,824 B `3c2991f0` |
| payload kernel | `92c0ca3a` | `ff51b89d` |
| boot.img | `dc7e4186` | `5a19e110` |
| wifi archive | `de3f48a5` | `9bb4fc6c` |
| series | 226 `d83fb189` | 226 `d83fb189` |
| args | `pong_wifi=0` | `pong_wifi=0` |

The 20,480 B difference is the lazy allocation itself. Segments are unchanged:
`__TEXT` 1,802,240, `__DATA_CONST` 12,124,160, `__DATA` 53,149,696 /
51,576,832, `__LINKEDIT` 6,684,672 / 6,668,344; `__DATA_CONST,__const`
11,919,062 @0x1b9000 still holds the container, and `_pong_wifi_firmware`
through `_pong_wifi_firmware_end` still spans 11,189,974 B. The manifest also
records `wifi_archive` and the kernel passes the `_pong_wifi_start_optional`
guard, which the first c3 attempt did not: that attempt exposed a merge
casualty — the merge at 02014e2 kept only the manifest fields of the wifi block
and dropped the definition and the guard, so the driver linked but the build
recorded nothing. Restored in 3207bd3.

## 4. T2 contingency: move the firmware blob out of `__TEXT` (built, flown, negated — kept as evidence)

Written on 2026-11-15 at the Lead's request so the fix would be ready the moment
T0 came back silent. It **was** built and flown after T0 was silent
(`wifi-20261116t2`, `usblog-20261115-161102`) and came back silent itself — that
is the flight which negated S1. This section is the record of the change and its
recipe, not a pending plan; the measured result is in `T2-PATCH.md` §5.0.

### 4.1 The change is one line

`scripts/build-k60-wifi-native.py:102` emits the assembly that carries the
11,189,974-byte PWF2 container into the kernel:

```python
asm.write_text('.section __TEXT,__const\n.p2align 12\n.globl _pong_wifi_firmware\n'
               '_pong_wifi_firmware:\n.incbin "'+str(pack)+'"\n'
               '.globl _pong_wifi_firmware_end\n_pong_wifi_firmware_end:\n')
```

Change the section name only — `.section __DATA,__const` (or
`__DATA,__data`) — and keep `.p2align 12` so the container stays 4 KiB
aligned. There is no kernel linker script to touch: Mach-O assigns a section
to a segment by the name the input object declares, and the wifi archive is
pulled in with `-Wl,-force_load` (`scripts/build-xnu-4k-baseline.sh:1153`
and `:1186`) which does not constrain layout.

The ready-to-apply diff, its validation, the t2 build recipe and the
pre-flight checks are in `docs/research/wifi/T2-PATCH.md`; this section keeps
the reasoning, that file keeps the executable form.

The C side needs no change at all. `PongWifiPlatform.cpp:35` declares
`extern const uint8_t pong_wifi_firmware[], pong_wifi_firmware_end[]` and
`fwGet()` (`:554-556`) only does pointer arithmetic inside that range
(`*data = pong_wifi_firmware + off`); it never writes. Moving the bytes to a
writable segment is harmless because nothing writes them.

### 4.2 The precedent is already in this tree and it boots

The 51 MB Metal blob takes exactly this route:
`scripts/gen-k60-metal-blob.py:109-119` emits `.data` + `.globl
_k60_metal_blob` + `.incbin`, and it lands in `__DATA,__data`. The image
built from it (`gpu-20261114t`) reaches SpringBoard. So a large read-only
blob in `__DATA` is a proven layout on this board, not an experiment.

### 4.3 The segment budget checks out

Measured with `mcopy` on the payload kernel (script
`E:/k60-work/scratch/prec.py`):

| segment / section | gpu-20261114t (boots) | wifi-20261116mhi5 (silent) |
|---|---|---|
| `__TEXT` vmsize | 0x1a4000 | 0xc64000 |
| `__TEXT,__const` | 0x86028 | **0xb38ed6** |
| `__DATA` vmsize / filesize | 0x3278000 / 0x3130000 | 0x32b0000 / 0x3130000 |
| `__DATA,__data` | 0x3110d08 | 0x31111f0 |

- Moving 11.19 MiB into `__DATA` takes its vmsize from 52.9 MiB to about
  64 MiB. DarwinBoot rejects a segment only above `WINDOW_SIZE` = 256 MiB
  (`DarwinBoot.c:168`), and the whole-image span only above 254 MiB
  (`:195-196`; mhi5's span is 123.6 MB), so both limits stay far away.
- The **file** does not grow: the same bytes simply live in a different
  segment, so the 117,305,344-byte total is unchanged. That matters because
  the loader reads the kernel through `ReadFile (Root, Request->KernelPath,
  SIZE_128MB, ...)` (`DarwinBoot.c:699`) — a 128 MiB hard ceiling that
  mhi5 already sits 10.7 MB under. Any T2 variant that *adds* bytes instead
  of relocating them would eat into that margin.
- `__DATA`'s vmsize exceeds its filesize by `__common` 0x95a18 plus
  `__bss` 0xe96220 (zero-fill, no file cost), which is why the segment can
  grow without the file growing.
- XNU maps segments by name in `arm_vm_init.c` (`:1415` RNX for
  `segTEXTB`, `:1432` RWNX for `segDATAB`), with no hard-coded size
  limit; the assertions at `:2306-2308` only check that adjacent segments
  stay contiguous, which a section move inside `__DATA` preserves.

### 4.4 What T2 would and would not prove

- If the T2 image boots, the killer is *residency of the blob in
  `__TEXT`* — the loader copying or mapping a 128 MiB image whose first
  read-only pages are 11 MB of opaque firmware — and not the firmware
  content or the wifi driver.
- If the T2 image is also silent, S1 is falsified and the remaining suspect
  is the loader/heap interaction (S2), which then needs the `NO WINDOW`
  diagnostic line rather than another placement guess.

### 4.5 Option B: read the firmware from the Data volume at runtime

Considered and deferred. `/private/var` lives on the Data volume, and the
metal plugin patch (`patches/xnu/0610-k60-metal-plugin-deploy.patch`) notes
that no host tool available here can write into it, which is why the Metal
blob went into the kernel instead. A Data-volume firmware would need a new
write path in the loader or the ramdisk — the "register a reserved region,
write it from the loader, rebuild the FD" work in `uefi-mondrian` that the
Lead scoped for T2 — and it costs a full FD rebuild per firmware change.
It stays the fallback if `__DATA` placement turns out to be insufficient.

## 5. Evidence index

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
- Post-T0 flights: `usblog-20261115-135859` (z0/T0, silent),
  `usblog-20261115-161102` (t2, silent),
  `usblog-20261115-140927` (bt-s4b-20261115b, alive),
  `usblog-20261115-163144` (bt-s4b-20261115c, silent),
  `usblog-20261115-162553` (bt-s4c-20261115c, alive).
- c1 build: `/mnt/e/k60-work/artifacts/wifi-20261116c1/build-manifest.json`
  (built 2026-11-15T23:10:57+08:00); payload-kernel byte diff against c0 with
  `cmp -l` on the two `mcopy` extracts; UUID literal test with `grep -c -a`.
- Pool/window analysis: `DARWINBOOT-POOL.md` (the three DarwinBoot memory
  nodes line by line, the window arithmetic against `board.toml:235` and the
  5120 MiB arena, and the one-flight discriminator).
- c2/c3 pair and the UFS lease: `patches/wifi/0012-drivers-PongWifi-lease-lock-lazy-init.patch`,
  `scripts/tests/test-pong-smmu-lease.py`, and
  `/mnt/e/k60-work/artifacts/wifi-20261116c3/build-manifest.json` (§3h).
- Static segment arithmetic for every flown image: `E:/k60-work/scratch/winmath3.py`
  (`mcopy` the payload kernel and its `.adt`, then apply `DarwinBoot.c:757-772`
  `Used`); the resulting table is §3g.
