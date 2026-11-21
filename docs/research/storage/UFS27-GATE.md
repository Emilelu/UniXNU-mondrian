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

## 1. The gate is five stages, and four of them were broken

| # | stage | owner | anchor | now (after the 2026-11-21 fix) |
|---|---|---|---|---|
| 1 | selection | framework `components.selected()` | `board.toml:366` + `UniXNU/scripts/unixnu/components.py:22-45` | **fixed** — the list no longer names a legacy alias |
| 2 | recipe | framework `kernel.archive_plan()` / `build_archives()` | `board.toml:389` + `UniXNU/scripts/unixnu/kernel.py:107-175` | closed on purpose; the F3 diff is one entry |
| 3 | switch | device configs | `configs/mondrian_ios27_defconfig:25` | **fixed** — off, with the reason in the comment |
| 4 | link | framework generic builder | `scripts/build-xnu-generic.sh:646-653` | OK — path and guard were already right |
| 5 | bind | 27 XNU patch series | `iokit/KernelConfigTables.cpp` of `xnu-12377.121.6` | patch ready (0542), not in series until F3 |

Before the fix the same table read: selection GAP, recipe GAP, switch GAP
(switched on against no producer), link OK, bind GAP. The line numbers moved
because the fix added comment lines; `board.toml:361` and `:384` in the quoted
output below are the pre-fix ones.

Stage 4 was the only finished piece, and it is the one the Lead's brief blamed.
Read the block:

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

One correction to how a reader should hold this file: `scripts/build-xnu-generic.sh`
is a *vendored copy* — `scripts/refresh-xnu-generic.py:15` (TARGET) overwrites it
from a UniXNU checkout, because a device file named `build-xnu-4k-baseline.sh`
shadows the framework's builder in the assembled tree (P-255). So a change to the
link block belongs in the framework and arrives here through that refresh, while
`board.toml` and `configs/` belong to this repository. That is the split §10's
rulings use.

## 2. Stage 1 — the selection identifier could not resolve (fixed)

`board.toml:366` used to read `include = ["ArmDTPlatform", "ArmCpu",
"XnuPrelink", "NativeUfs"]`. `NativeUfs` is **not** a catalog id: it is the
`legacy_name` of `ShengUfs` (`UniXNU/components.toml:121`, `legacy_name` at
`:139`), whose archive is `build/sheng-ufs/libShengUfs.a` with
`legacy_outputs = { "build/native-ufs/libNativeUfs.a" = "build/sheng-ufs/libShengUfs.a" }`
(`:140`). A legacy identifier is accepted only when the framework already holds
a *module* for that component — `components.selected()` at
`UniXNU/scripts/unixnu/components.py:22-45`, `official_alias()` at `:87-95`
requires the module's git identity to be
`github.com/unixnu/shengufs` (or `…/nativeufs`) — and modules come from feeds.
This repository's `feeds.toml` declares exactly one source, `sm8475`; no feed,
submodule or `board.toml` pin names the ShengUfs repository. So selection aborted
before any recipe ran:

```sh
python3 scripts/check-ufs27-storage-selection.py     # before the fix
#   GAP  selection   board.toml:361 include 'NativeUfs' is ShengUfs's legacy name, but no feed
#                    or submodule names github.com/unixnu/shengufs -- components.selected()
#                    raises 'unknown component: NativeUfs' before any recipe runs
```

Confirmed against the framework itself, with `modules = {}` (the true state of a
checkout that never fetched that component): `unknown component: NativeUfs`.
The route that reaches it is the real one, not a hypothetical: the 27 line builds
through the framework — `scripts/build-ios27-linux.sh:60` runs
`python3 ./unixnu build kernel --device "$ROOT"` — so this abort stops the whole
profile, not just the storage row.

Two shapes could have fixed it, and they are not equivalent:

- **A (the ruling).** Drop `"NativeUfs"` from the include list; build the
  vendored `drivers/NativeUfs` through a script recipe (stage 2). This keeps the
  driver identity that the archive, the `#include`s and `patches/wifi/0004` all
  assume, and it needs no feed and no framework change. **Applied 2026-11-21**:
  the include is `["ArmDTPlatform", "ArmCpu", "XnuPrelink"]` and the comment above
  it records why the identifier must not come back.
- **B.** Add a feed that fetches `https://github.com/UniXNU/ShengUfs` so the
  alias resolves. That builds *Sheng's* driver from `drivers/ShengUfs` and
  symlinks its archive onto `build/native-ufs/libNativeUfs.a`. It is the 16.6.1
  mechanism, but it swaps which driver runs — rejected on 2026-11-21 because it
  would move the LUN table that already merged on `main`.

## 3. Stage 2 — nothing writes the archive

