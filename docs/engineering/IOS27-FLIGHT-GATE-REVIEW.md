# Review: the flight gate against the storage line

Scope: `docs/engineering/IOS27-FLIGHT-BLOCKERS.toml` and
`scripts/check-ios27-artifacts.py --flight-ready` on main at 3c1a7b27 (the
gate landed in d97884c9). This page reviews what the gate proves, what the two
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

The gate prints the distinct column and the ledger calls it references. The
round-17d line in the ledger reads "28 bundles / 384 unresolved references, 29
bundles / 2262 items / 2688 sites": 384 is the distinct-target count for that
build, 2262 is the distinct-site count, and 2688 is the reference count, so the
last two labels are the wrong way round. `flight_ready()` then prints
`384 owner-target references have no address` (scripts/check-ios27-artifacts.py:355-357).

This is not a cosmetic bug. "650 references" and "133 symbols" lead to different
questions: the first asks which sites execute, the second asks which symbols the
map could not name. Both numbers are worth printing; only one of them is
currently in the ledger.

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
independent of the symbol question, and it deserves its own line in the
evidence field rather than being folded into a count.

## Recommendations

1. Rename `missing_refs`/`stubbed_refs` or print both the distinct and the
   total counts; state which one the ledger quotes.
2. Fix the round-17d wording: 384 symbols, 2262 sites, 2688 references.
3. Add the storage blocker in the same change that flips
   `CONFIG_XNU_NATIVE_UFS=y`, not before -- an open entry now would block F2
   for a line that is deliberately off. The entry should name
   `scripts/check-xnu27-source-storage.py` and `scripts/check-xnu27-storage-link.py`
   as its evidence, and say that `CONFIG_XNU_OWNER_DATA_MOUNT=y` requires the
   whole chain in [IOS27.md](IOS27.md) section 5.9.
4. If route D is selected, add a second entry for the parent-binding order,
   with the `SourceStorage.cpp` line numbers above and the scratch replay as
   its evidence, and leave it open until a board run shows the class resolving.
5. Keep the gate's conservative refusal on any stub. Per-site reachability is
   not something the current report can prove, and a gate that guesses would be
   worse than one that refuses.

## Verdict

The gate is correctly conservative about what it can see, and its two open
blockers are real. Its counts are distinct addresses labelled as references, and
its blind spot is the whole storage line: at F2 that is the right choice, at F3
it would let a storage-less image pass. The fixes above are small and belong
with the F3 switch, not before it.
