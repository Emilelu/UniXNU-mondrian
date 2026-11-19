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

    print("SERIES OK %s %d B sha256 %s matches the emitter%s"
          % (patch.name, len(booked), hashlib.sha256(booked).hexdigest(),
             "" if state else " (no series file here)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
