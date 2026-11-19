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

0621's call-site hunk and 0624 are dropped from the copies because 0629 replaces
them. 0621-k60-io-submap-budget is not carried at all: the 27 io_map.c has no
io_submap or IO_MAP_SIZE (see docs/research/cellular/20-IOS27-PORT-PLAN.md).
"""

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHES = os.path.join(ROOT, "patches", "xnu")

CALL_SITE_HEADER = "@@ -7834,2 +7834,10 @@"

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
        "# born as the 16 line 0621/0624 call sites",
        "0629-kern-exec-call-sites.patch",
        "# 0621-k60-io-submap-budget is not carried: the 27 io_map.c has no io_submap",
    ]) + chr(10)


def write_port(out, tree, anchor_text):
    os.makedirs(out, exist_ok=True)
    image = read("0620-k60-modem-image.patch")
    pas = strip_call_site(read("0621-k60-modem-pas.patch"))
    targets = {"0626-k60-modem-image.patch": image + "\n" + pas,
               "0627-k60-modem-qrtr.patch": read("0622-k60-modem-qrtr.patch"),
               "0628-k60-ipa.patch": read("0623-k60-ipa.patch")}
    for name, body in targets.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as handle:
            handle.write(body)
    with open(os.path.join(out, "series-port.txt"), "w", encoding="utf-8") as handle:
        handle.write(series_fragment())
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
              "0628-k60-ipa.patch", "0629-kern-exec-call-sites.patch"]
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
        print("K60 PORT27 PASS renumbering, anchor insertion, refusal, verification, series")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", help="root of the iOS 27 XNU source tree")
    parser.add_argument("--out", help="directory to write the 27-line patches into")
    parser.add_argument("--anchor", default="native_owner_data_stage = 3;",
                        help="line in bsd/kern/kern_exec.c to insert the probes before")
    parser.add_argument("--verify", action="store_true",
                        help="run git apply --check on every produced patch")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.tree or not args.out:
        parser.error("--tree and --out are required unless --self-test")
    problem = write_port(args.out, args.tree, args.anchor)
    if problem:
        print("K60 PORT27 FAIL " + problem)
        if args.verify:
            verify(args.tree, args.out)
        return 2
    print("K60 PORT27 OK wrote 0626, 0627, 0628, 0629 and series-port.txt to " + args.out)
    if not args.verify:
        return 0
    return verify(args.tree, args.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
