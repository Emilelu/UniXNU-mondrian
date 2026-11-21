# patches/proposed — offline drafts, not in the series

These are drafts written while no device flight is available. They are
deliberately **not** in `patches/*/series`, not built, and not flown. They fall
in four groups with different rules — the fourth is switched off on purpose:

| Group | Patches | What it changes | How it is carried |
| --- | --- | --- | --- |
| Measurement | `pong-scanout-offer-count.patch`, `pong-metal-client-gap.patch` | counters and printed fields only | **once, together, with the next image** (Lead ruling 2026-11-21, m01230, refined in m01375) |
| Behaviour | `pong-adreno-restart.patch`, `pong-gpu-only-default.patch` | a restart sequence nothing calls, and the default of an existing policy | **not carried** until the owner named below says so; each states its own veto |
| Assertions | `pong-scanout-assert-offsets.patch`, `pong-presenter-assert-offsets.patch` | `static_assert` + `offsetof` only; no structure, no runtime | **safe to adopt at any time**; they cannot change behaviour, only refuse to build a broken layout |
| Dormant | `pong-scanout-v2-layout-asserts.patch` | four `static_assert`s behind `#if PONG_SCANOUT_V2_LAYOUT`, switched off | **not carried**; enabled by the v2 wire decision, not by an image |

No kext is compiled here: this lane may not build (`LANE-CONTRACT-ios27` §2), so
"the patch applies" is the strongest claim available for the code itself. The
assertions are the exception in a different sense — their *text* was reproduced
against the same struct definitions and compiled with a host C++17 compiler, so
the offsets they pin are measured rather than assumed (see the end of this file).

## Group 1: measurement, carried as one flight

* nothing in this group changes a default, a boot argument or a policy;
* each one only adds counters and one printed field, so a flight can read a
  number that the budget in `docs/research/gpu/GPU-27-BUDGET-120FPS.md` needs
  and that neither side has ever printed;
* the field names are the ones `E:/hackios/k60-gates/scripts/judge-gpu27.py`
  already parses (`SCANOUT_VERSION`, `OFFERS`, `CLIENT`), so a single flight
  with these two patches makes three currently `unmeasured` fields measurable.

One flight, both patches, one image, then the numbers decide. Do not land them
one at a time — the point is that `offers`, `dropped` and `client` describe the
same frame stream. The order is fixed, because the judge reads both from one
flight:

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

## Group 2: behaviour, inert until someone asks for it

Both drafts are written because the offline evidence points at them, and both
are held out of any series because they change behaviour rather than report it.

### `pong-adreno-restart.patch`

Edits `drivers/PongAdreno/PongAdrenoCp.cpp` in two segments and touches nothing
else: a restart sequence after a hang, and the hook a caller installs. It does
**not** touch `hardware_init()` — the 27 board already runs that bring-up
sequence in the kernel (`PongAdrenoCp.cpp:213`, one call site at `:372`); what
it has no road back to is the state after a hang.

**Nothing calls `pong_adreno_cp_restart()`.** Until something does, the patch is
inert: it adds two functions, an atomic guard and a bus drain, and changes no
existing path. Whoever grows a recover path in the kit is the caller.

Two costs are stated here rather than discovered later:

* **The four components are rebuilt in place.** A hang poisons ring, CP init,
  submit and IRQ, and none of them can clear that: `NativeAdrenoRing::detach()`
  returns `kIOReturnBusy` once `poisoned_` (`NativeAdrenoRing.cpp:190`),
  `NativeAdrenoSubmit::attach()` refuses a poisoned pair
  (`NativeAdrenoSubmit.cpp:48`), and their addresses are held by the published
  backend (`PongAdrenoCp.cpp:411`), so a replacement would leave the backend
  pointing at a destroyed object. The draft therefore destroys and
  placement-news the four members in place. That is legal only because the
  addresses do not move; it is also the reason this belongs in the module and
  not in the kit.
* **An SMMU fault is not recoverable by this patch.** `NativeAdrenoVm` poisons
  itself on a fault (`NativeAdrenoVm.cpp:101-103`, which also quarantines both
  arenas) and offers no way back, so `submit.attach(&vm,&ring)` returns
  `kIOReturnBadArgument` and the restart stops there. A CP hang recovers; an
  SMMU fault does not. Whoever calls this must have told the two apart first.

### `pong-gpu-only-default.patch`

