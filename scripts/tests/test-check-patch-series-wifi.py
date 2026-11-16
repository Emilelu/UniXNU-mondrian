#!/usr/bin/env python3
"""Tests for the patches/wifi series-vs-README check in check-patch-series.py."""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-patch-series.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("check_patch_series", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    failures = 0
    cases = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures, cases
        cases += 1
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1
            if detail:
                print("      " + detail)

    module = load_gate()
    actual = module.check_wifi_series()
    check("the repository wifi series and README agree", not actual, str(actual))
    series = [line.strip().split()[0] for line in (ROOT / "patches/wifi/series").read_text(encoding="utf-8").splitlines() if line.strip()]
    patches = sorted(path.name for path in (ROOT / "patches/wifi").glob("*.patch"))
    check("every wifi patch is listed in series", set(series) == set(patches),
          f"series {len(series)}, patches {len(patches)}")

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / "series").write_text("0001.patch\n", encoding="utf-8")
        (root / "0001.patch").write_text("", encoding="utf-8")
        (root / "0002.patch").write_text("", encoding="utf-8")
        (root / "README.md").write_text("no mention here", encoding="utf-8")
        module.WIFI = root
        problems = module.check_wifi_series()
        check("a missing README mention is reported", any("README 未列出 0001.patch" in item for item in problems), str(problems))
        check("an untracked patch is reported", any("0002.patch 未登记到 series" in item for item in problems), str(problems))

        (root / "series").write_text("0001.patch\n0003.patch\n", encoding="utf-8")
        problems = module.check_wifi_series()
        check("a missing series patch is reported", any("0003.patch" in item and "不存在" in item for item in problems), str(problems))

        module.WIFI = root / "missing"
        problems = module.check_wifi_series()
        check("a missing wifi directory is reported", problems == ["patches/wifi 不存在"], str(problems))

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s))")
        return 1
    print(f"TESTS OK {cases} cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
