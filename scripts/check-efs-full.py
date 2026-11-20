#!/usr/bin/env python3
"""Judge the full 4 KiB EFS superblock against an independent Android capture.

W2's 16-byte head is necessary but not sufficient. A block can match the
first 16 bytes and still carry the wrong data region, a short read, or a
different storage's window. This judge compares the complete 4096-byte
superblock against the read-only Android reference captured on 2026-11-20.

The reference values below are constants from that capture. They are not a
format specification: fields whose semantics are unknown stay named unknown,
and are only compared as opaque expected values. The raw capture is not stored
in this repository (it may contain modem identity/calibration data).

Exit codes: 0 PASS, 2 PENDING (the capture is absent or shorter than 4096),
1 FAIL (a captured block is longer than 4096, a known field differs, the
padding is non-zero, or either data/full sha256 differs).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys

BLOCK_BYTES = 4096
HEADER_WORDS = 10
TAIL_WORDS = 4
LABEL_OFFSET = 0x28
LABEL_BYTES = 7
LENGTH_OFFSET = 0x2F
PAD_OFFSET = 0x40
DATA_OFFSET = 0x200

# Android by-name: sdf3=modemst1, sdf4=modemst2, sdf5=fsg, sdf6=fsc.
# The storage number is the RMTFS /boot/modem_fsN storage, not a LUN claim.
REFERENCE = {
    1: {
        "sha256": "94c2aa725f4e8c5d3de317e8cd39f7efc1588866e7d2854011d10e4656a1a6bb",
        "data_sha256": "3cc3383e26ddccc6c173df925379e3692c817ee6a8c55ce60506eab2b33210c6",
        "words": (0x00000010, 0x00000003, 0x000001D8, 0xC4A9FA20,
                  0x0027FE00, 0x0027FE00, 0xC4D1F820, 0x00000000,
                  0xC4D1F820, 0x00000000),
        "label": b"IMGEFS1",
        "length_byte": 0x18,
        "tail": (0xEE0000CD, 0xA1F362E5, 0x00000001, 0x00000102),
    },
    2: {
        "sha256": "8610958511c22e7c44736363ac2b9c2d8e87bd16d78540fa2d4e97be1c489726",
        "data_sha256": "66df4116cab50b05d3e9a3122f19b28f9654cd3ed63d9cffc393ff37fff59183",
        "words": (0x00000011, 0x00000003, 0x000001D8, 0x80600200,
                  0x0027FE00, 0x0027FE00, 0x80880000, 0x00000000,
                  0x80880000, 0x00000000),
        "label": b"IMGEFS2",
        "length_byte": 0x17,
        "tail": (0xE40000CD, 0xA1F345D6, 0x00000001, 0x00000102),
    },
    3: {
        "sha256": "e9a62f2a22e469b8008da4dc2733148ae4abcf887c9e1277a7646123fdbc31b4",
        "data_sha256": "32efa564d9ccc53fdc201920cb30b87f7aed2bcfc79e02d643ef919f2e6e4f0c",
        "words": (0x00000014, 0x00000003, 0x000001D8, 0x00000000,
                  0x0027FE00, 0x0027FE00, 0x0027FE00, 0x00000000,
                  0x0027FE00, 0x00000000),
        "label": b"IMGEFSG",
        "length_byte": 0x12,
        "tail": (0x10000000, 0x49917432, 0x00000000, 0x00000101),
    },
    4: {
        "sha256": "ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7",
        "data_sha256": "6cf1b57d59e7111bc218dfb01dda93ac0f776715599a1c69f89035bd20c16a10",
        "words": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        "label": bytes(7),
        "length_byte": 0x00,
        "tail": (0, 0, 0, 0),
    },
}

SEMANTICS = {
    0x00: "unknown", 0x04: "unknown", 0x08: "unknown", 0x0C: "unknown",
    0x10: "unknown", 0x14: "unknown", 0x18: "unknown", 0x1C: "unknown",
    0x20: "unknown", 0x24: "unknown", 0x28: "ASCII label",
    0x2F: "unknown", 0x30: "unknown", 0x34: "unknown",
    0x38: "unknown", 0x3C: "unknown",
}


def read_block(path):
    """Return (bytes, state, detail); state is ok, absent, short or long."""
    if not os.path.isfile(path):
        return None, "absent", "file is absent"
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < BLOCK_BYTES:
        return None, "short", "file is %d bytes; need %d" % (len(data), BLOCK_BYTES)
    if len(data) > BLOCK_BYTES:
        return data, "long", "file is %d bytes; expected exactly %d" % (
            len(data), BLOCK_BYTES)
    return data, "ok", None


def judge(path, storage):
    """Return (verdict, fields, reasons). verdict is PASS, PENDING or FAIL."""
    ref = REFERENCE[storage]
    fields = {"size": 0, "sha256": None, "data_sha256": None, "words": None,
              "label": None, "length_byte": None, "tail": None,
              "pad_nonzero": None}
    data, state, detail = read_block(path)
    if state == "absent":
        return "PENDING", fields, [detail]
    if state == "short":
        return "PENDING", fields, [detail]
    if state == "long":
        fields["size"] = len(data)
        fields["sha256"] = hashlib.sha256(data[:BLOCK_BYTES]).hexdigest()
        return "FAIL", fields, [detail]

    fields["size"] = len(data)
    fields["sha256"] = hashlib.sha256(data).hexdigest()
    fields["data_sha256"] = hashlib.sha256(data[DATA_OFFSET:]).hexdigest()
    fields["words"] = tuple(struct.unpack_from("<I", data, i * 4)[0]
                            for i in range(HEADER_WORDS))
    fields["label"] = data[LABEL_OFFSET:LABEL_OFFSET + LABEL_BYTES]
    fields["length_byte"] = data[LENGTH_OFFSET]
    fields["tail"] = tuple(struct.unpack_from("<I", data, 0x30 + i * 4)[0]
                           for i in range(TAIL_WORDS))
    fields["pad_nonzero"] = sum(1 for byte in data[PAD_OFFSET:DATA_OFFSET] if byte)

    reasons = []
    for index, (actual, expected) in enumerate(zip(fields["words"], ref["words"])):
        if actual != expected:
            reasons.append("0x%02x LE32 is 0x%08x, expected 0x%08x"
                           % (index * 4, actual, expected))
    if fields["label"] != ref["label"]:
        reasons.append("0x28 label is %s, expected %s"
                       % (fields["label"].hex(), ref["label"].hex()))
    if fields["length_byte"] != ref["length_byte"]:
        reasons.append("0x2f byte is 0x%02x, expected 0x%02x"
                       % (fields["length_byte"], ref["length_byte"]))
    for index, (actual, expected) in enumerate(zip(fields["tail"], ref["tail"])):
        if actual != expected:
            reasons.append("0x%02x LE32 is 0x%08x, expected 0x%08x"
                           % (0x30 + index * 4, actual, expected))
    if fields["pad_nonzero"]:
        reasons.append("0x40..0x1ff is not all zero (%d non-zero bytes)"
                       % fields["pad_nonzero"])
    if fields["data_sha256"] != ref["data_sha256"]:
        reasons.append("0x200..0xfff data sha256 is %s, expected %s"
                       % (fields["data_sha256"], ref["data_sha256"]))
    if fields["sha256"] != ref["sha256"]:
        reasons.append("full 4096-byte sha256 is %s, expected %s"
                       % (fields["sha256"], ref["sha256"]))
    return ("FAIL" if reasons else "PASS"), fields, reasons


def explain(storage, fields):
    ref = REFERENCE[storage]
    print("offset  width  expected    actual      semantics")
    for index in range(HEADER_WORDS):
        offset = index * 4
        actual = ("0x%08x" % fields["words"][index]) if fields["words"] else "absent"
        print("0x%02x    u32    0x%08x  %-10s  %s"
              % (offset, ref["words"][index], actual,
                 SEMANTICS.get(offset, "unknown")))
    actual_label = fields["label"].hex() if fields["label"] else "absent"
    print("0x28    7 bytes  %s  %-10s  ASCII label" % (ref["label"].hex(), actual_label))
    actual_len = ("0x%02x" % fields["length_byte"]) if fields["length_byte"] is not None else "absent"
    print("0x2f    u8       0x%02x      %-10s  unknown" % (ref["length_byte"], actual_len))
    for index in range(TAIL_WORDS):
        offset = 0x30 + index * 4
        actual = ("0x%08x" % fields["tail"][index]) if fields["tail"] else "absent"
        print("0x%02x    u32    0x%08x  %-10s  unknown"
              % (offset, ref["tail"][index], actual))
    actual_pad = fields["pad_nonzero"] if fields["pad_nonzero"] is not None else "absent"
    print("0x40    448 bytes  all zero  %-10s  zero padding" % actual_pad)
    print("0x200   3584 bytes  sha256 %s  opaque QEFS block" % ref["data_sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Judge a full 4 KiB EFS superblock")
    parser.add_argument("--storage", type=int, required=True, choices=(1, 2, 3, 4))
    parser.add_argument("--file", required=True, help="4096-byte read-only capture")
    parser.add_argument("--explain", action="store_true",
                        help="print every field, expected and actual")
    args = parser.parse_args(argv)
    verdict, fields, reasons = judge(args.file, args.storage)
    if verdict == "PENDING":
        print("K60 EFS FULL PENDING storage=%d reason=%s" % (args.storage, reasons[0]))
        return 2
    print("K60 EFS FULL %s storage=%d size=%d sha256=%s data_sha256=%s"
          % (verdict, args.storage, fields["size"], fields["sha256"],
             fields["data_sha256"]))
    for reason in reasons:
        print("  - " + reason)
    if args.explain:
        explain(args.storage, fields)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