The producer exists and works from the tree's own compile record:
`scripts/build-native-ufs-linux.py` (docstring `:2-21` says "It reports; it does
not wire anything up"), three translation units, `DEFINES = ['XNU_NATIVE_UFS=1',
'XNU_SOURCE_STORAGE=1']`, `--out` default `out/native-ufs-linux`, `--tree`
required (`:72`). Measured against the 24A446 object tree it produces
`NativeUfs.o` 212,256 B, `PongUfsTransport.o` 331,112 B, `verified_root.o`
10,936 B and a 556,720-byte archive — within eight bytes of the 16.6.1 recipe
(`docs/engineering/IOS27.md:376-377`).

The 27 profile never calls it. `board.toml:389` lists eight entries
(`build-corecrypto-14.py`, `build-firehose-stub.py`, …) and no storage recipe,
while `defconfig:14` already carries `CONFIG_XNU_BUILD_ARCHIVES=y`, so the
archive stage does run — it just has nothing to run for storage. That is correct
for the closed state: the switch is off (§4), so nothing links and no recipe is
needed.

Fix, for F3 and only together with the switch: one list entry, with the output
directory the builder reads:

```toml
# board.toml:389, 27 override [os_overrides."ios-27.0.1-24A446".kernel].archives
archives = [ … , "build-fileset-release-reference.py --tree .",
             "build-native-ufs-linux.py --tree . --out build/native-ufs"]
```

`--out build/native-ufs` is not cosmetic: without it the recipe writes
`out/native-ufs-linux/libNativeUfs.a` and stage 4's `test -f` still fails.
Script entries are ordinary `[kernel] archives` citizens
(`UniXNU/scripts/unixnu/kernel.py:141-175` runs them with
`{'tree','component','out'}` substitution and then errors on any `*_ARCHIVE`
that never appeared), so this needs no framework edit.

## 4. Stage 3 — the switch and the archive must agree, and one of them moved

`configs/mondrian_ios27_defconfig:25` was `CONFIG_XNU_NATIVE_UFS=y` with no
producer anywhere in the profile — a switch that turns a missing recipe into a
link failure at the very end, after every other stage has run. It is `n` as of
2026-11-21, with the Lead's reason written above it:

```sh
sed -n '17,26p' configs/mondrian_ios27_defconfig
#   ... the eleven IOBlockStorageDevice symbols it imports are not exported
#   by the kernel collection, so the link needs the fileset-entry route first
#   (the bt line owns that route as of 2026-11-21).
#   Off on purpose: turning it on before build/native-ufs/libNativeUfs.a has a
#   producer makes the builder's test -f (build-xnu-generic.sh:648) fail, so the
#   switch would only open onto a missing artefact.
#   CONFIG_XNU_NATIVE_UFS=n
```

A 27 tree is meant to be in one of two coherent states, never a mixture:

| state | defconfig | `board.toml:366` include | `board.toml:389` archives | personality patch |
|---|---|---|---|---|
| closed (now) | `n` | no `"NativeUfs"` | no recipe | on the branch, inert |
| open (F3) | `y` | no `"NativeUfs"` | `build-native-ufs-linux.py --tree . --out build/native-ufs` | in series, `-DXNU_NATIVE_UFS=1` injected |

Note that the include list stays without `"NativeUfs"` in *both* states: under the
Lead's ruling of 2026-11-21 the driver is compiled by that script recipe out of
the vendored `drivers/NativeUfs/`, not resolved as a catalog component, so the
identifier has no business in the list at any stage. Ruling 1 also keeps
`feeds.toml` untouched: fetching `UniXNU/ShengUfs` would swap the driver source
and put the LUN table that already merged on `main` (`feat/ufs-verified-table`,
three-window contract, `check-ufs-verified-table.py`) at risk for no gain in this
stage.

The three states are graded, not described. One command builds three copies of
the profile differing only in these two edits and checks the verdict each must
produce:

```sh
cd /e/k60-work/scratch/ufs27-f3matrix && python3 make.py && sh run.sh
```

```
=== closed (expect 0 gap(s))
PASS: closed -> 0 gap(s), exit 0
=== open (expect 0 gap(s))
PASS: open -> 0 gap(s), exit 0
=== mixed (expect 1 gap(s))
  GAP  producer    configs/mondrian_ios27_defconfig:25 CONFIG_XNU_NATIVE_UFS=y, but board.toml:389 names no
       build-native-ufs-linux.py --out build/native-ufs ... the switch opens onto a missing artefact
