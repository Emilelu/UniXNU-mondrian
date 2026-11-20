#!/usr/bin/env python3
"""Judge the K60 platform-sleep flight from a boot console.

Why this exists: on 2026-11-19 the platform-sleep line flew eleven images (z,
w, w2-w10) and every verdict was read by eye out of a 40 KB console.  Two of
them looked almost identical - w9 and w10 both reach "K60TRACE: resumed" and
both print the ArmCpu sleep report - yet w9 panicked with
"Spurious wakeup of cpu 1 @IOCPU.cpp:334" and w10 hard-hung with no
"wake cpus done" at all and had to be reset by hand.  A verdict that depends on
spotting the difference between those two tails between rounds is not a
criterion.  This judge makes the difference mechanical, and it names the two
known failure modes instead of leaving "it stopped" as the finding.

Criteria (in boot order):
  CAPTURE   capture.json readable, bytes matches the file, panic marker agrees
  ENABLE    "ArmCpu: platform sleep enabled wake-after=N s" with N > 0 and the
            diagnostic trigger armed - without these the image never asked to
            sleep, so the flight is INVALID, not failed
  ENTER     IOCPUSleepKernel enter and "K60TRACE: sleep enter cpus=8"
  PREPARE   sched override done, platform actions done, quiescing set, in order
  HALT      one "halt cpu N state=3" per secondary (descending), secondaries done
  RESUME    "K60TRACE: resumed" after the secondaries stopped
  REPORT    ArmCpu sleep report phase=5 entries>=1 spurious=0 and
            "K60Sleep: report prepares>=1 restores>=1"
  WAKE      "K60TRACE: wake cpus done" - this is what w10 never printed
  NO-PANIC  no K60PANIC / panic(cpu

Exit status: 0 PASS, 1 FAIL, 2 INVALID, 4 usage error (never a verdict).
Usage:
    python3 scripts/judge-k60-sleep-console.py <evidence-dir|console.log>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ENABLED_RE = re.compile(r"ArmCpu: platform sleep enabled wake-after=(?P<secs>\d+) s")
ARMED_RE = re.compile(r"K60Sleep: diagnostic trigger armed (?P<secs>\d+) s")
ENTER_RE = re.compile(r"Time 0x[0-9a-fA-F]+ Message IOCPUSleepKernel enter")
TRACE_ENTER_RE = re.compile(r"K60TRACE: sleep enter cpus=(?P<cpus>\d+)")
SCHED_RE = re.compile(r"K60TRACE: sched override done")
ACTIONS_RE = re.compile(r"K60TRACE: platform actions done")
QUIESCE_RE = re.compile(r"K60TRACE: quiescing set")
HALT_RE = re.compile(r"K60TRACE: halt cpu (?P<cpu>\d+) state=(?P<state>-?\d+)")
SECONDARIES_RE = re.compile(r"K60TRACE: secondaries done")
RESUME_RE = re.compile(r"K60TRACE: resumed")
ARMCPU_REPORT_RE = re.compile(
    r"ArmCpu: sleep report phase=(?P<phase>\d+) entries=(?P<entries>\d+) "
    r"spurious=(?P<spurious>\d+) last_intid=(?P<intid>\d+) last_reason=(?P<reason>\d+) "
    r"cpu_off=(?P<cpu_off>\d+) asleep_ticks=(?P<ticks>\d+) masked=(?P<masked>\d+) "
    r"ticks=(?P<wait_ticks>\d+) unarmed=(?P<unarmed>\d+)")
SLEEP_REPORT_RE = re.compile(
    r"K60Sleep: report prepares=(?P<prepares>\d+) restores=(?P<restores>\d+) "
    r"ticks=(?P<ticks>\d+)")
WAKE_RE = re.compile(r"K60TRACE: wake cpus done")
EXIT_RE = re.compile(r"IOCPUSleepKernel exit")
PANIC_RE = re.compile(r"K60PANIC: ring kept")
PANIC_ARGS_RE = re.compile(r"K60PANICARGS (?P<args>\S.*)$")
SPURIOUS_RE = re.compile(
    r"Spurious wakeup of cpu (?P<cpu>\d+) @(?P<file>[\w.]+):(?P<line>\d+)")
HALT_STATE_STOPPED = 3
EXPECTED_PHASE = 5


def _at(pattern: re.Pattern, lines: list[str], start: int = 0) -> tuple[int, re.Match] | None:
    for index in range(start, len(lines)):
        match = pattern.search(lines[index])
        if match:
            return index + 1, match
    return None


def _load_capture(capture: pathlib.Path) -> dict | None:
    try:
        return json.loads(capture.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def judge(console: pathlib.Path, capture: pathlib.Path | None) -> tuple[bool, int]:
    text = console.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    criteria: list[tuple[str, str, list[int], list[str]]] = []
    broken: list[str] = []
    capture_data = _load_capture(capture) if capture is not None else None
    stop_reason = str((capture_data or {}).get("stopReason") or "")

    def record(name: str, ok: bool, evidence: list[int], notes: list[str]) -> None:
        criteria.append((name, "PASS" if ok else "FAIL", evidence, notes))
        if not ok:
            broken.append(name)

    # CAPTURE
    ok = bool(lines)
    evidence: list[int] = []
    notes: list[str] = []
    if not ok:
        notes.append("the console file is empty")
    if capture is not None:
        if capture_data is None:
            ok = False
            notes.append("capture.json is present but unreadable")
        else:
            size = console.stat().st_size
            if capture_data.get("bytes") != size:
                ok = False
                notes.append(f"capture.json bytes={capture_data.get('bytes')} but console.log is {size}")
            if capture_data.get("complete") is not True:
                state = str(capture_data.get("state") or "")
                if state.startswith("captured") and stop_reason:
                    notes.append(f"capture.json complete=false (stopReason={stop_reason}); "
                                 "a cut capture is normal on a sleep flight that was reset or timed out")
                else:
                    ok = False
                    notes.append("capture.json does not say complete=true and no stop reason explains it")
            if str(capture_data.get("state") or "") == "port-not-observed":
                ok = False
                notes.append("capture.json says port-not-observed")
    record("CAPTURE", ok, evidence, notes)

    # ENABLE - is this even a sleep flight?
    enabled = _at(ENABLED_RE, lines)
    armed = _at(ARMED_RE, lines)
    ok = enabled is not None and armed is not None
    evidence = [t[0] for t in (enabled, armed) if t]
    notes = []
    if enabled is None:
        notes.append("no 'ArmCpu: platform sleep enabled' line: this image did not enable platform sleep")
    elif int(enabled[1].group("secs")) == 0:
        ok = False
        notes.append("wake-after=0 disables the only wake source this probe has")
    if armed is None:
        notes.append("no 'K60Sleep: diagnostic trigger armed' line: nothing asked the system to sleep")
    record("ENABLE", ok, evidence, notes)
    # Only a console that never enabled platform sleep is INVALID; a flight that
    # enabled it with wake-after=0 or never armed the trigger is a real failure
    # of the probe, not a missing experiment.
    enable_ok = enabled is not None

    # ENTER
    enter = _at(ENTER_RE, lines)
    trace_enter = _at(TRACE_ENTER_RE, lines)
    ok = enter is not None and trace_enter is not None
    evidence = [t[0] for t in (enter, trace_enter) if t]
    notes = []
    if enter is None:
        notes.append("IOCPUSleepKernel was never entered")
    if trace_enter is None:
        notes.append("no 'K60TRACE: sleep enter' line")
    elif int(trace_enter[1].group("cpus")) != 8:
        ok = False
        notes.append(f"sleep entered with cpus={trace_enter[1].group('cpus')}, expected 8")
    record("ENTER", ok, evidence, notes)

    # PREPARE - three ordered steps
    start = trace_enter[0] if trace_enter else 0
    sched = _at(SCHED_RE, lines, start)
    actions = _at(ACTIONS_RE, lines, sched[0] if sched else start)
    quiesce = _at(QUIESCE_RE, lines, actions[0] if actions else (sched[0] if sched else start))
    ok = sched is not None and actions is not None and quiesce is not None
    evidence = [t[0] for t in (sched, actions, quiesce) if t]
    notes = []
    if sched is None:
        notes.append("the scheduler override step never reported")
    if actions is None:
        notes.append("the platform pre-sleep actions step never reported")
    if quiesce is None:
        notes.append("the CPUs were never quiesced")
    record("PREPARE", ok, evidence, notes)

    # HALT - every secondary stops, highest first
    halts: list[tuple[int, int, int]] = []
    for number, line in enumerate(lines, 1):
        match = HALT_RE.search(line)
        if match:
            halts.append((number, int(match.group("cpu")), int(match.group("state"))))
    secondaries = _at(SECONDARIES_RE, lines, halts[0][0] if halts else 0)
    evidence = [n for n, _, _ in halts]
    notes = []
    ok = bool(halts) and secondaries is not None
    cpus = [cpu for _, cpu, _ in halts]
    if not halts:
        notes.append("no secondary CPU was halted")
    else:
        if sorted(cpus, reverse=True) != cpus:
            ok = False
            notes.append(f"secondaries were halted out of order: {cpus}")
        if len(set(cpus)) != len(cpus):
            ok = False
            notes.append(f"a CPU was halted twice: {cpus}")
        wrong = [(cpu, state) for _, cpu, state in halts if state != HALT_STATE_STOPPED]
        if wrong:
            ok = False
            notes.append("halted CPU(s) not in the stopped state: "
                         + ", ".join(f"cpu {cpu} state={state}" for cpu, state in wrong))
    if secondaries is None:
        notes.append("the halt loop never reported completion")
    record("HALT", ok, evidence, notes)

    # RESUME
    resume = _at(RESUME_RE, lines, secondaries[0] if secondaries else (halts[0][0] if halts else 0))
    ok = resume is not None
    record("RESUME", ok, [resume[0]] if resume else [],
           [] if ok else ["the console never shows 'K60TRACE: resumed'"])

    # REPORT - both cores report, and only after the console came back
    arm_report = _at(ARMCPU_REPORT_RE, lines, resume[0] if resume else 0)
    sleep_report = _at(SLEEP_REPORT_RE, lines, arm_report[0] if arm_report else (resume[0] if resume else 0))
    evidence = [t[0] for t in (arm_report, sleep_report) if t]
    notes = []
    ok = arm_report is not None and sleep_report is not None
    if arm_report is None:
        notes.append("no 'ArmCpu: sleep report' line after the resume "
                     "(0629-k60-sleep-trace.patch gates the weak hook on "
                     "K60_PLATFORM_SLEEP_REPORT; a build that sets it to 0, or a tree "
                     "still carrying the old defined(PONG) guard, silently loses it)")
    else:
        group = arm_report[1]
        if int(group.group("phase")) != EXPECTED_PHASE:
            ok = False
            notes.append(f"sleep phase={group.group('phase')}, expected {EXPECTED_PHASE}")
        if int(group.group("entries")) < 1:
            ok = False
            notes.append("no interrupt was recorded while asleep")
        if int(group.group("spurious")) != 0:
            ok = False
            notes.append(f"spurious wakeups={group.group('spurious')}")
        notes.append(f"woke on intid={group.group('intid')} reason={group.group('reason')} "
                     f"asleep_ticks={group.group('ticks')}")
    if sleep_report is None:
        notes.append("the board sleep hook never reported")
    else:
        if int(sleep_report[1].group("prepares")) < 1 or int(sleep_report[1].group("restores")) < 1:
            ok = False
            notes.append("the board hook did not both prepare and restore")
    record("REPORT", ok, evidence, notes)

    # WAKE
    wake = _at(WAKE_RE, lines, sleep_report[0] if sleep_report else (resume[0] if resume else 0))
    exit_line = _at(EXIT_RE, lines, wake[0] if wake else 0)
    notes = []
    ok = wake is not None
    if wake is None:
        notes.append("the secondaries were never woken: the console stops after the sleep report")
    elif exit_line is None:
        notes.append("wake completed but IOCPUSleepKernel never exited")
    record("WAKE", ok, [wake[0]] if wake else [], notes)

    # NO-PANIC
    panic = _at(PANIC_RE, lines)
    panic_args = _at(PANIC_ARGS_RE, lines)
    text_panic = "panic(cpu" in text
    ok = panic is None and panic_args is None and not text_panic
    notes = []
    evidence = [t[0] for t in (panic, panic_args) if t]
    if not ok:
        if panic_args is not None:
            notes.append("panic: " + panic_args[1].group("args"))
        else:
            notes.append("the console carries a panic")
    record("NO-PANIC", ok, evidence, notes)

    # ---- verdict and classification
    print(f"judge-k60-sleep-console: {console}")
    if capture is not None:
        print(f"  capture: {capture} (stopReason={stop_reason or 'none'})")
    for name, verdict, evidence, notes in criteria:
        where = "" if not evidence else " :" + ", :".join(str(n) for n in evidence)
        print(f"{verdict:<5}{name}{where}")
        for note in notes:
            print(f"       - {note}")

    if not enable_ok:
        print("verdict: INVALID - this console is not a platform-sleep flight")
        print("TOTAL  INVALID")
        return False, 2
    if not broken:
        print("verdict: the platform went to sleep, woke on its timer and resumed every CPU")
        print("TOTAL  PASS")
        return True, 0

    spurious = SPURIOUS_RE.search(text)
    if spurious is not None:
        print(f"diagnosis: the resume path panicked with a spurious wakeup on cpu "
              f"{spurious.group('cpu')} at {spurious.group('file')}:{spurious.group('line')} - "
              "a secondary left its halt loop without the wake event the catalog ArmCpu "
              "expects (processor_sleep from the target context)")
    elif wake is None and arm_report is not None and sleep_report is not None:
        # Both reports printed and the wake line never followed: the failure is
        # after the resume.  A console that was cut by a budget before the sleep
        # report reached anything is diagnosed by its first broken link instead.
        print("diagnosis: the kernel stopped after the sleep report - the secondaries were "
              "never woken (the w10 hard hang); this is a post-resume livelock, not a "
              "missing wake source")
    else:
        print(f"diagnosis: the first broken link is {broken[0]}; see the criteria above.")
    print("TOTAL  FAIL")
    return False, 1


class _ArgumentParser(argparse.ArgumentParser):
    """argparse exits 2 for a usage error, but 2 means INVALID here.

    A typo in a flag would then be indistinguishable from "the capture carried
    nothing to judge", which is the one distinction this exit table exists for.
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        raise SystemExit(4)

def main(argv: list[str]) -> int:
    parser = _ArgumentParser(
        description="Judge a K60 platform-sleep console against the resume criteria.")
    parser.add_argument("path", nargs="?",
                        help="an evidence directory (console.log + capture.json) or a console.log")
    args = parser.parse_args(argv)
    if not args.path:
        parser.print_usage(sys.stderr)
        print("judge-k60-sleep-console: a console.log or evidence directory is required", file=sys.stderr)
        return 4
    target = pathlib.Path(args.path)
    if target.is_dir():
        console = target / "console.log"
        capture = target / "capture.json"
        if not console.is_file():
            print(f"judge-k60-sleep-console: no console.log under {target}", file=sys.stderr)
            return 2
        if not capture.is_file():
            print(f"judge-k60-sleep-console: no capture.json under {target} (not a capture directory)",
                  file=sys.stderr)
            return 2
    elif target.is_file():
        console = target
        capture = target.with_name("capture.json")
        if not capture.is_file():
            capture = None
    else:
        print(f"judge-k60-sleep-console: not a file: {target}", file=sys.stderr)
        return 2
    _printed, code = judge(console, capture)
    return code


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
