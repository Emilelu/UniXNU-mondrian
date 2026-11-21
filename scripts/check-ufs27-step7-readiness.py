#!/usr/bin/env python3
"""Step 7 readiness: what the storage link closure still waits on.

Step 7 (⑦) of the eight-step pipeline asserts that the kernel links the storage
driver. On this branch that cannot be asserted yet, and not because of a missing
line: the 27 kernel image lives in a fileset entry, so `build/native-ufs/
libNativeUfs.a` brings eleven `IOBlockStorageDevice` symbols that only the sibling
entry `com.apple.iokit.IOStorageFamily` defines. The only measurement that means
anything is a link of the recorded kernel with and without the archive, which
needs a real 27 build. That is the Lead's to run (it invokes `ld`), so this script
does not link anything: it grades whether the inputs that measurement needs exist,
and prints the exact command for whoever may run it.

Rows (each independently pending, never merged into one green light):

  tree       the xnu object directory holding `.LDFLAGS` and `link.filelist`
             — `check-xnu27-storage-link.py:75` requires exactly that shape.
  stderr     a saved pair of `ld` stderrs (control, with archive). This is the only
             offline route (`--control-stderr`/`--archive-stderr`); without it the
             measurement has to link, and only the Lead may.
  archive    `build/native-ufs/libNativeUfs.a` with its three members. Read out of
             the archive itself, so "the file exists" is not mistaken for "the
             producer finished".
  cpo        the build record the producer reads:
             `build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json`
             with its `arguments` and `directory`. Without it
             `scripts/build-native-ufs-linux.py` cannot compile the archive at all.
  criterion  the predicate is expressible: `check-xnu27-storage-link.py` must still
             carry `--require-linkable`, `--tree`, `--out` and the two `--…-stderr`
             flags. If that script changes, the recorded criterion has to be
             re-read rather than trusted.

The criterion itself is bt's and is stricter than `--require-linkable`: that flag
only turns a gap into a failure when `archive_rc != 0`, so a successful link with
new symbols still prints OK. Closure therefore also requires the report's
`archive_rc == 0` and `new_symbols == []` — see `PASS_COMMAND`.

Exit code 0 while pending or ready, 1 when something is present but incoherent
(an archive with the wrong members, a stderr pair missing one half, a criterion
script that lost a flag). Absence is pending, not a gap: nothing claims closure.

Usage:
  python3 scripts/check-ufs27-step7-readiness.py [--archive PATH] [--tree PATH]

  --tree is the xnu OBJECT directory (the one with `.LDFLAGS` and
  `link.filelist`), not the tree root and not the parent of `ios-obj`. The
  producer's `--tree` is the tree root — the two flags mean different things.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
MEMBERS = ("NativeUfs.o", "PongUfsTransport.o", "verified_root.o")
LINK_CHECKER = "scripts/check-xnu27-storage-link.py"
FLAGS = ("--tree", "--archive", "--out", "--require-linkable", "--control-stderr", "--archive-stderr")
DEFAULT_ARCHIVE = REPO / "build" / "native-ufs" / "libNativeUfs.a"
DEFAULT_OUT = REPO / "out" / "xnu27-storage-link.json"
DEFAULT_SCRATCH = REPO.parent / "scratch" / "ufs27-link"
RECORD_GLOB = "build/xnu/ios-obj/*/iokit/DEVELOPMENT/KernelConfigTables.cpo.json"
PEND_TEXT = (
    "stage 0: CONFIG_XNU_NATIVE_UFS is n and no recipe writes "
    "$ROOT/build/native-ufs/libNativeUfs.a, so the force-load at "
    "scripts/build-xnu-generic.sh:646-653 does not happen and the eleven "
    "IOBlockStorageDevice imports are not in the kernel link. This proves the "
    "switch is off; it does not prove the link closes. PEND is not PASS."
)

PASS_CHECK = ("python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); "
              "sys.exit(0 if r[\"archive_rc\"]==0 and not r[\"new_symbols\"] else 1)' {out}")

problems: list[str] = []


def say(status: str, area: str, text: str) -> None:
    print(f"  {status:<4} {area:<10} {text}")


def ar_members(archive: Path) -> list[str]:
    """Member names out of a System V / GNU archive, without shelling out to ar.

    Names longer than 15 characters live in the `//` long-name table and the member
    header only carries `/<offset>`, which is exactly what the three storage objects
    need (`PongUfsTransport.o` is 18), so the table is resolved rather than skipped.
    """
    data = archive.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("not an ar archive")
    offset, names, table = 8, [], b""
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        if header[58:60] != b"`\n":
            raise ValueError(f"bad member header at {offset}")
        raw = header[0:16].decode("utf-8", "replace").strip()
        size = int(header[48:58].decode("ascii", "replace").strip() or "0")
        body = data[offset + 60 : offset + 60 + size]
        offset += 60 + size + (size & 1)
        if raw == "//":
            table = body
            continue
        if raw in ("/", "/SYM64/"):
            continue
        if raw.startswith("/") and raw[1:].isdigit():
            begin = int(raw[1:])
            finish = table.find(b"/\n", begin)
            names.append(table[begin : finish if finish >= 0 else len(table)].decode("utf-8", "replace"))
            continue
        names.append(raw.rstrip("/"))
    return names


def grade_tree(explicit: Path | None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env_tree = os.environ.get("K60_LINK_TREE")
    if env_tree:
        candidates.append(Path(env_tree))
    for base in (os.environ.get("K60_OUT"), REPO / "build" / "xnu" / "ios-obj"):
        if not base:
            continue
        root = Path(base)
        if not root.exists():
            continue
        candidates.extend(sorted(p for p in root.iterdir() if p.is_dir()))
        candidates.append(root)
    found: list[Path] = []
    for candidate in candidates:
        if (candidate / ".LDFLAGS").is_file() and (candidate / "link.filelist").is_file():
            found.append(candidate)
    if explicit is not None and explicit.exists() and explicit not in found:
        problems.append(f"--tree {explicit} exists but is not an xnu object directory: "
                        f"check-xnu27-storage-link.py needs both .LDFLAGS and link.filelist there")
        say("GAP", "tree", f"{explicit} has no .LDFLAGS/link.filelist pair")
        return None
    if not found:
        say("PEND", "tree", "no xnu object directory with .LDFLAGS + link.filelist is reachable from this "
                            "host; a real iOS 27 kernel build produces it (K60_OUT, or --tree)")
        return None
    say("OK", "tree", f"{found[0]} (.LDFLAGS + link.filelist)")
    return found[0]


def tree_root_from(objdir: Path) -> Path | None:
    """The tree root for an object dir: .../tree/build/xnu/ios-obj/<config> -> .../tree."""
    parts = objdir.resolve().parts
    if "ios-obj" in parts:
        index = parts.index("ios-obj")
        if index >= 3:
            return Path(*parts[: index - 2])
    return None


def grade_cpo(objdir: Path | None, explicit: Path | None) -> bool:
    root = explicit or (tree_root_from(objdir) if objdir is not None else None)
    if root is None:
        say("PEND", "cpo", "no tree root to look in; the producer reads "
                           f"{RECORD_GLOB} under it (pass --record-tree)")
        return False
    hits = sorted(root.glob(RECORD_GLOB))
    if not hits:
        problems.append(f"{root} has no {RECORD_GLOB}; scripts/build-native-ufs-linux.py cannot compile "
                        f"libNativeUfs.a without a recorded clang invocation")
        say("GAP", "cpo", f"{root} has no {RECORD_GLOB}")
        return False
    record = hits[0]
    try:
        payload, _ = json.JSONDecoder().raw_decode(record.read_text(encoding="utf-8", errors="replace"))
    except ValueError as error:
        problems.append(f"{record} is not readable JSON: {error}")
        say("GAP", "cpo", f"{record}: {error}")
        return False
    missing = [key for key in ("arguments", "directory") if key not in payload]
    if missing:
        problems.append(f"{record} lacks {', '.join(missing)}; the producer needs both")
        say("GAP", "cpo", f"{record} lacks {', '.join(missing)}")
        return False
    say("OK", "cpo", f"{record.relative_to(root).as_posix()} "
                     f"({len(payload.get('arguments') or [])} args, directory {payload['directory']})")
    return True


def grade_stderr() -> bool:
    control = Path(os.environ.get("K60_LINK_CONTROL_STDERR") or DEFAULT_SCRATCH / "control.stderr")
    arc = Path(os.environ.get("K60_LINK_ARCHIVE_STDERR") or DEFAULT_SCRATCH / "archive.stderr")
    have = (control.is_file(), arc.is_file())
    if all(have):
        say("OK", "stderr", f"saved pair present ({control}, {arc}); the measurement can run without linking")
        return True
    if any(have):
        missing = control if not control.is_file() else arc
        problems.append(f"only half of the saved ld stderr pair exists; missing {missing}")
        say("GAP", "stderr", f"half a pair: missing {missing}")
        return False
    say("PEND", "stderr", "no saved ld stderr pair, so the link has to be run to measure new symbols "
                          "(only the Lead may; this script never links)")
    return False


def grade_archive(explicit: Path | None) -> bool:
    archive = explicit or Path(os.environ.get("K60_NATIVE_UFS_ARCHIVE") or DEFAULT_ARCHIVE)
    if not archive.is_file():
        say("PEND", "archive", f"{archive} is not there yet; scripts/build-native-ufs-linux.py "
                               f"--out build/native-ufs writes it from a recorded KernelConfigTables.cpo.json")
        return False
    try:
        members = ar_members(archive)
    except ValueError as error:
        problems.append(f"{archive} is not a readable ar archive: {error}")
        say("GAP", "archive", f"{archive}: {error}")
        return False
    missing = [m for m in MEMBERS if m not in members]
    if missing:
        problems.append(f"{archive} lacks member(s) {', '.join(missing)}; it is not the three-member archive "
                        f"the producer describes")
        say("GAP", "archive", f"{archive} has {len(members)} member(s), missing {', '.join(missing)}")
        return False
    say("OK", "archive", f"{archive} ({len(members)} members, {archive.stat().st_size} bytes)")
    return True


def grade_criterion() -> list[str]:
    path = REPO / LINK_CHECKER
    if not path.is_file():
        problems.append(f"{LINK_CHECKER} is gone; the recorded criterion cannot be re-derived")
        say("GAP", "criterion", f"{LINK_CHECKER} is missing")
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    lost = [flag for flag in FLAGS if flag not in text]
    if lost:
        problems.append(f"{LINK_CHECKER} no longer accepts {', '.join(lost)}")
        say("GAP", "criterion", f"{LINK_CHECKER} lost {', '.join(lost)}")
        return []
    say("OK", "criterion", f"{LINK_CHECKER} still carries {len(FLAGS)} flags (--require-linkable among them)")
    return list(FLAGS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", type=Path, default=None, help="the xnu object directory (.LDFLAGS, link.filelist)")
    parser.add_argument("--archive", type=Path, default=None, help="the archive to force_load")
    parser.add_argument("--record-tree", type=Path, default=None,
                        help="tree root holding build/xnu/ios-obj/*/iokit/.../KernelConfigTables.cpo.json")
    args = parser.parse_args()

    print(f"ufs27-step7-readiness: {REPO}")
    tree = grade_tree(args.tree)
    have_cpo = grade_cpo(tree, args.record_tree)
    have_archive = grade_archive(args.archive)
    have_stderr = grade_stderr()
    flags = grade_criterion()

    print()
    if tree and have_archive and flags:
        archive = args.archive or Path(os.environ.get("K60_NATIVE_UFS_ARCHIVE") or DEFAULT_ARCHIVE)
        link = f"python3 {LINK_CHECKER} --tree {tree} --archive {archive} --out {DEFAULT_OUT} --require-linkable"
        if have_stderr:
            link = (
                f"CONTROL_RC=<n> ARCHIVE_RC=<n> python3 {LINK_CHECKER} --tree {tree} --archive {archive} "
                f"--control-stderr {Path(os.environ.get('K60_LINK_CONTROL_STDERR') or DEFAULT_SCRATCH / 'control.stderr')} "
                f"--archive-stderr {Path(os.environ.get('K60_LINK_ARCHIVE_STDERR') or DEFAULT_SCRATCH / 'archive.stderr')} "
                f"--out {DEFAULT_OUT} --require-linkable   # parses saved stderrs, does not link"
            )
        say("OK", "run", link + (
            "" if have_stderr else "   # links twice; only the Lead may run it"))
        say("OK", "pass", "&& " + PASS_CHECK.format(out=DEFAULT_OUT) + "   # --require-linkable alone is not the "
                          "criterion: a successful link with new symbols still prints OK")
    else:
        missing = [name for name, ok in (("tree", bool(tree)), ("cpo", have_cpo),
                                         ("archive", have_archive), ("criterion", bool(flags))) if not ok]
        say("PEND", "run", PEND_TEXT)
        print(f"         (pending on {', '.join(missing)}; the acceptance command is printed here the moment "
              f"they exist)")

    print()
    if os.name == "nt":
        print("  note: run this under WSL or Linux: .LDFLAGS and the cpo directory name /opt or /mnt/e paths, "
              "which a Windows Python cannot follow")
    print("  note: the checker takes one --archive; if F3 produces a driver archive and a bindings archive, "
          "merge them into one before grading, or new>0 will be read as closure")
    print("  note: out/xnu27-storage-link.json is a report, not source; do not commit it")

    if problems:
        print()
        for problem in problems:
            print(f"  note: {problem}")
        print(f"ufs27-step7-readiness: {len(problems)} gap(s)")
        return 1
    print("ufs27-step7-readiness: 0 gap(s) (pending is not a gap: nothing claims closure)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
