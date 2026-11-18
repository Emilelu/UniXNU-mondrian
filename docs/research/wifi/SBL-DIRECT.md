# SBL direct push: the official MHI image start without an EE event

Written 2026-11-18. Scope: why the queue candidate failed its first flight, why
the successor calls `mhi_download_amss_image()` in the same READY worker pass,
and the prewritten acceptance criteria for `wifi-20261118sbl-direct`. This is
the evidence record for the direct candidate; c8 remains HOLD.

## 0. Conclusion first

| question | answer |
|---|---|
| What did the queue candidate prove? | The device really sits in SBL with `exec_env=1` and reports BHI_STATUS success (`0x8b9a74ae`), so the official BHI_EXECENV read is meaningful. But the queued `DEV_ST_TRANSITION_SBL` work item ran only after `mhi_sync_power_up` timed out and `mhi_power_down` had invalidated the register window; `mhi_fw_load_bhie` returned `-EIO` (`amss bhie load ret=-5`). |
| What changes in this candidate? | After the BHI_STATUS success gate, the boot path sets `ee = MHI_EE_SBL`, latches `pong_sbl_pushed = true`, and calls `mhi_download_amss_image()` **directly in the same `mhi_fw_load_handler` worker pass**, where READY/POR still makes register access valid and `fbc_image` is already owned. The 200 x 10 ms bounded poll and the one-shot latch stay. |
| Why is this still the official path? | UniXNU-sheng `516a7804` `package/MhiBoot.c:104-107` polls `BHI_EXECENV` and writes the BHIe vector table (`start_image()`, `:65-75`) when it reads `MHI_EE_SBL`; it never waits for an EE event packet. Stock Linux instead returns after READY and `mhi_sync_power_up` waits the cached EE. This candidate mirrors the official polling point and keeps the stock MHI vector-table transfer. |
| Is this proven on K60? | **Partly — the direct BHIe push works.** The 2026-11-18 01:29 flight logged `amss bhie load ret=0 exec_env=1`, then the device reported `exec_env=2` (AMSS) and M0. WiFi still fails because the host keeps cached `ee=1` (SBL) and `mhi_sync_power_up` times out; see §6. |

## 1. Why the queue form was replaced

The queue candidate `wifi-20261118sbl-gated` was flown once at 2026-11-18
00:55. The complete console `E:/k60-work/evidence/usblog-20261118-005525/console.log`
(143,253 bytes, 2,079 lines) shows:

- `:631` `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x8b9a74ae; queueing the SBL transition`
  (top two bits = 2, success gate passed).
- `:635` `Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200`.
- `:637` AMSS vector table, `:645` `amss download begin entries=12`, then
  `:651` `amss bhie load ret=-5 exec_env=1` and `:653` `MHI did not load AMSS, ret:-5`.
- `:655` `ath11k: failed to power up mhi: -110`; SpringBoard still boots at
  `:1380`.

`mhi_sync_power_up` (`pm.c:1277-1295`) times out and calls `mhi_power_down`
(`pm.c:1212-1259`), which sets `pm_state = MHI_PM_LD_ERR_FATAL_DETECT` and
flushes the state worker. The queued SBL item then executes during that flush;
`mhi_fw_load_bhie` (`boot.c:210-223`) returns `-EIO` immediately because
`MHI_REG_ACCESS_VALID(pm_state)` is false. The direct call removes the
worker-queue delay without changing the device-side handshake.

## 2. Source anchors

The patch lives in the build generator, not in a checked-in copy of the Linux
source. The line numbers in this section are as of the direct build head
`0782eddc`; the current head has the same direct block at `:330-379`.
`E:/hackios/k60-wifi/scripts/build-k60-ath11k.py`:

- `:319-364`: replaces the passive wait with a bounded `for (i = 0; i < 200; i++)`
  poll while `MHI_REG_ACCESS_VALID(pm_state)`. It reads `mhi_get_exec_env`;
  on `MHI_EE_SBL` it reads `BHI_STATUS`, stops on `BHI_STATUS_ERROR` (top
  bits 3), waits on values other than `BHI_STATUS_SUCCESS` (2), and on
  success logs
  `Pong MHI: device is in SBL without an EE event, BHI_STATUS=%#x; pushing the AMSS image`,
  sets `mhi_cntrl->ee = MHI_EE_SBL`, sets `pong_sbl_pushed = true`, and calls
  `(void)mhi_download_amss_image(mhi_cntrl);`.
