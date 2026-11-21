# patches/proposed — offline drafts, not in the series

These are drafts that answer a question with a measurement, written while no
device flight is available. They are deliberately **not** in `patches/*/series`,
not built, and not flown:

* nothing here changes a default, a boot argument or a policy;
* each one only adds counters and one printed field, so a flight can read a
  number that the budget in `docs/research/gpu/GPU-27-BUDGET-120FPS.md` needs
  and that neither side has ever printed;
* the field names are the ones `E:/hackios/k60-gates/scripts/judge-gpu27.py`
  already parses (`SCANOUT_VERSION`, `OFFERS`, `CLIENT` at lines 52–56 of that
  script), so a single flight with these two patches makes three currently
  `unmeasured` fields measurable.

They are meant to be carried **once, together with the next image**
(Lead ruling 2026-11-21, m01230, refined in m01375): one flight, both patches,
one image, then the numbers decide. Do not land them one at a time — the point
is that `offers`, `dropped` and `client` describe the same frame stream.

The order is fixed, because the second patch edits a line the first one leaves
alone but the judge reads both from one flight:

1. `pong-scanout-offer-count.patch` — gives `scanout version=`, `offers=`, `dropped=`
2. `pong-metal-client-gap.patch` — gives `client=<us> us` on the stage line

The image to wait for is **the one that carries the new firmware volume and a
fileset kernel the boot accepts** — not the current image, which stops on the
menu (LANE-CONTRACT-ios27 §4). Carrying these two patches on an image that never
reaches a composed frame would produce no line at all, and a flight with no line
is `unmeasured`, not evidence.

Until they are carried, `judge-gpu27.py` reports `scanout version`, `offers`
and `client` as `unmeasured` rather than failing them: no observation is never
an observation of something bad.

## What the two target files look like on the 27 tree

Both drafts edit `drivers/PongAdreno/PongAdrenoScanout.cpp` and
`drivers/PongMetal/PongMetalScanout.h`. Those two files are byte-identical on
this tree and on `E:/hackios/xnekom-ios27` (`feat/xnu27-data-gate`), so both
drafts pass `git apply --check` there today and need no rebase. The format
strings the judge depends on, with their 27-side line numbers, the shape they
take after the drafts and the buffer accounting, are in
`docs/research/gpu/GPU-27-LOG-FORMATS.md`. "Identical today" is not a contract:
re-run the `diff` and the two `git apply --check` calls before carrying them.

## Verification done offline

```
cd E:/hackios/k60-gpu-27
git apply --check patches/proposed/pong-scanout-offer-count.patch
git apply --check patches/proposed/pong-metal-client-gap.patch
```

Both pass against `feat/gpu-27` at the commit that added this directory.
Neither file has been compiled: this lane may not build (`LANE-CONTRACT-ios27`
§2), so "applies" is the strongest offline claim, and it is the only one made
here.

## What each patch adds

| Patch | File | Adds |
| --- | --- | --- |
| `pong-scanout-offer-count.patch` | `drivers/PongAdreno/PongAdrenoScanout.cpp` | counters `offered`/`dropped` at the delivery gate, and one periodic line carrying `scanout version=`, `offers=`, `dropped=`; the print buffer grows 260 → 384 bytes (the widest value of the new format is 288) and a truncated line has its newline repaired, so a future field cannot glue this record onto the next one |
| `pong-metal-client-gap.patch` | `drivers/PongMetal/PongMetalScanout.h` | the arrival interval between two frames handed over by the client, printed as `client=<us> us` on the existing stage line |

The stage line keeps its original shape with one optional field inserted, and
`judge-gpu27.py` accepts both shapes (`client=` present or absent). That was a
real bug caught offline: the draft first put `client=` between `done=… us` and
`imports=`, which the judge's `STAGE` regex did not allow, so every stage line
of an instrumented flight would have been unparseable and a stage-only flight
would have been judged INVALID — instrumentation that blinds the parser (P-290
family). The regex now takes the optional group, and the fourth test fixture
(`gpu27-instrumented-drops-and-gap.log`) holds the drafts' exact line shapes.

## Field contract: which log line, and what counts as normal

Every value below is read from the console log of a `sheng-gpu-trace=1` flight.
"Normal" is stated against the 120 Hz budget of 8,333 µs and against the two
real flights the budget was built on (usblog-20261119-151837 for the
compositor, usblog-20261119-173454 for the copy bench).

| Field | Line it appears on | Normal | What a bad value means |
| --- | --- | --- | --- |
| `scanout version=<n>` | `PONG SCANOUT: scanout version=1 offers=… dropped=… frame=…` | `1` before the wire proposal lands, `2` after both halves move together | kernel and presenter disagreeing is exactly the state that returns `kIOReturnBadArgument` from `wait`, after which the presenter logs `scanout frame wait stopped` and the CPU compositor takes over. A `2` here with a version-1 presenter is that failure, named. |
| `offers=<n>` | same line | grows at the panel rate: ≈120 per second at 120 Hz, ≈20 per second when the CPU compositor is producing the frames | a rate far below the panel rate means the compositor is not producing frames at all (the screen is not the GPU's fault); a rate far above it means the same frame is being offered repeatedly |
| `dropped=<n>` | same line | 0 in a steady GPU-only flight; the counter exists so this can be checked rather than assumed | `dropped/offers > 0.05` means frames are being lost at the handover, not in the copy: either the render server was not blocked in `wait`, or the previous offer had not retired (there is one pending slot). In that state a faster copy cannot raise the frame rate, which is the whole point of measuring it. |
| `client=<us> us` | `scanout frames=… last frame: wait=… copy=… done=… client=… us; imports=…` | ≤ 8,333 µs at 120 Hz. `client` is the interval between two frames reaching the render server, so it is ≥ that frame's `copy+done` and ≥ the client's own encode time | `client > 8,333` with `gpu` in budget means the client is the limit, not the GPU. Before this patch the same interval could only be inferred by subtracting `copy+done` from `wait`, and every flight so far treated `wait` as if it were the interval. |

Two notes that keep these numbers honest:

* the first frame of a flight prints `client=0` because there is no previous
  arrival; a zero there is "no sample", not "instant";
* `offers`/`dropped` are counted under `scanout_gate`, so they are consistent
  with the per-frame line printed from the same lock.

## What these patches do not add

`gpuonly=` (the composition policy) lives in the XNU patch set, and
`abi=kernel=<v>/<sizeof> client=<v>` lives in the user-client open path; both
belong to other trees and other owners. Until those print, the judge reports
them as `unmeasured` rather than passed — see
`docs/research/gpu/GPU-27-JUDGE-DRAFT.md` §2.

## Rollback

Both patches are additive and independent: reverting either one restores the
previous log text exactly, and no caller reads these fields.
