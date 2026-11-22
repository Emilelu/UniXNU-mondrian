#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Grade the archive that CONFIG_XNU_NATIVE_UFS force-loads, in three states.

State 1 -- the switch is off: nothing is claimed, nothing is graded. `SKIP`,
exit 0. This is stage 0's state and it must stay quiet rather than green.
State 2 -- the switch is on, a producer exists, the archive exists and carries
the driver's symbols: `OK`, exit 0.
State 3 -- the switch is on but the archive is missing, the producer is missing,
or the archive lacks a required symbol: `FAIL`, exit 1.

Why a separate gate: scripts/build-xnu-generic.sh:648 tests for
build/native-ufs/libNativeUfs.a with a bare `test -f`, so a missing archive ends
the build with no message; and an archive built from stale objects can exist
while missing the driver's own entry point. Existence and content are two
different questions; this gate asks both, offline. It never builds anything.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SWITCH = "CONFIG_XNU_NATIVE_UFS"
DEFAULT_ARCHIVE = "build/native-ufs/libNativeUfs.a"
DEFAULT_PRODUCER = "scripts/build-native-ufs-linux.py"
REQUIRED_SYMBOLS = ("NativeUfs5start", "PongUfsBlock")
NM_CANDIDATES = ("/usr/bin/llvm-nm-18", "/usr/bin/llvm-nm", "llvm-nm-18", "llvm-nm", "nm")


def switch_state(defconfig: Path, key: str) -> bool | None:
    """True when the key is y/yes/1, False when n, None when the key is absent."""
    if not defconfig.is_file():
        return None
    pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*\"?([^\"\s#]+)\"?\s*$")
    for line in defconfig.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).lower() in ("y", "yes", "1", "true")
    return None


def find_nm(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for candidate in NM_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
        from shutil import which
        found = which(candidate)
        if found:
            return found
    return None


def archive_symbols(archive: Path, nm: str) -> set[str] | None:
    try:
        done = subprocess.run(shlex.split(nm) + ["--defined-only", str(archive)],
                              capture_output=True, text=True)
    except OSError:
        return None
    if done.returncode:
        return None
    return {line.split()[-1] for line in done.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--defconfig", type=Path, default=None,
                        help="default: <repo>/configs/mondrian_ios27_defconfig")
    parser.add_argument("--archive", type=Path, default=None,
                        help="default: <repo>/build/native-ufs/libNativeUfs.a")
    parser.add_argument("--producer", type=Path, default=None,
                        help="default: <repo>/scripts/build-native-ufs-linux.py")
    parser.add_argument("--switch", default=DEFAULT_SWITCH)
    parser.add_argument("--require-symbol", action="append", default=None)
    parser.add_argument("--nm", default=None,
                        help="llvm-nm executable, or a quoted shim command such as \"python fake-nm.py\"")
    args = parser.parse_args()

    repo = args.repo.resolve()
    defconfig = args.defconfig or (repo / "configs/mondrian_ios27_defconfig")
    archive = args.archive or (repo / DEFAULT_ARCHIVE)
    producer = args.producer or (repo / DEFAULT_PRODUCER)
    state = switch_state(defconfig, args.switch)

    if state is None:
        print("SKIP %s is absent from %s" % (args.switch, defconfig))
        print("ufs27-native-ufs-archive: skip")
        return 0
    if not state:
        print("SKIP %s is off in %s" % (args.switch, defconfig.name))
        print("ufs27-native-ufs-archive: skip")
        return 0

    problems: list[str] = []
    if not producer.is_file():
        problems.append("no producer: %s does not exist" % producer.relative_to(repo).as_posix())
    if not archive.is_file():
        problems.append("no archive: %s does not exist (the builder's bare test -f ends the build silently)" % archive.relative_to(repo).as_posix())
    if problems:
        for problem in problems:
            print("FAIL %s" % problem)
        print("ufs27-native-ufs-archive: FAIL (%d)" % len(problems))
        return 1

    required = args.require_symbol or list(REQUIRED_SYMBOLS)
    nm = find_nm(args.nm)
    if not nm:
        print("FAIL no llvm-nm found; pass --nm")
        print("ufs27-native-ufs-archive: FAIL (1)")
        return 1
    symbols = archive_symbols(archive, nm)
    if symbols is None:
        print("FAIL %s cannot read %s" % (nm, archive))
        print("ufs27-native-ufs-archive: FAIL (1)")
        return 1
    absent = [needle for needle in required if not any(needle in symbol for symbol in symbols)]
    if absent:
        print("FAIL %s lacks %s" % (archive.relative_to(repo).as_posix(), ", ".join(absent)))
        print("ufs27-native-ufs-archive: FAIL (%d)" % len(absent))
        return 1
    print("OK %s carries %s" % (archive.relative_to(repo).as_posix(), ", ".join(required)))
    print("ufs27-native-ufs-archive: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