PASS: mixed -> 1 gap(s), exit 1
```

So the F3 change is exactly two edits landed together — the recipe entry and the
switch — and `scripts/check-ufs27-storage-selection.py` refuses a tree that has
only one of them.

The personality column matters because the generic builder already injects the
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
| profile selection | `board.toml:366` include list | absent; the vendored copy is `drivers/NativeRamBlock/` (catalog path is `drivers/RamBlock`) |
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

Both switches are now graded by `scripts/check-ufs27-storage-switches.py` (§11).
Two facts it measures are worth having here:

- **The archive paths disagree between the two builders.** The generic builder
  reads `build/ram-block/libRamBlock.a` (`scripts/build-xnu-generic.sh:729`) and
  `build/verified-root-xnu/libVerifiedRootProbe.a` (`:766`); the only producers in
  this tree write `build/native-ram-block/`
  (`scripts/build-pong-ram-block-macos.py:25`) and `build/native-ufs/`
  (`scripts/build-pong-ufs-probe-macos.py:31`), which is exactly what the 16.6.1
  builder reads (`scripts/build-xnu-4k-baseline.sh:1145` for the RAM block,
  `:1054` for the UFS archive). Turning either switch on without a producer that
  writes the *generic* path stops the build at a `test -f`.
- **The verified-root probe archive has no producer at all.** The 16.6.1 line
  compiles `verified_root.c` and `xnu_crypto.c` into the UFS archive under a
  different switch name (`XNU_NATIVE_UFS_VERIFIED_ROOT`,
  `scripts/build-xnu-4k-baseline.sh:432`, passed to
  `build-pong-ufs-probe-macos.py --verified-root`), so `libVerifiedRootProbe.a`
  is a design nobody has implemented on this board yet.

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
| the tree is in a coherent state (closed or open, never mixed) | `K60_FRAMEWORK_REPO=E:/hackios/UniXNU python3 scripts/check-ufs27-storage-selection.py` | `ufs27-storage-selection: 0 gap(s)`, one `producer OK closed state` line, one `link NOTE` | exit 0; a `GAP` line means the switch and the archive disagree |
| all three states behave as described | `cd /e/k60-work/scratch/ufs27-f3matrix && python3 make.py && sh run.sh` | `PASS: closed -> 0`, `PASS: open -> 0`, `PASS: mixed -> 1`, matrix exit 0 | an `exit 1` here means the checker stopped distinguishing the states |
| the F3 diff is the whole F3 change | `python3 make.py` writes `open/` from the real files plus two edits | `open/` grades `0 gap(s)` with an `open state` line | no other edit is needed |
| framework accepts the shape | probe in §3 (`components.selected` + `kernel.archive_plan` with `modules={}`) | `selected: [ArmDTPlatform, ArmCpu, XnuPrelink]`, `plan: 7 entries; last = ('script', 'build-native-ufs-linux.py --tree . --out build/native-ufs')` | no `unknown component`, no `needs component entries` |
| personality patch applies | `patch -p1 --dry-run -i 0542-k60-native-ufs-personality.patch` in a copy of `xnu-12377.121.6` | `checking file iokit/KernelConfigTables.cpp` | exit 0, no fuzz, no reject |
| personality content | `grep -c "IONameMatch'     = ufshc" iokit/KernelConfigTables.cpp` | `1` | exactly one entry, inside `#if defined(XNU_NATIVE_UFS)` |
| 27 series untouched | `git -C . diff --stat origin/feat/xnu27-data-gate -- patches/` | empty | stage 0 must not change shape |
| the two platform-page switches are graded | `python3 scripts/check-ufs27-storage-switches.py` | `ufs27-storage-switches: 0 gap(s), 2 dormant (switch off; latent defects reported above)` — both guards OK, both dormant states OK, and the two bare `test -f` lines printed as `NOTE` with their line numbers | exit 0 while dormant; the moment a switch opens the same two lines become GAPs (fixture `latent`), and the framework fix is the patch in §11 and `storage/UFS27-SWITCH-GAP.md` |
| the three switch states behave as described | `cd /e/k60-work/scratch/ufs27-switchmatrix && python3 make.py && sh run.sh` | `PASS: closed -> 0`, `PASS: open -> 0`, `PASS: mixed -> 2`, matrix exit 0 | `exit 1` means the checker stopped distinguishing a guarded switch from an unguarded one |
| a bare `test -f` really is silent | `bash -euc 'test -f /nonexistent/archive.a'` | exit 1, **no output**; with `\|\| { echo …; exit 1; }` the same command names the path | what §11 criterion 3 grades, and why it is a defect rather than style |

## 10. Rulings of 2026-11-21, and what each one changed here

1. **Stage 1 route — A, the script recipe.** Keep the vendored `drivers/NativeUfs/`
   and compile it with `scripts/build-native-ufs-linux.py`; do not fetch
   `UniXNU/ShengUfs`, because that swaps the driver source under a LUN table that
   already merged on `main`. Applied: `"NativeUfs"` is out of
   `board.toml:366` for good (it is a legacy alias, not a component id).
