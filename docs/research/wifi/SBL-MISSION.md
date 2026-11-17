# SBL mission poll: cache AMSS after the direct BHIe push

Written 2026-11-18. Scope: why the direct candidate's remaining failure is the
host's cached execution environment, the single-variable successor that polls
`BHI_EXECENV` after `mhi_download_amss_image()`, and the prewritten acceptance
criteria for `wifi-20261118sbl-mission`. This is the evidence record for the
mission-poll candidate; c8 remains HOLD.

## 0. Conclusion first

| question | answer |
|---|---|
| What did the direct candidate prove? | The direct BHIe push works: the 2026-11-18 01:29 flight logged `amss bhie load ret=0 exec_env=1`, then the device reported `exec_env=2` (AMSS), `pm_state=4` (`MHI_PM_M0`) and `mhi_state=2` (`MHI_STATE_M0`). See `SBL-DIRECT.md` §6. |
| Why is WiFi still failing? | `mhi_sync_power_up` (`pm.c:1277-1295`) waits on `MHI_IN_MISSION_MODE(mhi_cntrl->ee)`, but the host cached `ee=1` (SBL). The only EE event consumed was `execenv=1`; no later EE event updated the cache even though the device had reached AMSS. |
| What changes in this candidate? | After the direct `mhi_download_amss_image()` returns 0, the same worker polls `mhi_get_exec_env` for up to 500 x 10 ms. On `MHI_EE_AMSS` or `MHI_EE_WFW` it assigns `mhi_cntrl->ee = mission` and calls `wake_up_all(&mhi_cntrl->state_event)`, so `mhi_sync_power_up` sees mission mode instead of a stale SBL value and wakes from its wait. |
| Is this the official path? | Yes. UniXNU-sheng `516a7804` `package/MhiBoot.c:117-119` has `MhiWaitMission`, which polls the execution environment until AMSS/WFW after the BHIe image. Stock Linux has no equivalent poll after `mhi_download_amss_image`; the cached EE is only refreshed by an EE event. |
| Is this proven on K60? | **No — built only, not flown.** The image is `hardware_tested: false` until the first flight. |

## 1. Why this is the next single variable

The direct candidate's console is complete:
`E:/k60-work/evidence/usblog-20261118-012938/console.log` (237,343 bytes,
3,591 lines, SHA256 `9fff4a26237a3b6e795263a0a241c4dd2ab6aa42a84adbdde6b28cdaa3609c05`).
It records:

- `:648` `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x8b9a74ae; pushing the AMSS image`.
- `:687` `Pong MHI: amss bhie load ret=0 exec_env=1` — the vector-table transfer completed.
- `:691` `Pong MHI: timeout after 20000 ms ee=1 pm_state=4 exec_env=2 mhi_state=2 MHISTATUS=0x201 MHICTRL=0x200`.
  The device is already in AMSS/M0; the host's `ee` cache is still 1/SBL.

`mhi_sync_power_up` is the waiter that turns that cache into a 20 s timeout.
The fix is intentionally confined to the value it waits on: no QMI, WMI, PCIe,
rail or DMA change is included in this candidate.

## 2. Source anchors

The patch lives in the build generator, not in a checked-in copy of the Linux
source. `E:/hackios/k60-wifi/scripts/build-k60-ath11k.py`:

- `:330`: declares `int i, j, amss_ret;`.
- `:355-366`: assigns `amss_ret = mhi_download_amss_image(mhi_cntrl);`; only
  when it is zero, runs the bounded `for (j = 0; j < 500; j++)` poll. On
  `MHI_EE_AMSS` or `MHI_EE_WFW` it assigns `mhi_cntrl->ee = mission`, calls
  `wake_up_all(&mhi_cntrl->state_event)` and logs
  `Pong MHI: exec_env=%d after AMSS download; cached ee updated`; it stops on
  `MHI_EE_MAX` and sleeps 10 ms between samples.
