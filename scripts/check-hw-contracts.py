#!/usr/bin/env python3
"""Verify every hardware-contract row against the line it cites.

The manifest (docs/research/power/HW-CONTRACTS.toml) is the list of numbers the
four lines cannot let drift silently: GLINK owner and lease layout, the SCM
register contract, trip points, PDMEM addresses. Each row names a file and a
line, plus the text that must sit on it, so this gate fails when a constant
moves instead of leaving a document pointing at the wrong address - the shape
that made four docs wrong in one week.

usage: check-hw-contracts.py [--root DIR] [--manifest PATH]
exit 0 every row verified / 1 problems / 2 manifest unusable
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = "docs/research/power/HW-CONTRACTS.toml"
LANES = {"adsp", "battery", "charger", "thermal", "power"}
DEPENDENCE = {"none", "macro", "firmware", "property-number", "layout"}
FIELDS = ("id", "lane", "what", "source", "expect", "dependence", "ios27")


def verify(root: pathlib.Path, manifest: pathlib.Path) -> list[str]:
    problems: list[str] = []
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{manifest} is missing"]
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        return [f"{manifest} does not parse: {error}"]
    rows = data.get("contract")
    if not isinstance(rows, list) or not rows:
        return [f"{manifest} has no [[contract]] rows"]
    seen: dict[str, int] = {}
    for index, row in enumerate(rows, 1):
        label = str(row.get("id") or f"row {index}")
        for field in FIELDS:
            if not str(row.get(field) or "").strip():
                problems.append(f"{label}: {field} is empty")
        if str(row.get("lane") or "") not in LANES:
            problems.append(f"{label}: lane {row.get('lane')!r} is not one of {sorted(LANES)}")
        if str(row.get("dependence") or "") not in DEPENDENCE:
            problems.append(f"{label}: dependence {row.get('dependence')!r} is not one of {sorted(DEPENDENCE)}")
        if label in seen:
            problems.append(f"{label}: duplicate id (also row {seen[label]})")
        seen.setdefault(label, index)
        source = str(row.get("source") or "")
        if ":" not in source:
            problems.append(f"{label}: source {source!r} is not path:line")
            continue
        rel, _, number = source.rpartition(":")
        try:
            want_line = int(number)
        except ValueError:
            problems.append(f"{label}: {number!r} is not a line number")
            continue
        path = root / rel
        if not path.is_file():
            problems.append(f"{label}: {rel} does not exist")
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            problems.append(f"{label}: cannot read {rel}: {error}")
            continue
        if not 1 <= want_line <= len(lines):
            problems.append(f"{label}: {rel} has {len(lines)} lines, the row cites {want_line}")
            continue
        expect = str(row.get("expect") or "")
        if expect and expect not in lines[want_line - 1]:
            problems.append(f"{label}: {rel}:{want_line} does not contain {expect!r}")
        mirror = str(row.get("mirror") or "").strip()
        if not mirror:
            continue
        if ":" not in mirror:
            problems.append(f"{label}: mirror {mirror!r} is not path:line")
            continue
        mrel, _, mnumber = mirror.rpartition(":")
        try:
            mline = int(mnumber)
        except ValueError:
            problems.append(f"{label}: mirror line {mnumber!r} is not a number")
            continue
        mpath = root / mrel
        if not mpath.is_file():
            problems.append(f"{label}: mirror {mrel} does not exist")
            continue
        mlines = mpath.read_text(encoding="utf-8", errors="replace").splitlines()
        if not 1 <= mline <= len(mlines):
            problems.append(f"{label}: mirror {mrel} has {len(mlines)} lines, the row cites {mline}")
            continue
        if expect and expect not in mlines[mline - 1]:
            problems.append(f"{label}: mirror {mrel}:{mline} does not contain {expect!r} (the second copy drifted)")
    covered = {str(row.get("lane") or "") for row in rows}
    for lane in sorted(LANES - covered):
        problems.append(f"no row covers the {lane} line")
    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--manifest")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    manifest = pathlib.Path(args.manifest) if args.manifest else root / REL
    problems = verify(root, manifest)
    if problems:
        for problem in problems:
            print(f"❌ {problem}", file=sys.stderr)
        print(f"hw-contracts: {len(problems)} problem(s)", file=sys.stderr)
        return 2 if problems and problems[0].startswith(str(manifest)) else 1
    rows = tomllib.loads(manifest.read_text(encoding="utf-8"))["contract"]
    lanes = sorted({str(row["lane"]) for row in rows})
    print(f"✅ hw-contracts: {len(rows)} contract(s) across {len(lanes)} lane(s) match the lines they cite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
