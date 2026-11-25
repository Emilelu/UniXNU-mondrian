# iOS 27 root storage: the path does not exist yet

Measured 2026-11-24, after r290n.

## The observation

| question | answer |
|---|---|
| how many patches in `patches/xnu-12377/series` mention `ufs` | 0 (`grep -n 'ufs' patches/xnu-12377/series` is empty) |
| how many 27 kernel archives build a block-storage driver | 0 (`board.toml [os_overrides."ios-27.0.1-24A446".kernel].archives` lists nine entries, none of them `component:PongUfs`, `build-native-ufs-linux.py` or `build-sheng-source-storage.py`) |
| where `K60UFS` / `plan.order` lives | `drivers/NativeUfs/` in the device repo, which only the 16.6.1 profile links |

So the 27 kernel has no block-storage provider at all. The UFS publish-order fix
(`fcee294c`, P-322) is correct and necessary for the 16 line, but it cannot change a
27 boot: no code from `drivers/NativeUfs` reaches the 27 kernel.

## Two routes, both already prototyped elsewhere

**A. Port `drivers/NativeUfs` into the 27 kernel.** The bt line already built
`libNativeUfs.a` on Linux (`scripts/build-native-ufs-linux.py`, `NativeUfs.o` 212,256 B,
`PongUfsTransport.o` 331,112 B, archive 556,720 B). Linking it into a 27 fileset fails
with twelve undefined symbols: eleven `IOBlockStorageDevice` members (vtable, meta class,
`init`/`D2Ev`/`C2E` and seven virtual slots) and `_armcpu_timer_interrupts`. In 16.6.1 the
class is defined in the kernel itself; in 27 it lives in the sibling fileset entry
`com.apple.iokit.IOStorageFamily`, so the kernel cannot resolve its vtable.

**B. Sheng's source-storage route (proven on iOS 27).**
`UniXNU-sheng/scripts/build-sheng-source-storage.py` compiles the pinned
`IOStorageFamily-337.100.1@7edb88fb` `IOBlockStorageDevice.cpp` with a metaclass macro,
and `package/SourceStorage.cpp:243,264` picks the superclass up at run time from the
loaded OSKext and asserts `getClassSize() == sizeof(IOBlockStorageDevice)`. Its 190-slot
table has PAC diversity 190/190. This is the only route in this workspace that has
actually produced a 27 block-storage device on a Pong-family board.

## Decision rule

Choose by the same rule used for the display stack: the route that has produced a 27
device on a Pong board wins unless a measured fact blocks it. That is B. A stays as the
fallback if B's class-size assertion cannot hold on this kernel.

## What is being done about it

`docs/engineering/IOS27-FLIGHT-BLOCKERS.toml` gains `root-storage-absent` (open). It is
not closable by a build flag: closing it requires one of the two routes above to land in
`board.toml` archives and a kernel link that reports no undefined `IOBlockStorageDevice`
symbols.
