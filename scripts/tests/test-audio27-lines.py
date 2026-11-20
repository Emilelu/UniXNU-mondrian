#!/usr/bin/env python3
"""Host cases for check-audio27-lines.py."""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts", "check-audio27-lines.py")
AMP = "drivers/PongAudio/PongAudioAmp.c"
DOC = "docs/research/audio/IOS27-WIRING.md"
MARKS = {
    63: "#if defined(PONG) || defined(XNU_PONG_AUDIO)",
    105: chr(9) + "__asm__ volatile(\"dsb sy\" ::: \"memory\");",
    111: chr(9) + "delay_for_interval(us, NSEC_PER_USEC);",
    955: chr(9) + 'printf("PongAudio: amp probe start");',
    1004: chr(9) + 'printf("PongAudio: amp probe done found=%u/2");',
}


def source(moved=None):
    body = ["/* filler %d */" % i for i in range(1, 1020)]
    for number, text in MARKS.items():
        body[number - 1] = text
    if moved:
        body[moved - 1] = "/* moved away */"
    return chr(10).join(body) + chr(10)


def tree(root, cited="63", moved=None):
    path = os.path.join(root, AMP)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(source(moved))
    doc = os.path.join(root, DOC)
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w") as handle:
        handle.write("banner `PongAudioAmp.c:%s`" % cited + chr(10))
    return root


def run(root):
    done = subprocess.run([sys.executable, GATE, root],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def case_holds(root):
    code, out = run(tree(root))
    assert code == 0, out
    assert "LINES OK 5 anchors hold and 1 citation(s) point at them" in out, out


def case_stale_citation(root):
    code, out = run(tree(root, cited="921"))
    assert code == 1, out
    assert "which no anchor covers" in out, out


def case_moved_token(root):
    code, out = run(tree(root, moved=955))
    assert code == 1, out
    assert "no longer holds" in out, out
    assert "nowhere" in out, out


def case_no_source(root):
    root = tree(root)
    os.remove(os.path.join(root, AMP))
    code, out = run(root)
    assert code == 1, out
    assert "is not on this branch" in out, out


def case_no_docs(root):
    root = tree(root)
    shutil.rmtree(os.path.join(root, "docs"))
    code, out = run(root)
    assert code == 1, out
    assert "has no docs/" in out, out


CASES = [case_holds, case_stale_citation, case_moved_token, case_no_source, case_no_docs]


def main():
    failed = 0
    for case in CASES:
        root = tempfile.mkdtemp(prefix="lines-")
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
