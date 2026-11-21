#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-wifi-b4-exports.py.

The B4 report is easy to misread as a green gate because it exits 0 even when
the two station APIs are missing. These cases pin the output semantics: a
complete pair resolves every driver symbol, a station archive without one API
must print that symbol by name, an absent symbol is classified as absent rather
than station-API, and a missing input exits 2 before nm is called.

The fake nm is a Python file, so the test runs on the host as well as in WSL.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-wifi-b4-exports.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load():
    spec = importlib.util.spec_from_file_location("check_wifi_b4_exports", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


KERNEL = "Symbols for com.apple.kernel:\n_ifnet_input T 0000000000000000 0000000000000010\n"
DRIVER_DEF = "driver.a[PongWifiNet.late.o]: _driver_init T 0000000000000000 0000000000000010\n"
DRIVER_UND = (
    "driver.a[PongWifiNet.late.o]: _nw_wifi_power U 0 0\n"
    "driver.a[PongWifiNet.late.o]: _nw_wifi_scan_frequencies U 0 0\n"
)
STATION_DEF = (
    "station.a[PongAth11k-linked.o]: _nw_wifi_power T 0000000000000000 0000000000000010\n"
    "station.a[PongAth11k-linked.o]: _nw_wifi_scan_frequencies T 0000000000000010 0000000000000010\n"
)
STATION_UND = "station.a[PongAth11k-linked.o]: _ifnet_input U 0 0\n"


def fixture(kernel: str = KERNEL, driver_def: str = DRIVER_DEF,
            driver_und: str = DRIVER_UND, station_def: str = STATION_DEF,
            station_und: str = STATION_UND) -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp())
    (root / "kernel.macho").write_bytes(b"")
    (root / "driver.a").write_bytes(b"")
    (root / "station.a").write_bytes(b"")
    (root / "kernel.txt").write_text(kernel, encoding="utf-8")
    (root / "driver_def.txt").write_text(driver_def, encoding="utf-8")
    (root / "driver_und.txt").write_text(driver_und, encoding="utf-8")
    (root / "station_def.txt").write_text(station_def, encoding="utf-8")
    (root / "station_und.txt").write_text(station_und, encoding="utf-8")
    nm = root / "nm.py"
    nm.write_text(
        "import pathlib, sys\n"
        "root = pathlib.Path(__file__).resolve().parent\n"
        "args = sys.argv[1:]\n"
        "if '-g' in args:\n"
        "    print((root / 'kernel.txt').read_text(), end='')\n"
        "    raise SystemExit(0)\n"
        "path = pathlib.Path(args[-1]).name\n"
        "und = '-u' in args\n"
        "stem = 'driver' if path.startswith('driver') else 'station'\n"
        "print((root / (stem + ('_und' if und else '_def') + '.txt')).read_text(), end='')\n",
        encoding="utf-8",
    )
    return root, nm


def run_case(root: Path, nm: Path) -> tuple[int, str, str]:
    script = load()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = script.main([
            "--kernel", str(root / "kernel.macho"),
            "--driver", str(root / "driver.a"),
            "--station", str(root / "station.a"),
            "--nm", str(nm),
        ])
    return code, out.getvalue(), err.getvalue()


@case
def a_complete_pair_resolves_every_driver_symbol():
    code, out, err = run_case(*fixture())
    assert code == 0, (code, out, err)
    assert "driver missing:" not in out, out
    assert "B4: 1 exports; 2 driver undefined, 2 resolved, 0 missing; " in out, out
    assert "1 station undefined, 1 resolved, 0 missing" in out, out


@case
def a_missing_station_api_is_named_not_just_counted():
    code, out, err = run_case(*fixture(
        station_def="station.a[PongAth11k-linked.o]: _nw_wifi_scan_frequencies "
                    "T 0000000000000000 0000000000000010\n"
    ))
    assert code == 0, (code, out, err)
    assert "driver missing: _nw_wifi_power" in out, out
    assert "B4: 1 exports; 2 driver undefined, 1 resolved, 1 missing; " in out, out


@case
def an_absent_symbol_is_not_called_a_station_api():
    code, out, err = run_case(*fixture(
        driver_und="driver.a[PongWifiNet.late.o]: _not_exported U 0 0\n"
                   "driver.a[PongWifiNet.late.o]: _nw_wifi_power U 0 0\n",
        station_def="",
    ))
    assert code == 0, (code, out, err)
    assert "absent=1" in out, out
    assert "driver missing: _not_exported, _nw_wifi_power" in out, out


@case
def a_missing_input_returns_two_before_nm():
    root = Path(tempfile.mkdtemp())
    code, out, err = run_case(root, root / "nm.py")
    assert code == 2, (code, out, err)
    assert "missing input:" in out, out


def main() -> int:
    failed = 0
    for fn in CASES:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as error:
            failed += 1
            print(f"FAIL {fn.__name__}: {error}")
    print(f"{len(CASES) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
