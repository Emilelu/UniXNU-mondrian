#!/usr/bin/env python3
"""Host-only tests for check-w1-lun-evidence.py.

The capture values are synthetic. No device was read and no LUN is claimed.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE = os.path.join(os.path.dirname(HERE), "check-w1-lun-evidence.py")
spec = importlib.util.spec_from_file_location("w1_judge", JUDGE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def descriptor(index=5, enable=1, idn=2, boot=0, length=0x40):
    body = bytes([length, idn, index, enable, boot])
    return body + bytes(max(0, length - len(body)))


def write(root, name, data):
    path = os.path.join(root, name)
    with open(path, "wb") as handle:
        handle.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def capture(root, hctl="0:0:0:5", desc=descriptor(), readme=True,
            descriptor_name="unit-desc.bin", extra=None):
    if hctl is not None:
        write(root, "device-link.txt", "/sys/devices/platform/soc/1d84000.ufshc/host0/"
              "target0:0:0/%s\n" % hctl)
    if desc is not None:
        write(root, descriptor_name, desc)
    if readme:
        write(root, "README.txt", "serial: synthetic\nbuild: synthetic\ncommands: test\n")
    for name, data in (extra or {}).items():
        write(root, name, data)


def run(name, root, want, expect=5, descriptor_file=None, needle=None):
    verdict, fields, reasons = module.judge(root, expect, descriptor_file)
    detail = "; ".join(reasons)
    if verdict != want:
        print("K60 W1 LUN FAIL %s: got %s, wanted %s (%s)" % (name, verdict, want, detail))
        return False
    if needle and needle not in detail:
        print("K60 W1 LUN FAIL %s: reason %r does not contain %r" % (name, detail, needle))
        return False
    return True


def cli(name, root, want, extra=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main([root] + (extra or []))
    if code != want:
        print("K60 W1 LUN FAIL %s: exit %d, wanted %d (%s)" %
              (name, code, want, out.getvalue().strip()))
        return False
    return True


def main():
    cases = []
    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root)
        cases.append(run("both legs agree", root, "PASS"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=None)
        cases.append(run("no descriptor", root, "PENDING", needle="unit-desc"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, hctl=None)
        cases.append(run("no hctl", root, "PENDING", needle="device-link"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=descriptor(index=4))
        cases.append(run("descriptor contradiction", root, "FAIL", needle="contradicts"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, hctl="0:0:0:4", desc=descriptor(index=4))
        cases.append(run("hypothesis still 5", root, "FAIL", needle="expected 5"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=descriptor(enable=0))
        cases.append(run("disabled lu", root, "FAIL", needle="not enabled"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=descriptor(idn=3))
        cases.append(run("wrong idn", root, "FAIL", needle="0x02"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=bytes([0x02, 0x02, 0x05, 0x01]))
        cases.append(run("short descriptor", root, "FAIL", needle="at least 5"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root)
        write(root, "device-link.txt", "not a path\n")
        cases.append(run("malformed hctl", root, "FAIL", needle="H:C:T:L"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, extra={"proc-scsi-scsi.txt": "Host: scsi0 Channel: 00 Id: 00 Lun: 04\n"})
        cases.append(run("proc contradiction", root, "FAIL", needle="does not list"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=descriptor(boot=1))
        cases.append(run("boot lun id is not the index", root, "PASS"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, readme=False)
        cases.append(run("missing provenance", root, "PENDING", needle="README"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, descriptor_name="unit-desc-5.bin")
        cases.append(run("named descriptor", root, "PASS"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root)
        write(root, "unit-desc-5.bin", descriptor())
        cases.append(run("ambiguous descriptor", root, "FAIL", needle="multiple"))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, hctl="0:0:0:4", desc=descriptor(index=4))
        cases.append(run("hypothesis can change", root, "PASS", expect=4))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root)
        cases.append(cli("cli pass", root, 0))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=None)
        cases.append(cli("cli pending", root, 2))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, desc=descriptor(index=4))
        cases.append(cli("cli fail", root, 1))

    with tempfile.TemporaryDirectory(prefix="w1-lun-") as root:
        capture(root, hctl="0:0:0:4", desc=descriptor(index=4))
        cases.append(cli("cli changed hypothesis", root, 0, ["--expect-lun", "4"]))

    cases.append(cli("cli missing directory", "/nonexistent/w1-lun", 1))

    if not all(cases):
        return 1
    print("K60 W1 LUN PASS %d host-only cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
