# Route D: deferred construction for the storage driver (plan)

**Status: plan only. Nothing in this document is implemented on this branch,
and it does not ride the stage-0 merge.** The switch that would use it
(`CONFIG_XNU_NATIVE_UFS`) stays `n` until the F3 decision; the three edits
that would open it are frozen in `d77c398d`.

## 1. Why this route exists

The shipped 24A446 kernel collection does not export the eleven
`IOBlockStorageDevice` symbols the storage driver imports. Measured on the
pinned cache: `com.apple.kernel` is `MH_EXECUTE` with 27 load commands and a
symbol table of zero entries, the `IOStorageFamily` entry has no export trie
and no symbol table, and the seven `__PRELINK_*`/`__PLK_*` segments are empty.
Apple resolves those symbols at build time, inside its own collection, and
publishes no sibling namespace to bind against.

- Route A (link against the family as a symbol provider) needs an export trie
  the file does not have.
- Route C (a constant stub) is forbidden: it would make the linker quiet and
  the runtime wrong.
- Route D keeps the C++ class and does not link against the family at all. The
  class is built later, from the running family's own metaclass, after that
  family is loaded.

Sheng's tree already carries this shape (`UniXNU-sheng` at
`a68ee4ee67cc71792fbf519de7e3e28072c717b5`); this document plans how it would
land here, not how to copy it.

## 2. What has to change, with file:line

Paths below the sheng checkout are the pinned ones; paths in this repository
name files this branch already owns.

| # | File | What changes |
| --- | --- | --- |
| 1 | `UniXNU-sheng/scripts/... build-sheng-source-storage.py:173-178` | the `OSDefineMetaClassAndAbstractStructors(IOBlockStorageDevice,IOService)` macro is replaced by `OSDefineMetaClassWithInit` plus an explicit `MetaClass` whose registry name is `UniXNUBlockStorageDevice` and whose parent comes from `native_source_storage_parent()`. The C++ identifier stays `IOBlockStorageDevice`; the comment at :241-242 says why (compiler-authored arm64e discriminators). |
| 2 | same builder `:228-231` | the three TUs (`IOBlockStorageDevice.cpp`, `NativeUfs.cpp`, `NativeRamBlock.cpp`) lose `__DATA,__mod_init_func` and ask `objcopy --globalize-symbol` for the static constructor. On Linux that flag is rejected for Mach-O (`option is not supported for MachO`); our scratch replay therefore emitted the wrapper itself instead. What Apple's `objcopy` does on the macOS host is **unverified here**. |
| 3 | `UniXNU-sheng/package/SourceStorage.cpp:243-247` | the accessor that the deferred metaclass constructor calls; it panics if the parent was not resolved first. |
| 4 | `SourceStorage.cpp:270-278` | `OSKextLoadKextWithIdentifier("com.apple.iokit.IOStorageFamily")`, then `OSMetaClass::getMetaClassWithName("IOBlockStorageDevice")`, then a size check only (`getClassSize() == sizeof(IOBlockStorageDevice)`). |
| 5 | `SourceStorage.cpp:282-292` | policy authentication, APFS load, `preModLoad`, base then UFS then RAM constructors, `postModLoad`. |
| 6 | this repository, `scripts/build-xnu-generic.sh:649` | already links `build/native-ufs/libNativeUfs.a` with `-force_load` when the switch is on; route D changes what that archive contains, not how it is linked. |
| 7 | `configs/mondrian_ios27_defconfig:21`, `configs/board.toml:359` | the switch and the component include; prepared by `d77c398d`, frozen until F3. |
| 8 | `scripts/check-ios27-storage-preflight.py` | the offline gate that must be green before any flight: entry (190 slots), translation (no target left in the input `__TEXT`), and both selectors agreeing. |

## 3. Runtime preconditions the plan depends on

None of these can be established from files on this host.

- **The metaclass registry is populated.** `sAllClassesDict` is created in
  `libkern/c++/OSMetaClass.cpp:844-856`; `getMetaClassWithName` reads it at
  `:1258-1264`; registration requires an owning kext (`:871-883`) and walks
  superclass links (:890-920).
- **The family can be loaded by identifier.** `OSKextLoadKextWithIdentifier`
  looks up `sKextsByID` (`libkern/c++/OSKext.cpp:6157-6223`) and takes the
  already-loaded success branch at `:6554-6563`. Whether a 27 fileset image
  enumerates and starts that kext is the F1 question, not this plan's.
- **The constructor window.** XNU's ordinary path runs module constructors
  inside `OSRuntime`'s init window (`libkern/c++/OSRuntime.cpp:482`,
  `:499-502`, `:526`), checks `OSMetaClass::checkModLoad` before each
  (`:235-245`) and strips PAC with `PTRAUTH_STRIP_STRUCTOR` (`:41`). A
  hand-called constructor bypasses the per-constructor check; the plan must
  either run inside that window or accept the difference explicitly.
