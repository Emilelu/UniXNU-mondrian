#!/usr/bin/env python3
"""check-kprintf-enabled: the flag and the print-trap fix must travel together."""
import pathlib
import subprocess
import sys
import tempfile

CHECK = pathlib.Path(__file__).resolve().parents[1] / 'check-kprintf-enabled.py'

BASE = '''[board]
os_profile = "{profile}"

[payload]
kernel_args = [{args}]
'''

OVERRIDE = '''[board]
os_profile = "ios-27.0.1-24A446"

[payload]
kernel_args = ["-v"]

[os_overrides."ios-27.0.1-24A446".payload]
kernel_args = [{args}]
'''

SERIES_FIX = '[P1] 0557-k60-fb-print-after-rows.patch\n'
SERIES_NONE = '[P1] 0556-k60-fb-full-witness.patch\n'

failures: list[str] = []


def run(board: str, series: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / 'board.toml').write_text(board, encoding='utf-8')
        (root / 'series').write_text(series, encoding='utf-8')
        return subprocess.run([sys.executable, str(CHECK), '--device', tmp, '--series', str(root / 'series')],
                              capture_output=True, text=True)


def check(name: str, process: subprocess.CompletedProcess, want: int) -> None:
    if process.returncode != want:
        failures.append(f'{name}: rc={process.returncode} want={want} out={process.stdout}{process.stderr}')


check('27 flag with the trap fix', run(BASE.format(profile='ios-27.0.1-24A446',
                                                   args='"-v", "-enable_kprintf_spam"'), SERIES_FIX), 0)
check('27 flag without the trap fix', run(BASE.format(profile='ios-27.0.1-24A446',
                                                      args='"-v", "-enable_kprintf_spam"'), SERIES_NONE), 1)
check('27 trap fix without the flag', run(BASE.format(profile='ios-27.0.1-24A446',
                                                      args='"-v", "debug=0x14e"'), SERIES_FIX), 1)
check('27 override supplies the flag', run(OVERRIDE.format(args='"-v", "-enable_kprintf_spam"'), SERIES_FIX), 0)
check('16 profile is skipped', run(BASE.format(profile='ipados-16.6.1-20G81', args='"-v"'), SERIES_NONE), 0)

if failures:
    for failure in failures:
        print('FAIL ' + failure)
    sys.exit(1)
print('TESTS OK 5 cases')
