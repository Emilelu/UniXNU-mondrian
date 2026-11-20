#!/usr/bin/env python3
"""Check that the iOS 27 device repository carries what the 27 kernel build reads.

The build resolves its patch series from the device repository (board.toml:
patch_series = [..., "device:patches/xnu-12377/series"]), not from this
repository.  Everything the cellular line generates therefore has to exist in
both places, byte for byte, in the order patches/xnu-12377/series-port.txt
records.  This tool compares the two and names what is missing.

usage: check-ios27-device.py --device <device repo> [--patches <dir>] [--self-test]
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATCHES = os.path.join(REPO, "patches", "xnu-12377")
DEVICE_SERIES = os.path.join("patches", "xnu-12377", "series")
BOARD = "board.toml"
NEEDLE = "device:patches/xnu-12377/series"


def read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def series_names(path):
    """Bare patch names from a series file, comments and blanks dropped."""
    names = []
    for line in read(path).splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        names.append(entry.split()[0])
    return names


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def device_board_names(device):
    """Component ids the 27 package includes, read without a TOML parser."""
    path = os.path.join(device, BOARD)
    if not os.path.exists(path):
        return None
    text = read(path)
    marker = '[os_overrides."ios-27.0.1-24A446".components]'
    start = text.find(marker)
    if start < 0:
        return None
    section = text[start + len(marker):]
    match = re.search(r"include\s*=\s*\[([^\]]*)\]", section)
    if not match:
        return None
    return [part.strip().strip(chr(34)).strip(chr(39))
            for part in match.group(1).split(",") if part.strip()]


UFS_SWITCH = "CONFIG_XNU_NATIVE_UFS="
BUILDER = os.path.join("scripts", "build-xnu-generic.sh")
UFS_ASSIGN = re.compile(r"UFS_ARCHIVE=\$ROOT/(\S+)")
# A line that names the archive only links it; the ones below write it.
WRITE_HINTS = ("libtool", "ar rcs", " -o ", "cp ", "install -m", "copyfile", "copy2")


def defconfig_path(device):
    """The defconfig the 27 kernel block names, else the stage-0 default."""
    default = os.path.join(device, "configs", "mondrian_ios27_defconfig")
    path = os.path.join(device, BOARD)
    if not os.path.exists(path):
        return default
    text = read(path)
    marker = '[os_overrides."ios-27.0.1-24A446".kernel]'
    start = text.find(marker)
    if start < 0:
        return default
    match = re.search(r'defconfig\s*=\s*"([^"]+)"', text[start:])
    if not match:
        return default
    return os.path.join(device, "configs", match.group(1))


def ufs_archive(device):
    """(True|False|None, why): can the 27 builder link the storage archive?

    The 27 profile builds with scripts/build-xnu-generic.sh (pick-xnu-builder.sh
    sends every profile but 16.6.1 there).  That script force-loads
    build/sheng-ufs/libPongUfs.a whenever CONFIG_XNU_NATIVE_UFS=y, and the only
    producer of a native UFS archive in either repository writes
    build/native-ufs/libNativeUfs.a from drivers/NativeUfs - a step that lives in
    build-xnu-4k-baseline.sh, which the 27 line never runs.  So flipping the
    switch without adding a producer stops the build at "test -f".
    """
    config = defconfig_path(device)
    if not os.path.exists(config):
        return None, "no 27 defconfig at " + os.path.basename(config)
    enabled = None
    for line in read(config).splitlines():
        if line.strip().startswith(UFS_SWITCH):
            enabled = line.strip()[len(UFS_SWITCH):].strip()
            break
    if enabled is None:
        return None, "the 27 defconfig does not set " + UFS_SWITCH.rstrip("=")
    if enabled != "y":
        return True, "the 27 defconfig keeps native UFS off (%s%s)" % (UFS_SWITCH, enabled)
    builder = os.path.join(device, BUILDER)
    if not os.path.exists(builder):
        return False, BUILDER.replace(os.sep, "/") + " is missing"
    match = UFS_ASSIGN.search(read(builder))
    if not match:
        return False, BUILDER.replace(os.sep, "/") + " names no archive to link"
    archive = match.group(1)
    scripts = os.path.join(device, "scripts")
    producers = []
    for name in sorted(os.listdir(scripts)) if os.path.isdir(scripts) else []:
        if not name.endswith((".sh", ".py")):
            continue
        for number, line in enumerate(read(os.path.join(scripts, name)).splitlines(), 1):
            if archive in line and any(hint in line for hint in WRITE_HINTS):
                producers.append("%s:%d" % (name, number))
    if not producers:
        return (False, "native UFS is on and nothing writes the archive " + BUILDER.replace(os.sep, "/")
                + " links (" + archive + ")")
    return True, "the archive the 27 builder links is written by " + " ".join(producers)


def check(device, patches):
    """Return (drift, notes) after comparing the device repository with ours."""
    drift, notes = 0, []
    board = os.path.join(device, BOARD)
    if not os.path.exists(board):
        print("K60 DEVICE INVALID no %s under %s" % (BOARD, device))
        return None, []
    if NEEDLE not in read(board):
        drift += 1
        print("K60 DEVICE DRIFT %s does not list %s in patch_series" % (BOARD, NEEDLE))
    else:
        print("K60 DEVICE ok   %s lists %s" % (BOARD, NEEDLE))

    ours = os.path.join(patches, "series-port.txt")
    if not os.path.exists(ours):
        print("K60 DEVICE INVALID no series-port.txt under " + patches)
        return None, []
    wanted = series_names(ours)

    theirs_path = os.path.join(device, DEVICE_SERIES)
    if not os.path.exists(theirs_path):
        drift += 1
        print("K60 DEVICE DRIFT the device repository has no " + DEVICE_SERIES)
        return drift, notes
    theirs = series_names(theirs_path)
    missing = [name for name in wanted if name not in theirs]
    if missing:
        drift += 1
        print("K60 DEVICE DRIFT %d of %d ported patches are not in the device series: %s"
              % (len(missing), len(wanted), " ".join(missing)))
    else:
        order = [theirs.index(name) for name in wanted]
        if order != sorted(order):
            drift += 1
            print("K60 DEVICE DRIFT the ported patches are out of order in the device series")
        else:
            print("K60 DEVICE ok   %d ported patches are in the device series, in order"
                  % len(wanted))

    differing, absent = [], []
    for name in wanted:
        mine = os.path.join(patches, name)
        other = os.path.join(device, DEVICE_SERIES.rsplit("/", 1)[0], name)
        if not os.path.exists(other):
            absent.append(name)
        elif sha256(mine) != sha256(other):
            differing.append(name)
    if absent:
        drift += 1
        print("K60 DEVICE DRIFT the device repository has no copy of: " + " ".join(absent))
    elif differing:
        drift += 1
        print("K60 DEVICE DRIFT copies differ from ours: " + " ".join(differing))
    else:
        print("K60 DEVICE ok   every ported patch is byte-identical in both repositories")

    included = device_board_names(device)
    if included is None:
        notes.append("the 27 package block does not list its components")
        print("K60 DEVICE note the 27 package block lists no components")
    elif "QcomBaseband" in included:
        print("K60 DEVICE ok   the 27 package includes QcomBaseband")
    else:
        notes.append("QcomBaseband is not in the 27 package include list")
        print("K60 DEVICE note QcomBaseband is not in the 27 package include list")
    # Two components, two different jobs: QcomBaseband answers for the seven
    # coachz symbols at link time, PongUfs is what can read a named volume at
    # all. Both are notes, not drift: the freeze keeps them off main until F3.
    if included is not None and "PongUfs" not in included:
        notes.append("PongUfs is not in the 27 package include list")
        print("K60 DEVICE note PongUfs is not in the 27 package include list either")
    elif included is not None:
        print("K60 DEVICE ok   the 27 package includes PongUfs")

    done, why = ufs_archive(device)
    if done is None:
        notes.append(why)
        print("K60 DEVICE note " + why)
    elif done:
        print("K60 DEVICE ok   " + why)
    else:
        drift += 1
        print("K60 DEVICE DRIFT " + why)
    return drift, notes


def self_test():
    work = tempfile.mkdtemp(prefix="k60-device-")
    try:
        patches = os.path.join(work, "patches", "xnu-12377")
        os.makedirs(patches)
        names = ["0626-a.patch", "0627-b.patch"]
        with open(os.path.join(patches, "series-port.txt"), "w", encoding="utf-8") as handle:
            handle.write("# comment\n" + "\n".join(names) + "\n")
        for name in names:
            with open(os.path.join(patches, name), "w", encoding="utf-8") as handle:
                handle.write(name + "\n")
        device = os.path.join(work, "device")
        target = os.path.join(device, "patches", "xnu-12377")
        os.makedirs(target)
        with open(os.path.join(device, BOARD), "w", encoding="utf-8") as handle:
            handle.write('[os_overrides."ios-27.0.1-24A446".kernel]\n'
                         'patch_series = ["device:patches/xnu-12377/series"]\n'
                         '[os_overrides."ios-27.0.1-24A446".components]\n'
                         'include = ["ArmDTPlatform", "QcomBaseband"]\n')
        with open(os.path.join(target, "series"), "w", encoding="utf-8") as handle:
            handle.write("0500-bt.patch\n" + "\n".join(names) + "\n")
        for name in names:
            shutil.copy(os.path.join(patches, name), os.path.join(target, name))
        if check(device, patches)[0] != 0:
            print("K60 DEVICE FAIL a complete device repository was reported as drift")
            return 1
        with open(os.path.join(target, "series"), "w", encoding="utf-8") as handle:
            handle.write("0500-bt.patch\n0626-a.patch\n")
        if check(device, patches)[0] == 0:
            print("K60 DEVICE FAIL a missing series entry was not reported")
            return 1
        with open(os.path.join(target, "series"), "w", encoding="utf-8") as handle:
            handle.write("0500-bt.patch\n" + "\n".join(names) + "\n")
        with open(os.path.join(target, "0627-b.patch"), "w", encoding="utf-8") as handle:
            handle.write("changed\n")
        if check(device, patches)[0] == 0:
            print("K60 DEVICE FAIL a differing copy was not reported")
            return 1
        # Undo the perturbation: the fixtures below expect a clean comparison.
        with open(os.path.join(target, "0627-b.patch"), "w", encoding="utf-8") as handle:
            handle.write("0627-b.patch\n")
        # The storage archive: off is fine, on without a producer is drift, and
        # a producer anywhere in scripts/ clears it.
        scripts = os.path.join(device, "scripts")
        configs = os.path.join(device, "configs")
        os.makedirs(scripts)
        os.makedirs(configs)
        with open(os.path.join(scripts, "build-xnu-generic.sh"), "w", encoding="utf-8") as handle:
            handle.write('UFS_ARCHIVE=$ROOT/build/sheng-ufs/libPongUfs.a\n'
                         'KERNEL_EXTRA_ARCHIVES="$KERNEL_EXTRA_ARCHIVES -Wl,-force_load,$UFS_ARCHIVE"\n')
        config = os.path.join(configs, "mondrian_ios27_defconfig")
        with open(config, "w", encoding="utf-8") as handle:
            handle.write("CONFIG_XNU_NATIVE_UFS=n\n")
        if check(device, patches)[0] != 0:
            print("K60 DEVICE FAIL a disabled UFS switch was reported as drift")
            return 1
        with open(config, "w", encoding="utf-8") as handle:
            handle.write("CONFIG_XNU_NATIVE_UFS=y\n")
        if check(device, patches)[0] == 0:
            print("K60 DEVICE FAIL an archive nobody writes was not reported")
            return 1
        with open(os.path.join(scripts, "build-pong-ufs.sh"), "w", encoding="utf-8") as handle:
            handle.write("libtool -static -o $ROOT/build/sheng-ufs/libPongUfs.a transport.o\n")
        if check(device, patches)[0] != 0:
            print("K60 DEVICE FAIL a produced archive was reported as drift")
            return 1
        print("K60 DEVICE PASS agreement, missing entry, differing copy, archive producer")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--device")
    parser.add_argument("--patches", default=DEFAULT_PATCHES)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.device:
        parser.error("--device is required")
    drift, _notes = check(args.device, args.patches)
    if drift is None:
        return 2
    if drift:
        print("K60 DEVICE CHANGED %d expectation(s) drifted" % drift)
        return 1
    print("K60 DEVICE OK the device repository carries the 27 line")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
