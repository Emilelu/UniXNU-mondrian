#!/usr/bin/env python3
"""Self-test for check-bt-27-acceptance.py.

The test builds small ledgers in a temporary directory, so it never depends on
the real BT table.  It proves the reader accepts a complete seven-row table and
rejects each shape error that would make an acceptance claim meaningless.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHECK = ROOT / "scripts" / "check-bt-27-acceptance.py"
STEPS = ["same_model", "official", "decompile", "wide", "plan", "deep", "verify"]
LABELS = {
    "same_model": "① 同型",
    "official": "② 官方",
    "decompile": "③ 反编译",
    "wide": "④ 广域",
    "plan": "⑤ 计划",
    "deep": "⑥ 深入",
    "verify": "⑦ 核验",
}


def literal(value: str) -> str:
    if "'" in value:
        raise ValueError(f"literal string cannot contain a quote: {value!r}")
    return "'" + value + "'"


def valid_toml(skip: set[tuple[str, str]] | None = None, overrides: dict | None = None) -> str:
    skip = skip or set()
    overrides = overrides or {}
    lines = [
        "[hardware.bluetooth.acceptance]",
        'status = "pre-boot"',
        'recorded_at = "2026-11-22T13:30:00+08:00"',
        'host = "test"',
        'note = "test table"',
    ]
    for step in STEPS:
        if ("__table__", step) in skip:
            continue
        fields = {
            "label": LABELS[step],
            "command": 'python3 -c "print(123)"',
            "expect": "123",
            "negative": "python3 scripts/tests/test-bt-27-acceptance.py",
            "precedent": "E:/example/repo:1",
            "conclusion": "有推断",
            "reading": "123",
            "negative_reading": "reader test",
        }
        fields.update(overrides.get(step, {}))
        lines.append("")
        lines.append(f"[hardware.bluetooth.acceptance.{step}]")
        for key, value in fields.items():
            if (step, key) in skip:
                continue
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif key in ("command", "negative"):
                rendered = literal(value)
            else:
                rendered = json.dumps(value, ensure_ascii=False)
            lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"


def run(text: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "bt-27.toml"
        path.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(CHECK), "--toml", str(path), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cases: list[tuple[str, bool, str]] = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        cases.append((name, ok, detail))

    r = run(valid_toml(), "--check")
    case("a complete table passes", r.returncode == 0 and "OK (7 steps)" in r.stdout, r.stderr)

    r = run(valid_toml(skip={("same_model", "expect")}), "--check")
    case("a missing expectation is rejected", r.returncode == 1 and "same_model.expect" in r.stderr, r.stderr)

    r = run(valid_toml(overrides={"plan": {"conclusion": "确定"}}), "--check")
    case("an unknown conclusion is rejected", r.returncode == 1 and "plan.conclusion" in r.stderr, r.stderr)

    r = run(valid_toml(overrides={"wide": {"precedent": "无先例"}}), "--check")
    case("no precedent requires a stop", r.returncode == 1 and "wide.stop" in r.stderr, r.stderr)

    r = run(valid_toml(skip={("__table__", "verify")}), "--check")
    case("a missing step is rejected", r.returncode == 1 and "verify" in r.stderr, r.stderr)

    r = run(valid_toml(), "--run", "--only", "same_model")
    case("run mode passes a matching reading", r.returncode == 0 and "PASS same_model: ok" in r.stdout, r.stdout + r.stderr)

    r = run(valid_toml(overrides={"same_model": {"expect": "999"}}), "--run", "--only", "same_model")
    case("run mode reds a wrong reading", r.returncode == 1 and "FAIL same_model" in r.stdout, r.stdout + r.stderr)

    r = run(valid_toml(), "--markdown")
    case("markdown has the header and a command", r.returncode == 0 and "| 步 |" in r.stdout and "python3 -c" in r.stdout, r.stdout + r.stderr)

    failed = 0
    for name, ok, detail in cases:
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            failed += 1
            print("  " + detail.strip().replace("\n", "\n  "))
    print(f"bt-27-acceptance test: {'OK' if not failed else 'FAILED'} ({len(cases)} case(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
