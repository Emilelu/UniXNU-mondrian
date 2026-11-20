#!/usr/bin/env python3
"""Check the three places the sleep-report switch can disappear.

The 0629 patch defaults K60_PLATFORM_SLEEP_REPORT to 1, but that is not enough:
the key must be in the .config, the generic builder must turn it into exactly one
-DK60_PLATFORM_SLEEP_REPORT=<0|1> in EXTRA_CFLAGS, and the xnu compile line for
IOCPU.cpp must actually carry it. P-190 and P-208 were both "the config was
right, the code was not compiled in".

This checker separates the three facts:

  switch         configs/mondrian_ios27_defconfig has the key set to y
  compile-line   the builder block expands to exactly one -D...=1 and the
                 builder passes EXTRA_CFLAGS as CFLAGS_EXTRA, which xnu folds
                 into CFLAGS
  object         IOCPU.cpp is in iokit/conf/files and has an IOCPU.cpo rule;
                 with --log, exactly one IOCPU.cpp compile line carries the
                 macro once, and with --object the object is newer than the
                 source it was built from

Without --log the object assertion is WIRING, not PRODUCT: the checker can
prove the plumbing, not that this build emitted the object. Supply the build
log after a build to turn WIRING into PRODUCT.

Usage:
  python3 scripts/check-sleep-report-build.py
  python3 scripts/check-sleep-report-build.py --log build.log \
      --object build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/Kernel/IOCPU.cpo \
      --source .cache/xnu-work/iokit/Kernel/IOCPU.cpp
"""
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFCONFIG = pathlib.Path("configs") / "mondrian_ios27_defconfig"
BUILDER = pathlib.Path("scripts") / "build-xnu-generic.sh"
BEGIN = "# K60_PLATFORM_SLEEP_REPORT: begin"
END = "# K60_PLATFORM_SLEEP_REPORT: end"
MACRO = "-DK60_PLATFORM_SLEEP_REPORT"


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def checker(root):
    return pathlib.Path(root)


def missing_source(root, relative):
    path = checker(root) / relative
    if path.exists():
        return None
    if not (checker(root) / ".git").exists():
        return "skip"
    return "missing"


def check_switch(root):
    state = missing_source(root, DEFCONFIG)
    if state == "skip":
        return "SKIP", "defconfig not carried in this bundle"
    if state == "missing":
        return "FAIL", "%s is missing" % DEFCONFIG
    lines = read(checker(root) / DEFCONFIG).splitlines()
    found = [line for line in lines if line.startswith("CONFIG_XNU_K60_PLATFORM_SLEEP_REPORT=")]
    if len(found) != 1:
        return "FAIL", "expected one CONFIG_XNU_K60_PLATFORM_SLEEP_REPORT= line, found %d" % len(found)
    value = found[0].split("=", 1)[1].strip()
    if value != "y":
        return "FAIL", "CONFIG_XNU_K60_PLATFORM_SLEEP_REPORT=%s (expected y)" % value
    return "OK", "CONFIG_XNU_K60_PLATFORM_SLEEP_REPORT=y"


def block(text):
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return None, "expected one %r and one %r" % (BEGIN, END)
    start = text.index(BEGIN)
    stop = text.index(END, start) + len(END)
    return text[start:stop], None


def expand(text, value):
    script = ('EXTRA_CFLAGS=""\n' + text + '\nprintf "%s" "$EXTRA_CFLAGS"\n').replace("\r\n", "\n")
    env = dict(os.environ)
    if value is None:
        env.pop("XNU_K60_PLATFORM_SLEEP_REPORT", None)
    else:
        env["XNU_K60_PLATFORM_SLEEP_REPORT"] = str(value)
    bashexe = os.environ.get("K60_BASH") or shutil.which("bash")
    if not bashexe:
        return None, "bash is not installed"
    try:
        return subprocess.run([bashexe, "-s"], input=script, text=True, capture_output=True, env=env,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)


def check_builder(root):
    state = missing_source(root, BUILDER)
    if state == "skip":
        return "SKIP", "builder not carried in this bundle"
    if state == "missing":
        return "FAIL", "%s is missing" % BUILDER
    text = read(checker(root) / BUILDER)
    body, problem = block(text)
    if problem:
        return "FAIL", problem
    for value, wanted in ((1, "1"), (0, "0")):
        result = expand(body, value)
        if isinstance(result, tuple):
            return "FAIL", "cannot run the builder block: %s" % result[1]
        if result.returncode != 0:
            return "FAIL", "builder block refused XNU_K60_PLATFORM_SLEEP_REPORT=%s: %s" % (value, result.stderr.strip())
        flags = result.stdout
        count = flags.count(MACRO)
        if count != 1:
            return "FAIL", "with XNU_K60_PLATFORM_SLEEP_REPORT=%s the expanded EXTRA_CFLAGS carries %s %d time(s)" % (value, MACRO, count)
        if MACRO + "=" + wanted not in flags:
            return "FAIL", "with XNU_K60_PLATFORM_SLEEP_REPORT=%s the expanded EXTRA_CFLAGS lacks %s=%s" % (value, MACRO, wanted)
    invalid = expand(body, 2)
    if isinstance(invalid, tuple):
        return "FAIL", "cannot run the builder block: %s" % invalid[1]
    if invalid.returncode == 0:
        return "FAIL", "builder block accepted XNU_K60_PLATFORM_SLEEP_REPORT=2"
    if "must be 0 or 1" not in invalid.stderr:
        return "FAIL", "builder block refused 2 without the expected message: %s" % invalid.stderr.strip()
    if text.count('CFLAGS_EXTRA="$EXTRA_CFLAGS"') != 1:
        return "FAIL", "builder does not pass EXTRA_CFLAGS as CFLAGS_EXTRA exactly once"
    return "OK", "expands to one %s=1 / =0; CFLAGS_EXTRA receives EXTRA_CFLAGS" % MACRO


