# The 27 Data gate: where the storage row still breaks, measured offline

Scope: official `porting/drivers` row 2 — *存储、根卷、持久 Data*: ShengUfs, RamBlock,
VirtioMmioBlock, VerifiedRoot (`E:/hackios/UniXNU/docs/zh/porting/drivers.md:37`) — against
[`porting/ufs`](https://unixnu.com/zh/porting/ufs) (`#source-map`, `#procedure`,
`#completion`) and [`porting/platform#block-and-os-services`](https://unixnu.com/zh/porting/platform#block-and-os-services).
Line: `feat/ufs-27`, base `9812517c` (the `feat/xnu27-data-gate` tip), 2026-11-21.
Nothing in this document was built, flashed or merged; every claim below has a
re-runnable command and an exit code.

The one question: **can this checkout produce the archive the 27 builder
force-loads, and does the kernel accept the driver once it does?** Today the
answer is no, for four independent reasons — and they are independent, which is
why fixing one does not move the gate.

## 1. The gate is five stages, and four of them are broken

| # | stage | owner | anchor | today |
|---|---|---|---|---|
| 1 | selection | framework `components.selected()` | `board.toml:361` + `UniXNU/scripts/unixnu/components.py:22-45` | **GAP** — the identifier cannot resolve |
| 2 | recipe | framework `kernel.archive_plan()` / `build_archives()` | `board.toml:384` + `UniXNU/scripts/unixnu/kernel.py:107-175` | **GAP** — nothing writes the archive |
| 3 | switch | device configs | `configs/mondrian_ios27_defconfig:21` | **GAP** — switched on against no producer |
| 4 | link | framework generic builder | `scripts/build-xnu-generic.sh:646-653` | OK — path and guard are already right |
| 5 | bind | 27 XNU patch series | `iokit/KernelConfigTables.cpp` of `xnu-12377.121.6` | **GAP** — no personality for the `ufshc` node |

Stage 4 is the only finished piece, and it is the one the Lead's brief currently
blames. Read the block:

```sh
sed -n '646,653p' scripts/build-xnu-generic.sh
```

It force-loads `$ROOT/build/native-ufs/libNativeUfs.a` and stops with `test -f`
if the file is absent — the 16.6.1 builder does the same at
`scripts/build-xnu-4k-baseline.sh:1054` (kernel link), `:1278` (platform link)
and audits the pair at `:1365`. The stale `build/sheng-ufs/libPongUfs.a`
identifier survives only in the copies of this script under
`E:/hackios/k60-gates`, `k60-wifi`, `k60-charger` and `k60-audio-ios27-carry`;
this branch and `main` already carry the corrected path. That identifier is also
why the gap looked like a missing file rather than a missing recipe.

## 2. Stage 1 — the selection identifier cannot resolve

`board.toml:361` reads `include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink",
"NativeUfs"]`. `NativeUfs` is **not** a catalog id: it is the `legacy_name` of
`ShengUfs` (`UniXNU/components.toml:121`, `legacy_name` at `:139`), whose
archive is `build/sheng-ufs/libShengUfs.a` with
`legacy_outputs = { "build/native-ufs/libNativeUfs.a" = "build/sheng-ufs/libShengUfs.a" }`
(`:140`). A legacy identifier is accepted only when the framework already holds
a *module* for that component — `components.selected()` at
`UniXNU/scripts/unixnu/components.py:22-45`, `official_alias()` at `:87-95`
requires the module's git identity to be
`github.com/unixnu/shengufs` (or `…/nativeufs`) — and modules come from feeds.
This repository's `feeds.toml` declares exactly one source, `sm8475`; no feed,
submodule or `board.toml` pin names the ShengUfs repository. So selection aborts
before any recipe runs:

```sh
python3 scripts/check-ufs27-storage-selection.py
#   GAP  selection   board.toml:361 include 'NativeUfs' is ShengUfs's legacy name, but no feed
#                    or submodule names github.com/unixnu/shengufs -- components.selected()
#                    raises 'unknown component: NativeUfs' before any recipe runs
```

Confirmed against the framework itself, with `modules = {}` (the true state of a
checkout that never fetched that component): `unknown component: NativeUfs`.

Two shapes can fix it, and they are not equivalent:

- **A (recommended).** Drop `"NativeUfs"` from `board.toml:361`; build the
  vendored `drivers/NativeUfs` through a script recipe (stage 2). This keeps the
  driver identity that the archive, the `#include`s and `patches/wifi/0004` all
  assume, and it needs no feed and no framework change.
- **B.** Add a feed that fetches `https://github.com/UniXNU/ShengUfs` so the
  alias resolves. That builds *Sheng's* driver from `drivers/ShengUfs` and
  symlinks its archive onto `build/native-ufs/libNativeUfs.a`. It is the 16.6.1
  mechanism, but it swaps which driver runs — a decision for whoever owns the
  driver, not a config edit.

## 3. Stage 2 — nothing writes the archive

The producer exists and works from the tree's own compile record:
`scripts/build-native-ufs-linux.py` (docstring `:2-21` says "It reports; it does
not wire anything up"), three translation units, `DEFINES = ['XNU_NATIVE_UFS=1',
'XNU_SOURCE_STORAGE=1']`, `--out` default `out/native-ufs-linux`, `--tree`
required (`:72`). Measured against the 24A446 object tree it produces
`NativeUfs.o` 212,256 B, `PongUfsTransport.o` 331,112 B, `verified_root.o`
10,936 B and a 556,720-byte archive — within eight bytes of the 16.6.1 recipe
(`docs/engineering/IOS27.md:376-377`).

The 27 profile never calls it. `board.toml:384` lists eight entries
(`build-corecrypto-14.py`, `build-firehose-stub.py`, …) and no storage recipe,
while `defconfig:14` already carries `CONFIG_XNU_BUILD_ARCHIVES=y`, so the
archive stage does run — it just has nothing to run for storage.

Fix: one list entry, with the output directory the builder reads:

```toml
# board.toml:384, 27 override [os_overrides."ios-27.0.1-24A446".kernel].archives
archives = [ … , "build-fileset-release-reference.py --tree .",
             "build-native-ufs-linux.py --tree . --out build/native-ufs"]
```

`--out build/native-ufs` is not cosmetic: without it the recipe writes
`out/native-ufs-linux/libNativeUfs.a` and stage 4's `test -f` still fails.
Script entries are ordinary `[kernel] archives` citizens
(`UniXNU/scripts/unixnu/kernel.py:141-175` runs them with
`{'tree','component','out'}` substitution and then errors on any `*_ARCHIVE`
that never appeared), so this needs no framework edit.

## 4. Stage 3 — the switch contradicts everything above it

`configs/mondrian_ios27_defconfig:21` is `CONFIG_XNU_NATIVE_UFS=y` already, and
the comment above it (`:17-20`) explains why that is premature today: the eleven
`IOBlockStorageDevice` imports need the fileset-entry route first. A switch that
is on while its archive has no producer is the worst of the three states: it
turns a missing recipe into a build failure at the very end.

Pick one pair, never a mixed one:

| state | defconfig | `board.toml:361` | `board.toml:384` | personality patch |
|---|---|---|---|---|
| stage 0 (today's intent) | `n` | no `"NativeUfs"` | no recipe | in series, inert |
| F3, storage on | `y` | no `"NativeUfs"` | recipe present | in series, `-DXNU_NATIVE_UFS=1` injected |

The right-hand column matters because the generic builder already injects the
define — `scripts/build-xnu-generic.sh:228-230` appends `-DXNU_NATIVE_UFS=1` to
`PERSONALITY_CFLAGS` and `:232` hands it to
`KernelConfigTables.cpo_CFLAGS_ADD`. The define therefore reaches
`iokit/KernelConfigTables.cpp` on every 27 build; §5 is about what it finds
there.

## 5. Stage 5 — no personality exists in the 27 tree, and the patch is ready

The personality table in `xnu-12377.121.6` has two entries and closes
immediately:

```sh
sed -n '37,49p' E:/hackios/UniXNU/out/feeds/xnu-3199e8bc/iokit/KernelConfigTables.cpp
#   IOPanicPlatform / IOPlatformExpertDevice
#   IOExclaveProxy   / IOService
#   ")"
```

`grep -rln NativeUfs patches/` hits the 16.6.1 series
(`patches/xnu/ios16-native-ufs-personality.patch`), the AES personality, the
blog patch and `patches/wifi/0004` — none of the four 27 series layers, which
is what `scripts/check-xnu27-source-storage.py` reports as
"a patch installs the IOKit personality". Without it the define switches on
nothing, `NativeUfs` is never instantiated from the `ufshc` node, and a
successful link still yields no root device.

The 16-line hunk inserts after `IOPanicPlatform`; on 12377 the entry has to
follow `IOExclaveProxy`, because that is where the table now ends. Prototyped
against the real file and dry-run applied in a scratch copy
(`E:/k60-work/scratch/ufs27-personality/`, `patch -p1 --dry-run` → "checking
file", exit 0):

```diff
--- a/iokit/KernelConfigTables.cpp
+++ b/iokit/KernelConfigTables.cpp
@@ -44,4 +44,12 @@ const char * gIOKernelConfigTables =
     "   }"
+#if defined(XNU_NATIVE_UFS) && XNU_NATIVE_UFS
+    "   ,{"
+    "     'IOClass'         = NativeUfs;"
+    "     'IOProviderClass' = IOPlatformDevice;"
+    "     'IONameMatch'     = ufshc;"
+    "     'IOProbeScore'    = 1000:32;"
+    "   }"
+#endif
     ")";
```

Proposed home: `patches/xnu-12377/0542-k60-native-ufs-personality.patch` plus a
`series` line (the device series ends at `0541-k60-virtual-timer-guard.patch`),
**not** listed until F3 — listing it in stage 0 changes nothing at runtime but
does change the series fingerprint every other line validates against.

Why `IONameMatch = ufshc` is right on this board, statically:
`dts/mondrian.dts:119` declares `compatible = "qcom,sm8475-ufshc"` and `:122`
`unixnu,adt-name = "ufshc"`; `scripts/make-pong-adt.py:188-189` emits the ADT
node under that name with both compatible strings; `drivers/NativeUfs/NativeUfs.cpp:58-64`
filters on exactly those two strings. The three pieces agree on the 16.6.1 line
and nothing in this tree changes the node on 27.

## 6. The link half is not a config problem

Adding the archive turns fourteen undefined symbols into twenty-six; eleven
belong to `IOBlockStorageDevice` (`__ZTV20IOBlockStorageDevice`, its
meta-class, `init`, `@free`, five dispatch slots — `docs/engineering/IOS27.md:385-396`).
On 27 those classes live in the sibling fileset entry
`com.apple.iokit.IOStorageFamily`, not in the prelinked executable, so no config
edit can close them; that is the storage-abi bindings object the bt line
measured (`E:/k60-work/scratch/reply-bt-20261115.md`:
`IOStorageFamily-337.100.1@7edb88fb`'s `IOBlockStorageDevice.cpp` compiled
arm64e, eleven imports gone, one `_native_source_storage_parent` left). Stages
1, 2, 3 and 5 can all land before that object exists; the build reaches the link
and stops there, which is a clean, measurable state.

## 7. RamBlock and VerifiedRoot on 27 — the platform page's other two rows

Neither is wired on the 27 profile. `grep -n "RAM_BLOCK\|VERIFIED_ROOT\|OWNER_ROOT_PROBE"
board.toml configs/*.defconfig` returns nothing at all.

**RamBlock** ([`platform#block-and-os-services`](https://unixnu.com/zh/porting/platform#block-and-os-services)
row 1: match dense/packed Data plus the ADT placeholder, implement the
`native_ufs_store` persistence callback):

| integration point | anchor | state on 27 |
|---|---|---|
| catalog identity | `UniXNU/components.toml:272` (`build/ram-block/libRamBlock.a`, `legacy_name = "NativeRamBlock"` → `build/native-ram-block/libNativeRamBlock.a`) | present, unselected |
| profile selection | `board.toml:361` include list | absent; the vendored copy is `drivers/NativeRamBlock/` (catalog path is `drivers/RamBlock`) |
| builder gate | `scripts/build-xnu-generic.sh:215-222` (`XNU_NATIVE_RAM_BLOCK`, requires `XNU_NATIVE_AES=1`), `:727-751` (link, audited against `bindings.json` when `XNU_NATIVE_VIRTIO_BLOCK=1`) | dead code — switch unset |
| personality | `patches/xnu/native-ram-block-personality.patch` (`IOClass = NativeRamBlock; IOProviderClass = IOResources; IOResourceMatch = IOBSD`) | 16-line only, not in the 27 series |
| design exclusion | `:727` also requires `XNU_SOURCE_STORAGE != 1` | on the source-storage line RamBlock is *deliberately* not linked: the storage stack owns the RAM disk |

**VerifiedRoot** (same page, row 3: owner policy plus the trust input for the
chosen image):

| integration point | anchor | state on 27 |
|---|---|---|
| catalog identity | `UniXNU/components.toml:435` — `kind = "kit"`, `path = kits/VerifiedRoot`, `build = []` | kit only, produces no archive |
| builder gate | `scripts/build-xnu-generic.sh:765-770` (`OWNER_ROOT_PROBE=1`, `…/libVerifiedRootProbe.a`, `test -f`) | switch unset |
| trust input | `UniXNU/scripts/policies/ipados-27.0.1-24A446/` | **empty directory** — the reason `check-xnu27-source-storage.py` reports "the policy bundle the root trust verifies" |
| device side | `drivers/NativeUfs/verified_root.c` → `verified_root.o` inside `libNativeUfs.a`; `board.toml:413` `root_match_volume_uuid = "E3F4AED0-…"` (24A446; the 16.6.1 value at `:237` differs) | compiled in, never reached |
| userdata window | `board.toml:47-51` `first_lba = 53342976`, `last_lba = 61731583`, `lba_bytes = 4096` → 32 GiB over LBAs | declared, unused |

The two rows differ in kind: RamBlock is *excluded by design* on a source-storage
line, so its 27 entry is a decision to record, not work to do; VerifiedRoot is
missing a signed policy bundle that only the kit owner can produce.

## 8. Offline archive check — what this host can and cannot answer

Asked and answered offline:

- **Source-level dependency inventory** (all in `drivers/NativeUfs/`):
  `PongUfsTransport.cpp:9` includes `IOKit/storage/IOBlockStorageDevice.h`;
  `:289` `class PongUfsBlock : public IOBlockStorageDevice`;
  `:338` `doAsyncReadWrite(…) override`; `:340`
  `OSDefineMetaClassAndStructors(PongUfsBlock, IOBlockStorageDevice)`;
  `:513` `IOBlockStorageDevice::init`; `:627` `…::start`; `:644` `…::free`;
  `:962` `OSKextLoadKextWithIdentifier("com.apple.iokit.IOStorageFamily")`;
  `NativeUfs.cpp:110` counts services by class name. So the dependency is one
  class, eight call sites, plus the kext-identifier load — the load is what makes
  the 27 fileset entry relevant at runtime even after a link fix.
- **No archive exists anywhere on this host.** Every `libNativeUfs.a` found is
  91,824–105,376 B (mac-build artifacts); the 556,720 B figure is the Linux
  producer's output recorded in `docs/engineering/IOS27.md:376-377`, not a file
  on disk now.
- **The producer cannot even dry-run here.** It rewrites the recorded clang argv
  from `build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json`;
  `find /e/hackios /e/k60-work -name KernelConfigTables.cpo.json` returns
  nothing, and `/opt/k60/trees/ios27-out` holds only `feeds ipsw mondrian
  state.json`.

So the arm64e member check is **not answerable offline today** — it needs one
artifact that only a build produces. The three commands that answer it, and
what they must print:

```sh
llvm-ar t build/native-ufs/libNativeUfs.a
# NativeUfs.o, PongUfsTransport.o, verified_root.o — three members, no .o.orig
llvm-nm --defined-only build/native-ufs/libNativeUfs.a | grep -E 'NativeUfs5start|PongUfsBlock'
# both present: the class start symbol is what scripts/check-kernel-archives.py:37 grades
python3 scripts/check-kernel-archives.py --kernel <out>/mondrian/…/kernel.macho
# today: FAIL: no kernel.macho under \opt\k60\trees\k60build\out-baseline (exit 2)
```

Member architecture cannot be read from `llvm-ar t`; the arch test is
`llvm-objdump --macho --private-headers` on the extracted member, expecting
`cputype 0x0100000c` (arm64e) — same expectation the kernel build record
enforces, since the producer copies its flags verbatim.

## 9. The triple: command, expected output, criterion

| claim | command | expected | criterion |
|---|---|---|---|
| selection, production and switch state | `python3 scripts/check-ufs27-storage-selection.py` | 3 GAP lines + `3 gap(s)` | exit 1 today; exit 0 only when all three close |
| recommended shape closes them | `bash E:/k60-work/scratch/ufs27-selcheck/run.sh` | `0 gap(s)` | exit 0 — the edited copy, never the real board |
| framework accepts the shape | probe in §3 (`components.selected` + `kernel.archive_plan` with `modules={}`) | `selected: [ArmDTPlatform, ArmCpu, XnuPrelink]`, `plan: 7 entries; last = ('script', 'build-native-ufs-linux.py --tree . --out build/native-ufs')` | no `unknown component`, no `needs component entries` |
| personality patch applies | `patch -p1 --dry-run -i 0542-k60-native-ufs-personality.patch` in a copy of `xnu-12377.121.6` | `checking file iokit/KernelConfigTables.cpp` | exit 0, no fuzz, no reject |
| personality content | `grep -c "IONameMatch'     = ufshc" iokit/KernelConfigTables.cpp` | `1` | exactly one entry, inside `#if defined(XNU_NATIVE_UFS)` |
| 27 series untouched | `git -C . diff --stat origin/feat/xnu27-data-gate -- patches/` | empty | stage 0 must not change shape |

## 10. Decisions this row needs from the Lead

1. **Stage 1 route** — A (script recipe, keep the vendored driver) or B (feed
   ShengUfs, swap driver identity). Everything in §3–§5 works with either, but
   only A keeps `drivers/NativeUfs`.
2. **Stage 3 timing** — is F3 the moment `CONFIG_XNU_NATIVE_UFS` stays `y`, or
   does the switch go to `n` until the storage-abi bindings object exists? The
   patch in §5 is inert either way; the archives entry is not.
3. **RamBlock** — record "excluded by design on the source-storage line" as the
   27 answer for that platform row, or schedule the `XNU_SOURCE_STORAGE=0` path
   as a separate configuration to keep the `native_ufs_store` callback alive.

Not needed from anyone: the personality patch (ready), the selection mechanism
(measured), the link path (already correct).
