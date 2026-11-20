#!/usr/bin/env python3
"""Stage what the iOS 27 device repository is missing from the cellular line.

The 27 kernel build reads its series from the device repository, so the five
ported patches and their series entries have to exist there.  This tool writes
that handoff into a staging directory and prints the two commands that land it;
it never writes into the device repository, which has a different owner.

usage: stage-ios27-device.py --device <device repo> [--patches <dir>] [--out <dir>]
                          [--self-test]
"""

import argparse
import difflib
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATCHES = os.path.join(REPO, "patches", "xnu-12377")
DEFAULT_OUT = "/mnt/e/k60-work/scratch/ios27-device-stage"
SERIES = "patches/xnu-12377/series"


def read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def series_names(text):
    names = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        names.append(entry.split()[0])
    return names


def stage(device, patches, out):
    """Write the handoff and return its exit code."""
    port = os.path.join(patches, "series-port.txt")
    if not os.path.exists(port):
        print("K60 STAGE INVALID no series-port.txt under " + patches)
        return 2
    port_text = read(port)
    wanted = series_names(port_text)
    if not wanted:
        print("K60 STAGE INVALID series-port.txt lists no patch")
        return 2
    for name in wanted:
        path = os.path.join(patches, name)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print("K60 STAGE INVALID %s is missing or empty" % name)
            return 2
    device_series = os.path.join(device, SERIES)
    if not os.path.exists(device_series):
        print("K60 STAGE INVALID the device repository has no " + SERIES)
        return 2
    old = read(device_series)
    present = set(series_names(old))
    have = [name for name in wanted if name in present]
    if have and len(have) != len(wanted):
        print("K60 STAGE REFUSED the device series lists %d of %d ported patches; fix it by hand: %s"
              % (len(have), len(wanted), " ".join(have)))
        return 1
    new = old
    if not have:
        if not new.endswith("\n"):
            new += "\n"
        new += port_text if port_text.endswith("\n") else port_text + "\n"

    shutil.rmtree(out, ignore_errors=True)
    staged = os.path.join(out, "patches", "xnu-12377")
    os.makedirs(staged)
    digests = {}
    for name in wanted:
        shutil.copy(os.path.join(patches, name), os.path.join(staged, name))
        with open(os.path.join(patches, name), "rb") as handle:
            digests[name] = hashlib.sha256(handle.read()).hexdigest()[:16]
    with open(os.path.join(out, "series.expected"), "w", encoding="utf-8") as handle:
        handle.write(new)
    diff = list(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                     fromfile="a/" + SERIES, tofile="b/" + SERIES))
    with open(os.path.join(out, "series.diff"), "w", encoding="utf-8") as handle:
        handle.write("".join(diff))
    commands = [
        "# land the cellular line into the 27 device repository",
        "cp %s/*.patch <device>/patches/xnu-12377/" % staged,
        "cp %s <device>/%s" % (os.path.join(out, "series.expected"), SERIES),
        "# or, for the series alone: git -C <device> apply %s" % os.path.join(out, "series.diff"),
        "python3 scripts/check-ios27-device.py --device <device>",
        "",
    ]
    with open(os.path.join(out, "apply.sh"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(commands))

    added = [line for line in port_text.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    state = "dry" if have else "ok"
    print("K60 STAGE %s %d patches (%s), the series gains %d entries (%s)"
          % (state, len(wanted), " ".join(digests[name] for name in wanted),
             len(added), " ".join(series_names(port_text)) if not have else "none"))
    print("K60 STAGE %s staged in %s; see apply.sh" % (state, out))
    if have:
        print("K60 STAGE ok   the device series already lists the ported patches")
    return 0


def self_test():
    work = tempfile.mkdtemp(prefix="k60-stage-")
    try:
        patches = os.path.join(work, "patches")
        os.makedirs(patches)
        names = ["0626-a.patch", "0627-b.patch"]
        with open(os.path.join(patches, "series-port.txt"), "w", encoding="utf-8") as handle:
            handle.write("# a comment\n" + "\n".join(names) + "\n")
        for name in names:
            with open(os.path.join(patches, name), "w", encoding="utf-8") as handle:
                handle.write(name + "\n")
        device = os.path.join(work, "device")
        target = os.path.join(device, "patches", "xnu-12377")
        os.makedirs(target)
        with open(os.path.join(target, "series"), "w", encoding="utf-8") as handle:
            handle.write("0500-bt.patch\n0510-bt-uart.patch\n")
        out = os.path.join(work, "out")
        if stage(device, patches, out) != 0:
            print("K60 STAGE FAIL a plain handoff was refused")
            return 1
        # the diff has to apply and produce exactly the staged series
        scratch = os.path.join(work, "apply")
        tree = os.path.join(scratch, "patches", "xnu-12377")
        os.makedirs(tree)
        shutil.copy(os.path.join(target, "series"), os.path.join(tree, "series"))
        subprocess.run(["git", "init", "-q", scratch], check=True)
        check = subprocess.run(["git", "-C", scratch, "apply", "--check",
                                os.path.join(out, "series.diff")])
        if check.returncode != 0:
            print("K60 STAGE FAIL the staged diff does not apply")
            return 1
        subprocess.run(["git", "-C", scratch, "apply", os.path.join(out, "series.diff")], check=True)
        if read(os.path.join(tree, "series")) != read(os.path.join(out, "series.expected")):
            print("K60 STAGE FAIL the applied series differs from the staged one")
            return 1
        # a second run must report the line as already listed, and change nothing
        with open(os.path.join(target, "series"), "w", encoding="utf-8") as handle:
            handle.write(read(os.path.join(tree, "series")))
        if stage(device, patches, out) != 0:
            print("K60 STAGE FAIL an already staged repository was refused")
            return 1
        if read(os.path.join(out, "series.expected")) != read(os.path.join(target, "series")):
            print("K60 STAGE FAIL a second run changed the series")
            return 1
        # a half-listed series is a state to fix by hand, not to append to
        with open(os.path.join(target, "series"), "w", encoding="utf-8") as handle:
            handle.write("0500-bt.patch\n0626-a.patch\n")
        if stage(device, patches, out) != 1:
            print("K60 STAGE FAIL a half-listed series was not refused")
            return 1
        print("K60 STAGE PASS handoff, diff applies, rerun is a no-op, half state refused")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--device")
    parser.add_argument("--patches", default=DEFAULT_PATCHES)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.device:
        parser.error("--device is required")
    return stage(args.device, args.patches, args.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
