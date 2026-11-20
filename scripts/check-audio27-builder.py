#!/usr/bin/env python3
"""Check each seam that carries the audio define into the 27 kernel build.

The 27 line builds through scripts/build-ios27-linux.sh, which ends in
`unixnu build kernel`. Three seams there break with a green build, so each
one gets its own verdict (`--seam hook|define|framework`):

  hook       the driver passes K60_CONF_FILES_HOOK, pointed at this tree's
             scripts/k60-conf-files-hook.py. Without it bsd/conf/files never
             lists the two sources and the glue is not compiled at all.
  define     the driver passes PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1.
             The array form is reset at scripts/build-xnu-generic.sh:166
             (P-260) and a dotted name cannot be exported by dash, so the
             only shapes that work are an env prefix or a bash export.
  framework  scripts/unixnu/kernel.py starts from dict(os.environ) and calls
             run(['bash', script], ..., env=env). If that ever becomes a
             curated environment, both variables above stop at the CLI.

Exit codes: 0 wired and consistent, or not wired yet (the message says so),
1 a wired file is wrong, 3 nothing to measure (driver or framework absent).
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
SEAMS = ("hook", "define", "framework")


def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def kernel_lines(text):
    """The lines that build a kernel, with shell continuations joined."""
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
    return [line for line in joined if "build kernel" in line]


def code_only(text):
    """The shell without its comments.

    A name after a # is a note to the reader, not a delivery: the driver can
    say `# K60_CONF_FILES_HOOK is set below` and set nothing.  Matching on the
    raw text is how a comment comes to look like wiring (P-251 shape).
    """
    return chr(10).join(line.split("#")[0] for line in text.splitlines())


def hands_over(lines, name, tail):
    for line in lines:
        code = line.split("#")[0]
        if name in code and tail in code:
            return True
    return False


def bash_shebang(text):
    first = text.splitlines()[0] if text.splitlines() else ""
    return "bash" in first


def exported(text, name, pattern):
    """True when the variable reaches the kernel line through the environment.

    Two shapes count: `export NAME=value` on one line, and `NAME=value`
    followed by a bare `export NAME`.  The second is what the 27 driver does,
    because the value is a path built at run time and the export sits inside
    the same `if` that checks the file exists.  A later `unset NAME` cancels
    either shape.  Comments are not code, so they are dropped first.
    """
    code = code_only(text)
    if re.search(r"^\s*export\s+%s=%s[\"\']?\s*$" % (re.escape(name), pattern),
                 code, re.MULTILINE):
        return True
    assign = re.search(r"^\s*%s=%s[\"\']?\s*$" % (re.escape(name), pattern),
                       code, re.MULTILINE)
    bare = re.search(r"^\s*export\s+%s\s*$" % re.escape(name), code, re.MULTILINE)
    if not (assign and bare and bare.start() > assign.start()):
        return False
    if re.search(r"^\s*unset\s+%s\b" % re.escape(name), code[bare.end():],
                 re.MULTILINE):
        return False
    return True


def seam_hook(text, here):
    if HOOK not in text:
        return 0, ("BUILDER: not wired yet (%s never names %s); without it bsd/conf/files keeps the "
                   "two sources unlisted and the glue is not compiled" % (DRIVER, HOOK))
    inline = hands_over(kernel_lines(text), HOOK, HOOK_TAIL)
    ok = inline or exported(text, HOOK, "[^ ]*" + re.escape(HOOK_TAIL))
    if not ok:
        if HOOK not in code_only(text):
            return 1, ("BUILDER FAILED: %s names %s only in a comment, so the kernel line never "
                       "carries it and a build reads as wired" % (DRIVER, HOOK))
        if HOOK_TAIL in text:
            return 1, ("BUILDER FAILED: %s names %s elsewhere but the kernel line does not carry it, "
                       "so the chaining hook never runs" % (DRIVER, HOOK))
        return 1, ("BUILDER FAILED: %s sets %s but not to %s, so the appender that counts the entries "
                   "is not the one called" % (DRIVER, HOOK, HOOK_TAIL))
    if not (here / HOOK_TAIL).is_file():
        return 1, "BUILDER FAILED: this tree has no %s to point at" % HOOK_TAIL
    where = "on the kernel line" if inline else "through the environment"
    return 0, "BUILDER OK: %s takes %s=%s %s" % (DRIVER, HOOK, HOOK_TAIL, where)


def seam_define(text):
    if DEFINE not in text:
        return 0, ("BUILDER: not wired yet (%s never passes %s=%s); PongAudioAmp.c compiles to nothing "
                   "and the build stays green" % (DRIVER, DEFINE, VALUE))
    if hands_over(kernel_lines(text), DEFINE, VALUE):
        return 0, "BUILDER OK: %s takes %s=%s in the env prefix" % (DRIVER, DEFINE, VALUE)
    if exported(text, DEFINE, re.escape(VALUE)):
        if bash_shebang(text):
            return 0, "BUILDER OK: %s exports %s=%s (bash)" % (DRIVER, DEFINE, VALUE)
        return 1, ("BUILDER FAILED: %s exports %s under %s, where dash refuses a dotted name; "
                   "use env %s=%s before the command" % (DRIVER, DEFINE, "a non-bash shebang", DEFINE, VALUE))
    return 1, ("BUILDER FAILED: %s mentions %s but never hands %s to the kernel build "
               "(the array form is reset at build-xnu-generic.sh:166)" % (DRIVER, DEFINE, VALUE))


def seam_framework(unixnu):
    kernel_py = unixnu / KERNEL_PY
    if not kernel_py.is_file():
        return 3, "BUILDER: no framework checkout at %s (set UNIXNU); the pass-through is not measured" % unixnu
    source = read(kernel_py)
    if ENV_LINE not in source:
        return 1, ("BUILDER FAILED: %s no longer starts from %r, so both variables above stop at the CLI"
                   % (KERNEL_PY, ENV_LINE))
    if RUN_LINE not in source:
        return 1, "BUILDER FAILED: %s no longer passes env=env to the device builder" % KERNEL_PY
    line = 0
    for number, entry in enumerate(source.splitlines(), 1):
        if ENV_LINE in entry:
            line = number
            break
    return 0, "BUILDER OK: %s:%d hands dict(os.environ) to the device builder" % (KERNEL_PY, line)


def main(argv):
    parser = argparse.ArgumentParser(description="check the seams that carry the audio define")
    parser.add_argument("--gates", help="k60-gates checkout (default $K60_GATES or ../k60-gates)")
    parser.add_argument("--unixnu", help="framework checkout (default $UNIXNU or ../UniXNU)")
    parser.add_argument("--seam", choices=SEAMS, action="append",
                        help="one seam per call; default is all three, one line each")
    options = parser.parse_args(argv)

    here = pathlib.Path(__file__).resolve().parents[1]
    gates = pathlib.Path(options.gates or os.environ.get("K60_GATES") or here.parent / "k60-gates")
    unixnu = pathlib.Path(options.unixnu or os.environ.get("UNIXNU") or here.parent / "UniXNU")
    driver = gates / DRIVER
    seams = options.seam or list(SEAMS)

    codes = []
    for seam in seams:
        if seam == "framework":
            code, message = seam_framework(unixnu)
        elif not driver.is_file():
            code, message = 3, "BUILDER: no build driver at %s (set K60_GATES)" % driver
        elif seam == "hook":
            code, message = seam_hook(read(driver), here)
        else:
            code, message = seam_define(read(driver))
        print(message)
        codes.append(code)
    return 1 if 1 in codes else (3 if codes and all(code == 3 for code in codes) else codes[-1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
