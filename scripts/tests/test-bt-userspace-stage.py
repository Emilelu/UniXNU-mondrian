#!/usr/bin/env python3
"""The Bluetooth userspace stager keeps the framework's addon contract."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'scripts/build-bluetooth-userspace.py'
STAGE = ROOT / 'scripts/stage-bluetooth-firmware.py'
CASES = 0
FAILURES = []


def check(ok, message):
    global CASES
    CASES += 1
    if not ok:
        FAILURES.append(message)


def make_component(tmp):
    component = Path(tmp) / 'component'
    (component / 'include').mkdir(parents=True)
    (component / 'tools').mkdir()
    (component / 'include/qbt.h').write_text('/* stub */\n')
    (component / 'tools/build-userland.py').write_text('''import hashlib, json, sys
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
for name in ('bin', 'lib', 'config'):
    (out / name).mkdir(exist_ok=True)
files = {}
for name in ('bin/BlueTool', 'lib/QcaBTType0.dylib', 'config/com.apple.BlueTool.plist'):
    (out / name).write_text(name + '\\n')
    files[name] = {'sha256': hashlib.sha256((out / name).read_bytes()).hexdigest()}
(out / 'report.json').write_text(json.dumps(dict(
    built=True, target='ios27', hardware_verified=False,
    native_input_sha256='f' * 64, files=files)))
''')
    return component


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)],
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    component = make_component(tmp)
    os_root = Path(tmp) / 'os-root'
    (os_root / 'usr/sbin').mkdir(parents=True)
    (os_root / 'usr/sbin/bluetoothd').write_bytes(b'stand-in daemon')
    out = Path(tmp) / 'out'
    result = run(BUILD, out, 'ios27', '--os-root', os_root, '--component', component)
    check(result.returncode == 0, 'the wrapper stages a report: ' + result.stderr[-300:])
    report = json.loads((out / 'report.json').read_text())
    check(report.get('directories', {}).get('bluetooth-bin') == 'userland/bin',
          'the report maps the binary directory')
    check(report['directories'].get('firmware/qca') == 'firmware/qca',
          'the report maps the firmware directory')
    check(report.get('native_input_sha256') == 'f' * 64, 'the native identity is carried')
    marker = (out / 'userland/bin/QcaBluetooth.runtime')
    check(marker.is_file(), 'the runtime marker is written')
    expected = dict(native_input_sha256='f' * 64,
                    files={name: item['sha256'] for name, item in report['files'].items()})
    check(marker.read_text() == json.dumps(expected, sort_keys=True) + '\n',
          'the marker lists the staged files')
    check(report['runtime_marker_sha256'] == hashlib.sha256(marker.read_bytes()).hexdigest(),
          'the report pins the marker hash')
    firmware = json.loads((out / 'bluetooth-firmware.json').read_text())
    check(firmware['firmware_prefix'] == 'firmware/qca', 'the firmware prefix is fixed')
    check((out / 'firmware/qca/hpbtfw21.tlv').stat().st_size == 146068,
          'the firmware files are staged')

    # A corrupted input must be rejected instead of staged.
    bad_source = Path(tmp) / 'bad-source'
    shutil.copytree(ROOT / 'firmware/bluetooth/qca', bad_source)
    target = bad_source / 'hpbtfw21.tlv'
    target.write_bytes(target.read_bytes()[:-1] + b'\x00')
    result = run(STAGE, Path(tmp) / 'bad-out', '--source', bad_source)
    check(result.returncode != 0, 'a corrupted firmware file is rejected')
    check('identity mismatch' in result.stdout + result.stderr,
          'the rejection names the identity check')

    # An unexpected firmware name must not be staged.
    manifest = json.loads((ROOT / 'firmware/bluetooth/manifest.json').read_text())
    manifest['files']['evil.bin'] = {'bytes': 1, 'sha256': '0' * 64}
    bad_manifest = Path(tmp) / 'manifest.json'
    bad_manifest.write_text(json.dumps(manifest))
    result = run(STAGE, Path(tmp) / 'bad-name-out', '--manifest', bad_manifest)
    check(result.returncode != 0, 'an unexpected firmware name is rejected')

print('TESTS OK %d case(s), %d failure(s)' % (CASES, len(FAILURES)))
for failure in FAILURES:
    print('FAIL ' + failure)
sys.exit(1 if FAILURES else 0)
