#!/usr/bin/env python3
"""Check that the v2 flip assertions in the wire header still say what the draft says.

Why this exists
---------------
`pong-scanout-v2-layout-asserts.patch` carries four numbers that only matter the
day `PONG_SCANOUT_V2_LAYOUT` goes from 0 to 1: the reply is 56 bytes, and token /
evict / target sit at 44 / 48 / 52. While the switch is 0 those assertions do not
compile and hold nothing, so nothing in the tree notices if the patch and the
header drift apart. The day the switch flips, the header is the thing the compiler
reads, and the patch is the thing the next image is built from - if they disagree,
the build either fails at a stranger's hands or, worse, passes with numbers nobody
chose.

So this compares the two copies while both still exist:

  * the four `static_assert`s in `drivers/PongAdreno/PongScanoutWire.h`
    (whitespace-normalised, sorted) against the four `+`-lines of the patch's
    first hunk, by sha256;
  * dormancy: while no `patches/*/series` names the patch, this exits 0 and says
    so. That is deliberate - a gate that cannot run must say it cannot run
    rather than pretend it passed (P-290). It becomes a real criterion the day
    the patch enters a series, with no edit here;
  * the inverse case is a failure: assertions in the header with no series line
    means the tree carries the claim without the record of why. A half block
    (one to three of the four) is a failure too.

Exit codes follow the other gpu27 checks: 0 all hold or dormant, 1 a check
failed, 2 the checker could not read its inputs.

Usage: python3 scripts/check-gpu27-flip-asserts.py [--lane-root=PATH] [--strict]
       --strict makes dormancy a failure, for a branch that claims to be ready.
"""

import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# The lane tree this check guards. Fixed default because the file it reads lives
# in the lane, not in this repository; K60_GPU27_REPO and --lane-root override it.
LANE = os.environ.get("K60_GPU27_REPO") or os.path.join(os.path.dirname(REPO), "k60-gpu-27")
HEADER = os.path.join("drivers", "PongAdreno", "PongScanoutWire.h")
PATCH = os.path.join("patches", "proposed", "pong-scanout-v2-layout-asserts.patch")
PATCH_NAME = "pong-scanout-v2-layout-asserts"

# Exactly the four numbers the decision fixes, and nothing else that happens to
# mention PongScanoutFrame: the offset drafts already assert `reserved` and the
# other members, and those are not this patch's business. The three v2 member
# names are unique to v2, so any value there is still "the v2 line" - which is
# what lets a drifted offset be reported as a disagreement between the two
# copies instead of silently shrinking the count.
ASSERT = re.compile(
    r"static_assert\(\s*"
    r"(?:sizeof\(PongScanoutFrame\)\s*==\s*56"
    r"|offsetof\(PongScanoutFrame\s*,\s*(?:token|evict|target)\)\s*==\s*\d+"
    r")")


def normalise(line):
    """Collapse whitespace so formatting churn does not read as a change."""
    return re.sub(r"\s+", "", line)


def v2_assertions(lines):
    """The normalised text of every line in `lines` that is one of the four."""
    found = []
    for line in lines:
        body = line
        if body.startswith("+"):
            body = body[1:]
        body = body.strip()
        if not body.startswith("static_assert("):
            continue
        if ASSERT.match(normalise(body)):
            found.append(normalise(body))
    return sorted(found)


def digest(items):
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()


def read_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read().splitlines()


def patch_hunk_lines(lines):
    """Only the `+` side of the first file in the patch (the header)."""
    out = []
    seen_header = False
    for line in lines:
        if line.startswith("+++ "):
            seen_header = True
            continue
        if line.startswith("--- ") and seen_header:
            break
        if seen_header:
            out.append(line)
    return out


def series_entries(lane):
    """Every line of every patches/*/series, with the file it came from."""
    root = os.path.join(lane, "patches")
    entries = []
    if not os.path.isdir(root):
        return entries
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, "series")
        if not os.path.isfile(path):
            continue
        for number, line in enumerate(read_lines(path), 1):
            if line.strip() and not line.lstrip().startswith("#"):
                entries.append((os.path.join("patches", name, "series"), number, line.strip()))
    return entries


def main(argv):
    lane = LANE
    strict = False
    for arg in argv[1:]:
        if arg == "--strict":
            strict = True
        elif arg.startswith("--lane-root="):
            lane = arg.split("=", 1)[1]
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            print("unknown argument %r (try --help)" % arg)
            return 2

    header_path = os.path.join(lane, HEADER)
    patch_path = os.path.join(lane, PATCH)
    for path in (header_path, patch_path):
        if not os.path.isfile(path):
            print("cannot read %s" % path)
            return 2

    listed = [entry for entry in series_entries(lane) if PATCH_NAME in entry[2]]
    header = v2_assertions(read_lines(header_path))
    patch = v2_assertions(patch_hunk_lines(read_lines(patch_path)))

    if len(patch) != 4:
        print("the draft itself is wrong: %d of 4 v2 assertions in %s" % (len(patch), PATCH))
        return 1

    if not listed:
        if header:
            print("the header carries %d v2 assertion(s) but no patches/*/series names %s"
                  % (len(header), PATCH_NAME))
            print("a claim in the tree without the record of why it is there is worse than no claim")
            return 1
        print("dormant: %s is in no series, and the header carries no v2 assertions" % PATCH_NAME)
        print("this check becomes a criterion on the day the patch enters a series")
        if strict:
            print("--strict: dormancy counts as a failure here")
            return 1
        return 0

    if len(header) != 4:
        print("the header carries %d of 4 v2 assertions (%s)" % (len(header), HEADER))
        return 1

    if digest(header) != digest(patch):
        only_header = [line for line in header if line not in patch]
        only_patch = [line for line in patch if line not in header]
        print("the two copies disagree (%s vs %s)" % (digest(header)[:16], digest(patch)[:16]))
        for line in only_header:
            print("  header only: %s" % line)
        for line in only_patch:
            print("  patch only:  %s" % line)
        return 1

    where, number, _ = listed[0]
    print("OK the four v2 assertions are identical in the header and the draft")
    print("   sha256 %s" % digest(header))
    print("   listed in %s:%d" % (where, number))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