2. **Stage 3 — off until the producer exists.** `CONFIG_XNU_NATIVE_UFS=n` at
   `configs/mondrian_ios27_defconfig:25` with the reason in the comment, so the
   failure the Lead named ("opens onto a missing artefact") is documented where
   the next reader will hit it. The F3 diff is the two edits in §4, landed
   together; the three-state matrix in §4 is the check.
3. **The eleven symbols go to the bt line, Route D.** This row does not build a
   second binding path. The handover is the five-stage table above plus §6; the
   patch `0542-k60-native-ufs-personality.patch` stays on this branch and out of
   `patches/xnu-12377/series` until F3.

Open inside this row, not blocked on anyone: the F3 diff itself (two lines, both
written down in §4), and the archive check once a 27 build leaves a
`KernelConfigTables.cpo.json` behind — only then can `build-native-ufs-linux.py`
run, and only then does the three-member/556,720-byte expectation in §8 become
testable.

Everything else that used to be listed here is settled or measured: the
personality patch is ready and dry-run verified, the selection mechanism is
measured against the framework's own code, and the link path was never the
broken piece.

## 11. The two platform-page switches, graded

Ruling (b) of 2026-11-21: an F3 diff prepared now would hang unverified until
the Route D criterion arrives, while a static gate is evidence that runs today
and can go red today. So `scripts/check-ufs27-storage-switches.py` grades the
other two storage archives the 27 builder can force-load, with the same exit
convention as the selection checker (0 clean, 1 gaps). It is the executable half
of §7.

Three criteria per switch, each measured rather than assumed:

1. **closed claim** — the archive assignment must sit inside an `if` on the
   switch. Measured: `scripts/build-xnu-generic.sh:728` guards
   `RAM_BLOCK_ARCHIVE` (`:729`) on `$NATIVE_RAM_BLOCK = 1`, and `:765` guards
   `VERIFIED_ROOT_ARCHIVE` (`:766`) on `$OWNER_ROOT_PROBE = 1`. Both `OK`: a
   closed 27 kernel never links either archive.
2. **open claim** — with the switch on, a `[kernel].archives` entry of the 27
   profile must name a script that exists in this checkout and write the
   directory the builder reads. Today both switches are off, so the verdict is
   `closed state`, and the line also records that the only producers write
   `build/native-ram-block/` and `build/native-ufs/` (§7). Note that
   `component:RamBlock` is *not* a free alternative: `archive_plan()` in
   UniXNU/scripts/unixnu/kernel.py:118-139 only expands components that
   `components.selected()` actually picked, and raises
   `[kernel] archives needs component entries for: …` for any picked component
   without an entry — the mirror image of the trap in §2.
3. **readable failure** — `test -f` on the archive must say what is missing.
   Measured: `scripts/build-xnu-generic.sh:730` and `:767` are bare, and the
   script runs under `set -euo pipefail` (`:9`), so
   `bash -euc 'test -f /nonexistent/archive.a'` exits 1 printing **nothing**.
   Both graded `GAP`.

Current verdict on the real tree: `ufs27-storage-switches: 0 gap(s), 2 dormant
(switch off; latent defects reported above)`, exit 0. The two silent failures are
printed as `NOTE` rows with their line numbers rather than as GAPs, because both
blocks are switched off and the `test -f` line is not reachable in that state —
grading it dormant would have made the gate red for a defect nobody can trigger
yet. This scoping was the Lead's instruction of 2026-11-21 (dormant exits 0 with a
note); it is a scope, not a relaxation: the fixture's `latent` state switches both
switches on with the line unpatched and must report the same two GAPs, and it does.
The line-by-line brief for the Lead is `storage/UFS27-SWITCH-GAP.md`, with the
patch `storage/UFS27-SWITCH-GAP.patch` (`patch -p1 --dry-run` exit 0). The fix is one line each:

```sh
test -f "$RAM_BLOCK_ARCHIVE" || { echo "build-xnu: NativeRamBlock is on but $RAM_BLOCK_ARCHIVE is missing" >&2; exit 1; }
test -f "$VERIFIED_ROOT_ARCHIVE" || { echo "build-xnu: the owner-root probe is on but $VERIFIED_ROOT_ARCHIVE is missing" >&2; exit 1; }
```

It is a **framework** change, not a device change: `scripts/refresh-xnu-generic.py:15`
overwrites this copy from a UniXNU checkout, so a local edit would be reverted by
the next refresh (P-255). The gate keeps failing until the framework carries it.

The preconditions are printed as `NOTE`, not graded, because they are ordering
decisions rather than this row's property: RamBlock refuses to link without
`XNU_NATIVE_AES=1` (`:221-227`) and is skipped entirely under
`XNU_SOURCE_STORAGE=1` (`:728`); VerifiedRoot refuses without
`XNU_SOURCE_CORECRYPTO14=1` and `XNU_CRYPTO_BOOTSTRAP=prelinked` (`:287-291`),
and the policy bundle it verifies against is the empty
`UniXNU/scripts/policies/ipados-27.0.1-24A446` (§7).

