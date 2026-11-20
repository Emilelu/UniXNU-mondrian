#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Do the symbols the audio glue exports already exist in this XNU tree?

The two glue files are added to bsd/dev of a tree they were not written in.
A private-sounding name is not proof of a private name: the tree keeps growing,
and a duplicate definition is a link error far from its cause. This script
compiles the glue against the portability stubs to learn what it exports, then
looks for those names anywhere in the kernel areas of the tree.

Two exemptions, both narrow: files the wiring installs (PongAudio*/PongCodec*)
and the one file apply-audio27-wiring.py --hook-init edits, recognised by the
comment it writes. Without the second one, a correctly hooked tree reports a
collision with its own call site.

usage: check-audio27-collisions.py <xnu-tree>
exit: 0 no clash, 1 a clash or an unreadable tree, 2 usage
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DRIVER = REPO / "drivers/PongAudio"
STUBS = REPO / "scripts/tests/portability"
SOURCES = ["PongAudioAmp.c", "PongAudioGeniI2c.c"]
AREAS = ("bsd", "osfmk", "pexpert", "iokit", "libkern")
OURS = re.compile(r"^(PongAudio|PongCodec)")
HOOK = "K60 audio amplifier probe"
DSB = '__asm__ volatile("dsb sy" ::: "memory");'


def exported(work):
    """The glue's externally visible symbols, learned from real objects."""
    objs = []
    for name in SOURCES:
        text = (DRIVER / name).read_text(encoding="utf-8")
        source = work / name
        source.write_text(text.replace(DSB, ""), encoding="utf-8")
        obj = work / (name + ".o")
        done = subprocess.run(["cc", "-std=gnu11", "-c", "-DXNU_PONG_AUDIO",
                               "-I", str(STUBS), "-I", str(DRIVER),
                               "-o", str(obj), str(source)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)
        if done.returncode != 0:
            raise SystemExit("collisions: cannot compile %s:\n%s" % (name, done.stdout))
        objs.append(str(obj))
    nm = os.environ.get("NM", "nm")
    done = subprocess.run([nm, "-g", "--defined-only"] + objs,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    if done.returncode != 0:
        raise SystemExit("collisions: %s failed:\n%s" % (nm, done.stdout))
    names = set()
    for line in done.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and re.match(r"^[TDBRSC]$", parts[1]):
            names.add(parts[2].lstrip("_"))
    return sorted(names)


def scan(root, names):
    """({name: [file:line]}, skipped hook files), ignoring the wiring's own files."""
    hits = {}
    skipped = []
    wanted = set(names)
    for area in AREAS:
        base = root / area
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in (".c", ".cpp", ".cc", ".h", ".s"):
                continue
            if OURS.match(path.name):
                continue
            try:
                if path.stat().st_size > 4 * 1024 * 1024:
                    continue
                body = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if HOOK in body:
                skipped.append(str(path.relative_to(root)))
                continue
            for number, line in enumerate(body.splitlines(), 1):
                for name in wanted:
                    if name in line:
                        hits.setdefault(name, []).append("%s:%d" % (path.relative_to(root), number))
    return hits, skipped


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    if len(argv) < 2:
        sys.stderr.write("usage: check-audio27-collisions.py <xnu-tree>\n")
        return 2
    root = pathlib.Path(argv[1])
    if not (root / "bsd").is_dir() and (root / ".cache/xnu-work/bsd").is_dir():
        root = root / ".cache/xnu-work"
    if not (root / "bsd").is_dir():
        print("collisions: no bsd/ under %s; that is not an XNU tree" % argv[1])
        return 1
    work = pathlib.Path(tempfile.mkdtemp(prefix="k60-coll-"))
    names = exported(work)
    hits, skipped = scan(root, names)
    if skipped:
        print("  (skipping the wiring hook: %s)" % ", ".join(sorted(skipped)))
    for name in names:
        if name in hits:
            print("  %-26s %s" % (name, ", ".join(hits[name][:4])))
    if hits:
        print("COLLISION: %d of %d glue symbols already appear in %s: %s"
              % (len(hits), len(names), root, ", ".join(sorted(hits))))
        return 1
    print("COLLISION OK: %d exported symbols, none of them in %s" % (len(names), root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
