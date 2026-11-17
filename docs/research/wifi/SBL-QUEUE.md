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
| Is this proven on K60? | **No — the queue path failed on its first flight (2026-11-18 00:55, §6).** The image exists and the offline gates pass; it was flown once and did not reach MISSION. `boot.json` still records `hardware_tested: false`. |

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

The queue is safe to issue from the same worker that is running the PBL
handler: Linux workqueue clears `WORK_STRUCT_PENDING_BIT` in
`process_one_work()` before it calls `worker->current_func(work)`, so a
`queue_work()` issued from inside `mhi_pm_st_worker()` schedules a fresh pass
instead of being dropped. The queued `DEV_ST_TRANSITION_SBL` item then runs
through `case DEV_ST_TRANSITION_SBL` in the same `mhi_pm_st_worker()` and calls
`mhi_create_devices()` + `mhi_download_amss_image()` exactly once (the
`pong_sbl_pushed` latch guards a later EE event).

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

The official reference also rules out one near-miss: `WifiProbe.cpp:1195` calls
`mhi_boot_begin(&boot, 0, ...)` with `msi_vector = 0`, so the stock Linux
`BHI_INTVEC = 0` write is not a K60/Pong divergence and must not be tried as
the next candidate.

## 3. Candidate identity

| field | value |
|---|---|
| tag | `wifi-20261118sbl-gated` |
| branch / head | `fix/wifi-bhi-execenv-wifi` / `4e00d56943d2fd280cd83cf06e630395050c1b1c` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-gated/boot.img`, 201,887,744 B, SHA256 `34867c7f26e975c7043e5d4c9ea7c00259374d7eeb24e83bbb655a3b1967e24c` |
| kernel | `4603d0c6ccb86a287049479720e6af96af51eb67f52443f21cb7ba2995ae7754` |
| payload kernel | `f857369b948f6d56b642e8c8985a9cff391dbba3b01e8c1811dcda23078a7dba` |
| WiFi archive | `c03534a77386b6ed17094e0fc63116dcf80e5d20911cebe5ea6732bd9cd44f8e` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-gated/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=1 k60_wifi_rsc=2` |

The earlier `wifi-20261117sbl-queue` image (head `e6b71ba8`) was built before
the BHI_STATUS gate existed and was never flown; it is superseded by the gated
candidate above and must not be booted.

Offline checks performed:

- `python3 -m py_compile scripts/build-k60-ath11k.py` — pass.
- At build time `python3 scripts/tests/test-wifi-sbl-queue.py` — 14
  source/artifact checks (including the BHI_STATUS success gate), 0 failures.
  The successor renamed this test to `test-wifi-sbl-direct.py`.
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
still HOLD and must not be built, booted or merged.

## 6. First flight of the queue candidate (2026-11-18 00:55)

The gated queue image `wifi-20261118sbl-gated` was flown with serial capture
attached before boot. It reached SpringBoard, and the log is complete:
`E:/k60-work/evidence/usblog-20261118-005525/console.log` (143,253 bytes,
2,079 lines). The MHI sequence is:

- `:586` 64 MiB wired DMA mapped, 35 native-4K table pages.
- `:600` `Pong MHI start: timeout=20000 ... ee=0 state=0`; `:614` firmware
  serial `0x22d0a7f3`, `ee=0 fbc=1`; `:616` `amss20.bin bytes=5296128`.
- `:629` device in READY state.
- `:631` `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x8b9a74ae; queueing the SBL transition`.
  The top two bits are `2`, so the BHI_STATUS success gate passed.
- `:635` `Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200`.
- `:637` AMSS vector table reported (`entries=12 last dma=0xa0001ec0 len=176`),
  `:645` `amss download begin entries=12`, then `:651`
  `amss bhie load ret=-5 exec_env=1` and `:653` `MHI did not load AMSS, ret:-5`.
- `:655` `ath11k: failed to power up mhi: -110`; SpringBoard still boots at
  `:1380` `Pong UI: 20G81 compatibility library entered SpringBoard`.

Interpretation: the queued SBL work item was not executed while the power-up
state was valid. `mhi_sync_power_up` (`pm.c:1277-1295`) times out first and
calls `mhi_power_down` (`pm.c:1212-1259`), which sets
`pm_state = MHI_PM_LD_ERR_FATAL_DETECT` and flushes `st_worker`. The queued SBL
item then runs during that flush; `mhi_fw_load_bhie` (`boot.c:210-223`) returns
`-EIO` immediately because `MHI_REG_ACCESS_VALID(pm_state)` is false. This
explains `amss bhie load ret=-5` without proving a device-side BHIe error.

The successor therefore calls `mhi_download_amss_image` directly in the same
`mhi_fw_load_handler` pass after READY and BHI_STATUS success, before the
power-up wait can tear the state down. It keeps the bounded 200 x 10 ms
`BHI_EXECENV` poll and the one-shot `pong_sbl_pushed` latch, and adds a
`BHIE_TXVECSTATUS` sequence/status/ret log. See `SBL-DIRECT.md`.