- `:240`: appends `bool pong_sbl_pushed;` to the pinned `linux/mhi.h` copy
  after `bool fbc_download;`.
- `:319-329`: the bounded 200 x 10 ms `BHI_EXECENV` poll, BHI_STATUS success
  gate and direct push that are unchanged from the direct candidate.
- `:435-443`: the `pm.c` SBL one-shot latch remains; a later EE event cannot
  download twice.
- `:274-286`: the `mhi_fw_load_bhie` status diagnostic remains available.

Generated source anchors from the mission archive:

| file | anchor |
|---|---|
| `mhi/boot.c` | direct block at :624-672; push log :647; `mhi_cntrl->ee = MHI_EE_SBL` :648; latch :649; `amss_ret = mhi_download_amss_image` :650; mission poll :651-662; mission log :656 |
| `mhi/pm.c` | guard :828; latch :834; fallback download :843 |
| `pinned/linux/mhi.h` | `bool pong_sbl_pushed;` at :445 |

The poll runs after `mhi_ready_state_transition` has left `pm_state=MHI_PM_POR`
and before `mhi_sync_power_up` has changed it, so the register window is the
same one that just completed the BHIe transfer. No new MMIO lifetime is
introduced. `mhi_sync_power_up` is already sleeping in
`wait_event_timeout(state_event, ...)`; writing the cached EE without a wake
would still end in the 20 s timeout, so the `wake_up_all` is part of the same
single-variable fix.

## 3. Candidate identity

| field | value |
|---|---|
| tag | `wifi-20261118sbl-mission` |
| built_at | TBD |
| branch / head | `fix/wifi-mission-poll` / TBD |
| `boot.img` | TBD |
| kernel | TBD |
| payload kernel | TBD |
| WiFi archive | TBD |
| ath11k archive | TBD |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-mission/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=1 k60_wifi_rsc=2` |

This candidate is a single-variable test: stock six WLAN rails, `amss20.bin`,
`k60_wifi_rsc=2`, no MHI pre-load, no IPA rail, no c8 raw-register dump. The
earlier queue image `wifi-20261118sbl-gated` must not be re-flown; its first
flight is recorded in `SBL-QUEUE.md` §6. The direct image
`wifi-20261118sbl-direct` was flown once and its result is in `SBL-DIRECT.md`
§6.

## 4. Prewritten flight criteria

The image is only valid with a serial console captured before `fastboot boot`.

### Success — L1

- The device reaches SpringBoard (`Pong UI: ... entered SpringBoard`).
- The direct push line `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x...; pushing the AMSS image`
  appears with BHI_STATUS top bits 2.
- `Pong MHI: amss download begin entries=...` and `Pong MHI: amss bhie load ret=0 exec_env=1`
  appear.
- The new line `Pong MHI: exec_env=2 after AMSS download; cached ee updated`
  appears (or `exec_env=4` for WFW), with no matching `Pong MHI: timeout after 20000 ms`.
- `ath11k: chip_id 0x12 ...` and `fw_version ...` appear, with no
  `ath11k: failed to power up mhi: -110`.

### Failure / stop

- No `cached ee updated` line and a `Pong MHI: timeout after 20000 ms` with
  `ee=1`: the poll did not see AMSS/WFW in 5 s; stop and inspect the
  `exec_env` samples.
- `amss bhie load ret` non-zero: BHIe failed before the mission poll; stop.
- More than one `amss download begin`: the latch is not effective; stop.
- Any panic, cache-policy failure, duplicate download, or missing console: stop
  and follow the early-boot path. `Pong MHI: irq entered` is shim polling,
  not MSI proof.

## 5. What this candidate does not claim

It does not claim WiFi works: QMI, WMI, 102 channels, `en0`, scan, WPA2, DHCP
and HTTPS remain after MHI. It does not replace c8's audit status: c8 is still
HOLD and must not be built, booted or merged.
