#!/usr/bin/env python3
"""Freeze the fourth class of the iOS 27 prelink review.

The 205 stubbed items split into 25 named targets (61 items), one generic
device-tree getter (5 items), and 105 unnamed targets (139 items).  This tool
classifies exactly that last set with a fixed first-match order:

    B bootcode -> R positive candidate -> S body string -> C caller string
    -> G callgraph only -> Z zero-score candidates -> O no candidate

It reads facts2.json and match.json from the local review workspace, never the
device or the build tree.  --check is the gate used by the document.
"""
from __future__ import annotations

import argparse
import json
import sys

# The 25 concrete names from classify.py CURATED.  They are excluded from the
# fourth class; changing this set changes the denominator and must be reviewed.
NAMED = {
    0xfffffff00b0de068, 0xfffffff00ad05978, 0xfffffff00b416214, 0xfffffff00b41624c,
    0xfffffff00abe3554, 0xfffffff00abe36d4, 0xfffffff00ab86b04, 0xfffffff00b0de1d8,
    0xfffffff00b11a998, 0xfffffff00b11a314, 0xfffffff00b11acd8, 0xfffffff00ac20880,
    0xfffffff00ad3d804, 0xfffffff00ad46814, 0xfffffff00ad468ec, 0xfffffff00ad46948,
    0xfffffff00ada1af4, 0xfffffff00ada94d8, 0xfffffff00add41bc, 0xfffffff00add40f8,
    0xfffffff00abdea40, 0xfffffff00abde90c, 0xfffffff00abdd25c, 0xfffffff00b2a7f90,
    0xfffffff00b2a7e74,
}
GENERIC = 0xfffffff00b432308
PRIORITY = {"B": 0, "R": 1, "S": 2, "C": 3, "G": 4, "Z": 5, "O": 6}
EXPECTED = {"B": (1, 5), "R": (13, 13), "S": (7, 13), "C": (51, 70),
            "G": (8, 12), "Z": (22, 23), "O": (3, 3)}


def classify(facts, matches):
    rows = []
    for rec in facts:
        target = int(rec["target"], 16)
        if target in NAMED or target == GENERIC:
            continue
        match = matches.get(rec["target"], {})
        candidates = match.get("candidates") or []
        top = max([int(c[0]) for c in candidates], default=0)
        strings = [s for s in (rec.get("strings") or []) if s]
        callees = [c for c in (rec.get("callees") or []) if c]
        callers = []
        for site in rec.get("sites") or []:
            callers.extend([s for s in (site.get("caller_strings") or []) if s])
        if "bootcode" in (rec.get("sect") or ""):
            kind, why = "B", "bootcode; no symbol table"
        elif top >= 1:
            kind, why = "R", "candidate score %d: %s" % (
                top, candidates[0][1] if candidates else "")
        elif strings:
            kind, why = "S", "body string: " + strings[0][:56]
        elif callers:
            kind, why = "C", "caller string: " + callers[0][:52]
        elif callees:
            kind, why = "G", "callees: %d; no other artifact" % len(callees)
        elif candidates:
            kind, why = "Z", "candidates %d; top score 0" % len(candidates)
        else:
            kind, why = "O", "no candidate; no strings/callers"
        rows.append({"target": rec["target"], "size": int(rec.get("size") or 0),
                     "items": int(rec.get("items") or 0),
                     "bundles": len(rec.get("bundles") or []),
                     "kind": kind, "why": why})
    rows.sort(key=lambda row: (PRIORITY[row["kind"]], int(row["target"], 16)))
    return rows


def totals(rows):
    result = {}
    for row in rows:
        count, items = result.get(row["kind"], (0, 0))
        result[row["kind"]] = (count + 1, items + row["items"])
    return result


def markdown(rows):
    out = ["| target | size | items | bundles | class | 现有最强证据 |",
           "|---|---:|---:|---:|---|---|"]
    for row in rows:
        out.append("| `%s` | %d | %d | %d | %s | %s |" % (
            row["target"], row["size"], row["items"], row["bundles"],
            row["kind"], row["why"].replace("|", "/")))
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", required=True, help="facts2.json")
    parser.add_argument("--match", required=True, help="match.json")
    parser.add_argument("--markdown", help="write the 105-row table here")
    parser.add_argument("--check", action="store_true",
                        help="require exactly 105 targets / 139 items and the frozen per-class sums")
    args = parser.parse_args()

    with open(args.facts, encoding="utf-8") as handle:
        facts = json.load(handle)
    with open(args.match, encoding="utf-8") as handle:
        matches = {row["target"]: row for row in json.load(handle)}
    rows = classify(facts, matches)
    got = totals(rows)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(markdown(rows) + "\n")
    print("FOURTH CLASS targets=%d items=%d" % (len(rows), sum(r["items"] for r in rows)))
    print("FOURTH CLASS " + " ".join("%s=%d/%d" % (k, got.get(k, (0, 0))[0], got.get(k, (0, 0))[1])
                                     for k in "BRSCGZO"))
    if not args.check:
        return 0
    problems = []
    if len(rows) != 105 or sum(r["items"] for r in rows) != 139:
        problems.append("population is not 105/139")
    for kind, expected in EXPECTED.items():
        if got.get(kind, (0, 0)) != expected:
            problems.append("%s is %r, expected %r" % (kind, got.get(kind), expected))
    if problems:
        for problem in problems:
            print("FOURTH CLASS FAIL " + problem)
        return 1
    print("FOURTH CLASS PASS 105 targets / 139 items, frozen per-class sums")
    return 0


if __name__ == "__main__":
    sys.exit(main())
