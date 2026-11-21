#!/usr/bin/env python3
"""Compare a prelink report's candidate hash with the final artifact bytes.

The report field is only a claim about the producer's output buffer.  This
tool binds that claim to the file that will actually be loaded: it hashes the
artifact with SHA-256 and compares the result with the named report field.
A missing field, an unreadable report, an unreadable artifact or a mismatch is
a failure.  The candidate_bytes field is checked too when the report carries it.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path,
                        help="the JSON report written next to the candidate")
    parser.add_argument("--artifact", required=True, type=Path,
                        help="the final file that will be loaded")
    parser.add_argument("--field", default=DEFAULT_FIELD,
                        help=f"report field to compare (default: {DEFAULT_FIELD})")
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"FAIL report: {args.report}: {error}")
        return 1
    if not isinstance(report, dict):
        print(f"FAIL report: {args.report} does not hold a JSON object")
        return 1

    recorded = report.get(args.field)
    if not isinstance(recorded, str) or not recorded:
        print(f"FAIL report: {args.report} has no {args.field}")
        return 1

    try:
        actual = digest(args.artifact)
        size = args.artifact.stat().st_size
    except OSError as error:
        print(f"FAIL artifact: {args.artifact}: {error}")
        return 1

    print(f"report {args.field}: {recorded}")
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


if __name__ == "__main__":
    sys.exit(main())
