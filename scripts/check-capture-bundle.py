#!/usr/bin/env python3
"""Compose the W1, W2 console and W2 full-superblock judges on local files.

This is the "one command after capture" entry. It never calls adb, never
touches a device, and never writes outside a temporary directory. Inputs are
the two outputs a read-only capture already produced:

  --leg-a   the one-line /sys/class/block/<sdX>/device link (text)
  --leg-b   the UFS Unit Descriptor binary read with a UPIU QUERY REQUEST

Optional inputs add the rest of the evidence without inventing it:

  --readme  provenance text; without it W1 stays PENDING, not PASS
  --proc    /proc/scsi/scsi text
  --console a cellular flight console; W2 header judge
  --efs-block STORAGE=PATH  a full 4096-byte EFS block; repeatable

Exit codes: 0 PASS, 2 PENDING (evidence is incomplete), 1 FAIL (a captured
piece is malformed or contradicts another piece). SKIP is printed for an
optional family that was not supplied and does not change the verdict.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, filename):
    path = os.path.join(HERE, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W1 = load("w1_judge", "check-w1-lun-evidence.py")
W2 = load("w2_judge", "judge-cellular-flight.py")
EFS = load("efs_full", "check-efs-full.py")


def require(path, label):
    if path and not os.path.isfile(path):
        raise SystemExit("K60 CAPTURE BUNDLE FAIL %s not found: %s" % (label, path))


def copy(path, directory, name):
    if path:
        shutil.copyfile(path, os.path.join(directory, name))


def parse_blocks(values):
    blocks = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit("K60 CAPTURE BUNDLE FAIL --efs-block wants STORAGE=PATH: %s" % value)
        storage, path = value.split("=", 1)
        try:
            storage = int(storage)
        except ValueError:
            raise SystemExit("K60 CAPTURE BUNDLE FAIL storage is not a number: %s" % storage)
        if storage not in (1, 2, 3, 4):
            raise SystemExit("K60 CAPTURE BUNDLE FAIL storage must be 1..4: %d" % storage)
        if storage in blocks:
            raise SystemExit("K60 CAPTURE BUNDLE FAIL duplicate storage: %d" % storage)
        require(path, "--efs-block storage=%d" % storage)
        blocks[storage] = path
    return blocks


def console_summary(items):
    efs = [item for item in items if item[1].startswith("efs bytes")]
    failures = [item for item in items if item[0] == "FAIL"]
    if failures:
        return "first failure: %s: %s" % (failures[0][1], failures[0][2])
    if efs:
        item = efs[-1]
        return "%s: %s" % (item[1], item[2])
    return "no EFS sample"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Judge a read-only cellular capture from local files only")
    parser.add_argument("--leg-a", help="device-link.txt from a read-only capture")
    parser.add_argument("--leg-b", help="unit descriptor binary from a read-only capture")
    parser.add_argument("--readme", help="provenance text (serial/build/commands)")
    parser.add_argument("--proc", help="/proc/scsi/scsi text")
    parser.add_argument("--console", help="cellular flight console")
    parser.add_argument("--efs-block", action="append", metavar="STORAGE=PATH",
                        help="full 4096-byte EFS block; repeat for storages 1..4")
    parser.add_argument("--expect-lun", type=int, default=5,
                        help="W1 hypothesis; default 5")
    parser.add_argument("--require-efs-bytes", action="store_true",
                        help="require both full-block digests (4096 at offset 0 and "
                             "3584 at offset 512) for every served EFS storage")
    args = parser.parse_args(argv)

    if not 0 <= args.expect_lun <= 31:
        parser.error("--expect-lun must be 0..31")
    for path, label in ((args.leg_a, "--leg-a"), (args.leg_b, "--leg-b"),
                        (args.readme, "--readme"), (args.proc, "--proc"),
                        (args.console, "--console")):
        require(path, label)
    blocks = parse_blocks(args.efs_block)

    records = []
    with tempfile.TemporaryDirectory(prefix="k60-capture-") as work:
        copy(args.leg_a, work, "device-link.txt")
        copy(args.leg_b, work, "unit-desc.bin")
        copy(args.readme, work, "README.txt")
        copy(args.proc, work, "proc-scsi-scsi.txt")

        verdict, fields, reasons = W1.judge(work, args.expect_lun)
        detail = W1.describe(fields, args.expect_lun)
        records.append(("W1 LUN", verdict, detail, reasons))

    if args.console:
        with open(args.console, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        raw, items, observed = W2.judge(text, W2.WINDOW_DEFAULT, args.require_efs_bytes)
        verdict = {"PASS": "PASS", "FAILED": "FAIL", "INVALID": "PENDING"}[raw]
        records.append(("W2 CONSOLE", verdict,
                        "window=%ds %s" % (observed, console_summary(items)), []))

    if blocks:
        failed = []
        passed = []
        pending = []
        for storage in sorted(blocks):
            verdict, fields, reasons = EFS.judge(blocks[storage], storage)
            if verdict == "FAIL":
                failed.append("storage=%d: %s" % (storage, reasons[0]))
            elif verdict == "PENDING":
                pending.append("storage=%d: %s" % (storage, reasons[0]))
            else:
                passed.append(storage)
        missing = [str(n) for n in (1, 2, 3, 4) if n not in blocks]
        if failed:
            records.append(("W2 FULL", "FAIL", "; ".join(failed), []))
        elif pending:
            records.append(("W2 FULL", "PENDING", "; ".join(pending), []))
        elif missing:
            records.append(("W2 FULL", "PENDING",
                            "passed %s; missing storage %s" %
                            (",".join(str(n) for n in passed), ",".join(missing)), []))
        else:
            records.append(("W2 FULL", "PASS", "all four storages match", []))
    else:
        records.append(("W2 FULL", "SKIP", "no --efs-block supplied", []))

    if not args.console:
        records.append(("W2 CONSOLE", "SKIP", "no --console supplied", []))

    overall = "PASS"
    if any(record[1] == "FAIL" for record in records):
        overall = "FAIL"
    elif any(record[1] == "PENDING" for record in records):
        overall = "PENDING"

    print("K60 CAPTURE BUNDLE %s" % overall)
    for name, verdict, detail, reasons in records:
        print("  %-11s %-7s %s" % (name, verdict, detail))
        for reason in reasons:
            print("    - " + reason)
    print("OVERALL: %s" % overall)
    return {"PASS": 0, "PENDING": 2, "FAIL": 1}[overall]


if __name__ == "__main__":
    sys.exit(main())
