#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-kernel-archives.py (P-190).

The gate exists because a force-loaded archive inside a dead `if` branch looks
exactly like a working one. Its own failure mode is subtler: a mistyped config
key makes it skip an archive and still print a green tick. That is what case 1
guards -- every key in EXPECTED must be a real key in the shipped defconfig.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-kernel-archives.py"
DEFCONFIG = ROOT / "configs" / "mondrian_defconfig"

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location("check_kernel_archives", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@case
def every_expected_key_is_a_real_defconfig_key():
    gate = load_gate()
    text = DEFCONFIG.read_text(encoding="utf-8", errors="replace")
    keys = set(re.findall(r"^CONFIG_([A-Z0-9_]+)=", text, re.M))
    keys |= set(re.findall(r"^# CONFIG_([A-Z0-9_]+) is not set", text, re.M))
    for symbol, _rel, _needle in gate.EXPECTED:
        assert symbol in keys, f"CONFIG_{symbol} is not in {DEFCONFIG.name} (the gate would skip it)"


@case
def expected_entries_are_unique():
    gate = load_gate()
    symbols = [symbol for symbol, _rel, _needle in gate.EXPECTED]
    assert len(symbols) == len(set(symbols)), f"duplicate config key in EXPECTED: {symbols}"
    rels = [rel for _symbol, rel, _needle in gate.EXPECTED]
    assert len(rels) == len(set(rels)), f"duplicate archive path in EXPECTED: {rels}"


@case
def last_assignment_wins():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / ".config"
        config.write_text(
            "CONFIG_XNU_SOURCE_CORECRYPTO14=y\n"
            "# CONFIG_XNU_SOURCE_CORECRYPTO14 is not set\n",
            encoding="utf-8",
        )
        assert gate.enabled(config, "XNU_SOURCE_CORECRYPTO14") is False
        config.write_text(
            "# CONFIG_XNU_SOURCE_CORECRYPTO14 is not set\n"
            "CONFIG_XNU_SOURCE_CORECRYPTO14=y\n",
            encoding="utf-8",
        )
        assert gate.enabled(config, "XNU_SOURCE_CORECRYPTO14") is True
        assert gate.enabled(Path(tmp) / "absent", "ANY") is False


@case
def a_missing_symbol_fails_the_gate():
    """The whole point: an archive that is configured but absent must fail."""
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mondrian" / "sdk" / "board"
        (out / "kernel").mkdir(parents=True)
        (out / ".config").write_text(
            "CONFIG_XNU_K60_PHYSICAL_BATTERY=y\n"
            "CONFIG_XNU_NATIVE_UFS=y\n",
            encoding="utf-8",
        )
        kernel = out / "kernel" / "kernel.macho"
        kernel.write_bytes(b"\x00" * 64)
        tree = out / "tree"
        (tree / "build" / "k60-battery").mkdir(parents=True)
        (tree / "build" / "k60-battery" / "libK60PhysicalBattery.a").write_bytes(b"!<arch>\n")
        (tree / "build" / "native-ufs").mkdir(parents=True)
        (tree / "build" / "native-ufs" / "libNativeUfs.a").write_bytes(b"!<arch>\n")
        rc = gate.main(["--out", str(Path(tmp)), "--kernel", str(kernel)])
        assert rc == 1, f"expected failure for a kernel with no symbols, got {rc}"


@case
def no_kernel_is_an_error():
    gate = load_gate()
    with tempfile.TemporaryDirectory() as tmp:
        rc = gate.main(["--out", tmp])
        assert rc == 2, f"expected 2 when no kernel exists, got {rc}"


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
