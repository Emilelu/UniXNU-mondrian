# K60 m11a 120 Hz panel switch — implementation and pre-registered flight plan

Status: `120hz-5` built (line-counter frame measurement, first-GPU-frame switch, requested-vs-measured refresh split, brightness control gate); flight pending. Branch: `feat/120hz-panel`.

## Scope

This task makes the K60 panel itself enter its native 120 Hz timing group. It
does not claim that the GPU renders 120 frames per second: the software
framebuffer and the future GPU scanout are separate measurements. The first
question is only whether the m11a panel accepts timing@2 and whether the INTF
line-counter frame period is about 120 per second. `INTF_LINE_COUNT` (0xb0)
wraps once per panel frame; the tear-counter high 16 bits is a read-pointer
frame count and the plain frame counter only advances on DPU commits.

The prior software-only declaration is in
`patches/xnu/0506-k60-120hz-refresh.patch`: while a request is active it reports
the requested 120 Hz to TimingElements (published once at start), while the
panel driver separately logs the INTF1-measured rate. It never touches DSI
timing itself.
`drivers/PongAdreno/PongDsiPanel.cpp:116` already says the cadence correction
does not establish a 120 Hz display mode. This plan adds the missing panel-side
switch and accepts both the project gate `p120=1` and the official reference
spelling `vsync=120`; every image without either stays at the native 60 Hz
declaration. The one-time TimingElements publication reports the requested
120 Hz; the separate `K60 PANEL: INTF1 ...` line records what the panel
actually produced, and a failed switch is judged from that line.

## Data source (live FDT plus vendor dtsi)

The live K60 FDT node is `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`. Timing group 2
is 120 Hz:

- The vendor dtsi (`LowTension/android_kernel_xiaomi_sm8475`,
  `dsi-panel-m11a-42-02-0a-dsc-cmd.dtsi`) has eleven packets:
  `0x15 2f 00`, `0x15 8b 00`, `0x39 f0 55 aa 52 08 00`, `0x15 6f 03`,
  `0x15 c0 10`, `0x15 6f 31`, `0x15 df 20`, `0x39 f0 55 aa 52 08 02`,
  `0x15 cc 30`, `0x15 ce 01` (post_wait 10 ms), `0x15 cc 00`.
- The live FDT copy is only 98 bytes / ten packets: it omits the final
  `CC 00` and the `CE 01` 10 ms post-wait. That is a truncated copy, not
  the full vendor switch; the first flight sent only ten packets and left
  the panel at an unverified rate.
- 60 Hz differs only in `2f 02`, `8b 00`, `df 21`; 90 Hz differs only in
  `2f 01`, `8b 10`, `df 20`.
- All three timing groups have the same clock rate (1,200,000,000), porch
  values (8/8/12 and 16/6/14), PHY timings
  (`00 27 0a 0a 1b 25 0a 0b 0b 0a 02 04 20 0f`), DSC 720x32 slices, and
  panel size 1440x3200. No PHY or PLL change belongs in this task.

The older `docs/plans/K60-120HZ-PLAN.md` and
`docs/state/STATE-2026-11-07.md:96-101` contain the sharp reference panel's
`0xC6 0x1244/0x1288` sequence and must not be used for m11a. The working
sequence is also recorded in `docs/plans/120HZ-PORT-PLAN.md`.

## Implementation

1. `drivers/PongAdreno/PongDsiPanel.cpp`: add the eleven-packet `kTiming120`
   table and `pong_panel_switch_120()`. The bring-up only records the request;
   the switch runs once at the first completed GPU frame (the zizhan `panelHz()`
   point), so the panel is already receiving UI frames. It sends each packet
   through the existing `dsi_dcs()` path, honours the per-packet post-wait
   (10 ms after `CE 01`), waits 300 ms, writes the INTF1 tear-check
   `vsync_count` from 100 to 50 when the inherited value is the known 60 Hz
   state, and measures the INTF1 line-counter wrap period before (200 ms) and
   after (500 ms). `pong_panel_sample()` takes a second observation
   (`after the UI frame`) once the real UI frame is presented.
2. `drivers/PongAdreno/PongDsiPanel.h`: expose the switch and its return
   values; document that the reported rate is the requested 120 Hz while a
   request is active, otherwise the INTF1 observation.
3. `patches/xnu/0506-k60-120hz-refresh.patch`: add
   `static TUNABLE(uint32_t, gK60Panel120, "p120", 0)`, declare
   `pong_panel_refresh_hz()`, and make `refreshHz()` return the requested
   120 Hz while the panel driver has an active request; otherwise use the
   measured INTF1 rate and fall back to `fb_hz`. The measured value is kept in
   the K60 PANEL log and never downgrades the one-time TimingElements value.