The fixture `E:/k60-work/scratch/ufs27-switchmatrix/` differs from the real tree
in exactly the F3-shaped edits, state by state:

| state | switches | recipe | builder `test -f` | verdict |
|---|---|---|---|---|
| `closed` | off | none | readable | `0 gap(s), 2 dormant` |
| `open` | on | writes both paths | readable | `0 gap(s)`, two `open state` lines |
| `mixed` | on | none | readable | `2 gap(s)`, `the switch opens onto a missing artefact` twice |
| `latent` | on | writes both paths | **bare** | `2 gap(s)`, the two silent `test -f` GAPs |

`make.py` copies the real `board.toml`, `feeds.toml`, defconfig and builder into
each state and applies only those edits; `run.sh` grades each against its
expected count. The readable `test -f` is applied in `closed`, `open` and `mixed`
because it is orthogonal to the switches, and deliberately withheld in `latent`
so that the dormant `NOTE` has a twin `GAP` proving the same line is graded the
moment it is reachable. Measured 2026-11-21: `closed 0 / open 0 / mixed 2 /
latent 2`, matrix exit 0.

## 12. ⑦ — what bt answered on 2026-11-21

Three corrections that change how this row states its own result:

1. **Stage 0 wording.** The measurable stage-0 fact is "the archive is not
   linked, so the eleven imports never enter the kernel link", not "eleven
   symbols stay undefined in the link". The 14 → 26 measurement belongs to F3,
   when the archive is force-loaded; stage-0 text must not quote 26, and must
   not call the undefined symbols "accepted".
2. **The F3 closure command exists but cannot run here.**
   `scripts/check-xnu27-storage-link.py --tree <ios27-obj> --archive
   build/native-ufs/libNativeUfs.a --out <report>.json --require-linkable`, with
   the pass predicate `exit 0`, archive row `new=0`, final
   `bluetooth-storage-link: OK`. It needs the archive **and** the
   `KernelConfigTables.cpo.json` record (§8), and it invokes `ld` on the recorded
   objects, which the lane contract counts as a build — so it is the Lead's call,
   not this row's. Without it, only the `docs/engineering/IOS27.md:385-396`
   numbers may be quoted, never "closed".
3. **`0542` is F3, not Route D.** It installs the `ufshc` personality and does
   not touch the eleven imports; it belongs in the same change as
   `CONFIG_XNU_NATIVE_UFS=y` and the archives recipe. It stays off
   `patches/xnu-12377/series` until then, and adding it early would move the
   series fingerprint.

The kext-entry alternative (route B) is a larger change than a link block, and
bt listed what it touches, which is what §1 stage 4 would become: the archive
turns into an `MH_KEXT_BUNDLE` (filetype 11) with `kmod_info`, `Info.plist`
gains `OSBundleLibraries` (`com.apple.iokit.IOStorageFamily`,
`com.apple.kec.corecrypto`) and the `ufshc` personalities, the force-load at
`scripts/build-xnu-generic.sh:646-653` goes away, `kits/XnuPrelink/emit_prelink_orig.py:117`
(accepts filetype 11 only) and `native_prelink.py:130` have to see the bundle as
a declared root, `[kernel.prelink] roots` has to list it, and acceptance becomes
`scripts/check-ios27-storage-entries.py --require-entry` reporting the entry
present with non-zero `kmod_info` start/stop. Route B does not define the eleven
symbols either — they stay Route D's — so it buys runtime loading, not link
closure.

## 13. ⑦'s judgement path, and what it waits on

The Lead's ruling of 2026-11-21 is that ⑦ takes the judgement path and waits: bt's
criterion and a real 27 build's product, no F3 diff written ahead of them. So ⑦ is
not a promise in prose — it is a readiness gate that says what is missing, in the
order the measurement needs it:

```sh
cd E:/k60-work/ufs27 && python3 scripts/check-ufs27-step7-readiness.py
#   PEND tree       no xnu object directory with .LDFLAGS + link.filelist is reachable from this host …
#   PEND archive    …/build/native-ufs/libNativeUfs.a is not there yet; scripts/build-native-ufs-linux.py writes it
#                   from a recorded KernelConfigTables.cpo.json
#   PEND stderr     no saved ld stderr pair, so the link has to be run to measure new symbols …
#   OK   criterion  scripts/check-xnu27-storage-link.py still carries 6 flags (--require-linkable among them)
#   PEND run        step 7 is pending on tree, archive; the acceptance command is printed here the moment they exist
# ufs27-step7-readiness: 0 gap(s) (pending is not a gap: nothing claims closure)
```

Four rows, each able to be pending on its own:

