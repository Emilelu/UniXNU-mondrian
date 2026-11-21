#!/usr/bin/env python3
"""Check that every consumer of PongScanoutFrame.target subtracts one.

`target` is index+1: 0 means "no dbuf", 1..N means db[i-1]. The size is the
same as the raw-index reading (52, and the frame stays 56 bytes), so a compiler
cannot tell the two apart - db[frame.target] and db[frame.target - 1] both
compile and both look reasonable. Only the convention says which is right.

So this gate does two things:
  1. reads the convention out of GPU-27-V2-FIELDS.md and refuses to judge when
     the marker it expects is gone (that is a drift, exit 2, not a pass);
  2. scans consumer code for both forms and reports the one that contradicts
     the convention.

Dormant by design: until the v2 fields exist in the tree there is nothing to
check, and the gate says so out loud instead of passing silently (P-290).
`db[frame.target]` under index+1 is wrong, and `db[frame.target - 1]` under a
raw index is wrong in the opposite direction - both must go red, which is what
docs/research/gpu/tools/fixtures/ pins.

Usage:
    check-gpu27-target-index.py [--repo DIR] [--convention index|index_plus_one]
                                [--scan DIR ...] [--doc PATH] [--strict] [--json]
Exit: 0 pass or dormant, 1 a consumer contradicts the convention, 2 cannot judge.
"""

import argparse
import json
import os
import re
import sys

# tools -> gpu -> research -> docs -> the tree root
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
DOC = os.path.join("docs", "research", "gpu", "GPU-27-V2-FIELDS.md")
DOC_MARKER = "**索引 + 1**"
SCAN = [os.path.join("drivers", "PongAdreno"), os.path.join("drivers", "PongMetal")]

# db[<anything>.target] / db[<anything>.target - N], with the bracket closed.
TARGET = re.compile(r"db\s*\[\s*[A-Za-z_][\w.>\-]*\.target\s*(?:-\s*(\d+))?\s*\]")
SUFFIX = (".c", ".cc", ".cpp", ".h", ".hpp", ".mm")


def convention_from_doc(path):
    """Return the convention the document declares, or None when it drifted."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    if DOC_MARKER not in text:
        return None
    return "index_plus_one"


def files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for base, _dirs, names in os.walk(root):
            for name in sorted(names):
                if name.endswith(SUFFIX):
                    yield os.path.join(base, name)


def matches(roots):
    found = []
    for path in files(roots):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            for match in TARGET.finditer(line):
                subtract = int(match.group(1) or 0)
                found.append((os.path.relpath(path, REPO), number, subtract, match.group(0)))
    return found


def judge(found, convention):
    """Split the matches into the ones the convention allows and the rest."""
    good, bad = [], []
    for (path, number, subtract, text) in found:
        ok = subtract == 1 if convention == "index_plus_one" else subtract == 0
        (good if ok else bad).append((path, number, text))
    return good, bad


def main():
    parser = argparse.ArgumentParser(description="Consumers of frame.target must match the declared convention")
    parser.add_argument("--repo", default=REPO)
    parser.add_argument("--convention", choices=["index", "index_plus_one"], default=None,
                        help="override the document; the real run reads it from the doc")
    parser.add_argument("--scan", action="append", default=None,
                        help="file or directory to scan (repeatable); defaults to the two Pong drivers")
    parser.add_argument("--doc", default=None)
    parser.add_argument("--strict", action="store_true", help="treat dormant as failure")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    doc = args.doc or os.path.join(args.repo, DOC)
    convention = args.convention or convention_from_doc(doc)
    roots = args.scan or [os.path.join(args.repo, item) for item in SCAN]

    report = {"convention": convention, "scanned": [os.path.relpath(r, args.repo) for r in roots]}
    if convention is None:
        report.update(state="cannot judge", why="the document no longer declares " + DOC_MARKER)
        print(json.dumps(report, ensure_ascii=False) if args.json
              else "K60 GPU27 TARGET INDEX CANNOT JUDGE %s no longer says %s" % (DOC, DOC_MARKER))
        return 2

    found = matches(roots)
    good, bad = judge(found, convention)
    report.update(state="checked", consumers=len(found), allowed=len(good), contradicting=len(bad),
                  lines=[{"file": p, "line": n, "text": t} for (p, n, t) in bad])

    if not found:
        report["state"] = "dormant"
        text = ("K60 GPU27 TARGET INDEX DORMANT no consumer of .target under %s yet (convention %s)"
                % (", ".join(report["scanned"]), convention))
        print(json.dumps(report, ensure_ascii=False) if args.json else text)
        return 1 if args.strict else 0

    if bad:
        report["state"] = "contradicted"
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print("K60 GPU27 TARGET INDEX FAIL convention %s, %d of %d consumers contradict it"
                  % (convention, len(bad), len(found)))
            for (path, number, text) in bad:
                expected = "target - 1" if convention == "index_plus_one" else "target"
                print("  %s:%d %s (expected %s)" % (path, number, text, expected))
        return 1

    print(json.dumps(report, ensure_ascii=False) if args.json
          else "K60 GPU27 TARGET INDEX PASS convention %s, %d consumer(s) agree" % (convention, len(found)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
