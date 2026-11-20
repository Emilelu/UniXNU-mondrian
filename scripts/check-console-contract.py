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
    ("battery-mirror-sample", "drivers/PongPower/K60Battery.cpp",
     "scripts/judge-k60-battery-mirror.py", "SAMPLE_RE", "sample=%u SOC=",
     ("physical source published", "cell")),
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
    ("sleep-enabled", "drivers/ArmCpu/ArmCpu.cpp", "scripts/judge-k60-sleep-console.py",
     "ENABLED_RE", "platform sleep enabled wake-after=", ()),
    ("sleep-report", "drivers/PongPower/K60PlatformSleep.cpp", "scripts/judge-k60-sleep-console.py",
     "SLEEP_REPORT_RE", "K60Sleep: report prepares=", ()),
    ("sleep-armed", "drivers/PongPower/K60PlatformSleep.cpp", "scripts/judge-k60-sleep-console.py",
     "ARMED_RE", "K60Sleep: diagnostic trigger armed", ()),
    ("sleep-armcpu-report", "drivers/ArmCpu/ArmCpu.cpp", "scripts/judge-k60-sleep-console.py",
     "ARMCPU_REPORT_RE", "ArmCpu: sleep report phase=", ()),
    ("sleep-trace-enter", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "TRACE_ENTER_RE", "K60TRACE: sleep enter cpus=", ()),
    ("sleep-trace-resumed", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "RESUME_RE", "K60TRACE: resumed", ()),
    ("sleep-trace-sched", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "SCHED_RE", "K60TRACE: sched override done", ()),
    ("sleep-trace-actions", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "ACTIONS_RE", "K60TRACE: platform actions done", ()),
    ("sleep-trace-quiesce", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "QUIESCE_RE", "K60TRACE: quiescing set", ()),
    ("sleep-trace-halt", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "HALT_RE", "K60TRACE: halt cpu ", ()),
    ("sleep-trace-secondaries", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "SECONDARIES_RE", "K60TRACE: secondaries done", ()),
    ("sleep-trace-wake", "patches/xnu/0629-k60-sleep-trace.patch",
     "scripts/judge-k60-sleep-console.py", "WAKE_RE", "K60TRACE: wake cpus done", ()),
    ("panic-ring", "patches/xnu/0334-k60-panic-reset-fastboot.patch",
     "scripts/judge-k60-sleep-console.py", "PANIC_RE", "K60PANIC: ring kept", ()),
    ("mode1-late-begin", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "LATE_BEGIN_RE", "late read begin (mode 1)", ()),
    ("mode1-late-end", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "LATE_END_RE", "late read end", ()),
    ("mode1-domain", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "DOMAIN_RE", "mode1=read-only", ()),
    ("mode1-header", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "HEADER_RE", "EPSS domains=", ()),
    ("mode1-l3", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "L3_RE", "K60CpuFreq: L3 base=", ()),
    ("mode1-apply", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "WRITE_PATTERNS:apply", "mode%u apply d", ()),
    ("mode1-vote", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "WRITE_PATTERNS:vote", "mode%u vote d", ()),
    ("mode1-pdmem", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "WRITE_PATTERNS:pdmem", "d%u pdmem=", ()),
    ("mode1-restore", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "WRITE_PATTERNS:restore", "restore domains=", ()),
    ("mode1-l3-readback", "drivers/PongPower/K60CpuFreqProbe.cpp",
     "scripts/judge-k60-mode1-console.py", "WRITE_PATTERNS:l3-readback", "readback=ok", ()),
)

# The sleep trace lines are printed from inside the xnu patch with printf(); every other
# pair comes out of a driver through IOLog. The call is a property of the pair, not a guess.
CALLS = {
    "sleep-trace-enter": "printf", "sleep-trace-resumed": "printf",
    "sleep-trace-sched": "printf", "sleep-trace-actions": "printf",
    "sleep-trace-quiesce": "printf", "sleep-trace-halt": "printf",
    "sleep-trace-secondaries": "printf", "sleep-trace-wake": "printf",
    "panic-ring": "printf",
}

