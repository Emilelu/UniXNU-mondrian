#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Prove that the console lines the judges parse are still the lines the drivers print.

A judge never sees the driver. It matches a regular expression against a captured
console, so the IOLog format string in the driver and the pattern in the judge are two
copies of one fact (P-259). They drift in the direction that fails silently: rename one
key inside the format and the judge still runs, still exits 0, and reports INVALID for a
device that printed its line perfectly. Nobody notices until the hardware is in hand.

For every pair below the emitter is located by a literal the judge also requires, the
format string is turned into a plausible console line, and the judge's own compiled
regex must match that line. Nothing is quoted twice: the checker reads both sides.
"""

import argparse
import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# (id, emitter, judge, attribute, anchor-both-sides-share, [fillers for %s])
PAIRS = (
    ("battery-sample", "drivers/PongPower/K60Battery.cpp", "scripts/judge-battery.py",
     "SAMPLE_RE", "sample=%u SOC=", ("physical source published", "cell")),
    ("battery-channel-up", "drivers/PongPower/K60Battery.cpp", "scripts/judge-battery.py",
     "CHANNEL_UP_RE", "channel up; measured sign=", ()),
    ("battery-adopt", "drivers/PongPower/K60PmicGlink.cpp", "scripts/judge-battery.py",
     "ADOPT_RE", "adopting authenticated PAS1 GLINK", ()),
    ("handoff-lease", "drivers/PongPower/K60HandoffRuntime.cpp", "scripts/judge-battery.py",
     "LEASE_OK_RE", "K60Handoff: published authenticated PAS1", ()),
    ("handoff-lease-failed", "drivers/PongPower/K60HandoffRuntime.cpp", "scripts/judge-battery.py",
     "LEASE_FAIL_RE", "no lease published", ()),
    ("battery-blocked", "drivers/PongPower/K60Battery.cpp", "scripts/judge-battery.py",
     "BLOCKED_RE", "no authenticated exclusive PAS1/SMEM/GLINK", ()),
    ("battery-failure", "drivers/PongPower/K60Battery.cpp", "scripts/judge-battery.py",
     "FAILURE_RE", "hardware sample unavailable", ("the lease never arrived",)),
)

ESCAPES = {"n": "\n", "t": "\t", "0": "\0", "r": "\r", "\\": "\\", '"': '"'}


def c_strings(text: str, open_paren: int) -> str:
    """Concatenate the C string literals inside one IOLog(...) call."""
    depth = 0
    pieces: list[str] = []
    i = open_paren
    while i < len(text):
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        elif char == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == "\\" and i + 1 < len(text):
                    pieces.append(ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                else:
                    pieces.append(text[i])
                    i += 1
        i += 1
    return "".join(pieces)


def find_format(text: str, anchor: str) -> str | None:
    """The format is not addressed by line number: it is found by the literal the judge
    requires, so moving the IOLog around the file does not break this gate."""
    for match in re.finditer(r"IOLog\(", text):
        fmt = c_strings(text, match.end() - 1)
        if anchor in fmt:
            return fmt
    return None


def synthesise(fmt: str, fillers: tuple[str, ...] = ()) -> str:
    """Turn a printf format into one plausible line. Values do not matter; the anchors
    around them do, and those are exactly what the judge's pattern is written against."""
    out: list[str] = []
    i = 0
    used = 0
    while i < len(fmt):
        if fmt[i] != "%":
            out.append(fmt[i])
            i += 1
            continue
        j = i + 1
        if j < len(fmt) and fmt[j] == "%":
            out.append("%")
            i = j + 1
            continue
        while j < len(fmt) and fmt[j] in "-+ #0":
            j += 1
        while j < len(fmt) and fmt[j].isdigit():
            j += 1
        while j < len(fmt) and fmt[j] in "lh":
            j += 1
        if j >= len(fmt):
            break
        conversion = fmt[j]
        if conversion == "s":
            value = fillers[min(used, len(fillers) - 1)] if fillers else "word"
            used += 1
        elif conversion in "diu":
            value = "1"
        elif conversion in "xX":
            value = "a"
        elif conversion == "c":
            value = "a"
        elif conversion == "p":
            value = "0x0"
        else:
            value = "1"
        out.append(value)
        i = j + 1
    return "".join(out)


def load_regex(path: pathlib.Path, attribute: str) -> re.Pattern:
    spec = importlib.util.spec_from_file_location(f"judge_{path.stem}_{attribute}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attribute)


def verify(root: pathlib.Path, pairs=PAIRS) -> list[str]:
    problems: list[str] = []
    for name, emitter, judge, attribute, anchor, fillers in pairs:
        emitted = root / emitter
        judged = root / judge
        if not emitted.is_file():
            problems.append(f"{name}: the emitter {emitter} does not exist")
            continue
        if not judged.is_file():
            problems.append(f"{name}: the judge {judge} does not exist")
            continue
        fmt = find_format(emitted.read_text(encoding="utf-8", errors="replace"), anchor)
        if fmt is None:
            problems.append(f"{name}: no IOLog format in {emitter} contains {anchor!r}; "
                            f"the judge waits for a line nothing prints")
            continue
        try:
            pattern = load_regex(judged, attribute)
        except (AttributeError, ImportError, SyntaxError) as error:
            problems.append(f"{name}: {judge} has no usable {attribute}: {error}")
            continue
        line = synthesise(fmt, fillers)
        if not pattern.search(line):
            problems.append(f"{name}: {judge}:{attribute} does not match the line {emitter} "
                            f"prints ({line.strip()!r})")
            continue
        # The anchor has to be what carries the match, otherwise a rename elsewhere would
        # slip through and this gate would be green about nothing.
        if pattern.search(synthesise(fmt.replace(anchor, ""), fillers)):
            problems.append(f"{name}: {attribute} still matches with {anchor!r} removed from "
                            f"the format, so this pair proves nothing")
    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    problems = verify(root)
    if problems:
        for problem in problems:
            print(f"❌ {problem}", file=sys.stderr)
        print(f"console-contract: {len(problems)} problem(s)", file=sys.stderr)
        return 2 if problems and "does not exist" in problems[0] else 1
    print(f"✅ console-contract: {len(PAIRS)} judged line(s) still come out of the emitter "
          f"that prints them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
