#!/usr/bin/env python3
"""End-to-end self-test for the local AUTOCHECK composition.

Three synthetic captures exercise the same command a real capture will use:

  PASS     W1 Leg A/B + README, plus the synthetic console fixture with a
           correct 16-byte EFS head and the two full-block digests.
  FAIL     the same W1 capture, plus a storage-1 block shifted by 512 bytes;
           the first LE32 is therefore 0, not the expected 0x10.
  PENDING  only Leg A + README; Leg B is absent.

No adb and no real EFS image is used. The shifted block is built from the
public header constants plus zero bytes.
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


def descriptor(index=5):
    return bytes([0x40, 0x02, index, 0x01, 0x00]) + bytes(0x3B)


def shifted_block(storage):
    """A valid header at 0x200 instead of 0x000; offset 0 stays zero."""
    ref = module.EFS.REFERENCE[storage]
    header = bytearray(0x40)
    for index, word in enumerate(ref["words"]):
        struct.pack_into("<I", header, index * 4, word)
    header[0x28:0x2f] = ref["label"]
    header[0x2f] = ref["length_byte"]
    for index, word in enumerate(ref["tail"]):
        struct.pack_into("<I", header, 0x30 + index * 4, word)
    block = bytes(0x200) + bytes(header)
    return block + bytes(module.EFS.BLOCK_BYTES - len(block))


def run(args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(args)
    return code, out.getvalue()


def main():
    with tempfile.TemporaryDirectory(prefix="autocheck-e2e-") as root:
        leg_a = write(root, "device-link.txt", "0:0:0:5\n")
        leg_b = write(root, "unit-desc.bin", descriptor())
        readme = write(root, "README.txt", "serial: synthetic\nbuild: synthetic\n")
        console = os.path.join(FIXTURES, "k60-flight-pass.log")
        shifted = write(root, "sdf3-shifted.bin", shifted_block(1))

        cases = []
        code, text = run(["--leg-a", leg_a, "--leg-b", leg_b,
                          "--readme", readme, "--console", console,
                          "--require-efs-bytes"])
        cases.append(("PASS", code, text, "OVERALL: PASS", "W2 CONSOLE  PASS"))
        print("=== PASS: correct W1 legs, 16-byte head and full-block digests")
        print(text)

        code, text = run(["--leg-a", leg_a, "--leg-b", leg_b,
                          "--readme", readme, "--efs-block", "1=" + shifted])
        cases.append(("FAIL", code, text, "OVERALL: FAIL",
                      "0x00 LE32 is 0x00000000, expected 0x00000010"))
        print("=== FAIL: storage-1 block shifted by 512 bytes")
        print(text)

        code, text = run(["--leg-a", leg_a, "--readme", readme])
        cases.append(("PENDING", code, text, "OVERALL: PENDING",
                      "Leg B: unit-desc.bin"))
        print("=== PENDING: Leg B absent")
        print(text)

        failures = []
        for name, code, text, verdict, needle in cases:
            if verdict not in text or needle not in text:
                failures.append("%s: missing %r or %r" % (name, verdict, needle))
            expected = {"PASS": 0, "FAIL": 1, "PENDING": 2}[name]
            if code != expected:
                failures.append("%s: exit %d, wanted %d" % (name, code, expected))

        if failures:
            print("K60 AUTOCHECK E2E FAIL")
            for failure in failures:
                print("  - " + failure)
            return 1
        print("K60 AUTOCHECK E2E PASS three synthetic verdicts")
        return 0


if __name__ == "__main__":
    sys.exit(main())
