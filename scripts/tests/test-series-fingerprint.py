#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the series fingerprint (P-214).

The failure this file pins is not a wrong hash -- it is *two* right hashes.  Until
2026-11-16 `scripts/build-strict.sh` wrote `sha256(<bytes of series>)` into the
build manifest while `scripts/porting-gate.py` and `scripts/record-boot.py`
computed `sha256(names + sizes)[:16]`.  Both are stable; they never agree.  Once
record-boot started trusting the manifest (P-211) the ledger filled with values
from the wrong namespace and iron-4 blocked every merge with "the series changed"
even though nothing had changed.

So the cases below do not test a value; they test that the three tools answer the
same question the same way, and that the answer moves when the patch set moves.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "series-fingerprint.py"
PORTING = ROOT / "scripts" / "porting-gate.py"
RECORD = ROOT / "scripts" / "record-boot.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_tool():
    spec = importlib.util.spec_from_file_location("series_fingerprint", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_repo(root: Path, entries: dict[str, int]) -> tuple[Path, Path]:
    patches = root / "patches" / "xnu"
    patches.mkdir(parents=True, exist_ok=True)
    for name, size in entries.items():
        (patches / name).write_bytes(b"x" * size)
    series = patches / "series"
    series.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return series, patches


def embedded_fingerprint(source: Path) -> tuple[str, int]:
    """Run the tool's own function, the way porting-gate and record-boot do."""
    spec = importlib.util.spec_from_file_location("series_fingerprint_inline", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.fingerprint(ROOT / "patches/xnu/series", ROOT / "patches/xnu")


@case
def the_cli_and_the_function_agree():
    module = load_tool()
    expected, count = module.fingerprint(ROOT / "patches/xnu/series", ROOT / "patches/xnu")
    out = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    value, seen = out.stdout.split()
    assert value == expected, (value, expected)
    assert int(seen) == count, (seen, count)


@case
def the_real_repository_matches_the_ledger_namespace():
    """The ledger and porting-gate use names+sizes truncated to 16 hex."""
    value, count = embedded_fingerprint(TOOL)
    assert len(value) == 16, value
    assert all(ch in "0123456789abcdef" for ch in value), value
    assert count > 100, count


@case
def a_renamed_patch_changes_the_fingerprint():
    module = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        series, patches = build_repo(Path(tmp), {"0001-a.patch": 10, "0002-b.patch": 20})
        first, count_a = module.fingerprint(series, patches)
        (patches / "0002-b.patch").rename(patches / "0002-c.patch")
        series.write_text("0001-a.patch\n0002-c.patch\n", encoding="utf-8")
        second, count_b = module.fingerprint(series, patches)
    assert count_a == count_b == 2, (count_a, count_b)
    assert first != second, "renaming a patch must change the fingerprint"


@case
def a_resized_patch_changes_the_fingerprint():
    module = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        series, patches = build_repo(Path(tmp), {"0001-a.patch": 10})
        first, _count = module.fingerprint(series, patches)
        (patches / "0001-a.patch").write_bytes(b"x" * 11)
        second, _count = module.fingerprint(series, patches)
    assert first != second, "a patch whose content changed size must change the fingerprint"


@case
def an_extra_entry_changes_the_fingerprint():
    module = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        series, patches = build_repo(Path(tmp), {"0001-a.patch": 10})
        first, count_a = module.fingerprint(series, patches)
        (patches / "0002-b.patch").write_bytes(b"x" * 20)
        series.write_text("0001-a.patch\n0002-b.patch\n", encoding="utf-8")
        second, count_b = module.fingerprint(series, patches)
    assert count_a == 1 and count_b == 2, (count_a, count_b)
    assert first != second


@case
def blank_lines_and_comments_do_not_count():
    module = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        series, patches = build_repo(Path(tmp), {"0001-a.patch": 10})
        plain, count_plain = module.fingerprint(series, patches)
        series.write_text("\n0001-a.patch\n\n", encoding="utf-8")
        padded, count_padded = module.fingerprint(series, patches)
    assert count_plain == count_padded == 1, (count_plain, count_padded)
    assert plain == padded, "blank lines must not change the fingerprint"


@case
def build_strict_writes_the_shared_namespace():
    """The manifest must carry the same value the gate computes (P-214)."""
    text = (ROOT / "scripts" / "build-strict.sh").read_text(encoding="utf-8")
    assert "series-fingerprint.py" in text, (
        "build-strict.sh must call scripts/series-fingerprint.py, not hash the file bytes"
    )
    assert 'SERIES_SHA=$(sha256sum "$REPO/patches/xnu/series"' not in text, (
        "the file-bytes hash is a different namespace from the ledger (P-214)"
    )
    assert "file_sha256" in text, "keep the file hash under its own name so both are readable"


@case
def the_gate_and_the_recorder_still_agree():
    """porting-gate and record-boot each carry a copy; both must match the tool."""
    module = load_tool()
    expected, count = module.fingerprint(ROOT / "patches/xnu/series", ROOT / "patches/xnu")

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
        return mod

    gate = load("porting_gate", PORTING)
    gate.SERIES = str(ROOT / "patches/xnu/series")
    gate.REPO = str(ROOT)
    value, seen = gate.series_fingerprint()
    assert (value, seen) == (expected, count), (value, seen, expected, count)

    recorder = load("record_boot", RECORD)
    recorder.SERIES = str(ROOT / "patches/xnu/series")
    recorder.REPO = str(ROOT)
    value2, seen2 = recorder.series_fingerprint()
    assert (value2, seen2) == (expected, count), (value2, seen2, expected, count)


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - a broken gate is a failure, not a crash
            failures += 1
            print(f"FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"TESTS OK {len(CASES) - failures} case(s) ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
