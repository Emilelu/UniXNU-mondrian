#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Contract test for scripts/build-wifi27-kernel.sh.

The script exists so nobody has to rediscover, from scratch, that the 27 line links
the station archive only through XNU_PONG_WIFI and that a link is not evidence. Each
case below pins one of those facts: the two variables it must export, the OS key that
selects the 12377 series, the symbol check it must run last, and the refusals that
keep a mistyped invocation from producing a kernel nobody checked.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build-wifi27-kernel.sh"
CHECKER = ROOT / "scripts" / "check-wifi-symbols.py"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True)


@case
def it_exports_the_two_variables_the_generic_builder_reads():
    body = text()
    assert "export XNU_PONG_WIFI=1" in body, "the archive never reaches the builder"
    assert "export XNU_PONG_WIFI_ARCHIVE=$ARCHIVE" in body, body[:200]


@case
def it_defaults_to_the_device_series_and_the_ios27_os_key():
    body = text()
    assert "OS_PROFILE=ios-27.0.1-24A446" in body, "the 16 series would be applied"
    assert "--os \"$OS_PROFILE\"" in body, "the driver is not given the OS key"


@case
def it_counts_symbols_after_the_build_instead_of_trusting_it():
    body = text()
    assert CHECKER.name in body, "the script never checks what it linked"
    assert "mach.development" in body, "it does not look for the linked kernel"


@case
def a_missing_archive_is_refused_before_the_build():
    out = run("--archive", "/nonexistent/libPongWifiNative.a")
    assert out.returncode == 2, (out.returncode, out.stderr)
    assert "no station archive" in out.stderr, out.stderr


@case
def an_unknown_argument_is_refused():
    out = run("--nope")
    assert out.returncode == 2, (out.returncode, out.stderr)
    assert "unknown argument" in out.stderr, out.stderr


def main() -> int:
    failures = 0
    for fn in CASES:
        try:
            fn()
        except AssertionError as error:
            failures += 1
            print(f"FAIL {fn.__name__}: {error}")
        else:
            print(f"ok   {fn.__name__}")
    print(f"{len(CASES) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())