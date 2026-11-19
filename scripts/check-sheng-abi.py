#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Hold sheng's audio ABI to the constants this lane plans against.

IOS27-USERLAND.md describes what the plug-in and the kernel service agree on,
and every number in it comes from sheng's package/ShengAudioAbi.h. That header
has moved twice already (a68ee4e -> c8f92b2 for unrelated work), and a silent
change of one selector would send the 27 port after the wrong call for a day.
So the numbers live here as expectations, the header is the input, and a drift
is named:

  python3 scripts/check-sheng-abi.py [--sheng PATH]

The comparison is on whitespace-normalised text, so reformatting is fine and a
changed value is not.
"""
import argparse
import hashlib
import os
import pathlib
import subprocess
import sys

EXPECTED = [
    ("class name", '#define SHENG_AUDIO_CLASS "ShengAudio"'),
    ("magic", "#define SHENG_AUDIO_MAGIC 0x53484155u"),
    ("version", "#define SHENG_AUDIO_VERSION 1u"),
    ("rate", "#define SHENG_AUDIO_RATE 48000u"),
    ("output channels", "#define SHENG_AUDIO_OUT_CHANNELS 2u"),
    ("input channels", "#define SHENG_AUDIO_IN_CHANNELS 1u"),
    ("period frames", "#define SHENG_AUDIO_PERIOD_FRAMES 480u"),
    ("ring frames", "#define SHENG_AUDIO_RING_FRAMES 65536u"),
    ("memory types", "ShengAudioMemoryControl = 0, ShengAudioMemoryOutput = 1, ShengAudioMemoryInput = 2"),
    ("direction selectors", "ShengAudioStartOutput = 0, ShengAudioStopOutput = 1, "
                            "ShengAudioStartInput = 2, ShengAudioStopInput = 3"),
    ("host clock selector", "ShengAudioSetHostClock = 4"),
    ("running bits", "ShengAudioOutputRunning = 1u << 0, ShengAudioInputRunning = 1u << 1, "
                     "ShengAudioOutputReady = 1u << 2, ShengAudioInputReady = 1u << 3"),
    ("diagnostics offset", "#define SHENG_AUDIO_DIAG_OFFSET 2048u"),
    ("diagnostics slots", "#define SHENG_AUDIO_DIAG_SLOTS 32u"),
    ("trace offset", "#define SHENG_AUDIO_TRACE_OFFSET 2560u"),
    ("trace slots", "#define SHENG_AUDIO_TRACE_SLOTS 128u"),
]
HEADER = "package/ShengAudioAbi.h"


def find(explicit):
    """The sheng checkout to read, or None: the flag, SHENG_REPO, then siblings.

    A named checkout that lacks the header is an error, not a reason to read the
    next candidate: measuring a different tree is how a green line lies.
    """
    named = explicit or os.environ.get("SHENG_REPO") or ""
    if named:
        root = pathlib.Path(named)
        return root if (root / HEADER).is_file() else None
    candidates = []
    here = pathlib.Path(__file__).resolve().parent.parent
    candidates += [str(here.parent / "UniXNU-sheng"), "/e/hackios/UniXNU-sheng",
                   "/mnt/e/hackios/UniXNU-sheng"]
    for candidate in candidates:
        root = pathlib.Path(candidate)
        if (root / HEADER).is_file():
            return root
    return None


def commit(root):
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              check=False)
        text = done.stdout.decode("utf-8", "replace").strip()
        return text or "unknown"
    except OSError:
        return "unknown"


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheng", default=None)
    args = parser.parse_args(argv[1:])

    root = find(args.sheng)
    if root is None:
        named = args.sheng or os.environ.get("SHENG_REPO") or ""
        if named:
            print("sheng abi: %s has no %s; refusing to read another tree"
                  % (named, HEADER))
        else:
            print("sheng abi: no checkout with %s (pass --sheng or set SHENG_REPO)" % HEADER)
        return 1
    header = root / HEADER
    raw = header.read_bytes()
    dead = " ".join(raw.decode("utf-8", "replace").split())

    lines = raw.decode("utf-8", "replace").count(chr(10))
    print("sheng abi: %s %d lines sha256 %s"
          % (header, lines, hashlib.sha256(raw).hexdigest()[:12]))
    print("sheng abi: commit %s" % commit(root))

    changed = [name for name, snippet in EXPECTED if snippet not in dead]
    if changed:
        print("SHENG ABI FAILED: %d of %d constants changed: %s"
              % (len(changed), len(EXPECTED), ", ".join(changed)))
        return 1
    print("SHENG ABI OK %d/%d constants (%s)"
          % (len(EXPECTED), len(EXPECTED), commit(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
