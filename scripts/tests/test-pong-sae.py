#!/usr/bin/env python3
"""Offline verification for the SAE authentication framing unit (drivers/PongWifi/ath11k/pong_sae.c).

Compiles the unit with its host self-test, runs it, then checks the constants and the anchors in
scripts/build-k60-ath11k.py that put the probe into the generated station source. Exit code 0 means
every check passed; the summary format matches scripts/tests/test-pong-he.py.
"""
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "drivers/PongWifi/ath11k"
HEADER = SRC / "pong_sae.h"
UNIT = SRC / "pong_sae.c"
SELFTEST = pathlib.Path(__file__).resolve().parent / "pong-sae-selftest.c"
BUILDER = ROOT / "scripts/build-k60-ath11k.py"

checks = 0
failures = []


def check(ok, what):
    global checks
    checks += 1
    if ok:
        print("  PASS " + what)
    else:
        failures.append(what)
        print("  FAIL " + what)


def main():
    for path in (HEADER, UNIT, SELFTEST, BUILDER):
        if not path.is_file():
            print("FAIL: missing %s" % path)
            return 1
    text = HEADER.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    check("#define PONG_SAE_ALG 3" in text, "the algorithm number is SAE's own (3)")
    check("#define PONG_SAE_SEQ_COMMIT 1" in text, "the first frame is a commit (transaction sequence 1)")
    check("#define PONG_SAE_BODY_HEADER 6" in text, "the authentication header is six bytes")
    check("#define PONG_SAE_GROUP_19 19" in text and "#define PONG_SAE_GROUP_20 20" in text, "both elliptic-curve groups are named")
    check("PONG_SAE_MAX_BODY 256" in text, "the body buffer covers group 20's 150 bytes")
    check("uint8_t" in text and "#include <linux/" not in text, "the header needs no kernel header")
    check("0x9eu" in unit, "the payload filler is deterministic and obviously not a commit")

    with tempfile.TemporaryDirectory() as td:
        exe = pathlib.Path(td) / "pong-sae-selftest"
        cc = subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-I", str(SRC), str(UNIT), str(SELFTEST), "-o", str(exe)],
            capture_output=True, text=True)
        check(cc.returncode == 0, "the unit and its self-test compile clean" + ("" if cc.returncode == 0 else ": " + cc.stderr.strip()[:300]))
        if cc.returncode == 0:
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            m = re.search(r"(\d+) checks passed, (\d+) failed", run.stdout)
            check(run.returncode == 0, "the self-test exits zero")
            check(m is not None, "the self-test reports its counts")
            if m:
                check(int(m.group(1)) >= 12, "the self-test runs at least twelve checks")
                check(int(m.group(2)) == 0, "the self-test reports no failure")
            print("    " + run.stdout.strip().replace("\n", "\n    "))

    builder = BUILDER.read_text(encoding="utf-8")
    check("pong_sae.c" in builder, "the builder compiles the unit")
    for anchor, what in (
        ("pong_sae.h", "the generated station includes the unit"),
        ("nw_wifi_sae_probe", "the station exports the probe gate"),
        ("k60 sae: sending authentication", "the probe logs the frame it sends"),
        ("k60 sae: access point answered", "the probe logs an authentication answer"),
    ):
        check(anchor in builder, what)

    print("%d checks, %d failure(s)" % (checks, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
