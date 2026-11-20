#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Prove that a built iOS 27 kernel (or any object) really carries the audio code.

A green build is not evidence. The glue compiles to nothing when the driver
macro never reaches the compile, and on 27 that failure has no log line until
F4 - the stage-0 kernel stops long before any audio call. So the verdict here is
taken from the product, the bytes of the file:

  python3 scripts/check-audio27-kernel.py <kernel.macho | PongAudioAmp.o>

Symbols are read with nm and compared without the Mach-O leading underscore. A
kernel whose symbols cannot be read (stripped) still has its strings checked and
says so on its own line, so the verdict never silently drops half the evidence.
"""
import hashlib
import pathlib
import subprocess
import sys

STRINGS = [
    ("boot argument", b"pong_audio_probe"),
    ("probe start", b"amp probe start"),
    ("probe done", b"amp probe done found="),
]
SYMBOLS = ["pong_audio_amp_probe", "pong_audio_amp_play", "pong_audio_amp_stop"]


def symbols(path):
    """The global symbols of the file, or (None, reason) when unreadable.

    GNU nm cannot read Mach-O at all, so the LLVM one is tried first; the reason
    travels with the answer, because "stripped" and "wrong tool" look alike.
    """
    reason = "no nm found"
    for tool in ("llvm-nm-18", "llvm-nm", "nm"):
        try:
            done = subprocess.run([tool, "-g", str(path)], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, check=False)
        except OSError as error:
            reason = "%s: %s" % (tool, error.strerror)
            continue
        text = done.stdout.decode("utf-8", "replace")
        if text.strip():
            break
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        reason = "%s: %s" % (tool, lines[0] if lines else "no symbols")
    else:
        return None, reason
    if not text.strip():
        return None, reason
    names = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            names.add(parts[2].lstrip("_"))
    return names, reason


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    if len(argv) != 2:
        print("usage: check-audio27-kernel.py <kernel or object>")
        return 2
    path = pathlib.Path(argv[1])
    if not path.is_file():
        print("audio27 kernel: no such file: %s" % path)
        return 1

    data = path.read_bytes()
    print("audio27 kernel: %s %s B sha256 %s"
          % (path.name, format(len(data), ","),
             hashlib.sha256(data).hexdigest()[:12]))

    absent = [name for name, needle in STRINGS if needle not in data]
    print("audio27 kernel: strings %d/%d (%s)"
          % (len(STRINGS) - len(absent), len(STRINGS),
             ", ".join(name for name, _ in STRINGS)))

    names, reason = symbols(path)
    if names is None:
        print("audio27 kernel: symbols unreadable (%s); the strings decide" % reason)
        missing = []
    else:
        missing = [name for name in SYMBOLS if name not in names]
        print("audio27 kernel: symbols %d/%d (%s)"
              % (len(SYMBOLS) - len(missing), len(SYMBOLS), ", ".join(SYMBOLS)))

    if absent or missing:
        if absent:
            print("AUDIO27 FAILED: strings absent: %s" % ", ".join(absent))
        if missing:
            print("AUDIO27 FAILED: symbols absent: %s" % ", ".join(missing))
        return 1
    print("AUDIO27 OK %s" % path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
