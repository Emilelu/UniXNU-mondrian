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

The producer carries a lineage: `build-native-ufs-linux.py` is the 27 producer,
any `*-macos.py` script is 16.6.1-only. Without --strict a 16-only producer is
accepted but labelled `NOTE 16.6.1-only`; with --strict it is not counted and the
gate fails, because the 27 profile never runs a macOS producer.
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


def relative(path: Path, repo: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return str(path)


def producer_lineage(producer: Path) -> str:
    """16 = 16.6.1-only, 27 = this line's producer, both = shared script."""
    if producer.name.endswith("-macos.py"):
        return "16"
    if producer.name == "build-native-ufs-linux.py":
        return "27"
    return "both"


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
    parser.add_argument("--strict", action="store_true",
                        help="a 16.6.1-only producer does not count as this line's producer")
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
    where = producer_lineage(producer)
    if where == "16":
        if args.strict:
            problems.append("producer %s is 16.6.1-only; the 27 line never runs it" % relative(producer, repo))
        else:
            print("NOTE 16.6.1-only producer %s" % relative(producer, repo))
    if not producer.is_file():
        problems.append("no producer: %s does not exist" % relative(producer, repo))
    if not archive.is_file():
        problems.append("no archive: %s does not exist (the builder's bare test -f ends the build silently)" % relative(archive, repo))
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
        print("FAIL %s lacks %s" % (relative(archive, repo), ", ".join(absent)))
        print("ufs27-native-ufs-archive: FAIL (%d)" % len(absent))
        return 1
    print("OK %s carries %s (producer %s [%s])" % (relative(archive, repo), ", ".join(required), relative(producer, repo), where))
    print("ufs27-native-ufs-archive: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