Edits `patches/xnu/0600-k60-display-composition.patch` itself rather than adding
a patch after it, so the series keeps its order and its numbering; both edits
are line-for-line replacements, so no hunk header in 0600 changes.

It changes a default, not a mechanism. `fGpuOnly` already exists and already
gates CPU composition (`0600:863`); today it starts at 0, so every frame where
the GPU hand-off does not land is composed again on the CPU at 13,183 µs a frame
(usblog-20261119-151837). With this, the board composes on the GPU unless asked
otherwise, and `pong_gpu_only=0` puts it back.

**Display owns the veto.** If the compositor needs the CPU fallback during
bring-up, drop this draft and nothing else in the tree moves.

## Group 3: assertions, adoptable before any flight

Two halves of one idea: the sizes are asserted today, the offsets are not, and a
layout is offsets. Swap two `uint64_t` members and every existing
`static_assert` stays green while both readers silently read the wrong field —
the wire would still be "48 bytes" and still be wrong.

* `pong-scanout-assert-offsets.patch` — `drivers/PongAdreno/PongScanoutWire.h`:
  every offset of the four records, plus the four method codes and the two
  constants. This is the side that defines the wire.
* `pong-presenter-assert-offsets.patch` — `drivers/PongMetal/PongMetalScanout.h`:
  the same facts where the presenter depends on them, so a wire change that
  breaks this presenter breaks **its** build and names **this** file, instead of
  only breaking the header it happens to include.

The two numbers that make this worth a patch rather than a comment are
`offsetof(PongScanoutFrame,reserved)==44` and
`offsetof(PongScanoutDone,reserved)==12`: both are in use
(`PongAdrenoScanout.cpp:149` writes the first as a literal `0`, `:122` treats the
second as a garbage sentinel), and both are exactly where the wire proposal puts
its version if the packaging goes that way. `offsetof(...,address)==8` is the
third: it is the GPU address the copy reads, and nothing asserts it today.

**Nothing here changes behaviour.** If either patch fails to build, the layout
changed under someone; that is the message, not a regression.

### The dormant member: `pong-scanout-v2-layout-asserts.patch`

One patch, both files, and it **does not compile as written — on purpose**. It
adds `#define PONG_SCANOUT_V2_LAYOUT 0` plus four `static_assert`s behind `#if`:
frame 56, `token` at 44 where `reserved` used to be, `evict` at 48, `target` at
52. The moment display signs the v2 semantics and a dbuf exists, flip the 0 to 1
and the layout is pinned by the compiler before anyone builds a kext.

Until then those four numbers describe fields that do not exist. An assertion
about a field that is not there is a false fact, which is exactly why it is
switched off rather than commented out: the numbers live in code that the
compiler will read the day it is enabled, not in a paragraph someone has to
remember.

It applies **after** `pong-scanout-assert-offsets.patch` — that patch brings
`<stddef.h>`, without which `offsetof` is not declared. `git apply --check` on a
tree with the offset patch already in place passes; on a clean tree it does not,
and that is expected, not a defect. The numbers themselves were checked the same
way as the others: a host C++17 compiler against the intended struct shape
(`E:/k60-work/scratch/prop/v2_layout_probe.cpp`), so 44/48/52/56 are measured,
not assumed.

Offline verification is stronger than "it applies": the assertion block was
reproduced against the same struct definitions with a host C++17 compiler and
compiles clean, so the offsets are correct rather than merely plausible (see
"Verification done offline").

## What each patch adds

