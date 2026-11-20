#!/usr/bin/env python3
"""Check the K60 Bluetooth device-tree contract.

The porting page asks the board to publish a bluetooth node before userland:
device_type, compatible, unixnu,adt-name, transport-encoding and
transport-speed.  This script reads the source dts, and optionally the built
dtb and the ADT inside a payload, so a change cannot silently drop a property.

With --driver it also refuses the node advertising a rate the driver does not
run: the node's transport-speed must equal K60_BT_RUN_BAUD in the patch that
programs the UART, and the encoding must stay 1 (H4).  Neither file can drift
without the other noticing.

Exit code 0 = every requested input passed; 1 = at least one check failed.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

EXPECTED = {
    'device_type': '"bluetooth"',
    'compatible': '"qcom,wcn6855-bt"',
    'unixnu,adt-name': '"bluetooth"',
    'transport-encoding': '1',
    'transport-speed': '3000000',
    'status': '"okay"',
}

FAILURES = []


def check(ok, message):
    if not ok:
        FAILURES.append(message)
    print(('PASS  ' if ok else 'FAIL  ') + message)


def node_block(text, name):
    """Return the root-level node body for *name* using brace matching."""
    pattern = re.compile(r'^\s*' + re.escape(name) + r'\s*\{', re.M)
    match = pattern.search(text)
    if not match:
        return None
    start = text.index('{', match.start())
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    return None


def dts_value(text, prop):
    body = node_block(text, 'bluetooth') or ''
    match = re.search(r'^\s*' + re.escape(prop) + r'\s*=\s*(.+?);\s*$', body, re.M)
    if not match:
        return None
    return match.group(1).strip().strip('<>')


def check_dts(path):
    text = open(path, encoding='utf-8').read()
    body = node_block(text, 'bluetooth')
    check(body is not None, f'{path}: root bluetooth node exists')
    if body is None:
        return text
    for prop, want in EXPECTED.items():
        match = re.search(r'^\s*' + re.escape(prop) + r'\s*=\s*(.+?);\s*$',
                          body, re.M)
        got = match.group(1).strip() if match else None
        if prop in ('transport-encoding', 'transport-speed'):
            got = (got or '').strip('<>')
        check(got == want, f'{path}: {prop} = {got!r} (want {want!r})')
    names = re.findall(r'unixnu,adt-name\s*=\s*"([^"]+)"', text)
    check(names.count('bluetooth') == 1,
          f'{path}: unixnu,adt-name "bluetooth" appears once '
          f'(total adt names: {len(names)})')
    reserved = {'bluetooth', 'wlan', 'pci', 'usb'}
    duplicates = [n for n in set(names) if names.count(n) > 1]
    check(not duplicates, f'{path}: adt names unique (duplicates: {duplicates})')
    return text


def check_driver(path, dts_text):
    """The node must advertise the rate the driver actually programs."""
    if not os.path.exists(path):
        check(False, f'{path}: driver source exists')
        return
    text = open(path, encoding='utf-8').read()
    match = re.search(r'#define\s+K60_BT_RUN_BAUD\s+(\d+)u?', text)
    run = int(match.group(1)) if match else None
    check(run is not None, f'{path}: K60_BT_RUN_BAUD is defined')
    speed = dts_value(dts_text, 'transport-speed')
    if run is not None:
        check(speed is not None and speed.isdigit() and int(speed) == run,
              f'{path}: K60_BT_RUN_BAUD {run} matches transport-speed {speed}')
    encoding = dts_value(dts_text, 'transport-encoding')
    check(encoding == '1',
          f'{path}: transport-encoding {encoding} is H4 (1), the framing the driver writes')


def check_dtb(path):
    if not os.path.exists(path):
        check(False, f'{path}: dtb exists')
        return
    check(True, f'{path}: dtb exists')
    for prop, want in EXPECTED.items():
        value = subprocess.run(['fdtget', path, '/bluetooth', prop],
                               capture_output=True, text=True)
        got = value.stdout.strip() if value.returncode == 0 else None
        # fdtget prints strings without the quotes the dts source uses.
        expect = want.strip('"') if want.startswith('"') else want
        check(got == expect, f'{path}: /bluetooth {prop} = {got!r} '
                             f'(want {expect!r})')


def check_payload(path):
    if not os.path.exists(path):
        check(False, f'{path}: payload exists')
        return
    with tempfile.TemporaryDirectory() as tmp:
        adt = os.path.join(tmp, 'kernel.macho.adt')
        copy = subprocess.run(['mcopy', '-n', '-i', path,
                               '::/EFI/UniXNU/Payloads/kernel.macho.adt', adt],
                              capture_output=True, text=True)
        check(copy.returncode == 0 and os.path.exists(adt),
              f'{path}: ADT extracted'.rstrip() + ('' if copy.returncode == 0
              else ' (' + copy.stderr.strip() + ')'))
        if not os.path.exists(adt):
            return
        data = open(adt, 'rb').read()
    check(data.count(b'bluetooth\x00') >= 1,
          f'{path}: ADT carries the bluetooth node')
    check(b'qcom,wcn6855-bt\x00' in data,
          f'{path}: ADT carries compatible qcom,wcn6855-bt')
    check(data.count(b'transport-speed\x00') >= 1,
          f'{path}: ADT carries transport-speed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dts', default='dts/mondrian.dts')
    parser.add_argument('--dtb')
    parser.add_argument('--payload')
    parser.add_argument('--driver', help='patch that defines K60_BT_RUN_BAUD')
    args = parser.parse_args()
    text = check_dts(args.dts)
    if args.driver:
        check_driver(args.driver, text)
    if args.dtb:
        check_dtb(args.dtb)
    if args.payload:
        check_payload(args.payload)
    print(f'bluetooth-dt-check: {"OK" if not FAILURES else "FAILED"} '
          f'({len(FAILURES)} failure(s))')
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
