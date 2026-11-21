#!/usr/bin/env python3
"""Every hardware line in the 27 ledger must have an architecture decision.

The 16.6.1 port grew out of the pong lineage.  For 27 that is the wrong trunk:
the user's rule is "official sheng and the official docs by default; a same-SoC
reference only where the hardware itself cannot be copied".  A rule like that
only holds if it is checked, so this gate ties the two places the decision lives:

  docs/engineering/IOS27-DRIVER-ARCH.md      the matrix, one row per layer
  docs/research/eight-step/*-27.toml         the ledger, one block per hardware item

A row is acceptable when it states which rule it follows (1/2/3), what we do,
and a citation.  "待定" and "待判" are refused: an undecided row is exactly the
state this gate exists to make visible.

Exit codes: 0 every item decided, 1 problems found, 2 cannot judge (missing
input, which is not the same as passing -- P-279).
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
MATRIX = HERE / "docs/engineering/IOS27-DRIVER-ARCH.md"
FRAGMENTS = HERE / "docs/research/eight-step"

# Which matrix layer answers for which ledger item.  Keyed by the item name used
# in docs/research/eight-step/*-27.toml.
ITEM_LAYERS = {
    "audio": "音频",
    "battery": "电源",
    "charger": "电源",
    "thermal": "电源",
    "bluetooth": "蓝牙",
    "wifi": "WiFi",
    "cellular": "蜂窝",
    "touch": "输入",
    "buttons": "输入",
    "display": "显示",
    "gpu": "GPU",
    "ufs": "存储",
    "usb": "USB",
    "platform": "CPU",
}

RULES = {"1", "2", "3"}
UNDECIDED = ("待定", "待判", "tbd", "TBD")
CITATION = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+:\d+")
NO_UPSTREAM = ("上游无实现", "官方无")


def cells(line: str) -> list[str]:
    """Split a markdown table row into its cells."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def matrix_rows(text: str) -> list[dict[str, str]]:
    """Rows of the first table whose header names 层 and 决定."""
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            if header and rows:
                break
            header = None
            continue
        parts = cells(line)
        if header is None:
            if any("层" in cell for cell in parts) and any("决定" in cell for cell in parts):
                header = parts
            continue
        if all(set(cell) <= set("-: ") for cell in parts if cell):
            continue
        if len(parts) != len(header):
            continue
        rows.append(dict(zip(header, parts)))
    return rows


def hardware_items(root: Path) -> dict[str, list[str]]:
    """Item name -> the fragment files that declare it."""
    found: dict[str, list[str]] = {}
    for path in sorted(root.glob("*-27.toml")):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
            continue
        for name in (data.get("hardware") or {}):
            found.setdefault(name, []).append(path.name)
    return found


def check(matrix: str, items: dict[str, list[str]]) -> list[str]:
    problems: list[str] = []
    rows = matrix_rows(matrix)
    if not rows:
        return ["the matrix has no table with 层/决定 columns; nothing can be judged"]
    by_layer: dict[str, dict[str, str]] = {}
    for row in rows:
        layer = row.get("层", "")
        if layer:
            by_layer[layer] = row
    for item, files in sorted(items.items()):
        layer = ITEM_LAYERS.get(item)
        if layer is None:
            problems.append(
                f"{item}: no matrix layer is mapped to this ledger item ({', '.join(files)}); "
                "add it to ITEM_LAYERS and to the matrix, or the decision is unwritten"
            )
            continue
        row = by_layer.get(layer)
        if row is None:
            problems.append(f"{item}: the matrix has no row for layer {layer!r}")
            continue
        rule = row.get("规则", "")
        code = re.match(r"\s*(\d)", rule)
        if not code or code.group(1) not in RULES:
            problems.append(f"{item}: row {layer!r} does not state rule 1, 2 or 3 (has {rule!r})")
        decision = row.get("决定", "")
        if not decision:
            problems.append(f"{item}: row {layer!r} has no decision")
        elif any(word in decision for word in UNDECIDED):
            problems.append(
                f"{item}: row {layer!r} is undecided ({decision[:40]!r}); "
                "an undecided row is the state this gate exists to surface"
            )
        citation = row.get("依据", "")
        if not citation:
            problems.append(f"{item}: row {layer!r} cites nothing")
        elif not CITATION.search(citation) and not any(word in citation for word in NO_UPSTREAM):
            problems.append(
                f"{item}: row {layer!r} cites no file:line and does not say the upstream has none "
                f"(has {citation[:60]!r})"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument("--fragments", type=Path, default=FRAGMENTS)
    arguments = parser.parse_args(argv)
    if not arguments.matrix.is_file():
        print(f"GATE UNKNOWN: no matrix at {arguments.matrix} (P-279: cannot judge is not a pass)")
        return 2
    if not arguments.fragments.is_dir():
        print(f"GATE UNKNOWN: no fragment directory at {arguments.fragments}")
        return 2
    items = hardware_items(arguments.fragments)
    if not items:
        print(f"GATE UNKNOWN: {arguments.fragments} has no *-27.toml hardware blocks")
        return 2
    problems = check(arguments.matrix.read_text(encoding="utf-8"), items)
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        print(f"FAIL driver-arch: {len(problems)} undecided or uncited ledger item(s)")
        return 1
    print(
        f"OK driver-arch: {len(items)} hardware item(s) across {len(set(sum(items.values(), [])))} "
        "fragment file(s) have a rule, a decision and a citation"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
