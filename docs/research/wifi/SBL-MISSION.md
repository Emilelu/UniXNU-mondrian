# SBL mission poll: cache AMSS after the direct BHIe push

Written 2026-11-18. Scope: why the direct candidate's remaining failure is the
host's cached execution environment, the successor that polls `BHI_EXECENV`
after `mhi_download_amss_image()` and then creates the MHI devices for the
AMSS channels, and the prewritten acceptance criteria for
`wifi-20261118sbl-mission4`. This is the evidence record for the mission-poll
candidate; c8 remains HOLD.

## 0. Conclusion first

| question | answer |
|---|---|
| What did the direct candidate prove? | The direct BHIe push works: the 2026-11-18 01:29 flight logged `amss bhie load ret=0 exec_env=1`, then the device reported `exec_env=2` (AMSS), `pm_state=4` (`MHI_PM_M0`) and `mhi_state=2` (`MHI_STATE_M0`). See `SBL-DIRECT.md` §6. |
| Why is WiFi still failing? | `mhi_sync_power_up` (`pm.c:1277-1295`) waits on `MHI_IN_MISSION_MODE(mhi_cntrl->ee)`, but the host cached `ee=1` (SBL). The only EE event consumed was `execenv=1`; no later EE event updated the cache even though the device had reached AMSS. |
| What changes in this candidate? | After the direct `mhi_download_amss_image()` returns 0, the same worker polls `mhi_get_exec_env` for up to 2500 x 10 ms. On `MHI_EE_AMSS` or `MHI_EE_WFW` it assigns `mhi_cntrl->ee = mission`, calls `mhi_create_devices(mhi_cntrl)` so the IPCR channels (`ee_mask = 0x4`, AMSS-only) are created, and calls `wake_up_all(&mhi_cntrl->state_event)`, so `mhi_sync_power_up` sees mission mode instead of a stale SBL value and wakes from its wait. |
| Is this the official path? | Yes. UniXNU-sheng `516a7804` `package/MhiBoot.c:117-119` has `MhiWaitMission`, which polls the execution environment until AMSS/WFW after the BHIe image. Stock Linux has no equivalent poll after `mhi_download_amss_image`; the cached EE is only refreshed by an EE event. |
| Is this proven on K60? | **No — built only, not flown.** The image is `hardware_tested: false` until the first flight. |

## 1. Why this is the next single variable

The direct candidate's console is complete:
`E:/k60-work/evidence/usblog-20261118-012938/console.log` (237,343 bytes,
3,591 lines, SHA256 `9fff4a26237a3b6e795263a0a241c4dd2ab6aa42a84adbdde6b28cdaa3609c05`).
It records:

- `:648` `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x8b9a74ae; pushing the AMSS image`.
- `:685` `Pong MHI: bhie tx_status=0x2 seq=0x2 expected=0x24e1b3ae ret=19369` — the remaining-jiffy count shows the BHIe wait returned early; most of the 20 s was spent without a mission poll, not in the transfer.
- `:687` `Pong MHI: amss bhie load ret=0 exec_env=1` — the vector-table transfer completed.
- `:691` `Pong MHI: timeout after 20000 ms ee=1 pm_state=4 exec_env=2 mhi_state=2 MHISTATUS=0x201 MHICTRL=0x200`.
  The device is already in AMSS/M0; the host's `ee` cache is still 1/SBL.

Because the direct console exposes `exec_env=2` only in the 20 s timeout line,
the earlier 5 s mission poll was too short to rely on. The mission3 candidate
polls for 25 s, but that poll starts only after `mhi_download_amss_image()`
returns; `mhi_sync_power_up` still gives up after its own fixed 20 s wait. The
mission4 candidate therefore raises `mhi_ctrl->ready_timeout_ms` to 60 s in
`ath11k_mhi_start` (generated `ath11k/mhi.c:450`) while keeping the 25 s poll.
This lets the sync waiter stay alive long enough for the poll to cache AMSS.

