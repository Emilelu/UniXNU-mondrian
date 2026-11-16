#!/usr/bin/env python3
"""P-226: the critical blocks in build-strict.sh must be asserted, not remembered.

A merge only prints a conflict for lines that actually overlap.  When the other
side carries an older copy of a file, a whole non-overlapping region can be
replaced without a single marker.  On 2026-11-16 that is how three
build-correctness blocks disappeared at once from scripts/build-strict.sh:

  * the __pycache__ prune in freeze()   -> the build voids itself at the end
  * board_dir()                         -> a wifi-only cell finds no .config
  * the P-202 hint in the die message   -> the message points at the wrong defconfig

None of them broke the build: it ran to completion and reported success.  That
is why "did git print a conflict?" is the wrong question and this gate is the
right one -- it asserts the blocks are present, so losing one is a red gate
instead of a mystery.

Usage:
    python3 scripts/check-build-strict-blocks.py            # check this repo
    K60_REPO=/path python3 scripts/check-build-strict-blocks.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
BUILD_STRICT = REPO / "scripts" / "build-strict.sh"


def body_of(text: str, header: str) -> str:
    """Return the shell text of a function, header included, or '' when absent."""
    lines = text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.startswith(header):
            start = index
            break
    if start is None:
        return ""
    depth = 0
    for index in range(start, len(lines)):
        depth += lines[index].count("{") - lines[index].count("}")
        if depth == 0:
            return "\n".join(lines[start:index + 1])
    return ""


def check(text: str) -> list[str]:
    """Return a list of problems; an empty list means every block is present."""
    problems: list[str] = []

    board = body_of(text, "board_dir() {")
    if not board:
        problems.append("board_dir() is missing (P-225): the board directory would be hardcoded again")
    else:
        for key in ("CONFIG_XNU_GPU_ADDON", "CONFIG_XNU_K60_PHYSICAL_BATTERY"):
            if key not in board:
                problems.append(
                    "board_dir() no longer ranks candidates by %s (P-225): a .config that "
                    "does not name the key would win on age alone" % key)
        if "K60_BOARD_DIR" not in board:
            problems.append("board_dir() ignores K60_BOARD_DIR (P-225): the override must win")
        elif not re.search(r'K60_BOARD_DIR[^\n]*\n[^\n]*die', board):
            problems.append(
                "board_dir() does not die when K60_BOARD_DIR has no .config (P-225): "
                "silently ignoring the override is the P-190 shape")

    freeze = body_of(text, "freeze() {")
    if not freeze:
        problems.append("freeze() is missing: nothing would guard the frozen inputs")
    elif "__pycache__" not in freeze and "*.pyc" not in freeze:
        problems.append(
            "freeze() has no bytecode prune (P-224): the build imports these scripts, python "
            "rewrites the .pyc files, and the run voids itself at the final comparison")

    if not re.search(r'\[ -f "\$M/\.config" \] \|\| die', text):
        problems.append(
            "the P-202 guard on $M/.config is missing: sed on a missing file yields nothing and "
            "the build would silently drop the Metal plugin and the battery archive")

    for marker in ("# --- gate-table:BEGIN ---", "# --- gate-table:END ---"):
        if marker not in text:
            problems.append("the gate-table marker %r is missing (P-205)" % marker)

    # The wifi archive is a wifi-line block, so its presence is conditional; when
    # it is present the kernel-side proof must be too, or the link can drop it in
    # silence (P-190).
    if "WIFI_ARCHIVE" in text and "_pong_wifi_start_optional" not in text:
        problems.append(
            "the wifi archive is selected but never verified in the kernel (P-190): "
            "add the _pong_wifi_start_optional assertion after the kernel is built")

    return problems


def main() -> int:
    if not BUILD_STRICT.is_file():
        print("skip: %s does not exist" % BUILD_STRICT)
        return 0
    problems = check(BUILD_STRICT.read_text(encoding="utf-8"))
    if problems:
        for problem in problems:
            print("FAIL %s" % problem)
        print("结论: \u274c build-strict.sh lost %d critical block(s) (P-226)" % len(problems))
        return 1
    print("\u2705 build-strict.sh: every P-226 critical block is present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
