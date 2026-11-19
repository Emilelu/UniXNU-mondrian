#!/usr/bin/env python3
"""Tests for scripts/check-bluetooth-payload-host.py."""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHECK = ROOT / 'scripts' / 'check-bluetooth-payload-host.py'
FRAMEWORK = '''def bundle_cdhash(path, options=()):
    detail = subprocess.run(['codesign', '--display', '--verbose=4', *options, str(path)],
                            check=True, capture_output=True, text=True).stderr
    match = re.search(r'^CDHash=([0-9a-f]{40})$', detail, re.M)


def os_mount(image, work):
    info = plistlib.loads(subprocess.check_output(['hdiutil', 'info', '-plist']))
'''
passed = failed = 0


def case(name, want, args, board=None, framework=None, codesign=None, work=None):
    global passed, failed
    board = board if board is not None else ''
    (work / 'board.toml').write_text(board)
    if framework is not None:
        (work / 'build-boot-runtime.py').write_text(framework)
    command = [sys.executable, str(CHECK), '--board', str(work / 'board.toml'),
               '--framework', str(work / 'build-boot-runtime.py')]
    if codesign is not None:
        command += ['--codesign', str(codesign)]
    command += args
    done = subprocess.run(command, capture_output=True, text=True)
    text = done.stdout + done.stderr
    ok = all(item in text for item in want) if isinstance(want, (list, tuple)) else want in text
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL ' + name)
        print('  want: ' + repr(want))
        print('  got:  ' + text.strip())


def shim(path, body):
    path.write_text('#!/bin/sh\n' + body + '\n')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def main():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        good = shim(work / 'codesign-ok', 'echo "CDHash=0123456789abcdef0123456789abcdef01234567" >&2')
        blind = shim(work / 'codesign-blind', 'exit 0')
        hdiutil = work / 'hdiutil'
        hdiutil.write_text('#!/bin/sh\nexit 0\n')
        hdiutil.chmod(0o755)
        probe = work / 'probe'
        probe.write_bytes(b'\xcf\xfa\xed\xfe' + b'\x00' * 28)
        block = '[payload.runtime]\nbluetooth_tool = "scripts/build-bluetooth-userspace.py"\nbluetooth_target = "ios27"\n'

        case('an empty board has no runtime block', 'absent', ['--hdiutil', ''],
             framework=FRAMEWORK, codesign=blind, work=work)
        case('--require-runtime fails without the block', 'is not enabled', ['--require-runtime', '--hdiutil', ''],
             framework=FRAMEWORK, codesign=blind, work=work)
        case('a full block reports the tool and the target',
             'with bluetooth_tool scripts/build-bluetooth-userspace.py -> ios27',
             ['--hdiutil', ''], board=block, framework=FRAMEWORK, codesign=blind, work=work)
        case('a block without bluetooth_tool is a failure',
             'has no bluetooth_tool', ['--hdiutil', ''],
             board='[payload.runtime]\nbluetooth_target = "ios27"\n',
             framework=FRAMEWORK, codesign=blind, work=work)
        case('--require fails on a block without bluetooth_tool', 'FAIL',
             ['--require', '--hdiutil', ''],
             board='[payload.runtime]\nbluetooth_target = "ios27"\n',
             framework=FRAMEWORK, codesign=blind, work=work)
        case('a framework that does not mount through hdiutil is a failure',
             'does not mount the OS image through hdiutil', ['--hdiutil', ''],
             framework='def os_mount(image, work):\n    pass\n', codesign=blind, work=work)
        case('a framework that reads no CDHash is a failure',
             'does not read a CDHash', ['--hdiutil', ''],
             framework='def os_mount(image, work):\n    pass\n', codesign=blind, work=work)
        case('a missing hdiutil is named', 'hdiutil is not on this host', ['--hdiutil', ''],
             framework=FRAMEWORK, codesign=blind, work=work)
        case('a blind codesign is named', 'codesign printed no CDHash', ['--hdiutil', ''],
             framework=FRAMEWORK, codesign=blind, work=work)
        case('a host with both tools is ready', 'ready to build the runtime addon',
             ['--hdiutil', str(hdiutil), '--codesign', str(good), '--probe', str(probe), '--require'],
             board=block, framework=FRAMEWORK, work=work)
        case('the report records the state', 'cannot build the runtime addon on this host',
             ['--hdiutil', '', '--out', str(work / 'out')], framework=FRAMEWORK, codesign=blind, work=work)
        case('a missing probe binary is a failure', 'no probe binary to read a CDHash from',
             ['--hdiutil', str(hdiutil), '--codesign', str(good), '--probe', str(work / 'nope')],
             framework=FRAMEWORK, work=work)

        report = json.loads((work / 'out' / 'report.json').read_text())
        if report['ready'] is False and report['hardware_verified'] is False and report['board']['present'] is False:
            print('ok report.json')
        else:
            global failed
            failed += 1
            print('FAIL report.json: ' + json.dumps(report)[:200])

    print('TESTS OK' if not failed else 'TESTS FAILED')
    print('{} case(s), {} failure(s)'.format(passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
