# Failure-reachable WiFi snapshot proposal

**Status: review only; NOT applied or ready to apply/build. c8 remains HOLD.** The
[unapplied diff](<../../../scripts/proposals/wifi-failure-snapshot.diff>) changes no
current driver, generator, artifact or manifest. No build, rebuild, boot, MSI
address/INTID/segment/window change is authorized by this proposal.

## Reachability and safe default

The new hook runs only at the non-mission return from mhi_sync_power_up(),
immediately before the existing mhi_power_down(mhi_cntrl,false) call. It does not
cover the immediate mhi_async_power_up() error return, every firmware-load error,
a later crash, or every failure path. Small board-counter snapshots also run at
the existing worker done label, before and after existing cleanup.

[Platform:690](<../../../drivers/PongWifi/PongWifiPlatform.cpp#L690>) branches to
done when nw_wifi_start fails. The later success loop and net-conditional periodic
print are not reached in c7; their absence says nothing about msiArrivals.

**Being before power-down does not establish allocation or MMIO lifetime.** The
new timeout helper takes no controller argument, dereferences no controller,
mhi_dev, CH/ER/CMD context, event object or ring, and reads no register. It uses
lx_log with a literal SKIP reason, then asks for module-static counters only.
A mapped address, non-null pointer, hostMmioReady, valid arithmetic range, or
cached EE/PM state is not accepted as a lifetime qualification.

## Collected and skipped values

| Layer | Proposed output | Interpretation boundary |
| --- | --- | --- |
| GIC dispatch | Existing INTID 172 owner count through a new count-only ArmCpu accessor; return code and count-available flag | The existing counter is incremented before the callback at [ArmCpu:407](<../../../drivers/ArmCpu/ArmCpu.cpp#L407>); it is not a logical Linux IRQ count. An unavailable count is not zero evidence. |
| Receiver callback | Existing msiEntries, msiArrivals and msiEmptyStatus atomic values | msiArrivals counts callbacks which observed nonzero MsiStatus, not individual vectors. These are prior ISR observations, not current register values. |
| Software shim | Pump calls, polling-triggered raises, all raise_all calls and logical handler dispatches | Forced software dispatch is distinct from hardware dispatch. Counts are module-lifetime cumulative values, without a session baseline. |
| MHI objects and registers | SKIP with allocation/powered-MMIO lifetime unproven | No cached EE/PM, pointer, context length, ring value, MHI register or payload read is attempted. |
| Receiver and GIC registers | SKIP with powered-MMIO lifetime unproven; enable/mask/status/pending/active/route unavailable | No DBI, PARF, distributor read or new GIC mapping is attempted. No successful zero values are fabricated. |

The existing ArmCpu dispatcher and its one counter increment remain byte-for-byte
unchanged. Its module-static owner array is published by the existing release
store to gSpiUsed at [ArmCpu:449](<../../../drivers/ArmCpu/ArmCpu.cpp#L449>); the
accessor uses an acquire load, bounds-checks used, then atomically reads the
existing counter. It never accesses gDist. No new ownership slot is used.

The existing WiFi ISR has logging. The proposed diff removes those prints while
preserving counter, ACK, mask and wake behavior. No new snapshot call, logging,
allocation or ring mutation enters interrupt context. Existing cleanup writes
remain unchanged; these changes do not prove their powered-MMIO lifetime or make
existing c8 register reads lifetime-safe. In particular, generated c8
pm.c:1300–1305 already reads MHISTATUS/MHICTRL and calls the execution-environment
and MHI-state readers before the new hook. This proposal makes only the added
diagnostic counter-only; it does not certify the whole existing timeout path.

## Why the richer snapshot is deferred

The lifetime audit found no callback-owned reference, lock or lease spanning this
hook. In the inspected Linux 7.0.14
[unregister path](<E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/bus/mhi/host/init.c#L1060>),
mhi_unregister_controller tears down IRQ/workqueue state, frees command/event/
channel metadata and releases the device. The generated c8
[context deinit path](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__init.c#L256>)
frees context/ring allocations independently. Valid pointer arithmetic cannot
exclude teardown or reuse. The audit identifies teardown endpoints; it does not
prove that a free actually races this timeout. The active caller expects the
controller to remain alive, but this added diagnostic has no demonstrated
spanning reference or teardown exclusion. See the companion
[lifetime audit](<FAILURE-SNAPSHOT-LIFETIME-AUDIT.md>). Power readiness is a
separate missing proof from mapping and allocation retention.

A future richer proposal needs an exact callback lifetime proof, stable context
ownership, teardown/reset exclusion and a powered-MMIO lease covering each read.
It must not replace those requirements with a fabricated provider or a boolean
that records only earlier initialization. Safe field capture and multiword/shared
read stability also need review before any register/context data is collected.

The [host test](<../../../scripts/tests/test-wifi-failure-snapshot-proposal.py>)
retains **offline-only** range and ring arithmetic. Its artificial input values
are not runtime observations, do not permit dereference and do not prove a page
table, cache visibility, current SMMU translation, or device DMA. The desired
future checks remain: actual CH/ER/CMD pointer-plus-length versus envelope and
mapped arena; separate original/aligned ring spans; host/shared pointer bounds;
and context bus addresses versus CCABAP/ECABAP/CRCBAP. None is collected now.

## Transformations and stability limits

The diff targets three repository-owned files: ArmCpu, PongWifiPlatform and the
ath11k generator. A strict source transformer adds the no-argument helper after
the generator's existing MHI pm.c patch pairs; another adds module-static shim
counters after the existing timer adapter. Each anchor must occur exactly once;
missing, duplicate and repeated-application inputs fail closed. External/generated
files are not edited. Only the board-counter diagnostic is added to the import
allowlist; its existing nw_wifi prefix rule is retained.

Individual atomic counter loads do not form a globally atomic snapshot. ISR
counts can advance between loads, 32-bit callback counters can wrap, and logging
changes timing. A zero count constrains only that counter's observed interval;
SKIP or count_available=0 means unavailable. The proposal does not infer that
SBL never emits MSI, that an event ring is unchanged, or that a route works.
No counter is cleared or reset; no lx_pump, doorbell, BHIE clear/retry, EE/PM state
write or cache operation is added by a snapshot helper.

## Host validation

Run the test with Python -B; it reconstructs proposed files only in memory,
parses the generator AST and executes selected pure source transformers. It
checks unchanged GIC dispatch, strict anchors, no new ISR logging, no object/MMIO
access in new helpers, and offline arithmetic boundaries. Negative cases inject
MHI pointer dereferences, raw register calls and board-window reads and must fail.

On 2026-11-16 the current revision passed **11/11 tests** against retained c8 pm.c
and shared lx_rt.c, plus git apply --check. The default invocation omits the
external-source case unless --pm-source and --shim-source are supplied. No
reconstructed source is written and no patch is applied. C/C++ compilation,
linking, complete generator execution and hardware behavior remain untested.
Parent must independently review the final diff and repeat the host checks.
**c8 remains HOLD after these checks pass.**