# A judge that pins the device's geometry cannot be satisfied by the default made-up values:
# the header line has to carry the real domains=3 cpus=8 lut-rows=40.
NUMBERS = {
    "mode1-header": ("1", "3", "8", "40"),
    # the write patterns only fire in a write mode: mode 1 is the read-only probe
    "mode1-apply": ("2",), "mode1-vote": ("2",),
    "mode1-pdmem": ("2",), "mode1-restore": ("2",),
}

# A regex with no printer is either a missing pair or a line this repository does not print.
# The second case is allowed, but only with a reason a reader can check - the same shape as
# the rule registry's check-or-waiver (P-179: an enumeration that silently drops an item).
EXEMPT = {
    ("scripts/judge-battery.py", "DMESG_FG_RE"):
        "reads Android dmesg for the C3 comparison, so it matches a foreign console, not a "
        "line any driver here prints",
    ("scripts/judge-battery.py", "DMESG_USB_RE"):
        "same as DMESG_FG_RE: the Android side of the C3 comparison",
    ("scripts/judge-k60-sleep-console.py", "ENTER_RE"):
        "stock xnu prints 'Time 0x... Message IOCPUSleepKernel enter' from source that lives "
        "in the kernel tree, not in this repository",
    ("scripts/judge-k60-sleep-console.py", "EXIT_RE"):
        "the matching 'IOCPUSleepKernel exit' line, same stock source",
    ("scripts/judge-k60-sleep-console.py", "SPURIOUS_RE"):
        "stock xnu panic text 'Spurious wakeup of cpu N @file:line'; nothing here prints it",
    ("scripts/judge-k60-sleep-console.py", "PANIC_ARGS_RE"):
        "0387 prints the prefix 'K60PANICARGS ' and then vprintf(fmt, args), so the judged "
        "text is the kernel's own panic format at runtime and has no static format to synthesise",
    ("scripts/judge-k60-mode1-console.py", "LEGACY_DOMAIN_RE"):
        "a looser match for consoles written before the domain line gained its fields; no "
        "current emitter, kept so an older capture still parses",
    ("scripts/judge-k60-mode1-console.py", "SPRINGBOARD_RE"):
        "launchd/SpringBoard text produced by the system once userland starts, not by this repo",
}

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
        elif char == "," and depth == 1:
            # only the first argument is the format: a ternary such as
            # (readback ? "ok" : "mismatch") is another literal inside the same call
            break
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


def find_format(text: str, anchor: str, call: str = "IOLog") -> str | None:
    """The format is not addressed by line number: it is found by the literal the judge
    requires, so moving the print around the file does not break this gate."""
    for match in re.finditer(re.escape(call) + r"\(", text):
        fmt = c_strings(text, match.end() - 1)
        if anchor in fmt:
            return fmt
    return None


def synthesise(fmt: str, fillers: tuple[str, ...] = (), numbers: tuple[str, ...] = ()) -> str:
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
        elif conversion in "diu" and used < len(numbers):
            value = numbers[used]
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


def pairs_present(root: pathlib.Path, pairs=PAIRS) -> int:
    """How many pairs both differ have a side in this tree. A pass over zero pairs is not
    a pass: the other checkout may simply not carry the drivers yet."""
    return sum(1 for _name, emitter, judge, _a, _an, _f in pairs
               if (root / emitter).is_file() and (root / judge).is_file())


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"judge_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_regex(path: pathlib.Path, attribute: str) -> re.Pattern:
    module = load_module(path)
    if attribute.startswith("WRITE_PATTERNS:"):
        key = attribute.split(":", 1)[1]
        return dict(module.WRITE_PATTERNS)[key]
    return getattr(module, attribute)


