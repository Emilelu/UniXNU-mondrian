#!/usr/bin/env python3
"""Counter-examples for check-gpu27-zero-copy.py.

Each case takes a fixture that is right and breaks exactly one thing the
criterion depends on, then insists the check notices. A dormant gate that only
ever says "dormant" proves nothing, which is why the direct fixture (PASS) and the
four broken ones exist beside it.

Run: python3 scripts/tests/test-check-gpu27-zero-copy.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CHECK = os.path.join(REPO, "scripts", "check-gpu27-zero-copy.py")
FIXTURES = os.path.join(HERE, "fixtures", "gpu27")


def run(path, *extra):
    proc = subprocess.run([sys.executable, CHECK, path] + list(extra),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return proc.returncode, proc.stdout


def expect(name, path, code, needle, *extra):
    got, output = run(path, *extra)
    ok = got == code and needle in output
    print("%-4s %-34s exit=%d (%s)" % ("ok" if ok else "FAIL", name, got, output.strip().splitlines()[0] if output.strip() else ""))
    if not ok:
        print("     wanted exit=%d and %r" % (code, needle))
        print("     " + output.replace("\n", "\n     "))
    return ok


def main():
    passed = True
    base = os.path.join(FIXTURES, "gpu27-zero-copy")

    passed &= expect("dormant: every frame copied", base + "-dormant.log", 0, "dormant:")
    passed &= expect("direct: the copy is gone", base + "-direct.log", 0, "the direct path ran")
    passed &= expect("a bench sample means a copy", base + "-with-bench.log", 1, "bench sample")
    passed &= expect("fallback still runs", base + "-mixed.log", 1, "fallback path")
    passed &= expect("too few samples to judge", base + "-insufficient.log", 2, "cannot judge")
    passed &= expect("strict: dormancy is failure", base + "-dormant.log", 1, "--strict", "--strict")

    # A direct line that still reports a copy is the subtle one: the imports say
    # zero but the GPU time says otherwise, and only the second field can tell.
    work = tempfile.mkdtemp(prefix="gpu27-zero-copy-")
    try:
        path = os.path.join(work, "copied.log")
        with open(base + "-direct.log", "r", encoding="utf-8") as src:
            text = src.read()
        with open(path, "w", encoding="utf-8", newline="\n") as out:
            out.write(text.replace("gpu=0 us sum=0 us", "gpu=1200 us sum=1200 us", 1))
        passed &= expect("imports=0 but gpu time is real", path, 1, "still report a GPU copy")

        empty = os.path.join(work, "empty.log")
        open(empty, "w").close()
        passed &= expect("no stage line at all", empty, 2, "cannot judge")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print()
    if not passed:
        print("TESTS FAILED")
        return 1
    print("TESTS OK: 8 cases (dormant, direct, bench, fallback, few samples, strict, copied-but-zero-imports, empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
