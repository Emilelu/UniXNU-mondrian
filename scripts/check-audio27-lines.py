#!/usr/bin/env python3
"""Check that the line numbers the 27 pages cite still point at the code.

A citation like PongAudioAmp.c:921 is a promise: that line is the one that
prints the probe banner. Add ten lines above it and the promise is broken
while every other gate stays green - the reader jumps to a blank line and
concludes the driver does not print it. The anchors below name the line and
a token that must sit on it; the pages are then read for citations into the
same file, and a citation that no anchor covers is a failure, because it is
either stale or unverified.
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOCS = ["docs/research/audio/IOS27-WIRING.md", "docs/research/audio/IOS27-MIGRATION.md"]
AMP = "drivers/PongAudio/PongAudioAmp.c"
ANCHORS = [
    (AMP, 63, "#if defined(PONG) || defined(XNU_PONG_AUDIO)"),
    (AMP, 105, "dsb sy"),
    (AMP, 111, "delay_for_interval(us, NSEC_PER_USEC)"),
    (AMP, 955, "amp probe start"),
    (AMP, 1004, "amp probe done found="),
]
CITE = re.compile(r"PongAudioAmp\.c:(\d+)")


def lines(repo, name):
    path = os.path.join(repo, name)
    if not os.path.exists(path):
        return None
    return io.open(path, encoding="utf-8", errors="replace").read().split(chr(10))


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    repo = argv[1] if len(argv) > 1 else REPO
    if not os.path.isdir(os.path.join(repo, "docs")):
        print("LINES FAILED: %s has no docs/, so there is nothing to read" % repo)
        return 1
    text = lines(repo, AMP)
    if text is None:
        print("LINES FAILED: %s is not on this branch" % AMP)
        return 1
    known = set()
    moved = []
    for name, number, token in ANCHORS:
        body = lines(repo, name)
        if body is None:
            continue
        known.add(number)
        if number > len(body) or token not in body[number - 1]:
            here = [i + 1 for i, line in enumerate(body) if token in line]
            moved.append((name, number, token, here))
    for name, number, token, here in moved:
        print("LINES FAILED: %s:%d no longer holds %r; the token is on line(s) %s"
              % (name, number, token, here or "nowhere"))
    cited = 0
    stale = []
    for doc in DOCS:
        body = lines(repo, doc)
        if body is None:
            continue
        for number, line in enumerate(body, 1):
            for match in CITE.finditer(line):
                cited += 1
                if int(match.group(1)) not in known:
                    stale.append((doc, number, match.group(1)))
    for doc, number, target in stale:
        print("LINES FAILED: %s:%d cites PongAudioAmp.c:%s, which no anchor covers (anchors: %s)"
              % (doc, number, target, sorted(known)))
    if moved or stale:
        return 1
    print("LINES OK %d anchors hold and %d citation(s) point at them" % (len(known), cited))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
