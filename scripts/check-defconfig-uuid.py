#!/usr/bin/env python3
"""check-defconfig-uuid.py -- a defconfig may not name the memory-backed seed (P-209).

The repository ships a 32 MiB memory-backed Data seed whose APFS volume UUID is
6DCCF70A-6FD6-403E-ACED-95313CD7CBB8. The device publishes a different, real
Data volume: 1BCD69FF-24A5-48B1-94B6-8FE592B2F597. A defconfig that names the
seed UUID makes the kernel wait five seconds for a volume that will never
appear, time out, and self-panic inside the root mount:

    PONG APFS: wait for Data UUID 6DCCF70A-..., timeout=5s
    K60DATA UFS Data window not published for 6DCCF70A-...
    panic: dataerr=2 at kern_exec.c:8463        (PITFALLS.md:3811-3818)

That failure lands *before* the USB console exists (the first `K60 USBLOG` line
is printed around the same time as `K60DATA mounted`), so the whole boot leaves
zero bytes on the wire and the device autoresets back to fastboot. Measured
2026-11-15: five wifi images (mhi3, mhi4, z0, t2, c0) were all "silent" for this
single reason, and four separate theories (image size, `__TEXT` const bloat,
firmware residency, DarwinBoot pool window) were built on top of the empty log.

The check is deliberately narrow: seed UUIDs are legitimate for the trial builds
that *do* mount the seed, so a line may opt in with a comment marker:

    # SEED-UUID: intentional -- this board boots the 32 MiB OwnerData seed

Anything else fails. Unknown UUIDs are reported, not failed: this gate does not
know every volume on every board, and inventing a verdict there would be the
P-194 mistake again.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

LIVE_DATA_UUID = '1BCD69FF-24A5-48B1-94B6-8FE592B2F597'
SEED_DATA_UUID = '6DCCF70A-6FD6-403E-ACED-95313CD7CBB8'

KNOWN = {
    LIVE_DATA_UUID: 'live',
    SEED_DATA_UUID: 'seed',
}

ASSIGNMENT = re.compile(
    r'^\s*(CONFIG_XNU_OWNER_(?:DATA|CACHE)_VOLUME_UUID)\s*=\s*"?([0-9A-Fa-f-]{36})"?\s*$')
MARKER = re.compile(r'#\s*SEED-UUID:\s*intentional\b', re.IGNORECASE)
MARKER_RADIUS = 6


def normalise(value: str) -> str:
    return value.strip().strip('"').upper()


def config_files(repo: Path) -> list[Path]:
    patterns = ('configs/*defconfig', 'configs/*config', 'profiles/arch/arm64/configs/*.config')
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(repo.glob(pattern)):
            if path.is_file() and path not in found:
                found.append(path)
    return found


def scan_file(path: Path, repo: Path) -> dict:
    """Return the verdict for one config file."""
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError as error:
        return {'file': str(path), 'status': 'error', 'detail': str(error), 'hits': []}

    try:
        label = str(path.relative_to(repo))
    except ValueError:
        label = str(path)

    hits: list[dict] = []
    failures: list[str] = []
    unknowns: list[str] = []

    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line)
        if not match:
            continue
        key, value = match.group(1), normalise(match.group(2))
        kind = KNOWN.get(value, 'unknown')
        marker = None
        low = max(0, index - MARKER_RADIUS)
        high = min(len(lines), index + MARKER_RADIUS + 1)
        for probe in range(low, high):
            found = MARKER.search(lines[probe])
            if found:
                marker = lines[probe].strip()
                break
        hits.append({'line': index + 1, 'key': key, 'value': value, 'kind': kind,
                     'marker': marker})
        if kind == 'seed' and marker is None:
            failures.append(
                f'{label}:{index + 1} {key} names the memory-backed seed UUID {value}; '
                f'the device publishes {LIVE_DATA_UUID}. This self-panics during the root '
                f'mount, before the USB console exists (P-209, PITFALLS.md P-209 / 3811-3818)')
        elif kind == 'unknown':
            unknowns.append(f'{label}:{index + 1} {key} = {value} (not a known volume)')

    status = 'fail' if failures else 'ok'
    return {'file': label, 'status': status, 'hits': hits, 'failures': failures,
            'unknowns': unknowns}


def run(repo: Path | None = None) -> dict:
    repo = Path(repo) if repo is not None else REPO
    files = config_files(repo)
    results = [scan_file(path, repo) for path in files]
    failures: list[str] = []
    unknowns: list[str] = []
    for result in results:
        failures.extend(result.get('failures', []))
        if result.get('status') == 'error':
            failures.append(f"{result['file']}: {result['detail']}")
        unknowns.extend(result.get('unknowns', []))
    return {
        'files': [r['file'] for r in results],
        'hits': [hit for r in results for hit in r.get('hits', [])],
        'failures': failures,
        'unknowns': unknowns,
        'ok': not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='reject defconfigs that name the seed Data UUID (P-209)')
    parser.add_argument('--repo', default=str(REPO), help='repository root')
    parser.add_argument('--json', action='store_true', help='machine-readable result')
    args = parser.parse_args(argv)

    report = run(Path(args.repo))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f'defconfig-uuid: scanned {len(report["files"])} file(s), '
              f'{len(report["hits"])} volume assignment(s)')
        for hit in report['hits']:
            marker = ' [SEED-UUID: intentional]' if hit.get('marker') else ''
            print(f'  {hit["kind"]:7s} {hit["key"]} = {hit["value"]}{marker}')
        for note in report['unknowns']:
            print(f'  note: {note}')
        for failure in report['failures']:
            print(f'FAIL {failure}')
        if report['ok']:
            print('✅ no defconfig names the memory-backed seed Data volume')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
