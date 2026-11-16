# WiFi MHI pre-load: program the contexts before offering the SBL image

Date: 2026-11-17
Status: candidate image built; not flown. c8 remains held.

## 0. Summary

The K60 port offers the SBL image to the QCA6490 while the MHI context
registers are still unprogrammed. The shared WCN7850 driver has already
recorded the exact failure and the working sequence for this family:

> The boot loader of the chip answered the image with an error code when it
> was offered right after the reset with no MHI contexts programmed. The
> loader that worked on this board waited, then wrote the context registers,
> then offered the image: do the same (the registers are written again after
> the loader's start, as the host's own sequence does).

Source: `E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi/src/nw_mhi.c:71-83`.
That workaround does two things: a short settle after reset, then a direct
`mhi_init_mmio()` call before the image is offered. It is not a change to the
MHI state machine.

The K60 MHI path currently does the opposite. `mhi_prepare_for_power_up()`
allocates the device contexts and reads the BHI offsets, but does not call
`mhi_init_mmio()`:

- `E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/bus/mhi/host/init.c:1108-1188`
  (`mhi_prepare_for_power_up`; `mhi_init_dev_ctxt()` at `:1116`)
- `init.c:469-607` is `mhi_init_mmio()`; it writes CCABAP, ECABAP, CRCBAP,
  MHICTRLBASE, MHIDATABASE, the IOVA limits, and MHICFG.
- The only normal call is in `pm.c:224` inside
  `mhi_ready_state_transition()`, after the SBL image has already been offered
  (`boot.c:540` is `request_firmware()`; `boot.c:610` is the later ready
  transition).

The candidate inserts the missing pre-load call into the generated
`mhi/boot.c` at the `skip_req_fw:` label, before
`fw_load_type = mhi_fw_load_type_get()`. It waits 200 ms, calls
`mhi_init_mmio()`, and fails closed if that returns an error. This is the
same shape as the working shared driver, adapted to the K60 generator's
logging and error convention.

## 1. The candidate change

Worktree: `E:/hackios/k60-wifi-mhi-preload`, branch
`feat/wifi-mhi-preload`, based on the cache candidate's HEAD
`7cce6e8a` (which is itself the c7 baseline `b004fe6c` plus the DMA
cache-policy fix).

Commits:

- `7b9ff7da` `fix(wifi): program MHI contexts before offering the SBL image`
- `3410d341` `chore(engineering): register the wifi mhi preload worktree`
- `df878236` `test(wifi): target the preload fail-closed block`

The generator change is in
`E:/hackios/k60-wifi-mhi-preload/scripts/build-k60-ath11k.py`:

- `:270` starts the static `nw_mhi_pre_load()` helper.
- `:283` is the log line
  `Pong MHI: contexts programmed before image: %d`.
- `:312-314` inserts the call at `skip_req_fw:` before
  `fw_load_type = mhi_fw_load_type_get(mhi_cntrl);`.

The generated source used for this build,
`/opt/k60/trees/k60build/wifi/ath11k-mhi-preload/mhi/boot.c`, has the
helper at line 21, the log at line 36, `skip_req_fw:` at line 577, the
call at line 578, and `fw_load_type` at line 584.

The host test is
`E:/hackios/k60-wifi-mhi-preload/scripts/tests/test-wifi-mhi-preload.py`.
It checks the helper, the 200 ms settle, the direct `mhi_init_mmio()` call,
the call order at `skip_req_fw:`, and the fail-closed `goto error_fw_load`
path. It rejects five negative mutants: missing settle, missing context
write, missing call, not fail closed, wrong init helper. It passes both on
the generator source and on the generated `boot.c` supplied above.

Relative to the **flown cache candidate**, this image adds exactly one
executable variable: the MHI pre-load. The DMA cache-policy fix is retained
because it was already measured on 2026-11-17 02:17 CST and did not change
the c7 stall; this build does not re-open that variable.

## 2. Built artifact

All build-host paths are WSL paths.

