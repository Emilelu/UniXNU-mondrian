#!/usr/bin/env python3
"""Host-only tests for check-efs-full.py.

All blocks are synthetic. The zero 4 KiB block is the real storage-4 shape;
the storage-1 header is assembled from the public constants, with a zero data
region, so no modem identity or calibration bytes are stored here.
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
CHECKER = os.path.join(os.path.dirname(HERE), "check-efs-full.py")
spec = importlib.util.spec_from_file_location("efs_full", CHECKER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def header(storage):
    ref = module.REFERENCE[storage]
    block = bytearray(module.BLOCK_BYTES)
    for index, word in enumerate(ref["words"]):
        struct.pack_into("<I", block, index * 4, word)
    block[0x28:0x2f] = ref["label"]
    block[0x2f] = ref["length_byte"]
    for index, word in enumerate(ref["tail"]):
        struct.pack_into("<I", block, 0x30 + index * 4, word)
    return block


def write(root, name, data):
    path = os.path.join(root, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def run(name, path, storage, want, needle=None):
    verdict, fields, reasons = module.judge(path, storage)
    detail = "; ".join(reasons)
    if verdict != want:
        print("K60 EFS FULL FAIL %s: got %s, wanted %s (%s)"
              % (name, verdict, want, detail))
        return False
    if needle and needle not in detail:
        print("K60 EFS FULL FAIL %s: reason %r does not contain %r"
              % (name, detail, needle))
        return False
    return True


def cli(name, path, storage, want, extra=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(["--storage", str(storage), "--file", path] + (extra or []))
    if code != want:
        print("K60 EFS FULL FAIL %s: exit %d, wanted %d (%s)"
              % (name, code, want, out.getvalue().strip()))
        return False, out.getvalue()
    return True, out.getvalue()


def main():
    cases = []
    with tempfile.TemporaryDirectory(prefix="efs-full-") as root:
        zero = write(root, "sdf6.bin", bytes(module.BLOCK_BYTES))
        cases.append(run("storage 4 all zero", zero, 4, "PASS"))
        cases.append(cli("storage 4 cli", zero, 4, 0)[0])

        nonzero = bytearray(module.BLOCK_BYTES)
        nonzero[0] = 1
        bad4 = write(root, "sdf6-bad.bin", bytes(nonzero))
        cases.append(run("storage 4 nonzero", bad4, 4, "FAIL",
                         needle="0x00"))

        short = write(root, "short.bin", bytes(100))
        cases.append(run("short block", short, 4, "PENDING", needle="need 4096"))
        cases.append(cli("short block cli", short, 4, 2)[0])

        absent = os.path.join(root, "absent.bin")
        cases.append(run("absent block", absent, 4, "PENDING", needle="absent"))
        cases.append(cli("absent cli", absent, 4, 2)[0])

        long_block = write(root, "long.bin", bytes(module.BLOCK_BYTES + 1))
        cases.append(run("long block", long_block, 4, "FAIL", needle="exactly"))

        head_only = write(root, "sdf3-head-only.bin", bytes(header(1)))
        cases.append(run("header matches, data zero", head_only, 1, "FAIL",
                         needle="0x200..0xfff data sha256"))

        padded = bytearray(header(1))
        padded[0x40] = 1
        pad_path = write(root, "sdf3-pad.bin", bytes(padded))
        cases.append(run("padding nonzero", pad_path, 1, "FAIL",
                         needle="not all zero"))

        cases.append(cli("fail cli", head_only, 1, 1)[0])

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main(["--storage", "4", "--file", zero, "--explain"])
        text = out.getvalue()
        if code != 0 or "0x2f" not in text or "unknown" not in text:
            print("K60 EFS FULL FAIL explain output: rc=%d %r" % (code, text))
            cases.append(False)
        else:
            cases.append(True)

    if not all(cases):
        print("K60 EFS FULL FAIL %d/%d checks" % (sum(1 for c in cases if c), len(cases)))
        return 1
    print("K60 EFS FULL PASS %d host-only cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
