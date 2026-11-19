#!/usr/bin/env python3
"""Port the cellular patch set onto the iOS 27 XNU tree.

The 16-line series carries six cellular patches. Three of them only add files and
apply unchanged to the 27 tree; two of them are the same two call sites inside
bsd/kern/kern_exec.c, which the 27 tree does not have yet because the data-mount
block they attach to is still being carried by the baseline line; and one of them
patches an io_map.c structure the 27 tree no longer has.

This tool produces the 27-line set mechanically:

  0626-k60-modem-image.patch    <- 0620, plus the three new files from 0621
  0627-k60-modem-qrtr.patch     <- 0622, unchanged
  0628-k60-ipa.patch            <- 0623, unchanged
  0629-kern-exec-call-sites.patch <- both probes, re-anchored by line
  0630-k60-smem.patch        <- the 16 line pong_smem pair from 0611, verbatim

0621's call-site hunk and 0624 are dropped from the copies because 0629 replaces
them. 0621-k60-io-submap-budget is not carried at all: the 27 io_map.c has no
io_submap or IO_MAP_SIZE (see docs/research/cellular/20-IOS27-PORT-PLAN.md).
"""

import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHES = os.path.join(ROOT, "patches", "xnu")

CALL_SITE_HEADER = "@@ -7834,2 +7834,10 @@"

# The carried modem and IPA sources include pong_smem.h, which the 16 line gets
# from 0611.  Those two files are self-contained (only their own header plus
# stdint), so the 27 line carries them verbatim instead of porting all of 0611.
# pong_pmic_rail.h is different: the carried files include it but call nothing
# from it (k60_rail_probe has no caller under drivers/PongCellular), so the
# include is dropped rather than dragging a second line's driver along.
CARRY = (("0611-k60-smem-handoff.patch", ("bsd/dev/pong_smem.h", "bsd/dev/pong_smem.c")),)
DROPPED_INCLUDE = '+#include "pong_pmic_rail.h"'


PROBES = [
    ("\t/* 0629: hand the modem carveout to the secure monitor once Data is mounted."
     "\n\t * Inert unless pong_modem is set: the probe returns on its first line without"
     "\n\t * mapping 0x8bc00000 or issuing an SMC. */"
     "\n\t{\n\t\textern int k60_modem_probe_from_handoff(void);\n\n"
     "\t\t(void)k60_modem_probe_from_handoff();\n\t}\n"),
    ("\t/* 0629: IPA firmware is independent of the modem image.  The probe is"
     "\n\t * inert unless pong_ipa is set; it reads IPA/ipa_fws.mbn from the same"
     "\n\t * payload FAT md0 and hands it to PAS 15. */"
     "\n\t{\n\t\textern int k60_ipa_probe_from_handoff(void);\n\n"
     "\t\t(void)k60_ipa_probe_from_handoff();\n\t}\n"),
]


def read(name):
    with open(os.path.join(PATCHES, name), encoding="utf-8") as handle:
        return handle.read()


def strip_call_site(text):
    """Drop the kern_exec.c hunk from 0621, keeping the new-file sections."""
    lines = text.splitlines(True)
    for index, line in enumerate(lines):
        if line.startswith(CALL_SITE_HEADER):
            kept = lines[:index]
            # The hunk's file header has to go with it: a section that keeps
            # "--- a/bsd/kern/kern_exec.c" and "+++ b/..." but no hunk
            # claims a file and applies nothing, which reads as a lying count.
            while kept and (kept[-1].startswith("+++ b/")
                            or kept[-1].startswith("--- a/")
                            or kept[-1].startswith("diff --git ")):
                kept.pop()
            while kept and kept[-1].strip() == "":
                kept.pop()
            return "".join(kept) + "\n"
    raise SystemExit("0621 no longer carries the call-site hunk; check the patch")


