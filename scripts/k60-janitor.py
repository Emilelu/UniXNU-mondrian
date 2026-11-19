#!/usr/bin/env python3
"""Reclaim build space the lines leave behind, and say exactly what it removed.

Why this exists
---------------
On 2026-11-19 the WSL virtual disk reached 181.8 GB. The accounting was:

    /opt/k60/trees  70 GB   (25 stale `power-conformance-battery-*` OUTPUTs, 1.8 GB each)
    /home/emilelu   52 GB   (IPSWs and extracted components -- still needed)
    /tmp            30 GB   (7101 entries, 18.3 GB older than a day)

A build OUT is reproducible from the repository plus the build input, so keeping
one per experiment forever is pure waste. The failure is not that a line built
twenty-eight times -- it is that nothing ever deleted the twenty-five it did not
need. This script is that deletion, with a dry run by default.

What it does NOT touch
---------------------
  * any `/tmp` symlink (`/tmp/k60build`, `/tmp/usb-cdc-mainline`, `/tmp/fakeroot`
    point *into* a build tree, so deleting the link would break a shim while
    deleting the target would break a build),
  * the newest `--keep` OUTs of each prefix, and anything younger than `--days`,
  * `--protect` paths and whatever `K60_KEEP` names (space separated),
  * repositories, build mirrors (`gates-device`, `k60build`), IPSWs.

Usage
-----
    python3 scripts/k60-janitor.py                 # dry run, prints the plan
    python3 scripts/k60-janitor.py --apply         # performs it
    python3 scripts/k60-janitor.py --apply --json  # for a scheduled task
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

TREES = os.environ.get("K60_TREES", "/opt/k60/trees")
TMP = os.environ.get("K60_TMP", "/tmp")

# Mirrors are inputs, not output. Deleting one costs a full re-fetch (the ADT and
# kernel toolchain live there), so they are named rather than pattern-matched.
PROTECTED_TREES = {
    "k60build",                 # shared build tree (also /tmp/k60build's target)
    "gates-device",             # the build input mirror
    "usb-cdc-mainline",         # second input mirror (also a /tmp symlink target)
    "gates-out",
}

# `name-20261119ac` / `name-20261118n`: a stamp suffix, one per experiment.
STAMP = re.compile(r"^(?P<prefix>.+?)-(?P<stamp>\d{8}[a-z0-9]{0,3})$")


def directory_bytes(path):
    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
        # A symlinked subdirectory is somebody else's tree; do not follow or count it.
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
    return total


def age_days(path):
    try:
        return (time.time() - os.lstat(path).st_mtime) / 86400.0
    except OSError:
        return 0.0


def plan_trees(trees, keep, days, extra_protect):
    """Return [(path, bytes, reason)] for OUTs old enough to delete."""
    if not os.path.isdir(trees):
        return []
    groups = {}
    for name in os.listdir(trees):
        full = os.path.join(trees, name)
        if not os.path.isdir(full) or os.path.islink(full):
            continue
        if name in PROTECTED_TREES or full in extra_protect:
            continue
        match = STAMP.match(name)
        if not match:
            continue
        groups.setdefault(match.group("prefix"), []).append(full)
    doomed = []
    for prefix, paths in sorted(groups.items()):
        # The newest `keep` stay, whether or not they are old: a line that has been
        # idle for a week may still need its last output to answer a question.
        paths.sort(key=lambda p: age_days(p))
        for path in paths[keep:]:
            if age_days(path) < days:
                continue
            doomed.append((path, directory_bytes(path), "older than %g day(s), beyond the newest %d" % (days, keep)))
    return doomed


def plan_tmp(tmp, hours, extra_protect):
    if not os.path.isdir(tmp):
        return []
    doomed = []
    for name in os.listdir(tmp):
        full = os.path.join(tmp, name)
        if os.path.islink(full) or full in extra_protect:
            continue
        try:
            age_hours = (time.time() - os.lstat(full).st_mtime) / 3600.0
        except OSError:
            continue
        if age_hours < hours:
            continue
        size = directory_bytes(full) if os.path.isdir(full) else os.lstat(full).st_size
        doomed.append((full, size, "in /tmp for %g hour(s)" % hours))
    return doomed


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually delete; without this it only prints")
    parser.add_argument("--days", type=float, default=3.0, help="keep build outputs younger than this (default 3)")
    parser.add_argument("--hours", type=float, default=24.0, help="/tmp entries younger than this stay (default 24)")
    parser.add_argument("--keep", type=int, default=2, help="newest outputs to keep per prefix (default 2)")
    parser.add_argument("--trees", default=TREES)
    parser.add_argument("--tmp", default=TMP)
    parser.add_argument("--protect", action="append", default=[], help="extra path to leave alone (repeatable)")
    parser.add_argument("--json", action="store_true", help="machine readable summary")
    args = parser.parse_args(argv)

    extra = {os.path.abspath(p) for p in args.protect}
    extra |= {os.path.abspath(p) for p in os.environ.get("K60_KEEP", "").split() if p}
    # A /tmp symlink may point into a build tree (/tmp/k60build, /tmp/fakeroot do).
    # The link itself is skipped below, but pruning its target would break the shim
    # just as silently -- so the target is protected too. Found by a test, not by a
    # build: scripts/tests/test-disk-guards.py test_symlink_in_tmp_is_never_removed.
    if os.path.isdir(args.tmp):
        for name in os.listdir(args.tmp):
            link = os.path.join(args.tmp, name)
            if os.path.islink(link):
                extra.add(os.path.abspath(os.path.realpath(link)))

    doomed = plan_trees(args.trees, args.keep, args.days, extra)
    doomed += plan_tmp(args.tmp, args.hours, extra)

    freed = 0
    removed = []
    failed = []
    for path, size, reason in doomed:
        if not args.apply:
            removed.append({"path": path, "bytes": size, "reason": reason, "applied": False})
            freed += size
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)
        except OSError as error:
            failed.append({"path": path, "error": str(error)})
            continue
        removed.append({"path": path, "bytes": size, "reason": reason, "applied": True})
        freed += size

    summary = {
        "apply": args.apply,
        "freed_bytes": freed,
        "freed_gb": round(freed / float(1 << 30), 2),
        "removed": removed,
        "failed": failed,
    }
    if args.json:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if failed else 0

    for item in removed:
        print("%s %8.2f GB  %s\n    %s" % ("deleted" if item["applied"] else "would delete",
                                          item["bytes"] / float(1 << 30), item["path"], item["reason"]))
    for item in failed:
        print("FAILED %s: %s" % (item["path"], item["error"]))
    print("\n%s %.2f GB across %d path(s)%s" % ("freed" if args.apply else "would free",
                                                freed / float(1 << 30), len(removed),
                                                "" if args.apply else "  (dry run: pass --apply to delete)"))
    if failed:
        print("⚠️  %d path(s) could not be removed; the usual cause is a root-owned mirror "
              "inside the tree -- run this as root rather than skipping it." % len(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
