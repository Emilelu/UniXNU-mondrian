#!/usr/bin/env python3
"""Check that the boot argument the probe gates on has one name everywhere.

Usage: check-audio27-bootargs.py [repo-root]

The probe only runs when the image boots with pong_audio_probe=1.  That
literal lives in six places:

  1. the driver       drivers/PongAudio/*.c  PE_parse_boot_argn(name)
  2. the image audit  scripts/check-image-args.py  ALLOWED_ADDITIONS
  3. the judge hint   scripts/judge-audio-capture.py
  4. the triage hint  scripts/triage-audio27.py
  5. the wiring page  docs/research/audio/IOS27-WIRING.md
  6. the boot-arg doc docs/engineering/BOOT-ARGS.md (in k60-gates)

Any one of them drifting makes the operator set a flag nobody reads, or
makes the audit drop the flag the driver does read.  Either way the capture
comes back with no amp probe start line and reads like a hardware answer.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[1]
ARGS_DOC = "docs/engineering/BOOT-ARGS.md"
WIRING = "docs/research/audio/IOS27-WIRING.md"
ROW_WORD = "\u542f\u52a8\u53c2\u6570"
TICK = chr(96)


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def driver_calls(repo):
    """Every PE_parse_boot_argn call in the audio driver: name, place, value."""
    found = []
    for path in sorted((repo / "drivers/PongAudio").glob("*.c")):
        text = read(path)
        for match in re.finditer(r'PE_parse_boot_argn\(\s*"([^"]+)"', text):
            tail = text[match.end():match.end() + 400]
            want = re.search(r"mode\s*!=\s*(\d+)u?", tail)
            found.append({
                "name": match.group(1),
                "where": "%s:%d" % (path.relative_to(repo).as_posix(),
                                    line_of(text, match.start())),
                "value": want.group(1) if want else None,
            })
    return found


def allow_list(repo):
    path = repo / "scripts/check-image-args.py"
    if not path.exists():
        return None
    text = read(path)
    start = text.find("ALLOWED_ADDITIONS")
    if start < 0:
        return None
    end = text.find("}", start)
    block = text[start:end if end > 0 else len(text)]
    return set(re.findall(r'"([A-Za-z0-9_]+)"', block))


def hint(repo, rel, name, value):
    path = repo / rel
    if not path.exists():
        return None
    token = "%s=%s" % (name, value)
    if token in read(path):
        return True
    return "no '%s' in %s" % (token, rel)


def wiring_row(repo, name):
    path = repo / WIRING
    if not path.exists():
        return "no %s" % WIRING
    for line in read(path).splitlines():
        if ROW_WORD in line and "%s%s%s" % (TICK, name, TICK) in line:
            return True
    return "%s has no %s row naming %s" % (WIRING, ROW_WORD, name)


def args_doc(repo, name):
    roots = [repo]
    gates = os.environ.get("K60_GATES")
    if gates:
        roots.append(pathlib.Path(gates))
    roots.append(repo.parent / "k60-gates")
    for root in roots:
        path = root / ARGS_DOC
        if path.exists():
            if name in read(path):
                return path.as_posix()
            return "STALE: %s does not name %s" % (path.as_posix(), name)
    return None


def main():
    if any(argument in ("-h", "--help") for argument in sys.argv[1:]):
        print((__doc__ or "").strip())
        return 0
    repo = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO
    calls = driver_calls(repo)
    if not calls:
        print("BOOTARGS FAILED: drivers/PongAudio calls PE_parse_boot_argn nowhere,"
              " so no boot argument gates the probe")
        return 1
    problems = []
    notes = []
    for call in calls:
        name = call["name"]
        value = call["value"]
        if value is None:
            problems.append("%s reads %s but no mode comparison decides the value"
                            % (call["where"], name))
            continue
        allowed = allow_list(repo)
        if allowed is None:
            problems.append("scripts/check-image-args.py has no ALLOWED_ADDITIONS,"
                            " so the image audit cannot pass %s through" % name)
        elif name not in allowed:
            problems.append("%s is absent from ALLOWED_ADDITIONS in"
                            " scripts/check-image-args.py, so the image audit drops"
                            " the flag the driver reads" % name)
        for rel in ("scripts/judge-audio-capture.py", "scripts/triage-audio27.py"):
            state = hint(repo, rel, name, value)
            if state is None:
                notes.append("%s is not on this branch" % rel)
            elif state is not True:
                problems.append(state)
        state = wiring_row(repo, name)
        if state is not True:
            problems.append(state)
        documented = args_doc(repo, name)
        if documented is None:
            notes.append("%s is not on this machine (set K60_GATES)" % ARGS_DOC)
        elif documented.startswith("STALE:"):
            problems.append(documented[7:])
        print("bootargs: %s = %s, read at %s" % (name, value, call["where"]))
    if problems:
        for problem in problems:
            print("BOOTARGS FAILED: %s" % problem)
        return 1
    for note in notes:
        print("BOOTARGS NOTE: %s" % note)
    names = ", ".join(sorted({"%s=%s" % (c["name"], c["value"]) for c in calls}))
    print("BOOTARGS OK %d call(s) name %s in the driver, the allow list, the judge"
          " hint, the triage hint and the wiring page" % (len(calls), names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
