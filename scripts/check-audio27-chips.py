#!/usr/bin/env python3
"""Check that the judge and the driver agree on the amplifier chip ids.

judge-audio-capture.py decides a probe pass or fail partly by asking whether
every reported id is in its KNOWN table. The driver answers the same question
from pong_audio_amp_name(). Two hand-kept copies of one fact drift: add a chip
to the driver and the judge calls it unknown, so a good probe is graded FAILED
and the next flight is wasted. This compares the two tables and fails on any
difference in either direction.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
JUDGE = "scripts/judge-audio-capture.py"
PLAN = "drivers/PongAudio/PongAudioPlan.h"
CASE = re.compile(r"case\s+0x([0-9a-fA-F]+)\s*:\s*return\s*\"([^\"]+)\";")
KNOWN_ENTRY = re.compile(r"0x([0-9a-fA-F]+)\s*:\s*\"([^\"]+)\"")


def read(repo, name):
    path = os.path.join(repo, name)
    if not os.path.exists(path):
        return None
    return io.open(path, encoding="utf-8", errors="replace").read()


def judge_table(text):
    """The KNOWN dict: the block that starts at KNOWN = { and ends at the brace."""
    at = text.find("KNOWN = {")
    if at < 0:
        return None
    end = text.find("}", at)
    return dict((int(a, 16), b) for a, b in KNOWN_ENTRY.findall(text[at:end]))


def driver_table(text):
    at = text.find("pong_audio_amp_name")
    if at < 0:
        return None
    end = text.find("default:", at)
    return dict((int(a, 16), b) for a, b in CASE.findall(text[at:end]))


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    repo = argv[1] if len(argv) > 1 else REPO
    jtext, dtext = read(repo, JUDGE), read(repo, PLAN)
    for name, text in ((JUDGE, jtext), (PLAN, dtext)):
        if text is None:
            print("CHIPS FAILED: %s is not on this branch" % name)
            return 1
    judge, driver = judge_table(jtext), driver_table(dtext)
    if judge is None:
        print("CHIPS FAILED: %s has no KNOWN = { table" % JUDGE)
        return 1
    if driver is None:
        print("CHIPS FAILED: %s has no pong_audio_amp_name() switch" % PLAN)
        return 1
    bad = 0
    for chip in sorted(set(judge) | set(driver)):
        a, b = judge.get(chip), driver.get(chip)
        if a == b:
            continue
        bad += 1
        print("CHIPS FAILED: 0x%04x is %s in %s and %s in %s"
              % (chip, a or "absent", JUDGE, b or "absent", PLAN))
    if bad:
        return 1
    print("CHIPS OK %d ids agree between %s and %s" % (len(judge), JUDGE, PLAN))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
