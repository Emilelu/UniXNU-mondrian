#!/usr/bin/env python3
"""Stage the pinned K60 Bluetooth firmware under the Data addon prefix."""
import argparse
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
PREFIX = 'firmware/qca'
NAME = re.compile(r'hpbtfw[0-9a-f]{2}\.tlv|hpnv[0-9a-f]{2}g?\.(bin|b[0-9a-f]{2,4})')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--source', type=Path, default=root / 'firmware/bluetooth/qca')
parser.add_argument('--manifest', type=Path, default=root / 'firmware/bluetooth/manifest.json')
args = parser.parse_args()
manifest = json.loads(args.manifest.read_text())
staged = {}
for name, expected in manifest['files'].items():
    if not NAME.fullmatch(name):
        raise SystemExit('Unsupported Bluetooth firmware name: ' + name)
    source = args.source / name
    data = source.read_bytes()
    if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
        raise SystemExit('Bluetooth firmware identity mismatch: ' + name)
    staged[name] = data
destination = args.output.resolve() / PREFIX
destination.mkdir(parents=True, exist_ok=True)
for name, data in staged.items():
    (destination / name).write_bytes(data)
report = dict(staged=True, firmware_prefix=PREFIX, files=manifest['files'],
              commit=manifest.get('commit', ''), hardware_verified=False)
(args.output / 'bluetooth-firmware.json').write_text(json.dumps(report, indent=2) + '\n')
print('Staged Bluetooth firmware: ' + str(destination))
