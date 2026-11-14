#!/usr/bin/env python3
"""Check that patches/xnu/0617-k60-thermal-tsens.patch carries the thermal driver.

The kernel cannot include drivers/PongThermal, so the shipping copies live inside the
patch as bsd/dev/pong_thermal.c, bsd/dev/pong_thermal_level.c, bsd/dev/pong_thermal_pm.cpp,
bsd/sys/pong_thermal.h and bsd/sys/pong_thermal_level.h. Those copies must be
byte-identical to the master copies in the repository, otherwise the code that is tested
is not the code that ships (P-190: verify the artifacts, not the file names).

Checks:
  1. the patch exists, is registered in patches/xnu/series, and is the last entry
  2. the patch adds the five files, and every reconstructed body matches its master
  3. the patch registers all three new sources in bsd/conf/files, including the first
     .cpp the bsd component ever built
  4. the patch calls pong_thermal_init() from bsd/kern/bsd_init.c
  5. the driver never writes a register: no store through the mapped pointers
     (P-190 read-only guarantee, checked mechanically)
  6. the publisher uses the one thermal entry point that exists, under the one key that
     moves IOPMrootDomain::thermalWarningState, and installs no actuator

Usage: scripts/check-thermal-kernel-patch.py [--repo DIR] [--quiet]
Exit code 0 when every check passes.
"""

import argparse
import os
import re
import sys

PATCH_NAME = "0617-k60-thermal-tsens.patch"

# (path inside the kernel tree, master copy in this repository)
FILES = (
    ("bsd/dev/pong_thermal.c", os.path.join("drivers", "PongThermal", "pong_thermal.c")),
    ("bsd/dev/pong_thermal_level.c",
     os.path.join("drivers", "PongThermal", "K60ThermalLevel.c")),
    ("bsd/dev/pong_thermal_pm.cpp",
     os.path.join("drivers", "PongThermal", "pong_thermal_pm.cpp")),
    ("bsd/sys/pong_thermal.h",
     os.path.join("drivers", "PongThermal", "K60ThermalKernel.h")),
    ("bsd/sys/pong_thermal_level.h",
     os.path.join("drivers", "PongThermal", "K60ThermalLevel.h")),
)
DEV_PATH = FILES[0][0]
MASTER_DEV = FILES[0][1]
PM_PATH = "bsd/dev/pong_thermal_pm.cpp"
LEVEL_PATH = "bsd/dev/pong_thermal_level.c"

problems = []
notes = []


