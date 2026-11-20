#!/usr/bin/env python3
"""Host cases for check-audio27-loglines.py."""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts", "check-audio27-loglines.py")
DOC = "docs/research/audio/IOS27-MIGRATION.md"
GOOD = "PongAudio: amp probe done found=2/2"
BAD = "PongAudio: amp probe finished without a table"
PRINTF = 'printf("PongAudio: amp probe done found=%u/%u", a, b);'


def tree(root, quote=GOOD, printf=PRINTF, chain=False, docs=True):
    if docs:
        path = os.path.join(root, DOC)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write("The run prints `%s` when both amplifiers answer.\n" % quote)
    if printf:
        source = os.path.join(root, "drivers", "PongAudio", "PongAudioAmp.c")
        os.makedirs(os.path.dirname(source), exist_ok=True)
        with open(source, "w") as handle:
            handle.write("void f(void) {\n    %s\n}\n" % printf)
    if chain:
        os.makedirs(os.path.join(root, "patches", "audio"), exist_ok=True)
    return root


def run(root):
    done = subprocess.run([sys.executable, GATE, root],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def case_printed(root):
    code, out = run(tree(root))
    assert code == 0, out
    assert "LOGLINES OK" in out, out


def case_bogus(root):
    code, out = run(tree(root, quote=BAD, chain=True))
    assert code == 1, out
    assert "which no printf prints" in out, out
    assert DOC + ":1" in out, out


def case_chain_absent(root):
    code, out = run(tree(root, quote=BAD))
    assert code == 0, out
    assert "LOGLINES NOTE" in out, out
    assert "patches/audio is not on this branch" in out, out


def case_no_docs(root):
    code, out = run(tree(root, docs=False))
    assert code == 1, out
    assert "has no docs/" in out, out


def case_no_printf(root):
    code, out = run(tree(root, printf=None))
    assert code == 1, out
    assert "no PongAudio printf" in out, out


CASES = [case_printed, case_bogus, case_chain_absent, case_no_docs, case_no_printf]


def main():
    failed = 0
    for case in CASES:
        root = tempfile.mkdtemp(prefix="loglines-")
        try:
            case(root)
        except AssertionError as error:
            failed += 1
            print("FAIL " + case.__name__ + ": " + str(error))
        finally:
            shutil.rmtree(root, ignore_errors=True)
    if failed:
        print("TESTS FAILED: %d of %d" % (failed, len(CASES)))
        return 1
    print("TESTS OK %d cases" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
