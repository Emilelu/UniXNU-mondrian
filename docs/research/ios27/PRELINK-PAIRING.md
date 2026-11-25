# Prelink pairing checklist: 19 unpinned addresses

`kernel.json` (build 19, kernel `5ce4965ff4ab`) lists **94 unpinned owner-target
items in 21 bundles**, which collapse to **19 distinct addresses**. All 19 are
covered by a segment, so none can fault on the first read; the risk is different
and worse to notice: `rebind()` in `fileset_segmented.py` leaves the original
target in place when it has no pairing, so a wrong pointer stays wrong and silent
until something dereferences it.

`scripts/check-prelink-hazards.py` now enumerates them and refuses to pass until
each one has a `[[pairing]]` entry in `docs/engineering/IOS27-PRELINK-ALLOWLIST.toml`
with a target name, a reason, and a reviewer.

## Why the reference cannot name them

The pinned 24A446 `kernelcache` has `LC_SYMTAB nsyms 0` and its prelink segments
are empty, so there is no symbol name to look up. The LTO reference we build
(`71d351ce`, 6,102 globals) names *our* code only. Pairing therefore cannot be
done by lookup; it has to be established per address.

## What we do know, measured

The kernelcache's `__DATA_CONST` does hold the objects: reading the qword at each
target gives a **chained-fixup encoding**, not a plain pointer
(`0x001000000478d818` at `0xfffffff007e89b80`, `0x02c0000004832e68` at
`0xfffffff007e8a9e0`), and consecutive targets `0xfffffff007e89b80..c0` are one
run of adjacent slots. So the objects are there and a decoder can recover what
they point at.

Note the multiplicity: six addresses in `0xfffffff007e89b80..0xfffffff007e8a9e0`
are referenced by 5 to 14 bundles each, i.e. they are shared kernel-side globals
(the classic shape of a base-class metaclass or a shared table), while the other
thirteen are referenced by one to four bundles.

## Method, in order of preference

1. **Decode the fixup** with the project's own decoder (`LC_DYLD_CHAINED_FIXUPS`,
   pointer format 8) against the pinned kernelcache: a rebase target that lands in
   `__TEXT_EXEC` names a function, one that lands on ASCII names a class. This is
   mechanical and should resolve most rows.
2. **Bundle-local reasoning** for the rest: a bundle's own class list
   (`OSMetaClass` statics in its `__DATA`) bounds which classes it can reference;
   bt's storage pass already did this for the 6 `IOStorageFamily` rows and found
   all of them to be `gMetaClass` class pointers with 0 function addresses.
3. **Bind by hand** where neither works, writing the evidence into `reason` --
   never "should be fine".

## The 19 rows

| address | bundles | note |
| --- | --- | --- |
| `0xfffffff007044478` | AppleARMWatchdogTimer | in `__TEXT`-adjacent range, may be a function-shaped target |
| `0xfffffff007e52c20` | AppleARMPlatform | |
| `0xfffffff007e5a7f0` | IOSurface | |
| `0xfffffff007e5a7f8` | IOHIDFamily, IOSurface | adjacent to the row above |
| `0xfffffff007e5a880` | AppleARMPlatform | |
| `0xfffffff007e87df8` | IOHIDFamily, IOReportFamily, IOStorageFamily, IOSurface | |
| `0xfffffff007e89b80` | 12 bundles | shared global |
| `0xfffffff007e89b98` | 9 bundles | shared global, adjacent |
| `0xfffffff007e89ba0` | 14 bundles | shared global, adjacent |
| `0xfffffff007e89ba8` | 9 bundles | shared global, adjacent |
| `0xfffffff007e89bb8` | 11 bundles | shared global, adjacent |
| `0xfffffff007e89bc0` | 5 bundles | shared global, adjacent |
| `0xfffffff007e8a9e0` | 13 bundles | shared global |
| `0xfffffff00b70c680` | apfs | |
| `0xfffffff00b72fce8` | IOHIDFamily | |
| `0xfffffff00b739538` | sandbox | |
| `0xfffffff00b792378` | AppleARMPlatform, IOAVFamily, IOHDCPFamily | |
| `0xfffffff00b792640` | ApplePMGR, IOAVFamily, IOHDCPFamily | |
| `0xfffffff00b794680` | AppleARMPlatform, AppleARMWatchdogTimer | |