def build_call_sites(tree, anchor_text):
    """Insert both probes before anchor_text in the tree copy, return a unified diff."""
    path = os.path.join(tree, "bsd", "kern", "kern_exec.c")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    lines = text.splitlines(True)
    hits = [i for i, line in enumerate(lines) if line.strip() == anchor_text.strip()]
    if len(hits) != 1:
        return None, "anchor %r matches %d lines, need exactly one" % (anchor_text, len(hits))
    blocks = "".join(PROBES)
    patched = lines[:hits[0]] + blocks.splitlines(True) + lines[hits[0]:]
    diff = difflib.unified_diff(lines, patched, fromfile="a/bsd/kern/kern_exec.c",
                                tofile="b/bsd/kern/kern_exec.c", n=6)
    return "".join(diff), None


def series_fragment():
    # One path per line, comments on their own lines: both the 16-line parser
    # (patches/xnu/series via .split()) and the 27-line one (whole line = path)
    # treat anything after the name as part of the filename.
    return chr(10).join([
        "# iOS 27 line: ported from 16 line 0620..0623, call sites merged into 0629",
        "# born as 16 line 0620 plus the 0621 file sections",
        "0626-k60-modem-image.patch",
        "# born as 16 line 0622",
        "0627-k60-modem-qrtr.patch",
        "# born as 16 line 0623",
        "0628-k60-ipa.patch",
        "# born as 16 line 0611: pong_smem only, nothing calls k60_rail_probe",
        "0630-k60-smem.patch",
        "# born as the 16 line 0621/0624 call sites",
        "0629-kern-exec-call-sites.patch",
        "# 0621-k60-io-submap-budget is not carried: the 27 io_map.c has no io_submap",
    ]) + chr(10)


def conf_entries(patch_paths):
    """Sources the patches install, in bsd/conf/files spelling.

    The patches only add files under bsd/dev; nothing in them teaches the build
    tree to compile those files (16 line: scripts/append-conffiles.py, P-171).
    """
    names = set()
    for path in patch_paths:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("+++ b/"):
                    name = line[6:].strip()
                    if name.startswith("bsd/dev/") and name.endswith(".c"):
                        names.add(name)
    return [name + chr(9) * 3 + "standard" for name in sorted(names)]


def carry_sections(name, targets):
    """The named file sections of a 16-line patch, byte for byte."""
    text = read(name)
    chunks, current, keep = [], None, False
    for line in text.splitlines(True):
        if line.startswith("diff --git "):
            if current is not None and keep:
                chunks.append(current)
            current, keep = line, False
        elif current is not None:
            current += line
            if line.startswith("+++ b/"):
                keep = line[6:].strip() in targets
    if current is not None and keep:
        chunks.append(current)
    found = set()
    for chunk in chunks:
        for field in chunk.splitlines():
            if field.startswith("+++ b/"):
                found.add(field[6:].strip())
    missing = [t for t in targets if t not in found]
    if missing:
        raise SystemExit("%s no longer carries %s" % (name, " ".join(missing)))
    return "".join(chunks)


def drop_include(text):
    """Remove an added include line and keep the hunk's counts honest.

    Deleting a '+' line without touching the header is exactly the corrupt patch
    the first version of this function produced, so the counts are recounted
    from the body instead of assumed."""
    out, header, body = [], None, []

    def flush():
        if header is None:
            return
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", header)
        if not match:
            out.append(header + chr(10))
            out.extend(body)
            return
        added = sum(1 for line in body if line.startswith("+"))
        removed = sum(1 for line in body if line.startswith("-"))
        context = sum(1 for line in body if line.startswith(" ") or line.strip() == "")
        out.append("@@ -%s,%d +%s,%d @@%s%s" % (match.group(1), removed + context,
                                                 match.group(3), added + context,
                                                 match.group(5), chr(10)))
        out.extend(body)

    for line in text.splitlines(True):
        if line.startswith("@@ "):
            flush()
            header, body = line.rstrip(chr(10)), []
        elif header is not None and line.startswith(DROPPED_INCLUDE):
            continue
        elif header is not None and line.startswith(("diff --git ", "+++ b/", "--- a/")):
            flush()
            header, body = None, []
            out.append(line)
        elif header is not None:
            body.append(line)
        else:
            out.append(line)
    flush()
    return "".join(out)


ANCHOR_MARKERS = (("native_owner_data_stage",),
                  ("native_owner_data_prepare", 'vnode_lookup("/private/var"'))


