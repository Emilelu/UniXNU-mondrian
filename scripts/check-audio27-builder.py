#!/usr/bin/env python3
"""Check each seam that carries the audio define into the 27 kernel build.

The 27 line builds through scripts/build-ios27-linux.sh, which ends in
`unixnu build kernel`. Three seams there break with a green build, so each
one gets its own verdict (`--seam hook|define|framework`):

  hook       the driver passes K60_CONF_FILES_HOOK, pointed at its own
             scripts/k60-conf-files-hook.py, which must exist in --tree.
             A copy in this audio checkout does not satisfy the driver.
             Without it bsd/conf/files never
             lists the two sources and the glue is not compiled at all.
  define     the driver names PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1,
             but that is only a text seam.  The macro must be present in the
             target's PongAudioAmp.o.json arguments, passed with --object.
             An env prefix or a bash export says how the name was written; it
             does not prove the compiler saw it (P-300 family).  A missing
             object or zero macros is a failure, not "not measured".
  framework  scripts/unixnu/kernel.py starts from dict(os.environ) and calls
             run(['bash', script], ..., env=env). If that ever becomes a
             curated environment, both variables above stop at the CLI.

Exit codes: 0 wired and consistent, 1 a wired file is wrong, 3 nothing to
measure (driver, hook or framework absent, or the driver does not name the
variable yet). A waiting seam therefore prints skip, never ok.
"""

import argparse
import json
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
OBJECT = "PongAudioAmp.o.json"
MACRO = "XNU_PONG_AUDIO"
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
    """Check the shell variable's state at the first kernel command.

    Only an exact assignment followed by an export (or one exported
    assignment) counts. A later assignment, unset, or export after the kernel
    command must not turn a broken handoff green. Comments are ignored.
    """
    lines = code_only(text).splitlines()
    kernel = next((index for index, line in enumerate(lines) if "build kernel" in line), None)
    if kernel is None:
        return False

    expected = re.compile(pattern)
    assignment = re.compile(r"^\s*(export\s+)?%s=(.*?)\s*$" % re.escape(name))
    unset = re.compile(r"^\s*unset\s+%s(?:\s|$)" % re.escape(name))
    bare_export = re.compile(r"^\s*export\s+%s\s*$" % re.escape(name))
    matches = False
    is_exported = False
    for line in lines[:kernel]:
        if unset.match(line):
            matches = False
            is_exported = False
            continue
        found = assignment.match(line)
        if found:
            value = found.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
                value = value[1:-1]
            matches = expected.fullmatch(value) is not None
            is_exported = is_exported or bool(found.group(1))
            continue
        if bare_export.match(line):
            is_exported = matches
    return matches and is_exported


