#!/usr/bin/env python3
"""Gate for P-155: a patch's line budget for a shared file is a contract.

Every patch in ``patches/xnu/series`` that touches ``bsd/kern/kern_exec.c`` adds
and removes lines in a file that a dozen later patches also anchor into. Adding
two lines to an early patch shifts every later hunk and the build dies with
``patch does not apply`` after the compiler has already run for minutes.

The check sums the added and removed lines every patch declares for that file and
compares the total against ``expected_kern_exec_delta`` in
``docs/engineering/RULES.toml``. Any change to the sum means an early patch moved
and the series has to be re-validated - which is exactly the moment this gate
should stop the build.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERIES = REPO / "patches" / "xnu" / "series"
RULES = REPO / "docs" / "engineering" / "RULES.toml"
WATCH = "bsd/kern/kern_exec.c"

HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


def patch_delta(path: Path) -> tuple[int, int]:
    """Return (added, removed) line counts a patch declares for WATCH."""
    added = removed = 0
    in_target = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("+++ "):
            match = FILE_RE.match(line)
            in_target = bool(match and match.group(1).strip() == WATCH)
            continue
        if not in_target:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def main() -> int:
    if not SERIES.is_file():
        print("❌ patches/xnu/series 不存在")
        return 1
    total_add = total_del = 0
    touched: list[str] = []
    for entry in SERIES.read_text(encoding="utf-8").split():
        patch = REPO / "patches" / "xnu" / entry
        if not patch.is_file():
            print(f"❌ series 指向不存在的补丁：{entry}")
            return 1
        added, removed = patch_delta(patch)
        if added or removed:
            total_add += added
            total_del += removed
            touched.append(f"{entry} +{added}/-{removed}")
    delta = total_add - total_del

    expected = None
    if RULES.is_file():
        data = tomllib.loads(RULES.read_text(encoding="utf-8"))
        expected = data.get("expected_kern_exec_delta")

    print(f"  · {len(touched)} 个补丁改 {WATCH}：+{total_add}/-{total_del} → 净 {delta:+d}")
    if expected is None:
        print(f"  · RULES.toml 未记录基线；把 expected_kern_exec_delta = {delta} 写进去即开始生效")
        print("✅ kern_exec.c 行数预算检查跳过（无基线）")
        return 0
    if int(expected) != delta:
        print("❌ kern_exec.c 行数预算被改动（P-155）：")
        print(f"   基线 {int(expected):+d}，当前 {delta:+d}")
        for row in touched:
            print(f"   - {row}")
        print("   要么让早期补丁保持净行数为 0，要么确认后续补丁仍能应用后更新基线。")
        return 1
    print("✅ kern_exec.c 行数预算未变（P-155）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
