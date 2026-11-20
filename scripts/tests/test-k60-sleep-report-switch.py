#!/usr/bin/env python3
"""Test the K60_PLATFORM_SLEEP_REPORT switch end to end, without a kernel build.

The 0629 patch defines the macro to 1 when the build says nothing, and guards
both report calls with it. That is only useful if a build can turn it off: with
the macro on and off the log lines must differ, or "the macro is present" and
"the macro is absent" look identical (P-204 family).

This extracts the macro block and the call block from the patch, compiles them
in a C fixture with two stub report functions, and runs the fixture twice.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATCH = REPO / "patches" / "xnu" / "0629-k60-sleep-trace.patch"
CONFIG = REPO / "configs" / "mondrian_ios27_defconfig"
BUILDER = REPO / "scripts" / "build-xnu-generic.sh"
REFRESH = REPO / "scripts" / "refresh-xnu-generic.py"
BUILD = REPO / "build"

failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(f"ok   {name}")
    else:
        failures += 1
        print(f"FAIL {name}{(': ' + detail) if detail else ''}")


def added_lines() -> list[str]:
    return [line[1:] for line in PATCH.read_text(encoding="utf-8").splitlines()
            if line.startswith("+") and not line.startswith("+++")]


def macro_block(lines: list[str]) -> str:
    start = lines.index("#ifndef K60_PLATFORM_SLEEP_REPORT")
    stop = lines.index("#endif", start)
    return "\n".join(lines[start:stop + 1])


def call_block(lines: list[str]) -> str:
    resumed = next(i for i, line in enumerate(lines) if "K60TRACE: resumed" in line)
    start = next(i for i in range(resumed, len(lines))
                 if lines[i] == "#if K60_PLATFORM_SLEEP_REPORT")
    stop = lines.index("#endif", start)
    return "\n".join(lines[start:stop + 1])


def run_fixture(directory: Path, macro: str, calls: str, define: str | None,
                compiler: str) -> subprocess.CompletedProcess:
    source = directory / "sleep-report.c"
    source.write_text(
        macro + "\n"
        "#include <stdio.h>\n"
        "static int armcpu_calls;\n"
        "static int k60_calls;\n"
        "static void armcpu_report_impl(void) { armcpu_calls++; printf(\"report armcpu\\n\"); }\n"
        "static void k60_report_impl(void) { k60_calls++; printf(\"report k60\\n\"); }\n"
        "static void (*armcpu_sleep_report)(void) __attribute__((unused)) = armcpu_report_impl;\n"
        "static void (*k60_platform_sleep_report)(void) __attribute__((unused)) = k60_report_impl;\n"
        "static void after_resume(void) {\n" + calls + "\n}\n"
        "int main(void) { after_resume(); printf(\"calls %d %d\\n\", armcpu_calls, k60_calls); return 0; }\n",
        encoding="utf-8", newline="\n")
    binary = directory / ("sleep-report-off" if define else "sleep-report-default")
    command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
               "-o", str(binary), str(source)]
    if define:
        command.insert(1, define)
    compiled = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
    if compiled.returncode != 0:
        return compiled
    return subprocess.run([str(binary)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def main() -> int:
    text = PATCH.read_text(encoding="utf-8")
    lines = added_lines()
    try:
        macro = macro_block(lines)
        calls = call_block(lines)
    except ValueError as error:
        print(f"FAIL cannot extract the switch blocks from {PATCH.name}: {error}")
        return 1

    check("the patch defaults the switch to 1",
          "#define K60_PLATFORM_SLEEP_REPORT 1" in macro, macro)
    check("the patch guards both report calls with the switch",
          calls.startswith("#if K60_PLATFORM_SLEEP_REPORT")
          and "armcpu_sleep_report();" in calls
          and "k60_platform_sleep_report();" in calls
          and calls.rstrip().endswith("#endif"), calls)

    skipped = 0
    in_repo = (REPO / ".git").exists()

    def carried(name: str, path: Path, predicate) -> None:
        nonlocal skipped
        if not path.exists():
            if in_repo:
                check(name, False, f"{path} is missing")
            else:
                skipped += 1
                print(f"skip {name} (not carried in this bundle)")
            return
        check(name, predicate(path.read_text(encoding="utf-8")))

    carried("the stage-0 defconfig carries the switch", CONFIG,
            lambda text: "CONFIG_XNU_K60_PLATFORM_SLEEP_REPORT=y" in text)
    carried("the generic builder maps 1 and 0 onto the driver define", BUILDER,
            lambda text: "-DK60_PLATFORM_SLEEP_REPORT=$SLEEP_REPORT_MODE" in text
            and "XNU_K60_PLATFORM_SLEEP_REPORT:-1" in text)
    carried("the generic builder refuses a value other than 0 or 1", BUILDER,
            lambda text: "must be 0 or 1" in text and "exit 1" in text)
    carried("the refresh script re-injects the block instead of dropping it", REFRESH,
            lambda text: "with_sleep_switch" in text
            and "K60_PLATFORM_SLEEP_REPORT: begin" in text
            and "with_sleep_switch(header" in text)

    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        # Windows host runs have no cc; the WSL half of the runner does. The
        # static checks above still ran, so this is a skip, not a pass.
        for name in ("the fixture compiles with the default switch",
                     "the default build prints both reports",
                     "the fixture compiles with the switch off",
                     "the switch-off build prints neither report"):
            print(f"skip {name} (no C compiler on PATH; the WSL runner supplies one)")
        print(f"TESTS OK 10 checks ({failures} failure(s), 4 skipped: no C compiler)")
        return 1 if failures else 0
    BUILD.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="k60-sleep-switch-", dir=BUILD))
    try:
        on = run_fixture(directory, macro, calls, None, compiler)
        check("the fixture compiles with the default switch",
              on.returncode == 0, (on.stderr or on.stdout)[:300])
        check("the default build prints both reports",
              "report armcpu" in on.stdout and "report k60" in on.stdout
              and "calls 1 1" in on.stdout, on.stdout)
        off = run_fixture(directory, macro, calls, "-DK60_PLATFORM_SLEEP_REPORT=0", compiler)
        check("the fixture compiles with the switch off",
              off.returncode == 0, (off.stderr or off.stdout)[:300])
        check("the switch-off build prints neither report",
              "report armcpu" not in off.stdout and "report k60" not in off.stdout
              and "calls 0 0" in off.stdout, off.stdout)
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    suffix = f", {skipped} skipped: not carried" if skipped else ""
    print(f"TESTS OK 10 checks ({failures} failure(s){suffix})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
