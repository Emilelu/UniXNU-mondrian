#!/usr/bin/env python3
"""Pin the snapshot gate's three-state remote check (P-183).

A failed ls-remote is unknown, not proof that a tag was never pushed. When
network access is unavailable, a recorded confirmation is usable only for the
same tag commit. All network outcomes are injected; this test never contacts
origin.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-snapshot-tag.py"
SPEC = importlib.util.spec_from_file_location("snapshot_gate", GATE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

checks = 0
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print("FAIL " + name + (": " + detail if detail else ""))


def pushed(returncode: int, stdout: str = ""):
    result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr="network failure")
    with patch.object(MODULE.subprocess, "run", return_value=result) as run:
        value = MODULE.is_pushed("boot-proven-20261120")
    check("is_pushed queries the requested remote tag",
          run.call_args.args[0] == ["git", "ls-remote", "--tags", "origin",
                                    "refs/tags/boot-proven-20261120"])
    return value


def main() -> int:
    check("remote failure is unknown, not unpushed", pushed(128) is None)
    check("successful empty lookup means unpushed", pushed(0) is False)
    check("successful nonempty lookup means pushed",
          pushed(0, "abc123 refs/tags/boot-proven-20261120\n") is True)

    with tempfile.TemporaryDirectory(prefix="k60-snapshot-tag-") as tmp:
        baseline = pathlib.Path(tmp) / "MAIN-BASELINE.toml"
        MODULE.BASELINE = str(baseline)
        sha = "a" * 40
        baseline.write_text(
            f'[[entry]]\ntag = "boot-proven-20261120"\ntag_commit = "{sha}"\n'
            'tag_pushed = "2026-11-19T20:00:00+08:00"\n', encoding="utf-8")
        with patch.object(MODULE, "tag_commit", return_value=sha):
            check("recorded push is accepted for the same tag commit",
                  MODULE.recorded_push("boot-proven-20261120") == "2026-11-19T20:00:00+08:00")
        with patch.object(MODULE, "tag_commit", return_value="b" * 40):
            check("recorded push is rejected after the tag moves",
                  MODULE.recorded_push("boot-proven-20261120") == "")

    print(f"TESTS OK {checks - failures} checks ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
