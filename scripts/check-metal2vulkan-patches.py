#!/usr/bin/env python3
"""Every patch we keep must either be applied by a build script or declared unused.

Why: patches/metal2vulkan/ holds 19 patches taken from data-a-live, several of which
change the per-draw allocation behaviour (0013) and draw command retention (0015,
0016).  scripts/build-pong-metal-bridge.py applies only 0008 and 0009.  A patch that
nobody applies is a silent no-op: the file sits in the tree looking like a fix while
the binary is built without it, which is the same shape as P-183 (asset nobody uses)
and P-221 (receipt nobody reads).

The gate fails when a patch is neither named by a build script nor listed in the
"unused" section of patches/metal2vulkan/DATA-A-LIVE.md, so dropping one from a build
is a visible decision rather than an accident.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
PATCH_DIR = ROOT / "patches" / "metal2vulkan"
NOTES = PATCH_DIR / "DATA-A-LIVE.md"
SCRIPTS = ("scripts",)
UNUSED_HEADING = re.compile(r"^#+\s*.*未启用|^#+\s*.*not applied|^#+\s*.*unused", re.IGNORECASE)
NAME = re.compile(r"^([0-9]{4}-[A-Za-z0-9._-]+\.patch)$")


def patch_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(entry.name for entry in directory.iterdir() if entry.is_file() and entry.suffix == ".patch")


def applied_names(root: Path, names: list[str]) -> set[str]:
    """Patch file names that any build script mentions."""
    found: set[str] = set()
    for folder in SCRIPTS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".sh"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in names:
                if name in text:
                    found.add(name)
    return found


def declared_unused(notes: Path, names: list[str]) -> set[str]:
    """Patch names listed under an "unused"/"未启用" heading in the notes file."""
    if not notes.is_file():
        return set()
    declared: set[str] = set()
    inside = False
    for line in notes.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            inside = bool(UNUSED_HEADING.search(line))
            continue
        if inside:
            for name in names:
                if name in line:
                    declared.add(name)
    return declared


def check(root: Path = ROOT) -> tuple[list[str], int]:
    directory = root / "patches" / "metal2vulkan"
    names = patch_names(directory)
    if not names:
        return [f"没有找到任何 metal2vulkan 补丁：{directory}"], 0
    used = applied_names(root, names)
    unused = declared_unused(directory / "DATA-A-LIVE.md", names)
    problems = [
        f"{name} 既没有被任何构建脚本应用，也没有在 DATA-A-LIVE.md 的「未启用」小节里声明"
        for name in names
        if name not in used and name not in unused
    ]
    return problems, len(names)


def main() -> int:
    problems, total = check()
    for problem in problems:
        print(f"❌ {problem}")
    if problems:
        print(f"FAIL {len(problems)} of {total} metal2vulkan patches are unaccounted for")
        return 1
    print(f"✅ {total} metal2vulkan 补丁全部有归属（已应用或已声明未启用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