None is reviewed yet. The blocker `prelink-map-unresolved` stays open until the
table is filled and the 203 stubbed call sites have been shown unreachable.

## What the decoder actually found (2026-11-21)

`scripts/decode-kext-target.py` reads the fixup entry stored in each slot. Two
corrections to the earlier guess, both from running it:

* the fixups payload starts at the load command's `dataoff`, not at the load
  command itself, and `dyld_chained_starts_in_segment` keeps `page_count` at
  `+20` -- reading `+6` gave `imports_count = 1_163_157_343`, which is how the
  first attempt "decoded" nonsense;
* the entries here are **authenticated rebases** (`auth = 1`), so the target is a
  32-bit offset from the image base, not the 43-bit field the plain-rebase layout
  uses.

Decoded so far, with the collection base `0xfffffff007004000`:

| slot | entry | decoded |
| --- | --- | --- |
| `0xfffffff007e89b80` | `0x001000000478d818` | auth-rebase `+0x478d818` -> `0xfffffff00b791818` in `__DATA` |
| `0xfffffff007e8a9e0` | `0x02c0000004832e68` | auth-rebase `+0x4832e68` -> `0xfffffff00b836e68` in `__DATA` |

Two consequences for the checklist:

1. these six shared slots point into the kernel's own `__DATA`, i.e. they are
   references to objects our kernel also builds -- the pairing target exists, it
   is the name that is missing;
2. `0xfffffff007044478` sits in `__PRELINK_TEXT`, a segment with no chained-fixup
   info at all, so that row needs a different method (it is not a data rebase).

`imports_count` in the pinned kernelcache is **0**: there are no bind entries, so
no import names can be recovered from this file. Naming therefore has to come from
the object the slot points at, which is the next step.

## Why the names cannot come out of this artifact

Four measurements on `/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed`
(77,987,840 B, root `MH_FILESET` with 318 load commands and 305 members):

| probe | result |
| --- | --- |
| root `dyld_chained_fixups_header` | `version 0, imports_count **0**, imports_offset == symbols_offset, symbols_format 0` |
| per-member `LC_DYLD_CHAINED_FIXUPS` | absent -- `AppleARMPlatform`, `IOHIDFamily`, `IOStorageFamily`, `IOSurface`, `security.sandbox`, `filesystems.apfs` all inherit the root's |
| per-member `LC_SYMTAB` | `nsyms 0` |
| `__LINKINFO` (file 0x499c000) | a binary plist holding `SymbolsSets` (KPI **export names** only) and `WeakRefFallbackSymbol = _gOSKextUnresolved`; no addresses |

So every binding Apple made was already resolved into a plain rebase before the
cache was written: there is no import table, no symbol table, and no name-addressed
structure anywhere in the file. The 19 unpinned targets are file-backed
`__DATA_CONST` globals whose own first pointers land in `__DATA` BSS (zero fill) and
in `__TEXT` string space -- nothing self-describing, so reading the object cannot
name it either.

**Consequence.** `prelink-map-unresolved` cannot be closed by "look up the names".
It has to be closed by a pairing that is *verifiable without names*, or it stays
open and the image stays grounded. The candidate is section-order alignment
against our own build, which does have a symbol table: sort our `__DATA_CONST`
symbols by address, walk Apple's section in the same order, and accept a mapping
only when the size sequence is unambiguous inside the window; every accepted pair
must then survive a round-trip check (its first pointer lands in the same *kind*
of section on both sides). Anything ambiguous stays refused -- a wrong pairing
here is worse than a missing one, because it makes a silent wrong address look
reviewed.
