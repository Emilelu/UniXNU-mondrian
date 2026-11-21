# Draft inventory: one row per patch, ticked before an image goes out

Every draft in this directory, with the thing that decides **when** it travels
and the thing it **depends on**. The point is not bookkeeping: a draft carried
alone can prove the wrong thing (0006 alone, without 0001, would document a wire
that no flight can explain), and a draft forgotten is a flight that answers one
question less than it cost.

Rules for using this page:

* a row marked *next image* travels with the first image that boots into a
  composed frame — not with the current one, which stops on the menu
  (`LANE-CONTRACT-ios27` §4);
* a row marked *milestone* waits for the named thing, and the named thing has to
  be **decidable** — a manifest field, a log line, or a gate turning green.
  "until the GPU works" is not a milestone and does not belong here;
* a row that is skipped on a given image says why, in the flight card. An
  unticked row with no reason is the failure mode this page exists to prevent.

| 本线编号 | File | Trigger | Depends on | series 编号 |
| --- | --- | --- | --- | --- |
| 0001 | `pong-scanout-offer-count.patch` | next image | nothing; first in the measurement stack | — (no series yet) |
| 0002 | `pong-metal-client-gap.patch` | next image, same flight as 0001 | 0001 in the same tree: independent files, but the two numbers describe one frame stream and are read from one flight | — (no series yet) |
| 0003 | `pong-scanout-frame-timestamp.patch` | next image, after 0002 | **0002 stacked** — both edit the same report block, so this diff is written against a tree that already has 0002; applied without it, it does not apply | — (no series yet) |
| 0004 | `pong-adreno-restart.patch` | milestone: a hang flight exists and someone owns the caller (or a CP hang reproduces with `DeviceLost` in the log) | nothing in this directory; costs in `README.md` (in-place rebuild; an SMMU fault is not recoverable) | — (no series yet) |
| 0005 | `pong-gpu-only-default.patch` | milestone: display's sign-off on the default (it owns the veto) | nothing; edits `patches/xnu/0600-k60-display-composition.patch` in place | — (takes none of its own; it edits 0600) |
| 0006 | `pong-scanout-assert-offsets.patch` | safe at any time — but must precede 0008 | nothing | — (one is assigned when it joins a series) |
| 0007 | `pong-presenter-assert-offsets.patch` | safe at any time | nothing; the presenter half of 0006 | — (one is assigned when it joins a series) |
| 0008 | `pong-scanout-v2-layout-asserts.patch` | milestone: wire v2 decided (`flip condition` in `docs/research/gpu/GPU-27-SCANOUT-WIRE-PROPOSAL.md` §2.5) **and** 0006 already in series | **0006** — it brings `<stddef.h>`; without it `offsetof` is not declared | — (no series yet) |
| — | `INVENTORY.md` | this page; ticked on the flight card | — | — |

The third numbering layer is why this table exists at all: a **本线编号** counts
drafts inside this directory, a **series 编号** is the `05xx`/`06xx` a patch takes
when it joins `patches/*/series`, and a **P-2xx** is a pitfall number and is
globally unique. Mixing them makes "is this patch actually in the build?" a
question nobody can answer, so each layer gets its own column and none of them
borrows the other's shape.

## What each row buys, in one line

| 本线编号 | The number the flight gains | Where the judge reads it |
| --- | --- | --- |
| 0001 | `scanout version`, `offers`, `dropped` | `judge-gpu27.py` — `SCANOUT_VERSION`, `OFFERS` |
| 0002 | `client=<us> us` | `judge-gpu27.py` — `CLIENT`, `STAGE` optional group |
| 0003 | `at=<sec>.<ms>`, so rule 5 can place a window on a clock | `check-gpu27-zero-copy.py` — `AT`, `judge_window()` |
| 0004 | `PONG SCANOUT: CP restart …` lines | read by hand; no gate yet (P-290: no flight, no criterion) |
| 0005 | `gpuonly=` — but the field is still unprinted | nothing reads it yet; `judge-gpu27.py` keeps reporting it `unmeasured` |
| 0006 | nothing at flight time: it refuses to build a moved layout | the compiler |
| 0007 | same, from the presenter's side | the compiler |
| 0008 | same, once the flip happens | the compiler, plus `check-gpu27-flip-asserts.py` (dormant until it is in series) |

