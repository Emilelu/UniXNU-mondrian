#!/usr/bin/env python3
"""Judge four realistic console captures and check the exit code of each.

The inline self-test exercises the matcher; these fixtures exercise the whole
command, including the window arithmetic over a log that carries a real wait
stamp every five seconds. A PASS fixture that the judge refuses would waste a
flight slot, and a short capture that reads FAILED would report a verdict the
window does not support.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(os.path.dirname(HERE), "judge-cellular-flight.py")
FIXTURES = os.path.join(HERE, "fixtures")

CASES = (("k60-flight-pass.log", 0, "PASS"),
         ("k60-flight-refused.log", 1, "FAILED"),
         ("k60-flight-nolun.log", 1, "FAILED"),
         ("k60-flight-short.log", 2, "INVALID"))


def main():
    for name, want_exit, want_verdict in CASES:
        path = os.path.join(FIXTURES, name)
        if not os.path.exists(path):
            print("K60 FIXTURES FAIL %s is missing" % name)
            return 1
        result = subprocess.run([sys.executable, JUDGE, path],
                                capture_output=True, text=True)
        if result.returncode != want_exit:
            print("K60 FIXTURES FAIL %s exit %d, wanted %d\n%s" %
                  (name, result.returncode, want_exit, result.stdout[-400:]))
            return 1
        if ("VERDICT: " + want_verdict) not in result.stdout:
            print("K60 FIXTURES FAIL %s did not print VERDICT: %s" % (name, want_verdict))
            return 1
    print("K60 FIXTURES PASS four console captures judged end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