| Row | What it needs | Why that shape |
| --- | --- | --- |
| `tree` | a directory holding `.LDFLAGS` and `link.filelist` | `scripts/check-xnu27-storage-link.py:75` is explicit: `--tree` is "the xnu object directory holding .LDFLAGS and link.filelist". It reads the recorded link line, so a build that never linked cannot be graded. |
| `archive` | `build/native-ufs/libNativeUfs.a` with `NativeUfs.o`, `PongUfsTransport.o`, `verified_root.o` | the members are read out of the archive header. "The file exists" is not "the producer finished": a truncated or single-object archive would otherwise pass as prepared. |
| `stderr` | a saved pair of `ld` stderrs (control, with archive) | `--control-stderr`/`--archive-stderr` exist, and this is the only route that does not link. Without a pair the measurement has to run `ld`, which only the Lead may do. This is the one row file existence cannot judge, so its shape is fixed in `storage/UFS27-STEP7-HANDOVER.md` §10: `ARCHIVE_RC=0` and `new=[]` and a non-empty control set and two different files and both newer than the archive and `--require-linkable`; everything else is `PEND`, and `new != []` is the gap itself. |
| `criterion` | `check-xnu27-storage-link.py` still carrying `--tree`, `--archive`, `--out`, `--require-linkable` and the two stderr flags | a criterion is only worth what its script's interface is. If that script changes, the recorded predicate has to be re-read instead of trusted. |

The gate never links anything: no `subprocess` to `ld`, no kernel, no build. It
prints the acceptance command and the pass predicate, and it exits 0 while pending
because absence is not a gap — nothing claims closure. It exits 1 only when
something is present but wrong: an archive with the wrong members, half a stderr
pair, an object directory without a link line, or a criterion script that lost a
flag.

The pass predicate, unchanged from bt's answer (§12): `exit 0`, the archive row
reports `new=0`, and the last line is `bluetooth-storage-link: OK`. The wording for
stage 0 stays "the archive is not linked, so the eleven imports never enter the
kernel link" — the `26 vs 14` pair is an F3 measurement and is not quoted as this
state.

The gate itself is graded, so it cannot rot into a script that only ever prints
`PEND`:

```sh
cd E:/k60-work/scratch/ufs27-step7matrix && bash run.sh
# PASS: real tree -> pending, 0 gap(s), exit 0
# PASS: incoherent -> 3 gaps, exit 1
# PASS: ready -> green with the acceptance command, exit 0
# ufs27-step7matrix: OK
```

The `ready` fixture carries the three-member archive (written with a real `//`
long-name table, because `PongUfsTransport.o` is 18 characters), a `.LDFLAGS` +
`link.filelist` pair and a full stderr pair, and the gate prints the offline
command — the one that parses saved stderrs instead of linking. That row is the
proof that the moment the Lead's build produces the inputs, this gate becomes an
answer rather than a report.

## 14. bt's four answers, and the rows they turned into

bt answered the four questions on 2026-11-21 (criterion, path shapes, cpo origin, PEND
wording). Three of them changed this gate rather than merely confirming it, and the sheet
that carries them for bt to execute is `storage/UFS27-STEP7-HANDOVER.md`.

**The criterion is stricter than `--require-linkable`.** bt's point: that flag only turns
a gap into a failure when `archive_rc != 0`, so a link that succeeds while gaining new
undefined symbols still prints OK. Closure therefore needs the report read too:

```sh
python3 scripts/check-xnu27-storage-link.py --tree "$OBJ" --archive "$ARCH" --out "$OUT" --require-linkable \
&& python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["archive_rc"]==0 and not r["new_symbols"] else 1)' "$OUT"
```

