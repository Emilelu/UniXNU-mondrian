#!/usr/bin/env python3
"""Cases for scripts/check-patch-hunk-counts.py (P-257).

The gate exists because a hand-spliced patch can carry a hunk header that
disagrees with its own body, and neither `git apply --numstat` nor `git apply`
complains: the file is written, truncated, and the build fails on the C file.
Every case here is a patch that the old gates would have accepted.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
GATE = ROOT / "scripts" / "check-patch-hunk-counts.py"
FIXTURES = ROOT / "build" / f"patch-hunk-tests-{os.getpid()}"

failures = 0
checks = 0


def check(name: str, got: object, want: object) -> None:
    global failures, checks
    checks += 1
    if got == want:
        print(f"ok   {name}")
    else:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def write(name: str, text: str) -> pathlib.Path:
    path = FIXTURES / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def run(*paths: pathlib.Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(GATE), *map(str, paths)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


GOOD = """--- /dev/null
+++ b/bsd/dev/thing.c
@@ -0,0 +1,4 @@
+int thing(void)
+{
+	return 0;
+}
"""

SHORT = """--- /dev/null
+++ b/bsd/dev/thing.c
@@ -0,0 +1,2 @@
+int thing(void)
+{
+	return 0;
+}
"""

LONG = """--- /dev/null
+++ b/bsd/dev/thing.c
@@ -0,0 +1,7 @@
+int thing(void)
+{
+	return 0;
+}
"""

# Two files in one plain unified diff, with the blank separator git writes and a
# hunk whose last context line is empty: the parser used to count those as body.
UNIFIED = """--- a/osfmk/arm64/start.s
+++ b/osfmk/arm64/start.s
@@ -10,3 +10,4 @@
 	adrp	x20, EXT(const_boot_args)@page
+	nop
 	add	x20, x20, EXT(const_boot_args)@pageoff
 
--- a/osfmk/arm/arm_init.c
+++ b/osfmk/arm/arm_init.c
@@ -349,2 +349,4 @@
  * Function: Runs once.
  */
+#define K60_X 1
+/* end */
"""


def main() -> int:
    shutil.rmtree(FIXTURES, ignore_errors=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    good = write("good.patch", GOOD)
    result = run(good)
    check("a consistent patch passes", result.returncode, 0)
    check("the pass line names the rule", "P-257" in result.stdout, True)

    for name, text in (("short.patch", SHORT), ("long.patch", LONG)):
        result = run(write(name, text))
        check(f"{name} is refused", result.returncode, 1)
        check(f"{name} reports the disagreement", "carries" in result.stdout, True)
        check(f"{name} names the declared count", "declares +" in result.stdout, True)

    result = run(write("unified.patch", UNIFIED))
    check("a two-file plain unified diff parses", result.returncode, 0)

    result = run(good, write("long2.patch", LONG))
    check("one bad patch fails the run", result.returncode, 1)

    shutil.rmtree(FIXTURES, ignore_errors=True)
    print(f"TESTS OK {checks} checks ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
