# MHI state machine: why the device waits in SBL and the host waits for an event

Written 2026-11-16, after c7 (`usblog-20261116-122546`). Scope: the host-side
MHI bring-up sequence as this tree runs it, the one transition that c7 proved
does not happen, and why the two sides wait for each other forever instead of
one of them timing out and retrying. c8 tests the resulting hypothesis.

## 0. Conclusion first

| question | answer |
|---|---|
| Where does the bring-up stop? | After READY. `mhi_sync_power_up()` waits 20 s for `MHI_IN_MISSION_MODE(ee)` and returns `-ETIMEDOUT` (-110). |
| What is the device doing? | Sitting in READY, execution environment SBL (`BHI_EXECENV = 1`), no system error (`MHISTATUS = 0x101`, SYSERR clear). |
| What is the host doing? | Waiting for an `MHI_PKT_TYPE_EE_EVENT` that would set `mhi_cntrl->ee = MHI_EE_SBL` and trigger the AMSS download. |
| Why is that a deadlock rather than a slow device? | The host only sends AMSS from the `DEV_ST_TRANSITION_SBL` branch, and that branch only runs when the EE event arrives. The device, already in SBL, waits for AMSS. Neither side moves; the 20 s timeout is the only thing that ends it. |
| What does c8 change? | Nothing in the state machine: after `mhi_ready_state_transition()` succeeds, if the hardware execution environment reads back as SBL, the host sets `mhi_cntrl->ee = MHI_EE_SBL` itself and calls `mhi_download_amss_image()`. |

## 1. The sequence as the code runs it

All line numbers are in `drivers/bus/mhi/host/` unless stated; the copies the
build compiles are the patched ones under
`/opt/k60/trees/k60build/wifi/ath11k-c8/mhi/`, and every patch is a print plus
the one c8 branch, so the control flow below is upstream's.

```
ath11k_mhi_start()                         ath11k/mhi.c:446
  mhi_prepare_for_power_up()               pm.c
  mhi_sync_power_up()                      pm.c:1277
    mhi_async_power_up()                   pm.c
      -> mhi_pm_st_worker()                pm.c:798
           case DEV_ST_TRANSITION_PBL:     pm.c:816
             ee = mhi_get_exec_env()       pm.c:819   reads BHI_EXECENV
             mhi_fw_load_handler()         pm.c:821
```

`mhi_fw_load_handler()` (`boot.c:490`) is where the two halves of the image are
separated:

| step | code | what c7 reported |
|---|---|---|
| read the serial number | `boot.c:507` `mhi_read_reg(..., BHI_SERIALNU, ...)` | `:614` `serial=0x22d0a7f3 ee=0 fbc=1 fw_sz=0` |
| pick the load type | `boot.c:556` `mhi_fw_load_type_get()` | `:618` `load type=2 image bytes=524288 vector bytes=5296128` — type 2 is FBC |
| build the BHIE table over the whole file | `boot.c:596` `mhi_alloc_bhie_table(&fbc_image, fw_sz)` | never printed, but the allocation is silent by design |
| copy the file into the segments | `boot.c:603` `mhi_firmware_copy_bhie()` | silent; the copy is what makes the vector table live |
| push the first 512 KiB (SBL) over BHI | `boot.c:568-583` `mhi_fw_load_bhi()` | `:618` `image bytes=524288` |
| RESET→READY, by polling | `boot.c:610` `mhi_ready_state_transition()` | `:624` polling, `:626` reset cleared, `:628` device in READY |

`mhi_ready_state_transition()` (`pm.c:170`) is the part that is easy to
misread as interrupt-driven. It is not:

- `pm.c:186-198` polls `MHICTRL_RESET_MASK` to zero, then `MHISTATUS_READY_MASK`
  to one, at 25 ms intervals. READY arriving proves the device accepted the
  reset handshake, not that it raised an interrupt.
- `pm.c:224` `mhi_init_mmio()` writes `CCABAP`/`ECABAP`/`CRCBAP` with the real
  context addresses, `MHICTRLBASE`/`MHIDATABASE` with `iova_start`, and
  `MHICTRLLIMIT`/`MHIDATALIMIT` with `iova_stop`.
- `pm.c:236-258` then, for every event ring, sets
  `*ring->ctxt_wp = ring->iommu_base + ring->len - ring->el_size` — the wrap
  value — and rings the ER doorbell, then `mhi_set_mhi_state(MHI_STATE_M0)`.

That wrap value is exactly what c7 printed as the device read pointer:
`:608` `dev rp=0xa0001a00 host rp=0xfffffff9bb055a00`. The two are the same
address in different address spaces (`0xa0001a00` is the IOVA the device was
given, the other is the host mapping of the same page), and it never moved in
20 s, which is the direct evidence that the device wrote nothing into the event
ring.

```
  ... after READY the host waits:
  mhi_sync_power_up()                     pm.c:1277
    wait_event_timeout(state_event,
        MHI_IN_MISSION_MODE(ee) || MHI_PM_FATAL_ERROR, 20000)
    ret = MHI_IN_MISSION_MODE(ee) ? 0 : -ETIMEDOUT      pm.c:1297
```

## 2. The transition that does not happen

The only thing that moves `mhi_cntrl->ee` off its initial value is the event
ring handler:

| step | code |
|---|---|
| the device writes an EE event and rings the ER doorbell | device side |
| the doorbell becomes an MSI, the MSI becomes a GIC interrupt | `PongWifiPlatform::irq()`, see `MSI-TOPOLOGY.md` |
| the shim dispatches it to `mhi_irq_handler()` | `main.c:1023` |
| the handler reads `er_ctxt->rp`, compares it with `ev_ring->rp` | `main.c:1023-1034` |
| equal ⇒ return, nothing to do | `main.c:1027` |
| different ⇒ walk the TREs, dispatch by type | `main.c` `mhi_process_event` |
| `MHI_PKT_TYPE_EE_EVENT` ⇒ `mhi_queue_state_transition(DEV_ST_TRANSITION_SBL)` | `main.c:893-926` |
| the worker then runs `case DEV_ST_TRANSITION_SBL:` | `pm.c:823` |
| sets `mhi_cntrl->ee = MHI_EE_SBL` | `pm.c:825` |
| creates the MHI devices | `pm.c:832` `mhi_create_devices()` |
| **and only here pushes AMSS** | `pm.c:833-834` `if (fbc_download) mhi_download_amss_image()` |

c7 shows every one of those steps failing to happen, and shows it twice over:
the host-side MHI handler ran (the shim raises all 64 shim IRQs on every pump,
so its invocation proves nothing) but found `ev_ring->rp == dev_rp` three times
in a row, and `mhi_cntrl->ee` was still `0` (`MHI_EE_PBL`) in the timeout line.
`mhi_download_amss_image()` was therefore never called — which is why the
`amss entries=` / `vec[]` prints c7 added never appeared. Their absence is a
result, not a missing print.

## 3. The deadlock, stated as a loop

```
        device                                    host
   ─────────────────────────────────────────────────────────────
   receives 512 KiB SBL over BHI
   enters SBL, BHI_EXECENV = 1
   ... waits for AMSS ...            ... waits for EE_EVENT(SBL) ...
                                     ee stays MHI_EE_PBL
                                     MHI_IN_MISSION_MODE(ee) false
                                     mhi_download_amss_image() never runs
                                     AMSS (5,296,128 B) stays in host memory
   ... waits for AMSS ...            ... 20 s elapse, -ETIMEDOUT ...
```

The image the device is waiting for is already in host memory and already
described by a live BHIE vector table; it is the *trigger* that is missing, not
the data. That is what makes this a sequencing bug on the host side rather than
a firmware problem: nothing about the device's state says it refused the image,
and its registers say it is healthy (`MHISTATUS = 0x101`: READY, no SYSERR).

Register decode used above (`common.h:111-115`):

| value | field | meaning |
|---|---|---|
| `MHISTATUS = 0x101` | `MHISTATUS_MHISTATE_MASK` (bits 15:8) | `1` = `MHI_STATE_READY` |
| | `MHISTATUS_READY_MASK` (bit 0) | set |
| | `MHISTATUS_SYSERR_MASK` (bit 2) | clear |
| `MHICTRL = 0x200` | `MHICTRL_MHISTATE_MASK` (bits 15:8) | `2` = `MHI_STATE_M0`, the host already asked |
| | `MHICTRL_RESET_MASK` (bit 1) | clear, reset released |
| `BHI_EXECENV = 1` | `include/linux/mhi.h:123-134` | `MHI_EE_SBL` (PBL=0, SBL=1, AMSS=2, RDDM=3, WFW=4, PTHRU=5, EDL=6, FP=7) |
| `ee = 0` | host-side `mhi_cntrl->ee` | still the initial `MHI_EE_PBL`: no EE event was ever processed |

## 4. What c8 does about it

One branch, placed after `mhi_ready_state_transition()` succeeds and before the
`Wait for device to enter SBL or Mission mode` message (`boot.c:608-616`):

```c
if (mhi_cntrl->fbc_download &&
    mhi_get_exec_env(mhi_cntrl) == MHI_EE_SBL) {
        /* print MHISTATUS, MHICTRL, MHICTRLBASE, MHIDATABASE, ECABAP,
           and the iova window, before the push */
        mhi_cntrl->ee = MHI_EE_SBL;
        mhi_download_amss_image(mhi_cntrl);
        /* print MHISTATUS, MHICTRL, exec_env after the push */
}
```

The gate is a hardware read (`BHI_EXECENV`), not a guess, so an image that
reaches this code with the device still in PBL behaves exactly as before. The
push itself is upstream's `mhi_download_amss_image()`, unchanged except for the
three prints c7 was missing (`entries`, `vec[0]`, `vec[entries-2]`, and the
BHIE return value with the execution environment that follows it).

What each outcome means:

| outcome | reading |
|---|---|
| `amss download begin entries=11`, then `exec_env` becomes 2 (AMSS) or a MISSION transition appears | the deadlock hypothesis holds: the device wanted the image, not an event. WiFi bring-up can continue past MHI. |
| `begin` appears, `amss bhie load ret` is negative or `MHI did not load AMSS` follows | the vector table or the BHIE addresses are wrong; next step is the BHIE registers and `BHI_STATUS` raw values, not more state-machine prints |
| no `begin` at all | the gate did not match: at READY the execution environment was not yet SBL. Then the trigger has to become a poll of `BHI_EXECENV` over a few hundred milliseconds. |
| the device enters SYSERR, panics, or the console dies | stop; dump `BHI_STATUS`, `MHISTATUS`, `MHICTRL` before changing anything else |

## 5. What this note does not claim

- It does not claim the missing EE event is a firmware defect. The vendor
  kernel never needs the event for this step because it drives the same
  transition from its own boot flow; a host that waits for the event on a
  device that does not send one is a host-side sequencing choice, and c8 tests
  exactly that.
- It does not change `seg_len`, `sbl_size`, `iova_start`, the MSI target
  address, the INTID, `board.toml` or the payload budget. One variable per
  flight (P-218).
- It does not explain why the EE event is missing. If c8 works, that question
  becomes "why does this device not announce SBL", which matters for the
  vendor-compatible path but not for bring-up.
