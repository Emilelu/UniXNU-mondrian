#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-wifi-station-archive.py.

The checker exists because four different failures each looked like a pass:
an archive whose members were built for arm64, an archive that only
references the station APIs, a stamp that described a header other than the
one beside it, and an archive carrying a scratch stub. The cases pin one
failure each, plus the end-to-end pass and the absent-archive note, so a
future edit cannot turn any of them into a green run.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-wifi-station-archive.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load():
    spec = importlib.util.spec_from_file_location("check_wifi_station_archive", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def header(cpusubtype: int) -> bytes:
    return struct.pack("<IIIIIIII", 0xFEEDFACF, 0x0100000C, cpusubtype, 1, 0, 0, 0, 0)


def stage(symbols: str, cpusubtype: int = 0x80000002, ie_bytes: int = 2048,
          stamp_sha: str | None = None, write_stamp: bool = True) -> tuple[Path, str, str]:
    """Build an archive-shaped directory with fake ar/nm and a real stamp pair."""
    root = Path(tempfile.mkdtemp())
    archive = root / "libPongAth11k.a"
    archive.write_bytes(b"!<arch>\n")
    abi = root / "abi"
    abi.mkdir()
    abi_header = abi / "nw_abi.h"
    abi_header.write_bytes(b"struct nw_wifi_abi { unsigned ie_bytes; };\n")
    digest = stamp_sha or hashlib.sha256(abi_header.read_bytes()).hexdigest()
    if write_stamp:
        (abi / "nw_abi.stamp").write_text(
            f"ie_bytes={ie_bytes}\nheader_sha256={digest}\n", encoding="utf-8")
    obj = root / "PongAth11k-linked.o"
    obj.write_bytes(header(cpusubtype))
    ar = root / "ar"
    ar_script = "#!/bin/sh\ncase \"$1\" in\n  t) echo PongAth11k-linked.o ;;\n  p) cat '%s' ;;\nesac\n" % obj
    ar.write_text(ar_script, encoding="utf-8")
    ar.chmod(0o755)
    nm = root / "nm"
    nm.write_text("#!/bin/sh\ncat <<'EOF'\n" + symbols + "EOF\n", encoding="utf-8")
    nm.chmod(0o755)
    return archive, str(ar), str(nm)


BOTH = "_nw_wifi_power T 0000000000000000 0000000000000010\n" \
       "_nw_wifi_scan_frequencies T 0000000000000010 0000000000000010\n"


def run_case(archive: Path, ar: str, nm: str) -> tuple[int, str, str]:
    checker = load()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = checker.main([str(archive), "--ar", ar, "--nm", nm])
    return code, out.getvalue(), err.getvalue()


@case
def a_complete_archive_passes():
    code, out, err = run_case(*stage(BOTH))
    assert code == 0, (code, out, err)
    assert "station archive contract: PASS" in out, out
    assert "1 arm64e" in out, out


@case
def an_undefined_reference_is_not_a_definition():
    code, out, err = run_case(*stage("_nw_wifi_power T 0000000000000000 0000000000000010\n"
                                   "                 U _nw_wifi_scan_frequencies\n"))
    assert code == 1, (code, out, err)
    assert "FAIL station API: _nw_wifi_scan_frequencies" in out, out


@case
def an_archive_that_defines_a_scratch_stub_fails():
    code, out, err = run_case(*stage(BOTH + "_psci_smp_init T 0000000000000000 0000000000000010\n"))
    assert code == 1, (code, out, err)
    assert "FAIL stubs: _psci_smp_init" in out, out


@case
def an_absent_archive_is_not_a_pass():
    root = Path(tempfile.mkdtemp())
    archive = root / "libPongAth11k.a"
    code, out, err = run_case(archive, "/bin/true", "/bin/true")
    assert code == 2, (code, out, err)
    assert f"note: {archive} is absent; the 27 station archive has not been built" in err, err


@case
def an_arm64_member_fails_before_the_link_does():
    code, out, err = run_case(*stage(BOTH, cpusubtype=0))
    assert code == 1, (code, out, err)
    assert "FAIL members" in out and "is not arm64e" in out, out


@case
def a_stamp_that_describes_another_header_fails():
    code, out, err = run_case(*stage(BOTH, stamp_sha="00" * 32))
    assert code == 1, (code, out, err)
    assert "does not match" in out, out


@case
def a_missing_stamp_is_not_a_pass():
    code, out, err = run_case(*stage(BOTH, write_stamp=False))
    assert code == 2, (code, out, err)
    assert "FAIL stamp" in out, out


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
