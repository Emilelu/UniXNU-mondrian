# BT d8: recorded inputs and source-bound host timing checks

Dated continuation, 2026-11-16. This supplements the earlier [reassessment](REASSESSMENT-2026-11-16.md); it does not rewrite that pre-d8 snapshot or promote the Bluetooth diagnostic flight into functional acceptance. Work is on `test/bt-d8-timing-model`. Main remains the separately recorded baseline; this change adds offline checks only. No driver, patch series, boot arguments, kernel/image build or device operation is changed here.

## Result and limits

Lead independently ran the source-bound C harness: **34 scenarios, 84 assertions and 8 input-rejection guards passed, exit 0**. The recorded-input checker returned **RECORDED_INPUTS_MATCH**, exit 0; its **17 synthetic regression fixtures passed**. These are three different results:

- The input checker binds a specific saved manifest, frozen lists, all 235 series patch files, selected committed source blobs, ordered patch-application log entries and boot image bytes. It has no implicit latest-build or foreign-tree fallback.
- The host harness executes complete QBT core C extracted from the pinned patches, with deterministic fake platform callbacks. It also exercises the actual 0515 measurement blocks around a fake segment-send boundary.
- Neither result proves which physical event caused the d8 NVM failure. No controller-acceptance, full firmware-download, effective UART/DMA/IBS, compiler-to-payload, or flash-gate proof follows from these checks.

The independent child audit and final test implementation are recorded as SA-08 in the [subagent ledger](../research/SUBAGENT-DELIVERABLES.md). Lead reviewed the implementation and ran it independently before integration. The child deliverables are both retained: [runner](../../scripts/tests/test-bt-d8-host-timing.py) and [C fixture](../../scripts/tests/fixtures/bt-d8-timing-harness.c).

## Recorded d8 identity

The explicit external source checkout is `E:/hackios/k60-bt`; the explicit artifact directory is `E:/k60-work/artifacts/bt-d8-tlv`. A newer docs-only owner HEAD is not substituted for the manifest's source revision. The checker reads the recorded commit directly and also checks the currently supplied patch bytes.

| Object | Recorded identity |
| --- | --- |
| Build source commit | `91dcd0761aeb035c15de743478851fb8ce0c0417`, manifest dirty count 0 |
| Manifest SHA-256 | `3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0` |
| Frozen before/after SHA-256 | `ec0bce53352203a5e430ce1ac7f80ae407ed1ba3ba208286dc665ddfe741f4e9`, equal lists, 515 entries |
| Series | 235 names; file SHA-256 `9a2cfd416b5250854f8fda38d03ca095a631be296e0679bf9522ba445e73cbb8` |
| Series fingerprint | namespace `names+sizes`, `f7aa7d63470b891d`; uses the existing [single implementation](../../scripts/series-fingerprint.py) |
| Kernel application log SHA-256 | `27c0c59caafd659bd9d0797ac354691e13a278eccb6edb3fac1e6d975174c6d3` |
| Boot image SHA-256 | `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b` |

Selected source pins, also present in the saved frozen list:

| Patch | SHA-256 |
| --- | --- |
| `0500-k60-bt-qbt-new-files.patch` | `4e6f58d96f1ba06cd8d440feaa7546e3df05519631a8550b96a6441ba69bc0b0` |
| `0514-k60-bt-boot-observability.patch` | `e6d5296b0b9e7e137c0f12271670aa485ebfa4e649b090101e258faef418a73c` |
| `0515-k60-bt-tlv-counters.patch` | `120c4d57d1bf72bdee18770a520367bd68d46c1c96ffb185c5bbf51ec46c4cd6` |

The application log names the three patches exactly once, in that order. The saved build eight-step log selected six items; it must not be confused with the later Bluetooth-owner flash preflight that selected seven items/56 checks. This input checker is not a replacement for either gate. It also does not unpack the boot payload or prove correspondence between compiler output and the packaged kernel.

## Device observation retained as failure

The existing capture is [console.log](E:/k60-work/evidence/usblog-20261116-164726/console.log), SHA-256 `1ef1f5abf55f6036f36c729779aab3de53f667e782e9ba3492fb332109be7cd2`, 255020 bytes/3749 lines. Capture metadata records a complete budget capture, accepted boot, and no panic/reset markers. SpringBoard appears 129 times on 128 lines. These are capture/boot observations, not Bluetooth functionality.

| Software observation group | Logged calls | Cumulative counters at group end | Result |
| --- | ---: | --- | --- |
| PATCH, type 1 | 602 | sent=602, acks=1, final=0 | ret=0; rampatch completion line |
| First NVM attempt | 7 | sent=609, acks=7, final=0 | six e=0 calls around 10000/10001 ms, then ret=-60 |
| NVM fallback | 21 | sent=630, acks=28, final=1 | twenty e=0 calls at integer dt_ms=0, then ret=-60 |

The NVM attempt deltas are sent/acks 7/6 and 21/21. Calls include failed attempts; counters are cumulative. `acks` counts particular software-decoded reports, including nonzero status, rather than independently correlated per-segment controller acceptance. `final` is overwritten by subsequent reports. The theoretical 27-segment division is not measured execution. The terminal `power=1 result=-60` and absence of an NVM completion marker remain the functional verdict. The grouping artifact is [BT-D8-OBSERVED.json](E:/k60-work/artifacts/reassessment-20261116/BT-D8-OBSERVED.json).