def seam_hook(text, tree):
    if HOOK not in text:
        return 3, ("BUILDER: not wired yet (%s never names %s); without it bsd/conf/files keeps the "
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
    target = tree / HOOK_TAIL
    if not target.is_file():
        return 3, ("BUILDER: hook not present -> seam inert (%s); the checker checkout is not "
                   "the driver target" % target)
    where = "on the kernel line" if inline else "through the environment"
    return 0, "BUILDER OK: %s takes %s=%s %s" % (DRIVER, HOOK, HOOK_TAIL, where)


def resolve_object(path):
    """Return (record file, error).  A directory is searched for OBJECT."""
    if path is None:
        return None, None
    if path.is_file():
        return path, None
    if path.is_dir():
        hits = sorted(path.rglob(OBJECT))
        if not hits:
            return None, "no %s under %s" % (OBJECT, path)
        return max(hits, key=lambda item: item.stat().st_mtime), None
    return None, "%s is not a file or directory" % path


def object_arguments(path):
    """The compile arguments in a .o.json record, or None when unreadable.

    The XNU object record is one JSON object followed by a comma and a newline,
    so json.load() rejects it; raw_decode() reads the object and leaves the
    separator alone.
    """
    text = read(path)
    if not text:
        return None
    try:
        record, _ = json.JSONDecoder().raw_decode(text.lstrip())
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    arguments = record.get("arguments")
    if not isinstance(arguments, list):
        return None
    return [str(item) for item in arguments]


def macro_defined(arguments):
    """True when -DXNU_PONG_AUDIO=1 is in the compiler arguments.

    XNU's object records split the flag and its value into adjacent argv
    entries ("-D", "XNU_PONG_AUDIO=1"); accept the joined spelling too.
    """
    expected = MACRO + "=1"
    for index, argument in enumerate(arguments):
        if argument == "-D" + expected:
            return True
        if (argument == "-D" and index + 1 < len(arguments)
                and arguments[index + 1] == expected):
            return True
    return False


def seam_define(text, object_path=None):
    if DEFINE not in text:
        return 3, ("BUILDER: not wired yet (%s never passes %s=%s); PongAudioAmp.c compiles to nothing "
                   "and the build stays green" % (DRIVER, DEFINE, VALUE))
    inline = hands_over(kernel_lines(text), DEFINE, VALUE)
    if not inline and not exported(text, DEFINE, re.escape(VALUE)):
        return 1, ("BUILDER FAILED: %s mentions %s but never hands %s to the kernel build "
                   "(the array form is reset at build-xnu-generic.sh:166)" % (DRIVER, DEFINE, VALUE))
    if not inline and not bash_shebang(text):
        return 1, ("BUILDER FAILED: %s exports %s under %s, where dash refuses a dotted name; "
                   "use env %s=%s before the command" % (DRIVER, DEFINE, "a non-bash shebang", DEFINE, VALUE))

    resolved, error = resolve_object(object_path)
    if resolved is None and error is None:
        return 3, ("BUILDER: %s names %s in text, but no PongAudioAmp.o.json was measured; "
                   "pass --object <file|ios-obj dir>; text alone is not evidence (P-300)"
                   % (DRIVER, DEFINE))
    if resolved is None:
        return 1, ("BUILDER FAILED: define 没到编译器，胶水编成空壳: %s" % error)
    arguments = object_arguments(resolved)
    if arguments is None:
        return 1, ("BUILDER FAILED: define 没到编译器，胶水编成空壳: %s is not a readable "
                   "object record" % resolved)
    if not macro_defined(arguments):
        return 1, ("BUILDER FAILED: define 没到编译器，胶水编成空壳: %s arguments have no "
                   "-DXNU_PONG_AUDIO=1" % resolved)
    return 0, "BUILDER OK: %s carries -DXNU_PONG_AUDIO=1 in the object record %s" % (
        DEFINE, resolved)


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
    parser.add_argument("--tree", "--gates", dest="tree",
                        help="checkout the driver runs from (default $K60_REPO, $K60_GATES or ../k60-gates)")
    parser.add_argument("--unixnu", help="framework checkout (default $UNIXNU or ../UniXNU)")
    parser.add_argument("--seam", choices=SEAMS, action="append",
                        help="one seam per call; default is all three, one line each")
    parser.add_argument("--object",
                        help="PongAudioAmp.o.json, or an ios-obj directory to search; "
                             "without it the define seam is only text and returns 3")
    options = parser.parse_args(argv)

    here = pathlib.Path(__file__).resolve().parents[1]
    tree = pathlib.Path(options.tree or os.environ.get("K60_REPO")
                        or os.environ.get("K60_GATES") or here.parent / "k60-gates")
    unixnu = pathlib.Path(options.unixnu or os.environ.get("UNIXNU") or here.parent / "UniXNU")
    driver = tree / DRIVER
    object_value = options.object or os.environ.get("K60_AUDIO27_OBJECT")
    object_path = pathlib.Path(object_value) if object_value else None
    seams = options.seam or list(SEAMS)

    codes = []
    for seam in seams:
        if seam == "framework":
            code, message = seam_framework(unixnu)
        elif not driver.is_file():
            code, message = 3, "BUILDER: no build driver at %s (set K60_REPO or pass --tree)" % driver
        elif seam == "hook":
            code, message = seam_hook(read(driver), tree)
        else:
            code, message = seam_define(read(driver), object_path)
        print(message)
        codes.append(code)
    return 1 if 1 in codes else (3 if codes and all(code == 3 for code in codes) else codes[-1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
