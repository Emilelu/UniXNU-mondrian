#!/usr/bin/env python3
"""Tests for check-bluetooth-dt.py, including the --driver cross-check."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'check-bluetooth-dt.py'
CASES = []

DTS = '''/ {
	bluetooth {
		device_type = "bluetooth";
		compatible = "qcom,wcn6855-bt";
		unixnu,adt-name = "bluetooth";
		transport-encoding = <%s>;
		transport-speed = <%s>;
		status = "okay";
	};
};
'''


def case(name, ok, detail=None):
    CASES.append((name, ok, detail))


def run(dts, driver=None):
    command = [sys.executable, str(TOOL), '--dts', str(dts)]
    if driver is not None:
        command += ['--driver', str(driver)]
    return subprocess.run(command, capture_output=True, text=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        good_dts = tmp / 'good.dts'
        good_dts.write_text(DTS % ('1', '3000000'))
        slow_dts = tmp / 'slow.dts'
        slow_dts.write_text(DTS % ('1', '3200000'))
        other_encoding = tmp / 'enc2.dts'
        other_encoding.write_text(DTS % ('2', '3000000'))

        driver = tmp / 'driver.patch'
        driver.write_text('+#define K60_BT_RUN_BAUD              3000000u\n')
        faster = tmp / 'faster.patch'
        faster.write_text('+#define K60_BT_RUN_BAUD              3200000u\n')
        undefined = tmp / 'undefined.patch'
        undefined.write_text('+int unrelated;\n')

        done = run(good_dts, driver)
        case('a node that advertises the driver rate passes',
             done.returncode == 0 and 'matches transport-speed 3000000' in done.stdout,
             done.stdout)

        done = run(slow_dts, faster)
        case('a node and a driver that disagree pass nothing',
             done.returncode == 1 and 'matches transport-speed 3200000' in done.stdout,
             done.stdout)

        done = run(good_dts, undefined)
        case('a driver without the define is red',
             done.returncode == 1 and 'K60_BT_RUN_BAUD is defined' in done.stdout,
             done.stdout)

        done = run(good_dts, tmp / 'absent.patch')
        case('an absent driver file is red', done.returncode == 1, done.stdout)

        done = run(other_encoding, driver)
        case('an encoding other than H4 is red',
             done.returncode == 1 and 'is H4 (1)' in done.stdout, done.stdout)

        done = run(good_dts)
        case('without --driver the old checks still run', done.returncode == 0, done.stdout)

    failures = [c for c in CASES if not c[1]]
    for name, ok, detail in CASES:
        print(('ok   ' if ok else 'FAIL ') + name)
        if not ok and detail:
            print('     ' + detail.strip().replace('\n', '\n     '))
    print('TESTS OK %d case(s)' % len(CASES) if not failures
          else 'TESTS FAILED %d of %d' % (len(failures), len(CASES)))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