The path is reachable on this board: the direct flight logged
`Pong MHI: serial=0x22d0a7f3 ee=0 fbc=1 fw_sz=0` at `:632`, so
`mhi_async_power_up` saw PBL and queued `DEV_ST_TRANSITION_PBL`; the PBL case
calls `mhi_fw_load_handler`, which calls `mhi_ready_state_transition` at
generated `mhi/boot.c:618` and then enters the direct block at `:624`.

`mhi_sync_power_up` is the waiter that turns a stale cache into the final
`-ETIMEDOUT`; the fix is intentionally confined to that wait plus the existing
mission poll. No QMI, WMI, PCIe, rail or DMA change is included.

## 2. Source anchors

The patch lives in the build generator, not in a checked-in copy of the Linux
source. `E:/hackios/k60-wifi/scripts/build-k60-ath11k.py`:

- `:331`: declares `int i, j, amss_ret;`.
- `:356-370`: assigns `amss_ret = mhi_download_amss_image(mhi_cntrl);`; only
  when it is zero, runs the bounded `for (j = 0; j < 2500; j++)` poll. On
  `MHI_EE_AMSS` or `MHI_EE_WFW` it assigns `mhi_cntrl->ee = mission`, calls
  `mhi_create_devices(mhi_cntrl)` at `:362` so the AMSS-only IPCR channels
  (`ee_mask = 0x4`) get MHI device objects, calls
  `wake_up_all(&mhi_cntrl->state_event)` and logs
  `Pong MHI: exec_env=%d after AMSS download; cached ee updated`; it stops on
  `MHI_EE_MAX` and sleeps 10 ms between samples.
- `:236-241`: appends `bool pong_sbl_pushed;` to the pinned `linux/mhi.h` copy
  after `bool fbc_download;`.
- `:330-379`: the bounded 200 x 10 ms `BHI_EXECENV` poll, BHI_STATUS success
  gate and direct push that are unchanged from the direct candidate.
- `:448-459`: the `pm.c` SBL one-shot latch remains; a later EE event cannot
  download twice.
- `:275-287`: the `mhi_fw_load_bhie` status diagnostic remains available.
- `:158-163`: the generated `ath11k/mhi.c` gets
  `ab_pci->mhi_ctrl->ready_timeout_ms = 60000;`; generated anchor
  `ath11k/mhi.c:450`.

Generated source anchors from the mission archive:

| file | anchor |
|---|---|
| `mhi/boot.c` | direct block at :624-674; ready transition call :618; push log :647; `mhi_cntrl->ee = MHI_EE_SBL` :648; latch :649; `amss_ret = mhi_download_amss_image` :650; mission poll :651-664; `mhi_cntrl->ee = mission` :655; `mhi_create_devices(mhi_cntrl)` :656; wake :657; mission log :658 |
| `mhi/pm.c` | guard :828; latch :834; fallback download :843 |
| `pinned/linux/mhi.h` | `bool pong_sbl_pushed;` at :445 |
| `ath11k/mhi.c` | `ready_timeout_ms = 60000` at :450 |

The poll runs after `mhi_ready_state_transition` has left `pm_state=MHI_PM_POR`
and before `mhi_sync_power_up` has changed it, so the register window is the
same one that just completed the BHIe transfer. No new MMIO lifetime is
introduced. `mhi_sync_power_up` is already sleeping in
`wait_event_timeout(state_event, ...)`; writing the cached EE without a wake
would still end in the 20 s timeout, so the `wake_up_all` is part of the same
fix. Once the cached EE names AMSS, the mission block's `mhi_create_devices`
must also run for the IPCR channels, because `nw_qrtr_mhi` calls
`mhi_prepare_for_transfer` as soon as the worker probes.

State-worker safety: the `mhi_create_devices` call runs inside
`mhi_fw_load_handler`, which is executed by `mhi_pm_st_worker`; the MHI event
tasklet can still run `mhi_pm_m0_transition`
(`E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/bus/mhi/host/main.c:861-862`)
and `mhi_send_cmd` rings the command doorbell itself (`main.c:1298-1303`), so
the synchronous `device_add` -> `nw_qrtr_mhi` probe cannot deadlock on M0 or on
a skipped command ring. The direct console shows only the SBL EE event (`:668`);
no later mission-mode EE event is present, so the stock mission transition does
not destroy and recreate the IPCR devices on this path.

