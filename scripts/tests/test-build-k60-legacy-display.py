#!/usr/bin/env python3
"""Tests for scripts/build-k60-legacy-display.py (check mode only).

The builder must fail closed: a missing component file or an incomplete vtable
fixture has to be reported by name, and a complete pair has to produce a plan
without touching a compiler.  These tests never compile anything.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "build-k60-legacy-display.py"
HEADERS = ("NativeLegacyRequest.h", "NativeGOPWire.h", "NativeHalfCodes.h",
           "NativeGpuTrace.h", "OriginalMobileFramebufferABI.h")
SOURCES = ("NativeLegacyDisplay.cpp", "NativeGOPPresenter.cpp")


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def make_case(root: Path, *, slots: int = 379, drop: str | None = None) -> tuple[Path, Path]:
    component = root / "component"
    component.mkdir()
    for name in SOURCES + HEADERS:
        (component / name).write_text("// stub\n", encoding="utf-8")
    fixture = root / "fixture.json"
    doc = {key: {} for key in ("kernelcache_sha256", "collection_slide", "vtable",
                               "instance_size", "methods", "leaves", "bindings",
                               "checks", "display", "request", "names")}
    doc["slots"] = [0] * slots
    if drop:
        doc.pop(drop)
    fixture.write_text(json.dumps(doc), encoding="utf-8")
    return component, fixture


def test_complete_inputs_plan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        component, fixture = make_case(Path(tmp))
        proc = run(["--component", str(component), "--fixture", str(fixture), "--plan"])
        assert proc.returncode == 0, proc.stderr
        assert "379 slots" in proc.stdout
        assert "check only" in proc.stdout
        assert "clang" in proc.stdout


def test_missing_component_file_is_named() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        component, fixture = make_case(Path(tmp))
        (component / "NativeGOPPresenter.cpp").unlink()
        proc = run(["--component", str(component), "--fixture", str(fixture)])
        assert proc.returncode == 2
        assert "NativeGOPPresenter.cpp" in proc.stderr


def test_incomplete_fixture_key_is_named() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        component, fixture = make_case(Path(tmp), drop="bindings")
        proc = run(["--component", str(component), "--fixture", str(fixture)])
        assert proc.returncode == 2
        assert "bindings" in proc.stderr


def test_short_vtable_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        component, fixture = make_case(Path(tmp), slots=10)
        proc = run(["--component", str(component), "--fixture", str(fixture)])
        assert proc.returncode == 2
        assert "10 slots" in proc.stderr


def test_run_without_permission_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        component, fixture = make_case(Path(tmp))
        proc = run(["--component", str(component), "--fixture", str(fixture), "--run"])
        assert proc.returncode == 3
        assert "K60_ALLOW_BUILD" in proc.stderr


def main() -> int:
    tests = [test_complete_inputs_plan, test_missing_component_file_is_named,
             test_incomplete_fixture_key_is_named, test_short_vtable_is_rejected,
             test_run_without_permission_is_refused]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"ok   {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"TESTS {'OK' if not failures else 'FAILED'} {len(tests)} case(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
