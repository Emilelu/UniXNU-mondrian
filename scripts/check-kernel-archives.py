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
    # Off by default (CONFIG_XNU_PONG_THERMAL=n); when switched on this row is
    # what catches the archive being force-loaded into a branch that never runs.
    ("XNU_PONG_THERMAL", "build/thermal-kext/libK60ThermalKext.a", "k60_thermal_start"),
)

# Archives the board links through an environment variable instead of a
# defconfig archive entry: (config symbol, override variable, checkout-relative
# path, entry point, optional later symbol). build-strict.sh:195-219 turns
# CONFIG_XNU_PONG_WIFI=y (or XNU_PONG_WIFI=1) into XNU_PONG_WIFI_ARCHIVE and the
# kernel link force-loads it, so neither .config nor [kernel] archives names the
# file. The official porting checklist (porting/network, build and verification)
# asks for exactly two inspections of an archive like this before a flight:
# `llvm-ar t` to prove the members are real objects and `llvm-nm
# --defined-only` to prove the entry point is defined rather than imported.
ENV_ARCHIVES = (
    ("XNU_PONG_WIFI", "XNU_PONG_WIFI_ARCHIVE", "build/pong-wifi/libPongWifiNative.a",
     "pong_wifi_start_optional", "pong_wifi_net_stop"),
)

AR_CANDIDATES = ("/usr/bin/llvm-ar-18", "/usr/bin/llvm-ar", "llvm-ar-18", "llvm-ar")


