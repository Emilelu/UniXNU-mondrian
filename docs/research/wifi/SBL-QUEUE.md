# SBL queue: what the official MHI boot path does that stock Linux does not

Written 2026-11-17. Scope: why the K60 MHI host never sees an EE event after
READY, what the official UniXNU MhiBoot does instead, and the prewritten
acceptance criteria for the successor candidate built from that reading. This
note is the evidence record for the gated SBL-queue candidate; c8 remains HOLD.

## 0. Conclusion first

| question | answer |
|---|---|
| What does c7 prove? | MHI reaches READY and M0, but `ee=0`, `pm_state=2`, `exec_env=1` (SBL); the event-ring read pointer never advances. The host waits for an EE event that never arrives. `E:/k60-work/evidence/usblog-20261116-122546/console.log:632` |
| What does the official path do? | `MhiBoot.c:91-98` requires `BHI_STATUS >> 30 == 2`; `MhiBoot.c:104-107` polls `BHI_EXECENV` and calls `start_image()` (BHIe write of `TXVECADDR/TXVECSIZE/TXVECDB`) when it reads `MHI_EE_SBL`. It never waits for an EE event packet. |
| What is the K60 change? | Build-time host patch: after `mhi_ready_state_transition`, poll `mhi_get_exec_env` for up to 200 x 10 ms while `MHI_REG_ACCESS_VALID(pm_state)`; on SBL read `BHI_STATUS` and queue the stock `DEV_ST_TRANSITION_SBL` work item **only when `BHI_STATUS >> 30 == 2` (success)**, stop on `== 3` (error), and keep waiting otherwise. A `pong_sbl_pushed` latch makes the existing worker's `mhi_create_devices` + `mhi_download_amss_image` run once. |
| Why not call `mhi_download_amss_image` from boot.c? | c8's direct call was held because it assumed a powered MMIO/DMA lease and could duplicate an already queued SBL transition. Queueing the stock transition keeps the worker, locks and `fbc_image` ownership in one place; the only new register reads use the existing MHI helpers while `pm_state` says access is valid. |
| Is this proven on K60? | **No.** The image exists and the offline gates pass; it has not flown. `boot.json` records `hardware_tested: false`. |

## 1. The source anchors

The patch lives in the build generator, not in a checked-in copy of the Linux
source. `scripts/build-k60-ath11k.py`:

- `:231-240`: pins `include/linux/mhi.h` and appends `bool pong_sbl_pushed;`
  after `bool fbc_download;`. The source header stays untouched.
- `:307-351`: inserts the bounded poll before the stock
  `Wait for device to enter SBL or Mission mode` line. On SBL it reads `BHI_STATUS`: `BHI_STATUS >> 30 == 3` stops with an error log;
  any value other than `2` (success) waits and retries; `2` logs
  `Pong MHI: device is in SBL without an EE event, BHI_STATUS=%#x; queueing the SBL transition`
  and calls `mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);`.
  It does not call the download directly and does not dump raw registers.
- `:409-429`: adds the one-shot guard to the existing
  `case DEV_ST_TRANSITION_SBL` in `pm.c`; the first worker pass sets
  `pong_sbl_pushed = true` when `fbc_download` is true.
- `:340-367`: retains the c8 AMSS vector logging inside
  `mhi_download_amss_image`, so a successful BHIe handoff is visible as
  `amss download begin entries=...` and `amss bhie load ret=... exec_env=...`.

Generated source identities (copied from the build):

| file | anchor |
|---|---|
| `mhi/boot.c` | `if (mhi_cntrl->fbc_download && !mhi_cntrl->pong_sbl_pushed) {` at :622; BHI status gate at :635-642; queue at :646 |
| `mhi/pm.c` | `if (mhi_cntrl->pong_sbl_pushed) {` at :828; latch at :834 |
| `pinned/linux/mhi.h` | `bool pong_sbl_pushed;` at :445 |

## 2. Why this is the official path, not a local invention

The official page `https://unixnu.com/zh/porting/network` describes the same
handshake from the other side: complete platform interrupts/DMA first, then
confirm the chip and firmware, then start `nw_wifi_start` and inspect
`nw_wifi_stats` / `nw_wifi_where` when it stalls. The source it names is
UniXNU-sheng `516a7804` `package/MhiBoot.c`; its `MhiWaitSbl` reads
`BHI_EXECENV` directly and writes the BHIe vector table on SBL. Stock Linux
`mhi_fw_load_handler` instead returns after READY and waits for an EE event in
`mhi_sync_power_up`. The difference is in the handshake, not in the firmware
or the board.

