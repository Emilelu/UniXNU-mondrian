#!/usr/bin/env python3
"""Check the delivery the 27 build driver has to make for the audio glue.

Three claims, each of which decays silently:

1. scripts/build-ios27-linux.sh passes K60_CONF_FILES_HOOK, pointed at this
   tree's scripts/k60-conf-files-hook.py. Without it bsd/conf/files never
   lists the two sources, the glue is not compiled, and the build is green.
2. It passes PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1 in a shape that
   reaches make. scripts/build-xnu-generic.sh:166 resets its EXTRA_MAKE_ARGS
   array, so the same name there is dropped (P-260); a dot-named name can only
   be handed over as an environment prefix or exported by bash, never by dash.
3. The framework hands its own environment to the device builder
   (scripts/unixnu/kernel.py: env = dict(os.environ), then
   run(['bash', script], cwd=ctx.tree, env=env)). If that ever becomes a
   curated environment, both variables above stop at the CLI, silently.

Exit 0 when wired and consistent, 0 with 'not wired yet' while the driver has
neither variable, 1 when it has one of them or when a wired file is wrong.
"""

import argparse
import os
import pathlib
import re
import sys

DRIVER = "scripts/build-ios27-linux.sh"
KERNEL_PY = "scripts/unixnu/kernel.py"
HOOK = "K60_CONF_FILES_HOOK"
HOOK_TAIL = "scripts/k60-conf-files-hook.py"
DEFINE = "PongAudioAmp.o_CFLAGS_ADD"
VALUE = "-DXNU_PONG_AUDIO=1"
ENV_LINE = "env = dict(os.environ)"
RUN_LINE = "env=env"


def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def build_lines(text):
    """The lines that reach `unixnu build kernel`, with their continuations."""
    lines = text.splitlines()
    joined = []
    index = 0
    while index < len(lines):
        line = lines[index]
        while line.endswith(chr(92)) and index + 1 < len(lines):
            index += 1
            line = line[:-1] + " " + lines[index].strip()
        joined.append(line)
        index += 1
    return joined


def hands_over(lines, name, tail):
    """True when the kernel line itself carries name and the string tail."""
    for line in lines:
        if "build kernel" in line and name in line and tail in line:
            return True
    return False


def exported(text, name, pattern, bash_only):
    """True when the script exports name=pattern; dot names need bash."""
    first = text.splitlines()[0] if text.splitlines() else ""
    if bash_only and "bash" not in first:
        return False
    return re.search(r"^\s*export\s+%s=%s\s*$" % (re.escape(name), pattern),
                     text, re.MULTILINE) is not None


def main(argv):
    parser = argparse.ArgumentParser(description="check the 27 driver delivers the audio define")
    parser.add_argument("--gates", help="k60-gates checkout (default $K60_GATES or ../k60-gates)")
    parser.add_argument("--unixnu", help="framework checkout (default $UNIXNU or ../UniXNU)")
    options = parser.parse_args(argv)

    here = pathlib.Path(__file__).resolve().parents[1]
    gates = pathlib.Path(options.gates or os.environ.get("K60_GATES") or here.parent / "k60-gates")
    driver = gates / DRIVER
    if not driver.is_file():
        print("BUILDER: no build driver at %s (set K60_GATES); the 27 driver lives in k60-gates" % driver)
        return 3

    text = read(driver)
    lines = build_lines(text)
    hook = hands_over(lines, HOOK, HOOK_TAIL) or exported(text, HOOK, "[^ ]*" + re.escape(HOOK_TAIL), False)
    hook_named = HOOK_TAIL in text
    define = hands_over(lines, DEFINE, VALUE) or exported(text, DEFINE, re.escape(VALUE), True)

    if not hook and not define:
        print("BUILDER: not wired yet (%s passes neither %s nor %s); until the Lead wires it the glue compiles in and never runs"
              % (DRIVER, HOOK, DEFINE))
        return 0
    problems = []
    if not hook:
        problems.append("the driver builds the kernel without %s" % HOOK)
    elif not hook_named:
        problems.append("the driver names %s but not %s, so the chainer that counts the entries is not the one called" % (HOOK, HOOK_TAIL))
    elif not (here / HOOK_TAIL).is_file():
        problems.append("this tree has no %s to point at" % HOOK_TAIL)
    if not define:
        problems.append("the driver builds the kernel without %s=%s (build-xnu-generic.sh:166 drops the array form)" % (DEFINE, VALUE))
    if problems:
        for problem in problems:
            print("BUILDER FAILED: " + problem)
        return 1

    unixnu = pathlib.Path(options.unixnu or os.environ.get("UNIXNU") or here.parent / "UniXNU")
    kernel_py = unixnu / KERNEL_PY
    framework = ""
    if kernel_py.is_file():
        source = read(kernel_py)
        if ENV_LINE not in source:
            print("BUILDER FAILED: %s no longer starts from %r; the two variables now stop at the CLI"
                  % (KERNEL_PY, ENV_LINE))
            return 1
        if RUN_LINE not in source:
            print("BUILDER FAILED: %s no longer passes env=env to the device builder" % KERNEL_PY)
            return 1
        line = 0
        for number, entry in enumerate(source.splitlines(), 1):
            if ENV_LINE in entry:
                line = number
                break
        framework = " (framework hands its environment through %s:%d)" % (KERNEL_PY, line)
    else:
        framework = " (framework not checked: no checkout at %s)" % unixnu

    print("BUILDER OK: %s takes %s and %s=%s%s"
          % (DRIVER, HOOK, DEFINE, VALUE, framework))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
