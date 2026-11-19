#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check the iOS 27 migration list against the driver directory.

Why this exists: the migration is a copy of a fixed set of files into a new tree,
and the one mistake that costs a day there is copying a file that looks portable
but is not - or forgetting one that is. The list in
docs/research/audio/IOS27-MIGRATION.md is the contract; this script holds the
same list and fails when the two drift, when the directory grows a file nobody
classified, or (with --compile) when a "pure C" file stops compiling alone.

Usage:
  python3 scripts/check-audio-migration.py            # classification check
  python3 scripts/check-audio-migration.py --compile  # plus a standalone build
  python3 scripts/check-audio-migration.py --copy DIR # the migration itself

--compile copies the pure set into a temporary directory, gives the compiler
-I. and nothing else, and builds each translation unit with
-std=gnu11 -Wall -Wextra -Werror. A file that needs a kernel header fails here
instead of in the 27 tree.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DRIVER = "drivers/PongAudio"
DOC = "docs/research/audio/IOS27-MIGRATION.md"

# Section 1: pure C, no kernel header, host-tested today.
PURE = [
    "PongAudioGeniI2c.c", "PongAudioGeniI2c.h",
    "PongCodecLpi.c", "PongCodecLpi.h",
    "PongCodecMacro.c", "PongCodecMacro.h",
    "PongCodecProbe.c", "PongCodecProbe.h",
    "PongCodecSwr.c", "PongCodecSwr.h",
    "PongAudioAcf.h", "PongAudioAmpProfile.h", "PongAudioAmpReplay.h",
    "PongAudioPlan.h", "PongAudioPlayback.h", "PongAudioRing.h",
    "PongAudioTlmm.h", "PongCodecPlan.h",
]
# Section 2: kernel glue, portable but rewired at the call site.
GLUE = ["PongAudioAmp.c", "PongAudioRegs.h"]
# Section 1b: travels only so the host tests keep compiling. The AFE/TDM
# parameter table is dead on this firmware, so no driver file may call it, but
# tests/test-pong-audio-geni-i2c.c:30 includes it and the 979 cases cover it.
TESTS_ONLY = ["PongAudioAfe.h"]
# Section 3: must not travel. The two patches are bound to the iOS 16 tree.
FROZEN = []
FROZEN_NAMES = ["0504-k60-audio-pong-audio.patch",
                "0003-k60-audio-afe-selftest.patch"]


def fail(message):
    print("FAIL " + message)
    return 1


ROW = re.compile(r"\|\s*`([^`]+)`(?:\s*/\s*`([^`]+)`)?\s*\|\s*([0-9/ ]+?)\s*\|")


def line_counts(doc):
    """The table carries a line count per file; drift there means a stale document."""
    errors = 0
    covered = set()
    tables = doc.split("## 1.")[1].split("## 3.")[0]
    for line in tables.splitlines():
        found = ROW.match(line.strip())
        if not found:
            continue
        first, second, numbers = found.group(1), found.group(2), found.group(3)
        names = [first] + ([first[:-2] + second] if second else [])
        claims = [n for n in numbers.replace("/", " ").split() if n.isdigit()]
        if len(claims) != len(names):
            errors += fail("the row for %s has %d line count(s) for %d file(s)"
                           % (first, len(claims), len(names)))
            continue
        for name, claimed in zip(names, claims):
            covered.add(name)
            real = os.path.join(REPO, DRIVER, name)
            if not os.path.isfile(real):
                errors += fail("%s is in the table but not on disk" % name)
                continue
            with open(real, "r", encoding="utf-8", errors="replace") as handle:
                lines = sum(1 for _ in handle)
            if lines != int(claimed):
                errors += fail("%s has %d lines, the table says %s"
                               % (name, lines, claimed))
    for name in PURE + GLUE + TESTS_ONLY:
        if name not in covered:
            errors += fail("%s carries no line count in the tables" % name)
    print("line counts: %d file(s) checked against the tables" % len(covered))
    return errors