## 3. Candidate identity

| field | value |
|---|---|
| tag | `wifi-20261118sbl-mission4` |
| built_at | 2026-11-18T03:41:57+08:00 |
| branch / head | `fix/wifi-mission-timeout` / `91c21c7cc71de684dc0b98cbd6784afdb9d5f5f3` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-mission4/boot.img`, 201,887,744 B, SHA256 `7646f5caf1b6fd03628587df2cdc915a24d8aca7115816af379858d9e6ac4a26` |
| kernel | `1ee83183537da2488267e98031f9ef41fb94baba24a3507d81ead5ef7023f4b3` |
| payload kernel | `e308664056ce2cb167a2c385ff6e3af7610ec36bbb5504a31724629b0e986987` |
| WiFi archive | `abe04821139df9b184df82bdd04f355e9374615807ca5e62629846ea867563a7` |
| ath11k archive | `a3793b0c3f587b20d148f04938436b96aaa18ccc41f78c087d77cdd487f2b120` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-mission4/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=1 k60_wifi_rsc=2` |

This candidate is the mission-poll successor plus the `mhi_create_devices`
call and the 60 s `ready_timeout_ms` wait: stock six WLAN rails, `amss20.bin`, `k60_wifi_rsc=2`, no MHI pre-load,
no IPA rail, no c8 raw-register dump. The earlier queue image
`wifi-20261118sbl-gated` must not be re-flown; its first flight is recorded in
`SBL-QUEUE.md` §6. The direct image `wifi-20261118sbl-direct` was flown once and
its result is in `SBL-DIRECT.md` §6. The pre-device-creation mission image
`wifi-20261118sbl-mission` was built but never flown and is superseded.

Offline checks performed:
- `python3 -m py_compile scripts/build-k60-ath11k.py` — pass.
- `python3 scripts/tests/test-wifi-sbl-mission.py` — all 29 source/artifact checks,
  0 failures.
- WSL `python3 scripts/verify-boot-image.py --manifest /mnt/e/...` — OK.
- WSL `python3 scripts/check-image-args.py --image /mnt/e/...` — OK (31
  arguments / 602 bytes).
- `boot.json` records `hardware_tested: false`; this image has not been flown.
- `python3 /mnt/e/k60-work/scratch/judge-sbl-mission2.py` — positive synthetic mission4 log passes 9/9; negative log with `timeout after 60000 ms` and no cached-ee line fails/stops as designed.

## 4. Prewritten flight criteria

The image is only valid with a serial console captured before `fastboot boot`.

### Success — L1

- The device reaches SpringBoard (`Pong UI: ... entered SpringBoard`).
- The direct push line `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x...; pushing the AMSS image`
  appears with BHI_STATUS top bits 2.
- `Pong MHI: amss download begin entries=...` and `Pong MHI: amss bhie load ret=0 exec_env=1`
  appear.
- The new line `Pong MHI: exec_env=2 after AMSS download; cached ee updated`
  appears (or `exec_env=4` for WFW), with no matching `Pong MHI: timeout after 60000 ms`.
- No `qrtr: cannot start the IPCR channels`; the two IPCR MHI devices exist after
  `mhi_create_devices`.
- `ath11k: chip_id 0x12 ...` and `fw_version ...` appear, with no
  `ath11k: failed to power up mhi: -110`.

### Failure / stop

- No `cached ee updated` line and a `Pong MHI: timeout after 60000 ms` with
  `ee=1`: the poll did not see AMSS/WFW before the 60 s ready wait expired; stop
  and inspect the `exec_env` samples.
- `amss bhie load ret` non-zero: BHIe failed before the mission poll; stop.
- More than one `amss download begin`: the latch is not effective; stop.
- Any panic, cache-policy failure, duplicate download, or missing console: stop
  and follow the early-boot path. `Pong MHI: irq entered` is shim polling,
  not MSI proof.

## 5. What this candidate does not claim

It does not claim WiFi works: QMI, WMI, 102 channels, `en0`, scan, WPA2, DHCP
and HTTPS remain after MHI. It does not replace c8's audit status: c8 is still
HOLD and must not be built, booted or merged.
