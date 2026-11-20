#!/usr/bin/env python3
"""Tests for record-hw-contracts.py."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/record-hw-contracts.py"
checks = 0
failures: list[str] = []


def check(ok: bool, what: str) -> None:
    global checks
    checks += 1
    if not ok:
        failures.append(what)


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline=chr(10))


def block(name: str, source: str, expect: str, same: str, copy: str, why: str | None = None) -> str:
    lines = ["[[contract]]", f'id = "{name}"', f'source = "{source}"', f'expect = "{expect}"',
             f'same27 = "{same}"', f'copy27 = "{copy}"']
    if why is not None:
        lines.append(f'why27 = "{why}"')
    return chr(10).join(lines) + chr(10)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def main() -> int:
    base = pathlib.Path(tempfile.mkdtemp(prefix="record-contracts-"))
    tree = base / "tree"
    patch = tree / "patches/xnu/x.patch"
    write(patch, "#ifndef X\nGUARD\n#endif\n")

    moved = base / "moved.toml"
    write(moved, block("moved", "patches/xnu/x.patch:1", "GUARD", "drift", "patches/xnu/x.patch:1", "old"))
    out = base / "moved-out.toml"
    r = run([str(tree), "--manifest", str(moved), "--out", str(out)])
    check(r.returncode == 0, f"moved row: rc={r.returncode} stderr={r.stderr}")
    recorded = tomllib.loads(out.read_text(encoding="utf-8"))["contract"][0] if out.is_file() else {}
    check(recorded.get("copy27") == "patches/xnu/x.patch:2" and recorded.get("same27") == "same",
          f"moved row: copy27={recorded.get('copy27')} same27={recorded.get('same27')}")
    check("why27" not in recorded and recorded.get("source") == "patches/xnu/x.patch:1",
          "moved row: why27 should be dropped and source kept")
    check("1 re-recorded, 0 kept" in r.stdout, f"moved row summary: {r.stdout!r}")

    unchanged = base / "unchanged.toml"
    text = block("already", "patches/xnu/x.patch:1", "GUARD", "same", "patches/xnu/x.patch:2")
    write(unchanged, text)
    out2 = base / "unchanged-out.toml"
    r = run([str(tree), "--manifest", str(unchanged), "--out", str(out2)])
    check(r.returncode == 0 and "0 re-recorded, 1 kept" in r.stdout and out2.read_text(encoding="utf-8") == text,
          f"unchanged row should be kept byte for byte: {r.stdout!r}")

    ambiguous_tree = base / "ambiguous"
    write(ambiguous_tree / "patches/xnu/x.patch", "one\nGUARD\ntwo\nGUARD\n")
    ambiguous = base / "ambiguous.toml"
    write(ambiguous, block("ambiguous", "patches/xnu/x.patch:1", "GUARD", "drift", "patches/xnu/x.patch:1"))
    out3 = base / "ambiguous-out.toml"
    r = run([str(ambiguous_tree), "--manifest", str(ambiguous), "--out", str(out3)])
    check(r.returncode == 1 and "refusing to guess" in r.stderr and not out3.exists(),
          f"ambiguous row must refuse and write nothing: rc={r.returncode} stderr={r.stderr!r}")

    missing = base / "missing.toml"
    write(missing, block("missing", "patches/xnu/x.patch:1", "NOT-THERE", "drift", "patches/xnu/x.patch:1"))
    out4 = base / "missing-out.toml"
    r = run([str(tree), "--manifest", str(missing), "--out", str(out4)])
    check(r.returncode == 0 and "0 re-recorded, 1 kept" in r.stdout,
          f"missing text should be kept, not invented: {r.stdout!r}")

    r = run([str(tree), "--manifest", str(moved), "--out", str(moved)])
    check(r.returncode == 2 and "refusing to overwrite" in r.stderr,
          f"out==manifest must be refused: rc={r.returncode} stderr={r.stderr!r}")

    r = run([str(base / "not-a-dir"), "--manifest", str(moved), "--out", str(base / "x.toml")])
    check(r.returncode == 2 and "not a directory" in r.stderr,
          f"non-directory tree must be refused: rc={r.returncode}")

    if failures:
        print(f"TESTS OK {checks} checks ({len(failures)} failure(s))")
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print(f"TESTS OK {checks} checks (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