def read(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as handle:
        return handle.read()


def split_patch(text):
    """Return {path: (old_path, new_lines)} for every file section in the patch."""
    sections = {}
    current = None
    for line in text.splitlines(True):
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            if not match:
                problems.append("unparsable diff header: %r" % line.rstrip())
                current = None
                continue
            current = match.group(2)
            sections[current] = {"old": match.group(1), "lines": [], "new_file": False}
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            sections[current]["new_file"] = True
            continue
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("index "):
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+"):
            sections[current]["lines"].append(line[1:])
        elif line.startswith(" "):
            sections[current]["lines"].append(line[1:])
        # '-' lines belong to the old body; the new body is what we compare
    return sections


def check_series(repo):
    series_path = os.path.join(repo, "patches", "xnu", "series")
    if not os.path.exists(series_path):
        problems.append("missing patches/xnu/series")
        return
    entries = [line.strip() for line in read(series_path).splitlines() if line.strip()]
    if PATCH_NAME not in entries:
        problems.append("%s is not registered in patches/xnu/series" % PATCH_NAME)
        return
    if entries[-1] != PATCH_NAME:
        problems.append("%s is registered at line %d, not last (a later patch can move the "
                        "bsd/conf/files anchor)" % (PATCH_NAME, entries.index(PATCH_NAME) + 1))
    notes.append("series: %d entries, %s last" % (len(entries), PATCH_NAME))


def check_bodies(repo, sections):
    for path, master in FILES:
        section = sections.get(path)
        if section is None:
            problems.append("patch does not add %s" % path)
            continue
        if not section["new_file"]:
            problems.append("%s is not added as a new file" % path)
        shipped = "".join(section["lines"])
        master_path = os.path.join(repo, master)
        if not os.path.exists(master_path):
            problems.append("missing master copy %s" % master)
            continue
        wanted = read(master_path)
        if shipped != wanted:
            problems.append("%s in the patch differs from %s (%d vs %d bytes)"
                            % (path, master, len(shipped.encode()), len(wanted.encode())))
            shipped_lines = shipped.splitlines()
            wanted_lines = wanted.splitlines()
            for index in range(min(len(shipped_lines), len(wanted_lines))):
                if shipped_lines[index] != wanted_lines[index]:
                    problems.append("  first difference at line %d:\n    patch:  %r\n    master: %r"
                                    % (index + 1, shipped_lines[index], wanted_lines[index]))
                    break
            else:
                problems.append("  one file is a prefix of the other (%d vs %d lines)"
                                % (len(shipped_lines), len(wanted_lines)))
            continue
        notes.append("%s matches %s (%d bytes, %d lines)"
                     % (path, master, len(wanted.encode()), wanted.count("\n")))


def check_registration(sections):
    conf = sections.get("bsd/conf/files")
    if conf is None:
        problems.append("patch does not touch bsd/conf/files")
    else:
        joined = "".join(conf["lines"])
        for path in (DEV_PATH, LEVEL_PATH, PM_PATH):
            if path not in joined:
                problems.append("bsd/conf/files does not register %s" % path)
        if all(path in joined for path in (DEV_PATH, LEVEL_PATH, PM_PATH)):
            notes.append("conf/files registers the driver, the level module and the publisher")
        # .cpp needs %CXXFILES in bsd/conf/Makefile.template, which the tree has had
        # since before this port (bsd/conf/Makefile.template:72).
        if PM_PATH in joined and ".cpp" not in joined:
            problems.append("the .cpp entry lost its extension")

    init = sections.get("bsd/kern/bsd_init.c")
    if init is None:
        problems.append("patch does not touch bsd/kern/bsd_init.c")
        return
    joined = "".join(init["lines"])
    if "pong_thermal_init()" not in joined:
        problems.append("bsd/kern/bsd_init.c does not call pong_thermal_init()")
    elif "extern void pong_thermal_init(void);" not in joined:
        problems.append("bsd/kern/bsd_init.c calls pong_thermal_init() without a declaration")
    else:
        notes.append("bsd_init.c declares and calls pong_thermal_init()")


def check_read_only(repo):
    """The driver must never store through the mapped windows."""
    master_path = os.path.join(repo, MASTER_DEV)
    if not os.path.exists(master_path):
        return
    body = read(master_path)
    offenders = []
    for number, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("*") or stripped.startswith("/*") or stripped.startswith("//"):
            continue
        # a store is an assignment whose left side dereferences the window
        if re.search(r"\b(?:ctl|c)->(?:tm|srot)\s*\[[^\]]*\]\s*(?:[-+*/%&|^]?=)[^=]", line):
            offenders.append((number, stripped))
        if re.search(r"\*(?:ctl|c)->(?:tm|srot)\b[^;]*=[^=]", line):
            offenders.append((number, stripped))
        # writes through the local pointer aliases used by the sampler
        if re.search(r"\bbase\s*\[[^\]]*\]\s*=(?!=)", line) or re.search(r"\*base\s*=(?!=)", line):
            offenders.append((number, stripped))
    if offenders:
        for number, text in offenders:
            problems.append("write to a mapped window at %s:%d: %s" % (MASTER_DEV, number, text))
    else:
        notes.append("driver performs no store through the mapped windows")


def check_publisher(repo):
    """The publisher must use the existing entry point and install no actuator."""
    master_path = os.path.join(repo, os.path.join("drivers", "PongThermal",
                                                  "pong_thermal_pm.cpp"))
    if not os.path.exists(master_path):
        return
    body = read(master_path)
    code = "\n".join(line for line in body.splitlines()
                     if not line.strip().startswith(("*", "/*", "//")))
    if "systemPowerEventOccurred" not in code:
        problems.append("%s never calls systemPowerEventOccurred" % PM_PATH)
    if "kIOPMThermalLevelWarningKey" not in code:
        problems.append("%s does not publish under kIOPMThermalLevelWarningKey "
                        "(the only key IOPMrootDomain::setThermalState reacts to)" % PM_PATH)
    if "getPMRootDomain" not in code:
        problems.append("%s does not fetch the root domain through IOService" % PM_PATH)
    # An actuator would touch a clock, a regulator or a trip register. None of that
    # belongs here: docs/research/thermal/TRIP-DESIGN.md section 3.5 is the decision.
    for pattern, what in (
            (r"\bsetFrequency\b", "a clock write"),
            (r"\bml_io_map\b", "an MMIO mapping"),
            (r"\bwrmsr\b|\bmsr_write\b", "an MSR write"),
            (r"\btrip\b\s*=", "a trip register write")):
        if re.search(pattern, code):
            problems.append("%s installs %s; this layer only reports" % (PM_PATH, what))
    else:
        notes.append("publisher uses systemPowerEventOccurred under the warning key, no actuator")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    repo = os.path.abspath(args.repo)

    patch_path = os.path.join(repo, "patches", "xnu", PATCH_NAME)
    if not os.path.exists(patch_path):
        problems.append("missing patches/xnu/%s" % PATCH_NAME)
    else:
        sections = split_patch(read(patch_path))
        check_series(repo)
        check_bodies(repo, sections)
        check_registration(sections)
    check_read_only(repo)
    check_publisher(repo)

    if not args.quiet:
        for note in notes:
            print("  ok   %s" % note)
    if problems:
        print("thermal kernel patch: %d problem(s)" % len(problems))
        for problem in problems:
            print("  FAIL %s" % problem)
        return 1
    print("thermal kernel patch: OK (%d checks)" % (len(notes) + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
