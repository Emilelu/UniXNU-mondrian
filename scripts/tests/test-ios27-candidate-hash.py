#!/usr/bin/env python3
"""Tests for check-ios27-candidate-hash.py.

The point of the tool is to make the report-to-file binding fail loudly.  The
fixtures therefore cover the three ways the binding can be absent or wrong:
a missing report field, a mismatched digest, and a mismatched byte count.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-ios27-candidate-hash.py"
CASES = []


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def write_report(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def run(args, tmp):
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, text=True, encoding="utf-8", cwd=tmp)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="candidate-hash-"))
    data = b"build-20 candidate bytes"
    artifact = tmp / "kernel.macho"
    artifact.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()

    report = tmp / "kernel.json"
    write_report(report, {"candidate_sha256": digest, "candidate_bytes": len(data)})
    args = ["--report", str(report), "--artifact", str(artifact)]

    done = run(args, tmp)
    case("the matching report is accepted", done.returncode == 0, done.stdout)
    case("the tool names the match", "ok candidate hash" in done.stdout, done.stdout)

    write_report(report, {"candidate_sha256": "0" * 64, "candidate_bytes": len(data)})
    done = run(args, tmp)
    case("a different digest is red", done.returncode == 1, done.stdout)
    case("the digest mismatch is named", "FAIL candidate hash" in done.stdout, done.stdout)

    write_report(report, {"candidate_bytes": len(data)})
    done = run(args, tmp)
    case("a report without the field is red",
         done.returncode == 1 and "has no candidate_sha256" in done.stdout, done.stdout)

    write_report(report, {"candidate_sha256": digest, "candidate_bytes": len(data) + 1})
    done = run(args, tmp)
    case("a different byte count is red",
         done.returncode == 1 and "FAIL candidate bytes" in done.stdout, done.stdout)

    report.write_text("{not json", encoding="utf-8")
    done = run(args, tmp)
    case("a malformed report is red",
         done.returncode == 1 and "FAIL report" in done.stdout, done.stdout)

    missing = tmp / "missing.bin"
    write_report(report, {"candidate_sha256": digest})
    done = run(["--report", str(report), "--artifact", str(missing)], tmp)
    case("a missing artifact is red",
         done.returncode == 1 and "FAIL artifact" in done.stdout, done.stdout)

    failed = [name for name, ok, _ in CASES if not ok]
    for name, ok, detail in CASES:
        if not ok:
            print(f"FAIL {name}")
            if detail:
                print(f"     {detail[:400]}")
    if failed:
        print(f"TESTS FAILED {len(failed)} of {len(CASES)} case(s)")
        return 1
    print(f"TESTS OK {len(CASES)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
