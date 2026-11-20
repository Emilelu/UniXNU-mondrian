#!/usr/bin/env python3
"""
Check that every log line the 27 pages quote is one the driver prints.

The pages say which output proves which part of the amplifier. A quoted line
that no printf can produce is worse than no line at all: the reader waits for
output that never comes, and every other gate stays green. The format strings
are the only authority, so a quote is walked token by token against them:
conversions accept any value, an ellipsis skips ahead, and the rest must match
as a prefix of the format token, because a quote may cut a line short.

Two places print: the carried sources under drivers/PongAudio, and the 16-line
patches that add what the 27 tree does not take (the TDM pads live in
patches/audio/0003). Both are read, because the pages quote both.
"""

import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOCS = ["docs/research/audio/IOS27-MIGRATION.md", "docs/research/audio/IOS27-WIRING.md"]
SOURCES = ["drivers/PongAudio/*.c", "patches/audio/*.patch"]
QUOTED = re.compile("(PongAudio: [^`]*)")
CONVERSION = re.compile("%[-#0-9.]*[a-zA-Z]")
ELLIPSES = (chr(8230), "...")
HEAD = "printf(\"PongAudio: "


def formats(repo):
    """Return (where, format) for every PongAudio printf this tree can print."""
    found = []
    for pattern in SOURCES:
        for name in sorted(glob.glob(os.path.join(repo, pattern))):
            text = io.open(name, encoding="utf-8", errors="replace").read()
            for number, line in enumerate(text.split(chr(10)), 1):
                at = line.find(HEAD)
                if at < 0:
                    continue
                rest = line[at + len(HEAD) - len("PongAudio: "):]
                end = rest.find(chr(34))
                if end < 0:
                    continue
                where = os.path.relpath(name, repo) + ":" + str(number)
                found.append((where, rest[:end]))
    return found


def pieces(token):
    """The literal pieces of one token, the conversions taken out."""
    return [p for p in CONVERSION.split(token) if p]


def token_ok(quote, token):
    """A quoted token fits when its literal pieces line up with the format."""
    left, right = pieces(quote), pieces(token)
    if not left or not right:
        return True
    for a, b in zip(left, right):
        if not (a.startswith(b) or b.startswith(a)):
            return False
    return True


def matches(quote, fmt):
    """True when the quoted tokens appear, in order, in the format string."""
    want = [w for w in quote.split() if w]
    keep = []
    for word in want:
        bare = word.replace(chr(8230), "").replace("...", "")
        if not any(c.isalnum() for c in bare):
            continue
        keep.append(bare)
    want = keep
    have = fmt.split()
    at = 0
    for word in want:
        while at < len(have) and not token_ok(word, have[at]):
            at += 1
        if at == len(have):
            return False
        at += 1
    return True


def main(argv):
    repo = argv[1] if len(argv) > 1 else REPO
    if not os.path.isdir(os.path.join(repo, "docs")):
        print("LOGLINES FAILED: %s has no docs/, so there is nothing to read" % repo)
        return 1
    forms = formats(repo)
    if not forms:
        print("LOGLINES FAILED: no PongAudio printf under %s" % repo)
        return 1
    checked = 0
    bad = []
    noted = []
    chain = os.path.isdir(os.path.join(repo, "patches", "audio"))
    for doc in DOCS:
        path = os.path.join(repo, doc)
        if not os.path.exists(path):
            continue
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for number, line in enumerate(text.split(chr(10)), 1):
            for match in QUOTED.finditer(line):
                quote = match.group(1).strip()
                checked += 1
                if any(matches(quote, fmt) for _, fmt in forms):
                    continue
                if chain:
                    bad.append((doc, number, quote))
                else:
                    noted.append((doc, number, quote))
    for doc, number, quote in noted:
        print("LOGLINES NOTE: %s:%d quotes '%s'; only the 16-line patch chain prints "
              "it, and patches/audio is not on this branch" % (doc, number, quote))
    for doc, number, quote in bad:
        print("LOGLINES FAILED: %s:%d quotes '%s', which no printf prints"
              % (doc, number, quote))
    if bad:
        print("LOGLINES: %d of %d quoted line(s) are not printed by this tree"
              % (len(bad), checked))
        return 1
    if noted:
        print("LOGLINES OK %d quoted lines (%d of them only the 16-line patch chain "
              "prints, and that chain is not on this branch), %d formats"
              % (checked, len(noted), len(forms)))
    else:
        print("LOGLINES OK %d quoted lines, all printed by %d formats"
              % (checked, len(forms)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
