# Route B wiring — what the builder must connect

Status: route B was **entered by the Lead on 2026-11-21**. Rings 2, 3, 4 and 7
are this row's to write; ring 5 — and therefore ring 6 — is framework prelink code
that moves *every* kext's placement, so it is pinned here and owned elsewhere.
`scripts/check-ufs27-route-b.py` grades the four rings this row owns (§8). Measured
2026-11-21 against `E:/k60-work/ufs27` (branch `feat/ufs-27`) and the framework
checkout `E:/hackios/UniXNU`. Every row names the file and line that decides it.

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
| 5 | the prelink emitter can *add* an entry | **absent** — it re-addresses entries it finds in the original | framework prelink kit — **not this row's** (a change here moves every kext, Lead ruling 2026-11-21) |
| 6 | the profile declares the entry as a root | blocked by 5 — a root must already exist in the original metadata | framework OS profile, unblocked only with 5 |
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

`scripts/build-xnu-generic.sh:646-653`: the block assigns
`UFS_ARCHIVE=$ROOT/build/native-ufs/libNativeUfs.a` at `:649`, guards it with a
bare `test -f` at `:650`, and appends `-Wl,-force_load,$UFS_ARCHIVE` at `:651` to
`KERNEL_EXTRA_ARCHIVES`, which reaches the kernel link as `LD_KERNEL_ARCHIVES` at
`:789`. The 16.6.1 builder carries the same pair twice — kernel archives
`:1054`/`:1056`, platform archives `:1279`/`:1280`. Route B turns all three off
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

## 6. What the Lead decided (2026-11-21)

1. **Route B is entered.** It is Apple's own shape and it bypasses the prelink
   wall of §2.4 rather than fighting it.
2. **Ring 5 is not this row's.** `emit_prelink.py` not accepting the profile's
   arguments (§2.4a) and the emitter not being able to add an entry (§2.4b) are
   framework prelink code; touching `native_prelink.py:147-171` or
   `emit_prelink_orig.py:131-134` changes where *every* kext lands, which is more
   than one storage lane can be answerable for. This file pins the ring; it does
   not change it.
3. The other four rings are written here, starting with a checker that runs
   today (§8) rather than with the implementation.
4. Proof (a)'s two failures get **no new blocker number**: the Lead records them
   in the framework pin paragraph and in a blocker's `why_open`.

## 7. Where the absence claims come from

Two rings claim that something does not exist anywhere. "Absent" is only worth
printing if the search is reproducible, so this is the search:

```sh
for r in E:/k60-work/ufs27 E:/hackios/UniXNU E:/hackios/UniXNU-sheng \
         E:/hackios/UniXNU-t970 E:/hackios/UniXNU-zizhan; do
  grep -rIn "MH_KEXT_BUNDLE\|kmod_info" --include=*.py --include=*.sh \
       --include=*.c --include=*.cpp "$r"
  grep -rIn -- "-kext " --include=*.py --include=*.sh "$r"
done
```

| tree | `MH_KEXT_BUNDLE` | a `-kext` link | `kmod_info` |
|---|---|---|---|
| `E:/k60-work/ufs27` (this row) | `kits/NativePrelink/native_prelink.py:170` — a *test* of Apple's entry | none; `patches/xnu-12377/series:57` is a comment about a form the kernel does not use | `kits/NativePrelink/emit_prelink.py:249` reads `kmod_info_va`; drivers only take `extern kmod_info_t g_kernel_kmod_info` (`drivers/PongWifi/PongWifiPlatform.cpp:42`, `drivers/PongAdreno/PongAdrenoAccelerator.cpp:10`) |
| `E:/hackios/UniXNU` (framework) | `package/UniXNUPkg/Library/UniXNULib/Kext.c:196` — the loader *refusing* an invalid bundle; `package/Scripts/smoke.sh:108` tests that refusal | none (the only `-bundle` is the user-space Metal plugin, `scripts/build-adreno-metal-plugin.py:80`) | `.cache/xnu-work/tools/tests/testkext/pgokext/pgokext.c:11-21` — XNU's own test kext |
| `E:/hackios/UniXNU-sheng` | none | none | `package/AcceleratorABIProbe.cpp:9`, `package/AudioProbe.cpp:42`, `package/BacklightProbe.cpp:9` — all `g_kernel_kmod_info` externs |
| `E:/hackios/UniXNU-t970` | `kits/NativePrelink/native_prelink.py:191` | none | `kits/NativePrelink/emit_prelink.py:248`; `drivers/T970Wifi/T970WifiNetGlue.cpp:34` |
| `E:/hackios/UniXNU-zizhan` | `kits/NativePrelink/native_prelink.py:191` | none | `kits/NativePrelink/emit_prelink.py:248`; `drivers/PongWifi/PongWifiPlatform.cpp:36` |

