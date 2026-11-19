#!/usr/bin/env python3
"""Tests for scripts/check-power-carry.py.

The gate guards the iOS 27 carry, so its own failure modes matter: a tampered
module, a suite that lost asserts, a module that dropped out of the portability
list, and a target tree that lost or edited a file must each turn it red.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-power-carry.py"
WORK = ROOT / "build" / "power-carry-tests"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)

ZERO = "0" * 64
failures = 0
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures, checks
    checks += 1
    if ok:
        print(f"ok   {name}")
        return
    failures += 1
    print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def build(target: Path, checks_in_runner: int = 3) -> Path:
    if target.exists():
        shutil.rmtree(target)
    (target / "drivers" / "PongPower").mkdir(parents=True)
    (target / "scripts" / "tests").mkdir(parents=True)
    (target / "docs" / "research" / "power").mkdir(parents=True)
    (target / "drivers" / "PongPower" / "Alpha.c").write_text("int alpha(void) { return 1; }\n", encoding="utf-8")
    (target / "drivers" / "PongPower" / "Alpha.h").write_text("#pragma once\nint alpha(void);\n", encoding="utf-8")
    (target / "scripts" / "tests" / "test-alpha.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (target / "scripts" / "tests" / "run-k60-power-host.sh").write_text(
        "#!/bin/bash\nrun alpha %d scripts/tests/test-alpha.c drivers/PongPower/Alpha.c\n" % checks_in_runner,
        encoding="utf-8",
    )
    (target / "scripts" / "check-power-portability.py").write_text('MODULES = ["Alpha.c"]\n', encoding="utf-8")
    (target / "docs" / "research" / "power" / "CARRY.toml").write_text(
        "version = 1\n\n[[module]]\n"
        'name = "Alpha"\n'
        'suite = "alpha"\n'
        "checks = 3\n"
        'test = "scripts/tests/test-alpha.c"\n'
        "files = [\n"
        f'  {{ path = "drivers/PongPower/Alpha.c", sha256 = "{ZERO}" }},\n'
        f'  {{ path = "drivers/PongPower/Alpha.h", sha256 = "{ZERO}" }},\n'
        "]\n\n"
        "[[judge]]\n"
        'name = "judge-alpha"\n'
        'path = "scripts/judge-alpha.py"\n'
        f'sha256 = "{ZERO}"\n'
        'test = "scripts/tests/test-judge-alpha.py"\n'
        "cases = 2\n",
        encoding="utf-8",
    )
    (target / "scripts" / "judge-alpha.py").write_text(
        "#!/usr/bin/env python3\nprint('judge-alpha: TOTAL PASS')\n", encoding="utf-8"
    )
    (target / "scripts" / "tests" / "test-judge-alpha.py").write_text(
        "print('TESTS OK 2 cases (0 failure(s))')\n", encoding="utf-8"
    )
    result = subprocess.run([sys.executable, str(TOOL), "--repo", str(target), "--update"], **RUN)
    assert result.returncode == 0, result.stderr
    return target


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], **RUN)


def case_verify_after_update() -> None:
    tree = build(WORK / "ok")
    result = run("--repo", str(tree))
    check("a fresh manifest verifies", result.returncode == 0, result.stderr)
    check("the summary names one module", "1 modules" in result.stdout, result.stdout)


def case_tampered_module() -> None:
    tree = build(WORK / "tampered")
    (tree / "drivers" / "PongPower" / "Alpha.c").write_text("int alpha(void) { return 2; }\n", encoding="utf-8")
    result = run("--repo", str(tree))
    check("a changed module fails", result.returncode == 1, result.stdout)
    check("the report says it changed", "changed" in result.stderr, result.stderr)


def case_target_identical() -> None:
    tree = build(WORK / "source")
    target = WORK / "target-same"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(tree, target)
    result = run("--repo", str(tree), "--target", str(target))
    check("an identical target passes", result.returncode == 0, result.stderr)
    check("the summary names the target", "target" in result.stdout, result.stdout)


def case_target_missing() -> None:
    tree = build(WORK / "source2")
    target = WORK / "target-missing"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(tree, target)
    (target / "drivers" / "PongPower" / "Alpha.h").unlink()
    result = run("--repo", str(tree), "--target", str(target))
    check("a missing target file fails", result.returncode == 1, result.stdout)
    check("the report says it is missing", "missing" in result.stderr, result.stderr)


def case_target_drift() -> None:
    tree = build(WORK / "source3")
    target = WORK / "target-drift"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(tree, target)
    (target / "drivers" / "PongPower" / "Alpha.c").write_text("int alpha(void) { return 3; }\n", encoding="utf-8")
    result = run("--repo", str(tree), "--target", str(target))
    check("an edited target file fails", result.returncode == 1, result.stdout)
    check("the report says it differs", "differs" in result.stderr, result.stderr)


def case_runner_count() -> None:
    tree = build(WORK / "count")
    runner = tree / "scripts" / "tests" / "run-k60-power-host.sh"
    runner.write_text(runner.read_text(encoding="utf-8").replace("run alpha 3", "run alpha 4"), encoding="utf-8")
    result = run("--repo", str(tree))
    check("a suite that gained asserts fails", result.returncode == 1, result.stdout)
    check("the report names the count", "manifest says 3 checks" in result.stderr, result.stderr)


def case_portability() -> None:
    tree = build(WORK / "portability")
    (tree / "scripts" / "check-power-portability.py").write_text('MODULES = ["Beta.c"]\n', encoding="utf-8")
    result = run("--repo", str(tree))
    check("a module outside the portability list fails", result.returncode == 1, result.stdout)
    check("the report names the list", "not in the portability module list" in result.stderr, result.stderr)


def case_no_manifest() -> None:
    tree = build(WORK / "nomanifest")
    (tree / "docs" / "research" / "power" / "CARRY.toml").unlink()
    result = run("--repo", str(tree))
    check("a missing manifest is unusable", result.returncode == 2, result.stdout)


def case_judge_summary() -> None:
    tree = build(WORK / "judges")
    result = run("--repo", str(tree))
    check("a tree with a judge verifies", result.returncode == 0, result.stderr)
    check("the summary counts the judge", "1 judge(s)" in result.stdout, result.stdout)


def case_judge_tampered() -> None:
    tree = build(WORK / "judge-tampered")
    (tree / "scripts" / "judge-alpha.py").write_text(
        "#!/usr/bin/env python3\nprint('judge-alpha: silently edited')\n", encoding="utf-8"
    )
    result = run("--repo", str(tree))
    check("an edited judge fails", result.returncode == 1, result.stdout)
    check("the report names the judge", "judge judge-alpha" in result.stderr, result.stderr)


def case_judge_case_count() -> None:
    tree = build(WORK / "judge-cases")
    (tree / "scripts" / "tests" / "test-judge-alpha.py").write_text(
        "print('TESTS OK 3 cases (0 failure(s))')\n", encoding="utf-8"
    )
    result = run("--repo", str(tree))
    check("a fixture suite that gained cases fails", result.returncode == 1, result.stdout)
    check("the report names both counts", "manifest says 2 cases" in result.stderr, result.stderr)


def case_judge_broken() -> None:
    tree = build(WORK / "judge-broken")
    (tree / "scripts" / "judge-alpha.py").write_text("def broken(:\n", encoding="utf-8")
    result = run("--repo", str(tree))
    check("a judge that does not compile fails", result.returncode == 1, result.stdout)
    check("the report says so", "does not compile" in result.stderr, result.stderr)


def case_judge_target_missing() -> None:
    tree = build(WORK / "judge-source")
    target = WORK / "judge-target"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(tree, target)
    (target / "scripts" / "judge-alpha.py").unlink()
    result = run("--repo", str(tree), "--target", str(target))
    check("a target that lost the judge fails", result.returncode == 1, result.stdout)
    check("the report says the judge is missing", "judge judge-alpha: scripts/judge-alpha.py is missing" in result.stderr, result.stderr)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    for case in (
        case_verify_after_update,
        case_tampered_module,
        case_target_identical,
        case_target_missing,
        case_target_drift,
        case_runner_count,
        case_portability,
        case_judge_summary,
        case_judge_tampered,
        case_judge_case_count,
        case_judge_broken,
        case_judge_target_missing,
        case_no_manifest,
    ):
        case()
    print(f"TESTS OK {checks} checks ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
