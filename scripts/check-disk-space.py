#!/usr/bin/env python3
"""Refuse to keep working on a host that is about to run out of disk.

The user should not have to notice this: three times now the machine filled up
mid-build (WSL root at 166 GiB used, E: at 113 GiB used, a 24 GiB scratch copy
nobody referenced) and the cleanup only started after they asked.  A rule that
is not checked is not a rule, so this runs in the same gate list as everything
else.

Two independent signals:

  1. free space on each filesystem the build actually writes to;
  2. the WSL virtual disk file versus the data inside it -- a vhdx that is much
     larger than its filesystem means deleted files were never returned to
     Windows, which is the failure mode that keeps coming back.

Exit status: 1 on any blocking condition, 0 otherwise (warnings do not block).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

GIB = 1024 ** 3

# mount, label, block below this many GiB free, warn below this many GiB free
FILESYSTEMS = (
    ("/mnt/e", "E:", 8.0, 25.0),
    ("/mnt/d", "D:", 10.0, 30.0),
    ("/", "WSL root", 12.0, 30.0),
)

# The one virtual disk this workspace uses; absence is not an error.
WSL_VHDX = "/mnt/d/Android/wsl/Ubuntu-24.04/ext4.vhdx"

# How much bigger than its contents the vhdx may be before it is worth
# compacting.  Trim plus a sparse file keeps this small; a non-sparse file that
# was never compacted drifts by tens of GiB.
VHDX_SLACK_GIB = 30.0


def assess(free_bytes: int, block_gib: float, warn_gib: float) -> tuple[str, str]:
    """Grade one filesystem. Returns ("ok"|"warn"|"fail", human reason)."""
    free_gib = free_bytes / GIB
    if free_gib <= block_gib:
        return "fail", f"{free_gib:.1f} GiB free, below the {block_gib:.0f} GiB floor"
    if free_gib < warn_gib:
        return "warn", f"{free_gib:.1f} GiB free, below the {warn_gib:.0f} GiB comfort line"
    return "ok", f"{free_gib:.1f} GiB free"


def vhdx_slack(vhdx_bytes: int, used_bytes: int, limit_gib: float) -> tuple[str, str]:
    """Grade a virtual disk against the data it holds.

    A sparse or freshly compacted disk sits close to its contents; anything
    more than ``limit_gib`` above them is space Windows cannot use.
    """
    slack_gib = (vhdx_bytes - used_bytes) / GIB
    if slack_gib > limit_gib:
        return (
            "warn",
            f"vhdx is {vhdx_bytes / GIB:.1f} GiB for {used_bytes / GIB:.1f} GiB of data "
            f"({slack_gib:.1f} GiB stranded); fstrim then compact it "
            f"(docs/engineering/DISK-HYGIENE.md)",
        )
    return "ok", f"vhdx {vhdx_bytes / GIB:.1f} GiB for {used_bytes / GIB:.1f} GiB of data"


def check_filesystems() -> tuple[list[tuple[str, str, str]], int]:
    rows: list[tuple[str, str, str]] = []
    failures = 0
    for mount, label, block_gib, warn_gib in FILESYSTEMS:
        if not os.path.isdir(mount):
            rows.append((label, "warn", f"{mount} is not mounted; skipped"))
            continue
        try:
            usage = shutil.disk_usage(mount)
        except OSError as error:
            rows.append((label, "warn", f"{mount} cannot be measured: {error}"))
            continue
        status, reason = assess(usage.free, block_gib, warn_gib)
        rows.append((label, status, reason))
        if status == "fail":
            failures += 1
    return rows, failures


def check_vhdx() -> tuple[list[tuple[str, str, str]], int]:
    rows: list[tuple[str, str, str]] = []
    if not os.path.exists(WSL_VHDX):
        rows.append(("WSL vhdx", "warn", f"{WSL_VHDX} does not exist; skipped"))
        return rows, 0
    try:
        size = os.path.getsize(WSL_VHDX)
        used = shutil.disk_usage("/").used
    except OSError as error:
        rows.append(("WSL vhdx", "warn", f"cannot be measured: {error}"))
        return rows, 0
    status, reason = vhdx_slack(size, used, VHDX_SLACK_GIB)
    rows.append(("WSL vhdx", status, reason))
    return rows, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vhdx-only",
        action="store_true",
        help="only grade the WSL virtual disk, not the filesystems",
    )
    args = parser.parse_args()

    rows, failures = [] if args.vhdx_only else check_filesystems()
    vhdx_rows, _ = check_vhdx()
    rows = list(rows) + vhdx_rows

    print("=" * 74)
    print("空间门禁（磁盘余量 + WSL 虚拟盘回收）")
    for label, status, reason in rows:
        mark = {"ok": "PASS", "warn": "WARN", "fail": "FAIL"}[status]
        print(f"    {mark}  {label:<12} {reason}")
    print("=" * 74)
    if failures:
        print(f"❌ {failures} 项阻断 —— 先腾空间再继续（见 docs/engineering/DISK-HYGIENE.md）")
        return 1
    print("✅ 空间充足")
    return 0


if __name__ == "__main__":
    sys.exit(main())