4. `scripts/check-image-args.py`: allow the documented `p120` and `vsync`
   additions.
5. `scripts/check-panel-timing.py`: static proof that the eleven packets, the
   p120/vsync gates, the first-frame switch, the requested-refresh accessor,
   the INTF vsync_count update, and the pre-/post-switch and post-first-frame
   INTF1 observations are present.
6. `scripts/check-120hz-log.py`: log-side judge for the pre-registered
   criteria (first-frame switch, eleven packets rc 0, before 55–65/s,
   after-UI TE 110–130/s, first frame, SpringBoard, sig=11, DCS failures,
   backlight conformance/control). Its selftest carries the healthy, 120hz-3
   failed, 12/s, missing-observation, missing-backlight, DCS-failure and
   no-panel shapes.

## Boot-argument budget

DarwinBoot accepts at most 607 bytes (`DARWIN_BOOT_LINE_LENGTH == 608`,
`DarwinBoot.c:681`). The board contract is 29 arguments/575 bytes.
`p120=1` adds 7 bytes (582); `vsync=120` adds 10 bytes (585).
`p120=1` plus `k60_backlight_control=1` is 606 bytes; `vsync=120` plus the same
backlight argument would be 609 bytes, so the two spellings are alternatives,
not additive. The image audit must print `image-arg-audit: OK` with the actual
count and byte length.

## Build records

`120hz-1` was built from branch `feat/120hz-panel` at HEAD `b27ca3d8`
(clean tree), with `K60_EIGHT_STEP_ITEMS=display` and `--kernel-arg p120=1`:

- `boot.img` 201,887,744 B, SHA-256
  `ff44c7a8e225d18a423e0ff22c96bf2235fd360fe34ad26d0a6a568897fa0b42`
- `kernel_built` 105,521,152 B, SHA-256
  `5e39e26c042c257aa5e14b00444876543f7323b6c650e3506032a58124ed27bc`
- manifest `E:/k60-work/artifacts/120hz-1/build-manifest.json`;
  `kernel_args_requested=["p120=1"]`; `image-arg-audit: OK (30 arguments, 582 bytes)`;
  `verify-boot-image: OK`.

`120hz-2` was built from branch `feat/120hz-panel` at HEAD `b786416d` (clean
tree), with `K60_EIGHT_STEP_ITEMS=display` and `--kernel-arg p120=1`:

- `boot.img` 201,887,744 B, SHA-256
  `bbe05b601762152a4ba16942e099f9bc818c00c8f970b0dab803c9ef87bf6cd7`
- `kernel_built` 105,521,152 B, SHA-256
  `a4547e223f3f65405a3db326e249e445de3de4894bb5a9cd839b8ddc7fcd3c8a`
- manifest `E:/k60-work/artifacts/120hz-2/build-manifest.json`;
  `kernel_args_requested=["p120=1"]`; `image-arg-audit: OK (30 arguments, 582 bytes)`;
  `verify-boot-image: OK`; `check-panel-timing: ok`.

`120hz-3` was built from branch `feat/120hz-panel` at HEAD `acbf6b0a` (clean
tree), with `K60_EIGHT_STEP_ITEMS=display` and `--kernel-arg vsync=120`
(built_at `2026-11-18T00:04:38+08:00`):

- `boot.img` 201,887,744 B, SHA-256
  `7c6f69edf120b5c176b06003beda39740cb036183de6582bd7653451a91a6f40`
- `kernel_built` 105,525,248 B, SHA-256
  `10dfed8ae736aa45ab13ffdccf4eda3d75bc9ae692298916f6772d170d4d6a45`
- manifest `E:/k60-work/artifacts/120hz-3/build-manifest.json`;
  `kernel_args_requested=["vsync=120"]`; `image-arg-audit: OK (30 arguments, 585 bytes)`;
  `verify-boot-image: OK`; `check-panel-timing: ok`.

`120hz-4` was built from branch `feat/120hz-panel` at HEAD `58eed3fc` (clean
tree), with `K60_EIGHT_STEP_ITEMS=display` and
`--kernel-arg p120=1 --kernel-arg k60_backlight_control=1`
(built_at `2026-11-18T00:56:24+08:00`):

- `boot.img` 201,887,744 B, SHA-256
  `54784067b2a2449a1457760d08fa48f8cc7137f9e51cbc7b4367ce5457ea0c86`
