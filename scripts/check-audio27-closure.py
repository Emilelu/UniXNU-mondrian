#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Compare the applier's copy set with the headers the compiler really opens.

apply-audio27-wiring.py decides what to copy from the #include lines it can see.
That is a reading of the source, not the compiler's answer, and the two differ
the moment a header reaches another header or a source includes one with angle
brackets: the applier copies nine files, the in-tree build stops on the tenth,
and nothing in the tree says why. This runs the same two sources through
"cc -MM" against the portability stubs and compares the two sets.

  python3 scripts/check-audio27-closure.py [--repo DIR]

Red when the compiler opens a Pong header the applier does not copy. Amber
(printed, not red) when the applier copies a header nothing opens: that is dead
weight, not a broken build.
"""
import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
BARRIER = '__asm__ volatile("dsb sy" ::: "memory");'
PATTERN = re.compile(r"\bPong(?:Audio|Codec)\w*\.h\b")
SOURCES = ("PongAudioAmp.c", "PongAudioGeniI2c.c")


def applier(root):
    path = root / "scripts/apply-audio27-wiring.py"
    if not path.is_file():
        raise SystemExit("closure: %s has no scripts/apply-audio27-wiring.py" % root)
    spec = importlib.util.spec_from_file_location("audio27_wiring", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def opened(root, work):
    """The Pong headers the compiler opens for the two glue sources."""
    driver = root / "drivers/PongAudio"
    sources = []
    for name in SOURCES:
        source = driver / name
        if not source.is_file():
            raise SystemExit("closure: %s is missing from %s" % (name, driver))
        copy = work / name
        copy.write_text(source.read_text(errors="replace").replace(BARRIER, ""))
        sources.append(str(copy))
    command = ["cc", "-std=gnu11", "-MM", "-DXNU_PONG_AUDIO",
               "-I", str(root / "scripts/tests/portability"),
               "-I", str(driver)] + sources
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    if done.returncode != 0:
        raise SystemExit("closure: the compiler refused the glue:" + chr(10) +
                         done.stderr.strip())
    return sorted(set(PATTERN.findall(done.stdout)))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=pathlib.Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    module = applier(root)
    copied = {name for name in module.kernel_set(root / "drivers/PongAudio")
              if name.endswith(".h")}
    with tempfile.TemporaryDirectory() as tmp:
        seen = opened(root, pathlib.Path(tmp))
    missing = [name for name in seen if name not in copied]
    for name in missing:
        print("CLOSURE: the compiler opens %s; the applier does not copy it" % name)
    if missing:
        print("CLOSURE FAILED: %d header(s) in the compiler's closure, %d in the copy set"
              % (len(missing), len(copied)))
        return 1
    stale = sorted(name for name in copied if name not in seen)
    note = "" if not stale else "; copied but never opened: " + ", ".join(stale)
    print("CLOSURE OK: %d headers, the applier copies what the compiler opens%s"
          % (len(seen), note))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
