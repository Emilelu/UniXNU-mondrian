#!/usr/bin/env python3
"""0524: the Bluetooth device-tree node and its checker."""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DTS = os.path.join(ROOT, 'dts', 'mondrian.dts')
CHECK = os.path.join(ROOT, 'scripts', 'check-bluetooth-dt.py')

CASES = 0
FAILURES = []


def check(ok, message):
    global CASES
    CASES += 1
    if not ok:
        FAILURES.append(message)


def run(*args):
    return subprocess.run([sys.executable, CHECK, *args],
                          capture_output=True, text=True)


check(os.path.exists(CHECK), 'check-bluetooth-dt.py exists')
result = run('--dts', DTS)
check(result.returncode == 0, 'the shipped dts passes: ' + result.stdout[-400:])
check(result.stdout.count('PASS') >= 9, 'the checker runs its nine assertions')

source = open(DTS, encoding='utf-8').read()
for prop in ('device_type', 'compatible', 'unixnu,adt-name',
             'transport-encoding', 'transport-speed', 'status'):
    check(prop in source, 'the dts carries ' + prop)
check(source.count('unixnu,adt-name = "bluetooth"') == 1,
      'the dts names the bluetooth node once')
check('compatible = "qcom,wcn6855-bt"' in source,
      'the dts uses the K60/WCN6855 binding')

with tempfile.TemporaryDirectory() as tmp:
    bad = os.path.join(tmp, 'bad.dts')
    open(bad, 'w', encoding='utf-8').write(
        source.replace('transport-speed = <3000000>', 'transport-speed = <3200000>'))
    result = run('--dts', bad)
    check(result.returncode != 0, 'a wrong transport-speed is rejected')
    check('transport-speed' in result.stdout, 'the failure names the property')

    dup = os.path.join(tmp, 'dup.dts')
    open(dup, 'w', encoding='utf-8').write(
        source + '\nbluetooth2 { unixnu,adt-name = "bluetooth"; };\n')
    result = run('--dts', dup)
    check(result.returncode != 0, 'a duplicate adt name is rejected')

    empty = os.path.join(tmp, 'empty.dts')
    open(empty, 'w', encoding='utf-8').write('/dts-v1/;\n')
    result = run('--dts', empty)
    check(result.returncode != 0, 'a missing node is rejected')

print('TESTS OK %d case(s), %d failure(s)' % (CASES, len(FAILURES)))
for failure in FAILURES:
    print('FAIL ' + failure)
sys.exit(1 if FAILURES else 0)