with `OBJ=$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837` (the object directory, not
the tree root), `ARCH=$REPO/build/native-ufs/libNativeUfs.a` (the checkout root, not the
checker's default, which derives `parents[3]` and lands under `.../tree/build/`), and
`OUT=$REPO/out/xnu27-storage-link.json` (a report; do not commit it). The gate's `run` row
now prints exactly that pair, and its `pass` row now carries the report check instead of
the sentence "new=0" alone.

**A new row: `cpo`.** The producer does not guess a compiler line, it replays the recorded
one from `build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json`. So the gate
derives the tree root from the object directory (`.../tree/build/xnu/ios-obj/<cfg>` →
`.../tree`) or takes `--record-tree`, globs that record, and requires both `arguments` and
`directory`. Measured today on the 24A446 tree: the record exists with 536 arguments and a
`/mnt/e/...` directory, and the object directory exists with `.LDFLAGS` (3,204 B) and
`link.filelist` (160,133 B):

```sh
python3 scripts/check-ufs27-step7-readiness.py \
  --tree 'E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837'
#   OK   tree       …/DEVELOPMENT_ARM64_BCM2837 (.LDFLAGS + link.filelist)
#   OK   cpo        build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/KernelConfigTables.cpo.json (536 args, …)
#   PEND archive    E:\\k60-work\\ufs27\\build\\native-ufs\\libNativeUfs.a is not there yet …
#   PEND stderr     no saved ld stderr pair …
#   OK   criterion  … 6 flags (--require-linkable among them)
# ufs27-step7-readiness: 0 gap(s) (pending is not a gap: nothing claims closure)
```

That run is the useful distinction: the two 24A446 inputs are real, and the run still
lands on PEND because the archive and the saved stderr pair are not. The 24A446 record
also cannot stand in for F3 — the closure is measured on the F3 tree's own kernel — and
who produces the first F3 build, or when, is undetermined on both sides.

**The PEND wording is bt's, verbatim**, and replaced the gate's own sentence: stage 0 has
`CONFIG_XNU_NATIVE_UFS` off and no recipe writing
`$ROOT/build/native-ufs/libNativeUfs.a`, so the force-load at
`scripts/build-xnu-generic.sh:646-653` does not happen and the eleven
`IOBlockStorageDevice` imports are not in the kernel link — which proves the switch is
off, not that the link closes. `26 vs 14` stays unquoted.

**Three ways to mistake a report for closure**, now printed as notes by the gate and
argued in the handover: `--require-linkable` alone; `new > 0` whose symbols all belong to
the `IOBlockStorageDevice` family (they clear only when the bindings enter the same
archive or the same force_load); and grading one of two archives, since the checker takes
a single `--archive`.

The fixture grew a fourth case so the new row cannot hide behind a pending run row:
`nocpo/` is coherent except for the build record and must report exactly one gap.

```sh
cd E:/k60-work/scratch/ufs27-step7matrix && bash run.sh
# PASS: real tree -> pending, 0 gap(s), exit 0
# PASS: incoherent -> 3 gaps, exit 1
# PASS: nocpo -> 1 gap (the build record), exit 1
# PASS: ready -> green with the acceptance command, exit 0
# ufs27-step7matrix: OK
```

**First turnover from bt: PENDING.** bt read the sheet and kept the criterion unchanged,
returning §6's six lines as pending — F3's object directory, its cpo, the three-member
archive and a saved stderr pair are all absent, and the 24A446 inputs are explicitly not
substituted for them. The full text and the input table are in
`storage/UFS27-STEP7-HANDOVER.md` §8. Nothing in that answer contradicts this gate's rows:
`tree`, `cpo`, `archive`, `stderr` are the same four, which is the reason the gate was
written as rows rather than as a paragraph.

## 15. The other two rows, re-checked beyond §7

§7 listed the integration points. Re-reading them against the source turned up three
facts that §7 did not have, and one of them changes what "deliberately excluded" means
for RamBlock. All three are static: no build, no `ld`, no device.

**One precondition gates both rows.** `XNU_NATIVE_AES=1` is itself refused unless
`CRYPTO_BOOTSTRAP_MODE == prelinked` and `XNU_SOURCE_CORECRYPTO14 == 1`
(`scripts/build-xnu-generic.sh:199-203`); the RamBlock gate then refuses unless
`XNU_NATIVE_AES=1` (`:221-227`), and the VerifiedRoot gate refuses unless the same pair
holds (`:287-291`). The 27 defconfig sets `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"`
(`configs/mondrian_ios27_defconfig:12`) and does not set
`CONFIG_XNU_SOURCE_CORECRYPTO14` at all, while the 16.6.1 file sets both (`:12`
`prelinked`, `:73` `SOURCE_CORECRYPTO14=n` — off, and `NATIVE_AES=n` at `:15`). So on 27
**neither switch can be turned on at all**: the build aborts before any archive lookup,
with "NativeRamBlock requires the qualified original storage/AES prelink closure" or "The
owner crypto probe requires the qualified original prelinked crypto provider". Flipping
them is a crypto-bootstrap decision, not a storage one — that is the single barrier, and
it belongs to whoever owns the 27 bootstrap mode.

**The persistence callback does not exist.** `drivers/NativeRamBlock/NativeRamBlock.cpp:35-40`
declares six weak imports — `native_ufs_store_mode`, `_open`, `_read`, `_write`, `_sync`,
`_gpt_check` — and `:69-70` routes the persisted read/write path through them. A grep of
`drivers/` and `patches/` finds **no definition** of any of the six. `weak_import` means
the link will not complain: the RAM disk builds, starts, and silently keeps every changed
page in memory. The platform page's row asks for exactly this callback ("implement
`native_ufs_store` persistence callback"); measured today, nothing in this tree implements
it, so "persistent Data" has no writer.

**The "source storage owns the RAM disk" exclusion is not in force, and its premise is
false.** The builder skips RamBlock when `XNU_SOURCE_STORAGE=1` with the comment "the RAM
disk is part of the source storage archive, which also starts it"
(`scripts/build-xnu-generic.sh:220-221`). On 27 that variable is not set at all — the
defconfig has no `CONFIG_XNU_SOURCE_STORAGE` — so the exclusion does not apply; and the
archive it points at is built from three sources only
(`scripts/build-native-ufs-linux.py:29-33`: `NativeUfs.cpp`, `PongUfsTransport.cpp`,
`verified_root.c`), with no `NativeRamBlock.cpp`. Even with source storage on, the RAM disk
would not be in that archive. The comment describes an arrangement that would have to be
built, not one that exists.

What that changes for planning: §7 said RamBlock is "a decision to record, not work to
do". Half right. Turning the switch on is (today) impossible without the crypto decision,
and turning it on would still deliver a RAM disk whose persistence is a row of null weak
imports. VerifiedRoot's blocker stays what §7 said — an empty
`UniXNU/scripts/policies/ipados-27.0.1-24A446/` — but it now has a second precondition in
front of it, so producing the policy bundle alone would not make the switch usable.

## 16. The other two names in row 2: VirtioMmioBlock and ShengUfs

Row 2 of the platform page names four services. Two are covered above (RamBlock,
VerifiedRoot); these are the other two, and each turns out to be a boundary rather than a
piece of work for this profile.

**VirtioMmioBlock is not this board's device, and it shares the same wall.** The catalog
entry (`UniXNU/components.toml:294-310`) is `scope = "protocol"`, hardware "VirtIO 1.2
modern MMIO split queues", `board_dependencies = []`, `verified_devices = []`. The board's
own files never mention it: `grep -n 'virtio' board.toml configs/mondrian_ios27_defconfig
dts/mondrian.dts` returns nothing, and the 27 defconfig sets `CONFIG_XNU_ARMVIRT_PLATFORM=n`
— there is no virtio-mmio node for it to bind. Its builder gate is the same
`XNU_NATIVE_AES=1` requirement (`scripts/build-xnu-generic.sh:208-213`), so on 27 it is
blocked by the same crypto question before it is even relevant. Note also that its link
line is a **third** bare `test -f` (`:699-701`, `VIRTIO_ARCHIVE`) of the class the Lead
owns at `:730`/`:767`; it is not graded by the switch checker because the switch is not
reachable from this board's profile at all.

**ShengUfs is the upstream home of the driver this repo vendors, not a second driver — and
it cannot be checked out here.** The catalog entry (`:121-140`) is `source_files =
["NativeUfs.cpp"]`, `runtime_identifiers = ["NativeUfs", "NativeUfs.cpp",
"org.blu-sharky.NativeUfs"]`, `legacy_name = "NativeUfs"`, `legacy_outputs` mapping
`build/native-ufs/libNativeUfs.a` → `build/sheng-ufs/libShengUfs.a`. That is the same file
name and the same runtime identifiers as the vendored `drivers/NativeUfs/` — the alias is
honest about identity, which is exactly why the earlier failure was confusing: a component
that is the same driver under a different repository path.

Three consequences, measured:

1. `os_abi = ["ipados-17.7.11-21H461"]` and `verified_devices = ["sheng"]`: the catalog's
   own verified pairing is 17.7 on another board, not 27 on this one.
2. `dependencies = ["VirtioMmioBlock", "VerifiedRoot"]`. That is why selecting `ShengUfs`
   drags in both — the earlier probe printed `selected […, 'VirtioMmioBlock',
   'VerifiedRoot', 'ShengUfs']` and then `[kernel] archives needs component entries for:
   ShengUfs, VirtioMmioBlock`. Choosing the feed route would not swap one driver for
   another; it would add a 17.7-verified tree plus a protocol driver this board has no
   device for.
3. The upstream tree is not on this host: in `E:/hackios/UniXNU-sheng`, `git ls-files
   drivers/ShengUfs` returns exactly one entry — a gitlink, with the directory empty. So a
   swap would need a fetch or submodule init, which the offline rule forbids, and the
   source could not even be compared byte for byte against the vendored copy today.

**Conclusion (Lead ruling, 2026-11-21): stage 0 keeps `source`.** The 27 bootstrap does not
change; a move to `prelinked` would have to move the crypto closure's producers and is a
separate change, not part of the storage row. So `XNU_NATIVE_AES`, `XNU_NATIVE_RAM_BLOCK` and
`XNU_VERIFIED_ROOT_PROBE` are **unreachable by construction on this profile**, and that is a
known, accepted fact — not a blocker and not an open question. §15's three findings stay as the
evidence for why; the question file is closed by this sentence.

That closes row 2: ShengUfs is the same source under its upstream name (not a candidate),
VirtioMmioBlock is a protocol driver with no device here, RamBlock is unreachable behind the
accepted `source` bootstrap and has no persistence provider, VerifiedRoot is behind the same
accepted wall and an empty policy bundle.
