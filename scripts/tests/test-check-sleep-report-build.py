#!/usr/bin/env python3
"""Fixture tests for scripts/check-sleep-report-build.py.

The checker exists so "the key is in the .config" cannot be mistaken for "the
macro reached IOCPU.cpp". These cases prove the switch, the builder expansion,
the xnu plumbing and the build-log parser separately, including the three
failure modes: no macro, the macro twice, and a macro with the wrong value.
"""
import importlib.util
import os
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
WORK = REPO / "build" / ("sleep-build-tests-%d" % os.getpid())
CHECKS = 0
FAILURES = 0


def check(name, condition, detail=""):
    global CHECKS, FAILURES
    CHECKS += 1
    if condition:
        print("ok   %s" % name)
    else:
        FAILURES += 1
        print("FAIL %s%s" % (name, ": " + detail if detail else ""))


def load():
    spec = importlib.util.spec_from_file_location(
        "check_sleep_report_build", REPO / "scripts" / "check-sleep-report-build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def line(macro="-DK60_PLATFORM_SLEEP_REPORT=1", target="iokit/Kernel/IOCPU.cpo"):
    return "/usr/bin/clang++ %s -c iokit/Kernel/IOCPU.cpp -o %s" % (macro, target)


def main():
    module = load()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    root = REPO

    if (REPO / ".git").exists():
        state, detail = module.check_switch(root)
        check("the real switch is y", state == "OK", "%s %s" % (state, detail))
        state, detail = module.check_builder(root)
        check("the real builder expands to one macro", state == "OK", "%s %s" % (state, detail))
        state, detail = module.check_xnu(root.parent / "xnu-12377")
        check("the real xnu plumbing lists IOCPU.cpp and its cpo rule", state == "OK", "%s %s" % (state, detail))
    else:
        print("skip real switch/builder/xnu (not carried in this bundle)")

    log = WORK / "ok.log"
    log.write_text(line() + "\n", encoding="utf-8")
    state, detail = module.check_product(log)
    check("one IOCPU.cpp compile line with the macro is OK", state == "OK", "%s %s" % (state, detail))

    bad = WORK / "no-macro.log"
    bad.write_text(line(macro="-DOTHER=1") + "\n", encoding="utf-8")
    state, detail = module.check_product(bad)
    check("a compile line without the macro is refused",
          state == "FAIL" and "did not see it" in detail, "%s %s" % (state, detail))

    twice = WORK / "twice.log"
    twice.write_text(line(macro="-DK60_PLATFORM_SLEEP_REPORT=1 -DK60_PLATFORM_SLEEP_REPORT=1") + "\n",
                     encoding="utf-8")
    state, detail = module.check_product(twice)
    check("the macro twice on one compile line is refused",
          state == "FAIL" and "2 time(s)" in detail, "%s %s" % (state, detail))

    zero = WORK / "zero.log"
    zero.write_text(line(macro="-DK60_PLATFORM_SLEEP_REPORT=0") + "\n", encoding="utf-8")
    state, detail = module.check_product(zero)
    check("the macro with value 0 is refused",
          state == "FAIL" and "expected 1" in detail, "%s %s" % (state, detail))

    two = WORK / "two-lines.log"
    two.write_text(line() + "\n" + line() + "\n", encoding="utf-8")
    state, detail = module.check_product(two)
    check("two IOCPU.cpp compile lines are refused",
          state == "FAIL" and "more than one" in detail, "%s %s" % (state, detail))

    other = WORK / "other.log"
    other.write_text("/usr/bin/clang++ -DK60_PLATFORM_SLEEP_REPORT=1 -c iokit/Kernel/IOOther.cpp -o iokit/Kernel/IOOther.cpo\n",
                     encoding="utf-8")
    state, detail = module.check_product(other)
    check("a different object does not satisfy IOCPU.cpp",
          state == "FAIL" and "did not see it" in detail, "%s %s" % (state, detail))

    object_path = WORK / "IOCPU.cpo"
    source_path = WORK / "IOCPU.cpp"
    object_path.write_bytes(b"object\n")
    source_path.write_bytes(b"source\n")
    os.utime(source_path, (1000, 1000))
    os.utime(object_path, (2000, 2000))
    state, detail = module.check_product(log, object_path, source_path)
    check("an object newer than its source is OK", state == "OK", "%s %s" % (state, detail))

    os.utime(object_path, (500, 500))
    state, detail = module.check_product(log, object_path, source_path)
    check("an object older than its source is refused",
          state == "FAIL" and "older" in detail, "%s %s" % (state, detail))

    wrong_object = WORK / "IOOther.cpo"
    wrong_object.write_bytes(b"other\n")
    state, detail = module.check_product(log, wrong_object)
    check("an object whose name does not match the log is refused",
          state == "FAIL" and "does not match" not in detail and "builds" in detail,
          "%s %s" % (state, detail))

    result = __import__("subprocess").run(
        [sys.executable, str(REPO / "scripts" / "check-sleep-report-build.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("without a log the command exits 0 and the output itself says WIRING ONLY",
          result.returncode == 0 and "WIRING ONLY" in result.stdout
          and "product is not proven" in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    result = __import__("subprocess").run(
        [sys.executable, str(REPO / "scripts" / "check-sleep-report-build.py"),
         "--log", str(log)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("the command with a good log exits 0 and does not claim wiring only",
          result.returncode == 0 and "sleep-report-build: OK" in result.stdout
          and "WIRING ONLY" not in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    result = __import__("subprocess").run(
        [sys.executable, str(REPO / "scripts" / "check-sleep-report-build.py"),
         "--log", str(bad)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("the command with a bad log exits 1 and names the product",
          result.returncode == 1 and "product" in result.stdout and "FAIL" in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    print()
    if FAILURES:
        print("TESTS FAILED %d of %d checks" % (FAILURES, CHECKS))
        return 1
    print("TESTS OK %d checks (0 failure(s))" % CHECKS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