def find_anchor(tree):
    """Return the line that stages the Data mount, once the 27 tree has one."""
    path = os.path.join(tree, "bsd", "kern", "kern_exec.c")
    if not os.path.exists(path):
        return None, "no bsd/kern/kern_exec.c under " + tree
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for markers in ANCHOR_MARKERS:
        hits = [line.strip() for line in lines
                if any(marker in line for marker in markers) and line.strip().endswith(";")]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, "anchor is ambiguous, %d candidates: %s" % (len(hits), " | ".join(hits))
    return None, "no line stages the Data mount yet; pass --anchor with the line text"


def write_port(out, tree, anchor_text):
    os.makedirs(out, exist_ok=True)
    image = read("0620-k60-modem-image.patch")
    pas = strip_call_site(read("0621-k60-modem-pas.patch"))
    carried = "".join(carry_sections(name, files) for name, files in CARRY)
    targets = {"0626-k60-modem-image.patch": image + "\n" + pas,
               "0627-k60-modem-qrtr.patch": drop_include(read("0622-k60-modem-qrtr.patch")),
               "0628-k60-ipa.patch": drop_include(read("0623-k60-ipa.patch")),
               "0630-k60-smem.patch": carried}
    for name, body in targets.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as handle:
            handle.write(body)
    with open(os.path.join(out, "series-port.txt"), "w", encoding="utf-8") as handle:
        handle.write(series_fragment())
    with open(os.path.join(out, "conffiles-port.txt"), "w", encoding="utf-8") as handle:
        handle.write(chr(10).join(conf_entries([
            os.path.join(out, name) for name in (
                "0626-k60-modem-image.patch",
                "0627-k60-modem-qrtr.patch",
                "0628-k60-ipa.patch",
                "0630-k60-smem.patch",
            )
        ])) + chr(10))
    call_sites, problem = build_call_sites(tree, anchor_text)
    if call_sites is None:
        return problem
    with open(os.path.join(out, "0629-kern-exec-call-sites.patch"), "w",
              encoding="utf-8") as handle:
        handle.write(call_sites)
    return None


def verify(tree, out):
    """Run git apply --check for every patch that was produced."""
    wanted = ["0626-k60-modem-image.patch", "0627-k60-modem-qrtr.patch",
              "0628-k60-ipa.patch", "0629-kern-exec-call-sites.patch",
              "0630-k60-smem.patch"]
    seen = 0
    for name in wanted:
        path = os.path.join(out, name)
        if not os.path.exists(path):
            print("K60 PORT27 VERIFY %s skipped (not produced)" % name[:4])
            continue
        result = subprocess.run(["git", "-C", tree, "apply", "--check", path],
                                capture_output=True, text=True)
        seen += 1
        if result.returncode != 0:
            print("K60 PORT27 VERIFY %s FAILED: %s"
                  % (name[:4], (result.stderr or result.stdout).strip()))
            return 1
        print("K60 PORT27 VERIFY %s ok" % name[:4])
    if not seen:
        print("K60 PORT27 VERIFY nothing to check in " + out)
        return 1
    return 0

