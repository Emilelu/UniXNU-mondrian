#!/usr/bin/env python3
"""Counter-examples for the post-flip gate: every way the claim can be wrong, pinned.

The gate under test is `check-gpu27-postflip.py`. Each case runs it as a
subprocess, because the exit code *is* the contract: 0 the claim holds, 1 it is
contradicted, 2 nothing could be judged. A test that called main() in-process
would still pass if the script stopped calling sys.exit.

The last case is the one this file exists for: a flight that claims the flip and
carries no `scanout version=` at all must be red, not unmeasured. The judge
treats an absent field as unmeasured - right for a measurement nobody took - but
here the absence contradicts a claim the tree is making.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "check-gpu27-postflip.py")
FIXTURES = os.path.join(HERE, "fixtures")


def run(log, lane):
    command = [sys.executable, TOOL, os.path.join(FIXTURES, log),
               "--lane-root=" + os.path.join(FIXTURES, lane)]
    done = subprocess.run(command, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def case(name, log, lane, expected, needle):
    code, output = run(log, lane)
    if code != expected:
        raise SystemExit("%s: expected exit %d, got %d\n%s" % (name, expected, code, output))
    if needle not in output:
        raise SystemExit("%s: exit %d as expected but the reason is missing\n"
                         "  need: %s\n  got:  %s" % (name, expected, needle, output.strip()))
    print("ok  exit %d  %s  (%s)" % (code, name, needle))


def main():
    # The claim holds: the flight says version=2, the two copies of the asserts agree.
    case("the flip holds", "postflip-v2-ok.log", "lane-postflip-in-step", 0,
         "the two copies of the flip asserts agree")

    # The image still carries the v1 kext.
    case("still v1", "postflip-v2-still-v1.log", "lane-postflip-in-step", 1,
         "the frame line says version=1, not 2")

    # The field is absent: this is the red the judge would call unmeasured.
    case("no version field", "postflip-v2-no-version.log", "lane-postflip-in-step", 1,
         "none says `scanout version=`")

    # The tree falls behind the claim: one of the four asserts is gone.
    case("header half", "postflip-v2-ok.log", "lane-postflip-half", 1,
         "the header carries 3 of 4 v2 assertions")

    # Nothing to judge: the patch is in no series yet, so nothing has been flipped.
    case("pre-flip", "postflip-v2-ok.log", "lane-preflip", 2,
         "dormant")

    # Unreadable input is cannot-judge, never a pass.
    code, output = run("missing.log", "lane-postflip-in-step")
    if code != 2:
        raise SystemExit("missing log: expected exit 2, got %d\n%s" % (code, output))
    print("ok  exit 2  a missing log is cannot-judge")

    # A flight that never touched the scanout path cannot answer the question.
    empty = os.path.join(FIXTURES, "postflip-v2-empty.log")
    with open(empty, "w", encoding="utf-8", newline="") as handle:
        handle.write("# SYNTHETIC FIXTURE: a flight in which nothing reached the scanout path\n")
    try:
        code, output = run("postflip-v2-empty.log", "lane-postflip-in-step")
        if code != 2 or "never ran" not in output:
            raise SystemExit("empty flight: expected exit 2 and 'never ran', got %d\n%s"
                             % (code, output))
        print("ok  exit 2  a flight with no scanout line is cannot-judge")
    finally:
        os.remove(empty)

    print("\nTESTS OK: 7 cases (holds, still v1, no version field, header half, pre-flip, "
          "missing log, empty flight)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
