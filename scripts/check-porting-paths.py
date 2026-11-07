#!/usr/bin/env python3
"""Local pre-check of porting.toml against board.toml and the repository tree.

The authoritative checker is `scripts/porting-record.py check` in the UniXNU core
repository. It needs a core checkout and a fetched tree, so this script reproduces
the parts that only depend on the device repository:

* identity: porting.toml [device] must match board.toml [board];
* sections: the thirteen required areas, allowed statuses, non-empty fields;
* evidence: kind/reference/result, plus command and a 40-character revision for
  host and device records, and references that resolve;
* components: every selected component is owned by an area;
* paths: every tracked file is claimed by at least one area path pattern, and a
  pattern in a non-planned area matches at least one tracked file;
* series: every patch listed in patches/xnu/series exists.

Usage:
    python3 scripts/check-porting-paths.py [--device DIR] [--quiet]
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tomllib

REQUIRED_AREAS = [
    "configuration",
    "firmware",
    "cpu",
    "memory",
    "storage",
    "display",
    "input",
    "gpu",
    "network",
    "audio",
    "power",
    "packaging",
    "diagnostics",
]
STATUSES = {"planned", "implemented", "host-verified", "device-verified", "not-applicable"}
EVIDENCE_KINDS = {"source", "host", "device"}
TEXT_FIELDS = ("inputs", "configuration", "procedure", "findings", "completion", "limits", "next_action")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SKIP_DIRS = {".git", "out", "__pycache__", ".cache", "node_modules"}


def split_pattern(pattern: str) -> list[str]:
    return [part for part in pattern.replace("\\", "/").split("/") if part not in ("", ".")]


def match_pattern(pattern: str, path: str) -> bool:
    """Match a repository-relative path against a `*`/`**` pattern."""
    parts = split_pattern(pattern)
    segments = split_pattern(path)
    return _match(parts, segments)


def _match(parts: list[str], segments: list[str]) -> bool:
    if not parts:
        return not segments
    head, rest = parts[0], parts[1:]
    if head == "**":
        for index in range(len(segments) + 1):
            if _match(rest, segments[index:]):
                return True
        return False
    if not segments:
        return False
    if not fnmatch.fnmatchcase(segments[0], head):
        return False
    return _match(rest, segments[1:])


def tracked_files(device: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", device, "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        files = [line.strip() for line in out.splitlines() if line.strip()]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for root, dirs, names in os.walk(device):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), device).replace(os.sep, "/")
            found.append(rel)
    return sorted(found)


def load(path: str) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def main() -> int:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=repo, help="device repository root")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args()
    device = os.path.abspath(args.device)

    errors: list[str] = []
    warnings: list[str] = []

    board = load(os.path.join(device, "board.toml"))
    record = load(os.path.join(device, "porting.toml"))

    if board.get("schema_version") != 2:
        errors.append("board.toml: schema_version must be 2")
    if record.get("schema_version") != 1:
        errors.append("porting.toml: schema_version must be 1")

    identity = record.get("device", {})
    for key in ("name", "soc", "os_profile"):
        if identity.get(key) != board.get("board", {}).get(key):
            errors.append(
                f"porting.toml: device.{key} = {identity.get(key)!r} does not match "
                f"board.toml board.{key} = {board.get('board', {}).get(key)!r}"
            )

    areas = record.get("area", [])
    seen: list[str] = []
    for area in areas:
        area_id = area.get("id", "<unnamed>")
        seen.append(area_id)
        status = area.get("status")
        if status not in STATUSES:
            errors.append(f"{area_id}: unknown status {status!r}")
        for field in TEXT_FIELDS:
            if not area.get(field):
                errors.append(f"{area_id}: {field} is empty")
        if status == "not-applicable":
            if area.get("components"):
                errors.append(f"{area_id}: not-applicable areas must not select components")
            if not area.get("limits"):
                errors.append(f"{area_id}: not-applicable areas need a scope note in limits")
        if status in {"host-verified", "device-verified"} and not area.get("evidence"):
            errors.append(f"{area_id}: {status} needs evidence")
        for item in area.get("evidence", []):
            kind = item.get("kind")
            reference = item.get("reference", "")
            if kind not in EVIDENCE_KINDS:
                errors.append(f"{area_id}: evidence kind {kind!r} is not source/host/device")
            for field in ("reference", "result"):
                if not item.get(field):
                    errors.append(f"{area_id}: evidence without {field}")
            if kind in {"host", "device"}:
                if not item.get("command"):
                    errors.append(f"{area_id}: {kind} evidence needs a command")
                revision = item.get("revision", "")
                if not SHA1.match(str(revision)):
                    errors.append(f"{area_id}: {kind} evidence needs a 40-character revision")
            if reference and not reference.startswith(("https://", "http://")):
                if not os.path.exists(os.path.join(device, reference)):
                    errors.append(f"{area_id}: evidence reference does not exist: {reference}")

    for area_id in REQUIRED_AREAS:
        if area_id not in seen:
            errors.append(f"missing required area: {area_id}")
    for area_id in seen:
        if seen.count(area_id) > 1:
            errors.append(f"duplicate area id: {area_id}")

    owned = {component for area in areas for component in area.get("components", [])}
    for component in board.get("components", {}).get("include", []):
        if component not in owned:
            errors.append(f"component {component} is selected in board.toml but no area claims it")

    files = tracked_files(device)
    patterns = [pattern for area in areas for pattern in area.get("paths", [])]
    unclaimed = [path for path in files if not any(match_pattern(p, path) for p in patterns)]
    for path in unclaimed:
        errors.append(f"no area claims tracked path: {path}")
    for area in areas:
        if area.get("status") == "planned":
            continue
        for pattern in area.get("paths", []):
            if not any(match_pattern(pattern, path) for path in files):
                warnings.append(f"{area.get('id')}: path pattern matches no tracked file: {pattern}")

    series = os.path.join(device, "patches", "xnu", "series")
    if os.path.exists(series):
        with open(series, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                entry = line.strip()
                if not entry or entry.startswith("#"):
                    continue
                target = os.path.join(os.path.dirname(series), entry)
                if not os.path.exists(target):
                    errors.append(f"patches/xnu/series:{number}: missing {entry}")
    else:
        errors.append("patches/xnu/series is missing")

    if not args.quiet:
        print(f"device: {identity.get('name')} ({device})")
        print(f"areas: {len(areas)}  statuses: {', '.join(sorted({a.get('status', '?') for a in areas}))}")
        print(f"tracked files: {len(files)}  claimed: {len(files) - len(unclaimed)}")
        print(f"components: {len(owned)}  evidence records: {sum(len(a.get('evidence', [])) for a in areas)}")
    for message in warnings:
        print(f"warning: {message}")
    for message in errors:
        print(f"error: {message}")
    if errors:
        print(f"FAILED: {len(errors)} problem(s)")
        return 1
    print("OK: porting record, components, paths, series and evidence checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
