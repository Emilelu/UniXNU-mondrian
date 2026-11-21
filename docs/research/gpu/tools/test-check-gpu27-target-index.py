#!/usr/bin/env python3
"""Exercise check-gpu27-target-index.py, including the two ways to be wrong.

A dormant gate without counter-examples is not a gate (P-290): if both fixtures
below still passed, the gate could never tell the two index readings apart, and
the first double-buffered flight would be the test instead.

Cases:
  1. index+1 convention, consumer writes db[frame.target]      -> 1 (off by one)
  2. raw convention,     consumer writes db[frame.target - 1]  -> 1 (one early)
  3. index+1 convention, consumer writes db[frame.target - 1]  -> 0 (allowed)
  4. the real tree today                                       -> 0 dormant
  5. the document without its marker                           -> 2 cannot judge
  6. --strict on a dormant tree                                -> 1
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
GATE = os.path.join(HERE, "check-gpu27-target-index.py")
FIXTURES = os.path.join(HERE, "fixtures")


def run(*args):
    result = subprocess.run([sys.executable, GATE, "--repo", REPO, *args],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def expect(name, want, *args, needle=None):
    code, output = run(*args)
    if code != want:
        print("FAIL %s: exit %d, wanted %d" % (name, code, want))
        print(output.strip())
        return False
    if needle and needle not in output:
        print("FAIL %s: %r not in output" % (name, needle))
        print(output.strip())
        return False
    return True


def main():
    ok = True
    ok &= expect("off by one", 1, "--convention", "index_plus_one",
                 "--scan", os.path.join(FIXTURES, "consumer-missing-minus-one.c"),
                 needle="contradict")
    ok &= expect("one early under a raw index", 1, "--convention", "index",
                 "--scan", os.path.join(FIXTURES, "consumer-minus-one-under-raw.c"),
                 needle="contradict")
    ok &= expect("allowed shape", 0, "--convention", "index_plus_one",
                 "--scan", os.path.join(FIXTURES, "consumer-correct.c"),
                 needle="PASS")
    ok &= expect("real tree dormant", 0, needle="DORMANT")
    ok &= expect("strict turns dormant into a failure", 1, "--strict")

    with tempfile.TemporaryDirectory() as scratch:
        doc = os.path.join(scratch, "GPU-27-V2-FIELDS.md")
        with open(doc, "w", encoding="utf-8") as handle:
            handle.write("# no marker here\n")
        code, output = run("--doc", doc, "--scan", os.path.join(FIXTURES, "consumer-correct.c"))
        if code != 2 or "CANNOT JUDGE" not in output:
            print("FAIL drifted document: exit %d %r" % (code, output.strip()))
            ok = False

    # The json form has to carry the same verdict, not a summary of it.
    code, output = run("--convention", "index_plus_one",
                       "--scan", os.path.join(FIXTURES, "consumer-missing-minus-one.c"), "--json")
    try:
        report = json.loads(output)
    except ValueError:
        report = {}
    if code != 1 or report.get("state") != "contradicted" or not report.get("lines"):
        print("FAIL json form: exit %d %r" % (code, output.strip()[:200]))
        ok = False

    if not ok:
        return 1
    print("TESTS OK: 6 cases (off by one, one early, allowed, dormant, strict, drifted document, json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
