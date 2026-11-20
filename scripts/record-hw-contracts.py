#!/usr/bin/env python3
"""Re-record copy27 line numbers for an overlaid 27 tree.

The committed HW-CONTRACTS.toml names the untouched 27 checkout. Once the
power-carry bundle is copied over an export, every patch/file line can move,
so --against reports disagreements that are not regressions. This tool writes
a COPY of the manifest with copy27 re-pointed at the overlaid tree; it never
edits the committed manifest. Only rows whose expect text is found exactly once
(or at the row's own source line) are changed. Ambiguous rows are refused.

Usage:
    python3 scripts/record-hw-contracts.py TREE --out build/HW-CONTRACTS-overlay.toml
    python3 scripts/check-hw-contracts.py --manifest build/HW-CONTRACTS-overlay.toml --against TREE
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/research/power/HW-CONTRACTS.toml"
OUT = ROOT / "build/HW-CONTRACTS-overlay.toml"


def row_of(block: str) -> dict | None:
    try:
        return tomllib.loads(block)["contract"][0]
    except (tomllib.TOMLDecodeError, KeyError, IndexError):
        return None


def rel_and_hints(row: dict) -> tuple[str | None, list[int]]:
    source = str(row.get("source") or "")
    copy = str(row.get("copy27") or "")
    verdict = str(row.get("same27") or "")
    if verdict in ("same", "drift") and ":" in copy:
        rel, _, number = copy.rpartition(":")
        hints: list[int] = []
        try:
            hints.append(int(number))
        except ValueError:
            pass
        if ":" in source and not source.startswith("external:"):
            source_rel, _, source_number = source.rpartition(":")
            if source_rel == rel:
                try:
                    hints.insert(0, int(source_number))
                except ValueError:
                    pass
        return rel, hints
    if ":" in source and not source.startswith("external:"):
        rel, _, number = source.rpartition(":")
        try:
            return rel, [int(number)]
        except ValueError:
            return rel, []
    return None, []


def find_line(tree: pathlib.Path, rel: str, expect: str, hints: list[int]) -> tuple[int | None, list[int]]:
    path = tree / rel
    if not path.is_file():
        return None, []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, []
    for hint in hints:
        if 1 <= hint <= len(lines) and expect in lines[hint - 1]:
            return hint, []
    hits = [index + 1 for index, text in enumerate(lines) if expect in text]
    if len(hits) == 1:
        return hits[0], hits
    return None, hits


def rewrite(block: str, copy: str) -> str:
    lines = block.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("same27"):
            out.append('same27 = "same"')
            continue
        if stripped.startswith("copy27"):
            if not inserted:
                out.append(f'copy27 = "{copy}"')
                inserted = True
            continue
        if stripped.startswith("why27") and not stripped.startswith('why27 = """'):
            continue
        out.append(line)
    if not inserted:
        expanded: list[str] = []
        for line in out:
            expanded.append(line)
            if line.strip().startswith("same27") and not inserted:
                expanded.append(f'copy27 = "{copy}"')
                inserted = True
        out = expanded
    return chr(10).join(out) + chr(10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tree", help="the overlaid 27 export to read")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    tree = pathlib.Path(args.tree).resolve()
    manifest = pathlib.Path(args.manifest).resolve()
    out = pathlib.Path(args.out).resolve()
    if not tree.is_dir():
        print(f"❌ {tree} is not a directory", file=sys.stderr)
        return 2
    if out == manifest:
        print("❌ refusing to overwrite the committed manifest; the overlay record is a copy", file=sys.stderr)
        return 2
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError as error:
        print(f"❌ {manifest}: {error}", file=sys.stderr)
        return 2

    parts = text.split("[[contract]]")
    header = parts[0]
    blocks: list[str] = []
    changed: list[tuple[str, str, str]] = []
    kept: list[str] = []
    ambiguous: list[tuple[str, list[int]]] = []
    for chunk in parts[1:]:
        block = "[[contract]]" + chunk
        row = row_of(block)
        if row is None:
            blocks.append(block)
            continue
        label = str(row.get("id") or "row")
        expect = str(row.get("expect") or "")
        rel, hints = rel_and_hints(row)
        if not expect or not rel:
            blocks.append(block)
            kept.append(label)
            continue
        line, hits = find_line(tree, rel, expect, hints)
        if line is None:
            blocks.append(block)
            if len(hits) > 1:
                ambiguous.append((label, hits))
            else:
                kept.append(label)
            continue
        copy = f"{rel}:{line}"
        old = str(row.get("same27") or "")
        if old == "same" and str(row.get("copy27") or "") == copy:
            blocks.append(block)
            kept.append(label)
            continue
        blocks.append(rewrite(block, copy))
        changed.append((label, old, copy))

    if ambiguous:
        for label, hits in ambiguous:
            print(f"❌ {label}: {len(hits)} lines carry this text ({hits[:6]}); refusing to guess",
                  file=sys.stderr)
        print("record-hw-contracts: nothing written because at least one row is ambiguous", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "".join(blocks), encoding="utf-8", newline=chr(10))
    for label, old, copy in changed:
        print(f"recorded {label}: {old or 'unchecked'} -> same at {copy}")
    print(f"record-hw-contracts: {len(changed)} re-recorded, {len(kept)} kept; wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