## What the real C tests establish

The [host runner](../../scripts/tests/test-bt-d8-host-timing.py) extracts full `bsd/dev/qbt/qbt_core.c`, `qbt.h` and `qbt_internal.h` from 0500, then applies exact 0514 core/header hunks in an external work directory. Ambiguous context or changed source hashes fail closed. It wraps the exact 0515 segment/summary blocks, using a fake segment-send function; it does not execute the entire `btqca.c` download or fallback routine. The [fixture](../../scripts/tests/fixtures/bt-d8-timing-harness.c) includes that extracted core and supplies fake clock, pump, waits, UART callbacks and scheduled event bytes.

Source anchors are the pinned owner's `0500-k60-bt-qbt-new-files.patch:1615-1644` (event handling), `:1791-1835` (run/command/delay), `0514-k60-bt-boot-observability.patch:43-64` (deadline ordering), and `0515-k60-bt-tlv-counters.patch:19-52` (measurement blocks). The final extracted source, executable and logs are retained outside the source trees.

| Area | Scenarios | Established software behavior |
| --- | ---: | --- |
| Events/status | 8 | TLV report counters can advance without a matching wait; nonzero TLV status counts but does not complete; generic status and later adapter interpretation are distinct. |
| Deadline ordering | 10 | `pump`/step, error and completion predicate precede global boot deadline and command deadline; equality uses `>=`. A matching late event can return success before expiry is checked. |
| Scheduling | 5 | `qbt_deadline()` suggests a wakeup, not a command timeout. The run-loop sleep is clamped to the command deadline, not the boot deadline; fake boot=50/command=100 wakes at 100. |
| Commands | 8 | A new command clears complete/reply state but retains global budget/counters. A same-opcode old event arriving after the new wait can satisfy it; there is no transaction identity in this matcher. |
| 0515 observations | 3 | Millisecond duration truncates; logging overhead follows sampling; failed calls still count; summaries read cumulative/current counters. |

The deadline counterexample is a software property, not a diagnosis of the physical d8 trace. For example, it does not establish that stale events caused its fallback, that the controller is merely slow, or that a longer budget would complete NVM. No budget, download mode, segment size, event matching, address, state-machine or hardware change is justified by test success alone.

Explicitly **NOT RUN** here: full QCA firmware-download/fallback, `qbt_boot`/reset lifecycle, Linux HCI adapter execution, controller/UART/DMA/IBS timing, XNU build, device boot, or flash gates. Full fallback persistence was read in source but is not executed by this fixture. Inputs are synthetic and deterministic, not a replay of the d8 device timeline.

## Reproduce offline

Use WSL Linux Python; Windows Python cannot open `/mnt/e` paths. The commands require explicit source/artifact paths. Save new receipts in a new external directory rather than overwriting historical outputs. No command below invokes adb or fastboot.

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/tests/test-check-bt-d8-inputs.py
python3 scripts/check-bt-d8-inputs.py \
  --repo /mnt/e/hackios/k60-bt \
  --artifact /mnt/e/k60-work/artifacts/bt-d8-tlv
python3 scripts/tests/test-bt-d8-host-timing.py \
  --patch-dir /mnt/e/hackios/k60-bt/patches/xnu \
  --frozen-before /mnt/e/k60-work/artifacts/bt-d8-tlv/frozen-before.txt \
  --work-dir /mnt/e/k60-work/artifacts/bt-d8-host-timing-20261116/reproduce-new
```

The [input checker](../../scripts/check-bt-d8-inputs.py) returns nonzero on missing/malformed or changed reviewed inputs. Its [17 fixtures](../../scripts/tests/test-check-bt-d8-inputs.py) exercise missing inputs/commit, manifest changes/dirty state, frozen mismatch/duplicates, same-size patch changes, invalid names/namespace, application-log membership/order/duplicates and image drift. Fixture profiles are synthetic and are never accepted by the CLI as a substitute for the pinned d8 profile.

Child runtime receipt: [runtime.log](E:/k60-work/artifacts/bt-d8-host-timing-20261116/runtime.log). Lead's independent run retained [extracted source and executable](E:/k60-work/artifacts/bt-d8-host-timing-20261116/lead-review/qbt_core.c). Integration receipts are kept under `E:/k60-work/artifacts/bt-d8-host-timing-20261116/final-review-1815/` with individual command exit codes; a failed command cannot be hidden by the wrapper finishing successfully.

## Next gate

Before d9 or any behavioral change, the Bluetooth owner should extend host evidence to the actual HCI adapter and full NVM fallback boundary, and specify bounded event/timestamp observations that distinguish queued TX, physical RX, parsed event status, matcher completion and attempt identity. Those are separate from report counters. Review what that additional source-bound execution proves before choosing a repair. Retain d8 as a failed NVM diagnostic observation, keep all original artifacts, and do not use its diagnostic eight-step label as functional or main-baseline acceptance.
