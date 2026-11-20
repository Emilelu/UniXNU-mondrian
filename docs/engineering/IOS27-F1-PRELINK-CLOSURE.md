# The prelink closure on the iOS 27 kernel

The 27 build redirects every cross-image reference it cannot resolve to
`_unixnu_fileset_unmapped` (osfmk/kern/debug.c:2585). The question this page
answers is whether those redirects are a setting that was left on, or a property
of the collection the emitter was handed. The short answer is the second: the
input kernel entry has no symbol table at all, so a symbol-level prelink has
nothing to match against. The numbers below come from the pinned cache and the
round-17 kernel.json on this host, not from a boot.

## What the two inputs say

The pinned input is
`/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed`
(77,987,840 bytes, sha256
`fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`).
Its `com.apple.kernel` child is an MH_EXECUTE at file offset 0x8000 with 27
load commands, and its only symbol table command is empty:

    LC_SYMTAB symoff 77496320 nsyms 0 stroff 77970320 strsize 1

Every prelink segment in that child has `vmsize 0`: `__PRELINK_TEXT`,
`__PRELINK_INFO`, `__PLK_TEXT_EXEC`, `__PRELINK_DATA`, `__PLK_DATA_CONST`,
`__PLK_LLVM_COV` and `__PLK_LINKEDIT`. There is no prelinked payload to read
names from either.

The build report is
`/mnt/e/hackios/ci-artifacts/44518998961/ext/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json`.
It records:

| field | value |
| --- | --- |
| missing bundles | 28 |
| missing target addresses | 133 |
| missing references (sum of counts) | 650 |
| stubbed bundles | 29 |
| stub sites (distinct) | 946 |
| stub references (sum of counts) | 2688 |

The distinction between the two counts matters and is explained on
[IOS27-FLIGHT-GATE-REVIEW.md](IOS27-FLIGHT-GATE-REVIEW.md): the report stores a
map of address to count, so `len(map)` is the number of distinct addresses and
the sum of the values is the number of references. The gate currently prints the
first number and calls it references.

Classified against the output collection's own segments, the 133 addresses are:

| output segment | addresses |
| --- | --- |
| `__DATA` | 101 |
| `__DATA_CONST` | 31 |
| `__PRELINK_TEXT` | 1 |

The `__PRELINK_TEXT` address is `0xfffffff007044478`, owner
`com.apple.driver.AppleARMWatchdogTimer`. An earlier edition of this page
called it a translation defect because it fits the input `__TEXT`
(`0xfffffff007004000` + `0x1a0000`) and not the output `__TEXT`
(`0xfffffff007184000` + `0x1a0000`), but the report's `segment_layout` lists
only `com.apple.kernel`'s own segments, not the coalesced `__PRELINK_TEXT`
(`0xfffffff00700c000` + `0xce4000`) where the address actually lands. The
defect did not exist; what remains is the assertion below.

The checker also reads the collection's chained rebases (format 8) and fails
while any target lies inside the input `__TEXT` and outside every output
segment (`--collection ... --require-translated`). On the pinned inputs that is
47,141 targets and none inside the input `__TEXT`. The decoder is a classifier,
not an oracle: on Apple's own 24A446 kernelcache it returns 783 targets, 355
outside every segment, so outside counts alone are not evidence.

## Why the names cannot come back

The emitter resolves a cross-image reference by looking the target address up
in the target kernel's defined symbols. With `nsyms 0` there is no candidate
for any address, so the lookup fails for all of them, the address is recorded as
missing, and the site is rewritten to the panic stub. A flag such as
`--allow-missing` only says the build may continue; it does not create a name.
Changing the pointer format, the slide or the selected roots cannot create one
either.

The 16.6.1 kernel is the control that proves the reader is not simply always
empty: `/opt/k60/trees/k60build/bt-out-0523/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho`
is an MH_EXECUTE with 25 load commands, an `LC_SYMTAB` of 180,035 symbols, and
non-empty `__PRELINK_TEXT` (0x714000) and `__PLK_TEXT_EXEC` (0x15b4000)
segments. On that kernel the same class of reference has names to resolve.

## The reproducible criteria

`scripts/check-ios27-prelink-closure.py` reads the report and the pinned cache
and prints the following, so a later build can be compared without trusting
this page:

1. The report counts as distinct symbols and as references, separately.
2. The kernel entry's filetype, load command count and `LC_SYMTAB.nsyms`.
3. The `vmsize` of every `__PRELINK_*` and `__PLK_*` segment.
4. The target distribution over the output collection's segments when
   `--collection` is given; the report's own layout covers only the kernel entry.
5. How many targets have a defined symbol at their exact address.
6. How many targets still sit inside the input `__TEXT` and outside every output
   segment, and how many chained rebases the collection carries;
   `--require-translated` fails while any remain and refuses to judge without
   `--collection`.

On the two inputs above it prints:

    report: 28 missing bundles, 133 symbols, 650 references
    stub:   29 bundles, 946 sites, 2688 references
    kernel: com.apple.kernel filetype 2, 27 load commands, nsyms 0
    prelink segments: __PLK_DATA_CONST 0x0, ... __PRELINK_TEXT 0x0
    targets: 133 distinct, 0 nameable, in the new layout (output collection);
             segments: __DATA 101, __DATA_CONST 31, outside-collection 1
    verdict: closure-needs-symbols -- the input kernel entry has no symbol
             table, so a symbol-level prelink cannot name any owner target

The verdict is an observation, not a failure: the tool exits 0 unless
`--require-named` is given, because a stripped input is a legitimate finding
about the input rather than a malformed report. `hardware_verified` stays
false in the JSON it writes.

## What would change the answer

Three routes exist, and only the first two produce names:

1. **Supply a symbol-rich kernel.** Build our own kernel with a symbol table, or
   obtain a collection whose `com.apple.kernel` still carries one. The emitter
   then resolves normally; nothing else in the map needs to change.
2. **Link the kexts into the kernel**, the 16.6.1 shape: one MH_EXECUTE, no
   sibling fileset entries, no cross-image owner lookup.
3. **Bind by address through a real export table.** This is what route A wanted
   for the storage class and what
   [IOS27-STORAGE-VTABLE.md](IOS27-STORAGE-VTABLE.md) measures; the pinned
   collection exports nothing from its entries
   (`scripts/check-ios27-storage-exports.py`: 0 of 305 entries carry an export
   trie), so this route needs an input that has one.

The ledger's existing `prelink-map-unresolved` blocker says counts alone do not
say which sites are reachable and that the arm64 prelink step may not be the
right instrument. This page supplies the missing half of that sentence: on this
input the instrument cannot produce a single name, so counting reachable sites
is premature until one of the three routes above changes the input.

## Limits

Nothing here ran on the board. The two inputs are read-only, the checker writes
only its own JSON, and the conclusion is about what the emitter can resolve from
the pinned collection -- not about whether a particular stubbed site is executed
during boot.
