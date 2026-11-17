# K60 m11a 120 Hz panel switch — implementation and pre-registered flight plan

Status: `120hz-3` built (vendor 11-packet sequence, official `vsync=120` alias, measured refresh report); device flight pending. Branch: `feat/120hz-panel`.

## Scope

This task makes the K60 panel itself enter its native 120 Hz timing group. It
does not claim that the GPU renders 120 frames per second: the software
framebuffer and the future GPU scanout are separate measurements. The first
question is only whether the m11a panel accepts timing@2 and whether the INTF
TE counter and frame counter advance at about 120 per second.

The prior software-only declaration is in
`patches/xnu/0506-k60-120hz-refresh.patch`: it now reports the rate the panel
driver actually measured from INTF1, but it never touches DSI timing itself.
`drivers/PongAdreno/PongDsiPanel.cpp:116` already says the cadence correction
does not establish a 120 Hz display mode. This plan adds the missing panel-side
switch and accepts both the project gate `p120=1` and the official reference
spelling `vsync=120`; every image without either stays at the native 60 Hz
declaration, and a failed switch reports the observed 60 Hz rather than the
request.

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
   table and `pong_panel_switch_120()`. It runs once, after the existing
   `0x11/0x29/0x51` bring-up, only when boot argument `p120=1` or `vsync=120`. It sends
   each packet through the existing `dsi_dcs()` path, honours the per-packet
   post-wait (10 ms after `CE 01`), waits 300 ms, and measures INTF1 frame/TE
   counters before (200 ms) and after (500 ms). The first-frame patch also
   calls `pong_panel_sample()`, which takes a second INTF1 observation
   (`after the UI frame`) once the real UI frame is presented.
2. `drivers/PongAdreno/PongDsiPanel.h`: expose the switch and its return
   values.
3. `patches/xnu/0506-k60-120hz-refresh.patch`: add
   `static TUNABLE(uint32_t, gK60Panel120, "p120", 0)`, declare
   `pong_panel_refresh_hz()`, and make `refreshHz()` return the measured INTF1
   rate when the panel is native (falling back to `fb_hz` when no measurement
   exists). A request alone never reports 120.
4. `scripts/check-image-args.py`: allow the documented `p120` and `vsync`
   additions.
5. `scripts/check-panel-timing.py`: static proof that the eleven packets, the
   p120/vsync gates, the measured-refresh accessor, and the pre-/post-switch
   and post-first-frame INTF1 observations are present.

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

## Pre-registered success criteria (write before the flight)

PASS requires all of the following in one capture, with the image SHA-256
matching the build manifest:

1. The image command line contains `p120=1` or `vsync=120`, contains every
   board argument unchanged, and is at most 607 bytes; `image-arg-audit`
   returns OK.
2. The log contains `K60 PANEL: timing switch to 120 Hz: 11 packets, rc 0`.
3. The log contains a `K60 PANEL: INTF1 after the UI frame te .../s` line
   with TE and frame rates in the range 110–130 per second. The before-switch
   line should be in the range 55–65 per second. The earlier `after the
   switch` line is supporting evidence; the post-first-frame line is the
   decisive one. A switch with no TE/rate evidence is INCONCLUSIVE, not PASS.
4. The log contains `K60 DISPLAY: first frame presented` at least once, at
   least 100 `SpringBoard` lines, and zero `sig=11` lines.
5. No `K60 PANEL: DCS ... failed` line appears after the switch begins, and
   the panel does not go black.

FAIL if any DCS packet fails, the panel black-screens, the first frame never
arrives, the measured rate stays near 60, or the image cannot be tied to the
built SHA-256.

## Flight procedure

1. Build with the display input/output trees:
   `K60_DEVICE_INPUT=/opt/k60/trees/display-device K60_OUT=/opt/k60/trees/display-out scripts/build-strict.sh 120hz-3 --kernel-arg vsync=120 --fd /mnt/e/k60-work/artifacts/fd/battery-20261114h-cf4485712c29.fd`.
2. Verify `boot.img` with `scripts/verify-boot-image.py --manifest` and
   `scripts/check-image-args.py --image ... --board board.toml`.
3. Only `fastboot boot`; never `fastboot flash`. Collect a 300 s USB log and
   preserve `boot.json`/`capture.json`.
4. Judge with `scripts/check-panel-timing.py` and grep the captured
   `console.log` for the four log lines above. Record the evidence directory,
   SHA-256, line numbers, and the actual TE/frame counts.

## Rollback

Nothing is written to the phone: the image is only booted. A normal reboot
returns to the previous image and the panel's native 60 Hz timing. No
persistent partition is touched.
