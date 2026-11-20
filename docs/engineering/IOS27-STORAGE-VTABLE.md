# The storage class vtable, slot by slot

The storage route asks whether the kernel can call Apple's
`IOBlockStorageDevice` methods through the class's own vtable. The count is
190 slots; a count alone proves nothing, because the wrong pointer format also
produces a plausible table. This page records the per-slot comparison between
the pinned 24A446 entry and the object the route would link.

## Where the table is

In `com.apple.iokit.IOStorageFamily` of the pinned kernelcache
(`/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed`, sha256
`fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`), the class
vtable is `__ZTV20IOBlockStorageDevice` at
`__DATA_CONST 0xfffffff008314d88` (file 0x1310d88). The first two words are
zero (offset-to-top and typeinfo); slot 0 starts at `0xfffffff008314d98`. The
outer `LC_DYLD_CHAINED_FIXUPS` declares `pointer_format 8`, which is
`dyld_chained_ptr_64_kernel_cache_rebase`:

    target:30  cacheLevel:2  diversity:16  addrDiv:1  key:2  next:12  isAuth:1

with collection base `0xfffffff007004000`. Decoded that way the table has 190
slots and is followed by three zero words. Decoded as `ARM64E_KERNEL` the same
bytes give 260 slots and run into the next table; both answers look reasonable
until the tail is checked.

## What is compared

`docs/engineering/ios27-storage-vtable.tsv` records, for each slot, the kind
(`own`, `external` or `pure`), the method name and the 16-bit discriminator
that the pinned `IOStorageFamily-337.100.1` source
(`7edb88fbae296fb7c8ce2f64e115e116e566d51c`) compiles into the object's vtable.
The checker reads the same slot from the kernelcache and requires three things:

1. the discriminator equals the source object's;
2. the pointer is an authenticated rebase (`isAuth 1`);
3. the target is code in the image the kind expects -- the entry's own
   `__TEXT_EXEC` for `own` methods, `com.apple.kernel`'s `__TEXT_EXEC` for
   `external` and `pure` ones.

## Result

    entry com.apple.iokit.IOStorageFamily: 5 segments, vtable 0xfffffff008314d88 (two-word header)
    slots: 190 read at 0xfffffff008314d88; 一致 190
    tail: three words after the table are zero
    verdict: all slots agree

| kind | slots | target |
| --- | --- | --- |
| own | 14 | entry `__TEXT_EXEC`, e.g. slot 0 `0xfffffff00a323e40` |
| external | 162 | `com.apple.kernel` `__TEXT_EXEC`, e.g. slot 2 `0xfffffff00b24e970` |
| pure virtual | 14 | `com.apple.kernel` `__TEXT_EXEC`, `0xfffffff00b41c76c` |

No slot is undecided and none disagrees. The pure-virtual slots all point at
the same kernel address, which is the shared `__cxa_pure_virtual` handler.

## What the result does and does not prove

The discriminator is a 16-bit hash of the symbol, so one match is evidence and
could in principle collide; 190 matches in slot order are a layout signature,
not a coincidence. This is the strongest static statement available without
running the class: the binary's table and the pinned source's table have the
same length, the same per-slot discriminators, the same code/data split and the
same ending.

It does **not** prove:

- that the parent metaclass resolves at load time (that is the
  `SourceStorage.cpp:270-278` path, measured only in a scratch replay);
- that construction order (`:287-292`) is safe on the board;
- that the arm64e PAC dispatch key and discriminator survive the cross-image
  call at run time.

The table is a necessary condition for route D, not a demonstration that the
route works.

## Reproduce

    python3 scripts/check-ios27-storage-vtable.py \\
        --kernelcache /home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed \\
        --vtable 0xfffffff008314d88

The TSV is the source side. It was read from the object built from the pinned
`IOBlockStorageDevice.cpp` with the recorded arm64e flags: the vtable lives at
`__const 0x530`, each slot word carries its discriminator, and the method names
come from the section relocations. The kernelcache side is re-derived on every
run, so a different build cannot inherit this page's answer.
## The table names its pin

The table is generated from a pinned source, so it records that pin in its head:
`# pin: IOStorageFamily IOStorageFamily-337.100.1`, `# commit: 7edb88fb...` and the
profile it came from. `check-ios27-storage-vtable.py` reads the head and compares the
commit with the `[[source]]` entry in `profiles/os/ios-27.0.1-24A446/profile.toml`; a
moved pin, a missing head or a missing profile is a failure, so the table cannot
outlive the source it compares against.
