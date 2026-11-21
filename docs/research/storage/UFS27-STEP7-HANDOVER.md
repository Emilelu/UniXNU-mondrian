# Step ⑦ handover — the storage link closure, for bt to run

This sheet is self-contained: it names every input, every command and every criterion,
so it can be executed without reading the storage line's repository. It exists because
⑦ is a measurement of a real link, and only one session may run that link.

Status: **pending, not passed.** No closure is claimed here. The four answers below are
bt's own, given 2026-11-21; this sheet only writes them down as an executable procedure.

## 1. What ⑦ asserts, and what it does not

⑦ asserts that the recorded 27 kernel links with `build/native-ufs/libNativeUfs.a`
force-loaded and gains **no** new undefined symbols — i.e. the eleven
`IOBlockStorageDevice` imports (`__ZTV20IOBlockStorageDevice`, its meta-class, `init`,
`@free`, five dispatch slots) resolve instead of entering the link unresolved.

It does not assert that the driver boots, probes, or reads a volume. Those are later
steps.

Stage 0 stands exactly as bt wrote it, and this wording is to be used verbatim:

> PEND：stage 0 的 `CONFIG_XNU_NATIVE_UFS` 为 `n`，且没有 recipe 产出
> `$ROOT/build/native-ufs/libNativeUfs.a`；`scripts/build-xnu-generic.sh:646-653` 的
> force-load 未发生，11 个 `IOBlockStorageDevice` import 不在内核链接中。此状态只证明
> 开关关闭，不证明链接闭合；PEND 不是 PASS。

Do not quote `26 vs 14`: that pair is an F3 measurement, not this state. Do not write
"the archive is unlinked, so ⑦ passes".

## 2. The inputs, by exact shape

`--tree` on the link checker is the **xnu object directory** — the one that directly
holds `.LDFLAGS` and `link.filelist`. It is neither the tree root nor the parent of
`ios-obj`. The 24A446 tree's exact value:

```
OBJ=E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837
# WSL: /mnt/e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837
```

For F3, use the same relative shape under the F3 build tree. Both files are present in
the 24A446 tree (`.LDFLAGS` 3,204 B, `link.filelist` 160,133 B), which is why this path
is quoted with a measured size rather than as a template.

`--archive` is the archive under the **checkout root** that has `board.toml` and
`scripts/` — the same `$ROOT` as `scripts/build-xnu-generic.sh:646-653`:

```
ARCH=$REPO/build/native-ufs/libNativeUfs.a
```

Do not use the checker's default: it derives the path from the object directory's
`parents[3]`, which is `.../tree/build/native-ufs/` and is not necessarily `$ROOT`.
The documented shape is 556,720 B with three members (`NativeUfs.o`,
`PongUfsTransport.o`, `verified_root.o`). **This file does not exist on this host yet** —
that is unmeasured, not measured-and-fine. It is written by
`python3 scripts/build-native-ufs-linux.py --device <checkout> --tree <tree root> --out build/native-ufs`.

`--out` is a report, not source:

```
OUT=$REPO/out/xnu27-storage-link.json   # do not commit it
```

Its top level carries `archive`, `control_rc`, `archive_rc`, `control_undefined`,
`archive_undefined`, `new_symbols`, `storage_imports`, `hardware_verified` (false).

## 3. The prerequisite the producer needs: the build record

`build-native-ufs-linux.py` does not guess a compiler line; it replays the recorded one
from `build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json` (it needs both
`arguments` and `directory`). Without that record the archive cannot be produced at all.

The 24A446 record exists and was verified today:

```
E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/KernelConfigTables.cpo.json
  directory = /mnt/e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT
  arguments = 536
```

Read-only existence check for whichever tree is being graded (no writes, no compile):

```sh
python3 - "$TREE" <<'PY'
import json, pathlib, sys
tree = pathlib.Path(sys.argv[1])
f = sorted(tree.glob("build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json"))
if not f: raise SystemExit("MISSING cpo")
d, _ = json.JSONDecoder().raw_decode(f[0].read_text())
if "arguments" not in d or "directory" not in d: raise SystemExit("BAD cpo")
print(f[0]); print(d["directory"], len(d["arguments"]))
PY
```

