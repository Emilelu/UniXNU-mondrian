#!/usr/bin/env python3
"""Judge the flight that claims the v2 layout flip, and the two copies of the flip asserts.

Why this exists
---------------
`k60-gpu-27/docs/research/gpu/FLIP-READINESS.md` clause 5 used to be a sentence:
"the flight that flips the switch can be judged". A sentence is not a criterion.
This tool turns that clause into one command with three outcomes, and its
fixtures are synthetic on purpose - no flight has flipped the switch yet, so
every fixture here says in its first line that it is not evidence.

What the flip claim consists of, and why one half is not enough
---------------------------------------------------------------
The flip is a claim about **two places** at once:

  * the tree: `patches/proposed/pong-scanout-v2-layout-asserts.patch` is in a
    series and the four `static_assert`s in `drivers/PongAdreno/PongScanoutWire.h`
    say exactly what the patch says. `check-gpu27-flip-asserts.py` answers this,
    and it answers `dormant` while no series names the patch - which this tool
    reports as "cannot judge", not as a pass;
  * the flight: the kernel frame line says `scanout version=2`. A flight that
    claims the flip and still prints `version=1` is a red: the image carries the
    old kext, or the patch never entered a series.

The second half is where a missing field must be red rather than unmeasured. The
judge treats an absent field as unmeasured, which is right for a measurement
nobody took - but here the absence itself contradicts the claim, so it is a
failure. That inversion is the whole reason this gate exists next to the judge.

Three paths, all required, none guessed
---------------------------------------
`--judge`, `--flip-asserts` and `--lane-root` are mandatory and there is no
default and no environment variable for any of them. This tool runs against more
than one tree (the lane that guards the wire header, and a shared tree that only
carries this repository), so a built-in default would be right for exactly one
caller and silently wrong for the other. A guessed default is more dangerous
than an error: the run would look like a verdict. Same rule as
`check-io-map-budget.py`'s `source == "default"` exit 2.

Exit codes, following the rest of the gpu27 checks
--------------------------------------------------
  0  every part of the claim holds
  1  the claim is contradicted (version=1, no version marker, header half, judge FAIL)
  2  nothing could be judged (no PONG SCANOUT line, asserts still dormant, judge INVALID,
     a missing required path, or unreadable input)

Usage
-----
  python3 scripts/check-gpu27-postflip.py <console.log> \
      --judge=scripts/judge-gpu27.py \
      --flip-asserts=scripts/check-gpu27-flip-asserts.py \
      --lane-root=<path to the tree that holds drivers/PongAdreno/PongScanoutWire.h> [--json]

Paths may be given as `/e/...` or `/mnt/e/...`; they are rewritten to `E:/...`
because the checks under test are run by a Windows python that joins with `\\`.
"""

import json
import os
import re
import subprocess
import sys

SCANOUT_LINE = re.compile(r"PONG SCANOUT:")
VERSION = re.compile(r"scanout version=(\d+)")
EXPECTED_VERSION = 2

REQUIRED = ("--judge", "--flip-asserts", "--lane-root")


def rebuild(path):
    """Accept /e/... and /mnt/e/... as well as E:/...

    Only a Windows host wants the E:/ spelling. Rewriting on POSIX handed
    python a path that does not exist there, and the helper then failed with
    "can't open file ... E:/hackios/..." joined onto the working directory -
    the same wrong-host translation as P-227.
    """
    if not path:
        return path
    text = path.replace("\\", "/")
    if os.name == "nt":
        if text.startswith("/mnt/e/"):
            return "E:/" + text[len("/mnt/e/"):]
        if text.startswith("/e/"):
            return "E:/" + text[len("/e/"):]
    return text


