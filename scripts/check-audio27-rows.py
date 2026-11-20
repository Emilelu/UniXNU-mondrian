#!/usr/bin/env python3
"""Is the preflight still as long as the three places that count it say?

Rows get added almost every round, and each addition leaves three copies of one
number behind: the script's own ROWS_EXPECTED, the prose in the audio pages,
and the recorded evidence in porting.toml. This gate holds the three together:

  the preflight declares ROWS_EXPECTED and its tail fails the run when the rows
  it printed do not match, so the constant is measured every time it runs;
  here that same constant is compared with every "N rows ok, M skip" sentence
  in the pages and with the "N host rows plus one skip" line of the record.

Usage: python3 scripts/check-audio27-rows.py [repo]
"""

import glob
import os
import re
import sys

DECLARED = re.compile(r"^ROWS_EXPECTED=(\d+)\s*$", re.M)
TAIL = re.compile(r"ROWS FAILED %s rows printed, %s declared")
COUNT = re.compile(r"([0-9〇零一二三四五六七八九十两]+)\s*行[^、。\n\`]{0,12}?\`(ok|skip)\`")
RECORD = re.compile(r"(\d+) host rows plus one skip")
DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def number(text):
    """Chinese or Arabic count up to ninety-nine."""
    if text.isdigit():
        return int(text)
    if not text:
        return None
    if "十" not in text:
        return DIGITS.get(text[0]) if len(text) == 1 else None
    head, _, tail = text.partition("十")
    tens = DIGITS.get(head) if head else 1
    ones = DIGITS.get(tail) if tail else 0
    if tens is None or ones is None:
        return None
    return tens * 10 + ones


def preflight(repo):
    path = os.path.join(repo, "scripts/check-audio27-preflight.sh")
    if not os.path.exists(path):
        return None
    return open(path, encoding="utf-8").read()


def claims(repo):
    """(page, line, ok, skip) for every sentence that counts the rows."""
    out = []
    for page in sorted(glob.glob(os.path.join(repo, "docs/research/audio/*.md"))):
        handle = open(page, encoding="utf-8")
        for index, line in enumerate(handle, 1):
            stated = {}
            for token, label in COUNT.findall(line):
                value = number(token)
                if value is not None and label not in stated:
                    stated[label] = value
            if "ok" in stated and "skip" in stated:
                out.append((os.path.relpath(page, repo), index, stated["ok"], stated["skip"]))
        handle.close()
    return out


def recorded(repo):
    path = os.path.join(repo, "porting.toml")
    if not os.path.exists(path):
        return []
    text = open(path, encoding="utf-8").read()
    return [(int(value), text.count(value) and text.find("%s host rows" % value)) 
            for value in set(RECORD.findall(text))]


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    repo = argv[0] if argv else "."
    text = preflight(repo)
    if text is None:
        print("ROWS: %s has no scripts/check-audio27-preflight.sh, that is not this tree" % repo)
        return 3
    found = DECLARED.search(text)
    if not found:
        print("ROWS FAILED: scripts/check-audio27-preflight.sh declares no ROWS_EXPECTED,"
              " so nothing anchors the pages' counts")
        return 1
    expected = int(found.group(1))
    problems = []

    if not TAIL.search(text):
        problems.append("the preflight no longer compares the rows it printed with ROWS_EXPECTED=%d,"
                        " so the constant is prose too" % expected)

    stated = claims(repo)
    if not stated:
        problems.append("no audio page states how many rows the preflight has")
    for page, line, ok, skip in stated:
        if ok + skip != expected:
            problems.append("%s:%d says %d rows ok and %d skip, which is %d, but the preflight"
                            " declares %d" % (page, line, ok, skip, ok + skip, expected))

    record = recorded(repo)
    for value, _ in record:
        if value + 1 != expected:
            problems.append("porting.toml records %d host rows plus one skip, which is %d, but the"
                            " preflight declares %d" % (value, value + 1, expected))
    if not record and not problems:
        print("ROWS NOTE: porting.toml does not count the rows, so only the pages are compared")

    if problems:
        for problem in problems:
            print("ROWS FAILED: %s" % problem)
        return 1

    for page, line, ok, skip in stated:
        print("ROWS NOTE: %s:%d counts %d ok and %d skip" % (page, line, ok, skip))
    print("ROWS OK %d rows declared, counted the same in %d page claim(s) and the record"
          % (expected, len(stated)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
