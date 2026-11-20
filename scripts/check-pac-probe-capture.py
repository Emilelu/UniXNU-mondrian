#!/usr/bin/env python3
"""Check that a PAC-probe capture contains every contracted line.

This is the executable form of docs/research/charger/ARM64E-PROBE.md section 9.
It does not decide whether the SoC supports PAC, and it does not turn a missing
line into "hardware does not support PAuth". It answers three questions:

  * was the probe in the image and did it start with the image hash and cpus=8?
  * did every P0-P4 step print its begin/end and per-core rows?
  * did the capture finish with a done line?

The verdict is PASS, INVALID or INCOMPLETE. A missing row is INCOMPLETE, never
"unsupported"; a missing start line, a hash mismatch, a wrong cpu count or a
wrong probe version is INVALID. PASS means only that the capture contract is
complete, not that any PAC experiment passed.

Usage:
  python3 scripts/check-pac-probe-capture.py --image kernel.macho
  python3 scripts/check-pac-probe-capture.py --image kernel.macho --log console.log

Without --log it checks only that the image carries the start format string; the
P0-P4 rows need the capture and a missing one is INCOMPLETE.

Exit codes: 0 PASS, 1 INCOMPLETE, 2 INVALID, 3 usage/read error.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

START = re.compile(r"probe v(?P<version>\d+) start image_sha256=(?P<sha>[0-9a-fA-F]{64}) cpus=(?P<cpus>\d+)")
DONE = re.compile(r"done\b")
EXPECTED_CPUS = 8
EXPECTED_VERSION = 3
P1_KEYS = ("APIA", "APIB", "APDA", "APDB", "APGA")


def payload(line):
    index = line.find("K60PAC:")
    if index < 0:
        return None
    return line[index + len("K60PAC:"):].strip()


def fields(text):
    values = dict(re.findall(r"([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)", text))
    if "core" in values and "cpu" not in values:
        values["cpu"] = values["core"]
    return values


def has_fields(row, names):
    return all(name in row for name in names)


def evaluate(lines, image_sha256, probe_version=EXPECTED_VERSION):
    """Return (verdict, missing, details) for one capture."""
    payloads = [value for value in (payload(line) for line in lines) if value]
    missing = []
    details = {}

    if not payloads:
        return "INVALID", ["no K60PAC line in the capture"], details

    first = payloads[0]
    start = START.search(first)
    if not start:
        return "INVALID", ["first K60PAC line is not the start line: %s" % first], details

    version = int(start.group("version"))
    cpus = int(start.group("cpus"))
    sha = start.group("sha").lower()
    details.update(version=version, cpus=cpus, image_sha256=sha, start=first)

    starts = [value for value in payloads if START.search(value)]
    if len(starts) != 1:
        missing.append("exactly one start line (found %d)" % len(starts))
    if version != probe_version:
        missing.append("probe version v%d (expected v%d)" % (version, probe_version))
    if cpus != EXPECTED_CPUS:
        missing.append("cpus=%d (expected %d)" % (cpus, EXPECTED_CPUS))
    if sha != image_sha256.lower():
        missing.append("image_sha256=%s does not match the image %s" % (sha, image_sha256.lower()))
    if missing:
        return "INVALID", missing, details

    def require(condition, label):
        if not condition:
            missing.append(label)

    for step in ("P0", "P1", "P2", "P3", "P4"):
        require(any(value.startswith(step + " begin") for value in payloads), step + " begin")
        require(any(value.startswith(step + " end") for value in payloads), step + " end")

    p0 = {}
    for value in payloads:
        if not value.startswith("P0 core="):
            continue
        row = fields(value)
        try:
            cpu = int(row.get("cpu", "-1"))
        except ValueError:
            cpu = -1
        p0.setdefault(cpu, []).append(row)
    for cpu in range(EXPECTED_CPUS):
        rows = p0.get(cpu, [])
        require(len(rows) == 1, "P0 core=%d line" % cpu)
        if rows:
            for name in ("mpidr", "midr", "isar1", "isar2", "apa", "api", "gpa", "gpi", "verdict"):
                require(name in rows[0], "P0 core=%d %s=" % (cpu, name))
    mpidrs = [rows[0].get("mpidr") for rows in p0.values() if rows]
    require(len(mpidrs) == EXPECTED_CPUS and len(set(mpidrs)) == EXPECTED_CPUS,
            "P0 eight distinct mpidr= values")

    p1 = {}
    for value in payloads:
        if not value.startswith("P1 core="):
            continue
        row = fields(value)
        try:
            cpu = int(row.get("cpu", "-1"))
        except ValueError:
            cpu = -1
        key = row.get("key")
        if key:
            p1[(cpu, key)] = row
        if "EnIA" in row:
            p1.setdefault(("sctlr", cpu), row)
    for cpu in range(EXPECTED_CPUS):
        for key in P1_KEYS:
            row = p1.get((cpu, key))
            require(row is not None, "P1 %s core=%d line" % (key, cpu))
            if row is not None:
                for name in ("write", "read", "verdict"):
                    require(name in row, "P1 %s core=%d %s=" % (key, cpu, name))
        row = p1.get(("sctlr", cpu))
        require(row is not None, "P1 SCTLR core=%d line" % cpu)
        if row is not None:
            for name in ("EnIA", "EnIB", "EnDA", "EnDB"):
                require(name in row, "P1 SCTLR core=%d %s=" % (cpu, name))

    p2 = {}
    for value in payloads:
        if not value.startswith("P2 core="):
            continue
        row = fields(value)
        try:
            cpu = int(row.get("cpu", "-1"))
        except ValueError:
            cpu = -1
        p2[(cpu, row.get("el"))] = row
    for cpu in range(EXPECTED_CPUS):
        for el in ("1", "0"):
            row = p2.get((cpu, el))
            require(row is not None, "P2 core=%d el=%s line" % (cpu, el))
            if row is not None:
                for name in ("p", "s", "autia", "ec", "verdict"):
                    require(name in row, "P2 core=%d el=%s %s=" % (cpu, el, name))
    require(any("cross-key" in value and "ec=" in value for value in payloads), "P2 cross-key ec= line")

    require(any(value.startswith("P3") and has_fields(fields(value), ("page", "repo", "commit"))
                for value in payloads), "P3 page=/repo=/commit= line")
    for stage in ("pmap", "user"):
        require(any(value.startswith("P4 stage=%s" % stage)
                    and has_fields(fields(value), ("tcr", "tg0", "tg1"))
                    for value in payloads), "P4 stage=%s tcr=/tg0=/tg1= line" % stage)

    done = [value for value in payloads if DONE.search(value)]
    require(len(done) == 1, "exactly one done line (found %d)" % len(done))
    if done:
        for step in ("P0", "P1", "P2", "P3", "P4"):
            require(step + "=" in done[0], "done %s= final verdict" % step)

    for value in payloads:
        if re.search(r"\b(exception|trap)\b", value, re.I) and "EC=" not in value and "ec=" not in value:
            missing.append("exception line without EC=: %s" % value)

    if missing:
        return "INCOMPLETE", missing, details
    return "PASS", [], details


def preflight(path, probe_version=EXPECTED_VERSION):
    """Check the image alone for the start format string."""
    needle = ("K60PAC: probe v%d start" % probe_version).encode()
    data = pathlib.Path(path).read_bytes()
    if needle in data:
        return "PASS", [], {"bytes": len(data), "format": needle.decode()}
    return "INVALID", ["start format string %r" % needle.decode()], {"bytes": len(data)}


def image_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", required=True, help="the file whose sha256 is in the start line")
    parser.add_argument("--log", default=None, help="serial capture text; omit for image-only preflight")
    parser.add_argument("--probe-version", type=int, default=EXPECTED_VERSION)
    parser.add_argument("--sha256", default=None, help="use this hash instead of hashing --image")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.log:
            lines = pathlib.Path(args.log).read_text(encoding="utf-8", errors="replace").splitlines()
            sha = args.sha256 or image_sha256(args.image)
            verdict, missing, details = evaluate(lines, sha, args.probe_version)
        else:
            verdict, missing, details = preflight(args.image, args.probe_version)
    except OSError as error:
        print("PAC-CAPTURE: INVALID")
        print("missing: cannot read image/log: %s" % error)
        return 3
    if args.json:
        print(json.dumps({"verdict": verdict, "missing": missing, "details": details}, ensure_ascii=False, sort_keys=True))
    else:
        print("PAC-CAPTURE: %s" % verdict)
        if details.get("start"):
            print("start: v%d cpus=%d image_sha256=%s" % (details["version"], details["cpus"], details["image_sha256"]))
        elif details:
            if details.get("format"):
                print("image: %d bytes, format string present" % details["bytes"])
            else:
                print("image: %d bytes" % details["bytes"])
        if missing:
            print("missing: %s" % ", ".join(missing))
        else:
            print("missing: none")
    return {"PASS": 0, "INCOMPLETE": 1, "INVALID": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
