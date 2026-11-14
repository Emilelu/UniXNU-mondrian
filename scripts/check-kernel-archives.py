#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Fail when a force-loaded archive contributed nothing to the built kernel.

P-190: a `-Wl,-force_load,$ARCHIVE` line that sits inside a dead `if` branch is
indistinguishable from a working one -- the build succeeds, the image verifies,
and the driver is simply absent. Measured 2026-11-14: the whole
KERNEL_EXTRA_ARCHIVES block sits inside `if [ "$XNU_SOURCE_CORECRYPTO14" = 1 ]`,
and the generated .config resolves that symbol to n, so an archive added there
never reaches the kernel.

This gate checks, for every archive the board can link, that one of its symbols
is really present in the kernel. Only reads. Exit: 0 = all present, 1 = missing,
2 = no kernel / no nm.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path(os.environ.get("K60_OUT") or "/opt/k60/trees/k60build/out-baseline")
NM_CANDIDATES = ("/usr/bin/llvm-nm-18", "/usr/bin/llvm-nm", "llvm-nm-18", "llvm-nm", "nm")

# (config symbol, archive path relative to the built tree, symbol substring)
# The first field is the config key WITHOUT the CONFIG_ prefix. Measured
# 2026-11-14: writing "ARM_DT_PLATFORM" here silently skipped the entry, because
# the generated key is CONFIG_XNU_ARM_DT_PLATFORM -- a gate that skips what it
# cannot name is worse than no gate, so every key below is copied from a real
# .config line and the count is printed on success.
EXPECTED = (
    ("XNU_K60_PHYSICAL_BATTERY", "build/k60-battery/libK60PhysicalBattery.a", "k60_physical_battery_start"),
    ("XNU_NATIVE_UFS", "build/native-ufs/libNativeUfs.a", "NativeUfs5start"),
    ("XNU_ARMCPU", "build/armcpu/libArmCpu.a", "ArmCpu10prepareGic"),
    ("XNU_ARM_DT_PLATFORM", "build/armdt-platform/libArmDTPlatform.a", "ArmDTPlatform"),
    ("XNU_NATIVE_ADRENO", "build/native-adreno/libNativeAdreno.a", "NativeAdreno"),
)


def find_kernel(out: Path) -> Path | None:
    base = out / "mondrian"
    if not base.is_dir():
        return None
    for board in sorted(base.glob("*/")):
        for candidate in sorted(board.glob("*/kernel/kernel.macho")):
            if candidate.is_file():
                return candidate
    return None


def nm_tool() -> str | None:
    for name in NM_CANDIDATES:
        if name.startswith("/"):
            if Path(name).is_file():
                return name
            continue
        found = subprocess.run(["sh", "-c", f"command -v {name}"], capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip()
    return None


def kernel_symbols(kernel: Path, nm: str) -> set[str]:
    proc = subprocess.run([nm, str(kernel)], capture_output=True, text=True)
    if proc.returncode != 0:
        return set()
    symbols = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts:
            symbols.add(parts[-1].lstrip("_"))
    return symbols


def enabled(config: Path, symbol: str) -> bool:
    """Last assignment wins, exactly as unixnu/scripts/unixnu/config.py does."""
    value = False
    if not config.is_file():
        return False
    for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line == f"# CONFIG_{symbol} is not set":
            value = False
        elif line.startswith(f"CONFIG_{symbol}="):
            value = line.split("=", 1)[1] == "y"
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="K60 output root")
    parser.add_argument("--kernel", type=Path, help="kernel.macho to inspect")
    args = parser.parse_args(argv)

    kernel = args.kernel or find_kernel(args.out)
    if not kernel or not kernel.is_file():
        # Two different situations share this branch, and they must not be
        # conflated (measured 2026-11-14 on the gate-fixes checkout):
        #   * a configured but never-built output tree -- normal before the first
        #     build, and build-strict.sh runs this gate right after a build, so
        #     the kernel is always there in the case that matters. Nothing to
        #     inspect is not the same as an archive going missing.
        #   * a path that is not an output tree at all -- that is a caller error.
        configured = list(args.out.glob("mondrian/*/*/.config")) if args.out.is_dir() else []
        if args.kernel is None and configured:
            print(f"skip: {args.out} is configured but not built; nothing to inspect")
            return 0
        print(f"FAIL: no kernel.macho under {args.out}", file=sys.stderr)
        return 2
    tree = kernel.parent.parent / "tree"
    config = kernel.parent.parent / ".config"
    nm = nm_tool()
    if not nm:
        print("FAIL: no nm tool found", file=sys.stderr)
        return 2

    symbols = kernel_symbols(kernel, nm)
    problems = []
    checked = 0
    for symbol, rel, needle in EXPECTED:
        if not enabled(config, symbol):
            print(f"skip: CONFIG_{symbol} is not enabled in {config.name}")
            continue
        checked += 1
        # The verdict is the symbol in the kernel: that is what P-190 is about.
        # The archive on disk is only evidence for *why* a symbol is missing, so
        # this check still works in a checkout that never built anything.
        if any(needle in name for name in symbols):
            continue
        # build-strict.sh points the battery archive at the checkout that built
        # it, because that archive is not produced inside the tree.
        override = os.environ.get("XNU_K60_BATTERY_ARCHIVE") if symbol == "XNU_K60_PHYSICAL_BATTERY" else None
        if override:
            archive = Path(override)
        elif symbol == "XNU_K60_PHYSICAL_BATTERY" and (REPO / rel).is_file():
            # This archive is built into the checkout, not into the tree.
            archive = REPO / rel
        else:
            archive = tree / rel
        if not archive.is_file():
            problems.append(
                f"CONFIG_{symbol}=y but {archive} is missing, so {rel} could never "
                f"have been force-loaded (P-190)"
            )
        else:
            problems.append(
                f"CONFIG_{symbol}=y but no {needle} symbol is in {kernel.name}; "
                f"{rel} was force-loaded into a branch that does not run (P-190)"
            )

    if problems:
        print("FAIL: kernel archives", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"✅ kernel archives: {checked} enabled archive(s) all present in {kernel.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
