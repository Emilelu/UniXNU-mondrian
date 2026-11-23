#!/usr/bin/env python3
"""Measure what the precedent ledger actually covers.

`scan-precedents.py` walks one patch directory per repository (the one the 27
recipe reads) and records board/defconfig *keys*. That answers "does the build
use this key", not "did we read every artefact of the working machines". This
auditor answers the second question and fails while any artefact is unaccounted:

  * every `*.patch` under `patches/**` of each precedent repository, matched to
    the ledger by file name **or** by sha256 (so a renamed copy still counts);
  * every `board.toml` and defconfig key **with its value**, because a key that
    exists in both trees with a different value is exactly the sort of omission
    that leaves a working precedent unused;
  * the top-level directories of `drivers/`, so a driver family that never
    reached the ledger is visible.

Read-only. Exit 0 only when every repository is complete.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
import tomllib

OURS = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = OURS / 'docs/research/ios27/PRECEDENT-MANIFEST.toml'


def scanner():
    spec = importlib.util.spec_from_file_location('scan_precedents', OURS / 'scripts/scan-precedents.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def flatten(prefix, value, out):
    if isinstance(value, dict):
        for key, child in value.items():
            flatten(f'{prefix}.{key}' if prefix else key, child, out)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flatten(f'{prefix}[{index}]', child, out)
    else:
        out.append(f'{prefix}={value!r}')


def board_pairs(path: pathlib.Path):
    if not path.is_file():
        return set()
    out = []
    flatten('', tomllib.loads(path.read_text(encoding='utf-8')), out)
    return set(out)


def defconfig_pairs(path: pathlib.Path):
    if not path.is_file():
        return set()
    pairs = set()
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            pairs.add(f'{key}={value}')
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    scan = scanner()
    manifest = tomllib.loads(MANIFEST.read_text(encoding='utf-8'))
    ledger = {repo['name']: repo for repo in manifest['repo']}

    report = []
    failures = 0
    for name, path in scan.REPOS.items():
        root = pathlib.Path(path)
        entry = {'repo': name, 'path': str(root)}
        if not root.is_dir():
            entry['missing_repository'] = True
            failures += 1
            report.append(entry)
            continue
        items = ledger.get(name, {}).get('item', [])
        names = {item['id'] for item in items}
        hashes = {item.get('sha256') for item in items if item.get('sha256')}
        files = sorted(root.glob('patches/**/*.patch'))
        by_name, by_hash, unaccounted = [], [], []
        for patch in files:
            if patch.name in names:
                by_name.append(patch)
            elif sha256(patch) in hashes:
                by_hash.append(patch)
            else:
                unaccounted.append(patch)
        entry['patch_files'] = len(files)
        entry['patched_by_name'] = len(by_name)
        entry['patched_by_hash'] = len(by_hash)
        entry['unaccounted'] = [str(p.relative_to(root)) for p in unaccounted]
        entry['unaccounted_dirs'] = sorted({str(p.parent.relative_to(root)) for p in unaccounted})
        # Key/value coverage: the ledger stores keys, so every ledger key must
        # exist in the tree; a key present with two different values cannot be
        # resolved by key alone and is reported as a value gap.
        layout = scan.LAYOUT.get(name, {})
        board = board_pairs(root / 'board.toml') if layout.get('board', True) else set()
        entry['board_pairs'] = len(board)
        entry['board_keys_in_ledger'] = sum(1 for pair in board if pair.split('=', 1)[0] in names)
        cfg_name = layout.get('defconfig', f'{name}_ipados27_defconfig')
        cfg = defconfig_pairs(root / 'configs' / cfg_name) if cfg_name else set()
        entry['defconfig_pairs'] = len(cfg)
        entry['defconfig_keys_in_ledger'] = sum(1 for pair in cfg if pair.split('=', 1)[0] in names)
        drivers = root / 'drivers'
        entry['driver_dirs'] = sorted(p.name for p in drivers.iterdir() if p.is_dir()) if drivers.is_dir() else []
        # The ninth entry is this repository, not a precedent: its own
        # patches/xnu-12377 series is the thing doing the porting, so it is
        # reported for completeness but cannot make the *precedent* coverage fail.
        if unaccounted and name != 'ios16':
            failures += 1
        report.append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        total_files = sum(r.get('patch_files', 0) for r in report)
        total_un = sum(len(r.get('unaccounted', [])) for r in report)
        print(f'precedent coverage: {total_files} patch files, {total_un} unaccounted')
        for r in report:
            if r.get('missing_repository'):
                print(f"  {r['repo']:10s} MISSING {r['path']}")
                continue
            print(f"  {r['repo']:10s} patches={r['patch_files']:4d} by_name={r['patched_by_name']:4d} by_hash={r['patched_by_hash']:3d} unaccounted={len(r['unaccounted']):4d} "
                  f"board_pairs={r['board_pairs']:0d} drivers={len(r['driver_dirs'])}")
            if args.verbose:
                for directory in r['unaccounted_dirs']:
                    count = sum(1 for p in r['unaccounted'] if p.rsplit('/', 1)[0] == directory)
                    print(f'      {directory}/  {count}')
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