| Patch | File | Adds |
| --- | --- | --- |
| `pong-scanout-offer-count.patch` | `drivers/PongAdreno/PongAdrenoScanout.cpp` | counters `offered`/`dropped` at the delivery gate, and one periodic line carrying `scanout version=`, `offers=`, `dropped=`; the print buffer grows 260 → 384 bytes (the widest value of the new format is 288) and a truncated line has its newline repaired, so a future field cannot glue this record onto the next one |
| `pong-metal-client-gap.patch` | `drivers/PongMetal/PongMetalScanout.h` | the arrival interval between two frames handed over by the client, printed as `client=<us> us` on the existing stage line |
| `pong-adreno-restart.patch` | `drivers/PongAdreno/PongAdrenoCp.cpp` | `gbif_drain()`, `restart_sequence()`, and `pong_adreno_cp_set_restart()` / `pong_adreno_cp_restart()`; no caller, no change to any existing path |
| `pong-gpu-only-default.patch` | `patches/xnu/0600-k60-display-composition.patch` | `gpuOnly` starts at 1 instead of 0, and the field comment says so |
| `pong-scanout-assert-offsets.patch` | `drivers/PongAdreno/PongScanoutWire.h` | `#include <stddef.h>` and four `static_assert`s: every field offset of Mode/Wait/Frame/Done, the four method codes, `PongScanoutVersion`, `PongScanoutBgra` |
| `pong-presenter-assert-offsets.patch` | `drivers/PongMetal/PongMetalScanout.h` | the presenter's own three `static_assert`s: the reply length it demands, the reserved word it refuses, the protocol numbers it switches on |
| `pong-scanout-v2-layout-asserts.patch` | both headers | four `static_assert`s behind `#if PONG_SCANOUT_V2_LAYOUT`, currently 0: frame 56, `token`@44, `evict`@48, `target`@52 |

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
| `CP restart …` on `PONG SCANOUT:` | `PONG SCANOUT: CP restart: ME_INIT sequence=… status=0x…`, `CP restart done`, `CP restart: register access failed` | absent in a healthy flight; present in pairs, one start and one outcome | `ME_INIT` with a non-zero status is the restart failing at its second step, before any ring exists again; `register access failed` means a read or write itself failed, which is the case the SMMU-fault note above covers |

Two notes that keep these numbers honest:

* the first frame of a flight prints `client=0` because there is no previous
  arrival; a zero there is "no sample", not "instant";
* `offers`/`dropped` are counted under `scanout_gate`, so they are consistent
  with the per-frame line printed from the same lock.

## What these patches do not add

`abi=kernel=<v>/<sizeof> client=<v>` lives in the user-client open path and
belongs to another tree; `gpuonly=` is printed by nothing today — the
`pong-gpu-only-default.patch` draft changes the policy but does not print it
either. Until those print, the judge reports them as `unmeasured` rather than
passed — see `docs/research/gpu/GPU-27-JUDGE-DRAFT.md` §2.

## What the targets look like on the 27 tree

`drivers/PongAdreno/PongAdrenoScanout.cpp` and `drivers/PongMetal/PongMetalScanout.h`
are byte-identical on this tree and on `E:/hackios/xnekom-ios27`
(`feat/xnu27-data-gate`), so the two measurement drafts pass `git apply --check`
there today and need no rebase. `drivers/PongAdreno/PongAdrenoCp.cpp` and
`patches/xnu/0600-k60-display-composition.patch` also pass `git apply --check`
there at the time of writing. The format strings the judge depends on, with
their 27-side line numbers, the shape they take after the drafts and the buffer
accounting, are in `docs/research/gpu/GPU-27-LOG-FORMATS.md`. "Identical today"
is not a contract: re-run the `diff` and the `git apply --check` calls before
carrying anything.

## Verification done offline

```
cd E:/hackios/k60-gpu-27
git apply --check patches/proposed/pong-scanout-offer-count.patch
git apply --check patches/proposed/pong-metal-client-gap.patch
git apply --check patches/proposed/pong-adreno-restart.patch
git apply --check patches/proposed/pong-gpu-only-default.patch
git apply --check patches/proposed/pong-scanout-assert-offsets.patch
git apply --check patches/proposed/pong-presenter-assert-offsets.patch
# The dormant v2 member needs the offset patch first; check it on such a tree.
git apply --check patches/proposed/pong-scanout-v2-layout-asserts.patch
```

The first six pass against `feat/gpu-27` at the commit that added this directory,
and all six pass against `E:/hackios/xnekom-ios27` today. The seventh is the
dormant one: it is checked on a tree where the offset patch is already applied
(`E:/k60-work/scratch/prop/v2_assert_patch.py` does exactly that, in a scratch
repo, and prints the check result). None is compiled — with one
exception, the assertions: their text was reproduced against the same struct
definitions and built with a host `g++ -std=c++17 -Wall -Wextra`
(`E:/k60-work/scratch/prop/wire_assert_probe.cpp`), so the offsets are checked
by a compiler, not by reading. That probe is not a substitute for building the
kext; it only proves the numbers in the assertions are the real ones.

## Rollback

Every patch is additive and independent: reverting one restores the previous
text exactly. The measurement drafts have no caller reading their fields; the
restart draft has no caller at all; the policy draft is one initializer and one
comment.
