#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Build drivers/NativeUfs into build/native-ufs/libNativeUfs.a on the Linux host.

The 16.6.1 line compiles this driver with scripts/build-pong-ufs-probe-macos.py
through xcrun; that path does not exist on the machine that builds iOS 27. This
is the Linux counterpart, with the same source list and the same defines, using
the cross toolchain the rest of the 27 build already uses:

    clang-24            /opt/unixnu-linux/llvm/bin/clang-24
    llvm-libtool-darwin /usr/bin/llvm-libtool-darwin-18
    llvm-nm             /usr/bin/llvm-nm-18

Output: <device>/build/native-ufs/libNativeUfs.a, the path
scripts/build-xnu-generic.sh:649 force-loads when XNU_NATIVE_UFS=1.

Two macros come from the defconfig rather than from a flag, because they change
what the driver compiles and the board record must be able to set them:

    NATIVE_VERIFIED_BLOCK   <- CONFIG_XNU_VERIFIED_ROOT_PROBE       (0/1)
    XNU_PONG_UFS_DATA       <- CONFIG_XNU_OWNER_DATA_UFS            (0/1)

Also honoured, as on the macOS producer: CONFIG_XNU_PONG_EARLY_TRACE.
Everything is static and offline: --dry-run prints every command and touches
nothing; a real run works only on a host that has the toolchain and an assembled
tree with the kernel headers.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEVICE = Path(__file__).resolve().parents[1]
CXX = "/opt/unixnu-linux/llvm/bin/clang-24"
CC = "/opt/unixnu-linux/llvm/bin/clang-24"
LIBTOOL = "/usr/bin/llvm-libtool-darwin-18"
NM = "/usr/bin/llvm-nm-18"
TARGET = "arm64-apple-ios27.0"

CXX_SOURCES = (("NativeUfs.cpp", "NativeUfs.o"), ("PongUfsTransport.cpp", "PongUfsTransport.o"))
C_SOURCES = (("verified_root.c", "verified_root.o"), ("xnu_crypto.c", "xnu_crypto.o"))
REQUIRED_SYMBOLS = ("NativeUfs5start", "PongUfsBlock")

BASE_DEFINES = ("KERNEL=1", "KERNEL_PRIVATE=1", "XNU_KERNEL_PRIVATE=1")


