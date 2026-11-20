#!/usr/bin/env python3
"""Judge a read-only W1 LUN capture from two independent legs.

W1 asks whether the modemst1 block device really sits on UFS LUN 5. The sd
letter, the partition name, and our own driver's chosen-LUN print are not
evidence. The two legs that can settle it are:

  A. the HCTL name of the SCSI device behind /sys/class/block/sdX/device;
     the last field is the controller LUN for a normal UFS LU;
  B. the UFS Unit Descriptor (IDN 0x02) read with a UPIU QUERY REQUEST;
     bUnitIndex must equal the HCTL LUN and bLUEnable must be 1.

The expected LUN is a hypothesis. A capture that agrees on 4 does not prove 5;
rerun with --expect-lun 4 only after adjudicating the discrepancy.

Exit codes: 0 PASS, 2 PENDING (a leg is absent or provenance is missing),
1 FAIL (a captured leg is malformed or the legs contradict).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

HCTL_RE = re.compile(r"(?:^|/)(\d+):(\d+):(\d+):(\d+)/?$")
SCSI_RE = re.compile(r"Host:\s*scsi(\d+)\s+Channel:\s*(\d+)\s+Id:\s*(\d+)\s+Lun:\s*(\d+)")
DESCRIPTOR_IDN = 0x02
LU_ENABLED = 0x01


def read_text(path):
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8", "replace")


def parse_hctl(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, "device-link.txt must hold exactly one non-empty line"
    match = HCTL_RE.search(lines[0])
    if not match:
        return None, "device-link.txt has no H:C:T:L tail: %s" % lines[0]
    return tuple(int(part) for part in match.groups()), None


# Offset provenance: 27 UEFI feed mu_basecore-8f10084c (Ufs.h:873-893) packs
# UFS_UNIT_DESC as Length/DescType/UnitIdx/LunEn/BootLunId at bytes 0..4, and
# UfsPassThru.c:996-1007 reads it with UfsUnitDesc; Linux v6.12
# (adc218676eef) ufshcd_read_desc_param() slices the same bytes in ufshcd.c:3637-3703.
# Both use single-byte fields, so the offsets need no endian conversion.
def parse_descriptor(data):
    if len(data) < 5:
        return None, "descriptor is %d bytes; need at least 5" % len(data)
    length = data[0]
    if length < 5:
        return None, "bLength %d is shorter than the five-byte header" % length
    if length > len(data):
        return None, "bLength %d exceeds the %d-byte file" % (length, len(data))
    if data[1] != DESCRIPTOR_IDN:
        return None, "bDescriptorIDN is 0x%02x, not 0x02" % data[1]
    if data[3] not in (0, 1):
        return None, "bLUEnable is 0x%02x, not 0 or 1" % data[3]
    if data[4] > 2:
        return None, "bBootLunID is 0x%02x, outside 0..2" % data[4]
    return {
        "length": length,
        "idn": data[1],
        "index": data[2],
        "enable": data[3],
        "boot_lun": data[4],
        "extra": len(data) - length,
    }, None


def descriptor_path(directory, explicit):
    if explicit:
        return explicit if os.path.isabs(explicit) else os.path.join(directory, explicit), None
    preferred = os.path.join(directory, "unit-desc.bin")
    found = sorted(glob.glob(os.path.join(directory, "unit-desc-*.bin")))
    if os.path.isfile(preferred):
        if found:
            return None, "multiple unit-desc files; pass --descriptor to choose one"
        return preferred, None
    if len(found) == 1:
        return found[0], None
    if len(found) > 1:
        return None, "multiple unit-desc-*.bin files; pass --descriptor to choose one"
    return None, "unit-desc.bin / unit-desc-*.bin is absent"


def judge(directory, expect_lun=5, descriptor=None):
    """Return (verdict, fields, reasons). verdict is PASS, PENDING or FAIL."""
    fields = {"hctl": None, "descriptor": None, "readme": False, "proc": None}
    reasons = []
    hard_fail = False

    readme = os.path.join(directory, "README.txt")
    if os.path.isfile(readme) and read_text(readme).strip():
        fields["readme"] = True
    else:
        reasons.append("README.txt is missing or empty; provenance is incomplete")

    link = os.path.join(directory, "device-link.txt")
    if not os.path.isfile(link):
        reasons.append("Leg A: device-link.txt is absent")
    else:
        hctl, error = parse_hctl(read_text(link))
        if error:
            hard_fail = True
            reasons.append("Leg A: " + error)
        else:
            fields["hctl"] = hctl

    path, error = descriptor_path(directory, descriptor)
    if error:
        reasons.append("Leg B: " + error)
        if "multiple" in error:
            hard_fail = True
    else:
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            hard_fail = True
            reasons.append("Leg B: cannot read %s: %s" % (path, exc))
        else:
            parsed, error = parse_descriptor(data)
            if error:
                hard_fail = True
                reasons.append("Leg B: " + error)
            else:
                fields["descriptor"] = parsed

    proc = os.path.join(directory, "proc-scsi-scsi.txt")
    if os.path.isfile(proc):
        entries = [tuple(int(part) for part in match.groups())
                   for match in SCSI_RE.finditer(read_text(proc))]
        fields["proc"] = entries
        if not entries:
            hard_fail = True
            reasons.append("proc-scsi-scsi.txt has no Host: ... Lun: line")
        elif fields["hctl"] and fields["hctl"] not in entries:
            hard_fail = True
            reasons.append("proc-scsi-scsi.txt does not list %s" % (fields["hctl"],))

    if hard_fail:
        return "FAIL", fields, reasons

    hctl = fields["hctl"]
    desc = fields["descriptor"]
    if hctl is None or desc is None:
        return "PENDING", fields, reasons

    if hctl[3] != expect_lun:
        return "FAIL", fields, reasons + [
            "controller LUN is %d, expected %d; update the hypothesis, do not call this PASS"
            % (hctl[3], expect_lun)
        ]
    if desc["index"] != hctl[3]:
        return "FAIL", fields, reasons + [
            "descriptor bUnitIndex %d contradicts HCTL LUN %d" % (desc["index"], hctl[3])
        ]
    if desc["enable"] != LU_ENABLED:
        return "FAIL", fields, reasons + [
            "descriptor bLUEnable is 0x%02x, not enabled" % desc["enable"]
        ]
    if not fields["readme"]:
        return "PENDING", fields, reasons
    return "PASS", fields, reasons


def describe(fields, expect_lun):
    parts = ["expect=%d" % expect_lun]
    hctl = fields["hctl"]
    parts.append("hctl=" + (("%d:%d:%d:%d" % hctl) if hctl else "absent"))
    desc = fields["descriptor"]
    if desc:
        parts.append("descriptor=index=%d enable=%d bootlun=%d" %
                     (desc["index"], desc["enable"], desc["boot_lun"]))
    else:
        parts.append("descriptor=absent")
    parts.append("readme=" + ("present" if fields["readme"] else "missing"))
    return " ".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Judge a read-only W1 UFS LUN capture")
    parser.add_argument("evidence", help="directory with device-link.txt and unit-desc*.bin")
    parser.add_argument("--expect-lun", type=int, default=5,
                        help="hypothesis to test; default 5")
    parser.add_argument("--descriptor", help="descriptor file, relative to evidence or absolute")
    args = parser.parse_args(argv)
    if not 0 <= args.expect_lun <= 31:
        parser.error("--expect-lun must be 0..31")
    if not os.path.isdir(args.evidence):
        print("K60 W1 LUN FAIL evidence directory not found: %s" % args.evidence)
        return 1
    verdict, fields, reasons = judge(args.evidence, args.expect_lun, args.descriptor)
    print("K60 W1 LUN %s %s" % (verdict, describe(fields, args.expect_lun)))
    for reason in reasons:
        print("  - " + reason)
    return {"PASS": 0, "PENDING": 2, "FAIL": 1}[verdict]


if __name__ == "__main__":
    sys.exit(main())
