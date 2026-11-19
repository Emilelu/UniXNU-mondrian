#!/usr/bin/env python3
"""Exercise scripts/judge-k60-sleep-console.py against synthetic consoles.

Every case here is a way a sleep flight can look like progress when skimmed:
eight CPUs halted but only one reported, a halt in the wrong order, a resume
without the boards' reports, a sleep report with a spurious wakeup, or the w10
shape where everything up to the report is printed and the secondaries are
never woken again.  The judge must name each one, must separate "this image
never enabled sleep" (INVALID) from "the resume failed" (FAIL), and must not
fail a console that actually woke every CPU.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-k60-sleep-console.py"
WORK = ROOT / "build" / "sleep-judge-tests"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)

ENABLE = "ArmCpu: platform sleep enabled wake-after=5 s"
ARMED = "K60Sleep: diagnostic trigger armed 6 s"
ENTER = "Time 0x6ae9d430 Message IOCPUSleepKernel enter"
TRACE_ENTER = "K60TRACE: sleep enter cpus=8"
SCHED = "K60TRACE: sched override done"
ACTIONS = "K60TRACE: platform actions done"
QUIESCE = "K60TRACE: quiescing set"
SECONDARIES = "K60TRACE: secondaries done"
RESUMED = "K60TRACE: resumed"
ARMCPU_REPORT = ("ArmCpu: sleep report phase=5 entries=1 spurious=0 last_intid=27 "
                 "last_reason=2 cpu_off=0 asleep_ticks=96018353 masked=0 ticks=0 unarmed=0")
SLEEP_REPORT = "K60Sleep: report prepares=1 restores=1 ticks=0"
WAKE = "K60TRACE: wake cpus done"
EXIT = "IOCPUSleepKernel exit"

checks = 0
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def halts(cpus=(7, 6, 5, 4, 3, 2, 1), state: int = 3) -> list[str]:
    return [f"K60TRACE: halt cpu {cpu} state={state}" for cpu in cpus]


def healthy() -> list[str]:
    return [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE, *halts(),
            SECONDARIES, RESUMED, ARMCPU_REPORT, SLEEP_REPORT, WAKE, EXIT]


def run(lines: list[str], capture: dict | None = None, name: str = "case",
        directory: bool = True, encoding: str = "utf-8") -> subprocess.CompletedProcess:
    where = WORK / name
    where.mkdir(parents=True, exist_ok=True)
    console = where / "console.log"
    console.write_text(("\n".join(lines) + "\n") if lines else "", encoding=encoding)
    if capture is None:
        capture = {"complete": True, "bytes": console.stat().st_size, "state": "captured"}
    elif not capture.get("bytes"):
        capture["bytes"] = console.stat().st_size
    (where / "capture.json").write_text(json.dumps(capture), encoding=encoding + "-sig" if False else "utf-8")
    target = where if directory else console
    return subprocess.run([sys.executable, str(JUDGE), str(target)], **RUN)


def case(name: str, lines: list[str], want_code: int, want: str,
         capture: dict | None = None) -> None:
    result = run(lines, capture, name=name)
    ok = result.returncode == want_code and want in result.stdout
    check(name, ok, f"rc={result.returncode} want={want_code}; "
                    f"output={result.stdout.strip().splitlines()[-1] if result.stdout.strip() else '<empty>'}")


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)

    # A console that woke every CPU passes.
    case("healthy wake", healthy(), 0, "TOTAL  PASS")

    # Not a sleep flight at all: the image never enabled platform sleep.
    case("no platform-sleep arg", [ENTER, TRACE_ENTER], 2, "not a platform-sleep flight")
    # wake-after=0 leaves the probe without a wake source.
    case("wake-after zero", [ENABLE.replace("=5", "=0"), ARMED, ENTER, TRACE_ENTER],
         1, "wake-after=0 disables")

    # The sleep was entered with the wrong CPU count.
    case("seven cpus", healthy()[:3] + ["K60TRACE: sleep enter cpus=7"] + healthy()[4:],
         1, "expected 8")

    # Halt ordering and state are part of the contract.
    case("halt out of order",
         [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE,
          *halts((7, 5, 6, 4, 3, 2, 1)), SECONDARIES, RESUMED, ARMCPU_REPORT,
          SLEEP_REPORT, WAKE],
         1, "halted out of order")
    case("halt cpu twice",
         [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE,
          *halts((7, 6, 5, 4, 3, 2, 1, 1)), SECONDARIES, RESUMED, ARMCPU_REPORT,
          SLEEP_REPORT, WAKE],
         1, "halted twice")
    case("halt not stopped",
         [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE,
          *halts((7, 6, 5, 4, 3, 2, 1), state=2), SECONDARIES, RESUMED, ARMCPU_REPORT,
          SLEEP_REPORT, WAKE],
         1, "not in the stopped state")
    # The halt loop never completed: the console stops mid-halt (the w8 shape).
    case("halt loop never completes",
         [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE, *halts((7, 6))],
         1, "the halt loop never reported completion")

    # Resume and the two reports.
    case("no resume",
         [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE, *halts(),
          SECONDARIES],
         1, "never shows 'K60TRACE: resumed'")
    case("wrong phase",
         [*healthy()[:10], ARMCPU_REPORT.replace("phase=5", "phase=4"), SLEEP_REPORT, WAKE],
         1, "expected 5")
    case("spurious wakeups",
         [*healthy()[:10], ARMCPU_REPORT.replace("spurious=0", "spurious=1"), SLEEP_REPORT, WAKE],
         1, "spurious wakeups=1")
    case("no board report",
         [*healthy()[:11], WAKE],
         1, "the board sleep hook never reported")
    case("hook did not restore",
         [*healthy()[:11], SLEEP_REPORT.replace("restores=1", "restores=0"), WAKE],
         1, "did not both prepare and restore")

    # w10: the report prints, then nothing - the secondaries are never woken.
    hang = [ENABLE, ARMED, ENTER, TRACE_ENTER, SCHED, ACTIONS, QUIESCE, *halts(),
            SECONDARIES, RESUMED, ARMCPU_REPORT, SLEEP_REPORT]
    case("w10 hard hang", hang, 1, "the w10 hard hang",
         capture={"complete": True, "state": "captured", "stopReason": "budget"})
    # A budget cut before the sleep was even entered is not the w10 hang: the
    # classification must follow the first broken link, not the stop reason.
    case("budget cut before enter", [ENABLE, ARMED, "Time 0x6ae9d430 Message IOCPUSleepKernel enter"],
         1, "the first broken link is ENTER",
         capture={"complete": True, "state": "captured", "stopReason": "budget"})
    check("budget cut does not claim the w10 hang",
          "the w10 hard hang" not in run([ENABLE, ARMED], name="budget cut before enable",
                                         capture={"complete": True, "state": "captured",
                                                  "stopReason": "budget"}).stdout)

    # Wake reported but the kernel never returned from IOCPUSleepKernel.
    case("no exit line", healthy()[:-1], 0, "TOTAL  PASS")
    check("no exit line is noted", "IOCPUSleepKernel never exited"
          in run(healthy()[:-1], name="no exit line note").stdout)

    # w9: resume panicked with a spurious wakeup.
    panic = [*hang, "K60PANICFMT caller=0xfffffff0079c059c fmt=Spurious wakeup of cpu %u @%s:%d",
             "K60PANICARGS Spurious wakeup of cpu 1 @IOCPU.cpp:334",
             "K60PANIC: ring kept; restart reason -> bootloader"]
    case("w9 spurious panic", panic, 1, "spurious wakeup on cpu 1 at IOCPU.cpp:334")

    # Capture handling.
    case("capture byte mismatch", healthy(), 1, "capture.json bytes=",
         capture={"complete": True, "bytes": 1, "state": "captured"})
    case("port not observed", healthy(), 1, "port-not-observed",
         capture={"complete": True, "state": "port-not-observed", "stopReason": "no-port"})
    case("cut capture is accepted", healthy(), 0, "TOTAL  PASS",
         capture={"complete": False, "state": "captured", "stopReason": "fastboot-return"})
    # A capture written by PowerShell carries a UTF-8 BOM.
    result = run(healthy(), name="bom capture")
    bom = WORK / "bom capture"
    (bom / "capture.json").write_text(
        json.dumps({"complete": True, "bytes": (bom / "console.log").stat().st_size,
                    "state": "captured"}), encoding="utf-8-sig")
    result = subprocess.run([sys.executable, str(JUDGE), str(bom)], **RUN)
    check("bom capture accepted", result.returncode == 0, f"rc={result.returncode}")

    # Missing capture.json and missing paths are INVALID, never a verdict.
    where = WORK / "no capture"
    where.mkdir(parents=True, exist_ok=True)
    (where / "console.log").write_text("\n".join(healthy()) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(JUDGE), str(where)], **RUN)
    check("missing capture.json", result.returncode == 2, f"rc={result.returncode}")
    result = subprocess.run([sys.executable, str(JUDGE), str(WORK / "absent")], **RUN)
    check("missing path", result.returncode == 2 and "not a file" in result.stderr,
          f"rc={result.returncode}")
    result = subprocess.run([sys.executable, str(JUDGE)], **RUN)
    check("no argument", result.returncode == 4, f"rc={result.returncode}")

    # The two real consoles the judge was written for, when this machine has them.
    # The real consoles live under E:/k60-work on the Windows host and under
    # /mnt/e/k60-work inside WSL; K60_EVIDENCE_ROOT overrides both.
    root = os.environ.get("K60_EVIDENCE_ROOT")
    candidates = [pathlib.Path(root)] if root else [pathlib.Path("E:/k60-work/evidence"),
                                                     pathlib.Path("/mnt/e/k60-work/evidence")]
    evidence = next((path for path in candidates if path.is_dir()), candidates[0])
    real_w9 = evidence / "power-conformance-sleep-w9-20261119-1311"
    real_w10 = evidence / "power-conformance-sleep-w10-20261119-1328"
    if real_w9.is_dir():
        result = subprocess.run([sys.executable, str(JUDGE), str(real_w9)], **RUN)
        check("real w9 is a resume panic",
              result.returncode == 1 and "spurious wakeup on cpu 1" in result.stdout,
              result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "<empty>")
    if real_w10.is_dir():
        result = subprocess.run([sys.executable, str(JUDGE), str(real_w10)], **RUN)
        check("real w10 is a hard hang",
              result.returncode == 1 and "the w10 hard hang" in result.stdout,
              result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "<empty>")

    print(f"TESTS OK {checks} checks ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
