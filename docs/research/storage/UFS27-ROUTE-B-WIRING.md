# Route B wiring — what the builder must connect

Status: checklist, no implementation. Measured 2026-11-21 against
`E:/k60-work/ufs27` (branch `feat/ufs-27`) and the framework checkout
`E:/hackios/UniXNU`. Every row names the file and line that decides it.

Route B is the *other* answer to the eleven `IOBlockStorageDevice` imports. Route
A / Route D binds them in the kernel link; route B ships `drivers/NativeUfs` as
its own fileset entry, so at prelink time its imports resolve against the
sibling `com.apple.iokit.IOStorageFamily` entry instead of `com.apple.kernel`.
The tree already says so in its own words:
`scripts/check-ios27-storage-entries.py:4-9` ("Route B keeps the UFS driver out
of the kernel image's own link … the driver's bundle has to be one of them"),
and `scripts/check-ios27-storage-exports.py:6-9` frames A versus B as the
question those readers answer.

This document answers one question: **what has to be wired, and which of it
exists today.** Nothing here was built; the only commands run are the two
recorded in §2.4 and §5.

## 1. The chain, and where it breaks

| # | link in the chain | state today | who owns it |
|---|---|---|---|
| 1 | three translation units compile | exists — `scripts/build-native-ufs-linux.py` | device repo |
| 2 | they become an `MH_KEXT_BUNDLE` (filetype 11) with `kmod_info` | **absent** — the producer stops at `llvm-ar` | device repo (new recipe) |
| 3 | the bundle carries `OSBundleLibraries` and the `ufshc` personality | **absent** — plist has neither key | device repo |
| 4 | the kernel link stops force-loading the archive | **absent** — one block does it | framework builder (vendored copy here) |
| 5 | the prelink emitter can *add* an entry | **absent** — it re-addresses entries it finds in the original | prelink kit (framework) |
| 6 | the profile declares the entry as a root | blocked by 5 — a root must already exist in the original metadata | framework OS profile |
| 7 | the product is checked for the entry | exists — three readers, §2.5 | device repo |

Chains 2-6 are ordered: 5 is the wall. Everything before it can be built and
nothing will carry it into the product.

## 2. Each link, measured

### 2.1 Compile to archive (exists)

`scripts/build-native-ufs-linux.py` compiles `NativeUfs.cpp`,
`PongUfsTransport.cpp` and `verified_root.c` with the kernel build's recorded
argv and archives them: `SOURCES` at `:29-33`, `DEFINES` at `:34`
(`XNU_NATIVE_UFS=1`, `XNU_SOURCE_STORAGE=1`), `llvm-ar` at `:115-119`. The output
is `libNativeUfs.a`, three members, 556,720 B when the 24A446 record is present
(`docs/engineering/IOS27.md:376-377`). An archive cannot be a fileset entry —
step 2 needs a link step that does not exist in either tree.

There is **no kext-link precedent to copy**: the only `-bundle` in the framework
builds a user-space Metal plugin
(`UniXNU/scripts/build-adreno-metal-plugin.py:80`), and this board's "thermal
kext" is also an archive that gets force-loaded
(`scripts/build-thermal-kext.sh:236` builds `libK60ThermalKext.a`, linked at
`scripts/build-xnu-4k-baseline.sh:1302-1313`). So step 2 is new work either way,
and the flag set has to be derived (`-kext` versus hand-built `kmod_info`
sections), not borrowed.

### 2.2 The bundle's Info.plist (absent)

`drivers/NativeUfs/Info.plist` is 10 lines: `CFBundleIdentifier`
`org.blu-sharky.NativeUfs.Pong`, `CFBundleExecutable NativeUfs`,
`CFBundlePackageType KEXT`, `CFBundleVersion 0.1.0`, `OSBundleRequired Root`.
It has **no `OSBundleLibraries`** and **no `IOKitPersonalities`**. Route B needs
both: the libraries are what the loader uses to order the sibling entry
(`com.apple.iokit.IOStorageFamily`, and `com.apple.kec.corecrypto` for the
crypto calls), and the personality is what makes the `ufshc` node probe the
driver at all — the same five keys `patches/xnu/ios16-native-ufs-personality.patch`
installs inside `KernelConfigTables.cpp` for route A.

`native_prelink.py:174-180` is the reason this is not optional: a component with
no executable fields must carry personalities, and a component with executable
fields but no declared libraries fails dependency planning (`:152-153`).

### 2.3 The kernel link (one block, framework side)

`scripts/build-xnu-generic.sh:646-653` appends
`-Wl,-force_load,$ROOT/build/native-ufs/libNativeUfs.a` to
`KERNEL_EXTRA_ARCHIVES`, which reaches the kernel link as
`LD_KERNEL_ARCHIVES` at `:789`. The 16.6.1 builder has the same two branches at
`scripts/build-xnu-4k-baseline.sh:1054` and `:1278`. Route B turns all three off
and, per iron rule 11 and P-255, that is done upstream and arrives here through
`scripts/refresh-xnu-generic.py:15` — the copy in this repo must not be edited.

Note what this block *is*: it is also the only thing that makes route A's
failure mode visible (14 → 26 undefined symbols). Turning it off is exactly what
removes the eleven from the kernel link, and with them the reason to bind them
there.

### 2.4 The prelink emitter (the wall)

Two measured facts, both decisive:

**(a) The 27 profile's prelink arguments are not understood by the tool it
names.** `UniXNU/profiles/os/ios-27.0.1-24A446/profile.toml:31-43` sets
`tool = "kits/XnuPrelink/emit_prelink.py"` and
`extra_args = ["--fileset-reference", …, "--allow-missing"]`, and
`UniXNU/scripts/unixnu/kernel.py:295` appends `extra_args` verbatim to that
tool's command line. The tool's parser (`kits/XnuPrelink/emit_prelink.py:181-190`)
accepts `--kernel --prelinked --root --slide --output --early-security-init
--library-only` and nothing else. Executed:

```sh
python3 kits/XnuPrelink/emit_prelink.py --kernel a --prelinked b --root c \
  --slide=0 --output d --fileset-reference build/xnu/fileset-reference/mach.release.bcm2837.unstripped.noctf \
  --allow-missing
# exit 2
# emit_prelink.py: error: unrecognized arguments: --fileset-reference … --allow-missing
```

So the 27 prelink step cannot run as configured, today, independently of
storage. Whoever designs the fileset-entry path owns that argument surface; it
is not this row's to change.

**(b) Even with arguments fixed, the emitter cannot carry a new entry.**
`kits/XnuPrelink/native_prelink.py:147-154` takes `roots`, looks each one up in
the *original* kernelcache's `_PrelinkInfoDictionary`, and raises
`Missing declared dependency {identifier}` for anything absent; `:160-171` then
walks the same original entries, requiring each to be `MH_KEXT_BUNDLE`
(filetype 11) and recording its `_PrelinkExecutableLoadAddr`. `emit_prelink_orig.py:131-134`
does the same on the emit side (`entries = {e['CFBundleIdentifier']: e for e in metadata['_PrelinkInfoDictionary']}`,
then `entries[identifier]['_PrelinkExecutableLoadAddr']`). The prelink output is
therefore a **re-addressing of Apple's own entries** onto the native kernel's
symbols; there is no code path that manufactures an entry for a bundle this
build produced.

Consequence for the checklist: step 5 is not a wiring change, it is a new
capability in the kit — parse a bundle, assign it a `__PRELINK_TEXT` extent
inside the outer `MH_FILESET`, synthesize its `_PrelinkExecutableLoadAddr`,
`_PrelinkExecutableSize` and `_PrelinkKmodInfo`, and include it in the pointer
re-binding pass. Nothing in either checkout does that today.

### 2.5 Acceptance (exists)

- `scripts/check-ios27-storage-entries.py --kernelcache <kc> --require-entry`
  parses `MH_FILESET` (filetype 12) and `LC_FILESET_ENTRY` (`0x80000035`), and
  reports which entry carries `NativeUfs`/`native-ufs` (defaults at `:23`).
  Without `--require-entry` an absent entry is a state, not an error.
- `scripts/check-ios27-storage-exports.py` answers whether the eleven symbols
  are exported, per entry, with `--require-exported` to make absence a failure —
  it is the reader that proves route B *worked*, because the symbols must come
  from the sibling entry and not from `com.apple.kernel`.
- `scripts/check-ios27-storage-vtable.py` and
  `scripts/check-ios27-storage-preflight.py` complete the set.

All four need a product (`kernel.macho` or a kernelcache). None can run on this
host, for the same reason as the archive check: no build, no artifact.

## 3. What has to change, by owner

| owner | change | verified by |
|---|---|---|
| device repo | a kext link recipe: archive → `MH_KEXT_BUNDLE` + `kmod_info`, plus `CFBundleExecutable`/`OSBundleLibraries`/`IOKitPersonalities` in `drivers/NativeUfs/Info.plist` | `llvm-objdump --macho --private-header` on the product: filetype 11, `__kmod_info` symbol present |
| device repo | a recipe entry in the 27 profile's `[kernel].archives` replacing the archive entry, and `scripts/check-kernel-archives.py:37`'s expectation (`NativeUfs5start`) re-pointed or retired | `python3 scripts/check-ufs27-storage-selection.py` stays at 0 gaps with the new entry |
| framework builder | remove the three force-load sites (`build-xnu-generic.sh:646-653`, `build-xnu-4k-baseline.sh:1054`, `:1278`) | diff in `UniXNU`, arrives here via `refresh-xnu-generic.py` |
| prelink kit | add-entry support of §2.4(b) — the only genuinely new code in route B | `python3 kits/XnuPrelink/test_native_prelink.py` plus a fixture that adds one entry |
| framework profile | `[kernel.prelink]` accepts the new entry: argument surface of §2.4(a) reconciled with the tool, entry named as a root, `roots` list untouched otherwise | the prelink command of §2.4(a) exits 0 instead of 2 |
| Lead | whether route B is entered at all; it is a bigger change than route A and does not remove the eleven symbols | — |

## 4. Three corrections to the handover list

1. **"filetype 11" is the inner bundle, not the product.** The product is
   `MH_FILESET` (filetype 12) and each entry inside it is `MH_KEXT_BUNDLE`
   (filetype 11) — `check-ios27-storage-entries.py:37-38` rejects anything that
   is not 12, and `native_prelink.py:169` is the check that Apple's entries are
   11. Both are true; they are not the same object.
2. **The prelink kit cannot add the entry.** Wiring the builder to emit a bundle
   is necessary and not sufficient; §2.4(b) is the blocker, and it is kit code.
3. **The 27 profile's prelink arguments do not parse today** (§2.4(a)), so any
   statement about "the 27 prelink" is about a step that has never run in this
   configuration.

## 5. What route B does not change

- **The eleven symbols stay Route D's.** Route B does not define
  `__ZTV20IOBlockStorageDevice` or its meta-class; it changes who resolves them
  (sibling entry at prelink instead of kernel link). If Route D lands, route B's
  reason shrinks to "don't put a driver in `com.apple.kernel`", which is a
  packaging preference, not a link requirement.
- **RamBlock's exclusion stands.** `scripts/build-xnu-generic.sh:728` still
  skips the RAM block under `XNU_SOURCE_STORAGE=1`, and the 27 line runs source
  storage. A kext-entry route for the UFS driver does not change the RAM disk
  decision.
- **The boot-arg question is untouched.** `native-ufs-root=1` still has no home
  on 27 (`board.toml:393` says it comes back with PongUfs in F3); a fileset entry
  does not create one.

## 6. What the Lead has to decide

1. Enter route B at all, or wait for Route D — knowing the kit needs new code
   (§2.4b) before the first bundle can be carried.
2. If yes: is the prelink kit change the framework's (same owner as the
   `test -f` fix of §11 in `UFS27-GATE.md`), or does it stay blocked until the
   fileset-entry design owner takes it?
3. If no: keep §5's first bullet as the record, and this file stays a checklist
   with no producer — the same status `UFS27-GATE.md` §7 gives VerifiedRoot.