| Item | Value |
|---|---|
| tag | `wifi-20261117mhi-preload` |
| boot image | `E:/k60-work/artifacts/wifi-20261117mhi-preload/boot.img` |
| boot SHA-256 | `ae27680067b54cdc710df4f046e80509f0e930d517bfc080ae43b1aaff573d87` |
| size | 201,887,744 B |
| manifest | `E:/k60-work/artifacts/wifi-20261117mhi-preload/build-manifest.json` |
| manifest SHA-256 | `7c3f675f10bd87b2247f99e4aa336e81a8eb325b402dea57847ccaea2a71c7bf` |
| repo | `feat/wifi-mhi-preload` @ `df8782367799090f03c8e2e16b5c31043aa9a011`, dirty 0 |
| kernel | `0b3e16aeef31adb45c2aa83090d7a185bc59e15cc8f8602b2a32813a67cbdb26` |
| payload kernel | `25fb92edf2f3e3563c3ef71c1337c40ac028c240c486b30d111aec6769dddc45` |
| ADT | `8ee95ff95c1285eed37c785ac0fb3572089b9354ca1d8b41e5740b81f51ea2e8` |
| WiFi archive | `3d4e69e181b491941a4965e098f9864814b0b243e1047395d017bbfe9c842ebc` |
| args | 31 items / 602 B, ends `pong_wifi=1 k60_wifi_rsc=2` |
| series | 227 files, `59d8037521a5b07b`, file `bb14a480c6b2ea4b465f409d862394f0ea25cce178d19a63b7253fab3511f9d4` |
| built at | 2026-11-17T03:19:22+08:00 |

Checks already run:

- `python3 scripts/verify-boot-image.py --manifest ...` → `OK`
- `python3 scripts/check-image-args.py --image ...` → `OK (31 arguments, 602 bytes)`
- `python3 scripts/tests/test-wifi-mhi-preload.py` → `PASS` (5 negative cases)
- same test with `--generated /opt/k60/trees/k60build/wifi/ath11k-mhi-preload/mhi/boot.c` → `PASS`
- archive strings: `Pong MHI: contexts programmed before image: %d` present;
  `pre-push` 0, `amss download begin` 0 (c8 not included)
- archive symbols: `_pong_wifi_firmware` and `_pong_wifi_firmware_end` in
  `__DATA,__const`; `_pong_smmu_lease_lock` in `__TEXT`

## 3. Flight criteria (prewritten, one new variable)

This image may be flown once, with the serial console capture attached before
boot. Judge the console, not whether the boot looks normal.

**Setup**

- Compare against the flown cache candidate; the only new executable change
  is the MHI pre-load in generated `mhi/boot.c`.
- Do not combine with c8. Do not change boot args, `seg_len`, `iova_start`,
  MSI target, INTID, or firmware on this flight.
- Console must include the existing MHI lines. `Pong MHI: irq entered` is a
  software-shim replay, not proof of a hardware MSI; it is not the L1 signal.

**Success — L1**

All of:

1. Boot reaches SpringBoard with a console log; no panic and no boot death
   before the WiFi driver runs.
2. The c7 timeout line is absent:
   `Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 mhi_state=1 MHISTATUS=0x101 MHICTRL=0x200`
3. The new line appears before any image offer:
   `Pong MHI: contexts programmed before image: 0`
4. The event path advances. At least one of:
   - `Pong MHI: event type=` appears, or
   - `Pong MHI: EE event execenv=` appears, or
   - the printed `exec_env` advances past SBL (values other than 0).
5. `ath11k: failed to power up mhi` is absent.

`QCA6490 MSI entered the GIC handler` is not required for L1; if it appears it
is additional evidence only.

**Success — L2/L3 (follow-on, not this experiment)**

- L2: QMI service/channel bring-up, MHI mission mode, 102 channels.
- L3: `en0`/IO80211 published and a scan returns BSS entries.

**Failure — stop and report**

- The same c7 timeout returns with no `event type`/EE line and no `exec_env`
  advance → the pre-load alone is not sufficient; do not fly c8 on this result.
- `Pong MHI: contexts programmed before image: <negative>` appears →
  report the exact return code; do not retry with a looser check.
- `MHI contexts were not programmed before image` appears → same: stop.
- Panic, boot death, or no console → stop; preserve the image SHA-256 and the
  last console line.

## 4. What remains unclosed

- The pre-load is proven as a workaround in the shared WCN7850 driver, but this
  QCA6490 K60 image has not yet been flown. The hardware question is whether
  this device’s SBL accepts the context write before the image; the test is
  binary and prewritten above.
- No Pong raw pstore log or Pong `modem_b` firmware image is available in this
  workspace, so the c7 firmware-content comparison remains an independent open
  variable. This candidate does not change firmware.
- The call writes the same context registers that `mhi_ready_state_transition()`
  writes later; it uses the existing controller context and the same
  `iova_start`/`iova_stop` values. It does not add a new address translation.
- c8 (proactive AMSS push) remains HOLD; it is not part of this image and its
  duplicate-SBL and context-lifetime questions are unchanged.
