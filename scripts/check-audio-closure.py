#!/usr/bin/env python3
"""Audio closure gate for the K60 audio line.

Reads docs/research/audio/AUDIO-CLOSURE.toml and refuses to call the line
ready while any item is open or blocking, so an image cannot be offered for a
boot with a known gap.

Usage:
  python3 scripts/check-audio-closure.py             gate; exit 1 while not ready
  python3 scripts/check-audio-closure.py --report    print the ledger, exit 0
  python3 scripts/check-audio-closure.py --check-evidence   also verify paths
"""

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
LEDGER = REPO / "docs/research/audio/AUDIO-CLOSURE.toml"

KINDS = ("static", "unit", "artifact")
STATES = ("closed", "open", "blocking")
REQUIRED = ("id", "stage", "change", "evidence_kind", "evidence", "criteria", "status", "owner")
LINE_SUFFIX = re.compile(r"^(?P<path>[^:]+)(?::(?P<lines>[0-9,]+))?$")


def load():
    if not LEDGER.exists():
        return None, "missing ledger: " + str(LEDGER)
    with LEDGER.open("rb") as fh:
        try:
            return tomllib.load(fh), None
        except tomllib.TOMLDecodeError as exc:
            return None, "toml error: " + str(exc)


def validate(doc):
    errors = []
    schema = doc.get("schema")
    if schema != 1:
        errors.append("schema must be 1, got " + repr(schema))
    items = doc.get("item") or []
    stages = doc.get("stage") or []
    if not items:
        errors.append("no [[item]] entries")
    if not stages:
        errors.append("no [[stage]] entries: on-device criteria are required")
    seen = set()
    for index, item in enumerate(items):
        where = "item[" + str(index) + "]"
        for field in REQUIRED:
            if field not in item:
                errors.append(where + " missing " + field)
        ident = item.get("id")
        if ident in seen:
            errors.append("duplicate id " + repr(ident))
        seen.add(ident)
        if item.get("evidence_kind") not in KINDS:
            errors.append(where + " evidence_kind must be one of " + ", ".join(KINDS))
        if item.get("status") not in STATES:
            errors.append(where + " status must be one of " + ", ".join(STATES))
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(where + " evidence must be a non-empty list")
    for index, stage in enumerate(stages):
        where = "stage[" + str(index) + "]"
        for field in ("id", "name", "marker", "expect", "on_fail"):
            if field not in stage:
                errors.append(where + " missing " + field)
    return errors


def evidence_paths(item):
    for entry in item.get("evidence", []):
        match = LINE_SUFFIX.match(entry)
        if match:
            yield match.group("path")


def check_evidence(doc):
    errors = []
    for item in doc.get("item") or []:
        for rel in evidence_paths(item):
            if rel.startswith("/"):
                continue
            if not (REPO / rel).exists():
                errors.append(item.get("id", "?") + ": evidence path missing: " + rel)
    return errors


def print_ledger(doc):
    items = doc.get("item") or []
    print("AUDIO-CLOSURE  schema=" + str(doc.get("schema")) + "  updated=" + str(doc.get("updated")))
    print("")
    width = max([len(i.get("id", "")) for i in items] + [4])
    for item in items:
        print(
            "  "
            + item.get("id", "?").ljust(width)
            + "  "
            + item.get("stage", "?").ljust(3)
            + "  "
            + item.get("status", "?").ljust(8)
            + "  "
            + item.get("evidence_kind", "?").ljust(8)
            + "  "
            + item.get("change", "")[:60]
        )
    counts = {state: sum(1 for i in items if i.get("status") == state) for state in STATES}
    print("")
    print(
        "  closed "
        + str(counts["closed"])
        + "   open "
        + str(counts["open"])
        + "   blocking "
        + str(counts["blocking"])
        + "   stages "
        + str(len(doc.get("stage") or []))
    )
    blocking = [i.get("id") for i in items if i.get("status") == "blocking"]
    if blocking:
        print("  blocking: " + ", ".join(str(b) for b in blocking))


def main(argv):
    parser = argparse.ArgumentParser(description="Audio closure gate")
    parser.add_argument("--report", action="store_true", help="print and exit 0")
    parser.add_argument("--check-evidence", action="store_true", help="verify evidence paths exist")
    args = parser.parse_args(argv)

    doc, error = load()
    if error:
        print("[FAIL] " + error)
        return 2

    errors = validate(doc)
    if args.check_evidence:
        errors += check_evidence(doc)
    if errors:
        for error in errors:
            print("[FAIL] " + error)
        return 2

    print_ledger(doc)
    items = doc.get("item") or []
    remaining = [i for i in items if i.get("status") != "closed"]
    if args.report:
        return 0
    if remaining:
        print("")
        print("[REFUSED] " + str(len(remaining)) + " item(s) still open or blocking; no boot may be offered.")
        return 1
    print("")
    print("[OK] every item is closed and every stage has a written criterion.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
