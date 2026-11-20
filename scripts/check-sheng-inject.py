#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check the sheng userland contract this lane's 27 plan depends on.

IOS27-USERLAND.md names facts about sheng and builds the reconnection on
them: the add-on mount patch, its source and visible point, the chain it stacks
on (add-on slot four, not a standalone patch), the plug-in that keeps its image
resident, and the media-server sandbox grant.  Those are line numbers in another
repository, so they rot silently. This script locates the required facts and
fails if one disappears; it notes an absent macOS-only grant separately.

A named tree that lacks the files is refused rather than skipped: measuring
some other checkout and calling it green is the failure this lane already hit
twice (P-251, P-256).
"""
import argparse
import os
import pathlib
import subprocess
import sys

PATCH = "patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch"

# (file, needle, what the userland plan assumes it means)
NEEDLES = [
    (PATCH, '"/private/var/ngpu/audio"', "the add-on source path"),
    (PATCH, '"/System/Library/Audio/Plug-Ins/HAL"', "the HAL mount point"),
    (PATCH, "BuiltinAudioPlugin.driver", "the reference bundle the mount copies from"),
    (PATCH, "ShengAudio.driver/Info.plist", "the visible plug-in the mount leaves behind"),
    (PATCH, "native_gpu_addon4_stage = 0", "the mount adds a fourth add-on slot"),
    (PATCH, "native_gpu_addon3_stage = 0",
     "and it stacks on the first three, so it is not a standalone patch"),
    ("hal/ShengAudioPlugIn.c", "keepImageResident", "the plug-in keeps its image resident"),
    ("package/ShengAudioService.cpp", '"audiomxd,mediaserverd"',
     "the iOS sandbox grant names the media servers"),
]

# Upstream c8f92b2 selects a different user-client sandbox grant for macOS.
# The iOS plan requires the iOS grant and the independent plug-in residency
# check, not the macOS grant. Still report the source difference.
VERSIONED = [
    ("package/ShengAudioService.cpp",
     '"coreaudiod,com.apple.audio.Core-Audio-Driver-Service.helper"',
     "the macOS branch of the same grant"),
]


def commit(root):
    done = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%h"],
                          capture_output=True, text=True)
    return done.stdout.strip() or "unknown"


def find(root, name, needle):
    path = root / name
    if not path.is_file():
        return None, "no %s in %s" % (name, root)
    text = path.read_text(errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return (name, number), None
    return None, "%s does not mention %s" % (name, needle)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheng", default=None, help="sheng checkout to read")
    args = parser.parse_args(argv[1:])

    selected = args.sheng or os.environ.get("SHENG_REPO")
    if selected:
        root = pathlib.Path(selected)
    else:
        here = pathlib.Path(__file__).resolve()
        for candidate in (pathlib.Path("/mnt/e/k60-work/UniXNU-sheng"),
                          here.parents[1].parent / "UniXNU-sheng",
                          pathlib.Path("/e/hackios/UniXNU-sheng"),
                          pathlib.Path("/mnt/e/hackios/UniXNU-sheng")):
            if (candidate / PATCH).is_file():
                root = candidate
                break
        else:
            print("sheng inject: no checkout with %s; pass --sheng" % PATCH)
            return 3

    if not (root / PATCH).is_file():
        print("sheng inject: %s has no %s; refusing to read another tree"
              % (root, PATCH))
        return 1

    places = []
    problems = []
    for name, needle, why in NEEDLES:
        where, error = find(root, name, needle)
        if where:
            places.append("%s:%d" % where)
        else:
            problems.append("%s: %s" % (error, why))
    if problems:
        for line in problems:
            print("INJECT FAILED: " + line)
        return 1

    absent = []
    for name, needle, why in VERSIONED:
        where, error = find(root, name, needle)
        if where:
            places.append("%s:%d" % where)
        else:
            absent.append("%s: %s" % (error, why))
    for line in absent:
        print("SHENG INJECT NOTE: " + line +
              "; upstream main carries it, this tree does not")

    total = len(NEEDLES) + len(VERSIONED)
    if absent:
        print("SHENG INJECT OK %d/%d invariants, %d versioned fact(s) absent (%s): %s"
              % (len(places), total, len(absent), commit(root), ", ".join(places)))
    else:
        print("SHENG INJECT OK %d/%d invariants (%s): %s"
              % (len(places), total, commit(root), ", ".join(places)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
