#!/usr/bin/env python3
"""Gate for P-151: a file-level upstream pick must never silently shrink a file.

`pick-upstream.py` extracts whole files from yibiya's branches because the two
histories share no ancestor. When both sides edited the same file, the pick
replaces our version wholesale - that is how a 1,052,856-byte
``0340-k60-uilib-deploy.patch`` became a 626,395-byte one and the kernel stopped
applying.

Two things are checked:
  1. the shrink guard still exists in ``pick-upstream.py`` (a pick that removes
     more than 25% of a file must warn, never pass silently);
  2. the newest commit that touched ``patches/`` or ``drivers/`` did not shrink
     any file by more than 25% against its parent.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PICKER = REPO / "scripts" / "pick-upstream.py"
LIMIT = 0.25
WATCH_DIRS = ("patches/", "drivers/")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False).stdout.strip()


def static_guard() -> list[str]:
    problems: list[str] = []
    if not PICKER.is_file():
        return [f"{PICKER.name} 不存在"]
    text = PICKER.read_text(encoding="utf-8", errors="replace")
    if "SHRINK_WARN" not in text:
        problems.append("pick-upstream.py 没有 SHRINK_WARN 阈值（P-151 保护区被删）")
    if "SHRINK_WARNINGS" not in text:
        problems.append("pick-upstream.py 没有 SHRINK_WARNINGS 记录，缩小不会被报告")
    match = re.search(r"SHRINK_WARN\s*=\s*([0-9.]+)", text)
    if match and float(match.group(1)) > LIMIT:
        problems.append(
            f"pick-upstream.py 的 SHRINK_WARN={match.group(1)} 高于 {LIMIT}，缩小 25% 不会告警")
    return problems


def last_pick_shrink() -> list[str]:
    sha = git("log", "-1", "--format=%H", "--", "patches", "drivers")
    if not sha:
        return []
    numstat = git("show", "--numstat", "--format=", sha)
    problems: list[str] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[2] == "Binary files differ":
            continue
        added, removed, path = parts
        if not str(path).startswith(WATCH_DIRS):
            continue
        if not added.isdigit() or not removed.isdigit():
            continue
        old_size = int(git("cat-file", "-s", f"{sha}^:{path}") or 0)
        new_size = int(git("cat-file", "-s", f"{sha}:{path}") or 0)
        if old_size and new_size and new_size < old_size * (1 - LIMIT):
            problems.append(
                f"{sha[:8]} 让 {path} 从 {old_size} B 缩到 {new_size} B "
                f"（-{100 * (1 - new_size / old_size):.0f}%），检查是否覆盖了本地改动")
    return problems


def main() -> int:
    problems = static_guard() + last_pick_shrink()
    if problems:
        print("❌ pick 缩小保护检查未通过（P-151）：")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print("✅ pick 缩小保护有效，最近一次 pick 没有整文件覆盖（P-151）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
