#!/usr/bin/env python3
"""Tests for check-kernel-console.py (P-300).

The judge is split out of the symbol reader precisely so this test needs no
kernel: what has to be right is the decision, not llvm-nm.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'console_check', ROOT / 'scripts/check-kernel-console.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

checks = 0


def check(name, condition, detail=''):
    global checks
    checks += 1
    if not condition:
        raise SystemExit(f'FAIL {name}{": " + detail if detail else ""}')
    print(f'ok {name}')


missing = {'_k60_serial_clock', '_vfs_mount', '_proc_parent'}

status, line = mod.judge(missing)
check('absent_is_two', status == 2, line)
check('absent_names_why', 'silence cannot' in line, line)

status, line = mod.judge(missing | {'_pong_ramoops_console_write'})
check('one_sink_is_enough', status == 0, line)
check('sink_is_named', '_pong_ramoops_console_write' in line, line)

status, line = mod.judge({'_k60_usblog_console_up'})
check('ep0_counts', status == 0, line)

status, line = mod.judge({'_k60_serial_clock'}, require='_pong_ramoops_console_write')
check('require_refuses_other_sink', status == 2, line)

status, line = mod.judge({'_pong_ramoops_console_write'},
                         require='_pong_ramoops_console_write')
check('require_accepts_its_own', status == 0, line)

# The 16.6.1 kernel is the positive control: it really has the mirror.  The 27
# kernel is the negative control until 0546 is built in.  Both are optional so
# the test still runs on a host without either tree.
sixteen = pathlib.Path('/opt/k60/trees/cellular-k49/mondrian/'
                       'ipados-16.6.1-20G81/mondrian/kernel/kernel.macho')
if sixteen.is_file():
    have = mod.symbols(str(sixteen))
    check('sixteen_has_a_sink', bool(have) and mod.judge(have)[0] == 0)
else:
    print('skip sixteen_has_a_sink (no 16.6.1 kernel on this host)')

print(f'TESTS OK: {checks} cases')
