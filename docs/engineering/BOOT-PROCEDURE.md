# Boot procedure (the only entry point)

> Iron rule 8: **a boot without a serial log is a blind experiment.** Every
> `fastboot boot` must run with the CDC-ACM console capture attached, and the
> capture must be attached **before** the boot starts.

## Why this page exists

On 2026-11-12 a boot hung in early boot, the console never appeared once, and
nothing was kept - the procedure then relied on "someone remembers to open a
window running `capture-k60-usblog.ps1`", and when that was forgotten the whole
round could only be guessed at. That round's conclusion even started from
speculation like "maybe it cannot find the unixnu partition".

The same evening produced a second shape of the same bug: `flash.sh` started a
capture process of its own, `boot-and-capture.ps1` started another one, **two
PowerShell processes fought over one COM port** and each wrote its own
timestamped directory. The primary criterion read `console.log` from the first
directory, and that file was 0 bytes - so a healthy boot ("Data already
mounted, launchd already reached early boot complete, SpringBoard already
running") was misread as "the kernel died before USB gadget init". The real log
was sitting in the neighbouring directory: 91 KB, 1405 lines.

Conclusion: **a procedure you can forget is not a procedure; something two
processes can write at once is not evidence.** The structure now is one
supervisor, one collector, one evidence directory, and criterion functions that
can be tested offline.

## One command

```bash
bash /mnt/e/hackios/UniXNU-mondrian/scripts/flash.sh /mnt/e/k60-work/usb-a-stage/out/<img> <seconds>
```

When the patch set differs from the last successful boot, gate item S requires
an explicit declaration:

```bash
K60_FORCE_NEW=1 bash /mnt/e/hackios/UniXNU-mondrian/scripts/flash.sh <img> <seconds>
```

`K60_FORCE_NEW=1` is not a bypass: every other item is still checked, the run
just no longer fails for the sole reason that the patch set changed.

The script lives in the repository (`scripts/flash.sh`), not in
`/mnt/e/k60-work/scripts/` - a file outside the repository is never committed,
never reviewed and never seen by a gate, which violates iron rule 1.

## Three roles, no crossing the line

| File | Role | Boundary |
| --- | --- | --- |
| `scripts/flash.sh` | gates + device state + invokes the supervisor | **only calls `boot-and-capture.ps1`; never opens the serial port itself** |
| `scripts/boot-and-capture.ps1` | the only supervisor | contains no `SerialPort`; arms the capture, runs `fastboot boot`, collects |
| `scripts/capture-k60-usblog.ps1` | the only collector | the only process that opens the COM port; holds the named mutex `Local\K60-CDC-ACM-Capture` |
| `scripts/k60-capture-state.ps1` | criterion functions | pure functions, testable offline (`scripts/tests/test-k60-capture-verdict.ps1`) |

Contention is handled explicitly: a second collector that cannot take the mutex
exits with `capture-busy` (rc=3) and writes no second copy of the evidence.

## Order inside flash.sh

1. `porting-gate.py --quick` (docs / porting / patch structure / series fingerprint)
2. `eight-step-gate.py --flash` (items ①-⑦ green + the ⑧ success/failure prediction)
3. `check-boot-procedure.py` (the self-check this page requires)
4. `research-gate.py`
5. device state check → `adb reboot bootloader` when needed, wait for fastboot (150 s)
6. `boot-and-capture.ps1`: start the collector **first** and wait for
   `capture.ready`, **then** `fastboot boot`
7. read the supervisor exit code, print the evidence directory path

## What the evidence directory holds

`E:\k60-work\evidence\usblog-<yyyyMMdd-HHmmss>\`

- `console.log` - raw serial bytes, the only body of evidence
- `capture.json` - the structured criterion: `state`, `complete`, `stopReason`,
  byte count, whether panic / reset markers were seen, when the port appeared
  and was opened
- `capture-events.jsonl` - the event timeline (port-observed / port-opened /
  open-error / read-error / panic-marker / reset-marker / stop-reason)
- `boot.json` - the supervisor's ledger: image path, sha256, whether the capture
  was armed, whether `Booting OKAY` arrived, whether the device dropped back to
  fastboot on its own
- `collector.stdout.log` / `collector.stderr.log`

## The criterion is not "does the file exist"

`k60-capture-state.ps1` sorts the result into seven states, and `complete` is
true only for `captured`:

- `captured` - bytes were captured, clean end
- `captured-truncated` - bytes were captured but the budget ran out or the link
  dropped; **the log is still usable**, only the tail is missing
- `captured-disconnected` - the device dropped back to fastboot and no panic
  marker was seen
- `captured-error` - the collector raised an error but bytes already exist
- `opened-no-data` - the port opened and not one byte arrived
- `port-open-failed` - the port appeared but opening it failed
- `port-not-observed` - the port was never seen

Supervisor exit codes: 0 complete, 1 supervision/boot failure, 2 zero bytes,
3 serial port busy, 4 truncated, 5 the device dropped back to fastboot on its
own. **A 0-byte log is not evidence that "the kernel never ran"** -
`port-not-observed` only says USB gadget enumeration did not succeed, and the
causes run from "the kernel died before gadget init" to "the boot never
happened at all", so it has to be read together with `bootAccepted` in
`boot.json`.

## What the serial console looks like

- the kernel gadget enumerates as `USB\VID_1209&PID_0001` and binds
  `usbser.sys` automatically
- the COM number is **not** in FriendlyName; it can only be found under
  `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` as `\Device\USBSER000`
  (picking by FriendlyName selects the Bluetooth modem COM3/COM4, which is wrong)
- `DtrEnable = $true` is mandatory, otherwise the kernel never drains the
  console ring

## When the console really never appears

Follow the early-boot path; do not guess at UI symptoms:

1. what differs between this boot and the last image that **did** run (kernel
   commits, `board.toml` kernel_args, payload variant, DTB, **firmware volume**)
2. whether that difference added a boot-arg (for example `pong_adreno_start=1` /
   `pong_metal=1`)
3. bisect: `bootimg --fd <known-good FD>` / `--kernel-arg <name>=0`, rolling
   back one variable at a time
4. the firmware volume itself can be the variable: `scripts/extract_fd.py`
   pulls the FD after the shim, before `_FVH`, so the sha256 can be compared

## The unixnu partition: never overwrite it wholesale

`unixnu-root.img`, produced by `scripts/build-k60-root-image.py`, is the
three-window image for a **fresh install**, and its Data window is only a 32 MiB
seed. On the device `/dev/block/sda38` already carries the correct layout and
Data is a real 19.87 GiB volume:

- the sha256 of OS / SystemOS is byte-for-byte identical to the newly built
  image → there is no reason to rewrite it
- once Data is covered by the 7.8 GB image it falls back to the 32 MiB seed,
  which destroys user data

So the partition layout stays as it is, only `boot.img` needs updating, and it
is started from memory with `fastboot boot` - no partition is written.

## Hard constraints

- only `fastboot boot` is allowed. **Never** `fastboot flash` an Android
  partition, **never** touch `persist`
- before every boot confirm `git status --porcelain` is empty (iron rule 2) and
  the `snap-*` tag is pushed (iron rule 7)
- "it looks fine" without a log does not count as an on-device pass at ⑧
- only one collector at a time; never open a second window onto the same port
  by hand