## The two rows that are easy to get wrong

* **0003 without 0002.** 0003 is a stack, not a standalone change: its hunk
  context is the line 0002 produced, so on a tree without 0002 it does not
  apply. That is the dependency talking, the same way 0008 refuses a tree
  without 0006. Read the dependency column, not just the file name.
* **0008 without 0006.** `offsetof` needs `<stddef.h>`, which 0006 brings. A
  build error here is the ordering talking, not a broken assertion.

## Verification available offline (no device, no build)

```sh
# every draft applies to a clean lane tree, or applies only after its dependency
cd E:/hackios/k60-gpu-27 && git apply --check patches/proposed/<file>.patch

# the measurement stack, in order, on a throwaway clone of the two headers
git apply patches/proposed/pong-scanout-offer-count.patch   # 0001
git apply patches/proposed/pong-metal-client-gap.patch       # 0002
git apply patches/proposed/pong-scanout-frame-timestamp.patch # 0003 — needs 0002

# the gate and its counter-examples (12 cases, four of them about the window)
python3 E:/hackios/k60-gates/scripts/tests/test-check-gpu27-zero-copy.py
```

Last checked: 2026-11-21. The drafts are not in any series, not built, not
flown; this page is the checklist for the flight that changes that.

## What was actually run today (not "should work")

| Check | Result |
| --- | --- |
| 0001 → 0002 → 0003 applied in order on a throwaway copy of the two headers | all three exit 0; the tree then contains `lastGap=0;`, `lastAt=0;`, `if(stamped(t1))lastAt=absoluteUs(t1);` and `sum=%llu us at=%llu.%03llu` |
| 0003 alone on a tree without 0002 | exit 1 (`patch does not apply`) — the dependency, verified rather than assumed |
| 0003 on the 27 tree, whose header is byte-identical to this one | `git apply --check` exit 0 |
| C landed as `988f7ee8` on top of `7071fd9e` | `TESTS OK: 12 cases`; the three new fixtures are in the same commit; the old `direct` case now exits 2 by design |
| C (`C-zero-copy-window.patch`, kept in `E:/k60-work/scratch/gpu27-batch/`) re-cut against the tree as it stands after Lead's `7071fd9e` (five files landed, nineteen already present) | applies exit 0; `TESTS OK: 12 cases`; the pre-existing `direct` case now exits 2 and says why |
| D landed as `4a6e7712` (plus one host-path fix inside the same commit) | the tool and its 14 fixtures are in `k60-gates/scripts`; Lead's fix rewrites `/mnt/e/…` only when `os.name == "nt"`, because my `rebuild()` translated the path on POSIX too and the helper then looked for `E:/hackios/…` under the WSL cwd (P-227 family) |
| the post-flip judge run on **both** hosts after that fix, from a scratch copy of the landed files | `TESTS OK: 11 cases (holds, still v1, no version field, header half, pre-flip, missing log, empty flight, and each of the three paths left out)` — once under MSYS python 3.14, once under WSL python 3.12 |
| the same test's empty-flight case, read for what it writes | it creates `postflip-v2-empty.log` **inside** the mirrored fixtures and deletes it in a `finally`; a case killed in between leaves a stray file that `sync-device-input.py` reports as unsynced (iron-5). `E` landed as `144b0191` (temp-dir fixture; both hosts re-verified): the log is built under `tempfile.mkdtemp()`, both hosts still `TESTS OK: 11 cases`, and no stray `.log` remains |
| the zero-copy gate with rule 5, patched copy, 12 counter-examples | `TESTS OK: 12 cases`, and by hand: `direct-at-ok` 0 (`380 frames in 3040 ms (125/s over 3040 ms)`), `direct-at-reversed` 1 (`time went backwards`), `direct-at-short` 2 (`span 1120 ms, rule 5 needs 3000 ms`), untouched `direct` 2 (`none of the 10 direct stage line(s) carries an at=… stamp`) |