def run(command):
    """Run a helper gate and return (code, stdout+stderr)."""
    try:
        done = subprocess.run(command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as error:
        return 2, "cannot run %s: %s" % (command[0], error)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def read_flight(path):
    """Which layout versions the frame lines claim, and how many frame lines there are."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as error:
        return None, None, "cannot read %s: %s" % (path, error)
    lines = [line for line in text.splitlines() if SCANOUT_LINE.search(line)]
    versions = []
    for line in lines:
        match = VERSION.search(line)
        if match:
            versions.append(int(match.group(1)))
    return len(lines), sorted(set(versions)), None


def judge(path, judge_path):
    """The judge's own verdict, so this gate does not re-implement its rules."""
    code, output = run([sys.executable, judge_path, path, "--json"])
    payload = None
    start = output.find("{")
    if start >= 0:
        try:
            payload = json.loads(output[start:])
        except ValueError:
            payload = None
    if code == 2 or payload is None:
        return None, 2, output.strip().splitlines()[-1] if output.strip() else "no output"
    return payload, code, ""


def main(argv):
    log = None
    given = {}
    as_json = False
    for arg in argv[1:]:
        if arg == "--json":
            as_json = True
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        elif arg.startswith("--"):
            name, _, value = arg.partition("=")
            if name not in REQUIRED:
                print("unknown option %r (try --help)" % name)
                return 2
            if not value:
                print("%s needs a value: %s=PATH (try --help)" % (name, name))
                return 2
            given[name] = rebuild(value)
        elif log is None:
            log = arg
        else:
            print("only one log per run (got %r as well as %r)" % (arg, log))
            return 2

    missing = [name for name in REQUIRED if name not in given]
    if missing:
        # No default, no environment variable: a guessed path would run quietly on
        # the wrong tree and read as a verdict.
        print("cannot judge: %s must be given explicitly (no default, no environment variable)"
              % ", ".join(missing))
        print("usage: check-gpu27-postflip.py <console.log> --judge=PATH --flip-asserts=PATH "
              "--lane-root=PATH [--json]")
        return 2
    if log is None:
        print("cannot judge: no console log given (try --help)")
        return 2

    judge_path = given["--judge"]
    flip_path = given["--flip-asserts"]
    lane = given["--lane-root"]

    reasons = []

    # Half one: does the flight say which layout it used?
    frames, versions, error = read_flight(log)
    if error:
        print(error)
        return 2
    if frames == 0:
        print("cannot judge: no PONG SCANOUT line in this flight, so the scanout path never ran")
        return 2
    if not versions:
        reasons.append("%d frame line(s) and none says `scanout version=`: after the flip the "
                       "kernel must say which layout it used, and a missing field contradicts "
                       "the claim instead of leaving it unmeasured" % frames)
    elif EXPECTED_VERSION not in versions:
        reasons.append("the frame line says version=%s, not %d: the image carries the v1 kext, "
                       "or the patch never entered a series - stop here, the frame numbers "
                       "below it mean nothing" % ("/".join(str(v) for v in versions),
                                                  EXPECTED_VERSION))
    elif len(versions) > 1:
        reasons.append("the flight reports more than one layout version (%s): the tree and the "
                       "image disagree" % ", ".join(str(v) for v in versions))

    # Half two: do the two copies of the flip asserts still say the same thing?
    if not reasons:
        code, output = run([sys.executable, flip_path, "--lane-root=" + lane])
        tail = [line for line in output.strip().splitlines() if line.strip()]
        if code == 2:
            print(output.strip())
            return 2
        if "dormant" in output:
            print("cannot judge: %s" % (tail[0] if tail else "the flip asserts are dormant"))
            return 2
        if code == 1:
            reasons.append("the flip asserts do not hold: %s"
                           % (tail[0] if tail else "check-gpu27-flip-asserts.py said no"))
        elif not any("identical in the header and the draft" in line for line in tail):
            print("cannot judge: the flip-assert check passed but did not say it compared "
                  "the two copies")
            return 2

    # Half three: the judge's own verdict on the same flight.
    if not reasons:
        payload, code, note = judge(log, judge_path)
        if payload is None:
            print("cannot judge: the judge could not read this log (%s)" % note)
            return 2
        if payload.get("state") == "INVALID":
            print("cannot judge: the judge calls this flight INVALID (%s)"
                  % ("; ".join(payload.get("reasons") or []) or "no reason given"))
            return 2
        if payload.get("state") == "FAIL":
            reasons.extend(payload.get("reasons") or ["the judge failed this flight"])

    state = "FAIL" if reasons else "PASS"
    if as_json:
        print(json.dumps({"state": state, "reasons": reasons,
                          "frames": frames, "versions": versions,
                          "lane_root": lane}, indent=2))
    else:
        if reasons:
            print("FAIL the flight claims the v2 flip and the tree does not back it")
            for reason in reasons:
                print("  - %s" % reason)
        else:
            print("PASS the flight says version=%d and the two copies of the flip asserts agree"
                  % EXPECTED_VERSION)
            print("   %d frame line(s) carried a version, lane root %s" % (frames, lane))
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
