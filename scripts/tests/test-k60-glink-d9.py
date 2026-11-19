#!/usr/bin/env python3
"""P-248: the GLINK zero-size intent divergence must stay deliberate.

0622-k60-modem-qrtr.patch (the cellular line's copy of bsd/dev/qcom_glink.c)
rejects a whole intent list when one entry has size 0:

    if (!size) return QcomGlinkCorrupt;   /* id 0 is a legal buffer number */

This tree drops the placeholder and keeps the rest, because id 0 is a valid
intent id and a zero-size entry is a sender's unfilled slot, not corruption of
its neighbours (drivers/PongPower/QcomGlink.c, the D9 guard).  The lead
accepted that divergence on 2026-11-19 and asked for it to be written down and
pinned, so a later cellular merge cannot silently "fix" it back.

Two layers, because either alone is a weak check:

  * the source assertion below catches the merge that flips the guard;
  * scripts/tests/test-k60-glink-intent.c proves the semantics on real code —
    a zero-length intent followed by a normal one, the normal one still usable
    for a send and still able to receive data.  It is compiled and run here
    whenever a C compiler is on PATH (WSL/Linux, and CI); on a host without
    one it is skipped with a loud note, never silently passed.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "drivers" / "PongPower" / "QcomGlink.c"
TEST = ROOT / "scripts" / "tests" / "test-k60-glink-intent.c"
RUNNER = ROOT / "scripts" / "tests" / "run-k60-glink-host.sh"

DROP = "if (!size) {g->dropped++; continue;}"
REJECT = "if (!size) return QcomGlinkCorrupt;"

failures = 0


def wsl_path(path: pathlib.Path) -> str:
    """The /mnt/<drive>/... spelling of a path on this host."""
    parts = path.resolve().parts
    # On Windows parts[0] is "E:\\" (drive and separator together).
    drive = parts[0].replace(":", "").replace("\\", "").lower()
    return "/mnt/" + drive + "/" + "/".join(parts[1:])


def check(condition: bool, message: str) -> None:
    global failures
    if condition:
        print(f"PASS {message}")
    else:
        print(f"FAIL {message}")
        failures += 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    text = SOURCE.read_text(encoding="utf-8")
    check(DROP in text, "QcomGlink.c keeps the per-entry drop for a zero-size intent")
    check(REJECT not in text, "QcomGlink.c does not reject the whole intent list")
    check("D9" in text, "the guard names D9 so the next reader finds the reason")
    check("0622-k60-modem-qrtr.patch" in text, "the guard names the cellular patch it diverges from")

    # The written record: PITFALLS.md carries the entry, RULES.toml its gate.
    pitfalls = (ROOT / "docs" / "engineering" / "PITFALLS.md").read_text(encoding="utf-8")
    check("## P-249" in pitfalls, "PITFALLS.md records the divergence as P-249")
    rules = (ROOT / "docs" / "engineering" / "RULES.toml").read_text(encoding="utf-8")
    check('id = "P-249"' in rules, "RULES.toml registers P-249")
    check(TEST.is_file() and RUNNER.is_file(), "the intent suite and its runner exist")

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        # The gate runs from the Windows host, which has no cc; WSL does.  A
        # silent skip would let a broken suite pass the registry, so try WSL
        # before giving up, and fail loudly when neither can build it.
        wsl = shutil.which("wsl")
        if not wsl:
            print("FAIL no C compiler and no wsl.exe: the semantic suite cannot run here")
            print(f"glink-d9: FAIL ({failures + 1} failure(s))")
            return 1
        # bash inside WSL cannot open an E:\... path: translate the runner to
        # its /mnt/<drive>/... form and use a Linux temp directory for output.
        script = wsl_path(RUNNER)
        run = subprocess.run(
            [wsl, "-d", os.environ.get("K60_WSL_DISTRO", "Ubuntu-24.04"), "--",
             "bash", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        print(run.stdout.strip())
        check(run.returncode == 0 and "TESTS OK 70 checks" in run.stdout,
              "the intent suite passes under WSL")
        print(f"glink-d9: {'FAIL' if failures else 'OK'} ({failures} failure(s))")
        return 1 if failures else 0

    with tempfile.TemporaryDirectory() as out:
        binary = pathlib.Path(out) / "glink-intent"
        build = subprocess.run(
            [compiler, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "drivers" / "PongPower"),
             "-o", str(binary), str(TEST), str(SOURCE)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        check(build.returncode == 0, "the intent suite compiles with -Werror")
        if build.returncode != 0:
            print((build.stdout or "") + (build.stderr or ""))
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            print(run.stdout.strip())
            check(run.returncode == 0 and "TESTS OK 70 checks" in run.stdout,
                  "the intent suite reports TESTS OK 70 checks")

    print(f"glink-d9: {'FAIL' if failures else 'OK'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
