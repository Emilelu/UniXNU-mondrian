#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Install the audio glue into a seeded XNU tree and list it in conf/files.

The 27 migration is three edits: copy the sources, list them in bsd/conf/files,
and compile them with XNU_PONG_AUDIO. The first two are file edits, and they
are the two that a human forgets in the middle of a build, so they live here and
run in one order that cannot half-apply silently:

  python3 scripts/apply-audio27-wiring.py --check <tree>          # report only
  python3 scripts/apply-audio27-wiring.py <tree> --anchor LINE    # 27 tree
  python3 scripts/apply-audio27-wiring.py <tree>                  # 16 series

<tree> is either the repository the builder seeds (kernel sources under
<tree>/.cache/xnu-work) or an iOS 27 output tree that builds in place; bsd/conf/files
in whichever one holds bsd/ is what the build reads. The
third edit is not a file edit - it is one make variable in the builder call
environment. The builder resets its EXTRA_MAKE_ARGS array at :166, so the same
name there is dropped; see test-audio27-define.py. This script prints that
line instead of touching the builder, which is a
framework copy (scripts/refresh-xnu-generic.py rewrites the whole file).

A fourth edit decides whether any of this runs: the glue is called once from
bsd/kern/bsd_init.c, the way the 16 series patch does it. That file is not ours,
so the step is opt-in (--hook-init) and prints the line it anchored on, because
"hooked in the wrong place" and "not hooked" read the same in a log otherwise
(P-171). Without it the glue compiles in and never runs.

Only what the kernel build needs is copied: the two sources and the headers
they include, transitively. PongAudioAfe.h is deliberately not among them - it
is the 16 series AFE endpoint, this firmware has no AFE service, and it travels
only with the host tests.

