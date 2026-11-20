#!/usr/bin/env python3
"""Judge five synthetic console fixtures and check every command exit code.

The inline self-test exercises the matcher; these fixtures exercise the whole
command, including a wait stamp every five seconds. Their LUN, partition and
physical-address values are test inputs, not observations of the device. Both
legacy and strict W2 acceptance are checked without claiming a hardware result.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(os.path.dirname(HERE), "judge-cellular-flight.py")
FIXTURES = os.path.join(HERE, "fixtures")

CASES = (("k60-flight-pass.log", 0, "PASS", ()),
         ("k60-flight-pass.log", 0, "PASS", ("--require-efs-bytes",)),
         ("k60-flight-refused.log", 1, "FAILED", ()),
         ("k60-flight-nolun.log", 1, "FAILED", ()),
         ("k60-flight-short.log", 2, "INVALID", ()),
         ("k60-flight-nohead.log", 1, "FAILED", ("--require-efs-bytes",)),
         ("k60-flight-nohead.log", 0, "PASS", ()),
         ("k60-flight-badhead.log", 1, "FAILED", ()),
         ("k60-flight-badhead.log", 1, "FAILED", ("--require-efs-bytes",)))


def main():
    for name, want_exit, want_verdict, extra in CASES:
        path = os.path.join(FIXTURES, name)
        if not os.path.exists(path):
            print("K60 FIXTURES FAIL %s is missing" % name)
            return 1
        result = subprocess.run([sys.executable, JUDGE, path] + list(extra),
                                capture_output=True, text=True)
        if result.returncode != want_exit:
            print("K60 FIXTURES FAIL %s exit %d, wanted %d\n%s" %
                  (name, result.returncode, want_exit, result.stdout[-400:]))
            return 1
        if ("VERDICT: " + want_verdict) not in result.stdout:
            print("K60 FIXTURES FAIL %s did not print VERDICT: %s" % (name, want_verdict))
            return 1
    print("K60 FIXTURES PASS nine runs over six synthetic console fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
