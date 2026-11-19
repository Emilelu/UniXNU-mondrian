#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-wifi-symbols.py.

The checker answers one question -- did -force_load put the driver in the
image? -- and its own failure mode is answering "yes" from a symbol table it
did not read: an undefined reference, or a name that only looks like ours.
Cases 1 and 2 are that pair. Case 4 guards the builder hook the count depends
on, because a hook that silently stopped arming would leave every 27 image
without a driver and every gate green.
"""

from __future__ import annotations

import importlib.util
import io
import contextlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-wifi-symbols.py"
GENERIC = ROOT / "scripts" / "build-xnu-generic.sh"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load():
    spec = importlib.util.spec_from_file_location("check_wifi_symbols", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fake_nm(text: str) -> str:
    """A stand-in nm that prints text, so the checker never needs a real image."""
    path = Path(tempfile.mkdtemp()) / "nm"
    path.write_text("#!/bin/sh\ncat <<'EOF'\n" + text + "EOF\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


@case
def defined_symbols_are_counted_and_references_are_not():
    checker = load()
    counts = checker.parse_nm(
        "0000000000001000 T _pong_wifi_start_optional\n"
        "                 U _pong_wifi_net_stop\n"
        "0000000000002000 t _pong_scan_monitor\n"
        "0000000000003000 T _not_ours\n"
    )
    assert counts == {"pong_wifi": 1, "pong_scan": 1}, counts


@case
def an_image_without_the_driver_fails():
    checker = load()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = checker.main(["image", "--nm", fake_nm("0000000000003000 T _not_ours\n")])
    assert code == 1, code
    assert "no PongWifi symbol" in err.getvalue(), err.getvalue()


@case
def an_image_with_the_driver_passes():
    checker = load()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = checker.main(["image", "--nm", fake_nm("0000000000001000 T _pong_wifi_start_optional\n")])
    assert code == 0, code
    assert "wifi symbols: 1" in out.getvalue(), out.getvalue()


@case
def the_generic_builder_arms_the_hook():
    text = GENERIC.read_text(encoding="utf-8")
    assert 'if [ "${XNU_PONG_WIFI:-0}" = 1 ]; then' in text, "the wifi hook is gone"
    assert "-Wl,-force_load,$PONG_WIFI_ARCHIVE" in text, "the hook no longer force-loads"
    assert "KERNEL_ARCHIVE_DEPENDENCIES" in text, "the hook no longer declares the dependency"


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
