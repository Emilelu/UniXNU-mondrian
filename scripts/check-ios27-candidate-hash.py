#!/usr/bin/env python3
"""Compare a prelink report's candidate hash with the final artifact bytes.

The report field is only a claim about the producer's output buffer.  This tool
binds that claim to the file that will actually be loaded.

The default is the dormant gate registered as P-294: a mismatch, a missing or
unreadable input, or a report without the field prints a NOTE and exits 0.  Only
when both inputs are missing does it exit 2.  A dormant gate must say it cannot
compare rather than pretend it passed.

--strict is the evidence mode.  It hashes the artifact, compares the named report
field and candidate_bytes when present, and fails on a missing field, an
unreadable report, an unreadable artifact or a mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_FIELD = "candidate_sha256"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def dormant(report_path: Path, artifact_path: Path, field: str) -> int:
    """Return 0 for match or any note; 2 only when both inputs are absent."""
    report_exists = report_path.exists()
    artifact_exists = artifact_path.exists()
    if not report_exists and not artifact_exists:
        print(f"NOTE candidate hash: both inputs are missing: {report_path} and {artifact_path}")
        return 2
    if not report_exists:
        print(f"NOTE candidate hash: report missing: {report_path}; cannot compare")
        return 0
    if not artifact_exists:
        print(f"NOTE candidate hash: artifact missing: {artifact_path}; cannot compare")
        return 0

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"NOTE candidate hash: report unreadable: {report_path}: {error}")
        return 0
    if not isinstance(report, dict):
        print(f"NOTE candidate hash: report is not a JSON object: {report_path}")
        return 0

    recorded = report.get(field)
    if not isinstance(recorded, str) or not recorded:
        print(f"NOTE candidate hash: report has no {field}: {report_path}")
        return 0

    try:
        actual = digest(artifact_path)
    except OSError as error:
        print(f"NOTE candidate hash: artifact unreadable: {artifact_path}: {error}")
        return 0

    print(f"report {field}: {recorded}")
    print(f"artifact sha256: {actual}")
    if recorded != actual:
        print(f"NOTE candidate hash: report {recorded} != artifact {actual}; "
              "P-294 dormant, not blocking")
        return 0
    print("ok candidate hash: dormant gate, report matches the artifact bytes")
    return 0


def strict(report_path: Path, artifact_path: Path, field: str) -> int:
    """Return 0 only when the report field and byte count match the artifact."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"FAIL report: {report_path}: {error}")
        return 1
    if not isinstance(report, dict):
        print(f"FAIL report: {report_path} does not hold a JSON object")
        return 1

    recorded = report.get(field)
    if not isinstance(recorded, str) or not recorded:
        print(f"FAIL report: {report_path} has no {field}")
        return 1

    try:
        actual = digest(artifact_path)
        size = artifact_path.stat().st_size
    except OSError as error:
        print(f"FAIL artifact: {artifact_path}: {error}")
        return 1

    print(f"report {field}: {recorded}")
    print(f"artifact sha256: {actual}")
    print(f"artifact bytes: {size}")

    failed = False
    if recorded != actual:
        print(f"FAIL candidate hash: report {recorded} != artifact {actual}")
        failed = True
    recorded_size = report.get("candidate_bytes")
    if isinstance(recorded_size, int) and recorded_size != size:
        print(f"FAIL candidate bytes: report {recorded_size} != artifact {size}")
        failed = True
    if failed:
        return 1

    print("ok candidate hash: report matches the artifact bytes")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path,
                        help="the JSON report written next to the candidate")
    parser.add_argument("--artifact", required=True, type=Path,
                        help="the final file that will be loaded")
    parser.add_argument("--field", default=DEFAULT_FIELD,
                        help=f"report field to compare (default: {DEFAULT_FIELD})")
    parser.add_argument("--strict", action="store_true",
                        help="evidence mode: any mismatch or unreadable input is a failure")
    args = parser.parse_args(argv)

    if args.strict:
        return strict(args.report, args.artifact, args.field)
    return dormant(args.report, args.artifact, args.field)


if __name__ == "__main__":
    sys.exit(main())