def read_defconfig(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        values[match.group(1)] = value
    return values


def flag(defconfig: dict[str, str], key: str, default: int = 0) -> int:
    value = defconfig.get(key, str(default)).strip().lower()
    return 1 if value in ("y", "yes", "1", "true") else 0


def include_flags(tree: Path, device: Path) -> list[str]:
    framework = tree / ".cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A"
    storage = tree / "build/storage-abi/include"
    if not storage.is_dir():
        storage = device / "mac-build/storage-abi/include"
    return [
        "-I" + str(tree / ".cache/xnu-work/EXTERNAL_HEADERS"),
        "-I" + str(framework / "PrivateHeaders"),
        "-I" + str(framework / "Headers"),
        "-I" + str(storage),
        "-I" + str(device / "drivers"),
        "-I" + str(device / "drivers/NativeUfs"),
    ]


def cxx_command(source: Path, obj: Path, defines: dict[str, int], includes: list[str]) -> list[str]:
    argv = [CXX, "-target", TARGET, "-mkernel", "-ffreestanding", "-fno-builtin",
            "-fno-exceptions", "-fno-rtti", "-fno-stack-check", "-std=gnu++17",
            "-fblocks", "-O2"]
    argv += ["-D" + name for name in BASE_DEFINES]
    argv += ["-DXNU_PONG_EARLY_TRACE=%d" % defines["trace"]]
    argv += ["-DXNU_PONG_UFS_DATA=%d" % defines["data"]]
    argv += ["-DNATIVE_VERIFIED_BLOCK=%d" % defines["verified"]]
    argv += includes
    argv += ["-Wall", "-Wextra", "-Werror", "-Wno-deprecated-declarations",
             "-Wno-unused-parameter", "-Wno-c99-designator", "-Wno-reorder-init-list",
             "-Wno-deprecated-enum-enum-conversion", "-Wno-unnecessary-virtual-specifier",
             "-c", str(source), "-o", str(obj)]
    return argv


def cc_command(source: Path, obj: Path, includes: list[str]) -> list[str]:
    argv = [CC, "-target", TARGET, "-mkernel", "-ffreestanding", "-fno-builtin",
            "-fno-stack-protector", "-std=gnu11", "-O2"]
    argv += ["-D" + name for name in BASE_DEFINES]
    argv += includes
    argv += ["-Wall", "-Wextra", "-Werror", "-Wno-deprecated-declarations",
             "-Wno-unused-parameter", "-c", str(source), "-o", str(obj)]
    return argv


def nm_symbols(archive: Path, nm: str) -> set[str] | None:
    done = subprocess.run([nm, "--defined-only", str(archive)], capture_output=True, text=True)
    if done.returncode:
        return None
    return {line.split()[-1] for line in done.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", type=Path, default=DEVICE)
    parser.add_argument("--tree", type=Path, default=None,
                        help="assembled tree holding .cache/xnu-work and .cache/fakeroot (default: --device)")
    parser.add_argument("--defconfig", type=Path, default=None,
                        help="default: <device>/configs/mondrian_ios27_defconfig")
    parser.add_argument("--out", type=Path, default=None,
                        help="default: <device>/build/native-ufs")
    parser.add_argument("--clang", default=CXX)
    parser.add_argument("--libtool", default=LIBTOOL)
    parser.add_argument("--nm", default=NM)
    parser.add_argument("--require-symbol", action="append", default=None,
                        help="symbol substring that must appear in the archive (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    device = args.device.resolve()
    tree = (args.tree or device).resolve()
    defconfig_path = args.defconfig or (device / "configs/mondrian_ios27_defconfig")
    out = args.out or (device / "build/native-ufs")
    if not defconfig_path.is_file():
        print("FAIL defconfig not found: %s" % defconfig_path)
        return 1
    config = read_defconfig(defconfig_path)
    defines = {
        "trace": flag(config, "CONFIG_XNU_PONG_EARLY_TRACE"),
        "data": flag(config, "CONFIG_XNU_OWNER_DATA_UFS"),
        "verified": flag(config, "CONFIG_XNU_VERIFIED_ROOT_PROBE"),
    }
    includes = include_flags(tree, device)
    sources = [(name, obj, "cxx") for name, obj in CXX_SOURCES]
    if defines["verified"]:
        sources += [(name, obj, "c") for name, obj in C_SOURCES]
    else:
        print("note: NATIVE_VERIFIED_BLOCK=0, verified_root.c and xnu_crypto.c stay out")

    missing = [str(device / "drivers/NativeUfs" / name) for name, _, _ in sources
               if not (device / "drivers/NativeUfs" / name).is_file()]
    if missing:
        print("FAIL source not found: %s" % ", ".join(missing))
        return 1
    for flag_path in includes:
        if flag_path.startswith("-I") and not Path(flag_path[2:]).is_dir():
            print("note: include directory absent: %s" % flag_path[2:])

    commands: list[tuple[str, list[str]]] = []
    objects: list[str] = []
    for name, obj, kind in sources:
        source = device / "drivers/NativeUfs" / name
        target = out / obj
        if kind == "c":
            argv = cc_command(source, target, includes)
        else:
            argv = cxx_command(source, target, defines, includes)
        argv[0] = args.clang
        commands.append(("compile %s" % name, argv))
        objects.append(str(target))
    archive = out / "libNativeUfs.a"
    commands.append(("archive", [args.libtool, "-static", "-o", str(archive), *objects]))

    if args.dry_run:
        for label, argv in commands:
            print("# %s" % label)
            print(" ".join(argv))
        print("native-ufs-linux: dry run (%d command(s), output %s)" % (len(commands), archive))
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for label, argv in commands:
        if label == "archive":
            if archive.exists():
                archive.unlink()
        done = subprocess.run(argv, capture_output=True, text=True)
        if done.returncode:
            print(done.stdout[-2000:])
            print(done.stderr[-4000:])
            print("FAIL %s (exit %d)" % (label, done.returncode))
            return 1
    required = args.require_symbol or list(REQUIRED_SYMBOLS)
    symbols = nm_symbols(archive, args.nm)
    if symbols is None:
        print("FAIL %s cannot read %s" % (args.nm, archive))
        return 1
    absent = [needle for needle in required if not any(needle in symbol for symbol in symbols)]
    if absent:
        print("FAIL the archive lacks %s" % ", ".join(absent))
        return 1
    print("  archived %-22s %8d bytes" % ("libNativeUfs.a", archive.stat().st_size))
    print("  symbols: %s" % ", ".join(sorted({s for s in symbols if any(n in s for n in required)})))
    print("native-ufs-linux: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
