# F2 flight plan after the INVALID run

Status: `5c060f27…d817a6b6` was booted at 09:16 on 2026-11-21. Console was 0 bytes, the Windows device
node never appeared (`port-not-observed`), and the phone did not return to fastboot within ten minutes.
That is INVALID by `F2-PREDICTION.md`, not a failure: a 0-byte capture cannot separate "died before the
gadget enumerated" from "ran but never enumerated".

The device is now absent from USB entirely, so the next step needs a physical power-cycle first.

## When the phone is back: alternate two images, not one

The prediction already committed to re-running the same image once. That alone still cannot tell apart
"our 27 kernel is broken" from "the capture chain broke", because both produce 0 bytes. So each boot
alternates a control:

| # | image | what it answers |
| --- | --- | --- |
| 1 | `e3d651ed…` (16.6.1, reaches SpringBoard) | is the supervisor still able to capture at all |
| 2 | `5c060f27…` (27 stage-0) | does the 27 image produce anything |

Interpretation, fixed before either boot:

- 1 silent **and** 2 silent ⇒ the capture chain is broken; stop judging 27 by console until it is fixed.
- 1 alive **and** 2 silent ⇒ the 27 image stops before the gadget enumerates. That is a real 27 defect,
  and the search moves from prelink residue to `arm_init` and the fileset entry path.
- 1 alive **and** 2 alive ⇒ read the log: `_unixnu_fileset_unmapped` return addresses turn the 205
  recorded items into a measured list.

## Why "before the gadget" is the expected place for a silent stop

K60's only console is USB CDC-ACM, brought up late in `bsd_init` by the usb-cdc-mainline gadget. Every
failure between the loader hand-off and that gadget — `arm_init`, pmap geometry, the 13 items reachable
from `code_signing_init()` — is silent by construction. That is why a 0-byte result must not be read as
"the kernel never started".

## Constraints unchanged

`fastboot boot` only, never flash, never touch `/dev/block/sda38`. One boot at a time, single writer,
supervisor armed before the hand-off.

## The gadget is present in the 27 kernel too

llvm-nm-18 counts 87 CDC/ACM/console-related symbols in the 27 kernel against 170 in the 16.6.1 kernel
that reaches SpringBoard. Fewer is expected (the 27 tree links fewer drivers), but the gadget is not
absent, so a missing console driver is not by itself the explanation for a 0-byte capture.
