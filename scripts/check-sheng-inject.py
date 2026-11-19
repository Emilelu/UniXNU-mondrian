#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check the sheng userland contract this lane's 27 plan depends on.

IOS27-USERLAND.md names four facts about sheng and builds the reconnection on
them: the add-on mount patch, its source and visible point, the plug-in that
keeps its image resident, and the media-server sandbox grant.  Those are line
numbers in another repository, so they rot silently.  This script reads them
back and fails when one moves or disappears.

A named tree that lacks the files is refused rather than skipped: measuring
some other checkout and calling it green is the failure this lane already hit
twice (P-251, P-256).
"""
import argparse
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
    ("hal/ShengAudioPlugIn.c", "keepImageResident", "the plug-in keeps its image resident"),
    ("package/ShengAudioService.cpp", '"audiomxd,mediaserverd"',
     "the iOS sandbox grant names the media servers"),
    ("package/ShengAudioService.cpp", '"coreaudiod,com.apple.audio.Core-Audio-Driver-Service.helper"',
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

    if args.sheng:
        root = pathlib.Path(args.sheng)
    else:
        here = pathlib.Path(__file__).resolve()
        for candidate in (here.parents[1].parent / "UniXNU-sheng",
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

    print("SHENG INJECT OK %d/%d invariants (%s): %s"
          % (len(places), len(NEEDLES), commit(root), ", ".join(places)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
