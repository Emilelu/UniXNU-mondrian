#!/usr/bin/env python3
"""Tests for scripts/check-aoci-index.py.

Four shapes: a healthy index, an entry whose file is gone, an entry outside the
managed scope (must not fail), and a missing index file.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "check-aoci-index.py"
HEADER = "#AOCI-CODE-VOLUME: 1\n\n===/<repository>/===\n"


def make_repo(root: Path, entries: str, config: dict | None = None) -> Path:
    (root / "aoci.txt").write_text("#AOCI-ROOT-VOLUME: 1\n", encoding="utf-8")
    (root / "aoci.meta.txt").write_text("#AOCI-META-VOLUME: 1\n", encoding="utf-8")
    (root / "aoci.code.txt").write_text(HEADER + entries, encoding="utf-8")
    (root / ".aoci").mkdir()
    (root / ".aoci/config.json").write_text(json.dumps(config or {}), encoding="utf-8")
    return root


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATE), "--repo", str(repo), *args],
                          capture_output=True, text=True)


def case_ok(tmp: Path) -> None:
    (tmp / "keep.py").write_text("x = 1\n", encoding="utf-8")
    make_repo(tmp, "keep.py[FC3T]: F:a file that exists | R:- | A:- | S:-\n")
    result = run(tmp)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AOCI OK 1 entries" in result.stdout


def case_missing(tmp: Path) -> None:
    make_repo(tmp, "gone.py[FC3T]: F:a file that moved | R:- | A:- | S:-\n")
    result = run(tmp)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "gone.py" in result.stdout and "no longer exists" in result.stdout


def case_out_of_scope(tmp: Path) -> None:
    config = {"managed_scope": {"rules": [
        {"rule_id": "exclude-patches", "action": "exclude",
         "pattern": "patches/**/*.patch", "pattern_kind": "glob", "enabled": True}]}}
    make_repo(tmp, "patches/0001-x.patch[FC3T]: F:a patch body | R:- | A:- | S:-\n", config)
    result = run(tmp)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 outside scope" not in result.stdout  # one entry was skipped
    assert "1 outside scope" in result.stdout


def case_sections(tmp: Path) -> None:
    (tmp / "docs").mkdir()
    (tmp / "docs" / "note.md").write_text("x\n", encoding="utf-8")
    make_repo(tmp, "===/<repository>/docs/===\nnote.md[FC3T]: F:a nested file | R:- | A:- | S:-\n")
    result = run(tmp)
    assert result.returncode == 0, result.stdout + result.stderr


def case_no_index(tmp: Path) -> None:
    (tmp / "aoci.txt").write_text("x\n", encoding="utf-8")
    result = run(tmp)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "missing" in result.stdout


def main() -> int:
    cases = [case_ok, case_missing, case_out_of_scope, case_sections, case_no_index]
    failures = 0
    for case in cases:
        tmp = Path(tempfile.mkdtemp(prefix="aoci-"))
        try:
            case(tmp)
            print(f"ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {case.__name__}: {exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"TESTS {'OK' if not failures else 'FAILED'} {len(cases)} cases, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())