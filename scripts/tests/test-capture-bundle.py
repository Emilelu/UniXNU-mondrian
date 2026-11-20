#!/usr/bin/env python3
"""Host-only tests for check-capture-bundle.py.

All inputs are synthetic; the only zero block is the real storage-4 shape.
No adb, device, or modem data is used.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.join(os.path.dirname(HERE), "check-capture-bundle.py")
FIXTURES = os.path.join(HERE, "fixtures")
spec = importlib.util.spec_from_file_location("capture_bundle", BUNDLE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write(root, name, data):
    path = os.path.join(root, name)
    with open(path, "wb") as handle:
        handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def descriptor(index=5, enable=1):
    return bytes([0x40, 0x02, index, enable, 0x00]) + bytes(0x3B)


def header_only(storage):
    ref = module.EFS.REFERENCE[storage]
    block = bytearray(module.EFS.BLOCK_BYTES)
    for index, word in enumerate(ref["words"]):
        struct.pack_into("<I", block, index * 4, word)
    block[0x28:0x2f] = ref["label"]
    block[0x2f] = ref["length_byte"]
    for index, word in enumerate(ref["tail"]):
        struct.pack_into("<I", block, 0x30 + index * 4, word)
    return bytes(block)


def run(root, extra, want, needle=None):
    args = ["--leg-a", os.path.join(root, "device-link.txt"),
            "--leg-b", os.path.join(root, "unit-desc.bin")]
    args.extend(extra)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(args)
    text = out.getvalue()
    if code != want:
        print("K60 CAPTURE BUNDLE FAIL exit %d wanted %d:\n%s" % (code, want, text))
        return False
    if needle and needle not in text:
        print("K60 CAPTURE BUNDLE FAIL missing %r:\n%s" % (needle, text))
        return False
    return True


def main():
    cases = []
    with tempfile.TemporaryDirectory(prefix="capture-bundle-") as root:
        write(root, "device-link.txt", "0:0:0:5\n")
        write(root, "unit-desc.bin", descriptor())
        write(root, "README.txt", "serial: synthetic\nbuild: synthetic\n")
        zero = write(root, "sdf6.bin", bytes(module.EFS.BLOCK_BYTES))
        console = os.path.join(FIXTURES, "k60-flight-pass.log")
        badhead = os.path.join(FIXTURES, "k60-flight-badhead.log")
        nohead = os.path.join(FIXTURES, "k60-flight-nohead.log")

        cases.append(run(root, ["--readme", os.path.join(root, "README.txt")], 0,
                         "K60 CAPTURE BUNDLE PASS"))
        cases.append(run(root, [], 2, "W1 LUN      PENDING"))
        cases.append(run(root, ["--readme", os.path.join(root, "README.txt"),
                                "--console", console], 0, "W2 CONSOLE  PASS"))
        cases.append(run(root, ["--readme", os.path.join(root, "README.txt"),
                                "--console", badhead], 1, "W2 CONSOLE  FAIL"))
        cases.append(run(root, ["--readme", os.path.join(root, "README.txt"),
                                "--console", nohead, "--require-efs-bytes"], 1,
                         "W2 CONSOLE  FAIL"))
        cases.append(run(root, ["--readme", os.path.join(root, "README.txt"),
                                "--efs-block", "4=" + zero], 2,
                         "W2 FULL     PENDING"))
        bad1 = write(root, "sdf3-head-only.bin", header_only(1))
        cases.append(run(root, ["--readme", os.path.join(root, "README.txt"),
                                "--efs-block", "1=" + bad1], 1,
                         "W2 FULL     FAIL"))

        write(root, "unit-desc.bin", descriptor(index=4))
        cases.append(run(root, ["--readme", os.path.join(root, "README.txt")], 1,
                         "W1 LUN      FAIL"))

    if not all(cases):
        print("K60 CAPTURE BUNDLE FAIL %d/%d cases" % (sum(1 for c in cases if c), len(cases)))
        return 1
    print("K60 CAPTURE BUNDLE PASS %d host-only cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
