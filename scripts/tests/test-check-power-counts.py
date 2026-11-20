#!/usr/bin/env python3
"""Fixture suite for scripts/check-power-counts.py.

The gate exists because a sticky sentence ("共 10 个套件，合计 1915 项断言 …")
went stale twice in one week. Its own failure modes therefore matter: every
number it reads must have a case that turns it red, and a sentence that
disappears must fail rather than pass silently (P-179).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-power-counts.py"
FAILURES = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if ok:
        print("ok   %s" % name)
        return
    FAILURES.append(name)
    print("FAIL %s%s" % (name, (": " + detail) if detail else ""))


RUNNER = """#!/usr/bin/env bash
run alpha 3 scripts/tests/test-alpha.c drivers/Alpha.c
run beta 4 scripts/tests/test-beta.c drivers/Beta.c
run_py one python3 scripts/tests/test-one.py
run_py two python3 scripts/tests/test-two.py
echo "power-python: OK (\u0024python_suites suites)"
"""

DOC = """# conformance

先跑 \`check-power-portability.py\`（两个策略模块必须无 IOKit 依赖），
再依次运行共 2 个套件，合计 7 项断言（3/4）。

C 套件之后同一条命令再跑 python 那半——carry 清单、一个控制台判读器、27 预检，
与硬件契约表核对（\`HW-CONTRACTS.toml\`，2 行 file:line 引用、1 行带独立第二来源）——
并打印 \`power-python: OK (2 suites)\`。
"""

CARRY = """[[module]]
name = "alpha"
suite = "alpha"
checks = 3

[[module]]
name = "beta"
suite = "beta"
checks = 4

[[judge]]
name = "judge-one"
cases = 1
"""

CONTRACTS = """[[contract]]
id = "alpha-owner"
lane = "adsp"
source = "drivers/Alpha.c:1"
expect = "ALPHA"
dependence = "firmware"
second = [{ source = "drivers/Beta.c:1", expect = "BETA" }]

[[contract]]
id = "beta-own-encoding"
lane = "power"
source = "drivers/Beta.c:2"
expect = "BETA_OWN"
dependence = "none"
"""


def fixture(base):
    (base / "scripts" / "tests").mkdir(parents=True, exist_ok=True)
    (base / "docs" / "research" / "power").mkdir(parents=True, exist_ok=True)
    (base / "scripts" / "tests" / "run-k60-power-host.sh").write_text(RUNNER, encoding="utf-8", newline="\n")
    (base / "docs" / "research" / "power" / "00-POWER-PAGE-CONFORMANCE.md").write_text(DOC, encoding="utf-8", newline="\n")
    (base / "docs" / "research" / "power" / "CARRY.toml").write_text(CARRY, encoding="utf-8", newline="\n")
    (base / "docs" / "research" / "power" / "HW-CONTRACTS.toml").write_text(CONTRACTS, encoding="utf-8", newline="\n")
    return base


def run(root):
    completed = subprocess.run([sys.executable, str(TOOL), "--root", str(root)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return completed.returncode, completed.stdout + completed.stderr


def case(name, mutate=None, expect_rc=1, expect=""):
    base = fixture(WORK / name)
    if mutate:
        mutate(base)
    code, out = run(base)
    check(name, code == expect_rc and expect in out, "rc=%d out=%r" % (code, out[-400:]))


def replace_in(base, relative, old, new):
    path = base / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError("%s does not contain %r" % (relative, old))
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


WORK = ROOT / "build" / ("power-counts-tests-%d" % os.getpid())
DOC_REL = "docs/research/power/00-POWER-PAGE-CONFORMANCE.md"
CONTRACTS_REL = "docs/research/power/HW-CONTRACTS.toml"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("power_counts", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check("chinese 二十四 is 24", module.chinese("二十四") == 24)
    check("chinese 十 is 10", module.chinese("十") == 10)
    check("chinese 两 is 2", module.chinese("两") == 2)
    check("number reads arabic", module.number("12") == 12)

    case("healthy", expect_rc=0, expect="2 C suite(s) / 7 checks")
    case("total", lambda b: replace_in(b, DOC_REL, "合计 7 项断言", "合计 8 项断言"),
         expect="the runner's suites add up to 7")
    case("per-suite list", lambda b: replace_in(b, DOC_REL, "（3/4）", "（4/3）"),
         expect="lists the suites as 4/3")
    case("suite count", lambda b: replace_in(b, DOC_REL, "共 2 个套件", "共 3 个套件"),
         expect="says 3 suites")
    case("module count", lambda b: replace_in(b, DOC_REL, "两个策略模块", "三个策略模块"),
         expect="strategy modules")
    case("judge count", lambda b: replace_in(b, DOC_REL, "一个控制台判读器", "两个控制台判读器"),
         expect="console judges")
    case("python suites", lambda b: replace_in(b, DOC_REL, "OK (2 suites)", "OK (3 suites)"),
         expect="quotes power-python with 3 suites")
    case("contract rows", lambda b: replace_in(b, DOC_REL, "，2 行 file:line", "，3 行 file:line"),
         expect="contract rows")
    case("contract seconds", lambda b: replace_in(b, DOC_REL, "1 行带独立第二来源", "2 行带独立第二来源"),
         expect="independent second source")
    case("sentence gone", lambda b: replace_in(b, DOC_REL, "共 2 个套件，合计 7 项断言（3/4）", "套件若干"),
         expect="no longer carries")
    case("a second source dropped from the table",
         lambda b: replace_in(b, CONTRACTS_REL, "second = [", "replaces = ["),
         expect="the table has 0")

    bare = WORK / "no-runner"
    (bare / "docs" / "research" / "power").mkdir(parents=True, exist_ok=True)
    check("a missing runner is unusable", run(bare)[0] == 2,
          str(run(bare)))

    code, out = run(ROOT)
    check("the repository agrees with itself", code == 0 and "1915 checks" in out, out[-300:])

    print("TESTS OK %d checks (%d failure(s))" % (CHECKS, len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
