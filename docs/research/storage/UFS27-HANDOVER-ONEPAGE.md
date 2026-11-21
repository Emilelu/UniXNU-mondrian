# Storage on iOS 27 — one page, for the fileset-entry owner

Compressed from `UFS27-GATE.md` §13–§16 (742-line detail, all anchors there). Everything
below is static: measured by reading this checkout, no build, no `ld`, no device.

## What is being asked of you

Two things, in this order.

1. **⑦'s judgement path needs one product to exist** — a real F3 (27) build tree with a
   link line, plus the archive described below. Until then ⑦ stays `false`, and the gate
   says which input is missing rather than repeating a promise.
2. **The prelink ring that adds an entry is yours** — the storage driver cannot become a
   fileset entry until something can add one. The interface it has to satisfy is
   `storage/UFS27-RING5-CONTRACT.md`; the two proofs of why it is missing today are in
   `storage/UFS27-ROUTE-B-WIRING.md` §2.

## ⑦ waits on four inputs, each able to be pending alone

```sh
cd E:/k60-work/ufs27 && python3 scripts/check-ufs27-step7-readiness.py
#   PEND tree       no xnu object directory with .LDFLAGS + link.filelist is reachable
#   PEND cpo        no KernelConfigTables.cpo.json for this tree
#   PEND archive    build/native-ufs/libNativeUfs.a is not there yet
#   PEND stderr     no saved ld stderr pair (control, with archive)
#   OK   criterion  check-xnu27-storage-link.py still carries its six flags
# ufs27-step7-readiness: 0 gap(s) (pending is not a gap: nothing claims closure)
```

| Row | Needs | Why that shape |
| --- | --- | --- |
| `tree` | the object directory holding `.LDFLAGS` + `link.filelist` | `check-xnu27-storage-link.py:75` reads the recorded link line; a build that never linked cannot be graded |
| `cpo` | `build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json` with `arguments` + `directory` | `build-native-ufs-linux.py` replays that recorded compiler line instead of guessing one |
| `archive` | `libNativeUfs.a` with `NativeUfs.o`, `PongUfsTransport.o`, `verified_root.o` | members are read out of the header; "the file exists" is not "the producer finished" |
| `stderr` | a saved `ld` stderr pair | `--control-stderr`/`--archive-stderr` exist, and that is the only route that does not link |

On the 24A446 tree the first two are already real (`.LDFLAGS` 3,204 B, `link.filelist`
160,133 B, cpo with 536 args) and the run still lands on PEND — which is the point: 24A446
cannot stand in for F3, whose closure is measured on F3's own kernel. The gate never links;
it prints the command and exits 0 while pending, 1 only if something is present but wrong.

## The pass predicate (bt's, unchanged)

```sh
python3 scripts/check-xnu27-storage-link.py --tree "$OBJ" --archive "$ARCH" --out "$OUT" --require-linkable \
&& python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["archive_rc"]==0 and not r["new_symbols"] else 1)' "$OUT"
```

`OBJ` = the object directory (not the tree root), `ARCH` = the checkout root's
`build/native-ufs/libNativeUfs.a` (not the checker's default, which lands under
`.../tree/build/`), `OUT` = a report, not source. `--require-linkable` alone is **not** the
criterion: it only fails when `archive_rc != 0`, so a successful link that gains symbols
still prints OK. Three false passes worth naming: that flag alone; `new > 0` whose symbols
are all the `IOBlockStorageDevice` family (they clear only when the bindings enter the same
archive or the same force_load); grading one of two archives, since the checker takes one
`--archive`. PASS wording is `UFS27-STEP7-HANDOVER.md` §9; FAIL is never PENDING.

Stage 0's wording stays: *the archive is not linked, so the eleven imports never enter the
kernel link* — `26 vs 14` is an F3 measurement and is not quoted as this state.

## The two device rows the platform page names

**RamBlock** and **VerifiedRoot** have one shared precondition, and it is not a storage
decision: `XNU_NATIVE_AES=1` is refused unless the bootstrap is `prelinked` *and*
`XNU_SOURCE_CORECRYPTO14=1` (`scripts/build-xnu-generic.sh:199-203`); its two dependants
inherit that at `:221-227` and `:287-291`. **Lead ruling 2026-11-21: stage 0 keeps
`source`**, so all three switches are unreachable by construction on this profile — known
and accepted, not a blocker. Moving to `prelinked` is a separate change that belongs to the
crypto closure's producers.

Two facts survive that ruling, and they are what future work will meet:

- RamBlock's persistence callback does not exist: `drivers/NativeRamBlock/NativeRamBlock.cpp:35-40`
  declares six `weak_import`s (`native_ufs_store_mode/_open/_read/_write/_sync/_gpt_check`)
  and `:69-70` routes the persisted path through them; nothing in `drivers/` or `patches/`
  defines any of them, so a RAM disk would build, start, and silently keep pages in memory.
  The platform page asks for exactly this callback.
- VerifiedRoot's blocker is still the empty `UniXNU/scripts/policies/ipados-27.0.1-24A446/`,
  and the same crypto wall stands in front of it, so producing the bundle alone would not
  make the switch usable.

**VirtioMmioBlock** is a protocol driver with no device here (`components.toml:294-310`:
`scope = "protocol"`, `board_dependencies = []`, `verified_devices = []`; no `virtio`
string in `board.toml`, the 27 defconfig or `dts/mondrian.dts`; `CONFIG_XNU_ARMVIRT_PLATFORM=n`).
Its link is a third bare `test -f` at `:699-701`, not graded because the switch is
unreachable from this profile.

**ShengUfs** is the same `NativeUfs.cpp` under its upstream repository, not a second
driver (`components.toml:121-140`: `source_files = ["NativeUfs.cpp"]`,
`runtime_identifiers = ["NativeUfs", "NativeUfs.cpp", "org.blu-sharky.NativeUfs"]`,
`legacy_name = "NativeUfs"`). Its verified pairing is 17.7 on sheng (`:130`, `:132`), it
depends on `VirtioMmioBlock` + `VerifiedRoot`, and `E:/hackios/UniXNU-sheng` carries
`drivers/ShengUfs` as a single gitlink with an empty directory — so it cannot be built or
compared here. Keep the vendored driver.

## What the storage row is not asking for

No F3 diff ahead of bt's word, no `ld` run by this line, no edit to the vendored
`scripts/build-xnu-generic.sh` (the Lead owns its two bare `test -f` lines), and no change
to `board.toml` or the defconfig while the switch and its archive cannot land together.

Detail, transcripts and every file:line live in `UFS27-GATE.md` §13–§16,
`UFS27-STEP7-HANDOVER.md` (§5 criterion, §8 bt's PENDING turnover, §9 PASS wording),
`UFS27-RING5-CONTRACT.md` and `UFS27-ROUTE-B-WIRING.md`.