- `:240`: appends `bool pong_sbl_pushed;` to the pinned `linux/mhi.h` copy
  after `bool fbc_download;`.
- `:435-443`: `pm.c` SBL case has a one-shot guard before
  `mhi_cntrl->ee = MHI_EE_SBL;`; the first pass sets the latch when
  `fbc_download` is true, so a later EE event cannot download twice.
- `:282-286`: adds the `mhi_fw_load_bhie` diagnostic
  `Pong MHI: bhie tx_status=%#x seq=%#x expected=%#x ret=%d`, so a transient
  `BHIE_TXVECSTATUS` value is visible without changing the stock wait.
- `:370-393`: retains the c8 AMSS vector logging
  (`amss download begin entries=...`, `amss vec[...]`, `amss bhie load ret=... exec_env=...`).

Generated source anchors from `E:/k60-work/build/wifi-sbl-direct`:

| file | anchor |
|---|---|
| `mhi/boot.c` | direct block at :624-657; BHI error at :639; push log at :647; `ee = MHI_EE_SBL` at :648; latch at :649; direct download at :650; no queue call |
| `mhi/pm.c` | guard at :828; latch at :834; fallback download at :843 |
| `pinned/linux/mhi.h` | `bool pong_sbl_pushed;` at :445 |

The direct call is made in the same worker that just ran
`mhi_ready_state_transition`. That transition leaves `pm_state = MHI_PM_POR`
and MHI state M0, which `MHI_REG_ACCESS_VALID` accepts, so the new
`BHI_STATUS` read and the existing `mhi_fw_load_bhie` register writes have the
same lifetime as the stock READY path. `fbc_image` was allocated by
`mhi_fw_load_handler` before it called `mhi_ready_state_transition`, so the
vector table is already owned and no duplicate allocation occurs.

## 3. Candidate identity

| field | value |
|---|---|
| tag | `wifi-20261118sbl-direct` |
| built_at | 2026-11-18T01:26:58+08:00 |
| first flight | 2026-11-18 01:29, console `E:/k60-work/evidence/usblog-20261118-012938/console.log`, 237,343 B / 3,591 lines, SHA256 `9fff4a26237a3b6e795263a0a241c4dd2ab6aa42a84adbdde6b28cdaa3609c05` |
| branch / head | `fix/wifi-bhie-direct` / `0782eddcfbd3f503db8089a4f7b8a3d1de9c0200` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-direct/boot.img`, 201,887,744 B, SHA256 `03e11c823672930b8c4140b27b4576d68a10459baa9bfcdf9ef03d18979332e1` |
| kernel | `64694fa5e1b6e7c83f5cd4080ef781ebe4355693bd1fc25b75ed561b5c117ba5` (117,342,208 B) |
| payload kernel | `41c7ef00db65af102523dba2ef44c7f9826a7480b6f650f35208b78b76704f61` |
| WiFi archive | `a9cf5a4397078d660fb04573ebf0341de39d5fd42e0cd673d43c8938e1cc744e` |
| ath11k archive | `82463ea28fc3f1e424e55ba1621318e23119b1f132a09300acce2f82b1a04af6` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-direct/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=1 k60_wifi_rsc=2` |

This candidate is a single-variable test: stock six WLAN rails, `amss20.bin`,
`k60_wifi_rsc=2`, no MHI pre-load, no IPA rail, no c8 raw-register dump. The
earlier queue image `wifi-20261118sbl-gated` must not be re-flown; its first
flight is recorded in `SBL-QUEUE.md` §6.

Offline checks performed:
- `python3 -m py_compile scripts/build-k60-ath11k.py` — pass.
- `python3 scripts/tests/test-wifi-sbl-direct.py` — 17 source/artifact checks,
  0 failures. The mission successor renamed this file to
  `test-wifi-sbl-mission.py`.
- WSL `python3 scripts/verify-boot-image.py --manifest /mnt/e/...` — OK.
- WSL `python3 scripts/check-image-args.py --image /mnt/e/...` — OK (31
  arguments / 602 bytes).
- `strings -a kernel.macho | grep -c 'device is in SBL without an EE event'` — 1.
- `boot.json` recorded `hardware_tested: false` before the flight; the first flight is in §6.

## 4. Prewritten flight criteria

The image is only valid with a serial console captured before `fastboot boot`.

### Success — L1

- The device reaches SpringBoard (`Pong UI: ... entered SpringBoard`).
- No line matching c7's exact `Pong MHI: timeout after 20000 ms ee=0 ...`.
- New line `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x...; pushing the AMSS image`
  with BHI_STATUS top bits 2.