- `kernel_built` 105,525,248 B, SHA-256
  `f0d54b8be5dde5a169b1576c7a6edb01e1aba544cf0be6e98f9efd996522a7a4`
- manifest `E:/k60-work/artifacts/120hz-4/build-manifest.json`;
  `kernel_args_requested=["p120=1","k60_backlight_control=1"]`;
  `image-arg-audit: OK (31 arguments, 606 bytes)`; `verify-boot-image: OK`;
  `check-panel-timing: ok`.

`120hz-5` was built from branch `feat/120hz-panel` at HEAD `569bafca` (clean
tree), with `K60_EIGHT_STEP_ITEMS=display` and
`--kernel-arg p120=1 --kernel-arg k60_backlight_control=1`
(built_at `2026-11-18T01:30:24+08:00`):

- `boot.img` 201,887,744 B, SHA-256
  `093150fbb0ad3826ecb42a244837d7cf35ad8c44cba4d6afd0b6b1a1cea83912`
- `kernel_built` 105,525,248 B, SHA-256
  `8344d340b3c292c10eec120e2257d81a058023cc6fdbf389f42f729f019eb319`
- manifest `E:/k60-work/artifacts/120hz-5/build-manifest.json`;
  `kernel_args_requested=["p120=1","k60_backlight_control=1"]`;
  `image-arg-audit: OK (31 arguments, 606 bytes)`; `verify-boot-image: OK`;
  `check-panel-timing: ok`.

## Pre-registered success criteria (write before the flight)

PASS requires all of the following in one capture, with the image SHA-256
matching the build manifest:

1. The image command line contains `p120=1` or `vsync=120`, contains every
   board argument unchanged, and is at most 607 bytes; `image-arg-audit`
   returns OK.
2. The log contains `K60 PANEL: 120 Hz switch at the first GPU frame`
   followed by `K60 PANEL: timing switch to 120 Hz: 11 packets, rc 0`.
3. The log contains a `K60 PANEL: INTF1 after the UI frame te .../s` line
   with the rate in the range 110–130 per second. That `te` value is computed
   from the `INTF_LINE_COUNT` (0xb0) wrap period: one wrap is one panel frame
   and the shortest interval between two wraps is the frame period, the method
   in the official `DisplayTimingProbe.cpp:45-70`. `INTF_TEAR_INT_COUNT_VAL`
   (0x298) high 16 bits is a read-pointer frame count and `INTF_FRAME_COUNT`
   (0xac) counts DPU command-FIFO commits; both are recorded as diagnostics but
   neither decides the rate. The before-switch line should be in the range
   55–65 per second. The earlier `after the switch` line is supporting
   evidence; the post-first-frame line is the decisive one. A switch with no
   line-counter evidence is INCONCLUSIVE, not PASS.
4. The log contains `K60 DISPLAY: first frame presented` at least once, at
   least 100 `SpringBoard` lines, and zero `sig=11` lines.
5. No `K60 PANEL: DCS ... failed` line appears after the switch begins, and
   the panel does not go black.
6. The same image contains `k60_backlight_control=1`; the log contains
   `K60 BACKLIGHT: published level ... conformance=1 control=1` and the user
   can move the brightness slider through both endpoints.

FAIL if any DCS packet fails, the panel black-screens, the first frame never
arrives, the measured rate stays near 60, or the image cannot be tied to the
built SHA-256.

## Flight procedure

1. Build with the display input/output trees:
   `K60_DEVICE_INPUT=/opt/k60/trees/display-device K60_OUT=/opt/k60/trees/display-out scripts/build-strict.sh 120hz-4 --kernel-arg p120=1 --kernel-arg k60_backlight_control=1 --fd /mnt/e/k60-work/artifacts/fd/battery-20261114h-cf4485712c29.fd`.
2. Verify `boot.img` with `scripts/verify-boot-image.py --manifest` and
   `scripts/check-image-args.py --image ... --board board.toml`.
3. Only `fastboot boot`; never `fastboot flash`. Collect a 300 s USB log and
   preserve `boot.json`/`capture.json`.
4. Judge with `scripts/check-panel-timing.py` (static) and
   `scripts/check-120hz-log.py <console.log>` (capture). Record the evidence
   directory, SHA-256, line numbers, and the actual TE/frame counts.

## Rollback

Nothing is written to the phone: the image is only booted. A normal reboot
returns to the previous image and the panel's native 60 Hz timing. No
persistent partition is touched.
