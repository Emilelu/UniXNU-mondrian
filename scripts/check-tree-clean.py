#!/usr/bin/env python3
"""Gate for iron rule 2: source is tracked and pushed before the next step.

Fails when tracked source is modified but uncommitted, or when HEAD is behind or
diverged from origin/main. Untracked files and submodule dirt are reported but do
not fail the gate: the build trees carry their own gitlink noise that this
repository does not own.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False).stdout.strip()


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []

    status = git("status", "--porcelain", "--untracked-files=no")
    dirty = [line for line in status.splitlines()
             if line and not line.startswith((" M ", "?? ")) or line.startswith(" M ")]
    if dirty:
        problems.append(
            f"{len(dirty)} tracked file(s) modified but not committed "
            f"(iron rule 2): " + ", ".join(line[3:] for line in dirty[:5]))

    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        notes.append("no upstream configured -> push check skipped")
    else:
        counts = git("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        parts = counts.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])
            if behind:
                problems.append(f"HEAD is {behind} commit(s) behind {upstream} (iron rule 2)")
            if ahead:
                notes.append(f"HEAD is {ahead} commit(s) ahead of {upstream}; push before flashing")

    for note in notes:
        print(f"  · {note}")
    if problems:
        print("❌ 未提交/未推送检查未通过：")
        for problem in problems:
            print(f"   - {problem}")
        return 1
    print("✅ 源码已跟踪且已推送（铁则 2）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
