# Review: the flight gate against the storage line

Scope: `docs/engineering/IOS27-FLIGHT-BLOCKERS.toml` and
`scripts/check-ios27-artifacts.py --flight-ready` on main at 2aea3759 (the
gate landed in d97884c9; the counting fix is 2aea3759). This page reviews what the gate proves, what the two
open blockers actually count, and where the storage line has no entry at all.
No edit was made to either file.

## What the gate proves

The structural half checks the kernel Mach-O header, the payload transform and
the boot image. The flight half adds two things: the prelink map has no
unresolved owner targets, and every ledger entry is closed. The ledger's own
header states the rule:

> A structural pass is not a flight gate: `boot.img` can be byte-exact, the ADT
> pinned and the payload the declared transform of the kernel, and the image
> still cannot boot.

Both open entries are real defects, and neither is a storage criterion. A grep
for `storage`, `UFS` or `NativeUfs` in the ledger returns nothing, and the
same grep over the gate returns nothing:

    docs/engineering/IOS27-FLIGHT-BLOCKERS.toml: no match
    scripts/check-ios27-artifacts.py: no match

## The two counts are different numbers

`prelink_state()` (scripts/check-ios27-artifacts.py:187-211) sums
`len(value)` over the report's per-bundle maps. Each value is a map of address
to count, so `len` is the number of distinct addresses, not the number of
references. For the 44518998961 report:

| quantity | distinct | references |
| --- | --- | --- |
| missing owner targets | 133 | 650 |
| sites on the panic stub | 946 | 2688 |

The gate used to print the distinct column under the name "references", and the
round-17d line read "28 bundles / 384 unresolved references, 29 bundles / 2262
items / 2688 sites". Main fixed both in 2aea3759: the ledger now names missing =
28 bundles / 384 items / 133 distinct addresses / 650 reference sites and
stubbed = 29 bundles / 2262 items / 946 distinct functions / 2688 reference
sites, and `flight_ready()` prints items. The lesson is P-281: a counter is
named after what is summed, not after what the reader expects.

That still matters when reading a report. "650 references" and "133 addresses"
answer different questions: the first asks how often the map refers to the
target, the second asks which symbols it could not name. The gate now prints
the item count, which is neither of those; the ledger carries all three.

## The gate cannot see the storage line

The 27 defconfig keeps `CONFIG_XNU_NATIVE_UFS=n`
(configs/mondrian_ios27_defconfig:20), so at F2 the gate is right to ignore
storage: the expected result is a root-mount panic, and requiring a mounted root
would contradict the stage's own criterion. At F3 the same silence becomes a
hole. An image in which:

- `NativeUfs` is not in `components.include` (board.toml:360),
- the builder links `build/sheng-ufs/libPongUfs.a` instead of the archive the
  Linux recipe produces, or
- the driver is linked but no `KernelConfigTables` entry matches the `ufshc`
  node,

passes every check the gate makes, because none of those facts is in the
artifact the gate reads. The three gaps and the missing `IONameMatch` note are
already reported by `scripts/check-xnu27-source-storage.py`; the link half is
reported by `scripts/check-xnu27-storage-link.py` (11 storage imports still
undefined). The gate does not call either.

Route D adds a second storage claim the ledger does not carry: the deferred
metaclass resolves its parent only after `com.apple.iokit.IOStorageFamily` has
loaded (`UniXNU-sheng/package/SourceStorage.cpp:270-278`), and the constructor
order that makes that safe (`:287-292`) has only been measured in a scratch
replay, not on the board.

## What the prelink blocker should say next

The prelink entry's `why_open` already says counts alone do not settle
reachability and that the arm64 prelink step may not be the right instrument.
[IOS27-F1-PRELINK-CLOSURE.md](IOS27-F1-PRELINK-CLOSURE.md) supplies the
missing half: the pinned input's `com.apple.kernel` has `nsyms 0` and empty
prelink segments, so a symbol-level resolver cannot name any of the 133
targets. Until the input changes, the 946 sites are not "possibly dead"; they
are the only outcome the instrument can produce.

The same run finds one target, `0xfffffff007044478`, that is still in the
input `__TEXT` and in no output segment. That is a translation defect
independent of the symbol question, so it is recorded in
[IOS27.md](IOS27.md) under "The one target the prelink did not move" and
asserted by `scripts/check-ios27-prelink-closure.py --require-translated`
instead of being folded into this ledger.

## Recommendations

1. Resolved in 2aea3759: the ledger now names items, distinct addresses and
   reference sites separately, and the gate prints items. The lesson is P-281.
2. Resolved in 2aea3759: the round-17d line now reads 384 items / 133 distinct
   addresses / 650 reference sites.
3. Do not add a storage entry to this ledger. When F3 flips
   `CONFIG_XNU_NATIVE_UFS=y`, attach the storage checks as an independent
   preflight instead: the source-storage gaps
   (`scripts/check-xnu27-source-storage.py`), the link imports
   (`scripts/check-xnu27-storage-link.py`) and the entry assertion
   (`scripts/check-ios27-storage-vtable.py --require-entry`). Its closing
   condition is three checks in one run: the F3 switch is on, the prelink
   reports zero untranslated targets (`--require-translated`), and the 190-slot
   entry assertion passes on the built collection.
4. If route D is selected, add a second entry for the parent-binding order,
   with the `SourceStorage.cpp` line numbers above and the scratch replay as
   its evidence, and leave it open until a board run shows the class resolving.
5. Keep the gate's conservative refusal on any stub. Per-site reachability is
   not something the current report can prove, and a gate that guesses would be
   worse than one that refuses.

## Verdict

The gate is correctly conservative about what it can see, and its two open
blockers are real. The counting is fixed in 2aea3759. Its blind spot is the
whole storage line: at F2 that is the right choice, at F3 it would let a
storage-less image pass, so storage gets its own preflight when the switch
flips rather than a line in this ledger.
