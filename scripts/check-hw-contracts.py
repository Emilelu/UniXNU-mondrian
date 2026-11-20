#!/usr/bin/env python3
"""Verify every hardware-contract row against the line it cites.

The manifest (docs/research/power/HW-CONTRACTS.toml) is the list of numbers the
four lines cannot let drift silently: GLINK owner and lease layout, the SCM
register contract, trip points, PDMEM addresses. Each row names a file and a
line, plus the text that must sit on it, so this gate fails when a constant
moves instead of leaving a document pointing at the wrong address - the shape
that made four docs wrong in one week.

A `dependence = "firmware"` row is a number the DSP, the boot chain or the
vendor Linux also knows: a citation of our own source proves nothing about the
other side, so such a row must carry an INDEPENDENT source as well -
`second = [...]`, a firmware image offset or a line in another implementation of
the same protocol - and a row that has none must say so with
`second_unavailable = { tried = [...], why = "..." }`, where `tried` names the
sources that were actually searched and `why` names what would settle it. The
words "cannot be verified" alone are not a reason (Lead, 2026-11-20).

usage: check-hw-contracts.py [--root DIR] [--manifest PATH]
exit 0 every row verified / 1 problems / 2 manifest unusable
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = "docs/research/power/HW-CONTRACTS.toml"
LANES = {"adsp", "battery", "charger", "thermal", "power"}
DEPENDENCE = {"none", "macro", "firmware", "property-number", "layout"}
FIELDS = ("id", "lane", "what", "source", "expect", "dependence", "ios27")
DRIVE = re.compile(r"^([A-Za-z]):[\\/]")


def hostpath(text: str) -> pathlib.Path:
    """Translate a Windows-style path for whichever host runs the gate (P-259).

    The table is written once and read on Windows and under WSL; a path that only
    resolves on one of them would make the gate green on one host and red on the
    other, which is the defect PROP-NUMBERS hit on its first version.
    """
    if os.name == "nt":
        return pathlib.Path(text)
    match = DRIVE.match(text)
    if not match:
        return pathlib.Path(text)
    rest = text[2:].replace("\\", "/").lstrip("/")
    return pathlib.Path("/mnt") / match.group(1).lower() / rest


def cited(root: pathlib.Path, roots: dict, text: str) -> tuple[pathlib.Path | None, str]:
    """Resolve a citation; `external:<root>/<path>` names a tree outside the repo."""
    text = text.strip()
    if not text.startswith("external:"):
        return root / text, ""
    name, _, tail = text[len("external:"):].partition("/")
    if name not in roots:
        return None, f"external root {name!r} is not declared under [roots] (have {sorted(roots)})"
    return hostpath(str(roots[name])) / tail, ""


def second_problems(label: str, row: dict, root: pathlib.Path, roots: dict) -> list[str]:
    """Check the independent sources of one row and the firmware-row obligation."""
    problems: list[str] = []
    entries = row.get("second")
    unavailable = row.get("second_unavailable")
    if entries is not None and not isinstance(entries, list):
        problems.append(f"{label}: second is not an array of tables")
        entries = None
    if unavailable is not None and not isinstance(unavailable, dict):
        problems.append(f"{label}: second_unavailable is not a table")
        unavailable = None
    if entries and unavailable:
        problems.append(f"{label}: second and second_unavailable are mutually exclusive")
    if str(row.get("dependence")) == "firmware" and not entries and not unavailable:
        problems.append(
            f"{label}: firmware row has no independent second source and does not say why "
            "(second = [...] or second_unavailable = { tried, why })")
    for entry in entries or []:
        if not isinstance(entry, dict):
            problems.append(f"{label}: a second-source entry is not a table")
            continue
        if "bytes" in entry:
            problems += bytes_problems(label, entry, root, roots)
            continue
        source = str(entry.get("source") or "")
        expect = str(entry.get("expect") or "")
        if not source or ":" not in source:
            problems.append(f"{label}: second source {source!r} is not path:line")
            continue
        rel, _, number = source.rpartition(":")
        try:
            want = int(number)
        except ValueError:
            problems.append(f"{label}: second source line {number!r} is not a number")
            continue
        path, error = cited(root, roots, rel)
        if error:
            problems.append(f"{label}: {error}")
            continue
        if path is None or not path.is_file():
            problems.append(f"{label}: second source {rel} does not exist")
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            problems.append(f"{label}: cannot read second source {rel}: {error}")
            continue
        if not 1 <= want <= len(lines):
            problems.append(f"{label}: second source {rel} has {len(lines)} lines, the row cites {want}")
            continue
        if expect and expect not in lines[want - 1]:
            problems.append(f"{label}: second source {rel}:{want} does not contain {expect!r}")
    if unavailable is not None:
        tried = unavailable.get("tried") or []
        why = str(unavailable.get("why") or "")
        if not isinstance(tried, list) or len(tried) < 2:
            problems.append(
                f"{label}: second_unavailable lists {len(tried) if isinstance(tried, list) else 0} "
                "tried source(s); at least two are required so the reason is checkable")
        if not why.strip():
            problems.append(f"{label}: second_unavailable has no why (name the artefact that would settle it)")
    return problems


def bytes_problems(label: str, entry: dict, root: pathlib.Path, roots: dict) -> list[str]:
    """A second source may be a byte range inside a binary the repo does not carry."""
    rel = str(entry.get("bytes") or "")
    try:
        offset = int(entry.get("offset"))
    except (TypeError, ValueError):
        return [f"{label}: second source {rel} has no integer offset"]
    want_hex = str(entry.get("hex") or "").replace(" ", "").lower()
    if not want_hex or len(want_hex) % 2:
        return [f"{label}: second source {rel} has no whole-byte hex"]
    path, error = cited(root, roots, rel)
    if error:
        return [f"{label}: {error}"]
    if path is None or not path.is_file():
        return [f"{label}: second source {rel} does not exist"]
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(offset, 0))
            actual = handle.read(len(want_hex) // 2).hex()
    except OSError as error:
        return [f"{label}: cannot read second source {rel}: {error}"]
    if offset < 0 or offset + len(want_hex) // 2 > size:
        return [f"{label}: second source {rel} is {size} B, offset {offset} + {len(want_hex) // 2} does not fit"]
    if actual != want_hex:
        return [f"{label}: second source {rel} at offset {offset:#x} reads {actual or 'nothing'}, the row records {want_hex}"]
    return []


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
    roots = data.get("roots") or {}
    if not isinstance(roots, dict):
        return [f"{manifest}: [roots] is not a table"]
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
        if mirror:
            if ":" not in mirror:
                problems.append(f"{label}: mirror {mirror!r} is not path:line")
            else:
                mrel, _, mnumber = mirror.rpartition(":")
                try:
                    mline = int(mnumber)
                except ValueError:
                    problems.append(f"{label}: mirror line {mnumber!r} is not a number")
                else:
                    mpath = root / mrel
                    if not mpath.is_file():
                        problems.append(f"{label}: mirror {mrel} does not exist")
                    else:
                        mlines = mpath.read_text(encoding="utf-8", errors="replace").splitlines()
                        if not 1 <= mline <= len(mlines):
                            problems.append(f"{label}: mirror {mrel} has {len(mlines)} lines, the row cites {mline}")
                        elif expect and expect not in mlines[mline - 1]:
                            problems.append(
                                f"{label}: mirror {mrel}:{mline} does not contain {expect!r} (the second copy drifted)")
        problems += second_problems(label, row, root, roots)
    covered = {str(row.get("lane") or "") for row in rows}
    for lane in sorted(LANES - covered):
        problems.append(f"no row covers the {lane} line")
    return problems


CHECKLIST = "docs/research/power/HW-CONTRACTS-IOS27.md"
ORDER = ["none", "macro", "firmware", "property-number", "layout"]


def second_note(row: dict) -> str:
    entries = row.get("second")
    if isinstance(entries, list) and entries:
        return f"independent, {len(entries)} citation(s)"
    unavailable = row.get("second_unavailable")
    if isinstance(unavailable, dict):
        tried = unavailable.get("tried") or []
        return f"none found, {len(tried) if isinstance(tried, list) else 0} tried"
    return ""


def render(root: pathlib.Path, manifest: pathlib.Path) -> str:
    """The rewire checklist, generated from the table so it cannot drift (P-259)."""
    rows = tomllib.loads(manifest.read_text(encoding="utf-8"))["contract"]
    out = [
        "# iOS 27 rewire checklist (generated)",
        "",
        "Generated by `python3 scripts/check-hw-contracts.py --render` from",
        "`docs/research/power/HW-CONTRACTS.toml`; edit the table, never this file.",
        "The gate fails while the two disagree.",
        "",
        f"{len(rows)} rows. Grouped by `dependence`, which says what a move to",
        "iOS 27 has to re-check: `none` rows are our own encoding and travel as-is,",
        "the rest name the thing to confirm before the number is trusted again.",
        "The `second source` column is the independent evidence behind a `firmware`",
        "row: a citation in another implementation, bytes inside the firmware image,",
        "or the count of sources searched when none exists (see the table's reason).",
        "",
    ]
    for dependence in ORDER:
        group = [row for row in rows if str(row.get("dependence")) == dependence]
        if not group:
            continue
        out.append(f"## {dependence} ({len(group)})")
        out.append("")
        out.append("| id | lane | what | source | second source | 27 action |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for row in group:
            cells = [str(row.get(key) or "").replace("|", "\\|")
                     for key in ("id", "lane", "what", "source")]
            cells.append(second_note(row).replace("|", "\\|"))
            cells.append(str(row.get("ios27") or "").replace("|", "\\|"))
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def checklist_problems(root: pathlib.Path, manifest: pathlib.Path) -> list[str]:
    path = root / CHECKLIST
    if not path.is_file():
        return [f"{CHECKLIST} is missing; run --render"]
    try:
        expected = render(root, manifest)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    if path.read_text(encoding="utf-8") != expected:
        return [f"{CHECKLIST} is stale; run --render (P-259: a generated list may not be hand-edited)"]
    return []


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--manifest")
    parser.add_argument("--render", metavar="PATH", help="write the generated rewire checklist here")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    manifest = pathlib.Path(args.manifest) if args.manifest else root / REL
    if args.render:
        target = pathlib.Path(args.render)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(root, manifest), encoding="utf-8", newline="\n")
        print(f"rendered {len(tomllib.loads(manifest.read_text(encoding='utf-8'))['contract'])} row(s) to {target}")
        return 0

    problems = verify(root, manifest)
    if not args.manifest:
        problems += checklist_problems(root, manifest)
    if problems:
        for problem in problems:
            print(f"❌ {problem}", file=sys.stderr)
        print(f"hw-contracts: {len(problems)} problem(s)", file=sys.stderr)
        return 2 if problems and problems[0].startswith(str(manifest)) else 1
    rows = tomllib.loads(manifest.read_text(encoding="utf-8"))["contract"]
    lanes = sorted({str(row["lane"]) for row in rows})
    independent = sum(1 for row in rows if isinstance(row.get("second"), list) and row["second"])
    pending = sum(1 for row in rows if isinstance(row.get("second_unavailable"), dict))
    print(f"✅ hw-contracts: {len(rows)} contract(s) across {len(lanes)} lane(s) match the lines they cite "
          f"({independent} with an independent second source, {pending} documented as not found)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
