#!/usr/bin/env python3
"""Tests for scripts/check-criteria-cites.py.

The gate exists because the 判据总表's evidence lines are a copy of where the driver prints
the judged text, and on 2026-11-20 both C1 and C2 pointed at a raw-number publish block
while the sample line had moved to :290. Every case below is one way that copy can drift.
"""
import importlib.util
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[2]
TOOL = ROOT / "scripts" / "check-criteria-cites.py"
FIXTURES = ROOT / "build" / ("criteria-cites-tests-%d" % os.getpid())

PASS = 0
FAIL = 0
FAILED = []


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL %s %s" % (name, detail))


def case(name):
    def wrap(fn):
        print(name)
        try:
            fn()
        except Exception as error:  # noqa: BLE001
            global FAIL
            FAIL += 1
            FAILED.append(name)
            print("  FAIL %s raised %r" % (name, error))
        return fn
    return wrap


def load(path=TOOL):
    spec = importlib.util.spec_from_file_location("criteria_cites_" + str(len(str(path))), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = """PAIRS = (
    ("battery-channel-up", "drivers/PongPower/K60Battery.cpp", "scripts/judge-battery.py",
     "CHANNEL_UP_RE", "channel up; measured sign=", ()),
    ("battery-sample", "drivers/PongPower/K60Battery.cpp", "scripts/judge-battery.py",
     "SAMPLE_RE", "sample=%u SOC=", ()),
)
"""

DRIVER = chr(10).join(['#include <IOKit/IOLib.h>', 'void probe(void) {', '    IOLog("K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=%d\\n", 1);', '    IOLog("K60Battery: %s sample=%u SOC=%u.%02u%%\\n", "x", 1, 2, 3);', '}', ''])

_DOC = """# 判据

## 判据总表

| 编号 | 判据 | 证据行 | 判据器 |
|---|---|---|---|
| C1 | 订阅成立 | @K60Battery.cpp:3@ | judge-battery.py |
| C2 | 四属性可读 | @K60Battery.cpp:4@ | judge-battery.py |

正文。
"""
DOC = _DOC.replace("@", chr(96))


def make(name, doc_body=DOC, driver_body=DRIVER, contract_body=CONTRACT, skip=()):
    root = FIXTURES / name
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "drivers" / "PongPower").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "research" / "charger").mkdir(parents=True, exist_ok=True)
    if "contract" not in skip:
        (root / "scripts" / "check-console-contract.py").write_text(contract_body, encoding="utf-8")
    if "driver" not in skip:
        (root / "drivers" / "PongPower" / "K60Battery.cpp").write_text(driver_body, encoding="utf-8")
    if "doc" not in skip:
        (root / "docs" / "research" / "charger" / "07-DEVICE-CRITERIA.md").write_text(doc_body, encoding="utf-8")
    return root, load()


def run(root, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root)] + list(args),
                          capture_output=True, text=True, encoding="utf-8", env=env)


@case("healthy fixture")
def _():
    root, gate = make("healthy")
    check("a correct table verifies", gate.verify(root) == [], gate.verify(root))
    result = run(root)
    check("cli reports the two criteria", result.returncode == 0 and "2 criterion(s)" in result.stdout,
          (result.returncode, result.stdout, result.stderr))


@case("stale citation")
def _():
    root, gate = make("stale", doc_body=DOC.replace("K60Battery.cpp:3", "K60Battery.cpp:2"))
    problems = gate.verify(root)
    check("a moved line is refused", problems and "K60Battery.cpp:2" in problems[0], problems)
    check("the real line is named", problems and "is 3," in problems[0] or "is 3" in problems[0], problems)
    result = run(root)
    check("cli exits 1", result.returncode == 1 and "problem(s)" in result.stdout, result.returncode)


@case("range")
def _():
    root, gate = make("range", doc_body=DOC.replace("K60Battery.cpp:4", "K60Battery.cpp:2-5"))
    check("a range that covers the line is accepted", gate.verify(root) == [], gate.verify(root))
    root2, gate2 = make("range-miss", doc_body=DOC.replace("K60Battery.cpp:4", "K60Battery.cpp:5-6"))
    problems = gate2.verify(root2)
    check("a range that misses it is refused", problems and "5-6" in problems[0], problems)


@case("no citation")
def _():
    root, gate = make("nocite", doc_body=DOC.replace("四属性可读 | " + chr(96) + "K60Battery.cpp:4" + chr(96), "四属性可读 | 见正文"))
    problems = gate.verify(root)
    check("a row with no file:line is refused", problems and "cites no file:line" in problems[0], problems)


@case("no row")
def _():
    root, gate = make("norow", doc_body=DOC.replace("| C2 | 四属性可读 | " + chr(96) + "K60Battery.cpp:4" + chr(96) + " | judge-battery.py |" + chr(10), ""))
    problems = gate.verify(root)
    check("a missing criterion row is refused", problems and "no row for C2" in problems[0], problems)


@case("no table")
def _():
    root, gate = make("notable", doc_body="# 判据\n\n没有表。\n")
    problems = gate.verify(root)
    check("a doc without the table is refused", problems and "判据总表" in problems[0], problems)


@case("pair gone")
def _():
    root, gate = make("pairgone", contract_body=CONTRACT.replace('"battery-sample"', '"battery-something"'))
    problems = gate.verify(root)
    check("a pair the contract no longer carries is refused",
          problems and "no longer in scripts/check-console-contract.py" in problems[0], problems)


@case("anchor gone")
def _():
    root, gate = make("anchorgone", driver_body=DRIVER.replace("channel up; measured sign=", "channel up; sign="))
    problems = gate.verify(root)
    check("a driver that stopped printing the anchor is refused",
          problems and "does not carry" in problems[0], problems)


@case("files missing")
def _():
    root, gate = make("nomissing", skip=("driver",))
    problems = gate.verify(root)
    check("a missing driver is refused", problems and "is missing" in problems[0], problems)
    root2, gate2 = make("nodoc", skip=("doc",))
    problems2 = gate2.verify(root2)
    check("a missing doc is refused", problems2 and "07-DEVICE-CRITERIA.md is missing" in problems2[0], problems2)
    root3, gate3 = make("nocontract", skip=("contract",))
    problems3 = gate3.verify(root3)
    check("a missing contract is refused",
          problems3 and "check-console-contract.py is missing" in problems3[0], problems3)


@case("cli edge")
def _():
    root, _gate = make("cliedge")
    missing = run(FIXTURES / "does-not-exist")
    check("a missing root exits 2", missing.returncode == 2, missing.returncode)


@case("this checkout")
def _():
    gate = load()
    problems = gate.verify(ROOT)
    check("the repository table verifies", problems == [], problems)
    result = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    check("the repository gate is green", result.returncode == 0 and "criteria-cites: 2 criterion(s)" in result.stdout,
          (result.returncode, result.stdout, result.stderr))


print()
if FAIL:
    print("TESTS FAILED %d check(s), %d failure(s): %s" % (PASS + FAIL, FAIL, ", ".join(FAILED)))
    sys.exit(1)
print("TESTS OK %d checks (0 failure(s))" % PASS)