- **PAC dispatch.** `HAS_APPLE_PAC`/`HAS_NATIVE_PAC` are set under
  `__arm64e__` (`pexpert/pexpert/arm64/BCM2837.h:30-33`); vtable slots carry
  discriminators. The layout agrees (section 4) but dispatch, casts and object
  identity across images are unproven.

## 4. What the offline evidence already shows

- **Link closure.** Six fixed-baseline groups were linked from the recorded
  build inputs: control 14 undefined, +archive 26, +archive+armcpu 25,
  wrapper+caller 16, wrapper+caller 15, wrapper+guarded accessor 14. All six
  `ld` runs returned 1 and wrote no image; the last group's undefined set is
  identical to control. Evidence:
  `E:/k60-work/scratch/bt-route-d-parent-01/evidence/`.
- **Single-variable deltas.** 23→24 changes only the constructor wrapper;
  24→25 adds a real guarded accessor and removes the remaining undefined
  symbol. No constant stub is involved.
- **Vtable.** 190/190 slots agree with Apple's table under the
  `dyld_chained_ptr_64_kernel_cache_rebase` format (diversity, isAuth and
  target class), with three zero words after the table
  (`docs/engineering/IOS27-STORAGE-VTABLE.md`).

## 5. What only hardware can decide

- that `IOStorageFamily` is loaded, and its metaclass registered, at the
  moment the deferred constructor runs;
- that the resolved parent is the same class the family registered (the size
  check is layout, not identity);
- that the deferred base/UFS/RAM constructors run in the intended window and
  in that order;
- that a vtable signed in one image dispatches correctly in another
  (`pacda`/`discriminator`), and that cross-image casts behave;
- that the Data volume mounts through this path at all.

## 6. Order of work, if F3 is authorised

1. Land the wrapper in **our** `NativeUfs` build, not in sheng's tree, with the
   archive unchanged otherwise.
2. Keep the preflight red until entry, translation and both selectors pass in
   the same run.
3. First flight with the boot argument **off**; the code path is inert.
4. Second flight with it on, criteria written before the boot (parent resolved,
   no panic at :245-247, Data disk line, storage attachment).
5. Only hardware evidence can make it the default.

## 7. Boundaries

- no stubs, no fabricated addresses;
- no ledger entry: Lead ruled the storage blocker belongs in the F3 preflight,
  not in `IOS27-FLIGHT-BLOCKERS.toml`;
- no shared-config, builder or board switch changes before F3;
- this plan does not merge with stage-0 and does not claim the driver works.
## 8. Which steps need an Apple private header

None of the eight steps does. This section exists because "needs Apple's headers" is
the usual reason a step gets deferred to a Mac, and it is not the reason here: the
route consumes published sources plus one Apple *binary* that this project already
pins.

| # | Step | Private header? | Consumes instead |
| --- | --- | --- | --- |
| 1 | metaclass macro rename, `build-sheng-source-storage.py:173-178` | no | `libkern/c++/OSMetaClass.h` from xnu-12377 and the `IOBlockStorageDevice.cpp` that ships in the pinned IOStorageFamily source |
| 2 | strip `__DATA,__mod_init_func`, `:228-231` | no | an `llvm-objcopy` that writes Mach-O (the 14 toolchain), no headers |
| 3 | `native_source_storage_parent()` in `SourceStorage.cpp:243-247` | no | `OSMetaClass.h` only |
| 4 | `OSKextLoadKextWithIdentifier` and `getMetaClassWithName`, `:270-278` | no | `libkern/OSKextLib.h`; the kext it loads is Apple's binary, already in the pinned kernelcache |
| 5 | policy authentication, APFS load, `preModLoad`, constructors, `postModLoad`, `:282-292` | no | the same OSS headers; `SourceStorage.cpp:3-12` includes only `IOKit/*`, `libkern/OSKextLib.h`, `mach/kmod.h`, `pexpert/pexpert.h` and `kern/thread.h` |
| 6 | link `libNativeUfs.a`, `build-xnu-generic.sh:649` | no | the archive and the recorded link line |
| 7 | the switch and the component include, defconfig:21 and board.toml:359 | no | repository configuration |
| 8 | the preflight | no | the pinned kernelcache and the kernel.json report |

What is Apple-private is the **binary, not the header**: `com.apple.iokit.IOStorageFamily`
inside the 24A446 collection, which the plan loads at runtime and never compiles
against. The vtable and metaclass work is exactly how the plan keeps that boundary —
it calls into a binary whose ABI it measured (190 slots, discriminators, class size
0x90) instead of reproducing Apple's private declarations.

One Mac-only artifact was involved and is no longer needed: the arm64e compile and
link arguments recorded in `KernelConfigTables.cpo.json`. They were replayed on Linux
with the recorded `clang` and produced the same 190/190 discriminators, so the
comparison table does not need a Mac to regenerate.

The residual case is worth naming. If policy authentication ever needs an AMFI KPI
that xnu's published source does not declare, that would be the first genuine private
interface, and it would show up as an undefined symbol in the link rather than as a
missing include. Nothing in the current code calls one.