The 24A446 record cannot stand in for F3: the closure has to be measured on the F3
tree's own kernel. Whether an F3 tree already carries this record is **undetermined** on
both sides; the probe above answers it.

## 4. The command

Run under WSL/Linux, not Windows Python: `.LDFLAGS` and the record's `directory` name
`/opt` or `/mnt/e` paths.

```sh
REPO=<checkout holding board.toml and scripts/build-xnu-generic.sh>
TREE=<27 build tree root, the one containing build/xnu/ios-obj>
OBJ="$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837"
ARCH="$REPO/build/native-ufs/libNativeUfs.a"
OUT="$REPO/out/xnu27-storage-link.json"

python3 scripts/check-xnu27-storage-link.py --tree "$OBJ" --archive "$ARCH" --out "$OUT" --require-linkable \
&& python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["archive_rc"]==0 and not r["new_symbols"] else 1)' "$OUT"
```

This command links the recorded kernel twice (control, then with the archive). It is the
F3 judgement, not a routine check, and it is not to be run while the offline constraint
is in force.

If a saved pair of `ld` stderrs exists, the same measurement can run without linking:

```sh
CONTROL_RC=<n> ARCHIVE_RC=<n> python3 scripts/check-xnu27-storage-link.py \
  --tree "$OBJ" --archive "$ARCH" \
  --control-stderr <control.stderr> --archive-stderr <archive.stderr> \
  --out "$OUT" --require-linkable
```

and the `new_symbols`/`archive_rc` check above still applies unchanged.

## 5. Expected output, and the criterion

The checker prints a row per link and ends with `bluetooth-storage-link: OK` on success;
the archive row reads `archive: rc=0 … new=0`.

Pass requires **all three**:

1. the composite command exits 0;
2. the report has `archive_rc == 0`;
3. the report has `new_symbols == []`.

Three things that do **not** pass, each because it looks like one:

- `--require-linkable` alone. It only turns a gap into a failure when `archive_rc != 0`.
  A successful link that gains new symbols still prints OK — hence the second command.
- "new > 0, but the new symbols are all the `IOBlockStorageDevice` family". Those eleven
  imports are the gap. They go away only when the bindings enter the **same** archive or
  the **same** force_load. `new > 0` is never closure.
- More than one archive. The checker accepts a single `--archive`. If F3 produces a
  driver archive plus a bindings archive, merge them into one first (or extend the
  checker); grading one of the two leaves the other's imports unmeasured.

## 6. What to hand back

A short report is enough, and every line is a fact the storage line cannot measure:

```
⑦ judgement (F3): PASS | FAIL
  OBJ  = <path>          # .LDFLAGS + link.filelist found?  y/n
  ARCH = <path>          # bytes, members
  OUT  = <path>          # archive_rc, len(new_symbols)
  cpo  = <path>          # present? arguments/directory?
  checker rc = <rc>; bluetooth-storage-link: <OK|…>
  if FAIL: new_symbols = [...] and the first file:line that would own each
```

For a pending result, hand back the same lines with `PENDING` and the missing input named
— no closure claim, no symbol counts, no `26/14`.

## 7. Where this sheet comes from

bt's four answers of 2026-11-21 (criterion, path shapes, cpo origin, PEND wording),
recorded here as a procedure so the storage line does not paraphrase them later. The
readiness side of the same subject — which inputs exist, and what is still missing — is
graded by `scripts/check-ufs27-step7-readiness.py`, whose rows (`tree`, `cpo`, `archive`,
`stderr`, `criterion`, `run`) print the command from §4 the moment the inputs are there.

Still undetermined after today: who runs the first F3 build and when its `cpo.json`
appears; whether F3's archive is one archive or two; and the exact wording bt wants in a
`PASS` report line (the `PEND` wording in §1 is bt's; a `PASS` wording is not yet set).