def find_kernel(out: Path) -> Path | None:
    """Return the newest kernel.macho under the output tree.

    Sorting by path used to decide this, so a kernel left behind by an earlier
    build was graded as if it were the current one (P-202).  The newest file is
    still only a guess -- build-strict.sh passes --kernel for that reason -- but
    guessing the stale one is strictly worse than guessing the fresh one.
    """
    base = out / "mondrian"
    if not base.is_dir():
        return None
    candidates = [
        candidate
        for board in sorted(base.glob("*/"))
        for candidate in board.glob("*/kernel/kernel.macho")
        if candidate.is_file()
    ]
    if not candidates:
        return None
    if len(candidates) > 1:
        print(
            f"note: {len(candidates)} kernels under {out}; grading the newest "
            f"({candidates[0].parent.parent.parent.parent.name}), pass --kernel to be explicit",
            file=sys.stderr,
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


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


def ar_tool() -> str | None:
    """The ar next to the nm this gate picked; llvm-ar reads Mach-O archives."""
    for name in AR_CANDIDATES:
        if name.startswith("/"):
            if Path(name).is_file():
                return name
            continue
        found = subprocess.run(["sh", "-c", f"command -v {name}"], capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip()
    return None


def parse_defined_symbols(text: str) -> set[str]:
    """Symbols nm lists as defined, with or without --defined-only.

    An archive member that only imports a name prints "U name". Counting that as
    defined is the exact confusion this gate exists to prevent (P-190), so the
    marker column decides rather than the presence of the name.
    """
    defined: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-2] != "U":
            defined.add(parts[-1].lstrip("_"))
    return defined


def inspect_archive(archive: Path, nm: str, ar: str | None) -> tuple[int, set[str]]:
    """(member count, defined symbols) for one archive; never raises."""
    members = 0
    if ar:
        proc = subprocess.run([ar, "t", str(archive)], capture_output=True, text=True)
        if proc.returncode == 0:
            members = sum(1 for line in proc.stdout.splitlines() if line.strip())
    proc = subprocess.run([nm, "--defined-only", str(archive)], capture_output=True, text=True)
    if proc.returncode != 0:
        proc = subprocess.run([nm, str(archive)], capture_output=True, text=True)
    return members, parse_defined_symbols(proc.stdout)


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
    parser.add_argument("--adsp-blob", action="store_true",
                        help="the build passed --adsp-blob; expect k60_adsp_blob in the kernel")
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
    # A configured-but-not-rebuilt out tree pairs a fresh .config with an old
    # kernel. The symbol list of that kernel cannot answer P-190, and the
    # registry runs before the build that would refresh it (same shape as the
    # P-194 deadlock): skip instead of failing on a stale pair.
    if config.is_file() and kernel.stat().st_mtime < config.stat().st_mtime:
        print(f"skip: {kernel.name} predates {config.name} in {args.out}; the out "
              f"tree was configured but not rebuilt, so its symbol list cannot "
              f"answer P-190 (the build that would refresh it is what this "
              f"registry is gating)")
        return 0
    nm = nm_tool()
    if not nm:
        print("FAIL: no nm tool found", file=sys.stderr)
        return 2
    ar = ar_tool()

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

    # The environment-selected archives, inspected rather than trusted: an
    # archive that exists but holds no members, or holds an import instead of
    # the definition, links without a symbol and the kernel simply has no WiFi.
    for symbol, env_name, rel, entry, later in ENV_ARCHIVES:
        if not enabled(config, symbol):
            print(f"skip: CONFIG_{symbol} is not enabled in {config.name}")
            continue
        checked += 1
        override = os.environ.get(env_name)
        archive = Path(override) if override else REPO / rel
        if not archive.is_file():
            if override:
                problems.append(
                    f"{env_name}={override} does not exist; the build would link "
                    f"nothing under CONFIG_{symbol}=y (P-190)"
                )
            else:
                # No override: build-strict.sh:215 already refuses this exact
                # configuration before the link, and the registry runs this gate
                # for every line, so failing here would block builds that never
                # asked this checkout for a wifi archive.
                print(
                    f"skip: {env_name} is unset and {archive} is absent; nothing "
                    f"to inspect for CONFIG_{symbol}"
                )
            continue
        members, defined = inspect_archive(archive, nm, ar)
        if ar and members == 0:
            problems.append(
                f"CONFIG_{symbol}=y but {ar} t {archive.name} lists no members: "
                f"the file is an archive header without objects (P-190)"
            )
        if entry not in defined:
            problems.append(
                f"CONFIG_{symbol}=y but {archive.name} does not define {entry}; "
                f"the link would import it from nowhere and the force_load would "
                f"add nothing (P-190)"
            )
        elif later and later not in defined:
            # A stale archive predates the teardown export; failing here would
            # block the rebuild that fixes it (same deadlock shape as P-207).
            print(
                f"note: {archive.name} does not export {later} yet; rebuild the "
                f"wifi archive before relying on the stop path",
                file=sys.stderr,
            )

    if problems:
        print("FAIL: kernel archives", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    # P-208: a force-loaded archive whose call site compiled away is just as
    # dead as one inside a false branch, and it links without an error because
    # force_load pulls the members in. The guarded blocks live in
    # iokit/bsddev/IOKitBSDInit.cpp, so that object must reference the archive.
    # Same scope rule as P-207: the object only answers P-208 when this run
    # produced it. The registered check command runs without --kernel, before
    # the build, against the previous build's tree -- judging that one would
    # block the very build that refreshes it.
    if enabled(config, "XNU_K60_PHYSICAL_BATTERY") and args.kernel is not None:
        objects = sorted(tree.glob("build/xnu/ios-obj/*/iokit/*/IOKitBSDInit.cpo"),
                         key=lambda p: p.stat().st_mtime)
        if objects:
            newest = objects[-1]
            proc = subprocess.run([nm, "-u", str(newest)], capture_output=True, text=True)
            if proc.returncode == 0:
                referenced = "k60_adsp_handoff_publish" in proc.stdout
            else:
                # A fixture is not a Mach-O object, so fall back to the string
                # table bytes: an undefined symbol keeps its name there.
                referenced = b"k60_adsp_handoff_publish" in newest.read_bytes()
            if not referenced:
                problems.append(
                    "CONFIG_XNU_K60_PHYSICAL_BATTERY=y but "
                    "iokit/bsddev/IOKitBSDInit.cpp has no call to "
                    "k60_adsp_handoff_publish: the guarded block compiled away, "
                    "so the battery entry point and the ADSP publisher never run "
                    "(P-208; the define must reach that translation unit, not "
                    "only KernelConfigTables.cpo)"
                )
        else:
            print("skip: no IOKitBSDInit.cpo under the tree, so the kernel was "
                  "not compiled far enough to answer P-208")
    if problems:
        print("FAIL: kernel archives", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if args.adsp_blob:
        if any("k60_adsp_blob" in name for name in symbols):
            print("✅ kernel archives: ADSP carrier blob linked (k60_adsp_blob present)")
        else:
            blob_s = tree / ".cache/xnu-work/osfmk/arm64/k60_adsp_blob.s"
            evidence = "generated and staged" if blob_s.is_file() else "staging file missing"
            print(
                f"FAIL: --adsp-blob was requested but no k60_adsp_blob symbol is in "
                f"{kernel.name}; the carrier was {evidence}",
                file=sys.stderr,
            )
            return 1
    print(f"✅ kernel archives: {checked} enabled archive(s) all present in {kernel.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
