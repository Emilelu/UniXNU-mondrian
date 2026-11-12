#!/usr/bin/env python3
"""Gate for iron rule 1: nothing durable lives in /tmp.

The rule exists because a 2026-11-07 cleanup wiped /tmp/usb-cdc-mainline and took
a day of kernel patches with it.

A /tmp reference is only acceptable when it is written down. Accepted references
live in ``docs/engineering/TMP-ALLOWLIST.toml`` with a reason and an owner; every
one of them is debt, printed in the report. Anything else - a new patch, a new
script, a new config that points at /tmp - fails the gate.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOWLIST = REPO / "docs" / "engineering" / "TMP-ALLOWLIST.toml"
SCAN_DIRS = ("patches", "configs", "dts", "drivers", "scripts")
SKIP_SUFFIX = {".png", ".jpg", ".bin", ".a", ".o", ".macho", ".dbr", ".img", ".zip"}
TMP_RE = re.compile(r"/tmp/[A-Za-z0-9._/+-]+")


def load_allowlist() -> dict[str, str]:
    if not ALLOWLIST.is_file():
        return {}
    data = tomllib.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return {entry["path"]: entry.get("reason", "") for entry in data.get("allow", [])}


def iter_files() -> list[Path]:
    out: list[Path] = []
    for name in SCAN_DIRS:
        root = REPO / name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix not in SKIP_SUFFIX and ".git" not in path.parts:
                out.append(path)
    return out


def main() -> int:
    allow = load_allowlist()
    problems: list[str] = []
    seen: set[str] = set()
    for path in iter_files():
        rel = str(path.relative_to(REPO)).replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in TMP_RE.finditer(line):
                target = match.group(0)
                key = f"{rel}::{target}"
                seen.add(key)
                if key in allow:
                    continue
                problems.append(f"{rel}:{lineno} uses {target} and is not in TMP-ALLOWLIST.toml")
    stale = sorted(set(allow) - seen)
    if stale:
        print(f"  · 白名单里有 {len(stale)} 条已不存在，可以删掉：{', '.join(stale[:3])}…")
    if allow:
        print(f"  · 白名单尚有 {len(allow)} 条 /tmp 债务")
    if problems:
        print("❌ /tmp 依赖检查未通过（铁则 1）：")
        for problem in problems[:20]:
            print(f"   - {problem}")
        if len(problems) > 20:
            print(f"   … 还有 {len(problems) - 20} 处")
        print("   要么改成持久路径，要么写进 docs/engineering/TMP-ALLOWLIST.toml 并说明原因。")
        return 1
    print("✅ 没有未登记的 /tmp 依赖（铁则 1）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
