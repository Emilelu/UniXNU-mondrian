
#!/usr/bin/env python3
"""Fail when the criteria table cites a line that is not where the driver prints it.

`docs/research/charger/07-DEVICE-CRITERIA.md` opens with a 判据总表 whose 证据行 column
names `file:line` for each criterion. Those are the lines a person opens when a judgement
goes wrong, and they are the part of the doc that rots fastest: on 2026-11-20 the C1 and C2
rows still pointed at `K60Battery.cpp:209-214` (a raw-number publish block) while the sample
line the judge reads had moved to `:290` and the channel-up line to `:442`.

So the citations are checked against the emitters the console-contract gate already pairs up:
the anchor string is the authoritative copy of "this is the line", and the doc must cite the
line that really carries it. A stale citation is refused with both numbers.

Exit 0 the table agrees, 1 a citation is stale or missing, 2 a file cannot be read.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = "docs/research/charger/07-DEVICE-CRITERIA.md"
CONTRACT = "scripts/check-console-contract.py"
# criterion -> the pairs whose anchor line the citation has to point at
CRITERIA = {
    "C1": ("battery-channel-up", "battery-sample"),
    "C2": ("battery-sample",),
}
CITE_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:c|cpp|h|mm)):([0-9]+)(?:-([0-9]+))?`")


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("ccc_" + path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def anchor_line(root: pathlib.Path, contract, pair_id: str):
    """(relative path, 1-based line) of the line that carries the pair's anchor."""
    pair = next((p for p in contract.PAIRS if p[0] == pair_id), None)
    if pair is None:
        return None, None, f"pair {pair_id!r} is no longer in {CONTRACT}"
    rel, anchor = pair[1], pair[4]
    path = root / rel
    if not path.is_file():
        return None, None, f"{rel} is missing"
    text = path.read_text(encoding="utf-8")
    index = text.find(anchor)
    if index < 0:
        return None, None, f"{rel} does not carry {anchor!r}"
    return rel, text.count("\n", 0, index) + 1, None


def table_rows(text: str) -> dict[str, str]:
    """The 判据总表 rows: criterion -> its 证据行 cell. Stops at the first blank line after it."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"C[0-9]+", cells[0]):
            rows[cells[0]] = cells[2]
    return rows


def verify(root: pathlib.Path = ROOT) -> list[str]:
    problems: list[str] = []
    contract_path = root / CONTRACT
    doc_path = root / DOC
    if not contract_path.is_file():
        return [f"{CONTRACT} is missing"]
    if not doc_path.is_file():
        return [f"{DOC} is missing"]
    contract = load(contract_path)
    rows = table_rows(doc_path.read_text(encoding="utf-8"))
    if not rows:
        return [f"{DOC} has no 判据总表 row (a table nobody can parse is a table nobody checks)"]
    for criterion, pairs in CRITERIA.items():
        cell = rows.get(criterion)
        if cell is None:
            problems.append(f"{DOC}: no row for {criterion}")
            continue
        cites = CITE_RE.findall(cell)
        if not cites:
            problems.append(f"{DOC}: {criterion} cites no file:line, so a reader cannot open its evidence")
            continue
        expected: dict[str, set[int]] = {}
        for pair_id in pairs:
            rel, line, error = anchor_line(root, contract, pair_id)
            if error:
                problems.append(f"{criterion}: {error}")
                continue
            expected.setdefault(rel, set()).add(line)
        for name, start, end in cites:
            rel = f"drivers/PongPower/{name}" if "/" not in name else name
            if rel not in expected:
                continue  # cites another file (the judge, a header); only the printers are policed
            first = int(start)
            last = int(end) if end else first
            if expected[rel] & set(range(first, last + 1)):
                continue
            wanted = ", ".join(str(n) for n in sorted(expected[rel]))
            if last > first:
                problems.append(f"{DOC}: {criterion} cites {name}:{first}-{last}, but the line the "
                                f"driver prints that evidence on is {wanted}")
            else:
                problems.append(f"{DOC}: {criterion} cites {name}:{first}, but the line the driver "
                                f"prints that evidence on is {wanted}")
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        print(f"criteria-cites: {args.root} is not a directory", file=sys.stderr)
        return 2
    problems = verify(root)
    if problems:
        for problem in problems:
            print(f"❌ {problem}")
        print(f"criteria-cites: {len(problems)} problem(s)")
        return 1
    print(f"✅ criteria-cites: {len(CRITERIA)} criterion(s) cite the line the driver prints them on")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
