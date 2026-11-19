#!/usr/bin/env python3
"""The GENI platform check: the engine source against a register model."""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECK = os.path.join(ROOT, 'scripts', 'check-bluetooth-geni.py')
PATCH = os.path.join(ROOT, 'patches', 'xnu', '0500-k60-bt-qbt-new-files.patch')
FIXTURE = os.path.join(ROOT, 'scripts', 'tests', 'fixtures', 'bt-geni-model.c')

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


check(os.path.exists(CHECK), 'check-bluetooth-geni.py exists')
check(os.path.exists(FIXTURE), 'the register model fixture exists')

with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, 'report')
    result = run('--out', out)
    check(result.returncode == 0, 'the shipped series passes: ' + result.stdout[-400:])
    check('bluetooth-geni-check: OK' in result.stdout,
          'the checker reports OK')
    check(result.stdout.count('PASS ') >= 60,
          'the model runs its assertions: ' + str(result.stdout.count('PASS ')))

    report_path = os.path.join(out, 'report.json')
    check(os.path.exists(report_path), 'the checker writes a report')
    report = json.load(open(report_path, encoding='utf-8'))
    check(report['passed'] is True, 'the report says passed')
    check(report['hardware_verified'] is False,
          'the report never claims hardware verification')
    check(report['registers_simulated'] >= 30,
          'the report counts the simulated registers')
    check(report['assertions'] >= 60, 'the report counts the assertions')
    check(sorted(report['inputs']) == ['qbt_geni.c', 'qbt_geni.h',
                                       'qbt_geni_regs.h'],
          'the report fingerprints the three engine sources')
    check(report['origin']['patch_sha256'] ==
          '4e6f58d96f1ba06cd8d440feaa7546e3df05519631a8550b96a6441ba69bc0b0',
          'the report fingerprints the 0500 patch')
    for name in ('prepare', 'rate', 'start', 'write', 'receive', 'fault',
                 'quiesce', 'flow'):
        check(report['scenarios'][name]['returncode'] == 0,
              'scenario ' + name + ' passes on its own')

    single = run('--scenario', 'rate')
    check(single.returncode == 0, 'one scenario can be selected')
    check('3 Mbaud from 48 MHz at 16x is exact' in single.stdout,
          'the rate scenario checks the board rate')

    # A changed patch must not silently pass: the extracted source drives the
    # model, so a damaged packing write has to fail.
    broken = os.path.join(tmp, 'broken.patch')
    source = open(PATCH, encoding='utf-8').read()
    open(broken, 'w', encoding='utf-8').write(
        source.replace('wr(g,G_TX_PACK0,0x4380e)', 'wr(g,G_TX_PACK0,0x4380f)'))
    result = run('--patch', broken)
    check(result.returncode != 0, 'a changed register header fails the check')

    missing = run('--patch', os.path.join(tmp, 'absent.patch'))
    check(missing.returncode != 0, 'a missing patch is refused')
    check('missing patch' in missing.stdout + missing.stderr,
          'the refusal names the missing patch')

    tree = run('--tree', tmp)
    check(tree.returncode != 0, 'an empty tree is refused')

if FAILURES:
    for failure in FAILURES:
        print('FAIL ' + failure)
    print('TESTS FAILED (%d/%d)' % (len(FAILURES), CASES))
    sys.exit(1)
print('TESTS OK %d case(s)' % CASES)