- Followed by `Pong MHI: amss download begin entries=...` and
  `Pong MHI: bhie tx_status=... seq=... expected=... ret=0`, then
  `Pong MHI: amss bhie load ret=0 exec_env=...`.
- Then `ath11k: chip_id 0x12 ...`, `fw_version ...`, and no
  `ath11k: failed to power up mhi: -110`.

### Failure / stop

- Same c7 timeout and no `pushing the AMSS image` line: the poll never read
  SBL within 2 s (or register access became invalid); stop, do not fly twice.
- Push line present but no `amss download begin`: the direct call did not
  execute or `fbc_image` was absent; stop.
- `BHI_STATUS=... not successful` repeats and no push line: the device never
  reported BHI success; stop and inspect BHI_STATUS/error code.
- `Pong MHI: bhie tx_status=...` non-zero `ret` with status not 2: BHIe
  handoff failed; stop and compare against the official `MhiImageLoading`
  sequence check.
- More than one `amss download begin`: the latch is not effective; stop.
- Any panic, cache-policy failure, or missing console: stop and follow the
  early-boot path. `Pong MHI: irq entered` is shim polling, not MSI proof.

## 5. What this candidate does not claim

It does not claim WiFi works: QMI, WMI, 102 channels, `en0`, scan, WPA2, DHCP
and HTTPS remain after MHI. It does not replace c8's audit status: c8 is still
HOLD and must not be built, booted or merged.

## 6. First flight of the direct candidate (2026-11-18 01:29)

The direct image `wifi-20261118sbl-direct` was flown with serial capture
attached before boot. The log is complete:
`E:/k60-work/evidence/usblog-20261118-012938/console.log` (237,343 bytes,
3,591 lines, SHA256 `9fff4a26237a3b6e795263a0a241c4dd2ab6aa42a84adbdde6b28cdaa3609c05`).
Boot was accepted, the console was captured, and SpringBoard was reached at
`:1630`.

The direct-push sequence is:

- `:646` `Pong MHI: device in READY state`.
- `:648` `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x8b9a74ae; pushing the AMSS image`.
  The top two bits are 2, so the success gate passed.
- `:650` AMSS vector table reported (`entries=12 last dma=0xa0001ec0 len=176`);
  `:658` `amss download begin entries=12`.
- `:664`/`:666` event types 32 and 64; `:668` `Pong MHI: EE event execenv=1`.
- `:685` `Pong MHI: bhie tx_status=0x2 seq=0x2 expected=0x24e1b3ae ret=19369`.
  The `ret=19369` is diagnostic garbage from an uninitialized local in the
  added log; the actual return is the next line.
- `:687` `Pong MHI: amss bhie load ret=0 exec_env=1` — **BHIe transfer
  succeeded**.
- `:691` `Pong MHI: timeout after 20000 ms ee=1 pm_state=4 exec_env=2 mhi_state=2 MHISTATUS=0x201 MHICTRL=0x200`.
  `pm_state=4` is `MHI_PM_M0`, `mhi_state=2` is `MHI_STATE_M0`, and
  `exec_env=2` is AMSS; the device is in mission mode.
- `:693` `ath11k: failed to power up mhi: -110`; SpringBoard still boots at
  `:1630`.

Interpretation: the direct BHIe path is correct and reaches AMSS. The remaining
single variable is the host's cached EE. The only EE event consumed was
`execenv=1` (SBL); after the image starts, the device reports `exec_env=2`
(AMSS) but no second EE event updates `mhi_cntrl->ee`. `mhi_sync_power_up`
(`pm.c:1277-1295`) waits on `MHI_IN_MISSION_MODE(mhi_cntrl->ee)`, sees
`ee=1`, and times out even though the device is already in M0/AMSS. This is
exactly the gap the official `MhiBoot.c:117-119` `MhiWaitMission` covers:
it polls `BHI_EXECENV` until AMSS/WFW; the direct candidate still returns to
stock `mhi_sync_power_up` with the stale cached value.

Next single-variable candidate: after `mhi_download_amss_image()` returns 0,
poll `mhi_get_exec_env` for up to 2 s; when it reads `MHI_EE_AMSS` or
`MHI_EE_WFW`, assign that value to `mhi_cntrl->ee` before
`mhi_sync_power_up` resumes. Keep the direct push, the BHI_STATUS gate and the
one-shot latch. Do not add QMI/WMI changes in the same flight.