Read together: five trees, no build step links a bundle; every driver is a static
archive force-loaded into `com.apple.kernel`; and the four `MH_KEXT_BUNDLE` hits
are all *readers* of a bundle (a loader check, a prelink check, a smoke test), not
producers. That is why ring 2 is "new work" and not "find the existing recipe".

For the plist, the search is narrower and equally reproducible:
`grep -n "OSBundleLibraries\|IOKitPersonalities" $(git ls-files '*Info.plist')`
over the same five trees returns nothing, and the file it would have to touch is
`drivers/NativeUfs/Info.plist` (10 lines, §2.2).

## 8. The checker that runs today

`scripts/check-ufs27-route-b.py` grades four rings — `bundle`, `plist`, `link`,
`readers` — as **coherent or not**, never as "complete", because at stage 0 most
rings are legitimately absent. Pending exits 0; only a state that cannot coexist
with another state is a gap:

| gap it can print | why it is a gap |
|---|---|
| two carriers | the kernel force-loads the archive *and* a bundle recipe links the same objects — whichever product loses, it loses silently |
| no carrier | the force-load is gone and no bundle recipe exists — the driver is in no product, and the readers would say "absent", not "broken" |
| half a plist | one of `OSBundleLibraries` / `IOKitPersonalities` present without the other |
| bundle without `CFBundleExecutable` | a recipe links a bundle the loader cannot name |
| a reader that is missing or does not compile | the acceptance set has to exist before a product can be judged |

```sh
K60_FRAMEWORK_REPO=E:/hackios/UniXNU python3 scripts/check-ufs27-route-b.py
# repo      E:/k60-work/ufs27
#   PEND bundle   no recipe links a bundle: …
#   PEND plist    drivers/NativeUfs/Info.plist has neither OSBundleLibraries nor IOKitPersonalities; …
#   PEND link     scripts/build-xnu-generic.sh:651, scripts/build-xnu-4k-baseline.sh:1056,
#                 scripts/build-xnu-4k-baseline.sh:1280 force-loads build/native-ufs/libNativeUfs.a …
#   PEND readers  4 readers present and compiling, none runnable yet: …
# ufs27-route-b: 0 gap(s), 4 pending
```

The five-state fixture proves each gap branch fires and that the checker can also
go green: `E:/k60-work/scratch/ufs27-routbematrix/` (`make.py`, `run.sh`) builds
`pending`, `ready`, `twocarr`, `orphan`, `halfplist` and expects `0 0 1 1 1`.

```sh
cd E:/k60-work/scratch/ufs27-routbematrix && bash run.sh
# PASS: pending     -> 0 gap(s)
# PASS: ready       -> 0 gap(s)
# PASS: twocarr     -> 1 gap(s)
# PASS: orphan      -> 1 gap(s)
# PASS: halfplist   -> 1 gap(s)
```

`ready` is the important row: with a bundle recipe, both plist keys, the
force-load removed and the four readers present, the gate reports 0 gaps — so it
is a criterion for the work, not a light that stays red for ever.
