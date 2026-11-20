#!/usr/bin/env python3
"""Fixtures for scripts/check-preflight-coverage.py."""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-preflight-coverage.py"
MANIFEST = "docs/research/power/PREFLIGHT-COVERAGE.toml"

checks = 0
failures: list[str] = []


def check(label: str, ok: bool, note: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}{(': ' + note) if note else ''}")


def load():
    spec = importlib.util.spec_from_file_location("coverage", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


PREFLIGHT = "def check_alpha(tree):\n    return 1, 'ok'\n\n\ndef check_beta(tree):\n    return 1, 'ok'\n"
CONTRACTS = '[[contract]]\nid = "row-one"\n'

ROW = '[[item]]\nfunction = "check_alpha"\nwhat = "alpha"\n{body}\n'


def contracts_for(body: str) -> str:
    rows = []
    for chunk in body.split("[[item]]")[1:]:
        function = re.search(r'function = "([^"]+)"', chunk)
        if function and '"row-one"' in chunk:
            rows.append('[[contract]]\nid = "row-one"\npreflight = ["%s"]\n' % function.group(1))
    return "".join(rows) or CONTRACTS


def build(base: Path, body: str, preflight: str = PREFLIGHT,
          contracts: str | None = None) -> Path:
    contracts = contracts_for(body) if contracts is None else contracts
    (base / "scripts").mkdir(parents=True, exist_ok=True)
    (base / "docs/research/power").mkdir(parents=True, exist_ok=True)
    (base / "scripts/check-ios27-power-preflight.py").write_text(preflight, encoding="utf-8")
    (base / "docs/research/power/HW-CONTRACTS.toml").write_text(contracts, encoding="utf-8")
    (base / MANIFEST).write_text(body, encoding="utf-8")
    return base


def run(base: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), "--root", str(base), *extra],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def healthy() -> str:
    return ("manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
            + ROW.replace("{body}", 'gate = "scripts/check-power-carry.py"')
            + ROW.replace("check_alpha", "check_beta").replace(
                "{body}", 'backed_by = ["row-one"]'))


def main() -> int:
    module = load()
    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), healthy())
        (base / "scripts/check-power-carry.py").write_text("", encoding="utf-8")
        run(base, "--render", "docs/research/power/PREFLIGHT-COVERAGE.md")
        items, problems, planned = module.verify(base)
        check("a table with one gate and one contract row verifies", not problems, str(problems))
        check("both rows are counted", len(items) == 2, str(len(items)))
        out = run(base)
        check("cli rc 0 on the healthy table", out.returncode == 0, out.stdout)
        check("cli reports both landings", "2 preflight check(s)" in out.stdout, out.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'gate = "scripts/check-power-carry.py"'))
        (base / "scripts/check-power-carry.py").write_text("", encoding="utf-8")
        _, problems, _ = module.verify(base)
        check("a preflight function with no row is refused",
              any("no [[item]] row says where it lands" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'why = "a written reason long enough to read"')
                     + ROW.replace("check_alpha", "check_gamma").replace(
                         "{body}", 'why = "another written reason, also long enough"'))
        _, problems, _ = module.verify(base)
        check("a row naming a function the preflight lacks is refused",
              any("no such function" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'backed_by = ["row-two"]')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'backed_by = ["row-one"]'))
        _, problems, _ = module.verify(base)
        check("a contract id the manifest lacks is refused",
              any("row-two" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'gate = "scripts/not-here.py"')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'backed_by = ["row-one"]'))
        _, problems, _ = module.verify(base)
        check("a gate that does not exist is refused",
              any("is not a file" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'why = "too short"')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'backed_by = ["row-one"]'))
        _, problems, _ = module.verify(base)
        check("a reason nobody can read is refused",
              any("no readable reason" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'why = "a written reason long enough to read"')
                     + ROW.replace("{body}", 'why = "the second row repeats the function"'))
        _, problems, _ = module.verify(base)
        check("the same function twice is refused",
              any("appears twice" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + '[[item]]\nplanned = true\nwhat = "later"\n'
                     + 'why = "not implemented yet, but wanted"\n'
                     + ROW.replace("{body}", 'why = "a written reason long enough to read"'))
        _, problems, planned = module.verify(base)
        check("a planned item without a next step is refused",
              any("has to say what will make it real" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + '[[item]]\nplanned = true\nfunction = "check_alpha"\n'
                     + 'next = "do it"\n'
                     + ROW.replace("{body}", 'why = "a written reason long enough to read"')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'backed_by = ["row-one"]'))
        _, problems, _ = module.verify(base)
        check("a planned item that already names a function is refused",
              any("must leave function empty" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n")
        _, problems, _ = module.verify(base)
        check("an empty table is refused",
              any("no [[item]] row" in p for p in problems), str(problems))

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'backed_by = ["row-one"]')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'why = "a written reason long enough to read"'))
        out = run(base, "--render", "docs/research/power/PREFLIGHT-COVERAGE.md")
        text = (base / "docs/research/power/PREFLIGHT-COVERAGE.md")
        check("render writes the table", out.returncode == 0 and text.exists(), out.stdout + out.stderr)
        body = text.read_text(encoding="utf-8") if text.exists() else ""
        check("the rendered file says it is generated", "never this file" in body, body[:200])

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + '[[item]]\nplanned = true\nwhat = "later"\n'
                     + 'why = "not implemented yet, but wanted"\nnext = "implement it"\n'
                     + ROW.replace("{body}", 'backed_by = ["row-one"]')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'why = "a written reason long enough to read"'))
        module.main(["--root", str(base), "--render", "docs/research/power/PREFLIGHT-COVERAGE.md"])
        body = (base / "docs/research/power/PREFLIGHT-COVERAGE.md").read_text(encoding="utf-8")
        check("the rendered file carries the planned section", "滚动待办" in body, body[-300:])

    with tempfile.TemporaryDirectory() as tmp:
        base = build(Path(tmp), "manifest = \"docs/research/power/HW-CONTRACTS.toml\"\n"
                     + ROW.replace("{body}", 'gate = "scripts/not-here.py"')
                     + ROW.replace("check_alpha", "check_beta").replace(
                         "{body}", 'why = "a written reason long enough to read"'))
        out = run(base)
        check("the cli fails on a broken table", out.returncode == 1, str(out.returncode))

    items, problems, planned = module.verify(ROOT)
    check("this checkout verifies", not problems, str(problems[:3]))
    check("every preflight class is covered", len(items) - len(planned) == 9, str(len(items)))
    committed = ROOT / "docs/research/power/PREFLIGHT-COVERAGE.md"
    check("the committed rendered file matches render()",
          committed.exists() and committed.read_text(encoding="utf-8") == module.render(ROOT),
          "stale; run --render")

    print(f"TESTS OK {checks} checks ({len(failures)} failure(s))")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
