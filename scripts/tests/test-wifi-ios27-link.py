#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for the 24A446 link contract of the wifi driver.

The 27 kernel link failed on three names that only look like driver bugs: the
SMMU kit the driver calls is a PongAdreno component the stage-0 kernel does not
link, and the USB console and UFS hooks are 16.6.1 kernel exports. Cases 1-2
pin the flag that carries the kit, cases 3-4 pin the weak references that make
the absent hooks a log line instead of an undefined symbol, and cases 5-6 pin
the station check that catches an API the newer header promises and the older
station archive does not implement.
"""

from __future__ import annotations

import importlib.util
import io
import contextlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build-k60-wifi-native.py"
PLATFORM = ROOT / "drivers" / "PongWifi" / "PongWifiPlatform.cpp"
CHECKER = ROOT / "scripts" / "check-wifi-station-api.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_wifi_station_api", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fake_nm(body: str) -> str:
    path = Path(tempfile.mkdtemp()) / "nm"
    path.write_text("#!/bin/sh\ncat <<'EOF'\n" + body + "EOF\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def station(names) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "src").mkdir()
    body = "".join("int %s(void);\nint %s(void) { return 0; }\n" % (n, n) for n in names)
    (root / "src" / "nw_mainline.c").write_text(body, encoding="utf-8")
    return root


@case
def the_kext_builder_carries_the_smmu_kit_only_behind_its_flag():
    source = text(BUILDER)
    assert "p.add_argument('--smmu4k-kit',action='store_true'" in source
    assert "kit=[]" in source, "the kit must default to no objects"
    for unit in ("ArmSmmu4K", "ArmSmmu4KContext", "ArmSmmu4KProgram"):
        assert "'%s'" % unit in source, unit


@case
def the_kit_objects_reach_the_archive():
    source = text(BUILDER)
    line = next(l for l in source.splitlines() if "libtool" in l and "static" in l)
    assert "*map(str,kit)" in line, line


@case
def both_16_only_providers_sit_behind_a_switch():
    source = text(PLATFORM)
    assert "#ifndef PONG_WIFI_HOST_HOOKS" in source
    assert "#define PONG_WIFI_HOST_HOOKS 1" in source
    assert "#if PONG_WIFI_HOST_HOOKS\nbool pong_ufs_ready(void);" in source
    assert "bool k60_usblog_console_up(void);\n#endif" in source
    # a weak reference would still be an undefined symbol under arm64e
    assert "__attribute__((weak))" not in source


@case
def an_absent_provider_is_a_log_line_not_a_call():
    source = text(PLATFORM)
    assert "c<240&&!k60_usblog_console_up()" in source
    assert "n<180&&!pong_ufs_ready()" in source
    assert "host console and UFS hooks absent" in source


@case
def the_kext_builder_can_compile_the_hooks_out():
    source = text(BUILDER)
    assert "p.add_argument('--no-host-hooks',action='store_true'" in source
    assert "flags.append('-DPONG_WIFI_HOST_HOOKS=0')" in source


@case
def a_station_without_a_referenced_call_fails():
    checker = load_checker()
    nm = fake_nm("                 U _nw_wifi_power\n                 U _nw_wifi_scan_frequencies\n")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = checker.main(["--kext", str(Path(tempfile.mkdtemp()) / "kext.a"),
                             "--station", str(station([])), "--nm", nm])
    # the archive path must exist for the checker to look at it at all
    assert code == 2, code


@case
def the_station_that_defines_them_passes():
    checker = load_checker()
    nm = fake_nm("                 U _nw_wifi_power\n                 U _nw_wifi_scan_frequencies\n"
                 "0000000000001000 T _nw_wifi_start\n")
    archive = Path(tempfile.mkdtemp()) / "kext.a"
    archive.write_bytes(b"!<arch>\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = checker.main(["--kext", str(archive),
                             "--station", str(station(["nw_wifi_power", "nw_wifi_scan_frequencies"])),
                             "--nm", nm])
    assert code == 0, (code, out.getvalue())
    assert "2 referenced, 2 defined" in out.getvalue(), out.getvalue()


def main() -> int:
    passed = failed = 0
    for fn in CASES:
        try:
            fn()
        except Exception as error:  # noqa: BLE001 - the report is the point
            failed += 1
            print("FAIL %s: %s" % (fn.__name__, error))
        else:
            passed += 1
            print("ok %s" % fn.__name__)
    print("%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())