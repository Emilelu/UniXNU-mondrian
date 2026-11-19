#!/usr/bin/env python3
"""Report whether this host can build the [payload.runtime] addon.

scripts/unixnu/runtime.py sets request['os_image'] as soon as board.toml names a
bluetooth_tool, and scripts/build-boot-runtime.py then mounts that image with
hdiutil (os_mount()) and verifies every staged executable with codesign --display
(verified_cdhash()/bundle_cdhash()).  Both are macOS tools; the Linux shims the
CI installs for the xnu host tools deliberately do nothing.  This checker reads
the board block, the framework source and the host, and says which of the three
is missing, so a red payload build after enabling the block is not mistaken for
a Bluetooth regression.

Nothing here touches the device, the kernel or the build output.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CDHASH = re.compile(r'^CDHash=([0-9a-f]{40})$', re.M)


def find_section(text, name):
    """Return the body of the TOML table called name, or None."""
    lines, start = text.splitlines(), None
    for index, line in enumerate(lines):
        if line.strip() == '[' + name + ']':
            start = index + 1
            break
    if start is None:
        return None
    body = []
    for line in lines[start:]:
        if line.startswith('['):
            break
        body.append(line)
    return '\n'.join(body)


def read_key(body, key):
    match = re.search(r'^' + re.escape(key) + r'\s*=\s*"([^"]*)"', body, re.M)
    return match.group(1) if match else None


def check_board(path):
    failures = []
    if not path.is_file():
        return dict(present=False, tool=None, target=None), ['board.toml not found: ' + str(path)]
    body = find_section(path.read_text(), 'payload.runtime')
    if body is None:
        return dict(present=False, tool=None, target=None), failures
    tool = read_key(body, 'bluetooth_tool')
    target = read_key(body, 'bluetooth_target')
    if tool is None:
        failures.append('[payload.runtime] has no bluetooth_tool; the block would build no Bluetooth services')
    if tool is not None and target is None:
        failures.append('[payload.runtime] has bluetooth_tool but no bluetooth_target')
    return dict(present=True, tool=tool, target=target), failures


def check_framework(path):
    failures = []
    if not path.is_file():
        return dict(present=False, hdiutil=False, cdhash=False), ['build-boot-runtime.py not found: ' + str(path)]
    text = path.read_text()
    hdiutil = "['hdiutil'" in text or "run('hdiutil'" in text
    cdhash = "'--display'" in text and 'CDHash=' in text
    if not hdiutil:
        failures.append('build-boot-runtime.py does not mount the OS image through hdiutil')
    if not cdhash:
        failures.append('build-boot-runtime.py does not read a CDHash through codesign --display')
    return dict(present=True, hdiutil=hdiutil, cdhash=cdhash), failures


def check_host(hdiutil, codesign, probe):
    failures = []
    hdiutil_path = hdiutil or shutil.which('hdiutil') or ''
    if not hdiutil_path or not Path(hdiutil_path).is_file():
        failures.append('hdiutil is not on this host; the OS image cannot be mounted')
        hdiutil_path = ''
    codesign_path = codesign or shutil.which('codesign') or ''
    cdhash = False
    if not codesign_path or not Path(codesign_path).is_file():
        failures.append('codesign is not on this host')
        codesign_path = ''
    elif not Path(probe).is_file():
        failures.append('no probe binary to read a CDHash from: ' + str(probe))
    else:
        done = subprocess.run([codesign_path, '--display', '--verbose=4', str(probe)],
                              capture_output=True, text=True)
        cdhash = bool(CDHASH.search(done.stderr))
        if not cdhash:
            failures.append('codesign printed no CDHash for ' + str(probe) +
                            '; on Linux this is the no-op shim, so verified_cdhash() fails')
    return dict(hdiutil=hdiutil_path, codesign=codesign_path, cdhash=cdhash), failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--board', type=Path, default=Path('board.toml'))
    parser.add_argument('--framework', type=Path,
                        default=Path(__file__).resolve().parent.parent.parent / 'UniXNU' / 'scripts' / 'build-boot-runtime.py')
    parser.add_argument('--hdiutil', default='')
    parser.add_argument('--codesign', default='')
    parser.add_argument('--probe', type=Path, default=Path('/bin/ls'))
    parser.add_argument('--require', action='store_true',
                        help='fail unless this host can build the runtime addon')
    parser.add_argument('--require-runtime', action='store_true',
                        help='fail unless board.toml enables [payload.runtime]')
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args()

    board, board_failures = check_board(args.board)
    framework, framework_failures = check_framework(args.framework)
    host, host_failures = check_host(args.hdiutil, args.codesign, args.probe)
    ready = not (board_failures or framework_failures or host_failures)
    failures = board_failures + framework_failures + host_failures

    print('board: [payload.runtime] ' + ('with bluetooth_tool ' + str(board['tool']) +
                                        ' -> ' + str(board['target']) if board['present'] else 'absent'))
    print('framework: hdiutil mount ' + ('yes' if framework['hdiutil'] else 'no') +
          ', codesign CDHash ' + ('yes' if framework['cdhash'] else 'no'))
    print('host: hdiutil ' + (host['hdiutil'] or 'missing') +
          ', codesign ' + (host['codesign'] or 'missing') +
          ', CDHash ' + ('yes' if host['cdhash'] else 'no'))
    print('verdict: ' + ('ready to build the runtime addon' if ready else
                         'cannot build the runtime addon on this host'))
    for line in failures:
        print('  - ' + line)

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'report.json').write_text(json.dumps(dict(
            board=board, framework=framework, host=host, ready=ready,
            failures=failures, hardware_verified=False), indent=2) + '\n')

    code = 0
    if args.require and not ready:
        print('bluetooth-payload-host: FAIL (this host cannot build the runtime addon)', file=sys.stderr)
        code = 1
    if args.require_runtime and not board['present']:
        print('bluetooth-payload-host: FAIL ([payload.runtime] is not enabled)', file=sys.stderr)
        code = 1
    if code == 0:
        print('bluetooth-payload-host: OK ({} failure(s))'.format(len(failures)))
    return code


if __name__ == '__main__':
    sys.exit(main())
