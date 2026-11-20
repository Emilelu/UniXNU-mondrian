#!/usr/bin/env python3
"""Print the next free pitfall number.

Pitfall numbers are a global resource of main, so counting the file in the
current branch is wrong: two branches can both hand out P-260 (that is exactly
what happened on 2026-11-20). The number has to be the larger of origin/main and
the working tree, plus one.
"""

import argparse
import os
import re
import subprocess
import sys

PATTERN = re.compile(r"P-(\d{3})")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELATIVE = "docs/engineering/PITFALLS.md"


def highest(text):
    numbers = [int(m) for m in PATTERN.findall(text)]
    return max(numbers) if numbers else 0


def read_main():
    result = subprocess.run(["git", "-C", REPO, "show", "origin/main:" + RELATIVE],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None, (result.stderr or "").strip()
    return result.stdout, None


def read_tree():
    path = os.path.join(REPO, RELATIVE)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def self_test():
    # explicit small cases keep the arithmetic obvious
    if highest("P-001 P-009") != 9 or highest("") != 0:
        print("K60 PITFALL ID FAIL highest()")
        return 1
    if max(highest("P-001 P-009"), highest("P-011")) + 1 != 12:
        print("K60 PITFALL ID FAIL next number")
        return 1
    if max(highest(""), highest("P-003")) + 1 != 4:
        print("K60 PITFALL ID FAIL empty main")
        return 1
    print("K60 PITFALL ID PASS highest of main and tree, plus one")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Next free K60 pitfall number")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    main_text, error = read_main()
    tree_text = read_tree()
    if main_text is None and tree_text is None:
        print("K60 PITFALL ID FAIL neither origin/main nor the tree is readable: %s" % (error,))
        return 2
    top_main = highest(main_text or "")
    top_tree = highest(tree_text or "")
    print("K60 PITFALL next P-%03d (main P-%03d, tree P-%03d)" %
          (max(top_main, top_tree) + 1, top_main, top_tree))
    return 0


if __name__ == "__main__":
    sys.exit(main())
