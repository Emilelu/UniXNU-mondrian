#!/usr/bin/env python3
"""P-266: the conf/files hook must run where the tree exists, and stay there.

Two things are checked, because they fail independently:

  1. build-xnu-generic.sh calls K60_CONF_FILES_HOOK after .cache/xnu-work is
     cloned, not before it.  The framework copy calls it at the top of the file,
     which is before the clone: on a fresh tree every appender answers "tree not
     seeded", the `|| echo` swallows it, and the build goes green with the driver
     sources missing from bsd/conf/files.  That is exactly the state the product
     checker (check-audio27-kernel.py) later calls AUDIO27 FAILED, so the two
     verdicts disagree about the same build.

  2. refresh-xnu-generic.py puts that call back.  Without the second half the
     first fix is undone by the next refresh, silently, which is how it got
     broken in the first place.

A third case pins the failure shape: a hook that fails must abort the build, not
print a line.  The old `|| echo` is the whole bug.
"""
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
BUILDER = REPO / "scripts" / "build-xnu-generic.sh"
REFRESH = REPO / "scripts" / "refresh-xnu-generic.py"

HOOK_CALL = 'python3 "${K60_CONF_FILES_HOOK}"'
CLONE = "git clone --shared refer/xnu .cache/xnu-work"

failures: list[str] = []
checks = 0


def check(condition: bool, label: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(label)


def main() -> int:
    builder = BUILDER.read_text(encoding="utf-8")
    refresh = REFRESH.read_text(encoding="utf-8")

    check(HOOK_CALL in builder, "the builder never calls the hook")
    check(CLONE in builder, "the builder no longer clones .cache/xnu-work")
    if HOOK_CALL in builder and CLONE in builder:
        check(builder.index(HOOK_CALL) > builder.index(CLONE),
              "the hook runs before .cache/xnu-work exists, so it always reports 'tree not seeded'")

    check("conf-files hook failed" in builder,
          "a failing hook no longer aborts the build")
    check("|| echo \"K60: conf/files hook failed\"" not in builder,
          "the hook exit status is still swallowed by '|| echo'")

    # the call must be the one immediately before the final make, not a stray
    makes = [m.start() for m in re.finditer(r"^make -C \.cache/xnu-work ", builder, re.M)]
    check(len(makes) >= 1, "the builder has no final make")
    if makes and HOOK_CALL in builder:
        hook = builder.index(HOOK_CALL)
        check(hook < makes[0],
              "the hook runs after the kernel is already built, so the entries arrive too late")

    check("LATE_HOOK_BLOCK" in refresh,
          "refresh-xnu-generic.py would drop the late hook on the next refresh")
    check("EARLY_HOOK" in refresh,
          "refresh-xnu-generic.py no longer removes the framework's early hook")
    check("EXTRA_CFLAGS" in refresh,
          "refresh-xnu-generic.py lost the anchor it inserts against")

    for label in failures:
        print(f"FAIL {label}")
    if failures:
        print(f"FAIL {len(failures)} of {checks} checks")
        return 1
    print(f"OK {checks} checks: the conf/files hook runs after seeding and survives a refresh")
    return 0


if __name__ == "__main__":
    sys.exit(main())