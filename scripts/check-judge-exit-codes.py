#!/usr/bin/env python3
"""One exit-code table for every judge on the power line, checked two ways.

The table is: 0 PASS, 1 FAIL, 2 INVALID (nothing judgeable, including an input that is not
there), 4 usage error (never a verdict).

On 2026-11-20 the five judges disagreed while all of them documented the table:
argparse exits 2 for a bad flag, which is exactly INVALID, so a typo looked like "the
capture carried nothing to judge"; and a console path that did not exist exited 4 in
judge-battery.py and judge-k60-mode1-console.py but 2 in the other three. Automation
that branches on "was this a verdict at all" could not tell.

This gate reads the docstring and the code statically, then runs each judge twice: a bad
flag has to exit 4 and a path that is not there has to exit 2. Exit 0 both agree, 1 a
judge drifted, 2 a judge cannot be read.
"""
from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
USAGE = 4
INVALID = 2
VERDICTS = (0, 1, 2, 4)
# judge -> (argv that carries no usable input, argv with a flag it does not have); the tokens
# console.log / mirror are replaced by paths that do not exist.
JUDGES = {
    "judge-battery.py": (("console.log",), ("console.log", "--definitely-not-a-flag")),
    "judge-k60-handoff-console.py": (("console.log",), ("--definitely-not-a-flag",)),
    "judge-k60-mode1-console.py": (("console.log",), ("console.log", "--definitely-not-a-flag")),
    "judge-k60-sleep-console.py": (("console.log",), ("console.log", "--definitely-not-a-flag")),
    "judge-k60-battery-mirror.py": (("console.log", "--mirror", "mirror"),
                                    ("console.log", "--mirror", "mirror", "--definitely-not-a-flag")),
}
EXIT_LINE = re.compile(r"(?i)exit(?:\s+status|\s+codes?)?\s*:")
NUMBER = re.compile(r"\b([0-4])\b")


def documented(text: str):
    """The exit line of a judge's docstring, and the codes on it."""
    for line in text.splitlines():
        if EXIT_LINE.search(line):
            return line.strip(), {int(n) for n in NUMBER.findall(line)}
    return None, set()


def returned(tree: ast.AST) -> set[int]:
    """Every integer exit constant the module can produce."""
    codes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, int):
            codes.add(node.value.value)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) \
                and getattr(node.exc.func, "id", "") == "SystemExit" and node.exc.args \
                and isinstance(node.exc.args[0], ast.Constant):
            codes.add(node.exc.args[0].value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "exit" and node.args \
                and isinstance(node.args[0], ast.Constant):
            codes.add(node.args[0].value)
    return {code for code in codes if isinstance(code, int)}


def run(judge: pathlib.Path, argv, tmp: pathlib.Path):
    missing = str(tmp / "not-here.log")
    mirror = str(tmp / "not-here.json")
    resolved = [missing if arg == "console.log" else mirror if arg == "mirror" else arg for arg in argv]
    result = subprocess.run([sys.executable, str(judge)] + resolved,
                            capture_output=True, text=True, encoding="utf-8",
                            env={"PYTHONIOENCODING": "utf-8", "PATH": "/usr/bin:/bin"})
    return result


def verify(root: pathlib.Path = ROOT) -> list[str]:
    import tempfile

    problems: list[str] = []
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="judge-exit-"))
    for name, (missing_argv, usage_argv) in JUDGES.items():
        path = root / "scripts" / name
        if not path.is_file():
            problems.append("%s is missing" % name)
            continue
        text = path.read_text(encoding="utf-8")
        line, said = documented(text)
        if line is None:
            problems.append("%s documents no exit line, so nobody knows the codes" % name)
            continue
        codes = returned(ast.parse(text))
        for code in sorted(codes - said):
            problems.append("%s returns %d, which its exit line does not document (%r)"
                            % (name, code, line))
        for code in sorted(said - codes - {0, 1}):
            problems.append("%s documents %d, but no path in it returns that code (%r)"
                            % (name, code, line))
        for word in ("PASS", "FAIL", "INVALID", "usage"):
            if word.lower() not in line.lower():
                problems.append("%s exit line does not name %s: %r" % (name, word, line))
        usage = run(path, usage_argv, tmp)
        if usage.returncode != USAGE:
            problems.append("%s exits %d on a flag it does not have, but a usage error is %d"
                            % (name, usage.returncode, USAGE))
        missing = run(path, missing_argv, tmp)
        if missing.returncode != INVALID:
            problems.append("%s exits %d when its input is not there, but INVALID is %d"
                            % (name, missing.returncode, INVALID))
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        print("judge-exit-codes: %s is not a directory" % args.root, file=sys.stderr)
        return 2
    problems = verify(root)
    if problems:
        for problem in problems:
            print("\u274c " + problem)
        print("judge-exit-codes: %d problem(s)" % len(problems))
        return 1
    print("\u2705 judge-exit-codes: %d judge(s) share one exit table (0 PASS, 1 FAIL, 2 INVALID, 4 usage)"
          % len(JUDGES))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
