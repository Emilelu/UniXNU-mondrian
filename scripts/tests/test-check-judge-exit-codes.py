#!/usr/bin/env python3
"""Tests for scripts/check-judge-exit-codes.py.

The gate says the five power judges share one exit table (0 PASS, 1 FAIL, 2 INVALID,
4 usage). Each case below is one way a judge drifts from it — including the one that was
real: argparse's own 2 for a bad flag, which is exactly INVALID.
"""
import importlib.util
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[2]
TOOL = ROOT / "scripts" / "check-judge-exit-codes.py"
FIXTURES = ROOT / "build" / ("judge-exit-tests-%d" % os.getpid())

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
    spec = importlib.util.spec_from_file_location("judge_exit_codes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DOC = "Runs a demo judge.\n\nExit status: 0 PASS, 1 FAIL, 2 INVALID, 4 usage error (never a verdict).\n"

GOOD = '''#!/usr/bin/env python3
"""%s"""
import argparse
import pathlib
import sys


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("%%s: error: %%s" %% (self.prog, message), file=sys.stderr)
        raise SystemExit(4)


def main():
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("path")
    args = parser.parse_args()
    target = pathlib.Path(args.path)
    if not target.is_file():
        print("demo: no console.log at %%s" %% target, file=sys.stderr)
        return %d
    text = target.read_text(encoding="utf-8")
    verdict = "PASS" if "ok" in text else "FAIL"
    return 2 if verdict == "INVALID" else (0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    sys.exit(main())
''' % (DOC, 2)


def build(name, body=GOOD, contract=None):
    root = FIXTURES / name
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "judge-demo.py").write_text(body, encoding="utf-8")
    gate = load()
    gate.JUDGES.clear()
    gate.JUDGES.update(contract or {"judge-demo.py": (("console.log",), ("console.log", "--nope"))})
    return root, gate


def run(root):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root)],
                          capture_output=True, text=True, encoding="utf-8", env=env)


@case("healthy fixture")
def _():
    root, gate = build("healthy")
    gate.JUDGES.update({"judge-demo.py": (("console.log",), ("console.log", "--nope"))})
    check("a judge that keeps the table is accepted", gate.verify(root) == [], gate.verify(root))


@case("undocumented code")
def _():
    body = GOOD.replace('        return 2\n', '        return 3\n')
    root, gate = build("undocumented", body=body)
    problems = gate.verify(root)
    check("a code the exit line omits is refused",
          any("returns 3" in p for p in problems), problems)


@case("documented but unreachable")
def _():
    body = GOOD.replace("0 PASS, 1 FAIL, 2 INVALID, 4 usage",
                        "0 PASS, 1 FAIL, 2 INVALID, 3 unreadable, 4 usage")
    root, gate = build("unreachable", body=body)
    problems = gate.verify(root)
    check("a documented code nothing returns is refused",
          any("documents 3" in p for p in problems), problems)


@case("no exit line")
def _():
    body = GOOD.replace("Exit status: 0 PASS, 1 FAIL, 2 INVALID, 4 usage error (never a verdict).",
                        "Nothing about codes.")
    root, gate = build("noexit", body=body)
    problems = gate.verify(root)
    check("a judge without an exit line is refused",
          any("documents no exit line" in p for p in problems), problems)


@case("vocabulary")
def _():
    body = GOOD.replace("2 INVALID, 4 usage error (never a verdict)", "2 unreadable, 4 misuse")
    root, gate = build("vocab", body=body)
    problems = gate.verify(root)
    check("an exit line that stops naming INVALID is refused",
          any("does not name INVALID" in p for p in problems), problems)
    check("an exit line that stops naming usage is refused",
          any("does not name usage" in p for p in problems), problems)


@case("plain argparse")
def _():
    body = GOOD.replace("parser = _ArgumentParser(", "parser = argparse.ArgumentParser(")
    root, gate = build("plain", body=body)
    problems = gate.verify(root)
    check("argparse's own 2 for a bad flag is refused",
          any("on a flag it does not have" in p for p in problems), problems)


@case("missing input")
def _():
    body = GOOD.replace('        return 2\n', '        return 4\n')
    root, gate = build("missing4", body=body)
    problems = gate.verify(root)
    check("a missing input that exits 4 is refused",
          any("when its input is not there" in p for p in problems), problems)


@case("missing judge")
def _():
    root, gate = build("absent")
    (root / "scripts" / "judge-demo.py").unlink()
    problems = gate.verify(root)
    check("a judge named in the table but absent is refused",
          any("is missing" in p for p in problems), problems)


@case("cli")
def _():
    root, _gate = build("cli")
    missing = subprocess.run([sys.executable, str(TOOL), "--root", str(FIXTURES / "nope")],
                             capture_output=True, text=True, encoding="utf-8",
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    check("a missing root exits 2", missing.returncode == 2, missing.returncode)


@case("this checkout")
def _():
    gate = load()
    check("the five judges share the table", gate.verify(ROOT) == [], gate.verify(ROOT))
    result = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True,
                            encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    check("the repository gate is green",
          result.returncode == 0 and "5 judge(s) share one exit table" in result.stdout,
          (result.returncode, result.stdout, result.stderr))


print()
if FAIL:
    print("TESTS FAILED %d check(s), %d failure(s): %s" % (PASS + FAIL, FAIL, ", ".join(FAILED)))
    sys.exit(1)
print("TESTS OK %d checks (0 failure(s))" % PASS)
