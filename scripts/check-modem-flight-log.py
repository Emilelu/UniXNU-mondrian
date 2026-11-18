#!/usr/bin/env python3
"""Judge a modem flight console log against the pre-written criteria.

The criteria live in docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md
section 4; this script only applies them, so a flight verdict does not depend
on how carefully someone greps the log afterwards.

Phases:
  p1  power-only diagnostic (pong_modem=4): rails only, no PAS command
  c   metadata-only diagnostic (pong_modem=3): init_image and mem_setup, no
      power, no transport, no auth_reset
  b   full bring-up (pong_modem=2): S3 requires power/init/transport/mem/auth,
      S4 requires the QRTR glink descriptor and a DMS revision

Exit status is 0 only when every group of the requested phase passes.
"""
import argparse
import re
import sys

POWER_RE = re.compile(
    r"K60MODEM power ok cx=(0x[0-9a-fA-F]+)/(\d+) mss=(0x[0-9a-fA-F]+)/(\d+) "
    r"xo=(0x[0-9a-fA-F]+)/(\d+)")
INIT_RE = re.compile(r"K60MODEM init_image ok metadata=0x([0-9a-fA-F]+) bytes=(\d+)")
TRANSPORT_RE = re.compile(
    r"K60MODEM transport ok smp2p=0x[0-9a-fA-F]+/\d+ desc=0x[0-9a-fA-F]+/\d+ "
    r"tx=0x[0-9a-fA-F]+/\d+")
MEM_RE = re.compile(r"K60MODEM mem_setup ok base=0x([0-9a-fA-F]+) span=0x([0-9a-fA-F]+)")
DMS_RE = re.compile(r"K60MODEM qrtr: dms revision (\S+)")

FAILED_LINES = (
    "K60MODEM power failed",
    "K60MODEM init_image failed",
    "K60MODEM transport failed",
    "K60MODEM mem_setup failed",
    "K60MODEM auth_reset failed",
)


def one_line(text, needle):
    found = text.count(needle)
    if found == 1:
        return None
    return 'expected exactly one "%s", found %d' % (needle, found)


def one_match(regex, text, label):
    found = regex.findall(text)
    if len(found) == 1:
        return found[0], None
    return None, "expected exactly one %s, found %d" % (label, len(found))


def absent(text, needle):
    found = text.count(needle)
    if found == 0:
        return None
    return 'unexpected "%s" (found %d)' % (needle, found)


def check_power(text, problems):
    match, problem = one_match(POWER_RE, text, "K60MODEM power ok line")
    if problem:
        problems.append(problem)
        return
    if match[5] != "3":
        problems.append("xo vote is %s, expected the literal 3 (PongModemRuntime.cpp:159)"
                        % match[5])


def check_p1(text):
    problems = []
    check_power(text, problems)
    for needle in (
        "K60MODEM power prepared",
        "K60MODEM diagnostic stop after power: init_image not sent",
    ):
        problem = one_line(text, needle)
        if problem:
            problems.append(problem)
    for needle in ("K60MODEM init_image", "K60MODEM mem_setup", "K60MODEM auth_reset",
                   "K60MODEM transport"):
        problem = absent(text, needle)
        if problem:
            problems.append(problem)
    for needle in FAILED_LINES:
        problem = absent(text, needle)
        if problem:
            problems.append(problem)
    return [("P1", problems)]


def check_c(text):
    problems = []
    match, problem = one_match(INIT_RE, text, "K60MODEM init_image ok line")
    if problem:
        problems.append(problem)
    elif match != ("b7ff0000", "5884"):
        problems.append("init_image metadata=%s bytes=%s, expected 0xb7ff0000/5884"
                        % (match[0], match[1]))
    match, problem = one_match(MEM_RE, text, "K60MODEM mem_setup ok line")
    if problem:
        problems.append(problem)
    elif match != ("8bc00000", "13200000"):
        problems.append("mem_setup base=0x%s span=0x%s, expected 0x8bc00000/0x13200000"
                        % (match[0], match[1]))
    problem = one_line(text, "K60MODEM diagnostic stop after mem_setup: auth_reset not sent")
    if problem:
        problems.append(problem)
    for needle in ("K60MODEM power ok", "K60MODEM power prepared", "K60MODEM auth_reset",
                   "K60MODEM transport"):
        problem = absent(text, needle)
        if problem:
            problems.append(problem)
    for needle in FAILED_LINES:
        problem = absent(text, needle)
        if problem:
            problems.append(problem)
    return [("C", problems)]


def check_b(text):
    s3 = []
    check_power(text, s3)
    for needle in ("K60MODEM power prepared", "K60MODEM auth_reset ok"):
        problem = one_line(text, needle)
        if problem:
            s3.append(problem)
    match, problem = one_match(INIT_RE, text, "K60MODEM init_image ok line")
    if problem:
        s3.append(problem)
    elif match != ("b7ff0000", "5884"):
        s3.append("init_image metadata=%s bytes=%s, expected 0xb7ff0000/5884"
                  % (match[0], match[1]))
    match, problem = one_match(TRANSPORT_RE, text, "K60MODEM transport ok line")
    if problem:
        s3.append(problem)
    match, problem = one_match(MEM_RE, text, "K60MODEM mem_setup ok line")
    if problem:
        s3.append(problem)
    elif match != ("8bc00000", "13200000"):
        s3.append("mem_setup base=0x%s span=0x%s, expected 0x8bc00000/0x13200000"
                  % (match[0], match[1]))
    for needle in FAILED_LINES:
        problem = absent(text, needle)
        if problem:
            s3.append(problem)

    s4 = []
    problem = one_line(text, "K60MODEM qrtr: glink desc=")
    if problem:
        s4.append(problem)
    match, problem = one_match(DMS_RE, text, "K60MODEM qrtr: dms revision line")
    if problem:
        s4.append(problem)
    elif match == "none":
        s4.append("dms revision is the placeholder 'none'")
    for needle in ("K60MODEM qrtr: modem not ready", "K60MODEM qrtr: dms revision missing"):
        problem = absent(text, needle)
        if problem:
            s4.append(problem)
    return [("S3", s3), ("S4", s4)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("p1", "c", "b"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("log")
    args = parser.parse_args(argv)
    try:
        with open(args.log, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as error:
        print("check-modem-flight-log: %s" % error, file=sys.stderr)
        return 2
    groups = {"p1": check_p1, "c": check_c, "b": check_b}[args.phase](text)
    failures = 0
    for name, problems in groups:
        verdict = "PASS" if not problems else "FAIL"
        if not args.quiet or problems:
            print("%s: %s" % (name, verdict))
        for problem in problems:
            print("  %s" % problem)
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