def self_test():
    """Build a throwaway tree, port into it, and prove the call-site patch applies."""
    work = tempfile.mkdtemp(prefix="k60-port27-")
    try:
        os.makedirs(os.path.join(work, "bsd", "kern"))
        body = "int exec_check(void)\n{\n\tint err = 0;\n" \
               "\tnative_owner_data_stage = 3;\n" \
               "\terr = vnode_lookup(\"/private/var\", 0, &root, ctx);\n" \
               "\treturn err;\n}\n"
        with open(os.path.join(work, "bsd", "kern", "kern_exec.c"), "w",
                  encoding="utf-8") as handle:
            handle.write(body)
        out = os.path.join(work, "out")
        problem = write_port(out, work, "native_owner_data_stage = 3;")
        if problem:
            print("K60 PORT27 FAIL " + problem)
            return 1
        missing = write_port(os.path.join(work, "empty"), work, "no_such_anchor;")
        if not missing or "matches 0 lines" not in missing:
            print("K60 PORT27 FAIL a missing anchor was not refused: %r" % (missing,))
            return 1
        found, problem = find_anchor(work)
        if found != "native_owner_data_stage = 3;" or problem:
            print("K60 PORT27 FAIL auto anchor did not find the staging line: %r %r" % (found, problem))
            return 1
        twice = os.path.join(work, "dup")
        os.makedirs(os.path.join(twice, "bsd", "kern"))
        with open(os.path.join(twice, "bsd", "kern", "kern_exec.c"), "w",
                  encoding="utf-8") as handle:
            handle.write("\tnative_owner_data_stage = 2;\n\tnative_owner_data_stage = 3;\n")
        found, problem = find_anchor(twice)
        if found is not None or "ambiguous" not in (problem or ""):
            print("K60 PORT27 FAIL two staging lines were not refused: %r %r" % (found, problem))
            return 1
        bare = os.path.join(work, "bare")
        os.makedirs(os.path.join(bare, "bsd", "kern"))
        with open(os.path.join(bare, "bsd", "kern", "kern_exec.c"), "w",
                  encoding="utf-8") as handle:
            handle.write("int exec_check(void) { return 0; }\n")
        found, problem = find_anchor(bare)
        if found is not None or "no line stages" not in (problem or ""):
            print("K60 PORT27 FAIL a tree without the staging line was not refused: %r %r" % (found, problem))
            return 1
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=work)
        result = subprocess.run(
            ["git", "apply", "--check",
             os.path.join(out, "0629-kern-exec-call-sites.patch")],
            cwd=work, capture_output=True, text=True, env=env,
            input=None)
        if result.returncode != 0:
            print("K60 PORT27 FAIL generated patch does not apply: " + result.stderr.strip())
            return 1
        if verify(work, out) != 0:
            print("K60 PORT27 FAIL verify disagreed with the generated patches")
            return 1
        entries = [line for line in series_fragment().splitlines()
                   if line and not line.startswith("#")]
        broken = [line for line in entries
                  if " " in line or not line.endswith(".patch")]
        if not entries or broken:
            print("K60 PORT27 FAIL series lines must be bare patch names: %r" % (broken,))
            return 1
        build = open(os.path.join(out, "conffiles-port.txt"),
                     encoding="utf-8").read().splitlines()
        names = [line.split(chr(9))[0] for line in build]
        stray = [line for line in build
                 if not line.endswith(chr(9) * 3 + "standard")
                 or not line.startswith("bsd/dev/")
                 or not line.split(chr(9))[0].endswith(".c")]
        if (not build or len(set(build)) != len(build) or stray
                or "bsd/dev/pong_modem_link.c" not in names):
            print("K60 PORT27 FAIL build list is not one source per line: %r" % (stray,))
            return 1
        print("K60 PORT27 PASS renumbering, anchor insertion, auto anchor, refusal, "
              "verification, series, build list")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", help="root of the iOS 27 XNU source tree")
    parser.add_argument("--out", help="directory to write the 27-line patches into")
    parser.add_argument("--anchor", default="native_owner_data_stage = 3;",
                        help="line in bsd/kern/kern_exec.c to insert the probes before")
    parser.add_argument("--anchor-auto", action="store_true",
                        help="find the Data-mount line in the tree instead of taking --anchor")
    parser.add_argument("--verify", action="store_true",
                        help="run git apply --check on every produced patch")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.tree or not args.out:
        parser.error("--tree and --out are required unless --self-test")
    anchor = args.anchor
    if args.anchor_auto:
        anchor, problem = find_anchor(args.tree)
        if problem:
            print("K60 PORT27 FAIL " + problem)
            return 2
        print("K60 PORT27 anchor " + anchor)
    problem = write_port(args.out, args.tree, anchor)
    if problem:
        print("K60 PORT27 FAIL " + problem)
        if args.verify:
            verify(args.tree, args.out)
        return 2
    print("K60 PORT27 OK wrote 0626..0630 and series-port.txt to " + args.out)
    if not args.verify:
        return 0
    return verify(args.tree, args.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