def coverage_problems(root: pathlib.Path, pairs=PAIRS) -> list[str]:
    """Every pattern a judge matches against a console must either name its printer below or
    say why this repository does not print that line. A judge that grows a new pattern would
    otherwise be added with no pair and nothing would notice (P-179)."""
    problems: list[str] = []
    paired = {(judge, attribute) for _n, _e, judge, attribute, _a, _f in pairs}
    for judge in sorted({judge for _n, _e, judge, _a, _an, _f in pairs}):
        path = root / judge
        if not path.is_file():
            continue
        module = load_module(path)
        attributes = [name for name in dir(module)
                      if name.endswith("_RE") and isinstance(getattr(module, name), re.Pattern)]
        attributes += [f"WRITE_PATTERNS:{key}" for key, _pattern in getattr(module, "WRITE_PATTERNS", ())]
        for attribute in attributes:
            key = (judge, attribute)
            if key in paired and key in EXEMPT:
                problems.append(f"{judge}:{attribute} is both paired and exempt; keep one")
            elif key in EXEMPT and not str(EXEMPT[key]).strip():
                problems.append(f"{judge}:{attribute} is exempt with an empty reason; a reason "
                                f"nobody can read is the same as no pair")
            elif key not in paired and key not in EXEMPT:
                problems.append(f"{judge}:{attribute} matches a console line but no pair says "
                                f"who prints it (add a pair, or an EXEMPT entry with the reason)")
    for judge, attribute in EXEMPT:
        path = root / judge
        if not path.is_file():
            continue
        module = load_module(path)
        if attribute.startswith("WRITE_PATTERNS:"):
            present = attribute.split(":", 1)[1] in dict(getattr(module, "WRITE_PATTERNS", ()))
        else:
            present = isinstance(getattr(module, attribute, None), re.Pattern)
        if not present:
            problems.append(f"EXEMPT names {judge}:{attribute}, which the judge no longer carries")
        elif (judge, attribute) in paired:
            problems.append(f"{judge}:{attribute} is paired now; drop its EXEMPT reason")
    return problems


def verify(root: pathlib.Path, pairs=PAIRS, require_files: bool = True) -> list[str]:
    """require_files=False is for reading another checkout (the iOS 27 tree), where a
    driver that has not been carried yet is not a broken pair - it is a file that is not
    there. What must never be skipped is a pair whose two sides are both present."""
    problems: list[str] = []
    for name, emitter, judge, attribute, anchor, fillers in pairs:
        emitted = root / emitter
        judged = root / judge
        if not emitted.is_file() or not judged.is_file():
            if require_files:
                which = emitter if not emitted.is_file() else judge
                kind = "emitter" if not emitted.is_file() else "judge"
                problems.append(f"{name}: the {kind} {which} does not exist")
            continue
        call = CALLS.get(name, "IOLog")
        fmt = find_format(emitted.read_text(encoding="utf-8", errors="replace"), anchor, call)
        if fmt is None:
            problems.append(f"{name}: no {call} format in {emitter} contains {anchor!r}; "
                            f"the judge waits for a line nothing prints")
            continue
        try:
            pattern = load_regex(judged, attribute)
        except (AttributeError, ImportError, SyntaxError) as error:
            problems.append(f"{name}: {judge} has no usable {attribute}: {error}")
            continue
        numbers = NUMBERS.get(name, ())
        line = synthesise(fmt, fillers, numbers)
        if not pattern.search(line):
            problems.append(f"{name}: {judge}:{attribute} does not match the line {emitter} "
                            f"prints ({line.strip()!r})")
            continue
        # The anchor has to be what carries the match, otherwise a rename elsewhere would
        # slip through and this gate would be green about nothing.
        if pattern.search(synthesise(fmt.replace(anchor, ""), fillers, numbers)):
            problems.append(f"{name}: {attribute} still matches with {anchor!r} removed from "
                            f"the format, so this pair proves nothing")
    if require_files:
        problems += coverage_problems(root, pairs)
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
    exempt = sum(1 for key in EXEMPT)
    print(f"✅ console-contract: {len(PAIRS)} judged line(s) still come out of the emitter "
          f"that prints them; every other pattern a judge matches has a written reason "
          f"({exempt} exempt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