def check_xnu(xnu):
    xnu = pathlib.Path(xnu)
    if not xnu.is_dir():
        return "SKIP", "%s is not present on this host" % xnu
    makedefs = xnu / "makedefs" / "MakeInc.def"
    files = xnu / "iokit" / "conf" / "files"
    template = xnu / "iokit" / "conf" / "Makefile.template"
    for path in (makedefs, files, template):
        if not path.is_file():
            return "FAIL", "xnu source lacks %s" % path
    makeinc = read(makedefs)
    start = makeinc.find("\nCFLAGS\t=")
    if start < 0:
        start = makeinc.find("\nCFLAGS =")
    if start < 0 or "$(CFLAGS_EXTRA)" not in makeinc[start:start + 900]:
        return "FAIL", "MakeInc.def does not fold CFLAGS_EXTRA into CFLAGS"
    if not re.search(r"^iokit/Kernel/IOCPU\.cpp\b", read(files), re.M):
        return "FAIL", "iokit/conf/files does not list iokit/Kernel/IOCPU.cpp"
    templ = read(template)
    if "IOCPU.cpo_" not in templ and "IOCPU.o_" not in templ:
        return "FAIL", "the iokit makefile has no IOCPU.cpo/IOCPU.o flags rule"
    return "OK", "CFLAGS_EXTRA is in xnu CFLAGS; IOCPU.cpp is listed and has a cpo rule"


def logical_lines(text):
    result, buffer = [], ""
    for raw in text.splitlines():
        line = buffer + (" " if buffer else "") + raw.strip()
        if line.endswith("\\"):
            buffer = line[:-1].rstrip()
            continue
        result.append(line)
        buffer = ""
    if buffer:
        result.append(buffer)
    return result


def check_product(log_path, object_path=None, source_path=None):
    log = pathlib.Path(log_path)
    if not log.is_file():
        return "FAIL", "%s is missing" % log_path
    lines = logical_lines(read(log))
    candidates = [line for line in lines
                  if "IOCPU.cpp" in line
                  and ("IOCPU.cpo" in line or "IOCPU.o" in line)
                  and MACRO in line]
    if not candidates:
        return "FAIL", "no compile line for IOCPU.cpp carries %s; the config may be right but this object did not see it" % MACRO
    if len(candidates) != 1:
        return "FAIL", "more than one IOCPU.cpp compile line carries %s (%d)" % (MACRO, len(candidates))
    line = candidates[0]
    count = line.count(MACRO)
    if count != 1:
        return "FAIL", "the IOCPU.cpp compile line carries %s %d time(s)" % (MACRO, count)
    match = re.search(re.escape(MACRO) + r"=(\d+)", line)
    if not match:
        return "FAIL", "the IOCPU.cpp compile line carries %s without a value" % MACRO
    if match.group(1) != "1":
        return "FAIL", "the IOCPU.cpp compile line carries %s=%s (expected 1)" % (MACRO, match.group(1))
    target = re.search(r"-o\s+(\S*IOCPU\.(?:cpo|o))", line)
    if not target:
        return "FAIL", "the IOCPU.cpp compile line has no -o IOCPU.cpo/IOCPU.o target"
    target_path = pathlib.Path(target.group(1))
    detail = "IOCPU.cpo compiled with %s=1 once" % MACRO
    if object_path:
        object_path = pathlib.Path(object_path)
        if not object_path.is_file():
            return "FAIL", "object %s does not exist" % object_path
        if object_path.name != target_path.name:
            return "FAIL", "the log builds %s but --object is %s" % (target_path.name, object_path.name)
        if source_path:
            source_path = pathlib.Path(source_path)
            if not source_path.is_file():
                return "FAIL", "source %s does not exist" % source_path
            if object_path.stat().st_mtime < source_path.stat().st_mtime:
                return "FAIL", "%s is older than %s; make did not rebuild it" % (object_path, source_path)
            detail += "; object is newer than the source"
    return "OK", detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--xnu", default=str(pathlib.Path(ROOT).parent / "xnu-12377"))
    parser.add_argument("--log", default=None, help="build log to prove the actual IOCPU.cpp compile line")
    parser.add_argument("--object", default=None, help="built IOCPU.cpo/IOCPU.o")
    parser.add_argument("--source", default=None, help="IOCPU.cpp the object was built from")
    args = parser.parse_args(argv)

    problems = []
    def report(name, result):
        state, detail = result
        print("sleep-report-build: %-12s %s (%s)" % (name, state, detail))
        if state == "FAIL":
            problems.append("%s: %s" % (name, detail))

    report("switch", check_switch(args.root))
    report("compile-line", check_builder(args.root))
    report("object", check_xnu(args.xnu))
    if args.log:
        report("product", check_product(args.log, args.object, args.source))
    else:
        print("sleep-report-build: product      SKIP (no --log; supply a build log to prove the object)")

    if problems:
        for problem in problems:
            print("FAIL %s" % problem)
        print("sleep-report-build: FAIL (%d problem(s))" % len(problems))
        return 1
    if args.log:
        print("sleep-report-build: OK (switch, compile line and object)")
    else:
        print("sleep-report-build: WIRING ONLY (switch and plumbing; the product is not proven without --log)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
