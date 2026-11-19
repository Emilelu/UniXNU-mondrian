#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Compare the 27 series copy of the audio call-site patch with the emitter.

One block has three copies: the applier's INIT_BLOCK (the source of truth),
the patch this lane handed over, and the copy the 27 series carries once the
Lead books it.  The first two are pinned by test-emit-audio27-patch.py and the
preflight's digest row.  This script covers the third: it emits the patch
again from a 27 tree and compares the bytes with the file in the series.

Exit codes: 0 the two agree, 1 they differ or the patch is not listed in the
series file, 3 the series has not booked the patch yet (nothing to compare,
and not a failure).
"""
import argparse
import hashlib
import importlib.util
import os
import pathlib
import re
import sys

NAME = re.compile(r"^0531-.*audio.*\.patch$")
DEFAULT = "/mnt/e/hackios/k60-gates/patches/xnu-12377"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def listed(series, name):
    """True when the series file names this patch; None when there is no file."""
    index = series / "series"
    if not index.is_file():
        return None
    for line in index.read_text(errors="replace").splitlines():
        text = line.split("#")[0].strip()
        if text and os.path.basename(text) == name:
            return True
    return False



HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def hunks(path, only=None):
    """Old-file hunk ranges per file, optionally limited to some files."""
    found = {}
    current = None
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
        elif line.startswith("@@") and current:
            match = HUNK.match(line)
            if not match:
                continue
            if only is not None and current not in only:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            found.setdefault(current, []).append((start, max(count, 1)))
    return found


def order(series, patch):
    """Does an earlier patch edit the lines the call site needs as context?

    The call site is a context-based hunk, so a patch ahead of it that rewrites
    the same few lines can make 0531 unappliable even though both are valid on
    their own. That is a property of the series, not of a build, so it is
    checked here: for every patch listed before this one, compare the old-file
    ranges it touches with the ranges this patch needs. A unified hunk already
    spans its three lines of context on either side, so the spans compare
    directly.
    """
    index = series / "series"
    if not index.is_file():
        return None
    names = [os.path.basename(line.split("#")[0].strip())
             for line in index.read_text(errors="replace").splitlines()]
    names = [name for name in names if name]
    if patch.name not in names:
        return None
    mine = hunks(patch)
    if not mine:
        return None
    problems = []
    checked = 0
    for name in names[:names.index(patch.name)]:
        other = series / name
        if not other.is_file():
            continue
        theirs = hunks(other, set(mine))
        if not theirs:
            continue
        checked += 1
        for path, ranges in theirs.items():
            for start, count in ranges:
                for mine_start, mine_count in mine[path]:
                    if (start <= mine_start + mine_count - 1
                            and mine_start <= start + count - 1):
                        problems.append((name, path, start, mine_start, mine_count))
    for name, path, start, mine_start, mine_count in problems:
        print("SERIES FAILED: %s edits %s:%d, inside the context %s:%d-%d needs;"
              " the series order decides whether the call site still applies"
              % (name, path, start, path, mine_start, mine_start + mine_count))
    if problems:
        return 1
    print("SERIES ORDER OK: %d earlier patch(es) touch the same files, none inside"
          " the call site context" % checked)
    return 0

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("tree", help="pristine XNU source tree the patch targets")
    parser.add_argument("--series", default=None,
                        help="27 series directory (XNU27_SERIES overrides the default)")
    args = parser.parse_args(argv[1:])

    series = pathlib.Path(args.series or os.environ.get("XNU27_SERIES") or DEFAULT)
    if not series.is_dir():
        print("series: %s is not on this machine" % series)
        return 3
    found = sorted(p for p in series.iterdir() if p.is_file() and NAME.match(p.name))
    if not found:
        print("series: no 0531 audio patch in %s yet; the Lead books it and the"
              " emitter is the source" % series)
        return 3
    if len(found) > 1:
        print("series: %d audio patches in %s: %s"
              % (len(found), series, ", ".join(p.name for p in found)))
        return 1

    patch = found[0]
    here = pathlib.Path(__file__).resolve().parent
    emitter = load("audio_emitter", here / "emit-audio27-patch.py")
    wiring = emitter.load_wiring(here / "apply-audio27-wiring.py")
    try:
        emitted, stripped = emitter.emit(pathlib.Path(args.tree), wiring)
    except LookupError as error:
        print("series: cannot emit from %s: %s" % (args.tree, error))
        return 1

    booked = patch.read_bytes()
    want = emitted.encode("utf-8")
    if booked != want:
        print("SERIES FAILED: %s differs from the emitter (series %s, emitter %s);"
              " regenerate with scripts/emit-audio27-patch.py"
              % (patch.name, hashlib.sha256(booked).hexdigest()[:16],
                 hashlib.sha256(want).hexdigest()[:16]))
        return 1

    state = listed(series, patch.name)
    if state is False:
        print("SERIES FAILED: %s is in %s but the series file does not list it,"
              " so the build never applies it" % (patch.name, series))
        return 1

    if order(series, patch) == 1:
        return 1

    print("SERIES OK %s %d B sha256 %s matches the emitter%s"
          % (patch.name, len(booked), hashlib.sha256(booked).hexdigest(),
             "" if state else " (no series file here)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
