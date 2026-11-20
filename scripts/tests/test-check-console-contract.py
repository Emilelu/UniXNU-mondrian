#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Fixtures for scripts/check-console-contract.py: the gate must be sensitive to a rename
inside the driver format, and it must refuse a pair whose anchor is not load-bearing."""

import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-console-contract.py"
WORK = ROOT / "build" / f"console-contract-tests-{os.getpid()}"

failures = 0
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures, checks
    checks += 1
    if ok:
        print(f"ok   {name}")
    else:
        failures += 1
        print(f"FAIL {name}: {detail}")


def load():
    spec = importlib.util.spec_from_file_location("console_contract", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find(root: pathlib.Path, name: str) -> pathlib.Path:
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    return root / name


EMITTER = 'void f() {\n    IOLog("K60Demo: sample=%u SOC=%u.%02u%% charge=%u/%umAh\\n",\n        1, 2, 3, 4, 5);\n}\n'
JUDGE = ('import re\n\n'
         'SAMPLE_RE = re.compile(\n'
         '    r"K60Demo: sample=(\\d+) SOC=(\\d+)\\.(\\d+)% charge=(\\d+)/(\\d+)mAh")\n')


def pair(emitter="drv.c", judge="judge.py", attribute="SAMPLE_RE", anchor="sample=%u SOC="):
    return (("demo", emitter, judge, attribute, anchor, ()),)


def main() -> int:
    module = load()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)

    check("the repository pair verifies", module.verify(ROOT) == [], str(module.verify(ROOT)))

    root = find(WORK / "good", "drv.c")
    root.write_text(EMITTER, encoding="utf-8", newline="\n")
    (root.parent / "judge.py").write_text(JUDGE, encoding="utf-8", newline="\n")
    problems = module.verify(root.parent, pair())
    check("a compatible pair verifies", problems == [], str(problems))

    fmt = module.find_format(EMITTER, "sample=%u SOC=")
    check("the format is found by the anchor, not by line number", fmt is not None and "K60Demo" in fmt, str(fmt))
    check("two literal chunks are joined", fmt is not None and fmt.endswith("mAh\n"), repr(fmt))
    line = module.synthesise(fmt or "", ())
    check("the synthesis fills every conversion",
          "K60Demo: sample=1 SOC=1.1% charge=1/1mAh" in line, repr(line))

    renamed = find(WORK / "renamed", "drv.c")
    # A key outside the anchor: the anchor still locates the format, so the refusal has to
    # come from the judge's pattern, which is the failure this gate exists for.
    renamed.write_text(EMITTER.replace("charge=", "charge-now="),
                       encoding="utf-8", newline="\n")
    (renamed.parent / "judge.py").write_text(JUDGE, encoding="utf-8", newline="\n")
    problems = module.verify(renamed.parent, pair())
    check("a renamed key inside the format is refused",
          any("does not match the line" in problem for problem in problems), str(problems))

    gone = find(WORK / "gone", "drv.c")
    gone.write_text('IOLog("K60Demo: other=%u\\n", 1);\n', encoding="utf-8", newline="\n")
    (gone.parent / "judge.py").write_text(JUDGE, encoding="utf-8", newline="\n")
    problems = module.verify(gone.parent, pair())
    check("an anchor nothing prints is refused",
          any("no IOLog format" in problem for problem in problems), str(problems))

    absent = find(WORK / "absent", "judge.py")
    absent.write_text(JUDGE, encoding="utf-8", newline="\n")
    problems = module.verify(absent.parent, pair())
    check("a missing emitter is refused",
          any("does not exist" in problem for problem in problems), str(problems))

    (absent.parent / "drv.c").write_text(EMITTER, encoding="utf-8", newline="\n")
    (absent.parent / "judge.py").write_text("import re\nOTHER_RE = re.compile('x')\n",
                                            encoding="utf-8", newline="\n")
    problems = module.verify(absent.parent, pair())
    check("a judge without the pattern is refused",
          any("no usable SAMPLE_RE" in problem for problem in problems), str(problems))

    # An anchor the regex does not actually depend on would make the pair prove nothing.
    loose = find(WORK / "loose", "drv.c")
    loose.write_text('IOLog("K60Demo: sample=%u\\n", 1);\n', encoding="utf-8", newline="\n")
    (loose.parent / "judge.py").write_text("import re\nSAMPLE_RE = re.compile(r'sample=(\\d+)')\n",
                                           encoding="utf-8", newline="\n")
    problems = module.verify(loose.parent, pair(anchor="K60Demo: "))
    check("an anchor the pattern does not use is refused",
          any("proves nothing" in problem for problem in problems), str(problems))

    # The sleep trace lines come out of the xnu patch with printf(), not IOLog. The call is
    # declared per pair, so the gate must find the format there and must not silently fall
    # back to IOLog when the pair says otherwise.
    trace = find(WORK / "trace", "0629.patch")
    trace.write_text('+\tprintf("K60TRACE: sleep enter cpus=%u\\n", gIOCPUs->getCount());\n',
                     encoding="utf-8", newline="\n")
    (trace.parent / "judge.py").write_text(
        "import re\nTRACE_ENTER_RE = re.compile(r'K60TRACE: sleep enter cpus=(\\d+)')\n",
        encoding="utf-8", newline="\n")
    printed = (("trace", "0629.patch", "judge.py", "TRACE_ENTER_RE", "K60TRACE: sleep enter cpus=", ()),)
    module.CALLS["trace"] = "printf"
    try:
        problems = module.verify(trace.parent, printed)
        check("a printf pair is found by its own call", problems == [], str(problems))
        module.CALLS["trace"] = "IOLog"
        problems = module.verify(trace.parent, printed)
        check("a pair that names the wrong call is refused",
              any("no IOLog format" in problem for problem in problems), str(problems))
    finally:
        module.CALLS.pop("trace", None)

    # A judge that grows a pattern nobody paired must be refused, and an exemption has to
    # carry a reason a reader can check (the same check-or-waiver shape as RULES.toml).
    cover = find(WORK / "cover", "drv.c")
    cover.write_text(EMITTER, encoding="utf-8", newline="\n")
    (cover.parent / "judge.py").write_text(
        JUDGE + "SPARE_RE = re.compile(r'K60Demo: spare=(\\d+)')\n",
        encoding="utf-8", newline="\n")
    problems = module.coverage_problems(cover.parent, pair())
    check("a pattern with no printer pair is refused",
          any("no pair says who prints it" in problem for problem in problems), str(problems))
    module.EXEMPT[("judge.py", "SPARE_RE")] = "printed by the kernel tree, not here"
    try:
        check("a written exemption is accepted",
              module.coverage_problems(cover.parent, pair()) == [],
              str(module.coverage_problems(cover.parent, pair())))
        module.EXEMPT[("judge.py", "SPARE_RE")] = "  "
        problems = module.coverage_problems(cover.parent, pair())
        check("an exemption with no reason is refused",
              any("empty reason" in problem for problem in problems), str(problems))
        module.EXEMPT[("judge.py", "SPARE_RE")] = "a reason"
        del module.EXEMPT[("judge.py", "SPARE_RE")]
        module.EXEMPT[("judge.py", "GONE_RE")] = "a reason"
        problems = module.coverage_problems(cover.parent, pair())
        check("an exemption the judge outgrew is refused",
              any("no longer carries" in problem for problem in problems), str(problems))
    finally:
        module.EXEMPT.pop(("judge.py", "SPARE_RE"), None)
        module.EXEMPT.pop(("judge.py", "GONE_RE"), None)

    # --root points at another checkout of the same repository, so it is exercised against
    # the real one and against an empty directory.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    cli = subprocess.run([sys.executable, str(TOOL), "--root", str(ROOT)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    check("--root on this checkout is green",
          cli.returncode == 0 and "judged line(s)" in cli.stdout,
          f"rc {cli.returncode} {(cli.stdout + cli.stderr).strip()[-200:]}")
    empty = WORK / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    cli = subprocess.run([sys.executable, str(TOOL), "--root", str(empty)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    check("--root on a tree without the drivers is refused",
          cli.returncode == 2 and "does not exist" in cli.stderr,
          f"rc {cli.returncode} {cli.stderr.strip()[-200:]}")

    print()
    if failures:
        print(f"TESTS FAILED {failures} of {checks} checks")
        return 1
    print(f"TESTS OK {checks} checks (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