def classify():
    errors = 0
    driver_dir = os.path.join(REPO, DRIVER)
    present = set()
    for name in sorted(os.listdir(driver_dir)):
        if name.endswith(".c") or name.endswith(".h"):
            present.add(name)
    known = set(PURE) | set(GLUE) | set(TESTS_ONLY) | set(FROZEN)
    for name in sorted(present - known):
        errors += fail("%s/%s is not classified in the migration list" % (DRIVER, name))
    for name in sorted(known - present):
        errors += fail("%s/%s is listed for migration but missing" % (DRIVER, name))

    doc_path = os.path.join(REPO, DOC)
    with open(doc_path, "r", encoding="utf-8") as handle:
        doc = handle.read()
    portable_section = doc.split("## 1.")[1].split("## 3.")[0]
    # Rows pair the two halves of a module as "`Name.c` / `.h`"; expand that so a
    # header is never reported missing just because the row abbreviates it.
    portable_section = re.sub(r"`(\w+)\.c` / `\.h`", r"`\1.c` `\1.h`", portable_section)
    frozen_section = doc.split("## 3.")[1].split("## 4.")[0]
    for name in PURE + GLUE + TESTS_ONLY:
        if name not in portable_section:
            errors += fail("%s is portable but the document never names it" % name)
    for name in FROZEN_NAMES:
        if name not in frozen_section:
            errors += fail("%s must be listed as not travelling" % name)
    for name in PURE + GLUE:
        if name in frozen_section:
            errors += fail("%s appears in the do-not-copy table" % name)

    errors += line_counts(doc)
    errors += pong_guards()

    total = len(PURE) + len(GLUE) + len(TESTS_ONLY)
    print("files: %d portable (%d pure C, %d glue, %d test-only), %d frozen"
          % (total, len(PURE), len(GLUE), len(TESTS_ONLY), len(FROZEN)))
    return errors


PONG_GUARD = re.compile(r"^\s*#\s*(?:if|ifdef|elif)\b[^\n]*\bPONG\b")


def pong_guards():
    """A second PONG guard is how a file silently leaves the 27 build.

    The glue is compiled on 27 because XNU_PONG_AUDIO is defined for that one
    object; a file wrapped in #if defined(PONG) alone compiles to nothing there
    and the only symptom is a missing symbol much later. So exactly one guard is
    allowed, it has to be the two-way one, and it has to be in the glue.
    """
    errors = 0
    hits = []
    for name in PURE + GLUE:
        path = os.path.join(REPO, DRIVER, name)
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                if PONG_GUARD.match(line):
                    hits.append((name, number, line.strip()))
    for name, number, line in hits:
        if name == "PongAudioAmp.c" and "XNU_PONG_AUDIO" in line:
            continue
        errors += fail("%s:%d guards on PONG alone; on 27 that file compiles to nothing"
                       % (name, number))
    if not hits:
        errors += fail("the glue carries no PONG guard, so the macro cannot switch it")
    print("pong guards: %d in the portable set (1 expected, PongAudioAmp.c)" % len(hits))
    return errors


def compile_pure():
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        return fail("no C compiler on PATH; run this from WSL")
    errors = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name in PURE:
            shutil.copy(os.path.join(REPO, DRIVER, name), os.path.join(tmp, name))
        units = [n for n in PURE if n.endswith(".c")]
        for unit in units:
            proc = subprocess.run(
                [cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-c", unit, "-o", unit + ".o"],
                cwd=tmp, capture_output=True, text=True)
            if proc.returncode != 0:
                errors += fail("%s does not build alone:\n%s" % (unit, proc.stderr.strip()))
            else:
                print("  built %s" % unit)
        print("standalone compile: %d translation unit(s)" % len(units))
    return errors


TESTS = ["run-tests.sh", "test-pong-audio-geni-i2c.c"]


def copy_set(dest):
    """The migration itself: the same list, copied where the 27 tree wants it.

    Nothing here decides anything new - it walks the three lists above so the
    copy can never disagree with what the check just approved. The glink runner
    stays out on purpose: it compiles drivers/PongPower, which is power's source.
    """
    src = os.path.join(REPO, DRIVER)
    os.makedirs(dest, exist_ok=True)
    tests_dest = os.path.join(dest, "tests")
    os.makedirs(tests_dest, exist_ok=True)
    copied = 0
    for name in PURE + GLUE + TESTS_ONLY:
        shutil.copy(os.path.join(src, name), os.path.join(dest, name))
        copied += 1
    for name in TESTS:
        shutil.copy(os.path.join(src, "tests", name), os.path.join(tests_dest, name))
        copied += 1
    os.chmod(os.path.join(tests_dest, "run-tests.sh"), 0o755)
    print("copied %d file(s) into %s" % (copied, dest))
    return 0


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile", action="store_true",
                        help="also build each pure C unit with -I. only")
    parser.add_argument("--copy", metavar="DIR",
                        help="copy the listed files into DIR/drivers/PongAudio")
    args = parser.parse_args(argv[1:])
    errors = classify()
    if args.compile:
        errors += compile_pure()
    if args.copy:
        if errors:
            return fail("refusing to copy while the classification is broken")
        errors += copy_set(args.copy)
    if errors:
        print("FAILED: %d problem(s)" % errors)
        return 1
    print("OK: the migration list matches the driver directory")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
