#!/usr/bin/env python3
"""Read the pre-boot acceptance table for the Bluetooth hardware item.

The table lives at hardware.bluetooth.acceptance in
docs/research/eight-step/bt-27.toml.  It is deliberately separate from the
seven evidence steps: an evidence step can be done while its executable
criterion is still red.  This reader checks the table's shape and, with
--run, executes the commands on the current host.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TOML = ROOT / "docs" / "research" / "eight-step" / "bt-27.toml"

STEPS = (
    "same_model",
    "official",
    "decompile",
    "wide",
    "plan",
    "deep",
    "verify",
)
CONCLUSIONS = {"有证据", "有推断", "不知道"}
REQUIRED = (
    "label",
    "command",
    "expect",
    "negative",
    "precedent",
    "conclusion",
    "reading",
    "negative_reading",
)
PRECEDENT = re.compile(r"^[A-Za-z]:/[^:]+:\d+")


class LedgerError(ValueError):
    pass


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LedgerError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise LedgerError(f"cannot parse {path}: {exc}") from exc


def table(doc: dict[str, Any]) -> dict[str, Any]:
    try:
        acc = doc["hardware"]["bluetooth"]["acceptance"]
    except (KeyError, TypeError) as exc:
        raise LedgerError("missing [hardware.bluetooth.acceptance]") from exc
    if not isinstance(acc, dict):
        raise LedgerError("[hardware.bluetooth.acceptance] is not a table")
    return acc


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    acc = table(doc)
    for key in ("status", "recorded_at", "host", "note"):
        value = acc.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"header {key}: expected a non-empty string")
    rows = {k: v for k, v in acc.items() if isinstance(v, dict)}
    missing = [s for s in STEPS if s not in rows]
    extra = [s for s in rows if s not in STEPS]
    if missing:
        errors.append("missing step(s): " + ", ".join(missing))
    if extra:
        errors.append("unknown step(s): " + ", ".join(extra))
    for step in STEPS:
        row = rows.get(step)
        if row is None:
            continue
        for key in REQUIRED:
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{step}.{key}: expected a non-empty string")
        conclusion = row.get("conclusion")
        if conclusion not in CONCLUSIONS:
            errors.append(
                f"{step}.conclusion: {conclusion!r} not in {sorted(CONCLUSIONS)}"
            )
        command = row.get("command", "")
        if len(command.strip()) < 8:
            errors.append(f"{step}.command: too short to be executable")
        expect = row.get("expect", "")
        if len(expect.strip()) < 3:
            errors.append(f"{step}.expect: too short to match anything")
        negative = row.get("negative", "")
        parts = [p.strip() for p in negative.split("&&") if p.strip()]
        if not parts or any(not p.startswith("python3 scripts/tests/") for p in parts):
            errors.append(
                f"{step}.negative: every command must start with "
                "python3 scripts/tests/"
            )
        precedent = row.get("precedent", "")
        if precedent.startswith("无先例"):
            if row.get("stop") is not True:
                errors.append(f"{step}.stop: 无先例 requires stop = true")
        elif not PRECEDENT.match(precedent):
            errors.append(
                f"{step}.precedent: expected D:/path:line or 无先例"
            )
        if conclusion == "不知道" and not row.get("blocked"):
            errors.append(f"{step}.blocked: 不知道 requires a reason")
    return errors


def run_one(row: dict[str, Any], root: pathlib.Path) -> tuple[bool, str]:
    command = row["command"]
    bash = shutil.which("bash")
    try:
        if bash:
            proc = subprocess.run(
                [bash, "-lc", command],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        else:
            proc = subprocess.run(
                command,
                cwd=root,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
    except subprocess.TimeoutExpired:
        return False, "timeout after 300 s"
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        tail = output.strip().splitlines()[-3:]
        return False, f"rc={proc.returncode}; " + " / ".join(tail)
    if row["expect"] not in output:
        tail = output.strip().splitlines()[-3:]
        return False, "expect not found; " + " / ".join(tail)
    return True, "ok"


def markdown(doc: dict[str, Any]) -> str:
    acc = table(doc)
    lines = [
        "| 步 | 判据（命令） | 期望读数 | 实测读数 | 负例自测 | 先例 | 结论 | 阻塞 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for step in STEPS:
        row = acc[step]
        cells = [
            row["label"],
            "`" + row["command"].replace("|", "\\|") + "`",
            row["expect"],
            row["reading"],
            "`" + row["negative"] + "`",
            row["precedent"],
            row["conclusion"],
            row.get("blocked", ""),
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toml", type=pathlib.Path, default=DEFAULT_TOML)
    parser.add_argument("--check", action="store_true", help="validate the table (default)")
    parser.add_argument("--run", action="store_true", help="run the criteria on this host")
    parser.add_argument("--only", help="comma-separated step names to run")
    parser.add_argument("--markdown", action="store_true", help="print the table")
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    args = parser.parse_args(argv)

    try:
        doc = load(args.toml)
        errors = validate(doc)
    except LedgerError as exc:
        print(f"bt-27-acceptance: ERROR: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"bt-27-acceptance: ERROR: {error}", file=sys.stderr)
        return 1

    acc = table(doc)
    if args.markdown:
        print(markdown(doc))
        return 0
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "steps": list(STEPS),
                    "rows": {s: acc[s] for s in STEPS},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.run:
        selected = list(STEPS)
        if args.only:
            selected = [s.strip() for s in args.only.split(",") if s.strip()]
            unknown = [s for s in selected if s not in STEPS]
            if unknown:
                print(
                    "bt-27-acceptance: ERROR: unknown --only step(s): "
                    + ", ".join(unknown),
                    file=sys.stderr,
                )
                return 1
        failures = 0
        for step in selected:
            ok, detail = run_one(acc[step], ROOT)
            print(f"{'PASS' if ok else 'FAIL'} {step}: {detail}")
            failures += 0 if ok else 1
        if failures:
            print(f"bt-27-acceptance: FAILED ({failures})", file=sys.stderr)
            return 1
        print(f"bt-27-acceptance: OK ({len(selected)} run)")
        return 0

    print(f"bt-27-acceptance: OK ({len(STEPS)} steps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