The verdict is a count, like the conf/files appender it calls: the number of
files in place and the number of conf/files lines naming them.
"""
import argparse
import pathlib
import re
import shutil
import subprocess
import sys

SOURCES = ("PongAudioAmp.c", "PongAudioGeniI2c.c")
INCLUDE = re.compile(r'#include\s+"(Pong[^"]+)"')
BUILDER_LINE = ("PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1 "
                "bash scripts/build-xnu-generic.sh")
INIT_FILE = "bsd/kern/bsd_init.c"
INIT_ANCHOR = '\tbsd_init_kprintf("calling vfsinit\\n");\n'
INIT_BLOCK = (
    "#if 1\n"
    "\t/*\n"
    "\t * K60 audio amplifier probe: the AW88261 answers a chip-id read over\n"
    "\t * AP-owned GENI I2C without the DSP. The switch is the boot argument\n"
    "\t * pong_audio_probe=1, read inside the probe; it is deliberately not\n"
    "\t * #if defined(XNU_PONG_AUDIO), because that macro reaches\n"
    "\t * PongAudioAmp.o only and would compile this call out. Ported from\n"
    "\t * the 16 line series, patches/audio/0001:3508-3522.\n"
    "\t */\n"
    "\t{\n"
    "\t\textern int pong_audio_amp_probe(void) __attribute__((weak));\n"
    "\n"
    "\t\tif (pong_audio_amp_probe != NULL) {\n"
    "\t\t\t(void)pong_audio_amp_probe();\n"
    "\t\t}\n"
    "\t}\n"
    "#endif\n"
)
CALL = "pong_audio_amp_probe()"


def resolve_tree(tree):
    """The directory holding bsd/: a seeded repo, or the XNU sources in place."""
    for root in (tree / ".cache/xnu-work", tree):
        if (root / "bsd/dev").is_dir():
            return root
    return None


def kernel_set(src):
    """The sources plus every Pong header they reach, transitively."""
    seen = []
    stack = list(SOURCES)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        path = src / name
        if not path.is_file():
            raise SystemExit("audio wiring: %s is missing from %s" % (name, src))
        seen.append(name)
        if name.endswith((".c", ".h")):
            stack.extend(INCLUDE.findall(path.read_text(errors="replace")))
    return sorted(seen)


def install(files, src, dest_dir, check):
    added = refreshed = current = 0
    for name in files:
        source = (src / name).read_bytes()
        dest = dest_dir / name
        if not dest.is_file():
            added += 1
        elif dest.read_bytes() != source:
            refreshed += 1
        else:
            current += 1
            continue
        if not check:
            shutil.copyfile(src / name, dest)
    return added, refreshed, current


def hook_init(work, check, anchor=INIT_ANCHOR):
    """Call the probe once from bsd_init, and say which line that was."""
    path = work / INIT_FILE
    if not path.is_file():
        print("audio wiring: no %s under %s; nothing to hook" % (INIT_FILE, work))
        return 1
    text = path.read_text(errors="replace")
    if not anchor.endswith("\n"):
        # a caller pasting the line out of the file loses its newline; without
        # this the block lands after the semicolon instead of on its own line
        anchor += "\n"
    calls = text.count(CALL)
    if calls:
        print("audio wiring: bsd_init already hooked (probe calls %d)" % calls)
        return 0
    if anchor not in text:
        print("audio wiring: init anchor %r missing, bsd_init not hooked" % anchor)
        print("audio wiring: pass --init-anchor with a line this tree has")
        return 1
    print("audio wiring: init anchor line %r" % anchor)
    if check:
        print("audio wiring: bsd_init probe calls %d (check mode: would be 1)"
              % calls)
        return 0
    path.write_text(text.replace(anchor, anchor + INIT_BLOCK, 1))
    after = path.read_text(errors="replace").count(CALL)
    print("audio wiring: bsd_init probe calls %d -> %d" % (calls, after))
    if after != 1:
        print("audio wiring: the hook did not land exactly once")
        return 1
    return 0


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("tree")
    parser.add_argument("--check", action="store_true",
                        help="report what is missing; write nothing")
    parser.add_argument("--anchor", default=None,
                        help="conf/files line to list the entries after")
    parser.add_argument("--hook-init", action="store_true",
                        help="also call the probe once from bsd/kern/bsd_init.c")
    parser.add_argument("--init-anchor", default=INIT_ANCHOR,
                        help="bsd_init.c line to put the call after")
    args = parser.parse_args(argv[1:])

    repo = pathlib.Path(__file__).resolve().parents[1]
    src = repo / "drivers/PongAudio"
    tree = pathlib.Path(args.tree)
    work = resolve_tree(tree)
    if work is None:
        print("audio wiring: no bsd/dev under %s (neither .cache/xnu-work nor "
              "the tree itself; tree not seeded)" % tree)
        print("audio wiring: run the builder's fetch step first, or point at "
              "the XNU sources themselves")
        return 1

    files = kernel_set(src)
    added, refreshed, current = install(files, src, work / "bsd/dev", args.check)
    print("audio wiring: sources %d (added %d, refreshed %d, current %d)"
          % (len(files), added, refreshed, current))

    command = [sys.executable, str(repo / "scripts/add-audio-conffiles.py"),
               str(tree)]
    if args.anchor:
        command += ["--anchor", args.anchor]
    if args.check:
        command.append("--check")
    code = subprocess.call(command)
    if code != 0:
        print("audio wiring: conf/files did not take the entries; the sources "
              "are in place, so rerun with --anchor once")
        return code

    hooked = 0
    if args.hook_init:
        code = hook_init(work, args.check, args.init_anchor)
        if code != 0:
            print("audio wiring: the sources are in place and listed; only the "
                  "bsd_init call is missing")
            return code
        hooked = 0 if args.check else 1
    else:
        print("audio wiring: bsd_init not hooked (pass --hook-init); the glue "
              "compiles in and never runs")

    print("audio wiring: next, build with the macro on that one object only")
    print("audio wiring: " + BUILDER_LINE)
    print("audio wiring: then read the object: sh scripts/tests/portability/"
          "run-symbols.sh --object <PongAudioAmp.o> --expect on")
    print("audio wiring: OK sources=%d conf=2 init=%d" % (len(files), hooked))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
