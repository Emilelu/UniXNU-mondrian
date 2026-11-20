#!/usr/bin/env python3
"""Check the counts the power documents quote against the things that own them.

P-259: prose that repeats a current value rots silently. The worst offender in
this line was "共 10 个套件，合计 1915 项断言（203/140/...）" - a sentence that
went stale twice in one week, once because a suite was added and once because
the per-suite list no longer summed to the total. Every number below is owned
somewhere else, so this gate reads the owner and the sentence:

  suite count, total and the per-suite list  <- scripts/tests/run-k60-power-host.sh
  "N 个策略模块"                               <- docs/research/power/CARRY.toml
  "N 个控制台判读器"                            <- docs/research/power/CARRY.toml
  "power-python: OK (N suites)"                <- the run_py lines of the same runner
  "N 行 file:line 引用、M 行带独立第二来源"        <- docs/research/power/HW-CONTRACTS.toml
  "[hardware.power].image_os"                  <- board.toml [package.defconfig] + W11-IMAGE.toml

A sentence that disappears is a failure, not a pass: otherwise renaming a
heading silently drops the coverage, which is how P-179's gates went hollow.
Exit 0 all agree, 1 disagreement or missing sentence, 2 an input cannot be read.
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = "docs/research/power/00-POWER-PAGE-CONFORMANCE.md"
CARRY = "docs/research/power/CARRY.toml"
CONTRACTS = "docs/research/power/HW-CONTRACTS.toml"
RUNNER = "scripts/tests/run-k60-power-host.sh"
EIGHT_STEPS = "docs/research/EIGHT-STEPS.toml"
BOARD = "board.toml"
W11_IMAGE = "docs/research/charger/W11-IMAGE.toml"

DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}

NUM = r"(?:[零一二两三四五六七八九十]+|\d+)"
SUITES = re.compile(r"共\s*(?P<count>" + NUM + r")\s*个套件，合计\s*(?P<total>\d+)\s*项断言（(?P<list>[0-9/]+)）")
MODULES = re.compile(r"(?P<count>" + NUM + r")\s*个策略模块")
JUDGES = re.compile(r"(?P<count>" + NUM + r")\s*个控制台判读器")
PYTHON = re.compile(r"power-python: OK \((?P<count>\d+) suites\)")
CONTRACTS_LINE = re.compile(r"(?P<rows>\d+)\s*行 file:line 引用、(?P<seconds>\d+)\s*行带独立第二来源")


def number(text):
    return int(text) if text.isdigit() else chinese(text)


def chinese(text):
    """Parse the numerals these documents actually use (1-99, no 零 padding)."""
    if not text or any(char not in DIGITS and char != "十" for char in text):
        raise ValueError(text)
    if text == "十":
        return 10
    if "十" not in text:
        return sum(DIGITS[char] * (10 ** index) for index, char in enumerate(reversed(text)))
    tens, _, ones = text.partition("十")
    return (DIGITS[tens] if tens else 1) * 10 + (DIGITS[ones] if ones else 0)


def runs(root):
    """(suite, checks) for every C suite the runner compiles and runs."""
    found = []
    for line in (root / RUNNER).read_text(encoding="utf-8").splitlines():
        if line.startswith("run ") and not line.startswith("run_py "):
            parts = line.split()
            if len(parts) >= 3 and parts[2].isdigit():
                found.append((parts[1], int(parts[2])))
    return found


def python_runs(root):
    return [line.split()[1] for line in (root / RUNNER).read_text(encoding="utf-8").splitlines()
            if line.startswith("run_py ") and len(line.split()) >= 4]


def verify(root):
    problems = []
    doc = (root / DOC).read_text(encoding="utf-8")
    suites = runs(root)
    if not suites:
        return ["%s declares no C suites; the gate would pass vacuously" % RUNNER]

    match = SUITES.search(doc)
    if not match:
        problems.append("%s no longer carries the '共 N 个套件，合计 T 项断言（…）' sentence; "
                        "update the pattern instead of dropping the check" % DOC)
    else:
        try:
            count = number(match.group("count"))
        except ValueError:
            count = None
            problems.append("cannot read the suite count %r" % match.group("count"))
        if count is not None and count != len(suites):
            problems.append("%s says %d suites, the runner declares %d (%s)"
                            % (DOC, count, len(suites), ", ".join(name for name, _ in suites)))
        total = int(match.group("total"))
        if total != sum(checks for _, checks in suites):
            problems.append("%s says %d checks in total, the runner's suites add up to %d"
                            % (DOC, total, sum(checks for _, checks in suites)))
        listed = [int(value) for value in match.group("list").split("/")]
        expected = [checks for _, checks in suites]
        if listed != expected:
            problems.append("%s lists the suites as %s, the runner runs %s"
                            % (DOC, match.group("list"), "/".join(str(n) for n in expected)))

    carry = tomllib.loads((root / CARRY).read_text(encoding="utf-8"))
    match = MODULES.search(doc)
    if not match:
        problems.append("%s no longer says how many strategy modules it carries" % DOC)
    else:
        try:
            said = number(match.group("count"))
        except ValueError:
            said = None
        if said != len(carry.get("module", [])):
            problems.append("%s says %s strategy modules, CARRY.toml lists %d"
                            % (DOC, match.group("count"), len(carry.get("module", []))))

    match = JUDGES.search(doc)
    if not match:
        problems.append("%s no longer says how many console judges it carries" % DOC)
    else:
        try:
            said = number(match.group("count"))
        except ValueError:
            said = None
        if said != len(carry.get("judge", [])):
            problems.append("%s says %s console judges, CARRY.toml lists %d"
                            % (DOC, match.group("count"), len(carry.get("judge", []))))

    match = PYTHON.search(doc)
    if not match:
        problems.append("%s no longer quotes 'power-python: OK (N suites)'" % DOC)
    elif int(match.group("count")) != len(python_runs(root)):
        problems.append("%s quotes power-python with %s suites, the runner calls %d"
                        % (DOC, match.group("count"), len(python_runs(root))))

    rows = tomllib.loads((root / CONTRACTS).read_text(encoding="utf-8")).get("contract", [])
    seconds = sum(1 for row in rows if row.get("second"))
    match = CONTRACTS_LINE.search(doc)
    if not match:
        problems.append("%s no longer says how many contract rows carry a second source" % DOC)
    else:
        if int(match.group("rows")) != len(rows):
            problems.append("%s says %s contract rows, HW-CONTRACTS.toml has %d"
                            % (DOC, match.group("rows"), len(rows)))
        if int(match.group("seconds")) != seconds:
            problems.append("%s says %s rows carry an independent second source, the table has %d"
                            % (DOC, match.group("seconds"), seconds))

    power = tomllib.loads((root / EIGHT_STEPS).read_text(encoding="utf-8")).get("hardware", {}).get("power", {})
    image_os = power.get("image_os")
    if not image_os:
        problems.append("%s [hardware.power] has no image_os; a note cannot say which OS an image belongs to"
                        % EIGHT_STEPS)
    profiles = tomllib.loads((root / BOARD).read_text(encoding="utf-8")).get("package", {}).get("defconfig", {})
    if image_os and image_os not in profiles:
        problems.append("%s [hardware.power].image_os is %r, not a key of board.toml [package.defconfig] (%s)"
                        % (EIGHT_STEPS, image_os, ", ".join(sorted(profiles))))
    image = tomllib.loads((root / W11_IMAGE).read_text(encoding="utf-8")).get("image", {})
    if image_os and image.get("os_profile") != image_os:
        problems.append("%s says os_profile=%r, [hardware.power].image_os is %r"
                        % (W11_IMAGE, image.get("os_profile"), image_os))
    digest = image.get("sha256")
    verify = power.get("step", {}).get("verify", {})
    artifact = " ".join(str(verify.get(key) or "") for key in ("evidence", "artifact_check"))
    if not digest:
        problems.append("%s has no [image].sha256" % W11_IMAGE)
    elif digest not in artifact:
        problems.append("%s sha256 is not quoted in [hardware.power.step.verify]; the ledger names no image"
                        % W11_IMAGE)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        problems = verify(root)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print("power-counts: cannot read %s" % error)
        return 2
    for problem in problems:
        print("power-counts: %s" % problem)
    if problems:
        print("power-counts: %d disagreement(s)" % len(problems))
        return 1
    carry = tomllib.loads((root / CARRY).read_text(encoding="utf-8"))
    rows = tomllib.loads((root / CONTRACTS).read_text(encoding="utf-8")).get("contract", [])
    print("power-counts: OK (%d C suite(s) / %d checks, %d python suite(s), %d module(s), %d judge(s), "
          "%d contract row(s) with %d second source(s))"
          % (len(runs(root)), sum(checks for _, checks in runs(root)), len(python_runs(root)),
             len(carry.get("module", [])), len(carry.get("judge", [])), len(rows),
             sum(1 for row in rows if row.get("second"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