Zizhan is the working same-SoC control: its 2026-11-03 g274 evidence shows
`PongWifi[6]: ath11k: wcn6855 hw2.1`, `Wait for device to enter SBL or Mission
mode`, then `ath11k: chip_id 0x12 ... soc_id 0x400c1211` and
`fw_version 0x200c0039`. It uses the same `amss20.bin` rewrite and the same
stock MHI host; that proves HW2.1 + amss20 can reach MISSION on this chip. It
does not prove the K60's c7 EE-event path works, which is exactly the variable
this candidate isolates.

## 3. Candidate identity

| field | value |
|---|---|
| tag | `wifi-20261117sbl-queue` |
| branch / head | `fix/wifi-bhi-execenv-wifi` / `e6b71ba889e0bdbedf86b3c6b9b622693f5f91f1` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261117sbl-queue/boot.img`, 201,887,744 B, SHA256 `ebdb312972685189aa2417ec5ca0e0d75e604ddb71c01683a344837fcbf27232` |
| kernel | `d737c568e18ebfbe2a197581ead795607d5aa431af383ccb3b851c270de8c6e6` |
| payload kernel | `d825506da800642f6e1c79635a186cbdc9413f76ecff7b2bee64b34f65d12995` |
| WiFi archive | `019d8304528060826a2c02180fcd9ce1d6463c16e56e0cb59e133ee131333430` |
| manifest | `E:/k60-work/artifacts/wifi-20261117sbl-queue/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=1 k60_wifi_rsc=2` |

Offline checks performed:

- `python3 -m py_compile scripts/build-k60-ath11k.py` — pass.
- `python3 scripts/tests/test-wifi-sbl-queue.py` — 12 source/artifact checks,
  0 failures.
- `verify-boot-image.py --manifest ...` — OK.
- `check-image-args.py --image ...` — OK (31 arguments, 602 bytes).
- `build-strict`: eight-step 36 checks, series 227, WiFi driver present in the
  kernel, boot image manifest recorded; `hardware_tested: false`.

The built kernel contains the new log string
`device is in SBL without an EE event` (one occurrence in
`kernel.macho`), so the image is not an unpatched rebuild.

## 4. Prewritten flight criteria

This candidate is a single-variable test: stock six WLAN rails, `amss20.bin`,
`k60_wifi_rsc=2`, no MHI pre-load, no IPA rail. A valid flight must capture the
serial console before `fastboot boot` and must not be attempted without an
operator present.

### Success — L1

- The device reaches SpringBoard (`Pong UI: ... entered SpringBoard`).
- No line matching c7's exact `Pong MHI: timeout after 20000 ms ee=0 ...`.
- New line `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x80000000; queueing the SBL transition` (the top two bits must decode to 2).
- Followed by `Pong MHI: amss download begin entries=...` and
  `Pong MHI: amss bhie load ret=0 exec_env=...`.
- Then the MHI/QMI advance becomes visible: `ath11k: chip_id 0x12 ...`,
  `fw_version`, and no `ath11k: failed to power up mhi: -110`.

### Failure / stop

- Same c7 timeout and **no** `device is in SBL` line: the poll never read SBL
  within 2 s (or register access was invalid); stop, do not fly twice.
- `device is in SBL` present but same timeout and no `amss download begin`:
  the queue/latch did not execute; stop and inspect the worker order.
- `BHI_STATUS=... not successful` repeats for the whole poll and no queue line:
  the device never reported BHI success; stop and inspect BHI_STATUS/error code.
- `amss bhie load ret` is non-zero: BHIe handoff failed; stop.
- More than one `amss download begin` line: the latch is not effective; stop.
- Any panic, cache-policy failure, or missing console: stop and follow the
  early-boot path. `Pong MHI: irq entered` is shim polling, not MSI proof;
  do not read it as a successful interrupt.

## 5. What this candidate does not claim

It does not claim WiFi works: QMI, WMI, 102 channels, `en0`, scan, WPA2, DHCP
and HTTPS remain after MHI. It also does not replace c8's audit status: c8 is
still HOLD and must not be built, booted or merged. If this candidate fails with
the same timeout, the next step is the BHI_STATUS / event-ring diagnostic track
from the official `native_wifi_mhi[16]` interface, not another blind flight.
